import json
import os
import queue
import threading
from ast_nodes import (Program, AgentDecl, NeuroStateNode,
                       LetStmt, OwnStmt, ReleaseStmt, RecvStmt, SpawnStmt,
                       SendChStmt, RecvChStmt, CloseChStmt,
                       EmitStmt, OnEventBlock, MatchStmt, MatchArm,
                       ReturnStmt, ExprStmt, BranchStmt,
                       LoopStmt, BreakStmt, WhenBlock, AttractorDecl, ForStmt,
                       Literal, VarRef, BinOp, FnCallExpr, MsgSend, QueryExpr,
                       ChannelCreateExpr, RangeExpr, ListExpr, OkExpr, ErrExpr,
                       SetMoodStmt, MethodCallExpr, AgentConstructorExpr, PropagateExpr)

class _PropagateError(Exception):
    """? 演算子によるエラー早期リターン用シグナル"""
    def __init__(self, err_val):
        self.err_val = err_val

TRUST_DEFAULT  = 0.5   # 未定義エージェントに対するデフォルト信頼度
TRUST_GATE     = 0.3   # これを下回ると query/send がブロックされる
PRIVILEGED_OPS = {"alloc", "free"}  # capability 宣言必須の特権操作
from stdlib import StdLib

RECV_TIMEOUT = 30.0   # recv のブロッキングタイムアウト（秒）
MAX_THREADS  = 16     # 同時実行スレッド数の上限

# インタープリタ用シミュレーテッドヒープ
_INTERP_HEAP: dict[str, list] = {}
_HEAP_CTR = [0]

def _heap_alloc(size: int) -> str:
    _HEAP_CTR[0] += 1
    addr = f"0x{_HEAP_CTR[0]:04x}"
    _INTERP_HEAP[addr] = [0] * max(1, int(size))
    return addr

def _heap_write(addr, val) -> None:
    if addr in _INTERP_HEAP:
        _INTERP_HEAP[addr][0] = val

def _heap_read(addr):
    return _INTERP_HEAP.get(str(addr), [0])[0]

def _heap_free(addr) -> None:
    _INTERP_HEAP.pop(str(addr), None)

INTERP_BUILTINS = {
    "alloc": lambda *a: _heap_alloc(a[0]),
    "write": lambda *a: _heap_write(a[0], a[1]),
    "read":  lambda *a: _heap_read(a[0]),
    "free":  lambda *a: _heap_free(a[0]),
    "log":   lambda *a: print(f"  [log] {' '.join(str(x) for x in a)}"),
    "print": lambda *a: print(f"  [print] {' '.join(str(x) for x in a)}"),
}

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


_CHANNEL_CLOSED = object()  # close sentinel


class NemaChannel:
    def __init__(self, elem_type=None):
        self._q = queue.Queue()
        self.elem_type = elem_type
        self._closed = False

    def put(self, value):
        if self._closed:
            raise RuntimeError("closed チャンネルへの send はできません")
        self._q.put(value)

    def get(self, timeout=RECV_TIMEOUT):
        return self._q.get(timeout=timeout)

    def close(self):
        if not self._closed:
            self._closed = True
            self._q.put(_CHANNEL_CLOSED)

    def __repr__(self):
        from ast_nodes import type_str
        et = type_str(self.elem_type) if self.elem_type else "?"
        return f"channel<{et}>"


class _ReturnSignal(Exception):
    def __init__(self, value):
        self.value = value

class _BreakSignal(Exception):
    pass


class NemaOk:
    """Result型の成功値"""
    def __init__(self, value):
        self.value = value
    def __repr__(self):
        return f"ok({self.value!r})"

