"""Compiler/interpreter patterns — lexer, recursive descent parser, AST, type checking, bytecode, tree-walking interpreter."""

PAIRS = [
    (
        "compiler/lexer-tokenizer",
        "Implement a lexer/tokenizer for a small programming language that supports integers, floats, strings, identifiers, operators, keywords, and comments, with proper error reporting including line and column numbers.",
        '''Complete lexer with token types, source location tracking, and error reporting:

```python
# lexer.py — Lexer/tokenizer with position tracking and comprehensive token types
from __future__ import annotations
import re
from dataclasses import dataclass
from enum import Enum, auto
from typing import Iterator


class TokenType(Enum):
    # Literals
    INTEGER = auto()
    FLOAT = auto()
    STRING = auto()
    BOOLEAN = auto()

    # Identifiers and keywords
    IDENTIFIER = auto()
    LET = auto()
    CONST = auto()
    FN = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    FOR = auto()
    RETURN = auto()
    TRUE = auto()
    FALSE = auto()
    NIL = auto()
    AND = auto()
    OR = auto()
    NOT = auto()
    STRUCT = auto()
    IMPORT = auto()
    PRINT = auto()

    # Operators
    PLUS = auto()         # +
    MINUS = auto()        # -
    STAR = auto()         # *
    SLASH = auto()        # /
    PERCENT = auto()      # %
    POWER = auto()        # **
    ASSIGN = auto()       # =
    EQUAL = auto()        # ==
    NOT_EQUAL = auto()    # !=
    LESS = auto()         # <
    LESS_EQUAL = auto()   # <=
    GREATER = auto()      # >
    GREATER_EQUAL = auto()# >=
    ARROW = auto()        # ->
    FAT_ARROW = auto()    # =>
    PLUS_ASSIGN = auto()  # +=
    MINUS_ASSIGN = auto() # -=

    # Delimiters
    LPAREN = auto()       # (
    RPAREN = auto()       # )
    LBRACE = auto()       # {
    RBRACE = auto()       # }
    LBRACKET = auto()     # [
    RBRACKET = auto()     # ]
    COMMA = auto()        # ,
    DOT = auto()          # .
    COLON = auto()        # :
    SEMICOLON = auto()    # ;

    # Special
    NEWLINE = auto()
    EOF = auto()
    ERROR = auto()


KEYWORDS: dict[str, TokenType] = {
    "let": TokenType.LET,
    "const": TokenType.CONST,
    "fn": TokenType.FN,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "while": TokenType.WHILE,
    "for": TokenType.FOR,
    "return": TokenType.RETURN,
    "true": TokenType.TRUE,
    "false": TokenType.FALSE,
    "nil": TokenType.NIL,
    "and": TokenType.AND,
    "or": TokenType.OR,
    "not": TokenType.NOT,
    "struct": TokenType.STRUCT,
    "import": TokenType.IMPORT,
    "print": TokenType.PRINT,
}


@dataclass(frozen=True)
class SourceLocation:
    """Tracks position in source code for error messages."""
    line: int
    column: int
    offset: int     # Byte offset in source string

    def __str__(self) -> str:
        return f"line {self.line}, col {self.column}"


@dataclass(frozen=True)
class Token:
    type: TokenType
    value: str              # Raw text
    literal: object | None  # Parsed value (int, float, str, bool, or None)
    location: SourceLocation

    def __repr__(self) -> str:
        if self.literal is not None:
            return f"Token({self.type.name}, {self.literal!r}, {self.location})"
        return f"Token({self.type.name}, {self.value!r}, {self.location})"


@dataclass
class LexerError:
    message: str
    location: SourceLocation

    def __str__(self) -> str:
        return f"LexError at {self.location}: {self.message}"


class Lexer:
    """Scans source code into a stream of tokens with full position tracking."""

    def __init__(self, source: str, filename: str = "<stdin>"):
        self.source = source
        self.filename = filename
        self._pos = 0
        self._line = 1
        self._col = 1
        self._line_start = 0
        self.errors: list[LexerError] = []

    @property
    def _current(self) -> str:
        if self._pos >= len(self.source):
            return "\\0"
        return self.source[self._pos]

    def _peek(self, offset: int = 1) -> str:
        idx = self._pos + offset
        if idx >= len(self.source):
            return "\\0"
        return self.source[idx]

    def _advance(self) -> str:
        ch = self._current
        self._pos += 1
        if ch == "\\n":
            self._line += 1
            self._col = 1
            self._line_start = self._pos
        else:
            self._col += 1
        return ch

    def _location(self) -> SourceLocation:
        return SourceLocation(self._line, self._col, self._pos)

    def _make_token(self, token_type: TokenType, value: str,
                    literal: object = None, loc: SourceLocation | None = None) -> Token:
        return Token(token_type, value, literal, loc or self._location())

    def _error(self, msg: str) -> Token:
        loc = self._location()
        self.errors.append(LexerError(msg, loc))
        return self._make_token(TokenType.ERROR, "", None, loc)

    def _skip_whitespace_and_comments(self):
        while self._pos < len(self.source):
            ch = self._current
            # Skip whitespace (except newlines which are tokens)
            if ch in " \\t\\r":
                self._advance()
            # Line comment: // until end of line
            elif ch == "/" and self._peek() == "/":
                while self._pos < len(self.source) and self._current != "\\n":
                    self._advance()
            # Block comment: /* ... */
            elif ch == "/" and self._peek() == "*":
                self._advance()  # /
                self._advance()  # *
                depth = 1
                while self._pos < len(self.source) and depth > 0:
                    if self._current == "/" and self._peek() == "*":
                        depth += 1
                        self._advance()
                    elif self._current == "*" and self._peek() == "/":
                        depth -= 1
                        self._advance()
                    self._advance()
                if depth > 0:
                    self._error("Unterminated block comment")
            else:
                break

    def _read_string(self) -> Token:
        loc = self._location()
        quote = self._advance()  # opening quote
        result = []
        while self._pos < len(self.source) and self._current != quote:
            if self._current == "\\n":
                return self._error("Unterminated string (newline in string)")
            if self._current == "\\\\":
                self._advance()
                escape = self._advance()
                match escape:
                    case "n":  result.append("\\n")
                    case "t":  result.append("\\t")
                    case "\\\\": result.append("\\\\")
                    case '"':  result.append('"')
                    case "'":  result.append("'")
                    case "0":  result.append("\\0")
                    case _:    result.append(escape)
            else:
                result.append(self._advance())

        if self._pos >= len(self.source):
            return self._error("Unterminated string")

        self._advance()  # closing quote
        text = "".join(result)
        return self._make_token(TokenType.STRING, f"{quote}{text}{quote}", text, loc)

    def _read_number(self) -> Token:
        loc = self._location()
        start = self._pos
        is_float = False

        # Integer part
        while self._pos < len(self.source) and self._current.isdigit():
            self._advance()

        # Decimal part
        if self._current == "." and self._peek().isdigit():
            is_float = True
            self._advance()  # .
            while self._pos < len(self.source) and self._current.isdigit():
                self._advance()

        # Scientific notation
        if self._current in ("e", "E"):
            is_float = True
            self._advance()
            if self._current in ("+", "-"):
                self._advance()
            if not self._current.isdigit():
                return self._error("Invalid number: expected digit after exponent")
            while self._pos < len(self.source) and self._current.isdigit():
                self._advance()

        text = self.source[start:self._pos]
        if is_float:
            return self._make_token(TokenType.FLOAT, text, float(text), loc)
        return self._make_token(TokenType.INTEGER, text, int(text), loc)

    def _read_identifier(self) -> Token:
        loc = self._location()
        start = self._pos
        while (self._pos < len(self.source) and
               (self._current.isalnum() or self._current == "_")):
            self._advance()

        text = self.source[start:self._pos]
        token_type = KEYWORDS.get(text, TokenType.IDENTIFIER)

        # Handle boolean literals
        if token_type == TokenType.TRUE:
            return self._make_token(token_type, text, True, loc)
        elif token_type == TokenType.FALSE:
            return self._make_token(token_type, text, False, loc)

        return self._make_token(token_type, text, None, loc)

    def tokenize(self) -> list[Token]:
        """Scan entire source into token list."""
        tokens: list[Token] = []
        while self._pos < len(self.source):
            self._skip_whitespace_and_comments()
            if self._pos >= len(self.source):
                break

            loc = self._location()
            ch = self._current

            # Newlines (significant in some grammars)
            if ch == "\\n":
                self._advance()
                tokens.append(self._make_token(TokenType.NEWLINE, "\\n", None, loc))
                continue

            # Strings
            if ch in ('"', "'"):
                tokens.append(self._read_string())
                continue

            # Numbers
            if ch.isdigit():
                tokens.append(self._read_number())
                continue

            # Identifiers and keywords
            if ch.isalpha() or ch == "_":
                tokens.append(self._read_identifier())
                continue

            # Two-character operators
            two_char = self.source[self._pos:self._pos + 2]
            match two_char:
                case "**": self._advance(); self._advance(); tokens.append(self._make_token(TokenType.POWER, "**", None, loc)); continue
                case "==": self._advance(); self._advance(); tokens.append(self._make_token(TokenType.EQUAL, "==", None, loc)); continue
                case "!=": self._advance(); self._advance(); tokens.append(self._make_token(TokenType.NOT_EQUAL, "!=", None, loc)); continue
                case "<=": self._advance(); self._advance(); tokens.append(self._make_token(TokenType.LESS_EQUAL, "<=", None, loc)); continue
                case ">=": self._advance(); self._advance(); tokens.append(self._make_token(TokenType.GREATER_EQUAL, ">=", None, loc)); continue
                case "->": self._advance(); self._advance(); tokens.append(self._make_token(TokenType.ARROW, "->", None, loc)); continue
                case "=>": self._advance(); self._advance(); tokens.append(self._make_token(TokenType.FAT_ARROW, "=>", None, loc)); continue
                case "+=": self._advance(); self._advance(); tokens.append(self._make_token(TokenType.PLUS_ASSIGN, "+=", None, loc)); continue
                case "-=": self._advance(); self._advance(); tokens.append(self._make_token(TokenType.MINUS_ASSIGN, "-=", None, loc)); continue

            # Single-character tokens
            self._advance()
            match ch:
                case "+": tokens.append(self._make_token(TokenType.PLUS, ch, None, loc))
                case "-": tokens.append(self._make_token(TokenType.MINUS, ch, None, loc))
                case "*": tokens.append(self._make_token(TokenType.STAR, ch, None, loc))
                case "/": tokens.append(self._make_token(TokenType.SLASH, ch, None, loc))
                case "%": tokens.append(self._make_token(TokenType.PERCENT, ch, None, loc))
                case "=": tokens.append(self._make_token(TokenType.ASSIGN, ch, None, loc))
                case "<": tokens.append(self._make_token(TokenType.LESS, ch, None, loc))
                case ">": tokens.append(self._make_token(TokenType.GREATER, ch, None, loc))
                case "(": tokens.append(self._make_token(TokenType.LPAREN, ch, None, loc))
                case ")": tokens.append(self._make_token(TokenType.RPAREN, ch, None, loc))
                case "{": tokens.append(self._make_token(TokenType.LBRACE, ch, None, loc))
                case "}": tokens.append(self._make_token(TokenType.RBRACE, ch, None, loc))
                case "[": tokens.append(self._make_token(TokenType.LBRACKET, ch, None, loc))
                case "]": tokens.append(self._make_token(TokenType.RBRACKET, ch, None, loc))
                case ",": tokens.append(self._make_token(TokenType.COMMA, ch, None, loc))
                case ".": tokens.append(self._make_token(TokenType.DOT, ch, None, loc))
                case ":": tokens.append(self._make_token(TokenType.COLON, ch, None, loc))
                case ";": tokens.append(self._make_token(TokenType.SEMICOLON, ch, None, loc))
                case _:
                    tokens.append(self._error(f"Unexpected character: {ch!r}"))

        tokens.append(self._make_token(TokenType.EOF, "", None, self._location()))
        return tokens
```

Example usage:

```python
source = """
// Fibonacci function
fn fib(n: int) -> int {
    if n <= 1 { return n; }
    return fib(n - 1) + fib(n - 2);
}

let result = fib(10);  /* should be 55 */
print(result);
"""

lexer = Lexer(source, "fib.hive")
tokens = lexer.tokenize()
for tok in tokens:
    if tok.type not in (TokenType.NEWLINE,):
        print(tok)

# Output:
# Token(FN, 'fn', line 3, col 1)
# Token(IDENTIFIER, 'fib', line 3, col 4)
# Token(LPAREN, '(', line 3, col 7)
# Token(IDENTIFIER, 'n', line 3, col 8)
# Token(COLON, ':', line 3, col 9)
# Token(IDENTIFIER, 'int', line 3, col 11)
# ...
```

| Lexer Strategy | Performance | Flexibility | Maintenance |
|---|---|---|---|
| Hand-written (this) | Best | Full control | Medium |
| Regex-based | Good | Pattern matching | Easy |
| Generated (ANTLR) | Good | Grammar-driven | Lowest |
| PEG parser | Varies | Unified lex+parse | Small grammars |

Key lexer patterns:
- Track line/column for every token to enable precise error messages
- Peek ahead for multi-character operators (`==`, `->`, `**`)
- Keywords are identified by looking up identifiers in a keyword table
- String escape sequences are resolved during lexing, not parsing
- Block comments support nesting via depth counter
- Errors produce ERROR tokens rather than throwing (allows recovery)
'''
    ),
    (
        "compiler/recursive-descent-parser",
        "Implement a recursive descent parser that builds an AST from the token stream, handling operator precedence with Pratt parsing, error recovery, and support for expressions, statements, functions, and control flow.",
        '''Recursive descent parser with Pratt precedence climbing and AST construction:

```python
# parser.py — Recursive descent parser with Pratt precedence and error recovery
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any
from enum import IntEnum

# Assume lexer.py provides Token, TokenType, SourceLocation
from lexer import Token, TokenType, SourceLocation


# ============================================================
# AST Node Definitions
# ============================================================

@dataclass
class ASTNode:
    location: SourceLocation

# --- Expressions ---

@dataclass
class IntegerLiteral(ASTNode):
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
class NilLiteral(ASTNode):
    pass

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
class CallExpr(ASTNode):
    callee: ASTNode
    arguments: list[ASTNode]

@dataclass
class IndexExpr(ASTNode):
    object: ASTNode
    index: ASTNode

@dataclass
class MemberExpr(ASTNode):
    object: ASTNode
    member: str

@dataclass
class AssignExpr(ASTNode):
    target: ASTNode
    value: ASTNode

# --- Statements ---

@dataclass
class ExprStatement(ASTNode):
    expression: ASTNode

@dataclass
class LetDecl(ASTNode):
    name: str
    type_annotation: str | None
    initializer: ASTNode | None
    is_const: bool = False

@dataclass
class ReturnStmt(ASTNode):
    value: ASTNode | None

@dataclass
class IfStmt(ASTNode):
    condition: ASTNode
    then_body: Block
    else_body: Block | IfStmt | None

@dataclass
class WhileStmt(ASTNode):
    condition: ASTNode
    body: Block

@dataclass
class Block(ASTNode):
    statements: list[ASTNode]

@dataclass
class Parameter(ASTNode):
    name: str
    type_annotation: str | None

@dataclass
class FunctionDecl(ASTNode):
    name: str
    params: list[Parameter]
    return_type: str | None
    body: Block

@dataclass
class Program(ASTNode):
    statements: list[ASTNode]


# ============================================================
# Pratt Parser Precedence Table
# ============================================================

class Precedence(IntEnum):
    NONE = 0
    ASSIGNMENT = 1    # =
    OR = 2            # or
    AND = 3           # and
    EQUALITY = 4      # == !=
    COMPARISON = 5    # < > <= >=
    TERM = 6          # + -
    FACTOR = 7        # * / %
    POWER = 8         # **
    UNARY = 9         # - not
    CALL = 10         # () [] .
    PRIMARY = 11


def get_precedence(token_type: TokenType) -> Precedence:
    return {
        TokenType.ASSIGN: Precedence.ASSIGNMENT,
        TokenType.PLUS_ASSIGN: Precedence.ASSIGNMENT,
        TokenType.MINUS_ASSIGN: Precedence.ASSIGNMENT,
        TokenType.OR: Precedence.OR,
        TokenType.AND: Precedence.AND,
        TokenType.EQUAL: Precedence.EQUALITY,
        TokenType.NOT_EQUAL: Precedence.EQUALITY,
        TokenType.LESS: Precedence.COMPARISON,
        TokenType.LESS_EQUAL: Precedence.COMPARISON,
        TokenType.GREATER: Precedence.COMPARISON,
        TokenType.GREATER_EQUAL: Precedence.COMPARISON,
        TokenType.PLUS: Precedence.TERM,
        TokenType.MINUS: Precedence.TERM,
        TokenType.STAR: Precedence.FACTOR,
        TokenType.SLASH: Precedence.FACTOR,
        TokenType.PERCENT: Precedence.FACTOR,
        TokenType.POWER: Precedence.POWER,
        TokenType.LPAREN: Precedence.CALL,
        TokenType.LBRACKET: Precedence.CALL,
        TokenType.DOT: Precedence.CALL,
    }.get(token_type, Precedence.NONE)


# ============================================================
# Parser
# ============================================================

class ParseError(Exception):
    def __init__(self, message: str, location: SourceLocation):
        self.location = location
        super().__init__(f"ParseError at {location}: {message}")


class Parser:
    """Recursive descent parser with Pratt precedence for expressions."""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self._pos = 0
        self.errors: list[ParseError] = []

    @property
    def _current(self) -> Token:
        return self.tokens[self._pos]

    def _peek(self, offset: int = 1) -> Token:
        idx = self._pos + offset
        if idx < len(self.tokens):
            return self.tokens[idx]
        return self.tokens[-1]

    def _advance(self) -> Token:
        token = self._current
        if token.type != TokenType.EOF:
            self._pos += 1
        # Skip newlines in most contexts
        while self._current.type == TokenType.NEWLINE:
            self._pos += 1
        return token

    def _expect(self, token_type: TokenType, message: str = "") -> Token:
        if self._current.type == token_type:
            return self._advance()
        msg = message or f"Expected {token_type.name}, got {self._current.type.name}"
        raise ParseError(msg, self._current.location)

    def _match(self, *types: TokenType) -> Token | None:
        if self._current.type in types:
            return self._advance()
        return None

    def _skip_newlines(self):
        while self._current.type == TokenType.NEWLINE:
            self._pos += 1

    # --- Entry point ---

    def parse(self) -> Program:
        self._skip_newlines()
        statements: list[ASTNode] = []
        while self._current.type != TokenType.EOF:
            try:
                stmt = self._parse_declaration()
                statements.append(stmt)
            except ParseError as e:
                self.errors.append(e)
                self._synchronize()
            self._skip_newlines()
        return Program(location=SourceLocation(1, 1, 0), statements=statements)

    def _synchronize(self):
        """Error recovery: skip tokens until we find a statement boundary."""
        while self._current.type != TokenType.EOF:
            if self._current.type in (
                TokenType.SEMICOLON, TokenType.NEWLINE
            ):
                self._advance()
                return
            if self._current.type in (
                TokenType.FN, TokenType.LET, TokenType.CONST,
                TokenType.IF, TokenType.WHILE, TokenType.RETURN,
            ):
                return
            self._advance()

    # --- Declarations ---

    def _parse_declaration(self) -> ASTNode:
        if self._current.type == TokenType.FN:
            return self._parse_function()
        if self._current.type in (TokenType.LET, TokenType.CONST):
            return self._parse_let()
        return self._parse_statement()

    def _parse_function(self) -> FunctionDecl:
        loc = self._current.location
        self._expect(TokenType.FN)
        name = self._expect(TokenType.IDENTIFIER).value

        self._expect(TokenType.LPAREN)
        params: list[Parameter] = []
        while self._current.type != TokenType.RPAREN:
            if params:
                self._expect(TokenType.COMMA)
            p_loc = self._current.location
            p_name = self._expect(TokenType.IDENTIFIER).value
            p_type = None
            if self._match(TokenType.COLON):
                p_type = self._expect(TokenType.IDENTIFIER).value
            params.append(Parameter(location=p_loc, name=p_name, type_annotation=p_type))
        self._expect(TokenType.RPAREN)

        return_type = None
        if self._match(TokenType.ARROW):
            return_type = self._expect(TokenType.IDENTIFIER).value

        body = self._parse_block()
        return FunctionDecl(loc, name, params, return_type, body)

    def _parse_let(self) -> LetDecl:
        loc = self._current.location
        is_const = self._current.type == TokenType.CONST
        self._advance()  # let or const

        name = self._expect(TokenType.IDENTIFIER).value
        type_ann = None
        if self._match(TokenType.COLON):
            type_ann = self._expect(TokenType.IDENTIFIER).value

        initializer = None
        if self._match(TokenType.ASSIGN):
            initializer = self._parse_expression()

        self._match(TokenType.SEMICOLON)
        return LetDecl(loc, name, type_ann, initializer, is_const)

    # --- Statements ---

    def _parse_statement(self) -> ASTNode:
        if self._current.type == TokenType.IF:
            return self._parse_if()
        if self._current.type == TokenType.WHILE:
            return self._parse_while()
        if self._current.type == TokenType.RETURN:
            return self._parse_return()
        if self._current.type == TokenType.LBRACE:
            return self._parse_block()

        expr = self._parse_expression()
        self._match(TokenType.SEMICOLON)
        return ExprStatement(location=expr.location, expression=expr)

    def _parse_block(self) -> Block:
        loc = self._current.location
        self._expect(TokenType.LBRACE)
        self._skip_newlines()
        stmts: list[ASTNode] = []
        while self._current.type != TokenType.RBRACE and self._current.type != TokenType.EOF:
            stmts.append(self._parse_declaration())
            self._skip_newlines()
        self._expect(TokenType.RBRACE)
        return Block(loc, stmts)

    def _parse_if(self) -> IfStmt:
        loc = self._current.location
        self._expect(TokenType.IF)
        condition = self._parse_expression()
        then_body = self._parse_block()
        else_body = None
        if self._match(TokenType.ELSE):
            if self._current.type == TokenType.IF:
                else_body = self._parse_if()
            else:
                else_body = self._parse_block()
        return IfStmt(loc, condition, then_body, else_body)

    def _parse_while(self) -> WhileStmt:
        loc = self._current.location
        self._expect(TokenType.WHILE)
        condition = self._parse_expression()
        body = self._parse_block()
        return WhileStmt(loc, condition, body)

    def _parse_return(self) -> ReturnStmt:
        loc = self._current.location
        self._expect(TokenType.RETURN)
        value = None
        if self._current.type not in (TokenType.SEMICOLON, TokenType.RBRACE, TokenType.NEWLINE, TokenType.EOF):
            value = self._parse_expression()
        self._match(TokenType.SEMICOLON)
        return ReturnStmt(loc, value)

    # --- Expressions (Pratt parsing) ---

    def _parse_expression(self, min_precedence: Precedence = Precedence.ASSIGNMENT) -> ASTNode:
        """Pratt precedence climbing parser for expressions."""
        left = self._parse_prefix()

        while get_precedence(self._current.type) >= min_precedence:
            prec = get_precedence(self._current.type)

            # Handle assignment (right-associative)
            if self._current.type in (TokenType.ASSIGN, TokenType.PLUS_ASSIGN, TokenType.MINUS_ASSIGN):
                op_token = self._advance()
                right = self._parse_expression(Precedence.ASSIGNMENT)
                left = AssignExpr(location=op_token.location, target=left, value=right)
                continue

            # Handle power (right-associative)
            if self._current.type == TokenType.POWER:
                op_token = self._advance()
                right = self._parse_expression(Precedence.POWER)
                left = BinaryOp(op_token.location, "**", left, right)
                continue

            # Handle function calls
            if self._current.type == TokenType.LPAREN:
                left = self._parse_call(left)
                continue

            # Handle indexing
            if self._current.type == TokenType.LBRACKET:
                left = self._parse_index(left)
                continue

            # Handle member access
            if self._current.type == TokenType.DOT:
                self._advance()
                member = self._expect(TokenType.IDENTIFIER).value
                left = MemberExpr(left.location, left, member)
                continue

            # Infix binary operators (left-associative)
            op_token = self._advance()
            right = self._parse_expression(Precedence(prec + 1))
            left = BinaryOp(op_token.location, op_token.value, left, right)

        return left

    def _parse_prefix(self) -> ASTNode:
        """Parse prefix expressions: literals, identifiers, unary operators, grouping."""
        token = self._current

        # Unary operators
        if token.type in (TokenType.MINUS, TokenType.NOT):
            self._advance()
            operand = self._parse_expression(Precedence.UNARY)
            return UnaryOp(token.location, token.value, operand)

        # Grouping
        if token.type == TokenType.LPAREN:
            self._advance()
            expr = self._parse_expression()
            self._expect(TokenType.RPAREN, "Expected ')' after expression")
            return expr

        # Literals
        if token.type == TokenType.INTEGER:
            self._advance()
            return IntegerLiteral(token.location, token.literal)
        if token.type == TokenType.FLOAT:
            self._advance()
            return FloatLiteral(token.location, token.literal)
        if token.type == TokenType.STRING:
            self._advance()
            return StringLiteral(token.location, token.literal)
        if token.type in (TokenType.TRUE, TokenType.FALSE):
            self._advance()
            return BoolLiteral(token.location, token.literal)
        if token.type == TokenType.NIL:
            self._advance()
            return NilLiteral(token.location)
        if token.type == TokenType.IDENTIFIER:
            self._advance()
            return Identifier(token.location, token.value)

        raise ParseError(f"Unexpected token: {token.type.name}", token.location)

    def _parse_call(self, callee: ASTNode) -> CallExpr:
        self._expect(TokenType.LPAREN)
        args: list[ASTNode] = []
        while self._current.type != TokenType.RPAREN:
            if args:
                self._expect(TokenType.COMMA)
            args.append(self._parse_expression(Precedence(Precedence.ASSIGNMENT + 1)))
        self._expect(TokenType.RPAREN)
        return CallExpr(callee.location, callee, args)

    def _parse_index(self, obj: ASTNode) -> IndexExpr:
        self._expect(TokenType.LBRACKET)
        index = self._parse_expression()
        self._expect(TokenType.RBRACKET)
        return IndexExpr(obj.location, obj, index)
```

| Parsing Technique | Handles Left Recursion | Precedence | Error Recovery |
|---|---|---|---|
| Recursive descent | No (manual rewrite) | Manual per function | Good |
| Pratt/precedence climbing | Yes | Table-driven | Good |
| LR(1) / LALR(1) | Yes | Grammar-driven | Fair |
| PEG | No (ordered choice) | Rule ordering | Limited |
| Earley | Yes | Grammar-driven | Best |

Key parser patterns:
- Pratt parsing handles operator precedence with a simple table lookup
- Right-associative operators (=, **) use same precedence for recursive call
- Left-associative operators use `prec + 1` for the recursive call
- Error recovery via `_synchronize()` skips to next statement boundary
- Each parse method returns an AST node with source location for error reporting
- Newlines are skipped in expression context but significant at statement boundaries
'''
    ),
    (
        "compiler/type-checker",
        "Implement a type checker that walks an AST and performs type inference, type unification, function signature checking, and reports type errors with source locations.",
        '''Type checker with inference, unification, and comprehensive error reporting:

```python
# type_checker.py — Type inference and checking over the AST
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from lexer import SourceLocation
from parser import (
    ASTNode, Program, FunctionDecl, LetDecl, Block, IfStmt, WhileStmt,
    ReturnStmt, ExprStatement, BinaryOp, UnaryOp, CallExpr, AssignExpr,
    Identifier, IntegerLiteral, FloatLiteral, StringLiteral, BoolLiteral,
    NilLiteral, MemberExpr, IndexExpr, Parameter,
)


# ============================================================
# Type Representation
# ============================================================

@dataclass(frozen=True)
class Type:
    """Base type."""
    def __str__(self) -> str:
        return "unknown"

@dataclass(frozen=True)
class IntType(Type):
    def __str__(self) -> str: return "int"

@dataclass(frozen=True)
class FloatType(Type):
    def __str__(self) -> str: return "float"

@dataclass(frozen=True)
class BoolType(Type):
    def __str__(self) -> str: return "bool"

@dataclass(frozen=True)
class StringType(Type):
    def __str__(self) -> str: return "string"

@dataclass(frozen=True)
class NilType(Type):
    def __str__(self) -> str: return "nil"

@dataclass(frozen=True)
class VoidType(Type):
    def __str__(self) -> str: return "void"

@dataclass(frozen=True)
class FunctionType(Type):
    param_types: tuple[Type, ...]
    return_type: Type
    def __str__(self) -> str:
        params = ", ".join(str(p) for p in self.param_types)
        return f"fn({params}) -> {self.return_type}"

@dataclass(frozen=True)
class ArrayType(Type):
    element_type: Type
    def __str__(self) -> str:
        return f"[{self.element_type}]"

@dataclass
class TypeVar(Type):
    """Type variable for inference — gets resolved during unification."""
    id: int
    resolved: Type | None = None

    def __str__(self) -> str:
        if self.resolved:
            return str(self.resolved)
        return f"T{self.id}"

    def __hash__(self) -> int:
        return hash(self.id)

    def __eq__(self, other) -> bool:
        if isinstance(other, TypeVar):
            return self.id == other.id
        return NotImplemented


BUILTIN_TYPES: dict[str, Type] = {
    "int": IntType(),
    "float": FloatType(),
    "bool": BoolType(),
    "string": StringType(),
    "void": VoidType(),
}


# ============================================================
# Type Environment (Scope)
# ============================================================

class TypeEnv:
    """Lexically scoped type environment."""

    def __init__(self, parent: TypeEnv | None = None):
        self.parent = parent
        self._bindings: dict[str, Type] = {}

    def define(self, name: str, typ: Type):
        self._bindings[name] = typ

    def lookup(self, name: str) -> Type | None:
        if name in self._bindings:
            return self._bindings[name]
        if self.parent:
            return self.parent.lookup(name)
        return None

    def child(self) -> TypeEnv:
        return TypeEnv(parent=self)


# ============================================================
# Type Error
# ============================================================

@dataclass
class TypeError_:
    message: str
    location: SourceLocation

    def __str__(self) -> str:
        return f"TypeError at {self.location}: {self.message}"


# ============================================================
# Type Checker
# ============================================================

class TypeChecker:
    """Walks the AST, infers types, checks constraints, reports errors."""

    def __init__(self):
        self.errors: list[TypeError_] = []
        self._next_type_var = 0
        self._current_function_return: Type | None = None

    def _fresh_type_var(self) -> TypeVar:
        tv = TypeVar(id=self._next_type_var)
        self._next_type_var += 1
        return tv

    def _resolve(self, typ: Type) -> Type:
        """Follow type variable chains to find the concrete type."""
        if isinstance(typ, TypeVar):
            if typ.resolved is not None:
                typ.resolved = self._resolve(typ.resolved)
                return typ.resolved
        return typ

    def _unify(self, a: Type, b: Type, location: SourceLocation) -> Type:
        """Unify two types: either they are compatible or we report an error."""
        a = self._resolve(a)
        b = self._resolve(b)

        if isinstance(a, TypeVar):
            a.resolved = b
            return b
        if isinstance(b, TypeVar):
            b.resolved = a
            return a

        if type(a) == type(b):
            if isinstance(a, FunctionType) and isinstance(b, FunctionType):
                if len(a.param_types) != len(b.param_types):
                    self._error(
                        f"Function arity mismatch: {len(a.param_types)} vs {len(b.param_types)}",
                        location,
                    )
                    return a
                for pa, pb in zip(a.param_types, b.param_types):
                    self._unify(pa, pb, location)
                self._unify(a.return_type, b.return_type, location)
            return a

        # Numeric coercion: int -> float
        if isinstance(a, IntType) and isinstance(b, FloatType):
            return FloatType()
        if isinstance(a, FloatType) and isinstance(b, IntType):
            return FloatType()

        # Nil is compatible with any nullable type
        if isinstance(a, NilType) or isinstance(b, NilType):
            return a if not isinstance(a, NilType) else b

        self._error(f"Type mismatch: {a} vs {b}", location)
        return a

    def _error(self, message: str, location: SourceLocation):
        self.errors.append(TypeError_(message, location))

    def _resolve_annotation(self, annotation: str | None) -> Type:
        if annotation is None:
            return self._fresh_type_var()
        typ = BUILTIN_TYPES.get(annotation)
        if typ is None:
            return self._fresh_type_var()  # Unknown type, infer later
        return typ

    # --- Checking entry point ---

    def check(self, program: Program) -> list[TypeError_]:
        env = TypeEnv()

        # Register builtins
        env.define("print", FunctionType(
            param_types=(self._fresh_type_var(),),
            return_type=VoidType(),
        ))

        for stmt in program.statements:
            self._check_statement(stmt, env)

        return self.errors

    def _check_statement(self, node: ASTNode, env: TypeEnv):
        match node:
            case FunctionDecl():
                self._check_function(node, env)
            case LetDecl():
                self._check_let(node, env)
            case IfStmt():
                self._check_if(node, env)
            case WhileStmt():
                cond_type = self._check_expr(node.condition, env)
                self._unify(cond_type, BoolType(), node.condition.location)
                self._check_block(node.body, env)
            case ReturnStmt():
                if node.value:
                    ret_type = self._check_expr(node.value, env)
                    if self._current_function_return:
                        self._unify(ret_type, self._current_function_return, node.location)
                elif self._current_function_return:
                    self._unify(VoidType(), self._current_function_return, node.location)
            case Block():
                self._check_block(node, env)
            case ExprStatement():
                self._check_expr(node.expression, env)

    def _check_function(self, node: FunctionDecl, env: TypeEnv):
        param_types = []
        func_env = env.child()

        for param in node.params:
            p_type = self._resolve_annotation(param.type_annotation)
            param_types.append(p_type)
            func_env.define(param.name, p_type)

        return_type = self._resolve_annotation(node.return_type)
        func_type = FunctionType(tuple(param_types), return_type)
        env.define(node.name, func_type)

        # Allow recursion
        func_env.define(node.name, func_type)

        prev_return = self._current_function_return
        self._current_function_return = return_type
        self._check_block(node.body, func_env)
        self._current_function_return = prev_return

    def _check_let(self, node: LetDecl, env: TypeEnv):
        declared_type = self._resolve_annotation(node.type_annotation)
        if node.initializer:
            init_type = self._check_expr(node.initializer, env)
            result_type = self._unify(declared_type, init_type, node.location)
            env.define(node.name, result_type)
        else:
            env.define(node.name, declared_type)

    def _check_if(self, node: IfStmt, env: TypeEnv):
        cond_type = self._check_expr(node.condition, env)
        self._unify(cond_type, BoolType(), node.condition.location)
        self._check_block(node.then_body, env)
        if isinstance(node.else_body, Block):
            self._check_block(node.else_body, env)
        elif isinstance(node.else_body, IfStmt):
            self._check_if(node.else_body, env)

    def _check_block(self, block: Block, env: TypeEnv):
        block_env = env.child()
        for stmt in block.statements:
            self._check_statement(stmt, block_env)

    # --- Expression type checking ---

    def _check_expr(self, node: ASTNode, env: TypeEnv) -> Type:
        match node:
            case IntegerLiteral():
                return IntType()
            case FloatLiteral():
                return FloatType()
            case StringLiteral():
                return StringType()
            case BoolLiteral():
                return BoolType()
            case NilLiteral():
                return NilType()
            case Identifier():
                typ = env.lookup(node.name)
                if typ is None:
                    self._error(f"Undefined variable: '{node.name}'", node.location)
                    return self._fresh_type_var()
                return typ
            case BinaryOp():
                return self._check_binary(node, env)
            case UnaryOp():
                return self._check_unary(node, env)
            case CallExpr():
                return self._check_call(node, env)
            case AssignExpr():
                target_type = self._check_expr(node.target, env)
                value_type = self._check_expr(node.value, env)
                return self._unify(target_type, value_type, node.location)
            case _:
                self._error(f"Unknown expression type: {type(node).__name__}", node.location)
                return self._fresh_type_var()

    def _check_binary(self, node: BinaryOp, env: TypeEnv) -> Type:
        left = self._check_expr(node.left, env)
        right = self._check_expr(node.right, env)

        if node.op in ("+", "-", "*", "/", "%", "**"):
            result = self._unify(left, right, node.location)
            # String concatenation
            if node.op == "+" and isinstance(self._resolve(left), StringType):
                return StringType()
            return result

        if node.op in ("==", "!=", "<", ">", "<=", ">="):
            self._unify(left, right, node.location)
            return BoolType()

        if node.op in ("and", "or"):
            self._unify(left, BoolType(), node.left.location)
            self._unify(right, BoolType(), node.right.location)
            return BoolType()

        self._error(f"Unknown operator: {node.op}", node.location)
        return self._fresh_type_var()

    def _check_unary(self, node: UnaryOp, env: TypeEnv) -> Type:
        operand = self._check_expr(node.operand, env)
        if node.op == "-":
            return operand  # Numeric negation preserves type
        if node.op == "not":
            self._unify(operand, BoolType(), node.operand.location)
            return BoolType()
        return self._fresh_type_var()

    def _check_call(self, node: CallExpr, env: TypeEnv) -> Type:
        callee_type = self._check_expr(node.callee, env)
        callee_type = self._resolve(callee_type)

        if not isinstance(callee_type, FunctionType):
            self._error(
                f"Cannot call non-function type: {callee_type}", node.location
            )
            return self._fresh_type_var()

        if len(node.arguments) != len(callee_type.param_types):
            self._error(
                f"Expected {len(callee_type.param_types)} arguments, "
                f"got {len(node.arguments)}",
                node.location,
            )

        for arg, param_type in zip(node.arguments, callee_type.param_types):
            arg_type = self._check_expr(arg, env)
            self._unify(arg_type, param_type, arg.location)

        return callee_type.return_type
```

| Type System Feature | Implementation | Complexity |
|---|---|---|
| Explicit annotations | Resolve from type name table | Simple |
| Local type inference | Fresh TypeVar + unification | Medium |
| Numeric coercion | int->float in unification | Simple |
| Function types | FunctionType(params, return) | Medium |
| Generics/parametric | TypeVar with constraints | Complex |
| Structural typing | Unify by structure, not name | Complex |

Key type checker patterns:
- Type variables enable inference: unknown types get fresh variables, resolved by unification
- Unification either makes two types equal or reports an error
- TypeVar chains are resolved lazily (path compression on access)
- Scoped environments with parent chain implement lexical scoping
- Numeric coercion (int -> float) is handled as a special case in unification
- Every error includes source location for precise error messages
'''
    ),
    (
        "compiler/bytecode-generation",
        "Implement a bytecode compiler that translates the AST into stack-based bytecode instructions, with a constant pool, local variable slots, and jump instructions for control flow.",
        '''Stack-based bytecode compiler with constant pool, locals, and control flow:

```python
# bytecode.py — Bytecode compiler from AST to stack-based instructions
from __future__ import annotations
from dataclasses import dataclass, field
from enum import IntEnum, auto
from typing import Any

from parser import (
    ASTNode, Program, FunctionDecl, LetDecl, Block, IfStmt, WhileStmt,
    ReturnStmt, ExprStatement, BinaryOp, UnaryOp, CallExpr, AssignExpr,
    Identifier, IntegerLiteral, FloatLiteral, StringLiteral, BoolLiteral,
    NilLiteral,
)


class OpCode(IntEnum):
    """Stack-based virtual machine instruction set."""
    # Stack manipulation
    CONST = 0        # Push constant from pool: CONST <idx>
    POP = 1          # Discard top of stack
    DUP = 2          # Duplicate top of stack

    # Local variables
    LOAD_LOCAL = 10  # Push local variable: LOAD_LOCAL <slot>
    STORE_LOCAL = 11 # Pop and store to local: STORE_LOCAL <slot>

    # Global variables
    LOAD_GLOBAL = 12
    STORE_GLOBAL = 13

    # Arithmetic (pop 2, push 1)
    ADD = 20
    SUB = 21
    MUL = 22
    DIV = 23
    MOD = 24
    POW = 25
    NEG = 26         # Unary negate (pop 1, push 1)

    # Comparison (pop 2, push bool)
    EQ = 30
    NEQ = 31
    LT = 32
    LTE = 33
    GT = 34
    GTE = 35

    # Logic
    NOT = 40         # Unary not (pop 1, push 1)
    AND = 41
    OR = 42

    # Control flow
    JUMP = 50        # Unconditional jump: JUMP <offset>
    JUMP_IF_FALSE = 51  # Pop, jump if falsy: JUMP_IF_FALSE <offset>
    JUMP_IF_TRUE = 52

    # Functions
    CALL = 60        # Call function: CALL <arg_count>
    RETURN = 61      # Return from function
    RETURN_NONE = 62 # Return nil

    # Built-ins
    PRINT = 70

    # Constants
    PUSH_TRUE = 80
    PUSH_FALSE = 81
    PUSH_NIL = 82

    HALT = 255


@dataclass
class Instruction:
    opcode: OpCode
    operand: int = 0  # Instruction argument (constant index, slot, offset)

    def __repr__(self) -> str:
        if self.operand != 0 or self.opcode in (
            OpCode.CONST, OpCode.LOAD_LOCAL, OpCode.STORE_LOCAL,
            OpCode.JUMP, OpCode.JUMP_IF_FALSE, OpCode.JUMP_IF_TRUE,
            OpCode.CALL, OpCode.LOAD_GLOBAL, OpCode.STORE_GLOBAL,
        ):
            return f"{self.opcode.name:20s} {self.operand}"
        return self.opcode.name


@dataclass
class CompiledFunction:
    """Bytecode for a single function."""
    name: str
    arity: int                                  # Number of parameters
    local_count: int = 0                        # Total local variable slots
    instructions: list[Instruction] = field(default_factory=list)
    constants: list[Any] = field(default_factory=list)

    def add_constant(self, value: Any) -> int:
        """Add a constant to the pool and return its index."""
        # Reuse existing constants
        for i, existing in enumerate(self.constants):
            if existing == value and type(existing) == type(value):
                return i
        idx = len(self.constants)
        self.constants.append(value)
        return idx

    def emit(self, opcode: OpCode, operand: int = 0) -> int:
        """Emit an instruction and return its index."""
        idx = len(self.instructions)
        self.instructions.append(Instruction(opcode, operand))
        return idx

    def patch_jump(self, instruction_idx: int, target: int | None = None):
        """Backpatch a jump instruction with the correct target offset."""
        if target is None:
            target = len(self.instructions)
        self.instructions[instruction_idx].operand = target

    def disassemble(self) -> str:
        lines = [f"=== {self.name} (arity={self.arity}, locals={self.local_count}) ==="]
        lines.append(f"Constants: {self.constants}")
        for i, inst in enumerate(self.instructions):
            lines.append(f"  {i:04d}  {inst}")
        return "\\n".join(lines)


@dataclass
class CompilerScope:
    """Tracks local variables within a scope."""
    locals: dict[str, int] = field(default_factory=dict)  # name -> slot index
    next_slot: int = 0
    parent: CompilerScope | None = None

    def define(self, name: str) -> int:
        slot = self.next_slot
        self.locals[name] = slot
        self.next_slot += 1
        return slot

    def resolve(self, name: str) -> int | None:
        if name in self.locals:
            return self.locals[name]
        if self.parent:
            return self.parent.resolve(name)
        return None


class Compiler:
    """Compiles AST to stack-based bytecode."""

    def __init__(self):
        self.functions: dict[str, CompiledFunction] = {}
        self._globals: dict[str, int] = {}
        self._next_global = 0

    def compile(self, program: Program) -> CompiledFunction:
        """Compile entire program into a top-level function."""
        main = CompiledFunction(name="<main>", arity=0)
        scope = CompilerScope()

        for stmt in program.statements:
            self._compile_statement(stmt, main, scope)

        main.emit(OpCode.HALT)
        main.local_count = scope.next_slot
        self.functions["<main>"] = main
        return main

    def _compile_statement(self, node: ASTNode, func: CompiledFunction, scope: CompilerScope):
        match node:
            case FunctionDecl():
                self._compile_function_decl(node, func, scope)
            case LetDecl():
                self._compile_let(node, func, scope)
            case IfStmt():
                self._compile_if(node, func, scope)
            case WhileStmt():
                self._compile_while(node, func, scope)
            case ReturnStmt():
                if node.value:
                    self._compile_expr(node.value, func, scope)
                    func.emit(OpCode.RETURN)
                else:
                    func.emit(OpCode.RETURN_NONE)
            case Block():
                inner_scope = CompilerScope(parent=scope)
                inner_scope.next_slot = scope.next_slot
                for stmt in node.statements:
                    self._compile_statement(stmt, func, inner_scope)
                scope.next_slot = max(scope.next_slot, inner_scope.next_slot)
            case ExprStatement():
                self._compile_expr(node.expression, func, scope)
                func.emit(OpCode.POP)

    def _compile_function_decl(self, node: FunctionDecl, parent: CompiledFunction, scope: CompilerScope):
        """Compile function body into a separate CompiledFunction."""
        fn = CompiledFunction(name=node.name, arity=len(node.params))
        fn_scope = CompilerScope()

        # Parameters are the first local slots
        for param in node.params:
            fn_scope.define(param.name)

        # Compile body
        for stmt in node.body.statements:
            self._compile_statement(stmt, fn, fn_scope)

        fn.emit(OpCode.RETURN_NONE)  # Implicit return
        fn.local_count = fn_scope.next_slot
        self.functions[node.name] = fn

        # In the parent scope, store function reference as a global
        global_idx = self._define_global(node.name)
        const_idx = parent.add_constant(node.name)
        parent.emit(OpCode.CONST, const_idx)
        parent.emit(OpCode.STORE_GLOBAL, global_idx)

    def _define_global(self, name: str) -> int:
        if name not in self._globals:
            self._globals[name] = self._next_global
            self._next_global += 1
        return self._globals[name]

    def _compile_let(self, node: LetDecl, func: CompiledFunction, scope: CompilerScope):
        slot = scope.define(node.name)
        if node.initializer:
            self._compile_expr(node.initializer, func, scope)
        else:
            func.emit(OpCode.PUSH_NIL)
        func.emit(OpCode.STORE_LOCAL, slot)

    def _compile_if(self, node: IfStmt, func: CompiledFunction, scope: CompilerScope):
        self._compile_expr(node.condition, func, scope)
        jump_false = func.emit(OpCode.JUMP_IF_FALSE, 0)  # Placeholder

        # Then branch
        self._compile_statement(node.then_body, func, scope)

        if node.else_body:
            jump_end = func.emit(OpCode.JUMP, 0)  # Skip else
            func.patch_jump(jump_false)
            self._compile_statement(node.else_body, func, scope)
            func.patch_jump(jump_end)
        else:
            func.patch_jump(jump_false)

    def _compile_while(self, node: WhileStmt, func: CompiledFunction, scope: CompilerScope):
        loop_start = len(func.instructions)
        self._compile_expr(node.condition, func, scope)
        jump_exit = func.emit(OpCode.JUMP_IF_FALSE, 0)

        self._compile_statement(node.body, func, scope)
        func.emit(OpCode.JUMP, loop_start)

        func.patch_jump(jump_exit)

    def _compile_expr(self, node: ASTNode, func: CompiledFunction, scope: CompilerScope):
        match node:
            case IntegerLiteral():
                idx = func.add_constant(node.value)
                func.emit(OpCode.CONST, idx)
            case FloatLiteral():
                idx = func.add_constant(node.value)
                func.emit(OpCode.CONST, idx)
            case StringLiteral():
                idx = func.add_constant(node.value)
                func.emit(OpCode.CONST, idx)
            case BoolLiteral():
                func.emit(OpCode.PUSH_TRUE if node.value else OpCode.PUSH_FALSE)
            case NilLiteral():
                func.emit(OpCode.PUSH_NIL)
            case Identifier():
                slot = scope.resolve(node.name)
                if slot is not None:
                    func.emit(OpCode.LOAD_LOCAL, slot)
                else:
                    global_idx = self._globals.get(node.name)
                    if global_idx is not None:
                        func.emit(OpCode.LOAD_GLOBAL, global_idx)
                    else:
                        idx = func.add_constant(node.name)
                        func.emit(OpCode.LOAD_GLOBAL, self._define_global(node.name))
            case BinaryOp():
                self._compile_binary(node, func, scope)
            case UnaryOp():
                self._compile_expr(node.operand, func, scope)
                match node.op:
                    case "-": func.emit(OpCode.NEG)
                    case "not": func.emit(OpCode.NOT)
            case CallExpr():
                self._compile_call(node, func, scope)
            case AssignExpr():
                self._compile_expr(node.value, func, scope)
                func.emit(OpCode.DUP)  # Assignment is an expression
                if isinstance(node.target, Identifier):
                    slot = scope.resolve(node.target.name)
                    if slot is not None:
                        func.emit(OpCode.STORE_LOCAL, slot)
                    else:
                        func.emit(OpCode.STORE_GLOBAL, self._define_global(node.target.name))

    def _compile_binary(self, node: BinaryOp, func: CompiledFunction, scope: CompilerScope):
        self._compile_expr(node.left, func, scope)
        self._compile_expr(node.right, func, scope)
        op_map = {
            "+": OpCode.ADD, "-": OpCode.SUB, "*": OpCode.MUL,
            "/": OpCode.DIV, "%": OpCode.MOD, "**": OpCode.POW,
            "==": OpCode.EQ, "!=": OpCode.NEQ,
            "<": OpCode.LT, "<=": OpCode.LTE,
            ">": OpCode.GT, ">=": OpCode.GTE,
            "and": OpCode.AND, "or": OpCode.OR,
        }
        opcode = op_map.get(node.op)
        if opcode:
            func.emit(opcode)

    def _compile_call(self, node: CallExpr, func: CompiledFunction, scope: CompilerScope):
        # Check for built-in print
        if isinstance(node.callee, Identifier) and node.callee.name == "print":
            for arg in node.arguments:
                self._compile_expr(arg, func, scope)
            func.emit(OpCode.PRINT)
            func.emit(OpCode.PUSH_NIL)  # print returns nil
            return

        # Compile callee (pushes function reference)
        self._compile_expr(node.callee, func, scope)
        # Compile arguments
        for arg in node.arguments:
            self._compile_expr(arg, func, scope)
        func.emit(OpCode.CALL, len(node.arguments))
```

Example bytecode output:

```
=== <main> (arity=0, locals=1) ===
Constants: ['fib', 10]
  0000  CONST                0       # Push "fib"
  0001  STORE_GLOBAL         0       # Store as global
  0002  LOAD_GLOBAL          0       # Load fib function
  0003  CONST                1       # Push 10
  0004  CALL                 1       # Call fib(10)
  0005  STORE_LOCAL           0       # let result = ...
  0006  LOAD_LOCAL            0       # Load result
  0007  PRINT                0       # print(result)
  0008  PUSH_NIL             0
  0009  POP                  0
  0010  HALT                 0
```

| VM Architecture | Operand Source | Pros | Cons |
|---|---|---|---|
| Stack-based (this) | Implicit (top of stack) | Simple compiler, compact bytecode | More instructions |
| Register-based | Explicit register operands | Fewer instructions, faster dispatch | Complex compiler |
| Three-address | src1, src2, dst | Optimizable (SSA form) | Largest bytecode |

Key bytecode compilation patterns:
- Constant pool deduplicates repeated values (strings, numbers)
- Local variables use indexed slots (faster than hash table lookup)
- Jump backpatching: emit placeholder, fill in target offset later
- Control flow compiles to conditional jumps and unconditional jumps
- Function calls push arguments left-to-right, then emit CALL with arity
- Each function gets its own CompiledFunction with separate constant pool and locals
'''
    ),
    (
        "compiler/tree-walking-interpreter",
        "Implement a tree-walking interpreter that directly executes the AST, with an environment for variable scoping, first-class functions with closures, and a REPL loop.",
        '''Tree-walking interpreter with closures, environments, and REPL:

```python
# interpreter.py — Tree-walking interpreter executing AST directly
from __future__ import annotations
import time
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

from lexer import Lexer, SourceLocation
from parser import (
    Parser, ASTNode, Program, FunctionDecl, LetDecl, Block, IfStmt, WhileStmt,
    ReturnStmt, ExprStatement, BinaryOp, UnaryOp, CallExpr, AssignExpr,
    Identifier, IntegerLiteral, FloatLiteral, StringLiteral, BoolLiteral,
    NilLiteral, MemberExpr, IndexExpr,
)


class Environment:
    """Lexically scoped variable environment with parent chain."""

    def __init__(self, parent: Environment | None = None):
        self.parent = parent
        self._values: dict[str, Any] = {}

    def define(self, name: str, value: Any):
        self._values[name] = value

    def get(self, name: str) -> Any:
        if name in self._values:
            return self._values[name]
        if self.parent:
            return self.parent.get(name)
        raise RuntimeError(f"Undefined variable: '{name}'")

    def set(self, name: str, value: Any):
        if name in self._values:
            self._values[name] = value
            return
        if self.parent:
            self.parent.set(name, value)
            return
        raise RuntimeError(f"Undefined variable: '{name}'")

    def child(self) -> Environment:
        return Environment(parent=self)


class ReturnException(Exception):
    """Used to unwind the call stack on return statements."""
    def __init__(self, value: Any):
        self.value = value


@dataclass
class HiveFunction:
    """User-defined function with closure over its defining environment."""
    name: str
    params: list[str]
    body: Block
    closure: Environment  # Captured environment at definition time

    def __repr__(self) -> str:
        return f"<fn {self.name}({', '.join(self.params)})>"


@dataclass
class BuiltinFunction:
    """Built-in function wrapping a Python callable."""
    name: str
    func: Callable
    arity: int = -1  # -1 means variadic

    def __repr__(self) -> str:
        return f"<builtin {self.name}>"


class Interpreter:
    """Tree-walking interpreter that directly evaluates AST nodes."""

    def __init__(self):
        self.globals = Environment()
        self._setup_builtins()
        self._call_depth = 0
        self._max_call_depth = 1000

    def _setup_builtins(self):
        self.globals.define("print", BuiltinFunction(
            "print", lambda *args: print(*args), arity=-1
        ))
        self.globals.define("len", BuiltinFunction(
            "len", lambda x: len(x), arity=1
        ))
        self.globals.define("str", BuiltinFunction(
            "str", lambda x: str(x), arity=1
        ))
        self.globals.define("int", BuiltinFunction(
            "int", lambda x: int(x), arity=1
        ))
        self.globals.define("float", BuiltinFunction(
            "float", lambda x: float(x), arity=1
        ))
        self.globals.define("clock", BuiltinFunction(
            "clock", lambda: time.time(), arity=0
        ))
        self.globals.define("type", BuiltinFunction(
            "type", lambda x: type(x).__name__, arity=1
        ))
        self.globals.define("input", BuiltinFunction(
            "input", lambda prompt="": input(prompt), arity=-1
        ))

    def interpret(self, program: Program):
        """Execute a complete program."""
        for stmt in program.statements:
            self._execute(stmt, self.globals)

    def _execute(self, node: ASTNode, env: Environment) -> Any:
        match node:
            case Program():
                for stmt in node.statements:
                    self._execute(stmt, env)
            case FunctionDecl():
                func = HiveFunction(
                    name=node.name,
                    params=[p.name for p in node.params],
                    body=node.body,
                    closure=env,  # Capture current environment (closure)
                )
                env.define(node.name, func)
            case LetDecl():
                value = None
                if node.initializer:
                    value = self._evaluate(node.initializer, env)
                env.define(node.name, value)
            case Block():
                block_env = env.child()
                for stmt in node.statements:
                    self._execute(stmt, block_env)
            case IfStmt():
                if self._is_truthy(self._evaluate(node.condition, env)):
                    self._execute(node.then_body, env)
                elif node.else_body:
                    self._execute(node.else_body, env)
            case WhileStmt():
                while self._is_truthy(self._evaluate(node.condition, env)):
                    self._execute(node.body, env)
            case ReturnStmt():
                value = None
                if node.value:
                    value = self._evaluate(node.value, env)
                raise ReturnException(value)
            case ExprStatement():
                self._evaluate(node.expression, env)
            case _:
                raise RuntimeError(f"Unknown statement: {type(node).__name__}")

    def _evaluate(self, node: ASTNode, env: Environment) -> Any:
        match node:
            case IntegerLiteral():  return node.value
            case FloatLiteral():    return node.value
            case StringLiteral():   return node.value
            case BoolLiteral():     return node.value
            case NilLiteral():      return None
            case Identifier():      return env.get(node.name)
            case BinaryOp():        return self._eval_binary(node, env)
            case UnaryOp():         return self._eval_unary(node, env)
            case CallExpr():        return self._eval_call(node, env)
            case AssignExpr():
                value = self._evaluate(node.value, env)
                if isinstance(node.target, Identifier):
                    env.set(node.target.name, value)
                return value
            case IndexExpr():
                obj = self._evaluate(node.object, env)
                idx = self._evaluate(node.index, env)
                return obj[idx]
            case _:
                raise RuntimeError(f"Unknown expression: {type(node).__name__}")

    def _eval_binary(self, node: BinaryOp, env: Environment) -> Any:
        left = self._evaluate(node.left, env)

        # Short-circuit logical operators
        if node.op == "and":
            return left if not self._is_truthy(left) else self._evaluate(node.right, env)
        if node.op == "or":
            return left if self._is_truthy(left) else self._evaluate(node.right, env)

        right = self._evaluate(node.right, env)

        match node.op:
            case "+":
                if isinstance(left, str) or isinstance(right, str):
                    return str(left) + str(right)
                return left + right
            case "-":  return left - right
            case "*":  return left * right
            case "/":
                if right == 0:
                    raise RuntimeError("Division by zero")
                return left / right
            case "%":  return left % right
            case "**": return left ** right
            case "==": return left == right
            case "!=": return left != right
            case "<":  return left < right
            case "<=": return left <= right
            case ">":  return left > right
            case ">=": return left >= right
            case _:
                raise RuntimeError(f"Unknown operator: {node.op}")

    def _eval_unary(self, node: UnaryOp, env: Environment) -> Any:
        operand = self._evaluate(node.operand, env)
        match node.op:
            case "-":   return -operand
            case "not": return not self._is_truthy(operand)
            case _:     raise RuntimeError(f"Unknown unary: {node.op}")

    def _eval_call(self, node: CallExpr, env: Environment) -> Any:
        callee = self._evaluate(node.callee, env)
        args = [self._evaluate(arg, env) for arg in node.arguments]

        if isinstance(callee, BuiltinFunction):
            return callee.func(*args)

        if isinstance(callee, HiveFunction):
            if len(args) != len(callee.params):
                raise RuntimeError(
                    f"{callee.name} expects {len(callee.params)} args, got {len(args)}"
                )

            self._call_depth += 1
            if self._call_depth > self._max_call_depth:
                raise RuntimeError("Maximum recursion depth exceeded")

            # Create new environment extending the closure (not the caller)
            call_env = callee.closure.child()
            for param, arg in zip(callee.params, args):
                call_env.define(param, arg)

            try:
                self._execute(callee.body, call_env)
            except ReturnException as ret:
                return ret.value
            finally:
                self._call_depth -= 1

            return None  # Implicit return nil

        raise RuntimeError(f"Cannot call {type(callee).__name__}")

    @staticmethod
    def _is_truthy(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return len(value) > 0
        return True


# ============================================================
# REPL
# ============================================================

def repl():
    """Interactive Read-Eval-Print Loop."""
    interpreter = Interpreter()
    print("Hive Language REPL (type 'exit' to quit)")

    while True:
        try:
            line = input(">>> ")
            if line.strip() in ("exit", "quit"):
                break
            if not line.strip():
                continue

            # Multi-line input: if line ends with {, read until balanced
            while line.count("{") > line.count("}"):
                line += "\\n" + input("... ")

            lexer = Lexer(line, "<repl>")
            tokens = lexer.tokenize()
            if lexer.errors:
                for err in lexer.errors:
                    print(f"  {err}")
                continue

            parser = Parser(tokens)
            program = parser.parse()
            if parser.errors:
                for err in parser.errors:
                    print(f"  {err}")
                continue

            interpreter.interpret(program)

        except ReturnException as ret:
            print(ret.value)
        except RuntimeError as e:
            print(f"  Runtime error: {e}")
        except KeyboardInterrupt:
            print()
        except EOFError:
            break

    print("Goodbye!")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        # File mode
        source = open(sys.argv[1]).read()
        lexer = Lexer(source, sys.argv[1])
        tokens = lexer.tokenize()
        parser = Parser(tokens)
        program = parser.parse()
        interpreter = Interpreter()
        interpreter.interpret(program)
    else:
        # REPL mode
        repl()
```

Execution model comparison:

| Strategy | Speed | Complexity | Debug-ability | Best For |
|---|---|---|---|---|
| Tree-walking (this) | Slowest | Simplest | Best | Prototyping, scripting |
| Bytecode VM | 10-50x faster | Medium | Good | Production interpreters |
| JIT compilation | 50-500x faster | Complex | Harder | Performance-critical |
| Transpilation | Depends on target | Low-Medium | Good | Compile to JS/C |
| AOT native | Fastest | Most complex | Hardest | Systems languages |

Key interpreter patterns:
- Closures capture the *defining* environment, not the calling environment
- ReturnException unwinds the call stack cleanly without breaking statement execution
- Short-circuit evaluation for `and`/`or` avoids evaluating the right operand unnecessarily
- Call depth tracking prevents stack overflow from infinite recursion
- REPL detects multi-line input by tracking brace balance
- Builtins are wrapped as BuiltinFunction objects for uniform calling convention
'''
    ),
]
