"""Async/concurrency training pairs: async web application patterns."""

pairs = [
    {
        "instruction": r'''How do I implement WebSocket handling in FastAPI with proper connection management, broadcasting, and error handling?''',
        "output": r'''<think>
WebSocket handling in FastAPI requires managing connection lifecycle, handling disconnections gracefully, and often broadcasting to multiple clients. The key challenges:

1. Connection management -- tracking active connections, cleaning up on disconnect
2. Broadcasting -- sending messages to all connected clients efficiently
3. Error handling -- clients can disconnect at any time, need to handle ConnectionClosed
4. Authentication -- WebSocket connections need auth too, but it works differently from HTTP

FastAPI provides a WebSocket class that wraps Starlette's WebSocket. The accept/receive/send lifecycle is async. I should show a connection manager pattern that handles multiple rooms/channels.

One tricky part: when you broadcast to N clients and one has disconnected, you need to catch the error for that client without killing the broadcast to others. You cannot just use gather with return_exceptions because you also want to remove the dead connection.
</think>

```python
import asyncio
import json
import logging
from typing import Any, Optional
from datetime import datetime
from dataclasses import dataclass, field
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)
app = FastAPI()

# ============================================================
# Connection manager
# ============================================================

@dataclass
class ConnectedClient:
    websocket: WebSocket
    client_id: str
    rooms: set[str] = field(default_factory=set)
    connected_at: datetime = field(default_factory=datetime.utcnow)

class ConnectionManager:
    """Manages WebSocket connections with room support."""

    def __init__(self):
        self._clients: dict[str, ConnectedClient] = {}
        self._rooms: dict[str, set[str]] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self, websocket: WebSocket, client_id: str
    ) -> ConnectedClient:
        await websocket.accept()
        async with self._lock:
            client = ConnectedClient(
                websocket=websocket, client_id=client_id
            )
            self._clients[client_id] = client
        logger.info("Client %s connected", client_id)
        return client

    async def disconnect(self, client_id: str):
        async with self._lock:
            client = self._clients.pop(client_id, None)
            if client:
                for room in client.rooms:
                    self._rooms.get(room, set()).discard(client_id)
        logger.info("Client %s disconnected", client_id)

    async def join_room(self, client_id: str, room: str):
        async with self._lock:
            if room not in self._rooms:
                self._rooms[room] = set()
            self._rooms[room].add(client_id)
            if client_id in self._clients:
                self._clients[client_id].rooms.add(room)

    async def leave_room(self, client_id: str, room: str):
        async with self._lock:
            self._rooms.get(room, set()).discard(client_id)
            if client_id in self._clients:
                self._clients[client_id].rooms.discard(room)

    async def send_to_client(
        self, client_id: str, message: dict
    ) -> bool:
        client = self._clients.get(client_id)
        if not client:
            return False
        try:
            await client.websocket.send_json(message)
            return True
        except Exception:
            await self.disconnect(client_id)
            return False

    async def broadcast_to_room(
        self, room: str, message: dict, exclude: Optional[str] = None
    ):
        """Send message to all clients in a room."""
        client_ids = list(self._rooms.get(room, set()))
        dead_clients = []

        for cid in client_ids:
            if cid == exclude:
                continue
            success = await self.send_to_client(cid, message)
            if not success:
                dead_clients.append(cid)

        # Clean up dead connections
        for cid in dead_clients:
            await self.disconnect(cid)

    async def broadcast_all(self, message: dict):
        """Send message to all connected clients."""
        client_ids = list(self._clients.keys())
        for cid in client_ids:
            await self.send_to_client(cid, message)

    @property
    def client_count(self) -> int:
        return len(self._clients)

manager = ConnectionManager()

# ============================================================
# WebSocket endpoint
# ============================================================

@app.websocket("/ws/{client_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    client_id: str,
    room: str = Query(default="general"),
):
    client = await manager.connect(websocket, client_id)
    await manager.join_room(client_id, room)

    # Notify room
    await manager.broadcast_to_room(room, {
        "type": "user_joined",
        "client_id": client_id,
        "timestamp": datetime.utcnow().isoformat(),
    }, exclude=client_id)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "message")

            if msg_type == "message":
                await manager.broadcast_to_room(room, {
                    "type": "message",
                    "client_id": client_id,
                    "content": data.get("content", ""),
                    "timestamp": datetime.utcnow().isoformat(),
                })
            elif msg_type == "join_room":
                new_room = data.get("room")
                if new_room:
                    await manager.join_room(client_id, new_room)
            elif msg_type == "ping":
                await manager.send_to_client(client_id, {
                    "type": "pong",
                })

    except WebSocketDisconnect:
        await manager.disconnect(client_id)
        await manager.broadcast_to_room(room, {
            "type": "user_left",
            "client_id": client_id,
        })
    except Exception as e:
        logger.error("WebSocket error for %s: %s", client_id, e)
        await manager.disconnect(client_id)

# ============================================================
# REST endpoint to broadcast from server
# ============================================================

@app.post("/broadcast/{room}")
async def broadcast(room: str, message: dict):
    await manager.broadcast_to_room(room, {
        "type": "server_message",
        **message,
    })
    return {"status": "sent", "clients": manager.client_count}
```

Key patterns:
- Use a `ConnectionManager` to track active connections and rooms
- Always handle `WebSocketDisconnect` to clean up
- Catch send errors per-client during broadcast to avoid killing the loop
- Use `asyncio.Lock` for thread-safe connection tracking
- Send structured JSON messages with a `type` field for routing'''
    },
    {
        "instruction": r'''How do I implement Server-Sent Events (SSE) in FastAPI for real-time streaming to clients?''',
        "output": r'''<think>
SSE (Server-Sent Events) is simpler than WebSockets -- it is one-way (server to client), uses regular HTTP, and automatically reconnects. In FastAPI, you implement it with StreamingResponse and async generators.

The key things to cover:
1. Basic SSE format (data: ...\n\n)
2. Event types and IDs for client-side handling
3. Heartbeat to keep connection alive
4. Clean shutdown when client disconnects
5. Integration with an event bus for real updates

The SSE protocol is simple: each event is text with "data:", "event:", "id:", and "retry:" fields, separated by double newlines. The client uses EventSource API in JavaScript.

One tricky part: detecting client disconnection. In FastAPI/Starlette, when the client disconnects, the generator should stop. You can detect this by checking if the request is disconnected, or by catching the GeneratorExit exception.
</think>

```python
import asyncio
import json
import logging
from datetime import datetime
from typing import AsyncIterator, Any, Optional
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)
app = FastAPI()

# ============================================================
# SSE message formatter
# ============================================================

def format_sse(
    data: str,
    event: Optional[str] = None,
    event_id: Optional[str] = None,
    retry: Optional[int] = None,
) -> str:
    """Format a Server-Sent Event message."""
    lines = []
    if event_id is not None:
        lines.append(f"id: {event_id}")
    if event is not None:
        lines.append(f"event: {event}")
    if retry is not None:
        lines.append(f"retry: {retry}")
    for line in data.split("\n"):
        lines.append(f"data: {line}")
    lines.append("")  # empty line terminates the event
    lines.append("")
    return "\n".join(lines)

# ============================================================
# Event bus for publishing/subscribing
# ============================================================

class EventBus:
    """Simple pub/sub for SSE events."""

    def __init__(self):
        self._subscribers: dict[str, list[asyncio.Queue]] = {}

    def subscribe(self, channel: str) -> asyncio.Queue:
        if channel not in self._subscribers:
            self._subscribers[channel] = []
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers[channel].append(queue)
        return queue

    def unsubscribe(self, channel: str, queue: asyncio.Queue):
        if channel in self._subscribers:
            self._subscribers[channel] = [
                q for q in self._subscribers[channel] if q is not queue
            ]

    async def publish(self, channel: str, event: dict):
        for queue in self._subscribers.get(channel, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("SSE queue full, dropping event")

event_bus = EventBus()

# ============================================================
# SSE endpoint with event bus
# ============================================================

async def event_stream(
    request: Request,
    channel: str,
    heartbeat_interval: float = 15.0,
) -> AsyncIterator[str]:
    """Generate SSE events from the event bus."""
    queue = event_bus.subscribe(channel)
    event_id = 0

    try:
        # Send initial connection event
        yield format_sse(
            json.dumps({"status": "connected", "channel": channel}),
            event="connected",
            retry=3000,
        )

        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            try:
                # Wait for events with timeout (for heartbeat)
                event = await asyncio.wait_for(
                    queue.get(), timeout=heartbeat_interval
                )
                event_id += 1
                yield format_sse(
                    json.dumps(event),
                    event=event.get("type", "message"),
                    event_id=str(event_id),
                )
            except asyncio.TimeoutError:
                # Send heartbeat comment to keep connection alive
                yield ": heartbeat\n\n"

    finally:
        event_bus.unsubscribe(channel, queue)
        logger.info("SSE client disconnected from %s", channel)

@app.get("/events/{channel}")
async def sse_endpoint(request: Request, channel: str):
    return StreamingResponse(
        event_stream(request, channel),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # disable nginx buffering
        },
    )

# ============================================================
# Publishing events (from other endpoints or background tasks)
# ============================================================

@app.post("/notify/{channel}")
async def publish_event(channel: str, payload: dict):
    await event_bus.publish(channel, {
        "type": "notification",
        "payload": payload,
        "timestamp": datetime.utcnow().isoformat(),
    })
    return {"status": "published"}

# ============================================================
# Simple SSE: streaming data processing progress
# ============================================================

@app.get("/process/{task_id}")
async def stream_progress(request: Request, task_id: str):
    async def progress_stream():
        for step in range(1, 11):
            if await request.is_disconnected():
                break
            await asyncio.sleep(1)  # simulate work
            yield format_sse(
                json.dumps({
                    "task_id": task_id,
                    "step": step,
                    "total": 10,
                    "progress": step * 10,
                }),
                event="progress",
            )
        yield format_sse(
            json.dumps({"task_id": task_id, "status": "complete"}),
            event="complete",
        )

    return StreamingResponse(
        progress_stream(),
        media_type="text/event-stream",
    )
```

JavaScript client usage:
```
const source = new EventSource("/events/updates");
source.addEventListener("message", (e) => console.log(JSON.parse(e.data)));
source.addEventListener("connected", (e) => console.log("Connected:", e.data));
source.onerror = (e) => console.error("SSE error:", e);
```

Key patterns:
- Send heartbeat comments (`: heartbeat`) to prevent proxy timeouts
- Use `request.is_disconnected()` to detect client disconnect
- Set `retry:` field to control client reconnection delay
- Disable response buffering with `X-Accel-Buffering: no` for nginx'''
    },
    {
        "instruction": r'''How do I run background tasks in FastAPI without blocking request handling?''',
        "output": r'''<think>
FastAPI has several approaches for background tasks:

1. BackgroundTasks (built-in) -- runs after the response is sent, but still on the event loop. Good for quick tasks like sending emails.

2. asyncio.create_task() -- fire-and-forget coroutines. Runs on the event loop. Good for lightweight async work.

3. Process/thread pool -- for CPU-bound or blocking work. Uses run_in_executor or to_thread.

4. External task queue (Celery, Dramatiq, Arq) -- for heavy, reliable, distributed tasks.

The built-in BackgroundTasks is the simplest but has limitations:
- Runs on the same event loop, so CPU-bound work blocks other requests
- Not persistent -- if the server crashes, the task is lost
- Not distributed -- only runs on the server that received the request

I should show the progression from simple to production-grade approaches.
</think>

```python
import asyncio
import time
import logging
from typing import Any
from datetime import datetime
from fastapi import FastAPI, BackgroundTasks, Request
from concurrent.futures import ProcessPoolExecutor

logger = logging.getLogger(__name__)
app = FastAPI()

# ============================================================
# Method 1: FastAPI BackgroundTasks (simplest)
# ============================================================

async def send_email_async(to: str, subject: str, body: str):
    """Async background task -- does not block event loop."""
    await asyncio.sleep(2)  # simulate sending email
    logger.info("Email sent to %s: %s", to, subject)

def write_audit_log(event: str, data: dict):
    """Sync background task -- runs in thread pool."""
    time.sleep(0.5)  # simulate file/DB write
    logger.info("Audit: %s %s", event, data)

@app.post("/users/")
async def create_user(
    name: str,
    email: str,
    background_tasks: BackgroundTasks,
):
    # Create user (fast)
    user = {"id": 1, "name": name, "email": email}

    # Schedule background work -- runs AFTER response is sent
    background_tasks.add_task(
        send_email_async, email, "Welcome!", f"Hello {name}"
    )
    background_tasks.add_task(
        write_audit_log, "user_created", {"user_id": 1}
    )

    # Response returns immediately
    return user

# ============================================================
# Method 2: Long-running background tasks with tracking
# ============================================================

class TaskManager:
    """Manage long-running background tasks."""

    def __init__(self):
        self._tasks: dict[str, asyncio.Task] = {}
        self._results: dict[str, dict[str, Any]] = {}

    def submit(self, task_id: str, coro) -> str:
        task = asyncio.create_task(coro)
        self._tasks[task_id] = task
        self._results[task_id] = {
            "status": "running",
            "started_at": datetime.utcnow().isoformat(),
        }
        task.add_done_callback(
            lambda t: self._on_complete(task_id, t)
        )
        return task_id

    def _on_complete(self, task_id: str, task: asyncio.Task):
        self._tasks.pop(task_id, None)
        if task.cancelled():
            self._results[task_id]["status"] = "cancelled"
        elif task.exception():
            self._results[task_id]["status"] = "failed"
            self._results[task_id]["error"] = str(task.exception())
        else:
            self._results[task_id]["status"] = "completed"
            self._results[task_id]["result"] = task.result()
        self._results[task_id]["finished_at"] = (
            datetime.utcnow().isoformat()
        )

    def get_status(self, task_id: str) -> dict:
        return self._results.get(task_id, {"status": "not_found"})

    async def cancel(self, task_id: str) -> bool:
        task = self._tasks.get(task_id)
        if task:
            task.cancel()
            return True
        return False

task_manager = TaskManager()

async def process_large_dataset(dataset_id: str) -> dict:
    """Simulate long-running data processing."""
    total_steps = 10
    for step in range(1, total_steps + 1):
        await asyncio.sleep(2)  # simulate work
        logger.info(
            "Dataset %s: step %d/%d", dataset_id, step, total_steps
        )
    return {"dataset_id": dataset_id, "rows_processed": 50000}

@app.post("/process/{dataset_id}")
async def start_processing(dataset_id: str):
    task_id = f"process-{dataset_id}"
    task_manager.submit(task_id, process_large_dataset(dataset_id))
    return {"task_id": task_id, "status": "started"}

@app.get("/tasks/{task_id}")
async def get_task_status(task_id: str):
    return task_manager.get_status(task_id)

@app.delete("/tasks/{task_id}")
async def cancel_task(task_id: str):
    cancelled = await task_manager.cancel(task_id)
    return {"cancelled": cancelled}

# ============================================================
# Method 3: CPU-bound work in process pool
# ============================================================

process_pool = ProcessPoolExecutor(max_workers=4)

def cpu_heavy_work(data: list[int]) -> dict:
    """CPU-bound function -- runs in separate process."""
    total = sum(x * x for x in data)
    return {"sum_of_squares": total, "count": len(data)}

@app.post("/compute/")
async def compute_endpoint(numbers: list[int]):
    loop = asyncio.get_running_loop()
    result = await loop.run_in_executor(
        process_pool, cpu_heavy_work, numbers
    )
    return result

# ============================================================
# App lifecycle: startup and shutdown
# ============================================================

@app.on_event("startup")
async def startup():
    logger.info("Application started")

@app.on_event("shutdown")
async def shutdown():
    # Cancel all running background tasks
    for task_id in list(task_manager._tasks.keys()):
        await task_manager.cancel(task_id)
    process_pool.shutdown(wait=False)
    logger.info("Application shutdown complete")
```

When to use each approach:
- `BackgroundTasks` -- quick fire-and-forget (emails, logs, cache invalidation)
- `TaskManager` with `create_task` -- medium tasks you need to track/cancel
- `ProcessPoolExecutor` -- CPU-bound work (image processing, ML inference)
- External queue (Celery/Arq) -- long tasks, retries, persistence, distribution'''
    },
    {
        "instruction": r'''How do I implement async middleware in FastAPI/Starlette for request logging, timing, and rate limiting?''',
        "output": r'''```python
import asyncio
import time
import logging
import uuid
from typing import Callable
from collections import defaultdict
from datetime import datetime

from fastapi import FastAPI, Request, Response, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)
app = FastAPI()

# ============================================================
# Middleware 1: Request ID and timing
# ============================================================

class RequestContextMiddleware(BaseHTTPMiddleware):
    """Add request ID, timing, and structured logging."""

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        request_id = request.headers.get(
            "X-Request-ID", str(uuid.uuid4())[:8]
        )
        start = time.monotonic()

        # Store request ID for use in handlers
        request.state.request_id = request_id

        try:
            response = await call_next(request)
            elapsed = time.monotonic() - start

            response.headers["X-Request-ID"] = request_id
            response.headers["X-Response-Time"] = f"{elapsed:.3f}s"

            logger.info(
                "method=%s path=%s status=%d duration=%.3fs request_id=%s",
                request.method,
                request.url.path,
                response.status_code,
                elapsed,
                request_id,
            )
            return response

        except Exception as e:
            elapsed = time.monotonic() - start
            logger.error(
                "method=%s path=%s error=%s duration=%.3fs request_id=%s",
                request.method,
                request.url.path,
                str(e),
                elapsed,
                request_id,
            )
            raise

# ============================================================
# Middleware 2: Rate limiter (token bucket)
# ============================================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting using token bucket algorithm."""

    def __init__(
        self,
        app: ASGIApp,
        max_requests: int = 60,
        window_seconds: float = 60.0,
    ):
        super().__init__(app)
        self.max_requests = max_requests
        self.window = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)
        self._lock = asyncio.Lock()

    def _get_client_ip(self, request: Request) -> str:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return request.client.host if request.client else "unknown"

    async def _check_rate(self, client_ip: str) -> tuple[bool, int]:
        """Returns (allowed, remaining_requests)."""
        async with self._lock:
            now = time.monotonic()
            bucket = self._buckets[client_ip]

            # Remove expired timestamps
            cutoff = now - self.window
            self._buckets[client_ip] = [
                t for t in bucket if t > cutoff
            ]
            bucket = self._buckets[client_ip]

            if len(bucket) >= self.max_requests:
                return False, 0

            bucket.append(now)
            remaining = self.max_requests - len(bucket)
            return True, remaining

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        client_ip = self._get_client_ip(request)
        allowed, remaining = await self._check_rate(client_ip)

        if not allowed:
            return Response(
                content='{"error": "Rate limit exceeded"}',
                status_code=429,
                media_type="application/json",
                headers={
                    "Retry-After": str(int(self.window)),
                    "X-RateLimit-Limit": str(self.max_requests),
                    "X-RateLimit-Remaining": "0",
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.max_requests)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

# ============================================================
# Middleware 3: CORS and security headers
# ============================================================

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        return response

# ============================================================
# Register middleware (order matters: last added = first executed)
# ============================================================

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    RateLimitMiddleware, max_requests=100, window_seconds=60.0
)
app.add_middleware(RequestContextMiddleware)

# ============================================================
# Example endpoints
# ============================================================

@app.get("/")
async def root(request: Request):
    return {
        "message": "Hello",
        "request_id": request.state.request_id,
    }

@app.get("/items/{item_id}")
async def get_item(item_id: int, request: Request):
    await asyncio.sleep(0.1)  # simulate DB lookup
    return {"item_id": item_id}
```

Middleware execution order (with the registration above):
1. `RequestContextMiddleware` -- adds request ID, starts timer
2. `RateLimitMiddleware` -- checks rate limit, may return 429
3. `SecurityHeadersMiddleware` -- adds security headers
4. Route handler -- processes the request

Key patterns:
- Use `BaseHTTPMiddleware` for simple request/response modification
- Use `request.state` to pass data from middleware to handlers
- Rate limiting needs async lock for thread safety
- Always add timing and request ID for production observability'''
    },
    {
        "instruction": r'''How do I implement streaming responses in FastAPI for large file downloads, AI model output, or CSV exports?''',
        "output": r'''```python
import asyncio
import csv
import io
import os
from typing import AsyncIterator
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, Response

app = FastAPI()

# ============================================================
# Pattern 1: Stream a large file without loading into memory
# ============================================================

@app.get("/download/{filename}")
async def download_file(filename: str):
    file_path = Path(f"/data/exports/{filename}")
    if not file_path.exists():
        return Response(status_code=404)

    async def file_stream():
        async with asyncio.to_thread(open, file_path, "rb") as f:
            pass
        # Use sync file I/O in chunks via to_thread
        with open(file_path, "rb") as f:
            while chunk := f.read(8192):
                yield chunk

    file_size = os.path.getsize(file_path)
    return StreamingResponse(
        file_stream(),
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(file_size),
        },
    )

# ============================================================
# Pattern 2: Stream CSV export from database
# ============================================================

async def fetch_records_chunked(
    query: str, chunk_size: int = 1000
) -> AsyncIterator[list[dict]]:
    """Simulate chunked database reads."""
    for offset in range(0, 10000, chunk_size):
        await asyncio.sleep(0.1)  # simulate DB query
        yield [
            {"id": i, "name": f"Record {i}", "value": i * 1.5}
            for i in range(offset, min(offset + chunk_size, 10000))
        ]

@app.get("/export/csv")
async def export_csv():
    async def csv_stream():
        # Write CSV header
        output = io.StringIO()
        writer = csv.DictWriter(
            output, fieldnames=["id", "name", "value"]
        )
        writer.writeheader()
        yield output.getvalue()
        output.seek(0)
        output.truncate(0)

        # Stream data rows
        async for chunk in fetch_records_chunked(
            "SELECT * FROM records", chunk_size=500
        ):
            for record in chunk:
                writer.writerow(record)
            yield output.getvalue()
            output.seek(0)
            output.truncate(0)

    return StreamingResponse(
        csv_stream(),
        media_type="text/csv",
        headers={
            "Content-Disposition": (
                'attachment; filename="export.csv"'
            ),
        },
    )

# ============================================================
# Pattern 3: Stream AI/LLM output (OpenAI-style SSE)
# ============================================================

async def generate_ai_response(prompt: str) -> AsyncIterator[str]:
    """Simulate streaming AI model output."""
    words = f"Here is a response to: {prompt}. ".split()
    words.extend(
        "The answer involves careful consideration of "
        "multiple factors including performance, reliability, "
        "and maintainability.".split()
    )
    for word in words:
        await asyncio.sleep(0.05)  # simulate token generation
        yield word + " "

@app.post("/chat/stream")
async def chat_stream(request: Request):
    body = await request.json()
    prompt = body.get("prompt", "")

    async def sse_stream():
        async for token in generate_ai_response(prompt):
            # OpenAI-compatible SSE format
            chunk = {
                "choices": [{
                    "delta": {"content": token},
                    "index": 0,
                }]
            }
            yield f"data: {__import__('json').dumps(chunk)}\n\n"

        yield "data: [DONE]\n\n"

    return StreamingResponse(
        sse_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )

# ============================================================
# Pattern 4: Stream JSON array (NDJSON)
# ============================================================

@app.get("/stream/records")
async def stream_ndjson():
    """Stream records as newline-delimited JSON."""
    import json

    async def ndjson_stream():
        async for chunk in fetch_records_chunked(
            "SELECT * FROM records"
        ):
            for record in chunk:
                yield json.dumps(record) + "\n"

    return StreamingResponse(
        ndjson_stream(),
        media_type="application/x-ndjson",
    )

# ============================================================
# Pattern 5: Proxy/forward a stream from upstream
# ============================================================

@app.get("/proxy/{path:path}")
async def proxy_stream(path: str):
    import httpx

    async def forward_stream():
        async with httpx.AsyncClient() as client:
            async with client.stream(
                "GET", f"https://upstream.example.com/{path}"
            ) as resp:
                async for chunk in resp.aiter_bytes(8192):
                    yield chunk

    return StreamingResponse(
        forward_stream(),
        media_type="application/octet-stream",
    )
```

Key patterns:
- Yield small chunks (4-8KB) to keep memory usage constant
- Use async generators for database-backed streams
- For CSV, use `io.StringIO` as buffer and flush after each chunk
- For AI output, use SSE format (`text/event-stream`) with `data:` prefix
- For large JSON, use NDJSON (one JSON object per line) instead of a giant array'''
    },
]
