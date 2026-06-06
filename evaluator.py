import json
import os
from ast_nodes import (Program, AgentDecl, NeuroStateNode,
                       LetStmt, ReturnStmt, ExprStmt, BranchStmt,
                       LoopStmt, BreakStmt, WhenBlock, AttractorDecl,
                       Literal, VarRef, BinOp, FnCallExpr, MsgSend)
from stdlib import StdLib

CPOS_SWAP_THRESHOLD = 0.7
CPOS_WORKING_LIMIT  = 5
MAX_LOOP_ITER       = 1000   # 無限ループ防止

NEURO_FIELDS = ["dp", "s", "ac", "ox", "gaba", "e"]
NEURO_LABELS = {
    "dp":   "Dopamine      (好奇心・やる気)",
    "s":    "Serotonin     (安定・落ち着き)",
    "ac":   "Acetylcholine (集中・注意)",
    "ox":   "Oxytocin      (信頼・共感)",
    "gaba": "GABA          (抑制・冷静さ)",
    "e":    "Endorphin     (快楽・達成感)",
}

AFTER_EFFECTS = {
    "explore": {"dp": +0.1, "e": +0.05},
    "connect": {"ox": +0.1, "s": +0.05},
    "sleep":   {"s": +0.2, "gaba": -0.1},
}

ERROR_EFFECTS = {"s": -0.2, "gaba": +0.1}

DECAY_RATES = {"dp": 0.01, "s": 0.005, "ac": 0.008,
               "ox": 0.007, "gaba": 0.003, "e": 0.01}

# NeuroState 論文の5アトラクター状態
ATTRACTORS = {
    "explore": {"dp": 0.9, "ac": 0.8, "e": 0.7, "s": 0.4, "ox": 0.5, "gaba": 0.3},
    "rest":    {"s": 0.9, "gaba": 0.8, "dp": 0.2, "ac": 0.3, "ox": 0.5, "e": 0.4},
    "social":  {"ox": 0.9, "s": 0.8, "e": 0.7, "dp": 0.5, "ac": 0.4, "gaba": 0.5},
    "crisis":  {"dp": 0.2, "s": 0.1, "ac": 0.3, "ox": 0.2, "gaba": 0.1, "e": 0.1},
    "flow":    {"dp": 0.7, "s": 0.7, "ac": 0.9, "ox": 0.6, "gaba": 0.6, "e": 0.8},
}


class _ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value

class _BreakSignal(Exception):
    pass


class NeuroState:
    def __init__(self, values: dict[str, float]):
        self.state = {f: 0.0 for f in NEURO_FIELDS}
        self.state.update(values)

    def check(self, conditions: list) -> bool:
        """
        conditions は list[list[tuple]]。外側=OR、内側=AND。
        any( all(each AND group) for OR groups )
        """
        ops = {">": float.__gt__, "<": float.__lt__, ">=": float.__ge__,
               "<=": float.__le__, "==": float.__eq__}
        return any(
            all(ops[op](self.state.get(field, 0.0), val)
                for field, op, val in group)
            for group in conditions
        )

    def apply(self, effects: dict):
        for field, delta in effects.items():
            self.state[field] = max(0.0, min(1.0,
                                   self.state.get(field, 0.0) + delta))

    def tick(self):
        for field, rate in DECAY_RATES.items():
            self.state[field] = max(0.0, self.state[field] - rate)

    def drift_to(self, target: dict, strength: float = 0.05):
        """アトラクターに向けてゆっくり引き寄せる"""
        for f in NEURO_FIELDS:
            if f in target:
                diff = target[f] - self.state[f]
                self.state[f] = max(0.0, min(1.0, self.state[f] + diff * strength))

    def nearest_attractor(self) -> str:
        """現在の状態に最も近いアトラクター名を返す"""
        best, best_dist = "explore", float("inf")
        for name, target in ATTRACTORS.items():
            dist = sum((self.state.get(f, 0.0) - target.get(f, 0.0)) ** 2
                       for f in NEURO_FIELDS) ** 0.5
            if dist < best_dist:
                best, best_dist = name, dist
        return best

    @property
    def gaba(self) -> float:
        return self.state["gaba"]

    def display(self) -> str:
        lines = []
        for f in NEURO_FIELDS:
            val = self.state.get(f, 0.0)
            bar = "█" * int(val * 20) + "░" * (20 - int(val * 20))
            lines.append(f"  {NEURO_LABELS[f]}: [{bar}] {val:.2f}")
        attractor = self.nearest_attractor()
        lines.append(f"  [最近アトラクター: {attractor}]")
        return "\n".join(lines)


