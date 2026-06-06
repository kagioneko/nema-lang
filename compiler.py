"""
Nema → LLVM IR コンパイラ (v0.1)

最初のターゲット:
- NeuroStateをdouble[6]の配列としてコンパイル
- エージェントのmoodをグローバル変数として生成
- mood_get/mood_set関数を生成
- メイン関数でmoodを出力
"""

from llvmlite import ir
from ast_nodes import Program, AgentDecl

NEURO_FIELDS = ["dp", "s", "ac", "ox", "gaba", "e"]
NEURO_LABELS = {
    "dp": "Dopamine",
    "s":  "Serotonin",
    "ac": "Acetylcholine",
    "ox": "Oxytocin",
    "gaba": "GABA",
    "e":  "Endorphin",
}


class NemaCompiler:
    def __init__(self, program: Program):
        self.program = program
        self.module = ir.Module(name="nema_module")
        self.module.triple = "x86_64-unknown-linux-gnu"

        self.double = ir.DoubleType()
        self.i32 = ir.IntType(32)
        self.i8p = ir.PointerType(ir.IntType(8))
        self.void = ir.VoidType()

        # printf宣言
        printf_ty = ir.FunctionType(self.i32, [self.i8p], var_arg=True)
        self.printf = ir.Function(self.module, printf_ty, name="printf")

        self.agent_moods: dict[str, ir.GlobalVariable] = {}
        self._str_counter = 0
        self._compile_agents()
        self._compile_main()

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

    def _compile_fn(self, agent_name: str, fn_decl, mood_gv: ir.GlobalVariable):
        """
        感情ゲート付き関数をLLVM IRにコンパイル。
        戻り値: i32 (0=実行OK, -1=感情ゲート拒否)
        """
        OPS = {">" : "ogt", "<" : "olt", ">=": "oge", "<=": "ole", "==": "oeq"}

        fn_ty = ir.FunctionType(self.i32, [])
        fn = ir.Function(self.module, fn_ty,
                         name=f"fn_{agent_name}_{fn_decl.name}")

        entry_block  = fn.append_basic_block("entry")
        exec_block   = fn.append_basic_block("exec")
        reject_block = fn.append_basic_block("reject")

        builder = ir.IRBuilder(entry_block)

        if fn_decl.requires:
            # 全条件をANDで結合
            cond_result = ir.Constant(ir.IntType(1), 1)  # true
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

        # 実行ブロック: 0を返す
        builder = ir.IRBuilder(exec_block)
        builder.ret(ir.Constant(self.i32, 0))

        # 拒否ブロック: -1を返す
        builder = ir.IRBuilder(reject_block)
        builder.ret(ir.Constant(self.i32, -1))

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
