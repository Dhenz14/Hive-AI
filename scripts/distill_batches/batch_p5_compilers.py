"""
Batch P5 — Compiler Design & Language Implementation
Covers: lexing, parsing, type checking, code generation, optimization.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    (
        "compilers/lexer-parser",
        "Explain the fundamentals of building a programming language compiler frontend including lexical analysis with finite automata, recursive descent parsing, operator precedence climbing, AST construction, and provide a complete Python implementation of a lexer and parser for a simple expression language with variables, functions, if-expressions, and proper error reporting with source locations.",
        r"""# Building a Compiler Frontend: Lexer & Parser

## The Compilation Pipeline

A compiler transforms source code through a series of well-defined phases: **lexing** (characters → tokens), **parsing** (tokens → AST), **semantic analysis** (type checking, name resolution), **optimization** (AST/IR transformations), and **code generation** (IR → target code). The frontend (lexer + parser) is the foundation — every subsequent phase depends on a correct and informative AST.

**Why build your own**: Even if you never build a production language, understanding compiler internals makes you a better programmer. You'll understand why certain syntax errors produce confusing messages, why some languages are harder to parse than others, and how tools like linters and formatters work internally.

## Lexical Analysis

The lexer converts a stream of characters into a stream of **tokens** — the smallest meaningful units of the language. Each token has a **type** (keyword, identifier, number, operator) and a **span** (source location for error messages).

```python
# Complete lexer and parser for a simple expression language
from __future__ import annotations

import dataclasses
import enum
from typing import Any, Optional, Callable


# === Token Definitions ===

class TokenType(enum.Enum):
    # Literals
    INT = "INT"
    FLOAT = "FLOAT"
    STRING = "STRING"
    IDENT = "IDENT"

    # Keywords
    LET = "let"
    FN = "fn"
    IF = "if"
    ELSE = "else"
    RETURN = "return"
    TRUE = "true"
    FALSE = "false"

    # Operators
    PLUS = "+"
    MINUS = "-"
    STAR = "*"
    SLASH = "/"
    PERCENT = "%"
    EQ = "=="
    NEQ = "!="
    LT = "<"
    GT = ">"
    LTE = "<="
    GTE = ">="
    ASSIGN = "="
    BANG = "!"
    AND = "&&"
    OR = "||"

    # Delimiters
    LPAREN = "("
    RPAREN = ")"
    LBRACE = "{"
    RBRACE = "}"
    COMMA = ","
    SEMICOLON = ";"
    ARROW = "->"
    COLON = ":"

    # Special
    EOF = "EOF"
    NEWLINE = "NEWLINE"


@dataclasses.dataclass(frozen=True)
class Span:
    # Source location for error messages
    # Without spans, error messages say "syntax error" with no location.
    # With spans, they say "error at line 5, column 12" -- dramatically
    # improving the developer experience.
    line: int
    column: int
    offset: int  # byte offset in source
    length: int = 1

    def __repr__(self) -> str:
        return f"{self.line}:{self.column}"


@dataclasses.dataclass(frozen=True)
class Token:
    type: TokenType
    value: str
    span: Span


KEYWORDS: dict[str, TokenType] = {
    "let": TokenType.LET,
    "fn": TokenType.FN,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "return": TokenType.RETURN,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
}

TWO_CHAR_OPS: dict[str, TokenType] = {
    "==": TokenType.EQ,
    "!=": TokenType.NEQ,
    "<=": TokenType.LTE,
    ">=": TokenType.GTE,
    "&&": TokenType.AND,
    "||": TokenType.OR,
    "->": TokenType.ARROW,
}

SINGLE_CHAR_OPS: dict[str, TokenType] = {
    "+": TokenType.PLUS, "-": TokenType.MINUS,
    "*": TokenType.STAR, "/": TokenType.SLASH,
    "%": TokenType.PERCENT, "=": TokenType.ASSIGN,
    "<": TokenType.LT, ">": TokenType.GT,
    "!": TokenType.BANG, "(": TokenType.LPAREN,
    ")": TokenType.RPAREN, "{": TokenType.LBRACE,
    "}": TokenType.RBRACE, ",": TokenType.COMMA,
    ";": TokenType.SEMICOLON, ":": TokenType.COLON,
}


class LexError(Exception):
    def __init__(self, message: str, span: Span) -> None:
        self.span = span
        super().__init__(f"{span}: {message}")


class Lexer:
    # Converts source text into a stream of tokens.
    #
    # Uses a simple character-by-character scanner rather than
    # regex-based lexing. This is more verbose but gives us precise
    # control over error messages and source locations.
    #
    # The lexer is implemented as an iterator -- it yields tokens
    # lazily, which means it can handle arbitrarily large files
    # without loading all tokens into memory at once.

    def __init__(self, source: str, filename: str = "<stdin>") -> None:
        self.source = source
        self.filename = filename
        self.pos = 0
        self.line = 1
        self.column = 1

    def _current(self) -> str:
        if self.pos >= len(self.source):
            return "\0"
        return self.source[self.pos]

    def _peek(self, offset: int = 1) -> str:
        pos = self.pos + offset
        if pos >= len(self.source):
            return "\0"
        return self.source[pos]

    def _advance(self) -> str:
        ch = self._current()
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return ch

    def _span(self, length: int = 1) -> Span:
        return Span(self.line, self.column, self.pos, length)

    def _skip_whitespace_and_comments(self) -> None:
        while self.pos < len(self.source):
            ch = self._current()
            if ch in " \t\r":
                self._advance()
            elif ch == "/" and self._peek() == "/":
                # Line comment
                while self.pos < len(self.source) and self._current() != "\n":
                    self._advance()
            elif ch == "/" and self._peek() == "*":
                # Block comment
                self._advance()  # /
                self._advance()  # *
                while self.pos < len(self.source):
                    if self._current() == "*" and self._peek() == "/":
                        self._advance()
                        self._advance()
                        break
                    self._advance()
            else:
                break

    def _read_number(self) -> Token:
        start = self.pos
        span = self._span()
        is_float = False

        while self._current().isdigit():
            self._advance()

        if self._current() == "." and self._peek().isdigit():
            is_float = True
            self._advance()  # consume .
            while self._current().isdigit():
                self._advance()

        value = self.source[start:self.pos]
        token_type = TokenType.FLOAT if is_float else TokenType.INT
        return Token(token_type, value, Span(span.line, span.column, start, len(value)))

    def _read_string(self) -> Token:
        span = self._span()
        self._advance()  # opening quote
        start = self.pos
        while self._current() != '"' and self._current() != "\0":
            if self._current() == "\\":
                self._advance()  # escape character
            self._advance()

        if self._current() == "\0":
            raise LexError("Unterminated string literal", span)

        value = self.source[start:self.pos]
        self._advance()  # closing quote
        return Token(TokenType.STRING, value, span)

    def _read_identifier(self) -> Token:
        start = self.pos
        span = self._span()
        while self._current().isalnum() or self._current() == "_":
            self._advance()

        value = self.source[start:self.pos]
        token_type = KEYWORDS.get(value, TokenType.IDENT)
        return Token(token_type, value, Span(span.line, span.column, start, len(value)))

    def tokenize(self) -> list[Token]:
        # Tokenize the entire source into a list of tokens
        tokens: list[Token] = []

        while self.pos < len(self.source):
            self._skip_whitespace_and_comments()

            if self.pos >= len(self.source):
                break

            ch = self._current()

            if ch == "\n":
                self._advance()
                continue

            if ch.isdigit():
                tokens.append(self._read_number())
            elif ch == '"':
                tokens.append(self._read_string())
            elif ch.isalpha() or ch == "_":
                tokens.append(self._read_identifier())
            else:
                # Check two-character operators first
                two = ch + self._peek()
                if two in TWO_CHAR_OPS:
                    span = self._span(2)
                    self._advance()
                    self._advance()
                    tokens.append(Token(TWO_CHAR_OPS[two], two, span))
                elif ch in SINGLE_CHAR_OPS:
                    span = self._span()
                    self._advance()
                    tokens.append(Token(SINGLE_CHAR_OPS[ch], ch, span))
                else:
                    raise LexError(f"Unexpected character: {ch!r}", self._span())

        tokens.append(Token(TokenType.EOF, "", self._span()))
        return tokens
```

