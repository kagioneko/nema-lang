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
    inner: object  # 内包する型

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


# ===== AST ノード =====

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
    params: list[Param]
    ret_type: NemaType | None
    requires: list[tuple] | None
    body: list


@dataclass
class AgentDecl:
    name: str
    mood: MoodDecl | None
    fns: list[FnDecl]


@dataclass
class Program:
    agents: list[AgentDecl]