class CPOSMemory:
    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.working: dict[str, str] = {}
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
        self.working[key] = value

    def recall(self, key: str) -> str | None:
        if key in self.working:
            return self.working[key]
        if key in self.storage:
            self.working[key] = self.storage[key]
            return self.working[key]
        return None

    def swap(self):
        if not self.working:
            return 0
        self.storage.update(self.working)
        self._save_storage()
        count = len(self.working)
        self.working.clear()
        return count

    def forget_oldest(self):
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
        self.whens = decl.whens
        self.memory = CPOSMemory(decl.name)
        self.std = StdLib(self)
        self.inbox: list[tuple[str, str]] = []  # [(from_agent, message), ...]
        # カスタムアトラクターを組み込みアトラクターに上書き
        self.attractors = dict(ATTRACTORS)
        for a in decl.attractors:
            self.attractors[a.name] = a.values
        self.active_attractor: str | None = None

    def call(self, fn_name: str, args: list = None) -> str:
        if fn_name not in self.fns:
            self.mood.apply(ERROR_EFFECTS)
            return f"[エラー] {fn_name} は未定義"
        fn = self.fns[fn_name]
        if fn.requires and not self.mood.check(fn.requires):
            # 最初のORグループの最初の条件を代表として表示
            first_cond = fn.requires[0][0]
            cur = self.mood.state.get(first_cond[0], 0.0)
            cond_str = " or ".join(
                " and ".join(f"{f}{o}{v}" for f, o, v in grp)
                for grp in fn.requires
            )
            self.mood.apply(ERROR_EFFECTS)
            return (f"[実行拒否] {fn_name}: "
                    f"{first_cond[0]}={cur:.2f} — 条件 [{cond_str}] を満たさない")

        # ローカルスコープを作って本体実行
        env = {}
        if fn.params and args:
            for p, a in zip(fn.params, args):
                pname = p.name if hasattr(p, "name") else str(p)
                env[pname] = a
        ret_val = self._exec_body(fn.body, env)

        if fn_name in AFTER_EFFECTS:
            self.mood.apply(AFTER_EFFECTS[fn_name])
        self.mood.tick()
        self.memory.forget_oldest()
        if self.mood.gaba >= CPOS_SWAP_THRESHOLD:
            count = self.memory.swap()
            if count:
                return f"[実行OK] {fn_name} [CPOS] 作業記憶{count}件を長期記憶にスワップ"

        ret_str = f" → {ret_val}" if ret_val is not None else ""
        return f"[実行OK] {fn_name}({', '.join(str(a) for a in (args or []))}){ret_str}"

    def _exec_body(self, body: list, env: dict) -> object:
        """関数本体の文リストを実行し、return値を返す"""
        try:
            for stmt in body:
                self._exec_stmt(stmt, env)
        except _ReturnSignal as sig:
            return sig.value
        return None

    def _exec_stmt(self, stmt, env: dict):
        if isinstance(stmt, LetStmt):
            env[stmt.name] = self._eval_expr(stmt.value, env)
            return None

        if isinstance(stmt, ReturnStmt):
            val = self._eval_expr(stmt.value, env) if stmt.value is not None else None
            raise _ReturnSignal(val)

        if isinstance(stmt, ExprStmt):
            val = self._eval_expr(stmt.expr, env)
            return val

        if isinstance(stmt, BranchStmt):
            if self.mood.check(stmt.condition):
                return self._exec_body(stmt.then_body, env)
            else:
                return self._exec_body(stmt.else_body, env)

        if isinstance(stmt, LoopStmt):
            for _ in range(MAX_LOOP_ITER):
                if stmt.condition is not None:
                    cond_met = self.mood.check(stmt.condition)
                    if stmt.until and cond_met:
                        break
                    if not stmt.until and not cond_met:
                        break
                try:
                    self._exec_body(stmt.body, env)
                except _BreakSignal:
                    break
            return None

        if isinstance(stmt, BreakStmt):
            raise _BreakSignal()

        return None

    def _eval_expr(self, expr, env: dict) -> object:
        if isinstance(expr, Literal):
            return expr.value

        if isinstance(expr, VarRef):
            if expr.name in env:
                return env[expr.name]
            if expr.name in self.mood.state:
                return self.mood.state[expr.name]
            return None

        if isinstance(expr, BinOp):
            l = self._eval_expr(expr.left, env)
            r = self._eval_expr(expr.right, env)
            ops = {"+": lambda a, b: a + b,
                   "-": lambda a, b: a - b,
                   "*": lambda a, b: a * b,
                   "/": lambda a, b: a / b if b != 0 else 0,
                   ">": lambda a, b: a > b,
                   "<": lambda a, b: a < b,
                   ">=": lambda a, b: a >= b,
                   "<=": lambda a, b: a <= b,
                   "==": lambda a, b: a == b}
            return ops.get(expr.op, lambda a, b: None)(l, r)

        if isinstance(expr, FnCallExpr):
            args = [self._eval_expr(a, env) for a in expr.args]
            result = self.call(expr.name, args)
            return result

        if isinstance(expr, MsgSend):
            msg = self._eval_expr(expr.message, env)
            # メッセージをinboxへ; 実際の配信はEvaluator.tick()で行う
            self.inbox.append((self.name, str(msg)))
            return f"→{expr.receiver}: {msg}"

        return None

    def receive_message(self, from_agent: str, message: str):
        """メッセージ受信 → ox/s に影響"""
        self.inbox.append((from_agent, message))
        self.mood.apply({"ox": +0.05, "s": +0.03})
        print(f"  [{self.name}] ← {from_agent}: {message!r} (ox+0.05, s+0.03)")

    def check_whens(self):
        """tick後にwhenブロックを評価"""
        for wb in self.whens:
            if self.mood.check(wb.condition):
                cond_str = " or ".join(
                    " and ".join(f"{f}{o}{v}" for f, o, v in grp)
                    for grp in wb.condition
                )
                print(f"  [when] {self.name}: {cond_str} → トリガー")
                self._exec_body(wb.body, {})

    def display(self) -> str:
        return f"Agent: {self.name}\n{self.mood.display()}\n{self.memory.display()}"