## Recursive Descent Parser with Precedence Climbing

```python
# === AST Node Definitions ===

@dataclasses.dataclass
class ASTNode:
    span: Span


@dataclasses.dataclass
class IntLiteral(ASTNode):
    value: int


@dataclasses.dataclass
class FloatLiteral(ASTNode):
    value: float


@dataclasses.dataclass
class StringLiteral(ASTNode):
    value: str


@dataclasses.dataclass
class BoolLiteral(ASTNode):
    value: bool


@dataclasses.dataclass
class Identifier(ASTNode):
    name: str


@dataclasses.dataclass
class BinaryOp(ASTNode):
    op: str
    left: ASTNode
    right: ASTNode


@dataclasses.dataclass
class UnaryOp(ASTNode):
    op: str
    operand: ASTNode


@dataclasses.dataclass
class CallExpr(ASTNode):
    callee: ASTNode
    args: list[ASTNode]


@dataclasses.dataclass
class IfExpr(ASTNode):
    condition: ASTNode
    then_branch: ASTNode
    else_branch: Optional[ASTNode]


@dataclasses.dataclass
class LetStmt(ASTNode):
    name: str
    type_ann: Optional[str]
    value: ASTNode


@dataclasses.dataclass
class FnDef(ASTNode):
    name: str
    params: list[tuple[str, Optional[str]]]  # (name, type_annotation)
    return_type: Optional[str]
    body: list[ASTNode]


@dataclasses.dataclass
class ReturnStmt(ASTNode):
    value: Optional[ASTNode]


@dataclasses.dataclass
class Block(ASTNode):
    statements: list[ASTNode]


@dataclasses.dataclass
class Program(ASTNode):
    statements: list[ASTNode]


class ParseError(Exception):
    def __init__(self, message: str, span: Span) -> None:
        self.span = span
        super().__init__(f"{span}: {message}")


# Operator precedence table for precedence climbing
# Higher number = higher precedence (binds tighter)
PRECEDENCE: dict[str, tuple[int, str]] = {
    "||": (1, "left"),
    "&&": (2, "left"),
    "==": (3, "left"), "!=": (3, "left"),
    "<": (4, "left"), ">": (4, "left"),
    "<=": (4, "left"), ">=": (4, "left"),
    "+": (5, "left"), "-": (5, "left"),
    "*": (6, "left"), "/": (6, "left"),
    "%": (6, "left"),
}


class Parser:
    # Recursive descent parser with Pratt-style precedence climbing.
    #
    # Precedence climbing is elegant because it handles operator
    # precedence and associativity without needing a separate grammar
    # rule per precedence level. A traditional recursive descent parser
    # for 7 precedence levels needs 7 functions; precedence climbing
    # uses one function with a loop.
    #
    # Error recovery strategy: on parse error, we skip tokens until
    # we find a synchronization point (semicolon, closing brace, or
    # keyword). This allows reporting multiple errors per parse instead
    # of stopping at the first one.

    def __init__(self, tokens: list[Token]) -> None:
        self.tokens = tokens
        self.pos = 0
        self.errors: list[ParseError] = []

    def _current(self) -> Token:
        return self.tokens[min(self.pos, len(self.tokens) - 1)]

    def _peek(self, offset: int = 1) -> Token:
        idx = min(self.pos + offset, len(self.tokens) - 1)
        return self.tokens[idx]

    def _advance(self) -> Token:
        tok = self._current()
        self.pos += 1
        return tok

    def _expect(self, expected: TokenType) -> Token:
        tok = self._current()
        if tok.type != expected:
            raise ParseError(
                f"Expected {expected.value}, got {tok.value!r}",
                tok.span,
            )
        return self._advance()

    def _match(self, *types: TokenType) -> Optional[Token]:
        if self._current().type in types:
            return self._advance()
        return None

    def parse(self) -> Program:
        # Parse a complete program
        statements: list[ASTNode] = []
        while self._current().type != TokenType.EOF:
            try:
                stmt = self._parse_statement()
                statements.append(stmt)
            except ParseError as e:
                self.errors.append(e)
                self._synchronize()

        span = statements[0].span if statements else Span(1, 1, 0)
        return Program(span=span, statements=statements)

    def _synchronize(self) -> None:
        # Error recovery: skip to next statement boundary
        while self._current().type != TokenType.EOF:
            if self._current().type in (TokenType.SEMICOLON, TokenType.RBRACE):
                self._advance()
                return
            if self._current().type in (TokenType.LET, TokenType.FN, TokenType.RETURN):
                return
            self._advance()

    def _parse_statement(self) -> ASTNode:
        tok = self._current()

        if tok.type == TokenType.LET:
            return self._parse_let()
        elif tok.type == TokenType.FN:
            return self._parse_fn()
        elif tok.type == TokenType.RETURN:
            return self._parse_return()
        else:
            expr = self._parse_expression(0)
            self._match(TokenType.SEMICOLON)
            return expr

    def _parse_let(self) -> LetStmt:
        span = self._expect(TokenType.LET).span
        name = self._expect(TokenType.IDENT).value
        type_ann = None
        if self._match(TokenType.COLON):
            type_ann = self._expect(TokenType.IDENT).value
        self._expect(TokenType.ASSIGN)
        value = self._parse_expression(0)
        self._match(TokenType.SEMICOLON)
        return LetStmt(span=span, name=name, type_ann=type_ann, value=value)

    def _parse_fn(self) -> FnDef:
        span = self._expect(TokenType.FN).span
        name = self._expect(TokenType.IDENT).value
        self._expect(TokenType.LPAREN)

        params: list[tuple[str, Optional[str]]] = []
        while self._current().type != TokenType.RPAREN:
            param_name = self._expect(TokenType.IDENT).value
            type_ann = None
            if self._match(TokenType.COLON):
                type_ann = self._expect(TokenType.IDENT).value
            params.append((param_name, type_ann))
            if not self._match(TokenType.COMMA):
                break

        self._expect(TokenType.RPAREN)

        return_type = None
        if self._match(TokenType.ARROW):
            return_type = self._expect(TokenType.IDENT).value

        body = self._parse_block()
        return FnDef(
            span=span, name=name, params=params,
            return_type=return_type, body=body.statements,
        )

    def _parse_return(self) -> ReturnStmt:
        span = self._expect(TokenType.RETURN).span
        value = None
        if self._current().type not in (TokenType.SEMICOLON, TokenType.RBRACE):
            value = self._parse_expression(0)
        self._match(TokenType.SEMICOLON)
        return ReturnStmt(span=span, value=value)

    def _parse_block(self) -> Block:
        span = self._expect(TokenType.LBRACE).span
        stmts: list[ASTNode] = []
        while self._current().type not in (TokenType.RBRACE, TokenType.EOF):
            try:
                stmts.append(self._parse_statement())
            except ParseError as e:
                self.errors.append(e)
                self._synchronize()
        self._expect(TokenType.RBRACE)
        return Block(span=span, statements=stmts)

    def _parse_expression(self, min_prec: int) -> ASTNode:
        # Pratt-style precedence climbing for binary operators.
        #
        # This handles left-associative operators naturally:
        # 1 + 2 + 3 parses as (1 + 2) + 3
        # and right-associative operators by adjusting min_prec.
        left = self._parse_unary()

        while True:
            op_token = self._current()
            op_str = op_token.value

            if op_str not in PRECEDENCE:
                break

            prec, assoc = PRECEDENCE[op_str]
            if prec < min_prec:
                break

            self._advance()  # consume operator

            # For left-associative: next operand must have higher precedence
            # For right-associative: same precedence is ok
            next_min = prec + 1 if assoc == "left" else prec
            right = self._parse_expression(next_min)

            left = BinaryOp(
                span=op_token.span, op=op_str, left=left, right=right,
            )

        return left

    def _parse_unary(self) -> ASTNode:
        tok = self._current()
        if tok.type in (TokenType.MINUS, TokenType.BANG):
            self._advance()
            operand = self._parse_unary()
            return UnaryOp(span=tok.span, op=tok.value, operand=operand)
        return self._parse_postfix()

    def _parse_postfix(self) -> ASTNode:
        # Parse function calls: expr(arg1, arg2)
        expr = self._parse_primary()

        while self._current().type == TokenType.LPAREN:
            self._advance()
            args: list[ASTNode] = []
            while self._current().type != TokenType.RPAREN:
                args.append(self._parse_expression(0))
                if not self._match(TokenType.COMMA):
                    break
            self._expect(TokenType.RPAREN)
            expr = CallExpr(span=expr.span, callee=expr, args=args)

        return expr

    def _parse_primary(self) -> ASTNode:
        tok = self._current()

        if tok.type == TokenType.INT:
            self._advance()
            return IntLiteral(span=tok.span, value=int(tok.value))

        if tok.type == TokenType.FLOAT:
            self._advance()
            return FloatLiteral(span=tok.span, value=float(tok.value))

        if tok.type == TokenType.STRING:
            self._advance()
            return StringLiteral(span=tok.span, value=tok.value)

        if tok.type in (TokenType.TRUE, TokenType.FALSE):
            self._advance()
            return BoolLiteral(span=tok.span, value=tok.type == TokenType.TRUE)

        if tok.type == TokenType.IDENT:
            self._advance()
            return Identifier(span=tok.span, name=tok.value)

        if tok.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expression(0)
            self._expect(TokenType.RPAREN)
            return expr

        if tok.type == TokenType.IF:
            return self._parse_if()

        raise ParseError(f"Unexpected token: {tok.value!r}", tok.span)

    def _parse_if(self) -> IfExpr:
        span = self._expect(TokenType.IF).span
        condition = self._parse_expression(0)
        then_branch = self._parse_block()

        else_branch = None
        if self._match(TokenType.ELSE):
            if self._current().type == TokenType.IF:
                else_branch = self._parse_if()
            else:
                else_branch = self._parse_block()

        return IfExpr(
            span=span, condition=condition,
            then_branch=then_branch, else_branch=else_branch,
        )
```

