PAIRS = [
    (
        "python/async-await-deep-dive",
        r"""Explain Python's async/await internals including the event loop architecture, coroutine lifecycle, task scheduling, how asyncio handles I/O multiplexing with selectors, and common pitfalls like blocking the event loop. Include practical patterns for structured concurrency.""",
        r"""## Python Async/Await Internals: Event Loop, Coroutines, and Structured Concurrency

Python's `async`/`await` syntax is built on top of **coroutines** — generator-like objects that can be suspended and resumed. Understanding the machinery beneath the syntax is essential for writing correct, performant async code.

### The Event Loop Architecture

The event loop is a **single-threaded** scheduler that multiplexes I/O operations using OS-level primitives (`epoll` on Linux, `kqueue` on macOS, `IOCP` on Windows). It runs in a loop:

1. Check for ready I/O events (non-blocking poll)
2. Execute callbacks for completed I/O
3. Run scheduled coroutines/tasks
4. Sleep until next event if nothing is ready

```python
import asyncio
import selectors
import time
from collections import deque
from typing import Coroutine, Any


class MiniEventLoop:
    """Simplified event loop showing core scheduling mechanics."""

    def __init__(self):
        self._ready: deque = deque()  # Callbacks ready to run
        self._selector = selectors.DefaultSelector()
        self._stopping = False

    def call_soon(self, callback, *args):
        """Schedule a callback to run on the next iteration."""
        self._ready.append((callback, args))

    def run_until_complete(self, coro: Coroutine) -> Any:
        """Run a coroutine to completion."""
        task = Task(coro, self)
        task._step()

        while self._ready or self._selector.get_map():
            # Phase 1: Run all ready callbacks
            while self._ready:
                callback, args = self._ready.popleft()
                callback(*args)

            # Phase 2: Poll for I/O events (with timeout)
            if self._selector.get_map():
                events = self._selector.select(timeout=0.01)
                for key, mask in events:
                    callback = key.data
                    self._selector.unregister(key.fileobj)
                    self._ready.append((callback, ()))

        return task._result


class Task:
    """Wraps a coroutine into a schedulable unit."""

    def __init__(self, coro, loop):
        self._coro = coro
        self._loop = loop
        self._result = None
        self._exception = None
        self._callbacks = []

    def _step(self, value=None):
        try:
            # Send a value into the coroutine to advance it
            result = self._coro.send(value)
            # The coroutine yielded a future — wait for it
            if isinstance(result, asyncio.Future):
                result.add_done_callback(self._wakeup)
            else:
                # Re-schedule immediately
                self._loop.call_soon(self._step)
        except StopIteration as e:
            self._result = e.value
            for cb in self._callbacks:
                self._loop.call_soon(cb, self)

    def _wakeup(self, future):
        self._loop.call_soon(self._step, future.result())
```

### Coroutine Lifecycle

A coroutine goes through distinct states:

```python
async def example():
    await asyncio.sleep(1)
    return 42

# 1. CREATED: calling async function returns coroutine object
coro = example()  # Nothing executes yet!

# 2. RUNNING: event loop sends None to start execution
# Internally: coro.send(None)

# 3. SUSPENDED: coroutine hits await, yields control back
# The awaited object (sleep future) is registered with event loop

# 4. RUNNING AGAIN: event loop resumes when future completes
# coro.send(result_of_awaited_thing)

# 5. COMPLETED: StopIteration raised with return value
```

**Critical insight**: `await` does NOT mean "wait here." It means "suspend this coroutine and let the event loop run other things until this result is ready." If the awaited thing is already complete, execution continues immediately without suspension.

### I/O Multiplexing with Selectors

The real power of async comes from non-blocking I/O. Here's how a TCP connection works under the hood:

```python
import socket


async def fetch_url(host: str, port: int, path: str) -> str:
    """Async HTTP GET showing how I/O multiplexing works."""
    loop = asyncio.get_event_loop()

    # Create non-blocking socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setblocking(False)

    # Connect asynchronously — the event loop registers the socket
    # with epoll/kqueue and suspends this coroutine until connected
    await loop.sock_connect(sock, (host, port))

    # Under the hood, loop.sock_connect does:
    # 1. Try connect() — gets EINPROGRESS (non-blocking)
    # 2. Register socket with selector for WRITE readiness
    # 3. Create a Future, suspend coroutine
    # 4. When selector says socket is writable, connection is done
    # 5. Resolve the Future, resume coroutine

    request = f"GET {path} HTTP/1.1\r\nHost: {host}\r\n\r\n"
    await loop.sock_sendall(sock, request.encode())

    # Read response in chunks
    chunks = []
    while True:
        chunk = await loop.sock_recv(sock, 4096)
        if not chunk:
            break
        chunks.append(chunk)

    sock.close()
    return b"".join(chunks).decode(errors="replace")


async def fetch_many():
    """Concurrent fetches — all sockets multiplexed on one thread."""
    tasks = [
        asyncio.create_task(fetch_url("example.com", 80, "/")),
        asyncio.create_task(fetch_url("httpbin.org", 80, "/get")),
        asyncio.create_task(fetch_url("api.github.com", 443, "/")),
    ]
    results = await asyncio.gather(*tasks)
    return results
```

### Common Pitfall: Blocking the Event Loop

The #1 async mistake is running blocking code in a coroutine:

```python
import hashlib
import asyncio
from concurrent.futures import ThreadPoolExecutor


# BAD: This blocks the entire event loop for seconds
async def bad_hash(data: bytes) -> str:
    # CPU-bound work in a coroutine — no other coroutine can run!
    return hashlib.pbkdf2_hmac("sha256", data, b"salt", 1_000_000).hex()


# GOOD: Offload CPU-bound work to a thread pool
async def good_hash(data: bytes) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,  # Default ThreadPoolExecutor
        hashlib.pbkdf2_hmac, "sha256", data, b"salt", 1_000_000
    )


# GOOD: For CPU-bound work, use ProcessPoolExecutor
_process_pool = ThreadPoolExecutor(max_workers=4)  # or ProcessPoolExecutor

async def cpu_intensive(data: bytes) -> str:
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(_process_pool, _heavy_compute, data)
    return result.hex()

def _heavy_compute(data: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", data, b"salt", 1_000_000)
```

### Structured Concurrency with TaskGroups

Python 3.11+ introduced `TaskGroup` for structured concurrency — ensuring all spawned tasks complete (or cancel) before the scope exits:

```python
import asyncio
from dataclasses import dataclass


@dataclass
class FetchResult:
    url: str
    status: int
    body: str


async def fetch_with_timeout(url: str, timeout: float = 5.0) -> FetchResult:
    """Fetch a URL with structured timeout handling."""
    async with asyncio.timeout(timeout):
        reader, writer = await asyncio.open_connection(
            url, 443, ssl=True
        )
        request = f"GET / HTTP/1.1\r\nHost: {url}\r\nConnection: close\r\n\r\n"
        writer.write(request.encode())
        await writer.drain()

        response = await reader.read(8192)
        writer.close()
        await writer.wait_closed()

        lines = response.decode(errors="replace").split("\r\n")
        status = int(lines[0].split()[1]) if lines else 0
        body = lines[-1] if lines else ""
        return FetchResult(url=url, status=status, body=body[:200])


async def fetch_all_structured(urls: list[str]) -> list[FetchResult]:
    """Structured concurrency: all tasks complete or all cancel."""
    results = []

    async with asyncio.TaskGroup() as tg:
        # All tasks are children of this group
        tasks = [
            tg.create_task(fetch_with_timeout(url))
            for url in urls
        ]
        # When we exit this block:
        # - If all succeed: results are available via task.result()
        # - If any raises: ALL other tasks are cancelled, then
        #   ExceptionGroup is raised with all failures

    # Only reached if all tasks succeeded
    results = [t.result() for t in tasks]
    return results


async def main():
    try:
        results = await fetch_all_structured([
            "example.com",
            "httpbin.org",
            "nonexistent.invalid",  # Will fail
        ])
    except* ConnectionError as eg:
        print(f"Connection failures: {len(eg.exceptions)}")
        for exc in eg.exceptions:
            print(f"  - {exc}")
    except* TimeoutError as eg:
        print(f"Timeouts: {len(eg.exceptions)}")
```

### Advanced Pattern: Async Generators and Context Managers

```python
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator


@asynccontextmanager
async def managed_connection(host: str, port: int):
    """Async context manager for connection lifecycle."""
    reader, writer = await asyncio.open_connection(host, port)
    try:
        yield reader, writer
    finally:
        writer.close()
        await writer.wait_closed()


async def stream_lines(reader: asyncio.StreamReader) -> AsyncIterator[str]:
    """Async generator that yields lines as they arrive."""
    buffer = b""
    while True:
        chunk = await reader.read(1024)
        if not chunk:
            if buffer:
                yield buffer.decode(errors="replace")
            return

        buffer += chunk
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            yield line.decode(errors="replace")


async def process_stream():
    """Consuming an async generator with backpressure."""
    async with managed_connection("stream.example.com", 8080) as (reader, _):
        line_count = 0
        async for line in stream_lines(reader):
            line_count += 1
            # Process each line without buffering everything in memory
            if line.startswith("ERROR"):
                print(f"Alert: {line}")
            if line_count % 1000 == 0:
                # Yield control periodically for fairness
                await asyncio.sleep(0)
```

**Key takeaways**: (1) async/await is cooperative multitasking — coroutines must explicitly yield control, (2) never block the event loop with CPU-bound or synchronous I/O work, (3) use `TaskGroup` for structured concurrency to prevent orphaned tasks, (4) `asyncio.sleep(0)` is a voluntary yield point for fairness in tight loops."""
    ),
    (
        "python/async-synchronization-primitives",
        r"""Explain async synchronization primitives in Python including asyncio.Lock, Semaphore, Event, Condition, and Barrier. Show when each is needed and common patterns for coordinating concurrent coroutines safely.""",
        r"""## Async Synchronization Primitives: Coordinating Concurrent Coroutines

Even though asyncio is single-threaded, you still need synchronization primitives. **Why?** Because coroutines can be suspended at any `await` point, allowing other coroutines to modify shared state in between. This creates **logical** race conditions even without thread-level parallelism.

### asyncio.Lock — Mutual Exclusion

Use when multiple coroutines must not execute a critical section simultaneously:

```python
import asyncio
from typing import Optional


class AsyncCache:
    """Thread-safe-ish async cache with lock-protected updates."""

    def __init__(self):
        self._data: dict[str, str] = {}
        self._lock = asyncio.Lock()
        self._hit = 0
        self._miss = 0

    async def get_or_fetch(self, key: str, fetcher) -> str:
        # Fast path: no lock needed for reads (single-threaded)
        if key in self._data:
            self._hit += 1
            return self._data[key]

        # Slow path: lock to prevent duplicate fetches
        async with self._lock:
            # Double-check after acquiring lock (another coroutine
            # might have fetched while we waited)
            if key in self._data:
                self._hit += 1
                return self._data[key]

            self._miss += 1
            value = await fetcher(key)
            self._data[key] = value
            return value


# Without the lock, two coroutines could both see a cache miss
# for the same key and fetch twice — wasting resources.
cache = AsyncCache()

async def expensive_fetch(key: str) -> str:
    await asyncio.sleep(1)  # Simulate slow API call
    return f"result-for-{key}"

async def worker(worker_id: int):
    result = await cache.get_or_fetch("shared-key", expensive_fetch)
    print(f"Worker {worker_id}: {result}")
```

### asyncio.Semaphore — Concurrency Limiting

Use to limit how many coroutines access a resource simultaneously:

```python
import asyncio
import aiohttp


class RateLimitedClient:
    """HTTP client with concurrency and rate limiting."""

    def __init__(self, max_concurrent: int = 10, max_per_second: float = 20):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._rate_limit = max_per_second
        self._last_request = 0.0
        self._rate_lock = asyncio.Lock()

    async def _wait_for_rate_limit(self):
        """Simple token bucket rate limiter."""
        async with self._rate_lock:
            now = asyncio.get_event_loop().time()
            min_interval = 1.0 / self._rate_limit
            wait_time = self._last_request + min_interval - now
            if wait_time > 0:
                await asyncio.sleep(wait_time)
            self._last_request = asyncio.get_event_loop().time()

    async def fetch(self, session: aiohttp.ClientSession, url: str) -> str:
        async with self._semaphore:  # At most max_concurrent at once
            await self._wait_for_rate_limit()
            async with session.get(url) as resp:
                return await resp.text()

    async def fetch_many(self, urls: list[str]) -> list[str]:
        async with aiohttp.ClientSession() as session:
            tasks = [self.fetch(session, url) for url in urls]
            return await asyncio.gather(*tasks)


# Even with 1000 URLs, only 10 connections are open at once
# and requests are throttled to 20/second
client = RateLimitedClient(max_concurrent=10, max_per_second=20)
```

### asyncio.Event — One-time or Repeated Signaling

Use when one coroutine needs to signal others that something happened:

```python
import asyncio
from dataclasses import dataclass, field


@dataclass
class AsyncWorkerPool:
    """Worker pool with graceful shutdown using Events."""

    shutdown_event: asyncio.Event = field(default_factory=asyncio.Event)
    ready_event: asyncio.Event = field(default_factory=asyncio.Event)
    _workers: list[asyncio.Task] = field(default_factory=list)
    _queue: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(100))

    async def start(self, num_workers: int = 4):
        for i in range(num_workers):
            task = asyncio.create_task(self._worker(i))
            self._workers.append(task)
        self.ready_event.set()  # Signal that pool is ready
        print(f"Pool started with {num_workers} workers")

    async def _worker(self, worker_id: int):
        while not self.shutdown_event.is_set():
            try:
                # Wait for work with a timeout so we can check shutdown
                item = await asyncio.wait_for(
                    self._queue.get(), timeout=1.0
                )
                print(f"Worker {worker_id} processing: {item}")
                await asyncio.sleep(0.1)  # Simulate work
                self._queue.task_done()
            except asyncio.TimeoutError:
                continue  # Check shutdown_event again

    async def submit(self, item):
        await self.ready_event.wait()  # Block until pool is ready
        await self._queue.put(item)

    async def shutdown(self):
        print("Initiating graceful shutdown...")
        await self._queue.join()  # Wait for pending work
        self.shutdown_event.set()  # Signal all workers to stop
        await asyncio.gather(*self._workers)  # Wait for workers to exit
        print("Shutdown complete")
```

### asyncio.Condition — Wait-and-Notify Pattern

Use when coroutines need to wait for a specific condition to become true:

```python
import asyncio
from collections import deque


class AsyncBoundedBuffer:
    """Producer-consumer buffer using Condition for coordination."""

    def __init__(self, maxsize: int = 10):
        self._buffer: deque = deque()
        self._maxsize = maxsize
        self._condition = asyncio.Condition()

    async def put(self, item):
        async with self._condition:
            # Wait while buffer is full
            while len(self._buffer) >= self._maxsize:
                await self._condition.wait()

            self._buffer.append(item)
            # Notify consumers that data is available
            self._condition.notify(1)

    async def get(self):
        async with self._condition:
            # Wait while buffer is empty
            while not self._buffer:
                await self._condition.wait()

            item = self._buffer.popleft()
            # Notify producers that space is available
            self._condition.notify(1)
            return item

    async def size(self) -> int:
        async with self._condition:
            return len(self._buffer)


async def producer(buffer: AsyncBoundedBuffer, name: str):
    for i in range(20):
        await buffer.put(f"{name}-item-{i}")
        await asyncio.sleep(0.05)

async def consumer(buffer: AsyncBoundedBuffer, name: str):
    for _ in range(10):
        item = await buffer.get()
        print(f"{name} consumed: {item}")
        await asyncio.sleep(0.1)
```

### asyncio.Barrier — Synchronization Point

Use when multiple coroutines must all reach a point before any can continue (Python 3.11+):

```python
import asyncio


async def parallel_pipeline():
    """Multi-stage pipeline where all workers sync between stages."""
    barrier = asyncio.Barrier(3)  # 3 workers must sync
    results = {0: [], 1: [], 2: []}

    async def worker(worker_id: int):
        # Stage 1: Each worker does independent preprocessing
        data = await preprocess(worker_id)
        results[worker_id].append(data)
        print(f"Worker {worker_id}: Stage 1 complete")

        # All workers must finish Stage 1 before Stage 2 starts
        await barrier.wait()

        # Stage 2: Cross-reference results from all workers
        merged = merge_results(results)
        output = await postprocess(worker_id, merged)
        results[worker_id].append(output)
        print(f"Worker {worker_id}: Stage 2 complete")

        await barrier.wait()  # Sync again before final stage

        # Stage 3: Final output
        final = finalize(worker_id, results)
        return final

    tasks = [asyncio.create_task(worker(i)) for i in range(3)]
    return await asyncio.gather(*tasks)
```

### Choosing the Right Primitive

| Primitive | Use When | Example |
|-----------|----------|---------|
| **Lock** | Protecting shared mutable state | Cache updates, counters |
| **Semaphore** | Limiting concurrent access | Connection pools, rate limiting |
| **Event** | One-to-many signaling | Startup readiness, shutdown |
| **Condition** | Wait for state predicate | Producer-consumer, bounded buffers |
| **Barrier** | N-way synchronization | Pipeline stages, parallel phases |

**Key insight**: Unlike threading primitives, async primitives never cause deadlocks from lock ordering issues (single-threaded!), but they can cause **logical deadlocks** if a coroutine awaits something that depends on the lock it holds."""
    ),
    (
        "python/async-testing-patterns",
        r"""Explain best practices for testing async Python code including pytest-asyncio setup, mocking async functions, testing timeouts and cancellation, fixtures for async resources, and testing async generators and context managers.""",
        r"""## Testing Async Python Code: pytest-asyncio, Mocking, and Advanced Patterns

Testing async code introduces unique challenges: you need an event loop to run coroutines, mocking `await` calls requires special handling, and testing timeout/cancellation behavior demands careful setup.

### Basic pytest-asyncio Setup

```python
# conftest.py
import pytest
import asyncio


# Option 1: Auto mode — all async tests use asyncio automatically
# In pyproject.toml: [tool.pytest.ini_options] asyncio_mode = "auto"

# Option 2: Explicit mode — mark each test
@pytest.fixture
def event_loop():
    """Override default event loop for custom configuration."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()
```

```python
# test_async_basic.py
import pytest
import asyncio


# With auto mode, just write async test functions
async def test_simple_coroutine():
    result = await asyncio.sleep(0.01, result=42)
    assert result == 42


# With explicit mode, use the marker
@pytest.mark.asyncio
async def test_with_marker():
    result = await asyncio.sleep(0.01, result=42)
    assert result == 42


# Testing concurrent behavior
async def test_gather_results():
    async def compute(x: int) -> int:
        await asyncio.sleep(0.01)
        return x * 2

    results = await asyncio.gather(
        compute(1), compute(2), compute(3)
    )
    assert results == [2, 4, 6]
```

### Mocking Async Functions

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class UserService:
    def __init__(self, db, cache):
        self.db = db
        self.cache = cache

    async def get_user(self, user_id: str) -> dict:
        cached = await self.cache.get(f"user:{user_id}")
        if cached:
            return cached

        user = await self.db.fetch_one(
            "SELECT * FROM users WHERE id = $1", user_id
        )
        if user:
            await self.cache.set(f"user:{user_id}", user, ttl=300)
        return user


# Test with AsyncMock
async def test_get_user_cache_hit():
    mock_cache = AsyncMock()
    mock_db = AsyncMock()

    # Configure the mock to return a value
    mock_cache.get.return_value = {"id": "123", "name": "Alice"}

    service = UserService(db=mock_db, cache=mock_cache)
    result = await service.get_user("123")

    assert result["name"] == "Alice"
    mock_cache.get.assert_awaited_once_with("user:123")
    # DB should NOT have been called (cache hit)
    mock_db.fetch_one.assert_not_awaited()


async def test_get_user_cache_miss():
    mock_cache = AsyncMock()
    mock_db = AsyncMock()

    mock_cache.get.return_value = None  # Cache miss
    mock_db.fetch_one.return_value = {"id": "123", "name": "Bob"}

    service = UserService(db=mock_db, cache=mock_cache)
    result = await service.get_user("123")

    assert result["name"] == "Bob"
    mock_cache.get.assert_awaited_once()
    mock_db.fetch_one.assert_awaited_once()
    # Verify cache was populated
    mock_cache.set.assert_awaited_once_with(
        "user:123", {"id": "123", "name": "Bob"}, ttl=300
    )


# Mock with side effects
async def test_retry_on_failure():
    mock_db = AsyncMock()
    mock_db.fetch_one.side_effect = [
        ConnectionError("timeout"),  # First call fails
        {"id": "123", "name": "Carol"},  # Retry succeeds
    ]

    # Assuming a retry wrapper
    async def fetch_with_retry(db, query, *args, retries=3):
        for attempt in range(retries):
            try:
                return await db.fetch_one(query, *args)
            except ConnectionError:
                if attempt == retries - 1:
                    raise
                await asyncio.sleep(0.01 * (attempt + 1))

    result = await fetch_with_retry(mock_db, "SELECT ...", "123")
    assert result["name"] == "Carol"
    assert mock_db.fetch_one.await_count == 2
```

### Testing Timeouts and Cancellation

```python
import asyncio
import pytest


async def slow_operation(duration: float) -> str:
    await asyncio.sleep(duration)
    return "completed"


async def test_timeout_fires():
    """Verify that operations respect timeout boundaries."""
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(slow_operation(10.0), timeout=0.05)


async def test_cancellation_cleanup():
    """Verify resources are cleaned up on cancellation."""
    cleanup_called = False

    async def operation_with_cleanup():
        nonlocal cleanup_called
        try:
            await asyncio.sleep(10.0)
        except asyncio.CancelledError:
            cleanup_called = True
            raise  # Re-raise to propagate cancellation

    task = asyncio.create_task(operation_with_cleanup())
    await asyncio.sleep(0.01)  # Let it start
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert cleanup_called, "Cleanup handler was not invoked"


async def test_graceful_shutdown():
    """Test that a service shuts down gracefully."""
    processed = []

    async def worker(queue: asyncio.Queue, shutdown: asyncio.Event):
        while not shutdown.is_set():
            try:
                item = await asyncio.wait_for(queue.get(), timeout=0.1)
                processed.append(item)
                queue.task_done()
            except asyncio.TimeoutError:
                continue

    queue = asyncio.Queue()
    shutdown = asyncio.Event()

    # Start worker
    task = asyncio.create_task(worker(queue, shutdown))

    # Submit work
    for i in range(5):
        await queue.put(i)

    # Wait for processing then shutdown
    await queue.join()
    shutdown.set()
    await task

    assert processed == [0, 1, 2, 3, 4]
```

### Async Fixtures

```python
import pytest
import asyncio


class AsyncDatabase:
    """Simulated async database for testing."""

    async def connect(self):
        self._connected = True
        return self

    async def disconnect(self):
        self._connected = False

    async def execute(self, query: str) -> list:
        assert self._connected, "Not connected"
        return []


@pytest.fixture
async def db():
    """Async fixture with setup and teardown."""
    database = AsyncDatabase()
    await database.connect()
    yield database
    await database.disconnect()


@pytest.fixture
async def populated_db(db):
    """Fixture that depends on another async fixture."""
    await db.execute("INSERT INTO users VALUES (1, 'test')")
    return db


async def test_with_db(populated_db):
    result = await populated_db.execute("SELECT * FROM users")
    # Assertions on result...


# Fixture with parametrize
@pytest.fixture(params=["sqlite", "postgres"])
async def multi_db(request):
    db_type = request.param
    db = AsyncDatabase()
    await db.connect()
    yield db, db_type
    await db.disconnect()
```

### Testing Async Generators

```python
import asyncio
import pytest


async def paginated_fetch(total: int, page_size: int = 10):
    """Async generator yielding pages of results."""
    for offset in range(0, total, page_size):
        await asyncio.sleep(0.01)  # Simulate API call
        page = list(range(offset, min(offset + page_size, total)))
        yield page


async def test_async_generator_full_iteration():
    pages = []
    async for page in paginated_fetch(25, page_size=10):
        pages.append(page)

    assert len(pages) == 3
    assert pages[0] == list(range(10))
    assert pages[1] == list(range(10, 20))
    assert pages[2] == list(range(20, 25))


async def test_async_generator_early_break():
    """Test that early termination works correctly."""
    pages_received = 0
    async for page in paginated_fetch(100, page_size=10):
        pages_received += 1
        if pages_received >= 3:
            break

    assert pages_received == 3


async def test_async_generator_with_aclose():
    """Test explicit cleanup of async generator."""
    gen = paginated_fetch(100)
    first_page = await gen.__anext__()
    assert first_page == list(range(10))
    await gen.aclose()  # Clean up generator resources
```

### Testing Async Context Managers

```python
import asyncio
from contextlib import asynccontextmanager


@asynccontextmanager
async def connection_pool(size: int):
    connections = [f"conn-{i}" for i in range(size)]
    semaphore = asyncio.Semaphore(size)
    try:
        yield connections, semaphore
    finally:
        connections.clear()


async def test_context_manager_lifecycle():
    async with connection_pool(3) as (conns, sem):
        assert len(conns) == 3
    # After exiting, connections should be cleaned up


async def test_context_manager_exception_handling():
    """Ensure cleanup runs even on exception."""
    with pytest.raises(ValueError):
        async with connection_pool(3) as (conns, sem):
            assert len(conns) == 3
            raise ValueError("test error")
    # Cleanup should still have run (connections cleared)
```

**Key testing principles**: (1) Use `AsyncMock` for async dependencies — it automatically returns coroutines, (2) Test cancellation paths explicitly — they're common in production, (3) Use `asyncio.wait_for` to prevent tests from hanging indefinitely, (4) Async fixtures handle setup/teardown for resources that need `await`."""
    ),
    (
        "python/async-performance-debugging",
        r"""Explain how to profile and debug async Python performance issues including identifying event loop blocking, measuring coroutine latency, using asyncio debug mode, tracing task execution, and profiling with py-spy and asyncio instrumentation.""",
        r"""## Profiling and Debugging Async Python: Finding Bottlenecks in Concurrent Code

Async performance issues are notoriously hard to diagnose because traditional profilers don't understand cooperative scheduling. A CPU profiler might show your code spending 90% of time in `select()`, which tells you nothing about which coroutine is slow.

### asyncio Debug Mode

The first diagnostic tool — enable it to catch common mistakes:

```python
import asyncio
import logging
import os

# Method 1: Environment variable
os.environ["PYTHONASYNCIODEBUG"] = "1"

# Method 2: At runtime
asyncio.get_event_loop().set_debug(True)

# Method 3: When running
# python -X dev your_script.py

# Debug mode enables:
# 1. Warnings when coroutines are never awaited
# 2. Warnings when event loop is blocked > 100ms
# 3. Detailed tracing of all callbacks and coroutines
# 4. Source location for all tasks (helps identify orphans)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("asyncio")
logger.setLevel(logging.WARNING)  # Or DEBUG for everything
```

### Detecting Event Loop Blocking

The most common async performance killer is blocking the event loop:

```python
import asyncio
import time
import functools
from typing import Callable


class EventLoopMonitor:
    """Detects when the event loop is blocked for too long."""

    def __init__(self, threshold_ms: float = 100):
        self._threshold = threshold_ms / 1000
        self._loop: asyncio.AbstractEventLoop = None
        self._running = False

    def start(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._running = True
        self._last_check = time.monotonic()

        # Install a slow callback logger
        loop.slow_callback_duration = self._threshold

        # Schedule periodic check
        self._schedule_check()

    def _schedule_check(self):
        if self._running and self._loop and self._loop.is_running():
            self._loop.call_later(0.1, self._check_responsiveness)

    def _check_responsiveness(self):
        now = time.monotonic()
        delay = now - self._last_check - 0.1  # Expected ~0.1s interval
        if delay > self._threshold:
            # The event loop was blocked!
            print(f"EVENT LOOP BLOCKED for {delay*1000:.0f}ms!")
            import traceback
            traceback.print_stack()
        self._last_check = now
        self._schedule_check()


def warn_if_blocking(threshold_ms: float = 50):
    """Decorator that warns if an async function takes too long."""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.monotonic()
            result = await func(*args, **kwargs)
            elapsed = (time.monotonic() - start) * 1000
            if elapsed > threshold_ms:
                print(
                    f"SLOW: {func.__qualname__} took {elapsed:.1f}ms "
                    f"(threshold: {threshold_ms}ms)"
                )
            return result
        return wrapper
    return decorator


@warn_if_blocking(threshold_ms=100)
async def process_request(data: dict) -> dict:
    # If this takes > 100ms, we'll get a warning
    result = await do_processing(data)
    return result
```

### Coroutine Latency Tracing

```python
import asyncio
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Optional


_trace_context: ContextVar[Optional["TraceSpan"]] = ContextVar(
    "_trace_context", default=None
)


@dataclass
class TraceSpan:
    name: str
    start_time: float = field(default_factory=time.monotonic)
    end_time: float = 0
    children: list = field(default_factory=list)
    wall_time_ms: float = 0

    def finish(self):
        self.end_time = time.monotonic()
        self.wall_time_ms = (self.end_time - self.start_time) * 1000

    def report(self, indent: int = 0) -> str:
        prefix = "  " * indent
        lines = [f"{prefix}{self.name}: {self.wall_time_ms:.1f}ms"]
        for child in self.children:
            lines.append(child.report(indent + 1))
        return "\n".join(lines)


class AsyncTracer:
    """Lightweight coroutine tracing for async performance analysis."""

    def __init__(self):
        self.spans: list[TraceSpan] = []

    def trace(self, name: str):
        """Use as async context manager to trace a section."""
        return _TraceContextManager(name, self)


class _TraceContextManager:
    def __init__(self, name: str, tracer: AsyncTracer):
        self.name = name
        self.tracer = tracer
        self.span: Optional[TraceSpan] = None

    async def __aenter__(self):
        self.span = TraceSpan(name=self.name)
        parent = _trace_context.get()
        if parent:
            parent.children.append(self.span)
        else:
            self.tracer.spans.append(self.span)
        self._token = _trace_context.set(self.span)
        return self.span

    async def __aexit__(self, *exc):
        self.span.finish()
        _trace_context.reset(self._token)


# Usage:
tracer = AsyncTracer()

async def handle_request(request_id: str):
    async with tracer.trace(f"request-{request_id}"):
        async with tracer.trace("auth"):
            await validate_token(request_id)

        async with tracer.trace("fetch-data"):
            data = await fetch_from_db(request_id)

        async with tracer.trace("transform"):
            result = await transform(data)

        async with tracer.trace("cache-write"):
            await write_cache(request_id, result)

    # Print trace tree:
    # request-123: 145.2ms
    #   auth: 12.3ms
    #   fetch-data: 89.7ms      <-- bottleneck!
    #   transform: 2.1ms
    #   cache-write: 41.1ms
```

### Task Execution Profiling

```python
import asyncio
import time
from collections import defaultdict


class TaskProfiler:
    """Profile all asyncio tasks to find bottlenecks."""

    def __init__(self):
        self.task_stats: dict[str, list[float]] = defaultdict(list)
        self._original_factory = None

    def install(self, loop: asyncio.AbstractEventLoop):
        """Monkey-patch task creation to add profiling."""
        original_create_task = loop.create_task

        def profiled_create_task(coro, *, name=None, **kwargs):
            task_name = name or coro.__qualname__
            wrapped = self._wrap_coroutine(coro, task_name)
            return original_create_task(wrapped, name=name, **kwargs)

        loop.create_task = profiled_create_task

    async def _wrap_coroutine(self, coro, name: str):
        start = time.monotonic()
        try:
            return await coro
        finally:
            elapsed = (time.monotonic() - start) * 1000
            self.task_stats[name].append(elapsed)

    def report(self) -> str:
        lines = ["Task Profiling Report", "=" * 60]
        for name, times in sorted(
            self.task_stats.items(),
            key=lambda x: sum(x[1]),
            reverse=True
        ):
            total = sum(times)
            avg = total / len(times)
            mx = max(times)
            lines.append(
                f"{name:40s} calls={len(times):4d} "
                f"total={total:8.1f}ms avg={avg:6.1f}ms "
                f"max={mx:6.1f}ms"
            )
        return "\n".join(lines)
```

### Integration with py-spy

py-spy can profile async code from outside the process:

```bash
# Attach to running process
py-spy top --pid 12345

# Record a flame graph (works with async!)
py-spy record -o profile.svg --pid 12345

# Key insight: in the flame graph, look for frames that are
# NOT in select/epoll — those are where actual work happens.
# Long bars in non-I/O code indicate event loop blocking.
```

```python
# Programmatic profiling with cProfile (limited for async)
import cProfile
import pstats

async def main():
    profiler = cProfile.Profile()
    profiler.enable()

    await your_async_workload()

    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats("cumulative")
    stats.print_stats(20)

    # For async, cumulative time includes time spent in other
    # coroutines. Focus on 'tottime' (time in function itself)
    # to identify CPU-bound blocking.
```

### Practical Debugging Checklist

```python
async def diagnose_slow_endpoint():
    """Systematic approach to debugging slow async code."""

    # Step 1: Is the event loop being blocked?
    # Enable debug mode and check for "Executing <Task> took X seconds"
    asyncio.get_event_loop().set_debug(True)

    # Step 2: Which awaitable is slow?
    # Add timing around each await:
    t0 = time.monotonic()
    result = await slow_operation()
    print(f"slow_operation: {(time.monotonic()-t0)*1000:.0f}ms")

    # Step 3: Is it I/O latency or CPU?
    # If I/O: check network, database query plans, connection pooling
    # If CPU: offload to executor

    # Step 4: Are there too many concurrent tasks?
    # Check: len(asyncio.all_tasks()) — thousands = problem
    print(f"Active tasks: {len(asyncio.all_tasks())}")

    # Step 5: Connection pool exhaustion?
    # Symptoms: tasks waiting for connections, increasing latency
    # Fix: increase pool size or add semaphore backpressure
```

**Key debugging principles**: (1) Always enable asyncio debug mode first — it catches 80% of issues, (2) Measure wall-clock time per await point to isolate bottlenecks, (3) CPU work in coroutines is the silent killer — profile with py-spy to find it, (4) Monitor active task count — unbounded task creation causes memory and scheduling issues."""
    ),
    (
        "python/async-patterns-production",
        r"""Explain production-ready async Python patterns including graceful shutdown handling, health checks, circuit breakers, retry with exponential backoff, connection pool management, and structured logging in async contexts.""",
        r"""## Production Async Python: Graceful Shutdown, Circuit Breakers, and Resilience Patterns

Moving async Python code from development to production requires patterns for reliability, observability, and graceful degradation.

### Graceful Shutdown

Production services must handle SIGTERM/SIGINT cleanly — finish in-flight requests, close connections, flush buffers:

```python
import asyncio
import signal
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)


class GracefulService:
    """Service with proper shutdown handling."""

    def __init__(self):
        self._shutdown_event = asyncio.Event()
        self._active_requests = 0
        self._request_lock = asyncio.Lock()

    async def start(self):
        loop = asyncio.get_event_loop()

        # Register signal handlers
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(
                sig, lambda s=sig: asyncio.create_task(self._shutdown(s))
            )

        logger.info("Service started, waiting for requests...")
        await self._shutdown_event.wait()

    async def _shutdown(self, sig: signal.Signals):
        logger.info(f"Received {sig.name}, starting graceful shutdown")

        # Phase 1: Stop accepting new requests
        self._accepting = False

        # Phase 2: Wait for in-flight requests (with timeout)
        try:
            await asyncio.wait_for(self._drain_requests(), timeout=30.0)
            logger.info("All requests drained")
        except asyncio.TimeoutError:
            logger.warning(
                f"Shutdown timeout, {self._active_requests} requests orphaned"
            )

        # Phase 3: Close resources
        await self._cleanup()

        # Phase 4: Signal main loop to exit
        self._shutdown_event.set()

    async def _drain_requests(self):
        while self._active_requests > 0:
            logger.info(f"Waiting for {self._active_requests} requests...")
            await asyncio.sleep(0.5)

    async def _cleanup(self):
        """Close database pools, flush metrics, etc."""
        pass

    @asynccontextmanager
    async def request_context(self):
        """Track active requests for graceful shutdown."""
        async with self._request_lock:
            self._active_requests += 1
        try:
            yield
        finally:
            async with self._request_lock:
                self._active_requests -= 1
```

### Circuit Breaker

Prevent cascading failures by stopping calls to failing services:

```python
import asyncio
import time
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, Any


class CircuitState(Enum):
    CLOSED = "closed"        # Normal operation
    OPEN = "open"            # Failing, reject calls
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreaker:
    """Async circuit breaker with configurable thresholds."""

    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 1

    _state: CircuitState = field(default=CircuitState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0, init=False)
    _half_open_calls: int = field(default=0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            if time.monotonic() - self._last_failure_time > self.recovery_timeout:
                return CircuitState.HALF_OPEN
        return self._state

    async def call(self, func: Callable, *args, **kwargs) -> Any:
        async with self._lock:
            current_state = self.state

            if current_state == CircuitState.OPEN:
                raise CircuitBreakerOpen(
                    f"Circuit open, retry after "
                    f"{self.recovery_timeout}s"
                )

            if (current_state == CircuitState.HALF_OPEN and
                    self._half_open_calls >= self.half_open_max_calls):
                raise CircuitBreakerOpen("Half-open limit reached")

        try:
            result = await func(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure()
            raise

    async def _on_success(self):
        async with self._lock:
            self._failure_count = 0
            if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                logger.info("Circuit breaker: CLOSED (recovered)")
            self._state = CircuitState.CLOSED
            self._half_open_calls = 0

    async def _on_failure(self):
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                logger.warning("Circuit breaker: OPEN (half-open test failed)")
            elif self._failure_count >= self.failure_threshold:
                self._state = CircuitState.OPEN
                logger.warning(
                    f"Circuit breaker: OPEN "
                    f"({self._failure_count} failures)"
                )


class CircuitBreakerOpen(Exception):
    pass


# Usage:
db_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=10.0)

async def get_user(user_id: str) -> dict:
    return await db_breaker.call(db.fetch_user, user_id)
```

### Retry with Exponential Backoff

```python
import asyncio
import random
import functools
from typing import Type


def async_retry(
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
):
    """Decorator for async retry with exponential backoff and jitter."""

    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None

            for attempt in range(max_attempts):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt == max_attempts - 1:
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(
                        base_delay * (exponential_base ** attempt),
                        max_delay
                    )

                    # Add jitter to prevent thundering herd
                    if jitter:
                        delay = delay * (0.5 + random.random())

                    logger.warning(
                        f"{func.__qualname__} attempt {attempt + 1} failed: "
                        f"{e}, retrying in {delay:.1f}s"
                    )
                    await asyncio.sleep(delay)

            raise last_exception

        return wrapper
    return decorator


@async_retry(
    max_attempts=3,
    base_delay=0.5,
    retryable_exceptions=(ConnectionError, TimeoutError),
)
async def fetch_data(url: str) -> dict:
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
            return await resp.json()
```

### Connection Pool Management

```python
import asyncio
from dataclasses import dataclass, field
from typing import Any
from contextlib import asynccontextmanager


@dataclass
class AsyncConnectionPool:
    """Generic async connection pool with health checking."""

    max_size: int = 10
    min_size: int = 2
    max_idle_time: float = 300.0
    health_check_interval: float = 30.0

    _pool: asyncio.Queue = field(init=False)
    _size: int = field(default=0, init=False)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, init=False)
    _health_task: asyncio.Task = field(default=None, init=False)

    async def initialize(self, factory):
        """Create pool with minimum connections."""
        self._factory = factory
        self._pool = asyncio.Queue(maxsize=self.max_size)

        for _ in range(self.min_size):
            conn = await self._factory()
            await self._pool.put(conn)
            self._size += 1

        self._health_task = asyncio.create_task(self._health_checker())

    @asynccontextmanager
    async def acquire(self):
        """Acquire a connection from the pool."""
        conn = await self._get_connection()
        try:
            yield conn
        except Exception:
            # Connection might be broken, don't return to pool
            async with self._lock:
                self._size -= 1
            await self._destroy_connection(conn)
            raise
        else:
            await self._pool.put(conn)

    async def _get_connection(self):
        try:
            return self._pool.get_nowait()
        except asyncio.QueueEmpty:
            async with self._lock:
                if self._size < self.max_size:
                    self._size += 1
                    return await self._factory()

            # Pool exhausted, wait for a connection
            return await asyncio.wait_for(
                self._pool.get(), timeout=5.0
            )

    async def _health_checker(self):
        while True:
            await asyncio.sleep(self.health_check_interval)
            checked = 0
            while not self._pool.empty() and checked < self._size:
                try:
                    conn = self._pool.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if await self._is_healthy(conn):
                    await self._pool.put(conn)
                else:
                    async with self._lock:
                        self._size -= 1
                    await self._destroy_connection(conn)
                checked += 1

    async def _is_healthy(self, conn) -> bool:
        try:
            await conn.ping()
            return True
        except Exception:
            return False

    async def _destroy_connection(self, conn):
        try:
            await conn.close()
        except Exception:
            pass

    async def close(self):
        if self._health_task:
            self._health_task.cancel()
        while not self._pool.empty():
            conn = self._pool.get_nowait()
            await self._destroy_connection(conn)
```

### Structured Logging in Async Contexts

```python
import asyncio
import logging
import uuid
from contextvars import ContextVar

# Context variable for request tracing
request_id_var: ContextVar[str] = ContextVar("request_id", default="no-request")


class AsyncContextFilter(logging.Filter):
    """Inject async context (request ID) into all log records."""

    def filter(self, record):
        record.request_id = request_id_var.get("no-request")
        record.task_name = ""
        try:
            task = asyncio.current_task()
            if task:
                record.task_name = task.get_name()
        except RuntimeError:
            pass
        return True


def setup_logging():
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s [%(request_id)s] "
        "[%(task_name)s] %(name)s: %(message)s"
    ))
    handler.addFilter(AsyncContextFilter())

    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.INFO)


async def handle_request(request: dict):
    # Set request ID for all logs in this coroutine tree
    request_id = request.get("id", str(uuid.uuid4())[:8])
    request_id_var.set(request_id)

    logger.info("Processing request")  # Logs: [abc12345] Processing request
    result = await process(request)
    logger.info("Request complete")
    return result


# ContextVars propagate to child tasks automatically!
async def process(request: dict):
    # This logs with the same request_id as the parent
    logger.info("Starting processing")
    await asyncio.sleep(0.1)
    logger.info("Processing done")
```

**Production checklist**: (1) Always handle SIGTERM for graceful shutdown with timeout, (2) Use circuit breakers for external service calls, (3) Add jittered exponential backoff to all retries, (4) Pool and health-check all connections, (5) Propagate request context through `ContextVar` for tracing across coroutine boundaries."""
    ),
]
