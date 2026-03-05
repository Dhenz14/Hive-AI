"""
Batch P5 -- Functional Programming: monads, algebraic data types,
immutable data structures, category theory, parser combinators.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. Monads in Practice ---
    (
        "monads_railway_oriented_programming_python",
        "Explain monads in practice with Maybe/Option, Either/Result, and IO monad patterns "
        "including monad transformers and Railway-oriented programming in Python. Show how monads "
        "compose error handling, eliminate nested conditionals, and provide complete production-ready "
        "implementations with type hints, chaining, and real-world usage examples.",
        r"""
# Monads in Practice: Railway-Oriented Programming in Python

## Why Monads Matter for Real Code

Monads are not an abstract mathematical curiosity -- they are the single most powerful
pattern for **composing computations that can fail, produce side effects, or carry context**.
Every time you write a chain of `if x is not None` checks, catch exceptions at every call
site, or thread configuration through ten function parameters, you are solving a problem
that monads solve more cleanly.

The core insight is this: a monad wraps a value inside a **computational context** (failure,
optionality, async, state, IO) and provides a way to **chain** operations that are aware of
that context. The `bind` operation (called `flatMap`, `>>=`, `and_then`, or `chain` depending
on the language) passes the inner value to the next function **only if** the context allows it.

**Because** Python lacks native monad syntax, many developers dismiss monads as irrelevant
to Python. However, the pattern is enormously useful -- it eliminates deeply nested
conditionals, makes error propagation explicit and type-safe, and enables Railway-oriented
programming where the "happy path" reads linearly while errors are handled systematically.

**Common mistake**: confusing monads with functors. A functor lets you `map` a function
over a wrapped value (`Maybe(5).map(lambda x: x + 1)`). A monad lets you `bind`/`chain`
a function that *itself returns a wrapped value* (`Maybe(5).bind(safe_divide_by_two)`).
The distinction matters **because** `bind` prevents nested wrapping: `Maybe(Maybe(5))` is
collapsed to `Maybe(5)`.

## The Maybe/Option Monad: Eliminating None Checks

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar, Generic, Callable, Optional, Iterator

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")


class Maybe(Generic[T]):
    # Base class for Maybe/Option monad.
    # Represents a value that may or may not exist.

    def bind(self, f: Callable[[T], Maybe[U]]) -> Maybe[U]:
        # Chain a function that returns a Maybe -- the core monadic operation
        if isinstance(self, Just):
            return f(self.value)
        return Nothing()

    def map(self, f: Callable[[T], U]) -> Maybe[U]:
        # Apply a pure function to the wrapped value (functor operation)
        if isinstance(self, Just):
            return Just(f(self.value))
        return Nothing()

    def or_else(self, default: T) -> T:
        # Unwrap with a fallback value
        if isinstance(self, Just):
            return self.value
        return default

    def or_else_lazy(self, f: Callable[[], T]) -> T:
        # Unwrap with a lazily-evaluated fallback
        if isinstance(self, Just):
            return self.value
        return f()

    def filter(self, predicate: Callable[[T], bool]) -> Maybe[T]:
        # Keep the value only if predicate holds
        if isinstance(self, Just) and predicate(self.value):
            return self
        return Nothing()

    def __iter__(self) -> Iterator[T]:
        # Allow unpacking: for x in maybe_val enables pattern matching
        if isinstance(self, Just):
            yield self.value

    def __bool__(self) -> bool:
        return isinstance(self, Just)


@dataclass(frozen=True)
class Just(Maybe[T]):
    value: T

    def __repr__(self) -> str:
        return f"Just({self.value!r})"


@dataclass(frozen=True)
class Nothing(Maybe[T]):
    def __repr__(self) -> str:
        return "Nothing()"


# Helper constructor
def maybe(value: Optional[T]) -> Maybe[T]:
    # Convert an Optional value to a Maybe monad
    if value is None:
        return Nothing()
    return Just(value)
```

This eliminates the **pitfall** of deeply nested None checks. Compare the imperative style
with the monadic style:

```python
# ---- Imperative style: nested None checks ----
def get_user_city_imperative(db: dict, user_id: str) -> Optional[str]:
    user = db.get(user_id)
    if user is None:
        return None
    address = user.get("address")
    if address is None:
        return None
    city = address.get("city")
    if city is None:
        return None
    return city.strip() or None


# ---- Monadic style: linear chain ----
def get_user_city_monadic(db: dict, user_id: str) -> Maybe[str]:
    return (
        maybe(db.get(user_id))
        .bind(lambda user: maybe(user.get("address")))
        .bind(lambda addr: maybe(addr.get("city")))
        .map(str.strip)
        .filter(lambda s: len(s) > 0)
    )


# Usage
result = get_user_city_monadic(database, "user_42").or_else("Unknown")
```

The monadic version reads top-to-bottom as a **pipeline**. Each `.bind()` is a rail on
the railway -- if any step produces `Nothing`, the entire chain short-circuits without
executing subsequent steps.

## The Either/Result Monad: Typed Error Handling

The `Maybe` monad tells you *that* something failed but not *why*. The `Either`/`Result`
monad carries **structured error information** through the chain. This is the foundation
of **Railway-oriented programming**: the computation travels on either the "success rail"
(Right/Ok) or the "error rail" (Left/Err), and `bind` only continues on the success rail.

```python
from __future__ import annotations

import traceback
from dataclasses import dataclass
from typing import TypeVar, Generic, Callable, Union

T = TypeVar("T")
U = TypeVar("U")
E = TypeVar("E")
F = TypeVar("F")


class Result(Generic[T, E]):
    # Either/Result monad for typed error handling.
    # Ok(value) represents success, Err(error) represents failure.

    def bind(self, f: Callable[[T], Result[U, E]]) -> Result[U, E]:
        # Chain a fallible operation -- only runs on the success rail
        if isinstance(self, Ok):
            return f(self.value)
        return self  # type: ignore[return-value]

    def map(self, f: Callable[[T], U]) -> Result[U, E]:
        # Transform the success value
        if isinstance(self, Ok):
            return Ok(f(self.value))
        return self  # type: ignore[return-value]

    def map_err(self, f: Callable[[E], F]) -> Result[T, F]:
        # Transform the error value
        if isinstance(self, Err):
            return Err(f(self.error))
        return self  # type: ignore[return-value]

    def unwrap(self) -> T:
        # Extract the value or raise -- use only at boundaries
        if isinstance(self, Ok):
            return self.value
        raise ValueError(f"Called unwrap on Err: {self}")

    def unwrap_or(self, default: T) -> T:
        if isinstance(self, Ok):
            return self.value
        return default

    def recover(self, f: Callable[[E], Result[T, E]]) -> Result[T, E]:
        # Attempt recovery from an error state
        if isinstance(self, Err):
            return f(self.error)
        return self


@dataclass(frozen=True)
class Ok(Result[T, E]):
    value: T

    def __repr__(self) -> str:
        return f"Ok({self.value!r})"


@dataclass(frozen=True)
class Err(Result[T, E]):
    error: E

    def __repr__(self) -> str:
        return f"Err({self.error!r})"


# Decorator to lift exception-throwing functions into Result
def try_result(f: Callable[..., T]) -> Callable[..., Result[T, str]]:
    def wrapper(*args, **kwargs) -> Result[T, str]:
        try:
            return Ok(f(*args, **kwargs))
        except Exception as exc:
            return Err(f"{type(exc).__name__}: {exc}")
    return wrapper


# ---- Railway-oriented pipeline ----
@dataclass(frozen=True)
class ValidationError:
    field: str
    message: str


def validate_email(email: str) -> Result[str, ValidationError]:
    if "@" not in email:
        return Err(ValidationError("email", "Missing @ symbol"))
    if not email.split("@")[1]:
        return Err(ValidationError("email", "Empty domain"))
    return Ok(email.lower().strip())


def validate_age(age: int) -> Result[int, ValidationError]:
    if age < 0 or age > 150:
        return Err(ValidationError("age", f"Invalid age: {age}"))
    return Ok(age)


def create_user(name: str, email: str, age: int) -> Result[dict, ValidationError]:
    # Railway-oriented: chain validations, short-circuit on first error
    return (
        validate_email(email)
        .bind(lambda valid_email: validate_age(age)
              .map(lambda valid_age: {
                  "name": name,
                  "email": valid_email,
                  "age": valid_age,
                  "status": "active",
              }))
    )
