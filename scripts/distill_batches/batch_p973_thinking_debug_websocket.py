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
The client thinks it is still connected but the server is dead. Could this be a bug in the websockets library? Hmm, let me think about what happens at the TCP level when a server crashes.

When a server crashes (process killed, power failure), it does NOT send a TCP FIN or WebSocket close frame. The client's TCP stack has no way to know the server is gone because no packet was sent to indicate disconnection. So the connection remains in the ESTABLISHED state -- this is the "half-open connection" problem.

Wait, but shouldn't TCP eventually detect this? Actually, TCP does have a keep-alive mechanism, but the default keep-alive timeout on most operating systems is 2 hours. So the recv() call would block for up to 2 hours before TCP notices the connection is dead. That explains why it "hangs indefinitely" from the user's perspective.

I initially considered just setting a timeout on recv() as the fix, but that alone is not enough -- it would just raise TimeoutError even during normal idle periods when the server has no data to send. Therefore the proper fix is a combination: use WebSocket-level ping/pong to actively probe the connection (the websockets library has built-in support for this), AND add a recv timeout as a fallback. The ping/pong approach is better because it actively verifies the connection is alive rather than just detecting silence.
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
WebSocket runs over TCP, which guarantees byte-level ordering. So how can messages arrive out of order? Could TCP itself be broken? No, that is extremely unlikely -- TCP ordering is fundamental and battle-tested.

Wait, the issue must be at the application layer, not the transport layer. Let me think about what could cause this. Multiple possibilities:

1. Multiple WebSocket connections -- if the client reconnects, messages sent on different connections have no ordering guarantee relative to each other
2. A load balancer distributing messages across multiple server instances -- message 1 goes to server A, message 2 goes to server B
3. Server-side async processing -- hmm, this is interesting. Even if messages arrive in order on a single connection, if each message is processed in a separate async task (create_task), their side effects complete in arbitrary order

Actually, I think cause 3 is the most common one in practice. The server receives messages 1, 2, 3 in order on the TCP stream, but spawns concurrent tasks to process them. Task for message 2 finishes before task for message 1, so the database sees updates in the order 2, 1, 3. The user blames the network, but the real issue is application-level concurrency.

Therefore the fix depends on the cause: for load balancers, use sticky sessions; for async processing, process messages sequentially or add sequence numbers with client-side reordering.
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
The server crashes with "frame exceeds limit: 52428800 > 1048576 bytes." The websockets library has a default max_size of 1MB (1048576 bytes), and the 50MB file exceeds this. Could I just increase the limit? That would work technically, but wait -- even with an increased limit, loading a 50MB message into memory all at once is problematic.

Hmm, why? Because the websockets library buffers the entire message in memory before calling the handler. Under concurrent uploads from multiple clients, this means 50MB * N connections of memory usage, which can easily exhaust server RAM. And the event loop is blocked during the read, affecting all other connections.

I initially thought just setting `max_size=100MB` would be sufficient, but actually the better approach for large files is chunked transfer. By breaking the file into small chunks (say 64KB each), you keep memory usage constant regardless of file size, and you can implement progress tracking. Even better, WebSocket is not really designed for bulk file transfers -- HTTP multipart upload handles this more efficiently with built-in flow control. Therefore I should present both the quick fix (increase max_size) and the proper fix (chunked transfer or HTTP upload).
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
The Nginx config looks correct for WebSocket upgrade. The heartbeat sends fine from the server but the client never receives it. Could there be a bug in the client-side code? Hmm, the user says the heartbeat messages are "missing" entirely, not that they are being received and ignored. So the issue is likely between the server and client -- meaning Nginx.

Let me think about what Nginx could be doing wrong. The config has the proper Upgrade and Connection headers, so the WebSocket handshake works. But wait -- what about proxy_read_timeout? The default is 60 seconds. The server's heartbeat logic sends a heartbeat after 60 seconds of no data... that is exactly the default timeout. So Nginx might close the upstream connection at the 60-second mark, just before or at the same time the heartbeat is sent.

I initially considered proxy_buffering as the culprit -- maybe Nginx is buffering the small heartbeat message. But actually, WebSocket frames should bypass normal HTTP buffering since the connection has been upgraded. However, the proxy_buffering directive might still interfere in some edge cases, so it is best to disable it explicitly for WebSocket locations.

Actually, the most likely scenario is the proxy_read_timeout race condition. The fix needs to either increase proxy_read_timeout significantly (like 3600s) or decrease the heartbeat interval to well under 60 seconds. Therefore I should recommend both: a much longer Nginx timeout AND a shorter heartbeat interval (like 30 seconds) to ensure heartbeats arrive well before any timeout fires.
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
After 5 reconnections, clicking the button sends "hello" 6 times. Could this be a WebSocket protocol issue where messages are duplicated? Hmm no, the pattern of N+1 messages after N reconnections is too precise for a network issue. This looks like an event listener leak.

Let me trace through the code. Every time `connect()` is called (initial + each reconnection), it sets up ws.onopen which adds a NEW addEventListener('click', ...) to the button. Event listeners are cumulative -- calling addEventListener again does NOT replace the old one. After N reconnections, there are N+1 click listeners on the button.

Wait, but do the old listeners even work? Each listener captures `ws` from its closure... actually, `ws` is a module-level variable that gets reassigned on each connect. So all listeners reference the SAME `ws` variable, which always points to the latest connection. That means all N+1 listeners send "hello" on the current connection, resulting in N+1 sends per click. And the old closed WebSocket objects are only referenced transiently during reassignment.

I initially thought about using removeEventListener before adding a new one, but that requires a named function reference. A simpler fix is to just move the addEventListener call outside the connect() function entirely, so it is called only once. Since all listeners share the same `ws` variable anyway, a single listener that reads the current `ws` value works perfectly.
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
