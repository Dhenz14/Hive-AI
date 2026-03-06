PAIRS = [
    ("thinking/debugging", r'''My WebSocket client doesn't detect when the server goes down. The connection appears open but messages are not being received:

```python
import websockets
import asyncio

async def listen():
    async with websockets.connect('ws://server:8765') as ws:
        while True:
            message = await ws.recv()  # blocks forever when server dies
            process(message)

asyncio.run(listen())
```

When the server crashes, `ws.recv()` just hangs indefinitely. No exception is raised. The client thinks it's still connected.''', r'''<think>
When a server crashes (process killed, power failure), it does not send a TCP FIN or WebSocket close frame. The client's TCP connection remains in the ESTABLISHED state because there is no notification that the server is gone. This is the "half-open connection" problem.

The recv() call blocks waiting for data that will never come. Eventually, TCP will time out (which can take minutes to hours depending on OS settings), but the default timeout is very long.

The fix: use ping/pong to detect dead connections, and set a timeout on recv().
</think>

When a server crashes (process kill, power failure, network partition), it does not send a TCP FIN or WebSocket close frame. The client's TCP stack has no way to know the server is gone. The connection appears ESTABLISHED and `recv()` blocks indefinitely waiting for data that will never arrive.

This is the "half-open connection" problem. TCP only detects dead connections when you try to send data (which eventually times out) or when TCP keep-alive probes go unanswered.

**Fix 1: Enable WebSocket ping/pong (built into websockets library)**

```python
import websockets
import asyncio

async def listen():
    async with websockets.connect(
        'ws://server:8765',
        ping_interval=20,    # send ping every 20 seconds
        ping_timeout=10,     # wait 10 seconds for pong
        close_timeout=5,     # timeout for close handshake
    ) as ws:
        try:
            async for message in ws:
                process(message)
        except websockets.ConnectionClosed as e:
            print(f"Connection closed: code={e.code}, reason={e.reason}")
```

With `ping_interval=20` and `ping_timeout=10`, the library sends a WebSocket ping frame every 20 seconds. If no pong is received within 10 seconds, the connection is considered dead and `ConnectionClosed` is raised.

**Fix 2: Add a receive timeout**

```python
async def listen():
    async with websockets.connect('ws://server:8765') as ws:
        while True:
            try:
                message = await asyncio.wait_for(ws.recv(), timeout=30)
                process(message)
            except asyncio.TimeoutError:
                # No message received in 30 seconds
                try:
                    pong = await ws.ping()
                    await asyncio.wait_for(pong, timeout=5)
                    print("Connection alive, just no messages")
                except (asyncio.TimeoutError, websockets.ConnectionClosed):
                    print("Server is dead, reconnecting...")
                    break
```

**Fix 3: Implement automatic reconnection**

```python
import websockets
import asyncio
import random

async def listen_with_reconnect():
    reconnect_delay = 1  # start with 1 second

    while True:
        try:
            async with websockets.connect(
                'ws://server:8765',
                ping_interval=20,
                ping_timeout=10,
            ) as ws:
                reconnect_delay = 1  # reset on successful connection
                print("Connected!")
                async for message in ws:
                    process(message)

        except (websockets.ConnectionClosed, ConnectionError, OSError) as e:
            print(f"Disconnected: {e}. Reconnecting in {reconnect_delay}s...")
            await asyncio.sleep(reconnect_delay)
            # Exponential backoff with jitter
            reconnect_delay = min(reconnect_delay * 2, 60)
            reconnect_delay += random.uniform(0, 1)

        except Exception as e:
            print(f"Unexpected error: {e}")
            await asyncio.sleep(5)
```

**Fix 4: Enable TCP keep-alive at the socket level**

```python
import socket

async def listen():
    async with websockets.connect(
        'ws://server:8765',
        ping_interval=20,
        ping_timeout=10,
    ) as ws:
        # Enable TCP keep-alive on the underlying socket
        sock = ws.transport.get_extra_info('socket')
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 30)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 10)
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 3)

        async for message in ws:
            process(message)
```

TCP keep-alive sends probes at the TCP level. After 3 failed probes (30s + 3*10s = 60s total), the OS marks the connection as dead.

**Prevention tips:**
- Always enable ping/pong or TCP keep-alive on WebSocket connections
- Implement automatic reconnection with exponential backoff
- Set timeouts on recv() to detect dead connections within acceptable time
- Log reconnection events for monitoring
- Use a circuit breaker pattern if the server is consistently unreachable
- Test failure scenarios: kill the server process and verify the client recovers'''),

    ("thinking/debugging", r'''My WebSocket messages arrive out of order. I send messages 1, 2, 3 but sometimes receive 2, 1, 3:

```javascript
// Client sends:
ws.send(JSON.stringify({ id: 1, type: 'update' }));
ws.send(JSON.stringify({ id: 2, type: 'update' }));
ws.send(JSON.stringify({ id: 3, type: 'update' }));

// Server receives:
// { id: 2, type: 'update' }  -- out of order!
// { id: 1, type: 'update' }
// { id: 3, type: 'update' }
```

WebSocket runs over TCP which guarantees ordering. So why are messages out of order?''', r'''<think>
TCP guarantees byte-level ordering within a single connection. If messages arrive out of order, there must be something between the client and server that is reordering them, or there are multiple connections/paths involved.

Possible causes:
1. Multiple WebSocket connections (e.g., reconnection creates a new connection)
2. A load balancer distributing messages across multiple server instances
3. Server-side async processing handling messages in parallel
4. The client uses multiple WebSocket connections (e.g., multiple tabs)
5. A proxy or CDN that processes messages in parallel

TCP guarantees ordering, but the APPLICATION layer might process messages out of order if using async/parallel processing.
</think>

TCP guarantees byte-level ordering within a single connection. If messages arrive out of order, the issue is not TCP but rather something at the application level or infrastructure.

**Common causes of out-of-order WebSocket messages:**

**Cause 1: Multiple WebSocket connections**

If the client reconnects, messages sent on the old connection might arrive after messages on the new connection:

```javascript
// Old connection sends message 1
// Connection drops
// New connection sends message 2
// Message 2 arrives first on new connection
// Message 1 may never arrive (old connection is dead)
```

**Cause 2: Load balancer distributing across server instances**

```
Client -> Load Balancer -> Server A (gets message 1)
                        -> Server B (gets message 2)
                        -> Server A (gets message 3)
```

If the load balancer does not use sticky sessions for WebSocket, messages may go to different servers.

**Cause 3: Server-side async processing**

```python
# Server processes messages concurrently
async def handler(websocket):
    async for message in websocket:
        asyncio.create_task(process_message(message))
        # process_message runs concurrently -- no ordering guarantee!
```

Even though messages arrive in order, if each is processed in a separate task, their side effects (database writes, state changes) may complete in any order.

**Fix 1: Add sequence numbers and client-side ordering**

```javascript
// Client:
let sequence = 0;
function sendOrdered(ws, data) {
    data._seq = ++sequence;
    ws.send(JSON.stringify(data));
}

// Server:
const expectedSeq = {};

function processOrdered(clientId, message) {
    if (!expectedSeq[clientId]) expectedSeq[clientId] = 1;

    if (message._seq === expectedSeq[clientId]) {
        // In order -- process immediately
        handle(message);
        expectedSeq[clientId]++;

        // Process any buffered messages
        while (messageBuffer[clientId]?.[expectedSeq[clientId]]) {
            handle(messageBuffer[clientId][expectedSeq[clientId]]);
            delete messageBuffer[clientId][expectedSeq[clientId]];
            expectedSeq[clientId]++;
        }
    } else if (message._seq > expectedSeq[clientId]) {
        // Out of order -- buffer it
        if (!messageBuffer[clientId]) messageBuffer[clientId] = {};
        messageBuffer[clientId][message._seq] = message;
    }
    // Ignore if _seq < expected (duplicate)
}
```

**Fix 2: Process messages sequentially on the server**

```python
# Instead of spawning a task per message:
async def handler(websocket):
    async for message in websocket:
        await process_message(message)  # await, not create_task
```

This ensures each message is fully processed before the next one starts.

**Fix 3: Use an ordered message queue**

```python
import asyncio

async def handler(websocket):
    queue = asyncio.Queue()

    # Producer: receives messages and enqueues them
    async def receiver():
        async for message in websocket:
            await queue.put(message)

    # Consumer: processes messages in order
    async def processor():
        while True:
            message = await queue.get()
            await process_message(message)  # strictly ordered
            queue.task_done()

    await asyncio.gather(receiver(), processor())
```

**Fix 4: Use sticky sessions on the load balancer**

```nginx
upstream websocket_servers {
    ip_hash;  # sticky sessions based on client IP
    server server1:8765;
    server server2:8765;
}
```

This ensures all messages from a client go to the same server instance.

**Prevention tips:**
- Always process WebSocket messages sequentially unless ordering does not matter
- Use sequence numbers for messages that must be ordered
- Configure load balancers for sticky sessions (IP hash or cookie-based)
- Implement idempotent message handlers to safely handle duplicates
- Log message sequence numbers to detect ordering issues in production
- Use a single WebSocket connection per client session'''),

    ("thinking/debugging", r'''My WebSocket server crashes when receiving a large binary file:

```python
import websockets
import asyncio

async def handler(websocket, path):
    async for message in websocket:
        if isinstance(message, bytes):
            await save_file(message)
            await websocket.send('File received')

start_server = websockets.serve(handler, '0.0.0.0', 8765)
```

When a client sends a 50MB file, the server crashes:
```
websockets.exceptions.PayloadTooBig: frame exceeds limit: 52428800 > 1048576 bytes
```

The default message size limit is 1MB. But even after increasing it, large files cause memory issues.''', r'''<think>
The websockets library has a default max_size of 1MB (1048576 bytes) to prevent denial-of-service attacks. The user needs to increase this limit. But beyond just increasing the limit, large binary transfers over WebSocket need special handling to avoid memory issues.

The better approach for large files is to use chunked transfer or streaming.
</think>

The `websockets` library enforces a default maximum message size of 1MB (1,048,576 bytes) to prevent memory exhaustion attacks. A 50MB file exceeds this limit.

**Fix 1: Increase the message size limit**

```python
start_server = websockets.serve(
    handler,
    '0.0.0.0', 8765,
    max_size=100 * 1024 * 1024,  # 100MB limit
)
```

However, this loads the entire message into memory before your handler sees it. For 50MB+ files, this wastes memory and blocks the event loop during read.

**Fix 2: Use chunked transfer (recommended for large files)**

```python
# Server: receive file in chunks
async def handler(websocket, path):
    # Protocol: first message is metadata, then chunks, then 'END'
    metadata = json.loads(await websocket.recv())
    filename = metadata['filename']
    total_size = metadata['size']

    received = 0
    with open(f'/uploads/{filename}', 'wb') as f:
        async for chunk in websocket:
            if chunk == b'END':
                break
            f.write(chunk)
            received += len(chunk)

            # Send progress
            progress = (received / total_size) * 100
            await websocket.send(json.dumps({'progress': progress}))

    await websocket.send(json.dumps({'status': 'complete'}))
```

```javascript
// Client: send file in chunks
async function uploadFile(ws, file) {
    const CHUNK_SIZE = 64 * 1024;  // 64KB chunks

    // Send metadata
    ws.send(JSON.stringify({
        filename: file.name,
        size: file.size,
    }));

    // Send file in chunks
    let offset = 0;
    while (offset < file.size) {
        const chunk = file.slice(offset, offset + CHUNK_SIZE);
        const buffer = await chunk.arrayBuffer();
        ws.send(buffer);
        offset += CHUNK_SIZE;

        // Wait for progress confirmation (optional flow control)
        // const response = await waitForMessage(ws);
    }

    // Signal end of file
    ws.send(new TextEncoder().encode('END'));
}
```

**Fix 3: Use HTTP upload instead of WebSocket for large files**

WebSocket is designed for bidirectional messaging, not bulk file transfer. HTTP is better suited:

```python
# Use aiohttp for async file upload handling
from aiohttp import web

async def upload_handler(request):
    reader = await request.multipart()
    field = await reader.next()

    with open(f'/uploads/{field.filename}', 'wb') as f:
        while True:
            chunk = await field.read_chunk(8192)
            if not chunk:
                break
            f.write(chunk)

    return web.json_response({'status': 'uploaded'})

# Client sends progress via WebSocket, file via HTTP
```

**Fix 4: Implement flow control to prevent memory buildup**

```python
async def handler(websocket, path):
    while True:
        try:
            message = await asyncio.wait_for(websocket.recv(), timeout=30)

            if isinstance(message, bytes) and len(message) > 10 * 1024 * 1024:
                # Reject messages larger than 10MB
                await websocket.send(json.dumps({
                    'error': 'Message too large',
                    'max_size': '10MB',
                }))
                continue

            await process(message)

        except asyncio.TimeoutError:
            continue
        except websockets.ConnectionClosed:
            break
```

**Security considerations:**

```python
# Always validate and limit file uploads
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB
ALLOWED_EXTENSIONS = {'.jpg', '.png', '.pdf', '.csv'}

async def validate_upload(metadata):
    if metadata['size'] > MAX_FILE_SIZE:
        raise ValueError(f"File too large: {metadata['size']} bytes")

    ext = os.path.splitext(metadata['filename'])[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File type not allowed: {ext}")

    # Sanitize filename to prevent path traversal
    filename = os.path.basename(metadata['filename'])
    filename = re.sub(r'[^\w.-]', '_', filename)
    return filename
```

**Prevention tips:**
- Use chunked transfer for files larger than 1MB
- Prefer HTTP upload for large file transfers
- Set reasonable max_size limits to prevent memory exhaustion
- Implement flow control (backpressure) for high-throughput scenarios
- Validate file size, type, and name before processing
- Write chunks to disk immediately, do not accumulate in memory
- Monitor memory usage on WebSocket server instances'''),

    ("thinking/debugging", r'''WebSocket heartbeat is not working through our reverse proxy:

```python
# Server
async def handler(websocket, path):
    while True:
        try:
            message = await asyncio.wait_for(websocket.recv(), timeout=60)
            await process(message)
        except asyncio.TimeoutError:
            # Send application-level heartbeat
            await websocket.send(json.dumps({'type': 'heartbeat'}))
```

The heartbeat sends fine from the server but the client never receives it. Nginx access logs show the WebSocket upgrade succeeds but heartbeat messages are missing.

Nginx config:
```nginx
location /ws {
    proxy_pass http://backend:8765;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
}
```''', r'''<think>
The Nginx config looks correct for WebSocket. The issue might be:
1. proxy_read_timeout is too low and Nginx closes the connection before the heartbeat
2. proxy_buffering is interfering with WebSocket frames
3. The heartbeat is sent but Nginx buffers it

Wait, the user says the heartbeat sends fine but the client doesn't receive it. If Nginx is buffering the response, small messages might be held in the buffer. But WebSocket frames should be forwarded immediately.

Actually, the most likely issue is still proxy_read_timeout. The default is 60s. If the client sends no data for 60s, Nginx closes the upstream connection. The server's heartbeat at 60s might arrive just after Nginx has already timed out.

Or the issue could be proxy_send_timeout on the client->Nginx direction.

Let me also consider: maybe the heartbeat IS being received but the client code has a bug in handling it.
</think>

The most likely issue is Nginx's `proxy_read_timeout` (default 60 seconds). When no data flows from the backend to Nginx for 60 seconds, Nginx closes the upstream connection. Your heartbeat timeout is also 60 seconds, so the heartbeat may arrive just after Nginx has already timed out.

Additionally, `proxy_buffering` may delay small WebSocket frames.

**Fix: Configure Nginx timeouts for WebSocket**

```nginx
location /ws {
    proxy_pass http://backend:8765;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;

    # Critical: increase timeouts for WebSocket
    proxy_read_timeout 3600s;    # 1 hour
    proxy_send_timeout 3600s;    # 1 hour

    # Disable buffering for WebSocket
    proxy_buffering off;

    # Forward WebSocket frames immediately
    proxy_cache off;

    # TCP keep-alive for the upstream connection
    proxy_socket_keepalive on;
}
```

**Key settings explained:**

- `proxy_read_timeout 3600s`: How long Nginx waits for data from the backend. Must be longer than your heartbeat interval.
- `proxy_send_timeout 3600s`: How long Nginx waits when sending data to the backend.
- `proxy_buffering off`: Prevents Nginx from buffering WebSocket frames. Without this, small messages might be held until the buffer is full.

**Fix the heartbeat interval to be shorter than proxy_read_timeout:**

```python
# Server: send heartbeat every 30 seconds (well under Nginx's 3600s timeout)
async def handler(websocket, path):
    async def heartbeat():
        while True:
            await asyncio.sleep(30)
            try:
                await websocket.send(json.dumps({'type': 'heartbeat'}))
            except websockets.ConnectionClosed:
                break

    heartbeat_task = asyncio.create_task(heartbeat())
    try:
        async for message in websocket:
            if message != 'pong':  # ignore heartbeat responses
                await process(message)
    finally:
        heartbeat_task.cancel()
```

**Client-side heartbeat handling:**

```javascript
const ws = new WebSocket('wss://example.com/ws');

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === 'heartbeat') {
        // Respond to server heartbeat
        ws.send('pong');
        return;
    }
    processMessage(data);
};

// Client-side timeout detection
let lastMessage = Date.now();
setInterval(() => {
    if (Date.now() - lastMessage > 45000) {  // 45 seconds
        console.warn('No heartbeat received, connection may be dead');
        ws.close();
        // Trigger reconnection logic
    }
}, 10000);

ws.onmessage = (event) => {
    lastMessage = Date.now();  // reset timer on any message
    // ... rest of handler
};
```

**Debugging WebSocket through Nginx:**

```bash
# Check if WebSocket upgrade is working
curl -v -H "Upgrade: websocket" -H "Connection: upgrade" \
     -H "Sec-WebSocket-Version: 13" -H "Sec-WebSocket-Key: test" \
     http://localhost/ws

# Check Nginx error log for timeout messages
tail -f /var/log/nginx/error.log
# Look for: "upstream timed out"

# Use wscat to test directly vs through proxy
wscat -c ws://backend:8765    # direct
wscat -c ws://localhost/ws     # through Nginx
```

**Prevention tips:**
- Set proxy_read_timeout to at least 2x your heartbeat interval
- Always disable proxy_buffering for WebSocket locations
- Send heartbeats from the server, not just ping/pong frames
- Monitor WebSocket connection duration and drop rates
- Test WebSocket through all proxies in your infrastructure
- Document the full network path and timeout at each hop'''),

    ("thinking/debugging", r'''My WebSocket reconnection creates an exponentially growing number of event listeners:

```javascript
let ws;

function connect() {
    ws = new WebSocket('wss://api.example.com/ws');

    ws.onopen = () => {
        console.log('Connected');
        document.getElementById('sendBtn').addEventListener('click', () => {
            ws.send('hello');
        });
    };

    ws.onclose = () => {
        console.log('Disconnected, reconnecting...');
        setTimeout(connect, 1000);
    };
}

connect();
```

After 5 reconnections, clicking the button sends "hello" 6 times. After 10 reconnections, it sends 11 times. Memory usage keeps climbing.''', r'''<think>
Every time `connect()` is called, a new `addEventListener('click', ...)` is added to the button. Event listeners are not removed when the WebSocket closes. After N reconnections, there are N+1 click listeners on the button, each capturing a different `ws` reference (though only the latest one works -- older ones reference closed WebSocket objects).

The fix: add the event listener only once, or remove it before adding a new one.
</think>

Every time `connect()` is called (including on reconnection), a new click event listener is added to the button. Event listeners accumulate because they are never removed. After 10 reconnections, the button has 11 click listeners.

Additionally, each listener captures the `ws` variable from its closure. Older listeners reference closed WebSocket objects, causing errors or wasted resources.

**Fix 1: Add the event listener only once, outside the connect function**

```javascript
let ws;

function connect() {
    ws = new WebSocket('wss://api.example.com/ws');

    ws.onopen = () => {
        console.log('Connected');
    };

    ws.onclose = () => {
        console.log('Disconnected, reconnecting...');
        setTimeout(connect, 1000);
    };

    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

// Add listener ONCE, outside connect()
document.getElementById('sendBtn').addEventListener('click', () => {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send('hello');
    } else {
        console.warn('WebSocket not connected');
    }
});

connect();
```

The click handler always uses the current value of `ws` (a module-level variable), so it automatically uses the latest connection after reconnection.

**Fix 2: Use AbortController to remove old listeners**

```javascript
let ws;
let abortController;

function connect() {
    // Abort previous listeners
    if (abortController) {
        abortController.abort();
    }
    abortController = new AbortController();

    ws = new WebSocket('wss://api.example.com/ws');

    ws.onopen = () => {
        console.log('Connected');
        document.getElementById('sendBtn').addEventListener('click', () => {
            ws.send('hello');
        }, { signal: abortController.signal });
        // This listener is automatically removed when abortController.abort() is called
    };

    ws.onclose = () => {
        setTimeout(connect, 1000);
    };
}
```

The `{ signal: abortController.signal }` option automatically removes the listener when the AbortController is aborted.

**Fix 3: Use a named function and removeEventListener**

```javascript
let ws;
let currentClickHandler = null;

function connect() {
    ws = new WebSocket('wss://api.example.com/ws');

    ws.onopen = () => {
        const btn = document.getElementById('sendBtn');

        // Remove old handler
        if (currentClickHandler) {
            btn.removeEventListener('click', currentClickHandler);
        }

        // Add new handler
        currentClickHandler = () => {
            ws.send('hello');
        };
        btn.addEventListener('click', currentClickHandler);
    };

    ws.onclose = () => {
        setTimeout(connect, 1000);
    };
}
```

**Fix 4: Use a WebSocket wrapper class**

```javascript
class WebSocketManager {
    constructor(url) {
        this.url = url;
        this.ws = null;
        this.listeners = new Map();
        this.reconnectDelay = 1000;
    }

    connect() {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
            this.reconnectDelay = 1000;
            console.log('Connected');
        };

        this.ws.onclose = () => {
            setTimeout(() => this.connect(), this.reconnectDelay);
            this.reconnectDelay = Math.min(this.reconnectDelay * 2, 30000);
        };
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(data);
            return true;
        }
        return false;
    }

    onMessage(callback) {
        // Only one onmessage handler, no listener leak
        this.messageHandler = callback;
        if (this.ws) {
            this.ws.onmessage = (event) => this.messageHandler(event);
        }
    }
}

const wsManager = new WebSocketManager('wss://api.example.com/ws');
wsManager.connect();

// Single event listener, no leaks
document.getElementById('sendBtn').addEventListener('click', () => {
    wsManager.send('hello');
});
```

**Prevention tips:**
- Never add event listeners inside functions that are called repeatedly
- Use AbortController for automatic listener cleanup
- Check for existing listeners before adding new ones
- Use a wrapper class or library to manage WebSocket lifecycle
- Monitor memory usage in browser DevTools to detect listener leaks
- Use Chrome DevTools "Performance" tab to count event listeners over time'''),
]
