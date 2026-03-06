"""Thinking-trace pairs: browser debugging."""

PAIRS = [
    (
        "thinking/debugging",
        r'''My fetch request to my API is being blocked by CORS when I include credentials (cookies). It works without credentials but fails when I add credentials: "include". The error is:

"Access to fetch at 'https://api.example.com/data' from origin 'https://app.example.com' has been blocked by CORS policy: The value of the 'Access-Control-Allow-Origin' header must not be the wildcard '*' when the request's credentials mode is 'include'."

My server responds with Access-Control-Allow-Origin: *. How do I fix this?''',
        r'''<think>
The error is clear: when credentials mode is "include" (cookies, HTTP auth), the server cannot use the wildcard "*" for Access-Control-Allow-Origin. The browser requires an explicit origin value.

Additionally, the server must also send:
- Access-Control-Allow-Credentials: true
- Access-Control-Allow-Origin must be the exact requesting origin (not *)

This is a security measure: if * were allowed with credentials, any website could send authenticated requests to the API and read the response.

The fix needs to be on the server side.
</think>

When using `credentials: "include"`, the browser enforces strict CORS rules. The wildcard `*` is not allowed. Here is the complete fix:

```javascript
// ============================================================
// CLIENT SIDE: The fetch request
// ============================================================

// This request requires cookies to be sent
const response = await fetch("https://api.example.com/data", {
    method: "GET",
    credentials: "include",  // Send cookies cross-origin
    headers: {
        "Content-Type": "application/json",
    },
});
```

```python
# ============================================================
# SERVER SIDE FIX (Python/FastAPI)
# ============================================================

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# BAD: Wildcard origin with credentials does not work
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["*"],  # FAILS with credentials
#     allow_credentials=True,
# )

# GOOD: Explicit origin list
ALLOWED_ORIGINS = [
    "https://app.example.com",
    "https://staging.example.com",
    "http://localhost:3000",  # Development
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,     # Explicit origins, NOT "*"
    allow_credentials=True,             # Allow cookies
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
    expose_headers=["X-Total-Count"],   # Headers client can read
    max_age=3600,                       # Cache preflight for 1 hour
)

# ============================================================
# DYNAMIC ORIGIN (when you have many allowed origins)
# ============================================================

from starlette.types import ASGIApp, Receive, Scope, Send

class DynamicCORSMiddleware:
    """CORS middleware that dynamically checks the Origin header."""

    def __init__(self, app: ASGIApp, allowed_origin_pattern: str = None):
        self.app = app
        self.allowed_pattern = allowed_origin_pattern

    def is_origin_allowed(self, origin: str) -> bool:
        """Check if the origin is allowed."""
        if not origin:
            return False

        # Allow specific domains and their subdomains
        import re
        allowed_patterns = [
            r"^https://.*\.example\.com$",
            r"^https://app\.example\.com$",
            r"^http://localhost:\d+$",
        ]
        return any(re.match(p, origin) for p in allowed_patterns)

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        origin = headers.get(b"origin", b"").decode()

        if not self.is_origin_allowed(origin):
            await self.app(scope, receive, send)
            return

        # Handle preflight (OPTIONS) requests
        if scope["method"] == "OPTIONS":
            from starlette.responses import Response
            response = Response(
                status_code=204,
                headers={
                    "Access-Control-Allow-Origin": origin,
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE",
                    "Access-Control-Allow-Headers": "Content-Type, Authorization",
                    "Access-Control-Max-Age": "3600",
                },
            )
            await response(scope, receive, send)
            return

        # For actual requests, add CORS headers to response
        async def send_with_cors(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                cors_headers = [
                    (b"access-control-allow-origin", origin.encode()),
                    (b"access-control-allow-credentials", b"true"),
                    (b"vary", b"Origin"),
                ]
                message["headers"] = list(message.get("headers", [])) + cors_headers
            await send(message)

        await self.app(scope, receive, send_with_cors)


app.add_middleware(DynamicCORSMiddleware)

# ============================================================
# COMMON CORS + CREDENTIALS CHECKLIST
# ============================================================

# 1. Access-Control-Allow-Origin MUST be exact origin (not *)
# 2. Access-Control-Allow-Credentials MUST be "true"
# 3. Set-Cookie header needs SameSite=None; Secure for cross-origin
# 4. The Vary header MUST include "Origin" (prevents cache issues)
# 5. Preflight (OPTIONS) response must include all CORS headers
# 6. Cookie domain must match or be parent of API domain

# COOKIE CONFIGURATION for cross-origin:
# Set-Cookie: session=abc123; SameSite=None; Secure; HttpOnly; Path=/

# In Python:
from fastapi.responses import JSONResponse

@app.post("/login")
async def login():
    response = JSONResponse({"status": "logged in"})
    response.set_cookie(
        key="session",
        value="abc123",
        httponly=True,
        secure=True,          # Required for SameSite=None
        samesite="none",      # Required for cross-origin cookies
        domain=".example.com", # Shared across subdomains
        max_age=3600,
    )
    return response
```

**Key rules for CORS with credentials:**
1. `Access-Control-Allow-Origin` must be the exact origin, never `*`
2. `Access-Control-Allow-Credentials: true` must be present
3. Cookies must have `SameSite=None; Secure` for cross-origin
4. Always include `Vary: Origin` to prevent CDN cache poisoning''',
    ),
    (
        "thinking/debugging",
        r'''My service worker cache is serving stale content after I deploy updates. Users see the old version of my app until they hard-refresh or clear the cache. How do I fix service worker cache staleness?''',
        r'''<think>
Service worker cache staleness is one of the most common PWA issues. The problem is:
1. Service worker intercepts all requests and serves from cache
2. The browser checks for SW updates but the SW itself is cached
3. Even when a new SW is found, it waits in "waiting" state until all tabs close
4. The old SW keeps serving stale cached content

Solutions:
1. Cache-busting strategies (versioned cache names)
2. Skip waiting to activate immediately
3. Navigation preload
4. Stale-while-revalidate caching strategy
5. Prompt user to refresh when update is available
</think>

Service worker cache staleness requires a combination of caching strategies and update mechanisms. Here is the complete solution:

```javascript
// ============================================================
// service-worker.js - With proper cache management
// ============================================================

// VERSION: Change this on every deploy to invalidate old caches
const CACHE_VERSION = "v2.1.0";
const CACHE_NAME = `app-cache-${CACHE_VERSION}`;

// Files to cache on install (app shell)
const APP_SHELL = [
    "/",
    "/index.html",
    "/styles/main.css",
    "/scripts/app.js",
    "/manifest.json",
];

// ============================================================
// INSTALL: Cache app shell with new version
// ============================================================
self.addEventListener("install", (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then((cache) => cache.addAll(APP_SHELL))
            .then(() => {
                // CRITICAL: Skip waiting to activate immediately
                // Without this, the new SW waits until all tabs close
                return self.skipWaiting();
            })
    );
});

// ============================================================
// ACTIVATE: Delete old caches
// ============================================================
self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches.keys()
            .then((cacheNames) => {
                return Promise.all(
                    cacheNames
                        .filter((name) => name !== CACHE_NAME)
                        .map((name) => {
                            console.log("Deleting old cache:", name);
                            return caches.delete(name);
                        })
                );
            })
            .then(() => {
                // Take control of all open tabs immediately
                return self.clients.claim();
            })
    );
});

// ============================================================
// FETCH: Stale-while-revalidate strategy
// ============================================================
self.addEventListener("fetch", (event) => {
    const url = new URL(event.request.url);

    // Skip non-GET requests
    if (event.request.method !== "GET") return;

    // Skip API calls (do not cache)
    if (url.pathname.startsWith("/api/")) return;

    // For navigation requests: network-first strategy
    if (event.request.mode === "navigate") {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    // Cache the fresh response
                    const clone = response.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, clone);
                    });
                    return response;
                })
                .catch(() => {
                    // Offline fallback
                    return caches.match(event.request)
                        || caches.match("/offline.html");
                })
        );
        return;
    }

    // For assets: stale-while-revalidate
    event.respondWith(
        caches.match(event.request).then((cachedResponse) => {
            // Start network fetch in background
            const fetchPromise = fetch(event.request)
                .then((networkResponse) => {
                    // Update cache with fresh response
                    const clone = networkResponse.clone();
                    caches.open(CACHE_NAME).then((cache) => {
                        cache.put(event.request, clone);
                    });
                    return networkResponse;
                })
                .catch(() => cachedResponse);

            // Return cached version immediately, update in background
            return cachedResponse || fetchPromise;
        })
    );
});

// ============================================================
// MESSAGE: Handle update commands from the page
// ============================================================
self.addEventListener("message", (event) => {
    if (event.data === "skipWaiting") {
        self.skipWaiting();
    }
});
```

```javascript
// ============================================================
// main.js - Register SW and handle updates on the page
// ============================================================

async function registerServiceWorker() {
    if (!("serviceWorker" in navigator)) return;

    try {
        const registration = await navigator.serviceWorker.register(
            "/service-worker.js",
            { scope: "/" }
        );

        // Check for updates periodically
        setInterval(() => {
            registration.update();
        }, 60 * 60 * 1000); // Every hour

        // Detect when a new SW is waiting
        registration.addEventListener("updatefound", () => {
            const newWorker = registration.installing;

            newWorker.addEventListener("statechange", () => {
                if (newWorker.state === "installed" &&
                    navigator.serviceWorker.controller) {
                    // New version available! Prompt user.
                    showUpdateBanner();
                }
            });
        });

        // When the new SW takes over, reload the page
        let refreshing = false;
        navigator.serviceWorker.addEventListener("controllerchange", () => {
            if (!refreshing) {
                refreshing = true;
                window.location.reload();
            }
        });

    } catch (error) {
        console.error("SW registration failed:", error);
    }
}

function showUpdateBanner() {
    // Show a banner: "New version available. Click to update."
    const banner = document.createElement("div");
    banner.id = "update-banner";
    banner.innerHTML = [
        '<p>A new version is available.</p>',
        '<button id="update-btn">Update Now</button>',
    ].join("");
    banner.style.cssText = [
        "position:fixed;bottom:0;left:0;right:0;",
        "background:#333;color:#fff;padding:16px;text-align:center;",
        "z-index:99999;",
    ].join("");
    document.body.appendChild(banner);

    document.getElementById("update-btn").addEventListener("click", () => {
        // Tell the waiting SW to activate
        navigator.serviceWorker.getRegistration().then((reg) => {
            if (reg && reg.waiting) {
                reg.waiting.postMessage("skipWaiting");
            }
        });
        banner.remove();
    });
}

registerServiceWorker();
```

**Cache staleness prevention checklist:**
1. Version your cache name (`app-cache-v2.1.0`) -- change on every deploy
2. Use `skipWaiting()` + `clients.claim()` for immediate activation
3. Delete old caches in the `activate` event
4. Use network-first for HTML, stale-while-revalidate for assets
5. Prompt users to reload when updates are detected
6. Never cache API responses in the service worker cache''',
    ),
    (
        "thinking/debugging",
        r'''My Web Worker is throwing "DataCloneError: Failed to execute 'postMessage' on 'Worker': [object Object] could not be cloned" when I try to send data to the worker. Some objects transfer fine but others fail. What types cannot be sent?''',
        r'''<think>
The structured clone algorithm used by postMessage cannot clone certain types:
1. Functions (including methods on objects)
2. DOM nodes (Element, Document, etc.)
3. Error objects (in some browsers)
4. Symbols
5. Property descriptors, getters/setters
6. Prototype chain is lost (only own enumerable properties are cloned)
7. Map/Set work, but WeakMap/WeakSet do not
8. RegExp works, Date works
9. Circular references are handled correctly

The fix is to serialize the data before sending, or use Transferable objects for performance.
</think>

The `postMessage` API uses the structured clone algorithm, which cannot clone certain JavaScript types. Here is what works and what does not:

```javascript
// ============================================================
// WHAT CAN AND CANNOT BE CLONED
// ============================================================

// WORKS: Primitive types, plain objects, arrays
worker.postMessage({ name: "Alice", age: 30 });        // OK
worker.postMessage([1, 2, 3, 4, 5]);                   // OK
worker.postMessage("hello");                            // OK
worker.postMessage(42);                                 // OK
worker.postMessage(null);                               // OK
worker.postMessage(new Date());                         // OK
worker.postMessage(new Map([["a", 1]]));                // OK
worker.postMessage(new Set([1, 2, 3]));                 // OK
worker.postMessage(/regex/gi);                          // OK
worker.postMessage(new ArrayBuffer(1024));              // OK
worker.postMessage(new Uint8Array([1, 2, 3]));          // OK

// FAILS: Functions, DOM nodes, symbols
worker.postMessage({ fn: () => {} });                   // DataCloneError
worker.postMessage(document.body);                      // DataCloneError
worker.postMessage({ sym: Symbol("id") });              // DataCloneError
worker.postMessage(new WeakMap());                      // DataCloneError
worker.postMessage(new WeakSet());                      // DataCloneError

// LOSES DATA: Class instances lose their prototype
class User {
    constructor(name) { this.name = name; }
    greet() { return `Hi, ${this.name}`; }
}
worker.postMessage(new User("Alice"));
// Worker receives: { name: "Alice" } -- greet() method is gone!

// ============================================================
// FIX 1: Serialize before sending
// ============================================================

// For objects with methods or non-cloneable properties:
function serializeForWorker(obj) {
    // Extract only the data properties
    return JSON.parse(JSON.stringify(obj));
}

// For class instances with methods:
class Task {
    constructor(id, data, processor) {
        this.id = id;
        this.data = data;
        this.processor = processor; // function -- not cloneable
    }

    toTransferable() {
        // Return only the cloneable parts
        return {
            type: "Task",
            id: this.id,
            data: this.data,
            // Omit processor function
        };
    }

    static fromTransferable(obj) {
        // Reconstruct on the other side
        return new Task(obj.id, obj.data, getProcessorById(obj.id));
    }
}

// Send:
const task = new Task(1, { values: [1, 2, 3] }, processData);
worker.postMessage(task.toTransferable());

// In worker, reconstruct:
self.onmessage = function(event) {
    const task = Task.fromTransferable(event.data);
    // ...
};

// ============================================================
// FIX 2: Use Transferable objects for large data (zero-copy)
// ============================================================

// For large ArrayBuffers, TRANSFER instead of clone
// This moves the buffer to the worker (original becomes unusable)
const buffer = new ArrayBuffer(1024 * 1024); // 1 MB
const data = new Float64Array(buffer);

// Fill with data
for (let i = 0; i < data.length; i++) {
    data[i] = Math.random();
}

// CLONE (slow for large buffers -- copies the data):
// worker.postMessage({ data: data });

// TRANSFER (fast -- zero-copy, moves ownership):
worker.postMessage({ data: buffer }, [buffer]);
// WARNING: buffer is now detached -- buffer.byteLength === 0

// In the worker, transfer back when done:
self.onmessage = function(event) {
    const buffer = event.data.data;
    const arr = new Float64Array(buffer);

    // Process...
    for (let i = 0; i < arr.length; i++) {
        arr[i] = arr[i] * 2;
    }

    // Transfer back to main thread
    self.postMessage({ result: buffer }, [buffer]);
};

// ============================================================
// FIX 3: MessageChannel for typed communication
// ============================================================

// Create a typed message protocol
const MessageTypes = {
    PROCESS_DATA: "PROCESS_DATA",
    RESULT: "RESULT",
    ERROR: "ERROR",
    PROGRESS: "PROGRESS",
};

// Main thread:
function sendToWorker(worker, type, payload, transfer = []) {
    const message = {
        id: crypto.randomUUID(),
        type: type,
        payload: payload,
        timestamp: Date.now(),
    };
    worker.postMessage(message, transfer);
    return message.id;
}

// Worker:
self.onmessage = function(event) {
    const { id, type, payload } = event.data;

    switch (type) {
        case MessageTypes.PROCESS_DATA:
            try {
                const result = processData(payload);
                self.postMessage({
                    id: id,
                    type: MessageTypes.RESULT,
                    payload: result,
                });
            } catch (error) {
                self.postMessage({
                    id: id,
                    type: MessageTypes.ERROR,
                    payload: { message: error.message, stack: error.stack },
                });
            }
            break;
    }
};

// ============================================================
// FIX 4: Use comlink for transparent RPC (recommended)
// ============================================================

// npm install comlink
// Comlink wraps postMessage into a proxy-based RPC interface

// worker.js:
// import * as Comlink from "comlink";
//
// const api = {
//     processData(data) { return data.map(x => x * 2); },
//     async fetchAndProcess(url) {
//         const resp = await fetch(url);
//         return resp.json();
//     },
// };
// Comlink.expose(api);

// main.js:
// import * as Comlink from "comlink";
//
// const worker = new Worker("worker.js");
// const api = Comlink.wrap(worker);
// const result = await api.processData([1, 2, 3]); // [2, 4, 6]
// Comlink handles serialization automatically
```

**Key rules for Web Worker communication:**
1. Only structured-cloneable types can be sent via postMessage
2. Functions, DOM nodes, Symbols, and WeakMap/WeakSet cannot be cloned
3. Class instances lose their prototype chain (methods disappear)
4. Use Transferable objects for large ArrayBuffers (zero-copy transfer)
5. Consider Comlink library for transparent RPC over postMessage''',
    ),
    (
        "thinking/debugging",
        r'''My IndexedDB transaction is aborting silently and I cannot figure out why. I am trying to store data in a transaction but the onsuccess callback never fires and onerror shows "AbortError". Here is my code:

const db = await openDatabase();
const tx = db.transaction(["users", "orders"], "readwrite");
const userStore = tx.objectStore("users");
const orderStore = tx.objectStore("orders");

// Store user
const userReq = userStore.put({ id: 1, name: "Alice" });
userReq.onsuccess = () => {
    console.log("User stored");
    // Now fetch something from another store
    fetch("/api/validate")
        .then(res => res.json())
        .then(data => {
            // This fails! Transaction already closed
            orderStore.put({ id: 1, userId: 1, total: data.total });
        });
};''',
        r'''<think>
The issue is that IndexedDB transactions auto-commit when there are no pending requests within the same event loop microtask. When the code does `fetch()` inside the onsuccess callback, the fetch is asynchronous and returns a Promise. The transaction sees no pending IDB requests and auto-commits. By the time the fetch resolves and tries to use `orderStore.put()`, the transaction is already committed/closed.

This is one of the most confusing aspects of IndexedDB: transactions have an "auto-commit" behavior tied to the microtask queue. You cannot use regular async/await patterns with IDB transactions because any async gap closes the transaction.

The fix is to either:
1. Do all IDB operations synchronously (no await/fetch between them)
2. Do the fetch BEFORE starting the transaction
3. Use a library like idb that provides better Promise-based wrappers
</think>

IndexedDB transactions auto-commit when there are no pending requests in the current microtask. The `fetch()` call creates an async gap that closes the transaction before the order can be stored.

```javascript
// ============================================================
// THE PROBLEM: Async gap closes the transaction
// ============================================================

// IndexedDB transactions auto-commit when:
// 1. All pending IDB requests have completed
// 2. No new IDB requests are made in the same microtask
//
// When you call fetch().then(), the .then() callback runs in a
// LATER microtask. The transaction sees no pending requests and
// commits before the fetch resolves.

// Timeline:
// 1. userStore.put() -- pending request
// 2. onsuccess fires -- request complete, no new requests yet
// 3. fetch() starts -- this is NOT an IDB request
// 4. Transaction sees 0 pending IDB requests --> auto-commits
// 5. fetch resolves, tries orderStore.put() --> AbortError!

// ============================================================
// FIX 1: Do ALL IDB operations before any async work
// ============================================================

async function saveUserAndOrder(db, userData, orderId) {
    // Do the async work FIRST, before starting the transaction
    const response = await fetch("/api/validate");
    const validation = await response.json();

    // NOW start the transaction with all data ready
    return new Promise((resolve, reject) => {
        const tx = db.transaction(["users", "orders"], "readwrite");

        tx.oncomplete = () => resolve("success");
        tx.onerror = (e) => reject(tx.error);
        tx.onabort = (e) => reject(new Error("Transaction aborted: " + tx.error));

        // All IDB operations happen synchronously within the transaction
        const userStore = tx.objectStore("users");
        const orderStore = tx.objectStore("orders");

        userStore.put(userData);
        orderStore.put({
            id: orderId,
            userId: userData.id,
            total: validation.total,
        });

        // Transaction will auto-commit after these requests complete
    });
}

// Usage:
// await saveUserAndOrder(db, { id: 1, name: "Alice" }, 1);

// ============================================================
// FIX 2: Use the "idb" library for better Promise support
// ============================================================

// npm install idb
// import { openDB } from "idb";

async function saveWithIdb() {
    // const db = await openDB("mydb", 1, { ... });

    // Fetch data first
    const response = await fetch("/api/validate");
    const validation = await response.json();

    // idb provides a cleaner transaction API
    const tx = db.transaction(["users", "orders"], "readwrite");

    // These are all synchronous within the transaction scope
    await Promise.all([
        tx.objectStore("users").put({ id: 1, name: "Alice" }),
        tx.objectStore("orders").put({
            id: 1, userId: 1, total: validation.total,
        }),
        tx.done,  // Resolves when transaction commits
    ]);

    console.log("Both stores updated successfully");
}

// ============================================================
// FIX 3: Split into separate transactions if needed
// ============================================================

async function saveInSteps(db) {
    // Transaction 1: Save user
    await new Promise((resolve, reject) => {
        const tx = db.transaction(["users"], "readwrite");
        tx.oncomplete = resolve;
        tx.onerror = () => reject(tx.error);
        tx.objectStore("users").put({ id: 1, name: "Alice" });
    });

    // Async work between transactions is fine
    const response = await fetch("/api/validate");
    const validation = await response.json();

    // Transaction 2: Save order
    await new Promise((resolve, reject) => {
        const tx = db.transaction(["orders"], "readwrite");
        tx.oncomplete = resolve;
        tx.onerror = () => reject(tx.error);
        tx.objectStore("orders").put({
            id: 1, userId: 1, total: validation.total,
        });
    });
}

// ============================================================
// DEBUGGING: Better error handling for IDB transactions
// ============================================================

function createTransaction(db, storeNames, mode) {
    return new Promise((resolve, reject) => {
        const tx = db.transaction(storeNames, mode);

        // Track all operations
        const operations = [];

        tx.oncomplete = () => {
            console.log(
                "Transaction committed:",
                operations.length, "operations"
            );
            resolve();
        };

        tx.onerror = (event) => {
            console.error("Transaction error:", tx.error);
            console.error("Failed operations:", operations);
            reject(tx.error);
        };

        tx.onabort = (event) => {
            console.error("Transaction ABORTED:", tx.error);
            console.error(
                "This usually means an async gap closed the transaction."
            );
            reject(new Error("Transaction aborted: " + (tx.error || "unknown")));
        };

        // Wrap object stores with logging
        const stores = {};
        for (const name of storeNames) {
            const store = tx.objectStore(name);
            stores[name] = {
                put: (data) => {
                    operations.push({ store: name, op: "put", data });
                    return store.put(data);
                },
                get: (key) => {
                    operations.push({ store: name, op: "get", key });
                    return store.get(key);
                },
                delete: (key) => {
                    operations.push({ store: name, op: "delete", key });
                    return store.delete(key);
                },
            };
        }

        resolve({ tx, stores });
    });
}
```

**Key rule:** Never do async work (fetch, setTimeout, await) inside an IndexedDB transaction. The transaction auto-commits as soon as there are no pending IDB requests. Fetch all external data BEFORE starting the transaction, then do all IDB operations synchronously within it.''',
    ),
    (
        "thinking/debugging",
        r'''My website's Content Security Policy (CSP) is blocking legitimate resources and I am getting violations in the console. How do I debug CSP violations and create a proper policy without breaking my site?

Console errors:
"Refused to execute inline script because it violates the Content-Security-Policy directive: 'script-src'"
"Refused to load the image 'https://cdn.example.com/logo.png' because it violates the Content-Security-Policy directive: 'img-src 'self'"''',
        r'''<think>
CSP debugging involves:
1. Understanding which directives are blocking which resources
2. Using CSP report-only mode to test policies without breaking the site
3. Identifying all resources the site needs (scripts, styles, images, fonts, etc.)
4. Building a policy incrementally
5. Handling inline scripts/styles with nonces or hashes

Let me provide a systematic approach.
</think>

CSP debugging requires a systematic approach: start with report-only mode, identify all resources, then build the policy incrementally.

```html
<!-- ============================================================ -->
<!-- STEP 1: Use Report-Only mode (does NOT block anything) -->
<!-- ============================================================ -->

<!-- This reports violations without blocking resources -->
<meta http-equiv="Content-Security-Policy-Report-Only"
      content="default-src 'self'; report-uri /csp-report">

<!-- Or set via HTTP header (preferred): -->
<!-- Content-Security-Policy-Report-Only: default-src 'self'; report-uri /csp-report -->
```

```python
# ============================================================
# STEP 2: Collect and analyze CSP violation reports
# ============================================================

from fastapi import FastAPI, Request
from collections import Counter
import json
import logging

app = FastAPI()
logger = logging.getLogger("csp")

violation_counter = Counter()

@app.post("/csp-report")
async def csp_report(request: Request):
    """Collect CSP violation reports."""
    body = await request.json()
    report = body.get("csp-report", body)

    violated_directive = report.get("violated-directive", "unknown")
    blocked_uri = report.get("blocked-uri", "unknown")
    source_file = report.get("source-file", "unknown")
    line_number = report.get("line-number", 0)

    violation_counter[f"{violated_directive}|{blocked_uri}"] += 1

    logger.info(
        "CSP Violation: directive=%s blocked=%s source=%s:%d",
        violated_directive, blocked_uri, source_file, line_number,
    )
    return {"status": "received"}

@app.get("/csp-report/summary")
async def csp_summary():
    """View aggregated violation summary."""
    return {
        "total_violations": sum(violation_counter.values()),
        "top_violations": violation_counter.most_common(20),
    }
```

```javascript
// ============================================================
// STEP 3: Build the CSP policy based on violations
// ============================================================

// Start with a strict policy and add exceptions:

// PHASE 1: Restrictive (breaks things, but shows what is needed)
const STRICT_CSP = [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self'",
    "font-src 'self'",
    "connect-src 'self'",
    "report-uri /csp-report",
].join("; ");

// PHASE 2: Add sources based on violation reports
const TUNED_CSP = [
    "default-src 'self'",
    // Scripts: self + CDN + nonce for inline scripts
    "script-src 'self' https://cdn.example.com 'nonce-abc123'",
    // Styles: self + CDN + unsafe-inline for inline styles
    // (use nonce instead of unsafe-inline when possible)
    "style-src 'self' https://cdn.example.com 'unsafe-inline'",
    // Images: self + CDN + data URIs (for base64 images)
    "img-src 'self' https://cdn.example.com data:",
    // Fonts: self + Google Fonts
    "font-src 'self' https://fonts.gstatic.com",
    // API connections
    "connect-src 'self' https://api.example.com wss://ws.example.com",
    // Frames: none (or specific sources)
    "frame-src 'none'",
    // Form submissions
    "form-action 'self'",
    // Base tag restriction
    "base-uri 'self'",
    // Report violations
    "report-uri /csp-report",
].join("; ");

// ============================================================
// STEP 4: Handle inline scripts with nonces
// ============================================================

// BAD: 'unsafe-inline' allows all inline scripts (XSS risk)
// script-src 'self' 'unsafe-inline'

// GOOD: Use nonces (generated per-request)
// Server generates a random nonce for each page load
// script-src 'self' 'nonce-<random>'

// In HTML:
// <script nonce="abc123">
//     console.log("This inline script is allowed by the nonce");
// </script>
```

```python
# ============================================================
# STEP 5: Server-side nonce generation (Python/FastAPI)
# ============================================================

import secrets
import base64
from fastapi import Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="templates")

@app.middleware("http")
async def add_csp_header(request: Request, call_next):
    """Add CSP header with per-request nonce."""
    # Generate a random nonce for this request
    nonce = base64.b64encode(secrets.token_bytes(16)).decode()
    request.state.csp_nonce = nonce

    response = await call_next(request)

    # Build CSP with the nonce
    csp = "; ".join([
        "default-src 'self'",
        f"script-src 'self' 'nonce-{nonce}' https://cdn.example.com",
        f"style-src 'self' 'nonce-{nonce}' https://cdn.example.com",
        "img-src 'self' https://cdn.example.com data:",
        "font-src 'self' https://fonts.gstatic.com",
        "connect-src 'self' https://api.example.com",
        "frame-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "report-uri /csp-report",
    ])

    response.headers["Content-Security-Policy"] = csp
    return response

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    nonce = request.state.csp_nonce
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "nonce": nonce},
    )

# In template (index.html):
# <script nonce="{{ nonce }}">
#     // This script is allowed by the CSP nonce
#     initApp();
# </script>
```

**CSP debugging workflow:**
1. Deploy with `Content-Security-Policy-Report-Only` first
2. Collect violations for 1-2 weeks to capture all resources
3. Build the allow-list from the violation reports
4. Use nonces for inline scripts (avoid `unsafe-inline`)
5. Switch from Report-Only to enforcing mode
6. Keep the `report-uri` directive to catch regressions''',
    ),
]
