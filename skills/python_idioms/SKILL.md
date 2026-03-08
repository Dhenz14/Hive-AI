# Python Idioms & Best Practices

## Dataclasses vs attrs
```python
from dataclasses import dataclass, field
from attrs import define, Factory

@dataclass(frozen=True, slots=True)  # Immutable + memory efficient
class Point:
    x: float
    y: float

@define  # attrs: validators, converters, less boilerplate
class User:
    name: str
    tags: list[str] = Factory(list)  # Safe mutable default
```

## Type Hints
```python
from typing import Protocol, TypeVar, Generic, TypeGuard

T = TypeVar("T", bound="Comparable")

class Comparable(Protocol):
    def __lt__(self, other: Self) -> bool: ...

def top_k(items: list[T], k: int) -> list[T]: ...

# 3.10+ union syntax: str | None instead of Optional[str]
def find(name: str) -> User | None: ...

def is_str_list(val: list[object]) -> TypeGuard[list[str]]:
    return all(isinstance(x, str) for x in val)
```

## Asyncio Patterns
```python
import asyncio

# TaskGroup (3.11+) — structured concurrency
async def fetch_all(urls: list[str]):
    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(fetch(u)) for u in urls]
    return [t.result() for t in tasks]  # All done or all cancelled

# Rate limiting with semaphore
sem = asyncio.Semaphore(10)
async def limited_fetch(url):
    async with sem:
        return await fetch(url)

# Async generator
async def stream_lines(path):
    async with aiofiles.open(path) as f:
        async for line in f:
            yield line.strip()
```

## Context Managers
```python
from contextlib import contextmanager, asynccontextmanager

@contextmanager
def temp_env(**vars):
    old = {k: os.environ.get(k) for k in vars}
    os.environ.update(vars)
    try:
        yield
    finally:
        for k, v in old.items():
            if v is None: os.environ.pop(k, None)
            else: os.environ[k] = v

@asynccontextmanager
async def db_transaction(pool):
    conn = await pool.acquire()
    try:
        yield conn
        await conn.commit()
    except:
        await conn.rollback()
        raise
    finally:
        await pool.release(conn)
```

## Common Pitfalls
```python
# BAD: mutable default — shared across calls
def add(item, lst=[]):  # Use lst=None, then lst = lst or []

# BAD: late binding closure
fns = [lambda: i for i in range(3)]  # All return 2!
fns = [lambda i=i: i for i in range(3)]  # Fix: default arg capture

# is vs ==: `is` checks identity, `==` checks value
# Only use `is` for None, True, False, sentinel objects
```

## Modern Syntax
```python
# Walrus operator (3.8+)
if (n := len(data)) > 100:
    print(f"Processing {n} items")

# Structural pattern matching (3.10+)
match command.split():
    case ["go", direction]:
        move(direction)
    case ["get", item] if item in inventory:
        take(item)

# f-string tricks
f"{value = }"          # "value = 42" (debug format)
f"{num:>10,.2f}"       # Right-aligned, comma-separated, 2 decimals
```

## itertools / functools
```python
from itertools import chain, groupby, islice, batched  # 3.12+
from functools import lru_cache, partial, reduce

# Chain iterables flat
all_items = list(chain.from_iterable(nested_lists))

# Group sorted data
for key, group in groupby(sorted(users, key=lambda u: u.role), key=lambda u: u.role):
    print(key, list(group))

# LRU cache (use maxsize=None for unbounded)
@lru_cache(maxsize=128)
def fib(n: int) -> int:
    return n if n < 2 else fib(n-1) + fib(n-2)

# Partial application
int_from_hex = partial(int, base=16)
```
