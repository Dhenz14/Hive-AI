"""
Batch P1213 -- JavaScript performance: Web Workers, requestIdleCallback,
Intersection Observer, virtual DOM diffing, bundle analysis.
Target: JS/TS rebalancing. 2 thinking + 3 direct pairs.
"""

pairs = [
    # --- 1. thinking: Web Workers ---
    {
        "instruction": r'''How do I use Web Workers in a modern JavaScript application to offload heavy computation without blocking the UI?''',
        "output": r'''<think>
Web Workers run JS in a background thread. The main thread stays
responsive while the worker computes. Communication is via postMessage
(structured clone). I should show a practical worker pool pattern
since that is the most common production use, not just a single
worker. Mention Comlink as a convenience library.
</think>

Web Workers run on a separate thread, keeping the UI responsive:

```javascript
// === worker.js ===
self.addEventListener("message", (event) => {
  const { type, payload } = event.data;
  if (type === "parse-csv") {
    const lines = payload.split("\n");
    const headers = lines[0].split(",");
    const results = [];
    for (let i = 1; i < lines.length; i++) {
      if (!lines[i].trim()) continue;
      const vals = lines[i].split(",");
      const row = {};
      headers.forEach((h, idx) => { row[h.trim()] = vals[idx]?.trim(); });
      results.push(row);
    }
    self.postMessage({ type: "result", payload: results });
  }
});

// === main.js -- worker pool ===
class WorkerPool {
  #workers; #queue = []; #active = new Map();

  constructor(url, size = navigator.hardwareConcurrency || 4) {
    this.#workers = Array.from({ length: size }, () => {
      const w = new Worker(url, { type: "module" });
      w.addEventListener("message", (e) => {
        if (e.data.type !== "result") return;
        this.#active.get(w)(e.data.payload);
        this.#active.delete(w);
        this.#drain(w);
      });
      return w;
    });
  }

  run(msg) {
    return new Promise((resolve) => {
      const idle = this.#workers.find((w) => !this.#active.has(w));
      if (idle) { this.#active.set(idle, resolve); idle.postMessage(msg); }
      else this.#queue.push({ msg, resolve });
    });
  }

  #drain(w) {
    if (this.#queue.length) {
      const { msg, resolve } = this.#queue.shift();
      this.#active.set(w, resolve);
      w.postMessage(msg);
    }
  }
}

const pool = new WorkerPool("./worker.js", 4);
const csv = await fetch("/data/large.csv").then((r) => r.text());
const rows = await pool.run({ type: "parse-csv", payload: csv });
```

For simpler cases, `Comlink` wraps message passing in a proxy-based RPC so worker functions feel like local async calls.'''
    },

    # --- 2. direct: requestIdleCallback ---
    {
        "instruction": r'''How does requestIdleCallback work and when should I use it instead of setTimeout or requestAnimationFrame?''',
        "output": r'''`requestIdleCallback` schedules work during browser idle periods -- after rendering and event handling:

```javascript
// Process a queue without blocking interactions
function processQueue(items, processItem) {
  let i = 0;
  function work(deadline) {
    while (i < items.length && deadline.timeRemaining() > 1) {
      processItem(items[i++]);
    }
    if (i < items.length) requestIdleCallback(work);
  }
  requestIdleCallback(work);
}
processQueue(analyticsEvents, sendToAnalytics);

// With timeout -- ensure work runs within N ms
requestIdleCallback(() => initAnalytics(), { timeout: 2000 });

// Cancel if no longer needed
const handle = requestIdleCallback(() => { /* ... */ });
cancelIdleCallback(handle);

// When to use which scheduler:
//
// requestAnimationFrame:
//   Visual updates, animations. Runs before paint (~16ms).
//
// setTimeout(fn, 0):
//   Yield to event loop. Still blocks if tasks queued.
//
// requestIdleCallback:
//   Analytics, prefetch, cache warming. May be delayed under load.
//
// queueMicrotask:
//   Highest priority. Runs before any macro task.

// Safari fallback (no rIC support)
const scheduleIdle = typeof requestIdleCallback !== "undefined"
  ? requestIdleCallback
  : (fn) => setTimeout(fn, 100);
```

Never put user-visible updates in `requestIdleCallback` -- it can be delayed by seconds under load. Use it for analytics, prefetching, and non-critical cleanup.'''
    },

    # --- 3. direct: Intersection Observer ---
    {
        "instruction": r'''Show how to use Intersection Observer for lazy loading images, infinite scroll, and tracking element visibility.''',
        "output": r'''`IntersectionObserver` detects when elements enter/leave the viewport without scroll listeners:

```javascript
// 1. Lazy loading images
const imgObserver = new IntersectionObserver(
  (entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        const img = entry.target;
        img.src = img.dataset.src;
        imgObserver.unobserve(img);
      }
    }
  },
  { rootMargin: "200px" } // load 200px before visible
);
document.querySelectorAll("img[data-src]").forEach((img) => imgObserver.observe(img));

// 2. Infinite scroll
function setupInfiniteScroll(sentinel, loadMore) {
  let loading = false;
  const obs = new IntersectionObserver(
    async ([entry]) => {
      if (entry.isIntersecting && !loading) {
        loading = true;
        const hasMore = await loadMore();
        loading = false;
        if (!hasMore) obs.disconnect();
      }
    },
    { rootMargin: "500px" }
  );
  obs.observe(sentinel);
  return () => obs.disconnect();
}

// 3. Visibility tracking
function trackVisibility(elements, onVisible) {
  const seen = new WeakSet();
  const obs = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting && !seen.has(e.target)) {
          seen.add(e.target);
          onVisible(e.target);
        }
      }
    },
    { threshold: 0.5 } // 50% visible
  );
  elements.forEach((el) => obs.observe(el));
}

// 4. Sticky header shadow
const sentinel = document.createElement("div");
document.body.prepend(sentinel);
new IntersectionObserver(([e]) => {
  document.querySelector("header").classList.toggle("shadow", !e.isIntersecting);
}).observe(sentinel);
```

More performant than scroll listeners -- the browser batches calculations off the main thread.'''
    },

    # --- 4. thinking: virtual DOM diffing ---
    {
        "instruction": r'''Explain how virtual DOM diffing works at a high level. Implement a simple diff and patch algorithm in JavaScript.''',
        "output": r'''<think>
Virtual DOM diffing compares two lightweight JS trees and produces
patches for the real DOM. The classic algorithm: compare root nodes,
if different type replace subtree, if same type diff props, then
recursively diff children. React uses heuristics to reduce O(n^3)
to O(n): different types produce different trees, keys identify
moved children, only compare siblings.
</think>

Diffing compares two virtual node trees and produces minimal DOM patches:

```javascript
function h(type, props, ...children) {
  return { type, props: props || {},
    children: children.flat().map((c) =>
      typeof c === "string" ? { type: "TEXT", props: { nodeValue: c }, children: [] } : c
    ),
  };
}

function diff(oldN, newN, patches = [], path = []) {
  if (!oldN && newN) { patches.push({ op: "CREATE", path, node: newN }); return patches; }
  if (oldN && !newN) { patches.push({ op: "REMOVE", path }); return patches; }
  if (oldN.type !== newN.type) { patches.push({ op: "REPLACE", path, node: newN }); return patches; }

  // Same type -- diff props
  const propChanges = [];
  const allKeys = new Set([...Object.keys(oldN.props), ...Object.keys(newN.props)]);
  for (const k of allKeys) {
    if (oldN.props[k] !== newN.props[k]) propChanges.push({ k, v: newN.props[k] });
  }
  if (propChanges.length) patches.push({ op: "PROPS", path, changes: propChanges });

  // Diff children by index
  const max = Math.max(oldN.children.length, newN.children.length);
  for (let i = 0; i < max; i++) {
    diff(oldN.children[i], newN.children[i], patches, [...path, i]);
  }
  return patches;
}

function applyPatches(root, patches) {
  for (const p of patches) {
    let el = root;
    for (const i of p.path) el = el.childNodes[i];
    switch (p.op) {
      case "CREATE": el.parentNode.appendChild(createElement(p.node)); break;
      case "REMOVE": el.parentNode.removeChild(el); break;
      case "REPLACE": el.parentNode.replaceChild(createElement(p.node), el); break;
      case "PROPS":
        for (const { k, v } of p.changes) {
          v === undefined ? el.removeAttribute(k) : el.setAttribute(k, v);
        }
    }
  }
}
```

Real frameworks add keys for reordering, batched updates, and compile-time optimizations. Core insight: diffing JS objects is far cheaper than touching the real DOM.'''
    },

    # --- 5. direct: bundle analysis ---
    {
        "instruction": r'''How do I analyze and reduce my JavaScript bundle size? Show tools and common optimization techniques.''',
        "output": r'''Bundle analysis identifies what makes your app large. Tools and techniques:

```javascript
// 1. Vite visualizer
// vite.config.ts
import { visualizer } from "rollup-plugin-visualizer";
export default defineConfig({
  plugins: [visualizer({ open: true, gzipSize: true })],
  build: {
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ["react", "react-dom"],
          charts: ["recharts"],
        },
      },
    },
  },
});

// 2. Dynamic imports -- code split at route level
const Dashboard = lazy(() => import("./pages/Dashboard"));

// 3. Tree-shaking: import only what you use
// BAD: import _ from "lodash";          // 70KB+
// GOOD: import debounce from "lodash/debounce"; // 4KB
// BEST: use native methods instead

// 4. Common replacements
// moment.js (300KB) --> dayjs (2KB)
// lodash (70KB)     --> native methods or lodash-es
// axios (13KB)      --> fetch (built-in)
// uuid (9KB)        --> crypto.randomUUID() (built-in)

// 5. CLI analysis tools
// npx source-map-explorer dist/assets/index-*.js
// npx depcheck  -- find unused dependencies

// 6. Bundle budgets in CI (package.json)
// "bundlewatch": {
//   "files": [
//     { "path": "dist/assets/index-*.js", "maxSize": "150KB" }
//   ]
// }
```

Start with the visualizer, identify largest modules, then apply targeted fixes: dynamic imports for routes, tree-shakeable alternatives, manual chunk splitting. Target under 150KB gzipped for initial load.'''
    },
]