```

## The IO Monad and Monad Transformers

The IO monad is **best practice** for separating pure logic from side effects. In Haskell,
all side effects live inside `IO`. In Python, we can approximate this to make the boundary
between pure and effectful code explicit.

**Trade-off**: a full IO monad in Python adds boilerplate without compiler enforcement.
Therefore, the pragmatic approach is to use IO at module boundaries (API handlers, CLI
entry points) and keep inner logic pure with Result chains.

A **monad transformer** stacks monadic contexts. For example, `ResultT[IO, T, E]` is an
IO action that produces a `Result[T, E]`. This avoids the "callback hell" of nested
monads. However, Python's type system cannot fully express higher-kinded types, so we
approximate with composition patterns.

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar, Generic, Callable

T = TypeVar("T")
U = TypeVar("U")


@dataclass(frozen=True)
class IO(Generic[T]):
    # IO monad: wraps a side-effectful computation.
    # The effect is not executed until .run() is called, making
    # it referentially transparent until that point.
    _effect: Callable[[], T]

    def run(self) -> T:
        # Execute the side effect
        return self._effect()

    def map(self, f: Callable[[T], U]) -> IO[U]:
        # Transform the result of the IO action
        return IO(lambda: f(self._effect()))

    def bind(self, f: Callable[[T], IO[U]]) -> IO[U]:
        # Chain IO actions sequentially
        return IO(lambda: f(self._effect()).run())

    @staticmethod
    def pure(value: T) -> IO[T]:
        # Lift a pure value into IO context
        return IO(lambda: value)


# Combining IO with Result for robust error-handling pipelines
class IOResult(Generic[T, E]):
    # Monad transformer: IO[Result[T, E]]
    # Combines side effects with typed error handling
    def __init__(self, effect: Callable[[], Result[T, E]]) -> None:
        self._effect = effect

    def run(self) -> Result[T, E]:
        return self._effect()

    def bind(self, f: Callable[[T], IOResult[U, E]]) -> IOResult[U, E]:
        def combined() -> Result[U, E]:
            result = self._effect()
            if isinstance(result, Ok):
                return f(result.value).run()
            return result  # type: ignore
        return IOResult(combined)

    def map(self, f: Callable[[T], U]) -> IOResult[U, E]:
        def combined() -> Result[U, E]:
            result = self._effect()
            if isinstance(result, Ok):
                return Ok(f(result.value))
            return result  # type: ignore
        return IOResult(combined)

    @staticmethod
    def of(value: T) -> IOResult[T, E]:
        return IOResult(lambda: Ok(value))

    @staticmethod
    def fail(error: E) -> IOResult[T, E]:
        return IOResult(lambda: Err(error))


# Usage: reading a config file with error handling
def read_config(path: str) -> IOResult[dict, str]:
    def effect() -> Result[dict, str]:
        try:
            import json
            with open(path) as fh:
                return Ok(json.load(fh))
        except FileNotFoundError:
            return Err(f"Config not found: {path}")
        except json.JSONDecodeError as exc:
            return Err(f"Invalid JSON in {path}: {exc}")
    return IOResult(effect)


def get_db_url(config: dict) -> IOResult[str, str]:
    url = config.get("database", {}).get("url")
    if url is None:
        return IOResult.fail("Missing database.url in config")
    return IOResult.of(url)


# Full pipeline: read config -> extract DB URL -> validate
pipeline = (
    read_config("/etc/myapp/config.json")
    .bind(get_db_url)
    .map(lambda url: url.replace("localhost", "db.internal"))
)

# Nothing executes until .run() -- referential transparency
# result: Result[str, str] = pipeline.run()
```

## Summary and Key Takeaways

- **Maybe/Option** eliminates `None`-checking pyramids by wrapping optionality in a
  chainable container; use `.bind()` for functions returning `Maybe`, `.map()` for pure
  transforms
- **Either/Result** extends this with **typed error information**, enabling Railway-oriented
  programming where errors short-circuit through the pipeline without exceptions
- **IO monad** makes side effects explicit and deferred; **best practice** is to push IO
  to the edges and keep core logic pure with Result chains
- **Monad transformers** (like `IOResult`) stack contexts to avoid nested unwrapping;
  however, Python's type system limits full higher-kinded polymorphism, so prefer
  practical composition over theoretical purity
- **Pitfall**: do not wrap every function in a monad -- use them at **boundaries** where
  failure, optionality, or effects cross module lines; within a single function, plain
  Python control flow is clearer
- **Best practice**: define `bind`, `map`, `pure`, and the monad laws (left identity,
  right identity, associativity) for your custom monads and test them with property-based
  tests to ensure lawful behavior
""",
    ),

    # --- 2. Algebraic Data Types ---
    (
        "algebraic_data_types_pattern_matching_python",
        "Explain algebraic data types including sum types, product types, pattern matching, and "
        "discriminated unions with practical Python implementations using dataclasses, enums, and "
        "structural pattern matching. Cover exhaustiveness checking, recursive data types, visitor "
        "pattern alternatives, and real-world modeling examples with complete type-safe code.",
        r"""
# Algebraic Data Types: Sum Types, Product Types, and Pattern Matching in Python

## What Are Algebraic Data Types and Why Do They Matter

