"""Rust systems programming — unsafe code, memory layout, Axum web, CLI with clap, serde custom serialization."""

PAIRS = [
    (
        "rust/unsafe-code-ffi",
        "Show Rust unsafe code patterns including raw pointers, FFI with C, transmute, and when unsafe is justified.",
        '''Rust unsafe code: raw pointers, FFI, transmute, and safety contracts:

```rust
// --- Raw pointers and unsafe blocks ---

use std::ptr;
use std::mem;

// Raw pointer basics
fn raw_pointer_fundamentals() {
    let mut x = 42;

    // Creating raw pointers is safe — dereferencing is unsafe
    let raw_const: *const i32 = &x as *const i32;
    let raw_mut: *mut i32 = &mut x as *mut i32;

    unsafe {
        // Dereference raw pointers
        println!("Value: {}", *raw_const);
        *raw_mut = 100;
        println!("Modified: {}", *raw_mut);
    }

    // Pointer arithmetic
    let arr = [10, 20, 30, 40, 50];
    let ptr = arr.as_ptr();

    unsafe {
        for i in 0..arr.len() {
            let val = *ptr.add(i); // ptr + i * size_of::<i32>()
            println!("arr[{}] = {}", i, val);
        }
    }
}

// Safe wrapper around unsafe code (the standard pattern)
pub struct RingBuffer<T> {
    buffer: *mut T,
    capacity: usize,
    head: usize,
    tail: usize,
    len: usize,
}

impl<T> RingBuffer<T> {
    pub fn new(capacity: usize) -> Self {
        assert!(capacity > 0, "Capacity must be > 0");
        let layout = std::alloc::Layout::array::<T>(capacity).unwrap();
        let buffer = unsafe { std::alloc::alloc(layout) as *mut T };

        if buffer.is_null() {
            std::alloc::handle_alloc_error(layout);
        }

        RingBuffer {
            buffer,
            capacity,
            head: 0,
            tail: 0,
            len: 0,
        }
    }

    pub fn push(&mut self, value: T) -> Result<(), T> {
        if self.len == self.capacity {
            return Err(value); // Full
        }
        unsafe {
            ptr::write(self.buffer.add(self.tail), value);
        }
        self.tail = (self.tail + 1) % self.capacity;
        self.len += 1;
        Ok(())
    }

    pub fn pop(&mut self) -> Option<T> {
        if self.len == 0 {
            return None;
        }
        let value = unsafe { ptr::read(self.buffer.add(self.head)) };
        self.head = (self.head + 1) % self.capacity;
        self.len -= 1;
        Some(value)
    }

    pub fn len(&self) -> usize {
        self.len
    }

    pub fn is_empty(&self) -> bool {
        self.len == 0
    }
}

// SAFETY: RingBuffer owns its data and doesn't share it
unsafe impl<T: Send> Send for RingBuffer<T> {}
unsafe impl<T: Sync> Sync for RingBuffer<T> {}

impl<T> Drop for RingBuffer<T> {
    fn drop(&mut self) {
        // Drop remaining elements
        while let Some(_) = self.pop() {}
        // Deallocate buffer
        let layout = std::alloc::Layout::array::<T>(self.capacity).unwrap();
        unsafe {
            std::alloc::dealloc(self.buffer as *mut u8, layout);
        }
    }
}
```

```rust
// --- FFI: calling C from Rust ---

use std::ffi::{CStr, CString};
use std::os::raw::{c_char, c_int, c_double};

// Declare external C functions
extern "C" {
    fn strlen(s: *const c_char) -> usize;
    fn strcmp(s1: *const c_char, s2: *const c_char) -> c_int;
    fn sqrt(x: c_double) -> c_double;
}

// Safe wrapper for C string length
fn safe_strlen(s: &str) -> usize {
    let c_string = CString::new(s).expect("CString::new failed (null byte in string)");
    unsafe { strlen(c_string.as_ptr()) }
}

// Linking to a custom C library
// build.rs:
// fn main() {
//     cc::Build::new()
//         .file("src/mylib.c")
//         .compile("mylib");
// }

// Opaque C type pattern
#[repr(C)]
pub struct CDatabase {
    _private: [u8; 0], // Opaque — cannot construct from Rust
}

extern "C" {
    fn db_open(path: *const c_char) -> *mut CDatabase;
    fn db_close(db: *mut CDatabase);
    fn db_query(db: *mut CDatabase, sql: *const c_char) -> c_int;
}

// Safe Rust wrapper with RAII
pub struct Database {
    handle: *mut CDatabase,
}

impl Database {
    pub fn open(path: &str) -> Result<Self, String> {
        let c_path = CString::new(path).map_err(|e| e.to_string())?;
        let handle = unsafe { db_open(c_path.as_ptr()) };
        if handle.is_null() {
            return Err("Failed to open database".into());
        }
        Ok(Database { handle })
    }

    pub fn query(&self, sql: &str) -> Result<i32, String> {
        let c_sql = CString::new(sql).map_err(|e| e.to_string())?;
        let result = unsafe { db_query(self.handle, c_sql.as_ptr()) };
        if result < 0 {
            Err(format!("Query failed with code {}", result))
        } else {
            Ok(result)
        }
    }
}

impl Drop for Database {
    fn drop(&mut self) {
        unsafe { db_close(self.handle) };
    }
}

// Exposing Rust to C
#[no_mangle]
pub extern "C" fn rust_add(a: c_int, b: c_int) -> c_int {
    a + b
}

#[no_mangle]
pub extern "C" fn rust_greet(name: *const c_char) -> *mut c_char {
    let c_str = unsafe {
        assert!(!name.is_null());
        CStr::from_ptr(name)
    };
    let greeting = format!("Hello, {}!", c_str.to_str().unwrap_or("unknown"));
    CString::new(greeting).unwrap().into_raw()
}

// Caller MUST call this to free the string returned by rust_greet
#[no_mangle]
pub extern "C" fn rust_free_string(s: *mut c_char) {
    if !s.is_null() {
        unsafe { drop(CString::from_raw(s)) };
    }
}
```

```rust
// --- transmute and mem operations ---

use std::mem;

// transmute: reinterpret bits (extremely dangerous)
fn transmute_examples() {
    // Safe: same-size integer conversion
    let x: u32 = 0x41424344;
    let bytes: [u8; 4] = unsafe { mem::transmute(x) };
    println!("Bytes: {:?}", bytes); // Platform-dependent (endianness)

    // Prefer safe alternatives:
    let bytes_safe = x.to_le_bytes(); // Explicit endianness
    let back = u32::from_le_bytes(bytes_safe);

    // transmute for enum with known repr
    #[repr(u8)]
    enum Direction {
        North = 0,
        South = 1,
        East = 2,
        West = 3,
    }

    fn direction_from_u8(val: u8) -> Option<Direction> {
        if val <= 3 {
            Some(unsafe { mem::transmute(val) })
        } else {
            None // Invalid discriminant
        }
    }

    // MaybeUninit for safe uninitialized memory
    use std::mem::MaybeUninit;

    fn create_array() -> [i32; 100] {
        let mut arr: [MaybeUninit<i32>; 100] = unsafe {
            MaybeUninit::uninit().assume_init()
        };

        for (i, elem) in arr.iter_mut().enumerate() {
            elem.write(i as i32 * 2);
        }

        // SAFETY: All elements have been initialized
        unsafe { mem::transmute(arr) }
    }

    // size_of, align_of
    println!("Size of i32: {}", mem::size_of::<i32>());       // 4
    println!("Align of i32: {}", mem::align_of::<i32>());     // 4
    println!("Size of String: {}", mem::size_of::<String>()); // 24 (ptr + len + cap)
    println!("Size of &str: {}", mem::size_of::<&str>());     // 16 (ptr + len)
}
```

Unsafe operations reference:

| Operation | Risk Level | Safe Alternative |
|-----------|-----------|------------------|
| `*ptr` (dereference) | High | References `&T` / `&mut T` |
| `transmute` | Very High | `as` casts, `from_le_bytes` |
| `alloc` / `dealloc` | High | `Vec`, `Box`, `Arc` |
| `ptr::write` / `ptr::read` | High | Normal assignment |
| Calling C functions | Medium | Bindgen-generated wrappers |
| `impl Send/Sync` | High | Auto-derived when safe |
| `MaybeUninit` | Medium | `Default::default()` |
| Mutable static | High | `OnceLock`, `Mutex` |

Key patterns:
1. Wrap unsafe code in safe abstractions — the public API should be impossible to misuse
2. Document SAFETY comments above every `unsafe` block explaining why the invariants hold
3. Use `CString`/`CStr` for FFI string conversion — never pass Rust `&str` directly to C
4. Always implement `Drop` for types that own raw pointers to prevent memory leaks
5. Prefer `MaybeUninit` over `mem::uninitialized()` (deprecated) for uninitialized memory
6. Use `#[repr(C)]` on structs passed to/from C to guarantee ABI-compatible memory layout'''
    ),
    (
        "rust/memory-layout-repr",
        "Show Rust memory layout patterns including repr attributes, struct padding, enum layout, and zero-cost abstractions.",
        '''Rust memory layout: repr attributes, padding, and zero-cost abstractions:

```rust
// --- Struct layout and repr ---

use std::mem;

// Default Rust layout: compiler may reorder fields for optimization
struct DefaultLayout {
    a: u8,    // 1 byte
    b: u64,   // 8 bytes
    c: u16,   // 2 bytes
    d: u8,    // 1 byte
}
// Compiler may reorder to: b(8) + c(2) + a(1) + d(1) + padding = 16 bytes
// (instead of naive 24 bytes with padding)

// #[repr(C)] — C-compatible layout, no reordering
#[repr(C)]
struct CLayout {
    a: u8,    // offset 0, 1 byte + 7 padding
    b: u64,   // offset 8, 8 bytes
    c: u16,   // offset 16, 2 bytes
    d: u8,    // offset 18, 1 byte + 5 padding
}
// Total: 24 bytes (with C-style padding for alignment)

// #[repr(packed)] — no padding (may cause unaligned access)
#[repr(C, packed)]
struct PackedLayout {
    a: u8,
    b: u64,
    c: u16,
    d: u8,
}
// Total: 12 bytes (no padding, but unaligned access to b!)

// #[repr(align(N))] — minimum alignment
#[repr(C, align(64))]
struct CacheLineAligned {
    data: [u8; 32],
}
// Total: 64 bytes (padded to cache line boundary)
// Useful for preventing false sharing in concurrent code

// #[repr(transparent)] — same layout as the inner field
#[repr(transparent)]
struct Meters(f64);
// Identical layout to f64 — zero-cost newtype

fn print_layout<T>(name: &str) {
    println!(
        "{}: size={}, align={}",
        name,
        mem::size_of::<T>(),
        mem::align_of::<T>(),
    );
}

fn show_layouts() {
    print_layout::<DefaultLayout>("DefaultLayout");  // 16, 8
    print_layout::<CLayout>("CLayout");              // 24, 8
    print_layout::<PackedLayout>("PackedLayout");    // 12, 1
    print_layout::<CacheLineAligned>("CacheAligned"); // 64, 64
    print_layout::<Meters>("Meters");                // 8, 8
}
```

```rust
// --- Enum layout and niche optimization ---

use std::mem;
use std::num::NonZeroU64;

// Simple enum — tag + largest variant
enum Shape {
    Circle(f64),          // tag(8) + f64(8) = 16
    Rectangle(f64, f64),  // tag(8) + 2*f64(16) = 24
    Triangle(f64, f64, f64), // tag(8) + 3*f64(24) = 32
}
// Size of Shape: 32 (tag + largest variant)

// Niche optimization: Option<&T> is same size as &T
// because null pointer is the None variant
fn niche_demo() {
    print_layout::<&u64>("&u64");                     // 8 bytes
    print_layout::<Option<&u64>>("Option<&u64>");     // 8 bytes!  (niche = null)
    print_layout::<Option<Option<&u64>>>("Option<Option<&u64>>"); // 8 bytes!

    print_layout::<NonZeroU64>("NonZeroU64");         // 8 bytes
    print_layout::<Option<NonZeroU64>>("Option<NonZeroU64>"); // 8 bytes (niche = 0)

    // Box, &, and NonZero types have niches
    print_layout::<Box<u64>>("Box<u64>");             // 8 bytes
    print_layout::<Option<Box<u64>>>("Option<Box<u64>>"); // 8 bytes
}

// C-style enum with explicit discriminant
#[repr(u8)]
enum Status {
    Active = 0,
    Inactive = 1,
    Suspended = 2,
    Deleted = 3,
}
// Size: 1 byte (just the u8 discriminant)

// Tagged union for FFI
#[repr(C)]
enum CResult {
    Ok { value: i64 },
    Err { code: i32, message: [u8; 256] },
}

// Fieldless enum with repr for bitflags
#[repr(u32)]
enum Permission {
    Read    = 0b001,
    Write   = 0b010,
    Execute = 0b100,
}
```

```rust
// --- Zero-cost abstractions and layout optimizations ---

use std::marker::PhantomData;

// PhantomData: zero-size type for compile-time guarantees
struct TypedId<T> {
    id: u64,
    _marker: PhantomData<T>,  // Zero bytes, enforces type safety
}

struct User;
struct Order;

fn get_user(_id: TypedId<User>) -> String { "user".into() }
fn get_order(_id: TypedId<Order>) -> String { "order".into() }

fn typed_id_demo() {
    let user_id = TypedId::<User> { id: 1, _marker: PhantomData };
    let order_id = TypedId::<Order> { id: 1, _marker: PhantomData };

    get_user(user_id);
    get_order(order_id);
    // get_user(order_id); // Compile error! Type mismatch

    // Same size as raw u64
    assert_eq!(mem::size_of::<TypedId<User>>(), mem::size_of::<u64>());
}

// Zero-sized types (ZSTs)
struct Marker;  // 0 bytes

// Vec<Marker> uses no heap memory (just len + capacity tracking)
fn zst_demo() {
    assert_eq!(mem::size_of::<Marker>(), 0);
    assert_eq!(mem::size_of::<PhantomData<String>>(), 0);
    assert_eq!(mem::size_of::<()>(), 0);

    // HashMap<K, ()> is essentially a HashSet
}

// String/Vec/slice layout
fn collection_layouts() {
    // String = { ptr: *mut u8, len: usize, cap: usize } = 24 bytes
    print_layout::<String>("String");

    // &str = { ptr: *const u8, len: usize } = 16 bytes (fat pointer)
    print_layout::<&str>("&str");

    // Vec<T> = { ptr: *mut T, len: usize, cap: usize } = 24 bytes
    print_layout::<Vec<u8>>("Vec<u8>");

    // &[T] = { ptr: *const T, len: usize } = 16 bytes (fat pointer)
    print_layout::<&[u8]>("&[u8]");

    // Box<dyn Trait> = { data_ptr, vtable_ptr } = 16 bytes (fat pointer)
    print_layout::<Box<dyn std::fmt::Debug>>("Box<dyn Debug>");

    // Option<Box<T>> = 8 bytes (niche optimization!)
    print_layout::<Option<Box<u8>>>("Option<Box<u8>>");
}

fn main() {
    show_layouts();
    niche_demo();
    typed_id_demo();
    collection_layouts();
}
```

Memory layout summary:

| Type | Size (64-bit) | Notes |
|------|--------------|-------|
| `u8` / `bool` | 1 byte | Alignment: 1 |
| `u32` / `i32` / `f32` | 4 bytes | Alignment: 4 |
| `u64` / `i64` / `f64` | 8 bytes | Alignment: 8 |
| `usize` / `*const T` | 8 bytes | Pointer-sized |
| `&T` | 8 bytes | Thin pointer |
| `&[T]` / `&str` | 16 bytes | Fat pointer (ptr + len) |
| `&dyn Trait` | 16 bytes | Fat pointer (ptr + vtable) |
| `String` / `Vec<T>` | 24 bytes | ptr + len + cap |
| `Option<&T>` | 8 bytes | Niche optimization (null = None) |
| `Option<Box<T>>` | 8 bytes | Niche optimization |
| `PhantomData<T>` | 0 bytes | Zero-sized marker |

Key patterns:
1. Use `#[repr(C)]` for FFI structs — Rust default layout reorders fields for optimization
2. `#[repr(transparent)]` creates zero-cost newtypes with identical layout to the inner type
3. Niche optimization makes `Option<&T>` and `Option<Box<T>>` the same size as the raw pointer
4. `#[repr(align(64))]` aligns to cache line boundaries — prevents false sharing in concurrent code
5. Use `PhantomData<T>` for zero-cost type-level markers that compile away completely
6. Avoid `#[repr(packed)]` unless required for exact binary format — unaligned access is slow and UB on some architectures'''
    ),
    (
        "rust/axum-web-framework",
        "Show Axum web framework patterns including routing, extractors, middleware, state management, and error handling.",
        '''Axum web framework patterns for production REST APIs:

```rust
// --- Axum app setup with routing and state ---

use axum::{
    Router, Json, Extension,
    extract::{Path, Query, State},
    http::{StatusCode, HeaderMap},
    middleware,
    response::IntoResponse,
    routing::{get, post, put, delete},
};
use serde::{Deserialize, Serialize};
use sqlx::PgPool;
use std::sync::Arc;
use tower::ServiceBuilder;
use tower_http::{
    cors::CorsLayer,
    trace::TraceLayer,
    compression::CompressionLayer,
};

// Shared application state
#[derive(Clone)]
struct AppState {
    db: PgPool,
    config: Arc<AppConfig>,
}

struct AppConfig {
    jwt_secret: String,
    max_page_size: usize,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    tracing_subscriber::init();

    let pool = PgPool::connect(&std::env::var("DATABASE_URL")?).await?;
    sqlx::migrate!().run(&pool).await?;

    let state = AppState {
        db: pool,
        config: Arc::new(AppConfig {
            jwt_secret: std::env::var("JWT_SECRET")?,
            max_page_size: 100,
        }),
    };

    let app = Router::new()
        // Public routes
        .route("/health", get(health_check))
        .route("/auth/login", post(login))
        // User routes
        .nest("/api/users", user_routes())
        // Post routes
        .nest("/api/posts", post_routes())
        // Global middleware (applied bottom-up)
        .layer(
            ServiceBuilder::new()
                .layer(TraceLayer::new_for_http())
                .layer(CompressionLayer::new())
                .layer(CorsLayer::permissive())
        )
        .with_state(state);

    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000").await?;
    tracing::info!("Server listening on :3000");
    axum::serve(listener, app).await?;
    Ok(())
}

fn user_routes() -> Router<AppState> {
    Router::new()
        .route("/", get(list_users).post(create_user))
        .route("/:id", get(get_user).put(update_user).delete(delete_user))
}

fn post_routes() -> Router<AppState> {
    Router::new()
        .route("/", get(list_posts).post(create_post))
        .route("/:id", get(get_post))
}
```

```rust
// --- Extractors and handlers ---

use axum::extract::{Path, Query, State, Json};
use serde::{Deserialize, Serialize};
use sqlx::FromRow;
use uuid::Uuid;

#[derive(Serialize, FromRow)]
struct User {
    id: Uuid,
    name: String,
    email: String,
    created_at: chrono::DateTime<chrono::Utc>,
}

#[derive(Deserialize)]
struct CreateUserPayload {
    name: String,
    email: String,
}

#[derive(Deserialize)]
struct PaginationParams {
    #[serde(default = "default_page")]
    page: u32,
    #[serde(default = "default_per_page")]
    per_page: u32,
}

fn default_page() -> u32 { 1 }
fn default_per_page() -> u32 { 20 }

#[derive(Serialize)]
struct PaginatedResponse<T: Serialize> {
    data: Vec<T>,
    page: u32,
    per_page: u32,
    total: i64,
}

// Handler with multiple extractors
async fn list_users(
    State(state): State<AppState>,
    Query(params): Query<PaginationParams>,
) -> Result<Json<PaginatedResponse<User>>, AppError> {
    let per_page = params.per_page.min(state.config.max_page_size as u32);
    let offset = (params.page.saturating_sub(1)) * per_page;

    let total: (i64,) = sqlx::query_as("SELECT COUNT(*) FROM users")
        .fetch_one(&state.db)
        .await?;

    let users: Vec<User> = sqlx::query_as(
        "SELECT id, name, email, created_at FROM users ORDER BY created_at DESC LIMIT $1 OFFSET $2"
    )
    .bind(per_page as i64)
    .bind(offset as i64)
    .fetch_all(&state.db)
    .await?;

    Ok(Json(PaginatedResponse {
        data: users,
        page: params.page,
        per_page,
        total: total.0,
    }))
}

async fn get_user(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<Json<User>, AppError> {
    let user: User = sqlx::query_as(
        "SELECT id, name, email, created_at FROM users WHERE id = $1"
    )
    .bind(id)
    .fetch_optional(&state.db)
    .await?
    .ok_or(AppError::NotFound(format!("User {}", id)))?;

    Ok(Json(user))
}

async fn create_user(
    State(state): State<AppState>,
    Json(payload): Json<CreateUserPayload>,
) -> Result<(StatusCode, Json<User>), AppError> {
    if payload.name.len() < 2 {
        return Err(AppError::Validation("Name must be at least 2 characters".into()));
    }

    let user: User = sqlx::query_as(
        "INSERT INTO users (id, name, email) VALUES ($1, $2, $3) RETURNING *"
    )
    .bind(Uuid::new_v4())
    .bind(&payload.name)
    .bind(&payload.email)
    .fetch_one(&state.db)
    .await
    .map_err(|e| match e {
        sqlx::Error::Database(ref db_err) if db_err.constraint() == Some("users_email_key") => {
            AppError::Conflict(format!("Email {} already exists", payload.email))
        }
        other => AppError::Database(other),
    })?;

    Ok((StatusCode::CREATED, Json(user)))
}

async fn health_check() -> impl IntoResponse {
    Json(serde_json::json!({ "status": "ok" }))
}

async fn login() -> impl IntoResponse { StatusCode::NOT_IMPLEMENTED }
async fn update_user() -> impl IntoResponse { StatusCode::NOT_IMPLEMENTED }
async fn delete_user() -> impl IntoResponse { StatusCode::NOT_IMPLEMENTED }
async fn list_posts() -> impl IntoResponse { StatusCode::NOT_IMPLEMENTED }
async fn create_post() -> impl IntoResponse { StatusCode::NOT_IMPLEMENTED }
async fn get_post() -> impl IntoResponse { StatusCode::NOT_IMPLEMENTED }
```

```rust
// --- Custom middleware and error handling ---

use axum::{
    extract::Request,
    http::{header, StatusCode},
    middleware::Next,
    response::{IntoResponse, Response},
    Json,
};
use serde::Serialize;
use thiserror::Error;

// Application error type
#[derive(Error, Debug)]
enum AppError {
    #[error("Not found: {0}")]
    NotFound(String),

    #[error("Validation error: {0}")]
    Validation(String),

    #[error("Conflict: {0}")]
    Conflict(String),

    #[error("Unauthorized")]
    Unauthorized,

    #[error("Database error")]
    Database(#[from] sqlx::Error),

    #[error("Internal error")]
    Internal(#[from] anyhow::Error),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        #[derive(Serialize)]
        struct ErrorBody {
            error: String,
            code: u16,
        }

        let (status, message) = match &self {
            AppError::NotFound(msg) => (StatusCode::NOT_FOUND, msg.clone()),
            AppError::Validation(msg) => (StatusCode::BAD_REQUEST, msg.clone()),
            AppError::Conflict(msg) => (StatusCode::CONFLICT, msg.clone()),
            AppError::Unauthorized => (StatusCode::UNAUTHORIZED, "Unauthorized".into()),
            AppError::Database(e) => {
                tracing::error!(error = ?e, "Database error");
                (StatusCode::INTERNAL_SERVER_ERROR, "Internal server error".into())
            }
            AppError::Internal(e) => {
                tracing::error!(error = ?e, "Internal error");
                (StatusCode::INTERNAL_SERVER_ERROR, "Internal server error".into())
            }
        };

        (status, Json(ErrorBody {
            error: message,
            code: status.as_u16(),
        })).into_response()
    }
}

// Auth middleware
async fn auth_middleware(
    State(state): State<AppState>,
    mut request: Request,
    next: Next,
) -> Result<Response, AppError> {
    let token = request
        .headers()
        .get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "))
        .ok_or(AppError::Unauthorized)?;

    let claims = validate_jwt(token, &state.config.jwt_secret)
        .map_err(|_| AppError::Unauthorized)?;

    // Inject claims into request extensions
    request.extensions_mut().insert(claims);

    Ok(next.run(request).await)
}

#[derive(Clone)]
struct Claims {
    user_id: Uuid,
    role: String,
}

fn validate_jwt(_token: &str, _secret: &str) -> Result<Claims, ()> {
    // JWT validation logic
    Ok(Claims {
        user_id: Uuid::new_v4(),
        role: "user".into(),
    })
}

// Request timing middleware
async fn timing_middleware(request: Request, next: Next) -> Response {
    let start = std::time::Instant::now();
    let method = request.method().clone();
    let uri = request.uri().clone();

    let response = next.run(request).await;

    let duration = start.elapsed();
    tracing::info!(
        method = %method,
        uri = %uri,
        status = %response.status(),
        duration_ms = %duration.as_millis(),
        "Request completed"
    );

    response
}
```

Axum extractor comparison:

| Extractor | Source | Example |
|-----------|--------|---------|
| `State(s)` | App state | `State(state): State<AppState>` |
| `Path(p)` | URL path params | `Path(id): Path<Uuid>` |
| `Query(q)` | URL query string | `Query(params): Query<Pagination>` |
| `Json(b)` | Request body | `Json(payload): Json<CreateUser>` |
| `HeaderMap` | All headers | `headers: HeaderMap` |
| `Extension(e)` | Request extensions | `Extension(claims): Extension<Claims>` |
| `Request` | Full request | `request: Request` (for middleware) |

Key patterns:
1. Use `Router::new().with_state(state)` for dependency injection — state is cloned per handler
2. Extractors run in order — if one fails, subsequent extractors and the handler are skipped
3. Return `Result<T, AppError>` from handlers for automatic error-to-response conversion
4. Use `Router::nest("/prefix", sub_router)` to group routes with shared path prefixes
5. Middleware applies bottom-up in the `layer()` chain — first added = outermost
6. Use request extensions (`request.extensions_mut().insert(claims)`) to pass data from middleware to handlers'''
    ),
    (
        "rust/cli-clap",
        "Show Rust CLI tool patterns with clap including subcommands, argument validation, and structured output.",
        '''Rust CLI tools with clap derive macro, subcommands, and structured output:

```rust
// --- CLI definition with clap derive ---

use clap::{Parser, Subcommand, Args, ValueEnum};
use serde::{Serialize, Deserialize};
use std::path::PathBuf;
use anyhow::{Context, Result, bail};

/// Database migration and management tool
#[derive(Parser)]
#[command(
    name = "dbctl",
    version,
    about = "Database migration and management CLI",
    long_about = None,
    propagate_version = true,
)]
struct Cli {
    /// Database connection URL
    #[arg(
        short,
        long,
        env = "DATABASE_URL",
        global = true,
    )]
    database_url: String,

    /// Output format
    #[arg(
        short = 'f',
        long,
        default_value = "table",
        global = true,
    )]
    format: OutputFormat,

    /// Verbose output
    #[arg(short, long, action = clap::ArgAction::Count)]
    verbose: u8,

    #[command(subcommand)]
    command: Commands,
}

#[derive(Subcommand)]
enum Commands {
    /// Run pending migrations
    Migrate(MigrateArgs),
    /// Seed database with test data
    Seed {
        /// Path to seed data file
        #[arg(short, long, default_value = "seeds/default.sql")]
        file: PathBuf,

        /// Number of records to generate
        #[arg(short, long, default_value_t = 100)]
        count: usize,
    },
    /// Show database status
    Status,
    /// Manage users
    #[command(subcommand)]
    User(UserCommands),
    /// Export data
    Export(ExportArgs),
}

#[derive(Args)]
struct MigrateArgs {
    /// Migration direction
    #[arg(default_value = "up")]
    direction: MigrateDirection,

    /// Number of migrations to apply (0 = all)
    #[arg(short = 'n', long, default_value_t = 0)]
    steps: u32,

    /// Dry run — show SQL without executing
    #[arg(long)]
    dry_run: bool,
}

#[derive(ValueEnum, Clone)]
enum MigrateDirection {
    Up,
    Down,
    Redo,
}

#[derive(ValueEnum, Clone)]
enum OutputFormat {
    Table,
    Json,
    Csv,
}

#[derive(Subcommand)]
enum UserCommands {
    /// List all users
    List {
        #[arg(short, long)]
        role: Option<String>,

        #[arg(short, long, default_value_t = 50)]
        limit: usize,
    },
    /// Create a new user
    Create {
        #[arg(short, long)]
        name: String,

        #[arg(short, long)]
        email: String,

        #[arg(short, long, default_value = "viewer")]
        role: String,
    },
    /// Delete a user
    Delete {
        /// User ID to delete
        id: u64,

        /// Skip confirmation prompt
        #[arg(long)]
        force: bool,
    },
}

#[derive(Args)]
struct ExportArgs {
    /// Tables to export (comma-separated)
    #[arg(short, long, value_delimiter = ',')]
    tables: Vec<String>,

    /// Output directory
    #[arg(short, long, default_value = "exports")]
    output: PathBuf,

    /// Compress output files
    #[arg(long)]
    compress: bool,
}
```

```rust
// --- Command execution and structured output ---

use comfy_table::{Table, Cell, Color};
use indicatif::{ProgressBar, ProgressStyle};

#[tokio::main]
async fn main() -> Result<()> {
    let cli = Cli::parse();

    // Set up logging based on verbosity
    let log_level = match cli.verbose {
        0 => tracing::Level::WARN,
        1 => tracing::Level::INFO,
        2 => tracing::Level::DEBUG,
        _ => tracing::Level::TRACE,
    };
    tracing_subscriber::fmt()
        .with_max_level(log_level)
        .init();

    match cli.command {
        Commands::Migrate(args) => run_migrate(&cli.database_url, args).await?,
        Commands::Seed { file, count } => run_seed(&cli.database_url, file, count).await?,
        Commands::Status => run_status(&cli.database_url, &cli.format).await?,
        Commands::User(cmd) => run_user_command(&cli.database_url, cmd, &cli.format).await?,
        Commands::Export(args) => run_export(&cli.database_url, args).await?,
    }

    Ok(())
}

async fn run_migrate(db_url: &str, args: MigrateArgs) -> Result<()> {
    println!("Connecting to database...");

    if args.dry_run {
        println!("DRY RUN — no changes will be applied");
    }

    // Progress bar for migration
    let pb = ProgressBar::new(10);
    pb.set_style(
        ProgressStyle::default_bar()
            .template("[{elapsed_precise}] {bar:40.cyan/blue} {pos}/{len} {msg}")?
            .progress_chars("=> "),
    );

    for i in 0..10 {
        pb.set_message(format!("Migration {}", i + 1));
        tokio::time::sleep(std::time::Duration::from_millis(200)).await;
        pb.inc(1);
    }

    pb.finish_with_message("Migrations complete");
    Ok(())
}

async fn run_status(db_url: &str, format: &OutputFormat) -> Result<()> {
    #[derive(Serialize)]
    struct StatusRow {
        migration: String,
        status: String,
        applied_at: String,
    }

    let rows = vec![
        StatusRow {
            migration: "001_create_users".into(),
            status: "applied".into(),
            applied_at: "2024-01-15 10:30:00".into(),
        },
        StatusRow {
            migration: "002_add_posts".into(),
            status: "applied".into(),
            applied_at: "2024-01-16 09:15:00".into(),
        },
        StatusRow {
            migration: "003_add_comments".into(),
            status: "pending".into(),
            applied_at: "-".into(),
        },
    ];

    match format {
        OutputFormat::Table => {
            let mut table = Table::new();
            table.set_header(vec!["Migration", "Status", "Applied At"]);

            for row in &rows {
                let status_cell = if row.status == "applied" {
                    Cell::new(&row.status).fg(Color::Green)
                } else {
                    Cell::new(&row.status).fg(Color::Yellow)
                };
                table.add_row(vec![
                    Cell::new(&row.migration),
                    status_cell,
                    Cell::new(&row.applied_at),
                ]);
            }
            println!("{table}");
        }
        OutputFormat::Json => {
            println!("{}", serde_json::to_string_pretty(&rows)?);
        }
        OutputFormat::Csv => {
            println!("migration,status,applied_at");
            for row in &rows {
                println!("{},{},{}", row.migration, row.status, row.applied_at);
            }
        }
    }

    Ok(())
}

async fn run_user_command(db_url: &str, cmd: UserCommands, format: &OutputFormat) -> Result<()> {
    match cmd {
        UserCommands::List { role, limit } => {
            println!("Listing users (role={:?}, limit={})", role, limit);
        }
        UserCommands::Create { name, email, role } => {
            println!("Created user: {} <{}> (role: {})", name, email, role);
        }
        UserCommands::Delete { id, force } => {
            if !force {
                print!("Delete user {}? [y/N] ", id);
                let mut input = String::new();
                std::io::stdin().read_line(&mut input)?;
                if !input.trim().eq_ignore_ascii_case("y") {
                    bail!("Aborted");
                }
            }
            println!("Deleted user {}", id);
        }
    }
    Ok(())
}

async fn run_seed(db_url: &str, file: PathBuf, count: usize) -> Result<()> {
    let file = file.canonicalize()
        .with_context(|| format!("Seed file not found: {}", file.display()))?;
    println!("Seeding from {} ({} records)", file.display(), count);
    Ok(())
}

async fn run_export(db_url: &str, args: ExportArgs) -> Result<()> {
    std::fs::create_dir_all(&args.output)
        .with_context(|| format!("Failed to create output dir: {}", args.output.display()))?;

    for table in &args.tables {
        let ext = if args.compress { "csv.gz" } else { "csv" };
        let path = args.output.join(format!("{}.{}", table, ext));
        println!("Exporting {} -> {}", table, path.display());
    }
    Ok(())
}
```

```rust
// --- Testing CLI applications ---

#[cfg(test)]
mod tests {
    use super::*;
    use clap::CommandFactory;

    #[test]
    fn verify_cli() {
        // Ensures the CLI definition is valid (catches issues at compile time)
        Cli::command().debug_assert();
    }

    #[test]
    fn test_parse_migrate() {
        let cli = Cli::parse_from([
            "dbctl",
            "--database-url", "postgres://localhost/test",
            "migrate",
            "up",
            "-n", "5",
            "--dry-run",
        ]);

        assert!(matches!(cli.command, Commands::Migrate(_)));
        if let Commands::Migrate(args) = cli.command {
            assert_eq!(args.steps, 5);
            assert!(args.dry_run);
        }
    }

    #[test]
    fn test_parse_user_create() {
        let cli = Cli::parse_from([
            "dbctl",
            "--database-url", "postgres://localhost/test",
            "user", "create",
            "--name", "Alice",
            "--email", "alice@example.com",
            "--role", "admin",
        ]);

        assert!(matches!(cli.command, Commands::User(UserCommands::Create { .. })));
    }

    #[test]
    fn test_parse_export() {
        let cli = Cli::parse_from([
            "dbctl",
            "--database-url", "postgres://localhost/test",
            "export",
            "--tables", "users,posts,comments",
            "--output", "/tmp/export",
            "--compress",
        ]);

        if let Commands::Export(args) = cli.command {
            assert_eq!(args.tables, vec!["users", "posts", "comments"]);
            assert!(args.compress);
        }
    }
}
```

Clap derive attribute comparison:

| Attribute | Level | Purpose | Example |
|-----------|-------|---------|---------|
| `#[command(name, version)]` | Struct | App metadata | `#[command(name = "dbctl")]` |
| `#[command(subcommand)]` | Field/Enum | Nested commands | `#[command(subcommand)] cmd: Commands` |
| `#[arg(short, long)]` | Field | Flag/option | `-v` / `--verbose` |
| `#[arg(env)]` | Field | Env var fallback | `env = "DATABASE_URL"` |
| `#[arg(default_value)]` | Field | Default | `default_value = "table"` |
| `#[arg(value_enum)]` | Field | Enum of choices | `format: OutputFormat` |
| `#[arg(value_delimiter)]` | Field | Split values | `--tables a,b,c` |
| `#[arg(action = Count)]` | Field | Repeated flag | `-vvv` for verbosity |
| `#[arg(global = true)]` | Field | Inherited by subcommands | `--format json` anywhere |

Key patterns:
1. Use `#[derive(Parser)]` on the root struct and `#[derive(Subcommand)]` on the enum for nested commands
2. Support environment variables with `#[arg(env = "VAR")]` for 12-factor app configuration
3. Use `#[arg(action = Count)]` for verbosity flags (`-v`, `-vv`, `-vvv`)
4. Output formats (table, JSON, CSV) let users pipe CLI output to other tools
5. Always write `Cli::command().debug_assert()` test to catch clap definition errors
6. Use `Cli::parse_from([...])` in tests to verify argument parsing without running the full app'''
    ),
    (
        "rust/serde-custom-serialization",
        "Show Rust serde patterns including custom serialize/deserialize, field attributes, and format-agnostic serialization.",
        '''Rust serde custom serialization and deserialization patterns:

```rust
// --- Serde field attributes and common patterns ---

use serde::{Serialize, Deserialize, Serializer, Deserializer};
use chrono::{DateTime, Utc, NaiveDate};
use std::collections::HashMap;

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]  // JSON convention
struct UserProfile {
    // Field renaming
    #[serde(rename = "userId")]
    id: u64,

    display_name: String,  // -> "displayName" (from rename_all)

    #[serde(rename = "email_address")]  // Override rename_all
    email: String,

    // Optional with default
    #[serde(default)]
    bio: Option<String>,

    // Skip serialization if None
    #[serde(skip_serializing_if = "Option::is_none")]
    avatar_url: Option<String>,

    // Custom serialization
    #[serde(with = "chrono::serde::ts_seconds")]
    created_at: DateTime<Utc>,

    // Flatten nested struct
    #[serde(flatten)]
    metadata: UserMetadata,

    // Default value if missing
    #[serde(default = "default_role")]
    role: String,

    // Skip entirely (never serialize or deserialize)
    #[serde(skip)]
    internal_cache: Option<String>,

    // Deserialize from multiple formats
    #[serde(deserialize_with = "deserialize_tags")]
    tags: Vec<String>,
}

fn default_role() -> String {
    "viewer".to_string()
}

#[derive(Debug, Serialize, Deserialize)]
struct UserMetadata {
    locale: String,
    timezone: String,
    #[serde(default)]
    preferences: HashMap<String, serde_json::Value>,
}

// Custom deserializer: accept both "tag1,tag2" and ["tag1", "tag2"]
fn deserialize_tags<'de, D>(deserializer: D) -> Result<Vec<String>, D::Error>
where
    D: Deserializer<'de>,
{
    #[derive(Deserialize)]
    #[serde(untagged)]
    enum TagsFormat {
        String(String),
        Array(Vec<String>),
    }

    match TagsFormat::deserialize(deserializer)? {
        TagsFormat::String(s) => Ok(s.split(',').map(|t| t.trim().to_string()).collect()),
        TagsFormat::Array(arr) => Ok(arr),
    }
}
```

```rust
// --- Custom Serialize/Deserialize implementations ---

use serde::{Serialize, Deserialize, Serializer, Deserializer};
use serde::de::{self, Visitor, MapAccess, SeqAccess};
use std::fmt;

// Custom serialization for a Money type
#[derive(Debug, Clone)]
struct Money {
    amount_cents: i64,
    currency: String,
}

impl Serialize for Money {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        use serde::ser::SerializeStruct;
        let mut state = serializer.serialize_struct("Money", 3)?;
        state.serialize_field("amount", &format!("{:.2}", self.amount_cents as f64 / 100.0))?;
        state.serialize_field("currency", &self.currency)?;
        state.serialize_field("cents", &self.amount_cents)?;
        state.end()
    }
}

impl<'de> Deserialize<'de> for Money {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        #[derive(Deserialize)]
        #[serde(untagged)]
        enum MoneyFormat {
            // "$12.50"
            String(String),
            // { "amount": "12.50", "currency": "USD" }
            Structured { amount: String, currency: String },
            // { "cents": 1250, "currency": "USD" }
            Cents { cents: i64, currency: String },
        }

        match MoneyFormat::deserialize(deserializer)? {
            MoneyFormat::String(s) => {
                let (currency, amount) = if s.starts_with('$') {
                    ("USD".to_string(), s[1..].to_string())
                } else {
                    return Err(de::Error::custom(format!("Unknown currency format: {}", s)));
                };
                let cents = amount.parse::<f64>()
                    .map_err(de::Error::custom)
                    .map(|f| (f * 100.0).round() as i64)?;
                Ok(Money { amount_cents: cents, currency })
            }
            MoneyFormat::Structured { amount, currency } => {
                let cents = amount.parse::<f64>()
                    .map_err(de::Error::custom)
                    .map(|f| (f * 100.0).round() as i64)?;
                Ok(Money { amount_cents: cents, currency })
            }
            MoneyFormat::Cents { cents, currency } => {
                Ok(Money { amount_cents: cents, currency })
            }
        }
    }
}

// Enum serialization strategies
#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "type")]  // Internally tagged: {"type": "email", "to": "..."}
enum Notification {
    #[serde(rename = "email")]
    Email { to: String, subject: String, body: String },

    #[serde(rename = "sms")]
    Sms { phone: String, message: String },

    #[serde(rename = "push")]
    Push { device_id: String, title: String, body: String },
}

// Adjacently tagged: {"type": "email", "data": {"to": "..."}}
#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "type", content = "data")]
enum Event {
    UserCreated(UserCreatedEvent),
    UserDeleted { user_id: u64 },
    OrderPlaced(OrderEvent),
}

#[derive(Debug, Serialize, Deserialize)]
struct UserCreatedEvent {
    user_id: u64,
    email: String,
}

#[derive(Debug, Serialize, Deserialize)]
struct OrderEvent {
    order_id: u64,
    total_cents: i64,
}
```

```rust
// --- Format-agnostic serialization and testing ---

use serde::{Serialize, de::DeserializeOwned};
use std::io::{Read, Write};
use anyhow::Result;

// Generic format-agnostic read/write
trait DataFormat {
    fn serialize<T: Serialize>(&self, value: &T) -> Result<Vec<u8>>;
    fn deserialize<T: DeserializeOwned>(&self, data: &[u8]) -> Result<T>;
    fn extension(&self) -> &str;
}

struct JsonFormat { pretty: bool }
struct YamlFormat;
struct TomlFormat;
struct MessagePackFormat;

impl DataFormat for JsonFormat {
    fn serialize<T: Serialize>(&self, value: &T) -> Result<Vec<u8>> {
        if self.pretty {
            Ok(serde_json::to_vec_pretty(value)?)
        } else {
            Ok(serde_json::to_vec(value)?)
        }
    }

    fn deserialize<T: DeserializeOwned>(&self, data: &[u8]) -> Result<T> {
        Ok(serde_json::from_slice(data)?)
    }

    fn extension(&self) -> &str { "json" }
}

impl DataFormat for YamlFormat {
    fn serialize<T: Serialize>(&self, value: &T) -> Result<Vec<u8>> {
        Ok(serde_yaml::to_string(value)?.into_bytes())
    }

    fn deserialize<T: DeserializeOwned>(&self, data: &[u8]) -> Result<T> {
        Ok(serde_yaml::from_slice(data)?)
    }

    fn extension(&self) -> &str { "yaml" }
}

// Config loader supporting multiple formats
fn load_config<T: DeserializeOwned>(path: &std::path::Path) -> Result<T> {
    let data = std::fs::read(path)?;
    let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("json");

    match ext {
        "json" => Ok(serde_json::from_slice(&data)?),
        "yaml" | "yml" => Ok(serde_yaml::from_slice(&data)?),
        "toml" => Ok(toml::from_str(std::str::from_utf8(&data)?)?),
        _ => anyhow::bail!("Unsupported format: {}", ext),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_money_json_roundtrip() {
        let money = Money {
            amount_cents: 1250,
            currency: "USD".into(),
        };

        let json = serde_json::to_string(&money).unwrap();
        assert!(json.contains("\"amount\":\"12.50\""));
        assert!(json.contains("\"currency\":\"USD\""));

        // Deserialize from string format
        let from_str: Money = serde_json::from_str(r#""$12.50""#).unwrap();
        assert_eq!(from_str.amount_cents, 1250);

        // Deserialize from structured format
        let from_obj: Money = serde_json::from_str(
            r#"{"amount": "12.50", "currency": "USD"}"#
        ).unwrap();
        assert_eq!(from_obj.amount_cents, 1250);
    }

    #[test]
    fn test_notification_tagged_enum() {
        let notif = Notification::Email {
            to: "user@example.com".into(),
            subject: "Hello".into(),
            body: "World".into(),
        };

        let json = serde_json::to_string(&notif).unwrap();
        assert!(json.contains(r#""type":"email""#));

        let parsed: Notification = serde_json::from_str(&json).unwrap();
        assert!(matches!(parsed, Notification::Email { .. }));
    }

    #[test]
    fn test_tags_flexible_deserialization() {
        // Array format
        let json1 = r#"{"userId": 1, "displayName": "Alice", "email_address": "a@b.com",
                        "createdAt": 1700000000, "locale": "en", "timezone": "UTC",
                        "tags": ["rust", "go"]}"#;
        let user1: UserProfile = serde_json::from_str(json1).unwrap();
        assert_eq!(user1.tags, vec!["rust", "go"]);

        // Comma-separated format
        let json2 = r#"{"userId": 1, "displayName": "Alice", "email_address": "a@b.com",
                        "createdAt": 1700000000, "locale": "en", "timezone": "UTC",
                        "tags": "rust, go"}"#;
        let user2: UserProfile = serde_json::from_str(json2).unwrap();
        assert_eq!(user2.tags, vec!["rust", "go"]);
    }
}
```

Serde attribute comparison:

| Attribute | Level | Effect |
|-----------|-------|--------|
| `#[serde(rename_all = "camelCase")]` | Container | Rename all fields |
| `#[serde(rename = "x")]` | Field | Rename single field |
| `#[serde(default)]` | Field/Container | Use `Default::default()` if missing |
| `#[serde(skip)]` | Field | Skip serialize and deserialize |
| `#[serde(skip_serializing_if = "...")]` | Field | Conditionally skip |
| `#[serde(flatten)]` | Field | Inline nested struct |
| `#[serde(with = "module")]` | Field | Custom ser/de module |
| `#[serde(untagged)]` | Enum | Try each variant in order |
| `#[serde(tag = "type")]` | Enum | Internal tag field |
| `#[serde(tag = "t", content = "c")]` | Enum | Adjacent tag + content |

Key patterns:
1. Use `#[serde(rename_all = "camelCase")]` on structs to match JSON naming conventions
2. `#[serde(flatten)]` merges nested struct fields into the parent — useful for shared metadata
3. `#[serde(untagged)]` on enums tries each variant in order — use for accepting multiple input formats
4. Custom `Deserialize` implementations handle multiple input formats (string, object, number) for one type
5. `#[serde(tag = "type")]` for internally tagged enums is the cleanest pattern for event systems
6. Write roundtrip tests for custom serialization to ensure serialize -> deserialize produces identical values'''
    ),
]
