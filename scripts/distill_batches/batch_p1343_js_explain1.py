"""JavaScript/TypeScript explanation-focused pairs: event loop, closures, prototypes, error handling, performance."""
PAIRS = [
    # -- 01-05: Event loop & async internals ------------------------------------
    ("js_explain1_01", r'''Explain JavaScript's event loop. What are microtasks vs macrotasks, and why does their ordering matter?''', r'''<think>
The user wants a deep explanation of the event loop, not just "it processes callbacks."
I need to explain the call stack, task queue (macrotasks), and microtask queue.
Key insight: microtasks drain completely before the next macrotask runs.
This means Promise.then callbacks always run before setTimeout callbacks, even setTimeout(fn, 0).
I should show a concrete ordering example that surprises people.
Important to explain WHY this design exists — microtasks enable consistent Promise semantics.
Edge case: recursive microtask enqueuing can starve the macrotask queue and freeze rendering.
</think>

## JavaScript Event Loop: Microtasks vs Macrotasks

The event loop is the mechanism that allows JavaScript to be **non-blocking** despite running on a single thread. Understanding it deeply requires knowing three components and **why** they exist.

### The Three Layers

1. **Call stack** — synchronous code runs here, one frame at a time
2. **Microtask queue** — Promises, `queueMicrotask()`, `MutationObserver`
3. **Macrotask queue** — `setTimeout`, `setInterval`, I/O callbacks, `requestAnimationFrame`

**The reason** for two separate queues is consistency. Microtasks were introduced because Promises needed a guarantee: `.then()` handlers always execute before any new I/O or timer work begins. This works by draining the **entire** microtask queue after each macrotask completes — and critically, after the current synchronous execution finishes.

### Ordering Example

```javascript
// This example reveals the exact processing order
console.log("1: synchronous");

setTimeout(() => {
  console.log("5: macrotask (setTimeout)");
}, 0);

Promise.resolve()
  .then(() => {
    console.log("3: microtask (Promise.then)");
    // Microtask enqueued INSIDE a microtask — still runs
    // before the setTimeout macrotask above
    queueMicrotask(() => {
      console.log("4: nested microtask");
    });
  });

console.log("2: synchronous (still on call stack)");

// Output order: 1, 2, 3, 4, 5
```

**This works by** following a strict algorithm each loop iteration:

1. Execute all synchronous code on the call stack until it empties
2. Drain the entire microtask queue (including any microtasks added during draining)
3. Pick ONE macrotask from the macrotask queue and execute it
4. Drain the microtask queue again
5. If it is time to render, run `requestAnimationFrame` callbacks, then paint
6. Repeat from step 3

### The Starvation Edge Case

**Important to note**: because the microtask queue drains completely before moving on, recursive microtask scheduling can freeze the browser:

```javascript
// WARNING: This starves the macrotask queue
function infiniteMicrotask() {
  queueMicrotask(infiniteMicrotask);
}
infiniteMicrotask();
// setTimeout callbacks will NEVER fire
// The browser will appear frozen because rendering is blocked
```

**The trade-off** with microtasks is responsiveness vs consistency. They guarantee Promise ordering but at the risk of blocking if misused. Always ensure microtask chains terminate.'''),

    ("js_explain1_02", r'''How does async/await actually work under the hood? What happens when you await a value?''', r'''<think>
The user wants to understand the machinery behind async/await, not just syntax.
async/await is syntactic sugar over Promises and generators.
When you await, the function is suspended and a Promise is returned to the caller.
The continuation after await is scheduled as a microtask when the awaited Promise resolves.
I should explain the implicit Promise wrapping, the state machine transformation, and gotchas.
Key gotcha: awaiting a non-thenable wraps it in Promise.resolve, which still yields to the microtask queue.
Another important point: each async function call creates a new Promise object — there is a cost.
</think>

## How async/await Works Under the Hood

`async/await` is often described as "syntactic sugar for Promises," but understanding the actual transformation reveals important behavioral details.

### What the Engine Actually Does

**The reason** `async` functions work is that the engine transforms them into state machines. Each `await` is a suspension point where the function yields control.

```javascript
// What you write:
async function fetchUser(id) {
  const response = await fetch(`/api/users/${id}`);
  const data = await response.json();
  return data;
}

// Conceptually, the engine transforms this to:
function fetchUser(id) {
  return new Promise((resolve, reject) => {
    // State 0: initial
    let response, data;

    // Execute until first await
    fetch(`/api/users/${id}`)
      .then(result => {
        // State 1: after first await
        response = result;
        return response.json();
      })
      .then(result => {
        // State 2: after second await
        data = result;
        resolve(data); // the return value resolves the outer Promise
      })
      .catch(reject); // any thrown error rejects the outer Promise
  });
}
```

### What Happens at Each `await`

When you write `await expr`, the engine does these steps:

1. **Evaluate** `expr` to get a value
2. **Wrap** it: if it is not a thenable, wrap in `Promise.resolve(value)`
3. **Suspend** the async function — save local variables and the current position
4. **Return** the implicit Promise to the caller (the function appears to "return")
5. When the awaited Promise settles, **schedule the continuation as a microtask**
6. **Resume** the function from where it left off

**Important to note**: even `await 42` (a non-Promise value) suspends the function. The value is wrapped in `Promise.resolve(42)`, and resumption happens in the next microtask batch:

```javascript
async function demo() {
  console.log("A");
  await 42; // still yields!
  console.log("B");
}

demo();
console.log("C");
// Output: A, C, B — NOT A, B, C
// because "B" runs as a microtask after synchronous code finishes
```

### Gotchas and Performance Implications

**Edge case** — sequential vs parallel awaits:

```javascript
// BAD: sequential — each await waits for the previous one
async function slow() {
  const a = await fetchA(); // waits ~200ms
  const b = await fetchB(); // then waits ~200ms
  return [a, b]; // total: ~400ms
}

// GOOD: parallel — start both, then await
async function fast() {
  const aPromise = fetchA(); // starts immediately
  const bPromise = fetchB(); // starts immediately
  return [await aPromise, await bPromise]; // total: ~200ms
}
```

**The trade-off** with async/await is readability vs overhead. Every `async` call creates a Promise object, and each `await` schedules a microtask. In hot loops, this overhead matters. For performance-critical code, consider batching operations or using raw Promises with `Promise.all`.'''),

    ("js_explain1_03", r'''What are unhandled Promise rejections and why are they dangerous? How do I properly handle them in Node.js and the browser?''', r'''<think>
The user wants to understand unhandled rejections deeply.
Key points: what makes a rejection "unhandled", why it matters (crash vs silent swallow), and proper patterns.
In Node.js >=15, unhandled rejections crash the process by default.
In browsers, they fire an event but don't crash — which can be worse because errors go silent.
I need to show the unhandledrejection event, process.on('unhandledRejection'), and the pattern of always returning or awaiting Promises.
Also important: the timing — a rejection is considered "unhandled" at the end of a microtask checkpoint.
</think>

## Unhandled Promise Rejections Explained

An unhandled rejection occurs when a Promise rejects and **no rejection handler** (`.catch()` or second argument to `.then()`) is attached by the time the microtask queue drains. **The reason** this is dangerous differs by environment.

### Why They Are Dangerous

**In Node.js (v15+)**: unhandled rejections crash the process with exit code 1. This is intentional — the Node.js team decided that silently swallowing errors is worse than crashing:

```javascript
// This WILL crash your Node.js server
async function riskyOperation() {
  const data = await fetch("https://api.example.com/data");
  // If fetch rejects, and nothing catches it, the process dies
}

// Calling without await or .catch() — the rejection floats away
riskyOperation(); // no await, no .catch() — DANGER
```

**In browsers**: unhandled rejections fire a `unhandledrejection` event but do NOT crash the page. **This works by** design because crashing a web page is too disruptive, but **the trade-off** is that errors silently disappear, leading to bugs that are extremely hard to diagnose.

### Proper Handling Patterns

```javascript
// -- Pattern 1: Global safety net (Node.js) --
process.on("unhandledRejection", (reason, promise) => {
  console.error("Unhandled Rejection at:", promise, "reason:", reason);
  // Log to monitoring service, then exit gracefully
  process.exit(1);
});

// -- Pattern 2: Global safety net (Browser) --
window.addEventListener("unhandledrejection", (event) => {
  console.error("Unhandled rejection:", event.reason);
  // Send to error tracking (Sentry, etc.)
  event.preventDefault(); // prevents default console error
});

// -- Pattern 3: Always handle fire-and-forget calls --
// BAD: floating Promise
startBackgroundSync();

// GOOD: attach a catch handler
startBackgroundSync().catch(err => {
  console.error("Background sync failed:", err);
});

// -- Pattern 4: Top-level async with error boundary --
async function main() {
  try {
    await initDatabase();
    await startServer();
  } catch (err) {
    console.error("Fatal startup error:", err);
    process.exit(1);
  }
}
main();
```

### The Timing Edge Case

**Important to note**: the engine checks for unhandled rejections after the microtask queue drains. This means attaching a handler asynchronously can be too late:

```javascript
const p = Promise.reject(new Error("fail"));

// This is TOO LATE — by the time setTimeout fires,
// the rejection is already "unhandled"
setTimeout(() => {
  p.catch(() => {}); // handler attached after the check
}, 0);

// This is FINE — .catch() runs synchronously before
// the microtask checkpoint
const p2 = Promise.reject(new Error("fail"));
p2.catch(() => {}); // attached immediately
```

**Because** the check happens at the microtask boundary, you must attach rejection handlers synchronously or within the same microtask chain. This is why `await` is generally safer than raw `.then()` chains — the `try/catch` around `await` naturally captures rejections at the point of use.'''),

    ("js_explain1_04", r'''What happens when you mix callbacks, Promises, and async/await in the same codebase? How does scheduling actually work across these patterns?''', r'''<think>
The user wants to understand how the three async paradigms interact in terms of scheduling.
Key insight: callbacks use macrotasks (setTimeout, I/O), Promises use microtasks, and async/await is built on Promises (microtasks).
When you mix them, the ordering can be surprising because microtasks always drain before the next macrotask.
I should show a concrete example mixing all three and predict the output order.
Also important: callback-style APIs wrapped in Promises (promisification) and the edge cases there.
Node.js process.nextTick is even higher priority than Promise microtasks — that is another layer.
</think>

## Mixing Callbacks, Promises, and async/await: Scheduling Deep Dive

When these three patterns coexist, their interactions depend on **which queue** each one uses. Understanding this prevents subtle ordering bugs.

### The Priority Hierarchy

```
Highest priority → Lowest priority:
1. process.nextTick()     [Node.js only — "next tick queue"]
2. Promise.then / await   [microtask queue]
3. setTimeout / I/O       [macrotask queue]
4. setImmediate()         [Node.js only — "check phase"]
```

**The reason** for this hierarchy is that each layer was designed for a different purpose. `process.nextTick` was created before Promises existed and needs to run before I/O processing. Microtasks handle Promise continuations. Macrotasks handle external events.

### Mixed Scheduling Example

```javascript
// Predict the output order before running this
console.log("1: sync");

setTimeout(() => console.log("8: setTimeout"), 0);

setImmediate?.(() => console.log("9: setImmediate")); // Node.js only

Promise.resolve().then(() => {
  console.log("4: Promise.then");
  process.nextTick?.(() => console.log("6: nextTick inside microtask"));
  Promise.resolve().then(() => console.log("7: nested Promise"));
});

process.nextTick?.(() => {
  console.log("3: nextTick");
  Promise.resolve().then(() => console.log("5: Promise inside nextTick"));
});

(async () => {
  console.log("2: async IIFE (sync part)");
  // Everything below here runs as microtasks after suspension
})();

// Node.js output: 1, 2, 3, 4, 5, 6, 7, 8, 9
```

**This works by** following the drain order: synchronous code first, then nextTick queue, then microtask queue (with re-draining), then one macrotask, then the check phase.

### The Promisification Edge Case

When you wrap callback APIs in Promises, be aware that the callback fires during a macrotask (I/O phase), but the `.then()` continuation fires as a microtask:

```javascript
const fs = require("fs");

function readFileAsync(path) {
  return new Promise((resolve, reject) => {
    // fs.readFile callback fires during I/O macrotask phase
    fs.readFile(path, "utf8", (err, data) => {
      console.log("A: callback fires (macrotask)");
      if (err) reject(err);
      else resolve(data); // this schedules .then() as microtask
    });
  });
}

readFileAsync("file.txt").then(data => {
  // This runs as a microtask AFTER the callback macrotask
  console.log("B: .then fires (microtask)");
});

setTimeout(() => console.log("C: setTimeout"), 0);

// Likely output: A, B, C
// because B (microtask) drains before C (macrotask)
```

### Practical Guidelines

**Important to note**: mixing paradigms is unavoidable in real projects, but follow these rules:

1. **Never** rely on ordering between `setTimeout(fn, 0)` and I/O callbacks — it is nondeterministic
2. **Always** prefer async/await over `.then()` chains for readability
3. **Avoid** `process.nextTick` in library code — it can starve I/O just like recursive microtasks
4. **Because** async/await uses the microtask queue, `try/catch` around `await` naturally captures errors from promisified callbacks

**The trade-off** with mixing paradigms is flexibility vs predictability. The more consistent your codebase's async style, the fewer ordering surprises you will encounter.'''),

    ("js_explain1_05", r'''How does Promise.race work for implementing timeouts, and what happens to the "losing" Promises? Are they cancelled?''', r'''<think>
This is a common misconception area. Promise.race does NOT cancel losing Promises.
The losing Promises continue executing — their results are just ignored.
This has real consequences: resource leaks, side effects, and memory usage.
I need to explain why cancellation doesn't exist natively, and how AbortController solves this.
Also worth showing the cleanup pattern and the difference between race for timeouts vs race for fastest response.
</think>

## Promise.race for Timeouts: The Cancellation Problem

`Promise.race` resolves or rejects with whichever Promise settles first. **The reason** it is commonly used for timeouts is straightforward — race the real operation against a timer. But there is a critical gotcha that most tutorials skip.

### Basic Timeout Pattern

```javascript
function withTimeout(promise, ms) {
  const timeout = new Promise((_, reject) => {
    setTimeout(() => reject(new Error(`Timed out after ${ms}ms`)), ms);
  });
  return Promise.race([promise, timeout]);
}

// Usage
try {
  const data = await withTimeout(fetch("/api/slow"), 5000);
} catch (err) {
  console.error(err.message); // "Timed out after 5000ms"
}
```

### The Losing Promise Problem

**Important to note**: JavaScript Promises are **not cancellable**. When `Promise.race` settles, the losing Promises keep running:

```javascript
async function demonstrateLeak() {
  const slowFetch = fetch("/api/huge-dataset")
    .then(res => res.json())
    .then(data => {
      // This STILL RUNS even after timeout!
      // The network request completed, JSON was parsed,
      // and this callback executes — all wasted work
      console.log("Fetched", data.length, "records");
      processData(data); // side effects happen!
    });

  const timeout = new Promise((_, reject) =>
    setTimeout(() => reject(new Error("Timeout")), 1000)
  );

  try {
    await Promise.race([slowFetch, timeout]);
  } catch {
    // We caught the timeout, but slowFetch is STILL running
    // The HTTP request is still in flight
    // When it completes, processData() will still execute
  }
}
```

**Because** Promises have no built-in cancellation, the losing side continues consuming CPU, memory, and network bandwidth.

### The Solution: AbortController

**This works by** using the `AbortSignal` mechanism, which gives you actual cancellation:

```javascript
function withTimeout(fetchFn, ms) {
  const controller = new AbortController();

  const timeout = setTimeout(() => {
    controller.abort(); // actually cancels the fetch
  }, ms);

  return fetchFn(controller.signal)
    .finally(() => clearTimeout(timeout)); // clean up timer on success
}

// Usage
async function getData() {
  try {
    const data = await withTimeout(
      (signal) => fetch("/api/data", { signal }).then(r => r.json()),
      5000
    );
    return data;
  } catch (err) {
    if (err.name === "AbortError") {
      console.log("Request was actually cancelled — no wasted resources");
    }
    throw err;
  }
}
```

### Generic Cancellable Race

```javascript
async function cancellableRace(tasks) {
  // Each task is { run: (signal) => Promise, name: string }
  const controller = new AbortController();

  const promises = tasks.map(task =>
    task.run(controller.signal).then(result => ({
      name: task.name,
      result
    }))
  );

  try {
    const winner = await Promise.race(promises);
    controller.abort(); // cancel all losers
    return winner;
  } catch (err) {
    controller.abort(); // cancel everything on error too
    throw err;
  }
}
```

**The trade-off** with `Promise.race` is simplicity vs correctness. The simple version is a one-liner but leaks resources. The `AbortController` version requires more setup but gives you real cancellation. In production code, always use `AbortController` for timeouts — **the reason** is that leaked requests can cause cascading failures in servers under load, where hundreds of "dead" requests pile up.'''),

    # -- 06-10: Closures & scope -----------------------------------------------
    ("js_explain1_06", r'''Explain closures in JavaScript from first principles. Why do they exist, how do they work internally, and when do they cause problems?''', r'''<think>
Closures are fundamental but often explained superficially.
I need to explain the execution context and scope chain first, then show how closures are a natural consequence.
The key insight is that functions capture a REFERENCE to the outer scope's variable environment, not a copy.
This explains both the power and the pitfalls (loop variable capture, memory leaks).
I should cover the practical uses (data privacy, factories, partial application) and the problems (accidental retention).
</think>

## Closures from First Principles

A closure is a function that retains access to variables from its enclosing scope even after that scope has finished executing. But to understand **why** closures exist, you need to understand how JavaScript manages scope.

### How Scope Works Internally

When a function is created, the engine attaches a hidden `[[Environment]]` reference pointing to the **lexical environment** (variable storage) where the function was defined. **This works by** the following mechanism:

```javascript
function createCounter() {
  // A new lexical environment is created here with { count: 0 }
  let count = 0;

  // This inner function captures a REFERENCE to the outer
  // environment — not a copy of 'count'
  return function increment() {
    count++;     // reads from the captured environment
    return count;
  };
}

const counter = createCounter();
// createCounter() has returned, its call stack frame is gone,
// BUT its lexical environment survives because increment
// holds a reference to it via [[Environment]]

console.log(counter()); // 1
console.log(counter()); // 2 — same 'count' variable, mutated
```

**The reason** the `count` variable survives is garbage collection. The engine cannot collect the lexical environment because `increment` still references it. The environment lives as long as any closure referencing it exists.

### The Classic Pitfall: Loop Variable Capture

**Because** closures capture references (not values), this infamous bug occurs:

```javascript
// BUG: all callbacks print 5
for (var i = 0; i < 5; i++) {
  setTimeout(() => console.log(i), 100);
}
// Output: 5, 5, 5, 5, 5
// The reason: all five closures share the SAME 'i' variable,
// and by the time they run, the loop has finished with i === 5

// FIX 1: use 'let' — creates a new binding per iteration
for (let i = 0; i < 5; i++) {
  setTimeout(() => console.log(i), 100);
}
// Output: 0, 1, 2, 3, 4

// FIX 2: IIFE — creates a new scope per iteration
for (var i = 0; i < 5; i++) {
  ((captured) => {
    setTimeout(() => console.log(captured), 100);
  })(i); // 'i' is passed by VALUE into the IIFE parameter
}
```

### Practical Uses

```javascript
// 1. Data privacy (module pattern)
function createWallet(initialBalance) {
  let balance = initialBalance; // private — no external access

  return {
    deposit(amount) { balance += amount; },
    getBalance() { return balance; },
    // No 'setBalance' — balance is truly private
  };
}

// 2. Partial application / currying
function multiply(a) {
  return (b) => a * b; // 'a' is captured in the closure
}
const double = multiply(2);
const triple = multiply(3);
console.log(double(5)); // 10
console.log(triple(5)); // 15
```

### When Closures Cause Memory Leaks

**Edge case**: closures can accidentally retain large objects:

```javascript
function processData() {
  const hugeArray = new Array(1_000_000).fill("data");

  // This closure only uses hugeArray.length, but it captures
  // the ENTIRE lexical environment, including hugeArray itself
  return function getCount() {
    return hugeArray.length;
  };
}

const getCount = processData();
// hugeArray (8MB+) stays in memory forever because getCount's
// closure references the environment containing it
```

**The trade-off**: closures provide elegant encapsulation but require awareness of what is being retained. In performance-critical code, extract only the values you need before creating the closure.'''),

    ("js_explain1_07", r'''What is an IIFE (Immediately Invoked Function Expression) and why was it important? Is it still relevant with ES modules?''', r'''<think>
IIFEs were crucial before ES modules. They solved the global namespace pollution problem.
With ES modules, their primary use case is mostly gone, but they still have niche uses.
I should explain the history (why they were needed), the syntax (why the parens matter), and modern relevance.
The parens are needed because of the statement vs expression distinction in JS parsing.
Modern uses: async IIFE for top-level await in non-module contexts, one-time initialization, and in bundler output.
</think>

## IIFE: History, Mechanics, and Modern Relevance

An IIFE (Immediately Invoked Function Expression) is a function that runs the moment it is defined. Understanding **why** it was invented explains a lot about JavaScript's evolution.

### Why IIFEs Were Essential

Before ES modules (pre-2015), every JavaScript file shared the **global scope**. If two scripts both declared `var utils = {}`, one would overwrite the other. **The reason** IIFEs became standard practice was to create isolated scopes:

```javascript
// Without IIFE — pollutes global scope
var counter = 0;
function increment() { counter++; }
// 'counter' and 'increment' are now global — any script can clash

// With IIFE — nothing leaks
var myModule = (function() {
  var counter = 0; // private to this scope

  return {
    increment: function() { counter++; },
    getCount: function() { return counter; }
  };
})();
// Only 'myModule' is global — everything else is encapsulated
```

### Why the Parentheses Matter

**Important to note**: the wrapping parentheses are not optional, and **the reason** is how JavaScript's parser distinguishes statements from expressions:

```javascript
// This FAILS — parser sees 'function' at statement position
// and expects a function declaration (which requires a name
// and cannot be immediately invoked)
function() { console.log("nope"); }();
// SyntaxError: Function statements require a function name

// This WORKS — the outer parens force the parser to treat
// it as a function EXPRESSION
(function() { console.log("works"); })();

// Alternative: parens around the whole thing
(function() { console.log("also works"); }());

// Void operator also works (but less common)
void function() { console.log("void trick"); }();
```

**This works by** exploiting JavaScript's grammar rules: anything after `(` must be an expression, so the parser treats the `function` keyword as the start of a function expression, not a declaration.

### The Module Pattern (IIFE's Greatest Hit)

```javascript
// The "revealing module pattern" — industry standard pre-ES6
var UserService = (function() {
  // Private state
  var users = [];
  var apiBase = "/api/users";

  // Private function
  function validate(user) {
    return user.name && user.email;
  }

  // Public API — only these are exposed
  return {
    add: function(user) {
      if (!validate(user)) throw new Error("Invalid user");
      users.push(user);
    },
    getAll: function() {
      return [...users]; // return copy, not reference
    },
    count: function() {
      return users.length;
    }
  };
})();
```

### Modern Relevance

With ES modules (`import/export`), IIFEs are largely unnecessary for scoping. **But** they survive in specific contexts:

```javascript
// 1. Async IIFE for top-level await (before Node 14.8+ / ES2022)
(async () => {
  const config = await loadConfig();
  const db = await connectDatabase(config);
  startServer(db);
})();

// 2. Bundler output — Webpack/Rollup wrap modules in IIFEs
// to isolate them in non-module environments

// 3. One-shot initialization with complex logic
const config = (() => {
  const env = process.env.NODE_ENV;
  if (env === "production") return { debug: false, logLevel: "error" };
  if (env === "test") return { debug: true, logLevel: "warn" };
  return { debug: true, logLevel: "debug" };
})();
```

**The trade-off**: IIFEs add syntactic noise but guarantee scope isolation everywhere, even in non-module `<script>` tags. In modern codebases using ES modules or TypeScript, prefer `export/import` for encapsulation. Use IIFEs only for the async initialization pattern or when you need a complex one-time computation that should not pollute the surrounding scope.'''),

    ("js_explain1_08", r'''How do closures cause memory leaks in JavaScript applications? What is WeakRef and how does it help?''', r'''<think>
This connects closures to memory management, a key area for senior-level understanding.
Closures can keep entire scope chains alive, including DOM elements, large data structures, etc.
Classic example: event listeners that capture DOM nodes, preventing garbage collection.
WeakRef (ES2021) and FinalizationRegistry provide a way to hold references without preventing GC.
I need to explain the garbage collector's reachability model first.
Important: WeakRef is not a silver bullet — the GC can collect the target at any time.
</think>

## Closure-Based Memory Leaks and WeakRef

Memory leaks in JavaScript almost always come down to one thing: **unintentional references** that prevent the garbage collector from reclaiming memory. Closures are the most common source because they invisibly retain scope chains.

### How the Garbage Collector Decides

JavaScript uses **reachability-based** garbage collection. An object is kept alive if it can be reached from any "root" (global variables, call stack, active closures). **The reason** closures cause leaks is that they create invisible references:

```javascript
function setupHandler() {
  const hugeData = fetchLargeDataset(); // 50MB object

  const button = document.getElementById("save");
  button.addEventListener("click", () => {
    // This closure captures the entire lexical environment,
    // which includes 'hugeData' — even though we only
    // need a small piece of it
    console.log("Saving", hugeData.title);
  });

  // When setupHandler returns, hugeData should be GC-eligible
  // BUT the event listener's closure keeps it alive forever
  // (or until the button is removed AND the listener is removed)
}
```

### Common Leak Patterns

```javascript
// Leak 1: Forgotten event listeners
class ChatWidget {
  constructor() {
    this.messages = [];
    // This listener keeps 'this' (and all its messages) alive
    // even if the widget is "destroyed" by removing its DOM node
    window.addEventListener("resize", () => {
      this.adjustLayout();
    });
    // FIX: store reference and removeEventListener in destroy()
  }
}

// Leak 2: Closures in caches
function createCache() {
  const cache = new Map();
  return {
    // Items in cache are never released — Map holds strong refs
    get(key, factory) {
      if (!cache.has(key)) cache.set(key, factory());
      return cache.get(key);
    }
  };
}

// Leak 3: Timers holding closures
function startPolling(component) {
  setInterval(() => {
    // 'component' is captured — even if the component is
    // unmounted, this interval keeps it alive
    component.refresh();
  }, 5000);
  // FIX: store interval ID, call clearInterval on unmount
}
```

### WeakRef to the Rescue

`WeakRef` (ES2021) holds a reference to an object **without preventing garbage collection**. **This works by** telling the GC: "I am interested in this object, but do not keep it alive on my account."

```javascript
class JsonCache {
  #cache = new Map();   // key -> WeakRef
  #registry;

  constructor() {
    // FinalizationRegistry runs a callback when an object is GC'd
    this.#registry = new FinalizationRegistry((key) => {
      // Clean up the Map entry when the cached value is collected
      const ref = this.#cache.get(key);
      if (ref && !ref.deref()) {
        this.#cache.delete(key);
      }
    });
  }

  set(key, value) {
    this.#cache.set(key, new WeakRef(value));
    this.#registry.register(value, key); // register for cleanup
  }

  get(key) {
    const ref = this.#cache.get(key);
    if (!ref) return undefined;

    const value = ref.deref(); // returns the object OR undefined
    if (!value) {
      // Object was garbage collected — clean up
      this.#cache.delete(key);
      return undefined;
    }
    return value;
  }
}
```

### Edge Cases and Caveats

**Important to note**: `WeakRef.deref()` can return `undefined` at **any** call — you must always check:

```javascript
const ref = new WeakRef(someObject);

// WRONG — race condition
if (ref.deref()) {
  ref.deref().doSomething(); // might be undefined by now!
}

// CORRECT — capture once
const obj = ref.deref();
if (obj) {
  obj.doSomething(); // safe — local variable keeps it alive
}
```

**The trade-off** with `WeakRef` is that you lose determinism. You cannot predict when or if the GC will collect the target. **Because** of this, `WeakRef` should only be used for caches and optional references — never for data that must exist. For most closure leaks, the proper fix is simply removing event listeners and clearing timers in cleanup code.'''),

    ("js_explain1_09", r'''Explain lexical scope vs dynamic scope. Why did JavaScript choose lexical scope, and where does `this` break the pattern?''', r'''<think>
This is a great question that connects scope design to the 'this' keyword.
JavaScript uses lexical scope — scope is determined by where code is written, not where it runs.
But 'this' is dynamically scoped — it depends on HOW a function is called, not where it's defined.
Arrow functions fix this by capturing 'this' lexically.
I should explain the benefits of lexical scope (predictability, static analysis) and why 'this' is dynamic (OOP flexibility).
Historical context: JavaScript inherited 'this' from Java/C++ but in a much looser way.
</think>

## Lexical Scope vs Dynamic Scope: Why `this` Is Different

JavaScript uses **lexical scope** for all variables — but `this` behaves as if it were **dynamically scoped**. Understanding this split explains many of JavaScript's most confusing behaviors.

### Lexical Scope: Determined at Write Time

**The reason** JavaScript (and most modern languages) chose lexical scope is predictability. You can determine which variable a name refers to just by reading the code:

```javascript
const x = "global";

function outer() {
  const x = "outer";

  function inner() {
    // Lexical scope: 'x' is resolved by looking at where
    // inner() is WRITTEN, not where it is CALLED
    console.log(x); // always "outer"
  }

  return inner;
}

const fn = outer();
fn(); // "outer" — even though we call it from global scope

// If JavaScript used dynamic scope, fn() would print "global"
// because it would look up 'x' in the CALLING scope instead
```

**This works by** the scope chain being fixed at function creation time. When `inner` is created inside `outer`, its `[[Environment]]` reference permanently points to `outer`'s lexical environment. No matter where you call `inner`, it always looks up variables through that same chain.

### Where `this` Breaks the Pattern

Unlike variables, `this` is determined by **how a function is called** — making it dynamically scoped in practice:

```javascript
const user = {
  name: "Alice",
  greet() {
    // 'this' depends on the CALL SITE, not the definition site
    console.log(`Hello, I am ${this.name}`);
  }
};

user.greet();         // "Hello, I am Alice" — called as method
const greet = user.greet;
greet();              // "Hello, I am undefined" — called as function
                      // (this === globalThis in sloppy mode, undefined in strict)

const bob = { name: "Bob", greet: user.greet };
bob.greet();          // "Hello, I am Bob" — 'this' follows the caller
```

**The reason** `this` works this way is flexibility for OOP. The same method can be shared across objects, with `this` adapting to whichever object calls it. But this creates the classic "lost this" problem.

### Arrow Functions: Lexical `this`

Arrow functions were introduced specifically to make `this` lexical:

```javascript
class Timer {
  constructor() {
    this.seconds = 0;
  }

  start() {
    // PROBLEM: regular function — 'this' will be the timer object
    // from setInterval, NOT the Timer instance
    setInterval(function() {
      this.seconds++; // 'this' is wrong! (globalThis or undefined)
    }, 1000);

    // SOLUTION: arrow function — captures 'this' from start()
    setInterval(() => {
      this.seconds++; // 'this' is the Timer instance — correct!
    }, 1000);
  }
}
```

**Because** arrow functions capture `this` lexically, they cannot be used as constructors or methods that need dynamic dispatch:

```javascript
const obj = {
  value: 42,
  // BAD: arrow function captures 'this' from the enclosing scope
  // (module/global), not from 'obj'
  getValue: () => this.value, // undefined!

  // GOOD: regular method — 'this' is dynamically bound to obj
  getValue() { return this.value; } // 42
};
```

### Explicit Binding: `call`, `apply`, `bind`

**Important to note**: you can manually control `this` binding:

```javascript
function greet(greeting) {
  console.log(`${greeting}, ${this.name}`);
}

const alice = { name: "Alice" };

greet.call(alice, "Hi");       // "Hi, Alice" — sets 'this' for one call
greet.apply(alice, ["Hi"]);    // same, but args as array
const bound = greet.bind(alice); // returns new function with 'this' locked
bound("Hey");                  // "Hey, Alice" — permanently bound
```

**The trade-off** of JavaScript's hybrid approach: lexical scope for variables gives predictability, while dynamic `this` gives OOP flexibility. Arrow functions bridge the gap by making `this` lexical when you need it. The rule of thumb: use regular functions for methods, arrow functions for callbacks.'''),

    ("js_explain1_10", r'''What is the module pattern vs ES modules? How do they handle encapsulation differently, and what are the trade-offs?''', r'''<think>
The module pattern uses closures/IIFEs, ES modules use the language's import/export system.
Key differences: the module pattern is runtime, ES modules are static (allowing tree shaking).
ES modules have live bindings (import sees mutations), while module pattern returns a frozen API.
I should compare encapsulation, dependency management, and tooling support.
Also important: CommonJS (require) as the middle ground.
</think>

## Module Pattern vs ES Modules: Encapsulation Compared

JavaScript has evolved through three module systems, each with different encapsulation guarantees. Understanding the differences explains why ES modules won.

### The Module Pattern (Closure-Based)

**This works by** using an IIFE to create a private scope and returning a public API object:

```javascript
// module-pattern/userService.js
var UserService = (function() {
  // PRIVATE — cannot be accessed from outside
  var users = [];
  var nextId = 1;

  function validate(user) {
    if (!user.name) throw new Error("Name required");
  }

  // PUBLIC — exposed via the returned object
  return Object.freeze({
    add(user) {
      validate(user);
      users.push({ ...user, id: nextId++ });
    },
    getAll() {
      return users.map(u => ({ ...u })); // defensive copy
    },
    count() {
      return users.length;
    }
  });
})();

// Usage
UserService.add({ name: "Alice" });
console.log(UserService.count()); // 1
console.log(UserService.users);   // undefined — truly private
```

**The reason** this pattern was dominant pre-ES6 is that it provides genuine privacy. The `users` array is completely inaccessible — no reflection, no `Object.getOwnPropertyNames()`, nothing can reach it. **But** the trade-offs are significant: dependencies are implicit (loaded via `<script>` tag order), no static analysis is possible, and no tree shaking.

### ES Modules (Language-Level)

```javascript
// es-modules/userService.js
// File scope IS the module scope — no IIFE needed
const users = [];
let nextId = 1;

function validate(user) {
  if (!user.name) throw new Error("Name required");
}

// Only exported symbols are public
export function add(user) {
  validate(user);
  users.push({ ...user, id: nextId++ });
}

export function getAll() {
  return users.map(u => ({ ...u }));
}

export function count() {
  return users.length;
}

// Usage (in another file)
// import { add, count } from "./userService.js";
```

### Key Differences

**Important to note**: ES modules have **live bindings**, not snapshots:

```javascript
// counter.js
export let count = 0;
export function increment() { count++; }

// main.js
import { count, increment } from "./counter.js";
console.log(count); // 0
increment();
console.log(count); // 1 — the import sees the updated value!

// With the module pattern, this would NOT work:
var Counter = (function() {
  var count = 0;
  return {
    count: count,         // snapshot — always 0
    increment() { count++; }
  };
})();
Counter.increment();
console.log(Counter.count); // still 0! (copied by value)
```

**Because** ES module imports are live bindings (references to the exporting module's variables), you get automatic synchronization. The module pattern copies primitive values at return time.

### Static vs Dynamic

```javascript
// ES modules are STATIC — imports must be top-level
import { foo } from "./bar.js"; // parsed at compile time

// This enables:
// 1. Tree shaking — bundlers can remove unused exports
// 2. Circular dependency detection at parse time
// 3. IDE autocompletion and type checking

// Module pattern is DYNAMIC — runs at runtime
var mod = (function() {
  if (condition) {
    // can conditionally include dependencies
    var dep = SomeGlobal;
  }
  return { /* ... */ };
})();

// Dynamic import() bridges the gap for ES modules
const { foo } = await import("./bar.js"); // runtime, returns Promise
```

### The Trade-Off Summary

| Aspect | Module Pattern | ES Modules |
|--------|---------------|------------|
| Privacy | True (closure) | Convention (`_prefix` or `#private`) |
| Bindings | Snapshot (copied) | Live (referenced) |
| Analysis | Runtime only | Static (tree shakeable) |
| Dependencies | Implicit (script order) | Explicit (import statements) |
| Browser support | Everywhere | Modern browsers + bundlers |

**The reason** ES modules won is that static analysis enables an entire ecosystem of tooling: bundlers, type checkers, linters, and IDE features all benefit from knowing the dependency graph at compile time. The module pattern's true privacy is rarely worth sacrificing these benefits.'''),

    # -- 11-15: Prototype chain & OOP ------------------------------------------
    ("js_explain1_11", r'''How does the prototype chain work in JavaScript? Explain __proto__, prototype, and Object.create with examples.''', r'''<think>
The prototype chain is JavaScript's inheritance mechanism.
I need to distinguish between __proto__ (the hidden link) and .prototype (property on constructor functions).
Object.create lets you set the prototype directly without a constructor.
I should draw the chain visually and show property lookup.
Key insight: methods are shared via prototypes, saving memory compared to instance methods.
Common confusion: Class syntax uses prototypes under the hood.
</think>

## The Prototype Chain: JavaScript's Inheritance Mechanism

Every JavaScript object has a hidden link to another object called its **prototype**. Property lookups walk this chain until the property is found or the chain ends at `null`. Understanding the three related but different concepts — `__proto__`, `.prototype`, and `Object.create` — is essential.

### The Three Concepts

**`__proto__`** (or `Object.getPrototypeOf(obj)`) — the actual link in the chain. Every object has one:

```javascript
const animal = { eats: true };
const rabbit = { jumps: true };

// Set rabbit's prototype to animal
Object.setPrototypeOf(rabbit, animal);
// (rabbit.__proto__ === animal) is now true

console.log(rabbit.jumps); // true — own property
console.log(rabbit.eats);  // true — found via prototype chain

// The lookup process:
// 1. Does rabbit have 'eats'? No
// 2. Does rabbit.__proto__ (animal) have 'eats'? Yes → return true
```

**`.prototype`** — a property that exists **only on functions**. It becomes the `__proto__` of objects created with `new`:

```javascript
function Dog(name) {
  this.name = name;
}
Dog.prototype.bark = function() {
  return `${this.name} says woof!`;
};

const rex = new Dog("Rex");

// What 'new' actually does:
// 1. Create empty object: {}
// 2. Set its __proto__: {}.__proto__ = Dog.prototype
// 3. Call Dog with 'this' bound to the new object
// 4. Return the object (unless constructor returns an object)

console.log(rex.__proto__ === Dog.prototype); // true
console.log(rex.bark()); // "Rex says woof!" — found on prototype
```

**`Object.create(proto)`** — creates a new object with a specified prototype, without needing a constructor:

```javascript
const vehicleProto = {
  start() { console.log(`${this.type} starting`); },
  stop() { console.log(`${this.type} stopping`); }
};

// Create object with vehicleProto as its prototype
const car = Object.create(vehicleProto);
car.type = "Car";
car.start(); // "Car starting" — method found via prototype chain

// The chain: car → vehicleProto → Object.prototype → null
```

### Visualizing the Chain

```
// For: const rex = new Dog("Rex")

rex                    Dog.prototype          Object.prototype      null
┌──────────┐          ┌──────────────┐       ┌──────────────┐
│ name:"Rex"│ ──__proto__──→ │ bark: fn     │ ──__proto__──→ │ toString: fn │ ──→ null
└──────────┘          │ constructor: │       │ hasOwnProp:fn│
                      │   Dog        │       └──────────────┘
                      └──────────────┘
```

**This works by** each property lookup walking rightward through the chain. **The reason** this is efficient is that methods defined on the prototype are **shared** across all instances — they exist in memory only once:

```javascript
const a = new Dog("A");
const b = new Dog("B");

// Both share the SAME function object
console.log(a.bark === b.bark); // true
// Only 'name' is per-instance, 'bark' is shared
```

### Property Shadowing

```javascript
const parent = { x: 1, y: 2 };
const child = Object.create(parent);

child.x = 10; // creates OWN property, does NOT modify parent

console.log(child.x);  // 10 — own property (shadows parent.x)
console.log(parent.x); // 1  — unchanged
console.log(child.y);  // 2  — from prototype (no shadowing)
```

### Edge Case: Object.create(null)

**Important to note**: you can create objects with NO prototype:

```javascript
const bare = Object.create(null);
bare.key = "value";

console.log(bare.toString); // undefined — no Object.prototype!
console.log("key" in bare); // true — own property
// Useful for dictionary objects where you don't want
// inherited properties like 'constructor' or 'toString'
// polluting key lookups
```

**The trade-off** with prototypal inheritance is flexibility vs clarity. The chain allows powerful delegation patterns, but the distinction between `__proto__` and `.prototype` confuses developers. **Because** of this confusion, ES6 classes were introduced as syntactic sugar — but they use the exact same prototype chain under the hood.'''),

    ("js_explain1_12", r'''What is the difference between ES6 classes and prototypes? Are classes just syntactic sugar?''', r'''<think>
Classes ARE mostly syntactic sugar, but there are differences that matter.
Key differences: classes are always strict mode, not hoisted, constructor must use new, methods are non-enumerable.
Also: class fields, private fields (#), and static members add real functionality.
I should show the equivalent prototype code for a class to prove it's sugar, then show where classes differ.
</think>

## ES6 Classes vs Prototypes: More Than Just Sugar

ES6 classes are **primarily** syntactic sugar over prototypes, but they add several behaviors that cannot be replicated with plain constructor functions. Understanding both the equivalence and the differences matters.

### The Sugar: What Classes Compile To

```javascript
// ES6 class
class Animal {
  constructor(name) {
    this.name = name;
  }

  speak() {
    return `${this.name} makes a sound`;
  }

  static create(name) {
    return new Animal(name);
  }
}

// Equivalent prototype-based code
function AnimalOld(name) {
  this.name = name;
}

AnimalOld.prototype.speak = function() {
  return `${this.name} makes a sound`;
};

AnimalOld.create = function(name) {
  return new AnimalOld(name);
};

// Both produce the same prototype chain:
const a1 = new Animal("Cat");
const a2 = new AnimalOld("Dog");
// a1.__proto__ === Animal.prototype ✓
// a2.__proto__ === AnimalOld.prototype ✓
```

**The reason** they are called syntactic sugar is that `typeof Animal === "function"` — classes ARE functions. The `constructor` method becomes the function body, and other methods are placed on `.prototype`.

### Where Classes Are NOT Just Sugar

**Important to note** these behavioral differences:

```javascript
// 1. Classes CANNOT be called without 'new'
class Foo {}
Foo(); // TypeError: Class constructor Foo cannot be invoked without 'new'

function Bar() {}
Bar(); // works fine (but 'this' is wrong — silent bug)

// 2. Class methods are NON-ENUMERABLE
class MyClass {
  method() {}
}
for (let key in new MyClass()) {
  console.log(key); // nothing — method is not enumerable
}

function MyFunc() {}
MyFunc.prototype.method = function() {};
for (let key in new MyFunc()) {
  console.log(key); // "method" — IS enumerable
}

// 3. Classes are always in STRICT MODE
class StrictByDefault {
  method() {
    // 'use strict' is implicit
    x = 5; // ReferenceError (no implicit global)
  }
}

// 4. Classes are NOT HOISTED (unlike function declarations)
const a = new MyAnimal(); // ReferenceError: Cannot access before init
class MyAnimal {}

const b = new MyOldAnimal(); // works! function is hoisted
function MyOldAnimal() {}
```

### Private Fields: Genuine New Feature

```javascript
class BankAccount {
  // # prefix creates truly private fields — not sugar, this is
  // a new language feature with no prototype equivalent
  #balance;
  #pin;

  constructor(initialBalance, pin) {
    this.#balance = initialBalance;
    this.#pin = pin;
  }

  withdraw(amount, pin) {
    if (pin !== this.#pin) throw new Error("Wrong PIN");
    if (amount > this.#balance) throw new Error("Insufficient funds");
    this.#balance -= amount;
    return this.#balance;
  }

  get balance() {
    return this.#balance;
  }
}

const account = new BankAccount(1000, "1234");
console.log(account.#balance); // SyntaxError: Private field
console.log(account.balance);  // 1000 (via getter)

// This is STRONGER than closure-based privacy because:
// - It works with multiple instances (closure pattern needs factory)
// - Performance: V8 optimizes private fields like regular properties
// - TypeScript/tooling can statically check access
```

### Inheritance Comparison

```javascript
// Class inheritance — clean and readable
class Shape {
  constructor(color) { this.color = color; }
  describe() { return `A ${this.color} shape`; }
}

class Circle extends Shape {
  constructor(color, radius) {
    super(color); // MUST call super before using 'this'
    this.radius = radius;
  }

  area() { return Math.PI * this.radius ** 2; }

  // Override with super access
  describe() {
    return `${super.describe()} (circle, r=${this.radius})`;
  }
}

// Prototype equivalent — verbose and error-prone
function ShapeOld(color) { this.color = color; }
ShapeOld.prototype.describe = function() {
  return `A ${this.color} shape`;
};

function CircleOld(color, radius) {
  ShapeOld.call(this, color); // manual super() call
  this.radius = radius;
}
CircleOld.prototype = Object.create(ShapeOld.prototype);
CircleOld.prototype.constructor = CircleOld; // fix constructor ref
CircleOld.prototype.area = function() {
  return Math.PI * this.radius ** 2;
};
```

**The trade-off**: classes sacrifice some of JavaScript's prototypal flexibility (like changing prototypes at runtime) in exchange for clarity, safety (strict mode, `new` enforcement), and real features (private fields). **Because** the prototype chain is still used under the hood, understanding prototypes remains essential for debugging and advanced patterns.'''),

    ("js_explain1_13", r'''How do I implement mixins in JavaScript? What are the patterns and pitfalls?''', r'''<think>
Mixins allow composing behavior from multiple sources. JavaScript doesn't have multiple inheritance, so mixins are the workaround.
Patterns: Object.assign for simple mixins, class mixin factories for class-based code, Symbol.hasInstance for instanceof support.
Pitfalls: name collisions, prototype pollution, diamond problem.
I should show multiple approaches and compare their trade-offs.
</think>

## Mixins in JavaScript: Patterns and Pitfalls

JavaScript has single inheritance (one prototype chain), but real applications often need to compose behaviors from multiple sources. **The reason** mixins exist is to solve this without the complexity of multiple inheritance.

### Pattern 1: Object.assign (Simple Mixins)

The simplest approach copies properties from source objects:

```javascript
const Serializable = {
  serialize() {
    return JSON.stringify(this);
  },
  toJSON() {
    // Filter out methods and private-looking properties
    const data = {};
    for (const [key, value] of Object.entries(this)) {
      if (typeof value !== "function" && !key.startsWith("_")) {
        data[key] = value;
      }
    }
    return data;
  }
};

const Validatable = {
  validate() {
    for (const [field, rule] of Object.entries(this._rules || {})) {
      if (rule.required && !this[field]) {
        throw new Error(`${field} is required`);
      }
    }
    return true;
  }
};

class User {
  constructor(name, email) {
    this.name = name;
    this.email = email;
    this._rules = { name: { required: true }, email: { required: true } };
  }
}

// Apply mixins to the prototype
Object.assign(User.prototype, Serializable, Validatable);

const user = new User("Alice", "alice@example.com");
user.validate();                    // true
console.log(user.serialize());      // {"name":"Alice","email":"alice@example.com"}
console.log(user instanceof User);  // true
```

**This works by** copying enumerable own properties from the mixin objects onto the target prototype. Each instance gets access to the mixed-in methods through the normal prototype chain.

### Pattern 2: Class Mixin Factories (Recommended)

**The reason** this pattern is preferred for class-based code is that it preserves the prototype chain and works with `super`:

```javascript
// Each mixin is a function that takes a base class and returns
// a new class extending it — a "subclass factory"
const Timestamped = (Base) => class extends Base {
  constructor(...args) {
    super(...args);
    this.createdAt = new Date();
    this.updatedAt = new Date();
  }

  touch() {
    this.updatedAt = new Date();
  }
};

const SoftDeletable = (Base) => class extends Base {
  #deleted = false;

  delete() {
    this.#deleted = true;
    this.touch?.(); // call Timestamped.touch if available
  }

  get isDeleted() {
    return this.#deleted;
  }
};

// Compose by nesting — reads right to left
// Article extends Timestamped extends SoftDeletable extends BaseModel
class BaseModel {
  save() { console.log("Saving to database..."); }
}

class Article extends Timestamped(SoftDeletable(BaseModel)) {
  constructor(title, body) {
    super();
    this.title = title;
    this.body = body;
  }
}

const article = new Article("Hello", "World");
console.log(article.createdAt);  // Date — from Timestamped
article.delete();                 // from SoftDeletable
article.save();                   // from BaseModel
console.log(article.isDeleted);   // true
```

### Pitfall 1: Name Collisions

```javascript
const MixinA = { process() { return "A"; } };
const MixinB = { process() { return "B"; } };

// Object.assign takes the LAST one — MixinA.process is lost
Object.assign(Target.prototype, MixinA, MixinB);
new Target().process(); // "B" — silent override!

// FIX: Use Symbols to avoid collisions
const MixinASafe = {
  [Symbol.for("MixinA.process")]() { return "A"; }
};
```

### Pitfall 2: The Diamond Problem

```javascript
// When two mixins depend on the same base behavior:
const LoggableA = (Base) => class extends Base {
  log() { console.log("A:", this.data); }
};

const LoggableB = (Base) => class extends Base {
  log() { console.log("B:", this.data); }
};

// class Thing extends LoggableA(LoggableB(Base))
// LoggableA.log shadows LoggableB.log — only "A:" is accessible
// There is no way to call both without explicit composition
```

### Pitfall 3: instanceof Breaks

```javascript
const Mixin = { greet() { return "hi"; } };
Object.assign(User.prototype, Mixin);

const user = new User();
user.greet(); // works
// But there is no way to check: user instanceof Mixin
// because Mixin is a plain object, not a constructor
```

**The trade-off** between approaches: `Object.assign` is simple but loses `super` and `instanceof`. Class factories preserve the chain but create deeper prototype hierarchies. **Important to note**: prefer composition over inheritance when possible — a `User` that HAS a `Serializer` is often cleaner than a `User` that IS `Serializable`.'''),

    ("js_explain1_14", r'''Explain Symbol properties in JavaScript. What problems do they solve, and how are well-known Symbols used?''', r'''<think>
Symbols are unique, non-string property keys. They solve name collision and enable metaprogramming.
Well-known Symbols (Symbol.iterator, Symbol.toPrimitive, etc.) let you customize built-in behaviors.
I should cover: creation, uniqueness, property hiding, well-known symbols, and practical uses.
Key insight: Symbols are NOT private — they're just collision-proof.
</think>

## Symbol Properties: Collision-Proof Keys and Metaprogramming

Symbols are a **primitive type** introduced in ES6 that serve as guaranteed-unique property keys. They solve two problems: preventing name collisions between unrelated code and enabling customization of built-in language behaviors.

### Why Symbols Exist

**The reason** Symbols were added is that string property keys inevitably collide. If a library adds a `.serialize()` method to an object, and your code adds its own `.serialize()`, one overwrites the other. Symbols eliminate this:

```javascript
// Two independent libraries — no collision possible
const libA_id = Symbol("id");
const libB_id = Symbol("id");

const obj = {};
obj[libA_id] = "library-A-data";
obj[libB_id] = "library-B-data";

// Despite having the same description string, these are
// completely different keys
console.log(libA_id === libB_id);  // false
console.log(obj[libA_id]);         // "library-A-data"
console.log(obj[libB_id]);         // "library-B-data"
```

**Important to note**: Symbols are NOT private. They are just hidden from casual enumeration:

```javascript
const secret = Symbol("secret");
const obj = { [secret]: 42, visible: true };

// Symbols are hidden from these:
console.log(Object.keys(obj));               // ["visible"]
console.log(JSON.stringify(obj));            // {"visible":true}
for (let key in obj) console.log(key);       // "visible"

// But accessible via these:
console.log(Object.getOwnPropertySymbols(obj)); // [Symbol(secret)]
console.log(Reflect.ownKeys(obj));               // ["visible", Symbol(secret)]
```

### Well-Known Symbols: Customizing Language Behavior

JavaScript defines several built-in Symbols that let you override how objects interact with language features:

```javascript
// Symbol.iterator — make any object iterable
class Range {
  constructor(start, end) {
    this.start = start;
    this.end = end;
  }

  // This makes Range work with for...of, spread, and destructuring
  [Symbol.iterator]() {
    let current = this.start;
    const end = this.end;
    return {
      next() {
        if (current <= end) {
          return { value: current++, done: false };
        }
        return { done: true };
      }
    };
  }
}

const range = new Range(1, 5);
console.log([...range]);        // [1, 2, 3, 4, 5]
for (const n of range) {}       // works!
const [a, b] = range;           // a=1, b=2

// Symbol.toPrimitive — control type coercion
class Money {
  constructor(amount, currency) {
    this.amount = amount;
    this.currency = currency;
  }

  [Symbol.toPrimitive](hint) {
    // hint is "number", "string", or "default"
    if (hint === "number") return this.amount;
    if (hint === "string") return `${this.amount} ${this.currency}`;
    return this.amount; // default: used in + and ==
  }
}

const price = new Money(9.99, "USD");
console.log(+price);         // 9.99 (number hint)
console.log(`${price}`);     // "9.99 USD" (string hint)
console.log(price + 0.01);   // 10 (default hint)

// Symbol.hasInstance — customize instanceof
class EvenNumber {
  static [Symbol.hasInstance](value) {
    return typeof value === "number" && value % 2 === 0;
  }
}

console.log(4 instanceof EvenNumber);   // true
console.log(5 instanceof EvenNumber);   // false
```

### Symbol.for: Global Symbol Registry

```javascript
// Symbol() always creates a UNIQUE symbol
Symbol("app.id") === Symbol("app.id"); // false

// Symbol.for() uses a GLOBAL registry — same key = same symbol
Symbol.for("app.id") === Symbol.for("app.id"); // true

// This works ACROSS iframes and workers — truly global
// Useful for cross-module communication without imports

// Reverse lookup
console.log(Symbol.keyFor(Symbol.for("app.id"))); // "app.id"
console.log(Symbol.keyFor(Symbol("local")));       // undefined
```

### Practical Use: Metadata and Type Branding

```javascript
// Use Symbols for metadata that should not interfere with data
const VALIDATED = Symbol("validated");
const SCHEMA = Symbol("schema");

function validate(obj, schema) {
  // ... validation logic ...
  obj[VALIDATED] = true;
  obj[SCHEMA] = schema;
  return obj;
}

const user = validate({ name: "Alice" }, userSchema);
// Metadata is attached but invisible to JSON.stringify,
// Object.keys, for...in — it does not pollute the data
```

**The trade-off** with Symbols is discoverability vs safety. Because they are hidden from common iteration, they make great metadata keys and prevent collisions. **Because** they are not truly private (accessible via `getOwnPropertySymbols`), they should not be used for security-sensitive data — use `#private` class fields for that.'''),

    ("js_explain1_15", r'''How does Object.create differ from using the new keyword? When would I use one over the other?''', r'''<think>
Object.create creates an object with a specified prototype without running a constructor.
new calls the constructor, sets up the prototype, and returns the object.
Key difference: Object.create is purely about the prototype link, new is about initialization too.
Object.create is useful for prototype-only inheritance, dictionary objects, and when you want to avoid constructor side effects.
I should show detailed comparisons with practical scenarios.
</think>

## Object.create vs new: Different Tools for Different Jobs

Both create objects with prototype links, but they differ fundamentally in **what else happens** during object creation. Understanding this helps you choose the right tool.

### What Each One Does

```javascript
// -- new Constructor() --
function Person(name) {
  // Step 1: Engine creates {} with __proto__ = Person.prototype
  // Step 2: 'this' is bound to the new object
  this.name = name;  // Step 3: constructor body runs
  // Step 4: the new object is returned (unless constructor
  //         explicitly returns a different object)
}
Person.prototype.greet = function() {
  return `Hi, I am ${this.name}`;
};

const alice = new Person("Alice");
// alice has: own property 'name', prototype method 'greet'

// -- Object.create(proto) --
const personProto = {
  greet() { return `Hi, I am ${this.name}`; }
};

const bob = Object.create(personProto);
// bob has: NO own properties, just the prototype link
bob.name = "Bob"; // must set properties manually

// Both produce equivalent prototype chains:
// alice.__proto__ === Person.prototype
// bob.__proto__ === personProto
```

**The reason** for the difference: `new` is designed for the constructor pattern (create + initialize in one step). `Object.create` is designed for the prototypal pattern (create first, initialize separately).

### When to Use Object.create

**1. Clean prototype-only inheritance (no constructor needed):**

```javascript
// Prototype-based inheritance without constructors
const animal = {
  init(name, sound) {
    this.name = name;
    this.sound = sound;
    return this; // enable chaining
  },
  speak() {
    return `${this.name} says ${this.sound}`;
  }
};

const dog = Object.create(animal).init("Rex", "woof");
const cat = Object.create(animal).init("Whiskers", "meow");
// No constructor functions needed — pure object delegation
```

**2. Inheriting from a prototype without running the parent constructor:**

```javascript
// PROBLEM with constructor-based inheritance:
function ExpensiveBase() {
  this.data = fetchFromDatabase(); // side effect!
}

function Child() {
  // We want Child.prototype to inherit from ExpensiveBase.prototype
  // but we do NOT want to run fetchFromDatabase()
}

// WRONG — runs ExpensiveBase constructor, triggering side effects
Child.prototype = new ExpensiveBase();

// CORRECT — creates the prototype link WITHOUT running constructor
Child.prototype = Object.create(ExpensiveBase.prototype);
Child.prototype.constructor = Child;
```

**3. Dictionary objects with no inherited properties:**

```javascript
// Normal objects inherit from Object.prototype
const normal = {};
console.log("toString" in normal); // true — inherited

// Object.create(null) creates a clean dictionary
const dict = Object.create(null);
console.log("toString" in dict); // false — truly empty

// This is important for safe key-value storage
dict["__proto__"] = "value"; // safe! no prototype to pollute
dict["constructor"] = "value"; // safe! no inherited constructor
```

**4. Using the second argument for property descriptors:**

```javascript
const config = Object.create(null, {
  host: {
    value: "localhost",
    writable: false,    // immutable
    enumerable: true
  },
  port: {
    value: 8080,
    writable: false,
    enumerable: true
  },
  _internal: {
    value: "secret",
    enumerable: false   // hidden from Object.keys
  }
});

console.log(Object.keys(config)); // ["host", "port"]
config.host = "other";            // silently fails (or throws in strict)
```

### Comparison Table

```javascript
// Feature comparison
const a = new Constructor(args);
// ✓ Runs constructor body (initialization)
// ✓ Sets __proto__ to Constructor.prototype
// ✓ Can use 'this' in constructor
// ✗ Cannot skip constructor side effects
// ✗ Cannot create prototype-less objects

const b = Object.create(proto);
// ✗ No constructor runs (manual init needed)
// ✓ Sets __proto__ to any object (or null)
// ✓ Can define property descriptors inline
// ✓ Can create prototype-less objects
// ✓ No side effects
```

**The trade-off**: `new` is convenient when you need initialization logic bundled with object creation. `Object.create` is more flexible and lower-level. **Because** ES6 classes use `new` under the hood, most modern code uses `new` for instances and `Object.create` only for specific patterns: setting up inheritance hierarchies, creating clean dictionaries, and avoiding constructor side effects. **Edge case**: `Object.create` is also the only way to create frozen prototype chains, since you can freeze the proto object before creating descendants.'''),

    # -- 16-20: Error handling patterns -----------------------------------------
    ("js_explain1_16", r'''How do I create proper Error subclasses in JavaScript? What are the best practices for custom error hierarchies?''', r'''<think>
Custom errors are important for structured error handling.
Key points: extending Error properly, setting name and stack, creating hierarchies.
Common mistakes: losing the stack trace, not setting the name property, using string matching instead of instanceof.
Modern approach: Error.captureStackTrace (V8), cause chaining (ES2022).
I should show a complete hierarchy with proper construction.
</think>

## Custom Error Hierarchies in JavaScript

Well-designed error classes let you distinguish between error types programmatically (using `instanceof`) instead of parsing error message strings. But there are several pitfalls in implementing them correctly.

### Basic Custom Error

```javascript
class AppError extends Error {
  constructor(message, options = {}) {
    // ES2022: pass { cause } to chain errors
    super(message, { cause: options.cause });

    // CRITICAL: set the name property — without this,
    // error.name is "Error" (inherited from Error.prototype)
    this.name = this.constructor.name; // "AppError"

    // Optional: V8-specific — cleans up the stack trace
    // by removing the constructor frame
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, this.constructor);
    }
  }
}
```

**The reason** you must set `this.name` is that `Error.prototype.name` defaults to `"Error"`. Without overriding it, your custom error's `toString()` output will misleadingly say `Error: message` instead of `AppError: message`.

### Building a Complete Hierarchy

```javascript
// Base application error
class AppError extends Error {
  constructor(message, { cause, statusCode, code } = {}) {
    super(message, { cause });
    this.name = this.constructor.name;
    this.statusCode = statusCode || 500;
    this.code = code || "INTERNAL_ERROR";
    this.timestamp = new Date().toISOString();

    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, this.constructor);
    }
  }

  // Structured serialization for logging/API responses
  toJSON() {
    return {
      name: this.name,
      message: this.message,
      code: this.code,
      statusCode: this.statusCode,
      timestamp: this.timestamp,
      // Include cause chain for debugging
      ...(this.cause && { cause: this.cause.message })
    };
  }
}

// Specific error types
class NotFoundError extends AppError {
  constructor(resource, id, options = {}) {
    super(`${resource} with id '${id}' not found`, {
      ...options,
      statusCode: 404,
      code: "NOT_FOUND"
    });
    this.resource = resource;
    this.resourceId = id;
  }
}

class ValidationError extends AppError {
  constructor(message, fields = [], options = {}) {
    super(message, {
      ...options,
      statusCode: 400,
      code: "VALIDATION_ERROR"
    });
    this.fields = fields; // [{ field: "email", issue: "invalid format" }]
  }
}

class AuthorizationError extends AppError {
  constructor(action, resource, options = {}) {
    super(`Not authorized to ${action} ${resource}`, {
      ...options,
      statusCode: 403,
      code: "FORBIDDEN"
    });
  }
}
```

### Using the Hierarchy

```javascript
async function getUser(id) {
  try {
    const user = await db.users.findById(id);
    if (!user) {
      throw new NotFoundError("User", id);
    }
    return user;
  } catch (err) {
    if (err instanceof NotFoundError) {
      throw err; // re-throw domain errors as-is
    }
    // Wrap unexpected errors with cause chaining
    throw new AppError("Failed to fetch user", {
      cause: err, // original error preserved for debugging
      code: "DB_ERROR"
    });
  }
}

// In Express middleware
app.use((err, req, res, next) => {
  if (err instanceof AppError) {
    // Structured response — client gets useful info
    res.status(err.statusCode).json(err.toJSON());
  } else {
    // Unknown error — hide internals from client
    console.error("Unhandled error:", err);
    res.status(500).json({ code: "INTERNAL_ERROR", message: "Something went wrong" });
  }
});
```

### Error Cause Chaining (ES2022)

**Important to note**: the `cause` property creates a traceable error chain:

```javascript
async function processOrder(orderId) {
  try {
    const order = await fetchOrder(orderId);
    await chargePayment(order);
  } catch (err) {
    // Chain the original error as the cause
    throw new AppError("Order processing failed", { cause: err });
  }
}

// When you catch it later:
try {
  await processOrder("123");
} catch (err) {
  console.log(err.message);       // "Order processing failed"
  console.log(err.cause.message); // "Payment declined" (original)
  console.log(err.cause.cause);   // possibly another level deep
}
```

**The trade-off** with error hierarchies is granularity vs complexity. Too few classes and you end up string-matching messages. Too many and the hierarchy becomes unwieldy. **Because** `instanceof` checks work through the prototype chain, `catch (err) { if (err instanceof AppError) }` catches ALL your custom errors, while `instanceof ValidationError` catches only validation errors — design your hierarchy accordingly.'''),

    ("js_explain1_17", r'''How should I handle errors in async JavaScript? What are the patterns for async error boundaries and what goes wrong with unhandled errors in Promises?''', r'''<think>
Async error handling is tricky because errors can escape try/catch if you're not careful.
Key patterns: try/catch with await, .catch() on Promises, error boundary wrappers, and the Go-style tuple pattern.
Common mistakes: forgetting to await (error escapes), not catching in Promise.all, swallowing errors silently.
I should show each pattern with the failure mode it prevents.
</think>

## Async Error Handling: Patterns and Boundaries

Error handling in asynchronous code is fundamentally different from synchronous code because errors can "escape" the call stack. Understanding where errors go and how to catch them prevents silent failures.

### The Core Problem

```javascript
// Synchronous — try/catch always works
try {
  throw new Error("sync error");
} catch (err) {
  console.log("Caught:", err.message); // always caught
}

// Asynchronous — try/catch DOES NOT catch callback errors
try {
  setTimeout(() => {
    throw new Error("async error"); // this escapes!
  }, 100);
} catch (err) {
  // NEVER REACHED — the error is thrown in a different
  // call stack frame, long after try/catch has exited
}
```

**The reason** this happens is that `try/catch` only guards the synchronous execution of its block. By the time the callback fires, the try block's stack frame is gone.

### Pattern 1: try/catch with await (Recommended)

```javascript
// await converts Promise rejections into thrown errors,
// making them catchable with try/catch
async function fetchUserData(id) {
  try {
    const response = await fetch(`/api/users/${id}`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }
    const data = await response.json();
    return data;
  } catch (err) {
    // Catches: network errors, HTTP errors, JSON parse errors
    console.error("Failed to fetch user:", err.message);
    throw err; // re-throw so callers know it failed
  }
}
```

### Pattern 2: Safe Wrapper (Go-Style Tuples)

**This works by** converting exceptions into return values, eliminating the need for try/catch:

```javascript
// Generic wrapper that catches errors and returns [error, result]
async function to(promise) {
  try {
    const result = await promise;
    return [null, result];
  } catch (err) {
    return [err, null];
  }
}

// Usage — clean, no try/catch nesting
async function createUser(data) {
  const [validationErr, validated] = await to(validate(data));
  if (validationErr) return { error: "Invalid data" };

  const [dbErr, user] = await to(db.users.create(validated));
  if (dbErr) return { error: "Database error" };

  const [emailErr] = await to(sendWelcomeEmail(user.email));
  if (emailErr) {
    // Non-critical — log but don't fail
    console.warn("Welcome email failed:", emailErr.message);
  }

  return { user };
}
```

### Pattern 3: Async Error Boundaries

```javascript
// Wrap entire subsystems in error boundaries
function asyncBoundary(fn, errorHandler) {
  return async function(...args) {
    try {
      return await fn.apply(this, args);
    } catch (err) {
      return errorHandler(err, ...args);
    }
  };
}

// Apply boundaries to route handlers
const safeGetUser = asyncBoundary(
  async (req, res) => {
    const user = await UserService.findById(req.params.id);
    res.json(user);
  },
  (err, req, res) => {
    console.error("Route error:", err);
    res.status(500).json({ error: "Internal server error" });
  }
);

app.get("/users/:id", safeGetUser);
```

### Common Mistakes

```javascript
// MISTAKE 1: Forgetting to await — error silently disappears
async function processItems(items) {
  items.forEach(async (item) => {
    await process(item); // rejection goes nowhere!
    // forEach does NOT await the returned Promise
  });
  console.log("Done"); // runs BEFORE any items are processed
}

// FIX: use for...of or Promise.all
async function processItems(items) {
  for (const item of items) {
    await process(item); // sequential, properly awaited
  }
  // OR: parallel
  await Promise.all(items.map(item => process(item)));
}

// MISTAKE 2: Promise.all fails fast — one rejection kills all
async function fetchAll(urls) {
  // If ANY fetch fails, ALL results are lost
  const results = await Promise.all(urls.map(u => fetch(u)));
  return results;
}

// FIX: use Promise.allSettled for resilient batch operations
async function fetchAll(urls) {
  const results = await Promise.allSettled(urls.map(u => fetch(u)));
  const successes = results
    .filter(r => r.status === "fulfilled")
    .map(r => r.value);
  const failures = results
    .filter(r => r.status === "rejected")
    .map(r => r.reason);
  return { successes, failures };
}
```

### Edge Case: Error in finally

**Important to note**: errors in `finally` blocks replace the original error:

```javascript
async function risky() {
  try {
    throw new Error("Original error");
  } finally {
    throw new Error("Finally error");
    // The "Original error" is LOST — only "Finally error" propagates
    // This is a language design flaw; always guard finally blocks
  }
}
```

**The trade-off** across patterns: try/catch is familiar but deeply nested. Go-style tuples are flat but lose stack context. Error boundaries are clean but add abstraction. **Because** no single pattern fits all cases, production code typically uses try/catch for simple flows, tuple pattern for multi-step operations, and error boundaries for framework-level code.'''),

    ("js_explain1_18", r'''What is the Result/Either pattern in TypeScript? How do I implement it for type-safe error handling without exceptions?''', r'''<think>
The Result/Either pattern models operations that can fail without using exceptions.
It comes from functional programming (Rust's Result, Haskell's Either).
In TypeScript, discriminated unions work perfectly for this.
Key benefits: errors are in the type system (compiler enforces handling), no hidden throws, composable.
I should show a practical implementation with map/flatMap for chaining.
</think>

## The Result Pattern in TypeScript: Type-Safe Error Handling

The Result pattern models success and failure as **data** rather than control flow (exceptions). **The reason** this pattern is valuable is that TypeScript's type system can then **force** callers to handle errors — the compiler catches missing error handling, not runtime crashes.

### Implementation with Discriminated Unions

```typescript
// Core type definition
type Result<T, E = Error> =
  | { ok: true; value: T }
  | { ok: false; error: E };

// Constructor helpers
function Ok<T>(value: T): Result<T, never> {
  return { ok: true, value };
}

function Err<E>(error: E): Result<never, E> {
  return { ok: false, error };
}

// Usage — the return type TELLS you this can fail
function parseJSON(text: string): Result<unknown, SyntaxError> {
  try {
    return Ok(JSON.parse(text));
  } catch (err) {
    return Err(err as SyntaxError);
  }
}

const result = parseJSON('{"name": "Alice"}');

// TypeScript FORCES you to check before accessing .value
if (result.ok) {
  console.log(result.value); // TypeScript knows this is 'unknown'
} else {
  console.log(result.error.message); // TypeScript knows this is SyntaxError
}

// This WON'T compile — TypeScript catches the missing check
// console.log(result.value);
// Error: Property 'value' does not exist on type '{ ok: false; error: SyntaxError }'
```

### Practical Result Class with Chaining

```typescript
class Result<T, E = Error> {
  private constructor(
    private readonly _ok: boolean,
    private readonly _value?: T,
    private readonly _error?: E,
  ) {}

  static ok<T>(value: T): Result<T, never> {
    return new Result<T, never>(true, value);
  }

  static err<E>(error: E): Result<never, E> {
    return new Result<never, E>(false, undefined, error);
  }

  // Transform the success value (like Array.map)
  map<U>(fn: (value: T) => U): Result<U, E> {
    if (this._ok) return Result.ok(fn(this._value!));
    return Result.err(this._error!);
  }

  // Chain operations that themselves return Results
  flatMap<U>(fn: (value: T) => Result<U, E>): Result<U, E> {
    if (this._ok) return fn(this._value!);
    return Result.err(this._error!);
  }

  // Provide a fallback value on error
  unwrapOr(fallback: T): T {
    return this._ok ? this._value! : fallback;
  }

  // Extract value or throw (escape hatch)
  unwrap(): T {
    if (this._ok) return this._value!;
    throw this._error;
  }

  get isOk(): boolean { return this._ok; }
  get isErr(): boolean { return !this._ok; }
}
```

### Chaining Results (Railway-Oriented Programming)

**This works by** treating the success path as a "railway track" — if any step fails, the error short-circuits through all subsequent steps:

```typescript
type ValidationError = { field: string; message: string };

function validateEmail(input: string): Result<string, ValidationError> {
  if (!input.includes("@")) {
    return Result.err({ field: "email", message: "Must contain @" });
  }
  return Result.ok(input.toLowerCase().trim());
}

function validateAge(input: number): Result<number, ValidationError> {
  if (input < 0 || input > 150) {
    return Result.err({ field: "age", message: "Must be 0-150" });
  }
  return Result.ok(input);
}

// Chain validations — first failure stops the chain
function validateUser(data: { email: string; age: number }) {
  return validateEmail(data.email)
    .flatMap(email =>
      validateAge(data.age)
        .map(age => ({ email, age }))
    );
}

const valid = validateUser({ email: "alice@test.com", age: 30 });
// Result<{ email: string; age: number }, ValidationError>

// Collecting ALL errors (not just the first):
function validateAll<T, E>(results: Result<T, E>[]): Result<T[], E[]> {
  const values: T[] = [];
  const errors: E[] = [];

  for (const r of results) {
    if (r.isOk) values.push(r.unwrap());
    else errors.push((r as any)._error);
  }

  return errors.length > 0 ? Result.err(errors) : Result.ok(values);
}
```

### When to Use Result vs Exceptions

**The trade-off** is explicitness vs convenience:

```typescript
// Use Result when:
// - Failure is EXPECTED (validation, parsing, user input)
// - You want the compiler to enforce error handling
// - You're building a library API

// Use exceptions when:
// - Failure is UNEXPECTED (programmer errors, invariant violations)
// - You need to bail out of deeply nested code
// - The error handling is genuinely exceptional

// ANTI-PATTERN: wrapping everything in Result
function add(a: number, b: number): Result<number, never> {
  return Result.ok(a + b); // this can't fail — Result adds noise
}
```

**Because** TypeScript has discriminated unions, the simple `{ ok, value/error }` pattern is often sufficient without a full Result class. **Important to note**: the key benefit is not the pattern itself but the type system integration — the compiler becomes your error-handling safety net.'''),

    ("js_explain1_19", r'''How should I serialize and deserialize errors in JavaScript? My API errors lose their type and stack trace when sent over the network.''', r'''<think>
This is a practical problem. Error objects don't serialize well with JSON.stringify — they lose name, stack, and custom properties.
I need to show: why JSON.stringify fails on errors, how to implement toJSON, how to deserialize back to typed errors, and how to handle cause chains.
Also relevant: structured clone (for workers), and error serialization in logging.
</think>

## Error Serialization: Preserving Type and Context Across Boundaries

Errors in JavaScript are notoriously bad at serialization because `JSON.stringify(new Error("fail"))` produces `"{}"`. Understanding **why** this happens and how to fix it is essential for any API or logging system.

### Why Errors Don't Serialize

**The reason** is that `Error` properties (`message`, `stack`, `name`) are **non-enumerable**:

```javascript
const err = new Error("something failed");

// JSON.stringify only includes enumerable own properties
console.log(JSON.stringify(err)); // "{}" — empty!

// The properties exist, they are just hidden
console.log(Object.getOwnPropertyDescriptor(err, "message"));
// { value: "something failed", writable: true,
//   enumerable: FALSE, configurable: true }

console.log(Object.getOwnPropertyDescriptor(err, "stack"));
// Same — enumerable: false
```

### Serialization: Error to JSON

```javascript
// Simple serializer function
function serializeError(err) {
  if (!(err instanceof Error)) return { message: String(err) };

  const serialized = {
    name: err.name,
    message: err.message,
    stack: err.stack,
    // Include any custom properties (statusCode, code, etc.)
    ...Object.getOwnPropertyNames(err).reduce((acc, key) => {
      if (key !== "name" && key !== "message" && key !== "stack") {
        acc[key] = err[key];
      }
      return acc;
    }, {})
  };

  // Recursively serialize the cause chain (ES2022)
  if (err.cause) {
    serialized.cause = serializeError(err.cause);
  }

  return serialized;
}

// Or add toJSON to your error base class
class AppError extends Error {
  constructor(message, { cause, code, statusCode } = {}) {
    super(message, { cause });
    this.name = this.constructor.name;
    this.code = code;
    this.statusCode = statusCode;
  }

  toJSON() {
    return {
      name: this.name,
      message: this.message,
      code: this.code,
      statusCode: this.statusCode,
      stack: this.stack,
      ...(this.cause && {
        cause: this.cause instanceof Error
          ? serializeError(this.cause)
          : this.cause
      })
    };
  }
}

// Now JSON.stringify works correctly
const err = new AppError("User not found", { code: "NOT_FOUND", statusCode: 404 });
console.log(JSON.stringify(err));
// {"name":"AppError","message":"User not found","code":"NOT_FOUND","statusCode":404,"stack":"..."}
```

### Deserialization: JSON Back to Typed Errors

**This works by** maintaining a registry of error constructors:

```javascript
// Error type registry
const ERROR_REGISTRY = new Map();

function registerError(ErrorClass) {
  ERROR_REGISTRY.set(ErrorClass.name, ErrorClass);
}

function deserializeError(data) {
  if (!data || !data.name) return new Error(String(data));

  // Look up the constructor by name
  const ErrorClass = ERROR_REGISTRY.get(data.name) || Error;

  const err = new ErrorClass(data.message);
  err.name = data.name;

  // Restore custom properties
  for (const [key, value] of Object.entries(data)) {
    if (key !== "name" && key !== "message" && key !== "stack") {
      if (key === "cause" && value) {
        err.cause = deserializeError(value); // recursive
      } else {
        err[key] = value;
      }
    }
  }

  // Optionally restore the original stack
  if (data.stack) {
    err.stack = data.stack; // original stack from the server
  }

  return err;
}

// Register your custom errors
registerError(AppError);
registerError(NotFoundError);
registerError(ValidationError);

// Round-trip works:
const original = new NotFoundError("User", "123");
const json = JSON.stringify(original);
const restored = deserializeError(JSON.parse(json));
console.log(restored instanceof NotFoundError); // true (if registered)
console.log(restored.message);                  // "User with id '123' not found"
```

### API Response Pattern

```javascript
// Express error middleware — consistent API error responses
app.use((err, req, res, next) => {
  // Development: full error details
  // Production: hide stack and internal details
  const isDev = process.env.NODE_ENV !== "production";

  const response = {
    error: {
      name: err.name,
      message: err instanceof AppError ? err.message : "Internal server error",
      code: err.code || "INTERNAL_ERROR",
      ...(isDev && { stack: err.stack }),
      ...(isDev && err.cause && { cause: serializeError(err.cause) })
    }
  };

  const status = err.statusCode || 500;
  res.status(status).json(response);
});

// Client-side: reconstruct errors from API responses
async function apiCall(url) {
  const res = await fetch(url);
  if (!res.ok) {
    const body = await res.json();
    const err = deserializeError(body.error);
    throw err; // now instanceof checks work on the client
  }
  return res.json();
}
```

**Important to note**: never send stack traces in production responses — they reveal file paths, line numbers, and internal architecture. **The trade-off** with error serialization is that you lose `instanceof` guarantees across the network boundary (unless both sides share the error registry). **Because** JSON has no type system, the registry approach is the best compromise between type safety and practical interoperability.'''),

    ("js_explain1_20", r'''What are error boundaries in React and how do they relate to JavaScript error handling? Can I use them with async code?''', r'''<think>
Error boundaries are React's mechanism for catching rendering errors.
They only catch errors in render, lifecycle methods, and constructors — NOT in event handlers or async code.
This is a common source of confusion.
I need to explain what they catch, what they don't, and how to handle the gaps.
Also worth showing the getDerivedStateFromError and componentDidCatch lifecycle methods.
</think>

## React Error Boundaries: What They Catch and What They Don't

Error boundaries are React components that catch JavaScript errors during rendering and display a fallback UI instead of crashing the entire component tree. **The reason** they exist is that an unhandled error in any component previously unmounted the entire React app.

### How Error Boundaries Work

Error boundaries are class components (no hook equivalent exists) that implement one or both of these lifecycle methods:

```tsx
class ErrorBoundary extends React.Component<
  { children: React.ReactNode; fallback?: React.ReactNode },
  { hasError: boolean; error: Error | null }
> {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  // Called during RENDER phase — must be pure, no side effects
  // Updates state so the next render shows the fallback UI
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  // Called during COMMIT phase — can have side effects
  // Use for logging, error reporting, etc.
  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error("Error boundary caught:", error);
    console.error("Component stack:", errorInfo.componentStack);
    // Send to error tracking service
    errorReporter.captureException(error, { extra: errorInfo });
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback || (
        <div role="alert">
          <h2>Something went wrong</h2>
          <button onClick={() => this.setState({ hasError: false, error: null })}>
            Try again
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// Usage — wrap parts of the tree
function App() {
  return (
    <div>
      <Header /> {/* errors here crash the app */}
      <ErrorBoundary fallback={<p>Dashboard failed to load</p>}>
        <Dashboard /> {/* errors here are contained */}
      </ErrorBoundary>
      <ErrorBoundary fallback={<p>Chat unavailable</p>}>
        <ChatWidget /> {/* isolated from Dashboard errors */}
      </ErrorBoundary>
    </div>
  );
}
```

### What Error Boundaries Catch vs Don't Catch

**Important to note** — error boundaries ONLY catch errors in:

1. Rendering (during `render()` method or function component body)
2. Lifecycle methods (`componentDidMount`, `componentDidUpdate`, etc.)
3. Constructors of child components

**They do NOT catch errors in:**

```tsx
function ProblematicComponent() {
  // 1. EVENT HANDLERS — not caught by error boundary
  const handleClick = () => {
    throw new Error("Click error"); // escapes the boundary!
  };

  // 2. ASYNC CODE — not caught by error boundary
  useEffect(() => {
    async function fetchData() {
      const res = await fetch("/api/data");
      throw new Error("Async error"); // escapes the boundary!
    }
    fetchData();
  }, []);

  // 3. SETTIMEOUT — not caught by error boundary
  useEffect(() => {
    setTimeout(() => {
      throw new Error("Timer error"); // escapes the boundary!
    }, 1000);
  }, []);

  return <button onClick={handleClick}>Click me</button>;
}
```

**The reason** error boundaries cannot catch these is that they rely on React's rendering mechanism. Event handlers and async code execute outside React's render cycle.

### Handling the Gaps

```tsx
// Pattern: Manual error state for event handlers and async code
function DataLoader() {
  const [data, setData] = useState(null);
  const [error, setError] = useState<Error | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const res = await fetch("/api/data");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = await res.json();
        if (!cancelled) setData(json);
      } catch (err) {
        if (!cancelled) setError(err as Error);
      }
    }

    load();
    return () => { cancelled = true; };
  }, []);

  // Option A: Handle locally
  if (error) return <p>Failed to load: {error.message}</p>;

  // Option B: Rethrow during render to let error boundary catch it
  if (error) throw error; // NOW the error boundary will catch it!

  return <div>{data && renderData(data)}</div>;
}
```

### React-Error-Boundary Library (Recommended)

```tsx
import { ErrorBoundary } from "react-error-boundary";

function App() {
  return (
    <ErrorBoundary
      fallbackRender={({ error, resetErrorBoundary }) => (
        <div role="alert">
          <p>Error: {error.message}</p>
          <button onClick={resetErrorBoundary}>Retry</button>
        </div>
      )}
      onError={(error, info) => {
        // Log to service
        logErrorToService(error, info.componentStack);
      }}
      onReset={() => {
        // Reset app state when user clicks retry
        queryClient.clear();
      }}
    >
      <Dashboard />
    </ErrorBoundary>
  );
}
```

**The trade-off** with error boundaries is that they protect against render crashes but create a false sense of security if you assume they catch everything. **Because** async errors and event handler errors are invisible to boundaries, you need a dual strategy: error boundaries for render errors plus `try/catch` or state-based error handling for everything else.'''),

    # -- 21-25: Performance & memory -------------------------------------------
    ("js_explain1_21", r'''What are V8 hidden classes and how do they affect JavaScript performance? How can I write code that V8 optimizes well?''', r'''<think>
V8 hidden classes (also called "shapes" or "maps" internally) are how V8 optimizes property access.
When objects have the same shape (same properties added in the same order), they share a hidden class, enabling fast property access via offsets instead of hash lookups.
Deoptimization happens when you add/delete properties unpredictably, use delete, or change property types.
I should explain the concept, show optimization-friendly patterns, and show what triggers deopt.
</think>

## V8 Hidden Classes: How JavaScript Gets Fast Property Access

V8 (the engine in Chrome and Node.js) transforms JavaScript objects from slow hash-map lookups into fast fixed-offset access using an internal concept called **hidden classes** (also known as "shapes" or "maps"). Understanding this mechanism explains why certain coding patterns are dramatically faster.

### The Problem Hidden Classes Solve

JavaScript objects are dynamic — you can add, remove, and change properties at any time. **The reason** this is a performance challenge is that a naive implementation requires a hash table lookup for every property access. V8 instead creates hidden class transitions:

```javascript
// V8 creates hidden classes as you add properties
const point = {};      // Hidden class C0: {}
point.x = 10;          // Hidden class C1: { x } (offset 0)
point.y = 20;          // Hidden class C2: { x, y } (offsets 0, 1)

// Now point.x is accessed at memory offset 0 — no hash lookup needed
// This is as fast as accessing a field on a C struct
```

**This works by** V8 caching the hidden class on each object. When it sees `point.x`, it checks the hidden class, finds that `x` is at offset 0, and reads directly from memory. This cached lookup is called an **inline cache (IC)**.

### When Objects Share Hidden Classes

```javascript
// GOOD: Same constructor, same property order → same hidden class
function Point(x, y) {
  this.x = x; // transition: C0 → C1
  this.y = y; // transition: C1 → C2
}

const p1 = new Point(1, 2); // hidden class: C2
const p2 = new Point(3, 4); // hidden class: C2 (SHARED!)

// V8 only needs one inline cache for Point.x access
// because p1 and p2 have the same hidden class
// This makes loops over Point arrays extremely fast
```

### What Breaks Hidden Classes (Deoptimization)

```javascript
// BAD: Different property order → different hidden classes
const a = {}; a.x = 1; a.y = 2; // C0 → C1(x) → C2(x,y)
const b = {}; b.y = 1; b.x = 2; // C0 → C3(y) → C4(y,x)
// a and b have DIFFERENT hidden classes despite same properties!
// V8 cannot share inline caches between them

// BAD: Conditional properties → polymorphic call sites
function createUser(name, isAdmin) {
  const user = { name };
  if (isAdmin) user.role = "admin"; // some objects get 'role', some don't
  return user;
}
// V8 sees multiple hidden classes at the same call site → slower

// BAD: Using 'delete' — forces transition to slow "dictionary mode"
const obj = { x: 1, y: 2, z: 3 };
delete obj.y; // V8 abandons hidden classes for this object
// Property access falls back to hash table lookups

// BAD: Changing property types
const config = { timeout: 5000 };
config.timeout = "5s"; // was number, now string
// V8 must deoptimize the inline cache for 'timeout'
```

### Optimization-Friendly Patterns

```javascript
// RULE 1: Initialize all properties in the constructor
class User {
  constructor(name, email, age) {
    // Always set ALL properties, even if undefined
    this.name = name;
    this.email = email;
    this.age = age;
    this.lastLogin = null; // initialize to null, not left absent
    this.preferences = null; // set later, but shape is consistent
  }
}

// RULE 2: Same property order in all objects of the same "type"
// BAD
const users = data.map(d => {
  const u = {};
  if (d.name) u.name = d.name;
  if (d.email) u.email = d.email; // different objects, different shapes
  return u;
});

// GOOD
const users = data.map(d => ({
  name: d.name || null,
  email: d.email || null  // always same shape
}));

// RULE 3: Use Map instead of objects for dynamic keys
// Objects with dynamic keys get deoptimized
const cache = {};
cache[userId1] = data1; // different keys = different hidden classes
cache[userId2] = data2;

// Map is designed for dynamic keys — no hidden class overhead
const cache = new Map();
cache.set(userId1, data1);
cache.set(userId2, data2);

// RULE 4: Avoid changing property types after creation
// If a property starts as a number, keep it a number
```

**The trade-off** with optimizing for hidden classes is code flexibility vs performance. Highly dynamic objects (adding/removing properties at will) are convenient but slow. Fixed-shape objects are fast but require discipline. **Because** V8's optimizer is very good, you rarely need to think about this — but in hot loops processing thousands of objects, consistent shapes can mean 10-50x speedups.'''),

    ("js_explain1_22", r'''What causes JavaScript functions to be deoptimized by V8? How can I detect and fix deoptimization?''', r'''<think>
V8 has multiple compilation tiers: Ignition (interpreter), Sparkplug (baseline), Maglev, and TurboFan (optimizing compiler).
Deoptimization happens when TurboFan's assumptions are invalidated.
Common causes: type changes, hidden class mismatches, try-catch (historically), arguments object misuse, megamorphic call sites.
Detection: --trace-deopt flag, Chrome DevTools performance profiler.
I should explain the compilation pipeline and common deopt triggers.
</think>

## V8 Deoptimization: Why Fast Code Becomes Slow

V8 compiles JavaScript through multiple tiers, with TurboFan producing the fastest machine code. **Deoptimization** occurs when TurboFan's assumptions about your code are proven wrong at runtime, forcing it to fall back to slower execution. Understanding the causes lets you write consistently fast code.

### V8's Compilation Pipeline

```
Your code → Ignition (interpreter) → Sparkplug (baseline) → TurboFan (optimizing)
                  Slow                   Medium                  Fast

TurboFan makes ASSUMPTIONS to generate fast code:
- "x is always a number" → emit integer arithmetic
- "obj always has hidden class C2" → emit direct offset access
- "this function is only called with 2 args" → skip arguments check

When assumptions break → DEOPTIMIZE → fall back to Ignition
```

**The reason** V8 uses this approach is speculative optimization. It observes your code running, makes educated guesses, generates fast code based on those guesses, and deoptimizes if the guesses are wrong.

### Common Deoptimization Triggers

**1. Type instability (most common)**

```javascript
// V8 sees 'add' called with numbers → optimizes for numbers
function add(a, b) {
  return a + b;
}

add(1, 2);     // V8 learns: "a and b are integers"
add(3, 4);     // confirms assumption → optimizes
add("x", "y"); // DEOPT! expected numbers, got strings
// V8 must deoptimize and recompile with broader type assumptions
```

**2. Hidden class changes (polymorphic/megamorphic)**

```javascript
function getX(obj) {
  return obj.x; // V8 caches the hidden class of 'obj'
}

// Monomorphic: one hidden class → fastest
getX({ x: 1, y: 2 });
getX({ x: 3, y: 4 }); // same shape → inline cache hit

// Polymorphic: 2-4 hidden classes → slower (checks multiple caches)
getX({ x: 1 });           // different shape
getX({ x: 1, y: 2, z: 3 }); // another shape

// Megamorphic: 5+ hidden classes → slowest (falls back to generic lookup)
getX({ x: 1, a: 1 });
getX({ x: 1, b: 1 });
getX({ x: 1, c: 1 });
getX({ x: 1, d: 1 });
getX({ x: 1, e: 1 }); // now megamorphic — V8 gives up on caching
```

**3. Changing object shapes after optimization**

```javascript
function processUser(user) {
  // V8 optimizes based on user's hidden class
  return user.name + " (" + user.email + ")";
}

const user = { name: "Alice", email: "a@b.com" };
processUser(user);   // optimized
user.phone = "555";  // hidden class changed!
processUser(user);   // may deoptimize — shape mismatch
```

### Detecting Deoptimization

```bash
# Node.js: trace deoptimizations
node --trace-deopt app.js 2>&1 | grep "DEOPT"

# More detailed: shows reason for each deopt
node --trace-deopt --trace-opt app.js

# Output looks like:
# [deoptimizing (DEOPT eager): begin ... @2 reason: wrong map]
# "wrong map" = unexpected hidden class
# "not a Smi" = expected small integer, got something else
# "wrong call target" = function changed
```

```javascript
// Chrome DevTools: Performance tab
// 1. Record a performance trace
// 2. Look for yellow "Deoptimized" markers in the flame chart
// 3. Click on them to see the deopt reason

// Programmatic detection with Performance API
const obs = new PerformanceObserver((list) => {
  for (const entry of list.getEntries()) {
    if (entry.name.includes("V8.DeoptimizeCode")) {
      console.warn("Deoptimization detected:", entry);
    }
  }
});
```

### Fixes for Common Deopt Causes

```javascript
// FIX 1: Keep types consistent
// BAD
function calculateTotal(items) {
  let total = 0;        // starts as integer (Smi)
  for (const item of items) {
    total += item.price; // if any price is a string → deopt!
  }
  return total;
}

// GOOD: Ensure types at boundaries
function calculateTotal(items) {
  let total = 0;
  for (const item of items) {
    total += Number(item.price); // coerce to number at entry
  }
  return total;
}

// FIX 2: Avoid arguments object
// BAD
function sum() {
  let total = 0;
  for (let i = 0; i < arguments.length; i++) {
    total += arguments[i]; // 'arguments' prevents many optimizations
  }
  return total;
}

// GOOD: use rest parameters
function sum(...nums) {
  let total = 0;
  for (const n of nums) total += n;
  return total;
}
```

**The trade-off** with optimizing for V8 is that over-optimization leads to brittle, unreadable code. **Because** V8 is very good at optimizing "normal" JavaScript, focus on the basics: consistent types, consistent object shapes, and avoid the `arguments` object. Only investigate deoptimization when profiling reveals actual performance problems.'''),

    ("js_explain1_23", r'''What are WeakMap and WeakSet, and why are they important for memory management? When should I use them over Map and Set?''', r'''<think>
WeakMap and WeakSet hold "weak" references — they don't prevent garbage collection of keys.
Key constraints: keys must be objects (not primitives), not iterable, no size property.
Use cases: associating metadata with objects without causing leaks, caching, DOM node tracking.
I should contrast with Map/Set and show practical examples.
</think>

## WeakMap and WeakSet: Garbage-Collector-Friendly Collections

`WeakMap` and `WeakSet` hold references to objects **without preventing garbage collection**. **The reason** they exist is to solve a fundamental problem: how do you associate data with an object without creating a memory leak?

### The Problem They Solve

```javascript
// Using a regular Map to cache computed results
const cache = new Map();

function processElement(element) {
  if (cache.has(element)) return cache.get(element);

  const result = expensiveComputation(element);
  cache.set(element, result);
  return result;
}

// PROBLEM: When the element is removed from the DOM and all
// other references are dropped, it SHOULD be garbage collected.
// But the Map's strong reference keeps it alive forever!
document.body.removeChild(element);
// element is still in cache → memory leak
// The Map entry exists forever unless you manually delete it
```

**This works by** the garbage collector's rules: an object is collected only when NO references to it exist. A regular `Map` key counts as a reference. A `WeakMap` key does NOT.

### WeakMap: The Solution

```javascript
// WeakMap keys are "weak" — they don't prevent GC
const cache = new WeakMap();

function processElement(element) {
  if (cache.has(element)) return cache.get(element);

  const result = expensiveComputation(element);
  cache.set(element, result);
  return result;
}

// When element is removed and dereferenced:
document.body.removeChild(element);
element = null;
// The WeakMap entry is automatically removed by GC!
// No manual cleanup needed
```

### Key Constraints and Why They Exist

```javascript
const wm = new WeakMap();

// 1. Keys MUST be objects (not primitives)
wm.set({}, "value");         // OK
wm.set(document.body, "v");  // OK
// wm.set("string", "v");    // TypeError!
// wm.set(42, "v");          // TypeError!
// The reason: primitives are not garbage collected (they are values,
// not heap-allocated objects), so "weak" reference makes no sense

// 2. NOT iterable — no forEach, no keys(), no values()
// wm.forEach(...)  // TypeError!
// [...wm]          // TypeError!
// The reason: iteration would require strong references to all keys,
// which would defeat the purpose of being "weak"

// 3. No .size property
// console.log(wm.size) // undefined
// The reason: the GC can collect entries at any time, so the
// size could change between checking and using it
```

### Practical Use Cases

**1. Private data for class instances:**

```javascript
// Store private data without # syntax (works in any environment)
const privateData = new WeakMap();

class User {
  constructor(name, ssn) {
    this.name = name; // public
    privateData.set(this, { ssn }); // truly private
  }

  getLastFour() {
    return privateData.get(this).ssn.slice(-4);
  }
}

const user = new User("Alice", "123-45-6789");
console.log(user.name);          // "Alice"
console.log(user.getLastFour()); // "6789"
// No way to access ssn from outside
// When 'user' is GC'd, the private data is also collected
```

**2. Tracking DOM event handlers for cleanup:**

```javascript
const handlers = new WeakMap();

function addTrackedListener(element, event, handler) {
  element.addEventListener(event, handler);

  if (!handlers.has(element)) handlers.set(element, []);
  handlers.get(element).push({ event, handler });
}

function removeAllListeners(element) {
  const list = handlers.get(element) || [];
  for (const { event, handler } of list) {
    element.removeEventListener(event, handler);
  }
  handlers.delete(element);
  // If element is later GC'd, its entry disappears automatically
}
```

**3. Memoization without leaks:**

```javascript
function memoize(fn) {
  const cache = new WeakMap();

  return function(obj) {
    if (cache.has(obj)) return cache.get(obj);
    const result = fn(obj);
    cache.set(obj, result);
    return result;
  };
}

const getArea = memoize((rect) => rect.width * rect.height);

let rect = { width: 10, height: 20 };
getArea(rect); // computed
getArea(rect); // cached

rect = null; // cache entry auto-cleaned by GC
```

### WeakSet: Tagging Objects

```javascript
// Track which objects have been processed
const processed = new WeakSet();

function processOnce(obj) {
  if (processed.has(obj)) return; // already done
  processed.add(obj);
  // ... do work ...
}
// When obj is GC'd, it is automatically removed from the WeakSet
```

**The trade-off** with weak collections is capability vs safety. You lose iteration, size checking, and primitive keys, but you gain automatic memory cleanup. **Because** memory leaks are subtle and cumulative (your app works fine until it runs for hours), using `WeakMap` for caches and metadata should be the default unless you specifically need the features of `Map`.'''),

    ("js_explain1_24", r'''How does memory profiling work in JavaScript? How do I find and fix memory leaks in a Node.js or browser application?''', r'''<think>
Memory profiling involves heap snapshots, allocation timelines, and identifying retained objects.
Tools: Chrome DevTools Memory tab, Node.js --inspect, process.memoryUsage().
Process: take snapshots, compare them, find growing objects, trace retainers.
Common leaks: event listeners, closures, detached DOM trees, forgotten timers, growing arrays/maps.
I should show a practical debugging workflow, not just theory.
</think>

## Memory Profiling in JavaScript: Finding and Fixing Leaks

Memory leaks in JavaScript are objects that grow unbounded because references prevent garbage collection. **The reason** they are hard to find is that JavaScript's automatic GC creates a false sense of safety — if something keeps a reference, the GC cannot help you.

### Step 1: Detect the Leak

```javascript
// Node.js: monitor memory usage over time
setInterval(() => {
  const usage = process.memoryUsage();
  console.log({
    heapUsed: `${(usage.heapUsed / 1024 / 1024).toFixed(1)} MB`,
    heapTotal: `${(usage.heapTotal / 1024 / 1024).toFixed(1)} MB`,
    rss: `${(usage.rss / 1024 / 1024).toFixed(1)} MB`
  });
}, 5000);

// If heapUsed grows continuously without stabilizing,
// you have a memory leak
```

### Step 2: Heap Snapshots (The Primary Tool)

**This works by** capturing a complete snapshot of every object in memory, then comparing snapshots to find what is growing:

```
Chrome DevTools workflow:
1. Open DevTools → Memory tab
2. Take Heap Snapshot (initial baseline)
3. Perform the action you suspect leaks (e.g., open/close a dialog 10 times)
4. Take another Heap Snapshot
5. Select "Comparison" view between snapshots
6. Sort by "# Delta" or "Size Delta" — look for objects that GREW

Node.js workflow:
1. Start with: node --inspect app.js
2. Open chrome://inspect in Chrome
3. Click "inspect" on your Node process
4. Use the Memory tab same as browser
```

### Step 3: Reading the Retainer Tree

**Important to note**: the key information is not WHAT is leaked but WHY it is retained:

```
When you click on a leaked object in the heap snapshot,
the "Retainers" panel shows the chain of references keeping it alive:

Object @12345 (leaked)
  ↑ held by: property 'data' of Object @67890
    ↑ held by: element [42] of Array @11111
      ↑ held by: property 'cache' of Window (global)

This tells you: a global cache array holds a reference
to an object that holds the leaked data.
```

### Common Leak Patterns and Fixes

```javascript
// LEAK 1: Growing event listener list
class EventBus {
  constructor() {
    this.listeners = {}; // listeners accumulate forever
  }

  on(event, callback) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(callback);
    // If callers never call 'off()', this grows without bound
  }

  // FIX: always provide and USE a cleanup mechanism
  on(event, callback) {
    if (!this.listeners[event]) this.listeners[event] = [];
    this.listeners[event].push(callback);

    // Return unsubscribe function
    return () => {
      this.listeners[event] = this.listeners[event]
        .filter(cb => cb !== callback);
    };
  }
}

// LEAK 2: Detached DOM nodes
function createList(items) {
  const container = document.createElement("div");
  // ... add elements to container ...

  // Store references to elements in a data structure
  const elementMap = {};
  items.forEach(item => {
    const el = document.createElement("span");
    container.appendChild(el);
    elementMap[item.id] = el; // strong reference!
  });

  // Later: removing the container from DOM does NOT free elements
  // because elementMap still holds references to them
  // FIX: set elementMap entries to null or use WeakRef
}

// LEAK 3: Closures capturing large scopes
function setupWebSocket(url) {
  const socket = new WebSocket(url);
  const messageHistory = []; // grows forever!

  socket.onmessage = (event) => {
    messageHistory.push(event.data);
    // This closure keeps messageHistory alive as long as
    // the socket exists — and messageHistory grows without limit
  };

  // FIX: limit the history
  socket.onmessage = (event) => {
    messageHistory.push(event.data);
    if (messageHistory.length > 1000) {
      messageHistory.splice(0, messageHistory.length - 1000);
    }
  };
}
```

### Programmatic Leak Detection

```javascript
// Expose GC for testing (V8 only)
// Run with: node --expose-gc app.js
function checkForLeak(action, iterations = 100) {
  global.gc(); // force garbage collection
  const before = process.memoryUsage().heapUsed;

  for (let i = 0; i < iterations; i++) {
    action();
  }

  global.gc();
  const after = process.memoryUsage().heapUsed;
  const diff = after - before;

  console.log(`Memory delta: ${(diff / 1024).toFixed(1)} KB`);
  if (diff > 1024 * 1024) {
    console.warn("Potential leak: >1MB growth after", iterations, "iterations");
  }
}

checkForLeak(() => {
  const data = createSomething();
  useSomething(data);
  // data should be GC-eligible after this
});
```

**The trade-off** with memory profiling is that heap snapshots are expensive — taking one pauses the application (stop-the-world GC). **Because** of this, use allocation timeline sampling for production monitoring and full heap snapshots only during dedicated debugging sessions. **Edge case**: memory that appears stable can still be a leak if the rate is slow enough — a 1KB/second leak takes 17 hours to reach 60MB, but it will eventually crash a long-running server.'''),

    ("js_explain1_25", r'''What is ArrayBuffer in JavaScript and when should I use it? How does it relate to TypedArrays, DataView, and SharedArrayBuffer?''', r'''<think>
ArrayBuffer is the foundation of binary data handling in JavaScript.
TypedArrays provide typed views onto ArrayBuffer.
DataView provides flexible byte-level access with explicit endianness.
SharedArrayBuffer enables shared memory between workers (with Atomics for synchronization).
Use cases: file processing, WebGL, WebAudio, network protocols, WASM interop.
I should explain the architecture and show practical examples.
</think>

## ArrayBuffer and Binary Data in JavaScript

`ArrayBuffer` represents a fixed-length chunk of raw binary memory. **The reason** it exists is that JavaScript originally had no way to work with binary data — everything was strings and numbers. Binary APIs (WebGL, file I/O, network protocols, WebAssembly) require direct memory access.

### The Architecture

```
ArrayBuffer (raw bytes — cannot be read directly)
    │
    ├── TypedArray views (interpret bytes as specific number types)
    │   ├── Uint8Array      (unsigned 8-bit integers)
    │   ├── Int16Array       (signed 16-bit integers)
    │   ├── Float32Array     (32-bit floats)
    │   ├── Float64Array     (64-bit doubles)
    │   └── ... 9 types total
    │
    └── DataView (flexible byte-level access with endianness control)
```

**This works by** separating the memory allocation (ArrayBuffer) from the interpretation (views). The same bytes can be read as different types:

```javascript
// Allocate 16 bytes of raw memory
const buffer = new ArrayBuffer(16);

// View the same memory as different types
const bytes = new Uint8Array(buffer);     // 16 elements (1 byte each)
const ints = new Int32Array(buffer);       // 4 elements (4 bytes each)
const floats = new Float64Array(buffer);   // 2 elements (8 bytes each)

// They all share the SAME underlying memory
ints[0] = 42;
console.log(bytes[0]); // 42 (same memory, different view)
console.log(bytes[1]); // 0
console.log(bytes[2]); // 0
console.log(bytes[3]); // 0 (42 in little-endian: 0x2A 0x00 0x00 0x00)
```

### TypedArrays: Fast Numeric Arrays

```javascript
// TypedArrays are array-like but type-constrained
const positions = new Float32Array(3000); // 3000 floats for WebGL

// They support most Array methods
positions.fill(0);
positions.set([1.0, 2.0, 3.0], 0); // copy values at offset

// But they CLAMP or TRUNCATE values to fit the type
const u8 = new Uint8Array(3);
u8[0] = 256;   // becomes 0 (overflow wraps)
u8[1] = -1;    // becomes 255 (unsigned wraps)
u8[2] = 3.7;   // becomes 3 (truncated, not rounded)

// Uint8ClampedArray is special — it clamps instead of wrapping
// (used by Canvas ImageData)
const clamped = new Uint8ClampedArray(3);
clamped[0] = 256;  // becomes 255 (clamped to max)
clamped[1] = -1;   // becomes 0 (clamped to min)

// Performance: TypedArrays are MUCH faster than regular arrays
// for numeric computation because V8 stores them as contiguous
// memory with no type checks per element
const regular = new Array(1_000_000).fill(0); // each element is a JS object
const typed = new Float64Array(1_000_000);     // contiguous 8MB block
// Iterating 'typed' is 2-10x faster depending on operation
```

### DataView: Byte-Level Control

**The reason** DataView exists is endianness. TypedArrays use the platform's native byte order, but network protocols and file formats often specify a particular endianness:

```javascript
const buffer = new ArrayBuffer(8);
const view = new DataView(buffer);

// Write a 32-bit integer in BIG-ENDIAN (network byte order)
view.setInt32(0, 0x12345678, false); // false = big-endian
// Bytes: 0x12, 0x34, 0x56, 0x78

// Read it back in LITTLE-ENDIAN (x86 native order)
console.log(view.getInt32(0, true).toString(16));
// "78563412" — bytes are reversed

// Practical: parsing a binary protocol header
function parsePacketHeader(buffer) {
  const view = new DataView(buffer);
  return {
    version: view.getUint8(0),           // 1 byte at offset 0
    type: view.getUint8(1),              // 1 byte at offset 1
    length: view.getUint16(2, false),    // 2 bytes, big-endian
    sequence: view.getUint32(4, false),  // 4 bytes, big-endian
  };
}
```

### SharedArrayBuffer: Shared Memory Between Workers

```javascript
// Main thread
const shared = new SharedArrayBuffer(1024);
const view = new Int32Array(shared);

const worker = new Worker("worker.js");
worker.postMessage(shared); // zero-copy transfer

// Worker thread (worker.js)
onmessage = function(e) {
  const view = new Int32Array(e.data);

  // Both threads see the SAME memory — but beware race conditions!
  // Use Atomics for synchronization
  Atomics.add(view, 0, 1);          // atomic increment
  Atomics.store(view, 1, 42);       // atomic write
  const val = Atomics.load(view, 1); // atomic read

  // Wait/notify for thread coordination
  Atomics.wait(view, 2, 0);    // block until view[2] !== 0
  // (in another thread)
  Atomics.notify(view, 2, 1);  // wake one waiting thread
};
```

**Important to note**: `SharedArrayBuffer` requires specific HTTP headers (`Cross-Origin-Opener-Policy` and `Cross-Origin-Embedder-Policy`) due to Spectre mitigations.

### When to Use What

```javascript
// ArrayBuffer + TypedArray: file I/O, canvas pixels, WebGL, audio
const pixels = new Uint8ClampedArray(width * height * 4); // RGBA

// ArrayBuffer + DataView: binary protocols, file format parsing
const header = new DataView(buffer, 0, 12); // parse first 12 bytes

// SharedArrayBuffer + Atomics: parallel computation in workers
const matrix = new Float64Array(new SharedArrayBuffer(8 * 1000000));

// Regular Array: general purpose, mixed types, sparse data
const items = [1, "two", { three: 3 }]; // TypedArray can't do this
```

**The trade-off** is flexibility vs performance. Regular arrays handle any type but have per-element overhead. TypedArrays are restricted to one numeric type but provide C-like performance and memory efficiency. **Because** TypedArrays share the ArrayBuffer's memory, you can parse complex binary structures by creating multiple views at different offsets — making JavaScript viable for systems-level binary processing.'''),
]
