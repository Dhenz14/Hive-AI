PAIRS = [
    ("projects/websocket-chat", r'''<think>
A WebSocket chat server needs connection management, room support,
and message broadcasting. I will use the websockets library with asyncio
for the server foundation, and store connections in a registry.
</think>
Build a WebSocket chat server with room management and connection tracking.''', r'''import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Dict, Optional, Set
import websockets
from websockets.server import WebSocketServerProtocol

logger = logging.getLogger(__name__)


@dataclass
class Client:
    """Represents a connected chat client."""
    ws: WebSocketServerProtocol
    user_id: str
    username: str
    room: Optional[str] = None
    connected_at: float = field(default_factory=time.time)

    async def send(self, message: dict) -> None:
        try:
            await self.ws.send(json.dumps(message))
        except websockets.ConnectionClosed:
            pass


class RoomManager:
    """Manages chat rooms and their members."""

    def __init__(self):
        self._rooms: Dict[str, Set[str]] = {}  # room_name -> set of user_ids
        self._clients: Dict[str, Client] = {}  # user_id -> Client

    def register_client(self, client: Client) -> None:
        self._clients[client.user_id] = client
        logger.info(f"Client registered: {client.username} ({client.user_id})")

    def unregister_client(self, user_id: str) -> None:
        client = self._clients.pop(user_id, None)
        if client and client.room:
            self.leave_room(user_id, client.room)
        logger.info(f"Client unregistered: {user_id}")

    def join_room(self, user_id: str, room_name: str) -> None:
        client = self._clients.get(user_id)
        if not client:
            return

        # Leave current room if in one
        if client.room:
            self.leave_room(user_id, client.room)

        if room_name not in self._rooms:
            self._rooms[room_name] = set()

        self._rooms[room_name].add(user_id)
        client.room = room_name
        logger.info(f"{client.username} joined room {room_name}")

    def leave_room(self, user_id: str, room_name: str) -> None:
        if room_name in self._rooms:
            self._rooms[room_name].discard(user_id)
            if not self._rooms[room_name]:
                del self._rooms[room_name]

        client = self._clients.get(user_id)
        if client and client.room == room_name:
            client.room = None

    def get_room_members(self, room_name: str) -> list:
        user_ids = self._rooms.get(room_name, set())
        members = []
        for uid in user_ids:
            client = self._clients.get(uid)
            if client:
                members.append({"user_id": uid, "username": client.username})
        return members

    async def broadcast_to_room(self, room_name: str, message: dict, exclude: Optional[str] = None) -> None:
        user_ids = self._rooms.get(room_name, set())
        tasks = []
        for uid in user_ids:
            if uid == exclude:
                continue
            client = self._clients.get(uid)
            if client:
                tasks.append(client.send(message))
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def list_rooms(self) -> list:
        return [
            {"name": name, "member_count": len(members)}
            for name, members in self._rooms.items()
        ]


rooms = RoomManager()


async def handle_connection(ws: WebSocketServerProtocol) -> None:
    """Handle a single WebSocket connection."""
    client = None
    try:
        # First message must be authentication
        raw = await asyncio.wait_for(ws.recv(), timeout=10.0)
        auth_msg = json.loads(raw)

        if auth_msg.get("type") != "auth":
            await ws.close(4001, "First message must be auth")
            return

        user_id = auth_msg["user_id"]
        username = auth_msg.get("username", f"user_{user_id}")
        client = Client(ws=ws, user_id=user_id, username=username)
        rooms.register_client(client)

        await client.send({"type": "auth_ok", "user_id": user_id})

        async for raw_message in ws:
            msg = json.loads(raw_message)
            await dispatch_message(client, msg)

    except websockets.ConnectionClosed:
        logger.info("Connection closed normally")
    except asyncio.TimeoutError:
        await ws.close(4002, "Auth timeout")
    except Exception as e:
        logger.error(f"Error in connection handler: {e}")
    finally:
        if client:
            rooms.unregister_client(client.user_id)


async def dispatch_message(client: Client, msg: dict) -> None:
    """Route an incoming message to the appropriate handler."""
    msg_type = msg.get("type")
    if msg_type == "join":
        await handle_join(client, msg)
    elif msg_type == "leave":
        await handle_leave(client, msg)
    elif msg_type == "chat":
        await handle_chat(client, msg)
    elif msg_type == "list_rooms":
        await client.send({"type": "room_list", "rooms": rooms.list_rooms()})


async def handle_join(client: Client, msg: dict) -> None:
    room_name = msg.get("room", "general")
    rooms.join_room(client.user_id, room_name)
    members = rooms.get_room_members(room_name)
    await client.send({"type": "joined", "room": room_name, "members": members})
    await rooms.broadcast_to_room(room_name, {
        "type": "user_joined", "user_id": client.user_id, "username": client.username,
    }, exclude=client.user_id)


async def handle_leave(client: Client, msg: dict) -> None:
    room_name = msg.get("room") or client.room
    if room_name:
        await rooms.broadcast_to_room(room_name, {
            "type": "user_left", "user_id": client.user_id, "username": client.username,
        }, exclude=client.user_id)
        rooms.leave_room(client.user_id, room_name)
        await client.send({"type": "left", "room": room_name})


async def handle_chat(client: Client, msg: dict) -> None:
    if not client.room:
        await client.send({"type": "error", "message": "Not in a room"})
        return
    await rooms.broadcast_to_room(client.room, {
        "type": "chat", "user_id": client.user_id, "username": client.username,
        "content": msg.get("content", ""), "timestamp": time.time(),
    })


async def main():
    async with websockets.serve(handle_connection, "0.0.0.0", 8765):
        logger.info("WebSocket server started on ws://0.0.0.0:8765")
        await asyncio.Future()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
'''),
    ("projects/websocket-chat", r'''Implement message history storage and retrieval for the WebSocket chat, with in-memory ring buffer and optional persistence.''', r'''import time
import json
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from collections import deque
from pathlib import Path


@dataclass
class ChatMessage:
    """Represents a single chat message."""
    message_id: str
    room: str
    user_id: str
    username: str
    content: str
    timestamp: float
    edited: bool = False
    deleted: bool = False

    def to_dict(self) -> dict:
        return {
            "message_id": self.message_id,
            "room": self.room,
            "user_id": self.user_id,
            "username": self.username,
            "content": self.content if not self.deleted else "[deleted]",
            "timestamp": self.timestamp,
            "edited": self.edited,
            "deleted": self.deleted,
        }


class MessageHistory:
    """In-memory message history with ring buffer per room."""

    def __init__(self, max_per_room: int = 500, persist_dir: Optional[str] = None):
        self._history: Dict[str, deque] = {}
        self._max_per_room = max_per_room
        self._message_index: Dict[str, ChatMessage] = {}
        self._counter = 0
        self._persist_dir = Path(persist_dir) if persist_dir else None

        if self._persist_dir:
            self._persist_dir.mkdir(parents=True, exist_ok=True)
            self._load_persisted()

    def _generate_id(self) -> str:
        """Generate a unique message ID."""
        self._counter += 1
        return f"msg_{int(time.time() * 1000)}_{self._counter}"

    def add_message(
        self,
        room: str,
        user_id: str,
        username: str,
        content: str,
    ) -> ChatMessage:
        """Add a message to the room history."""
        msg = ChatMessage(
            message_id=self._generate_id(),
            room=room,
            user_id=user_id,
            username=username,
            content=content,
            timestamp=time.time(),
        )

        if room not in self._history:
            self._history[room] = deque(maxlen=self._max_per_room)

        self._history[room].append(msg)
        self._message_index[msg.message_id] = msg

        if self._persist_dir:
            self._persist_message(msg)

        return msg

    def get_history(
        self,
        room: str,
        limit: int = 50,
        before_timestamp: Optional[float] = None,
    ) -> List[dict]:
        """Retrieve message history for a room."""
        messages = self._history.get(room, deque())

        if before_timestamp:
            filtered = [m for m in messages if m.timestamp < before_timestamp]
        else:
            filtered = list(messages)

        # Return most recent messages up to limit
        result = filtered[-limit:]
        return [m.to_dict() for m in result]

    def edit_message(self, message_id: str, user_id: str, new_content: str) -> Optional[dict]:
        """Edit a message. Only the author can edit."""
        msg = self._message_index.get(message_id)
        if not msg or msg.user_id != user_id or msg.deleted:
            return None
        msg.content = new_content
        msg.edited = True
        return msg.to_dict()

    def delete_message(self, message_id: str, user_id: str, is_admin: bool = False) -> bool:
        """Soft-delete a message. Author or admin can delete."""
        msg = self._message_index.get(message_id)
        if not msg:
            return False
        if msg.user_id != user_id and not is_admin:
            return False
        msg.deleted = True
        return True

    def search_messages(self, room: str, query: str, limit: int = 20) -> List[dict]:
        """Search messages in a room by content."""
        messages = self._history.get(room, deque())
        query_lower = query.lower()
        results = []
        for msg in reversed(messages):
            if not msg.deleted and query_lower in msg.content.lower():
                results.append(msg.to_dict())
                if len(results) >= limit:
                    break
        return results

    def get_room_stats(self, room: str) -> dict:
        """Get statistics for a room."""
        messages = self._history.get(room, deque())
        active = [m for m in messages if not m.deleted]
        unique_users = set(m.user_id for m in active)
        return {
            "room": room,
            "total_messages": len(active),
            "unique_users": len(unique_users),
            "oldest_message": active[0].timestamp if active else None,
            "newest_message": active[-1].timestamp if active else None,
        }

    def _persist_message(self, msg: ChatMessage) -> None:
        """Append a message to the room's persistence file."""
        if not self._persist_dir:
            return
        filepath = self._persist_dir / f"{msg.room}.jsonl"
        with open(filepath, "a") as f:
            f.write(json.dumps(msg.to_dict()) + "\n")

    def _load_persisted(self) -> None:
        """Load persisted messages from disk on startup."""
        if not self._persist_dir:
            return
        for filepath in self._persist_dir.glob("*.jsonl"):
            room = filepath.stem
            self._history[room] = deque(maxlen=self._max_per_room)
            with open(filepath, "r") as f:
                for line in f:
                    data = json.loads(line.strip())
                    msg = ChatMessage(**data)
                    self._history[room].append(msg)
                    self._message_index[msg.message_id] = msg
'''),
    ("projects/websocket-chat", r'''Implement typing indicators for the WebSocket chat so users can see when others are typing.''', r'''import asyncio
import time
from typing import Dict, Optional, Set
from dataclasses import dataclass


@dataclass
class TypingState:
    """Tracks the typing state of a user in a room."""
    user_id: str
    username: str
    room: str
    started_at: float
    expires_at: float


class TypingIndicatorManager:
    """Manages typing indicators with automatic expiration.

    Typing indicators automatically expire after a configurable timeout
    to handle cases where the user stops typing without sending a stop event.
    """

    TYPING_TIMEOUT = 5.0  # seconds before typing indicator expires

    def __init__(self):
        self._typing: Dict[str, Dict[str, TypingState]] = {}  # room -> user_id -> state
        self._cleanup_task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the background cleanup task."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop(self) -> None:
        """Stop the background cleanup task."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

    def set_typing(self, user_id: str, username: str, room: str) -> bool:
        """Mark a user as typing. Returns True if this is a new typing event."""
        now = time.time()
        if room not in self._typing:
            self._typing[room] = {}

        is_new = user_id not in self._typing[room]
        self._typing[room][user_id] = TypingState(
            user_id=user_id,
            username=username,
            room=room,
            started_at=now if is_new else self._typing[room].get(user_id, TypingState(user_id, username, room, now, 0)).started_at,
            expires_at=now + self.TYPING_TIMEOUT,
        )
        return is_new

    def clear_typing(self, user_id: str, room: str) -> bool:
        """Clear typing state for a user. Returns True if they were typing."""
        room_typing = self._typing.get(room, {})
        if user_id in room_typing:
            del room_typing[user_id]
            return True
        return False

    def clear_user(self, user_id: str) -> list:
        """Clear all typing states for a user (e.g., on disconnect). Returns affected rooms."""
        affected_rooms = []
        for room_name, room_typing in self._typing.items():
            if user_id in room_typing:
                del room_typing[user_id]
                affected_rooms.append(room_name)
        return affected_rooms

    def get_typing_users(self, room: str) -> list:
        """Get list of currently typing users in a room."""
        now = time.time()
        room_typing = self._typing.get(room, {})
        return [
            {"user_id": state.user_id, "username": state.username}
            for state in room_typing.values()
            if state.expires_at > now
        ]

    async def _cleanup_loop(self) -> None:
        """Periodically clean up expired typing indicators."""
        while True:
            await asyncio.sleep(2.0)
            now = time.time()
            expired_events = []

            for room_name, room_typing in list(self._typing.items()):
                expired = [
                    uid for uid, state in room_typing.items()
                    if state.expires_at <= now
                ]
                for uid in expired:
                    del room_typing[uid]
                    expired_events.append((room_name, uid))

                if not room_typing:
                    del self._typing[room_name]

            # Notify rooms about expired typing indicators
            for room_name, user_id in expired_events:
                await self._on_typing_expired(room_name, user_id)

    async def _on_typing_expired(self, room: str, user_id: str) -> None:
        """Callback when typing indicator expires. Override to broadcast."""
        pass


class TypingBroadcaster(TypingIndicatorManager):
    """Extended typing manager that broadcasts updates via a room manager."""

    def __init__(self, room_manager):
        super().__init__()
        self._room_manager = room_manager

    async def handle_typing_event(self, user_id: str, username: str, room: str, is_typing: bool) -> None:
        """Handle a typing event from a client."""
        if is_typing:
            is_new = self.set_typing(user_id, username, room)
            if is_new:
                await self._broadcast_typing_update(room, user_id)
        else:
            was_typing = self.clear_typing(user_id, room)
            if was_typing:
                await self._broadcast_typing_update(room, user_id)

    async def _broadcast_typing_update(self, room: str, exclude_user: Optional[str] = None) -> None:
        """Broadcast current typing users to the room."""
        typing_users = self.get_typing_users(room)
        await self._room_manager.broadcast_to_room(room, {
            "type": "typing",
            "users": typing_users,
        }, exclude=exclude_user)

    async def _on_typing_expired(self, room: str, user_id: str) -> None:
        """When typing expires, broadcast the updated list."""
        await self._broadcast_typing_update(room)
'''),
    ("projects/websocket-chat", r'''<think>
Reconnection logic is important for WebSocket reliability. I need
to implement exponential backoff on the client side, with state
recovery when the connection is re-established. The server should
support session resumption so clients can pick up where they left off.
</think>
Implement WebSocket reconnection logic with exponential backoff and session resumption support.''', r'''import asyncio
import json
import logging
import random
import time
from typing import Callable, Dict, Optional, Any

logger = logging.getLogger(__name__)


class ReconnectingWebSocket:
    """Client-side WebSocket with automatic reconnection and backoff.

    This class wraps a WebSocket connection and automatically reconnects
    when the connection drops, using exponential backoff with jitter.
    """

    def __init__(
        self,
        url: str,
        on_message: Optional[Callable] = None,
        on_connect: Optional[Callable] = None,
        on_disconnect: Optional[Callable] = None,
        max_retries: int = 10,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ):
        self.url = url
        self.on_message = on_message
        self.on_connect = on_connect
        self.on_disconnect = on_disconnect
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

        self._ws = None
        self._session_id: Optional[str] = None
        self._retry_count = 0
        self._running = False
        self._send_queue: asyncio.Queue = asyncio.Queue()
        self._last_message_id: Optional[str] = None

    def _calculate_backoff(self) -> float:
        """Calculate exponential backoff with jitter."""
        delay = self.base_delay * (2 ** self._retry_count)
        delay = min(delay, self.max_delay)
        # Add random jitter (0.5x to 1.5x)
        jitter = delay * (0.5 + random.random())
        return jitter

    async def connect(self) -> None:
        """Start the connection loop."""
        import websockets
        self._running = True

        while self._running and self._retry_count <= self.max_retries:
            try:
                logger.info(f"Connecting to {self.url}...")
                async with websockets.connect(self.url) as ws:
                    self._ws = ws
                    self._retry_count = 0
                    logger.info("Connected successfully")

                    # Send session resumption if we have a session
                    if self._session_id:
                        await ws.send(json.dumps({
                            "type": "resume",
                            "session_id": self._session_id,
                            "last_message_id": self._last_message_id,
                        }))

                    if self.on_connect:
                        await self.on_connect()

                    # Run send and receive loops concurrently
                    await asyncio.gather(
                        self._receive_loop(ws),
                        self._send_loop(ws),
                    )

            except Exception as e:
                logger.warning(f"Connection lost: {e}")
                self._ws = None

                if self.on_disconnect:
                    await self.on_disconnect()

                if not self._running:
                    break

                self._retry_count += 1
                if self._retry_count > self.max_retries:
                    logger.error("Max retries exceeded. Giving up.")
                    break

                delay = self._calculate_backoff()
                logger.info(
                    f"Reconnecting in {delay:.1f}s "
                    f"(attempt {self._retry_count}/{self.max_retries})"
                )
                await asyncio.sleep(delay)

    async def _receive_loop(self, ws) -> None:
        """Receive messages from the WebSocket."""
        async for raw in ws:
            msg = json.loads(raw)

            # Track session and message IDs for resumption
            if msg.get("type") == "session_created":
                self._session_id = msg["session_id"]
            if "message_id" in msg:
                self._last_message_id = msg["message_id"]

            if self.on_message:
                await self.on_message(msg)

    async def _send_loop(self, ws) -> None:
        """Send queued messages through the WebSocket."""
        while True:
            msg = await self._send_queue.get()
            await ws.send(json.dumps(msg))

    async def send(self, message: dict) -> None:
        """Queue a message for sending."""
        await self._send_queue.put(message)

    async def disconnect(self) -> None:
        """Gracefully disconnect."""
        self._running = False
        if self._ws:
            await self._ws.close()


class SessionManager:
    """Server-side session manager for connection resumption."""

    def __init__(self, session_ttl: float = 300.0):
        self._sessions: Dict[str, dict] = {}
        self._session_ttl = session_ttl

    def create_session(self, user_id: str, room: Optional[str] = None) -> str:
        """Create a new session for a user."""
        import secrets
        session_id = secrets.token_urlsafe(16)
        self._sessions[session_id] = {
            "user_id": user_id,
            "room": room,
            "created_at": time.time(),
            "disconnected_at": None,
            "pending_messages": [],
        }
        return session_id

    def disconnect_session(self, session_id: str) -> None:
        """Mark a session as disconnected but keep it alive for resumption."""
        session = self._sessions.get(session_id)
        if session:
            session["disconnected_at"] = time.time()

    def resume_session(self, session_id: str, last_message_id: Optional[str] = None) -> Optional[dict]:
        """Try to resume an existing session. Returns session data or None."""
        session = self._sessions.get(session_id)
        if not session:
            return None

        if session["disconnected_at"]:
            elapsed = time.time() - session["disconnected_at"]
            if elapsed > self._session_ttl:
                del self._sessions[session_id]
                return None

        session["disconnected_at"] = None
        # Return any missed messages
        pending = session.get("pending_messages", [])
        if last_message_id:
            idx = next((i for i, m in enumerate(pending) if m.get("message_id") == last_message_id), -1)
            pending = pending[idx + 1:]

        result = {
            "user_id": session["user_id"],
            "room": session["room"],
            "missed_messages": pending,
        }
        session["pending_messages"] = []
        return result

    def queue_message(self, session_id: str, message: dict) -> None:
        """Queue a message for a disconnected session."""
        session = self._sessions.get(session_id)
        if session and session["disconnected_at"]:
            session["pending_messages"].append(message)
            # Limit pending messages to prevent memory issues
            if len(session["pending_messages"]) > 100:
                session["pending_messages"] = session["pending_messages"][-100:]

    def cleanup_expired(self) -> int:
        """Remove expired sessions. Returns number removed."""
        now = time.time()
        expired = [
            sid for sid, s in self._sessions.items()
            if s["disconnected_at"] and (now - s["disconnected_at"]) > self._session_ttl
        ]
        for sid in expired:
            del self._sessions[sid]
        return len(expired)
'''),
    ("projects/websocket-chat", r'''Build a WebSocket chat client class for integration into a web frontend, with event handling and message queuing.''', r'''import json
import time
from typing import Any, Callable, Dict, List, Optional
from enum import Enum


class ConnectionState(Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"


class ChatClient:
    """High-level chat client that wraps WebSocket connection management.

    This class provides a clean API for chat operations and manages
    the underlying WebSocket connection, message queuing, and event
    dispatching.
    """

    def __init__(self, server_url: str, user_id: str, username: str):
        self.server_url = server_url
        self.user_id = user_id
        self.username = username
        self.state = ConnectionState.DISCONNECTED
        self.current_room: Optional[str] = None

        self._listeners: Dict[str, List[Callable]] = {}
        self._outgoing_queue: List[dict] = []
        self._ws = None
        self._message_cache: List[dict] = []
        self._max_cache = 200

    def on(self, event: str, callback: Callable) -> Callable:
        """Register an event listener. Returns the callback for chaining."""
        if event not in self._listeners:
            self._listeners[event] = []
        self._listeners[event].append(callback)
        return callback

    def off(self, event: str, callback: Optional[Callable] = None) -> None:
        """Remove an event listener, or all listeners for an event."""
        if callback is None:
            self._listeners.pop(event, None)
        else:
            listeners = self._listeners.get(event, [])
            self._listeners[event] = [cb for cb in listeners if cb != callback]

    def _emit(self, event: str, data: Any = None) -> None:
        """Emit an event to all registered listeners."""
        for callback in self._listeners.get(event, []):
            try:
                callback(data)
            except Exception as e:
                self._emit("error", {"event": event, "error": str(e)})

    def _queue_or_send(self, message: dict) -> None:
        """Send a message or queue it if not connected."""
        if self.state == ConnectionState.CONNECTED and self._ws:
            self._ws.send(json.dumps(message))
        else:
            self._outgoing_queue.append(message)

    def _flush_queue(self) -> None:
        """Send all queued messages."""
        while self._outgoing_queue and self._ws:
            msg = self._outgoing_queue.pop(0)
            self._ws.send(json.dumps(msg))

    def connect(self) -> None:
        """Initiate connection to the chat server."""
        self.state = ConnectionState.CONNECTING
        self._emit("state_change", self.state)

        # In a real implementation, this would use the ReconnectingWebSocket
        # Here we show the protocol flow
        auth_message = {
            "type": "auth",
            "user_id": self.user_id,
            "username": self.username,
        }
        self._queue_or_send(auth_message)

    def disconnect(self) -> None:
        """Gracefully disconnect from the server."""
        if self._ws:
            self._ws.close()
        self.state = ConnectionState.DISCONNECTED
        self.current_room = None
        self._emit("state_change", self.state)

    def join_room(self, room_name: str) -> None:
        """Join a chat room."""
        self._queue_or_send({"type": "join", "room": room_name})

    def leave_room(self) -> None:
        """Leave the current room."""
        if self.current_room:
            self._queue_or_send({"type": "leave", "room": self.current_room})

    def send_message(self, content: str) -> None:
        """Send a chat message to the current room."""
        if not self.current_room:
            self._emit("error", {"message": "Not in a room"})
            return

        msg = {
            "type": "chat",
            "content": content,
            "room": self.current_room,
            "client_timestamp": time.time(),
        }
        self._queue_or_send(msg)

        # Optimistic local update
        local_msg = {
            "user_id": self.user_id,
            "username": self.username,
            "content": content,
            "timestamp": time.time(),
            "pending": True,
        }
        self._message_cache.append(local_msg)
        if len(self._message_cache) > self._max_cache:
            self._message_cache = self._message_cache[-self._max_cache:]
        self._emit("message_sent", local_msg)

    def send_typing(self, is_typing: bool = True) -> None:
        """Send typing indicator."""
        self._queue_or_send({
            "type": "typing",
            "is_typing": is_typing,
            "room": self.current_room,
        })

    def request_history(self, before_timestamp: Optional[float] = None, limit: int = 50) -> None:
        """Request message history from the server."""
        self._queue_or_send({
            "type": "history",
            "room": self.current_room,
            "before": before_timestamp,
            "limit": limit,
        })

    def handle_message(self, raw: str) -> None:
        """Process an incoming WebSocket message."""
        msg = json.loads(raw)
        msg_type = msg.get("type")

        if msg_type == "auth_ok":
            self.state = ConnectionState.CONNECTED
            self._emit("state_change", self.state)
            self._flush_queue()

        elif msg_type == "joined":
            self.current_room = msg.get("room")
            self._emit("room_joined", msg)

        elif msg_type == "left":
            self.current_room = None
            self._emit("room_left", msg)

        elif msg_type == "chat":
            self._message_cache.append(msg)
            if len(self._message_cache) > self._max_cache:
                self._message_cache = self._message_cache[-self._max_cache:]
            self._emit("message", msg)

        elif msg_type == "typing":
            self._emit("typing", msg.get("users", []))

        elif msg_type == "history":
            self._emit("history", msg.get("messages", []))

        elif msg_type == "user_joined":
            self._emit("user_joined", msg)

        elif msg_type == "user_left":
            self._emit("user_left", msg)

        elif msg_type == "error":
            self._emit("error", msg)

    def get_cached_messages(self) -> List[dict]:
        """Return locally cached messages."""
        return list(self._message_cache)
'''),
]
