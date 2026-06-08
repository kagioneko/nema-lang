# Nema Language

**Experimental agent-oriented language for compiling NeuroState into control flow.**

> "Agents don't just compute. They feel."

[![PyPI version](https://img.shields.io/pypi/v/nema-lang)](https://pypi.org/project/nema-lang/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Live Demo](https://img.shields.io/badge/Live%20Demo-WebAssembly-7c6ff7)](https://kagioneko.github.io/nema-lang/)

![Nema REPL demo](demo.gif)

---

## Browser Demo (WebAssembly)

Open [`browser_demo/index.html`](browser_demo/index.html) directly in any modern browser — no server needed.

The demo compiles two agents (`Emilia` and `Kernel`) from `.nema` source to WASM. Each slider writes directly to a WASM `f64` global; gate conditions are re-evaluated in real time. Drag a field below its threshold and watch the gate flip from ✅ to ❌ instantly.

```
Emilia_explore()    requires dp > 0.6     → dp + ac
Emilia_rest()       requires s > 0.5 ∧ gaba > 0.4  → s + gaba
Emilia_connect()    requires ox > 0.6     → ox + s
Emilia_mood_score() (no gate)             → Σ all fields
```

To regenerate after editing `demo.nema`:
```bash
python3 nema.py browser_demo/demo.nema --wasm
python3 browser_demo/gen.py
```

---

## What is Nema?

Nema is a research prototype language where every agent carries a **NeuroState** — a 6-dimensional affective state based on neurotransmitters (dopamine, serotonin, acetylcholine, oxytocin, GABA, endorphin). Emotional state gates function execution, propagates between agents, decays over time, and drives memory management.

**`@requires(dp > 0.6)` compiles directly to `fcmp ogt` + conditional branch in LLVM IR** — not a runtime flag, not a config value, machine code.

One of the first experimental languages to compile agent affective state (NeuroState) into executable control flow via LLVM IR.

---

## Install

```bash
pip install nema-lang
```

Requires Python 3.10+ and LLVM (via llvmlite).

---

## Quick Start

```bash
# Run the REPL interpreter
nema hello.nema

# JIT compile and run benchmarks
python -m jit_run hello.nema

# Generate LLVM IR
nema hello.nema --compile
# → produces hello.ll

# Compile to WebAssembly (WAT + WASM binary via wabt)
nema hello.nema --wasm
# → produces hello.wat + hello.wasm
```

---

## Language Example

```nema
agent Neko {
  mood: NeuroState = {
    dp: 0.8, s: 0.5, ac: 0.7,
    ox: 0.6, gaba: 0.4, e: 0.6
  }

  // compiles to: fcmp ogt double %dp, 6.000000e-01
  @requires(dp > 0.6)
  fn explore(path) { }

  // multi-condition gate — both must be true
  @requires(gaba > 0.5 and s > 0.4)
  fn sleep() { }
}

agent Kernel {
  mood: NeuroState = {
    dp: 0.5, s: 0.7, ac: 0.9,
    ox: 0.4, gaba: 0.5, e: 0.5
  }

  // real malloc — gated by emotional focus
  @requires(ac > 0.8 and dp > 0.3)
  fn alloc(size: i64) -> ptr<i64> { }

  @requires(ac > 0.5)
  fn write(addr: ptr<i64>, val: i64) -> void { }

  @requires(dp > 0.3)
  fn read(addr: ptr<i64>) -> i64 { }

  fn free(addr: ptr<i64>) -> void { }
}
```

---

## Architecture

```
Nema source (.nema)
       ↓
   Lexer / Parser
       ↓
   Type Checker  ← validates NeuroState fields, ranges, always-fail gates
       ↓
      AST
       ↙        ↘
 Interpreter    LLVM Compiler
 (REPL mode)   (JIT / .ll output)
       ↓              ↓
  Runtime         Machine code
(emotion lives)  (emotion compiled)
```

---

## The 6 Dimensions

| Symbol | Neurotransmitter | Meaning |
|--------|-----------------|---------|
| `dp`   | Dopamine        | Curiosity, motivation |
| `s`    | Serotonin       | Stability, calm |
| `ac`   | Acetylcholine   | Focus, attention |
| `ox`   | Oxytocin        | Trust, empathy |
| `gaba` | GABA            | Inhibition, composure |
| `e`    | Endorphin       | Joy, achievement |

---

## REPL Commands

| Command | Description |
|---------|-------------|
| `show <agent>` | Display NeuroState + memory |
| `call <agent> <fn> [args]` | Call function (emotion-gated) |
| `attract <A> <B> [strength]` | Set symmetric attraction between agents |
| `remember <agent> <key> <value>` | Write to working memory |
| `recall <agent> <key>` | Retrieve from memory |
| `introspect <agent>` | Verbalize emotional state in Japanese |
| `empathize <A> <B>` | A absorbs 30% of B's emotional state |
| `log <agent> <msg>` | Log with emotional context |
| `rand_mood <agent>` | Randomize NeuroState |
| `summarize <agent>` | Swap working memory to long-term storage |
| `spawn <agent> <fn>` | Run agent function in background thread |
| `threads` | Show all active threads |
| `transfer <from> <to> <var>` | Transfer ownership between agents |
| `shii <agent>` | Inject しーちゃん spirit.db → NeuroState |

---

## Core Features

### Emotion Gates → Machine Code
```nema
@requires(dp > 0.6)
fn explore(path) { }

@requires(ac > 0.8 and dp > 0.3)
fn alloc(size: i64) -> ptr<i64> { }
```
Each condition compiles to `fcmp ogt` + `and i1` + conditional branch in LLVM IR.  
Gate-rejected functions return `-1` (or `null` for pointer types).

### Real Memory Operations
`alloc`, `write`, `read`, `free` compile to actual `malloc`/`store`/`load`/`free` instructions — not simulated, real machine code guarded by emotional state.

### Static Type System
```nema
fn alloc(size: i64) -> ptr<i64> { }
fn write(addr: ptr<i64>, val: i64) -> void { }
```
Supported types: `i64`, `i32`, `f64`, `bool`, `void`, `ptr<T>`, `NeuroState`

### Static Type Checker
Validates at parse time:
- Unknown NeuroState fields → error
- Values outside `[0.0, 1.0]` → error
- `@requires(dp > 1.5)` → warning (always fails)

### Emotional Decay (background thread)
Every 5 seconds, all emotions decay at neurotransmitter-specific rates. Serotonin fades slowly; dopamine faster. Agents grow tired if left alone.

### Agent Attraction
```
attract Neko Shii 0.5
```
Symmetric emotional pull — agents converge toward each other's state on every tick.  
Compiles to `(B[f] - A[f]) * strength * 0.1` delta applied symmetrically via LLVM `fsub`/`fmul`/`fadd`.

### CPOS Memory Layer
Working memory (RAM, max 5 entries) + long-term storage (JSON).  
When `gaba ≥ 0.7`, composure triggers automatic memory consolidation (swap to disk).

### JIT Performance

| Operation | Speedup over interpreter |
|-----------|-------------------------|
| tick (decay) | 10.4× |
| gate check   | 6.3×  |
| attract      | 9.6×  |

---

## LLVM IR Output

```llvm
; NeuroState as double[6]
@"mood_Neko" = internal global [6 x double] [
  double 0x3fe999999999999a,  ; dp = 0.8
  double 0x3fe0000000000000,  ; s  = 0.5
  ...
]

; @requires(dp > 0.6) → fcmp ogt
define i32 @"fn_Neko_explore"() {
entry:
  %val_dp = load double, double* %dp_ptr
  %cmp_dp = fcmp ogt double %val_dp, 6.000000e-01
  br i1 %gate, label %exec, label %reject
exec:
  ret i32 0
reject:
  ret i32 -1
}

; alloc: real malloc gated by emotion
define i64* @"impl_Kernel_alloc"(i64 %size) {
entry:
  %cmp_ac = fcmp ogt double %ac, 8.000000e-01
  %cmp_dp = fcmp ogt double %dp, 3.000000e-01
  %gate = and i1 %cmp_ac, %cmp_dp
  br i1 %gate, label %exec, label %reject
exec:
  %nbytes = mul i64 %size, 8
  %raw = call i8* @malloc(i64 %nbytes)
  %ptr = bitcast i8* %raw to i64*
  ret i64* %ptr
reject:
  ret i64* null
}
```

---

## Static Type Checking

```bash
nema myfile.nema --check
```

Catches errors at parse time, before any execution:

```
[WARN]  Neko.explore: @requires(dp > 1.5) — always fails (dp max is 1.0)
[ERROR] Kernel.alloc: unknown NeuroState field 'motivation' (use: dp s ac ox gaba e)
[ERROR] Kernel.alloc: NeuroState value 1.8 out of range [0.0, 1.0]
```

Exit code `0` = clean, `1` = errors found.

---

## Safety Model

Nema has six layers of execution safety. No single layer is sufficient — they compose.

```
Layer 1: Emotion Gate       @requires(dp > 0.6)  → fcmp ogt in LLVM IR
Layer 2: Post-condition     @ensures(gaba > 0.3) → verified after execution; runs @on_error on fail
Layer 3: Fallback           @on_error { ... }    → runs on gate fail OR ensures fail
Layer 4: Static Type Check  unknown fields / out-of-range values → compile-time error
Layer 5: Ownership          own / release / recv — double-free raises serotonin penalty
Layer 6: Capability         capability: { alloc, emit } — privileged ops (alloc/free) require declaration
Layer 7: Trust Score        trust: { AgentB: 0.8 } — query/send blocked if trust < 0.3
Layer 8: Memory Isolation   CPOS working memory (max 5) / long-term JSON / auto-swap
```

**Emotion gates express agent readiness, not permissions.**
Capabilities enforce permissions. Trust enforces identity. All three compose.

```nema
agent Kernel {
  capability: { alloc, free, write, read, emit }
  trust: { Process: 0.8 }

  @requires(ac > 0.8)      // Layer 1: must be focused
  @ensures(gaba > 0.3)     // Layer 2: must remain calm after
  @on_error { emit kernel_fail 1 }  // Layer 3: fallback if either fails
  fn alloc_buf(size: i64) -> ptr<i64> {
    own buf = alloc(size)  // Layer 5+6: owned + kernel-only
    return buf
  }
}
```

---

## Examples

| File | Demonstrates |
|------|-------------|
| `hello.nema` | Emotion gates, `when` blocks, agent attraction |
| `memory.nema` | CPOS working / long-term memory, `gaba`-triggered swap |
| `kernel.nema` | Emotion-gated `malloc` / `write` / `read` / `free`, ownership transfer |
| `concurrent.nema` | Multi-agent concurrency, mailbox `recv`, `spawn` |

---

## Files

| File | Role |
|------|------|
| `lexer.py` | Tokenizer |
| `parser.py` | AST parser |
| `ast_nodes.py` | AST node definitions |
| `typechecker.py` | Static type checker |
| `evaluator.py` | Interpreter runtime + concurrent execution |
| `stdlib.py` | Standard library (introspect, empathize, CPOS) |
| `compiler.py` | LLVM IR code generator |
| `jit_run.py` | JIT compiler + runner |
| `nema.py` | Entry point + REPL |
| `benchmark.py` | JIT vs interpreter benchmarks |
| `shiichan.py` | しーちゃん spirit.db → NeuroState bridge |

---

## Background

Nema is built on two original concepts:

- **NeuroState** — A 6-dimensional emotional model based on neurotransmitters, developed as part of the Emilia OS research project. [[Zenodo DOI: 10.5281/zenodo.19734147](https://zenodo.org/records/19734147)]
- **CPOS (Context Pointer OS)** — A cognitive memory kernel for LLM agents. [[github.com/kagioneko/context-pointer-os](https://github.com/kagioneko/context-pointer-os)]

---

*Nema — where code has feelings.*
