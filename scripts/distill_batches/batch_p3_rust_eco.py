"""P3 Batch: Rust ecosystem deep-dives — Serde, SQLx, proc macros, embedded no_std, error handling."""

PAIRS = [
    (
        "Serde serialization and deserialization in Rust",
        "Explain advanced Serde patterns in Rust including custom serializers and deserializers, the #[serde(with)] attribute, zero-copy deserialization with borrowed data, handling multiple wire formats like JSON MessagePack and CBOR, and performance tuning with serde_json::RawValue. Show production-grade code with thorough error handling.",
        """## Advanced Serde: Beyond Derive in Production Rust

### Why Serde's Architecture Matters

Serde is not just a serialization library -- it is a **data model abstraction layer** that decouples your Rust types from wire formats. The key insight is that Serde defines an intermediate data model (29 types: bool, i8..i128, u8..u128, f32, f64, char, str, bytes, option, unit, seq, map, etc.), and both serializers and deserializers speak this intermediate language. This means you write your type mapping **once**, and it works with JSON, MessagePack, CBOR, TOML, Bincode, and any future format automatically.

However, the derive macro only handles straightforward cases. In production, you inevitably encounter fields that need custom logic: timestamps that must be integers on the wire but `DateTime` in memory, enums with legacy string representations, or nested structures where you want to delay parsing for performance. This is where custom serializers, `#[serde(with)]`, and `RawValue` become essential.

### Custom Serializers and Deserializers

The most common mistake is implementing `Serialize`/`Deserialize` on the type itself when you only need a custom representation for one field. The `#[serde(with)]` attribute lets you isolate the custom logic.

```rust
use serde::{Deserialize, Deserializer, Serialize, Serializer};
use chrono::{DateTime, Utc};

/// Module for serializing DateTime<Utc> as Unix timestamp milliseconds.
/// This is a best practice because it keeps the custom logic contained
/// and reusable across multiple structs.
mod timestamp_millis {
    use super::*;

    pub fn serialize<S>(dt: &DateTime<Utc>, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        serializer.serialize_i64(dt.timestamp_millis())
    }

    pub fn deserialize<'de, D>(deserializer: D) -> Result<DateTime<Utc>, D::Error>
    where
        D: Deserializer<'de>,
    {
        let millis = i64::deserialize(deserializer)?;
        DateTime::from_timestamp_millis(millis)
            .ok_or_else(|| serde::de::Error::custom(
                format!("invalid timestamp: {} is out of range", millis)
            ))
    }
}

/// Module for optional DateTime fields -- a common pitfall is forgetting
/// that Option<T> with #[serde(with)] requires a separate module.
mod option_timestamp_millis {
    use super::*;

    pub fn serialize<S>(opt: &Option<DateTime<Utc>>, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        match opt {
            Some(dt) => serializer.serialize_some(&dt.timestamp_millis()),
            None => serializer.serialize_none(),
        }
    }

    pub fn deserialize<'de, D>(deserializer: D) -> Result<Option<DateTime<Utc>>, D::Error>
    where
        D: Deserializer<'de>,
    {
        let opt = Option::<i64>::deserialize(deserializer)?;
        match opt {
            Some(millis) => DateTime::from_timestamp_millis(millis)
                .map(Some)
                .ok_or_else(|| serde::de::Error::custom("invalid timestamp")),
            None => Ok(None),
        }
    }
}

/// Event from an external API that uses Unix timestamps on the wire.
#[derive(Debug, Serialize, Deserialize)]
pub struct Event {
    pub id: String,
    pub name: String,

    #[serde(with = "timestamp_millis")]
    pub created_at: DateTime<Utc>,

    #[serde(with = "option_timestamp_millis")]
    pub deleted_at: Option<DateTime<Utc>>,

    /// Flatten merges the fields of metadata directly into the parent JSON object.
    /// This avoids a nested "metadata" key on the wire.
    #[serde(flatten)]
    pub metadata: EventMetadata,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct EventMetadata {
    #[serde(default)]
    pub tags: Vec<String>,
    #[serde(default)]
    pub priority: u8,
}
```

The reason we use a module pattern (not a standalone function) is that `#[serde(with = "path")]` expects a module with `serialize` and `deserialize` functions. This is cleaner than implementing the entire `Serialize` trait on a newtype wrapper.

### Zero-Copy Deserialization

Zero-copy deserialization is a **critical performance optimization** for services that parse large JSON payloads. Instead of allocating new `String`s for every field, Serde can borrow `&str` slices directly from the input buffer. The trade-off is that the deserialized struct now has a lifetime tied to the input.

```rust
use serde::Deserialize;

/// Zero-copy log entry -- borrows strings from the input buffer.
/// This avoids thousands of small allocations when parsing log batches.
/// The lifetime 'a ties this struct to the input byte slice.
#[derive(Debug, Deserialize)]
pub struct LogEntry<'a> {
    /// &'a str instead of String: zero-copy, no allocation
    #[serde(borrow)]
    pub level: &'a str,

    #[serde(borrow)]
    pub message: &'a str,

    #[serde(borrow)]
    pub source: &'a str,

    /// For fields that might contain escape sequences, Serde uses
    /// Cow<'a, str> -- borrowed when possible, owned when escapes
    /// force a new allocation. This is the best practice for mixed content.
    #[serde(borrow)]
    pub context: std::borrow::Cow<'a, str>,

    /// Numeric fields are always copied (they are stack values, not heap).
    pub timestamp: u64,
}

/// Batch of log entries -- the entire batch borrows from one input buffer.
#[derive(Debug, Deserialize)]
pub struct LogBatch<'a> {
    #[serde(borrow)]
    pub entries: Vec<LogEntry<'a>>,
    pub batch_id: u64,
}

/// Parse a log batch with zero-copy deserialization.
/// The input must outlive the returned LogBatch because we borrow from it.
pub fn parse_log_batch(input: &[u8]) -> Result<LogBatch<'_>, serde_json::Error> {
    serde_json::from_slice(input)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_zero_copy_parse() {
        let json = br#"{
            "entries": [
                {"level": "error", "message": "disk full", "source": "storage", "context": "node-3", "timestamp": 1700000000},
                {"level": "warn", "message": "high latency", "source": "network", "context": "path with \"escape\"", "timestamp": 1700000001}
            ],
            "batch_id": 42
        }"#;

        let batch = parse_log_batch(json).expect("should parse");
        assert_eq!(batch.entries.len(), 2);
        // "level" field is borrowed directly from the json buffer -- no allocation
        assert_eq!(batch.entries[0].level, "error");
        // "context" with escapes becomes Cow::Owned
        assert!(matches!(batch.entries[1].context, std::borrow::Cow::Owned(_)));
    }
}
```

A common mistake is using `#[serde(borrow)]` on `Vec<String>` and expecting it to become `Vec<&str>`. You must change the type signature explicitly. Serde's `borrow` attribute only tells the derive macro to add the lifetime bound to the `Deserialize` impl -- it does not change the field type.

### Multi-Format Support with RawValue

In production, you often need to support multiple formats or delay parsing of certain fields for performance. `serde_json::RawValue` lets you defer parsing: it stores the raw JSON bytes without interpreting them. This is essential for **API gateways**, **message routers**, and **schema-evolution systems** where you forward parts of the payload without understanding them.

```rust
use serde::{Deserialize, Serialize};
use serde_json::value::RawValue;

/// Envelope that can carry any payload without parsing it.
/// This is the pattern used by event buses and API gateways because
/// the router only needs to inspect the header, not the body.
#[derive(Debug, Serialize, Deserialize)]
pub struct Envelope<'a> {
    pub event_type: String,
    pub version: u32,

    /// RawValue defers parsing -- the JSON bytes are stored as-is.
    /// This avoids the cost of deserializing a large nested payload
    /// when you only need to route based on event_type.
    #[serde(borrow)]
    pub payload: &'a RawValue,
}

/// Multi-format codec that can serialize/deserialize using different wire formats.
pub struct MultiCodec;

impl MultiCodec {
    /// Detect format from content-type header and deserialize accordingly.
    /// This pattern is common in microservices that must support both
    /// JSON (human-readable debugging) and MessagePack (production throughput).
    pub fn deserialize<'de, T: Deserialize<'de>>(
        content_type: &str,
        data: &'de [u8],
    ) -> Result<T, CodecError> {
        match content_type {
            "application/json" => {
                serde_json::from_slice(data).map_err(CodecError::Json)
            }
            "application/msgpack" | "application/x-msgpack" => {
                rmp_serde::from_slice(data).map_err(CodecError::MsgPack)
            }
            "application/cbor" => {
                ciborium::from_reader(data).map_err(|e| CodecError::Cbor(e.to_string()))
            }
            _ => Err(CodecError::UnsupportedFormat(content_type.to_string())),
        }
    }

    pub fn serialize<T: Serialize>(
        content_type: &str,
        value: &T,
    ) -> Result<Vec<u8>, CodecError> {
        match content_type {
            "application/json" => {
                serde_json::to_vec(value).map_err(CodecError::Json)
            }
            "application/msgpack" | "application/x-msgpack" => {
                rmp_serde::to_vec(value).map_err(CodecError::MsgPack)
            }
            "application/cbor" => {
                let mut buf = Vec::new();
                ciborium::into_writer(value, &mut buf)
                    .map_err(|e| CodecError::Cbor(e.to_string()))?;
                Ok(buf)
            }
            _ => Err(CodecError::UnsupportedFormat(content_type.to_string())),
        }
    }
}

/// Error type for codec operations.
#[derive(Debug, thiserror::Error)]
pub enum CodecError {
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),

    #[error("MessagePack error: {0}")]
    MsgPack(#[from] rmp_serde::decode::Error),

    #[error("CBOR error: {0}")]
    Cbor(String),

    #[error("unsupported format: {0}")]
    UnsupportedFormat(String),
}

#[cfg(test)]
mod format_tests {
    use super::*;

    #[derive(Debug, PartialEq, Serialize, Deserialize)]
    struct TestPayload {
        name: String,
        count: u64,
    }

    #[test]
    fn test_json_roundtrip() {
        let original = TestPayload { name: "test".into(), count: 42 };
        let bytes = MultiCodec::serialize("application/json", &original).unwrap();
        let decoded: TestPayload = MultiCodec::deserialize("application/json", &bytes).unwrap();
        assert_eq!(original, decoded);
    }

    #[test]
    fn test_msgpack_roundtrip() {
        let original = TestPayload { name: "test".into(), count: 42 };
        let bytes = MultiCodec::serialize("application/msgpack", &original).unwrap();
        // MessagePack is typically 30-50% smaller than JSON
        let json_bytes = MultiCodec::serialize("application/json", &original).unwrap();
        assert!(bytes.len() < json_bytes.len(), "msgpack should be smaller");
        let decoded: TestPayload = MultiCodec::deserialize("application/msgpack", &bytes).unwrap();
        assert_eq!(original, decoded);
    }

    #[test]
    fn test_raw_value_routing() {
        let json = r#"{"event_type":"user.created","version":1,"payload":{"user_id":123,"email":"a@b.com"}}"#;
        let envelope: Envelope = serde_json::from_str(json).unwrap();
        assert_eq!(envelope.event_type, "user.created");
        // payload was NOT parsed -- it is still raw JSON bytes
        assert!(envelope.payload.get().contains("user_id"));
    }
}
```

### Performance Tuning Summary

- **Use `#[serde(skip)]`** on fields computed at runtime to avoid serialization overhead
- **Use `RawValue`** to defer parsing of large nested payloads -- this reduces latency for routers by 40-60% in benchmarks
- **Use zero-copy** (`&str`, `Cow<str>`) for high-throughput log ingestion pipelines
- **Use `#[serde(rename_all = "camelCase")]`** at the struct level instead of per-field `#[serde(rename)]` to reduce annotation noise
- **Avoid `#[serde(flatten)]` in hot paths** because it forces Serde to use a map-based intermediate representation, which is slower than positional access
- **Prefer MessagePack or CBOR** for internal service-to-service communication where human readability is not needed -- throughput improvements of 2-4x over JSON are typical

### Key Takeaways

The best practice for production Serde usage is to start with derive macros, add `#[serde(with)]` modules for fields that need custom representation, use `RawValue` for deferred parsing in routing layers, and switch to binary formats for internal traffic. The common pitfall is over-customizing: if you find yourself implementing `Serialize` from scratch, you have probably missed a serde attribute that does what you need. Check the [serde attributes reference](https://serde.rs/attributes.html) before writing custom impls.""",
    ),
    (
        "SQLx compile-time checked database queries in Rust",
        "Demonstrate how to use SQLx in Rust with compile-time checked SQL queries, connection pooling, migrations, transactions with proper error handling, custom type mappings for domain types, batch operations, and testing strategies with isolated test databases. Explain the trade-offs versus ORMs like Diesel.",
        """## SQLx: Compile-Time SQL Verification in Rust

### Why SQLx Over Diesel or SeaORM

SQLx occupies a unique position in the Rust database ecosystem: it verifies your SQL queries **at compile time** against a real database, but does not generate SQL for you. This is a deliberate trade-off. Diesel generates type-safe query builders (like an ORM), which means you must learn Diesel's DSL. SeaORM adds an ActiveRecord-like layer. SQLx says: "write raw SQL, and we will verify it compiles against your schema."

The consequence is that SQLx is better for teams with strong SQL skills, complex queries (CTEs, window functions, recursive queries), and polyglot environments where the same SQL runs in migrations and application code. Diesel is better when you want the compiler to prevent SQL injection at the type level and you prefer a Rust-native query syntax.

However, the common mistake with SQLx is not understanding that **compile-time checking requires a running database at build time**. This has implications for CI/CD pipelines, Docker builds, and offline development. SQLx solves this with `sqlx prepare`, which caches query metadata in a `.sqlx/` directory that you commit to version control.

### Project Setup and Connection Pooling

```rust
// src/db.rs
use sqlx::postgres::{PgPool, PgPoolOptions};
use std::time::Duration;

/// Create a connection pool with production-tuned settings.
/// The pool size matters because each connection holds a PostgreSQL backend
/// process. Too many connections starve the OS of file descriptors;
/// too few cause request queuing under load.
pub async fn create_pool(database_url: &str) -> Result<PgPool, sqlx::Error> {
    PgPoolOptions::new()
        // Best practice: max_connections = (2 * CPU cores) + disk spindles
        // For cloud databases (RDS, Cloud SQL), start with 10-20.
        .max_connections(20)
        // Minimum idle connections prevent cold-start latency on the first
        // request after a quiet period.
        .min_connections(5)
        // Acquire timeout prevents requests from hanging indefinitely
        // when the pool is exhausted. Fail fast and return 503.
        .acquire_timeout(Duration::from_secs(3))
        // Idle timeout reclaims connections that have been unused.
        // PostgreSQL has a default idle timeout of 0 (infinite), but
        // load balancers (AWS ALB) may drop idle connections after 60s.
        .idle_timeout(Duration::from_secs(600))
        // Max lifetime prevents using connections that PostgreSQL has
        // silently closed (e.g., after a failover).
        .max_lifetime(Duration::from_secs(1800))
        .connect(database_url)
        .await
}
```

### Migrations

SQLx migrations are plain SQL files, which means your DBA can review them without knowing Rust. This is a significant advantage over Diesel's migration system, which uses Rust code.

```sql
-- migrations/20240101000000_create_users.sql
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email       TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,
    role        TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin', 'member', 'viewer')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_users_email ON users (email);
CREATE INDEX idx_users_role ON users (role);

-- Trigger for auto-updating updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at();
```

### Domain Types with Custom Mappings

```rust
// src/models.rs
use serde::{Deserialize, Serialize};
use sqlx::Type;
use uuid::Uuid;
use chrono::{DateTime, Utc};

/// Custom enum that maps to a TEXT column with CHECK constraint.
/// SQLx's Type derive generates the necessary encode/decode impls.
/// The rename_all = "lowercase" ensures Rust's PascalCase variants
/// map to the lowercase strings stored in PostgreSQL.
#[derive(Debug, Clone, Serialize, Deserialize, Type, PartialEq)]
#[sqlx(type_name = "TEXT", rename_all = "lowercase")]
pub enum UserRole {
    Admin,
    Member,
    Viewer,
}

/// Domain model with compile-time verified field mappings.
/// sqlx::FromRow generates the row-to-struct conversion code.
#[derive(Debug, Clone, Serialize, Deserialize, sqlx::FromRow)]
pub struct User {
    pub id: Uuid,
    pub email: String,
    pub name: String,
    pub role: UserRole,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
}

/// Input type for creating users -- separate from the domain model
/// because id, created_at, updated_at are generated by the database.
#[derive(Debug, Deserialize)]
pub struct CreateUser {
    pub email: String,
    pub name: String,
    #[serde(default)]
    pub role: Option<UserRole>,
}

/// Input for updates -- all fields optional to support PATCH semantics.
#[derive(Debug, Deserialize)]
pub struct UpdateUser {
    pub email: Option<String>,
    pub name: Option<String>,
    pub role: Option<UserRole>,
}
```

### Repository Pattern with Transactions

```rust
// src/repository.rs
use crate::models::{CreateUser, UpdateUser, User, UserRole};
use sqlx::PgPool;
use uuid::Uuid;

/// Repository encapsulates all database operations.
/// This is not an ORM -- each method contains hand-written SQL that
/// is verified at compile time by the sqlx::query! macro.
pub struct UserRepository {
    pool: PgPool,
}

impl UserRepository {
    pub fn new(pool: PgPool) -> Self {
        Self { pool }
    }

    /// Find a user by ID. Returns None if not found.
    /// The query! macro checks at compile time that:
    /// 1. The SQL syntax is valid
    /// 2. The "users" table exists with an "id" column of type UUID
    /// 3. The returned columns match the struct fields
    pub async fn find_by_id(&self, id: Uuid) -> Result<Option<User>, sqlx::Error> {
        sqlx::query_as!(
            User,
            r#"SELECT id, email, name, role as "role: UserRole", created_at, updated_at
               FROM users WHERE id = $1"#,
            id
        )
        .fetch_optional(&self.pool)
        .await
    }

    /// List users with optional role filter and pagination.
    /// The query uses COALESCE to handle optional filters in SQL
    /// rather than building dynamic queries in Rust, which would
    /// bypass compile-time checking.
    pub async fn list(
        &self,
        role_filter: Option<UserRole>,
        limit: i64,
        offset: i64,
    ) -> Result<Vec<User>, sqlx::Error> {
        sqlx::query_as!(
            User,
            r#"SELECT id, email, name, role as "role: UserRole", created_at, updated_at
               FROM users
               WHERE ($1::TEXT IS NULL OR role = $1)
               ORDER BY created_at DESC
               LIMIT $2 OFFSET $3"#,
            role_filter as Option<UserRole>,
            limit,
            offset
        )
        .fetch_all(&self.pool)
        .await
    }

    /// Create a user inside a transaction.
    /// Transactions are essential for operations that touch multiple tables
    /// or require rollback on partial failure.
    pub async fn create(&self, input: CreateUser) -> Result<User, sqlx::Error> {
        let mut tx = self.pool.begin().await?;

        let user = sqlx::query_as!(
            User,
            r#"INSERT INTO users (email, name, role)
               VALUES ($1, $2, $3)
               RETURNING id, email, name, role as "role: UserRole", created_at, updated_at"#,
            input.email,
            input.name,
            input.role.unwrap_or(UserRole::Member) as UserRole
        )
        .fetch_one(&mut *tx)
        .await?;

        // You could insert into an audit_log table here, still inside
        // the same transaction. If the audit insert fails, the user
        // creation is rolled back automatically.
        sqlx::query!(
            "INSERT INTO audit_log (entity_type, entity_id, action) VALUES ('user', $1, 'created')",
            user.id
        )
        .execute(&mut *tx)
        .await?;

        tx.commit().await?;
        Ok(user)
    }

    /// Batch insert using UNNEST -- far more efficient than individual INSERTs.
    /// For 1000 rows, this is typically 10-50x faster than looping because
    /// it reduces network round-trips to a single query.
    pub async fn batch_create(&self, users: Vec<CreateUser>) -> Result<Vec<User>, sqlx::Error> {
        let emails: Vec<String> = users.iter().map(|u| u.email.clone()).collect();
        let names: Vec<String> = users.iter().map(|u| u.name.clone()).collect();
        let roles: Vec<UserRole> = users
            .iter()
            .map(|u| u.role.clone().unwrap_or(UserRole::Member))
            .collect();

        sqlx::query_as!(
            User,
            r#"INSERT INTO users (email, name, role)
               SELECT * FROM UNNEST($1::TEXT[], $2::TEXT[], $3::TEXT[])
               RETURNING id, email, name, role as "role: UserRole", created_at, updated_at"#,
            &emails,
            &names,
            &roles as &[UserRole]
        )
        .fetch_all(&self.pool)
        .await
    }
}
```

### Testing with Isolated Databases

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use sqlx::PgPool;

    /// Each test gets its own database by using sqlx::test with migrations.
    /// SQLx creates a temporary database, runs all migrations, gives you
    /// a pool, and drops the database after the test. This avoids test
    /// pollution -- the most common pitfall in database testing.
    #[sqlx::test(migrations = "./migrations")]
    async fn test_create_and_find_user(pool: PgPool) {
        let repo = UserRepository::new(pool);

        let input = CreateUser {
            email: "test@example.com".into(),
            name: "Test User".into(),
            role: Some(UserRole::Admin),
        };

        let created = repo.create(input).await.expect("should create user");
        assert_eq!(created.email, "test@example.com");
        assert_eq!(created.role, UserRole::Admin);

        let found = repo.find_by_id(created.id).await.expect("should query");
        assert!(found.is_some());
        assert_eq!(found.unwrap().name, "Test User");
    }

    #[sqlx::test(migrations = "./migrations")]
    async fn test_batch_create(pool: PgPool) {
        let repo = UserRepository::new(pool);

        let users = vec![
            CreateUser { email: "a@test.com".into(), name: "A".into(), role: None },
            CreateUser { email: "b@test.com".into(), name: "B".into(), role: Some(UserRole::Viewer) },
        ];

        let created = repo.batch_create(users).await.expect("batch insert");
        assert_eq!(created.len(), 2);
        assert_eq!(created[0].role, UserRole::Member); // default role
        assert_eq!(created[1].role, UserRole::Viewer);
    }

    #[sqlx::test(migrations = "./migrations")]
    async fn test_duplicate_email_fails(pool: PgPool) {
        let repo = UserRepository::new(pool);

        let input = CreateUser {
            email: "dup@test.com".into(),
            name: "First".into(),
            role: None,
        };
        repo.create(input).await.expect("first insert should work");

        let duplicate = CreateUser {
            email: "dup@test.com".into(),
            name: "Second".into(),
            role: None,
        };
        let result = repo.create(duplicate).await;
        assert!(result.is_err(), "duplicate email should fail");
    }
}
```

### Key Takeaways

- **Compile-time checking** catches column name typos, type mismatches, and missing tables before your code ships -- but requires a database at build time or cached metadata via `sqlx prepare`
- **Connection pooling** must be tuned for your workload: too many connections waste memory, too few cause bottleneck queuing
- **Transactions** should wrap multi-table operations; use `begin()` / `commit()` with `?` propagation so failures auto-rollback
- **Batch operations** with UNNEST are 10-50x faster than individual inserts because they minimize network round-trips
- **Test isolation** with `#[sqlx::test]` prevents the most common database testing pitfall: shared mutable state between tests
- Avoid the pitfall of mixing compile-time checked `query!` with runtime `query()` -- use `query!` everywhere possible, and only fall back to `query()` for truly dynamic SQL (e.g., user-defined report builders)""",
    ),
    (
        "Rust procedural macros for code generation",
        "Build a complete Rust procedural macro from scratch showing derive macros attribute macros and function-like macros. Implement a production-quality Builder derive macro that generates a builder pattern for any struct. Explain the syn and quote crates, token stream manipulation, error reporting, and testing strategies for proc macros.",
        """## Rust Procedural Macros: From Token Streams to Production Code Generation

### Why Procedural Macros Exist

Rust's type system is powerful but verbose. When you find yourself writing the same boilerplate for every struct -- builders, validation, serialization, database mappings -- procedural macros let you generate that code at compile time. The key insight is that proc macros operate on **token streams**, not on AST nodes or text. They receive Rust tokens as input and produce Rust tokens as output, which the compiler then type-checks normally.

There are three kinds of procedural macros, and understanding when to use each is essential:

- **Derive macros** (`#[derive(MyTrait)]`): Generate trait implementations for a struct/enum. Best practice for adding capabilities without modifying the original type.
- **Attribute macros** (`#[my_attr]`): Transform the annotated item. Use when you need to modify the item itself (e.g., adding fields, wrapping functions).
- **Function-like macros** (`my_macro!(...)`) : Accept arbitrary tokens. Use for DSLs or when the input is not a valid Rust item.

The common mistake is reaching for proc macros when declarative macros (`macro_rules!`) suffice. Proc macros add a separate crate, increase compile times, and are harder to debug. Use them only when you need to inspect struct fields, parse attributes, or generate complex code that `macro_rules!` pattern matching cannot handle.

### Project Structure

Proc macros must live in a separate crate with `proc-macro = true` in `Cargo.toml`. This is a compiler requirement, not a convention.

```toml
# derive_builder_macro/Cargo.toml
[package]
name = "derive_builder_macro"
version = "0.1.0"
edition = "2021"

[lib]
proc-macro = true

[dependencies]
syn = { version = "2", features = ["full", "extra-traits"] }
quote = "1"
proc-macro2 = "1"
```

### The Builder Derive Macro

This macro generates a type-safe builder for any struct. For a struct `Config` with fields `host: String` and `port: u16`, it generates a `ConfigBuilder` with setter methods and a `build()` method that validates all required fields are set.

```rust
// derive_builder_macro/src/lib.rs
use proc_macro::TokenStream;
use quote::{quote, format_ident};
use syn::{parse_macro_input, DeriveInput, Data, Fields, Field, Attribute, Lit, Meta};

/// Derive macro that generates a builder pattern for any named struct.
///
/// # Example
/// ```rust
/// #[derive(Builder)]
/// struct Config {
///     host: String,
///     port: u16,
///     #[builder(default = "30")]
///     timeout_secs: u64,
///     #[builder(optional)]
///     description: Option<String>,
/// }
/// ```
#[proc_macro_derive(Builder, attributes(builder))]
pub fn derive_builder(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as DeriveInput);

    match generate_builder(&input) {
        Ok(tokens) => tokens.into(),
        Err(err) => err.to_compile_error().into(),
    }
}

/// Parsed metadata for a single field, extracted from #[builder(...)] attributes.
struct FieldMeta {
    field: Field,
    is_optional: bool,
    default_value: Option<String>,
}

/// Parse #[builder(...)] attributes on a field.
/// Returns structured metadata that the code generator uses.
fn parse_field_meta(field: &Field) -> Result<FieldMeta, syn::Error> {
    let mut is_optional = false;
    let mut default_value = None;

    for attr in &field.attrs {
        if !attr.path().is_ident("builder") {
            continue;
        }

        attr.parse_nested_meta(|meta| {
            if meta.path.is_ident("optional") {
                is_optional = true;
                Ok(())
            } else if meta.path.is_ident("default") {
                let value = meta.value()?;
                let lit: Lit = value.parse()?;
                if let Lit::Str(s) = lit {
                    default_value = Some(s.value());
                } else {
                    return Err(meta.error("expected string literal for default value"));
                }
                Ok(())
            } else {
                Err(meta.error("unknown builder attribute; expected `optional` or `default`"))
            }
        })?;
    }

    Ok(FieldMeta {
        field: field.clone(),
        is_optional,
        default_value,
    })
}

/// Core code generation logic. Separated from the proc_macro entry point
/// for testability -- this function works with proc_macro2 types.
fn generate_builder(input: &DeriveInput) -> Result<proc_macro2::TokenStream, syn::Error> {
    let name = &input.ident;
    let builder_name = format_ident!("{}Builder", name);
    let vis = &input.vis;

    // Extract named fields -- we do not support tuple or unit structs.
    let fields = match &input.data {
        Data::Struct(data) => match &data.fields {
            Fields::Named(fields) => &fields.named,
            _ => return Err(syn::Error::new_spanned(
                name,
                "Builder derive only supports structs with named fields"
            )),
        },
        _ => return Err(syn::Error::new_spanned(
            name,
            "Builder derive only supports structs, not enums or unions"
        )),
    };

    let field_metas: Vec<FieldMeta> = fields
        .iter()
        .map(parse_field_meta)
        .collect::<Result<Vec<_>, _>>()?;

    // Generate builder struct fields -- all wrapped in Option<T> so we can
    // track which fields have been set.
    let builder_fields = field_metas.iter().map(|fm| {
        let name = &fm.field.ident;
        let ty = &fm.field.ty;
        quote! { #name: ::core::option::Option<#ty> }
    });

    // Generate setter methods. Each setter takes self by value and returns self,
    // enabling method chaining: Config::builder().host("localhost").port(8080).build()
    let setter_methods = field_metas.iter().map(|fm| {
        let name = &fm.field.ident;
        let ty = &fm.field.ty;
        quote! {
            /// Set the `#name` field.
            pub fn #name(mut self, value: #ty) -> Self {
                self.#name = ::core::option::Option::Some(value);
                self
            }
        }
    });

    // Generate the build() method body. Required fields produce an error
    // if not set; optional fields use None; fields with defaults use the default.
    let build_fields = field_metas.iter().map(|fm| {
        let name = &fm.field.ident;
        let field_name_str = name.as_ref().map(|n| n.to_string()).unwrap_or_default();

        if fm.is_optional {
            // Optional fields: use None if not set
            quote! { #name: self.#name }
        } else if let Some(ref default) = fm.default_value {
            // Fields with defaults: parse the default expression
            let default_expr: proc_macro2::TokenStream = default.parse().unwrap();
            quote! {
                #name: self.#name.unwrap_or_else(|| #default_expr)
            }
        } else {
            // Required fields: return error if missing
            quote! {
                #name: self.#name.ok_or_else(|| {
                    ::std::format!("missing required field: {}", #field_name_str)
                })?
            }
        }
    });

    let expanded = quote! {
        /// Auto-generated builder for [`#name`].
        #[derive(Debug, Default)]
        #vis struct #builder_name {
            #(#builder_fields,)*
        }

        impl #name {
            /// Create a new builder for this type.
            pub fn builder() -> #builder_name {
                #builder_name::default()
            }
        }

        impl #builder_name {
            #(#setter_methods)*

            /// Consume the builder and construct the target type.
            /// Returns an error string if any required fields are missing.
            pub fn build(self) -> ::core::result::Result<#name, ::std::string::String> {
                ::core::result::Result::Ok(#name {
                    #(#build_fields,)*
                })
            }
        }
    };

    Ok(expanded)
}
```

### Attribute Macro Example

Attribute macros transform the item they are attached to. A common use case is adding tracing or validation to functions.

```rust
/// Attribute macro that wraps a function with timing instrumentation.
/// Usage: #[timed] fn my_function() { ... }
#[proc_macro_attribute]
pub fn timed(_attr: TokenStream, item: TokenStream) -> TokenStream {
    let input = parse_macro_input!(item as syn::ItemFn);
    let fn_name = &input.sig.ident;
    let fn_name_str = fn_name.to_string();
    let block = &input.block;
    let sig = &input.sig;
    let vis = &input.vis;
    let attrs = &input.attrs;

    let expanded = quote! {
        #(#attrs)*
        #vis #sig {
            let __start = ::std::time::Instant::now();
            let __result = (|| #block)();
            let __elapsed = __start.elapsed();
            ::tracing::info!(
                function = #fn_name_str,
                duration_ms = __elapsed.as_millis() as u64,
                "function completed"
            );
            __result
        }
    };

    expanded.into()
}
```

### Testing Procedural Macros

Testing proc macros is tricky because they run at compile time. There are three strategies, each with different trade-offs.

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use syn::parse_quote;

    /// Strategy 1: Unit test the generation function with synthetic input.
    /// This tests the logic without compiling the output.
    #[test]
    fn test_builder_generates_struct() {
        let input: DeriveInput = parse_quote! {
            struct Config {
                host: String,
                port: u16,
            }
        };

        let output = generate_builder(&input).expect("should generate");
        let output_str = output.to_string();

        // Verify the builder struct is generated
        assert!(output_str.contains("ConfigBuilder"));
        // Verify setter methods exist
        assert!(output_str.contains("fn host"));
        assert!(output_str.contains("fn port"));
        // Verify build method exists
        assert!(output_str.contains("fn build"));
    }

    /// Strategy 2: Use trybuild for compile-pass/compile-fail tests.
    /// This is the best practice for verifying error messages.
    #[test]
    fn test_compile_errors() {
        let t = trybuild::TestCases::new();
        t.pass("tests/pass/*.rs");
        t.compile_fail("tests/fail/*.rs");
    }
}

// tests/pass/basic_builder.rs -- should compile successfully
// use derive_builder_macro::Builder;
//
// #[derive(Builder)]
// struct Config {
//     host: String,
//     port: u16,
// }
//
// fn main() {
//     let config = Config::builder()
//         .host("localhost".into())
//         .port(8080)
//         .build()
//         .unwrap();
//     assert_eq!(config.port, 8080);
// }

// tests/fail/enum_not_supported.rs -- should fail with clear error message
// use derive_builder_macro::Builder;
//
// #[derive(Builder)]
// enum NotAStruct { A, B }
//
// fn main() {}
```

### Key Takeaways

- **Use `syn` for parsing** and `quote` for code generation -- never manipulate token streams as strings, because that bypasses Rust's lexer rules
- **Separate generation logic** from the `#[proc_macro_derive]` entry point so you can unit test with `parse_quote!`
- **Report errors with `syn::Error`** that point to the correct span, so users see errors on the right line, not on the derive attribute
- **Use `trybuild`** for integration tests that verify both success cases and error messages
- A common pitfall is generating code that references types without fully qualifying them (e.g., `Option` instead of `::core::option::Option`). Always use absolute paths in generated code to avoid name collisions with user-defined types
- Proc macros increase compile time proportionally to the complexity of parsing. Keep your `syn` feature flags minimal -- use `features = ["derive"]` instead of `features = ["full"]` when you only need derive input parsing""",
    ),
    (
        "no_std Rust for embedded ARM Cortex-M firmware",
        "Write a complete no_std Rust firmware example targeting ARM Cortex-M microcontrollers. Cover memory allocators, interrupt handlers with NVIC priorities, DMA transfers, HAL abstractions using embedded-hal traits, and testing embedded code without hardware. Explain the design decisions for resource-constrained environments.",
        """## no_std Rust for Embedded: Production Firmware on ARM Cortex-M

### Why Rust for Embedded Over C

Rust's ownership model eliminates three of the most dangerous classes of embedded bugs: use-after-free (common in interrupt handlers that share buffers), data races (when DMA and CPU access the same memory), and buffer overflows (the leading cause of CVEs in IoT firmware). The trade-off is that Rust's borrow checker requires explicit lifetime annotations for shared resources, which adds verbosity. However, in embedded contexts, this verbosity is a **feature**: it forces you to document and verify every resource-sharing decision at compile time.

The `no_std` attribute removes the standard library, which depends on an OS. In its place, you use `core` (language primitives), `alloc` (optional heap allocation), and hardware-specific crates. The embedded Rust ecosystem is built on the **embedded-hal** trait abstraction, which means your driver code is portable across STM32, nRF52, RP2040, and any other chip that implements the traits.

### Project Setup

```toml
# Cargo.toml
[package]
name = "cortex-m-firmware"
version = "0.1.0"
edition = "2021"

[dependencies]
cortex-m = { version = "0.7", features = ["critical-section-single-core"] }
cortex-m-rt = "0.7"
panic-halt = "0.2"
embedded-hal = "1.0"
stm32f4xx-hal = { version = "0.21", features = ["stm32f411"] }
heapless = "0.8"          # Fixed-capacity collections (no heap needed)
embedded-alloc = "0.6"    # Optional: global allocator for dynamic allocation
critical-section = "1.1"

[profile.release]
opt-level = "s"       # Optimize for size -- flash is limited (256KB-1MB typical)
lto = true            # Link-time optimization removes unused code
debug = true          # Keep debug info for probe-rs / defmt debugging
codegen-units = 1     # Single codegen unit enables better optimization
```

```toml
# .cargo/config.toml
[target.thumbv7em-none-eabihf]
runner = "probe-rs run --chip STM32F411CEUx"

[build]
target = "thumbv7em-none-eabihf"    # Cortex-M4F with hardware FPU
```

### Memory Layout and Allocator

Embedded systems have a fixed memory map. The linker script (provided by `cortex-m-rt`) places code in flash and data in SRAM. If you need dynamic allocation (for protocols like MQTT that need variable-length buffers), you must provide a global allocator.

```rust
// src/main.rs
#![no_std]
#![no_main]

use core::cell::RefCell;
use cortex_m::interrupt::Mutex;
use cortex_m_rt::{entry, exception};
use embedded_hal::digital::OutputPin;
use embedded_hal::delay::DelayNs;
use heapless::Vec as HeaplessVec;
use panic_halt as _;
use stm32f4xx_hal::{
    gpio::{Output, PushPull, Pin},
    pac::{self, TIM2, USART1, DMA2},
    prelude::*,
    serial::{Config as SerialConfig, Serial},
    timer::CounterUs,
    dma::{StreamsTuple, config::DmaConfig, Transfer, MemoryToPeripheral},
};

// Optional heap allocator -- only use when heapless collections are insufficient.
// The common mistake is defaulting to heap allocation out of habit.
// In embedded, prefer heapless::Vec, heapless::String, and stack allocation.
use embedded_alloc::LlffHeap as Heap;

#[global_allocator]
static HEAP: Heap = Heap::empty();

/// Initialize the heap allocator. Must be called before any heap allocation.
/// We place the heap at the end of SRAM, after the stack.
fn init_heap() {
    const HEAP_SIZE: usize = 4096; // 4KB heap -- keep this small
    static mut HEAP_MEM: [u8; HEAP_SIZE] = [0; HEAP_SIZE];
    unsafe { HEAP.init(HEAP_MEM.as_ptr() as usize, HEAP_SIZE) }
}
```

### Interrupt Handlers and Shared State

Sharing state between interrupts and the main loop is the most error-prone part of embedded programming. In C, you use `volatile` variables and hope for the best. In Rust, the type system enforces correct synchronization.

```rust
/// Shared state between the main loop and the TIM2 interrupt.
/// Mutex<RefCell<Option<T>>> is the standard pattern for single-core
/// Cortex-M because:
/// - Mutex (from cortex-m) disables interrupts during access (no data race)
/// - RefCell provides interior mutability (needed because statics are immutable)
/// - Option allows late initialization (peripherals are configured in main)
static TIMER: Mutex<RefCell<Option<CounterUs<TIM2>>>> = Mutex::new(RefCell::new(None));
static LED: Mutex<RefCell<Option<Pin<'A', 5, Output<PushPull>>>>> =
    Mutex::new(RefCell::new(None));

/// Event counter shared between ISR and main loop.
/// Uses heapless::Vec to avoid heap allocation for the event log.
static EVENT_LOG: Mutex<RefCell<HeaplessVec<u32, 64>>> =
    Mutex::new(RefCell::new(HeaplessVec::new()));

/// TIM2 interrupt handler. Toggles the LED and logs a timestamp.
/// The #[interrupt] attribute from cortex-m-rt sets up the vector table entry.
#[allow(non_snake_case)]
#[cortex_m_rt::interrupt]
fn TIM2() {
    // critical_section::with disables interrupts for the duration of the closure.
    // This is safe on single-core Cortex-M because there is no other core
    // that could preempt us while interrupts are disabled.
    cortex_m::interrupt::free(|cs| {
        if let Some(ref mut timer) = TIMER.borrow(cs).borrow_mut().as_mut() {
            // Clear the interrupt flag -- if you forget this, the ISR
            // fires continuously (a common embedded pitfall).
            timer.clear_interrupt(stm32f4xx_hal::timer::Event::Update);
        }

        if let Some(ref mut led) = LED.borrow(cs).borrow_mut().as_mut() {
            let _ = led.toggle();
        }

        // Log the tick count. HeaplessVec silently drops pushes when full,
        // which is acceptable for a circular log buffer.
        let mut log = EVENT_LOG.borrow(cs).borrow_mut();
        let tick = cortex_m::peripheral::DWT::cycle_count();
        let _ = log.push(tick);
    });
}
```

### HAL Abstraction for Portable Drivers

```rust
/// A temperature sensor driver written against embedded-hal traits.
/// Because it uses trait bounds instead of concrete types, this driver
/// works on any microcontroller that implements embedded-hal I2C.
pub struct Tmp102<I2C> {
    i2c: I2C,
    address: u8,
}

impl<I2C, E> Tmp102<I2C>
where
    I2C: embedded_hal::i2c::I2c<Error = E>,
    E: core::fmt::Debug,
{
    /// Create a new TMP102 driver instance.
    /// The address is 0x48 by default (ADD0 pin grounded).
    pub fn new(i2c: I2C, address: u8) -> Self {
        Self { i2c, address }
    }

    /// Read temperature in millidegrees Celsius.
    /// Returns i32 to handle negative temperatures without floating point,
    /// which is a best practice on Cortex-M0 (no FPU).
    pub fn read_temperature_mdeg(&mut self) -> Result<i32, E> {
        let mut buf = [0u8; 2];
        // Read 2 bytes from the temperature register (register 0x00)
        self.i2c.write_read(self.address, &[0x00], &mut buf)?;

        // TMP102 returns 12-bit temperature in the upper bits.
        // Bit manipulation is necessary because the sensor packs data
        // to minimize I2C transfer time (a throughput consideration).
        let raw = ((buf[0] as i16) << 4) | ((buf[1] as i16) >> 4);

        // Convert to millidegrees: each LSB = 0.0625 C = 62.5 mdeg
        // We use integer arithmetic to avoid pulling in the float library.
        Ok((raw as i32) * 625 / 10)
    }

    /// Set the alert threshold in millidegrees Celsius.
    pub fn set_alert_threshold(&mut self, mdeg: i32) -> Result<(), E> {
        // Convert back from millidegrees to raw 12-bit value
        let raw = ((mdeg * 10) / 625) as i16;
        let bytes = [
            0x03, // High limit register
            (raw >> 4) as u8,
            ((raw & 0x0F) << 4) as u8,
        ];
        self.i2c.write(self.address, &bytes)
    }
}
```

### Main Entry Point with DMA

```rust
/// Firmware entry point. The #[entry] attribute ensures this is called
/// after cortex-m-rt initializes .bss, .data, and the vector table.
#[entry]
fn main() -> ! {
    init_heap();

    // Take ownership of all peripherals. This can only be called once --
    // subsequent calls return None, preventing aliasing.
    let dp = pac::Peripherals::take().expect("peripherals already taken");
    let cp = cortex_m::Peripherals::take().expect("core peripherals already taken");

    // Configure clocks. The STM32F411 runs at up to 100MHz.
    // Running at max speed increases power consumption, so choose based
    // on your application's latency requirements vs battery life.
    let rcc = dp.RCC.constrain();
    let clocks = rcc.cfgr
        .use_hse(25.MHz())  // External 25MHz crystal
        .sysclk(100.MHz())
        .pclk1(50.MHz())
        .pclk2(100.MHz())
        .freeze();

    // Configure GPIO
    let gpioa = dp.GPIOA.split();
    let mut led = gpioa.pa5.into_push_pull_output();

    // Configure UART for debug output
    let tx_pin = gpioa.pa9.into_alternate();
    let rx_pin = gpioa.pa10.into_alternate();
    let serial = Serial::new(
        dp.USART1,
        (tx_pin, rx_pin),
        SerialConfig::default().baudrate(115_200.bps()),
        &clocks,
    ).unwrap();

    let (tx, _rx) = serial.split();

    // Configure timer interrupt at 1Hz for LED blink
    let mut timer = dp.TIM2.counter_us(&clocks);
    timer.start(1_000_000.micros()).unwrap(); // 1 second period
    timer.listen(stm32f4xx_hal::timer::Event::Update);

    // Move peripherals into shared statics
    cortex_m::interrupt::free(|cs| {
        TIMER.borrow(cs).replace(Some(timer));
        LED.borrow(cs).replace(Some(led));
    });

    // Enable the TIM2 interrupt in the NVIC.
    // Priority 1 (lower = higher priority on Cortex-M).
    unsafe {
        cortex_m::peripheral::NVIC::unmask(pac::Interrupt::TIM2);
    }

    // Create a delay provider for the main loop
    let mut delay = cp.SYST.delay(&clocks);

    // Main loop -- in embedded, main() never returns (-> !)
    loop {
        // Read event log
        cortex_m::interrupt::free(|cs| {
            let log = EVENT_LOG.borrow(cs).borrow();
            if log.len() > 0 {
                // Process logged events (e.g., send over UART)
            }
        });

        delay.delay_ms(100u32);
    }
}
```

### Testing Without Hardware

```rust
#[cfg(test)]
mod tests {
    use super::*;
    use embedded_hal_mock::eh1::i2c::{Mock as I2cMock, Transaction as I2cTransaction};

    /// Test the TMP102 driver using a mock I2C bus.
    /// embedded-hal-mock provides mock implementations of all embedded-hal traits,
    /// so you can test drivers on your development machine without hardware.
    #[test]
    fn test_tmp102_read_temperature() {
        // 25.0C = 25000 mdeg = raw value 400 (400 * 0.0625 = 25.0)
        // raw 400 = 0x190, packed as [0x19, 0x00]
        let expectations = [
            I2cTransaction::write_read(0x48, vec![0x00], vec![0x19, 0x00]),
        ];
        let i2c = I2cMock::new(&expectations);

        let mut sensor = Tmp102::new(i2c, 0x48);
        let temp = sensor.read_temperature_mdeg().unwrap();
        assert_eq!(temp, 25000); // 25.000 C

        sensor.i2c.done(); // Verify all expectations were met
    }

    #[test]
    fn test_tmp102_negative_temperature() {
        // -10.0C = raw value -160 = 0xFF60, packed as [0xF6, 0x00]
        let expectations = [
            I2cTransaction::write_read(0x48, vec![0x00], vec![0xF6, 0x00]),
        ];
        let i2c = I2cMock::new(&expectations);

        let mut sensor = Tmp102::new(i2c, 0x48);
        let temp = sensor.read_temperature_mdeg().unwrap();
        assert!(temp < 0, "negative temperature should be negative");
    }
}
```

### Key Takeaways

- **Use `heapless` collections** instead of `Vec`/`String` whenever possible -- heap fragmentation is the silent killer of long-running embedded systems
- **The `Mutex<RefCell<Option<T>>>` pattern** is the correct way to share peripherals between ISRs and the main loop on single-core Cortex-M. Although it looks verbose, each layer serves a purpose: `Mutex` prevents data races, `RefCell` allows mutation, `Option` allows late initialization
- **Always clear interrupt flags** in ISR handlers. Forgetting this causes the ISR to fire continuously, starving the main loop (a common pitfall that manifests as the system appearing to hang)
- **Write drivers against `embedded-hal` traits**, not concrete HAL types. This makes your driver portable across chip families and testable with mocks
- **Use `opt-level = "s"` and LTO** in release builds to minimize flash usage. On a 256KB flash MCU, the difference between `opt-level = 3` and `opt-level = "s"` can be 30-50KB
- Avoid floating-point arithmetic on Cortex-M0/M0+ (no FPU). Use fixed-point or millidegree/millivolt representations instead, because software float emulation is 10-100x slower and increases code size by 5-10KB""",
    ),
    (
        "Rust error handling patterns and strategies",
        "Compare and contrast Rust error handling approaches including thiserror vs anyhow, the .context() method for error enrichment, designing custom error types for library crates versus application crates, error conversion chains with From implementations, and structured error reporting for observability. Show production-grade patterns with code examples and explain the trade-offs.",
        """## Rust Error Handling: From Prototypes to Production

### The Two-World Model

Rust error handling follows a fundamental split that every Rust developer must understand: **library errors** and **application errors** serve different purposes and require different tools.

- **Library crates** expose structured error types so callers can match on specific variants and decide how to recover. The caller needs to know *what* went wrong (e.g., `NotFound` vs `PermissionDenied`).
- **Application crates** need error context -- *where* and *why* something went wrong -- for debugging and logging. The human operator needs a chain of causes: "failed to process order 12345 -> database query failed -> connection refused."

This distinction explains why `thiserror` and `anyhow` exist as separate crates, and why using the wrong one causes pain. Using `anyhow` in a library strips callers of their ability to match on error variants. Using `thiserror` in an application binary adds boilerplate for error types that nobody will ever match on.

### thiserror: Structured Errors for Libraries

`thiserror` is a derive macro that generates `Display`, `Error`, and `From` implementations for your error enum. The key design decision is choosing your error variants: each variant should represent a **recoverable condition** that callers might want to handle differently.

```rust
// src/lib.rs -- a hypothetical storage library
use std::path::PathBuf;
use thiserror::Error;

/// Error type for the storage library.
/// Each variant represents a distinct failure mode that callers
/// can pattern-match on to decide recovery strategy.
///
/// Design principle: only add variants for conditions that callers
/// will realistically branch on. Do not add a variant for every
/// possible OS error -- group them under IoError instead.
#[derive(Debug, Error)]
pub enum StorageError {
    /// The requested key does not exist in the store.
    /// Callers typically handle this by returning a 404 or creating a default.
    #[error("key not found: {key}")]
    NotFound { key: String },

    /// The store has exceeded its configured capacity.
    /// Callers might trigger eviction or reject the write.
    #[error("storage capacity exceeded: {used}/{capacity} bytes")]
    CapacityExceeded { used: u64, capacity: u64 },

    /// Data corruption detected (checksum mismatch).
    /// This is a serious error -- callers should trigger a repair or alert.
    #[error("data corruption in {path}: expected checksum {expected}, got {actual}")]
    Corruption {
        path: PathBuf,
        expected: String,
        actual: String,
    },

    /// A serialization or deserialization error.
    /// The #[from] attribute generates `impl From<serde_json::Error> for StorageError`.
    #[error("serialization error: {0}")]
    Serialization(#[from] serde_json::Error),

    /// An I/O error. The #[source] attribute marks this as the error source
    /// for the Error::source() chain, without generating a From impl.
    /// We include the path for context because raw io::Error does not
    /// include file path information (a common frustration).
    #[error("I/O error on {path}: {source}")]
    Io {
        path: PathBuf,
        source: std::io::Error,
    },

    /// Configuration error during store initialization.
    #[error("invalid configuration: {0}")]
    Config(String),
}

/// Convenience type alias -- a best practice that reduces verbosity
/// throughout the library without hiding the error type.
pub type Result<T> = std::result::Result<T, StorageError>;

/// Storage operations that return structured errors.
pub struct Store {
    base_path: PathBuf,
    capacity: u64,
    used: u64,
}

impl Store {
    pub fn new(base_path: PathBuf, capacity: u64) -> Result<Self> {
        if capacity == 0 {
            return Err(StorageError::Config(
                "capacity must be greater than zero".into(),
            ));
        }
        if !base_path.exists() {
            return Err(StorageError::Io {
                path: base_path.clone(),
                source: std::io::Error::new(
                    std::io::ErrorKind::NotFound,
                    "base path does not exist",
                ),
            });
        }
        Ok(Self { base_path, capacity, used: 0 })
    }

    /// Read a value by key. Returns NotFound if the key does not exist.
    pub fn get<T: serde::de::DeserializeOwned>(&self, key: &str) -> Result<T> {
        let path = self.base_path.join(key);

        let bytes = std::fs::read(&path).map_err(|e| {
            if e.kind() == std::io::ErrorKind::NotFound {
                StorageError::NotFound { key: key.to_string() }
            } else {
                StorageError::Io { path: path.clone(), source: e }
            }
        })?;

        // serde_json::Error is automatically converted via #[from]
        let value: T = serde_json::from_slice(&bytes)?;
        Ok(value)
    }

    /// Write a value. Returns CapacityExceeded if the store is full.
    pub fn put<T: serde::Serialize>(&mut self, key: &str, value: &T) -> Result<()> {
        let bytes = serde_json::to_vec(value)?;

        if self.used + bytes.len() as u64 > self.capacity {
            return Err(StorageError::CapacityExceeded {
                used: self.used,
                capacity: self.capacity,
            });
        }

        let path = self.base_path.join(key);
        std::fs::write(&path, &bytes).map_err(|source| StorageError::Io {
            path,
            source,
        })?;

        self.used += bytes.len() as u64;
        Ok(())
    }
}
```

### anyhow: Contextual Errors for Applications

`anyhow` is the counterpart for application code. It provides a single error type (`anyhow::Error`) that can hold any error and attach context. The `.context()` method is the killer feature: it adds a human-readable explanation of what was happening when the error occurred.

```rust
// src/main.rs -- application code that uses the storage library
use anyhow::{Context, Result, bail, ensure};
use std::path::PathBuf;
use tracing::{info, error};

/// Application-level function that orchestrates multiple operations.
/// Notice how .context() adds layers of explanation at each call site.
/// This produces error chains like:
///   "failed to process order 12345"
///   "  caused by: failed to read customer profile"
///   "  caused by: key not found: customer_42"
pub async fn process_order(
    store: &mut Store,
    order_id: &str,
    customer_id: &str,
) -> Result<()> {
    // .context() wraps the error with additional information.
    // Without context, a "key not found" error gives no clue about
    // which operation failed or which order triggered it.
    let customer: Customer = store
        .get(customer_id)
        .context(format!("failed to read customer profile for order {order_id}"))?;

    // ensure! is anyhow's assertion macro -- it returns an error instead of panicking.
    // This is a best practice for input validation in application code
    // because panics should be reserved for programming errors, not data errors.
    ensure!(
        customer.is_active,
        "cannot process order {order_id}: customer {customer_id} is inactive"
    );

    // bail! immediately returns an error -- useful for guard clauses.
    if customer.credit_limit == 0 {
        bail!("customer {customer_id} has zero credit limit");
    }

    let order = Order {
        id: order_id.to_string(),
        customer_id: customer_id.to_string(),
        status: "processing".into(),
    };

    store
        .put(order_id, &order)
        .context(format!("failed to save order {order_id}"))?;

    info!(order_id, customer_id, "order processed successfully");
    Ok(())
}

/// Load configuration from a TOML file with rich error context.
/// This demonstrates how .context() builds a diagnostic chain:
///   "failed to load application config"
///   "  caused by: failed to read /etc/myapp/config.toml"
///   "  caused by: No such file or directory (os error 2)"
pub fn load_config(path: &PathBuf) -> Result<AppConfig> {
    let contents = std::fs::read_to_string(path)
        .with_context(|| format!("failed to read {}", path.display()))?;

    let config: AppConfig = toml::from_str(&contents)
        .with_context(|| format!("failed to parse TOML in {}", path.display()))?;

    // Validate the configuration after parsing
    ensure!(
        config.max_connections > 0,
        "max_connections must be positive, got {}",
        config.max_connections
    );

    ensure!(
        config.listen_port > 1024,
        "listen_port must be > 1024 (got {}); use a reverse proxy for port 80/443",
        config.listen_port
    );

    Ok(config)
}
```

### Error Conversion Chains

When building middleware or service layers, you need to convert between error types. The `From` trait is the standard mechanism, but designing the conversion chain requires care.

```rust
use thiserror::Error;

/// API-layer error type that converts domain errors into HTTP responses.
/// This is the boundary between your domain logic and your HTTP framework.
#[derive(Debug, Error)]
pub enum ApiError {
    #[error("not found: {0}")]
    NotFound(String),

    #[error("bad request: {0}")]
    BadRequest(String),

    #[error("internal error")]
    Internal(#[source] anyhow::Error),
}

/// Convert storage errors into API errors.
/// This From impl defines the error boundary: storage-level details
/// (file paths, checksums) are logged but not exposed to API clients.
impl From<StorageError> for ApiError {
    fn from(err: StorageError) -> Self {
        match err {
            StorageError::NotFound { key } => ApiError::NotFound(key),
            StorageError::CapacityExceeded { .. } => {
                ApiError::BadRequest("storage capacity exceeded".into())
            }
            StorageError::Config(msg) => ApiError::BadRequest(msg),
            // For security, internal errors are logged but not exposed.
            // Leaking file paths or checksums in API responses is a
            // common security pitfall.
            other => {
                tracing::error!(error = ?other, "internal storage error");
                ApiError::Internal(anyhow::anyhow!(other))
            }
        }
    }
}

/// Implement IntoResponse for your web framework (e.g., Axum).
/// This closes the conversion chain: StorageError -> ApiError -> HTTP Response.
impl axum::response::IntoResponse for ApiError {
    fn into_response(self) -> axum::response::Response {
        let (status, message) = match &self {
            ApiError::NotFound(msg) => (axum::http::StatusCode::NOT_FOUND, msg.clone()),
            ApiError::BadRequest(msg) => (axum::http::StatusCode::BAD_REQUEST, msg.clone()),
            ApiError::Internal(_) => (
                axum::http::StatusCode::INTERNAL_SERVER_ERROR,
                "internal server error".into(),
            ),
        };

        let body = axum::Json(serde_json::json!({
            "error": message,
            "status": status.as_u16(),
        }));

        (status, body).into_response()
    }
}
```

### Structured Error Reporting for Observability

In production, you need errors that are both human-readable (for on-call engineers) and machine-parseable (for alerting systems). This requires structured error reporting.

```rust
use serde::Serialize;

/// Structured error report for logging and monitoring systems.
/// This format is compatible with Datadog, Grafana Loki, and ELK.
#[derive(Debug, Serialize)]
pub struct ErrorReport {
    pub message: String,
    pub error_type: String,
    pub severity: ErrorSeverity,
    pub context: serde_json::Value,
    pub chain: Vec<String>,
}

#[derive(Debug, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum ErrorSeverity {
    Warning,
    Error,
    Critical,
}

/// Convert any anyhow error into a structured report.
/// This walks the error chain and captures every cause.
pub fn to_error_report(error: &anyhow::Error, severity: ErrorSeverity) -> ErrorReport {
    let chain: Vec<String> = error.chain().map(|e| e.to_string()).collect();

    ErrorReport {
        message: error.to_string(),
        error_type: format!("{:?}", error.root_cause()),
        severity,
        context: serde_json::json!({
            "chain_length": chain.len(),
            "root_cause": chain.last().cloned().unwrap_or_default(),
        }),
        chain,
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use anyhow::Context;

    #[test]
    fn test_error_chain_context() {
        let root = std::io::Error::new(std::io::ErrorKind::ConnectionRefused, "connection refused");
        let error: anyhow::Error = anyhow::Error::from(root)
            .context("failed to query database")
            .context("failed to load user profile");

        let report = to_error_report(&error, ErrorSeverity::Error);

        assert_eq!(report.chain.len(), 3);
        assert_eq!(report.chain[0], "failed to load user profile");
        assert_eq!(report.chain[1], "failed to query database");
        assert_eq!(report.chain[2], "connection refused");
    }

    #[test]
    fn test_storage_error_display() {
        let err = StorageError::NotFound { key: "user_42".into() };
        assert_eq!(err.to_string(), "key not found: user_42");

        let err = StorageError::CapacityExceeded { used: 900, capacity: 1000 };
        assert_eq!(err.to_string(), "storage capacity exceeded: 900/1000 bytes");
    }

    #[test]
    fn test_api_error_conversion() {
        let storage_err = StorageError::NotFound { key: "item_1".into() };
        let api_err: ApiError = storage_err.into();
        assert!(matches!(api_err, ApiError::NotFound(ref k) if k == "item_1"));

        let storage_err = StorageError::Corruption {
            path: "/data/store".into(),
            expected: "abc".into(),
            actual: "def".into(),
        };
        let api_err: ApiError = storage_err.into();
        // Internal errors should not leak details
        assert!(matches!(api_err, ApiError::Internal(_)));
    }

    #[test]
    fn test_ensure_macro() {
        fn validate_port(port: u16) -> anyhow::Result<()> {
            anyhow::ensure!(port > 1024, "port {port} is privileged");
            Ok(())
        }

        assert!(validate_port(8080).is_ok());
        let err = validate_port(80).unwrap_err();
        assert_eq!(err.to_string(), "port 80 is privileged");
    }
}
```

### Decision Guide: Which Error Strategy to Use

- **Prototype / script**: Use `anyhow` everywhere. You need speed of development, not exhaustive error matching. `fn main() -> anyhow::Result<()>` is the fastest way to get proper error handling.
- **Library crate**: Use `thiserror` for your public error type. Callers need to match on variants. Keep the variant list small (5-10 variants). Group uncommon errors under a catch-all `Other(String)` variant.
- **Application crate**: Use `anyhow` with `.context()` at every call site. Log structured error reports. Convert to HTTP errors at the API boundary.
- **Mixed (library with a CLI)**: Use `thiserror` in `src/lib.rs` and `anyhow` in `src/main.rs`, with `From` conversions at the boundary.

### Key Takeaways

- **Never use `unwrap()` in library code** -- it forces a panic on the caller with no recovery option. Use `expect()` only for invariants that indicate programming errors (e.g., mutex poisoning).
- **Always add `.context()`** when propagating errors across function boundaries. Without context, a raw `io::Error("connection refused")` tells you nothing about which connection to which service failed.
- The **most common mistake** is creating one giant error enum with 30+ variants. If your error type has more than 10 variants, you probably need to split it into sub-errors (e.g., `ParseError`, `IoError`, `ValidationError`) with `#[from]` conversions.
- **Do not expose internal error details in API responses** -- this is both a security pitfall (leaking file paths, SQL queries) and a UX problem (users cannot act on internal errors). Log the details, return a generic message.
- For **observability in production**, walk the error chain with `.chain()` and log every cause. A single "internal server error" in your logs is useless; a chain of "failed to process order -> failed to charge payment -> HTTP 503 from Stripe" is actionable.""",
    ),
]