Algebraic Data Types (ADTs) are a type system feature that lets you model data as
**combinations of simpler types** using two fundamental operations: **products** (AND --
"a record has field A *and* field B") and **sums** (OR -- "a shape is a Circle *or* a
Rectangle *or* a Triangle"). The "algebraic" part comes from the fact that the number of
possible values follows arithmetic: a product type's cardinality is the *product* of its
fields' cardinalities, while a sum type's is the *sum*.

This matters for software design **because** ADTs let you make **illegal states
unrepresentable**. Instead of a `Shape` class with nullable fields for `radius`, `width`,
`height`, and `side_count` (most combinations of which are nonsensical), you define
exactly the valid variants. The compiler then ensures you handle every case.

**Common mistake**: using class hierarchies with inheritance to model sum types. Inheritance
is open -- anyone can add a subclass -- which breaks exhaustiveness guarantees. ADTs are
**closed** -- the set of variants is fixed, enabling the compiler (or runtime) to verify
that every pattern match handles all cases.

## Product Types: Structs, Records, Tuples

A **product type** combines multiple values into one. Python's `dataclass`, `NamedTuple`,
and plain tuples are all product types. The key **best practice** is to use frozen
dataclasses for domain models to get immutability, structural equality, and hashing.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import TypeVar, Generic, Callable, Sequence, Never
import math


# ---- Product types with frozen dataclasses ----
@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def distance_to(self, other: Point) -> float:
        return math.sqrt((self.x - other.x) ** 2 + (self.y - other.y) ** 2)


@dataclass(frozen=True)
class Color:
    r: int
    g: int
    b: int
    a: float = 1.0

    def __post_init__(self) -> None:
        # Validate invariants at construction time
        for ch in (self.r, self.g, self.b):
            if not (0 <= ch <= 255):
                raise ValueError(f"Channel value must be 0-255, got {ch}")
        if not (0.0 <= self.a <= 1.0):
            raise ValueError(f"Alpha must be 0.0-1.0, got {self.a}")


# Cardinality of Point = float x float (infinite)
# Cardinality of Color = 256 x 256 x 256 x float (effectively infinite, but constrained)


# ---- Product type composition ----
@dataclass(frozen=True)
class StyledPoint:
    position: Point
    color: Color
    label: str = ""

    # Cardinality = Point x Color x str
```

## Sum Types: Discriminated Unions

A **sum type** represents a value that is exactly one of several variants. Python 3.10+
structural pattern matching makes this practical. The **trade-off** compared to inheritance
is that sum types are closed (all variants defined upfront) while class hierarchies are
open (new subclasses can be added). Choose sum types when the set of variants is stable
and you want exhaustiveness checking.

```python
# ---- Sum types (discriminated unions) ----

# Approach 1: Base class + frozen dataclass variants
@dataclass(frozen=True)
class Shape:
    # Base type for the Shape sum type.
    # All variants must be defined here -- adding a variant
    # forces updating all match statements (which is the point).
    pass


@dataclass(frozen=True)
class Circle(Shape):
    center: Point
    radius: float


@dataclass(frozen=True)
class Rectangle(Shape):
    top_left: Point
    width: float
    height: float


@dataclass(frozen=True)
class Triangle(Shape):
    a: Point
    b: Point
    c: Point


@dataclass(frozen=True)
class Polygon(Shape):
    vertices: tuple[Point, ...]

    def __post_init__(self) -> None:
        if len(self.vertices) < 3:
            raise ValueError("Polygon needs at least 3 vertices")


# ---- Pattern matching with exhaustiveness ----
def area(shape: Shape) -> float:
    # Compute area using structural pattern matching.
    # If a new Shape variant is added, this function must be updated.
    match shape:
        case Circle(center=_, radius=r):
            return math.pi * r ** 2
        case Rectangle(top_left=_, width=w, height=h):
            return w * h
        case Triangle(a=p1, b=p2, c=p3):
            # Heron's formula
            side_a = p1.distance_to(p2)
            side_b = p2.distance_to(p3)
            side_c = p3.distance_to(p1)
            s = (side_a + side_b + side_c) / 2
            return math.sqrt(s * (s - side_a) * (s - side_b) * (s - side_c))
        case Polygon(vertices=verts):
            # Shoelace formula
            n = len(verts)
            total = sum(
                verts[i].x * verts[(i + 1) % n].y - verts[(i + 1) % n].x * verts[i].y
                for i in range(n)
            )
            return abs(total) / 2
        case _:
            _exhaustive_check: Never = shape  # type: ignore[assignment]
            raise TypeError(f"Unhandled shape: {shape}")


def perimeter(shape: Shape) -> float:
    match shape:
        case Circle(radius=r):
            return 2 * math.pi * r
        case Rectangle(width=w, height=h):
            return 2 * (w + h)
        case Triangle(a=p1, b=p2, c=p3):
            return p1.distance_to(p2) + p2.distance_to(p3) + p3.distance_to(p1)
        case Polygon(vertices=verts):
            n = len(verts)
            return sum(verts[i].distance_to(verts[(i + 1) % n]) for i in range(n))
        case _:
            _exhaustive_check: Never = shape  # type: ignore[assignment]
            raise TypeError(f"Unhandled shape: {shape}")
```

The `Never` trick in the default case is a **best practice** for exhaustiveness checking.
If you add a new variant to `Shape` but forget to handle it, the type checker (mypy/pyright)
will flag the `Never` assignment as an error, **because** the unhandled variant cannot be
assigned to `Never`.

## Recursive Data Types: Expression Trees

ADTs truly shine for **recursive data structures** like expression trees, ASTs, and linked
lists. The **pitfall** with inheritance-based approaches is that adding a new operation
requires modifying every class (the Expression Problem). With ADTs and pattern matching,
adding a new operation is just a new function.

```python
# ---- Recursive sum type: arithmetic expression tree ----
@dataclass(frozen=True)
class Expr:
    pass


@dataclass(frozen=True)
class Lit(Expr):
    value: float


@dataclass(frozen=True)
class Var(Expr):
    name: str


@dataclass(frozen=True)
class BinOp(Expr):
    op: str  # "+", "-", "*", "/"
    left: Expr
    right: Expr


@dataclass(frozen=True)
class UnaryOp(Expr):
    op: str  # "neg", "abs", "sqrt"
    operand: Expr


@dataclass(frozen=True)
class LetIn(Expr):
    # let name = binding in body
    name: str
    binding: Expr
    body: Expr


# ---- Operations as functions over the ADT ----
def evaluate(expr: Expr, env: dict[str, float] | None = None) -> float:
    env = env or {}
    match expr:
        case Lit(value=v):
            return v
        case Var(name=n):
            if n not in env:
                raise NameError(f"Undefined variable: {n}")
            return env[n]
        case BinOp(op="+", left=l, right=r):
            return evaluate(l, env) + evaluate(r, env)
        case BinOp(op="-", left=l, right=r):
            return evaluate(l, env) - evaluate(r, env)
        case BinOp(op="*", left=l, right=r):
            return evaluate(l, env) * evaluate(r, env)
        case BinOp(op="/", left=l, right=r):
            divisor = evaluate(r, env)
            if divisor == 0:
                raise ZeroDivisionError("Division by zero in expression")
            return evaluate(l, env) / divisor
        case UnaryOp(op="neg", operand=o):
            return -evaluate(o, env)
        case UnaryOp(op="abs", operand=o):
            return abs(evaluate(o, env))
        case UnaryOp(op="sqrt", operand=o):
            return math.sqrt(evaluate(o, env))
        case LetIn(name=n, binding=b, body=body):
            val = evaluate(b, env)
            return evaluate(body, {**env, n: val})
        case _:
            raise TypeError(f"Unknown expression: {expr}")


def pretty_print(expr: Expr) -> str:
    match expr:
        case Lit(value=v):
            return str(v)
        case Var(name=n):
            return n
        case BinOp(op=op, left=l, right=r):
            return f"({pretty_print(l)} {op} {pretty_print(r)})"
        case UnaryOp(op=op, operand=o):
            return f"{op}({pretty_print(o)})"
        case LetIn(name=n, binding=b, body=body):
            return f"let {n} = {pretty_print(b)} in {pretty_print(body)}"
        case _:
            return repr(expr)


# Example: let x = 3 + 4 in x * x
expression = LetIn("x", BinOp("+", Lit(3), Lit(4)), BinOp("*", Var("x"), Var("x")))
# evaluate(expression) -> 49
# pretty_print(expression) -> "let x = (3 + 4) in (x * x)"
```

## Summary and Key Takeaways

- **Product types** (dataclasses, tuples) combine fields with AND; **sum types** (tagged
  unions) combine variants with OR -- together they model any domain precisely
- **Best practice**: use `@dataclass(frozen=True)` for immutability and structural equality;
  use `__post_init__` to enforce invariants at construction time
- The `Never` type annotation in default match cases provides **exhaustiveness checking**
  that catches missing variants at type-check time -- this is the primary advantage of
  ADTs over open class hierarchies
- **Recursive ADTs** (expression trees, ASTs) are the natural way to represent nested
  structure; pattern matching replaces the Visitor pattern with simpler, more readable code
- **Pitfall**: overusing string enums or dictionaries where a proper sum type would make
  illegal states unrepresentable -- if a value can only be one of three things, model it
  as three dataclass variants, not a string field
- **Trade-off**: ADTs are closed (adding a variant requires updating all functions), while
  class hierarchies are open (adding a variant is easy, adding an operation is hard) --
  choose based on which axis changes more frequently in your domain
""",
    ),

    # --- 3. Immutable Data Structures ---
    (
        "immutable_persistent_data_structures_python",
        "Explain immutable and persistent data structures including structural sharing, HAMTs, "
        "persistent vectors with trie-based indexing, and persistent hash maps. Show how they enable "
        "safe concurrency and undo/redo, and provide complete Python implementations with performance "
        "analysis, copy-on-write semantics, and practical usage patterns with type hints.",
        r"""
# Immutable Data Structures: Persistent Vectors, HAMTs, and Structural Sharing

## Why Immutability Changes Everything

Mutable data structures are the root cause of an enormous class of bugs: race conditions
in concurrent code, action-at-a-distance when two parts of a system share a reference,
iterator invalidation when a collection is modified during traversal, and the impossibility
of reliable undo/redo or time-travel debugging. **Immutable** data structures eliminate all
of these problems **because** "updating" creates a new version while the old version remains
valid and unchanged.

The naive approach -- copying the entire structure on every "update" -- is O(n) and
impractical for large collections. **Persistent data structures** solve this with
**structural sharing**: the new version shares most of its internal nodes with the old
version, making updates O(log n) or even O(1) amortized while using O(log n) extra memory.

**Common mistake**: confusing "immutable" with "inefficient." Libraries like Clojure's
persistent vectors and Scala's `Vector` prove that persistent data structures can match
mutable ones in practical performance. The key is the right internal representation:
**wide tries** (branching factor 32) that keep the tree shallow.

**Trade-off**: persistent data structures use more memory per element than mutable arrays
(due to tree overhead) but provide O(1) snapshot/versioning. In scenarios requiring
concurrent reads, undo history, or functional pipelines, the trade-off overwhelmingly
favors persistence.

## Persistent Vector: Trie-Based Indexing

A persistent vector stores elements in a **wide trie** (typically branching factor 32).
Each level of the trie holds 32 children, so a 32-bit index is decomposed into groups
of 5 bits, each selecting a child at the corresponding level. This gives O(log32 n) --
effectively O(1) -- lookup and update.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeVar, Generic, Optional, Iterator, Callable
import copy

T = TypeVar("T")

# Branching factor -- 32 in production, smaller here for clarity
BITS = 5
WIDTH = 1 << BITS   # 32
MASK = WIDTH - 1     # 0b11111


class PersistentVector(Generic[T]):
    # A persistent (immutable) vector using a trie with branching factor 32.
    # Supports O(log32 n) lookup, update, and append -- effectively O(1).

    __slots__ = ("_size", "_shift", "_root", "_tail")

    def __init__(self) -> None:
        self._size: int = 0
        self._shift: int = BITS  # depth * BITS
        self._root: list = []
        self._tail: list = []

    @staticmethod
    def of(*items: T) -> PersistentVector[T]:
        # Build a vector from items
        vec: PersistentVector[T] = PersistentVector()
        for item in items:
            vec = vec.append(item)
        return vec

    def __len__(self) -> int:
        return self._size

    def _tail_offset(self) -> int:
        if self._size < WIDTH:
            return 0
        return ((self._size - 1) >> BITS) << BITS

    def __getitem__(self, index: int) -> T:
        if index < 0:
            index += self._size
        if not (0 <= index < self._size):
            raise IndexError(f"Index {index} out of range for size {self._size}")
        # Check if index is in the tail
        if index >= self._tail_offset():
            return self._tail[index & MASK]
        # Walk the trie
        node = self._root
        level = self._shift
        while level > 0:
            node = node[(index >> level) & MASK]
            level -= BITS
        return node[index & MASK]

    def append(self, value: T) -> PersistentVector[T]:
        # Return a new vector with value appended -- O(log32 n)
        result = PersistentVector.__new__(PersistentVector)

        if self._size - self._tail_offset() < WIDTH:
            # Room in tail -- just copy tail with new element
            result._root = self._root
            result._shift = self._shift
            result._tail = self._tail + [value]
            result._size = self._size + 1
            return result

        # Tail is full -- push it into the trie
        new_root = self._push_tail(self._shift, self._root, self._tail)
        new_shift = self._shift

        # Root overflow -- add new level
        if len(new_root) > WIDTH:
            new_root = [self._root, new_root[WIDTH:][0] if len(new_root) > WIDTH else []]
            new_shift += BITS

        result._root = new_root
        result._shift = new_shift
        result._tail = [value]
        result._size = self._size + 1
        return result

    def _push_tail(self, level: int, parent: list, tail: list) -> list:
        # Push the tail chunk into the trie at the appropriate position
        subidx = ((self._size - 1) >> level) & MASK
        result = list(parent)  # shallow copy -- structural sharing

        if level == BITS:
            # Bottom level: insert tail directly
            result.append(tail)
        else:
            if subidx < len(parent):
                child = self._push_tail(level - BITS, parent[subidx], tail)
                result[subidx] = child
            else:
                result.append(self._new_path(level - BITS, tail))
        return result

    def _new_path(self, level: int, node: list) -> list:
        if level == 0:
            return node
        return [self._new_path(level - BITS, node)]

    def set(self, index: int, value: T) -> PersistentVector[T]:
        # Return a new vector with index updated -- O(log32 n)
        if index < 0:
            index += self._size
        if not (0 <= index < self._size):
            raise IndexError(f"Index {index} out of range")

        result = PersistentVector.__new__(PersistentVector)
        result._size = self._size
        result._shift = self._shift

        if index >= self._tail_offset():
            result._root = self._root  # share root
            result._tail = list(self._tail)
            result._tail[index & MASK] = value
            return result

        # Update in the trie with path copying
        result._tail = self._tail  # share tail
        result._root = self._do_set(self._shift, self._root, index, value)
        return result

    def _do_set(self, level: int, node: list, index: int, value: T) -> list:
        result = list(node)  # copy this level only
        if level == 0:
            result[index & MASK] = value
        else:
            subidx = (index >> level) & MASK
            result[subidx] = self._do_set(level - BITS, node[subidx], index, value)
        return result

    def __iter__(self) -> Iterator[T]:
        for i in range(self._size):
            yield self[i]

    def __repr__(self) -> str:
        items = ", ".join(repr(x) for x in self)
        return f"PVec([{items}])"
```

## HAMT: Hash Array Mapped Trie for Persistent Maps

A **Hash Array Mapped Trie** (HAMT) is the persistent equivalent of a hash map. It uses
the hash of the key to navigate a trie, with each level consuming 5 bits of the hash.
Collisions at the leaf level are handled with a list. This gives O(log32 n) operations
with structural sharing on updates.

```python
from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar, Generic, Optional, Iterator, Tuple

K = TypeVar("K")
V = TypeVar("V")

HAMT_BITS = 5
HAMT_WIDTH = 1 << HAMT_BITS
HAMT_MASK = HAMT_WIDTH - 1


@dataclass(frozen=True)
class _Entry(Generic[K, V]):
    key: K
    value: V
    hash_val: int


class PersistentHashMap(Generic[K, V]):
    # Persistent hash map using a Hash Array Mapped Trie (HAMT).
    # O(log32 n) get, set, delete with full structural sharing.

    __slots__ = ("_root", "_size")

    def __init__(self) -> None:
        self._root: Optional[_HAMTNode] = None
        self._size: int = 0

    def get(self, key: K, default: V = None) -> Optional[V]:
        if self._root is None:
            return default
        entry = self._root.find(0, hash(key), key)
        return entry.value if entry is not None else default

    def set(self, key: K, value: V) -> PersistentHashMap[K, V]:
        # Return a new map with key set to value
        h = hash(key)
        entry = _Entry(key, value, h)
        if self._root is None:
            new_root = _HAMTLeaf(entry)
            added = True
        else:
            new_root, added = self._root.assoc(0, entry)

        result = PersistentHashMap.__new__(PersistentHashMap)
        result._root = new_root
        result._size = self._size + (1 if added else 0)
        return result

    def delete(self, key: K) -> PersistentHashMap[K, V]:
        if self._root is None:
            return self
        new_root = self._root.dissoc(0, hash(key), key)
        if new_root is self._root:
            return self  # key not found

        result = PersistentHashMap.__new__(PersistentHashMap)
        result._root = new_root
        result._size = self._size - 1
        return result

    def __len__(self) -> int:
        return self._size

    def __contains__(self, key: K) -> bool:
        if self._root is None:
            return False
        return self._root.find(0, hash(key), key) is not None

    def items(self) -> Iterator[Tuple[K, V]]:
        if self._root is not None:
            yield from self._root.entries()

    def __repr__(self) -> str:
        items_str = ", ".join(f"{k!r}: {v!r}" for k, v in self.items())
        return f"PMap({{{items_str}}})"


class _HAMTNode:
    # Abstract base for HAMT internal nodes
    def find(self, shift: int, h: int, key: K) -> Optional[_Entry]: ...
    def assoc(self, shift: int, entry: _Entry) -> Tuple[_HAMTNode, bool]: ...
    def dissoc(self, shift: int, h: int, key: K) -> Optional[_HAMTNode]: ...
    def entries(self) -> Iterator[Tuple]: ...


class _HAMTLeaf(_HAMTNode):
    __slots__ = ("entry",)

    def __init__(self, entry: _Entry) -> None:
        self.entry = entry

    def find(self, shift: int, h: int, key) -> Optional[_Entry]:
        if self.entry.key == key:
            return self.entry
        return None

    def assoc(self, shift: int, entry: _Entry) -> Tuple[_HAMTNode, bool]:
        if self.entry.key == entry.key:
            return _HAMTLeaf(entry), False  # update
        # Hash collision at this level -- create branch
        return _make_branch(shift, self.entry, entry), True

    def dissoc(self, shift: int, h: int, key) -> Optional[_HAMTNode]:
        if self.entry.key == key:
            return None
        return self

    def entries(self) -> Iterator[Tuple]:
        yield (self.entry.key, self.entry.value)


class _HAMTBranch(_HAMTNode):
    __slots__ = ("children", "bitmap")

    def __init__(self, bitmap: int, children: tuple) -> None:
        self.bitmap = bitmap
        self.children = children

    def _index(self, bit: int) -> int:
        return bin(self.bitmap & (bit - 1)).count("1")

    def find(self, shift: int, h: int, key) -> Optional[_Entry]:
        bit = 1 << ((h >> shift) & HAMT_MASK)
        if not (self.bitmap & bit):
            return None
        idx = self._index(bit)
        return self.children[idx].find(shift + HAMT_BITS, h, key)

    def assoc(self, shift: int, entry: _Entry) -> Tuple[_HAMTNode, bool]:
        bit = 1 << ((entry.hash_val >> shift) & HAMT_MASK)
        idx = self._index(bit)

        if self.bitmap & bit:
            child = self.children[idx]
            new_child, added = child.assoc(shift + HAMT_BITS, entry)
            new_children = list(self.children)
            new_children[idx] = new_child
            return _HAMTBranch(self.bitmap, tuple(new_children)), added
        else:
            new_children = list(self.children)
            new_children.insert(idx, _HAMTLeaf(entry))
            return _HAMTBranch(self.bitmap | bit, tuple(new_children)), True

    def dissoc(self, shift: int, h: int, key) -> Optional[_HAMTNode]:
        bit = 1 << ((h >> shift) & HAMT_MASK)
        if not (self.bitmap & bit):
            return self
        idx = self._index(bit)
        child = self.children[idx]
        new_child = child.dissoc(shift + HAMT_BITS, h, key)
        if new_child is child:
            return self
        if new_child is None:
            if len(self.children) == 1:
                return None
            new_children = list(self.children)
            del new_children[idx]
            return _HAMTBranch(self.bitmap ^ bit, tuple(new_children))
        new_children = list(self.children)
        new_children[idx] = new_child
        return _HAMTBranch(self.bitmap, tuple(new_children))

    def entries(self) -> Iterator[Tuple]:
        for child in self.children:
            yield from child.entries()


def _make_branch(shift: int, e1: _Entry, e2: _Entry) -> _HAMTNode:
    h1_frag = (e1.hash_val >> shift) & HAMT_MASK
    h2_frag = (e2.hash_val >> shift) & HAMT_MASK
    if h1_frag == h2_frag:
        # Same fragment at this level -- recurse deeper
        child = _make_branch(shift + HAMT_BITS, e1, e2)
        return _HAMTBranch(1 << h1_frag, (child,))
    bit1, bit2 = 1 << h1_frag, 1 << h2_frag
    leaf1, leaf2 = _HAMTLeaf(e1), _HAMTLeaf(e2)
    if h1_frag < h2_frag:
        return _HAMTBranch(bit1 | bit2, (leaf1, leaf2))
    return _HAMTBranch(bit1 | bit2, (leaf2, leaf1))
```

## Practical Usage: Undo/Redo and Safe Concurrency

**Because** persistent data structures preserve old versions, undo/redo is trivial: just
keep a list of past states. This is the same pattern used by Redux in frontend development
and by database MVCC (Multi-Version Concurrency Control).

```python
from dataclasses import dataclass, field
from typing import TypeVar, Generic

T = TypeVar("T")


@dataclass
class UndoStack(Generic[T]):
    # Undo/redo manager using persistent data structures.
    # Each operation produces a new state without destroying the old one.
    _history: list[T] = field(default_factory=list)
    _redo_stack: list[T] = field(default_factory=list)

    @property
    def current(self) -> T:
        return self._history[-1]

    def push(self, state: T) -> None:
        # Record a new state, clearing the redo stack
        self._history.append(state)
        self._redo_stack.clear()

    def undo(self) -> T:
        if len(self._history) <= 1:
            raise IndexError("Nothing to undo")
        state = self._history.pop()
        self._redo_stack.append(state)
        return self._history[-1]

    def redo(self) -> T:
        if not self._redo_stack:
            raise IndexError("Nothing to redo")
        state = self._redo_stack.pop()
        self._history.append(state)
        return state


# Usage with persistent vector
editor = UndoStack[PersistentVector[str]]()
doc = PersistentVector.of("Hello", "World")
editor.push(doc)

doc2 = doc.append("!")
editor.push(doc2)  # ["Hello", "World", "!"]

doc3 = doc2.set(1, "Python")
editor.push(doc3)  # ["Hello", "Python", "!"]

editor.undo()  # back to ["Hello", "World", "!"]
editor.undo()  # back to ["Hello", "World"]
editor.redo()  # forward to ["Hello", "World", "!"]
```

## Summary and Key Takeaways

- **Persistent data structures** create new versions on "update" while sharing structure
  with old versions -- O(log32 n) time and space per operation, effectively O(1) in practice
- **Structural sharing** is the key technique: only the path from root to the modified
  node is copied; all other nodes are shared between versions
- **Persistent vectors** use a wide trie (branching factor 32) with a tail optimization
  for fast appends; **HAMTs** use the same trie structure keyed by hash bits for maps
- **Best practice**: use persistent data structures when you need snapshots, undo/redo,
  safe concurrent reads, or functional pipeline composition
- **Pitfall**: implementing with a narrow branching factor (e.g., binary trees) --
  the depth becomes O(log2 n) = 32 levels for 4 billion elements, versus O(log32 n) = 7
  levels with a branching factor of 32
- **Trade-off**: persistent structures use ~2-4x more memory than mutable equivalents due
  to tree overhead, but enable O(1) versioning that would cost O(n) with copying
- In Python, the `pyrsistent` library provides production-quality persistent data
  structures; use it in production and study this implementation for understanding
""",
    ),

    # --- 4. Category Theory for Programmers ---
    (
        "category_theory_functors_monads_python",
        "Explain category theory concepts for programmers including functors, applicative functors, "
        "monads, natural transformations, and the functor-applicative-monad hierarchy with practical "
        "Python implementations. Cover the laws each must satisfy, show how they compose, and provide "
        "real-world examples demonstrating why these abstractions improve code quality and correctness.",
        r"""
# Category Theory for Programmers: Functors, Applicatives, and Monads

## Why Category Theory Matters for Software

Category theory is often dismissed as "abstract nonsense," but it provides the most
**precise vocabulary** for describing patterns that recur across all of programming.
When you learn that `map` over a list, `map` over an `Optional`, and `map` over a `Future`
all follow the same **functor laws**, you gain the ability to reason about all three
uniformly. This is not aesthetic -- it is **practical**, because code that respects
categorical laws is composable, testable, and predictable.

The hierarchy is: **Functor** (you can `map` over it) -> **Applicative** (you can apply
wrapped functions to wrapped values) -> **Monad** (you can `bind`/`flatMap` to chain
context-dependent computations). Each level adds power, and each level requires its
own laws. **Because** Python lacks type classes, we implement these as protocols with
explicit law-checking tests.

**Common mistake**: treating these abstractions as "just design patterns." Design patterns
are informal and language-specific. Categorical abstractions come with **laws** --
mathematical guarantees about behavior. A "functor" that violates the identity law
(`fmap(id, x) == x`) is not a functor, and code that assumes the law will break.

## Functors: Things You Can Map Over

A **functor** is a type constructor `F` with a `map` operation:
`map(f: A -> B, fa: F[A]) -> F[B]` that satisfies two laws:

1. **Identity**: `fa.map(lambda x: x) == fa`
2. **Composition**: `fa.map(f).map(g) == fa.map(lambda x: g(f(x)))`

These laws ensure that mapping preserves structure -- it transforms the values inside
the container without changing the container's shape.

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TypeVar, Generic, Callable, Protocol, runtime_checkable

A = TypeVar("A")
B = TypeVar("B")
C = TypeVar("C")


# ---- Functor protocol ----
@runtime_checkable
class Functor(Protocol[A]):
    def map(self, f: Callable[[A], B]) -> Functor[B]: ...


# ---- Maybe functor ----
@dataclass(frozen=True)
class Maybe(Generic[A]):
    _value: A | None

    @staticmethod
    def just(value: A) -> Maybe[A]:
        return Maybe(value)

    @staticmethod
    def nothing() -> Maybe[A]:
        return Maybe(None)

    def map(self, f: Callable[[A], B]) -> Maybe[B]:
        if self._value is None:
            return Maybe.nothing()
        return Maybe.just(f(self._value))

    @property
    def value(self) -> A | None:
        return self._value

    def __repr__(self) -> str:
        if self._value is None:
            return "Nothing"
        return f"Just({self._value!r})"


# ---- List functor ----
@dataclass(frozen=True)
class FList(Generic[A]):
    # Functional list wrapper that satisfies functor/applicative/monad laws
    _items: tuple[A, ...]

    @staticmethod
    def of(*items: A) -> FList[A]:
        return FList(items)

    def map(self, f: Callable[[A], B]) -> FList[B]:
        return FList(tuple(f(x) for x in self._items))

    @property
    def items(self) -> tuple[A, ...]:
        return self._items

    def __repr__(self) -> str:
        return f"FList({list(self._items)})"


# ---- Identity functor (simplest possible functor) ----
@dataclass(frozen=True)
class Identity(Generic[A]):
    value: A

    def map(self, f: Callable[[A], B]) -> Identity[B]:
        return Identity(f(self.value))

    def __repr__(self) -> str:
        return f"Identity({self.value!r})"


# ---- Law verification ----
def verify_functor_identity(fa: Maybe[int]) -> bool:
    # Identity law: fa.map(id) == fa
    return fa.map(lambda x: x) == fa


def verify_functor_composition(fa: Maybe[int], f: Callable, g: Callable) -> bool:
    # Composition law: fa.map(f).map(g) == fa.map(lambda x: g(f(x)))
    return fa.map(f).map(g) == fa.map(lambda x: g(f(x)))


# Test the laws
assert verify_functor_identity(Maybe.just(42))
assert verify_functor_identity(Maybe.nothing())
assert verify_functor_composition(Maybe.just(5), lambda x: x + 1, lambda x: x * 2)
```

## Applicative Functors: Applying Wrapped Functions

An **applicative functor** extends Functor with two operations:
- `pure(value: A) -> F[A]` -- wraps a plain value
- `apply(ff: F[A -> B], fa: F[A]) -> F[B]` -- applies a wrapped function to a wrapped value

This is more powerful than `map` **because** it allows combining **multiple independent**
wrapped values. With just `map`, you can transform one `Maybe[int]` to `Maybe[str]`, but
you cannot combine `Maybe[int]` and `Maybe[str]` into `Maybe[Tuple[int, str]]`.

The applicative laws are:
1. **Identity**: `pure(id).apply(v) == v`
2. **Composition**: `pure(compose).apply(u).apply(v).apply(w) == u.apply(v.apply(w))`
3. **Homomorphism**: `pure(f).apply(pure(x)) == pure(f(x))`
4. **Interchange**: `u.apply(pure(y)) == pure(lambda f: f(y)).apply(u)`

```python
# ---- Applicative Maybe ----
@dataclass(frozen=True)
class AMaybe(Generic[A]):
    _value: A | None

    @staticmethod
    def pure(value: A) -> AMaybe[A]:
        return AMaybe(value)

    @staticmethod
    def nothing() -> AMaybe[A]:
        return AMaybe(None)

    def map(self, f: Callable[[A], B]) -> AMaybe[B]:
        if self._value is None:
            return AMaybe.nothing()
        return AMaybe.pure(f(self._value))

    def apply(self, fa: AMaybe[A]) -> AMaybe[B]:
        # self contains a function A -> B, fa contains an A
        if self._value is None or fa._value is None:
            return AMaybe.nothing()
        return AMaybe.pure(self._value(fa._value))

    def __repr__(self) -> str:
        if self._value is None:
            return "Nothing"
        return f"Just({self._value!r})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, AMaybe):
            return NotImplemented
        return self._value == other._value


# Combining multiple Maybe values with applicative style
def lift_a2(f: Callable[[A, B], C], fa: AMaybe[A], fb: AMaybe[B]) -> AMaybe[C]:
    # Lift a 2-argument function to work on applicative values
    return AMaybe.pure(lambda a: lambda b: f(a, b)).apply(fa).apply(fb)


def lift_a3(f: Callable, fa: AMaybe, fb: AMaybe, fc: AMaybe) -> AMaybe:
    # Lift a 3-argument function to work on applicative values
    return (
        AMaybe.pure(lambda a: lambda b: lambda c: f(a, b, c))
        .apply(fa)
        .apply(fb)
        .apply(fc)
    )


# ---- Practical example: form validation ----
def validate_name(s: str) -> AMaybe[str]:
    return AMaybe.pure(s.strip()) if s.strip() else AMaybe.nothing()


def validate_age(s: str) -> AMaybe[int]:
    try:
        age = int(s)
        return AMaybe.pure(age) if 0 <= age <= 150 else AMaybe.nothing()
    except ValueError:
        return AMaybe.nothing()


def validate_email(s: str) -> AMaybe[str]:
    return AMaybe.pure(s) if "@" in s else AMaybe.nothing()


def make_user(name: str, age: int, email: str) -> dict:
    return {"name": name, "age": age, "email": email}


# All three validations must succeed, or the result is Nothing
user = lift_a3(
    make_user,
    validate_name("  Alice  "),
    validate_age("30"),
    validate_email("alice@example.com"),
)
# user == Just({'name': 'Alice', 'age': 30, 'email': 'alice@example.com'})
```

The **best practice** distinction: use **Applicative** when computations are
**independent** (each validation does not depend on the result of another). Use **Monad**
when computations are **dependent** (the second query depends on the result of the first).

## Natural Transformations: Converting Between Functors

A **natural transformation** is a mapping from one functor to another that preserves
structure. In programming terms, it is a polymorphic function `nat: F[A] -> G[A]` that
works for all types `A` and commutes with `map`:
`nat(fa.map(f)) == nat(fa).map(f)`

```python
# ---- Natural transformations ----

def maybe_to_list(m: Maybe[A]) -> FList[A]:
    # Natural transformation: Maybe -> FList
    # Nothing -> empty list, Just(x) -> single-element list
    if m.value is None:
        return FList.of()
    return FList.of(m.value)


def list_to_maybe(fl: FList[A]) -> Maybe[A]:
    # Natural transformation: FList -> Maybe
    # Takes the head element, if any
    if not fl.items:
        return Maybe.nothing()
    return Maybe.just(fl.items[0])


# Naturality condition: nat(fa.map(f)) == nat(fa).map(f)
m = Maybe.just(5)
f_transform = lambda x: x * 2

# These must be equal for the transformation to be natural:
result1 = maybe_to_list(m.map(f_transform))   # map then transform
result2 = maybe_to_list(m).map(f_transform)    # transform then map
# Both yield FList([10])
```

This matters **because** natural transformations let you change your data structure mid-pipeline
without losing the structure of the computation. A database query that returns `Maybe[User]`
can be naturally transformed to `List[User]` for downstream processing, and the naturality
law guarantees this transformation is well-behaved.

## Monads: Sequential, Context-Dependent Composition

A **monad** extends Applicative with `bind` (also called `flatMap` or `>>=`):
`bind(ma: M[A], f: A -> M[B]) -> M[B]`

The monad laws are:
1. **Left identity**: `pure(a).bind(f) == f(a)`
2. **Right identity**: `ma.bind(pure) == ma`
3. **Associativity**: `ma.bind(f).bind(g) == ma.bind(lambda x: f(x).bind(g))`

```python
# ---- Monad: extending AMaybe with bind ----
@dataclass(frozen=True)
class MMaybe(Generic[A]):
    _value: A | None

    @staticmethod
    def pure(value: A) -> MMaybe[A]:
        return MMaybe(value)

    @staticmethod
    def nothing() -> MMaybe[A]:
        return MMaybe(None)

    def map(self, f: Callable[[A], B]) -> MMaybe[B]:
        if self._value is None:
            return MMaybe.nothing()
        return MMaybe.pure(f(self._value))

    def bind(self, f: Callable[[A], MMaybe[B]]) -> MMaybe[B]:
        # The key monadic operation: chain context-dependent computations
        if self._value is None:
            return MMaybe.nothing()
        return f(self._value)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, MMaybe):
            return NotImplemented
        return self._value == other._value

    def __repr__(self) -> str:
        if self._value is None:
            return "Nothing"
        return f"Just({self._value!r})"


