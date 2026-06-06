from ast_nodes import Program, AgentDecl, FnDecl
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

        return self.errors

    def _check_agent(self, agent: AgentDecl, agent_names: set[str]):
        # mood の値チェック
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

        # 関数チェック
        fn_names = {fn.name for fn in agent.fns}
        for fn in agent.fns:
            self._check_fn(agent.name, fn, agent_names, fn_names)

    def _check_fn(self, agent_name: str, fn: FnDecl,
                  agent_names: set[str], fn_names: set[str]):
        # @requires の条件チェック
        if fn.requires:
            for field, op, val in fn.requires:
                if field not in NEURO_FIELDS:
                    self._err(agent_name, fn.name,
                              f"@requires で未知のフィールド: '{field}'")
                if val > 1.0:
                    self._warn(agent_name, fn.name,
                               f"@requires({field}{op}{val}): "
                               f"NeuroStateは最大1.0なので常に失敗する")
                if val < 0.0:
                    self._warn(agent_name, fn.name,
                               f"@requires({field}{op}{val}): "
                               f"NeuroStateは最小0.0なので常に成功する")

        # 関数名の重複チェック
        seen = set()
        if fn.name in seen:
            self._err(agent_name, fn.name, f"関数名が重複している: '{fn.name}'")
        seen.add(fn.name)


def typecheck(program: Program) -> list[TypeError]:
    return TypeChecker(program).check()


def report(errors: list[TypeError]) -> bool:
    """エラーを表示してエラーがあればTrueを返す"""
    if not errors:
        print("✅ 型チェック: 問題なし")
        return False

    err_count = sum(1 for e in errors if e.level == "error")
    warn_count = sum(1 for e in errors if e.level == "warn")

    print(f"型チェック結果: ❌ {err_count}件のエラー / ⚠️  {warn_count}件の警告")
    for e in errors:
        print(e)

    return err_count > 0
