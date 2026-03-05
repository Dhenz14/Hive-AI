"""Browser internals — rendering pipeline, event loop, Web APIs, performance optimization."""

PAIRS = [
    (
        "web/browser-rendering-pipeline",
        "Explain the browser rendering pipeline from HTML parsing to pixels on screen. Cover DOM construction, CSSOM, layout, paint, and compositing.",
        '''The browser rendering pipeline transforms HTML/CSS/JS into pixels:

```
HTML bytes → Characters → Tokens → Nodes → DOM tree
CSS bytes  → Characters → Tokens → Nodes → CSSOM tree

DOM + CSSOM → Render Tree → Layout → Paint → Composite → Display

Detailed pipeline:
1. Parse HTML → DOM (Document Object Model)
2. Parse CSS → CSSOM (CSS Object Model)
3. Execute JavaScript (can modify DOM/CSSOM)
4. Build Render Tree (visible elements + computed styles)
5. Layout (calculate geometry: position, size)
6. Paint (draw pixels: text, colors, images, borders)
7. Composite (layer management, GPU composition)
```

```javascript
// --- Performance-aware DOM manipulation ---

// BAD: Forces layout thrashing (read-write-read-write)
function badLayout() {
    const elements = document.querySelectorAll('.item');
    elements.forEach(el => {
        const height = el.offsetHeight;  // READ (forces layout)
        el.style.height = (height * 2) + 'px';  // WRITE (invalidates layout)
        // Next iteration's read forces re-layout!
    });
}

// GOOD: Batch reads then batch writes
function goodLayout() {
    const elements = document.querySelectorAll('.item');
    // Phase 1: Read all
    const heights = Array.from(elements).map(el => el.offsetHeight);
    // Phase 2: Write all
    elements.forEach((el, i) => {
        el.style.height = (heights[i] * 2) + 'px';
    });
}

// BEST: Use requestAnimationFrame for visual updates
function bestLayout() {
    const elements = document.querySelectorAll('.item');
    const heights = Array.from(elements).map(el => el.offsetHeight);

    requestAnimationFrame(() => {
        elements.forEach((el, i) => {
            el.style.height = (heights[i] * 2) + 'px';
        });
    });
}

// --- Layout triggers (properties that force synchronous layout) ---
const LAYOUT_TRIGGERS = [
    'offsetTop', 'offsetLeft', 'offsetWidth', 'offsetHeight',
    'scrollTop', 'scrollLeft', 'scrollWidth', 'scrollHeight',
    'clientTop', 'clientLeft', 'clientWidth', 'clientHeight',
    'getComputedStyle()', 'getBoundingClientRect()',
];

// --- Composite-only animations (no layout/paint) ---

// SLOW: Triggers layout every frame
function slowAnimation(el) {
    el.style.left = (parseInt(el.style.left) + 1) + 'px';
    el.style.top = (parseInt(el.style.top) + 1) + 'px';
}

// FAST: Only triggers composite (GPU-accelerated)
function fastAnimation(el) {
    el.style.transform = 'translate(100px, 100px)';
    el.style.opacity = 0.5;
}

// CSS properties by rendering cost:
// Composite only (cheapest): transform, opacity
// Paint + Composite: color, background, box-shadow, border-radius
// Layout + Paint + Composite (expensive): width, height, margin, padding,
//                                          top, left, font-size, display

// --- will-change hint for compositing ---
// .animated-element {
//     will-change: transform, opacity;  /* Promote to own layer */
// }

// --- Intersection Observer (efficient scroll-based triggers) ---

const observer = new IntersectionObserver(
    (entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                entry.target.classList.add('visible');
                // Lazy load images
                if (entry.target.dataset.src) {
                    entry.target.src = entry.target.dataset.src;
                    observer.unobserve(entry.target);
                }
            }
        });
    },
    {
        root: null,          // Viewport
        rootMargin: '100px', // Start loading 100px before visible
        threshold: 0.1,      // 10% visible triggers callback
    }
);

document.querySelectorAll('.lazy-image').forEach(img => observer.observe(img));

// --- Resize Observer (efficient element size monitoring) ---

const resizeObserver = new ResizeObserver((entries) => {
    for (const entry of entries) {
        const { width, height } = entry.contentRect;
        // Respond to size changes without polling
        updateLayout(entry.target, width, height);
    }
});
resizeObserver.observe(document.querySelector('.responsive-container'));
```

Critical rendering path optimization:
1. **Minimize critical resources** — inline critical CSS, defer non-critical
2. **Minimize critical bytes** — compress, minify
3. **Minimize critical path length** — reduce round trips
4. **Avoid layout thrashing** — batch DOM reads/writes
5. **Use composite-only properties** — transform, opacity for animations
6. **Virtualize long lists** — only render visible items'''
    ),
    (
        "web/javascript-event-loop",
        "Explain the JavaScript event loop in detail: call stack, task queue, microtask queue, requestAnimationFrame timing, and common async patterns.",
        '''The JavaScript event loop orchestrates async execution:

```javascript
// --- Event Loop Architecture ---
//
// Call Stack (synchronous execution)
//     ↓ (when empty, check queues)
// Microtask Queue (Promise.then, queueMicrotask, MutationObserver)
//     ↓ (drain ALL microtasks before proceeding)
// Animation Callbacks (requestAnimationFrame)
//     ↓ (before next paint)
// Render (Style → Layout → Paint → Composite)
//     ↓
// Macrotask Queue (setTimeout, setInterval, I/O, events)
//     ↓ (process ONE macrotask, then back to microtasks)

// --- Execution order demonstration ---

console.log('1: sync');

setTimeout(() => console.log('2: macrotask'), 0);

Promise.resolve().then(() => console.log('3: microtask'));

queueMicrotask(() => console.log('4: microtask'));

requestAnimationFrame(() => console.log('5: rAF'));

Promise.resolve().then(() => {
    console.log('6: microtask');
    // Microtasks from microtasks run before macrotasks
    Promise.resolve().then(() => console.log('7: nested microtask'));
});

console.log('8: sync');

// Output order: 1, 8, 3, 4, 6, 7, 5, 2
// Sync first, then ALL microtasks (including nested), then rAF, then macrotask

// --- Yielding to the main thread ---

// BAD: Long task blocks rendering
function processLargeArray(items) {
    items.forEach(item => heavyComputation(item));
    // UI is frozen during entire execution
}

// GOOD: Break work into chunks using scheduler
async function processInChunks(items, chunkSize = 100) {
    for (let i = 0; i < items.length; i += chunkSize) {
        const chunk = items.slice(i, i + chunkSize);
        chunk.forEach(item => heavyComputation(item));

        // Yield to main thread between chunks
        await new Promise(resolve => setTimeout(resolve, 0));
    }
}

// BETTER: Use scheduler API (modern browsers)
async function processWithScheduler(items) {
    for (const item of items) {
        await scheduler.yield();  // Yield if higher-priority work waiting
        heavyComputation(item);
    }
}

// --- AbortController for cancellable async operations ---

class CancellableTask {
    constructor() {
        this.controller = new AbortController();
    }

    async run(items) {
        const signal = this.controller.signal;

        for (const item of items) {
            if (signal.aborted) {
                throw new DOMException('Task cancelled', 'AbortError');
            }
            await processItem(item);
            await new Promise(r => setTimeout(r, 0));  // Yield
        }
    }

    cancel() {
        this.controller.abort();
    }
}

// --- Debounce and throttle (event loop aware) ---

function debounce(fn, delay) {
    let timer = null;
    return function (...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

function throttle(fn, interval) {
    let lastTime = 0;
    let timer = null;
    return function (...args) {
        const now = Date.now();
        const remaining = interval - (now - lastTime);
        clearTimeout(timer);

        if (remaining <= 0) {
            lastTime = now;
            fn.apply(this, args);
        } else {
            timer = setTimeout(() => {
                lastTime = Date.now();
                fn.apply(this, args);
            }, remaining);
        }
    };
}

// --- Performance measurement ---

function measureTask(name, fn) {
    performance.mark(`${name}-start`);
    fn();
    performance.mark(`${name}-end`);
    performance.measure(name, `${name}-start`, `${name}-end`);
    const entry = performance.getEntriesByName(name)[0];
    console.log(`${name}: ${entry.duration.toFixed(2)}ms`);
}

// Long task observer
const longTaskObserver = new PerformanceObserver((list) => {
    for (const entry of list.getEntries()) {
        console.warn(`Long task detected: ${entry.duration.toFixed(0)}ms`);
        // Log to monitoring system
    }
});
longTaskObserver.observe({ type: 'longtask', buffered: true });
```

Key rules:
1. **Microtasks drain completely** before any macrotask or render
2. **One macrotask per loop iteration** (then check microtasks again)
3. **rAF runs before paint** — best place for visual updates
4. **Long tasks (>50ms) block** — break them up with yields
5. **setTimeout(fn, 0)** minimum is actually 1-4ms (browser-dependent)'''
    ),
    (
        "web/web-workers",
        "Explain Web Workers, SharedArrayBuffer, and Atomics for parallel computation in the browser. Show practical patterns.",
        '''Web Workers enable true multi-threading in JavaScript:

```javascript
// --- Dedicated Worker ---
// main.js
const worker = new Worker('worker.js');

// Structured clone (copies data)
worker.postMessage({ type: 'process', data: largeArray });

// Transferable objects (zero-copy transfer)
const buffer = new ArrayBuffer(1024 * 1024);
worker.postMessage({ type: 'compute', buffer }, [buffer]);
// buffer is now neutered (unusable) in main thread

worker.onmessage = (event) => {
    const { type, result } = event.data;
    if (type === 'result') {
        updateUI(result);
    }
};

worker.onerror = (error) => {
    console.error('Worker error:', error.message);
};

// worker.js
self.onmessage = (event) => {
    const { type, data, buffer } = event.data;

    if (type === 'process') {
        const result = heavyComputation(data);
        self.postMessage({ type: 'result', result });
    }

    if (type === 'compute') {
        const view = new Float64Array(buffer);
        // Process buffer...
        self.postMessage({ type: 'result', buffer }, [buffer]);
    }
};

// --- Worker Pool ---

class WorkerPool {
    constructor(workerUrl, poolSize = navigator.hardwareConcurrency || 4) {
        this.workers = [];
        this.queue = [];
        this.activeJobs = new Map();

        for (let i = 0; i < poolSize; i++) {
            const worker = new Worker(workerUrl);
            worker.busy = false;
            worker.onmessage = (e) => this._onMessage(worker, e);
            this.workers.push(worker);
        }
    }

    execute(task) {
        return new Promise((resolve, reject) => {
            const job = { task, resolve, reject };
            const freeWorker = this.workers.find(w => !w.busy);

            if (freeWorker) {
                this._dispatch(freeWorker, job);
            } else {
                this.queue.push(job);
            }
        });
    }

    _dispatch(worker, job) {
        worker.busy = true;
        this.activeJobs.set(worker, job);
        worker.postMessage(job.task);
    }

    _onMessage(worker, event) {
        const job = this.activeJobs.get(worker);
        this.activeJobs.delete(worker);
        worker.busy = false;

        if (event.data.error) {
            job.reject(new Error(event.data.error));
        } else {
            job.resolve(event.data.result);
        }

        // Process queued job
        if (this.queue.length > 0) {
            this._dispatch(worker, this.queue.shift());
        }
    }

    terminate() {
        this.workers.forEach(w => w.terminate());
    }
}

// Usage:
const pool = new WorkerPool('compute-worker.js', 4);

async function parallelProcess(items) {
    const results = await Promise.all(
        items.map(item => pool.execute({ type: 'process', item }))
    );
    return results;
}

// --- SharedArrayBuffer + Atomics ---

// main.js (requires cross-origin isolation headers)
// Cross-Origin-Opener-Policy: same-origin
// Cross-Origin-Embedder-Policy: require-corp

const sharedBuffer = new SharedArrayBuffer(1024 * Int32Array.BYTES_PER_ELEMENT);
const sharedArray = new Int32Array(sharedBuffer);

// Share with workers (no transfer, both can access)
worker1.postMessage({ buffer: sharedBuffer });
worker2.postMessage({ buffer: sharedBuffer });

// --- Atomic operations (thread-safe) ---

// worker.js
self.onmessage = (event) => {
    const shared = new Int32Array(event.data.buffer);

    // Atomic increment (thread-safe counter)
    Atomics.add(shared, 0, 1);

    // Compare-and-swap (lock-free)
    let current = Atomics.load(shared, 1);
    while (!Atomics.compareExchange(shared, 1, current, current + 1)) {
        current = Atomics.load(shared, 1);
    }

    // Wait/notify (synchronization)
    // Worker 1: wait for signal
    Atomics.wait(shared, 2, 0);  // Block until shared[2] != 0

    // Worker 2: send signal
    Atomics.store(shared, 2, 1);
    Atomics.notify(shared, 2, 1);  // Wake one waiting thread
};

// --- Parallel array processing with SharedArrayBuffer ---

function parallelSum(array, numWorkers = 4) {
    const length = array.length;
    const chunkSize = Math.ceil(length / numWorkers);

    // Shared input + output
    const inputBuffer = new SharedArrayBuffer(length * Float64Array.BYTES_PER_ELEMENT);
    const resultBuffer = new SharedArrayBuffer(numWorkers * Float64Array.BYTES_PER_ELEMENT);

    const input = new Float64Array(inputBuffer);
    input.set(array);  // Copy data to shared buffer

    const workers = [];
    const promises = [];

    for (let i = 0; i < numWorkers; i++) {
        const worker = new Worker('sum-worker.js');
        workers.push(worker);

        promises.push(new Promise(resolve => {
            worker.onmessage = () => resolve();
        }));

        worker.postMessage({
            input: inputBuffer,
            result: resultBuffer,
            start: i * chunkSize,
            end: Math.min((i + 1) * chunkSize, length),
            index: i,
        });
    }

    return Promise.all(promises).then(() => {
        const results = new Float64Array(resultBuffer);
        let total = 0;
        for (let i = 0; i < numWorkers; i++) total += results[i];
        workers.forEach(w => w.terminate());
        return total;
    });
}
```

When to use each pattern:
- **Dedicated Worker** — single background task (parsing, encoding)
- **Worker Pool** — many independent tasks (image processing, data transforms)
- **SharedArrayBuffer** — large data shared between threads (simulations, real-time processing)
- **Service Worker** — network proxy, offline caching, push notifications'''
    ),
    (
        "web/websocket-patterns",
        "Show WebSocket implementation patterns: connection management, reconnection, heartbeats, message protocol design, and scaling.",
        '''Production WebSocket patterns:

```python
# --- Server (FastAPI + WebSocket) ---
import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Optional
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

@dataclass
class Client:
    ws: WebSocket
    user_id: str
    connected_at: float = field(default_factory=time.time)
    last_pong: float = field(default_factory=time.time)
    subscriptions: set[str] = field(default_factory=set)

class ConnectionManager:
    def __init__(self):
        self.clients: dict[str, Client] = {}
        self.channels: dict[str, set[str]] = {}  # channel → {user_ids}

    async def connect(self, ws: WebSocket, user_id: str) -> Client:
        await ws.accept()
        client = Client(ws=ws, user_id=user_id)
        self.clients[user_id] = client
        return client

    def disconnect(self, user_id: str):
        client = self.clients.pop(user_id, None)
        if client:
            for channel in client.subscriptions:
                self.channels.get(channel, set()).discard(user_id)

    async def subscribe(self, user_id: str, channel: str):
        if channel not in self.channels:
            self.channels[channel] = set()
        self.channels[channel].add(user_id)
        if user_id in self.clients:
            self.clients[user_id].subscriptions.add(channel)

    async def broadcast(self, channel: str, message: dict):
        """Send to all subscribers of a channel."""
        user_ids = self.channels.get(channel, set())
        dead = []
        for uid in user_ids:
            client = self.clients.get(uid)
            if client and client.ws.client_state == WebSocketState.CONNECTED:
                try:
                    await client.ws.send_json(message)
                except Exception:
                    dead.append(uid)
        for uid in dead:
            self.disconnect(uid)

    async def send_to_user(self, user_id: str, message: dict):
        client = self.clients.get(user_id)
        if client:
            await client.ws.send_json(message)

manager = ConnectionManager()

# --- Message protocol ---

async def handle_message(client: Client, raw: str):
    """Route messages based on type."""
    try:
        msg = json.loads(raw)
    except json.JSONDecodeError:
        await client.ws.send_json({"type": "error", "message": "Invalid JSON"})
        return

    msg_type = msg.get("type")
    handlers = {
        "subscribe": handle_subscribe,
        "unsubscribe": handle_unsubscribe,
        "publish": handle_publish,
        "pong": handle_pong,
    }

    handler = handlers.get(msg_type)
    if handler:
        await handler(client, msg)
    else:
        await client.ws.send_json({"type": "error", "message": f"Unknown type: {msg_type}"})

async def handle_subscribe(client: Client, msg: dict):
    channel = msg.get("channel")
    if channel:
        await manager.subscribe(client.user_id, channel)
        await client.ws.send_json({"type": "subscribed", "channel": channel})

async def handle_unsubscribe(client: Client, msg: dict):
    channel = msg.get("channel")
    if channel:
        client.subscriptions.discard(channel)
        manager.channels.get(channel, set()).discard(client.user_id)

async def handle_publish(client: Client, msg: dict):
    channel = msg.get("channel")
    if channel and channel in client.subscriptions:
        await manager.broadcast(channel, {
            "type": "message",
            "channel": channel,
            "from": client.user_id,
            "data": msg.get("data"),
            "ts": time.time(),
        })

async def handle_pong(client: Client, msg: dict):
    client.last_pong = time.time()

# --- Heartbeat task ---

async def heartbeat_loop(interval: int = 30, timeout: int = 60):
    """Detect dead connections via ping/pong."""
    while True:
        await asyncio.sleep(interval)
        now = time.time()
        dead = []
        for uid, client in manager.clients.items():
            if now - client.last_pong > timeout:
                dead.append(uid)
            else:
                try:
                    await client.ws.send_json({"type": "ping", "ts": now})
                except Exception:
                    dead.append(uid)
        for uid in dead:
            manager.disconnect(uid)

# --- FastAPI endpoints ---

app = FastAPI()

@asynccontextmanager
async def lifespan(app):
    task = asyncio.create_task(heartbeat_loop())
    yield
    task.cancel()

@app.websocket("/ws/{user_id}")
async def websocket_endpoint(ws: WebSocket, user_id: str):
    client = await manager.connect(ws, user_id)
    try:
        while True:
            raw = await ws.receive_text()
            await handle_message(client, raw)
    except WebSocketDisconnect:
        manager.disconnect(user_id)
```

```javascript
// --- Client-side with auto-reconnect ---

class ReconnectingWebSocket {
    constructor(url, options = {}) {
        this.url = url;
        this.maxRetries = options.maxRetries ?? 10;
        this.baseDelay = options.baseDelay ?? 1000;
        this.maxDelay = options.maxDelay ?? 30000;
        this.retryCount = 0;
        this.handlers = { message: [], open: [], close: [] };
        this.pendingSubscriptions = new Set();
        this.connect();
    }

    connect() {
        this.ws = new WebSocket(this.url);

        this.ws.onopen = () => {
            this.retryCount = 0;
            // Resubscribe after reconnect
            for (const channel of this.pendingSubscriptions) {
                this.send({ type: 'subscribe', channel });
            }
            this.handlers.open.forEach(fn => fn());
            this._startPingInterval();
        };

        this.ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === 'ping') {
                this.send({ type: 'pong' });
                return;
            }
            this.handlers.message.forEach(fn => fn(msg));
        };

        this.ws.onclose = () => {
            this._stopPingInterval();
            this.handlers.close.forEach(fn => fn());
            this._reconnect();
        };
    }

    _reconnect() {
        if (this.retryCount >= this.maxRetries) return;
        // Exponential backoff with jitter
        const delay = Math.min(
            this.baseDelay * Math.pow(2, this.retryCount) + Math.random() * 1000,
            this.maxDelay
        );
        this.retryCount++;
        setTimeout(() => this.connect(), delay);
    }

    send(msg) {
        if (this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(msg));
        }
    }

    subscribe(channel) {
        this.pendingSubscriptions.add(channel);
        this.send({ type: 'subscribe', channel });
    }

    on(event, handler) { this.handlers[event].push(handler); }
}
```

Scaling WebSockets:
- **Sticky sessions** — same user routes to same server (via cookie/IP hash)
- **Pub/sub backbone** — Redis pub/sub or NATS for cross-server messaging
- **Connection limits** — ~10K connections per server (monitor file descriptors)
- **Compression** — `permessage-deflate` extension for large payloads'''
    ),
]
