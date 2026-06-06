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
        attractions = []
        while self.peek().type != TT.EOF:
            t = self.peek()
            if t.type == TT.AGENT:
                agents.append(self.parse_agent())
            elif (t.type == TT.IDENT
                  and self.pos + 1 < len(self.tokens)
                  and self.tokens[self.pos + 1].type == TT.ATTRACT):
                attractions.append(self.parse_top_attraction())
            else:
                self.advance()
        return Program(agents=agents, attractions=attractions)

    def parse_top_attraction(self):
        from ast_nodes import AttractionStmt
        a = self.advance().value    # IDENT
        self.advance()              # ~~
        b = self.advance().value    # IDENT
        strength = 0.3
        if self.peek().type in (TT.FLOAT, TT.INT):
            strength = float(self.advance().value)
        return AttractionStmt(agent_a=a, agent_b=b, strength=strength)

    def parse_agent(self) -> AgentDecl:
        self.expect(TT.AGENT)
        name = self.expect(TT.IDENT).value
        self.expect(TT.LBRACE)

        mood = None
        fns = []
        whens = []
        attractors = []

        while self.peek().type != TT.RBRACE:
            t = self.peek()
            if t.type == TT.MOOD:
                mood = self.parse_mood()
            elif t.type in (TT.FN, TT.REQUIRES, TT.AFTER, TT.ON_ERROR):
                fns.append(self.parse_fn())
            elif t.type == TT.WHEN:
                whens.append(self.parse_when_block())
            elif t.type == TT.IDENT and t.value == "attractor":
                attractors.append(self.parse_attractor())
            else:
                self.advance()

        self.expect(TT.RBRACE)
        return AgentDecl(name=name, mood=mood, fns=fns,
                         whens=whens, attractors=attractors)

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

        if self.peek().type == TT.REQUIRES:
            self.advance()
            self.expect(TT.LPAREN)
            requires = self.parse_condition()
            self.expect(TT.RPAREN)

        while self.peek().type in (TT.AFTER, TT.ON_ERROR):
            self.advance()
            if self.peek().type == TT.LPAREN:
                self.advance()
                while self.peek().type != TT.RPAREN:
                    self.advance()
                self.advance()

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

        ret_type = None
        if self.peek().type == TT.ARROW:
            self.advance()
            ret_type = self.parse_type()

        self.expect(TT.LBRACE)
        body = self.parse_body()
        self.expect(TT.RBRACE)

        return FnDecl(name=name, params=params, ret_type=ret_type,
                      requires=requires, body=body)

    def parse_when_block(self) -> WhenBlock:
        self.expect(TT.WHEN)
        self.expect(TT.LPAREN)
        cond = self.parse_condition()
        self.expect(TT.RPAREN)
        self.expect(TT.LBRACE)
        body = self.parse_body()
        self.expect(TT.RBRACE)
        return WhenBlock(condition=cond, body=body)

    def parse_attractor(self) -> AttractorDecl:
        self.advance()  # consume 'attractor' ident
        name = self.expect(TT.IDENT).value
        values = {}
        if self.peek().type == TT.LBRACE:
            self.expect(TT.LBRACE)
            while self.peek().type != TT.RBRACE:
                key = self.expect(TT.IDENT).value
                self.expect(TT.COLON)
                val = float(self.advance().value)
                values[key] = val
                self.skip(TT.COMMA)
            self.expect(TT.RBRACE)
        return AttractorDecl(name=name, values=values)

    # ===== 文パーサー =====

    def parse_body(self) -> list:
        stmts = []
        while self.peek().type not in (TT.RBRACE, TT.EOF):
            s = self.parse_stmt()
            if s is not None:
                stmts.append(s)
        return stmts

    def parse_stmt(self):
        t = self.peek()

        if t.type == TT.LET:
            return self.parse_let()

        if t.type == TT.RETURN:
            return self.parse_return()

        if t.type == TT.BRANCH:
            return self.parse_branch()

        if t.type == TT.LOOP:
            return self.parse_loop()

        if t.type == TT.WHILE:
            return self.parse_while()

        if t.type == TT.UNTIL:
            return self.parse_until()

        # IDENT ~> IDENT msg — メッセージ送信文
        if t.type == TT.IDENT and self.pos + 1 < len(self.tokens):
            next_t = self.tokens[self.pos + 1]
            if next_t.type == TT.ATTRACT:  # ~~
                return self.parse_msg_send()

        # IDENT( ... ) — 関数呼び出し文
        if t.type == TT.IDENT:
            expr = self.parse_expr()
            return ExprStmt(expr=expr)

        # その他は読み捨て
        self.advance()
        return None

    def parse_let(self) -> LetStmt:
        self.expect(TT.LET)
        name = self.expect(TT.IDENT).value
        self.expect(TT.ASSIGN)
        value = self.parse_expr()
        return LetStmt(name=name, value=value)

    def parse_return(self) -> ReturnStmt:
        self.expect(TT.RETURN)
        if self.peek().type in (TT.RBRACE, TT.EOF):
            return ReturnStmt(value=None)
        return ReturnStmt(value=self.parse_expr())

    def parse_branch(self) -> BranchStmt:
        self.expect(TT.BRANCH)
        cond = self.parse_condition()
        self.expect(TT.LBRACE)
        then_body = self.parse_body()
        self.expect(TT.RBRACE)
        else_body = []
        if self.peek().type == TT.IDENT and self.peek().value == "else":
            self.advance()
            self.expect(TT.LBRACE)
            else_body = self.parse_body()
            self.expect(TT.RBRACE)
        return BranchStmt(condition=cond, then_body=then_body, else_body=else_body)

    def parse_loop(self) -> LoopStmt:
        self.expect(TT.LOOP)
        self.expect(TT.LBRACE)
        body = self.parse_body()
        self.expect(TT.RBRACE)
        return LoopStmt(body=body, condition=None)

    def parse_while(self) -> LoopStmt:
        self.expect(TT.WHILE)
        cond = self.parse_condition()
        self.expect(TT.LBRACE)
        body = self.parse_body()
        self.expect(TT.RBRACE)
        return LoopStmt(body=body, condition=cond, until=False)

    def parse_until(self) -> LoopStmt:
        self.expect(TT.UNTIL)
        cond = self.parse_condition()
        self.expect(TT.LBRACE)
        body = self.parse_body()
        self.expect(TT.RBRACE)
        return LoopStmt(body=body, condition=cond, until=True)

    def parse_msg_send(self) -> ExprStmt:
        receiver = self.advance().value  # IDENT
        self.advance()                   # ~~ or ~>
        msg = self.parse_expr()
        return ExprStmt(expr=MsgSend(receiver=receiver, message=msg))

    # ===== 式パーサー =====

    def parse_expr(self) -> object:
        return self.parse_binop()

    def parse_binop(self) -> object:
        left = self.parse_primary()
        while self.peek().type in (TT.PLUS, TT.MINUS, TT.GT, TT.LT, TT.GE, TT.LE, TT.EQ):
            op = self.advance().value
            right = self.parse_primary()
            left = BinOp(left=left, op=op, right=right)
        return left

    def parse_primary(self) -> object:
        t = self.peek()

        if t.type in (TT.INT, TT.FLOAT):
            self.advance()
            val = int(t.value) if t.type == TT.INT else float(t.value)
            return Literal(value=val)

        if t.type == TT.STRING:
            self.advance()
            return Literal(value=t.value)

        if t.type == TT.IDENT:
            name = self.advance().value
            if self.peek().type == TT.LPAREN:
                self.advance()
                args = []
                while self.peek().type != TT.RPAREN:
                    args.append(self.parse_expr())
                    self.skip(TT.COMMA)
                self.expect(TT.RPAREN)
                return FnCallExpr(name=name, args=args)
            return VarRef(name=name)

        if t.type == TT.LPAREN:
            self.advance()
            expr = self.parse_expr()
            self.expect(TT.RPAREN)
            return expr

        self.advance()
        return Literal(value=None)

    # ===== 型・条件パーサー =====

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
        self.advance()
        return None

    def parse_condition(self) -> list:
        """
        list[list[tuple]] を返す。外側=OR、内側=AND。
        例: dp > 0.6 and s > 0.4 or ox > 0.8
            → [[('dp','>',0.6),('s','>',0.4)], [('ox','>',0.8)]]
        """
        groups: list[list[tuple]] = []
        current: list[tuple] = []

        field = self.advance().value
        op = self.advance().value
        val = float(self.advance().value)
        current.append((field, op, val))

        while self.peek().type in (TT.AND, TT.OR):
            combiner = self.advance()
            field = self.advance().value
            op = self.advance().value
            val = float(self.advance().value)
            if combiner.type == TT.OR:
                groups.append(current)
                current = [(field, op, val)]
            else:
                current.append((field, op, val))

        groups.append(current)
        return groups
