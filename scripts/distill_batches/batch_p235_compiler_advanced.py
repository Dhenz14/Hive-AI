"""Compiler and interpreter patterns — recursive descent parser, bytecode VM, SSA optimization, garbage collection."""

PAIRS = [
    (
        "compilers/recursive-descent-parser",
        "Build a recursive descent parser for an expression language with operator precedence, function calls, if/else, and detailed error reporting with source locations.",
        '''Recursive descent parser with precedence climbing and error recovery:

```python
# lexer.py — Tokenizer with source location tracking
from __future__ import annotations
from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterator


class TokenType(Enum):
    # Literals
    INT = auto()
    FLOAT = auto()
    STRING = auto()
    IDENT = auto()
    BOOL = auto()

    # Operators
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    PERCENT = auto()
    BANG = auto()
    EQ = auto()
    NEQ = auto()
    LT = auto()
    GT = auto()
    LTE = auto()
    GTE = auto()
    AND = auto()
    OR = auto()
    ASSIGN = auto()

    # Delimiters
    LPAREN = auto()
    RPAREN = auto()
    LBRACE = auto()
    RBRACE = auto()
    COMMA = auto()
    SEMICOLON = auto()
    COLON = auto()
    ARROW = auto()

    # Keywords
    LET = auto()
    FN = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    RETURN = auto()
    TRUE = auto()
    FALSE = auto()

    # Special
    EOF = auto()
    ERROR = auto()


@dataclass(frozen=True)
class SourceLoc:
    line: int
    column: int
    offset: int

    def __str__(self) -> str:
        return f"{self.line}:{self.column}"


@dataclass
class Token:
    type: TokenType
    value: str
    loc: SourceLoc

    def __repr__(self) -> str:
        return f"Token({self.type.name}, {self.value!r}, {self.loc})"


KEYWORDS: dict[str, TokenType] = {
    "let": TokenType.LET,
    "fn": TokenType.FN,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "while": TokenType.WHILE,
    "return": TokenType.RETURN,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
}


class Lexer:
    """Tokenizer with line/column tracking and error tokens."""

    def __init__(self, source: str):
        self.source = source
        self.pos = 0
        self.line = 1
        self.col = 1

    def _loc(self) -> SourceLoc:
        return SourceLoc(self.line, self.col, self.pos)

    def _peek(self) -> str:
        if self.pos >= len(self.source):
            return "\0"
        return self.source[self.pos]

    def _advance(self) -> str:
        ch = self.source[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _match(self, expected: str) -> bool:
        if self.pos < len(self.source) and self.source[self.pos] == expected:
            self._advance()
            return True
        return False

    def tokenize(self) -> Iterator[Token]:
        while self.pos < len(self.source):
            self._skip_whitespace()
            if self.pos >= len(self.source):
                break

            loc = self._loc()
            ch = self._advance()

            # Single-char tokens
            simple = {
                "(": TokenType.LPAREN, ")": TokenType.RPAREN,
                "{": TokenType.LBRACE, "}": TokenType.RBRACE,
                ",": TokenType.COMMA, ";": TokenType.SEMICOLON,
                ":": TokenType.COLON, "+": TokenType.PLUS,
                "*": TokenType.STAR, "/": TokenType.SLASH,
                "%": TokenType.PERCENT,
            }
            if ch in simple:
                yield Token(simple[ch], ch, loc)
                continue

            # Two-char tokens
            if ch == "-":
                if self._match(">"):
                    yield Token(TokenType.ARROW, "->", loc)
                else:
                    yield Token(TokenType.MINUS, "-", loc)
                continue
            if ch == "=":
                if self._match("="):
                    yield Token(TokenType.EQ, "==", loc)
                else:
                    yield Token(TokenType.ASSIGN, "=", loc)
                continue
            if ch == "!":
                if self._match("="):
                    yield Token(TokenType.NEQ, "!=", loc)
                else:
                    yield Token(TokenType.BANG, "!", loc)
                continue
            if ch == "<":
                if self._match("="):
                    yield Token(TokenType.LTE, "<=", loc)
                else:
                    yield Token(TokenType.LT, "<", loc)
                continue
            if ch == ">":
                if self._match("="):
                    yield Token(TokenType.GTE, ">=", loc)
                else:
                    yield Token(TokenType.GT, ">", loc)
                continue
            if ch == "&" and self._match("&"):
                yield Token(TokenType.AND, "&&", loc)
                continue
            if ch == "|" and self._match("|"):
                yield Token(TokenType.OR, "||", loc)
                continue

            # Numbers
            if ch.isdigit():
                yield self._read_number(ch, loc)
                continue

            # Strings
            if ch == '"':
                yield self._read_string(loc)
                continue

            # Identifiers and keywords
            if ch.isalpha() or ch == "_":
                yield self._read_identifier(ch, loc)
                continue

            yield Token(TokenType.ERROR, ch, loc)

        yield Token(TokenType.EOF, "", self._loc())

    def _skip_whitespace(self) -> None:
        while self.pos < len(self.source):
            ch = self.source[self.pos]
            if ch in " \t\r\n":
                self._advance()
            elif ch == "/" and self.pos + 1 < len(self.source) and self.source[self.pos + 1] == "/":
                while self.pos < len(self.source) and self.source[self.pos] != "\n":
                    self._advance()
            else:
                break

    def _read_number(self, first: str, loc: SourceLoc) -> Token:
        result = first
        is_float = False
        while self.pos < len(self.source) and (self._peek().isdigit() or self._peek() == "."):
            if self._peek() == ".":
                if is_float:
                    break
                is_float = True
            result += self._advance()
        return Token(TokenType.FLOAT if is_float else TokenType.INT, result, loc)

    def _read_string(self, loc: SourceLoc) -> Token:
        result = ""
        while self.pos < len(self.source) and self._peek() != '"':
            if self._peek() == "\\":
                self._advance()
                esc = self._advance()
                escapes = {"n": "\n", "t": "\t", "\\": "\\", '"': '"'}
                result += escapes.get(esc, esc)
            else:
                result += self._advance()
        if self.pos < len(self.source):
            self._advance()  # closing quote
        return Token(TokenType.STRING, result, loc)

    def _read_identifier(self, first: str, loc: SourceLoc) -> Token:
        result = first
        while self.pos < len(self.source) and (self._peek().isalnum() or self._peek() == "_"):
            result += self._advance()
        tt = KEYWORDS.get(result, TokenType.IDENT)
        return Token(tt, result, loc)
```

```python
# ast_nodes.py — AST node definitions
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from lexer import SourceLoc


@dataclass
class ASTNode:
    loc: SourceLoc


# Expressions
@dataclass
class IntLiteral(ASTNode):
    value: int

@dataclass
class FloatLiteral(ASTNode):
    value: float

@dataclass
class StringLiteral(ASTNode):
    value: str

@dataclass
class BoolLiteral(ASTNode):
    value: bool

@dataclass
class Identifier(ASTNode):
    name: str

@dataclass
class BinaryOp(ASTNode):
    op: str
    left: ASTNode
    right: ASTNode

@dataclass
class UnaryOp(ASTNode):
    op: str
    operand: ASTNode

@dataclass
class FuncCall(ASTNode):
    callee: ASTNode
    args: list[ASTNode]

@dataclass
class IfExpr(ASTNode):
    condition: ASTNode
    then_branch: Block
    else_branch: Block | None = None

# Statements
@dataclass
class LetStmt(ASTNode):
    name: str
    value: ASTNode
    type_annotation: str | None = None

@dataclass
class ReturnStmt(ASTNode):
    value: ASTNode | None = None

@dataclass
class ExprStmt(ASTNode):
    expr: ASTNode

@dataclass
class Block(ASTNode):
    statements: list[ASTNode]

@dataclass
class FuncDef(ASTNode):
    name: str
    params: list[tuple[str, str]]  # (name, type)
    return_type: str | None
    body: Block

@dataclass
class WhileStmt(ASTNode):
    condition: ASTNode
    body: Block

@dataclass
class Program(ASTNode):
    declarations: list[ASTNode]
```

```python
# parser.py — Recursive descent parser with Pratt precedence
from __future__ import annotations
from lexer import Lexer, Token, TokenType, SourceLoc
from ast_nodes import *


class ParseError(Exception):
    def __init__(self, message: str, loc: SourceLoc, source_line: str = ""):
        self.message = message
        self.loc = loc
        self.source_line = source_line
        super().__init__(f"{loc}: {message}")


class Parser:
    """
    Recursive descent parser with Pratt-style operator precedence.

    Grammar (simplified):
        program     -> declaration* EOF
        declaration -> func_def | statement
        func_def    -> "fn" IDENT "(" params ")" ("->" type)? block
        statement   -> let_stmt | return_stmt | while_stmt | expr_stmt
        let_stmt    -> "let" IDENT (":" type)? "=" expression ";"
        expr_stmt   -> expression ";"
        expression  -> assignment
        assignment  -> IDENT "=" assignment | logic_or
        logic_or    -> logic_and ("||" logic_and)*
        logic_and   -> equality ("&&" equality)*
        equality    -> comparison (("==" | "!=") comparison)*
        comparison  -> addition (("<" | ">" | "<=" | ">=") addition)*
        addition    -> multiply (("+" | "-") multiply)*
        multiply    -> unary (("*" | "/" | "%") unary)*
        unary       -> ("!" | "-") unary | call
        call        -> primary ("(" arguments ")")*
        primary     -> INT | FLOAT | STRING | BOOL | IDENT | "(" expression ")" | if_expr
    """

    # Operator precedence levels (Pratt-style)
    PRECEDENCE = {
        TokenType.OR: 1,
        TokenType.AND: 2,
        TokenType.EQ: 3, TokenType.NEQ: 3,
        TokenType.LT: 4, TokenType.GT: 4, TokenType.LTE: 4, TokenType.GTE: 4,
        TokenType.PLUS: 5, TokenType.MINUS: 5,
        TokenType.STAR: 6, TokenType.SLASH: 6, TokenType.PERCENT: 6,
    }

    BINARY_OPS = {
        TokenType.PLUS: "+", TokenType.MINUS: "-",
        TokenType.STAR: "*", TokenType.SLASH: "/", TokenType.PERCENT: "%",
        TokenType.EQ: "==", TokenType.NEQ: "!=",
        TokenType.LT: "<", TokenType.GT: ">",
        TokenType.LTE: "<=", TokenType.GTE: ">=",
        TokenType.AND: "&&", TokenType.OR: "||",
    }

    def __init__(self, source: str):
        self.source = source
        self.source_lines = source.splitlines()
        self.tokens: list[Token] = list(Lexer(source).tokenize())
        self.pos = 0
        self.errors: list[ParseError] = []

    def _current(self) -> Token:
        return self.tokens[self.pos] if self.pos < len(self.tokens) else self.tokens[-1]

    def _peek(self) -> Token:
        return self._current()

    def _advance(self) -> Token:
        tok = self._current()
        if tok.type != TokenType.EOF:
            self.pos += 1
        return tok

    def _check(self, *types: TokenType) -> bool:
        return self._current().type in types

    def _match(self, *types: TokenType) -> Token | None:
        if self._current().type in types:
            return self._advance()
        return None

    def _expect(self, tt: TokenType, message: str) -> Token:
        if self._current().type == tt:
            return self._advance()
        self._error(message)
        return self._current()  # Continue parsing

    def _error(self, message: str) -> None:
        tok = self._current()
        line_text = self.source_lines[tok.loc.line - 1] if tok.loc.line <= len(self.source_lines) else ""
        err = ParseError(message, tok.loc, line_text)
        self.errors.append(err)

    def parse(self) -> Program:
        """Parse the entire program."""
        declarations: list[ASTNode] = []
        while not self._check(TokenType.EOF):
            try:
                declarations.append(self._declaration())
            except ParseError:
                self._synchronize()
        return Program(loc=SourceLoc(1, 1, 0), declarations=declarations)

    def _synchronize(self) -> None:
        """Error recovery: skip to next statement boundary."""
        self._advance()
        while not self._check(TokenType.EOF):
            if self.tokens[self.pos - 1].type == TokenType.SEMICOLON:
                return
            if self._check(TokenType.FN, TokenType.LET, TokenType.IF,
                           TokenType.WHILE, TokenType.RETURN):
                return
            self._advance()

    def _declaration(self) -> ASTNode:
        if self._check(TokenType.FN):
            return self._func_def()
        return self._statement()

    def _func_def(self) -> FuncDef:
        loc = self._advance().loc  # consume 'fn'
        name = self._expect(TokenType.IDENT, "Expected function name").value
        self._expect(TokenType.LPAREN, "Expected '(' after function name")
        params = self._param_list()
        self._expect(TokenType.RPAREN, "Expected ')' after parameters")

        return_type = None
        if self._match(TokenType.ARROW):
            return_type = self._expect(TokenType.IDENT, "Expected return type").value

        body = self._block()
        return FuncDef(loc=loc, name=name, params=params,
                      return_type=return_type, body=body)

    def _param_list(self) -> list[tuple[str, str]]:
        params: list[tuple[str, str]] = []
        if not self._check(TokenType.RPAREN):
            while True:
                name = self._expect(TokenType.IDENT, "Expected parameter name").value
                self._expect(TokenType.COLON, "Expected ':' after parameter name")
                ptype = self._expect(TokenType.IDENT, "Expected parameter type").value
                params.append((name, ptype))
                if not self._match(TokenType.COMMA):
                    break
        return params

    def _block(self) -> Block:
        loc = self._expect(TokenType.LBRACE, "Expected '{'").loc
        stmts: list[ASTNode] = []
        while not self._check(TokenType.RBRACE, TokenType.EOF):
            stmts.append(self._statement())
        self._expect(TokenType.RBRACE, "Expected '}'")
        return Block(loc=loc, statements=stmts)

    def _statement(self) -> ASTNode:
        if self._check(TokenType.LET):
            return self._let_stmt()
        if self._check(TokenType.RETURN):
            return self._return_stmt()
        if self._check(TokenType.WHILE):
            return self._while_stmt()
        return self._expr_stmt()

    def _let_stmt(self) -> LetStmt:
        loc = self._advance().loc
        name = self._expect(TokenType.IDENT, "Expected variable name").value
        type_ann = None
        if self._match(TokenType.COLON):
            type_ann = self._expect(TokenType.IDENT, "Expected type").value
        self._expect(TokenType.ASSIGN, "Expected '='")
        value = self._expression()
        self._expect(TokenType.SEMICOLON, "Expected ';'")
        return LetStmt(loc=loc, name=name, value=value, type_annotation=type_ann)

    def _return_stmt(self) -> ReturnStmt:
        loc = self._advance().loc
        value = None
        if not self._check(TokenType.SEMICOLON):
            value = self._expression()
        self._expect(TokenType.SEMICOLON, "Expected ';'")
        return ReturnStmt(loc=loc, value=value)

    def _while_stmt(self) -> WhileStmt:
        loc = self._advance().loc
        condition = self._expression()
        body = self._block()
        return WhileStmt(loc=loc, condition=condition, body=body)

    def _expr_stmt(self) -> ExprStmt:
        expr = self._expression()
        self._expect(TokenType.SEMICOLON, "Expected ';'")
        return ExprStmt(loc=expr.loc, expr=expr)

    # --- Pratt-style expression parsing ---

    def _expression(self) -> ASTNode:
        return self._parse_precedence(0)

    def _parse_precedence(self, min_prec: int) -> ASTNode:
        left = self._unary()

        while self._current().type in self.PRECEDENCE:
            prec = self.PRECEDENCE[self._current().type]
            if prec < min_prec:
                break

            op_tok = self._advance()
            op_str = self.BINARY_OPS[op_tok.type]
            right = self._parse_precedence(prec + 1)  # Left-associative
            left = BinaryOp(loc=op_tok.loc, op=op_str, left=left, right=right)

        return left

    def _unary(self) -> ASTNode:
        if self._check(TokenType.BANG, TokenType.MINUS):
            op = self._advance()
            operand = self._unary()
            return UnaryOp(loc=op.loc, op=op.value, operand=operand)
        return self._call()

    def _call(self) -> ASTNode:
        expr = self._primary()
        while self._match(TokenType.LPAREN):
            args: list[ASTNode] = []
            if not self._check(TokenType.RPAREN):
                while True:
                    args.append(self._expression())
                    if not self._match(TokenType.COMMA):
                        break
            self._expect(TokenType.RPAREN, "Expected ')' after arguments")
            expr = FuncCall(loc=expr.loc, callee=expr, args=args)
        return expr

    def _primary(self) -> ASTNode:
        tok = self._current()

        if self._match(TokenType.INT):
            return IntLiteral(loc=tok.loc, value=int(tok.value))
        if self._match(TokenType.FLOAT):
            return FloatLiteral(loc=tok.loc, value=float(tok.value))
        if self._match(TokenType.STRING):
            return StringLiteral(loc=tok.loc, value=tok.value)
        if self._match(TokenType.TRUE):
            return BoolLiteral(loc=tok.loc, value=True)
        if self._match(TokenType.FALSE):
            return BoolLiteral(loc=tok.loc, value=False)
        if self._match(TokenType.IDENT):
            return Identifier(loc=tok.loc, name=tok.value)
        if self._match(TokenType.LPAREN):
            expr = self._expression()
            self._expect(TokenType.RPAREN, "Expected ')'")
            return expr
        if self._check(TokenType.IF):
            return self._if_expr()

        self._error(f"Unexpected token: {tok.value!r}")
        self._advance()
        return IntLiteral(loc=tok.loc, value=0)  # Error recovery

    def _if_expr(self) -> IfExpr:
        loc = self._advance().loc
        condition = self._expression()
        then_branch = self._block()
        else_branch = None
        if self._match(TokenType.ELSE):
            else_branch = self._block()
        return IfExpr(loc=loc, condition=condition,
                     then_branch=then_branch, else_branch=else_branch)


# Usage
source = """
fn fibonacci(n: int) -> int {
    if n <= 1 {
        return n;
    }
    return fibonacci(n - 1) + fibonacci(n - 2);
}

let result = fibonacci(10);
"""

parser = Parser(source)
ast = parser.parse()
if parser.errors:
    for err in parser.errors:
        print(f"Error at {err.loc}: {err.message}")
        if err.source_line:
            print(f"  {err.source_line}")
            print(f"  {' ' * (err.loc.column - 1)}^")
```

| Parsing Technique | Handles Left Recursion | Precedence | Error Recovery | Performance |
|---|---|---|---|---|
| Recursive descent | No (rewrite needed) | Manual/Pratt | Synchronization | O(N) |
| Pratt / precedence climbing | Yes | Table-driven | Good | O(N) |
| PEG (packrat) | No | Ordered alternatives | Limited | O(N) with memoization |
| LR(1) / LALR | Yes | Grammar-driven | Shift-reduce errors | O(N) |
| Earley | Yes | Grammar-driven | Full ambiguity | O(N^3) worst case |

Key patterns:
1. Pratt parsing uses a precedence table to handle operator priority without nested functions
2. `min_prec + 1` in recursive call gives left-associativity; `min_prec` gives right-associativity
3. Error recovery via synchronization skips tokens to the next statement boundary
4. Source locations on every token and AST node enable precise error messages
5. Separate lexer and parser phases simplify both implementations
6. Keywords are identified during lexing by checking an identifier against a keyword table'''
    ),
    (
        "compilers/bytecode-vm",
        "Build a bytecode compiler and stack-based virtual machine for a simple expression language with variables, functions, and control flow.",
        '''Bytecode compiler and stack-based VM:

```python
# bytecode.py — Instruction set definition
from enum import IntEnum, auto
from dataclasses import dataclass, field


class OpCode(IntEnum):
    """Stack-based bytecode instructions."""
    # Stack manipulation
    CONST = 0        # Push constant: CONST <index>
    POP = 1          # Pop top of stack
    DUP = 2          # Duplicate top of stack

    # Arithmetic (pop 2, push 1)
    ADD = 10
    SUB = 11
    MUL = 12
    DIV = 13
    MOD = 14
    NEG = 15         # Unary negate

    # Comparison (pop 2, push bool)
    EQ = 20
    NEQ = 21
    LT = 22
    GT = 23
    LTE = 24
    GTE = 25

    # Logic
    NOT = 30
    AND = 31
    OR = 32

    # Variables
    GET_LOCAL = 40   # Push local variable: GET_LOCAL <slot>
    SET_LOCAL = 41   # Set local variable: SET_LOCAL <slot>
    GET_GLOBAL = 42  # Push global variable: GET_GLOBAL <name_index>
    SET_GLOBAL = 43  # Set global variable: SET_GLOBAL <name_index>

    # Control flow
    JUMP = 50        # Unconditional jump: JUMP <offset>
    JUMP_IF_FALSE = 51  # Conditional jump: JUMP_IF_FALSE <offset>
    LOOP = 52        # Jump backward: LOOP <offset>

    # Functions
    CALL = 60        # Call function: CALL <arg_count>
    RETURN = 61      # Return from function

    # Built-in
    PRINT = 70       # Print top of stack
    HALT = 99        # Stop execution


@dataclass
class Chunk:
    """A compiled bytecode chunk (function body)."""
    code: list[int] = field(default_factory=list)
    constants: list[object] = field(default_factory=list)
    lines: list[int] = field(default_factory=list)  # Source line per instruction
    name: str = "<script>"

    def emit(self, op: OpCode | int, line: int = 0) -> int:
        """Emit one byte, return its offset."""
        offset = len(self.code)
        self.code.append(int(op))
        self.lines.append(line)
        return offset

    def emit_pair(self, op: OpCode, operand: int, line: int = 0) -> int:
        """Emit opcode + operand."""
        offset = self.emit(op, line)
        self.emit(operand, line)
        return offset

    def add_constant(self, value: object) -> int:
        """Add a constant and return its index."""
        self.constants.append(value)
        return len(self.constants) - 1

    def patch_jump(self, offset: int) -> None:
        """Patch a jump instruction with the current offset."""
        jump_distance = len(self.code) - offset - 2
        self.code[offset + 1] = jump_distance

    def disassemble(self) -> str:
        """Pretty-print bytecode for debugging."""
        lines: list[str] = [f"=== {self.name} ==="]
        i = 0
        while i < len(self.code):
            op = OpCode(self.code[i])
            line_num = self.lines[i] if i < len(self.lines) else 0

            if op in (OpCode.CONST, OpCode.GET_LOCAL, OpCode.SET_LOCAL,
                      OpCode.GET_GLOBAL, OpCode.SET_GLOBAL, OpCode.CALL):
                operand = self.code[i + 1]
                if op == OpCode.CONST:
                    val = self.constants[operand]
                    lines.append(f"  {i:04d}  L{line_num:3d}  {op.name:20s} {operand} ({val!r})")
                else:
                    lines.append(f"  {i:04d}  L{line_num:3d}  {op.name:20s} {operand}")
                i += 2
            elif op in (OpCode.JUMP, OpCode.JUMP_IF_FALSE, OpCode.LOOP):
                operand = self.code[i + 1]
                target = i + 2 + operand if op != OpCode.LOOP else i + 2 - operand
                lines.append(f"  {i:04d}  L{line_num:3d}  {op.name:20s} -> {target:04d}")
                i += 2
            else:
                lines.append(f"  {i:04d}  L{line_num:3d}  {op.name}")
                i += 1

        lines.append(f"Constants: {self.constants}")
        return "\n".join(lines)
```

```python
# compiler.py — AST-to-bytecode compiler
from ast_nodes import *
from bytecode import OpCode, Chunk


@dataclass
class Local:
    name: str
    depth: int


class Compiler:
    """Compile AST to bytecode for the stack-based VM."""

    def __init__(self):
        self.chunk = Chunk()
        self.locals: list[Local] = []
        self.scope_depth = 0

    def compile(self, program: Program) -> Chunk:
        for decl in program.declarations:
            self._compile_node(decl)
        self.chunk.emit(OpCode.HALT)
        return self.chunk

    def _compile_node(self, node: ASTNode) -> None:
        line = node.loc.line

        if isinstance(node, IntLiteral):
            idx = self.chunk.add_constant(node.value)
            self.chunk.emit_pair(OpCode.CONST, idx, line)

        elif isinstance(node, FloatLiteral):
            idx = self.chunk.add_constant(node.value)
            self.chunk.emit_pair(OpCode.CONST, idx, line)

        elif isinstance(node, BoolLiteral):
            idx = self.chunk.add_constant(node.value)
            self.chunk.emit_pair(OpCode.CONST, idx, line)

        elif isinstance(node, StringLiteral):
            idx = self.chunk.add_constant(node.value)
            self.chunk.emit_pair(OpCode.CONST, idx, line)

        elif isinstance(node, BinaryOp):
            self._compile_node(node.left)
            self._compile_node(node.right)
            ops = {
                "+": OpCode.ADD, "-": OpCode.SUB,
                "*": OpCode.MUL, "/": OpCode.DIV, "%": OpCode.MOD,
                "==": OpCode.EQ, "!=": OpCode.NEQ,
                "<": OpCode.LT, ">": OpCode.GT,
                "<=": OpCode.LTE, ">=": OpCode.GTE,
            }
            if node.op in ops:
                self.chunk.emit(ops[node.op], line)

        elif isinstance(node, UnaryOp):
            self._compile_node(node.operand)
            if node.op == "-":
                self.chunk.emit(OpCode.NEG, line)
            elif node.op == "!":
                self.chunk.emit(OpCode.NOT, line)

        elif isinstance(node, LetStmt):
            self._compile_node(node.value)
            self.locals.append(Local(name=node.name, depth=self.scope_depth))
            # Value stays on stack — local variable slot

        elif isinstance(node, Identifier):
            slot = self._resolve_local(node.name)
            if slot >= 0:
                self.chunk.emit_pair(OpCode.GET_LOCAL, slot, line)
            else:
                idx = self.chunk.add_constant(node.name)
                self.chunk.emit_pair(OpCode.GET_GLOBAL, idx, line)

        elif isinstance(node, IfExpr):
            self._compile_node(node.condition)
            # Jump over then-branch if false
            false_jump = self.chunk.emit_pair(OpCode.JUMP_IF_FALSE, 0xFF, line)

            self.chunk.emit(OpCode.POP, line)  # Pop condition
            self._compile_block(node.then_branch)

            if node.else_branch:
                # Jump over else-branch after then
                else_jump = self.chunk.emit_pair(OpCode.JUMP, 0xFF, line)
                self.chunk.patch_jump(false_jump)
                self.chunk.emit(OpCode.POP, line)
                self._compile_block(node.else_branch)
                self.chunk.patch_jump(else_jump)
            else:
                self.chunk.patch_jump(false_jump)

        elif isinstance(node, WhileStmt):
            loop_start = len(self.chunk.code)
            self._compile_node(node.condition)
            exit_jump = self.chunk.emit_pair(OpCode.JUMP_IF_FALSE, 0xFF, line)
            self.chunk.emit(OpCode.POP, line)
            self._compile_block(node.body)
            # Loop back
            loop_offset = len(self.chunk.code) - loop_start + 2
            self.chunk.emit_pair(OpCode.LOOP, loop_offset, line)
            self.chunk.patch_jump(exit_jump)
            self.chunk.emit(OpCode.POP, line)

        elif isinstance(node, ExprStmt):
            self._compile_node(node.expr)
            self.chunk.emit(OpCode.POP, line)

        elif isinstance(node, FuncCall):
            self._compile_node(node.callee)
            for arg in node.args:
                self._compile_node(arg)
            self.chunk.emit_pair(OpCode.CALL, len(node.args), line)

        elif isinstance(node, Block):
            self._compile_block(node)

        elif isinstance(node, ReturnStmt):
            if node.value:
                self._compile_node(node.value)
            else:
                idx = self.chunk.add_constant(None)
                self.chunk.emit_pair(OpCode.CONST, idx, line)
            self.chunk.emit(OpCode.RETURN, line)

    def _compile_block(self, block: Block) -> None:
        self.scope_depth += 1
        local_count_before = len(self.locals)
        for stmt in block.statements:
            self._compile_node(stmt)
        # Pop locals when exiting scope
        while len(self.locals) > local_count_before:
            self.locals.pop()
            self.chunk.emit(OpCode.POP)
        self.scope_depth -= 1

    def _resolve_local(self, name: str) -> int:
        for i in range(len(self.locals) - 1, -1, -1):
            if self.locals[i].name == name:
                return i
        return -1
```

```python
# vm.py — Stack-based virtual machine
from bytecode import OpCode, Chunk
from typing import Any
from dataclasses import dataclass, field


class VMError(Exception):
    def __init__(self, message: str, line: int = 0):
        self.line = line
        super().__init__(f"Runtime error at line {line}: {message}")


@dataclass
class CallFrame:
    """Tracks a function call on the call stack."""
    chunk: Chunk
    ip: int = 0          # Instruction pointer within chunk
    stack_base: int = 0   # Base of this frame's stack window


class VM:
    """Stack-based bytecode virtual machine."""

    MAX_STACK = 1024
    MAX_FRAMES = 256

    def __init__(self):
        self.stack: list[Any] = []
        self.globals: dict[str, Any] = {}
        self.frames: list[CallFrame] = []
        self._builtin_functions()

    def _builtin_functions(self) -> None:
        self.globals["print"] = lambda *args: print(*args)
        self.globals["len"] = lambda x: len(x)
        self.globals["str"] = lambda x: str(x)
        self.globals["int"] = lambda x: int(x)

    def execute(self, chunk: Chunk) -> Any:
        """Execute a bytecode chunk and return the final value."""
        self.frames.append(CallFrame(chunk=chunk, ip=0, stack_base=0))

        while self.frames:
            frame = self.frames[-1]
            chunk = frame.chunk

            if frame.ip >= len(chunk.code):
                break

            op = OpCode(chunk.code[frame.ip])
            frame.ip += 1

            if op == OpCode.CONST:
                idx = chunk.code[frame.ip]
                frame.ip += 1
                self.stack.append(chunk.constants[idx])

            elif op == OpCode.POP:
                if self.stack:
                    self.stack.pop()

            elif op == OpCode.DUP:
                self.stack.append(self.stack[-1])

            # Arithmetic
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
                    raise VMError("Division by zero", chunk.lines[frame.ip - 1])
                self.stack.append(a / b)
            elif op == OpCode.MOD:
                b, a = self.stack.pop(), self.stack.pop()
                self.stack.append(a % b)
            elif op == OpCode.NEG:
                self.stack.append(-self.stack.pop())

            # Comparison
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

            # Logic
            elif op == OpCode.NOT:
                self.stack.append(not self.stack.pop())

            # Variables
            elif op == OpCode.GET_LOCAL:
                slot = chunk.code[frame.ip]
                frame.ip += 1
                self.stack.append(self.stack[frame.stack_base + slot])
            elif op == OpCode.SET_LOCAL:
                slot = chunk.code[frame.ip]
                frame.ip += 1
                self.stack[frame.stack_base + slot] = self.stack[-1]
            elif op == OpCode.GET_GLOBAL:
                name_idx = chunk.code[frame.ip]
                frame.ip += 1
                name = chunk.constants[name_idx]
                if name not in self.globals:
                    raise VMError(f"Undefined variable: {name}")
                self.stack.append(self.globals[name])
            elif op == OpCode.SET_GLOBAL:
                name_idx = chunk.code[frame.ip]
                frame.ip += 1
                name = chunk.constants[name_idx]
                self.globals[name] = self.stack[-1]

            # Control flow
            elif op == OpCode.JUMP:
                offset = chunk.code[frame.ip]
                frame.ip += 1 + offset
            elif op == OpCode.JUMP_IF_FALSE:
                offset = chunk.code[frame.ip]
                frame.ip += 1
                if not self.stack[-1]:
                    frame.ip += offset
            elif op == OpCode.LOOP:
                offset = chunk.code[frame.ip]
                frame.ip += 1
                frame.ip -= offset

            # Functions
            elif op == OpCode.CALL:
                arg_count = chunk.code[frame.ip]
                frame.ip += 1
                callee = self.stack[-(arg_count + 1)]
                if callable(callee):
                    args = self.stack[-arg_count:] if arg_count else []
                    self.stack = self.stack[:-(arg_count + 1)]
                    result = callee(*args)
                    self.stack.append(result)

            elif op == OpCode.RETURN:
                result = self.stack.pop() if self.stack else None
                self.frames.pop()
                self.stack.append(result)

            elif op == OpCode.PRINT:
                print(self.stack[-1])

            elif op == OpCode.HALT:
                break

        return self.stack[-1] if self.stack else None


# Run it
from parser import Parser

source = "let x = (10 + 20) * 3 - 5;"
parser = Parser(source)
ast = parser.parse()
compiler = Compiler()
chunk = compiler.compile(ast)
print(chunk.disassemble())
vm = VM()
result = vm.execute(chunk)
```

| VM Architecture | Dispatch | Performance | Complexity | Example |
|---|---|---|---|---|
| Stack-based | Push/pop | Good | Simple | CPython, JVM, Lua |
| Register-based | Load/store | Better (~20%) | More complex | Dalvik, LuaJIT |
| Threaded (direct) | Computed goto | Fast | Non-portable | LuaJIT, Ruby 3 |
| JIT compiled | Native code | Fastest | Very complex | V8, PyPy, GraalVM |

Key patterns:
1. Stack-based VMs need no register allocation -- simpler compiler, smaller bytecode
2. Jump patching: emit a placeholder offset, fill it in when the target is known
3. Call frames track IP and stack base for each function invocation
4. Scope depth tracks variable lifetime -- pop locals when exiting a scope
5. Disassembler is essential for debugging -- print human-readable bytecode
6. Built-in functions are just Python callables stored in the globals table'''
    ),
    (
        "compilers/ssa-optimization",
        "Explain SSA (Static Single Assignment) form for compiler intermediate representations, including phi functions, and show optimization passes like constant folding, dead code elimination, and common subexpression elimination.",
        '''SSA form and optimization passes for compiler IRs:

```python
# ssa/ir.py — SSA-based intermediate representation
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Iterator


class IRType(Enum):
    INT = auto()
    FLOAT = auto()
    BOOL = auto()
    VOID = auto()


class IROp(Enum):
    # Arithmetic
    ADD = "add"
    SUB = "sub"
    MUL = "mul"
    DIV = "div"
    MOD = "mod"
    NEG = "neg"

    # Comparison
    EQ = "eq"
    NEQ = "neq"
    LT = "lt"
    GT = "gt"
    LTE = "lte"
    GTE = "gte"

    # SSA specific
    PHI = "phi"           # Phi function: merge values from predecessors
    COPY = "copy"         # Simple value copy

    # Memory
    LOAD = "load"
    STORE = "store"
    ALLOCA = "alloca"

    # Control
    BR = "br"             # Unconditional branch
    BR_COND = "br_cond"   # Conditional branch
    CALL = "call"
    RET = "ret"

    # Constants
    CONST = "const"


@dataclass
class Value:
    """An SSA value — each definition creates a unique version."""
    name: str              # e.g., "x.3" (variable x, version 3)
    type: IRType = IRType.INT
    version: int = 0

    def __repr__(self) -> str:
        return f"%{self.name}.{self.version}" if self.version > 0 else f"%{self.name}"

    def __hash__(self) -> int:
        return hash((self.name, self.version))

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Value):
            return NotImplemented
        return self.name == other.name and self.version == other.version


@dataclass
class Instruction:
    """An SSA instruction."""
    op: IROp
    result: Value | None = None     # Output value (None for branches, stores)
    operands: list[Value | int | float | str] = field(default_factory=list)
    phi_sources: list[tuple[str, Value]] | None = None  # For PHI: (block_label, value)
    target_blocks: list[str] = field(default_factory=list)  # For branches

    def __repr__(self) -> str:
        if self.op == IROp.PHI:
            sources = ", ".join(f"[{blk}: {val}]" for blk, val in (self.phi_sources or []))
            return f"  {self.result} = phi {sources}"
        if self.result:
            ops = ", ".join(str(o) for o in self.operands)
            return f"  {self.result} = {self.op.value} {ops}"
        ops = ", ".join(str(o) for o in self.operands)
        return f"  {self.op.value} {ops}"

    @property
    def uses(self) -> list[Value]:
        """Values read by this instruction."""
        vals = [o for o in self.operands if isinstance(o, Value)]
        if self.phi_sources:
            vals.extend(v for _, v in self.phi_sources)
        return vals

    @property
    def defines(self) -> Value | None:
        """Value defined by this instruction."""
        return self.result


@dataclass
class BasicBlock:
    """A basic block — straight-line code with no internal branches."""
    label: str
    instructions: list[Instruction] = field(default_factory=list)
    predecessors: list[str] = field(default_factory=list)
    successors: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        instrs = "\n".join(str(i) for i in self.instructions)
        preds = ", ".join(self.predecessors)
        return f"{self.label}: (preds: {preds})\n{instrs}"


@dataclass
class Function:
    """An SSA function with basic blocks."""
    name: str
    params: list[Value]
    return_type: IRType
    blocks: dict[str, BasicBlock] = field(default_factory=dict)
    entry_block: str = "entry"

    def add_block(self, label: str) -> BasicBlock:
        block = BasicBlock(label=label)
        self.blocks[label] = block
        return block

    def __repr__(self) -> str:
        params = ", ".join(str(p) for p in self.params)
        blocks = "\n\n".join(str(b) for b in self.blocks.values())
        return f"func {self.name}({params}) -> {self.return_type.name}:\n{blocks}"
```

```python
# ssa/passes.py — Optimization passes on SSA IR
from ssa.ir import *
from typing import Any


class ConstantFolding:
    """
    Evaluate operations on constants at compile time.
    e.g., %x = add 3, 5  -->  %x = const 8
    """

    def run(self, func: Function) -> int:
        changes = 0
        for block in func.blocks.values():
            new_instructions = []
            for instr in block.instructions:
                folded = self._try_fold(instr)
                if folded:
                    new_instructions.append(folded)
                    changes += 1
                else:
                    new_instructions.append(instr)
            block.instructions = new_instructions
        return changes

    def _try_fold(self, instr: Instruction) -> Instruction | None:
        if instr.op in (IROp.ADD, IROp.SUB, IROp.MUL, IROp.DIV, IROp.MOD):
            if len(instr.operands) == 2:
                a, b = instr.operands
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    ops = {
                        IROp.ADD: lambda x, y: x + y,
                        IROp.SUB: lambda x, y: x - y,
                        IROp.MUL: lambda x, y: x * y,
                        IROp.DIV: lambda x, y: x // y if isinstance(x, int) else x / y,
                        IROp.MOD: lambda x, y: x % y,
                    }
                    result = ops[instr.op](a, b)
                    return Instruction(
                        op=IROp.CONST,
                        result=instr.result,
                        operands=[result],
                    )

        # Boolean constant folding
        if instr.op in (IROp.EQ, IROp.NEQ, IROp.LT, IROp.GT, IROp.LTE, IROp.GTE):
            if len(instr.operands) == 2:
                a, b = instr.operands
                if isinstance(a, (int, float)) and isinstance(b, (int, float)):
                    ops = {
                        IROp.EQ: lambda x, y: x == y,
                        IROp.NEQ: lambda x, y: x != y,
                        IROp.LT: lambda x, y: x < y,
                        IROp.GT: lambda x, y: x > y,
                        IROp.LTE: lambda x, y: x <= y,
                        IROp.GTE: lambda x, y: x >= y,
                    }
                    result = ops[instr.op](a, b)
                    return Instruction(
                        op=IROp.CONST,
                        result=instr.result,
                        operands=[result],
                    )

        return None


class DeadCodeElimination:
    """
    Remove instructions whose results are never used.
    An instruction is dead if its result is not in any other instruction's uses.
    """

    def run(self, func: Function) -> int:
        # Collect all used values
        used: set[Value] = set()
        for block in func.blocks.values():
            for instr in block.instructions:
                used.update(instr.uses)
                # Branch targets and side-effecting ops are always live
                if instr.op in (IROp.BR, IROp.BR_COND, IROp.RET,
                               IROp.CALL, IROp.STORE):
                    if instr.result:
                        used.add(instr.result)

        # Remove dead instructions
        changes = 0
        for block in func.blocks.values():
            alive = []
            for instr in block.instructions:
                if instr.result is None:
                    alive.append(instr)  # No result = side effect
                elif instr.result in used:
                    alive.append(instr)
                elif instr.op in (IROp.CALL, IROp.STORE):
                    alive.append(instr)  # Side effects
                else:
                    changes += 1  # Dead — remove
            block.instructions = alive

        return changes


class CommonSubexpressionElimination:
    """
    Replace redundant computations with references to previously computed values.
    e.g., %a = add %x, %y; %b = add %x, %y  -->  %b = copy %a
    """

    def run(self, func: Function) -> int:
        changes = 0
        for block in func.blocks.values():
            # Map expression signature -> result value
            seen: dict[tuple, Value] = {}
            new_instructions = []

            for instr in block.instructions:
                if instr.op in (IROp.ADD, IROp.SUB, IROp.MUL, IROp.DIV,
                               IROp.MOD, IROp.EQ, IROp.NEQ, IROp.LT,
                               IROp.GT, IROp.LTE, IROp.GTE):
                    # Create a canonical signature
                    sig = (instr.op, tuple(
                        (o.name, o.version) if isinstance(o, Value) else o
                        for o in instr.operands
                    ))

                    if sig in seen and instr.result:
                        # Replace with copy of previous result
                        new_instructions.append(Instruction(
                            op=IROp.COPY,
                            result=instr.result,
                            operands=[seen[sig]],
                        ))
                        changes += 1
                    else:
                        if instr.result:
                            seen[sig] = instr.result
                        new_instructions.append(instr)
                else:
                    new_instructions.append(instr)

            block.instructions = new_instructions

        return changes


class CopyPropagation:
    """
    Replace uses of copied values with the original.
    e.g., %b = copy %a; use %b  -->  use %a
    """

    def run(self, func: Function) -> int:
        # Build copy map: copied_value -> original_value
        copies: dict[tuple, Value] = {}
        for block in func.blocks.values():
            for instr in block.instructions:
                if instr.op == IROp.COPY and instr.result and isinstance(instr.operands[0], Value):
                    key = (instr.result.name, instr.result.version)
                    copies[key] = instr.operands[0]

        # Replace uses
        changes = 0
        for block in func.blocks.values():
            for instr in block.instructions:
                for i, op in enumerate(instr.operands):
                    if isinstance(op, Value):
                        key = (op.name, op.version)
                        if key in copies:
                            instr.operands[i] = copies[key]
                            changes += 1
                if instr.phi_sources:
                    for j, (blk, val) in enumerate(instr.phi_sources):
                        key = (val.name, val.version)
                        if key in copies:
                            instr.phi_sources[j] = (blk, copies[key])
                            changes += 1

        return changes


class OptimizationPipeline:
    """Run optimization passes until fixed point."""

    def __init__(self):
        self.passes = [
            ("constant_folding", ConstantFolding()),
            ("cse", CommonSubexpressionElimination()),
            ("copy_propagation", CopyPropagation()),
            ("dce", DeadCodeElimination()),
        ]

    def run(self, func: Function, max_iterations: int = 10) -> dict[str, int]:
        stats: dict[str, int] = {}
        for name, _ in self.passes:
            stats[name] = 0

        for iteration in range(max_iterations):
            total_changes = 0
            for name, pass_obj in self.passes:
                changes = pass_obj.run(func)
                stats[name] += changes
                total_changes += changes

            if total_changes == 0:
                break  # Fixed point reached

        return stats
```

```text
SSA Transformation Example:

Original code:
    x = 1
    if condition:
        x = x + 1
    else:
        x = x * 2
    y = x + 3

SSA form (each assignment creates a new version):

entry:
    %x.1 = const 1
    br_cond %cond, then, else

then:
    %x.2 = add %x.1, 1
    br merge

else:
    %x.3 = mul %x.1, 2
    br merge

merge:
    %x.4 = phi [then: %x.2, else: %x.3]   <-- Phi function!
    %y.1 = add %x.4, 3
    ret %y.1

Phi function: selects the correct version of x based on
which predecessor block was executed. This is the key insight
of SSA — it makes data flow explicit.

Optimization pipeline on:  %a = add 3, 5; %b = mul %a, 2; %c = mul %a, 2

Pass 1 - Constant folding:  %a = const 8; %b = mul 8, 2; %c = mul 8, 2
Pass 2 - Constant folding:  %a = const 8; %b = const 16; %c = const 16
Pass 3 - CSE:               %a = const 8; %b = const 16; %c = copy %b
Pass 4 - Copy propagation:  (replaces uses of %c with %b)
Pass 5 - DCE:               (removes %c = copy %b if %c unused)
```

| Optimization Pass | What It Does | Prerequisites | Typical Improvement |
|---|---|---|---|
| Constant folding | Evaluate constant expressions at compile time | None | 5-15% code size |
| DCE | Remove unused computations | Use-def chains | 5-20% code size |
| CSE | Eliminate redundant computations | Dominance info | 5-10% speed |
| Copy propagation | Remove unnecessary copies | SSA form | Enables further DCE |
| Constant propagation | Track constant values through variables | SSA form | 10-20% speed |
| Loop-invariant code motion | Hoist invariant computations out of loops | Loop analysis | 10-30% for loops |
| Inlining | Replace function call with body | Call graph | 10-50% speed |
| Strength reduction | Replace expensive ops (mul -> shift) | Loop analysis | 5-15% speed |
| Phi elimination | Convert SSA back to normal form | SSA form | Required for codegen |

Key patterns:
1. SSA ensures each variable is assigned exactly once -- simplifies data-flow analysis
2. Phi functions merge values at control flow join points
3. Run passes in a loop until no more changes (fixed-point iteration)
4. DCE depends on CSE and copy propagation -- order matters
5. Dominance tree determines where phi functions are needed (using iterated dominance frontiers)
6. Converting out of SSA requires replacing phis with copies in predecessor blocks'''
    ),
    (
        "compilers/garbage-collector",
        "Implement garbage collector algorithms including mark-and-sweep, generational collection, and tri-color concurrent marking with write barriers.",
        '''Garbage collector implementations -- mark-sweep, generational, concurrent:

```python
# gc/mark_sweep.py — Basic mark-and-sweep garbage collector
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Iterator
from enum import Enum, auto


class ObjType(Enum):
    INT = auto()
    STRING = auto()
    PAIR = auto()       # Cons cell / tuple
    ARRAY = auto()
    CLOSURE = auto()


@dataclass
class GCObject:
    """A heap-allocated object managed by the garbage collector."""
    obj_type: ObjType
    marked: bool = False
    data: Any = None

    # For PAIR type
    car: GCObject | None = None
    cdr: GCObject | None = None

    # For ARRAY type
    elements: list[GCObject] = field(default_factory=list)

    # For CLOSURE type
    upvalues: list[GCObject] = field(default_factory=list)

    def children(self) -> Iterator[GCObject]:
        """Yield all objects referenced by this object."""
        if self.obj_type == ObjType.PAIR:
            if self.car: yield self.car
            if self.cdr: yield self.cdr
        elif self.obj_type == ObjType.ARRAY:
            yield from self.elements
        elif self.obj_type == ObjType.CLOSURE:
            yield from self.upvalues


class MarkSweepGC:
    """
    Simple mark-and-sweep collector.

    Phase 1 (Mark): Trace all reachable objects from roots, set marked=True
    Phase 2 (Sweep): Free all unmarked objects

    Stop-the-world: mutator is paused during collection.
    """

    def __init__(self, heap_limit: int = 1024):
        self.heap: list[GCObject] = []
        self.heap_limit = heap_limit
        self.roots: list[GCObject] = []  # Stack, globals
        self._stats = {"collections": 0, "freed": 0, "total_allocated": 0}

    def allocate(self, obj_type: ObjType, data: Any = None) -> GCObject:
        """Allocate a new object, triggering GC if needed."""
        if len(self.heap) >= self.heap_limit:
            self.collect()
            # If still over limit after GC, grow heap
            if len(self.heap) >= self.heap_limit:
                self.heap_limit *= 2

        obj = GCObject(obj_type=obj_type, data=data)
        self.heap.append(obj)
        self._stats["total_allocated"] += 1
        return obj

    def add_root(self, obj: GCObject) -> None:
        """Register a GC root (stack variable, global)."""
        self.roots.append(obj)

    def remove_root(self, obj: GCObject) -> None:
        if obj in self.roots:
            self.roots.remove(obj)

    def collect(self) -> int:
        """Run a full mark-sweep collection. Returns number of freed objects."""
        before = len(self.heap)

        # Mark phase
        self._mark()

        # Sweep phase
        freed = self._sweep()

        self._stats["collections"] += 1
        self._stats["freed"] += freed
        return freed

    def _mark(self) -> None:
        """Trace all reachable objects from roots using iterative DFS."""
        worklist: list[GCObject] = list(self.roots)

        while worklist:
            obj = worklist.pop()
            if obj.marked:
                continue
            obj.marked = True
            # Add children to worklist
            for child in obj.children():
                if not child.marked:
                    worklist.append(child)

    def _sweep(self) -> int:
        """Remove all unmarked objects from the heap."""
        alive: list[GCObject] = []
        freed = 0

        for obj in self.heap:
            if obj.marked:
                obj.marked = False  # Reset for next GC cycle
                alive.append(obj)
            else:
                freed += 1
                # In a real GC: call finalizer, free memory

        self.heap = alive
        return freed

    def stats(self) -> dict:
        return {
            **self._stats,
            "heap_size": len(self.heap),
            "heap_limit": self.heap_limit,
        }
```

```python
# gc/generational.py — Generational garbage collector with write barrier
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any, Iterator
from enum import IntEnum


class Generation(IntEnum):
    YOUNG = 0     # Nursery: most objects die young
    OLD = 1       # Tenured: survived multiple young GCs
    PERMANENT = 2 # Immortal: built-in objects


@dataclass
class GenObject:
    """Heap object with generational metadata."""
    obj_type: str
    generation: Generation = Generation.YOUNG
    marked: bool = False
    age: int = 0                     # Survived N young collections
    remembered: bool = False         # In remembered set (old->young ref)
    data: Any = None
    references: list[GenObject] = field(default_factory=list)

    def children(self) -> Iterator[GenObject]:
        yield from self.references


class GenerationalGC:
    """
    Generational garbage collector.

    Hypothesis: most objects die young (infant mortality).
    Strategy: collect the young generation frequently (cheap),
              collect old generation rarely (expensive).

    Write barrier: when an old object starts referencing a young object,
    record it in the remembered set so young GC can find it as a root.
    """

    PROMOTION_AGE = 3     # Promote to old after surviving N young GCs
    YOUNG_LIMIT = 256     # Trigger young GC at this count
    OLD_LIMIT = 1024      # Trigger old GC at this count

    def __init__(self):
        self.young: list[GenObject] = []
        self.old: list[GenObject] = []
        self.permanent: list[GenObject] = []

        self.roots: list[GenObject] = []
        self.remembered_set: set[GenObject] = set()  # Old objects pointing to young

        self._stats = {
            "young_collections": 0,
            "old_collections": 0,
            "promoted": 0,
            "total_allocated": 0,
        }

    def allocate(self, obj_type: str, data: Any = None) -> GenObject:
        """Allocate in young generation."""
        if len(self.young) >= self.YOUNG_LIMIT:
            self.collect_young()

        obj = GenObject(obj_type=obj_type, data=data, generation=Generation.YOUNG)
        self.young.append(obj)
        self._stats["total_allocated"] += 1
        return obj

    def write_barrier(self, parent: GenObject, child: GenObject) -> None:
        """
        Write barrier: called when parent.references is modified.
        If an OLD object references a YOUNG object, add to remembered set.
        This ensures young GC can find all roots into the young generation.
        """
        parent.references.append(child)

        if parent.generation == Generation.OLD and child.generation == Generation.YOUNG:
            self.remembered_set.add(parent)
            parent.remembered = True

    def collect_young(self) -> int:
        """
        Minor GC: only collect young generation.
        Roots = stack roots + remembered set (old->young references).
        """
        self._stats["young_collections"] += 1

        # Roots for young GC
        young_roots: list[GenObject] = []
        young_roots.extend(r for r in self.roots if r.generation == Generation.YOUNG)

        # Remembered set: old objects that reference young objects
        for old_obj in self.remembered_set:
            for child in old_obj.children():
                if child.generation == Generation.YOUNG:
                    young_roots.append(child)

        # Mark reachable young objects
        worklist = list(young_roots)
        while worklist:
            obj = worklist.pop()
            if obj.marked:
                continue
            obj.marked = True
            for child in obj.children():
                if child.generation == Generation.YOUNG and not child.marked:
                    worklist.append(child)

        # Sweep young generation
        alive: list[GenObject] = []
        freed = 0
        promoted = 0

        for obj in self.young:
            if obj.marked:
                obj.marked = False
                obj.age += 1

                # Promote to old if survived enough collections
                if obj.age >= self.PROMOTION_AGE:
                    obj.generation = Generation.OLD
                    self.old.append(obj)
                    promoted += 1
                else:
                    alive.append(obj)
            else:
                freed += 1

        self.young = alive
        self._stats["promoted"] += promoted

        # Clean remembered set
        self.remembered_set = {
            obj for obj in self.remembered_set
            if any(c.generation == Generation.YOUNG for c in obj.children())
        }

        # Trigger old GC if needed
        if len(self.old) >= self.OLD_LIMIT:
            self.collect_old()

        return freed

    def collect_old(self) -> int:
        """Major GC: collect both young and old generations (full GC)."""
        self._stats["old_collections"] += 1

        # Mark from all roots
        worklist = list(self.roots)
        while worklist:
            obj = worklist.pop()
            if obj.marked:
                continue
            obj.marked = True
            for child in obj.children():
                if not child.marked:
                    worklist.append(child)

        # Sweep all generations
        freed = 0
        for gen_list in (self.young, self.old):
            alive = []
            for obj in gen_list:
                if obj.marked:
                    obj.marked = False
                    alive.append(obj)
                else:
                    freed += 1
            if gen_list is self.young:
                self.young = alive
            else:
                self.old = alive

        self.remembered_set.clear()
        return freed
```

```python
# gc/concurrent.py — Tri-color concurrent mark with write barrier
from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Iterator
import threading


class Color(Enum):
    WHITE = auto()   # Not yet visited (potentially garbage)
    GRAY = auto()    # Visited but children not yet scanned
    BLACK = auto()   # Fully scanned (reachable)


@dataclass
class ConcurrentObject:
    obj_type: str
    color: Color = Color.WHITE
    data: Any = None
    references: list[ConcurrentObject] = field(default_factory=list)


class TriColorCollector:
    """
    Tri-color concurrent mark-sweep collector.

    Invariant: no black object may reference a white object.
    (Enforced by the write barrier.)

    Phases:
        1. Initial mark (STW): mark roots as gray
        2. Concurrent mark: scan gray objects, mark children gray, turn self black
        3. Remark (STW): process write barrier log
        4. Concurrent sweep: free white objects

    The mutator runs concurrently with phases 2 and 4.
    """

    def __init__(self):
        self.heap: list[ConcurrentObject] = []
        self.roots: list[ConcurrentObject] = []
        self.gray_worklist: list[ConcurrentObject] = []
        self.write_barrier_log: list[tuple[ConcurrentObject, ConcurrentObject]] = []
        self._lock = threading.Lock()

    def allocate(self, obj_type: str, data: Any = None) -> ConcurrentObject:
        obj = ConcurrentObject(obj_type=obj_type, data=data)
        with self._lock:
            self.heap.append(obj)
        return obj

    def write_barrier_snapshot(
        self, parent: ConcurrentObject, new_child: ConcurrentObject
    ) -> None:
        """
        Snapshot-at-the-beginning write barrier.
        When a reference is about to be overwritten, save the OLD target.
        This preserves the snapshot of reachable objects at GC start.
        """
        with self._lock:
            # If parent is black and child is white, mark child gray
            if parent.color == Color.BLACK and new_child.color == Color.WHITE:
                new_child.color = Color.GRAY
                self.gray_worklist.append(new_child)

    def initial_mark(self) -> None:
        """Phase 1 (STW): Mark roots as gray."""
        for root in self.roots:
            if root.color == Color.WHITE:
                root.color = Color.GRAY
                self.gray_worklist.append(root)

    def concurrent_mark(self) -> int:
        """Phase 2 (concurrent): Scan gray objects."""
        scanned = 0
        while True:
            with self._lock:
                if not self.gray_worklist:
                    break
                obj = self.gray_worklist.pop()

            if obj.color != Color.GRAY:
                continue

            # Scan children
            for child in obj.references:
                with self._lock:
                    if child.color == Color.WHITE:
                        child.color = Color.GRAY
                        self.gray_worklist.append(child)

            with self._lock:
                obj.color = Color.BLACK
            scanned += 1

        return scanned

    def remark(self) -> None:
        """Phase 3 (STW): Process write barrier log entries."""
        with self._lock:
            for parent, child in self.write_barrier_log:
                if child.color == Color.WHITE:
                    child.color = Color.GRAY
                    self.gray_worklist.append(child)
            self.write_barrier_log.clear()

        # Drain any new gray objects
        self.concurrent_mark()

    def concurrent_sweep(self) -> int:
        """Phase 4 (concurrent): Free white objects."""
        freed = 0
        alive: list[ConcurrentObject] = []

        with self._lock:
            for obj in self.heap:
                if obj.color == Color.WHITE:
                    freed += 1
                else:
                    obj.color = Color.WHITE  # Reset for next cycle
                    alive.append(obj)
            self.heap = alive

        return freed

    def full_cycle(self) -> dict:
        """Run a complete GC cycle."""
        # Phase 1: Initial mark (STW)
        self.initial_mark()

        # Phase 2: Concurrent mark
        scanned = self.concurrent_mark()

        # Phase 3: Remark (STW)
        self.remark()

        # Phase 4: Concurrent sweep
        freed = self.concurrent_sweep()

        return {
            "scanned": scanned,
            "freed": freed,
            "heap_size": len(self.heap),
        }
```

| GC Algorithm | Pause Time | Throughput | Memory Overhead | Complexity | Used By |
|---|---|---|---|---|---|
| Mark-sweep | O(heap) STW | Good | Low (1 bit/object) | Simple | Lua, early JVMs |
| Mark-compact | O(heap) STW | Good | Low | Medium | .NET (Gen2) |
| Copying (semispace) | O(live) STW | Very good | 2x memory | Simple | Young gen (JVM, V8) |
| Generational | Short young GC | Very good | Write barrier | Medium | JVM, .NET, V8, Go |
| Concurrent mark-sweep | ~1ms STW | Good | Gray/write barrier | High | Go, JVM (CMS) |
| Incremental | Bounded pauses | Medium | Write/read barrier | High | Lua 5.1+ |
| Reference counting | None (amortized) | Medium | Counter per object | Simple | CPython, Swift, Rust (Arc) |

Key patterns:
1. Mark-sweep is simplest: trace from roots, free unmarked objects
2. Generational GC exploits infant mortality -- most objects die young
3. Write barriers detect when old-to-young pointers are created
4. Tri-color invariant: no black->white edge ensures concurrent correctness
5. STW (stop-the-world) pauses are minimized by doing most work concurrently
6. Remembered sets track inter-generational pointers for efficient young collection
7. Iterative DFS (worklist) avoids stack overflow on deep object graphs'''
    ),
]
"""
