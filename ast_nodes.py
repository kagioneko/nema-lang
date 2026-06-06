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

NemaType = TypeI64 | TypeI32 | TypeF64 | TypeBool | TypeVoid | TypePtr | TypeNeuroState


def type_str(t) -> str:
    if isinstance(t, TypeI64): return "i64"
    if isinstance(t, TypeI32): return "i32"
    if isinstance(t, TypeF64): return "f64"
    if isinstance(t, TypeBool): return "bool"
    if isinstance(t, TypeVoid): return "void"
    if isinstance(t, TypePtr): return f"ptr<{type_str(t.inner)}>"
    if isinstance(t, TypeNeuroState): return "NeuroState"
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
    name: str       # 受け取る変数名
    from_agent: str # 送り元エージェント名

@dataclass
class ReturnStmt:
    value: object

@dataclass
class ExprStmt:
    expr: object

@dataclass
class BranchStmt:
    condition: list
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
    body: list  # list of statement nodes

@dataclass
class WhenBlock:
    condition: list  # [(field, op, val), ...]
    body: list

@dataclass
class AttractorDecl:
    name: str          # "explore" | "rest" | "social" | "crisis" | "flow"
    values: dict[str, float]

@dataclass
class AgentDecl:
    name: str
    mood: MoodDecl | None
    fns: list
    whens: list        # list[WhenBlock]
    attractors: list   # list[AttractorDecl]

@dataclass
class AttractionStmt:
    agent_a: str
    agent_b: str
    strength: float = 0.3

@dataclass
class Program:
    agents: list
    attractions: list   # list[AttractionStmt]
