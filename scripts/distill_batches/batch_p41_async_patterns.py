"""Async patterns — asyncio advanced, task groups, structured concurrency, and async generators."""

PAIRS = [
    (
        "python/asyncio-advanced",
        "Show advanced asyncio patterns: TaskGroup, structured concurrency, semaphores, async generators, and cancellation handling.",
        '''Advanced asyncio patterns for production:

```python
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Any

# --- TaskGroup (Python 3.11+) — structured concurrency ---

async def fetch_user_data(user_id: str) -> dict:
    """Fetch user profile, orders, and preferences concurrently."""
    async with asyncio.TaskGroup() as tg:
        profile_task = tg.create_task(fetch_profile(user_id))
        orders_task = tg.create_task(fetch_orders(user_id))
        prefs_task = tg.create_task(fetch_preferences(user_id))

    # All tasks completed (or all cancelled if any raised)
    return {
        "profile": profile_task.result(),
        "orders": orders_task.result(),
        "preferences": prefs_task.result(),
    }

# With error handling
async def fetch_with_fallbacks(user_id: str) -> dict:
    results = {}
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(set_result(results, "profile", fetch_profile(user_id)))
            tg.create_task(set_result(results, "orders", fetch_orders(user_id)))
    except* ValueError as eg:
        # ExceptionGroup handling (Python 3.11+)
        for exc in eg.exceptions:
            print(f"ValueError: {exc}")
    except* ConnectionError as eg:
        for exc in eg.exceptions:
            print(f"Connection failed: {exc}")
    return results

async def set_result(results: dict, key: str, coro):
    results[key] = await coro


# --- Semaphore: limit concurrency ---

async def fetch_all_urls(urls: list[str], max_concurrent: int = 10) -> list:
    """Fetch URLs with bounded concurrency."""
    semaphore = asyncio.Semaphore(max_concurrent)
    results = []

    async def fetch_one(url: str) -> dict:
        async with semaphore:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=10)
                return {"url": url, "status": response.status_code}

    async with asyncio.TaskGroup() as tg:
        tasks = [tg.create_task(fetch_one(url)) for url in urls]

    return [task.result() for task in tasks]


# --- Async generator: streaming data ---

async def stream_database_rows(query: str, batch_size: int = 100) -> AsyncIterator[dict]:
    """Stream rows from database without loading all into memory."""
    offset = 0
    while True:
        rows = await db.fetch(f"{query} LIMIT {batch_size} OFFSET {offset}")
        if not rows:
            break
        for row in rows:
            yield dict(row)
        offset += batch_size

# Consume:
async for row in stream_database_rows("SELECT * FROM users"):
    await process_user(row)

# With async comprehension:
active_users = [
    user async for user in stream_database_rows("SELECT * FROM users")
    if user["is_active"]
]


# --- Timeout and cancellation ---

async def fetch_with_timeout(url: str, timeout: float = 5.0):
    """Timeout wrapper with cleanup."""
    try:
        async with asyncio.timeout(timeout):
            return await fetch(url)
    except TimeoutError:
        print(f"Timeout fetching {url}")
        return None

# Cancellation-safe cleanup
async def managed_connection():
    conn = await create_connection()
    try:
        yield conn
    except asyncio.CancelledError:
        # Cleanup even on cancellation
        await conn.close()
        raise  # Re-raise to propagate cancellation


# --- Event: signal between tasks ---

async def producer_consumer():
    event = asyncio.Event()
    queue = asyncio.Queue(maxsize=100)

    async def producer():
        for i in range(50):
            await queue.put(f"item-{i}")
            await asyncio.sleep(0.01)
        event.set()  # Signal completion

    async def consumer(name: str):
        while not event.is_set() or not queue.empty():
            try:
                item = await asyncio.wait_for(queue.get(), timeout=1.0)
                await process(item)
            except TimeoutError:
                continue

    async with asyncio.TaskGroup() as tg:
        tg.create_task(producer())
        for i in range(3):
            tg.create_task(consumer(f"worker-{i}"))


# --- Async context manager ---

@asynccontextmanager
async def managed_pool(size: int = 10):
    """Async resource pool with cleanup."""
    pool = await create_pool(size=size)
    try:
        yield pool
    finally:
        await pool.close()
        await pool.wait_closed()

# Usage:
async with managed_pool(10) as pool:
    async with pool.acquire() as conn:
        await conn.execute("SELECT 1")


# --- Debounce: coalesce rapid calls ---

class AsyncDebouncer:
    def __init__(self, delay: float = 0.5):
        self.delay = delay
        self._task: asyncio.Task | None = None

    async def __call__(self, coro_fn: Callable, *args, **kwargs):
        if self._task:
            self._task.cancel()
        self._task = asyncio.create_task(self._debounced(coro_fn, *args, **kwargs))

    async def _debounced(self, coro_fn, *args, **kwargs):
        await asyncio.sleep(self.delay)
        await coro_fn(*args, **kwargs)
```

Key patterns:
1. **TaskGroup** — structured concurrency, all tasks cancelled on failure
2. **Semaphore** — bound concurrency for resource-intensive operations
3. **Async generators** — memory-efficient streaming with `async for`
4. **`asyncio.timeout`** — cleaner than `wait_for` (Python 3.11+)
5. **Event** — coordinate producer/consumer without polling'''
    ),
    (
        "python/async-testing",
        "Show async testing patterns: pytest-asyncio, testing concurrent code, mocking async functions, and timing-sensitive tests.",
        '''Testing async Python code:

```python
import asyncio
import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

# --- Basic async test (pytest-asyncio) ---

# pyproject.toml: asyncio_mode = "auto"

async def test_async_service():
    """Async tests work naturally with auto mode."""
    service = UserService(repo=AsyncMock())
    service.repo.get_by_id.return_value = {"id": "1", "name": "Alice"}

    user = await service.get_user("1")
    assert user["name"] == "Alice"


# --- Testing concurrent operations ---

async def test_concurrent_fetches():
    """Verify operations run concurrently, not sequentially."""
    call_times = []

    async def mock_fetch(url):
        call_times.append(asyncio.get_event_loop().time())
        await asyncio.sleep(0.1)  # Simulate latency
        return {"url": url, "data": "..."}

    with patch("app.services.fetch", side_effect=mock_fetch):
        start = asyncio.get_event_loop().time()
        results = await fetch_multiple(["url1", "url2", "url3"])
        duration = asyncio.get_event_loop().time() - start

    assert len(results) == 3
    # Should complete in ~0.1s (concurrent), not ~0.3s (sequential)
    assert duration < 0.2


# --- Testing timeouts ---

async def test_timeout_handling():
    """Test that timeout is properly handled."""
    async def slow_operation():
        await asyncio.sleep(10)

    mock_client = AsyncMock()
    mock_client.get.side_effect = slow_operation

    result = await fetch_with_timeout(mock_client, "http://test", timeout=0.1)
    assert result is None  # Should return None on timeout


# --- Testing async generators ---

async def test_async_generator():
    """Test streaming results."""
    mock_db = AsyncMock()
    mock_db.fetch.side_effect = [
        [{"id": 1}, {"id": 2}],  # First batch
        [{"id": 3}],              # Second batch
        [],                        # Empty = done
    ]

    results = []
    async for row in stream_rows(mock_db, batch_size=2):
        results.append(row)

    assert len(results) == 3
    assert mock_db.fetch.call_count == 3


# --- Testing event-driven code ---

async def test_event_emitter():
    received = []

    async def handler(event):
        received.append(event)

    emitter = EventEmitter()
    emitter.on("order.created", handler)

    await emitter.emit("order.created", {"order_id": "123"})

    # Give handler time to process
    await asyncio.sleep(0)

    assert len(received) == 1
    assert received[0]["order_id"] == "123"


# --- Testing with real asyncio.Queue ---

async def test_worker_processes_messages():
    queue = asyncio.Queue()
    results = []

    async def worker():
        while True:
            msg = await queue.get()
            if msg is None:
                break
            results.append(msg.upper())
            queue.task_done()

    # Start worker
    task = asyncio.create_task(worker())

    # Send messages
    await queue.put("hello")
    await queue.put("world")
    await queue.put(None)  # Shutdown signal

    await task
    assert results == ["HELLO", "WORLD"]


# --- Fixtures for async setup/teardown ---

@pytest.fixture
async def event_loop_policy():
    """Custom event loop policy if needed."""
    policy = asyncio.DefaultEventLoopPolicy()
    asyncio.set_event_loop_policy(policy)
    yield policy
    asyncio.set_event_loop_policy(None)

@pytest.fixture
async def background_service():
    """Start and stop a background service for testing."""
    service = BackgroundWorker()
    task = asyncio.create_task(service.run())
    yield service
    service.shutdown()
    await task
```

Async testing tips:
1. **Use `asyncio_mode = "auto"`** — no need for `@pytest.mark.asyncio`
2. **AsyncMock** — automatically handles `await` on mock calls
3. **Test concurrency** — verify operations run in parallel, not serial
4. **`asyncio.sleep(0)`** — yield control to let callbacks execute
5. **Shutdown signals** — use `None` sentinel or cancellation for clean shutdown'''
    ),
]
