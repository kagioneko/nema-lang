"""
Nema ベンチマーク: インタープリタ vs JIT (LLVM機械語)

測定対象:
1. mood_tick (decay) × N回
2. emotion gate check × N回
3. attract × N回
"""
import ctypes
import time
import sys
sys.path.insert(0, "/home/mayutama/nema")

from llvmlite import binding
from lexer import Lexer
from parser import Parser
from evaluator import Agent, NeuroState
from compiler import NemaCompiler, NEURO_FIELDS
from typechecker import typecheck, report

ITERATIONS = 100_000
SRC = open("/home/mayutama/nema/hello.nema").read()


def setup_jit():
    tokens = Lexer(SRC).tokenize()
    program = Parser(tokens).parse()
    comp = NemaCompiler(program)
    ir_code = comp.get_ir()
    defined = {str(f.name) for f in comp.module.functions}

    binding.initialize_native_target()
    binding.initialize_native_asmprinter()
    llvm_mod = binding.parse_assembly(ir_code)
    llvm_mod.verify()
    tm = binding.Target.from_default_triple().create_target_machine()
    engine = binding.create_mcjit_compiler(llvm_mod, tm)
    engine.finalize_object()
    engine.run_static_constructors()
    return engine, defined


def bench(label: str, fn, n: int) -> float:
    start = time.perf_counter()
    for _ in range(n):
        fn()
    elapsed = time.perf_counter() - start
    per_call = elapsed / n * 1_000_000  # μs
    print(f"  {label:<40} {elapsed:.3f}s  ({per_call:.4f} μs/call)")
    return elapsed


def main():
    print(f"=== Nema Benchmark ({ITERATIONS:,} iterations) ===\n")

    # --- セットアップ ---
    tokens = Lexer(SRC).tokenize()
    program = Parser(tokens).parse()
    engine, defined = setup_jit()

    neko_decl = next(a for a in program.agents if a.name == "Neko")

    # --- 1. mood_tick (decay) ---
    print("[ mood_tick: decay ]")

    # インタープリタ
    interp_agent = Agent(neko_decl)
    t_interp_tick = bench(
        "Interpreter (Python)",
        interp_agent.mood.tick,
        ITERATIONS
    )

    # JIT
    tick_ptr = engine.get_function_address("mood_tick_Neko")
    tick_fn = ctypes.CFUNCTYPE(None)(tick_ptr)
    t_jit_tick = bench(
        "JIT (LLVM machine code)",
        tick_fn,
        ITERATIONS
    )
    print(f"  → JIT speedup: {t_interp_tick / t_jit_tick:.1f}x\n")

    # --- 2. emotion gate check ---
    print("[ emotion gate: @requires(dp > 0.6) ]")

    interp_agent2 = Agent(neko_decl)
    fn_decl = next(f for f in neko_decl.fns if f.name == "explore")

    def interp_gate():
        interp_agent2.mood.check(fn_decl.requires)

    t_interp_gate = bench(
        "Interpreter (Python)",
        interp_gate,
        ITERATIONS
    )

    gate_ptr = engine.get_function_address("fn_Neko_explore")
    gate_fn = ctypes.CFUNCTYPE(ctypes.c_int)(gate_ptr)
    t_jit_gate = bench(
        "JIT (LLVM machine code)",
        gate_fn,
        ITERATIONS
    )
    print(f"  → JIT speedup: {t_interp_gate / t_jit_gate:.1f}x\n")

    # --- 3. attract ---
    print("[ attract: Neko ~~ Shii (strength=0.5) ]")

    from evaluator import Evaluator
    ev = Evaluator(program)
    ev.attract("Neko", "Shii", 0.5)

    def interp_attract():
        ev.apply_attractions()

    t_interp_attract = bench(
        "Interpreter (Python)",
        interp_attract,
        ITERATIONS
    )

    attract_ptr = engine.get_function_address("attract_Neko_Shii")
    attract_fn = ctypes.CFUNCTYPE(None, ctypes.c_double)(attract_ptr)

    def jit_attract():
        attract_fn(0.5)

    t_jit_attract = bench(
        "JIT (LLVM machine code)",
        jit_attract,
        ITERATIONS
    )
    print(f"  → JIT speedup: {t_interp_attract / t_jit_attract:.1f}x\n")

    # --- まとめ ---
    print("[ Summary ]")
    print(f"  tick    : {t_interp_tick / t_jit_tick:.1f}x faster")
    print(f"  gate    : {t_interp_gate / t_jit_gate:.1f}x faster")
    print(f"  attract : {t_interp_attract / t_jit_attract:.1f}x faster")


if __name__ == "__main__":
    main()
