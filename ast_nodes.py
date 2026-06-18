from dataclasses import dataclass, field


# ===== 型システム =====

@dataclass
class TypeI64:
    pass

@dataclass
class TypeI32:
    pass

@dataclass
class TypeF64:
    pass

@dataclass
class TypeBool:
    pass

@dataclass
class TypeVoid:
    pass

@dataclass
class TypePtr:
    inner: object

@dataclass
class TypeNeuroState:
    pass

@dataclass
class TypeChannel:
    elem: object  # NemaType — channel<i64> の i64 部分

@dataclass
class TypeList:
    elem: object  # NemaType — list<i64> の i64 部分

@dataclass
class TypeResult:
    ok: object  # NemaType — Result<T> の T

NemaType = TypeI64 | TypeI32 | TypeF64 | TypeBool | TypeVoid | TypePtr | TypeNeuroState | TypeChannel | TypeList | TypeResult


def type_str(t) -> str:
    if isinstance(t, TypeI64): return "i64"
    if isinstance(t, TypeI32): return "i32"
    if isinstance(t, TypeF64): return "f64"
    if isinstance(t, TypeBool): return "bool"
    if isinstance(t, TypeVoid): return "void"
    if isinstance(t, TypePtr): return f"ptr<{type_str(t.inner)}>"
    if isinstance(t, TypeNeuroState): return "NeuroState"
    if isinstance(t, TypeChannel): return f"channel<{type_str(t.elem)}>"
    if isinstance(t, TypeList): return f"list<{type_str(t.elem)}>"
    if isinstance(t, TypeResult): return f"Result<{type_str(t.ok)}>"
    return "unknown"


# ===== 式ノード =====

@dataclass
class Literal:
    value: object  # int | float | str | bool

@dataclass
class VarRef:
    name: str

@dataclass
class BinOp:
    left: object
    op: str   # + - * / > < >= <= == !=
    right: object

@dataclass
class FnCallExpr:
    name: str
    args: list

@dataclass
class MsgSend:
    receiver: str   # エージェント名
    message: object # Expr

@dataclass
class QueryExpr:
    field: str      # NeuroState フィールド名 ("dp"/"s"/... or "mood" or "owned")
    agent: str      # 対象エージェント名
    var: str | None = None  # "owned <var>" のとき変数名

@dataclass
class ChannelCreateExpr:
    elem_type: object  # NemaType

@dataclass
class RangeExpr:
    start: object  # Expr
    end: object    # Expr

@dataclass
class ListExpr:
    elems: list    # list[Expr]

@dataclass
class PropagateExpr:
    """expr? — Result<T>をアンラップ。Errなら即return Err(...)"""
    expr: object

@dataclass
class MethodCallExpr:
    receiver: object  # Expr (VarRef or AgentConstructorExpr)
    method: str
    args: list

@dataclass
class AgentConstructorExpr:
    agent_name: str   # "MathHelper()" → agent への参照を返す

@dataclass
class OkExpr:
    value: object  # Expr

@dataclass
class ErrExpr:
    message: object  # Expr (string literal or VarRef)


# ===== 文ノード =====

@dataclass
class LetStmt:
    name: str
    value: object

@dataclass
class OwnStmt:
    name: str
    value: object   # Expr — 所有権付きで変数を作る

@dataclass
class ReleaseStmt:
    name: str       # 所有権を解放する変数名

@dataclass
class RecvStmt:
    name: str              # 受け取る変数名
    from_agent: str | None # None = mailbox から受信（blocking）

@dataclass
class SpawnStmt:
    fn_name: str   # バックグラウンドで実行する関数名
    args: list     # 引数リスト

@dataclass
class ReturnStmt:
    value: object

@dataclass
class ExprStmt:
    expr: object

@dataclass
class BranchStmt:
    condition: object  # list (mood条件) or Expr (boolean式)
    then_body: list
    else_body: list

@dataclass
class LoopStmt:
    body: list
    condition: list | None
    until: bool = False

@dataclass
class BreakStmt:
    pass

@dataclass
class SendChStmt:
    channel: str   # チャンネル変数名
    value: object  # Expr

@dataclass
class RecvChStmt:
    channel: str   # チャンネル変数名
    var: str       # 受け取る値のバインド名
    body: list     # 受信後に実行するボディ

@dataclass
class CloseChStmt:
    channel: str   # チャンネル変数名

@dataclass
class EmitStmt:
    event: str      # イベント名（文字列）
    value: object   # Expr — ペイロード（None 可）

@dataclass
class OnEventBlock:
    event: str      # 受信するイベント名
    body: list      # 実行する文のリスト

@dataclass
class MatchArm:
    op: str | None      # ">", "<", ">=", "<=", "==" or None（default _）
    threshold: object   # Expr — 比較値、None は default arm
    body: list          # 実行する文のリスト
    bind: str | None = None   # ok(v)/err(msg) のバインド変数名

@dataclass
class MatchStmt:
    subject: object     # Expr — match する値（VarRef "dp" など）
    arms: list          # list[MatchArm]

@dataclass
class ForStmt:
    var: str           # ループ変数名
    iter: object       # RangeExpr | ListExpr | VarRef
    body: list         # 実行する文のリスト

@dataclass
class SetMoodStmt:
    field: str   # NeuroState フィールド名 ("dp"/"s"/...)
    op: str      # "=" / "+=" / "-="
    value: object  # Expr


# ===== エージェント宣言ノード =====

@dataclass
class NeuroStateNode:
    values: dict[str, float]

@dataclass
class MoodDecl:
    state: NeuroStateNode

@dataclass
class Param:
    name: str
    type: NemaType | None = None

@dataclass
class FnDecl:
    name: str
    params: list
    ret_type: NemaType | None
    requires: list | None
    body: list                  # list of statement nodes
    on_error_body: list = None  # @on_error { ... } があれば実行される
    ensures: list = None        # @ensures(dp > 0.5) — 事後条件
    cpos_gate: bool = False     # @cpos_gate — NeuroState警告またはパターン異常で発動

@dataclass
class WhenBlock:
    condition: list  # [(field, op, val), ...]
    body: list

@dataclass
class AttractorDecl:
    name: str          # "explore" | "rest" | "social" | "crisis" | "flow"
    values: dict[str, float]

@dataclass
class TrustDecl:
    scores: dict[str, float]   # { AgentName: 0.8, ... }

@dataclass
class CapabilityDecl:
    caps: set   # {"alloc", "free", "emit", ...}

@dataclass
class ContractDecl:
    invariants: list  # list[list[list[tuple]]] — 各不変条件（parse_condition形式）

@dataclass
class AgentDecl:
    name: str
    mood: MoodDecl | None
    fns: list
    whens: list        # list[WhenBlock]
    attractors: list   # list[AttractorDecl]
    on_events: list = None       # list[OnEventBlock]
    trust: TrustDecl | None = None
    capability: CapabilityDecl | None = None
    contract: "ContractDecl | None" = None

@dataclass
class AttractionStmt:
    agent_a: str
    agent_b: str
    strength: float = 0.3

@dataclass
class TrustStmt:
    agent_a: str   # a が b を信頼する（一方向）
    agent_b: str
    score: float = 0.5

@dataclass
class Program:
    agents: list
    attractions: list   # list[AttractionStmt]
    trusts: list = None  # list[TrustStmt]
