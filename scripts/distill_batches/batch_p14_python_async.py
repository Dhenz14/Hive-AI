"""p14 python async"""

PAIRS = [
    (
        "python/async-await-deep-dive",
        "Explain Python's async/await internals including the event loop architecture, coroutine lifecycle, task scheduling, how asyncio handles I/O multiplexing with selectors, and common pitfalls like blocking the event loop. Include practical patterns for structured concurrency.",
        '''Python's `async`/`await` syntax is built on top of **coroutines** -- generator-like objects that can be suspended and resumed. Understanding the machinery beneath the syntax is essential for writing correct, performant async code.

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
            # The coroutine yielded a future -- wait for it
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

    # Connect asynchronously -- the event loop registers the socket
    # with epoll/kqueue and suspends this coroutine until connected
    await loop.sock_connect(sock, (host, port))

    # Under the hood, loop.sock_connect does:
    # 1. Try connect() -- gets EINPROGRESS (non-blocking)
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
    """Concurrent fetches -- all sockets multiplexed on one thread."""
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
    # CPU-bound work in a coroutine -- no other coroutine can run!
    return hashlib.pbkdf2_hmac("sha256", data, b"salt", 1_000_000).hex()


# GOOD: Offload CPU-bound work to a thread pool
async def good_hash(data: bytes) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,  # Default ThreadPoolExecutor
        hashlib.pbkdf2_hmac, "sha256", data, b"salt", 1_000_000'''
    ),
    (
        "python/async-synchronization-primitives",
        "Explain async synchronization primitives in Python including asyncio.Lock, Semaphore, Event, Condition, and Barrier. Show when each is needed and common patterns for coordinating concurrent coroutines safely.",
        '''Even though asyncio is single-threaded, you still need synchronization primitives. **Why?** Because coroutines can be suspended at any `await` point, allowing other coroutines to modify shared state in between. This creates **logical** race conditions even without thread-level parallelism.

### asyncio.Lock -- Mutual Exclusion

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
# for the same key and fetch twice -- wasting resources.
cache = AsyncCache()

async def expensive_fetch(key: str) -> str:
    await asyncio.sleep(1)  # Simulate slow API call
    return f"result-for-{key}"

async def worker(worker_id: int):
    result = await cache.get_or_fetch("shared-key", expensive_fetch)
    print(f"Worker {worker_id}: {result}")
```

### asyncio.Semaphore -- Concurrency Limiting

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

### asyncio.Event -- One-time or Repeated Signaling

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
                    self._queue.get(), timeout=1.0'''
    ),
    (
        "python/async-testing-patterns",
        "Explain best practices for testing async Python code including pytest-asyncio setup, mocking async functions, testing timeouts and cancellation, fixtures for async resources, and testing async generators and context managers.",
        '''Testing async code introduces unique challenges: you need an event loop to run coroutines, mocking `await` calls requires special handling, and testing timeout/cancellation behavior demands careful setup.

### Basic pytest-asyncio Setup

```python
# conftest.py
import pytest
import asyncio


# Option 1: Auto mode -- all async tests use asyncio automatically
# In pyproject.toml: [tool.pytest.ini_options] asyncio_mode = "auto"

# Option 2: Explicit mode -- mark each test
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
        compute(1), compute(2), compute(3)'''
    ),
    (
        "python/async-performance-debugging",
        "Explain how to profile and debug async Python performance issues including identifying event loop blocking, measuring coroutine latency, using asyncio debug mode, tracing task execution, and profiling with py-spy and asyncio instrumentation.",
        '''Async performance issues are notoriously hard to diagnose because traditional profilers don't understand cooperative scheduling. A CPU profiler might show your code spending 90% of time in `select()`, which tells you nothing about which coroutine is slow.

### asyncio Debug Mode

The first diagnostic tool -- enable it to catch common mistakes:

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
                    f"(threshold: {threshold_ms}ms)"'''
    ),
    (
        "_trace_context",
        ") @dataclass class TraceSpan: name: str start_time: float = field(default_factory=time.monotonic) end_time: float = 0 children: list = field(default_factory=list) wall_time_ms: float = 0 def finish(self): self.end_time = time.monotonic() self.wall_time_ms = (self.end_time - self.start_time) * 1000 def report(self, indent: int = 0) -> str: prefix = '  ' * indent lines = [f'{prefix}{self.name}: {self.wall_time_ms:.1f}ms'] for child in self.children: lines.append(child.report(indent + 1)) return '\n'.join(lines) class AsyncTracer:",
        '''self.spans: list[TraceSpan] = []

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
                f"max={mx:6.1f}ms"'''
    ),
    (
        "python/async-patterns-production",
        "Explain production-ready async Python patterns including graceful shutdown handling, health checks, circuit breakers, retry with exponential backoff, connection pool management, and structured logging in async contexts.",
        '''Moving async Python code from development to production requires patterns for reliability, observability, and graceful degradation.

### Graceful Shutdown

Production services must handle SIGTERM/SIGINT cleanly -- finish in-flight requests, close connections, flush buffers:

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
                sig, lambda s=sig: asyncio.create_task(self._shutdown(s))'''
    ),
]
