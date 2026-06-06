from dataclasses import dataclass, field


@dataclass
class NeuroStateNode:
    values: dict[str, float]  # dp, s, ac, ox, gaba, e


@dataclass
class MoodDecl:
    state: NeuroStateNode


@dataclass
class FnDecl:
    name: str
    params: list[str]
    requires: list[tuple] | None  # [(field, op, value), ...]
    body: list


@dataclass
class AgentDecl:
    name: str
    mood: MoodDecl | None
    fns: list[FnDecl]


@dataclass
class Program:
    agents: list[AgentDecl]
