"""Rust — async/tokio, traits, error handling, and ownership patterns."""

PAIRS = [
    (
        "rust/async-tokio",
        "Show Rust async patterns with Tokio: spawning tasks, channels, select, and graceful shutdown.",
        '''Rust async with Tokio:

```rust
use std::time::Duration;
use tokio::sync::{mpsc, oneshot, Semaphore};
use tokio::time;
use tokio::signal;
use std::sync::Arc;

// --- Basic async with Tokio ---

#[tokio::main]
async fn main() {
    // Spawn concurrent tasks
    let handle1 = tokio::spawn(async {
        fetch_data("https://api.example.com/users").await
    });

    let handle2 = tokio::spawn(async {
        fetch_data("https://api.example.com/orders").await
    });

    // Await both results
    let (users, orders) = tokio::join!(handle1, handle2);
    println!("Users: {:?}, Orders: {:?}", users.unwrap(), orders.unwrap());
}


// --- Channel patterns ---

async fn producer_consumer() {
    // Multi-producer, single-consumer
    let (tx, mut rx) = mpsc::channel::<String>(100);

    // Spawn producers
    for i in 0..3 {
        let tx = tx.clone();
        tokio::spawn(async move {
            for j in 0..10 {
                let msg = format!("producer-{}: message-{}", i, j);
                if tx.send(msg).await.is_err() {
                    break; // Receiver dropped
                }
            }
        });
    }
    drop(tx); // Drop original sender so rx eventually returns None

    // Consume
    while let Some(msg) = rx.recv().await {
        println!("Received: {}", msg);
    }
}


// --- Select pattern ---

async fn select_example(mut rx: mpsc::Receiver<String>) {
    let mut interval = time::interval(Duration::from_secs(5));

    loop {
        tokio::select! {
            // Receive message
            Some(msg) = rx.recv() => {
                println!("Got: {}", msg);
            }
            // Periodic tick
            _ = interval.tick() => {
                println!("Heartbeat");
            }
            // Shutdown signal
            _ = signal::ctrl_c() => {
                println!("Shutting down...");
                break;
            }
        }
    }
}


// --- Semaphore (limit concurrency) ---

async fn fetch_with_limit(urls: Vec<String>, max_concurrent: usize) -> Vec<String> {
    let semaphore = Arc::new(Semaphore::new(max_concurrent));
    let mut handles = vec![];

    for url in urls {
        let sem = semaphore.clone();
        let handle = tokio::spawn(async move {
            let _permit = sem.acquire().await.unwrap();
            fetch_data(&url).await
        });
        handles.push(handle);
    }

    let mut results = vec![];
    for handle in handles {
        results.push(handle.await.unwrap());
    }
    results
}


// --- Graceful shutdown pattern ---

async fn run_server() -> Result<(), Box<dyn std::error::Error>> {
    let (shutdown_tx, shutdown_rx) = oneshot::channel::<()>();

    // Spawn server
    let server = tokio::spawn(async move {
        // Run until shutdown signal
        tokio::select! {
            _ = async {
                // Server loop
                loop {
                    handle_connection().await;
                }
            } => {}
            _ = shutdown_rx => {
                println!("Server shutting down gracefully");
            }
        }
    });

    // Wait for Ctrl+C
    signal::ctrl_c().await?;
    println!("Received Ctrl+C");

    // Signal server to stop
    let _ = shutdown_tx.send(());

    // Wait for server with timeout
    tokio::time::timeout(Duration::from_secs(30), server).await??;

    Ok(())
}


// --- Timeout and retry ---

async fn fetch_with_retry(url: &str, max_retries: u32) -> Result<String, String> {
    let mut last_err = String::new();

    for attempt in 0..=max_retries {
        if attempt > 0 {
            let delay = Duration::from_millis(100 * 2u64.pow(attempt - 1));
            time::sleep(delay).await;
        }

        match time::timeout(Duration::from_secs(5), fetch_data(url)).await {
            Ok(result) => return Ok(result),
            Err(_) => last_err = "timeout".to_string(),
        }
    }

    Err(format!("Failed after {} retries: {}", max_retries, last_err))
}
```

Tokio async patterns:
1. **`tokio::join!`** — await multiple futures concurrently
2. **`mpsc::channel`** — async multi-producer, single-consumer channels
3. **`tokio::select!`** — race multiple async operations, handle first to complete
4. **`Semaphore`** — limit concurrent tasks to prevent resource exhaustion
5. **Graceful shutdown** — `oneshot` channel + `ctrl_c()` for clean teardown'''
    ),
    (
        "rust/traits-generics",
        "Show Rust trait patterns: trait objects, default implementations, associated types, and trait bounds.",
        '''Rust trait patterns:

```rust
use std::fmt;
use std::io;

// --- Trait definition with default methods ---

trait Repository {
    type Item;
    type Error;

    fn get(&self, id: &str) -> Result<Self::Item, Self::Error>;
    fn save(&mut self, item: &Self::Item) -> Result<(), Self::Error>;
    fn delete(&mut self, id: &str) -> Result<(), Self::Error>;

    // Default implementation
    fn exists(&self, id: &str) -> bool {
        self.get(id).is_ok()
    }
}


// --- Implementation ---

#[derive(Debug, Clone)]
struct User {
    id: String,
    name: String,
    email: String,
}

struct InMemoryUserRepo {
    users: std::collections::HashMap<String, User>,
}

impl Repository for InMemoryUserRepo {
    type Item = User;
    type Error = RepoError;

    fn get(&self, id: &str) -> Result<User, RepoError> {
        self.users.get(id)
            .cloned()
            .ok_or(RepoError::NotFound(id.to_string()))
    }

    fn save(&mut self, user: &User) -> Result<(), RepoError> {
        self.users.insert(user.id.clone(), user.clone());
        Ok(())
    }

    fn delete(&mut self, id: &str) -> Result<(), RepoError> {
        self.users.remove(id)
            .map(|_| ())
            .ok_or(RepoError::NotFound(id.to_string()))
    }
}


// --- Trait bounds and generics ---

fn print_all<R>(repo: &R, ids: &[&str])
where
    R: Repository,
    R::Item: fmt::Debug,
{
    for id in ids {
        match repo.get(id) {
            Ok(item) => println!("{:?}", item),
            Err(_) => println!("{} not found", id),
        }
    }
}


// --- Trait objects (dynamic dispatch) ---

type DynRepo = Box<dyn Repository<Item = User, Error = RepoError>>;

fn create_repo(backend: &str) -> DynRepo {
    match backend {
        "memory" => Box::new(InMemoryUserRepo {
            users: std::collections::HashMap::new(),
        }),
        // "postgres" => Box::new(PostgresUserRepo::new()),
        _ => panic!("Unknown backend: {}", backend),
    }
}


// --- Multiple trait bounds ---

fn process<T>(item: T)
where
    T: fmt::Display + fmt::Debug + Clone + Send + 'static,
{
    println!("Display: {}", item);
    println!("Debug: {:?}", item);
    let _clone = item.clone();
}


// --- Supertraits ---

trait Serializable: fmt::Debug + Clone {
    fn to_bytes(&self) -> Vec<u8>;
}


// --- Extension traits ---

trait StringExt {
    fn truncate_words(&self, max_words: usize) -> String;
    fn is_valid_email(&self) -> bool;
}

impl StringExt for str {
    fn truncate_words(&self, max_words: usize) -> String {
        self.split_whitespace()
            .take(max_words)
            .collect::<Vec<_>>()
            .join(" ")
    }

    fn is_valid_email(&self) -> bool {
        let parts: Vec<&str> = self.split('@').collect();
        parts.len() == 2 && !parts[0].is_empty() && parts[1].contains('.')
    }
}


// --- Blanket implementations ---

trait ToJson {
    fn to_json(&self) -> String;
}

// Implement for anything that implements Debug
impl<T: fmt::Debug> ToJson for T {
    fn to_json(&self) -> String {
        format!("{:?}", self)
    }
}


// --- Newtype pattern for orphan rule ---

struct Email(String);

impl fmt::Display for Email {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        // Mask email for display
        let parts: Vec<&str> = self.0.split('@').collect();
        if parts.len() == 2 {
            write!(f, "{}...@{}", &parts[0][..2], parts[1])
        } else {
            write!(f, "***")
        }
    }
}
```

Rust trait patterns:
1. **Associated types** — `type Item` avoids extra generic params on callers
2. **Default methods** — provide behavior that implementations can override
3. **Trait objects** — `Box<dyn Trait>` for dynamic dispatch (runtime polymorphism)
4. **Extension traits** — add methods to existing types (`impl MyTrait for str`)
5. **Blanket impls** — `impl<T: Debug> MyTrait for T` covers all matching types'''
    ),
    (
        "rust/error-handling",
        "Show Rust error handling patterns: custom errors, the ? operator, thiserror, and anyhow.",
        '''Rust error handling:

```rust
use std::fmt;
use std::io;
use std::num::ParseIntError;

// --- Custom error type (manual) ---

#[derive(Debug)]
enum AppError {
    NotFound { resource: String, id: String },
    Validation(String),
    Database(String),
    Io(io::Error),
    Parse(ParseIntError),
    Internal(String),
}

impl fmt::Display for AppError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            AppError::NotFound { resource, id } =>
                write!(f, "{} with id '{}' not found", resource, id),
            AppError::Validation(msg) => write!(f, "Validation error: {}", msg),
            AppError::Database(msg) => write!(f, "Database error: {}", msg),
            AppError::Io(err) => write!(f, "IO error: {}", err),
            AppError::Parse(err) => write!(f, "Parse error: {}", err),
            AppError::Internal(msg) => write!(f, "Internal error: {}", msg),
        }
    }
}

impl std::error::Error for AppError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            AppError::Io(err) => Some(err),
            AppError::Parse(err) => Some(err),
            _ => None,
        }
    }
}

// Automatic conversion with From
impl From<io::Error> for AppError {
    fn from(err: io::Error) -> Self {
        AppError::Io(err)
    }
}

impl From<ParseIntError> for AppError {
    fn from(err: ParseIntError) -> Self {
        AppError::Parse(err)
    }
}


// --- Using thiserror (derive macro) ---

// #[derive(Debug, thiserror::Error)]
// enum AppError {
//     #[error("{resource} with id '{id}' not found")]
//     NotFound { resource: String, id: String },
//
//     #[error("Validation error: {0}")]
//     Validation(String),
//
//     #[error("Database error: {0}")]
//     Database(String),
//
//     #[error(transparent)]
//     Io(#[from] io::Error),
//
//     #[error(transparent)]
//     Parse(#[from] ParseIntError),
// }


// --- The ? operator ---

fn read_config(path: &str) -> Result<Config, AppError> {
    let content = std::fs::read_to_string(path)?;  // io::Error -> AppError
    let port: u16 = content.trim().parse()?;        // ParseIntError -> AppError
    Ok(Config { port })
}


// --- Result combinators ---

fn process_user(id: &str) -> Result<String, AppError> {
    let user = find_user(id)
        .map_err(|_| AppError::NotFound {
            resource: "User".into(),
            id: id.into(),
        })?;

    let name = user.name
        .ok_or_else(|| AppError::Validation("User has no name".into()))?;

    Ok(format!("Hello, {}!", name))
}


// --- anyhow for application code ---

// use anyhow::{Context, Result, bail, ensure};
//
// fn load_config(path: &str) -> Result<Config> {
//     let content = std::fs::read_to_string(path)
//         .context("Failed to read config file")?;   // Adds context to error
//
//     let config: Config = toml::from_str(&content)
//         .context("Failed to parse config TOML")?;
//
//     ensure!(config.port > 0, "Port must be positive"); // Like assert but returns Err
//
//     if config.host.is_empty() {
//         bail!("Host cannot be empty"); // Return Err immediately
//     }
//
//     Ok(config)
// }


// --- Error handling in main ---

fn main() -> Result<(), AppError> {
    let config = read_config("config.txt")?;
    println!("Running on port {}", config.port);
    Ok(())
}


// --- Type alias for common Results ---

type AppResult<T> = Result<T, AppError>;

fn get_user(id: &str) -> AppResult<User> {
    // ...
    Ok(User { id: id.to_string(), name: Some("Alice".to_string()) })
}


// --- Collecting Results ---

fn parse_all(inputs: &[&str]) -> Result<Vec<i32>, ParseIntError> {
    inputs.iter()
        .map(|s| s.parse::<i32>())
        .collect()  // Short-circuits on first error
}

fn parse_all_keep_errors(inputs: &[&str]) -> (Vec<i32>, Vec<String>) {
    let (oks, errs): (Vec<_>, Vec<_>) = inputs.iter()
        .map(|s| s.parse::<i32>())
        .partition(Result::is_ok);

    (
        oks.into_iter().map(Result::unwrap).collect(),
        errs.into_iter().map(|e| e.unwrap_err().to_string()).collect(),
    )
}
```

Rust error handling:
1. **`?` operator** — propagate errors with automatic `From` conversion
2. **`thiserror`** — derive `Error`/`Display` for library error types
3. **`anyhow`** — `Result<T>` with context chaining for application code
4. **`map_err()`** — convert between error types at call boundaries
5. **`.collect::<Result<Vec<_>, _>>()`** — collect iterator of Results, short-circuit on error'''
    ),
]
"""
