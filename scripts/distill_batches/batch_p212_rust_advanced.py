"""Rust advanced patterns — ownership/lifetimes, async Tokio, error handling, traits/generics, macros."""

PAIRS = [
    (
        "rust/ownership-lifetimes",
        "Explain Rust advanced ownership and lifetimes including borrowing rules, lifetime elision, lifetime bounds, and self-referential patterns.",
        '''Rust advanced ownership and lifetime patterns:

```rust
// --- Lifetime fundamentals and elision rules ---

// Elision rule 1: Each reference parameter gets its own lifetime
// Elision rule 2: If exactly one input lifetime, it applies to all outputs
// Elision rule 3: If &self or &mut self, that lifetime applies to all outputs

// Explicit lifetimes when elision rules are insufficient
fn longest<'a>(x: &'a str, y: &'a str) -> &'a str {
    if x.len() > y.len() { x } else { y }
}

// Multiple lifetimes — output tied to specific input
fn first_word<'a, 'b>(text: &'a str, _prefix: &'b str) -> &'a str {
    text.split_whitespace().next().unwrap_or(text)
}

// Lifetime bounds on structs
#[derive(Debug)]
struct Excerpt<'a> {
    text: &'a str,
    line: usize,
}

impl<'a> Excerpt<'a> {
    // Elision rule 3: &self lifetime flows to output
    fn text(&self) -> &str {
        self.text
    }

    // Explicit: output borrows from the passed-in string, not self
    fn combine<'b>(&self, other: &'b str) -> String {
        format!("{} {}", self.text, other)
    }
}

// Lifetime bounds on traits
trait Parser<'input> {
    fn parse(&self, input: &'input str) -> Result<Vec<&'input str>, String>;
}

struct CSVParser {
    delimiter: char,
}

impl<'input> Parser<'input> for CSVParser {
    fn parse(&self, input: &'input str) -> Result<Vec<&'input str>, String> {
        Ok(input.split(self.delimiter).collect())
    }
}

// Static lifetime — data lives for entire program
fn get_greeting() -> &'static str {
    "Hello, world!" // String literal: 'static
}

// Lifetime with generics
fn find_item<'a, T: PartialEq>(haystack: &'a [T], needle: &T) -> Option<&'a T> {
    haystack.iter().find(|item| *item == needle)
}
```

```rust
// --- Advanced borrowing patterns ---

use std::collections::HashMap;

// Interior mutability with RefCell (runtime borrow checking)
use std::cell::RefCell;

struct CachedValue<T: Clone> {
    value: T,
    cache: RefCell<Option<String>>,
}

impl<T: Clone + std::fmt::Display> CachedValue<T> {
    fn new(value: T) -> Self {
        CachedValue {
            value,
            cache: RefCell::new(None),
        }
    }

    // &self but mutates cache internally
    fn formatted(&self) -> String {
        let mut cache = self.cache.borrow_mut();
        if let Some(ref cached) = *cache {
            return cached.clone();
        }
        let result = format!("Value: {}", self.value);
        *cache = Some(result.clone());
        result
    }
}

// Cow (Clone on Write) — avoid allocation when possible
use std::borrow::Cow;

fn normalize_name(name: &str) -> Cow<'_, str> {
    if name.chars().all(|c| c.is_alphanumeric() || c == ' ') {
        Cow::Borrowed(name) // No allocation needed
    } else {
        let cleaned: String = name
            .chars()
            .filter(|c| c.is_alphanumeric() || *c == ' ')
            .collect();
        Cow::Owned(cleaned) // Had to allocate
    }
}

// Entry API — avoids double lookup in HashMaps
fn word_count(text: &str) -> HashMap<&str, usize> {
    let mut counts = HashMap::new();
    for word in text.split_whitespace() {
        // entry() borrows the map mutably, providing get-or-insert
        *counts.entry(word).or_insert(0) += 1;
    }
    counts
}

// Reborrowing — &mut T can be temporarily shared as &T
fn process(data: &mut Vec<i32>) {
    // Implicitly reborrows &mut Vec as &Vec for len()
    let len = data.len();   // &Vec<i32> — shared borrow
    data.push(len as i32);  // &mut Vec<i32> — exclusive borrow resumes
}

// Split borrows — borrow different fields simultaneously
struct Database {
    users: Vec<String>,
    logs: Vec<String>,
}

impl Database {
    fn update(&mut self) {
        // OK: borrowing different fields simultaneously
        let users = &self.users;
        let logs = &mut self.logs;
        for user in users {
            logs.push(format!("Updated: {}", user));
        }
    }
}
```

```rust
// --- Higher-Ranked Trait Bounds (HRTBs) and advanced lifetimes ---

// HRTB: "for all lifetimes 'a"
fn apply_to_str<F>(f: F, s: &str) -> String
where
    F: for<'a> Fn(&'a str) -> &'a str,
{
    f(s).to_string()
}

// Type alias for complex lifetime-bound closures
type Validator<'a> = Box<dyn Fn(&'a str) -> bool + 'a>;

fn create_validator<'a>(min_len: usize) -> Validator<'a> {
    Box::new(move |s: &str| s.len() >= min_len)
}

// Phantom lifetime — struct does not hold reference but is
// conceptually tied to a lifetime
use std::marker::PhantomData;

struct Token<'db> {
    id: u64,
    _marker: PhantomData<&'db ()>,
}

struct Database2 {
    next_id: u64,
}

impl Database2 {
    fn create_token(&mut self) -> Token<'_> {
        let id = self.next_id;
        self.next_id += 1;
        Token {
            id,
            _marker: PhantomData,
        }
    }

    fn use_token(&self, token: &Token<'_>) {
        println!("Using token {}", token.id);
    }
}

// Subtyping: 'long: 'short means 'long outlives 'short
fn coerce_lifetime<'long: 'short, 'short>(
    long_ref: &'long str,
) -> &'short str {
    long_ref // 'long can be used where 'short is expected
}

fn main() {
    let text = String::from("Hello, Rust lifetimes!");
    let excerpt = Excerpt {
        text: &text,
        line: 1,
    };
    println!("{:?}", excerpt);

    let name = normalize_name("Hello World!!!");
    println!("Normalized: {}", name);

    let mut db = Database2 { next_id: 1 };
    let token = db.create_token();
    db.use_token(&token);
}
```

Lifetime and borrowing pattern comparison:

| Pattern | Allocation? | Use Case | Runtime Cost |
|---------|------------|----------|--------------|
| `&'a T` | No | Borrowed reference | Zero |
| `Cow<'a, T>` | Maybe | Avoid clone when unnecessary | Branch check |
| `RefCell<T>` | No | Interior mutability (single-threaded) | Runtime borrow check |
| `Arc<Mutex<T>>` | Yes (heap) | Shared mutable state (multi-threaded) | Lock contention |
| `Box<T>` | Yes (heap) | Owned heap allocation | Allocation |
| `PhantomData<&'a T>` | No | Lifetime association without data | Zero |
| `'static` | No | Program-lifetime data | Zero |

Key patterns:
1. Lifetime elision handles ~90% of cases — add explicit lifetimes only when the compiler requires them
2. Use `Cow<'_, str>` to avoid unnecessary allocations when input might or might not need transformation
3. `RefCell<T>` provides interior mutability with runtime borrow checking — panics on double mutable borrow
4. Split borrows let you mutably borrow different struct fields simultaneously — the compiler tracks each field
5. HRTBs (`for<'a>`) are needed when a closure must work with any lifetime, not a specific one
6. `PhantomData` establishes lifetime relationships without storing actual references — used in unsafe abstractions'''
    ),
    (
        "rust/async-tokio",
        "Show Rust async programming with Tokio including runtime setup, tasks, channels, streams, and async patterns.",
        '''Rust async programming with Tokio runtime and patterns:

```rust
// --- Tokio runtime and basic async ---

use std::time::Duration;
use tokio::time::{sleep, timeout, interval};
use tokio::sync::{mpsc, oneshot, broadcast, Semaphore};
use tokio::task::{self, JoinSet};
use anyhow::Result;

// Main entry point with Tokio runtime
#[tokio::main]
async fn main() -> Result<()> {
    // Spawn concurrent tasks
    let handle1 = tokio::spawn(async {
        sleep(Duration::from_millis(100)).await;
        "task 1 complete"
    });

    let handle2 = tokio::spawn(async {
        sleep(Duration::from_millis(200)).await;
        42
    });

    // Await both results
    let result1 = handle1.await?;
    let result2 = handle2.await?;
    println!("{}, {}", result1, result2);

    // Timeout wrapper
    match timeout(Duration::from_secs(5), slow_operation()).await {
        Ok(result) => println!("Got: {:?}", result),
        Err(_) => println!("Operation timed out"),
    }

    // Select — race multiple futures
    tokio::select! {
        val = async { sleep(Duration::from_millis(100)).await; "fast" } => {
            println!("Fast completed: {}", val);
        }
        val = async { sleep(Duration::from_secs(10)).await; "slow" } => {
            println!("Slow completed: {}", val);
        }
    }

    Ok(())
}

async fn slow_operation() -> String {
    sleep(Duration::from_secs(2)).await;
    "done".to_string()
}

// JoinSet for managing dynamic sets of tasks
async fn process_urls(urls: Vec<String>) -> Vec<Result<String>> {
    let mut set = JoinSet::new();

    for url in urls {
        set.spawn(async move {
            let resp = reqwest::get(&url).await?;
            let body = resp.text().await?;
            Ok::<String, anyhow::Error>(body)
        });
    }

    let mut results = Vec::new();
    while let Some(res) = set.join_next().await {
        match res {
            Ok(Ok(body)) => results.push(Ok(body)),
            Ok(Err(e)) => results.push(Err(e)),
            Err(join_err) => results.push(Err(join_err.into())),
        }
    }
    results
}
```

```rust
// --- Tokio channels ---

use tokio::sync::{mpsc, oneshot, broadcast, watch};

// mpsc: Multiple producers, single consumer
async fn mpsc_example() -> Result<()> {
    let (tx, mut rx) = mpsc::channel::<String>(100); // Bounded buffer

    // Spawn multiple producers
    for i in 0..5 {
        let tx = tx.clone();
        tokio::spawn(async move {
            tx.send(format!("Message from producer {}", i)).await.ok();
        });
    }
    drop(tx); // Drop original sender so rx eventually returns None

    // Consumer
    while let Some(msg) = rx.recv().await {
        println!("Received: {}", msg);
    }

    Ok(())
}

// oneshot: Single value, single use (request-response)
async fn oneshot_example() -> Result<()> {
    let (tx, rx) = oneshot::channel::<String>();

    tokio::spawn(async move {
        // Simulate work
        sleep(Duration::from_millis(100)).await;
        tx.send("computation result".to_string()).ok();
    });

    let result = rx.await?;
    println!("Got: {}", result);
    Ok(())
}

// broadcast: Multiple consumers, each gets every message
async fn broadcast_example() -> Result<()> {
    let (tx, _) = broadcast::channel::<String>(16);

    let mut rx1 = tx.subscribe();
    let mut rx2 = tx.subscribe();

    tokio::spawn(async move {
        tx.send("event 1".to_string()).ok();
        tx.send("event 2".to_string()).ok();
    });

    let h1 = tokio::spawn(async move {
        while let Ok(msg) = rx1.recv().await {
            println!("Subscriber 1: {}", msg);
        }
    });

    let h2 = tokio::spawn(async move {
        while let Ok(msg) = rx2.recv().await {
            println!("Subscriber 2: {}", msg);
        }
    });

    let _ = tokio::join!(h1, h2);
    Ok(())
}

// watch: Latest-value channel (lossy, single producer)
async fn watch_example() -> Result<()> {
    let (tx, mut rx) = watch::channel("initial".to_string());

    tokio::spawn(async move {
        for i in 0..10 {
            tx.send(format!("config v{}", i)).ok();
            sleep(Duration::from_millis(50)).await;
        }
    });

    // Consumer sees only the latest value
    while rx.changed().await.is_ok() {
        println!("Current config: {}", *rx.borrow());
    }
    Ok(())
}
```

```rust
// --- Async patterns: semaphore, retry, graceful shutdown ---

use std::sync::Arc;
use tokio::sync::Semaphore;
use tokio::signal;

// Bounded concurrency with semaphore
async fn bounded_fetch(urls: Vec<String>, max_concurrent: usize) -> Vec<Result<String>> {
    let semaphore = Arc::new(Semaphore::new(max_concurrent));
    let mut handles = Vec::new();

    for url in urls {
        let permit = semaphore.clone().acquire_owned().await.unwrap();
        handles.push(tokio::spawn(async move {
            let result = reqwest::get(&url).await?.text().await?;
            drop(permit); // Release semaphore slot
            Ok::<String, anyhow::Error>(result)
        }));
    }

    let mut results = Vec::new();
    for handle in handles {
        results.push(handle.await.unwrap_or_else(|e| Err(e.into())));
    }
    results
}

// Retry with exponential backoff
async fn retry_with_backoff<F, Fut, T>(
    max_retries: u32,
    base_delay: Duration,
    mut operation: F,
) -> Result<T>
where
    F: FnMut() -> Fut,
    Fut: std::future::Future<Output = Result<T>>,
{
    let mut last_err = None;
    for attempt in 0..=max_retries {
        match operation().await {
            Ok(val) => return Ok(val),
            Err(e) => {
                last_err = Some(e);
                if attempt < max_retries {
                    let delay = base_delay * 2u32.pow(attempt);
                    eprintln!("Attempt {} failed, retrying in {:?}", attempt + 1, delay);
                    sleep(delay).await;
                }
            }
        }
    }
    Err(last_err.unwrap())
}

// Graceful shutdown with tokio::select!
async fn run_server() -> Result<()> {
    let listener = tokio::net::TcpListener::bind("0.0.0.0:8080").await?;
    println!("Listening on :8080");

    let (shutdown_tx, mut shutdown_rx) = broadcast::channel::<()>(1);

    // Spawn shutdown signal handler
    let tx = shutdown_tx.clone();
    tokio::spawn(async move {
        signal::ctrl_c().await.expect("Failed to listen for ctrl_c");
        println!("Shutdown signal received");
        tx.send(()).ok();
    });

    loop {
        tokio::select! {
            Ok((stream, addr)) = listener.accept() => {
                let mut rx = shutdown_tx.subscribe();
                tokio::spawn(async move {
                    tokio::select! {
                        _ = handle_connection(stream) => {}
                        _ = rx.recv() => {
                            println!("Connection {} shutting down", addr);
                        }
                    }
                });
            }
            _ = shutdown_rx.recv() => {
                println!("Server shutting down gracefully");
                break;
            }
        }
    }

    Ok(())
}

async fn handle_connection(_stream: tokio::net::TcpStream) {
    sleep(Duration::from_secs(5)).await; // Simulate work
}
```

Tokio channel comparison:

| Channel | Producers | Consumers | Buffering | Use Case |
|---------|-----------|-----------|-----------|----------|
| `mpsc` | Many | One | Bounded/Unbounded | Work queues, command channels |
| `oneshot` | One | One | Single value | Request-response, result delivery |
| `broadcast` | One | Many | Bounded (lossy) | Event bus, pub/sub |
| `watch` | One | Many | Latest value only | Config updates, state sharing |

Key patterns:
1. Use `tokio::select!` to race multiple async operations — the first to complete wins, others are cancelled
2. `JoinSet` manages dynamic sets of tasks and collects results as they complete
3. `Semaphore` bounds concurrent async operations — `acquire_owned` returns an owned permit for `spawn`
4. Always use `bounded` mpsc channels in production to provide backpressure
5. Retry with exponential backoff prevents thundering herd on transient failures
6. Graceful shutdown uses `broadcast` to signal all tasks, combined with `select!` in each task loop'''
    ),
    (
        "rust/error-handling",
        "Show Rust error handling with thiserror, anyhow, custom error types, error conversion, and the ? operator.",
        '''Rust error handling with thiserror, anyhow, and custom patterns:

```rust
// --- Custom error types with thiserror ---

use thiserror::Error;
use std::io;

// thiserror derives Display, Error, and From automatically
#[derive(Error, Debug)]
pub enum AppError {
    #[error("User not found: {id}")]
    UserNotFound { id: u64 },

    #[error("Invalid input: {field} — {message}")]
    ValidationError {
        field: String,
        message: String,
    },

    #[error("Authentication failed")]
    Unauthorized,

    #[error("Access denied for resource: {resource}")]
    Forbidden { resource: String },

    #[error("Database error")]
    Database(#[from] sqlx::Error),  // Auto-converts sqlx::Error -> AppError

    #[error("IO error")]
    Io(#[from] io::Error),  // Auto-converts io::Error -> AppError

    #[error("Serialization error")]
    Serialization(#[from] serde_json::Error),

    #[error("External service error: {service}")]
    ExternalService {
        service: String,
        #[source]  // Marks as the source of this error
        source: reqwest::Error,
    },

    #[error("Rate limited — retry after {retry_after_secs}s")]
    RateLimited { retry_after_secs: u64 },
}

impl AppError {
    pub fn status_code(&self) -> u16 {
        match self {
            AppError::UserNotFound { .. } => 404,
            AppError::ValidationError { .. } => 400,
            AppError::Unauthorized => 401,
            AppError::Forbidden { .. } => 403,
            AppError::RateLimited { .. } => 429,
            AppError::Database(_) | AppError::Io(_) => 500,
            AppError::Serialization(_) => 422,
            AppError::ExternalService { .. } => 502,
        }
    }

    pub fn is_retryable(&self) -> bool {
        matches!(
            self,
            AppError::Database(_)
                | AppError::ExternalService { .. }
                | AppError::RateLimited { .. }
        )
    }
}

// Domain-specific result alias
pub type AppResult<T> = Result<T, AppError>;
```

```rust
// --- Using errors across application layers ---

use anyhow::{Context, Result, bail, ensure};

// Repository layer — returns domain errors
struct UserRepository {
    pool: sqlx::PgPool,
}

impl UserRepository {
    async fn find_by_id(&self, id: u64) -> AppResult<User> {
        sqlx::query_as!(User, "SELECT * FROM users WHERE id = $1", id as i64)
            .fetch_optional(&self.pool)
            .await?  // sqlx::Error auto-converts to AppError::Database via #[from]
            .ok_or(AppError::UserNotFound { id })
    }

    async fn create(&self, user: &NewUser) -> AppResult<User> {
        // Validate before DB operation
        if user.email.is_empty() {
            return Err(AppError::ValidationError {
                field: "email".into(),
                message: "cannot be empty".into(),
            });
        }

        sqlx::query_as!(
            User,
            "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING *",
            user.name, user.email,
        )
        .fetch_one(&self.pool)
        .await
        .map_err(|e| match e {
            sqlx::Error::Database(ref db_err)
                if db_err.constraint() == Some("users_email_key") =>
            {
                AppError::ValidationError {
                    field: "email".into(),
                    message: format!("{} already exists", user.email),
                }
            }
            other => AppError::Database(other),
        })
    }
}

// Service layer — uses anyhow for internal context
struct UserService {
    repo: UserRepository,
    auth: AuthClient,
}

impl UserService {
    // anyhow::Result for internal/CLI tools
    async fn sync_users(&self) -> Result<usize> {
        let external_users = self.auth
            .fetch_users()
            .await
            .context("Failed to fetch users from auth service")?;

        ensure!(!external_users.is_empty(), "No users returned from auth service");

        let mut count = 0;
        for user in external_users {
            self.repo
                .create(&user)
                .await
                .with_context(|| format!("Failed to create user: {}", user.email))?;
            count += 1;
        }

        Ok(count)
    }

    // AppResult for API-facing methods
    async fn get_user(&self, id: u64) -> AppResult<User> {
        self.repo.find_by_id(id).await
    }
}

#[derive(Debug)]
struct User { id: i64, name: String, email: String }
struct NewUser { name: String, email: String }
struct AuthClient;
impl AuthClient {
    async fn fetch_users(&self) -> Result<Vec<NewUser>> { Ok(vec![]) }
}
```

```rust
// --- Error handling in HTTP handlers (Axum) ---

use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;

// Convert AppError into HTTP response
impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        #[derive(Serialize)]
        struct ErrorBody {
            error: String,
            code: u16,
            retryable: bool,
        }

        let status = StatusCode::from_u16(self.status_code())
            .unwrap_or(StatusCode::INTERNAL_SERVER_ERROR);

        let body = ErrorBody {
            error: self.to_string(),
            code: self.status_code(),
            retryable: self.is_retryable(),
        };

        // Log server errors
        if status.is_server_error() {
            tracing::error!(error = ?self, "Server error");
        }

        (status, Json(body)).into_response()
    }
}

// Handler using ? operator with automatic error conversion
async fn get_user_handler(
    axum::extract::Path(id): axum::extract::Path<u64>,
    axum::extract::State(service): axum::extract::State<UserService>,
) -> Result<Json<User>, AppError> {
    let user = service.get_user(id).await?;  // AppError auto-converts to response
    Ok(Json(user))
}

// Multiple error sources in one handler
async fn create_user_handler(
    axum::extract::State(service): axum::extract::State<UserService>,
    Json(payload): Json<NewUser>,
) -> Result<(StatusCode, Json<User>), AppError> {
    // Validation
    if payload.name.len() < 2 {
        return Err(AppError::ValidationError {
            field: "name".into(),
            message: "must be at least 2 characters".into(),
        });
    }

    let user = service.repo.create(&payload).await?;
    Ok((StatusCode::CREATED, Json(user)))
}
```

```rust
// --- Error handling utilities ---

use std::fmt;

// Retry with typed errors
async fn retry<F, Fut, T, E>(
    max_attempts: u32,
    operation: F,
) -> Result<T, E>
where
    F: Fn() -> Fut,
    Fut: std::future::Future<Output = Result<T, E>>,
    E: fmt::Debug,
{
    let mut last_err = None;
    for attempt in 1..=max_attempts {
        match operation().await {
            Ok(val) => return Ok(val),
            Err(e) => {
                tracing::warn!(attempt, error = ?e, "Operation failed, retrying");
                last_err = Some(e);
            }
        }
    }
    Err(last_err.unwrap())
}

// Extension trait for adding context to any error
trait ResultExt<T> {
    fn with_status(self, status: u16) -> Result<T, AppError>;
}

impl<T, E: Into<AppError>> ResultExt<T> for Result<T, E> {
    fn with_status(self, _status: u16) -> Result<T, AppError> {
        self.map_err(|e| e.into())
    }
}
```

Error handling crate comparison:

| Crate | Purpose | When to Use |
|-------|---------|------------|
| `thiserror` | Derive `Error` for library/domain errors | Public APIs, domain error enums |
| `anyhow` | Flexible error context chaining | CLI tools, internal code, scripts |
| `eyre` | `anyhow` alternative with custom reports | Apps needing rich error display |
| `miette` | Diagnostic errors with source spans | Compilers, linters, config parsers |
| `snafu` | Context selectors for error variants | Complex error hierarchies |

Key patterns:
1. Use `thiserror` for domain error enums exposed in public APIs — it generates `Display`, `Error`, and `From`
2. Use `anyhow` for application code where you need `.context("msg")` chains without defining every error type
3. The `#[from]` attribute on `thiserror` variants auto-generates `From<E>` for the `?` operator
4. Map database constraint errors to domain validation errors at the repository layer
5. Implement `IntoResponse` for your error type to automatically convert errors to HTTP responses
6. Use `ensure!()` and `bail!()` from anyhow for early validation exits with context'''
    ),
    (
        "rust/traits-generics",
        "Show Rust traits and generics patterns including associated types, trait objects, blanket implementations, and supertraits.",
        '''Rust traits and generics with associated types and advanced patterns:

```rust
// --- Associated types vs generic parameters ---

// Associated type: one implementation per type (like Iterator)
trait Repository {
    type Entity;
    type Error;

    fn find_by_id(&self, id: u64) -> Result<Self::Entity, Self::Error>;
    fn save(&self, entity: &Self::Entity) -> Result<(), Self::Error>;
    fn delete(&self, id: u64) -> Result<(), Self::Error>;
}

#[derive(Debug, Clone)]
struct User {
    id: u64,
    name: String,
    email: String,
}

struct PostgresUserRepo {
    pool: sqlx::PgPool,
}

impl Repository for PostgresUserRepo {
    type Entity = User;
    type Error = sqlx::Error;

    fn find_by_id(&self, id: u64) -> Result<User, sqlx::Error> {
        // Implementation...
        todo!()
    }

    fn save(&self, entity: &User) -> Result<(), sqlx::Error> {
        todo!()
    }

    fn delete(&self, id: u64) -> Result<(), sqlx::Error> {
        todo!()
    }
}

// Generic parameter: multiple implementations possible
trait Converter<Target> {
    fn convert(&self) -> Target;
}

impl Converter<String> for User {
    fn convert(&self) -> String {
        format!("{} <{}>", self.name, self.email)
    }
}

impl Converter<serde_json::Value> for User {
    fn convert(&self) -> serde_json::Value {
        serde_json::json!({
            "id": self.id,
            "name": self.name,
            "email": self.email,
        })
    }
}

// Supertraits — trait requires another trait
trait Identifiable {
    fn id(&self) -> u64;
}

trait Auditable: Identifiable + std::fmt::Debug {
    fn created_at(&self) -> chrono::DateTime<chrono::Utc>;
    fn updated_at(&self) -> chrono::DateTime<chrono::Utc>;

    // Default method using supertrait
    fn audit_log(&self) -> String {
        format!(
            "[{}] Entity {:?} created={} updated={}",
            self.id(),
            self,
            self.created_at(),
            self.updated_at(),
        )
    }
}
```

```rust
// --- Trait objects and dynamic dispatch ---

use std::fmt;

// Trait object: runtime polymorphism with dyn
trait Notifier: Send + Sync {
    fn send(&self, to: &str, message: &str) -> Result<(), Box<dyn std::error::Error>>;
    fn name(&self) -> &str;
}

struct EmailNotifier {
    smtp_host: String,
}

impl Notifier for EmailNotifier {
    fn send(&self, to: &str, message: &str) -> Result<(), Box<dyn std::error::Error>> {
        println!("Email to {}: {}", to, message);
        Ok(())
    }
    fn name(&self) -> &str { "email" }
}

struct SlackNotifier {
    webhook_url: String,
}

impl Notifier for SlackNotifier {
    fn send(&self, to: &str, message: &str) -> Result<(), Box<dyn std::error::Error>> {
        println!("Slack to {}: {}", to, message);
        Ok(())
    }
    fn name(&self) -> &str { "slack" }
}

// Using trait objects for runtime polymorphism
struct NotificationService {
    notifiers: Vec<Box<dyn Notifier>>,
}

impl NotificationService {
    fn new() -> Self {
        NotificationService { notifiers: Vec::new() }
    }

    fn register(&mut self, notifier: Box<dyn Notifier>) {
        self.notifiers.push(notifier);
    }

    fn notify_all(&self, to: &str, message: &str) {
        for notifier in &self.notifiers {
            if let Err(e) = notifier.send(to, message) {
                eprintln!("Failed to send via {}: {}", notifier.name(), e);
            }
        }
    }
}

// Object safety rules:
// A trait is object-safe if:
// 1. It does not require Self: Sized
// 2. All methods have a receiver (self, &self, &mut self, etc.)
// 3. No method returns Self
// 4. No method has generic type parameters
// 5. No associated functions (no self parameter)

// NOT object-safe (returns Self):
// trait Clone { fn clone(&self) -> Self; }

// Workaround: separate object-safe trait
trait CloneBox {
    fn clone_box(&self) -> Box<dyn CloneBox>;
}

impl<T: Clone + 'static> CloneBox for T {
    fn clone_box(&self) -> Box<dyn CloneBox> {
        Box::new(self.clone())
    }
}
```

```rust
// --- Blanket implementations and extension traits ---

// Blanket implementation: implement trait for ALL types meeting a bound
trait Printable {
    fn print(&self);
}

// Every type that implements Display gets Printable for free
impl<T: fmt::Display> Printable for T {
    fn print(&self) {
        println!("{}", self);
    }
}

// Extension trait — add methods to existing types
trait StringExt {
    fn truncate_with_ellipsis(&self, max_len: usize) -> String;
    fn is_valid_email(&self) -> bool;
}

impl StringExt for str {
    fn truncate_with_ellipsis(&self, max_len: usize) -> String {
        if self.len() <= max_len {
            self.to_string()
        } else {
            format!("{}...", &self[..max_len.saturating_sub(3)])
        }
    }

    fn is_valid_email(&self) -> bool {
        let parts: Vec<&str> = self.split('@').collect();
        parts.len() == 2 && !parts[0].is_empty() && parts[1].contains('.')
    }
}

// Newtype pattern for implementing foreign traits on foreign types
struct Meters(f64);
struct Kilometers(f64);

impl From<Meters> for Kilometers {
    fn from(m: Meters) -> Self {
        Kilometers(m.0 / 1000.0)
    }
}

impl fmt::Display for Meters {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{:.2}m", self.0)
    }
}

// Generic function with multiple trait bounds
fn process_and_log<T>(item: T)
where
    T: fmt::Debug + fmt::Display + Clone + Send + 'static,
{
    println!("Processing: {}", item);
    let clone = item.clone();
    std::thread::spawn(move || {
        println!("Background: {:?}", clone);
    });
}

// impl Trait in return position (existential type)
fn create_notifier(kind: &str) -> impl Notifier {
    match kind {
        "email" => EmailNotifier { smtp_host: "smtp.example.com".into() },
        // Cannot return different types with impl Trait
        // Use Box<dyn Notifier> for runtime polymorphism
        _ => EmailNotifier { smtp_host: "localhost".into() },
    }
}

fn main() {
    // Extension trait usage
    let email = "user@example.com";
    println!("Valid email: {}", email.is_valid_email());

    let long_text = "This is a very long string that should be truncated";
    println!("{}", long_text.truncate_with_ellipsis(20));

    // Blanket implementation usage
    42.print();           // i32: Display -> Printable
    "hello".print();      // &str: Display -> Printable

    // Trait object usage
    let mut service = NotificationService::new();
    service.register(Box::new(EmailNotifier {
        smtp_host: "smtp.example.com".into(),
    }));
    service.register(Box::new(SlackNotifier {
        webhook_url: "https://hooks.slack.com/...".into(),
    }));
    service.notify_all("admin", "Server deployed successfully");
}
```

Trait dispatch comparison:

| Approach | Dispatch | Performance | Flexibility | Use When |
|----------|----------|-------------|-------------|----------|
| `impl Trait` (param) | Static (monomorphized) | Fast (inlined) | Compile-time only | Known types at compile time |
| `impl Trait` (return) | Static | Fast | Single concrete type | Factory functions |
| `dyn Trait` | Dynamic (vtable) | Pointer indirection | Runtime polymorphism | Heterogeneous collections |
| `Box<dyn Trait>` | Dynamic (heap) | Allocation + indirection | Owned trait objects | Plugin systems, registries |
| `&dyn Trait` | Dynamic (stack) | Indirection only | Borrowed trait objects | Temporary polymorphism |
| Enum dispatch | Static (match) | Fast (no indirection) | Closed set of variants | Known, finite type set |

Key patterns:
1. Use associated types when there is exactly one implementation per type (`Iterator::Item`)
2. Use generic parameters when multiple implementations are needed (`From<T>`)
3. Blanket implementations (`impl<T: Display> MyTrait for T`) add methods to all qualifying types
4. Extension traits add methods to foreign types without needing the newtype pattern
5. Object safety requires: no `Self` in return position, no generic methods, all methods have a receiver
6. Prefer static dispatch (`impl Trait`) for performance; use `dyn Trait` only when you need runtime polymorphism'''
    ),
    (
        "rust/macros-declarative-procedural",
        "Show Rust macro patterns including declarative macros (macro_rules!), procedural macros (derive, attribute), and when to use each.",
        '''Rust macros: declarative (macro_rules!) and procedural (derive, attribute):

```rust
// --- Declarative macros (macro_rules!) ---

// Simple matching macro
macro_rules! hashmap {
    // Empty map
    () => {
        std::collections::HashMap::new()
    };
    // Key-value pairs: hashmap!{ "a" => 1, "b" => 2 }
    ($($key:expr => $val:expr),+ $(,)?) => {{
        let mut map = std::collections::HashMap::new();
        $(map.insert($key, $val);)+
        map
    }};
}

// Builder pattern macro
macro_rules! builder {
    ($name:ident { $($field:ident : $ty:ty),* $(,)? }) => {
        #[derive(Debug, Default)]
        pub struct $name {
            $($field: Option<$ty>,)*
        }

        impl $name {
            pub fn new() -> Self {
                Self::default()
            }

            $(
                pub fn $field(mut self, value: $ty) -> Self {
                    self.$field = Some(value);
                    self
                }
            )*
        }
    };
}

builder!(ServerConfig {
    host: String,
    port: u16,
    max_connections: usize,
    timeout_secs: u64,
});

// Variadic function-like macro
macro_rules! log_fields {
    ($level:expr, $msg:expr, $($key:ident = $val:expr),* $(,)?) => {
        eprintln!(
            "[{}] {} {}",
            $level,
            $msg,
            vec![$(format!("{}={:?}", stringify!($key), $val)),*].join(" ")
        );
    };
}

// Recursive macro for compile-time computation
macro_rules! count {
    () => { 0usize };
    ($head:tt $($tail:tt)*) => { 1usize + count!($($tail)*) };
}

// Enum with auto-generated methods
macro_rules! enum_str {
    ($name:ident { $($variant:ident),* $(,)? }) => {
        #[derive(Debug, Clone, Copy, PartialEq, Eq)]
        pub enum $name {
            $($variant),*
        }

        impl $name {
            pub fn as_str(&self) -> &'static str {
                match self {
                    $(Self::$variant => stringify!($variant)),*
                }
            }

            pub fn from_str(s: &str) -> Option<Self> {
                match s {
                    $(stringify!($variant) => Some(Self::$variant),)*
                    _ => None,
                }
            }

            pub fn variants() -> &'static [Self] {
                &[$(Self::$variant),*]
            }
        }

        impl std::fmt::Display for $name {
            fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                write!(f, "{}", self.as_str())
            }
        }
    };
}

enum_str!(Color { Red, Green, Blue, Yellow });

fn main() {
    let config = ServerConfig::new()
        .host("localhost".to_string())
        .port(8080)
        .max_connections(100);
    println!("{:?}", config);

    let map = hashmap!{
        "name" => "Alice",
        "role" => "admin",
    };
    println!("{:?}", map);

    log_fields!("INFO", "User logged in", user = "alice", ip = "127.0.0.1");

    let items = count!(a b c d e);
    println!("Count: {}", items); // 5

    println!("Colors: {:?}", Color::variants());
    println!("From str: {:?}", Color::from_str("Red"));
}
```

```rust
// --- Procedural derive macro (in a separate crate) ---
// File: my_derive/src/lib.rs

use proc_macro::TokenStream;
use quote::quote;
use syn::{parse_macro_input, DeriveInput, Data, Fields};

// Derive macro: #[derive(MyDebug)]
#[proc_macro_derive(MyDebug, attributes(debug_ignore))]
pub fn derive_my_debug(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as DeriveInput);
    let name = &input.ident;

    let fields = match &input.data {
        Data::Struct(data) => match &data.fields {
            Fields::Named(fields) => &fields.named,
            _ => panic!("MyDebug only supports named fields"),
        },
        _ => panic!("MyDebug only supports structs"),
    };

    // Filter out fields marked with #[debug_ignore]
    let field_debugs = fields.iter().filter_map(|f| {
        let has_ignore = f.attrs.iter().any(|attr| {
            attr.path().is_ident("debug_ignore")
        });
        if has_ignore {
            return None;
        }
        let field_name = &f.ident;
        let field_str = field_name.as_ref().map(|n| n.to_string());
        Some(quote! {
            .field(#field_str, &self.#field_name)
        })
    });

    let name_str = name.to_string();
    let expanded = quote! {
        impl std::fmt::Debug for #name {
            fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
                f.debug_struct(#name_str)
                    #(#field_debugs)*
                    .finish()
            }
        }
    };

    TokenStream::from(expanded)
}

// Attribute macro: #[route(GET, "/api/users")]
#[proc_macro_attribute]
pub fn route(attr: TokenStream, item: TokenStream) -> TokenStream {
    let args = parse_macro_input!(attr as syn::AttributeArgs);
    let input = parse_macro_input!(item as syn::ItemFn);
    let fn_name = &input.sig.ident;

    // Parse method and path from args
    // (simplified — real implementation parses args properly)

    let expanded = quote! {
        #input

        // Generate registration code
        inventory::submit! {
            Route {
                method: "GET",
                path: "/api/users",
                handler: #fn_name,
            }
        }
    };

    TokenStream::from(expanded)
}
```

```rust
// --- Using derive macros and practical patterns ---

// In application code:

use serde::{Serialize, Deserialize};

#[derive(MyDebug, Serialize, Deserialize)]
struct UserProfile {
    id: u64,
    name: String,
    email: String,
    #[debug_ignore]           // Custom attribute: hide from debug
    #[serde(skip_serializing)] // Serde attribute: skip in JSON
    password_hash: String,
    #[serde(rename = "createdAt")]
    created_at: String,
}

// Common derive macro patterns:
// #[derive(Debug, Clone)]                 — basic traits
// #[derive(Serialize, Deserialize)]       — serde JSON/YAML/etc
// #[derive(sqlx::FromRow)]               — database row mapping
// #[derive(clap::Parser)]               — CLI argument parsing
// #[derive(thiserror::Error)]            — error types
// #[derive(PartialEq, Eq, Hash)]        — comparison and hashing

// Conditional compilation with cfg
macro_rules! debug_log {
    ($($arg:tt)*) => {
        #[cfg(debug_assertions)]
        eprintln!("[DEBUG] {}", format!($($arg)*));
    };
}

// Macro for test helpers
macro_rules! assert_err {
    ($expr:expr, $pat:pat) => {
        match $expr {
            Err($pat) => {},
            Err(other) => panic!(
                "Expected error matching {}, got: {:?}",
                stringify!($pat),
                other,
            ),
            Ok(val) => panic!(
                "Expected error matching {}, got Ok({:?})",
                stringify!($pat),
                val,
            ),
        }
    };
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_color_roundtrip() {
        for color in Color::variants() {
            let s = color.as_str();
            let parsed = Color::from_str(s).unwrap();
            assert_eq!(*color, parsed);
        }
    }

    #[test]
    fn test_hashmap_macro() {
        let map = hashmap!{
            1 => "one",
            2 => "two",
        };
        assert_eq!(map.len(), 2);
        assert_eq!(map[&1], "one");
    }
}
```

Macro type comparison:

| Type | Syntax | Crate | Capabilities | Use Case |
|------|--------|-------|-------------|----------|
| Declarative (`macro_rules!`) | Pattern matching | Same crate | Token transformation | Simple code generation, DSLs |
| Derive (`#[derive(X)]`) | Proc macro | Separate crate | Full Rust code, syn/quote | Auto-implement traits |
| Attribute (`#[x(...)]`) | Proc macro | Separate crate | Transform any item | Routing, logging, validation |
| Function-like (`x!(...)`) | Proc macro | Separate crate | Arbitrary input | Complex DSLs, SQL queries |

Key patterns:
1. Use `macro_rules!` for simple pattern-based code generation — no separate crate needed
2. Procedural macros require a separate crate with `proc-macro = true` in Cargo.toml
3. Use `syn` to parse Rust tokens and `quote` to generate output in procedural macros
4. The `$(...)* ` repetition in `macro_rules!` handles variable-length inputs (like varargs)
5. Use `$(,)?` at the end of repetitions to allow trailing commas
6. Prefer derive macros over attribute macros when you are implementing a trait — they compose better with other derives'''
    ),
]
