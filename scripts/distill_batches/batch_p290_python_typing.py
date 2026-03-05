"""Python advanced typing — generics, protocols, TypeVar, overloads."""

PAIRS = [
    (
        "python/advanced-typing",
        "Show advanced Python typing: generics, Protocol classes, TypeVar bounds, overloaded functions, and ParamSpec.",
        '''Advanced Python type annotations:

```python
from typing import (TypeVar, Generic, Protocol, overload, ParamSpec, Callable,
                     Concatenate, TypeGuard, Never, Self, runtime_checkable)
from dataclasses import dataclass


# --- Generics with bounds ---
T = TypeVar("T")
Numeric = TypeVar("Numeric", int, float)  # Constrained TypeVar

class SortedList(Generic[T]):
    """Generic sorted collection."""
    def __init__(self) -> None:
        self._items: list[T] = []

    def add(self, item: T) -> None:
        # bisect insertion for O(log n)
        lo, hi = 0, len(self._items)
        while lo < hi:
            mid = (lo + hi) // 2
            if self._items[mid] < item:
                lo = mid + 1
            else:
                hi = mid
        self._items.insert(lo, item)

    def __getitem__(self, index: int) -> T:
        return self._items[index]

    def __len__(self) -> int:
        return len(self._items)


def clamp(value: Numeric, low: Numeric, high: Numeric) -> Numeric:
    """Works with int or float, return type matches input."""
    return max(low, min(value, high))


# --- Protocols (structural subtyping) ---
@runtime_checkable
class Renderable(Protocol):
    def render(self) -> str: ...

class HasSize(Protocol):
    @property
    def size(self) -> int: ...

class Widget:
    """Satisfies Renderable without explicitly inheriting."""
    def render(self) -> str:
        return "<div>widget</div>"

def display(item: Renderable) -> None:
    print(item.render())

# Widget works because it has render() -> str
display(Widget())  # OK - structural match


# --- Overloaded functions ---
@overload
def parse(data: str) -> dict: ...
@overload
def parse(data: bytes) -> dict: ...
@overload
def parse(data: str, as_list: bool) -> list: ...

def parse(data, as_list=False):
    import json
    text = data.decode() if isinstance(data, bytes) else data
    result = json.loads(text)
    return list(result.values()) if as_list else result


# --- ParamSpec for decorator typing ---
P = ParamSpec("P")
R = TypeVar("R")

def retry(times: int = 3) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Typed decorator that preserves function signature."""
    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            for attempt in range(times):
                try:
                    return fn(*args, **kwargs)
                except Exception:
                    if attempt == times - 1:
                        raise
            raise RuntimeError("unreachable")
        return wrapper
    return decorator

@retry(times=3)
def fetch_data(url: str, timeout: int = 30) -> dict:
    ...  # IDE knows: fetch_data(url: str, timeout: int = 30) -> dict


# --- TypeGuard for type narrowing ---
def is_string_list(val: list[object]) -> TypeGuard[list[str]]:
    return all(isinstance(x, str) for x in val)

def process(items: list[object]) -> None:
    if is_string_list(items):
        # Type checker knows items: list[str] here
        print(", ".join(items))


# --- Self type for fluent APIs ---
class QueryBuilder:
    def where(self, condition: str) -> Self:
        return self

    def order_by(self, field: str) -> Self:
        return self

    def limit(self, n: int) -> Self:
        return self
```

Key patterns:
1. **Constrained TypeVar** — `TypeVar("N", int, float)` restricts to specific types
2. **Protocol** — structural subtyping; no inheritance needed, just implement the methods
3. **@overload** — different return types based on input types; IDE sees all signatures
4. **ParamSpec** — preserve decorated function's parameter types in wrapper
5. **TypeGuard** — custom type narrowing for isinstance-like checks on complex types'''
    ),
    (
        "python/context-managers",
        "Show advanced Python context managers: async context managers, contextlib patterns, and resource management.",
        '''Advanced context managers:

```python
import asyncio
from contextlib import contextmanager, asynccontextmanager, ExitStack
from typing import AsyncIterator, Iterator
from dataclasses import dataclass


# Generator-based context manager
@contextmanager
def timer(label: str) -> Iterator[dict]:
    """Time a code block."""
    import time
    result = {"label": label, "elapsed": 0.0}
    start = time.perf_counter()
    try:
        yield result
    finally:
        result["elapsed"] = time.perf_counter() - start
        print(f"{label}: {result['elapsed']:.3f}s")


# Async context manager
@asynccontextmanager
async def managed_connection(dsn: str) -> AsyncIterator:
    """Async DB connection with auto-cleanup."""
    import asyncpg
    conn = await asyncpg.connect(dsn)
    try:
        yield conn
    except Exception:
        if conn.is_in_transaction():
            await conn.execute("ROLLBACK")
        raise
    finally:
        await conn.close()


# ExitStack for dynamic resource management
class ResourcePool:
    """Manage variable number of resources."""

    def __init__(self, resources: list[str]):
        self.resource_specs = resources
        self._stack = None

    def __enter__(self):
        self._stack = ExitStack()
        self._stack.__enter__()
        self.handles = []
        for spec in self.resource_specs:
            handle = self._stack.enter_context(open(spec))
            self.handles.append(handle)
        return self

    def __exit__(self, *exc):
        return self._stack.__exit__(*exc)


# Reentrant context manager
class TransactionManager:
    """Supports nested transactions (savepoints)."""

    def __init__(self, conn):
        self.conn = conn
        self.depth = 0

    async def __aenter__(self):
        if self.depth == 0:
            await self.conn.execute("BEGIN")
        else:
            await self.conn.execute(f"SAVEPOINT sp_{self.depth}")
        self.depth += 1
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        self.depth -= 1
        if exc_type:
            if self.depth == 0:
                await self.conn.execute("ROLLBACK")
            else:
                await self.conn.execute(f"ROLLBACK TO sp_{self.depth}")
        else:
            if self.depth == 0:
                await self.conn.execute("COMMIT")
            else:
                await self.conn.execute(f"RELEASE sp_{self.depth}")
        return False  # Don't suppress exceptions
```

Key patterns:
1. **Generator context manager** — yield in try/finally; cleanup always runs
2. **Async context manager** — `async with` for async resources (connections, sessions)
3. **ExitStack** — manage dynamic/variable number of context managers
4. **Nested transactions** — savepoints for reentrant transaction context managers
5. **Result passing** — yield a dict/object to communicate state back to caller'''
    ),
]
"""
