"""
Rust language training pairs - Axum handlers, extractors, middleware, tower layers, serde
"""

pairs = [
    {
        "instruction": r'''<thinking>
The user wants a basic Axum web server in Rust. I should show routing, JSON responses, path parameters, and query parameters. I will use axum 0.7 patterns with tokio.
</thinking>

Show me how to build a basic REST API in Rust using Axum with routing, JSON responses, and extractors.''',
        "output": r'''Axum is built on tokio and tower. Here is a REST API with routing, extractors, and JSON.

```rust
use axum::{
    extract::{Path, Query, State},
    http::StatusCode, response::IntoResponse,
    routing::{get, post}, Json, Router,
};
use serde::{Deserialize, Serialize};
use std::sync::{Arc, Mutex};

#[derive(Clone, Serialize, Deserialize)]
struct Todo { id: u64, title: String, done: bool }

#[derive(Deserialize)]
struct CreateTodo { title: String }

#[derive(Deserialize)]
struct Pagination { page: Option<u32>, per_page: Option<u32> }

type Db = Arc<Mutex<Vec<Todo>>>;

async fn list_todos(
    State(db): State<Db>, Query(p): Query<Pagination>,
) -> Json<Vec<Todo>> {
    let db = db.lock().unwrap();
    let page = p.page.unwrap_or(1) as usize;
    let per = p.per_page.unwrap_or(10) as usize;
    Json(db.iter().skip((page - 1) * per).take(per).cloned().collect())
}

async fn get_todo(
    State(db): State<Db>, Path(id): Path<u64>,
) -> Result<Json<Todo>, StatusCode> {
    let db = db.lock().unwrap();
    db.iter().find(|t| t.id == id).cloned().map(Json)
        .ok_or(StatusCode::NOT_FOUND)
}

async fn create_todo(
    State(db): State<Db>, Json(input): Json<CreateTodo>,
) -> impl IntoResponse {
    let mut db = db.lock().unwrap();
    let todo = Todo { id: db.len() as u64 + 1, title: input.title, done: false };
    db.push(todo.clone());
    (StatusCode::CREATED, Json(todo))
}

#[tokio::main]
async fn main() {
    let db: Db = Arc::new(Mutex::new(Vec::new()));
    let app = Router::new()
        .route("/todos", get(list_todos).post(create_todo))
        .route("/todos/{id}", get(get_todo))
        .with_state(db);
    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000").await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
```

Key concepts:
- Extractors (`Path`, `Query`, `Json`, `State`) pull data from requests
- Handlers are async functions whose arguments are extractors
- `IntoResponse` lets you return tuples like `(StatusCode, Json<T>)`
- State is shared via `Arc<Mutex<T>>` and injected with `with_state()`'''
    },
    {
        "instruction": r'''How do I write custom middleware in Axum using tower layers? Show request logging and authentication.''',
        "output": r'''Axum uses tower layers for middleware. Here are logging and auth examples.

```rust
use axum::{
    extract::Request, http::{header, StatusCode},
    middleware::{self, Next}, response::Response,
    routing::get, Router,
};
use std::time::Instant;

async fn logging_middleware(req: Request, next: Next) -> Response {
    let method = req.method().clone();
    let uri = req.uri().clone();
    let start = Instant::now();
    let resp = next.run(req).await;
    println!("{method} {uri} -- {} ({:.2?})", resp.status(), start.elapsed());
    resp
}

async fn auth_middleware(req: Request, next: Next) -> Result<Response, StatusCode> {
    let token = req.headers().get(header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.strip_prefix("Bearer "));
    match token {
        Some(t) if t == "valid-key-123" => Ok(next.run(req).await),
        _ => Err(StatusCode::UNAUTHORIZED),
    }
}

async fn public_handler() -> &'static str { "public" }
async fn protected_handler() -> &'static str { "secret data" }

#[tokio::main]
async fn main() {
    let protected = Router::new()
        .route("/data", get(protected_handler))
        .layer(middleware::from_fn(auth_middleware));

    let public = Router::new()
        .route("/", get(public_handler));

    let app = Router::new()
        .merge(public)
        .merge(protected)
        .layer(middleware::from_fn(logging_middleware));

    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000").await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
```

Key points:
- `middleware::from_fn` wraps an async function as a tower layer
- Middleware receives the `Request` and a `Next` to call the inner handler
- Return `Result<Response, StatusCode>` to short-circuit (e.g., 401)
- Layer order matters: last added runs first (outermost)
- Apply auth only to specific route groups by layering on a sub-router'''
    },
    {
        "instruction": r'''Show how to use serde for JSON serialization and deserialization in Rust, including custom field handling and validation.''',
        "output": r'''Serde is the standard serialization framework in Rust. Here are common JSON patterns.

```rust
use serde::{Deserialize, Serialize, Deserializer};

#[derive(Debug, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
struct User {
    user_id: u64,           // becomes "userId"
    display_name: String,
    #[serde(default)]
    is_admin: bool,         // defaults to false if missing
    #[serde(skip_serializing)]
    password_hash: String,  // never in JSON output
    #[serde(deserialize_with = "non_empty")]
    email: String,
    #[serde(default = "default_role")]
    role: String,
}

fn default_role() -> String { "viewer".to_string() }

fn non_empty<'de, D: Deserializer<'de>>(d: D) -> Result<String, D::Error> {
    let s = String::deserialize(d)?;
    if s.trim().is_empty() {
        Err(serde::de::Error::custom("must not be empty"))
    } else {
        Ok(s)
    }
}

// Tagged enum -- each variant gets a "type" discriminator
#[derive(Debug, Serialize, Deserialize)]
#[serde(tag = "type", content = "value")]
enum Event {
    #[serde(rename = "click")]
    Click { x: i32, y: i32 },
    #[serde(rename = "keypress")]
    KeyPress { key: String },
}

fn main() {
    let json = r#"{
        "userId": 42, "displayName": "Alice",
        "passwordHash": "abc", "email": "a@b.com", "isAdmin": true
    }"#;
    let user: User = serde_json::from_str(json).unwrap();
    println!("Role: {}", user.role); // "viewer" (defaulted)
    // passwordHash excluded from output
    println!("{}", serde_json::to_string_pretty(&user).unwrap());

    let ev = Event::Click { x: 10, y: 20 };
    println!("{}", serde_json::to_string(&ev).unwrap());
    // {"type":"click","value":{"x":10,"y":20}}
}
```

Key serde attributes:
- `rename_all = "camelCase"` -- field naming convention
- `skip_serializing_if` -- omit None/empty fields
- `default` -- use Default::default() or a custom function
- `flatten` -- inline nested struct fields
- `tag`/`content` -- control enum JSON shape'''
    },
    {
        "instruction": r'''How do I handle errors properly in Axum handlers and return structured JSON error responses?''',
        "output": r'''Implement `IntoResponse` on your error type to return structured JSON errors with proper HTTP status codes.

```rust
use axum::{
    extract::Path, http::StatusCode,
    response::{IntoResponse, Response},
    routing::get, Json, Router,
};
use serde::Serialize;

#[derive(Serialize)]
struct ErrorBody { error: String, code: u16 }

enum AppError {
    NotFound(String),
    BadRequest(String),
    Internal(String),
}

impl IntoResponse for AppError {
    fn into_response(self) -> Response {
        let (status, msg) = match self {
            AppError::NotFound(m) => (StatusCode::NOT_FOUND, m),
            AppError::BadRequest(m) => (StatusCode::BAD_REQUEST, m),
            AppError::Internal(m) => {
                eprintln!("Internal: {m}");
                (StatusCode::INTERNAL_SERVER_ERROR, "internal error".into())
            }
        };
        (status, Json(ErrorBody { error: msg, code: status.as_u16() })).into_response()
    }
}

// From impl lets you use ? with io::Error in handlers
impl From<std::io::Error> for AppError {
    fn from(e: std::io::Error) -> Self { AppError::Internal(e.to_string()) }
}

async fn get_item(Path(id): Path<u64>) -> Result<Json<serde_json::Value>, AppError> {
    if id == 0 {
        return Err(AppError::BadRequest("id must be > 0".into()));
    }
    // Simulate lookup
    if id > 100 {
        return Err(AppError::NotFound(format!("item {id} not found")));
    }
    Ok(Json(serde_json::json!({"id": id, "name": "widget"})))
}

#[tokio::main]
async fn main() {
    let app = Router::new().route("/items/{id}", get(get_item));
    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000").await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
```

This ensures every error returns `{"error": "...", "code": 404}` with the matching HTTP status. Add `From` impls for each external error type so `?` converts automatically.'''
    },
    {
        "instruction": r'''<thinking>
The user wants to see Axum custom extractors. I should show how to implement FromRequestParts or FromRequest to build reusable request parsing logic, such as extracting an authenticated user from a JWT header.
</thinking>

How do I create a custom extractor in Axum? Show extracting an authenticated user from a request header.''',
        "output": r'''Implement `FromRequestParts` (headers only) or `FromRequest` (needs body) for custom extractors. Here is a user-from-token extractor.

```rust
use axum::{
    async_trait, extract::FromRequestParts,
    http::{header, request::Parts, StatusCode},
    response::{IntoResponse, Response},
    routing::get, Json, Router,
};
use serde::Serialize;

#[derive(Debug, Clone, Serialize)]
struct AuthUser { user_id: u64, name: String, role: String }

enum AuthError { Missing, Invalid }

impl IntoResponse for AuthError {
    fn into_response(self) -> Response {
        let msg = match self {
            AuthError::Missing => "missing auth header",
            AuthError::Invalid => "invalid token",
        };
        (StatusCode::UNAUTHORIZED, Json(serde_json::json!({"error": msg}))).into_response()
    }
}

#[async_trait]
impl<S: Send + Sync> FromRequestParts<S> for AuthUser {
    type Rejection = AuthError;
    async fn from_request_parts(parts: &mut Parts, _s: &S) -> Result<Self, Self::Rejection> {
        let hdr = parts.headers.get(header::AUTHORIZATION)
            .and_then(|v| v.to_str().ok())
            .ok_or(AuthError::Missing)?;
        let token = hdr.strip_prefix("Bearer ").ok_or(AuthError::Invalid)?;
        decode(token).ok_or(AuthError::Invalid)
    }
}

fn decode(token: &str) -> Option<AuthUser> {
    let p: Vec<&str> = token.split(':').collect();
    if p.len() == 3 {
        Some(AuthUser { user_id: p[0].parse().ok()?, name: p[1].into(), role: p[2].into() })
    } else { None }
}

async fn profile(user: AuthUser) -> Json<AuthUser> { Json(user) }

async fn admin(user: AuthUser) -> Result<String, StatusCode> {
    if user.role != "admin" { return Err(StatusCode::FORBIDDEN); }
    Ok(format!("Admin {} acted", user.name))
}

#[tokio::main]
async fn main() {
    let app = Router::new()
        .route("/profile", get(profile))
        .route("/admin", get(admin));
    let listener = tokio::net::TcpListener::bind("0.0.0.0:3000").await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
// curl -H "Authorization: Bearer 42:alice:admin" localhost:3000/profile
```

Key points:
- `FromRequestParts` -- headers, cookies, path (no body consumed)
- `FromRequest` -- custom body parsing (consumes body)
- `Rejection` must implement `IntoResponse`
- Extractors compose: `(AuthUser, Json<T>)` extracts auth then body'''
    },
]
