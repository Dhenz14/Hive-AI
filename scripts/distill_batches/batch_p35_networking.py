"""Network programming — sockets, protocols, async networking in Python."""

PAIRS = [
    (
        "python/socket-programming",
        "Show Python socket programming: TCP/UDP servers, async sockets, protocol implementation, and connection pooling.",
        '''Python network programming patterns:

```python
import asyncio
import struct
import json
from dataclasses import dataclass
from typing import Callable, Awaitable

# --- Async TCP server with framing protocol ---

class MessageProtocol:
    """Length-prefixed message framing (4-byte header + payload)."""

    @staticmethod
    def encode(data: dict) -> bytes:
        payload = json.dumps(data).encode("utf-8")
        header = struct.pack("!I", len(payload))  # Network byte order
        return header + payload

    @staticmethod
    async def read_message(reader: asyncio.StreamReader) -> dict | None:
        header = await reader.readexactly(4)
        if not header:
            return None
        length = struct.unpack("!I", header)[0]
        if length > 10_000_000:  # 10MB limit
            raise ValueError(f"Message too large: {length}")
        payload = await reader.readexactly(length)
        return json.loads(payload.decode("utf-8"))


class AsyncTCPServer:
    def __init__(self, host: str = "0.0.0.0", port: int = 9000):
        self.host = host
        self.port = port
        self.handlers: dict[str, Callable] = {}
        self.clients: dict[str, asyncio.StreamWriter] = {}

    def on(self, message_type: str):
        """Register handler for message type."""
        def decorator(func):
            self.handlers[message_type] = func
            return func
        return decorator

    async def start(self):
        server = await asyncio.start_server(
            self._handle_client, self.host, self.port
        )
        print(f"Server listening on {self.host}:{self.port}")
        async with server:
            await server.serve_forever()

    async def _handle_client(self, reader: asyncio.StreamReader,
                              writer: asyncio.StreamWriter):
        addr = writer.get_extra_info("peername")
        client_id = f"{addr[0]}:{addr[1]}"
        self.clients[client_id] = writer
        print(f"Connected: {client_id}")

        try:
            while True:
                try:
                    message = await asyncio.wait_for(
                        MessageProtocol.read_message(reader),
                        timeout=60.0,  # Idle timeout
                    )
                except asyncio.TimeoutError:
                    await self._send(writer, {
                        "type": "ping", "data": {}
                    })
                    continue
                except asyncio.IncompleteReadError:
                    break

                if message is None:
                    break

                msg_type = message.get("type", "")
                handler = self.handlers.get(msg_type)
                if handler:
                    response = await handler(client_id, message.get("data", {}))
                    if response:
                        await self._send(writer, response)
                else:
                    await self._send(writer, {
                        "type": "error",
                        "data": {"message": f"Unknown type: {msg_type}"},
                    })
        except ConnectionResetError:
            pass
        finally:
            self.clients.pop(client_id, None)
            writer.close()
            await writer.wait_closed()
            print(f"Disconnected: {client_id}")

    async def _send(self, writer: asyncio.StreamWriter, message: dict):
        writer.write(MessageProtocol.encode(message))
        await writer.drain()

    async def broadcast(self, message: dict, exclude: str = None):
        dead = []
        for client_id, writer in self.clients.items():
            if client_id == exclude:
                continue
            try:
                await self._send(writer, message)
            except Exception:
                dead.append(client_id)
        for cid in dead:
            self.clients.pop(cid, None)


# --- Usage ---
server = AsyncTCPServer(port=9000)

@server.on("chat")
async def handle_chat(client_id: str, data: dict):
    await server.broadcast({
        "type": "chat",
        "data": {"from": client_id, "message": data["message"]},
    }, exclude=client_id)
    return {"type": "ack", "data": {"status": "sent"}}

@server.on("ping")
async def handle_ping(client_id: str, data: dict):
    return {"type": "pong", "data": {}}


# --- Async TCP client with reconnection ---

class AsyncTCPClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self.handlers: dict[str, Callable] = {}
        self._connected = asyncio.Event()

    async def connect(self, retries: int = 5):
        for attempt in range(retries):
            try:
                self.reader, self.writer = await asyncio.open_connection(
                    self.host, self.port
                )
                self._connected.set()
                print(f"Connected to {self.host}:{self.port}")
                return
            except ConnectionRefusedError:
                delay = min(2 ** attempt, 30)
                print(f"Connection failed, retrying in {delay}s...")
                await asyncio.sleep(delay)
        raise ConnectionError(f"Failed after {retries} attempts")

    async def send(self, msg_type: str, data: dict):
        await self._connected.wait()
        message = MessageProtocol.encode({"type": msg_type, "data": data})
        self.writer.write(message)
        await self.writer.drain()

    async def listen(self):
        while True:
            try:
                message = await MessageProtocol.read_message(self.reader)
                if message is None:
                    break
                msg_type = message.get("type", "")
                handler = self.handlers.get(msg_type)
                if handler:
                    await handler(message.get("data", {}))
            except Exception as e:
                print(f"Error: {e}")
                break

        self._connected.clear()
        print("Disconnected, reconnecting...")
        await self.connect()
        asyncio.create_task(self.listen())


# --- Connection pool ---

class ConnectionPool:
    def __init__(self, host: str, port: int, size: int = 10):
        self.host = host
        self.port = port
        self.size = size
        self._pool: asyncio.Queue = asyncio.Queue(maxsize=size)
        self._created = 0

    async def _create_connection(self):
        reader, writer = await asyncio.open_connection(self.host, self.port)
        return reader, writer

    async def acquire(self):
        try:
            return self._pool.get_nowait()
        except asyncio.QueueEmpty:
            if self._created < self.size:
                self._created += 1
                return await self._create_connection()
            return await self._pool.get()

    async def release(self, conn):
        reader, writer = conn
        if writer.is_closing():
            self._created -= 1
            return
        try:
            self._pool.put_nowait(conn)
        except asyncio.QueueFull:
            writer.close()
            self._created -= 1

    async def close_all(self):
        while not self._pool.empty():
            reader, writer = self._pool.get_nowait()
            writer.close()
```

Key patterns:
1. **Message framing** — length-prefix protocol prevents message boundary issues
2. **Async server** — `asyncio.start_server` for concurrent client handling
3. **Idle timeout** — detect and clean up stale connections
4. **Reconnection** — exponential backoff on client disconnect
5. **Connection pool** — reuse TCP connections for performance'''
    ),
    (
        "python/http-client-patterns",
        "Show Python HTTP client patterns: connection pooling, retry logic, circuit breaker, and efficient API consumption with httpx.",
        '''Production HTTP client patterns with httpx:

```python
import httpx
import asyncio
from typing import Any, Optional
from dataclasses import dataclass, field
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

# --- Configured HTTP client ---

class APIClient:
    """HTTP client with retry, timeout, and logging."""

    def __init__(self, base_url: str, api_key: str = "",
                 timeout: float = 30, max_retries: int = 3):
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=5.0),
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
                keepalive_expiry=30,
            ),
            headers={
                "User-Agent": "MyApp/1.0",
                "Accept": "application/json",
                **({"Authorization": f"Bearer {api_key}"} if api_key else {}),
            },
            follow_redirects=True,
        )

    async def request(self, method: str, path: str,
                      **kwargs) -> httpx.Response:
        """Make request with retry and logging."""
        last_exception = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = await self.client.request(method, path, **kwargs)

                # Don't retry client errors (4xx)
                if 400 <= response.status_code < 500:
                    response.raise_for_status()

                # Retry server errors (5xx)
                if response.status_code >= 500:
                    logger.warning(
                        "Server error %d on %s %s (attempt %d/%d)",
                        response.status_code, method, path,
                        attempt, self.max_retries,
                    )
                    if attempt < self.max_retries:
                        await asyncio.sleep(2 ** attempt)
                        continue
                    response.raise_for_status()

                return response

            except httpx.TimeoutException as e:
                last_exception = e
                logger.warning(
                    "Timeout on %s %s (attempt %d/%d)",
                    method, path, attempt, self.max_retries,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)
            except httpx.ConnectError as e:
                last_exception = e
                logger.warning(
                    "Connection error on %s %s (attempt %d/%d)",
                    method, path, attempt, self.max_retries,
                )
                if attempt < self.max_retries:
                    await asyncio.sleep(2 ** attempt)

        raise last_exception or httpx.HTTPError("Max retries exceeded")

    async def get(self, path: str, **kwargs) -> Any:
        response = await self.request("GET", path, **kwargs)
        return response.json()

    async def post(self, path: str, data: dict = None, **kwargs) -> Any:
        response = await self.request("POST", path, json=data, **kwargs)
        return response.json()

    async def close(self):
        await self.client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


# --- Concurrent API fetching ---

async def fetch_all_pages(client: APIClient, endpoint: str,
                           max_concurrent: int = 5) -> list:
    """Fetch all pages of a paginated API concurrently."""
    # Get first page to determine total
    first_page = await client.get(endpoint, params={"page": 1, "size": 100})
    total_pages = first_page["pages"]
    all_items = first_page["items"]

    if total_pages <= 1:
        return all_items

    # Fetch remaining pages concurrently
    semaphore = asyncio.Semaphore(max_concurrent)

    async def fetch_page(page: int):
        async with semaphore:
            result = await client.get(
                endpoint, params={"page": page, "size": 100}
            )
            return result["items"]

    tasks = [fetch_page(p) for p in range(2, total_pages + 1)]
    pages = await asyncio.gather(*tasks)

    for page_items in pages:
        all_items.extend(page_items)

    return all_items


# --- Webhook sender with retry ---

@dataclass
class WebhookDelivery:
    url: str
    payload: dict
    attempt: int = 0
    max_attempts: int = 5
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

async def deliver_webhook(delivery: WebhookDelivery) -> bool:
    """Deliver webhook with exponential backoff."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        while delivery.attempt < delivery.max_attempts:
            delivery.attempt += 1
            try:
                response = await client.post(
                    delivery.url,
                    json=delivery.payload,
                    headers={"Content-Type": "application/json"},
                )
                if response.status_code < 400:
                    return True
                if response.status_code < 500:
                    return False  # Client error, don't retry
            except (httpx.TimeoutException, httpx.ConnectError):
                pass

            if delivery.attempt < delivery.max_attempts:
                delay = min(60, 2 ** delivery.attempt)
                await asyncio.sleep(delay)

    return False
```

Patterns:
1. **Connection pooling** — `httpx.Limits` reuses connections
2. **Retry logic** — exponential backoff for 5xx and timeouts only
3. **Concurrent fetching** — semaphore-limited parallel page fetching
4. **Proper timeouts** — separate connect vs read timeouts
5. **Resource management** — async context manager for cleanup'''
    ),
]
