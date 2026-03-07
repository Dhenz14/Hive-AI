"""JavaScript/TypeScript training pairs (part 1): Node.js, async, TypeScript types, React."""

PAIRS = [
    (
        "javascript/node-readable-streams",
        r'''How do I read a large file in Node.js without loading the entire thing into memory? I keep running out of memory with fs.readFileSync on big CSV files.''',
        r'''<think>
The user is hitting memory limits with readFileSync on large files. This is the classic case
for Node.js readable streams. I should show fs.createReadStream with proper event handling,
backpressure awareness, and a practical line-by-line processing example. Using the readline
module on top of a read stream is the idiomatic approach for CSV-like line processing.
I'll also mention highWaterMark for tuning chunk size.
</think>

Use `fs.createReadStream` to process the file in chunks instead of loading it all at once:

```javascript
import { createReadStream } from 'fs';
import { createInterface } from 'readline';

async function processLargeCSV(filePath) {
  const stream = createReadStream(filePath, {
    encoding: 'utf-8',
    highWaterMark: 64 * 1024, // 64KB chunks (default is 16KB)
  });

  const rl = createInterface({ input: stream, crlfDelay: Infinity });

  let lineCount = 0;
  for await (const line of rl) {
    const columns = line.split(',');
    // Process each row here
    lineCount++;
    if (lineCount % 100_000 === 0) {
      console.log(`Processed ${lineCount} lines`);
    }
  }

  console.log(`Done. Total lines: ${lineCount}`);
}

processLargeCSV('./huge-data.csv');
```

Key points:
- `createReadStream` reads in chunks controlled by `highWaterMark`, so memory stays flat regardless of file size
- `readline.createInterface` splits the stream into lines for you
- `for await...of` handles backpressure automatically — it pauses the stream when your processing is slower than the read speed
- If you need raw chunks instead of lines, listen to `stream.on('data', chunk => ...)` directly'''
    ),
    (
        "javascript/transform-streams-pipeline",
        r'''I need to read a big JSON-lines file, transform each record, and write the results to a new file in Node.js. What's the right way to chain this with streams?''',
        r'''<think>
This is about Node.js Transform streams and the pipeline API. The user wants to chain
read -> transform -> write. I should use stream.pipeline (or stream/promises pipeline)
for proper error handling and backpressure, and show a Transform stream that parses
JSON lines and modifies each record. pipeline is preferred over .pipe() because it
handles cleanup on errors automatically.
</think>

Use `stream.pipeline` with a `Transform` stream for proper backpressure and error handling:

```javascript
import { createReadStream, createWriteStream } from 'fs';
import { pipeline } from 'stream/promises';
import { Transform } from 'stream';
import { createInterface } from 'readline';

function createJsonTransform(transformFn) {
  return new Transform({
    objectMode: true,
    transform(line, encoding, callback) {
      try {
        if (!line.trim()) return callback();
        const record = JSON.parse(line);
        const result = transformFn(record);
        callback(null, JSON.stringify(result) + '\n');
      } catch (err) {
        callback(err);
      }
    },
  });
}

async function transformFile(inputPath, outputPath) {
  const readStream = createReadStream(inputPath, { encoding: 'utf-8' });

  // Convert raw bytes to lines
  const lineStream = new Transform({
    objectMode: true,
    transform(chunk, enc, cb) {
      const lines = chunk.toString().split('\n');
      for (const line of lines) {
        if (line.trim()) this.push(line);
      }
      cb();
    },
  });

  const transformer = createJsonTransform((record) => ({
    ...record,
    processed: true,
    timestamp: Date.now(),
    name: record.name?.toUpperCase(),
  }));

  const writeStream = createWriteStream(outputPath);

  await pipeline(readStream, lineStream, transformer, writeStream);
  console.log('Pipeline complete');
}

transformFile('./input.jsonl', './output.jsonl');
```

Why `pipeline` over `.pipe()`:
- **Automatic cleanup**: destroys all streams if any stream errors
- **Backpressure**: handled correctly across the entire chain
- **Promise version**: `stream/promises` lets you `await` the whole pipeline
- **No memory leaks**: `.pipe()` doesn't clean up on error, `pipeline` does'''
    ),
    (
        "javascript/promise-allsettled-error-aggregation",
        r'''I have multiple API calls I want to run in parallel but I need ALL of them to finish even if some fail, and then get a summary of what failed. Promise.all just throws on the first error.''',
        r'''<think>
Promise.allSettled is exactly what the user needs — it waits for all promises regardless
of rejection. I should show how to partition the results into fulfilled/rejected, aggregate
errors meaningfully, and handle partial success. This is a common pattern for batch
operations. I'll include a practical helper function that extracts successes and errors
cleanly using the status discriminant.
</think>

`Promise.allSettled` waits for every promise to complete and reports each result's status:

```javascript
async function fetchAllUsers(userIds) {
  const results = await Promise.allSettled(
    userIds.map((id) =>
      fetch(`https://api.example.com/users/${id}`).then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status} for user ${id}`);
        return r.json();
      })
    )
  );

  const { successes, failures } = partitionSettled(results, userIds);

  console.log(`Fetched ${successes.length}/${userIds.length} users`);
  if (failures.length > 0) {
    console.error('Failed:', failures);
  }

  return { users: successes.map((s) => s.value), failures };
}

function partitionSettled(results, labels = []) {
  const successes = [];
  const failures = [];

  results.forEach((result, i) => {
    if (result.status === 'fulfilled') {
      successes.push({ value: result.value, index: i, label: labels[i] });
    } else {
      failures.push({
        reason: result.reason.message ?? String(result.reason),
        index: i,
        label: labels[i],
      });
    }
  });

  return { successes, failures };
}

// Usage
const ids = ['u1', 'u2', 'u3', 'u4', 'u5'];
const { users, failures } = await fetchAllUsers(ids);

// Optionally throw an AggregateError if too many failures
if (failures.length > ids.length / 2) {
  throw new AggregateError(
    failures.map((f) => new Error(f.reason)),
    `Majority failed: ${failures.length}/${ids.length}`
  );
}
```

Each result in the array is either `{ status: 'fulfilled', value }` or `{ status: 'rejected', reason }` — you always get all results, never short-circuit on the first error.'''
    ),
    (
        "javascript/async-iterators-paginated-api",
        r'''What's a clean way to iterate over a paginated REST API in JavaScript? I want to use for-await-of so the caller doesn't have to manage page tokens manually.''',
        r'''<think>
The user wants an async generator that abstracts away pagination. This is an excellent
use case for async iterators — yield each page's items and internally manage the cursor
or page token. I should show an async generator function with for-await-of consumption,
handle the stop condition, and mention Symbol.asyncIterator for class-based iterators.
I'll keep it practical with a real REST pagination pattern (cursor-based).
</think>

Use an async generator to encapsulate the pagination logic:

```javascript
async function* paginate(baseUrl, options = {}) {
  const { pageSize = 50, maxPages = Infinity } = options;
  let cursor = null;
  let page = 0;

  while (page < maxPages) {
    const url = new URL(baseUrl);
    url.searchParams.set('limit', pageSize);
    if (cursor) url.searchParams.set('cursor', cursor);

    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}: ${url}`);

    const { data, nextCursor } = await response.json();

    // Yield items one by one so the consumer gets a flat stream
    for (const item of data) {
      yield item;
    }

    page++;
    if (!nextCursor || data.length === 0) break;
    cursor = nextCursor;
  }
}

// Consumer is clean — no page management needed
async function getAllActiveUsers() {
  const users = [];
  for await (const user of paginate('https://api.example.com/users', { pageSize: 100 })) {
    if (user.status === 'active') {
      users.push(user);
    }
    // Can break early — the generator stops fetching
    if (users.length >= 500) break;
  }
  return users;
}

// Class-based version for reusable APIs
class PaginatedResource {
  constructor(baseUrl, pageSize = 50) {
    this.baseUrl = baseUrl;
    this.pageSize = pageSize;
  }

  async *[Symbol.asyncIterator]() {
    yield* paginate(this.baseUrl, { pageSize: this.pageSize });
  }
}

// Usage
const users = new PaginatedResource('https://api.example.com/users');
for await (const user of users) {
  console.log(user.name);
}
```

Key benefits:
- **Lazy fetching**: pages are only fetched as the consumer iterates
- **Early exit**: `break` in the `for await` loop stops further API calls
- **Composable**: you can chain with filtering, mapping, or `take(n)` helpers'''
    ),
    (
        "javascript/abortcontroller-fetch-cancellation",
        r'''How do I cancel a fetch request in JavaScript if it takes too long or the user navigates away? I need both timeout-based and manual cancellation.''',
        r'''<think>
AbortController is the standard way to cancel fetch requests. I need to show two patterns:
timeout-based cancellation (AbortSignal.timeout is the modern way, or manual setTimeout
with controller.abort), and user-triggered cancellation (e.g., component unmount or
navigation). I should also show how to detect AbortError vs other errors, and mention
AbortSignal.any for combining multiple signals.
</think>

Use `AbortController` to cancel fetch requests. Here are both patterns:

```javascript
// 1. Timeout-based cancellation (modern — Node 18+, all modern browsers)
async function fetchWithTimeout(url, timeoutMs = 5000) {
  const response = await fetch(url, {
    signal: AbortSignal.timeout(timeoutMs),
  });
  return response.json();
}

// 2. Manual cancellation (e.g., user action)
class ApiClient {
  #controller = null;

  async search(query) {
    // Cancel any in-flight request
    this.#controller?.abort();
    this.#controller = new AbortController();

    try {
      const res = await fetch(`/api/search?q=${encodeURIComponent(query)}`, {
        signal: this.#controller.signal,
      });
      return await res.json();
    } catch (err) {
      if (err.name === 'AbortError') {
        console.log('Request cancelled — newer search superseded it');
        return null;
      }
      throw err; // Re-throw real errors
    }
  }

  cancelAll() {
    this.#controller?.abort();
  }
}

// 3. Combined: timeout + manual cancel with AbortSignal.any
async function fetchCancellable(url, { timeoutMs = 10000, signal } = {}) {
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  const combinedSignal = signal
    ? AbortSignal.any([signal, timeoutSignal])
    : timeoutSignal;

  const response = await fetch(url, { signal: combinedSignal });
  return response.json();
}

// Usage in React
function useSearch() {
  const controllerRef = useRef(null);

  useEffect(() => {
    return () => controllerRef.current?.abort(); // Cleanup on unmount
  }, []);

  const search = async (query) => {
    controllerRef.current?.abort();
    controllerRef.current = new AbortController();
    return fetchCancellable(`/api/search?q=${query}`, {
      signal: controllerRef.current.signal,
      timeoutMs: 5000,
    });
  };

  return { search };
}
```

- `AbortSignal.timeout(ms)` — built-in, no manual setTimeout needed
- `AbortSignal.any([...signals])` — triggers if any signal fires (combine timeout + user cancel)
- Always check `err.name === 'AbortError'` to distinguish cancellation from real failures'''
    ),
    (
        "javascript/race-condition-prevention-locks",
        r'''I have a Node.js app where two async operations can modify the same file concurrently and corrupt it. How do I add locking to prevent race conditions without external dependencies?''',
        r'''<think>
Race conditions with async file access are common in Node.js. Since Node is single-threaded
for JS execution but async I/O can interleave, we need a mutex/lock pattern. I'll show a
simple promise-based mutex that serializes access to shared resources. No native Mutex in
Node, but we can build one with promise chaining. I should also mention the newer
`fs.open` with `O_EXCL` flag as a filesystem-level lock, and the proper-lockfile pattern.
</think>

Build a simple promise-based mutex to serialize access to shared resources:

```javascript
class Mutex {
  #queue = Promise.resolve();

  async acquire() {
    let release;
    const next = new Promise((resolve) => {
      release = resolve;
    });

    // Wait for previous lock holder, then give caller the release function
    const prev = this.#queue;
    this.#queue = next;
    await prev;
    return release;
  }

  async runExclusive(fn) {
    const release = await this.acquire();
    try {
      return await fn();
    } finally {
      release();
    }
  }
}

// Usage: protect concurrent file access
import { readFile, writeFile } from 'fs/promises';

const fileLocks = new Map();

function getFileLock(filePath) {
  if (!fileLocks.has(filePath)) {
    fileLocks.set(filePath, new Mutex());
  }
  return fileLocks.get(filePath);
}

async function safeUpdateJson(filePath, updater) {
  const lock = getFileLock(filePath);

  return lock.runExclusive(async () => {
    const raw = await readFile(filePath, 'utf-8');
    const data = JSON.parse(raw);
    const updated = updater(data);
    await writeFile(filePath, JSON.stringify(updated, null, 2));
    return updated;
  });
}

// Both of these are now safe — they'll serialize automatically
await Promise.all([
  safeUpdateJson('./state.json', (d) => ({ ...d, count: d.count + 1 })),
  safeUpdateJson('./state.json', (d) => ({ ...d, lastRun: Date.now() })),
]);
```

How the mutex works:
- Each `acquire()` chains a new promise onto the queue
- The caller `await`s the previous promise, guaranteeing serial execution
- `release()` resolves the current promise, letting the next waiter proceed
- `runExclusive` wraps acquire/release with `try/finally` so the lock is always freed

For multi-process locking (e.g., PM2 cluster mode), you need filesystem-level locks — use `fs.open` with `O_EXCL` flag or the `proper-lockfile` package.'''
    ),
    (
        "javascript/typescript-mapped-types",
        r'''I have a TypeScript interface and I want to create variations of it — like a version where all fields are optional, or a version with only certain keys. How do mapped types work?''',
        r'''<think>
The user wants to understand TypeScript mapped types. I should explain the syntax
`[K in keyof T]: ...` and show practical examples beyond just Partial/Pick. I'll cover
building custom mapped types, using `as` for key remapping, and combining with conditional
types. Show both the built-in utility types and how to create custom ones for real
scenarios like form state or API responses.
</think>

Mapped types iterate over keys of a type and transform each one. Here's how they work and how to build custom ones:

```typescript
interface User {
  id: number;
  name: string;
  email: string;
  role: 'admin' | 'user';
}

// Built-in mapped types (these are defined using the same syntax)
type OptionalUser = Partial<User>;          // all fields optional
type ReadonlyUser = Readonly<User>;         // all fields readonly
type NameAndEmail = Pick<User, 'name' | 'email'>; // subset of keys
type WithoutId = Omit<User, 'id'>;          // exclude keys

// Custom mapped type: make all string fields uppercase-branded
type Uppercased<T> = {
  [K in keyof T]: T[K] extends string ? Uppercase<T[K]> : T[K];
};

// Custom: nullable version (every field can also be null)
type Nullable<T> = {
  [K in keyof T]: T[K] | null;
};
type NullableUser = Nullable<User>;
// { id: number | null; name: string | null; ... }

// Key remapping with `as` — prefix all keys with "set"
type Setters<T> = {
  [K in keyof T as `set${Capitalize<string & K>}`]: (value: T[K]) => void;
};
type UserSetters = Setters<User>;
// { setId: (value: number) => void; setName: (value: string) => void; ... }

// Filter keys by value type — only keep string fields
type StringKeys<T> = {
  [K in keyof T as T[K] extends string ? K : never]: T[K];
};
type UserStrings = StringKeys<User>;
// { name: string; email: string; role: 'admin' | 'user' }

// Practical: form state with dirty tracking
type FormState<T> = {
  values: T;
  dirty: { [K in keyof T]: boolean };
  errors: { [K in keyof T]?: string };
};

function createForm<T>(initial: T): FormState<T> {
  return {
    values: { ...initial },
    dirty: Object.fromEntries(
      Object.keys(initial as object).map((k) => [k, false])
    ) as { [K in keyof T]: boolean },
    errors: {},
  };
}
```

The core syntax is `{ [K in keyof T]: NewType }` — `K` iterates each key, and you transform the value type however you want. Use `as` after `K in keyof T` to rename or filter keys.'''
    ),
    (
        "javascript/typescript-conditional-types",
        r'''Can you explain TypeScript conditional types? I see `T extends U ? X : Y` in library code and I'm not sure how to write my own.''',
        r'''<think>
Conditional types are one of TypeScript's most powerful features. I should explain the
basic syntax, then show `infer` for extracting types, distributive behavior over unions,
and practical use cases like unwrapping promises, extracting function return types, and
building type-level logic. The user sees these in library code so they need both reading
and writing ability.
</think>

Conditional types let you write type-level `if/else` logic. Here's a progression from basic to advanced:

```typescript
// Basic: T extends U ? TrueType : FalseType
type IsString<T> = T extends string ? true : false;
type A = IsString<'hello'>;  // true
type B = IsString<42>;       // false

// Practical: extract the element type from an array
type ElementOf<T> = T extends (infer E)[] ? E : never;
type C = ElementOf<string[]>;      // string
type D = ElementOf<[number, boolean]>; // number | boolean

// `infer` extracts parts of a type
type ReturnOf<T> = T extends (...args: any[]) => infer R ? R : never;
type E = ReturnOf<() => string>;   // string
type F = ReturnOf<(x: number) => Promise<boolean>>; // Promise<boolean>

// Unwrap nested promises
type Awaited<T> = T extends Promise<infer U> ? Awaited<U> : T;
type G = Awaited<Promise<Promise<number>>>; // number

// Distributive behavior: conditional types distribute over unions
type NonNullish<T> = T extends null | undefined ? never : T;
type H = NonNullish<string | null | number | undefined>; // string | number

// Practical: extract event handler argument types
type EventPayload<T> = T extends (event: infer P) => void ? P : never;

interface Handlers {
  onClick: (event: MouseEvent) => void;
  onKeyDown: (event: KeyboardEvent) => void;
  onCustom: (event: { id: string; data: unknown }) => void;
}

type ClickPayload = EventPayload<Handlers['onClick']>; // MouseEvent

// Advanced: type-level pattern matching
type ParseRoute<T extends string> =
  T extends `${infer _Start}:${infer Param}/${infer Rest}`
    ? Param | ParseRoute<Rest>
    : T extends `${infer _Start}:${infer Param}`
      ? Param
      : never;

type Params = ParseRoute<'/users/:userId/posts/:postId'>;
// "userId" | "postId"

// Constrain conditional types for better error messages
type MustBeArray<T> = T extends readonly any[]
  ? T[number]
  : { error: 'Expected an array type'; got: T };
```

Key concepts:
- **`infer`** captures a part of the type for use in the true branch
- **Distributive**: when `T` is a union, the condition is applied to each member separately
- **Recursive**: conditional types can reference themselves (like `Awaited` above)'''
    ),
    (
        "javascript/typescript-template-literal-types",
        r'''How do TypeScript template literal types work? I want to build type-safe event names and route patterns.''',
        r'''<think>
Template literal types let you construct string types from other types using backtick
syntax. They're great for event names, CSS properties, route patterns, and API endpoints.
I should show basic concatenation, combining with unions for cartesian products, extracting
parts with infer, and practical use cases like type-safe event emitters and route builders.
</think>

Template literal types use backtick syntax at the type level to construct and parse string types:

```typescript
// Basic: construct string types
type Greeting = `Hello, ${string}`;
const a: Greeting = 'Hello, world';  // OK
const b: Greeting = 'Goodbye';       // Error

// Combine with unions — creates cartesian product
type Color = 'red' | 'blue' | 'green';
type Shade = 'light' | 'dark';
type Theme = `${Shade}-${Color}`;
// "light-red" | "light-blue" | "light-green" | "dark-red" | "dark-blue" | "dark-green"

// Type-safe event emitter
type EventName = 'click' | 'focus' | 'blur';
type HandlerName = `on${Capitalize<EventName>}`;
// "onClick" | "onFocus" | "onBlur"

type EventHandlers = {
  [K in EventName as `on${Capitalize<K>}`]: (event: K) => void;
};
// { onClick: (event: "click") => void; onFocus: ...; onBlur: ... }

// Route pattern extraction with infer
type ExtractParams<T extends string> =
  T extends `${string}:${infer Param}/${infer Rest}`
    ? { [K in Param | keyof ExtractParamsObj<Rest>]: string }
    : T extends `${string}:${infer Param}`
      ? { [K in Param]: string }
      : {};

type ExtractParamsObj<T extends string> = ExtractParams<T>;

type UserRoute = ExtractParams<'/api/users/:userId/posts/:postId'>;
// { userId: string; postId: string }

// Type-safe API client
type Method = 'get' | 'post' | 'put' | 'delete';
type Endpoint = '/users' | '/users/:id' | '/posts' | '/posts/:id';

type ApiMethod = `${Uppercase<Method>} ${Endpoint}`;
// "GET /users" | "GET /users/:id" | "POST /users" | ... (16 combinations)

// CSS utility type
type CSSSpacing = `${'margin' | 'padding'}-${'top' | 'right' | 'bottom' | 'left'}`;
// "margin-top" | "margin-right" | ... | "padding-left"

type SpacingProps = {
  [K in CSSSpacing]?: number;
};

function applySpacing(el: HTMLElement, props: SpacingProps) {
  for (const [prop, value] of Object.entries(props)) {
    el.style.setProperty(prop, `${value}px`);
  }
}
```

Template literal types are especially powerful when combined with mapped types and `Capitalize`/`Uppercase`/`Lowercase` intrinsic string types for building type-safe DSLs.'''
    ),
    (
        "javascript/discriminated-unions-exhaustive-checks",
        r'''How do I make TypeScript enforce that I handle every variant of a union type? I keep forgetting to add cases when I extend my union.''',
        r'''<think>
The user wants exhaustive checking with discriminated unions. The key technique is using
a `never` assertion in the default case — if a new variant is added to the union but not
handled, TypeScript will error because the value can't be assigned to `never`. I should
show the discriminant property pattern, exhaustive switch, and the assertNever helper.
Also show it with if-chains and the satisfies operator approach.
</think>

Use a discriminated union with a `never` check in the default case. TypeScript will error at compile time if you miss a variant:

```typescript
// The discriminated union — "type" is the discriminant
type Shape =
  | { type: 'circle'; radius: number }
  | { type: 'rectangle'; width: number; height: number }
  | { type: 'triangle'; base: number; height: number };

// Exhaustive check helper
function assertNever(x: never, msg?: string): never {
  throw new Error(msg ?? `Unexpected value: ${JSON.stringify(x)}`);
}

function area(shape: Shape): number {
  switch (shape.type) {
    case 'circle':
      return Math.PI * shape.radius ** 2;
    case 'rectangle':
      return shape.width * shape.height;
    case 'triangle':
      return 0.5 * shape.base * shape.height;
    default:
      // If you add a new Shape variant and forget to handle it,
      // TypeScript will error HERE because `shape` won't be `never`
      return assertNever(shape);
  }
}

// Real example: state machine
type RequestState<T> =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'success'; data: T }
  | { status: 'error'; error: Error };

function renderState<T>(state: RequestState<T>): string {
  switch (state.status) {
    case 'idle':
      return 'Ready';
    case 'loading':
      return 'Loading...';
    case 'success':
      return `Got: ${state.data}`;
    case 'error':
      return `Error: ${state.error.message}`;
    default:
      return assertNever(state);
  }
}

// Also works with if-chains using type narrowing
function describe(shape: Shape): string {
  if (shape.type === 'circle') return `Circle r=${shape.radius}`;
  if (shape.type === 'rectangle') return `Rect ${shape.width}x${shape.height}`;
  if (shape.type === 'triangle') return `Tri base=${shape.base}`;

  // TypeScript knows shape is `never` here — compile error if a variant is unhandled
  return assertNever(shape);
}
```

The trick: after all variants are handled, the variable's type narrows to `never`. If you add a new variant to the union, the narrowing won't fully resolve and `assertNever(shape)` produces a type error, forcing you to add the missing case.'''
    ),
    (
        "javascript/type-guards-and-narrowing",
        r'''What are the different ways to narrow types in TypeScript? I'm confused about when to use `is`, `in`, `instanceof`, and type assertion functions.''',
        r'''<think>
Type narrowing is fundamental to TypeScript. I should cover all the narrowing mechanisms:
typeof guards, instanceof, `in` operator, discriminated unions (already covered but brief
mention), custom type predicates with `is`, and assertion functions with `asserts`.
Show when each is appropriate and the trade-offs. Custom type predicates are the most
important advanced concept here.
</think>

TypeScript has several narrowing mechanisms, each suited to different situations:

```typescript
// 1. typeof — for primitives
function process(value: string | number) {
  if (typeof value === 'string') {
    return value.toUpperCase(); // TS knows it's string
  }
  return value.toFixed(2); // TS knows it's number
}

// 2. instanceof — for class instances
function formatError(err: Error | string) {
  if (err instanceof TypeError) {
    return `Type error: ${err.message}`;
  }
  if (err instanceof Error) {
    return err.message;
  }
  return err; // string
}

// 3. `in` operator — for checking property existence
type Fish = { swim: () => void };
type Bird = { fly: () => void };

function move(animal: Fish | Bird) {
  if ('swim' in animal) {
    animal.swim(); // narrowed to Fish
  } else {
    animal.fly(); // narrowed to Bird
  }
}

// 4. Custom type predicate with `is`
interface ApiError {
  code: number;
  message: string;
  details?: Record<string, string>;
}

function isApiError(err: unknown): err is ApiError {
  return (
    typeof err === 'object' &&
    err !== null &&
    'code' in err &&
    'message' in err &&
    typeof (err as ApiError).code === 'number'
  );
}

async function callApi(url: string) {
  try {
    const res = await fetch(url);
    if (!res.ok) throw await res.json();
  } catch (err) {
    if (isApiError(err)) {
      console.error(`API error ${err.code}: ${err.message}`);
      // err is ApiError here — full autocomplete
    } else {
      throw err;
    }
  }
}

// 5. Assertion function with `asserts`
function assertDefined<T>(value: T | null | undefined, name: string): asserts value is T {
  if (value == null) {
    throw new Error(`${name} must be defined`);
  }
}

function processUser(user: User | null) {
  assertDefined(user, 'user');
  // After this line, TS knows user is User (not null)
  console.log(user.name);
}

// 6. Discriminated unions (narrowed by property value)
type Result<T> = { ok: true; value: T } | { ok: false; error: Error };

function unwrap<T>(result: Result<T>): T {
  if (result.ok) return result.value;
  throw result.error;
}
```

When to use which:
- **`typeof`**: primitives (`string`, `number`, `boolean`)
- **`instanceof`**: class hierarchies
- **`in`**: duck-typing / structural checks
- **`is` predicates**: custom validation logic, checking `unknown` values
- **`asserts`**: throw-on-failure guards that narrow after the call'''
    ),
    (
        "javascript/satisfies-operator-usage",
        r'''What does the `satisfies` operator do in TypeScript and when should I use it instead of a type annotation?''',
        r'''<think>
The `satisfies` operator (TS 4.9+) validates that an expression matches a type without
widening the inferred type. This is different from a type annotation which replaces the
inferred type. The key benefit is you get type checking AND preserve the narrower literal
types. I should show the difference with concrete examples — config objects and theme
definitions are classic use cases.
</think>

`satisfies` validates that a value conforms to a type while keeping the narrower inferred type. Compare with type annotation:

```typescript
type Color = { r: number; g: number; b: number } | string;

interface Palette {
  primary: Color;
  secondary: Color;
  accent: Color;
}

// With type annotation — loses literal type info
const palette1: Palette = {
  primary: '#ff0000',
  secondary: { r: 0, g: 128, b: 255 },
  accent: 'rebeccapurple',
};
palette1.primary.toUpperCase(); // Error! TS thinks it's `Color` (string | object)

// With satisfies — validates AND preserves narrowed types
const palette2 = {
  primary: '#ff0000',
  secondary: { r: 0, g: 128, b: 255 },
  accent: 'rebeccapurple',
} satisfies Palette;

palette2.primary.toUpperCase();   // OK — TS knows it's a string
palette2.secondary.r;             // OK — TS knows it's the object variant

// Use case: config objects with known keys
type Routes = Record<string, { path: string; auth?: boolean }>;

const routes = {
  home: { path: '/' },
  dashboard: { path: '/dashboard', auth: true },
  profile: { path: '/profile/:id', auth: true },
} satisfies Routes;

// TS knows the exact keys — autocompletes "home" | "dashboard" | "profile"
routes.dashboard.auth; // boolean (not boolean | undefined, because it's literally `true`)

// Use case: enforce exhaustive mapping
type Status = 'pending' | 'active' | 'archived';

const statusLabels = {
  pending: 'Pending Review',
  active: 'Active',
  archived: 'Archived',
} satisfies Record<Status, string>;
// If you add a new Status variant and forget to add it here, TS errors

// With annotation, you'd lose the literal string types:
const labels: Record<Status, string> = { ... };
labels.active; // string (not 'Active')

// The satisfies version preserves them:
statusLabels.active; // 'Active' (literal type)
```

Rule of thumb: use `satisfies` when you want to validate shape but preserve the narrower inferred types. Use type annotations when you intentionally want to widen the type.'''
    ),
    (
        "javascript/react-custom-hooks-data-fetching",
        r'''How should I build a custom React hook for data fetching that handles loading, error states, and avoids race conditions?''',
        r'''<think>
A data fetching hook is the quintessential custom hook example. I should include loading,
error, and data states, an AbortController for race condition prevention (when the
dependency changes before the previous fetch completes), and a clean API. I'll show a
generic useFetch with TypeScript generics, proper cleanup in useEffect, and mention
stale closure prevention.
</think>

Here's a production-quality `useFetch` hook with race condition prevention via `AbortController`:

```typescript
import { useState, useEffect, useCallback, useRef } from 'react';

interface FetchState<T> {
  data: T | null;
  error: Error | null;
  isLoading: boolean;
}

function useFetch<T>(url: string | null, options?: RequestInit): FetchState<T> & { refetch: () => void } {
  const [state, setState] = useState<FetchState<T>>({
    data: null,
    error: null,
    isLoading: false,
  });
  const fetchIdRef = useRef(0);

  const fetchData = useCallback(async (signal: AbortSignal) => {
    if (!url) return;

    const fetchId = ++fetchIdRef.current;
    setState((prev) => ({ ...prev, isLoading: true, error: null }));

    try {
      const response = await fetch(url, { ...options, signal });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);

      const data: T = await response.json();

      // Only update if this is still the latest request
      if (fetchId === fetchIdRef.current) {
        setState({ data, error: null, isLoading: false });
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return;
      if (fetchId === fetchIdRef.current) {
        setState({ data: null, error: err as Error, isLoading: false });
      }
    }
  }, [url, options]);

  useEffect(() => {
    const controller = new AbortController();
    fetchData(controller.signal);
    return () => controller.abort();
  }, [fetchData]);

  const refetch = useCallback(() => {
    const controller = new AbortController();
    fetchData(controller.signal);
  }, [fetchData]);

  return { ...state, refetch };
}

// Usage
function UserProfile({ userId }: { userId: string }) {
  const { data: user, error, isLoading, refetch } = useFetch<User>(
    `/api/users/${userId}`
  );

  if (isLoading) return <p>Loading...</p>;
  if (error) return <p>Error: {error.message} <button onClick={refetch}>Retry</button></p>;
  if (!user) return null;

  return <h1>{user.name}</h1>;
}

// Conditional fetching: pass null to skip
function Dashboard({ userId }: { userId: string | null }) {
  const { data } = useFetch<DashboardData>(
    userId ? `/api/dashboard/${userId}` : null
  );
  // Fetch only runs when userId is non-null
}
```

Key design decisions:
- **AbortController in cleanup**: cancels in-flight request when url changes or component unmounts
- **fetchIdRef**: prevents stale responses from overwriting newer data (race condition guard)
- **`null` url**: skips the fetch entirely (conditional fetching pattern)
- **`refetch`**: lets the consumer manually re-trigger without changing dependencies'''
    ),
    (
        "javascript/react-compound-component-pattern",
        r'''What's the compound component pattern in React? I want to build a flexible Tabs component where the parent controls state but children render independently.''',
        r'''<think>
Compound components use React context to share implicit state between a parent and its
children. The classic example is Tabs/Tab or Select/Option. The parent manages state,
children read it via context, and the API is declarative JSX. I should show the pattern
with TypeScript, context, and the dot-notation export style (Tabs.Tab, Tabs.Panel).
</think>

Compound components share implicit state through context, giving you a clean declarative API:

```typescript
import { createContext, useContext, useState, ReactNode } from 'react';

// 1. Shared context
interface TabsContextType {
  activeTab: string;
  setActiveTab: (id: string) => void;
}

const TabsContext = createContext<TabsContextType | null>(null);

function useTabsContext() {
  const ctx = useContext(TabsContext);
  if (!ctx) throw new Error('Tabs compound components must be used within <Tabs>');
  return ctx;
}

// 2. Parent — manages state
interface TabsProps {
  defaultTab: string;
  onChange?: (tabId: string) => void;
  children: ReactNode;
}

function Tabs({ defaultTab, onChange, children }: TabsProps) {
  const [activeTab, setActive] = useState(defaultTab);

  const setActiveTab = (id: string) => {
    setActive(id);
    onChange?.(id);
  };

  return (
    <TabsContext.Provider value={{ activeTab, setActiveTab }}>
      <div className="tabs">{children}</div>
    </TabsContext.Provider>
  );
}

// 3. Child components — read state from context
function TabList({ children }: { children: ReactNode }) {
  return <div role="tablist" className="tab-list">{children}</div>;
}

function Tab({ id, children }: { id: string; children: ReactNode }) {
  const { activeTab, setActiveTab } = useTabsContext();
  return (
    <button
      role="tab"
      aria-selected={activeTab === id}
      className={activeTab === id ? 'tab active' : 'tab'}
      onClick={() => setActiveTab(id)}
    >
      {children}
    </button>
  );
}

function Panel({ id, children }: { id: string; children: ReactNode }) {
  const { activeTab } = useTabsContext();
  if (activeTab !== id) return null;
  return <div role="tabpanel" className="tab-panel">{children}</div>;
}

// 4. Attach as dot-notation properties
Tabs.TabList = TabList;
Tabs.Tab = Tab;
Tabs.Panel = Panel;

// Usage — clean, declarative API
function Settings() {
  return (
    <Tabs defaultTab="general" onChange={(tab) => console.log(`Switched to ${tab}`)}>
      <Tabs.TabList>
        <Tabs.Tab id="general">General</Tabs.Tab>
        <Tabs.Tab id="security">Security</Tabs.Tab>
        <Tabs.Tab id="billing">Billing</Tabs.Tab>
      </Tabs.TabList>

      <Tabs.Panel id="general"><GeneralSettings /></Tabs.Panel>
      <Tabs.Panel id="security"><SecuritySettings /></Tabs.Panel>
      <Tabs.Panel id="billing"><BillingSettings /></Tabs.Panel>
    </Tabs>
  );
}
```

The compound pattern gives consumers full layout control while the parent manages state. Children can be reordered, wrapped in divs, or conditionally rendered — the context connection is implicit, not positional.'''
    ),
    (
        "javascript/react-context-optimization-split",
        r'''My React app re-renders everything when context updates. How do I split context to optimize performance?''',
        r'''<think>
The common problem: a single context with multiple values causes all consumers to re-render
when ANY value changes. The solution is to split into separate contexts (one for state,
one for dispatch, or one per concern). I should also mention useMemo for the value object,
and the pattern of separating frequently-changing values from stable ones.
</think>

The problem is that React re-renders every consumer when any part of the context value changes. Split your context by update frequency:

```typescript
import { createContext, useContext, useReducer, useMemo, ReactNode } from 'react';

// BAD: single context with everything
// Every component re-renders when count OR theme OR user changes
const BadContext = createContext({ count: 0, theme: 'light', user: null, dispatch: () => {} });

// GOOD: split by update frequency / concern

// 1. Separate state from dispatch (dispatch never changes)
interface State {
  count: number;
  items: string[];
}
type Action = { type: 'increment' } | { type: 'addItem'; item: string };

const StateContext = createContext<State | null>(null);
const DispatchContext = createContext<React.Dispatch<Action> | null>(null);

function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'increment': return { ...state, count: state.count + 1 };
    case 'addItem': return { ...state, items: [...state.items, action.item] };
    default: return state;
  }
}

function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, { count: 0, items: [] });

  // dispatch is stable — DispatchContext consumers never re-render from state changes
  return (
    <DispatchContext.Provider value={dispatch}>
      <StateContext.Provider value={state}>
        {children}
      </StateContext.Provider>
    </DispatchContext.Provider>
  );
}

// 2. Further split: separate frequently-changing from stable values
const CountContext = createContext(0);
const ItemsContext = createContext<string[]>([]);

function SplitProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(reducer, { count: 0, items: [] });

  // Memoize items array reference to prevent unnecessary re-renders
  const items = useMemo(() => state.items, [state.items]);

  return (
    <DispatchContext.Provider value={dispatch}>
      <CountContext.Provider value={state.count}>
        <ItemsContext.Provider value={items}>
          {children}
        </ItemsContext.Provider>
      </CountContext.Provider>
    </DispatchContext.Provider>
  );
}

// Now components only re-render when their specific context changes
function Counter() {
  const count = useContext(CountContext);  // Only re-renders on count change
  const dispatch = useContext(DispatchContext)!;
  return <button onClick={() => dispatch({ type: 'increment' })}>{count}</button>;
}

function ItemList() {
  const items = useContext(ItemsContext);  // Only re-renders on items change
  return <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul>;
}

// Custom hooks for clean API
function useCount() { return useContext(CountContext); }
function useItems() { return useContext(ItemsContext); }
function useAppDispatch() {
  const dispatch = useContext(DispatchContext);
  if (!dispatch) throw new Error('Missing AppProvider');
  return dispatch;
}
```

Rules of thumb:
- Separate **state from dispatch** — dispatch is a stable reference
- Split contexts that **change at different rates** (count changes often, theme rarely)
- Use `useMemo` for derived values to stabilize references'''
    ),
    (
        "javascript/react-suspense-lazy-loading",
        r'''How do I use React Suspense with lazy loading to code-split my app and show loading states?''',
        r'''<think>
React.lazy and Suspense for code splitting is a core performance optimization. I should
show the basic lazy/Suspense pattern, nested Suspense boundaries for granular loading
states, error boundaries for failed loads, and route-based splitting. Also mention
preloading strategies for better UX.
</think>

Use `React.lazy` for code splitting and `Suspense` for declarative loading states:

```typescript
import { lazy, Suspense, ComponentType } from 'react';

// Basic: lazy-load a route component
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Settings = lazy(() => import('./pages/Settings'));
const Analytics = lazy(() => import('./pages/Analytics'));

function App() {
  return (
    <Suspense fallback={<FullPageSpinner />}>
      <Routes>
        <Route path="/dashboard" element={<Dashboard />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/analytics" element={<Analytics />} />
      </Routes>
    </Suspense>
  );
}

// Nested Suspense: granular loading states
function DashboardPage() {
  return (
    <div className="dashboard">
      <h1>Dashboard</h1>

      {/* Chart loads independently — doesn't block the sidebar */}
      <Suspense fallback={<ChartSkeleton />}>
        <HeavyChart />
      </Suspense>

      <Suspense fallback={<TableSkeleton />}>
        <DataTable />
      </Suspense>
    </div>
  );
}

const HeavyChart = lazy(() => import('./components/HeavyChart'));
const DataTable = lazy(() => import('./components/DataTable'));

// Error boundary for failed chunk loads
import { Component, ReactNode } from 'react';

class ChunkErrorBoundary extends Component<
  { children: ReactNode; fallback: ReactNode },
  { hasError: boolean }
> {
  state = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  render() {
    if (this.state.hasError) {
      return (
        <div>
          <p>Failed to load. <button onClick={() => window.location.reload()}>Retry</button></p>
        </div>
      );
    }
    return this.props.children;
  }
}

// Wrap lazy components with error boundary
function SafeLazy({ children }: { children: ReactNode }) {
  return (
    <ChunkErrorBoundary fallback={<p>Failed to load component</p>}>
      <Suspense fallback={<Spinner />}>
        {children}
      </Suspense>
    </ChunkErrorBoundary>
  );
}

// Preload on hover/focus for better UX
function preload(factory: () => Promise<{ default: ComponentType }>) {
  factory(); // Triggers the import, caches the promise
}

function NavLink({ to, factory, children }: { to: string; factory: () => Promise<any>; children: ReactNode }) {
  return (
    <Link
      to={to}
      onMouseEnter={() => preload(factory)}
      onFocus={() => preload(factory)}
    >
      {children}
    </Link>
  );
}

// Usage: preloads Analytics chunk when user hovers the nav link
<NavLink to="/analytics" factory={() => import('./pages/Analytics')}>
  Analytics
</NavLink>
```

Key patterns: nest `Suspense` boundaries for independent loading zones, pair with error boundaries for resilience, and preload on hover to eliminate perceived latency.'''
    ),
    (
        "javascript/react-server-components-basics",
        r'''Can you explain React Server Components? What's the difference between server and client components, and when should I use each?''',
        r'''<think>
React Server Components (RSC) are a paradigm shift. I should explain the mental model:
server components run on the server only (no JS shipped), client components run on both.
The 'use client' directive marks the boundary. Key points: server components can be async,
can access databases directly, but can't use state/effects. Client components handle
interactivity. Show practical file structure and data flow patterns.
</think>

React Server Components (RSC) split your components into two types — server (default) and client (`'use client'`):

```typescript
// Server Component (default in Next.js App Router) — runs on server only
// app/dashboard/page.tsx
import { db } from '@/lib/db';
import { UserList } from './UserList';
import { SearchBar } from './SearchBar';

// Can be async! Runs on the server, zero JS shipped for this component
export default async function DashboardPage() {
  const users = await db.query('SELECT * FROM users LIMIT 100');
  const stats = await db.query('SELECT count(*) FROM orders');

  return (
    <div>
      <h1>Dashboard ({stats.count} orders)</h1>
      {/* Client component for interactivity */}
      <SearchBar />
      {/* Server component — passes server data as props */}
      <UserList users={users} />
    </div>
  );
}

// Client Component — 'use client' directive at the top
// app/dashboard/SearchBar.tsx
'use client';

import { useState, useTransition } from 'react';
import { useRouter } from 'next/navigation';

export function SearchBar() {
  const [query, setQuery] = useState('');
  const [isPending, startTransition] = useTransition();
  const router = useRouter();

  function handleSearch(value: string) {
    setQuery(value);
    startTransition(() => {
      router.push(`/dashboard?q=${value}`);
    });
  }

  return (
    <input
      value={query}
      onChange={(e) => handleSearch(e.target.value)}
      placeholder={isPending ? 'Searching...' : 'Search users...'}
    />
  );
}

// Server Component rendering server data — no 'use client' needed
// app/dashboard/UserList.tsx
interface User { id: number; name: string; email: string; }

export function UserList({ users }: { users: User[] }) {
  return (
    <ul>
      {users.map((u) => (
        <li key={u.id}>{u.name} — {u.email}</li>
      ))}
    </ul>
  );
}
```

**Decision guide:**

| Use Server Component when... | Use Client Component when... |
|---|---|
| Fetching data from DB/API | Need `useState`, `useEffect` |
| Accessing server-only resources | Event handlers (onClick, onChange) |
| Keeping secrets server-side | Browser APIs (localStorage, etc.) |
| Rendering static/data-driven UI | Interactive widgets, forms |
| Reducing client JS bundle | Third-party client-only libraries |

**Key rules:**
- Server components can import client components, but NOT vice versa
- Props crossing the server-client boundary must be serializable (no functions, no classes)
- Server components can be `async` — client components cannot'''
    ),
    (
        "javascript/use-transition-non-blocking-updates",
        r'''What's useTransition in React and when should I use it? I have a search input that filters a huge list and it makes typing laggy.''',
        r'''<think>
useTransition marks state updates as non-urgent so React can interrupt them to keep the
UI responsive. The classic use case is exactly what the user describes: filtering a large
list while keeping the input responsive. I should show the before/after, explain the
isPending flag, and contrast with useDeferredValue which is the simpler alternative
for the same problem.
</think>

`useTransition` tells React that a state update is non-urgent, so it can be interrupted by urgent updates (like typing):

```typescript
import { useState, useTransition, useMemo } from 'react';

// WITHOUT useTransition — typing is laggy
function SearchListSlow({ items }: { items: Item[] }) {
  const [query, setQuery] = useState('');

  // This filters on every keystroke, blocking the input
  const filtered = items.filter((item) =>
    item.name.toLowerCase().includes(query.toLowerCase())
  );

  return (
    <>
      <input value={query} onChange={(e) => setQuery(e.target.value)} />
      <List items={filtered} />
    </>
  );
}

// WITH useTransition — input stays snappy
function SearchList({ items }: { items: Item[] }) {
  const [query, setQuery] = useState('');
  const [filterQuery, setFilterQuery] = useState('');
  const [isPending, startTransition] = useTransition();

  const filtered = useMemo(
    () => items.filter((item) =>
      item.name.toLowerCase().includes(filterQuery.toLowerCase())
    ),
    [items, filterQuery]
  );

  function handleChange(e: React.ChangeEvent<HTMLInputElement>) {
    const value = e.target.value;
    setQuery(value); // Urgent: update input immediately

    startTransition(() => {
      setFilterQuery(value); // Non-urgent: can be interrupted
    });
  }

  return (
    <>
      <input value={query} onChange={handleChange} />
      {isPending && <p className="text-gray-400">Updating...</p>}
      <List items={filtered} />
    </>
  );
}

// Simpler alternative: useDeferredValue (same effect, less code)
import { useDeferredValue } from 'react';

function SearchListDeferred({ items }: { items: Item[] }) {
  const [query, setQuery] = useState('');
  const deferredQuery = useDeferredValue(query);

  const filtered = useMemo(
    () => items.filter((item) =>
      item.name.toLowerCase().includes(deferredQuery.toLowerCase())
    ),
    [items, deferredQuery]
  );

  const isStale = query !== deferredQuery;

  return (
    <>
      <input value={query} onChange={(e) => setQuery(e.target.value)} />
      <div style={{ opacity: isStale ? 0.6 : 1 }}>
        <List items={filtered} />
      </div>
    </>
  );
}
```

**useTransition vs useDeferredValue:**
- `useTransition`: wraps the setter call — use when you control the state update
- `useDeferredValue`: wraps the value — use when you receive a value as a prop and want to defer its effect
- Both achieve the same goal: React prioritizes urgent updates (typing) over non-urgent ones (filtering)'''
    ),
    (
        "javascript/jest-mocking-modules-functions",
        r'''How do I properly mock modules and functions in Jest? I need to mock a database module and an API client for unit tests.''',
        r'''<think>
Jest mocking is essential for unit testing. I should cover jest.mock for module-level
mocking, jest.fn for individual functions, spyOn for partial mocking, and the typed
mock pattern with jest.Mocked. Show practical examples with a database module and API
client, including setup/teardown patterns and assertion helpers.
</think>

Here are the main Jest mocking patterns with practical examples:

```typescript
// src/services/userService.ts
import { db } from '../lib/db';
import { apiClient } from '../lib/apiClient';

export async function getUser(id: string) {
  const cached = await db.get('users', id);
  if (cached) return cached;

  const user = await apiClient.fetch(`/users/${id}`);
  await db.set('users', id, user);
  return user;
}

// __tests__/userService.test.ts
import { getUser } from '../services/userService';
import { db } from '../lib/db';
import { apiClient } from '../lib/apiClient';

// 1. Mock entire modules
jest.mock('../lib/db');
jest.mock('../lib/apiClient');

// Get typed mock versions
const mockDb = jest.mocked(db);
const mockApi = jest.mocked(apiClient);

describe('getUser', () => {
  beforeEach(() => {
    jest.clearAllMocks(); // Reset call counts and implementations
  });

  it('returns cached user from db', async () => {
    const cachedUser = { id: '1', name: 'Alice' };
    mockDb.get.mockResolvedValue(cachedUser);

    const result = await getUser('1');

    expect(result).toEqual(cachedUser);
    expect(mockDb.get).toHaveBeenCalledWith('users', '1');
    expect(mockApi.fetch).not.toHaveBeenCalled(); // Didn't hit API
  });

  it('fetches from API on cache miss and stores result', async () => {
    const apiUser = { id: '2', name: 'Bob' };
    mockDb.get.mockResolvedValue(null); // Cache miss
    mockApi.fetch.mockResolvedValue(apiUser);

    const result = await getUser('2');

    expect(result).toEqual(apiUser);
    expect(mockApi.fetch).toHaveBeenCalledWith('/users/2');
    expect(mockDb.set).toHaveBeenCalledWith('users', '2', apiUser);
  });

  it('throws when API fails', async () => {
    mockDb.get.mockResolvedValue(null);
    mockApi.fetch.mockRejectedValue(new Error('Network error'));

    await expect(getUser('3')).rejects.toThrow('Network error');
  });
});

// 2. Partial module mock — keep some real implementations
jest.mock('../lib/utils', () => ({
  ...jest.requireActual('../lib/utils'),
  generateId: jest.fn(() => 'mock-id-123'),
}));

// 3. spyOn — mock a single method without replacing the module
import * as mathUtils from '../lib/mathUtils';

test('spyOn example', () => {
  const spy = jest.spyOn(mathUtils, 'calculateTax').mockReturnValue(42);

  const result = mathUtils.calculateTax(100);
  expect(result).toBe(42);
  expect(spy).toHaveBeenCalledWith(100);

  spy.mockRestore(); // Restore original implementation
});

// 4. Mock factory with different behaviors per test
jest.mock('../lib/config', () => ({
  getConfig: jest.fn(),
}));

import { getConfig } from '../lib/config';
const mockGetConfig = jest.mocked(getConfig);

test('production behavior', () => {
  mockGetConfig.mockReturnValue({ env: 'production', debug: false });
  // ...
});

test('development behavior', () => {
  mockGetConfig.mockReturnValue({ env: 'development', debug: true });
  // ...
});
```

Key tips: use `jest.mocked()` for type safety, `clearAllMocks` in `beforeEach`, and `mockResolvedValue`/`mockRejectedValue` for async mocks.'''
    ),
    (
        "javascript/vitest-async-testing-patterns",
        r'''I'm switching from Jest to Vitest. How do I test async code, timers, and handle expected errors in Vitest?''',
        r'''<think>
Vitest has a very similar API to Jest but with some differences. I should show async
testing with async/await, timer mocking with vi.useFakeTimers, error assertion patterns,
and the differences from Jest (vi instead of jest, first-class ESM support). Also cover
vi.fn, vi.spyOn, and the concurrent test feature.
</think>

Vitest's API is mostly Jest-compatible but uses `vi` instead of `jest`. Here are the async and timer patterns:

```typescript
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// 1. Async/await testing
describe('async operations', () => {
  it('resolves with data', async () => {
    const fetchUser = vi.fn().mockResolvedValue({ id: 1, name: 'Alice' });

    const user = await fetchUser(1);
    expect(user).toEqual({ id: 1, name: 'Alice' });
    expect(fetchUser).toHaveBeenCalledWith(1);
  });

  it('rejects with an error', async () => {
    const failingFn = vi.fn().mockRejectedValue(new Error('Not found'));

    await expect(failingFn()).rejects.toThrow('Not found');
    // Or check the full error object
    await expect(failingFn()).rejects.toMatchObject({
      message: 'Not found',
    });
  });
});

// 2. Timer mocking
describe('debounce', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('calls the function after the delay', () => {
    const callback = vi.fn();
    const debounced = debounce(callback, 300);

    debounced('hello');
    expect(callback).not.toHaveBeenCalled();

    vi.advanceTimersByTime(299);
    expect(callback).not.toHaveBeenCalled();

    vi.advanceTimersByTime(1);
    expect(callback).toHaveBeenCalledWith('hello');
  });

  it('resets timer on subsequent calls', () => {
    const callback = vi.fn();
    const debounced = debounce(callback, 300);

    debounced('a');
    vi.advanceTimersByTime(200);
    debounced('b'); // Resets the timer
    vi.advanceTimersByTime(300);

    expect(callback).toHaveBeenCalledTimes(1);
    expect(callback).toHaveBeenCalledWith('b');
  });
});

// 3. Testing async with timers (common pain point)
describe('polling', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('polls until condition is met', async () => {
    let count = 0;
    const checkStatus = vi.fn(async () => {
      count++;
      return count >= 3 ? 'done' : 'pending';
    });

    const promise = pollUntil(checkStatus, { interval: 1000, timeout: 10000 });

    // Advance timers and flush promises
    await vi.advanceTimersByTimeAsync(1000);
    await vi.advanceTimersByTimeAsync(1000);
    await vi.advanceTimersByTimeAsync(1000);

    const result = await promise;
    expect(result).toBe('done');
    expect(checkStatus).toHaveBeenCalledTimes(3);
  });
});

// 4. Module mocking
vi.mock('./db', () => ({
  query: vi.fn(),
}));

import { query } from './db';

it('mocks module imports', async () => {
  vi.mocked(query).mockResolvedValue([{ id: 1 }]);
  const rows = await query('SELECT * FROM users');
  expect(rows).toHaveLength(1);
});

// 5. Concurrent tests (Vitest-specific — runs tests in parallel)
describe.concurrent('independent tests', () => {
  it('test A', async () => {
    const result = await slowOperation('a');
    expect(result).toBeDefined();
  });

  it('test B', async () => {
    const result = await slowOperation('b');
    expect(result).toBeDefined();
  });
});
```

Key Vitest differences from Jest: `vi.advanceTimersByTimeAsync` for async timer code, `describe.concurrent` for parallel tests, and native ESM support (no transform needed).'''
    ),
    (
        "javascript/msw-api-mocking-tests",
        r'''How do I use MSW (Mock Service Worker) to mock API responses in my tests? I want to avoid mocking fetch directly.''',
        r'''<think>
MSW intercepts requests at the network level, so you don't need to mock fetch or axios.
It's the recommended approach for testing API interactions. I should show MSW v2 syntax
(the http.get/post handlers), setupServer for Node tests, and patterns for per-test
overrides, error simulation, and dynamic responses. MSW v2 changed the API significantly
from v1.
</think>

MSW intercepts at the network level — your code uses real `fetch`/`axios` and MSW intercepts the requests. Here's the MSW v2 setup:

```typescript
// mocks/handlers.ts — define default API behaviors
import { http, HttpResponse } from 'msw';

export const handlers = [
  http.get('/api/users', () => {
    return HttpResponse.json([
      { id: 1, name: 'Alice', role: 'admin' },
      { id: 2, name: 'Bob', role: 'user' },
    ]);
  }),

  http.get('/api/users/:id', ({ params }) => {
    const { id } = params;
    return HttpResponse.json({ id: Number(id), name: `User ${id}` });
  }),

  http.post('/api/users', async ({ request }) => {
    const body = await request.json();
    return HttpResponse.json(
      { id: 3, ...body },
      { status: 201 }
    );
  }),
];

// mocks/server.ts — setup for Node (Vitest/Jest)
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);

// test setup (vitest.setup.ts or jest.setup.ts)
import { beforeAll, afterAll, afterEach } from 'vitest';
import { server } from './mocks/server';

beforeAll(() => server.listen({ onUnhandledRequest: 'error' }));
afterEach(() => server.resetHandlers()); // Reset overrides between tests
afterAll(() => server.close());

// __tests__/userService.test.ts
import { http, HttpResponse } from 'msw';
import { server } from '../mocks/server';
import { getUsers, createUser } from '../services/userService';

describe('userService', () => {
  it('fetches users from API', async () => {
    // Uses default handler — returns Alice and Bob
    const users = await getUsers();
    expect(users).toHaveLength(2);
    expect(users[0].name).toBe('Alice');
  });

  it('handles server errors', async () => {
    // Override for this specific test
    server.use(
      http.get('/api/users', () => {
        return HttpResponse.json(
          { error: 'Internal Server Error' },
          { status: 500 }
        );
      })
    );

    await expect(getUsers()).rejects.toThrow('HTTP 500');
  });

  it('handles network errors', async () => {
    server.use(
      http.get('/api/users', () => {
        return HttpResponse.error(); // Simulates network failure
      })
    );

    await expect(getUsers()).rejects.toThrow();
  });

  it('creates a user', async () => {
    const user = await createUser({ name: 'Charlie', role: 'user' });
    expect(user.id).toBe(3);
    expect(user.name).toBe('Charlie');
  });

  it('tracks request details', async () => {
    let capturedBody: any;

    server.use(
      http.post('/api/users', async ({ request }) => {
        capturedBody = await request.json();
        return HttpResponse.json({ id: 4, ...capturedBody }, { status: 201 });
      })
    );

    await createUser({ name: 'Dan', role: 'admin' });
    expect(capturedBody).toEqual({ name: 'Dan', role: 'admin' });
  });
});
```

MSW advantages over `jest.fn()` / `vi.fn()` mocking: tests exercise your actual HTTP client code (headers, serialization, error handling), not a mocked shortcut.'''
    ),
    (
        "javascript/express-middleware-chain",
        r'''How does Express middleware chaining work? I want to build reusable middleware for auth, validation, and error handling.''',
        r'''<think>
Express middleware is a core concept — functions with (req, res, next) that form a chain.
I should show the execution order, how next() passes control, error middleware with 4
args, and practical reusable middleware patterns. Include async error handling since
Express doesn't catch async errors by default (need to wrap or use express-async-errors).
</think>

Express middleware are functions that execute in order, each calling `next()` to pass control to the next one:

```typescript
import express, { Request, Response, NextFunction, RequestHandler } from 'express';

const app = express();
app.use(express.json());

// 1. Reusable auth middleware
function authenticate(req: Request, res: Response, next: NextFunction) {
  const token = req.headers.authorization?.replace('Bearer ', '');
  if (!token) return res.status(401).json({ error: 'No token provided' });

  try {
    const user = verifyJWT(token);
    (req as any).user = user;
    next(); // Pass to next middleware
  } catch {
    res.status(401).json({ error: 'Invalid token' });
  }
}

// 2. Role-based authorization (middleware factory)
function requireRole(...roles: string[]): RequestHandler {
  return (req, res, next) => {
    const user = (req as any).user;
    if (!roles.includes(user.role)) {
      return res.status(403).json({ error: 'Insufficient permissions' });
    }
    next();
  };
}

// 3. Validation middleware factory
function validate(schema: ZodSchema): RequestHandler {
  return (req, res, next) => {
    const result = schema.safeParse(req.body);
    if (!result.success) {
      return res.status(400).json({
        error: 'Validation failed',
        details: result.error.flatten(),
      });
    }
    req.body = result.data; // Replace with parsed/typed data
    next();
  };
}

// 4. Async wrapper (Express doesn't catch async errors natively)
function asyncHandler(fn: (req: Request, res: Response, next: NextFunction) => Promise<any>): RequestHandler {
  return (req, res, next) => {
    fn(req, res, next).catch(next); // Forward errors to error middleware
  };
}

// 5. Chain middleware on routes
const createUserSchema = z.object({
  name: z.string().min(1),
  email: z.string().email(),
  role: z.enum(['user', 'admin']),
});

app.post(
  '/api/users',
  authenticate,                      // 1st: check auth
  requireRole('admin'),              // 2nd: check permissions
  validate(createUserSchema),        // 3rd: validate body
  asyncHandler(async (req, res) => { // 4th: handle request
    const user = await db.createUser(req.body);
    res.status(201).json(user);
  })
);

// 6. Error handling middleware (MUST have 4 parameters)
app.use((err: Error, req: Request, res: Response, next: NextFunction) => {
  console.error(err.stack);

  if (err.name === 'ValidationError') {
    return res.status(400).json({ error: err.message });
  }

  res.status(500).json({
    error: process.env.NODE_ENV === 'production'
      ? 'Internal server error'
      : err.message,
  });
});

app.listen(3000);
```

Execution flow: `authenticate` -> `requireRole` -> `validate` -> handler. If any middleware doesn't call `next()` (e.g., returns a 401), the chain stops. Errors passed to `next(err)` skip to the 4-parameter error middleware.'''
    ),
    (
        "javascript/fastify-plugin-architecture",
        r'''How does Fastify's plugin system work? I want to structure my API with encapsulated plugins that have their own routes, hooks, and decorators.''',
        r'''<think>
Fastify's plugin architecture is its killer feature — encapsulation via context inheritance.
Plugins create their own scope, decorators and hooks registered inside don't leak out.
I should show fastify-plugin for shared plugins vs scoped plugins, registering routes
inside plugins, and the encapsulation model. Also show TypeScript declaration merging
for type-safe decorators.
</think>

Fastify's plugin system uses encapsulation — each plugin gets its own scope for hooks, decorators, and routes:

```typescript
import Fastify, { FastifyInstance, FastifyPluginAsync } from 'fastify';
import fp from 'fastify-plugin';

const app = Fastify({ logger: true });

// 1. Shared plugin (breaks encapsulation — available to siblings/children)
// Use fastify-plugin (fp) when you want to decorate the parent scope
const dbPlugin: FastifyPluginAsync<{ connectionString: string }> = async (fastify, opts) => {
  const pool = createPool(opts.connectionString);

  // Decorate the instance — accessible in all routes
  fastify.decorate('db', pool);

  // Cleanup on shutdown
  fastify.addHook('onClose', async () => {
    await pool.end();
  });
};

// fp() breaks encapsulation — db is available to ALL plugins registered after this
app.register(fp(dbPlugin), { connectionString: 'postgres://...' });

// 2. Scoped plugin (encapsulated — hooks and decorators stay inside)
const userRoutes: FastifyPluginAsync = async (fastify) => {
  // This hook only runs for routes inside THIS plugin
  fastify.addHook('onRequest', async (request) => {
    const token = request.headers.authorization;
    if (!token) throw fastify.httpErrors.unauthorized();
    request.user = verifyToken(token);
  });

  fastify.get('/users', async (request) => {
    return fastify.db.query('SELECT * FROM users');
  });

  fastify.get('/users/:id', async (request) => {
    const { id } = request.params as { id: string };
    return fastify.db.query('SELECT * FROM users WHERE id = $1', [id]);
  });

  fastify.post('/users', {
    schema: {
      body: {
        type: 'object',
        required: ['name', 'email'],
        properties: {
          name: { type: 'string' },
          email: { type: 'string', format: 'email' },
        },
      },
    },
  }, async (request) => {
    const { name, email } = request.body as { name: string; email: string };
    return fastify.db.query('INSERT INTO users (name, email) VALUES ($1, $2) RETURNING *', [name, email]);
  });
};

// 3. Register scoped plugins with prefixes
app.register(userRoutes, { prefix: '/api/v1' });
app.register(orderRoutes, { prefix: '/api/v1' });

// 4. TypeScript: declare your decorators for type safety
declare module 'fastify' {
  interface FastifyInstance {
    db: Pool;
  }
  interface FastifyRequest {
    user: { id: string; role: string };
  }
}

// 5. Plugin composition — plugins can register sub-plugins
const apiPlugin: FastifyPluginAsync = async (fastify) => {
  fastify.register(fp(authPlugin));  // Shared within this scope
  fastify.register(userRoutes);      // Gets access to authPlugin
  fastify.register(orderRoutes);     // Gets access to authPlugin
};

app.register(apiPlugin, { prefix: '/api' });

await app.listen({ port: 3000 });
```

Key concept: without `fp()`, plugins are **encapsulated** — their decorators and hooks don't leak to siblings. Use `fp()` only for shared infrastructure (db, auth, config). Keep route plugins scoped.'''
    ),
    (
        "javascript/websocket-server-ws-library",
        r'''How do I build a WebSocket server in Node.js using the ws library? I need rooms, broadcasting, and heartbeat to detect dead connections.''',
        r'''<think>
The ws library is the standard WebSocket implementation for Node.js. I should show server
setup, room management using a Map, broadcasting to room members, heartbeat/ping-pong
for detecting dead connections, and typed message handling. This is an advanced topic
so I'll include a fairly complete implementation.
</think>

Here's a WebSocket server with rooms, broadcasting, and heartbeat using `ws`:

```typescript
import { WebSocketServer, WebSocket } from 'ws';
import { createServer } from 'http';

interface ExtendedWS extends WebSocket {
  isAlive: boolean;
  userId: string;
  rooms: Set<string>;
}

interface Message {
  type: 'join' | 'leave' | 'broadcast' | 'direct';
  room?: string;
  to?: string;
  payload: unknown;
}

const server = createServer();
const wss = new WebSocketServer({ server });

// Room management
const rooms = new Map<string, Set<ExtendedWS>>();
const clients = new Map<string, ExtendedWS>();

function joinRoom(ws: ExtendedWS, room: string) {
  if (!rooms.has(room)) rooms.set(room, new Set());
  rooms.get(room)!.add(ws);
  ws.rooms.add(room);
}

function leaveRoom(ws: ExtendedWS, room: string) {
  rooms.get(room)?.delete(ws);
  if (rooms.get(room)?.size === 0) rooms.delete(room);
  ws.rooms.delete(room);
}

function broadcastToRoom(room: string, data: unknown, exclude?: ExtendedWS) {
  const members = rooms.get(room);
  if (!members) return;

  const message = JSON.stringify(data);
  for (const client of members) {
    if (client !== exclude && client.readyState === WebSocket.OPEN) {
      client.send(message);
    }
  }
}

// Connection handling
wss.on('connection', (socket: WebSocket, req) => {
  const ws = socket as ExtendedWS;
  const userId = new URL(req.url!, `http://${req.headers.host}`).searchParams.get('userId') ?? crypto.randomUUID();

  ws.isAlive = true;
  ws.userId = userId;
  ws.rooms = new Set();
  clients.set(userId, ws);

  ws.on('pong', () => { ws.isAlive = true; });

  ws.on('message', (raw) => {
    try {
      const msg: Message = JSON.parse(raw.toString());

      switch (msg.type) {
        case 'join':
          if (msg.room) {
            joinRoom(ws, msg.room);
            broadcastToRoom(msg.room, { type: 'system', text: `${userId} joined` }, ws);
          }
          break;

        case 'leave':
          if (msg.room) leaveRoom(ws, msg.room);
          break;

        case 'broadcast':
          if (msg.room) {
            broadcastToRoom(msg.room, { type: 'message', from: userId, payload: msg.payload }, ws);
          }
          break;

        case 'direct':
          if (msg.to) {
            const target = clients.get(msg.to);
            if (target?.readyState === WebSocket.OPEN) {
              target.send(JSON.stringify({ type: 'direct', from: userId, payload: msg.payload }));
            }
          }
          break;
      }
    } catch (e) {
      ws.send(JSON.stringify({ type: 'error', message: 'Invalid message format' }));
    }
  });

  ws.on('close', () => {
    for (const room of ws.rooms) {
      leaveRoom(ws, room);
      broadcastToRoom(room, { type: 'system', text: `${userId} left` });
    }
    clients.delete(userId);
  });
});

// Heartbeat: detect dead connections every 30 seconds
const heartbeat = setInterval(() => {
  for (const ws of wss.clients as Set<ExtendedWS>) {
    if (!ws.isAlive) return ws.terminate();
    ws.isAlive = false;
    ws.ping();
  }
}, 30_000);

wss.on('close', () => clearInterval(heartbeat));

server.listen(8080, () => console.log('WS server on :8080'));
```

The heartbeat loop pings all clients every 30s. If a client doesn't respond with a pong before the next cycle, it's terminated. This catches connections that die silently (e.g., network disconnect without TCP FIN).'''
    ),
    (
        "javascript/event-driven-architecture-eventemitter",
        r'''How do I build an event-driven architecture in Node.js using EventEmitter? I want typed events and a clean decoupled design.''',
        r'''<think>
EventEmitter is Node's built-in pub/sub mechanism. For typed events in TypeScript, I
should show the typed EventEmitter pattern (either the generic approach or declaration
merging). I'll demonstrate a practical event-driven architecture with domain events,
decoupled handlers, and error handling. Show both the class extension and composition
approaches.
</think>

Here's a typed event-driven architecture using Node's `EventEmitter`:

```typescript
import { EventEmitter } from 'events';

// 1. Define typed events
interface AppEvents {
  'user:created': [user: User];
  'user:updated': [user: User, changes: Partial<User>];
  'order:placed': [order: Order];
  'order:shipped': [orderId: string, trackingNumber: string];
  'error': [error: Error, context: string];
}

// 2. Typed EventEmitter wrapper
class TypedEmitter<T extends Record<string, any[]>> {
  private emitter = new EventEmitter();

  on<K extends keyof T & string>(event: K, listener: (...args: T[K]) => void): this {
    this.emitter.on(event, listener as any);
    return this;
  }

  emit<K extends keyof T & string>(event: K, ...args: T[K]): boolean {
    return this.emitter.emit(event, ...args);
  }

  off<K extends keyof T & string>(event: K, listener: (...args: T[K]) => void): this {
    this.emitter.off(event, listener as any);
    return this;
  }

  once<K extends keyof T & string>(event: K, listener: (...args: T[K]) => void): this {
    this.emitter.once(event, listener as any);
    return this;
  }
}

// 3. Application event bus
const eventBus = new TypedEmitter<AppEvents>();

// 4. Decoupled handlers — each module subscribes independently
// Email service
eventBus.on('user:created', (user) => {
  sendWelcomeEmail(user.email, user.name);
  console.log(`Welcome email sent to ${user.email}`);
});

// Analytics service
eventBus.on('user:created', (user) => {
  trackEvent('signup', { userId: user.id, source: user.referralSource });
});

// Inventory service
eventBus.on('order:placed', (order) => {
  for (const item of order.items) {
    decrementStock(item.productId, item.quantity);
  }
});

// Notification service
eventBus.on('order:shipped', (orderId, trackingNumber) => {
  notifyCustomer(orderId, `Your order has shipped! Tracking: ${trackingNumber}`);
});

// 5. Domain service emits events (doesn't know about handlers)
class UserService {
  constructor(private bus: TypedEmitter<AppEvents>) {}

  async createUser(data: CreateUserInput): Promise<User> {
    const user = await db.insert('users', data);
    this.bus.emit('user:created', user);   // Fire and forget
    return user;
  }

  async updateUser(id: string, changes: Partial<User>): Promise<User> {
    const user = await db.update('users', id, changes);
    this.bus.emit('user:updated', user, changes);
    return user;
  }
}

// 6. Error handling for event handlers
eventBus.on('error', (error, context) => {
  console.error(`Event error in ${context}:`, error);
  // Send to error tracking service
});

// Wrap handlers to catch async errors
function safeHandler<Args extends any[]>(
  context: string,
  handler: (...args: Args) => Promise<void> | void
): (...args: Args) => void {
  return (...args) => {
    try {
      const result = handler(...args);
      if (result instanceof Promise) {
        result.catch((err) => eventBus.emit('error', err, context));
      }
    } catch (err) {
      eventBus.emit('error', err as Error, context);
    }
  };
}

eventBus.on('order:placed', safeHandler('inventory', async (order) => {
  await updateInventory(order);
}));
```

Benefits: services are decoupled (UserService doesn't import EmailService), handlers can be added/removed without modifying the emitter, and the typed wrapper gives you autocomplete on event names and payload types.'''
    ),
]
