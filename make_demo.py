#!/usr/bin/env python3
"""v0.3.2 demo.cast 自動生成スクリプト（pexpect使用）"""
import json, time, sys, os, pexpect

CAST_FILE = "demo_v032.cast"
WIDTH, HEIGHT = 100, 32
PROMPT = r">"  # Nema REPLのプロンプト

def write_cast(f, t, data):
    f.write(json.dumps([round(t, 6), "o", data]) + "\n")

def type_line(f, child, cmd, t_ref):
    """コマンドをタイプしてEnterを押す。castに記録。"""
    now = time.time() - t_ref
    # タイプ風に1文字ずつ出力
    for i, ch in enumerate(cmd):
        write_cast(f, now + i * 0.05, ch)
    write_cast(f, now + len(cmd) * 0.05, "\r\n")
    child.sendline(cmd)
    return now + len(cmd) * 0.05 + 0.3

def run_demo():
    t_start = time.time()

    with open(CAST_FILE, "w") as f:
        # ヘッダー
        header = {
            "version": 2,
            "width": WIDTH,
            "height": HEIGHT,
            "timestamp": int(t_start),
            "title": "Nema Language v0.3.2 — for loops & Result<T>",
            "env": {"SHELL": "/bin/bash", "TERM": "xterm-256color"}
        }
        f.write(json.dumps(header) + "\n")

        def w(data, delay=0.0):
            nonlocal t_start
            t = time.time() - t_start + delay
            write_cast(f, t, data)

        # ===== セクション1: for_demo.nema =====
        venv = os.path.join(os.path.dirname(__file__), ".venv", "bin", "python3")
        nema = os.path.join(os.path.dirname(__file__), "nema.py")
        demo_for = os.path.join(os.path.dirname(__file__), "for_demo.nema")
        demo_res = os.path.join(os.path.dirname(__file__), "result_demo.nema")

        # シェルプロンプト表示
        w("\r\n\033[1;32m# Nema v0.3.2 — for loops & Result<T> demo\033[0m\r\n")
        time.sleep(0.4)
        w("\033[1;34m~/nema\033[0m $ ")
        time.sleep(0.5)

        cmd = f"python3 {nema} {demo_for}"
        child = pexpect.spawn(
            venv, [nema, demo_for],
            encoding="utf-8", timeout=15,
            dimensions=(HEIGHT, WIDTH)
        )
        child.logfile_read = None

        # コマンドタイプ演出
        for ch in cmd:
            w(ch)
            time.sleep(0.04)
        w("\r\n")
        time.sleep(0.1)

        # 起動出力を待つ
        child.expect(">")
        out = child.before + ">"
        w(out)
        time.sleep(0.5)

        # call sum_range
        w(" call Counter sum_range\r\n")
        child.sendline("call Counter sum_range")
        child.expect(">")
        out = child.before + ">"
        w(out)
        time.sleep(0.8)

        # call gated_loop（感情ゲートデモ）
        w(" call Counter gated_loop\r\n")
        child.sendline("call Counter gated_loop")
        child.expect(">")
        out = child.before + ">"
        w(out)
        time.sleep(0.8)

        # 低dp状態でゲートブロックデモ
        w(" rand_mood Counter\r\n")
        child.sendline("rand_mood Counter")
        child.expect(">")
        out = child.before + ">"
        w(out)
        time.sleep(0.4)

        w(" call Counter gated_loop\r\n")
        child.sendline("call Counter gated_loop")
        child.expect(">")
        out = child.before + ">"
        w(out)
        time.sleep(0.8)

        # quit
        w(" quit\r\n")
        child.sendline("quit")
        child.close()
        time.sleep(0.3)

        # ===== セクション2: result_demo.nema =====
        w("\r\n\033[1;32m# Result<T> — エラー型デモ\033[0m\r\n")
        time.sleep(0.4)
        w("\033[1;34m~/nema\033[0m $ ")

        cmd2 = f"python3 {nema} {demo_res}"
        for ch in cmd2:
            w(ch)
            time.sleep(0.04)
        w("\r\n")
        time.sleep(0.1)

        child2 = pexpect.spawn(
            venv, [nema, demo_res],
            encoding="utf-8", timeout=15,
            dimensions=(HEIGHT, WIDTH)
        )

        child2.expect(">")
        out = child2.before + ">"
        w(out)
        time.sleep(0.5)

        # ok パス
        w(" call SafeDiv divide 10.0 2.0\r\n")
        child2.sendline("call SafeDiv divide 10.0 2.0")
        child2.expect(">")
        out = child2.before + ">"
        w(out)
        time.sleep(0.8)

        # err パス（ゼロ除算）
        w(" call SafeDiv divide 5.0 0.0\r\n")
        child2.sendline("call SafeDiv divide 5.0 0.0")
        child2.expect(">")
        out = child2.before + ">"
        w(out)
        time.sleep(0.8)

        # match デモ
        w(" call SafeDiv try_err\r\n")
        child2.sendline("call SafeDiv try_err")
        child2.expect(">")
        out = child2.before + ">"
        w(out)
        time.sleep(0.8)

        w(" quit\r\n")
        child2.sendline("quit")
        child2.close()

        w("\r\n\033[1;32m# Done! github.com/kagioneko/nema-lang\033[0m\r\n")

    print(f"✅ cast saved: {CAST_FILE}")

if __name__ == "__main__":
    os.chdir(os.path.dirname(__file__) or ".")
    run_demo()
