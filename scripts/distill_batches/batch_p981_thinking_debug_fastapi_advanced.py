"""Thinking-trace pairs: advanced FastAPI debugging."""

PAIRS = [
    (
        "thinking/debugging",
        r'''I'm writing tests for my FastAPI application and need to override a dependency, but the override is not taking effect. Here is my code:

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

app = FastAPI()

def get_db():
    return RealDatabase()

def get_current_user(db=Depends(get_db)):
    return db.get_user(token)

@app.get("/profile")
def profile(user=Depends(get_current_user)):
    return {"name": user.name}

# In tests:
def override_get_db():
    return FakeDatabase()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)
response = client.get("/profile")
# Still hitting real database!

Why is the override not working?''',
        r'''<think>
Let me think about why dependency overrides might not work in FastAPI.

The common issues with dependency_overrides are:

1. The override key must be the exact same function object, not a different function with the same name. If the import paths differ, the function objects are different.

2. If get_db is imported in two different ways (e.g., `from app.deps import get_db` vs `import app.deps; app.deps.get_db`), the override might reference a different function object than the one used in the route.

3. The nested dependency issue: even if you override get_db, the get_current_user function still depends on get_db. If get_current_user is also problematic, you might need to override it too.

4. TestClient creation timing: if the TestClient is created before the override is set, it might not pick up the change (though in practice FastAPI checks overrides at request time, not at TestClient creation time).

5. The most common issue: the function reference used as the key in dependency_overrides must be the EXACT same function object used in Depends(). If you have circular imports or re-exports, the references might differ.

Let me also address the fact that get_current_user itself has logic (db.get_user(token)) that will fail -- even if db is overridden, `token` is not defined in the scope shown.
</think>

The most common reason dependency overrides fail in FastAPI is that the **function reference used as the key does not match** the function reference used in `Depends()`. Here is a complete diagnosis and fix:

```python
# ============================================================
# app/deps.py - Shared dependencies
# ============================================================
from fastapi import Depends

def get_db():
    """Return a real database session."""
    db = RealDatabase()
    try:
        yield db
    finally:
        db.close()

def get_current_user(db=Depends(get_db)):
    """Get user from auth token."""
    # ... authentication logic ...
    return db.get_user_by_token("some_token")


# ============================================================
# app/main.py - Application
# ============================================================
from fastapi import FastAPI, Depends
# CRITICAL: import from the SAME module path
from app.deps import get_db, get_current_user

app = FastAPI()

@app.get("/profile")
def profile(user=Depends(get_current_user)):
    return {"name": user.name}


# ============================================================
# tests/test_profile.py - Tests (WRONG)
# ============================================================
from fastapi.testclient import TestClient
# BUG: if you import get_db from a DIFFERENT path, the override fails
# from app.deps import get_db  <-- this works
# from app.main import get_db  <-- this might be a re-export, different object!

# ============================================================
# tests/test_profile.py - Tests (CORRECT)
# ============================================================
from fastapi.testclient import TestClient
from app.main import app
from app.deps import get_db, get_current_user  # SAME import path as main.py

class FakeUser:
    name = "Test User"

class FakeDB:
    def get_user_by_token(self, token):
        return FakeUser()
    def close(self):
        pass

def override_get_db():
    """Override that yields a fake database."""
    db = FakeDB()
    try:
        yield db
    finally:
        db.close()

def override_get_current_user():
    """Alternatively, override the higher-level dependency."""
    return FakeUser()

def test_profile_override_db():
    """Override just the DB dependency."""
    # Verify the function reference is correct
    print(f"get_db id: {id(get_db)}")
    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    response = client.get("/profile")
    assert response.status_code == 200
    assert response.json() == {"name": "Test User"}
    # IMPORTANT: clean up overrides after test
    app.dependency_overrides.clear()

def test_profile_override_user():
    """Override the user dependency directly (simpler)."""
    app.dependency_overrides[get_current_user] = override_get_current_user
    client = TestClient(app)
    response = client.get("/profile")
    assert response.status_code == 200
    assert response.json() == {"name": "Test User"}
    app.dependency_overrides.clear()

# ============================================================
# DEBUGGING TIP: Verify function identity
# ============================================================
def debug_overrides():
    """Check if your override key matches the actual dependency."""
    from app.deps import get_db as deps_get_db
    # Compare function objects
    for route in app.routes:
        if hasattr(route, "dependant"):
            for dep in route.dependant.dependencies:
                print(f"Route dependency: {dep.call} (id={id(dep.call)})")
                print(f"Override key:     {deps_get_db} (id={id(deps_get_db)})")
                print(f"Match: {dep.call is deps_get_db}")
```

**Common pitfalls:**
1. **Import path mismatch** -- the #1 cause. Always import from the same module.
2. **Generator vs return** -- if the real dep uses `yield`, the override should too.
3. **Missing cleanup** -- always call `app.dependency_overrides.clear()` after tests.
4. **Nested deps** -- sometimes it is simpler to override the top-level dependency rather than a deeply nested one.''',
    ),
    (
        "thinking/debugging",
        r'''My FastAPI middleware is not executing in the order I expect. I have logging middleware and auth middleware, but auth runs before logging, so failed auth attempts are not logged. Here is my setup:

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware

app = FastAPI()

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        print(f"LOG: {request.method} {request.url}")
        response = await call_next(request)
        print(f"LOG: Response {response.status_code}")
        return response

class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        token = request.headers.get("Authorization")
        if not token:
            return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
        response = await call_next(request)
        return response

app.add_middleware(AuthMiddleware)
app.add_middleware(LoggingMiddleware)

# Auth failures are not being logged!''',
        r'''<think>
The issue is about middleware ordering in FastAPI/Starlette. This is a common source of confusion.

In Starlette (which FastAPI is built on), middleware is added in a stack-like fashion. The LAST middleware added with `add_middleware()` is the OUTERMOST middleware -- meaning it executes FIRST on the way in and LAST on the way out.

So with:
```
app.add_middleware(AuthMiddleware)    # added first -> inner
app.add_middleware(LoggingMiddleware) # added second -> outer
```

The execution order is:
1. LoggingMiddleware (request) -- logs the request
2. AuthMiddleware (request) -- checks auth
3. Route handler (if auth passes)
4. AuthMiddleware (response)
5. LoggingMiddleware (response) -- logs the response

Wait, that means logging IS the outer middleware and SHOULD execute before auth. So logging should capture auth failures...

Unless the issue is that BaseHTTPMiddleware has a known bug with response streaming. When AuthMiddleware returns a JSONResponse directly (without calling call_next), the LoggingMiddleware's `call_next` might not properly capture the status code.

Actually, let me reconsider. The order as written should work correctly for logging. The LoggingMiddleware wraps AuthMiddleware. So when auth fails and returns 401, the LoggingMiddleware should still see the response.

But wait -- there is a known issue with BaseHTTPMiddleware: when the inner middleware returns a response WITHOUT calling call_next, the outer middleware's call_next might hang or not return properly in some versions of Starlette.

Actually, I think the real issue might be simpler: the user might have the order backwards in their head. Let me re-read...

"app.add_middleware(AuthMiddleware)" first, then "app.add_middleware(LoggingMiddleware)" second. The last added is outermost. So LoggingMiddleware IS outer. It should work.

Unless... the user is running an older version where the behavior is different. Or the issue is that `await call_next(request)` in LoggingMiddleware blocks when AuthMiddleware returns early.

Let me provide a comprehensive answer covering the ordering rules and the BaseHTTPMiddleware pitfalls.
</think>

FastAPI/Starlette middleware ordering is counterintuitive: the **last** middleware added with `add_middleware()` is the **outermost** (executes first). But there is also a known issue with `BaseHTTPMiddleware` and early returns.

```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp, Receive, Scope, Send
import time

app = FastAPI()

# ============================================================
# UNDERSTANDING THE ORDER
# ============================================================
# add_middleware works like a STACK (LIFO):
#   app.add_middleware(A)  -> inner
#   app.add_middleware(B)  -> outer
# Request flow:  B -> A -> route handler
# Response flow: route handler -> A -> B

# So in your code:
#   app.add_middleware(AuthMiddleware)    # inner (2nd to execute)
#   app.add_middleware(LoggingMiddleware) # outer (1st to execute)
# This order IS correct for logging auth failures.

# ============================================================
# THE REAL BUG: BaseHTTPMiddleware + early return
# ============================================================
# BaseHTTPMiddleware has known issues:
# 1. It wraps the response body in a background thread
# 2. When inner middleware returns without calling call_next,
#    the outer middleware may not see the correct response
# 3. It can cause memory leaks with streaming responses

# ============================================================
# FIX: Use pure ASGI middleware instead of BaseHTTPMiddleware
# ============================================================

class LoggingMiddlewareASGI:
    """Pure ASGI middleware -- no BaseHTTPMiddleware issues."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.time()
        path = scope.get("path", "unknown")
        method = scope.get("method", "unknown")

        status_code = None

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        print(f"LOG: {method} {path}")
        await self.app(scope, receive, send_wrapper)
        duration = time.time() - start_time
        print(f"LOG: {method} {path} -> {status_code} ({duration:.3f}s)")


class AuthMiddlewareASGI:
    """Pure ASGI auth middleware."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        auth = headers.get(b"authorization", None)

        if not auth:
            response = JSONResponse(
                status_code=401,
                content={"detail": "Not authenticated"},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


# Add in correct order: last added = outermost = executes first
app.add_middleware(AuthMiddlewareASGI)    # inner
app.add_middleware(LoggingMiddlewareASGI) # outer -- logs everything

@app.get("/profile")
async def profile():
    return {"name": "Alice"}

# Now the flow for an unauthenticated request:
# 1. LoggingMiddlewareASGI logs "GET /profile"
# 2. AuthMiddlewareASGI checks token, returns 401
# 3. LoggingMiddlewareASGI logs "GET /profile -> 401"
# Auth failures are now properly logged!
```

**Key lessons:**
- Middleware order is LIFO: last added executes first on the request path.
- Avoid `BaseHTTPMiddleware` for production -- use pure ASGI middleware.
- Pure ASGI middleware correctly handles early returns and streaming.
- Always test middleware ordering with a failing request to verify the flow.''',
    ),
    (
        "thinking/debugging",
        r'''My FastAPI background task is silently swallowing exceptions and I cannot see what is going wrong. Here is my code:

from fastapi import FastAPI, BackgroundTasks
import httpx

app = FastAPI()

async def send_notification(email: str, message: str):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.notifications.example.com/send",
            json={"email": email, "message": message},
        )
        response.raise_for_status()  # This might throw but I never see the error

@app.post("/orders")
async def create_order(background_tasks: BackgroundTasks):
    # ... create order logic ...
    background_tasks.add_task(send_notification, "user@example.com", "Order created!")
    return {"status": "Order created"}

# The endpoint returns 200 but the notification email never arrives.
# No error in logs. How do I debug this?''',
        r'''<think>
Background tasks in FastAPI run after the response is sent. If they raise exceptions, those exceptions are caught by Starlette's background task runner and logged to stderr, but they do not affect the HTTP response. If logging is not configured properly, the errors appear to vanish.

The fixes are:
1. Wrap background tasks in try/except with proper logging
2. Use a proper task queue (Celery, etc.) for important tasks
3. Configure Starlette's error handling

Let me provide a comprehensive solution.
</think>

FastAPI background tasks run **after the response is sent** to the client. Exceptions in background tasks are caught by Starlette and logged to stderr, but if your logging is not configured, they appear to vanish silently.

```python
from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.responses import JSONResponse
import httpx
import logging
import traceback
import asyncio
from functools import wraps

# ============================================================
# STEP 1: Configure logging properly
# ============================================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("background_tasks")

app = FastAPI()

# ============================================================
# STEP 2: Wrap background tasks with error handling
# ============================================================

def safe_background_task(func):
    """Decorator that catches and logs background task exceptions."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        try:
            if asyncio.iscoroutinefunction(func):
                return await func(*args, **kwargs)
            else:
                return func(*args, **kwargs)
        except Exception as e:
            logger.error(
                "Background task %s failed: %s\n%s",
                func.__name__,
                str(e),
                traceback.format_exc(),
            )
            # Optionally: send to error tracking (Sentry, etc.)
            # sentry_sdk.capture_exception(e)
            # Optionally: store failure for retry
            # await store_failed_task(func.__name__, args, kwargs, str(e))
    return wrapper


@safe_background_task
async def send_notification(email: str, message: str):
    """Send notification with proper error handling."""
    logger.info("Sending notification to %s", email)
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            "https://api.notifications.example.com/send",
            json={"email": email, "message": message},
        )
        response.raise_for_status()
    logger.info("Notification sent successfully to %s", email)


@app.post("/orders")
async def create_order(background_tasks: BackgroundTasks):
    # ... create order logic ...
    background_tasks.add_task(
        send_notification, "user@example.com", "Order created!"
    )
    return {"status": "Order created"}


# ============================================================
# STEP 3: For critical tasks, use a retry mechanism
# ============================================================

async def send_notification_with_retry(
    email: str, message: str, max_retries: int = 3
):
    """Send notification with exponential backoff retry."""
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    "https://api.notifications.example.com/send",
                    json={"email": email, "message": message},
                )
                response.raise_for_status()
                logger.info("Notification sent to %s on attempt %d", email, attempt + 1)
                return
        except (httpx.HTTPError, httpx.TimeoutException) as e:
            wait = 2 ** attempt  # 1s, 2s, 4s
            logger.warning(
                "Attempt %d/%d failed for %s: %s. Retrying in %ds",
                attempt + 1, max_retries, email, str(e), wait,
            )
            if attempt < max_retries - 1:
                await asyncio.sleep(wait)
            else:
                logger.error(
                    "All %d attempts failed for %s: %s",
                    max_retries, email, str(e),
                )
                raise


# ============================================================
# STEP 4: For truly important tasks, do not use BackgroundTasks
# ============================================================
# BackgroundTasks are fire-and-forget. For critical operations:
# - Use Celery, Dramatiq, or ARQ for reliable task queues
# - Use a database-backed job table with a worker process
# - At minimum, log failures and have alerting on error rates
```

**Why background task errors vanish:**
1. Starlette catches exceptions and writes to `sys.stderr`, not to your logger
2. If stderr is not captured (e.g., in production with only file logging), errors are lost
3. The HTTP response is already sent, so the client never knows the task failed

**Rule of thumb:** If a task failure should be noticed by anyone, do not rely on `BackgroundTasks` alone. Add explicit error handling, logging, and consider a proper task queue.''',
    ),
    (
        "thinking/debugging",
        r'''I'm using FastAPI streaming responses but the client receives the entire response at once instead of streaming chunks. Here is my code:

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio

app = FastAPI()

async def generate_data():
    for i in range(10):
        yield f"data: chunk {i}\n\n"
        await asyncio.sleep(1)

@app.get("/stream")
async def stream_data():
    return StreamingResponse(generate_data(), media_type="text/event-stream")

# Client receives all 10 chunks at once after 10 seconds
# instead of receiving one chunk per second''',
        r'''<think>
The code itself looks correct for server-sent events streaming. The issue is likely caused by:

1. A reverse proxy (nginx, etc.) buffering the response
2. GZip middleware in FastAPI compressing the response (which requires buffering)
3. The client not handling streaming properly
4. Missing headers that tell proxies not to buffer

Let me cover all these cases.
</think>

The FastAPI code is correct, but streaming is often broken by **buffering at other layers**. Here are all the common causes and fixes:

```python
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from starlette.middleware.gzip import GZipMiddleware
import asyncio

app = FastAPI()

# ============================================================
# CAUSE 1: GZip middleware buffers the entire response
# ============================================================
# If you have this, it KILLS streaming:
# app.add_middleware(GZipMiddleware)  # REMOVE THIS for SSE endpoints

# FIX: Conditionally apply GZip, excluding SSE endpoints
# (or just do not use GZipMiddleware with streaming)


# ============================================================
# CAUSE 2: Missing headers for proxy pass-through
# ============================================================
async def generate_data():
    for i in range(10):
        yield f"data: chunk {i}\n\n"
        await asyncio.sleep(1)

@app.get("/stream")
async def stream_data():
    return StreamingResponse(
        generate_data(),
        media_type="text/event-stream",
        headers={
            # Tell proxies not to buffer this response
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",  # nginx-specific
            "Connection": "keep-alive",
            # Prevent content-encoding that requires buffering
            "Content-Encoding": "identity",
        },
    )


# ============================================================
# CAUSE 3: Nginx buffering (most common in production)
# ============================================================
# Add to your nginx config for the streaming location:
#
# location /stream {
#     proxy_pass http://backend;
#     proxy_buffering off;        # Disable response buffering
#     proxy_cache off;            # Disable caching
#     proxy_set_header Connection '';
#     proxy_http_version 1.1;
#     chunked_transfer_encoding off;
#
#     # For SSE specifically:
#     proxy_set_header Cache-Control 'no-cache';
#     proxy_read_timeout 86400;   # Long timeout for SSE
# }


# ============================================================
# CAUSE 4: Python WSGI server buffering (use ASGI server)
# ============================================================
# Streaming only works with ASGI servers like:
#   uvicorn app:app --host 0.0.0.0 --port 8000
# NOT with WSGI servers like gunicorn (without uvicorn workers)
# For gunicorn, use:
#   gunicorn app:app -k uvicorn.workers.UvicornWorker


# ============================================================
# CAUSE 5: Client-side fetch() not reading stream properly
# ============================================================
# JavaScript client must use ReadableStream, not await response.json()
CLIENT_JS = """
// WRONG: waits for entire response
// const data = await fetch('/stream').then(r => r.text());

// CORRECT: read stream incrementally
const response = await fetch('/stream');
const reader = response.body.getReader();
const decoder = new TextDecoder();

while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    const chunk = decoder.decode(value, { stream: true });
    console.log('Received chunk:', chunk);
}

// EVEN BETTER: Use EventSource for SSE
const eventSource = new EventSource('/stream');
eventSource.onmessage = function(event) {
    console.log('Received:', event.data);
};
eventSource.onerror = function(event) {
    console.error('SSE error:', event);
    eventSource.close();
};
"""


# ============================================================
# DEBUGGING: Add flush markers to verify server-side streaming
# ============================================================
async def generate_debug():
    """Generator with timestamps to verify streaming works."""
    import time
    for i in range(10):
        timestamp = time.time()
        yield f"data: chunk {i} at {timestamp:.3f}\n\n"
        await asyncio.sleep(1)
    yield "data: [DONE]\n\n"

@app.get("/stream-debug")
async def stream_debug():
    return StreamingResponse(
        generate_debug(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )

# Test with curl to eliminate client-side issues:
# curl -N http://localhost:8000/stream-debug
# The -N flag disables curl's output buffering
# You should see chunks appear one per second
```

**Debugging checklist:**
1. Test with `curl -N` first to rule out client issues
2. Check for GZipMiddleware or any response-modifying middleware
3. Check reverse proxy config (nginx, Cloudflare, AWS ALB)
4. Verify you are running an ASGI server (uvicorn, hypercorn)
5. Check that no CDN or WAF is buffering the response''',
    ),
    (
        "thinking/debugging",
        r'''My FastAPI application's lifespan context manager is not cleaning up resources properly on shutdown. Database connections are leaking. Here is my code:

from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncpg

db_pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool
    db_pool = await asyncpg.create_pool("postgresql://localhost/mydb")
    print("DB pool created")
    yield
    await db_pool.close()
    print("DB pool closed")

app = FastAPI(lifespan=lifespan)

@app.get("/data")
async def get_data():
    async with db_pool.acquire() as conn:
        return await conn.fetch("SELECT * FROM items")

# When I stop the server with Ctrl+C, "DB pool closed" never prints
# and connections remain open in PostgreSQL.''',
        r'''<think>
The issue is that when the server receives SIGINT (Ctrl+C), the shutdown sequence might not complete the lifespan cleanup properly. This can happen because:

1. The asyncio event loop gets cancelled before the lifespan generator can resume after yield
2. The global variable pattern is fragile
3. The pool.close() might hang if connections are still in use
4. Exception handling around the yield is missing

Let me provide a robust solution.
</think>

The lifespan cleanup fails because `Ctrl+C` sends SIGINT which can interrupt the event loop before the code after `yield` executes. Additionally, `pool.close()` can hang if connections are still acquired. Here is the fix:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
import asyncpg
import asyncio
import signal
import logging

logger = logging.getLogger(__name__)

# ============================================================
# FIX 1: Use app.state instead of global variables
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan with robust cleanup."""
    pool = None
    try:
        # STARTUP
        pool = await asyncpg.create_pool(
            "postgresql://localhost/mydb",
            min_size=2,
            max_size=10,
            # Set timeouts to prevent cleanup hangs
            command_timeout=30,
            # Connection will be terminated if idle too long
            max_inactive_connection_lifetime=300,
        )
        # Store on app.state, NOT as a global variable
        app.state.db_pool = pool
        logger.info("DB pool created with %d connections", pool.get_size())

        yield

    except Exception as e:
        logger.error("Lifespan error: %s", e)
        raise
    finally:
        # SHUTDOWN - this block runs even if yield is interrupted
        logger.info("Shutting down: closing DB pool...")
        if pool is not None:
            try:
                # Terminate all connections with a timeout
                # pool.close() waits for connections to be released
                # pool.terminate() forcefully closes all connections
                await asyncio.wait_for(pool.close(), timeout=5.0)
                logger.info("DB pool closed gracefully")
            except asyncio.TimeoutError:
                logger.warning("Pool close timed out, terminating forcefully")
                pool.terminate()
            except Exception as e:
                logger.error("Error closing pool: %s", e)
                pool.terminate()


app = FastAPI(lifespan=lifespan)


@app.get("/data")
async def get_data(request: Request):
    """Use request.app.state to access the pool."""
    pool = request.app.state.db_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT * FROM items")
        return [dict(row) for row in rows]


# ============================================================
# FIX 2: Handle signals properly in the entrypoint
# ============================================================

def main():
    """Run with proper signal handling."""
    import uvicorn

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        # Graceful shutdown timeout (seconds)
        timeout_graceful_shutdown=10,
    )
    server = uvicorn.Server(config)

    # uvicorn handles SIGINT/SIGTERM, but you can add extra handling:
    original_handler = signal.getsignal(signal.SIGINT)

    def signal_handler(signum, frame):
        logger.info("Received signal %d, initiating graceful shutdown", signum)
        # Let uvicorn handle it
        if original_handler and callable(original_handler):
            original_handler(signum, frame)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    server.run()


# ============================================================
# FIX 3: Middleware to track active connections (debugging)
# ============================================================

from starlette.types import ASGIApp, Receive, Scope, Send

class ConnectionTracker:
    """Track active request count to debug shutdown issues."""

    def __init__(self, app: ASGIApp):
        self.app = app
        self.active_requests = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            self.active_requests += 1
            logger.debug("Active requests: %d", self.active_requests)
            try:
                await self.app(scope, receive, send)
            finally:
                self.active_requests -= 1
                logger.debug("Active requests: %d", self.active_requests)
        else:
            await self.app(scope, receive, send)

app.add_middleware(ConnectionTracker)

if __name__ == "__main__":
    main()
```

**Key fixes:**
1. **Use `try/finally`** around `yield` in lifespan -- the `finally` block runs even when the server is interrupted.
2. **Use `asyncio.wait_for` with timeout** on `pool.close()` -- prevents hangs if connections are still acquired.
3. **Fall back to `pool.terminate()`** if graceful close times out.
4. **Use `app.state`** instead of globals -- avoids import ordering issues and makes testing easier.
5. **Set `timeout_graceful_shutdown`** in uvicorn to ensure the server waits for in-flight requests before running lifespan cleanup.''',
    ),
]
