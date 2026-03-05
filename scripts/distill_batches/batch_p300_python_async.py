"""Python async: asyncio patterns, task groups, structured concurrency, async generators, async context managers."""

PAIRS = [
    (
        "python/async/task-groups-structured-concurrency",
        "How do I use Python 3.11+ TaskGroups for structured concurrency? Show real-world patterns for parallel API calls with error handling, cancellation, and result collection.",
        '''Python 3.11 introduced `asyncio.TaskGroup` for structured concurrency — guaranteeing that all spawned tasks complete (or are cancelled) before the block exits. This replaces the older `asyncio.gather` pattern with safer semantics.

```python
"""Structured concurrency with TaskGroup — parallel API calls with
error handling, cancellation, retries, and result collection."""

from __future__ import annotations

import asyncio
import logging
import random
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class APIResult:
    """Encapsulates the outcome of a single API call."""
    url: str
    status: int
    body: dict[str, Any]
    elapsed_ms: float


@dataclass
class BatchResult:
    """Aggregates results and errors from a batch of parallel calls."""
    successes: list[APIResult] = field(default_factory=list)
    failures: list[tuple[str, Exception]] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return len(self.failures) == 0


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------
async def fetch_with_retry(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_retries: int = 3,
    backoff_base: float = 0.5,
) -> APIResult:
    """Fetch a URL with exponential backoff + jitter."""
    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = await client.get(url, timeout=10.0)
            resp.raise_for_status()
            return APIResult(
                url=url,
                status=resp.status_code,
                body=resp.json(),
                elapsed_ms=resp.elapsed.total_seconds() * 1000,
            )
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = backoff_base * (2 ** (attempt - 1)) + random.uniform(0, 0.3)
                logger.warning("Retry %d/%d for %s: %s", attempt, max_retries, url, exc)
                await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Core pattern: TaskGroup with result collection
# ---------------------------------------------------------------------------
async def fetch_all(urls: list[str]) -> BatchResult:
    """Fetch many URLs in parallel using structured concurrency.

    Key behaviours:
    - All tasks run inside a TaskGroup scope.
    - If *any* task raises an unhandled exception the group cancels the rest
      and re-raises as an ExceptionGroup.
    - We catch per-task exceptions so the group does NOT cancel siblings.
    """
    result = BatchResult()

    async def _guarded_fetch(client: httpx.AsyncClient, url: str) -> None:
        """Wraps a single fetch so exceptions are captured, not propagated."""
        try:
            api_result = await fetch_with_retry(client, url)
            result.successes.append(api_result)
        except Exception as exc:
            logger.error("Failed to fetch %s: %s", url, exc)
            result.failures.append((url, exc))

    async with httpx.AsyncClient() as client:
        async with asyncio.TaskGroup() as tg:
            for url in urls:
                tg.create_task(_guarded_fetch(client, url))

    return result


# ---------------------------------------------------------------------------
# Cancellation-aware variant: first-N-wins pattern
# ---------------------------------------------------------------------------
async def fetch_first_n(
    urls: list[str],
    n: int,
) -> list[APIResult]:
    """Return as soon as *n* URLs respond successfully, cancel the rest."""
    results: list[APIResult] = []
    done_event = asyncio.Event()

    async def _race_fetch(client: httpx.AsyncClient, url: str) -> None:
        if done_event.is_set():
            return
        try:
            api_result = await fetch_with_retry(client, url, max_retries=1)
            results.append(api_result)
            if len(results) >= n:
                done_event.set()
        except Exception:
            pass  # losers silently ignored

    async with httpx.AsyncClient() as client:
        try:
            async with asyncio.TaskGroup() as tg:
                for url in urls:
                    tg.create_task(_race_fetch(client, url))
                # Monitor completion
                tg.create_task(_wait_and_cancel(done_event, tg))
        except* asyncio.CancelledError:
            pass  # expected when we cancel remaining tasks

    return results[:n]


async def _wait_and_cancel(event: asyncio.Event, tg: asyncio.TaskGroup) -> None:
    """Wait for the done signal, then cancel the task group."""
    await event.wait()
    raise asyncio.CancelledError  # propagates to cancel siblings


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
async def main() -> None:
    urls = [
        "https://httpbin.org/delay/1",
        "https://httpbin.org/delay/2",
        "https://httpbin.org/status/500",  # will fail
        "https://httpbin.org/get",
        "https://httpbin.org/delay/3",
    ]

    batch = await fetch_all(urls)
    print(f"Successes: {len(batch.successes)}, Failures: {len(batch.failures)}")

    first_two = await fetch_first_n(urls, n=2)
    print(f"First 2 results: {[r.url for r in first_two]}")


if __name__ == "__main__":
    asyncio.run(main())
```

**Comparison: `asyncio.gather` vs `TaskGroup`**

| Feature | `asyncio.gather` | `asyncio.TaskGroup` |
|---|---|---|
| Cancellation on error | Only with `return_exceptions=False` | Automatic — all siblings cancelled |
| Exception type | Single exception or list | `ExceptionGroup` (PEP 654) |
| Scope guarantee | None — tasks can outlive caller | Tasks cannot outlive the `async with` block |
| Nested groups | Manual | Natural nesting |
| Python version | 3.4+ | 3.11+ |

**Key patterns:**

- **Guarded tasks** — catch exceptions inside each task so one failure does not cancel siblings
- **First-N-wins** — set an event when enough results arrive, then cancel remaining via `CancelledError`
- **Retry with backoff** — exponential backoff + jitter prevents thundering herd
- **Result aggregation** — use a shared mutable container (`BatchResult`) passed via closure
- **Exception groups** — use `except*` syntax to handle `ExceptionGroup` from TaskGroup failures'''
    ),
    (
        "python/async/generators-streaming",
        "Show me how to build async generators in Python for streaming data processing — including backpressure, chunked iteration, and fan-out patterns.",
        '''Async generators (`async def ... yield`) are the backbone of streaming data pipelines in Python. They let you lazily produce values without buffering entire datasets in memory.

```python
"""Async generators for streaming data — backpressure, chunking,
fan-out, and composable pipeline stages."""

from __future__ import annotations

import asyncio
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Stage 1: Source — async generator that produces records
# ---------------------------------------------------------------------------
async def read_events(
    source_url: str,
    *,
    batch_size: int = 100,
) -> AsyncIterator[dict]:
    """Simulate reading events from an external source.

    In production this would be an SSE stream, Kafka consumer, or
    database cursor.
    """
    event_id = 0
    while True:
        # Simulate network fetch
        await asyncio.sleep(0.01)
        for _ in range(batch_size):
            event_id += 1
            yield {
                "id": event_id,
                "source": source_url,
                "timestamp": time.time(),
                "payload": f"data-{event_id}",
            }
        if event_id >= 1000:
            break  # finite for demo


# ---------------------------------------------------------------------------
# Stage 2: Transform — async generator that filters and maps
# ---------------------------------------------------------------------------
async def enrich_events(
    events: AsyncIterator[dict],
    *,
    enrichment_delay: float = 0.001,
) -> AsyncIterator[dict]:
    """Enrich each event (e.g., lookup user, geo-decode IP)."""
    async for event in events:
        await asyncio.sleep(enrichment_delay)  # simulate IO
        event["enriched"] = True
        event["processed_at"] = time.time()
        yield event


# ---------------------------------------------------------------------------
# Stage 3: Chunk — collect into fixed-size batches
# ---------------------------------------------------------------------------
async def chunk(
    source: AsyncIterator[T],
    size: int = 50,
) -> AsyncIterator[list[T]]:
    """Yield lists of up to *size* items from the source.

    This is critical for batched writes (e.g., bulk INSERT, S3 upload).
    """
    buffer: list[T] = []
    async for item in source:
        buffer.append(item)
        if len(buffer) >= size:
            yield buffer
            buffer = []
    if buffer:
        yield buffer


# ---------------------------------------------------------------------------
# Stage 4: Sink — consume batches with backpressure
# ---------------------------------------------------------------------------
@dataclass
class WriteStats:
    batches_written: int = 0
    records_written: int = 0
    total_latency_ms: float = 0.0


async def write_batches(
    batches: AsyncIterator[list[dict]],
    *,
    max_concurrent: int = 5,
) -> WriteStats:
    """Write batches with bounded concurrency (backpressure).

    Uses a semaphore so at most *max_concurrent* writes happen in parallel.
    """
    sem = asyncio.Semaphore(max_concurrent)
    stats = WriteStats()

    async def _write_one(batch: list[dict]) -> None:
        async with sem:
            # Simulate a database / API write
            await asyncio.sleep(0.02)
            stats.batches_written += 1
            stats.records_written += len(batch)

    async with asyncio.TaskGroup() as tg:
        async for batch in batches:
            tg.create_task(_write_one(batch))

    return stats


# ---------------------------------------------------------------------------
# Fan-out: duplicate an async iterator to multiple consumers
# ---------------------------------------------------------------------------
async def fan_out(
    source: AsyncIterator[T],
    n: int,
    buffer_size: int = 64,
) -> list[asyncio.Queue[T | None]]:
    """Broadcast items from *source* to *n* queues.

    Each consumer gets its own queue. A sentinel `None` signals completion.
    """
    queues: list[asyncio.Queue[T | None]] = [
        asyncio.Queue(maxsize=buffer_size) for _ in range(n)
    ]

    async def _broadcast() -> None:
        async for item in source:
            for q in queues:
                await q.put(item)  # blocks if full → backpressure
        for q in queues:
            await q.put(None)  # sentinel

    asyncio.create_task(_broadcast())
    return queues


async def queue_to_aiter(q: asyncio.Queue[T | None]) -> AsyncIterator[T]:
    """Wrap an asyncio.Queue as an async iterator (stops on None sentinel)."""
    while True:
        item = await q.get()
        if item is None:
            break
        yield item


# ---------------------------------------------------------------------------
# Compose the full pipeline
# ---------------------------------------------------------------------------
async def run_pipeline() -> None:
    """Assemble a streaming pipeline: source → enrich → chunk → sink."""
    source = read_events("https://events.example.com/stream")
    enriched = enrich_events(source)
    batches = chunk(enriched, size=50)
    stats = await write_batches(batches, max_concurrent=5)

    print(
        f"Wrote {stats.records_written} records in "
        f"{stats.batches_written} batches"
    )


async def run_fan_out_demo() -> None:
    """Fan-out demo: one source feeds two independent consumers."""
    source = read_events("https://events.example.com/stream")
    queues = await fan_out(source, n=2, buffer_size=32)

    async def consumer(name: str, q: asyncio.Queue) -> None:
        count = 0
        async for item in queue_to_aiter(q):
            count += 1
        print(f"Consumer {name} processed {count} events")

    async with asyncio.TaskGroup() as tg:
        tg.create_task(consumer("analytics", queues[0]))
        tg.create_task(consumer("archive", queues[1]))


if __name__ == "__main__":
    asyncio.run(run_pipeline())
```

**Key patterns:**

- **Lazy evaluation** — async generators only produce the next item when the consumer asks, keeping memory constant
- **Chunking** — `chunk()` collects items into batches before a bulk write, amortizing IO overhead
- **Backpressure via semaphore** — `asyncio.Semaphore(max_concurrent)` bounds how many writes run in parallel, preventing overload
- **Fan-out with queues** — `asyncio.Queue(maxsize=N)` naturally applies backpressure: producers block when the queue is full
- **Composable stages** — each function takes an `AsyncIterator` and yields an `AsyncIterator`, making the pipeline easy to extend
- **Sentinel-based termination** — `None` signals "no more items" through queues, cleanly shutting down consumers'''
    ),
    (
        "python/async/context-managers",
        "How should I build async context managers in Python? Show patterns for resource management, connection pools, and lifecycle management.",
        '''Async context managers (`async with`) are essential for managing resources that require asynchronous setup and teardown — database connections, HTTP clients, locks, and service lifecycles.

```python
"""Async context managers — resource pools, lifecycle management,
and composable resource patterns."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Self

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pattern 1: Class-based async context manager (connection pool)
# ---------------------------------------------------------------------------
@dataclass
class Connection:
    """Simulated database connection."""
    id: int
    created_at: float = field(default_factory=time.time)
    _closed: bool = field(default=False, repr=False)

    async def execute(self, query: str, params: tuple = ()) -> list[dict]:
        if self._closed:
            raise RuntimeError("Connection is closed")
        await asyncio.sleep(0.01)  # simulate query
        return [{"result": f"data from conn-{self.id}"}]

    async def close(self) -> None:
        self._closed = True
        await asyncio.sleep(0.001)


class ConnectionPool:
    """Async connection pool with bounded size and health checks.

    Usage:
        async with ConnectionPool(dsn="...", min_size=2, max_size=10) as pool:
            async with pool.acquire() as conn:
                rows = await conn.execute("SELECT ...")
    """

    def __init__(
        self,
        dsn: str,
        *,
        min_size: int = 2,
        max_size: int = 10,
        max_idle_seconds: float = 300.0,
    ) -> None:
        self.dsn = dsn
        self.min_size = min_size
        self.max_size = max_size
        self.max_idle_seconds = max_idle_seconds
        self._pool: asyncio.Queue[Connection] = asyncio.Queue(maxsize=max_size)
        self._size = 0
        self._lock = asyncio.Lock()
        self._closed = False
        self._next_id = 0

    async def __aenter__(self) -> Self:
        """Warm up the pool with min_size connections."""
        for _ in range(self.min_size):
            conn = await self._create_connection()
            await self._pool.put(conn)
        logger.info("Pool started with %d connections", self.min_size)
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        """Drain and close all connections."""
        self._closed = True
        while not self._pool.empty():
            conn = self._pool.get_nowait()
            await conn.close()
        logger.info("Pool shut down, all connections closed")

    async def _create_connection(self) -> Connection:
        self._next_id += 1
        self._size += 1
        await asyncio.sleep(0.01)  # simulate connect
        return Connection(id=self._next_id)

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[Connection]:
        """Acquire a connection; return it to the pool on exit."""
        if self._closed:
            raise RuntimeError("Pool is closed")

        conn: Connection | None = None
        try:
            conn = self._pool.get_nowait()
        except asyncio.QueueEmpty:
            async with self._lock:
                if self._size < self.max_size:
                    conn = await self._create_connection()
        if conn is None:
            # All connections in use and at max — wait for one
            conn = await self._pool.get()

        try:
            yield conn
        except Exception:
            # Connection might be in a bad state — close and replace
            await conn.close()
            self._size -= 1
            raise
        else:
            # Return healthy connection to pool
            if not self._closed:
                await self._pool.put(conn)


# ---------------------------------------------------------------------------
# Pattern 2: Function-based with @asynccontextmanager
# ---------------------------------------------------------------------------
@asynccontextmanager
async def managed_http_client(
    base_url: str,
    *,
    timeout: float = 30.0,
    max_connections: int = 100,
) -> AsyncIterator[dict]:
    """Provide a configured HTTP client with automatic cleanup.

    Demonstrates the @asynccontextmanager decorator pattern.
    """
    import httpx

    transport = httpx.AsyncHTTPTransport(
        retries=2,
        limits=httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=20,
        ),
    )
    client = httpx.AsyncClient(
        base_url=base_url,
        timeout=timeout,
        transport=transport,
    )
    logger.info("HTTP client created for %s", base_url)
    try:
        yield client  # type: ignore[arg-type]
    finally:
        await client.aclose()
        logger.info("HTTP client closed")


# ---------------------------------------------------------------------------
# Pattern 3: Composable service lifecycle
# ---------------------------------------------------------------------------
class ServiceLifecycle:
    """Manage multiple async resources with ordered startup/shutdown.

    Usage:
        lifecycle = ServiceLifecycle()
        lifecycle.add("database", db_pool_context)
        lifecycle.add("cache", redis_context)
        lifecycle.add("http", http_client_context)

        async with lifecycle as services:
            db = services["database"]
            cache = services["cache"]
    """

    def __init__(self) -> None:
        self._factories: list[tuple[str, Any]] = []
        self._instances: dict[str, Any] = {}
        self._stack: list[tuple[str, Any]] = []

    def add(self, name: str, context_manager_factory: Any) -> Self:
        self._factories.append((name, context_manager_factory))
        return self

    async def __aenter__(self) -> dict[str, Any]:
        for name, factory in self._factories:
            ctx = factory()
            instance = await ctx.__aenter__()
            self._stack.append((name, ctx))
            self._instances[name] = instance
            logger.info("Started service: %s", name)
        return self._instances

    async def __aexit__(self, *exc_info: Any) -> None:
        # Shutdown in reverse order
        errors: list[Exception] = []
        for name, ctx in reversed(self._stack):
            try:
                await ctx.__aexit__(*exc_info)
                logger.info("Stopped service: %s", name)
            except Exception as e:
                errors.append(e)
                logger.error("Error stopping %s: %s", name, e)
        self._stack.clear()
        self._instances.clear()
        if errors:
            raise ExceptionGroup("Service shutdown errors", errors)


# ---------------------------------------------------------------------------
# Usage example
# ---------------------------------------------------------------------------
async def main() -> None:
    # Direct pool usage
    async with ConnectionPool("postgres://localhost/mydb", min_size=2, max_size=5) as pool:
        async with pool.acquire() as conn:
            rows = await conn.execute("SELECT 1")
            print(f"Query result: {rows}")

        # Parallel queries
        async with asyncio.TaskGroup() as tg:
            async def query(q: str) -> None:
                async with pool.acquire() as c:
                    result = await c.execute(q)
                    print(f"{q}: {result}")

            for i in range(5):
                tg.create_task(query(f"SELECT {i}"))


if __name__ == "__main__":
    asyncio.run(main())
```

**Key patterns:**

- **Class-based** (`__aenter__` / `__aexit__`) — best for stateful resources like connection pools that need internal bookkeeping
- **Decorator-based** (`@asynccontextmanager`) — concise for simple setup/teardown; uses `try/finally` around a `yield`
- **Composable lifecycle** — `ServiceLifecycle` starts services in order and shuts them down in reverse, collecting errors into an `ExceptionGroup`
- **Connection pool** — uses `asyncio.Queue` for thread-safe checkout/return and `asyncio.Lock` for size management
- **Nested contexts** — `pool.acquire()` is itself an async context manager nested inside the pool context, showing how resources compose naturally'''
    ),
    (
        "python/async/synchronization-primitives",
        "What synchronization primitives does asyncio provide and when should I use each one? Show practical examples of Lock, Semaphore, Event, Condition, and Barrier.",
        '''asyncio provides cooperative synchronization primitives that work with the event loop — they never block the thread, only suspend the current coroutine. Here is a comprehensive guide with production examples.

```python
"""asyncio synchronization primitives — Lock, Semaphore, Event,
Condition, Barrier with practical use cases."""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections import deque
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 1. Lock — mutual exclusion for shared mutable state
# ---------------------------------------------------------------------------
class RateLimiter:
    """Token-bucket rate limiter using asyncio.Lock.

    Only one coroutine refills the bucket at a time.
    """

    def __init__(self, rate: float, burst: int = 10) -> None:
        self.rate = rate            # tokens per second
        self.burst = burst          # max tokens
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(self.burst, self._tokens + elapsed * self.rate)
                self._last_refill = now
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
            # No token available — yield and retry
            await asyncio.sleep(1.0 / self.rate)


# ---------------------------------------------------------------------------
# 2. Semaphore — bounded concurrency
# ---------------------------------------------------------------------------
async def crawl_urls(urls: list[str], max_concurrent: int = 10) -> list[str]:
    """Crawl URLs with bounded concurrency using Semaphore."""
    sem = asyncio.Semaphore(max_concurrent)
    results: list[str] = []

    async def _fetch(url: str) -> None:
        async with sem:
            logger.info("Fetching %s (active slots: %d/%d)",
                        url, max_concurrent - sem._value, max_concurrent)
            await asyncio.sleep(random.uniform(0.1, 0.5))  # simulate IO
            results.append(f"content-of-{url}")

    async with asyncio.TaskGroup() as tg:
        for url in urls:
            tg.create_task(_fetch(url))

    return results


# ---------------------------------------------------------------------------
# 3. Event — one-shot signal between coroutines
# ---------------------------------------------------------------------------
class GracefulShutdown:
    """Coordinate graceful shutdown across multiple workers using Event."""

    def __init__(self) -> None:
        self._shutdown_event = asyncio.Event()
        self._workers_done = asyncio.Event()
        self._active_workers = 0
        self._lock = asyncio.Lock()

    def request_shutdown(self) -> None:
        logger.info("Shutdown requested")
        self._shutdown_event.set()

    @property
    def is_shutting_down(self) -> bool:
        return self._shutdown_event.is_set()

    async def run_worker(self, name: str) -> None:
        async with self._lock:
            self._active_workers += 1

        try:
            while not self._shutdown_event.is_set():
                # Do work
                logger.info("Worker %s processing...", name)
                try:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=1.0,  # check every second
                    )
                except asyncio.TimeoutError:
                    pass  # continue working
        finally:
            async with self._lock:
                self._active_workers -= 1
                if self._active_workers == 0:
                    self._workers_done.set()
            logger.info("Worker %s stopped", name)

    async def wait_for_workers(self) -> None:
        await self._workers_done.wait()
        logger.info("All workers stopped")


# ---------------------------------------------------------------------------
# 4. Condition — producer/consumer with complex predicates
# ---------------------------------------------------------------------------
@dataclass
class BoundedBuffer:
    """Thread-safe bounded buffer using asyncio.Condition.

    Producers wait when buffer is full, consumers wait when empty.
    """
    capacity: int = 10
    _buffer: deque = field(default_factory=deque)
    _condition: asyncio.Condition = field(default_factory=asyncio.Condition)
    _closed: bool = False

    async def put(self, item: object) -> None:
        async with self._condition:
            while len(self._buffer) >= self.capacity:
                await self._condition.wait()
            self._buffer.append(item)
            self._condition.notify()  # wake one consumer

    async def get(self) -> object:
        async with self._condition:
            while len(self._buffer) == 0 and not self._closed:
                await self._condition.wait()
            if self._buffer:
                item = self._buffer.popleft()
                self._condition.notify()  # wake one producer
                return item
            raise StopAsyncIteration("Buffer closed and empty")

    async def close(self) -> None:
        async with self._condition:
            self._closed = True
            self._condition.notify_all()


# ---------------------------------------------------------------------------
# 5. Barrier — synchronize N coroutines at a rendezvous point
# ---------------------------------------------------------------------------
async def parallel_phase_computation(n_workers: int = 4) -> None:
    """Multi-phase computation where all workers must finish each phase
    before any can proceed to the next."""
    barrier = asyncio.Barrier(n_workers)

    async def worker(worker_id: int) -> None:
        for phase in range(3):
            # Phase work
            work_time = random.uniform(0.1, 0.5)
            await asyncio.sleep(work_time)
            logger.info("Worker %d finished phase %d (%.2fs)",
                        worker_id, phase, work_time)

            # Wait for all workers at the barrier
            await barrier.wait()
            logger.info("Worker %d passed barrier for phase %d",
                        worker_id, phase)

    async with asyncio.TaskGroup() as tg:
        for i in range(n_workers):
            tg.create_task(worker(i))

    print("All phases complete")


# ---------------------------------------------------------------------------
# Demo runner
# ---------------------------------------------------------------------------
async def main() -> None:
    # Rate limiter demo
    limiter = RateLimiter(rate=5.0, burst=3)
    t0 = time.monotonic()
    for i in range(6):
        await limiter.acquire()
        print(f"Request {i} at t={time.monotonic()-t0:.2f}s")

    # Bounded concurrency crawl
    urls = [f"https://example.com/page/{i}" for i in range(20)]
    pages = await crawl_urls(urls, max_concurrent=5)
    print(f"Crawled {len(pages)} pages")

    # Barrier
    await parallel_phase_computation(n_workers=4)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
```

**Comparison table:**

| Primitive | Purpose | Blocks when | Wakes when |
|---|---|---|---|
| `Lock` | Mutual exclusion | Another coro holds the lock | Lock is released |
| `Semaphore` | Bounded concurrency | Counter reaches 0 | A holder releases |
| `Event` | One-shot signal | `wait()` before `set()` | `set()` is called |
| `Condition` | Complex predicates | Predicate is false | `notify()` / `notify_all()` |
| `Barrier` | Phase synchronization | Fewer than N arrived | All N arrive |

**Key patterns:**

- **Lock** — use for read-modify-write on shared state (e.g., token bucket refill)
- **Semaphore** — use to limit concurrent IO operations (API calls, DB connections)
- **Event** — use for signaling between coroutines (shutdown signals, readiness checks)
- **Condition** — use for producer/consumer patterns with complex wait predicates
- **Barrier** — use for phased parallel computation where all workers must sync between phases
- All primitives are **non-blocking** — they suspend the coroutine, not the thread'''
    ),
    (
        "python/async/exception-groups",
        "How do I handle ExceptionGroups from TaskGroup in Python 3.11+? Show patterns for except*, filtering, and converting exception groups.",
        '''Python 3.11 introduced `ExceptionGroup` and the `except*` syntax (PEP 654) specifically to handle multiple concurrent failures from `TaskGroup` and other structured concurrency patterns.

```python
"""ExceptionGroup handling — except*, filtering, flattening,
and custom exception hierarchies for concurrent code."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Custom exception hierarchy for a microservice
# ---------------------------------------------------------------------------
class ServiceError(Exception):
    """Base for all service errors."""

class TransientError(ServiceError):
    """Retryable errors (network timeout, 503, etc.)."""
    def __init__(self, message: str, *, retry_after: float = 1.0) -> None:
        super().__init__(message)
        self.retry_after = retry_after

class PermanentError(ServiceError):
    """Non-retryable errors (400, 404, auth failure)."""

class ValidationError(PermanentError):
    """Input validation failed."""
    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field

class RateLimitError(TransientError):
    """Rate limit exceeded."""
    def __init__(self, retry_after: float = 60.0) -> None:
        super().__init__("Rate limit exceeded", retry_after=retry_after)


# ---------------------------------------------------------------------------
# Pattern 1: Basic except* handling
# ---------------------------------------------------------------------------
async def handle_task_group_errors() -> None:
    """Demonstrate except* with TaskGroup failures."""
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(succeed_after(0.1))
            tg.create_task(fail_with(TransientError("timeout")))
            tg.create_task(fail_with(ValidationError("email", "invalid format")))
            tg.create_task(fail_with(RateLimitError(retry_after=30)))
    except* TransientError as eg:
        # eg is an ExceptionGroup containing ONLY TransientError instances
        for exc in eg.exceptions:
            if isinstance(exc, RateLimitError):
                logger.warning("Rate limited, retry after %.0fs", exc.retry_after)
            else:
                logger.warning("Transient error (will retry): %s", exc)
    except* ValidationError as eg:
        # Separate handler for validation errors
        fields = [exc.field for exc in eg.exceptions]
        logger.error("Validation failed for fields: %s", fields)
    except* Exception as eg:
        # Catch-all for unexpected errors
        logger.error("Unexpected errors: %s", eg.exceptions)


async def succeed_after(delay: float) -> str:
    await asyncio.sleep(delay)
    return "ok"


async def fail_with(exc: Exception) -> None:
    await asyncio.sleep(0.05)
    raise exc


# ---------------------------------------------------------------------------
# Pattern 2: ExceptionGroup filtering and transformation
# ---------------------------------------------------------------------------
@dataclass
class ErrorReport:
    """Structured error report from a batch operation."""
    retryable: list[TransientError]
    permanent: list[PermanentError]
    unexpected: list[Exception]

    @property
    def has_retryable(self) -> bool:
        return len(self.retryable) > 0

    @property
    def max_retry_after(self) -> float:
        if not self.retryable:
            return 0.0
        return max(e.retry_after for e in self.retryable)


def classify_errors(eg: ExceptionGroup) -> ErrorReport:
    """Classify errors from an ExceptionGroup into categories.

    Uses the .subgroup() method for precise filtering.
    """
    retryable_group = eg.subgroup(lambda e: isinstance(e, TransientError))
    permanent_group = eg.subgroup(lambda e: isinstance(e, PermanentError))
    unexpected_group = eg.subgroup(
        lambda e: not isinstance(e, ServiceError)
    )

    return ErrorReport(
        retryable=list(retryable_group.exceptions) if retryable_group else [],
        permanent=list(permanent_group.exceptions) if permanent_group else [],
        unexpected=list(unexpected_group.exceptions) if unexpected_group else [],
    )


# ---------------------------------------------------------------------------
# Pattern 3: Retry logic with ExceptionGroup awareness
# ---------------------------------------------------------------------------
async def run_with_retry(
    tasks: list,
    *,
    max_retries: int = 3,
) -> list:
    """Run tasks, automatically retrying those that fail with TransientError.

    Tasks that raise PermanentError are not retried.
    """
    results = [None] * len(tasks)
    pending_indices = list(range(len(tasks)))

    for attempt in range(1, max_retries + 1):
        if not pending_indices:
            break

        errors: dict[int, Exception] = {}

        async def _run(idx: int) -> None:
            try:
                results[idx] = await tasks[idx]()
            except TransientError as e:
                errors[idx] = e
            except PermanentError:
                raise  # propagate immediately

        try:
            async with asyncio.TaskGroup() as tg:
                for idx in pending_indices:
                    tg.create_task(_run(idx))
        except* PermanentError as eg:
            # Re-raise permanent errors — caller must handle
            raise

        # Retry only transient failures
        pending_indices = list(errors.keys())
        if pending_indices and attempt < max_retries:
            max_wait = max(
                (e.retry_after for e in errors.values()
                 if isinstance(e, TransientError)),
                default=1.0,
            )
            logger.info(
                "Attempt %d/%d: %d tasks failed transiently, "
                "retrying after %.1fs",
                attempt, max_retries, len(pending_indices), max_wait,
            )
            await asyncio.sleep(max_wait)

    if pending_indices:
        failed = [errors[i] for i in pending_indices if i in errors]
        raise ExceptionGroup(
            f"{len(failed)} tasks failed after {max_retries} retries",
            failed,
        )

    return results


# ---------------------------------------------------------------------------
# Pattern 4: Flattening nested ExceptionGroups
# ---------------------------------------------------------------------------
def flatten_exception_group(eg: BaseExceptionGroup) -> list[BaseException]:
    """Recursively flatten nested ExceptionGroups into a flat list."""
    result: list[BaseException] = []
    for exc in eg.exceptions:
        if isinstance(exc, BaseExceptionGroup):
            result.extend(flatten_exception_group(exc))
        else:
            result.append(exc)
    return result


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
async def main() -> None:
    # Pattern 1: basic except*
    await handle_task_group_errors()

    # Pattern 2: error classification
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(fail_with(TransientError("connect timeout")))
            tg.create_task(fail_with(RateLimitError(30)))
            tg.create_task(fail_with(ValidationError("age", "must be positive")))
            tg.create_task(fail_with(ValueError("unexpected")))
    except* Exception as eg:
        report = classify_errors(eg)  # type: ignore[arg-type]
        print(f"Retryable: {len(report.retryable)}")
        print(f"Permanent: {len(report.permanent)}")
        print(f"Unexpected: {len(report.unexpected)}")
        print(f"Max retry after: {report.max_retry_after}s")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
```

**Key patterns:**

- **`except*` handlers** — each `except*` clause matches a *subgroup* of the `ExceptionGroup`; multiple `except*` clauses can fire for the same group
- **`ExceptionGroup.subgroup(predicate)`** — returns a new `ExceptionGroup` containing only exceptions matching the predicate, or `None`
- **Error classification** — use `subgroup()` to split errors into retryable vs permanent categories
- **Retry with ExceptionGroup** — catch transient errors, re-raise permanent ones, and retry only the failed tasks
- **Flattening** — recursively unwrap nested `ExceptionGroup`s from nested `TaskGroup`s into a flat list for logging or reporting
- **Custom hierarchy** — define `TransientError` vs `PermanentError` base classes so `except*` handlers can cleanly separate them'''
    ),
]
