#!/usr/bin/env python3
import sys
import threading
import time
from lexer import Lexer
from parser import Parser
from evaluator import Evaluator
from typechecker import typecheck, report

DECAY_INTERVAL = 5.0  # 5秒ごとにtick


def run(src: str, strict: bool = False):
    tokens = Lexer(src).tokenize()
    program = Parser(tokens).parse()
    has_errors = report(typecheck(program))
    if strict and has_errors:
        sys.exit(1)
    return Evaluator(program)


def decay_loop(ev: Evaluator, stop: threading.Event):
    while not stop.is_set():
        time.sleep(DECAY_INTERVAL)
        for agent in ev.agents.values():
            agent.mood.tick()
        ev.apply_attractions()
        # 減衰通知
        print("\n[tick] 感情が減衰した")
        for name in ev.agents:
            agent = ev.agents[name]
            summary = " | ".join(
                f"{f}={agent.mood.state[f]:.2f}"
                for f in ["dp", "s", "gaba", "e"]
            )
            print(f"  {name}: {summary}")
        print("> ", end="", flush=True)


def main():
    if len(sys.argv) < 2:
        print("usage: nema.py <file.nema>")
        sys.exit(1)

    path = sys.argv[1]
    with open(path) as f:
        src = f.read()

    ev = run(src)

    for name in ev.agents:
        ev.show(name)
        print()

    # バックグラウンドdecayスレッド起動
    stop = threading.Event()
    t = threading.Thread(target=decay_loop, args=(ev, stop), daemon=True)
    t.start()

    print(f"--- Nema REPL (quit で終了 / {DECAY_INTERVAL}秒ごとに自動decay) ---")
    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if line in ("quit", "exit"):
            break
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "show" and len(parts) == 2:
            ev.show(parts[1])
        elif parts[0] == "call" and len(parts) >= 3:
            ev.call(parts[1], parts[2], parts[3:])
        elif parts[0] == "attract" and len(parts) >= 3:
            strength = float(parts[3]) if len(parts) > 3 else 0.3
            ev.attract(parts[1], parts[2], strength)
        elif parts[0] == "introspect" and len(parts) == 2:
            agent = ev.agents.get(parts[1])
            if agent: print(agent.std.introspect())
        elif parts[0] == "summarize" and len(parts) == 2:
            agent = ev.agents.get(parts[1])
            if agent: print(agent.std.summarize())
        elif parts[0] == "empathize" and len(parts) == 3:
            a, b = ev.agents.get(parts[1]), ev.agents.get(parts[2])
            if a and b: print(a.std.empathize(b))
        elif parts[0] == "log" and len(parts) >= 3:
            agent = ev.agents.get(parts[1])
            if agent: agent.std.log(" ".join(parts[2:]))
        elif parts[0] == "rand_mood" and len(parts) == 2:
            agent = ev.agents.get(parts[1])
            if agent: print(agent.std.rand_mood())
        elif parts[0] == "remember" and len(parts) >= 4:
            agent = ev.agents.get(parts[1])
            if agent:
                agent.memory.remember(parts[2], " ".join(parts[3:]))
                print(f"[記憶] {parts[1]}: #{parts[2]} = {' '.join(parts[3:])}")
            else:
                print(f"[エラー] agent {parts[1]} が見つからない")
        elif parts[0] == "recall" and len(parts) == 3:
            agent = ev.agents.get(parts[1])
            if agent:
                val = agent.memory.recall(parts[2])
                print(f"[想起] {parts[1]}: #{parts[2]} = {val}" if val else f"[なし] #{parts[2]} は記憶にない")
            else:
                print(f"[エラー] agent {parts[1]} が見つからない")
        else:
            print("コマンド: show <agent> | call <agent> <fn> [args...] | attract <A> <B> [strength] | remember <agent> <key> <value> | recall <agent> <key>")

    stop.set()


if __name__ == "__main__":
    main()
