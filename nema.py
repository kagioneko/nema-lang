#!/usr/bin/env python3
import sys
import os
import threading
import time
from lexer import Lexer
from parser import Parser
from evaluator import Evaluator, ATTRACTORS, NEURO_FIELDS
from typechecker import typecheck, report
from compiler import compile_program

DECAY_INTERVAL = 5.0
VERSION = "0.1.0"

HELP_TEXT = """
Nema Language Interpreter v0.1.0
usage: nema <file.nema> [options]

Options:
  --compile   Generate LLVM IR (.ll file)
  --check     Type-check only (no REPL)
  --live      Live-updating emotion graph (updates in place)
  --version   Show version
  --help      Show this message

REPL Commands:
  show <agent>                    Display NeuroState + memory
  call <agent> <fn> [args...]     Call function (emotion-gated)
  attract <A> <B> [strength]      Set symmetric attraction (default 0.3)
  attractor <agent> <state>       Pull agent toward attractor state
                                  States: explore / rest / social / crisis / flow / none
  send <from> <to> <message>      Send message between agents
  remember <agent> <key> <value>  Write to working memory
  recall <agent> <key>            Read from memory
  introspect <agent>              Verbalize emotional state in Japanese
  empathize <A> <B>               A absorbs 30%% of B's emotion
  log <agent> <msg>               Timestamped log with mood
  rand_mood <agent>               Randomize NeuroState
  summarize <agent>               Swap working memory → long-term
  shii <agent> [db_path]          Inject しーちゃん spirit.db → agent NeuroState
  tick                            Manually trigger emotion decay + when blocks
  quit / exit                     Exit
""".strip()


def run(src: str, strict: bool = False):
    tokens = Lexer(src).tokenize()
    program = Parser(tokens).parse()
    has_errors = report(typecheck(program))
    if strict and has_errors:
        sys.exit(1)
    return Evaluator(program)


def decay_loop(ev: Evaluator, stop: threading.Event, live: bool = False):
    while not stop.is_set():
        time.sleep(DECAY_INTERVAL)
        ev.tick()
        if live:
            _live_render(ev)
        else:
            print("\n[tick] 感情が減衰した")
            for name, agent in ev.agents.items():
                s = agent.mood.state
                summary = " | ".join(f"{f}={s[f]:.2f}"
                                     for f in ["dp", "s", "gaba", "e"])
                attractor = agent.mood.nearest_attractor()
                print(f"  {name}: {summary}  [{attractor}]")
            print("> ", end="", flush=True)


def _live_render(ev: Evaluator):
    """ANSI エスケープでインプレース更新"""
    lines = []
    for name, agent in ev.agents.items():
        s = agent.mood.state
        lines.append(f"\033[1mAgent: {name}\033[0m  [{agent.mood.nearest_attractor()}]")
        for f in NEURO_FIELDS:
            val = s[f]
            filled = int(val * 30)
            bar = "█" * filled + "░" * (30 - filled)
            lines.append(f"  {f:4s} [{bar}] {val:.2f}")
        lines.append("")

    total = len(lines)
    # カーソルを上に移動して上書き
    sys.stdout.write(f"\033[{total}A")
    for line in lines:
        sys.stdout.write(f"\033[2K{line}\n")
    sys.stdout.flush()


