from lexer import Token, TT, Lexer
import os
from ast_nodes import (
    Program, AgentDecl, MoodDecl, NeuroStateNode, FnDecl, Param,
    WhenBlock, AttractorDecl, AttractionStmt, TrustDecl, CapabilityDecl, ContractDecl,
    TypeI64, TypeI32, TypeF64, TypeBool, TypeVoid, TypePtr, TypeNeuroState, TypeChannel,
    Literal, VarRef, BinOp, FnCallExpr, MsgSend, QueryExpr, ChannelCreateExpr,
    LetStmt, OwnStmt, ReleaseStmt, RecvStmt, SpawnStmt,
    SendChStmt, RecvChStmt, CloseChStmt,
    EmitStmt, OnEventBlock, MatchArm, MatchStmt,
    ReturnStmt, ExprStmt, BranchStmt, LoopStmt, BreakStmt,
)


class ParseError(Exception):
    pass


class Parser:
    def __init__(self, tokens: list[Token], base_dir: str = None,
                 _imported: set = None):
        self.tokens = [t for t in tokens if t.type != TT.NEWLINE]
        self.pos = 0
        self.base_dir = base_dir or os.getcwd()
        self._imported: set = _imported if _imported is not None else set()

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
        trusts = []
        while self.peek().type != TT.EOF:
            t = self.peek()
            if t.type == TT.IMPORT:
                imported = self._parse_import()
                if imported:
                    agents.extend(imported.agents)
                    attractions.extend(imported.attractions)
                    trusts.extend(imported.trusts or [])
            elif t.type == TT.AGENT:
                agents.append(self.parse_agent())
            elif (t.type == TT.IDENT
                  and self.pos + 1 < len(self.tokens)
                  and self.tokens[self.pos + 1].type == TT.ATTRACT):
                attractions.append(self.parse_top_attraction())
            elif (t.type == TT.IDENT
                  and self.pos + 1 < len(self.tokens)
                  and self.tokens[self.pos + 1].type == TT.TRUST):
                trusts.append(self.parse_top_trust())
            else:
                self.advance()
        return Program(agents=agents, attractions=attractions, trusts=trusts)

    def _parse_import(self):
        """import "path/to/file.nema" — ファイルを読み込んでマージ"""
        from lexer import Lexer
        self.advance()  # consume 'import'
        path_tok = self.advance()
        rel_path = path_tok.value  # STRING トークン（クォートなし）
        full_path = os.path.normpath(os.path.join(self.base_dir, rel_path))
        if full_path in self._imported:
            return None  # 循環 import 防止
        self._imported.add(full_path)
        try:
            with open(full_path) as f:
                src = f.read()
        except FileNotFoundError:
            raise ParseError(f"import: ファイルが見つからない: {full_path!r}")
        tokens = Lexer(src).tokenize()
        sub_parser = Parser(tokens,
                            base_dir=os.path.dirname(full_path),
                            _imported=self._imported)
        return sub_parser.parse()

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
        on_events = []
        trust = None
        capability = None
        contract = None

        while self.peek().type != TT.RBRACE:
            t = self.peek()
            if t.type == TT.MOOD:
                mood = self.parse_mood()
            elif t.type in (TT.FN, TT.REQUIRES, TT.ENSURES, TT.AFTER, TT.ON_ERROR):
                fns.append(self.parse_fn())
            elif t.type == TT.WHEN:
                whens.append(self.parse_when_block())
            elif t.type == TT.ON:
                on_events.append(self.parse_on_event())
            elif t.type == TT.TRUST:
                trust = self.parse_trust_decl()
            elif t.type == TT.CAPABILITY:
                capability = self.parse_capability_decl()
            elif t.type == TT.CONTRACT:
                contract = self.parse_contract()
            elif t.type == TT.IDENT and t.value == "attractor":
                attractors.append(self.parse_attractor())
            else:
                self.advance()

        self.expect(TT.RBRACE)
        return AgentDecl(name=name, mood=mood, fns=fns,
                         whens=whens, attractors=attractors,
                         on_events=on_events, trust=trust,
                         capability=capability, contract=contract)

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
        ensures = None
        on_error_body = None

        if self.peek().type == TT.REQUIRES:
            self.advance()
            self.expect(TT.LPAREN)
            requires = self.parse_condition()
            self.expect(TT.RPAREN)

        if self.peek().type == TT.ENSURES:
            self.advance()
            self.expect(TT.LPAREN)
            ensures = self.parse_condition()
            self.expect(TT.RPAREN)

        while self.peek().type in (TT.AFTER, TT.ON_ERROR):
            deco = self.advance()
            if deco.type == TT.ON_ERROR and self.peek().type == TT.LBRACE:
                self.advance()
                on_error_body = self.parse_body()
                self.expect(TT.RBRACE)
            elif self.peek().type == TT.LPAREN:
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
                      requires=requires, ensures=ensures, body=body,
                      on_error_body=on_error_body)

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

        if t.type == TT.OWN:
            return self.parse_own()

        if t.type == TT.RELEASE:
            return self.parse_release()

        if t.type == TT.RECV:
            return self.parse_recv()

        if t.type == TT.SEND:
            return self.parse_send_ch()

        if t.type == TT.CLOSE:
            return self.parse_close_ch()

        if t.type == TT.SYNC:
            return self.parse_spawn()

        if t.type == TT.EMIT:
            return self.parse_emit()

        if t.type == TT.MATCH:
            return self.parse_match()

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

    def parse_own(self) -> OwnStmt:
        self.expect(TT.OWN)
        name = self.expect(TT.IDENT).value
        self.expect(TT.ASSIGN)
        value = self.parse_expr()
        return OwnStmt(name=name, value=value)

    def parse_release(self) -> ReleaseStmt:
        self.expect(TT.RELEASE)
        name = self.expect(TT.IDENT).value
        return ReleaseStmt(name=name)

    def parse_recv(self):
        self.expect(TT.RECV)
        name = self.expect(TT.IDENT).value
        # recv ch -> val { body }  — チャンネル受信
        if self.peek().type == TT.ARROW:
            self.advance()  # consume '->'
            var = self.expect(TT.IDENT).value
            self.expect(TT.LBRACE)
            body = self.parse_body()
            self.expect(TT.RBRACE)
            return RecvChStmt(channel=name, var=var, body=body)
        if self.peek().type == TT.FROM:
            self.advance()
            from_agent = self.expect(TT.IDENT).value
            return RecvStmt(name=name, from_agent=from_agent)
        # from なし → mailbox からブロッキング受信
        return RecvStmt(name=name, from_agent=None)

    def parse_send_ch(self) -> SendChStmt:
        """send <channel> <expr>"""
        self.advance()  # consume 'send'
        channel = self.expect(TT.IDENT).value
        value = self.parse_expr()
        return SendChStmt(channel=channel, value=value)

    def parse_close_ch(self) -> CloseChStmt:
        """close <channel>"""
        self.advance()  # consume 'close'
        channel = self.expect(TT.IDENT).value
        return CloseChStmt(channel=channel)

    def parse_spawn(self) -> SpawnStmt:
        self.advance()  # sync → spawn として使う
        fn_name = self.expect(TT.IDENT).value
        args = []
        if self.peek().type == TT.LPAREN:
            self.advance()
            while self.peek().type != TT.RPAREN:
                args.append(self.parse_expr())
                self.skip(TT.COMMA)
            self.expect(TT.RPAREN)
        return SpawnStmt(fn_name=fn_name, args=args)

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

        if t.type == TT.QUERY:
            return self.parse_query_expr()

        if t.type == TT.CHANNEL:
            self.advance()  # consume 'channel'
            self.expect(TT.LT)
            elem_type = self.parse_type()
            self.expect(TT.GT)
            return ChannelCreateExpr(elem_type=elem_type)

        if t.type == TT.LPAREN:
            self.advance()
            expr = self.parse_expr()
            self.expect(TT.RPAREN)
            return expr

        self.advance()
        return Literal(value=None)

    def parse_match(self) -> MatchStmt:
        """
        match <expr> {
          > 0.8 { ... }
          >= 0.5 { ... }
          == 0.3 { ... }
          _     { ... }
        }
        """
        self.advance()  # consume 'match'
        subject = self.parse_expr()
        self.expect(TT.LBRACE)
        arms = []
        while self.peek().type != TT.RBRACE:
            t = self.peek()
            # default arm: _
            if t.type == TT.IDENT and t.value == "_":
                self.advance()
                self.expect(TT.LBRACE)
                body = self.parse_body()
                self.expect(TT.RBRACE)
                arms.append(MatchArm(op=None, threshold=None, body=body))
                break  # default は最後
            # 条件 arm: op value { body }
            op = self.advance().value   # > < >= <= ==
            threshold = self.parse_expr()
            self.expect(TT.LBRACE)
            body = self.parse_body()
            self.expect(TT.RBRACE)
            arms.append(MatchArm(op=op, threshold=threshold, body=body))
        self.expect(TT.RBRACE)
        return MatchStmt(subject=subject, arms=arms)

    def parse_contract(self) -> ContractDecl:
        """
        contract {
          dp >= 0.0
          dp <= 1.0
          gaba >= 0.1
        }
        各行が独立した不変条件（parse_condition 形式）。
        """
        self.advance()  # consume 'contract'
        self.expect(TT.LBRACE)
        invariants = []
        while self.peek().type != TT.RBRACE:
            if self.peek().type == TT.EOF:
                break
            invariants.append(self.parse_condition())
        self.expect(TT.RBRACE)
        return ContractDecl(invariants=invariants)

    def parse_capability_decl(self) -> "CapabilityDecl":
        """capability: { alloc, free, write, read }"""
        self.advance()  # consume 'capability'
        self.expect(TT.COLON)
        self.expect(TT.LBRACE)
        caps = set()
        while self.peek().type != TT.RBRACE:
            caps.add(self.advance().value)
            self.skip(TT.COMMA)
        self.expect(TT.RBRACE)
        return CapabilityDecl(caps=caps)

    def parse_emit(self) -> EmitStmt:
        """emit "event_name" [expr]"""
        self.advance()  # consume 'emit'
        event = self.advance().value  # STRING or IDENT
        value = None
        if self.peek().type not in (TT.RBRACE, TT.EOF, TT.NEWLINE):
            value = self.parse_expr()
        return EmitStmt(event=event, value=value)

    def parse_on_event(self) -> OnEventBlock:
        """on "event_name" { ... }"""
        self.advance()  # consume 'on'
        event = self.advance().value  # STRING or IDENT
        self.expect(TT.LBRACE)
        body = self.parse_body()
        self.expect(TT.RBRACE)
        return OnEventBlock(event=event, body=body)

    def parse_trust_decl(self) -> TrustDecl:
        """trust: { AgentName: 0.8, ... }"""
        self.advance()  # consume 'trust'
        self.expect(TT.COLON)
        self.expect(TT.LBRACE)
        scores = {}
        while self.peek().type != TT.RBRACE:
            name = self.advance().value
            self.expect(TT.COLON)
            val = float(self.advance().value)
            scores[name] = val
            self.skip(TT.COMMA)
        self.expect(TT.RBRACE)
        return TrustDecl(scores=scores)

    def parse_top_trust(self):
        """AgentA trust AgentB 0.8  (トップレベル)"""
        from ast_nodes import TrustStmt
        a = self.advance().value   # IDENT
        self.advance()             # trust
        b = self.advance().value   # IDENT
        score = 0.5
        if self.peek().type in (TT.FLOAT, TT.INT):
            score = float(self.advance().value)
        return TrustStmt(agent_a=a, agent_b=b, score=score)

    def parse_query_expr(self) -> QueryExpr:
        """
        query <field> from <Agent>
        query owned <var> from <Agent>
        query mood from <Agent>
        """
        self.advance()  # consume 'query'
        # "owned <var>" か NeuroState フィールド名 or "mood"
        field_tok = self.advance()
        field = field_tok.value
        var = None
        if field == "owned":
            var = self.advance().value   # 変数名
        self.expect(TT.FROM)
        agent = self.advance().value     # エージェント名
        return QueryExpr(field=field, agent=agent, var=var)

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
        if t.type == TT.CHANNEL:
            self.advance()
            self.expect(TT.LT)
            elem = self.parse_type()
            self.expect(TT.GT)
            return TypeChannel(elem=elem)
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
