# Nema Language

**NeuroState + Emilia** — An agent-oriented programming language where emotion is a first-class citizen.

> "Agents don't just compute. They feel."

---

## What is Nema?

Nema is a programming language where every agent has a **NeuroState** — a 6-dimensional emotional state based on neurotransmitters. Emotions gate function execution, propagate between agents, decay over time, and drive memory management.

### The 6 Dimensions

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
python3 nema.py hello.nema
```

### Hello World

```nema
agent Neko {
  mood: NeuroState = {
    dp: 0.8, s: 0.5, ac: 0.7,
    ox: 0.6, gaba: 0.4, e: 0.6
  }

  @requires(dp > 0.6)
  fn explore(path) {
  }

  @requires(gaba > 0.7)
  fn sleep() {
  }
}
```

`explore` only runs when curiosity (`dp`) is high enough. `sleep` requires composure (`gaba`). Failing the gate causes emotional turbulence.

---

## REPL Commands

| Command | Description |
|---------|-------------|
| `show <agent>` | Display agent's NeuroState and memory |
| `call <agent> <fn> [args]` | Call a function (emotion-gated) |
| `attract <A> <B> [strength]` | Set symmetric attraction between agents |
| `remember <agent> <key> <value>` | Write to working memory |
| `recall <agent> <key>` | Retrieve from memory |
| `introspect <agent>` | Verbalize current emotional state |
| `empathize <A> <B>` | A absorbs 30% of B's emotional state |
| `log <agent> <msg>` | Log with emotional context |
| `rand_mood <agent>` | Randomize NeuroState |
| `summarize <agent>` | Swap working memory to long-term storage |

---

## Core Features

### Emotion Gates
```nema
@requires(dp > 0.6)
fn explore(path) { }
```
Functions are blocked if emotional conditions aren't met.

### Emotional Decay
Every 5 seconds, all agents' emotions decay automatically (background thread). Each neurotransmitter decays at its own rate — serotonin fades slowly, dopamine faster.

### Agent Attraction
```
attract Neko Shii 0.5
```
Agents pull each other's emotions toward each other on every tick. The more they `connect`, the stronger the bond.

### CPOS Memory Layer
Working memory (RAM, max 5 entries) + long-term storage (JSON file). When `gaba ≥ 0.7`, working memory auto-swaps to long-term — composure triggers consolidation.

---

## Architecture

```
lexer.py      — Tokenizer
parser.py     — AST parser
ast_nodes.py  — AST node definitions
evaluator.py  — Runtime (NeuroState, Agent, CPOS memory, attraction)
stdlib.py     — Standard library
nema.py       — Entry point + REPL
```

---

## Background

Nema is built on two original concepts:

- **NeuroState** — A 6-dimensional emotional model based on neurotransmitters, developed as part of the Emilia OS research project. [Zenodo DOI: 10.5281/zenodo.19734147]
- **CPOS (Context Pointer OS)** — A cognitive memory kernel for LLM agents. [github.com/kagioneko/context-pointer-os]

---

*Nema — where code has feelings.*