class NemaErr:
    """Result型のエラー値"""
    def __init__(self, message):
        self.message = message
    def __repr__(self):
        return f"err({self.message!r})"


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

    def apply(self, effects: dict, lock=None):
        def _do():
            for field, delta in effects.items():
                self.state[field] = max(0.0, min(1.0,
                                       self.state.get(field, 0.0) + delta))
        if lock:
            with lock: _do()
        else:
            _do()

    def tick(self, lock=None):
        def _do():
            for field, rate in DECAY_RATES.items():
                self.state[field] = max(0.0, self.state[field] - rate)
        if lock:
            with lock: _do()
        else:
            _do()

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
    def __init__(self, decl: AgentDecl, evaluator=None):
        self.name = decl.name
        self._ev = evaluator  # Evaluator への back-reference（query で使用）
        self.mood = NeuroState(decl.mood.state.values) if decl.mood else NeuroState({})
        self.fns = {fn.name: fn for fn in decl.fns}
        self.whens = decl.whens
        self.memory = CPOSMemory(decl.name)
        self.std = StdLib(self)
        self.inbox: list[tuple[str, str]] = []
        self.mailbox: queue.Queue = queue.Queue()
        self.mood_lock: threading.Lock = threading.Lock()
        self.owned: dict[str, object] = {}
        # trust スコア: agent名 → 0.0〜1.0
        self.trust: dict[str, float] = dict(decl.trust.scores) if decl.trust else {}
        # on_event ハンドラ: イベント名 → 文リスト
        self.on_events: dict[str, list] = {
            oe.event: oe.body for oe in (decl.on_events or [])
        }
        # capability: 許可された操作セット（None なら全許可）
        self.caps: set | None = set(decl.capability.caps) if decl.capability else None
        self._transfer_box: dict[str, object] = {}
        self._threads: list[threading.Thread] = []  # このエージェントのスレッド
        self._stop_event: threading.Event = threading.Event()
        # contract 不変条件リスト
        self.invariants: list = list(decl.contract.invariants) if decl.contract else []
        # カスタムアトラクターを組み込みアトラクターに上書き
        self.attractors = dict(ATTRACTORS)
        for a in decl.attractors:
            self.attractors[a.name] = a.values
        self.active_attractor: str | None = None

    def call_value(self, fn_name: str, args: list = None):
        """実際の返り値を返す内部呼び出し（式の中で使用）"""
        if fn_name not in self.fns:
            self.mood.apply(ERROR_EFFECTS)
            return f"[エラー] {fn_name} は未定義"
        fn = self.fns[fn_name]
        if fn.requires and not self.mood.check(fn.requires):
            first_cond = fn.requires[0][0]
            cur = self.mood.state.get(first_cond[0], 0.0)
            cond_str = " or ".join(
                " and ".join(f"{f}{o}{v}" for f, o, v in grp)
                for grp in fn.requires
            )
            self.mood.apply(ERROR_EFFECTS, self.mood_lock)
            print(f"[実行拒否] {fn_name}: "
                  f"{first_cond[0]}={cur:.2f} — 条件 [{cond_str}] を満たさない")
            if fn.on_error_body:
                print(f"  [@on_error] {fn_name}: fallback 実行")
                self._exec_body(fn.on_error_body, {})
                if self._ev and self._ev._pending_events:
                    self._ev._deliver_events()
            return f"[on_error] {fn_name}: fallback 完了" if fn.on_error_body else \
                   f"[実行拒否] {fn_name}: gate NG"

        # ローカルスコープを作って本体実行
        env = {}
        if fn.params and args:
            for p, a in zip(fn.params, args):
                pname = p.name if hasattr(p, "name") else str(p)
                env[pname] = a
        try:
            ret_val = self._exec_body(fn.body, env)
        except _PropagateError as e:
            # ? 演算子によるエラー早期リターン
            return e.err_val

        if fn_name in AFTER_EFFECTS:
            self.mood.apply(AFTER_EFFECTS[fn_name], self.mood_lock)
        self.mood.tick(self.mood_lock)
        self.memory.forget_oldest()
        if self.mood.gaba >= CPOS_SWAP_THRESHOLD:
            count = self.memory.swap()
            if count:
                return f"[実行OK] {fn_name} [CPOS] 作業記憶{count}件を長期記憶にスワップ"

        # @ensures 事後条件チェック
        if fn.ensures and not self.mood.check(fn.ensures):
            cond_str = " or ".join(
                " and ".join(f"{f}{o}{v}" for f, o, v in grp)
                for grp in fn.ensures
            )
            self.mood.apply(ERROR_EFFECTS, self.mood_lock)
            print(f"  [@ensures FAIL] {fn_name}: 事後条件 [{cond_str}] を満たさない")
            if fn.on_error_body:
                print(f"  [@on_error] {fn_name}: fallback 実行")
                self._exec_body(fn.on_error_body, {})
                if self._ev and self._ev._pending_events:
                    self._ev._deliver_events()
            return f"[ensures NG] {fn_name}: 事後条件違反"

        # emit されたイベントを即座に配信
        if self._ev and self._ev._pending_events:
            self._ev._deliver_events()

        self._check_invariants(f"call:{fn_name}")

        ret_str = f" → {ret_val}" if ret_val is not None else ""
        print(f"[実行OK] {fn_name}({', '.join(str(a) for a in (args or []))}){ret_str}")
        return ret_val

    def call(self, fn_name: str, args: list = None) -> str:
        """REPL向け: 実行して文字列サマリを返す（互換維持）"""
        result = self.call_value(fn_name, args)
        if isinstance(result, str) and result.startswith("["):
            return result  # エラー文字列はそのまま
        return f"[完了] {fn_name}"

    def _check_invariants(self, context: str = ""):
        """contract 不変条件を全てチェックし、違反があればログ + ペナルティ"""
        if not self.invariants:
            return
        ops = {">": float.__gt__, "<": float.__lt__, ">=": float.__ge__,
               "<=": float.__le__, "==": float.__eq__}
        for cond in self.invariants:
            cond_str = " or ".join(
                " and ".join(f"{f}{o}{v}" for f, o, v in grp)
                for grp in cond
            )
            ok = any(
                all(ops[op](self.mood.state.get(field, 0.0), val)
                    for field, op, val in group)
                for group in cond
            )
            if not ok:
                field0 = cond[0][0][0]
                cur_val = self.mood.state.get(field0, 0.0)
                self.mood.apply({"s": -0.1, "gaba": +0.05}, self.mood_lock)
                print(f"  [contract FAIL] {self.name} [{context}]: "
                      f"不変条件違反 [{cond_str}] "
                      f"(現在値: {cur_val:.3f})")

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

        if isinstance(stmt, OwnStmt):
            val = self._eval_expr(stmt.value, env)
            self.owned[stmt.name] = val
            env[stmt.name] = val
            self.mood.apply({"gaba": +0.05}, self.mood_lock)
            print(f"  [own] {self.name}: {stmt.name} = {val!r} を所有")
            return None

        if isinstance(stmt, ReleaseStmt):
            if stmt.name not in self.owned:
                self.mood.apply({"s": -0.3, "gaba": +0.1}, self.mood_lock)
                print(f"  [release ERROR] {self.name}: {stmt.name} を所有していない（二重解放？）")
                return None
            val = self.owned.pop(stmt.name)
            env.pop(stmt.name, None)
            self.mood.apply({"s": +0.05}, self.mood_lock)
            print(f"  [release] {self.name}: {stmt.name} を解放")
            return None

        if isinstance(stmt, RecvStmt):
            if stmt.from_agent is None:
                # mailbox からブロッキング受信（並行モード）
                try:
                    from_ag, msg = self.mailbox.get(timeout=RECV_TIMEOUT)
                    self.owned[stmt.name] = msg
                    env[stmt.name] = msg
                    self.mood.apply({"ox": +0.05}, self.mood_lock)
                    print(f"  [recv] {self.name} ← mailbox ({from_ag}): {stmt.name} = {msg!r}")
                except queue.Empty:
                    self.mood.apply({"s": -0.1}, self.mood_lock)
                    print(f"  [recv TIMEOUT] {self.name}: mailbox recv タイムアウト ({RECV_TIMEOUT}s)")
                return None
            key = f"{stmt.from_agent}→{self.name}:{stmt.name}"
            if key in self._transfer_box:
                # コード経由の transfer（non-direct）
                val = self._transfer_box.pop(key)
                self.owned[stmt.name] = val
                env[stmt.name] = val
                self.mood.apply({"ox": +0.05}, self.mood_lock)
                print(f"  [recv] {self.name} ← {stmt.from_agent}: {stmt.name} = {val!r}")
            elif stmt.name in self.owned:
                # REPL の direct transfer で既に owned にある
                env[stmt.name] = self.owned[stmt.name]
                self.mood.apply({"ox": +0.03}, self.mood_lock)
                print(f"  [recv] {self.name}: {stmt.name} = {self.owned[stmt.name]!r} (転送済み)")
            else:
                self.mood.apply({"s": -0.1}, self.mood_lock)
                print(f"  [recv ERROR] {self.name}: {stmt.from_agent} から {stmt.name} が届いていない")
            return None

        if isinstance(stmt, EmitStmt):
            if self.caps is not None and "emit" not in self.caps:
                self.mood.apply({"s": -0.1}, self.mood_lock)
                print(f"  [capability DENIED] {self.name}: emit 権限がない")
                return None
            value = self._eval_expr(stmt.value, env) if stmt.value is not None else None
            if self._ev:
                self._ev._pending_events.append((self.name, stmt.event, value))
            self.mood.apply({"e": +0.03}, self.mood_lock)
            print(f"  [emit] {self.name} → '{stmt.event}' = {value!r}")
            return None

        if isinstance(stmt, SpawnStmt):
            if stmt.fn_name not in self.fns:
                self.mood.apply(ERROR_EFFECTS, self.mood_lock)
                print(f"  [spawn ERROR] {self.name}: {stmt.fn_name} は未定義")
                return None
            active = sum(1 for t in self._threads if t.is_alive())
            if active >= MAX_THREADS:
                print(f"  [spawn ERROR] {self.name}: スレッド上限 ({MAX_THREADS}) 到達")
                return None
            args = [self._eval_expr(a, env) for a in stmt.args]
            t = threading.Thread(
                target=self.call,
                args=(stmt.fn_name, args),
                daemon=True,
                name=f"{self.name}.{stmt.fn_name}",
            )
            self._threads.append(t)
            t.start()
            print(f"  [spawn] {self.name}: {stmt.fn_name} をスレッドで起動")
            return None

        if isinstance(stmt, ReturnStmt):
            val = self._eval_expr(stmt.value, env) if stmt.value is not None else None
            raise _ReturnSignal(val)

        if isinstance(stmt, ExprStmt):
            val = self._eval_expr(stmt.expr, env)
            return val

        if isinstance(stmt, BranchStmt):
            if isinstance(stmt.condition, list):
                # 旧形式: mood条件リスト [[('dp','>',0.6),...],...]
                cond_result = self.mood.check(stmt.condition)
            else:
                # 新形式: Expr (ローカル変数・算術式・比較式)
                cond_result = bool(self._eval_expr(stmt.condition, env))
            if cond_result:
                result = self._exec_body(stmt.then_body, env)
            else:
                result = self._exec_body(stmt.else_body, env)
            if result is not None:
                raise _ReturnSignal(result)
            return None

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

        if isinstance(stmt, MatchStmt):
            subj = self._eval_expr(stmt.subject, env)
            ops = {">": float.__gt__, "<": float.__lt__,
                   ">=": float.__ge__, "<=": float.__le__, "==": float.__eq__}
            for arm in stmt.arms:
                if arm.op is None:  # default _
                    return self._exec_body(arm.body, env)
                # Result アーム: ok(v) / err(msg)
                if arm.op == "ok" and isinstance(subj, NemaOk):
                    child = dict(env)
                    child[arm.bind] = subj.value
                    result = self._exec_body(arm.body, child)
                    if result is not None:
                        raise _ReturnSignal(result)
                    return None
                if arm.op == "err" and isinstance(subj, NemaErr):
                    child = dict(env)
                    child[arm.bind] = subj.message
                    result = self._exec_body(arm.body, child)
                    if result is not None:
                        raise _ReturnSignal(result)
                    return None
                if arm.op in ("ok", "err"):
                    continue
                thresh = self._eval_expr(arm.threshold, env)
                try:
                    matched = ops[arm.op](float(subj), float(thresh))
                except (TypeError, ValueError):
                    matched = False
                if matched:
                    result = self._exec_body(arm.body, env)
                    if result is not None:
                        raise _ReturnSignal(result)
                    return None
            return None

        if isinstance(stmt, ForStmt):
            iterable = self._eval_expr(stmt.iter, env)
            if isinstance(iterable, (range, list)):
                for val in iterable:
                    env[stmt.var] = val
                    try:
                        result = self._exec_body(stmt.body, env)
                        if result is not None:
                            raise _ReturnSignal(result)
                    except _BreakSignal:
                        break
            return None

        if isinstance(stmt, SetMoodStmt):
            field = stmt.field
            if field not in NEURO_FIELDS:
                print(f"  [set ERROR] {self.name}: '{field}' はNeuroStateフィールドではない")
                return None
            val = float(self._eval_expr(stmt.value, env) or 0.0)
            with self.mood_lock:
                if stmt.op == "=":
                    self.mood.state[field] = max(0.0, min(1.0, val))
                elif stmt.op == "+=":
                    self.mood.state[field] = max(0.0, min(1.0, self.mood.state[field] + val))
                elif stmt.op == "-=":
                    self.mood.state[field] = max(0.0, min(1.0, self.mood.state[field] - val))
            print(f"  [set] {self.name}.{field} {stmt.op} {val:.3f} → {self.mood.state[field]:.3f}")
            return None

        if isinstance(stmt, SendChStmt):
            ch = env.get(stmt.channel) or self.owned.get(stmt.channel)
            if not isinstance(ch, NemaChannel):
                print(f"  [send ERROR] {self.name}: '{stmt.channel}' はチャンネルではない")
                return None
            val = self._eval_expr(stmt.value, env)
            try:
                ch.put(val)
                self.mood.apply({"ac": +0.02}, self.mood_lock)
                print(f"  [send] {self.name} → {stmt.channel}: {val!r}")
            except RuntimeError as e:
                print(f"  [send ERROR] {self.name}: {e}")
            return None

        if isinstance(stmt, RecvChStmt):
            ch = env.get(stmt.channel) or self.owned.get(stmt.channel)
            if not isinstance(ch, NemaChannel):
                print(f"  [recv ERROR] {self.name}: '{stmt.channel}' はチャンネルではない")
                return None
            try:
                val = ch.get(timeout=RECV_TIMEOUT)
            except queue.Empty:
                self.mood.apply({"s": -0.05}, self.mood_lock)
                print(f"  [recv TIMEOUT] {self.name}: {stmt.channel} タイムアウト")
                raise _BreakSignal()
            if val is _CHANNEL_CLOSED:
                raise _BreakSignal()  # close されたら loop を抜ける
            env[stmt.var] = val
            self.mood.apply({"ox": +0.03}, self.mood_lock)
            print(f"  [recv] {self.name} ← {stmt.channel}: {stmt.var} = {val!r}")
            return self._exec_body(stmt.body, env)

        if isinstance(stmt, CloseChStmt):
            ch = env.get(stmt.channel) or self.owned.get(stmt.channel)
            if not isinstance(ch, NemaChannel):
                print(f"  [close ERROR] {self.name}: '{stmt.channel}' はチャンネルではない")
                return None
            ch.close()
            print(f"  [close] {self.name}: {stmt.channel} をクローズ")
            return None

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

        if isinstance(expr, PropagateExpr):
            val = self._eval_expr(expr.expr, env)
            if isinstance(val, NemaOk):
                return val.value
            if isinstance(val, NemaErr):
                raise _PropagateError(val)
            return val  # Result でない値はそのまま通す

        if isinstance(expr, AgentConstructorExpr):
            # MathHelper() → エージェント参照を返す
            if self._ev and expr.agent_name in self._ev.agents:
                return ("__agent_ref__", expr.agent_name)
            # 未定義の場合は自分のメソッドを試みる
            return self.call_value(expr.agent_name, [])

        if isinstance(expr, MethodCallExpr):
            receiver = self._eval_expr(expr.receiver, env)
            args = [self._eval_expr(a, env) for a in expr.args]
            # h.method(args) — receiver がエージェント参照
            if isinstance(receiver, tuple) and len(receiver) == 2 and receiver[0] == "__agent_ref__":
                agent_name = receiver[1]
                if self._ev and agent_name in self._ev.agents:
                    return self._ev.agents[agent_name].call_value(expr.method, args)
                return f"[エラー] agent {agent_name} が見つからない"
            return f"[エラー] {receiver} はエージェント参照ではない"

        if isinstance(expr, FnCallExpr):
            args = [self._eval_expr(a, env) for a in expr.args]
            # エージェント名 → エージェント参照を返す（コンストラクタ呼び出し）
            if self._ev and expr.name in self._ev.agents and not args:
                return ("__agent_ref__", expr.name)
            # インタープリタ組み込み関数（alloc/write/read/free）
            if expr.name in INTERP_BUILTINS:
                # capability チェック
                # 特権操作: capability 宣言がなければ即ブロック
                # 非特権操作: capability 宣言があるが含まれない場合のみブロック
                is_privileged = expr.name in PRIVILEGED_OPS
                denied = (
                    (is_privileged and (self.caps is None or expr.name not in self.caps))
                    or (not is_privileged and self.caps is not None and expr.name not in self.caps)
                )
                if denied:
                    self.mood.apply({"s": -0.2, "gaba": +0.1}, self.mood_lock)
                    print(f"  [capability DENIED] {self.name}: "
                          f"{expr.name!r} の権限がない")
                    return None
                return INTERP_BUILTINS[expr.name](*args)
            return self.call_value(expr.name, args)

        if isinstance(expr, MsgSend):
            msg = self._eval_expr(expr.message, env)
            self.inbox.append((self.name, str(msg)))
            return f"→{expr.receiver}: {msg}"

        if isinstance(expr, QueryExpr):
            return self._eval_query(expr)

        if isinstance(expr, ChannelCreateExpr):
            ch = NemaChannel(elem_type=expr.elem_type)
            print(f"  [channel] {self.name}: {ch} を作成")
            return ch

        if isinstance(expr, RangeExpr):
            start = int(self._eval_expr(expr.start, env))
            end   = int(self._eval_expr(expr.end, env))
            return range(start, end)

        if isinstance(expr, ListExpr):
            return [self._eval_expr(e, env) for e in expr.elems]

        if isinstance(expr, OkExpr):
            return NemaOk(self._eval_expr(expr.value, env))

        if isinstance(expr, ErrExpr):
            return NemaErr(self._eval_expr(expr.message, env))

        return None

    def _eval_query(self, expr: QueryExpr) -> object:
        """他エージェントの状態を読み取る（所有権移動なし）"""
        if self._ev is None:
            print(f"  [query ERROR] {self.name}: evaluator 未設定")
            return None
        target = self._ev.agents.get(expr.agent)
        if target is None:
            self.mood.apply({"s": -0.05}, self.mood_lock)
            print(f"  [query ERROR] {self.name}: agent {expr.agent!r} が見つからない")
            return None
        # trust ゲート: target が trust を宣言していれば未知エージェントはブロック
        if target.trust:
            trust_score = target.trust.get(self.name, 0.0)
        else:
            trust_score = TRUST_DEFAULT
        if trust_score < TRUST_GATE:
            self.mood.apply({"s": -0.05, "ox": -0.03}, self.mood_lock)
            print(f"  [query BLOCKED] {expr.agent} は {self.name} を信頼していない"
                  f" (trust={trust_score:.2f} < {TRUST_GATE})")
            return None

        if expr.field == "mood":
            # 全NeuroStateをdictで返す
            val = dict(target.mood.state)
            self.mood.apply({"ac": +0.03}, self.mood_lock)
            print(f"  [query] {self.name} ← {expr.agent}.mood = {val}")
            return val

        if expr.field == "owned":
            var = expr.var
            val = target.owned.get(var)
            self.mood.apply({"ac": +0.03}, self.mood_lock)
            print(f"  [query] {self.name} ← {expr.agent}.owned[{var!r}] = {val!r}")
            return val

        # NeuroState フィールド
        if expr.field in NEURO_FIELDS:
            val = target.mood.state.get(expr.field, 0.0)
            self.mood.apply({"ac": +0.02}, self.mood_lock)
            print(f"  [query] {self.name} ← {expr.agent}.{expr.field} = {val:.3f}")
            return val

        print(f"  [query ERROR] {self.name}: 不明なフィールド {expr.field!r}")
        return None

    def receive_message(self, from_agent: str, message: str):
        """メッセージ受信 → ox/s に影響 + mailbox に push"""
        self.inbox.append((from_agent, message))
        self.mailbox.put((from_agent, message))
        self.mood.apply({"ox": +0.05, "s": +0.03}, self.mood_lock)
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
            a = Agent(decl)
            a._ev = self
            self.agents[decl.name] = a
        self.attractions: dict[tuple[str, str], float] = {}
        self._pending_messages: list[tuple[str, str, str]] = []
        self._pending_events: list[tuple[str, str, object]] = []
        # .nema ファイル内の ~~ 宣言を自動セットアップ
        for attr in getattr(program, "attractions", []):
            key = tuple(sorted([attr.agent_a, attr.agent_b]))
            self.attractions[key] = min(1.0, attr.strength)
            print(f"[引力] {attr.agent_a} ~~ {attr.agent_b} "
                  f"(strength={attr.strength:.2f})")
        # トップレベル trust 宣言
        for ts in getattr(program, "trusts", []) or []:
            if ts.agent_a in self.agents:
                self.agents[ts.agent_a].trust[ts.agent_b] = min(1.0, ts.score)
                print(f"[信頼] {ts.agent_a} trust {ts.agent_b} "
                      f"(score={ts.score:.2f})")

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
            agent._check_invariants("tick")
        self.apply_attractions()
        self._deliver_messages()
        self._deliver_events()

    def send_message(self, from_name: str, to_name: str, message: str):
        self._pending_messages.append((from_name, to_name, message))

    def _deliver_messages(self):
        for from_n, to_n, msg in self._pending_messages:
            if to_n not in self.agents:
                continue
            target = self.agents[to_n]
            # trust チェック
            if target.trust:
                score = target.trust.get(from_n, 0.0)
            else:
                score = TRUST_DEFAULT
            if score < TRUST_GATE:
                print(f"  [send BLOCKED] {to_n} は {from_n} を信頼していない"
                      f" (trust={score:.2f})")
                continue
            target.receive_message(from_n, msg)
        self._pending_messages.clear()

    def _deliver_events(self):
        """pending_events を全エージェントの on_event ハンドラに配信"""
        for from_ag, event, value in self._pending_events:
            for name, agent in self.agents.items():
                if name == from_ag:
                    continue
                handler = agent.on_events.get(event)
                if handler:
                    env = {"event": event, "value": value, "from": from_ag}
                    agent.mood.apply({"ox": +0.03, "e": +0.02}, agent.mood_lock)
                    print(f"  [on {event!r}] {name} ← {from_ag}: value={value!r}")
                    agent._exec_body(handler, env)
        self._pending_events.clear()

    def emit(self, from_name: str, event: str, value=None):
        """REPL からイベントを発火"""
        if from_name not in self.agents:
            print(f"[エラー] agent {from_name} が見つからない")
            return
        self._pending_events.append((from_name, event, value))
        print(f"[emit] {from_name} → '{event}' = {value!r}")
        self._deliver_events()

    def set_trust(self, from_name: str, to_name: str, score: float):
        """REPL / コードから信頼スコアを設定"""
        if from_name not in self.agents:
            print(f"[エラー] agent {from_name} が見つからない")
            return
        self.agents[from_name].trust[to_name] = max(0.0, min(1.0, score))
        print(f"[信頼] {from_name} trust {to_name} (score={score:.2f})")

    def transfer_ownership(self, from_name: str, to_name: str,
                           var_name: str, direct: bool = True) -> bool:
        """
        from_agent の owned[var_name] を to_agent に移譲する。
        direct=True (REPL): 即座に to_agent.owned に入れる
        direct=False (コード): transfer_box に入れ RecvStmt で取り出す
        """
        if from_name not in self.agents or to_name not in self.agents:
            print(f"[transfer ERROR] エージェントが見つからない")
            return False
        from_agent = self.agents[from_name]
        to_agent   = self.agents[to_name]
        if var_name not in from_agent.owned:
            from_agent.mood.apply({"s": -0.2})
            print(f"[transfer ERROR] {from_name} は {var_name} を所有していない")
            return False
        val = from_agent.owned.pop(var_name)
        if direct:
            to_agent.owned[var_name] = val
        else:
            key = f"{from_name}→{to_name}:{var_name}"
            to_agent._transfer_box[key] = val
        from_agent.mood.apply({"ox": +0.03})
        to_agent.mood.apply({"ox": +0.05})
        print(f"[transfer] {from_name} → {to_name}: {var_name} = {val!r}")
        return True

    def show_owned(self, agent_name: str):
        if agent_name not in self.agents:
            print(f"[エラー] agent {agent_name} が見つからない")
            return
        agent = self.agents[agent_name]
        if not agent.owned:
            print(f"[owned] {agent_name}: なし")
        else:
            print(f"[owned] {agent_name}:")
            for k, v in agent.owned.items():
                print(f"  {k} = {v!r}")

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
        self.agents[agent_name].call_value(fn_name, args)
        if "connect" in fn_name:
            for (a, b) in list(self.attractions.keys()):
                if agent_name in (a, b):
                    self.attractions[(a, b)] = min(1.0, self.attractions[(a, b)] + 0.01)

    def spawn(self, agent_name: str, fn_name: str, args: list = None) -> bool:
        """エージェントの関数をバックグラウンドスレッドで実行"""
        if agent_name not in self.agents:
            print(f"[エラー] agent {agent_name} が見つからない")
            return False
        agent = self.agents[agent_name]
        active = sum(1 for t in agent._threads if t.is_alive())
        if active >= MAX_THREADS:
            print(f"[spawn ERROR] {agent_name}: スレッド上限 ({MAX_THREADS}) 到達")
            return False
        t = threading.Thread(
            target=agent.call_value,
            args=(fn_name, args or []),
            daemon=True,
            name=f"{agent_name}.{fn_name}",
        )
        agent._threads.append(t)
        t.start()
        print(f"[spawn] {agent_name}.{fn_name} をバックグラウンドで起動")
        return True

    def show_threads(self):
        """全エージェントのスレッド状態を表示"""
        total = 0
        for name, agent in self.agents.items():
            alive = [t for t in agent._threads if t.is_alive()]
            total += len(alive)
            if alive:
                print(f"  {name}: {len(alive)} スレッド稼働中")
                for t in alive:
                    print(f"    [{t.name}]")
        if total == 0:
            print("  スレッドなし（全完了）")
