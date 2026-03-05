"""Type systems — TypeScript advanced (template literals, conditional types, mapped types), Python type hints, runtime validation."""

PAIRS = [
    (
        "type-systems/typescript-template-literals-conditional-types",
        "Show advanced TypeScript template literal types and conditional types for building a type-safe event system, route parser, and branded types with deep inference.",
        '''Advanced TypeScript template literal types and conditional types:

```typescript
// ============================================================
// 1. Type-safe event system with template literal inference
// ============================================================

type EventName = "user" | "order" | "payment";
type EventAction = "created" | "updated" | "deleted";
type EventString = `${EventName}:${EventAction}`;

// Parse event strings back into structured types
type ParseEvent<S extends string> =
  S extends `${infer Name}:${infer Action}`
    ? { name: Name; action: Action }
    : never;

type Parsed = ParseEvent<"user:created">;
// { name: "user"; action: "created" }

// Build a type-safe event emitter
type EventPayloads = {
  "user:created": { id: string; email: string; createdAt: Date };
  "user:updated": { id: string; changes: Partial<{ email: string; name: string }> };
  "user:deleted": { id: string; reason?: string };
  "order:created": { orderId: string; items: Array<{ sku: string; qty: number }> };
  "order:updated": { orderId: string; status: "pending" | "shipped" | "delivered" };
  "payment:created": { paymentId: string; amount: number; currency: string };
};

class TypedEventEmitter<TPayloads extends Record<string, any>> {
  private handlers = new Map<string, Set<Function>>();

  on<K extends keyof TPayloads & string>(
    event: K,
    handler: (payload: TPayloads[K]) => void
  ): () => void {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, new Set());
    }
    this.handlers.get(event)!.add(handler);
    return () => this.handlers.get(event)?.delete(handler);
  }

  emit<K extends keyof TPayloads & string>(
    event: K,
    payload: TPayloads[K]
  ): void {
    this.handlers.get(event)?.forEach((fn) => fn(payload));
  }

  // Type-safe wildcard: listen to all events matching a pattern
  onPattern<P extends EventName>(
    pattern: P,
    handler: (event: `${P}:${EventAction}`, payload: any) => void
  ): void {
    for (const [key, fns] of this.handlers) {
      if (key.startsWith(`${pattern}:`)) {
        // rewire
      }
    }
  }
}

const emitter = new TypedEventEmitter<EventPayloads>();

// Fully typed - TS knows payload shape
emitter.on("user:created", (payload) => {
  console.log(payload.id, payload.email); // OK
  // payload.orderId; // Error: Property 'orderId' does not exist
});

emitter.emit("order:created", {
  orderId: "abc",
  items: [{ sku: "WIDGET-1", qty: 3 }],
});


// ============================================================
// 2. Type-safe route parser using template literal inference
// ============================================================

type ExtractParams<T extends string> =
  T extends `${string}:${infer Param}/${infer Rest}`
    ? { [K in Param | keyof ExtractParams<Rest>]: string }
    : T extends `${string}:${infer Param}`
      ? { [K in Param]: string }
      : {};

type RouteParams = ExtractParams<"/users/:userId/posts/:postId">;
// { userId: string; postId: string }

type RouteDef<TPath extends string, TResponse> = {
  path: TPath;
  handler: (params: ExtractParams<TPath>) => Promise<TResponse>;
};

function defineRoute<TPath extends string, TResponse>(
  def: RouteDef<TPath, TResponse>
): RouteDef<TPath, TResponse> {
  return def;
}

const userRoute = defineRoute({
  path: "/users/:userId/posts/:postId",
  handler: async (params) => {
    // params is { userId: string; postId: string } - fully inferred
    return { user: params.userId, post: params.postId };
  },
});


// ============================================================
// 3. Branded / nominal types for domain safety
// ============================================================

declare const __brand: unique symbol;
type Brand<T, B extends string> = T & { readonly [__brand]: B };

type UserId = Brand<string, "UserId">;
type OrderId = Brand<string, "OrderId">;
type Cents = Brand<number, "Cents">;
type Dollars = Brand<number, "Dollars">;

function createUserId(id: string): UserId {
  if (!/^usr_[a-z0-9]{12}$/.test(id)) throw new Error("Invalid user ID");
  return id as UserId;
}

function createOrderId(id: string): OrderId {
  if (!/^ord_[a-z0-9]{12}$/.test(id)) throw new Error("Invalid order ID");
  return id as OrderId;
}

function dollarsToCents(d: Dollars): Cents {
  return Math.round(d * 100) as Cents;
}

function chargeUser(userId: UserId, amount: Cents): void {
  // ...
}

const uid = createUserId("usr_abc123def456");
const oid = createOrderId("ord_xyz789ghi012");
const price = 19.99 as Dollars;

chargeUser(uid, dollarsToCents(price)); // OK
// chargeUser(oid, price);  // Error: OrderId not assignable to UserId
//                          // Error: Dollars not assignable to Cents


// ============================================================
// 4. Advanced conditional type patterns
// ============================================================

// Deep readonly
type DeepReadonly<T> =
  T extends (infer U)[]
    ? ReadonlyArray<DeepReadonly<U>>
    : T extends Map<infer K, infer V>
      ? ReadonlyMap<DeepReadonly<K>, DeepReadonly<V>>
      : T extends Set<infer U>
        ? ReadonlySet<DeepReadonly<U>>
        : T extends object
          ? { readonly [P in keyof T]: DeepReadonly<T[P]> }
          : T;

// Type-safe builder pattern using conditional accumulation
type BuilderState = { [key: string]: boolean };

type Builder<T, State extends BuilderState = {}> = {
  [K in keyof T as K extends string
    ? State[K] extends true ? never : `set${Capitalize<K>}`
    : never
  ]: (
    value: T[K]
  ) => Builder<T, State & { [P in K & string]: true }>;
} & (
  keyof { [K in keyof T as State[K & string] extends true ? never : K]: 1 } extends never
    ? { build(): T }
    : {}
);

interface UserConfig {
  name: string;
  email: string;
  role: "admin" | "user";
}

declare function createBuilder<T>(): Builder<T>;

const builder = createBuilder<UserConfig>();
const result = builder
  .setName("Alice")       // returns Builder with name marked set
  .setEmail("a@b.com")    // returns Builder with name+email marked set
  .setRole("admin")       // returns Builder with all marked set
  .build();               // build() only available when all fields set
```

**Key patterns:**

| Pattern | Purpose | Example |
|---------|---------|---------|
| Template literal types | Parse/construct string types | `${Name}:${Action}` |
| Conditional type inference | Extract types from structures | `T extends X ? infer R : never` |
| Branded/nominal types | Prevent cross-domain assignment | `Brand<string, "UserId">` |
| Recursive conditional types | Deep transformations | `DeepReadonly<T>` |
| Mapped type filtering | Conditional property inclusion | `[K in keyof T as Cond<K>]` |

**Best practices:**
- Use branded types for domain IDs, monetary values, and units to prevent mix-ups
- Template literal types replace runtime string parsing with compile-time guarantees
- Keep conditional type depth manageable (TypeScript has a recursion limit of ~50)
- Use `satisfies` operator (TS 5.x+) to validate types without widening
- Prefer `NoInfer<T>` (TS 5.4+) to control inference sites in generic functions'''
    ),
    (
        "type-systems/typescript-mapped-types-advanced",
        "Demonstrate advanced TypeScript mapped types including key remapping, variadic tuple types, and recursive type transformations for building a type-safe ORM query builder.",
        '''Advanced TypeScript mapped types and variadic tuples for a type-safe ORM:

```typescript
// ============================================================
// 1. Key remapping and property modifiers
// ============================================================

// Remap keys to getter/setter pairs
type Accessors<T> = {
  [K in keyof T as `get${Capitalize<K & string>}`]: () => T[K];
} & {
  [K in keyof T as `set${Capitalize<K & string>}`]: (value: T[K]) => void;
};

interface User {
  name: string;
  age: number;
  active: boolean;
}

type UserAccessors = Accessors<User>;
// {
//   getName: () => string;   setName: (value: string) => void;
//   getAge: () => number;    setAge: (value: number) => void;
//   getActive: () => boolean; setActive: (value: boolean) => void;
// }


// Filter properties by value type
type PropertiesOfType<T, V> = {
  [K in keyof T as T[K] extends V ? K : never]: T[K];
};

type StringProps = PropertiesOfType<User, string>;
// { name: string }

type NumericProps = PropertiesOfType<User, number>;
// { age: number }


// ============================================================
// 2. Variadic tuple types for composable pipelines
// ============================================================

type Pipeline<TInput, TOutput> = (input: TInput) => TOutput;

// Compose pipeline from array of transforms
type PipelineChain<T extends any[]> =
  T extends [Pipeline<infer A, infer B>]
    ? Pipeline<A, B>
    : T extends [Pipeline<infer A, infer B>, ...infer Rest]
      ? Rest extends [Pipeline<B, any>, ...any[]]
        ? Pipeline<A, PipelineChain<Rest> extends Pipeline<B, infer Final> ? Final : never>
        : never
      : never;

// Typed pipe function
function pipe<A, B>(f1: Pipeline<A, B>): Pipeline<A, B>;
function pipe<A, B, C>(f1: Pipeline<A, B>, f2: Pipeline<B, C>): Pipeline<A, C>;
function pipe<A, B, C, D>(
  f1: Pipeline<A, B>, f2: Pipeline<B, C>, f3: Pipeline<C, D>
): Pipeline<A, D>;
function pipe<A, B, C, D, E>(
  f1: Pipeline<A, B>, f2: Pipeline<B, C>, f3: Pipeline<C, D>, f4: Pipeline<D, E>
): Pipeline<A, E>;
function pipe(...fns: Function[]) {
  return (input: any) => fns.reduce((acc, fn) => fn(acc), input);
}

const transform = pipe(
  (x: string) => parseInt(x, 10),     // string -> number
  (x: number) => x * 2,                // number -> number
  (x: number) => ({ value: x }),        // number -> { value: number }
  (x: { value: number }) => x.value > 0 // { value: number } -> boolean
);

const result: boolean = transform("42"); // Fully typed end-to-end


// ============================================================
// 3. Type-safe ORM query builder
// ============================================================

// Schema definition
interface Schema {
  users: {
    id: number;
    name: string;
    email: string;
    department_id: number;
    created_at: Date;
    salary: number;
  };
  departments: {
    id: number;
    name: string;
    budget: number;
    location: string;
  };
  orders: {
    id: number;
    user_id: number;
    total: number;
    status: "pending" | "shipped" | "delivered";
    ordered_at: Date;
  };
}

// Column reference type
type ColumnRef<T extends keyof Schema> = keyof Schema[T] & string;

// Select result type based on selected columns
type SelectResult<
  T extends keyof Schema,
  Cols extends ColumnRef<T>[]
> = Pick<Schema[T], Cols[number]>;

// Comparison operators
type WhereOp = "=" | "!=" | ">" | "<" | ">=" | "<=" | "LIKE" | "IN";

type WhereClause<T extends keyof Schema> = {
  column: ColumnRef<T>;
  op: WhereOp;
  value: Schema[T][keyof Schema[T]];
};

// Order direction
type OrderDir = "ASC" | "DESC";

// Query builder with method chaining
class QueryBuilder<
  T extends keyof Schema,
  Selected extends ColumnRef<T>[] = [],
  HasWhere extends boolean = false
> {
  private tableName: T;
  private selectedCols: string[] = [];
  private whereClauses: string[] = [];
  private orderClauses: string[] = [];
  private limitCount?: number;
  private offsetCount?: number;

  constructor(table: T) {
    this.tableName = table;
  }

  select<C extends ColumnRef<T>[]>(
    ...columns: C
  ): QueryBuilder<T, C, HasWhere> {
    this.selectedCols = columns;
    return this as any;
  }

  where<K extends ColumnRef<T>>(
    column: K,
    op: WhereOp,
    value: Schema[T][K]
  ): QueryBuilder<T, Selected, true> {
    this.whereClauses.push(`${String(column)} ${op} ?`);
    return this as any;
  }

  andWhere<K extends ColumnRef<T>>(
    column: K,
    op: WhereOp,
    value: Schema[T][K]
  ): HasWhere extends true ? QueryBuilder<T, Selected, true> : never {
    this.whereClauses.push(`AND ${String(column)} ${op} ?`);
    return this as any;
  }

  orderBy(
    column: ColumnRef<T>,
    direction: OrderDir = "ASC"
  ): QueryBuilder<T, Selected, HasWhere> {
    this.orderClauses.push(`${column} ${direction}`);
    return this as any;
  }

  limit(count: number): QueryBuilder<T, Selected, HasWhere> {
    this.limitCount = count;
    return this;
  }

  offset(count: number): QueryBuilder<T, Selected, HasWhere> {
    this.offsetCount = count;
    return this;
  }

  toSQL(): string {
    const cols = this.selectedCols.length > 0
      ? this.selectedCols.join(", ")
      : "*";
    let sql = `SELECT ${cols} FROM ${String(this.tableName)}`;
    if (this.whereClauses.length > 0) {
      sql += ` WHERE ${this.whereClauses.join(" ")}`;
    }
    if (this.orderClauses.length > 0) {
      sql += ` ORDER BY ${this.orderClauses.join(", ")}`;
    }
    if (this.limitCount !== undefined) sql += ` LIMIT ${this.limitCount}`;
    if (this.offsetCount !== undefined) sql += ` OFFSET ${this.offsetCount}`;
    return sql;
  }

  async execute(): Promise<
    Selected extends [] ? Schema[T][] : SelectResult<T, Selected>[]
  > {
    const sql = this.toSQL();
    // Execute against DB...
    return [] as any;
  }
}

function from<T extends keyof Schema>(table: T): QueryBuilder<T> {
  return new QueryBuilder(table);
}

// Usage - everything is type-safe
const query = from("users")
  .select("id", "name", "email")
  .where("department_id", "=", 5)
  .andWhere("salary", ">", 50000)
  .orderBy("name", "ASC")
  .limit(10);

// Result type is Pick<Schema["users"], "id" | "name" | "email">[]
const users = await query.execute();
users[0].name;  // OK: string
users[0].email; // OK: string
// users[0].salary; // Error: not in selected columns
```

**Mapped type techniques:**

| Technique | Syntax | Use Case |
|-----------|--------|----------|
| Key remapping | `[K in keyof T as NewKey]` | Rename/transform property keys |
| Filtering | `[K as Cond ? K : never]` | Remove properties by type |
| Variadic tuples | `[...T, U]` | Type-safe function composition |
| Recursive mapping | `T[K] extends obj ? Deep<T[K]> : T[K]` | Deep transformations |
| Generic constraints | `K extends ColumnRef<T>` | Schema-aware builders |

**Best practices:**
- Use `NoInfer<T>` to prevent unwanted inference widening on builder methods
- Keep mapped type depth under control to avoid "type instantiation too deep" errors
- Prefer `satisfies` over `as const` assertions when you need both validation and inference
- Use conditional types with `infer` for decomposing complex structures'''
    ),
    (
        "type-systems/python-type-hints-advanced",
        "Show advanced Python type hints including ParamSpec, TypeVarTuple, Protocol with generic bounds, overloaded signatures, and runtime-checkable protocols for a plugin system.",
        '''Advanced Python type hints (3.12+ syntax) for production systems:

```python
"""Advanced Python typing patterns — ParamSpec, TypeVarTuple,
Protocol, overload, and runtime-checkable protocols."""

from __future__ import annotations

import asyncio
import functools
import inspect
import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import (
    Any,
    Generic,
    Literal,
    Never,
    ParamSpec,
    Protocol,
    Self,
    TypeGuard,
    TypeVar,
    TypeVarTuple,
    Unpack,
    overload,
    runtime_checkable,
)

logger = logging.getLogger(__name__)

# ============================================================
# 1. ParamSpec — preserve function signatures through decorators
# ============================================================

P = ParamSpec("P")
R = TypeVar("R")


def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Retry decorator that fully preserves the wrapped function's signature."""

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exc: Exception | None = None
            current_delay = delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    logger.warning(
                        "Attempt %d/%d for %s failed: %s",
                        attempt, max_attempts, func.__name__, exc,
                    )
                    if attempt < max_attempts:
                        time.sleep(current_delay)
                        current_delay *= backoff
            raise last_exc  # type: ignore[misc]

        return wrapper

    return decorator


def async_retry(
    max_attempts: int = 3,
    delay: float = 1.0,
) -> Callable[
    [Callable[P, Awaitable[R]]], Callable[P, Awaitable[R]]
]:
    """Async-aware retry that preserves async function signatures."""

    def decorator(
        func: Callable[P, Awaitable[R]],
    ) -> Callable[P, Awaitable[R]]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except Exception as exc:
                    last_exc = exc
                    if attempt < max_attempts:
                        await asyncio.sleep(delay * (2 ** (attempt - 1)))
            raise last_exc  # type: ignore[misc]

        return wrapper  # type: ignore[return-value]

    return decorator


@retry(max_attempts=3, exceptions=(ConnectionError, TimeoutError))
def fetch_data(url: str, timeout: int = 30) -> dict[str, Any]:
    """Type checker knows signature is (url: str, timeout: int = 30) -> dict."""
    ...


# ============================================================
# 2. TypeVarTuple — variadic generics
# ============================================================

Ts = TypeVarTuple("Ts")


class TypedPipeline(Generic[*Ts]):
    """Pipeline that tracks intermediate types through each stage."""

    def __init__(self, *stages: *Ts) -> None:
        self._stages = stages

    def __len__(self) -> int:
        return len(self._stages)


@overload
def pipeline(s1: Callable[[Any], R]) -> Callable[[Any], R]: ...
@overload
def pipeline(
    s1: Callable[[Any], Any], s2: Callable[[Any], R]
) -> Callable[[Any], R]: ...
@overload
def pipeline(
    s1: Callable[[Any], Any],
    s2: Callable[[Any], Any],
    s3: Callable[[Any], R],
) -> Callable[[Any], R]: ...


def pipeline(*stages: Callable[..., Any]) -> Callable[..., Any]:
    """Compose callables into a left-to-right pipeline."""

    def run(data: Any) -> Any:
        result = data
        for stage in stages:
            result = stage(result)
        return result

    return run


transform = pipeline(
    lambda x: int(x),        # str -> int
    lambda x: x * 2,         # int -> int
    lambda x: f"${x:.2f}",   # int -> str
)
result: str = transform("42")  # "$84.00"


# ============================================================
# 3. Protocol with generic bounds — plugin system
# ============================================================

T_co = TypeVar("T_co", covariant=True)
T_contra = TypeVar("T_contra", contravariant=True)


@runtime_checkable
class Plugin(Protocol[T_contra, T_co]):
    """Protocol for type-safe plugins."""

    @property
    def name(self) -> str: ...

    @property
    def version(self) -> tuple[int, int, int]: ...

    def process(self, data: T_contra) -> T_co: ...

    def health_check(self) -> bool: ...


@runtime_checkable
class AsyncPlugin(Protocol[T_contra, T_co]):
    """Async variant of the plugin protocol."""

    @property
    def name(self) -> str: ...

    async def process(self, data: T_contra) -> T_co: ...


@dataclass
class MarkdownPlugin:
    """Converts raw text to HTML — satisfies Plugin[str, str]."""

    name: str = "markdown"
    version: tuple[int, int, int] = (1, 0, 0)

    def process(self, data: str) -> str:
        # Simplified markdown to HTML
        lines = data.split("\\n")
        html_lines: list[str] = []
        for line in lines:
            if line.startswith("# "):
                html_lines.append(f"<h1>{line[2:]}</h1>")
            elif line.startswith("## "):
                html_lines.append(f"<h2>{line[3:]}</h2>")
            else:
                html_lines.append(f"<p>{line}</p>")
        return "\\n".join(html_lines)

    def health_check(self) -> bool:
        return True


# Runtime protocol check
assert isinstance(MarkdownPlugin(), Plugin)


class PluginRegistry(Generic[T_contra, T_co]):
    """Registry that enforces plugin type contracts."""

    def __init__(self) -> None:
        self._plugins: dict[str, Plugin[T_contra, T_co]] = {}

    def register(self, plugin: Plugin[T_contra, T_co]) -> None:
        if not isinstance(plugin, Plugin):
            raise TypeError(f"{plugin} does not satisfy Plugin protocol")
        self._plugins[plugin.name] = plugin

    def get(self, name: str) -> Plugin[T_contra, T_co] | None:
        return self._plugins.get(name)

    def process_all(self, data: T_contra) -> list[T_co]:
        return [p.process(data) for p in self._plugins.values()]


registry = PluginRegistry[str, str]()
registry.register(MarkdownPlugin())


# ============================================================
# 4. TypeGuard and type narrowing
# ============================================================

@dataclass
class ApiSuccess(Generic[T_co]):
    data: T_co
    status: Literal["ok"] = "ok"


@dataclass
class ApiError:
    message: str
    code: int
    status: Literal["error"] = "error"


type ApiResponse[T] = ApiSuccess[T] | ApiError


def is_success(response: ApiResponse[Any]) -> TypeGuard[ApiSuccess[Any]]:
    """Narrow response type to ApiSuccess."""
    return isinstance(response, ApiSuccess)


def handle_response(response: ApiResponse[dict[str, Any]]) -> None:
    if is_success(response):
        # Type checker knows: response is ApiSuccess[dict[str, Any]]
        print(response.data["key"])
    else:
        # Type checker knows: response is ApiError
        print(f"Error {response.code}: {response.message}")


# ============================================================
# 5. Self type for fluent builders
# ============================================================

class QueryBuilder:
    def __init__(self) -> None:
        self._table: str = ""
        self._conditions: list[str] = []
        self._limit: int | None = None

    def table(self, name: str) -> Self:
        self._table = name
        return self

    def where(self, condition: str) -> Self:
        self._conditions.append(condition)
        return self

    def limit(self, n: int) -> Self:
        self._limit = n
        return self

    def build(self) -> str:
        sql = f"SELECT * FROM {self._table}"
        if self._conditions:
            sql += " WHERE " + " AND ".join(self._conditions)
        if self._limit:
            sql += f" LIMIT {self._limit}"
        return sql


class PaginatedQueryBuilder(QueryBuilder):
    def __init__(self) -> None:
        super().__init__()
        self._page: int = 1

    def page(self, n: int) -> Self:
        # Self ensures this returns PaginatedQueryBuilder, not QueryBuilder
        self._page = n
        return self


# Chaining preserves subclass type
query = (
    PaginatedQueryBuilder()
    .table("users")           # returns PaginatedQueryBuilder (Self)
    .where("active = true")   # returns PaginatedQueryBuilder (Self)
    .page(3)                  # returns PaginatedQueryBuilder (Self)
    .limit(25)                # returns PaginatedQueryBuilder (Self)
    .build()
)
```

**Key patterns summary:**

| Feature | Python Version | Use Case |
|---------|---------------|----------|
| `ParamSpec` | 3.10+ | Signature-preserving decorators |
| `TypeVarTuple` | 3.11+ | Variadic generics, tuple typing |
| `Protocol` | 3.8+ | Structural subtyping / duck typing |
| `@runtime_checkable` | 3.8+ | `isinstance()` checks with protocols |
| `TypeGuard` | 3.10+ | Custom type narrowing functions |
| `Self` | 3.11+ | Fluent method chaining in hierarchies |
| `type X = Y` syntax | 3.12+ | Type alias statements |

**Best practices:**
- Prefer `Protocol` over ABC for extensible plugin systems
- Always use `ParamSpec` in decorators to preserve IDE autocomplete and type checking
- Use `Self` instead of `TypeVar` bound to the class for fluent interfaces
- Combine `@overload` with `Literal` types for APIs with behavior that varies by argument
- Use `TypeGuard` to teach the type checker about custom validation logic'''
    ),
    (
        "type-systems/runtime-validation-pydantic-zod",
        "Build a comprehensive runtime validation system using Pydantic v2 in Python and Zod in TypeScript, including custom validators, discriminated unions, recursive types, and error formatting.",
        '''Runtime validation with Pydantic v2 (Python) and Zod (TypeScript):

```python
"""Pydantic v2 runtime validation patterns for production APIs."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from decimal import Decimal
from enum import StrEnum
from ipaddress import IPv4Address
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    HttpUrl,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic.functional_validators import AfterValidator, BeforeValidator


# ============================================================
# 1. Custom annotated types with validators
# ============================================================

def _normalize_phone(v: str) -> str:
    """Strip non-digits, validate length."""
    digits = re.sub(r"\D", "", v)
    if len(digits) == 10:
        digits = f"1{digits}"
    if len(digits) != 11:
        raise ValueError("Phone number must be 10 or 11 digits")
    return f"+{digits}"


def _check_not_disposable_email(v: str) -> str:
    """Block disposable email domains."""
    disposable = {"mailinator.com", "guerrillamail.com", "tempmail.com"}
    domain = v.rsplit("@", 1)[-1].lower()
    if domain in disposable:
        raise ValueError(f"Disposable email domain not allowed: {domain}")
    return v


PhoneNumber = Annotated[str, BeforeValidator(_normalize_phone)]
SafeEmail = Annotated[EmailStr, AfterValidator(_check_not_disposable_email)]
PositiveCents = Annotated[int, Field(gt=0, description="Amount in cents")]
Slug = Annotated[
    str,
    Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", min_length=1, max_length=128),
]


# ============================================================
# 2. Discriminated unions
# ============================================================

class PaymentMethod(StrEnum):
    CARD = "card"
    BANK = "bank_transfer"
    WALLET = "wallet"


class CardPayment(BaseModel):
    method: Literal[PaymentMethod.CARD] = PaymentMethod.CARD
    card_number: str = Field(pattern=r"^\d{16}$")
    expiry_month: int = Field(ge=1, le=12)
    expiry_year: int = Field(ge=2025)
    cvv: str = Field(pattern=r"^\d{3,4}$")


class BankTransfer(BaseModel):
    method: Literal[PaymentMethod.BANK] = PaymentMethod.BANK
    routing_number: str = Field(pattern=r"^\d{9}$")
    account_number: str = Field(min_length=8, max_length=17)
    account_type: Literal["checking", "savings"]


class WalletPayment(BaseModel):
    method: Literal[PaymentMethod.WALLET] = PaymentMethod.WALLET
    wallet_id: str
    provider: Literal["apple_pay", "google_pay", "paypal"]


# Pydantic v2 discriminated union — fast validation via method field
Payment = Annotated[
    CardPayment | BankTransfer | WalletPayment,
    Field(discriminator="method"),
]


# ============================================================
# 3. Recursive types and model validators
# ============================================================

class Comment(BaseModel):
    """Self-referential / recursive model."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        str_min_length=1,
    )

    id: UUID
    author: SafeEmail
    body: str = Field(max_length=10_000)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    replies: list[Comment] = Field(default_factory=list, max_length=100)
    depth: int = Field(default=0, ge=0, le=10)

    @model_validator(mode="after")
    def validate_reply_depth(self) -> Self:
        """Ensure nested replies increment depth and respect max."""
        for reply in self.replies:
            if reply.depth != self.depth + 1:
                raise ValueError(
                    f"Reply depth must be {self.depth + 1}, got {reply.depth}"
                )
        return self


# ============================================================
# 4. Complex order model with cross-field validation
# ============================================================

class OrderItem(BaseModel):
    sku: str = Field(pattern=r"^[A-Z]{2,4}-\d{4,8}$")
    quantity: int = Field(gt=0, le=9999)
    unit_price_cents: PositiveCents
    discount_pct: Decimal = Field(default=Decimal("0"), ge=0, le=100)

    @property
    def total_cents(self) -> int:
        discount_mult = 1 - float(self.discount_pct) / 100
        return int(self.unit_price_cents * self.quantity * discount_mult)


class CreateOrderRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{
                "customer_email": "alice@example.com",
                "items": [{"sku": "WDG-1234", "quantity": 2, "unit_price_cents": 1999}],
                "payment": {"method": "card", "card_number": "4111111111111111",
                            "expiry_month": 12, "expiry_year": 2026, "cvv": "123"},
                "shipping_address": {"line1": "123 Main St", "city": "Springfield",
                                     "state": "IL", "zip_code": "62701", "country": "US"},
            }],
        },
    )

    customer_email: SafeEmail
    items: list[OrderItem] = Field(min_length=1, max_length=50)
    payment: Payment
    shipping_address: Address
    notes: str | None = Field(default=None, max_length=500)
    idempotency_key: UUID

    @model_validator(mode="after")
    def validate_order_total(self) -> Self:
        total = sum(item.total_cents for item in self.items)
        if total > 1_000_000_00:  # $1M limit
            raise ValueError(
                f"Order total ${total / 100:.2f} exceeds $1,000,000 limit"
            )
        if total == 0:
            raise ValueError("Order total cannot be zero")
        return self


class Address(BaseModel):
    line1: str = Field(min_length=1, max_length=200)
    line2: str | None = Field(default=None, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")
    zip_code: str = Field(pattern=r"^\d{5}(-\d{4})?$")
    country: str = Field(default="US", pattern=r"^[A-Z]{2}$")


# ============================================================
# 5. Structured error formatting
# ============================================================

def format_validation_errors(exc: ValidationError) -> dict[str, Any]:
    """Convert Pydantic errors to API-friendly format."""
    errors: list[dict[str, Any]] = []
    for error in exc.errors():
        field_path = ".".join(str(loc) for loc in error["loc"])
        errors.append({
            "field": field_path,
            "message": error["msg"],
            "type": error["type"],
            "input": error.get("input"),
        })
    return {
        "status": "validation_error",
        "error_count": len(errors),
        "errors": errors,
    }


# Usage
try:
    order = CreateOrderRequest.model_validate_json(raw_json)
except ValidationError as exc:
    error_response = format_validation_errors(exc)
    # Returns structured JSON like:
    # {
    #   "status": "validation_error",
    #   "error_count": 2,
    #   "errors": [
    #     {"field": "items.0.sku", "message": "String should match pattern...", ...},
    #     {"field": "payment.card_number", "message": "String should match...", ...}
    #   ]
    # }
```

```typescript
// ============================================================
// Zod equivalent — TypeScript runtime validation
// ============================================================

import { z } from "zod";

// Custom reusable types
const PhoneNumber = z
  .string()
  .transform((v) => v.replace(/\D/g, ""))
  .pipe(
    z.string().regex(/^1?\d{10}$/, "Must be 10 or 11 digits")
  )
  .transform((v) => (v.length === 10 ? `+1${v}` : `+${v}`));

const Slug = z
  .string()
  .min(1)
  .max(128)
  .regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/);

const PositiveCents = z.number().int().positive();

// Discriminated union
const CardPayment = z.object({
  method: z.literal("card"),
  cardNumber: z.string().regex(/^\d{16}$/),
  expiryMonth: z.number().int().min(1).max(12),
  expiryYear: z.number().int().min(2025),
  cvv: z.string().regex(/^\d{3,4}$/),
});

const BankTransfer = z.object({
  method: z.literal("bank_transfer"),
  routingNumber: z.string().regex(/^\d{9}$/),
  accountNumber: z.string().min(8).max(17),
  accountType: z.enum(["checking", "savings"]),
});

const WalletPayment = z.object({
  method: z.literal("wallet"),
  walletId: z.string().min(1),
  provider: z.enum(["apple_pay", "google_pay", "paypal"]),
});

const Payment = z.discriminatedUnion("method", [
  CardPayment,
  BankTransfer,
  WalletPayment,
]);

// Recursive type (comments with replies)
type Comment = z.infer<typeof BaseComment> & {
  replies: Comment[];
};

const BaseComment = z.object({
  id: z.string().uuid(),
  author: z.string().email(),
  body: z.string().min(1).max(10_000),
  createdAt: z.coerce.date().default(() => new Date()),
  depth: z.number().int().min(0).max(10).default(0),
});

const CommentSchema: z.ZodType<Comment> = BaseComment.extend({
  replies: z.lazy(() => CommentSchema.array().max(100)).default([]),
}).refine(
  (comment) =>
    comment.replies.every((reply) => reply.depth === comment.depth + 1),
  { message: "Reply depth must increment by 1" }
);

// Infer TypeScript types from Zod schemas (single source of truth)
type PaymentInput = z.input<typeof Payment>;   // before transforms
type PaymentOutput = z.output<typeof Payment>;  // after transforms
type CommentType = z.infer<typeof CommentSchema>;

// Structured error formatting
function formatZodErrors(error: z.ZodError): object {
  return {
    status: "validation_error",
    errorCount: error.issues.length,
    errors: error.issues.map((issue) => ({
      field: issue.path.join("."),
      message: issue.message,
      code: issue.code,
    })),
  };
}
```

**Comparison: Pydantic v2 vs Zod:**

| Feature | Pydantic v2 | Zod |
|---------|------------|-----|
| Discriminated unions | `Field(discriminator=...)` | `z.discriminatedUnion()` |
| Recursive types | Self-referencing model | `z.lazy()` |
| Transform on parse | `BeforeValidator` / `AfterValidator` | `.transform()` / `.pipe()` |
| Type inference | Types defined first, validation follows | Types inferred from schema |
| Cross-field validation | `@model_validator(mode="after")` | `.refine()` / `.superRefine()` |
| Error formatting | `exc.errors()` list of dicts | `error.issues` array |
| Performance | Rust core (pydantic-core) | Pure JS |

**Best practices:**
- Define validation at the boundary (API input), use plain types internally
- Use discriminated unions for polymorphic payloads (10-50x faster than plain unions)
- Keep `@model_validator` logic simple; push complex validation to service layer
- Always `model_config = ConfigDict(extra="forbid")` to reject unknown fields in APIs
- Use `Annotated[T, ...]` reusable types to build a domain validation vocabulary'''
    ),
]
"""
