"""Advanced asyncio — structured concurrency, streaming, and production patterns."""

PAIRS = [
    (
        "python/asyncio-patterns",
        "Show advanced Python asyncio patterns: TaskGroup, structured concurrency, semaphores, and async generators.",
        '''Advanced asyncio patterns:

```python
import asyncio
from asyncio import TaskGroup, Semaphore, Queue
from contextlib import asynccontextmanager
from typing import AsyncIterator, Callable, Any
import logging
import time

logger = logging.getLogger(__name__)


# --- Structured concurrency with TaskGroup (3.11+) ---

async def fetch_dashboard_data(user_id: str) -> dict:
    """Fetch multiple data sources concurrently with proper error handling."""
    async with TaskGroup() as tg:
        profile_task = tg.create_task(fetch_profile(user_id))
        orders_task = tg.create_task(fetch_orders(user_id))
        notifications_task = tg.create_task(fetch_notifications(user_id))
        # If ANY task raises, all others are cancelled automatically

    return {
        "profile": profile_task.result(),
        "orders": orders_task.result(),
        "notifications": notifications_task.result(),
    }


# --- Bounded concurrency with Semaphore ---

async def fetch_all_urls(urls: list[str], max_concurrent: int = 10) -> list[dict]:
    """Fetch URLs with bounded concurrency."""
    semaphore = Semaphore(max_concurrent)
    results = []

    async def fetch_one(url: str) -> dict:
        async with semaphore:
            async with httpx.AsyncClient() as client:
                resp = await client.get(url, timeout=30)
                return {"url": url, "status": resp.status_code, "body": resp.text}

    async with TaskGroup() as tg:
        tasks = [tg.create_task(fetch_one(url)) for url in urls]

    return [t.result() for t in tasks]


# --- Async producer-consumer with Queue ---

async def producer_consumer_pipeline(
    items: list[Any],
    process: Callable,
    workers: int = 5,
):
    """Process items through async worker pool."""
    queue: Queue = Queue(maxsize=workers * 2)
    results = []

    async def worker(worker_id: int):
        while True:
            item = await queue.get()
            if item is None:
                queue.task_done()
                break
            try:
                result = await process(item)
                results.append(result)
            except Exception as e:
                logger.error("Worker %d error: %s", worker_id, e)
            finally:
                queue.task_done()

    # Start workers
    async with TaskGroup() as tg:
        worker_tasks = [
            tg.create_task(worker(i)) for i in range(workers)
        ]

        # Feed items
        for item in items:
            await queue.put(item)

        # Send stop signals
        for _ in range(workers):
            await queue.put(None)

    return results


# --- Async generator (streaming) ---

async def stream_large_query(
    query: str,
    batch_size: int = 100,
) -> AsyncIterator[dict]:
    """Stream database results without loading all into memory."""
    offset = 0
    while True:
        rows = await db.fetch_all(
            f"{query} LIMIT {batch_size} OFFSET {offset}"
        )
        if not rows:
            break
        for row in rows:
            yield dict(row)
        offset += batch_size


# async for record in stream_large_query("SELECT * FROM events"):
#     process(record)


# --- Timeout and cancellation ---

async def fetch_with_timeout(url: str, timeout: float = 5.0) -> dict | None:
    """Fetch with timeout, return None on timeout."""
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient() as client:
                resp = await client.get(url)
                return resp.json()
    except asyncio.TimeoutError:
        logger.warning("Timeout fetching %s", url)
        return None


async def first_successful(*coros) -> Any:
    """Return result of first coroutine to succeed, cancel rest."""
    async with TaskGroup() as tg:
        done = asyncio.Event()
        result_holder = [None]

        async def wrapper(coro):
            try:
                result = await coro
                if not done.is_set():
                    result_holder[0] = result
                    done.set()
            except Exception:
                pass

        for coro in coros:
            tg.create_task(wrapper(coro))

        await done.wait()
        # Cancel remaining tasks by exiting TaskGroup
        # (remaining tasks get CancelledError)

    return result_holder[0]


# --- Periodic background task ---

async def run_periodically(
    func: Callable,
    interval: float,
    *args,
    **kwargs,
):
    """Run async function on a fixed interval."""
    while True:
        start = time.monotonic()
        try:
            await func(*args, **kwargs)
        except Exception as e:
            logger.error("Periodic task error: %s", e)

        elapsed = time.monotonic() - start
        sleep_time = max(0, interval - elapsed)
        await asyncio.sleep(sleep_time)


# --- Async context manager for resource pools ---

class AsyncPool:
    """Generic async resource pool."""

    def __init__(self, factory: Callable, size: int = 10):
        self._factory = factory
        self._semaphore = Semaphore(size)
        self._pool: Queue = Queue(maxsize=size)
        self._size = size

    async def initialize(self):
        for _ in range(self._size):
            resource = await self._factory()
            await self._pool.put(resource)

    @asynccontextmanager
    async def acquire(self):
        async with self._semaphore:
            resource = await self._pool.get()
            try:
                yield resource
            finally:
                await self._pool.put(resource)


# pool = AsyncPool(create_connection, size=10)
# await pool.initialize()
# async with pool.acquire() as conn:
#     await conn.execute("SELECT 1")
```

Asyncio patterns:
1. **`TaskGroup`** — structured concurrency: if one task fails, all siblings are cancelled
2. **`Semaphore`** — bound concurrency to N simultaneous operations (e.g., HTTP requests)
3. **`Queue`** — async producer-consumer with backpressure via `maxsize`
4. **`async for` generators** — stream large datasets without loading all into memory
5. **`asyncio.timeout()`** — clean timeout handling with automatic cancellation (3.11+)'''
    ),
    (
        "python/async-testing",
        "Show async Python testing patterns: pytest-asyncio, mocking async functions, and testing streams.",
        '''Async testing patterns with pytest:

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient
import pytest_asyncio


# --- pytest-asyncio setup ---

# pyproject.toml:
# [tool.pytest.ini_options]
# asyncio_mode = "auto"  # All async tests run automatically


# --- Basic async test ---

async def test_fetch_user():
    """Test async function directly."""
    user = await fetch_user("user-123")
    assert user["id"] == "user-123"
    assert user["email"] is not None


# --- Async fixtures ---

@pytest_asyncio.fixture
async def db_session():
    """Create and cleanup async database session."""
    session = await create_async_session()
    await session.execute("BEGIN")
    yield session
    await session.execute("ROLLBACK")
    await session.close()


@pytest_asyncio.fixture
async def sample_user(db_session):
    """Create a sample user for tests."""
    user = await db_session.execute(
        "INSERT INTO users (email, name) VALUES ($1, $2) RETURNING *",
        "test@example.com", "Test User",
    )
    return dict(user)


async def test_update_user(db_session, sample_user):
    await update_user(db_session, sample_user["id"], name="Updated")
    user = await get_user(db_session, sample_user["id"])
    assert user["name"] == "Updated"


# --- Mocking async functions ---

async def test_send_notification_calls_api():
    """Mock external async API call."""
    mock_client = AsyncMock()
    mock_client.post.return_value = MagicMock(status_code=200)

    await send_notification(
        client=mock_client,
        user_id="123",
        message="Hello",
    )

    mock_client.post.assert_called_once_with(
        "https://api.notify.com/send",
        json={"user_id": "123", "message": "Hello"},
    )


async def test_retry_on_failure():
    """Test that function retries on failure."""
    mock_fn = AsyncMock(
        side_effect=[ConnectionError, ConnectionError, "success"]
    )

    result = await retry_async(mock_fn, max_retries=3)
    assert result == "success"
    assert mock_fn.call_count == 3


# --- Patching async methods ---

async def test_external_service():
    with patch("myapp.services.fetch_weather", new_callable=AsyncMock) as mock:
        mock.return_value = {"temp": 72, "condition": "sunny"}

        result = await get_dashboard_data("user-123")
        assert result["weather"]["temp"] == 72


# --- Testing async generators ---

async def test_stream_events():
    """Test async generator output."""
    events = []
    async for event in stream_events(limit=5):
        events.append(event)

    assert len(events) == 5
    assert all("timestamp" in e for e in events)


async def test_stream_cancellation():
    """Test that stream handles cancellation gracefully."""
    count = 0
    async for event in stream_events(limit=100):
        count += 1
        if count >= 3:
            break  # Should not leak resources

    # Verify cleanup happened
    assert count == 3


# --- Testing timeouts ---

async def test_operation_timeout():
    """Verify timeout behavior."""
    with pytest.raises(asyncio.TimeoutError):
        async with asyncio.timeout(0.1):
            await slow_operation()


async def test_graceful_timeout_handling():
    """Test that timeout returns fallback."""
    result = await fetch_with_timeout("http://slow.example.com", timeout=0.01)
    assert result is None  # Function returns None on timeout


# --- Testing concurrent operations ---

async def test_concurrent_safety():
    """Test that concurrent access is safe."""
    counter = AtomicCounter()

    async def increment_many():
        for _ in range(100):
            await counter.increment()

    async with asyncio.TaskGroup() as tg:
        for _ in range(10):
            tg.create_task(increment_many())

    assert counter.value == 1000


# --- HTTPX test client (FastAPI) ---

from httpx import ASGITransport, AsyncClient
from myapp import app

@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_api_endpoint(client: AsyncClient):
    response = await client.get("/api/users")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)


async def test_authenticated_endpoint(client: AsyncClient):
    # Login
    login = await client.post("/api/auth/login", json={
        "email": "test@test.com", "password": "secret",
    })
    token = login.json()["access_token"]

    # Authenticated request
    response = await client.get(
        "/api/profile",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
```

Async testing patterns:
1. **`asyncio_mode = "auto"`** — no need for `@pytest.mark.asyncio` decorator
2. **`AsyncMock`** — mock async functions with `side_effect` lists for retry testing
3. **`@pytest_asyncio.fixture`** — async setup/teardown with `yield`
4. **`ASGITransport`** — test FastAPI without starting a real server
5. **`TaskGroup` in tests** — verify concurrent safety by running parallel operations'''
    ),
]
"""
