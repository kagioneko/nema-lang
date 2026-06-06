import json
import os
from ast_nodes import Program, AgentDecl, NeuroStateNode
from stdlib import StdLib

CPOS_SWAP_THRESHOLD = 0.7   # gabaがこれ以上で作業記憶をスワップ
CPOS_WORKING_LIMIT  = 5     # 作業記憶の最大エントリ数

NEURO_FIELDS = ["dp", "s", "ac", "ox", "gaba", "e"]
NEURO_LABELS = {
    "dp":   "Dopamine      (好奇心・やる気)",
    "s":    "Serotonin     (安定・落ち着き)",
    "ac":   "Acetylcholine (集中・注意)",
    "ox":   "Oxytocin      (信頼・共感)",
    "gaba": "GABA          (抑制・冷静さ)",
    "e":    "Endorphin     (快楽・達成感)",
}

# 関数実行後の感情変化ルール
AFTER_EFFECTS = {
    "explore": {"dp": +0.1, "e": +0.05},
    "connect": {"ox": +0.1, "s": +0.05},
    "sleep":   {"s": +0.2, "gaba": -0.1},
}

# 失敗時の感情変化ルール
ERROR_EFFECTS = {"s": -0.2, "gaba": +0.1}

# 時間減衰レート（tickごと）
DECAY_RATES = {"dp": 0.01, "s": 0.005, "ac": 0.008, "ox": 0.007, "gaba": 0.003, "e": 0.01}


class NeuroState:
    def __init__(self, values: dict[str, float]):
        self.state = {f: 0.0 for f in NEURO_FIELDS}
        self.state.update(values)

    def check(self, conditions: list[tuple]) -> bool:
        ops = {">": float.__gt__, "<": float.__lt__, ">=": float.__ge__,
               "<=": float.__le__, "==": float.__eq__}
        return all(ops[op](self.state.get(field, 0.0), val)
                   for field, op, val in conditions)

    def apply(self, effects: dict[str, float]):
        for field, delta in effects.items():
            self.state[field] = max(0.0, min(1.0, self.state.get(field, 0.0) + delta))

    def tick(self):
        for field, rate in DECAY_RATES.items():
            self.state[field] = max(0.0, self.state[field] - rate)

    @property
    def gaba(self) -> float:
        return self.state["gaba"]

    def display(self) -> str:
        lines = []
        for f in NEURO_FIELDS:
            val = self.state.get(f, 0.0)
            bar = "█" * int(val * 20) + "░" * (20 - int(val * 20))
            lines.append(f"  {NEURO_LABELS[f]}: [{bar}] {val:.2f}")
        return "\n".join(lines)


class CPOSMemory:
    """作業記憶（RAM）と長期記憶（ディスク）の二層メモリ"""

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.working: dict[str, str] = {}           # 作業記憶（アクティブ）
        self.storage_path = f"/tmp/nema_{agent_name}_longterm.json"
        self._load_storage()

    def _load_storage(self):
        if os.path.exists(self.storage_path):
            with open(self.storage_path) as f:
                self.storage: dict[str, str] = json.load(f)
        else:
            self.storage: dict[str, str] = {}

    def _save_storage(self):
        with open(self.storage_path, "w") as f:
            json.dump(self.storage, f, ensure_ascii=False)

    def remember(self, key: str, value: str):
        """作業記憶に書き込む"""
        self.working[key] = value

    def recall(self, key: str) -> str | None:
        """作業記憶→長期記憶の順で検索"""
        if key in self.working:
            return self.working[key]
        if key in self.storage:
            # 長期記憶から作業記憶に呼び戻す
            self.working[key] = self.storage[key]
            return self.working[key]
        return None

    def swap(self):
        """作業記憶を長期記憶にスワップ（gaba高いときに呼ばれる）"""
        if not self.working:
            return 0
        self.storage.update(self.working)
        self._save_storage()
        count = len(self.working)
        self.working.clear()
        return count

    def forget_oldest(self):
        """作業記憶が上限超えたら古いものを長期記憶へ退避"""
        if len(self.working) <= CPOS_WORKING_LIMIT:
            return
        oldest_key = next(iter(self.working))
        self.storage[oldest_key] = self.working.pop(oldest_key)
        self._save_storage()

    def display(self) -> str:
        lines = [f"  [作業記憶] {len(self.working)}/{CPOS_WORKING_LIMIT}件"]
        for k, v in self.working.items():
            lines.append(f"    #{k}: {v}")
        lines.append(f"  [長期記憶] {len(self.storage)}件 → {self.storage_path}")
        return "\n".join(lines)


