"""Async/concurrency training pairs: JavaScript async patterns."""

pairs = [
    {
        "instruction": r'''What is the difference between Promise.all(), Promise.allSettled(), Promise.race(), and Promise.any() in JavaScript? When should I use each one?''',
        "output": r'''<think>
These four Promise combinators each have different failure semantics:

- Promise.all() -- resolves when ALL promises resolve; rejects on the FIRST rejection
- Promise.allSettled() -- waits for ALL promises to settle (resolve or reject); never rejects
- Promise.race() -- resolves/rejects with the FIRST promise to settle (whether resolve or reject)
- Promise.any() -- resolves with the FIRST promise to resolve; rejects only if ALL reject (AggregateError)

Hmm, the tricky one is the difference between race() and any(). race() returns the first settled promise regardless of outcome, while any() returns the first successful one. So if the first promise to settle is a rejection, race() rejects but any() keeps waiting for a success.

I should show practical use cases for each one to make the differences clear.
</think>

The four Promise combinators differ in how they handle multiple promises:

```javascript
// Setup: helper functions
const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function fetchFast() {
  await delay(100);
  return { source: "fast", data: "quick result" };
}

async function fetchSlow() {
  await delay(500);
  return { source: "slow", data: "thorough result" };
}

async function fetchFlaky() {
  await delay(200);
  throw new Error("Service unavailable");
}

// ============================================================
// Promise.all() -- ALL must succeed
// ============================================================
// Use case: fetching multiple resources that are ALL required

async function loadDashboard(userId) {
  try {
    const [user, orders, prefs] = await Promise.all([
      fetchUser(userId),
      fetchOrders(userId),
      fetchPreferences(userId),
    ]);
    // All three succeeded
    return { user, orders, prefs };
  } catch (err) {
    // First failure cancels everything (conceptually)
    console.error("Dashboard failed:", err.message);
  }
}

// ============================================================
// Promise.allSettled() -- wait for ALL, tolerate failures
// ============================================================
// Use case: best-effort fetching, partial results OK

async function loadDashboardBestEffort(userId) {
  const results = await Promise.allSettled([
    fetchUser(userId),
    fetchOrders(userId),
    fetchFlaky(),  // this will fail
  ]);

  // results is an array of {status, value} or {status, reason}
  const data = {};
  results.forEach((result, i) => {
    if (result.status === "fulfilled") {
      data[i] = result.value;
    } else {
      console.warn(`Source ${i} failed: ${result.reason.message}`);
    }
  });
  return data;
}

// ============================================================
// Promise.race() -- first to settle wins (success OR failure)
// ============================================================
// Use case: timeout implementation

function withTimeout(promise, ms) {
  const timeout = new Promise((_, reject) =>
    setTimeout(() => reject(new Error(`Timeout after ${ms}ms`)), ms)
  );
  return Promise.race([promise, timeout]);
}

async function fetchWithTimeout() {
  try {
    const result = await withTimeout(fetchSlow(), 200);
    return result;
  } catch (err) {
    console.error(err.message);  // "Timeout after 200ms"
  }
}

// ============================================================
// Promise.any() -- first to SUCCEED wins
// ============================================================
// Use case: redundant sources, take fastest success

async function fetchFromMirrors(resourceId) {
  try {
    const result = await Promise.any([
      fetchFromMirror1(resourceId),
      fetchFromMirror2(resourceId),
      fetchFromMirror3(resourceId),
    ]);
    // First successful response wins
    return result;
  } catch (err) {
    // AggregateError -- ALL mirrors failed
    console.error("All mirrors failed:");
    err.errors.forEach((e) => console.error(" -", e.message));
  }
}

// Helper stubs
async function fetchUser(id) { return { id, name: "Alice" }; }
async function fetchOrders(id) { return [{ orderId: 1 }]; }
async function fetchPreferences(id) { return { theme: "dark" }; }
async function fetchFromMirror1(id) { return { mirror: 1 }; }
async function fetchFromMirror2(id) { throw new Error("down"); }
async function fetchFromMirror3(id) { return { mirror: 3 }; }
```

Summary table:
- `Promise.all` -- all must succeed, fails fast on first error
- `Promise.allSettled` -- waits for all, never rejects, returns status objects
- `Promise.race` -- first to settle (success or failure) wins
- `Promise.any` -- first to succeed wins, rejects only if all fail'''
    },
    {
        "instruction": r'''How do I use AbortController in JavaScript to cancel async operations like fetch requests?''',
        "output": r'''<think>
AbortController is the standard way to cancel fetch requests and other async operations in JavaScript. It works with the Fetch API, some Node.js APIs, and custom code.

The key parts:
1. Create an AbortController
2. Pass controller.signal to the operation
3. Call controller.abort() to cancel

One thing I should mention -- AbortController can only be used once. Once you call abort(), that signal is permanently aborted. You need a new controller for new operations.

Also worth showing: using AbortSignal.timeout() (newer API) for simple timeouts, and how to make custom functions support AbortSignal.
</think>

`AbortController` provides a standard way to cancel async operations:

```javascript
// ============================================================
// Basic: Cancel a fetch request
// ============================================================

async function fetchWithCancel(url) {
  const controller = new AbortController();

  // Cancel after 5 seconds
  const timeoutId = setTimeout(() => controller.abort(), 5000);

  try {
    const response = await fetch(url, {
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    return await response.json();
  } catch (err) {
    if (err.name === "AbortError") {
      console.log("Request was cancelled");
      return null;
    }
    throw err; // Re-throw non-abort errors
  }
}

// ============================================================
// AbortSignal.timeout() -- simpler timeout (modern browsers)
// ============================================================

async function fetchWithTimeout(url, ms = 5000) {
  try {
    const response = await fetch(url, {
      signal: AbortSignal.timeout(ms),
    });
    return await response.json();
  } catch (err) {
    if (err.name === "TimeoutError") {
      console.log("Request timed out");
      return null;
    }
    throw err;
  }
}

// ============================================================
// Cancel multiple operations with one controller
// ============================================================

async function fetchDashboard() {
  const controller = new AbortController();

  try {
    const [user, posts, notifications] = await Promise.all([
      fetch("/api/user", { signal: controller.signal }),
      fetch("/api/posts", { signal: controller.signal }),
      fetch("/api/notifications", { signal: controller.signal }),
    ]);
    return {
      user: await user.json(),
      posts: await posts.json(),
      notifications: await notifications.json(),
    };
  } catch (err) {
    // If any fetch fails, cancel the others
    controller.abort();
    throw err;
  }
}

// ============================================================
// React pattern: cancel on unmount
// ============================================================

function useUserData(userId) {
  const [data, setData] = React.useState(null);
  const [error, setError] = React.useState(null);

  React.useEffect(() => {
    const controller = new AbortController();

    fetch(`/api/users/${userId}`, { signal: controller.signal })
      .then((res) => res.json())
      .then((json) => setData(json))
      .catch((err) => {
        if (err.name !== "AbortError") {
          setError(err);
        }
      });

    // Cleanup: cancel if component unmounts or userId changes
    return () => controller.abort();
  }, [userId]);

  return { data, error };
}

// ============================================================
// Make custom async functions support AbortSignal
// ============================================================

async function processLargeDataset(items, signal) {
  const results = [];

  for (let i = 0; i < items.length; i++) {
    // Check if cancelled before each chunk of work
    if (signal?.aborted) {
      throw new DOMException("Processing cancelled", "AbortError");
    }

    // Process item (async to avoid blocking)
    await new Promise((resolve) => setTimeout(resolve, 0));
    results.push(transform(items[i]));

    // Also listen for abort during async waits
    if (i % 100 === 0) {
      await new Promise((resolve, reject) => {
        if (signal?.aborted) {
          reject(new DOMException("Cancelled", "AbortError"));
          return;
        }
        signal?.addEventListener("abort", () => {
          reject(new DOMException("Cancelled", "AbortError"));
        }, { once: true });
        setTimeout(resolve, 0);
      });
    }
  }
  return results;
}

function transform(item) {
  return { ...item, processed: true };
}

// Usage
async function main() {
  const controller = new AbortController();

  // Cancel after 2 seconds
  setTimeout(() => controller.abort(), 2000);

  try {
    const results = await processLargeDataset(
      Array.from({ length: 10000 }, (_, i) => ({ id: i })),
      controller.signal
    );
  } catch (err) {
    if (err.name === "AbortError") {
      console.log("Processing was cancelled");
    }
  }
}
```

Key points:
- Each `AbortController` is single-use -- create a new one per cancellable operation
- Always check `err.name === "AbortError"` to distinguish cancellation from real errors
- Use `AbortSignal.timeout(ms)` for simple timeout-only cases
- In React, abort in the useEffect cleanup function'''
    },
    {
        "instruction": r'''Show me how to implement async iterators and the for-await-of pattern in JavaScript.''',
        "output": r'''```javascript
// ============================================================
// Basic async iterator using Symbol.asyncIterator
// ============================================================

class AsyncRange {
  constructor(start, end, delayMs = 100) {
    this.start = start;
    this.end = end;
    this.delayMs = delayMs;
  }

  [Symbol.asyncIterator]() {
    let current = this.start;
    const end = this.end;
    const delayMs = this.delayMs;

    return {
      async next() {
        if (current >= end) {
          return { done: true, value: undefined };
        }
        await new Promise((r) => setTimeout(r, delayMs));
        return { done: false, value: current++ };
      },
    };
  }
}

// Usage
async function demo() {
  for await (const num of new AsyncRange(0, 5, 50)) {
    console.log(num); // 0, 1, 2, 3, 4
  }
}

// ============================================================
// Async generator function (simpler syntax)
// ============================================================

async function* paginate(url, pageSize = 10) {
  let page = 1;
  let hasMore = true;

  while (hasMore) {
    const response = await fetch(
      `${url}?page=${page}&size=${pageSize}`
    );
    const data = await response.json();

    yield data.items;

    hasMore = data.items.length === pageSize;
    page++;
  }
}

async function getAllItems() {
  const allItems = [];
  for await (const pageItems of paginate("/api/products")) {
    allItems.push(...pageItems);
    console.log(`Loaded ${allItems.length} items so far`);
  }
  return allItems;
}

// ============================================================
// Async generator: SSE (Server-Sent Events) stream
// ============================================================

async function* streamSSE(url, signal) {
  const response = await fetch(url, { signal });
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const data = line.slice(6);
          if (data === "[DONE]") return;
          yield JSON.parse(data);
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// Usage
async function consumeStream() {
  const controller = new AbortController();
  setTimeout(() => controller.abort(), 30000);

  for await (const event of streamSSE("/api/events", controller.signal)) {
    console.log("Event:", event);
    if (event.type === "complete") break;
  }
}

// ============================================================
// Utility: transform async iterables
// ============================================================

async function* map(iterable, fn) {
  for await (const item of iterable) {
    yield fn(item);
  }
}

async function* filter(iterable, predicate) {
  for await (const item of iterable) {
    if (predicate(item)) {
      yield item;
    }
  }
}

async function* take(iterable, count) {
  let taken = 0;
  for await (const item of iterable) {
    yield item;
    taken++;
    if (taken >= count) return;
  }
}

// Compose: get first 3 even numbers from async range
async function composedExample() {
  const source = new AsyncRange(0, 100, 10);
  const evens = filter(source, (n) => n % 2 === 0);
  const firstThree = take(evens, 3);

  const results = [];
  for await (const n of firstThree) {
    results.push(n);
  }
  console.log(results); // [0, 2, 4]
}

// ============================================================
// Node.js: reading file line by line (async iterator)
// ============================================================

// const fs = require("fs");
// const readline = require("readline");
//
// async function* readLines(filePath) {
//   const stream = fs.createReadStream(filePath);
//   const rl = readline.createInterface({ input: stream });
//   for await (const line of rl) {
//     yield line;
//   }
// }
//
// async function processLog() {
//   for await (const line of readLines("app.log")) {
//     if (line.includes("ERROR")) {
//       console.log(line);
//     }
//   }
// }
```

Key points:
- Implement `[Symbol.asyncIterator]()` for class-based iterators
- Use `async function*` for simpler async generators
- `for await...of` consumes any async iterable
- Async generators are lazy -- they only compute values when requested
- Compose with utility functions like `map`, `filter`, `take`'''
    },
    {
        "instruction": r'''How do I use Worker Threads in Node.js for CPU-intensive tasks without blocking the main event loop?''',
        "output": r'''```javascript
// ============================================================
// main.js -- using worker_threads for CPU-bound work
// ============================================================

const {
  Worker,
  isMainThread,
  parentPort,
  workerData,
} = require("worker_threads");
const os = require("os");

// ============================================================
// Pattern 1: Simple one-shot worker
// ============================================================

function runInWorker(workerFile, data) {
  return new Promise((resolve, reject) => {
    const worker = new Worker(workerFile, { workerData: data });
    worker.on("message", resolve);
    worker.on("error", reject);
    worker.on("exit", (code) => {
      if (code !== 0) {
        reject(new Error(`Worker exited with code ${code}`));
      }
    });
  });
}

// worker_hash.js -- the worker script
// const { parentPort, workerData } = require("worker_threads");
// const crypto = require("crypto");
//
// const hash = crypto
//   .pbkdf2Sync(workerData.password, workerData.salt, 100000, 64, "sha512")
//   .toString("hex");
//
// parentPort.postMessage({ hash });

// ============================================================
// Pattern 2: Worker pool for reusable workers
// ============================================================

class WorkerPool {
  constructor(workerFile, poolSize) {
    this.workerFile = workerFile;
    this.poolSize = poolSize || os.cpus().length;
    this.workers = [];
    this.queue = [];
    this.activeWorkers = new Map();

    for (let i = 0; i < this.poolSize; i++) {
      this._addWorker();
    }
  }

  _addWorker() {
    const worker = new Worker(this.workerFile);
    worker.on("message", (result) => {
      const callback = this.activeWorkers.get(worker);
      this.activeWorkers.delete(worker);
      callback.resolve(result);
      this._processQueue();
    });
    worker.on("error", (err) => {
      const callback = this.activeWorkers.get(worker);
      if (callback) {
        this.activeWorkers.delete(worker);
        callback.reject(err);
      }
    });
    this.workers.push(worker);
  }

  _processQueue() {
    if (this.queue.length === 0) return;

    const available = this.workers.find(
      (w) => !this.activeWorkers.has(w)
    );
    if (!available) return;

    const { data, resolve, reject } = this.queue.shift();
    this.activeWorkers.set(available, { resolve, reject });
    available.postMessage(data);
  }

  execute(data) {
    return new Promise((resolve, reject) => {
      this.queue.push({ data, resolve, reject });
      this._processQueue();
    });
  }

  async shutdown() {
    const exits = this.workers.map(
      (w) => new Promise((resolve) => {
        w.on("exit", resolve);
        w.terminate();
      })
    );
    await Promise.all(exits);
  }
}

// ============================================================
// Pattern 3: Inline worker with eval (no separate file)
// ============================================================

function createInlineWorker(fn) {
  const code = `
    const { parentPort } = require("worker_threads");
    const fn = ${fn.toString()};
    parentPort.on("message", async (data) => {
      try {
        const result = await fn(data);
        parentPort.postMessage({ result });
      } catch (err) {
        parentPort.postMessage({ error: err.message });
      }
    });
  `;
  return new Worker(code, { eval: true });
}

// ============================================================
// Usage example
// ============================================================

async function main() {
  // One-shot worker
  // const hashResult = await runInWorker("./worker_hash.js", {
  //   password: "secret",
  //   salt: "random-salt",
  // });

  // Worker pool
  // const pool = new WorkerPool("./worker_compute.js", 4);
  // const results = await Promise.all(
  //   Array.from({ length: 20 }, (_, i) =>
  //     pool.execute({ taskId: i, input: i * 100 })
  //   )
  // );
  // console.log("All tasks done:", results.length);
  // await pool.shutdown();

  // Inline worker
  const worker = createInlineWorker((data) => {
    let sum = 0;
    for (let i = 0; i < data.iterations; i++) {
      sum += Math.sqrt(i);
    }
    return { sum, iterations: data.iterations };
  });

  const result = await new Promise((resolve) => {
    worker.on("message", (msg) => {
      resolve(msg.result);
      worker.terminate();
    });
    worker.postMessage({ iterations: 10_000_000 });
  });

  console.log("Computed:", result);
}

main().catch(console.error);
```

Key points:
- Worker threads run JavaScript in separate threads with their own V8 isolate
- Use for CPU-bound work (hashing, compression, parsing large JSON)
- A worker pool reuses workers to avoid the overhead of creating new threads
- Data is copied between threads (structured clone), not shared
- For shared memory, use `SharedArrayBuffer` and `Atomics`'''
    },
    {
        "instruction": r'''Explain JavaScript async/await error handling patterns. What are the best practices for handling errors in async code?''',
        "output": r'''```javascript
// ============================================================
// Pattern 1: try/catch with await (most common)
// ============================================================

async function fetchUserProfile(userId) {
  try {
    const response = await fetch(`/api/users/${userId}`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const user = await response.json();
    return user;
  } catch (err) {
    if (err.name === "AbortError") {
      console.log("Request cancelled");
      return null;
    }
    console.error("Failed to fetch user:", err.message);
    throw err; // Re-throw if caller should handle it
  }
}

// ============================================================
// Pattern 2: Go-style [error, result] tuple
// ============================================================

async function to(promise) {
  try {
    const result = await promise;
    return [null, result];
  } catch (err) {
    return [err, null];
  }
}

async function processOrder(orderId) {
  const [fetchErr, order] = await to(fetchOrder(orderId));
  if (fetchErr) {
    console.error("Could not fetch order:", fetchErr.message);
    return;
  }

  const [payErr, payment] = await to(processPayment(order));
  if (payErr) {
    console.error("Payment failed:", payErr.message);
    await rollbackOrder(orderId);
    return;
  }

  const [shipErr, shipment] = await to(createShipment(order));
  if (shipErr) {
    console.error("Shipment failed:", shipErr.message);
    await refundPayment(payment.id);
    return;
  }

  return { order, payment, shipment };
}

// ============================================================
// Pattern 3: Error boundaries for async operations
// ============================================================

class AsyncOperation {
  constructor(name) {
    this.name = name;
    this.retries = 0;
    this.maxRetries = 3;
  }

  async execute(fn) {
    for (let attempt = 1; attempt <= this.maxRetries; attempt++) {
      try {
        return await fn();
      } catch (err) {
        this.retries = attempt;
        if (attempt === this.maxRetries) {
          console.error(
            `${this.name} failed after ${this.maxRetries} attempts:`,
            err.message
          );
          throw err;
        }
        const delay = Math.min(1000 * Math.pow(2, attempt), 10000);
        console.warn(
          `${this.name} attempt ${attempt} failed, ` +
          `retrying in ${delay}ms`
        );
        await new Promise((r) => setTimeout(r, delay));
      }
    }
  }
}

// ============================================================
// Pattern 4: Promise.allSettled for partial failure tolerance
// ============================================================

async function loadDashboard(userId) {
  const results = await Promise.allSettled([
    fetchUserProfile(userId),
    fetchOrders(userId),
    fetchNotifications(userId),
  ]);

  return {
    user: results[0].status === "fulfilled" ? results[0].value : null,
    orders: results[1].status === "fulfilled" ? results[1].value : [],
    notifications: results[2].status === "fulfilled"
      ? results[2].value
      : [],
    errors: results
      .filter((r) => r.status === "rejected")
      .map((r) => r.reason.message),
  };
}

// ============================================================
// Safety net: catch unhandled rejections globally
// ============================================================

// Browser
window.addEventListener("unhandledrejection", (event) => {
  console.error("Unhandled rejection:", event.reason);
  event.preventDefault(); // prevent default logging
  // Send to error tracking service
});

// Node.js
// process.on("unhandledRejection", (reason, promise) => {
//   console.error("Unhandled rejection at:", promise, "reason:", reason);
// });

// ============================================================
// Common mistake: forgetting to await
// ============================================================

async function buggyCode() {
  try {
    // BUG: missing await! Error is NOT caught by try/catch
    // fetchUserProfile(42);

    // CORRECT: await the promise
    await fetchUserProfile(42);
  } catch (err) {
    console.error(err);
  }
}

// Stubs
async function fetchOrder(id) { return { id, total: 100 }; }
async function processPayment(order) { return { id: "pay_1" }; }
async function createShipment(order) { return { id: "ship_1" }; }
async function rollbackOrder(id) {}
async function refundPayment(id) {}
async function fetchOrders(id) { return []; }
async function fetchNotifications(id) { return []; }
```

Best practices summary:
- Always `await` promises inside try/catch blocks
- Use the `[error, result]` tuple pattern for sequential fallible operations
- Use `Promise.allSettled()` when partial failure is acceptable
- Add a global `unhandledrejection` handler as a safety net
- Retry transient errors with exponential backoff'''
    },
]
