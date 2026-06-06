"""
NemaのLLVM IRをJITコンパイルして直接実行する
"""
import ctypes
import sys
from llvmlite import ir, binding

from lexer import Lexer
from parser import Parser
from typechecker import typecheck, report
from compiler import NemaCompiler, NEURO_FIELDS, NEURO_LABELS, DECAY_RATES


def jit_run(src: str):
    # パース
    tokens = Lexer(src).tokenize()
    program = Parser(tokens).parse()
    has_errors = report(typecheck(program))
    if has_errors:
        sys.exit(1)

    # LLVM IR生成
    comp = NemaCompiler(program)
    ir_code = comp.get_ir()

    # 存在する関数名をセットで管理（get_function_addressのセグフォルト防止）
    defined_fns = {str(f.name) for f in comp.module.functions}

    # LLVMバインディング初期化
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()

    # IRをパース・検証
    llvm_mod = binding.parse_assembly(ir_code)
    llvm_mod.verify()

    # JITエンジン作成
    target = binding.Target.from_default_triple()
    target_machine = target.create_target_machine()
    engine = binding.create_mcjit_compiler(llvm_mod, target_machine)
    engine.finalize_object()
    engine.run_static_constructors()

    # 各エージェントの感情値とゲートをJIT経由で実行
    print("\n=== Nema JIT実行 ===")
    for agent in program.agents:
        if not agent.mood:
            continue
        print(f"\nAgent: {agent.name}")
        for field in NEURO_FIELDS:
            fn_name = f"mood_get_{agent.name}_{field}"
            fn_ptr = engine.get_function_address(fn_name)
            fn = ctypes.CFUNCTYPE(ctypes.c_double)(fn_ptr)
            val = fn()
            bar = "█" * int(val * 20) + "░" * (20 - int(val * 20))
            print(f"  {NEURO_LABELS[field]:<16}: [{bar}] {val:.4f}")

        # 感情ゲート関数のJIT呼び出し
        if agent.fns:
            print(f"\n  --- 感情ゲート (機械語) ---")
            for fn_decl in agent.fns:
                jit_name = f"fn_{agent.name}_{fn_decl.name}"
                fn_ptr = engine.get_function_address(jit_name)
                fn = ctypes.CFUNCTYPE(ctypes.c_int)(fn_ptr)
                result = fn()
                if fn_decl.requires:
                    cond = fn_decl.requires[0]
                    cond_str = f"@requires({cond[0]}{cond[1]}{cond[2]})"
                else:
                    cond_str = "(no gate)"
                status = "✅ 実行OK" if result == 0 else "❌ 拒否"
                print(f"  {fn_decl.name:<12} {cond_str:<24} → {status}")

        # decayのJIT呼び出し（3回tick）
        print(f"\n  --- tick × 3 (decay 機械語) ---")
        tick_ptr = engine.get_function_address(f"mood_tick_{agent.name}")
        tick_fn = ctypes.CFUNCTYPE(None)(tick_ptr)
        for _ in range(3):
            tick_fn()

        get_dp_ptr = engine.get_function_address(f"mood_get_{agent.name}_dp")
        get_dp = ctypes.CFUNCTYPE(ctypes.c_double)(get_dp_ptr)
        get_s_ptr = engine.get_function_address(f"mood_get_{agent.name}_s")
        get_s = ctypes.CFUNCTYPE(ctypes.c_double)(get_s_ptr)
        print(f"  dp={get_dp():.4f} (decay×3: -{DECAY_RATES['dp']*3:.3f})")
        print(f"  s ={get_s():.4f} (decay×3: -{DECAY_RATES['s']*3:.3f})")

        # after_effectsのJIT呼び出し（explore実行後）
        after_name = f"mood_after_{agent.name}_explore"
        if after_name in defined_fns:
            after_ptr = engine.get_function_address(after_name)
            after_fn = ctypes.CFUNCTYPE(None)(after_ptr)
            after_fn()
            print(f"\n  --- after explore (dp+0.1, e+0.05 機械語) ---")
            print(f"  dp={get_dp():.4f} (+0.1 applied)")


def jit_attract_demo(engine, program, defined_fns):
    """引力のJITデモ: Neko~~Shii strength=0.5 を10回適用"""
    agents = [a for a in program.agents if a.mood]
    if len(agents) < 2:
        return
    a, b = agents[0], agents[1]
    fn_name = f"attract_{a.name}_{b.name}"
    if fn_name not in defined_fns:
        return

    attract_ptr = engine.get_function_address(fn_name)
    attract_fn = ctypes.CFUNCTYPE(None, ctypes.c_double)(attract_ptr)

    get_a = {f: ctypes.CFUNCTYPE(ctypes.c_double)(
        engine.get_function_address(f"mood_get_{a.name}_{f}"))
        for f in NEURO_FIELDS}
    get_b = {f: ctypes.CFUNCTYPE(ctypes.c_double)(
        engine.get_function_address(f"mood_get_{b.name}_{f}"))
        for f in NEURO_FIELDS}

    print(f"\n=== 引力デモ: {a.name} ~~ {b.name} (strength=0.5, ×10tick) ===")
    print(f"{'':12} {'before_A':>10} {'before_B':>10} {'after_A':>10} {'after_B':>10}")
    before_a = {f: get_a[f]() for f in NEURO_FIELDS}
    before_b = {f: get_b[f]() for f in NEURO_FIELDS}

    for _ in range(10):
        attract_fn(0.5)

    for f in NEURO_FIELDS:
        ba, bb = before_a[f], before_b[f]
        aa, ab = get_a[f](), get_b[f]()
        print(f"  {f:<10} {ba:>10.4f} {bb:>10.4f} {aa:>10.4f} {ab:>10.4f}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: jit_run.py <file.nema>")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        src = f.read()
    jit_run(src)
    # 引力デモは別途呼び出し
    from lexer import Lexer as L
    from parser import Parser as P
    tokens = L(src).tokenize()
    prog = P(tokens).parse()
    comp2 = NemaCompiler(prog)
    ir2 = comp2.get_ir()
    defined2 = {str(f.name) for f in comp2.module.functions}
    binding.initialize_native_target()
    binding.initialize_native_asmprinter()
    llvm2 = binding.parse_assembly(ir2)
    llvm2.verify()
    tm2 = binding.Target.from_default_triple().create_target_machine()
    eng2 = binding.create_mcjit_compiler(llvm2, tm2)
    eng2.finalize_object()
    eng2.run_static_constructors()
    jit_attract_demo(eng2, prog, defined2)
