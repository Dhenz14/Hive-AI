"""
Rust language training pairs - Result, ?, thiserror, anyhow, custom error types
"""

pairs = [
    {
        "instruction": r'''<thinking>
The user wants to understand Rust error handling basics. I should cover Result, Option, the ? operator, and show how they compose in real code. I will demonstrate a function that reads a config file and parses it, chaining errors with ?.
</thinking>

Explain Rust error handling with Result and the ? operator. Show a practical example that chains multiple fallible operations.''',
        "output": r'''Rust uses `Result<T, E>` for recoverable errors and `panic!` for unrecoverable ones. The `?` operator propagates errors up the call stack, converting them if needed.

```rust
use std::fs;
use std::num::ParseIntError;
use std::io;

#[derive(Debug)]
struct Config {
    host: String,
    port: u16,
    workers: usize,
}

fn load_config(path: &str) -> Result<Config, Box<dyn std::error::Error>> {
    // ? returns early with the error if the operation fails
    let contents = fs::read_to_string(path)?;

    let mut host = String::from("localhost");
    let mut port: u16 = 8080;
    let mut workers: usize = 4;

    for line in contents.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        if let Some((key, val)) = line.split_once('=') {
            match key.trim() {
                "host" => host = val.trim().to_string(),
                "port" => port = val.trim().parse()?,  // ? converts ParseIntError
                "workers" => workers = val.trim().parse()?,
                _ => {} // ignore unknown keys
            }
        }
    }

    Ok(Config { host, port, workers })
}

fn main() {
    match load_config("app.conf") {
        Ok(cfg) => println!("Config: {cfg:?}"),
        Err(e) => eprintln!("Failed to load config: {e}"),
    }

    // Option works similarly -- use ? in functions returning Option
    let val: Option<i32> = Some(42);
    let doubled = val.map(|v| v * 2);
    println!("Doubled: {doubled:?}");
}
```

The `?` operator:
- On `Result`: returns `Err(e.into())` if the result is `Err`
- On `Option`: returns `None` if the option is `None`
- Performs `From` conversion automatically, so `io::Error` and `ParseIntError` both convert to `Box<dyn Error>`'''
    },
    {
        "instruction": r'''<thinking>
The user wants to see how to define custom error types in Rust using thiserror. I need to show a proper enum-based error type with derive macros and how it integrates with the ? operator.
</thinking>

How do I create a custom error type in Rust using the thiserror crate? Show a complete example with multiple error variants.''',
        "output": r'''The `thiserror` crate provides derive macros that implement `std::error::Error`, `Display`, and `From` for your error enums with minimal boilerplate.

```rust
// Cargo.toml:
// [dependencies]
// thiserror = "1"
// serde_json = "1"

use thiserror::Error;
use std::io;

#[derive(Error, Debug)]
pub enum AppError {
    #[error("I/O error: {0}")]
    Io(#[from] io::Error),

    #[error("JSON parse error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("validation failed: {field} -- {reason}")]
    Validation {
        field: String,
        reason: String,
    },

    #[error("record not found: id={id}")]
    NotFound { id: u64 },

    #[error("rate limit exceeded, retry after {retry_after_secs}s")]
    RateLimited { retry_after_secs: u64 },
}

// The #[from] attribute auto-generates From<io::Error> for AppError
// and From<serde_json::Error> for AppError, enabling ? conversion.

pub fn load_user(path: &str, user_id: u64) -> Result<String, AppError> {
    let data = std::fs::read_to_string(path)?; // io::Error -> AppError::Io
    let users: Vec<serde_json::Value> = serde_json::from_str(&data)?; // -> AppError::Json

    let user = users
        .iter()
        .find(|u| u["id"].as_u64() == Some(user_id))
        .ok_or(AppError::NotFound { id: user_id })?;

    let name = user["name"]
        .as_str()
        .ok_or_else(|| AppError::Validation {
            field: "name".into(),
            reason: "must be a string".into(),
        })?;

    Ok(name.to_string())
}

fn main() {
    match load_user("users.json", 42) {
        Ok(name) => println!("Found user: {name}"),
        Err(AppError::NotFound { id }) => eprintln!("No user with id {id}"),
        Err(e) => eprintln!("Error: {e}"),
    }
}
```

Use `thiserror` in libraries where callers need to match on specific error variants. Each `#[error("...")]` attribute defines the `Display` output, and `#[from]` generates the `From` impl for automatic `?` conversion.'''
    },
    {
        "instruction": r'''What is the anyhow crate in Rust and how does it differ from thiserror? Show when to use each.''',
        "output": r'''`anyhow` provides a catch-all error type for application code where you do not need callers to match on specific variants. `thiserror` is for libraries that expose structured error types.

```rust
// Cargo.toml:
// [dependencies]
// anyhow = "1"
// serde_json = "1"

use anyhow::{Context, Result, bail, ensure};

// Result is anyhow::Result<T> which is Result<T, anyhow::Error>
fn fetch_config(url: &str) -> Result<serde_json::Value> {
    // .context() adds a human-readable message to the error chain
    let body = std::fs::read_to_string(url)
        .context("failed to read config file")?;

    let config: serde_json::Value = serde_json::from_str(&body)
        .context("config file contains invalid JSON")?;

    // bail! returns an error immediately
    if config["version"].is_null() {
        bail!("config missing required 'version' field");
    }

    // ensure! is like assert! but returns an error instead of panicking
    ensure!(
        config["version"].as_u64().unwrap_or(0) >= 2,
        "config version must be >= 2, got {:?}",
        config["version"]
    );

    Ok(config)
}

fn main() -> Result<()> {
    let config = fetch_config("config.json")?;
    println!("Loaded config v{}", config["version"]);
    Ok(())
    // If main returns Err, anyhow prints the full error chain:
    //   Error: failed to read config file
    //   Caused by: No such file or directory (os error 2)
}
```

When to use which:
- `thiserror` -- you are writing a library; callers need to inspect/match error variants
- `anyhow` -- you are writing an application; you just want to propagate and display errors
- You can combine them: a library defines errors with `thiserror`, and the application wraps everything in `anyhow::Error`

Key `anyhow` features:
- `context()` / `with_context()` -- add messages to the chain
- `bail!` -- early return with a formatted error
- `ensure!` -- conditional bail
- Automatic backtrace capture (on nightly or with RUST_BACKTRACE=1)'''
    },
    {
        "instruction": r'''Show how to convert between different error types in Rust using From and Into traits manually, without thiserror.''',
        "output": r'''You can implement `From<SourceError>` for your error type to enable automatic conversion with the `?` operator.

```rust
use std::fmt;
use std::io;
use std::num::ParseIntError;

#[derive(Debug)]
enum ConfigError {
    Io(io::Error),
    Parse(ParseIntError),
    Missing(String),
}

// Implement Display (required by std::error::Error)
impl fmt::Display for ConfigError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ConfigError::Io(e) => write!(f, "I/O error: {e}"),
            ConfigError::Parse(e) => write!(f, "parse error: {e}"),
            ConfigError::Missing(key) => write!(f, "missing key: {key}"),
        }
    }
}

// Implement std::error::Error with source chaining
impl std::error::Error for ConfigError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            ConfigError::Io(e) => Some(e),
            ConfigError::Parse(e) => Some(e),
            ConfigError::Missing(_) => None,
        }
    }
}

// From impls enable the ? operator to convert automatically
impl From<io::Error> for ConfigError {
    fn from(e: io::Error) -> Self {
        ConfigError::Io(e)
    }
}

impl From<ParseIntError> for ConfigError {
    fn from(e: ParseIntError) -> Self {
        ConfigError::Parse(e)
    }
}

fn read_port(path: &str) -> Result<u16, ConfigError> {
    let content = std::fs::read_to_string(path)?; // io::Error -> ConfigError::Io
    let port: u16 = content.trim().parse()?;       // ParseIntError -> ConfigError::Parse
    if port == 0 {
        return Err(ConfigError::Missing("port must be nonzero".into()));
    }
    Ok(port)
}

fn main() {
    match read_port("port.txt") {
        Ok(p) => println!("Port: {p}"),
        Err(e) => {
            eprintln!("Error: {e}");
            // Walk the error chain
            let mut source = std::error::Error::source(&e);
            while let Some(cause) = source {
                eprintln!("  caused by: {cause}");
                source = cause.source();
            }
        }
    }
}
```

This is exactly what `thiserror` generates with its derive macro. Writing it manually helps you understand the pattern: `From` conversions power the `?` operator, and `source()` enables error chain inspection.'''
    },
    {
        "instruction": r'''How do I handle multiple error types in a Rust function that calls different libraries? Show the map_err pattern.''',
        "output": r'''When `From` conversions are not set up or you need to transform errors with additional context, use `map_err` to convert explicitly.

```rust
use std::io;

#[derive(Debug)]
enum ServiceError {
    Database(String),
    Network(String),
    InvalidInput(String),
}

impl std::fmt::Display for ServiceError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ServiceError::Database(msg) => write!(f, "db: {msg}"),
            ServiceError::Network(msg) => write!(f, "net: {msg}"),
            ServiceError::InvalidInput(msg) => write!(f, "input: {msg}"),
        }
    }
}

// Simulate external functions with their own error types
fn db_query(sql: &str) -> Result<Vec<String>, io::Error> {
    if sql.contains("DROP") {
        return Err(io::Error::new(io::ErrorKind::PermissionDenied, "forbidden"));
    }
    Ok(vec!["row1".into(), "row2".into()])
}

fn http_get(url: &str) -> Result<String, io::Error> {
    if url.is_empty() {
        return Err(io::Error::new(io::ErrorKind::InvalidInput, "empty URL"));
    }
    Ok(format!("response from {url}"))
}

fn process_user(user_id: u32) -> Result<String, ServiceError> {
    // Validate input -- no external error to convert
    if user_id == 0 {
        return Err(ServiceError::InvalidInput("user_id cannot be zero".into()));
    }

    // map_err converts io::Error into our ServiceError variant
    let rows = db_query(&format!("SELECT * FROM users WHERE id = {user_id}"))
        .map_err(|e| ServiceError::Database(format!("query failed: {e}")))?;

    let profile_url = rows.first()
        .ok_or_else(|| ServiceError::Database("user not found".into()))?;

    // Different map_err for network errors
    let profile = http_get(profile_url)
        .map_err(|e| ServiceError::Network(format!("fetch failed: {e}")))?;

    Ok(profile)
}

fn main() {
    // Using and_then for chaining
    let result = [1, 0, 42]
        .iter()
        .map(|id| process_user(*id))
        .collect::<Vec<_>>();

    for (i, r) in result.iter().enumerate() {
        match r {
            Ok(profile) => println!("[{i}] {profile}"),
            Err(e) => eprintln!("[{i}] Error: {e}"),
        }
    }
}
```

Use `map_err` when:
- You want to add context to the error message
- The source error type does not have a `From` impl for your error
- You need to map to different variants based on the call site'''
    },
]
