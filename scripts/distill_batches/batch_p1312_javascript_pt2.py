"""JavaScript/TypeScript training pairs (part 2): performance, bundling, advanced patterns."""

PAIRS = [
    (
        "javascript/web-workers-cpu-intensive",
        r'''How do I use Web Workers to offload CPU-intensive tasks in the browser without blocking the UI?''',
        r'''<think>
Web Workers run JS in a separate thread, communicating via postMessage.
They cannot access the DOM but are ideal for heavy computation.
The pattern is: create a worker from a script or blob URL, send data in,
receive results back. For structured data, transferable objects avoid
copying overhead. I should show both the main thread and worker sides,
plus cleanup with worker.terminate().
</think>

**Web Workers** let you run expensive computation off the main thread:

```javascript
// worker.js
self.onmessage = (e) => {
  const { pixels, width, height } = e.data;
  // CPU-heavy image processing
  for (let i = 0; i < pixels.length; i += 4) {
    const gray = pixels[i] * 0.299 + pixels[i+1] * 0.587 + pixels[i+2] * 0.114;
    pixels[i] = pixels[i+1] = pixels[i+2] = gray;
  }
  // Transfer ownership back (zero-copy)
  self.postMessage({ pixels }, [pixels.buffer]);
};
```

```javascript
// main.js
const worker = new Worker('./worker.js');

function processImage(imageData) {
  return new Promise((resolve, reject) => {
    worker.onmessage = (e) => resolve(e.data.pixels);
    worker.onerror = (e) => reject(new Error(e.message));
    // Transfer the buffer to avoid copying
    const buffer = imageData.data.buffer;
    worker.postMessage(
      { pixels: imageData.data, width: imageData.width, height: imageData.height },
      [buffer]
    );
  });
}

// Usage
const canvas = document.getElementById('canvas');
const ctx = canvas.getContext('2d');
const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
const processed = await processImage(imageData);
// UI never blocked during processing

// Cleanup when done
worker.terminate();
```

Key points:
- **Transferable objects** (`[buffer]` second arg) move memory instead of copying — critical for large data
- Workers have no DOM access — pass only serializable data
- Use `worker.terminate()` to free the thread when done
- For multiple tasks, use a **worker pool** instead of spawning one per task'''
    ),
    (
        "javascript/sharedarraybuffer-atomics",
        r'''Explain SharedArrayBuffer and Atomics in JavaScript. When would I use them over regular postMessage?''',
        r'''<think>
SharedArrayBuffer allows multiple workers to share the same memory region
without copying. Atomics provides atomic operations (load, store, add,
compareExchange, wait, notify) to avoid race conditions on shared memory.
This is useful for high-throughput scenarios like real-time audio, physics
simulations, or shared state between many workers. Requires cross-origin
isolation headers (COOP/COEP). postMessage copies data; SAB shares it.
</think>

**SharedArrayBuffer** lets multiple threads read/write the same memory. **Atomics** prevents race conditions:

```javascript
// main.js — shared counter across workers
const sharedBuf = new SharedArrayBuffer(4); // 4 bytes = 1 Int32
const counter = new Int32Array(sharedBuf);

const NUM_WORKERS = 4;
const INCREMENTS = 100_000;
let finished = 0;

for (let i = 0; i < NUM_WORKERS; i++) {
  const w = new Worker('./counter-worker.js');
  w.postMessage({ sharedBuf, increments: INCREMENTS });
  w.onmessage = () => {
    if (++finished === NUM_WORKERS) {
      console.log(`Final count: ${Atomics.load(counter, 0)}`);
      // Always exactly 400,000 — no races
    }
  };
}
```

```javascript
// counter-worker.js
self.onmessage = (e) => {
  const { sharedBuf, increments } = e.data;
  const counter = new Int32Array(sharedBuf);

  for (let i = 0; i < increments; i++) {
    Atomics.add(counter, 0, 1); // atomic increment — thread-safe
  }
  self.postMessage('done');
};
```

**Wait/notify for synchronization:**

```javascript
// Worker A — waits for signal
const flag = new Int32Array(sharedBuf);
Atomics.wait(flag, 0, 0); // blocks until flag[0] !== 0
console.log('Woke up, data ready');

// Worker B — signals when ready
Atomics.store(flag, 0, 1);
Atomics.notify(flag, 0, 1); // wake 1 waiter
```

**When to use SAB over postMessage:**

| | postMessage | SharedArrayBuffer |
|---|---|---|
| Data transfer | Copy (or transfer) | Shared in-place |
| Overhead | O(n) per message | Near zero |
| Coordination | Event-based | Atomics (mutex-like) |
| Use case | Occasional large results | Real-time, high-frequency |

**Required headers** (cross-origin isolation):
```
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
```'''
    ),
    (
        "javascript/weakref-finalizationregistry",
        r'''What are WeakRef and FinalizationRegistry in JavaScript? Give me a practical use case.''',
        r'''<think>
WeakRef holds a weak reference to an object — it doesn't prevent GC.
FinalizationRegistry lets you register a callback that fires after an
object is garbage collected. Together they enable caches that auto-evict,
leak detection, and resource cleanup. The key caveat: GC timing is
non-deterministic, so never rely on finalizers for correctness. A
practical use case is an object cache that doesn't cause memory leaks.
</think>

**WeakRef** creates a reference that doesn't prevent garbage collection. **FinalizationRegistry** runs cleanup when an object is collected:

```javascript
class ObjectCache {
  #cache = new Map();
  #registry = new FinalizationRegistry((key) => {
    // Called after the cached object is GC'd
    const ref = this.#cache.get(key);
    if (ref && ref.deref() === undefined) {
      this.#cache.delete(key);
      console.log(`Cache entry '${key}' evicted by GC`);
    }
  });

  set(key, value) {
    const ref = new WeakRef(value);
    this.#cache.set(key, ref);
    this.#registry.register(value, key, value); // value is unregister token
  }

  get(key) {
    const ref = this.#cache.get(key);
    if (!ref) return undefined;
    const obj = ref.deref(); // returns object or undefined if GC'd
    if (obj === undefined) {
      this.#cache.delete(key);
      return undefined;
    }
    return obj;
  }

  delete(key) {
    const ref = this.#cache.get(key);
    if (ref) {
      const obj = ref.deref();
      if (obj) this.#registry.unregister(obj); // cancel finalizer
    }
    this.#cache.delete(key);
  }

  get size() {
    return this.#cache.size;
  }
}

// Usage
const cache = new ObjectCache();
let bigData = { values: new Array(1_000_000).fill(0) };
cache.set('dataset', bigData);

console.log(cache.get('dataset')); // { values: [...] }

bigData = null; // drop strong reference
// Eventually GC will collect it, and cache auto-cleans
```

**Important caveats:**
- `deref()` may return the object or `undefined` — always check
- Finalizer timing is **non-deterministic** — never rely on it for correctness
- Don't use finalizers as a substitute for explicit `.close()` or `.dispose()`
- Good for: caches, leak detection, telemetry. Bad for: critical resource cleanup'''
    ),
    (
        "javascript/tree-shaking-esm",
        r'''How does tree shaking work with ES modules? Why doesn't it work well with CommonJS?''',
        r'''<think>
Tree shaking is dead-code elimination for imports. ESM uses static
import/export declarations that can be analyzed at build time. Bundlers
(Rollup, webpack, esbuild) trace which exports are actually used and
drop the rest. CJS uses dynamic require() and module.exports which are
runtime constructs — the bundler can't statically determine what's used.
I should show how to write tree-shakeable code and common pitfalls.
</think>

**Tree shaking** eliminates unused exports at build time. It relies on ESM's **static structure**:

```javascript
// math.js (ESM — tree-shakeable)
export function add(a, b) { return a + b; }
export function multiply(a, b) { return a * b; }
export function complexFFT(data) { /* 500 lines */ }

// app.js — only imports add
import { add } from './math.js';
console.log(add(1, 2));
// multiply and complexFFT are eliminated from the bundle
```

**Why CJS defeats tree shaking:**

```javascript
// math-cjs.js
module.exports = {
  add(a, b) { return a + b; },
  multiply(a, b) { return a * b; },
  complexFFT(data) { /* 500 lines */ }
};

// app.js
const { add } = require('./math-cjs');
// Bundler can't prove multiply/complexFFT aren't used — keeps everything
// because require() is a runtime function call, could be dynamic
```

**Common tree-shaking killers:**

```javascript
// 1. Re-exporting everything (barrel files)
// index.js
export * from './add';
export * from './multiply';
export * from './complexFFT';
// Some bundlers struggle with deep barrel re-exports

// 2. Side effects in module scope
let counter = 0;
export function increment() { return ++counter; }
// Bundler must keep this — module has side effects

// 3. Classes (methods can't be individually shaken)
export class MathUtils {
  add(a, b) { return a + b; }
  complexFFT(data) { /* ... */ }
}
// Import MathUtils → get ALL methods, even unused ones
```

**Ensure tree shaking works:**

```json
// package.json
{
  "sideEffects": false,
  "module": "dist/esm/index.js",
  "exports": {
    ".": { "import": "./dist/esm/index.js" },
    "./add": { "import": "./dist/esm/add.js" }
  }
}
```

- Mark `"sideEffects": false` so bundlers can safely drop unused modules
- Prefer **named exports** over default exports with objects
- Prefer **standalone functions** over class methods
- Use granular entry points (`import { add } from 'mylib/add'`) for libraries'''
    ),
    (
        "javascript/bundle-code-splitting",
        r'''Show me how to implement code splitting in a modern JavaScript project. What strategies work best?''',
        r'''<think>
Code splitting breaks a bundle into smaller chunks loaded on demand.
The main approaches are: dynamic import(), route-based splitting (React.lazy),
vendor chunk separation, and shared chunk extraction. Webpack, Vite, and
Rollup all support this. The goal is smaller initial load and parallel
chunk loading. I'll show practical patterns for both vanilla JS and React
with Vite/webpack config.
</think>

**Code splitting** breaks your bundle into chunks loaded on demand, reducing initial load time:

**1. Dynamic `import()` — works everywhere:**

```javascript
// Load heavy library only when needed
document.getElementById('chart-btn').addEventListener('click', async () => {
  const { Chart } = await import('chart.js');
  new Chart(canvas, config);
});
```

**2. Route-based splitting with React:**

```jsx
import { lazy, Suspense } from 'react';
import { Routes, Route } from 'react-router-dom';

// Each route becomes its own chunk
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Settings = lazy(() => import('./pages/Settings'));
const Analytics = lazy(() => import(
  /* webpackChunkName: "analytics" */
  /* webpackPrefetch: true */
  './pages/Analytics'
));

function App() {
  return (
    <Suspense fallback={<Spinner />}>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/settings" element={<Settings />} />
        <Route path="/analytics" element={<Analytics />} />
      </Routes>
    </Suspense>
  );
}
```

**3. Vite config for chunk optimization:**

```javascript
// vite.config.js
export default defineConfig({
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            // Split large deps into separate vendor chunks
            if (id.includes('chart.js')) return 'vendor-chart';
            if (id.includes('lodash')) return 'vendor-lodash';
            return 'vendor'; // everything else
          }
        }
      }
    },
    chunkSizeWarningLimit: 500 // KB
  }
});
```

**4. Prefetch/preload for perceived speed:**

```html
<!-- Preload critical next-page chunk -->
<link rel="prefetch" href="/assets/analytics-3a1b2c.js">

<!-- Or programmatically -->
<script>
  // Prefetch on hover
  link.addEventListener('mouseenter', () => {
    import('./pages/Analytics'); // browser caches it
  });
</script>
```

**Strategy summary:**
| Strategy | When | Impact |
|---|---|---|
| Route splitting | Always | Biggest win for SPAs |
| Vendor separation | Large deps | Better cache invalidation |
| Dynamic import | Feature-gated code | On-demand loading |
| Prefetch | Predictable navigation | Hides latency |'''
    ),
    (
        "javascript/proxy-reflect-validation",
        r'''How can I use Proxy and Reflect in JavaScript for object validation?''',
        r'''<think>
Proxy wraps an object and intercepts operations (get, set, delete, etc.).
Reflect provides the default behavior for each trap. Together they create
transparent validation layers. The set trap is most common for validation.
I should show type checking, range validation, and a schema-based approach.
Using Reflect.set ensures proper behavior with inheritance and receivers.
</think>

**Proxy** intercepts object operations; **Reflect** provides the default behavior for each trap:

```javascript
function createValidated(target, schema) {
  return new Proxy(target, {
    set(obj, prop, value, receiver) {
      const rule = schema[prop];
      if (!rule) {
        throw new Error(`Unknown property: ${prop}`);
      }
      if (rule.type && typeof value !== rule.type) {
        throw new TypeError(`${prop} must be ${rule.type}, got ${typeof value}`);
      }
      if (rule.min !== undefined && value < rule.min) {
        throw new RangeError(`${prop} must be >= ${rule.min}`);
      }
      if (rule.max !== undefined && value > rule.max) {
        throw new RangeError(`${prop} must be <= ${rule.max}`);
      }
      if (rule.pattern && !rule.pattern.test(value)) {
        throw new Error(`${prop} failed pattern validation`);
      }
      // Use Reflect.set for correct receiver/prototype behavior
      return Reflect.set(obj, prop, value, receiver);
    },

    deleteProperty(obj, prop) {
      if (schema[prop]?.required) {
        throw new Error(`Cannot delete required property: ${prop}`);
      }
      return Reflect.deleteProperty(obj, prop);
    }
  });
}

// Define schema
const userSchema = {
  name:  { type: 'string', required: true },
  email: { type: 'string', pattern: /^[^@]+@[^@]+\.[^@]+$/ },
  age:   { type: 'number', min: 0, max: 150 },
};

const user = createValidated({}, userSchema);

user.name = 'Alice';           // OK
user.email = 'alice@test.com'; // OK
user.age = 30;                 // OK

user.age = -5;       // RangeError: age must be >= 0
user.email = 'bad';  // Error: email failed pattern validation
user.role = 'admin'; // Error: Unknown property: role
delete user.name;    // Error: Cannot delete required property: name
```

**Logging proxy (debugging):**

```javascript
function withLogging(obj, label = 'Proxy') {
  return new Proxy(obj, {
    get(target, prop, receiver) {
      const value = Reflect.get(target, prop, receiver);
      console.log(`${label}.get(${String(prop)}) -> ${JSON.stringify(value)}`);
      return value;
    },
    set(target, prop, value, receiver) {
      console.log(`${label}.set(${String(prop)}, ${JSON.stringify(value)})`);
      return Reflect.set(target, prop, value, receiver);
    }
  });
}
```

**Why Reflect over direct access:**
- `Reflect.set(obj, prop, value, receiver)` correctly handles prototype chains and getters/setters on the receiver
- Returns `true`/`false` instead of throwing on failure
- 1:1 mapping with every Proxy trap — consistent API'''
    ),
    (
        "javascript/tc39-decorators",
        r'''How do TC39 stage 3 decorators work in JavaScript? Show me practical examples.''',
        r'''<think>
TC39 decorators (2023+ stage 3) differ from the legacy TypeScript experimental
decorators. They receive a value and a context object with kind, name, addInitializer.
They work on classes, methods, accessors, and fields. The return value replaces
the decorated element. This is supported in TypeScript 5.0+ and Babel. I'll show
method decorators for logging, bound methods, and class decorators.
</think>

**TC39 decorators** (stage 3, supported in TS 5.0+ and Babel) use a new API different from legacy TS decorators:

```javascript
// @logged — method decorator
function logged(originalMethod, context) {
  const methodName = context.name;
  function replacementMethod(...args) {
    console.log(`-> ${methodName}(${args.join(', ')})`);
    const result = originalMethod.call(this, ...args);
    console.log(`<- ${methodName} returned ${result}`);
    return result;
  }
  return replacementMethod;
}

// @bound — auto-bind method to instance
function bound(originalMethod, context) {
  context.addInitializer(function () {
    this[context.name] = this[context.name].bind(this);
  });
  return originalMethod;
}

class Calculator {
  value = 0;

  @logged
  add(n) {
    this.value += n;
    return this.value;
  }

  @bound
  @logged
  multiply(n) {
    this.value *= n;
    return this.value;
  }
}

const calc = new Calculator();
calc.add(5);
// -> add(5)
// <- add returned 5

// multiply is auto-bound, safe to destructure
const { multiply } = calc;
multiply(3); // works — `this` is correct
```

**Accessor decorator (validation):**

```javascript
function clamp(min, max) {
  return function (target, context) {
    // target is { get, set } for auto-accessor
    return {
      get() { return target.get.call(this); },
      set(value) {
        target.set.call(this, Math.min(max, Math.max(min, value)));
      },
      init(initialValue) {
        return Math.min(max, Math.max(min, initialValue));
      }
    };
  };
}

class Slider {
  @clamp(0, 100)
  accessor value = 50;
}

const s = new Slider();
s.value = 150;
console.log(s.value); // 100 (clamped)
```

**Context object shape:**
```typescript
interface DecoratorContext {
  kind: 'class' | 'method' | 'getter' | 'setter' | 'field' | 'accessor';
  name: string | symbol;
  static: boolean;
  private: boolean;
  addInitializer(fn: () => void): void;
  access?: { get(): unknown; set(value: unknown): void };
}
```

The new decorators are **not compatible** with legacy `experimentalDecorators` — set `"experimentalDecorators": false` in tsconfig when migrating.'''
    ),
    (
        "javascript/react-error-boundaries",
        r'''How do error boundaries work in React? Can I use them with hooks?''',
        r'''<think>
Error boundaries are class components that catch JS errors in their child
component tree during rendering, lifecycle methods, and constructors. They
use componentDidCatch and getDerivedStateFromError. There's no hook equivalent
yet — you must use a class or a library like react-error-boundary. I should
show the class implementation and then the popular library approach which
provides a hook-friendly API.
</think>

Error boundaries catch rendering errors in child components. They **must be class components** (no hook equivalent exists):

**Class-based implementation:**

```jsx
class ErrorBoundary extends React.Component {
  state = { error: null, errorInfo: null };

  static getDerivedStateFromError(error) {
    // Update state to show fallback UI
    return { error };
  }

  componentDidCatch(error, errorInfo) {
    // Log to error reporting service
    errorService.report(error, errorInfo.componentStack);
  }

  render() {
    if (this.state.error) {
      return this.props.fallback?.(this.state.error) ?? (
        <div role="alert">
          <h2>Something went wrong</h2>
          <button onClick={() => this.setState({ error: null })}>
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// Usage
<ErrorBoundary fallback={(err) => <p>Error: {err.message}</p>}>
  <RiskyComponent />
</ErrorBoundary>
```

**Better: use `react-error-boundary` library (hooks-friendly):**

```jsx
import { ErrorBoundary, useErrorBoundary } from 'react-error-boundary';

function ErrorFallback({ error, resetErrorBoundary }) {
  return (
    <div role="alert">
      <p>Failed: {error.message}</p>
      <button onClick={resetErrorBoundary}>Retry</button>
    </div>
  );
}

function App() {
  return (
    <ErrorBoundary
      FallbackComponent={ErrorFallback}
      onReset={() => queryClient.clear()}
      resetKeys={[userId]} // auto-reset when userId changes
    >
      <Dashboard />
    </ErrorBoundary>
  );
}

// Imperatively trigger error boundary from a hook
function DataLoader() {
  const { showBoundary } = useErrorBoundary();

  useEffect(() => {
    fetchData().catch((err) => showBoundary(err));
  }, []);

  return <div>Loading...</div>;
}
```

**What error boundaries do NOT catch:**
- Event handlers (use try/catch)
- Async code (promises, setTimeout)
- Server-side rendering
- Errors in the boundary itself

Place boundaries at **route level** (catch page crashes) and around **individual widgets** (isolate failures).'''
    ),
    (
        "javascript/esm-cjs-interop",
        r'''I keep getting errors mixing ESM and CommonJS in Node.js. How do I handle interop correctly?''',
        r'''<think>
ESM and CJS interop in Node.js has specific rules. ESM can import CJS
defaults but not named exports (unless the CJS uses static-analyzable
exports). CJS cannot require() ESM — must use dynamic import(). File
extensions matter: .mjs is always ESM, .cjs is always CJS, .js follows
the nearest package.json "type" field. The main gotchas are __dirname
not existing in ESM and top-level await only in ESM.
</think>

ESM/CJS interop in Node.js follows strict rules. Here's the definitive guide:

**File resolution:**
| Extension | Module system |
|---|---|
| `.mjs` | Always ESM |
| `.cjs` | Always CJS |
| `.js` | Follows nearest `package.json` `"type"` field |
| No `"type"` field | CJS (default) |

**ESM importing CJS — works with caveats:**

```javascript
// lib.cjs (CommonJS)
module.exports = { hello: 'world', count: 42 };

// app.mjs (ESM)
import lib from './lib.cjs';       // default import = module.exports object
console.log(lib.hello);            // 'world'

// Named imports sometimes work (Node analyzes static patterns)
import { hello } from './lib.cjs'; // may work if Node can statically analyze
// Safer: destructure from default
const { hello, count } = lib;
```

**CJS importing ESM — must use dynamic import():**

```javascript
// utils.mjs (ESM)
export function greet(name) { return `Hello ${name}`; }

// app.cjs (CommonJS)
// require('./utils.mjs'); // ERROR: require() of ES Module not supported

// Correct: use dynamic import()
async function main() {
  const { greet } = await import('./utils.mjs');
  console.log(greet('Node'));
}
main();
```

**Common gotchas and fixes:**

```javascript
// __dirname doesn't exist in ESM
import { fileURLToPath } from 'node:url';
import { dirname } from 'node:path';
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// require() doesn't exist in ESM
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const pkg = require('./package.json'); // JSON import workaround
```

**Dual-package publishing (library authors):**

```json
{
  "name": "my-lib",
  "exports": {
    ".": {
      "import": "./dist/esm/index.js",
      "require": "./dist/cjs/index.cjs"
    }
  },
  "main": "./dist/cjs/index.cjs",
  "module": "./dist/esm/index.js",
  "type": "module"
}
```

**Rule of thumb:** New projects should use `"type": "module"` and ESM throughout. Only deal with CJS interop for legacy dependencies.'''
    ),
    (
        "javascript/bun-runtime-features",
        r'''What makes Bun different from Node.js? Show me Bun.serve and its file I/O.''',
        r'''<think>
Bun is an all-in-one JS runtime (JavaScriptCore engine, not V8) with
built-in bundler, transpiler, test runner, and package manager. Key
differences: faster startup, native TS/JSX support, Web API-first
design, Bun.serve for HTTP, Bun.file for zero-copy file I/O. It aims
for Node.js compatibility while being significantly faster. I'll show
the most distinctive APIs.
</think>

**Bun** is a fast all-in-one JS runtime built on JavaScriptCore (not V8):

**HTTP server with `Bun.serve`:**

```javascript
// server.ts — no imports needed, Bun has native TS support
const server = Bun.serve({
  port: 3000,
  async fetch(req) {
    const url = new URL(req.url);

    if (url.pathname === '/api/users' && req.method === 'GET') {
      const users = await Bun.file('./data/users.json').json();
      return Response.json(users);
    }

    if (url.pathname === '/api/upload' && req.method === 'POST') {
      const formData = await req.formData();
      const file = formData.get('file');
      await Bun.write(`./uploads/${file.name}`, file);
      return Response.json({ ok: true, size: file.size });
    }

    return new Response('Not Found', { status: 404 });
  },

  // WebSocket built-in
  websocket: {
    open(ws) { ws.subscribe('chat'); },
    message(ws, msg) { ws.publish('chat', msg); },
    close(ws) { ws.unsubscribe('chat'); },
  },
});

console.log(`Listening on ${server.url}`);
```

**File I/O — zero-copy with `Bun.file`:**

```javascript
// Read — lazy, doesn't load until consumed
const file = Bun.file('./large-dataset.csv');
console.log(file.size); // immediate, no read
console.log(file.type); // "text/csv"

const text = await file.text();      // as string
const bytes = await file.arrayBuffer(); // as binary
const stream = file.stream();        // as ReadableStream

// Write — extremely fast
await Bun.write('./output.txt', 'Hello Bun');
await Bun.write('./copy.csv', Bun.file('./source.csv')); // file-to-file copy
await Bun.write('./data.gz', Bun.gzipSync(text));        // compressed

// SQLite built-in (no npm install)
import { Database } from 'bun:sqlite';
const db = new Database('./app.db');
db.run('CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY, value TEXT)');
const insert = db.prepare('INSERT OR REPLACE INTO kv VALUES (?, ?)');
insert.run('name', 'Bun');
```

**Package management — fastest in class:**

```bash
bun install           # replaces npm install (~25x faster)
bun add zod           # add dependency
bun run dev           # run scripts
bunx create-next-app  # replaces npx
bun test              # built-in Jest-compatible test runner
```

**Key differences from Node.js:**
- Native TypeScript/JSX — no build step
- `Bun.file()` is lazy and zero-copy
- Built-in SQLite, test runner, bundler
- Web-standard APIs first (fetch, Response, WebSocket)
- ~4x faster startup, ~3x faster I/O in benchmarks'''
    ),
    (
        "javascript/deno-runtime",
        r'''Give me a practical overview of Deno — permissions, standard library, and how it differs from Node.js.''',
        r'''<think>
Deno is a secure JS/TS runtime by Ryan Dahl (Node.js creator). Key
differences: secure by default (explicit permissions), built-in TS,
Web API-first, URL imports (now also supports npm:), built-in toolchain
(fmt, lint, test, bench). The std library is audited and versioned.
Deno 2.0 added full Node.js/npm compatibility. I'll cover the permission
model, std library usage, and a practical server example.
</think>

**Deno** is a secure TypeScript-first runtime with batteries included:

**Permission model (secure by default):**

```bash
# Nothing is allowed unless explicitly granted
deno run server.ts
# Error: Requires net access to "0.0.0.0:3000"

# Grant specific permissions
deno run --allow-net=0.0.0.0:3000 --allow-read=./data server.ts

# Permission flags
# --allow-net=host:port   Network access (specific hosts)
# --allow-read=path       File system read
# --allow-write=path      File system write
# --allow-env=VAR         Environment variables
# --allow-run=cmd         Subprocess execution
# --allow-ffi             Foreign function interface
# -A                      Allow all (development only!)
```

**Standard library (audited, versioned):**

```typescript
// deno.json — import map
{
  "imports": {
    "@std/": "jsr:@std/"
  }
}
```

```typescript
import { serve } from "@std/http";
import { join } from "@std/path";
import { parse } from "@std/csv";
import { assert } from "@std/assert";

// HTTP server using Web APIs
Deno.serve({ port: 3000 }, async (req) => {
  const url = new URL(req.url);

  if (url.pathname === '/data') {
    const csv = await Deno.readTextFile('./data/records.csv');
    const records = parse(csv, { skipFirstRow: true });
    return Response.json(records);
  }

  // Serve static files
  const filePath = join('./public', url.pathname);
  try {
    const file = await Deno.open(filePath, { read: true });
    return new Response(file.readable);
  } catch {
    return new Response('Not Found', { status: 404 });
  }
});
```

**npm compatibility (Deno 2.0+):**

```typescript
// Use npm packages directly
import express from "npm:express@4";
import { z } from "npm:zod";

// Or in deno.json
{
  "imports": {
    "express": "npm:express@4",
    "zod": "npm:zod@3"
  }
}
```

**Built-in toolchain:**

```bash
deno fmt           # format (like prettier)
deno lint          # lint (built-in)
deno test          # test runner
deno bench         # benchmarking
deno compile       # single binary executable
deno task dev      # task runner (like npm scripts)
```

**Deno vs Node.js:**
| | Deno | Node.js |
|---|---|---|
| Security | Explicit permissions | Full access |
| TypeScript | Native | Needs build step |
| Package manager | URL/JSR imports | npm |
| Toolchain | Built-in (fmt, lint, test) | Third-party |
| APIs | Web-standard first | Custom APIs |'''
    ),
    (
        "javascript/node-worker-threads",
        r'''How do I use worker_threads in Node.js for parallel processing? Show a practical example.''',
        r'''<think>
Node.js worker_threads provides true multi-threading (unlike cluster which
forks processes). Workers share memory via SharedArrayBuffer and transfer
data via postMessage or MessageChannel. Common use: CPU-bound tasks like
image processing, crypto, parsing. The workerData option passes initial
data. I should show a practical worker pool pattern since spawning a worker
per task is expensive.
</think>

**`worker_threads`** provides true multi-threading in Node.js for CPU-bound work:

**Simple worker:**

```javascript
// hash-worker.js
const { parentPort, workerData } = require('node:worker_threads');
const crypto = require('node:crypto');

const hash = crypto.createHash('sha256')
  .update(workerData.input)
  .digest('hex');

parentPort.postMessage({ hash });
```

```javascript
// main.js
const { Worker } = require('node:worker_threads');

function hashAsync(input) {
  return new Promise((resolve, reject) => {
    const worker = new Worker('./hash-worker.js', {
      workerData: { input }
    });
    worker.on('message', resolve);
    worker.on('error', reject);
  });
}
```

**Worker pool (reuse threads):**

```javascript
const { Worker } = require('node:worker_threads');
const os = require('node:os');

class WorkerPool {
  #workers = [];
  #queue = [];

  constructor(workerScript, size = os.availableParallelism()) {
    for (let i = 0; i < size; i++) {
      this.#addWorker(workerScript);
    }
  }

  #addWorker(script) {
    const worker = new Worker(script);
    const entry = { worker, busy: false };
    worker.on('message', (result) => {
      entry.resolve(result);
      entry.busy = false;
      this.#processQueue();
    });
    worker.on('error', (err) => {
      entry.reject(err);
      entry.busy = false;
      this.#processQueue();
    });
    this.#workers.push(entry);
  }

  #processQueue() {
    if (this.#queue.length === 0) return;
    const idle = this.#workers.find(w => !w.busy);
    if (!idle) return;

    const { data, resolve, reject } = this.#queue.shift();
    idle.busy = true;
    idle.resolve = resolve;
    idle.reject = reject;
    idle.worker.postMessage(data);
  }

  exec(data) {
    return new Promise((resolve, reject) => {
      this.#queue.push({ data, resolve, reject });
      this.#processQueue();
    });
  }

  async destroy() {
    await Promise.all(this.#workers.map(w => w.worker.terminate()));
  }
}

// pool-worker.js
const { parentPort } = require('node:worker_threads');
parentPort.on('message', (data) => {
  // Heavy computation here
  const result = fibonacci(data.n);
  parentPort.postMessage({ n: data.n, result });
});

// Usage
const pool = new WorkerPool('./pool-worker.js', 4);
const results = await Promise.all(
  [40, 41, 42, 43, 44, 45].map(n => pool.exec({ n }))
);
console.log(results); // computed in parallel across 4 threads
await pool.destroy();
```

**When to use `worker_threads` vs `cluster`:**
- **worker_threads**: CPU-bound tasks, shared memory, thread pool pattern
- **cluster**: Multiple HTTP server instances, load balancing across cores'''
    ),
    (
        "javascript/node-cluster-multicore",
        r'''How do I use the Node.js cluster module to utilize all CPU cores for an HTTP server?''',
        r'''<think>
The cluster module forks the main process into worker processes (one per
core). The primary process manages workers and distributes connections.
It uses IPC under the hood. Workers share the server port via SO_REUSEPORT
or the primary round-robins connections. I should show the standard pattern
with graceful restart and sticky sessions consideration.
</think>

The **cluster** module forks your server across all CPU cores:

```javascript
const cluster = require('node:cluster');
const http = require('node:http');
const os = require('node:os');

const NUM_WORKERS = os.availableParallelism();

if (cluster.isPrimary) {
  console.log(`Primary ${process.pid} forking ${NUM_WORKERS} workers`);

  // Fork workers
  for (let i = 0; i < NUM_WORKERS; i++) {
    cluster.fork();
  }

  // Restart crashed workers
  cluster.on('exit', (worker, code, signal) => {
    console.log(`Worker ${worker.process.pid} died (${signal || code})`);
    if (!worker.exitedAfterDisconnect) {
      console.log('Starting replacement worker...');
      cluster.fork();
    }
  });

  // Graceful shutdown
  process.on('SIGTERM', () => {
    console.log('SIGTERM received, shutting down workers...');
    for (const id in cluster.workers) {
      cluster.workers[id].disconnect();
    }
  });

} else {
  // Workers share the same port
  const server = http.createServer((req, res) => {
    // Each request handled by one worker
    res.writeHead(200);
    res.end(`Handled by worker ${process.pid}\n`);
  });

  server.listen(3000, () => {
    console.log(`Worker ${process.pid} listening`);
  });

  // Graceful shutdown for individual worker
  process.on('SIGTERM', () => {
    server.close(() => process.exit(0));
  });
}
```

**Rolling restart (zero downtime):**

```javascript
// In the primary process
function rollingRestart() {
  const workerIds = Object.keys(cluster.workers);
  let index = 0;

  function restartNext() {
    if (index >= workerIds.length) return;
    const worker = cluster.workers[workerIds[index++]];
    if (!worker) return restartNext();

    console.log(`Restarting worker ${worker.process.pid}`);
    const replacement = cluster.fork();

    replacement.once('listening', () => {
      worker.disconnect();
      worker.once('exit', restartNext);
    });
  }

  restartNext();
}

// Trigger via signal
process.on('SIGUSR2', rollingRestart);
```

**Production tip:** For most apps, use **PM2** instead of raw cluster:

```bash
pm2 start app.js -i max    # auto-cluster across all cores
pm2 reload app.js           # zero-downtime restart
pm2 monit                   # monitoring dashboard
```

**Caveats:**
- Workers don't share memory (use Redis/DB for shared state)
- WebSocket sticky sessions needed if using socket.io (use `@socket.io/sticky`)
- Each worker is a separate process (~30-50 MB overhead each)'''
    ),
    (
        "javascript/snapshot-testing-strategies",
        r'''When should I use snapshot testing, and what are good strategies to avoid brittle snapshots?''',
        r'''<think>
Snapshot testing captures a serialized output and compares it against a
stored snapshot file. Good for: UI components, serialized data, CLI
output. Brittle when snapshots are too large, contain volatile data
(dates, IDs), or are blindly updated. Strategies: small focused snapshots,
inline snapshots, custom serializers, property matchers for dynamic values.
I'll cover Jest/Vitest patterns.
</think>

Snapshot testing captures output and detects unexpected changes. Here's how to use it effectively:

**When to use snapshots:**
- UI component rendered output
- Serialized data structures (API responses, configs)
- Error messages and CLI output
- NOT for logic testing — use assertions instead

**Focused snapshots (not full component trees):**

```javascript
// BAD — entire component tree, 200+ lines, breaks on any change
expect(render(<Dashboard />)).toMatchSnapshot();

// GOOD — focused on specific output
test('renders user greeting', () => {
  const { getByRole } = render(<UserCard name="Alice" role="admin" />);
  expect(getByRole('heading')).toMatchInlineSnapshot(`
    <h2>
      Alice
      <span class="badge">admin</span>
    </h2>
  `);
});
```

**Handle dynamic values with property matchers:**

```javascript
test('creates user with correct shape', () => {
  const user = createUser({ name: 'Alice' });

  expect(user).toMatchSnapshot({
    id: expect.any(String),           // ignore specific ID
    createdAt: expect.any(Date),      // ignore timestamp
    name: expect.stringContaining('Alice'),
  });
});

// Resulting snapshot stores:
// { id: Any<String>, createdAt: Any<Date>, name: StringContaining "Alice" }
```

**Custom serializers for cleaner snapshots:**

```javascript
// vitest.config.js or jest.config.js
export default {
  snapshotSerializers: ['./test/serializers/strip-ids.js'],
};

// strip-ids.js
module.exports = {
  test(val) { return val && typeof val.id === 'string'; },
  serialize(val, config, indent, depth, refs, printer) {
    const copy = { ...val, id: '[ID]' };
    return printer(copy, config, indent, depth, refs);
  },
};
```

**Inline snapshots (review in-place):**

```javascript
test('formats currency', () => {
  expect(formatCurrency(1234.5, 'USD')).toMatchInlineSnapshot(`"$1,234.50"`);
  expect(formatCurrency(1234.5, 'EUR')).toMatchInlineSnapshot(`"€1,234.50"`);
  // Vitest/Jest auto-fills these on first run
});
```

**Anti-patterns to avoid:**
1. Snapshots > 50 lines — too large to review meaningfully
2. Blindly running `--update` without reviewing diffs
3. Snapshot tests as the only test for a component
4. Snapshots containing volatile data (timestamps, random IDs, absolute paths)

**Rule:** If you wouldn't carefully review the diff in a PR, the snapshot is too big.'''
    ),
    (
        "javascript/property-based-testing-fast-check",
        r'''How does property-based testing with fast-check work in JavaScript? Show me a real example.''',
        r'''<think>
Property-based testing generates random inputs and verifies invariants
(properties) hold for all of them, rather than testing specific examples.
fast-check is the main JS library for this. It generates arbitraries
(random values), runs many iterations, and shrinks failing cases to
minimal reproductions. Good for: parsers, serializers, math functions,
data transformations where properties are known.
</think>

**Property-based testing** verifies invariants hold for all generated inputs, not just hand-picked examples:

```bash
npm install -D fast-check
```

**Basic example — testing a sort function:**

```javascript
import fc from 'fast-check';
import { describe, it, expect } from 'vitest';

describe('Array.sort', () => {
  it('output has same length as input', () => {
    fc.assert(
      fc.property(fc.array(fc.integer()), (arr) => {
        expect(arr.sort().length).toBe(arr.length);
      })
    );
  });

  it('output is ordered', () => {
    fc.assert(
      fc.property(fc.array(fc.integer()), (arr) => {
        const sorted = [...arr].sort((a, b) => a - b);
        for (let i = 1; i < sorted.length; i++) {
          expect(sorted[i]).toBeGreaterThanOrEqual(sorted[i - 1]);
        }
      })
    );
  });

  it('output is a permutation of input', () => {
    fc.assert(
      fc.property(fc.array(fc.integer()), (arr) => {
        const sorted = [...arr].sort((a, b) => a - b);
        expect(sorted).toEqual(expect.arrayContaining(arr));
        expect(arr).toEqual(expect.arrayContaining(sorted));
      })
    );
  });
});
```

**Real-world: testing encode/decode roundtrip:**

```javascript
describe('JSON codec roundtrip', () => {
  const userArbitrary = fc.record({
    name: fc.string({ minLength: 1, maxLength: 100 }),
    age: fc.integer({ min: 0, max: 150 }),
    email: fc.emailAddress(),
    tags: fc.array(fc.string(), { maxLength: 10 }),
  });

  it('encode then decode returns original', () => {
    fc.assert(
      fc.property(userArbitrary, (user) => {
        const encoded = encodeUser(user);
        const decoded = decodeUser(encoded);
        expect(decoded).toEqual(user);
      }),
      { numRuns: 1000 } // run 1000 random inputs
    );
  });
});
```

**Testing a URL parser:**

```javascript
it('parse(format(url)) === url', () => {
  fc.assert(
    fc.property(
      fc.webUrl({ withFragments: true, withQueryParameters: true }),
      (url) => {
        const parsed = new URL(url);
        expect(parsed.href).toBe(new URL(parsed.href).href);
      }
    )
  );
});
```

**Custom arbitrary for domain objects:**

```javascript
const moneyArbitrary = fc.record({
  amount: fc.integer({ min: 0, max: 999999 }),
  currency: fc.constantFrom('USD', 'EUR', 'GBP'),
});

it('addition is commutative', () => {
  fc.assert(
    fc.property(moneyArbitrary, moneyArbitrary, (a, b) => {
      fc.pre(a.currency === b.currency); // precondition: same currency
      expect(addMoney(a, b)).toEqual(addMoney(b, a));
    })
  );
});
```

**Key benefit:** When a test fails, fast-check **shrinks** the input to the minimal failing case, making debugging trivial.'''
    ),
    (
        "javascript/typescript-generic-constraints",
        r'''How do TypeScript generic constraints work? Show me practical patterns beyond basic extends.''',
        r'''<think>
Generic constraints use `extends` to restrict type parameters. Beyond basic
`T extends SomeType`, there are: keyof constraints, conditional types with
constraints, multiple constraints via intersection, constrained defaults,
and the extends + infer pattern. I should show practical patterns like
type-safe object picking, constrained factory functions, and recursive
generic constraints.
</think>

Generic constraints restrict what types a generic parameter can accept:

**Basic to advanced patterns:**

```typescript
// 1. keyof constraint — type-safe property access
function getProperty<T, K extends keyof T>(obj: T, key: K): T[K] {
  return obj[key];
}

const user = { name: 'Alice', age: 30 };
getProperty(user, 'name');  // string
getProperty(user, 'age');   // number
getProperty(user, 'email'); // Error: "email" not in "name" | "age"

// 2. Multiple constraints via intersection
interface HasId { id: string }
interface HasTimestamp { createdAt: Date }

function processEntity<T extends HasId & HasTimestamp>(entity: T): void {
  console.log(entity.id, entity.createdAt); // both guaranteed
}

// 3. Constrained return type that depends on input
function create<T extends 'user' | 'post'>(
  type: T
): T extends 'user' ? { name: string } : { title: string } {
  if (type === 'user') return { name: '' } as any;
  return { title: '' } as any;
}

const u = create('user');  // { name: string }
const p = create('post');  // { title: string }

// 4. Recursive generic constraint
type JSONValue = string | number | boolean | null | JSONValue[] | { [k: string]: JSONValue };

function deepFreeze<T extends JSONValue>(obj: T): Readonly<T> {
  if (typeof obj === 'object' && obj !== null) {
    Object.values(obj).forEach(deepFreeze);
    return Object.freeze(obj) as Readonly<T>;
  }
  return obj;
}

// 5. Constrained generics with defaults
interface QueryOptions<T extends Record<string, unknown> = Record<string, unknown>> {
  filters: Partial<T>;
  sort?: keyof T;
  limit?: number;
}

function query<T extends Record<string, unknown>>(
  table: string,
  opts: QueryOptions<T>
): T[] {
  // sort is constrained to keys of T
  return [] as T[];
}

interface User { name: string; age: number; active: boolean }
query<User>('users', {
  filters: { active: true },
  sort: 'age',      // OK — keyof User
  // sort: 'email', // Error — not in User
});

// 6. Generic constraint on constructor
function createInstance<T>(
  Ctor: new (...args: any[]) => T,
  ...args: ConstructorParameters<typeof Ctor extends new (...a: infer A) => any ? { new(...a: A): T } : never>
): T {
  return new Ctor(...args);
}

// 7. Mapped type with constraint
type Optional<T, K extends keyof T> = Omit<T, K> & Partial<Pick<T, K>>;

type UserOptionalAge = Optional<User, 'age'>;
// { name: string; active: boolean; age?: number }
```

**Rule of thumb:** Use constraints to make impossible states unrepresentable at the type level. If a function only makes sense for certain inputs, encode that restriction in the generic constraint.'''
    ),
    (
        "javascript/typescript-infer-keyword",
        r'''Explain TypeScript's `infer` keyword with practical examples. I find it confusing.''',
        r'''<think>
The `infer` keyword declares a type variable inside a conditional type's
extends clause. It lets you "extract" a type from a larger structure.
Think of it as pattern matching for types. Common uses: extracting return
types, promise unwrapping, tuple manipulation, function parameter
extraction. I should build from simple to complex examples.
</think>

**`infer`** lets you extract (pattern-match) types inside conditional types:

```typescript
// Basic pattern: T extends SomePattern<infer U> ? U : Fallback
// "If T matches this shape, extract U from it"

// 1. Extract return type (how ReturnType<T> works internally)
type MyReturnType<T> = T extends (...args: any[]) => infer R ? R : never;

type A = MyReturnType<() => string>;        // string
type B = MyReturnType<(x: number) => void>; // void

// 2. Extract Promise inner type (recursive unwrap)
type Awaited<T> = T extends Promise<infer U> ? Awaited<U> : T;

type C = Awaited<Promise<string>>;              // string
type D = Awaited<Promise<Promise<number>>>;     // number (recursive!)

// 3. Extract array element type
type ElementOf<T> = T extends (infer U)[] ? U : never;

type E = ElementOf<string[]>;    // string
type F = ElementOf<[1, 'a', true]>; // 1 | 'a' | true

// 4. Extract first and rest of a tuple
type First<T extends any[]> = T extends [infer F, ...any[]] ? F : never;
type Rest<T extends any[]> = T extends [any, ...infer R] ? R : never;

type G = First<[1, 2, 3]>; // 1
type H = Rest<[1, 2, 3]>;  // [2, 3]

// 5. Extract event type from handler
type EventMap = {
  click: { x: number; y: number };
  keydown: { key: string; code: string };
};

type HandlerParam<T> = T extends (event: infer E) => void ? E : never;
type ClickHandler = (event: EventMap['click']) => void;
type ClickEvent = HandlerParam<ClickHandler>; // { x: number; y: number }

// 6. Extract string template parts
type ExtractRouteParams<T extends string> =
  T extends `${string}:${infer Param}/${infer Rest}`
    ? Param | ExtractRouteParams<Rest>
    : T extends `${string}:${infer Param}`
      ? Param
      : never;

type Params = ExtractRouteParams<'/users/:userId/posts/:postId'>;
// "userId" | "postId"

// 7. Practical: type-safe API response extractor
type ApiResponse<T> = { data: T; status: number };

type ExtractData<T> = T extends ApiResponse<infer D> ? D : never;

type UserResponse = ApiResponse<{ name: string; age: number }>;
type UserData = ExtractData<UserResponse>; // { name: string; age: number }

// 8. Multiple infer positions
type FunctionParts<T> = T extends (...args: infer A) => infer R
  ? { args: A; return: R }
  : never;

type Parts = FunctionParts<(x: string, y: number) => boolean>;
// { args: [x: string, y: number]; return: boolean }
```

**Mental model:** `infer X` is a "capture group" in type-level pattern matching. It says "whatever type appears in this position, capture it as X."'''
    ),
    (
        "javascript/typescript-module-augmentation",
        r'''How do I extend third-party TypeScript types using module augmentation and declaration merging?''',
        r'''<think>
Module augmentation lets you add types to existing modules without modifying
source. Uses `declare module 'x'` to merge additional declarations into a
module's type space. Common for: adding custom properties to Express req,
extending library interfaces, adding global types. Also covers interface
merging, namespace augmentation, and ambient declarations. I should show
the Express pattern since it's the most common real-world case.
</think>

**Module augmentation** lets you extend third-party types without modifying their source:

**Extend Express Request (most common pattern):**

```typescript
// types/express.d.ts
import { User } from '../models/user';

declare module 'express-serve-static-core' {
  interface Request {
    user?: User;
    requestId: string;
  }
}

// Now works everywhere without casts
app.use((req, res, next) => {
  req.requestId = crypto.randomUUID(); // no error
  req.user = await authenticate(req);  // typed as User | undefined
  next();
});
```

**Extend a library's types:**

```typescript
// Extend Zod with a custom method
import { ZodString } from 'zod';

declare module 'zod' {
  interface ZodString {
    slug(): ZodString;
  }
}

// Implementation
ZodString.prototype.slug = function () {
  return this.regex(/^[a-z0-9]+(?:-[a-z0-9]+)*$/, 'Invalid slug');
};

// Usage
const schema = z.string().slug(); // fully typed
```

**Augment global scope:**

```typescript
// types/global.d.ts
declare global {
  interface Window {
    __APP_CONFIG__: {
      apiUrl: string;
      version: string;
    };
  }

  // Add a global function
  function structuredClone<T>(value: T): T;
}

export {}; // Required — makes this a module

// Now available everywhere
const config = window.__APP_CONFIG__; // typed
```

**Namespace augmentation (enums, constants):**

```typescript
// Original library exports
// declare enum Color { Red, Green, Blue }

declare module 'color-lib' {
  enum Color {
    Purple = 100,
    Orange = 101,
  }
}

import { Color } from 'color-lib';
Color.Purple; // works, value 100
```

**Interface merging (same file):**

```typescript
// Merge additional fields into an interface
interface Config {
  host: string;
  port: number;
}

interface Config {
  debug?: boolean;
  logLevel?: 'info' | 'warn' | 'error';
}

// Result: Config has all four properties

// Works with generics too
interface EventEmitter<T = any> {
  on(event: string, handler: (data: T) => void): void;
}
interface EventEmitter<T = any> {
  once(event: string, handler: (data: T) => void): void;
}
```

**Setup in tsconfig.json:**

```json
{
  "compilerOptions": {
    "typeRoots": ["./node_modules/@types", "./types"]
  },
  "include": ["src/**/*", "types/**/*"]
}
```

**Key rule:** The `declare module` block must be in a file that is itself a module (has at least one `import` or `export`). Otherwise it becomes an ambient declaration and won't merge correctly.'''
    ),
    (
        "javascript/react-performance-optimization",
        r'''When should I use useMemo, useCallback, and React.memo? I hear conflicting advice about premature optimization.''',
        r'''<think>
The key insight is that these hooks have a cost (memory + comparison overhead)
and should only be used when there's a measurable performance problem. React
re-renders are usually fast. The three tools serve different purposes:
memo() prevents child re-renders when props haven't changed, useMemo()
caches expensive computations, useCallback() stabilizes function references
for memo'd children. I should give clear guidelines on when each is worth it.
</think>

These tools are not "always use" — they have overhead. Here's when each actually helps:

**`React.memo` — skip re-rendering when props are unchanged:**

```jsx
// WORTH IT: expensive child in a frequently re-rendering parent
const ExpensiveChart = React.memo(function Chart({ data, config }) {
  // Heavy SVG rendering, thousands of elements
  return <svg>{data.map(renderPoint)}</svg>;
});

// NOT WORTH IT: simple/cheap components
const Label = React.memo(({ text }) => <span>{text}</span>); // overhead > savings
```

**`useMemo` — cache expensive computations:**

```jsx
function SearchResults({ items, query }) {
  // WORTH IT: filtering/sorting thousands of items
  const filtered = useMemo(
    () => items.filter(item =>
      item.name.toLowerCase().includes(query.toLowerCase())
    ).sort((a, b) => a.rank - b.rank),
    [items, query]
  );

  // NOT WORTH IT: trivial computation
  const fullName = useMemo(
    () => `${first} ${last}`, // cheaper than the memo overhead itself
    [first, last]
  );

  return <List items={filtered} />;
}
```

**`useCallback` — stabilize function identity for memo'd children:**

```jsx
function Parent() {
  const [count, setCount] = useState(0);
  const [text, setText] = useState('');

  // Without useCallback: new function every render → MemoChild re-renders
  // With useCallback: stable reference → MemoChild skips re-render
  const handleClick = useCallback((id) => {
    setCount(c => c + 1);
  }, []); // no deps needed with updater function

  return (
    <>
      <input value={text} onChange={(e) => setText(e.target.value)} />
      <MemoChild onClick={handleClick} /> {/* won't re-render on text change */}
    </>
  );
}

const MemoChild = React.memo(function Child({ onClick }) {
  console.log('Child rendered'); // only once, not on every keystroke
  return <ExpensiveList onClick={onClick} />;
});
```

**Decision framework:**

```
Is there a MEASURED performance problem?
  No  → Don't optimize. React re-renders are fast.
  Yes → What's causing it?
    Expensive child re-rendering → React.memo on child
    Expensive computation → useMemo
    Memo'd child re-renders due to function prop → useCallback

useCallback WITHOUT memo is useless:
  // This does nothing useful — Child re-renders anyway
  const handler = useCallback(() => {}, []);
  return <Child onClick={handler} />; // Child is not memo'd!
```

**Profile first:** Use React DevTools Profiler to identify which components re-render unnecessarily and how long they take. If a re-render takes < 1ms, memoization overhead isn't worth it.'''
    ),
    (
        "javascript/react-usereducer-state-machines",
        r'''Show me how to use useReducer as a state machine pattern in React for complex UI state.''',
        r'''<think>
useReducer is perfect for state machines where transitions depend on the
current state. The pattern: define states, valid transitions, and use a
discriminated union for the state shape. This prevents impossible states
(e.g., loading + error simultaneously) and makes logic explicit. I'll
show a practical form submission flow with idle, submitting, success,
error states.
</think>

**`useReducer` as a state machine** eliminates impossible states and makes transitions explicit:

```typescript
// Define states as a discriminated union — impossible states are unrepresentable
type FormState =
  | { status: 'idle' }
  | { status: 'validating'; data: FormData }
  | { status: 'submitting'; data: FormData }
  | { status: 'success'; result: ApiResult }
  | { status: 'error'; error: string; data: FormData };

type FormAction =
  | { type: 'VALIDATE'; data: FormData }
  | { type: 'VALIDATION_PASSED'; data: FormData }
  | { type: 'SUBMIT' }
  | { type: 'SUCCESS'; result: ApiResult }
  | { type: 'FAILURE'; error: string }
  | { type: 'RETRY' }
  | { type: 'RESET' };

function formReducer(state: FormState, action: FormAction): FormState {
  switch (state.status) {
    case 'idle':
      if (action.type === 'VALIDATE') return { status: 'validating', data: action.data };
      return state;

    case 'validating':
      if (action.type === 'VALIDATION_PASSED') return { status: 'submitting', data: action.data };
      if (action.type === 'FAILURE') return { status: 'error', error: action.error, data: state.data };
      return state;

    case 'submitting':
      if (action.type === 'SUCCESS') return { status: 'success', result: action.result };
      if (action.type === 'FAILURE') return { status: 'error', error: action.error, data: state.data };
      return state;

    case 'error':
      if (action.type === 'RETRY') return { status: 'submitting', data: state.data };
      if (action.type === 'RESET') return { status: 'idle' };
      return state;

    case 'success':
      if (action.type === 'RESET') return { status: 'idle' };
      return state;
  }
}
```

```tsx
function RegistrationForm() {
  const [state, dispatch] = useReducer(formReducer, { status: 'idle' });

  async function handleSubmit(formData: FormData) {
    dispatch({ type: 'VALIDATE', data: formData });

    const errors = validate(formData);
    if (errors.length) {
      dispatch({ type: 'FAILURE', error: errors.join(', ') });
      return;
    }

    dispatch({ type: 'VALIDATION_PASSED', data: formData });

    try {
      const result = await api.register(formData);
      dispatch({ type: 'SUCCESS', result });
    } catch (err) {
      dispatch({ type: 'FAILURE', error: err.message });
    }
  }

  return (
    <div>
      {state.status === 'idle' && (
        <Form onSubmit={handleSubmit} />
      )}
      {state.status === 'submitting' && <Spinner />}
      {state.status === 'error' && (
        <div>
          <p className="error">{state.error}</p>
          <button onClick={() => dispatch({ type: 'RETRY' })}>Retry</button>
          <button onClick={() => dispatch({ type: 'RESET' })}>Start Over</button>
        </div>
      )}
      {state.status === 'success' && (
        <p>Welcome, {state.result.user.name}!</p>
      )}
    </div>
  );
}
```

**Why this beats `useState` booleans:**
- `useState`: `isLoading && isError` — impossible but representable
- `useReducer`: `status: 'submitting'` — can only be in one state at a time
- Transitions are guarded — can't go from `idle` directly to `success`
- The reducer is pure and trivially testable'''
    ),
    (
        "javascript/server-sent-events",
        r'''How do I implement Server-Sent Events (SSE) in Node.js? When should I use SSE over WebSockets?''',
        r'''<think>
SSE is a one-way server-to-client push protocol over HTTP. Simpler than
WebSockets — uses standard HTTP, auto-reconnects, supports event types
and IDs. Good for: live feeds, notifications, progress updates. Not for:
bidirectional communication, binary data. I'll show the Node.js server
side and browser client, plus reconnection handling.
</think>

**Server-Sent Events** provide server-to-client push over plain HTTP:

**Node.js server (no libraries needed):**

```javascript
import http from 'node:http';

const clients = new Set();

const server = http.createServer((req, res) => {
  if (req.url === '/events') {
    // SSE headers
    res.writeHead(200, {
      'Content-Type': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'Connection': 'keep-alive',
      'Access-Control-Allow-Origin': '*',
    });

    // Send initial data
    res.write(`data: ${JSON.stringify({ type: 'connected' })}\n\n`);

    // Track client
    clients.add(res);
    req.on('close', () => clients.delete(res));
    return;
  }

  if (req.url === '/broadcast' && req.method === 'POST') {
    let body = '';
    req.on('data', chunk => body += chunk);
    req.on('end', () => {
      broadcast('message', JSON.parse(body));
      res.writeHead(200).end('OK');
    });
    return;
  }

  res.writeHead(404).end();
});

function broadcast(event, data) {
  const payload = [
    `event: ${event}`,
    `data: ${JSON.stringify(data)}`,
    `id: ${Date.now()}`,
    '', '' // double newline terminates the event
  ].join('\n');

  for (const client of clients) {
    client.write(payload);
  }
}

// Heartbeat to detect dead connections
setInterval(() => {
  for (const client of clients) {
    client.write(': heartbeat\n\n'); // comment line, ignored by client
  }
}, 30_000);

server.listen(3000);
```

**Browser client:**

```javascript
const es = new EventSource('/events');

// Default 'message' event
es.onmessage = (e) => {
  const data = JSON.parse(e.data);
  console.log('Message:', data);
};

// Named events
es.addEventListener('notification', (e) => {
  const data = JSON.parse(e.data);
  showNotification(data.title, data.body);
});

// Auto-reconnect is built-in. Use Last-Event-ID for resuming:
es.onerror = (e) => {
  console.log('Connection lost, auto-reconnecting...');
  // EventSource automatically reconnects with Last-Event-ID header
};

// Close when done
es.close();
```

**Express version (concise):**

```javascript
app.get('/events', (req, res) => {
  res.setHeader('Content-Type', 'text/event-stream');
  res.setHeader('Cache-Control', 'no-cache');
  res.flushHeaders();

  const intervalId = setInterval(() => {
    res.write(`data: ${JSON.stringify({ time: new Date() })}\n\n`);
  }, 1000);

  req.on('close', () => clearInterval(intervalId));
});
```

**SSE vs WebSocket:**

| | SSE | WebSocket |
|---|---|---|
| Direction | Server → Client | Bidirectional |
| Protocol | HTTP | Upgrade to WS |
| Reconnect | Automatic | Manual |
| Data format | Text only | Text + Binary |
| Proxy/CDN | Works everywhere | Often blocked |
| Use case | Feeds, notifications | Chat, games, collab |

**Choose SSE** when you only need server-to-client push — it's simpler and works through more infrastructure.'''
    ),
    (
        "javascript/node-diagnostic-channels",
        r'''What are Node.js diagnostic channels and how do I use them for observability?''',
        r'''<think>
diagnostics_channel is a Node.js core module (stable since v19.2) that
provides a pub/sub mechanism for diagnostic events within the process.
Libraries publish events to named channels, and consumers subscribe to
collect telemetry without modifying library code. HTTP, net, and other
core modules publish events. It's the foundation for APM tools. I should
show both subscribing to built-in channels and creating custom ones.
</think>

**`diagnostics_channel`** is Node.js's built-in pub/sub for observability — no monkey-patching needed:

```javascript
import dc from 'node:diagnostics_channel';

// 1. Subscribe to built-in HTTP request tracing
const httpStart = dc.channel('http.client.request.start');
const httpEnd = dc.channel('http.client.response.finish');

httpStart.subscribe(({ request }) => {
  request.__startTime = performance.now();
  console.log(`→ ${request.method} ${request.host}${request.path}`);
});

httpEnd.subscribe(({ request, response }) => {
  const duration = (performance.now() - request.__startTime).toFixed(1);
  console.log(`← ${response.statusCode} ${request.path} (${duration}ms)`);
});

// Now ANY http request is automatically traced
await fetch('https://api.example.com/users');
// → GET api.example.com/users
// ← 200 /users (142.3ms)
```

**Built-in channels (Node 20+):**
- `http.client.request.start` / `.error`
- `http.client.response.finish`
- `http.server.request.start` / `.finish`
- `net.client.socket` / `net.server.socket`
- `module.require.start` / `.end` (CJS)
- `module.import.start` / `.end` (ESM)
- `worker_threads`

**2. Create custom diagnostic channels for your app:**

```javascript
// db-client.js — library publishes events
import dc from 'node:diagnostics_channel';

const queryChannel = dc.channel('myapp.db.query');

export async function query(sql, params) {
  const start = performance.now();
  const context = { sql, params, start };

  if (queryChannel.hasSubscribers) {
    queryChannel.publish({ ...context, phase: 'start' });
  }

  try {
    const result = await pool.query(sql, params);
    if (queryChannel.hasSubscribers) {
      queryChannel.publish({
        ...context,
        phase: 'end',
        duration: performance.now() - start,
        rowCount: result.rowCount,
      });
    }
    return result;
  } catch (err) {
    if (queryChannel.hasSubscribers) {
      queryChannel.publish({ ...context, phase: 'error', error: err });
    }
    throw err;
  }
}
```

```javascript
// observability.js — consumer collects metrics
import dc from 'node:diagnostics_channel';

const slowQueryThreshold = 100; // ms

dc.channel('myapp.db.query').subscribe((event) => {
  if (event.phase === 'end') {
    metrics.histogram('db.query.duration', event.duration);
    if (event.duration > slowQueryThreshold) {
      logger.warn('Slow query', { sql: event.sql, duration: event.duration });
    }
  }
  if (event.phase === 'error') {
    metrics.increment('db.query.errors');
  }
});
```

**3. TracingChannel for structured start/end/error:**

```javascript
const tracing = dc.tracingChannel('myapp.http.handler');

// Automatically wraps async functions with start/end/error events
app.use((req, res, next) => {
  tracing.tracePromise(async () => {
    return await handleRequest(req, res);
  }, { req, res });
});
```

**Why use diagnostic channels over custom events:**
- Zero overhead when no subscribers (checked with `hasSubscribers`)
- Standardized across the ecosystem — APM tools auto-subscribe
- No need to modify library code to add observability'''
    ),
    (
        "javascript/custom-eslint-rule",
        r'''How do I create a custom ESLint rule? I need to enforce a project-specific convention.''',
        r'''<think>
Custom ESLint rules are visitor-pattern functions that traverse the AST.
With ESLint's flat config (v9+), you create a rule in a local plugin.
The rule exports a create function returning an AST visitor. I should
show a practical example — like banning console.log in production code,
or enforcing naming conventions — with the modern flat config approach.
</think>

Custom ESLint rules use the AST visitor pattern. Here's a complete example with flat config (ESLint 9+):

**Example: ban `TODO` comments without a ticket reference:**

```javascript
// eslint-rules/no-unlinked-todo.js
export const noUnlinkedTodo = {
  meta: {
    type: 'suggestion',
    docs: {
      description: 'Require TODO comments to reference a ticket (e.g., TODO(PROJ-123))',
    },
    messages: {
      missingTicket: 'TODO comment must reference a ticket: TODO(PROJ-XXX)',
    },
    schema: [
      {
        type: 'object',
        properties: {
          pattern: { type: 'string' } // custom ticket pattern
        },
        additionalProperties: false,
      },
    ],
  },
  create(context) {
    const pattern = context.options[0]?.pattern || '[A-Z]+-\\d+';
    const ticketRegex = new RegExp(`TODO\\(${pattern}\\)`);

    return {
      Program() {
        const sourceCode = context.sourceCode;
        const comments = sourceCode.getAllComments();

        for (const comment of comments) {
          const text = comment.value;
          if (/\bTODO\b/.test(text) && !ticketRegex.test(text)) {
            context.report({
              node: comment,
              messageId: 'missingTicket',
            });
          }
        }
      },
    };
  },
};
```

**Another rule: enforce async function naming:**

```javascript
// eslint-rules/async-function-suffix.js
export const asyncFunctionSuffix = {
  meta: {
    type: 'suggestion',
    messages: {
      missingSuffix: 'Async function "{{name}}" should end with "Async"',
    },
    fixable: null,
  },
  create(context) {
    function check(node) {
      if (!node.async) return;
      const name = node.id?.name || node.parent?.id?.name;
      if (name && !name.endsWith('Async') && !name.startsWith('handle')) {
        context.report({ node, messageId: 'missingSuffix', data: { name } });
      }
    }
    return {
      FunctionDeclaration: check,
      FunctionExpression: check,
      ArrowFunctionExpression: check,
    };
  },
};
```

**Wire it up in flat config:**

```javascript
// eslint.config.js
import { noUnlinkedTodo } from './eslint-rules/no-unlinked-todo.js';
import { asyncFunctionSuffix } from './eslint-rules/async-function-suffix.js';

const localPlugin = {
  rules: {
    'no-unlinked-todo': noUnlinkedTodo,
    'async-function-suffix': asyncFunctionSuffix,
  },
};

export default [
  {
    plugins: { local: localPlugin },
    rules: {
      'local/no-unlinked-todo': ['error', { pattern: 'PROJ-\\d+' }],
      'local/async-function-suffix': 'warn',
    },
  },
];
```

**Testing your rule:**

```javascript
import { RuleTester } from 'eslint';
import { noUnlinkedTodo } from './no-unlinked-todo.js';

const tester = new RuleTester();
tester.run('no-unlinked-todo', noUnlinkedTodo, {
  valid: [
    '// TODO(PROJ-123): fix this',
    '// This is a regular comment',
  ],
  invalid: [
    { code: '// TODO: fix later', errors: [{ messageId: 'missingTicket' }] },
    { code: '/* TODO fix this */', errors: [{ messageId: 'missingTicket' }] },
  ],
});
```

**Key:** Use https://astexplorer.net with `@typescript-eslint/parser` to explore the AST and find the right visitor node types for your rule.'''
    ),
    (
        "javascript/monorepo-workspaces",
        r'''How do I set up a JavaScript/TypeScript monorepo with workspaces? What are the tradeoffs?''',
        r'''<think>
Monorepos manage multiple packages in one repo. npm/yarn/pnpm all support
workspaces natively. Key decisions: package manager choice, build tool
(Turborepo, Nx, or plain scripts), shared config (tsconfig, eslint),
versioning strategy. pnpm workspaces are the most popular now due to
strict node_modules. I'll show a practical pnpm setup with Turborepo
since that's the most common modern stack.
</think>

**Monorepo with pnpm workspaces + Turborepo** (most popular modern setup):

**Project structure:**

```
my-monorepo/
├── package.json
├── pnpm-workspace.yaml
├── turbo.json
├── packages/
│   ├── shared/          # @myapp/shared — types, utils
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   └── src/
│   ├── ui/              # @myapp/ui — component library
│   │   ├── package.json
│   │   └── src/
│   └── config/          # @myapp/config — shared tsconfig, eslint
│       ├── tsconfig.base.json
│       └── eslint.base.js
├── apps/
│   ├── web/             # Next.js frontend
│   │   └── package.json
│   └── api/             # Express backend
│       └── package.json
```

**pnpm-workspace.yaml:**

```yaml
packages:
  - 'packages/*'
  - 'apps/*'
```

**Root package.json:**

```json
{
  "private": true,
  "scripts": {
    "dev": "turbo dev",
    "build": "turbo build",
    "lint": "turbo lint",
    "test": "turbo test"
  },
  "devDependencies": {
    "turbo": "^2.0.0"
  }
}
```

**turbo.json (build orchestration):**

```json
{
  "$schema": "https://turbo.build/schema.json",
  "tasks": {
    "build": {
      "dependsOn": ["^build"],
      "outputs": ["dist/**"]
    },
    "dev": {
      "cache": false,
      "persistent": true
    },
    "lint": {},
    "test": {
      "dependsOn": ["build"]
    }
  }
}
```

**Internal package (packages/shared/package.json):**

```json
{
  "name": "@myapp/shared",
  "version": "0.0.0",
  "private": true,
  "main": "./dist/index.js",
  "types": "./dist/index.d.ts",
  "scripts": {
    "build": "tsc",
    "dev": "tsc --watch"
  }
}
```

**Consuming internal packages (apps/web/package.json):**

```json
{
  "name": "@myapp/web",
  "dependencies": {
    "@myapp/shared": "workspace:*",
    "@myapp/ui": "workspace:*"
  }
}
```

```typescript
// apps/web/src/page.tsx — just import like any package
import { formatDate, type User } from '@myapp/shared';
import { Button } from '@myapp/ui';
```

**Shared TypeScript config (packages/config/tsconfig.base.json):**

```json
{
  "compilerOptions": {
    "strict": true,
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true
  }
}
```

**Tradeoffs:**

| Pros | Cons |
|---|---|
| Shared code without publishing | Longer CI times (mitigated by Turbo cache) |
| Atomic cross-package changes | Tooling complexity |
| Single lint/test/format config | Large `node_modules` (pnpm helps) |
| Consistent dependency versions | Learning curve for team |'''
    ),
    (
        "javascript/zero-downtime-deployment-node",
        r'''How do I achieve zero-downtime deployments for a Node.js application?''',
        r'''<think>
Zero-downtime deployment means deploying new code without dropping
existing connections. Strategies: cluster module with rolling restarts,
PM2 reload, container orchestration (K8s rolling update), load balancer
health checks, graceful shutdown handling. The key is draining existing
connections before killing the old process. I should cover both simple
(PM2) and production (container) approaches plus the critical graceful
shutdown code.
</think>

Zero-downtime deployment requires **graceful shutdown** + **rolling replacement**. Here's the complete approach:

**1. Graceful shutdown (required for any strategy):**

```javascript
import http from 'node:http';

const server = http.createServer(app);
let isShuttingDown = false;

server.listen(3000);

// Handle shutdown signals
for (const signal of ['SIGTERM', 'SIGINT']) {
  process.on(signal, () => gracefulShutdown(signal));
}

async function gracefulShutdown(signal) {
  if (isShuttingDown) return;
  isShuttingDown = true;
  console.log(`${signal} received, starting graceful shutdown...`);

  // 1. Stop accepting new connections
  server.close(() => {
    console.log('All connections drained');
    process.exit(0);
  });

  // 2. Health check returns unhealthy (load balancer stops sending traffic)
  // (handled by the middleware below)

  // 3. Finish in-flight requests (with timeout)
  setTimeout(() => {
    console.error('Forced shutdown — connections did not drain in time');
    process.exit(1);
  }, 30_000); // 30s grace period

  // 4. Close database pools, flush queues, etc.
  await db.end();
  await messageQueue.close();
}

// Middleware: reject new requests during shutdown
app.use((req, res, next) => {
  if (isShuttingDown) {
    res.setHeader('Connection', 'close');
    return res.status(503).json({ error: 'Server is shutting down' });
  }
  next();
});

// Health check endpoint
app.get('/health', (req, res) => {
  if (isShuttingDown) return res.status(503).end();
  res.status(200).json({ status: 'healthy' });
});
```

**2. PM2 rolling reload (simplest):**

```bash
# Start in cluster mode
pm2 start app.js -i max --name myapp

# Zero-downtime reload: restarts workers one by one
pm2 reload myapp

# Each worker gets SIGINT → graceful shutdown → new worker spawned
```

```javascript
// ecosystem.config.js
module.exports = {
  apps: [{
    name: 'myapp',
    script: './dist/server.js',
    instances: 'max',
    exec_mode: 'cluster',
    kill_timeout: 30000,        // 30s to drain
    listen_timeout: 10000,      // 10s to start
    wait_ready: true,           // wait for process.send('ready')
    shutdown_with_message: true,
  }]
};

// In your app — signal ready after setup
server.listen(3000, () => {
  process.send?.('ready'); // tell PM2 this instance is ready
});
```

**3. Docker/K8s rolling update:**

```yaml
# Kubernetes deployment
apiVersion: apps/v1
kind: Deployment
spec:
  replicas: 3
  strategy:
    rollingUpdate:
      maxSurge: 1        # add 1 new pod before removing old
      maxUnavailable: 0   # never have fewer than 3 running
  template:
    spec:
      terminationGracePeriodSeconds: 30
      containers:
        - name: api
          readinessProbe:
            httpGet:
              path: /health
              port: 3000
            initialDelaySeconds: 5
            periodSeconds: 5
          lifecycle:
            preStop:
              exec:
                command: ["sleep", "5"] # allow LB to deregister
```

```dockerfile
# Dockerfile
FROM node:22-slim
WORKDIR /app
COPY package.json pnpm-lock.yaml ./
RUN corepack enable && pnpm install --frozen-lockfile --prod
COPY dist ./dist
USER node
EXPOSE 3000
CMD ["node", "dist/server.js"]
# Docker sends SIGTERM → graceful shutdown kicks in
```

**Deployment flow:**
1. New container starts, passes health check
2. Load balancer adds new container to pool
3. Old container receives SIGTERM
4. Old container stops accepting new connections
5. In-flight requests complete (up to 30s)
6. Old container exits cleanly'''
    ),
]