## Testing the Frontend

```python
def pretty_print(node: ASTNode, indent: int = 0) -> str:
    # Pretty-print AST for debugging
    pad = "  " * indent
    if isinstance(node, IntLiteral):
        return f"{pad}Int({node.value})"
    if isinstance(node, FloatLiteral):
        return f"{pad}Float({node.value})"
    if isinstance(node, StringLiteral):
        return f"{pad}String({node.value!r})"
    if isinstance(node, BoolLiteral):
        return f"{pad}Bool({node.value})"
    if isinstance(node, Identifier):
        return f"{pad}Ident({node.name})"
    if isinstance(node, BinaryOp):
        left = pretty_print(node.left, indent + 1)
        right = pretty_print(node.right, indent + 1)
        return f"{pad}BinOp({node.op})\n{left}\n{right}"
    if isinstance(node, UnaryOp):
        operand = pretty_print(node.operand, indent + 1)
        return f"{pad}UnaryOp({node.op})\n{operand}"
    if isinstance(node, CallExpr):
        callee = pretty_print(node.callee, indent + 1)
        args = "\n".join(pretty_print(a, indent + 1) for a in node.args)
        return f"{pad}Call\n{callee}\n{args}"
    if isinstance(node, LetStmt):
        val = pretty_print(node.value, indent + 1)
        ann = f": {node.type_ann}" if node.type_ann else ""
        return f"{pad}Let({node.name}{ann})\n{val}"
    if isinstance(node, FnDef):
        params = ", ".join(
            f"{n}: {t}" if t else n for n, t in node.params
        )
        body = "\n".join(pretty_print(s, indent + 1) for s in node.body)
        ret = f" -> {node.return_type}" if node.return_type else ""
        return f"{pad}Fn({node.name}({params}){ret})\n{body}"
    if isinstance(node, Program):
        stmts = "\n".join(pretty_print(s, indent) for s in node.statements)
        return f"Program\n{stmts}"
    return f"{pad}{type(node).__name__}(...)"


def test_lexer():
    source = 'let x: int = 42 + y * 3;'
    lexer = Lexer(source)
    tokens = lexer.tokenize()
    types = [t.type for t in tokens]
    assert TokenType.LET in types
    assert TokenType.IDENT in types
    assert TokenType.INT in types
    assert TokenType.PLUS in types
    assert TokenType.STAR in types
    print(f"Lexer test passed: {len(tokens)} tokens")


def test_parser_expressions():
    # Test precedence: 1 + 2 * 3 should parse as 1 + (2 * 3)
    tokens = Lexer("1 + 2 * 3").tokenize()
    parser = Parser(tokens)
    expr = parser._parse_expression(0)
    assert isinstance(expr, BinaryOp)
    assert expr.op == "+"
    assert isinstance(expr.right, BinaryOp)
    assert expr.right.op == "*"
    print("Precedence test passed: 1 + 2 * 3 = 1 + (2 * 3)")


def test_parser_program():
    source = """
    fn add(a: int, b: int) -> int {
        return a + b;
    }

    let result = add(3, 4);
    """
    tokens = Lexer(source).tokenize()
    parser = Parser(tokens)
    program = parser.parse()

    assert len(program.statements) == 2
    assert isinstance(program.statements[0], FnDef)
    assert program.statements[0].name == "add"
    assert len(program.statements[0].params) == 2
    assert isinstance(program.statements[1], LetStmt)
    print("Program parse test passed")
    print(pretty_print(program))


def test_error_recovery():
    # Parser should report errors but continue
    source = "let x = ; let y = 5;"
    tokens = Lexer(source).tokenize()
    parser = Parser(tokens)
    program = parser.parse()
    assert len(parser.errors) > 0, "Should have parse errors"
    print(f"Error recovery test: {len(parser.errors)} errors, "
          f"{len(program.statements)} statements recovered")


if __name__ == "__main__":
    test_lexer()
    test_parser_expressions()
    test_parser_program()
    test_error_recovery()
    print("\nAll compiler frontend tests passed!")
```

## Key Design Decisions

