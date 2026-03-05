"""WebSocket patterns — real-time communication, rooms, scaling."""

PAIRS = [
    (
        "backend/websocket-server",
        "Show WebSocket server patterns: connection management, rooms/channels, heartbeat, and message broadcasting.",
        '''WebSocket server with rooms:

```python
import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect


@dataclass
class Client:
    ws: WebSocket
    client_id: str
    rooms: set[str] = field(default_factory=set)
    connected_at: float = field(default_factory=time.time)
    last_pong: float = field(default_factory=time.time)


class WebSocketManager:
    """Manage WebSocket connections with room support."""

    def __init__(self):
        self.clients: dict[str, Client] = {}
        self.rooms: dict[str, set[str]] = {}  # room_name -> client_ids

    async def connect(self, ws: WebSocket, client_id: str) -> Client:
        await ws.accept()
        client = Client(ws=ws, client_id=client_id)
        self.clients[client_id] = client
        return client

    async def disconnect(self, client_id: str):
        client = self.clients.pop(client_id, None)
        if client:
            for room in list(client.rooms):
                self.leave_room(client_id, room)

    def join_room(self, client_id: str, room: str):
        self.rooms.setdefault(room, set()).add(client_id)
        if client_id in self.clients:
            self.clients[client_id].rooms.add(room)

    def leave_room(self, client_id: str, room: str):
        if room in self.rooms:
            self.rooms[room].discard(client_id)
            if not self.rooms[room]:
                del self.rooms[room]
        if client_id in self.clients:
            self.clients[client_id].rooms.discard(room)

    async def send_to_client(self, client_id: str, message: dict):
        client = self.clients.get(client_id)
        if client:
            try:
                await client.ws.send_json(message)
            except Exception:
                await self.disconnect(client_id)

    async def broadcast_to_room(self, room: str, message: dict,
                                 exclude: str = None):
        client_ids = self.rooms.get(room, set()).copy()
        tasks = []
        for cid in client_ids:
            if cid != exclude:
                tasks.append(self.send_to_client(cid, message))
        await asyncio.gather(*tasks, return_exceptions=True)

    async def broadcast_all(self, message: dict):
        tasks = [self.send_to_client(cid, message) for cid in self.clients]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def heartbeat_loop(self, interval: float = 30):
        """Detect dead connections via ping/pong."""
        while True:
            await asyncio.sleep(interval)
            now = time.time()
            dead = [cid for cid, c in self.clients.items()
                    if now - c.last_pong > interval * 2]
            for cid in dead:
                await self.disconnect(cid)


# FastAPI integration
app = FastAPI()
manager = WebSocketManager()


@app.websocket("/ws/{client_id}")
async def websocket_endpoint(ws: WebSocket, client_id: str):
    client = await manager.connect(ws, client_id)
    try:
        while True:
            data = await ws.receive_json()
            action = data.get("action")

            if action == "join":
                manager.join_room(client_id, data["room"])
                await manager.broadcast_to_room(
                    data["room"],
                    {"type": "user_joined", "user": client_id},
                    exclude=client_id,
                )
            elif action == "leave":
                manager.leave_room(client_id, data["room"])
            elif action == "message":
                await manager.broadcast_to_room(
                    data["room"],
                    {"type": "message", "from": client_id,
                     "content": data["content"]},
                )
            elif action == "pong":
                client.last_pong = time.time()
    except WebSocketDisconnect:
        await manager.disconnect(client_id)
```

Key patterns:
1. **Room abstraction** — group clients into rooms; broadcast within room scope
2. **Connection lifecycle** — connect → join rooms → exchange messages → disconnect cleanup
3. **Heartbeat/pong** — detect dead connections; clean up stale clients
4. **Concurrent broadcast** — asyncio.gather sends to all clients in parallel
5. **Graceful disconnect** — leave all rooms, remove from client registry on disconnect'''
    ),
    (
        "backend/websocket-scaling",
        "Show WebSocket scaling: Redis pub/sub for multi-server broadcast, sticky sessions, and connection migration.",
        '''Scaling WebSockets across servers:

```python
import asyncio
import json
from typing import Callable


class RedisWebSocketBridge:
    """Scale WebSockets across servers using Redis pub/sub.

    Each server subscribes to Redis channels.
    Broadcasting goes through Redis, reaching all servers.
    """

    def __init__(self, redis_client, local_manager):
        self.redis = redis_client
        self.local = local_manager
        self._subscriptions: dict[str, asyncio.Task] = {}

    async def subscribe_room(self, room: str):
        """Subscribe to Redis channel for a room."""
        if room in self._subscriptions:
            return

        pubsub = self.redis.pubsub()
        await pubsub.subscribe(f"ws:room:{room}")

        async def listener():
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    # Broadcast to local clients only
                    origin = data.pop("_origin_server", None)
                    if origin != self.server_id:
                        await self.local.broadcast_to_room(room, data)

        self._subscriptions[room] = asyncio.create_task(listener())

    async def publish_to_room(self, room: str, message: dict):
        """Publish message to all servers via Redis."""
        message["_origin_server"] = self.server_id
        await self.redis.publish(
            f"ws:room:{room}",
            json.dumps(message),
        )

    async def get_room_count(self, room: str) -> int:
        """Get total clients in room across all servers."""
        counts = await self.redis.hgetall(f"ws:room_counts:{room}")
        return sum(int(v) for v in counts.values())

    async def update_presence(self, room: str, count: int):
        """Update this server's client count for a room."""
        await self.redis.hset(
            f"ws:room_counts:{room}",
            self.server_id,
            count,
        )
        await self.redis.expire(f"ws:room_counts:{room}", 60)
```

Key patterns:
1. **Redis pub/sub** — each server subscribes; messages fan out to all server instances
2. **Origin tracking** — skip re-broadcasting messages from own server; prevent loops
3. **Distributed presence** — Redis hash tracks per-server counts; aggregate for room total
4. **Sticky sessions** — load balancer routes same client to same server; avoids reconnects
5. **Channel per room** — subscribe/unsubscribe as rooms are created/emptied'''
    ),
]
