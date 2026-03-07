"""Thinking-trace pairs: browser debugging."""

PAIRS = [
    (
        "thinking/debugging",
        r'''My fetch request to my API is being blocked by CORS when I include credentials (cookies). It works without credentials but fails when I add credentials: "include". The error is:

"Access to fetch at 'https://api.example.com/data' from origin 'https://app.example.com' has been blocked by CORS policy: The value of the 'Access-Control-Allow-Origin' header must not be the wildcard '*' when the request's credentials mode is 'include'."

My server responds with Access-Control-Allow-Origin: *. How do I fix this?''',
        r'''<think>
The error message is very specific: "The value of the 'Access-Control-Allow-Origin' header must not be the wildcard '*' when the request's credentials mode is 'include'."

My first thought was "just change * to the specific origin" -- but wait, WHY does the browser enforce this restriction? Could I just keep * and make it work somehow?

Actually, no. This is a security measure. If `Access-Control-Allow-Origin: *` were allowed with `credentials: "include"`, then ANY website could send authenticated requests (with cookies) to the API and read the response. That would be a massive CSRF/data-exfiltration vulnerability. By requiring an explicit origin, the browser ensures the server consciously decided to trust that specific origin with credentialed access.

So the server needs to:
1. Check the `Origin` header of the incoming request
2. Verify it is in an allow list
3. Echo that specific origin back in `Access-Control-Allow-Origin`
4. Also include `Access-Control-Allow-Credentials: true`

Hmm, but what if I have many subdomains (app.example.com, admin.example.com, staging.example.com)? I cannot list them all statically. I need dynamic origin checking -- read the Origin header, validate it against a pattern, and echo it back. I should also set `Vary: Origin` so CDNs do not cache a response with one origin's ACAO header and serve it to requests from a different origin.

Wait, there is another requirement I almost forgot: for cross-origin cookies to work, the cookies themselves need `SameSite=None; Secure`. Without these attributes, the browser will not send cookies cross-origin regardless of what CORS headers the server sets. This is a common second failure point after fixing the ACAO header.
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
Service worker cache staleness is one of the most frustrating PWA issues. Let me trace the lifecycle to understand why this happens.

When a new service worker is deployed, the browser detects it (via byte-comparison of the SW script) and installs it. But here is the key gotcha: the new SW does NOT activate immediately. It enters a "waiting" state and stays there until ALL tabs with the old SW close. The old SW continues to intercept requests and serve stale cached content.

My first thought was "just call skipWaiting() in the install event to activate immediately." But wait -- that could break things. If the old SW is serving pages that expect old API responses or old JS bundles, and the new SW starts serving new cached content mid-session, the user could see a mix of old and new content. That is why the default behavior is conservative -- it waits for a clean transition.

However, for most web apps, the risk of mixed content is lower than the cost of serving stale content. So skipWaiting() combined with clients.claim() is the right tradeoff. But I should also prompt the user to refresh so they get a clean page load with the new content.

Hmm, what about the caching strategy itself? Even with skipWaiting(), if the cache contains old assets and the new SW still serves from cache, the user sees old content. The solution is versioned cache names (e.g., "app-cache-v2.1.0"). On activation, the new SW deletes all caches except the current version. That ensures a clean slate.

But deleting all old caches on activation means the user has to re-download everything. Could I use a stale-while-revalidate strategy instead? Serve the cached version immediately for fast first paint, but fetch the fresh version in the background and update the cache. The user sees the old content on this visit but gets the new content on the next visit. The tradeoff: it is always one visit behind.

I think the best approach combines multiple strategies: versioned caches for cache cleanup, skipWaiting for immediate activation, network-first for HTML (always get the latest page), and stale-while-revalidate for static assets (fast but eventually fresh).
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
The user is getting DataCloneError when sending objects to a Web Worker via postMessage. The structured clone algorithm cannot clone certain types, but WHICH types exactly?

My first thought was "anything that is not JSON-serializable will fail." But that is not quite right -- structured clone is more capable than JSON. It handles Date objects, Map, Set, ArrayBuffer, RegExp, and even circular references. JSON cannot handle any of those.

So what CAN'T structured clone handle? The key insight is that structured clone cannot serialize anything that involves executable code or runtime-specific resources:
- Functions (including methods on objects) -- because code is not data
- DOM nodes -- because they are tied to the document's rendering context
- Symbols -- because they are unique by definition and cannot be recreated
- WeakMap/WeakSet -- because their entries are tied to garbage collection state

Wait, what about class instances? They CAN be cloned, but... hmm, actually the prototype chain is lost. Structured clone copies only own enumerable properties into a plain object. So `new User("Alice")` becomes `{name: "Alice"}` with no methods. That is technically not an error (no DataCloneError), but it breaks any code that expects methods on the received object.

I initially assumed Error objects could not be cloned, but actually in modern browsers (Chrome 77+), Error objects ARE structured-cloneable. Older browsers throw DataCloneError for them.

For the fix, there are several approaches:
1. Serialize to plain objects before sending (strip methods, convert non-cloneable types)
2. Use Transferable objects for large ArrayBuffers (zero-copy transfer, much faster)
3. Use a library like Comlink that provides transparent RPC over postMessage

The Transferable approach is particularly important for performance -- cloning a 10MB ArrayBuffer copies all the bytes, while transferring moves ownership in O(1).
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
The IndexedDB transaction is aborting silently. The user does `fetch()` inside the `onsuccess` callback and then tries to use the transaction after the fetch resolves. Let me think about why this fails.

My first thought was that the transaction object expires or gets garbage collected. But actually, the issue is more subtle: IndexedDB transactions auto-commit when there are no pending IDB requests in the current microtask. When the code calls `fetch()`, that starts an asynchronous operation that returns a Promise. The `.then()` callback runs in a LATER microtask. Between the `onsuccess` callback finishing and the `.then()` callback running, the transaction sees zero pending IDB requests and auto-commits.

Wait, but why would the transaction commit just because there are no pending requests? Could it not stay open until explicitly committed? Actually no -- IndexedDB was designed this way intentionally. Transactions auto-commit to prevent holding database locks indefinitely. If a transaction stayed open across async boundaries, a slow network request could block all other IDB operations.

Hmm, but this means you cannot mix IDB transactions with ANY async operation -- no fetch, no setTimeout, no await, no reading from another async source. That severely limits what you can do inside a transaction.

I initially considered using `Promise.resolve().then()` to chain IDB operations, thinking microtask-level chaining would keep the transaction alive. But even microtask boundaries can close the transaction if no IDB requests are pending during the gap. The only safe pattern is to have continuously pending IDB requests with no async gaps between them.

The fix is to restructure the code: do ALL async work (fetch, etc.) BEFORE starting the transaction, then do all IDB operations synchronously within the transaction scope. Alternatively, split into separate transactions -- first transaction saves the user, then fetch the validation data, then a second transaction saves the order. The tradeoff is losing atomicity across the two transactions.
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
CSP debugging. The user is getting two violations: one for inline scripts and one for images from a CDN. Let me think about the systematic approach.

My first instinct is to add `'unsafe-inline'` for scripts and the CDN URL for images. But wait -- `'unsafe-inline'` defeats the entire purpose of CSP for scripts, since XSS attacks inject inline scripts. That is like disabling the lock because the key is inconvenient.

Could I use hashes instead? I can compute the hash of each inline script and add it to the CSP. But that breaks whenever the inline script changes, which makes it fragile for dynamic content. Hmm, what about nonces? A nonce is a random value generated per-request: `script-src 'nonce-abc123'`. Each inline script gets a `nonce="abc123"` attribute. Since the nonce is random and changes every page load, an attacker cannot predict it, so injected scripts are still blocked. That is the right approach for inline scripts.

But there is a deployment challenge: how do I test a CSP without breaking the live site? If I set a strict policy and forget to allow a legitimate resource, users see a broken page. The answer is `Content-Security-Policy-Report-Only` -- it logs violations without blocking anything. I can deploy in report-only mode, collect violations for a week, build the allow-list from the reports, then switch to enforcing mode.

I initially thought building the CSP would be a one-time task, but actually it requires ongoing maintenance. Adding a new CDN, embedding a third-party widget, or changing analytics providers all require CSP updates. The `report-uri` directive should stay in the enforcing policy to catch regressions.

The systematic approach: start strict (default-src 'self'), deploy in report-only mode, analyze violations, add exceptions, use nonces for inline scripts, switch to enforcing, keep monitoring.
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
