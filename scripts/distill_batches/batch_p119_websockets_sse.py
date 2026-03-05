"""Real-time — Server-Sent Events, WebRTC signaling, and real-time sync patterns."""

PAIRS = [
    (
        "api/server-sent-events",
        "Show Server-Sent Events patterns: SSE endpoint, event types, reconnection, and client handling.",
        '''Server-Sent Events (SSE) patterns:

```python
# --- FastAPI SSE endpoint ---

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
import asyncio
import json
from datetime import datetime, timezone
from typing import AsyncIterator

app = FastAPI()


class EventBroker:
    """Pub/sub broker for SSE connections."""

    def __init__(self):
        self._subscribers: dict[str, asyncio.Queue] = {}

    def subscribe(self, client_id: str) -> asyncio.Queue:
        queue = asyncio.Queue(maxsize=100)
        self._subscribers[client_id] = queue
        return queue

    def unsubscribe(self, client_id: str):
        self._subscribers.pop(client_id, None)

    async def publish(self, event_type: str, data: dict):
        message = format_sse(event_type, data)
        dead = []
        for client_id, queue in self._subscribers.items():
            try:
                queue.put_nowait(message)
            except asyncio.QueueFull:
                dead.append(client_id)
        for client_id in dead:
            self.unsubscribe(client_id)

    @property
    def subscriber_count(self) -> int:
        return len(self._subscribers)


broker = EventBroker()


def format_sse(event_type: str, data: dict, event_id: str | None = None) -> str:
    """Format data as SSE message."""
    lines = []
    if event_id:
        lines.append(f"id: {event_id}")
    lines.append(f"event: {event_type}")
    lines.append(f"data: {json.dumps(data)}")
    lines.append("")  # Empty line terminates message
    return "\\n".join(lines) + "\\n"


async def event_stream(client_id: str, request: Request) -> AsyncIterator[str]:
    """Generate SSE stream for a client."""
    queue = broker.subscribe(client_id)

    try:
        # Send initial connection event
        yield format_sse("connected", {"client_id": client_id})

        while True:
            # Check if client disconnected
            if await request.is_disconnected():
                break

            try:
                message = await asyncio.wait_for(queue.get(), timeout=30)
                yield message
            except asyncio.TimeoutError:
                # Send keepalive comment (prevents proxy timeouts)
                yield ": keepalive\\n\\n"

    finally:
        broker.unsubscribe(client_id)


@app.get("/events/stream")
async def sse_stream(request: Request, client_id: str):
    return StreamingResponse(
        event_stream(client_id, request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


@app.post("/events/publish")
async def publish_event(event_type: str, data: dict):
    await broker.publish(event_type, data)
    return {"subscribers": broker.subscriber_count}
```

```typescript
// --- Client-side SSE handling ---

class SSEClient {
  private eventSource: EventSource | null = null;
  private reconnectDelay = 1000;
  private maxReconnectDelay = 30000;

  constructor(
    private url: string,
    private handlers: Record<string, (data: any) => void>,
  ) {}

  connect(): void {
    this.eventSource = new EventSource(this.url);

    this.eventSource.onopen = () => {
      console.log('SSE connected');
      this.reconnectDelay = 1000;  // Reset delay on success
    };

    // Register typed event handlers
    for (const [eventType, handler] of Object.entries(this.handlers)) {
      this.eventSource.addEventListener(eventType, (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data);
          handler(data);
        } catch (e) {
          console.error(`Failed to parse SSE data for ${eventType}:`, e);
        }
      });
    }

    this.eventSource.onerror = () => {
      console.log('SSE error, reconnecting...');
      this.eventSource?.close();

      // Exponential backoff reconnect
      setTimeout(() => this.connect(), this.reconnectDelay);
      this.reconnectDelay = Math.min(
        this.reconnectDelay * 2,
        this.maxReconnectDelay,
      );
    };
  }

  disconnect(): void {
    this.eventSource?.close();
    this.eventSource = null;
  }
}

// Usage:
// const sse = new SSEClient('/events/stream?client_id=user-1', {
//   notification: (data) => showNotification(data),
//   update: (data) => updateUI(data),
//   connected: (data) => console.log('Connected:', data),
// });
// sse.connect();
```

SSE patterns:
1. **`text/event-stream`** — MIME type triggers browser SSE handling
2. **`event:` field** — typed events route to specific `addEventListener` handlers
3. **Keepalive comments** — `: keepalive` prevents proxy/CDN timeout (every 30s)
4. **`EventBroker`** — pub/sub with per-client queues and dead client cleanup
5. **Exponential backoff** — client reconnects with increasing delay on errors'''
    ),
    (
        "patterns/real-time-sync",
        "Show real-time data synchronization patterns: optimistic updates, conflict resolution, and offline sync.",
        '''Real-time data synchronization patterns:

```typescript
// --- Optimistic updates with rollback ---

interface OptimisticUpdate<T> {
  id: string;
  optimisticData: T;
  serverPromise: Promise<T>;
  rollback: () => void;
}

class OptimisticStore<T extends { id: string }> {
  private items: Map<string, T> = new Map();
  private pendingUpdates: Map<string, OptimisticUpdate<T>> = new Map();
  private listeners: Set<() => void> = new Set();

  getAll(): T[] {
    return Array.from(this.items.values());
  }

  subscribe(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private notify(): void {
    this.listeners.forEach((fn) => fn());
  }

  async optimisticUpdate(
    id: string,
    optimisticData: T,
    serverFn: () => Promise<T>,
  ): Promise<T> {
    // Save current state for rollback
    const previous = this.items.get(id);
    const rollback = () => {
      if (previous) {
        this.items.set(id, previous);
      } else {
        this.items.delete(id);
      }
      this.notify();
    };

    // Apply optimistic update immediately
    this.items.set(id, optimisticData);
    this.notify();

    try {
      // Send to server
      const serverData = await serverFn();
      // Update with server response (may differ from optimistic)
      this.items.set(id, serverData);
      this.notify();
      return serverData;
    } catch (error) {
      // Rollback on failure
      rollback();
      throw error;
    } finally {
      this.pendingUpdates.delete(id);
    }
  }
}


// --- Last-Write-Wins (LWW) conflict resolution ---

interface Timestamped<T> {
  data: T;
  updatedAt: number;  // Unix timestamp ms
  updatedBy: string;  // Client/user ID
}

function resolveConflictLWW<T>(
  local: Timestamped<T>,
  remote: Timestamped<T>,
): Timestamped<T> {
  // Most recent write wins
  if (remote.updatedAt > local.updatedAt) {
    return remote;
  }
  if (local.updatedAt > remote.updatedAt) {
    return local;
  }
  // Tie-break by client ID (deterministic)
  return local.updatedBy > remote.updatedBy ? local : remote;
}


// --- Operational Transform (simple text) ---

type TextOp =
  | { type: 'insert'; position: number; text: string }
  | { type: 'delete'; position: number; length: number };

function transformOps(op1: TextOp, op2: TextOp): TextOp {
  /**
   * Transform op1 against op2 that was applied first.
   * Returns adjusted op1 that produces same result.
   */
  if (op1.type === 'insert' && op2.type === 'insert') {
    if (op1.position <= op2.position) return op1;
    return { ...op1, position: op1.position + op2.text.length };
  }

  if (op1.type === 'insert' && op2.type === 'delete') {
    if (op1.position <= op2.position) return op1;
    return {
      ...op1,
      position: Math.max(op1.position - op2.length, op2.position),
    };
  }

  if (op1.type === 'delete' && op2.type === 'insert') {
    if (op1.position >= op2.position) {
      return { ...op1, position: op1.position + op2.text.length };
    }
    return op1;
  }

  // Both deletes
  if (op1.type === 'delete' && op2.type === 'delete') {
    if (op1.position >= op2.position + op2.length) {
      return { ...op1, position: op1.position - op2.length };
    }
    if (op1.position + op1.length <= op2.position) {
      return op1;
    }
    // Overlapping deletes — adjust
    return { ...op1, length: Math.max(0, op1.length - op2.length) };
  }

  return op1;
}


// --- Offline-first sync queue ---

interface SyncItem {
  id: string;
  action: 'create' | 'update' | 'delete';
  data: any;
  timestamp: number;
  retries: number;
}

class OfflineSyncQueue {
  private queue: SyncItem[] = [];
  private syncing = false;

  constructor(private apiClient: any) {
    // Load pending items from IndexedDB on init
    this.loadFromStorage();

    // Sync when online
    window.addEventListener('online', () => this.flush());
  }

  add(item: Omit<SyncItem, 'timestamp' | 'retries'>): void {
    this.queue.push({
      ...item,
      timestamp: Date.now(),
      retries: 0,
    });
    this.saveToStorage();

    if (navigator.onLine) {
      this.flush();
    }
  }

  async flush(): Promise<void> {
    if (this.syncing || this.queue.length === 0) return;
    this.syncing = true;

    try {
      while (this.queue.length > 0) {
        const item = this.queue[0];
        try {
          await this.apiClient.sync(item);
          this.queue.shift();  // Remove on success
        } catch (error) {
          item.retries++;
          if (item.retries > 5) {
            this.queue.shift();  // Drop after max retries
            console.error('Sync item dropped after max retries:', item);
          }
          break;  // Stop on first failure
        }
      }
    } finally {
      this.syncing = false;
      this.saveToStorage();
    }
  }

  private saveToStorage(): void {
    localStorage.setItem('sync_queue', JSON.stringify(this.queue));
  }

  private loadFromStorage(): void {
    const saved = localStorage.getItem('sync_queue');
    if (saved) this.queue = JSON.parse(saved);
  }
}
```

Real-time sync patterns:
1. **Optimistic updates** — apply locally first, rollback on server failure
2. **Last-Write-Wins** — timestamp-based conflict resolution with deterministic tie-breaking
3. **Operational Transform** — adjust concurrent text edits to converge
4. **Offline sync queue** — persist pending changes, flush when connectivity returns
5. **`navigator.onLine`** — detect connectivity and trigger sync automatically'''
    ),
]
"""
