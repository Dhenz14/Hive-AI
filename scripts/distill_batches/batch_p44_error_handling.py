"""Error handling — exception patterns, custom errors, retry logic, and graceful degradation."""

PAIRS = [
    (
        "python/error-handling-patterns",
        "Show Python error handling patterns: custom exceptions, error hierarchies, Result type, and graceful degradation.",
        '''Production error handling patterns:

```python
from dataclasses import dataclass
from typing import TypeVar, Generic, Union, Callable
from enum import Enum
import traceback
import logging

logger = logging.getLogger(__name__)
T = TypeVar("T")
E = TypeVar("E")

# --- Custom exception hierarchy ---

class AppError(Exception):
    """Base application error."""
    def __init__(self, message: str, code: str = "INTERNAL_ERROR",
                 status_code: int = 500, details: dict = None):
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.details = details or {}

class NotFoundError(AppError):
    def __init__(self, resource: str, identifier: str):
        super().__init__(
            f"{resource} not found: {identifier}",
            code="NOT_FOUND", status_code=404,
            details={"resource": resource, "id": identifier},
        )

class ValidationError(AppError):
    def __init__(self, errors: list[dict]):
        super().__init__(
            "Validation failed",
            code="VALIDATION_ERROR", status_code=422,
            details={"errors": errors},
        )

class ConflictError(AppError):
    def __init__(self, message: str):
        super().__init__(message, code="CONFLICT", status_code=409)

class RateLimitError(AppError):
    def __init__(self, retry_after: int = 60):
        super().__init__(
            "Rate limit exceeded",
            code="RATE_LIMITED", status_code=429,
            details={"retry_after": retry_after},
        )

class ExternalServiceError(AppError):
    def __init__(self, service: str, original: Exception = None):
        super().__init__(
            f"External service failure: {service}",
            code="SERVICE_UNAVAILABLE", status_code=502,
            details={"service": service, "error": str(original) if original else None},
        )


# --- Result type (functional error handling) ---

@dataclass
class Ok(Generic[T]):
    value: T
    def is_ok(self) -> bool: return True
    def is_err(self) -> bool: return False
    def unwrap(self) -> T: return self.value
    def map(self, fn: Callable) -> "Result": return Ok(fn(self.value))

@dataclass
class Err(Generic[E]):
    error: E
    def is_ok(self) -> bool: return False
    def is_err(self) -> bool: return True
    def unwrap(self) -> None: raise self.error if isinstance(self.error, Exception) else ValueError(self.error)
    def map(self, fn: Callable) -> "Result": return self

Result = Union[Ok[T], Err[E]]

def safe_divide(a: float, b: float) -> Result[float, str]:
    if b == 0:
        return Err("Division by zero")
    return Ok(a / b)

def safe_parse_int(s: str) -> Result[int, str]:
    try:
        return Ok(int(s))
    except ValueError:
        return Err(f"Cannot parse '{s}' as integer")


# --- Graceful degradation ---

async def get_user_with_fallbacks(user_id: str) -> dict:
    """Try multiple sources, degrade gracefully."""
    # Try cache first
    try:
        cached = await cache.get(f"user:{user_id}")
        if cached:
            return cached
    except Exception as e:
        logger.warning("Cache unavailable: %s", e)

    # Try primary database
    try:
        user = await db.get_user(user_id)
        if user:
            try:
                await cache.set(f"user:{user_id}", user, ttl=300)
            except Exception:
                pass  # Cache write failure is non-critical
            return user
    except Exception as e:
        logger.error("Database error: %s", e)

    # Try read replica
    try:
        user = await db_replica.get_user(user_id)
        if user:
            return user
    except Exception as e:
        logger.error("Replica error: %s", e)

    raise NotFoundError("User", user_id)


# --- Error boundary (catch and report) ---

class ErrorBoundary:
    """Catch errors, report them, return fallback."""

    def __init__(self, fallback=None, report_fn=None):
        self.fallback = fallback
        self.report_fn = report_fn or logger.exception

    async def execute(self, fn, *args, **kwargs):
        try:
            return await fn(*args, **kwargs)
        except AppError:
            raise  # Known errors propagate
        except Exception as e:
            self.report_fn(f"Unexpected error in {fn.__name__}: {e}")
            if self.fallback is not None:
                return self.fallback
            raise ExternalServiceError(fn.__name__, e)

# Usage:
boundary = ErrorBoundary(fallback=[])
recommendations = await boundary.execute(get_recommendations, user_id)
# Returns [] on failure instead of crashing
```

Error handling principles:
1. **Custom hierarchy** — domain-specific errors with codes and status
2. **Result type** — explicit success/failure without exceptions (for expected failures)
3. **Graceful degradation** — fallback to less optimal data sources
4. **Error boundary** — catch unexpected errors, report and continue
5. **Log and rethrow** — never swallow errors silently, always log'''
    ),
    (
        "python/decorator-patterns",
        "Show Python decorator patterns: timing, caching, rate limiting, authentication, and decorator factories.",
        '''Python decorator patterns for cross-cutting concerns:

```python
import time
import asyncio
import logging
from functools import wraps
from typing import Callable, TypeVar, ParamSpec, Any
from datetime import datetime, timezone

P = ParamSpec("P")
R = TypeVar("R")
logger = logging.getLogger(__name__)

# --- Timer decorator ---

def timed(func: Callable[P, R]) -> Callable[P, R]:
    @wraps(func)
    async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()
        result = await func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logger.info("%s took %.3fs", func.__name__, elapsed)
        return result

    @wraps(func)
    def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        logger.info("%s took %.3fs", func.__name__, elapsed)
        return result

    return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper


# --- Retry decorator with backoff ---

def retry(
    max_attempts: int = 3,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple = (Exception,),
):
    """Retry on failure with exponential backoff."""
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            last_exc = None
            current_delay = delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_attempts:
                        logger.warning(
                            "%s attempt %d/%d failed: %s, retrying in %.1fs",
                            func.__name__, attempt, max_attempts, e, current_delay,
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
            raise last_exc

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            last_exc = None
            current_delay = delay
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_attempts:
                        time.sleep(current_delay)
                        current_delay *= backoff
            raise last_exc

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator

@retry(max_attempts=3, delay=1.0, exceptions=(ConnectionError, TimeoutError))
async def fetch_external_data(url: str) -> dict:
    ...


# --- Validate decorator ---

def validate_args(**validators: Callable):
    """Validate function arguments with custom validators."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            import inspect
            sig = inspect.signature(func)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()

            for param_name, validator_fn in validators.items():
                if param_name in bound.arguments:
                    value = bound.arguments[param_name]
                    if not validator_fn(value):
                        raise ValueError(
                            f"Invalid {param_name}: {value}"
                        )
            return func(*args, **kwargs)
        return wrapper
    return decorator

@validate_args(
    age=lambda x: 0 < x < 150,
    email=lambda x: "@" in x,
)
def create_user(name: str, age: int, email: str):
    ...


# --- Deprecation decorator ---

import warnings

def deprecated(reason: str = "", version: str = ""):
    """Mark function as deprecated."""
    def decorator(func):
        msg = f"{func.__name__} is deprecated"
        if version:
            msg += f" since v{version}"
        if reason:
            msg += f": {reason}"

        @wraps(func)
        def wrapper(*args, **kwargs):
            warnings.warn(msg, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)
        return wrapper
    return decorator

@deprecated(reason="Use get_user_v2 instead", version="2.0")
def get_user(user_id: str):
    ...


# --- Singleton decorator ---

def singleton(cls):
    """Make a class a singleton."""
    instances = {}

    @wraps(cls)
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]
    return get_instance

@singleton
class DatabasePool:
    def __init__(self, url: str):
        self.url = url


# --- Class-based decorator (with state) ---

class RateLimit:
    """Rate limiting decorator that tracks calls."""

    def __init__(self, calls: int = 10, period: float = 60.0):
        self.calls = calls
        self.period = period
        self.timestamps: list[float] = []

    def __call__(self, func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            now = time.time()
            self.timestamps = [
                t for t in self.timestamps if now - t < self.period
            ]
            if len(self.timestamps) >= self.calls:
                raise RateLimitError(
                    retry_after=int(self.period - (now - self.timestamps[0]))
                )
            self.timestamps.append(now)
            return func(*args, **kwargs)
        return wrapper

@RateLimit(calls=5, period=60)
def send_email(to: str, subject: str):
    ...
```

Decorator types:
1. **Simple decorator** — no arguments, wraps function directly
2. **Decorator factory** — takes arguments, returns decorator
3. **Class decorator** — maintains state across calls
4. **Async-aware** — handles both sync and async functions
5. **Always use `@wraps`** — preserves `__name__`, `__doc__`, `__module__`'''
    ),
    (
        "python/type-hints-advanced",
        "Show advanced Python type hints: generics, Protocol, TypeVar, overload, ParamSpec, and runtime type checking.",
        '''Advanced Python type hints for safer code:

```python
from typing import (
    TypeVar, Generic, Protocol, runtime_checkable,
    overload, Literal, TypeAlias, TypeGuard, Self,
    ParamSpec, Concatenate, Never, assert_never,
)
from dataclasses import dataclass
from collections.abc import Callable, Sequence, Mapping

T = TypeVar("T")
P = ParamSpec("P")

# --- Generic classes ---

@dataclass
class Result(Generic[T]):
    value: T | None
    error: str | None

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        return cls(value=value, error=None)

    @classmethod
    def fail(cls, error: str) -> "Result[T]":
        return cls(value=None, error=error)

    def unwrap(self) -> T:
        if self.error:
            raise ValueError(self.error)
        return self.value  # type: ignore

result: Result[int] = Result.ok(42)
result: Result[str] = Result.fail("not found")


# --- Protocol (structural subtyping) ---

@runtime_checkable
class Renderable(Protocol):
    def render(self) -> str: ...

class HTMLWidget:
    def render(self) -> str:
        return "<div>widget</div>"

class JSONResponse:
    def render(self) -> str:
        return '{"key": "value"}'

def display(item: Renderable) -> str:
    return item.render()

# Both work without inheriting from Renderable
display(HTMLWidget())
display(JSONResponse())
isinstance(HTMLWidget(), Renderable)  # True at runtime


# --- Callable with ParamSpec ---

def add_logging(func: Callable[P, T]) -> Callable[P, T]:
    """Preserve exact function signature in type system."""
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        print(f"Calling {func.__name__}")
        return func(*args, **kwargs)
    return wrapper

@add_logging
def greet(name: str, greeting: str = "Hello") -> str:
    return f"{greeting}, {name}!"

# Type checker knows: greet(name=str, greeting=str) -> str


# --- overload (different return types) ---

@overload
def process(data: str) -> list[str]: ...
@overload
def process(data: list[str]) -> str: ...
@overload
def process(data: int) -> float: ...

def process(data):
    if isinstance(data, str):
        return data.split()
    elif isinstance(data, list):
        return " ".join(data)
    elif isinstance(data, int):
        return float(data)

result1: list[str] = process("hello world")  # Type checker knows
result2: str = process(["hello", "world"])     # Type checker knows


# --- TypeGuard (narrow types in conditions) ---

def is_string_list(val: list[object]) -> TypeGuard[list[str]]:
    return all(isinstance(x, str) for x in val)

def process_items(items: list[object]):
    if is_string_list(items):
        # Type checker knows items is list[str] here
        for item in items:
            print(item.upper())


# --- Literal types ---

Mode = Literal["read", "write", "append"]

def open_file(path: str, mode: Mode) -> None:
    ...

open_file("test.txt", "read")    # OK
# open_file("test.txt", "delete") # Type error!


# --- TypeAlias ---

JSON: TypeAlias = dict[str, "JSON"] | list["JSON"] | str | int | float | bool | None
Headers: TypeAlias = Mapping[str, str | list[str]]
Handler: TypeAlias = Callable[[dict], dict]


# --- Exhaustive matching with Never ---

from enum import Enum

class Color(Enum):
    RED = "red"
    GREEN = "green"
    BLUE = "blue"

def color_to_hex(color: Color) -> str:
    match color:
        case Color.RED:
            return "#ff0000"
        case Color.GREEN:
            return "#00ff00"
        case Color.BLUE:
            return "#0000ff"
        case _ as unreachable:
            assert_never(unreachable)
            # If someone adds YELLOW without updating this function,
            # the type checker will catch it


# --- Self type (Python 3.11+) ---

class Builder:
    def __init__(self):
        self.items: list[str] = []

    def add(self, item: str) -> Self:
        self.items.append(item)
        return self

    def build(self) -> list[str]:
        return self.items.copy()

# Works with subclasses too
class SpecialBuilder(Builder):
    def add_special(self, item: str) -> Self:
        self.items.append(f"*{item}*")
        return self
```

Type hint guide:
1. **`Protocol`** — structural typing (duck typing with safety)
2. **`Generic[T]`** — parameterized classes and functions
3. **`ParamSpec`** — preserve function signatures in decorators
4. **`overload`** — different return types based on input types
5. **`TypeGuard`** — narrow types in conditional branches
6. **`Literal`** — restrict to specific string/int values
7. **`Self`** — return type for method chaining'''
    ),
]