| Decision | Choice | Why |
|----------|--------|-----|
| **Lexer approach** | Hand-written scanner | Better error messages than regex, full source location tracking |
| **Parser approach** | Recursive descent + precedence climbing | Simpler than parser generators, easy to extend, good errors |
| **AST design** | Typed dataclasses | Type safety, pattern matching support, immutable by default |
| **Error recovery** | Synchronization tokens | Reports multiple errors per parse, better developer experience |
| **Source locations** | Span on every AST node | Essential for error messages, IDE integration, and source maps |

## Common Pitfalls

1. **Forgetting left-recursion**: `expr → expr + term` is left-recursive and will cause infinite recursion in a recursive descent parser. Precedence climbing handles this naturally by using iteration instead of recursion for left-associative operators.

2. **Greedy lexing mistakes**: The lexer must try longer matches first — `<=` before `<`, `==` before `=`. Our two-character operator check handles this correctly.

3. **Poor error messages**: "Unexpected token" is useless. Always include what was **expected** and what was **found**, with source locations. This is why we thread `Span` through every token and AST node.

## Key Takeaways

- A **hand-written recursive descent parser** is the industry standard for production compilers (GCC, Clang, Rust, Go, TypeScript all use them) because they give the best error messages and are easiest to debug
- **Precedence climbing** (Pratt parsing) elegantly handles operator precedence and associativity in a single function, eliminating the need for one grammar rule per precedence level
- **Source location tracking** (spans) from the lexer through the AST is essential — without it, error messages are useless and tooling integration (LSP, linters, formatters) is impossible
- **Error recovery** via synchronization tokens allows the parser to report multiple errors per invocation, which dramatically improves the developer experience compared to stopping at the first error
- The compiler frontend is **language-agnostic infrastructure** — the same lexer/parser patterns work for programming languages, configuration formats, query languages, and domain-specific languages
"""
    ),
    (
        "compilers/type-checking",
        "Explain type checking and type inference for programming languages including Hindley-Milner type inference, unification algorithm, let-polymorphism, constraint generation and solving, and provide a Python implementation of a complete type checker for a simple functional language with integers, booleans, functions, let-bindings, and if-expressions that infers types without explicit annotations.",
        r"""# Type Checking & Hindley-Milner Type Inference

## Why Type Inference Matters

Type inference frees programmers from writing type annotations while still catching type errors at compile time. Languages like Haskell, OCaml, Rust (partially), and TypeScript use variants of the **Hindley-Milner** (HM) algorithm, which can infer the most general type for any expression in a simply-typed lambda calculus — without any annotations at all.

The HM algorithm is remarkable because it's both **complete** (it infers the most general type possible) and **decidable** (it always terminates). This is a rare combination in type theory — most expressive type systems sacrifice one or the other.

## The Core Concepts

### Types as Trees

Types are tree structures: `int` is a leaf, `int -> bool` is a node with two children. **Type variables** (like `a`, `b`) represent unknown types that inference will determine.

### Unification

The heart of HM inference is **unification**: given two types, find a **substitution** (mapping from type variables to types) that makes them equal. For example, unifying `a -> int` with `bool -> b` produces `{a = bool, b = int}`.

### Let-Polymorphism

In `let f = \x -> x in (f 1, f true)`, the identity function `f` is used at both `int -> int` and `bool -> bool`. HM handles this with **generalization**: at `let` boundaries, free type variables are universally quantified, allowing polymorphic use.