class Evaluator:
    def __init__(self, program: Program):
        self.agents: dict[str, Agent] = {}
        for decl in program.agents:
            self.agents[decl.name] = Agent(decl)
        self.attractions: dict[tuple[str, str], float] = {}
        self._pending_messages: list[tuple[str, str, str]] = []
        # .nema ファイル内の ~~ 宣言を自動セットアップ
        for attr in getattr(program, "attractions", []):
            key = tuple(sorted([attr.agent_a, attr.agent_b]))
            self.attractions[key] = min(1.0, attr.strength)
            print(f"[引力] {attr.agent_a} ~~ {attr.agent_b} "
                  f"(strength={attr.strength:.2f})")

    def attract(self, a: str, b: str, strength: float = 0.3):
        key = tuple(sorted([a, b]))
        self.attractions[key] = min(1.0, strength)
        print(f"[引力] {a} ~~ {b} (strength={strength:.2f})")

    def apply_attractions(self):
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

    def tick(self):
        """全エージェントのtick + when チェック + アトラクタードリフト"""
        for agent in self.agents.values():
            agent.mood.tick()
            # アクティブなアトラクターへのドリフト
            if agent.active_attractor and agent.active_attractor in agent.attractors:
                target = agent.attractors[agent.active_attractor]
                agent.mood.drift_to(target, strength=0.05)
            agent.check_whens()
        self.apply_attractions()
        self._deliver_messages()

    def send_message(self, from_name: str, to_name: str, message: str):
        self._pending_messages.append((from_name, to_name, message))

    def _deliver_messages(self):
        for from_n, to_n, msg in self._pending_messages:
            if to_n in self.agents:
                self.agents[to_n].receive_message(from_n, msg)
        self._pending_messages.clear()

    def set_attractor(self, agent_name: str, attractor: str):
        if agent_name not in self.agents:
            print(f"[エラー] agent {agent_name} が見つからない")
            return
        agent = self.agents[agent_name]
        if attractor not in agent.attractors and attractor != "none":
            print(f"[エラー] アトラクター '{attractor}' が未定義")
            print(f"  利用可能: {', '.join(agent.attractors.keys())}, none")
            return
        agent.active_attractor = None if attractor == "none" else attractor
        print(f"[アトラクター] {agent_name} → {attractor}")

    def inject_neurostate(self, agent_name: str, values: dict):
        """外部データ（しーちゃんなど）をNeuroStateに注入"""
        if agent_name not in self.agents:
            print(f"[エラー] agent {agent_name} が見つからない")
            return
        agent = self.agents[agent_name]
        for f, v in values.items():
            if f in NEURO_FIELDS:
                agent.mood.state[f] = max(0.0, min(1.0, float(v)))
        print(f"[注入] {agent_name} NeuroState を更新")
        print(agent.mood.display())

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
        if "connect" in fn_name:
            for (a, b) in list(self.attractions.keys()):
                if agent_name in (a, b):
                    self.attractions[(a, b)] = min(1.0, self.attractions[(a, b)] + 0.01)
        print(result)
