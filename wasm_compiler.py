"""
Nema → WAT (WASM Text Format) コンパイラ

対応機能:
  - NeuroState → f64 グローバル変数（エージェント名プレフィックス付き）
  - @requires ゲート → early-exit パターン（ゲート失敗時 -1.0 を return）
  - let / return / 基本演算 (+, -, *, /, >, <, >=, <=, ==)
  - VarRef（NeuroState フィールド・ローカル変数）
  - branch（if/else）
  - 関数呼び出し（同一エージェント内）
  - エクスポート: "AgentName_fnName"

非対応（インタープリタのみ）:
  - channel / spawn / emit / trust / query / import / match
  - @on_error / @ensures / contract
"""

from ast_nodes import (
    Program, AgentDecl, FnDecl, Param,
    LetStmt, ReturnStmt, ExprStmt, BranchStmt, ForStmt, SetMoodStmt,
    Literal, VarRef, BinOp, FnCallExpr,
    RangeExpr, ListExpr,
    TypeI64, TypeI32, TypeF64, TypeBool, TypeVoid, TypePtr,
)

NEURO_FIELDS = ["dp", "s", "ac", "ox", "gaba", "e"]

# WASMコンパイル非対応のインタープリタ専用組み込み関数
_INTERP_ONLY = {
    "log", "print", "alloc", "write", "read", "free", "size",
    "introspect", "summarize", "empathize", "rand_mood",
}

F64_OPS = {
    "+":  "f64.add",
    "-":  "f64.sub",
    "*":  "f64.mul",
    "/":  "f64.div",
    ">":  "f64.gt",
    "<":  "f64.lt",
    ">=": "f64.ge",
    "<=": "f64.le",
    "==": "f64.eq",
}


def _wat_type(t) -> str:
    if isinstance(t, TypeI64):  return "i64"
    if isinstance(t, TypeI32):  return "i32"
    if isinstance(t, TypeF64):  return "f64"
    if isinstance(t, TypeBool): return "i32"
    return "f64"


def _zero(wat_type: str) -> str:
    if wat_type == "i64": return "(i64.const 0)"
    if wat_type == "i32": return "(i32.const 0)"
    return "(f64.const 0.0)"


