"""Async/concurrency training pairs: advanced asyncio patterns."""

pairs = [
    {
        "instruction": r'''How do I limit concurrency in Python asyncio? I need to make 1000 HTTP requests but only allow 20 at a time.''',
        "output": r'''<think>
Limiting concurrency in asyncio -- the main tool is asyncio.Semaphore. You create a semaphore with a count (e.g., 20) and each task acquires it before doing work. When 20 tasks hold the semaphore, the 21st blocks until one releases.

But wait, there is also the question of whether to create all 1000 tasks upfront or lazily. If I create all 1000 tasks at once, they all get scheduled even though only 20 can run. That wastes memory for the task objects and their coroutine frames. For very large numbers, an async iterator or queue approach is better.

Actually, for most practical cases (1000 requests), creating all tasks with a semaphore is fine. The memory overhead of 1000 task objects is small. The queue pattern matters more at 100k+ scale. I will show both approaches but emphasize the semaphore as the primary solution.
</think>

Use `asyncio.Semaphore` to cap concurrent operations:

```python
import asyncio
import httpx
import time
from typing import Any

async def fetch_url(
    client: httpx.AsyncClient,
    url: str,
    semaphore: asyncio.Semaphore,
) -> dict[str, Any]:
    """Fetch a URL with bounded concurrency."""
    async with semaphore:
        # Only N tasks can be inside this block at once
        resp = await client.get(url, timeout=30)
        return {"url": url, "status": resp.status_code}

async def fetch_all_bounded(urls: list[str], max_concurrent: int = 20):
    """Fetch many URLs with limited concurrency."""
    semaphore = asyncio.Semaphore(max_concurrent)

    async with httpx.AsyncClient() as client:
        tasks = [
            asyncio.create_task(fetch_url(client, url, semaphore))
            for url in urls
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]
    return successes, failures

# --- Alternative: Queue-based worker pool (better for huge scale) ---

async def worker(
    name: str,
    queue: asyncio.Queue,
    client: httpx.AsyncClient,
    results: list,
):
    """Worker that pulls URLs from a queue."""
    while True:
        url = await queue.get()
        try:
            resp = await client.get(url, timeout=30)
            results.append({"url": url, "status": resp.status_code})
        except Exception as e:
            results.append({"url": url, "error": str(e)})
        finally:
            queue.task_done()

async def fetch_with_worker_pool(
    urls: list[str],
    num_workers: int = 20,
):
    """Use a fixed worker pool to process URLs."""
    queue: asyncio.Queue[str] = asyncio.Queue()
    results: list[dict[str, Any]] = []

    # Fill the queue
    for url in urls:
        await queue.put(url)

    async with httpx.AsyncClient() as client:
        # Start workers
        workers = [
            asyncio.create_task(worker(f"w-{i}", queue, client, results))
            for i in range(num_workers)
        ]

        # Wait for all items to be processed
        await queue.join()

        # Cancel workers (they are waiting on queue.get())
        for w in workers:
            w.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    return results

async def main():
    urls = [f"https://httpbin.org/delay/1?i={i}" for i in range(100)]

    start = time.monotonic()
    successes, failures = await fetch_all_bounded(urls, max_concurrent=20)
    elapsed = time.monotonic() - start
    print(f"Semaphore: {len(successes)} OK, {len(failures)} failed in {elapsed:.1f}s")

asyncio.run(main())
```

The semaphore approach is simpler and works well for most cases. The queue approach gives more control and is better when you need to dynamically add work.'''
    },
    {
        "instruction": r'''How do I implement timeouts and cancellation in Python asyncio?''',
        "output": r'''<think>
Timeouts and cancellation -- there are several mechanisms:
1. asyncio.wait_for() -- wraps an awaitable with a timeout
2. asyncio.timeout() -- context manager (Python 3.11+)
3. task.cancel() -- explicit cancellation
4. asyncio.shield() -- protect a coroutine from cancellation

I should cover all of these. The tricky part is that cancellation in asyncio works by injecting CancelledError into the coroutine at the next await point. The coroutine can catch it, do cleanup, and then must re-raise it (or the cancellation is suppressed, which is usually a bug).

Actually, wait -- in Python 3.9+, CancelledError inherits from BaseException, not Exception. So a bare `except Exception` will NOT catch it, which is the correct behavior. But in Python 3.8 and earlier, CancelledError inherits from Exception, so bare except clauses could accidentally swallow cancellations.

Let me show practical patterns for all of these.
</think>

```python
import asyncio
from typing import Any

async def slow_operation(duration: float) -> str:
    try:
        await asyncio.sleep(duration)
        return f"completed after {duration}s"
    except asyncio.CancelledError:
        print("Operation cancelled -- running cleanup")
        # Do cleanup (close connections, release resources)
        raise  # Always re-raise CancelledError!

# ============================================================
# 1. asyncio.wait_for() -- timeout on a single awaitable
# ============================================================

async def with_wait_for():
    try:
        result = await asyncio.wait_for(
            slow_operation(10.0),
            timeout=2.0,
        )
    except asyncio.TimeoutError:
        print("Operation timed out after 2s")

# ============================================================
# 2. asyncio.timeout() -- context manager (Python 3.11+)
# ============================================================

async def with_timeout_cm():
    try:
        async with asyncio.timeout(2.0):
            # Everything inside this block has a 2s deadline
            result1 = await slow_operation(0.5)
            result2 = await slow_operation(0.5)
            # Total time matters, not individual calls
    except TimeoutError:
        print("Block timed out")

    # You can also reschedule the deadline
    async with asyncio.timeout(5.0) as cm:
        await slow_operation(1.0)
        # Extend the deadline by 3 more seconds
        cm.reschedule(asyncio.get_running_loop().time() + 3.0)
        await slow_operation(2.0)

# ============================================================
# 3. Explicit task cancellation
# ============================================================

async def cancel_tasks():
    task = asyncio.create_task(slow_operation(100.0))

    await asyncio.sleep(1.0)
    task.cancel("no longer needed")  # message arg is Python 3.9+

    try:
        await task
    except asyncio.CancelledError:
        print(f"Task was cancelled: {task.cancelled()}")

# ============================================================
# 4. asyncio.shield() -- protect from parent cancellation
# ============================================================

async def critical_save(data: dict) -> None:
    """Must not be interrupted."""
    await asyncio.sleep(1.0)  # simulate database write
    print(f"Saved: {data}")

async def shielded_operation():
    try:
        # shield() prevents the inner coroutine from being
        # cancelled when the outer task is cancelled
        await asyncio.shield(critical_save({"key": "value"}))
    except asyncio.CancelledError:
        print("Outer was cancelled but save continues")
        # Note: the shielded task keeps running!

# ============================================================
# Practical: timeout with fallback
# ============================================================

async def fetch_with_fallback(
    primary_source: str,
    fallback_source: str,
    timeout_seconds: float = 2.0,
) -> dict[str, Any]:
    try:
        async with asyncio.timeout(timeout_seconds):
            return await fetch_from(primary_source)
    except TimeoutError:
        print(f"Primary timed out, trying fallback")
        return await fetch_from(fallback_source)

async def fetch_from(source: str) -> dict[str, Any]:
    await asyncio.sleep(0.5)
    return {"source": source, "data": "result"}

async def main():
    await with_wait_for()
    await cancel_tasks()

asyncio.run(main())
```

Key rules:
- Always re-raise `CancelledError` after cleanup
- Use `asyncio.timeout()` (3.11+) over `wait_for()` when possible
- `shield()` protects the inner task but the outer still gets cancelled
- `CancelledError` is a `BaseException`, not caught by `except Exception`'''
    },
    {
        "instruction": r'''Show me how to build a producer-consumer pipeline using asyncio.Queue in Python.''',
        "output": r'''```python
import asyncio
import random
import time
from dataclasses import dataclass
from typing import Any

@dataclass
class WorkItem:
    id: int
    data: str
    created_at: float

@dataclass
class ProcessedItem:
    id: int
    result: str
    processing_time: float

async def producer(
    queue: asyncio.Queue[WorkItem],
    num_items: int,
    name: str,
):
    """Generate work items and put them on the queue."""
    for i in range(num_items):
        item = WorkItem(
            id=i,
            data=f"item-{i}-from-{name}",
            created_at=time.monotonic(),
        )
        await queue.put(item)
        print(f"[{name}] produced item {i}")
        # Simulate variable production rate
        await asyncio.sleep(random.uniform(0.01, 0.1))
    print(f"[{name}] finished producing")

async def consumer(
    input_queue: asyncio.Queue[WorkItem],
    output_queue: asyncio.Queue[ProcessedItem],
    name: str,
):
    """Process work items from input queue, put results on output queue."""
    while True:
        item = await input_queue.get()
        try:
            start = time.monotonic()
            # Simulate processing
            await asyncio.sleep(random.uniform(0.05, 0.2))
            result = ProcessedItem(
                id=item.id,
                result=f"processed-{item.data}",
                processing_time=time.monotonic() - start,
            )
            await output_queue.put(result)
            print(f"[{name}] processed item {item.id}")
        finally:
            input_queue.task_done()

async def result_collector(
    output_queue: asyncio.Queue[ProcessedItem],
    results: list[ProcessedItem],
):
    """Collect processed results."""
    while True:
        item = await output_queue.get()
        results.append(item)
        output_queue.task_done()

async def pipeline(
    num_items: int = 20,
    num_producers: int = 2,
    num_consumers: int = 4,
):
    """Run a multi-stage producer-consumer pipeline."""
    # Bounded queues provide backpressure
    work_queue: asyncio.Queue[WorkItem] = asyncio.Queue(maxsize=10)
    result_queue: asyncio.Queue[ProcessedItem] = asyncio.Queue()
    results: list[ProcessedItem] = []

    start = time.monotonic()

    # Start consumers and collector
    consumers = [
        asyncio.create_task(
            consumer(work_queue, result_queue, f"consumer-{i}")
        )
        for i in range(num_consumers)
    ]
    collector = asyncio.create_task(
        result_collector(result_queue, results)
    )

    # Start producers and wait for them to finish
    items_per_producer = num_items // num_producers
    producers = [
        asyncio.create_task(
            producer(work_queue, items_per_producer, f"producer-{i}")
        )
        for i in range(num_producers)
    ]
    await asyncio.gather(*producers)

    # Wait for all work to be processed
    await work_queue.join()
    await result_queue.join()

    # Cancel workers
    for c in consumers:
        c.cancel()
    collector.cancel()
    await asyncio.gather(*consumers, collector, return_exceptions=True)

    elapsed = time.monotonic() - start
    avg_time = sum(r.processing_time for r in results) / len(results)
    print(f"\nPipeline complete:")
    print(f"  Items processed: {len(results)}")
    print(f"  Total time: {elapsed:.2f}s")
    print(f"  Avg processing time: {avg_time:.3f}s")

asyncio.run(pipeline())
```

Key design points:
- `maxsize` on the work queue creates backpressure -- producers block when the queue is full
- `task_done()` and `join()` let you know when all items are processed
- Consumers run forever and are cancelled after all work is done
- Multiple producers and consumers scale independently'''
    },
    {
        "instruction": r'''What is structured concurrency in Python and why should I prefer it over fire-and-forget tasks?''',
        "output": r'''<think>
Structured concurrency -- the core idea is that concurrent tasks should be scoped like variables: they start in a block, and the block does not exit until all tasks finish. This is in contrast to fire-and-forget where you call create_task() and the task lives independently.

Why does fire-and-forget cause problems? Let me think through the failure modes:
1. Leaked tasks -- task outlives its scope, holds resources, crashes later with no handler
2. Lost exceptions -- if nobody awaits the task, exceptions silently vanish
3. Shutdown complexity -- you need to track all tasks manually to cancel them during shutdown
4. Testing difficulty -- tests cannot know when background tasks finish

Python 3.11 added TaskGroup for structured concurrency. The key guarantees are:
- All tasks are children of the group
- The group block does not exit until all tasks complete
- If any task raises, all siblings are cancelled
- Exceptions are collected into an ExceptionGroup

I should show a concrete before/after to make the benefits clear.
</think>

Structured concurrency means concurrent tasks are scoped to a block -- they cannot outlive it. This prevents leaked tasks, lost exceptions, and shutdown bugs.

```python
import asyncio
import logging

logger = logging.getLogger(__name__)

# ============================================================
# BAD: Fire-and-forget creates invisible problems
# ============================================================

async def send_notification(user_id: int, message: str):
    await asyncio.sleep(0.5)
    if user_id == 42:
        raise ConnectionError("Notification service down")
    print(f"Notified user {user_id}: {message}")

async def bad_handler(request: dict):
    # Fire-and-forget: task floats in the void
    asyncio.create_task(send_notification(42, "welcome"))
    # Problems:
    # 1. ConnectionError silently lost
    # 2. Task outlives this function
    # 3. If app shuts down, task may be killed mid-send
    # 4. No way to know if notification succeeded
    return {"status": "ok"}

# ============================================================
# GOOD: Structured concurrency with TaskGroup
# ============================================================

async def good_handler(request: dict):
    async with asyncio.TaskGroup() as tg:
        tg.create_task(send_notification(request["user_id"], "welcome"))
        tg.create_task(update_analytics(request))
        tg.create_task(log_access(request))
    # Guarantees:
    # 1. ALL tasks finished (or failed) before we reach here
    # 2. Any exception cancels siblings and propagates
    # 3. No leaked tasks possible
    return {"status": "ok"}

async def update_analytics(request: dict):
    await asyncio.sleep(0.1)

async def log_access(request: dict):
    await asyncio.sleep(0.05)

# ============================================================
# Pattern: background tasks that SHOULD outlive a request
# ============================================================

class BackgroundTaskManager:
    """For tasks that genuinely need to run independently."""

    def __init__(self):
        self._tasks: set[asyncio.Task] = set()

    def create_task(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._on_done)
        return task

    def _on_done(self, task: asyncio.Task):
        self._tasks.discard(task)
        if not task.cancelled() and task.exception():
            logger.error(
                "Background task failed: %s",
                task.exception(),
            )

    async def shutdown(self, timeout: float = 10.0):
        """Cancel all tasks and wait for cleanup."""
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=timeout)
        remaining = [t for t in self._tasks if not t.done()]
        if remaining:
            logger.warning(
                "%d tasks did not finish in time", len(remaining)
            )

# Usage
manager = BackgroundTaskManager()

async def request_handler(request: dict):
    # Structured part: must complete before response
    async with asyncio.TaskGroup() as tg:
        data = tg.create_task(fetch_data(request))
        auth = tg.create_task(check_auth(request))

    # Genuinely background: fire-and-forget with safety net
    manager.create_task(send_notification(1, "done"))

    return {"data": data.result()}

async def fetch_data(req): return {"key": "value"}
async def check_auth(req): return True

async def main():
    await request_handler({"user_id": 1})
    await manager.shutdown()

asyncio.run(main())
```

Rule of thumb: use `TaskGroup` by default. Only use fire-and-forget when the task genuinely should outlive its scope, and always use a manager with error logging.'''
    },
    {
        "instruction": r'''How do I use async context managers and async iterators in Python?''',
        "output": r'''```python
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Any

# ============================================================
# Async Context Managers
# ============================================================

# Method 1: Class-based async context manager
class AsyncDatabasePool:
    """Manages a pool of database connections."""

    def __init__(self, dsn: str, min_size: int = 2, max_size: int = 10):
        self.dsn = dsn
        self.min_size = min_size
        self.max_size = max_size
        self._pool = None

    async def __aenter__(self):
        print(f"Connecting to {self.dsn}...")
        await asyncio.sleep(0.1)  # simulate connection
        self._pool = {"dsn": self.dsn, "active": True}
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        print("Closing pool...")
        await asyncio.sleep(0.05)  # simulate cleanup
        self._pool = None
        return False  # do not suppress exceptions

    async def query(self, sql: str) -> list[dict]:
        await asyncio.sleep(0.05)
        return [{"id": 1, "sql": sql}]

# Method 2: Decorator-based async context manager
@asynccontextmanager
async def async_timer(label: str):
    """Time an async block."""
    import time
    start = time.monotonic()
    try:
        yield start  # value available via 'as'
    finally:
        elapsed = time.monotonic() - start
        print(f"[{label}] took {elapsed:.3f}s")

@asynccontextmanager
async def temporary_file(path: str):
    """Create a temp file, clean up when done."""
    import os
    try:
        with open(path, "w") as f:
            f.write("")
        yield path
    finally:
        if os.path.exists(path):
            os.remove(path)

# ============================================================
# Async Iterators
# ============================================================

# Method 1: Class-based async iterator
class AsyncPaginator:
    """Paginate through API results asynchronously."""

    def __init__(self, base_url: str, page_size: int = 10):
        self.base_url = base_url
        self.page_size = page_size
        self._page = 0
        self._exhausted = False

    def __aiter__(self):
        return self

    async def __anext__(self) -> list[dict]:
        if self._exhausted:
            raise StopAsyncIteration
        self._page += 1
        await asyncio.sleep(0.1)  # simulate API call
        # Simulate: 3 pages of results
        if self._page > 3:
            raise StopAsyncIteration
        return [
            {"id": (self._page - 1) * self.page_size + i}
            for i in range(self.page_size)
        ]

# Method 2: Async generator (simplest approach)
async def stream_events(
    channel: str,
    max_events: int = 100,
) -> AsyncIterator[dict[str, Any]]:
    """Yield events as they arrive."""
    for i in range(max_events):
        await asyncio.sleep(0.1)
        yield {"channel": channel, "event_id": i, "data": f"event-{i}"}

async def chunked_reader(
    data: list[Any],
    chunk_size: int = 5,
) -> AsyncIterator[list[Any]]:
    """Yield data in chunks with async processing."""
    for i in range(0, len(data), chunk_size):
        chunk = data[i:i + chunk_size]
        await asyncio.sleep(0.01)  # simulate I/O
        yield chunk

# ============================================================
# Using them together
# ============================================================

async def main():
    # Async context manager
    async with AsyncDatabasePool("postgres://localhost/mydb") as db:
        results = await db.query("SELECT * FROM users")
        print(f"Got {len(results)} rows")

    # Async timer
    async with async_timer("data-fetch"):
        await asyncio.sleep(0.5)

    # Async iterator -- for loop
    async for page in AsyncPaginator("https://api.example.com/items"):
        print(f"Got page with {len(page)} items")

    # Async generator -- collect first 5 events
    events = []
    async for event in stream_events("updates", max_events=20):
        events.append(event)
        if len(events) >= 5:
            break
    print(f"Collected {len(events)} events")

    # Async comprehension
    chunks = [
        chunk
        async for chunk in chunked_reader(list(range(25)), chunk_size=5)
    ]
    print(f"Got {len(chunks)} chunks")

asyncio.run(main())
```'''
    },
]
