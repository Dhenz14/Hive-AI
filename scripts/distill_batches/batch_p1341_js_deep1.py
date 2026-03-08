"""JavaScript/TypeScript deep reasoning pairs batch 1: async, types, closures, Node.js, error handling."""
PAIRS = [
    # -- 01-05: Async patterns ------------------------------------------------
    ("js_deep1_01", r'''How do I compose multiple Promises in JavaScript beyond Promise.all? Show me Promise.allSettled, Promise.any, Promise.race, and custom combinators for real-world scenarios.''', r'''<think>
The user wants to go deeper than just Promise.all.
Promise.allSettled waits for all, giving status objects -- great for best-effort operations.
Promise.any resolves with the first fulfilled, throws AggregateError if all reject -- good for racing mirrors.
Promise.race resolves/rejects with the first to settle -- useful for timeouts.
Custom combinators like "first N of M" or "all with timeout" are common in production.
I should show each with a practical use case, not just the API signature.
Key gotcha: Promise.all short-circuits on first rejection, allSettled never does.
Another gotcha: Promise.race does not cancel the losers -- they keep running.
I should show a timeout combinator using Promise.race and AbortController.
Also worth showing a custom promiseMap that limits concurrency (p-limit pattern).
I will use modern async/await syntax throughout.
</think>

Here is a comprehensive guide to Promise composition in modern JavaScript:

```typescript
// -- Promise.allSettled: best-effort batch operations --
// Unlike Promise.all, this NEVER rejects -- you get results for everything
async function sendNotifications(users: User[]) {
  const results = await Promise.allSettled(
    users.map(user => sendEmail(user.email))
  );

  const succeeded = results.filter(
    (r): r is PromiseFulfilledResult<void> => r.status === "fulfilled"
  );
  const failed = results.filter(
    (r): r is PromiseRejectedResult => r.status === "rejected"
  );

  console.log(`Sent: ${succeeded.length}, Failed: ${failed.length}`);
  failed.forEach(f => console.error("Notification failed:", f.reason));
}

// -- Promise.any: first success wins (mirror racing) --
async function fetchFromMirrors(url: string): Promise<Response> {
  const mirrors = [
    `https://cdn1.example.com${url}`,
    `https://cdn2.example.com${url}`,
    `https://cdn3.example.com${url}`,
  ];

  try {
    return await Promise.any(mirrors.map(m => fetch(m)));
  } catch (err) {
    if (err instanceof AggregateError) {
      console.error("All mirrors failed:", err.errors);
    }
    throw err;
  }
}

// -- Promise.race: timeout combinator --
function withTimeout<T>(promise: Promise<T>, ms: number): Promise<T> {
  const timeout = new Promise<never>((_, reject) =>
    setTimeout(() => reject(new Error(`Timed out after ${ms}ms`)), ms)
  );
  return Promise.race([promise, timeout]);
}

// -- Custom combinator: first N of M --
async function firstN<T>(
  promises: Promise<T>[],
  n: number
): Promise<T[]> {
  return new Promise((resolve, reject) => {
    const results: T[] = [];
    let settled = false;
    let rejections = 0;

    for (const p of promises) {
      p.then(value => {
        if (settled) return;
        results.push(value);
        if (results.length === n) {
          settled = true;
          resolve(results);
        }
      }).catch(() => {
        rejections++;
        if (rejections > promises.length - n) {
          settled = true;
          reject(new Error(`Not enough promises fulfilled (need ${n})`));
        }
      });
    }
  });
}

// -- Custom combinator: retry with backoff --
async function retryAsync<T>(
  fn: () => Promise<T>,
  maxRetries = 3,
  baseDelay = 1000
): Promise<T> {
  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (err) {
      if (attempt === maxRetries) throw err;
      const delay = baseDelay * Math.pow(2, attempt) + Math.random() * 100;
      await new Promise(r => setTimeout(r, delay));
    }
  }
  throw new Error("Unreachable");
}
```

Key rules:
- `Promise.all` -- fail fast, all-or-nothing
- `Promise.allSettled` -- always wait for everything, inspect each result
- `Promise.any` -- first success, AggregateError if all fail
- `Promise.race` -- first to settle (success OR failure) wins
- None of these cancel the losers -- use AbortController for that'''),

    ("js_deep1_02", r'''Show me how to build a proper async iterator in JavaScript/TypeScript that can paginate through an API, with backpressure support.''', r'''<think>
Async iterators are the right abstraction for paginated API calls.
The Symbol.asyncIterator protocol requires a next() returning Promise of {value, done}.
Using async generator functions (async function*) is the cleanest syntax.
Backpressure is automatic with for-await-of: the consumer controls the pace.
Each iteration only fetches the next page when the consumer asks for it.
I should show both the async generator approach and the manual protocol.
Real-world: cursor-based pagination (not offset) since offset has drift issues.
I should show how to compose async iterables with map/filter/take helpers.
TypeScript typing: AsyncIterable and AsyncIterableIterator are the interfaces.
I will include a concrete example with cursor-based pagination.
</think>

Here is a production-quality async iterator for API pagination:

```typescript
interface Page<T> {
  data: T[];
  cursor: string | null;
}

async function* paginate<T>(
  fetchPage: (cursor?: string) => Promise<Page<T>>
): AsyncGenerator<T, void, undefined> {
  let cursor: string | undefined;

  while (true) {
    const page = await fetchPage(cursor);

    for (const item of page.data) {
      yield item;
    }

    if (page.cursor === null) return;
    cursor = page.cursor;
  }
}

// Usage with a real API
interface User { id: string; name: string; }

async function fetchUsers(cursor?: string): Promise<Page<User>> {
  const url = new URL("https://api.example.com/users");
  url.searchParams.set("limit", "100");
  if (cursor) url.searchParams.set("cursor", cursor);

  const resp = await fetch(url);
  if (!resp.ok) throw new Error(`API error: ${resp.status}`);
  return resp.json();
}

// Backpressure: each page fetched only when the loop needs more items
async function processAllUsers() {
  for await (const user of paginate(fetchUsers)) {
    await saveToDatabase(user);  // Slow consumer? Next page waits
    console.log(`Processed ${user.name}`);
  }
}

// Composable async iterable helpers
async function* asyncMap<T, U>(
  source: AsyncIterable<T>,
  fn: (item: T) => U | Promise<U>
): AsyncGenerator<U> {
  for await (const item of source) {
    yield await fn(item);
  }
}

async function* asyncFilter<T>(
  source: AsyncIterable<T>,
  predicate: (item: T) => boolean | Promise<boolean>
): AsyncGenerator<T> {
  for await (const item of source) {
    if (await predicate(item)) yield item;
  }
}

async function* asyncTake<T>(
  source: AsyncIterable<T>,
  n: number
): AsyncGenerator<T> {
  let count = 0;
  for await (const item of source) {
    yield item;
    if (++count >= n) return;
  }
}

// Compose them together
async function getFirst50ActiveUsers() {
  const allUsers = paginate(fetchUsers);
  const active = asyncFilter(allUsers, u => u.name !== "deleted");
  const first50 = asyncTake(active, 50);

  const results: User[] = [];
  for await (const user of first50) {
    results.push(user);
  }
  return results;
}

// Manual protocol (for when you need more control)
class PaginatedIterator<T> implements AsyncIterableIterator<T> {
  private buffer: T[] = [];
  private cursor: string | undefined;
  private done = false;

  constructor(
    private fetchPage: (cursor?: string) => Promise<Page<T>>
  ) {}

  async next(): Promise<IteratorResult<T>> {
    if (this.buffer.length === 0 && !this.done) {
      const page = await this.fetchPage(this.cursor);
      this.buffer = page.data;
      this.cursor = page.cursor ?? undefined;
      if (page.cursor === null) this.done = true;
    }

    if (this.buffer.length > 0) {
      return { value: this.buffer.shift()!, done: false };
    }
    return { value: undefined as any, done: true };
  }

  [Symbol.asyncIterator]() { return this; }
}
```

The key insight: `for await...of` provides **automatic backpressure**. The generator pauses at each `yield` until the consumer calls `next()`, so a slow consumer will not cause unbounded memory growth from prefetching pages.'''),

    ("js_deep1_03", r'''How do I limit concurrent async operations in JavaScript? I have 1000 URLs to fetch but only want 10 running at once.''', r'''<think>
This is the concurrency limiter / semaphore pattern.
The naive approach is Promise.all(urls.map(fetch)) which fires all 1000 at once.
The correct approach is a pool/semaphore that limits active promises.
Chunk-based: split into groups of 10, await each group. Downside: waits for slowest.
Pool-based: always keep 10 in flight, start new one as soon as one finishes. Optimal throughput.
I should build a reusable pLimit function (like the npm package).
The core trick: maintain a queue, use a counter for active promises.
Key: the function returns a wrapper that gates execution.
TypeScript generics make this clean -- the wrapper preserves return types.
I will show pool-based, chunk-based, and an async generator pool variant.
</think>

Here is how to build a production-quality concurrency limiter from scratch:

```typescript
// The pLimit pattern: reusable concurrency limiter
function pLimit(concurrency: number) {
  const queue: (() => void)[] = [];
  let active = 0;

  function next() {
    if (queue.length > 0 && active < concurrency) {
      active++;
      const run = queue.shift()!;
      run();
    }
  }

  return <T>(fn: () => Promise<T>): Promise<T> => {
    return new Promise<T>((resolve, reject) => {
      queue.push(() => {
        fn().then(resolve, reject).finally(() => {
          active--;
          next();
        });
      });
      next();
    });
  };
}

// Usage: fetch 1000 URLs, 10 at a time
async function fetchAllUrls(urls: string[]): Promise<Response[]> {
  const limit = pLimit(10);

  const results = await Promise.all(
    urls.map(url => limit(() => fetch(url)))
  );

  return results;
}

// With progress tracking
async function fetchWithProgress(urls: string[]) {
  const limit = pLimit(10);
  let completed = 0;

  const results = await Promise.allSettled(
    urls.map(url =>
      limit(async () => {
        const resp = await fetch(url);
        completed++;
        if (completed % 100 === 0) {
          console.log(`Progress: ${completed}/${urls.length}`);
        }
        return resp.json();
      })
    )
  );

  return results;
}

// Alternative: async pool with iterator (memory efficient)
async function* asyncPool<T, R>(
  concurrency: number,
  items: T[],
  fn: (item: T) => Promise<R>
): AsyncGenerator<R> {
  const executing = new Set<Promise<[R, Promise<R>]>>();

  for (const item of items) {
    const p: Promise<[R, Promise<R>]> = fn(item).then(
      result => [result, p] as [R, Promise<R>]
    );
    executing.add(p);

    if (executing.size >= concurrency) {
      const [result, completed] = await Promise.race(executing);
      executing.delete(completed);
      yield result;
    }
  }

  for (const p of executing) {
    const [result] = await p;
    yield result;
  }
}

// Results arrive as they complete
for await (const data of asyncPool(10, urls, url => fetch(url).then(r => r.json()))) {
  console.log("Got result:", data);
}

// Simple chunk approach (less optimal but simpler)
async function fetchInChunks<T>(
  items: T[],
  batchSize: number,
  fn: (item: T) => Promise<void>
): Promise<void> {
  for (let i = 0; i < items.length; i += batchSize) {
    const chunk = items.slice(i, i + batchSize);
    await Promise.all(chunk.map(fn));
  }
}
```

The pool approach is superior to chunking because it keeps exactly N operations in flight at all times. With chunking, if 9 of 10 finish in 100ms but one takes 5s, you waste 4.9s of potential throughput.'''),

    ("js_deep1_04", r'''How do errors propagate through async/await chains in JavaScript? What are the gotchas with unhandled rejections and how do I handle them properly?''', r'''<think>
Error propagation in async/await has several non-obvious gotchas.
When you await a rejected promise, it throws -- that is the easy part.
The hard part: forgetting to await creates floating promises that reject silently.
Node.js has unhandledRejection events; browsers have unhandledrejection.
Since Node 15, unhandled rejections terminate the process by default.
Key gotchas: forgetting to await, return vs return await in try/catch, forEach not awaiting.
With Promise.all, if one rejects, the others keep running but results are lost.
Another gotcha: try/catch only catches if you await inside the try block.
The return await lint rule is relevant -- return await is needed inside try/catch.
I need to cover the global safety net with process.on unhandledRejection.
</think>

Here is a deep dive into async error propagation and all the gotchas:

```typescript
// GOTCHA 1: Forgetting to await creates silent failures
async function bad_saveUser(user: User) {
  database.save(user);  // No await -- unhandled rejection if save() fails
  console.log("Saved!");  // Always prints, even if save failed
}

async function good_saveUser(user: User) {
  await database.save(user);  // Error will propagate to caller
  console.log("Saved!");
}

// GOTCHA 2: try/catch only works with await
async function misleadingTryCatch() {
  try {
    riskyAsyncOp();  // Not awaited, so catch never fires
  } catch (err) {
    console.log("This never runs!");
  }
}

async function correctTryCatch() {
  try {
    await riskyAsyncOp();
  } catch (err) {
    console.log("This runs when riskyAsyncOp rejects");
  }
}

// GOTCHA 3: return vs return await inside try/catch
async function returnWithoutAwait() {
  try {
    return asyncOp();  // Returns the promise, catch never fires
  } catch (err) {
    handleError(err);  // Dead code
  }
}

async function returnWithAwait() {
  try {
    return await asyncOp();  // Unwraps, catches, then re-wraps
  } catch (err) {
    handleError(err);  // This works
    throw err;
  }
}

// GOTCHA 4: forEach does NOT await
async function processItems_BROKEN(items: string[]) {
  items.forEach(async (item) => {
    await processItem(item);  // Each iteration spawns a floating promise
  });
  console.log("Done!");  // Runs before any processing finishes
}

async function processItems_CORRECT(items: string[]) {
  for (const item of items) {
    await processItem(item);
  }
  // OR parallel:
  await Promise.all(items.map(item => processItem(item)));
  console.log("Done!");  // Runs after all processing
}

// GOTCHA 5: Promise.all loses results on rejection
async function fragileParallel() {
  try {
    const [a, b, c] = await Promise.all([task1(), task2(), task3()]);
  } catch (err) {
    // You know something failed but not what succeeded
  }
}

async function robustParallel() {
  const results = await Promise.allSettled([task1(), task2(), task3()]);
  for (const r of results) {
    if (r.status === "fulfilled") use(r.value);
    else logError(r.reason);
  }
}

// Global safety nets
process.on("unhandledRejection", (reason, promise) => {
  console.error("Unhandled rejection at:", promise, "reason:", reason);
  process.exit(1);
});

window.addEventListener("unhandledrejection", (event) => {
  console.error("Unhandled rejection:", event.reason);
  event.preventDefault();
});

// Pattern: error boundary wrapper
function withErrorBoundary<T extends (...args: any[]) => Promise<any>>(
  fn: T,
  onError: (err: unknown) => void
): T {
  return (async (...args: any[]) => {
    try {
      return await fn(...args);
    } catch (err) {
      onError(err);
      throw err;
    }
  }) as T;
}

const safeFetch = withErrorBoundary(
  async (url: string) => {
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    return resp.json();
  },
  (err) => errorTracker.capture(err)
);
```

The golden rule: **every Promise must be either awaited, returned, or explicitly handled with `.catch()`**. If you see an async function call without one of those three, it is a bug.'''),

    ("js_deep1_05", r'''How do I use AbortController to cancel fetch requests and other async operations in JavaScript? Show me real-world patterns including timeouts and user-initiated cancellation.''', r'''<think>
AbortController is the standard cancellation mechanism in JS.
It works with fetch natively, and can be adapted for any async operation.
Key parts: controller.signal (passed to operations), controller.abort() (triggers cancellation).
The signal has an abort event and an aborted boolean property.
AbortSignal.timeout() is a newer static method for simple timeout cases.
AbortSignal.any() combines multiple signals (like CancellationTokenSource linking).
Real-world uses: cancel on route change, cancel on component unmount, request timeouts.
Key gotcha: AbortError is the error name, not a separate class.
Another gotcha: once aborted, a signal stays aborted forever -- new controller for retries.
I will use modern APIs: AbortSignal.timeout() and AbortSignal.any() (Node 20+).
</think>

Here is a thorough guide to AbortController patterns:

```typescript
// Basic fetch cancellation
async function fetchWithCancel(url: string) {
  const controller = new AbortController();
  const fetchPromise = fetch(url, { signal: controller.signal });

  setTimeout(() => controller.abort(), 5000);

  try {
    const resp = await fetchPromise;
    return await resp.json();
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      console.log("Request was cancelled");
      return null;
    }
    throw err;
  }
}

// AbortSignal.timeout() -- cleaner timeout (Node 18+)
async function fetchWithTimeout(url: string) {
  const resp = await fetch(url, {
    signal: AbortSignal.timeout(5000),
  });
  return resp.json();
}

// AbortSignal.any() -- combine signals (Node 20+)
async function fetchWithCombinedSignals(
  url: string,
  userSignal: AbortSignal
) {
  const resp = await fetch(url, {
    signal: AbortSignal.any([
      userSignal,
      AbortSignal.timeout(10000),
    ]),
  });
  return resp.json();
}

// React: cancel on unmount
function useAsyncData<T>(url: string) {
  const [data, setData] = React.useState<T | null>(null);
  const [error, setError] = React.useState<Error | null>(null);

  React.useEffect(() => {
    const controller = new AbortController();

    fetch(url, { signal: controller.signal })
      .then(r => r.json())
      .then(setData)
      .catch(err => {
        if (err.name !== "AbortError") setError(err);
      });

    return () => controller.abort();
  }, [url]);

  return { data, error };
}

// SPA: cancel previous request on new search
class SearchService {
  private currentController: AbortController | null = null;

  async search(query: string): Promise<SearchResult[]> {
    this.currentController?.abort();
    this.currentController = new AbortController();

    const resp = await fetch(`/api/search?q=${encodeURIComponent(query)}`, {
      signal: this.currentController.signal,
    });
    return resp.json();
  }
}

// Custom abortable operations (non-fetch)
function abortableDelay(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      return reject(new DOMException("Aborted", "AbortError"));
    }

    const timer = setTimeout(resolve, ms);

    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    }, { once: true });
  });
}

async function longRunningTask(signal: AbortSignal) {
  const items = await fetchItems();

  for (const item of items) {
    if (signal.aborted) {
      throw new DOMException("Aborted", "AbortError");
    }
    await processItem(item);
    await abortableDelay(100, signal);
  }
}

function isAbortError(err: unknown): boolean {
  return err instanceof DOMException && err.name === "AbortError";
}

async function resilientFetch(url: string, signal?: AbortSignal) {
  try {
    return await fetch(url, { signal });
  } catch (err) {
    if (isAbortError(err)) return null;
    throw err;
  }
}
```

Key points: `AbortSignal.timeout()` replaces manual setTimeout+abort. `AbortSignal.any()` merges multiple cancellation sources. Always check `err.name === "AbortError"` to distinguish cancellation from real errors. In React, return `() => controller.abort()` from useEffect.'''),

    # -- 06-10: TypeScript type system -----------------------------------------
    ("js_deep1_06", r'''Show me advanced TypeScript generics patterns: constrained generics, generic defaults, generic inference from function arguments, and the generic slot pattern for type-safe APIs.''', r'''<think>
TypeScript generics go way beyond simple angle-bracket T.
Constrained generics use extends to limit what T can be.
Generic defaults (T = string) let callers omit the type arg.
The inference trick: TS infers T from the argument you pass, so you rarely need to specify it.
The generic slot pattern is for builder APIs where you accumulate type info across chained calls.
I should show real patterns, not contrived examples.
The extends constraint is the most powerful tool -- T must have property X.
I will show: constrained generics, defaults, inference, builder/slot pattern, and NoInfer.
TypeScript 4.0+ variadic tuple types make inference cleaner.
NoInfer (TS 5.4+) prevents unwanted widening from secondary parameters.
</think>

Here are production-grade TypeScript generics patterns:

```typescript
// 1. Constrained generics -- narrow what T can be

function findById<T extends { id: string }>(items: T[], id: string): T | undefined {
  return items.find(item => item.id === id);
}

const user = findById([{ id: "1", name: "Alice" }], "1");
// user is { id: string; name: string } | undefined

function getProperty<Obj, K extends keyof Obj>(obj: Obj, key: K): Obj[K] {
  return obj[key];
}
const name = getProperty({ name: "Alice", age: 30 }, "name");  // string

// 2. Generic defaults -- optional type parameters

interface ApiResponse<TData = unknown, TError = Error> {
  data: TData | null;
  error: TError | null;
  status: number;
}

const resp1: ApiResponse = { data: null, error: null, status: 200 };
const resp2: ApiResponse<User> = { data: user, error: null, status: 200 };

// 3. Inference from arguments -- let TS figure it out

function createState<T>(initial: T) {
  let value = initial;
  return {
    get: (): T => value,
    set: (next: T) => { value = next; },
  };
}

const counter = createState(0);    // T inferred as number
const label = createState("hi");   // T inferred as string
counter.set("wrong");              // Error: string is not number

function tuple<T extends unknown[]>(...args: T): T {
  return args;
}
const t = tuple(1, "hello", true);  // [number, string, boolean]

function createRoutes<T extends Record<string, (...args: any[]) => any>>(
  routes: T
): T {
  return routes;
}

const routes = createRoutes({
  "/users": (id: string) => fetchUser(id),
  "/posts": (page: number) => fetchPosts(page),
});

// 4. The generic slot pattern -- type-safe builders

class QueryBuilder<TSelect = {}, TWhere = {}> {
  private _select: string[] = [];
  private _where: Record<string, unknown> = {};

  select<K extends string>(
    ...fields: K[]
  ): QueryBuilder<TSelect & Record<K, unknown>, TWhere> {
    this._select.push(...fields);
    return this as any;
  }

  where<K extends string, V>(
    field: K,
    value: V
  ): QueryBuilder<TSelect, TWhere & Record<K, V>> {
    this._where[field] = value;
    return this as any;
  }

  build(): { select: TSelect; where: TWhere } {
    return { select: this._select, where: this._where } as any;
  }
}

const query = new QueryBuilder()
  .select("name", "email")
  .where("age", 30)
  .where("active", true)
  .build();
// query.where.age is number, query.where.active is boolean

// 5. NoInfer -- prevent unwanted inference (TS 5.4+)

function getOrDefault_BAD<T>(value: T | null, defaultValue: T): T {
  return value ?? defaultValue;
}
// getOrDefault_BAD("hello", 42) -- T widens to string | number (wrong!)

function getOrDefault<T>(value: T | null, defaultValue: NoInfer<T>): T {
  return value ?? defaultValue;
}
// getOrDefault("hello", 42) -- Error: 42 is not assignable to string
```

The mental model: generics are **type variables** that TS fills in based on usage context. Use constraints (`extends`) to narrow them, defaults for optional params, and the slot pattern for accumulative builders.'''),

    ("js_deep1_07", r'''Explain TypeScript mapped types and show how to build custom utility types like DeepReadonly, DeepPartial, and PickByType.''', r'''<think>
Mapped types iterate over keys of a type and transform each property.
The syntax is { [K in keyof T]: ... }.
You can add/remove modifiers: readonly, optional (?).
Built-in utility types (Partial, Required, Readonly, Pick) are all mapped types.
DeepReadonly needs recursion: if a property is an object, apply DeepReadonly to it.
DeepPartial similarly recurses into nested objects.
PickByType filters properties by their value type -- needs conditional types.
Key insight: mapped types + conditional types = powerful type transformations.
I should also show key remapping with the as clause (TS 4.1+).
Template literal types in key remapping enable things like getX / setX from property x.
I will build each utility type from scratch with explanations.
</think>

Here is how mapped types work and how to build custom utilities:

```typescript
// Mapped type basics -- iterate over keys, transform values

// This is how Partial<T> works internally
type MyPartial<T> = {
  [K in keyof T]?: T[K];
};

// This is how Readonly<T> works
type MyReadonly<T> = {
  readonly [K in keyof T]: T[K];
};

// DeepReadonly -- recursively freeze nested objects
type DeepReadonly<T> =
  T extends (infer U)[]
    ? ReadonlyArray<DeepReadonly<U>>
    : T extends object
      ? { readonly [K in keyof T]: DeepReadonly<T[K]> }
      : T;

interface Config {
  db: { host: string; port: number; options: { ssl: boolean } };
  cache: { ttl: number };
}

type FrozenConfig = DeepReadonly<Config>;

const config: FrozenConfig = {
  db: { host: "localhost", port: 5432, options: { ssl: true } },
  cache: { ttl: 3600 },
};
// config.db.port = 3000;          // Error
// config.db.options.ssl = false;  // Error -- deep readonly works

// DeepPartial -- recursively make everything optional
type DeepPartial<T> =
  T extends (infer U)[]
    ? DeepPartial<U>[]
    : T extends object
      ? { [K in keyof T]?: DeepPartial<T[K]> }
      : T;

function mergeConfig(
  base: Config,
  overrides: DeepPartial<Config>
): Config {
  return {
    db: { ...base.db, ...overrides.db,
      options: { ...base.db.options, ...overrides.db?.options } },
    cache: { ...base.cache, ...overrides.cache },
  };
}

mergeConfig(defaultConfig, { db: { port: 3000 } });

// PickByType -- filter properties by value type
type PickByType<T, ValueType> = {
  [K in keyof T as T[K] extends ValueType ? K : never]: T[K];
};

interface User {
  id: number;
  name: string;
  email: string;
  age: number;
  active: boolean;
}

type StringProps = PickByType<User, string>;
// { name: string; email: string }

type NumericProps = PickByType<User, number>;
// { id: number; age: number }

// OmitByType -- the inverse
type OmitByType<T, ValueType> = {
  [K in keyof T as T[K] extends ValueType ? never : K]: T[K];
};

// Key remapping with as -- create getter/setter types
type Getters<T> = {
  [K in keyof T as `get${Capitalize<string & K>}`]: () => T[K];
};

type Setters<T> = {
  [K in keyof T as `set${Capitalize<string & K>}`]: (value: T[K]) => void;
};

type UserGetters = Getters<User>;
// { getId: () => number; getName: () => string; ... }

// RequiredKeys / OptionalKeys extraction
type RequiredKeys<T> = {
  [K in keyof T]-?: {} extends Pick<T, K> ? never : K;
}[keyof T];

type OptionalKeys<T> = {
  [K in keyof T]-?: {} extends Pick<T, K> ? K : never;
}[keyof T];

interface Form {
  name: string;
  email: string;
  nickname?: string;
  bio?: string;
}

type Req = RequiredKeys<Form>;  // "name" | "email"
type Opt = OptionalKeys<Form>;  // "nickname" | "bio"
```

The power of mapped types comes from three features: key iteration (`in keyof`), modifier changes (`+/-readonly`, `+/-?`), and key remapping (`as`). Combined with conditional types, you can express nearly any type transformation.'''),

    ("js_deep1_08", r'''Show me how TypeScript conditional types work, including infer, distributive conditionals, and practical patterns like extracting function return types or unwrapping Promises.''', r'''<think>
Conditional types are TypeScript's if/else for types.
Syntax: T extends U ? X : Y -- if T is assignable to U, resolve to X, else Y.
The infer keyword lets you extract parts of a type inside the condition.
Distributive behavior: when T is a union, the conditional distributes over each member.
This is how ReturnType, Parameters, and Awaited are built.
Key patterns: unwrap promises, extract array element types, function overload resolution.
I should show how to disable distribution with [T] extends [U].
The infer keyword can extract from function signatures, tuple positions, template literals.
I will build several utility types showing each concept.
</think>

Here is a complete guide to conditional types:

```typescript
// Basic conditional types -- type-level if/else
type IsString<T> = T extends string ? true : false;

type A = IsString<"hello">;  // true
type B = IsString<42>;       // false

// infer -- extract parts of a type

// This is how ReturnType works
type MyReturnType<T> = T extends (...args: any[]) => infer R ? R : never;

type FnReturn = MyReturnType<(x: number) => string>;  // string

// Extract element type from an array
type ElementOf<T> = T extends (infer E)[] ? E : never;
type Elem = ElementOf<string[]>;  // string

// Recursive promise unwrapping
type UnwrapPromise<T> =
  T extends Promise<infer U>
    ? UnwrapPromise<U>
    : T;

type Inner = UnwrapPromise<Promise<Promise<number>>>;  // number

// Extract function parameters
type MyParameters<T> = T extends (...args: infer P) => any ? P : never;
type Params = MyParameters<(a: string, b: number) => void>;
// [a: string, b: number]

// Distributive conditionals -- unions get mapped
type ToArray<T> = T extends any ? T[] : never;
type Distributed = ToArray<string | number>;
// string[] | number[]  (NOT (string | number)[])

// This is how Exclude works
type MyExclude<T, U> = T extends U ? never : T;
type Filtered = MyExclude<"a" | "b" | "c", "a" | "c">;  // "b"

// This is how Extract works
type MyExtract<T, U> = T extends U ? T : never;
type Kept = MyExtract<string | number | boolean, number | boolean>;
// number | boolean

// Preventing distribution with [T] extends [U]
type ToArrayNonDist<T> = [T] extends [any] ? T[] : never;
type NonDistributed = ToArrayNonDist<string | number>;
// (string | number)[]  -- single array type, not a union

// Check if type IS a union
type IsUnion<T, U = T> =
  T extends any
    ? [U] extends [T] ? false : true
    : never;

type TestUnion = IsUnion<"a" | "b">;  // true
type TestSingle = IsUnion<"a">;        // false

// Advanced infer: template literal extraction
type ParseRoute<T> =
  T extends `${string}:${infer Param}/${infer Rest}`
    ? Param | ParseRoute<Rest>
    : T extends `${string}:${infer Param}`
      ? Param
      : never;

type RouteParams = ParseRoute<"/users/:userId/posts/:postId">;
// "userId" | "postId"

// Practical: type-safe event handlers
interface EventMap {
  click: { x: number; y: number };
  keydown: { key: string; code: string };
  scroll: { scrollY: number };
}

function on<K extends keyof EventMap>(
  event: K,
  handler: (event: EventMap[K]) => void
): void { }

on("click", (e) => console.log(e.x, e.y));
on("keydown", (e) => console.log(e.key));
```

The three pillars: **conditional check** (`extends ? :`), **type extraction** (`infer`), and **distribution** (automatic mapping over unions). Master these and you can express any type-level computation.'''),

    ("js_deep1_09", r'''Show me how to use TypeScript template literal types to build type-safe string manipulation, route matching, and event naming patterns.''', r'''<think>
Template literal types (TS 4.1+) let you manipulate string types at the type level.
Syntax: backtick with ${...} inside a type creates a string pattern type.
Combined with conditional types and infer, you can parse and transform strings.
Built-in intrinsic types: Uppercase, Lowercase, Capitalize, Uncapitalize.
Use cases: CSS-in-JS property names, route parameter extraction, event name conventions.
Key pattern: recursive template literal types can tokenize strings.
Template literal types distribute over unions, so you get cross-product behavior.
I will focus on practical patterns: event naming, route params, dot paths, camelToKebab.
</think>

Here are template literal type patterns for real-world TypeScript:

```typescript
// Basic template literal types -- string construction
type Greeting = `Hello, ${string}`;
const valid: Greeting = "Hello, world";

// Union distribution: creates all combinations
type Color = "red" | "blue" | "green";
type Size = "sm" | "md" | "lg";
type ClassName = `${Color}-${Size}`;
// "red-sm" | "red-md" | "red-lg" | "blue-sm" | ...

// Event naming convention: on + Capitalize
type EventName = "click" | "focus" | "blur" | "scroll";
type HandlerName = `on${Capitalize<EventName>}`;
// "onClick" | "onFocus" | "onBlur" | "onScroll"

type Handlers = {
  [K in EventName as `on${Capitalize<K>}`]: (event: Event) => void;
};

// Route parameter extraction
type ExtractParams<T extends string> =
  T extends `${string}:${infer Param}/${infer Rest}`
    ? { [K in Param | keyof ExtractParamsHelper<Rest>]: string }
    : T extends `${string}:${infer Param}`
      ? { [K in Param]: string }
      : {};

type ExtractParamsHelper<T extends string> =
  T extends `${string}:${infer Param}/${infer Rest}`
    ? { [K in Param]: string } & ExtractParamsHelper<Rest>
    : T extends `${string}:${infer Param}`
      ? { [K in Param]: string }
      : {};

function createRoute<T extends string>(
  path: T,
  handler: (params: ExtractParams<T>) => void
) { }

createRoute("/users/:userId/posts/:postId", (params) => {
  params.userId;   // string -- autocomplete works
  params.postId;   // string
});

// Dot-notation path access
interface Nested {
  user: {
    name: string;
    address: { city: string; zip: number };
  };
  tags: string[];
}

type DotPath<T, Prefix extends string = ""> =
  T extends object
    ? {
        [K in keyof T & string]:
          | `${Prefix}${K}`
          | DotPath<T[K], `${Prefix}${K}.`>
      }[keyof T & string]
    : never;

type Paths = DotPath<Nested>;
// "user" | "user.name" | "user.address" | "user.address.city" | ...

type GetAtPath<T, P extends string> =
  P extends `${infer Key}.${infer Rest}`
    ? Key extends keyof T ? GetAtPath<T[Key], Rest> : never
    : P extends keyof T ? T[P] : never;

type CityType = GetAtPath<Nested, "user.address.city">;  // string
type ZipType = GetAtPath<Nested, "user.address.zip">;    // number

function getValue<T, P extends DotPath<T>>(
  obj: T,
  path: P
): GetAtPath<T, P> {
  return path.split(".").reduce((o: any, k) => o[k], obj);
}

// CSS-in-JS: camelCase to kebab-case
type CamelToKebab<S extends string> =
  S extends `${infer Head}${infer Tail}`
    ? Head extends Uppercase<Head>
      ? `-${Lowercase<Head>}${CamelToKebab<Tail>}`
      : `${Head}${CamelToKebab<Tail>}`
    : S;

type KebabCSS = CamelToKebab<"backgroundColor">;  // "background-color"
type KebabCSS2 = CamelToKebab<"borderTopWidth">;   // "border-top-width"

// SQL-like query validation
type Table = "users" | "posts" | "comments";
type Select = `SELECT ${string} FROM ${Table}`;

function query<T extends Select>(sql: T): void { }
query("SELECT name FROM users");          // OK
// query("SELECT name FROM invalid");     // Error
```

Template literal types turn TypeScript into a string-processing type system. The key patterns are: **construction** (unions distribute into all combinations), **extraction** (`infer` inside template positions), and **recursion** (process strings segment by segment).'''),

    ("js_deep1_10", r'''Explain TypeScript discriminated unions and show how to use them for type-safe state machines, API responses, and exhaustive pattern matching.''', r'''<think>
Discriminated unions are the most important pattern in TypeScript for modeling variants.
Each member of the union has a common literal property (the discriminant).
When you switch/if on the discriminant, TS narrows the type automatically.
The never type enables exhaustive checking -- if you miss a case, TS tells you.
Use cases: Redux actions, API response types, state machines, AST nodes.
The assertNever pattern catches missing cases at compile time AND runtime.
Discriminated unions are better than class hierarchies for data modeling in TS.
I will also show how to derive action creators from a discriminated union type.
</think>

Here is a deep dive into discriminated unions:

```typescript
// Basic discriminated union -- the type field narrows
type Shape =
  | { type: "circle"; radius: number }
  | { type: "rectangle"; width: number; height: number }
  | { type: "triangle"; base: number; height: number };

function area(shape: Shape): number {
  switch (shape.type) {
    case "circle":
      return Math.PI * shape.radius ** 2;
    case "rectangle":
      return shape.width * shape.height;
    case "triangle":
      return 0.5 * shape.base * shape.height;
  }
}

// Exhaustive checking with assertNever
function assertNever(x: never): never {
  throw new Error(`Unexpected value: ${JSON.stringify(x)}`);
}

function areaExhaustive(shape: Shape): number {
  switch (shape.type) {
    case "circle":    return Math.PI * shape.radius ** 2;
    case "rectangle": return shape.width * shape.height;
    case "triangle":  return 0.5 * shape.base * shape.height;
    default:          return assertNever(shape);
  }
}

// API response modeling
type ApiResult<T> =
  | { status: "loading" }
  | { status: "success"; data: T }
  | { status: "error"; error: string; retryable: boolean };

function renderResult<T>(result: ApiResult<T>): string {
  switch (result.status) {
    case "loading": return "Loading...";
    case "success": return `Got data: ${JSON.stringify(result.data)}`;
    case "error":   return result.retryable
      ? `Error: ${result.error} (click to retry)`
      : `Fatal: ${result.error}`;
  }
}

// State machine with discriminated unions
type ConnectionState =
  | { state: "disconnected" }
  | { state: "connecting"; attempt: number }
  | { state: "connected"; socket: WebSocket; connectedAt: Date }
  | { state: "error"; error: Error; lastAttempt: Date };

type ConnectionEvent =
  | { type: "CONNECT" }
  | { type: "CONNECTED"; socket: WebSocket }
  | { type: "DISCONNECT" }
  | { type: "ERROR"; error: Error };

function transition(
  state: ConnectionState,
  event: ConnectionEvent
): ConnectionState {
  switch (state.state) {
    case "disconnected":
      if (event.type === "CONNECT") {
        return { state: "connecting", attempt: 1 };
      }
      return state;

    case "connecting":
      switch (event.type) {
        case "CONNECTED":
          return { state: "connected", socket: event.socket, connectedAt: new Date() };
        case "ERROR":
          return state.attempt < 3
            ? { state: "connecting", attempt: state.attempt + 1 }
            : { state: "error", error: event.error, lastAttempt: new Date() };
        default: return state;
      }

    case "connected":
      if (event.type === "DISCONNECT" || event.type === "ERROR") {
        state.socket.close();
        return event.type === "DISCONNECT"
          ? { state: "disconnected" }
          : { state: "error", error: event.error, lastAttempt: new Date() };
      }
      return state;

    case "error":
      if (event.type === "CONNECT") return { state: "connecting", attempt: 1 };
      return state;

    default:
      return assertNever(state);
  }
}

// Derive action creators from union type
type Action =
  | { type: "ADD_TODO"; text: string }
  | { type: "TOGGLE_TODO"; id: number }
  | { type: "DELETE_TODO"; id: number }
  | { type: "SET_FILTER"; filter: "all" | "active" | "done" };

type ActionPayload<T extends Action["type"]> =
  Omit<Extract<Action, { type: T }>, "type">;

function createAction<T extends Action["type"]>(
  type: T,
  payload: ActionPayload<T>
): Extract<Action, { type: T }> {
  return { type, ...payload } as any;
}

const action = createAction("ADD_TODO", { text: "Buy milk" });

// Narrowing with type predicates
function isSuccess<T>(
  result: ApiResult<T>
): result is Extract<ApiResult<T>, { status: "success" }> {
  return result.status === "success";
}
```

Discriminated unions encode **valid states** in the type system. Invalid states like `{ state: "disconnected", socket: ws }` are unrepresentable. This eliminates entire categories of bugs at compile time.'''),

    # -- 11-15: Closures and functional patterns -------------------------------
    ("js_deep1_11", r'''Show me how to build a proper memoization function in JavaScript/TypeScript that handles multiple arguments, has cache eviction, and works with async functions.''', r'''<think>
Memoization caches function results based on arguments.
The simple version: Map with JSON.stringify(args) as key.
Problems: JSON.stringify is slow, does not handle circular refs, object identity issues.
Better: WeakMap for single-object-arg functions (automatic GC of cache entries).
For multiple args: use a trie/nested Map structure or a custom hash.
Cache eviction: LRU (least recently used) is the standard strategy.
Async memoization: cache the Promise itself, not the result, to avoid thundering herd.
I should show: simple memo, LRU memo, WeakMap memo, and async memo.
TypeScript: preserve the function signature using generics.
Key gotcha: memoizing methods requires binding or WeakMap keyed on this.
</think>

Here is a production-quality memoization library from scratch:

```typescript
// Simple memoize -- works for serializable args
function memoize<Args extends unknown[], R>(
  fn: (...args: Args) => R
): (...args: Args) => R {
  const cache = new Map<string, R>();

  return (...args: Args): R => {
    const key = JSON.stringify(args);
    if (cache.has(key)) return cache.get(key)!;
    const result = fn(...args);
    cache.set(key, result);
    return result;
  };
}

const expensiveCalc = memoize((n: number) => {
  console.log("Computing...");
  return fibonacci(n);
});
expensiveCalc(40);  // Computing... (slow)
expensiveCalc(40);  // Instant -- cached

// LRU memoize -- bounded cache with eviction
function memoizeLRU<Args extends unknown[], R>(
  fn: (...args: Args) => R,
  maxSize: number = 100
): (...args: Args) => R {
  const cache = new Map<string, R>();

  return (...args: Args): R => {
    const key = JSON.stringify(args);

    if (cache.has(key)) {
      const value = cache.get(key)!;
      cache.delete(key);
      cache.set(key, value);  // Move to end (most recently used)
      return value;
    }

    const result = fn(...args);
    cache.set(key, result);

    if (cache.size > maxSize) {
      const oldest = cache.keys().next().value;
      cache.delete(oldest!);
    }

    return result;
  };
}

// WeakMap memoize -- for single object arguments
function memoizeWeak<T extends object, R>(
  fn: (arg: T) => R
): (arg: T) => R {
  const cache = new WeakMap<T, R>();

  return (arg: T): R => {
    if (cache.has(arg)) return cache.get(arg)!;
    const result = fn(arg);
    cache.set(arg, result);
    return result;
  };
}

const getMetadata = memoizeWeak((node: HTMLElement) => {
  return { tagName: node.tagName, childCount: node.children.length };
});

// Async memoize -- caches the Promise to prevent thundering herd
function memoizeAsync<Args extends unknown[], R>(
  fn: (...args: Args) => Promise<R>,
  options: { maxSize?: number; ttlMs?: number } = {}
): (...args: Args) => Promise<R> {
  const { maxSize = 100, ttlMs } = options;
  const cache = new Map<string, { promise: Promise<R>; expiresAt?: number }>();

  return (...args: Args): Promise<R> => {
    const key = JSON.stringify(args);
    const cached = cache.get(key);

    if (cached) {
      if (!cached.expiresAt || Date.now() < cached.expiresAt) {
        return cached.promise;
      }
      cache.delete(key);
    }

    // Cache the PROMISE, not the result
    // If 10 callers ask simultaneously, only one fetch runs
    const promise = fn(...args).catch((err) => {
      cache.delete(key);  // On error, remove so next call retries
      throw err;
    });

    cache.set(key, {
      promise,
      expiresAt: ttlMs ? Date.now() + ttlMs : undefined,
    });

    if (cache.size > maxSize) {
      const oldest = cache.keys().next().value;
      cache.delete(oldest!);
    }

    return promise;
  };
}

const fetchUser = memoizeAsync(
  async (id: string) => {
    const resp = await fetch(`/api/users/${id}`);
    return resp.json();
  },
  { ttlMs: 60_000, maxSize: 500 }
);

// These two calls share a single HTTP request
const [a, b] = await Promise.all([fetchUser("123"), fetchUser("123")]);

// Trie-based memoize -- handles non-serializable args
function memoizeTrie<Args extends unknown[], R>(
  fn: (...args: Args) => R
): (...args: Args) => R {
  const root = new Map();
  const RESULT = Symbol("result");

  return (...args: Args): R => {
    let node = root;
    for (const arg of args) {
      if (!node.has(arg)) node.set(arg, new Map());
      node = node.get(arg);
    }
    if (node.has(RESULT)) return node.get(RESULT);
    const result = fn(...args);
    node.set(RESULT, result);
    return result;
  };
}
```

The key insight for async memoization: **cache the Promise, not the resolved value**. This prevents the thundering herd problem where 100 concurrent callers each trigger their own fetch.'''),

    ("js_deep1_12", r'''Show me how to implement currying and partial application in TypeScript with full type safety, including auto-currying any function.''', r'''<think>
Currying transforms f(a, b, c) into f(a)(b)(c).
Partial application fixes some arguments: partial(f, a) returns (b, c) => f(a, b, c).
TypeScript challenge: preserving parameter types through the transformation.
The key type is a recursive conditional that peels off arguments one at a time.
For auto-curry: accept 1+ args and return either the result or another curried function.
I need to handle: zero-arg functions, rest params, overloads.
TypeScript 4.0+ variadic tuple types make this cleaner.
I will show: simple curry, partial, auto-curry, and practical use cases.
I should include point-free style composition helpers.
</think>

Here is how to build type-safe currying and partial application:

```typescript
// Type: Curried function type (recursive)
type Curry<Args extends unknown[], R> =
  Args extends [infer First, ...infer Rest]
    ? (arg: First) => Curry<Rest, R>
    : R;

// Simple curry -- one arg at a time
function curry<Args extends unknown[], R>(
  fn: (...args: Args) => R
): Curry<Args, R> {
  const arity = fn.length;

  function curried(collected: unknown[]): any {
    if (collected.length >= arity) {
      return fn(...collected as Args);
    }
    return (arg: unknown) => curried([...collected, arg]);
  }

  return curried([]) as Curry<Args, R>;
}

const add = (a: number, b: number, c: number) => a + b + c;
const curriedAdd = curry(add);
const add5 = curriedAdd(5);
const add5and3 = add5(3);
const result = add5and3(2);  // 10

// Auto-curry: accept multiple args at once
type AutoCurry<Args extends unknown[], R> =
  Args extends []
    ? R
    : Args extends [infer First, ...infer Rest]
      ? Rest extends []
        ? (arg: First) => R
        : ((...args: Args) => R) & ((arg: First) => AutoCurry<Rest, R>)
      : never;

function autoCurry<Args extends unknown[], R>(
  fn: (...args: Args) => R
): AutoCurry<Args, R> {
  const arity = fn.length;

  function curried(...args: unknown[]): any {
    if (args.length >= arity) {
      return fn(...args as Args);
    }
    return (...more: unknown[]) => curried(...args, ...more);
  }

  return curried as AutoCurry<Args, R>;
}

const flexAdd = autoCurry(add);
flexAdd(1)(2)(3);    // 6
flexAdd(1, 2)(3);    // 6
flexAdd(1)(2, 3);    // 6
flexAdd(1, 2, 3);    // 6

// Partial application (fix leading arguments)
type PartialApply<Args extends unknown[], Applied extends unknown[]> =
  Applied extends [any, ...infer RestApplied]
    ? Args extends [any, ...infer RestArgs]
      ? PartialApply<RestArgs, RestApplied>
      : Args
    : Args;

function partial<Args extends unknown[], Applied extends unknown[], R>(
  fn: (...args: Args) => R,
  ...applied: Applied
): (...args: PartialApply<Args, Applied>) => R {
  return (...rest: any[]) => fn(...applied, ...rest) as any;
}

function greet(greeting: string, name: string, punctuation: string) {
  return `${greeting}, ${name}${punctuation}`;
}

const sayHello = partial(greet, "Hello");
console.log(sayHello("Alice", "!"));  // "Hello, Alice!"

// Practical: curried data transformation helpers
const map = autoCurry(<T, U>(fn: (x: T) => U, arr: T[]): U[] => arr.map(fn));
const filter = autoCurry(<T>(fn: (x: T) => boolean, arr: T[]): T[] => arr.filter(fn));
const prop = autoCurry(<K extends string>(key: K, obj: Record<K, any>) => obj[key]);

const names = map(prop("name"));
const adults = filter((u: {age: number}) => u.age >= 18);

const users = [
  { name: "Alice", age: 30 },
  { name: "Bob", age: 16 },
];
console.log(names(users));   // ["Alice", "Bob"]
console.log(adults(users));  // [{ name: "Alice", age: 30 }]
```

Currying shines in point-free composition: `pipe(filter(isActive), map(getName), take(10))`. Each curried function creates a reusable, composable building block with full type inference.'''),

    ("js_deep1_13", r'''Build a type-safe pipe and compose function in TypeScript that infers types through the entire chain of functions.''', r'''<think>
Pipe passes a value through a chain of functions: pipe(x, f, g, h) = h(g(f(x))).
Compose does it in reverse: compose(h, g, f)(x) = h(g(f(x))).
TypeScript challenge: inferring that f's output type matches g's input type.
With overloads, we can handle chains up to about 10 functions with full type safety.
Overloads give better error messages than recursive types.
I should show both pipe (value-first) and compose (functions-first).
Also worth showing: async pipe for chaining async transformations.
I will use overloads for up to 6 functions, then a variadic fallback.
Key insight: each function's return type must match the next function's parameter type.
</think>

Here are type-safe pipe and compose implementations:

```typescript
// pipe -- pass a value through a chain of transforms
function pipe<A>(value: A): A;
function pipe<A, B>(value: A, fn1: (a: A) => B): B;
function pipe<A, B, C>(value: A, fn1: (a: A) => B, fn2: (b: B) => C): C;
function pipe<A, B, C, D>(
  value: A, fn1: (a: A) => B, fn2: (b: B) => C, fn3: (c: C) => D
): D;
function pipe<A, B, C, D, E>(
  value: A, fn1: (a: A) => B, fn2: (b: B) => C,
  fn3: (c: C) => D, fn4: (d: D) => E
): E;
function pipe<A, B, C, D, E, F>(
  value: A, fn1: (a: A) => B, fn2: (b: B) => C,
  fn3: (c: C) => D, fn4: (d: D) => E, fn5: (e: E) => F
): F;
function pipe(value: unknown, ...fns: Function[]): unknown {
  return fns.reduce((acc, fn) => fn(acc), value);
}

const result = pipe(
  " Hello, World! ",
  (s: string) => s.trim(),
  (s) => s.toLowerCase(),
  (s) => s.split(" "),
  (arr) => arr.length,
);
// result is number (value: 2)

// compose -- right-to-left function composition
function compose<A, B>(fn1: (a: A) => B): (a: A) => B;
function compose<A, B, C>(fn2: (b: B) => C, fn1: (a: A) => B): (a: A) => C;
function compose<A, B, C, D>(
  fn3: (c: C) => D, fn2: (b: B) => C, fn1: (a: A) => B
): (a: A) => D;
function compose(...fns: Function[]): Function {
  return (arg: unknown) => fns.reduceRight((acc, fn) => fn(acc), arg);
}

const processName = compose(
  (s: string) => s.toUpperCase(),
  (s: string) => s.trim(),
  (s: string) => s.split(",")[0],
);
processName("doe, john");  // "DOE"

// flow -- like pipe but returns a function (left-to-right compose)
function flow<A, B>(fn1: (a: A) => B): (a: A) => B;
function flow<A, B, C>(fn1: (a: A) => B, fn2: (b: B) => C): (a: A) => C;
function flow<A, B, C, D>(
  fn1: (a: A) => B, fn2: (b: B) => C, fn3: (c: C) => D
): (a: A) => D;
function flow<A, B, C, D, E>(
  fn1: (a: A) => B, fn2: (b: B) => C,
  fn3: (c: C) => D, fn4: (d: D) => E
): (a: A) => E;
function flow(...fns: Function[]): Function {
  return (arg: unknown) => fns.reduce((acc, fn) => fn(acc), arg);
}

const processUser = flow(
  (user: { name: string; age: number }) => user.name,
  (name) => name.split(" "),
  (parts) => ({ first: parts[0], last: parts[1] ?? "" }),
);
processUser({ name: "Alice Smith", age: 30 });
// { first: "Alice", last: "Smith" }

// Async pipe -- chain async transformations
function pipeAsync<A>(value: A): Promise<A>;
function pipeAsync<A, B>(
  value: A, fn1: (a: A) => B | Promise<B>
): Promise<B>;
function pipeAsync<A, B, C>(
  value: A, fn1: (a: A) => B | Promise<B>,
  fn2: (b: B) => C | Promise<C>
): Promise<C>;
function pipeAsync<A, B, C, D>(
  value: A, fn1: (a: A) => B | Promise<B>,
  fn2: (b: B) => C | Promise<C>,
  fn3: (c: C) => D | Promise<D>
): Promise<D>;
async function pipeAsync(
  value: unknown, ...fns: Function[]
): Promise<unknown> {
  let result = value;
  for (const fn of fns) {
    result = await fn(result);
  }
  return result;
}

const userData = await pipeAsync(
  "user-123",
  (id: string) => fetch(`/api/users/${id}`),
  (resp: Response) => resp.json(),
  (data: any) => data.name.toUpperCase(),
);

// Practical: data processing pipeline
interface Transaction {
  id: string; amount: number; category: string; date: string;
}

const monthlyReport = flow(
  (txns: Transaction[]) => txns.filter(t => t.amount > 0),
  (txns) => txns.reduce((acc, t) => {
    acc[t.category] = (acc[t.category] ?? 0) + t.amount;
    return acc;
  }, {} as Record<string, number>),
  (totals) => Object.entries(totals).sort(([, a], [, b]) => b - a),
  (sorted) => sorted.map(([cat, total]) => `${cat}: $${total.toFixed(2)}`),
  (lines) => lines.join("\n"),
);
```

`pipe` is for immediate transformation of a value. `flow` is for building reusable pipelines. The overload approach gives better error messages than recursive types -- when a function has the wrong input type, TypeScript points directly at it.'''),

    ("js_deep1_14", r'''Build a type-safe EventEmitter in TypeScript that enforces event names and payload types at compile time.''', r'''<think>
A type-safe EventEmitter uses a generic type map to link event names to payload types.
The key: EventMap is a Record where keys are event names and values are argument tuples.
Methods like on/emit/off are generic over K extends keyof EventMap.
This prevents emitting wrong payloads or listening with wrong handler signatures.
Node.js EventEmitter is loosely typed -- we want something better.
I should show: typed on/off/once/emit, method chaining, async variant, and mixin version.
The implementation uses Map of string to Set of Function internally.
TypeScript ensures all event/handler pairs are correct at compile time.
</think>

Here is a fully type-safe EventEmitter:

```typescript
type EventMap = Record<string, unknown[]>;
type Handler<Args extends unknown[]> = (...args: Args) => void;

class TypedEmitter<Events extends EventMap> {
  private listeners = new Map<string, Set<Function>>();

  on<K extends keyof Events & string>(
    event: K,
    handler: Handler<Events[K]>
  ): this {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(handler);
    return this;
  }

  off<K extends keyof Events & string>(
    event: K, handler: Handler<Events[K]>
  ): this {
    this.listeners.get(event)?.delete(handler);
    return this;
  }

  once<K extends keyof Events & string>(
    event: K, handler: Handler<Events[K]>
  ): this {
    const wrapper = (...args: Events[K]) => {
      this.off(event, wrapper as Handler<Events[K]>);
      handler(...args);
    };
    return this.on(event, wrapper as Handler<Events[K]>);
  }

  emit<K extends keyof Events & string>(
    event: K, ...args: Events[K]
  ): boolean {
    const handlers = this.listeners.get(event);
    if (!handlers || handlers.size === 0) return false;
    for (const handler of handlers) handler(...args);
    return true;
  }

  removeAllListeners<K extends keyof Events & string>(event?: K): this {
    if (event) this.listeners.delete(event);
    else this.listeners.clear();
    return this;
  }
}

// Usage -- define your event map
interface AppEvents extends EventMap {
  "user:login": [user: { id: string; name: string }];
  "user:logout": [userId: string];
  "message": [from: string, text: string, timestamp: Date];
  "error": [error: Error];
}

const emitter = new TypedEmitter<AppEvents>();

emitter.on("user:login", (user) => {
  console.log(`${user.name} logged in`);
});

emitter.on("message", (from, text, timestamp) => {
  console.log(`[${timestamp.toISOString()}] ${from}: ${text}`);
});

// These would be compile errors:
// emitter.on("user:login", (x: number) => {});
// emitter.emit("user:login", "wrong");
// emitter.emit("typo", {});

emitter.emit("user:login", { id: "1", name: "Alice" });
emitter.emit("message", "Bob", "Hello!", new Date());

// Async EventEmitter variant
class AsyncEmitter<Events extends EventMap> {
  private listeners = new Map<string, Set<Function>>();

  on<K extends keyof Events & string>(
    event: K,
    handler: (...args: Events[K]) => void | Promise<void>
  ): this {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(handler);
    return this;
  }

  async emit<K extends keyof Events & string>(
    event: K, ...args: Events[K]
  ): Promise<void> {
    const handlers = this.listeners.get(event);
    if (!handlers) return;
    await Promise.all(
      Array.from(handlers).map(handler => handler(...args))
    );
  }

  async emitSerial<K extends keyof Events & string>(
    event: K, ...args: Events[K]
  ): Promise<void> {
    const handlers = this.listeners.get(event);
    if (!handlers) return;
    for (const handler of handlers) await handler(...args);
  }
}

// Mixin version -- add typed events to any class
type Constructor = new (...args: any[]) => any;

function WithEvents<Events extends EventMap>() {
  return function <TBase extends Constructor>(Base: TBase) {
    return class extends Base {
      private _emitter = new TypedEmitter<Events>();

      on<K extends keyof Events & string>(
        event: K, handler: Handler<Events[K]>
      ) { this._emitter.on(event, handler); return this; }

      emit<K extends keyof Events & string>(
        event: K, ...args: Events[K]
      ) { return this._emitter.emit(event, ...args); }
    };
  };
}

interface DatabaseEvents extends EventMap {
  "connected": [];
  "query": [sql: string, durationMs: number];
  "error": [error: Error];
}

class Database extends WithEvents<DatabaseEvents>()(class {}) {
  async query(sql: string) {
    const start = performance.now();
    // ... execute
    this.emit("query", sql, performance.now() - start);
  }
}

const db = new Database();
db.on("query", (sql, ms) => console.log(`${sql} took ${ms}ms`));
```

The power is in the `EventMap` interface: every event name maps to a tuple of argument types. TypeScript enforces correctness at every call site.'''),

    ("js_deep1_15", r'''Show me how to implement a finite state machine in TypeScript with type-safe transitions, guards, and actions.''', r'''<think>
A finite state machine (FSM) has states, events, and transitions.
TypeScript can enforce that only valid transitions are possible at compile time.
Key features: define allowed transitions per state, guards (conditions), actions (side effects).
I should use discriminated unions for states and events.
The transition function returns a new state (immutable).
Guards are predicates that can prevent a transition.
Actions run on enter/exit of states or during transitions.
I will build a reusable createMachine function with full type inference.
I will show a traffic light and auth flow example.
</think>

Here is a type-safe state machine implementation:

```typescript
// Core types
interface MachineConfig<
  TState extends string,
  TEvent extends { type: string },
  TContext
> {
  initial: TState;
  context: TContext;
  states: {
    [S in TState]: {
      on?: {
        [E in TEvent["type"]]?: {
          target: TState;
          guard?: (ctx: TContext, event: Extract<TEvent, { type: E }>) => boolean;
          action?: (ctx: TContext, event: Extract<TEvent, { type: E }>) => TContext;
        };
      };
      onEnter?: (ctx: TContext) => void;
      onExit?: (ctx: TContext) => void;
    };
  };
}

interface MachineState<TState extends string, TContext> {
  value: TState;
  context: TContext;
}

function createMachine<
  TState extends string,
  TEvent extends { type: string },
  TContext
>(config: MachineConfig<TState, TEvent, TContext>) {
  type State = MachineState<TState, TContext>;

  let current: State = {
    value: config.initial,
    context: { ...config.context },
  };

  const listeners = new Set<(state: State) => void>();

  function send(event: TEvent): State {
    const stateConfig = config.states[current.value];
    const transitions = stateConfig.on;
    if (!transitions) return current;

    const transition = (transitions as any)[event.type];
    if (!transition) return current;

    if (transition.guard && !transition.guard(current.context, event)) {
      return current;
    }

    stateConfig.onExit?.(current.context);

    const newContext = transition.action
      ? transition.action(current.context, event)
      : current.context;

    const newState: State = { value: transition.target, context: newContext };
    config.states[transition.target].onEnter?.(newContext);

    current = newState;
    listeners.forEach(fn => fn(newState));
    return newState;
  }

  function subscribe(fn: (state: State) => void) {
    listeners.add(fn);
    return () => listeners.delete(fn);
  }

  return { send, subscribe, getState: () => current };
}

// Example: traffic light
type TrafficState = "red" | "yellow" | "green";
type TrafficEvent = { type: "TIMER" } | { type: "EMERGENCY" };

const trafficLight = createMachine<TrafficState, TrafficEvent, {}>({
  initial: "red",
  context: {},
  states: {
    red: {
      on: { TIMER: { target: "green" } },
      onEnter: () => console.log("Stop!"),
    },
    green: {
      on: {
        TIMER: { target: "yellow" },
        EMERGENCY: { target: "red" },
      },
      onEnter: () => console.log("Go!"),
    },
    yellow: {
      on: {
        TIMER: { target: "red" },
        EMERGENCY: { target: "red" },
      },
      onEnter: () => console.log("Slow down!"),
    },
  },
});

trafficLight.send({ type: "TIMER" });  // red -> green
trafficLight.send({ type: "TIMER" });  // green -> yellow

// Example: auth flow with context and guards
type AuthState = "loggedOut" | "loggingIn" | "loggedIn" | "error";
type AuthEvent =
  | { type: "LOGIN"; username: string; password: string }
  | { type: "LOGIN_SUCCESS"; token: string }
  | { type: "LOGIN_FAILURE"; error: string }
  | { type: "LOGOUT" }
  | { type: "RETRY" };

interface AuthContext {
  token: string | null;
  error: string | null;
  attempts: number;
}

const authMachine = createMachine<AuthState, AuthEvent, AuthContext>({
  initial: "loggedOut",
  context: { token: null, error: null, attempts: 0 },
  states: {
    loggedOut: {
      on: {
        LOGIN: {
          target: "loggingIn",
          action: (ctx) => ({ ...ctx, attempts: ctx.attempts + 1 }),
        },
      },
    },
    loggingIn: {
      on: {
        LOGIN_SUCCESS: {
          target: "loggedIn",
          action: (ctx, event) => ({
            ...ctx, token: event.token, error: null, attempts: 0,
          }),
        },
        LOGIN_FAILURE: {
          target: "error",
          action: (ctx, event) => ({ ...ctx, error: event.error }),
        },
      },
      onEnter: (ctx) => console.log(`Login attempt #${ctx.attempts}`),
    },
    loggedIn: {
      on: {
        LOGOUT: {
          target: "loggedOut",
          action: (ctx) => ({ ...ctx, token: null }),
        },
      },
    },
    error: {
      on: {
        RETRY: {
          target: "loggingIn",
          guard: (ctx) => ctx.attempts < 3,
          action: (ctx) => ({ ...ctx, attempts: ctx.attempts + 1 }),
        },
        LOGOUT: {
          target: "loggedOut",
          action: (ctx) => ({ ...ctx, error: null, attempts: 0 }),
        },
      },
    },
  },
});

authMachine.subscribe((state) => {
  console.log(`Auth: ${state.value}`, state.context);
});
```

State machines eliminate impossible states by construction. Instead of checking `if (isLoading && hasError)` -- which should never happen -- you make it unrepresentable in the type system.'''),

    # -- 16-20: Node.js patterns -----------------------------------------------
    ("js_deep1_16", r'''Show me how to use Node.js streams properly: readable, writable, transform, and pipeline. Include backpressure handling and error propagation.''', r'''<think>
Node.js streams are the foundation for efficient I/O processing.
Four types: Readable, Writable, Transform, Duplex.
Backpressure: when writable.write() returns false, stop reading until drain event.
pipeline() handles backpressure and error cleanup automatically.
Common mistake: piping without error handling -- errors do not propagate with .pipe().
pipeline() fixes this: errors in any stream destroy the whole chain.
Transform streams are the most useful: read, process, write in a streaming fashion.
Modern Node has stream/promises with async iteration support.
I will show CSV parsing as a practical transform stream example.
</think>

Here is a comprehensive guide to Node.js streams:

```typescript
import { Readable, Writable, Transform } from "node:stream";
import { pipeline as pipelineAsync } from "node:stream/promises";
import { createReadStream, createWriteStream } from "node:fs";
import { createGzip } from "node:zlib";

// Custom Readable -- generates data on demand
class NumberStream extends Readable {
  private current = 0;

  constructor(private max: number) {
    super({ objectMode: true });
  }

  _read() {
    if (this.current >= this.max) {
      this.push(null);
      return;
    }
    while (this.current < this.max) {
      const canContinue = this.push({ n: this.current++ });
      if (!canContinue) break;  // Respect backpressure
    }
  }
}

// Custom Transform -- process each chunk
class CSVParser extends Transform {
  private buffer = "";
  private headers: string[] | null = null;

  constructor() {
    super({ objectMode: true });
  }

  _transform(chunk: Buffer, encoding: string, callback: Function) {
    this.buffer += chunk.toString();
    const lines = this.buffer.split("\n");
    this.buffer = lines.pop()!;

    for (const line of lines) {
      if (!line.trim()) continue;
      const values = line.split(",").map(v => v.trim());

      if (!this.headers) { this.headers = values; continue; }

      const record: Record<string, string> = {};
      this.headers.forEach((h, i) => { record[h] = values[i] ?? ""; });
      this.push(record);
    }
    callback();
  }

  _flush(callback: Function) {
    if (this.buffer.trim() && this.headers) {
      const values = this.buffer.split(",").map(v => v.trim());
      const record: Record<string, string> = {};
      this.headers.forEach((h, i) => { record[h] = values[i] ?? ""; });
      this.push(record);
    }
    callback();
  }
}

// Custom Writable -- consume data in batches
class BatchWriter extends Writable {
  private batch: any[] = [];

  constructor(
    private batchSize: number,
    private onBatch: (items: any[]) => Promise<void>
  ) {
    super({ objectMode: true, highWaterMark: batchSize * 2 });
  }

  async _write(chunk: any, encoding: string, callback: Function) {
    this.batch.push(chunk);
    if (this.batch.length >= this.batchSize) {
      try {
        await this.onBatch(this.batch);
        this.batch = [];
        callback();
      } catch (err) { callback(err); }
    } else { callback(); }
  }

  async _final(callback: Function) {
    if (this.batch.length > 0) {
      try { await this.onBatch(this.batch); callback(); }
      catch (err) { callback(err); }
    } else { callback(); }
  }
}

// pipeline() -- the RIGHT way to connect streams
// BAD: .pipe() does not propagate errors
// GOOD: pipeline handles errors, backpressure, and cleanup
await pipelineAsync(
  createReadStream("data.csv"),
  new CSVParser(),
  new Transform({
    objectMode: true,
    transform(record, _, cb) {
      if (parseInt(record.age) > 18) {
        this.push(JSON.stringify(record) + "\n");
      }
      cb();
    },
  }),
  createWriteStream("adults.jsonl")
);

// Compress a file
await pipelineAsync(
  createReadStream("large-file.log"),
  createGzip(),
  createWriteStream("large-file.log.gz")
);

// Async iteration over streams
async function processCSV(filePath: string) {
  const readable = createReadStream(filePath).pipe(new CSVParser());
  let count = 0;
  for await (const record of readable) {
    await saveToDatabase(record);
    count++;
    if (count % 1000 === 0) console.log(`Processed ${count} records`);
  }
}

// Readable.from -- create streams from iterables
async function* generateData() {
  for (let i = 0; i < 1_000_000; i++) {
    yield JSON.stringify({ id: i, ts: Date.now() }) + "\n";
  }
}

await pipelineAsync(
  Readable.from(generateData()),
  createGzip(),
  createWriteStream("data.jsonl.gz")
);
```

The golden rule: **always use `pipeline()` instead of `.pipe()`**. `.pipe()` does not propagate errors, does not handle cleanup, and can leave streams in a broken state. `pipeline()` from `stream/promises` handles all of this correctly.'''),

    ("js_deep1_17", r'''How do I use Worker Threads in Node.js for CPU-intensive tasks? Show me the communication patterns, shared memory, and a practical thread pool implementation.''', r'''<think>
Worker threads run JavaScript in separate V8 isolates within the same process.
They share the process memory space but have isolated JS heaps.
Communication: postMessage/on message for structured clone, SharedArrayBuffer for shared memory.
Use cases: CPU-intensive computation without blocking the event loop.
Worker threads are NOT for I/O -- the event loop handles I/O efficiently already.
I should show: basic worker, SharedArrayBuffer, and a thread pool.
The thread pool pattern reuses workers instead of creating/destroying per task.
Key: Atomics API for synchronization when using shared memory.
I will build a practical thread pool that queues tasks and distributes to workers.
</think>

Here is a complete guide to Node.js Worker Threads:

```typescript
// worker-task.ts -- the worker script
import { parentPort } from "node:worker_threads";

parentPort!.on("message", (task: { type: string; data: any }) => {
  switch (task.type) {
    case "hash": {
      const { createHash } = require("node:crypto");
      const hash = createHash("sha256").update(task.data).digest("hex");
      parentPort!.postMessage({ type: "result", hash });
      break;
    }
    case "fibonacci": {
      function fib(n: number): number {
        if (n <= 1) return n;
        return fib(n - 1) + fib(n - 2);
      }
      parentPort!.postMessage({ type: "result", value: fib(task.data) });
      break;
    }
  }
});

// main.ts -- using a single worker
import { Worker } from "node:worker_threads";

function runInWorker<T>(scriptPath: string, data: any): Promise<T> {
  return new Promise((resolve, reject) => {
    const worker = new Worker(scriptPath, { workerData: data });
    worker.on("message", resolve);
    worker.on("error", reject);
    worker.on("exit", (code) => {
      if (code !== 0) reject(new Error(`Worker exited with code ${code}`));
    });
  });
}

// SharedArrayBuffer -- zero-copy shared memory
function parallelSum(data: Float64Array, numWorkers: number): Promise<number> {
  const shared = new SharedArrayBuffer(Float64Array.BYTES_PER_ELEMENT * data.length);
  const sharedArray = new Float64Array(shared);
  sharedArray.set(data);

  const resultBuf = new SharedArrayBuffer(Float64Array.BYTES_PER_ELEMENT * numWorkers);
  const results = new Float64Array(resultBuf);

  const chunkSize = Math.ceil(data.length / numWorkers);

  const workers = Array.from({ length: numWorkers }, (_, i) => {
    return new Promise<void>((resolve, reject) => {
      const worker = new Worker("./sum-worker.ts", {
        workerData: {
          shared, resultBuf,
          start: i * chunkSize,
          end: Math.min((i + 1) * chunkSize, data.length),
          workerIndex: i,
        },
      });
      worker.on("message", () => resolve());
      worker.on("error", reject);
    });
  });

  return Promise.all(workers).then(() => {
    return results.reduce((a, b) => a + b, 0);
  });
}

// Thread Pool -- reuse workers across tasks
interface PoolTask<T> {
  data: any;
  resolve: (value: T) => void;
  reject: (err: Error) => void;
}

class WorkerPool {
  private workers: Worker[] = [];
  private idle: Worker[] = [];
  private queue: PoolTask<any>[] = [];

  constructor(private scriptPath: string, private poolSize: number = 4) {
    for (let i = 0; i < poolSize; i++) {
      const worker = new Worker(scriptPath);
      this.workers.push(worker);
      this.idle.push(worker);
    }
  }

  execute<T>(data: any): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      const task: PoolTask<T> = { data, resolve, reject };
      if (this.idle.length > 0) {
        this.runTask(this.idle.pop()!, task);
      } else {
        this.queue.push(task);
      }
    });
  }

  private runTask<T>(worker: Worker, task: PoolTask<T>) {
    const onMessage = (result: T) => {
      cleanup();
      task.resolve(result);
      this.onWorkerFree(worker);
    };
    const onError = (err: Error) => {
      cleanup();
      task.reject(err);
      this.onWorkerFree(worker);
    };
    const cleanup = () => {
      worker.removeListener("message", onMessage);
      worker.removeListener("error", onError);
    };

    worker.on("message", onMessage);
    worker.on("error", onError);
    worker.postMessage(task.data);
  }

  private onWorkerFree(worker: Worker) {
    if (this.queue.length > 0) {
      this.runTask(worker, this.queue.shift()!);
    } else {
      this.idle.push(worker);
    }
  }

  async destroy(): Promise<void> {
    await Promise.all(this.workers.map(w => w.terminate()));
    this.workers = [];
    this.idle = [];
  }
}

// Usage: hash 10,000 passwords using the thread pool
const pool = new WorkerPool("./worker-task.ts", 4);

async function hashPasswords(passwords: string[]) {
  const results = await Promise.all(
    passwords.map(pw =>
      pool.execute<{ hash: string }>({ type: "hash", data: pw })
    )
  );
  return results.map(r => r.hash);
}

process.on("beforeExit", () => pool.destroy());
```

Key rules: use worker threads for **CPU-bound** work only (crypto, parsing, compression). For I/O-bound work, the event loop is already non-blocking and threads add overhead. The thread pool amortizes the ~30ms cost of creating a worker across many tasks.'''),

    ("js_deep1_18", r'''How do I use the Node.js cluster module to scale a web server across multiple CPU cores? Show me graceful shutdown, zero-downtime restarts, and sticky sessions.''', r'''<think>
The cluster module forks the main process into worker processes (one per CPU core).
Each worker gets its own event loop, V8 instance, and memory.
The primary distributes incoming connections to workers (round-robin by default on Linux).
Key patterns: graceful shutdown, zero-downtime restart, sticky sessions for WebSocket.
Graceful shutdown: stop accepting new connections, finish existing requests, then exit.
Zero-downtime restart: restart workers one at a time, waiting for each to be ready.
Sticky sessions: route same client to same worker (needed for WebSocket/session state).
I will include signal handling for graceful shutdown.
</think>

Here is a production-ready Node.js cluster setup:

```typescript
import cluster from "node:cluster";
import http from "node:http";
import os from "node:os";
import net from "node:net";
import { createHash } from "node:crypto";

const NUM_WORKERS = os.cpus().length;
const PORT = 3000;

if (cluster.isPrimary) {
  console.log(`Primary ${process.pid} starting ${NUM_WORKERS} workers`);

  const workers = new Map<number, ReturnType<typeof cluster.fork>>();
  let isShuttingDown = false;

  for (let i = 0; i < NUM_WORKERS; i++) {
    const worker = cluster.fork();
    workers.set(worker.id, worker);
  }

  cluster.on("exit", (worker, code, signal) => {
    workers.delete(worker.id);
    console.log(`Worker ${worker.process.pid} died (${signal || code})`);
    if (!isShuttingDown) {
      const newWorker = cluster.fork();
      workers.set(newWorker.id, newWorker);
    }
  });

  // Graceful Shutdown
  async function gracefulShutdown(signal: string) {
    if (isShuttingDown) return;
    isShuttingDown = true;
    console.log(`${signal} received. Shutting down gracefully...`);

    const timeout = setTimeout(() => {
      console.error("Shutdown timeout -- forcing exit");
      process.exit(1);
    }, 30_000);

    const shutdownPromises = Array.from(workers.values()).map(worker => {
      return new Promise<void>((resolve) => {
        worker.send("shutdown");
        worker.on("exit", () => resolve());
      });
    });

    await Promise.all(shutdownPromises);
    clearTimeout(timeout);
    process.exit(0);
  }

  process.on("SIGTERM", () => gracefulShutdown("SIGTERM"));
  process.on("SIGINT", () => gracefulShutdown("SIGINT"));

  // Zero-Downtime Restart
  process.on("SIGUSR2", async () => {
    console.log("SIGUSR2: Zero-downtime restart");
    const workerIds = Array.from(workers.keys());

    for (const id of workerIds) {
      const oldWorker = workers.get(id)!;
      const newWorker = cluster.fork();

      await new Promise<void>((resolve) => {
        newWorker.on("listening", () => {
          workers.set(newWorker.id, newWorker);
          oldWorker.send("shutdown");
          oldWorker.on("exit", () => {
            workers.delete(id);
            resolve();
          });
        });
      });
      console.log(`Replaced worker ${id} with ${newWorker.id}`);
    }
  });

} else {
  // WORKER PROCESS
  let isAccepting = true;

  const server = http.createServer((req, res) => {
    if (!isAccepting) {
      res.writeHead(503);
      res.end("Server shutting down");
      return;
    }

    res.writeHead(200, { "Content-Type": "application/json" });
    res.end(JSON.stringify({
      worker: process.pid,
      uptime: process.uptime(),
    }));
  });

  server.listen(PORT);

  process.on("message", (msg) => {
    if (msg === "shutdown") {
      isAccepting = false;
      server.close(() => process.exit(0));
      setTimeout(() => process.exit(1), 10_000);
    }
  });
}

// Sticky Sessions -- route same client to same worker
// For WebSocket or session-based apps
if (cluster.isPrimary) {
  const stickyWorkers: ReturnType<typeof cluster.fork>[] = [];
  for (let i = 0; i < NUM_WORKERS; i++) {
    stickyWorkers.push(cluster.fork());
  }

  const balancer = net.createServer({ pauseOnConnect: true }, (conn) => {
    const ip = conn.remoteAddress || "";
    const hash = createHash("md5").update(ip).digest();
    const idx = hash.readUInt32BE(0) % stickyWorkers.length;
    stickyWorkers[idx].send("sticky:connection", conn);
  });
  balancer.listen(PORT);
}
```

Key points: each worker is a full process with its own memory. For shared state, use Redis. Zero-downtime restarts work by starting new workers before killing old ones. For production, consider PM2 which adds log management, monitoring, and automatic clustering.'''),

    ("js_deep1_19", r'''Show me advanced EventEmitter patterns in Node.js: memory leak detection, async event handling, event delegation, and building a pub/sub system.''', r'''<think>
Node.js EventEmitter has several advanced features beyond basic on/emit.
Memory leak detection: maxListeners warning (default 10).
captureRejections catches unhandled promise rejections in event handlers.
EventEmitter.on() returns an AsyncIterator (Node 13.6+).
Building a pub/sub system: channels, wildcards, persistent messages.
I should show: leak detection, async error handling, streaming events, and pub/sub.
The once() function from events module returns a Promise for single-event awaiting.
AbortSignal integration with events for cleanup.
</think>

Here are advanced Node.js EventEmitter patterns:

```typescript
import { EventEmitter, once, on } from "node:events";
import { setTimeout as sleep } from "node:timers/promises";

// Memory leak detection and prevention
const emitter = new EventEmitter();

emitter.on("newListener", (event) => {
  const count = emitter.listenerCount(event);
  if (count > 8) {
    console.warn(
      `Warning: ${count + 1} listeners on "${event}" -- possible leak`
    );
  }
});

// Common leak: adding listeners without removing
function leakyPattern(emitter: EventEmitter) {
  emitter.on("data", (d) => process(d));  // Adds every call!
}

function fixedPattern(emitter: EventEmitter) {
  const handler = (d: any) => process(d);
  emitter.on("data", handler);
  return () => emitter.off("data", handler);
}

// Async event handling with captureRejections
class AsyncService extends EventEmitter {
  constructor() {
    super({ captureRejections: true });
  }

  [Symbol.for("nodejs.rejection")](err: Error, event: string) {
    console.error(`Async error in "${event}" handler:`, err);
    this.emit("error", err);
  }
}

// EventEmitter.on() as AsyncIterator -- stream events
async function streamEvents() {
  const emitter = new EventEmitter();

  const producer = (async () => {
    for (let i = 0; i < 100; i++) {
      emitter.emit("data", { id: i, value: Math.random() });
      await sleep(100);
    }
  })();

  const ac = new AbortController();
  for await (const [event] of on(emitter, "data", { signal: ac.signal })) {
    console.log("Received:", event);
    if (event.id >= 50) { ac.abort(); break; }
  }
}

// once() -- wait for a single event (Promise-based)
async function waitForReady(service: EventEmitter) {
  const [data] = await once(service, "ready");
  console.log("Service ready with:", data);
}

async function waitForReadyWithTimeout(service: EventEmitter) {
  try {
    const [data] = await once(service, "ready", {
      signal: AbortSignal.timeout(5000),
    });
    return data;
  } catch (err) {
    if ((err as Error).name === "AbortError") {
      throw new Error("Service failed to become ready within 5 seconds");
    }
    throw err;
  }
}

// Pub/Sub system with channels and wildcards
class PubSub {
  private channels = new Map<string, Set<(data: any) => void>>();
  private messageHistory = new Map<string, any[]>();

  subscribe(pattern: string, handler: (data: any, channel: string) => void) {
    if (!this.channels.has(pattern)) {
      this.channels.set(pattern, new Set());
    }
    this.channels.get(pattern)!.add(handler);

    return () => {
      this.channels.get(pattern)?.delete(handler);
      if (this.channels.get(pattern)?.size === 0) {
        this.channels.delete(pattern);
      }
    };
  }

  publish(channel: string, data: any) {
    if (!this.messageHistory.has(channel)) {
      this.messageHistory.set(channel, []);
    }
    this.messageHistory.get(channel)!.push(data);

    for (const [pattern, handlers] of this.channels) {
      if (this.matchPattern(pattern, channel)) {
        for (const handler of handlers) {
          try { handler(data, channel); }
          catch (err) { console.error(`Handler error on "${channel}":`, err); }
        }
      }
    }
  }

  replay(channel: string, handler: (data: any) => void) {
    const history = this.messageHistory.get(channel) ?? [];
    history.forEach(data => handler(data));
  }

  private matchPattern(pattern: string, channel: string): boolean {
    if (pattern === channel) return true;
    if (!pattern.includes("*")) return false;
    const regex = new RegExp(
      "^" + pattern.replace(/\./g, "\\.").replace(/\*/g, "[^.]+") + "$"
    );
    return regex.test(channel);
  }
}

const pubsub = new PubSub();
const unsub = pubsub.subscribe("user.*", (data, channel) => {
  console.log(`[${channel}]`, data);
});

pubsub.publish("user.created", { id: 1, name: "Alice" });
pubsub.publish("user.updated", { id: 1, name: "Alicia" });
pubsub.publish("order.created", { id: 100 });  // Not matched

unsub();
```

Key takeaways: use `once()` for single-event awaiting, `on()` for async iteration, and `captureRejections` to catch async errors. Always track and clean up listeners to prevent memory leaks.'''),

    ("js_deep1_20", r'''How do I use child_process in Node.js to safely execute external commands, handle streaming output, and manage process lifecycles?''', r'''<think>
child_process provides spawn, exec, execFile, and fork for running external processes.
spawn is the most flexible: streams stdin/stdout/stderr.
exec buffers all output -- easier but limited by buffer size.
execFile is safer than exec because it does not spawn a shell (no shell injection).
fork is specifically for Node.js child processes with IPC.
Security: exec with user input is a shell injection vector.
I should show: safe execution, streaming output, process management, and signal handling.
Key patterns: timeout, kill on parent exit, stream processing, error handling.
I will build a safe command runner with streaming output and timeout.
</think>

Here is how to safely and effectively use child_process:

```typescript
import { spawn, execFile, fork } from "node:child_process";
import { promisify } from "node:util";

const execFilePromise = promisify(execFile);

// SECURITY: exec vs execFile vs spawn
// DANGEROUS: exec() runs in a shell -- shell injection possible
// exec(`grep ${userInput} /var/log/app.log`);

// SAFE: execFile() does NOT use a shell
async function safeGrep(pattern: string, file: string): Promise<string> {
  const { stdout } = await execFilePromise("grep", [pattern, file]);
  return stdout;
}

// SAFE: spawn() with args array -- no shell interpolation
function safeSpawn(cmd: string, args: string[]) {
  return spawn(cmd, args, { stdio: "pipe" });
}

// Streaming output with spawn
function runWithStreaming(
  command: string,
  args: string[]
): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: "pipe" });
    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      stdout += text;
      process.stdout.write(text);
    });
    child.stderr.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      stderr += text;
      process.stderr.write(text);
    });

    child.on("error", reject);
    child.on("close", (code) => {
      resolve({ code: code ?? 1, stdout, stderr });
    });
  });
}

// Command runner with timeout and abort
interface RunOptions {
  command: string;
  args: string[];
  cwd?: string;
  env?: Record<string, string>;
  timeoutMs?: number;
  signal?: AbortSignal;
  onStdout?: (line: string) => void;
}

async function run(options: RunOptions): Promise<{
  code: number; stdout: string; stderr: string;
}> {
  const { command, args, cwd, env, timeoutMs, signal, onStdout } = options;

  return new Promise((resolve, reject) => {
    const child = spawn(command, args, {
      cwd,
      env: env ? { ...process.env, ...env } : undefined,
      stdio: "pipe",
      signal,
    });

    let stdout = "";
    let stderr = "";
    let killed = false;

    let timer: NodeJS.Timeout | undefined;
    if (timeoutMs) {
      timer = setTimeout(() => {
        killed = true;
        child.kill("SIGTERM");
        setTimeout(() => child.kill("SIGKILL"), 5000);
      }, timeoutMs);
    }

    let lineBuffer = "";
    child.stdout.on("data", (chunk: Buffer) => {
      const text = chunk.toString();
      stdout += text;
      if (onStdout) {
        lineBuffer += text;
        const lines = lineBuffer.split("\n");
        lineBuffer = lines.pop()!;
        lines.forEach(line => onStdout(line));
      }
    });

    child.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });

    child.on("error", (err) => { clearTimeout(timer); reject(err); });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (onStdout && lineBuffer) onStdout(lineBuffer);
      if (killed) reject(new Error(`Command timed out after ${timeoutMs}ms`));
      else resolve({ code: code ?? 1, stdout, stderr });
    });
  });
}

const output = await run({
  command: "npm",
  args: ["test"],
  cwd: "/project",
  timeoutMs: 60_000,
  onStdout: (line) => console.log(`[test] ${line}`),
});

// fork() -- Node.js child with IPC
function forkWorker(scriptPath: string, data: any): Promise<any> {
  return new Promise((resolve, reject) => {
    const child = fork(scriptPath, [], { serialization: "advanced" });
    child.send(data);
    child.on("message", (result) => { child.kill(); resolve(result); });
    child.on("error", reject);
    child.on("exit", (code) => {
      if (code !== 0) reject(new Error(`Worker exited with code ${code}`));
    });
  });
}

// Process lifecycle management
class ProcessManager {
  private processes = new Map<string, ReturnType<typeof spawn>>();

  start(name: string, command: string, args: string[]) {
    if (this.processes.has(name)) throw new Error(`"${name}" already running`);

    const child = spawn(command, args, {
      stdio: ["ignore", "pipe", "pipe"],
    });

    child.stdout.on("data", (d) =>
      console.log(`[${name}] ${d.toString().trim()}`)
    );
    child.stderr.on("data", (d) =>
      console.error(`[${name}] ${d.toString().trim()}`)
    );
    child.on("exit", (code) => {
      console.log(`[${name}] exited with code ${code}`);
      this.processes.delete(name);
    });

    this.processes.set(name, child);
  }

  async stop(name: string): Promise<void> {
    const child = this.processes.get(name);
    if (!child) return;
    return new Promise((resolve) => {
      child.on("exit", () => { this.processes.delete(name); resolve(); });
      child.kill("SIGTERM");
      setTimeout(() => child.kill("SIGKILL"), 5000);
    });
  }

  async stopAll(): Promise<void> {
    await Promise.all(
      Array.from(this.processes.keys()).map(name => this.stop(name))
    );
  }
}

const pm = new ProcessManager();
process.on("SIGINT", () => pm.stopAll().then(() => process.exit(0)));
```

The critical rule: **never pass user input to `exec()`**. Always use `execFile()` or `spawn()` with an arguments array to prevent shell injection.'''),

    # -- 21-25: Error handling and testing --------------------------------------
    ("js_deep1_21", r'''How do I build a proper custom error hierarchy in JavaScript/TypeScript with error codes, serialization, and error cause chaining?''', r'''<think>
Custom errors in JS extend the Error class.
Key issues: stack trace capture, instanceof checks, JSON serialization.
Error cause chaining (ES2022): new Error("msg", { cause: originalError }).
Error codes are essential for programmatic error handling.
In TypeScript, we can use discriminated unions for error types.
I should show: base error class, domain-specific errors, serialization, and cause chains.
The name property must be set for proper stack traces.
captureStackTrace (V8-specific) gives cleaner traces.
I will build a practical error hierarchy for an API application.
</think>

Here is a production-grade error system:

```typescript
interface ErrorOptions {
  cause?: Error;
  statusCode?: number;
  code?: string;
  details?: Record<string, unknown>;
}

class AppError extends Error {
  readonly code: string;
  readonly statusCode: number;
  readonly details: Record<string, unknown>;
  readonly timestamp: string;

  constructor(message: string, options: ErrorOptions = {}) {
    super(message, { cause: options.cause });
    Object.setPrototypeOf(this, new.target.prototype);

    this.name = this.constructor.name;
    this.code = options.code ?? "INTERNAL_ERROR";
    this.statusCode = options.statusCode ?? 500;
    this.details = options.details ?? {};
    this.timestamp = new Date().toISOString();

    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, this.constructor);
    }
  }

  toJSON(): Record<string, unknown> {
    return {
      name: this.name, message: this.message,
      code: this.code, statusCode: this.statusCode,
      details: this.details, timestamp: this.timestamp,
      cause: this.cause instanceof AppError
        ? this.cause.toJSON()
        : this.cause instanceof Error
          ? { name: this.cause.name, message: this.cause.message }
          : undefined,
    };
  }
}

class NotFoundError extends AppError {
  constructor(resource: string, id: string | number, cause?: Error) {
    super(`${resource} with id "${id}" not found`, {
      code: "NOT_FOUND", statusCode: 404,
      details: { resource, id }, cause,
    });
  }
}

class ValidationError extends AppError {
  constructor(message: string, fields: Record<string, string[]>, cause?: Error) {
    super(message, {
      code: "VALIDATION_ERROR", statusCode: 422,
      details: { fields }, cause,
    });
  }
}

class AuthenticationError extends AppError {
  constructor(message = "Authentication required", cause?: Error) {
    super(message, { code: "UNAUTHENTICATED", statusCode: 401, cause });
  }
}

class RateLimitError extends AppError {
  constructor(retryAfterMs: number) {
    super("Rate limit exceeded", {
      code: "RATE_LIMITED", statusCode: 429,
      details: { retryAfterMs },
    });
  }
}

class ExternalServiceError extends AppError {
  constructor(service: string, cause: Error) {
    super(`External service "${service}" failed`, {
      code: "EXTERNAL_SERVICE_ERROR", statusCode: 502,
      details: { service }, cause,
    });
  }
}

// Error cause chaining
async function getUser(id: string) {
  try {
    const resp = await fetch(`/api/users/${id}`);
    if (resp.status === 404) throw new NotFoundError("User", id);
    if (!resp.ok) throw new AppError(`API responded with ${resp.status}`, {
      code: "API_ERROR", statusCode: resp.status,
    });
    return resp.json();
  } catch (err) {
    if (err instanceof AppError) throw err;
    throw new ExternalServiceError("user-api", err as Error);
  }
}

// Express error handler
function errorHandler(err: Error, req: any, res: any, next: any) {
  if (err instanceof AppError) {
    res.status(err.statusCode).json({
      error: { code: err.code, message: err.message, details: err.details },
    });
    if (err.statusCode >= 500) {
      console.error("Server error:", JSON.stringify(err.toJSON(), null, 2));
    }
  } else {
    console.error("Unhandled error:", err);
    res.status(500).json({
      error: { code: "INTERNAL_ERROR", message: "An unexpected error occurred" },
    });
  }
}

// Type guards
function isAppError(err: unknown): err is AppError {
  return err instanceof AppError;
}

function hasErrorCode(err: unknown, code: string): boolean {
  return isAppError(err) && err.code === code;
}

try {
  await getUser("123");
} catch (err) {
  if (hasErrorCode(err, "NOT_FOUND")) {
    console.log("User does not exist");
  } else if (hasErrorCode(err, "RATE_LIMITED")) {
    const retryMs = (err as RateLimitError).details.retryAfterMs;
    console.log(`Retry after ${retryMs}ms`);
  } else {
    throw err;
  }
}
```

The key insight: error codes (`NOT_FOUND`, `VALIDATION_ERROR`) are for **programmatic** handling, while messages are for **humans**. Never match on `error.message` strings. The `cause` chain preserves the debugging trail without exposing internals to API consumers.'''),

    ("js_deep1_22", r'''Build a robust retry pattern in JavaScript/TypeScript with exponential backoff, jitter, circuit breaker, and configurable retry conditions.''', r'''<think>
Retry with exponential backoff is essential for resilient network calls.
Key components: max retries, base delay, exponential growth, random jitter.
Jitter prevents thundering herd where all clients retry simultaneously.
Circuit breaker: stop retrying when a service is clearly down (fail fast).
Configurable retry conditions: only retry on specific errors/status codes.
The circuit breaker has three states: CLOSED, OPEN, HALF_OPEN.
Exponential backoff: delay = baseDelay * 2^attempt + random jitter.
I will build composable pieces that can be combined for production use.
</think>

Here is a complete retry and resilience toolkit:

```typescript
interface RetryOptions {
  maxRetries: number;
  baseDelayMs: number;
  maxDelayMs: number;
  jitter: boolean;
  shouldRetry?: (error: unknown, attempt: number) => boolean;
  onRetry?: (error: unknown, attempt: number, delayMs: number) => void;
}

const DEFAULT_RETRY: RetryOptions = {
  maxRetries: 3, baseDelayMs: 1000, maxDelayMs: 30_000, jitter: true,
};

async function retry<T>(
  fn: (attempt: number) => Promise<T>,
  options: Partial<RetryOptions> = {}
): Promise<T> {
  const opts = { ...DEFAULT_RETRY, ...options };
  let lastError: unknown;

  for (let attempt = 0; attempt <= opts.maxRetries; attempt++) {
    try {
      return await fn(attempt);
    } catch (err) {
      lastError = err;
      if (attempt === opts.maxRetries) break;
      if (opts.shouldRetry && !opts.shouldRetry(err, attempt)) throw err;

      let delay = Math.min(
        opts.baseDelayMs * Math.pow(2, attempt),
        opts.maxDelayMs
      );
      if (opts.jitter) delay = delay * (0.5 + Math.random() * 0.5);

      opts.onRetry?.(err, attempt, delay);
      await new Promise(r => setTimeout(r, delay));
    }
  }
  throw lastError;
}

// Circuit Breaker
type CircuitState = "CLOSED" | "OPEN" | "HALF_OPEN";

class CircuitBreaker {
  private state: CircuitState = "CLOSED";
  private failures = 0;
  private lastFailureTime = 0;
  private halfOpenAttempts = 0;

  constructor(
    private readonly threshold: number = 5,
    private readonly resetTimeMs: number = 30_000,
    private readonly halfOpenMax: number = 2
  ) {}

  async execute<T>(fn: () => Promise<T>): Promise<T> {
    if (this.state === "OPEN") {
      if (Date.now() - this.lastFailureTime >= this.resetTimeMs) {
        this.state = "HALF_OPEN";
        this.halfOpenAttempts = 0;
      } else {
        throw new Error("Circuit breaker is OPEN -- failing fast");
      }
    }

    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (err) {
      this.onFailure();
      throw err;
    }
  }

  private onSuccess() {
    if (this.state === "HALF_OPEN") {
      this.halfOpenAttempts++;
      if (this.halfOpenAttempts >= this.halfOpenMax) {
        this.state = "CLOSED";
        this.failures = 0;
      }
    } else {
      this.failures = 0;
    }
  }

  private onFailure() {
    this.failures++;
    this.lastFailureTime = Date.now();
    if (this.state === "HALF_OPEN") {
      this.state = "OPEN";
    } else if (this.failures >= this.threshold) {
      this.state = "OPEN";
      console.warn(`Circuit breaker OPENED after ${this.failures} failures`);
    }
  }

  getState(): CircuitState { return this.state; }
}

// Combining retry + circuit breaker
class ResilientClient {
  private breaker = new CircuitBreaker(5, 30_000);

  async fetch<T>(url: string): Promise<T> {
    return this.breaker.execute(() =>
      retry(
        async () => {
          const resp = await fetch(url);
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          return resp.json() as Promise<T>;
        },
        {
          maxRetries: 3,
          baseDelayMs: 500,
          shouldRetry: (err) => {
            const msg = err instanceof Error ? err.message : "";
            const status = parseInt(msg.slice(5));
            return isNaN(status) || status >= 500 || status === 429;
          },
        }
      )
    );
  }
}

// Retry with abort support
async function retryWithAbort<T>(
  fn: (signal: AbortSignal) => Promise<T>,
  options: Partial<RetryOptions> & { signal?: AbortSignal } = {}
): Promise<T> {
  const { signal, ...retryOpts } = options;

  return retry(
    async (attempt) => {
      if (signal?.aborted) throw new DOMException("Aborted", "AbortError");

      const ac = new AbortController();
      const onAbort = () => ac.abort();
      signal?.addEventListener("abort", onAbort, { once: true });

      try {
        return await fn(ac.signal);
      } finally {
        signal?.removeEventListener("abort", onAbort);
      }
    },
    {
      ...retryOpts,
      shouldRetry: (err, attempt) => {
        if (err instanceof DOMException && err.name === "AbortError") return false;
        return retryOpts.shouldRetry?.(err, attempt) ?? true;
      },
    }
  );
}

const controller = new AbortController();
const data = await retryWithAbort(
  (signal) => fetch("/api/data", { signal }).then(r => r.json()),
  { maxRetries: 3, signal: controller.signal }
);
```

The three layers of resilience: **retry** handles transient failures, **circuit breaker** prevents cascading failures when a service is down, and **abort** lets callers cancel. The `shouldRetry` predicate is critical -- never retry 400 or 401, only retry 5xx and 429.'''),

    ("js_deep1_23", r'''Show me how to implement dependency injection in TypeScript without a framework, using constructor injection and a simple container.''', r'''<think>
Dependency injection (DI) decouples object creation from usage.
In TypeScript without a framework: use interfaces + constructor injection.
A simple container maps tokens to factory functions.
Key benefits: testability (mock dependencies), flexibility (swap implementations).
The container should support: singleton vs transient lifetime, lazy resolution.
No decorators needed -- pure TypeScript interfaces and generics.
Show how this makes unit testing trivial by injecting mocks.
I will build a practical example with a web service and its dependencies.
</think>

Here is dependency injection in TypeScript from first principles:

```typescript
// Step 1: Define interfaces (contracts)
interface Logger {
  info(message: string, context?: Record<string, unknown>): void;
  error(message: string, error?: Error): void;
}

interface Database {
  query<T>(sql: string, params?: unknown[]): Promise<T[]>;
  execute(sql: string, params?: unknown[]): Promise<void>;
}

interface Cache {
  get<T>(key: string): Promise<T | null>;
  set(key: string, value: unknown, ttlMs?: number): Promise<void>;
}

// Step 2: Implementations
class ConsoleLogger implements Logger {
  info(message: string, context?: Record<string, unknown>) {
    console.log(JSON.stringify({ level: "info", message, ...context }));
  }
  error(message: string, error?: Error) {
    console.error(JSON.stringify({ level: "error", message, error: error?.message }));
  }
}

class PostgresDatabase implements Database {
  constructor(private connectionString: string) {}
  async query<T>(sql: string, params?: unknown[]): Promise<T[]> { return []; }
  async execute(sql: string, params?: unknown[]): Promise<void> {}
}

// Step 3: Constructor injection
class UserService {
  constructor(
    private db: Database,
    private cache: Cache,
    private logger: Logger
  ) {}

  async getUser(id: string) {
    const cached = await this.cache.get<User>(`user:${id}`);
    if (cached) {
      this.logger.info("Cache hit", { userId: id });
      return cached;
    }

    const [user] = await this.db.query<User>(
      "SELECT * FROM users WHERE id = $1", [id]
    );
    if (user) await this.cache.set(`user:${id}`, user, 60_000);
    return user ?? null;
  }
}

// Step 4: Simple DI Container
type Factory<T> = (container: Container) => T;

class Container {
  private factories = new Map<string, Factory<any>>();
  private singletons = new Map<string, any>();

  register<T>(token: string, factory: Factory<T>): this {
    this.factories.set(token, factory);
    return this;
  }

  singleton<T>(token: string, factory: Factory<T>): this {
    this.factories.set(token, (c) => {
      if (!this.singletons.has(token)) {
        this.singletons.set(token, factory(c));
      }
      return this.singletons.get(token);
    });
    return this;
  }

  resolve<T>(token: string): T {
    const factory = this.factories.get(token);
    if (!factory) throw new Error(`No registration for "${token}"`);
    return factory(this);
  }
}

// Step 5: Wire everything together
function createContainer(config: AppConfig): Container {
  const container = new Container();

  container.singleton("logger", () => new ConsoleLogger());
  container.singleton("database", () => new PostgresDatabase(config.dbUrl));
  container.singleton("cache", () => new RedisCache(config.redisUrl));

  container.register("userService", (c) =>
    new UserService(
      c.resolve("database"),
      c.resolve("cache"),
      c.resolve("logger")
    )
  );

  return container;
}

const container = createContainer({
  dbUrl: process.env.DATABASE_URL!,
  redisUrl: process.env.REDIS_URL!,
});

const userService = container.resolve<UserService>("userService");

// Step 6: Testing -- inject mocks
class MockDatabase implements Database {
  private data = new Map<string, any[]>();
  seed(table: string, rows: any[]) { this.data.set(table, rows); }
  async query<T>(sql: string): Promise<T[]> {
    return (this.data.get("users") ?? []) as T[];
  }
  async execute(): Promise<void> {}
}

class MockCache implements Cache {
  private store = new Map<string, any>();
  async get<T>(key: string): Promise<T | null> {
    return this.store.get(key) ?? null;
  }
  async set(key: string, value: unknown): Promise<void> {
    this.store.set(key, value);
  }
}

class MockLogger implements Logger {
  logs: { level: string; message: string }[] = [];
  info(message: string) { this.logs.push({ level: "info", message }); }
  error(message: string) { this.logs.push({ level: "error", message }); }
}

describe("UserService", () => {
  it("returns cached user on cache hit", async () => {
    const db = new MockDatabase();
    const cache = new MockCache();
    const logger = new MockLogger();

    await cache.set("user:123", { id: "123", name: "Alice" });

    const service = new UserService(db, cache, logger);
    const user = await service.getUser("123");

    expect(user).toEqual({ id: "123", name: "Alice" });
    expect(logger.logs[0].message).toBe("Cache hit");
  });
});
```

The pattern: **interfaces** define contracts, **classes** implement them, **constructors** declare what they need, and the **container** wires implementations to consumers. Full testability without any framework or decorator magic.'''),

    ("js_deep1_24", r'''Show me how to write effective mocks, stubs, and spies in JavaScript testing without a mocking library. Then show the equivalent patterns with jest.mock and vi.mock.''', r'''<think>
Manual mocking teaches the underlying concepts that libraries automate.
A stub replaces a function with a predetermined return value.
A spy wraps a function to record calls while preserving behavior.
A mock combines stub + spy: records calls AND controls return values.
I should show manual implementations first, then jest equivalents.
Key patterns: function spies, module mocking, partial mocking, mock reset.
Jest: jest.fn(), jest.spyOn(), jest.mock(). Vitest: vi.fn(), vi.spyOn(), vi.mock().
Important: mock restoration (cleanup) to prevent test pollution.
I will cover: simple spies, return value control, module replacement.
</think>

Here is mocking from first principles, then with jest/vitest:

```typescript
// MANUAL: Build a spy function from scratch
interface SpyCall<Args extends unknown[], R> {
  args: Args;
  result?: R;
  error?: Error;
  timestamp: number;
}

function createSpy<Args extends unknown[], R>(
  implementation?: (...args: Args) => R
) {
  const calls: SpyCall<Args, R>[] = [];
  let _impl = implementation;

  const spy = (...args: Args): R => {
    const call: SpyCall<Args, R> = { args, timestamp: Date.now() };
    calls.push(call);
    try {
      if (_impl) {
        const result = _impl(...args);
        call.result = result;
        return result;
      }
      return undefined as R;
    } catch (err) {
      call.error = err as Error;
      throw err;
    }
  };

  spy.calls = calls;
  spy.callCount = () => calls.length;
  spy.calledWith = (...args: Args) =>
    calls.some(c => JSON.stringify(c.args) === JSON.stringify(args));
  spy.lastCall = () => calls[calls.length - 1];
  spy.reset = () => { calls.length = 0; };
  spy.mockImplementation = (fn: (...args: Args) => R) => { _impl = fn; };
  spy.mockReturnValue = (value: R) => { _impl = () => value; };

  return spy;
}

const fetchData = createSpy((id: string) => ({ id, name: "test" }));
fetchData("123");
fetchData("456");
console.log(fetchData.callCount());       // 2
console.log(fetchData.calledWith("123")); // true

// JEST: jest.fn() -- creates a spy/mock function
describe("UserService", () => {
  it("calls database with correct query", async () => {
    const mockQuery = jest.fn().mockResolvedValue([
      { id: "1", name: "Alice" },
    ]);

    const db: Database = { query: mockQuery, execute: jest.fn() };
    const service = new UserService(db, mockCache, mockLogger);
    const user = await service.getUser("1");

    expect(mockQuery).toHaveBeenCalledTimes(1);
    expect(mockQuery).toHaveBeenCalledWith(
      "SELECT * FROM users WHERE id = $1", ["1"]
    );
    expect(user).toEqual({ id: "1", name: "Alice" });
  });
});

// JEST: jest.spyOn() -- wrap existing methods
describe("spy patterns", () => {
  it("tracks calls to existing methods", () => {
    const obj = { add: (a: number, b: number) => a + b };
    const spy = jest.spyOn(obj, "add");

    obj.add(1, 2);

    expect(spy).toHaveBeenCalledWith(1, 2);
    expect(spy).toHaveReturnedWith(3);
    spy.mockRestore();
  });

  it("replaces implementation temporarily", async () => {
    const spy = jest.spyOn(global, "fetch").mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    );
    await fetchData("/api/test");
    expect(spy).toHaveBeenCalledWith("/api/test");
    spy.mockRestore();
  });
});

// JEST: jest.mock() -- replace entire modules
jest.mock("./database");

jest.mock("./email-service", () => ({
  sendEmail: jest.fn().mockResolvedValue({ messageId: "mock-123" }),
}));

// Partial mock: keep some real implementations
jest.mock("./utils", () => ({
  ...jest.requireActual("./utils"),
  fetchRemoteConfig: jest.fn().mockResolvedValue({ feature: true }),
}));

// VITEST: equivalent patterns
import { vi } from "vitest";

const mockFn = vi.fn().mockReturnValue(42);
const spy = vi.spyOn(console, "log");

vi.mock("./database", () => ({
  createConnection: vi.fn().mockReturnValue({
    query: vi.fn().mockResolvedValue([]),
  }),
}));

afterEach(() => {
  vi.restoreAllMocks();
});

// Pattern: mock factory for complex dependencies
function createMockLogger(): Logger & { info: jest.Mock; error: jest.Mock } {
  return { info: jest.fn(), error: jest.fn() };
}

function createMockDatabase(
  data: Record<string, any[]> = {}
): Database & { query: jest.Mock; execute: jest.Mock } {
  return {
    query: jest.fn().mockImplementation(async (sql: string) => {
      const table = sql.match(/FROM\s+(\w+)/i)?.[1] ?? "";
      return data[table] ?? [];
    }),
    execute: jest.fn().mockResolvedValue(undefined),
  };
}

it("handles empty results", async () => {
  const db = createMockDatabase({});
  const logger = createMockLogger();
  const service = new UserService(db, createMockCache(), logger);
  const result = await service.getUser("999");
  expect(result).toBeNull();
  expect(db.query).toHaveBeenCalledTimes(1);
});
```

The core insight: `jest.fn()` is just a `createSpy()` with more assertions. Understanding manual mocking makes you better at using frameworks -- you know when to use `fn()` vs `spyOn()` vs `mock()`.'''),

    ("js_deep1_25", r'''Explain property-based testing in JavaScript/TypeScript. Show how to use fast-check to find edge cases that example-based tests miss.''', r'''<think>
Property-based testing generates random inputs and checks that invariants hold.
Instead of testing specific examples, you define properties that must ALWAYS be true.
fast-check is the main JS library for this (inspired by Haskell QuickCheck).
Key concepts: arbitraries (data generators), properties (invariants), shrinking.
Common properties: roundtrip, invariants, commutativity.
Shrinking is the killer feature: fast-check finds the MINIMAL failing input.
Compare with example-based: property tests find edge cases you never think of.
I will show: basic property tests, custom arbitraries, bug discovery, and model-based testing.
</think>

Here is a guide to property-based testing with fast-check:

```typescript
import * as fc from "fast-check";

// What property-based testing IS

// Example-based: test specific inputs you chose
test("add: 1 + 2 = 3", () => expect(add(1, 2)).toBe(3));
// Did you test MAX_SAFE_INTEGER? Negative numbers? NaN?

// Property-based: test invariants for ALL inputs
test("add is commutative", () => {
  fc.assert(
    fc.property(fc.integer(), fc.integer(), (a, b) => {
      expect(add(a, b)).toBe(add(b, a));
    })
  );
});

// Property: roundtrip (encode then decode = original)
function serialize(obj: unknown): string { return JSON.stringify(obj); }
function deserialize(json: string): unknown { return JSON.parse(json); }

test("JSON roundtrip preserves data", () => {
  fc.assert(
    fc.property(fc.jsonValue(), (value) => {
      const roundtripped = deserialize(serialize(value));
      expect(roundtripped).toEqual(value);
    })
  );
});

// Property: sort invariants
function sortNumbers(arr: number[]): number[] {
  return [...arr].sort((a, b) => a - b);
}

test("sort properties", () => {
  fc.assert(
    fc.property(fc.array(fc.integer()), (arr) => {
      const sorted = sortNumbers(arr);
      expect(sorted.length).toBe(arr.length);
      for (let i = 1; i < sorted.length; i++) {
        expect(sorted[i]).toBeGreaterThanOrEqual(sorted[i - 1]);
      }
      expect(sorted.sort()).toEqual([...arr].sort());
    })
  );
});

// Finding REAL bugs with property-based testing
function clamp(value: number, min: number, max: number): number {
  if (value < min) return min;
  if (value > max) return max;
  return value;
}

test("clamp properties", () => {
  fc.assert(
    fc.property(fc.integer(), fc.integer(), fc.integer(), (value, a, b) => {
      const min = Math.min(a, b);
      const max = Math.max(a, b);
      const result = clamp(value, min, max);
      expect(result).toBeGreaterThanOrEqual(min);
      expect(result).toBeLessThanOrEqual(max);
    })
  );
});

// Custom arbitraries -- generate domain objects
interface User {
  id: string;
  email: string;
  age: number;
  role: "admin" | "user" | "guest";
}

const userArbitrary: fc.Arbitrary<User> = fc.record({
  id: fc.uuid(),
  email: fc.emailAddress(),
  age: fc.integer({ min: 13, max: 120 }),
  role: fc.constantFrom("admin", "user", "guest"),
});

test("user serialization roundtrip", () => {
  fc.assert(
    fc.property(userArbitrary, (user) => {
      const json = JSON.stringify(user);
      const parsed = JSON.parse(json) as User;
      expect(parsed).toEqual(user);
    })
  );
});

// Shrinking -- finding minimal failing case
function removeDuplicates<T>(arr: T[]): T[] {
  // Bug: only removes ADJACENT duplicates
  return arr.filter((item, i) => i === 0 || item !== arr[i - 1]);
}

test("removeDuplicates produces unique elements", () => {
  fc.assert(
    fc.property(fc.array(fc.integer({ min: 1, max: 5 })), (arr) => {
      const result = removeDuplicates(arr);
      const unique = new Set(result);
      expect(result.length).toBe(unique.size);
    })
  );
  // Property failed after 15 tests
  // Shrunk to: [1, 2, 1]  <-- minimal counterexample!
});

// Advanced: model-based testing
class MyStack<T> {
  private items: T[] = [];
  push(item: T) { this.items.push(item); }
  pop(): T | undefined { return this.items.pop(); }
  peek(): T | undefined { return this.items[this.items.length - 1]; }
  size(): number { return this.items.length; }
}

test("stack behaves like array-based model", () => {
  const command = fc.oneof(
    fc.integer().map(n => ({ type: "push" as const, value: n })),
    fc.constant({ type: "pop" as const }),
    fc.constant({ type: "peek" as const }),
  );

  fc.assert(
    fc.property(fc.array(command, { maxLength: 50 }), (commands) => {
      const stack = new MyStack<number>();
      const model: number[] = [];

      for (const cmd of commands) {
        switch (cmd.type) {
          case "push":
            stack.push(cmd.value);
            model.push(cmd.value);
            break;
          case "pop":
            expect(stack.pop()).toBe(model.pop());
            break;
          case "peek":
            expect(stack.peek()).toBe(model[model.length - 1]);
            break;
        }
        expect(stack.size()).toBe(model.length);
      }
    })
  );
});
```

Property-based testing excels at finding edge cases you would never write by hand. The **shrinking** feature is the killer: when a test fails on a large random input, fast-check automatically reduces it to the simplest input that still fails, making debugging trivial.'''),
]
