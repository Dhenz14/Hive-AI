"""FastAPI advanced — middleware, dependencies, background tasks, WebSockets, and production patterns."""

PAIRS = [
    (
        "python/fastapi-middleware",
        "Show FastAPI middleware patterns: request/response logging, CORS, rate limiting, request ID propagation, and error handling middleware.",
        '''FastAPI middleware and cross-cutting concerns:

```python
import time
import uuid
import logging
from contextvars import ContextVar
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from typing import Callable

app = FastAPI()

# --- Context variable for request ID ---
request_id_ctx: ContextVar[str] = ContextVar("request_id", default="")

# --- Request ID middleware ---
@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request_id_ctx.set(request_id)
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response

# --- Timing middleware ---
@app.middleware("http")
async def timing_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    response.headers["X-Process-Time"] = f"{duration:.4f}"

    # Log slow requests
    if duration > 1.0:
        logging.warning(
            "Slow request",
            extra={
                "path": request.url.path,
                "method": request.method,
                "duration": duration,
                "request_id": getattr(request.state, "request_id", ""),
            },
        )
    return response

# --- Structured logging middleware ---
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    logger = logging.getLogger("api")

    logger.info(
        "Request started",
        extra={
            "method": request.method,
            "path": request.url.path,
            "client_ip": request.client.host,
            "request_id": getattr(request.state, "request_id", ""),
        },
    )

    response = await call_next(request)

    logger.info(
        "Request completed",
        extra={
            "method": request.method,
            "path": request.url.path,
            "status": response.status_code,
            "request_id": getattr(request.state, "request_id", ""),
        },
    )
    return response

# --- CORS ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://app.example.com"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "X-Process-Time"],
)

# --- Global exception handler ---
from fastapi.responses import JSONResponse

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", "unknown")
    logging.exception(
        "Unhandled error",
        extra={"request_id": request_id, "path": request.url.path},
    )
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "request_id": request_id,
        },
    )

class AppError(Exception):
    def __init__(self, message: str, status_code: int = 400,
                 error_code: str = "BAD_REQUEST"):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "request_id": getattr(request.state, "request_id", ""),
        },
    )
```

Middleware order (outermost first):
1. **Request ID** — assign/propagate trace ID
2. **Timing** — measure request duration
3. **Logging** — structured access logs
4. **CORS** — handle preflight and headers
5. **Auth** — verify tokens (usually as dependency instead)
6. **Error handler** — catch unhandled exceptions'''
    ),
    (
        "python/fastapi-dependencies",
        "Show FastAPI dependency injection: database sessions, service layer, caching, pagination, and reusable dependencies.",
        '''FastAPI dependency injection for clean architecture:

```python
from fastapi import FastAPI, Depends, Query, Request
from typing import Annotated, AsyncGenerator, Optional
from contextlib import asynccontextmanager
from dataclasses import dataclass

app = FastAPI()

# --- Database session dependency ---

async def get_db() -> AsyncGenerator:
    """Yield a database session, auto-close on completion."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

DB = Annotated[AsyncSession, Depends(get_db)]

# --- Service layer dependencies ---

class UserRepository:
    def __init__(self, db: DB):
        self.db = db

    async def get_by_id(self, user_id: str):
        return await self.db.get(User, user_id)

    async def create(self, **kwargs):
        user = User(**kwargs)
        self.db.add(user)
        await self.db.flush()
        return user

class UserService:
    def __init__(self, repo: Annotated[UserRepository, Depends()],
                 cache: Annotated["CacheService", Depends()]):
        self.repo = repo
        self.cache = cache

    async def get_user(self, user_id: str):
        cached = await self.cache.get(f"user:{user_id}")
        if cached:
            return cached
        user = await self.repo.get_by_id(user_id)
        if user:
            await self.cache.set(f"user:{user_id}", user, ttl=300)
        return user

# FastAPI auto-resolves the dependency chain:
# Route -> UserService -> UserRepository -> get_db()
#                      -> CacheService

@app.get("/users/{user_id}")
async def get_user(user_id: str,
                   service: Annotated[UserService, Depends()]):
    user = await service.get_user(user_id)
    if not user:
        raise HTTPException(404)
    return user


# --- Pagination dependency ---

@dataclass
class Pagination:
    page: int
    size: int
    offset: int

def get_pagination(
    page: int = Query(1, ge=1, le=1000),
    size: int = Query(20, ge=1, le=100),
) -> Pagination:
    return Pagination(page=page, size=size, offset=(page - 1) * size)

PageParams = Annotated[Pagination, Depends(get_pagination)]

@app.get("/items")
async def list_items(pagination: PageParams, db: DB):
    query = select(Item).offset(pagination.offset).limit(pagination.size)
    items = (await db.execute(query)).scalars().all()
    total = (await db.execute(select(func.count(Item.id)))).scalar()
    return {
        "items": items,
        "page": pagination.page,
        "size": pagination.size,
        "total": total,
        "pages": -(-total // pagination.size),
    }


# --- Current user dependency ---

async def get_current_user(
    request: Request,
    db: DB,
) -> User:
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(401, "Not authenticated")
    payload = verify_jwt(token)
    user = await db.get(User, payload["sub"])
    if not user:
        raise HTTPException(401, "User not found")
    return user

CurrentUser = Annotated[User, Depends(get_current_user)]

async def require_admin(user: CurrentUser) -> User:
    if "admin" not in user.roles:
        raise HTTPException(403, "Admin required")
    return user

AdminUser = Annotated[User, Depends(require_admin)]

@app.delete("/admin/users/{user_id}")
async def delete_user(user_id: str, admin: AdminUser,
                      service: Annotated[UserService, Depends()]):
    await service.delete_user(user_id)
    return {"deleted": True}


# --- Lifespan for startup/shutdown ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.db_pool = await create_pool()
    app.state.redis = await create_redis()
    yield
    # Shutdown
    await app.state.db_pool.close()
    await app.state.redis.close()

app = FastAPI(lifespan=lifespan)
```

Patterns:
1. **Annotated types** — `Annotated[Type, Depends()]` for clean signatures
2. **Auto-resolution** — FastAPI builds dependency graph automatically
3. **Session management** — yield-based deps with auto commit/rollback
4. **Layered deps** — route → service → repository → database
5. **Lifespan** — manage connection pools and resources'''
    ),
    (
        "python/fastapi-websockets",
        "Show FastAPI WebSocket patterns: connection management, rooms, broadcasting, and authentication.",
        '''FastAPI WebSocket patterns for real-time features:

```python
import asyncio
import json
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends
from typing import Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone

app = FastAPI()

# --- Connection Manager ---

class ConnectionManager:
    def __init__(self):
        # room_id -> set of websockets
        self.rooms: dict[str, set[WebSocket]] = {}
        # websocket -> user info
        self.connections: dict[WebSocket, dict] = {}

    async def connect(self, websocket: WebSocket, user: dict,
                      room: str = "general"):
        await websocket.accept()
        self.connections[websocket] = {**user, "room": room}
        self.rooms.setdefault(room, set()).add(websocket)

        # Notify room
        await self.broadcast(room, {
            "type": "user.joined",
            "user": user["name"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }, exclude=websocket)

    async def disconnect(self, websocket: WebSocket):
        info = self.connections.pop(websocket, None)
        if info:
            room = info["room"]
            self.rooms.get(room, set()).discard(websocket)
            if not self.rooms.get(room):
                self.rooms.pop(room, None)

            await self.broadcast(room, {
                "type": "user.left",
                "user": info["name"],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })

    async def broadcast(self, room: str, message: dict,
                        exclude: Optional[WebSocket] = None):
        """Send message to all connections in a room."""
        dead = []
        for ws in self.rooms.get(room, set()):
            if ws == exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                dead.append(ws)

        # Clean up dead connections
        for ws in dead:
            await self.disconnect(ws)

    async def send_to_user(self, user_id: str, message: dict):
        """Send message to a specific user (all their connections)."""
        for ws, info in self.connections.items():
            if info.get("user_id") == user_id:
                try:
                    await ws.send_json(message)
                except Exception:
                    pass

    def get_room_users(self, room: str) -> list[str]:
        return [
            self.connections[ws]["name"]
            for ws in self.rooms.get(room, set())
            if ws in self.connections
        ]

manager = ConnectionManager()


# --- WebSocket authentication ---

async def ws_authenticate(websocket: WebSocket) -> Optional[dict]:
    """Authenticate WebSocket via query param or first message."""
    # Option 1: Token in query params
    token = websocket.query_params.get("token")
    if token:
        try:
            return verify_jwt(token)
        except Exception:
            await websocket.close(code=4001, reason="Invalid token")
            return None

    # Option 2: Token in first message after connect
    await websocket.accept()
    try:
        data = await asyncio.wait_for(
            websocket.receive_json(), timeout=10.0
        )
        if data.get("type") != "auth":
            await websocket.close(code=4001, reason="Auth required")
            return None
        return verify_jwt(data["token"])
    except (asyncio.TimeoutError, Exception):
        await websocket.close(code=4001, reason="Auth timeout")
        return None


# --- Chat WebSocket endpoint ---

@app.websocket("/ws/chat/{room}")
async def chat_websocket(websocket: WebSocket, room: str):
    # Authenticate
    user = await ws_authenticate(websocket)
    if not user:
        return

    await manager.connect(websocket, user, room)

    # Send room state
    await websocket.send_json({
        "type": "room.state",
        "users": manager.get_room_users(room),
        "room": room,
    })

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "message":
                await manager.broadcast(room, {
                    "type": "message",
                    "user": user["name"],
                    "content": data["content"],
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

            elif msg_type == "typing":
                await manager.broadcast(room, {
                    "type": "typing",
                    "user": user["name"],
                }, exclude=websocket)

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        await manager.disconnect(websocket)


# --- Server-Sent Events alternative (simpler one-way) ---

from fastapi.responses import StreamingResponse

@app.get("/events/{user_id}")
async def event_stream(user_id: str):
    async def generate():
        queue = asyncio.Queue()
        event_subscribers[user_id] = queue
        try:
            while True:
                event = await queue.get()
                yield f"event: {event['type']}\\ndata: {json.dumps(event)}\\n\\n"
        finally:
            event_subscribers.pop(user_id, None)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
```

Patterns:
1. **Room-based broadcasting** — group connections by channel/room
2. **WS authentication** — token via query param or first message
3. **Dead connection cleanup** — remove on send failure
4. **Heartbeat** — ping/pong to detect stale connections
5. **SSE fallback** — simpler option for server-to-client only streaming'''
    ),
]
"""
