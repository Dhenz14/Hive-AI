"""P2 Batch: Rust ecosystem — Axum, Tauri, error handling patterns, async patterns."""

PAIRS = [
    (
        "Axum web framework for production Rust APIs",
        "Build a production-ready REST API using Axum in Rust. Show routing, middleware, state management, error handling, and database integration with SQLx. Explain the design decisions and tradeoffs.",
        """## Axum: Production Rust Web APIs

### Why Axum Over Actix-Web or Warp

Axum is built by the Tokio team, which means it integrates perfectly with the Tokio ecosystem (tower middleware, hyper HTTP, tonic gRPC). The key design choice: Axum uses **tower::Service** as its middleware abstraction, so any tower middleware works with Axum out of the box.

Actix-web uses its own actor system (powerful but different from the ecosystem). Warp uses filter combinators (type-safe but complex error messages). Axum sits in the middle: ergonomic like Express.js, but type-safe like Rust.

### Complete Production API

```rust
// src/main.rs
use axum::{
    extract::{Path, Query, State},
    http::StatusCode,
    middleware,
    response::IntoResponse,
    routing::{get, post, delete},
    Json, Router,
};
use serde::{Deserialize, Serialize};
use sqlx::sqlite::SqlitePoolOptions;
use sqlx::SqlitePool;
use std::sync::Arc;
use tower_http::cors::CorsLayer;
use tower_http::trace::TraceLayer;

// Application state — shared across all handlers via Arc
#[derive(Clone)]
struct AppState {
    db: SqlitePool,
}

// Domain types with serde for JSON (de)serialization
#[derive(Serialize, sqlx::FromRow)]
struct Task {
    id: i64,
    title: String,
    done: bool,
    created_at: String,
}

#[derive(Deserialize)]
struct CreateTask {
    title: String,
}

#[derive(Deserialize)]
struct ListParams {
    done: Option<bool>,
    limit: Option<i64>,
}

// Custom error type — converts to HTTP responses automatically.
// This is where Rust shines: exhaustive error handling without exceptions.
#[derive(Debug)]
enum AppError {
    NotFound(String),
    Database(sqlx::Error),
    Validation(String),
}

impl IntoResponse for AppError {
    fn into_response(self) -> axum::response::Response {
        let (status, message) = match self {
            AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg),
            AppError::Database(e) => {
                tracing::error!("Database error: {:?}", e);
                (StatusCode::INTERNAL_SERVER_ERROR, "Internal server error".into())
            }
            AppError::Validation(msg) => (StatusCode::BAD_REQUEST, msg),
        };
        (status, Json(serde_json::json!({"error": message}))).into_response()
    }
}

// Automatic conversion from sqlx errors
impl From<sqlx::Error> for AppError {
    fn from(e: sqlx::Error) -> Self {
        AppError::Database(e)
    }
}

// Handlers — each is a plain async function. Axum extracts parameters
// from the request automatically based on the function signature.
// This is the "extractor" pattern: State, Path, Query, Json are extractors.

async fn list_tasks(
    State(state): State<AppState>,
    Query(params): Query<ListParams>,
) -> Result<Json<Vec<Task>>, AppError> {
    let limit = params.limit.unwrap_or(50).min(100);

    let tasks = match params.done {
        Some(done) => {
            sqlx::query_as::<_, Task>("SELECT * FROM tasks WHERE done = ? ORDER BY created_at DESC LIMIT ?")
                .bind(done)
                .bind(limit)
                .fetch_all(&state.db)
                .await?
        }
        None => {
            sqlx::query_as::<_, Task>("SELECT * FROM tasks ORDER BY created_at DESC LIMIT ?")
                .bind(limit)
                .fetch_all(&state.db)
                .await?
        }
    };

    Ok(Json(tasks))
}

async fn create_task(
    State(state): State<AppState>,
    Json(input): Json<CreateTask>,
) -> Result<(StatusCode, Json<Task>), AppError> {
    let title = input.title.trim().to_string();
    if title.is_empty() {
        return Err(AppError::Validation("Title cannot be empty".into()));
    }
    if title.len() > 500 {
        return Err(AppError::Validation("Title too long (max 500 chars)".into()));
    }

    let task = sqlx::query_as::<_, Task>(
        "INSERT INTO tasks (title, done) VALUES (?, false) RETURNING *"
    )
    .bind(&title)
    .fetch_one(&state.db)
    .await?;

    Ok((StatusCode::CREATED, Json(task)))
}

async fn get_task(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<Task>, AppError> {
    sqlx::query_as::<_, Task>("SELECT * FROM tasks WHERE id = ?")
        .bind(id)
        .fetch_optional(&state.db)
        .await?
        .map(Json)
        .ok_or_else(|| AppError::NotFound(format!("Task {id} not found")))
}

async fn toggle_task(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<Json<Task>, AppError> {
    let task = sqlx::query_as::<_, Task>(
        "UPDATE tasks SET done = NOT done WHERE id = ? RETURNING *"
    )
    .bind(id)
    .fetch_optional(&state.db)
    .await?
    .ok_or_else(|| AppError::NotFound(format!("Task {id} not found")))?;

    Ok(Json(task))
}

async fn delete_task(
    State(state): State<AppState>,
    Path(id): Path<i64>,
) -> Result<StatusCode, AppError> {
    let result = sqlx::query("DELETE FROM tasks WHERE id = ?")
        .bind(id)
        .execute(&state.db)
        .await?;

    if result.rows_affected() == 0 {
        Err(AppError::NotFound(format!("Task {id} not found")))
    } else {
        Ok(StatusCode::NO_CONTENT)
    }
}

async fn health_check() -> &'static str {
    "ok"
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Initialize tracing (structured logging)
    tracing_subscriber::init();

    // Database connection pool
    let db = SqlitePoolOptions::new()
        .max_connections(5)
        .connect("sqlite:tasks.db?mode=rwc")
        .await?;

    // Run migrations
    sqlx::query(
        "CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            done BOOLEAN NOT NULL DEFAULT false,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )"
    ).execute(&db).await?;

    let state = AppState { db };

    // Build the router — nested routes, middleware, shared state
    let app = Router::new()
        .route("/health", get(health_check))
        .route("/tasks", get(list_tasks).post(create_task))
        .route("/tasks/{id}", get(get_task).delete(delete_task))
        .route("/tasks/{id}/toggle", post(toggle_task))
        .layer(CorsLayer::permissive())     // CORS middleware
        .layer(TraceLayer::new_for_http())  // Request logging
        .with_state(state);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000").await?;
    tracing::info!("Listening on http://0.0.0.0:3000");
    axum::serve(listener, app).await?;

    Ok(())
}
```

### Key Design Decisions Explained

**Why `State<AppState>` instead of global state?** Axum passes state through the type system. Every handler declares what it needs via extractors. This means: no global mutable state, no runtime errors from missing state, and the compiler verifies that state is available at route registration time.

**Why `Result<T, AppError>` instead of panicking?** Rust has no exceptions. Every error must be handled explicitly. The `?` operator propagates errors automatically, and the `From<sqlx::Error>` impl converts database errors into HTTP errors. This means: no unhandled exceptions crashing your server, no try/catch boilerplate.

**Why tower middleware?** Tower's `Service` trait is composable. You can stack CORS + logging + auth + rate limiting, and each middleware is an independent, testable unit. The same middleware works with Axum, Tonic (gRPC), and raw Hyper.""",
    ),

    (
        "Tauri desktop applications with Rust backend",
        "Explain how to build cross-platform desktop applications with Tauri — how its Rust backend works with a web frontend, how it compares to Electron, and show a complete example with IPC between Rust and JavaScript.",
        """## Tauri: Native Desktop Apps Without the Electron Bloat

### Why Tauri Over Electron

Electron bundles a full Chromium browser (~150MB) and Node.js runtime with every app. Slack, VS Code, Discord — each is essentially a separate Chrome installation. Tauri takes a different approach: it uses the OS's built-in webview (WebView2 on Windows, WebKit on macOS/Linux) and a Rust backend instead of Node.js.

| Metric | Electron | Tauri |
|--------|----------|-------|
| **Binary size** | 150-300MB | 3-10MB |
| **RAM usage** | 200-500MB | 30-80MB |
| **Startup time** | 2-5 seconds | <1 second |
| **Backend language** | JavaScript (Node.js) | Rust |
| **Frontend** | HTML/CSS/JS | HTML/CSS/JS (same) |
| **Security** | Node.js has full system access | Capability-based permissions |

### Architecture

```
┌─────────────────────────────────────────┐
│              Tauri App                  │
│                                          │
│  ┌──────────────┐   IPC    ┌──────────┐ │
│  │  Web Frontend │ ◄═════► │ Rust Core │ │
│  │  (React/Vue/  │  JSON   │  (tauri)  │ │
│  │   Svelte/etc) │ commands│           │ │
│  │  runs in OS   │         │ file I/O  │ │
│  │  webview      │         │ DB access │ │
│  └──────────────┘         │ system    │ │
│                            │ crypto    │ │
│                            └──────────┘ │
└─────────────────────────────────────────┘
```

### Complete Example: Note-Taking App

```rust
// src-tauri/src/main.rs — Rust backend
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use serde::{Deserialize, Serialize};
use std::fs;
use std::path::PathBuf;
use tauri::Manager;

#[derive(Serialize, Deserialize, Clone)]
struct Note {
    id: String,
    title: String,
    content: String,
    created_at: String,
    updated_at: String,
}

// Tauri commands are Rust functions callable from JavaScript.
// The #[tauri::command] macro handles JSON serialization automatically.

#[tauri::command]
fn list_notes(app_handle: tauri::AppHandle) -> Result<Vec<Note>, String> {
    let notes_dir = get_notes_dir(&app_handle)?;
    let mut notes = Vec::new();

    if let Ok(entries) = fs::read_dir(&notes_dir) {
        for entry in entries.flatten() {
            if entry.path().extension().map_or(false, |e| e == "json") {
                let content = fs::read_to_string(entry.path())
                    .map_err(|e| format!("Failed to read note: {}", e))?;
                let note: Note = serde_json::from_str(&content)
                    .map_err(|e| format!("Failed to parse note: {}", e))?;
                notes.push(note);
            }
        }
    }

    notes.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));
    Ok(notes)
}

#[tauri::command]
fn save_note(app_handle: tauri::AppHandle, note: Note) -> Result<Note, String> {
    let notes_dir = get_notes_dir(&app_handle)?;
    let file_path = notes_dir.join(format!("{}.json", note.id));

    let mut note = note;
    note.updated_at = chrono::Utc::now().to_rfc3339();
    if note.created_at.is_empty() {
        note.created_at = note.updated_at.clone();
    }

    let json = serde_json::to_string_pretty(&note)
        .map_err(|e| format!("Serialization error: {}", e))?;
    fs::write(&file_path, json)
        .map_err(|e| format!("Failed to save: {}", e))?;

    Ok(note)
}

#[tauri::command]
fn delete_note(app_handle: tauri::AppHandle, id: String) -> Result<(), String> {
    let notes_dir = get_notes_dir(&app_handle)?;
    let file_path = notes_dir.join(format!("{}.json", id));

    if file_path.exists() {
        fs::remove_file(&file_path)
            .map_err(|e| format!("Failed to delete: {}", e))?;
    }
    Ok(())
}

#[tauri::command]
fn search_notes(app_handle: tauri::AppHandle, query: String) -> Result<Vec<Note>, String> {
    let all_notes = list_notes(app_handle)?;
    let query_lower = query.to_lowercase();

    Ok(all_notes
        .into_iter()
        .filter(|n| {
            n.title.to_lowercase().contains(&query_lower)
                || n.content.to_lowercase().contains(&query_lower)
        })
        .collect())
}

fn get_notes_dir(app_handle: &tauri::AppHandle) -> Result<PathBuf, String> {
    let dir = app_handle
        .path()
        .app_data_dir()
        .map_err(|e| format!("No app data dir: {}", e))?
        .join("notes");
    fs::create_dir_all(&dir).map_err(|e| format!("Failed to create dir: {}", e))?;
    Ok(dir)
}

fn main() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![
            list_notes,
            save_note,
            delete_note,
            search_notes,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
```

### Frontend: Calling Rust from JavaScript

```javascript
// src/App.jsx — React frontend (works with Vue, Svelte, etc. too)
import { invoke } from '@tauri-apps/api/core';
import { useState, useEffect } from 'react';

function App() {
    const [notes, setNotes] = useState([]);
    const [selected, setSelected] = useState(null);
    const [search, setSearch] = useState('');

    useEffect(() => {
        loadNotes();
    }, []);

    async function loadNotes() {
        // invoke() calls Rust functions via IPC
        // Arguments are serialized to JSON automatically
        const result = await invoke('list_notes');
        setNotes(result);
    }

    async function handleSave(note) {
        const saved = await invoke('save_note', { note });
        setSelected(saved);
        await loadNotes();
    }

    async function handleDelete(id) {
        await invoke('delete_note', { id });
        setSelected(null);
        await loadNotes();
    }

    async function handleSearch(query) {
        setSearch(query);
        if (query.trim()) {
            const results = await invoke('search_notes', { query });
            setNotes(results);
        } else {
            await loadNotes();
        }
    }

    return (
        <div className="app">
            <aside>
                <input
                    type="search"
                    placeholder="Search notes..."
                    value={search}
                    onChange={e => handleSearch(e.target.value)}
                />
                <button onClick={() => setSelected({
                    id: crypto.randomUUID(),
                    title: 'New Note',
                    content: '',
                    created_at: '',
                    updated_at: '',
                })}>New Note</button>
                <ul>
                    {notes.map(n => (
                        <li key={n.id} onClick={() => setSelected(n)}>
                            {n.title}
                        </li>
                    ))}
                </ul>
            </aside>
            {selected && (
                <main>
                    <input
                        value={selected.title}
                        onChange={e => setSelected({...selected, title: e.target.value})}
                    />
                    <textarea
                        value={selected.content}
                        onChange={e => setSelected({...selected, content: e.target.value})}
                    />
                    <div>
                        <button onClick={() => handleSave(selected)}>Save</button>
                        <button onClick={() => handleDelete(selected.id)}>Delete</button>
                    </div>
                </main>
            )}
        </div>
    );
}

export default App;
```

### When to Choose Tauri

Choose Tauri when: you need a desktop app, care about binary size and performance, and your team knows Rust (or wants to learn). Choose Electron when: your team is all JavaScript, you need extensive Node.js npm packages, or you need perfect cross-platform rendering consistency (Electron's Chromium is identical everywhere; OS webviews vary slightly).""",
    ),

    (
        "Rust async patterns with Tokio",
        "Explain advanced Rust async patterns using Tokio — select!, join!, channels, graceful shutdown, and backpressure. Show production-ready code for a concurrent web scraper with rate limiting.",
        """## Rust Async with Tokio: Beyond Basic async/await

### The Tokio Mental Model

Tokio is a runtime, not a framework. It provides: an executor (runs futures to completion), an I/O reactor (efficient async networking), and synchronization primitives (channels, mutexes, semaphores). Understanding which piece does what prevents common mistakes.

The key difference from JavaScript's event loop: Tokio is **multi-threaded by default**. Futures can run on any thread in the thread pool. This means: `Rc` won't work (use `Arc`), `RefCell` won't work (use `Mutex`), and you must think about `Send` bounds.

### Pattern 1: select! for Racing Futures

```rust
use tokio::time::{sleep, Duration, Instant};
use tokio::sync::mpsc;
use tokio::signal;

/// select! waits for the FIRST future to complete and cancels the rest.
/// This is how you implement timeouts, graceful shutdown, and priority handling.
async fn fetch_with_timeout(url: &str, timeout: Duration) -> Result<String, String> {
    tokio::select! {
        result = reqwest::get(url) => {
            match result {
                Ok(resp) => resp.text().await.map_err(|e| e.to_string()),
                Err(e) => Err(e.to_string()),
            }
        }
        _ = sleep(timeout) => {
            Err(format!("Timeout after {:?}", timeout))
        }
    }
}

/// Graceful shutdown: process messages until Ctrl+C
async fn worker_with_shutdown(mut rx: mpsc::Receiver<String>) {
    loop {
        tokio::select! {
            // biased; means: check shutdown FIRST on each iteration
            // Without biased, select! picks randomly, which could
            // process more messages even after shutdown is requested.
            biased;

            _ = signal::ctrl_c() => {
                println!("Shutting down gracefully...");
                // Drain remaining messages
                while let Ok(msg) = rx.try_recv() {
                    println!("Processing remaining: {}", msg);
                }
                break;
            }
            msg = rx.recv() => {
                match msg {
                    Some(m) => println!("Processing: {}", m),
                    None => break, // Channel closed
                }
            }
        }
    }
}
```

### Pattern 2: Concurrent Scraper with Rate Limiting

```rust
use tokio::sync::Semaphore;
use tokio::time::{sleep, Duration};
use std::sync::Arc;

/// Production web scraper with:
/// - Configurable concurrency limit (semaphore)
/// - Per-domain rate limiting (token bucket)
/// - Retry with exponential backoff
/// - Graceful error handling (no panics)

struct Scraper {
    client: reqwest::Client,
    concurrency: Arc<Semaphore>,
    rate_limiter: Arc<tokio::sync::Mutex<RateLimiter>>,
}

struct RateLimiter {
    tokens: f64,
    max_tokens: f64,
    refill_rate: f64,  // tokens per second
    last_refill: std::time::Instant,
}

impl RateLimiter {
    fn new(requests_per_second: f64) -> Self {
        Self {
            tokens: requests_per_second,
            max_tokens: requests_per_second * 2.0,  // Allow small bursts
            refill_rate: requests_per_second,
            last_refill: std::time::Instant::now(),
        }
    }

    async fn acquire(&mut self) {
        loop {
            let now = std::time::Instant::now();
            let elapsed = now.duration_since(self.last_refill).as_secs_f64();
            self.tokens = (self.tokens + elapsed * self.refill_rate).min(self.max_tokens);
            self.last_refill = now;

            if self.tokens >= 1.0 {
                self.tokens -= 1.0;
                return;
            }

            // Wait for token to become available
            let wait_time = (1.0 - self.tokens) / self.refill_rate;
            sleep(Duration::from_secs_f64(wait_time)).await;
        }
    }
}

impl Scraper {
    fn new(max_concurrent: usize, requests_per_second: f64) -> Self {
        Self {
            client: reqwest::Client::builder()
                .timeout(Duration::from_secs(30))
                .build()
                .unwrap(),
            concurrency: Arc::new(Semaphore::new(max_concurrent)),
            rate_limiter: Arc::new(tokio::sync::Mutex::new(
                RateLimiter::new(requests_per_second),
            )),
        }
    }

    async fn scrape_urls(&self, urls: Vec<String>) -> Vec<Result<String, String>> {
        // join_all runs all futures concurrently (bounded by semaphore)
        let futures: Vec<_> = urls
            .into_iter()
            .map(|url| self.scrape_one(url))
            .collect();

        futures::future::join_all(futures).await
    }

    async fn scrape_one(&self, url: String) -> Result<String, String> {
        // Acquire semaphore permit (blocks if at max concurrency)
        let _permit = self.concurrency.acquire().await.map_err(|e| e.to_string())?;

        // Rate limit
        self.rate_limiter.lock().await.acquire().await;

        // Retry with exponential backoff
        let mut delay = Duration::from_millis(100);
        for attempt in 0..3 {
            match self.client.get(&url).send().await {
                Ok(resp) if resp.status().is_success() => {
                    return resp.text().await.map_err(|e| e.to_string());
                }
                Ok(resp) if resp.status().as_u16() == 429 => {
                    // Rate limited by server — back off more aggressively
                    sleep(delay * 5).await;
                    delay *= 2;
                }
                Ok(resp) => {
                    return Err(format!("HTTP {}: {}", resp.status(), url));
                }
                Err(e) if attempt < 2 => {
                    sleep(delay).await;
                    delay *= 2;
                }
                Err(e) => return Err(format!("Failed after 3 attempts: {}", e)),
            }
        }
        Err("Exhausted retries".into())
    }
}

#[tokio::main]
async fn main() {
    let scraper = Scraper::new(
        10,   // Max 10 concurrent requests
        5.0,  // Max 5 requests per second
    );

    let urls = vec![
        "https://example.com/page1".into(),
        "https://example.com/page2".into(),
        "https://example.com/page3".into(),
    ];

    let results = scraper.scrape_urls(urls).await;
    for (i, result) in results.iter().enumerate() {
        match result {
            Ok(body) => println!("URL {}: {} bytes", i, body.len()),
            Err(e) => println!("URL {}: ERROR: {}", i, e),
        }
    }
}
```

### Pattern 3: Channels for Decoupled Pipeline

```rust
use tokio::sync::mpsc;

/// Three-stage pipeline: fetch → process → store
/// Each stage runs independently, connected by channels.
/// Backpressure is automatic: if store is slow, process blocks
/// on send, which makes fetch block on send — no unbounded queues.
async fn pipeline() {
    let (fetch_tx, mut fetch_rx) = mpsc::channel::<String>(32);    // Bounded!
    let (process_tx, mut process_rx) = mpsc::channel::<Vec<u8>>(16);

    // Stage 1: Fetch
    let fetcher = tokio::spawn(async move {
        let urls = vec!["url1", "url2", "url3"];
        for url in urls {
            let body = format!("Content from {}", url);
            // send() blocks if channel is full (backpressure)
            if fetch_tx.send(body).await.is_err() {
                break; // Receiver dropped — pipeline shutting down
            }
        }
    });

    // Stage 2: Process
    let processor = tokio::spawn(async move {
        while let Some(html) = fetch_rx.recv().await {
            let processed = html.to_uppercase().into_bytes();
            if process_tx.send(processed).await.is_err() {
                break;
            }
        }
    });

    // Stage 3: Store
    let storer = tokio::spawn(async move {
        let mut count = 0;
        while let Some(data) = process_rx.recv().await {
            count += 1;
            println!("Stored item {}: {} bytes", count, data.len());
        }
        println!("Pipeline complete: {} items processed", count);
    });

    // Wait for all stages
    let _ = tokio::join!(fetcher, processor, storer);
}
```

The critical insight about Rust async: the compiler guarantees that your concurrent code is free of data races at compile time. The `Send + Sync` bounds, `Arc<Mutex<T>>` pattern, and ownership system mean that if your async code compiles, it's thread-safe. This is Rust's unique value proposition for concurrent systems: correctness by construction, not by testing.""",
    ),

    (
        "Nix and NixOS for reproducible development environments",
        "Explain Nix — the package manager and build system that guarantees reproducibility. How does it differ from Docker, and when should you use it? Show practical examples for development environments and CI/CD.",
        """## Nix: Truly Reproducible Builds and Environments

### The Problem Nix Solves

"Works on my machine" exists because development environments are mutable. Installing Python 3.12 might break a project that needs 3.11. A system update might change OpenSSL. Docker helps by isolating environments, but Dockerfiles are imperative — `apt-get install python3` gives you whatever version the mirror has today.

Nix makes environments **purely functional**: every package is built from a precise description (inputs → outputs), and the output is stored in a content-addressed path. Same inputs always produce the same output. No mutation, no side effects, no surprises.

### Nix vs Docker

| Aspect | Docker | Nix |
|--------|--------|-----|
| **Reproducibility** | Approximate (layer caching, mutable base images) | Exact (content-addressed, hermetic) |
| **Granularity** | Container (whole OS image) | Package (individual binaries) |
| **Dev environment** | Runs in container (different from host) | Runs on host (native performance) |
| **Build cache** | Layer-based (invalidates everything below changed layer) | Per-derivation (only rebuilds what changed) |
| **Size** | 100MB-1GB+ per image | Exact packages needed (often 50-200MB) |
| **Sharing** | Registry (push/pull images) | Binary cache (content-addressed) |

### Nix Flakes: Modern Nix for Projects

```nix
# flake.nix — Pin exact versions of ALL dependencies
{
  description = "HiveAI development environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.05";  # Pinned version
    flake-utils.url = "github:numtide/flake-utils";
    rust-overlay.url = "github:oxalica/rust-overlay";
  };

  outputs = { self, nixpkgs, flake-utils, rust-overlay }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        overlays = [ rust-overlay.overlays.default ];
        pkgs = import nixpkgs { inherit system overlays; };

        # Pin exact Rust version (not "latest", not "stable" — EXACT)
        rust = pkgs.rust-bin.stable."1.77.0".default.override {
          extensions = [ "rust-src" "rust-analyzer" ];
          targets = [ "wasm32-unknown-unknown" ];
        };
      in
      {
        # Development shell — enter with: nix develop
        devShells.default = pkgs.mkShell {
          buildInputs = [
            # Languages
            pkgs.python311          # Exact Python 3.11
            pkgs.python311Packages.pip
            pkgs.python311Packages.virtualenv
            rust                     # Exact Rust 1.77.0
            pkgs.go_1_22            # Exact Go 1.22

            # Tools
            pkgs.sqlite
            pkgs.ollama
            pkgs.git
            pkgs.nodejs_20          # Exact Node 20

            # Build dependencies
            pkgs.openssl
            pkgs.pkg-config
            pkgs.cmake
          ];

          # Environment variables set when entering the shell
          shellHook = ''
            echo "HiveAI dev environment loaded"
            echo "Python: $(python --version)"
            echo "Rust: $(rustc --version)"
            echo "Go: $(go version)"
            export VIRTUAL_ENV=$PWD/.venv
            [ -d $VIRTUAL_ENV ] || python -m venv $VIRTUAL_ENV
            source $VIRTUAL_ENV/bin/activate
          '';
        };

        # Packages — build with: nix build
        packages.default = pkgs.stdenv.mkDerivation {
          name = "hiveai";
          src = ./.;
          buildInputs = [ pkgs.python311 ];
          buildPhase = ''
            python -m compileall hiveai/
          '';
          installPhase = ''
            mkdir -p $out/lib
            cp -r hiveai/ $out/lib/
          '';
        };
      }
    );
}
```

### Using Nix for Development

```bash
# Enter the development environment (all tools available instantly)
nix develop

# Or run a single command in the environment
nix develop --command python -m pytest

# Build the project
nix build

# Run directly without installing
nix run

# Show what would be built (dependency tree)
nix flake show
```

### Nix for CI/CD: Cacheable, Reproducible Builds

```yaml
# .github/workflows/ci.yml — GitHub Actions with Nix
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: cachix/install-nix-action@v26
        with:
          nix_path: nixpkgs=channel:nixos-24.05
      - uses: cachix/cachix-action@v14
        with:
          name: your-project  # Binary cache — builds are cached and shared
          authToken: '${{ secrets.CACHIX_AUTH_TOKEN }}'

      # First run: builds everything (~10 minutes)
      # Subsequent runs: pulls from cache (~30 seconds)
      - run: nix develop --command python -m pytest
      - run: nix build
```

### Per-Project Shells with direnv

```bash
# .envrc — Automatically enter Nix environment when you cd into the project
use flake

# Now:
# cd ~/projects/hiveai  → Python 3.11 + Rust 1.77 + Go 1.22 available
# cd ~/projects/other   → Different versions, different tools
# No conflicts, no version managers, no path hacks
```

### When to Use Nix

Use Nix when: you need exact reproducibility (scientific computing, regulated industries), your team has different OS versions, your CI builds are flaky due to dependency drift, or you maintain multiple projects with conflicting dependencies.

Don't use Nix when: your team is small and Docker works fine, you're on Windows (Nix support is limited), or the learning curve isn't worth it for a short-lived project.

The learning curve is real: Nix's functional language is unlike anything most developers have seen. But once you internalize the model — immutable packages, content-addressed store, declarative configurations — it becomes hard to go back to mutable package managers.""",
    ),
]
