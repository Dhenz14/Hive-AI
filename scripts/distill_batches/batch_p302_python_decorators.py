"""Python decorators: class decorators, decorator factories, functools.wraps, stacking, parametrized decorators."""

PAIRS = [
    (
        "python/decorators/factory-patterns",
        "How do I write parametrized decorator factories in Python? Show patterns for retry logic, caching, and rate limiting with configurable parameters.",
        '''Decorator factories are functions that return decorators. They let you configure behavior at decoration time while keeping the decorator pattern clean.

```python
"""Parametrized decorator factories — retry, cache, rate limit,
timeout, and deprecation decorators with full type safety."""

from __future__ import annotations

import asyncio
import functools
import hashlib
import json
import logging
import time
import warnings
from collections import OrderedDict
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar, overload

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Retry decorator factory
# ---------------------------------------------------------------------------
def retry(
    max_attempts: int = 3,
    *,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
    on_retry: Callable[[Exception, int], None] | None = None,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Decorator factory: retry a function on specified exceptions.

    Args:
        max_attempts: Maximum number of tries.
        delay: Initial delay between retries in seconds.
        backoff: Multiplier applied to delay after each retry.
        exceptions: Tuple of exception types to catch.
        on_retry: Optional callback(exception, attempt_number).
    """
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            current_delay = delay
            last_exception: Exception | None = None

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:
                    last_exception = exc
                    if attempt == max_attempts:
                        break
                    if on_retry:
                        on_retry(exc, attempt)
                    logger.warning(
                        "Retry %d/%d for %s: %s (next in %.1fs)",
                        attempt, max_attempts, func.__name__, exc, current_delay,
                    )
                    time.sleep(current_delay)
                    current_delay *= backoff

            raise last_exception  # type: ignore[misc]

        # Expose config for testing/introspection
        wrapper.max_attempts = max_attempts  # type: ignore[attr-defined]
        wrapper.retry_exceptions = exceptions  # type: ignore[attr-defined]
        return wrapper

    return decorator


# Async variant
def async_retry(
    max_attempts: int = 3,
    *,
    delay: float = 1.0,
    backoff: float = 2.0,
    exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """Async version of the retry decorator."""
    def decorator(func: Callable[P, Any]) -> Callable[P, Any]:
        @functools.wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            current_delay = delay
            last_exc: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as exc:
                    last_exc = exc
                    if attempt < max_attempts:
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff
            raise last_exc  # type: ignore[misc]
        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# 2. LRU Cache with TTL (time-to-live)
# ---------------------------------------------------------------------------
def ttl_cache(
    maxsize: int = 128,
    ttl_seconds: float = 300.0,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Cache function results with a time-to-live expiry."""
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        cache: OrderedDict[str, tuple[float, R]] = OrderedDict()
        lock = None  # threading.Lock() if thread-safe needed

        def _make_key(*args: Any, **kwargs: Any) -> str:
            key_data = json.dumps(
                {"args": args, "kwargs": sorted(kwargs.items())},
                default=str, sort_keys=True,
            )
            return hashlib.sha256(key_data.encode()).hexdigest()

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            key = _make_key(*args, **kwargs)
            now = time.monotonic()

            # Check cache
            if key in cache:
                timestamp, value = cache[key]
                if now - timestamp < ttl_seconds:
                    cache.move_to_end(key)
                    return value
                else:
                    del cache[key]

            # Compute and store
            result = func(*args, **kwargs)
            cache[key] = (now, result)

            # Evict oldest if over capacity
            while len(cache) > maxsize:
                cache.popitem(last=False)

            return result

        def cache_clear() -> None:
            cache.clear()

        def cache_info() -> dict[str, Any]:
            return {"size": len(cache), "maxsize": maxsize, "ttl": ttl_seconds}

        wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
        wrapper.cache_info = cache_info  # type: ignore[attr-defined]
        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# 3. Rate limiter decorator (token bucket)
# ---------------------------------------------------------------------------
def rate_limit(
    calls: int = 10,
    period: float = 1.0,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Limit function calls to `calls` per `period` seconds."""
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        call_times: list[float] = []

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            now = time.monotonic()
            # Remove expired timestamps
            cutoff = now - period
            while call_times and call_times[0] < cutoff:
                call_times.pop(0)

            if len(call_times) >= calls:
                wait_time = call_times[0] + period - now
                raise RuntimeError(
                    f"Rate limit exceeded for {func.__name__}. "
                    f"Try again in {wait_time:.1f}s"
                )

            call_times.append(now)
            return func(*args, **kwargs)

        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# 4. Deprecation decorator factory
# ---------------------------------------------------------------------------
def deprecated(
    *,
    since: str = "",
    removed_in: str = "",
    alternative: str = "",
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Mark a function as deprecated with migration guidance."""
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        parts = [f"{func.__name__} is deprecated"]
        if since:
            parts.append(f"(since {since})")
        if removed_in:
            parts.append(f"and will be removed in {removed_in}")
        if alternative:
            parts.append(f"— use {alternative} instead")
        message = " ".join(parts) + "."

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            warnings.warn(message, DeprecationWarning, stacklevel=2)
            return func(*args, **kwargs)

        wrapper.__deprecated__ = message  # type: ignore[attr-defined]
        return wrapper

    return decorator


# ---------------------------------------------------------------------------
# 5. Timing / metrics decorator factory
# ---------------------------------------------------------------------------
def timed(
    *,
    label: str = "",
    log_args: bool = False,
    threshold_ms: float = 0.0,
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Log function execution time."""
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        name = label or func.__qualname__

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                elapsed_ms = (time.perf_counter() - start) * 1000
                if elapsed_ms >= threshold_ms:
                    msg = f"{name} took {elapsed_ms:.2f}ms"
                    if log_args:
                        msg += f" args={args} kwargs={kwargs}"
                    logger.info(msg)

        return wrapper
    return decorator


# ---------------------------------------------------------------------------
# Usage examples
# ---------------------------------------------------------------------------
@retry(max_attempts=3, delay=0.1, exceptions=(ConnectionError, TimeoutError))
def fetch_data(url: str) -> dict:
    """Simulated unreliable API call."""
    import random
    if random.random() < 0.7:
        raise ConnectionError("Connection refused")
    return {"url": url, "data": "ok"}


@ttl_cache(maxsize=100, ttl_seconds=60)
def expensive_query(user_id: int, include_history: bool = False) -> dict:
    """Simulated expensive database query."""
    time.sleep(0.1)
    return {"user_id": user_id, "name": "Alice", "history": include_history}


@rate_limit(calls=5, period=1.0)
def send_notification(user_id: int, message: str) -> bool:
    return True


@deprecated(since="2.0", removed_in="3.0", alternative="new_api_call()")
def old_api_call(endpoint: str) -> dict:
    return {"endpoint": endpoint}


@timed(threshold_ms=50.0)
def process_batch(items: list[int]) -> int:
    time.sleep(0.1)
    return sum(items)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Retry
    try:
        result = fetch_data("https://api.example.com/data")
        print(f"Fetch result: {result}")
    except ConnectionError:
        print("All retries failed")

    # TTL cache
    r1 = expensive_query(42)
    r2 = expensive_query(42)  # cached — instant
    print(f"Cache info: {expensive_query.cache_info()}")

    # Timing
    process_batch(list(range(100)))
```

**Key patterns:**

- **Three-level nesting** — factory returns decorator, decorator returns wrapper: `factory(params)(func)` -> `wrapper`
- **`functools.wraps`** — preserves `__name__`, `__doc__`, `__module__`, and `__qualname__` of the original function
- **`ParamSpec` + `TypeVar`** — full type safety: the wrapper has the same signature as the original
- **Attached metadata** — add `.cache_info()`, `.cache_clear()`, or `.max_attempts` to the wrapper for introspection
- **Async variants** — use `async def wrapper` and `await func(...)` for async-compatible decorators
- **Stacking** — decorators compose naturally: `@retry @timed @rate_limit` applies in bottom-up order'''
    ),
    (
        "python/decorators/class-decorators",
        "Show me how to write class decorators in Python — decorators that modify classes, and decorators implemented as classes. What are the patterns for each?",
        '''There are two distinct concepts: (1) decorators *applied to* classes that modify the class, and (2) decorators *implemented as* classes using `__call__`. Both are powerful patterns.

```python
"""Class decorators — decorators that modify classes, and
decorators implemented as classes (callable objects)."""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, ParamSpec, TypeVar, get_type_hints

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger(__name__)


# ===================================================================
# PART 1: Decorators APPLIED TO classes
# ===================================================================

# ---------------------------------------------------------------------------
# 1a. Singleton class decorator
# ---------------------------------------------------------------------------
def singleton(cls: type) -> type:
    """Make a class a singleton — only one instance ever exists."""
    instances: dict[type, Any] = {}
    original_init = cls.__init__

    @functools.wraps(cls.__init__)
    def __init__(self: Any, *args: Any, **kwargs: Any) -> None:
        if cls not in instances:
            original_init(self, *args, **kwargs)
            instances[cls] = self

    cls.__init__ = __init__

    original_new = cls.__new__

    def __new__(klass: type, *args: Any, **kwargs: Any) -> Any:
        if klass in instances:
            return instances[klass]
        instance = object.__new__(klass)
        instances[klass] = instance
        return instance

    cls.__new__ = __new__
    return cls


# ---------------------------------------------------------------------------
# 1b. Auto-register class decorator (plugin pattern)
# ---------------------------------------------------------------------------
class Registry:
    """Plugin registry that auto-discovers decorated classes."""

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self._registry: dict[str, type] = {}

    def register(self, *, name: str = "") -> Callable[[type], type]:
        """Decorator to register a class in this registry."""
        def decorator(cls: type) -> type:
            key = name or cls.__name__
            if key in self._registry:
                raise ValueError(f"Duplicate registration: {key!r}")
            self._registry[key] = cls
            cls._registry_name = key  # type: ignore[attr-defined]
            return cls
        return decorator

    def get(self, name: str) -> type:
        return self._registry[name]

    def create(self, name: str, *args: Any, **kwargs: Any) -> Any:
        cls = self.get(name)
        return cls(*args, **kwargs)

    @property
    def registered_names(self) -> list[str]:
        return list(self._registry.keys())


# Usage of registry
handler_registry = Registry("handlers")


@handler_registry.register(name="json")
class JSONHandler:
    def parse(self, data: str) -> dict:
        import json
        return json.loads(data)


@handler_registry.register(name="csv")
class CSVHandler:
    def parse(self, data: str) -> list[list[str]]:
        return [line.split(",") for line in data.strip().split("\\n")]


# ---------------------------------------------------------------------------
# 1c. Add methods/properties to a class
# ---------------------------------------------------------------------------
def add_repr(cls: type) -> type:
    """Add a __repr__ based on __init__ parameters."""
    hints = get_type_hints(cls.__init__) if hasattr(cls, "__init__") else {}
    params = [p for p in hints if p != "return"]

    def __repr__(self: Any) -> str:
        fields_str = ", ".join(
            f"{p}={getattr(self, p, '?')!r}" for p in params
        )
        return f"{cls.__name__}({fields_str})"

    cls.__repr__ = __repr__
    return cls


def add_equality(cls: type) -> type:
    """Add __eq__ and __hash__ based on all instance attributes."""
    def __eq__(self: Any, other: Any) -> bool:
        if type(self) is not type(other):
            return NotImplemented
        return vars(self) == vars(other)

    def __hash__(self: Any) -> int:
        return hash(tuple(sorted(vars(self).items())))

    cls.__eq__ = __eq__
    cls.__hash__ = __hash__
    return cls


# ---------------------------------------------------------------------------
# 1d. Parametrized class decorator — add validation
# ---------------------------------------------------------------------------
def validate_fields(**field_validators: Callable) -> Callable[[type], type]:
    """Add field validation to a class's __init__.

    Usage:
        @validate_fields(age=lambda v: 0 <= v <= 150, name=lambda v: len(v) > 0)
        class Person:
            def __init__(self, name: str, age: int): ...
    """
    def decorator(cls: type) -> type:
        original_init = cls.__init__

        @functools.wraps(original_init)
        def new_init(self: Any, *args: Any, **kwargs: Any) -> None:
            original_init(self, *args, **kwargs)
            for field_name, validator in field_validators.items():
                value = getattr(self, field_name, None)
                if not validator(value):
                    raise ValueError(
                        f"Validation failed for {field_name}={value!r}"
                    )

        cls.__init__ = new_init
        return cls

    return decorator


# ===================================================================
# PART 2: Decorators IMPLEMENTED AS classes
# ===================================================================

# ---------------------------------------------------------------------------
# 2a. Callable class decorator with state
# ---------------------------------------------------------------------------
class CountCalls:
    """Decorator that counts how many times a function is called."""

    def __init__(self, func: Callable[P, R]) -> None:
        functools.update_wrapper(self, func)
        self.func = func
        self.call_count = 0

    def __call__(self, *args: P.args, **kwargs: P.kwargs) -> R:
        self.call_count += 1
        logger.debug("%s called %d times", self.func.__name__, self.call_count)
        return self.func(*args, **kwargs)

    def reset(self) -> None:
        self.call_count = 0


# ---------------------------------------------------------------------------
# 2b. Class decorator with parameters (using __init__ + __call__)
# ---------------------------------------------------------------------------
class Throttle:
    """Class-based decorator that throttles function calls.

    As a class, it can maintain state between calls.
    """

    def __init__(self, min_interval: float = 1.0, *, raise_on_throttle: bool = False):
        self.min_interval = min_interval
        self.raise_on_throttle = raise_on_throttle
        self._func: Callable | None = None
        self._last_called: float = 0.0

    def __call__(self, func: Callable[P, R]) -> Callable[P, R | None]:
        self._func = func

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
            now = time.monotonic()
            elapsed = now - self._last_called

            if elapsed < self.min_interval:
                if self.raise_on_throttle:
                    raise RuntimeError(
                        f"Throttled: {func.__name__} called too soon "
                        f"({elapsed:.2f}s < {self.min_interval}s)"
                    )
                logger.debug("Throttled call to %s", func.__name__)
                return None

            self._last_called = now
            return func(*args, **kwargs)

        wrapper.throttle = self  # type: ignore[attr-defined]
        return wrapper


# ---------------------------------------------------------------------------
# 2c. Descriptor-based decorator (works as instance method)
# ---------------------------------------------------------------------------
class Memoize:
    """Decorator implemented as a descriptor — works correctly as a
    method decorator (handles `self` properly).
    """

    def __init__(self, func: Callable) -> None:
        self.func = func
        self.cache: dict[tuple, Any] = {}
        functools.update_wrapper(self, func)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        key = (args, tuple(sorted(kwargs.items())))
        if key not in self.cache:
            self.cache[key] = self.func(*args, **kwargs)
        return self.cache[key]

    def __get__(self, obj: Any, objtype: type | None = None) -> Callable:
        """Support instance methods by binding self."""
        if obj is None:
            return self
        return functools.partial(self.__call__, obj)


# ---------------------------------------------------------------------------
# Usage demonstrations
# ---------------------------------------------------------------------------
@singleton
class AppConfig:
    def __init__(self, env: str = "production") -> None:
        self.env = env
        self.settings: dict = {}


@add_repr
@add_equality
@validate_fields(
    age=lambda v: 0 <= v <= 150,
    name=lambda v: isinstance(v, str) and len(v) > 0,
)
class Person:
    def __init__(self, name: str, age: int) -> None:
        self.name = name
        self.age = age


@CountCalls
def process_item(item_id: int) -> str:
    return f"processed-{item_id}"


@Throttle(min_interval=0.5)
def send_alert(message: str) -> None:
    print(f"ALERT: {message}")


class MathService:
    @Memoize
    def fibonacci(self, n: int) -> int:
        if n < 2:
            return n
        return self.fibonacci(n - 1) + self.fibonacci(n - 2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG)

    # Singleton
    c1 = AppConfig("dev")
    c2 = AppConfig("prod")
    print(f"Same instance: {c1 is c2}")  # True

    # Registry
    handler = handler_registry.create("json")
    print(handler.parse('{"key": "value"}'))
    print(f"Registered: {handler_registry.registered_names}")

    # Stacked decorators
    p = Person("Alice", 30)
    print(repr(p))  # Person(name='Alice', age=30)

    # CountCalls
    for i in range(5):
        process_item(i)
    print(f"Call count: {process_item.call_count}")

    # Memoize as method
    svc = MathService()
    print(f"fib(30) = {svc.fibonacci(30)}")
```

**Key patterns:**

- **Decorators applied to classes** modify the class itself — add methods, register, validate, or enforce singleton
- **Decorators implemented as classes** use `__init__` for configuration and `__call__` for invocation, giving them persistent state
- **Descriptor protocol** — implement `__get__` on class-based decorators so they work correctly as method decorators (binding `self`)
- **`functools.update_wrapper`** — preserves the original function metadata when using class-based decorators
- **Registry pattern** — parametrized class decorator with `register(name=...)` for plugin discovery
- **Stacking** — `@add_repr @add_equality @validate_fields(...)` applies bottom-up, each modifying the class'''
    ),
    (
        "python/decorators/stacking-composition",
        "How does decorator stacking work in Python? Show the order of execution, how to compose multiple decorators, and how to debug decorator stacks.",
        '''Decorator stacking applies decorators bottom-up (innermost first), but *executes* top-down at call time. Understanding this is critical for correct composition.

```python
"""Decorator stacking — execution order, composition helpers,
and debugging decorator chains."""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar

P = ParamSpec("P")
R = TypeVar("R")

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Demonstration decorators that log their execution
# ---------------------------------------------------------------------------
def log_entry_exit(name: str) -> Callable:
    """Decorator factory that logs when it wraps and when it runs."""
    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        print(f"  [{name}] wrapping {func.__name__}")

        @functools.wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            print(f"  [{name}] ENTER -> calling {func.__name__}")
            result = func(*args, **kwargs)
            print(f"  [{name}] EXIT  <- {func.__name__} returned {result!r}")
            return result

        return wrapper
    return decorator


# Stacking order demonstration:
print("--- Decoration time (bottom-up) ---")


@log_entry_exit("A")     # Applied THIRD (outermost wrapper)
@log_entry_exit("B")     # Applied SECOND
@log_entry_exit("C")     # Applied FIRST (innermost wrapper)
def greet(name: str) -> str:
    return f"Hello, {name}!"


print("\\n--- Call time (top-down) ---")
result = greet("World")
print(f"\\nResult: {result}")

# Output:
# --- Decoration time (bottom-up) ---
#   [C] wrapping greet        # C wraps greet first
#   [B] wrapping greet        # B wraps C's wrapper
#   [A] wrapping greet        # A wraps B's wrapper
#
# --- Call time (top-down) ---
#   [A] ENTER -> calling greet    # A runs first (outermost)
#   [B] ENTER -> calling greet    # B runs second
#   [C] ENTER -> calling greet    # C runs third (innermost)
#   [C] EXIT  <- greet returned 'Hello, World!'
#   [B] EXIT  <- greet returned 'Hello, World!'
#   [A] EXIT  <- greet returned 'Hello, World!'


# ---------------------------------------------------------------------------
# Composing decorators into a reusable pipeline
# ---------------------------------------------------------------------------
def compose(*decorators: Callable) -> Callable:
    """Compose multiple decorators into one.

    compose(A, B, C)(func) is equivalent to A(B(C(func)))
    """
    def composed_decorator(func: Callable) -> Callable:
        for dec in reversed(decorators):
            func = dec(func)
        return func
    return composed_decorator


# Reusable decorator pipeline
def validate_input(func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        for arg in args:
            if arg is None:
                raise ValueError("None argument not allowed")
        return func(*args, **kwargs)
    return wrapper


def timing(func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = (time.perf_counter() - start) * 1000
        logger.info("%s took %.2fms", func.__name__, elapsed)
        return result
    return wrapper


def log_calls(func: Callable[P, R]) -> Callable[P, R]:
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        logger.info("Calling %s(%s, %s)", func.__name__, args, kwargs)
        result = func(*args, **kwargs)
        logger.info("%s returned %r", func.__name__, result)
        return result
    return wrapper


# Create a reusable composed decorator
api_handler = compose(timing, log_calls, validate_input)


@api_handler
def process_order(order_id: str, amount: float) -> dict:
    return {"order_id": order_id, "amount": amount, "status": "processed"}


# ---------------------------------------------------------------------------
# Decorator that inspects the decorator chain
# ---------------------------------------------------------------------------
def debug_decorators(func: Callable) -> Callable:
    """Decorator that records the decoration chain for debugging."""

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    # Walk the wrapper chain
    chain: list[str] = []
    current: Any = wrapper
    while hasattr(current, "__wrapped__"):
        chain.append(current.__qualname__)
        current = current.__wrapped__
    chain.append(current.__qualname__)

    wrapper._decorator_chain = chain  # type: ignore[attr-defined]
    return wrapper


# ---------------------------------------------------------------------------
# Conditional decorator
# ---------------------------------------------------------------------------
def conditional(
    condition: bool,
    decorator: Callable,
) -> Callable:
    """Apply a decorator only if condition is True.

    Usage:
        @conditional(DEBUG, log_calls)
        def my_func(): ...
    """
    if condition:
        return decorator
    return lambda func: func  # identity — no-op


DEBUG = True


@conditional(DEBUG, timing)
@conditional(DEBUG, log_calls)
def debug_function(x: int) -> int:
    return x * 2


# ---------------------------------------------------------------------------
# Decorator with optional parentheses
# ---------------------------------------------------------------------------
def flexible_decorator(
    func: Callable | None = None,
    *,
    label: str = "",
    log_level: int = logging.INFO,
) -> Callable:
    """Decorator that works with or without parentheses.

    Both of these work:
        @flexible_decorator
        def foo(): ...

        @flexible_decorator(label="custom")
        def bar(): ...
    """
    def actual_decorator(f: Callable[P, R]) -> Callable[P, R]:
        name = label or f.__name__

        @functools.wraps(f)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            logger.log(log_level, ">>> %s", name)
            return f(*args, **kwargs)

        return wrapper

    if func is not None:
        # Called without parentheses: @flexible_decorator
        return actual_decorator(func)
    # Called with parentheses: @flexible_decorator(label="custom")
    return actual_decorator


@flexible_decorator
def no_parens() -> str:
    return "works"


@flexible_decorator(label="custom_name")
def with_parens() -> str:
    return "also works"


# ---------------------------------------------------------------------------
# Preserving type hints through decorator stacks
# ---------------------------------------------------------------------------
from typing import Protocol, runtime_checkable


@runtime_checkable
class HasMetadata(Protocol):
    __name__: str
    __doc__: str | None


def typed_decorator(func: Callable[P, R]) -> Callable[P, R]:
    """Template showing proper typing for decorators."""
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return func(*args, **kwargs)
    return wrapper


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Composed decorator
    result = process_order("ORD-123", 99.99)
    print(f"Order: {result}")

    # Conditional
    print(f"debug_function(5) = {debug_function(5)}")

    # Flexible
    print(no_parens())
    print(with_parens())
```

**Execution order rules:**

```
@A          # 3rd applied, 1st to run at call time
@B          # 2nd applied, 2nd to run at call time
@C          # 1st applied, 3rd to run at call time (closest to function)
def func(): ...

# Equivalent to: A(B(C(func)))
# Call order: A.enter -> B.enter -> C.enter -> func -> C.exit -> B.exit -> A.exit
```

**Key patterns:**

- **Bottom-up application** — decorators are applied from bottom to top (C, B, A)
- **Top-down execution** — at call time, the outermost wrapper (A) runs first
- **`compose()`** — combine multiple decorators into one reusable pipeline
- **`conditional()`** — apply a decorator only when a flag is set (debug mode, feature flags)
- **Flexible syntax** — support both `@decorator` and `@decorator(params)` by checking if `func` is `None`
- **`functools.wraps`** — always use it to preserve `__wrapped__` chain for debuggability'''
    ),
    (
        "python/decorators/method-descriptors",
        "How do I write decorators that work correctly on methods, classmethods, staticmethods, and properties? Show the descriptor protocol interaction.",
        '''Decorating methods is trickier than decorating functions because of the descriptor protocol. The decorator must handle `self` binding correctly.

```python
"""Method decorators — handling self-binding, classmethods,
staticmethods, properties, and the descriptor protocol."""

from __future__ import annotations

import asyncio
import functools
import inspect
import time
from collections.abc import Callable
from typing import Any, ParamSpec, TypeVar, overload

P = ParamSpec("P")
R = TypeVar("R")


# ---------------------------------------------------------------------------
# 1. Basic method decorator (works with regular methods)
# ---------------------------------------------------------------------------
def log_method(func: Callable[P, R]) -> Callable[P, R]:
    """Simple method decorator — works because @functools.wraps
    preserves the function signature including `self`."""
    @functools.wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        # args[0] is `self` for instance methods
        cls_name = type(args[0]).__name__ if args else "?"
        print(f"  {cls_name}.{func.__name__} called")
        return func(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# 2. Descriptor-based decorator (correctly handles all method types)
# ---------------------------------------------------------------------------
class MethodTimer:
    """Descriptor-based decorator that works with:
    - Regular instance methods
    - @classmethod
    - @staticmethod
    - @property

    Implements __get__ to correctly bind the method.
    """

    def __init__(self, func: Callable) -> None:
        self.func = func
        functools.update_wrapper(self, func)

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        result = self.func(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000
        print(f"  {self.func.__qualname__} took {elapsed_ms:.2f}ms")
        return result

    def __get__(self, obj: Any, objtype: type | None = None) -> Any:
        """Descriptor protocol: bind the method to the instance."""
        if obj is None:
            # Accessed from the class, not an instance
            return self
        # Return a bound method
        return functools.partial(self.__call__, obj)


# ---------------------------------------------------------------------------
# 3. Decorator that works with both sync and async methods
# ---------------------------------------------------------------------------
def universal_log(func: Callable) -> Callable:
    """Decorator that works with both sync and async functions/methods."""
    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            name = func.__qualname__
            print(f"  [async] {name} called")
            result = await func(*args, **kwargs)
            print(f"  [async] {name} returned")
            return result
        return async_wrapper
    else:
        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            name = func.__qualname__
            print(f"  [sync] {name} called")
            result = func(*args, **kwargs)
            print(f"  [sync] {name} returned")
            return result
        return sync_wrapper


# ---------------------------------------------------------------------------
# 4. Decorator for classmethods and staticmethods (order matters!)
# ---------------------------------------------------------------------------
class Service:
    """Demonstrates correct decorator ordering with class/static methods.

    RULE: Custom decorators go ABOVE @classmethod/@staticmethod.
    The class/static decorator must be the innermost (closest to def).
    """

    def __init__(self, name: str) -> None:
        self.name = name
        self._cache: dict = {}

    # Regular method — any decorator works
    @log_method
    def process(self, data: str) -> str:
        return f"{self.name}: processed {data}"

    # Classmethod — decorator ABOVE @classmethod
    @universal_log
    @classmethod
    def from_config(cls, config: dict) -> Service:
        return cls(name=config.get("name", "default"))

    # Staticmethod — decorator ABOVE @staticmethod
    @universal_log
    @staticmethod
    def validate_name(name: str) -> bool:
        return len(name) > 0 and name.isalnum()


# ---------------------------------------------------------------------------
# 5. Property decorator — combining with caching
# ---------------------------------------------------------------------------
def cached_property_with_ttl(ttl_seconds: float = 300.0) -> Callable:
    """A property decorator with time-based cache invalidation."""
    def decorator(method: Callable) -> property:
        cache_attr = f"_cached_{method.__name__}"
        time_attr = f"_cached_{method.__name__}_time"

        @property
        @functools.wraps(method)
        def wrapper(self: Any) -> Any:
            now = time.monotonic()
            cached_time = getattr(self, time_attr, 0.0)
            if now - cached_time < ttl_seconds and hasattr(self, cache_attr):
                return getattr(self, cache_attr)

            value = method(self)
            object.__setattr__(self, cache_attr, value)
            object.__setattr__(self, time_attr, now)
            return value

        return wrapper  # type: ignore[return-value]
    return decorator


# ---------------------------------------------------------------------------
# 6. Method decorator that accesses instance state
# ---------------------------------------------------------------------------
def require_auth(
    *,
    roles: tuple[str, ...] = (),
) -> Callable:
    """Decorator that checks authentication before allowing method call.

    Expects the instance to have a `current_user` attribute.
    """
    def decorator(method: Callable) -> Callable:
        @functools.wraps(method)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            user = getattr(self, "current_user", None)
            if user is None:
                raise PermissionError("Authentication required")
            if roles:
                user_roles = getattr(user, "roles", set())
                if not set(roles) & set(user_roles):
                    raise PermissionError(
                        f"Requires one of {roles}, user has {user_roles}"
                    )
            return method(self, *args, **kwargs)
        return wrapper
    return decorator


class User:
    def __init__(self, name: str, roles: set[str]) -> None:
        self.name = name
        self.roles = roles


class AdminPanel:
    def __init__(self, current_user: User | None = None) -> None:
        self.current_user = current_user

    @require_auth(roles=("admin", "superadmin"))
    def delete_user(self, user_id: str) -> str:
        return f"Deleted user {user_id}"

    @require_auth()
    def view_dashboard(self) -> str:
        return "Dashboard data"


# ---------------------------------------------------------------------------
# 7. Auto-register method decorator (event handler pattern)
# ---------------------------------------------------------------------------
class EventHandlerMixin:
    """Mixin that discovers methods decorated with @handles."""
    _event_handlers: dict[str, list[Callable]]

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        cls._event_handlers = {}
        for name in dir(cls):
            method = getattr(cls, name, None)
            if callable(method) and hasattr(method, "_handles_event"):
                event = method._handles_event
                cls._event_handlers.setdefault(event, []).append(name)

    def emit(self, event: str, **data: Any) -> list[Any]:
        results = []
        for method_name in self._event_handlers.get(event, []):
            method = getattr(self, method_name)
            results.append(method(**data))
        return results


def handles(event: str) -> Callable:
    """Mark a method as a handler for the given event."""
    def decorator(method: Callable) -> Callable:
        method._handles_event = event  # type: ignore[attr-defined]
        return method
    return decorator


class OrderService(EventHandlerMixin):
    @handles("order.created")
    def send_confirmation(self, order_id: str, **kw: Any) -> str:
        return f"Confirmation sent for {order_id}"

    @handles("order.created")
    def update_inventory(self, order_id: str, **kw: Any) -> str:
        return f"Inventory updated for {order_id}"

    @handles("order.cancelled")
    def process_refund(self, order_id: str, **kw: Any) -> str:
        return f"Refund processed for {order_id}"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print("=== Method decorators ===")
    svc = Service("MySvc")
    svc.process("hello")

    print("\\n=== Classmethod ===")
    svc2 = Service.from_config({"name": "configured"})

    print("\\n=== Staticmethod ===")
    Service.validate_name("test")

    print("\\n=== Auth decorator ===")
    admin = AdminPanel(current_user=User("alice", {"admin"}))
    print(admin.delete_user("U-42"))

    no_auth = AdminPanel()
    try:
        no_auth.view_dashboard()
    except PermissionError as e:
        print(f"Blocked: {e}")

    print("\\n=== Event handlers ===")
    orders = OrderService()
    results = orders.emit("order.created", order_id="ORD-123")
    for r in results:
        print(f"  {r}")
```

**Key patterns:**

- **Regular method decorators** work with `@functools.wraps` because `self` passes through `*args`
- **Descriptor-based decorators** implement `__get__` to correctly bind methods to instances
- **Ordering rule**: custom decorators go ABOVE `@classmethod` / `@staticmethod` (they must be innermost)
- **Universal decorators** check `asyncio.iscoroutinefunction()` to handle both sync and async
- **Instance-aware decorators** access `self` via `args[0]` or explicit first parameter to check state (auth, permissions)
- **Event handler pattern** — `@handles("event")` marks methods, `__init_subclass__` discovers them at class creation time'''
    ),
    (
        "python/decorators/functools-advanced",
        "What advanced functools features should I know for writing decorators? Show singledispatch, cache, partial, and update_wrapper in depth.",
        '''The `functools` module provides essential building blocks for decorators. Here are the advanced features every Python developer should master.

```python
"""Advanced functools for decorators — singledispatch, cache,
partial, update_wrapper, and reduce patterns."""

from __future__ import annotations

import functools
import json
import logging
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from typing import Any, TypeVar, overload
from uuid import UUID

logger = logging.getLogger(__name__)
T = TypeVar("T")


# ---------------------------------------------------------------------------
# 1. @singledispatch — type-based function overloading
# ---------------------------------------------------------------------------
@functools.singledispatch
def serialize(obj: Any) -> Any:
    """Serialize Python objects to JSON-compatible types.

    Register new types without modifying this function.
    """
    raise TypeError(f"Cannot serialize {type(obj).__name__}")


@serialize.register
def _(obj: str) -> str:
    return obj


@serialize.register
def _(obj: int | float) -> int | float:
    return obj


@serialize.register
def _(obj: bool) -> bool:
    return obj


@serialize.register
def _(obj: datetime) -> str:
    return obj.isoformat()


@serialize.register
def _(obj: date) -> str:
    return obj.isoformat()


@serialize.register
def _(obj: UUID) -> str:
    return str(obj)


@serialize.register
def _(obj: Decimal) -> str:
    return str(obj)


@serialize.register(list)
@serialize.register(tuple)
def _(obj: Sequence) -> list:
    return [serialize(item) for item in obj]


@serialize.register
def _(obj: dict) -> dict:
    return {str(k): serialize(v) for k, v in obj.items()}


# Register for dataclasses generically
@serialize.register
def _(obj: object) -> dict:
    """Fallback: try dataclass serialization."""
    from dataclasses import fields, asdict
    if hasattr(obj, "__dataclass_fields__"):
        return {f.name: serialize(getattr(obj, f.name)) for f in fields(obj)}
    raise TypeError(f"Cannot serialize {type(obj).__name__}")


# ---------------------------------------------------------------------------
# 2. @singledispatchmethod — for class methods
# ---------------------------------------------------------------------------
class Formatter:
    """Demonstrates singledispatchmethod for method overloading."""

    def __init__(self, indent: int = 2) -> None:
        self.indent = indent

    @functools.singledispatchmethod
    def format(self, value: Any) -> str:
        return repr(value)

    @format.register
    def _(self, value: str) -> str:
        return f'"{value}"'

    @format.register
    def _(self, value: int) -> str:
        return f"{value:,}"

    @format.register
    def _(self, value: float) -> str:
        return f"{value:.4f}"

    @format.register
    def _(self, value: dict) -> str:
        return json.dumps(value, indent=self.indent)

    @format.register
    def _(self, value: list) -> str:
        items = ", ".join(self.format(item) for item in value)
        return f"[{items}]"


# ---------------------------------------------------------------------------
# 3. @cache and @lru_cache — memoization
# ---------------------------------------------------------------------------
# @cache (Python 3.9+) — unbounded cache, simplest API
@functools.cache
def fibonacci(n: int) -> int:
    """Unbounded memoization — suitable for pure functions with
    small argument space."""
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)


# @lru_cache — bounded cache with eviction
@functools.lru_cache(maxsize=256)
def parse_user_agent(ua_string: str) -> dict[str, str]:
    """LRU cache with size limit — evicts least-recently-used entries.

    Good for functions where the argument space is large but access
    patterns are hot-spot heavy.
    """
    # Simulated expensive parsing
    parts = ua_string.split("/")
    return {
        "browser": parts[0] if parts else "Unknown",
        "version": parts[1] if len(parts) > 1 else "0",
        "raw": ua_string,
    }


# Custom cache key function using functools.partial
def cache_with_key(
    key_func: Callable[..., Any],
    maxsize: int = 128,
) -> Callable:
    """Decorator that caches based on a custom key function."""
    def decorator(func: Callable) -> Callable:
        cache: dict[Any, Any] = {}
        hits = misses = 0

        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            nonlocal hits, misses
            key = key_func(*args, **kwargs)
            if key in cache:
                hits += 1
                return cache[key]
            misses += 1
            result = func(*args, **kwargs)
            cache[key] = result
            if len(cache) > maxsize:
                # Evict oldest
                oldest = next(iter(cache))
                del cache[oldest]
            return result

        wrapper.cache_info = lambda: {  # type: ignore[attr-defined]
            "hits": hits, "misses": misses, "size": len(cache),
        }
        wrapper.cache_clear = cache.clear  # type: ignore[attr-defined]
        return wrapper
    return decorator


# Usage: cache by first argument only (ignore others)
@cache_with_key(lambda user_id, **kw: user_id)
def get_user_profile(user_id: int, include_avatar: bool = False) -> dict:
    """Cache keyed only on user_id, ignoring other params."""
    return {"user_id": user_id, "name": f"User-{user_id}"}


# ---------------------------------------------------------------------------
# 4. functools.partial and partialmethod
# ---------------------------------------------------------------------------
class APIClient:
    """Demonstrates partial and partialmethod for creating
    specialized versions of methods."""

    def __init__(self, base_url: str, api_key: str) -> None:
        self.base_url = base_url
        self.api_key = api_key

    def request(
        self,
        method: str,
        path: str,
        *,
        data: dict | None = None,
        headers: dict | None = None,
    ) -> dict:
        """Generic HTTP request method."""
        url = f"{self.base_url}{path}"
        print(f"  {method} {url} data={data}")
        return {"status": 200, "method": method, "path": path}

    # Create specialized methods using partialmethod
    get = functools.partialmethod(request, "GET")
    post = functools.partialmethod(request, "POST")
    put = functools.partialmethod(request, "PUT")
    delete = functools.partialmethod(request, "DELETE")
    patch = functools.partialmethod(request, "PATCH")


# functools.partial for standalone functions
def create_logger(
    name: str,
    level: int = logging.INFO,
    fmt: str = "%(name)s - %(message)s",
) -> Callable:
    """Create a pre-configured logging function."""
    log = logging.getLogger(name)
    log.setLevel(level)
    # Return a partial that pre-fills the level
    return functools.partial(log.log, level)


# ---------------------------------------------------------------------------
# 5. functools.reduce — building pipelines
# ---------------------------------------------------------------------------
def pipeline(*functions: Callable) -> Callable:
    """Compose functions left-to-right: pipeline(f, g, h)(x) = h(g(f(x)))"""
    def apply(value: Any) -> Any:
        return functools.reduce(lambda v, f: f(v), functions, value)
    return apply


# Usage
clean_text = pipeline(
    str.strip,
    str.lower,
    lambda s: s.replace("  ", " "),
    lambda s: s.replace("\n", " "),
)


# ---------------------------------------------------------------------------
# 6. functools.total_ordering — complete comparison from __eq__ + __lt__
# ---------------------------------------------------------------------------
@functools.total_ordering
@dataclass
class Version:
    """Semantic version with full comparison support from just __eq__ and __lt__."""
    major: int
    minor: int
    patch: int

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return (self.major, self.minor, self.patch) == (other.major, other.minor, other.patch)

    def __lt__(self, other: Version) -> bool:
        if not isinstance(other, Version):
            return NotImplemented
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # singledispatch
    print("=== singledispatch ===")
    print(serialize(42))
    print(serialize(datetime.now()))
    print(serialize({"key": [1, 2, Decimal("3.14")]}))

    # Formatter (singledispatchmethod)
    fmt = Formatter()
    print(f"int: {fmt.format(1_000_000)}")
    print(f"float: {fmt.format(3.14159)}")

    # Cache
    print(f"\n=== cache ===")
    print(f"fib(30) = {fibonacci(30)}")
    print(f"Cache info: {fibonacci.cache_info()}")

    print(f"UA: {parse_user_agent('Chrome/120.0')}")
    print(f"LRU info: {parse_user_agent.cache_info()}")

    # Partial
    print(f"\n=== partial ===")
    client = APIClient("https://api.example.com", "key-123")
    client.get("/users")
    client.post("/users", data={"name": "Alice"})

    # Pipeline
    print(f"\n=== pipeline ===")
    result = clean_text("  Hello   World\n  Foo  ")
    print(f"Cleaned: {result!r}")

    # total_ordering
    versions = [Version(2, 0, 0), Version(1, 9, 3), Version(2, 1, 0)]
    print(f"\nSorted: {sorted(versions)}")
    print(f"Max: {max(versions)}")
```

**Key patterns:**

- **`@singledispatch`** — register type-specific implementations without if/elif chains; extensible by third parties
- **`@singledispatchmethod`** — same but for class methods; dispatches on the second argument (after `self`)
- **`@cache`** — unbounded memoization for pure functions; Python 3.9+
- **`@lru_cache(maxsize=N)`** — bounded memoization with LRU eviction; use `cache_info()` to monitor hit rates
- **`functools.partial`** — create specialized function variants by pre-filling arguments
- **`functools.partialmethod`** — same but for class methods; creates bound method variants
- **`functools.reduce`** — build left-to-right function pipelines
- **`@total_ordering`** — generate all 6 comparison methods from just `__eq__` and `__lt__`'''
    ),
]
