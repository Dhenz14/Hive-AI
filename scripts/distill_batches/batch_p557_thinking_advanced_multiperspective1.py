"""Phase 2D: Advanced Reasoning — Multi-Perspective Analysis (Part 1/4)
Analyze the same problem from multiple angles: correctness, performance, security,
maintainability, operability. Identify tensions between perspectives."""

PAIRS = [
    (
        "thinking/multiperspective-auth-system",
        "We're designing the authentication system for a new SaaS product. We need to support email/password login, OAuth (Google, GitHub), and API keys for integrations. What approach should we take?",
        r'''<think>
Let me evaluate this from multiple perspectives simultaneously.

SECURITY:
- Passwords must be hashed with bcrypt/argon2 (never SHA-256, never MD5)
- OAuth reduces our attack surface (we don't store Google passwords)
- API keys are bearer tokens — if leaked, full access. Need rotation, scoping.
- Session management: JWT vs server-side sessions. JWT = stateless but no revocation. Sessions = stateful but revocable.
- MFA should be supported from day 1 (adding it later is painful)
- Rate limiting on login attempts to prevent brute force
- Account lockout vs CAPTCHA after N failures

PERFORMANCE:
- JWT: no DB lookup per request → fast (just verify signature)
- Sessions: DB/Redis lookup per request → adds ~2ms latency
- OAuth: redirect flow adds latency to login (round-trip to provider)
- API key: simple lookup → fast, can be cached
- bcrypt is intentionally slow (100ms per hash) — this is a feature, not a bug

DEVELOPER EXPERIENCE:
- OAuth: need to manage client IDs, secrets, callback URLs per provider
- API keys: developers expect them immediately, not after approval
- Consistent token format across auth methods simplifies middleware
- Good error messages: "Invalid credentials" not "User not found" (info leak)

OPERABILITY:
- JWT: no server-side state → scales easily, but token revocation requires a blacklist
- Sessions: need Redis/DB → another dependency to monitor
- OAuth: depends on external providers → need fallback if Google is down
- API key rotation: need to support multiple active keys during transition
- Audit logging: who logged in, from where, when, which method

MAINTAINABILITY:
- Multiple auth methods = complexity. Need a unified internal representation.
- Abstract behind an AuthProvider interface so adding new providers is easy
- Session vs JWT decision affects architecture deeply — hard to change later

TENSIONS:
- Security wants slow password hashing → Performance wants fast auth
  Resolution: bcrypt on login only (infrequent), fast JWT verification on every request
- Security wants short JWT expiration → UX wants long sessions
  Resolution: short access tokens (15 min) + refresh tokens (7 days)
- Security wants no JWT (server sessions) → Scalability wants stateless
  Resolution: JWT with a revocation blacklist (compromise)
- DX wants simple API keys → Security wants scoped, rotatable, expiring keys
  Resolution: scoped keys with optional expiration, rotation support
</think>

Let me analyze this from five perspectives, then show where they conflict:

**SECURITY perspective**:
```python
# Password hashing: argon2 (preferred) or bcrypt — NEVER SHA-256
from argon2 import PasswordHasher
ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
hashed = ph.hash(password)

# API keys: scoped, rotatable, with prefix for identification
api_key = f"hive_live_{secrets.token_urlsafe(32)}"  # Prefix identifies type
# Store hash of key, not plaintext. Lookup by prefix + first 8 chars.

# OAuth: reduces surface area — we never see the user's Google password
# But we MUST validate the OAuth state parameter (CSRF protection)
```

**PERFORMANCE perspective**:
```
Auth Method     | Login latency  | Per-request latency | Scales?
----------------|---------------|--------------------|---------
Password+JWT    | ~200ms (hash) | ~0.1ms (verify JWT)| Yes (stateless)
OAuth           | ~500ms (redirect) | ~0.1ms (JWT)   | Yes
API key         | ~1ms (lookup) | ~1ms (lookup)      | Cache it
Server sessions | ~5ms (create) | ~2ms (Redis lookup) | Needs Redis
```

**OPERABILITY perspective**:
```python
# Every auth event must be logged for security forensics
async def authenticate(request: Request) -> User:
    # ... auth logic ...
    audit_log.info("auth_event", extra={
        "user_id": user.id,
        "method": "oauth:google",     # Which auth method
        "ip": request.client.host,
        "user_agent": request.headers.get("user-agent"),
        "success": True,
        "timestamp": datetime.utcnow().isoformat(),
    })
```

**The architecture that balances all perspectives**:
```python
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

# Unified auth result — same regardless of method
@dataclass
class AuthResult:
    user_id: str
    method: str           # "password", "oauth:google", "api_key"
    scopes: list[str]     # What this auth is allowed to do
    expires_at: datetime

# Provider interface — one per auth method
class AuthProvider(ABC):
    @abstractmethod
    async def authenticate(self, credentials: dict) -> AuthResult: ...

class PasswordAuthProvider(AuthProvider):
    async def authenticate(self, credentials: dict) -> AuthResult:
        user = await user_repo.get_by_email(credentials["email"])
        if not user or not ph.verify(user.password_hash, credentials["password"]):
            raise AuthError("Invalid credentials")  # Don't reveal WHICH is wrong
        return AuthResult(user.id, "password", ["*"], expires_in(minutes=15))

class OAuthProvider(AuthProvider):
    async def authenticate(self, credentials: dict) -> AuthResult:
        token_data = await exchange_oauth_code(credentials["code"], credentials["provider"])
        user = await user_repo.get_or_create_from_oauth(token_data)
        return AuthResult(user.id, f"oauth:{credentials['provider']}", ["*"], expires_in(minutes=15))

class APIKeyProvider(AuthProvider):
    async def authenticate(self, credentials: dict) -> AuthResult:
        key_hash = hash_api_key(credentials["api_key"])
        api_key = await api_key_repo.get_by_hash(key_hash)
        if not api_key or api_key.is_expired:
            raise AuthError("Invalid API key")
        return AuthResult(api_key.user_id, "api_key", api_key.scopes, api_key.expires_at)

# Token strategy: short-lived access + long-lived refresh
class TokenService:
    def create_token_pair(self, auth_result: AuthResult) -> dict:
        access_token = jwt.encode({
            "sub": auth_result.user_id,
            "scopes": auth_result.scopes,
            "method": auth_result.method,
            "exp": datetime.utcnow() + timedelta(minutes=15),  # Short-lived
        }, SECRET_KEY)

        refresh_token = secrets.token_urlsafe(64)
        # Store refresh token in DB (revocable)
        self.refresh_repo.create(refresh_token, auth_result.user_id, expires_days=7)

        return {"access_token": access_token, "refresh_token": refresh_token}
```

**Key tension resolutions**:
- **Security vs Performance**: Slow hashing (argon2) only at login; fast JWT verification on every request
- **Security vs UX**: 15-min access tokens + 7-day refresh tokens (short enough to limit damage, long enough to not annoy users)
- **Scalability vs Revocation**: JWT is stateless, but refresh tokens are DB-backed (revocable). Revoke refresh token = user must re-login within 15 min
- **DX vs Security**: API keys have scopes and rotation, but creation is instant and self-service'''
    ),
    (
        "thinking/multiperspective-data-pipeline",
        "We need to build a data pipeline that ingests user events from our web app (clickstream, page views, form submissions), processes them, and makes them available for analytics. We expect 50K events/second at peak. What architecture should we use?",
        r'''<think>
Let me analyze from multiple angles:

THROUGHPUT & LATENCY:
- 50K events/sec = 4.3B events/day. This is serious volume.
- Need to distinguish: how fast must analytics see the data?
  - Real-time dashboards: <5 seconds (streaming)
  - Daily reports: batch is fine
  - Most teams need "near-real-time" (1-5 min delay acceptable)
- At 50K/sec, a single-threaded approach is out. Need parallel processing.

RELIABILITY:
- Can we lose events? Clickstream: some loss acceptable. Form submissions: no.
- Need at-least-once delivery (tolerate duplicates, handle in processing)
- Need durability: events survive broker restart (Kafka retention)
- Need replay capability: if a bug in processing, reprocess from offset

COST:
- 50K events/sec × ~500 bytes each = 25 MB/sec ingestion
- Daily: ~2.1 TB raw data
- Monthly: ~63 TB. Storage matters!
- Kafka + Flink + data warehouse = significant infra cost
- vs. managed services (Kinesis, BigQuery Streaming) = higher per-event cost but lower ops

OPERATIONAL COMPLEXITY:
- Self-managed Kafka: 3+ brokers, Zookeeper, monitoring, upgrades
- Self-managed Flink: complex stateful processing, checkpointing
- Managed alternatives: less control but less ops burden
- Team skill: does the team know Kafka/Flink? Learning curve matters.

DATA QUALITY:
- Schema evolution: events change over time. Need schema registry.
- Late-arriving data: events from mobile might arrive hours late
- Deduplication: at-least-once means duplicates. Need idempotent processing.
- Data validation: malformed events shouldn't corrupt the pipeline

SECURITY:
- PII in events (user IDs, emails, IP addresses)
- GDPR: right to deletion — how do you delete from an append-only log?
- Encryption at rest and in transit
- Access control to raw vs aggregated data

TENSIONS:
- Latency wants streaming → Cost wants batching
  Resolution: micro-batch (every 1-5 min) — nearly real-time at batch cost
- Reliability wants at-least-once → Quality wants exactly-once
  Resolution: at-least-once + idempotent consumers (effectively exactly-once)
- Ops complexity wants managed services → Cost wants self-managed
  Resolution: depends on team size. < 3 engineers = managed. > 5 = self-managed may save money
</think>

**Five-perspective analysis** for 50K events/sec analytics pipeline:

**THROUGHPUT perspective** — what can handle 50K/sec:
```
Ingestion Layer     | Max throughput    | Latency
--------------------|-------------------|----------
Kafka (3 brokers)   | 500K+ events/sec  | < 10ms
AWS Kinesis         | 50K/sec (50 shards)| < 200ms
Redis Streams       | 100K+ events/sec  | < 1ms
Direct to DB        | ~5K events/sec    | 10-50ms ← can't handle load
```

**RELIABILITY perspective** — events must not be lost:
```python
# Event producer: buffer + retry + dead letter queue
class EventProducer:
    async def send(self, event: dict):
        try:
            await self.kafka.send("events", value=event)
        except KafkaError:
            # Don't lose the event — store locally and retry
            await self.dead_letter_queue.put(event)
            # Background worker retries dead letters
```

**COST perspective** — 50K/sec = ~2TB/day:
```
Architecture                  | Monthly infra cost | Ops cost (engineers)
------------------------------|-------------------|-----------------------
Self-managed Kafka + Flink    | ~$3K               | 0.5 FTE (~$8K/mo)
AWS Kinesis + Lambda          | ~$8K               | 0.1 FTE (~$1.5K/mo)
GCP Pub/Sub + Dataflow        | ~$6K               | 0.1 FTE
Confluent Cloud + ksqlDB      | ~$5K               | 0.2 FTE

For small team (<5 eng): managed services save money despite higher unit cost.
For large team (>10 eng): self-managed saves money at this scale.
```

**The balanced architecture**:
```
┌─────────┐    ┌─────────┐    ┌──────────────┐    ┌─────────────┐
│ Web App │───→│  Kafka   │───→│ Stream       │───→│ Data        │
│ Events  │    │  Topics  │    │ Processor    │    │ Warehouse   │
│ (50K/s) │    │          │    │ (Flink/      │    │ (ClickHouse/│
└─────────┘    └────┬─────┘    │  micro-batch)│    │  BigQuery)  │
                    │          └──────┬───────┘    └──────┬──────┘
                    │                 │                    │
               ┌────▼─────┐    ┌─────▼──────┐    ┌──────▼──────┐
               │ Schema   │    │ Dead Letter │    │ Dashboard   │
               │ Registry │    │ Queue       │    │ (Grafana/   │
               │ (Avro)   │    │ (errors)    │    │  Metabase)  │
               └──────────┘    └────────────┘    └─────────────┘
```

```python
# Stream processor: micro-batch for cost + near-real-time
from pyspark.sql import SparkSession

spark = SparkSession.builder.appName("EventProcessor").getOrCreate()

events = (spark.readStream
    .format("kafka")
    .option("kafka.bootstrap.servers", "kafka:9092")
    .option("subscribe", "user-events")
    .load())

processed = (events
    .select(from_json(col("value").cast("string"), event_schema).alias("event"))
    .select("event.*")
    .withColumn("processed_at", current_timestamp())
    .dropDuplicates(["event_id"])  # Dedup for at-least-once
)

# Write to warehouse in micro-batches (every 60 seconds)
(processed.writeStream
    .format("clickhouse")  # or bigquery, snowflake
    .trigger(processingTime="60 seconds")  # Near-real-time at batch cost
    .option("checkpointLocation", "/checkpoints/events")
    .start())
```

**Key tension resolutions**:
- **Latency vs Cost**: Micro-batch every 60s (not true streaming) — 95% of analytics queries don't need sub-second freshness
- **Reliability vs Complexity**: Kafka provides at-least-once delivery; dedup in the processor makes it effectively exactly-once
- **GDPR vs Append-only**: Store raw events in Kafka with 30-day retention. Warehouse supports `DELETE WHERE user_id = X` for GDPR requests'''
    ),
    (
        "thinking/multiperspective-error-handling",
        "What's the right error handling strategy for our REST API? We have 50 endpoints across 8 microservices. Some team members catch everything, some let errors propagate, and error responses are inconsistent.",
        r'''<think>
Let me analyze error handling from multiple perspectives:

USER EXPERIENCE:
- Users need actionable error messages: "Email already registered" not "Constraint violation"
- Different clients need different detail levels (API client vs browser vs mobile)
- Error responses must be CONSISTENT across all 50 endpoints and 8 services
- Users should never see stack traces or internal details
- Validation errors should return ALL fields that failed, not just the first one

DEBUGGABILITY:
- Engineers need to trace errors across 8 microservices
- Need correlation IDs that flow through the entire request chain
- Internal error details (stack trace, service, version) must be logged
- Error rate monitoring needs consistent error codes for alerting
- Must distinguish "expected" errors (validation) from "unexpected" (null pointer)

SECURITY:
- Stack traces leak internal structure (class names, file paths, framework versions)
- Database errors can leak schema information
- "User not found" vs "Wrong password" leaks whether an email is registered
- Error messages in URLs can enable XSS if reflected

PERFORMANCE:
- Exception handling has CPU cost (stack unwinding)
- Logging every 4xx error at ERROR level floods logs
- Validation errors are common and expected — handle efficiently
- Avoid unnecessary string formatting for errors that won't be logged

CONSISTENCY:
- 8 microservices × 50 endpoints = high chance of inconsistency
- Need a shared error response contract
- Need shared error handling middleware
- Error codes should be documented and stable (clients depend on them)

TENSIONS:
- Debuggability wants detailed errors → Security wants minimal external info
  Resolution: full details in logs, sanitized version in response
- UX wants specific messages → Security wants generic messages (for auth)
  Resolution: specific for validation, generic for auth
- Performance wants minimal overhead → Debuggability wants rich context
  Resolution: structured logging with lazy evaluation
</think>

**Unified error strategy across all 8 services — analyzed from 5 angles**:

**Standard error response format** (all 50 endpoints, all services):
```python
# Every error response looks like this — no exceptions
{
    "error": {
        "code": "VALIDATION_ERROR",        # Machine-readable, stable
        "message": "Invalid request data",  # Human-readable
        "details": [                         # Optional: field-level errors
            {"field": "email", "message": "Already registered"},
            {"field": "age", "message": "Must be between 1 and 150"}
        ],
        "request_id": "req_abc123"          # For cross-service tracing
    }
}
```

**Error classification** (drives logging, alerting, and response):
```python
from enum import Enum

class ErrorCategory(Enum):
    # 4xx — client's fault, expected, log at WARN
    VALIDATION = ("VALIDATION_ERROR", 400, "warn")
    AUTHENTICATION = ("AUTH_FAILED", 401, "warn")
    FORBIDDEN = ("FORBIDDEN", 403, "warn")
    NOT_FOUND = ("NOT_FOUND", 404, "info")     # Very common, don't flood logs
    CONFLICT = ("CONFLICT", 409, "warn")
    RATE_LIMITED = ("RATE_LIMITED", 429, "info")

    # 5xx — our fault, unexpected, log at ERROR + alert
    INTERNAL = ("INTERNAL_ERROR", 500, "error")
    SERVICE_UNAVAILABLE = ("SERVICE_UNAVAILABLE", 503, "error")
    DEPENDENCY_FAILED = ("DEPENDENCY_FAILED", 502, "error")

# Shared exception hierarchy — used by all 8 services
class AppError(Exception):
    def __init__(self, category: ErrorCategory, message: str, details=None):
        self.category = category
        self.message = message
        self.details = details or []
        self.code, self.status_code, self.log_level = category.value

# Shared middleware — consistent handling across all services
@app.exception_handler(AppError)
async def handle_app_error(request: Request, exc: AppError):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    # LOG: full details (for engineers)
    log_func = getattr(logger, exc.log_level)
    log_func(
        f"[{exc.code}] {exc.message}",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "error_code": exc.code,
            "details": exc.details,
        },
        exc_info=exc.log_level == "error",  # Stack trace only for 5xx
    )

    # RESPONSE: sanitized (for users)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details,
                "request_id": request_id,
            }
        }
    )

@app.exception_handler(Exception)
async def handle_unexpected(request: Request, exc: Exception):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    # LOG: everything — this is a bug
    logger.critical(f"Unhandled: {exc}", extra={"request_id": request_id}, exc_info=True)
    metrics.increment("unhandled_errors")  # Triggers PagerDuty

    # RESPONSE: nothing internal (security)
    return JSONResponse(
        status_code=500,
        content={"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred", "request_id": request_id}}
    )
```

**Cross-service error propagation** (correlation IDs):
```python
# Service A calls Service B — propagate request ID
async def call_service_b(request_id: str, data: dict):
    try:
        resp = await httpx.post(
            f"{SERVICE_B_URL}/process",
            json=data,
            headers={"X-Request-ID": request_id},  # Same ID flows through
            timeout=5.0,
        )
        if resp.status_code >= 400:
            error = resp.json()["error"]
            raise AppError(
                ErrorCategory.DEPENDENCY_FAILED,
                f"Service B failed: {error['message']}",
            )
    except httpx.TimeoutException:
        raise AppError(ErrorCategory.SERVICE_UNAVAILABLE, "Service B timeout")
```

**Security-specific decisions**:
```python
# Auth errors: GENERIC messages (don't reveal which field is wrong)
raise AppError(ErrorCategory.AUTHENTICATION, "Invalid credentials")
# NOT: "User not found" or "Wrong password" — leaks info

# Validation errors: SPECIFIC messages (help the user fix it)
raise AppError(ErrorCategory.VALIDATION, "Invalid input", details=[
    {"field": "email", "message": "Must be a valid email address"},
])
```

**Monitoring from error codes**:
```
Alert Rule                          | Threshold | Action
------------------------------------|-----------|------------------
INTERNAL_ERROR rate > 10/min        | Critical  | Page on-call
DEPENDENCY_FAILED for service X     | Warning   | Check service X health
RATE_LIMITED spike                  | Info      | Check for abuse
AUTH_FAILED spike from single IP    | Warning   | Possible brute force
```'''
    ),
    (
        "thinking/multiperspective-caching-strategy",
        "Our e-commerce product pages load in 2 seconds. The product catalog has 100K products. Products change ~100 times per day (price updates, stock changes). Should we add caching, and if so, what strategy?",
        r'''<think>
Let me analyze this from multiple perspectives:

FRESHNESS vs PERFORMANCE:
- Products change 100 times/day across 100K products = any individual product changes ~once per 1000 days on average (very infrequent)
- But SOME products (popular/promoted) change more often (price, stock)
- 2-second page load is bad for UX (Amazon found every 100ms = 1% revenue)
- Goal: < 200ms page load without serving stale prices

CACHE HIT RATE:
- 100K products, but traffic follows power law (20% of products get 80% of traffic)
- If we cache the top 20K products: ~80% hit rate
- TTL of 60 seconds: 100 changes/day ÷ 86400 seconds = 1 change every 864 seconds
- Average staleness with 60s TTL: product is stale for ~60s out of every 864s = ~7% of the time
- Is 7% staleness acceptable? For most products, yes. For prices shown at checkout, NO.

CONSISTENCY:
- Product listing page: 30-60 second staleness is fine (user will see current price at checkout)
- Shopping cart / checkout: MUST be fresh (stale price = legal/financial issue)
- Search results: 5-minute staleness is fine

MEMORY:
- 100K products × ~5KB each = ~500MB cache
- Top 20K products = ~100MB — easily fits in Redis
- Include images/descriptions = much more, use CDN for media

INVALIDATION STRATEGY:
- TTL-based: simple, eventual consistency (max staleness = TTL)
- Event-based: price change → invalidate cache → next request gets fresh data
- Write-through: update cache on write → always fresh, but adds write latency
- Read-through: cache miss → fetch from DB → populate cache → return

Recommendation: event-based invalidation for critical fields (price, stock), TTL-based for everything else.

OPERABILITY:
- Redis as cache: need monitoring (hit rate, memory, eviction rate)
- Cache stampede protection: when a popular product's cache expires, 1000 requests hit DB simultaneously
- Cold start: after Redis restart, all requests hit DB (need warming)
</think>

**Multi-perspective analysis — yes, cache, but with nuanced strategy**:

**The math that drives the decision**:
```
Current: 2 seconds/page × millions of views/day = massive waste
Target: <200ms/page
Products: 100K total, ~20K get 80% of traffic (power law)
Change rate: 100/day ÷ 100K products = any product changes once per 1000 days
Staleness with 60s TTL: product is stale ~7% of the time — acceptable for listings
```

**Tiered caching strategy — different freshness per context**:
```python
from enum import Enum

class CachePolicy(Enum):
    # Product listing pages: 60s staleness is fine
    LISTING = {"ttl": 60, "strategy": "cache-aside", "stale_while_revalidate": True}

    # Product detail page: 30s staleness, event-invalidated for price
    DETAIL = {"ttl": 30, "strategy": "event-invalidated"}

    # Cart/checkout: NEVER cached (stale price = legal issue)
    CHECKOUT = {"ttl": 0, "strategy": "no-cache"}

    # Search results: 5 min staleness is fine
    SEARCH = {"ttl": 300, "strategy": "cache-aside"}


class ProductCache:
    def __init__(self, redis_client):
        self.redis = redis_client

    async def get_product(self, product_id: str, policy: CachePolicy) -> dict:
        if policy == CachePolicy.CHECKOUT:
            return await self._fetch_from_db(product_id)  # Always fresh

        cache_key = f"product:{product_id}"
        cached = await self.redis.get(cache_key)

        if cached:
            return json.loads(cached)

        # Cache miss — fetch and populate
        product = await self._fetch_from_db(product_id)
        ttl = policy.value["ttl"]
        await self.redis.setex(cache_key, ttl, json.dumps(product))
        return product

    async def invalidate(self, product_id: str):
        """Called when price/stock changes — event-driven invalidation."""
        await self.redis.delete(f"product:{product_id}")
        await self.redis.delete(f"search:*")  # Invalidate search results too


# Event-driven invalidation: when product changes, cache is immediately cleared
async def handle_product_updated(event: ProductUpdatedEvent):
    await product_cache.invalidate(event.product_id)
    # Next request will cache-miss and get fresh data
```

**Cache stampede protection** (critical for popular products):
```python
async def get_product_safe(self, product_id: str, policy: CachePolicy) -> dict:
    cache_key = f"product:{product_id}"
    lock_key = f"lock:product:{product_id}"

    cached = await self.redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # Stampede protection: only ONE request fetches from DB
    acquired = await self.redis.set(lock_key, "1", nx=True, ex=5)
    if acquired:
        try:
            product = await self._fetch_from_db(product_id)
            await self.redis.setex(cache_key, policy.value["ttl"], json.dumps(product))
            return product
        finally:
            await self.redis.delete(lock_key)
    else:
        # Another request is fetching — wait briefly, retry cache
        await asyncio.sleep(0.1)
        cached = await self.redis.get(cache_key)
        return json.loads(cached) if cached else await self._fetch_from_db(product_id)
```

**Perspective tensions and resolutions**:
```
Tension                            Resolution
─────────────────────────          ─────────────────────────
Freshness vs Speed                 Tiered: listings cached, checkout never
Memory vs Hit Rate                 Cache top 20K products (100MB, 80% hits)
Simplicity vs Consistency          Event invalidation for prices, TTL for rest
Availability vs Consistency        Stale-while-revalidate: serve stale, refresh background
```

**Monitoring dashboard**:
```
Metric               | Healthy       | Alert threshold
---------------------|---------------|------------------
Cache hit rate       | > 80%         | < 60% (cold start or bad TTL)
Avg staleness        | < 30s         | > 120s (invalidation broken)
Redis memory         | < 80% limit   | > 90% (need eviction policy)
Cache stampede events| < 10/min      | > 100/min (popular product churn)
P99 response time    | < 200ms       | > 500ms (cache not helping)
```'''
    ),
    (
        "thinking/multiperspective-logging",
        "How verbose should our application logging be? Some developers want to log everything for debugging, others say it's too noisy and expensive. What's the right balance?",
        r'''<think>
Let me analyze from multiple angles:

DEBUGGABILITY:
- Want: log every request, every DB query, every external call, full request/response bodies
- This makes production debugging trivial — "show me everything that happened for request X"
- But: at scale, this is terabytes of logs per day

PERFORMANCE:
- Each log statement: serialize data, write to buffer, maybe flush to disk
- Synchronous logging: adds 0.1-1ms per log statement
- At 1000 log statements per request: 100ms-1s of logging overhead!
- String formatting for logs that won't be output (debug level in prod): pure waste

COST:
- Log storage: $0.50-1.00 per GB ingested (Datadog, Splunk, etc.)
- 100K requests/sec × 10KB logs per request = 1GB/sec = 86TB/day = $43K-86K/day!
- Even with sampling: 10% = $4.3K-8.6K/day
- Self-hosted ELK: cheaper per GB but needs 3+ engineers to maintain

SECURITY:
- Logging request bodies might capture passwords, credit cards, PII
- GDPR: logs containing PII must be deletable on request
- Logs are attack surface: if attacker can inject log entries (log injection), can confuse forensics
- Full request logs are a goldmine for attackers who gain access to log storage

NOISE:
- Too many logs = engineers ignore them
- "Alert fatigue" when every error is logged at ERROR level
- Structured logging (JSON) is searchable; unstructured (text) is not
- Need signal, not noise

COMPLIANCE:
- Some industries require audit logs (financial, healthcare)
- Retention requirements: keep for N years
- Need to balance "log everything" (compliance) with "log nothing PII" (privacy)

The right balance: structured, leveled, sampled logging with sensitive data redaction.
</think>

**The "right amount" of logging — analyzed from 5 perspectives**:

**The cost math** (this usually settles the debate):
```
Scenario: 100K requests/sec, 10KB logs per request (verbose)
Daily log volume: 100K × 10KB × 86400 = 86 TB/day

Log service costs:
  Datadog: $0.10/GB indexed = $8,600/day = $258K/month
  Splunk:  $0.50/GB ingested = $43,000/day = $1.3M/month (!)
  Self-hosted ELK: ~$5K/month infra + 1 FTE to maintain

With structured, leveled logging (1KB per request):
  Daily: 8.6 TB/day → $860/day = $26K/month on Datadog
  90% reduction just from being intentional about what you log.
```

**The logging strategy that balances everything**:
```python
import structlog
import logging

# Configure structured logging with levels
logger = structlog.get_logger()

# ═══════════════════════════════════════════
# LEVEL GUIDE — what goes where
# ═══════════════════════════════════════════

# DEBUG: Developer-only, NEVER in production
# "I'm tracing through this function"
logger.debug("Query plan", query=query, plan=plan)  # Off in prod

# INFO: Important business events (always on)
# "Something significant happened that we'd want to know about"
logger.info("order_created", order_id=order.id, total=order.total, items=len(order.items))
logger.info("user_registered", user_id=user.id, method="oauth:google")

# WARNING: Something unexpected but handled
# "This shouldn't happen often, but we recovered"
logger.warning("retry_succeeded", service="payment", attempt=3, latency_ms=1200)
logger.warning("rate_limited", user_id=user.id, endpoint="/api/search")

# ERROR: Something failed and we couldn't recover for this request
# "A user was affected, but the system is still running"
logger.error("payment_failed", order_id=order.id, error=str(e), gateway="stripe")

# CRITICAL: System is degraded, needs immediate attention
# "Wake someone up"
logger.critical("database_connection_lost", host="db-primary", error=str(e))


# ═══════════════════════════════════════════
# SENSITIVE DATA REDACTION
# ═══════════════════════════════════════════
class SensitiveDataFilter:
    REDACT_FIELDS = {"password", "credit_card", "ssn", "token", "secret", "authorization"}

    def __call__(self, _, __, event_dict):
        for key in list(event_dict.keys()):
            if any(sensitive in key.lower() for sensitive in self.REDACT_FIELDS):
                event_dict[key] = "***REDACTED***"
        return event_dict

structlog.configure(processors=[
    SensitiveDataFilter(),
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.JSONRenderer(),
])


# ═══════════════════════════════════════════
# REQUEST-LEVEL LOGGING (one line per request)
# ═══════════════════════════════════════════
@app.middleware("http")
async def request_logging(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.perf_counter()

    response = await call_next(request)

    duration_ms = (time.perf_counter() - start) * 1000

    # ONE structured log line per request — searchable, compact
    logger.info("http_request",
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round(duration_ms, 1),
        user_id=getattr(request.state, "user_id", None),
    )
    # NOT logging: request body, response body, headers, query params
    # Those go in DEBUG level only, sampled in production

    return response
```

**Sampling for expensive logs** (have your cake and eat it too):
```python
import random

def should_sample(rate: float = 0.01) -> bool:
    """Log 1% of requests at DEBUG level for deep debugging."""
    return random.random() < rate

@app.middleware("http")
async def sampled_debug_logging(request: Request, call_next):
    if should_sample(0.01):
        # 1% of requests: log EVERYTHING (for debugging production issues)
        logger.debug("http_request_full",
            body=await request.body(),
            headers=dict(request.headers),
            # Still redact sensitive data!
        )
    # Other 99%: just the standard INFO line
```

**Decision matrix**:
```
Question                              Answer
────────────────────────────          ──────
Log request/response bodies?          DEBUG only, sampled 1%, redact PII
Log every DB query?                   DEBUG only, NEVER in prod unless debugging
Log business events?                  INFO — always (order_created, user_registered)
Log external service calls?           INFO with latency (for SLO tracking)
Log errors with stack traces?         ERROR (5xx) yes, WARN (4xx) no
How long to retain?                   INFO: 30 days. ERROR: 90 days. DEBUG: 7 days.
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
