"""
Rust language training pairs - tokio, async/await, Futures, streams, select!
"""

pairs = [
    {
        "instruction": r'''<thinking>
The user wants a practical introduction to async Rust with tokio. I should show a basic async main, spawning tasks, and awaiting results. I will cover the tokio runtime setup and common patterns.
</thinking>

Show me the basics of async/await in Rust with tokio. Include spawning tasks and awaiting results.''',
        "output": r'''Tokio is the most popular async runtime for Rust. Here is a practical introduction covering task spawning, concurrency, and communication.

```rust
// Cargo.toml:
// [dependencies]
// tokio = { version = "1", features = ["full"] }

use tokio::time::{sleep, Duration};
use tokio::task::JoinHandle;

#[tokio::main]
async fn main() {
    // Basic async/await
    let result = fetch_data("users").await;
    println!("Got: {result}");

    // Spawn concurrent tasks
    let handles: Vec<JoinHandle<String>> = (0..3)
        .map(|i| {
            tokio::spawn(async move {
                sleep(Duration::from_millis(100 * (3 - i))).await;
                format!("task {i} done")
            })
        })
        .collect();

    // Await all tasks
    for h in handles {
        let msg = h.await.expect("task panicked");
        println!("{msg}");
    }

    // Run two futures concurrently, return when both complete
    let (a, b) = tokio::join!(
        fetch_data("posts"),
        fetch_data("comments"),
    );
    println!("Join results: {a}, {b}");

    // Channels for task communication
    let (tx, mut rx) = tokio::sync::mpsc::channel::<String>(32);
    tokio::spawn(async move {
        for i in 0..5 {
            tx.send(format!("msg-{i}")).await.unwrap();
        }
    });
    while let Some(msg) = rx.recv().await {
        println!("Received: {msg}");
    }
}

async fn fetch_data(resource: &str) -> String {
    // Simulate async I/O
    sleep(Duration::from_millis(50)).await;
    format!("{resource}: [data]")
}
```

Key points:
- `#[tokio::main]` sets up the multi-threaded runtime
- `tokio::spawn` creates a new task on the runtime
- `tokio::join!` runs futures concurrently (not sequentially)
- Spawned tasks must be `Send + 'static` since they may run on any thread'''
    },
    {
        "instruction": r'''How do I use tokio::select! to race multiple async operations in Rust? Show timeout and cancellation patterns.''',
        "output": r'''`tokio::select!` waits on multiple futures simultaneously and executes the branch of whichever completes first. The other futures are dropped (cancelled).

```rust
use tokio::time::{sleep, Duration, timeout};
use tokio::sync::mpsc;

#[tokio::main]
async fn main() {
    // Pattern 1: Timeout using select!
    tokio::select! {
        result = slow_operation() => {
            println!("Operation completed: {result}");
        }
        _ = sleep(Duration::from_secs(2)) => {
            println!("Operation timed out after 2s");
        }
    }

    // Pattern 2: Using the timeout utility (simpler for basic cases)
    match timeout(Duration::from_secs(1), slow_operation()).await {
        Ok(val) => println!("Got: {val}"),
        Err(_) => println!("Timed out"),
    }

    // Pattern 3: Select over a channel and a shutdown signal
    let (tx, mut rx) = mpsc::channel::<String>(10);
    let (shutdown_tx, mut shutdown_rx) = mpsc::channel::<()>(1);

    // Producer
    let producer = tokio::spawn(async move {
        for i in 0..100 {
            if tx.send(format!("item-{i}")).await.is_err() {
                break;
            }
            sleep(Duration::from_millis(50)).await;
        }
    });

    // Shutdown after 200ms
    tokio::spawn(async move {
        sleep(Duration::from_millis(200)).await;
        let _ = shutdown_tx.send(()).await;
    });

    // Consumer with graceful shutdown
    loop {
        tokio::select! {
            Some(msg) = rx.recv() => {
                println!("Processing: {msg}");
            }
            _ = shutdown_rx.recv() => {
                println!("Shutdown signal received");
                break;
            }
        }
    }

    producer.abort(); // cancel the producer task
    println!("Clean shutdown complete");
}

async fn slow_operation() -> String {
    sleep(Duration::from_secs(5)).await;
    "done".to_string()
}
```

Important: when one `select!` branch completes, the other futures are dropped. If a future holds state you need to preserve, use `tokio::pin!` and pass `&mut future` so it is not consumed on each loop iteration.'''
    },
    {
        "instruction": r'''<thinking>
The user wants to understand async streams in Rust. I should show how to create and consume streams using tokio and tokio-stream, including practical patterns like buffered processing.
</thinking>

Show how to work with async streams in Rust using tokio-stream. Include creating, transforming, and consuming streams.''',
        "output": r'''Async streams yield values over time -- an async version of `Iterator`. The `tokio-stream` crate provides utilities for them.

```rust
// Cargo.toml:
// [dependencies]
// tokio = { version = "1", features = ["full"] }
// tokio-stream = "0.1"
// async-stream = "0.3"

use tokio_stream::{self as stream, StreamExt};
use async_stream::stream;
use std::time::Duration;

#[tokio::main]
async fn main() {
    // From an iterator
    let mut numbers = stream::iter(vec![1, 2, 3, 4, 5]);
    while let Some(n) = numbers.next().await {
        println!("Got: {n}");
    }

    // From the async-stream macro (supports yield + await)
    let ticker = stream! {
        for i in 0..5 {
            tokio::time::sleep(Duration::from_millis(100)).await;
            yield format!("tick-{i}");
        }
    };
    tokio_stream::pin_mut!(ticker);
    while let Some(val) = ticker.next().await {
        println!("{}", val.to_uppercase());
    }

    // Filter + map + take -- same adapters as Iterator
    let squares = stream::iter(1..=20)
        .filter(|x| x % 2 == 0)
        .map(|x| x * x)
        .take(5);
    tokio_stream::pin_mut!(squares);
    while let Some(val) = squares.next().await {
        print!("{val} ");
    }
    println!();

    // Paginated API consumer
    let pages = fetch_pages("https://api.example.com/items");
    tokio_stream::pin_mut!(pages);
    let mut total = 0;
    while let Some(items) = pages.next().await {
        total += items.len();
    }
    println!("Total items: {total}");
}

fn fetch_pages(url: &str) -> impl tokio_stream::Stream<Item = Vec<String>> + '_ {
    stream! {
        for page in 1..=3 {
            tokio::time::sleep(Duration::from_millis(50)).await;
            yield (0..10).map(|i| format!("{url}?p={page}&i={i}")).collect();
        }
    }
}
```

Key patterns:
- `stream::iter()` wraps a sync iterator into a stream
- `async_stream::stream!` macro creates streams with yield
- `StreamExt` gives `next()`, `filter()`, `map()`, `take()`
- Pin streams with `tokio_stream::pin_mut!` before consuming'''
    },
    {
        "instruction": r'''How do I implement the Future trait manually in Rust? Show a simple custom future.''',
        "output": r'''Implementing `Future` manually gives you full control over polling. Here is a timer future.

```rust
use std::future::Future;
use std::pin::Pin;
use std::task::{Context, Poll};
use std::time::{Duration, Instant};

struct Delay { when: Instant }

impl Delay {
    fn new(dur: Duration) -> Self {
        Delay { when: Instant::now() + dur }
    }
}

impl Future for Delay {
    type Output = String;

    fn poll(self: Pin<&mut Self>, cx: &mut Context<'_>) -> Poll<Self::Output> {
        if Instant::now() >= self.when {
            Poll::Ready("timer fired".to_string())
        } else {
            // Spawn a thread to wake us after the deadline.
            // Real impls register with a timer wheel instead.
            let waker = cx.waker().clone();
            let when = self.when;
            std::thread::spawn(move || {
                let now = Instant::now();
                if now < when {
                    std::thread::sleep(when - now);
                }
                waker.wake();
            });
            Poll::Pending
        }
    }
}

#[tokio::main]
async fn main() {
    let msg = Delay::new(Duration::from_millis(100)).await;
    println!("{msg}");
}
```

Key concepts:
- `poll()` returns `Poll::Ready(value)` when done, `Poll::Pending` when not yet ready
- You MUST call `cx.waker().wake()` to schedule a re-poll -- otherwise the future hangs forever
- `Pin<&mut Self>` ensures self-referential futures stay in place in memory
- Most Rust code uses async/await sugar; manual Future impl is mainly for library authors building combinators or custom I/O primitives'''
    },
    {
        "instruction": r'''Show how to build a concurrent web scraper in Rust using tokio with rate limiting and error handling.''',
        "output": r'''Here is a concurrent scraper using tokio semaphores for rate limiting.

```rust
use tokio::sync::Semaphore;
use tokio::time::{sleep, Duration};
use std::sync::Arc;

#[derive(Debug)]
struct Page { url: String, body_len: usize }

async fn fetch_page(url: &str) -> Result<Page, String> {
    sleep(Duration::from_millis((url.len() as u64 * 7) % 200)).await;
    if url.contains("fail") {
        return Err(format!("HTTP 500: {url}"));
    }
    Ok(Page { url: url.to_string(), body_len: 1024 + url.len() * 100 })
}

#[tokio::main]
async fn main() {
    let urls = vec![
        "https://example.com/page/1",
        "https://example.com/page/2",
        "https://example.com/page/fail",
        "https://example.com/page/3",
        "https://example.com/page/4",
    ];

    // Semaphore limits concurrency to 3 simultaneous requests
    let sem = Arc::new(Semaphore::new(3));
    let mut handles = Vec::new();

    for url in urls {
        let sem = Arc::clone(&sem);
        let url = url.to_string();
        handles.push(tokio::spawn(async move {
            let _permit = sem.acquire().await.unwrap();
            sleep(Duration::from_millis(50)).await; // rate limit

            // Retry up to 3 times
            let mut attempts = 0;
            loop {
                attempts += 1;
                match fetch_page(&url).await {
                    Ok(page) => return Ok(page),
                    Err(e) if attempts < 3 => {
                        eprintln!("Retry {attempts} for {url}: {e}");
                        sleep(Duration::from_millis(100)).await;
                    }
                    Err(e) => return Err(e),
                }
            }
        }));
    }

    let (mut ok, mut fail) = (0u32, 0u32);
    for h in handles {
        match h.await.unwrap() {
            Ok(p) => { println!("[OK] {} -- {} bytes", p.url, p.body_len); ok += 1; }
            Err(e) => { eprintln!("[FAIL] {e}"); fail += 1; }
        }
    }
    println!("Done: {ok} ok, {fail} failed");
}
```

This pattern gives you controlled concurrency (semaphore), rate limiting (sleep between requests), and retry logic -- all composable with async/await.'''
    },
]
