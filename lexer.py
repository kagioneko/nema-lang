import re
from dataclasses import dataclass
from enum import Enum, auto


class TT(Enum):
    # キーワード
    AGENT = auto()
    FN = auto()
    MOOD = auto()
    NEUROSTATE = auto()
    WHEN = auto()
    AWAIT = auto()
    LOOP = auto()
    BRANCH = auto()
    OWN = auto()
    RECV = auto()
    RELEASE = auto()
    QUERY = auto()
    FROM = auto()
    EMIT = auto()
    ON = auto()
    TRUST = auto()
    IMPORT = auto()
    MATCH = auto()
    CHANNEL = auto()
    SEND = auto()
    CLOSE = auto()
    CONTRACT = auto()
    WHILE = auto()
    UNTIL = auto()
    SYNC = auto()
    FOR = auto()
    IN = auto()
    OK = auto()
    ERR = auto()
    SET = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    LET = auto()
    RETURN = auto()
    # 型キーワード
    TYPE_I64 = auto()
    TYPE_I32 = auto()
    TYPE_F64 = auto()
    TYPE_BOOL = auto()
    TYPE_PTR = auto()
    TYPE_VOID = auto()
    # デコレータ
    REQUIRES = auto()
    ENSURES = auto()
    AFTER = auto()
    ON_ERROR = auto()
    CTX = auto()
    CAPABILITY = auto()
    CPOS_GATE = auto()
    # リテラル
    IDENT = auto()
    FLOAT = auto()
    INT = auto()
    STRING = auto()
    # 演算子
    ASSIGN = auto()     # =
    ARROW = auto()      # →
    AI_OP = auto()      # ~>
    ATTRACT = auto()    # ~~
    GT = auto()         # >
    LT = auto()         # <
    GE = auto()         # >=
    LE = auto()         # <=
    EQ = auto()         # ==
    PLUS = auto()       # +
    MINUS = auto()      # -
    PLUS_ASSIGN = auto() # +=
    MINUS_ASSIGN = auto() # -=
    DOT = auto()        # .
    DOTDOT = auto()     # ..
    LBRACKET = auto()   # [
    RBRACKET = auto()   # ]
    STAR = auto()       # *
    SLASH = auto()      # /
    COLON = auto()      # :
    COMMA = auto()      # ,
    AT = auto()         # @
    HASH = auto()       # #
    LBRACE = auto()     # {
    RBRACE = auto()     # }
    LPAREN = auto()     # (
    RPAREN = auto()     # )
    LANGLE = auto()     # <
    RANGLE = auto()     # >
    QUESTION = auto()  # ?
    # その他
    NEWLINE = auto()
    EOF = auto()


KEYWORDS = {
    "agent": TT.AGENT,
    "fn": TT.FN,
    "mood": TT.MOOD,
    "NeuroState": TT.NEUROSTATE,
    "when": TT.WHEN,
    "await": TT.AWAIT,
    "loop": TT.LOOP,
    "branch": TT.BRANCH,
    "own": TT.OWN,
    "recv": TT.RECV,
    "release": TT.RELEASE,
    "query": TT.QUERY,
    "from": TT.FROM,
    "emit": TT.EMIT,
    "on": TT.ON,
    "trust": TT.TRUST,
    "import": TT.IMPORT,
    "match": TT.MATCH,
    "channel": TT.CHANNEL,
    "set":     TT.SET,
    "send": TT.SEND,
    "close": TT.CLOSE,
    "contract": TT.CONTRACT,
    "while": TT.WHILE,
    "until": TT.UNTIL,
    "sync": TT.SYNC,
    "spawn": TT.SYNC,
    "for": TT.FOR,
    "in": TT.IN,
    "ok": TT.OK,
    "err": TT.ERR,
    "and": TT.AND,
    "or": TT.OR,
    "not": TT.NOT,
    "let": TT.LET,
    "return": TT.RETURN,
    "i64": TT.TYPE_I64,
    "i32": TT.TYPE_I32,
    "f64": TT.TYPE_F64,
    "bool": TT.TYPE_BOOL,
    "ptr": TT.TYPE_PTR,
    "void": TT.TYPE_VOID,
}

DECORATORS = {
    "requires": TT.REQUIRES,
    "ensures": TT.ENSURES,
    "after": TT.AFTER,
    "on_error": TT.ON_ERROR,
    "when": TT.WHEN,
    "cpos_gate": TT.CPOS_GATE,
}

KEYWORDS["capability"] = TT.CAPABILITY


@dataclass
class Token:
    type: TT
    value: str
    line: int

    def __repr__(self):
        return f"Token({self.type.name}, {self.value!r})"


class LexerError(Exception):
    pass


