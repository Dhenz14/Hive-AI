"""Functional programming — immutability, monads, algebraic data types, FP in Python."""

PAIRS = [
    (
        "paradigms/functional-python",
        "Show functional programming patterns in Python: pure functions, immutability, function composition, monads, and when FP improves code quality.",
        '''Functional programming patterns that improve Python code:

```python
from typing import TypeVar, Callable, Generic, Optional, Iterator
from dataclasses import dataclass, replace
from functools import reduce, partial, wraps
from itertools import chain, islice, groupby
from operator import attrgetter, itemgetter

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")

# --- Pure functions and immutability ---

# BAD: Mutates input, side effects
def process_orders_impure(orders):
    for order in orders:
        order["total"] = order["price"] * order["quantity"]
        if order["total"] > 100:
            order["discount"] = 0.1
    return orders  # Modified in place!

# GOOD: Pure function, returns new data
def calculate_total(order: dict) -> dict:
    total = order["price"] * order["quantity"]
    discount = 0.1 if total > 100 else 0
    return {**order, "total": total, "discount": discount}

def process_orders_pure(orders: list[dict]) -> list[dict]:
    return [calculate_total(o) for o in orders]

# --- Immutable data with frozen dataclasses ---

@dataclass(frozen=True)
class Money:
    amount: int  # Store as cents to avoid float issues
    currency: str

    def add(self, other: "Money") -> "Money":
        assert self.currency == other.currency
        return Money(self.amount + other.amount, self.currency)

    def multiply(self, factor: int) -> "Money":
        return Money(self.amount * factor, self.currency)

@dataclass(frozen=True)
class OrderLine:
    product: str
    unit_price: Money
    quantity: int

    @property
    def total(self) -> Money:
        return self.unit_price.multiply(self.quantity)

@dataclass(frozen=True)
class Order:
    lines: tuple[OrderLine, ...]  # Tuple for immutability

    def add_line(self, line: OrderLine) -> "Order":
        return replace(self, lines=self.lines + (line,))

    @property
    def total(self) -> Money:
        return reduce(lambda acc, l: acc.add(l.total), self.lines,
                       Money(0, self.lines[0].unit_price.currency))

# --- Result monad (railway-oriented programming) ---

@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T

    def map(self, fn: Callable[[T], U]) -> "Result[U, E]":
        return Ok(fn(self.value))

    def flat_map(self, fn: Callable[[T], "Result[U, E]"]) -> "Result[U, E]":
        return fn(self.value)

    def unwrap_or(self, default: T) -> T:
        return self.value

@dataclass(frozen=True)
class Err(Generic[E]):
    error: E

    def map(self, fn) -> "Err[E]":
        return self  # Short-circuit on error

    def flat_map(self, fn) -> "Err[E]":
        return self

    def unwrap_or(self, default):
        return default

Result = Ok[T] | Err[E]

def validate_email(email: str) -> Result[str, str]:
    if "@" not in email:
        return Err("Invalid email format")
    return Ok(email.lower().strip())

def validate_age(age: int) -> Result[int, str]:
    if age < 0 or age > 150:
        return Err(f"Invalid age: {age}")
    return Ok(age)

# Chain validations (railway pattern)
def validate_user(data: dict) -> Result[dict, str]:
    return (
        validate_email(data.get("email", ""))
        .flat_map(lambda email:
            validate_age(data.get("age", 0))
            .map(lambda age: {"email": email, "age": age})
        )
    )

# --- Function composition ---

def compose(*fns: Callable) -> Callable:
    """Right-to-left function composition."""
    return reduce(lambda f, g: lambda x: f(g(x)), fns)

def pipe_val(value, *fns):
    """Left-to-right value piping."""
    return reduce(lambda acc, fn: fn(acc), fns, value)

# Example pipeline:
result = pipe_val(
    raw_data,
    lambda d: [x for x in d if x["status"] == "active"],
    lambda d: sorted(d, key=itemgetter("created_at"), reverse=True),
    lambda d: d[:10],
    lambda d: [{"name": x["name"], "score": x["score"]} for x in d],
)

# --- Lazy evaluation with generators ---

def lazy_filter(predicate: Callable, iterable: Iterator) -> Iterator:
    return (x for x in iterable if predicate(x))

def lazy_map(fn: Callable, iterable: Iterator) -> Iterator:
    return (fn(x) for x in iterable)

def lazy_take(n: int, iterable: Iterator) -> Iterator:
    return islice(iterable, n)

# Process millions of records lazily (constant memory):
def process_large_dataset(records):
    pipeline = records
    pipeline = lazy_filter(lambda r: r["age"] > 18, pipeline)
    pipeline = lazy_map(lambda r: {**r, "category": categorize(r)}, pipeline)
    pipeline = lazy_filter(lambda r: r["category"] != "excluded", pipeline)
    pipeline = lazy_take(1000, pipeline)
    return list(pipeline)  # Only materializes 1000 items

# --- Currying and partial application ---

def curry(fn):
    """Auto-curry a function."""
    import inspect
    n_args = len(inspect.signature(fn).parameters)

    @wraps(fn)
    def curried(*args):
        if len(args) >= n_args:
            return fn(*args)
        return lambda *more: curried(*args, *more)
    return curried

@curry
def add(a: int, b: int) -> int:
    return a + b

add_10 = add(10)       # Partially applied
result = add_10(5)     # 15
```

When FP helps Python code:
- **Data transformation pipelines** — compose, map, filter, reduce
- **Validation chains** — Result monad avoids nested try/except
- **Configuration** — frozen dataclasses prevent accidental mutation
- **Concurrent code** — immutable data eliminates shared state bugs
- **Testing** — pure functions are trivially testable'''
    ),
    (
        "paradigms/compiler-basics",
        "Explain compiler/interpreter basics: lexing, parsing, AST construction, and evaluation. Build a simple expression evaluator in Python.",
        '''Build a simple expression language from scratch:

```python
from dataclasses import dataclass
from typing import Union
from enum import Enum, auto

# --- 1. Lexer (tokenizer) ---

class TokenType(Enum):
    NUMBER = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    LPAREN = auto()
    RPAREN = auto()
    IDENT = auto()
    ASSIGN = auto()
    IF = auto()
    THEN = auto()
    ELSE = auto()
    EOF = auto()

@dataclass
class Token:
    type: TokenType
    value: str
    pos: int

KEYWORDS = {"if": TokenType.IF, "then": TokenType.THEN, "else": TokenType.ELSE}

def tokenize(source: str) -> list[Token]:
    tokens = []
    i = 0
    while i < len(source):
        ch = source[i]

        if ch.isspace():
            i += 1
        elif ch.isdigit() or (ch == '.' and i + 1 < len(source) and source[i+1].isdigit()):
            start = i
            while i < len(source) and (source[i].isdigit() or source[i] == '.'):
                i += 1
            tokens.append(Token(TokenType.NUMBER, source[start:i], start))
        elif ch.isalpha() or ch == '_':
            start = i
            while i < len(source) and (source[i].isalnum() or source[i] == '_'):
                i += 1
            word = source[start:i]
            tt = KEYWORDS.get(word, TokenType.IDENT)
            tokens.append(Token(tt, word, start))
        elif ch == '+': tokens.append(Token(TokenType.PLUS, ch, i)); i += 1
        elif ch == '-': tokens.append(Token(TokenType.MINUS, ch, i)); i += 1
        elif ch == '*': tokens.append(Token(TokenType.STAR, ch, i)); i += 1
        elif ch == '/': tokens.append(Token(TokenType.SLASH, ch, i)); i += 1
        elif ch == '(': tokens.append(Token(TokenType.LPAREN, ch, i)); i += 1
        elif ch == ')': tokens.append(Token(TokenType.RPAREN, ch, i)); i += 1
        elif ch == '=': tokens.append(Token(TokenType.ASSIGN, ch, i)); i += 1
        else:
            raise SyntaxError(f"Unexpected character '{ch}' at position {i}")

    tokens.append(Token(TokenType.EOF, "", i))
    return tokens

# --- 2. AST (Abstract Syntax Tree) ---

@dataclass
class NumberLit:
    value: float

@dataclass
class BinaryOp:
    op: str
    left: "Expr"
    right: "Expr"

@dataclass
class UnaryOp:
    op: str
    operand: "Expr"

@dataclass
class Variable:
    name: str

@dataclass
class Assign:
    name: str
    value: "Expr"

@dataclass
class IfExpr:
    condition: "Expr"
    then_branch: "Expr"
    else_branch: "Expr"

Expr = Union[NumberLit, BinaryOp, UnaryOp, Variable, Assign, IfExpr]

# --- 3. Parser (recursive descent) ---

class Parser:
    """Recursive descent parser with operator precedence."""

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def peek(self) -> Token:
        return self.tokens[self.pos]

    def advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def expect(self, tt: TokenType) -> Token:
        tok = self.advance()
        if tok.type != tt:
            raise SyntaxError(f"Expected {tt.name}, got {tok.type.name} at {tok.pos}")
        return tok

    def parse(self) -> Expr:
        return self.expression()

    def expression(self) -> Expr:
        # Assignment: ident = expr
        if (self.peek().type == TokenType.IDENT and
                self.pos + 1 < len(self.tokens) and
                self.tokens[self.pos + 1].type == TokenType.ASSIGN):
            name = self.advance().value
            self.advance()  # consume =
            value = self.expression()
            return Assign(name, value)

        # If expression
        if self.peek().type == TokenType.IF:
            return self.if_expression()

        return self.additive()

    def if_expression(self) -> Expr:
        self.expect(TokenType.IF)
        condition = self.additive()
        self.expect(TokenType.THEN)
        then_branch = self.expression()
        self.expect(TokenType.ELSE)
        else_branch = self.expression()
        return IfExpr(condition, then_branch, else_branch)

    def additive(self) -> Expr:
        left = self.multiplicative()
        while self.peek().type in (TokenType.PLUS, TokenType.MINUS):
            op = self.advance().value
            right = self.multiplicative()
            left = BinaryOp(op, left, right)
        return left

    def multiplicative(self) -> Expr:
        left = self.unary()
        while self.peek().type in (TokenType.STAR, TokenType.SLASH):
            op = self.advance().value
            right = self.unary()
            left = BinaryOp(op, left, right)
        return left

    def unary(self) -> Expr:
        if self.peek().type == TokenType.MINUS:
            self.advance()
            return UnaryOp("-", self.primary())
        return self.primary()

    def primary(self) -> Expr:
        tok = self.peek()
        if tok.type == TokenType.NUMBER:
            self.advance()
            return NumberLit(float(tok.value))
        if tok.type == TokenType.IDENT:
            self.advance()
            return Variable(tok.value)
        if tok.type == TokenType.LPAREN:
            self.advance()
            expr = self.expression()
            self.expect(TokenType.RPAREN)
            return expr
        raise SyntaxError(f"Unexpected token {tok.type.name} at {tok.pos}")

# --- 4. Evaluator (tree-walk interpreter) ---

class Evaluator:
    def __init__(self):
        self.env: dict[str, float] = {}

    def eval(self, node: Expr) -> float:
        match node:
            case NumberLit(value):
                return value
            case BinaryOp("+", left, right):
                return self.eval(left) + self.eval(right)
            case BinaryOp("-", left, right):
                return self.eval(left) - self.eval(right)
            case BinaryOp("*", left, right):
                return self.eval(left) * self.eval(right)
            case BinaryOp("/", left, right):
                r = self.eval(right)
                if r == 0:
                    raise ZeroDivisionError("Division by zero")
                return self.eval(left) / r
            case UnaryOp("-", operand):
                return -self.eval(operand)
            case Variable(name):
                if name not in self.env:
                    raise NameError(f"Undefined variable: {name}")
                return self.env[name]
            case Assign(name, value):
                result = self.eval(value)
                self.env[name] = result
                return result
            case IfExpr(condition, then_b, else_b):
                return self.eval(then_b) if self.eval(condition) != 0 else self.eval(else_b)

# --- Usage ---

def run(source: str) -> float:
    tokens = tokenize(source)
    parser = Parser(tokens)
    ast = parser.parse()
    evaluator = Evaluator()
    return evaluator.eval(ast)

# Examples:
# run("2 + 3 * 4")           → 14.0
# run("(2 + 3) * 4")         → 20.0
# run("x = 10")              → 10.0
# run("if 1 then 42 else 0") → 42.0
```

Compiler phases:
1. **Lexing** — characters → tokens (tokenization)
2. **Parsing** — tokens → AST (syntax analysis)
3. **Semantic analysis** — type checking, scope resolution
4. **Optimization** — constant folding, dead code elimination
5. **Code generation** — AST → target code (bytecode, machine code)'''
    ),
    (
        "paradigms/rust-ownership",
        "Explain Rust ownership, borrowing, and lifetimes with practical examples. Show how the borrow checker prevents common bugs.",
        '''Rust ownership system — preventing bugs at compile time:

```rust
// --- Ownership Rules ---
// 1. Each value has exactly ONE owner
// 2. When owner goes out of scope, value is dropped
// 3. Ownership can be moved or borrowed

// --- Move semantics ---
fn ownership_move() {
    let s1 = String::from("hello");
    let s2 = s1;           // s1 is MOVED to s2
    // println!("{}", s1);  // Error! s1 no longer valid

    // Fix: clone (explicit deep copy)
    let s3 = s2.clone();
    println!("{} {}", s2, s3);  // Both valid

    // Primitives (Copy trait) are copied, not moved
    let x = 42;
    let y = x;
    println!("{} {}", x, y);  // Both valid (i32 implements Copy)
}

// --- Borrowing (references) ---
fn borrowing_rules() {
    let mut data = vec![1, 2, 3];

    // Immutable borrow: unlimited readers
    let r1 = &data;
    let r2 = &data;
    println!("{:?} {:?}", r1, r2);  // OK: multiple immutable borrows

    // Mutable borrow: exclusive writer
    let r3 = &mut data;
    r3.push(4);
    // let r4 = &data;  // Error! Can't borrow immutably while mutably borrowed
    println!("{:?}", r3);
}

// --- Lifetimes (prevent dangling references) ---

// This won't compile:
// fn dangling() -> &str {
//     let s = String::from("hello");
//     &s  // Error! s is dropped, reference would dangle
// }

// Lifetime annotations tell compiler how long references live
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() { x } else { y }
}

// Lifetime in structs
struct Config<'a> {
    name: &'a str,
    values: &'a [i32],
}

impl<'a> Config<'a> {
    fn get_name(&self) -> &'a str {
        self.name
    }
}

// --- Practical example: safe concurrent data ---

use std::sync::{Arc, Mutex};
use std::thread;

fn safe_concurrent_counter() {
    let counter = Arc::new(Mutex::new(0));
    let mut handles = vec![];

    for _ in 0..10 {
        let counter = Arc::clone(&counter);
        let handle = thread::spawn(move || {
            let mut num = counter.lock().unwrap();
            *num += 1;
            // Mutex automatically unlocked when `num` goes out of scope
        });
        handles.push(handle);
    }

    for handle in handles {
        handle.join().unwrap();
    }
    println!("Count: {}", *counter.lock().unwrap());  // Always 10
}

// --- Error handling with Result ---

use std::fs;
use std::io;

fn read_config(path: &str) -> Result<Config, Box<dyn std::error::Error>> {
    let content = fs::read_to_string(path)?;  // ? propagates errors
    let parsed = parse_config(&content)?;
    Ok(parsed)
}

// Pattern matching on Result
fn process_file(path: &str) {
    match read_config(path) {
        Ok(config) => println!("Loaded: {}", config.get_name()),
        Err(e) => eprintln!("Failed: {}", e),
    }
}

// --- Traits (interfaces) and generics ---

trait Summary {
    fn summarize(&self) -> String;
    fn preview(&self) -> String {
        format!("{}...", &self.summarize()[..50])
    }
}

struct Article {
    title: String,
    content: String,
}

impl Summary for Article {
    fn summarize(&self) -> String {
        format!("{}: {}", self.title, &self.content[..100])
    }
}

// Generic with trait bound
fn notify(item: &impl Summary) {
    println!("Breaking: {}", item.summarize());
}

// --- Enum variants (algebraic data types) ---

enum Shape {
    Circle { radius: f64 },
    Rectangle { width: f64, height: f64 },
    Triangle { base: f64, height: f64 },
}

impl Shape {
    fn area(&self) -> f64 {
        match self {
            Shape::Circle { radius } => std::f64::consts::PI * radius * radius,
            Shape::Rectangle { width, height } => width * height,
            Shape::Triangle { base, height } => 0.5 * base * height,
        }
    }
}
```

What the borrow checker prevents:
- **Use-after-free** — ownership system drops at right time
- **Data races** — exclusive mutable OR shared immutable, never both
- **Dangling references** — lifetimes ensure references outlive their data
- **Double free** — single owner means single drop
- **Iterator invalidation** — can't modify collection while iterating'''
    ),
]
