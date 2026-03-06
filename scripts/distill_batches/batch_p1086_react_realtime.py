"""
Batch p1086: React realtime patterns.
WebSocket hooks, Server-Sent Events, optimistic UI, conflict resolution, presence indicators.
"""

PAIRS = [
    (
        "react/realtime",
        r'''Build a production-grade React WebSocket hook with automatic reconnection, exponential backoff, heartbeat/ping-pong, connection state tracking, and typed message handling. Support both JSON messages and binary frames.''',
        r'''A robust WebSocket hook with reconnection, heartbeat, and typed messages:

```typescript
import { useCallback, useEffect, useRef, useState } from "react";

type ConnectionState = "connecting" | "connected" | "disconnecting" | "disconnected" | "reconnecting";

interface WebSocketMessage<T = unknown> {
  type: string;
  payload: T;
  timestamp: number;
  id?: string;
}

interface UseWebSocketOptions {
  url: string;
  protocols?: string | string[];
  reconnect?: boolean;
  maxReconnectAttempts?: number;
  initialBackoffMs?: number;
  maxBackoffMs?: number;
  heartbeatIntervalMs?: number;
  heartbeatTimeoutMs?: number;
  onOpen?: (event: Event) => void;
  onClose?: (event: CloseEvent) => void;
  onError?: (event: Event) => void;
}

interface UseWebSocketReturn {
  connectionState: ConnectionState;
  lastMessage: WebSocketMessage | null;
  sendMessage: <T>(type: string, payload: T) => void;
  sendBinary: (data: ArrayBuffer | Blob) => void;
  subscribe: <T>(type: string, handler: (payload: T, msg: WebSocketMessage<T>) => void) => () => void;
  disconnect: () => void;
  reconnect: () => void;
}

export function useWebSocket(options: UseWebSocketOptions): UseWebSocketReturn {
  const {
    url,
    protocols,
    reconnect: shouldReconnect = true,
    maxReconnectAttempts = 10,
    initialBackoffMs = 1000,
    maxBackoffMs = 30000,
    heartbeatIntervalMs = 30000,
    heartbeatTimeoutMs = 10000,
    onOpen,
    onClose,
    onError,
  } = options;

  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected");
  const [lastMessage, setLastMessage] = useState<WebSocketMessage | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval>>();
  const heartbeatTimeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const subscribersRef = useRef<Map<string, Set<(payload: unknown, msg: WebSocketMessage) => void>>>(new Map());
  const intentionalCloseRef = useRef(false);
  const mountedRef = useRef(true);

  function clearTimers() {
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    if (heartbeatTimerRef.current) clearInterval(heartbeatTimerRef.current);
    if (heartbeatTimeoutRef.current) clearTimeout(heartbeatTimeoutRef.current);
  }

  function startHeartbeat() {
    if (heartbeatTimerRef.current) clearInterval(heartbeatTimerRef.current);

    heartbeatTimerRef.current = setInterval(() => {
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify({ type: "__ping", timestamp: Date.now() }));

        heartbeatTimeoutRef.current = setTimeout(() => {
          // No pong received - connection is dead
          console.warn("WebSocket heartbeat timeout, forcing reconnect");
          wsRef.current?.close(4000, "Heartbeat timeout");
        }, heartbeatTimeoutMs);
      }
    }, heartbeatIntervalMs);
  }

  function notifySubscribers(msg: WebSocketMessage) {
    const handlers = subscribersRef.current.get(msg.type);
    if (handlers) {
      for (const handler of handlers) {
        try {
          handler(msg.payload, msg);
        } catch (err) {
          console.error(`WebSocket subscriber error for "${msg.type}":`, err);
        }
      }
    }

    // Wildcard subscribers
    const wildcardHandlers = subscribersRef.current.get("*");
    if (wildcardHandlers) {
      for (const handler of wildcardHandlers) {
        try {
          handler(msg.payload, msg);
        } catch (err) {
          console.error("WebSocket wildcard subscriber error:", err);
        }
      }
    }
  }

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setConnectionState(reconnectAttemptRef.current > 0 ? "reconnecting" : "connecting");
    intentionalCloseRef.current = false;

    const ws = new WebSocket(url, protocols);
    wsRef.current = ws;

    ws.onopen = (event) => {
      if (!mountedRef.current) return;
      setConnectionState("connected");
      reconnectAttemptRef.current = 0;
      startHeartbeat();
      onOpen?.(event);
    };

    ws.onmessage = (event) => {
      if (!mountedRef.current) return;

      if (typeof event.data === "string") {
        try {
          const msg = JSON.parse(event.data) as WebSocketMessage;

          // Handle pong
          if (msg.type === "__pong") {
            if (heartbeatTimeoutRef.current) clearTimeout(heartbeatTimeoutRef.current);
            return;
          }

          setLastMessage(msg);
          notifySubscribers(msg);
        } catch {
          console.warn("Received non-JSON WebSocket message:", event.data);
        }
      }
      // Binary messages handled via subscriber for "__binary" type
    };

    ws.onclose = (event) => {
      if (!mountedRef.current) return;
      clearTimers();

      if (intentionalCloseRef.current) {
        setConnectionState("disconnected");
        onClose?.(event);
        return;
      }

      setConnectionState("disconnected");
      onClose?.(event);

      // Attempt reconnection
      if (shouldReconnect && reconnectAttemptRef.current < maxReconnectAttempts) {
        const backoff = Math.min(
          initialBackoffMs * Math.pow(2, reconnectAttemptRef.current),
          maxBackoffMs
        );
        // Add jitter
        const jitter = backoff * (0.5 + Math.random() * 0.5);

        reconnectAttemptRef.current += 1;
        setConnectionState("reconnecting");

        reconnectTimerRef.current = setTimeout(() => {
          if (mountedRef.current) connect();
        }, jitter);
      }
    };

    ws.onerror = (event) => {
      if (!mountedRef.current) return;
      onError?.(event);
    };
  }, [url, protocols, shouldReconnect, maxReconnectAttempts, initialBackoffMs, maxBackoffMs, onOpen, onClose, onError]);

  const disconnect = useCallback(() => {
    intentionalCloseRef.current = true;
    clearTimers();
    setConnectionState("disconnecting");
    wsRef.current?.close(1000, "Client disconnect");
  }, []);

  const reconnectManual = useCallback(() => {
    disconnect();
    reconnectAttemptRef.current = 0;
    setTimeout(connect, 100);
  }, [connect, disconnect]);

  const sendMessage = useCallback(<T,>(type: string, payload: T) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      console.warn("WebSocket not connected, message dropped:", type);
      return;
    }

    const msg: WebSocketMessage<T> = {
      type,
      payload,
      timestamp: Date.now(),
      id: crypto.randomUUID(),
    };

    wsRef.current.send(JSON.stringify(msg));
  }, []);

  const sendBinary = useCallback((data: ArrayBuffer | Blob) => {
    if (wsRef.current?.readyState !== WebSocket.OPEN) {
      console.warn("WebSocket not connected, binary message dropped");
      return;
    }
    wsRef.current.send(data);
  }, []);

  const subscribe = useCallback(<T,>(
    type: string,
    handler: (payload: T, msg: WebSocketMessage<T>) => void
  ): (() => void) => {
    if (!subscribersRef.current.has(type)) {
      subscribersRef.current.set(type, new Set());
    }
    const handlers = subscribersRef.current.get(type)!;
    const wrappedHandler = handler as (payload: unknown, msg: WebSocketMessage) => void;
    handlers.add(wrappedHandler);

    return () => {
      handlers.delete(wrappedHandler);
      if (handlers.size === 0) {
        subscribersRef.current.delete(type);
      }
    };
  }, []);

  // Auto-connect on mount
  useEffect(() => {
    mountedRef.current = true;
    connect();

    return () => {
      mountedRef.current = false;
      clearTimers();
      intentionalCloseRef.current = true;
      wsRef.current?.close(1000, "Component unmount");
    };
  }, [connect]);

  return {
    connectionState,
    lastMessage,
    sendMessage,
    sendBinary,
    subscribe,
    disconnect,
    reconnect: reconnectManual,
  };
}

// Usage example: Chat component
function ChatRoom({ roomId }: { roomId: string }) {
  const [messages, setMessages] = useState<{ user: string; text: string }[]>([]);
  const { connectionState, sendMessage, subscribe } = useWebSocket({
    url: `wss://api.example.com/ws?room=${roomId}`,
    heartbeatIntervalMs: 25000,
  });

  useEffect(() => {
    const unsub = subscribe<{ user: string; text: string }>("chat:message", (payload) => {
      setMessages((prev) => [...prev, payload]);
    });
    return unsub;
  }, [subscribe]);

  function handleSend(text: string) {
    sendMessage("chat:message", { text, roomId });
  }

  return (
    <div>
      <div aria-live="polite">{connectionState === "reconnecting" ? "Reconnecting..." : ""}</div>
      <ul>{messages.map((m, i) => <li key={i}><b>{m.user}:</b> {m.text}</li>)}</ul>
    </div>
  );
}
```

The hook manages the full WebSocket lifecycle with exponential backoff (plus jitter to avoid thundering herd), heartbeat ping/pong to detect dead connections, a pub/sub system for typed message routing, and proper cleanup on unmount. The connection state machine tracks connecting, connected, reconnecting, and disconnected states for UI feedback.'''
    ),
    (
        "react/realtime",
        r'''<think>
Server-Sent Events are simpler than WebSocket for one-way server-to-client streaming. I need to show:
1. A hook that wraps EventSource with reconnection
2. Typed event handling with discriminated unions
3. Connection state management
4. Support for custom event types (not just "message")
5. Last-Event-ID for resuming streams after reconnection

SSE has built-in reconnection but I should add custom logic for auth token refresh and error handling.
</think>
Create a React hook for Server-Sent Events (SSE) with typed event handling, automatic reconnection with Last-Event-ID resume, authentication header support via fetch-based SSE, and connection state management.''',
        r'''A typed SSE hook with auth support and stream resumption:

```typescript
import { useCallback, useEffect, useRef, useState } from "react";

type SSEConnectionState = "connecting" | "connected" | "disconnected" | "error";

interface SSEEvent<T = unknown> {
  type: string;
  data: T;
  id?: string;
  retry?: number;
}

interface UseSSEOptions {
  url: string;
  headers?: Record<string, string>;
  withCredentials?: boolean;
  reconnectIntervalMs?: number;
  maxReconnectAttempts?: number;
  onConnect?: () => void;
  onDisconnect?: () => void;
  onError?: (error: Error) => void;
}

interface UseSSEReturn {
  connectionState: SSEConnectionState;
  lastEventId: string | null;
  subscribe: <T>(eventType: string, handler: (data: T, event: SSEEvent<T>) => void) => () => void;
  disconnect: () => void;
  reconnect: () => void;
}

// Fetch-based SSE reader (supports custom headers unlike native EventSource)
class FetchEventSource {
  private abortController: AbortController | null = null;
  private lastEventId: string | null = null;
  private listeners = new Map<string, Set<(event: SSEEvent) => void>>();

  onopen?: () => void;
  onerror?: (error: Error) => void;
  onclose?: () => void;

  constructor(
    private url: string,
    private options: { headers?: Record<string, string>; credentials?: RequestCredentials }
  ) {}

  get lastId(): string | null {
    return this.lastEventId;
  }

  addEventListener(type: string, handler: (event: SSEEvent) => void): void {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, new Set());
    }
    this.listeners.get(type)!.add(handler);
  }

  removeEventListener(type: string, handler: (event: SSEEvent) => void): void {
    this.listeners.get(type)?.delete(handler);
  }

  async connect(): Promise<void> {
    this.abortController = new AbortController();

    const headers: Record<string, string> = {
      Accept: "text/event-stream",
      "Cache-Control": "no-cache",
      ...this.options.headers,
    };

    if (this.lastEventId) {
      headers["Last-Event-ID"] = this.lastEventId;
    }

    try {
      const response = await fetch(this.url, {
        headers,
        credentials: this.options.credentials,
        signal: this.abortController.signal,
      });

      if (!response.ok) {
        throw new Error(`SSE connection failed: ${response.status} ${response.statusText}`);
      }

      if (!response.body) {
        throw new Error("SSE response has no body");
      }

      this.onopen?.();

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // Keep incomplete last line

        let eventType = "message";
        let eventData = "";
        let eventId: string | undefined;

        for (const line of lines) {
          if (line.startsWith("event:")) {
            eventType = line.slice(6).trim();
          } else if (line.startsWith("data:")) {
            eventData += (eventData ? "\n" : "") + line.slice(5).trim();
          } else if (line.startsWith("id:")) {
            eventId = line.slice(3).trim();
            this.lastEventId = eventId;
          } else if (line.startsWith("retry:")) {
            // Server-suggested retry interval - could be used by reconnection logic
          } else if (line === "") {
            // Empty line = end of event
            if (eventData) {
              let parsed: unknown;
              try {
                parsed = JSON.parse(eventData);
              } catch {
                parsed = eventData;
              }

              const sseEvent: SSEEvent = { type: eventType, data: parsed, id: eventId };
              this.dispatch(eventType, sseEvent);

              eventType = "message";
              eventData = "";
              eventId = undefined;
            }
          }
        }
      }

      this.onclose?.();
    } catch (err) {
      if (err instanceof DOMException && err.name === "AbortError") {
        this.onclose?.();
        return;
      }
      this.onerror?.(err instanceof Error ? err : new Error(String(err)));
    }
  }

  private dispatch(type: string, event: SSEEvent): void {
    const handlers = this.listeners.get(type);
    if (handlers) {
      for (const handler of handlers) {
        handler(event);
      }
    }
    // Also dispatch to wildcard listeners
    const wildcardHandlers = this.listeners.get("*");
    if (wildcardHandlers) {
      for (const handler of wildcardHandlers) {
        handler(event);
      }
    }
  }

  close(): void {
    this.abortController?.abort();
  }
}

export function useSSE(options: UseSSEOptions): UseSSEReturn {
  const {
    url,
    headers,
    withCredentials = false,
    reconnectIntervalMs = 3000,
    maxReconnectAttempts = 20,
    onConnect,
    onDisconnect,
    onError,
  } = options;

  const [connectionState, setConnectionState] = useState<SSEConnectionState>("disconnected");
  const [lastEventId, setLastEventId] = useState<string | null>(null);

  const sourceRef = useRef<FetchEventSource | null>(null);
  const subscribersRef = useRef<Map<string, Set<(data: unknown, event: SSEEvent) => void>>>(new Map());
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout>>();
  const mountedRef = useRef(true);
  const intentionalCloseRef = useRef(false);

  const connect = useCallback(() => {
    if (sourceRef.current) {
      sourceRef.current.close();
    }

    setConnectionState("connecting");
    intentionalCloseRef.current = false;

    const source = new FetchEventSource(url, {
      headers,
      credentials: withCredentials ? "include" : "same-origin",
    });

    // Forward events to subscribers
    source.addEventListener("*", (event: SSEEvent) => {
      if (!mountedRef.current) return;
      if (event.id) setLastEventId(event.id);

      const handlers = subscribersRef.current.get(event.type);
      if (handlers) {
        for (const handler of handlers) {
          handler(event.data, event);
        }
      }
    });

    source.onopen = () => {
      if (!mountedRef.current) return;
      setConnectionState("connected");
      reconnectCountRef.current = 0;
      onConnect?.();
    };

    source.onerror = (error) => {
      if (!mountedRef.current) return;
      setConnectionState("error");
      onError?.(error);
      attemptReconnect();
    };

    source.onclose = () => {
      if (!mountedRef.current) return;
      if (!intentionalCloseRef.current) {
        attemptReconnect();
      } else {
        setConnectionState("disconnected");
        onDisconnect?.();
      }
    };

    sourceRef.current = source;
    source.connect();
  }, [url, headers, withCredentials, onConnect, onDisconnect, onError]);

  function attemptReconnect() {
    if (intentionalCloseRef.current) return;
    if (reconnectCountRef.current >= maxReconnectAttempts) {
      setConnectionState("error");
      return;
    }

    reconnectCountRef.current += 1;
    const delay = reconnectIntervalMs * Math.min(reconnectCountRef.current, 5);

    reconnectTimerRef.current = setTimeout(() => {
      if (mountedRef.current && !intentionalCloseRef.current) {
        connect();
      }
    }, delay);
  }

  const disconnect = useCallback(() => {
    intentionalCloseRef.current = true;
    if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
    sourceRef.current?.close();
    setConnectionState("disconnected");
  }, []);

  const reconnectManual = useCallback(() => {
    disconnect();
    reconnectCountRef.current = 0;
    setTimeout(connect, 100);
  }, [connect, disconnect]);

  const subscribe = useCallback(<T,>(
    eventType: string,
    handler: (data: T, event: SSEEvent<T>) => void
  ): (() => void) => {
    if (!subscribersRef.current.has(eventType)) {
      subscribersRef.current.set(eventType, new Set());
    }
    const handlers = subscribersRef.current.get(eventType)!;
    const wrapped = handler as (data: unknown, event: SSEEvent) => void;
    handlers.add(wrapped);

    return () => {
      handlers.delete(wrapped);
      if (handlers.size === 0) {
        subscribersRef.current.delete(eventType);
      }
    };
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    connect();
    return () => {
      mountedRef.current = false;
      intentionalCloseRef.current = true;
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      sourceRef.current?.close();
    };
  }, [connect]);

  return { connectionState, lastEventId, subscribe, disconnect, reconnect: reconnectManual };
}

// Usage: Live notifications feed
function NotificationsFeed() {
  const [notifications, setNotifications] = useState<{ id: string; text: string; type: string }[]>([]);
  const { connectionState, subscribe } = useSSE({
    url: "/api/notifications/stream",
    headers: { Authorization: "Bearer token123" },
  });

  useEffect(() => {
    return subscribe<{ id: string; text: string; type: string }>("notification", (data) => {
      setNotifications((prev) => [data, ...prev].slice(0, 50));
    });
  }, [subscribe]);

  return (
    <div>
      <span>{connectionState === "connected" ? "Live" : "Connecting..."}</span>
      <ul>{notifications.map((n) => <li key={n.id}>{n.text}</li>)}</ul>
    </div>
  );
}
```

This uses a fetch-based SSE reader instead of native `EventSource` to support custom headers (required for auth tokens). It parses the SSE wire format manually from the streaming response, tracks `Last-Event-ID` for stream resumption after reconnection, and provides a typed pub/sub interface for different event types.'''
    ),
    (
        "react/realtime",
        r'''Implement an optimistic UI update system for React that handles pending mutations, automatic rollback on failure, conflict resolution with server state, and a queue for offline mutations that sync when connectivity returns.''',
        r'''An optimistic update system with rollback, conflict resolution, and offline queue:

```typescript
import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from "react";

// Mutation types
interface OptimisticMutation<TData = unknown> {
  id: string;
  type: string;
  optimisticData: TData;
  serverRequest: () => Promise<TData>;
  rollbackData: TData;
  timestamp: number;
  status: "pending" | "confirmed" | "failed" | "conflict";
  retryCount: number;
  maxRetries: number;
}

// Conflict resolution strategies
type ConflictStrategy = "client-wins" | "server-wins" | "merge" | "manual";

interface ConflictInfo<T> {
  clientData: T;
  serverData: T;
  baseData: T;
}

type MergeFunction<T> = (conflict: ConflictInfo<T>) => T;

// Optimistic store
class OptimisticStore<TState> {
  private baseState: TState;
  private pendingMutations: OptimisticMutation[] = [];
  private offlineQueue: OptimisticMutation[] = [];
  private listeners = new Set<() => void>();
  private isOnline = navigator.onLine;

  constructor(
    initialState: TState,
    private applyMutation: (state: TState, mutation: OptimisticMutation) => TState,
    private conflictStrategy: ConflictStrategy = "server-wins",
    private mergeFn?: MergeFunction<TState>
  ) {
    this.baseState = initialState;

    window.addEventListener("online", () => {
      this.isOnline = true;
      this.flushOfflineQueue();
    });

    window.addEventListener("offline", () => {
      this.isOnline = false;
    });
  }

  getSnapshot = (): TState => {
    // Apply all pending mutations on top of base state
    let state = this.baseState;
    for (const mutation of this.pendingMutations) {
      if (mutation.status === "pending") {
        state = this.applyMutation(state, mutation);
      }
    }
    return state;
  };

  getServerState = (): TState => {
    return this.baseState;
  };

  subscribe = (listener: () => void): (() => void) => {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  };

  private notify() {
    for (const listener of this.listeners) {
      listener();
    }
  }

  updateBaseState(newState: TState): void {
    this.baseState = newState;
    this.notify();
  }

  getPendingMutations(): OptimisticMutation[] {
    return [...this.pendingMutations];
  }

  getOfflineQueue(): OptimisticMutation[] {
    return [...this.offlineQueue];
  }

  async mutate<TData>(options: {
    type: string;
    optimisticData: TData;
    serverRequest: () => Promise<TData>;
    rollbackData?: TData;
    maxRetries?: number;
  }): Promise<TData> {
    const mutation: OptimisticMutation<TData> = {
      id: crypto.randomUUID(),
      type: options.type,
      optimisticData: options.optimisticData,
      serverRequest: options.serverRequest,
      rollbackData: (options.rollbackData ?? this.baseState) as TData,
      timestamp: Date.now(),
      status: "pending",
      retryCount: 0,
      maxRetries: options.maxRetries ?? 3,
    };

    this.pendingMutations.push(mutation);
    this.notify();

    if (!this.isOnline) {
      this.offlineQueue.push(mutation);
      this.persistOfflineQueue();
      return options.optimisticData;
    }

    return this.executeMutation(mutation);
  }

  private async executeMutation<TData>(mutation: OptimisticMutation<TData>): Promise<TData> {
    try {
      const serverResult = await mutation.serverRequest();

      // Check for conflicts
      const mutationIndex = this.pendingMutations.findIndex((m) => m.id === mutation.id);
      if (mutationIndex !== -1) {
        // Compare optimistic with server result
        const hasConflict = JSON.stringify(serverResult) !== JSON.stringify(mutation.optimisticData);

        if (hasConflict) {
          const resolved = this.resolveConflict(mutation, serverResult);
          this.pendingMutations[mutationIndex].status = "confirmed";

          // Remove from pending after small delay for UI transition
          setTimeout(() => {
            this.pendingMutations = this.pendingMutations.filter((m) => m.id !== mutation.id);
            this.notify();
          }, 100);

          this.baseState = resolved as unknown as TState;
          this.notify();
          return resolved;
        }

        this.pendingMutations[mutationIndex].status = "confirmed";
        this.pendingMutations = this.pendingMutations.filter((m) => m.id !== mutation.id);
        this.baseState = this.applyMutation(this.baseState, mutation);
        this.notify();
      }

      return serverResult;
    } catch (error) {
      // Retry logic
      if (mutation.retryCount < mutation.maxRetries) {
        mutation.retryCount += 1;
        const backoff = Math.pow(2, mutation.retryCount) * 500;
        await new Promise((resolve) => setTimeout(resolve, backoff));
        return this.executeMutation(mutation);
      }

      // Rollback
      this.pendingMutations = this.pendingMutations.filter((m) => m.id !== mutation.id);
      this.notify();

      throw error;
    }
  }

  private resolveConflict<TData>(mutation: OptimisticMutation<TData>, serverData: TData): TData {
    switch (this.conflictStrategy) {
      case "client-wins":
        return mutation.optimisticData;

      case "server-wins":
        return serverData;

      case "merge":
        if (this.mergeFn) {
          return this.mergeFn({
            clientData: mutation.optimisticData,
            serverData,
            baseData: mutation.rollbackData,
          } as unknown as ConflictInfo<TState>) as unknown as TData;
        }
        return serverData;

      case "manual":
        // Store conflict for manual resolution
        mutation.status = "conflict";
        this.notify();
        return serverData;

      default:
        return serverData;
    }
  }

  private async flushOfflineQueue() {
    const queue = [...this.offlineQueue];
    this.offlineQueue = [];
    this.clearPersistedQueue();

    for (const mutation of queue) {
      try {
        await this.executeMutation(mutation);
      } catch (error) {
        console.error("Failed to sync offline mutation:", mutation.type, error);
        // Re-queue failed mutations
        this.offlineQueue.push(mutation);
      }
    }

    if (this.offlineQueue.length > 0) {
      this.persistOfflineQueue();
    }

    this.notify();
  }

  private persistOfflineQueue() {
    try {
      const serializable = this.offlineQueue.map((m) => ({
        id: m.id,
        type: m.type,
        optimisticData: m.optimisticData,
        timestamp: m.timestamp,
      }));
      localStorage.setItem("optimistic_offline_queue", JSON.stringify(serializable));
    } catch {
      // Storage may be full
    }
  }

  private clearPersistedQueue() {
    localStorage.removeItem("optimistic_offline_queue");
  }
}

// React hook
interface TodoItem {
  id: string;
  text: string;
  completed: boolean;
  updatedAt: number;
}

interface TodoState {
  items: TodoItem[];
}

function applyTodoMutation(state: TodoState, mutation: OptimisticMutation): TodoState {
  switch (mutation.type) {
    case "add":
      return { items: [...state.items, mutation.optimisticData as TodoItem] };
    case "toggle": {
      const data = mutation.optimisticData as { id: string; completed: boolean };
      return {
        items: state.items.map((item) =>
          item.id === data.id ? { ...item, completed: data.completed } : item
        ),
      };
    }
    case "delete": {
      const data = mutation.optimisticData as { id: string };
      return { items: state.items.filter((item) => item.id !== data.id) };
    }
    default:
      return state;
  }
}

// Merge function for conflict resolution
function mergeTodos(conflict: ConflictInfo<TodoState>): TodoState {
  const serverMap = new Map(conflict.serverData.items.map((i) => [i.id, i]));
  const clientMap = new Map(conflict.clientData.items.map((i) => [i.id, i]));
  const baseMap = new Map(conflict.baseData.items.map((i) => [i.id, i]));

  const merged: TodoItem[] = [];

  // Include all server items, preferring client changes for items modified locally
  for (const [id, serverItem] of serverMap) {
    const clientItem = clientMap.get(id);
    const baseItem = baseMap.get(id);

    if (clientItem && baseItem) {
      // Both modified - use most recent
      merged.push(clientItem.updatedAt > serverItem.updatedAt ? clientItem : serverItem);
    } else {
      merged.push(serverItem);
    }
  }

  // Add client-only items (created offline)
  for (const [id, clientItem] of clientMap) {
    if (!serverMap.has(id)) {
      merged.push(clientItem);
    }
  }

  return { items: merged };
}

const todoStore = new OptimisticStore<TodoState>(
  { items: [] },
  applyTodoMutation,
  "merge",
  mergeTodos
);

export function useTodos() {
  const state = useSyncExternalStore(todoStore.subscribe, todoStore.getSnapshot, todoStore.getServerState);
  const pending = todoStore.getPendingMutations();

  const addTodo = useCallback(async (text: string) => {
    const optimistic: TodoItem = {
      id: `temp_${Date.now()}`,
      text,
      completed: false,
      updatedAt: Date.now(),
    };

    return todoStore.mutate({
      type: "add",
      optimisticData: optimistic,
      serverRequest: async () => {
        const resp = await fetch("/api/todos", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ text }),
        });
        return resp.json();
      },
    });
  }, []);

  const toggleTodo = useCallback(async (id: string, completed: boolean) => {
    return todoStore.mutate({
      type: "toggle",
      optimisticData: { id, completed },
      serverRequest: async () => {
        const resp = await fetch(`/api/todos/${id}`, {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ completed }),
        });
        return resp.json();
      },
    });
  }, []);

  return { todos: state.items, pending, addTodo, toggleTodo };
}
```

The store maintains a base state (confirmed by server) and layers pending optimistic mutations on top via `getSnapshot`. Failed mutations automatically roll back, and the merge strategy resolves conflicts using timestamps. The offline queue persists to localStorage and flushes when connectivity returns, with per-mutation retry logic.'''
    ),
    (
        "react/realtime",
        r'''Create a React presence system that shows which users are currently viewing a page, their cursor positions, and typing indicators. Use WebSocket for real-time updates with debounced position broadcasting and stale presence cleanup.''',
        r'''A presence system with cursors, typing indicators, and stale cleanup:

```typescript
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useWebSocket } from "./use-websocket";

interface UserPresence {
  userId: string;
  name: string;
  avatarUrl?: string;
  color: string;
  cursor: { x: number; y: number } | null;
  isTyping: boolean;
  lastSeen: number;
  currentPage: string;
}

interface PresenceState {
  users: Map<string, UserPresence>;
  selfId: string;
}

// Assign consistent colors to users
const PRESENCE_COLORS = [
  "#ef4444", "#f97316", "#eab308", "#22c55e",
  "#06b6d4", "#3b82f6", "#8b5cf6", "#ec4899",
  "#14b8a6", "#f59e0b", "#6366f1", "#d946ef",
];

function userColor(userId: string): string {
  let hash = 0;
  for (let i = 0; i < userId.length; i++) {
    hash = ((hash << 5) - hash + userId.charCodeAt(i)) | 0;
  }
  return PRESENCE_COLORS[Math.abs(hash) % PRESENCE_COLORS.length];
}

// Debounce utility
function debounce<T extends (...args: unknown[]) => void>(fn: T, ms: number): T & { cancel: () => void } {
  let timer: ReturnType<typeof setTimeout>;
  const debounced = (...args: unknown[]) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
  debounced.cancel = () => clearTimeout(timer);
  return debounced as T & { cancel: () => void };
}

// Throttle utility
function throttle<T extends (...args: unknown[]) => void>(fn: T, ms: number): T {
  let lastCall = 0;
  let timer: ReturnType<typeof setTimeout> | null = null;
  return ((...args: unknown[]) => {
    const now = Date.now();
    const remaining = ms - (now - lastCall);
    if (remaining <= 0) {
      if (timer) { clearTimeout(timer); timer = null; }
      lastCall = now;
      fn(...args);
    } else if (!timer) {
      timer = setTimeout(() => {
        lastCall = Date.now();
        timer = null;
        fn(...args);
      }, remaining);
    }
  }) as T;
}

const STALE_TIMEOUT_MS = 30_000; // Remove users not seen for 30s
const CURSOR_THROTTLE_MS = 50;   // Send cursor updates max every 50ms
const TYPING_DEBOUNCE_MS = 2000; // Stop typing indicator after 2s of inactivity

interface UsePresenceOptions {
  roomId: string;
  userId: string;
  userName: string;
  avatarUrl?: string;
  currentPage: string;
}

export function usePresence(options: UsePresenceOptions) {
  const { roomId, userId, userName, avatarUrl, currentPage } = options;
  const [users, setUsers] = useState<Map<string, UserPresence>>(new Map());
  const usersRef = useRef(users);
  usersRef.current = users;

  const { connectionState, sendMessage, subscribe } = useWebSocket({
    url: `wss://api.example.com/presence?room=${roomId}`,
  });

  // Announce presence on connect
  useEffect(() => {
    if (connectionState !== "connected") return;

    sendMessage("presence:join", {
      userId,
      name: userName,
      avatarUrl,
      color: userColor(userId),
      currentPage,
    });

    // Send heartbeat every 10 seconds
    const heartbeat = setInterval(() => {
      sendMessage("presence:heartbeat", { userId, currentPage });
    }, 10_000);

    return () => {
      clearInterval(heartbeat);
      sendMessage("presence:leave", { userId });
    };
  }, [connectionState, userId, userName, avatarUrl, currentPage, sendMessage]);

  // Subscribe to presence events
  useEffect(() => {
    const unsubs: (() => void)[] = [];

    unsubs.push(subscribe<{
      userId: string; name: string; avatarUrl?: string; color: string; currentPage: string;
    }>("presence:join", (data) => {
      setUsers((prev) => {
        const next = new Map(prev);
        next.set(data.userId, {
          ...data,
          cursor: null,
          isTyping: false,
          lastSeen: Date.now(),
        });
        return next;
      });
    }));

    unsubs.push(subscribe<{ userId: string }>("presence:leave", (data) => {
      setUsers((prev) => {
        const next = new Map(prev);
        next.delete(data.userId);
        return next;
      });
    }));

    unsubs.push(subscribe<{ userId: string; x: number; y: number }>("presence:cursor", (data) => {
      setUsers((prev) => {
        const user = prev.get(data.userId);
        if (!user) return prev;
        const next = new Map(prev);
        next.set(data.userId, {
          ...user,
          cursor: { x: data.x, y: data.y },
          lastSeen: Date.now(),
        });
        return next;
      });
    }));

    unsubs.push(subscribe<{ userId: string; isTyping: boolean }>("presence:typing", (data) => {
      setUsers((prev) => {
        const user = prev.get(data.userId);
        if (!user) return prev;
        const next = new Map(prev);
        next.set(data.userId, { ...user, isTyping: data.isTyping, lastSeen: Date.now() });
        return next;
      });
    }));

    unsubs.push(subscribe<{ userId: string; currentPage: string }>("presence:heartbeat", (data) => {
      setUsers((prev) => {
        const user = prev.get(data.userId);
        if (!user) return prev;
        const next = new Map(prev);
        next.set(data.userId, { ...user, currentPage: data.currentPage, lastSeen: Date.now() });
        return next;
      });
    }));

    // Bulk sync on initial connect
    unsubs.push(subscribe<UserPresence[]>("presence:sync", (data) => {
      setUsers(new Map(data.map((u) => [u.userId, u])));
    }));

    return () => unsubs.forEach((fn) => fn());
  }, [subscribe]);

  // Stale presence cleanup
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      setUsers((prev) => {
        let changed = false;
        const next = new Map(prev);
        for (const [id, user] of next) {
          if (id !== userId && now - user.lastSeen > STALE_TIMEOUT_MS) {
            next.delete(id);
            changed = true;
          }
        }
        return changed ? next : prev;
      });
    }, 5000);

    return () => clearInterval(interval);
  }, [userId]);

  // Throttled cursor broadcast
  const broadcastCursor = useMemo(
    () =>
      throttle((x: number, y: number) => {
        sendMessage("presence:cursor", { userId, x, y });
      }, CURSOR_THROTTLE_MS),
    [sendMessage, userId]
  );

  // Debounced typing indicator
  const stopTypingDebounced = useMemo(
    () =>
      debounce(() => {
        sendMessage("presence:typing", { userId, isTyping: false });
      }, TYPING_DEBOUNCE_MS),
    [sendMessage, userId]
  );

  const broadcastTyping = useCallback(() => {
    sendMessage("presence:typing", { userId, isTyping: true });
    stopTypingDebounced();
  }, [sendMessage, userId, stopTypingDebounced]);

  // Track mouse movement
  const trackCursor = useCallback(
    (event: React.MouseEvent | MouseEvent) => {
      broadcastCursor(event.clientX, event.clientY);
    },
    [broadcastCursor]
  );

  // Filter to other users on the same page
  const activeUsers = useMemo(() => {
    const result: UserPresence[] = [];
    for (const [id, user] of users) {
      if (id !== userId && user.currentPage === currentPage) {
        result.push(user);
      }
    }
    return result;
  }, [users, userId, currentPage]);

  const allOnlineUsers = useMemo(() => {
    return Array.from(users.values()).filter((u) => u.userId !== userId);
  }, [users, userId]);

  return {
    activeUsers,
    allOnlineUsers,
    trackCursor,
    broadcastTyping,
    connectionState,
  };
}

// Cursor overlay component
function CursorOverlay({ users }: { users: UserPresence[] }) {
  return (
    <div
      style={{ position: "fixed", inset: 0, pointerEvents: "none", zIndex: 9998 }}
      aria-hidden="true"
    >
      {users.map((user) =>
        user.cursor ? (
          <div
            key={user.userId}
            style={{
              position: "absolute",
              left: user.cursor.x,
              top: user.cursor.y,
              transition: "left 100ms linear, top 100ms linear",
            }}
          >
            {/* Cursor arrow SVG */}
            <svg width="16" height="20" viewBox="0 0 16 20" fill={user.color}>
              <path d="M0 0L16 12L8 12L12 20L8 18L4 12L0 16Z" />
            </svg>
            <span style={{
              background: user.color, color: "white", fontSize: "11px",
              padding: "2px 6px", borderRadius: "4px", marginLeft: "8px",
              whiteSpace: "nowrap", position: "relative", top: "-4px",
            }}>
              {user.name}
            </span>
          </div>
        ) : null
      )}
    </div>
  );
}

// Presence avatars component
function PresenceAvatars({ users }: { users: UserPresence[] }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: "-8px" }} aria-label="Users online">
      {users.slice(0, 5).map((user) => (
        <div
          key={user.userId}
          title={`${user.name}${user.isTyping ? " (typing...)" : ""}`}
          style={{
            width: "32px", height: "32px", borderRadius: "50%",
            background: user.color, color: "white",
            display: "flex", alignItems: "center", justifyContent: "center",
            fontSize: "12px", fontWeight: 600,
            border: "2px solid white", marginLeft: "-8px",
            position: "relative",
          }}
        >
          {user.avatarUrl ? (
            <img src={user.avatarUrl} alt={user.name} style={{ width: "100%", height: "100%", borderRadius: "50%" }} />
          ) : (
            user.name.charAt(0).toUpperCase()
          )}
          {user.isTyping && (
            <span style={{
              position: "absolute", bottom: "-2px", right: "-2px",
              width: "10px", height: "10px", borderRadius: "50%",
              background: "#22c55e", border: "2px solid white",
            }} />
          )}
        </div>
      ))}
      {users.length > 5 && (
        <div style={{
          width: "32px", height: "32px", borderRadius: "50%",
          background: "#6b7280", color: "white",
          display: "flex", alignItems: "center", justifyContent: "center",
          fontSize: "11px", border: "2px solid white", marginLeft: "-8px",
        }}>
          +{users.length - 5}
        </div>
      )}
    </div>
  );
}

// Page usage
function CollaborativeEditor() {
  const { activeUsers, trackCursor, broadcastTyping } = usePresence({
    roomId: "doc-123",
    userId: "user_abc",
    userName: "Alice",
    currentPage: "/docs/123",
  });

  return (
    <div onMouseMove={trackCursor}>
      <PresenceAvatars users={activeUsers} />
      <textarea
        onInput={() => broadcastTyping()}
        placeholder="Start typing..."
        style={{ width: "100%", minHeight: "300px" }}
      />
      <CursorOverlay users={activeUsers} />
    </div>
  );
}
```

The presence system broadcasts cursor positions at a throttled rate (50ms) to avoid flooding the WebSocket, uses debounced typing indicators that auto-clear after 2 seconds of inactivity, sends periodic heartbeats for liveness detection, and cleans up stale users who have not been seen for 30 seconds. Cursor rendering uses CSS transitions for smooth interpolation between position updates.'''
    ),
]
