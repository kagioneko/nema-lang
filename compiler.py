"""
Nema → LLVM IR コンパイラ (v0.1)

最初のターゲット:
- NeuroStateをdouble[6]の配列としてコンパイル
- エージェントのmoodをグローバル変数として生成
- mood_get/mood_set関数を生成
- メイン関数でmoodを出力
"""

from llvmlite import ir
from ast_nodes import (Program, AgentDecl,
                       TypeI64, TypeI32, TypeF64, TypeBool, TypeVoid,
                       TypePtr, TypeNeuroState, NemaType)

NEURO_FIELDS = ["dp", "s", "ac", "ox", "gaba", "e"]
BUILTIN_IMPLS = {"alloc", "write", "read", "free"}
NEURO_LABELS = {
    "dp": "Dopamine",
    "s":  "Serotonin",
    "ac": "Acetylcholine",
    "ox": "Oxytocin",
    "gaba": "GABA",
    "e":  "Endorphin",
}

# 伝達物質ごとの減衰レート（tickごと）
DECAY_RATES = {
    "dp":   0.01,
    "s":    0.005,
    "ac":   0.008,
    "ox":   0.007,
    "gaba": 0.003,
    "e":    0.01,
}

# 関数実行後の感情変化ルール
AFTER_EFFECTS = {
    "explore": {"dp": +0.1, "e": +0.05},
    "connect": {"ox": +0.1, "s": +0.05},
    "sleep":   {"s": +0.2,  "gaba": -0.1},
}


