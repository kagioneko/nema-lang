from ast_nodes import Program, AgentDecl, FnDecl, WhenBlock, AttractorDecl
from dataclasses import dataclass

NEURO_FIELDS = {"dp", "s", "ac", "ox", "gaba", "e"}


@dataclass
class TypeError:
    level: str  # "error" or "warn"
    agent: str
    fn: str | None
    message: str

    def __str__(self):
        loc = f"{self.agent}" + (f".{self.fn}" if self.fn else "")
        icon = "❌" if self.level == "error" else "⚠️ "
        return f"  {icon} [{loc}] {self.message}"


class TypeChecker:
    def __init__(self, program: Program):
        self.program = program
        self.errors: list[TypeError] = []

    def _err(self, agent: str, fn: str | None, msg: str):
        self.errors.append(TypeError("error", agent, fn, msg))

    def _warn(self, agent: str, fn: str | None, msg: str):
        self.errors.append(TypeError("warn", agent, fn, msg))

    def check(self) -> list[TypeError]:
        agent_names = {a.name for a in self.program.agents}
        for agent in self.program.agents:
            self._check_agent(agent, agent_names)
        self._check_attractions()
        return self.errors

    def _check_agent(self, agent: AgentDecl, agent_names: set[str]):
        if agent.mood:
            for field, val in agent.mood.state.values.items():
                if field not in NEURO_FIELDS:
                    self._err(agent.name, None,
                              f"未知のNeuroStateフィールド: '{field}' "
                              f"(有効: {', '.join(sorted(NEURO_FIELDS))})")
                if not (0.0 <= val <= 1.0):
                    self._err(agent.name, None,
                              f"{field}={val} は範囲外 (0.0〜1.0)")
        else:
            self._warn(agent.name, None, "mood が未定義 (感情ゲートが全て失敗する)")

        fn_names = {fn.name for fn in agent.fns}
        for fn in agent.fns:
            self._check_fn(agent.name, fn, agent_names, fn_names)

        for wb in agent.whens:
            self._check_condition(agent.name, "when", wb.condition)

        for at in agent.attractors:
            self._check_attractor(agent.name, at)

    def _check_fn(self, agent_name: str, fn: FnDecl,
                  agent_names: set[str], fn_names: set[str]):
        if fn.requires:
            self._check_condition(agent_name, fn.name, fn.requires)

    def _check_condition(self, agent_name: str, ctx: str, requires: list):
        """conditions は list[list[tuple]] 形式"""
        for group in requires:
            for field, op, val in group:
                if field not in NEURO_FIELDS:
                    self._err(agent_name, ctx,
                              f"未知のフィールド: '{field}' "
                              f"(有効: {', '.join(sorted(NEURO_FIELDS))})")
                if val > 1.0:
                    self._warn(agent_name, ctx,
                               f"@requires({field}{op}{val}): "
                               f"NeuroStateは最大1.0なので常に失敗する")
                if val < 0.0:
                    self._warn(agent_name, ctx,
                               f"@requires({field}{op}{val}): "
                               f"NeuroStateは最小0.0なので常に成功する")

    def _check_attractor(self, agent_name: str, at: AttractorDecl):
        for field, val in at.values.items():
            if field not in NEURO_FIELDS:
                self._err(agent_name, f"attractor:{at.name}",
                          f"未知のフィールド: '{field}'")
            if not (0.0 <= val <= 1.0):
                self._err(agent_name, f"attractor:{at.name}",
                          f"{field}={val} は範囲外 (0.0〜1.0)")

    def _check_attractions(self):
        agent_names = {a.name for a in self.program.agents}
        for attr in getattr(self.program, "attractions", []):
            if attr.agent_a not in agent_names:
                self._err(attr.agent_a, None,
                          f"attraction に未定義のエージェント: '{attr.agent_a}'")
            if attr.agent_b not in agent_names:
                self._err(attr.agent_b, None,
                          f"attraction に未定義のエージェント: '{attr.agent_b}'")
            if not (0.0 <= attr.strength <= 1.0):
                self._warn(attr.agent_a, None,
                           f"attraction strength={attr.strength} は 0〜1 を推奨")


def typecheck(program: Program) -> list[TypeError]:
    return TypeChecker(program).check()


def report(errors: list[TypeError]) -> bool:
    if not errors:
        print("✅ 型チェック: 問題なし")
        return False
    err_count = sum(1 for e in errors if e.level == "error")
    warn_count = sum(1 for e in errors if e.level == "warn")
    print(f"型チェック結果: ❌ {err_count}件のエラー / ⚠️  {warn_count}件の警告")
    for e in errors:
        print(e)
    return err_count > 0
