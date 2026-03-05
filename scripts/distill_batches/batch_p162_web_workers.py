"""Web Workers and SharedArrayBuffer."""

PAIRS = [
    (
        "frontend/web-workers-dedicated-shared",
        "Demonstrate Web Workers including dedicated workers, shared workers, and transferable objects for off-main-thread computation.",
        '''Web Workers run JavaScript on background threads, keeping the main thread responsive. Dedicated workers serve a single page, shared workers serve multiple tabs, and transferable objects enable zero-copy data passing.

```typescript
// --- Dedicated Worker (most common) ---

// main.ts — spawning a dedicated worker
const worker = new Worker(
  new URL('./heavy-worker.ts', import.meta.url),
  { type: 'module' }
);

// Type-safe messaging
interface WorkerRequest {
  type: 'PROCESS_DATA';
  payload: { data: number[]; chunkSize: number };
  id: string;
}

interface WorkerResponse {
  type: 'PROCESS_RESULT';
  payload: { result: number[]; stats: { mean: number; stddev: number } };
  id: string;
}

interface WorkerError {
  type: 'PROCESS_ERROR';
  error: string;
  id: string;
}

type WorkerMessage = WorkerResponse | WorkerError;

// Send work to the worker
function processDataAsync(data: number[]): Promise<WorkerResponse['payload']> {
  return new Promise((resolve, reject) => {
    const id = crypto.randomUUID();

    function handler(event: MessageEvent<WorkerMessage>) {
      if (event.data.id !== id) return;
      worker.removeEventListener('message', handler);

      if (event.data.type === 'PROCESS_ERROR') {
        reject(new Error(event.data.error));
      } else {
        resolve(event.data.payload);
      }
    }

    worker.addEventListener('message', handler);
    worker.postMessage({
      type: 'PROCESS_DATA',
      payload: { data, chunkSize: 1000 },
      id,
    } satisfies WorkerRequest);
  });
}


// heavy-worker.ts — the worker file
self.addEventListener('message', (event: MessageEvent<WorkerRequest>) => {
  const { type, payload, id } = event.data;

  if (type === 'PROCESS_DATA') {
    try {
      const { data, chunkSize } = payload;

      // Heavy computation — runs off main thread
      const result: number[] = [];
      for (let i = 0; i < data.length; i += chunkSize) {
        const chunk = data.slice(i, i + chunkSize);
        const processed = chunk.map(x => Math.sqrt(x * x + 1));
        result.push(...processed);
      }

      const mean = result.reduce((a, b) => a + b, 0) / result.length;
      const variance = result.reduce((a, b) => a + (b - mean) ** 2, 0) / result.length;

      self.postMessage({
        type: 'PROCESS_RESULT',
        payload: { result, stats: { mean, stddev: Math.sqrt(variance) } },
        id,
      } satisfies WorkerResponse);
    } catch (err) {
      self.postMessage({
        type: 'PROCESS_ERROR',
        error: err instanceof Error ? err.message : String(err),
        id,
      } satisfies WorkerError);
    }
  }
});
```

```typescript
// --- Transferable objects (zero-copy transfer) ---

// Transferable objects move ownership to the worker
// instead of copying — O(1) instead of O(n)

// main.ts
function transferLargeArray(data: Float64Array): void {
  // Transfer the underlying ArrayBuffer (not a copy)
  worker.postMessage(
    { type: 'CRUNCH', buffer: data.buffer },
    [data.buffer]  // transfer list — buffer is moved, not copied
  );
  // WARNING: data is now neutered (length 0) — cannot use it here!
  console.log(data.byteLength); // 0
}

// Structured clone vs transfer comparison
function demonstrateTransfer(): void {
  const size = 100_000_000; // 100M floats = 800MB
  const arr = new Float64Array(size);

  // Slow: structured clone (copies 800MB)
  // worker.postMessage({ buffer: arr.buffer });

  // Fast: transfer (moves reference, ~0ms)
  worker.postMessage(
    { buffer: arr.buffer },
    { transfer: [arr.buffer] }   // modern syntax
  );
}


// Transferable types:
// - ArrayBuffer
// - MessagePort
// - ReadableStream / WritableStream / TransformStream
// - ImageBitmap
// - OffscreenCanvas
// - VideoFrame
// - RTCDataChannel


// --- Worker pool for parallel processing ---

class WorkerPool<TReq, TRes> {
  private workers: Worker[] = [];
  private queue: Array<{
    message: TReq;
    transfer?: Transferable[];
    resolve: (value: TRes) => void;
    reject: (reason: Error) => void;
  }> = [];
  private available: Worker[] = [];

  constructor(
    private workerUrl: URL,
    private poolSize: number = navigator.hardwareConcurrency || 4,
  ) {
    for (let i = 0; i < this.poolSize; i++) {
      const w = new Worker(workerUrl, { type: 'module' });
      this.workers.push(w);
      this.available.push(w);
    }
  }

  execute(message: TReq, transfer?: Transferable[]): Promise<TRes> {
    return new Promise<TRes>((resolve, reject) => {
      const worker = this.available.pop();
      if (worker) {
        this.runOnWorker(worker, message, transfer, resolve, reject);
      } else {
        this.queue.push({ message, transfer, resolve, reject });
      }
    });
  }

  private runOnWorker(
    worker: Worker,
    message: TReq,
    transfer: Transferable[] | undefined,
    resolve: (value: TRes) => void,
    reject: (reason: Error) => void,
  ): void {
    const onMessage = (e: MessageEvent<TRes>) => {
      worker.removeEventListener('message', onMessage);
      worker.removeEventListener('error', onError);
      this.available.push(worker);
      resolve(e.data);
      this.processQueue();
    };

    const onError = (e: ErrorEvent) => {
      worker.removeEventListener('message', onMessage);
      worker.removeEventListener('error', onError);
      this.available.push(worker);
      reject(new Error(e.message));
      this.processQueue();
    };

    worker.addEventListener('message', onMessage);
    worker.addEventListener('error', onError);
    worker.postMessage(message, transfer ? { transfer } : undefined);
  }

  private processQueue(): void {
    if (this.queue.length === 0 || this.available.length === 0) return;
    const { message, transfer, resolve, reject } = this.queue.shift()!;
    const worker = this.available.pop()!;
    this.runOnWorker(worker, message, transfer, resolve, reject);
  }

  terminate(): void {
    this.workers.forEach(w => w.terminate());
    this.workers = [];
    this.available = [];
    this.queue.forEach(({ reject }) => reject(new Error('Pool terminated')));
    this.queue = [];
  }
}

// Usage
const pool = new WorkerPool<{ data: number[] }, { result: number[] }>(
  new URL('./compute-worker.ts', import.meta.url),
  4,
);

const results = await Promise.all([
  pool.execute({ data: chunk1 }),
  pool.execute({ data: chunk2 }),
  pool.execute({ data: chunk3 }),
]);
```

```typescript
// --- Shared Worker (multiple tabs/windows) ---

// shared-worker.ts
const connections: MessagePort[] = [];

self.addEventListener('connect', (event: MessageEvent) => {
  const port = event.ports[0];
  connections.push(port);

  // Shared state across all connected tabs
  let sharedCounter = 0;

  port.addEventListener('message', (e: MessageEvent) => {
    const { type, payload } = e.data;

    switch (type) {
      case 'INCREMENT':
        sharedCounter++;
        // Broadcast to ALL connected tabs
        connections.forEach(p => {
          p.postMessage({ type: 'COUNTER_UPDATE', value: sharedCounter });
        });
        break;

      case 'GET_COUNTER':
        port.postMessage({ type: 'COUNTER_UPDATE', value: sharedCounter });
        break;

      case 'BROADCAST':
        // Send message to all OTHER tabs
        connections.forEach(p => {
          if (p !== port) {
            p.postMessage({ type: 'BROADCAST', payload: payload });
          }
        });
        break;
    }
  });

  port.start();

  // Cleanup on disconnect
  port.addEventListener('close', () => {
    const idx = connections.indexOf(port);
    if (idx !== -1) connections.splice(idx, 1);
  });
});


// main.ts — connecting to shared worker
const shared = new SharedWorker(
  new URL('./shared-worker.ts', import.meta.url),
  { type: 'module', name: 'app-shared' }
);

shared.port.start();

shared.port.addEventListener('message', (e) => {
  console.log('From shared worker:', e.data);
});

shared.port.postMessage({ type: 'INCREMENT' });
shared.port.postMessage({ type: 'BROADCAST', payload: { tab: 'Hello from this tab!' } });
```

| Worker Type | Scope | Shared State | Use Case |
|---|---|---|---|
| Dedicated Worker | Single page | No (message passing) | Heavy computation, data processing |
| Shared Worker | Multiple tabs/windows | Yes (in worker) | Cross-tab communication, shared cache |
| Service Worker | Origin-wide (proxy) | No (event-driven) | Offline, push notifications, caching |

| Transfer Method | Speed | Memory | Ownership |
|---|---|---|---|
| Structured clone | O(n) — copies data | Doubled during transfer | Both sides keep data |
| Transfer | O(1) — moves pointer | No duplication | Source loses access |
| SharedArrayBuffer | O(1) — shared memory | Single copy | Both sides read/write |

Key patterns:
1. Use `new URL('./worker.ts', import.meta.url)` for bundler-compatible worker loading
2. Transfer `ArrayBuffer` instead of cloning for large data (800MB in ~0ms)
3. Worker pools distribute parallel tasks across `navigator.hardwareConcurrency` threads
4. Shared Workers maintain state across browser tabs via `MessagePort`
5. Always handle errors: `worker.addEventListener('error', ...)` and try/catch in worker
6. Type-safe messaging with discriminated unions (`{ type: string; payload: T }`)
7. After transferring a buffer, the source reference is neutered (byteLength = 0)'''
    ),
    (
        "frontend/sharedarraybuffer-atomics",
        "Demonstrate SharedArrayBuffer and Atomics for lock-free parallel computation between workers including synchronization primitives.",
        '''SharedArrayBuffer allows multiple workers to read/write the same memory region. Atomics provides atomic operations and synchronization to prevent data races.

```typescript
// --- SharedArrayBuffer basics ---

// main.ts
// IMPORTANT: requires Cross-Origin-Isolation headers:
//   Cross-Origin-Opener-Policy: same-origin
//   Cross-Origin-Embedder-Policy: require-corp

// Check availability
if (typeof SharedArrayBuffer === 'undefined') {
  throw new Error(
    'SharedArrayBuffer not available. Set COOP/COEP headers.'
  );
}

// Create shared memory (1MB)
const sharedBuffer = new SharedArrayBuffer(1024 * 1024);

// Create typed views into the same memory
const sharedInt32 = new Int32Array(sharedBuffer);
const sharedFloat64 = new Float64Array(sharedBuffer);

// Spawn workers that share the same buffer
const worker1 = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' });
const worker2 = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' });

// Send the shared buffer — NOT transferred, both sides keep access
worker1.postMessage({ sharedBuffer, workerId: 0, workerCount: 2 });
worker2.postMessage({ sharedBuffer, workerId: 1, workerCount: 2 });


// --- Atomic operations ---

// Without Atomics: data race
// sharedInt32[0] = sharedInt32[0] + 1;  // NOT safe!

// With Atomics: atomic read-modify-write
Atomics.add(sharedInt32, 0, 1);           // atomic increment
Atomics.sub(sharedInt32, 0, 1);           // atomic decrement
Atomics.load(sharedInt32, 0);             // atomic read
Atomics.store(sharedInt32, 0, 42);        // atomic write
Atomics.exchange(sharedInt32, 0, 99);     // atomic swap, returns old value
Atomics.compareExchange(sharedInt32, 0, 99, 100); // CAS operation

// Bitwise atomics
Atomics.and(sharedInt32, 0, 0xFF);
Atomics.or(sharedInt32, 0, 0x100);
Atomics.xor(sharedInt32, 0, 0x1);
```

```typescript
// --- Parallel array processing with shared memory ---

// Layout of shared buffer:
// [0]       = status flag (0=idle, 1=working, 2=done)
// [1]       = worker count that finished
// [2..N+2]  = input data
// [N+2..]   = output data

interface SharedConfig {
  sharedBuffer: SharedArrayBuffer;
  workerId: number;
  workerCount: number;
  dataOffset: number;
  dataLength: number;
  outputOffset: number;
}

// worker.ts — parallel computation
self.addEventListener('message', (e: MessageEvent<SharedConfig>) => {
  const { sharedBuffer, workerId, workerCount, dataOffset, dataLength, outputOffset } = e.data;

  const data = new Float64Array(sharedBuffer, dataOffset * 8, dataLength);
  const output = new Float64Array(sharedBuffer, outputOffset * 8, dataLength);
  const status = new Int32Array(sharedBuffer);

  // Each worker processes its chunk
  const chunkSize = Math.ceil(dataLength / workerCount);
  const start = workerId * chunkSize;
  const end = Math.min(start + chunkSize, dataLength);

  // Process data (e.g., square root of absolute value)
  for (let i = start; i < end; i++) {
    output[i] = Math.sqrt(Math.abs(data[i]));
  }

  // Atomically signal completion
  const finished = Atomics.add(status, 1, 1) + 1;

  if (finished === workerCount) {
    // Last worker to finish — signal all done
    Atomics.store(status, 0, 2); // status = done
    Atomics.notify(status, 0);   // wake up main thread
  }
});


// main.ts — orchestrating parallel work
async function parallelProcess(data: Float64Array): Promise<Float64Array> {
  const workerCount = navigator.hardwareConcurrency || 4;
  const bufferSize = (2 + data.length * 2) * 8; // status + input + output

  const sharedBuffer = new SharedArrayBuffer(bufferSize);
  const status = new Int32Array(sharedBuffer);
  const input = new Float64Array(sharedBuffer, 16, data.length);
  const output = new Float64Array(sharedBuffer, 16 + data.length * 8, data.length);

  // Copy input data to shared buffer
  input.set(data);

  // Initialize status
  Atomics.store(status, 0, 1); // working
  Atomics.store(status, 1, 0); // 0 workers finished

  // Spawn workers
  const workers: Worker[] = [];
  for (let i = 0; i < workerCount; i++) {
    const w = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' });
    w.postMessage({
      sharedBuffer,
      workerId: i,
      workerCount,
      dataOffset: 2,
      dataLength: data.length,
      outputOffset: 2 + data.length,
    } satisfies SharedConfig);
    workers.push(w);
  }

  // Wait for completion (non-blocking on main thread)
  await Atomics.waitAsync(status, 0, 1).value;

  // Read result
  const result = new Float64Array(data.length);
  result.set(output);

  // Cleanup
  workers.forEach(w => w.terminate());

  return result;
}
```

```typescript
// --- Spinlock and Mutex with Atomics ---

class AtomicMutex {
  private lockIndex: number;
  private view: Int32Array;

  constructor(sharedBuffer: SharedArrayBuffer, lockIndex: number) {
    this.view = new Int32Array(sharedBuffer);
    this.lockIndex = lockIndex;
  }

  lock(): void {
    // Spin until we acquire the lock (CAS: 0 -> 1)
    while (Atomics.compareExchange(this.view, this.lockIndex, 0, 1) !== 0) {
      // Wait until someone releases (value changes from 1)
      Atomics.wait(this.view, this.lockIndex, 1);
    }
  }

  unlock(): void {
    Atomics.store(this.view, this.lockIndex, 0);
    Atomics.notify(this.view, this.lockIndex, 1); // wake one waiter
  }

  withLock<T>(fn: () => T): T {
    this.lock();
    try {
      return fn();
    } finally {
      this.unlock();
    }
  }
}


// --- Ring buffer for lock-free producer/consumer ---

class SharedRingBuffer {
  private buffer: Float64Array;
  private meta: Int32Array;
  // meta[0] = write index, meta[1] = read index, meta[2] = capacity

  constructor(sharedBuffer: SharedArrayBuffer, metaOffset: number, dataOffset: number, capacity: number) {
    this.meta = new Int32Array(sharedBuffer, metaOffset, 3);
    this.buffer = new Float64Array(sharedBuffer, dataOffset, capacity);
    Atomics.store(this.meta, 2, capacity);
  }

  push(value: number): boolean {
    const capacity = Atomics.load(this.meta, 2);
    const writeIdx = Atomics.load(this.meta, 0);
    const readIdx = Atomics.load(this.meta, 1);

    // Check if full
    if ((writeIdx - readIdx) >= capacity) return false;

    this.buffer[writeIdx % capacity] = value;
    Atomics.add(this.meta, 0, 1); // advance write index
    Atomics.notify(this.meta, 1); // wake consumer
    return true;
  }

  pop(): number | null {
    const writeIdx = Atomics.load(this.meta, 0);
    const readIdx = Atomics.load(this.meta, 1);

    // Check if empty
    if (readIdx >= writeIdx) return null;

    const capacity = Atomics.load(this.meta, 2);
    const value = this.buffer[readIdx % capacity];
    Atomics.add(this.meta, 1, 1); // advance read index
    return value;
  }

  popBlocking(): number {
    // Wait until data is available
    while (true) {
      const value = this.pop();
      if (value !== null) return value;
      Atomics.wait(this.meta, 1, Atomics.load(this.meta, 1));
    }
  }
}
```

| Operation | Description | Thread-Safe | Blocking |
|---|---|---|---|
| `Atomics.load` | Read value atomically | Yes | No |
| `Atomics.store` | Write value atomically | Yes | No |
| `Atomics.add/sub` | Increment/decrement | Yes | No |
| `Atomics.compareExchange` | CAS (compare and swap) | Yes | No |
| `Atomics.wait` | Block until value changes | Yes | Yes (worker only) |
| `Atomics.waitAsync` | Async wait (returns promise) | Yes | No (main thread OK) |
| `Atomics.notify` | Wake waiting threads | Yes | No |

| Approach | Copy Cost | Synchronization | Complexity |
|---|---|---|---|
| `postMessage` (clone) | O(n) | Implicit (message order) | Low |
| `postMessage` (transfer) | O(1) | Implicit (ownership move) | Low |
| `SharedArrayBuffer` | O(1) shared | Manual (Atomics) | High |
| `SharedArrayBuffer` + Mutex | O(1) shared | Lock-based | Medium |

Key patterns:
1. SharedArrayBuffer requires COOP/COEP headers for cross-origin isolation
2. Always use `Atomics.*` for reads/writes — raw access causes data races
3. `Atomics.wait` blocks (workers only); use `Atomics.waitAsync` on the main thread
4. `Atomics.compareExchange` is the building block for mutexes and lock-free structures
5. Layout shared memory with typed array views at specific byte offsets
6. Ring buffers enable lock-free producer/consumer patterns between workers
7. Use `Atomics.notify` to wake workers waiting on `Atomics.wait`'''
    ),
    (
        "frontend/comlink-worker-rpc",
        "Show how to use Comlink for transparent RPC between the main thread and Web Workers with async function calls and proxy objects.",
        '''Comlink by Google Chrome Labs turns the postMessage-based worker API into transparent async function calls, making workers feel like normal async modules.

```typescript
// --- Basic Comlink usage ---

// worker.ts — expose an API
import { expose } from 'comlink';

interface ProcessingResult {
  data: number[];
  elapsed: number;
  stats: { min: number; max: number; mean: number };
}

const api = {
  // Regular function — becomes async on main thread
  add(a: number, b: number): number {
    return a + b;
  },

  // Heavy computation — runs on worker thread
  processLargeDataset(data: number[]): ProcessingResult {
    const start = performance.now();

    const sorted = [...data].sort((a, b) => a - b);
    const processed = sorted.map(x => Math.sqrt(x * x + 1));

    const min = processed[0];
    const max = processed[processed.length - 1];
    const mean = processed.reduce((a, b) => a + b, 0) / processed.length;

    return {
      data: processed,
      elapsed: performance.now() - start,
      stats: { min, max, mean },
    };
  },

  // Async function — works seamlessly
  async fetchAndProcess(url: string): Promise<ProcessingResult> {
    const response = await fetch(url);
    const data: number[] = await response.json();
    return api.processLargeDataset(data);
  },

  // Stateful: Comlink proxies maintain object identity
  createCounter(initial: number = 0) {
    let count = initial;
    return {
      increment() { return ++count; },
      decrement() { return --count; },
      getCount() { return count; },
      reset() { count = initial; return count; },
    };
  },
};

export type WorkerApi = typeof api;

expose(api);


// main.ts — use the worker as a normal async module
import { wrap, proxy, transfer, type Remote } from 'comlink';
import type { WorkerApi } from './worker';

const worker = new Worker(
  new URL('./worker.ts', import.meta.url),
  { type: 'module' }
);

// Wrap returns a proxy where every method call is async
const api: Remote<WorkerApi> = wrap<WorkerApi>(worker);

// Transparent async calls
const sum = await api.add(2, 3);        // 5
const result = await api.processLargeDataset([3, 1, 4, 1, 5]);
console.log(result.stats);              // { min: ..., max: ..., mean: ... }

// Stateful proxy objects
const counter = await api.createCounter(10);
await counter.increment();   // 11
await counter.increment();   // 12
await counter.getCount();    // 12
```

```typescript
// --- Advanced: callbacks, transfer, and React integration ---

// worker.ts — accepting callbacks from main thread
import { expose } from 'comlink';

const api = {
  // Accept a callback — Comlink proxies it across the boundary
  async processWithProgress(
    data: number[],
    onProgress: (percent: number) => void,
  ): Promise<number[]> {
    const result: number[] = [];
    const total = data.length;

    for (let i = 0; i < total; i++) {
      result.push(Math.sqrt(data[i]));

      // Report progress every 10%
      if (i % Math.ceil(total / 10) === 0) {
        await onProgress(Math.round((i / total) * 100));
      }
    }

    await onProgress(100);
    return result;
  },

  // Accept transferable buffers for zero-copy
  processBuffer(buffer: ArrayBuffer): ArrayBuffer {
    const input = new Float64Array(buffer);
    const output = new Float64Array(input.length);

    for (let i = 0; i < input.length; i++) {
      output[i] = input[i] * 2;
    }

    return transfer(output.buffer, [output.buffer]);
  },
};

expose(api);


// main.ts — passing callbacks and transferables
import { wrap, proxy, transfer } from 'comlink';

const api = wrap<typeof import('./worker')['default']>(worker);

// Pass a callback using proxy() — tells Comlink to keep the reference alive
const result = await api.processWithProgress(
  largeData,
  proxy((percent: number) => {
    progressBar.style.width = `${percent}%`;
    progressLabel.textContent = `${percent}%`;
  }),
);

// Transfer an ArrayBuffer to the worker
const inputBuffer = new Float64Array([1, 2, 3, 4, 5]).buffer;
const outputBuffer = await api.processBuffer(
  transfer(inputBuffer, [inputBuffer])
);


// --- React hook for Comlink workers ---

import { useEffect, useRef, useState, useCallback } from 'react';
import { wrap, type Remote } from 'comlink';

function useWorker<T>(
  workerFactory: () => Worker,
): Remote<T> | null {
  const workerRef = useRef<Worker | null>(null);
  const apiRef = useRef<Remote<T> | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const w = workerFactory();
    workerRef.current = w;
    apiRef.current = wrap<T>(w);
    setReady(true);

    return () => {
      w.terminate();
      workerRef.current = null;
      apiRef.current = null;
    };
  }, []);

  return ready ? apiRef.current : null;
}

// Usage in component
function DataProcessor() {
  const api = useWorker<WorkerApi>(
    () => new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' })
  );
  const [result, setResult] = useState<ProcessingResult | null>(null);
  const [loading, setLoading] = useState(false);

  const handleProcess = useCallback(async () => {
    if (!api) return;
    setLoading(true);
    try {
      const res = await api.processLargeDataset(generateData(100000));
      setResult(res);
    } finally {
      setLoading(false);
    }
  }, [api]);

  return (
    <div>
      <button onClick={handleProcess} disabled={loading || !api}>
        {loading ? 'Processing...' : 'Process Data'}
      </button>
      {result && (
        <pre>{JSON.stringify(result.stats, null, 2)}</pre>
      )}
    </div>
  );
}
```

```typescript
// --- Comlink with SharedWorker and ServiceWorker ---

// shared-worker.ts
import { expose } from 'comlink';

const sharedState = {
  connections: 0,
  data: new Map<string, unknown>(),
};

const api = {
  connect() {
    sharedState.connections++;
    return sharedState.connections;
  },

  setData(key: string, value: unknown) {
    sharedState.data.set(key, value);
  },

  getData(key: string): unknown {
    return sharedState.data.get(key);
  },

  getConnectionCount(): number {
    return sharedState.connections;
  },
};

// For SharedWorker: expose on each port
addEventListener('connect', (event: MessageEvent) => {
  expose(api, event.ports[0]);
});


// main.ts — using SharedWorker with Comlink
import { wrap } from 'comlink';

const sharedWorker = new SharedWorker(
  new URL('./shared-worker.ts', import.meta.url),
  { type: 'module' }
);

const sharedApi = wrap<typeof api>(sharedWorker.port);

const count = await sharedApi.connect();
console.log(`Connection #${count}`);

await sharedApi.setData('theme', 'dark');
const theme = await sharedApi.getData('theme');  // 'dark'


// --- Type-safe worker module pattern ---

// Define the contract
interface ImageProcessor {
  resize(data: ArrayBuffer, width: number, height: number): Promise<ArrayBuffer>;
  blur(data: ArrayBuffer, radius: number): Promise<ArrayBuffer>;
  grayscale(data: ArrayBuffer): Promise<ArrayBuffer>;
}

// Create typed worker factory
function createImageProcessor(): Remote<ImageProcessor> {
  const worker = new Worker(
    new URL('./image-worker.ts', import.meta.url),
    { type: 'module' }
  );
  return wrap<ImageProcessor>(worker);
}

const processor = createImageProcessor();
const resized = await processor.resize(imageBuffer, 800, 600);
```

| Feature | Raw postMessage | Comlink | workerize-loader |
|---|---|---|---|
| API style | Event-based messages | Async function calls | Async function calls |
| Type safety | Manual typing | Full TypeScript support | Limited |
| Callbacks | Manual message routing | `proxy()` wrapper | Not supported |
| Transferables | Manual transfer list | `transfer()` helper | Not supported |
| SharedWorker | Manual port handling | `expose(api, port)` | Not supported |
| Bundle size | 0 KB | ~5 KB | ~2 KB |
| Proxy objects | Not possible | Maintained across boundary | Not supported |
| Learning curve | Medium | Low | Low |

Key patterns:
1. `expose(api)` in the worker, `wrap<Type>(worker)` in the main thread
2. Every method becomes async — `api.add(1, 2)` returns `Promise<number>`
3. Use `proxy(callback)` when passing functions to the worker
4. Use `transfer(buffer, [buffer])` for zero-copy ArrayBuffer passing
5. Proxy objects from `createCounter()` maintain state across the boundary
6. For SharedWorkers, `expose(api, port)` inside the `connect` event handler
7. Combine with a React hook (`useWorker`) for component-scoped worker lifecycle'''
    ),
    (
        "frontend/offscreencanvas-gpu",
        "Demonstrate OffscreenCanvas for GPU rendering in Web Workers including WebGL, 2D canvas, and animation patterns.",
        '''OffscreenCanvas allows canvas rendering in Web Workers, freeing the main thread from heavy drawing operations. This enables smooth 60fps animations even when the main thread is busy.

```typescript
// --- Transferring canvas control to a worker ---

// main.ts
const canvas = document.getElementById('render-canvas') as HTMLCanvasElement;

// Transfer control — the main thread can no longer draw on this canvas
const offscreen: OffscreenCanvas = canvas.transferControlToOffscreen();

const worker = new Worker(
  new URL('./render-worker.ts', import.meta.url),
  { type: 'module' }
);

// Transfer the OffscreenCanvas to the worker
worker.postMessage(
  { type: 'INIT', canvas: offscreen, width: canvas.width, height: canvas.height },
  [offscreen]  // transfer list — ownership moves to worker
);

// Send user interactions to the worker
canvas.addEventListener('mousemove', (e) => {
  const rect = canvas.getBoundingClientRect();
  worker.postMessage({
    type: 'MOUSE_MOVE',
    x: e.clientX - rect.left,
    y: e.clientY - rect.top,
  });
});

canvas.addEventListener('click', (e) => {
  worker.postMessage({ type: 'CLICK' });
});

// Resize handling
const resizeObserver = new ResizeObserver(entries => {
  for (const entry of entries) {
    const { width, height } = entry.contentRect;
    worker.postMessage({ type: 'RESIZE', width, height });
  }
});
resizeObserver.observe(canvas);
```

```typescript
// --- 2D rendering in worker ---

// render-worker.ts (2D context)
let canvas: OffscreenCanvas;
let ctx: OffscreenCanvasRenderingContext2D;
let width: number;
let height: number;
let mouseX = 0;
let mouseY = 0;
let animationId: number;

interface Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  color: string;
  life: number;
  maxLife: number;
}

const particles: Particle[] = [];

function createParticle(x: number, y: number): Particle {
  const angle = Math.random() * Math.PI * 2;
  const speed = Math.random() * 3 + 1;
  return {
    x, y,
    vx: Math.cos(angle) * speed,
    vy: Math.sin(angle) * speed,
    radius: Math.random() * 4 + 2,
    color: `hsl(${Math.random() * 360}, 70%, 60%)`,
    life: 0,
    maxLife: Math.random() * 60 + 30,
  };
}

function update(): void {
  // Emit particles at mouse position
  for (let i = 0; i < 3; i++) {
    particles.push(createParticle(mouseX, mouseY));
  }

  // Update particles
  for (let i = particles.length - 1; i >= 0; i--) {
    const p = particles[i];
    p.x += p.vx;
    p.y += p.vy;
    p.vy += 0.05;  // gravity
    p.life++;

    if (p.life >= p.maxLife) {
      particles.splice(i, 1);
    }
  }
}

function draw(): void {
  ctx.clearRect(0, 0, width, height);

  for (const p of particles) {
    const alpha = 1 - p.life / p.maxLife;
    ctx.globalAlpha = alpha;
    ctx.fillStyle = p.color;
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.radius * alpha, 0, Math.PI * 2);
    ctx.fill();
  }

  ctx.globalAlpha = 1;
}

function loop(): void {
  update();
  draw();
  animationId = requestAnimationFrame(loop);
}

self.addEventListener('message', (e: MessageEvent) => {
  switch (e.data.type) {
    case 'INIT':
      canvas = e.data.canvas as OffscreenCanvas;
      width = e.data.width;
      height = e.data.height;
      canvas.width = width;
      canvas.height = height;
      ctx = canvas.getContext('2d')!;
      loop();
      break;

    case 'MOUSE_MOVE':
      mouseX = e.data.x;
      mouseY = e.data.y;
      break;

    case 'RESIZE':
      width = e.data.width;
      height = e.data.height;
      canvas.width = width;
      canvas.height = height;
      break;

    case 'STOP':
      cancelAnimationFrame(animationId);
      break;
  }
});
```

```typescript
// --- WebGL rendering in worker ---

// webgl-worker.ts
let gl: WebGL2RenderingContext;
let program: WebGLProgram;

function initWebGL(canvas: OffscreenCanvas): void {
  gl = canvas.getContext('webgl2')!;
  if (!gl) throw new Error('WebGL2 not supported in OffscreenCanvas');

  // Vertex shader
  const vertSrc = `#version 300 es
    in vec2 aPosition;
    in vec3 aColor;
    out vec3 vColor;

    uniform float uTime;
    uniform vec2 uResolution;

    void main() {
      vec2 pos = aPosition;
      pos.y += sin(pos.x * 3.0 + uTime) * 0.1;
      gl_Position = vec4(pos, 0.0, 1.0);
      vColor = aColor;
    }
  `;

  // Fragment shader
  const fragSrc = `#version 300 es
    precision highp float;
    in vec3 vColor;
    out vec4 fragColor;

    void main() {
      fragColor = vec4(vColor, 1.0);
    }
  `;

  const vert = compileShader(gl, gl.VERTEX_SHADER, vertSrc);
  const frag = compileShader(gl, gl.FRAGMENT_SHADER, fragSrc);

  program = gl.createProgram()!;
  gl.attachShader(program, vert);
  gl.attachShader(program, frag);
  gl.linkProgram(program);

  if (!gl.getProgramParameter(program, gl.LINK_STATUS)) {
    throw new Error(gl.getProgramInfoLog(program) ?? 'Link failed');
  }

  gl.useProgram(program);
  setupGeometry();
}

function compileShader(
  gl: WebGL2RenderingContext,
  type: number,
  source: string,
): WebGLShader {
  const shader = gl.createShader(type)!;
  gl.shaderSource(shader, source);
  gl.compileShader(shader);

  if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) {
    const info = gl.getShaderInfoLog(shader);
    gl.deleteShader(shader);
    throw new Error(`Shader compile error: ${info}`);
  }

  return shader;
}

function setupGeometry(): void {
  // Triangle strip grid
  const vertices: number[] = [];
  const colors: number[] = [];
  const gridSize = 50;

  for (let y = 0; y < gridSize; y++) {
    for (let x = 0; x <= gridSize; x++) {
      const nx = (x / gridSize) * 2 - 1;
      const ny1 = (y / gridSize) * 2 - 1;
      const ny2 = ((y + 1) / gridSize) * 2 - 1;

      vertices.push(nx, ny1, nx, ny2);
      const r = x / gridSize;
      const g = y / gridSize;
      colors.push(r, g, 0.5, r, g, 0.8);
    }
  }

  const posBuffer = gl.createBuffer()!;
  gl.bindBuffer(gl.ARRAY_BUFFER, posBuffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(vertices), gl.STATIC_DRAW);

  const posLoc = gl.getAttribLocation(program, 'aPosition');
  gl.enableVertexAttribArray(posLoc);
  gl.vertexAttribPointer(posLoc, 2, gl.FLOAT, false, 0, 0);

  const colorBuffer = gl.createBuffer()!;
  gl.bindBuffer(gl.ARRAY_BUFFER, colorBuffer);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(colors), gl.STATIC_DRAW);

  const colorLoc = gl.getAttribLocation(program, 'aColor');
  gl.enableVertexAttribArray(colorLoc);
  gl.vertexAttribPointer(colorLoc, 3, gl.FLOAT, false, 0, 0);
}

let startTime = performance.now();

function render(): void {
  const time = (performance.now() - startTime) / 1000;

  gl.clearColor(0.05, 0.05, 0.1, 1);
  gl.clear(gl.COLOR_BUFFER_BIT);

  const timeLoc = gl.getUniformLocation(program, 'uTime');
  gl.uniform1f(timeLoc, time);

  const resLoc = gl.getUniformLocation(program, 'uResolution');
  gl.uniform2f(resLoc, gl.canvas.width, gl.canvas.height);

  gl.drawArrays(gl.TRIANGLE_STRIP, 0, 102 * 51);

  requestAnimationFrame(render);
}

self.addEventListener('message', (e: MessageEvent) => {
  if (e.data.type === 'INIT') {
    const canvas = e.data.canvas as OffscreenCanvas;
    canvas.width = e.data.width;
    canvas.height = e.data.height;
    initWebGL(canvas);
    render();
  }
});
```

| Rendering Approach | Main Thread Blocking | GPU Access | Use Case |
|---|---|---|---|
| Canvas 2D (main) | Yes | No (CPU) | Simple UI drawing |
| Canvas 2D (worker) | No | No (CPU) | Charts, data viz |
| WebGL (main) | Yes (JS calls) | Yes | 3D scenes, games |
| WebGL (worker) | No | Yes | Heavy 3D, simulations |
| WebGPU (worker) | No | Yes (compute) | ML inference, physics |

| Feature | Regular Canvas | OffscreenCanvas |
|---|---|---|
| Runs in | Main thread only | Main thread or Worker |
| DOM access | Yes | No |
| Event handling | Direct | Via postMessage |
| requestAnimationFrame | Yes | Yes (in worker) |
| WebGL/WebGL2 | Yes | Yes |
| WebGPU | Yes | Yes |
| ImageBitmap | `createImageBitmap` | `createImageBitmap` |
| Transferable | No | Yes (`transferControlToOffscreen`) |

Key patterns:
1. `canvas.transferControlToOffscreen()` moves drawing control to a worker (one-time, irreversible)
2. Send the OffscreenCanvas via `postMessage` with transfer list: `[offscreen]`
3. Worker gets its own `requestAnimationFrame` — animation runs on the worker thread
4. Forward user events (mouse, touch) from main thread to worker via postMessage
5. Both 2D and WebGL/WebGPU contexts work on OffscreenCanvas
6. Use `ResizeObserver` on main thread and send resize events to the worker
7. Combine with SharedArrayBuffer for shared simulation state between physics and render workers'''
    ),
]
