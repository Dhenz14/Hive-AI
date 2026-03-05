"""Chat and messaging system design — real-time messaging, delivery guarantees, storage strategies, and push notifications."""

PAIRS = [
    (
        "system-design/realtime-messaging",
        "Design a real-time messaging architecture using WebSockets with presence tracking, typing indicators, and connection management.",
        '''Real-time messaging architecture with WebSocket management and presence:

```python
# --- ws_manager.py --- WebSocket connection management ---

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any
from enum import Enum

import redis.asyncio as redis
from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class PresenceStatus(Enum):
    ONLINE = "online"
    AWAY = "away"
    DND = "do_not_disturb"
    OFFLINE = "offline"


@dataclass
class Connection:
    """Represents a single WebSocket connection."""
    user_id: str
    device_id: str
    websocket: WebSocket
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_heartbeat: datetime = field(default_factory=datetime.utcnow)


class ConnectionManager:
    """Manage WebSocket connections for a single server instance.

    For multi-server deployment, combine with Redis pub/sub for
    cross-server message routing.
    """

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        # Local connections on this server instance
        self._connections: dict[str, list[Connection]] = {}  # user_id -> [connections]
        self._heartbeat_interval = 30  # seconds
        self._heartbeat_timeout = 90   # consider dead after this

    async def connect(
        self, websocket: WebSocket, user_id: str, device_id: str
    ) -> Connection:
        """Register a new WebSocket connection."""
        await websocket.accept()

        conn = Connection(
            user_id=user_id,
            device_id=device_id,
            websocket=websocket,
        )

        if user_id not in self._connections:
            self._connections[user_id] = []
        self._connections[user_id].append(conn)

        # Update presence in Redis (shared across servers)
        await self._set_presence(user_id, PresenceStatus.ONLINE)

        # Notify user's contacts
        await self._broadcast_presence(user_id, PresenceStatus.ONLINE)

        logger.info(f"Connected: {user_id} ({device_id})")
        return conn

    async def disconnect(self, user_id: str, device_id: str) -> None:
        """Remove a WebSocket connection."""
        connections = self._connections.get(user_id, [])
        self._connections[user_id] = [
            c for c in connections if c.device_id != device_id
        ]

        # Only set offline if no remaining connections for this user
        if not self._connections[user_id]:
            del self._connections[user_id]
            await self._set_presence(user_id, PresenceStatus.OFFLINE)
            await self._broadcast_presence(user_id, PresenceStatus.OFFLINE)

        logger.info(f"Disconnected: {user_id} ({device_id})")

    async def send_to_user(self, user_id: str, message: dict) -> int:
        """Send a message to all of a user's connected devices.

        Returns the number of devices that received the message.
        """
        connections = self._connections.get(user_id, [])
        sent_count = 0

        for conn in connections:
            try:
                await conn.websocket.send_json(message)
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to send to {user_id}/{conn.device_id}: {e}")
                await self.disconnect(user_id, conn.device_id)

        # If user not on this server, publish to Redis for other servers
        if sent_count == 0:
            await self.redis.publish(
                f"user:{user_id}:messages",
                json.dumps(message),
            )

        return sent_count

    async def send_to_room(self, room_id: str, message: dict, exclude_user: str = "") -> None:
        """Send a message to all members of a chat room."""
        member_ids = await self.redis.smembers(f"room:{room_id}:members")

        tasks = []
        for member_id in member_ids:
            member_id_str = member_id if isinstance(member_id, str) else member_id.decode()
            if member_id_str != exclude_user:
                tasks.append(self.send_to_user(member_id_str, message))

        await asyncio.gather(*tasks, return_exceptions=True)

    async def handle_heartbeat(self, user_id: str, device_id: str) -> None:
        """Process heartbeat from client."""
        connections = self._connections.get(user_id, [])
        for conn in connections:
            if conn.device_id == device_id:
                conn.last_heartbeat = datetime.utcnow()
                break

        # Refresh presence TTL in Redis
        await self.redis.expire(f"presence:{user_id}", self._heartbeat_timeout)

    async def _set_presence(self, user_id: str, status: PresenceStatus) -> None:
        """Update user presence in Redis."""
        key = f"presence:{user_id}"
        data = {
            "status": status.value,
            "last_seen": datetime.utcnow().isoformat(),
            "server_id": self._get_server_id(),
        }
        await self.redis.hset(key, mapping=data)
        if status != PresenceStatus.OFFLINE:
            await self.redis.expire(key, self._heartbeat_timeout)
        else:
            await self.redis.expire(key, 86400)  # keep for 24h

    async def _broadcast_presence(self, user_id: str, status: PresenceStatus) -> None:
        """Notify user's contacts about presence change."""
        contact_ids = await self.redis.smembers(f"user:{user_id}:contacts")
        event = {
            "type": "presence",
            "user_id": user_id,
            "status": status.value,
            "timestamp": datetime.utcnow().isoformat(),
        }
        for contact_id in contact_ids:
            cid = contact_id if isinstance(contact_id, str) else contact_id.decode()
            await self.send_to_user(cid, event)

    def _get_server_id(self) -> str:
        import socket
        return socket.gethostname()
```

```python
# --- chat_handler.py --- WebSocket message handler ---

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Query
from ws_manager import ConnectionManager, PresenceStatus

app = FastAPI()


@app.websocket("/ws/chat")
async def websocket_chat(
    websocket: WebSocket,
    token: str = Query(...),
):
    """WebSocket endpoint for real-time chat."""
    # Authenticate token
    user = await authenticate_ws_token(token)
    if not user:
        await websocket.close(code=4001, reason="Unauthorized")
        return

    user_id = user["id"]
    device_id = websocket.headers.get("X-Device-ID", "web")
    manager = get_connection_manager()

    conn = await manager.connect(websocket, user_id, device_id)

    try:
        while True:
            data = await websocket.receive_json()
            await handle_message(manager, user_id, data)

    except WebSocketDisconnect:
        await manager.disconnect(user_id, device_id)
    except Exception as e:
        logger.error(f"WebSocket error for {user_id}: {e}")
        await manager.disconnect(user_id, device_id)


async def handle_message(
    manager: ConnectionManager, sender_id: str, data: dict
) -> None:
    """Route incoming WebSocket messages by type."""
    msg_type = data.get("type")

    handlers = {
        "chat.message": handle_chat_message,
        "chat.typing": handle_typing_indicator,
        "chat.read": handle_read_receipt,
        "presence.update": handle_presence_update,
        "heartbeat": handle_heartbeat,
    }

    handler = handlers.get(msg_type)
    if handler:
        await handler(manager, sender_id, data)
    else:
        await manager.send_to_user(sender_id, {
            "type": "error",
            "message": f"Unknown message type: {msg_type}",
        })


async def handle_chat_message(
    manager: ConnectionManager, sender_id: str, data: dict
) -> None:
    """Process and deliver a chat message."""
    room_id = data["room_id"]
    content = data["content"]
    client_msg_id = data.get("client_id", str(uuid.uuid4()))

    # Persist message
    message = {
        "id": f"msg_{uuid.uuid4().hex[:12]}",
        "room_id": room_id,
        "sender_id": sender_id,
        "content": content,
        "client_id": client_msg_id,
        "timestamp": datetime.utcnow().isoformat(),
        "status": "sent",
    }

    await save_message(message)

    # Send acknowledgment to sender
    await manager.send_to_user(sender_id, {
        "type": "chat.ack",
        "client_id": client_msg_id,
        "message_id": message["id"],
        "timestamp": message["timestamp"],
    })

    # Deliver to room members
    delivery_event = {
        "type": "chat.message",
        **message,
    }
    await manager.send_to_room(room_id, delivery_event, exclude_user=sender_id)


async def handle_typing_indicator(
    manager: ConnectionManager, sender_id: str, data: dict
) -> None:
    """Broadcast typing indicator to room members."""
    room_id = data["room_id"]
    is_typing = data.get("is_typing", True)

    await manager.send_to_room(
        room_id,
        {
            "type": "chat.typing",
            "room_id": room_id,
            "user_id": sender_id,
            "is_typing": is_typing,
            "timestamp": datetime.utcnow().isoformat(),
        },
        exclude_user=sender_id,
    )


async def handle_read_receipt(
    manager: ConnectionManager, sender_id: str, data: dict
) -> None:
    """Mark messages as read and notify sender."""
    room_id = data["room_id"]
    last_read_id = data["last_read_message_id"]

    # Update read cursor in database
    await update_read_cursor(sender_id, room_id, last_read_id)

    # Notify message senders that their messages were read
    await manager.send_to_room(
        room_id,
        {
            "type": "chat.read",
            "room_id": room_id,
            "user_id": sender_id,
            "last_read_message_id": last_read_id,
            "timestamp": datetime.utcnow().isoformat(),
        },
        exclude_user=sender_id,
    )


async def handle_presence_update(
    manager: ConnectionManager, user_id: str, data: dict
) -> None:
    """User explicitly updates their presence status."""
    status = PresenceStatus(data.get("status", "online"))
    await manager._set_presence(user_id, status)
    await manager._broadcast_presence(user_id, status)


async def handle_heartbeat(
    manager: ConnectionManager, user_id: str, data: dict
) -> None:
    """Process client heartbeat."""
    device_id = data.get("device_id", "web")
    await manager.handle_heartbeat(user_id, device_id)
    await manager.send_to_user(user_id, {"type": "heartbeat.ack"})
```

```typescript
// --- client.ts --- WebSocket client with reconnection ---

interface ChatMessage {
  type: string;
  room_id?: string;
  content?: string;
  client_id?: string;
  [key: string]: any;
}

class ChatClient {
  private ws: WebSocket | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 10;
  private reconnectDelay = 1000;
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null;
  private pendingAcks = new Map<string, (msg: ChatMessage) => void>();
  private messageHandlers = new Map<string, ((msg: ChatMessage) => void)[]>();

  constructor(
    private url: string,
    private token: string,
    private deviceId: string = "web",
  ) {}

  connect(): void {
    this.ws = new WebSocket(`${this.url}?token=${this.token}`);
    this.ws.onopen = () => {
      console.log("Connected to chat server");
      this.reconnectAttempts = 0;
      this.startHeartbeat();
    };

    this.ws.onmessage = (event) => {
      const msg: ChatMessage = JSON.parse(event.data);
      this.handleMessage(msg);
    };

    this.ws.onclose = (event) => {
      console.log(`Disconnected: ${event.code} ${event.reason}`);
      this.stopHeartbeat();
      if (event.code !== 4001) { // not unauthorized
        this.reconnect();
      }
    };

    this.ws.onerror = (error) => {
      console.error("WebSocket error:", error);
    };
  }

  private reconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error("Max reconnect attempts reached");
      return;
    }
    const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts);
    this.reconnectAttempts++;
    console.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
    setTimeout(() => this.connect(), delay);
  }

  sendMessage(roomId: string, content: string): Promise<ChatMessage> {
    const clientId = crypto.randomUUID();
    return new Promise((resolve, reject) => {
      // Register pending ack
      this.pendingAcks.set(clientId, resolve);
      setTimeout(() => {
        if (this.pendingAcks.has(clientId)) {
          this.pendingAcks.delete(clientId);
          reject(new Error("Message ack timeout"));
        }
      }, 10000);

      this.send({
        type: "chat.message",
        room_id: roomId,
        content: content,
        client_id: clientId,
      });
    });
  }

  sendTyping(roomId: string, isTyping: boolean): void {
    this.send({
      type: "chat.typing",
      room_id: roomId,
      is_typing: isTyping,
    });
  }

  markRead(roomId: string, lastMessageId: string): void {
    this.send({
      type: "chat.read",
      room_id: roomId,
      last_read_message_id: lastMessageId,
    });
  }

  on(type: string, handler: (msg: ChatMessage) => void): void {
    if (!this.messageHandlers.has(type)) {
      this.messageHandlers.set(type, []);
    }
    this.messageHandlers.get(type)!.push(handler);
  }

  private handleMessage(msg: ChatMessage): void {
    // Handle acks for pending messages
    if (msg.type === "chat.ack" && msg.client_id) {
      const resolve = this.pendingAcks.get(msg.client_id);
      if (resolve) {
        this.pendingAcks.delete(msg.client_id);
        resolve(msg);
      }
    }

    // Dispatch to registered handlers
    const handlers = this.messageHandlers.get(msg.type) || [];
    handlers.forEach((h) => h(msg));
  }

  private send(msg: ChatMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  private startHeartbeat(): void {
    this.heartbeatInterval = setInterval(() => {
      this.send({ type: "heartbeat", device_id: this.deviceId });
    }, 30000);
  }

  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
    }
  }
}

// Usage:
// const chat = new ChatClient("wss://chat.example.com/ws/chat", authToken);
// chat.connect();
// chat.on("chat.message", (msg) => console.log("New message:", msg));
// await chat.sendMessage("room-123", "Hello!");
```

| Component | Technology | Purpose |
|-----------|-----------|---------|
| WebSocket server | FastAPI + uvicorn | Real-time bidirectional communication |
| Connection registry | In-memory dict + Redis | Track who is connected where |
| Presence | Redis with TTL | Track online/offline/away status |
| Cross-server routing | Redis pub/sub | Route messages between server instances |
| Heartbeat | Client-side timer | Detect stale connections, refresh presence |
| Reconnection | Client-side backoff | Auto-recover from network interruptions |

Key patterns:
1. Support multiple devices per user — each gets a separate connection with a device ID
2. Use heartbeats (30s interval, 90s timeout) to detect dead connections and update presence
3. Client-side reconnection with exponential backoff handles network interruptions gracefully
4. Use Redis pub/sub for cross-server message routing in horizontally scaled deployments
5. Acknowledge every message with a `chat.ack` so clients know delivery succeeded'''
    ),
    (
        "system-design/message-delivery-guarantees",
        "Design message delivery guarantees for a chat system including at-least-once delivery, read receipts, and offline message queuing.",
        '''Message delivery guarantees with at-least-once delivery and read receipts:

```python
# --- delivery.py --- Message delivery guarantee system ---

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field

import redis.asyncio as redis

logger = logging.getLogger(__name__)


class DeliveryStatus(Enum):
    PENDING = "pending"         # saved but not delivered
    SENT = "sent"              # sent over WebSocket
    DELIVERED = "delivered"     # client acknowledged receipt
    READ = "read"              # user has seen the message
    FAILED = "failed"          # delivery failed after retries


@dataclass
class MessageDelivery:
    """Track delivery status per recipient."""
    message_id: str
    recipient_id: str
    status: DeliveryStatus
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    read_at: Optional[datetime] = None
    retry_count: int = 0
    last_retry_at: Optional[datetime] = None


class DeliveryManager:
    """Ensures at-least-once message delivery.

    Flow:
    1. Message saved to DB (PENDING)
    2. Sent via WebSocket (SENT)
    3. Client sends delivery ack (DELIVERED)
    4. User sees message (READ)

    If client is offline, messages queue and deliver on reconnect.
    """

    MAX_RETRIES = 5
    RETRY_INTERVAL = timedelta(seconds=30)
    OFFLINE_QUEUE_TTL = timedelta(days=30)

    def __init__(
        self,
        redis_client: redis.Redis,
        message_store: MessageStore,
        connection_manager: ConnectionManager,
    ):
        self.redis = redis_client
        self.store = message_store
        self.connections = connection_manager

    async def deliver_message(
        self, message: dict, recipient_ids: list[str]
    ) -> dict[str, DeliveryStatus]:
        """Deliver a message to all recipients with guarantees."""
        results: dict[str, DeliveryStatus] = {}

        for recipient_id in recipient_ids:
            delivery = MessageDelivery(
                message_id=message["id"],
                recipient_id=recipient_id,
                status=DeliveryStatus.PENDING,
            )

            # Check if recipient is online
            is_online = await self._is_user_online(recipient_id)

            if is_online:
                # Try immediate delivery via WebSocket
                success = await self._send_via_websocket(recipient_id, message)
                if success:
                    delivery.status = DeliveryStatus.SENT
                    delivery.sent_at = datetime.utcnow()
                else:
                    # WebSocket send failed — queue for retry
                    await self._enqueue_for_delivery(delivery, message)
            else:
                # User offline — add to offline queue
                await self._enqueue_offline(recipient_id, message)
                delivery.status = DeliveryStatus.PENDING

            await self._save_delivery_status(delivery)
            results[recipient_id] = delivery.status

        return results

    async def process_delivery_ack(
        self, recipient_id: str, message_id: str
    ) -> None:
        """Client acknowledges receipt of a message."""
        await self._update_delivery_status(
            message_id, recipient_id,
            DeliveryStatus.DELIVERED,
            delivered_at=datetime.utcnow(),
        )

        # Remove from retry queue
        await self.redis.srem(
            f"delivery:pending:{recipient_id}", message_id
        )

        logger.debug(f"Delivery ack: {message_id} -> {recipient_id}")

    async def process_read_receipt(
        self, reader_id: str, room_id: str, last_read_message_id: str
    ) -> None:
        """User has read messages up to a certain point."""
        # Get all message IDs in the room up to last_read
        message_ids = await self.store.get_message_ids_up_to(
            room_id, last_read_message_id
        )

        for msg_id in message_ids:
            await self._update_delivery_status(
                msg_id, reader_id,
                DeliveryStatus.READ,
                read_at=datetime.utcnow(),
            )

        # Notify the message senders
        for msg_id in message_ids:
            message = await self.store.get_message(msg_id)
            if message and message["sender_id"] != reader_id:
                await self.connections.send_to_user(
                    message["sender_id"],
                    {
                        "type": "chat.read_receipt",
                        "message_id": msg_id,
                        "room_id": room_id,
                        "reader_id": reader_id,
                        "read_at": datetime.utcnow().isoformat(),
                    },
                )

    async def deliver_offline_queue(self, user_id: str) -> int:
        """Deliver queued messages when a user comes online.

        Called when a WebSocket connection is established.
        """
        queue_key = f"offline:{user_id}:messages"
        messages = await self.redis.lrange(queue_key, 0, -1)

        delivered = 0
        for msg_data in messages:
            message = json.loads(msg_data)
            success = await self._send_via_websocket(user_id, message)
            if success:
                delivered += 1

        # Clear the offline queue
        if delivered > 0:
            await self.redis.delete(queue_key)
            logger.info(f"Delivered {delivered} offline messages to {user_id}")

        return delivered

    async def retry_failed_deliveries(self) -> int:
        """Background job: retry pending deliveries.

        Run every 30 seconds to catch messages stuck in SENT state
        (WebSocket sent but no delivery ack from client).
        """
        retry_count = 0
        # Scan for users with pending deliveries
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(
                cursor, match="delivery:pending:*", count=100
            )
            for key in keys:
                user_id = key.decode().split(":")[-1]
                message_ids = await self.redis.smembers(key)

                for msg_id in message_ids:
                    msg_id_str = msg_id.decode() if isinstance(msg_id, bytes) else msg_id
                    delivery = await self._get_delivery_status(msg_id_str, user_id)

                    if not delivery:
                        continue
                    if delivery.retry_count >= self.MAX_RETRIES:
                        delivery.status = DeliveryStatus.FAILED
                        await self._save_delivery_status(delivery)
                        await self.redis.srem(key, msg_id)
                        continue

                    # Retry delivery
                    message = await self.store.get_message(msg_id_str)
                    if message:
                        success = await self._send_via_websocket(user_id, message)
                        delivery.retry_count += 1
                        delivery.last_retry_at = datetime.utcnow()
                        if success:
                            delivery.status = DeliveryStatus.SENT
                        await self._save_delivery_status(delivery)
                        retry_count += 1

            if cursor == 0:
                break

        return retry_count

    async def _send_via_websocket(self, user_id: str, message: dict) -> bool:
        """Attempt WebSocket delivery."""
        try:
            sent = await self.connections.send_to_user(user_id, {
                "type": "chat.message",
                **message,
            })
            return sent > 0
        except Exception as e:
            logger.warning(f"WebSocket delivery failed for {user_id}: {e}")
            return False

    async def _enqueue_offline(self, user_id: str, message: dict) -> None:
        """Add message to user's offline queue in Redis."""
        queue_key = f"offline:{user_id}:messages"
        await self.redis.rpush(queue_key, json.dumps(message))
        await self.redis.expire(queue_key, int(self.OFFLINE_QUEUE_TTL.total_seconds()))

    async def _enqueue_for_delivery(self, delivery: MessageDelivery, message: dict) -> None:
        """Add to retry queue."""
        await self.redis.sadd(
            f"delivery:pending:{delivery.recipient_id}",
            delivery.message_id,
        )

    async def _is_user_online(self, user_id: str) -> bool:
        return await self.redis.exists(f"presence:{user_id}")

    async def _save_delivery_status(self, delivery: MessageDelivery) -> None:
        key = f"delivery:{delivery.message_id}:{delivery.recipient_id}"
        await self.redis.hset(key, mapping={
            "status": delivery.status.value,
            "retry_count": str(delivery.retry_count),
            "sent_at": delivery.sent_at.isoformat() if delivery.sent_at else "",
            "delivered_at": delivery.delivered_at.isoformat() if delivery.delivered_at else "",
            "read_at": delivery.read_at.isoformat() if delivery.read_at else "",
        })

    async def _update_delivery_status(
        self, message_id: str, recipient_id: str,
        status: DeliveryStatus, **kwargs
    ) -> None:
        key = f"delivery:{message_id}:{recipient_id}"
        updates = {"status": status.value}
        for k, v in kwargs.items():
            updates[k] = v.isoformat() if isinstance(v, datetime) else str(v)
        await self.redis.hset(key, mapping=updates)

    async def _get_delivery_status(
        self, message_id: str, recipient_id: str
    ) -> Optional[MessageDelivery]:
        key = f"delivery:{message_id}:{recipient_id}"
        data = await self.redis.hgetall(key)
        if not data:
            return None
        return MessageDelivery(
            message_id=message_id,
            recipient_id=recipient_id,
            status=DeliveryStatus(data.get(b"status", b"pending").decode()),
            retry_count=int(data.get(b"retry_count", b"0")),
        )
```

```python
# --- client_delivery.py --- Client-side delivery tracking ---

import json
import time
from dataclasses import dataclass
from typing import Callable


@dataclass
class ClientMessageTracker:
    """Client-side message delivery tracking.

    Handles:
    - Optimistic UI (show message immediately)
    - Server ack (message saved)
    - Delivery ack (recipient received)
    - Read receipt (recipient read)
    - Retry on failure
    """

    def __init__(self, ws_client):
        self.ws = ws_client
        self.pending: dict[str, dict] = {}  # client_id -> message
        self.ack_timeout_ms = 10000

    def send_message(self, room_id: str, content: str, on_status: Callable) -> str:
        """Send message with delivery tracking.

        Status callbacks:
        - "sending" — optimistic UI
        - "sent" — server ack received
        - "delivered" — recipient ack received
        - "read" — recipient read
        - "failed" — delivery failed
        """
        client_id = generate_uuid()

        message = {
            "type": "chat.message",
            "room_id": room_id,
            "content": content,
            "client_id": client_id,
        }

        # Optimistic UI
        on_status("sending", client_id)
        self.pending[client_id] = {
            "message": message,
            "on_status": on_status,
            "sent_at": time.time(),
            "retries": 0,
        }

        # Send via WebSocket
        self.ws.send(json.dumps(message))

        # Set timeout for ack
        self._schedule_retry(client_id)

        return client_id

    def handle_server_ack(self, data: dict) -> None:
        """Server confirms message was saved."""
        client_id = data["client_id"]
        if client_id in self.pending:
            entry = self.pending[client_id]
            entry["server_msg_id"] = data["message_id"]
            entry["on_status"]("sent", client_id)

    def handle_delivery_ack(self, data: dict) -> None:
        """Recipient's device confirms receipt."""
        # Match by server message ID
        for client_id, entry in self.pending.items():
            if entry.get("server_msg_id") == data["message_id"]:
                entry["on_status"]("delivered", client_id)
                break

    def handle_read_receipt(self, data: dict) -> None:
        """Recipient has read the message."""
        for client_id, entry in self.pending.items():
            if entry.get("server_msg_id") == data["message_id"]:
                entry["on_status"]("read", client_id)
                del self.pending[client_id]
                break

    def _schedule_retry(self, client_id: str) -> None:
        """Retry if no server ack within timeout."""
        # Implementation depends on client framework (setTimeout, asyncio, etc.)
        pass
```

```
Message Delivery Flow:

Sender                 Server                 Recipient
  |                      |                       |
  |-- chat.message ----->|                       |
  |   (client_id: abc)   |                       |
  |                      |-- save to DB          |
  |<---- chat.ack -------|                       |
  |   (msg_id: xyz)      |                       |
  |                      |                       |
  |   [Recipient Online] |                       |
  |                      |-- chat.message ------>|
  |                      |   (msg_id: xyz)       |
  |                      |                       |
  |                      |<-- delivery.ack ------|
  |<-- delivery.ack -----|   (msg_id: xyz)       |
  |   (msg_id: xyz)      |                       |
  |                      |                       |
  |   [Recipient Reads]  |                       |
  |                      |<-- chat.read ---------|
  |<-- read.receipt -----|   (last_read: xyz)    |
  |   (msg_id: xyz)      |                       |

  Status: sending -> sent -> delivered -> read

Offline Delivery:
  |                      |                       |
  |-- chat.message ----->|                       |
  |<---- chat.ack -------|                       |
  |                      |-- enqueue offline --->| (stored in Redis)
  |                      |                       |
  |   [Recipient Reconnects]                     |
  |                      |<-- connect ----------|
  |                      |-- flush offline ----->|
  |                      |<-- delivery.ack ------|
```

| Guarantee | Implementation | Trade-off |
|-----------|---------------|-----------|
| At-most-once | Fire and forget via WebSocket | Fast but messages can be lost |
| At-least-once | Persist + retry + ack | Reliable but may duplicate |
| Exactly-once | Idempotent delivery + dedup | Most reliable, highest complexity |
| Ordered | Sequence numbers per room | Important for conversation flow |

Key patterns:
1. Save to database BEFORE sending via WebSocket — ensures message survives server crash
2. Use client-generated `client_id` for deduplication if the same message is sent twice
3. Queue messages for offline users in Redis with TTL — deliver on reconnect
4. Retry delivery with backoff, move to FAILED after max retries
5. Read receipts use a "high water mark" (last_read_message_id) instead of per-message tracking'''
    ),
    (
        "system-design/chat-storage",
        "Compare fan-out on write vs fan-out on read for chat message storage and show the storage schema design.",
        '''Chat storage strategies — fan-out on write vs fan-out on read:

```python
# --- fanout_write.py --- Fan-out on Write strategy ---

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional


class FanoutOnWriteStorage:
    """Fan-out on Write: when a message is sent, write a copy
    to each recipient's inbox.

    Pros: Read is fast (just query your own inbox)
    Cons: Write amplification (N copies for N recipients)

    Best for: Small groups, DMs, low fan-out (<100 members)
    """

    def __init__(self, db):
        self.db = db

    async def send_message(
        self, sender_id: str, room_id: str, content: str
    ) -> dict:
        """Write message + fan out to all recipient inboxes."""
        message_id = f"msg_{uuid.uuid4().hex[:12]}"
        now = datetime.utcnow()

        # 1. Write the canonical message
        message = {
            "id": message_id,
            "room_id": room_id,
            "sender_id": sender_id,
            "content": content,
            "created_at": now.isoformat(),
        }
        await self.db.execute(
            """INSERT INTO messages (id, room_id, sender_id, content, created_at)
               VALUES (:id, :room_id, :sender_id, :content, :created_at)""",
            message,
        )

        # 2. Fan out: write to each member's inbox
        members = await self.db.fetch_all(
            "SELECT user_id FROM room_members WHERE room_id = :room_id",
            {"room_id": room_id},
        )

        inbox_entries = [
            {
                "user_id": member["user_id"],
                "message_id": message_id,
                "room_id": room_id,
                "created_at": now.isoformat(),
                "is_read": member["user_id"] == sender_id,  # sender auto-read
            }
            for member in members
        ]

        await self.db.execute_many(
            """INSERT INTO user_inbox (user_id, message_id, room_id, created_at, is_read)
               VALUES (:user_id, :message_id, :room_id, :created_at, :is_read)""",
            inbox_entries,
        )

        return message

    async def get_inbox(
        self, user_id: str, limit: int = 50, before: Optional[str] = None
    ) -> list[dict]:
        """Read user's inbox — fast, single table scan."""
        query = """
            SELECT m.*, ui.is_read
            FROM user_inbox ui
            JOIN messages m ON m.id = ui.message_id
            WHERE ui.user_id = :user_id
        """
        params = {"user_id": user_id, "limit": limit}

        if before:
            query += " AND ui.created_at < :before"
            params["before"] = before

        query += " ORDER BY ui.created_at DESC LIMIT :limit"
        return await self.db.fetch_all(query, params)

    async def get_room_messages(
        self, user_id: str, room_id: str, limit: int = 50
    ) -> list[dict]:
        """Get messages for a specific room from inbox."""
        return await self.db.fetch_all(
            """SELECT m.*, ui.is_read
               FROM user_inbox ui
               JOIN messages m ON m.id = ui.message_id
               WHERE ui.user_id = :user_id AND ui.room_id = :room_id
               ORDER BY m.created_at DESC
               LIMIT :limit""",
            {"user_id": user_id, "room_id": room_id, "limit": limit},
        )


class FanoutOnReadStorage:
    """Fan-out on Read: write message once, each reader queries
    from the shared messages table.

    Pros: Write is fast (single insert)
    Cons: Read may be slow for users in many rooms

    Best for: Large groups, channels, broadcast (100+ members)
    """

    def __init__(self, db):
        self.db = db

    async def send_message(
        self, sender_id: str, room_id: str, content: str
    ) -> dict:
        """Write message once — no fan-out."""
        message_id = f"msg_{uuid.uuid4().hex[:12]}"
        message = {
            "id": message_id,
            "room_id": room_id,
            "sender_id": sender_id,
            "content": content,
            "created_at": datetime.utcnow().isoformat(),
        }

        await self.db.execute(
            """INSERT INTO messages (id, room_id, sender_id, content, created_at)
               VALUES (:id, :room_id, :sender_id, :content, :created_at)""",
            message,
        )
        return message

    async def get_inbox(
        self, user_id: str, limit: int = 50
    ) -> list[dict]:
        """Read inbox — must query all rooms the user is in."""
        return await self.db.fetch_all(
            """SELECT m.*, rm.room_id,
                      CASE WHEN rc.last_read_at >= m.created_at THEN true ELSE false END as is_read
               FROM room_members rm
               JOIN messages m ON m.room_id = rm.room_id
               LEFT JOIN read_cursors rc ON rc.user_id = :user_id AND rc.room_id = m.room_id
               WHERE rm.user_id = :user_id
               ORDER BY m.created_at DESC
               LIMIT :limit""",
            {"user_id": user_id, "limit": limit},
        )

    async def get_room_messages(
        self, room_id: str, limit: int = 50, before: Optional[str] = None
    ) -> list[dict]:
        """Get messages for a room — simple indexed query."""
        query = "SELECT * FROM messages WHERE room_id = :room_id"
        params = {"room_id": room_id, "limit": limit}

        if before:
            query += " AND created_at < :before"
            params["before"] = before

        query += " ORDER BY created_at DESC LIMIT :limit"
        return await self.db.fetch_all(query, params)
```

```sql
-- Schema for hybrid fan-out approach

-- Canonical message store (single source of truth)
CREATE TABLE messages (
    id          VARCHAR(32) PRIMARY KEY,
    room_id     VARCHAR(32) NOT NULL,
    sender_id   VARCHAR(32) NOT NULL,
    content     TEXT NOT NULL,
    content_type VARCHAR(20) DEFAULT 'text',  -- text, image, file, system
    metadata    JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ,
    deleted_at  TIMESTAMPTZ  -- soft delete
);

-- Partition messages by room for efficient room queries
CREATE INDEX idx_messages_room_time ON messages (room_id, created_at DESC);
CREATE INDEX idx_messages_sender ON messages (sender_id, created_at DESC);

-- Fan-out inbox (for DMs and small groups only)
CREATE TABLE user_inbox (
    user_id     VARCHAR(32) NOT NULL,
    message_id  VARCHAR(32) NOT NULL REFERENCES messages(id),
    room_id     VARCHAR(32) NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL,
    is_read     BOOLEAN DEFAULT FALSE,
    PRIMARY KEY (user_id, message_id)
);

CREATE INDEX idx_inbox_user_time ON user_inbox (user_id, created_at DESC);
CREATE INDEX idx_inbox_unread ON user_inbox (user_id, is_read) WHERE is_read = FALSE;

-- Room membership
CREATE TABLE room_members (
    room_id     VARCHAR(32) NOT NULL,
    user_id     VARCHAR(32) NOT NULL,
    role        VARCHAR(20) DEFAULT 'member',  -- owner, admin, member
    joined_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    muted_until TIMESTAMPTZ,
    PRIMARY KEY (room_id, user_id)
);

CREATE INDEX idx_room_members_user ON room_members (user_id);

-- Rooms (conversations, groups, channels)
CREATE TABLE rooms (
    id              VARCHAR(32) PRIMARY KEY,
    type            VARCHAR(20) NOT NULL,  -- dm, group, channel
    name            VARCHAR(200),
    member_count    INT DEFAULT 0,
    last_message_at TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Read cursors (for fan-out on read)
CREATE TABLE read_cursors (
    user_id         VARCHAR(32) NOT NULL,
    room_id         VARCHAR(32) NOT NULL,
    last_read_id    VARCHAR(32),
    last_read_at    TIMESTAMPTZ,
    PRIMARY KEY (user_id, room_id)
);

-- Unread count cache (denormalized for fast badge counts)
CREATE TABLE unread_counts (
    user_id         VARCHAR(32) NOT NULL,
    room_id         VARCHAR(32) NOT NULL,
    unread_count    INT DEFAULT 0,
    last_updated    TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, room_id)
);
```

```python
# --- hybrid_storage.py --- Hybrid approach used by production systems ---

class HybridChatStorage:
    """Hybrid fan-out strategy used by most production chat systems.

    - DMs and small groups (<50 members): fan-out on write
    - Large channels (50+ members): fan-out on read
    - Celebrity/broadcast accounts: fan-out on read with caching
    """

    FANOUT_THRESHOLD = 50  # switch to read fan-out above this

    def __init__(self, db, cache):
        self.db = db
        self.cache = cache
        self.write_storage = FanoutOnWriteStorage(db)
        self.read_storage = FanoutOnReadStorage(db)

    async def send_message(
        self, sender_id: str, room_id: str, content: str
    ) -> dict:
        """Route to appropriate storage strategy based on room size."""
        room = await self._get_room(room_id)

        if room["member_count"] <= self.FANOUT_THRESHOLD:
            # Small group: fan-out on write for fast reads
            message = await self.write_storage.send_message(
                sender_id, room_id, content
            )
        else:
            # Large channel: write once, read fans out
            message = await self.read_storage.send_message(
                sender_id, room_id, content
            )

        # Update room's last_message timestamp
        await self.db.execute(
            "UPDATE rooms SET last_message_at = NOW() WHERE id = :id",
            {"id": room_id},
        )

        # Invalidate room list cache for all members
        members = await self.db.fetch_all(
            "SELECT user_id FROM room_members WHERE room_id = :room_id",
            {"room_id": room_id},
        )
        for member in members:
            await self.cache.delete(f"room_list:{member['user_id']}")

        # Update unread counts
        await self._increment_unread(room_id, sender_id, members)

        return message

    async def get_conversation_list(self, user_id: str) -> list[dict]:
        """Get user's conversation list (sidebar) with unread counts.

        This is the most frequently called query — must be fast.
        Cache aggressively.
        """
        cache_key = f"room_list:{user_id}"
        cached = await self.cache.get(cache_key)
        if cached:
            return json.loads(cached)

        rooms = await self.db.fetch_all(
            """SELECT r.*, rm.muted_until, uc.unread_count,
                      m.content as last_message_content,
                      m.sender_id as last_message_sender
               FROM room_members rm
               JOIN rooms r ON r.id = rm.room_id
               LEFT JOIN unread_counts uc
                   ON uc.user_id = :user_id AND uc.room_id = r.id
               LEFT JOIN messages m
                   ON m.id = (SELECT id FROM messages WHERE room_id = r.id
                              ORDER BY created_at DESC LIMIT 1)
               WHERE rm.user_id = :user_id
               ORDER BY r.last_message_at DESC NULLS LAST
               LIMIT 100""",
            {"user_id": user_id},
        )

        await self.cache.set(cache_key, json.dumps(rooms, default=str), ex=60)
        return rooms

    async def _get_room(self, room_id: str) -> dict:
        return await self.db.fetch_one(
            "SELECT * FROM rooms WHERE id = :id", {"id": room_id}
        )

    async def _increment_unread(
        self, room_id: str, sender_id: str, members: list[dict]
    ) -> None:
        for member in members:
            if member["user_id"] != sender_id:
                await self.db.execute(
                    """INSERT INTO unread_counts (user_id, room_id, unread_count)
                       VALUES (:user_id, :room_id, 1)
                       ON CONFLICT (user_id, room_id)
                       DO UPDATE SET unread_count = unread_counts.unread_count + 1,
                                     last_updated = NOW()""",
                    {"user_id": member["user_id"], "room_id": room_id},
                )
```

| Strategy | Write cost | Read cost | Best for |
|----------|-----------|----------|----------|
| Fan-out on write | O(N) per message | O(1) per user | DMs, small groups (<50) |
| Fan-out on read | O(1) per message | O(R) per user (R=rooms) | Large channels (100+) |
| Hybrid | Varies by room size | Varies by room size | Production systems |
| Timeline cache | O(N) + cache | O(1) from cache | High-read celebrity feeds |

Key patterns:
1. Use hybrid approach: fan-out on write for DMs/small groups, fan-out on read for large channels
2. Denormalize unread counts into a separate table for instant badge rendering
3. Cache the conversation list (sidebar) aggressively — it is the hottest read path
4. Use read cursors (high-water mark) instead of per-message read tracking for efficiency
5. Partition messages by room_id for efficient range queries within a conversation'''
    ),
    (
        "system-design/push-notifications",
        "Design a push notification infrastructure supporting iOS APNS, Android FCM, and web push with delivery tracking.",
        '''Push notification infrastructure with multi-platform delivery:

```python
# --- push_service.py --- Multi-platform push notification service ---

from __future__ import annotations

import json
import logging
import asyncio
from datetime import datetime
from enum import Enum
from typing import Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class Platform(Enum):
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


class PushPriority(Enum):
    HIGH = "high"       # immediate delivery, wakes device
    NORMAL = "normal"   # batched by OS for battery optimization


@dataclass
class DeviceToken:
    """Registered device for push notifications."""
    user_id: str
    device_id: str
    platform: Platform
    token: str                    # APNS token, FCM token, or web push subscription
    app_version: str
    os_version: str
    enabled: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_used_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class PushNotification:
    """Push notification payload."""
    id: str
    user_id: str
    title: str
    body: str
    category: str               # "chat_message", "mention", "system"
    priority: PushPriority
    data: dict[str, Any] = field(default_factory=dict)
    badge_count: Optional[int] = None
    sound: str = "default"
    image_url: Optional[str] = None
    thread_id: Optional[str] = None   # group notifications (iOS)
    collapse_key: Optional[str] = None # replace previous (Android)
    ttl_seconds: int = 86400          # expiry: 24 hours default


class PushNotificationService:
    """Send push notifications across all platforms."""

    def __init__(
        self,
        apns_provider: APNSProvider,
        fcm_provider: FCMProvider,
        web_push_provider: WebPushProvider,
        device_store: DeviceTokenStore,
        delivery_tracker: DeliveryTracker,
    ):
        self.apns = apns_provider
        self.fcm = fcm_provider
        self.web_push = web_push_provider
        self.devices = device_store
        self.tracker = delivery_tracker

    async def send(
        self, notification: PushNotification
    ) -> dict[str, list[str]]:
        """Send notification to all user's devices.

        Returns: {"sent": [...], "failed": [...], "skipped": [...]}
        """
        # Get all registered devices for the user
        tokens = await self.devices.get_user_devices(
            notification.user_id, enabled_only=True
        )

        if not tokens:
            logger.debug(f"No devices for user {notification.user_id}")
            return {"sent": [], "failed": [], "skipped": []}

        # Check user preferences
        if await self._should_suppress(notification):
            return {"sent": [], "failed": [], "skipped": [t.device_id for t in tokens]}

        # Send to each platform in parallel
        results = {"sent": [], "failed": [], "skipped": []}
        tasks = []

        for device in tokens:
            task = self._send_to_device(notification, device)
            tasks.append((device, task))

        send_results = await asyncio.gather(
            *[t[1] for t in tasks], return_exceptions=True
        )

        for (device, _), result in zip(tasks, send_results):
            if isinstance(result, Exception):
                results["failed"].append(device.device_id)
                await self._handle_send_error(device, result)
            elif result:
                results["sent"].append(device.device_id)
            else:
                results["failed"].append(device.device_id)

        # Track delivery
        await self.tracker.record(notification.id, results)

        return results

    async def _send_to_device(
        self, notification: PushNotification, device: DeviceToken
    ) -> bool:
        """Route to platform-specific provider."""
        if device.platform == Platform.IOS:
            return await self.apns.send(
                token=device.token,
                title=notification.title,
                body=notification.body,
                badge=notification.badge_count,
                sound=notification.sound,
                category=notification.category,
                thread_id=notification.thread_id,
                data=notification.data,
                priority=notification.priority,
                ttl=notification.ttl_seconds,
            )
        elif device.platform == Platform.ANDROID:
            return await self.fcm.send(
                token=device.token,
                title=notification.title,
                body=notification.body,
                data=notification.data,
                priority=notification.priority,
                collapse_key=notification.collapse_key,
                ttl=notification.ttl_seconds,
                image_url=notification.image_url,
            )
        elif device.platform == Platform.WEB:
            return await self.web_push.send(
                subscription=json.loads(device.token),
                title=notification.title,
                body=notification.body,
                data=notification.data,
                ttl=notification.ttl_seconds,
                image_url=notification.image_url,
            )
        return False

    async def _should_suppress(self, notification: PushNotification) -> bool:
        """Check if notification should be suppressed (DND, muted room)."""
        # Check if user is currently active on WebSocket (don't push if online)
        if notification.category == "chat_message":
            is_online = await self.devices.is_user_active(notification.user_id)
            if is_online:
                return True

        # Check DND schedule
        prefs = await self.devices.get_user_preferences(notification.user_id)
        if prefs and prefs.get("dnd_enabled"):
            return self._in_dnd_window(prefs)

        # Check if room is muted
        room_id = notification.data.get("room_id")
        if room_id:
            is_muted = await self.devices.is_room_muted(
                notification.user_id, room_id
            )
            if is_muted:
                return True

        return False

    async def _handle_send_error(
        self, device: DeviceToken, error: Exception
    ) -> None:
        """Handle platform-specific errors."""
        error_str = str(error)

        # Token is invalid or expired — remove device
        if any(code in error_str for code in [
            "InvalidRegistration", "NotRegistered",   # FCM
            "BadDeviceToken", "Unregistered",          # APNS
            "410",                                      # Web Push
        ]):
            logger.info(f"Removing invalid device: {device.device_id}")
            await self.devices.remove_device(device.user_id, device.device_id)
        else:
            logger.warning(f"Push send error for {device.device_id}: {error}")

    def _in_dnd_window(self, prefs: dict) -> bool:
        from datetime import time as dt_time
        now = datetime.utcnow().time()
        dnd_start = dt_time.fromisoformat(prefs.get("dnd_start", "22:00"))
        dnd_end = dt_time.fromisoformat(prefs.get("dnd_end", "08:00"))
        if dnd_start <= dnd_end:
            return dnd_start <= now <= dnd_end
        return now >= dnd_start or now <= dnd_end
```

```python
# --- apns_provider.py --- Apple Push Notification Service ---

import jwt
import httpx
import time
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class APNSConfig:
    team_id: str
    key_id: str
    private_key_path: str
    bundle_id: str
    use_sandbox: bool = False

    @property
    def endpoint(self) -> str:
        if self.use_sandbox:
            return "https://api.sandbox.push.apple.com"
        return "https://api.push.apple.com"


class APNSProvider:
    """Send notifications via Apple Push Notification Service (HTTP/2)."""

    def __init__(self, config: APNSConfig):
        self.config = config
        self._token: str = ""
        self._token_expires: float = 0
        self._client = httpx.AsyncClient(http2=True)

    async def send(
        self,
        token: str,
        title: str,
        body: str,
        badge: int | None = None,
        sound: str = "default",
        category: str = "",
        thread_id: str | None = None,
        data: dict | None = None,
        priority: str = "high",
        ttl: int = 86400,
    ) -> bool:
        """Send a single APNS notification."""
        payload = {
            "aps": {
                "alert": {"title": title, "body": body},
                "sound": sound,
                "category": category,
                "mutable-content": 1,  # allow notification extension
            },
        }

        if badge is not None:
            payload["aps"]["badge"] = badge
        if thread_id:
            payload["aps"]["thread-id"] = thread_id
        if data:
            payload.update(data)

        headers = {
            "authorization": f"bearer {self._get_auth_token()}",
            "apns-topic": self.config.bundle_id,
            "apns-priority": "10" if priority == "high" else "5",
            "apns-expiration": str(int(time.time()) + ttl),
            "apns-push-type": "alert",
        }

        url = f"{self.config.endpoint}/3/device/{token}"

        response = await self._client.post(
            url, json=payload, headers=headers
        )

        if response.status_code == 200:
            return True

        error = response.json() if response.content else {}
        reason = error.get("reason", "unknown")
        logger.warning(f"APNS error: {response.status_code} {reason}")

        if reason in ("BadDeviceToken", "Unregistered"):
            raise InvalidTokenError(reason)

        return False

    def _get_auth_token(self) -> str:
        """Generate JWT for APNS authentication (valid for 1 hour)."""
        now = time.time()
        if self._token and now < self._token_expires:
            return self._token

        with open(self.config.private_key_path, "r") as f:
            private_key = f.read()

        headers = {"alg": "ES256", "kid": self.config.key_id}
        payload = {"iss": self.config.team_id, "iat": int(now)}

        self._token = jwt.encode(payload, private_key, algorithm="ES256", headers=headers)
        self._token_expires = now + 3500  # refresh 100s before expiry
        return self._token


class InvalidTokenError(Exception):
    pass
```

```python
# --- fcm_provider.py --- Firebase Cloud Messaging ---

import httpx
import google.auth.transport.requests
from google.oauth2 import service_account
import logging

logger = logging.getLogger(__name__)

FCM_ENDPOINT = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"


class FCMProvider:
    """Send notifications via Firebase Cloud Messaging (FCM v1 HTTP API)."""

    def __init__(self, project_id: str, service_account_path: str):
        self.project_id = project_id
        self.credentials = service_account.Credentials.from_service_account_file(
            service_account_path,
            scopes=["https://www.googleapis.com/auth/firebase.messaging"],
        )
        self._client = httpx.AsyncClient()

    async def send(
        self,
        token: str,
        title: str,
        body: str,
        data: dict | None = None,
        priority: str = "high",
        collapse_key: str | None = None,
        ttl: int = 86400,
        image_url: str | None = None,
    ) -> bool:
        """Send a single FCM notification."""
        message = {
            "message": {
                "token": token,
                "notification": {
                    "title": title,
                    "body": body,
                },
                "android": {
                    "priority": priority.upper(),
                    "ttl": f"{ttl}s",
                    "notification": {
                        "channel_id": "chat_messages",
                        "click_action": "OPEN_CHAT",
                    },
                },
            }
        }

        if data:
            # FCM data must be string values
            message["message"]["data"] = {
                k: str(v) for k, v in data.items()
            }

        if collapse_key:
            message["message"]["android"]["collapse_key"] = collapse_key

        if image_url:
            message["message"]["notification"]["image"] = image_url

        # Refresh OAuth2 token
        self.credentials.refresh(google.auth.transport.requests.Request())

        url = FCM_ENDPOINT.format(project_id=self.project_id)
        response = await self._client.post(
            url,
            json=message,
            headers={
                "Authorization": f"Bearer {self.credentials.token}",
                "Content-Type": "application/json",
            },
        )

        if response.status_code == 200:
            return True

        error = response.json().get("error", {})
        code = error.get("code", 0)
        status = error.get("status", "")

        logger.warning(f"FCM error: {code} {status}")

        if status in ("NOT_FOUND", "INVALID_ARGUMENT"):
            raise InvalidTokenError(status)

        return False
```

| Platform | Service | Protocol | Auth | Token lifecycle |
|----------|---------|----------|------|----------------|
| iOS | APNS | HTTP/2 | JWT (ES256) | Token changes on OS update, app reinstall |
| Android | FCM | HTTP/1.1 | OAuth2 (service account) | Token changes on app uninstall, data clear |
| Web | Web Push | HTTP/1.1 | VAPID (ES256) | Subscription expires (varies by browser) |

Key patterns:
1. Suppress push notifications when the user is actively connected via WebSocket
2. Clean up invalid device tokens immediately on receipt of platform error responses
3. Use collapse keys (Android) and thread IDs (iOS) to group related notifications
4. Respect DND schedules and room mute settings before sending
5. Send to all devices in parallel and track per-device delivery for analytics'''
    ),
]
