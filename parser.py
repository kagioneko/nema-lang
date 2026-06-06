from lexer import Token, TT, Lexer
from ast_nodes import *


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = [t for t in tokens if t.type != TT.NEWLINE]
        self.pos = 0

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        t = self.tokens[self.pos]
        self.pos += 1
        return t

    def expect(self, tt: TT) -> Token:
        t = self.advance()
        if t.type != tt:
            raise ParseError(f"line {t.line}: expected {tt.name}, got {t.type.name} ({t.value!r})")
        return t

    def skip(self, tt: TT) -> bool:
        if self.peek().type == tt:
            self.advance()
            return True
        return False

    def parse(self) -> Program:
        agents = []
        while self.peek().type != TT.EOF:
            agents.append(self.parse_agent())
        return Program(agents=agents)

    def parse_agent(self) -> AgentDecl:
        self.expect(TT.AGENT)
        name = self.expect(TT.IDENT).value
        self.expect(TT.LBRACE)

        mood = None
        fns = []

        while self.peek().type != TT.RBRACE:
            if self.peek().type == TT.MOOD:
                mood = self.parse_mood()
            elif self.peek().type in (TT.FN, TT.REQUIRES, TT.AFTER, TT.ON_ERROR, TT.WHEN):
                fns.append(self.parse_fn())
            else:
                self.advance()  # 未知トークンはスキップ

        self.expect(TT.RBRACE)
        return AgentDecl(name=name, mood=mood, fns=fns)

    def parse_mood(self) -> MoodDecl:
        self.expect(TT.MOOD)
        self.expect(TT.COLON)
        self.expect(TT.NEUROSTATE)
        self.expect(TT.ASSIGN)
        state = self.parse_neurostate()
        return MoodDecl(state=state)

    def parse_neurostate(self) -> NeuroStateNode:
        self.expect(TT.LBRACE)
        values = {}
        while self.peek().type != TT.RBRACE:
            key = self.expect(TT.IDENT).value
            self.expect(TT.COLON)
            val = float(self.advance().value)
            values[key] = val
            self.skip(TT.COMMA)
        self.expect(TT.RBRACE)
        return NeuroStateNode(values=values)

    def parse_fn(self) -> FnDecl:
        requires = None

        # @requires デコレータ
        if self.peek().type == TT.REQUIRES:
            self.advance()
            self.expect(TT.LPAREN)
            requires = self.parse_condition()
            self.expect(TT.RPAREN)

        # デコレータ系は今はスキップ
        while self.peek().type in (TT.AFTER, TT.ON_ERROR, TT.WHEN):
            self.advance()
            if self.peek().type == TT.LPAREN:
                self.expect(TT.LPAREN)
                while self.peek().type != TT.RPAREN:
                    self.advance()
                self.expect(TT.RPAREN)

        self.expect(TT.FN)
        name = self.expect(TT.IDENT).value
        self.expect(TT.LPAREN)
        params = []
        while self.peek().type != TT.RPAREN:
            pname = self.advance().value
            ptype = None
            if self.peek().type == TT.COLON:
                self.advance()
                ptype = self.parse_type()
            params.append(Param(name=pname, type=ptype))
            self.skip(TT.COMMA)
        self.expect(TT.RPAREN)

        # 戻り値型
        ret_type = None
        if self.peek().type == TT.ARROW:
            self.advance()
            ret_type = self.parse_type()
        elif self.peek().type == TT.IDENT and self.peek().value in ("String", "Answer", "Float", "Int"):
            self.advance()

        self.expect(TT.LBRACE)
        body = []
        while self.peek().type != TT.RBRACE:
            body.append(self.advance().value)
        self.expect(TT.RBRACE)

        return FnDecl(name=name, params=params, ret_type=ret_type,
                      requires=requires, body=body)

    def parse_type(self):
        t = self.peek()
        if t.type == TT.TYPE_I64:
            self.advance(); return TypeI64()
        if t.type == TT.TYPE_I32:
            self.advance(); return TypeI32()
        if t.type == TT.TYPE_F64:
            self.advance(); return TypeF64()
        if t.type == TT.TYPE_BOOL:
            self.advance(); return TypeBool()
        if t.type == TT.TYPE_VOID:
            self.advance(); return TypeVoid()
        if t.type == TT.TYPE_PTR:
            self.advance()
            self.expect(TT.LT)
            inner = self.parse_type()
            self.expect(TT.GT)
            return TypePtr(inner=inner)
        if t.type == TT.NEUROSTATE:
            self.advance(); return TypeNeuroState()
        # 未知型はIDENTとしてスキップ
        self.advance()
        return None

    def parse_condition(self) -> list[tuple]:
        # "dp > 0.6" などをパース
        conditions = []
        field = self.advance().value
        op = self.advance().value
        val = float(self.advance().value)
        conditions.append((field, op, val))
        return conditions