class Lexer:
    def __init__(self, src: str):
        self.src = src
        self.pos = 0
        self.line = 1

    def peek(self, offset=0) -> str:
        i = self.pos + offset
        return self.src[i] if i < len(self.src) else ""

    def advance(self) -> str:
        ch = self.src[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
        return ch

    def skip_whitespace(self):
        while self.pos < len(self.src) and self.peek() in (" ", "\t", "\r"):
            self.advance()

    def skip_comment(self):
        if self.peek() == "/" and self.peek(1) == "/":
            while self.pos < len(self.src) and self.peek() != "\n":
                self.advance()

    def read_string(self) -> Token:
        line = self.line
        self.advance()  # 開き "
        buf = ""
        while self.pos < len(self.src) and self.peek() != '"':
            buf += self.advance()
        self.advance()  # 閉じ "
        return Token(TT.STRING, buf, line)

    def read_number(self) -> Token:
        line = self.line
        buf = ""
        while self.pos < len(self.src):
            ch = self.peek()
            if ch.isdigit():
                buf += self.advance()
            elif ch == "." and self.peek(1) != ".":
                buf += self.advance()
            else:
                break
        tt = TT.FLOAT if "." in buf else TT.INT
        return Token(tt, buf, line)

    def read_ident(self) -> Token:
        line = self.line
        buf = ""
        while self.pos < len(self.src) and (self.peek().isalnum() or self.peek() in ("_",)):
            buf += self.advance()
        tt = KEYWORDS.get(buf, TT.IDENT)
        return Token(tt, buf, line)

    def tokenize(self) -> list[Token]:
        tokens = []
        while self.pos < len(self.src):
            self.skip_whitespace()
            self.skip_comment()
            if self.pos >= len(self.src):
                break

            ch = self.peek()
            line = self.line

            if ch == "\n":
                self.advance()
                tokens.append(Token(TT.NEWLINE, "\\n", line))
            elif ch == '"':
                tokens.append(self.read_string())
            elif ch.isdigit():
                tokens.append(self.read_number())
            elif ch.isalpha() or ch == "_":
                tokens.append(self.read_ident())
            elif ch == "@":
                self.advance()
                deco = ""
                while self.pos < len(self.src) and (self.peek().isalnum() or self.peek() == "_"):
                    deco += self.advance()
                tt = DECORATORS.get(deco, TT.AT)
                tokens.append(Token(tt, f"@{deco}", line))
            elif ch == "#":
                self.advance()
                name = ""
                while self.pos < len(self.src) and (self.peek().isalnum() or self.peek() == "_"):
                    name += self.advance()
                if name == "ctx":
                    tokens.append(Token(TT.CTX, "#ctx", line))
                else:
                    tokens.append(Token(TT.HASH, f"#{name}", line))
            elif ch == "~":
                self.advance()
                if self.peek() == ">":
                    self.advance()
                    tokens.append(Token(TT.AI_OP, "~>", line))
                elif self.peek() == "~":
                    self.advance()
                    tokens.append(Token(TT.ATTRACT, "~~", line))
            elif ch == "→":
                self.advance()
                tokens.append(Token(TT.ARROW, "→", line))
            elif ch == "+":
                self.advance()
                if self.peek() == "=":
                    self.advance()
                    tokens.append(Token(TT.PLUS_ASSIGN, "+=", line))
                else:
                    tokens.append(Token(TT.PLUS, "+", line))
            elif ch == "-":
                self.advance()
                if self.peek() == "=":
                    self.advance()
                    tokens.append(Token(TT.MINUS_ASSIGN, "-=", line))
                elif self.peek() == ">":
                    self.advance()
                    tokens.append(Token(TT.ARROW, "->", line))
                else:
                    tokens.append(Token(TT.MINUS, "-", line))
            elif ch == "=":
                self.advance()
                if self.peek() == "=":
                    self.advance()
                    tokens.append(Token(TT.EQ, "==", line))
                else:
                    tokens.append(Token(TT.ASSIGN, "=", line))
            elif ch == ">":
                self.advance()
                if self.peek() == "=":
                    self.advance()
                    tokens.append(Token(TT.GE, ">=", line))
                else:
                    tokens.append(Token(TT.GT, ">", line))
            elif ch == "<":
                self.advance()
                if self.peek() == "=":
                    self.advance()
                    tokens.append(Token(TT.LE, "<=", line))
                else:
                    tokens.append(Token(TT.LT, "<", line))
            elif ch == "{":
                self.advance(); tokens.append(Token(TT.LBRACE, "{", line))
            elif ch == "}":
                self.advance(); tokens.append(Token(TT.RBRACE, "}", line))
            elif ch == "(":
                self.advance(); tokens.append(Token(TT.LPAREN, "(", line))
            elif ch == ")":
                self.advance(); tokens.append(Token(TT.RPAREN, ")", line))
            elif ch == ":":
                self.advance(); tokens.append(Token(TT.COLON, ":", line))
            elif ch == ",":
                self.advance(); tokens.append(Token(TT.COMMA, ",", line))
            elif ch == ".":
                self.advance()
                if self.peek() == ".":
                    self.advance()
                    tokens.append(Token(TT.DOTDOT, "..", line))
                else:
                    tokens.append(Token(TT.DOT, ".", line))
            elif ch == "[":
                self.advance(); tokens.append(Token(TT.LBRACKET, "[", line))
            elif ch == "]":
                self.advance(); tokens.append(Token(TT.RBRACKET, "]", line))
            elif ch == "*":
                self.advance(); tokens.append(Token(TT.STAR, "*", line))
            elif ch == "/":
                self.advance(); tokens.append(Token(TT.SLASH, "/", line))
            elif ch == "?":
                self.advance(); tokens.append(Token(TT.QUESTION, "?", line))
            else:
                raise LexerError(f"line {line}: unexpected char {ch!r}")

        tokens.append(Token(TT.EOF, "", self.line))
        return tokens