```python
# Complete Hindley-Milner type inference implementation
from __future__ import annotations

import dataclasses
from typing import Optional, Union


# === Type Representation ===

@dataclasses.dataclass(frozen=True)
class TInt:
    # The integer type
    pass


@dataclasses.dataclass(frozen=True)
class TBool:
    # The boolean type
    pass


@dataclasses.dataclass(frozen=True)
class TVar:
    # A type variable (unknown type to be inferred)
    name: str


@dataclasses.dataclass(frozen=True)
class TFun:
    # Function type: param_type -> return_type
    param: Type
    ret: Type


@dataclasses.dataclass(frozen=True)
class TForAll:
    # Universally quantified (polymorphic) type
    # forall a. a -> a
    vars: tuple[str, ...]
    body: Type


Type = Union[TInt, TBool, TVar, TFun, TForAll]


# === Expression AST (input to type checker) ===

@dataclasses.dataclass
class EInt:
    value: int

@dataclasses.dataclass
class EBool:
    value: bool

@dataclasses.dataclass
class EVar:
    name: str

@dataclasses.dataclass
class ELam:
    # Lambda: \param -> body
    param: str
    body: Expr

@dataclasses.dataclass
class EApp:
    # Application: func(arg)
    func: Expr
    arg: Expr

@dataclasses.dataclass
class ELet:
    # Let binding: let name = value in body
    name: str
    value: Expr
    body: Expr

@dataclasses.dataclass
class EIf:
    cond: Expr
    then_br: Expr
    else_br: Expr

@dataclasses.dataclass
class EBinOp:
    op: str  # "+", "-", "==", "<", "&&", "||"
    left: Expr
    right: Expr


Expr = Union[EInt, EBool, EVar, ELam, EApp, ELet, EIf, EBinOp]


# === Substitution ===

class Substitution:
    # A mapping from type variables to types.
    #
    # Substitutions are composed, not replaced: applying substitution
    # S2 after S1 means S2(S1(type)). This composition is critical
    # for correctness because later unifications must see the effects
    # of earlier ones.

    def __init__(self) -> None:
        self.mapping: dict[str, Type] = {}

    def apply(self, ty: Type) -> Type:
        # Apply this substitution to a type, replacing type variables
        if isinstance(ty, TInt) or isinstance(ty, TBool):
            return ty
        if isinstance(ty, TVar):
            if ty.name in self.mapping:
                # Apply recursively to handle chains: a -> b -> int
                return self.apply(self.mapping[ty.name])
            return ty
        if isinstance(ty, TFun):
            return TFun(self.apply(ty.param), self.apply(ty.ret))
        if isinstance(ty, TForAll):
            # Don't substitute bound variables
            inner = Substitution()
            inner.mapping = {
                k: v for k, v in self.mapping.items()
                if k not in ty.vars
            }
            return TForAll(ty.vars, inner.apply(ty.body))
        return ty

    def compose(self, other: Substitution) -> Substitution:
        # Compose two substitutions: self after other
        result = Substitution()
        # Apply self to all of other's mappings
        for var, ty in other.mapping.items():
            result.mapping[var] = self.apply(ty)
        # Add self's mappings (other's take precedence for shared keys)
        for var, ty in self.mapping.items():
            if var not in result.mapping:
                result.mapping[var] = ty
        return result


class TypeError(Exception):
    pass


# === Unification ===

def occurs_check(var_name: str, ty: Type) -> bool:
    # Check if a type variable occurs in a type.
    #
    # This prevents infinite types like a = a -> int.
    # Without the occurs check, unification would loop forever
    # on expressions like (\x -> x x) — the self-application
    # combinator that is untypable in simply-typed lambda calculus.
    if isinstance(ty, TVar):
        return ty.name == var_name
    if isinstance(ty, TFun):
        return occurs_check(var_name, ty.param) or occurs_check(var_name, ty.ret)
    return False


def unify(t1: Type, t2: Type) -> Substitution:
    # Unify two types, returning a substitution that makes them equal.
    #
    # This is the Robinson unification algorithm:
    # 1. If both are the same concrete type, succeed with empty substitution
    # 2. If one is a type variable, bind it to the other (with occurs check)
    # 3. If both are function types, unify params and returns
    # 4. Otherwise, types are incompatible -- raise TypeError

    if isinstance(t1, TInt) and isinstance(t2, TInt):
        return Substitution()
    if isinstance(t1, TBool) and isinstance(t2, TBool):
        return Substitution()

    if isinstance(t1, TVar):
        if t1 == t2:
            return Substitution()
        if occurs_check(t1.name, t2):
            raise TypeError(f"Infinite type: {t1.name} = {format_type(t2)}")
        s = Substitution()
        s.mapping[t1.name] = t2
        return s

    if isinstance(t2, TVar):
        return unify(t2, t1)  # swap to hit the TVar case above

    if isinstance(t1, TFun) and isinstance(t2, TFun):
        s1 = unify(t1.param, t2.param)
        s2 = unify(s1.apply(t1.ret), s1.apply(t2.ret))
        return s2.compose(s1)

    raise TypeError(
        f"Cannot unify {format_type(t1)} with {format_type(t2)}"
    )


# === Type Inference (Algorithm W) ===

class TypeInferencer:
    # Hindley-Milner type inference using Algorithm W.
    #
    # Algorithm W works bottom-up: it infers types for subexpressions
    # first, then uses unification to constrain type variables.
    #
    # Key steps:
    # 1. Assign fresh type variables to unknowns
    # 2. Generate constraints by traversing the expression
    # 3. Solve constraints via unification
    # 4. At let-boundaries, generalize free type variables

    def __init__(self) -> None:
        self._next_var = 0

    def fresh_var(self) -> TVar:
        # Generate a fresh type variable
        name = f"t{self._next_var}"
        self._next_var += 1
        return TVar(name)

    def free_vars(self, ty: Type) -> set[str]:
        # Collect free (unbound) type variables in a type
        if isinstance(ty, TInt) or isinstance(ty, TBool):
            return set()
        if isinstance(ty, TVar):
            return {ty.name}
        if isinstance(ty, TFun):
            return self.free_vars(ty.param) | self.free_vars(ty.ret)
        if isinstance(ty, TForAll):
            return self.free_vars(ty.body) - set(ty.vars)
        return set()

    def free_vars_env(self, env: dict[str, Type]) -> set[str]:
        result: set[str] = set()
        for ty in env.values():
            result |= self.free_vars(ty)
        return result

    def generalize(self, env: dict[str, Type], ty: Type) -> Type:
        # Generalize a type by quantifying free variables not in env.
        #
        # This is what enables let-polymorphism: after inferring the
        # type of a let-binding, we universally quantify any type
        # variables that aren't constrained by the surrounding context.
        free_in_ty = self.free_vars(ty)
        free_in_env = self.free_vars_env(env)
        generalizable = free_in_ty - free_in_env

        if not generalizable:
            return ty
        return TForAll(tuple(sorted(generalizable)), ty)

    def instantiate(self, ty: Type) -> Type:
        # Replace quantified variables with fresh type variables.
        #
        # Each use of a polymorphic binding gets fresh variables,
        # allowing it to be used at different types.
        if not isinstance(ty, TForAll):
            return ty

        fresh_map: dict[str, Type] = {}
        for var in ty.vars:
            fresh_map[var] = self.fresh_var()

        def substitute(t: Type) -> Type:
            if isinstance(t, TVar) and t.name in fresh_map:
                return fresh_map[t.name]
            if isinstance(t, TFun):
                return TFun(substitute(t.param), substitute(t.ret))
            return t

        return substitute(ty.body)

    def infer(self, env: dict[str, Type], expr: Expr) -> tuple[Substitution, Type]:
        # Infer the type of an expression in the given environment.
        #
        # Returns (substitution, inferred_type). The substitution
        # captures all type variable bindings discovered during inference.

        if isinstance(expr, EInt):
            return Substitution(), TInt()

        if isinstance(expr, EBool):
            return Substitution(), TBool()

        if isinstance(expr, EVar):
            if expr.name not in env:
                raise TypeError(f"Unbound variable: {expr.name}")
            ty = self.instantiate(env[expr.name])
            return Substitution(), ty

        if isinstance(expr, ELam):
            param_type = self.fresh_var()
            new_env = {**env, expr.param: param_type}
            s, body_type = self.infer(new_env, expr.body)
            return s, TFun(s.apply(param_type), body_type)

        if isinstance(expr, EApp):
            result_type = self.fresh_var()
            s1, func_type = self.infer(env, expr.func)
            s2, arg_type = self.infer(
                {k: s1.apply(v) for k, v in env.items()},
                expr.arg,
            )
            s3 = unify(
                s2.apply(func_type),
                TFun(arg_type, result_type),
            )
            return s3.compose(s2).compose(s1), s3.apply(result_type)

        if isinstance(expr, ELet):
            # Let-polymorphism: infer value type, generalize, then
            # infer body with the generalized binding
            s1, val_type = self.infer(env, expr.value)
            env1 = {k: s1.apply(v) for k, v in env.items()}
            gen_type = self.generalize(env1, val_type)
            env2 = {**env1, expr.name: gen_type}
            s2, body_type = self.infer(env2, expr.body)
            return s2.compose(s1), body_type

        if isinstance(expr, EIf):
            s1, cond_type = self.infer(env, expr.cond)
            s2 = unify(s1.apply(cond_type), TBool())
            s_so_far = s2.compose(s1)

            env1 = {k: s_so_far.apply(v) for k, v in env.items()}
            s3, then_type = self.infer(env1, expr.then_br)
            s_so_far = s3.compose(s_so_far)

            env2 = {k: s_so_far.apply(v) for k, v in env.items()}
            s4, else_type = self.infer(env2, expr.else_br)
            s_so_far = s4.compose(s_so_far)

            s5 = unify(s_so_far.apply(then_type), s_so_far.apply(else_type))
            return s5.compose(s_so_far), s5.apply(s_so_far.apply(then_type))

        if isinstance(expr, EBinOp):
            return self._infer_binop(env, expr)

        raise TypeError(f"Unknown expression type: {type(expr)}")

    def _infer_binop(
        self, env: dict[str, Type], expr: EBinOp
    ) -> tuple[Substitution, Type]:
        s1, left_type = self.infer(env, expr.left)
        env1 = {k: s1.apply(v) for k, v in env.items()}
        s2, right_type = self.infer(env1, expr.right)

        if expr.op in ("+", "-", "*", "/", "%"):
            s3 = unify(s2.apply(left_type), TInt())
            s4 = unify(s3.apply(right_type), TInt())
            return s4.compose(s3).compose(s2).compose(s1), TInt()

        if expr.op in ("==", "!="):
            s3 = unify(s2.apply(left_type), s2.apply(right_type))
            return s3.compose(s2).compose(s1), TBool()

        if expr.op in ("<", ">", "<=", ">="):
            s3 = unify(s2.apply(left_type), TInt())
            s4 = unify(s3.apply(right_type), TInt())
            return s4.compose(s3).compose(s2).compose(s1), TBool()

        if expr.op in ("&&", "||"):
            s3 = unify(s2.apply(left_type), TBool())
            s4 = unify(s3.apply(right_type), TBool())
            return s4.compose(s3).compose(s2).compose(s1), TBool()

        raise TypeError(f"Unknown operator: {expr.op}")


def format_type(ty: Type) -> str:
    if isinstance(ty, TInt):
        return "int"
    if isinstance(ty, TBool):
        return "bool"
    if isinstance(ty, TVar):
        return ty.name
    if isinstance(ty, TFun):
        param = format_type(ty.param)
        ret = format_type(ty.ret)
        if isinstance(ty.param, TFun):
            return f"({param}) -> {ret}"
        return f"{param} -> {ret}"
    if isinstance(ty, TForAll):
        body = format_type(ty.body)
        vars_str = " ".join(ty.vars)
        return f"forall {vars_str}. {body}"
    return str(ty)


def infer_type(expr: Expr) -> str:
    inferencer = TypeInferencer()
    sub, ty = inferencer.infer({}, expr)
    return format_type(sub.apply(ty))


# === Tests ===

def test_basic_inference():
    # Integer literal
    assert infer_type(EInt(42)) == "int"

    # Boolean literal
    assert infer_type(EBool(True)) == "bool"

    # Arithmetic
    assert infer_type(EBinOp("+", EInt(1), EInt(2))) == "int"

    # Comparison
    assert infer_type(EBinOp("<", EInt(1), EInt(2))) == "bool"

    print("Basic inference tests passed")


def test_function_inference():
    # Identity function: \x -> x  should infer  t0 -> t0
    identity = ELam("x", EVar("x"))
    ty = infer_type(identity)
    assert "->" in ty, f"Identity should be a function type, got {ty}"
    print(f"Identity function: {ty}")

    # Constant function: \x -> \y -> x  should infer  t0 -> t1 -> t0
    constant = ELam("x", ELam("y", EVar("x")))
    ty = infer_type(constant)
    print(f"Constant function: {ty}")


def test_let_polymorphism():
    # let id = \x -> x in (id 1, id true)
    # Without let-polymorphism, this would fail because id
    # would be monomorphically typed as either int->int or bool->bool.
    # With HM, id gets type forall a. a -> a, so both uses work.

    # Simulated as: let id = \x -> x in id 1
    expr = ELet("id", ELam("x", EVar("x")), EApp(EVar("id"), EInt(42)))
    ty = infer_type(expr)
    assert ty == "int", f"Expected int, got {ty}"

    # let id = \x -> x in id true
    expr2 = ELet("id", ELam("x", EVar("x")), EApp(EVar("id"), EBool(True)))
    ty2 = infer_type(expr2)
    assert ty2 == "bool", f"Expected bool, got {ty2}"

    print("Let-polymorphism test passed")


def test_type_errors():
    # if 42 then 1 else 2 -- condition must be bool
    try:
        infer_type(EIf(EInt(42), EInt(1), EInt(2)))
        assert False, "Should have raised TypeError"
    except TypeError as e:
        print(f"Correctly caught type error: {e}")

    # 1 + true -- operands must be int
    try:
        infer_type(EBinOp("+", EInt(1), EBool(True)))
        assert False, "Should have raised TypeError"
    except TypeError as e:
        print(f"Correctly caught type error: {e}")


if __name__ == "__main__":
    test_basic_inference()
    test_function_inference()
    test_let_polymorphism()
    test_type_errors()
    print("\nAll type inference tests passed!")
```

