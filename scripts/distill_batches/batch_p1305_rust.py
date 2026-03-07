"""Rust training pairs (part 1): ownership, lifetimes, async, error handling, traits."""

PAIRS = [
    (
        "rust/ownership-transfer-vs-borrowing",
        r'''Explain the difference between ownership transfer and borrowing in Rust. Show both with a function that processes a String.''',
        r'''<think>
This is a core Rust concept. I need to show move semantics vs borrowing clearly.
Ownership transfer means the caller loses access after passing to a function.
Borrowing (shared &T or exclusive &mut T) lets the caller retain ownership.
I'll show a function that takes ownership vs one that borrows, and explain when to use each.
The compiler enforces these rules at compile time with no runtime cost.
</think>

In Rust, **ownership transfer** (move) gives the callee full control — the caller can no longer use the value. **Borrowing** lends access temporarily via references.

```rust
// Ownership transfer — caller loses access to `s` after this call
fn consume(s: String) -> usize {
    println!("consumed: {s}");
    s.len()
}

// Borrowing — caller retains ownership of `s`
fn inspect(s: &str) -> usize {
    println!("inspected: {s}");
    s.len()
}

fn main() {
    let s = String::from("hello");

    // Borrow: `s` is still valid after this call
    let len = inspect(&s);
    println!("len = {len}, s is still alive: {s}");

    // Move: `s` is consumed, using it after this is a compile error
    let len = consume(s);
    // println!("{s}"); // ERROR: value used after move
    println!("len = {len}");
}
```

**When to use which:**
- **Borrow (`&T` / `&str`)** — the default; use when you only need to read.
- **Move** — when the function needs to store the value, return a transformed version, or the type isn't `Clone`.
- **`&mut T`** — when you need to modify in place without taking ownership.

Types that implement `Copy` (integers, `bool`, `char`) are implicitly copied instead of moved.'''
    ),
    (
        "rust/mutable-references-borrow-checker",
        r'''Show me how mutable references work with the borrow checker. What are the rules, and can you give an example that would fail?''',
        r'''<think>
The borrow checker enforces two key rules: you can have either one &mut or many & references at a time, never both.
This prevents data races at compile time. I should show a valid mutable borrow,
then a failing case where we try to alias a mutable reference with a shared one.
I'll also mention Non-Lexical Lifetimes (NLL) which made the rules more ergonomic in edition 2018+.
NLL lets borrows end at last use rather than at scope end.
</think>

Rust's borrow checker enforces at compile time:
1. **One mutable reference** OR **any number of shared references** — never both simultaneously.
2. The referent must live at least as long as the reference.

```rust
fn main() {
    let mut v = vec![1, 2, 3];

    // Valid: single mutable borrow
    let r = &mut v;
    r.push(4);
    println!("{r:?}"); // [1, 2, 3, 4]

    // Valid thanks to NLL — `r` is no longer used, so this shared borrow is fine
    println!("{}", v.len());

    // FAILS: mutable + shared borrow overlap
    let r1 = &v;          // shared borrow starts
    // let r2 = &mut v;   // ERROR: cannot borrow `v` as mutable because
                           //        it is also borrowed as immutable
    println!("{r1:?}");    // shared borrow used here
}
```

A common real-world case — iterating while mutating:

```rust
fn main() {
    let mut scores = vec![80, 55, 90, 42];

    // This fails — can't borrow `scores` mutably while iterating
    // for s in &scores {
    //     if *s < 60 { scores.push(0); }
    // }

    // Fix: collect indices first, then mutate
    let to_fix: Vec<usize> = scores.iter()
        .enumerate()
        .filter(|(_, &s)| s < 60)
        .map(|(i, _)| i)
        .collect();

    for i in to_fix {
        scores[i] = 60; // reborrow as &mut is fine, no active shared borrow
    }
    println!("{scores:?}"); // [80, 60, 90, 60]
}
```'''
    ),
    (
        "rust/lifetime-annotations-in-structs",
        r'''How do I add lifetime annotations to a Rust struct that holds references? Give a practical example.''',
        r'''<think>
When a struct holds a reference, the compiler needs to know that the referenced data
outlives the struct. We express this with a named lifetime parameter on the struct.
I should show a simple struct with one lifetime, then a more complex one with two.
I'll also show how methods on such structs carry the lifetime through.
This is intermediate-level Rust that trips up many newcomers.
</think>

When a struct holds a reference, you must declare a **lifetime parameter** so the compiler can verify the referenced data outlives the struct.

```rust
// The struct borrows a string slice — `'a` ties the reference's lifetime
// to the struct's lifetime
struct Excerpt<'a> {
    text: &'a str,
    line: usize,
}

impl<'a> Excerpt<'a> {
    fn new(text: &'a str, line: usize) -> Self {
        Excerpt { text, line }
    }

    // Return type borrows from the same lifetime
    fn first_word(&self) -> &'a str {
        self.text.split_whitespace().next().unwrap_or("")
    }
}

fn main() {
    let novel = String::from("Call me Ishmael. Some years ago...");
    let excerpt = Excerpt::new(&novel[..16], 1);
    println!("line {}: {:?} — first word: {}", excerpt.line, excerpt.text, excerpt.first_word());
    // "line 1: "Call me Ishmael." — first word: Call"
}
```

**Multiple lifetimes** when fields borrow from different sources:

```rust
struct Pair<'a, 'b> {
    key: &'a str,
    value: &'b str,
}

fn build_pair<'a, 'b>(k: &'a str, v: &'b str) -> Pair<'a, 'b> {
    Pair { key: k, value: v }
}
```

**Key rules:**
- The struct cannot outlive the data it references.
- If you own the data instead, use `String` (not `&str`) and skip lifetimes entirely.
- Prefer owned types unless you have a clear reason to borrow (zero-copy parsing, large data).'''
    ),
    (
        "rust/lifetime-elision-rules",
        r'''What are Rust's lifetime elision rules? When can I skip writing lifetime annotations?''',
        r'''<think>
Lifetime elision is the compiler's ability to infer lifetimes in function signatures
without explicit annotations. There are three rules applied in order.
Rule 1: each reference param gets its own lifetime. Rule 2: if exactly one input lifetime,
it's assigned to all output lifetimes. Rule 3: if one param is &self or &mut self,
that lifetime is assigned to all output lifetimes.
If the rules don't fully determine output lifetimes, you must annotate explicitly.
I'll show examples where elision works and where it fails.
</think>

The compiler applies **three rules** in order to infer lifetimes so you don't have to write them:

**Rule 1:** Each reference parameter gets its own lifetime.
```rust
fn foo(x: &str, y: &str)
// becomes: fn foo<'a, 'b>(x: &'a str, y: &'b str)
```

**Rule 2:** If there is exactly **one** input lifetime, it is assigned to all output references.
```rust
fn first_word(s: &str) -> &str { .. }
// becomes: fn first_word<'a>(s: &'a str) -> &'a str
```

**Rule 3:** If one parameter is `&self` or `&mut self`, the `self` lifetime is assigned to all outputs.
```rust
impl MyStruct {
    fn name(&self) -> &str { .. }
    // becomes: fn name<'a>(&'a self) -> &'a str
}
```

**When elision fails** — you must annotate explicitly:

```rust
// Two input lifetimes, no `self` — compiler can't decide which
// output borrows from. This won't compile without annotations.
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() { x } else { y }
}
```

**Practical tip:** Write your function without lifetime annotations first. If the compiler complains, add them. Elision handles ~90% of cases in everyday code.'''
    ),
    (
        "rust/async-await-tokio-runtime",
        r'''Show me how to set up a basic async Rust program with tokio. Include making an HTTP request.''',
        r'''<think>
Setting up async Rust with tokio requires the tokio runtime macro and an async main.
I'll show the Cargo.toml deps (tokio + reqwest), the #[tokio::main] macro,
and a simple HTTP GET. I should mention the runtime flavors (current_thread vs multi_thread)
and that async functions return a Future that must be awaited.
reqwest is the standard HTTP client in the async Rust ecosystem.
</think>

**Cargo.toml:**
```toml
[dependencies]
tokio = { version = "1", features = ["full"] }
reqwest = { version = "0.12", features = ["json"] }
serde = { version = "1", features = ["derive"] }
```

**src/main.rs:**
```rust
use serde::Deserialize;

#[derive(Debug, Deserialize)]
struct Repo {
    name: String,
    stargazers_count: u64,
}

#[tokio::main] // expands to a multi-thread runtime by default
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let client = reqwest::Client::new();

    let repo: Repo = client
        .get("https://api.github.com/repos/tokio-rs/tokio")
        .header("User-Agent", "rust-example")
        .send()
        .await?       // await the Future, ? propagates errors
        .json()
        .await?;

    println!("{} has {} stars", repo.name, repo.stargazers_count);
    Ok(())
}
```

**Key points:**
- `#[tokio::main]` sets up the runtime. For a single-threaded runtime use `#[tokio::main(flavor = "current_thread")]`.
- Every `.await` is a suspension point — the runtime can run other tasks while waiting.
- `async fn` returns `impl Future<Output = T>` — nothing runs until awaited.
- For libraries, don't use `#[tokio::main]`; let the caller choose the runtime. Return `impl Future` instead.'''
    ),
    (
        "rust/tokio-spawn-joinhandle",
        r'''How do I spawn concurrent tasks in tokio? Show tokio::spawn and how to collect results.''',
        r'''<think>
tokio::spawn creates a new task on the runtime, returning a JoinHandle.
The spawned future must be 'static and Send. I'll show spawning multiple tasks,
collecting JoinHandles, and awaiting them. I should also show error handling since
JoinHandle::await returns Result<T, JoinError>.
A practical example: fetching multiple URLs concurrently.
This is intermediate async Rust.
</think>

`tokio::spawn` schedules a future as an independent task on the runtime and returns a `JoinHandle<T>`.

```rust
use tokio::task::JoinHandle;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Spawn several tasks concurrently
    let handles: Vec<JoinHandle<u64>> = (1..=5)
        .map(|i| {
            tokio::spawn(async move {
                // Simulate async work
                tokio::time::sleep(std::time::Duration::from_millis(100 * i)).await;
                i * i
            })
        })
        .collect();

    // Await all results
    let mut results = Vec::new();
    for h in handles {
        let val = h.await?; // JoinError if the task panicked
        results.push(val);
    }
    println!("{results:?}"); // [1, 4, 9, 16, 25]

    Ok(())
}
```

**Using `futures::future::join_all` for convenience:**

```rust
use futures::future::join_all;

async fn fetch(url: &str) -> reqwest::Result<String> {
    reqwest::get(url).await?.text().await
}

#[tokio::main]
async fn main() {
    let urls = vec![
        "https://httpbin.org/get",
        "https://httpbin.org/ip",
    ];

    let tasks: Vec<_> = urls.into_iter().map(|u| {
        tokio::spawn(async move { fetch(u).await })
    }).collect();

    let results = join_all(tasks).await;
    for r in results {
        match r {
            Ok(Ok(body)) => println!("{}", &body[..80.min(body.len())]),
            Ok(Err(e)) => eprintln!("request error: {e}"),
            Err(e) => eprintln!("task panicked: {e}"),
        }
    }
}
```

**Constraints on spawned futures:**
- Must be `Send` (no `Rc`, non-Send mutex guards across `.await`).
- Must be `'static` (can't borrow from the calling scope — use `Arc` or move owned data).'''
    ),
    (
        "rust/tokio-select-concurrent",
        r'''Show how to use tokio::select! to race multiple async operations.''',
        r'''<think>
tokio::select! waits on multiple futures and runs the branch for whichever completes first.
The remaining futures are dropped (cancelled). This is useful for timeouts, graceful shutdown,
and multiplexing channels. I need to show basic syntax, the cancellation semantics,
and a practical example like racing a timeout against a computation.
I should also mention biased mode and the else branch.
</think>

`tokio::select!` races multiple futures concurrently and executes the branch of whichever completes first. All other branches are **cancelled** (dropped).

```rust
use tokio::time::{sleep, Duration};
use tokio::sync::mpsc;

#[tokio::main]
async fn main() {
    let (tx, mut rx) = mpsc::channel::<String>(10);

    // Producer in a separate task
    tokio::spawn(async move {
        sleep(Duration::from_millis(200)).await;
        tx.send("data arrived".into()).await.ok();
    });

    // Race: channel message vs timeout
    tokio::select! {
        Some(msg) = rx.recv() => {
            println!("received: {msg}");
        }
        _ = sleep(Duration::from_secs(1)) => {
            println!("timed out waiting for message");
        }
    }
}
```

**Loop with select for a worker pattern:**

```rust
use tokio::signal;
use tokio::sync::mpsc;
use tokio::time::{interval, Duration};

async fn worker(mut rx: mpsc::Receiver<u32>) {
    let mut tick = interval(Duration::from_secs(5));

    loop {
        tokio::select! {
            Some(job) = rx.recv() => {
                println!("processing job {job}");
            }
            _ = tick.tick() => {
                println!("heartbeat");
            }
            _ = signal::ctrl_c() => {
                println!("shutting down");
                break;
            }
        }
    }
}
```

**Key details:**
- Unselected branches are **dropped** — if a future holds state, wrap it outside the loop or use `&mut future` with `pin!`.
- `biased;` as the first token evaluates branches in order (useful to prioritize shutdown signals).
- The `else` branch runs if all branches are disabled (e.g., all channels closed).'''
    ),
    (
        "rust/tokio-channels-mpsc-oneshot",
        r'''Explain tokio's channel types (mpsc and oneshot). Show a request-response pattern using both.''',
        r'''<think>
Tokio provides mpsc (multi-producer, single-consumer) and oneshot (single-use reply) channels.
A common pattern is sending a request through mpsc with a oneshot Sender bundled for the reply.
This is how actor-like patterns work in async Rust. I'll show the request struct,
the server loop receiving from mpsc, and the client awaiting the oneshot response.
This is an advanced async pattern used in production services.
</think>

Tokio provides two main channel types:
- **`mpsc`** — multi-producer, single-consumer; buffered or unbounded.
- **`oneshot`** — single value, single use; perfect for request/response.

**Request-response actor pattern:**

```rust
use tokio::sync::{mpsc, oneshot};

// Request carries a oneshot sender for the reply
struct Lookup {
    key: String,
    reply: oneshot::Sender<Option<String>>,
}

// "Actor" — owns the data, processes requests sequentially
async fn kv_actor(mut rx: mpsc::Receiver<Lookup>) {
    let mut store = std::collections::HashMap::new();
    store.insert("foo".to_string(), "bar".to_string());

    while let Some(req) = rx.recv().await {
        let result = store.get(&req.key).cloned();
        let _ = req.reply.send(result); // ignore if caller dropped
    }
}

// Client handle — cheaply cloneable
#[derive(Clone)]
struct KvClient {
    tx: mpsc::Sender<Lookup>,
}

impl KvClient {
    async fn get(&self, key: &str) -> Option<String> {
        let (reply_tx, reply_rx) = oneshot::channel();
        let req = Lookup { key: key.to_string(), reply: reply_tx };
        self.tx.send(req).await.ok()?;
        reply_rx.await.ok().flatten()
    }
}

#[tokio::main]
async fn main() {
    let (tx, rx) = mpsc::channel(32);
    tokio::spawn(kv_actor(rx));

    let client = KvClient { tx };

    // Multiple concurrent lookups
    let c1 = client.clone();
    let c2 = client.clone();
    let (r1, r2) = tokio::join!(
        c1.get("foo"),
        c2.get("missing"),
    );
    println!("foo => {r1:?}");     // Some("bar")
    println!("missing => {r2:?}"); // None
}
```

**When to use which:**
| Channel | Producers | Messages | Use case |
|---------|-----------|----------|----------|
| `mpsc` | Many | Stream | Work queues, event buses |
| `oneshot` | One | One | Reply channels, completion signals |
| `broadcast` | Many | Many (clone) | Fan-out notifications |
| `watch` | One | Latest value | Config reload, state sharing |'''
    ),
    (
        "rust/async-timeouts-cancellation",
        r'''How do I implement timeouts and cancellation for async operations in tokio?''',
        r'''<think>
Tokio provides tokio::time::timeout to wrap any future with a deadline.
For cancellation, dropping a future cancels it; CancellationToken is the structured approach.
I should show timeout wrapping, CancellationToken usage, and how to make operations
cancellation-safe (important for correctness). tokio_util::sync::CancellationToken
is the standard tool for graceful shutdown.
This is advanced async Rust.
</think>

**Timeouts with `tokio::time::timeout`:**

```rust
use tokio::time::{timeout, Duration};

async fn slow_operation() -> String {
    tokio::time::sleep(Duration::from_secs(10)).await;
    "done".into()
}

#[tokio::main]
async fn main() {
    match timeout(Duration::from_secs(2), slow_operation()).await {
        Ok(result) => println!("got: {result}"),
        Err(_) => println!("operation timed out"),
    }
}
```

**Structured cancellation with `CancellationToken`:**

```rust
use tokio_util::sync::CancellationToken;
use tokio::time::{sleep, Duration};

async fn background_worker(token: CancellationToken) {
    loop {
        tokio::select! {
            _ = token.cancelled() => {
                println!("worker: shutting down gracefully");
                break;
            }
            _ = sleep(Duration::from_secs(1)) => {
                println!("worker: tick");
            }
        }
    }
}

#[tokio::main]
async fn main() {
    let token = CancellationToken::new();

    // Child tokens for hierarchical cancellation
    let child_token = token.child_token();
    let handle = tokio::spawn(background_worker(child_token));

    sleep(Duration::from_secs(3)).await;
    token.cancel(); // cancels all children too
    handle.await.unwrap();
    println!("clean shutdown complete");
}
```

**Cancellation safety gotcha:**

```rust
// UNSAFE pattern — data loss if cancelled between recv and process
loop {
    tokio::select! {
        Some(msg) = rx.recv() => {
            process(msg).await; // if cancelled HERE, msg is lost
        }
        _ = token.cancelled() => break,
    }
}

// SAFE pattern — don't hold unprocessed data across await points
loop {
    let msg = tokio::select! {
        Some(msg) = rx.recv() => msg,
        _ = token.cancelled() => break,
    };
    process(msg).await; // outside select, runs to completion
}
```'''
    ),
    (
        "rust/result-option-chaining",
        r'''Show idiomatic Result and Option chaining in Rust. How do I avoid nested match blocks?''',
        r'''<think>
Rust's Result and Option have rich combinator APIs: map, and_then, unwrap_or_else, ok_or,
transpose, etc. The ? operator is the primary tool for early returns.
I'll show chaining with ? in a function, then combinators for transformations,
and the interop between Option and Result (ok_or, transpose).
This is intermediate Rust that drastically cleans up error handling code.
</think>

Use the `?` operator and combinators to flatten nested matches into clean chains.

**The `?` operator — early return on error/None:**

```rust
use std::fs;

fn read_config_value(path: &str, key: &str) -> Result<String, Box<dyn std::error::Error>> {
    let content = fs::read_to_string(path)?;          // returns Err if file fails
    let line = content
        .lines()
        .find(|l| l.starts_with(key))
        .ok_or("key not found")?;                     // Option → Result with ok_or
    let value = line
        .split('=')
        .nth(1)
        .ok_or("malformed line")?
        .trim()
        .to_string();
    Ok(value)
}
```

**Combinator chaining on Option:**

```rust
fn parse_port(input: Option<&str>) -> u16 {
    input
        .map(|s| s.trim())                  // Option<&str>
        .filter(|s| !s.is_empty())          // None if empty
        .and_then(|s| s.parse::<u16>().ok()) // Option<u16>
        .unwrap_or(8080)                     // default
}

assert_eq!(parse_port(Some(" 3000 ")), 3000);
assert_eq!(parse_port(Some("")), 8080);
assert_eq!(parse_port(None), 8080);
```

**Result combinators:**

```rust
fn double_parse(s: &str) -> Result<i64, String> {
    s.parse::<i64>()
        .map(|n| n * 2)                          // transform Ok value
        .map_err(|e| format!("bad number: {e}"))  // transform Err value
}

// Chaining fallible operations
fn pipeline(input: &str) -> Result<String, String> {
    input.parse::<u64>()
        .map_err(|e| e.to_string())
        .and_then(|n| if n > 0 { Ok(n) } else { Err("must be positive".into()) })
        .map(|n| format!("result: {}", n * 10))
}
```

**Option ↔ Result interop:**

```rust
let opt: Option<Result<i32, &str>> = Some(Ok(42));
let res: Result<Option<i32>, &str> = opt.transpose(); // Ok(Some(42))

let opt: Option<i32> = None;
let res: Result<i32, &str> = opt.ok_or("missing value");
```'''
    ),
    (
        "rust/custom-error-types-thiserror",
        r'''How do I define custom error types in Rust using thiserror? Show a real-world example.''',
        r'''<think>
The thiserror crate provides derive macros for implementing std::error::Error.
It generates Display and From impls automatically. I should show a multi-variant enum error
with #[from] for automatic conversion and #[error("...")] for display formatting.
A real-world example: a service that does file I/O and JSON parsing, each with its own error variant.
This is intermediate Rust — thiserror is the standard for library error types.
</think>

`thiserror` generates `Display`, `Error`, and optionally `From` impls via derive macros. It's the standard choice for **library** error types.

```rust
use thiserror::Error;

#[derive(Debug, Error)]
pub enum AppError {
    #[error("database error: {0}")]
    Database(#[from] sqlx::Error),         // auto From<sqlx::Error>

    #[error("config parse error in {path}: {source}")]
    ConfigParse {
        path: String,
        #[source]                           // sets Error::source()
        source: serde_json::Error,
    },

    #[error("not found: {entity} with id {id}")]
    NotFound { entity: &'static str, id: u64 },

    #[error("unauthorized")]
    Unauthorized,

    #[error(transparent)]                   // delegates Display + source
    Other(#[from] anyhow::Error),
}

// Usage — the ? operator auto-converts thanks to #[from]
async fn get_user(pool: &sqlx::PgPool, id: u64) -> Result<User, AppError> {
    let user = sqlx::query_as::<_, User>("SELECT * FROM users WHERE id = $1")
        .bind(id as i64)
        .fetch_optional(pool)
        .await?                             // sqlx::Error → AppError::Database
        .ok_or(AppError::NotFound { entity: "user", id })?;
    Ok(user)
}

fn load_config(path: &str) -> Result<Config, AppError> {
    let data = std::fs::read_to_string(path)
        .map_err(|e| anyhow::anyhow!("io: {e}"))?;  // → AppError::Other
    let cfg: Config = serde_json::from_str(&data)
        .map_err(|source| AppError::ConfigParse {
            path: path.to_string(),
            source,
        })?;
    Ok(cfg)
}
```

**Guidelines:**
- **Libraries**: use `thiserror` — callers can match on variants.
- **Applications**: use `anyhow` — you rarely match on error types, just propagate and display.
- Keep `#[from]` for 1:1 mappings; use manual construction when you need extra context.'''
    ),
    (
        "rust/error-handling-anyhow",
        r'''When should I use anyhow vs thiserror in Rust? Show practical anyhow usage.''',
        r'''<think>
anyhow is for application-level error handling where you don't need to match on variants.
It provides anyhow::Result, context(), and bail!(). thiserror is for libraries
where callers need typed errors. I'll show typical anyhow patterns: context for wrapping,
bail! for early return, and how it integrates with ? for any Error type.
This is an intermediate topic but critical for writing clean Rust applications.
</think>

**Rule of thumb:** `thiserror` for libraries (typed errors), `anyhow` for applications (just propagate and display).

```rust
use anyhow::{Context, Result, bail, ensure};
use std::path::Path;

#[derive(serde::Deserialize)]
struct Config {
    port: u16,
    db_url: String,
}

fn load_config(path: &Path) -> Result<Config> {
    // .context() wraps the error with a human-readable message
    let text = std::fs::read_to_string(path)
        .with_context(|| format!("failed to read config from {}", path.display()))?;

    let cfg: Config = toml::from_str(&text)
        .context("invalid TOML in config file")?;

    // bail! for early return with a formatted error
    if cfg.port == 0 {
        bail!("port must be non-zero");
    }

    // ensure! is like assert but returns an error instead of panicking
    ensure!(cfg.db_url.starts_with("postgres://"), "db_url must be a postgres URL");

    Ok(cfg)
}

fn main() -> Result<()> {
    let cfg = load_config(Path::new("config.toml"))?;
    println!("starting on port {}", cfg.port);
    Ok(())
}
```

**Error output with context chain:**
```
Error: failed to read config from config.toml

Caused by:
    No such file or directory (os error 2)
```

**anyhow also works in `#[tokio::main]`:**
```rust
#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let resp = reqwest::get("https://api.example.com/data")
        .await
        .context("API request failed")?;
    let body = resp.text().await?;
    println!("{body}");
    Ok(())
}
```

**When to downcast (rare but possible):**
```rust
if let Some(io_err) = err.downcast_ref::<std::io::Error>() {
    if io_err.kind() == std::io::ErrorKind::NotFound { /* handle */ }
}
```'''
    ),
    (
        "rust/trait-objects-vs-impl-trait",
        r'''What's the difference between `dyn Trait` and `impl Trait` in Rust? When should I use each?''',
        r'''<think>
This is about static vs dynamic dispatch. impl Trait uses monomorphization (static dispatch),
while dyn Trait uses a vtable (dynamic dispatch). impl Trait in argument position is sugar
for generics; in return position it hides the concrete type. dyn Trait is needed when
the concrete type isn't known at compile time (heterogeneous collections, plugin systems).
I should cover performance, object safety, and practical examples.
</think>

**`impl Trait`** = static dispatch (monomorphized, zero-cost). **`dyn Trait`** = dynamic dispatch (vtable, runtime indirection).

```rust
trait Renderer {
    fn render(&self, data: &str) -> String;
}

struct HtmlRenderer;
impl Renderer for HtmlRenderer {
    fn render(&self, data: &str) -> String { format!("<p>{data}</p>") }
}

struct JsonRenderer;
impl Renderer for JsonRenderer {
    fn render(&self, data: &str) -> String { format!(r#"{{"text":"{data}"}}"#) }
}

// Static dispatch — compiler generates a specialized copy for each type
fn render_static(r: &impl Renderer, data: &str) -> String {
    r.render(data) // inlined, no vtable
}

// Dynamic dispatch — one function, dispatches via vtable at runtime
fn render_dynamic(r: &dyn Renderer, data: &str) -> String {
    r.render(data) // vtable lookup
}

// Heterogeneous collection — REQUIRES dyn
fn render_all(renderers: &[Box<dyn Renderer>], data: &str) {
    for r in renderers {
        println!("{}", r.render(data));
    }
}

// Return position impl Trait — hides concrete type, still static
fn make_renderer(html: bool) -> Box<dyn Renderer> {
    // Can't use `impl Renderer` here because the two branches
    // return DIFFERENT concrete types
    if html { Box::new(HtmlRenderer) } else { Box::new(JsonRenderer) }
}
```

**Decision guide:**

| Situation | Use |
|-----------|-----|
| Single concrete type, performance critical | `impl Trait` / generics |
| Heterogeneous collection | `Box<dyn Trait>` |
| Plugin / strategy pattern | `Box<dyn Trait>` or `Arc<dyn Trait>` |
| Return type varies by branch | `Box<dyn Trait>` |
| Public library API, hide internals | `impl Trait` return |

**Object safety requirement** for `dyn Trait`: no `Self` in return position, no generic methods (unless bounded with `where Self: Sized`).'''
    ),
    (
        "rust/advanced-generics-where-clauses",
        r'''Show advanced generic patterns in Rust using where clauses. When are they necessary?''',
        r'''<think>
Where clauses are needed when bounds are complex: multiple traits, associated type constraints,
bounds on associated types, or higher-ranked trait bounds. They improve readability over
inline bounds. I should show several patterns: multi-trait bounds, bounds on associated types,
conditional impls, and the where clause making complex signatures readable.
This is advanced Rust generics usage.
</think>

`where` clauses move trait bounds out of the signature for readability and enable constraints that inline bounds can't express.

**Basic readability improvement:**

```rust
// Cluttered inline bounds
fn process<T: Clone + Send + Sync + std::fmt::Debug + serde::Serialize>(item: T) { .. }

// Clean with where clause
fn process<T>(item: T)
where
    T: Clone + Send + Sync + std::fmt::Debug + serde::Serialize,
{
    println!("{item:?}");
}
```

**Bounds on associated types:**

```rust
fn sum_values<I>(iter: I) -> i64
where
    I: Iterator<Item = i64>,
{
    iter.sum()
}

// More complex: associated type must implement a trait
fn print_all<I>(iter: I)
where
    I: Iterator,
    I::Item: std::fmt::Display,
{
    for item in iter {
        println!("{item}");
    }
}
```

**Conditional trait implementations:**

```rust
struct Wrapper<T>(T);

// Wrapper is Debug only if T is Debug
impl<T> std::fmt::Debug for Wrapper<T>
where
    T: std::fmt::Debug,
{
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "Wrapper({:?})", self.0)
    }
}

// Wrapper is Clone only if T is Clone
impl<T: Clone> Clone for Wrapper<T> {
    fn clone(&self) -> Self { Wrapper(self.0.clone()) }
}
```

**Higher-ranked trait bounds (HRTB):**

```rust
// F must work for ANY lifetime, not just one specific one
fn apply_to_ref<F>(f: F, data: &[u8])
where
    F: for<'a> Fn(&'a [u8]) -> &'a [u8],
{
    let result = f(data);
    println!("{}", result.len());
}
```

**Multiple type parameters with cross-constraints:**

```rust
fn convert_and_store<S, T>(source: S, store: &mut Vec<T>)
where
    S: IntoIterator,
    S::Item: TryInto<T>,
    <S::Item as TryInto<T>>::Error: std::fmt::Debug,
{
    for item in source {
        if let Ok(val) = item.try_into() {
            store.push(val);
        }
    }
}
```'''
    ),
    (
        "rust/associated-types-in-traits",
        r'''Explain associated types in Rust traits. How are they different from generic type parameters on traits?''',
        r'''<think>
Associated types define a type placeholder in a trait that each implementor chooses once.
Generic type parameters on traits allow multiple implementations for the same type.
The key difference: Iterator uses an associated type (Item) because a type should
have ONE Iterator impl, not many. Contrast with From<T> which is generic because
you can convert from many types. I'll show both patterns and when to choose which.
</think>

**Associated types** = each implementor sets the type **once**. **Generic parameters** = a type can implement the trait **multiple times** with different type args.

```rust
// Associated type — Vec<i32> has exactly ONE Iterator::Item = i32
trait Iterator {
    type Item;                // associated type
    fn next(&mut self) -> Option<Self::Item>;
}

// Generic parameter — String implements From<&str>, From<Vec<u8>>, etc.
trait From<T> {
    fn from(value: T) -> Self;
}
```

**Defining a trait with associated types:**

```rust
trait Graph {
    type Node: std::fmt::Debug;
    type Edge;

    fn nodes(&self) -> Vec<Self::Node>;
    fn edges(&self, node: &Self::Node) -> Vec<Self::Edge>;
    fn neighbors(&self, node: &Self::Node) -> Vec<Self::Node>;
}

struct CityMap;

impl Graph for CityMap {
    type Node = String;          // city name
    type Edge = (String, f64);   // (road name, distance)

    fn nodes(&self) -> Vec<String> { vec!["NYC".into(), "LA".into()] }
    fn edges(&self, _node: &String) -> Vec<(String, f64)> { vec![] }
    fn neighbors(&self, _node: &String) -> Vec<String> { vec![] }
}

// Using as a bound — clean, no extra generic params
fn print_nodes<G: Graph>(graph: &G) {
    for node in graph.nodes() {
        println!("{node:?}");
    }
}
```

**When to use which:**

| Pattern | Example | Reason |
|---------|---------|--------|
| Associated type | `Iterator::Item` | One natural choice per impl |
| Associated type | `Deref::Target` | `Vec<T>` always derefs to `[T]` |
| Generic param | `From<T>` | Multiple conversions for same type |
| Generic param | `Add<Rhs>` | `Matrix + Matrix` and `Matrix + Scalar` |

**Constraining associated types in bounds:**

```rust
fn sum_iter<I>(iter: I) -> i64
where
    I: Iterator<Item = i64>,  // constrain the associated type
{
    iter.sum()
}
```'''
    ),
    (
        "rust/generic-associated-types",
        r'''What are GATs (Generic Associated Types) in Rust? Show a practical use case.''',
        r'''<think>
GATs allow associated types to have their own generic parameters (lifetimes or types).
Stabilized in Rust 1.65. The classic use case is a lending iterator that borrows from self,
or a collection trait where the iterator type is parameterized by a lifetime.
Without GATs, you couldn't express "the associated type borrows from the implementor."
This is expert-level Rust. I'll show the lending iterator pattern.
</think>

**Generic Associated Types** (stabilized in Rust 1.65) let associated types have their own generic parameters — most commonly lifetime parameters. This enables patterns that were previously impossible.

**The problem without GATs:**

```rust
// We want a trait where the iterator borrows from the collection.
// Without GATs, there's no way to express this lifetime relationship.

// This DOESN'T work — 'a isn't connected to the implementor
// trait Collection {
//     type Iter: Iterator;  // can't express that Iter borrows from &self
// }
```

**With GATs — a lending collection trait:**

```rust
trait Collection {
    type Item;
    type Iter<'a>: Iterator<Item = &'a Self::Item> where Self: 'a;

    fn iter<'a>(&'a self) -> Self::Iter<'a>;
    fn push(&mut self, item: Self::Item);
}

impl<T> Collection for Vec<T> {
    type Item = T;
    type Iter<'a> = std::slice::Iter<'a, T> where T: 'a;

    fn iter<'a>(&'a self) -> Self::Iter<'a> {
        self.as_slice().iter()
    }

    fn push(&mut self, item: T) {
        Vec::push(self, item);
    }
}

// Generic function over any Collection
fn print_all<C: Collection>(col: &C)
where
    C::Item: std::fmt::Debug,
{
    for item in col.iter() {
        println!("{item:?}");
    }
}
```

**Lending iterator (borrows from self on each call):**

```rust
trait LendingIterator {
    type Item<'a> where Self: 'a;  // GAT: Item is parameterized by lifetime

    fn next(&mut self) -> Option<Self::Item<'_>>;
}

struct WindowsMut<'w, T> {
    data: &'w mut [T],
    pos: usize,
    size: usize,
}

impl<'w, T> LendingIterator for WindowsMut<'w, T> {
    type Item<'a> = &'a mut [T] where Self: 'a;

    fn next(&mut self) -> Option<&mut [T]> {
        if self.pos + self.size > self.data.len() { return None; }
        let start = self.pos;
        self.pos += 1;
        Some(&mut self.data[start..start + self.size])
    }
}
```

GATs are essential for async traits, lending iterators, and generic collection abstractions.'''
    ),
    (
        "rust/arc-mutex-shared-state",
        r'''How do I share mutable state between threads in Rust using Arc and Mutex?''',
        r'''<think>
Arc provides shared ownership across threads (atomic reference counting).
Mutex provides interior mutability with locking. Arc<Mutex<T>> is the standard pattern
for shared mutable state in concurrent Rust. I should show the pattern, proper lock handling,
and common pitfalls (deadlocks, holding locks across await points).
This is intermediate concurrent Rust.
</think>

`Arc<Mutex<T>>` is the standard pattern: `Arc` for shared ownership across threads, `Mutex` for exclusive access.

```rust
use std::sync::{Arc, Mutex};
use std::thread;

fn main() {
    let counter = Arc::new(Mutex::new(0u64));
    let mut handles = vec![];

    for _ in 0..10 {
        let counter = Arc::clone(&counter);  // cheap atomic ref count bump
        handles.push(thread::spawn(move || {
            for _ in 0..1000 {
                let mut guard = counter.lock().unwrap(); // blocks until lock available
                *guard += 1;
                // guard dropped here → lock released
            }
        }));
    }

    for h in handles {
        h.join().unwrap();
    }
    println!("final: {}", counter.lock().unwrap()); // 10000
}
```

**Async version with `tokio::sync::Mutex`:**

```rust
use std::sync::Arc;
use tokio::sync::Mutex;
use std::collections::HashMap;

type SharedState = Arc<Mutex<HashMap<String, String>>>;

async fn insert(state: SharedState, key: String, value: String) {
    let mut map = state.lock().await;  // async-aware, doesn't block the thread
    map.insert(key, value);
}

#[tokio::main]
async fn main() {
    let state: SharedState = Arc::new(Mutex::new(HashMap::new()));

    let mut tasks = vec![];
    for i in 0..5 {
        let s = state.clone();
        tasks.push(tokio::spawn(async move {
            insert(s, format!("key{i}"), format!("val{i}")).await;
        }));
    }
    futures::future::join_all(tasks).await;

    println!("{:?}", state.lock().await); // all 5 entries
}
```

**Pitfalls:**
- **Deadlock**: don't hold two locks in inconsistent order; keep critical sections short.
- **Poison**: `std::sync::Mutex` poisons on panic — use `.lock().unwrap()` or `.lock().unwrap_or_else(|e| e.into_inner())`.
- **Async**: use `tokio::sync::Mutex` if you hold the lock across `.await`; `std::sync::Mutex` is fine for short synchronous sections even in async code (and is faster).'''
    ),
    (
        "rust/rwlock-patterns",
        r'''When should I use RwLock instead of Mutex in Rust? Show a practical pattern.''',
        r'''<think>
RwLock allows multiple concurrent readers OR one exclusive writer.
It's better than Mutex when reads vastly outnumber writes.
I should show the read/write API, a real use case like a config store,
and the trade-off (RwLock has higher overhead per operation than Mutex,
so it only wins when read contention is high). Also mention writer starvation.
</think>

`RwLock` allows **many concurrent readers** or **one exclusive writer**. Use it when reads vastly outnumber writes.

```rust
use std::sync::{Arc, RwLock};
use std::thread;

struct ConfigStore {
    inner: RwLock<Config>,
}

#[derive(Clone, Debug)]
struct Config {
    max_connections: usize,
    timeout_ms: u64,
}

impl ConfigStore {
    fn new(cfg: Config) -> Arc<Self> {
        Arc::new(Self { inner: RwLock::new(cfg) })
    }

    // Many threads can read simultaneously
    fn get(&self) -> Config {
        self.inner.read().unwrap().clone()
    }

    // Only one thread can write; blocks all readers
    fn update<F: FnOnce(&mut Config)>(&self, f: F) {
        let mut guard = self.inner.write().unwrap();
        f(&mut guard);
    }
}

fn main() {
    let store = ConfigStore::new(Config { max_connections: 100, timeout_ms: 5000 });
    let mut handles = vec![];

    // 8 reader threads
    for i in 0..8 {
        let s = store.clone();
        handles.push(thread::spawn(move || {
            for _ in 0..100 {
                let cfg = s.get(); // concurrent reads, no blocking each other
                std::hint::black_box(cfg);
            }
            println!("reader {i} done");
        }));
    }

    // 1 writer thread (infrequent updates)
    let s = store.clone();
    handles.push(thread::spawn(move || {
        thread::sleep(std::time::Duration::from_millis(10));
        s.update(|cfg| cfg.max_connections = 200);
        println!("config updated");
    }));

    for h in handles { h.join().unwrap(); }
    println!("final: {:?}", store.get());
}
```

**Mutex vs RwLock decision:**

| Scenario | Choice |
|----------|--------|
| Short critical sections, mixed reads/writes | `Mutex` (lower overhead) |
| 95%+ reads, expensive read operations | `RwLock` |
| Async code | `tokio::sync::RwLock` |
| Single value, one writer, many readers | Consider `arc_swap` or `tokio::sync::watch` |

**Caveat:** `std::sync::RwLock` on some platforms can starve writers. For fairness guarantees, use `parking_lot::RwLock`.'''
    ),
    (
        "rust/crossbeam-scoped-threads",
        r'''Show me how crossbeam scoped threads work and why they're useful.''',
        r'''<think>
Crossbeam scoped threads (and std::thread::scope since Rust 1.63) let you spawn threads
that can borrow from the local stack without Arc. The scope guarantees all threads
join before it returns, so borrowing is safe. This eliminates the 'static requirement.
I should show the crossbeam version and the std version, and explain when to use which.
This is intermediate-advanced concurrent Rust.
</think>

Scoped threads can **borrow local variables** because the scope guarantees all threads join before returning. No `Arc` needed.

**`std::thread::scope` (stable since Rust 1.63):**

```rust
fn main() {
    let mut data = vec![1, 2, 3, 4, 5, 6, 7, 8];
    let chunk_size = data.len() / 4;

    let results: Vec<i32> = std::thread::scope(|s| {
        let handles: Vec<_> = data
            .chunks(chunk_size)
            .map(|chunk| {
                s.spawn(|| {
                    // Borrows `chunk` from the stack — no 'static needed!
                    chunk.iter().sum::<i32>()
                })
            })
            .collect();

        handles.into_iter().map(|h| h.join().unwrap()).collect()
    });

    println!("partial sums: {results:?}"); // [3, 7, 11, 15]
    println!("total: {}", results.iter().sum::<i32>()); // 36
}
```

**Crossbeam version (still useful for advanced features):**

```rust
use crossbeam::thread;

fn parallel_transform(input: &mut [f64]) {
    thread::scope(|s| {
        for chunk in input.chunks_mut(256) {
            s.spawn(move |_| {
                for val in chunk.iter_mut() {
                    *val = val.sqrt() * 2.0;
                }
            });
        }
    }).unwrap(); // all threads joined here
}

fn main() {
    let mut data: Vec<f64> = (1..=1000).map(|x| x as f64).collect();
    parallel_transform(&mut data);
    println!("first 5: {:?}", &data[..5]);
}
```

**Why scoped threads beat `Arc`:**
- **No allocation overhead** — borrow directly from the stack.
- **Mutable borrows** — split a `&mut [T]` across threads (impossible with `Arc`).
- **Simpler code** — no `Arc::clone()` boilerplate.

**When to still use `Arc` + `thread::spawn`:**
- When threads must outlive the current scope (background workers, daemon threads).
- When passing to async tasks that need `'static`.'''
    ),
    (
        "rust/rayon-parallel-iterators",
        r'''How do I use Rayon for parallel iterators in Rust? Show practical examples.''',
        r'''<think>
Rayon provides par_iter() and par_iter_mut() that distribute work across a thread pool.
Just change .iter() to .par_iter() and Rayon handles the rest.
It's work-stealing and has very low overhead for CPU-bound tasks.
I'll show basic parallel map/filter/reduce, par_sort, and par_bridge for custom iterators.
This is intermediate Rust — Rayon is the go-to for data parallelism.
</think>

Rayon turns sequential iterators into parallel ones with minimal code changes.

```toml
[dependencies]
rayon = "1.10"
```

**Basic parallel map + filter + reduce:**

```rust
use rayon::prelude::*;

fn main() {
    let numbers: Vec<u64> = (1..=10_000_000).collect();

    // Sequential: ~120ms
    let sum_seq: u64 = numbers.iter()
        .filter(|&&n| n % 3 == 0)
        .map(|&n| n * n)
        .sum();

    // Parallel: ~30ms (4 cores) — just change iter() to par_iter()
    let sum_par: u64 = numbers.par_iter()
        .filter(|&&n| n % 3 == 0)
        .map(|&n| n * n)
        .sum();

    assert_eq!(sum_seq, sum_par);
    println!("sum = {sum_par}");
}
```

**Parallel sort:**

```rust
use rayon::prelude::*;

fn main() {
    let mut data: Vec<f64> = (0..1_000_000)
        .map(|i| (i as f64 * 2.71828).sin())
        .collect();

    data.par_sort_unstable_by(|a, b| a.partial_cmp(b).unwrap());
    println!("min: {}, max: {}", data[0], data.last().unwrap());
}
```

**Parallel processing with mutable output:**

```rust
use rayon::prelude::*;

fn process_images(paths: &[String]) -> Vec<(String, usize)> {
    paths.par_iter()
        .map(|path| {
            let data = std::fs::read(path).unwrap_or_default();
            let checksum = data.iter().map(|&b| b as usize).sum();
            (path.clone(), checksum)
        })
        .collect()  // collects in order, not randomly
}
```

**Key points:**
- **Work-stealing** scheduler adapts to uneven workload automatically.
- **Composable**: `par_iter()` supports `map`, `filter`, `fold`, `reduce`, `for_each`, `flat_map`, `find_any`, etc.
- **Deterministic order**: `collect()` preserves input order; use `for_each` when order doesn't matter for best performance.
- **Overhead**: don't parallelize trivial work — Rayon has ~1μs overhead per task split. Aim for >10μs of work per element.'''
    ),
    (
        "rust/smart-pointers-box-rc-refcell",
        r'''Explain Box, Rc, and RefCell in Rust. When do I use each?''',
        r'''<think>
Box is heap allocation with single ownership. Rc is reference-counted shared ownership
(single-threaded). RefCell provides interior mutability with runtime borrow checking.
Rc<RefCell<T>> is the combination for shared mutable state in single-threaded code.
I should show each individually and then the combined pattern.
This is intermediate Rust that every developer needs to know.
</think>

Three smart pointers for different ownership needs:

**`Box<T>`** — heap allocation, single owner:

```rust
// Recursive types need indirection
enum List {
    Cons(i32, Box<List>),
    Nil,
}

// Large values on the heap to avoid stack copies
let big = Box::new([0u8; 1_000_000]);
```

**`Rc<T>`** — shared ownership, single-threaded, immutable:

```rust
use std::rc::Rc;

#[derive(Debug)]
struct SharedConfig {
    db_url: String,
}

let config = Rc::new(SharedConfig { db_url: "postgres://...".into() });
let c1 = Rc::clone(&config); // ref count: 2, NOT a deep clone
let c2 = Rc::clone(&config); // ref count: 3
println!("{:?}", c1); // all three see the same data
// dropped when last Rc goes out of scope
```

**`RefCell<T>`** — interior mutability with runtime borrow checking:

```rust
use std::cell::RefCell;

let data = RefCell::new(vec![1, 2, 3]);

// Borrow checking happens at RUNTIME, not compile time
{
    let mut v = data.borrow_mut(); // panics if already borrowed
    v.push(4);
}
println!("{:?}", data.borrow()); // [1, 2, 3, 4]
```

**Combined: `Rc<RefCell<T>>` — shared mutable state (single-threaded):**

```rust
use std::rc::Rc;
use std::cell::RefCell;

#[derive(Debug)]
struct Node {
    value: i32,
    children: Vec<Rc<RefCell<Node>>>,
}

fn main() {
    let leaf = Rc::new(RefCell::new(Node { value: 3, children: vec![] }));
    let branch = Rc::new(RefCell::new(Node {
        value: 1,
        children: vec![Rc::clone(&leaf)],
    }));

    // Mutate leaf through any handle
    leaf.borrow_mut().value = 42;
    println!("branch sees: {}", branch.borrow().children[0].borrow().value); // 42
}
```

| Type | Ownership | Mutability | Thread-safe | Cost |
|------|-----------|-----------|-------------|------|
| `Box<T>` | Single | Via `&mut` | Send + Sync | Heap alloc |
| `Rc<T>` | Shared | Immutable | No | Ref counting |
| `RefCell<T>` | Single | Runtime-checked | No | Runtime checks |
| `Arc<T>` | Shared | Immutable | Yes | Atomic ref counting |
| `Arc<Mutex<T>>` | Shared | Locked | Yes | Atomic + lock |'''
    ),
    (
        "rust/pin-unpin-self-referential",
        r'''Explain Pin and Unpin in Rust. Why do they exist and when do I need them?''',
        r'''<think>
Pin exists to support self-referential types, most notably async Futures.
When a future is polled, it may contain internal references to its own stack frame.
If the future is moved in memory, those references become dangling. Pin<&mut T> guarantees
the value won't be moved. Unpin is an auto-trait meaning "it's safe to move even when pinned."
Most types are Unpin; only self-referential types (like async state machines) are !Unpin.
This is expert-level Rust.
</think>

`Pin` prevents a value from being moved in memory. It exists primarily for **self-referential types** — notably async futures.

**The problem:**

```rust
// An async block compiles into a state machine struct like:
struct MyFuture {
    data: String,
    // This pointer points into `data` above — if the struct moves,
    // this pointer becomes dangling!
    slice: *const str,
}
// Moving MyFuture in memory would invalidate `slice`.
// Pin prevents this move.
```

**How Pin works:**

```rust
use std::pin::Pin;

// Pin<&mut T> guarantees T won't move for the lifetime of the borrow
// You can only get &mut T back if T: Unpin

fn poll_future(fut: Pin<&mut dyn Future<Output = ()>>) {
    // Can't call std::mem::swap or move the future out
    // The future's internal self-references remain valid
}
```

**Unpin = "safe to move even when pinned":**

```rust
// Most types auto-implement Unpin: integers, String, Vec, etc.
// Async futures generated by the compiler are !Unpin

fn example() {
    let mut x = String::from("hello");
    let pinned = Pin::new(&mut x); // works because String: Unpin
    // We can still get &mut String back
    let r: &mut String = Pin::into_inner(pinned);
}
```

**Practical: pinning a future manually:**

```rust
use std::pin::pin;
use tokio::time::{sleep, Duration};

async fn example() {
    let fut = sleep(Duration::from_secs(1));

    // pin! macro pins to the stack (fut is now Pin<&mut Sleep>)
    let pinned = pin!(fut);

    // Now safe to pass to APIs that require Pin<&mut F>
    pinned.await;
}
```

**When you encounter Pin:**
1. **Implementing `Future` manually** — `fn poll(self: Pin<&mut Self>, cx: &mut Context) -> Poll<T>`
2. **Storing futures in structs** — use `Pin<Box<dyn Future>>` or `#[pin_project]`
3. **99% of the time** — just use `async/await` and the compiler handles pinning for you.

```rust
// pin-project crate for custom types with pinned fields
use pin_project::pin_project;

#[pin_project]
struct TimedFuture<F> {
    #[pin]
    inner: F,          // pinned — won't move
    started: Instant,  // unpinned — normal field
}
```'''
    ),
    (
        "rust/iterator-combinators-custom",
        r'''Show me iterator combinators and how to implement a custom iterator in Rust.''',
        r'''<think>
Rust iterators are lazy and composable via combinators. I should show common combinators
(map, filter, flat_map, scan, take_while, zip, enumerate, chain) and then implement
a custom iterator for a practical type. The Iterator trait requires implementing next().
I'll show a Fibonacci iterator as a clean example.
This is intermediate Rust.
</think>

**Combinator chains — lazy, zero-cost after optimization:**

```rust
fn analyze(data: &[f64]) -> (f64, f64, usize) {
    let positives: Vec<f64> = data.iter()
        .copied()
        .filter(|&x| x > 0.0)
        .collect();

    let mean = positives.iter().sum::<f64>() / positives.len() as f64;

    let max = data.iter()
        .copied()
        .fold(f64::NEG_INFINITY, f64::max);

    let outliers = data.iter()
        .filter(|&&x| (x - mean).abs() > 2.0 * mean)
        .count();

    (mean, max, outliers)
}

// Chaining, zipping, and flat_mapping
fn interleave_and_index(a: &[&str], b: &[&str]) -> Vec<(usize, String)> {
    a.iter()
        .zip(b.iter())
        .flat_map(|(x, y)| [*x, *y])       // interleave
        .enumerate()
        .map(|(i, s)| (i, s.to_uppercase()))
        .collect()
}
```

**Custom iterator — Fibonacci:**

```rust
struct Fibonacci {
    a: u64,
    b: u64,
}

impl Fibonacci {
    fn new() -> Self { Fibonacci { a: 0, b: 1 } }
}

impl Iterator for Fibonacci {
    type Item = u64;

    fn next(&mut self) -> Option<u64> {
        let val = self.a;
        let next = self.a.checked_add(self.b)?; // returns None on overflow
        self.a = self.b;
        self.b = next;
        Some(val)
    }
}

fn main() {
    // Works with all combinators automatically
    let first_10: Vec<u64> = Fibonacci::new().take(10).collect();
    println!("{first_10:?}"); // [0, 1, 1, 2, 3, 5, 8, 13, 21, 34]

    let sum_under_1000: u64 = Fibonacci::new()
        .take_while(|&n| n < 1000)
        .filter(|n| n % 2 == 0)
        .sum();
    println!("sum of even fibs under 1000: {sum_under_1000}"); // 44
}
```

**Custom iterator with a reference (requires lifetime):**

```rust
struct ChunkIter<'a, T> {
    data: &'a [T],
    size: usize,
}

impl<'a, T> Iterator for ChunkIter<'a, T> {
    type Item = &'a [T];

    fn next(&mut self) -> Option<&'a [T]> {
        if self.data.is_empty() { return None; }
        let chunk_len = self.size.min(self.data.len());
        let (chunk, rest) = self.data.split_at(chunk_len);
        self.data = rest;
        Some(chunk)
    }
}
```

**Tip:** Implement `Iterator` to get 70+ methods for free: `map`, `filter`, `fold`, `sum`, `zip`, `chain`, `enumerate`, `peekable`, `skip`, `take`, `scan`, `flat_map`, `inspect`, and more.'''
    ),
    (
        "rust/closure-capture-semantics",
        r'''Explain Fn, FnMut, and FnOnce in Rust. How do closures capture variables?''',
        r'''<think>
Rust closures capture variables in three ways: by shared reference (&T → Fn),
by mutable reference (&mut T → FnMut), or by value/move (FnOnce).
The compiler infers the least restrictive trait. FnOnce is the supertype —
all closures implement it. Fn: FnMut: FnOnce in terms of hierarchy.
The move keyword forces capture by value.
I should show examples of each and when to use move.
</think>

Closures implement one or more of three traits based on how they capture variables:

```rust
// Fn — captures by shared reference, can be called repeatedly
let name = String::from("Alice");
let greet = || println!("Hello, {name}!");  // borrows &name
greet();
greet();  // fine — Fn can be called many times
println!("{name}");  // name still usable

// FnMut — captures by mutable reference, can be called repeatedly
let mut count = 0;
let mut increment = || { count += 1; };  // borrows &mut count
increment();
increment();
println!("{count}");  // 2

// FnOnce — captures by value (moves), can only be called once
let data = vec![1, 2, 3];
let consume = || drop(data);  // moves data into closure
consume();
// consume(); // ERROR: cannot call FnOnce again
// println!("{data:?}"); // ERROR: data was moved
```

**Trait hierarchy:** `Fn: FnMut: FnOnce` — every `Fn` is also `FnMut` and `FnOnce`.

**Using closures as parameters:**

```rust
// Accept the most general trait your usage requires
fn apply_once<F: FnOnce() -> String>(f: F) -> String { f() }
fn apply_mut<F: FnMut(i32) -> i32>(mut f: F, x: i32) -> i32 { f(x) }
fn apply_many<F: Fn(i32) -> i32>(f: F) -> Vec<i32> {
    (0..5).map(|x| f(x)).collect()
}

fn main() {
    let squares = apply_many(|x| x * x);
    println!("{squares:?}"); // [0, 1, 4, 9, 16]

    let mut total = 0;
    let accumulator = |x: i32| -> i32 { total += x; total };
    println!("{}", apply_mut(accumulator, 10)); // 10
}
```

**The `move` keyword — forces capture by value:**

```rust
use std::thread;

fn main() {
    let msg = String::from("hello");

    // Without `move`, this won't compile: the thread might outlive `msg`
    let handle = thread::spawn(move || {
        println!("{msg}");  // msg is moved into the closure
    });

    // println!("{msg}"); // ERROR: msg was moved
    handle.join().unwrap();
}
```

**Returning closures:**

```rust
fn make_adder(n: i32) -> impl Fn(i32) -> i32 {
    move |x| x + n  // must move `n` because it would be dropped otherwise
}

let add5 = make_adder(5);
println!("{}", add5(10)); // 15
```'''
    ),
    (
        "rust/advanced-pattern-matching",
        r'''Show advanced pattern matching in Rust: match guards, @ bindings, OR patterns, and nested destructuring.''',
        r'''<think>
Rust's pattern matching goes beyond simple enums. I need to cover:
- Match guards (if conditions on arms)
- @ bindings (bind a name while also matching a pattern)
- OR patterns (|)
- Nested destructuring (structs inside enums, tuples of tuples)
- Ranges in patterns
This is intermediate-advanced Rust. I'll show practical examples for each.
</think>

Rust's pattern matching is one of its most powerful features. Here are the advanced capabilities:

**Match guards — additional conditions:**

```rust
fn classify(value: i32) -> &'static str {
    match value {
        n if n < 0 => "negative",
        0 => "zero",
        n if n % 2 == 0 => "positive even",
        _ => "positive odd",
    }
}
```

**`@` bindings — capture while matching:**

```rust
enum Command {
    Move { x: i32, y: i32 },
    Resize(u32, u32),
    Quit,
}

fn handle(cmd: Command) {
    match cmd {
        // Bind the whole struct AND destructure it
        cmd @ Command::Move { x, y } if x.abs() + y.abs() > 100 => {
            println!("large move to ({x}, {y})");
        }
        Command::Move { x, y } => println!("move to ({x}, {y})"),

        // Bind value while constraining to a range
        Command::Resize(w @ 1..=1920, h @ 1..=1080) => {
            println!("valid resize: {w}x{h}");
        }
        Command::Resize(w, h) => println!("invalid size: {w}x{h}"),

        Command::Quit => println!("quit"),
    }
}
```

**OR patterns — multiple alternatives:**

```rust
fn is_vowel(c: char) -> bool {
    matches!(c, 'a' | 'e' | 'i' | 'o' | 'u' | 'A' | 'E' | 'I' | 'O' | 'U')
}

fn describe(code: u16) -> &'static str {
    match code {
        200 | 201 | 204 => "success",
        301 | 302 => "redirect",
        400 | 401 | 403 | 404 => "client error",
        500..=599 => "server error",
        _ => "unknown",
    }
}
```

**Nested destructuring:**

```rust
struct Point { x: f64, y: f64 }
enum Shape {
    Circle { center: Point, radius: f64 },
    Rect { top_left: Point, bottom_right: Point },
}

fn area(shape: &Shape) -> f64 {
    match shape {
        Shape::Circle { radius, .. } => std::f64::consts::PI * radius * radius,
        Shape::Rect {
            top_left: Point { x: x1, y: y1 },
            bottom_right: Point { x: x2, y: y2 },
        } => (x2 - x1).abs() * (y2 - y1).abs(),
    }
}
```

**`if let` chains (Rust 1.64+ let-else, nightly let-chains):**

```rust
// let-else: destructure or diverge
fn parse_pair(s: &str) -> Option<(i32, i32)> {
    let Some((a, b)) = s.split_once(',') else { return None };
    let Ok(x) = a.trim().parse::<i32>() else { return None };
    let Ok(y) = b.trim().parse::<i32>() else { return None };
    Some((x, y))
}
```

**Tuple + slice patterns:**

```rust
fn first_last(slice: &[i32]) -> String {
    match slice {
        [] => "empty".into(),
        [x] => format!("single: {x}"),
        [first, .., last] => format!("first: {first}, last: {last}"),
    }
}

assert_eq!(first_last(&[1, 2, 3, 4, 5]), "first: 1, last: 5");
```'''
    ),
]