# ---- Verify monad laws ----
def verify_left_identity(a: int, f: Callable[[int], MMaybe[int]]) -> bool:
    return MMaybe.pure(a).bind(f) == f(a)


def verify_right_identity(ma: MMaybe[int]) -> bool:
    return ma.bind(MMaybe.pure) == ma


def verify_associativity(
    ma: MMaybe[int],
    f: Callable[[int], MMaybe[int]],
    g: Callable[[int], MMaybe[int]],
) -> bool:
    return ma.bind(f).bind(g) == ma.bind(lambda x: f(x).bind(g))


safe_div = lambda x: MMaybe.nothing() if x == 0 else MMaybe.pure(100 // x)
safe_sqrt = lambda x: MMaybe.nothing() if x < 0 else MMaybe.pure(int(x ** 0.5))

assert verify_left_identity(5, safe_div)
assert verify_right_identity(MMaybe.pure(42))
assert verify_associativity(MMaybe.pure(25), safe_sqrt, safe_div)
```

## Summary and Key Takeaways

- **Functors** provide `map`: transform values inside a context without changing the
  context's structure; the identity and composition laws ensure predictable behavior
- **Applicatives** provide `pure` and `apply`: combine **independent** wrapped values;
  use `lift_a2`/`lift_a3` to apply multi-argument functions to applicative values
- **Monads** provide `bind`: chain **dependent** computations where each step can
  influence the context; the three monad laws ensure composition is well-behaved
- **Natural transformations** convert between functors (e.g., `Maybe -> List`) while
  preserving the structure of mapped operations
- **Best practice**: verify laws with property-based tests using Hypothesis -- generate
  random values and functions, and assert that identity, composition, and associativity
  hold; a lawful instance is a correct instance
- **Pitfall**: creating instances that violate laws -- e.g., a "Maybe" where `map(id)`
  strips whitespace is **not** a functor, and downstream code assuming the identity law
  will produce incorrect results
- **Trade-off**: Python lacks type classes and higher-kinded types, so these abstractions
  require more boilerplate than in Haskell or Scala; however, the conceptual framework
  still improves code design even without compiler support
""",
    ),

    # --- 5. Parser Combinators ---
    (
        "parser_combinators_json_parser_python",
        "Explain parser combinators for building parsers from small composable functions, including "
        "implementing a complete JSON parser with error recovery and position tracking. Cover the "
        "fundamental combinators (sequence, choice, many, map), monadic parser composition, error "
        "reporting with source locations, and provide a full Python implementation with type hints.",
        r"""
# Parser Combinators: Building a JSON Parser from Composable Functions

## What Are Parser Combinators and Why Use Them

A **parser combinator** library lets you build complex parsers by composing small, simple
parsing functions. Instead of writing a monolithic parser or using a separate grammar file
(like ANTLR or yacc), you write parsers **in the host language** as values that can be
combined with operators. A parser for "a number followed by a plus sign followed by a
number" is literally `number >> char('+') >> number` -- readable, testable, and modular.

This matters **because** parser combinators occupy a sweet spot between regular expressions
(too weak for nested structures) and parser generators (require a separate toolchain). They
handle recursive grammars, produce excellent error messages, and are trivially extensible.

**Common mistake**: using regex for structured formats like JSON, XML, or programming
languages. Regular expressions **cannot** match nested brackets -- they lack the stack
needed for context-free grammars. Parser combinators handle recursion naturally **because**
a parser can reference itself.

**Trade-off**: parser combinators are typically slower than hand-written recursive descent
parsers or table-driven parser generators. However, for configuration files, DSLs, and
protocol messages, the difference is negligible, and the development speed advantage is
substantial.

## The Core: Parser Type and Fundamental Combinators

A parser is a function that takes an input string (with a position) and returns either
a **success** (parsed value + remaining input) or a **failure** (error message + position).
This is exactly the `Result` monad applied to parsing.

```python
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypeVar, Generic, Callable, Sequence, Optional, Union
import re
import string

T = TypeVar("T")
U = TypeVar("U")


@dataclass(frozen=True)
class SourcePos:
    # Tracks position in source for error reporting
    offset: int
    line: int
    col: int

    @staticmethod
    def start() -> SourcePos:
        return SourcePos(0, 1, 1)

    def advance(self, char: str) -> SourcePos:
        if char == "\n":
            return SourcePos(self.offset + 1, self.line + 1, 1)
        return SourcePos(self.offset + 1, self.line, self.col + 1)

    def advance_by(self, text: str) -> SourcePos:
        pos = self
        for ch in text:
            pos = pos.advance(ch)
        return pos

    def __str__(self) -> str:
        return f"line {self.line}, col {self.col}"


@dataclass(frozen=True)
class ParseError:
    pos: SourcePos
    expected: tuple[str, ...]
    context: str = ""

    def __str__(self) -> str:
        expected_str = " or ".join(self.expected)
        msg = f"Parse error at {self.pos}: expected {expected_str}"
        if self.context:
            msg += f" (in {self.context})"
        return msg

    def merge(self, other: ParseError) -> ParseError:
        # Combine error messages from alternatives
        if self.pos.offset > other.pos.offset:
            return self
        if other.pos.offset > self.pos.offset:
            return other
        return ParseError(self.pos, self.expected + other.expected)


@dataclass(frozen=True)
class ParseState:
    text: str
    pos: SourcePos

    @staticmethod
    def from_string(text: str) -> ParseState:
        return ParseState(text, SourcePos.start())

    @property
    def remaining(self) -> str:
        return self.text[self.pos.offset:]

    @property
    def at_end(self) -> bool:
        return self.pos.offset >= len(self.text)

    def peek(self) -> Optional[str]:
        if self.at_end:
            return None
        return self.text[self.pos.offset]


@dataclass(frozen=True)
class Success(Generic[T]):
    value: T
    state: ParseState


@dataclass(frozen=True)
class Failure:
    error: ParseError


# A ParseResult is either Success or Failure
ParseResult = Union[Success[T], Failure]


class Parser(Generic[T]):
    # A parser combinator: wraps a parsing function and provides
    # combinators for composition (map, bind, >>, |, many, etc.)

    def __init__(self, fn: Callable[[ParseState], ParseResult[T]]) -> None:
        self._fn = fn

    def parse(self, state: ParseState) -> ParseResult[T]:
        return self._fn(state)

    def run(self, text: str) -> ParseResult[T]:
        # Convenience: parse from a string
        return self.parse(ParseState.from_string(text))

    # ---- Functor ----
    def map(self, f: Callable[[T], U]) -> Parser[U]:
        def parse(state: ParseState) -> ParseResult[U]:
            result = self.parse(state)
            if isinstance(result, Failure):
                return result
            return Success(f(result.value), result.state)
        return Parser(parse)

    # ---- Monad ----
    def bind(self, f: Callable[[T], Parser[U]]) -> Parser[U]:
        # Monadic bind: use the result of this parser to choose the next parser
        def parse(state: ParseState) -> ParseResult[U]:
            result = self.parse(state)
            if isinstance(result, Failure):
                return result
            return f(result.value).parse(result.state)
        return Parser(parse)

    # ---- Sequencing ----
    def then(self, other: Parser[U]) -> Parser[U]:
        # Parse self, discard result, then parse other
        return self.bind(lambda _: other)

    def skip(self, other: Parser) -> Parser[T]:
        # Parse self, keep result, then parse other and discard
        return self.bind(lambda v: other.map(lambda _: v))

    # ---- Alternation ----
    def or_else(self, other: Parser[T]) -> Parser[T]:
        # Try self first; if it fails without consuming input, try other
        def parse(state: ParseState) -> ParseResult[T]:
            result = self.parse(state)
            if isinstance(result, Success):
                return result
            # Only try alternative if we did not consume input
            if isinstance(result, Failure) and result.error.pos.offset == state.pos.offset:
                result2 = other.parse(state)
                if isinstance(result2, Failure):
                    return Failure(result.error.merge(result2.error))
                return result2
            return result
        return Parser(parse)

    # ---- Repetition ----
    def many(self) -> Parser[list[T]]:
        # Parse zero or more occurrences
        def parse(state: ParseState) -> ParseResult[list[T]]:
            results: list[T] = []
            current = state
            while True:
                result = self.parse(current)
                if isinstance(result, Failure):
                    return Success(results, current)
                results.append(result.value)
                current = result.state
        return Parser(parse)

    def many1(self) -> Parser[list[T]]:
        # Parse one or more occurrences
        return self.bind(lambda first: self.many().map(lambda rest: [first] + rest))

    def sep_by(self, sep: Parser) -> Parser[list[T]]:
        # Parse zero or more occurrences separated by sep
        rest = sep.then(self).many()
        first_then_rest = self.bind(lambda f: rest.map(lambda r: [f] + r))
        return first_then_rest.or_else(pure([]))

    def optional(self, default: T = None) -> Parser[Optional[T]]:
        return self.or_else(pure(default))

    def label(self, name: str) -> Parser[T]:
        # Provide a human-readable name for error messages
        def parse(state: ParseState) -> ParseResult[T]:
            result = self.parse(state)
            if isinstance(result, Failure):
                return Failure(ParseError(state.pos, (name,)))
            return result
        return Parser(parse)
```

## Primitive Parsers: Building Blocks

These primitives are the atoms from which all parsers are built. Each one is simple
and handles exactly one concern.

```python
# ---- Primitive parsers ----

def pure(value: T) -> Parser[T]:
    # Always succeeds without consuming input
    return Parser(lambda state: Success(value, state))


def fail(expected: str) -> Parser:
    # Always fails with the given expectation
    return Parser(lambda state: Failure(ParseError(state.pos, (expected,))))


def satisfy(predicate: Callable[[str], bool], expected: str) -> Parser[str]:
    # Parse a single character matching the predicate
    def parse(state: ParseState) -> ParseResult[str]:
        if state.at_end:
            return Failure(ParseError(state.pos, (expected,)))
        ch = state.text[state.pos.offset]
        if predicate(ch):
            return Success(ch, ParseState(state.text, state.pos.advance(ch)))
        return Failure(ParseError(state.pos, (expected,)))
    return Parser(parse)


def char(c: str) -> Parser[str]:
    return satisfy(lambda ch: ch == c, repr(c))


def string(s: str) -> Parser[str]:
    # Parse an exact string
    def parse(state: ParseState) -> ParseResult[str]:
        remaining = state.remaining
        if remaining.startswith(s):
            return Success(s, ParseState(state.text, state.pos.advance_by(s)))
        return Failure(ParseError(state.pos, (repr(s),)))
    return Parser(parse)


def regex(pattern: str, group: int = 0, expected: str = "") -> Parser[str]:
    compiled = re.compile(pattern)
    def parse(state: ParseState) -> ParseResult[str]:
        m = compiled.match(state.remaining)
        if m is None:
            return Failure(ParseError(state.pos, (expected or pattern,)))
        matched = m.group(group)
        return Success(matched, ParseState(state.text, state.pos.advance_by(m.group(0))))
    return Parser(parse)


# Common character classes
digit = satisfy(str.isdigit, "digit")
letter = satisfy(str.isalpha, "letter")
whitespace = satisfy(str.isspace, "whitespace")
ws = whitespace.many().map(lambda chars: "".join(chars))  # optional whitespace


def between(open_p: Parser, close_p: Parser, content: Parser[T]) -> Parser[T]:
    # Parse content between open and close delimiters
    return open_p.then(content).skip(close_p)


def lazy(fn: Callable[[], Parser[T]]) -> Parser[T]:
    # Deferred parser construction for recursive grammars
    return Parser(lambda state: fn().parse(state))
```

## Complete JSON Parser

Now we combine these primitives to build a **complete JSON parser** with proper error
messages and position tracking. This demonstrates the power of composition -- each
sub-parser is independently testable.

```python
# ---- JSON Parser built from combinators ----

# JSON whitespace
json_ws = regex(r"[ \t\n\r]*", expected="whitespace")

# JSON null
json_null: Parser = string("null").map(lambda _: None).label("null")

# JSON booleans
json_true: Parser = string("true").map(lambda _: True)
json_false: Parser = string("false").map(lambda _: False)
json_bool: Parser = json_true.or_else(json_false).label("boolean")

# JSON numbers (integers and floats)
json_number: Parser[float] = regex(
    r"-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?",
    expected="number",
).map(float).label("number")

# JSON strings with escape handling
def _parse_json_string(state: ParseState) -> ParseResult[str]:
    if state.at_end or state.text[state.pos.offset] != '"':
        return Failure(ParseError(state.pos, ('"\\"" (string)',)))

    pos = state.pos.advance('"')  # skip opening quote
    chars: list[str] = []
    offset = pos.offset

    while offset < len(state.text):
        ch = state.text[offset]
        if ch == '"':
            # End of string
            final_pos = SourcePos(offset + 1, pos.line, pos.col + len(chars) + 1)
            return Success("".join(chars), ParseState(state.text, final_pos))
        elif ch == '\\':
            offset += 1
            if offset >= len(state.text):
                return Failure(ParseError(pos, ("escape sequence",)))
            esc = state.text[offset]
            escape_map = {'"': '"', '\\': '\\', '/': '/', 'b': '\b',
                          'f': '\f', 'n': '\n', 'r': '\r', 't': '\t'}
            if esc in escape_map:
                chars.append(escape_map[esc])
            elif esc == 'u':
                hex_str = state.text[offset + 1:offset + 5]
                if len(hex_str) < 4:
                    return Failure(ParseError(pos, ("4 hex digits",)))
                chars.append(chr(int(hex_str, 16)))
                offset += 4
            else:
                return Failure(ParseError(pos, (f"valid escape (got \\{esc})",)))
        else:
            chars.append(ch)
        offset += 1

    return Failure(ParseError(pos, ("closing quote",)))


json_string: Parser[str] = Parser(_parse_json_string).label("string")

# JSON array: [ value, value, ... ]
def _json_array() -> Parser[list]:
    return between(
        char("[").skip(json_ws),
        json_ws.then(char("]")),
        lazy(lambda: json_value).sep_by(json_ws.then(char(",")).skip(json_ws)),
    ).label("array")

# JSON object: { "key": value, ... }
def _json_object() -> Parser[dict]:
    pair = (
        json_string
        .skip(json_ws)
        .skip(char(":"))
        .skip(json_ws)
        .bind(lambda key: lazy(lambda: json_value).map(lambda val: (key, val)))
    )
    pairs = pair.sep_by(json_ws.then(char(",")).skip(json_ws))
    return between(
        char("{").skip(json_ws),
        json_ws.then(char("}")),
        pairs,
    ).map(dict).label("object")

# The top-level JSON value parser
json_value: Parser = (
    json_null
    .or_else(json_bool)
    .or_else(json_number)
    .or_else(json_string)
    .or_else(lazy(_json_array))
    .or_else(lazy(_json_object))
).label("JSON value")

# Full JSON document parser (with leading/trailing whitespace)
json_document: Parser = json_ws.then(json_value).skip(json_ws)


# ---- Usage ----
def parse_json(text: str) -> object:
    # Parse a JSON string, raising ValueError on failure
    result = json_document.run(text)
    if isinstance(result, Failure):
        raise ValueError(str(result.error))
    return result.value


# Examples:
# parse_json('{"name": "Alice", "age": 30, "scores": [95, 87, 92]}')
# -> {'name': 'Alice', 'age': 30, 'scores': [95.0, 87.0, 92.0]}
#
# parse_json('[1, [2, [3, []]]]')
# -> [1.0, [2.0, [3.0, []]]]
```

## Error Recovery and Best Practices

**Best practice** for error messages: use `.label()` liberally to give human-readable names
to parsers. Without labels, a failure in a deeply nested parser reports "expected digit"
when it should report "expected number in array element." The label combinator replaces
low-level error messages with higher-level context.

**Pitfall**: left recursion. Parser combinators using recursive descent will loop forever
on left-recursive grammars like `expr = expr + term`. The standard solution is to rewrite
as `expr = term ('+' term)*` using `sep_by` or `many`. This is a fundamental limitation
of top-down parsing, not specific to combinators.

**Best practice** for performance: avoid excessive backtracking by ordering alternatives
carefully. Place the most likely alternative first, and use `string("true")` instead of
`char('t').then(char('r')).then(char('u')).then(char('e'))` to match multi-character
tokens in a single operation.

## Summary and Key Takeaways

- **Parser combinators** build complex parsers from small functions using composition
  operators: `then` (sequence), `or_else` (choice), `many` (repetition), `map` (transform),
  and `bind` (context-dependent sequencing)
- The parser type is fundamentally **monadic**: `bind` allows one parser's result to
  determine which parser runs next, enabling context-sensitive parsing
- **Structural sharing** with the host language means parsers are first-class values --
  you can store them in variables, pass them to functions, and compute them dynamically
- **Best practice**: use `lazy()` for recursive grammars to avoid infinite recursion
  during parser construction; use `.label()` for readable error messages
- **Pitfall**: left recursion causes infinite loops in recursive descent combinators;
  always rewrite left-recursive rules as right-recursive with `many` or `sep_by`
- **Trade-off**: parser combinators are slower than parser generators (no table
  pre-computation) but faster to develop, easier to debug, and trivially extensible
  with new combinators
- The approach demonstrated here scales to real-world parsers: add position tracking
  for IDE integration, error recovery for partial parsing, and memoization (Packrat
  parsing) for guaranteed linear-time performance
""",
    ),
]
