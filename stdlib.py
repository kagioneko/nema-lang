import time
import random
from datetime import datetime

NEURO_FIELDS = ["dp", "s", "ac", "ox", "gaba", "e"]

# introspect用の言語化テンプレート
INTROSPECT_TEMPLATES = {
    "dp": [
        (0.7, "好奇心が高まっている。何かを探索したい。"),
        (0.4, "やる気はそこそこある。"),
        (0.0, "意欲が湧かない。"),
    ],
    "s": [
        (0.7, "安定していて落ち着いている。"),
        (0.4, "まあまあ穏やか。"),
        (0.0, "不安定な感じがする。"),
    ],
    "ac": [
        (0.7, "集中できている。"),
        (0.4, "注意力は普通。"),
        (0.0, "散漫な状態。"),
    ],
    "ox": [
        (0.7, "誰かとつながりたい気持ちがある。"),
        (0.4, "他者への関心は普通。"),
        (0.0, "孤立している感覚。"),
    ],
    "gaba": [
        (0.7, "とても冷静で、整理したい気分。"),
        (0.4, "まあ落ち着いている。"),
        (0.0, "抑制が弱く、衝動的になりやすい。"),
    ],
    "e": [
        (0.7, "達成感がある。幸福感が高い。"),
        (0.4, "そこそこ満足している。"),
        (0.0, "快楽が薄い。疲弊気味。"),
    ],
}


def _describe(field: str, val: float) -> str:
    for threshold, text in INTROSPECT_TEMPLATES[field]:
        if val >= threshold:
            return text
    return INTROSPECT_TEMPLATES[field][-1][1]


class StdLib:
    def __init__(self, agent):
        self.agent = agent

    def log(self, msg: str) -> str:
        mood = self.agent.mood.state
        ts = datetime.now().strftime("%H:%M:%S")
        summary = f"dp={mood['dp']:.2f} s={mood['s']:.2f} e={mood['e']:.2f}"
        line = f"[{ts}] [{self.agent.name}|{summary}] {msg}"
        print(line)
        return line

    def wait(self, sec: float) -> str:
        time.sleep(sec)
        # 待機するとgabaが上がる（休憩効果）
        self.agent.mood.apply({"gaba": sec * 0.05, "s": sec * 0.02})
        return f"[wait] {sec}秒待機 → gaba+{sec*0.05:.2f}"

    def rand_mood(self) -> str:
        new_state = {f: round(random.uniform(0.1, 0.9), 2) for f in NEURO_FIELDS}
        self.agent.mood.state.update(new_state)
        return f"[rand_mood] {self.agent.name}の感情をランダム化: " + \
               " ".join(f"{k}={v}" for k, v in new_state.items())

    def summarize(self) -> str:
        mem = self.agent.memory
        if not mem.working:
            return "[summarize] 作業記憶は空"
        summary = "、".join(f"{k}={v}" for k, v in mem.working.items())
        count = mem.swap()
        return f"[summarize] 作業記憶{count}件を要約して長期記憶へ → {summary}"

    def empathize(self, other_agent) -> str:
        src = other_agent.mood.state
        dst = self.agent.mood.state
        for f in NEURO_FIELDS:
            diff = src[f] - dst[f]
            dst[f] = max(0.0, min(1.0, dst[f] + diff * 0.3))
        return (f"[empathize] {self.agent.name} が {other_agent.name} の感情を受け取った "
                f"(ox={dst['ox']:.2f} s={dst['s']:.2f})")

    def introspect(self) -> str:
        state = self.agent.mood.state
        lines = [f"[introspect] {self.agent.name} の内省:"]
        for f in NEURO_FIELDS:
            lines.append(f"  {_describe(f, state[f])}")
        # 支配的な感情を特定
        dominant = max(NEURO_FIELDS, key=lambda f: state[f])
        lines.append(f"  → 今最も強いのは {dominant}（{state[dominant]:.2f}）")
        return "\n".join(lines)