class Agent:
    def __init__(self, decl: AgentDecl):
        self.name = decl.name
        self.mood = NeuroState(decl.mood.state.values) if decl.mood else NeuroState({})
        self.fns = {fn.name: fn for fn in decl.fns}
        self.memory = CPOSMemory(decl.name)
        self.std = StdLib(self)

    def call(self, fn_name: str, args: list = None) -> str:
        if fn_name not in self.fns:
            self.mood.apply(ERROR_EFFECTS)
            return f"[エラー] {fn_name} は未定義"
        fn = self.fns[fn_name]
        if fn.requires and not self.mood.check(fn.requires):
            cond = fn.requires[0]
            cur = self.mood.state.get(cond[0], 0.0)
            self.mood.apply(ERROR_EFFECTS)
            return (f"[実行拒否] {fn_name}: "
                    f"{cond[0]}={cur:.2f} が条件 {cond[0]}{cond[1]}{cond[2]} を満たさない")
        # 実行成功 → 感情変化
        if fn_name in AFTER_EFFECTS:
            self.mood.apply(AFTER_EFFECTS[fn_name])
        self.mood.tick()
        self.memory.forget_oldest()
        # gabaが高いと自動スワップ
        if self.mood.gaba >= CPOS_SWAP_THRESHOLD:
            count = self.memory.swap()
            if count:
                return f"[実行OK] {fn_name}({', '.join(args or [])}) [CPOS] 作業記憶{count}件を長期記憶にスワップ"
        return f"[実行OK] {fn_name}({', '.join(args or [])})"

    def display(self) -> str:
        return f"Agent: {self.name}\n{self.mood.display()}\n{self.memory.display()}"


class Evaluator:
    def __init__(self, program: Program):
        self.agents: dict[str, Agent] = {}
        for decl in program.agents:
            self.agents[decl.name] = Agent(decl)
        # 引力ペア: {(A, B): strength}
        self.attractions: dict[tuple[str, str], float] = {}

    def attract(self, a: str, b: str, strength: float = 0.3):
        """エージェントAとBの間に引力を設定（対称）"""
        key = tuple(sorted([a, b]))
        self.attractions[key] = min(1.0, strength)
        print(f"[引力] {a} ~~ {b} (strength={strength:.2f})")

    def apply_attractions(self):
        """引力を全ペアに適用（tickごとに呼ぶ）"""
        for (a, b), strength in self.attractions.items():
            if a not in self.agents or b not in self.agents:
                continue
            sa = self.agents[a].mood.state
            sb = self.agents[b].mood.state
            for f in NEURO_FIELDS:
                diff = sb[f] - sa[f]
                delta = diff * strength * 0.1
                sa[f] = max(0.0, min(1.0, sa[f] + delta))
                sb[f] = max(0.0, min(1.0, sb[f] - delta))

    def show(self, agent_name: str):
        if agent_name not in self.agents:
            print(f"[エラー] agent {agent_name} が見つからない")
            return
        print(self.agents[agent_name].display())

    def call(self, agent_name: str, fn_name: str, args: list = None):
        if agent_name not in self.agents:
            print(f"[エラー] agent {agent_name} が見つからない")
            return
        result = self.agents[agent_name].call(fn_name, args)
        # connect系は引力を強化
        if "connect" in fn_name:
            for (a, b) in list(self.attractions.keys()):
                if agent_name in (a, b):
                    self.attractions[(a, b)] = min(1.0, self.attractions[(a, b)] + 0.01)
        print(result)
