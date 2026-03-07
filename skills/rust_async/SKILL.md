# Rust Async Patterns (Tokio)

## Core Setup
```rust
#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Multi-threaded runtime by default
    // Use #[tokio::main(flavor = "current_thread")] for single-threaded
    Ok(())
}
```

## Spawning Tasks
```rust
use tokio::task;

// Fire-and-forget
task::spawn(async move { do_work().await });

// Get result back
let handle = task::spawn(async move { compute().await });
let result = handle.await??;  // First ? = JoinError, second ? = your error

// CPU-heavy work — don't block the async runtime
let result = task::spawn_blocking(move || expensive_sync_computation()).await?;
```

## Concurrency Patterns
```rust
use tokio::sync::{Semaphore, Mutex, RwLock, mpsc, oneshot};
use std::sync::Arc;

// Bounded concurrency (e.g., max 10 parallel requests)
let sem = Arc::new(Semaphore::new(10));
let mut handles = vec![];
for url in urls {
    let permit = sem.clone().acquire_owned().await?;
    handles.push(task::spawn(async move {
        let result = fetch(url).await;
        drop(permit);  // Release when done
        result
    }));
}
let results: Vec<_> = futures::future::join_all(handles).await;

// Channel (producer-consumer)
let (tx, mut rx) = mpsc::channel(100);  // Bounded buffer
task::spawn(async move {
    while let Some(msg) = rx.recv().await {
        process(msg).await;
    }
});
tx.send(item).await?;

// Select — first completion wins
tokio::select! {
    result = future_a => handle_a(result),
    result = future_b => handle_b(result),
    _ = tokio::time::sleep(Duration::from_secs(5)) => timeout(),
}
```

## Error Handling Chain
```rust
use thiserror::Error;

#[derive(Error, Debug)]
enum AppError {
    #[error("network: {0}")]
    Network(#[from] reqwest::Error),
    #[error("parse: {0}")]
    Parse(#[from] serde_json::Error),
    #[error("io: {0}")]
    Io(#[from] std::io::Error),
    #[error("{0}")]
    Custom(String),
}

// Use anyhow for applications, thiserror for libraries
// ? operator auto-converts via From trait
async fn fetch_json<T: DeserializeOwned>(url: &str) -> Result<T, AppError> {
    let body = reqwest::get(url).await?.text().await?;
    Ok(serde_json::from_str(&body)?)
}
```

## Timeouts and Cancellation
```rust
use tokio::time::{timeout, Duration};
use tokio_util::sync::CancellationToken;

// Timeout a single operation
let result = timeout(Duration::from_secs(30), fetch(url)).await
    .map_err(|_| AppError::Custom("timeout".into()))??;

// Graceful shutdown with cancellation token
let token = CancellationToken::new();
let child_token = token.child_token();
task::spawn(async move {
    tokio::select! {
        _ = child_token.cancelled() => { /* cleanup */ },
        _ = run_server() => {},
    }
});
// Later: token.cancel();
```

## Key Gotchas
- **Never block in async**: No `std::thread::sleep`, `Mutex::lock` (std), or heavy CPU. Use `spawn_blocking`.
- **Send + 'static**: Spawned tasks require `Send + 'static`. Use `Arc` for shared data.
- **Mutex choice**: `tokio::sync::Mutex` if held across `.await`, `std::sync::Mutex` if lock is brief and no await inside.
- **Buffered streams**: Use `futures::stream::BufferedUnordered` for parallel iteration with backpressure.
- **Pin**: `Box::pin(future)` when you need to store or return `dyn Future`.
