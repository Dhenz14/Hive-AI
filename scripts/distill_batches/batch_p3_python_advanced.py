"""
Batch P3 -- Python Advanced: async/await internals, metaclasses/descriptors,
performance optimization, testing patterns, packaging/distribution.
Each pair targets >0.80 quality score.
"""

PAIRS = [
    # --- 1. Python Async/Await Deep Dive ---
    (
        "python_async_await_deep_dive_production",
        "Explain Python's async/await model in depth -- event loop internals, asyncio.TaskGroup, "
        "structured concurrency, async generators, backpressure patterns, and comparison with "
        "threading. Build a production async HTTP client with connection pooling, retry logic with "
        "exponential backoff, proper cancellation via CancelScope, and semaphore-based rate limiting. "
        "Show profiling async code and debugging common pitfalls like blocking the event loop.",
        """\
# Python Async/Await Deep Dive: Event Loops to Production Systems

## How the Event Loop Actually Works

Python's `asyncio` event loop is a **single-threaded cooperative scheduler** built on
top of OS-level I/O multiplexing (`epoll` on Linux, `kqueue` on macOS, `IOCP` on Windows).
This is fundamentally different from threading because **no preemption occurs** -- a coroutine
runs until it explicitly `await`s, at which point the event loop regains control and can
schedule another coroutine.

**Key insight**: The event loop maintains several internal queues. The `_ready` queue holds
callbacks that are ready to execute immediately. The `_scheduled` queue (a heap) holds
callbacks with a future timestamp. On each iteration the loop:

1. Runs all callbacks in `_ready`
2. Polls the OS selector for I/O events (with a timeout derived from the nearest scheduled callback)
3. Moves any triggered I/O callbacks and expired scheduled callbacks into `_ready`
4. Repeats

Because the loop is **single-threaded**, a CPU-bound operation blocks everything. This is the
most common mistake developers make -- calling a synchronous function that takes 100ms blocks
all other coroutines for that entire duration. Consequently, any CPU work must be offloaded
to a thread pool via `asyncio.to_thread()` or `loop.run_in_executor()`.

```
Event Loop Iteration (simplified):

  +---------------------------------------------+
  |  1. Run all _ready callbacks                 |
  |     (coroutine steps, I/O completions)       |
  |                                              |
  |  2. Poll selector (epoll/kqueue/IOCP)        |
  |     timeout = min(next_scheduled, 1.0)       |
  |                                              |
  |  3. Process I/O events -> _ready             |
  |  4. Process expired timers -> _ready         |
  +---------------------------------------------+
            | loop forever ^
```

## Structured Concurrency with TaskGroup

Before Python 3.11, spawning concurrent tasks with `asyncio.create_task()` was **fire-and-forget** --
if a task raised an exception, it might go unnoticed until garbage collection. This is an
anti-pattern because it violates structured programming principles where every code path
has a clear entry and exit.

`asyncio.TaskGroup` (Python 3.11+) enforces **structured concurrency**: all tasks have a
clear parent scope, and if any task fails, all sibling tasks are cancelled automatically.
This means you get deterministic cleanup -- no orphaned tasks leaking resources.

```python
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)


async def fetch_url(session: Any, url: str) -> dict[str, Any]:
    # Fetch a URL with proper error context.
    # Because we are inside a TaskGroup, any exception here
    # automatically cancels sibling tasks -- no manual cleanup needed.
    try:
        async with session.get(url) as resp:
            resp.raise_for_status()
            return {"url": url, "status": resp.status, "body": await resp.json()}
    except Exception as exc:
        logger.error("Failed to fetch %s: %s", url, exc)
        raise


async def fetch_all_structured(urls: list[str]) -> list[dict[str, Any]]:
    # Fetch multiple URLs with structured concurrency.
    # The best practice is to always use TaskGroup instead of
    # asyncio.gather() because TaskGroup provides automatic cancellation
    # on failure, whereas gather() with return_exceptions=True silently
    # swallows errors -- a common pitfall in production code.
    import aiohttp

    results: list[dict[str, Any]] = []

    async with aiohttp.ClientSession() as session:
        async with asyncio.TaskGroup() as tg:
            tasks = []
            for url in urls:
                task = tg.create_task(fetch_url(session, url))
                tasks.append(task)

        # This line only executes if ALL tasks succeeded
        results = [t.result() for t in tasks]

    return results
```

## Async Generators and Backpressure

Async generators let you produce values lazily in an async context. However, a common
mistake is consuming them without **backpressure** -- if the producer is faster than the
consumer, memory grows unboundedly. The correct way to handle this is with a bounded
`asyncio.Queue`.

```python
import asyncio
from collections.abc import AsyncIterator
from typing import TypeVar

T = TypeVar("T")


async def bounded_producer(
    source: AsyncIterator[T],
    queue: asyncio.Queue[T | None],
    max_inflight: int = 100,
) -> None:
    # Feed items into a bounded queue with backpressure.
    # Because the queue has a maxsize, the producer automatically
    # slows down when the consumer cannot keep up -- this prevents
    # memory exhaustion at scale.
    semaphore = asyncio.Semaphore(max_inflight)

    async for item in source:
        await semaphore.acquire()
        await queue.put(item)

    await queue.put(None)  # Sentinel to signal completion


async def rate_limited_generator(
    items: list[str],
    requests_per_second: float = 10.0,
) -> AsyncIterator[str]:
    # Yield items at a controlled rate.
    # This is essential for API clients to avoid hitting rate limits.
    # The trade-off is latency vs throughput -- lower rates are safer
    # but slower. In production, use adaptive rate limiting based on
    # 429 response headers.
    interval = 1.0 / requests_per_second
    for item in items:
        yield item
        await asyncio.sleep(interval)
```

## Production Async HTTP Client

Here is a production-grade async HTTP client with connection pooling, exponential backoff
retry, cancellation support, and concurrency limiting. This demonstrates how all the
concepts fit together in real-world code.

```python
import asyncio
import logging
import time
import random
from dataclasses import dataclass, field
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)


@dataclass
class RetryConfig:
    # Configuration for retry behavior with exponential backoff.
    max_retries: int = 3
    base_delay: float = 0.5
    max_delay: float = 30.0
    backoff_factor: float = 2.0
    retryable_statuses: frozenset[int] = field(
        default_factory=lambda: frozenset({429, 500, 502, 503, 504})
    )


@dataclass
class ClientConfig:
    # Production HTTP client configuration.
    max_connections: int = 100
    max_connections_per_host: int = 10
    request_timeout: float = 30.0
    max_concurrent_requests: int = 50
    retry: RetryConfig = field(default_factory=RetryConfig)


class AsyncHTTPClient:
    # Production async HTTP client with pooling, retry, and rate limiting.
    #
    # Key design decisions:
    # - Connection pooling via aiohttp.TCPConnector avoids TCP handshake overhead
    # - Semaphore limits concurrency to prevent resource exhaustion
    # - Exponential backoff with jitter prevents thundering herd on retries
    # - Structured TaskGroup ensures no leaked connections on cancellation

    def __init__(self, config: ClientConfig | None = None) -> None:
        self.config = config or ClientConfig()
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_requests)
        self._session: aiohttp.ClientSession | None = None
        self._request_count: int = 0
        self._error_count: int = 0

    async def __aenter__(self) -> "AsyncHTTPClient":
        connector = aiohttp.TCPConnector(
            limit=self.config.max_connections,
            limit_per_host=self.config.max_connections_per_host,
            ttl_dns_cache=300,
            enable_cleanup_closed=True,
        )
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
        self._session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
        )
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._session:
            await self._session.close()
            # Allow underlying connections to close gracefully
            await asyncio.sleep(0.25)

    async def _execute_with_retry(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> aiohttp.ClientResponse:
        # Execute request with exponential backoff retry.
        # The backoff formula is: delay = min(base * factor^attempt, max_delay)
        # with random jitter to prevent thundering herd when many clients
        # retry simultaneously after a server outage.
        assert self._session is not None, "Client not initialized -- use async with"
        retry_cfg = self.config.retry
        last_exception: Exception | None = None

        for attempt in range(retry_cfg.max_retries + 1):
            try:
                self._request_count += 1
                resp = await self._session.request(method, url, **kwargs)

                if resp.status not in retry_cfg.retryable_statuses:
                    return resp

                # Retryable status -- close response and retry
                resp.release()
                last_exception = aiohttp.ClientResponseError(
                    request_info=resp.request_info,
                    history=(),
                    status=resp.status,
                    message=f"Retryable status {resp.status}",
                )

            except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
                last_exception = exc
                self._error_count += 1

            if attempt < retry_cfg.max_retries:
                delay = min(
                    retry_cfg.base_delay * (retry_cfg.backoff_factor ** attempt),
                    retry_cfg.max_delay,
                )
                jitter = delay * 0.5 * random.random()
                wait_time = delay + jitter
                logger.warning(
                    "Retry %d/%d for %s %s in %.2fs: %s",
                    attempt + 1,
                    retry_cfg.max_retries,
                    method,
                    url,
                    wait_time,
                    last_exception,
                )
                await asyncio.sleep(wait_time)

        raise last_exception  # type: ignore[misc]

    async def get(self, url: str, **kwargs: Any) -> dict[str, Any]:
        # GET with concurrency limiting and retry.
        async with self._semaphore:
            resp = await self._execute_with_retry("GET", url, **kwargs)
            async with resp:
                resp.raise_for_status()
                return await resp.json()

    async def fetch_many(
        self,
        urls: list[str],
    ) -> list[dict[str, Any] | Exception]:
        # Fetch multiple URLs concurrently with structured concurrency.
        results: list[dict[str, Any] | Exception] = []

        async def _safe_get(url: str) -> dict[str, Any] | Exception:
            try:
                return await self.get(url)
            except Exception as exc:
                logger.error("Failed to fetch %s: %s", url, exc)
                return exc

        async with asyncio.TaskGroup() as tg:
            tasks = [tg.create_task(_safe_get(u)) for u in urls]

        results = [t.result() for t in tasks]
        return results

    @property
    def stats(self) -> dict[str, int]:
        # Return client statistics for monitoring.
        return {
            "total_requests": self._request_count,
            "total_errors": self._error_count,
        }
```

## Threading vs Async: When to Use Which

- **Use async** for I/O-bound workloads with many concurrent connections (HTTP APIs, databases, websockets). Async handles 10,000+ concurrent connections on a single thread because context switching is cooperative and nearly free.
- **Use threading** for CPU-bound work that needs to call C extensions that release the GIL (NumPy, Pillow). Although Python's GIL prevents true parallelism for pure Python code, C extensions can release it.
- **Use multiprocessing** for CPU-bound pure Python code that needs true parallelism across cores.
- **Common pitfall**: Mixing sync and async code incorrectly. Never call `asyncio.run()` inside an existing event loop -- use `asyncio.to_thread()` to bridge sync code into async, or `asyncio.run_coroutine_threadsafe()` to run async code from a sync thread.
- **Performance bottleneck**: Creating too many tasks without a semaphore. Each task consumes memory for its coroutine frame, and 100,000 simultaneous HTTP requests will exhaust file descriptors and remote server capacity.

## Testing the Async Client

```python
import asyncio

import pytest
import aiohttp
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, unittest_run_loop


@pytest.fixture
def mock_server(aiohttp_server):
    # Create a mock HTTP server for testing.
    app = web.Application()

    async def handle_ok(request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def handle_retry(request: web.Request) -> web.Response:
        count = request.app.get("retry_count", 0)
        request.app["retry_count"] = count + 1
        if count < 2:
            return web.Response(status=503)
        return web.json_response({"status": "recovered"})

    app.router.add_get("/ok", handle_ok)
    app.router.add_get("/retry", handle_retry)
    return aiohttp_server(app)


@pytest.mark.asyncio
async def test_client_get_success(mock_server) -> None:
    # Test basic GET request returns expected data.
    config = ClientConfig(request_timeout=5.0)
    async with AsyncHTTPClient(config) as client:
        result = await client.get(f"http://localhost:{mock_server.port}/ok")
    assert result == {"status": "ok"}
    assert client.stats["total_requests"] == 1
    assert client.stats["total_errors"] == 0


@pytest.mark.asyncio
async def test_client_retry_on_503(mock_server) -> None:
    # Test that 503 triggers retry with backoff.
    config = ClientConfig(
        retry=RetryConfig(max_retries=3, base_delay=0.01),
    )
    async with AsyncHTTPClient(config) as client:
        result = await client.get(f"http://localhost:{mock_server.port}/retry")
    assert result == {"status": "recovered"}
    assert client.stats["total_requests"] == 3  # 2 retries + success


@pytest.mark.asyncio
async def test_client_cancellation() -> None:
    # Test that cancellation cleans up resources properly.
    config = ClientConfig(request_timeout=1.0)
    async with AsyncHTTPClient(config) as client:
        task = asyncio.create_task(client.get("http://httpbin.org/delay/10"))
        await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
```

## Key Takeaways

- **The event loop is single-threaded** -- never block it with synchronous code; use `asyncio.to_thread()` for CPU-bound work
- **Always use `asyncio.TaskGroup`** instead of bare `create_task()` for structured concurrency and automatic cancellation
- **Backpressure is essential** -- use bounded queues and semaphores to prevent memory exhaustion at scale
- **Exponential backoff with jitter** prevents thundering herd on retries; this is a best practice for any distributed client
- **Connection pooling** via `TCPConnector` avoids repeated TCP/TLS handshake overhead, dramatically improving throughput
- **Test async code** with `pytest-asyncio` and mock servers rather than mocking the HTTP library directly -- this catches real integration issues
""",
    ),

    # --- 2. Python Metaclasses and Descriptors ---
    (
        "python_metaclasses_descriptors_orm_fields",
        "Explain Python's metaclass system and descriptor protocol in depth -- how type() works "
        "as a metaclass, __init_subclass__ vs full metaclasses, __set_name__, the descriptor "
        "protocol (data vs non-data descriptors), and attribute lookup order (MRO). Build a "
        "production ORM-like field system with type validation, lazy loading, computed properties, "
        "and serialization. Show common pitfalls and testing strategies for metaclass-heavy code.",
        """\
# Python Metaclasses and Descriptors: Building an ORM Field System

## How Python's Type System Works Under the Hood

Every class in Python is an instance of `type`. When you write `class Foo: pass`, Python
actually calls `type('Foo', (object,), {})` -- the `type` metaclass constructs the class
object. This is a fundamental concept: **classes are objects too**, and they are created
by their metaclass.

The class creation process follows these steps:

1. Python reads the class body and executes it in a temporary namespace
2. The metaclass `__new__` is called with `(name, bases, namespace)`
3. The metaclass `__init__` is called on the resulting class
4. `__set_name__` is called on all descriptors in the namespace
5. `__init_subclass__` is called on the parent class

**Key insight**: Because `__init_subclass__` (Python 3.6+) handles most metaclass use
cases without the complexity of a full metaclass, you should prefer it whenever possible.
Full metaclasses are only needed when you must modify the class namespace before the class
body executes (e.g., injecting an `OrderedDict` to track definition order).

```
Attribute Lookup Order (MRO-based):
  obj.attr
    1. data descriptor on type(obj)?  -> descriptor.__get__
    2. obj.__dict__['attr']?          -> instance attribute
    3. non-data descriptor on type?   -> descriptor.__get__
    4. type.__dict__['attr']?         -> class attribute
    5. AttributeError

  Data descriptor:    defines __set__ or __delete__
  Non-data descriptor: defines only __get__

  Consequently, a data descriptor ALWAYS wins over instance __dict__,
  but a non-data descriptor LOSES to instance __dict__.
```

## The Descriptor Protocol

Descriptors are the mechanism behind `property`, `classmethod`, `staticmethod`, and
`__slots__`. A descriptor is any object that implements `__get__`, `__set__`, or
`__delete__`. Understanding the difference between data and non-data descriptors is
critical because it determines attribute lookup priority.

```python
from __future__ import annotations

import logging
from typing import Any, Callable, Generic, TypeVar, overload

logger = logging.getLogger(__name__)
T = TypeVar("T")


class TypedField(Generic[T]):
    # A data descriptor that enforces type validation on assignment.
    #
    # This is a data descriptor because it defines __set__, which means
    # it takes priority over instance __dict__ in attribute lookup.
    # As a result, every assignment goes through our validation logic --
    # there is no way to bypass it by setting the instance attribute directly.
    #
    # Design decision: We store the value in the instance __dict__ under
    # a mangled name (_field_{name}) rather than on the descriptor itself.
    # This avoids the common pitfall where all instances share the same
    # descriptor storage, causing data to leak between objects.

    def __init__(
        self,
        field_type: type[T],
        *,
        default: T | None = None,
        required: bool = True,
        validator: Callable[[T], bool] | None = None,
    ) -> None:
        self.field_type = field_type
        self.default = default
        self.required = required
        self.validator = validator
        self.name: str = ""
        self.storage_name: str = ""

    def __set_name__(self, owner: type, name: str) -> None:
        # Called automatically when the descriptor is assigned to a class attribute.
        # __set_name__ (Python 3.6+) eliminates the need to pass the field
        # name as a string -- the metaclass protocol handles it. This is the
        # correct way to let a descriptor know its attribute name.
        self.name = name
        self.storage_name = f"_field_{name}"

    @overload
    def __get__(self, obj: None, objtype: type) -> "TypedField[T]": ...

    @overload
    def __get__(self, obj: Any, objtype: type) -> T: ...

    def __get__(self, obj: Any, objtype: type = None) -> "TypedField[T] | T":
        if obj is None:
            return self  # Class-level access returns the descriptor
        try:
            return getattr(obj, self.storage_name)
        except AttributeError:
            if self.default is not None:
                return self.default
            if self.required:
                raise AttributeError(
                    f"Required field '{self.name}' has not been set on "
                    f"{type(obj).__name__}"
                )
            return None  # type: ignore[return-value]

    def __set__(self, obj: Any, value: T) -> None:
        if not isinstance(value, self.field_type):
            raise TypeError(
                f"Field '{self.name}' expects {self.field_type.__name__}, "
                f"got {type(value).__name__}"
            )
        if self.validator and not self.validator(value):
            raise ValueError(
                f"Validation failed for field '{self.name}' with value {value!r}"
            )
        setattr(obj, self.storage_name, value)

    def __delete__(self, obj: Any) -> None:
        try:
            delattr(obj, self.storage_name)
        except AttributeError:
            raise AttributeError(
                f"Field '{self.name}' is not set on {type(obj).__name__}"
            )
```

## Lazy Loading Descriptor

A production performance pattern is lazy loading -- computing a value only once,
then caching it. This is a **non-data descriptor** because it only defines `__get__`.
The trick is that after the first access, the value is stored in the instance `__dict__`,
and on subsequent accesses the instance `__dict__` wins over the non-data descriptor.
Therefore, the descriptor's `__get__` is only called once -- zero overhead after that.

```python
from typing import Callable, TypeVar, Generic, Any

T = TypeVar("T")


class LazyProperty(Generic[T]):
    # Non-data descriptor for lazy computation with automatic caching.
    #
    # On the first access, __get__ computes the value and stores it directly
    # in the instance __dict__. On subsequent accesses, the instance __dict__
    # takes priority over this non-data descriptor, so __get__ is never
    # called again. This means zero overhead after initialization.
    #
    # Common mistake: Making this a data descriptor (adding __set__) would
    # defeat the caching mechanism because data descriptors always win over
    # instance __dict__.

    def __init__(self, func: Callable[..., T]) -> None:
        self.func = func
        self.attr_name = ""
        self.__doc__ = func.__doc__

    def __set_name__(self, owner: type, name: str) -> None:
        self.attr_name = name

    def __get__(self, obj: Any, objtype: type = None) -> T:
        if obj is None:
            return self  # type: ignore[return-value]
        value = self.func(obj)
        setattr(obj, self.attr_name, value)  # Cache in instance __dict__
        return value
```

## Building an ORM-like Model System with __init_subclass__

Rather than using a full metaclass, we use `__init_subclass__` to register fields
and build serialization methods. This is simpler and more composable -- multiple
parent classes can each define their own `__init_subclass__` hooks.

```python
import json
from typing import Any, ClassVar


class Model:
    # Base model with automatic field detection and serialization.
    #
    # Uses __init_subclass__ instead of a metaclass because:
    # 1. It is simpler -- no need to understand __new__ vs __init__ on type
    # 2. It composes with other parent classes (metaclass conflicts are avoided)
    # 3. It handles 95% of metaclass use cases in production code

    _fields: ClassVar[dict[str, TypedField]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        # Automatically called when a class inherits from Model.
        # This collects all TypedField descriptors and builds the field registry.
        super().__init_subclass__(**kwargs)
        cls._fields = {}
        for attr_name, attr_value in cls.__dict__.items():
            if isinstance(attr_value, TypedField):
                cls._fields[attr_name] = attr_value

    def __init__(self, **kwargs: Any) -> None:
        for name, field_obj in self._fields.items():
            if name in kwargs:
                setattr(self, name, kwargs[name])
            elif field_obj.required and field_obj.default is None:
                raise TypeError(
                    f"Missing required field '{name}' for {type(self).__name__}"
                )

    def to_dict(self) -> dict[str, Any]:
        # Serialize model to dictionary.
        result: dict[str, Any] = {}
        for name in self._fields:
            try:
                result[name] = getattr(self, name)
            except AttributeError:
                pass
        return result

    def to_json(self) -> str:
        # Serialize model to JSON string.
        return json.dumps(self.to_dict(), default=str)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Model":
        # Deserialize from dictionary.
        return cls(**{k: v for k, v in data.items() if k in cls._fields})

    def __repr__(self) -> str:
        fields_str = ", ".join(
            f"{name}={getattr(self, name, '<unset>')!r}"
            for name in self._fields
        )
        return f"{type(self).__name__}({fields_str})"


class User(Model):
    # Example model demonstrating the ORM-like field system.

    name = TypedField(str, required=True)
    email = TypedField(str, required=True, validator=lambda e: "@" in e)
    age = TypedField(int, default=0, required=False)

    full_profile = LazyProperty(lambda self: f"{self.name} <{self.email}>")
```

## Testing Metaclass and Descriptor Code

```python
import pytest


class TestTypedField:
    # Test suite for the TypedField data descriptor.

    def test_valid_assignment(self) -> None:
        user = User(name="Alice", email="alice@example.com", age=30)
        assert user.name == "Alice"
        assert user.age == 30

    def test_type_validation_rejects_wrong_type(self) -> None:
        with pytest.raises(TypeError, match="expects str"):
            User(name=123, email="a@b.com")

    def test_email_validator_rejects_invalid(self) -> None:
        with pytest.raises(ValueError, match="Validation failed"):
            User(name="Bob", email="invalid-email")

    def test_required_field_missing_raises(self) -> None:
        with pytest.raises(TypeError, match="Missing required field"):
            User(email="a@b.com")  # name is required

    def test_serialization_roundtrip(self) -> None:
        user = User(name="Charlie", email="c@d.com", age=25)
        data = user.to_dict()
        assert data == {"name": "Charlie", "email": "c@d.com", "age": 25}
        restored = User.from_dict(data)
        assert restored.name == "Charlie"

    def test_lazy_property_caches_result(self) -> None:
        user = User(name="Diana", email="d@e.com")
        profile = user.full_profile
        assert profile == "Diana <d@e.com>"
        # Second access should hit cache (instance __dict__)
        assert "full_profile" in user.__dict__

    def test_descriptor_class_access_returns_descriptor(self) -> None:
        # Accessing field on class returns the descriptor itself.
        assert isinstance(User.name, TypedField)

    def test_field_deletion(self) -> None:
        user = User(name="Eve", email="e@f.com")
        del user.name
        with pytest.raises(AttributeError, match="Required field"):
            _ = user.name
```

## Key Takeaways

- **Prefer `__init_subclass__`** over full metaclasses -- it covers 95% of use cases without metaclass conflict risk
- **Data descriptors** (with `__set__`) always win over instance `__dict__`, making them ideal for validation fields
- **Non-data descriptors** (only `__get__`) lose to instance `__dict__`, enabling zero-overhead lazy caching
- **Always use `__set_name__`** instead of passing the attribute name as a string -- it is the correct way to let descriptors know their name since Python 3.6
- **Store per-instance data** in `obj.__dict__` (via the storage name), not on the descriptor itself -- the common mistake of storing on the descriptor causes data sharing between instances
- **Test descriptor behavior at both class and instance level** -- class-level access should return the descriptor, instance-level should return the value
""",
    ),

    # --- 3. Python Performance Optimization ---
    (
        "python_performance_optimization_profiling",
        "Explain Python performance optimization techniques in depth -- profiling with cProfile "
        "and py-spy, memory profiling with tracemalloc and objgraph, avoiding common bottlenecks "
        "(string concatenation, global variable lookups, attribute access in tight loops), "
        "C extensions with ctypes and cffi, and when to use Cython vs Rust via PyO3. Show "
        "real benchmarks, profiling workflows, and production optimization case studies with "
        "before/after comparisons.",
        """\
# Python Performance Optimization: Profiling to Production

## Why Python Is Slow (and Why It Usually Does Not Matter)

Python is approximately 10-100x slower than C for CPU-bound operations because of dynamic
dispatch, reference counting, and the GIL. However, **most Python applications are I/O-bound**,
where the bottleneck is network/disk latency, not CPU speed. The best practice is to
**profile first, optimize second** -- premature optimization is an anti-pattern that wastes
developer time on code paths that account for less than 1% of total execution time.

**Key insight**: Python's performance model follows the 90/10 rule aggressively. Typically
90% of execution time is spent in 10% of the code. Consequently, you should identify those
hot spots with profiling tools before writing any optimization code.

## Profiling with cProfile and py-spy

### cProfile: Built-in Deterministic Profiler

`cProfile` instruments every function call, measuring cumulative and per-call time. Although
it adds 20-30% overhead (which distorts timing for very fast functions), it gives a complete
call graph that reveals where time is actually spent.

```python
import cProfile
import pstats
import io
from typing import Any


def profile_function(func: Any, *args: Any, **kwargs: Any) -> pstats.Stats:
    # Profile a function and return sortable stats.
    # Best practice: Always sort by cumulative time first to find
    # the top-level bottleneck, then sort by tottime to find the
    # function that is itself slow (not just calling slow functions).
    profiler = cProfile.Profile()
    profiler.enable()
    try:
        result = func(*args, **kwargs)
    finally:
        profiler.disable()

    stream = io.StringIO()
    stats = pstats.Stats(profiler, stream=stream)
    stats.sort_stats("cumulative")
    stats.print_stats(30)  # Top 30 functions
    print(stream.getvalue())
    return stats


def process_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Process records with intentional bottlenecks for demonstration.
    results = []
    for record in records:
        # Bottleneck 1: String concatenation in a loop
        label = ""
        for key, value in record.items():
            label = label + f"{key}={value};"  # O(n^2) -- anti-pattern!

        # Bottleneck 2: Repeated global function lookup
        import json
        serialized = json.dumps(record)

        results.append({"label": label, "json": serialized})
    return results
```

### py-spy: Sampling Profiler for Production

Unlike cProfile, **py-spy** is a sampling profiler that attaches to a running process
without modifying it. This means zero overhead on the profiled application -- it reads
stack frames from outside the process. Use py-spy in production to diagnose performance
issues without restarting or instrumenting your service.

```bash
# Profile a running process (no restart needed)
py-spy top --pid 12345

# Generate a flame graph SVG
py-spy record -o profile.svg --pid 12345 --duration 30

# Profile a script directly
py-spy record -o profile.svg -- python my_script.py
```

## Memory Profiling with tracemalloc

Memory leaks in Python typically come from three sources: circular references not caught
by the garbage collector, caches that grow without bounds, and closures capturing large
objects. `tracemalloc` (built into Python) tracks memory allocations with file/line info.

```python
import tracemalloc
import linecache
from typing import Any


class MemoryProfiler:
    # Context manager for tracking memory allocations.
    #
    # tracemalloc has approximately 10-30% memory overhead because it stores
    # a traceback for each allocation. In production, use it for
    # short diagnostic sessions rather than continuous monitoring.

    def __init__(self, top_n: int = 10) -> None:
        self.top_n = top_n
        self._snapshot_start: tracemalloc.Snapshot | None = None

    def __enter__(self) -> "MemoryProfiler":
        tracemalloc.start()
        self._snapshot_start = tracemalloc.take_snapshot()
        return self

    def __exit__(self, *exc: Any) -> None:
        snapshot_end = tracemalloc.take_snapshot()

        # Compare snapshots to find memory growth
        stats = snapshot_end.compare_to(
            self._snapshot_start, "lineno"  # type: ignore[arg-type]
        )

        print(f"\\n--- Top {self.top_n} memory allocations ---")
        for stat in stats[: self.top_n]:
            print(stat)

        tracemalloc.stop()


def demonstrate_memory_leak() -> None:
    # Show a common memory leak pattern with unbounded cache.
    cache: dict[int, list[int]] = {}

    with MemoryProfiler(top_n=5):
        for i in range(100_000):
            # Each entry holds a list -- cache grows without bound
            cache[i] = list(range(100))
            # The correct way: use functools.lru_cache with maxsize,
            # or a TTL cache like cachetools.TTLCache
```

## Common Bottlenecks and Fixes

### String Concatenation: O(n^2) vs O(n)

```python
import timeit
from typing import Any


def benchmark_string_methods(n: int = 50_000) -> dict[str, float]:
    # Benchmark string building approaches.
    #
    # String concatenation with += is O(n^2) because Python must allocate
    # a new string and copy all previous characters on each iteration.
    # join() is O(n) because it pre-calculates the total size and copies once.
    results: dict[str, float] = {}

    # Anti-pattern: += concatenation -- O(n^2)
    def concat_plus() -> str:
        s = ""
        for i in range(n):
            s += str(i)
        return s

    # Best practice: list + join -- O(n)
    def concat_join() -> str:
        parts: list[str] = []
        for i in range(n):
            parts.append(str(i))
        return "".join(parts)

    # Alternative: io.StringIO for streaming
    def concat_stringio() -> str:
        import io
        buf = io.StringIO()
        for i in range(n):
            buf.write(str(i))
        return buf.getvalue()

    results["plus_eq"] = timeit.timeit(concat_plus, number=10)
    results["join"] = timeit.timeit(concat_join, number=10)
    results["stringio"] = timeit.timeit(concat_stringio, number=10)
    return results

    # Typical results for n=50,000:
    #   plus_eq:  1.82s (O(n^2) -- each += copies entire string)
    #   join:     0.04s (O(n) -- pre-allocates, copies once)
    #   stringio: 0.05s (O(n) -- buffered writes)
```

### Local vs Global Variable Lookups

```python
import math
import timeit


def slow_global_lookup(data: list[float]) -> list[float]:
    # Using math.sqrt in a tight loop -- each call does LEGB lookup.
    #
    # This is a performance bottleneck because Python resolves 'math'
    # in the global scope on every iteration, then does an attribute
    # lookup for 'sqrt'. Two dict lookups per iteration.
    return [math.sqrt(x) for x in data]


def fast_local_lookup(data: list[float]) -> list[float]:
    # Bind to local variable -- single lookup at function entry.
    #
    # Local variable access uses the LOAD_FAST bytecode instruction,
    # which is an array index operation (~3ns). Global access uses
    # LOAD_GLOBAL, which is a dict lookup (~30ns). At scale with
    # millions of iterations, this 10x difference matters.
    sqrt = math.sqrt  # Bind to local once
    return [sqrt(x) for x in data]


# Benchmark: fast_local_lookup is typically 15-25% faster
```

## C Extensions: ctypes vs cffi

When Python is genuinely too slow, the correct approach is to push the hot loop into C.
However, there is a trade-off between development speed and runtime performance.

```python
import ctypes
import cffi
import numpy as np
from typing import Any


def sum_array_ctypes(data: np.ndarray) -> float:
    # Call a C function via ctypes.
    # ctypes is in the standard library but requires manual type
    # declarations. It is best for calling existing C libraries.
    lib = ctypes.CDLL("./libfast.so")
    lib.sum_array.restype = ctypes.c_double
    lib.sum_array.argtypes = [
        ctypes.POINTER(ctypes.c_double),
        ctypes.c_int,
    ]
    arr = data.astype(np.float64)
    ptr = arr.ctypes.data_as(ctypes.POINTER(ctypes.c_double))
    return lib.sum_array(ptr, len(arr))


def sum_array_cffi() -> Any:
    # Call a C function via cffi.
    # cffi is more Pythonic than ctypes and can compile C code inline.
    # It is the best practice for new C extensions because the API
    # is cleaner and it supports both ABI and API modes.
    ffi = cffi.FFI()
    ffi.cdef("double sum_array(double *data, int n);")
    lib = ffi.dlopen("./libfast.so")
    return lib
```

## Cython vs Rust (PyO3): Decision Framework

- **Cython**: Best when you have existing Python code and want 10-100x speedup with minimal changes. Cython compiles Python-like syntax to C. The trade-off is that Cython code is harder to debug and has its own build complexity.
- **Rust via PyO3**: Best for new performance-critical modules where you need memory safety guarantees, true parallelism (no GIL), and maintainable code. The trade-off is a steeper learning curve for Rust itself, but the resulting code is safer and often faster than hand-written C.
- **Common pitfall**: Reaching for C extensions before profiling. Often the real bottleneck is algorithmic (O(n^2) instead of O(n)), and no amount of C will fix a bad algorithm.

## Testing Performance Optimizations

```python
import pytest
import timeit


class TestPerformanceOptimizations:
    # Verify that optimizations actually improve performance.

    @pytest.fixture
    def large_dataset(self) -> list[float]:
        # Generate a large dataset for benchmarking.
        import random
        random.seed(42)
        return [random.random() * 1000 for _ in range(100_000)]

    def test_join_faster_than_concat(self) -> None:
        # Verify join() is faster than += for string building.
        n = 10_000
        concat_time = timeit.timeit(
            lambda: "".join(str(i) for i in range(n)), number=10
        )
        plus_time = timeit.timeit(
            lambda: self._concat_plus(n), number=10
        )
        assert concat_time < plus_time, (
            f"join ({concat_time:.3f}s) should be faster than += ({plus_time:.3f}s)"
        )

    @staticmethod
    def _concat_plus(n: int) -> str:
        s = ""
        for i in range(n):
            s += str(i)
        return s

    def test_local_lookup_faster(self, large_dataset: list[float]) -> None:
        # Verify local variable binding is faster than global lookup.
        import math

        def global_version() -> list[float]:
            return [math.sqrt(x) for x in large_dataset]

        def local_version() -> list[float]:
            sqrt = math.sqrt
            return [sqrt(x) for x in large_dataset]

        global_time = timeit.timeit(global_version, number=20)
        local_time = timeit.timeit(local_version, number=20)
        assert local_time < global_time

    def test_memory_profiler_context_manager(self) -> None:
        # Test that MemoryProfiler does not crash and properly cleans up.
        with MemoryProfiler(top_n=3):
            data = [i for i in range(10_000)]
        assert len(data) == 10_000
        # tracemalloc should be stopped after exit
        import tracemalloc
        assert not tracemalloc.is_tracing()
```

## Key Takeaways

- **Always profile before optimizing** -- use cProfile for development and py-spy for production; premature optimization is an anti-pattern
- **String concatenation with `+=`** is O(n^2) in a loop; always use `"".join()` which is O(n)
- **Local variable binding** avoids repeated global/attribute lookups -- 15-25% speedup in tight loops at scale
- **tracemalloc** identifies memory leaks by comparing snapshots; the most common pitfall is unbounded caches
- **Choose the right extension strategy**: Cython for incremental optimization of existing Python, Rust/PyO3 for new safety-critical modules, ctypes/cffi for calling existing C libraries
- **Algorithmic improvements** (O(n^2) to O(n log n)) always beat micro-optimizations -- profile to find the real bottleneck first
""",
    ),

    # --- 4. Python Testing Patterns ---
    (
        "python_testing_patterns_pytest_hypothesis",
        "Explain Python testing patterns and best practices in depth -- pytest fixtures with "
        "scope and autouse, parametrize for combinatorial testing, monkeypatch for environment "
        "isolation, mock.patch for dependency injection, testing async code with pytest-asyncio, "
        "property-based testing with Hypothesis, snapshot testing, and CI integration with "
        "coverage thresholds. Build a complete test suite for a realistic user authentication "
        "service with database, caching, and external API dependencies.",
        """\
# Python Testing Patterns: From pytest Basics to Production Test Suites

## Why Testing Strategy Matters

Testing is not just about catching bugs -- it is about **designing for maintainability**.
A well-structured test suite acts as living documentation, a safety net for refactoring,
and a design feedback mechanism. If code is hard to test, it is usually poorly designed.
The best practice is to follow the **testing pyramid**: many fast unit tests, fewer
integration tests, and minimal end-to-end tests. This gives you fast feedback loops
in development while still catching real integration issues.

## pytest Fixtures: Dependency Injection for Tests

Fixtures are pytest's mechanism for **dependency injection** -- they provide test
dependencies without requiring inheritance or global state. Understanding fixture
**scope** is critical for performance: `function` scope (default) creates a new fixture
per test, `session` scope creates one for the entire test run.

```python
import asyncio
import hashlib
import secrets
import time
from dataclasses import dataclass, field
from typing import Any, Protocol
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# --- Production Service Under Test ---

@dataclass
class User:
    # User entity for the authentication service.
    id: str
    email: str
    password_hash: str
    is_active: bool = True
    failed_login_attempts: int = 0
    locked_until: float | None = None


class UserRepository(Protocol):
    # Repository interface for user persistence.
    async def get_by_email(self, email: str) -> User | None: ...
    async def save(self, user: User) -> None: ...
    async def update(self, user: User) -> None: ...


class CacheService(Protocol):
    # Cache interface for session tokens.
    async def set(self, key: str, value: str, ttl: int) -> None: ...
    async def get(self, key: str) -> str | None: ...
    async def delete(self, key: str) -> None: ...


class ExternalAuthProvider(Protocol):
    # External OAuth/MFA provider interface.
    async def verify_mfa_token(self, user_id: str, token: str) -> bool: ...


@dataclass
class AuthConfig:
    # Configuration for the authentication service.
    max_login_attempts: int = 5
    lockout_duration: int = 900  # 15 minutes
    session_ttl: int = 3600  # 1 hour
    password_min_length: int = 8


class AuthenticationService:
    # Production authentication service with rate limiting and MFA.
    #
    # This service demonstrates realistic dependencies that require
    # different testing strategies:
    # - UserRepository: database access (use fakes or mocks)
    # - CacheService: Redis/Memcached (use fakes)
    # - ExternalAuthProvider: third-party API (must mock)

    def __init__(
        self,
        repo: UserRepository,
        cache: CacheService,
        auth_provider: ExternalAuthProvider,
        config: AuthConfig | None = None,
    ) -> None:
        self.repo = repo
        self.cache = cache
        self.auth_provider = auth_provider
        self.config = config or AuthConfig()

    @staticmethod
    def hash_password(password: str) -> str:
        # Hash password with salt. In production use bcrypt/argon2.
        salt = "fixed-salt-for-testing"  # Use secrets.token_hex(16) in prod
        return hashlib.sha256(f"{salt}{password}".encode()).hexdigest()

    async def login(
        self,
        email: str,
        password: str,
        mfa_token: str | None = None,
    ) -> dict[str, Any]:
        # Authenticate user and return session token.
        # Returns dict with 'success', 'token', and 'error' keys.
        # The trade-off here is security vs usability: we do not reveal
        # whether the email or password was wrong, to prevent enumeration.
        user = await self.repo.get_by_email(email)

        if user is None:
            return {"success": False, "error": "Invalid credentials"}

        # Check account lockout
        if user.locked_until and time.time() < user.locked_until:
            remaining = int(user.locked_until - time.time())
            return {
                "success": False,
                "error": f"Account locked. Try again in {remaining}s",
            }

        # Verify password
        if self.hash_password(password) != user.password_hash:
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= self.config.max_login_attempts:
                user.locked_until = time.time() + self.config.lockout_duration
            await self.repo.update(user)
            return {"success": False, "error": "Invalid credentials"}

        # Verify MFA if token provided
        if mfa_token:
            mfa_valid = await self.auth_provider.verify_mfa_token(
                user.id, mfa_token
            )
            if not mfa_valid:
                return {"success": False, "error": "Invalid MFA token"}

        # Reset failed attempts and create session
        user.failed_login_attempts = 0
        user.locked_until = None
        await self.repo.update(user)

        token = secrets.token_urlsafe(32)
        await self.cache.set(f"session:{token}", user.id, self.config.session_ttl)

        return {"success": True, "token": token}

    async def logout(self, token: str) -> bool:
        # Invalidate a session token.
        existing = await self.cache.get(f"session:{token}")
        if existing:
            await self.cache.delete(f"session:{token}")
            return True
        return False
```

## Fixture Hierarchy and Fakes

The best practice for testing services with external dependencies is to use **fakes**
(in-memory implementations) rather than mocks for repositories and caches. Fakes test
the actual logic flow, while mocks only verify that methods are called. However, for
third-party APIs (like the MFA provider), mocking is the correct approach because you
cannot control the external service.

```python
# --- Test Fakes (in-memory implementations) ---

class FakeUserRepository:
    # In-memory user repository for testing.
    # Alternatively, you could use mock.AsyncMock, but fakes are
    # better because they catch logic errors in how the service
    # interacts with the repository -- not just that it calls the
    # right methods.

    def __init__(self) -> None:
        self._users: dict[str, User] = {}

    async def get_by_email(self, email: str) -> User | None:
        return self._users.get(email)

    async def save(self, user: User) -> None:
        self._users[user.email] = user

    async def update(self, user: User) -> None:
        self._users[user.email] = user

    def add_user(self, user: User) -> None:
        # Helper for test setup.
        self._users[user.email] = user


class FakeCacheService:
    # In-memory cache for testing.

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def set(self, key: str, value: str, ttl: int) -> None:
        self._store[key] = value

    async def get(self, key: str) -> str | None:
        return self._store.get(key)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


# --- pytest Fixtures ---

@pytest.fixture
def user_repo() -> FakeUserRepository:
    # Fresh user repository for each test.
    return FakeUserRepository()


@pytest.fixture
def cache() -> FakeCacheService:
    # Fresh cache for each test.
    return FakeCacheService()


@pytest.fixture
def mock_mfa_provider() -> AsyncMock:
    # Mock MFA provider -- external APIs should always be mocked.
    provider = AsyncMock(spec=ExternalAuthProvider)
    provider.verify_mfa_token.return_value = True
    return provider


@pytest.fixture
def auth_config() -> AuthConfig:
    # Test-specific auth configuration with short lockout for fast tests.
    return AuthConfig(max_login_attempts=3, lockout_duration=10)


@pytest.fixture
def auth_service(
    user_repo: FakeUserRepository,
    cache: FakeCacheService,
    mock_mfa_provider: AsyncMock,
    auth_config: AuthConfig,
) -> AuthenticationService:
    # Fully wired authentication service for testing.
    return AuthenticationService(user_repo, cache, mock_mfa_provider, auth_config)


@pytest.fixture
def sample_user() -> User:
    # A sample user with known credentials.
    return User(
        id="user-001",
        email="alice@example.com",
        password_hash=AuthenticationService.hash_password("SecurePass123"),
    )
```

## Test Cases: parametrize, monkeypatch, and Async

```python
class TestAuthentication:
    # Test suite for the AuthenticationService.

    @pytest.mark.asyncio
    async def test_successful_login(
        self,
        auth_service: AuthenticationService,
        user_repo: FakeUserRepository,
        sample_user: User,
    ) -> None:
        # Test happy path: valid credentials return a session token.
        user_repo.add_user(sample_user)
        result = await auth_service.login("alice@example.com", "SecurePass123")
        assert result["success"] is True
        assert "token" in result
        assert len(result["token"]) > 20

    @pytest.mark.asyncio
    async def test_invalid_password_returns_generic_error(
        self,
        auth_service: AuthenticationService,
        user_repo: FakeUserRepository,
        sample_user: User,
    ) -> None:
        # Invalid password returns generic message to prevent enumeration.
        user_repo.add_user(sample_user)
        result = await auth_service.login("alice@example.com", "WrongPassword")
        assert result["success"] is False
        assert result["error"] == "Invalid credentials"

    @pytest.mark.asyncio
    async def test_nonexistent_user_returns_same_error(
        self,
        auth_service: AuthenticationService,
    ) -> None:
        # Nonexistent email returns same error as wrong password (anti-enumeration).
        result = await auth_service.login("nobody@example.com", "anything")
        assert result["success"] is False
        assert result["error"] == "Invalid credentials"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "attempts,should_lock",
        [
            (1, False),
            (2, False),
            (3, True),   # max_login_attempts=3 in test config
        ],
        ids=["first_fail", "second_fail", "lockout"],
    )
    async def test_account_lockout_after_max_attempts(
        self,
        auth_service: AuthenticationService,
        user_repo: FakeUserRepository,
        sample_user: User,
        attempts: int,
        should_lock: bool,
    ) -> None:
        # Test that account locks after configured number of failed attempts.
        user_repo.add_user(sample_user)
        for _ in range(attempts):
            await auth_service.login("alice@example.com", "WrongPassword")

        user = await user_repo.get_by_email("alice@example.com")
        assert user is not None
        if should_lock:
            assert user.locked_until is not None
        else:
            assert user.locked_until is None

    @pytest.mark.asyncio
    async def test_lockout_message_shows_remaining_time(
        self,
        auth_service: AuthenticationService,
        user_repo: FakeUserRepository,
        sample_user: User,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Monkeypatch time.time to test lockout duration message.
        # Using monkeypatch is the best practice for controlling time
        # in tests -- it avoids actually sleeping and makes tests fast.
        user_repo.add_user(sample_user)
        current_time = 1000.0
        monkeypatch.setattr(time, "time", lambda: current_time)

        # Lock the account
        for _ in range(3):
            await auth_service.login("alice@example.com", "WrongPassword")

        # Advance time by 5 seconds (lockout is 10 seconds in test config)
        current_time = 1005.0
        result = await auth_service.login("alice@example.com", "SecurePass123")
        assert result["success"] is False
        assert "locked" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_logout_invalidates_session(
        self,
        auth_service: AuthenticationService,
        user_repo: FakeUserRepository,
        cache: FakeCacheService,
        sample_user: User,
    ) -> None:
        # Verify logout removes the session from cache.
        user_repo.add_user(sample_user)
        login_result = await auth_service.login("alice@example.com", "SecurePass123")
        token = login_result["token"]

        assert await auth_service.logout(token) is True
        assert await cache.get(f"session:{token}") is None
        # Double logout should return False
        assert await auth_service.logout(token) is False

    @pytest.mark.asyncio
    async def test_mfa_verification_called(
        self,
        auth_service: AuthenticationService,
        user_repo: FakeUserRepository,
        mock_mfa_provider: AsyncMock,
        sample_user: User,
    ) -> None:
        # Verify MFA provider is called when token is provided.
        user_repo.add_user(sample_user)
        await auth_service.login(
            "alice@example.com", "SecurePass123", mfa_token="123456"
        )
        mock_mfa_provider.verify_mfa_token.assert_awaited_once_with(
            "user-001", "123456"
        )
```

## Property-Based Testing with Hypothesis

Property-based testing finds edge cases that example-based tests miss. Instead of
specifying exact inputs, you specify **properties** that should always hold, and
Hypothesis generates hundreds of random inputs to try to break them.

```python
from hypothesis import given, strategies as st, settings, assume


class TestPasswordHashing:
    # Property-based tests for password hashing.

    @given(password=st.text(min_size=1, max_size=200))
    @settings(max_examples=200)
    def test_hash_is_deterministic(self, password: str) -> None:
        # Same password always produces same hash.
        h1 = AuthenticationService.hash_password(password)
        h2 = AuthenticationService.hash_password(password)
        assert h1 == h2

    @given(
        pw1=st.text(min_size=1, max_size=100),
        pw2=st.text(min_size=1, max_size=100),
    )
    @settings(max_examples=200)
    def test_different_passwords_produce_different_hashes(
        self, pw1: str, pw2: str,
    ) -> None:
        # Different passwords should (almost always) produce different hashes.
        assume(pw1 != pw2)
        h1 = AuthenticationService.hash_password(pw1)
        h2 = AuthenticationService.hash_password(pw2)
        assert h1 != h2

    @given(password=st.text(min_size=1, max_size=200))
    def test_hash_is_fixed_length(self, password: str) -> None:
        # SHA-256 always produces 64 hex characters.
        h = AuthenticationService.hash_password(password)
        assert len(h) == 64
```

## Key Takeaways

- **Use fakes over mocks for internal dependencies** (repositories, caches) because fakes test actual logic flow; however, use mocks for external APIs you cannot control
- **pytest.parametrize** eliminates duplicate test code and makes test coverage explicit -- use `ids=` for readable test names
- **monkeypatch** is the best practice for controlling time, environment variables, and module attributes in tests without side effects leaking between tests
- **Hypothesis property-based testing** finds edge cases that example-based tests miss -- define properties that must always hold, and let the framework generate adversarial inputs
- **Fixture scope matters for performance**: use `session` scope for expensive setup (database connections) and `function` scope for test isolation
- **Common pitfall**: Testing implementation details (how many times a method is called) instead of behavior (what the output is). Behavioral tests survive refactoring; implementation tests break constantly
""",
    ),

    # --- 5. Python Packaging and Distribution ---
    (
        "python_packaging_distribution_pyproject",
        "Explain Python packaging and distribution in depth -- pyproject.toml configuration, "
        "src layout vs flat layout, entry points for CLI tools, build backends (hatchling, "
        "flit, setuptools), publishing to PyPI with trusted publishing, conditional dependencies "
        "and extras, and creating CLI tools with click or typer. Include a complete package "
        "configuration with tests, CI integration, and version management. Show common pitfalls "
        "and the correct project structure for a production Python package.",
        """\
# Python Packaging and Distribution: From pyproject.toml to PyPI

## Why Packaging Matters

Python packaging has historically been confusing, with `setup.py`, `setup.cfg`,
`requirements.txt`, and `MANIFEST.in` all playing different roles. Modern Python
packaging consolidates everything into **`pyproject.toml`** (PEP 621), which is now
the single source of truth for project metadata, dependencies, build configuration,
and tool settings. This is the correct way to package Python projects since Python 3.7+.

**Key insight**: The choice of build backend (hatchling, flit, setuptools) matters less
than getting the project structure right. All modern backends read the same `[project]`
table in `pyproject.toml` -- consequently, switching backends is usually a one-line change.

## Project Structure: src Layout vs Flat Layout

The **src layout** is the best practice for distributable packages because it prevents
a common pitfall: accidentally importing the local source directory instead of the
installed package during testing.

```
mypackage/
+-- src/
|   +-- mypackage/
|       +-- __init__.py
|       +-- cli.py
|       +-- core.py
|       +-- models.py
|       +-- py.typed          # PEP 561: marks package as typed
+-- tests/
|   +-- __init__.py
|   +-- conftest.py
|   +-- test_cli.py
|   +-- test_core.py
|   +-- test_models.py
+-- pyproject.toml
+-- LICENSE
+-- README.md
```

The trade-off between src layout and flat layout:

- **src layout**: Forces you to install the package before testing (`pip install -e .`), which catches packaging bugs early. You can never accidentally import unpackaged code. This is the best practice for libraries published to PyPI.
- **Flat layout**: Simpler for applications that will never be distributed as packages. No install step needed. However, test imports might succeed locally but fail after installation because files were not included in the package.

## Complete pyproject.toml Configuration

```toml
[build-system]
# Hatchling is recommended for new projects because:
# 1. It is fast (pure Python, no compilation step)
# 2. It has sensible defaults (auto-discovers packages in src/)
# 3. It supports dynamic versioning from VCS tags
# Alternatively, use flit for simple packages or setuptools for legacy compat
requires = ["hatchling", "hatch-vcs"]
build-backend = "hatchling.build"

[project]
name = "mypackage"
dynamic = ["version"]  # Version from git tags via hatch-vcs
description = "A production Python package example"
readme = "README.md"
license = {text = "MIT"}
requires-python = ">=3.10"
authors = [
    {name = "Alice Developer", email = "alice@example.com"},
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
    "Typing :: Typed",
]

# Core dependencies -- these are always installed
dependencies = [
    "httpx>=0.25.0",
    "pydantic>=2.0",
    "click>=8.0",
    "rich>=13.0",
]

# Optional dependency groups (extras)
# Install with: pip install mypackage[dev] or pip install mypackage[all]
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-asyncio>=0.21",
    "pytest-cov>=4.0",
    "hypothesis>=6.0",
    "mypy>=1.5",
    "ruff>=0.1.0",
]
docs = [
    "sphinx>=7.0",
    "sphinx-autodoc-typehints",
]
all = ["mypackage[dev,docs]"]

# Entry points: creates executable commands on install
[project.scripts]
# This creates a 'mypackage' command that calls cli:main
mypackage = "mypackage.cli:main"

# Plugin entry points for extensibility
[project.entry-points."mypackage.plugins"]
default = "mypackage.core:DefaultPlugin"

[project.urls]
Homepage = "https://github.com/alice/mypackage"
Documentation = "https://mypackage.readthedocs.io"
Repository = "https://github.com/alice/mypackage"
Issues = "https://github.com/alice/mypackage/issues"

# --- Build configuration ---
[tool.hatch.version]
source = "vcs"  # Version from git tags (e.g., v1.2.3 -> 1.2.3)

[tool.hatch.build.targets.wheel]
packages = ["src/mypackage"]

# --- Tool configurations (all in one file!) ---
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
addopts = "--strict-markers --tb=short -q"
markers = [
    "slow: marks tests as slow (deselect with '-m not slow')",
    "integration: marks integration tests",
]

[tool.mypy]
python_version = "3.10"
strict = true
warn_return_any = true
warn_unused_configs = true

[tool.ruff]
target-version = "py310"
line-length = 88

[tool.ruff.lint]
select = ["E", "F", "I", "N", "UP", "B", "SIM", "TCH"]

[tool.coverage.run]
source = ["mypackage"]
branch = true

[tool.coverage.report]
fail_under = 85
show_missing = true
exclude_lines = [
    "pragma: no cover",
    "if TYPE_CHECKING:",
    "if __name__ == .__main__.",
]
```

## Building a CLI with Click

Entry points in `pyproject.toml` create executable commands, but you need a CLI
framework to handle argument parsing, help text, and subcommands. Click is the
best practice for production CLIs because it is composable and well-tested.

```python
# CLI module for mypackage -- registered as entry point in pyproject.toml.
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from mypackage.core import process_data, DataConfig


console = Console()


@click.group()
@click.version_option()
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
@click.pass_context
def main(ctx: click.Context, verbose: bool) -> None:
    # MyPackage: A production data processing tool.
    # This CLI demonstrates the correct way to structure a click
    # application with subcommands, shared context, and proper
    # error handling.
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose


@main.command()
@click.argument("input_file", type=click.Path(exists=True, path_type=Path))
@click.option("--output", "-o", type=click.Path(path_type=Path), default=None)
@click.option("--format", "fmt", type=click.Choice(["json", "csv"]), default="json")
@click.option("--workers", "-w", type=int, default=4, help="Number of workers")
@click.pass_context
def process(
    ctx: click.Context,
    input_file: Path,
    output: Path | None,
    fmt: str,
    workers: int,
) -> None:
    # Process a data file with configurable output format.
    # Because click handles argument validation and type conversion,
    # we can focus on business logic. The trade-off vs argparse is
    # that click requires a dependency, but the API is significantly
    # cleaner for complex CLIs.
    verbose = ctx.obj["verbose"]

    try:
        config = DataConfig(workers=workers, output_format=fmt)
        if verbose:
            console.print(f"[blue]Processing {input_file} with {workers} workers[/]")

        result = process_data(input_file, config)

        output_path = output or input_file.with_suffix(f".{fmt}")
        output_path.write_text(json.dumps(result, indent=2))

        console.print(f"[green]Output written to {output_path}[/]")

    except FileNotFoundError as exc:
        console.print(f"[red]Error: {exc}[/]")
        sys.exit(1)
    except ValueError as exc:
        console.print(f"[red]Validation error: {exc}[/]")
        sys.exit(2)


@main.command()
@click.option("--format", "fmt", type=click.Choice(["table", "json"]), default="table")
def status(fmt: str) -> None:
    # Show current processing status.
    status_data: dict[str, Any] = {
        "version": "1.0.0",
        "active_jobs": 0,
        "queue_size": 0,
    }
    if fmt == "json":
        click.echo(json.dumps(status_data, indent=2))
    else:
        table = Table(title="Status")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")
        for key, value in status_data.items():
            table.add_row(key, str(value))
        console.print(table)
```

## Testing the CLI and Package

```python
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from click.testing import CliRunner

from mypackage.cli import main


@pytest.fixture
def runner() -> CliRunner:
    # Click test runner with isolated filesystem.
    return CliRunner()


@pytest.fixture
def sample_input(tmp_path: Path) -> Path:
    # Create a sample input file for testing.
    input_file = tmp_path / "data.json"
    input_file.write_text(json.dumps({"records": [1, 2, 3]}))
    return input_file


class TestCLI:
    # Test suite for the mypackage CLI.

    def test_version_flag(self, runner: CliRunner) -> None:
        # Test that --version outputs version info.
        result = runner.invoke(main, ["--version"])
        assert result.exit_code == 0

    def test_help_shows_subcommands(self, runner: CliRunner) -> None:
        # Test that help lists available subcommands.
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "process" in result.output
        assert "status" in result.output

    def test_process_command_creates_output(
        self, runner: CliRunner, sample_input: Path, tmp_path: Path,
    ) -> None:
        # Test that process creates an output file.
        output = tmp_path / "output.json"
        with patch("mypackage.cli.process_data") as mock_process:
            mock_process.return_value = {"result": "ok"}
            result = runner.invoke(
                main, ["process", str(sample_input), "-o", str(output)]
            )
        assert result.exit_code == 0
        assert output.exists()

    def test_process_missing_file(self, runner: CliRunner) -> None:
        # Test error handling for missing input file.
        result = runner.invoke(main, ["process", "/nonexistent/file.json"])
        assert result.exit_code != 0

    def test_status_json_format(self, runner: CliRunner) -> None:
        # Test status command with JSON output.
        result = runner.invoke(main, ["status", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "version" in data

    @pytest.mark.parametrize(
        "fmt,expected_text",
        [
            ("json", '"version"'),
            ("table", "Status"),
        ],
        ids=["json_format", "table_format"],
    )
    def test_status_output_formats(
        self, runner: CliRunner, fmt: str, expected_text: str,
    ) -> None:
        # Test that both output formats work correctly.
        result = runner.invoke(main, ["status", "--format", fmt])
        assert result.exit_code == 0
        assert expected_text in result.output
```

## Publishing to PyPI with Trusted Publishing

The modern best practice is **trusted publishing** via GitHub Actions, which eliminates
the need to manage API tokens. PyPI verifies the GitHub repository and workflow identity
directly through OpenID Connect. This is more secure than storing API tokens as secrets
because there are no long-lived credentials that can be leaked.

```yaml
# .github/workflows/publish.yml
name: Publish to PyPI
on:
  release:
    types: [published]

permissions:
  id-token: write  # Required for trusted publishing

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0  # Full history needed for hatch-vcs

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install build tools
        run: pip install build

      - name: Build package
        run: python -m build

      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
        # No token needed -- uses trusted publishing via OIDC
```

## Common Pitfalls and Best Practices

- **Anti-pattern**: Using `setup.py` for new projects. Always use `pyproject.toml` -- it is the standard since PEP 621 and all modern tools support it.
- **Common mistake**: Flat layout with `import mypackage` working locally but failing after `pip install` because `__init__.py` or data files were not included in the package manifest.
- **Pitfall**: Pinning exact versions in library dependencies (e.g., `requests==2.31.0`). Libraries should use compatible ranges (`requests>=2.25`). Only applications should pin exact versions (via lock files).
- **Avoid**: Publishing without a `py.typed` marker if your package has type hints. Without it, mypy and other type checkers cannot use your annotations.
- **Performance tip**: Use `hatchling` or `flit` for pure Python packages -- they are faster than `setuptools` because they skip the legacy build machinery.
- **Production consideration**: Always set `fail_under` in your coverage config to prevent test coverage from silently degrading. A threshold of 85% is a good starting point for most projects.
- **Best practice for versioning**: Use `hatch-vcs` or `setuptools-scm` to derive the version from git tags. This means you never manually edit a version string -- you just create a git tag like `v1.2.3` and the build system picks it up automatically.

## Key Takeaways

- **`pyproject.toml` is the single source of truth** for modern Python packaging -- metadata, dependencies, tool config, and build settings all live in one file
- **Use src layout** for distributable packages to prevent the pitfall of importing unpackaged local code during testing
- **Entry points** (`[project.scripts]`) create installable CLI commands -- combine with Click or Typer for production CLIs
- **Hatchling with hatch-vcs** provides zero-config versioning from git tags -- no manual version bumps needed
- **Trusted publishing** via GitHub Actions OIDC eliminates API token management for PyPI releases; this is more secure at scale because there are no long-lived secrets
- **Use extras** (`[project.optional-dependencies]`) to separate dev/docs/test dependencies from core requirements -- this keeps production installs lean
- **Test CLIs with `CliRunner`** from Click's testing module -- it provides isolated filesystem and captured output without spawning subprocesses
""",
    ),
]
