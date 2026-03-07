"""
Batch P1207 -- Modern JavaScript APIs: Proxy, Reflect, WeakRef,
FinalizationRegistry, structuredClone, AbortController.
Target: JS/TS rebalancing. 2 thinking + 3 direct pairs.
"""

pairs = [
    # --- 1. thinking: Proxy and Reflect ---
    {
        "instruction": r'''How do JavaScript Proxy and Reflect work together? Show me practical use cases beyond simple logging.''',
        "output": r'''<think>
Proxy intercepts operations on objects; Reflect provides the default
behavior for each trap. I should show practical uses: validation layer,
observable objects, and lazy initialization. Always use Reflect inside
traps to preserve correct this binding and prototype chains.
</think>

`Proxy` intercepts object operations; `Reflect` provides correct default behavior inside traps:

```javascript
// 1. Validated model -- reject bad assignments
function createModel(schema) {
  return new Proxy({}, {
    set(target, prop, value, receiver) {
      const check = schema[prop];
      if (check && !check(value)) {
        throw new TypeError(`Invalid "${String(prop)}": ${JSON.stringify(value)}`);
      }
      return Reflect.set(target, prop, value, receiver);
    },
  });
}

const user = createModel({
  name: (v) => typeof v === "string" && v.length > 0,
  age: (v) => Number.isInteger(v) && v >= 0 && v <= 150,
});
user.name = "Alice"; // OK
// user.age = -5;    // TypeError

// 2. Observable -- notify on change
function observable(target, onChange) {
  return new Proxy(target, {
    set(obj, prop, value, receiver) {
      const old = Reflect.get(obj, prop, receiver);
      const ok = Reflect.set(obj, prop, value, receiver);
      if (ok && old !== value) onChange(prop, value, old);
      return ok;
    },
  });
}

const state = observable({ count: 0 }, (k, v, old) => {
  console.log(`${String(k)}: ${old} -> ${v}`);
});
state.count = 1; // logs "count: 0 -> 1"

// 3. Lazy initialization
function lazy(factory) {
  const cache = new Map();
  return new Proxy({}, {
    get(_, prop) {
      if (!cache.has(prop)) cache.set(prop, factory(prop));
      return cache.get(prop);
    },
  });
}
const mods = lazy((name) => ({ name, loaded: Date.now() }));
mods.auth; // created on first access, cached after
```

Always use `Reflect.get/set` inside traps -- direct property access breaks getter/setter `this` binding.'''
    },

    # --- 2. direct: WeakRef and FinalizationRegistry ---
    {
        "instruction": r'''Explain JavaScript WeakRef and FinalizationRegistry with a practical caching example.''',
        "output": r'''`WeakRef` holds a reference without preventing GC. `FinalizationRegistry` runs cleanup when an object is collected:

```javascript
class WeakCache {
  #cache = new Map();
  #registry = new FinalizationRegistry((key) => {
    const ref = this.#cache.get(key);
    if (ref && ref.deref() === undefined) {
      this.#cache.delete(key);
    }
  });

  set(key, value) {
    const ref = new WeakRef(value);
    this.#cache.set(key, ref);
    this.#registry.register(value, key, value);
  }

  get(key) {
    const ref = this.#cache.get(key);
    if (!ref) return undefined;
    const value = ref.deref();
    if (value === undefined) {
      this.#cache.delete(key);
      return undefined;
    }
    return value;
  }
}

const cache = new WeakCache();

function fetchData(id) {
  let data = cache.get(id);
  if (data) return data;
  data = { id, payload: new ArrayBuffer(1024 * 100) };
  cache.set(id, data);
  return data;
}

fetchData("123"); // cached
fetchData("123"); // cache hit
// When strong ref is dropped and GC runs, entry is evicted
```

Caveats: GC timing is non-deterministic. `FinalizationRegistry` callbacks may run late or never. Use them for cleanup only, never for correctness.'''
    },

    # --- 3. direct: structuredClone ---
    {
        "instruction": r'''When should I use structuredClone() instead of JSON.parse(JSON.stringify()) for deep cloning in JavaScript?''',
        "output": r'''`structuredClone()` handles types that JSON round-tripping destroys:

```javascript
const original = {
  date: new Date("2025-01-15"),
  regex: /hello\s+world/gi,
  map: new Map([["key", "value"]]),
  set: new Set([1, 2, 3]),
  buffer: new ArrayBuffer(16),
  typed: new Uint8Array([10, 20, 30]),
};

// JSON loses type information
const jsonClone = JSON.parse(JSON.stringify(original));
jsonClone.date;   // string, not Date
jsonClone.map;    // empty object {}

// structuredClone preserves types
const clone = structuredClone(original);
clone.date instanceof Date;          // true
clone.map instanceof Map;            // true
clone.set instanceof Set;            // true
clone.buffer instanceof ArrayBuffer; // true

// Handles circular references
const circular = { name: "root" };
circular.self = circular;
structuredClone(circular); // works
// JSON.stringify(circular); // throws

// Transfer (zero-copy for ArrayBuffers)
const buf = new ArrayBuffer(1024 * 1024);
const moved = structuredClone(buf, { transfer: [buf] });
buf.byteLength;   // 0 -- transferred
moved.byteLength; // 1048576

// Cannot clone: functions, DOM nodes, symbols, prototype chains
```

Use `structuredClone` for `Date`, `Map`, `Set`, `RegExp`, `ArrayBuffer`, circular refs. Use JSON for serialization to strings or very old runtimes.'''
    },

    # --- 4. thinking: AbortController patterns ---
    {
        "instruction": r'''Show me advanced AbortController patterns in JavaScript for cancelling fetch requests, timeouts, and composing multiple abort signals.''',
        "output": r'''<think>
AbortController is a general-purpose cancellation primitive. Beyond
basic fetch cancellation, I should cover AbortSignal.timeout(),
AbortSignal.any() for composing signals, cancelling custom async ops,
and automatic event listener cleanup with the signal option.
</think>

`AbortController` is a general cancellation primitive, not just for fetch:

```javascript
// 1. Timeout with AbortSignal.timeout()
const res = await fetch(url, {
  signal: AbortSignal.timeout(5000),
});

// 2. Compose signals with AbortSignal.any()
async function fetchCancellable(url, userAbort) {
  return fetch(url, {
    signal: AbortSignal.any([
      AbortSignal.timeout(10_000),
      userAbort.signal,
    ]),
  });
}

// 3. Abortable custom async operation
function abortableDelay(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(signal.reason); return; }
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => {
      clearTimeout(timer);
      reject(signal.reason);
    }, { once: true });
  });
}

// 4. Auto-cleanup event listeners
element.addEventListener("click", handler, { signal });
// Listener removed automatically when signal aborts

// 5. Race pattern -- first response wins
async function raceFetch(urls) {
  const ctrl = new AbortController();
  try {
    const result = await Promise.any(
      urls.map((u) => fetch(u, { signal: ctrl.signal }).then((r) => r.json()))
    );
    ctrl.abort(); // cancel remaining
    return result;
  } catch (err) {
    ctrl.abort();
    throw err;
  }
}
```

The `{ signal }` option in `addEventListener` is the cleanest way to manage listener cleanup -- no manual `removeEventListener` needed.'''
    },

    # --- 5. direct: Reflect API ---
    {
        "instruction": r'''What is the Reflect API in JavaScript and why should I use it instead of direct object operations?''',
        "output": r'''`Reflect` provides methods that mirror `Proxy` traps, returning booleans instead of throwing:

```javascript
// Reflect.set returns false on failure (no exception)
const frozen = Object.freeze({ x: 1 });
Reflect.set(frozen, "x", 2); // false -- no TypeError

// Reflect.get preserves receiver for getters
const base = {
  _name: "base",
  get name() { return this._name; },
};
const child = Object.create(base);
child._name = "child";
Reflect.get(base, "name", child); // "child"

// Reflect.ownKeys includes symbols and non-enumerable
const obj = { visible: 1, [Symbol.for("s")]: 2 };
Object.defineProperty(obj, "hidden", { value: 3, enumerable: false });
Object.keys(obj);       // ["visible"]
Reflect.ownKeys(obj);   // ["visible", "hidden", Symbol.for("s")]

// Reflect.construct with different new.target
class Base { constructor() { console.log(new.target.name); } }
class Sub extends Base {}
Reflect.construct(Base, [], Sub); // logs "Sub"

// Reflect.apply -- safer than Function.prototype.apply
function sum(...args) { return args.reduce((a, b) => a + b, 0); }
Reflect.apply(sum, null, [1, 2, 3]); // 6
```

Use `Reflect` inside `Proxy` traps to forward operations correctly, and anywhere you want boolean success/failure instead of exceptions.'''
    },
]