def main():
    args = sys.argv[1:]

    if not args or "--help" in args or "-h" in args:
        print(HELP_TEXT)
        sys.exit(0)

    if "--version" in args or "-v" in args:
        print(f"nema-lang {VERSION}")
        sys.exit(0)

    live_mode    = "--live" in args
    compile_mode = "--compile" in args
    check_mode   = "--check" in args
    path = next((a for a in args if not a.startswith("--")), None)

    if not path:
        print("エラー: .nema ファイルを指定してください")
        sys.exit(1)

    try:
        with open(path) as f:
            src = f.read()
    except FileNotFoundError:
        print(f"エラー: ファイルが見つかりません: {path}")
        sys.exit(1)

    if check_mode:
        tokens = Lexer(src).tokenize()
        program = Parser(tokens).parse()
        has_errors = report(typecheck(program))
        sys.exit(1 if has_errors else 0)

    if compile_mode:
        tokens = Lexer(src).tokenize()
        program = Parser(tokens).parse()
        has_errors = report(typecheck(program))
        if has_errors:
            sys.exit(1)
        ir_code = compile_program(program)
        out_path = path.replace(".nema", ".ll")
        with open(out_path, "w") as f:
            f.write(ir_code)
        print(f"✅ LLVM IR生成: {out_path}")
        sys.exit(0)

    ev = run(src)

    if live_mode:
        # ライブモード: 初期描画用の空行を確保
        total_lines = sum(len(NEURO_FIELDS) + 2 for _ in ev.agents)
        print("\n" * total_lines, end="")
        _live_render(ev)
    else:
        for name in ev.agents:
            ev.show(name)
            print()

    stop = threading.Event()
    t = threading.Thread(target=decay_loop,
                         args=(ev, stop, live_mode), daemon=True)
    t.start()

    if not live_mode:
        print(f"--- Nema REPL ({DECAY_INTERVAL}秒ごとに自動decay / --help で一覧) ---")

    while True:
        try:
            line = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if line in ("quit", "exit"):
            break
        if not line:
            continue

        parts = line.split()
        cmd = parts[0]

        if cmd == "show" and len(parts) == 2:
            ev.show(parts[1])

        elif cmd == "call" and len(parts) >= 3:
            ev.call(parts[1], parts[2], parts[3:])

        elif cmd == "attract" and len(parts) >= 3:
            strength = float(parts[3]) if len(parts) > 3 else 0.3
            ev.attract(parts[1], parts[2], strength)

        elif cmd == "attractor" and len(parts) >= 3:
            ev.set_attractor(parts[1], parts[2])

        elif cmd == "send" and len(parts) >= 4:
            ev.send_message(parts[1], parts[2], " ".join(parts[3:]))
            ev._deliver_messages()

        elif cmd == "tick":
            ev.tick()
            print("[手動tick] 感情減衰 + whenチェック完了")

        elif cmd == "introspect" and len(parts) == 2:
            agent = ev.agents.get(parts[1])
            if agent: print(agent.std.introspect())

        elif cmd == "summarize" and len(parts) == 2:
            agent = ev.agents.get(parts[1])
            if agent: print(agent.std.summarize())

        elif cmd == "empathize" and len(parts) == 3:
            a, b = ev.agents.get(parts[1]), ev.agents.get(parts[2])
            if a and b: print(a.std.empathize(b))

        elif cmd == "log" and len(parts) >= 3:
            agent = ev.agents.get(parts[1])
            if agent: agent.std.log(" ".join(parts[2:]))

        elif cmd == "rand_mood" and len(parts) == 2:
            agent = ev.agents.get(parts[1])
            if agent: print(agent.std.rand_mood())

        elif cmd == "remember" and len(parts) >= 4:
            agent = ev.agents.get(parts[1])
            if agent:
                agent.memory.remember(parts[2], " ".join(parts[3:]))
                print(f"[記憶] {parts[1]}: #{parts[2]} = {' '.join(parts[3:])}")
            else:
                print(f"[エラー] agent {parts[1]} が見つからない")

        elif cmd == "recall" and len(parts) == 3:
            agent = ev.agents.get(parts[1])
            if agent:
                val = agent.memory.recall(parts[2])
                print(f"[想起] #{parts[2]} = {val}" if val
                      else f"[なし] #{parts[2]} は記憶にない")
            else:
                print(f"[エラー] agent {parts[1]} が見つからない")

        elif cmd == "shii" and len(parts) >= 2:
            try:
                from shiichan import load_latest, print_mapping, SPIRIT_DB_DEFAULT
                db = parts[2] if len(parts) > 2 else str(SPIRIT_DB_DEFAULT)
                nema_state, ts, raw = load_latest(db)
                print(f"[しーちゃん] {ts}")
                print_mapping(raw, nema_state)
                ev.inject_neurostate(parts[1], nema_state)
            except Exception as ex:
                print(f"[エラー] しーちゃん連携失敗: {ex}")

        elif cmd in ("help", "--help"):
            print(HELP_TEXT)

        else:
            print("? コマンドが不明です。'help' で一覧を表示")

    stop.set()


if __name__ == "__main__":
    main()
