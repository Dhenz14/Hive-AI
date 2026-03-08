"""
batch_p1342_js_deep2.py — 25 deep JavaScript/TypeScript training pairs.
Topics: browser APIs, design patterns, performance, security, modern JS features.
"""

PAIRS = [
    # ── 01-05: Browser & Web APIs ──────────────────────────────────────

    ("js_deep2_01", r'''Implement a lazy-loading image component using IntersectionObserver that supports placeholder blur-up, error fallbacks, and priority loading for above-the-fold images.''',
     r'''<think>
IntersectionObserver is the modern way to detect visibility. Key design points:
1. Observe each image element — load src only when it enters the viewport.
2. Blur-up effect: show a tiny base64 placeholder, crossfade to full image.
3. Priority: above-the-fold images should load immediately (skip observer).
4. Error fallback: if image fails to load, show a fallback image or colored div.
5. Unobserve after loading to prevent memory leaks.
6. rootMargin: start loading slightly before the image enters viewport.
7. Use data attributes for deferred src to prevent eager loading.
8. Consider native loading="lazy" as progressive enhancement.
</think>

```typescript
interface LazyImageOptions {
  rootMargin?: string;
  threshold?: number;
  placeholderColor?: string;
  fallbackSrc?: string;
  onLoad?: (img: HTMLImageElement) => void;
  onError?: (img: HTMLImageElement, error: Event) => void;
}

class LazyImageLoader {
  private observer: IntersectionObserver;
  private loadedImages = new WeakSet<HTMLImageElement>();
  private opts: Required<LazyImageOptions>;

  constructor(options: LazyImageOptions = {}) {
    this.opts = {
      rootMargin: "200px 0px",  // Start loading 200px before viewport
      threshold: 0.01,
      placeholderColor: "#e0e0e0",
      fallbackSrc: "",
      onLoad: () => {},
      onError: () => {},
      ...options,
    };

    this.observer = new IntersectionObserver(
      (entries) => this.handleIntersection(entries),
      {
        rootMargin: this.opts.rootMargin,
        threshold: this.opts.threshold,
      }
    );
  }

  observe(img: HTMLImageElement): void {
    const src = img.dataset.src;
    if (!src) return;

    // Priority images (above the fold) — load immediately
    if (img.dataset.priority === "high") {
      this.loadImage(img, src);
      return;
    }

    // Apply placeholder
    const placeholder = img.dataset.placeholder;
    if (placeholder) {
      img.src = placeholder;  // Tiny base64 blur
      img.style.filter = "blur(10px)";
      img.style.transition = "filter 0.3s ease-out";
    } else {
      img.style.backgroundColor = this.opts.placeholderColor;
    }

    this.observer.observe(img);
  }

  private handleIntersection(entries: IntersectionObserverEntry[]): void {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;

      const img = entry.target as HTMLImageElement;
      const src = img.dataset.src;
      if (!src || this.loadedImages.has(img)) continue;

      this.loadImage(img, src);
      this.observer.unobserve(img);
    }
  }

  private loadImage(img: HTMLImageElement, src: string): void {
    // Create a temporary image to preload
    const tempImg = new Image();

    tempImg.onload = () => {
      img.src = src;
      img.style.filter = "";  // Remove blur
      img.removeAttribute("data-src");
      this.loadedImages.add(img);
      this.opts.onLoad(img);
    };

    tempImg.onerror = (e) => {
      if (this.opts.fallbackSrc) {
        img.src = this.opts.fallbackSrc;
      }
      img.style.filter = "";
      this.opts.onError(img, e as Event);
    };

    tempImg.src = src;
  }

  observeAll(selector: string = "img[data-src]"): void {
    document.querySelectorAll<HTMLImageElement>(selector).forEach(
      (img) => this.observe(img)
    );
  }

  disconnect(): void {
    this.observer.disconnect();
  }
}
```

**Usage:**

```html
<!-- Lazy image with blur-up placeholder -->
<img
  data-src="/photos/landscape.jpg"
  data-placeholder="data:image/jpeg;base64,/9j/4AAQSkZ..."
  alt="Landscape"
  width="800"
  height="600"
/>

<!-- Priority image (loads immediately) -->
<img
  data-src="/photos/hero.jpg"
  data-priority="high"
  alt="Hero"
/>
```

```typescript
const loader = new LazyImageLoader({
  rootMargin: "300px 0px",
  fallbackSrc: "/images/placeholder.svg",
  onLoad: (img) => img.classList.add("loaded"),
});

loader.observeAll();

// For dynamically added images
const newImg = document.createElement("img");
newImg.dataset.src = "/photos/new.jpg";
loader.observe(newImg);
```

The blur-up technique (pioneered by Medium) works by loading a tiny ~1KB base64 image as placeholder, applying CSS blur, then crossfading to the full image. Users see content shape immediately, with the full image loading smoothly in.'''),

    ("js_deep2_02", r'''Implement a Service Worker that provides offline-first caching with these strategies: cache-first for static assets, network-first for API calls, and stale-while-revalidate for images. Include a cache versioning/cleanup system.''',
     r'''<think>
Service Workers are the foundation of PWAs. Strategy breakdown:
1. Cache-first: check cache, return if found, else network (good for static assets that rarely change).
2. Network-first: try network, fall back to cache (good for API calls that should be fresh).
3. Stale-while-revalidate: return cached immediately, fetch in background to update (good for images).
4. Cache versioning: use a CACHE_VERSION constant. On activate, delete old caches.
5. Precaching: during install, cache essential shell assets.
6. Route matching: use URL patterns to determine which strategy to use.
7. Background sync: queue failed POST requests for retry when online.
8. Must handle cache storage limits gracefully.
</think>

```typescript
// sw.ts — Service Worker

const CACHE_VERSION = "v3";
const STATIC_CACHE = `static-${CACHE_VERSION}`;
const API_CACHE = `api-${CACHE_VERSION}`;
const IMAGE_CACHE = `images-${CACHE_VERSION}`;

const PRECACHE_URLS = [
  "/",
  "/index.html",
  "/styles/app.css",
  "/scripts/app.js",
  "/offline.html",
];

// ── Install: precache static assets ──
self.addEventListener("install", (event: ExtendableEvent) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => cache.addAll(PRECACHE_URLS))
  );
  (self as any).skipWaiting();  // Activate immediately
});

// ── Activate: clean old caches ──
self.addEventListener("activate", (event: ExtendableEvent) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names
          .filter((name) => !name.endsWith(CACHE_VERSION))
          .map((name) => {
            console.log(`[SW] Deleting old cache: ${name}`);
            return caches.delete(name);
          })
      )
    )
  );
  (self as any).clients.claim();  // Control all open tabs
});

// ── Fetch: route to strategy ──
self.addEventListener("fetch", (event: FetchEvent) => {
  const url = new URL(event.request.url);

  // Skip non-GET requests
  if (event.request.method !== "GET") return;

  // API calls → network-first
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(networkFirst(event.request, API_CACHE));
    return;
  }

  // Images → stale-while-revalidate
  if (
    url.pathname.match(/\.(jpg|jpeg|png|gif|webp|svg)$/i) ||
    url.pathname.startsWith("/images/")
  ) {
    event.respondWith(staleWhileRevalidate(event.request, IMAGE_CACHE));
    return;
  }

  // Everything else → cache-first
  event.respondWith(cacheFirst(event.request, STATIC_CACHE));
});

// ── Strategies ──

async function cacheFirst(request: Request, cacheName: string): Promise<Response> {
  const cached = await caches.match(request);
  if (cached) return cached;

  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    // Offline fallback for navigation requests
    if (request.mode === "navigate") {
      const fallback = await caches.match("/offline.html");
      if (fallback) return fallback;
    }
    return new Response("Offline", { status: 503 });
  }
}

async function networkFirst(request: Request, cacheName: string): Promise<Response> {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(cacheName);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response(
      JSON.stringify({ error: "offline", cached: false }),
      { status: 503, headers: { "Content-Type": "application/json" } }
    );
  }
}

async function staleWhileRevalidate(
  request: Request,
  cacheName: string
): Promise<Response> {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);

  // Revalidate in background regardless
  const fetchPromise = fetch(request)
    .then((response) => {
      if (response.ok) {
        cache.put(request, response.clone());
        // Trim cache if too large
        trimCache(cacheName, 100);
      }
      return response;
    })
    .catch(() => cached ?? new Response("", { status: 503 }));

  // Return cached immediately, or wait for network
  return cached ?? fetchPromise;
}

// ── Cache size management ──
async function trimCache(cacheName: string, maxItems: number): Promise<void> {
  const cache = await caches.open(cacheName);
  const keys = await cache.keys();
  if (keys.length <= maxItems) return;

  // Delete oldest entries (FIFO)
  const toDelete = keys.slice(0, keys.length - maxItems);
  await Promise.all(toDelete.map((key) => cache.delete(key)));
}
```

**Registration from main app:**

```typescript
if ("serviceWorker" in navigator) {
  window.addEventListener("load", async () => {
    try {
      const reg = await navigator.serviceWorker.register("/sw.js");
      console.log("SW registered:", reg.scope);

      // Listen for updates
      reg.addEventListener("updatefound", () => {
        const newWorker = reg.installing;
        newWorker?.addEventListener("statechange", () => {
          if (newWorker.state === "activated") {
            // Notify user about update
            showUpdateBanner();
          }
        });
      });
    } catch (err) {
      console.error("SW registration failed:", err);
    }
  });
}
```

**Strategy summary:**
- **Cache-first** (static assets): fastest, uses network only on cache miss. Version cache to bust stale assets.
- **Network-first** (APIs): always fresh when online, falls back to cached when offline.
- **Stale-while-revalidate** (images): instant response from cache, updates in background. Best user experience for content that changes slowly.'''),

    ("js_deep2_03", r'''Build a virtual DOM diffing algorithm in TypeScript. Implement createElement, diff, and patch functions that can efficiently update the real DOM based on virtual DOM changes.''',
     r'''<think>
Virtual DOM is the core of React. The algorithm:
1. VNode: plain object representing a DOM element { type, props, children }.
2. createElement: convert VNode tree to real DOM nodes.
3. diff: compare old VNode tree with new, produce a patch list.
4. patch: apply patches to real DOM efficiently.
5. Diff algorithm key points:
   - Same type: update props, recurse children.
   - Different type: replace entire subtree.
   - Text nodes: just update textContent.
   - Children: keyed diffing for reorder optimization.
6. Keep it simple but correct — skip fiber reconciler complexity.
7. Handle: add/remove/replace/update props, add/remove/reorder children.
8. Event handlers: attach as properties (onclick), not addEventListener.
</think>

```typescript
// ── Virtual Node Types ──

interface VElement {
  type: string;
  props: Record<string, any>;
  children: VNode[];
  key?: string;
}

type VNode = VElement | string | number | null;

function h(
  type: string,
  props: Record<string, any> | null,
  ...children: VNode[]
): VElement {
  return {
    type,
    props: props ?? {},
    children: children.flat().filter((c) => c != null),
    key: props?.key,
  };
}

// ── Create real DOM from VNode ──

function createElement(vnode: VNode): Node {
  if (vnode == null) return document.createComment("null");
  if (typeof vnode === "string" || typeof vnode === "number") {
    return document.createTextNode(String(vnode));
  }

  const el = document.createElement(vnode.type);

  // Set props
  for (const [key, value] of Object.entries(vnode.props)) {
    if (key === "key") continue;
    setProp(el, key, value);
  }

  // Append children
  for (const child of vnode.children) {
    el.appendChild(createElement(child));
  }

  return el;
}

function setProp(el: HTMLElement, key: string, value: any): void {
  if (key.startsWith("on")) {
    const event = key.slice(2).toLowerCase();
    (el as any)[`__${event}`] = value;  // Store for comparison
    el.addEventListener(event, value);
  } else if (key === "className") {
    el.className = value ?? "";
  } else if (key === "style" && typeof value === "object") {
    Object.assign(el.style, value);
  } else if (typeof value === "boolean") {
    if (value) el.setAttribute(key, "");
    else el.removeAttribute(key);
  } else {
    el.setAttribute(key, String(value));
  }
}

function removeProp(el: HTMLElement, key: string, value: any): void {
  if (key.startsWith("on")) {
    const event = key.slice(2).toLowerCase();
    el.removeEventListener(event, value);
    delete (el as any)[`__${event}`];
  } else if (key === "className") {
    el.className = "";
  } else {
    el.removeAttribute(key);
  }
}

// ── Diff + Patch ──

function patch(parent: Node, oldVNode: VNode, newVNode: VNode, index = 0): void {
  const el = parent.childNodes[index];

  // New node added
  if (oldVNode == null) {
    parent.appendChild(createElement(newVNode));
    return;
  }

  // Node removed
  if (newVNode == null) {
    parent.removeChild(el);
    return;
  }

  // Text node changed
  if (typeof oldVNode !== "object" || typeof newVNode !== "object") {
    if (oldVNode !== newVNode) {
      parent.replaceChild(createElement(newVNode), el);
    }
    return;
  }

  // Different element type — replace entire subtree
  if (oldVNode.type !== newVNode.type) {
    parent.replaceChild(createElement(newVNode), el);
    return;
  }

  // Same type — diff props and children
  patchProps(el as HTMLElement, oldVNode.props, newVNode.props);
  patchChildren(el, oldVNode.children, newVNode.children);
}

function patchProps(
  el: HTMLElement,
  oldProps: Record<string, any>,
  newProps: Record<string, any>
): void {
  const allProps = new Set([...Object.keys(oldProps), ...Object.keys(newProps)]);

  for (const key of allProps) {
    if (key === "key") continue;
    const oldVal = oldProps[key];
    const newVal = newProps[key];

    if (newVal === undefined) {
      removeProp(el, key, oldVal);
    } else if (oldVal !== newVal) {
      if (key.startsWith("on")) {
        if (oldVal) removeProp(el, key, oldVal);
      }
      setProp(el, key, newVal);
    }
  }
}

function patchChildren(
  parent: Node,
  oldChildren: VNode[],
  newChildren: VNode[]
): void {
  const maxLen = Math.max(oldChildren.length, newChildren.length);

  // Process from end to avoid index shifting issues on removal
  for (let i = maxLen - 1; i >= 0; i--) {
    patch(parent, oldChildren[i] ?? null, newChildren[i] ?? null, i);
  }
}
```

**Usage:**

```typescript
// JSX-like syntax using h()
let vdom = h("div", { className: "app" },
  h("h1", null, "Counter"),
  h("p", { id: "count" }, "Count: 0"),
  h("button", { onClick: () => increment() }, "Click me")
);

// Mount
const root = document.getElementById("root")!;
root.appendChild(createElement(vdom));

// Update
function increment() {
  const newVdom = h("div", { className: "app" },
    h("h1", null, "Counter"),
    h("p", { id: "count", style: { color: "blue" } }, "Count: 1"),
    h("button", { onClick: () => increment() }, "Click me")
  );

  patch(root, vdom, newVdom, 0);
  vdom = newVdom;
}
```

This simplified VDOM shows the core algorithm behind React, Preact, and Vue. Production implementations add keyed reconciliation (for list reordering), batched updates, and fiber-based scheduling.'''),

    ("js_deep2_04", r'''Implement IndexedDB wrapper in TypeScript with a clean async API, schema migrations, and type-safe CRUD operations. Handle the complexity of IndexedDB's event-based API.''',
     r'''<think>
IndexedDB is powerful but has a terrible API — event-based, no Promises. Key design:
1. Wrap IDBRequest/IDBTransaction in Promises for async/await.
2. Schema versioning with upgrade callbacks (like SQL migrations).
3. Type-safe: generics for store types, key paths.
4. CRUD: get, getAll, put, delete, clear, query by index.
5. Transaction management: auto-create transactions for simple operations.
6. Cursor support for large datasets.
7. Error handling: transaction failures, version conflicts.
8. Keep the API surface minimal — don't over-abstract.
</think>

```typescript
interface StoreSchema {
  name: string;
  keyPath: string;
  autoIncrement?: boolean;
  indexes?: Array<{
    name: string;
    keyPath: string | string[];
    unique?: boolean;
  }>;
}

interface Migration {
  version: number;
  stores: StoreSchema[];
}

class IndexedDBWrapper {
  private db: IDBDatabase | null = null;
  private dbName: string;
  private migrations: Migration[];

  constructor(dbName: string, migrations: Migration[]) {
    this.dbName = dbName;
    this.migrations = migrations.sort((a, b) => a.version - b.version);
  }

  async open(): Promise<void> {
    const latestVersion = this.migrations[this.migrations.length - 1]?.version ?? 1;

    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, latestVersion);

      request.onupgradeneeded = (event) => {
        const db = request.result;
        const oldVersion = event.oldVersion;

        for (const migration of this.migrations) {
          if (migration.version <= oldVersion) continue;

          for (const schema of migration.stores) {
            // Create store if it doesn't exist
            let store: IDBObjectStore;
            if (!db.objectStoreNames.contains(schema.name)) {
              store = db.createObjectStore(schema.name, {
                keyPath: schema.keyPath,
                autoIncrement: schema.autoIncrement,
              });
            } else {
              store = request.transaction!.objectStore(schema.name);
            }

            // Create indexes
            for (const idx of schema.indexes ?? []) {
              if (!store.indexNames.contains(idx.name)) {
                store.createIndex(idx.name, idx.keyPath, {
                  unique: idx.unique ?? false,
                });
              }
            }
          }
        }
      };

      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onerror = () => reject(request.error);
    });
  }

  private getDB(): IDBDatabase {
    if (!this.db) throw new Error("Database not opened. Call open() first.");
    return this.db;
  }

  private promisify<T>(request: IDBRequest<T>): Promise<T> {
    return new Promise((resolve, reject) => {
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async get<T>(storeName: string, key: IDBValidKey): Promise<T | undefined> {
    const db = this.getDB();
    const tx = db.transaction(storeName, "readonly");
    const store = tx.objectStore(storeName);
    return this.promisify<T>(store.get(key));
  }

  async getAll<T>(storeName: string): Promise<T[]> {
    const db = this.getDB();
    const tx = db.transaction(storeName, "readonly");
    const store = tx.objectStore(storeName);
    return this.promisify<T[]>(store.getAll());
  }

  async put<T>(storeName: string, value: T): Promise<IDBValidKey> {
    const db = this.getDB();
    const tx = db.transaction(storeName, "readwrite");
    const store = tx.objectStore(storeName);
    return this.promisify(store.put(value));
  }

  async putMany<T>(storeName: string, values: T[]): Promise<void> {
    const db = this.getDB();
    const tx = db.transaction(storeName, "readwrite");
    const store = tx.objectStore(storeName);

    for (const value of values) {
      store.put(value);
    }

    return new Promise((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async delete(storeName: string, key: IDBValidKey): Promise<void> {
    const db = this.getDB();
    const tx = db.transaction(storeName, "readwrite");
    const store = tx.objectStore(storeName);
    await this.promisify(store.delete(key));
  }

  async queryByIndex<T>(
    storeName: string,
    indexName: string,
    query: IDBValidKey | IDBKeyRange
  ): Promise<T[]> {
    const db = this.getDB();
    const tx = db.transaction(storeName, "readonly");
    const store = tx.objectStore(storeName);
    const index = store.index(indexName);
    return this.promisify<T[]>(index.getAll(query));
  }

  async clear(storeName: string): Promise<void> {
    const db = this.getDB();
    const tx = db.transaction(storeName, "readwrite");
    const store = tx.objectStore(storeName);
    await this.promisify(store.clear());
  }

  async count(storeName: string): Promise<number> {
    const db = this.getDB();
    const tx = db.transaction(storeName, "readonly");
    const store = tx.objectStore(storeName);
    return this.promisify(store.count());
  }

  close(): void {
    this.db?.close();
    this.db = null;
  }
}
```

**Usage:**

```typescript
interface User {
  id: string;
  name: string;
  email: string;
  role: "admin" | "user";
  createdAt: number;
}

const db = new IndexedDBWrapper("myapp", [
  {
    version: 1,
    stores: [{
      name: "users",
      keyPath: "id",
      indexes: [
        { name: "by_email", keyPath: "email", unique: true },
        { name: "by_role", keyPath: "role" },
      ],
    }],
  },
  {
    version: 2,
    stores: [{
      name: "users",
      keyPath: "id",
      indexes: [
        { name: "by_email", keyPath: "email", unique: true },
        { name: "by_role", keyPath: "role" },
        { name: "by_created", keyPath: "createdAt" },  // New index in v2
      ],
    }],
  },
]);

await db.open();

// CRUD
await db.put<User>("users", { id: "1", name: "Alice", email: "alice@example.com", role: "admin", createdAt: Date.now() });
const user = await db.get<User>("users", "1");
const admins = await db.queryByIndex<User>("users", "by_role", "admin");

// Range query
const recent = await db.queryByIndex<User>(
  "users", "by_created",
  IDBKeyRange.lowerBound(Date.now() - 86400000)  // Last 24h
);
```

This wrapper turns IndexedDB's callback nightmare into clean async/await while preserving the full power of indexes, transactions, and migrations.'''),

    ("js_deep2_05", r'''Implement a Web Worker communication system in TypeScript with typed messages, request/response pattern (RPC), transferable objects, and proper error handling.''',
     r'''<think>
Web Workers for off-main-thread computation. The challenge is typed communication:
1. postMessage is untyped — need to define a message protocol.
2. RPC pattern: main sends request with ID, worker responds with same ID.
3. Transferable objects: ArrayBuffer, OffscreenCanvas — zero-copy transfer.
4. Error handling: worker errors should propagate to the caller's promise.
5. TypeScript: define the RPC method signatures, infer request/response types.
6. Timeout: requests should fail if worker doesn't respond.
7. Multiple concurrent requests: track by unique ID.
8. Consider SharedArrayBuffer for shared state.
</think>

```typescript
// ── Shared types (used by both main and worker) ──

interface WorkerMethods {
  processImage: { params: { data: ArrayBuffer; width: number; height: number }; result: ArrayBuffer };
  fibonacci: { params: { n: number }; result: number };
  parseCSV: { params: { csv: string }; result: Record<string, string>[] };
}

interface RPCRequest<K extends keyof WorkerMethods = keyof WorkerMethods> {
  type: "rpc_request";
  id: string;
  method: K;
  params: WorkerMethods[K]["params"];
}

interface RPCResponse<K extends keyof WorkerMethods = keyof WorkerMethods> {
  type: "rpc_response";
  id: string;
  result?: WorkerMethods[K]["result"];
  error?: string;
}

// ── Main thread: RPC Client ──

class WorkerRPC {
  private worker: Worker;
  private pending = new Map<string, {
    resolve: (value: any) => void;
    reject: (error: Error) => void;
    timer: ReturnType<typeof setTimeout>;
  }>();
  private idCounter = 0;

  constructor(workerUrl: string | URL) {
    this.worker = new Worker(workerUrl, { type: "module" });

    this.worker.onmessage = (event: MessageEvent<RPCResponse>) => {
      const { id, result, error } = event.data;
      const pending = this.pending.get(id);
      if (!pending) return;

      clearTimeout(pending.timer);
      this.pending.delete(id);

      if (error) {
        pending.reject(new Error(error));
      } else {
        pending.resolve(result);
      }
    };

    this.worker.onerror = (err) => {
      // Reject all pending requests
      for (const [id, { reject, timer }] of this.pending) {
        clearTimeout(timer);
        reject(new Error(`Worker error: ${err.message}`));
      }
      this.pending.clear();
    };
  }

  call<K extends keyof WorkerMethods>(
    method: K,
    params: WorkerMethods[K]["params"],
    options: { timeout?: number; transfer?: Transferable[] } = {}
  ): Promise<WorkerMethods[K]["result"]> {
    const { timeout = 30_000, transfer = [] } = options;
    const id = `rpc_${this.idCounter++}`;

    return new Promise((resolve, reject) => {
      const timer = setTimeout(() => {
        this.pending.delete(id);
        reject(new Error(`RPC timeout: ${method} after ${timeout}ms`));
      }, timeout);

      this.pending.set(id, { resolve, reject, timer });

      const message: RPCRequest<K> = { type: "rpc_request", id, method, params };
      this.worker.postMessage(message, transfer);
    });
  }

  terminate(): void {
    for (const { reject, timer } of this.pending.values()) {
      clearTimeout(timer);
      reject(new Error("Worker terminated"));
    }
    this.pending.clear();
    this.worker.terminate();
  }
}

// ── Worker thread: RPC Server ──
// worker.ts

type MethodHandler<K extends keyof WorkerMethods> = (
  params: WorkerMethods[K]["params"]
) => WorkerMethods[K]["result"] | Promise<WorkerMethods[K]["result"]>;

const handlers: { [K in keyof WorkerMethods]?: MethodHandler<K> } = {};

function registerMethod<K extends keyof WorkerMethods>(
  method: K,
  handler: MethodHandler<K>
): void {
  handlers[method] = handler as any;
}

self.onmessage = async (event: MessageEvent<RPCRequest>) => {
  const { id, method, params } = event.data;
  const handler = handlers[method];

  if (!handler) {
    self.postMessage({ type: "rpc_response", id, error: `Unknown method: ${method}` });
    return;
  }

  try {
    const result = await handler(params as any);

    // Auto-detect transferable objects
    const transfer: Transferable[] = [];
    if (result instanceof ArrayBuffer) transfer.push(result);

    self.postMessage({ type: "rpc_response", id, result } as RPCResponse, transfer);
  } catch (err: any) {
    self.postMessage({ type: "rpc_response", id, error: err.message } as RPCResponse);
  }
};

// Register handlers
registerMethod("fibonacci", ({ n }) => {
  function fib(n: number): number {
    if (n <= 1) return n;
    let a = 0, b = 1;
    for (let i = 2; i <= n; i++) [a, b] = [b, a + b];
    return b;
  }
  return fib(n);
});

registerMethod("processImage", ({ data, width, height }) => {
  const pixels = new Uint8ClampedArray(data);
  // Grayscale conversion (CPU-intensive)
  for (let i = 0; i < pixels.length; i += 4) {
    const gray = pixels[i] * 0.299 + pixels[i + 1] * 0.587 + pixels[i + 2] * 0.114;
    pixels[i] = pixels[i + 1] = pixels[i + 2] = gray;
  }
  return pixels.buffer;  // Transfer back (zero-copy)
});
```

**Usage from main thread:**

```typescript
const worker = new WorkerRPC(new URL("./worker.ts", import.meta.url));

// Type-safe RPC calls
const fib = await worker.call("fibonacci", { n: 42 });
//    ^? number

// Transfer ArrayBuffer (zero-copy, main thread loses access)
const imageData = canvas.getContext("2d")!.getImageData(0, 0, 800, 600);
const processed = await worker.call(
  "processImage",
  { data: imageData.data.buffer, width: 800, height: 600 },
  { transfer: [imageData.data.buffer] }
);
```

The RPC pattern transforms Web Workers from fire-and-forget messaging into a clean async function call interface. Transferable objects ensure large data (images, buffers) moves between threads without copying.'''),

    # ── 06-10: Design Patterns in JavaScript ────────────────────────────

    ("js_deep2_06", r'''Implement the Builder pattern in TypeScript for constructing complex objects. Create a type-safe SQL query builder that prevents invalid query construction at compile time.''',
     r'''<think>
The Builder pattern is great for constructing objects step by step. For SQL:
1. Method chaining: each method returns the builder for fluent API.
2. Type safety: can't call .where() before .from(), can't call .having() without .groupBy().
3. Use TypeScript's type system to enforce valid query sequences.
4. Parameterized queries to prevent SQL injection.
5. Support: SELECT, FROM, WHERE, JOIN, GROUP BY, HAVING, ORDER BY, LIMIT.
6. The key trick: each builder method returns a NEW type that has the next valid methods.
7. This is the "phantom type" or "state machine" pattern in TypeScript.
</think>

```typescript
// Parameter collector for safe SQL
interface QueryParams {
  text: string;
  values: unknown[];
}

// Builder state tracking via type parameters
class QueryBuilder<HasFrom extends boolean = false, HasGroupBy extends boolean = false> {
  private parts = {
    select: [] as string[],
    from: "",
    joins: [] as string[],
    where: [] as string[],
    groupBy: [] as string[],
    having: [] as string[],
    orderBy: [] as string[],
    limit: 0,
    offset: 0,
    params: [] as unknown[],
  };

  private paramIndex = 0;

  private param(value: unknown): string {
    this.parts.params.push(value);
    return `$${++this.paramIndex}`;
  }

  select(...columns: string[]): this {
    this.parts.select.push(...columns);
    return this;
  }

  from(table: string): QueryBuilder<true, HasGroupBy> {
    this.parts.from = table;
    return this as any;
  }

  // WHERE only available after FROM
  where(this: QueryBuilder<true, any>, condition: string, ...values: unknown[]): this {
    const parameterized = values.reduce<string>(
      (cond, val) => cond.replace("?", this.param(val)),
      condition
    );
    this.parts.where.push(parameterized);
    return this;
  }

  join(this: QueryBuilder<true, any>, table: string, on: string): this {
    this.parts.joins.push(`JOIN ${table} ON ${on}`);
    return this;
  }

  leftJoin(this: QueryBuilder<true, any>, table: string, on: string): this {
    this.parts.joins.push(`LEFT JOIN ${table} ON ${on}`);
    return this;
  }

  groupBy(this: QueryBuilder<true, any>, ...columns: string[]): QueryBuilder<true, true> {
    this.parts.groupBy.push(...columns);
    return this as any;
  }

  // HAVING only available after GROUP BY
  having(this: QueryBuilder<true, true>, condition: string, ...values: unknown[]): this {
    const parameterized = values.reduce<string>(
      (cond, val) => cond.replace("?", this.param(val)),
      condition
    );
    this.parts.having.push(parameterized);
    return this;
  }

  orderBy(this: QueryBuilder<true, any>, column: string, direction: "ASC" | "DESC" = "ASC"): this {
    this.parts.orderBy.push(`${column} ${direction}`);
    return this;
  }

  limit(this: QueryBuilder<true, any>, n: number): this {
    this.parts.limit = n;
    return this;
  }

  offset(this: QueryBuilder<true, any>, n: number): this {
    this.parts.offset = n;
    return this;
  }

  build(this: QueryBuilder<true, any>): QueryParams {
    const parts: string[] = [];

    parts.push(`SELECT ${this.parts.select.length ? this.parts.select.join(", ") : "*"}`);
    parts.push(`FROM ${this.parts.from}`);

    for (const join of this.parts.joins) parts.push(join);
    if (this.parts.where.length) parts.push(`WHERE ${this.parts.where.join(" AND ")}`);
    if (this.parts.groupBy.length) parts.push(`GROUP BY ${this.parts.groupBy.join(", ")}`);
    if (this.parts.having.length) parts.push(`HAVING ${this.parts.having.join(" AND ")}`);
    if (this.parts.orderBy.length) parts.push(`ORDER BY ${this.parts.orderBy.join(", ")}`);
    if (this.parts.limit) parts.push(`LIMIT ${this.parts.limit}`);
    if (this.parts.offset) parts.push(`OFFSET ${this.parts.offset}`);

    return { text: parts.join("\n"), values: this.parts.params };
  }
}

function query(): QueryBuilder {
  return new QueryBuilder();
}
```

**Usage:**

```typescript
// Valid query — full type safety
const q = query()
  .select("u.name", "COUNT(o.id) as order_count")
  .from("users u")
  .leftJoin("orders o", "o.user_id = u.id")
  .where("u.active = ?", true)
  .where("u.created_at > ?", "2024-01-01")
  .groupBy("u.id", "u.name")
  .having("COUNT(o.id) > ?", 5)
  .orderBy("order_count", "DESC")
  .limit(10)
  .build();

// q.text:
// SELECT u.name, COUNT(o.id) as order_count
// FROM users u
// LEFT JOIN orders o ON o.user_id = u.id
// WHERE u.active = $1 AND u.created_at > $2
// GROUP BY u.id, u.name
// HAVING COUNT(o.id) > $3
// ORDER BY order_count DESC
// LIMIT 10
//
// q.values: [true, "2024-01-01", 5]

// COMPILE ERRORS:
query().where("x = 1");        // Error: where needs FROM first
query().from("t").having("x"); // Error: having needs GROUP BY first
query().build();               // Error: build needs FROM first
```

Parameterized values (`$1`, `$2`) prevent SQL injection — values are never interpolated into the query string.'''),

    ("js_deep2_07", r'''Implement the Observer pattern in TypeScript with a typed EventBus that supports: wildcard listeners, event namespacing, once listeners, and memory leak detection for listeners that were never removed.''',
     r'''<think>
EventBus is a decoupled communication pattern. Key features:
1. Typed events with payload types.
2. Wildcard: listen to all events with `*`.
3. Namespacing: "user:login", "user:*" matches all user events.
4. Once: auto-remove after first invocation.
5. Memory leak detection: warn if listener count exceeds threshold.
6. Priority: higher priority handlers run first.
7. Return unsubscribe function for cleanup.
8. Consider WeakRef for listeners to help GC.
</think>

```typescript
type EventHandler<T = unknown> = (payload: T) => void;

interface ListenerEntry<T = unknown> {
  handler: EventHandler<T>;
  once: boolean;
  priority: number;
  stack?: string;  // Creation stack for leak detection
}

interface EventBusOptions {
  maxListeners?: number;
  leakWarning?: boolean;
  debug?: boolean;
}

class EventBus<Events extends Record<string, unknown> = Record<string, unknown>> {
  private listeners = new Map<string, ListenerEntry[]>();
  private wildcardListeners: ListenerEntry<{ event: string; payload: unknown }>[] = [];
  private opts: Required<EventBusOptions>;

  constructor(options: EventBusOptions = {}) {
    this.opts = {
      maxListeners: 20,
      leakWarning: true,
      debug: false,
      ...options,
    };
  }

  on<K extends keyof Events & string>(
    event: K,
    handler: EventHandler<Events[K]>,
    options: { priority?: number; once?: boolean } = {}
  ): () => void {
    const { priority = 0, once = false } = options;

    // Wildcard listener
    if (event === "*") {
      const entry: ListenerEntry<any> = {
        handler, once, priority,
        stack: this.opts.leakWarning ? new Error().stack : undefined,
      };
      this.wildcardListeners.push(entry);
      this.wildcardListeners.sort((a, b) => b.priority - a.priority);
      return () => {
        const idx = this.wildcardListeners.indexOf(entry);
        if (idx !== -1) this.wildcardListeners.splice(idx, 1);
      };
    }

    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    const list = this.listeners.get(event)!;

    // Leak detection
    if (this.opts.leakWarning && list.length >= this.opts.maxListeners) {
      console.warn(
        `EventBus: "${event}" has ${list.length + 1} listeners (max: ${this.opts.maxListeners}).` +
        ` Possible memory leak. Set maxListeners to suppress.`
      );
      // Log creation stacks
      for (const entry of list) {
        if (entry.stack) console.warn("  Registered at:", entry.stack.split("\n")[2]?.trim());
      }
    }

    const entry: ListenerEntry<Events[K]> = {
      handler, once, priority,
      stack: this.opts.leakWarning ? new Error().stack : undefined,
    };
    list.push(entry as ListenerEntry);
    list.sort((a, b) => b.priority - a.priority);

    // Return unsubscribe function
    return () => {
      const idx = list.indexOf(entry as ListenerEntry);
      if (idx !== -1) list.splice(idx, 1);
    };
  }

  once<K extends keyof Events & string>(
    event: K,
    handler: EventHandler<Events[K]>,
    priority = 0
  ): () => void {
    return this.on(event, handler, { once: true, priority });
  }

  emit<K extends keyof Events & string>(event: K, payload: Events[K]): void {
    if (this.opts.debug) console.log(`[EventBus] emit: ${event}`, payload);

    // Exact match listeners
    const list = this.listeners.get(event);
    if (list) {
      // Copy to avoid mutation during iteration (once removal)
      const snapshot = [...list];
      for (const entry of snapshot) {
        if (entry.once) {
          const idx = list.indexOf(entry);
          if (idx !== -1) list.splice(idx, 1);
        }
        try {
          entry.handler(payload);
        } catch (err) {
          console.error(`EventBus handler error on "${event}":`, err);
        }
      }
    }

    // Namespace wildcard: "user:*" matches "user:login", "user:logout"
    for (const [pattern, handlers] of this.listeners) {
      if (!pattern.endsWith(":*")) continue;
      const namespace = pattern.slice(0, -2);
      if (event.startsWith(namespace + ":") && event !== pattern) {
        for (const entry of [...handlers]) {
          if (entry.once) {
            const idx = handlers.indexOf(entry);
            if (idx !== -1) handlers.splice(idx, 1);
          }
          try {
            entry.handler(payload);
          } catch (err) {
            console.error(`EventBus namespace handler error:`, err);
          }
        }
      }
    }

    // Global wildcard listeners
    for (const entry of [...this.wildcardListeners]) {
      if (entry.once) {
        const idx = this.wildcardListeners.indexOf(entry);
        if (idx !== -1) this.wildcardListeners.splice(idx, 1);
      }
      try {
        (entry.handler as any)({ event, payload });
      } catch (err) {
        console.error(`EventBus wildcard handler error:`, err);
      }
    }
  }

  off<K extends keyof Events & string>(event: K, handler?: EventHandler<Events[K]>): void {
    if (!handler) {
      this.listeners.delete(event);
      return;
    }
    const list = this.listeners.get(event);
    if (!list) return;
    const idx = list.findIndex(e => e.handler === handler);
    if (idx !== -1) list.splice(idx, 1);
  }

  listenerCount(event?: string): number {
    if (event) return (this.listeners.get(event)?.length ?? 0);
    let total = this.wildcardListeners.length;
    for (const list of this.listeners.values()) total += list.length;
    return total;
  }

  removeAll(): void {
    this.listeners.clear();
    this.wildcardListeners = [];
  }
}
```

**Usage:**

```typescript
interface AppEvents {
  "user:login": { userId: string; timestamp: number };
  "user:logout": { userId: string };
  "notification:new": { title: string; body: string };
  "error": Error;
}

const bus = new EventBus<AppEvents>({ maxListeners: 10 });

// Regular listener with auto-cleanup
const unsub = bus.on("user:login", (data) => {
  console.log(`User ${data.userId} logged in`);
});

// Namespace wildcard — catches all "user:*" events
bus.on("user:*" as any, (data) => {
  console.log("User event:", data);
});

// Global wildcard — catches everything
bus.on("*" as any, ({ event, payload }) => {
  analytics.track(event, payload);
});

// Once listener
bus.once("notification:new", (n) => console.log("First notification:", n.title));

// Emit
bus.emit("user:login", { userId: "123", timestamp: Date.now() });

// Cleanup
unsub();
```'''),

    ("js_deep2_08", r'''Implement the Middleware pattern (like Express or Koa) as a reusable TypeScript library. Support async middleware, error handling middleware, and conditional middleware.''',
     r'''<think>
The middleware pattern is a pipeline where each step can:
1. Process the context object.
2. Call next() to pass to the next middleware.
3. Do work after next() returns (Koa-style onion model).
4. Skip remaining middleware by not calling next.
5. Handle errors thrown by downstream middleware.
6. Conditional execution based on context.
The onion model means middleware wraps around each other like layers.
</think>

```typescript
type Next = () => Promise<void>;
type Middleware<T> = (context: T, next: Next) => Promise<void> | void;
type ErrorMiddleware<T> = (error: Error, context: T, next: Next) => Promise<void> | void;
type Condition<T> = (context: T) => boolean;

class MiddlewarePipeline<T extends object> {
  private stack: Array<{
    handler: Middleware<T> | ErrorMiddleware<T>;
    isErrorHandler: boolean;
    condition?: Condition<T>;
    name?: string;
  }> = [];

  use(middleware: Middleware<T>, name?: string): this {
    this.stack.push({ handler: middleware, isErrorHandler: false, name });
    return this;
  }

  useIf(condition: Condition<T>, middleware: Middleware<T>): this {
    this.stack.push({ handler: middleware, isErrorHandler: false, condition });
    return this;
  }

  catch(handler: ErrorMiddleware<T>): this {
    this.stack.push({ handler, isErrorHandler: true });
    return this;
  }

  async execute(context: T): Promise<void> {
    let index = 0;
    let currentError: Error | null = null;

    const dispatch = async (i: number): Promise<void> => {
      if (i >= this.stack.length) {
        // If there's an unhandled error at the end, throw it
        if (currentError) throw currentError;
        return;
      }

      const entry = this.stack[i];
      index = i;

      try {
        if (currentError) {
          // In error state — skip normal middleware, run error handlers
          if (entry.isErrorHandler) {
            currentError = null;  // Error is being handled
            await (entry.handler as ErrorMiddleware<T>)(
              currentError!, context, () => dispatch(i + 1)
            );
          } else {
            // Skip normal middleware during error propagation
            await dispatch(i + 1);
          }
        } else {
          // Normal execution
          if (entry.isErrorHandler) {
            // Skip error handlers when no error
            await dispatch(i + 1);
            return;
          }

          // Check condition
          if (entry.condition && !entry.condition(context)) {
            await dispatch(i + 1);
            return;
          }

          // Run middleware with next() pointing to next in stack
          let nextCalled = false;
          await (entry.handler as Middleware<T>)(context, async () => {
            if (nextCalled) throw new Error("next() called multiple times");
            nextCalled = true;
            await dispatch(i + 1);
          });
        }
      } catch (err) {
        currentError = err instanceof Error ? err : new Error(String(err));
        // Continue dispatch to find error handlers
        await dispatch(i + 1);
      }
    };

    await dispatch(0);
  }

  // Compose multiple pipelines
  merge(other: MiddlewarePipeline<T>): this {
    this.stack.push(...other.stack);
    return this;
  }
}
```

**Usage — building an HTTP-like pipeline:**

```typescript
interface HttpContext {
  request: { method: string; path: string; headers: Record<string, string>; body?: unknown };
  response: { status: number; body: unknown; headers: Record<string, string> };
  state: Record<string, unknown>;
}

const pipeline = new MiddlewarePipeline<HttpContext>();

// Timing middleware (Koa-style onion — runs before AND after)
pipeline.use(async (ctx, next) => {
  const start = performance.now();
  await next();  // Run all downstream middleware
  const ms = (performance.now() - start).toFixed(1);
  ctx.response.headers["X-Response-Time"] = `${ms}ms`;
  console.log(`${ctx.request.method} ${ctx.request.path} - ${ms}ms`);
});

// Auth middleware (conditional — only for /api routes)
pipeline.useIf(
  (ctx) => ctx.request.path.startsWith("/api"),
  async (ctx, next) => {
    const token = ctx.request.headers["authorization"];
    if (!token) {
      ctx.response.status = 401;
      ctx.response.body = { error: "Unauthorized" };
      return;  // Don't call next — stops the pipeline
    }
    ctx.state.user = { id: "123", role: "admin" };
    await next();
  }
);

// Route handler
pipeline.use(async (ctx, next) => {
  if (ctx.request.path === "/api/users" && ctx.request.method === "GET") {
    ctx.response.status = 200;
    ctx.response.body = [{ id: "1", name: "Alice" }];
  } else {
    await next();
  }
});

// 404 handler
pipeline.use(async (ctx) => {
  ctx.response.status = 404;
  ctx.response.body = { error: "Not Found" };
});

// Error handler — catches errors from any middleware above
pipeline.catch(async (err, ctx, next) => {
  console.error("Pipeline error:", err);
  ctx.response.status = 500;
  ctx.response.body = { error: "Internal Server Error" };
});

// Execute
const ctx: HttpContext = {
  request: { method: "GET", path: "/api/users", headers: { authorization: "Bearer xyz" } },
  response: { status: 200, body: null, headers: {} },
  state: {},
};

await pipeline.execute(ctx);
console.log(ctx.response);
// { status: 200, body: [...], headers: { "X-Response-Time": "1.2ms" } }
```

The **onion model** means the timing middleware's code after `await next()` runs after all downstream middleware completes — giving it access to the final response for logging, timing, and cleanup.'''),

    ("js_deep2_09", r'''Implement the Command pattern in TypeScript with undo/redo support, command history, and macro commands (composite commands). Build a simple text editor as a demonstration.''',
     r'''<think>
Command pattern encapsulates operations as objects. Key parts:
1. Command interface: execute() and undo().
2. CommandHistory: stack-based undo/redo.
3. Macro commands: composite of multiple commands that execute/undo together.
4. Serialization: commands should be serializable for persistence.
5. For a text editor: InsertCommand, DeleteCommand, ReplaceCommand.
6. History limit to prevent unbounded memory growth.
7. Redo stack cleared when new commands are pushed after undo.
</think>

```typescript
// ── Command Interface ──
interface Command {
  execute(): void;
  undo(): void;
  description: string;
}

// ── Command History (Undo/Redo Manager) ──
class CommandHistory {
  private undoStack: Command[] = [];
  private redoStack: Command[] = [];
  private maxHistory: number;

  constructor(maxHistory = 100) {
    this.maxHistory = maxHistory;
  }

  execute(command: Command): void {
    command.execute();
    this.undoStack.push(command);
    this.redoStack = [];  // Clear redo on new action

    // Trim history
    if (this.undoStack.length > this.maxHistory) {
      this.undoStack.shift();
    }
  }

  undo(): string | null {
    const command = this.undoStack.pop();
    if (!command) return null;
    command.undo();
    this.redoStack.push(command);
    return command.description;
  }

  redo(): string | null {
    const command = this.redoStack.pop();
    if (!command) return null;
    command.execute();
    this.undoStack.push(command);
    return command.description;
  }

  get canUndo(): boolean { return this.undoStack.length > 0; }
  get canRedo(): boolean { return this.redoStack.length > 0; }

  get history(): string[] {
    return this.undoStack.map(c => c.description);
  }

  clear(): void {
    this.undoStack = [];
    this.redoStack = [];
  }
}

// ── Macro Command (Composite) ──
class MacroCommand implements Command {
  constructor(
    private commands: Command[],
    readonly description: string
  ) {}

  execute(): void {
    for (const cmd of this.commands) cmd.execute();
  }

  undo(): void {
    // Undo in reverse order
    for (let i = this.commands.length - 1; i >= 0; i--) {
      this.commands[i].undo();
    }
  }
}

// ── Text Editor Model ──
class TextDocument {
  private content: string[] = [""]; // Lines

  get text(): string { return this.content.join("\n"); }
  get lineCount(): number { return this.content.length; }

  getLine(line: number): string { return this.content[line] ?? ""; }

  insertAt(line: number, col: number, text: string): void {
    const current = this.content[line] ?? "";
    this.content[line] = current.slice(0, col) + text + current.slice(col);

    // Handle inserted newlines
    if (text.includes("\n")) {
      const parts = this.content[line].split("\n");
      this.content.splice(line, 1, ...parts);
    }
  }

  deleteRange(startLine: number, startCol: number, endLine: number, endCol: number): string {
    if (startLine === endLine) {
      const line = this.content[startLine];
      const deleted = line.slice(startCol, endCol);
      this.content[startLine] = line.slice(0, startCol) + line.slice(endCol);
      return deleted;
    }

    // Multi-line delete
    const firstPart = this.content[startLine].slice(0, startCol);
    const lastPart = this.content[endLine].slice(endCol);
    const deleted = this.content.slice(startLine, endLine + 1).join("\n")
      .slice(startCol, -(this.content[endLine].length - endCol) || undefined);
    this.content.splice(startLine, endLine - startLine + 1, firstPart + lastPart);
    return deleted;
  }
}

// ── Concrete Commands ──
class InsertCommand implements Command {
  constructor(
    private doc: TextDocument,
    private line: number,
    private col: number,
    private text: string
  ) {}

  get description() { return `Insert "${this.text.slice(0, 20)}"`; }

  execute(): void {
    this.doc.insertAt(this.line, this.col, this.text);
  }

  undo(): void {
    const endCol = this.col + this.text.length;
    this.doc.deleteRange(this.line, this.col, this.line, endCol);
  }
}

class DeleteCommand implements Command {
  private deletedText = "";

  constructor(
    private doc: TextDocument,
    private startLine: number,
    private startCol: number,
    private endLine: number,
    private endCol: number
  ) {}

  get description() { return `Delete "${this.deletedText.slice(0, 20)}"`; }

  execute(): void {
    this.deletedText = this.doc.deleteRange(
      this.startLine, this.startCol, this.endLine, this.endCol
    );
  }

  undo(): void {
    this.doc.insertAt(this.startLine, this.startCol, this.deletedText);
  }
}
```

**Usage:**

```typescript
const doc = new TextDocument();
const history = new CommandHistory();

// Type some text
history.execute(new InsertCommand(doc, 0, 0, "Hello, World!"));
console.log(doc.text);  // "Hello, World!"

history.execute(new InsertCommand(doc, 0, 13, "\nSecond line"));
console.log(doc.text);  // "Hello, World!\nSecond line"

// Delete some text
history.execute(new DeleteCommand(doc, 0, 5, 0, 7));
console.log(doc.text);  // "HelloWorld!\nSecond line"

// Undo
history.undo();
console.log(doc.text);  // "Hello, World!\nSecond line"

history.undo();
console.log(doc.text);  // "Hello, World!"

// Redo
history.redo();
console.log(doc.text);  // "Hello, World!\nSecond line"

// Macro: "Find and Replace" as a composite command
const findReplace = new MacroCommand([
  new DeleteCommand(doc, 0, 0, 0, 5),
  new InsertCommand(doc, 0, 0, "Goodbye"),
], "Replace 'Hello' with 'Goodbye'");

history.execute(findReplace);
console.log(doc.text);   // "Goodbye, World!\nSecond line"
history.undo();          // Undoes both delete and insert atomically
console.log(doc.text);   // "Hello, World!\nSecond line"
```

Every text editor (VS Code, Google Docs) uses this pattern. The Command object encapsulates both the action and its inverse, making undo/redo trivial.'''),

    ("js_deep2_10", r'''Implement a plugin system in TypeScript where plugins can hook into a host application's lifecycle, modify behavior through interceptors, and be loaded/unloaded dynamically.''',
     r'''<think>
Plugin systems need careful design:
1. Plugin interface: install(), uninstall(), metadata (name, version, deps).
2. Lifecycle hooks: beforeStart, afterStart, beforeStop, etc.
3. Interceptors: modify behavior at extension points (like middleware for specific operations).
4. Dynamic loading: load/unload plugins at runtime.
5. Dependency resolution: plugin A depends on plugin B.
6. Conflict detection: two plugins trying to override the same thing.
7. Sandboxing: plugins shouldn't be able to break the host.
8. TypeScript: type-safe hook and interceptor registration.
</think>

```typescript
// ── Plugin System Types ──

interface PluginMeta {
  name: string;
  version: string;
  description?: string;
  dependencies?: string[];
}

type HookHandler = (...args: any[]) => void | Promise<void>;
type Interceptor<T> = (value: T) => T | Promise<T>;

interface PluginContext {
  // Register a lifecycle hook
  hook(name: string, handler: HookHandler): void;
  // Register an interceptor (transform pipeline)
  intercept<T>(point: string, handler: Interceptor<T>): void;
  // Access shared services
  getService<T>(name: string): T | undefined;
  // Register a service for other plugins
  provide(name: string, service: unknown): void;
  // Log with plugin context
  log(message: string): void;
}

interface Plugin {
  meta: PluginMeta;
  install(ctx: PluginContext): void | Promise<void>;
  uninstall?(): void | Promise<void>;
}

// ── Plugin Manager ──

class PluginManager {
  private plugins = new Map<string, { plugin: Plugin; installed: boolean }>();
  private hooks = new Map<string, Array<{ pluginName: string; handler: HookHandler }>>();
  private interceptors = new Map<string, Array<{ pluginName: string; handler: Interceptor<any> }>>();
  private services = new Map<string, { pluginName: string; service: unknown }>();

  async install(plugin: Plugin): Promise<void> {
    const { name } = plugin.meta;

    if (this.plugins.has(name)) {
      throw new Error(`Plugin "${name}" is already installed`);
    }

    // Check dependencies
    for (const dep of plugin.meta.dependencies ?? []) {
      if (!this.plugins.has(dep) || !this.plugins.get(dep)!.installed) {
        throw new Error(`Plugin "${name}" requires "${dep}" which is not installed`);
      }
    }

    // Create scoped context for this plugin
    const ctx = this.createContext(name);
    this.plugins.set(name, { plugin, installed: false });

    try {
      await plugin.install(ctx);
      this.plugins.get(name)!.installed = true;
      console.log(`[PluginManager] Installed: ${name} v${plugin.meta.version}`);
    } catch (err) {
      // Rollback on failure
      this.removePluginRegistrations(name);
      this.plugins.delete(name);
      throw new Error(`Failed to install "${name}": ${err}`);
    }
  }

  async uninstall(name: string): Promise<void> {
    const entry = this.plugins.get(name);
    if (!entry) throw new Error(`Plugin "${name}" is not installed`);

    // Check if other plugins depend on this one
    for (const [otherName, { plugin: other }] of this.plugins) {
      if (other.meta.dependencies?.includes(name)) {
        throw new Error(`Cannot uninstall "${name}": "${otherName}" depends on it`);
      }
    }

    await entry.plugin.uninstall?.();
    this.removePluginRegistrations(name);
    this.plugins.delete(name);
    console.log(`[PluginManager] Uninstalled: ${name}`);
  }

  private createContext(pluginName: string): PluginContext {
    return {
      hook: (name, handler) => {
        if (!this.hooks.has(name)) this.hooks.set(name, []);
        this.hooks.get(name)!.push({ pluginName, handler });
      },
      intercept: (point, handler) => {
        if (!this.interceptors.has(point)) this.interceptors.set(point, []);
        this.interceptors.get(point)!.push({ pluginName, handler });
      },
      getService: <T>(name: string) => this.services.get(name)?.service as T | undefined,
      provide: (name, service) => {
        if (this.services.has(name)) {
          console.warn(`[${pluginName}] Overriding service: ${name}`);
        }
        this.services.set(name, { pluginName, service });
      },
      log: (msg) => console.log(`[${pluginName}] ${msg}`),
    };
  }

  private removePluginRegistrations(name: string): void {
    for (const [, handlers] of this.hooks) {
      const filtered = handlers.filter(h => h.pluginName !== name);
      handlers.length = 0;
      handlers.push(...filtered);
    }
    for (const [, interceptors] of this.interceptors) {
      const filtered = interceptors.filter(i => i.pluginName !== name);
      interceptors.length = 0;
      interceptors.push(...filtered);
    }
    for (const [svcName, svc] of this.services) {
      if (svc.pluginName === name) this.services.delete(svcName);
    }
  }

  // Run all hooks for a lifecycle event
  async runHook(name: string, ...args: any[]): Promise<void> {
    const handlers = this.hooks.get(name) ?? [];
    for (const { handler } of handlers) {
      await handler(...args);
    }
  }

  // Run a value through interceptors
  async intercept<T>(point: string, value: T): Promise<T> {
    const interceptors = this.interceptors.get(point) ?? [];
    let result = value;
    for (const { handler } of interceptors) {
      result = await handler(result);
    }
    return result;
  }

  get installedPlugins(): PluginMeta[] {
    return [...this.plugins.values()]
      .filter(e => e.installed)
      .map(e => e.plugin.meta);
  }
}
```

**Usage:**

```typescript
const pm = new PluginManager();

// Logger plugin
const loggerPlugin: Plugin = {
  meta: { name: "logger", version: "1.0.0" },
  install(ctx) {
    ctx.hook("app:request", (req: any) => {
      ctx.log(`${req.method} ${req.path}`);
    });
    ctx.provide("logger", { info: console.log, error: console.error });
  },
};

// Auth plugin (depends on logger)
const authPlugin: Plugin = {
  meta: { name: "auth", version: "1.0.0", dependencies: ["logger"] },
  install(ctx) {
    const logger = ctx.getService<{ info: Function }>("logger")!;

    ctx.intercept("response", async (response: any) => {
      response.headers["X-Auth"] = "verified";
      logger.info("Auth interceptor ran");
      return response;
    });

    ctx.hook("app:start", () => ctx.log("Auth system initialized"));
  },
};

await pm.install(loggerPlugin);
await pm.install(authPlugin);

// Host app uses hooks and interceptors
await pm.runHook("app:start");
const response = await pm.intercept("response", { status: 200, body: "ok", headers: {} });
```'''),

    # ── 11-15: Performance ──────────────────────────────────────────────

    ("js_deep2_11", r'''Implement production-quality debounce and throttle functions in TypeScript with these features: leading/trailing edge options, cancel, flush, and proper `this` binding. Explain when to use which.''',
     r'''<think>
Debounce and throttle are critical for performance. Key differences:
1. Debounce: waits until calls stop for N ms, then executes once. Good for: search input, resize.
2. Throttle: executes at most once per N ms. Good for: scroll, mousemove, rate limiting.
3. Leading edge: execute on first call immediately, then debounce.
4. Trailing edge: execute after the quiet period (default for debounce).
5. Cancel: abort a pending execution.
6. Flush: execute pending immediately (useful for cleanup/unmount).
7. `this` binding: preserve the original `this` context.
8. TypeScript: preserve function signature, return type should include undefined.
</think>

```typescript
interface DebounceOptions {
  leading?: boolean;   // Execute on first call (default: false)
  trailing?: boolean;  // Execute after quiet period (default: true)
  maxWait?: number;    // Max time to wait before forced execution
}

interface DebouncedFn<T extends (...args: any[]) => any> {
  (...args: Parameters<T>): void;
  cancel(): void;
  flush(): ReturnType<T> | undefined;
  pending(): boolean;
}

function debounce<T extends (...args: any[]) => any>(
  fn: T,
  wait: number,
  options: DebounceOptions = {}
): DebouncedFn<T> {
  const { leading = false, trailing = true, maxWait } = options;

  let timer: ReturnType<typeof setTimeout> | null = null;
  let lastArgs: Parameters<T> | null = null;
  let lastThis: any;
  let lastCallTime: number | undefined;
  let firstCallTime: number | undefined;
  let lastResult: ReturnType<T> | undefined;

  function invoke(): ReturnType<T> | undefined {
    if (lastArgs === null) return lastResult;
    const args = lastArgs;
    const thisArg = lastThis;
    lastArgs = lastThis = null;
    firstCallTime = undefined;
    lastResult = fn.apply(thisArg, args);
    return lastResult;
  }

  function startTimer(wait: number): void {
    timer = setTimeout(() => {
      timer = null;
      if (trailing && lastArgs) invoke();
    }, wait);
  }

  function remainingWait(): number {
    const elapsed = Date.now() - (lastCallTime ?? 0);
    let remaining = wait - elapsed;

    if (maxWait !== undefined && firstCallTime !== undefined) {
      const maxRemaining = maxWait - (Date.now() - firstCallTime);
      remaining = Math.min(remaining, maxRemaining);
    }

    return Math.max(0, remaining);
  }

  const debounced = function (this: any, ...args: Parameters<T>) {
    const now = Date.now();
    lastArgs = args;
    lastThis = this;
    lastCallTime = now;

    if (firstCallTime === undefined) firstCallTime = now;

    // Leading edge
    if (leading && timer === null) {
      invoke();
      startTimer(wait);
      return;
    }

    // MaxWait check
    if (maxWait !== undefined && firstCallTime !== undefined) {
      if (now - firstCallTime >= maxWait) {
        if (timer) clearTimeout(timer);
        timer = null;
        invoke();
        startTimer(wait);
        return;
      }
    }

    // Restart timer
    if (timer) clearTimeout(timer);
    startTimer(remainingWait());
  } as DebouncedFn<T>;

  debounced.cancel = () => {
    if (timer) clearTimeout(timer);
    timer = null;
    lastArgs = lastThis = null;
    firstCallTime = lastCallTime = undefined;
  };

  debounced.flush = () => {
    if (timer) clearTimeout(timer);
    timer = null;
    return invoke();
  };

  debounced.pending = () => timer !== null;

  return debounced;
}

// ── Throttle (built on debounce with leading+trailing+maxWait) ──

function throttle<T extends (...args: any[]) => any>(
  fn: T,
  wait: number,
  options: { leading?: boolean; trailing?: boolean } = {}
): DebouncedFn<T> {
  return debounce(fn, wait, {
    leading: options.leading ?? true,
    trailing: options.trailing ?? true,
    maxWait: wait,  // This is the key — maxWait = wait makes it a throttle
  });
}
```

**Usage:**

```typescript
// Debounce: search input — wait until user stops typing
const search = debounce(async (query: string) => {
  const results = await fetch(`/api/search?q=${query}`);
  renderResults(await results.json());
}, 300);

input.addEventListener("input", (e) => {
  search((e.target as HTMLInputElement).value);
});

// Throttle: scroll handler — execute at most every 100ms
const onScroll = throttle(() => {
  const scrollY = window.scrollY;
  updateNavbar(scrollY);
  lazyLoadImages(scrollY);
}, 100);

window.addEventListener("scroll", onScroll);

// Leading debounce: button click — execute immediately, ignore rapid clicks
const submitForm = debounce(
  () => { /* submit */ },
  1000,
  { leading: true, trailing: false }
);

// Cleanup on component unmount
function cleanup() {
  search.cancel();
  onScroll.cancel();
}
```

**When to use which:**

| Scenario | Use | Why |
|----------|-----|-----|
| Search input | Debounce (300ms) | Wait for user to finish typing |
| Window resize | Debounce (150ms) | Only care about final size |
| Scroll handler | Throttle (100ms) | Need periodic updates during scroll |
| Button click | Debounce (leading) | Prevent double-submit |
| Mousemove | Throttle (16ms) | ~60fps update rate |
| Auto-save | Debounce (maxWait: 5000ms) | Save after pause, but at least every 5s |

The key insight: throttle guarantees execution at regular intervals during continuous activity, while debounce only executes after activity stops.'''),

    ("js_deep2_12", r'''How do you implement virtual scrolling in JavaScript for rendering millions of rows efficiently? Show the math, DOM recycling, and variable row height support.''',
     r'''<think>
Virtual scrolling only renders visible items + a small buffer. Key math:
1. Container height = total items * average row height (for scrollbar accuracy).
2. Visible range: startIndex = scrollTop / rowHeight, endIndex = startIndex + visibleCount.
3. Buffer: render extra rows above/below for smooth scrolling.
4. DOM recycling: reuse DOM nodes instead of creating/destroying.
5. Variable heights: need a height cache + binary search for position.
6. translateY positioning: use absolute positioning or padding to offset visible items.
7. Intersection with ResizeObserver for dynamic measurement.
8. Performance: requestAnimationFrame for scroll handling.
</think>

```typescript
interface VirtualScrollOptions<T> {
  container: HTMLElement;
  items: T[];
  renderItem: (item: T, index: number) => HTMLElement;
  estimatedItemHeight?: number;
  overscan?: number;  // Extra items to render above/below
  onRangeChange?: (start: number, end: number) => void;
}

class VirtualScroller<T> {
  private container: HTMLElement;
  private viewport: HTMLElement;
  private content: HTMLElement;
  private items: T[];
  private renderItem: (item: T, index: number) => HTMLElement;
  private estimatedHeight: number;
  private overscan: number;
  private heightCache = new Map<number, number>();
  private renderedRange = { start: 0, end: 0 };
  private itemElements = new Map<number, HTMLElement>();
  private resizeObserver: ResizeObserver;
  private onRangeChange?: (start: number, end: number) => void;

  constructor(options: VirtualScrollOptions<T>) {
    this.container = options.container;
    this.items = options.items;
    this.renderItem = options.renderItem;
    this.estimatedHeight = options.estimatedItemHeight ?? 40;
    this.overscan = options.overscan ?? 5;
    this.onRangeChange = options.onRangeChange;

    // Create viewport structure
    this.viewport = document.createElement("div");
    this.viewport.style.cssText = "overflow-y: auto; height: 100%; position: relative;";

    this.content = document.createElement("div");
    this.content.style.cssText = "position: relative; width: 100%;";

    this.viewport.appendChild(this.content);
    this.container.appendChild(this.viewport);

    // Observe rendered items for height measurement
    this.resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const el = entry.target as HTMLElement;
        const index = parseInt(el.dataset.index ?? "-1");
        if (index >= 0) {
          this.heightCache.set(index, entry.contentRect.height);
        }
      }
      this.updateContentHeight();
    });

    // Scroll handler with rAF
    let ticking = false;
    this.viewport.addEventListener("scroll", () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          this.updateVisibleRange();
          ticking = false;
        });
        ticking = true;
      }
    });

    // Initial render
    this.updateContentHeight();
    this.updateVisibleRange();
  }

  private getItemTop(index: number): number {
    let top = 0;
    for (let i = 0; i < index; i++) {
      top += this.heightCache.get(i) ?? this.estimatedHeight;
    }
    return top;
  }

  private getTotalHeight(): number {
    return this.getItemTop(this.items.length);
  }

  private updateContentHeight(): void {
    this.content.style.height = `${this.getTotalHeight()}px`;
  }

  private getVisibleRange(): { start: number; end: number } {
    const scrollTop = this.viewport.scrollTop;
    const viewportHeight = this.viewport.clientHeight;

    // Binary search for start index
    let start = 0;
    let accHeight = 0;
    for (let i = 0; i < this.items.length; i++) {
      const h = this.heightCache.get(i) ?? this.estimatedHeight;
      if (accHeight + h > scrollTop) {
        start = i;
        break;
      }
      accHeight += h;
    }

    // Find end index
    let end = start;
    let visibleHeight = 0;
    for (let i = start; i < this.items.length; i++) {
      if (visibleHeight > viewportHeight) break;
      visibleHeight += this.heightCache.get(i) ?? this.estimatedHeight;
      end = i + 1;
    }

    // Apply overscan
    start = Math.max(0, start - this.overscan);
    end = Math.min(this.items.length, end + this.overscan);

    return { start, end };
  }

  private updateVisibleRange(): void {
    const { start, end } = this.getVisibleRange();

    if (start === this.renderedRange.start && end === this.renderedRange.end) return;

    // Remove items outside new range
    for (const [index, el] of this.itemElements) {
      if (index < start || index >= end) {
        this.resizeObserver.unobserve(el);
        el.remove();
        this.itemElements.delete(index);
      }
    }

    // Add items in new range
    for (let i = start; i < end; i++) {
      if (this.itemElements.has(i)) continue;

      const el = this.renderItem(this.items[i], i);
      el.dataset.index = String(i);
      el.style.position = "absolute";
      el.style.top = `${this.getItemTop(i)}px`;
      el.style.width = "100%";

      this.content.appendChild(el);
      this.itemElements.set(i, el);
      this.resizeObserver.observe(el);
    }

    this.renderedRange = { start, end };
    this.onRangeChange?.(start, end);
  }

  // Public API
  scrollToIndex(index: number): void {
    this.viewport.scrollTop = this.getItemTop(index);
  }

  updateItems(items: T[]): void {
    this.items = items;
    this.heightCache.clear();
    for (const [, el] of this.itemElements) {
      this.resizeObserver.unobserve(el);
      el.remove();
    }
    this.itemElements.clear();
    this.updateContentHeight();
    this.updateVisibleRange();
  }

  destroy(): void {
    this.resizeObserver.disconnect();
    this.container.innerHTML = "";
  }
}
```

**Usage:**

```typescript
const scroller = new VirtualScroller({
  container: document.getElementById("list")!,
  items: Array.from({ length: 1_000_000 }, (_, i) => ({
    id: i,
    name: `Item ${i}`,
    description: `Description for item ${i}`,
  })),
  renderItem: (item, index) => {
    const el = document.createElement("div");
    el.className = "list-item";
    el.innerHTML = `<strong>${item.name}</strong><p>${item.description}</p>`;
    return el;
  },
  estimatedItemHeight: 60,
  overscan: 10,
});
```

With 1 million items, only ~30-50 DOM nodes exist at any time. The browser thinks the container is huge (scrollbar reflects total height), but actual DOM work is minimal.'''),

    ("js_deep2_13", r'''How do you prevent XSS (Cross-Site Scripting) attacks in JavaScript? Show all attack vectors, sanitization techniques, Content Security Policy setup, and a DOMPurify-like sanitizer.''',
     r'''<think>
XSS is the #1 web vulnerability. Attack vectors:
1. Reflected XSS: malicious input reflected back in HTML (<script>alert(1)</script>).
2. Stored XSS: malicious content saved in DB, served to other users.
3. DOM-based XSS: client-side code inserts untrusted data into DOM.
4. Mutation XSS (mXSS): browser's HTML parser normalizes malicious input into active content.
5. Defense layers: input sanitization, output encoding, CSP, trusted types.
6. Context-specific encoding: HTML, URL, JavaScript, CSS contexts all need different encoding.
7. Template literals with innerHTML are dangerous.
8. CSP: Content-Security-Policy header restricts script sources.
9. Sanitization: parse HTML, allow-list safe elements/attributes, strip dangerous ones.
</think>

```typescript
// ── Context-Specific Output Encoding ──

function escapeHTML(str: string): string {
  const map: Record<string, string> = {
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#x27;",
    "/": "&#x2F;",
  };
  return str.replace(/[&<>"'/]/g, (c) => map[c]);
}

function escapeAttribute(str: string): string {
  // For use inside HTML attribute values
  return str.replace(/[&"'<>]/g, (c) => `&#${c.charCodeAt(0)};`);
}

function escapeURL(str: string): string {
  // Prevent javascript: protocol and encode special chars
  const url = new URL(str, window.location.origin);
  if (!["http:", "https:", "mailto:"].includes(url.protocol)) {
    return "#blocked";
  }
  return encodeURI(str);
}

// ── Safe DOM Manipulation ──

// DANGEROUS — XSS vector!
// element.innerHTML = userInput;

// SAFE alternatives:
function safeSetText(element: HTMLElement, text: string): void {
  element.textContent = text;  // Automatically escapes HTML
}

function safeCreateLink(href: string, text: string): HTMLAnchorElement {
  const a = document.createElement("a");
  a.href = escapeURL(href);
  a.textContent = text;  // textContent, not innerHTML
  return a;
}

// ── HTML Sanitizer (DOMPurify-like) ──

interface SanitizeOptions {
  allowedTags?: string[];
  allowedAttributes?: Record<string, string[]>;
  allowedProtocols?: string[];
}

const DEFAULT_ALLOWED_TAGS = [
  "p", "br", "b", "i", "em", "strong", "a", "ul", "ol", "li",
  "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "pre", "code",
  "img", "span", "div", "table", "thead", "tbody", "tr", "th", "td",
];

const DEFAULT_ALLOWED_ATTRS: Record<string, string[]> = {
  a: ["href", "title", "target", "rel"],
  img: ["src", "alt", "width", "height"],
  td: ["colspan", "rowspan"],
  th: ["colspan", "rowspan"],
  "*": ["class", "id"],  // Allowed on any element
};

const DEFAULT_PROTOCOLS = ["http:", "https:", "mailto:"];

function sanitizeHTML(dirty: string, options: SanitizeOptions = {}): string {
  const allowedTags = new Set(options.allowedTags ?? DEFAULT_ALLOWED_TAGS);
  const allowedAttrs = options.allowedAttributes ?? DEFAULT_ALLOWED_ATTRS;
  const allowedProtocols = new Set(options.allowedProtocols ?? DEFAULT_PROTOCOLS);

  // Parse using the browser's HTML parser (handles mXSS)
  const parser = new DOMParser();
  const doc = parser.parseFromString(
    `<div>${dirty}</div>`,
    "text/html"
  );
  const root = doc.body.firstElementChild!;

  function walk(node: Node): void {
    const children = [...node.childNodes];

    for (const child of children) {
      if (child.nodeType === Node.TEXT_NODE) continue;

      if (child.nodeType === Node.ELEMENT_NODE) {
        const el = child as Element;
        const tag = el.tagName.toLowerCase();

        // Remove disallowed tags
        if (!allowedTags.has(tag)) {
          // Keep text content, remove element
          while (el.firstChild) {
            node.insertBefore(el.firstChild, el);
          }
          node.removeChild(el);
          continue;
        }

        // Clean attributes
        const attrs = [...el.attributes];
        for (const attr of attrs) {
          const attrName = attr.name.toLowerCase();
          const tagAllowed = allowedAttrs[tag] ?? [];
          const globalAllowed = allowedAttrs["*"] ?? [];

          if (!tagAllowed.includes(attrName) && !globalAllowed.includes(attrName)) {
            el.removeAttribute(attrName);
            continue;
          }

          // Check URL attributes for dangerous protocols
          if (["href", "src", "action"].includes(attrName)) {
            try {
              const url = new URL(attr.value, window.location.origin);
              if (!allowedProtocols.has(url.protocol)) {
                el.removeAttribute(attrName);
              }
            } catch {
              el.removeAttribute(attrName);
            }
          }

          // Remove event handler attributes
          if (attrName.startsWith("on")) {
            el.removeAttribute(attrName);
          }
        }

        // Force safe link attributes
        if (tag === "a") {
          el.setAttribute("rel", "noopener noreferrer");
        }

        walk(el);
      } else {
        // Remove comments, processing instructions, etc.
        node.removeChild(child);
      }
    }
  }

  walk(root);
  return root.innerHTML;
}
```

**Content Security Policy (CSP):**

```typescript
// Express middleware to set CSP header
app.use((req, res, next) => {
  res.setHeader("Content-Security-Policy", [
    "default-src 'self'",
    "script-src 'self' 'nonce-${generateNonce()}'",  // Only nonced scripts
    "style-src 'self' 'unsafe-inline'",               // Allow inline styles
    "img-src 'self' data: https:",                     // Images from self, data URIs, HTTPS
    "connect-src 'self' https://api.example.com",      // API calls
    "frame-ancestors 'none'",                          // Prevent framing (clickjacking)
    "base-uri 'self'",                                 // Prevent base tag injection
    "form-action 'self'",                              // Forms only submit to self
  ].join("; "));
  next();
});
```

**XSS prevention checklist:**
1. **Never use `innerHTML`** with untrusted data — use `textContent` or sanitize
2. **Sanitize** user-generated HTML through a parser-based sanitizer
3. **CSP** blocks inline scripts and limits script sources
4. **HttpOnly cookies** prevent JS access to session tokens
5. **Encode output** based on context (HTML, URL, JS, CSS)
6. **Trusted Types** API (Chrome) prevents DOM XSS at the browser level'''),

    ("js_deep2_14", r'''Implement JWT (JSON Web Token) handling in TypeScript: token creation, verification, refresh token rotation, and secure storage patterns for both browser and Node.js environments.''',
     r'''<think>
JWT security is critical and often implemented wrong. Key points:
1. JWT structure: header.payload.signature (base64url encoded).
2. Signing: HMAC-SHA256 or RS256 (asymmetric).
3. Verification: check signature, expiry, issuer, audience.
4. Refresh tokens: long-lived, used to get new access tokens.
5. Token rotation: each refresh returns a new refresh token (detect reuse = compromise).
6. Browser storage: HttpOnly cookies (not localStorage — XSS vector).
7. Node.js: use crypto for HMAC, no external JWT library needed.
8. Claims: exp, iat, iss, aud, sub — standard claims.
9. Never store sensitive data in JWT payload (it's only base64, not encrypted).
</think>

```typescript
// ── JWT Implementation (Node.js, no external dependencies) ──

import { createHmac, timingSafeEqual } from "crypto";

interface JWTHeader {
  alg: "HS256";
  typ: "JWT";
}

interface JWTPayload {
  sub: string;        // Subject (user ID)
  iss?: string;       // Issuer
  aud?: string;       // Audience
  exp: number;        // Expiration (unix timestamp)
  iat: number;        // Issued at
  jti?: string;       // JWT ID (for refresh token tracking)
  [key: string]: unknown;
}

function base64urlEncode(data: string | Buffer): string {
  const buf = typeof data === "string" ? Buffer.from(data) : data;
  return buf.toString("base64url");
}

function base64urlDecode(str: string): string {
  return Buffer.from(str, "base64url").toString("utf-8");
}

function sign(payload: object, secret: string): string {
  const header: JWTHeader = { alg: "HS256", typ: "JWT" };
  const headerB64 = base64urlEncode(JSON.stringify(header));
  const payloadB64 = base64urlEncode(JSON.stringify(payload));
  const data = `${headerB64}.${payloadB64}`;
  const signature = createHmac("sha256", secret).update(data).digest();
  return `${data}.${base64urlEncode(signature)}`;
}

function verify(token: string, secret: string): JWTPayload {
  const parts = token.split(".");
  if (parts.length !== 3) throw new Error("Invalid token format");

  const [headerB64, payloadB64, signatureB64] = parts;

  // Verify signature using timing-safe comparison
  const data = `${headerB64}.${payloadB64}`;
  const expected = createHmac("sha256", secret).update(data).digest();
  const actual = Buffer.from(signatureB64, "base64url");

  if (!timingSafeEqual(expected, actual)) {
    throw new Error("Invalid signature");
  }

  const payload = JSON.parse(base64urlDecode(payloadB64)) as JWTPayload;

  // Check expiration
  if (payload.exp && Date.now() / 1000 > payload.exp) {
    throw new Error("Token expired");
  }

  return payload;
}

// ── Token Service with Refresh Rotation ──

class TokenService {
  private accessSecret: string;
  private refreshSecret: string;
  private accessTTL: number;   // seconds
  private refreshTTL: number;  // seconds
  // Track valid refresh token IDs (in production, use Redis)
  private validRefreshTokens = new Map<string, { userId: string; family: string }>();

  constructor(config: {
    accessSecret: string;
    refreshSecret: string;
    accessTTL?: number;
    refreshTTL?: number;
  }) {
    this.accessSecret = config.accessSecret;
    this.refreshSecret = config.refreshSecret;
    this.accessTTL = config.accessTTL ?? 900;        // 15 minutes
    this.refreshTTL = config.refreshTTL ?? 604800;    // 7 days
  }

  createTokenPair(userId: string, claims: Record<string, unknown> = {}): {
    accessToken: string;
    refreshToken: string;
  } {
    const now = Math.floor(Date.now() / 1000);
    const family = crypto.randomUUID();  // Token family for rotation detection

    const accessToken = sign({
      sub: userId,
      iat: now,
      exp: now + this.accessTTL,
      ...claims,
    }, this.accessSecret);

    const jti = crypto.randomUUID();
    const refreshToken = sign({
      sub: userId,
      iat: now,
      exp: now + this.refreshTTL,
      jti,
      family,
    }, this.refreshSecret);

    this.validRefreshTokens.set(jti, { userId, family });
    return { accessToken, refreshToken };
  }

  verifyAccess(token: string): JWTPayload {
    return verify(token, this.accessSecret);
  }

  refresh(refreshToken: string): {
    accessToken: string;
    refreshToken: string;
  } {
    const payload = verify(refreshToken, this.refreshSecret);
    const { sub: userId, jti, family } = payload as JWTPayload & { family: string };

    if (!jti || !family) throw new Error("Invalid refresh token");

    // Check if this refresh token is still valid
    const stored = this.validRefreshTokens.get(jti);
    if (!stored) {
      // TOKEN REUSE DETECTED — invalidate entire family
      console.error(`Refresh token reuse detected for family ${family}!`);
      for (const [id, data] of this.validRefreshTokens) {
        if (data.family === family) this.validRefreshTokens.delete(id);
      }
      throw new Error("Token reuse detected — all sessions revoked");
    }

    // Invalidate used refresh token
    this.validRefreshTokens.delete(jti);

    // Issue new pair (rotation)
    return this.createTokenPair(userId);
  }

  revokeAll(userId: string): void {
    for (const [id, data] of this.validRefreshTokens) {
      if (data.userId === userId) this.validRefreshTokens.delete(id);
    }
  }
}
```

**Express middleware:**

```typescript
// Set tokens as HttpOnly cookies (NOT localStorage!)
app.post("/auth/login", async (req, res) => {
  const user = await authenticate(req.body);
  const { accessToken, refreshToken } = tokenService.createTokenPair(user.id);

  res.cookie("access_token", accessToken, {
    httpOnly: true,     // JS can't access
    secure: true,       // HTTPS only
    sameSite: "strict", // CSRF protection
    maxAge: 900_000,    // 15 min
  });

  res.cookie("refresh_token", refreshToken, {
    httpOnly: true,
    secure: true,
    sameSite: "strict",
    path: "/auth/refresh",  // Only sent to refresh endpoint
    maxAge: 604800_000,     // 7 days
  });

  res.json({ userId: user.id });
});
```

**Why HttpOnly cookies over localStorage:**
- localStorage is accessible to ANY JavaScript — a single XSS vulnerability exposes all tokens
- HttpOnly cookies are invisible to JavaScript — even XSS can't steal them
- `SameSite: strict` prevents CSRF attacks (cookie not sent cross-origin)'''),

    ("js_deep2_15", r'''Implement a complete input sanitization library in TypeScript that handles: HTML entity encoding, SQL parameter binding, command injection prevention, path traversal prevention, and email validation.''',
     r'''<think>
Input sanitization is defense-in-depth. Each context needs different sanitization:
1. HTML: encode < > & " ' to prevent XSS when inserting into HTML.
2. SQL: parameterized queries — never string concatenation.
3. Command injection: validate against allowlist, never pass user input to shell.
4. Path traversal: resolve and check the path stays within allowed directory.
5. Email: RFC 5322 validation (not just regex).
6. General: type coercion, length limits, character allowlists.
7. Important: sanitize at the boundary (input), not deep in business logic.
8. Validation vs sanitization: validate = reject bad input, sanitize = transform to safe form.
</think>

```typescript
// ── HTML Sanitization ──

const HTML_ENTITIES: Record<string, string> = {
  "&": "&amp;", "<": "&lt;", ">": "&gt;",
  '"': "&quot;", "'": "&#39;", "`": "&#96;",
};

function sanitizeHTML(input: string): string {
  return input.replace(/[&<>"'`]/g, (c) => HTML_ENTITIES[c]);
}

// ── SQL Parameterization Helper ──

interface SafeQuery {
  text: string;
  values: unknown[];
}

function sql(strings: TemplateStringsArray, ...values: unknown[]): SafeQuery {
  // Tagged template literal that auto-parameterizes
  let text = "";
  const params: unknown[] = [];

  for (let i = 0; i < strings.length; i++) {
    text += strings[i];
    if (i < values.length) {
      params.push(values[i]);
      text += `$${params.length}`;
    }
  }

  return { text, values: params };
}

// Usage: sql`SELECT * FROM users WHERE id = ${userId} AND role = ${role}`
// Result: { text: "SELECT * FROM users WHERE id = $1 AND role = $2", values: [userId, role] }

// ── Command Injection Prevention ──

const SAFE_COMMAND_CHARS = /^[a-zA-Z0-9._\-\/\\: ]+$/;

function sanitizeShellArg(arg: string): string {
  // Reject anything with shell metacharacters
  if (!SAFE_COMMAND_CHARS.test(arg)) {
    throw new Error(`Unsafe shell argument: ${arg.slice(0, 50)}`);
  }
  // Double-quote wrap for spaces (but we already validated chars)
  return `"${arg}"`;
}

function safeExec(
  command: string,
  allowedCommands: string[],
  args: string[]
): { command: string; args: string[] } {
  // Allowlist the command itself
  if (!allowedCommands.includes(command)) {
    throw new Error(`Command not allowed: ${command}`);
  }

  // Sanitize each argument
  const safeArgs = args.map(sanitizeShellArg);
  return { command, args: safeArgs };
}

// ── Path Traversal Prevention ──

import { resolve, normalize, relative } from "path";

function sanitizePath(userPath: string, baseDir: string): string {
  // Resolve to absolute path
  const resolved = resolve(baseDir, userPath);
  const normalized = normalize(resolved);

  // Check it's still within the base directory
  const rel = relative(baseDir, normalized);
  if (rel.startsWith("..") || resolve(baseDir, rel) !== normalized) {
    throw new Error(`Path traversal detected: ${userPath}`);
  }

  return normalized;
}

// Usage:
// sanitizePath("../../../etc/passwd", "/app/uploads")
// Throws: "Path traversal detected"
// sanitizePath("docs/file.txt", "/app/uploads")
// Returns: "/app/uploads/docs/file.txt"

// ── Email Validation ──

function isValidEmail(email: string): boolean {
  // RFC 5322 simplified — handles 99.9% of real emails
  if (email.length > 254) return false;  // Max email length

  const parts = email.split("@");
  if (parts.length !== 2) return false;

  const [local, domain] = parts;
  if (local.length > 64) return false;   // Max local part
  if (local.length === 0 || domain.length === 0) return false;

  // Local part: allow alphanumeric, dots, underscores, hyphens, plus
  if (!/^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+$/.test(local)) return false;

  // Domain: valid hostname
  if (!/^[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$/.test(domain)) return false;

  // Must have at least one dot in domain (TLD required)
  if (!domain.includes(".")) return false;

  // TLD must be at least 2 chars
  const tld = domain.split(".").pop()!;
  if (tld.length < 2) return false;

  return true;
}

// ── General Purpose Sanitizer ──

interface SanitizeRule {
  type: "string" | "number" | "boolean" | "email" | "url";
  required?: boolean;
  minLength?: number;
  maxLength?: number;
  min?: number;
  max?: number;
  pattern?: RegExp;
  allowedValues?: string[];
  transform?: "trim" | "lowercase" | "uppercase";
}

type Schema = Record<string, SanitizeRule>;

function sanitizeInput<T extends Record<string, unknown>>(
  input: unknown,
  schema: Schema
): { data: T; errors: Record<string, string> } {
  const raw = (typeof input === "object" && input !== null) ? input as Record<string, unknown> : {};
  const data: Record<string, unknown> = {};
  const errors: Record<string, string> = {};

  for (const [field, rule] of Object.entries(schema)) {
    let value = raw[field];

    // Required check
    if (value === undefined || value === null || value === "") {
      if (rule.required) errors[field] = `${field} is required`;
      continue;
    }

    // Type coercion and validation
    switch (rule.type) {
      case "string": {
        let str = String(value);
        if (rule.transform === "trim") str = str.trim();
        if (rule.transform === "lowercase") str = str.toLowerCase();
        if (rule.transform === "uppercase") str = str.toUpperCase();
        if (rule.minLength && str.length < rule.minLength)
          errors[field] = `${field} must be at least ${rule.minLength} characters`;
        else if (rule.maxLength && str.length > rule.maxLength)
          errors[field] = `${field} must be at most ${rule.maxLength} characters`;
        else if (rule.pattern && !rule.pattern.test(str))
          errors[field] = `${field} format is invalid`;
        else if (rule.allowedValues && !rule.allowedValues.includes(str))
          errors[field] = `${field} must be one of: ${rule.allowedValues.join(", ")}`;
        else
          data[field] = str;
        break;
      }
      case "number": {
        const num = Number(value);
        if (isNaN(num)) errors[field] = `${field} must be a number`;
        else if (rule.min !== undefined && num < rule.min) errors[field] = `${field} must be >= ${rule.min}`;
        else if (rule.max !== undefined && num > rule.max) errors[field] = `${field} must be <= ${rule.max}`;
        else data[field] = num;
        break;
      }
      case "email": {
        const email = String(value).trim().toLowerCase();
        if (!isValidEmail(email)) errors[field] = `${field} must be a valid email`;
        else data[field] = email;
        break;
      }
      case "boolean":
        data[field] = Boolean(value);
        break;
    }
  }

  return { data: data as T, errors };
}
```

**Usage:**

```typescript
const { data, errors } = sanitizeInput(req.body, {
  name: { type: "string", required: true, minLength: 1, maxLength: 100, transform: "trim" },
  email: { type: "email", required: true },
  age: { type: "number", min: 13, max: 120 },
  role: { type: "string", allowedValues: ["user", "admin"] },
});

if (Object.keys(errors).length > 0) {
  return res.status(400).json({ errors });
}

// Safe to use data.name, data.email, etc.
const query = sql`INSERT INTO users (name, email, age) VALUES (${data.name}, ${data.email}, ${data.age})`;
await db.query(query.text, query.values);
```

**Defense in depth:** sanitize at input, parameterize at database, encode at output. No single layer is sufficient — attackers find the gap between layers.'''),

    # ── 16-20: Modern JS Features ──────────────────────────────────────

    ("js_deep2_16", r'''Explain and demonstrate JavaScript Proxy and Reflect with practical examples: validation proxy, lazy loading proxy, negative array indices, and change tracking with deep observation.''',
     r'''<think>
Proxy intercepts fundamental operations on objects. Reflect provides the default behavior.
Key traps: get, set, has, deleteProperty, apply, construct.
Practical uses:
1. Validation: reject invalid property assignments.
2. Lazy loading: defer expensive computation until property accessed.
3. Negative indices: Python-style arr[-1] for last element.
4. Change tracking: record all mutations for undo or sync.
5. Deep observation: recursively proxy nested objects.
6. Default values: return defaults for missing properties.
Reflect is important because it preserves the correct `this` binding and receiver.
</think>

```typescript
// ── 1. Validation Proxy ──

function validated<T extends object>(target: T, rules: Record<string, (v: any) => boolean>): T {
  return new Proxy(target, {
    set(obj, prop: string, value, receiver) {
      const rule = rules[prop];
      if (rule && !rule(value)) {
        throw new TypeError(`Invalid value for ${prop}: ${JSON.stringify(value)}`);
      }
      return Reflect.set(obj, prop, value, receiver);
    },
  });
}

const user = validated({ name: "", age: 0 }, {
  name: (v) => typeof v === "string" && v.length > 0 && v.length <= 50,
  age: (v) => typeof v === "number" && v >= 0 && v <= 150,
});

user.name = "Alice";  // OK
user.age = 30;        // OK
user.age = -5;        // Throws: Invalid value for age

// ── 2. Lazy Loading Proxy ──

function lazy<T extends object>(factory: () => T): T {
  let instance: T | null = null;

  return new Proxy({} as T, {
    get(_, prop, receiver) {
      if (!instance) instance = factory();
      return Reflect.get(instance, prop, receiver);
    },
    set(_, prop, value, receiver) {
      if (!instance) instance = factory();
      return Reflect.set(instance, prop, value, receiver);
    },
  });
}

// Expensive initialization only happens on first access
const config = lazy(() => {
  console.log("Loading config...");
  return JSON.parse(readFileSync("config.json", "utf-8"));
});
// Nothing happens yet...
console.log(config.database.host);  // NOW it loads

// ── 3. Negative Array Indices ──

function negativeIndex<T>(arr: T[]): T[] {
  return new Proxy(arr, {
    get(target, prop, receiver) {
      if (typeof prop === "string") {
        const index = Number(prop);
        if (Number.isInteger(index) && index < 0) {
          return target[target.length + index];
        }
      }
      return Reflect.get(target, prop, receiver);
    },
    set(target, prop, value, receiver) {
      if (typeof prop === "string") {
        const index = Number(prop);
        if (Number.isInteger(index) && index < 0) {
          target[target.length + index] = value;
          return true;
        }
      }
      return Reflect.set(target, prop, value, receiver);
    },
  });
}

const arr = negativeIndex([1, 2, 3, 4, 5]);
console.log(arr[-1]);   // 5 (last element)
console.log(arr[-2]);   // 4
arr[-1] = 99;
console.log(arr);       // [1, 2, 3, 4, 99]

// ── 4. Deep Change Tracking ──

type ChangeRecord = {
  path: string;
  type: "set" | "delete";
  oldValue?: unknown;
  newValue?: unknown;
  timestamp: number;
};

function trackChanges<T extends object>(
  target: T,
  onChange?: (change: ChangeRecord) => void
): T & { __changes: ChangeRecord[] } {
  const changes: ChangeRecord[] = [];

  function createProxy(obj: any, path: string): any {
    if (typeof obj !== "object" || obj === null) return obj;

    return new Proxy(obj, {
      get(target, prop, receiver) {
        if (prop === "__changes") return changes;

        const value = Reflect.get(target, prop, receiver);
        // Recursively proxy nested objects
        if (typeof value === "object" && value !== null && typeof prop === "string") {
          return createProxy(value, path ? `${path}.${prop}` : prop);
        }
        return value;
      },

      set(target, prop: string, value, receiver) {
        const oldValue = target[prop];
        const fullPath = path ? `${path}.${prop}` : prop;

        const change: ChangeRecord = {
          path: fullPath,
          type: "set",
          oldValue,
          newValue: value,
          timestamp: Date.now(),
        };
        changes.push(change);
        onChange?.(change);

        return Reflect.set(target, prop, value, receiver);
      },

      deleteProperty(target, prop: string) {
        const fullPath = path ? `${path}.${prop}` : prop;
        changes.push({
          path: fullPath,
          type: "delete",
          oldValue: target[prop],
          timestamp: Date.now(),
        });
        return Reflect.deleteProperty(target, prop);
      },
    });
  }

  return createProxy(target, "") as T & { __changes: ChangeRecord[] };
}

// Usage
const state = trackChanges(
  { user: { name: "Alice", settings: { theme: "dark" } }, count: 0 },
  (change) => console.log(`Change: ${change.path} = ${change.newValue}`)
);

state.count = 1;                    // Change: count = 1
state.user.name = "Bob";           // Change: user.name = Bob
state.user.settings.theme = "light"; // Change: user.settings.theme = light

console.log(state.__changes.length); // 3
```

**Why Reflect matters:** `Reflect.get(target, prop, receiver)` passes the correct `receiver` (the proxy itself), so property access on inherited objects works correctly. Without Reflect, `this` inside getters would point to the raw target, not the proxy.'''),

    ("js_deep2_17", r'''Explain and implement WeakRef and FinalizationRegistry in JavaScript. Show practical use cases: cache that doesn't prevent garbage collection, resource cleanup, and memory-efficient object pools.''',
     r'''<think>
WeakRef and FinalizationRegistry are GC-aware primitives:
1. WeakRef: holds a reference to an object without preventing GC.
2. FinalizationRegistry: callback when a registered object is GC'd.
3. Use case: caches where you want to cache objects but allow GC to reclaim memory.
4. Use case: resource cleanup (file handles, connections) when objects are abandoned.
5. Important: GC timing is non-deterministic — don't rely on cleanup for correctness.
6. WeakRef.deref() returns the object or undefined if GC'd.
7. FinalizationRegistry callback may never run (process exit, etc.).
8. These are for optimization, not correctness.
</think>

```typescript
// ── 1. Memory-Efficient Cache ──

class WeakCache<K, V extends object> {
  private cache = new Map<K, WeakRef<V>>();
  private registry = new FinalizationRegistry<K>((key) => {
    // Clean up map entry when value is GC'd
    const ref = this.cache.get(key);
    if (ref && ref.deref() === undefined) {
      this.cache.delete(key);
    }
  });

  set(key: K, value: V): void {
    // Clean up old entry if exists
    const oldRef = this.cache.get(key);
    if (oldRef) {
      const oldValue = oldRef.deref();
      if (oldValue) this.registry.unregister(oldValue);
    }

    this.cache.set(key, new WeakRef(value));
    this.registry.register(value, key, value); // value is also unregister token
  }

  get(key: K): V | undefined {
    const ref = this.cache.get(key);
    if (!ref) return undefined;

    const value = ref.deref();
    if (value === undefined) {
      // Object was GC'd — clean up
      this.cache.delete(key);
      return undefined;
    }

    return value;
  }

  has(key: K): boolean {
    return this.get(key) !== undefined;
  }

  get size(): number {
    // Approximate — some entries may be GC'd but not yet cleaned
    return this.cache.size;
  }
}

// Usage: cache parsed documents without preventing GC
const docCache = new WeakCache<string, Document>();

async function getDocument(url: string): Promise<Document> {
  let doc = docCache.get(url);
  if (doc) return doc;

  const response = await fetch(url);
  const html = await response.text();
  doc = new DOMParser().parseFromString(html, "text/html");
  docCache.set(url, doc);
  return doc;
}
// If memory pressure rises, GC can reclaim cached documents
// Next access will re-fetch — slower but the app doesn't OOM

// ── 2. Resource Cleanup ──

class ManagedResource {
  private handle: number;
  private static registry = new FinalizationRegistry<number>((handle) => {
    console.warn(`Resource ${handle} was not properly closed! Cleaning up...`);
    ManagedResource.releaseHandle(handle);
  });

  constructor() {
    this.handle = ManagedResource.acquireHandle();
    ManagedResource.registry.register(this, this.handle, this);
  }

  // Explicit cleanup (preferred)
  close(): void {
    ManagedResource.registry.unregister(this);
    ManagedResource.releaseHandle(this.handle);
  }

  // If user forgets close(), FinalizationRegistry cleans up eventually
  private static nextHandle = 0;
  private static acquireHandle(): number { return ++this.nextHandle; }
  private static releaseHandle(handle: number): void {
    console.log(`Released handle ${handle}`);
  }
}

// ── 3. Object Pool with Weak Back-References ──

class ObjectPool<T extends object> {
  private available: T[] = [];
  private inUse = new Set<WeakRef<T>>();
  private factory: () => T;
  private reset: (obj: T) => void;
  private registry: FinalizationRegistry<null>;

  constructor(factory: () => T, reset: (obj: T) => void, initialSize = 0) {
    this.factory = factory;
    this.reset = reset;

    this.registry = new FinalizationRegistry(() => {
      // An in-use object was GC'd without being returned — pool leak detected
      console.warn("Pool object was GC'd without being returned!");
    });

    for (let i = 0; i < initialSize; i++) {
      this.available.push(factory());
    }
  }

  acquire(): T {
    let obj = this.available.pop();
    if (!obj) obj = this.factory();

    const ref = new WeakRef(obj);
    this.inUse.add(ref);
    this.registry.register(obj, null, obj);

    return obj;
  }

  release(obj: T): void {
    this.registry.unregister(obj);

    // Remove from inUse
    for (const ref of this.inUse) {
      if (ref.deref() === obj) {
        this.inUse.delete(ref);
        break;
      }
    }

    this.reset(obj);
    this.available.push(obj);
  }

  get stats() {
    // Clean up dead weak refs
    let active = 0;
    for (const ref of this.inUse) {
      if (ref.deref()) active++;
    }
    return {
      available: this.available.length,
      inUse: active,
      total: this.available.length + active,
    };
  }
}
```

**Usage:**

```typescript
// Buffer pool for network I/O
const bufferPool = new ObjectPool(
  () => new ArrayBuffer(4096),     // Factory
  (buf) => new Uint8Array(buf).fill(0),  // Reset
  10                                // Pre-allocate 10
);

const buf = bufferPool.acquire();
// ... use buffer ...
bufferPool.release(buf);  // Return to pool

console.log(bufferPool.stats);  // { available: 10, inUse: 0, total: 10 }
```

**Key rules for WeakRef/FinalizationRegistry:**
- **Never rely on finalization for correctness** — GC timing is unpredictable
- **Always provide explicit cleanup** (`.close()`, `.dispose()`) — finalization is a safety net
- **Don't access WeakRef.deref() in hot loops** — it prevents the engine from collecting
- **FinalizationRegistry callbacks run asynchronously** — not during GC itself'''),

    ("js_deep2_18", r'''Implement the `using` keyword pattern (TC39 Explicit Resource Management) in TypeScript with Symbol.dispose and Symbol.asyncDispose, and show how it simplifies resource cleanup.''',
     r'''<think>
The `using` declaration (TC39 proposal, Stage 3) is like C#'s `using` or Python's `with`.
It auto-calls Symbol.dispose when a variable goes out of scope.
1. Symbol.dispose: sync cleanup (files, locks).
2. Symbol.asyncDispose: async cleanup (DB connections, streams).
3. DisposableStack: collect multiple disposables for batch cleanup.
4. The pattern eliminates try/finally for resource management.
5. TypeScript 5.2+ supports this with the Disposable interface.
6. For older runtimes, we can polyfill with try/finally wrappers.
</think>

```typescript
// ── Disposable Interfaces ──
// TypeScript 5.2+ has these built-in, but here's the shape:

interface Disposable {
  [Symbol.dispose](): void;
}

interface AsyncDisposable {
  [Symbol.asyncDispose](): Promise<void>;
}

// ── Example: Database Connection ──

class DBConnection implements AsyncDisposable {
  private connected = false;

  static async connect(url: string): Promise<DBConnection> {
    const conn = new DBConnection();
    console.log(`Connecting to ${url}...`);
    conn.connected = true;
    return conn;
  }

  async query(sql: string): Promise<unknown[]> {
    if (!this.connected) throw new Error("Not connected");
    console.log(`Query: ${sql}`);
    return [];
  }

  async [Symbol.asyncDispose](): Promise<void> {
    if (this.connected) {
      console.log("Closing DB connection...");
      this.connected = false;
    }
  }
}

// ── Example: File Handle ──

class FileHandle implements Disposable {
  private open = true;

  constructor(readonly path: string) {
    console.log(`Opened file: ${path}`);
  }

  read(): string {
    if (!this.open) throw new Error("File closed");
    return "file contents";
  }

  [Symbol.dispose](): void {
    if (this.open) {
      console.log(`Closed file: ${this.path}`);
      this.open = false;
    }
  }
}

// ── Example: Lock ──

class Mutex implements Disposable {
  private locked = false;

  acquire(): Disposable {
    if (this.locked) throw new Error("Already locked");
    this.locked = true;
    console.log("Lock acquired");

    return {
      [Symbol.dispose]: () => {
        this.locked = false;
        console.log("Lock released");
      },
    };
  }
}

// ── Usage with `using` keyword (TypeScript 5.2+) ──

// Sync resources:
function processFile(path: string): string {
  using file = new FileHandle(path);  // Auto-disposed at end of block
  return file.read();
  // FileHandle[Symbol.dispose]() called automatically here
}

// Async resources:
async function queryDB(): Promise<unknown[]> {
  await using db = await DBConnection.connect("postgres://localhost/app");
  const users = await db.query("SELECT * FROM users");
  return users;
  // DBConnection[Symbol.asyncDispose]() called automatically here
  // Even if query throws, connection is still closed!
}

// Multiple resources:
async function migrate(): Promise<void> {
  await using source = await DBConnection.connect("postgres://old-db/app");
  await using target = await DBConnection.connect("postgres://new-db/app");

  const data = await source.query("SELECT * FROM users");
  // ... migrate data ...

  // Both connections closed in reverse order (target first, then source)
}

// ── DisposableStack: batch resource management ──

class DisposableStack implements Disposable {
  private stack: Disposable[] = [];
  private disposed = false;

  use<T extends Disposable>(resource: T): T {
    if (this.disposed) throw new Error("Stack already disposed");
    this.stack.push(resource);
    return resource;
  }

  defer(cleanup: () => void): void {
    this.use({ [Symbol.dispose]: cleanup });
  }

  [Symbol.dispose](): void {
    if (this.disposed) return;
    this.disposed = true;

    // Dispose in reverse order (LIFO)
    const errors: Error[] = [];
    while (this.stack.length > 0) {
      const resource = this.stack.pop()!;
      try {
        resource[Symbol.dispose]();
      } catch (err) {
        errors.push(err instanceof Error ? err : new Error(String(err)));
      }
    }

    if (errors.length > 0) {
      throw new AggregateError(errors, "Errors during disposal");
    }
  }
}

// Usage:
function complexOperation(): void {
  using stack = new DisposableStack();

  const file1 = stack.use(new FileHandle("input.txt"));
  const file2 = stack.use(new FileHandle("output.txt"));
  const mutex = new Mutex();
  const lock = stack.use(mutex.acquire());

  stack.defer(() => console.log("Custom cleanup"));

  // Do work...
  // ALL resources cleaned up at end of scope, in reverse order
}
```

**Before `using` (traditional approach):**

```typescript
// Ugly nested try/finally
async function queryDB_old(): Promise<unknown[]> {
  const db = await DBConnection.connect("postgres://localhost/app");
  try {
    return await db.query("SELECT * FROM users");
  } finally {
    await db[Symbol.asyncDispose]();
  }
}
```

`using` eliminates the try/finally boilerplate while guaranteeing cleanup — even when exceptions are thrown. It's the same pattern as Go's `defer`, Python's `with`, and C#'s `using`.'''),

    ("js_deep2_19", r'''Implement JavaScript decorators (TC39 Stage 3) in TypeScript. Show method decorators for logging, memoization, retry, and access control. Explain the decorator evaluation order.''',
     r'''<think>
TC39 Stage 3 decorators (different from legacy/experimental TS decorators):
1. New syntax: @decorator on classes, methods, fields, accessors.
2. Decorator receives context object (not target/key/descriptor like old decorators).
3. Method decorators can wrap the original method.
4. Class decorators can wrap or replace the class.
5. Evaluation order: bottom-up for decorators on same element, outer class last.
6. Show practical decorators: @log, @memoize, @retry, @authorize.
7. Use TypeScript 5.0+ native decorator support.
</think>

```typescript
// ── Helper Types ──
type MethodDecorator = (
  target: Function,
  context: ClassMethodDecoratorContext
) => Function | void;

// ── @log — Log method calls with timing ──

function log(
  target: Function,
  context: ClassMethodDecoratorContext
): Function {
  const methodName = String(context.name);

  return function (this: any, ...args: any[]) {
    const argsStr = args.map(a => JSON.stringify(a)).join(", ");
    console.log(`-> ${methodName}(${argsStr})`);

    const start = performance.now();
    const result = target.apply(this, args);

    // Handle async methods
    if (result instanceof Promise) {
      return result.then((val: any) => {
        const ms = (performance.now() - start).toFixed(1);
        console.log(`<- ${methodName} [${ms}ms]:`, val);
        return val;
      });
    }

    const ms = (performance.now() - start).toFixed(1);
    console.log(`<- ${methodName} [${ms}ms]:`, result);
    return result;
  };
}

// ── @memoize — Cache results by arguments ──

function memoize(
  target: Function,
  context: ClassMethodDecoratorContext
): Function {
  const cache = new Map<string, any>();

  return function (this: any, ...args: any[]) {
    const key = JSON.stringify(args);
    if (cache.has(key)) return cache.get(key);

    const result = target.apply(this, args);
    cache.set(key, result);
    return result;
  };
}

// ── @retry — Retry on failure with exponential backoff ──

function retry(attempts: number, delay = 100) {
  return function (
    target: Function,
    context: ClassMethodDecoratorContext
  ): Function {
    const methodName = String(context.name);

    return async function (this: any, ...args: any[]) {
      let lastError: Error;

      for (let i = 0; i < attempts; i++) {
        try {
          return await target.apply(this, args);
        } catch (err) {
          lastError = err instanceof Error ? err : new Error(String(err));
          if (i < attempts - 1) {
            const wait = delay * Math.pow(2, i);
            console.warn(`${methodName} attempt ${i + 1} failed, retrying in ${wait}ms`);
            await new Promise(r => setTimeout(r, wait));
          }
        }
      }

      throw lastError!;
    };
  };
}

// ── @authorize — Access control ──

function authorize(...roles: string[]) {
  return function (
    target: Function,
    context: ClassMethodDecoratorContext
  ): Function {
    return function (this: any, ...args: any[]) {
      const user = this.currentUser ?? this.context?.user;
      if (!user) throw new Error("Not authenticated");
      if (!roles.includes(user.role)) {
        throw new Error(`Forbidden: requires role ${roles.join(" or ")}`);
      }
      return target.apply(this, args);
    };
  };
}

// ── @throttle — Rate limit method calls ──

function throttle(ms: number) {
  return function (
    target: Function,
    context: ClassMethodDecoratorContext
  ): Function {
    let lastCall = 0;

    return function (this: any, ...args: any[]) {
      const now = Date.now();
      if (now - lastCall < ms) return;
      lastCall = now;
      return target.apply(this, args);
    };
  };
}

// ── Usage ──

class UserService {
  currentUser = { id: "1", role: "admin" };

  @log
  @memoize
  getUser(id: string): { id: string; name: string } {
    // Expensive lookup
    return { id, name: `User ${id}` };
  }

  @log
  @retry(3, 200)
  async fetchFromAPI(endpoint: string): Promise<unknown> {
    const res = await fetch(endpoint);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }

  @authorize("admin", "moderator")
  deleteUser(id: string): void {
    console.log(`Deleted user ${id}`);
  }

  @throttle(1000)
  onScroll(position: number): void {
    console.log(`Scroll position: ${position}`);
  }
}

const svc = new UserService();

svc.getUser("123");
// -> getUser("123")
// <- getUser [0.1ms]: { id: "123", name: "User 123" }

svc.getUser("123");
// -> getUser("123")
// <- getUser [0.0ms]: { id: "123", name: "User 123" }  (cached!)

svc.deleteUser("456");  // OK (user is admin)
```

**Decorator evaluation order:**

```typescript
class Example {
  @A    // 3rd: wraps result of B wrapping C
  @B    // 2nd: wraps result of C
  @C    // 1st: wraps original method
  method() {}
}
// Execution: A(B(C(original)))
// When method() is called: A's wrapper → B's wrapper → C's wrapper → original
```

Decorators evaluate bottom-up (C, then B, then A), but execute top-down (A's wrapper runs first, calls B's, which calls C's, which calls the original). This matches the mathematical composition `A(B(C(x)))`.'''),

    ("js_deep2_20", r'''Implement `structuredClone` alternatives for edge cases it doesn't handle: functions, class instances with methods, Proxy objects, and circular references with metadata. Also implement a serializable deep-diff.''',
     r'''<think>
structuredClone has limitations. Need to handle:
1. Functions: structuredClone throws on functions.
2. Class instances: loses prototype/methods.
3. Proxy: structuredClone sees the proxy's values but loses the proxy wrapper.
4. Need a clone that preserves class identity and methods.
5. Deep diff: compare two objects, produce a list of changes.
6. Diff should be serializable (for sending over network or storing).
7. Diff should handle: added, removed, changed properties, and nested changes.
8. Support arrays with proper index tracking.
</think>

```typescript
// ── Smart Clone: handles classes, functions, prototypes ──

function smartClone<T>(value: T, options: {
  cloneFunctions?: boolean;
  preservePrototype?: boolean;
} = {}): T {
  const { cloneFunctions = false, preservePrototype = true } = options;
  const seen = new WeakMap();

  function clone(val: any): any {
    if (val === null || typeof val !== "object") {
      if (typeof val === "function" && cloneFunctions) {
        return val.bind(null);  // Create a bound copy
      }
      return val;
    }

    if (seen.has(val)) return seen.get(val);

    // Built-in types
    if (val instanceof Date) return new Date(val.getTime());
    if (val instanceof RegExp) return new RegExp(val.source, val.flags);
    if (val instanceof Map) {
      const m = new Map();
      seen.set(val, m);
      for (const [k, v] of val) m.set(clone(k), clone(v));
      return m;
    }
    if (val instanceof Set) {
      const s = new Set();
      seen.set(val, s);
      for (const v of val) s.add(clone(v));
      return s;
    }
    if (ArrayBuffer.isView(val)) {
      return new (val.constructor as any)((val as any).buffer.slice(0));
    }

    // Array
    if (Array.isArray(val)) {
      const arr: any[] = [];
      seen.set(val, arr);
      for (const item of val) arr.push(clone(item));
      return arr;
    }

    // Object — preserve prototype for class instances
    const proto = preservePrototype ? Object.getPrototypeOf(val) : Object.prototype;
    const obj = Object.create(proto);
    seen.set(val, obj);

    for (const key of Reflect.ownKeys(val)) {
      const desc = Object.getOwnPropertyDescriptor(val, key)!;
      if ("value" in desc) {
        const v = desc.value;
        if (typeof v === "function" && !cloneFunctions) {
          // Share method references (they're on the prototype usually)
          obj[key] = v;
        } else {
          obj[key] = clone(v);
        }
      } else {
        Object.defineProperty(obj, key, desc);
      }
    }

    return obj;
  }

  return clone(value);
}

// ── Serializable Deep Diff ──

type DiffType = "added" | "removed" | "changed" | "unchanged";

interface DiffEntry {
  path: string;
  type: DiffType;
  oldValue?: unknown;
  newValue?: unknown;
  children?: DiffEntry[];
}

function deepDiff(a: unknown, b: unknown, path = ""): DiffEntry[] {
  const diffs: DiffEntry[] = [];

  // Same value
  if (Object.is(a, b)) return diffs;

  // Different types
  if (typeof a !== typeof b || a === null || b === null) {
    diffs.push({ path: path || "(root)", type: "changed", oldValue: a, newValue: b });
    return diffs;
  }

  // Primitives
  if (typeof a !== "object") {
    diffs.push({ path: path || "(root)", type: "changed", oldValue: a, newValue: b });
    return diffs;
  }

  // Arrays
  if (Array.isArray(a) && Array.isArray(b)) {
    const maxLen = Math.max(a.length, b.length);
    for (let i = 0; i < maxLen; i++) {
      const itemPath = path ? `${path}[${i}]` : `[${i}]`;
      if (i >= a.length) {
        diffs.push({ path: itemPath, type: "added", newValue: b[i] });
      } else if (i >= b.length) {
        diffs.push({ path: itemPath, type: "removed", oldValue: a[i] });
      } else {
        diffs.push(...deepDiff(a[i], b[i], itemPath));
      }
    }
    return diffs;
  }

  // Objects
  const aObj = a as Record<string, unknown>;
  const bObj = b as Record<string, unknown>;
  const allKeys = new Set([...Object.keys(aObj), ...Object.keys(bObj)]);

  for (const key of allKeys) {
    const propPath = path ? `${path}.${key}` : key;

    if (!(key in aObj)) {
      diffs.push({ path: propPath, type: "added", newValue: bObj[key] });
    } else if (!(key in bObj)) {
      diffs.push({ path: propPath, type: "removed", oldValue: aObj[key] });
    } else {
      diffs.push(...deepDiff(aObj[key], bObj[key], propPath));
    }
  }

  return diffs;
}

// ── Apply diff (patch) ──

function applyDiff<T>(target: T, diffs: DiffEntry[]): T {
  const result = smartClone(target);

  for (const diff of diffs) {
    const parts = diff.path.replace(/\[(\d+)\]/g, ".$1").split(".");
    let current: any = result;

    for (let i = 0; i < parts.length - 1; i++) {
      current = current[parts[i]];
    }

    const lastKey = parts[parts.length - 1];
    switch (diff.type) {
      case "added":
      case "changed":
        current[lastKey] = diff.newValue;
        break;
      case "removed":
        if (Array.isArray(current)) {
          current.splice(Number(lastKey), 1);
        } else {
          delete current[lastKey];
        }
        break;
    }
  }

  return result;
}
```

**Usage:**

```typescript
const v1 = {
  name: "Alice",
  age: 30,
  tags: ["admin", "user"],
  settings: { theme: "dark", lang: "en" },
};

const v2 = {
  name: "Alice",
  age: 31,
  tags: ["admin", "user", "moderator"],
  settings: { theme: "light", lang: "en", beta: true },
};

const diffs = deepDiff(v1, v2);
// [
//   { path: "age", type: "changed", oldValue: 30, newValue: 31 },
//   { path: "tags[2]", type: "added", newValue: "moderator" },
//   { path: "settings.theme", type: "changed", oldValue: "dark", newValue: "light" },
//   { path: "settings.beta", type: "added", newValue: true },
// ]

// Diffs are serializable — send over network for sync
const json = JSON.stringify(diffs);

// Apply on another client
const patched = applyDiff(v1, JSON.parse(json));
// patched deep-equals v2
```

This pattern is how collaborative editing (Google Docs), state synchronization (CRDTs), and version control (git's tree diff) work at a fundamental level.'''),

    # ── 21-25: Testing and Quality ──────────────────────────────────────

    ("js_deep2_21", r'''Implement a property-based testing library in TypeScript (like fast-check). Create generators for common types (numbers, strings, arrays, objects) and a `forAll` function that finds minimal failing cases through shrinking.''',
     r'''<think>
Property-based testing generates random inputs to find edge cases. Core components:
1. Generators (Arbitrary): produce random values of a specific type.
2. forAll: run a property function with many random inputs.
3. Shrinking: when a failure is found, find the smallest input that still fails.
4. Common generators: integer, string, array, object, oneOf, constant.
5. Combinators: map, filter, chain for building complex generators.
6. Seed-based randomness for reproducibility.
7. The key insight: shrinking produces simpler values toward the "zero" of each type.
</think>

```typescript
// ── Random number generator (seedable) ──
class PRNG {
  private state: number;
  constructor(seed: number) { this.state = seed; }

  next(): number {
    this.state = (this.state * 1103515245 + 12345) & 0x7fffffff;
    return this.state / 0x7fffffff;
  }

  integer(min: number, max: number): number {
    return Math.floor(this.next() * (max - min + 1)) + min;
  }
}

// ── Generator (Arbitrary) ──
interface Arbitrary<T> {
  generate(rng: PRNG, size: number): T;
  shrink(value: T): T[];
}

// ── Built-in generators ──

function integer(min = -1000, max = 1000): Arbitrary<number> {
  return {
    generate: (rng, size) => {
      const range = Math.min(size, max - min);
      return rng.integer(min, min + range);
    },
    shrink: (n) => {
      if (n === 0) return [];
      const shrinks: number[] = [0];
      if (n > 0) shrinks.push(Math.floor(n / 2));
      if (n < 0) shrinks.push(-Math.floor(-n / 2), Math.abs(n));
      return shrinks.filter(s => s >= min && s <= max && s !== n);
    },
  };
}

function string(minLen = 0, maxLen = 50): Arbitrary<string> {
  const chars = "abcdefghijklmnopqrstuvwxyz0123456789 ";
  return {
    generate: (rng, size) => {
      const len = rng.integer(minLen, Math.min(size, maxLen));
      let s = "";
      for (let i = 0; i < len; i++) {
        s += chars[rng.integer(0, chars.length - 1)];
      }
      return s;
    },
    shrink: (s) => {
      if (s.length <= minLen) return [];
      const shrinks: string[] = [];
      if (s.length > 0) shrinks.push(s.slice(0, Math.ceil(s.length / 2)));
      if (s.length > 1) shrinks.push(s.slice(1));
      shrinks.push(s.replace(/[^a]/g, "a"));  // Simplify characters
      return shrinks.filter(x => x !== s && x.length >= minLen);
    },
  };
}

function array<T>(element: Arbitrary<T>, minLen = 0, maxLen = 20): Arbitrary<T[]> {
  return {
    generate: (rng, size) => {
      const len = rng.integer(minLen, Math.min(size, maxLen));
      return Array.from({ length: len }, () => element.generate(rng, size));
    },
    shrink: (arr) => {
      if (arr.length <= minLen) return [];
      const shrinks: T[][] = [];
      // Remove elements
      if (arr.length > 0) shrinks.push(arr.slice(0, Math.ceil(arr.length / 2)));
      for (let i = 0; i < arr.length; i++) {
        shrinks.push([...arr.slice(0, i), ...arr.slice(i + 1)]);
      }
      // Shrink individual elements
      for (let i = 0; i < arr.length; i++) {
        for (const shrunk of element.shrink(arr[i])) {
          const copy = [...arr];
          copy[i] = shrunk;
          shrinks.push(copy);
        }
      }
      return shrinks.filter(s => s.length >= minLen);
    },
  };
}

function constant<T>(value: T): Arbitrary<T> {
  return { generate: () => value, shrink: () => [] };
}

function oneOf<T>(...arbitraries: Arbitrary<T>[]): Arbitrary<T> {
  return {
    generate: (rng, size) => {
      const arb = arbitraries[rng.integer(0, arbitraries.length - 1)];
      return arb.generate(rng, size);
    },
    shrink: (value) => {
      for (const arb of arbitraries) {
        const shrinks = arb.shrink(value);
        if (shrinks.length > 0) return shrinks;
      }
      return [];
    },
  };
}

// ── forAll: the test runner ──

interface ForAllResult<T> {
  success: boolean;
  numTests: number;
  failingInput?: T;
  shrunkInput?: T;
  error?: Error;
  seed: number;
}

function forAll<T>(
  arbitrary: Arbitrary<T>,
  property: (value: T) => boolean | void,
  options: { numRuns?: number; seed?: number; maxShrinks?: number } = {}
): ForAllResult<T> {
  const { numRuns = 100, seed = Date.now(), maxShrinks = 100 } = options;
  const rng = new PRNG(seed);

  for (let i = 0; i < numRuns; i++) {
    const size = Math.floor((i / numRuns) * 100);  // Grow size over time
    const value = arbitrary.generate(rng, size);

    try {
      const result = property(value);
      if (result === false) {
        // Property failed — try to shrink
        const shrunk = shrink(arbitrary, property, value, maxShrinks);
        return {
          success: false, numTests: i + 1, seed,
          failingInput: value, shrunkInput: shrunk,
        };
      }
    } catch (error) {
      const shrunk = shrink(arbitrary, property, value, maxShrinks);
      return {
        success: false, numTests: i + 1, seed,
        failingInput: value, shrunkInput: shrunk,
        error: error instanceof Error ? error : new Error(String(error)),
      };
    }
  }

  return { success: true, numTests: numRuns, seed };
}

function shrink<T>(
  arbitrary: Arbitrary<T>,
  property: (value: T) => boolean | void,
  failingValue: T,
  maxAttempts: number
): T {
  let smallest = failingValue;
  let attempts = 0;

  const candidates = arbitrary.shrink(smallest);
  const queue = [...candidates];

  while (queue.length > 0 && attempts < maxAttempts) {
    const candidate = queue.shift()!;
    attempts++;

    try {
      const result = property(candidate);
      if (result === false) {
        smallest = candidate;
        queue.unshift(...arbitrary.shrink(candidate));
      }
    } catch {
      smallest = candidate;
      queue.unshift(...arbitrary.shrink(candidate));
    }
  }

  return smallest;
}
```

**Usage:**

```typescript
// Property: sorting should be idempotent
const sortResult = forAll(
  array(integer()),
  (arr) => {
    const sorted = [...arr].sort((a, b) => a - b);
    const sortedAgain = [...sorted].sort((a, b) => a - b);
    return JSON.stringify(sorted) === JSON.stringify(sortedAgain);
  }
);
console.log(sortResult); // { success: true, numTests: 100 }

// Property: reverse of reverse is identity
forAll(array(integer()), (arr) => {
  const reversed = [...arr].reverse().reverse();
  return JSON.stringify(arr) === JSON.stringify(reversed);
});

// Find a bug: this flawed function fails on negative numbers
function abs(n: number): number {
  return n > 0 ? n : n;  // Bug: should be -n
}

const result = forAll(integer(-100, 100), (n) => abs(n) >= 0);
// { success: false, failingInput: -73, shrunkInput: -1 }
// Shrinking found the minimal failing case: -1
```

Property-based testing finds edge cases that unit tests miss — off-by-one errors, empty inputs, overflow, negative numbers — by exploring the input space systematically.'''),

    ("js_deep2_22", r'''Build a code coverage tracker in JavaScript that instruments functions to track which lines/branches were executed, without using any build tools or transpilers.''',
     r'''<think>
Runtime code coverage without build tools — use Function constructor or Proxy. Approach:
1. Parse function source to identify lines and branches.
2. Inject counters at each line/branch point.
3. Track execution counts in a coverage map.
4. Report: which lines executed, which branches taken, percentage.
5. Simpler approach: wrap functions to track call counts and basic metrics.
6. For line-level: use the Function constructor to inject tracking code.
7. Branch coverage: detect if/else, ternary, switch patterns.
8. Keep it practical — this is for understanding, not production coverage tools.
</think>

```typescript
// ── Coverage Data ──

interface CoverageData {
  functions: Map<string, { calls: number; lines: Map<number, number> }>;
  branches: Map<string, { taken: number; notTaken: number }>;
}

const coverage: CoverageData = {
  functions: new Map(),
  branches: new Map(),
};

// ── Function-level tracking via wrapper ──

function trackFunction<T extends (...args: any[]) => any>(
  name: string,
  fn: T
): T {
  coverage.functions.set(name, { calls: 0, lines: new Map() });

  const wrapped = function (this: any, ...args: any[]) {
    const data = coverage.functions.get(name)!;
    data.calls++;
    return fn.apply(this, args);
  } as unknown as T;

  Object.defineProperty(wrapped, "name", { value: name });
  return wrapped;
}

// ── Line-level tracking via source instrumentation ──

function instrumentSource(name: string, source: string): string {
  const lines = source.split("\n");
  const instrumented: string[] = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    const lineNum = i + 1;

    // Skip empty lines, comments, braces-only
    if (!line || line.startsWith("//") || line === "{" || line === "}") {
      instrumented.push(lines[i]);
      continue;
    }

    // Inject line counter before executable lines
    instrumented.push(
      `__coverage_hit("${name}", ${lineNum});` + lines[i]
    );

    // Branch detection: if statements
    if (/^\s*if\s*\(/.test(lines[i])) {
      const branchId = `${name}:${lineNum}`;
      // We'll track this branch in the global hit function
    }
  }

  return instrumented.join("\n");
}

// Global tracking function (injected into instrumented code)
(globalThis as any).__coverage_hit = (fn: string, line: number) => {
  const data = coverage.functions.get(fn);
  if (data) {
    data.lines.set(line, (data.lines.get(line) ?? 0) + 1);
  }
};

// ── Coverage Reporter ──

function getCoverageReport(): {
  summary: { functions: number; lines: number; coveredLines: number; percentage: number };
  details: Array<{ name: string; calls: number; linesCovered: number; linesTotal: number }>;
} {
  let totalLines = 0;
  let coveredLines = 0;
  const details: Array<{ name: string; calls: number; linesCovered: number; linesTotal: number }> = [];

  for (const [name, data] of coverage.functions) {
    const linesTotal = data.lines.size;
    const linesCovered = [...data.lines.values()].filter(v => v > 0).length;
    totalLines += linesTotal;
    coveredLines += linesCovered;
    details.push({ name, calls: data.calls, linesCovered, linesTotal });
  }

  return {
    summary: {
      functions: coverage.functions.size,
      lines: totalLines,
      coveredLines,
      percentage: totalLines > 0 ? (coveredLines / totalLines) * 100 : 0,
    },
    details,
  };
}

function printCoverageReport(): void {
  const report = getCoverageReport();

  console.log("\n=== Coverage Report ===");
  console.log(`Functions: ${report.summary.functions}`);
  console.log(`Lines: ${report.summary.coveredLines}/${report.summary.lines} (${report.summary.percentage.toFixed(1)}%)`);

  console.log("\nPer function:");
  for (const fn of report.details) {
    const pct = fn.linesTotal > 0 ? ((fn.linesCovered / fn.linesTotal) * 100).toFixed(0) : "N/A";
    console.log(`  ${fn.name}: ${fn.calls} calls, ${fn.linesCovered}/${fn.linesTotal} lines (${pct}%)`);
  }
}
```

**Usage:**

```typescript
// Track a function
const add = trackFunction("add", (a: number, b: number) => a + b);
const divide = trackFunction("divide", (a: number, b: number) => {
  if (b === 0) throw new Error("Division by zero");
  return a / b;
});

add(1, 2);
add(3, 4);
divide(10, 2);

printCoverageReport();
// === Coverage Report ===
// Functions: 2
// Lines: tracked/total
// Per function:
//   add: 2 calls
//   divide: 1 calls (error branch not tested!)
```

Production coverage tools (Istanbul/nyc, V8's built-in coverage) instrument at the AST level during compilation. This runtime approach trades completeness for simplicity — useful for understanding the concept and for scenarios where you can't modify the build pipeline.'''),

    ("js_deep2_23", r'''Implement a complete snapshot testing utility in TypeScript: serialize any value to a deterministic string, compare against stored snapshots, update snapshots on flag, and handle non-deterministic values (dates, random IDs).''',
     r'''<think>
Snapshot testing (like Jest's toMatchSnapshot). Components:
1. Serializer: convert any JS value to a deterministic, readable string.
2. Storage: read/write snapshot files.
3. Comparison: diff current vs stored snapshot.
4. Update mode: overwrite stored when --update-snapshots flag is set.
5. Non-deterministic values: replace dates, UUIDs with placeholders.
6. Serialization order: sort object keys for determinism.
7. Handle: functions, undefined, symbols (serialize as descriptive strings).
8. Pretty output with proper indentation.
</think>

```typescript
import { readFileSync, writeFileSync, mkdirSync } from "fs";
import { join, dirname } from "path";

// ── Deterministic Serializer ──

type Replacer = (key: string, value: unknown) => unknown;

const DEFAULT_REPLACERS: Replacer[] = [
  // Replace Date instances with placeholder
  (_, v) => v instanceof Date ? `[Date: ${v.toISOString()}]` : v,
  // Replace functions with descriptive string
  (_, v) => typeof v === "function" ? `[Function: ${v.name || "anonymous"}]` : v,
  // Replace undefined (JSON.stringify drops it)
  (k, v) => v === undefined ? "[undefined]" : v,
  // Replace symbols
  (_, v) => typeof v === "symbol" ? `[Symbol: ${v.description ?? ""}]` : v,
];

function serialize(value: unknown, replacers: Replacer[] = DEFAULT_REPLACERS): string {
  function transform(key: string, val: unknown): unknown {
    let result = val;
    for (const replacer of replacers) {
      result = replacer(key, result);
    }
    return result;
  }

  function stringify(val: unknown, indent: number): string {
    val = transform("", val);
    const pad = "  ".repeat(indent);
    const pad1 = "  ".repeat(indent + 1);

    if (val === null) return "null";
    if (typeof val === "string") return JSON.stringify(val);
    if (typeof val === "number" || typeof val === "boolean") return String(val);

    if (val instanceof Map) {
      if (val.size === 0) return "Map {}";
      const entries = [...val.entries()]
        .sort(([a], [b]) => String(a).localeCompare(String(b)))
        .map(([k, v]) => `${pad1}${stringify(k, indent + 1)} => ${stringify(v, indent + 1)}`);
      return `Map {\n${entries.join(",\n")}\n${pad}}`;
    }

    if (val instanceof Set) {
      if (val.size === 0) return "Set {}";
      const items = [...val].map(v => `${pad1}${stringify(v, indent + 1)}`);
      return `Set {\n${items.join(",\n")}\n${pad}}`;
    }

    if (Array.isArray(val)) {
      if (val.length === 0) return "[]";
      const items = val.map(v => `${pad1}${stringify(v, indent + 1)}`);
      return `[\n${items.join(",\n")}\n${pad}]`;
    }

    if (typeof val === "object") {
      const keys = Object.keys(val as object).sort();
      if (keys.length === 0) return "{}";
      const entries = keys.map(k => {
        const v = (val as any)[k];
        return `${pad1}${JSON.stringify(k)}: ${stringify(v, indent + 1)}`;
      });
      return `{\n${entries.join(",\n")}\n${pad}}`;
    }

    return String(val);
  }

  return stringify(value, 0);
}

// ── Snapshot Manager ──

interface SnapshotResult {
  passed: boolean;
  isNew: boolean;
  diff?: string;
}

class SnapshotManager {
  private snapshots = new Map<string, string>();
  private snapshotDir: string;
  private updateMode: boolean;
  private customReplacers: Replacer[];

  constructor(options: {
    snapshotDir?: string;
    update?: boolean;
    replacers?: Replacer[];
  } = {}) {
    this.snapshotDir = options.snapshotDir ?? "__snapshots__";
    this.updateMode = options.update ?? process.argv.includes("--update-snapshots");
    this.customReplacers = [...DEFAULT_REPLACERS, ...(options.replacers ?? [])];
  }

  match(name: string, value: unknown): SnapshotResult {
    const serialized = serialize(value, this.customReplacers);
    const snapshotPath = join(this.snapshotDir, `${name}.snap`);

    // Try to load existing snapshot
    let existing: string | null = null;
    try {
      existing = readFileSync(snapshotPath, "utf-8");
    } catch {}

    // New snapshot
    if (existing === null) {
      mkdirSync(dirname(snapshotPath), { recursive: true });
      writeFileSync(snapshotPath, serialized, "utf-8");
      console.log(`  New snapshot: ${name}`);
      return { passed: true, isNew: true };
    }

    // Compare
    if (serialized === existing) {
      return { passed: true, isNew: false };
    }

    // Mismatch
    if (this.updateMode) {
      writeFileSync(snapshotPath, serialized, "utf-8");
      console.log(`  Updated snapshot: ${name}`);
      return { passed: true, isNew: false };
    }

    // Generate diff
    const diff = generateDiff(existing, serialized);
    return { passed: false, isNew: false, diff };
  }
}

function generateDiff(expected: string, actual: string): string {
  const expLines = expected.split("\n");
  const actLines = actual.split("\n");
  const lines: string[] = [];

  const maxLen = Math.max(expLines.length, actLines.length);
  for (let i = 0; i < maxLen; i++) {
    if (i >= expLines.length) {
      lines.push(`+ ${actLines[i]}`);
    } else if (i >= actLines.length) {
      lines.push(`- ${expLines[i]}`);
    } else if (expLines[i] !== actLines[i]) {
      lines.push(`- ${expLines[i]}`);
      lines.push(`+ ${actLines[i]}`);
    }
  }

  return lines.join("\n");
}
```

**Usage:**

```typescript
const snap = new SnapshotManager({
  replacers: [
    // Replace UUIDs with placeholder
    (_, v) => typeof v === "string" && /^[0-9a-f]{8}-/.test(v)
      ? "[UUID]" : v,
  ],
});

// First run: creates snapshot file
const result = snap.match("user-response", {
  id: "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  name: "Alice",
  createdAt: new Date("2024-01-01"),
  roles: new Set(["admin", "user"]),
  preferences: { theme: "dark", lang: "en" },
});

// Snapshot file contains:
// {
//   "createdAt": "[Date: 2024-01-01T00:00:00.000Z]",
//   "id": "[UUID]",
//   "name": "Alice",
//   "preferences": {
//     "lang": "en",
//     "theme": "dark"
//   },
//   "roles": Set {
//     "admin",
//     "user"
//   }
// }

// Run with --update-snapshots to regenerate after intentional changes
```

Snapshot testing catches unintended changes in complex outputs (API responses, rendered HTML, serialized state) without manually writing expected values for every field.'''),

    ("js_deep2_24", r'''Implement a benchmark utility in TypeScript that accurately measures function performance with: warm-up runs, statistical analysis (mean, median, p95, standard deviation), comparison between implementations, and memory tracking.''',
     r'''<think>
Benchmarking in JS is tricky due to JIT compilation and GC. Key requirements:
1. Warm-up: run the function several times before measuring (JIT optimization).
2. Multiple iterations: run many times to get stable measurements.
3. Statistical analysis: mean, median, p95, stddev — single numbers lie.
4. Comparison: run two implementations side-by-side with the same inputs.
5. GC consideration: force GC between runs if possible (--expose-gc flag).
6. High-resolution timing: performance.now() for sub-ms accuracy.
7. Memory tracking: process.memoryUsage() before/after (Node.js only).
8. Output: formatted table with results.
</think>

```typescript
interface BenchmarkOptions {
  warmup?: number;     // Warm-up iterations (default: 10)
  iterations?: number; // Measurement iterations (default: 1000)
  minTime?: number;    // Minimum total time in ms (default: 1000)
}

interface BenchmarkResult {
  name: string;
  iterations: number;
  mean: number;      // ms
  median: number;    // ms
  min: number;       // ms
  max: number;       // ms
  p95: number;       // ms
  stddev: number;    // ms
  opsPerSec: number;
  heapUsed?: number; // bytes
}

class Benchmark {
  private results: BenchmarkResult[] = [];
  private opts: Required<BenchmarkOptions>;

  constructor(options: BenchmarkOptions = {}) {
    this.opts = {
      warmup: options.warmup ?? 10,
      iterations: options.iterations ?? 1000,
      minTime: options.minTime ?? 1000,
    };
  }

  add(name: string, fn: () => void): this {
    // Warm-up (let JIT optimize)
    for (let i = 0; i < this.opts.warmup; i++) fn();

    // Force GC if available
    if (typeof globalThis.gc === "function") globalThis.gc();
    const heapBefore = typeof process !== "undefined"
      ? process.memoryUsage().heapUsed : undefined;

    // Collect samples
    const samples: number[] = [];
    let totalTime = 0;
    let iterations = 0;

    while (iterations < this.opts.iterations || totalTime < this.opts.minTime) {
      const start = performance.now();
      fn();
      const elapsed = performance.now() - start;
      samples.push(elapsed);
      totalTime += elapsed;
      iterations++;
    }

    const heapAfter = typeof process !== "undefined"
      ? process.memoryUsage().heapUsed : undefined;

    // Calculate statistics
    samples.sort((a, b) => a - b);
    const mean = samples.reduce((a, b) => a + b, 0) / samples.length;
    const median = samples[Math.floor(samples.length / 2)];
    const p95 = samples[Math.floor(samples.length * 0.95)];
    const variance = samples.reduce((acc, s) => acc + Math.pow(s - mean, 2), 0) / samples.length;

    this.results.push({
      name,
      iterations,
      mean,
      median,
      min: samples[0],
      max: samples[samples.length - 1],
      p95,
      stddev: Math.sqrt(variance),
      opsPerSec: 1000 / mean,
      heapUsed: heapBefore !== undefined && heapAfter !== undefined
        ? heapAfter - heapBefore : undefined,
    });

    return this;
  }

  async addAsync(name: string, fn: () => Promise<void>): Promise<this> {
    for (let i = 0; i < this.opts.warmup; i++) await fn();

    const samples: number[] = [];
    let totalTime = 0;
    let iterations = 0;

    while (iterations < this.opts.iterations || totalTime < this.opts.minTime) {
      const start = performance.now();
      await fn();
      const elapsed = performance.now() - start;
      samples.push(elapsed);
      totalTime += elapsed;
      iterations++;
    }

    samples.sort((a, b) => a - b);
    const mean = samples.reduce((a, b) => a + b, 0) / samples.length;
    const median = samples[Math.floor(samples.length / 2)];
    const p95 = samples[Math.floor(samples.length * 0.95)];
    const variance = samples.reduce((acc, s) => acc + Math.pow(s - mean, 2), 0) / samples.length;

    this.results.push({
      name, iterations, mean, median,
      min: samples[0], max: samples[samples.length - 1],
      p95, stddev: Math.sqrt(variance),
      opsPerSec: 1000 / mean,
    });

    return this;
  }

  report(): void {
    console.log("\n" + "=".repeat(90));
    console.log("  BENCHMARK RESULTS");
    console.log("=".repeat(90));

    const header = [
      "Name".padEnd(25),
      "ops/s".padStart(12),
      "mean".padStart(10),
      "median".padStart(10),
      "p95".padStart(10),
      "stddev".padStart(10),
    ].join(" | ");

    console.log(header);
    console.log("-".repeat(90));

    // Sort by ops/sec descending
    const sorted = [...this.results].sort((a, b) => b.opsPerSec - a.opsPerSec);

    for (const r of sorted) {
      const row = [
        r.name.padEnd(25),
        formatNumber(r.opsPerSec).padStart(12),
        formatTime(r.mean).padStart(10),
        formatTime(r.median).padStart(10),
        formatTime(r.p95).padStart(10),
        formatTime(r.stddev).padStart(10),
      ].join(" | ");
      console.log(row);
    }

    // Comparison
    if (sorted.length >= 2) {
      const fastest = sorted[0];
      const slowest = sorted[sorted.length - 1];
      const ratio = fastest.opsPerSec / slowest.opsPerSec;
      console.log(`\n  "${fastest.name}" is ${ratio.toFixed(1)}x faster than "${slowest.name}"`);
    }

    console.log("=".repeat(90) + "\n");
  }
}

function formatTime(ms: number): string {
  if (ms < 0.001) return `${(ms * 1_000_000).toFixed(0)}ns`;
  if (ms < 1) return `${(ms * 1000).toFixed(1)}us`;
  return `${ms.toFixed(2)}ms`;
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return n.toFixed(0);
}
```

**Usage:**

```typescript
const bench = new Benchmark({ iterations: 10000 });

const data = Array.from({ length: 1000 }, (_, i) => i);

bench
  .add("for loop", () => {
    let sum = 0;
    for (let i = 0; i < data.length; i++) sum += data[i];
  })
  .add("for...of", () => {
    let sum = 0;
    for (const n of data) sum += n;
  })
  .add("reduce", () => {
    data.reduce((a, b) => a + b, 0);
  })
  .add("forEach", () => {
    let sum = 0;
    data.forEach(n => sum += n);
  })
  .report();

// ========================
//   BENCHMARK RESULTS
// ========================
//   Name                   |       ops/s |      mean |    median |       p95 |    stddev
//   for loop               |       8.2M  |    122ns  |    118ns  |    145ns  |     12ns
//   for...of               |       5.1M  |    196ns  |    189ns  |    234ns  |     18ns
//   reduce                 |       4.3M  |    233ns  |    225ns  |    278ns  |     22ns
//   forEach                |       3.8M  |    263ns  |    255ns  |    312ns  |     25ns
//
//   "for loop" is 2.2x faster than "forEach"
```'''),

    ("js_deep2_25", r'''Implement a complete error boundary system for React applications in TypeScript: class-based error boundary with fallback UI, error recovery, retry mechanism, and error reporting to an external service.''',
     r'''<think>
React error boundaries catch rendering errors in the component tree. Key design:
1. Class component (hooks don't support componentDidCatch).
2. getDerivedStateFromError: update state to show fallback UI.
3. componentDidCatch: log error info, report to service.
4. Retry mechanism: reset the error state to re-attempt rendering.
5. Fallback UI: configurable per-boundary (page-level vs component-level).
6. Error reporting: send to Sentry/DataDog/custom endpoint.
7. Recovery: detect if the re-render succeeds after retry.
8. Nested boundaries: different fallbacks for different sections.
</think>

```typescript
import React, { Component, ReactNode, ErrorInfo } from "react";

// ── Error Reporting Service ──

interface ErrorReport {
  error: Error;
  errorInfo: ErrorInfo;
  timestamp: number;
  url: string;
  userAgent: string;
  componentStack: string;
  metadata?: Record<string, unknown>;
}

class ErrorReporter {
  private endpoint: string;
  private queue: ErrorReport[] = [];
  private flushTimer: ReturnType<typeof setTimeout> | null = null;

  constructor(endpoint: string) {
    this.endpoint = endpoint;
  }

  report(error: Error, errorInfo: ErrorInfo, metadata?: Record<string, unknown>): void {
    this.queue.push({
      error: { name: error.name, message: error.message, stack: error.stack } as any,
      errorInfo,
      timestamp: Date.now(),
      url: typeof window !== "undefined" ? window.location.href : "",
      userAgent: typeof navigator !== "undefined" ? navigator.userAgent : "",
      componentStack: errorInfo.componentStack ?? "",
      metadata,
    });

    // Batch and flush
    if (!this.flushTimer) {
      this.flushTimer = setTimeout(() => this.flush(), 1000);
    }
  }

  private async flush(): Promise<void> {
    this.flushTimer = null;
    if (this.queue.length === 0) return;

    const batch = [...this.queue];
    this.queue = [];

    try {
      await fetch(this.endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ errors: batch }),
        keepalive: true,
      });
    } catch {
      // Re-queue on failure
      this.queue.unshift(...batch);
    }
  }
}

const errorReporter = new ErrorReporter("/api/errors");

// ── Error Boundary Component ──

interface ErrorBoundaryProps {
  children: ReactNode;
  fallback?: ReactNode | ((props: ErrorFallbackProps) => ReactNode);
  onError?: (error: Error, errorInfo: ErrorInfo) => void;
  onReset?: () => void;
  maxRetries?: number;
  reportErrors?: boolean;
  level?: "page" | "section" | "component";
}

interface ErrorFallbackProps {
  error: Error;
  resetError: () => void;
  retryCount: number;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
  retryCount: number;
}

class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  static defaultProps = {
    maxRetries: 3,
    reportErrors: true,
    level: "component",
  };

  state: ErrorBoundaryState = {
    hasError: false,
    error: null,
    retryCount: 0,
  };

  static getDerivedStateFromError(error: Error): Partial<ErrorBoundaryState> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo): void {
    // Report to external service
    if (this.props.reportErrors) {
      errorReporter.report(error, errorInfo, {
        level: this.props.level,
        retryCount: this.state.retryCount,
      });
    }

    // Custom error handler
    this.props.onError?.(error, errorInfo);

    console.error(`[ErrorBoundary:${this.props.level}]`, error, errorInfo.componentStack);
  }

  resetError = (): void => {
    this.setState((prev) => ({
      hasError: false,
      error: null,
      retryCount: prev.retryCount + 1,
    }));
    this.props.onReset?.();
  };

  render(): ReactNode {
    if (this.state.hasError) {
      const { fallback, maxRetries } = this.props;
      const canRetry = this.state.retryCount < (maxRetries ?? 3);

      // Custom fallback (function or element)
      if (typeof fallback === "function") {
        return fallback({
          error: this.state.error!,
          resetError: canRetry ? this.resetError : () => {},
          retryCount: this.state.retryCount,
        });
      }

      if (fallback) return fallback;

      // Default fallback based on level
      return this.renderDefaultFallback(canRetry);
    }

    return this.props.children;
  }

  private renderDefaultFallback(canRetry: boolean): ReactNode {
    const { level } = this.props;
    const { error, retryCount } = this.state;

    if (level === "page") {
      return React.createElement("div", {
        style: { padding: "40px", textAlign: "center" as const }
      },
        React.createElement("h1", null, "Something went wrong"),
        React.createElement("p", { style: { color: "#666" } }, error?.message),
        canRetry && React.createElement("button", {
          onClick: this.resetError,
          style: { padding: "8px 16px", marginTop: "16px", cursor: "pointer" },
        }, `Retry (${retryCount + 1}/${this.props.maxRetries})`)
      );
    }

    // Component-level: minimal inline fallback
    return React.createElement("div", {
      style: { padding: "8px", border: "1px solid #f5c6cb", borderRadius: "4px",
               backgroundColor: "#f8d7da", color: "#721c24" }
    },
      React.createElement("span", null, "Error loading component"),
      canRetry && React.createElement("button", {
        onClick: this.resetError,
        style: { marginLeft: "8px", cursor: "pointer" },
      }, "Retry")
    );
  }
}
```

**Usage:**

```tsx
// Page-level boundary
function App() {
  return (
    <ErrorBoundary level="page" maxRetries={2}>
      <Header />
      <main>
        {/* Section-level boundary */}
        <ErrorBoundary level="section" fallback={<div>Sidebar unavailable</div>}>
          <Sidebar />
        </ErrorBoundary>

        {/* Component-level with custom fallback */}
        <ErrorBoundary
          level="component"
          maxRetries={3}
          fallback={({ error, resetError, retryCount }) => (
            <div>
              <p>Chart failed: {error.message}</p>
              <button onClick={resetError}>
                Retry ({retryCount}/3)
              </button>
            </div>
          )}
          onError={(err) => console.error("Chart error:", err)}
        >
          <Chart data={data} />
        </ErrorBoundary>
      </main>
    </ErrorBoundary>
  );
}
```

**Key patterns:**
- **Nested boundaries**: page catches everything, section/component boundaries handle specific failures
- **Retry with limit**: prevents infinite re-render loops on persistent errors
- **Error reporting**: batched, async, with full component stack trace
- **Recovery**: `resetError` clears the error state, giving the component tree another chance'''),
]