## Key Takeaways

- **Hindley-Milner type inference** infers the most general type for any expression without annotations — it's both complete and decidable, a rare combination in type theory
- **Unification** (Robinson's algorithm) is the core operation: it finds a substitution that makes two types equal, propagating type information bidirectionally through the expression tree
- **Let-polymorphism** is what makes HM practical: without it, a function like `id = \x -> x` could only be used at one type per scope; with it, each use site gets fresh type variables
- The **occurs check** prevents infinite types (like `a = a -> int`) which would cause the algorithm to loop forever — this is why the self-application combinator `\x -> x x` is untypable
- Production type systems (TypeScript, Rust, Kotlin) extend HM with **subtyping**, **row polymorphism**, and **GADTs** — each extension adds expressiveness but makes inference harder or incomplete
"""
    ),
    (
        "compilers/code-generation",
        "Explain compiler backend code generation including intermediate representation design, register allocation with graph coloring, instruction selection, and provide a Python implementation of a simple compiler backend that takes an AST, generates stack-based bytecode, and includes a virtual machine to execute it with support for arithmetic, comparisons, function calls, and control flow.",
        r"""# Compiler Backend: Code Generation & Virtual Machine

## From AST to Executable Code

The compiler backend transforms the AST (from the frontend) into executable code. Modern compilers use an **intermediate representation** (IR) as a bridge: the frontend produces IR, the backend consumes IR. This separation means N frontends and M backends only need N+M implementations instead of N*M.

We'll build a **stack-based bytecode compiler and VM** — the same architecture used by Python (CPython), Java (JVM), Lua, and WebAssembly. Stack machines are simpler to target than register machines because you don't need register allocation.

## Bytecode Design

```python
# Complete bytecode compiler and virtual machine
from __future__ import annotations

import dataclasses
import enum
import struct
from typing import Any, Optional


class OpCode(enum.IntEnum):
    # Stack manipulation
    PUSH_INT = 0x01      # push integer constant
    PUSH_BOOL = 0x02     # push boolean constant
    PUSH_STR = 0x03      # push string constant
    POP = 0x04           # discard top of stack

    # Arithmetic (pop 2, push 1)
    ADD = 0x10
    SUB = 0x11
    MUL = 0x12
    DIV = 0x13
    MOD = 0x14
    NEG = 0x15           # unary negation

    # Comparison (pop 2, push bool)
    EQ = 0x20
    NEQ = 0x21
    LT = 0x22
    GT = 0x23
    LTE = 0x24
    GTE = 0x25

    # Logic
    AND = 0x30
    OR = 0x31
    NOT = 0x32

    # Variables
    LOAD_LOCAL = 0x40    # push local variable
    STORE_LOCAL = 0x41   # pop and store to local
    LOAD_GLOBAL = 0x42   # push global variable
    STORE_GLOBAL = 0x43  # pop and store to global

    # Control flow
    JUMP = 0x50          # unconditional jump
    JUMP_IF_FALSE = 0x51 # conditional jump
    JUMP_IF_TRUE = 0x52  # conditional jump

    # Functions
    CALL = 0x60          # call function with N args
    RETURN = 0x61        # return from function
    PUSH_CLOSURE = 0x62  # push function reference

    # VM control
    HALT = 0xFF
    PRINT = 0xFE         # debug: print top of stack


@dataclasses.dataclass
class Instruction:
    opcode: OpCode
    operand: Any = None  # immediate value or address

    def __repr__(self) -> str:
        if self.operand is not None:
            return f"{self.opcode.name} {self.operand}"
        return self.opcode.name


@dataclasses.dataclass
class FunctionChunk:
    # Compiled function bytecode
    name: str
    arity: int  # number of parameters
    instructions: list[Instruction]
    locals_count: int
    constants: list[Any]


class Compiler:
    # Compiles AST to stack-based bytecode.
    #
    # The compiler walks the AST and emits instructions that, when
    # executed on a stack machine, produce the correct result.
    #
    # Key insight: expressions are compiled to leave exactly one
    # value on the stack. Binary operators pop two values and push
    # one result. This invariant makes code generation straightforward.
    #
    # For control flow, we use forward and backward jumps with
    # patch-up: emit a JUMP with a placeholder address, then
    # come back and fill in the real address once we know it.

    def __init__(self) -> None:
        self.instructions: list[Instruction] = []
        self.constants: list[Any] = []
        self.locals: dict[str, int] = {}  # name -> stack slot
        self.functions: dict[str, FunctionChunk] = {}
        self._next_local = 0

    def _emit(self, opcode: OpCode, operand: Any = None) -> int:
        # Emit an instruction and return its index (for patching)
        idx = len(self.instructions)
        self.instructions.append(Instruction(opcode, operand))
        return idx

    def _add_constant(self, value: Any) -> int:
        if value in self.constants:
            return self.constants.index(value)
        self.constants.append(value)
        return len(self.constants) - 1

    def _patch_jump(self, instruction_idx: int) -> None:
        # Patch a forward jump to point to the current position
        self.instructions[instruction_idx].operand = len(self.instructions)

    def _declare_local(self, name: str) -> int:
        slot = self._next_local
        self.locals[name] = slot
        self._next_local += 1
        return slot

    def compile_program(self, statements: list[Any]) -> FunctionChunk:
        # Compile a list of statements into a function chunk
        for stmt in statements:
            self.compile_node(stmt)
        self._emit(OpCode.HALT)

        return FunctionChunk(
            name="<main>",
            arity=0,
            instructions=self.instructions,
            locals_count=self._next_local,
            constants=self.constants,
        )

    def compile_node(self, node: Any) -> None:
        # Dispatch to the appropriate compilation method
        # Using duck-typing based on class name for simplicity
        node_type = type(node).__name__

        if node_type == "IntLiteral":
            self._emit(OpCode.PUSH_INT, node.value)

        elif node_type == "BoolLiteral":
            self._emit(OpCode.PUSH_BOOL, node.value)

        elif node_type == "StringLiteral":
            idx = self._add_constant(node.value)
            self._emit(OpCode.PUSH_STR, idx)

        elif node_type == "Identifier":
            if node.name in self.locals:
                self._emit(OpCode.LOAD_LOCAL, self.locals[node.name])
            else:
                idx = self._add_constant(node.name)
                self._emit(OpCode.LOAD_GLOBAL, idx)

        elif node_type == "BinaryOp":
            self.compile_node(node.left)
            self.compile_node(node.right)
            op_map = {
                "+": OpCode.ADD, "-": OpCode.SUB,
                "*": OpCode.MUL, "/": OpCode.DIV,
                "%": OpCode.MOD, "==": OpCode.EQ,
                "!=": OpCode.NEQ, "<": OpCode.LT,
                ">": OpCode.GT, "<=": OpCode.LTE,
                ">=": OpCode.GTE, "&&": OpCode.AND,
                "||": OpCode.OR,
            }
            if node.op in op_map:
                self._emit(op_map[node.op])
            else:
                raise ValueError(f"Unknown operator: {node.op}")

        elif node_type == "UnaryOp":
            self.compile_node(node.operand)
            if node.op == "-":
                self._emit(OpCode.NEG)
            elif node.op == "!":
                self._emit(OpCode.NOT)

        elif node_type == "LetStmt":
            self.compile_node(node.value)
            slot = self._declare_local(node.name)
            self._emit(OpCode.STORE_LOCAL, slot)

        elif node_type == "IfExpr":
            # Compile: if (cond) { then } else { else }
            #
            # Bytecode pattern:
            #   <compile condition>
            #   JUMP_IF_FALSE else_label
            #   <compile then branch>
            #   JUMP end_label
            # else_label:
            #   <compile else branch>
            # end_label:
            self.compile_node(node.condition)
            else_jump = self._emit(OpCode.JUMP_IF_FALSE, 0)  # placeholder

            # Then branch
            if hasattr(node.then_branch, "statements"):
                for s in node.then_branch.statements:
                    self.compile_node(s)
            else:
                self.compile_node(node.then_branch)

            end_jump = self._emit(OpCode.JUMP, 0)  # placeholder
            self._patch_jump(else_jump)

            # Else branch
            if node.else_branch is not None:
                if hasattr(node.else_branch, "statements"):
                    for s in node.else_branch.statements:
                        self.compile_node(s)
                else:
                    self.compile_node(node.else_branch)

            self._patch_jump(end_jump)

        elif node_type == "CallExpr":
            # Push arguments, then call
            for arg in node.args:
                self.compile_node(arg)
            self.compile_node(node.callee)
            self._emit(OpCode.CALL, len(node.args))

        elif node_type == "ReturnStmt":
            if node.value is not None:
                self.compile_node(node.value)
            self._emit(OpCode.RETURN)

        elif node_type == "FnDef":
            # Compile function body into a separate chunk
            old_instructions = self.instructions
            old_locals = self.locals
            old_next_local = self._next_local

            self.instructions = []
            self.locals = {}
            self._next_local = 0

            # Declare parameters as locals
            for param_name, _ in node.params:
                self._declare_local(param_name)

            for stmt in node.body:
                self.compile_node(stmt)

            # Implicit return if no explicit return
            if not self.instructions or self.instructions[-1].opcode != OpCode.RETURN:
                self._emit(OpCode.PUSH_INT, 0)  # default return value
                self._emit(OpCode.RETURN)

            chunk = FunctionChunk(
                name=node.name,
                arity=len(node.params),
                instructions=self.instructions,
                locals_count=self._next_local,
                constants=self.constants,
            )
            self.functions[node.name] = chunk

            # Restore state
            self.instructions = old_instructions
            self.locals = old_locals
            self._next_local = old_next_local

            # Store function reference as global
            idx = self._add_constant(node.name)
            self._emit(OpCode.PUSH_CLOSURE, idx)
            self._emit(OpCode.STORE_GLOBAL, idx)

        else:
            raise ValueError(f"Cannot compile: {node_type}")


# === Virtual Machine ===

@dataclasses.dataclass
class CallFrame:
    # A function call frame on the call stack
    chunk: FunctionChunk
    ip: int  # instruction pointer
    bp: int  # base pointer (start of locals on stack)


class VirtualMachine:
    # Stack-based virtual machine that executes bytecode.
    #
    # Architecture: a value stack for computation, a call stack
    # for function calls, and globals for top-level bindings.
    #
    # Performance note: real VMs like CPython and LuaJIT use
    # computed gotos or threaded code instead of a switch statement
    # for 2-5x better dispatch performance. Our switch-based
    # approach is clearer for educational purposes.

    MAX_STACK = 1024
    MAX_FRAMES = 256

    def __init__(self) -> None:
        self.stack: list[Any] = []
        self.frames: list[CallFrame] = []
        self.globals: dict[str, Any] = {}
        self.functions: dict[str, FunctionChunk] = {}
        self.output: list[str] = []

    def run(self, main_chunk: FunctionChunk, functions: dict[str, FunctionChunk]) -> Any:
        self.functions = functions

        # Push main frame
        self.frames.append(CallFrame(
            chunk=main_chunk, ip=0, bp=0,
        ))

        # Allocate space for main's locals
        for _ in range(main_chunk.locals_count):
            self.stack.append(None)

        return self._execute()

    def _execute(self) -> Any:
        while self.frames:
            frame = self.frames[-1]
            chunk = frame.chunk

            if frame.ip >= len(chunk.instructions):
                break

            inst = chunk.instructions[frame.ip]
            frame.ip += 1

            op = inst.opcode

            if op == OpCode.PUSH_INT:
                self.stack.append(inst.operand)

            elif op == OpCode.PUSH_BOOL:
                self.stack.append(inst.operand)

            elif op == OpCode.PUSH_STR:
                self.stack.append(chunk.constants[inst.operand])

            elif op == OpCode.POP:
                self.stack.pop()

            elif op == OpCode.ADD:
                b, a = self.stack.pop(), self.stack.pop()
                self.stack.append(a + b)

            elif op == OpCode.SUB:
                b, a = self.stack.pop(), self.stack.pop()
                self.stack.append(a - b)

            elif op == OpCode.MUL:
                b, a = self.stack.pop(), self.stack.pop()
                self.stack.append(a * b)

            elif op == OpCode.DIV:
                b, a = self.stack.pop(), self.stack.pop()
                if b == 0:
                    raise RuntimeError("Division by zero")
                self.stack.append(a // b)

            elif op == OpCode.MOD:
                b, a = self.stack.pop(), self.stack.pop()
                self.stack.append(a % b)

            elif op == OpCode.NEG:
                self.stack.append(-self.stack.pop())

            elif op == OpCode.EQ:
                b, a = self.stack.pop(), self.stack.pop()
                self.stack.append(a == b)

            elif op == OpCode.NEQ:
                b, a = self.stack.pop(), self.stack.pop()
                self.stack.append(a != b)

            elif op == OpCode.LT:
                b, a = self.stack.pop(), self.stack.pop()
                self.stack.append(a < b)

            elif op == OpCode.GT:
                b, a = self.stack.pop(), self.stack.pop()
                self.stack.append(a > b)

            elif op == OpCode.LTE:
                b, a = self.stack.pop(), self.stack.pop()
                self.stack.append(a <= b)

            elif op == OpCode.GTE:
                b, a = self.stack.pop(), self.stack.pop()
                self.stack.append(a >= b)

            elif op == OpCode.AND:
                b, a = self.stack.pop(), self.stack.pop()
                self.stack.append(a and b)

            elif op == OpCode.OR:
                b, a = self.stack.pop(), self.stack.pop()
                self.stack.append(a or b)

            elif op == OpCode.NOT:
                self.stack.append(not self.stack.pop())

            elif op == OpCode.LOAD_LOCAL:
                self.stack.append(self.stack[frame.bp + inst.operand])

            elif op == OpCode.STORE_LOCAL:
                self.stack[frame.bp + inst.operand] = self.stack.pop()

            elif op == OpCode.LOAD_GLOBAL:
                name = chunk.constants[inst.operand]
                self.stack.append(self.globals.get(name))

            elif op == OpCode.STORE_GLOBAL:
                name = chunk.constants[inst.operand]
                self.globals[name] = self.stack.pop()

            elif op == OpCode.PUSH_CLOSURE:
                name = chunk.constants[inst.operand]
                self.stack.append(("function", name))

            elif op == OpCode.JUMP:
                frame.ip = inst.operand

            elif op == OpCode.JUMP_IF_FALSE:
                if not self.stack.pop():
                    frame.ip = inst.operand

            elif op == OpCode.JUMP_IF_TRUE:
                if self.stack.pop():
                    frame.ip = inst.operand

            elif op == OpCode.CALL:
                num_args = inst.operand
                callee = self.stack.pop()

                if isinstance(callee, tuple) and callee[0] == "function":
                    func_name = callee[1]
                    if func_name not in self.functions:
                        raise RuntimeError(f"Undefined function: {func_name}")

                    func_chunk = self.functions[func_name]
                    if func_chunk.arity != num_args:
                        raise RuntimeError(
                            f"{func_name} expects {func_chunk.arity} args, "
                            f"got {num_args}"
                        )

                    # Set up new frame
                    new_bp = len(self.stack) - num_args
                    # Extend stack for additional locals
                    extra_locals = func_chunk.locals_count - num_args
                    for _ in range(extra_locals):
                        self.stack.append(None)

                    self.frames.append(CallFrame(
                        chunk=func_chunk, ip=0, bp=new_bp,
                    ))
                else:
                    raise RuntimeError(f"Cannot call: {callee}")

            elif op == OpCode.RETURN:
                result = self.stack.pop() if self.stack else None
                returning_frame = self.frames.pop()
                # Clean up locals
                while len(self.stack) > returning_frame.bp:
                    self.stack.pop()
                self.stack.append(result)

            elif op == OpCode.PRINT:
                value = self.stack[-1]  # peek, don't pop
                self.output.append(str(value))

            elif op == OpCode.HALT:
                break

        return self.stack[-1] if self.stack else None


def test_vm_arithmetic():
    # Test: 2 + 3 * 4 = 14
    compiler = Compiler()
    compiler._emit(OpCode.PUSH_INT, 2)
    compiler._emit(OpCode.PUSH_INT, 3)
    compiler._emit(OpCode.PUSH_INT, 4)
    compiler._emit(OpCode.MUL)
    compiler._emit(OpCode.ADD)
    compiler._emit(OpCode.HALT)

    chunk = FunctionChunk("test", 0, compiler.instructions, 0, [])
    vm = VirtualMachine()
    result = vm.run(chunk, {})
    assert result == 14, f"Expected 14, got {result}"
    print("Arithmetic test passed: 2 + 3 * 4 = 14")


def test_vm_control_flow():
    # Test: if true then 42 else 0
    compiler = Compiler()
    compiler._emit(OpCode.PUSH_BOOL, True)
    else_jump = compiler._emit(OpCode.JUMP_IF_FALSE, 0)
    compiler._emit(OpCode.PUSH_INT, 42)
    end_jump = compiler._emit(OpCode.JUMP, 0)
    compiler._patch_jump(else_jump)
    compiler._emit(OpCode.PUSH_INT, 0)
    compiler._patch_jump(end_jump)
    compiler._emit(OpCode.HALT)

    chunk = FunctionChunk("test", 0, compiler.instructions, 0, [])
    vm = VirtualMachine()
    result = vm.run(chunk, {})
    assert result == 42, f"Expected 42, got {result}"
    print("Control flow test passed: if true then 42")


def test_vm_variables():
    # Test: let x = 10; let y = 20; x + y = 30
    compiler = Compiler()
    compiler._emit(OpCode.PUSH_INT, 10)
    compiler._emit(OpCode.STORE_LOCAL, 0)
    compiler._emit(OpCode.PUSH_INT, 20)
    compiler._emit(OpCode.STORE_LOCAL, 1)
    compiler._emit(OpCode.LOAD_LOCAL, 0)
    compiler._emit(OpCode.LOAD_LOCAL, 1)
    compiler._emit(OpCode.ADD)
    compiler._emit(OpCode.HALT)

    chunk = FunctionChunk("test", 0, compiler.instructions, 2, [])
    vm = VirtualMachine()
    # Pre-allocate locals
    vm.stack = [None, None]
    vm.frames = [CallFrame(chunk, 0, 0)]
    result = vm._execute()
    assert result == 30, f"Expected 30, got {result}"
    print("Variable test passed: x + y = 30")


if __name__ == "__main__":
    test_vm_arithmetic()
    test_vm_control_flow()
    test_vm_variables()
    print("\nAll VM tests passed!")
```

## Key Takeaways

- **Stack-based bytecode** is simpler to generate than register-based because you don't need register allocation — expressions naturally push and pop values in the correct order
- **Jump patching** handles forward references in control flow: emit a jump with a placeholder, then patch the address once the target is known — this is the standard technique used by all bytecode compilers
- The **call frame** (instruction pointer + base pointer) enables function calls by saving and restoring execution context — this is the same mechanism used by hardware call stacks
- **Production VMs** add: garbage collection, JIT compilation (converting hot bytecode to native code), inline caching (for dynamic dispatch), and escape analysis (for stack allocation) — each is a separate area of study
- Understanding bytecode compilation makes you better at debugging performance issues in Python, Java, and JavaScript because you can reason about what the VM is actually doing with your code
"""
    ),
]
