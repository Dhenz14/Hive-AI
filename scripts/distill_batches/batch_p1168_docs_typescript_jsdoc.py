"""Documentation generation training pairs: JSDoc/TSDoc for TypeScript."""

pairs = [
    {
        "instruction": r'''Write JSDoc documentation for this TypeScript event emitter class:

type EventHandler<T = any> = (data: T) => void;

class TypedEventEmitter<Events extends Record<string, any>> {
  private handlers: Map<keyof Events, Set<EventHandler>> = new Map();
  private onceHandlers: Map<keyof Events, Set<EventHandler>> = new Map();

  on<K extends keyof Events>(event: K, handler: EventHandler<Events[K]>): () => void {
    if (!this.handlers.has(event)) this.handlers.set(event, new Set());
    this.handlers.get(event)!.add(handler);
    return () => this.off(event, handler);
  }

  once<K extends keyof Events>(event: K, handler: EventHandler<Events[K]>): void {
    if (!this.onceHandlers.has(event)) this.onceHandlers.set(event, new Set());
    this.onceHandlers.get(event)!.add(handler);
  }

  off<K extends keyof Events>(event: K, handler: EventHandler<Events[K]>): void {
    this.handlers.get(event)?.delete(handler);
    this.onceHandlers.get(event)?.delete(handler);
  }

  emit<K extends keyof Events>(event: K, data: Events[K]): void {
    this.handlers.get(event)?.forEach(h => h(data));
    this.onceHandlers.get(event)?.forEach(h => h(data));
    this.onceHandlers.delete(event);
  }

  removeAllListeners(event?: keyof Events): void {
    if (event) {
      this.handlers.delete(event);
      this.onceHandlers.delete(event);
    } else {
      this.handlers.clear();
      this.onceHandlers.clear();
    }
  }
}''',
        "output": r'''<think>
This is a type-safe event emitter using TypeScript generics. The Events type parameter maps event names to their payload types. I need JSDoc for:
- The type alias
- The class itself with a usage example showing the generic parameter
- Each method with @param, @returns, @template tags
- The `on` method returns an unsubscribe function, which is worth highlighting
</think>

```typescript
/**
 * Callback function type for event handlers.
 * @template T - The event payload type. Defaults to `any`.
 * @param data - The event payload passed when the event is emitted.
 */
type EventHandler<T = any> = (data: T) => void;

/**
 * A type-safe event emitter with support for persistent and one-time listeners.
 *
 * Define an event map interface to get compile-time checks on event names
 * and payload types.
 *
 * @template Events - A record mapping event names to their payload types.
 *
 * @example
 * ```typescript
 * interface AppEvents {
 *   userLogin: { userId: string; timestamp: number };
 *   error: Error;
 * }
 * const emitter = new TypedEventEmitter<AppEvents>();
 * const unsub = emitter.on('userLogin', (data) => console.log(data.userId));
 * emitter.emit('userLogin', { userId: 'abc', timestamp: Date.now() });
 * unsub();
 * ```
 */
class TypedEventEmitter<Events extends Record<string, any>> {

  /**
   * Register a persistent event listener.
   *
   * @template K - The event name (inferred from the first argument).
   * @param event - The event to listen for.
   * @param handler - Callback invoked each time the event fires.
   * @returns An unsubscribe function. Call it to remove this listener.
   */
  on<K extends keyof Events>(event: K, handler: EventHandler<Events[K]>): () => void { ... }

  /** Register a one-time listener, auto-removed after firing once. */
  once<K extends keyof Events>(event: K, handler: EventHandler<Events[K]>): void { ... }

  /** Remove a specific listener by reference. */
  off<K extends keyof Events>(event: K, handler: EventHandler<Events[K]>): void { ... }

  /**
   * Emit an event, invoking all handlers with the payload.
   * One-time handlers are removed after being called.
   */
  emit<K extends keyof Events>(event: K, data: Events[K]): void { ... }

  /** Remove all listeners for a specific event, or all events if omitted. */
  removeAllListeners(event?: keyof Events): void { ... }
}
```'''
    },
    {
        "instruction": r'''Add TSDoc comments to this React hook:

function useDebounce<T>(value: T, delayMs: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debouncedValue;
}

function useDebouncedCallback<Args extends any[]>(
  callback: (...args: Args) => void,
  delayMs: number,
  deps: React.DependencyList = [],
): (...args: Args) => void {
  const timeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const callbackRef = useRef(callback);

  useEffect(() => {
    callbackRef.current = callback;
  }, [callback, ...deps]);

  useEffect(() => {
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current);
    };
  }, []);

  return useCallback((...args: Args) => {
    if (timeoutRef.current) clearTimeout(timeoutRef.current);
    timeoutRef.current = setTimeout(() => callbackRef.current(...args), delayMs);
  }, [delayMs]);
}''',
        "output": r'''```typescript
/**
 * Debounce a value so it only updates after a period of inactivity.
 *
 * Returns a copy of `value` that only changes once `delayMs` milliseconds
 * have passed without `value` changing. Useful for delaying API calls
 * triggered by user input (e.g., search-as-you-type).
 *
 * @template T - The type of the value being debounced.
 * @param value - The rapidly-changing input value.
 * @param delayMs - Debounce delay in milliseconds.
 * @returns The debounced value, which updates only after the delay.
 *
 * @example
 * ```tsx
 * const [query, setQuery] = useState('');
 * const debouncedQuery = useDebounce(query, 300);
 *
 * useEffect(() => {
 *   if (debouncedQuery) fetchResults(debouncedQuery);
 * }, [debouncedQuery]);
 * ```
 */
function useDebounce<T>(value: T, delayMs: number): T { ... }

/**
 * Create a debounced version of a callback function.
 *
 * Unlike {@link useDebounce}, which debounces a value, this hook
 * debounces the invocation of a function. The callback is only
 * executed after `delayMs` milliseconds have passed since the last
 * call. Previous pending invocations are cancelled.
 *
 * The returned function is stable across renders (memoized). The
 * internal callback reference is updated when `callback` or `deps`
 * change, so it always calls the latest version.
 *
 * The timeout is automatically cleared on unmount.
 *
 * @template Args - Tuple type of the callback's parameters.
 * @param callback - The function to debounce.
 * @param delayMs - Debounce delay in milliseconds.
 * @param deps - Additional dependencies that should refresh the
 *   internal callback reference. Defaults to an empty array.
 * @returns A debounced wrapper with the same signature as `callback`.
 *
 * @example
 * ```tsx
 * const saveToServer = useDebouncedCallback(
 *   (content: string) => api.save(docId, content),
 *   500,
 *   [docId],
 * );
 *
 * // Called on every keystroke, but only fires after 500ms idle
 * <textarea onChange={(e) => saveToServer(e.target.value)} />
 * ```
 */
function useDebouncedCallback<Args extends any[]>(
  callback: (...args: Args) => void,
  delayMs: number,
  deps?: React.DependencyList,
): (...args: Args) => void { ... }
```'''
    },
    {
        "instruction": r'''Write JSDoc for this TypeScript HTTP client interface and its factory function:

interface RequestConfig {
  baseURL: string;
  timeout?: number;
  headers?: Record<string, string>;
  retries?: number;
  retryDelay?: number;
}

interface HttpResponse<T> {
  data: T;
  status: number;
  headers: Record<string, string>;
  duration: number;
}

interface HttpClient {
  get<T>(path: string, params?: Record<string, string>): Promise<HttpResponse<T>>;
  post<T>(path: string, body?: unknown): Promise<HttpResponse<T>>;
  put<T>(path: string, body?: unknown): Promise<HttpResponse<T>>;
  delete<T>(path: string): Promise<HttpResponse<T>>;
}

function createHttpClient(config: RequestConfig): HttpClient {
  ...
}''',
        "output": r'''<think>
I need to document three interfaces and a factory function. The interfaces define the contract for configuration, responses, and the client itself. The factory function creates the client. I should document each interface field, the generic type parameter on HttpResponse and the methods, and the factory function.
</think>

```typescript
/**
 * Configuration for creating an HTTP client instance.
 */
interface RequestConfig {
  /** Base URL prepended to all request paths (e.g., "https://api.example.com/v1"). */
  baseURL: string;
  /** Request timeout in milliseconds. Defaults to 30000 (30 seconds). */
  timeout?: number;
  /** Default headers sent with every request (e.g., Authorization). */
  headers?: Record<string, string>;
  /** Number of automatic retries on network failure. Defaults to 0. */
  retries?: number;
  /** Delay between retries in milliseconds. Defaults to 1000. */
  retryDelay?: number;
}

/**
 * Wrapper around an HTTP response with typed body data.
 *
 * @template T - The expected shape of the response body.
 */
interface HttpResponse<T> {
  /** Parsed response body. */
  data: T;
  /** HTTP status code (e.g., 200, 404). */
  status: number;
  /** Response headers as key-value pairs. */
  headers: Record<string, string>;
  /** Request round-trip time in milliseconds. */
  duration: number;
}

/**
 * A typed HTTP client supporting GET, POST, PUT, and DELETE methods.
 * All methods return a Promise that resolves to an {@link HttpResponse}
 * or rejects with an error containing the response details.
 */
interface HttpClient {
  /** Send a GET request. @param params - Optional query string key-value pairs. */
  get<T>(path: string, params?: Record<string, string>): Promise<HttpResponse<T>>;
  /** Send a POST request. @param body - Request body (serialized to JSON). */
  post<T>(path: string, body?: unknown): Promise<HttpResponse<T>>;
  /** Send a PUT request. @param body - Request body (serialized to JSON). */
  put<T>(path: string, body?: unknown): Promise<HttpResponse<T>>;
  /** Send a DELETE request. */
  delete<T>(path: string): Promise<HttpResponse<T>>;
}

/**
 * Create a configured HTTP client instance.
 *
 * @param config - Client configuration (base URL, timeout, retry policy).
 * @returns A fully configured {@link HttpClient} ready to make requests.
 *
 * @example
 * ```typescript
 * const api = createHttpClient({
 *   baseURL: 'https://api.example.com/v1',
 *   timeout: 5000,
 *   headers: { Authorization: 'Bearer token123' },
 *   retries: 3,
 * });
 *
 * const users = await api.get<User[]>('/users', { role: 'admin' });
 * console.log(users.data, users.duration);
 * ```
 */
function createHttpClient(config: RequestConfig): HttpClient { ... }
```'''
    },
    {
        "instruction": r'''Write JSDoc for this middleware chain implementation:

type Middleware<Ctx> = (ctx: Ctx, next: () => Promise<void>) => Promise<void>;

class Pipeline<Ctx> {
  private middlewares: Middleware<Ctx>[] = [];

  use(middleware: Middleware<Ctx>): this {
    this.middlewares.push(middleware);
    return this;
  }

  async execute(ctx: Ctx): Promise<void> {
    let index = 0;
    const dispatch = async (): Promise<void> => {
      if (index >= this.middlewares.length) return;
      const mw = this.middlewares[index++];
      await mw(ctx, dispatch);
    };
    await dispatch();
  }
}''',
        "output": r'''```typescript
/**
 * A middleware function that receives a context and a `next` callback.
 * Calling `next()` passes control to the next middleware in the chain.
 * Not calling `next()` short-circuits the pipeline.
 *
 * @template Ctx - The context object type shared across middlewares.
 * @param ctx - The shared context, readable and writable by each middleware.
 * @param next - Async function to invoke the next middleware. Await it to
 *   run downstream middlewares before continuing.
 */
type Middleware<Ctx> = (ctx: Ctx, next: () => Promise<void>) => Promise<void>;

/**
 * Koa-style middleware pipeline with typed context.
 *
 * Middlewares execute in registration order. Each middleware can run
 * code before calling `next()`, await downstream processing, then
 * run code after -- enabling patterns like logging, timing, and
 * error wrapping.
 *
 * @template Ctx - The context object type passed through the pipeline.
 *
 * @example
 * ```typescript
 * interface ReqCtx { path: string; status: number; body: string; }
 *
 * const app = new Pipeline<ReqCtx>();
 *
 * // Timing middleware
 * app.use(async (ctx, next) => {
 *   const start = Date.now();
 *   await next();
 *   console.log(ctx.path, Date.now() - start, 'ms');
 * });
 *
 * // Handler
 * app.use(async (ctx) => {
 *   ctx.status = 200;
 *   ctx.body = 'OK';
 * });
 *
 * await app.execute({ path: '/test', status: 0, body: '' });
 * ```
 */
class Pipeline<Ctx> {
  /**
   * Append a middleware to the end of the chain.
   *
   * @param middleware - The middleware function to add.
   * @returns `this` for method chaining.
   */
  use(middleware: Middleware<Ctx>): this { ... }

  /**
   * Execute the middleware chain with the given context.
   *
   * Middlewares run in the order they were added via {@link use}.
   * If any middleware throws, the error propagates to the caller.
   *
   * @param ctx - The context object passed to every middleware.
   */
  async execute(ctx: Ctx): Promise<void> { ... }
}
```'''
    },
    {
        "instruction": r'''Write TSDoc for this generic state machine:

type StateTransition<S extends string, E extends string> = {
  from: S;
  event: E;
  to: S;
  guard?: () => boolean;
  action?: () => void;
};

class StateMachine<S extends string, E extends string> {
  private current: S;
  private transitions: StateTransition<S, E>[];
  private listeners: Map<S, Array<() => void>> = new Map();

  constructor(initial: S, transitions: StateTransition<S, E>[]) {
    this.current = initial;
    this.transitions = transitions;
  }

  getState(): S { return this.current; }

  send(event: E): boolean {
    const t = this.transitions.find(
      t => t.from === this.current && t.event === event
    );
    if (!t) return false;
    if (t.guard && !t.guard()) return false;
    this.current = t.to;
    t.action?.();
    this.listeners.get(t.to)?.forEach(fn => fn());
    return true;
  }

  onEnter(state: S, callback: () => void): () => void {
    if (!this.listeners.has(state)) this.listeners.set(state, []);
    this.listeners.get(state)!.push(callback);
    return () => {
      const arr = this.listeners.get(state);
      if (arr) {
        const idx = arr.indexOf(callback);
        if (idx >= 0) arr.splice(idx, 1);
      }
    };
  }
}''',
        "output": r'''```typescript
/**
 * Defines a valid state transition triggered by an event.
 *
 * @template S - Union type of all possible states.
 * @template E - Union type of all possible events.
 */
type StateTransition<S extends string, E extends string> = {
  /** The state this transition starts from. */
  from: S;
  /** The event that triggers this transition. */
  event: E;
  /** The state to move to if the transition is accepted. */
  to: S;
  /** Optional predicate. Transition is blocked if guard returns false. */
  guard?: () => boolean;
  /** Optional side-effect executed after the state changes. */
  action?: () => void;
};

/**
 * A finite state machine with typed states, events, guards, and listeners.
 *
 * @template S - Union type of valid state strings.
 * @template E - Union type of valid event strings.
 *
 * @example
 * ```typescript
 * type OrderState = 'pending' | 'paid' | 'shipped' | 'cancelled';
 * type OrderEvent = 'pay' | 'ship' | 'cancel';
 *
 * const machine = new StateMachine<OrderState, OrderEvent>('pending', [
 *   { from: 'pending', event: 'pay',    to: 'paid' },
 *   { from: 'paid',    event: 'ship',   to: 'shipped' },
 *   { from: 'pending', event: 'cancel', to: 'cancelled' },
 * ]);
 *
 * machine.onEnter('shipped', () => sendNotification());
 * machine.send('pay');   // true, state -> 'paid'
 * machine.send('ship');  // true, state -> 'shipped'
 * ```
 */
class StateMachine<S extends string, E extends string> {
  /**
   * Create a state machine.
   * @param initial - The starting state.
   * @param transitions - Array of valid state transitions.
   */
  constructor(initial: S, transitions: StateTransition<S, E>[]) { ... }

  /**
   * Get the current state.
   * @returns The current state value.
   */
  getState(): S { ... }

  /**
   * Attempt a state transition by sending an event.
   *
   * Finds a matching transition from the current state for the given
   * event. If a guard is defined, it must return true for the transition
   * to proceed. On success, the state changes, the action runs, and
   * onEnter listeners for the new state are called.
   *
   * @param event - The event to send.
   * @returns `true` if the transition succeeded, `false` if no matching
   *   transition was found or the guard rejected it.
   */
  send(event: E): boolean { ... }

  /**
   * Register a callback that fires whenever the machine enters a state.
   *
   * @param state - The state to listen for.
   * @param callback - Function called when the machine transitions
   *   into the specified state.
   * @returns An unsubscribe function to remove the listener.
   */
  onEnter(state: S, callback: () => void): () => void { ... }
}
```'''
    },
]
