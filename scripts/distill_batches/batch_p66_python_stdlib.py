"""Python — stdlib deep dive: typing, functools, itertools, and contextlib."""

PAIRS = [
    (
        "python/typing-advanced",
        "Show advanced Python typing patterns: generics, protocols, type guards, overloads, and ParamSpec.",
        '''Advanced Python typing patterns:

```python
from typing import (
    Generic, TypeVar, Protocol, runtime_checkable,
    TypeGuard, TypeAlias, Self, overload,
    ParamSpec, Concatenate, Callable, Any,
    TypedDict, Required, NotRequired, Unpack,
    Final, ClassVar, Literal, LiteralString,
    Never, assert_never,
)
from dataclasses import dataclass
from collections.abc import Sequence, Iterator, AsyncIterator
import functools


# --- Generics with bounds ---

T = TypeVar("T")
T_co = TypeVar("T_co", covariant=True)
Numeric = TypeVar("Numeric", int, float)  # Constrained

@dataclass
class Result(Generic[T]):
    """Type-safe result wrapper."""
    _value: T | None = None
    _error: str | None = None

    @classmethod
    def ok(cls, value: T) -> "Result[T]":
        return cls(_value=value)

    @classmethod
    def err(cls, error: str) -> "Result[T]":
        return cls(_error=error)

    def unwrap(self) -> T:
        if self._error:
            raise ValueError(self._error)
        return self._value  # type: ignore

    def map(self, fn: Callable[[T], T]) -> "Result[T]":
        if self._error:
            return Result.err(self._error)
        return Result.ok(fn(self._value))  # type: ignore

# result: Result[int] = Result.ok(42)
# result.map(lambda x: x * 2).unwrap()  # 84


# --- Protocols (structural subtyping) ---

@runtime_checkable
class Renderable(Protocol):
    def render(self) -> str: ...

class HasLength(Protocol):
    def __len__(self) -> int: ...

class Comparable(Protocol):
    def __lt__(self, other: Self) -> bool: ...
    def __eq__(self, other: object) -> bool: ...

def render_all(items: Sequence[Renderable]) -> list[str]:
    return [item.render() for item in items]

# Any class with a render() method works — no inheritance needed


# --- TypeGuard (narrows types in conditionals) ---

def is_string_list(val: list[Any]) -> TypeGuard[list[str]]:
    return all(isinstance(x, str) for x in val)

def process(items: list[int | str]):
    if is_string_list(items):
        # Type checker knows items is list[str] here
        print(", ".join(items))
    else:
        print(sum(items))  # list[int | str]


# --- Overloads (different return types based on input) ---

@overload
def parse(data: str, as_list: Literal[True]) -> list[str]: ...
@overload
def parse(data: str, as_list: Literal[False] = ...) -> str: ...

def parse(data: str, as_list: bool = False) -> str | list[str]:
    if as_list:
        return data.split(",")
    return data.strip()

# x = parse("a,b,c", as_list=True)   # type: list[str]
# y = parse("hello")                   # type: str


# --- ParamSpec (preserve function signatures) ---

P = ParamSpec("P")
R = TypeVar("R")

def with_logging(fn: Callable[P, R]) -> Callable[P, R]:
    """Decorator that preserves the wrapped function's signature."""
    @functools.wraps(fn)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        print(f"Calling {fn.__name__}")
        result = fn(*args, **kwargs)
        print(f"Result: {result}")
        return result
    return wrapper

@with_logging
def add(x: int, y: int) -> int:
    return x + y

# add(1, 2)       # ✓ Type checker knows signature is (int, int) -> int
# add("a", "b")   # ✗ Type error


# --- TypedDict (structured dicts) ---

class UserDict(TypedDict):
    name: str
    email: str
    age: Required[int]
    bio: NotRequired[str]

def create_user(data: UserDict) -> None:
    print(data["name"])  # Type checker knows this is str
    bio = data.get("bio", "")  # Optional field


# --- Exhaustiveness checking ---

class Shape(Protocol):
    kind: str

def area(shape: Literal["circle", "square", "triangle"]) -> float:
    match shape:
        case "circle":
            return 3.14
        case "square":
            return 1.0
        case "triangle":
            return 0.5
        case _ as unreachable:
            assert_never(unreachable)  # Type error if case missing


# --- Type aliases ---

JSON: TypeAlias = dict[str, "JSON"] | list["JSON"] | str | int | float | bool | None
UserId: TypeAlias = str
Handler: TypeAlias = Callable[[dict[str, Any]], dict[str, Any]]
```

Typing patterns:
1. **`Protocol`** — structural typing (duck typing with type safety)
2. **`TypeGuard`** — narrow types in conditional branches
3. **`@overload`** — different return types based on input parameter values
4. **`ParamSpec`** — preserve decorated function's parameter types
5. **`assert_never`** — exhaustiveness checking in match/if-else chains'''
    ),
    (
        "python/functools-patterns",
        "Show functools patterns: decorators, caching, partial, singledispatch, and total_ordering.",
        '''functools patterns:

```python
import functools
import time
import asyncio
from typing import Callable, TypeVar, ParamSpec, Any

P = ParamSpec("P")
R = TypeVar("R")


# --- LRU cache with TTL ---

def ttl_cache(maxsize: int = 128, ttl: float = 300):
    """LRU cache with time-to-live expiry."""
    def decorator(fn):
        cache = functools.lru_cache(maxsize=maxsize)(fn)
        cache._expiry = {}

        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            key = functools._make_key(args, kwargs, typed=False)
            now = time.time()

            if key in cache._expiry and now > cache._expiry[key]:
                # Expired — clear this entry
                cache.cache_clear()
                cache._expiry.clear()

            cache._expiry[key] = now + ttl
            return cache(*args, **kwargs)

        wrapper.cache_info = cache.cache_info
        wrapper.cache_clear = lambda: (cache.cache_clear(),
                                        cache._expiry.clear())
        return wrapper
    return decorator

@ttl_cache(maxsize=256, ttl=60)
def get_exchange_rate(currency: str) -> float:
    # Expensive API call, cached for 60 seconds
    return fetch_rate(currency)


# --- singledispatch (function overloading by type) ---

@functools.singledispatch
def serialize(obj) -> str:
    """Default serialization."""
    return str(obj)

@serialize.register
def _(obj: dict) -> str:
    import json
    return json.dumps(obj)

@serialize.register
def _(obj: list) -> str:
    return ", ".join(serialize(item) for item in obj)

@serialize.register(int)
@serialize.register(float)
def _(obj) -> str:
    return f"{obj:,.2f}"

from datetime import datetime

@serialize.register
def _(obj: datetime) -> str:
    return obj.isoformat()

# serialize({"a": 1})         # '{"a": 1}'
# serialize(42)                # '42.00'
# serialize([1, 2, 3])         # '1.00, 2.00, 3.00'
# serialize(datetime.now())    # '2024-01-15T10:30:00'


# --- partial for dependency injection ---

def send_notification(
    message: str,
    channel: str,
    api_key: str,
    timeout: float = 5.0,
):
    """Send notification via channel."""
    pass

# Create pre-configured senders
send_slack = functools.partial(
    send_notification, channel="slack", api_key="xoxb-..."
)
send_email = functools.partial(
    send_notification, channel="email", api_key="sg-..."
)

# send_slack("Hello!")  # Only need message now


# --- reduce for aggregation ---

from functools import reduce

# Pipeline composition
def compose(*functions: Callable) -> Callable:
    """Compose functions: compose(f, g, h)(x) = f(g(h(x)))."""
    return reduce(
        lambda f, g: lambda *a, **kw: f(g(*a, **kw)),
        functions,
    )

pipeline = compose(
    str.upper,
    str.strip,
    lambda s: s.replace("  ", " "),
)
# pipeline("  hello  world  ")  # "HELLO WORLD"


# --- total_ordering (complete comparison from __eq__ and __lt__) ---

@functools.total_ordering
class Version:
    def __init__(self, major: int, minor: int, patch: int):
        self.major = major
        self.minor = minor
        self.patch = patch

    def __eq__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return (self.major, self.minor, self.patch) == \
               (other.major, other.minor, other.patch)

    def __lt__(self, other):
        if not isinstance(other, Version):
            return NotImplemented
        return (self.major, self.minor, self.patch) < \
               (other.major, other.minor, other.patch)

    def __repr__(self):
        return f"v{self.major}.{self.minor}.{self.patch}"

# Version(1, 0, 0) < Version(2, 0, 0)  # True
# Version(1, 2, 3) >= Version(1, 2, 0)  # True (auto-generated)


# --- cached_property (one-time lazy computation) ---

class DataLoader:
    def __init__(self, path: str):
        self.path = path

    @functools.cached_property
    def data(self) -> list[dict]:
        """Loaded once on first access, then cached."""
        import json
        with open(self.path) as f:
            return json.load(f)

    @functools.cached_property
    def stats(self) -> dict:
        return {
            "count": len(self.data),
            "keys": list(self.data[0].keys()) if self.data else [],
        }


# --- wraps for proper decorator metadata ---

def retry(max_attempts: int = 3, delay: float = 1.0):
    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(fn)  # Preserves __name__, __doc__, __module__
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except Exception:
                    if attempt == max_attempts - 1:
                        raise
                    time.sleep(delay * (2 ** attempt))
            raise RuntimeError("Unreachable")
        return wrapper
    return decorator
```

functools patterns:
1. **`lru_cache`** — memoize pure functions, with TTL wrapper for time-sensitive data
2. **`singledispatch`** — function overloading by argument type (visitor pattern)
3. **`partial`** — pre-fill arguments for dependency injection and configuration
4. **`total_ordering`** — generate all comparison methods from `__eq__` + `__lt__`
5. **`cached_property`** — lazy one-time computation, cached on instance'''
    ),
    (
        "python/itertools-patterns",
        "Show itertools patterns: grouping, windowing, combinatorics, and pipeline composition.",
        '''itertools patterns:

```python
import itertools
from typing import Iterator, TypeVar, Iterable, Callable
from collections.abc import Sequence

T = TypeVar("T")


# --- Grouping ---

from itertools import groupby

def group_by_key(items: list[dict], key: str) -> dict[str, list[dict]]:
    """Group items by a key value."""
    sorted_items = sorted(items, key=lambda x: x[key])
    return {
        k: list(group)
        for k, group in groupby(sorted_items, key=lambda x: x[key])
    }

# orders = [{"region": "US", ...}, {"region": "EU", ...}]
# by_region = group_by_key(orders, "region")
# {"EU": [...], "US": [...]}


# --- Chunking ---

def chunk(iterable: Iterable[T], size: int) -> Iterator[list[T]]:
    """Split iterable into fixed-size chunks."""
    it = iter(iterable)
    while True:
        batch = list(itertools.islice(it, size))
        if not batch:
            break
        yield batch

# list(chunk(range(10), 3))  # [[0,1,2], [3,4,5], [6,7,8], [9]]


# --- Sliding window ---

def sliding_window(iterable: Iterable[T], n: int) -> Iterator[tuple[T, ...]]:
    """Sliding window of size n over iterable."""
    it = iter(iterable)
    window = tuple(itertools.islice(it, n))
    if len(window) == n:
        yield window
    for item in it:
        window = window[1:] + (item,)
        yield window

# list(sliding_window([1,2,3,4,5], 3))
# [(1,2,3), (2,3,4), (3,4,5)]


# --- Flatten ---

def flatten(nested: Iterable) -> Iterator:
    """Flatten nested iterables (one level)."""
    return itertools.chain.from_iterable(nested)

# list(flatten([[1,2], [3,4], [5]]))  # [1, 2, 3, 4, 5]

def deep_flatten(nested) -> Iterator:
    """Recursively flatten arbitrarily nested iterables."""
    for item in nested:
        if isinstance(item, (list, tuple, set)):
            yield from deep_flatten(item)
        else:
            yield item

# list(deep_flatten([1, [2, [3, 4]], [5, [6]]]))  # [1,2,3,4,5,6]


# --- Combinatorics ---

from itertools import product, combinations, permutations

# Cartesian product
sizes = ["S", "M", "L"]
colors = ["red", "blue"]
variants = list(product(sizes, colors))
# [("S","red"), ("S","blue"), ("M","red"), ("M","blue"), ...]

# Combinations (order doesn't matter)
pairs = list(combinations([1, 2, 3, 4], 2))
# [(1,2), (1,3), (1,4), (2,3), (2,4), (3,4)]

# Permutations (order matters)
arrangements = list(permutations([1, 2, 3], 2))
# [(1,2), (1,3), (2,1), (2,3), (3,1), (3,2)]


# --- Pipeline composition ---

def pipeline(*steps: Callable[[Iterator], Iterator]):
    """Compose iterator transformations into a pipeline."""
    def run(data: Iterable) -> Iterator:
        result = iter(data)
        for step in steps:
            result = step(result)
        return result
    return run

def filter_active(items):
    return (item for item in items if item.get("active"))

def transform_names(items):
    return ({**item, "name": item["name"].upper()} for item in items)

def take(n: int):
    def _take(items):
        return itertools.islice(items, n)
    return _take

process = pipeline(filter_active, transform_names, take(10))
# results = list(process(all_users))


# --- Accumulate (running totals) ---

from itertools import accumulate
import operator

# Running sum
running_total = list(accumulate([1, 2, 3, 4, 5]))
# [1, 3, 6, 10, 15]

# Running max
running_max = list(accumulate([3, 1, 4, 1, 5, 9], max))
# [3, 3, 4, 4, 5, 9]

# Running product
running_product = list(accumulate([1, 2, 3, 4], operator.mul))
# [1, 2, 6, 24]


# --- Interleave ---

def interleave(*iterables: Iterable[T]) -> Iterator[T]:
    """Interleave multiple iterables."""
    for items in itertools.zip_longest(*iterables, fillvalue=None):
        for item in items:
            if item is not None:
                yield item

# list(interleave([1,3,5], [2,4,6]))  # [1,2,3,4,5,6]


# --- Pairwise (Python 3.10+) ---

from itertools import pairwise

# list(pairwise([1,2,3,4]))  # [(1,2), (2,3), (3,4)]

# Compute differences
values = [10, 15, 13, 20, 18]
diffs = [b - a for a, b in pairwise(values)]
# [5, -2, 7, -2]
```

itertools patterns:
1. **`groupby`** — group sorted items by key (must sort first!)
2. **`islice`** — lazy slicing for chunking and pagination
3. **`chain.from_iterable`** — flatten one level of nesting
4. **`product`** — Cartesian product for generating all combinations
5. **`accumulate`** — running totals/max/product without loops'''
    ),
]
