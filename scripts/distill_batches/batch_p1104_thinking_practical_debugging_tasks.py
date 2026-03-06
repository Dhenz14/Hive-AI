"""Thinking-trace pairs: real-world debugging tasks with vague requests."""

PAIRS = [
    (
        "thinking/practical",
        r'''this works in Python 3.9 but breaks in 3.12, no idea why

import asyncio
import datetime
import configparser
from collections import OrderedDict

config = configparser.ConfigParser()
config.read("settings.ini")

class TaskRunner:
    def __init__(self):
        self.tasks = OrderedDict()
        self.loop = asyncio.get_event_loop()

    def run(self, coro):
        return self.loop.run_until_complete(coro)

    def schedule(self, name, coro):
        self.tasks[name] = coro

    def run_all(self):
        for name, coro in self.tasks.items():
            print(f"Running {name} at {datetime.datetime.utcnow()}")
            self.run(coro)

    def get_setting(self, key):
        return config.get("DEFAULT", key)

async def fetch_data():
    await asyncio.sleep(1)
    return {"data": "value"}

runner = TaskRunner()
runner.schedule("fetch", fetch_data())
runner.run_all()''',
        r'''<think>
Let me trace through the code and identify what changed between Python 3.9 and 3.12 that would break this.

1. `asyncio.get_event_loop()` -- This is the big one. In Python 3.10+, calling `asyncio.get_event_loop()` when there is no running event loop raises a DeprecationWarning, and in 3.12 it raises an error in some contexts. The recommended approach since 3.10 is `asyncio.new_event_loop()` or `asyncio.run()`.

2. `datetime.datetime.utcnow()` -- Deprecated in Python 3.12. It returns a naive datetime and the deprecation warning says to use `datetime.datetime.now(datetime.UTC)` instead. This would not cause a crash but produces warnings.

3. `OrderedDict` -- Still works fine, but regular dicts have been insertion-ordered since 3.7, so it is unnecessary.

4. `configparser` -- No breaking changes I know of between 3.9 and 3.12.

5. The coroutine handling: `fetch_data()` is called immediately (creating a coroutine object) and stored. When `run_all` tries to run it, it might work but there could be issues with coroutine reuse if it were scheduled multiple times. Actually, the bigger issue is that in 3.12, `asyncio.get_event_loop()` in `__init__` will likely emit a DeprecationWarning or fail because there is no current event loop at module level.

The primary breaking change is #1: `asyncio.get_event_loop()`.

In Python 3.9: `get_event_loop()` would create a new event loop if none existed.
In Python 3.10+: It emits a DeprecationWarning if no running event loop.
In Python 3.12: The behavior changed more strictly -- it will raise a DeprecationWarning always when called outside of an async context, and may not auto-create the loop.

Actually, the exact change: in 3.10+ `get_event_loop()` emits DeprecationWarning if there is no current event loop. In 3.12 it still works but the warning is more aggressive. The actual error would depend on the context.

Let me also check: is there anything else? The `configparser.ConfigParser` class had some changes but nothing breaking.

Let me provide fixes for all the deprecations and the actual breaking change.
</think>

The main breaking change is `asyncio.get_event_loop()`. In Python 3.9, this would silently create a new event loop if none existed. In 3.10+ it emits a DeprecationWarning, and in 3.12 it can fail outright when called outside of an async context. You also have a `datetime.utcnow()` deprecation.

Here is every issue and the fix:

**Issue 1 (BREAKING): `asyncio.get_event_loop()` behavior change**

```python
# Python 3.9: Creates a new event loop if none exists
loop = asyncio.get_event_loop()  # works silently

# Python 3.10-3.11: DeprecationWarning if no current event loop
loop = asyncio.get_event_loop()  # warning but still works

# Python 3.12: Stricter -- may raise RuntimeError in some contexts
loop = asyncio.get_event_loop()  # can fail
```

**Issue 2 (WARNING): `datetime.datetime.utcnow()` deprecated in 3.12**

```python
# Python 3.9-3.11: Works fine
now = datetime.datetime.utcnow()

# Python 3.12: DeprecationWarning
# "datetime.utcnow() is deprecated, use datetime.now(datetime.UTC) instead"
now = datetime.datetime.utcnow()
```

**Issue 3 (STYLE): `OrderedDict` is unnecessary since Python 3.7**

Regular dicts maintain insertion order since Python 3.7. `OrderedDict` still works but adds overhead for no benefit.

**The fixed code:**

```python
import asyncio
import datetime
from typing import Coroutine, Any

# configparser is fine -- no changes needed
import configparser

config = configparser.ConfigParser()
config.read("settings.ini")


class TaskRunner:
    """Runs async tasks sequentially.

    Fixed for Python 3.10+ compatibility:
    - Uses asyncio.run() instead of manual event loop management
    - Or asyncio.new_event_loop() when you need a persistent loop
    """

    def __init__(self):
        # Use a regular dict -- insertion-ordered since Python 3.7
        self.tasks: dict[str, Coroutine[Any, Any, Any]] = {}

    def run(self, coro):
        """Run a single coroutine.

        asyncio.run() is the correct way since Python 3.7+.
        It creates a new event loop, runs the coroutine, and closes the loop.
        """
        return asyncio.run(coro)

    def schedule(self, name: str, coro_func, *args, **kwargs):
        """Schedule a coroutine FACTORY (not an already-created coroutine).

        IMPORTANT: Store the function + args, not the coroutine object.
        A coroutine object can only be awaited once. If you store the
        result of `fetch_data()`, you cannot rerun it.
        """
        self.tasks[name] = (coro_func, args, kwargs)

    def run_all(self):
        """Run all scheduled tasks sequentially."""
        for name, (coro_func, args, kwargs) in self.tasks.items():
            # Use timezone-aware UTC time (Python 3.12+ compatible)
            now = datetime.datetime.now(datetime.timezone.utc)
            print(f"Running {name} at {now.isoformat()}")

            # Create a fresh coroutine for each run
            result = asyncio.run(coro_func(*args, **kwargs))
            print(f"  {name} completed with result: {result}")

    async def run_all_concurrent(self):
        """Run all scheduled tasks concurrently (faster).

        Use this when tasks are independent and can run in parallel.
        """
        tasks = []
        for name, (coro_func, args, kwargs) in self.tasks.items():
            now = datetime.datetime.now(datetime.timezone.utc)
            print(f"Starting {name} at {now.isoformat()}")
            tasks.append(asyncio.create_task(coro_func(*args, **kwargs)))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        for (name, _), result in zip(self.tasks.items(), results):
            if isinstance(result, Exception):
                print(f"  {name} FAILED: {result}")
            else:
                print(f"  {name} completed: {result}")

        return results

    def get_setting(self, key: str) -> str:
        return config.get("DEFAULT", key)


async def fetch_data():
    await asyncio.sleep(1)
    return {"data": "value"}


# --- Usage ---

# Sequential execution
runner = TaskRunner()
runner.schedule("fetch", fetch_data)  # pass the function, NOT fetch_data()
runner.run_all()

# Concurrent execution (faster when tasks are independent)
runner2 = TaskRunner()
runner2.schedule("fetch_1", fetch_data)
runner2.schedule("fetch_2", fetch_data)
asyncio.run(runner2.run_all_concurrent())
```

**If you need a persistent event loop (e.g., for a long-running service):**

```python
class PersistentTaskRunner:
    """For cases where you need to keep the event loop alive
    across multiple operations (like a background service).
    """

    def __init__(self):
        self.tasks = {}
        # Explicitly create a new loop instead of get_event_loop()
        self._loop = asyncio.new_event_loop()

    def run(self, coro):
        return self._loop.run_until_complete(coro)

    def close(self):
        """Always close the loop when done."""
        self._loop.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# Usage:
with PersistentTaskRunner() as runner:
    result = runner.run(fetch_data())
# Loop is automatically closed
```

**Complete list of Python 3.9 -> 3.12 breaking changes to watch for:**

| Removed/Changed | Version | Replacement |
|---|---|---|
| `asyncio.get_event_loop()` auto-create | 3.10+ | `asyncio.run()` or `asyncio.new_event_loop()` |
| `datetime.utcnow()` | 3.12 | `datetime.now(datetime.timezone.utc)` |
| `datetime.utcfromtimestamp()` | 3.12 | `datetime.fromtimestamp(ts, tz=datetime.timezone.utc)` |
| `typing.Optional[X]` needed | 3.10+ | `X \| None` (PEP 604) |
| `typing.Union[X, Y]` needed | 3.10+ | `X \| Y` (PEP 604) |
| `typing.List`, `typing.Dict` | 3.9+ | `list`, `dict` (built-in generics) |
| `imp` module | 3.12 removed | `importlib` |
| `distutils` module | 3.12 removed | `setuptools` |
| `asyncio.coroutine` decorator | 3.11 removed | `async def` |
| `loop.create_task()` before run | 3.10+ | Create tasks inside `async def` |
| `configparser` legacy interpolation | 3.12 | Use `BasicInterpolation` or `ExtendedInterpolation` |

Run `python -W all your_script.py` to see all deprecation warnings in your current code before they become errors in the next Python version.'''),
    (
        "thinking/practical",
        r'''my async code is somehow slower than the sync version''',
        r'''<think>
Async code being slower than sync is a very common complaint, and it usually comes down to one of these causes:

1. Blocking code in async functions -- the most common mistake. If you call a blocking function (like `requests.get()`, `time.sleep()`, CPU-heavy computation) inside an async function, it blocks the entire event loop. The single thread running the event loop just waits, and no other coroutines can run.

2. Not actually running things concurrently -- writing `await func_a(); await func_b()` runs them sequentially. You need `asyncio.gather(func_a(), func_b())` for concurrency.

3. Creating a new connection per request instead of reusing connections. `aiohttp.ClientSession` / `httpx.AsyncClient` should be created ONCE and reused. Creating a new session per request means a new TCP connection + TLS handshake each time.

4. Overhead of asyncio for simple tasks -- if you are just making one request and waiting for it, async adds overhead (event loop, coroutine creation) with zero benefit. Async only helps when you have multiple I/O operations to overlap.

5. Using async database drivers without connection pooling -- creating a new connection per query defeats the purpose.

I should show the before/after for each of these, with timing comparisons.
</think>

Async code is slower than sync when it is not actually running concurrently, or when blocking code is sneaking into the event loop. Here are the most common causes and fixes.

**Cause 1: Blocking calls inside async functions (most common)**

```python
import asyncio
import time
import httpx
import requests  # sync library


# BROKEN: This is slower than sync because requests.get() blocks the event loop.
# While waiting for one request, NO other coroutines can run.
async def fetch_urls_broken(urls: list[str]) -> list[str]:
    results = []
    for url in urls:
        # requests.get is BLOCKING -- it freezes the entire event loop
        response = requests.get(url)  # <-- THE PROBLEM
        results.append(response.text)
    return results


# FIXED: Use an async HTTP client
async def fetch_urls_fixed(urls: list[str]) -> list[str]:
    async with httpx.AsyncClient() as client:
        # Run all requests concurrently with gather
        tasks = [client.get(url) for url in urls]
        responses = await asyncio.gather(*tasks)
        return [r.text for r in responses]


# Timing comparison for 10 URLs (each takes ~200ms):
# Broken async:  ~2000ms (sequential, event loop blocked)
# Sync requests:  ~2000ms (sequential, same speed)
# Fixed async:    ~250ms  (concurrent, 8x faster)
```

**Cause 2: Sequential awaits instead of concurrent execution**

```python
# SLOW: Sequential -- each await waits for the previous one to finish
async def get_user_profile_slow(user_id: int):
    user = await fetch_user(user_id)          # 100ms
    orders = await fetch_orders(user_id)       # 150ms
    recommendations = await fetch_recs(user_id) # 200ms
    # Total: 450ms (sequential)
    return {"user": user, "orders": orders, "recs": recommendations}


# FAST: Concurrent -- all three run at the same time
async def get_user_profile_fast(user_id: int):
    user, orders, recommendations = await asyncio.gather(
        fetch_user(user_id),          # 100ms \
        fetch_orders(user_id),         # 150ms  > all at once
        fetch_recs(user_id),           # 200ms /
    )
    # Total: 200ms (limited by the slowest one)
    return {"user": user, "orders": orders, "recs": recommendations}


# FAST with error handling: If one fails, others still complete
async def get_user_profile_safe(user_id: int):
    results = await asyncio.gather(
        fetch_user(user_id),
        fetch_orders(user_id),
        fetch_recs(user_id),
        return_exceptions=True,  # do not cancel others if one fails
    )

    user, orders, recs = results
    return {
        "user": user if not isinstance(user, Exception) else None,
        "orders": orders if not isinstance(orders, Exception) else [],
        "recs": recs if not isinstance(recs, Exception) else [],
    }
```

**Cause 3: Creating new connections per request**

```python
# SLOW: New TCP connection + TLS handshake for EVERY request
async def fetch_many_slow(urls: list[str]):
    results = []
    for url in urls:
        # Creates and destroys a connection each time
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            results.append(response.text)
    return results


# FAST: Reuse one client (connection pooling + keep-alive)
async def fetch_many_fast(urls: list[str]):
    # One client = one connection pool, shared across all requests
    async with httpx.AsyncClient(
        timeout=30.0,
        limits=httpx.Limits(
            max_connections=20,      # max total connections
            max_keepalive_connections=10,  # keep this many alive
        ),
    ) as client:
        tasks = [client.get(url) for url in urls]
        responses = await asyncio.gather(*tasks)
        return [r.text for r in responses]


# For a web app: Create the client ONCE at startup, reuse everywhere
class APIClient:
    """Manages a shared HTTP client with connection pooling."""

    def __init__(self):
        self._client: httpx.AsyncClient | None = None

    async def startup(self):
        self._client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=50),
        )

    async def shutdown(self):
        if self._client:
            await self._client.aclose()

    @property
    def client(self) -> httpx.AsyncClient:
        if not self._client:
            raise RuntimeError("Client not initialized -- call startup() first")
        return self._client


# FastAPI integration:
api_client = APIClient()

@app.on_event("startup")
async def startup():
    await api_client.startup()

@app.on_event("shutdown")
async def shutdown():
    await api_client.shutdown()
```

**Cause 4: CPU-bound work blocking the event loop**

```python
import hashlib
from concurrent.futures import ProcessPoolExecutor

# BROKEN: CPU-heavy work blocks the event loop
async def process_file_broken(data: bytes) -> str:
    # This runs on the event loop thread -- blocks ALL other coroutines
    return hashlib.sha256(data).hexdigest()


# FIXED: Offload CPU-bound work to a thread/process pool
executor = ProcessPoolExecutor(max_workers=4)

def _hash_data(data: bytes) -> str:
    """This runs in a separate process, not on the event loop."""
    return hashlib.sha256(data).hexdigest()

async def process_file_fixed(data: bytes) -> str:
    loop = asyncio.get_running_loop()
    # run_in_executor runs the function in a separate thread/process
    result = await loop.run_in_executor(executor, _hash_data, data)
    return result


# For file I/O (also blocking):
async def read_file_wrong(path: str) -> str:
    # open() and read() are blocking system calls
    with open(path) as f:
        return f.read()  # blocks event loop

async def read_file_right(path: str) -> str:
    # Use aiofiles for non-blocking file I/O
    import aiofiles
    async with aiofiles.open(path) as f:
        return await f.read()
```

**Cause 5: Database queries without async driver or pooling**

```python
# SLOW: Sync database driver blocks the event loop
import psycopg2

async def get_users_broken():
    conn = psycopg2.connect("postgresql://...")  # BLOCKS
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users")  # BLOCKS
    return cursor.fetchall()


# FAST: Async driver with connection pool
import asyncpg

# Create pool once at startup
pool: asyncpg.Pool = None

async def init_db():
    global pool
    pool = await asyncpg.create_pool(
        "postgresql://...",
        min_size=5,
        max_size=20,
    )

async def get_users_fast():
    async with pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM users")
```

**Diagnostic: Find blocking calls in your async code**

```python
import asyncio
import logging
import time

# Enable slow callback detection -- logs when the event loop is blocked
# for more than the threshold
def enable_blocking_detection(threshold_ms: int = 100):
    """Log a warning when any callback blocks the event loop.

    The event loop runs callbacks one at a time. If a callback takes
    longer than threshold_ms, it means something is blocking.
    """
    loop = asyncio.get_event_loop()
    loop.slow_callback_duration = threshold_ms / 1000.0

    # Enable debug mode for detailed info
    loop.set_debug(True)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


# Usage:
# enable_blocking_detection(threshold_ms=100)
# asyncio.run(main())
#
# Output when something blocks:
# WARNING:asyncio:Executing <Task ...> took 0.523 seconds
```

**Decision guide: When async actually helps**

| Scenario | Use async? | Why |
|---|---|---|
| Many concurrent HTTP requests | Yes | Overlap I/O wait times |
| Single API call and return | No | Async adds overhead, no concurrency |
| Database queries in a web handler | Yes | Concurrent requests share the pool |
| CPU-heavy computation | No | Use multiprocessing instead |
| File I/O heavy | Maybe | aiofiles helps, but often threading is simpler |
| WebSocket connections | Yes | Need to handle many long-lived connections |

The rule of thumb: async only helps when you have multiple I/O operations that can overlap. If your code is sequential by nature, async will be the same speed or slower than sync.'''),
    (
        "thinking/practical",
        r'''users report they sometimes see other users' data''',
        r'''<think>
This is a critical security issue -- data leaking between users. This is one of the most serious bugs possible in a web application. Let me think about common causes:

1. Shared mutable state / global variables
   - A global variable or module-level dict that stores user data
   - In a multi-threaded web server, requests from different users can read/write the same variable
   - Example: storing `current_user` in a module-level variable

2. Cache key collisions or missing user scoping
   - Cache key is "/api/profile" instead of "/api/profile:user_123"
   - CDN caching pages with user-specific content
   - Response with `Cache-Control: public` on authenticated endpoints

3. Database query missing WHERE clause
   - `SELECT * FROM orders` instead of `SELECT * FROM orders WHERE user_id = ?`
   - ORM query missing filter

4. Session/cookie issues
   - Session fixation (attacker sets victim's session ID)
   - Session not regenerated after login
   - Set-Cookie without Secure/HttpOnly flags

5. Connection pooling and shared state in ORM
   - SQLAlchemy session being shared across requests
   - Database connection returned to pool with uncommitted transaction

6. Race conditions in async code
   - Storing user context in a mutable shared object
   - Task-local storage not used correctly

The "sometimes" nature of the bug strongly suggests either:
- A caching issue (most likely -- the first user's response gets cached and served to the second user)
- A global variable race condition (happens under concurrent load)

I need to provide diagnostic steps + fixes for each potential cause.
</think>

This is a critical security bug called a "data leak" or "cross-user data exposure." The "sometimes" nature points to either a caching issue or a shared mutable state race condition. Here is how to diagnose and fix it.

**Step 1: Emergency diagnosis -- find the leak source**

```python
# Add this middleware IMMEDIATELY to trace the issue.
# It logs user identity alongside request/response details
# so you can correlate "who saw whose data."

import uuid
import logging
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("security.audit")


class DataLeakDetectionMiddleware(BaseHTTPMiddleware):
    """Logs request identity info to help trace cross-user data leaks.

    Add this as the OUTERMOST middleware so it wraps everything.
    """

    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())[:8]

        # Capture identity signals
        auth_header = request.headers.get("Authorization", "none")[:30]
        session_id = request.cookies.get("session_id", "none")[:16]
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("User-Agent", "")[:50]

        logger.info(
            "REQUEST %s | method=%s path=%s | auth=%s session=%s ip=%s ua=%s",
            request_id,
            request.method,
            request.url.path,
            auth_header,
            session_id,
            client_ip,
            user_agent,
        )

        response = await call_next(request)

        # Log cache headers -- if these are wrong, that is likely the cause
        cache_control = response.headers.get("Cache-Control", "NOT SET")
        vary = response.headers.get("Vary", "NOT SET")

        logger.info(
            "RESPONSE %s | status=%d | cache-control=%s vary=%s",
            request_id,
            response.status_code,
            cache_control,
            vary,
        )

        # Add request ID header for debugging
        response.headers["X-Request-ID"] = request_id
        return response
```

**Fix 1: Caching issues (most common cause)**

```python
# BROKEN: Caching authenticated responses
# If your CDN or reverse proxy caches this, User B sees User A's profile

from fastapi import FastAPI, Depends
from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/api/profile")
async def get_profile(user=Depends(get_current_user)):
    return {"name": user.name, "email": user.email}
    # Response has NO cache headers -> CDN may cache it with default TTL
    # Next user hitting /api/profile gets the FIRST user's data


# FIXED: Explicitly prevent caching of authenticated endpoints

from functools import wraps

def no_cache_response(data: dict, status_code: int = 200) -> JSONResponse:
    """Return a JSON response that is explicitly not cacheable."""
    return JSONResponse(
        content=data,
        status_code=status_code,
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, private",
            "Pragma": "no-cache",
            "Vary": "Authorization, Cookie",
        },
    )


@app.get("/api/profile")
async def get_profile_fixed(user=Depends(get_current_user)):
    return no_cache_response({
        "name": user.name,
        "email": user.email,
    })


# Even better: Add a middleware that sets cache headers for ALL authenticated routes

class NoCacheAuthMiddleware(BaseHTTPMiddleware):
    """Prevent caching of any response that required authentication."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        # If the request had auth credentials, the response is user-specific
        has_auth = (
            request.headers.get("Authorization")
            or request.cookies.get("session_id")
        )

        if has_auth:
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["Vary"] = "Authorization, Cookie"

        return response
```

**Fix 2: Global / shared mutable state**

```python
# BROKEN: Module-level mutable state shared across requests
# In a threaded server (gunicorn with threads, uvicorn), multiple
# requests execute concurrently and share this variable.

# app/state.py
current_user = None  # <-- DISASTER: shared across all threads

# app/middleware.py
async def auth_middleware(request, call_next):
    import app.state
    app.state.current_user = await get_user_from_token(request)  # Thread A sets User A
    response = await call_next(request)  # Thread B overwrites with User B
    return response  # Thread A reads current_user... which is now User B


# FIXED: Use request-scoped state

# Option A: FastAPI dependency injection (recommended)
async def get_current_user(request: Request) -> User:
    """Each request gets its own user via dependency injection.
    No shared state, no race conditions."""
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return await verify_and_decode_token(token)


@app.get("/api/profile")
async def get_profile(user: User = Depends(get_current_user)):
    # `user` is scoped to THIS request only
    return {"name": user.name}


# Option B: Request state (for middleware)
async def auth_middleware_fixed(request: Request, call_next):
    # request.state is per-request, not shared
    user = await get_user_from_token(request)
    request.state.user = user  # safe -- request.state is per-request
    response = await call_next(request)
    return response


# Option C: contextvars for async code (like thread-locals but for async)
import contextvars

_current_user: contextvars.ContextVar[User] = contextvars.ContextVar("current_user")

async def auth_middleware_contextvar(request: Request, call_next):
    user = await get_user_from_token(request)
    token = _current_user.set(user)  # scoped to this async context
    try:
        response = await call_next(request)
    finally:
        _current_user.reset(token)
    return response

# Access from anywhere in the call chain:
def get_user() -> User:
    return _current_user.get()
```

**Fix 3: Database query missing user scope**

```python
# BROKEN: Forgetting to filter by user
@app.get("/api/orders")
async def get_orders(db=Depends(get_db), user=Depends(get_current_user)):
    # Missing WHERE user_id = ... returns ALL users' orders
    orders = await db.fetch("SELECT * FROM orders ORDER BY created_at DESC LIMIT 50")
    return orders


# FIXED: Always scope queries to the authenticated user

class ScopedQueryBuilder:
    """Ensures all queries are scoped to the current user.

    This makes it structurally impossible to forget the WHERE clause.
    """

    def __init__(self, db, user_id: int):
        self.db = db
        self.user_id = user_id

    async def fetch_orders(self, limit: int = 50):
        return await self.db.fetch(
            "SELECT * FROM orders WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2",
            self.user_id,
            limit,
        )

    async def fetch_order(self, order_id: int):
        """Get a single order, verifying it belongs to this user."""
        order = await self.db.fetchrow(
            "SELECT * FROM orders WHERE id = $1 AND user_id = $2",
            order_id,
            self.user_id,
        )
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        return order


# Dependency that provides a user-scoped query builder
async def get_scoped_db(
    db=Depends(get_db),
    user=Depends(get_current_user),
) -> ScopedQueryBuilder:
    return ScopedQueryBuilder(db, user.id)


@app.get("/api/orders")
async def get_orders_fixed(scoped_db=Depends(get_scoped_db)):
    # Cannot accidentally return another user's data
    return await scoped_db.fetch_orders()
```

**Fix 4: Session and cache isolation verification**

```python
# Automated test that checks for cross-user data leaks

import pytest
import httpx


@pytest.mark.asyncio
async def test_no_cross_user_data_leak():
    """Verify that User A cannot see User B's data.

    This test should be in your CI pipeline and run on every deploy.
    """
    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        # Create two users
        user_a_token = await create_test_user(client, "user_a@test.com")
        user_b_token = await create_test_user(client, "user_b@test.com")

        # User A creates some data
        await client.post(
            "/api/orders",
            json={"product": "Widget A", "amount": 100},
            headers={"Authorization": f"Bearer {user_a_token}"},
        )

        # User B should NOT see User A's orders
        response = await client.get(
            "/api/orders",
            headers={"Authorization": f"Bearer {user_b_token}"},
        )
        orders = response.json()
        assert len(orders) == 0, "User B can see User A's orders!"

        # Verify User B's profile returns User B's data, not User A's
        response_a = await client.get(
            "/api/profile",
            headers={"Authorization": f"Bearer {user_a_token}"},
        )
        response_b = await client.get(
            "/api/profile",
            headers={"Authorization": f"Bearer {user_b_token}"},
        )
        assert response_a.json()["email"] == "user_a@test.com"
        assert response_b.json()["email"] == "user_b@test.com"


@pytest.mark.asyncio
async def test_no_cache_leak_under_load():
    """Simulate concurrent requests to check for cache-based leaks."""
    import asyncio

    async with httpx.AsyncClient(base_url="http://localhost:8000") as client:
        user_tokens = []
        for i in range(10):
            token = await create_test_user(client, f"user_{i}@test.com")
            user_tokens.append((f"user_{i}@test.com", token))

        # Hit the profile endpoint concurrently
        async def check_profile(email: str, token: str):
            response = await client.get(
                "/api/profile",
                headers={"Authorization": f"Bearer {token}"},
            )
            data = response.json()
            assert data["email"] == email, (
                f"LEAK DETECTED: Expected {email}, got {data['email']}"
            )

        # Run 100 concurrent checks
        tasks = []
        for _ in range(10):
            for email, token in user_tokens:
                tasks.append(check_profile(email, token))

        await asyncio.gather(*tasks)
```

**Checklist of things to verify immediately:**

1. Check CDN/reverse proxy config -- is it caching authenticated responses?
2. Search codebase for global/module-level mutable variables
3. Check `Cache-Control` headers on authenticated endpoints
4. Verify every database query includes `WHERE user_id = ?`
5. Check SQLAlchemy session scope (should be per-request, not per-app)
6. Check Redis cache keys include user ID
7. Run the cross-user data leak test above

Start with #1 (caching) -- it is the cause in about 60% of these bugs.'''),
    (
        "thinking/practical",
        r'''our test suite takes 45 minutes to run''',
        r'''<think>
45 minutes for a test suite is a real productivity killer. Developers stop running tests, CI feedback is slow, and everything slows down. Common causes:

1. No parallel execution -- tests run sequentially on one core
2. Excessive database setup/teardown -- each test creates and destroys the entire schema
3. Network calls in tests -- hitting real APIs without mocking
4. Sleep statements in tests -- time.sleep() waiting for async operations
5. Inefficient fixtures -- heavy fixtures being recreated for every test instead of shared
6. Too many integration/E2E tests, not enough unit tests
7. No test selection -- running ALL tests on every change instead of just affected ones
8. Slow test discovery (pytest collecting thousands of files)
9. Heavy imports at module level

I should provide solutions in order of impact:
1. Parallel execution (usually 3-5x speedup)
2. Database optimization (shared schema, transactions for isolation)
3. Fixture optimization (session-scoped vs function-scoped)
4. Test selection (only run tests affected by the change)
5. Profiling to find the slowest tests
</think>

A 45-minute test suite usually has multiple compounding issues. Here is a systematic approach to cut it down, typically to 5-10 minutes.

**Step 1: Find the bottlenecks (profile first, optimize second)**

```bash
# Find the slowest tests
pytest --durations=30 2>&1 | tail -40

# Output looks like:
# 30 slowest to run
# 12.45s call  tests/test_integration.py::test_full_workflow
# 8.23s call   tests/test_api.py::test_payment_flow
# 5.67s setup  tests/test_db.py::test_user_creation   <-- slow SETUP, not the test itself
```

```python
# conftest.py -- Add timing to find slow fixtures
import time
import pytest

@pytest.fixture(autouse=True)
def _log_test_timing(request):
    """Log timing for every test to identify slow ones."""
    start = time.perf_counter()
    yield
    duration = time.perf_counter() - start
    if duration > 1.0:  # only log tests taking more than 1 second
        print(f"\nSLOW TEST: {request.node.nodeid} took {duration:.2f}s")
```

**Step 2: Parallel execution (biggest single improvement, 3-5x speedup)**

```bash
# Install pytest-xdist
pip install pytest-xdist

# Run tests across all CPU cores
pytest -n auto

# Or specify worker count
pytest -n 8

# Group tests by file to minimize fixture setup overhead
pytest -n auto --dist loadfile
```

```python
# conftest.py -- Make tests safe for parallel execution

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# Each pytest-xdist worker gets its own database
# This prevents tests from interfering with each other
@pytest.fixture(scope="session")
def db_engine(worker_id):
    """Create a separate test database for each parallel worker."""
    if worker_id == "master":
        db_name = "test_db"
    else:
        db_name = f"test_db_{worker_id}"

    # Create the database
    admin_engine = create_engine("postgresql://test:test@localhost/postgres")
    with admin_engine.connect() as conn:
        conn.execution_options(isolation_level="AUTOCOMMIT")
        conn.execute(f"DROP DATABASE IF EXISTS {db_name}")
        conn.execute(f"CREATE DATABASE {db_name}")
    admin_engine.dispose()

    engine = create_engine(f"postgresql://test:test@localhost/{db_name}")

    # Create all tables once per session
    from app.models import Base
    Base.metadata.create_all(engine)

    yield engine

    engine.dispose()
```

**Step 3: Transaction-based test isolation (eliminates teardown overhead)**

```python
# conftest.py -- Use transactions instead of recreating tables for each test

@pytest.fixture(scope="session")
def db_session_factory(db_engine):
    """Session factory scoped to the entire test session."""
    return sessionmaker(bind=db_engine)


@pytest.fixture()
def db_session(db_session_factory):
    """Per-test database session that rolls back after each test.

    This is MUCH faster than creating/dropping tables for each test.
    Each test runs inside a transaction that is rolled back at the end,
    so the database stays clean without any teardown cost.
    """
    session = db_session_factory()
    session.begin_nested()  # SAVEPOINT

    yield session

    session.rollback()  # Undo everything the test did
    session.close()


# Tests automatically get a clean database:
def test_create_user(db_session):
    user = User(name="Alice", email="alice@test.com")
    db_session.add(user)
    db_session.flush()
    assert user.id is not None
    # No cleanup needed -- transaction is rolled back automatically
```

**Step 4: Mock external services (eliminate network calls)**

```python
# conftest.py -- Mock all external HTTP calls by default

import pytest
import responses  # pip install responses
from unittest.mock import patch


@pytest.fixture(autouse=True)
def _block_network(request):
    """Block all real HTTP requests in tests by default.

    Tests that intentionally make network calls can use the
    'allow_network' marker to opt out.
    """
    if "allow_network" in request.keywords:
        yield
        return

    with responses.RequestsMock(assert_all_requests_are_fired=False) as rsps:
        yield rsps


# Register the marker
def pytest_configure(config):
    config.addinivalue_line(
        "markers", "allow_network: Allow real network calls in this test"
    )


# Usage:
def test_api_call(_block_network):
    # Register a mock response
    _block_network.add(
        responses.GET,
        "https://api.example.com/data",
        json={"result": "mocked"},
        status=200,
    )
    # Your code that calls the API will get the mocked response
    result = fetch_from_api()
    assert result == {"result": "mocked"}


@pytest.mark.allow_network
def test_integration_with_real_api():
    # This test is explicitly allowed to make real HTTP calls
    pass
```

**Step 5: Optimize fixtures (session vs function scope)**

```python
# SLOW: Heavy fixture recreated for EVERY test
@pytest.fixture()  # function scope = runs for every test
def sample_data(db_session):
    """Creates 1000 test records -- runs 500 times if you have 500 tests."""
    users = [User(name=f"User {i}") for i in range(1000)]
    db_session.add_all(users)
    db_session.flush()
    return users


# FAST: Shared fixture created once per session
@pytest.fixture(scope="session")
def reference_data(db_engine):
    """Created ONCE, shared across all tests (read-only).

    Use session scope for data that tests only READ, never modify.
    """
    Session = sessionmaker(bind=db_engine)
    session = Session()
    users = [User(name=f"User {i}") for i in range(1000)]
    session.add_all(users)
    session.commit()
    user_ids = [u.id for u in users]
    session.close()
    return user_ids


# FAST: Lazy fixture that only creates what is needed
@pytest.fixture()
def make_user(db_session):
    """Factory fixture -- only creates data when called.

    Much faster than pre-creating data that most tests do not need.
    """
    created = []

    def _make_user(name="Test User", email=None, **kwargs):
        email = email or f"{name.lower().replace(' ', '.')}@test.com"
        user = User(name=name, email=email, **kwargs)
        db_session.add(user)
        db_session.flush()
        created.append(user)
        return user

    yield _make_user
    # Cleanup handled by transaction rollback in db_session fixture


def test_user_profile(make_user):
    # Only creates the ONE user this test needs
    user = make_user(name="Alice")
    assert user.name == "Alice"
```

**Step 6: Selective test running (only run what changed)**

```bash
# pytest-testmon: Only run tests affected by your code changes
pip install pytest-testmon

# First run: collects dependency data (takes normal time)
pytest --testmon

# Subsequent runs: only runs tests affected by changed files
pytest --testmon
# Output: "3 tests deselected (not affected by changes), 12 selected"

# pytest-changed: Run tests for changed files only
pip install pytest-changed
pytest --changed-only

# Manual: Run tests matching a pattern
pytest -k "test_user" tests/
pytest tests/test_api.py  # just one file
```

**Step 7: Configuration for speed**

```ini
# pyproject.toml

[tool.pytest.ini_options]
# Use xdist for parallel execution
addopts = "-n auto --dist loadfile -x --tb=short"
# -n auto: use all CPU cores
# --dist loadfile: group tests by file (better fixture reuse)
# -x: stop on first failure (fast feedback)
# --tb=short: shorter tracebacks

# Faster test discovery
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]

# Do not collect from these directories
norecursedirs = [".git", "node_modules", "venv", "__pycache__", "migrations"]
```

**Expected improvement:**

| Optimization | Speedup | Effort |
|---|---|---|
| Parallel execution (pytest -n auto) | 3-5x | Low (15 min) |
| Transaction-based isolation | 2-3x | Medium (1-2 hours) |
| Mock external services | 1.5-2x | Medium (2-4 hours) |
| Fixture optimization | 1.5-2x | Medium (1-2 hours) |
| Selective test running | 5-10x for incremental runs | Low (15 min) |
| Combined | 10-30x total | |

With all optimizations, a 45-minute suite typically drops to 3-8 minutes for full runs, and under 1 minute for incremental runs during development.'''),
    (
        "thinking/practical",
        r'''the app works fine for a few hours then starts returning 500 errors''',
        r'''<think>
"Works for hours then fails" is the classic symptom of a resource leak. Something is accumulating over time until a limit is hit. The most common causes:

1. Memory leak -- objects being created but never garbage collected
   - Growing caches with no eviction
   - Event listeners being added but never removed
   - Circular references preventing GC
   - Large objects held in closures

2. Connection exhaustion -- database/HTTP/socket connections not being returned to the pool
   - Connections opened but not closed on error paths
   - Connection pool too small for the load
   - Connections becoming stale/broken but not removed from pool

3. File descriptor exhaustion -- files/sockets opened but never closed
   - open() without close() or context manager
   - Subprocess pipes not closed
   - Socket connections not cleaned up

4. Thread/goroutine leak -- threads spawned but never joined
   - Background tasks that accumulate
   - Thread pool growing without bound

5. Disk space -- logs filling up, temp files accumulating
   - No log rotation
   - Temp files not cleaned up

The "few hours" timeframe suggests it is proportional to traffic -- more requests = faster failure. This points to per-request resource leaks (connections, file handles) rather than pure time-based issues.

I should provide:
1. Diagnostic tools to identify the specific leak
2. Common fixes for each type
3. Monitoring to catch leaks before they cause outages
</think>

"Works for hours then breaks" is almost always a resource leak -- something accumulates per request until a limit is hit. Here is how to find and fix it.

**Step 1: Diagnose which resource is leaking**

```python
# resource_monitor.py -- Add this to your app for live monitoring

import os
import gc
import sys
import time
import psutil
import logging
import threading
from collections import Counter
from typing import Optional

logger = logging.getLogger("resource_monitor")


class ResourceMonitor:
    """Periodically logs resource usage to catch leaks early.

    Tracks memory, connections, file descriptors, and threads over time.
    When any metric trends upward continuously, you have a leak.
    """

    def __init__(self, interval_seconds: int = 60):
        self.interval = interval_seconds
        self.process = psutil.Process(os.getpid())
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.history: list[dict] = []

    def start(self):
        """Start background monitoring."""
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Resource monitor started (interval=%ds)", self.interval)

    def stop(self):
        self._running = False

    def _monitor_loop(self):
        while self._running:
            snapshot = self.take_snapshot()
            self.history.append(snapshot)

            # Keep last 60 snapshots (1 hour at 60s interval)
            if len(self.history) > 60:
                self.history = self.history[-60:]

            # Check for concerning trends
            self._check_trends()

            time.sleep(self.interval)

    def take_snapshot(self) -> dict:
        """Capture current resource usage."""
        mem = self.process.memory_info()
        connections = self.process.connections()

        snapshot = {
            "timestamp": time.time(),
            "memory_rss_mb": mem.rss / 1024 / 1024,
            "memory_vms_mb": mem.vms / 1024 / 1024,
            "open_files": len(self.process.open_files()),
            "connections_total": len(connections),
            "connections_established": sum(
                1 for c in connections if c.status == "ESTABLISHED"
            ),
            "connections_close_wait": sum(
                1 for c in connections if c.status == "CLOSE_WAIT"
            ),
            "thread_count": self.process.num_threads(),
            "gc_objects": len(gc.get_objects()),
            "gc_collections": {
                f"gen{i}": gc.get_stats()[i]["collections"]
                for i in range(3)
            },
        }

        logger.info(
            "RESOURCES: mem=%.0fMB conns=%d(%d CLOSE_WAIT) fds=%d threads=%d gc_objects=%d",
            snapshot["memory_rss_mb"],
            snapshot["connections_total"],
            snapshot["connections_close_wait"],
            snapshot["open_files"],
            snapshot["thread_count"],
            snapshot["gc_objects"],
        )

        return snapshot

    def _check_trends(self):
        """Alert if resources are trending upward (leak indicator)."""
        if len(self.history) < 5:
            return

        recent = self.history[-5:]

        # Check memory trend
        mem_values = [s["memory_rss_mb"] for s in recent]
        if all(mem_values[i] < mem_values[i + 1] for i in range(len(mem_values) - 1)):
            growth = mem_values[-1] - mem_values[0]
            logger.warning(
                "POSSIBLE MEMORY LEAK: RSS grew %.1fMB over last %d snapshots (%.0f -> %.0f MB)",
                growth,
                len(recent),
                mem_values[0],
                mem_values[-1],
            )

        # Check connection trend
        conn_values = [s["connections_total"] for s in recent]
        if all(conn_values[i] <= conn_values[i + 1] for i in range(len(conn_values) - 1)):
            if conn_values[-1] > conn_values[0] + 10:
                logger.warning(
                    "POSSIBLE CONNECTION LEAK: connections grew from %d to %d",
                    conn_values[0],
                    conn_values[-1],
                )

        # Check CLOSE_WAIT (connections not properly closed)
        close_wait = recent[-1]["connections_close_wait"]
        if close_wait > 10:
            logger.warning(
                "HIGH CLOSE_WAIT COUNT: %d connections in CLOSE_WAIT (not being closed properly)",
                close_wait,
            )

    def get_top_memory_types(self, top_n: int = 20) -> list[tuple[str, int]]:
        """Find which object types are using the most memory.

        Run this when memory is high to find what is accumulating.
        """
        type_counts = Counter(type(obj).__name__ for obj in gc.get_objects())
        return type_counts.most_common(top_n)


# --- Integration ---

monitor = ResourceMonitor(interval_seconds=60)

# FastAPI startup/shutdown:
# @app.on_event("startup")
# async def startup():
#     monitor.start()
#
# @app.on_event("shutdown")
# async def shutdown():
#     monitor.stop()
```

**Step 2: Fix the most common leaks**

**Connection leak (most likely cause for 500 errors after hours):**

```python
# LEAKING: Connection not returned to pool on error
async def get_user_leaking(user_id: int):
    conn = await db_pool.acquire()  # get connection from pool
    try:
        result = await conn.fetch("SELECT * FROM users WHERE id = $1", user_id)
        return result
    except Exception:
        # If an exception occurs, conn is NEVER released back to the pool
        raise
    # conn.release() never called on error path
    # After N errors, pool is exhausted -> all new requests get 500


# FIXED: Always return connection to pool
async def get_user_fixed(user_id: int):
    async with db_pool.acquire() as conn:  # context manager ALWAYS releases
        result = await conn.fetch("SELECT * FROM users WHERE id = $1", user_id)
        return result


# For SQLAlchemy: Same pattern
# LEAKING:
def get_data_leaking():
    session = Session()
    try:
        return session.query(User).all()
    except Exception:
        raise  # session never closed on error

# FIXED:
def get_data_fixed():
    with Session() as session:  # context manager handles close
        return session.query(User).all()
```

**Memory leak -- unbounded cache:**

```python
# LEAKING: Cache grows forever
_cache = {}

async def get_product(product_id: int):
    if product_id not in _cache:
        _cache[product_id] = await fetch_from_db(product_id)
    return _cache[product_id]
    # After millions of unique product lookups, cache eats all memory


# FIXED: Use LRU cache with a max size
from functools import lru_cache
from cachetools import TTLCache

# Option A: functools.lru_cache (sync only, fixed max size)
@lru_cache(maxsize=10000)
def get_product_sync(product_id: int):
    return fetch_from_db_sync(product_id)

# Option B: TTLCache (entries expire after a time)
_cache = TTLCache(maxsize=10000, ttl=300)  # max 10K items, 5 min TTL

async def get_product_ttl(product_id: int):
    if product_id not in _cache:
        _cache[product_id] = await fetch_from_db(product_id)
    return _cache[product_id]
```

**File descriptor leak:**

```python
# LEAKING: File opened but never closed on error
def process_upload_leaking(filepath: str):
    f = open(filepath, "rb")
    data = f.read()
    # If process_data() throws, f is never closed
    result = process_data(data)
    f.close()  # never reached on error
    return result

# FIXED: Always use context managers
def process_upload_fixed(filepath: str):
    with open(filepath, "rb") as f:
        data = f.read()
    # f is closed even if process_data throws
    return process_data(data)
```

**Step 3: Add health checks that detect leaks**

```python
# health.py -- Health endpoint that reports resource usage

from fastapi import FastAPI, Response
import psutil
import os

app = FastAPI()

# Thresholds that trigger unhealthy status
MAX_MEMORY_MB = 512
MAX_CONNECTIONS = 100
MAX_OPEN_FILES = 200


@app.get("/health")
async def health_check():
    """Health check that catches resource leaks before they cause 500s."""
    process = psutil.Process(os.getpid())
    mem_mb = process.memory_info().rss / 1024 / 1024
    connections = len(process.connections())
    open_files = len(process.open_files())
    issues = []

    if mem_mb > MAX_MEMORY_MB:
        issues.append(f"Memory high: {mem_mb:.0f}MB (limit {MAX_MEMORY_MB}MB)")

    if connections > MAX_CONNECTIONS:
        issues.append(f"Connections high: {connections} (limit {MAX_CONNECTIONS})")

    if open_files > MAX_OPEN_FILES:
        issues.append(f"Open files high: {open_files} (limit {MAX_OPEN_FILES})")

    if issues:
        # Return 503 so load balancer stops sending traffic
        # and orchestrator restarts the container
        return Response(
            content=f'{{"status": "unhealthy", "issues": {issues}}}',
            status_code=503,
            media_type="application/json",
        )

    return {
        "status": "healthy",
        "metrics": {
            "memory_mb": round(mem_mb, 1),
            "connections": connections,
            "open_files": open_files,
        },
    }
```

**Step 4: Kubernetes/Docker auto-restart on resource limits**

```yaml
# kubernetes deployment -- auto-restart leaky containers
spec:
  containers:
    - name: app
      resources:
        limits:
          memory: "512Mi"  # OOMKilled if exceeded
        requests:
          memory: "256Mi"
      livenessProbe:
        httpGet:
          path: /health
          port: 8000
        initialDelaySeconds: 30
        periodSeconds: 30
        failureThreshold: 3  # restart after 3 failed health checks
```

**Diagnosis flowchart:**

```
App starts returning 500s after hours
    |
    +-- Check memory (RSS growing over time?)
    |   Yes -> Memory leak: unbounded cache, circular refs, large closures
    |
    +-- Check connections (total or CLOSE_WAIT growing?)
    |   Yes -> Connection leak: missing close/release on error paths
    |
    +-- Check open files (fd count growing?)
    |   Yes -> File descriptor leak: open() without context manager
    |
    +-- Check threads (thread count growing?)
    |   Yes -> Thread leak: spawning threads without joining
    |
    +-- Check disk space
    |   Yes -> Logs filling up, temp files accumulating
    |
    +-- Check error logs for specific exception
        -> The exception message will tell you which resource is exhausted
```

Start with the `ResourceMonitor` class -- run it for an hour and the logs will make the leak obvious. The most common cause by far is database connections not being released on error paths.'''),
]
