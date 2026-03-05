"""Functional programming — monads, functors, pattern matching, algebraic data types, effect systems."""

PAIRS = [
    (
        "functional-programming/monads-and-functors",
        "Implement monads and functors in Python and TypeScript including Maybe/Option, Either/Result, IO monad, and monadic composition for building a railway-oriented error handling pipeline.",
        '''Monads and functors for railway-oriented programming:

```python
"""Monads — Maybe, Either, IO, and monadic composition in Python."""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from typing import Generic, Never, TypeVar, overload

logger = logging.getLogger(__name__)

A = TypeVar("A")
B = TypeVar("B")
E = TypeVar("E")


# ============================================================
# 1. Functor / Monad base
# ============================================================

class Functor(ABC, Generic[A]):
    """Base functor — supports fmap (map)."""

    @abstractmethod
    def map(self, f: Callable[[A], B]) -> "Functor[B]":
        ...


class Monad(Functor[A], ABC):
    """Base monad — supports flatmap (bind/chain)."""

    @abstractmethod
    def flat_map(self, f: Callable[[A], "Monad[B]"]) -> "Monad[B]":
        ...

    @classmethod
    @abstractmethod
    def pure(cls, value: A) -> "Monad[A]":
        """Lift a plain value into the monadic context."""
        ...


# ============================================================
# 2. Maybe / Option monad
# ============================================================

class Maybe(Monad[A], ABC):
    """Option type — represents presence or absence of a value."""

    @staticmethod
    def of(value: A | None) -> "Maybe[A]":
        if value is None:
            return Nothing()
        return Just(value)

    @classmethod
    def pure(cls, value: A) -> "Maybe[A]":
        return Just(value)

    @abstractmethod
    def or_else(self, default: A) -> A:
        ...

    @abstractmethod
    def or_else_get(self, supplier: Callable[[], A]) -> A:
        ...

    @abstractmethod
    def filter(self, predicate: Callable[[A], bool]) -> "Maybe[A]":
        ...

    @abstractmethod
    def is_present(self) -> bool:
        ...


@dataclass(frozen=True)
class Just(Maybe[A]):
    _value: A

    def map(self, f: Callable[[A], B]) -> Maybe[B]:
        return Just(f(self._value))

    def flat_map(self, f: Callable[[A], Maybe[B]]) -> Maybe[B]:
        return f(self._value)

    def or_else(self, default: A) -> A:
        return self._value

    def or_else_get(self, supplier: Callable[[], A]) -> A:
        return self._value

    def filter(self, predicate: Callable[[A], bool]) -> Maybe[A]:
        return self if predicate(self._value) else Nothing()

    def is_present(self) -> bool:
        return True

    def __repr__(self) -> str:
        return f"Just({self._value!r})"


@dataclass(frozen=True)
class Nothing(Maybe[A]):

    def map(self, f: Callable[[A], B]) -> Maybe[B]:
        return Nothing()

    def flat_map(self, f: Callable[[A], Maybe[B]]) -> Maybe[B]:
        return Nothing()

    def or_else(self, default: A) -> A:
        return default

    def or_else_get(self, supplier: Callable[[], A]) -> A:
        return supplier()

    def filter(self, predicate: Callable[[A], bool]) -> Maybe[A]:
        return self

    def is_present(self) -> bool:
        return False

    def __repr__(self) -> str:
        return "Nothing()"


# ============================================================
# 3. Either / Result monad
# ============================================================

class Either(Monad[A], ABC, Generic[E, A]):
    """Either type — Left for errors, Right for success values."""

    @classmethod
    def pure(cls, value: A) -> "Either[Never, A]":
        return Right(value)

    @abstractmethod
    def map_left(self, f: Callable[[E], B]) -> "Either[B, A]":
        ...

    @abstractmethod
    def fold(
        self,
        on_left: Callable[[E], B],
        on_right: Callable[[A], B],
    ) -> B:
        """Collapse Either into a single value."""
        ...

    @abstractmethod
    def to_maybe(self) -> Maybe[A]:
        ...


@dataclass(frozen=True)
class Left(Either[E, A]):
    _error: E

    def map(self, f: Callable[[A], B]) -> Either[E, B]:
        return Left(self._error)

    def flat_map(self, f: Callable[[A], Either[E, B]]) -> Either[E, B]:
        return Left(self._error)

    def map_left(self, f: Callable[[E], B]) -> Either[B, A]:
        return Left(f(self._error))

    def fold(self, on_left: Callable[[E], B], on_right: Callable[[A], B]) -> B:
        return on_left(self._error)

    def to_maybe(self) -> Maybe[A]:
        return Nothing()

    def __repr__(self) -> str:
        return f"Left({self._error!r})"


@dataclass(frozen=True)
class Right(Either[E, A]):
    _value: A

    def map(self, f: Callable[[A], B]) -> Either[E, B]:
        return Right(f(self._value))

    def flat_map(self, f: Callable[[A], Either[E, B]]) -> Either[E, B]:
        return f(self._value)

    def map_left(self, f: Callable[[E], B]) -> Either[B, A]:
        return Right(self._value)

    def fold(self, on_left: Callable[[E], B], on_right: Callable[[A], B]) -> B:
        return on_right(self._value)

    def to_maybe(self) -> Maybe[A]:
        return Just(self._value)

    def __repr__(self) -> str:
        return f"Right({self._value!r})"


# ============================================================
# 4. Railway-oriented pipeline using Either
# ============================================================

@dataclass(frozen=True)
class ValidationError:
    field: str
    message: str


@dataclass(frozen=True)
class UserInput:
    name: str
    email: str
    age: str


@dataclass(frozen=True)
class ValidatedUser:
    name: str
    email: str
    age: int


def validate_name(inp: UserInput) -> Either[ValidationError, UserInput]:
    if len(inp.name.strip()) < 2:
        return Left(ValidationError("name", "Name must be at least 2 characters"))
    return Right(inp)


def validate_email(inp: UserInput) -> Either[ValidationError, UserInput]:
    if "@" not in inp.email or "." not in inp.email.split("@")[-1]:
        return Left(ValidationError("email", "Invalid email format"))
    return Right(inp)


def validate_age(inp: UserInput) -> Either[ValidationError, UserInput]:
    try:
        age = int(inp.age)
        if not (0 < age < 150):
            return Left(ValidationError("age", "Age must be between 1 and 149"))
        return Right(inp)
    except ValueError:
        return Left(ValidationError("age", "Age must be a number"))


def to_validated_user(inp: UserInput) -> Either[ValidationError, ValidatedUser]:
    return Right(ValidatedUser(
        name=inp.name.strip(),
        email=inp.email.lower().strip(),
        age=int(inp.age),
    ))


def validate_user(inp: UserInput) -> Either[ValidationError, ValidatedUser]:
    """Railway-oriented validation pipeline.

    Each step short-circuits on Left (error), or continues on Right (success).
    """
    return (
        Right(inp)
        .flat_map(validate_name)
        .flat_map(validate_email)
        .flat_map(validate_age)
        .flat_map(to_validated_user)
    )


# Usage
result = validate_user(UserInput(name="Alice", email="alice@example.com", age="30"))
message = result.fold(
    on_left=lambda err: f"Validation failed: {err.field} - {err.message}",
    on_right=lambda user: f"Welcome, {user.name} ({user.email}), age {user.age}!",
)
print(message)  # "Welcome, Alice (alice@example.com), age 30!"

bad_result = validate_user(UserInput(name="A", email="bad", age="xyz"))
print(bad_result)  # Left(ValidationError(field='name', message='Name must be...'))


# ============================================================
# 5. IO monad — defer side effects
# ============================================================

@dataclass(frozen=True)
class IO(Generic[A]):
    """IO monad — wraps side-effectful computations as pure values.

    The effect is only executed when .run() is called.
    """
    _effect: Callable[[], A]

    @staticmethod
    def pure(value: A) -> "IO[A]":
        return IO(lambda: value)

    def map(self, f: Callable[[A], B]) -> "IO[B]":
        return IO(lambda: f(self._effect()))

    def flat_map(self, f: Callable[[A], "IO[B]"]) -> "IO[B]":
        return IO(lambda: f(self._effect()).run())

    def run(self) -> A:
        """Execute the side effect."""
        return self._effect()


def read_file(path: str) -> IO[str]:
    return IO(lambda: open(path).read())

def parse_json(text: str) -> IO[dict]:
    return IO(lambda: json.loads(text))

def log_data(data: dict) -> IO[None]:
    return IO(lambda: logger.info("Parsed: %s", data))


# Compose IO operations — nothing executes until .run()
program: IO[None] = (
    read_file("config.json")
    .flat_map(parse_json)
    .flat_map(log_data)
)
# program.run()  # Only now does file I/O + parsing + logging happen
```

**Monad laws (must hold for valid implementations):**

| Law | Description | Code |
|-----|-------------|------|
| Left identity | `pure(a).flat_map(f) == f(a)` | Wrapping then binding = calling directly |
| Right identity | `m.flat_map(pure) == m` | Binding with pure = no-op |
| Associativity | `m.flat_map(f).flat_map(g) == m.flat_map(x -> f(x).flat_map(g))` | Binding order doesn't matter |

**When to use each monad:**
- `Maybe/Option`: nullable values, dictionary lookups, optional config
- `Either/Result`: operations that can fail with typed errors
- `IO`: deferring side effects, composing file/network operations
- `List`: non-deterministic computation, generating combinations'''
    ),
    (
        "functional-programming/pattern-matching-algebraic-data-types",
        "Implement algebraic data types (sum types and product types) with exhaustive pattern matching in Python using match/case and in TypeScript using discriminated unions, including AST evaluation and state machines.",
        '''Algebraic data types with exhaustive pattern matching:

```python
"""Algebraic data types — sum types, product types, exhaustive matching."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Never, assert_never


# ============================================================
# 1. Sum types (tagged unions) with pattern matching
# ============================================================

# --- Expression AST ---

@dataclass(frozen=True)
class Literal:
    value: float

@dataclass(frozen=True)
class Variable:
    name: str

@dataclass(frozen=True)
class BinOp:
    op: str  # "+", "-", "*", "/"
    left: "Expr"
    right: "Expr"

@dataclass(frozen=True)
class UnaryOp:
    op: str  # "-", "abs", "sqrt"
    operand: "Expr"

@dataclass(frozen=True)
class IfExpr:
    condition: "Expr"
    then_branch: "Expr"
    else_branch: "Expr"

@dataclass(frozen=True)
class FuncCall:
    name: str
    args: tuple["Expr", ...]


# Sum type = union of all variants
type Expr = Literal | Variable | BinOp | UnaryOp | IfExpr | FuncCall


# ============================================================
# 2. Exhaustive pattern matching for evaluation
# ============================================================

type Env = dict[str, float]
type FuncTable = dict[str, callable]

import math

BUILTINS: FuncTable = {
    "sin": math.sin,
    "cos": math.cos,
    "sqrt": math.sqrt,
    "abs": abs,
    "max": max,
    "min": min,
}


def evaluate(expr: Expr, env: Env) -> float:
    """Evaluate expression with exhaustive pattern matching.

    Python's match/case + assert_never guarantees all variants handled.
    """
    match expr:
        case Literal(value=v):
            return v

        case Variable(name=n):
            if n not in env:
                raise NameError(f"Undefined variable: {n}")
            return env[n]

        case BinOp(op=op, left=left, right=right):
            l = evaluate(left, env)
            r = evaluate(right, env)
            match op:
                case "+": return l + r
                case "-": return l - r
                case "*": return l * r
                case "/":
                    if r == 0:
                        raise ZeroDivisionError("Division by zero")
                    return l / r
                case _:
                    raise ValueError(f"Unknown operator: {op}")

        case UnaryOp(op=op, operand=operand):
            val = evaluate(operand, env)
            match op:
                case "-": return -val
                case "abs": return abs(val)
                case "sqrt":
                    if val < 0:
                        raise ValueError("sqrt of negative number")
                    return math.sqrt(val)
                case _:
                    raise ValueError(f"Unknown unary operator: {op}")

        case IfExpr(condition=cond, then_branch=then_b, else_branch=else_b):
            return evaluate(then_b, env) if evaluate(cond, env) != 0 else evaluate(else_b, env)

        case FuncCall(name=name, args=args):
            if name not in BUILTINS:
                raise NameError(f"Unknown function: {name}")
            evaluated_args = tuple(evaluate(a, env) for a in args)
            return BUILTINS[name](*evaluated_args)

        case _ as unreachable:
            assert_never(unreachable)


# Pretty-printer using pattern matching
def pretty_print(expr: Expr) -> str:
    match expr:
        case Literal(value=v):
            return str(v) if v != int(v) else str(int(v))
        case Variable(name=n):
            return n
        case BinOp(op=op, left=l, right=r):
            return f"({pretty_print(l)} {op} {pretty_print(r)})"
        case UnaryOp(op=op, operand=o):
            return f"{op}({pretty_print(o)})"
        case IfExpr(condition=c, then_branch=t, else_branch=e):
            return f"if {pretty_print(c)} then {pretty_print(t)} else {pretty_print(e)}"
        case FuncCall(name=n, args=args):
            arg_str = ", ".join(pretty_print(a) for a in args)
            return f"{n}({arg_str})"
        case _ as unreachable:
            assert_never(unreachable)


# Build and evaluate: sqrt(x^2 + y^2)
expr = FuncCall("sqrt", (
    BinOp("+",
        BinOp("*", Variable("x"), Variable("x")),
        BinOp("*", Variable("y"), Variable("y")),
    ),
))

env = {"x": 3.0, "y": 4.0}
print(pretty_print(expr))     # sqrt((x * x) + (y * y))
print(evaluate(expr, env))    # 5.0


# ============================================================
# 3. State machine as algebraic data type
# ============================================================

@dataclass(frozen=True)
class Idle:
    pass

@dataclass(frozen=True)
class Loading:
    url: str
    started_at: float

@dataclass(frozen=True)
class Success:
    data: dict
    loaded_at: float

@dataclass(frozen=True)
class Error:
    message: str
    retry_count: int
    last_url: str


type FetchState = Idle | Loading | Success | Error


# Events
@dataclass(frozen=True)
class StartFetch:
    url: str

@dataclass(frozen=True)
class FetchSucceeded:
    data: dict

@dataclass(frozen=True)
class FetchFailed:
    error: str

@dataclass(frozen=True)
class Retry:
    pass

@dataclass(frozen=True)
class Reset:
    pass


type FetchEvent = StartFetch | FetchSucceeded | FetchFailed | Retry | Reset


import time

def transition(state: FetchState, event: FetchEvent) -> FetchState:
    """Pure state transition function — no side effects."""
    match (state, event):
        case (Idle(), StartFetch(url=url)):
            return Loading(url=url, started_at=time.time())

        case (Loading(), FetchSucceeded(data=data)):
            return Success(data=data, loaded_at=time.time())

        case (Loading(url=url), FetchFailed(error=msg)):
            return Error(message=msg, retry_count=0, last_url=url)

        case (Error(retry_count=n, last_url=url), Retry()) if n < 3:
            return Loading(url=url, started_at=time.time())

        case (Error(retry_count=n), Retry()):
            return state  # Max retries exceeded, stay in error

        case (_, Reset()):
            return Idle()

        case (Success(), StartFetch(url=url)):
            return Loading(url=url, started_at=time.time())

        case _:
            raise ValueError(
                f"Invalid transition: {type(state).__name__} + {type(event).__name__}"
            )


def render_state(state: FetchState) -> str:
    """Render UI based on current state."""
    match state:
        case Idle():
            return "<div>Ready to fetch</div>"
        case Loading(url=url):
            return f"<div>Loading {url}...</div>"
        case Success(data=data):
            return f"<div>Data: {data}</div>"
        case Error(message=msg, retry_count=n):
            return f"<div>Error: {msg} (retries: {n})</div>"
        case _ as unreachable:
            assert_never(unreachable)


# State machine execution
state: FetchState = Idle()
state = transition(state, StartFetch(url="https://api.example.com/data"))
print(render_state(state))  # <div>Loading https://api.example.com/data...</div>

state = transition(state, FetchFailed(error="Connection timeout"))
print(render_state(state))  # <div>Error: Connection timeout (retries: 0)</div>

state = transition(state, Retry())
print(render_state(state))  # <div>Loading https://api.example.com/data...</div>

state = transition(state, FetchSucceeded(data={"users": [1, 2, 3]}))
print(render_state(state))  # <div>Data: {'users': [1, 2, 3]}</div>
```

```typescript
// ============================================================
// TypeScript discriminated unions + exhaustive matching
// ============================================================

// Expression AST as discriminated union
type Expr =
  | { tag: "literal"; value: number }
  | { tag: "variable"; name: string }
  | { tag: "binop"; op: "+" | "-" | "*" | "/"; left: Expr; right: Expr }
  | { tag: "unary"; op: "-" | "abs" | "sqrt"; operand: Expr }
  | { tag: "if"; condition: Expr; then: Expr; else: Expr }
  | { tag: "call"; name: string; args: Expr[] };

// Helper constructors
const lit = (value: number): Expr => ({ tag: "literal", value });
const varRef = (name: string): Expr => ({ tag: "variable", name });
const add = (l: Expr, r: Expr): Expr => ({ tag: "binop", op: "+", left: l, right: r });
const mul = (l: Expr, r: Expr): Expr => ({ tag: "binop", op: "*", left: l, right: r });
const call = (name: string, ...args: Expr[]): Expr => ({ tag: "call", name, args });

// Exhaustive evaluation
function evaluate(expr: Expr, env: Record<string, number>): number {
  switch (expr.tag) {
    case "literal":
      return expr.value;
    case "variable":
      if (!(expr.name in env)) throw new Error(`Undefined: ${expr.name}`);
      return env[expr.name];
    case "binop": {
      const l = evaluate(expr.left, env);
      const r = evaluate(expr.right, env);
      switch (expr.op) {
        case "+": return l + r;
        case "-": return l - r;
        case "*": return l * r;
        case "/": if (r === 0) throw new Error("Div by zero"); return l / r;
      }
    }
    case "unary": {
      const val = evaluate(expr.operand, env);
      switch (expr.op) {
        case "-": return -val;
        case "abs": return Math.abs(val);
        case "sqrt": return Math.sqrt(val);
      }
    }
    case "if":
      return evaluate(expr.condition, env) !== 0
        ? evaluate(expr.then, env)
        : evaluate(expr.else, env);
    case "call": {
      const fn = builtins[expr.name];
      if (!fn) throw new Error(`Unknown function: ${expr.name}`);
      return fn(...expr.args.map((a) => evaluate(a, env)));
    }
    default: {
      const _exhaustive: never = expr;
      throw new Error(`Unhandled: ${_exhaustive}`);
    }
  }
}

const builtins: Record<string, (...args: number[]) => number> = {
  sin: Math.sin, cos: Math.cos, sqrt: Math.sqrt,
  abs: Math.abs, max: Math.max, min: Math.min,
};

// sqrt(x^2 + y^2)
const expr = call("sqrt", add(mul(varRef("x"), varRef("x")), mul(varRef("y"), varRef("y"))));
console.log(evaluate(expr, { x: 3, y: 4 })); // 5
```

**ADT concepts:**

| Concept | Python | TypeScript |
|---------|--------|-----------|
| Sum type | `type X = A \| B \| C` | `type X = A \| B \| C` with `tag` |
| Product type | `@dataclass` fields | Object with typed properties |
| Pattern matching | `match/case` (3.10+) | `switch` on discriminant |
| Exhaustiveness | `assert_never()` | `never` type in default |
| Guard clauses | `case X() if cond:` | `if` inside case |

**Best practices:**
- Use frozen dataclasses for immutable ADT variants
- Always include `assert_never()` / `never` default for exhaustiveness
- Keep state transition functions pure (no side effects)
- Use tuple-matching `(state, event)` for state machine transitions
- Prefer `type` alias (Python 3.12+) over `Union` for sum types'''
    ),
    (
        "functional-programming/effect-systems-and-dependency-injection",
        "Build an effect system in Python that separates pure business logic from side effects using the Reader monad and tagless final pattern, enabling testable, composable, and dependency-injectable code.",
        '''Effect systems and functional dependency injection:

```python
"""Effect systems — Reader monad, tagless final, and capability-based DI."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Generic, Protocol, TypeVar, runtime_checkable

logger = logging.getLogger(__name__)

A = TypeVar("A")
B = TypeVar("B")
R = TypeVar("R")


# ============================================================
# 1. Reader monad — inject dependencies functionally
# ============================================================

@dataclass(frozen=True)
class Reader(Generic[R, A]):
    """Reader monad — defers computation until dependencies are provided.

    R = environment/dependency type
    A = result type
    """
    _run: Callable[[R], A]

    def run(self, env: R) -> A:
        """Execute with provided environment."""
        return self._run(env)

    def map(self, f: Callable[[A], B]) -> "Reader[R, B]":
        return Reader(lambda env: f(self._run(env)))

    def flat_map(self, f: Callable[[A], "Reader[R, B]"]) -> "Reader[R, B]":
        return Reader(lambda env: f(self._run(env)).run(env))

    @staticmethod
    def pure(value: A) -> "Reader[Any, A]":
        return Reader(lambda _: value)

    @staticmethod
    def ask() -> "Reader[R, R]":
        """Get the environment itself."""
        return Reader(lambda env: env)


# ============================================================
# 2. Capability-based environment (tagless final style)
# ============================================================

@runtime_checkable
class HasDatabase(Protocol):
    async def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict]: ...
    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int: ...


@runtime_checkable
class HasCache(Protocol):
    async def get(self, key: str) -> str | None: ...
    async def set(self, key: str, value: str, ttl: int = 300) -> None: ...
    async def delete(self, key: str) -> None: ...


@runtime_checkable
class HasEmailSender(Protocol):
    async def send_email(self, to: str, subject: str, body: str) -> bool: ...


@runtime_checkable
class HasClock(Protocol):
    def now(self) -> datetime: ...


@runtime_checkable
class HasLogger(Protocol):
    def log(self, level: str, message: str, **kwargs: Any) -> None: ...


# ============================================================
# 3. Effect-based service layer
# ============================================================

@dataclass(frozen=True)
class User:
    id: str
    name: str
    email: str
    created_at: datetime


@dataclass(frozen=True)
class CreateUserRequest:
    name: str
    email: str


class UserService:
    """Service layer using Reader monad for dependency injection.

    Business logic is pure — side effects are deferred to the environment.
    """

    @staticmethod
    def create_user(
        request: CreateUserRequest,
    ) -> Reader[HasDatabase & HasCache & HasClock & HasLogger, User]:
        """Create user — returns a Reader that defers all side effects."""

        async def _run(env: HasDatabase & HasCache & HasClock & HasLogger) -> User:
            env.log("info", f"Creating user: {request.name}")

            # Check cache for duplicate
            cached = await env.get(f"user:email:{request.email}")
            if cached:
                raise ValueError(f"User with email {request.email} already exists")

            # Insert into database
            now = env.now()
            user_id = f"usr_{now.timestamp():.0f}"
            await env.execute(
                "INSERT INTO users (id, name, email, created_at) VALUES (?, ?, ?, ?)",
                (user_id, request.name, request.email, now.isoformat()),
            )

            user = User(id=user_id, name=request.name, email=request.email, created_at=now)

            # Invalidate cache
            await env.set(f"user:email:{request.email}", user_id, ttl=3600)
            await env.delete("users:count")

            env.log("info", f"Created user {user_id}")
            return user

        return Reader(lambda env: asyncio.get_event_loop().run_until_complete(_run(env)))

    @staticmethod
    def get_user_by_email(
        email: str,
    ) -> Reader[HasDatabase & HasCache & HasLogger, User | None]:

        async def _run(env: HasDatabase & HasCache & HasLogger) -> User | None:
            # Check cache first
            cached_id = await env.get(f"user:email:{email}")
            if cached_id:
                env.log("debug", f"Cache hit for email: {email}")
                rows = await env.query(
                    "SELECT * FROM users WHERE id = ?", (cached_id,)
                )
            else:
                rows = await env.query(
                    "SELECT * FROM users WHERE email = ?", (email,)
                )

            if not rows:
                return None

            row = rows[0]
            return User(
                id=row["id"],
                name=row["name"],
                email=row["email"],
                created_at=datetime.fromisoformat(row["created_at"]),
            )

        return Reader(lambda env: asyncio.get_event_loop().run_until_complete(_run(env)))


# ============================================================
# 4. Production environment implementation
# ============================================================

class ProductionEnv:
    """Real environment with actual database, cache, etc."""

    def __init__(self, db_pool: Any, redis_client: Any) -> None:
        self._db = db_pool
        self._redis = redis_client

    async def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict]:
        async with self._db.acquire() as conn:
            rows = await conn.fetch(sql, *params)
            return [dict(r) for r in rows]

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        async with self._db.acquire() as conn:
            return await conn.execute(sql, *params)

    async def get(self, key: str) -> str | None:
        return await self._redis.get(key)

    async def set(self, key: str, value: str, ttl: int = 300) -> None:
        await self._redis.setex(key, ttl, value)

    async def delete(self, key: str) -> None:
        await self._redis.delete(key)

    def now(self) -> datetime:
        return datetime.now(timezone.utc)

    def log(self, level: str, message: str, **kwargs: Any) -> None:
        getattr(logger, level)(message, extra=kwargs)


# ============================================================
# 5. Test environment (pure, no side effects)
# ============================================================

class TestEnv:
    """In-memory test double for all capabilities."""

    def __init__(self) -> None:
        self._db: list[dict[str, Any]] = []
        self._cache: dict[str, str] = {}
        self._emails_sent: list[tuple[str, str, str]] = []
        self._logs: list[tuple[str, str]] = []
        self._frozen_time = datetime(2026, 1, 1, tzinfo=timezone.utc)

    async def query(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict]:
        # Simple in-memory query simulation
        if "WHERE email = ?" in sql and params:
            return [r for r in self._db if r.get("email") == params[0]]
        if "WHERE id = ?" in sql and params:
            return [r for r in self._db if r.get("id") == params[0]]
        return self._db

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        if sql.startswith("INSERT"):
            record = {"id": params[0], "name": params[1],
                       "email": params[2], "created_at": params[3]}
            self._db.append(record)
            return 1
        return 0

    async def get(self, key: str) -> str | None:
        return self._cache.get(key)

    async def set(self, key: str, value: str, ttl: int = 300) -> None:
        self._cache[key] = value

    async def delete(self, key: str) -> None:
        self._cache.pop(key, None)

    async def send_email(self, to: str, subject: str, body: str) -> bool:
        self._emails_sent.append((to, subject, body))
        return True

    def now(self) -> datetime:
        return self._frozen_time

    def log(self, level: str, message: str, **kwargs: Any) -> None:
        self._logs.append((level, message))

    # Test assertions
    def assert_logged(self, level: str, substring: str) -> None:
        assert any(
            lvl == level and substring in msg
            for lvl, msg in self._logs
        ), f"Expected log {level}: *{substring}* not found in {self._logs}"

    def assert_email_sent(self, to: str) -> None:
        assert any(
            email[0] == to for email in self._emails_sent
        ), f"No email sent to {to}"


# ============================================================
# 6. Tests — pure, fast, no mocking needed
# ============================================================

import pytest

@pytest.fixture
def env() -> TestEnv:
    return TestEnv()

def test_create_user(env: TestEnv) -> None:
    request = CreateUserRequest(name="Alice", email="alice@example.com")
    reader = UserService.create_user(request)

    # Run the Reader with our test environment
    user = reader.run(env)

    assert user.name == "Alice"
    assert user.email == "alice@example.com"
    assert user.created_at == env._frozen_time
    assert len(env._db) == 1
    env.assert_logged("info", "Created user")

def test_duplicate_email_rejected(env: TestEnv) -> None:
    # Pre-populate cache to simulate existing user
    asyncio.run(env.set("user:email:alice@example.com", "existing-id"))

    request = CreateUserRequest(name="Alice", email="alice@example.com")
    reader = UserService.create_user(request)

    with pytest.raises(ValueError, match="already exists"):
        reader.run(env)
```

**Effect system concepts:**

| Concept | Description | Benefit |
|---------|-------------|---------|
| Reader monad | Defers dependency resolution | Composable, lazy DI |
| Capability protocols | Fine-grained effect contracts | Only require what you need |
| Tagless final | Abstract over effect type | Swap real/test implementations |
| Pure business logic | No side effects in core code | Easy to test and reason about |
| Test doubles | In-memory implementations | Fast tests, no mocking |

**Best practices:**
- Define capabilities as protocols, not concrete classes
- Use intersection types (`HasDB & HasCache`) to compose requirements
- Keep Reader chains shallow; deep nesting hurts readability
- Test environments should be trivially constructable (no setup/teardown)
- Use the environment pattern for cross-cutting concerns (logging, metrics, tracing)'''
    ),
    (
        "functional-programming/advanced-pattern-matching-combinators",
        "Build a parser combinator library in Python using functional patterns including higher-order functions, closures, and monadic composition to parse a simple expression language.",
        '''Parser combinator library using functional composition:

```python
"""Parser combinators — functional parsing with monadic composition."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Generic, TypeVar

A = TypeVar("A")
B = TypeVar("B")


# ============================================================
# 1. Core parser type — function from input to result
# ============================================================

@dataclass(frozen=True)
class ParseResult(Generic[A]):
    """Result of a parse attempt."""
    value: A
    remaining: str
    success: bool = True
    error: str = ""
    position: int = 0

    @staticmethod
    def failure(msg: str, position: int = 0) -> "ParseResult[A]":
        return ParseResult(
            value=None,  # type: ignore
            remaining="",
            success=False,
            error=msg,
            position=position,
        )


# A Parser is a function from string to ParseResult
Parser = Callable[[str, int], ParseResult[A]]


# ============================================================
# 2. Primitive parsers
# ============================================================

def char(c: str) -> Parser[str]:
    """Parse a single specific character."""
    def parse(inp: str, pos: int) -> ParseResult[str]:
        if pos < len(inp) and inp[pos] == c:
            return ParseResult(value=c, remaining=inp[pos + 1:], position=pos + 1)
        expected = repr(c)
        got = repr(inp[pos]) if pos < len(inp) else "EOF"
        return ParseResult.failure(f"Expected {expected}, got {got}", pos)
    return parse


def string(s: str) -> Parser[str]:
    """Parse an exact string."""
    def parse(inp: str, pos: int) -> ParseResult[str]:
        end = pos + len(s)
        if inp[pos:end] == s:
            return ParseResult(value=s, remaining=inp[end:], position=end)
        return ParseResult.failure(f"Expected {s!r} at position {pos}", pos)
    return parse


def regex_parser(pattern: str) -> Parser[str]:
    """Parse using a regex pattern."""
    import re
    compiled = re.compile(pattern)

    def parse(inp: str, pos: int) -> ParseResult[str]:
        m = compiled.match(inp, pos)
        if m:
            matched = m.group()
            return ParseResult(value=matched, remaining=inp[m.end():], position=m.end())
        return ParseResult.failure(f"Pattern {pattern!r} did not match at {pos}", pos)
    return parse


def satisfy(predicate: Callable[[str], bool], name: str = "char") -> Parser[str]:
    """Parse a character satisfying a predicate."""
    def parse(inp: str, pos: int) -> ParseResult[str]:
        if pos < len(inp) and predicate(inp[pos]):
            return ParseResult(value=inp[pos], remaining=inp[pos + 1:], position=pos + 1)
        got = repr(inp[pos]) if pos < len(inp) else "EOF"
        return ParseResult.failure(f"Expected {name}, got {got}", pos)
    return parse


digit = satisfy(str.isdigit, "digit")
letter = satisfy(str.isalpha, "letter")
whitespace = satisfy(str.isspace, "whitespace")


# ============================================================
# 3. Combinators (higher-order parsers)
# ============================================================

def map_parser(parser: Parser[A], f: Callable[[A], B]) -> Parser[B]:
    """Apply function to parser result (functor map)."""
    def parse(inp: str, pos: int) -> ParseResult[B]:
        result = parser(inp, pos)
        if result.success:
            return ParseResult(value=f(result.value), remaining=result.remaining, position=result.position)
        return ParseResult.failure(result.error, result.position)
    return parse


def flat_map(parser: Parser[A], f: Callable[[A], Parser[B]]) -> Parser[B]:
    """Monadic bind — chain parsers where second depends on first result."""
    def parse(inp: str, pos: int) -> ParseResult[B]:
        result = parser(inp, pos)
        if not result.success:
            return ParseResult.failure(result.error, result.position)
        next_parser = f(result.value)
        return next_parser(inp, result.position)
    return parse


def seq(*parsers: Parser) -> Parser[tuple]:
    """Sequence parsers, collecting all results."""
    def parse(inp: str, pos: int) -> ParseResult[tuple]:
        values = []
        current_pos = pos
        for p in parsers:
            result = p(inp, current_pos)
            if not result.success:
                return ParseResult.failure(result.error, result.position)
            values.append(result.value)
            current_pos = result.position
        remaining = inp[current_pos:]
        return ParseResult(value=tuple(values), remaining=remaining, position=current_pos)
    return parse


def alt(*parsers: Parser[A]) -> Parser[A]:
    """Try parsers in order, return first success."""
    def parse(inp: str, pos: int) -> ParseResult[A]:
        errors = []
        for p in parsers:
            result = p(inp, pos)
            if result.success:
                return result
            errors.append(result.error)
        return ParseResult.failure(" | ".join(errors), pos)
    return parse


def many(parser: Parser[A]) -> Parser[list[A]]:
    """Parse zero or more occurrences."""
    def parse(inp: str, pos: int) -> ParseResult[list[A]]:
        values: list[A] = []
        current_pos = pos
        while True:
            result = parser(inp, current_pos)
            if not result.success:
                break
            values.append(result.value)
            current_pos = result.position
        remaining = inp[current_pos:]
        return ParseResult(value=values, remaining=remaining, position=current_pos)
    return parse


def many1(parser: Parser[A]) -> Parser[list[A]]:
    """Parse one or more occurrences."""
    def parse(inp: str, pos: int) -> ParseResult[list[A]]:
        result = many(parser)(inp, pos)
        if not result.success or len(result.value) == 0:
            return ParseResult.failure("Expected at least one match", pos)
        return result
    return parse


def sep_by(parser: Parser[A], separator: Parser) -> Parser[list[A]]:
    """Parse items separated by a delimiter."""
    def parse(inp: str, pos: int) -> ParseResult[list[A]]:
        first = parser(inp, pos)
        if not first.success:
            return ParseResult(value=[], remaining=inp[pos:], position=pos)

        values = [first.value]
        current_pos = first.position
        while True:
            sep_result = separator(inp, current_pos)
            if not sep_result.success:
                break
            item_result = parser(inp, sep_result.position)
            if not item_result.success:
                break
            values.append(item_result.value)
            current_pos = item_result.position

        remaining = inp[current_pos:]
        return ParseResult(value=values, remaining=remaining, position=current_pos)
    return parse


def between(open_p: Parser, close_p: Parser, content: Parser[A]) -> Parser[A]:
    """Parse content between opening and closing delimiters."""
    return map_parser(seq(open_p, content, close_p), lambda t: t[1])


def skip_whitespace(parser: Parser[A]) -> Parser[A]:
    """Skip leading whitespace before parser."""
    return map_parser(seq(many(whitespace), parser), lambda t: t[1])


# ============================================================
# 4. Expression language parser
# ============================================================

# Grammar:
#   expr   = term (('+' | '-') term)*
#   term   = factor (('*' | '/') factor)*
#   factor = number | '(' expr ')' | '-' factor
#   number = digit+ ('.' digit+)?

@dataclass(frozen=True)
class Num:
    value: float

@dataclass(frozen=True)
class BinOp:
    op: str
    left: "ASTNode"
    right: "ASTNode"

@dataclass(frozen=True)
class Neg:
    operand: "ASTNode"

type ASTNode = Num | BinOp | Neg


def number() -> Parser[ASTNode]:
    """Parse a number (integer or float)."""
    return map_parser(
        regex_parser(r"\d+(\.\d+)?"),
        lambda s: Num(float(s)),
    )

def factor() -> Parser[ASTNode]:
    """Parse a factor: number | parenthesized expr | negation."""
    return skip_whitespace(alt(
        number(),
        between(
            skip_whitespace(char("(")),
            skip_whitespace(char(")")),
            lambda inp, pos: expr()(inp, pos),  # Lazy reference to avoid recursion
        ),
        map_parser(
            seq(char("-"), lambda inp, pos: factor()(inp, pos)),
            lambda t: Neg(t[1]),
        ),
    ))

def term() -> Parser[ASTNode]:
    """Parse term: factor (('*' | '/') factor)*"""
    def parse(inp: str, pos: int) -> ParseResult[ASTNode]:
        left_result = factor()(inp, pos)
        if not left_result.success:
            return left_result

        node = left_result.value
        current_pos = left_result.position

        while current_pos < len(inp):
            op_result = skip_whitespace(alt(char("*"), char("/")))(inp, current_pos)
            if not op_result.success:
                break
            right_result = factor()(inp, op_result.position)
            if not right_result.success:
                return right_result
            node = BinOp(op=op_result.value, left=node, right=right_result.value)
            current_pos = right_result.position

        return ParseResult(value=node, remaining=inp[current_pos:], position=current_pos)
    return parse

def expr() -> Parser[ASTNode]:
    """Parse expression: term (('+' | '-') term)*"""
    def parse(inp: str, pos: int) -> ParseResult[ASTNode]:
        left_result = term()(inp, pos)
        if not left_result.success:
            return left_result

        node = left_result.value
        current_pos = left_result.position

        while current_pos < len(inp):
            op_result = skip_whitespace(alt(char("+"), char("-")))(inp, current_pos)
            if not op_result.success:
                break
            right_result = term()(inp, op_result.position)
            if not right_result.success:
                return right_result
            node = BinOp(op=op_result.value, left=node, right=right_result.value)
            current_pos = right_result.position

        return ParseResult(value=node, remaining=inp[current_pos:], position=current_pos)
    return parse


def evaluate(node: ASTNode) -> float:
    match node:
        case Num(value=v):
            return v
        case BinOp(op="+", left=l, right=r):
            return evaluate(l) + evaluate(r)
        case BinOp(op="-", left=l, right=r):
            return evaluate(l) - evaluate(r)
        case BinOp(op="*", left=l, right=r):
            return evaluate(l) * evaluate(r)
        case BinOp(op="/", left=l, right=r):
            return evaluate(l) / evaluate(r)
        case Neg(operand=o):
            return -evaluate(o)


# Usage
result = expr()("3 + 4 * (2 - 1)", 0)
assert result.success
print(evaluate(result.value))  # 7.0

result2 = expr()("(10 + 20) * 3 / 5", 0)
print(evaluate(result2.value))  # 18.0
```

**Parser combinator patterns:**

| Combinator | Type | Purpose |
|-----------|------|---------|
| `char(c)` | Primitive | Match single character |
| `map_parser` | Functor | Transform parse result |
| `flat_map` | Monad | Chain dependent parsers |
| `seq` | Applicative | Combine sequential parsers |
| `alt` | Alternative | Try multiple parsers |
| `many` / `many1` | Kleene star | Repetition |
| `sep_by` | List parsing | Delimited sequences |
| `between` | Bracketing | Content between delimiters |

**Best practices:**
- Use lazy references (lambda wrappers) for recursive grammars to avoid infinite recursion
- Build complex parsers from small, tested primitives
- Always propagate position information for error reporting
- Left-factor grammars to avoid backtracking performance issues
- Use `skip_whitespace` combinator consistently for whitespace handling'''
    ),
]
"""
