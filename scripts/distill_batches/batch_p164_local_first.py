"""Local-first software — offline-first, sync engines."""

PAIRS = [
    (
        "frontend/local-first-architecture",
        "Design a local-first architecture using CRDTs and IndexedDB for an application that works offline and syncs when connected.",
        '''Local-first software stores data on the user\'s device as the primary copy, syncs with peers/servers when available, and resolves conflicts automatically using CRDTs.

```typescript
// --- Local-first data layer with Yjs + IndexedDB ---

import * as Y from 'yjs';
import { IndexeddbPersistence } from 'y-indexeddb';
import { WebsocketProvider } from 'y-websocket';

interface LocalFirstConfig {
  docId: string;
  wsUrl: string;
  authToken?: string;
}

interface SyncStatus {
  isOnline: boolean;
  isSynced: boolean;
  pendingChanges: number;
  lastSyncedAt: Date | null;
  connectedPeers: number;
}

class LocalFirstStore<T extends Record<string, unknown>> {
  private ydoc: Y.Doc;
  private indexeddb: IndexeddbPersistence;
  private wsProvider: WebsocketProvider | null = null;
  private statusListeners: Set<(status: SyncStatus) => void> = new Set();
  private changeListeners: Set<(doc: T) => void> = new Set();
  private status: SyncStatus = {
    isOnline: navigator.onLine,
    isSynced: false,
    pendingChanges: 0,
    lastSyncedAt: null,
    connectedPeers: 0,
  };

  constructor(private config: LocalFirstConfig) {
    this.ydoc = new Y.Doc();

    // 1. Load from IndexedDB first (instant, offline)
    this.indexeddb = new IndexeddbPersistence(config.docId, this.ydoc);
    this.indexeddb.on('synced', () => {
      console.log('Loaded from IndexedDB');
      this.notifyChangeListeners();
    });

    // 2. Connect to server when online
    this.setupNetworking();

    // 3. Listen for online/offline changes
    window.addEventListener('online', () => this.handleOnline());
    window.addEventListener('offline', () => this.handleOffline());

    // 4. Track document changes
    this.ydoc.on('update', () => {
      this.status.pendingChanges++;
      this.notifyChangeListeners();
    });
  }

  private setupNetworking(): void {
    if (!navigator.onLine) return;

    this.wsProvider = new WebsocketProvider(
      this.config.wsUrl,
      this.config.docId,
      this.ydoc,
      {
        connect: true,
        params: this.config.authToken
          ? { token: this.config.authToken }
          : {},
      }
    );

    this.wsProvider.on('status', ({ status }: { status: string }) => {
      this.status.isOnline = status === 'connected';
      this.notifyStatusListeners();
    });

    this.wsProvider.on('sync', (isSynced: boolean) => {
      if (isSynced) {
        this.status.isSynced = true;
        this.status.pendingChanges = 0;
        this.status.lastSyncedAt = new Date();
      }
      this.notifyStatusListeners();
    });

    this.wsProvider.awareness.on('change', () => {
      this.status.connectedPeers =
        this.wsProvider!.awareness.getStates().size - 1;
      this.notifyStatusListeners();
    });
  }

  private handleOnline(): void {
    this.status.isOnline = true;
    this.setupNetworking();
    this.notifyStatusListeners();
  }

  private handleOffline(): void {
    this.status.isOnline = false;
    this.status.isSynced = false;
    this.wsProvider?.disconnect();
    this.wsProvider = null;
    this.notifyStatusListeners();
  }

  // --- Public API ---

  getMap(name: string): Y.Map<unknown> {
    return this.ydoc.getMap(name);
  }

  getArray(name: string): Y.Array<unknown> {
    return this.ydoc.getArray(name);
  }

  getText(name: string): Y.Text {
    return this.ydoc.getText(name);
  }

  transact(fn: () => void): void {
    this.ydoc.transact(fn);
  }

  onStatusChange(listener: (status: SyncStatus) => void): () => void {
    this.statusListeners.add(listener);
    listener(this.status);
    return () => this.statusListeners.delete(listener);
  }

  onChange(listener: (doc: T) => void): () => void {
    this.changeListeners.add(listener);
    return () => this.changeListeners.delete(listener);
  }

  getStatus(): SyncStatus {
    return { ...this.status };
  }

  destroy(): void {
    this.wsProvider?.disconnect();
    this.indexeddb.destroy();
    this.ydoc.destroy();
    window.removeEventListener('online', () => this.handleOnline());
    window.removeEventListener('offline', () => this.handleOffline());
  }

  private notifyStatusListeners(): void {
    this.statusListeners.forEach(l => l({ ...this.status }));
  }

  private notifyChangeListeners(): void {
    this.changeListeners.forEach(l => l(this.ydoc.toJSON() as T));
  }
}
```

```typescript
// --- React hooks for local-first store ---

import { useState, useEffect, useCallback, useSyncExternalStore, createContext, useContext } from 'react';

// Context for the store
const StoreContext = createContext<LocalFirstStore<any> | null>(null);

function LocalFirstProvider({
  children,
  config,
}: {
  children: React.ReactNode;
  config: LocalFirstConfig;
}) {
  const [store] = useState(() => new LocalFirstStore(config));

  useEffect(() => {
    return () => store.destroy();
  }, [store]);

  return (
    <StoreContext.Provider value={store}>
      {children}
    </StoreContext.Provider>
  );
}

function useLocalFirstStore() {
  const store = useContext(StoreContext);
  if (!store) throw new Error('Missing LocalFirstProvider');
  return store;
}

function useSyncStatus(): SyncStatus {
  const store = useLocalFirstStore();
  const [status, setStatus] = useState<SyncStatus>(store.getStatus());

  useEffect(() => {
    return store.onStatusChange(setStatus);
  }, [store]);

  return status;
}

// Reactive hook for a Y.Map
function useYMap<T extends Record<string, unknown>>(name: string): [T, (key: string, value: unknown) => void] {
  const store = useLocalFirstStore();
  const ymap = store.getMap(name);
  const [state, setState] = useState<T>(ymap.toJSON() as T);

  useEffect(() => {
    const handler = () => setState(ymap.toJSON() as T);
    ymap.observe(handler);
    return () => ymap.unobserve(handler);
  }, [ymap]);

  const set = useCallback((key: string, value: unknown) => {
    ymap.set(key, value);
  }, [ymap]);

  return [state, set];
}

// Reactive hook for a Y.Array
function useYArray<T>(name: string): [T[], {
  push: (item: T) => void;
  delete: (index: number) => void;
  update: (index: number, item: T) => void;
}] {
  const store = useLocalFirstStore();
  const yarray = store.getArray(name);
  const [state, setState] = useState<T[]>(yarray.toJSON() as T[]);

  useEffect(() => {
    const handler = () => setState(yarray.toJSON() as T[]);
    yarray.observe(handler);
    return () => yarray.unobserve(handler);
  }, [yarray]);

  const actions = {
    push: useCallback((item: T) => {
      if (typeof item === 'object' && item !== null) {
        const ymap = new Y.Map();
        for (const [k, v] of Object.entries(item)) {
          ymap.set(k, v);
        }
        yarray.push([ymap]);
      } else {
        yarray.push([item]);
      }
    }, [yarray]),

    delete: useCallback((index: number) => {
      yarray.delete(index, 1);
    }, [yarray]),

    update: useCallback((index: number, item: T) => {
      const existing = yarray.get(index);
      if (existing instanceof Y.Map && typeof item === 'object' && item !== null) {
        store.transact(() => {
          for (const [k, v] of Object.entries(item)) {
            (existing as Y.Map<unknown>).set(k, v);
          }
        });
      }
    }, [yarray, store]),
  };

  return [state, actions];
}


// --- Usage: Collaborative Todo App ---

interface Todo {
  id: string;
  text: string;
  done: boolean;
  createdAt: number;
}

function TodoApp() {
  const [todos, { push, delete: deleteTodo, update }] = useYArray<Todo>('todos');
  const status = useSyncStatus();

  function addTodo(text: string) {
    push({
      id: crypto.randomUUID(),
      text,
      done: false,
      createdAt: Date.now(),
    });
  }

  function toggleTodo(index: number) {
    update(index, { ...todos[index], done: !todos[index].done });
  }

  return (
    <div>
      <SyncStatusBar status={status} />
      <ul>
        {todos.map((todo, i) => (
          <li key={todo.id}>
            <input
              type="checkbox"
              checked={todo.done}
              onChange={() => toggleTodo(i)}
            />
            <span>{todo.text}</span>
            <button onClick={() => deleteTodo(i)}>Delete</button>
          </li>
        ))}
      </ul>
      <AddTodoForm onAdd={addTodo} />
    </div>
  );
}

function SyncStatusBar({ status }: { status: SyncStatus }) {
  return (
    <div className={`sync-bar ${status.isOnline ? 'online' : 'offline'}`}>
      <span>{status.isOnline ? 'Online' : 'Offline'}</span>
      {status.isSynced && <span>Synced</span>}
      {status.pendingChanges > 0 && (
        <span>{status.pendingChanges} pending changes</span>
      )}
      {status.connectedPeers > 0 && (
        <span>{status.connectedPeers} peers</span>
      )}
    </div>
  );
}
```

```typescript
// --- IndexedDB wrapper for non-CRDT local data ---

interface DBSchema {
  settings: { key: string; value: unknown };
  files: { id: string; name: string; data: Blob; lastModified: number };
  syncQueue: { id: string; operation: string; payload: unknown; timestamp: number };
}

class LocalDB {
  private db: IDBDatabase | null = null;

  async open(name: string, version: number = 1): Promise<void> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(name, version);

      request.onupgradeneeded = (event) => {
        const db = (event.target as IDBOpenDBRequest).result;

        if (!db.objectStoreNames.contains('settings')) {
          db.createObjectStore('settings', { keyPath: 'key' });
        }
        if (!db.objectStoreNames.contains('files')) {
          const store = db.createObjectStore('files', { keyPath: 'id' });
          store.createIndex('name', 'name', { unique: false });
          store.createIndex('lastModified', 'lastModified', { unique: false });
        }
        if (!db.objectStoreNames.contains('syncQueue')) {
          const store = db.createObjectStore('syncQueue', { keyPath: 'id' });
          store.createIndex('timestamp', 'timestamp', { unique: false });
        }
      };

      request.onsuccess = () => {
        this.db = request.result;
        resolve();
      };

      request.onerror = () => reject(request.error);
    });
  }

  async get<T>(store: keyof DBSchema, key: string): Promise<T | undefined> {
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(store, 'readonly');
      const request = tx.objectStore(store).get(key);
      request.onsuccess = () => resolve(request.result as T | undefined);
      request.onerror = () => reject(request.error);
    });
  }

  async put<T extends DBSchema[keyof DBSchema]>(
    store: keyof DBSchema,
    value: T,
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(store, 'readwrite');
      tx.objectStore(store).put(value);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  async getAll<T>(store: keyof DBSchema): Promise<T[]> {
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(store, 'readonly');
      const request = tx.objectStore(store).getAll();
      request.onsuccess = () => resolve(request.result as T[]);
      request.onerror = () => reject(request.error);
    });
  }

  async delete(store: keyof DBSchema, key: string): Promise<void> {
    return new Promise((resolve, reject) => {
      const tx = this.db!.transaction(store, 'readwrite');
      tx.objectStore(store).delete(key);
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  // Queue operations for sync when back online
  async queueForSync(operation: string, payload: unknown): Promise<void> {
    await this.put('syncQueue', {
      id: crypto.randomUUID(),
      operation,
      payload,
      timestamp: Date.now(),
    });
  }

  // Flush sync queue when online
  async flushSyncQueue(
    sender: (op: string, payload: unknown) => Promise<boolean>,
  ): Promise<number> {
    const queue = await this.getAll<DBSchema['syncQueue']>('syncQueue');
    let synced = 0;

    // Process in order
    const sorted = queue.sort((a, b) => a.timestamp - b.timestamp);

    for (const item of sorted) {
      try {
        const success = await sender(item.operation, item.payload);
        if (success) {
          await this.delete('syncQueue', item.id);
          synced++;
        } else {
          break; // Stop on first failure (preserve order)
        }
      } catch {
        break;
      }
    }

    return synced;
  }
}
```

| Principle | Description | Implementation |
|---|---|---|
| No spinners | Data is local — reads are instant | IndexedDB + in-memory CRDT |
| Works offline | Full functionality without network | Service Worker + local storage |
| Network optional | Server enhances, not required | WebSocket sync when available |
| User owns data | Data lives on user's device | IndexedDB as primary store |
| Multi-device | Sync across devices | CRDT merge on reconnection |
| Collaboration | Real-time when online | WebSocket + awareness protocol |
| Conflict-free | No manual conflict resolution | CRDT automatic merge |

| Local-First Stack | Storage | Sync | CRDT | Best For |
|---|---|---|---|---|
| Yjs + y-indexeddb | IndexedDB | y-websocket / y-webrtc | Yjs | Rich text, kanban |
| Automerge + Repo | IndexedDB | automerge-repo | Automerge | JSON documents |
| PowerSync + Postgres | SQLite (WASM) | PowerSync service | LWW per row | SQL-based apps |
| Electric SQL | SQLite (local) | Electric service | Per-table CRDT | Postgres mirroring |
| DXOS + ECHO | Custom | Mesh network | Custom CRDT | P2P applications |
| TinyBase + CR-SQLite | SQLite (WASM) | Custom | CRR tables | Relational local-first |

Key patterns:
1. Local storage (IndexedDB) is the primary data store; server is a sync peer, not the source of truth
2. CRDTs handle conflict resolution automatically when peers reconnect
3. Network status UI (online/offline/syncing) gives users confidence about data state
4. Sync queue pattern: buffer operations while offline, flush when reconnected
5. Use `y-indexeddb` or `automerge-repo` storage adapters for seamless persistence
6. Awareness protocol tracks presence (cursors, who is online) as ephemeral state
7. Design for offline-first: every feature should work without a network connection'''
    ),
    (
        "frontend/offline-first-service-workers",
        "Build an offline-first application using Service Workers with caching strategies, background sync, and push notifications.",
        '''Service Workers act as a programmable network proxy, enabling offline functionality through cache management, background sync for deferred operations, and push notifications.

```typescript
// --- Service Worker registration ---

// main.ts — register the service worker
async function registerServiceWorker(): Promise<ServiceWorkerRegistration | null> {
  if (!('serviceWorker' in navigator)) {
    console.warn('Service Workers not supported');
    return null;
  }

  try {
    const registration = await navigator.serviceWorker.register(
      '/sw.js',
      { scope: '/', type: 'module' }
    );

    // Update handling
    registration.addEventListener('updatefound', () => {
      const newWorker = registration.installing;
      if (!newWorker) return;

      newWorker.addEventListener('statechange', () => {
        if (newWorker.state === 'activated' && navigator.serviceWorker.controller) {
          // New version available — prompt user to refresh
          showUpdateNotification();
        }
      });
    });

    // Listen for messages from SW
    navigator.serviceWorker.addEventListener('message', (event) => {
      const { type, payload } = event.data;
      switch (type) {
        case 'SYNC_COMPLETE':
          console.log('Background sync completed:', payload);
          break;
        case 'CACHE_UPDATED':
          console.log('Cache updated for:', payload.url);
          break;
      }
    });

    console.log('SW registered with scope:', registration.scope);
    return registration;
  } catch (error) {
    console.error('SW registration failed:', error);
    return null;
  }
}
```

```typescript
// --- Service Worker with caching strategies ---

// sw.ts
/// <reference lib="webworker" />
declare const self: ServiceWorkerGlobalScope;

const CACHE_VERSION = 'v1';
const STATIC_CACHE = `static-${CACHE_VERSION}`;
const DYNAMIC_CACHE = `dynamic-${CACHE_VERSION}`;
const API_CACHE = `api-${CACHE_VERSION}`;

const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/styles.css',
  '/app.js',
  '/manifest.json',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/offline.html',
];

// --- Install: pre-cache static assets ---
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(cache => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();  // activate immediately
});

// --- Activate: clean old caches ---
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key => key !== STATIC_CACHE && key !== DYNAMIC_CACHE && key !== API_CACHE)
          .map(key => caches.delete(key))
      )
    )
  );
  self.clients.claim();  // take control of all pages
});

// --- Fetch: routing and caching strategies ---
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // API requests: Network-first with cache fallback
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(networkFirst(request, API_CACHE));
    return;
  }

  // Static assets: Cache-first
  if (STATIC_ASSETS.includes(url.pathname)) {
    event.respondWith(cacheFirst(request, STATIC_CACHE));
    return;
  }

  // Images: Cache-first with dynamic cache
  if (request.destination === 'image') {
    event.respondWith(cacheFirst(request, DYNAMIC_CACHE));
    return;
  }

  // Everything else: Stale-while-revalidate
  event.respondWith(staleWhileRevalidate(request, DYNAMIC_CACHE));
});


// --- Caching strategy implementations ---

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
    return new Response('Offline', { status: 503 });
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

    // Return offline fallback for navigation requests
    if (request.mode === 'navigate') {
      const offline = await caches.match('/offline.html');
      return offline ?? new Response('Offline', { status: 503 });
    }

    return new Response(JSON.stringify({ error: 'Offline' }), {
      status: 503,
      headers: { 'Content-Type': 'application/json' },
    });
  }
}

async function staleWhileRevalidate(
  request: Request,
  cacheName: string,
): Promise<Response> {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);

  // Start fetch in background
  const fetchPromise = fetch(request).then(response => {
    if (response.ok) {
      cache.put(request, response.clone());
      // Notify clients about the update
      self.clients.matchAll().then(clients => {
        clients.forEach(client => {
          client.postMessage({
            type: 'CACHE_UPDATED',
            payload: { url: request.url },
          });
        });
      });
    }
    return response;
  }).catch(() => cached ?? new Response('Offline', { status: 503 }));

  // Return cached immediately, or wait for network
  return cached ?? fetchPromise;
}
```

```typescript
// --- Background Sync ---

// sw.ts — handle sync events
self.addEventListener('sync', (event: SyncEvent) => {
  if (event.tag === 'sync-pending-actions') {
    event.waitUntil(syncPendingActions());
  }

  if (event.tag === 'sync-offline-data') {
    event.waitUntil(syncOfflineData());
  }
});

async function syncPendingActions(): Promise<void> {
  const db = await openDB();
  const actions = await getAllFromStore(db, 'pendingActions');

  for (const action of actions) {
    try {
      const response = await fetch(action.url, {
        method: action.method,
        headers: action.headers,
        body: action.body,
      });

      if (response.ok) {
        await deleteFromStore(db, 'pendingActions', action.id);
      }
    } catch {
      // Will retry on next sync event
      break;
    }
  }

  // Notify the client
  const clients = await self.clients.matchAll();
  clients.forEach(client => {
    client.postMessage({ type: 'SYNC_COMPLETE', payload: { synced: actions.length } });
  });
}


// main.ts — queue actions for background sync
async function queueAction(
  url: string,
  method: string,
  body: unknown,
): Promise<void> {
  // Store the action in IndexedDB
  const db = await openDB();
  await putInStore(db, 'pendingActions', {
    id: crypto.randomUUID(),
    url,
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    timestamp: Date.now(),
  });

  // Request background sync
  const registration = await navigator.serviceWorker.ready;
  await registration.sync.register('sync-pending-actions');
}

// Usage: instead of direct fetch, queue for reliability
async function createTodo(text: string): Promise<void> {
  const todo = { id: crypto.randomUUID(), text, done: false };

  // Optimistic local update
  addTodoToLocalStore(todo);

  // Queue for sync (will send when online)
  await queueAction('/api/todos', 'POST', todo);
}


// --- Periodic Background Sync (optional) ---

// Request periodic sync for fresh data
async function requestPeriodicSync(): Promise<void> {
  const registration = await navigator.serviceWorker.ready;

  if ('periodicSync' in registration) {
    const status = await navigator.permissions.query({
      name: 'periodic-background-sync' as PermissionName,
    });

    if (status.state === 'granted') {
      await (registration as any).periodicSync.register('refresh-data', {
        minInterval: 60 * 60 * 1000,  // minimum: 1 hour
      });
    }
  }
}

// sw.ts — handle periodic sync
self.addEventListener('periodicsync', (event: any) => {
  if (event.tag === 'refresh-data') {
    event.waitUntil(refreshCachedData());
  }
});

async function refreshCachedData(): Promise<void> {
  const cache = await caches.open(API_CACHE);
  const keys = await cache.keys();

  for (const request of keys) {
    try {
      const response = await fetch(request);
      if (response.ok) {
        await cache.put(request, response);
      }
    } catch {
      // Ignore — will try again next interval
    }
  }
}
```

| Caching Strategy | Description | Best For |
|---|---|---|
| Cache-first | Check cache, fallback to network | Static assets, fonts, images |
| Network-first | Try network, fallback to cache | API data, dynamic content |
| Stale-while-revalidate | Return cache, update in background | Semi-dynamic content, feeds |
| Network-only | Always fetch from network | Real-time data, auth endpoints |
| Cache-only | Only serve from cache | Installed PWA shell |

| SW Lifecycle Event | When It Fires | Use Case |
|---|---|---|
| `install` | SW first installed | Pre-cache static assets |
| `activate` | New SW takes control | Clean old caches |
| `fetch` | Any network request | Intercept and cache |
| `sync` | Network available after offline | Flush pending actions |
| `periodicsync` | Browser-scheduled interval | Refresh cached data |
| `push` | Push message received | Show notification |

Key patterns:
1. Pre-cache critical assets in the `install` event for instant offline loading
2. Use Network-first for API data, Cache-first for static assets
3. Stale-while-revalidate gives instant loads while keeping data fresh
4. Background Sync queues failed requests and retries when the network returns
5. `self.skipWaiting()` + `self.clients.claim()` activates new SW versions immediately
6. Post messages to clients to notify about sync completions and cache updates
7. Always provide an `/offline.html` fallback for navigation requests that fail'''
    ),
    (
        "frontend/sync-engines",
        "Compare sync engine patterns including Electric SQL, PowerSync, and custom sync with conflict resolution for local-first applications.",
        '''Sync engines bridge local databases (SQLite, IndexedDB) with remote servers, handling bidirectional sync, conflict resolution, and real-time updates.

```typescript
// --- PowerSync: SQLite sync for React ---

// PowerSync syncs a local SQLite database with a Postgres backend
// using a CRDT-like approach (LWW per column)

import { PowerSyncDatabase } from '@powersync/web';
import { WASQLiteOpenFactory } from '@powersync/web';
import { PowerSyncContext, usePowerSync, useQuery, useStatus } from '@powersync/react';

// Define the schema (mirrors your Postgres tables)
const AppSchema = {
  todos: {
    id: 'TEXT PRIMARY KEY',
    text: 'TEXT NOT NULL',
    done: 'INTEGER NOT NULL DEFAULT 0',
    list_id: 'TEXT NOT NULL',
    created_at: 'TEXT NOT NULL',
    updated_at: 'TEXT NOT NULL',
  },
  lists: {
    id: 'TEXT PRIMARY KEY',
    name: 'TEXT NOT NULL',
    owner_id: 'TEXT NOT NULL',
    created_at: 'TEXT NOT NULL',
  },
} as const;

// Initialize PowerSync
const powerSync = new PowerSyncDatabase({
  database: new WASQLiteOpenFactory({ dbFilename: 'app.db' }),
  schema: AppSchema,
});

// Connect to your sync service
await powerSync.connect({
  endpoint: 'https://your-powersync-instance.com',
  token: async () => {
    // Return a JWT for authentication
    const res = await fetch('/api/auth/powersync-token');
    const { token } = await res.json();
    return token;
  },
});

// React components with live queries
function TodoList({ listId }: { listId: string }) {
  const { data: todos, isLoading } = useQuery<{
    id: string;
    text: string;
    done: number;
    created_at: string;
  }>(
    'SELECT * FROM todos WHERE list_id = ? ORDER BY created_at DESC',
    [listId]
  );

  const status = useStatus();
  const db = usePowerSync();

  async function addTodo(text: string) {
    await db.execute(
      'INSERT INTO todos (id, text, done, list_id, created_at, updated_at) VALUES (?, ?, 0, ?, datetime(), datetime())',
      [crypto.randomUUID(), text, listId]
    );
    // Automatically syncs to server when online
  }

  async function toggleTodo(id: string, currentDone: number) {
    await db.execute(
      'UPDATE todos SET done = ?, updated_at = datetime() WHERE id = ?',
      [currentDone ? 0 : 1, id]
    );
  }

  if (isLoading) return <p>Loading...</p>;

  return (
    <div>
      <SyncIndicator connected={status.connected} uploading={status.uploading} />
      <ul>
        {todos.map(todo => (
          <li key={todo.id}>
            <input
              type="checkbox"
              checked={!!todo.done}
              onChange={() => toggleTodo(todo.id, todo.done)}
            />
            {todo.text}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

```typescript
// --- Electric SQL: Postgres sync ---

// Electric SQL syncs a Postgres subset to a local SQLite database
// with full conflict resolution

// Define synced shapes (subsets of Postgres data)
import { ShapeStream, Shape } from '@electric-sql/client';

// Shape: a live, synced subset of a Postgres table
const todosShape = new ShapeStream({
  url: 'https://your-electric-instance.com/v1/shape',
  params: {
    table: 'todos',
    where: `list_id = '${listId}'`,
    columns: ['id', 'text', 'done', 'created_at'],
  },
});

// Subscribe to changes
const shape = new Shape(todosShape);

shape.subscribe(({ rows, isUpToDate }) => {
  console.log('Todos:', rows);
  console.log('Fully synced:', isUpToDate);
});

// Get current value
const { rows } = await shape.value;


// --- Custom sync engine pattern ---

interface SyncOperation {
  id: string;
  table: string;
  type: 'INSERT' | 'UPDATE' | 'DELETE';
  data: Record<string, unknown>;
  timestamp: number;
  clientId: string;
  version: number;
}

class CustomSyncEngine {
  private localDb: IDBDatabase;
  private pendingOps: SyncOperation[] = [];
  private serverVersion: number = 0;
  private clientId: string;
  private syncInterval: ReturnType<typeof setInterval> | null = null;

  constructor(
    localDb: IDBDatabase,
    private serverUrl: string,
  ) {
    this.localDb = localDb;
    this.clientId = this.getOrCreateClientId();
  }

  // Apply a local change
  async localChange(
    table: string,
    type: SyncOperation['type'],
    data: Record<string, unknown>,
  ): Promise<void> {
    const op: SyncOperation = {
      id: crypto.randomUUID(),
      table,
      type,
      data,
      timestamp: Date.now(),
      clientId: this.clientId,
      version: 0,  // assigned by server
    };

    // Apply locally
    await this.applyToLocal(op);

    // Queue for sync
    this.pendingOps.push(op);
    await this.persistPendingOps();

    // Try to sync immediately
    if (navigator.onLine) {
      await this.sync();
    }
  }

  // Pull changes from server + push pending local changes
  async sync(): Promise<{ pulled: number; pushed: number }> {
    let pushed = 0;
    let pulled = 0;

    try {
      // 1. Push local changes
      if (this.pendingOps.length > 0) {
        const response = await fetch(`${this.serverUrl}/sync/push`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            clientId: this.clientId,
            operations: this.pendingOps,
          }),
        });

        if (response.ok) {
          const { accepted } = await response.json();
          pushed = accepted.length;
          // Remove pushed ops from pending
          const acceptedIds = new Set(accepted.map((a: any) => a.id));
          this.pendingOps = this.pendingOps.filter(op => !acceptedIds.has(op.id));
          await this.persistPendingOps();
        }
      }

      // 2. Pull remote changes
      const pullResponse = await fetch(
        `${this.serverUrl}/sync/pull?since=${this.serverVersion}&clientId=${this.clientId}`
      );

      if (pullResponse.ok) {
        const { operations, version } = await pullResponse.json();
        pulled = operations.length;

        for (const op of operations) {
          await this.applyToLocal(op);
        }

        this.serverVersion = version;
        await this.persistServerVersion();
      }
    } catch (error) {
      console.warn('Sync failed, will retry:', error);
    }

    return { pulled, pushed };
  }

  // Start periodic sync
  startPeriodicSync(intervalMs: number = 30000): void {
    this.syncInterval = setInterval(() => {
      if (navigator.onLine) this.sync();
    }, intervalMs);

    window.addEventListener('online', () => this.sync());
  }

  stopPeriodicSync(): void {
    if (this.syncInterval) {
      clearInterval(this.syncInterval);
      this.syncInterval = null;
    }
  }

  private async applyToLocal(op: SyncOperation): Promise<void> {
    const tx = this.localDb.transaction(op.table, 'readwrite');
    const store = tx.objectStore(op.table);

    switch (op.type) {
      case 'INSERT':
      case 'UPDATE':
        store.put(op.data);
        break;
      case 'DELETE':
        store.delete(op.data.id as string);
        break;
    }

    await new Promise<void>((resolve, reject) => {
      tx.oncomplete = () => resolve();
      tx.onerror = () => reject(tx.error);
    });
  }

  private getOrCreateClientId(): string {
    let id = localStorage.getItem('sync_client_id');
    if (!id) {
      id = crypto.randomUUID();
      localStorage.setItem('sync_client_id', id);
    }
    return id;
  }

  private async persistPendingOps(): Promise<void> {
    localStorage.setItem('pending_ops', JSON.stringify(this.pendingOps));
  }

  private async persistServerVersion(): Promise<void> {
    localStorage.setItem('server_version', String(this.serverVersion));
  }
}
```

```typescript
// --- Server-side sync endpoint ---

import { type Request, type Response } from 'express';

interface ServerSyncState {
  operations: SyncOperation[];
  version: number;
}

// In-memory for demo; use a database in production
const syncState: ServerSyncState = { operations: [], version: 0 };

// Push endpoint: receive client changes
async function handlePush(req: Request, res: Response): Promise<void> {
  const { clientId, operations } = req.body;
  const accepted: SyncOperation[] = [];

  for (const op of operations) {
    // Conflict resolution: Last-Writer-Wins by timestamp
    const existing = syncState.operations.find(
      existing =>
        existing.table === op.table &&
        existing.data.id === op.data.id &&
        existing.timestamp > op.timestamp
    );

    if (!existing) {
      syncState.version++;
      const serverOp = { ...op, version: syncState.version };
      syncState.operations.push(serverOp);
      accepted.push(serverOp);
    }
  }

  res.json({ accepted, version: syncState.version });
}

// Pull endpoint: send changes since client's version
async function handlePull(req: Request, res: Response): Promise<void> {
  const since = parseInt(req.query.since as string, 10) || 0;
  const clientId = req.query.clientId as string;

  // Send operations the client hasn't seen
  // (excluding the client's own operations)
  const operations = syncState.operations.filter(
    op => op.version > since && op.clientId !== clientId
  );

  res.json({ operations, version: syncState.version });
}
```

| Sync Engine | Local DB | Server | Conflict Resolution | Real-time |
|---|---|---|---|---|
| PowerSync | SQLite (WASM) | Postgres + PowerSync | LWW per column | Yes (streaming) |
| Electric SQL | SQLite (WASM) | Postgres + Electric | LWW / custom rules | Yes (shapes) |
| Replicache | In-memory | Any (custom backend) | Server-authoritative | Yes (poke) |
| TinyBase | SQLite / Memory | Any | Custom merge | Via CRDTs |
| Instant (InstantDB) | IndexedDB | Managed service | Server-authoritative | Yes (subscriptions) |
| Custom + Yjs | IndexedDB | WebSocket server | CRDT merge | Yes |

| Conflict Strategy | Description | Data Loss Risk | Complexity |
|---|---|---|---|
| Last-Writer-Wins (LWW) | Latest timestamp wins | Possible (overwrite) | Low |
| Server-authoritative | Server decides | None (server is truth) | Low |
| CRDT merge | Mathematical convergence | None | Medium |
| Custom merge function | App-specific logic | Depends on logic | High |
| User-prompted resolution | Ask the user | None (user decides) | Medium |

Key patterns:
1. PowerSync and Electric SQL sync Postgres tables to local SQLite automatically
2. Push-pull sync: push local changes, pull remote changes, apply locally
3. Last-Writer-Wins (LWW) is the simplest conflict strategy — use per-column for best results
4. Server-authoritative sync (Replicache pattern) avoids conflicts by rebasing local mutations
5. Version vectors track what each client has seen to minimize data transfer
6. Periodic sync + event-driven sync (on online event) covers all connectivity scenarios
7. Always persist pending operations and server version to survive page reloads'''
    ),
    (
        "frontend/conflict-resolution-strategies",
        "Demonstrate conflict resolution strategies for local-first apps including LWW, merge functions, operational transform, and user-prompted resolution.",
        '''When multiple users edit the same data offline, conflicts are inevitable. Here are the major strategies to resolve them, from simple to sophisticated.

```typescript
// --- Strategy 1: Last-Writer-Wins (LWW) ---

// Simplest approach: the most recent write wins.
// Works well for independent fields, bad for collaborative text.

interface LWWField<T> {
  value: T;
  updatedAt: number;   // timestamp
  updatedBy: string;   // user/client ID
}

interface LWWDocument {
  id: string;
  fields: Record<string, LWWField<unknown>>;
}

function mergeLWW(local: LWWDocument, remote: LWWDocument): LWWDocument {
  const merged: LWWDocument = { id: local.id, fields: {} };
  const allKeys = new Set([
    ...Object.keys(local.fields),
    ...Object.keys(remote.fields),
  ]);

  for (const key of allKeys) {
    const localField = local.fields[key];
    const remoteField = remote.fields[key];

    if (!localField) {
      merged.fields[key] = remoteField;
    } else if (!remoteField) {
      merged.fields[key] = localField;
    } else if (remoteField.updatedAt > localField.updatedAt) {
      merged.fields[key] = remoteField;
    } else if (localField.updatedAt > remoteField.updatedAt) {
      merged.fields[key] = localField;
    } else {
      // Tie-break: higher user ID wins
      merged.fields[key] =
        localField.updatedBy > remoteField.updatedBy ? localField : remoteField;
    }
  }

  return merged;
}


// --- Per-field LWW for forms ---

interface UserProfile {
  name: LWWField<string>;
  email: LWWField<string>;
  bio: LWWField<string>;
  avatar: LWWField<string>;
}

function updateField<T>(
  field: LWWField<T>,
  value: T,
  userId: string,
): LWWField<T> {
  return { value, updatedAt: Date.now(), updatedBy: userId };
}

// Alice changes name, Bob changes email — no conflict!
// Alice changes name, Bob changes name — latest timestamp wins
```

```typescript
// --- Strategy 2: Three-way merge ---

// Compare local and remote against a common ancestor.
// Fields changed by only one side are accepted; both-changed = conflict.

interface MergeResult<T> {
  merged: T;
  conflicts: Array<{
    field: string;
    ancestor: unknown;
    local: unknown;
    remote: unknown;
  }>;
  autoResolved: string[];
}

function threeWayMerge<T extends Record<string, unknown>>(
  ancestor: T,
  local: T,
  remote: T,
): MergeResult<T> {
  const merged = { ...ancestor } as Record<string, unknown>;
  const conflicts: MergeResult<T>['conflicts'] = [];
  const autoResolved: string[] = [];

  const allKeys = new Set([
    ...Object.keys(ancestor),
    ...Object.keys(local),
    ...Object.keys(remote),
  ]);

  for (const key of allKeys) {
    const ancestorVal = ancestor[key];
    const localVal = local[key];
    const remoteVal = remote[key];

    const localChanged = !deepEqual(ancestorVal, localVal);
    const remoteChanged = !deepEqual(ancestorVal, remoteVal);

    if (!localChanged && !remoteChanged) {
      // No change
      merged[key] = ancestorVal;
    } else if (localChanged && !remoteChanged) {
      // Only local changed — accept local
      merged[key] = localVal;
      autoResolved.push(key);
    } else if (!localChanged && remoteChanged) {
      // Only remote changed — accept remote
      merged[key] = remoteVal;
      autoResolved.push(key);
    } else if (deepEqual(localVal, remoteVal)) {
      // Both changed to same value — no conflict
      merged[key] = localVal;
      autoResolved.push(key);
    } else {
      // Both changed to different values — CONFLICT
      conflicts.push({
        field: key,
        ancestor: ancestorVal,
        local: localVal,
        remote: remoteVal,
      });
      // Default: keep local (or could keep remote)
      merged[key] = localVal;
    }
  }

  return { merged: merged as T, conflicts, autoResolved };
}

function deepEqual(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}
```

```typescript
// --- Strategy 3: Custom merge functions per data type ---

type MergeFn<T> = (ancestor: T, local: T, remote: T) => T;

const mergeStrategies: Record<string, MergeFn<any>> = {
  // Numeric fields: sum the deltas
  'counter': (ancestor: number, local: number, remote: number) => {
    const localDelta = local - ancestor;
    const remoteDelta = remote - ancestor;
    return ancestor + localDelta + remoteDelta;
  },

  // Sets: union
  'tags': (ancestor: string[], local: string[], remote: string[]) => {
    const added = new Set([
      ...local.filter(t => !ancestor.includes(t)),
      ...remote.filter(t => !ancestor.includes(t)),
    ]);
    const removed = new Set([
      ...ancestor.filter(t => !local.includes(t)),
      ...ancestor.filter(t => !remote.includes(t)),
    ]);
    const base = new Set(ancestor);
    added.forEach(t => base.add(t));
    removed.forEach(t => base.delete(t));
    return [...base];
  },

  // Boolean: OR (if either side set to true, result is true)
  'completed': (ancestor: boolean, local: boolean, remote: boolean) => {
    return local || remote;
  },

  // List: merge by ID (add new items from both, resolve item conflicts)
  'items': (
    ancestor: Array<{ id: string; [key: string]: unknown }>,
    local: Array<{ id: string; [key: string]: unknown }>,
    remote: Array<{ id: string; [key: string]: unknown }>,
  ) => {
    const ancestorMap = new Map(ancestor.map(i => [i.id, i]));
    const localMap = new Map(local.map(i => [i.id, i]));
    const remoteMap = new Map(remote.map(i => [i.id, i]));
    const allIds = new Set([...localMap.keys(), ...remoteMap.keys()]);

    const result: Array<{ id: string; [key: string]: unknown }> = [];

    for (const id of allIds) {
      const anc = ancestorMap.get(id);
      const loc = localMap.get(id);
      const rem = remoteMap.get(id);

      if (loc && !rem && anc) continue;  // remote deleted
      if (!loc && rem && anc) continue;  // local deleted

      if (loc && rem) {
        // Both have it — merge fields
        result.push(loc); // simplified: prefer local
      } else if (loc) {
        result.push(loc);
      } else if (rem) {
        result.push(rem);
      }
    }

    return result;
  },
};


// --- Strategy 4: User-prompted conflict resolution ---

interface ConflictPrompt<T> {
  field: string;
  localValue: T;
  localUser: string;
  localTimestamp: Date;
  remoteValue: T;
  remoteUser: string;
  remoteTimestamp: Date;
}

// React component for conflict resolution UI
function ConflictResolver<T>({
  conflict,
  onResolve,
}: {
  conflict: ConflictPrompt<T>;
  onResolve: (value: T) => void;
}) {
  return (
    <div className="conflict-dialog" role="alertdialog">
      <h3>Conflict in "{conflict.field}"</h3>
      <div className="conflict-options">
        <div className="option">
          <h4>Your change ({conflict.localUser})</h4>
          <p>{String(conflict.localValue)}</p>
          <time>{conflict.localTimestamp.toLocaleString()}</time>
          <button onClick={() => onResolve(conflict.localValue)}>
            Keep mine
          </button>
        </div>
        <div className="option">
          <h4>Their change ({conflict.remoteUser})</h4>
          <p>{String(conflict.remoteValue)}</p>
          <time>{conflict.remoteTimestamp.toLocaleString()}</time>
          <button onClick={() => onResolve(conflict.remoteValue)}>
            Keep theirs
          </button>
        </div>
      </div>
    </div>
  );
}


// --- Hybrid: auto-resolve what you can, prompt for the rest ---

async function resolveConflicts<T extends Record<string, unknown>>(
  ancestor: T,
  local: T,
  remote: T,
  customMerges: Record<string, MergeFn<any>>,
  promptUser: (conflict: ConflictPrompt<unknown>) => Promise<unknown>,
): Promise<T> {
  const result = threeWayMerge(ancestor, local, remote);

  // Apply custom merge strategies
  for (const conflict of [...result.conflicts]) {
    const strategy = customMerges[conflict.field];
    if (strategy) {
      (result.merged as Record<string, unknown>)[conflict.field] =
        strategy(conflict.ancestor, conflict.local, conflict.remote);
      result.conflicts = result.conflicts.filter(c => c !== conflict);
    }
  }

  // Prompt user for remaining conflicts
  for (const conflict of result.conflicts) {
    const resolved = await promptUser({
      field: conflict.field,
      localValue: conflict.local,
      localUser: 'You',
      localTimestamp: new Date(),
      remoteValue: conflict.remote,
      remoteUser: 'Collaborator',
      remoteTimestamp: new Date(),
    });
    (result.merged as Record<string, unknown>)[conflict.field] = resolved;
  }

  return result.merged;
}
```

| Strategy | Automatic | Data Loss | User Effort | Best For |
|---|---|---|---|---|
| Last-Writer-Wins | Yes | Possible | None | Independent fields, settings |
| Three-way merge | Partial | On true conflicts | Minimal | Documents, structured data |
| Custom merge functions | Yes | None (if correct) | None | Domain-specific types (counters, sets) |
| CRDT merge | Yes | None | None | Collaborative text, shared state |
| User-prompted | No | None (user decides) | High | Critical data, rare conflicts |
| Server-authoritative | Yes | Possible | None | Gaming, financial transactions |

| When to Use | Strategy |
|---|---|
| Simple key-value settings | LWW per field |
| Rich text editing | CRDT (Yjs, Automerge) |
| Form data with independent fields | Three-way merge + LWW fallback |
| Shopping cart quantities | Custom merge (sum deltas) |
| Tag/label sets | Custom merge (set union) |
| Financial records | Server-authoritative |
| Medical/legal documents | User-prompted resolution |

Key patterns:
1. LWW is simplest but can lose concurrent edits — use per-field, not per-document
2. Three-way merge requires storing the common ancestor (base version) for comparison
3. Custom merge functions encode domain knowledge (counters sum, sets union, booleans OR)
4. CRDTs are the gold standard for collaborative text — no conflicts by design
5. User-prompted resolution should be the last resort — most conflicts can be auto-resolved
6. Hybrid approach: auto-resolve what you can, prompt for true conflicts only
7. Always use Hybrid Logical Clocks instead of wall clocks for reliable timestamp ordering'''
    ),

    # --- 5. CRDT-Based Sync with Optimistic Updates ---
    (
        "frontend/crdt-optimistic-sync",
        "Build a local-first task manager with CRDT-based sync using Yjs, optimistic updates, "
        "and a React hook that provides automatic conflict resolution. Show the full stack: "
        "IndexedDB persistence, WebSocket sync, and a UI that works seamlessly offline.",
        """\
# CRDT-Based Sync with Optimistic Updates

## The Local-First Loop

```
User action
  -> Apply to local Y.Doc immediately (optimistic)
  -> Persist to IndexedDB (offline durability)
  -> Send update via WebSocket (when online)
  -> Server merges via CRDT (no conflicts possible)
  -> Server broadcasts to other clients
  -> Other clients apply update to their Y.Doc

Key insight: because CRDTs guarantee convergence, every local
write is automatically an "optimistic update" that never needs
to be rolled back.
```

## Full-Stack Implementation

```typescript
// lib/local-first-store.ts
import * as Y from "yjs";
import { IndexeddbPersistence } from "y-indexeddb";
import { WebsocketProvider } from "y-websocket";

interface Task {
  id: string;
  title: string;
  completed: boolean;
  createdAt: number;
  updatedAt: number;
}

class LocalFirstStore {
  private doc: Y.Doc;
  private tasks: Y.Map<any>;
  private persistence: IndexeddbPersistence;
  private provider: WebsocketProvider | null = null;
  private listeners: Set<() => void> = new Set();

  constructor(private roomId: string) {
    this.doc = new Y.Doc();
    this.tasks = this.doc.getMap("tasks");

    // 1. IndexedDB persistence (works offline)
    this.persistence = new IndexeddbPersistence(roomId, this.doc);
    this.persistence.once("synced", () => {
      console.log("Loaded from IndexedDB");
      this.notify();
    });

    // 2. Observe all changes (local + remote)
    this.tasks.observeDeep(() => this.notify());
  }

  connect(wsUrl: string) {
    // 3. WebSocket sync (when online)
    this.provider = new WebsocketProvider(wsUrl, this.roomId, this.doc, {
      connect: true,
      maxBackoffTime: 10_000,
    });
    this.provider.on("status", ({ status }: any) => {
      console.log(`Sync status: ${status}`);
      this.notify();
    });
  }

  // --- Optimistic CRUD operations ---
  // All writes apply instantly to the local Y.Doc.
  // The CRDT guarantees they will merge correctly with remote changes.

  addTask(title: string): string {
    const id = crypto.randomUUID();
    const now = Date.now();
    this.doc.transact(() => {
      const taskMap = new Y.Map();
      taskMap.set("id", id);
      taskMap.set("title", title);
      taskMap.set("completed", false);
      taskMap.set("createdAt", now);
      taskMap.set("updatedAt", now);
      this.tasks.set(id, taskMap);
    });
    return id;
  }

  toggleTask(id: string) {
    const task = this.tasks.get(id) as Y.Map<any> | undefined;
    if (!task) return;
    this.doc.transact(() => {
      task.set("completed", !task.get("completed"));
      task.set("updatedAt", Date.now());
    });
  }

  updateTitle(id: string, title: string) {
    const task = this.tasks.get(id) as Y.Map<any> | undefined;
    if (!task) return;
    this.doc.transact(() => {
      task.set("title", title);
      task.set("updatedAt", Date.now());
    });
  }

  deleteTask(id: string) {
    this.tasks.delete(id);
  }

  // --- Read operations ---

  getAllTasks(): Task[] {
    const result: Task[] = [];
    this.tasks.forEach((taskMap: Y.Map<any>) => {
      result.push({
        id: taskMap.get("id"),
        title: taskMap.get("title"),
        completed: taskMap.get("completed"),
        createdAt: taskMap.get("createdAt"),
        updatedAt: taskMap.get("updatedAt"),
      });
    });
    return result.sort((a, b) => b.createdAt - a.createdAt);
  }

  isOnline(): boolean {
    return this.provider?.wsconnected ?? false;
  }

  // --- Subscription ---

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify() {
    for (const listener of this.listeners) listener();
  }

  destroy() {
    this.provider?.disconnect();
    this.persistence.destroy();
    this.doc.destroy();
  }
}

export { LocalFirstStore };
export type { Task };
```

## React Integration

```tsx
// hooks/useLocalFirstTasks.ts
"use client";
import { useRef, useSyncExternalStore, useCallback } from "react";
import { LocalFirstStore, type Task } from "../lib/local-first-store";

export function useLocalFirstTasks(roomId: string, wsUrl: string) {
  const storeRef = useRef<LocalFirstStore | null>(null);

  if (!storeRef.current) {
    storeRef.current = new LocalFirstStore(roomId);
    storeRef.current.connect(wsUrl);
  }

  const store = storeRef.current;

  const tasks = useSyncExternalStore(
    (cb) => store.subscribe(cb),
    () => store.getAllTasks(),
    () => [] as Task[]
  );

  const isOnline = useSyncExternalStore(
    (cb) => store.subscribe(cb),
    () => store.isOnline(),
    () => false
  );

  return {
    tasks,
    isOnline,
    addTask: useCallback((title: string) => store.addTask(title), [store]),
    toggleTask: useCallback((id: string) => store.toggleTask(id), [store]),
    updateTitle: useCallback(
      (id: string, title: string) => store.updateTitle(id, title),
      [store]
    ),
    deleteTask: useCallback((id: string) => store.deleteTask(id), [store]),
  };
}
```

## Task Manager Component

```tsx
// components/TaskManager.tsx
"use client";
import { useState } from "react";
import { useLocalFirstTasks } from "../hooks/useLocalFirstTasks";

export function TaskManager({ roomId }: { roomId: string }) {
  const {
    tasks, isOnline, addTask, toggleTask, updateTitle, deleteTask,
  } = useLocalFirstTasks(roomId, "ws://localhost:4444");
  const [newTitle, setNewTitle] = useState("");

  return (
    <div className="task-manager">
      <header>
        <span className={`status ${isOnline ? "online" : "offline"}`}>
          {isOnline ? "Synced" : "Working offline"}
        </span>
        <span>{tasks.length} tasks</span>
      </header>

      <form onSubmit={(e) => {
        e.preventDefault();
        if (newTitle.trim()) { addTask(newTitle.trim()); setNewTitle(""); }
      }}>
        <input
          value={newTitle}
          onChange={(e) => setNewTitle(e.target.value)}
          placeholder="Add a task..."
        />
        <button type="submit">Add</button>
      </form>

      <ul>
        {tasks.map((task) => (
          <li key={task.id} className={task.completed ? "done" : ""}>
            <input
              type="checkbox"
              checked={task.completed}
              onChange={() => toggleTask(task.id)}
            />
            <input
              value={task.title}
              onChange={(e) => updateTitle(task.id, e.target.value)}
              className="task-title"
            />
            <button onClick={() => deleteTask(task.id)}>Delete</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

| Pattern | How It Works | Conflict Handling |
|---|---|---|
| Optimistic local write | Apply to Y.Doc immediately | CRDT auto-merge |
| IndexedDB persistence | y-indexeddb stores incremental updates | Replay on reload |
| WebSocket sync | y-websocket exchanges state diffs | CRDT convergence |
| Cross-tab sync | BroadcastChannel (built into y-websocket) | Same Y.Doc |
| Offline queue | Updates accumulate in Y.Doc | Merge on reconnect |

Key patterns:
1. Every write is optimistic because CRDTs guarantee convergence with no rollback
2. Y.Map per entity gives field-level last-writer-wins (not whole-document LWW)
3. IndexedDB persistence via y-indexeddb survives page reload and browser restart
4. WebSocket provider handles reconnection with exponential backoff automatically
5. `useSyncExternalStore` bridges the Yjs observable store to React re-renders
6. `doc.transact()` batches multiple field changes into a single update event
7. BroadcastChannel syncs across tabs without extra WebSocket connections"""
    ),
]
