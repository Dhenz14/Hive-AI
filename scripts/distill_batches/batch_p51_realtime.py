"""Real-time systems — Server-Sent Events, WebSocket patterns, and live updates."""

PAIRS = [
    (
        "python/server-sent-events",
        "Show Server-Sent Events (SSE) patterns: streaming responses, event types, reconnection, and FastAPI integration.",
        '''Server-Sent Events patterns:

```python
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
import asyncio
import json
import time

app = FastAPI()


# --- SSE message format ---

def sse_message(data: dict, event: str = None, id: str = None,
                retry: int = None) -> str:
    """Format SSE message."""
    lines = []
    if id:
        lines.append(f"id: {id}")
    if event:
        lines.append(f"event: {event}")
    if retry:
        lines.append(f"retry: {retry}")
    lines.append(f"data: {json.dumps(data)}")
    return "\n".join(lines) + "\n\n"


# --- Basic SSE endpoint ---

@app.get("/events/stream")
async def event_stream(request: Request):
    async def generate() -> AsyncGenerator[str, None]:
        # Set retry interval for client reconnection
        yield sse_message({"status": "connected"}, event="connected", retry=5000)

        counter = 0
        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            counter += 1
            yield sse_message(
                {"count": counter, "timestamp": time.time()},
                event="heartbeat",
                id=str(counter),
            )
            await asyncio.sleep(1)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        },
    )


# --- Multi-channel SSE with PubSub ---

class SSEManager:
    """Manage SSE connections and broadcast events."""

    def __init__(self):
        self._channels: dict[str, list[asyncio.Queue]] = {}

    async def subscribe(self, channel: str) -> AsyncGenerator[str, None]:
        queue = asyncio.Queue(maxsize=100)
        self._channels.setdefault(channel, []).append(queue)
        try:
            yield sse_message({"channel": channel}, event="subscribed")
            while True:
                data = await queue.get()
                yield sse_message(data["payload"], event=data.get("event"))
        finally:
            self._channels[channel].remove(queue)
            if not self._channels[channel]:
                del self._channels[channel]

    async def publish(self, channel: str, event: str, payload: dict):
        for queue in self._channels.get(channel, []):
            try:
                queue.put_nowait({"event": event, "payload": payload})
            except asyncio.QueueFull:
                pass  # Drop message if client is slow

    @property
    def connection_count(self) -> dict[str, int]:
        return {ch: len(subs) for ch, subs in self._channels.items()}


sse = SSEManager()


@app.get("/events/{channel}")
async def channel_stream(channel: str, request: Request):
    async def generate():
        async for message in sse.subscribe(channel):
            if await request.is_disconnected():
                break
            yield message

    return StreamingResponse(generate(), media_type="text/event-stream")


@app.post("/events/{channel}/publish")
async def publish_event(channel: str, event: str, payload: dict):
    await sse.publish(channel, event, payload)
    return {"published": True, "subscribers": len(sse._channels.get(channel, []))}


# --- Client-side JavaScript ---
# const source = new EventSource('/events/orders');
#
# source.addEventListener('order_update', (e) => {
#     const data = JSON.parse(e.data);
#     updateOrderUI(data);
# });
#
# source.addEventListener('connected', (e) => {
#     console.log('Connected to SSE');
# });
#
# source.onerror = (e) => {
#     // Browser auto-reconnects with retry interval
#     console.log('SSE error, reconnecting...');
# };


# --- SSE for long-running task progress ---

@app.post("/tasks/process")
async def start_processing(request: Request):
    task_id = str(time.time())

    async def generate():
        yield sse_message({"task_id": task_id, "status": "started"}, event="start")

        for i in range(100):
            if await request.is_disconnected():
                break
            await asyncio.sleep(0.1)  # Simulate work
            yield sse_message(
                {"progress": i + 1, "total": 100},
                event="progress",
            )

        yield sse_message(
            {"task_id": task_id, "status": "completed", "result_url": f"/results/{task_id}"},
            event="complete",
        )

    return StreamingResponse(generate(), media_type="text/event-stream")
```

SSE patterns:
1. **Unidirectional** — server to client only (simpler than WebSockets)
2. **Auto-reconnect** — browser automatically reconnects with `retry:` interval
3. **Event types** — `event:` field for client-side routing
4. **`id:` field** — enables resume from `Last-Event-ID` header on reconnect
5. **Use cases** — notifications, progress bars, live feeds, dashboard updates'''
    ),
    (
        "python/websocket-advanced",
        "Show advanced WebSocket patterns: room management, authentication, heartbeat, and scaling with Redis.",
        '''Advanced WebSocket patterns:

```python
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from typing import Optional
import asyncio
import json
import time
import redis.asyncio as aioredis

app = FastAPI()


# --- Connection manager with rooms ---

class ConnectionManager:
    def __init__(self):
        self.rooms: dict[str, dict[str, WebSocket]] = {}
        self.user_rooms: dict[str, set[str]] = {}

    async def connect(self, ws: WebSocket, room_id: str, user_id: str):
        await ws.accept()
        self.rooms.setdefault(room_id, {})[user_id] = ws
        self.user_rooms.setdefault(user_id, set()).add(room_id)

        # Notify room
        await self.broadcast(room_id, {
            "type": "user_joined",
            "user_id": user_id,
            "online_count": len(self.rooms[room_id]),
        }, exclude=user_id)

    def disconnect(self, room_id: str, user_id: str):
        if room_id in self.rooms:
            self.rooms[room_id].pop(user_id, None)
            if not self.rooms[room_id]:
                del self.rooms[room_id]
        if user_id in self.user_rooms:
            self.user_rooms[user_id].discard(room_id)

    async def send_to_user(self, user_id: str, message: dict):
        """Send to specific user across all their rooms."""
        for room_id in self.user_rooms.get(user_id, []):
            ws = self.rooms.get(room_id, {}).get(user_id)
            if ws:
                try:
                    await ws.send_json(message)
                except Exception:
                    self.disconnect(room_id, user_id)

    async def broadcast(self, room_id: str, message: dict,
                       exclude: str = None):
        """Broadcast to all users in a room."""
        if room_id not in self.rooms:
            return
        disconnected = []
        for user_id, ws in self.rooms[room_id].items():
            if user_id == exclude:
                continue
            try:
                await ws.send_json(message)
            except Exception:
                disconnected.append(user_id)
        for uid in disconnected:
            self.disconnect(room_id, uid)

    def get_online_users(self, room_id: str) -> list[str]:
        return list(self.rooms.get(room_id, {}).keys())


manager = ConnectionManager()


# --- WebSocket endpoint with auth and heartbeat ---

@app.websocket("/ws/{room_id}")
async def websocket_endpoint(ws: WebSocket, room_id: str):
    # Authenticate
    token = ws.query_params.get("token")
    user = await authenticate_token(token)
    if not user:
        await ws.close(code=4001, reason="Unauthorized")
        return

    await manager.connect(ws, room_id, user.id)

    # Send initial state
    await ws.send_json({
        "type": "room_state",
        "online_users": manager.get_online_users(room_id),
    })

    # Heartbeat task
    async def heartbeat():
        while True:
            try:
                await asyncio.sleep(30)
                await ws.send_json({"type": "ping", "ts": time.time()})
            except Exception:
                break

    heartbeat_task = asyncio.create_task(heartbeat())

    try:
        while True:
            data = await ws.receive_json()
            msg_type = data.get("type")

            if msg_type == "pong":
                continue  # Client heartbeat response

            elif msg_type == "message":
                await manager.broadcast(room_id, {
                    "type": "message",
                    "user_id": user.id,
                    "user_name": user.name,
                    "content": data["content"],
                    "timestamp": time.time(),
                })

            elif msg_type == "typing":
                await manager.broadcast(room_id, {
                    "type": "typing",
                    "user_id": user.id,
                    "user_name": user.name,
                }, exclude=user.id)

    except WebSocketDisconnect:
        pass
    finally:
        heartbeat_task.cancel()
        manager.disconnect(room_id, user.id)
        await manager.broadcast(room_id, {
            "type": "user_left",
            "user_id": user.id,
            "online_count": len(manager.rooms.get(room_id, {})),
        })


# --- Scaling with Redis PubSub ---

class RedisWebSocketBridge:
    """Bridge WebSocket rooms across multiple server instances."""

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self.redis = aioredis.from_url(redis_url)
        self.local_manager = ConnectionManager()

    async def start_listener(self):
        """Listen for messages from other instances."""
        pubsub = self.redis.pubsub()
        await pubsub.psubscribe("ws:room:*")

        async for message in pubsub.listen():
            if message["type"] == "pmessage":
                room_id = message["channel"].decode().split(":")[-1]
                data = json.loads(message["data"])
                # Broadcast to local connections only
                await self.local_manager.broadcast(
                    room_id, data,
                    exclude=data.get("_sender_id"),
                )

    async def publish(self, room_id: str, message: dict, sender_id: str):
        """Publish to Redis (reaches all server instances)."""
        message["_sender_id"] = sender_id
        await self.redis.publish(
            f"ws:room:{room_id}",
            json.dumps(message),
        )
        # Also broadcast locally
        await self.local_manager.broadcast(
            room_id, message, exclude=sender_id
        )
```

WebSocket patterns:
1. **Room-based** — organize connections by room/channel for targeted broadcasts
2. **Heartbeat** — detect dead connections with ping/pong
3. **Auth on connect** — validate token before accepting connection
4. **Redis bridge** — scale WebSockets across multiple server instances
5. **Graceful disconnect** — clean up rooms and notify peers on disconnect'''
    ),
]
