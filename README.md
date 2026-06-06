# Nema Language

**NeuroState + Emilia** — An agent-oriented programming language where emotion is a first-class citizen.

> "Agents don't just compute. They feel."

---

## What is Nema?

Nema is a programming language where every agent has a **NeuroState** — a 6-dimensional emotional state based on neurotransmitters. Emotions gate function execution, propagate between agents, decay over time, and drive memory management.

**`@requires(dp > 0.6)` compiles to a machine-level `fcmp ogt` instruction.**  
The world's first emotional conditional branch.

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

## Quick Start

```bash
# Interpreter (REPL)
python3 nema.py hello.nema

# JIT compile + run
.venv/bin/python3 jit_run.py hello.nema

# Generate LLVM IR
.venv/bin/python3 nema.py hello.nema --compile
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

  // gaba too low → machine-level branch to reject block
  @requires(gaba > 0.7)
  fn sleep() { }
}

agent Shii {
  mood: NeuroState = {
    dp: 0.3, s: 0.7, ac: 0.5,
    ox: 0.8, gaba: 0.6, e: 0.4
  }

  @requires(s > 0.6)
  fn rest() { }
}
```

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

---

## Core Features

### Emotion Gates → Machine Code
```nema
@requires(dp > 0.6)
fn explore(path) { }
```
Compiles to `fcmp ogt` + conditional branch in LLVM IR. If the condition fails, execution branches to a reject block returning `-1`.

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

### CPOS Memory Layer
Working memory (RAM, max 5 entries) + long-term storage (JSON). When `gaba ≥ 0.7`, composure triggers automatic memory consolidation.

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
```

---

## Files

| File | Role |
|------|------|
| `lexer.py` | Tokenizer |
| `parser.py` | AST parser |
| `ast_nodes.py` | AST node definitions |
| `typechecker.py` | Static type checker |
| `evaluator.py` | Interpreter runtime |
| `stdlib.py` | Standard library |
| `compiler.py` | LLVM IR code generator |
| `jit_run.py` | JIT compiler + runner |
| `nema.py` | Entry point + REPL |
| `hello.nema` | Example program |

---

## Background

Nema is built on two original concepts:

- **NeuroState** — A 6-dimensional emotional model based on neurotransmitters, developed as part of the Emilia OS research project. [[Zenodo DOI: 10.5281/zenodo.19734147](https://zenodo.org/records/19734147)]
- **CPOS (Context Pointer OS)** — A cognitive memory kernel for LLM agents. [[github.com/kagioneko/context-pointer-os](https://github.com/kagioneko/context-pointer-os)]

---

*Nema — where code has feelings.*
