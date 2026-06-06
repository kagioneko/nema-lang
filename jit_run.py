"""
NemaのLLVM IRをJITコンパイルして直接実行する
"""
import ctypes
import sys
from llvmlite import ir, binding

from lexer import Lexer
from parser import Parser
from typechecker import typecheck, report
from compiler import NemaCompiler, NEURO_FIELDS, NEURO_LABELS


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
                fn = ctypes.CFUNCTYPE(ctypes.c_int32)(fn_ptr)
                result = fn()
                if fn_decl.requires:
                    cond = fn_decl.requires[0]
                    cond_str = f"@requires({cond[0]}{cond[1]}{cond[2]})"
                else:
                    cond_str = "(no gate)"
                status = "✅ 実行OK" if result == 0 else "❌ 拒否"
                print(f"  {fn_decl.name:<12} {cond_str:<24} → {status}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("usage: jit_run.py <file.nema>")
        sys.exit(1)
    with open(sys.argv[1]) as f:
        src = f.read()
    jit_run(src)