class WasmCompiler:
    def __init__(self):
        self._depth = 1
        self._pfx = ""           # エージェント名プレフィックス（小文字）
        self._locals: dict[str, str] = {}

    def _i(self, s: str) -> str:
        return "  " * self._depth + s

    # ──────────────────────────────────────────
    # エントリポイント
    # ──────────────────────────────────────────

    def compile(self, program: Program) -> str:
        lines = ["(module"]
        for agent in program.agents:
            lines += self._agent(agent)
        lines.append(")")
        return "\n".join(lines)

    # ──────────────────────────────────────────
    # エージェント → グローバル変数 + 関数群
    # ──────────────────────────────────────────

    def _agent(self, a: AgentDecl) -> list[str]:
        pfx = a.name.lower()
        self._pfx = pfx
        mood = a.mood.state.values if a.mood else {}

        out = [self._i(f";; ── Agent: {a.name} ──")]
        for f in NEURO_FIELDS:
            out.append(self._i(
                f"(global ${pfx}_{f} (mut f64) (f64.const {mood.get(f, 0.5):.4f}))"
            ))
        out.append("")

        for fn in a.fns:
            out += self._fn(fn, a.name, pfx)
            out.append("")

        # NeuroState グローバルのエクスポート（JS から読み書き可能）
        for f in NEURO_FIELDS:
            out.append(self._i(
                f'(export "{a.name}_{f}" (global ${pfx}_{f}))'
            ))
        out.append("")

        return out

    # ──────────────────────────────────────────
    # 関数
    # ──────────────────────────────────────────

    def _fn(self, fn: FnDecl, agent_name: str, pfx: str) -> list[str]:
        self._locals = {}

        # パラメータ
        params = []
        for p in (fn.params or []):
            wt = _wat_type(p.type) if p.type else "f64"
            params.append(f"(param ${p.name} {wt})")
            self._locals[p.name] = wt

        # 戻り値
        ret = _wat_type(fn.ret_type) if fn.ret_type else "f64"
        result = f"(result {ret})"

        header = f"(func ${pfx}_{fn.name}"
        if params:    header += " " + " ".join(params)
        header += f" {result}"

        out = [self._i(header)]
        self._depth += 1

        # ローカル変数宣言（本体を先読みして収集）
        for name, wt in self._collect_locals(fn.body).items():
            if name not in self._locals:
                out.append(self._i(f"(local ${name} {wt})"))
                self._locals[name] = wt

        # @requires → early-exit ゲート
        if fn.requires:
            out += self._gate(fn.requires, ret)

        # 本体
        out += self._body(fn.body, ret)

        # 末尾にデフォルト return 値
        if not self._has_return(fn.body):
            out.append(self._i(_zero(ret)))

        self._depth -= 1
        out.append(self._i(")"))
        out.append(self._i(f'(export "{agent_name}_{fn.name}" (func ${pfx}_{fn.name}))'))
        return out

    # ──────────────────────────────────────────
    # @requires → early-exit ゲート
    # ゲート失敗なら -1 を return して終了
    # ──────────────────────────────────────────

    def _gate(self, requires: list, ret: str) -> list[str]:
        """@requires → early-exit ゲート（OR グループ完全対応）
        requires = [[AND条件...], [AND条件...], ...]  外側=OR / 内側=AND
        いずれかの AND グループが全て真なら通過。全グループ失敗で -1 return。
        """
        out = []

        for gi, group in enumerate(requires):
            # AND グループ内の各条件
            for i, (field, op, val) in enumerate(group):
                if field in NEURO_FIELDS:
                    out.append(self._i(f"(global.get ${self._pfx}_{field})"))
                elif field in self._locals:
                    out.append(self._i(f"(local.get ${field})"))
                else:
                    out.append(self._i(f"(f64.const 0.0)  ;; unknown: {field}"))
                out.append(self._i(f"(f64.const {float(val)})"))
                out.append(self._i(f"({F64_OPS.get(op, 'f64.gt')})"))
                if i > 0:
                    out.append(self._i("(i32.and)"))  # AND 結合
            # 複数グループは OR で結合
            if gi > 0:
                out.append(self._i("(i32.or)"))

        # 全グループの OR 結果が偽なら early return -1
        fail = "(i64.const -1)" if ret == "i64" else "(f64.const -1.0)"
        out.append(self._i("(i32.eqz)  ;; 失敗 = 1 に変換"))
        out.append(self._i("(if"))
        self._depth += 1
        out.append(self._i("(then"))
        self._depth += 1
        out.append(self._i(fail))
        out.append(self._i("(return)"))
        self._depth -= 1
        out.append(self._i(")"))  # close then
        self._depth -= 1
        out.append(self._i(")"))  # close if
        out.append(self._i(";; ゲート通過 → 本体実行"))
        return out

    # ──────────────────────────────────────────
    # 文
    # ──────────────────────────────────────────

    def _body(self, stmts: list, ret: str = "f64") -> list[str]:
        out = []
        for s in stmts:
            out += self._stmt(s, ret)
        return out

    def _stmt(self, s, ret: str) -> list[str]:
        out = []

        if isinstance(s, LetStmt):
            wt = self._type_of(s.value)
            out += self._expr(s.value, wt)
            out.append(self._i(f"(local.set ${s.name})"))

        elif isinstance(s, ReturnStmt):
            if s.value is not None:
                out += self._expr(s.value, ret)
            else:
                out.append(self._i(_zero(ret)))
            out.append(self._i("(return)"))

        elif isinstance(s, ExprStmt):
            wt = self._type_of(s.expr)
            out += self._expr(s.expr, wt)
            if wt:
                out.append(self._i("(drop)"))

        elif isinstance(s, BranchStmt):
            out += self._branch(s, ret)

        elif isinstance(s, ForStmt):
            out += self._for_stmt(s, ret)

        elif isinstance(s, SetMoodStmt):
            out += self._set_mood(s)

        return out

    def _branch(self, s: BranchStmt, ret: str) -> list[str]:
        out = []
        group = s.condition[0]

        for i, (field, op, val) in enumerate(group):
            if field in NEURO_FIELDS:
                out.append(self._i(f"(global.get ${self._pfx}_{field})"))
            else:
                out.append(self._i(f"(f64.const 0.0)"))
            out.append(self._i(f"(f64.const {float(val)})"))
            out.append(self._i(f"({F64_OPS.get(op, 'f64.gt')})"))
            if i > 0:
                out.append(self._i("(i32.and)"))

        has_else = bool(s.else_body)
        result_clause = f"(result {ret})" if has_else else ""
        out.append(self._i(f"(if {result_clause}".strip()))

        self._depth += 1
        out.append(self._i("(then"))
        self._depth += 1
        out += self._body(s.then_body, ret)
        if has_else and not self._has_return(s.then_body):
            out.append(self._i(_zero(ret)))
        self._depth -= 1
        out.append(self._i(")"))  # close then

        if has_else:
            out.append(self._i("(else"))
            self._depth += 1
            out += self._body(s.else_body, ret)
            if not self._has_return(s.else_body):
                out.append(self._i(_zero(ret)))
            self._depth -= 1
            out.append(self._i(")"))  # close else

        self._depth -= 1
        out.append(self._i(")"))  # close if
        return out

    # ──────────────────────────────────────────
    # 式
    # ──────────────────────────────────────────

    def _expr(self, e, hint: str = "f64") -> list[str]:
        out = []

        if isinstance(e, Literal):
            if isinstance(e.value, bool):
                out.append(self._i(f"(i32.const {1 if e.value else 0})"))
            elif isinstance(e.value, float):
                out.append(self._i(f"(f64.const {e.value})"))
            elif isinstance(e.value, int):
                if hint == "f64":
                    out.append(self._i(f"(f64.const {float(e.value)})"))
                else:
                    out.append(self._i(f"(i64.const {e.value})"))
            else:
                out.append(self._i(f"(i64.const 0)  ;; unsupported: {e.value!r}"))

        elif isinstance(e, VarRef):
            if e.name in NEURO_FIELDS:
                out.append(self._i(f"(global.get ${self._pfx}_{e.name})"))
            elif e.name in self._locals:
                out.append(self._i(f"(local.get ${e.name})"))
            else:
                out.append(self._i(f"(f64.const 0.0)  ;; unknown: {e.name}"))

        elif isinstance(e, BinOp):
            wt = self._type_of(e)
            out += self._expr(e.left, wt)
            out += self._expr(e.right, wt)
            op_wat = F64_OPS.get(e.op, "f64.add")
            out.append(self._i(f"({op_wat})"))

        elif isinstance(e, FnCallExpr):
            if e.name in _INTERP_ONLY:
                # インタープリタ専用関数: 引数を評価して捨て、0.0 を戻す
                for arg in e.args:
                    out += self._expr(arg, self._type_of(arg))
                    out.append(self._i("(drop)"))
                out.append(self._i(f"(f64.const 0.0)  ;; interp-only: {e.name}"))
            else:
                for arg in e.args:
                    out += self._expr(arg, self._type_of(arg))
                out.append(self._i(f"(call ${self._pfx}_{e.name})"))

        return out

    # ──────────────────────────────────────────
    # 型推論（簡略）
    # ──────────────────────────────────────────

    def _type_of(self, e) -> str:
        if isinstance(e, Literal):
            if isinstance(e.value, float): return "f64"
            if isinstance(e.value, bool):  return "i32"
            return "i64"
        if isinstance(e, VarRef):
            if e.name in NEURO_FIELDS:     return "f64"
            return self._locals.get(e.name, "f64")
        if isinstance(e, BinOp):
            lt = self._type_of(e.left)
            rt = self._type_of(e.right)
            return "f64" if "f64" in (lt, rt) else "i64"
        return "f64"

    # ──────────────────────────────────────────
    # ユーティリティ
    # ──────────────────────────────────────────

    def _set_mood(self, s: SetMoodStmt) -> list[str]:
        """set field op val → WASM global.set（clamp 0.0–1.0）"""
        out = []
        g = f"${self._pfx}_{s.field}"
        if s.op == "=":
            out += self._expr(s.value, "f64")
        elif s.op == "+=":
            out.append(self._i(f"(global.get {g})"))
            out += self._expr(s.value, "f64")
            out.append(self._i("(f64.add)"))
        elif s.op == "-=":
            out.append(self._i(f"(global.get {g})"))
            out += self._expr(s.value, "f64")
            out.append(self._i("(f64.sub)"))
        # clamp to [0.0, 1.0]
        out.append(self._i("(f64.const 0.0)"))
        out.append(self._i("(f64.max)"))
        out.append(self._i("(f64.const 1.0)"))
        out.append(self._i("(f64.min)"))
        out.append(self._i(f"(global.set {g})"))
        return out

    def _collect_locals(self, body: list) -> dict[str, str]:
        res = {}
        for s in body:
            if isinstance(s, LetStmt):
                res[s.name] = self._type_of(s.value)
            elif isinstance(s, BranchStmt):
                res.update(self._collect_locals(s.then_body))
                res.update(self._collect_locals(s.else_body))
            elif isinstance(s, ForStmt):
                wt = "i64" if isinstance(s.iter, RangeExpr) else (
                    self._type_of(s.iter.elems[0]) if isinstance(s.iter, ListExpr) and s.iter.elems else "f64"
                )
                res[s.var] = wt
                res.update(self._collect_locals(s.body))
        return res

    def _for_stmt(self, s: ForStmt, ret: str) -> list[str]:
        out = []
        label = s.var  # ループラベルに変数名を流用

        if isinstance(s.iter, RangeExpr):
            # --- 範囲ループ: block/loop/br_if パターン ---
            wt = "i64"
            # loop var の初期値をセット
            out += self._expr(s.iter.start, wt)
            out.append(self._i(f"(local.set ${label})"))

            out.append(self._i(f"(block $break_{label}"))
            self._depth += 1
            out.append(self._i(f"(loop $loop_{label}"))
            self._depth += 1

            # 条件チェック: var >= end なら break へ
            out.append(self._i(f"(local.get ${label})"))
            out += self._expr(s.iter.end, wt)
            out.append(self._i("(i64.ge_s)"))
            out.append(self._i(f"(br_if $break_{label})"))

            # ボディ
            out += self._body(s.body, ret)

            # var += 1
            out.append(self._i(f"(local.get ${label})"))
            out.append(self._i("(i64.const 1)"))
            out.append(self._i("(i64.add)"))
            out.append(self._i(f"(local.set ${label})"))

            # ループ先頭へ
            out.append(self._i(f"(br $loop_{label})"))

            self._depth -= 1
            out.append(self._i(")"))  # close loop
            self._depth -= 1
            out.append(self._i(")"))  # close block

        elif isinstance(s.iter, ListExpr):
            # --- リスト: 静的アンロール ---
            wt = self._type_of(s.iter.elems[0]) if s.iter.elems else "f64"
            for elem in s.iter.elems:
                out += self._expr(elem, wt)
                out.append(self._i(f"(local.set ${label})"))
                out += self._body(s.body, ret)

        return out

    def _has_return(self, body: list) -> bool:
        return any(isinstance(s, ReturnStmt) for s in body)


def compile_to_wat(program: Program) -> str:
    return WasmCompiler().compile(program)
