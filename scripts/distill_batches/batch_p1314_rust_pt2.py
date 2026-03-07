"""Rust training pairs (part 2): macros, serde, web, CLI, unsafe, testing."""

PAIRS = [
    (
        "rust/declarative-macros",
        r'''How do I write a declarative macro in Rust using macro_rules! that generates getter methods for struct fields?''',
        r'''<think>
The user wants a macro_rules! macro that auto-generates getter methods. This requires matching on
repeated struct field patterns and emitting an impl block. I'll use the $(...)* repetition syntax
to match multiple field names and types. The macro needs to accept the struct name, field names,
and their types, then expand into getter functions returning references.
Key considerations: hygiene, the correct fragment specifiers (ident, ty), and proper repetition.
</think>

You can use `macro_rules!` with repetition to generate getters:

```rust
macro_rules! with_getters {
    ($name:ident { $($field:ident : $ty:ty),* $(,)? }) => {
        pub struct $name {
            $($field: $ty),*
        }

        impl $name {
            $(
                pub fn $field(&self) -> &$ty {
                    &self.$field
                }
            )*
        }
    };
}

with_getters!(Config {
    host: String,
    port: u16,
    debug: bool,
});

fn main() {
    let cfg = Config {
        host: "localhost".into(),
        port: 8080,
        debug: true,
    };
    println!("{}:{} (debug={})", cfg.host(), cfg.port(), cfg.debug());
}
```

Fragment specifiers used:
- `$name:ident` matches an identifier (the struct name)
- `$field:ident` and `$ty:ty` match field names and types
- `$(,)?` allows an optional trailing comma
- `$(...)*` repeats for each field'''
    ),
    (
        "rust/proc-derive-macros",
        r'''How do I create a custom derive macro in Rust? I want a #[derive(Describe)] that generates a method returning the struct's field names as strings.''',
        r'''<think>
Proc macros live in a separate crate with proc-macro = true. I need to parse the DeriveInput using
syn, extract field names from a named struct, then generate code via quote! that implements a trait
with a method returning field names as a slice. The trait should be defined in the main crate or a
shared crate, while the macro crate handles code generation.
Key pieces: syn for parsing, quote for code generation, proc_macro2 for token manipulation.
This is advanced Rust metaprogramming but follows a well-established pattern.
</think>

You need two crates: one for the proc macro, one for the trait definition.

**1. Macro crate (`describe_derive/Cargo.toml`):**
```toml
[lib]
proc-macro = true

[dependencies]
syn = { version = "2", features = ["full"] }
quote = "1"
```

**2. Macro implementation (`describe_derive/src/lib.rs`):**
```rust
use proc_macro::TokenStream;
use quote::quote;
use syn::{parse_macro_input, DeriveInput, Data, Fields};

#[proc_macro_derive(Describe)]
pub fn derive_describe(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as DeriveInput);
    let name = &input.ident;

    let field_names: Vec<String> = match &input.data {
        Data::Struct(data) => match &data.fields {
            Fields::Named(fields) => fields.named.iter()
                .map(|f| f.ident.as_ref().unwrap().to_string())
                .collect(),
            _ => vec![],
        },
        _ => panic!("Describe only supports structs with named fields"),
    };

    let expanded = quote! {
        impl #name {
            pub fn field_names() -> &'static [&'static str] {
                &[#(#field_names),*]
            }
        }
    };
    expanded.into()
}
```

**3. Usage:**
```rust
use describe_derive::Describe;

#[derive(Describe)]
struct User {
    name: String,
    email: String,
    age: u32,
}

fn main() {
    println!("{:?}", User::field_names());
    // ["name", "email", "age"]
}
```'''
    ),
    (
        "rust/serde-basics",
        r'''Show me how to use serde for JSON serialization and deserialization in Rust, including renaming fields and handling optional values.''',
        r'''<think>
Serde is the standard serialization framework in Rust. The user wants basic serialize/deserialize
with JSON, plus field renaming and optional handling. I'll show Serialize/Deserialize derives,
the #[serde(rename)], #[serde(rename_all)], and #[serde(default)] / Option<T> patterns.
Dependencies needed: serde with derive feature, serde_json.
This is intermediate-level Rust — serde is one of the most-used crates in the ecosystem.
</think>

Add to `Cargo.toml`:
```toml
[dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

```rust
use serde::{Serialize, Deserialize};

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct ApiResponse {
    status_code: u16,
    #[serde(rename = "msg")]
    message: String,
    #[serde(default)]
    retry_after: Option<u64>,
    #[serde(skip_serializing_if = "Vec::is_empty", default)]
    errors: Vec<String>,
}

fn main() -> Result<(), serde_json::Error> {
    // Deserialize from JSON
    let json = r#"{"statusCode": 200, "msg": "OK"}"#;
    let resp: ApiResponse = serde_json::from_str(json)?;
    println!("{:?}", resp);
    // retry_after is None, errors is empty vec (both from #[serde(default)])

    // Serialize to JSON
    let output = serde_json::to_string_pretty(&resp)?;
    println!("{output}");
    // "errors" is omitted thanks to skip_serializing_if

    // Deserialize with all fields
    let full = r#"{
        "statusCode": 429,
        "msg": "Rate limited",
        "retryAfter": 30,
        "errors": ["too many requests"]
    }"#;
    let resp: ApiResponse = serde_json::from_str(full)?;
    println!("{:?}", resp);
    Ok(())
}
```

Key attributes:
- `rename_all = "camelCase"` converts `snake_case` fields to `camelCase` in JSON
- `rename = "msg"` overrides a single field's JSON key
- `default` uses `Default::default()` when the field is missing
- `skip_serializing_if` omits the field during serialization when the predicate is true'''
    ),
    (
        "rust/serde-custom-deserializer",
        r'''How do I write a custom serde deserializer in Rust? I have a JSON field that can be either a string "none" or a number, and I want to parse it into an Option<u64>.''',
        r'''<think>
Custom deserialization in serde requires implementing a Visitor. The field can be a string "none" or
a number, so the visitor needs to handle both visit_str and visit_u64. I'll use a deserialize_with
function approach, which is simpler than implementing Deserialize on a whole type.
The visitor pattern: define a struct implementing serde::de::Visitor, implement the expected method
and the visit_* methods for each possible input type. Then wrap it in a function usable with
#[serde(deserialize_with = "...")]. This is advanced serde usage.
</think>

Use `#[serde(deserialize_with = "...")]` with a custom visitor:

```rust
use serde::{Serialize, Deserialize, Deserializer};
use serde::de::{self, Visitor};
use std::fmt;

fn string_or_number<'de, D>(deserializer: D) -> Result<Option<u64>, D::Error>
where
    D: Deserializer<'de>,
{
    struct StringOrNumber;

    impl<'de> Visitor<'de> for StringOrNumber {
        type Value = Option<u64>;

        fn expecting(&self, f: &mut fmt::Formatter) -> fmt::Result {
            write!(f, r#"a number or the string "none""#)
        }

        fn visit_u64<E: de::Error>(self, v: u64) -> Result<Self::Value, E> {
            Ok(Some(v))
        }

        fn visit_i64<E: de::Error>(self, v: i64) -> Result<Self::Value, E> {
            u64::try_from(v)
                .map(Some)
                .map_err(|_| E::custom("negative number"))
        }

        fn visit_str<E: de::Error>(self, v: &str) -> Result<Self::Value, E> {
            match v {
                "none" | "null" | "" => Ok(None),
                other => other.parse::<u64>()
                    .map(Some)
                    .map_err(|_| E::custom(format!("unknown string: {other}"))),
            }
        }
    }

    deserializer.deserialize_any(StringOrNumber)
}

#[derive(Debug, Serialize, Deserialize)]
struct Config {
    name: String,
    #[serde(deserialize_with = "string_or_number")]
    timeout: Option<u64>,
}

fn main() -> Result<(), serde_json::Error> {
    let a: Config = serde_json::from_str(r#"{"name":"a","timeout":30}"#)?;
    let b: Config = serde_json::from_str(r#"{"name":"b","timeout":"none"}"#)?;
    let c: Config = serde_json::from_str(r#"{"name":"c","timeout":"500"}"#)?;
    println!("{a:?}"); // timeout: Some(30)
    println!("{b:?}"); // timeout: None
    println!("{c:?}"); // timeout: Some(500)
    Ok(())
}
```

The visitor handles three JSON representations:
- Number literal (`30`) via `visit_u64`
- String `"none"` via `visit_str` returning `None`
- Numeric string `"500"` via `visit_str` with parsing'''
    ),
    (
        "rust/axum-web-basics",
        r'''Show me how to set up a basic Axum web server in Rust with a few routes including JSON request/response handling.''',
        r'''<think>
Axum is the modern Rust web framework built on top of tokio and tower. The user wants basic routing
and JSON handling. I'll show creating a Router with GET and POST routes, using Json extractor for
request bodies and Json wrapper for responses. Need to show shared state with State extractor too.
Dependencies: axum, tokio with full features, serde. This is intermediate-level web development
in Rust. Axum 0.7+ uses its own listener instead of hyper directly.
</think>

Add to `Cargo.toml`:
```toml
[dependencies]
axum = "0.8"
tokio = { version = "1", features = ["full"] }
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

```rust
use axum::{
    Router,
    Json,
    extract::{Path, State},
    routing::{get, post},
    http::StatusCode,
};
use serde::{Deserialize, Serialize};
use std::sync::{Arc, Mutex};

#[derive(Clone)]
struct AppState {
    items: Arc<Mutex<Vec<Item>>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
struct Item {
    id: u64,
    name: String,
}

#[derive(Deserialize)]
struct CreateItem {
    name: String,
}

async fn health() -> &'static str {
    "OK"
}

async fn list_items(State(state): State<AppState>) -> Json<Vec<Item>> {
    let items = state.items.lock().unwrap();
    Json(items.clone())
}

async fn create_item(
    State(state): State<AppState>,
    Json(payload): Json<CreateItem>,
) -> (StatusCode, Json<Item>) {
    let mut items = state.items.lock().unwrap();
    let item = Item {
        id: items.len() as u64 + 1,
        name: payload.name,
    };
    items.push(item.clone());
    (StatusCode::CREATED, Json(item))
}

async fn get_item(
    State(state): State<AppState>,
    Path(id): Path<u64>,
) -> Result<Json<Item>, StatusCode> {
    let items = state.items.lock().unwrap();
    items.iter()
        .find(|i| i.id == id)
        .cloned()
        .map(Json)
        .ok_or(StatusCode::NOT_FOUND)
}

#[tokio::main]
async fn main() {
    let state = AppState {
        items: Arc::new(Mutex::new(vec![])),
    };

    let app = Router::new()
        .route("/health", get(health))
        .route("/items", get(list_items).post(create_item))
        .route("/items/{id}", get(get_item))
        .with_state(state);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000").await.unwrap();
    println!("Listening on :3000");
    axum::serve(listener, app).await.unwrap();
}
```

Axum's key concepts:
- **Extractors** (`Json`, `Path`, `State`) pull data from requests automatically
- **Handlers** are async functions whose arguments are extractors
- Return types implement `IntoResponse` (tuples, `Json<T>`, `StatusCode`, etc.)
- **State** is shared via `with_state()` and must be `Clone`'''
    ),
    (
        "rust/axum-middleware-extractors",
        r'''How do I write custom middleware and extractors in Axum? I want to extract an API key from headers and reject unauthorized requests.''',
        r'''<think>
The user wants custom middleware/extractors in Axum. The idiomatic Axum approach is to use a custom
extractor by implementing FromRequestParts. This lets you pull the API key from headers and return
an error if it's missing or invalid. I'll show both the extractor approach (preferred) and a
middleware layer approach using axum::middleware::from_fn for comparison.
This is advanced Axum usage — understanding the extractor trait system is key.
</think>

The cleanest approach is a custom extractor via `FromRequestParts`:

```rust
use axum::{
    Router, Json,
    extract::FromRequestParts,
    http::{request::Parts, StatusCode, header},
    routing::get,
    response::{IntoResponse, Response},
    middleware::{self, Next},
};

// -- Custom Extractor approach (preferred) --

struct ApiKey(String);

#[axum::async_trait]
impl<S: Send + Sync> FromRequestParts<S> for ApiKey {
    type Rejection = Response;

    async fn from_request_parts(parts: &mut Parts, _state: &S) -> Result<Self, Self::Rejection> {
        let key = parts.headers
            .get("x-api-key")
            .and_then(|v| v.to_str().ok())
            .ok_or_else(|| {
                (StatusCode::UNAUTHORIZED, "Missing x-api-key header").into_response()
            })?;

        if key.len() < 16 {
            return Err(
                (StatusCode::FORBIDDEN, "Invalid API key").into_response()
            );
        }

        Ok(ApiKey(key.to_string()))
    }
}

async fn protected(ApiKey(key): ApiKey) -> String {
    format!("Authenticated with key: {}...", &key[..8])
}

// -- Middleware approach (for cross-cutting concerns) --

async fn logging_middleware(req: axum::extract::Request, next: Next) -> Response {
    let method = req.method().clone();
    let uri = req.uri().clone();
    let start = std::time::Instant::now();

    let response = next.run(req).await;

    println!("{method} {uri} -> {} ({:?})", response.status(), start.elapsed());
    response
}

#[tokio::main]
async fn main() {
    let app = Router::new()
        .route("/protected", get(protected))
        .route("/public", get(|| async { "Hello" }))
        .layer(middleware::from_fn(logging_middleware));

    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000").await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
```

**When to use which:**
- **Extractors**: per-route concerns (auth, parsing custom headers). The handler declares what it needs.
- **Middleware layers**: cross-cutting concerns (logging, CORS, compression) applied to many routes.
- Extractors compose naturally — just add them as handler parameters.'''
    ),
    (
        "rust/actix-web-handlers",
        r'''Show me how to build an Actix-web server with shared mutable state and JSON handlers.''',
        r'''<think>
Actix-web is another major Rust web framework. Shared state uses web::Data<T> wrapping an Arc or
Mutex. Handlers use extractors like web::Json, web::Path, web::Data. I'll show a simple CRUD-like
API with shared state using web::Data<Mutex<Vec<T>>>. Key difference from Axum: actix-web uses
attribute macros for routes and has its own runtime (actix-rt).
This is intermediate-level Rust web development.
</think>

```toml
[dependencies]
actix-web = "4"
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

```rust
use actix_web::{web, App, HttpServer, HttpResponse, middleware::Logger};
use serde::{Deserialize, Serialize};
use std::sync::Mutex;

#[derive(Debug, Clone, Serialize, Deserialize)]
struct Todo {
    id: u64,
    title: String,
    done: bool,
}

#[derive(Deserialize)]
struct CreateTodo {
    title: String,
}

struct AppState {
    todos: Mutex<Vec<Todo>>,
}

async fn list_todos(state: web::Data<AppState>) -> HttpResponse {
    let todos = state.todos.lock().unwrap();
    HttpResponse::Ok().json(&*todos)
}

async fn create_todo(
    state: web::Data<AppState>,
    body: web::Json<CreateTodo>,
) -> HttpResponse {
    let mut todos = state.todos.lock().unwrap();
    let todo = Todo {
        id: todos.len() as u64 + 1,
        title: body.into_inner().title,
        done: false,
    };
    todos.push(todo.clone());
    HttpResponse::Created().json(todo)
}

async fn toggle_todo(
    state: web::Data<AppState>,
    path: web::Path<u64>,
) -> HttpResponse {
    let id = path.into_inner();
    let mut todos = state.todos.lock().unwrap();
    match todos.iter_mut().find(|t| t.id == id) {
        Some(todo) => {
            todo.done = !todo.done;
            HttpResponse::Ok().json(todo.clone())
        }
        None => HttpResponse::NotFound().finish(),
    }
}

#[actix_web::main]
async fn main() -> std::io::Result<()> {
    env_logger::init();

    let state = web::Data::new(AppState {
        todos: Mutex::new(vec![]),
    });

    HttpServer::new(move || {
        App::new()
            .wrap(Logger::default())
            .app_data(state.clone())
            .route("/todos", web::get().to(list_todos))
            .route("/todos", web::post().to(create_todo))
            .route("/todos/{id}/toggle", web::patch().to(toggle_todo))
    })
    .bind("0.0.0.0:8080")?
    .run()
    .await
}
```

Key differences from Axum:
- State is wrapped in `web::Data<T>` (internally `Arc`)
- `HttpServer::new` takes a closure that builds the `App` per worker thread
- Route handlers return `HttpResponse` explicitly
- Uses `actix-rt` runtime, not raw tokio (though compatible)'''
    ),
    (
        "rust/sqlx-async-queries",
        r'''How do I use SQLx in Rust for async database queries with compile-time checked SQL?''',
        r'''<think>
SQLx is the async SQL toolkit for Rust with compile-time query checking. I need to show the
connection pool setup, basic CRUD operations using sqlx::query and sqlx::query_as macros, and
mention the offline mode for CI. The compile-time checking feature requires DATABASE_URL at build
time or prepared query data. I'll use PostgreSQL as the example database.
This is intermediate-to-advanced: async + database + compile-time verification.
</think>

```toml
[dependencies]
sqlx = { version = "0.8", features = ["runtime-tokio", "postgres", "macros"] }
tokio = { version = "1", features = ["full"] }
serde = { version = "1", features = ["derive"] }
```

Set `DATABASE_URL` in `.env` for compile-time checking:
```
DATABASE_URL=postgres://user:pass@localhost/mydb
```

```rust
use sqlx::{PgPool, FromRow};
use serde::Serialize;

#[derive(Debug, FromRow, Serialize)]
struct User {
    id: i64,
    name: String,
    email: String,
}

async fn setup_db(pool: &PgPool) -> Result<(), sqlx::Error> {
    sqlx::query(
        "CREATE TABLE IF NOT EXISTS users (
            id BIGSERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL
        )"
    )
    .execute(pool)
    .await?;
    Ok(())
}

// Compile-time checked query returning typed results
async fn get_user(pool: &PgPool, id: i64) -> Result<Option<User>, sqlx::Error> {
    sqlx::query_as!(User, "SELECT id, name, email FROM users WHERE id = $1", id)
        .fetch_optional(pool)
        .await
}

async fn create_user(pool: &PgPool, name: &str, email: &str) -> Result<User, sqlx::Error> {
    sqlx::query_as!(
        User,
        "INSERT INTO users (name, email) VALUES ($1, $2) RETURNING id, name, email",
        name, email
    )
    .fetch_one(pool)
    .await
}

async fn list_users(pool: &PgPool, limit: i64) -> Result<Vec<User>, sqlx::Error> {
    sqlx::query_as!(User, "SELECT id, name, email FROM users ORDER BY id LIMIT $1", limit)
        .fetch_all(pool)
        .await
}

// Dynamic queries when compile-time checking isn't possible
async fn search_users(pool: &PgPool, term: &str) -> Result<Vec<User>, sqlx::Error> {
    let pattern = format!("%{term}%");
    sqlx::query_as::<_, User>("SELECT id, name, email FROM users WHERE name ILIKE $1")
        .bind(&pattern)
        .fetch_all(pool)
        .await
}

#[tokio::main]
async fn main() -> Result<(), sqlx::Error> {
    let pool = PgPool::connect("postgres://user:pass@localhost/mydb").await?;
    setup_db(&pool).await?;

    let user = create_user(&pool, "Alice", "alice@example.com").await?;
    println!("Created: {user:?}");

    let found = get_user(&pool, user.id).await?;
    println!("Found: {found:?}");

    // For CI without a database, run: cargo sqlx prepare
    // This saves query metadata to .sqlx/ for offline checking
    Ok(())
}
```

Key features:
- `query_as!` checks SQL syntax and column types at compile time
- `query_as::<_, T>()` with `.bind()` for dynamic queries (runtime checked)
- `cargo sqlx prepare` generates offline data for CI builds without a live database'''
    ),
    (
        "rust/clap-cli-tool",
        r'''How do I build a CLI tool in Rust using clap with the derive API?''',
        r'''<think>
Clap's derive API is the ergonomic way to build CLI tools in Rust. I'll show a realistic CLI with
subcommands, flags, optional arguments, and value enums. The derive macro generates the argument
parser from struct/enum definitions. This is intermediate Rust — clap is the standard CLI library.
I should show Parser derive on the main struct and Subcommand derive on the enum.
</think>

```toml
[dependencies]
clap = { version = "4", features = ["derive"] }
```

```rust
use clap::{Parser, Subcommand, ValueEnum};
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "taskr", version, about = "A simple task manager")]
struct Cli {
    #[command(subcommand)]
    command: Commands,

    /// Enable verbose output
    #[arg(short, long, global = true)]
    verbose: bool,
}

#[derive(Subcommand)]
enum Commands {
    /// Add a new task
    Add {
        /// Task description
        description: String,

        /// Priority level
        #[arg(short, long, default_value = "medium")]
        priority: Priority,

        /// Tags for the task
        #[arg(short, long, num_args = 1..)]
        tags: Vec<String>,
    },
    /// List all tasks
    List {
        /// Filter by priority
        #[arg(short, long)]
        priority: Option<Priority>,

        /// Output format
        #[arg(short, long, default_value = "table")]
        format: OutputFormat,
    },
    /// Import tasks from file
    Import {
        /// Path to JSON file
        #[arg(value_name = "FILE")]
        path: PathBuf,

        /// Overwrite existing tasks
        #[arg(long)]
        overwrite: bool,
    },
}

#[derive(Clone, ValueEnum)]
enum Priority {
    Low,
    Medium,
    High,
    Critical,
}

#[derive(Clone, ValueEnum)]
enum OutputFormat {
    Table,
    Json,
    Csv,
}

fn main() {
    let cli = Cli::parse();

    match cli.command {
        Commands::Add { description, priority, tags } => {
            if cli.verbose {
                println!("Adding task with {} tags", tags.len());
            }
            println!("Added: {description} (priority: {:?})", priority as u8);
        }
        Commands::List { priority, format } => {
            println!("Listing tasks...");
        }
        Commands::Import { path, overwrite } => {
            println!("Importing from {}", path.display());
        }
    }
}
```

Usage:
```bash
taskr add "Fix the bug" --priority high --tags backend urgent
taskr list --priority critical --format json
taskr import tasks.json --overwrite
taskr --verbose add "Review PR"
```

Key features:
- `#[command(subcommand)]` creates `taskr <subcommand>` style CLI
- `#[arg(global = true)]` makes flags available to all subcommands
- `ValueEnum` auto-generates string-to-enum parsing with validation
- Clap auto-generates `--help`, `--version`, and error messages'''
    ),
    (
        "rust/file-io-buffered",
        r'''What are the best practices for file I/O in Rust, including buffered reading and writing?''',
        r'''<think>
File I/O in Rust uses std::fs and std::io. Key patterns: BufReader/BufWriter for performance,
read_to_string for small files, line-by-line iteration for large files. I should show multiple
approaches: simple read/write, buffered I/O, and the convenience functions in std::fs.
This is intermediate Rust — understanding the Read/Write traits and buffering is important.
</think>

```rust
use std::fs::{self, File, OpenOptions};
use std::io::{self, BufRead, BufReader, BufWriter, Read, Write};
use std::path::Path;

// Simple: read entire file into a String
fn read_small_file(path: &Path) -> io::Result<String> {
    fs::read_to_string(path)
}

// Buffered: process large file line by line (minimal memory)
fn process_large_file(path: &Path) -> io::Result<usize> {
    let file = File::open(path)?;
    let reader = BufReader::new(file);
    let mut count = 0;
    for line in reader.lines() {
        let line = line?;
        if !line.is_empty() {
            count += 1;
        }
    }
    Ok(count)
}

// Buffered write (flushes automatically when buffer is full or on drop)
fn write_csv(path: &Path, rows: &[(String, u64)]) -> io::Result<()> {
    let file = File::create(path)?;
    let mut writer = BufWriter::new(file);
    writeln!(writer, "name,value")?;
    for (name, value) in rows {
        writeln!(writer, "{name},{value}")?;
    }
    // BufWriter flushes remaining buffer on drop,
    // but explicit flush catches write errors
    writer.flush()?;
    Ok(())
}

// Append to existing file
fn append_log(path: &Path, message: &str) -> io::Result<()> {
    let mut file = OpenOptions::new()
        .create(true)
        .append(true)
        .open(path)?;
    writeln!(file, "{message}")?;
    Ok(())
}

// Read binary file in chunks
fn hash_file(path: &Path) -> io::Result<u64> {
    let file = File::open(path)?;
    let mut reader = BufReader::with_capacity(64 * 1024, file); // 64KB buffer
    let mut hash: u64 = 0;
    let mut buf = [0u8; 8192];
    loop {
        let n = reader.read(&mut buf)?;
        if n == 0 { break; }
        for &byte in &buf[..n] {
            hash = hash.wrapping_mul(31).wrapping_add(byte as u64);
        }
    }
    Ok(hash)
}

fn main() -> io::Result<()> {
    // Quick one-liner write
    fs::write("hello.txt", "Hello, Rust!\n")?;

    let content = read_small_file(Path::new("hello.txt"))?;
    println!("{content}");

    let rows = vec![("alpha".into(), 1u64), ("beta".into(), 2)];
    write_csv(Path::new("data.csv"), &rows)?;

    Ok(())
}
```

Guidelines:
- **Small files** (<few MB): use `fs::read_to_string` / `fs::write`
- **Large files**: use `BufReader` line-by-line or chunked reads
- **Always buffer**: raw `File` does a syscall per write — `BufWriter` batches them
- **Explicit `flush()`**: catches errors that silent drop-flush would ignore'''
    ),
    (
        "rust/tokio-tcp-networking",
        r'''Show me how to build a simple TCP echo server and client using tokio in Rust.''',
        r'''<think>
Tokio TCP networking uses TcpListener and TcpStream with async read/write. For an echo server,
I'll accept connections, spawn a task per connection, and read/write in a loop. The client connects
and sends data. I should use tokio::io::AsyncReadExt and AsyncWriteExt traits.
Key pattern: split the stream into reader/writer halves for concurrent read/write.
This is intermediate async Rust.
</think>

```rust
// server.rs
use tokio::net::TcpListener;
use tokio::io::{AsyncReadExt, AsyncWriteExt};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let listener = TcpListener::bind("127.0.0.1:8080").await?;
    println!("Echo server listening on :8080");

    loop {
        let (mut socket, addr) = listener.accept().await?;
        println!("Connection from {addr}");

        tokio::spawn(async move {
            let mut buf = vec![0u8; 4096];
            loop {
                let n = match socket.read(&mut buf).await {
                    Ok(0) => {
                        println!("{addr} disconnected");
                        return;
                    }
                    Ok(n) => n,
                    Err(e) => {
                        eprintln!("{addr} read error: {e}");
                        return;
                    }
                };

                if let Err(e) = socket.write_all(&buf[..n]).await {
                    eprintln!("{addr} write error: {e}");
                    return;
                }
            }
        });
    }
}
```

```rust
// client.rs
use tokio::net::TcpStream;
use tokio::io::{self, AsyncReadExt, AsyncWriteExt, AsyncBufReadExt, BufReader};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    let stream = TcpStream::connect("127.0.0.1:8080").await?;
    let (reader, mut writer) = stream.into_split();

    // Spawn task to print responses
    let print_handle = tokio::spawn(async move {
        let mut reader = BufReader::new(reader);
        let mut line = String::new();
        loop {
            line.clear();
            match reader.read_line(&mut line).await {
                Ok(0) | Err(_) => break,
                Ok(_) => print!("Echo: {line}"),
            }
        }
    });

    // Read stdin and send to server
    let stdin = BufReader::new(io::stdin());
    let mut lines = stdin.lines();
    while let Ok(Some(line)) = lines.next_line().await {
        writer.write_all(line.as_bytes()).await?;
        writer.write_all(b"\n").await?;
    }

    drop(writer); // close write half, triggering server disconnect
    let _ = print_handle.await;
    Ok(())
}
```

Key patterns:
- `into_split()` separates read/write halves for concurrent use in different tasks
- `tokio::spawn` creates a new async task per connection (server) or per concern (client)
- Always handle `Ok(0)` from `read()` — it means the connection closed
- Use `write_all()` not `write()` to ensure all bytes are sent'''
    ),
    (
        "rust/unit-testing-patterns",
        r'''What are the common patterns for unit testing in Rust? Show me how to test with setup/teardown, test helpers, and should_panic.''',
        r'''<think>
Rust's built-in test framework uses #[cfg(test)] modules. I should cover: basic assertions, custom
error messages, #[should_panic], Result-returning tests, test helper functions, and setup patterns.
Rust doesn't have setup/teardown like JUnit but you can use helper functions or Drop-based RAII.
This is intermediate Rust — testing is core to the language.
</think>

```rust
pub struct UserStore {
    users: Vec<(u64, String)>,
}

impl UserStore {
    pub fn new() -> Self {
        Self { users: vec![] }
    }

    pub fn add(&mut self, name: &str) -> u64 {
        let id = self.users.len() as u64 + 1;
        self.users.push((id, name.to_string()));
        id
    }

    pub fn get(&self, id: u64) -> Option<&str> {
        self.users.iter()
            .find(|(uid, _)| *uid == id)
            .map(|(_, name)| name.as_str())
    }

    pub fn remove(&mut self, id: u64) -> Result<(), String> {
        let pos = self.users.iter().position(|(uid, _)| *uid == id)
            .ok_or_else(|| format!("User {id} not found"))?;
        self.users.remove(pos);
        Ok(())
    }

    pub fn parse_id(s: &str) -> u64 {
        s.parse().expect("valid numeric ID")
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // Helper: create a store pre-populated with test data
    fn setup_store() -> UserStore {
        let mut store = UserStore::new();
        store.add("Alice");
        store.add("Bob");
        store.add("Charlie");
        store
    }

    #[test]
    fn test_add_and_get() {
        let mut store = UserStore::new();
        let id = store.add("Dave");
        assert_eq!(store.get(id), Some("Dave"));
    }

    #[test]
    fn test_get_nonexistent_returns_none() {
        let store = setup_store();
        assert!(store.get(999).is_none(), "ID 999 should not exist");
    }

    #[test]
    fn test_remove_existing() -> Result<(), String> {
        // Tests can return Result — Err fails the test with the message
        let mut store = setup_store();
        store.remove(2)?;
        assert_eq!(store.get(2), None);
        Ok(())
    }

    #[test]
    fn test_remove_nonexistent_returns_error() {
        let mut store = setup_store();
        let result = store.remove(42);
        assert!(result.is_err());
        assert_eq!(result.unwrap_err(), "User 42 not found");
    }

    #[test]
    #[should_panic(expected = "valid numeric ID")]
    fn test_parse_id_panics_on_invalid() {
        UserStore::parse_id("not-a-number");
    }

    #[test]
    #[ignore] // Skipped by default, run with: cargo test -- --ignored
    fn test_slow_operation() {
        std::thread::sleep(std::time::Duration::from_secs(5));
        assert!(true);
    }

    // Parameterized testing via a helper
    #[test]
    fn test_multiple_cases() {
        let cases = [("1", 1u64), ("42", 42), ("0", 0)];
        for (input, expected) in cases {
            assert_eq!(
                UserStore::parse_id(input), expected,
                "Failed for input: {input}"
            );
        }
    }
}
```

Patterns:
- **Setup helper**: plain functions like `setup_store()` called at test start
- **RAII teardown**: use `Drop` on a guard struct for cleanup (temp files, etc.)
- **Result tests**: return `Result<(), E>` instead of using `.unwrap()` everywhere
- **`#[should_panic]`**: verifies code panics with an expected message substring
- **`#[ignore]`**: skip slow tests unless explicitly requested'''
    ),
    (
        "rust/integration-testing",
        r'''How do I write integration tests in Rust that test the public API of my library?''',
        r'''<think>
Integration tests in Rust live in the `tests/` directory at the crate root. Each file there is
compiled as a separate crate that can only access the public API. I should show the directory
structure, how to share test utilities via a common module, and how to test async code.
Key point: integration tests are external to the crate, so they import it by name.
This is intermediate Rust — understanding the test organization is important.
</think>

Integration tests live in `tests/` at your crate root and can only use your public API:

```
my_crate/
├── src/
│   └── lib.rs
├── tests/
│   ├── common/
│   │   └── mod.rs      # Shared test helpers
│   ├── user_tests.rs   # Integration test file
│   └── api_tests.rs    # Another test file
└── Cargo.toml
```

**`src/lib.rs`** (the crate under test):
```rust
pub struct Database {
    data: std::collections::HashMap<String, String>,
}

impl Database {
    pub fn new() -> Self {
        Self { data: std::collections::HashMap::new() }
    }
    pub fn set(&mut self, key: &str, value: &str) {
        self.data.insert(key.into(), value.into());
    }
    pub fn get(&self, key: &str) -> Option<&str> {
        self.data.get(key).map(|s| s.as_str())
    }
    pub fn len(&self) -> usize {
        self.data.len()
    }
}
```

**`tests/common/mod.rs`** (shared utilities):
```rust
use my_crate::Database;

pub fn populated_db() -> Database {
    let mut db = Database::new();
    db.set("name", "Alice");
    db.set("role", "admin");
    db
}
```

**`tests/user_tests.rs`**:
```rust
mod common;

use my_crate::Database;

#[test]
fn test_empty_database() {
    let db = Database::new();
    assert_eq!(db.len(), 0);
    assert_eq!(db.get("anything"), None);
}

#[test]
fn test_set_and_get() {
    let mut db = Database::new();
    db.set("key", "value");
    assert_eq!(db.get("key"), Some("value"));
}

#[test]
fn test_populated_db_from_helper() {
    let db = common::populated_db();
    assert_eq!(db.len(), 2);
    assert_eq!(db.get("name"), Some("Alice"));
}

#[test]
fn test_overwrite_value() {
    let mut db = common::populated_db();
    db.set("name", "Bob");
    assert_eq!(db.get("name"), Some("Bob"));
    assert_eq!(db.len(), 2); // no duplicate key
}
```

**Run specific test files:**
```bash
cargo test --test user_tests            # run only user_tests.rs
cargo test --test api_tests             # run only api_tests.rs
cargo test --test user_tests test_empty # run one test in that file
```

Key points:
- Each file in `tests/` is a separate crate — no access to private items
- Shared helpers go in `tests/common/mod.rs` (not `tests/common.rs`, which would be treated as a test file)
- Use `#[cfg(test)]` modules in `src/` for unit tests, `tests/` for integration tests
- Integration tests only apply to library crates (`src/lib.rs`), not binary crates'''
    ),
    (
        "rust/proptest-property-testing",
        r'''How do I use property-based testing in Rust with the proptest crate?''',
        r'''<think>
Property-based testing generates random inputs and checks that invariants hold. The proptest crate
is the standard choice in Rust. I need to show the proptest! macro, custom strategies, and how to
define meaningful properties. Common patterns: roundtrip testing (serialize/deserialize), invariant
checking, and shrinking on failure. This is advanced testing methodology.
</think>

Add to `Cargo.toml`:
```toml
[dev-dependencies]
proptest = "1"
```

```rust
use std::collections::HashMap;

/// A sorted, deduplicated list wrapper
#[derive(Debug, Clone, PartialEq)]
pub struct SortedSet {
    items: Vec<i32>,
}

impl SortedSet {
    pub fn new() -> Self {
        Self { items: vec![] }
    }

    pub fn insert(&mut self, val: i32) {
        if let Err(pos) = self.items.binary_search(&val) {
            self.items.insert(pos, val);
        }
    }

    pub fn contains(&self, val: i32) -> bool {
        self.items.binary_search(&val).is_ok()
    }

    pub fn len(&self) -> usize {
        self.items.len()
    }

    pub fn to_vec(&self) -> Vec<i32> {
        self.items.clone()
    }
}

pub fn encode(s: &str) -> String {
    s.chars().map(|c| (c as u8 + 1) as char).collect()
}

pub fn decode(s: &str) -> String {
    s.chars().map(|c| (c as u8 - 1) as char).collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;
    use proptest::collection::vec as prop_vec;

    proptest! {
        // Property: inserting any value means it's contained
        #[test]
        fn insert_then_contains(val in any::<i32>()) {
            let mut set = SortedSet::new();
            set.insert(val);
            prop_assert!(set.contains(val));
        }

        // Property: the set is always sorted after any insertions
        #[test]
        fn always_sorted(values in prop_vec(any::<i32>(), 0..100)) {
            let mut set = SortedSet::new();
            for v in &values {
                set.insert(*v);
            }
            let result = set.to_vec();
            for window in result.windows(2) {
                prop_assert!(window[0] < window[1], "Not sorted: {:?}", result);
            }
        }

        // Property: no duplicates regardless of input
        #[test]
        fn no_duplicates(values in prop_vec(0..10i32, 0..50)) {
            let mut set = SortedSet::new();
            for v in &values {
                set.insert(*v);
            }
            let unique: std::collections::HashSet<_> = values.iter().collect();
            prop_assert_eq!(set.len(), unique.len());
        }

        // Roundtrip property: decode(encode(s)) == s
        #[test]
        fn encode_decode_roundtrip(s in "[a-y]{0,100}") {
            // Restrict to a-y to avoid overflow at 'z'
            prop_assert_eq!(decode(&encode(&s)), s);
        }

        // Custom strategy: generate (key, value) pairs
        #[test]
        fn hashmap_len_matches(
            pairs in prop_vec(("[a-z]{1,5}", 0..1000u32), 1..20)
        ) {
            let map: HashMap<&str, u32> = pairs.iter()
                .map(|(k, v)| (k.as_str(), *v))
                .collect();
            prop_assert!(map.len() <= pairs.len());
        }
    }
}
```

Key concepts:
- `proptest!` macro runs each test with many random inputs (default 256 cases)
- On failure, proptest **shrinks** the input to find the minimal failing case
- `prop_assert!` / `prop_assert_eq!` replace `assert!` inside proptest blocks
- **Strategies**: `any::<T>()`, ranges (`0..100`), regex strings (`"[a-z]{1,5}"`), `prop_vec()`
- **Roundtrip testing** is the most valuable pattern: `decode(encode(x)) == x`'''
    ),
    (
        "rust/unsafe-raw-pointers",
        r'''When and how do I use unsafe Rust with raw pointers? What are the rules I need to follow?''',
        r'''<think>
Unsafe Rust with raw pointers is an expert topic. The user needs to understand when unsafe is
necessary, the invariants they must uphold, and common patterns. Raw pointers (*const T, *mut T)
can be created safely but dereferenced only in unsafe blocks. Key rules: no aliasing &mut,
valid alignment, no dangling pointers, no data races. I should show practical examples and
emphasize minimizing the unsafe surface area.
</think>

Raw pointers (`*const T`, `*mut T`) are created safely but **dereferenced only in `unsafe`**:

```rust
use std::alloc::{self, Layout};
use std::ptr;

// Example 1: Manual memory allocation (like a simple Vec)
struct RawVec<T> {
    ptr: *mut T,
    len: usize,
    cap: usize,
}

impl<T> RawVec<T> {
    fn new() -> Self {
        Self { ptr: ptr::null_mut(), len: 0, cap: 0 }
    }

    fn push(&mut self, val: T) {
        if self.len == self.cap {
            self.grow();
        }
        unsafe {
            // SAFETY: self.len < self.cap, so ptr.add(self.len) is within allocation
            self.ptr.add(self.len).write(val);
        }
        self.len += 1;
    }

    fn get(&self, index: usize) -> Option<&T> {
        if index < self.len {
            unsafe {
                // SAFETY: index < self.len, all elements 0..len are initialized
                Some(&*self.ptr.add(index))
            }
        } else {
            None
        }
    }

    fn grow(&mut self) {
        let new_cap = if self.cap == 0 { 4 } else { self.cap * 2 };
        let layout = Layout::array::<T>(new_cap).unwrap();
        let new_ptr = if self.cap == 0 {
            unsafe { alloc::alloc(layout) as *mut T }
        } else {
            let old_layout = Layout::array::<T>(self.cap).unwrap();
            unsafe {
                alloc::realloc(self.ptr as *mut u8, old_layout, layout.size()) as *mut T
            }
        };
        assert!(!new_ptr.is_null(), "allocation failed");
        self.ptr = new_ptr;
        self.cap = new_cap;
    }
}

impl<T> Drop for RawVec<T> {
    fn drop(&mut self) {
        if self.cap > 0 {
            unsafe {
                // SAFETY: drop each initialized element, then free memory
                for i in 0..self.len {
                    ptr::drop_in_place(self.ptr.add(i));
                }
                let layout = Layout::array::<T>(self.cap).unwrap();
                alloc::dealloc(self.ptr as *mut u8, layout);
            }
        }
    }
}

// Example 2: Pointer arithmetic for a ring buffer index
fn wrap_ptr<T>(base: *const T, offset: usize, cap: usize) -> *const T {
    unsafe {
        // SAFETY: caller ensures offset < cap and base has cap elements allocated
        base.add(offset % cap)
    }
}

fn main() {
    let mut v = RawVec::new();
    v.push("hello".to_string());
    v.push("world".to_string());
    println!("{}", v.get(0).unwrap()); // hello
    println!("{}", v.get(1).unwrap()); // world
}
```

**Rules you MUST follow in unsafe:**
1. **No dangling pointers** — the pointed-to memory must be valid and allocated
2. **Alignment** — pointers must be properly aligned for the type
3. **No aliasing `&mut`** — never create two `&mut` references to the same memory
4. **Initialize before read** — reading uninitialized memory is UB
5. **Drop before dealloc** — call `drop_in_place` before freeing memory with `Drop` types

**Best practice:** wrap unsafe in a safe API. The unsafe block is small; the safe wrapper enforces invariants. Use `// SAFETY:` comments to document why each unsafe block is correct.'''
    ),
    (
        "rust/ffi-with-c",
        r'''How do I call C functions from Rust and expose Rust functions to C using FFI?''',
        r'''<think>
FFI (Foreign Function Interface) is expert-level Rust. Calling C from Rust uses extern "C" blocks
with unsafe calls. Exposing Rust to C uses #[no_mangle] extern "C" fn. I need to cover: linking
to C libraries, repr(C) structs, handling strings (CStr/CString), null pointers, and the
build.rs/cc crate for compiling C code. Safety concerns are critical here.
</think>

**Calling C from Rust:**

```rust
// Declare the C functions you want to call
extern "C" {
    fn strlen(s: *const std::ffi::c_char) -> usize;
    fn abs(n: i32) -> i32;
}

// For custom C libraries, use a build script
// build.rs:
// fn main() {
//     cc::Build::new().file("src/math.c").compile("math");
// }

use std::ffi::{CStr, CString, c_char, c_int};

fn safe_strlen(s: &str) -> usize {
    let c_str = CString::new(s).expect("string contains null byte");
    unsafe { strlen(c_str.as_ptr()) }
}

fn main() {
    println!("strlen: {}", safe_strlen("hello"));
    println!("abs: {}", unsafe { abs(-42) });
}
```

**Exposing Rust to C:**

```rust
use std::ffi::{CStr, c_char, c_int};
use std::ptr;

/// A struct with C-compatible layout
#[repr(C)]
pub struct Point {
    pub x: f64,
    pub y: f64,
}

/// Exposed to C as: double point_distance(Point a, Point b)
#[no_mangle]
pub extern "C" fn point_distance(a: Point, b: Point) -> f64 {
    ((a.x - b.x).powi(2) + (a.y - b.y).powi(2)).sqrt()
}

/// String handling: C passes a char*, Rust returns a new char*
/// Caller must free the result with `free_rust_string`
#[no_mangle]
pub extern "C" fn greet(name: *const c_char) -> *mut c_char {
    if name.is_null() {
        return ptr::null_mut();
    }
    let name = unsafe {
        // SAFETY: caller guarantees name is a valid null-terminated string
        CStr::from_ptr(name)
    };
    let name = name.to_str().unwrap_or("unknown");
    let greeting = CString::new(format!("Hello, {name}!")).unwrap();
    greeting.into_raw() // transfers ownership to C
}

#[no_mangle]
pub extern "C" fn free_rust_string(s: *mut c_char) {
    if !s.is_null() {
        unsafe {
            // SAFETY: s was created by CString::into_raw
            drop(CString::from_raw(s));
        }
    }
}
```

**Corresponding C header (`mylib.h`):**
```c
typedef struct { double x; double y; } Point;
double point_distance(Point a, Point b);
char* greet(const char* name);
void free_rust_string(char* s);
```

**`Cargo.toml` for a C-callable library:**
```toml
[lib]
crate-type = ["cdylib"]  # produces .so/.dll/.dylib
```

Critical FFI rules:
- Always use `#[repr(C)]` for structs shared across the boundary
- `CString` owns the memory (Rust side), `CStr` borrows it
- Null-check all incoming pointers before dereferencing
- Memory allocated by Rust must be freed by Rust (and vice versa)'''
    ),
    (
        "rust/zero-copy-parsing",
        r'''How do I implement zero-copy parsing in Rust using lifetimes to borrow from the input data?''',
        r'''<think>
Zero-copy parsing means the parsed structure borrows directly from the input buffer instead of
allocating new strings. This is a key Rust performance pattern enabled by lifetimes. I should show
a parser that takes &'a str or &'a [u8] and returns structs containing &'a str slices.
Common in network protocols, file formats, and log parsing. This is expert-level Rust requiring
solid understanding of lifetimes and borrowing.
</think>

Zero-copy parsing borrows slices from the input instead of allocating:

```rust
/// Parsed HTTP-like header — borrows from input, no allocations
#[derive(Debug)]
struct Request<'a> {
    method: &'a str,
    path: &'a str,
    headers: Vec<(&'a str, &'a str)>,
}

fn parse_request(input: &str) -> Result<Request<'_>, &'static str> {
    let mut lines = input.split("\r\n");

    // Parse request line: "GET /path HTTP/1.1"
    let request_line = lines.next().ok_or("empty input")?;
    let mut parts = request_line.splitn(3, ' ');
    let method = parts.next().ok_or("missing method")?;
    let path = parts.next().ok_or("missing path")?;

    // Parse headers: "Key: Value"
    let mut headers = Vec::new();
    for line in lines {
        if line.is_empty() { break; }
        let (key, value) = line.split_once(": ")
            .ok_or("malformed header")?;
        headers.push((key, value));
    }

    Ok(Request { method, path, headers })
}

/// Zero-copy CSV row parser
#[derive(Debug)]
struct CsvRow<'a> {
    fields: Vec<&'a str>,
}

fn parse_csv_rows(input: &str) -> Vec<CsvRow<'_>> {
    input.lines()
        .map(|line| CsvRow {
            fields: line.split(',').map(str::trim).collect(),
        })
        .collect()
}

/// Zero-copy binary parsing from a byte slice
#[derive(Debug)]
struct Packet<'a> {
    version: u8,
    length: u16,
    payload: &'a [u8],
}

fn parse_packet(data: &[u8]) -> Result<Packet<'_>, &'static str> {
    if data.len() < 3 {
        return Err("too short");
    }
    let version = data[0];
    let length = u16::from_be_bytes([data[1], data[2]]) as usize;
    if data.len() < 3 + length {
        return Err("truncated payload");
    }
    Ok(Packet {
        version,
        length: length as u16,
        payload: &data[3..3 + length], // borrows directly from input
    })
}

fn main() {
    // Text parsing — Request borrows from `raw`
    let raw = "GET /api/users HTTP/1.1\r\nHost: example.com\r\nAuth: Bearer tok\r\n\r\n";
    let req = parse_request(raw).unwrap();
    println!("{} {} ({} headers)", req.method, req.path, req.headers.len());

    // CSV — all fields are &str slices into `csv`
    let csv = "name, age, city\nAlice, 30, NYC\nBob, 25, LA";
    let rows = parse_csv_rows(csv);
    println!("{:?}", rows[1].fields); // ["Alice", "30", "NYC"]

    // Binary — payload is &[u8] slice into `bytes`
    let bytes = [1u8, 0, 3, b'h', b'i', b'!'];
    let pkt = parse_packet(&bytes).unwrap();
    println!("v{} payload: {:?}", pkt.version, pkt.payload);
}
```

Why zero-copy matters:
- **No allocations** — parsed structs borrow from the input buffer
- **Cache-friendly** — data stays in the original memory location
- **Lifetime safety** — Rust guarantees the input outlives the parsed result
- **Pattern**: `fn parse<'a>(input: &'a [u8]) -> Result<Parsed<'a>, Error>` — the `'a` flows through'''
    ),
    (
        "rust/simd-optimization",
        r'''Show me how to use SIMD intrinsics in Rust for a performance-critical operation like counting bytes in a buffer.''',
        r'''<think>
SIMD in Rust can be done through std::arch intrinsics or the portable std::simd (nightly).
For stable Rust, std::arch with target_feature is the way. I'll show counting a specific byte
in a buffer using x86_64 SSE2/AVX2 intrinsics. Key: use #[target_feature(enable = "...")] and
check availability at runtime with is_x86_feature_detected!. This is expert-level optimization.
I should show a safe wrapper around the unsafe SIMD code.
</think>

```rust
#[cfg(target_arch = "x86_64")]
use std::arch::x86_64::*;

/// Count occurrences of `needle` in `haystack` using AVX2 (32 bytes at a time)
#[cfg(target_arch = "x86_64")]
#[target_feature(enable = "avx2")]
unsafe fn count_byte_avx2(haystack: &[u8], needle: u8) -> usize {
    let len = haystack.len();
    let mut count = 0usize;
    let needle_vec = _mm256_set1_epi8(needle as i8);
    let mut i = 0;

    // Process 32 bytes at a time
    while i + 32 <= len {
        let chunk = _mm256_loadu_si256(haystack.as_ptr().add(i) as *const __m256i);
        let cmp = _mm256_cmpeq_epi8(chunk, needle_vec);
        let mask = _mm256_movemask_epi8(cmp) as u32;
        count += mask.count_ones() as usize;
        i += 32;
    }

    // Handle remaining bytes
    for &b in &haystack[i..] {
        if b == needle {
            count += 1;
        }
    }
    count
}

/// Scalar fallback
fn count_byte_scalar(haystack: &[u8], needle: u8) -> usize {
    haystack.iter().filter(|&&b| b == needle).count()
}

/// Safe public API with runtime feature detection
pub fn count_byte(haystack: &[u8], needle: u8) -> usize {
    #[cfg(target_arch = "x86_64")]
    {
        if is_x86_feature_detected!("avx2") {
            return unsafe { count_byte_avx2(haystack, needle) };
        }
    }
    count_byte_scalar(haystack, needle)
}

fn main() {
    let data = b"Hello, World! Hello, Rust! Hello, SIMD!";
    let count = count_byte(data, b'l');
    println!("Found 'l' {} times", count); // 6

    // Benchmark with a larger buffer
    let big = vec![b'x'; 10_000_000];
    let start = std::time::Instant::now();
    let c = count_byte(&big, b'x');
    println!("{c} matches in {:?}", start.elapsed());
}
```

Key points:
- `#[target_feature(enable = "avx2")]` compiles the function with AVX2 instructions
- The function must be `unsafe` because calling it on a CPU without AVX2 is UB
- `is_x86_feature_detected!` does runtime CPUID checking (cached after first call)
- Always provide a scalar fallback for portability
- AVX2 processes 32 bytes per iteration vs 1 byte scalar — up to 20-30x speedup on large buffers
- For portable SIMD without intrinsics, consider the `wide` crate or nightly `std::simd`'''
    ),
    (
        "rust/type-state-pattern",
        r'''Explain and demonstrate the type state pattern in Rust. How do I use the type system to enforce valid state transitions at compile time?''',
        r'''<think>
The type state pattern uses zero-sized types as generic parameters to encode state in the type
system. State transitions become method signatures that consume Self and return a new type.
Invalid transitions simply don't compile. This is an advanced Rust pattern leveraging the type
system for correctness. Common example: a builder or connection that must go through specific
states (e.g., Disconnected -> Connected -> Authenticated).
</think>

The type state pattern encodes object state in the type system so invalid transitions are compile errors:

```rust
use std::marker::PhantomData;

// States are zero-sized types (no runtime cost)
struct Draft;
struct UnderReview;
struct Approved;
struct Published;

struct Article<State> {
    title: String,
    body: String,
    _state: PhantomData<State>,
}

// Methods available only in Draft state
impl Article<Draft> {
    fn new(title: &str) -> Self {
        Article {
            title: title.into(),
            body: String::new(),
            _state: PhantomData,
        }
    }

    fn set_body(mut self, body: &str) -> Self {
        self.body = body.into();
        self
    }

    // Consumes Draft, returns UnderReview — can't use Draft article after this
    fn submit_for_review(self) -> Article<UnderReview> {
        println!("'{}' submitted for review", self.title);
        Article {
            title: self.title,
            body: self.body,
            _state: PhantomData,
        }
    }
}

// Methods available only in UnderReview state
impl Article<UnderReview> {
    fn approve(self) -> Article<Approved> {
        println!("'{}' approved", self.title);
        Article {
            title: self.title,
            body: self.body,
            _state: PhantomData,
        }
    }

    fn reject(self) -> Article<Draft> {
        println!("'{}' sent back to draft", self.title);
        Article {
            title: self.title,
            body: self.body,
            _state: PhantomData,
        }
    }
}

impl Article<Approved> {
    fn publish(self) -> Article<Published> {
        println!("'{}' is now live!", self.title);
        Article {
            title: self.title,
            body: self.body,
            _state: PhantomData,
        }
    }
}

// Read-only access available in ALL states via a generic impl
impl<S> Article<S> {
    fn title(&self) -> &str {
        &self.title
    }
}

fn main() {
    let article = Article::new("Type States in Rust")
        .set_body("Type states encode valid transitions...");

    // Valid workflow
    let in_review = article.submit_for_review();
    let approved = in_review.approve();
    let _published = approved.publish();

    // These would NOT compile:
    // Article::<Draft>::new("x").approve();       // Draft can't be approved
    // Article::<Draft>::new("x").publish();        // Draft can't be published
    // in_review.set_body("...");                   // Can't edit under review
}
```

Benefits:
- **Zero runtime cost** — `PhantomData` is zero-sized, states exist only in the type system
- **Compile-time enforcement** — calling `.publish()` on a `Draft` is a type error, not a runtime panic
- **Self-documenting** — the function signature `fn approve(self) -> Article<Approved>` is the documentation
- **Move semantics** — consuming `self` prevents using the old state after a transition'''
    ),
    (
        "rust/newtype-pattern",
        r'''How do I use the newtype pattern in Rust for type safety? I want to prevent mixing up IDs, emails, and other stringly-typed values.''',
        r'''<think>
The newtype pattern wraps a primitive type in a single-field tuple struct to create a distinct type.
This prevents accidentally passing a UserId where an OrderId is expected. I should show basic
newtypes, deriving traits, implementing Deref (selectively), and using From/Into for conversions.
This is intermediate Rust — a very common and recommended pattern.
</think>

```rust
use std::fmt;

// Distinct types that wrap the same underlying type
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
struct UserId(u64);

#[derive(Debug, Clone, PartialEq, Eq, Hash)]
struct OrderId(u64);

#[derive(Debug, Clone, PartialEq, Eq)]
struct Email(String);

// Validated construction
impl Email {
    fn new(value: &str) -> Result<Self, &'static str> {
        if value.contains('@') && value.contains('.') {
            Ok(Email(value.to_lowercase()))
        } else {
            Err("invalid email format")
        }
    }

    fn as_str(&self) -> &str {
        &self.0
    }
}

impl fmt::Display for Email {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}", self.0)
    }
}

// From/Into for ergonomic conversion
impl From<u64> for UserId {
    fn from(id: u64) -> Self {
        UserId(id)
    }
}

impl From<UserId> for u64 {
    fn from(id: UserId) -> Self {
        id.0
    }
}

// The type system prevents mixing up IDs
fn get_user_orders(user_id: UserId) -> Vec<OrderId> {
    println!("Fetching orders for user {:?}", user_id);
    vec![OrderId(1001), OrderId(1002)]
}

fn send_email(to: &Email, subject: &str) {
    println!("Sending '{}' to {}", subject, to);
}

// Newtype for units — prevents mixing meters and kilometers
#[derive(Debug, Clone, Copy, PartialEq, PartialOrd)]
struct Meters(f64);

#[derive(Debug, Clone, Copy, PartialEq, PartialOrd)]
struct Kilometers(f64);

impl Meters {
    fn to_km(self) -> Kilometers {
        Kilometers(self.0 / 1000.0)
    }
}

impl Kilometers {
    fn to_meters(self) -> Meters {
        Meters(self.0 * 1000.0)
    }
}

// Can't accidentally add Meters + Kilometers
impl std::ops::Add for Meters {
    type Output = Self;
    fn add(self, rhs: Self) -> Self {
        Meters(self.0 + rhs.0)
    }
}

fn main() {
    let user = UserId(42);
    let order = OrderId(100);

    // get_user_orders(order);  // COMPILE ERROR: expected UserId, got OrderId

    let orders = get_user_orders(user.clone());
    println!("{:?}", orders);

    let email = Email::new("Alice@Example.com").unwrap();
    send_email(&email, "Hello!");
    // send_email("raw@string.com", "Hi"); // COMPILE ERROR: expected &Email

    let d1 = Meters(500.0);
    let d2 = Meters(300.0);
    let total = d1 + d2;
    println!("{:?} = {:?}", total, total.to_km());
}
```

Guidelines:
- **Don't implement `Deref`** to the inner type unless you truly want transparent access — it defeats the purpose
- **Validate in the constructor** — `Email::new()` enforces invariants; the inner `String` is private
- **Derive selectively** — only derive `Copy` if the inner type is `Copy` and copying makes semantic sense
- **Use `From`/`Into`** for explicit conversions instead of making the inner field public'''
    ),
    (
        "rust/builder-pattern",
        r'''Show me how to implement the builder pattern in Rust for constructing complex objects with many optional fields.''',
        r'''<think>
The builder pattern in Rust is used when structs have many fields, especially optional ones. Two
main approaches: consuming builder (takes self) and borrowing builder (takes &mut self). I'll show
the consuming builder with method chaining, required vs optional fields, and validation in build().
The bon crate or derive_builder can auto-generate this, but showing manual implementation is
more educational. This is intermediate Rust.
</think>

```rust
#[derive(Debug)]
struct HttpRequest {
    method: String,
    url: String,
    headers: Vec<(String, String)>,
    body: Option<Vec<u8>>,
    timeout_ms: u64,
    follow_redirects: bool,
}

#[derive(Default)]
struct HttpRequestBuilder {
    method: Option<String>,
    url: Option<String>,
    headers: Vec<(String, String)>,
    body: Option<Vec<u8>>,
    timeout_ms: u64,
    follow_redirects: bool,
}

#[derive(Debug)]
struct BuildError(String);

impl HttpRequestBuilder {
    fn new() -> Self {
        Self {
            timeout_ms: 30_000,
            follow_redirects: true,
            ..Default::default()
        }
    }

    // Required fields
    fn method(mut self, method: &str) -> Self {
        self.method = Some(method.to_uppercase());
        self
    }

    fn url(mut self, url: &str) -> Self {
        self.url = Some(url.into());
        self
    }

    // Optional fields
    fn header(mut self, key: &str, value: &str) -> Self {
        self.headers.push((key.into(), value.into()));
        self
    }

    fn body(mut self, body: impl Into<Vec<u8>>) -> Self {
        self.body = Some(body.into());
        self
    }

    fn timeout_ms(mut self, ms: u64) -> Self {
        self.timeout_ms = ms;
        self
    }

    fn no_follow_redirects(mut self) -> Self {
        self.follow_redirects = false;
        self
    }

    // Validate and build
    fn build(self) -> Result<HttpRequest, BuildError> {
        let method = self.method
            .ok_or_else(|| BuildError("method is required".into()))?;
        let url = self.url
            .ok_or_else(|| BuildError("url is required".into()))?;

        if method == "GET" && self.body.is_some() {
            return Err(BuildError("GET requests cannot have a body".into()));
        }

        Ok(HttpRequest {
            method,
            url,
            headers: self.headers,
            body: self.body,
            timeout_ms: self.timeout_ms,
            follow_redirects: self.follow_redirects,
        })
    }
}

// Convenience constructor on the target type
impl HttpRequest {
    fn builder() -> HttpRequestBuilder {
        HttpRequestBuilder::new()
    }
}

fn main() {
    let req = HttpRequest::builder()
        .method("POST")
        .url("https://api.example.com/data")
        .header("Content-Type", "application/json")
        .header("Authorization", "Bearer token123")
        .body(r#"{"key": "value"}"#.as_bytes().to_vec())
        .timeout_ms(5_000)
        .build()
        .unwrap();

    println!("{req:#?}");

    // This fails validation:
    let err = HttpRequest::builder()
        .method("GET")
        .url("https://example.com")
        .body(b"oops".to_vec())
        .build();
    println!("Error: {:?}", err.unwrap_err());
}
```

Design choices:
- **Consuming `self`** (not `&mut self`) enables method chaining and prevents reuse of a partially-built builder
- **`build()` returns `Result`** for validation — better than panicking
- **Defaults in `new()`** provide sensible values (30s timeout, follow redirects)
- **`impl Into<Vec<u8>>`** for `body()` accepts both `Vec<u8>` and `&[u8]` ergonomically
- For auto-generation, consider the `derive_builder` or `bon` crates'''
    ),
    (
        "rust/trait-dependency-injection",
        r'''How do I use traits for dependency injection in Rust to make code testable?''',
        r'''<think>
Dependency injection via traits is a core pattern for testable Rust code. Define behavior as traits,
accept trait objects or generics in your business logic, then swap in mock implementations for
testing. I should show both static dispatch (generics) and dynamic dispatch (dyn Trait), plus
async traits. This is intermediate-to-advanced Rust.
</think>

```rust
use std::collections::HashMap;

// Define behavior contracts as traits
trait UserRepository {
    fn find_by_id(&self, id: u64) -> Option<User>;
    fn save(&mut self, user: &User) -> Result<(), String>;
}

trait EmailService {
    fn send(&self, to: &str, subject: &str, body: &str) -> Result<(), String>;
}

#[derive(Debug, Clone)]
struct User {
    id: u64,
    name: String,
    email: String,
}

// Business logic depends on traits, not concrete types
struct UserService<R: UserRepository, E: EmailService> {
    repo: R,
    email: E,
}

impl<R: UserRepository, E: EmailService> UserService<R, E> {
    fn new(repo: R, email: E) -> Self {
        Self { repo, email }
    }

    fn welcome_user(&mut self, id: u64) -> Result<(), String> {
        let user = self.repo.find_by_id(id)
            .ok_or("user not found")?;
        self.email.send(
            &user.email,
            "Welcome!",
            &format!("Hello, {}!", user.name),
        )?;
        Ok(())
    }
}

// === Production implementations ===

struct PgUserRepo { /* pool: PgPool */ }

impl UserRepository for PgUserRepo {
    fn find_by_id(&self, id: u64) -> Option<User> {
        // Real database query here
        Some(User { id, name: "Real User".into(), email: "real@db.com".into() })
    }
    fn save(&mut self, _user: &User) -> Result<(), String> { Ok(()) }
}

struct SmtpEmailService { /* config */ }

impl EmailService for SmtpEmailService {
    fn send(&self, to: &str, subject: &str, _body: &str) -> Result<(), String> {
        println!("SMTP: sending '{subject}' to {to}");
        Ok(())
    }
}

// === Test mocks ===
#[cfg(test)]
mod tests {
    use super::*;

    struct MockRepo {
        users: HashMap<u64, User>,
    }

    impl MockRepo {
        fn with_user(id: u64, name: &str, email: &str) -> Self {
            let mut users = HashMap::new();
            users.insert(id, User { id, name: name.into(), email: email.into() });
            Self { users }
        }
    }

    impl UserRepository for MockRepo {
        fn find_by_id(&self, id: u64) -> Option<User> {
            self.users.get(&id).cloned()
        }
        fn save(&mut self, user: &User) -> Result<(), String> {
            self.users.insert(user.id, user.clone());
            Ok(())
        }
    }

    struct MockEmail {
        sent: std::cell::RefCell<Vec<(String, String)>>,
    }

    impl MockEmail {
        fn new() -> Self {
            Self { sent: std::cell::RefCell::new(vec![]) }
        }
        fn sent_count(&self) -> usize {
            self.sent.borrow().len()
        }
    }

    impl EmailService for MockEmail {
        fn send(&self, to: &str, subject: &str, _body: &str) -> Result<(), String> {
            self.sent.borrow_mut().push((to.into(), subject.into()));
            Ok(())
        }
    }

    #[test]
    fn test_welcome_sends_email() {
        let repo = MockRepo::with_user(1, "Alice", "alice@test.com");
        let email = MockEmail::new();
        let mut svc = UserService::new(repo, email);
        svc.welcome_user(1).unwrap();
        assert_eq!(svc.email.sent_count(), 1);
    }

    #[test]
    fn test_welcome_missing_user() {
        let repo = MockRepo { users: HashMap::new() };
        let email = MockEmail::new();
        let mut svc = UserService::new(repo, email);
        assert!(svc.welcome_user(99).is_err());
        assert_eq!(svc.email.sent_count(), 0);
    }
}

fn main() {
    let repo = PgUserRepo {};
    let email = SmtpEmailService {};
    let mut svc = UserService::new(repo, email);
    svc.welcome_user(1).unwrap();
}
```

Two dispatch approaches:
- **Generics** (`<R: UserRepository>`) — zero-cost, monomorphized, used above
- **Trait objects** (`Box<dyn UserRepository>`) — dynamic dispatch, useful when you need heterogeneous collections or runtime swapping
- For **async traits**, use `#[trait_variant::make(Send)]` or `async fn` in traits (stable since Rust 1.75)'''
    ),
    (
        "rust/const-generics-validation",
        r'''How do I use const generics in Rust for compile-time validation, like ensuring array sizes or bounded integers?''',
        r'''<think>
Const generics allow types parameterized by constant values (like integers). This enables
compile-time enforcement of sizes and bounds. I'll show fixed-size arrays, bounded values, and
type-level dimensional analysis. Const generics are stable for simple types (integers, bool, char).
This is advanced Rust — combining const generics with where clauses for constraints.
</think>

```rust
// Fixed-size matrix with dimensions checked at compile time
#[derive(Debug)]
struct Matrix<const ROWS: usize, const COLS: usize> {
    data: [[f64; COLS]; ROWS],
}

impl<const ROWS: usize, const COLS: usize> Matrix<ROWS, COLS> {
    fn zero() -> Self {
        Self { data: [[0.0; COLS]; ROWS] }
    }

    fn get(&self, row: usize, col: usize) -> f64 {
        self.data[row][col]
    }

    fn set(&mut self, row: usize, col: usize, val: f64) {
        self.data[row][col] = val;
    }

    // Transpose: ROWS x COLS -> COLS x ROWS
    fn transpose(&self) -> Matrix<COLS, ROWS> {
        let mut result = Matrix::<COLS, ROWS>::zero();
        for r in 0..ROWS {
            for c in 0..COLS {
                result.data[c][r] = self.data[r][c];
            }
        }
        result
    }
}

// Multiplication: (M x N) * (N x P) -> (M x P)
// The shared dimension N is enforced by the type system
impl<const M: usize, const N: usize> Matrix<M, N> {
    fn multiply<const P: usize>(&self, other: &Matrix<N, P>) -> Matrix<M, P> {
        let mut result = Matrix::<M, P>::zero();
        for i in 0..M {
            for j in 0..P {
                let mut sum = 0.0;
                for k in 0..N {
                    sum += self.data[i][k] * other.data[k][j];
                }
                result.data[i][j] = sum;
            }
        }
        result
    }
}

// Fixed-capacity stack-allocated buffer (no heap allocation)
struct FixedBuf<const CAP: usize> {
    data: [u8; CAP],
    len: usize,
}

impl<const CAP: usize> FixedBuf<CAP> {
    fn new() -> Self {
        Self { data: [0; CAP], len: 0 }
    }

    fn push(&mut self, byte: u8) -> Result<(), &'static str> {
        if self.len >= CAP {
            return Err("buffer full");
        }
        self.data[self.len] = byte;
        self.len += 1;
        Ok(())
    }

    fn as_slice(&self) -> &[u8] {
        &self.data[..self.len]
    }
}

// Bounded integer: value must be in range [MIN, MAX]
#[derive(Debug, Clone, Copy)]
struct Bounded<const MIN: i32, const MAX: i32>(i32);

impl<const MIN: i32, const MAX: i32> Bounded<MIN, MAX> {
    fn new(val: i32) -> Option<Self> {
        if val >= MIN && val <= MAX {
            Some(Bounded(val))
        } else {
            None
        }
    }

    fn value(self) -> i32 {
        self.0
    }
}

// Type aliases for specific bounds
type Percentage = Bounded<0, 100>;
type DayOfMonth = Bounded<1, 31>;

fn main() {
    // Matrix dimensions checked at compile time
    let a = Matrix::<2, 3>::zero();
    let b = Matrix::<3, 4>::zero();
    let c: Matrix<2, 4> = a.multiply(&b); // 2x3 * 3x4 = 2x4

    // This would NOT compile — dimension mismatch:
    // let bad = a.multiply(&Matrix::<5, 2>::zero()); // error: expected Matrix<3, _>

    let t = a.transpose(); // Matrix<3, 2>

    // Bounded integers
    let pct = Percentage::new(85).unwrap();
    let bad = Percentage::new(150); // None
    println!("{}% (invalid: {:?})", pct.value(), bad);

    // Fixed buffer
    let mut buf = FixedBuf::<8>::new();
    buf.push(b'H').unwrap();
    buf.push(b'i').unwrap();
    println!("{:?}", std::str::from_utf8(buf.as_slice()));
}
```

Const generics enforce:
- **Matrix dimension compatibility** — `multiply` requires matching inner dimensions at compile time
- **Buffer capacity** — stack-allocated, no heap, size known at compile time
- **Value bounds** — `Bounded<0, 100>` creates a type that only holds values 0-100'''
    ),
    (
        "rust/async-error-propagation",
        r'''How do I handle error propagation across async boundaries in Rust? I'm struggling with Send bounds and error types in async code.''',
        r'''<think>
Error handling in async Rust is tricky because errors need to be Send + 'static for tokio::spawn,
and the ? operator needs compatible error types across await points. Common issues: non-Send errors,
error type mismatches between async functions, and JoinError from spawned tasks. I should show
using thiserror for typed errors, anyhow for application code, and handling JoinError.
This is advanced async Rust.
</think>

```rust
use std::num::ParseIntError;
use tokio::task::JoinError;

// Define a domain error with thiserror (Send + Sync automatically)
#[derive(Debug, thiserror::Error)]
enum AppError {
    #[error("database error: {0}")]
    Database(String),

    #[error("parse error: {0}")]
    Parse(#[from] ParseIntError),

    #[error("http error: {0}")]
    Http(#[from] reqwest::Error),

    #[error("task failed: {0}")]
    TaskJoin(#[from] JoinError),

    #[error("not found: {entity} with id {id}")]
    NotFound { entity: &'static str, id: u64 },

    #[error("{0}")]
    Other(String),
}

// Result alias for convenience
type Result<T> = std::result::Result<T, AppError>;

// Async functions use ? naturally with the From impls
async fn fetch_user_age(user_id: u64) -> Result<u32> {
    // Simulated DB call
    let raw: &str = match user_id {
        1 => "25",
        2 => "not_a_number",
        _ => return Err(AppError::NotFound { entity: "user", id: user_id }),
    };

    let age: u32 = raw.parse()?; // ParseIntError -> AppError::Parse via From
    Ok(age)
}

// Spawning tasks: errors must be Send + 'static
async fn process_users(ids: Vec<u64>) -> Result<Vec<u32>> {
    let mut handles = vec![];

    for id in ids {
        // tokio::spawn requires the future to be Send + 'static
        let handle = tokio::spawn(async move {
            fetch_user_age(id).await
        });
        handles.push(handle);
    }

    let mut results = vec![];
    for handle in handles {
        // JoinError (task panic/cancel) -> AppError::TaskJoin via From
        // Then inner Result is our AppError
        let age = handle.await??;
        results.push(age);
    }
    Ok(results)
}

// Collecting partial results: don't fail everything on one error
async fn process_users_lenient(ids: Vec<u64>) -> Vec<Result<u32>> {
    let mut handles = vec![];

    for id in ids {
        handles.push(tokio::spawn(async move {
            fetch_user_age(id).await
        }));
    }

    let mut results = vec![];
    for handle in handles {
        let result = match handle.await {
            Ok(inner) => inner,
            Err(e) => Err(AppError::TaskJoin(e)),
        };
        results.push(result);
    }
    results
}

// Using anyhow for quick prototyping (alternative to custom error types)
async fn quick_prototype() -> anyhow::Result<()> {
    let data = tokio::fs::read_to_string("config.toml").await
        .map_err(|e| anyhow::anyhow!("config read failed: {e}"))?;

    let val: u64 = data.trim().parse()
        .map_err(|_| anyhow::anyhow!("bad config value"))?;

    println!("Config value: {val}");
    Ok(())
}

#[tokio::main]
async fn main() {
    // Strict mode: first error stops everything
    match process_users(vec![1, 3]).await {
        Ok(ages) => println!("Ages: {ages:?}"),
        Err(e) => eprintln!("Failed: {e}"),
    }

    // Lenient mode: collect all results
    let results = process_users_lenient(vec![1, 2, 3]).await;
    for (i, r) in results.iter().enumerate() {
        match r {
            Ok(age) => println!("User {}: age {age}", i + 1),
            Err(e) => println!("User {}: error: {e}", i + 1),
        }
    }
}
```

Key rules for async error handling:
- **`tokio::spawn` requires `Send + 'static`** — your error types must be `Send` (thiserror types are by default)
- **`handle.await??`** — outer `?` unwraps `JoinError`, inner `?` unwraps your app error
- **Use `thiserror`** for library code (typed errors with `From` impls)
- **Use `anyhow`** for application/script code (any error, quick context)
- **Non-Send types** (like `Rc`, `MutexGuard`) cannot be held across `.await` — restructure to drop them before awaiting'''
    ),
    (
        "rust/workspace-multi-crate",
        r'''How do I structure a Rust workspace with multiple crates? Show me the project layout and Cargo configuration.''',
        r'''<think>
Rust workspaces let you organize a project into multiple crates that share a single Cargo.lock and
target directory. Common structure: a binary crate, a core library, shared types, and utility
crates. I should show the Cargo.toml workspace configuration, inter-crate dependencies, and
shared dependency versions. This is intermediate Rust project management.
</think>

```
my-project/
├── Cargo.toml              # Workspace root
├── Cargo.lock              # Shared across all crates
├── crates/
│   ├── app/                # Binary crate (the final executable)
│   │   ├── Cargo.toml
│   │   └── src/
│   │       └── main.rs
│   ├── core/               # Core business logic library
│   │   ├── Cargo.toml
│   │   └── src/
│   │       └── lib.rs
│   ├── api/                # HTTP API library
│   │   ├── Cargo.toml
│   │   └── src/
│   │       └── lib.rs
│   └── shared/             # Shared types and utilities
│       ├── Cargo.toml
│       └── src/
│           └── lib.rs
└── target/                 # Shared build output
```

**Root `Cargo.toml`:**
```toml
[workspace]
resolver = "2"
members = [
    "crates/app",
    "crates/core",
    "crates/api",
    "crates/shared",
]

# Shared dependency versions (DRY)
[workspace.dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
tokio = { version = "1", features = ["full"] }
anyhow = "1"
tracing = "0.1"
```

**`crates/shared/Cargo.toml`:**
```toml
[package]
name = "my-shared"
version = "0.1.0"
edition = "2021"

[dependencies]
serde.workspace = true  # Uses version from workspace root
```

**`crates/shared/src/lib.rs`:**
```rust
use serde::{Serialize, Deserialize};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct UserId(pub u64);

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct User {
    pub id: UserId,
    pub name: String,
    pub email: String,
}
```

**`crates/core/Cargo.toml`:**
```toml
[package]
name = "my-core"
version = "0.1.0"
edition = "2021"

[dependencies]
my-shared = { path = "../shared" }
anyhow.workspace = true
```

**`crates/core/src/lib.rs`:**
```rust
use my_shared::{User, UserId};

pub trait UserRepository: Send + Sync {
    fn find(&self, id: &UserId) -> anyhow::Result<Option<User>>;
    fn save(&self, user: &User) -> anyhow::Result<()>;
}

pub struct UserService<R: UserRepository> {
    repo: R,
}

impl<R: UserRepository> UserService<R> {
    pub fn new(repo: R) -> Self {
        Self { repo }
    }

    pub fn get_user(&self, id: u64) -> anyhow::Result<User> {
        self.repo.find(&UserId(id))?
            .ok_or_else(|| anyhow::anyhow!("user {id} not found"))
    }
}
```

**`crates/app/Cargo.toml`:**
```toml
[package]
name = "my-app"
version = "0.1.0"
edition = "2021"

[dependencies]
my-shared = { path = "../shared" }
my-core = { path = "../core" }
my-api = { path = "../api" }
tokio.workspace = true
tracing.workspace = true
```

**Common commands:**
```bash
cargo build                        # build everything
cargo build -p my-core             # build one crate
cargo test --workspace             # test all crates
cargo test -p my-core              # test one crate
cargo run -p my-app                # run the binary
cargo clippy --workspace           # lint everything
```

Benefits of workspaces:
- **Single `Cargo.lock`** — all crates use the same dependency versions
- **Shared `target/`** — compiled dependencies are reused across crates
- **`workspace.dependencies`** — define versions once, use `dep.workspace = true` everywhere
- **Independent crates** — each has its own `Cargo.toml`, can be published separately'''
    ),
]