class NemaCompiler:
    def __init__(self, program: Program):
        self.program = program
        self.module = ir.Module(name="nema_module")
        self.module.triple = "x86_64-unknown-linux-gnu"

        self.double = ir.DoubleType()
        self.i64 = ir.IntType(64)
        self.i32 = ir.IntType(32)
        self.i8p = ir.PointerType(ir.IntType(8))
        self.void = ir.VoidType()
        self.bool_t = ir.IntType(1)

        # 外部関数宣言
        printf_ty = ir.FunctionType(self.i32, [self.i8p], var_arg=True)
        self.printf = ir.Function(self.module, printf_ty, name="printf")
        malloc_ty = ir.FunctionType(self.i8p, [self.i64])
        self.malloc_fn = ir.Function(self.module, malloc_ty, name="malloc")
        free_ty = ir.FunctionType(self.void, [self.i8p])
        self.free_fn = ir.Function(self.module, free_ty, name="free")

        self.agent_moods: dict[str, ir.GlobalVariable] = {}
        self._str_counter = 0
        self._compile_agents()
        self._compile_all_attractions()
        self._compile_main()

    def nema_to_llvm(self, t) -> ir.Type:
        if isinstance(t, TypeI64): return self.i64
        if isinstance(t, TypeI32): return self.i32
        if isinstance(t, TypeF64): return self.double
        if isinstance(t, TypeBool): return self.bool_t
        if isinstance(t, TypeVoid): return self.void
        if isinstance(t, TypePtr): return ir.PointerType(self.nema_to_llvm(t.inner))
        return self.void

    def _neurostate_type(self) -> ir.ArrayType:
        return ir.ArrayType(self.double, 6)

    def _compile_agents(self):
        ns_ty = self._neurostate_type()
        for agent in self.program.agents:
            if not agent.mood:
                continue
            vals = [
                ir.Constant(self.double,
                            agent.mood.state.values.get(f, 0.0))
                for f in NEURO_FIELDS
            ]
            init = ir.Constant(ns_ty, vals)
            gv = ir.GlobalVariable(self.module, ns_ty, name=f"mood_{agent.name}")
            gv.initializer = init
            gv.linkage = "internal"
            self.agent_moods[agent.name] = gv

            # mood_get_<Agent>_<field>(void) -> double
            for i, field in enumerate(NEURO_FIELDS):
                fn_ty = ir.FunctionType(self.double, [])
                fn = ir.Function(self.module, fn_ty,
                                 name=f"mood_get_{agent.name}_{field}")
                block = fn.append_basic_block("entry")
                builder = ir.IRBuilder(block)
                zero = ir.Constant(self.i32, 0)
                idx = ir.Constant(self.i32, i)
                ptr = builder.gep(gv, [zero, idx])
                val = builder.load(ptr)
                builder.ret(val)

            # mood_set_<Agent>_<field>(double) -> void
            for i, field in enumerate(NEURO_FIELDS):
                fn_ty = ir.FunctionType(self.void, [self.double])
                fn = ir.Function(self.module, fn_ty,
                                 name=f"mood_set_{agent.name}_{field}")
                block = fn.append_basic_block("entry")
                builder = ir.IRBuilder(block)
                zero = ir.Constant(self.i32, 0)
                idx = ir.Constant(self.i32, i)
                ptr = builder.gep(gv, [zero, idx])
                builder.store(fn.args[0], ptr)
                builder.ret_void()

            # エージェントの関数（感情ゲート付き）をコンパイル
            for fn_decl in agent.fns:
                self._compile_fn(agent.name, fn_decl, gv)

            # mood_tick_<Agent>: 全フィールドをdecayレートで減衰
            self._compile_tick(agent.name, gv)

            # mood_after_<Agent>_<fn>: 関数実行後の感情変化
            for fn_decl in agent.fns:
                if fn_decl.name in AFTER_EFFECTS:
                    self._compile_after(agent.name, fn_decl.name, gv)

    def _compile_fn(self, agent_name: str, fn_decl, mood_gv: ir.GlobalVariable):
        """感情ゲート付き関数をLLVM IRにコンパイル"""
        OPS = {">" : "ogt", "<" : "olt", ">=": "oge", "<=": "ole", "==": "oeq"}

        # 引数型・戻り値型を解決
        param_types = [self.nema_to_llvm(p.type) if p.type else self.i64
                       for p in fn_decl.params]
        ret_llvm = self.nema_to_llvm(fn_decl.ret_type) if fn_decl.ret_type else self.i32

        # ゲート専用の wrapper 関数（引数なし、i32を返す）は維持
        gate_ty = ir.FunctionType(self.i32, [])
        gate_fn = ir.Function(self.module, gate_ty,
                              name=f"fn_{agent_name}_{fn_decl.name}")
        entry_block  = gate_fn.append_basic_block("entry")
        exec_block   = gate_fn.append_basic_block("exec")
        reject_block = gate_fn.append_basic_block("reject")

        builder = ir.IRBuilder(entry_block)
        if fn_decl.requires:
            cond_result = ir.Constant(ir.IntType(1), 1)
            zero = ir.Constant(self.i32, 0)
            for field, op, threshold in fn_decl.requires:
                field_idx = NEURO_FIELDS.index(field)
                idx = ir.Constant(self.i32, field_idx)
                ptr = builder.gep(mood_gv, [zero, idx])
                val = builder.load(ptr, name=f"val_{field}")
                thresh_const = ir.Constant(self.double, threshold)
                cmp = builder.fcmp_ordered(OPS[op], val, thresh_const,
                                           name=f"cmp_{field}")
                cond_result = builder.and_(cond_result, cmp, name="gate")
            builder.cbranch(cond_result, exec_block, reject_block)
        else:
            builder.branch(exec_block)

        builder = ir.IRBuilder(exec_block)
        builder.ret(ir.Constant(self.i32, 0))
        builder = ir.IRBuilder(reject_block)
        builder.ret(ir.Constant(self.i32, -1))

        # ビルトイン関数の本体実装（感情ゲート + 実処理）
        if fn_decl.name in BUILTIN_IMPLS:
            self._compile_builtin(agent_name, fn_decl, mood_gv,
                                  param_types, ret_llvm)

    def _compile_builtin(self, agent_name: str, fn_decl, mood_gv: ir.GlobalVariable,
                         param_types: list, ret_llvm: ir.Type):
        """
        impl_<Agent>_<fn>: 感情ゲート付きで実際のメモリ操作を実行するLLVM関数
          alloc(size: i64) -> ptr<i64>  : malloc(size*8) → bitcast
          write(addr, val) -> void       : store
          read(addr)       -> i64        : load
          free(addr)       -> void       : bitcast → free
        """
        OPS = {">" : "ogt", "<" : "olt", ">=": "oge", "<=": "ole", "==": "oeq"}

        fn_ty = ir.FunctionType(ret_llvm, param_types)
        fn = ir.Function(self.module, fn_ty,
                         name=f"impl_{agent_name}_{fn_decl.name}")

        entry   = fn.append_basic_block("entry")
        exec_b  = fn.append_basic_block("exec")
        reject_b = fn.append_basic_block("reject")

        builder = ir.IRBuilder(entry)
        if fn_decl.requires:
            cond = ir.Constant(ir.IntType(1), 1)
            zero = ir.Constant(self.i32, 0)
            for field, op, threshold in fn_decl.requires:
                fi = NEURO_FIELDS.index(field)
                ptr = builder.gep(mood_gv, [zero, ir.Constant(self.i32, fi)])
                val = builder.load(ptr)
                cmp = builder.fcmp_ordered(OPS[op], val,
                                           ir.Constant(self.double, threshold))
                cond = builder.and_(cond, cmp)
            builder.cbranch(cond, exec_b, reject_b)
        else:
            builder.branch(exec_b)

        # exec ブロック: 実処理
        builder = ir.IRBuilder(exec_b)
        fname = fn_decl.name
        if fname == "alloc":
            size = fn.args[0]
            eight = ir.Constant(self.i64, 8)
            nbytes = builder.mul(size, eight, name="nbytes")
            raw = builder.call(self.malloc_fn, [nbytes], name="raw")
            typed_ptr = builder.bitcast(raw, ir.PointerType(self.i64), name="ptr")
            builder.ret(typed_ptr)
        elif fname == "write":
            addr, val = fn.args[0], fn.args[1]
            builder.store(val, addr)
            builder.ret_void()
        elif fname == "read":
            addr = fn.args[0]
            val = builder.load(addr, name="val")
            builder.ret(val)
        elif fname == "free":
            addr = fn.args[0]
            raw = builder.bitcast(addr, self.i8p, name="raw")
            builder.call(self.free_fn, [raw])
            builder.ret_void()

        # reject ブロック: 型に応じたデフォルト値を返す
        builder = ir.IRBuilder(reject_b)
        if isinstance(ret_llvm, ir.VoidType):
            builder.ret_void()
        elif isinstance(ret_llvm, ir.PointerType):
            builder.ret(ir.Constant(ret_llvm, None))   # null ptr
        else:
            builder.ret(ir.Constant(ret_llvm, -1))

    def _compile_tick(self, agent_name: str, mood_gv: ir.GlobalVariable):
        """mood_tick_<Agent>: 全フィールドをdecayレートで減衰（0.0未満にならない）"""
        fn_ty = ir.FunctionType(self.void, [])
        fn = ir.Function(self.module, fn_ty, name=f"mood_tick_{agent_name}")
        block = fn.append_basic_block("entry")
        builder = ir.IRBuilder(block)
        zero = ir.Constant(self.i32, 0)
        zero_d = ir.Constant(self.double, 0.0)

        for i, field in enumerate(NEURO_FIELDS):
            rate = ir.Constant(self.double, DECAY_RATES[field])
            idx = ir.Constant(self.i32, i)
            ptr = builder.gep(mood_gv, [zero, idx])
            val = builder.load(ptr, name=f"{field}_val")
            decayed = builder.fsub(val, rate, name=f"{field}_decayed")
            # max(0.0, decayed) — llvmiteにはmaxがないのでselectで実装
            cmp = builder.fcmp_ordered("ogt", decayed, zero_d, name=f"{field}_pos")
            clamped = builder.select(cmp, decayed, zero_d, name=f"{field}_clamped")
            builder.store(clamped, ptr)

        builder.ret_void()

    def _compile_after(self, agent_name: str, fn_name: str,
                       mood_gv: ir.GlobalVariable):
        """mood_after_<Agent>_<fn>: 関数実行後の感情変化（clamp 0.0〜1.0）"""
        effects = AFTER_EFFECTS[fn_name]
        fn_ty = ir.FunctionType(self.void, [])
        fn = ir.Function(self.module, fn_ty,
                         name=f"mood_after_{agent_name}_{fn_name}")
        block = fn.append_basic_block("entry")
        builder = ir.IRBuilder(block)
        zero = ir.Constant(self.i32, 0)
        zero_d = ir.Constant(self.double, 0.0)
        one_d  = ir.Constant(self.double, 1.0)

        for field, delta in effects.items():
            i = NEURO_FIELDS.index(field)
            idx = ir.Constant(self.i32, i)
            ptr = builder.gep(mood_gv, [zero, idx])
            val = builder.load(ptr, name=f"{field}_val")
            delta_c = ir.Constant(self.double, delta)
            new_val = builder.fadd(val, delta_c, name=f"{field}_new")
            # clamp [0.0, 1.0]
            cmp_lo = builder.fcmp_ordered("ogt", new_val, zero_d)
            clamped_lo = builder.select(cmp_lo, new_val, zero_d)
            cmp_hi = builder.fcmp_ordered("olt", clamped_lo, one_d)
            clamped = builder.select(cmp_hi, clamped_lo, one_d)
            builder.store(clamped, ptr)

        builder.ret_void()

    def _compile_all_attractions(self):
        """全エージェントペアの引力関数を生成"""
        agents = list(self.agent_moods.items())
        for i in range(len(agents)):
            for j in range(i + 1, len(agents)):
                name_a, gv_a = agents[i]
                name_b, gv_b = agents[j]
                self._compile_attract(name_a, gv_a, name_b, gv_b)

    def _compile_attract(self, name_a: str, gv_a: ir.GlobalVariable,
                         name_b: str, gv_b: ir.GlobalVariable):
        """
        attract_<A>_<B>(double strength) → void
        対称引力: A・Bの各フィールドを互いに引き寄せる
          delta = (B[f] - A[f]) * strength * 0.1
          A[f] += delta  (clamp 0〜1)
          B[f] -= delta  (clamp 0〜1)
        """
        fn_ty = ir.FunctionType(self.void, [self.double])
        fn = ir.Function(self.module, fn_ty,
                         name=f"attract_{name_a}_{name_b}")
        strength = fn.args[0]
        strength.name = "strength"

        block = fn.append_basic_block("entry")
        builder = ir.IRBuilder(block)
        zero   = ir.Constant(self.i32, 0)
        zero_d = ir.Constant(self.double, 0.0)
        one_d  = ir.Constant(self.double, 1.0)
        coeff  = ir.Constant(self.double, 0.1)

        for i, field in enumerate(NEURO_FIELDS):
            idx = ir.Constant(self.i32, i)

            ptr_a = builder.gep(gv_a, [zero, idx])
            ptr_b = builder.gep(gv_b, [zero, idx])
            val_a = builder.load(ptr_a, name=f"a_{field}")
            val_b = builder.load(ptr_b, name=f"b_{field}")

            # delta = (b - a) * strength * 0.1
            diff  = builder.fsub(val_b, val_a, name=f"diff_{field}")
            step  = builder.fmul(diff, strength, name=f"step_{field}")
            delta = builder.fmul(step, coeff, name=f"delta_{field}")

            # A += delta, clamp
            new_a = builder.fadd(val_a, delta, name=f"new_a_{field}")
            cmp_a_lo = builder.fcmp_ordered("ogt", new_a, zero_d)
            cl_a_lo  = builder.select(cmp_a_lo, new_a, zero_d)
            cmp_a_hi = builder.fcmp_ordered("olt", cl_a_lo, one_d)
            cl_a     = builder.select(cmp_a_hi, cl_a_lo, one_d)
            builder.store(cl_a, ptr_a)

            # B -= delta, clamp
            new_b = builder.fsub(val_b, delta, name=f"new_b_{field}")
            cmp_b_lo = builder.fcmp_ordered("ogt", new_b, zero_d)
            cl_b_lo  = builder.select(cmp_b_lo, new_b, zero_d)
            cmp_b_hi = builder.fcmp_ordered("olt", cl_b_lo, one_d)
            cl_b     = builder.select(cmp_b_hi, cl_b_lo, one_d)
            builder.store(cl_b, ptr_b)

        builder.ret_void()

    def _make_str(self, builder: ir.IRBuilder, s: str) -> ir.Constant:
        encoded = (s + "\0").encode("utf-8")
        str_ty = ir.ArrayType(ir.IntType(8), len(encoded))
        self._str_counter += 1
        gv = ir.GlobalVariable(self.module, str_ty,
                               name=f".str.{self._str_counter}")
        gv.initializer = ir.Constant(str_ty, bytearray(encoded))
        gv.global_constant = True
        gv.linkage = "internal"
        zero = ir.Constant(self.i32, 0)
        return builder.gep(gv, [zero, zero])

    def _compile_main(self):
        main_ty = ir.FunctionType(self.i32, [])
        main_fn = ir.Function(self.module, main_ty, name="main")
        block = main_fn.append_basic_block("entry")
        builder = ir.IRBuilder(block)

        for agent_name, gv in self.agent_moods.items():
            # エージェント名の出力
            header = self._make_str(builder, f"\n=== Agent: {agent_name} ===\n")
            builder.call(self.printf, [header])

            # 各フィールドの値を出力
            fmt = self._make_str(builder, "  %-16s: %.4f\n")
            zero = ir.Constant(self.i32, 0)
            for i, field in enumerate(NEURO_FIELDS):
                label = self._make_str(builder, NEURO_LABELS[field])
                idx = ir.Constant(self.i32, i)
                ptr = builder.gep(gv, [zero, idx])
                val = builder.load(ptr)
                builder.call(self.printf, [fmt, label, val])

        builder.ret(ir.Constant(self.i32, 0))

    def get_ir(self) -> str:
        return str(self.module)


def compile_program(program: Program) -> str:
    return NemaCompiler(program).get_ir()
