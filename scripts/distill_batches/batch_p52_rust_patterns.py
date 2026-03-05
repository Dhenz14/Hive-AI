"""Rust — ownership, error handling, traits, and async patterns."""

PAIRS = [
    (
        "rust/ownership-patterns",
        "Show Rust ownership patterns: borrowing, lifetimes, smart pointers, and common ownership solutions.",
        '''Rust ownership and borrowing patterns:

```rust
use std::collections::HashMap;

// --- Borrowing rules ---
// 1. One mutable reference OR any number of immutable references
// 2. References must always be valid

// Immutable borrow (multiple readers)
fn print_stats(data: &[f64]) {
    let sum: f64 = data.iter().sum();
    let avg = sum / data.len() as f64;
    println!("Count: {}, Avg: {:.2}", data.len(), avg);
}

// Mutable borrow (single writer)
fn normalize(data: &mut Vec<f64>) {
    let max = data.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
    if max > 0.0 {
        for val in data.iter_mut() {
            *val /= max;
        }
    }
}


// --- Ownership transfer patterns ---

// Take ownership when you need to store the value
struct Database {
    connection_string: String,  // Owns the string
}

impl Database {
    fn new(conn: String) -> Self {
        Database { connection_string: conn }
    }

    // Borrow when you only need to read
    fn query(&self, sql: &str) -> Vec<String> {
        println!("Querying {} with: {}", self.connection_string, sql);
        vec![]
    }
}


// --- Clone vs borrow decision ---

// Borrow when possible (zero-cost)
fn find_longest<'a>(a: &'a str, b: &'a str) -> &'a str {
    if a.len() >= b.len() { a } else { b }
}

// Clone when you need independent ownership
fn process_items(items: &[String]) -> Vec<String> {
    items.iter()
        .filter(|s| !s.is_empty())
        .map(|s| s.to_uppercase())  // Creates new String
        .collect()
}


// --- Smart pointers ---

use std::rc::Rc;
use std::cell::RefCell;
use std::sync::{Arc, Mutex};

// Rc<T> — shared ownership (single-threaded)
fn shared_config() {
    let config = Rc::new(HashMap::from([
        ("host".to_string(), "localhost".to_string()),
        ("port".to_string(), "8080".to_string()),
    ]));

    let config_clone = Rc::clone(&config);  // Cheap reference count bump
    // Both variables point to same data
}

// RefCell<T> — interior mutability (runtime borrow checking)
struct Cache {
    data: RefCell<HashMap<String, String>>,
}

impl Cache {
    fn get_or_insert(&self, key: &str, compute: impl Fn() -> String) -> String {
        {
            let data = self.data.borrow();
            if let Some(val) = data.get(key) {
                return val.clone();
            }
        }  // Immutable borrow dropped here
        let value = compute();
        self.data.borrow_mut().insert(key.to_string(), value.clone());
        value
    }
}

// Arc<Mutex<T>> — shared ownership + mutation (multi-threaded)
fn shared_counter() {
    let counter = Arc::new(Mutex::new(0));
    let mut handles = vec![];

    for _ in 0..10 {
        let counter = Arc::clone(&counter);
        let handle = std::thread::spawn(move || {
            let mut num = counter.lock().unwrap();
            *num += 1;
        });
        handles.push(handle);
    }

    for handle in handles {
        handle.join().unwrap();
    }
    println!("Count: {}", *counter.lock().unwrap());
}


// --- Builder pattern (avoids complex constructors) ---

#[derive(Debug)]
struct Request {
    url: String,
    method: String,
    headers: HashMap<String, String>,
    body: Option<String>,
    timeout_ms: u64,
}

struct RequestBuilder {
    url: String,
    method: String,
    headers: HashMap<String, String>,
    body: Option<String>,
    timeout_ms: u64,
}

impl RequestBuilder {
    fn new(url: impl Into<String>) -> Self {
        Self {
            url: url.into(),
            method: "GET".to_string(),
            headers: HashMap::new(),
            body: None,
            timeout_ms: 30000,
        }
    }

    fn method(mut self, method: impl Into<String>) -> Self {
        self.method = method.into();
        self
    }

    fn header(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.headers.insert(key.into(), value.into());
        self
    }

    fn body(mut self, body: impl Into<String>) -> Self {
        self.body = Some(body.into());
        self
    }

    fn timeout(mut self, ms: u64) -> Self {
        self.timeout_ms = ms;
        self
    }

    fn build(self) -> Request {
        Request {
            url: self.url,
            method: self.method,
            headers: self.headers,
            body: self.body,
            timeout_ms: self.timeout_ms,
        }
    }
}

// Usage:
// let req = RequestBuilder::new("https://api.example.com")
//     .method("POST")
//     .header("Content-Type", "application/json")
//     .body(r#"{"key": "value"}"#)
//     .timeout(5000)
//     .build();
```

Ownership patterns:
1. **Borrow by default** — use `&T` or `&mut T`, only take ownership when needed
2. **`Rc`/`Arc`** — shared ownership (single-threaded / multi-threaded)
3. **`RefCell`/`Mutex`** — interior mutability when needed
4. **Builder pattern** — `self` by value for method chaining (ownership transfer)
5. **`impl Into<String>`** — accept both `&str` and `String` ergonomically'''
    ),
    (
        "rust/error-handling",
        "Show Rust error handling: Result, custom errors, the ? operator, anyhow/thiserror, and error conversion.",
        '''Rust error handling patterns:

```rust
use std::fmt;
use std::io;
use std::num::ParseIntError;

// --- Custom error with thiserror ---

// Cargo.toml: thiserror = "1"
use thiserror::Error;

#[derive(Error, Debug)]
enum AppError {
    #[error("User not found: {0}")]
    NotFound(String),

    #[error("Validation failed: {field} - {reason}")]
    Validation { field: String, reason: String },

    #[error("Database error")]
    Database(#[from] sqlx::Error),

    #[error("IO error")]
    Io(#[from] io::Error),

    #[error("Parse error")]
    Parse(#[from] ParseIntError),

    #[error("Unauthorized: {0}")]
    Unauthorized(String),

    #[error("Rate limited, retry after {retry_after}s")]
    RateLimited { retry_after: u64 },
}

// HTTP status code mapping
impl AppError {
    fn status_code(&self) -> u16 {
        match self {
            AppError::NotFound(_) => 404,
            AppError::Validation { .. } => 422,
            AppError::Unauthorized(_) => 401,
            AppError::RateLimited { .. } => 429,
            _ => 500,
        }
    }
}


// --- Using the ? operator ---

async fn get_user(id: &str) -> Result<User, AppError> {
    let user_id: i64 = id.parse()?;  // ParseIntError -> AppError::Parse

    let user = sqlx::query_as!(User,
        "SELECT * FROM users WHERE id = $1", user_id
    )
    .fetch_optional(&pool)
    .await?;  // sqlx::Error -> AppError::Database

    user.ok_or_else(|| AppError::NotFound(format!("user {id}")))
}


// --- Result combinators ---

fn process_config(path: &str) -> Result<Config, AppError> {
    let content = std::fs::read_to_string(path)?;  // io::Error -> AppError

    let config: Config = serde_json::from_str(&content)
        .map_err(|e| AppError::Validation {
            field: "config".to_string(),
            reason: e.to_string(),
        })?;

    Ok(config)
}


// --- anyhow for application code ---

// Cargo.toml: anyhow = "1"
use anyhow::{Context, Result, bail, ensure};

fn run_pipeline(input: &str) -> Result<Output> {
    let data = std::fs::read_to_string(input)
        .context("Failed to read input file")?;

    ensure!(!data.is_empty(), "Input file is empty");

    let parsed = parse_data(&data)
        .context("Failed to parse data")?;

    if parsed.records.is_empty() {
        bail!("No records found in input");
    }

    let result = process(parsed)
        .context("Processing failed")?;

    Ok(result)
}


// --- Pattern matching on errors ---

async fn handle_request(id: &str) -> HttpResponse {
    match get_user(id).await {
        Ok(user) => HttpResponse::Ok().json(user),
        Err(AppError::NotFound(msg)) => {
            HttpResponse::NotFound().json(ErrorBody {
                code: "NOT_FOUND",
                message: &msg,
            })
        }
        Err(AppError::Validation { field, reason }) => {
            HttpResponse::UnprocessableEntity().json(ErrorBody {
                code: "VALIDATION",
                message: &format!("{field}: {reason}"),
            })
        }
        Err(e) => {
            tracing::error!("Unhandled error: {e:?}");
            HttpResponse::InternalServerError().json(ErrorBody {
                code: "INTERNAL",
                message: "Internal server error",
            })
        }
    }
}


// --- Collecting results ---

fn parse_all(inputs: &[&str]) -> Result<Vec<i64>, AppError> {
    inputs.iter()
        .map(|s| s.parse::<i64>().map_err(AppError::from))
        .collect()  // Stops at first error
}

fn parse_all_lenient(inputs: &[&str]) -> (Vec<i64>, Vec<AppError>) {
    let (oks, errs): (Vec<_>, Vec<_>) = inputs.iter()
        .map(|s| s.parse::<i64>().map_err(AppError::from))
        .partition(Result::is_ok);

    (
        oks.into_iter().map(Result::unwrap).collect(),
        errs.into_iter().map(Result::unwrap_err).collect(),
    )
}
```

Rust error patterns:
1. **`thiserror`** — derive `Error` for library errors with `#[from]` auto-conversion
2. **`anyhow`** — use in application code for easy error context chaining
3. **`?` operator** — propagate errors with automatic conversion
4. **`context()`** — add human-readable context to error chain
5. **Pattern matching** — exhaustive error handling with `match`'''
    ),
]
"""
