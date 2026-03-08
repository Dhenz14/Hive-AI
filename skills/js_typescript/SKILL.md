# JavaScript & TypeScript Patterns

## Async/Await
```typescript
// Always wrap await in try/catch or use .catch()
async function fetchData(url: string): Promise<Data> {
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  } catch (err) {
    throw err instanceof Error ? err : new Error(String(err));
  }
}

// Parallel execution (don't await sequentially!)
const [users, posts] = await Promise.all([fetchUsers(), fetchPosts()]);

// Race condition guard — stale closure over ID
function useLatest(fn: () => Promise<void>) {
  let id = 0;
  return async () => {
    const thisId = ++id;
    await fn();
    if (thisId !== id) return; // Stale — discard
  };
}
```

## TypeScript Generics
```typescript
// Constraints
function getProperty<T, K extends keyof T>(obj: T, key: K): T[K] {
  return obj[key];
}

// Mapped types — make all properties optional & nullable
type Partial<T> = { [K in keyof T]?: T[K] };
type Nullable<T> = { [K in keyof T]: T[K] | null };

// Conditional types
type Unwrap<T> = T extends Promise<infer U> ? U : T;
type IsString<T> = T extends string ? true : false;
```

## Closures & Factories
```typescript
// Module pattern (encapsulate state)
function createCounter(initial = 0) {
  let count = initial;
  return {
    inc: () => ++count,
    dec: () => --count,
    get: () => count,
  };
}

// Memoize any function
function memoize<T extends (...args: any[]) => any>(fn: T): T {
  const cache = new Map<string, ReturnType<T>>();
  return ((...args: any[]) => {
    const key = JSON.stringify(args);
    if (!cache.has(key)) cache.set(key, fn(...args));
    return cache.get(key)!;
  }) as T;
}

// Currying
const add = (a: number) => (b: number) => a + b;
const add5 = add(5); // add5(3) => 8
```

## Promises
```typescript
// Promise.all — fails fast on first rejection
const results = await Promise.all(urls.map(u => fetch(u)));

// Promise.allSettled — never rejects, returns status per item
const outcomes = await Promise.allSettled(tasks);
const successes = outcomes.filter(o => o.status === "fulfilled");
const failures = outcomes.filter(o => o.status === "rejected");

// Promise.race — first to settle wins (timeout pattern)
const result = await Promise.race([
  fetchData(url),
  new Promise((_, reject) => setTimeout(() => reject(new Error("timeout")), 5000)),
]);

// Promisify callback-style function
import { promisify } from "node:util";
const readFile = promisify(fs.readFile);
```

## Error Handling
```typescript
// Custom error with cause chaining (ES2022)
class AppError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "AppError";
  }
}
throw new AppError("fetch failed", { cause: originalError });

// Result pattern (no exceptions)
type Result<T, E = Error> = { ok: true; value: T } | { ok: false; error: E };

function safeParse<T>(json: string): Result<T> {
  try {
    return { ok: true, value: JSON.parse(json) };
  } catch (e) {
    return { ok: false, error: e instanceof Error ? e : new Error(String(e)) };
  }
}
```

## Proxy & Reflect
```typescript
// Validation proxy
function validated<T extends object>(target: T, validator: (k: string, v: any) => boolean): T {
  return new Proxy(target, {
    set(obj, prop, value) {
      if (!validator(String(prop), value)) throw new TypeError(`Invalid: ${String(prop)}`);
      return Reflect.set(obj, prop, value);
    },
  });
}

// Lazy loading / virtual properties
const lazy = new Proxy({} as Record<string, any>, {
  get(cache, prop: string) {
    if (!(prop in cache)) cache[prop] = expensiveCompute(prop);
    return cache[prop];
  },
});
```

## Key Gotchas
- **`this` binding**: Arrow functions capture `this` lexically. Class methods need `bind` or arrow syntax to pass as callbacks.
- **Event loop**: Microtasks (Promise, queueMicrotask) run before macrotasks (setTimeout, I/O). `await` yields to the microtask queue.
- **== vs ===**: Always use `===`. `==` coerces: `0 == "" // true`, `null == undefined // true`.
- **Prototype chain**: `Object.create(null)` for clean dictionaries. `hasOwnProperty` vs `in` (includes inherited).
- **Closure over loop var**: `var` in loops shares one binding. Use `let` (block-scoped) or `.forEach()`.
- **Floating point**: `0.1 + 0.2 !== 0.3`. Use `Math.abs(a - b) < Number.EPSILON` or integer cents.
- **Import order**: ESM is statically analyzed; circular imports resolve to `undefined` for uninitialized bindings.
