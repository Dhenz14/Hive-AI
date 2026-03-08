"""Understanding-focused training pairs: explain, analyze, compare, and review code."""
PAIRS = [
    # ===================== EXPLAIN THIS CODE (8 pairs) =====================

    # Python: decorator with args (thinking)
    (
        "understand1_01",
        r'''What does this Python code do? Walk me through it step by step.

```python
def retry(max_attempts=3, delay=1.0, exceptions=(Exception,)):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except exceptions as e:
                    last_exc = e
                    if attempt < max_attempts:
                        await asyncio.sleep(delay * (2 ** (attempt - 1)))
            raise last_exc
        return wrapper
    return decorator
```''',
        r'''<think>
This is a decorator factory — a function that returns a decorator, which itself returns a wrapper. I should walk through the three layers: the outermost function captures config, the middle one captures the original function, and the innermost one is the actual retry logic. The exponential backoff pattern (delay * 2^(attempt-1)) is worth highlighting.
</think>

## Walkthrough: Async Retry Decorator with Exponential Backoff

This code defines a **decorator factory** — a three-layer function pattern that lets you write `@retry(max_attempts=5)` with configurable parameters.

### Layer 1: `retry(max_attempts, delay, exceptions)` — The Factory

The outermost function captures configuration via closure variables:
- `max_attempts`: how many times to try before giving up (default 3)
- `delay`: base delay in seconds between retries (default 1.0)
- `exceptions`: a tuple of exception types to catch (default catches all)

It returns `decorator`, the actual decorator function.

### Layer 2: `decorator(func)` — The Decorator

This receives the function being decorated and returns `wrapper`. The `@functools.wraps(func)` call preserves the original function's name, docstring, and metadata so that introspection tools still work.

### Layer 3: `wrapper(*args, **kwargs)` — The Retry Logic

This is what actually runs when you call the decorated function:

1. **Loop** from attempt 1 to `max_attempts`
2. **Try** calling the original async function with `await func(*args, **kwargs)`
3. **On success**: return the result immediately — no retries needed
4. **On failure** (if the exception matches `exceptions`): store the exception, and if this wasn't the last attempt, **sleep with exponential backoff**: `delay * 2^(attempt - 1)`
   - Attempt 1 fails → sleep `1.0s`
   - Attempt 2 fails → sleep `2.0s`
   - Attempt 3 fails → no sleep, fall through
5. After all attempts are exhausted, **re-raise the last exception**

### Usage Example

```python
@retry(max_attempts=4, delay=0.5, exceptions=(ConnectionError, TimeoutError))
async def fetch_data(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            return await resp.json()
```

### Key Design Points

- **Async-only**: The wrapper uses `await`, so this only works on async functions. A sync version would need `time.sleep` instead.
- **Exponential backoff** prevents thundering herd problems — each retry waits longer, giving the failing service time to recover.
- **Selective exception catching**: By defaulting to `(Exception,)` but allowing a tuple, you can restrict retries to transient errors only (network timeouts) and let programming errors propagate immediately.'''
    ),

    # Python: async context manager (direct)
    (
        "understand1_02",
        r'''Explain what this code does:

```python
class ConnectionPool:
    def __init__(self, dsn: str, min_size: int = 2, max_size: int = 10):
        self._dsn = dsn
        self._pool: asyncio.Queue[Connection] = asyncio.Queue(maxsize=max_size)
        self._min_size = min_size
        self._size = 0
        self._lock = asyncio.Lock()

    async def _create_connection(self) -> Connection:
        conn = await asyncpg.connect(self._dsn)
        self._size += 1
        return conn

    async def acquire(self) -> Connection:
        try:
            return self._pool.get_nowait()
        except asyncio.QueueEmpty:
            async with self._lock:
                if self._size < self._pool.maxsize:
                    return await self._create_connection()
            return await self._pool.get()

    async def release(self, conn: Connection) -> None:
        await self._pool.put(conn)

    async def __aenter__(self):
        for _ in range(self._min_size):
            conn = await self._create_connection()
            await self._pool.put(conn)
        return self

    async def __aexit__(self, *exc):
        while not self._pool.empty():
            conn = self._pool.get_nowait()
            await conn.close()
```''',
        r'''## Async Database Connection Pool

This class implements a **connection pool** for async database connections using `asyncpg`. Connection pools avoid the overhead of creating a new database connection for every query by reusing a set of pre-established connections.

### How It Works

**Initialization** (`__init__`): Sets up an `asyncio.Queue` as the pool storage with a max capacity. The queue acts as a thread-safe (coroutine-safe) FIFO buffer. `_size` tracks total connections created (both in the pool and checked out).

**Async Context Manager** (`__aenter__` / `__aexit__`): When you write `async with ConnectionPool(dsn) as pool:`, the `__aenter__` method pre-creates `min_size` connections and puts them in the queue, so they're ready before any queries run. On exit, `__aexit__` drains the queue and closes every connection.

**Acquiring a Connection** (`acquire`): Uses a three-tier strategy:
1. **Fast path**: `get_nowait()` tries to grab a connection from the pool without waiting. If one is available, it returns instantly.
2. **Create path**: If the pool is empty but we haven't hit `max_size`, create a new connection. The `asyncio.Lock` prevents a race condition where multiple coroutines could simultaneously check `_size` and exceed the max.
3. **Wait path**: If the pool is empty AND we're at max capacity, `await self._pool.get()` blocks the coroutine until another coroutine releases a connection.

**Releasing** (`release`): Simply puts the connection back into the queue, making it available for the next `acquire()` call.

### Potential Issues

- **No health checking**: A connection could be stale or broken when acquired. Production pools typically run a `SELECT 1` before returning a connection.
- **`_size` mutation outside the lock**: In `__aenter__`, `_create_connection()` increments `_size` without holding `self._lock`. This is safe during startup (single coroutine), but the design is fragile.
- **No timeout on acquire**: If all connections are checked out and none are released, `await self._pool.get()` blocks forever. A `asyncio.wait_for` wrapper would add a timeout.'''
    ),

    # Python: metaclass (thinking)
    (
        "understand1_03",
        r'''What's going on in this Python code?

```python
class SingletonMeta(type):
    _instances = {}

    def __call__(cls, *args, **kwargs):
        if cls not in cls._instances:
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        return cls._instances[cls]

class Database(metaclass=SingletonMeta):
    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self._conn = None

    def connect(self):
        if self._conn is None:
            self._conn = create_connection(self.connection_string)
        return self._conn
```''',
        r'''<think>
This is a metaclass-based Singleton pattern. The key insight is that `type.__call__` is what runs when you do `Database(...)` — it normally calls `__new__` then `__init__`. By overriding `__call__` in the metaclass, we intercept object creation itself. I should explain the metaclass mechanism and the singleton behavior, plus note the caveat that `__init__` only runs once.
</think>

## Metaclass-Based Singleton Pattern

This implements the **Singleton pattern** using a Python metaclass, ensuring that only one instance of `Database` ever exists regardless of how many times you call `Database(...)`.

### How Metaclasses Work Here

In Python, classes are themselves objects — instances of their metaclass. Normally, the metaclass is `type`. When you write `Database("postgres://...")`, Python calls `type.__call__(Database, "postgres://...")`, which internally invokes `Database.__new__()` then `Database.__init__()`.

`SingletonMeta` subclasses `type` and overrides `__call__`, intercepting the moment you try to create an instance:

1. **First call** — `Database("postgres://localhost/db")`:
   - `cls` is the `Database` class itself
   - `Database` is not in `_instances`, so `super().__call__(*args, **kwargs)` runs, which creates and initializes a real `Database` instance
   - The instance is stored in `_instances[Database]`
   - Returns the new instance

2. **Subsequent calls** — `Database("postgres://other/db")`:
   - `Database` IS in `_instances`
   - Returns the **same instance** from the first call
   - `__init__` is **NOT called again** — the `"postgres://other/db"` argument is silently ignored

### The `_instances` Dict

`_instances` is a **class variable on the metaclass**, shared across all classes that use `SingletonMeta`. Each class gets its own key, so if you had `class Cache(metaclass=SingletonMeta)`, it would have its own separate singleton independent of `Database`.

### Caveats

- **Constructor arguments are ignored after the first call**: This is a subtle trap. `Database("prod_db")` followed by `Database("test_db")` returns the prod instance — the test connection string is silently discarded.
- **Not thread-safe**: Two threads could both check `cls not in cls._instances` simultaneously, creating two instances. A `threading.Lock` around the check would fix this.
- **Testing difficulty**: Singletons make unit testing harder because state persists between tests. You'd need to manually clear `SingletonMeta._instances` in test teardown.'''
    ),

    # Rust: lifetime annotations in a struct (thinking)
    (
        "understand1_04",
        r'''Can you explain what the lifetimes are doing in this Rust code?

```rust
struct Parser<'input> {
    source: &'input str,
    position: usize,
}

impl<'input> Parser<'input> {
    fn new(source: &'input str) -> Self {
        Parser { source, position: 0 }
    }

    fn next_token(&mut self) -> Option<&'input str> {
        let remaining = &self.source[self.position..];
        let end = remaining.find(char::is_whitespace).unwrap_or(remaining.len());
        if end == 0 {
            return None;
        }
        let token = &self.source[self.position..self.position + end];
        self.position += end;
        while self.position < self.source.len()
            && self.source.as_bytes()[self.position].is_ascii_whitespace()
        {
            self.position += 1;
        }
        self.position = self.position.min(self.source.len());
        Some(token)
    }
}
```''',
        r'''<think>
The key here is the `'input` lifetime on `Parser` and how it propagates. The struct borrows from the source string, and `next_token` returns slices that borrow from the *original source*, not from the parser. That's the crucial distinction — the return type is `&'input str`, not `&'self str`. This means tokens can outlive the parser as long as the source string is alive.
</think>

## Lifetime Annotations in the Parser

The `'input` lifetime serves one critical purpose: it tells the Rust compiler **how long the borrowed data inside `Parser` must remain valid**, and it connects the lifetime of returned tokens back to the original source string.

### What `'input` Means on the Struct

```rust
struct Parser<'input> {
    source: &'input str,
    // ...
}
```

This says: "A `Parser` holds a reference to a `str` that must live at least as long as `'input`." The parser does **not own** the source string — it borrows it. The lifetime parameter `'input` is a name the compiler uses to track that borrow.

### The Key Insight: `next_token`'s Return Type

```rust
fn next_token(&mut self) -> Option<&'input str>
```

The return type is `&'input str` — a reference tied to the **original source string's lifetime**, NOT to the parser's lifetime. This is crucial because it means:

```rust
let source = String::from("hello world");
let mut parser = Parser::new(&source);
let token = parser.next_token();  // token borrows from `source`
drop(parser);                      // parser is gone
println!("{}", token.unwrap());    // still valid — token borrows `source`, not `parser`
```

If the return type were instead `&str` with an implicit `&'_ str` tied to `&mut self`, the token would be invalidated when the parser is dropped or mutably borrowed again.

### How It Works Mechanically

Inside `next_token`, the method creates `token` by slicing `self.source`:

```rust
let token = &self.source[self.position..self.position + end];
```

Since `self.source` is `&'input str`, any sub-slice of it is also `&'input str`. The compiler verifies that the return type matches — the slice inherits the source's lifetime, not the parser's.

### Why This Matters

This is a **zero-copy parser**. It never allocates new strings for tokens; every token is a view into the original source. The lifetime system guarantees at compile time that the source string cannot be freed or modified while any token references still exist.'''
    ),

    # Rust: trait object vs generic (direct)
    (
        "understand1_05",
        r'''What's the difference between these two Rust function signatures? When would you use each?

```rust
// Version A
fn process_items(items: &[Box<dyn Processor>]) -> Vec<Output> {
    items.iter().map(|item| item.process()).collect()
}

// Version B
fn process_items<T: Processor>(items: &[T]) -> Vec<Output> {
    items.iter().map(|item| item.process()).collect()
}
```''',
        r'''## Trait Objects (`dyn`) vs Generics in Rust

These two signatures compile and look similar but have fundamentally different behavior at both compile time and runtime.

### Version A: Dynamic Dispatch with Trait Objects

```rust
fn process_items(items: &[Box<dyn Processor>]) -> Vec<Output>
```

- **One function** is compiled. It works with any mix of types in the same slice.
- Each `Box<dyn Processor>` is a **fat pointer**: a pointer to the data + a pointer to a vtable (virtual method table) containing the `process()` function pointer.
- Method calls go through **indirect dispatch** at runtime: load the vtable, look up `process`, call through the function pointer.
- The slice can contain **heterogeneous types**: `items[0]` could be `ImageProcessor`, `items[1]` could be `AudioProcessor`, as long as both implement `Processor`.

### Version B: Static Dispatch with Generics

```rust
fn process_items<T: Processor>(items: &[T]) -> Vec<Output>
```

- The compiler generates a **separate copy** of this function for each concrete type `T` used (monomorphization). If called with `ImageProcessor` and `AudioProcessor`, two versions exist in the binary.
- Method calls are **direct** — the compiler knows the exact type and can inline `process()`.
- The slice must be **homogeneous**: every element must be the same type `T`. You cannot mix `ImageProcessor` and `AudioProcessor` in one call.

### When to Use Each

**Use `dyn` (Version A) when:**
- You need a collection of **different types** implementing the same trait
- You're building plugin systems or extensible architectures
- You want to reduce binary size (one function, not N copies)
- The trait methods are not performance-critical hot paths

**Use generics (Version B) when:**
- All items are the **same concrete type**
- Performance matters — the compiler can inline and optimize
- You want the compiler to catch type mismatches at compile time
- You're writing library code where users benefit from zero-cost abstraction

### Performance Note

The overhead of dynamic dispatch is typically a vtable lookup (one cache miss in the worst case) per method call. For most applications this is negligible. But in tight loops processing millions of items, the inability to inline through `dyn` can prevent auto-vectorization and other optimizations that generics enable.'''
    ),

    # Go: goroutine with select/channel pattern (thinking)
    (
        "understand1_06",
        r'''Walk me through what this Go code does:

```go
func fanIn(ctx context.Context, channels ...<-chan Result) <-chan Result {
    var wg sync.WaitGroup
    merged := make(chan Result)

    output := func(ch <-chan Result) {
        defer wg.Done()
        for {
            select {
            case val, ok := <-ch:
                if !ok {
                    return
                }
                select {
                case merged <- val:
                case <-ctx.Done():
                    return
                }
            case <-ctx.Done():
                return
            }
        }
    }

    wg.Add(len(channels))
    for _, ch := range channels {
        go output(ch)
    }

    go func() {
        wg.Wait()
        close(merged)
    }()

    return merged
}
```''',
        r'''<think>
This is the fan-in concurrency pattern — multiple input channels merged into one output channel, with context cancellation. The nested select is important: the outer select receives from the input channel OR detects context cancellation, and the inner select sends to the merged channel OR detects context cancellation. Without the inner select, a slow consumer could block the goroutine even after cancellation.
</think>

## Fan-In Pattern with Context Cancellation

This function merges **multiple input channels into a single output channel**, a classic Go concurrency pattern called "fan-in." It also handles graceful shutdown via `context.Context`.

### Step-by-Step Execution

**1. Setup:**
- Creates a `WaitGroup` to track when all input goroutines finish
- Creates `merged`, an unbuffered output channel
- Defines `output`, a closure that drains one input channel into `merged`

**2. Launch goroutines** — one per input channel:
```go
wg.Add(len(channels))
for _, ch := range channels {
    go output(ch)
}
```
Each goroutine runs the `output` closure, reading from its assigned input channel and forwarding values to `merged`.

**3. The `output` closure** — the core logic with a nested `select`:

**Outer select:**
```go
case val, ok := <-ch:   // receive from input channel
case <-ctx.Done():      // context was cancelled
```
This blocks until either a value arrives from the input or the context is cancelled. If the channel is closed (`ok == false`), the goroutine returns.

**Inner select:**
```go
case merged <- val:     // send to output channel
case <-ctx.Done():      // context was cancelled while trying to send
```
This is the subtle part. After receiving a value, we need to *send* it to `merged`. But if the consumer has stopped reading (maybe the context was cancelled), this send would block forever. The inner select prevents that deadlock — if the context is cancelled while waiting to send, the goroutine exits cleanly.

**4. Cleanup goroutine:**
```go
go func() {
    wg.Wait()
    close(merged)
}()
```
A separate goroutine waits for ALL input goroutines to finish, then closes the `merged` channel. This signals to the consumer that no more values will arrive.

### Why the Nested Select Matters

Without the inner select, consider: context is cancelled, but the goroutine has already received `val` from `ch`. It tries `merged <- val`, but no one is reading `merged` anymore. The goroutine blocks forever — a **goroutine leak**. The nested select ensures the goroutine can bail out at both the receive AND send stages.

### Usage

```go
results := fanIn(ctx, searchGoogle, searchBing, searchDDG)
for r := range results {
    fmt.Println(r)
}
```

All three search channels feed into one stream that you consume with a simple `range` loop.'''
    ),

    # Go: interface embedding (direct)
    (
        "understand1_07",
        r'''What does this Go code achieve with the embedded interfaces?

```go
type Reader interface {
    Read(p []byte) (n int, err error)
}

type Writer interface {
    Write(p []byte) (n int, err error)
}

type Closer interface {
    Close() error
}

type ReadWriter interface {
    Reader
    Writer
}

type ReadWriteCloser interface {
    ReadWriter
    Closer
}

type limitedReader struct {
    r         Reader
    remaining int64
}

func (lr *limitedReader) Read(p []byte) (int, error) {
    if lr.remaining <= 0 {
        return 0, io.EOF
    }
    if int64(len(p)) > lr.remaining {
        p = p[:lr.remaining]
    }
    n, err := lr.r.Read(p)
    lr.remaining -= int64(n)
    return n, err
}
```''',
        r'''## Interface Embedding and Composition in Go

This code demonstrates Go's approach to **interface composition** — building larger interfaces from smaller ones — and shows a concrete implementation that decorates a `Reader`.

### The Interface Hierarchy

Go doesn't have inheritance, but interfaces can **embed** other interfaces, combining their method sets:

- `Reader` requires one method: `Read([]byte) (int, error)`
- `Writer` requires one method: `Write([]byte) (int, error)`
- `Closer` requires one method: `Close() error`
- `ReadWriter` embeds both `Reader` and `Writer`, so any type satisfying `ReadWriter` must have both `Read` and `Write`
- `ReadWriteCloser` embeds `ReadWriter` and `Closer`, requiring all three methods

This is **interface segregation** — you define the smallest useful interfaces and compose them. A function that only needs to read accepts `Reader`, not `ReadWriteCloser`. This keeps dependencies minimal and makes testing easier (mock only what's needed).

### The `limitedReader` Implementation

`limitedReader` wraps any `Reader` and enforces a byte limit:

1. It holds a reference to an inner `Reader` and a `remaining` counter
2. On each `Read` call:
   - If `remaining <= 0`, it returns `io.EOF` — no more data
   - If the caller's buffer is larger than `remaining`, it **shrinks the buffer** with `p = p[:lr.remaining]` — this is a slice reslice, not a copy
   - It delegates to the inner reader with the possibly-smaller buffer
   - It subtracts the bytes actually read from `remaining`

This is the **decorator pattern**: `limitedReader` satisfies `Reader` itself (it has a `Read` method), so it can be used anywhere a `Reader` is expected. You can stack decorators — wrap a `limitedReader` inside a `bufio.Reader` inside a `gzip.Reader`, and each layer only knows about the `Reader` interface.

### Design Principle

This pattern (small interfaces + embedding + decorators) is idiomatic Go. The standard library's `io` package uses exactly this approach. Because interfaces are satisfied **implicitly** (no `implements` keyword), any type with a `Read([]byte) (int, error)` method is a `Reader` — no coupling to this package required.'''
    ),

    # JS: Proxy handler with Reflect (thinking)
    (
        "understand1_08",
        r'''What does this JavaScript code do?

```javascript
function createObservable(target, onChange) {
  const handler = {
    get(obj, prop, receiver) {
      const value = Reflect.get(obj, prop, receiver);
      if (typeof value === 'object' && value !== null) {
        return createObservable(value, onChange);
      }
      return value;
    },
    set(obj, prop, value, receiver) {
      const oldValue = Reflect.get(obj, prop, receiver);
      const result = Reflect.set(obj, prop, value, receiver);
      if (oldValue !== value) {
        onChange(prop, oldValue, value);
      }
      return result;
    },
    deleteProperty(obj, prop) {
      const oldValue = obj[prop];
      const result = Reflect.deleteProperty(obj, prop);
      if (result) {
        onChange(prop, oldValue, undefined);
      }
      return result;
    }
  };
  return new Proxy(target, handler);
}
```''',
        r'''<think>
This creates a deeply reactive observable object using Proxy. The key insight is the recursive wrapping in the `get` trap — when you access a nested object property, it returns a new Proxy around that nested object, making the entire tree observable. The `set` trap fires the onChange callback only when the value actually changes. The `deleteProperty` trap handles property deletion. I should explain how Proxy/Reflect work together.
</think>

## Deep Observable Object via Proxy

This function creates a **reactive wrapper** around any JavaScript object that calls `onChange` whenever a property is modified or deleted — including nested properties at any depth.

### The Proxy/Reflect Mechanism

`Proxy` creates a transparent wrapper that intercepts operations on an object (get, set, delete, etc.). `Reflect` provides the default behavior for those operations, so the handler can do extra work and then fall through to normal behavior.

### The Three Traps

**`get` trap** — intercepts property access (`obj.foo`):
```javascript
const value = Reflect.get(obj, prop, receiver);
if (typeof value === 'object' && value !== null) {
    return createObservable(value, onChange);  // recursive wrapping
}
return value;
```
This is the key to **deep observation**. When you access `state.user.name`, the `get` trap fires for `user`, sees it's an object, and returns a new Proxy wrapping `user`. Then accessing `.name` on that proxy also goes through a trap. This means nested mutations like `state.user.name = "Alice"` trigger `onChange` even though only the top-level object was explicitly wrapped.

**`set` trap** — intercepts property assignment (`obj.foo = "bar"`):
- Reads the old value first
- Performs the actual set via `Reflect.set`
- Compares old vs new — only fires `onChange` if the value actually changed
- Returns `result` (must return `true` for the assignment to succeed in strict mode)

**`deleteProperty` trap** — intercepts `delete obj.foo`:
- Captures the old value, performs the deletion
- Only fires `onChange` if the deletion succeeded (property existed)

### Important Characteristics

- **Lazy wrapping**: Nested objects aren't wrapped until accessed. The Proxy is created on-the-fly in the `get` trap, so there's no upfront traversal cost.
- **No caching**: Every property access on a nested object creates a **new Proxy**. This means `state.user === state.user` is `false` (different Proxy instances). This can break identity checks and cause issues with `Map`/`Set`.
- **Shallow comparison**: `oldValue !== value` uses strict equality. Setting an object to a different but deeply-equal object will trigger `onChange`.

This pattern is the foundation of reactivity systems in frameworks like Vue 3, which uses Proxy-based observation for its reactive state management.'''
    ),

    # ===================== COMPARE X VS Y (7 pairs) =====================

    # Python: threading vs multiprocessing vs asyncio (thinking)
    (
        "understand1_09",
        r'''When should I use threading vs multiprocessing vs asyncio in Python? I'm confused about when to pick each one.''',
        r'''<think>
This is about the three main concurrency models in Python. The core issue is the GIL — threading can't truly parallelize CPU work because of the GIL, but it's fine for I/O-bound tasks. Multiprocessing bypasses the GIL by using separate processes. Asyncio is single-threaded cooperative concurrency for I/O-heavy workloads. I need to make the decision criteria clear.
</think>

## Threading vs Multiprocessing vs Asyncio

The choice depends on **what your program spends time waiting for**.

### `threading` — Concurrent I/O with Shared Memory

**Use when:** You have I/O-bound work (network requests, file reads, database queries) and need to share data between tasks easily.

**How it works:** Multiple threads run in the same process, sharing memory. The **GIL (Global Interpreter Lock)** means only one thread executes Python bytecode at a time, but the GIL is released during I/O operations. So while one thread waits for a network response, another can run.

**Good for:** Scraping 50 URLs concurrently, reading multiple files, simple producer/consumer queues.

**Drawbacks:** GIL prevents CPU parallelism. Race conditions on shared data require locks. Threads have ~8MB stack overhead each, so thousands of threads is impractical.

### `multiprocessing` — True CPU Parallelism

**Use when:** You have CPU-bound work (number crunching, image processing, data transformation) that needs to use multiple cores.

**How it works:** Spawns separate OS processes, each with its own Python interpreter and GIL. Data is passed between processes via serialization (pickle), shared memory, or `multiprocessing.Queue`.

**Good for:** Parallel data processing, ML training preprocessing, batch image resizing, anything that maxes out a CPU core.

**Drawbacks:** Process creation is expensive (~100ms). Data sharing requires serialization (slow for large objects). Debugging is harder across process boundaries. Memory usage multiplies (each process has its own copy of imported modules).

### `asyncio` — High-Concurrency I/O in a Single Thread

**Use when:** You have **thousands** of concurrent I/O operations and need efficiency.

**How it works:** A single thread runs an event loop. Tasks cooperatively yield control at `await` points. No thread switching overhead, no locks needed (single-threaded), and coroutines are extremely lightweight (~1KB each vs ~8MB for threads).

**Good for:** Web servers handling thousands of connections, API gateways, chat servers, WebSocket applications, anything with massive I/O concurrency.

**Drawbacks:** ALL I/O libraries must be async-compatible (can't use `requests`, must use `aiohttp`). A single CPU-bound task blocks the entire event loop. Debugging async stack traces is harder. Ecosystem fragmentation (sync vs async versions of everything).

### Decision Flowchart

1. **Is the work CPU-bound?** → `multiprocessing`
2. **Do you need 100+ concurrent I/O tasks?** → `asyncio`
3. **Do you need 5-50 concurrent I/O tasks with simple shared state?** → `threading`
4. **Mixing CPU and I/O?** → `asyncio` event loop + `ProcessPoolExecutor` for CPU work via `loop.run_in_executor()`'''
    ),

    # Rust: Box<dyn Trait> vs impl Trait vs generics (direct)
    (
        "understand1_10",
        r'''In Rust, what's the difference between `Box<dyn Trait>`, `impl Trait`, and `<T: Trait>`? When do I use each?''',
        r'''## Three Ways to Use Traits in Rust

### `<T: Trait>` — Generic Type Parameter

```rust
fn serialize<T: Serialize>(value: &T) -> String { ... }
```

**What happens:** The compiler generates a separate copy of `serialize` for each concrete type used (monomorphization). At runtime, there's a direct function call — no indirection.

**Use when:** You want maximum performance, need the concrete type information inside the function, or want the caller to specify the exact type. The compiler can inline, auto-vectorize, and optimize aggressively.

**Limitation:** The caller must know the type at compile time. You can't store different types implementing the same trait in a `Vec<T>` — all elements must be the same `T`.

### `impl Trait` — Opaque Type (Two Positions)

**In argument position** — sugar for generics:
```rust
fn serialize(value: &impl Serialize) -> String { ... }
// Exactly equivalent to: fn serialize<T: Serialize>(value: &T) -> String
```

**In return position** — the function chooses the concrete type:
```rust
fn make_iter() -> impl Iterator<Item = u32> {
    (0..10).filter(|x| x % 2 == 0)
}
```
The caller knows it gets "some type implementing Iterator" but cannot name the concrete type. This is essential for returning closures and complex iterator chains that have unnameable types.

**Use when:** You want generic arguments with cleaner syntax (argument position), or you need to return a concrete-but-unnameable type like a closure (return position).

**Limitation:** In return position, you can only return **one** concrete type. You can't conditionally return different types based on runtime logic.

### `Box<dyn Trait>` — Dynamic Dispatch (Trait Object)

```rust
fn process(items: Vec<Box<dyn Processor>>) { ... }
```

**What happens:** `Box<dyn Processor>` is a fat pointer — 2 words: one pointing to the heap-allocated data, one pointing to a vtable. Method calls go through the vtable at runtime (virtual dispatch).

**Use when:** You need a **heterogeneous** collection (different types in one `Vec`), runtime polymorphism (choose the type based on config/input), or you want to reduce binary size by avoiding monomorphization.

**Limitation:** Heap allocation required. Vtable lookup on every method call. The trait must be **object-safe** (no `Self` in return types, no generic methods).

### Quick Reference

| Feature | `<T: Trait>` | `impl Trait` | `Box<dyn Trait>` |
|---|---|---|---|
| Dispatch | Static | Static | Dynamic |
| Mixed types in collection | No | No | Yes |
| Performance | Best | Best | Vtable overhead |
| Binary size | Larger (copies) | Larger (copies) | Smaller |
| Object safety required | No | No | Yes |'''
    ),

    # Go: sync.Mutex vs sync.RWMutex vs channels (thinking)
    (
        "understand1_11",
        r'''In Go, when should I use sync.Mutex vs sync.RWMutex vs channels for managing shared state?''',
        r'''<think>
This is about choosing the right synchronization primitive in Go. The tradeoffs are: Mutex is simplest but serializes all access, RWMutex allows concurrent reads but adds complexity, and channels are "share memory by communicating" — Go's preferred idiom for coordinating goroutines. The right choice depends on the access pattern (read-heavy vs write-heavy) and whether the state management is a coordination problem.
</think>

## Mutex vs RWMutex vs Channels in Go

### `sync.Mutex` — Simple Exclusive Access

```go
var mu sync.Mutex
var balance int

func withdraw(amount int) {
    mu.Lock()
    defer mu.Unlock()
    balance -= amount
}
```

**Behavior:** Only one goroutine can hold the lock at a time. All others block, whether they want to read or write.

**Use when:** The critical section is short, writes are frequent relative to reads, or you're protecting a simple value. Mutex is the default choice — start here and only switch if profiling shows contention.

**Strength:** Simplicity. Two methods: `Lock()` and `Unlock()`. Hard to misuse.

### `sync.RWMutex` — Concurrent Reads, Exclusive Writes

```go
var rw sync.RWMutex
var cache map[string]Data

func get(key string) Data {
    rw.RLock()
    defer rw.RUnlock()
    return cache[key]
}

func set(key string, val Data) {
    rw.Lock()
    defer rw.Unlock()
    cache[key] = val
}
```

**Behavior:** Multiple goroutines can hold `RLock` simultaneously (concurrent reads). But `Lock` (write) is exclusive — it waits for all readers to finish and blocks new readers.

**Use when:** Reads vastly outnumber writes (90%+ reads). Typical examples: configuration caches, lookup tables, metrics registries.

**Caveat:** `RWMutex` has higher overhead per lock operation than `Mutex`. If your read/write ratio is close to 50/50, a plain `Mutex` is actually faster due to less bookkeeping.

### Channels — Coordination, Not Just Locking

```go
type command struct {
    action string
    key    string
    value  Data
    result chan Data
}

func stateManager(ch <-chan command) {
    store := make(map[string]Data)
    for cmd := range ch {
        switch cmd.action {
        case "get":
            cmd.result <- store[cmd.key]
        case "set":
            store[cmd.key] = cmd.value
        }
    }
}
```

**Behavior:** A single goroutine owns the state. Other goroutines send commands via a channel. No locks — there's no shared memory, so there are no races.

**Use when:** State management involves complex logic (not just get/set), you need to coordinate sequences of operations, or the state owner should also perform background work (expiration, persistence). Also useful when the state transitions form a natural pipeline.

### Decision Guide

- **Simple shared counter/flag** → `sync.Mutex`
- **Read-heavy cache with rare updates** → `sync.RWMutex`
- **Complex state machine or coordination** → Channel with owner goroutine
- **Pipeline of data transformations** → Channels (this is what they're designed for)

Go's proverb is "Don't communicate by sharing memory; share memory by communicating." But this is guidance, not dogma. Mutexes are perfectly idiomatic when they're the simpler solution.'''
    ),

    # JS: Promise.all vs Promise.allSettled vs Promise.race (direct)
    (
        "understand1_12",
        r'''What's the difference between Promise.all, Promise.allSettled, and Promise.race in JavaScript? When do I use each?''',
        r'''## Promise Combinators: `all` vs `allSettled` vs `race`

### `Promise.all` — All Must Succeed

```javascript
const [users, posts, comments] = await Promise.all([
  fetchUsers(),
  fetchPosts(),
  fetchComments()
]);
```

**Behavior:** Waits for **all** promises to resolve. If **any** promise rejects, the entire `Promise.all` rejects immediately with that error. The other promises keep running (there's no cancellation), but their results are discarded.

**Use when:** You need all results and a failure in any one makes the combined result useless. Classic example: loading all data needed to render a page — if any fetch fails, you can't render.

**Gotcha:** One failing promise means you lose the results of all the others, even those that succeeded. If you need partial results, use `allSettled`.

### `Promise.allSettled` — Wait for Everything, Never Rejects

```javascript
const results = await Promise.allSettled([
  fetchPrimary(),
  fetchFallback(),
  fetchOptional()
]);

results.forEach(r => {
  if (r.status === 'fulfilled') console.log(r.value);
  if (r.status === 'rejected') console.log(r.reason);
});
```

**Behavior:** Waits for **all** promises to settle (resolve or reject). Never rejects. Returns an array of `{ status, value }` or `{ status, reason }` objects.

**Use when:** You want to attempt multiple operations and handle each result independently. Examples: sending notifications to multiple services (some may fail), batch API calls where partial success is acceptable, health checks across multiple endpoints.

### `Promise.race` — First to Settle Wins

```javascript
const result = await Promise.race([
  fetchFromCDN(url),
  fetchFromOrigin(url)
]);
```

**Behavior:** Resolves or rejects as soon as the **first** promise settles (whether it succeeds or fails). The other promises keep running but their results are ignored.

**Use when:** You want the fastest response from redundant sources, or you need a timeout:

```javascript
await Promise.race([
  fetchData(),
  new Promise((_, reject) =>
    setTimeout(() => reject(new Error('Timeout')), 5000)
  )
]);
```

**Related: `Promise.any`** — Like `race` but ignores rejections. It resolves with the first **successful** result. Only rejects if ALL promises reject (`AggregateError`). Use for: "try multiple mirrors, use whichever responds first successfully."

### Summary Table

| Combinator | Resolves when | Rejects when | Use case |
|---|---|---|---|
| `all` | All succeed | Any one fails | Need all results |
| `allSettled` | All settle | Never | Handle partial failures |
| `race` | First settles | First settles (if rejection) | Fastest response / timeout |
| `any` | First succeeds | All fail | Redundant sources |'''
    ),

    # General: SQL vs NoSQL (thinking)
    (
        "understand1_13",
        r'''I'm building a social media app. Should I use SQL (PostgreSQL) or NoSQL (MongoDB)? The app has user profiles, posts, comments, likes, and a follow system.''',
        r'''<think>
This is a classic "it depends" question but with a concrete use case. Social media has highly relational data (follows are a many-to-many relationship, comments reference posts and users, likes reference users and posts). This actually favors SQL. But there are valid NoSQL arguments for specific parts (like activity feeds). I should give a nuanced answer, not just "use SQL."
</think>

## SQL vs NoSQL for a Social Media App

For your specific feature set — profiles, posts, comments, likes, follows — **PostgreSQL is the stronger choice** as the primary database. Here's why, and where NoSQL might complement it.

### Why SQL Fits This Data Model

Your data is **deeply relational**:
- A comment belongs to a post AND a user
- A like connects a user to a post (many-to-many)
- Follows connect users to users (self-referential many-to-many)
- You'll need queries like "show posts from people I follow, ordered by time, with like counts and whether I've liked each one"

That query involves joining `follows`, `posts`, `likes`, and `users`. In SQL:

```sql
SELECT p.*, u.username, COUNT(l.id) AS likes,
       EXISTS(SELECT 1 FROM likes WHERE post_id = p.id AND user_id = $1) AS liked
FROM posts p
JOIN users u ON p.author_id = u.id
JOIN follows f ON f.following_id = p.author_id AND f.follower_id = $1
LEFT JOIN likes l ON l.post_id = p.id
GROUP BY p.id, u.username
ORDER BY p.created_at DESC LIMIT 20;
```

In MongoDB, this requires multiple queries or denormalization (embedding like counts in post documents, duplicating usernames everywhere), leading to consistency headaches when a user changes their username.

### Where MongoDB Struggles with This Model

- **Follows**: A many-to-many relationship. MongoDB has no joins — you'd either embed follower arrays (hits 16MB document limit for popular users) or use a separate collection (then you're simulating foreign keys without database enforcement).
- **"Unlike" or "Unfollow"**: Requires finding and removing an element from a nested array. SQL: `DELETE FROM likes WHERE ...` — one indexed operation.
- **Data integrity**: SQL enforces that a like references a real post and real user via foreign keys. MongoDB puts that burden on your application code.

### Where NoSQL Shines (as a Complement)

- **Activity feeds**: Pre-computed fan-out feeds stored in Redis or MongoDB for fast reads
- **User sessions / caching**: Key-value stores (Redis) for session data
- **Media metadata**: If posts have flexible, schema-less metadata (polls, locations, embedded content), a JSONB column in PostgreSQL handles this well — or a document store if the variety is extreme
- **Analytics / event logs**: Append-heavy, write-optimized stores (Cassandra, ClickHouse)

### Recommendation

Use **PostgreSQL as your primary database** for all core data. It handles your relational queries efficiently, enforces data integrity, supports JSONB for flexible fields, and scales well to millions of users with proper indexing. Introduce a caching layer (Redis) for feeds and sessions. Only add a document store if you hit a specific limitation that PostgreSQL can't handle — and in practice, for most social apps under 10M users, PostgreSQL alone is sufficient.'''
    ),

    # General: Monorepo vs polyrepo (direct)
    (
        "understand1_14",
        r'''What are the tradeoffs between monorepo and polyrepo? My team of 8 is building a web app with a React frontend, Node.js API, Python ML service, and shared protobuf schemas.''',
        r'''## Monorepo vs Polyrepo for Your Stack

### Monorepo — One Repository, All Services

**Advantages for your case:**
- **Shared protobuf schemas** are the strongest argument for monorepo. When you change a `.proto` file, you update the generated code for the Node.js API and Python ML service in the **same commit**. No version mismatch, no "which version of the schema does service X use?" questions.
- **Atomic cross-service changes**: Changing an API endpoint and updating the React frontend that calls it happens in one PR. Reviewers see the full picture.
- **Code sharing**: Common utilities, types, and configs live in one place. No publishing internal packages to npm/PyPI.
- **Unified CI**: One pipeline runs all affected tests when a PR touches shared code.

**Disadvantages:**
- **Tooling complexity**: You need a build tool that understands the dependency graph (Nx, Turborepo, Bazel, or Pants) to avoid rebuilding everything on every commit.
- **Mixed languages are harder**: Most monorepo tools are optimized for one ecosystem. Managing npm, pip, and protoc in one build system takes effort.
- **CI gets slow** without dependency-aware task runners. A change to a README shouldn't trigger Python ML model tests.
- **Repository size**: Over time, git operations slow down. Shallow clones and sparse checkouts help but add complexity.

### Polyrepo — Separate Repository per Service

**Advantages:**
- **Independent deployment**: Each service has its own CI/CD pipeline, release cycle, and version. The ML team can deploy daily without waiting for frontend approval.
- **Clear ownership**: `ml-service` repo belongs to the ML team, `frontend` repo belongs to the frontend team. Permissions and code review are straightforward.
- **Tool freedom**: Each repo uses the build tools natural to its language. The Python repo uses pytest and pip; the JS repos use Jest and npm. No polyglot build system needed.
- **Simpler git history**: Each repo's log tells one service's story.

**Disadvantages for your case:**
- **Protobuf schema versioning** becomes a real problem. You'll need a `schemas` repo, publish generated code as packages, and ensure all services use compatible versions. Breaking schema changes require coordinated releases.
- **Cross-service changes** require multiple PRs across repos, merged in the right order. "Update the API and frontend" becomes a choreographed dance.
- **Dependency drift**: Services may use different versions of shared libraries, leading to subtle bugs.

### Recommendation for Team of 8

At 8 people, a **monorepo** is likely the better fit. The protobuf schema sharing alone makes it worthwhile. Your team is small enough that the "who owns what" clarity of polyrepos isn't critical — everyone probably touches multiple services anyway. Use **Turborepo** for the JS projects and a Makefile or Pants for the Python service. The complexity of monorepo tooling pays off when your alternative is coordinating schema changes across 4 repos.

Switch to polyrepo if: the team grows past 20-30, services need independent release cadences, or the ML service's large model files bloat the repo.'''
    ),

    # Python: @property vs __getattr__ vs descriptors (thinking)
    (
        "understand1_15",
        r'''What's the difference between @property, __getattr__, and descriptors in Python? They all seem to intercept attribute access.''',
        r'''<think>
These three mechanisms all intercept attribute access but at different levels and with different use cases. @property is a specific descriptor, __getattr__ is a fallback hook, and descriptors are the general protocol. I should clarify the lookup order and when each fires.
</think>

## Three Levels of Attribute Interception in Python

These mechanisms operate at different stages of Python's attribute lookup process.

### `@property` — Per-Attribute Computed Values

```python
class Circle:
    def __init__(self, radius):
        self._radius = radius

    @property
    def area(self):
        return 3.14159 * self._radius ** 2
```

**What it does:** Defines a method that looks like an attribute. `circle.area` calls the getter function transparently. You can also define `@area.setter` and `@area.deleter` for write and delete operations.

**When to use:** You want one specific attribute to be computed, validated on set, or lazily loaded. It's explicit — readers see `@property` and know the attribute has custom behavior.

**Limitation:** You must define it for each attribute individually. If you have 20 attributes that all need the same validation logic, 20 `@property` definitions creates a lot of boilerplate.

### `__getattr__` — Fallback for Missing Attributes

```python
class DotDict:
    def __init__(self, data):
        self._data = data

    def __getattr__(self, name):
        try:
            return self._data[name]
        except KeyError:
            raise AttributeError(name)
```

**What it does:** Called **only when normal attribute lookup fails** — after checking the instance `__dict__`, the class, and all base classes. It's a fallback, not an interceptor.

**When to use:** Proxy objects, dynamic attribute mapping, delegation patterns. `DotDict` above lets you write `config.database_url` instead of `config["database_url"]`.

**Important distinction:** `__getattr__` is NOT called for attributes that exist normally. If `self.x = 5`, then `obj.x` returns `5` directly without calling `__getattr__`. For intercepting ALL attribute access (including existing attributes), use `__getattribute__` — but that's dangerous and rarely needed.

### Descriptors — The General Protocol

```python
class Validated:
    def __init__(self, validator):
        self.validator = validator

    def __set_name__(self, owner, name):
        self.name = '_' + name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return getattr(obj, self.name, None)

    def __set__(self, obj, value):
        if not self.validator(value):
            raise ValueError(f"Invalid value: {value}")
        setattr(obj, self.name, value)

class User:
    age = Validated(lambda x: 0 <= x <= 150)
    email = Validated(lambda x: '@' in x)
```

**What it does:** A descriptor is any object with `__get__`, `__set__`, or `__delete__` methods that lives as a **class variable**. When you access the attribute, Python calls the descriptor's methods instead of returning the descriptor object itself.

**When to use:** You need the same attribute behavior across multiple attributes or multiple classes. ORMs use descriptors for column definitions. `@property` is itself implemented as a descriptor.

### Lookup Order

1. **Data descriptors** (have `__set__` or `__delete__`) — checked first, override instance `__dict__`
2. **Instance `__dict__`** — the object's own attributes
3. **Non-data descriptors** (only `__get__`) — checked after instance dict
4. **`__getattr__`** — called only if everything above fails

This is why `@property` (a data descriptor) can intercept even when an instance has the same attribute name in its `__dict__`.'''
    ),

    # ===================== WHAT'S WRONG WITH THIS CODE? (8 pairs) =====================

    # Python: race condition in threading (thinking)
    (
        "understand1_16",
        r'''What's wrong with this code?

```python
import threading

class BankAccount:
    def __init__(self, balance=0):
        self.balance = balance

    def deposit(self, amount):
        current = self.balance
        # simulate some processing
        self.balance = current + amount

    def withdraw(self, amount):
        current = self.balance
        if current >= amount:
            self.balance = current - amount
            return True
        return False

account = BankAccount(1000)

def transfer_out():
    for _ in range(10000):
        account.withdraw(1)

def transfer_in():
    for _ in range(10000):
        account.deposit(1)

t1 = threading.Thread(target=transfer_out)
t2 = threading.Thread(target=transfer_in)
t1.start()
t2.start()
t1.join()
t2.join()
print(account.balance)  # should be 1000, but isn't
```''',
        r'''<think>
Classic race condition — the read-modify-write on self.balance is not atomic. Thread 1 reads balance=100, thread 2 reads balance=100, thread 1 writes 99, thread 2 writes 101. The withdraw's decrement was lost. Even with the GIL, Python can switch threads between reading self.balance and writing the new value.
</think>

## Bug: Race Condition on `self.balance`

The `deposit` and `withdraw` methods have a **TOCTOU (Time-of-Check-to-Time-of-Use) race condition**. The read-modify-write of `self.balance` is not atomic — a thread switch can happen between reading the current value and writing the updated value.

### How It Breaks

Consider two threads running simultaneously:

```
Thread 1 (withdraw):          Thread 2 (deposit):
current = self.balance  # 1000
                                current = self.balance  # 1000
self.balance = 1000 - 1 # 999
                                self.balance = 1000 + 1 # 1001
```

Thread 2 read `balance` before Thread 1 wrote its update. Thread 2's deposit overwrites Thread 1's withdrawal. The withdrawal is **lost** — balance is 1001 instead of 1000.

Even though Python has the GIL (only one thread runs Python bytecode at a time), the GIL doesn't make multi-statement operations atomic. Python can switch threads between any two bytecode instructions, including between `current = self.balance` and `self.balance = current + amount`.

### The Fix: Use a Lock

```python
import threading

class BankAccount:
    def __init__(self, balance=0):
        self.balance = balance
        self._lock = threading.Lock()

    def deposit(self, amount):
        with self._lock:
            self.balance += amount

    def withdraw(self, amount):
        with self._lock:
            if self.balance >= amount:
                self.balance -= amount
                return True
            return False
```

The `threading.Lock` ensures that only one thread can execute the critical section at a time. `with self._lock` acquires the lock on entry and releases it on exit (even if an exception occurs).

### Why `self.balance += amount` Alone Isn't Enough

You might think `+=` is atomic, but it's not. CPython compiles `self.balance += amount` into multiple bytecodes: `LOAD_ATTR`, `LOAD_FAST`, `BINARY_ADD`, `STORE_ATTR`. A thread switch can happen between any of these. The lock is the only reliable solution.'''
    ),

    # Python: mutable default arg (direct)
    (
        "understand1_17",
        r'''What's the bug in this code? It's behaving strangely when I create multiple instances.

```python
class EventLog:
    def __init__(self, events=[]):
        self.events = events

    def add(self, event):
        self.events.append(event)
        return self

    def get_latest(self, n=5):
        return self.events[-n:]

log1 = EventLog()
log1.add("user_login")

log2 = EventLog()
print(log2.events)  # prints ['user_login'] — why?!
```''',
        r'''## Bug: Mutable Default Argument

The default value `events=[]` in `__init__` is created **once** when the class is defined, not each time `__init__` is called. Every instance that uses the default shares the **same list object**.

### What Happens Step by Step

1. Python defines `EventLog` — the default `[]` is created and stored on the function object
2. `log1 = EventLog()` — `events` parameter defaults to that shared list. `self.events` points to it
3. `log1.add("user_login")` — appends to the shared list. The shared list is now `["user_login"]`
4. `log2 = EventLog()` — `events` parameter defaults to the **same shared list**, which already contains `"user_login"`
5. `log2.events` is `["user_login"]` because `log2.events` IS `log1.events` — they're literally the same object

You can verify: `log1.events is log2.events` returns `True`.

### The Fix: Use `None` as Sentinel

```python
class EventLog:
    def __init__(self, events=None):
        self.events = events if events is not None else []

    def add(self, event):
        self.events.append(event)
        return self
```

Now each instance gets its own fresh list. The `None` default is immutable, so sharing it is harmless. The `[]` is created inside the method body, so each call creates a new list.

### The General Rule

**Never use mutable objects as default arguments** — this includes `[]`, `{}`, `set()`, and any custom mutable object. Always use `None` and create the mutable inside the function body.

This is one of Python's most well-known gotchas. Linters like `pylint` and `ruff` flag it (`B006` / `W0102`).'''
    ),

    # Rust: use-after-move (thinking)
    (
        "understand1_18",
        r'''Why doesn't this Rust code compile?

```rust
fn process_data(data: Vec<String>) {
    println!("Processing {} items", data.len());
}

fn main() {
    let items = vec!["hello".to_string(), "world".to_string()];

    process_data(items);

    println!("Done processing {} items", items.len());
}
```''',
        r'''<think>
This is a use-after-move error. `process_data` takes `Vec<String>` by value, so `items` is moved into the function. After the call, `items` is no longer valid — using it in the println is a compile error. I should explain ownership and the three common fixes.
</think>

## Error: Use After Move

The code won't compile because `items` is **moved** into `process_data`, and then `main` tries to use it afterward.

```
error[E0382]: borrow of moved value: `items`
  --> src/main.rs:8:46
   |
5  |     let items = vec!["hello".to_string(), "world".to_string()];
   |         ----- move occurs because `items` has type `Vec<String>`
6  |
7  |     process_data(items);
   |                  ----- value moved here
8  |
9  |     println!("Done processing {} items", items.len());
   |                                          ^^^^^ value borrowed here after move
```

### Why This Happens

In Rust, `Vec<String>` does not implement `Copy` (it's a heap-allocated type). When you pass it to a function by value, **ownership transfers** — `items` is moved into the `data` parameter. After the move, `items` is invalid in `main`. This is Rust's ownership system preventing use-after-free bugs.

### Three Fixes

**1. Borrow instead of move** (usually the best choice):
```rust
fn process_data(data: &[String]) {  // borrow a slice
    println!("Processing {} items", data.len());
}

fn main() {
    let items = vec!["hello".to_string(), "world".to_string()];
    process_data(&items);  // lend, don't give
    println!("Done processing {} items", items.len());  // still valid
}
```

**2. Clone before passing** (if the function must own the data):
```rust
process_data(items.clone());  // pass a copy, keep the original
println!("Done processing {} items", items.len());
```

**3. Return the value back** (awkward but sometimes necessary):
```rust
fn process_data(data: Vec<String>) -> Vec<String> {
    println!("Processing {} items", data.len());
    data  // return ownership back
}

let items = process_data(items);  // rebind
```

### The Right Choice

Option 1 (borrowing) is almost always correct. If `process_data` only needs to read the data, it should take `&[String]` (a slice reference), not `Vec<String>`. Taking ownership is only appropriate when the function needs to consume, store, or modify the data permanently.'''
    ),

    # Rust: lifetime issue returning reference to local (direct)
    (
        "understand1_19",
        r'''What's wrong with this Rust function?

```rust
fn longest_line(text: &str) -> &str {
    let lines: Vec<&str> = text.lines().collect();
    let mut longest = "";

    for line in &lines {
        if line.len() > longest.len() {
            longest = line;
        }
    }

    longest
}
```

Wait actually I think this compiles fine. But what about this version?

```rust
fn longest_line(text: &str) -> &str {
    let processed: String = text.to_uppercase();
    let lines: Vec<&str> = processed.lines().collect();
    let mut longest = "";

    for line in &lines {
        if line.len() > longest.len() {
            longest = line;
        }
    }

    longest
}
```''',
        r'''## First Version: Compiles Fine

You're right — the first version works. `text.lines()` returns slices that borrow from `text` (the input parameter). So `longest` is a `&str` borrowing from `text`, and the return type `&str` has the same lifetime as the input. The `Vec<&str>` is a local that gets dropped, but the slices it held point into the original `text`, which outlives the function.

## Second Version: Dangling Reference

```
error[E0515]: cannot return value referencing local variable `processed`
```

The problem is that `processed` is a **new `String`** created inside the function. When you call `processed.lines()`, the slices borrow from `processed`. But `processed` is dropped at the end of the function. Returning `longest` would create a dangling reference — a pointer to freed memory.

### The Lifetime Chain

```
text (lives outside function)
  → processed = text.to_uppercase()  // NEW String, owned locally
    → lines = processed.lines()      // borrows from processed
      → longest = lines[...]         // borrows from processed
        → return longest             // ERROR: processed dies here
```

The return type `&str` is implicitly `&'a str` where `'a` is the lifetime of the input `text`. But `longest` doesn't borrow from `text` — it borrows from `processed`, which has a shorter lifetime. The compiler catches this mismatch.

### Fixes

**Return an owned `String`:**
```rust
fn longest_line(text: &str) -> String {
    let processed = text.to_uppercase();
    processed.lines()
        .max_by_key(|line| line.len())
        .unwrap_or("")
        .to_string()
}
```

**Or avoid creating a local `String`** if the transformation isn't needed:
```rust
fn longest_line(text: &str) -> &str {
    text.lines()
        .max_by_key(|line| line.len())
        .unwrap_or("")
}
```

The rule: you can only return a reference if it points to data that **outlives the function** — meaning either the input parameters or `'static` data.'''
    ),

    # Go: goroutine leak with unbuffered channel (thinking)
    (
        "understand1_20",
        r'''What's wrong with this Go code?

```go
func fetchFirst(ctx context.Context, urls []string) (string, error) {
    ch := make(chan string)
    errCh := make(chan error)

    for _, url := range urls {
        go func(u string) {
            resp, err := http.Get(u)
            if err != nil {
                errCh <- err
                return
            }
            defer resp.Body.Close()
            body, _ := io.ReadAll(resp.Body)
            ch <- string(body)
        }(url)
    }

    select {
    case result := <-ch:
        return result, nil
    case err := <-errCh:
        return "", err
    case <-ctx.Done():
        return "", ctx.Err()
    }
}
```''',
        r'''<think>
This has a goroutine leak. The function launches N goroutines but only reads ONE result from the channels (via select). The remaining N-1 goroutines will block forever trying to send on the unbuffered channels — no one is reading from them anymore. Also, the http.Get calls don't use the context, so they won't be cancelled either.
</think>

## Bug: Goroutine Leak

This function spawns a goroutine for each URL but only consumes **one** result via the `select` statement. The remaining goroutines will **block forever** trying to send on the unbuffered channels `ch` and `errCh`.

### Why They Leak

Channels are unbuffered (`make(chan string)` with no capacity). A send on an unbuffered channel blocks until a receiver is ready. After `fetchFirst` returns, no goroutine is reading from `ch` or `errCh`. The remaining goroutines are stuck at `ch <- string(body)` or `errCh <- err` permanently — they'll never be garbage collected because they hold references to the channels.

If you call `fetchFirst` with 10 URLs, 9 goroutines leak every call. Over time, this exhausts memory and file descriptors.

### Secondary Issue: No Context on HTTP Requests

`http.Get(u)` ignores the context. Even if `ctx` is cancelled, the HTTP requests continue running. Only the parent function returns — the goroutines keep downloading.

### Fixed Version

```go
func fetchFirst(ctx context.Context, urls []string) (string, error) {
    // Buffered channels: goroutines can send without blocking
    ch := make(chan string, len(urls))
    errCh := make(chan error, len(urls))

    ctx, cancel := context.WithCancel(ctx)
    defer cancel() // cancel remaining requests when we have a result

    for _, url := range urls {
        go func(u string) {
            // Use context-aware request
            req, err := http.NewRequestWithContext(ctx, "GET", u, nil)
            if err != nil {
                errCh <- err
                return
            }
            resp, err := http.DefaultClient.Do(req)
            if err != nil {
                errCh <- err
                return
            }
            defer resp.Body.Close()
            body, _ := io.ReadAll(resp.Body)
            ch <- string(body)
        }(url)
    }

    select {
    case result := <-ch:
        return result, nil
    case err := <-errCh:
        return "", err
    case <-ctx.Done():
        return "", ctx.Err()
    }
}
```

**Key fixes:**
1. **Buffered channels** with capacity `len(urls)` — goroutines can send even after `fetchFirst` returns, then exit normally. The channel and its data are garbage collected when all references are gone.
2. **`context.WithCancel`** + `defer cancel()` — when we get a result, cancel the context to abort remaining HTTP requests.
3. **`http.NewRequestWithContext`** — passes the context to the HTTP client so requests respect cancellation.'''
    ),

    # Go: range variable capture in closure (direct)
    (
        "understand1_21",
        r'''Find the bug in this Go code:

```go
func startWorkers(tasks []Task) []*Worker {
    workers := make([]*Worker, len(tasks))

    for i, task := range tasks {
        workers[i] = &Worker{
            ID: i,
            Run: func() error {
                fmt.Printf("Worker %d processing task: %s\n", i, task.Name)
                return task.Execute()
            },
        }
    }

    return workers
}
```''',
        r'''## Bug: Loop Variable Capture in Closure

All closures capture the **same** `i` and `task` variables. When the `Run` functions execute later, they all see the **final values** from the last loop iteration.

### What Happens

In Go versions before 1.22, the `for i, task := range tasks` loop reuses the same `i` and `task` variables on each iteration — they're declared once and updated. The closure captures **references** to these variables, not their current values.

So if `tasks` has 3 elements, every worker's `Run` function will use `i = 2` and `task = tasks[2]`. Worker 0 and Worker 1 will both think they're Worker 2 processing the last task.

### Fix for Go < 1.22: Shadow the Variables

```go
for i, task := range tasks {
    i, task := i, task  // create new variables scoped to this iteration
    workers[i] = &Worker{
        ID: i,
        Run: func() error {
            fmt.Printf("Worker %d processing task: %s\n", i, task.Name)
            return task.Execute()
        },
    }
}
```

The line `i, task := i, task` declares **new** variables that shadow the loop variables. Each closure captures its own copy.

### Go 1.22+ Fixed This

Starting with Go 1.22, loop variables are **per-iteration** by default. Each iteration of `for i, task := range tasks` creates new `i` and `task` variables. The code in the question works correctly in Go 1.22+.

However, this is still a critical bug to recognize because: (a) many codebases still target Go < 1.22, (b) the `GOEXPERIMENT=loopvar` flag must be set in 1.21, and (c) this pattern is one of the most common Go bugs in production code.

### Note

The `ID: i` field assignment works correctly even in old Go — it copies the integer value at assignment time. Only the closure is affected because it captures a reference to the variable for deferred evaluation.'''
    ),

    # JS: async forEach not awaiting (thinking)
    (
        "understand1_22",
        r'''Why doesn't this JavaScript code work as expected?

```javascript
async function processOrders(orderIds) {
    const results = [];

    orderIds.forEach(async (id) => {
        const order = await fetchOrder(id);
        const validated = await validateOrder(order);
        results.push(validated);
    });

    console.log(`Processed ${results.length} orders`);
    return results;
}
```''',
        r'''<think>
The issue is that `forEach` doesn't await async callbacks. Each iteration starts an async function that returns a Promise, but `forEach` ignores the return value. So all the async callbacks are launched but the code continues immediately to console.log — `results` is still empty at that point.
</think>

## Bug: `forEach` Doesn't Await Async Callbacks

`Array.forEach` ignores the return value of its callback. When the callback is `async`, it returns a `Promise`, but `forEach` discards it. All iterations **fire concurrently** and the code falls through to `console.log` immediately — before any of the `fetchOrder`/`validateOrder` calls have completed.

### What Actually Happens

1. `forEach` calls the async callback for each ID — each call starts running and immediately returns a Promise
2. `forEach` doesn't wait for those Promises. It loops through all IDs and returns `undefined`
3. Code reaches `console.log` — `results` is empty because none of the awaits have resolved yet
4. The function returns an empty `results` array
5. Sometime later, all the fetch/validate calls complete and push to `results` — but no one is listening anymore

### Fix 1: `for...of` — Sequential Processing

```javascript
async function processOrders(orderIds) {
    const results = [];

    for (const id of orderIds) {
        const order = await fetchOrder(id);
        const validated = await validateOrder(order);
        results.push(validated);
    }

    console.log(`Processed ${results.length} orders`);
    return results;
}
```

Processes one order at a time. Use this when order matters or the API has rate limits.

### Fix 2: `Promise.all` + `map` — Concurrent Processing

```javascript
async function processOrders(orderIds) {
    const results = await Promise.all(
        orderIds.map(async (id) => {
            const order = await fetchOrder(id);
            return validateOrder(order);
        })
    );

    console.log(`Processed ${results.length} orders`);
    return results;
}
```

All orders process concurrently. Faster, but all promises must succeed (or use `Promise.allSettled` for partial failure handling).

### The Rule

Never use `forEach` with `async` callbacks. Use `for...of` for sequential execution or `Promise.all(array.map(...))` for concurrent execution. This also applies to `.map` without `Promise.all` — the promises start but aren't awaited.'''
    ),

    # C++: dangling reference from string_view (thinking)
    (
        "understand1_23",
        r'''What's wrong with this C++ code?

```cpp
#include <string>
#include <string_view>
#include <iostream>

std::string_view get_extension(const std::string& filename) {
    auto pos = filename.rfind('.');
    if (pos == std::string::npos) return "";
    return std::string_view(filename).substr(pos);
}

void process_file(const std::string& path) {
    auto ext = get_extension(path);
    std::cout << "Extension: " << ext << std::endl;
}

std::string_view get_greeting() {
    std::string msg = "Hello, World!";
    return std::string_view(msg);
}

int main() {
    // Case 1: This works fine
    process_file("document.pdf");

    // Case 2: This is undefined behavior
    auto greeting = get_greeting();
    std::cout << greeting << std::endl;
}
```''',
        r'''<think>
There are two scenarios here. `get_extension` is fine because the string_view points to the caller's string which outlives the view. But `get_greeting` creates a local `std::string`, creates a `string_view` pointing into it, then returns the view. When the function returns, `msg` is destroyed, and the `string_view` becomes a dangling pointer. Classic dangling reference via string_view.
</think>

## Bug: Dangling `string_view` in `get_greeting`

### Case 1 (`get_extension`): Safe

`get_extension` takes a `const std::string&` and returns a `string_view` pointing into **the caller's string**. The caller's `path` variable outlives the returned `string_view`, so this is valid. The `string_view` is a non-owning view into memory that persists.

### Case 2 (`get_greeting`): Undefined Behavior

```cpp
std::string_view get_greeting() {
    std::string msg = "Hello, World!";      // local string on stack
    return std::string_view(msg);           // view points into msg's buffer
}   // msg destroyed here — view now points to freed memory
```

`msg` is a **local variable**. When `get_greeting` returns, `msg`'s destructor runs, freeing its character buffer. The returned `string_view` holds a pointer to that freed memory — it's a **dangling pointer**. Reading `greeting` in `main` is undefined behavior: it might print garbage, crash, or appear to work correctly (the memory hasn't been overwritten yet), making this bug intermittent and hard to reproduce.

### Why `string_view` Is Dangerous Here

`string_view` is explicitly **non-owning**. It's just a `{pointer, length}` pair — it doesn't extend the lifetime of what it points to. This is unlike `std::string`, which owns and manages its buffer. The `string_view` doesn't know or care that the underlying memory has been freed.

### The Fix

**Return `std::string` when the data is locally owned:**
```cpp
std::string get_greeting() {
    return "Hello, World!";  // RVO — no copy
}
```

**Or use a string literal (static storage duration):**
```cpp
std::string_view get_greeting() {
    return "Hello, World!";  // string literal lives for entire program
}
```

String literals have static storage duration — they exist in the program's read-only data segment for the entire execution. A `string_view` pointing to a literal is always safe.

### The Rule

Never return a `string_view` (or `span`, or any non-owning view) that points to a local variable. `string_view` should only reference data that outlives the view: function parameters, member variables, globals, or string literals.'''
    ),

    # ===================== REVIEW THIS FUNCTION (7 pairs) =====================

    # Python: SRP violation (thinking)
    (
        "understand1_24",
        r'''Can you review this function? It works but feels wrong.

```python
def process_user_registration(form_data: dict, db_session, mailer, logger):
    # Validate
    errors = []
    if not form_data.get('email') or '@' not in form_data['email']:
        errors.append('Invalid email')
    if not form_data.get('password') or len(form_data['password']) < 8:
        errors.append('Password too short')
    if not form_data.get('username') or len(form_data['username']) < 3:
        errors.append('Username too short')
    if db_session.query(User).filter_by(email=form_data['email']).first():
        errors.append('Email already registered')
    if errors:
        return {'success': False, 'errors': errors}

    # Create user
    hashed = bcrypt.hashpw(form_data['password'].encode(), bcrypt.gensalt())
    user = User(
        username=form_data['username'],
        email=form_data['email'],
        password_hash=hashed.decode(),
        created_at=datetime.utcnow()
    )
    db_session.add(user)
    db_session.commit()

    # Send welcome email
    template = load_template('welcome_email.html')
    html = template.render(username=user.username)
    mailer.send(to=user.email, subject='Welcome!', html=html)

    # Log
    logger.info(f'New user registered: {user.email}')

    # Create default settings
    settings = UserSettings(user_id=user.id, theme='light', notifications=True)
    db_session.add(settings)
    db_session.commit()

    return {'success': True, 'user_id': user.id}
```''',
        r'''<think>
This is a classic SRP (Single Responsibility Principle) violation. The function does validation, password hashing, database insertion, email sending, logging, and settings creation. Each of these is a different concern. I should also note the two separate commits (partial failure risk), the lack of transaction handling, and that the email sending could fail after the user is committed.
</think>

## Code Review: `process_user_registration`

### Primary Issue: Single Responsibility Violation

This function handles **six different concerns**: input validation, password hashing, user persistence, email sending, logging, and default settings creation. This makes it difficult to test, modify, or reuse any single piece.

For example, you can't validate a registration form without a database session, a mailer, and a logger. You can't test email sending without creating a real user.

### Suggested Decomposition

```python
def validate_registration(form_data: dict, db_session) -> list[str]:
    """Pure validation — returns list of errors."""

def create_user(form_data: dict, db_session) -> User:
    """Hash password, create user, return instance."""

def send_welcome_email(user: User, mailer):
    """Render template and send."""

def create_default_settings(user: User, db_session):
    """Initialize user preferences."""
```

Each function is independently testable. The orchestrator becomes a thin coordinator.

### Bug: Two Separate Commits = Partial Failure

```python
db_session.commit()      # user is committed
# ... email sending ...
db_session.commit()      # settings are committed
```

If the email fails (or anything between the two commits), you have a user without settings. Use a **single transaction**:

```python
db_session.add(user)
db_session.flush()  # get user.id without committing
settings = UserSettings(user_id=user.id, ...)
db_session.add(settings)
db_session.commit()  # atomic: both or neither
```

### Bug: Email Failure Leaves Committed User

If `mailer.send()` raises an exception after `db_session.commit()`, the user exists in the database but never received a welcome email. Either:
- Send the email asynchronously (via a task queue like Celery) so failures can be retried
- Or catch the email error and log it, don't let it crash registration

### Minor Issues

- **`datetime.utcnow()`** is deprecated in Python 3.12+. Use `datetime.now(timezone.utc)`.
- **No password strength check** beyond length — consider checking against common passwords.
- **The `logger` parameter** is unusual. Most Python code uses `logger = logging.getLogger(__name__)` at module level rather than injecting it.
- **Email validation** with `'@' in email` is too weak — `"@@"` passes. Use a library or at minimum check for exactly one `@` with content on both sides.'''
    ),

    # Python: bare except (direct)
    (
        "understand1_25",
        r'''Review this error handling code:

```python
def fetch_user_data(user_id: int) -> dict:
    try:
        response = requests.get(f"{API_BASE}/users/{user_id}", timeout=10)
        data = response.json()
        user = {
            'name': data['name'],
            'email': data['email'],
            'role': data.get('role', 'user'),
        }
        cache.set(f'user:{user_id}', user, ttl=300)
        return user
    except:
        logger.error("Failed to fetch user")
        return None
```''',
        r'''## Code Review: Error Handling Anti-Patterns

### Critical: Bare `except` Catches Everything

`except:` without specifying an exception type catches **all exceptions**, including:
- `KeyboardInterrupt` (user pressing Ctrl+C)
- `SystemExit` (a call to `sys.exit()`)
- `MemoryError`, `RecursionError`
- Syntax-level issues in the JSON parsing

This means you can't even stop the program with Ctrl+C when it's stuck in this function. At minimum use `except Exception:`, which excludes `KeyboardInterrupt` and `SystemExit`.

### Problem: Too-Broad Try Block

The entire function body is in one `try` block, so you can't distinguish between:
- Network failure (`requests.ConnectionError`) — the API is down
- Timeout (`requests.Timeout`) — the API is slow
- HTTP error (404, 500) — the API returned an error status
- Bad JSON (`json.JSONDecodeError`) — the API returned non-JSON
- Missing key (`KeyError`) — the API changed its schema
- Cache failure — Redis is down

Each failure has a different appropriate response. A schema change (missing `'name'` key) is a bug that should alert developers, not silently return `None`.

### Problem: Generic Error Message

`"Failed to fetch user"` tells you nothing. Which user? What error? Was it a network issue or a data issue?

### Problem: Returning `None`

Every caller must check `if result is None` or risk `TypeError` later. This spreads error handling throughout the codebase. Consider raising a domain-specific exception instead.

### Improved Version

```python
def fetch_user_data(user_id: int) -> dict:
    try:
        response = requests.get(
            f"{API_BASE}/users/{user_id}", timeout=10
        )
        response.raise_for_status()
    except requests.Timeout:
        logger.warning("Timeout fetching user %d", user_id)
        raise UserFetchError(f"Timeout for user {user_id}") from None
    except requests.RequestException as e:
        logger.error("Network error fetching user %d: %s", user_id, e)
        raise UserFetchError(f"Cannot reach API for user {user_id}") from e

    data = response.json()
    user = {
        'name': data['name'],    # KeyError here = bug, let it propagate
        'email': data['email'],
        'role': data.get('role', 'user'),
    }

    try:
        cache.set(f'user:{user_id}', user, ttl=300)
    except Exception as e:
        logger.warning("Cache write failed for user %d: %s", user_id, e)
        # Non-fatal: return the user even if caching fails

    return user
```

This distinguishes network errors (handled), schema changes (crash loudly), and cache failures (log and continue).'''
    ),

    # Rust: unnecessary clones (thinking)
    (
        "understand1_26",
        r'''Review this Rust code for performance:

```rust
fn find_duplicates(items: &[String]) -> Vec<String> {
    let mut seen = HashSet::new();
    let mut duplicates = Vec::new();

    for item in items {
        let key = item.clone().to_lowercase();
        if seen.contains(&key) {
            duplicates.push(item.clone());
        } else {
            seen.insert(key.clone());
        }
    }

    duplicates.sort();
    duplicates.dedup();
    duplicates
}
```''',
        r'''<think>
Several unnecessary allocations here. The `item.clone().to_lowercase()` clones the string before lowercasing — `to_lowercase()` already creates a new String, so the clone is wasted. Then `key.clone()` when inserting into the set is unnecessary because `key` isn't used after the insert (it can be moved). And `duplicates.push(item.clone())` is necessary since we're borrowing from the slice — but the sort+dedup at the end could be avoided with a second HashSet.
</think>

## Code Review: Unnecessary Allocations

### Issue 1: `item.clone().to_lowercase()` — Wasted Clone

```rust
let key = item.clone().to_lowercase();
```

`to_lowercase()` already creates a **new `String`**. Cloning `item` first creates an intermediate `String` that's immediately consumed by `to_lowercase()` and then dropped. Just call `to_lowercase()` directly:

```rust
let key = item.to_lowercase();  // item is &String, to_lowercase works on &str
```

This eliminates one allocation per item.

### Issue 2: `seen.insert(key.clone())` — Unnecessary Clone

```rust
seen.insert(key.clone());
```

`key` is not used after this point in the `else` branch. It can be **moved** into the set instead of cloned:

```rust
seen.insert(key);  // move, not clone
```

This eliminates another allocation per unique item.

### Issue 3: `sort()` + `dedup()` — Use a HashSet Instead

```rust
duplicates.sort();
duplicates.dedup();
```

This is O(n log n) for deduplication. If an item appears 5 times, it gets pushed 4 times and then deduped. Using a second `HashSet` for duplicates is O(1) per check:

```rust
fn find_duplicates(items: &[String]) -> Vec<String> {
    let mut seen = HashSet::new();
    let mut dup_set = HashSet::new();

    for item in items {
        let key = item.to_lowercase();
        if !seen.insert(key) {
            // insert returns false if the value was already present
            dup_set.insert(item.clone());
        }
    }

    let mut duplicates: Vec<String> = dup_set.into_iter().collect();
    duplicates.sort();  // only if sorted output is needed
    duplicates
}
```

### Summary of Savings

| Change | Allocations saved |
|---|---|
| Remove `.clone()` before `to_lowercase()` | 1 per item |
| Move `key` into set instead of cloning | 1 per unique item |
| Use `HashSet` for dedup | Avoids duplicate pushes entirely |

For a list of 10,000 items, the original version creates roughly 30,000 unnecessary `String` allocations. The improved version reduces this to the minimum: one `to_lowercase()` per item plus one `clone()` per duplicate.'''
    ),

    # Go: error handling not idiomatic (direct)
    (
        "understand1_27",
        r'''Review this Go code — is it idiomatic?

```go
func LoadConfig(path string) (*Config, error) {
    data, err := os.ReadFile(path)
    if err != nil {
        return nil, errors.New("config error")
    }

    var cfg Config
    err = json.Unmarshal(data, &cfg)
    if err != nil {
        return nil, errors.New("config error")
    }

    if cfg.Port == 0 {
        cfg.Port = 8080
    }

    if cfg.DatabaseURL == "" {
        return nil, errors.New("config error")
    }

    conn, err := sql.Open("postgres", cfg.DatabaseURL)
    if err != nil {
        return nil, errors.New("config error")
    }

    err = conn.Ping()
    if err != nil {
        return nil, errors.New("config error")
    }

    cfg.DB = conn
    return &cfg, nil
}
```''',
        r'''## Code Review: Go Error Handling

### Critical: All Errors Are `"config error"`

Every failure path returns the same generic `errors.New("config error")`. The caller has no idea what went wrong — was the file missing? Was the JSON malformed? Was the database unreachable? This makes debugging in production extremely painful.

**Fix:** Wrap errors with context using `fmt.Errorf` and the `%w` verb:

```go
data, err := os.ReadFile(path)
if err != nil {
    return nil, fmt.Errorf("reading config %s: %w", path, err)
}

err = json.Unmarshal(data, &cfg)
if err != nil {
    return nil, fmt.Errorf("parsing config JSON: %w", err)
}
```

The `%w` verb wraps the original error, so callers can use `errors.Is()` and `errors.As()` to inspect the cause. The context string tells you WHERE the error happened while preserving WHAT the original error was.

### Issue: Function Does Too Much

`LoadConfig` reads a file, parses JSON, validates fields, connects to a database, and pings it. Loading configuration and establishing database connections are separate concerns. If the database is temporarily down, you can't even read your config.

```go
func LoadConfig(path string) (*Config, error) { /* read + parse + validate */ }
func ConnectDB(cfg *Config) (*sql.DB, error)  { /* connect + ping */ }
```

### Issue: Database Connection Leak on Partial Failure

If `conn.Ping()` fails, `conn` (the `*sql.DB`) is never closed. While `sql.Open` often just validates arguments without creating real connections, it's still a resource that should be cleaned up:

```go
conn, err := sql.Open("postgres", cfg.DatabaseURL)
if err != nil {
    return nil, fmt.Errorf("opening database: %w", err)
}
if err := conn.Ping(); err != nil {
    conn.Close()
    return nil, fmt.Errorf("pinging database: %w", err)
}
```

### Minor: Validation Could Be a Method

```go
func (c *Config) validate() error {
    if c.DatabaseURL == "" {
        return errors.New("database_url is required")
    }
    if c.Port == 0 {
        c.Port = 8080 // default
    }
    return nil
}
```

This makes validation testable independently and keeps `LoadConfig` focused on I/O.'''
    ),

    # JS: callback hell (thinking)
    (
        "understand1_28",
        r'''Review this JavaScript code:

```javascript
function processOrder(orderId, callback) {
    getOrder(orderId, function(err, order) {
        if (err) return callback(err);
        validateInventory(order.items, function(err, available) {
            if (err) return callback(err);
            if (!available) return callback(new Error('Out of stock'));
            calculateShipping(order.address, order.items, function(err, shipping) {
                if (err) return callback(err);
                chargePayment(order.payment, order.total + shipping, function(err, receipt) {
                    if (err) return callback(err);
                    updateOrderStatus(orderId, 'completed', receipt, function(err) {
                        if (err) return callback(err);
                        sendConfirmationEmail(order.email, receipt, function(err) {
                            if (err) return callback(err);
                            callback(null, { orderId, receipt, shipping });
                        });
                    });
                });
            });
        });
    });
}
```''',
        r'''<think>
Classic callback hell / pyramid of doom. The code works but is deeply nested, hard to read, and error handling is repetitive. Should be refactored to async/await. I should also point out the lack of error recovery — if chargePayment succeeds but updateOrderStatus fails, the payment was taken but the order isn't marked complete.
</think>

## Code Review: Callback Pyramid of Doom

### Primary Issue: Deep Nesting

This is the classic "callback hell" pattern — six levels of nesting that make the code hard to read, modify, and debug. Adding a step between `calculateShipping` and `chargePayment` means indenting everything below it further.

### Refactored with Async/Await

Assuming the underlying functions return Promises (or can be wrapped with `util.promisify`):

```javascript
async function processOrder(orderId) {
    const order = await getOrder(orderId);

    const available = await validateInventory(order.items);
    if (!available) throw new Error('Out of stock');

    const shipping = await calculateShipping(order.address, order.items);
    const receipt = await chargePayment(order.payment, order.total + shipping);

    await updateOrderStatus(orderId, 'completed', receipt);
    await sendConfirmationEmail(order.email, receipt);

    return { orderId, receipt, shipping };
}
```

Same logic, flat structure. Each step is one line. Adding or removing a step is a single-line change.

### Deeper Issue: No Error Recovery for Partial Failures

Both versions have the same logical bug: if `chargePayment` succeeds but `updateOrderStatus` fails, the customer has been charged but their order shows as incomplete. There's no rollback or compensation.

In a real system, you'd want:

```javascript
const receipt = await chargePayment(order.payment, order.total + shipping);
try {
    await updateOrderStatus(orderId, 'completed', receipt);
} catch (err) {
    // Payment was taken — don't lose it
    await flagForManualReview(orderId, receipt, err);
    throw err;
}
```

### Other Notes

- **`sendConfirmationEmail`** should not block the response or cause the entire operation to fail. If the payment is taken and order is updated, a failed email shouldn't roll back the order. Send it asynchronously or put it on a queue.
- **No input validation**: `orderId` is used without checking if it's valid.
- **Error messages from deeper functions are lost**: In the callback version, each `err` is passed through but never enriched with context. At the top level, a caller might get "connection refused" with no idea which step failed.'''
    ),

    # JS: React stale closure (direct)
    (
        "understand1_29",
        r'''What's wrong with this React component?

```javascript
function ChatRoom({ roomId }) {
    const [messages, setMessages] = useState([]);
    const [input, setInput] = useState('');

    useEffect(() => {
        const ws = new WebSocket(`wss://chat.example.com/${roomId}`);

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            setMessages([...messages, msg]);
        };

        ws.onclose = () => {
            console.log(`Disconnected from room ${roomId}`);
        };

        return () => ws.close();
    }, [roomId]);

    const sendMessage = () => {
        // assume wsRef is available
        ws.send(JSON.stringify({ text: input, room: roomId }));
        setInput('');
    };

    return (
        <div>
            {messages.map((m, i) => <p key={i}>{m.text}</p>)}
            <input value={input} onChange={e => setInput(e.target.value)} />
            <button onClick={sendMessage}>Send</button>
        </div>
    );
}
```''',
        r'''## Code Review: Multiple Bugs

### Bug 1: Stale Closure Over `messages`

```javascript
ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    setMessages([...messages, msg]);  // `messages` is stale!
};
```

The `useEffect` runs when `roomId` changes, capturing `messages` at that moment (likely `[]`). As new messages arrive, each `onmessage` callback spreads `[...messages, msg]` — but `messages` is always the value from when the effect ran, not the current state. Result: **only the latest message is kept**, overwriting all previous ones.

**Fix:** Use the functional form of `setMessages`:

```javascript
ws.onmessage = (event) => {
    const msg = JSON.parse(event.data);
    setMessages(prev => [...prev, msg]);  // prev is always current
};
```

The functional updater `prev => [...]` receives the actual current state, avoiding the stale closure.

### Bug 2: `ws` Not Accessible in `sendMessage`

```javascript
const sendMessage = () => {
    ws.send(JSON.stringify({ text: input, room: roomId }));
};
```

`ws` is declared inside the `useEffect` callback — it's not in scope for `sendMessage`. This will throw `ReferenceError: ws is not defined`. You need a ref:

```javascript
const wsRef = useRef(null);

useEffect(() => {
    const ws = new WebSocket(`wss://chat.example.com/${roomId}`);
    wsRef.current = ws;
    // ...
    return () => ws.close();
}, [roomId]);

const sendMessage = () => {
    wsRef.current?.send(JSON.stringify({ text: input, room: roomId }));
};
```

### Bug 3: Missing Dependency Warning

ESLint's `react-hooks/exhaustive-deps` rule would flag `messages` as a missing dependency in the `useEffect`. But adding `messages` to the dependency array would be wrong — it would reconnect the WebSocket on every new message. The functional updater in Bug 1's fix eliminates this dependency entirely.

### Minor: Using Array Index as Key

```javascript
messages.map((m, i) => <p key={i}>{m.text}</p>)
```

Using index as key is problematic when items can be reordered or inserted at the beginning. If messages always append at the end, it works, but a message ID would be more robust: `key={m.id}`.'''
    ),

    # C++: raw pointers where smart pointers should be (thinking)
    (
        "understand1_30",
        r'''Review this C++ code:

```cpp
class ResourceManager {
public:
    ResourceManager() : logger_(new Logger()), cache_(new LRUCache(1000)) {}

    ~ResourceManager() {
        delete logger_;
        delete cache_;
    }

    void loadResource(const std::string& name) {
        Resource* res = new Resource(name);
        res->load();
        if (!res->isValid()) {
            delete res;
            throw std::runtime_error("Invalid resource: " + name);
        }
        resources_[name] = res;
    }

    Resource* getResource(const std::string& name) {
        return resources_[name];
    }

    void clearAll() {
        for (auto& [name, res] : resources_) {
            delete res;
        }
        resources_.clear();
    }

private:
    Logger* logger_;
    LRUCache* cache_;
    std::unordered_map<std::string, Resource*> resources_;
};
```''',
        r'''<think>
Multiple issues: no copy constructor/assignment operator (Rule of Five violation), raw owning pointers should be smart pointers, exception safety issues in loadResource, getResource returns raw pointer with unclear ownership, and clearAll doesn't handle double-delete if called twice without clearing the map (actually it does clear). Let me be thorough.
</think>

## Code Review: Manual Memory Management Issues

### Critical: Rule of Five Violation

The class defines a destructor (`~ResourceManager`) but no copy constructor, copy assignment, move constructor, or move assignment. If a `ResourceManager` is copied:

```cpp
ResourceManager a;
ResourceManager b = a;  // shallow copy — both own same pointers
// b's destructor deletes logger_, cache_, all resources
// a's destructor deletes them again — double-free, undefined behavior
```

**Fix:** Either delete copy/move operations or implement them correctly:
```cpp
ResourceManager(const ResourceManager&) = delete;
ResourceManager& operator=(const ResourceManager&) = delete;
```

### Critical: Use Smart Pointers

All raw `new`/`delete` pairs should be smart pointers:

```cpp
class ResourceManager {
public:
    ResourceManager()
        : logger_(std::make_unique<Logger>())
        , cache_(std::make_unique<LRUCache>(1000)) {}

    // No destructor needed — smart pointers clean up automatically

    void loadResource(const std::string& name) {
        auto res = std::make_unique<Resource>(name);
        res->load();
        if (!res->isValid()) {
            throw std::runtime_error("Invalid resource: " + name);
            // res automatically deleted when unique_ptr goes out of scope
        }
        resources_[name] = std::move(res);
    }

    Resource* getResource(const std::string& name) {
        auto it = resources_.find(name);
        return it != resources_.end() ? it->second.get() : nullptr;
    }

    void clearAll() {
        resources_.clear();  // unique_ptrs delete their resources
    }

private:
    std::unique_ptr<Logger> logger_;
    std::unique_ptr<LRUCache> cache_;
    std::unordered_map<std::string, std::unique_ptr<Resource>> resources_;
};
```

### Bug: Exception Safety in `loadResource`

In the original, if `resources_[name] = res` throws (possible if the map needs to rehash and allocation fails), `res` is leaked. With `unique_ptr`, the resource is automatically cleaned up.

### Bug: `getResource` with `operator[]`

```cpp
return resources_[name];  // inserts nullptr if name doesn't exist!
```

`operator[]` on `unordered_map` **inserts a default value** if the key is missing. So querying a nonexistent resource silently creates a null entry. Use `find()` instead.

### Bug: Destructor Doesn't Delete Resources

The destructor deletes `logger_` and `cache_` but **never calls `clearAll()`**. All resources in the map are leaked when the `ResourceManager` is destroyed. With `unique_ptr`, this is handled automatically.'''
    ),
]
