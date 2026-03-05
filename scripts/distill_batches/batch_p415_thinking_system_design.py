"""Thinking-trace pairs: system design decisions with capacity planning reasoning."""

PAIRS = [
    (
        "thinking/design-rate-limiter",
        "Design a rate limiter for our API. We have 10 application servers behind a load balancer, serving 50,000 requests/second total. Each user gets 100 requests per minute. How should we implement this?",
        r'''<think>
Let me think through the design constraints:

**Requirements:**
- 50K req/s across 10 servers = 5K req/s per server
- Per-user limit: 100 requests per minute
- Must work correctly across all 10 servers (distributed)

**Why a local rate limiter won't work:**
If each server tracks counts independently, a user hitting different servers gets 100 × 10 = 1000 requests/minute. The load balancer distributes requests (round-robin, least connections, etc.), so a single user's requests will hit different servers.

**Option 1: Sticky sessions**
Route each user to the same server. Then local rate limiting works. But:
- Uneven load distribution (hot users overload one server)
- Failover breaks rate limiting state
- Reduces benefits of load balancing
Not ideal.

**Option 2: Centralized Redis counter**
Each server checks/increments a counter in Redis before processing.
- Key: `rate:{user_id}`, value: request count, TTL: 60 seconds
- Atomic increment with INCR
- If count > 100, reject

Pros: Simple, correct, widely used.
Cons: Redis becomes a single point of failure. Every request adds Redis RTT (~0.5ms).

At 50K req/s, Redis handles this easily (Redis does 100K+ ops/s single-threaded). Network latency is the concern — 0.5ms per request adds 50% overhead if API latency is 1ms. But for most APIs with 10-100ms latency, 0.5ms is negligible.

**Option 3: Token bucket in Redis**
Instead of a simple counter with TTL, use the token bucket algorithm:
- Bucket capacity: 100 tokens
- Refill rate: 100 tokens per 60 seconds (~1.67 tokens/second)
- Each request consumes 1 token
- If bucket empty, reject

Advantage over fixed window: no burst at window boundaries. With a fixed counter that resets every minute, a user can send 100 requests at 0:59 and 100 more at 1:01 — 200 requests in 2 seconds.

Token bucket smooths this out. But it's more complex to implement.

**Option 4: Sliding window log**
Store timestamps of each request in a sorted set. Count requests in the last 60 seconds. Most accurate but uses more memory (storing every timestamp vs. a single counter).

At 100 requests per user per minute, storing timestamps in a Redis sorted set uses ~100 × 20 bytes = 2KB per active user. With 100K active users, that's 200MB — manageable.

**Option 5: Sliding window counter (hybrid)**
Combine fixed window counter with weighted overlap. Use two counters (current minute and previous minute), weight the previous minute's count by the overlap ratio.

Example: At 0:45 (45 seconds into current window):
- Previous minute had 80 requests
- Current minute has 40 requests
- Weighted count = 80 × (15/60) + 40 = 20 + 40 = 60
- Under limit (100), allow

This is approximate but uses minimal memory (2 counters per user) and handles window boundaries well.

**My recommendation: Token bucket in Redis with Lua script**

Why:
1. Token bucket handles bursts gracefully
2. Redis Lua script makes the check-and-decrement atomic (no race conditions)
3. Single Redis call per request (no multi-step transaction)
4. Memory efficient (2 keys per user: token count + last refill timestamp)

For resilience:
- Redis Sentinel or Redis Cluster for HA
- If Redis is down, fail OPEN (allow requests) — better to serve some extra requests than to reject all traffic
- Local in-memory fallback with approximate counts during Redis outage

Let me also consider the Lua script design. We need:
1. Read current tokens and last refill time
2. Calculate tokens to add based on elapsed time
3. If tokens available, decrement and allow
4. If not, reject and return time until next token

This must be atomic — the Lua script runs in Redis's single-threaded event loop, so no race conditions between concurrent requests.
</think>

### Architecture: Token Bucket in Redis

```
                    ┌──────────────┐
  Users ──→ LB ──→ │ App Server 1 │──→ Redis ──→ rate:{user_id}
                    │ App Server 2 │──↗     tokens: 87
                    │    ...       │──↗     last_refill: 1709654321.5
                    │ App Server 10│──↗
                    └──────────────┘
```

### Redis Lua Script (atomic, no race conditions)

```lua
-- rate_limit.lua
-- KEYS[1] = rate limit key (e.g., "rate:user:12345")
-- ARGV[1] = max tokens (bucket capacity)
-- ARGV[2] = refill rate (tokens per second)
-- ARGV[3] = current timestamp (seconds, float)
-- ARGV[4] = tokens to consume (usually 1)

local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local requested = tonumber(ARGV[4])

-- Get current state
local data = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

-- Initialize if first request
if tokens == nil then
    tokens = capacity
    last_refill = now
end

-- Refill tokens based on elapsed time
local elapsed = math.max(0, now - last_refill)
tokens = math.min(capacity, tokens + (elapsed * refill_rate))
last_refill = now

-- Check if enough tokens
local allowed = false
local retry_after = 0

if tokens >= requested then
    tokens = tokens - requested
    allowed = true
else
    -- Calculate wait time for next available token
    retry_after = (requested - tokens) / refill_rate
end

-- Save state
redis.call('HMSET', key, 'tokens', tokens, 'last_refill', last_refill)
redis.call('EXPIRE', key, math.ceil(capacity / refill_rate) * 2)  -- Auto-cleanup inactive users

if allowed then
    return {1, tostring(tokens)}  -- allowed, remaining tokens
else
    return {0, tostring(retry_after)}  -- denied, seconds until retry
end
```

### Python Implementation

```python
import time
import redis
from pathlib import Path

class DistributedRateLimiter:
    def __init__(self, redis_url: str = 'redis://localhost:6379'):
        self.redis = redis.Redis.from_url(redis_url)
        self._script = self.redis.register_script(
            Path('rate_limit.lua').read_text()
        )

    def allow(self, key: str, capacity: int = 100,
              refill_rate: float = 1.667,  # 100 per 60 seconds
              tokens: int = 1) -> tuple[bool, float]:
        """
        Check if request is allowed under rate limit.
        Returns (allowed: bool, remaining_or_retry_after: float)
        """
        try:
            result = self._script(
                keys=[f'rate:{key}'],
                args=[capacity, refill_rate, time.time(), tokens]
            )
            allowed = bool(result[0])
            value = float(result[1])
            return allowed, value
        except redis.ConnectionError:
            # Redis down: fail OPEN (allow traffic)
            return True, capacity


# Middleware integration (FastAPI example)
limiter = DistributedRateLimiter()

@app.middleware('http')
async def rate_limit_middleware(request, call_next):
    user_id = request.state.user_id  # From auth middleware
    allowed, value = limiter.allow(f'user:{user_id}')

    if not allowed:
        return JSONResponse(
            {'error': 'Rate limit exceeded'},
            status_code=429,
            headers={
                'Retry-After': str(int(value) + 1),
                'X-RateLimit-Limit': '100',
                'X-RateLimit-Remaining': '0',
            }
        )

    response = await call_next(request)
    response.headers['X-RateLimit-Remaining'] = str(int(value))
    return response
```

### Why token bucket over alternatives

| Algorithm | Burst handling | Memory | Accuracy | Complexity |
|-----------|---------------|--------|----------|------------|
| Fixed window counter | Bad (2x burst at boundary) | 1 key/user | Low | Simple |
| Sliding window log | Good | 100 entries/user | Exact | Medium |
| Sliding window counter | Good | 2 keys/user | Approximate | Medium |
| **Token bucket** | **Configurable** | **2 fields/user** | **Good** | **Medium** |

### Capacity planning

```
Active users: 100,000
Memory per user: ~100 bytes (hash with 2 fields + key)
Total Redis memory: ~10MB
Redis ops: 50,000/second (one EVALSHA per request)
Redis capacity: 100,000+ ops/s → 50% utilization → comfortable headroom
```

### Failure modes

| Scenario | Behavior |
|----------|----------|
| Redis down | Fail open — allow all traffic (better than blocking everything) |
| Redis slow (>10ms) | Circuit breaker → fall back to local approximate limiter |
| Clock skew between servers | Irrelevant — each request sends its own `time.time()` to the Lua script |
| Redis key eviction | User gets a fresh bucket (full tokens) — slightly permissive, acceptable |'''
    ),
    (
        "thinking/design-message-queue-choice",
        "We're building an event-driven system for an e-commerce platform. Events include: order placed, payment processed, inventory updated, shipping notification. We need to choose between RabbitMQ, Kafka, and Redis Streams. Daily volume is about 2 million events. What should we pick?",
        r'''<think>
Let me evaluate each option against the specific requirements.

**Workload characteristics:**
- 2 million events/day = ~23 events/second average
- E-commerce has burst patterns: flash sales, Black Friday could 10-100x this
- So peak might be 2,300 events/second
- Events: order placed, payment processed, inventory updated, shipping notification
- These are business-critical events (payments, inventory) — can't lose them

**Key requirements I need to assess:**
1. Durability — can't lose payment events
2. Ordering — do events need to be processed in order?
3. Multiple consumers — do multiple services need the same event?
4. Replay — do we need to reprocess past events?
5. Throughput — 23/s average, 2,300/s peak
6. Latency — payments need low latency, shipping notifications don't
7. Operational complexity — team size and expertise matter

**RabbitMQ assessment:**
- Traditional message broker, AMQP protocol
- Excellent at task distribution (competing consumers)
- Supports multiple exchange types (direct, fanout, topic)
- Fanout exchange: one event → multiple queues (order service, email service, analytics)
- Message acknowledgment: consumers confirm processing, messages redelivered on failure
- Durable queues with disk persistence
- Throughput: ~50K messages/s easily — way more than we need
- Ordering: per-queue FIFO, but multiple consumers break ordering
- NO replay: once consumed and ACKed, messages are deleted
- Mature, battle-tested, great tooling (management UI, Prometheus metrics)
- Operational: moderate complexity, needs Erlang runtime

**Kafka assessment:**
- Distributed commit log, not a traditional queue
- Append-only log with configurable retention (days, weeks, forever)
- Consumer groups: multiple services read from the same topic independently
- Each consumer tracks its own offset — replay is trivial (reset offset)
- Partitioning: events in the same partition are strictly ordered
- Key-based routing: all events for order #12345 go to the same partition → ordered processing
- Throughput: 100K+ messages/s per broker — massive overkill for 23/s
- Durability: replication factor 3 = survive 2 broker failures
- Operational: COMPLEX. ZooKeeper (or KRaft in newer versions), partition management, consumer group rebalancing, disk management
- For 2M events/day, Kafka is like using a 747 to go to the grocery store

**Redis Streams assessment:**
- Built into Redis 5+, no additional infrastructure if Redis is already used
- XADD/XREAD API, consumer groups with ACK
- Persistent if Redis has AOF/RDB persistence enabled
- Throughput: 100K+ messages/s
- Ordering: strict within a stream
- Replay: XRANGE lets you read any time range
- Consumer groups: multiple consumers, message acknowledgment
- BUT: Redis is primarily in-memory. 2M events/day × 1KB each × 7 days retention = 14GB. Feasible but competes with cache data for RAM
- Operational: simplest if Redis is already in the stack
- Risk: Redis is not primarily a message broker. Less mature tooling for this use case. AOF persistence adds disk I/O.

**My recommendation flow:**

For 2M events/day at an e-commerce company:

1. Is the team already running Kafka? → Use Kafka (don't add another system)
2. Does the team need event replay for analytics/debugging? → Kafka or Redis Streams
3. Is operational simplicity a priority? → RabbitMQ (most straightforward) or Redis Streams (if Redis exists)
4. Will volume grow 100x in the next 2 years? → Kafka (future-proofs)

For THIS specific case:
- 2M events/day is LOW volume — any of these handle it trivially
- E-commerce events are business-critical — durability matters
- Multiple services need the same events (order service, payment, email, analytics) — need pub/sub or consumer groups
- Replay is valuable (debugging payment issues, rebuilding search index)
- Ordering matters for some events (payment must process before shipping)

I'd recommend **RabbitMQ** for most teams at this scale, with a note on when to graduate to Kafka.

Why not Kafka: the operational overhead isn't justified at 23 events/second. A 3-node Kafka cluster with ZooKeeper/KRaft, partition management, consumer group monitoring — that's a lot of complexity for a low-volume workload.

Why not Redis Streams: if they're already using Redis for caching, adding streams is tempting. But mixing cache data and business-critical event streams in the same Redis instance is risky. A cache eviction policy that drops events = data loss. You'd need a dedicated Redis instance, which negates the "no additional infrastructure" benefit.

RabbitMQ with publisher confirms + durable queues + consumer ACKs gives exactly the durability guarantees needed. The fanout exchange pattern handles multi-consumer nicely. And the management UI makes operational work straightforward.
</think>

### Recommendation: RabbitMQ

At 2M events/day (~23/s), all three handle the volume trivially. The decision comes down to operational complexity, durability guarantees, and team capabilities.

### Comparison for your workload

| Factor | RabbitMQ | Kafka | Redis Streams |
|--------|----------|-------|---------------|
| Volume handling | 23/s (capacity: 50K/s) | 23/s (capacity: 1M/s) | 23/s (capacity: 100K/s) |
| Durability | Durable queues + disk | Replicated log | AOF persistence |
| Multi-consumer | Fanout exchange | Consumer groups | Consumer groups |
| Event replay | No (consumed = deleted) | Yes (offset reset) | Yes (XRANGE) |
| Ordering | Per-queue FIFO | Per-partition | Per-stream |
| Operational cost | **Medium** | **High** (ZooKeeper/KRaft, partitions) | **Low** (if Redis exists) |
| Right-sized? | **Yes** | Overkill | Risky for critical events |

### Why RabbitMQ wins here

1. **Right-sized**: Kafka's distributed log is built for millions of events/second. At 23/s, you're paying operational complexity for capacity you don't need.

2. **Durability without compromise**: Publisher confirms + durable queues + consumer ACKs = guaranteed delivery. Redis Streams CAN lose data if AOF fsync is delayed.

3. **Multi-consumer is natural**: Fanout exchanges send one event to multiple queues (order processing, email notification, analytics) without consumer group coordination.

### Architecture

```
                         ┌─ Queue: order_processing ─→ Order Service
                         │
Order Placed ─→ Exchange ├─ Queue: payment_trigger ──→ Payment Service
  (fanout)               │
                         ├─ Queue: email_notify ─────→ Email Service
                         │
                         └─ Queue: analytics ────────→ Analytics Service
```

```python
# Publisher (with confirms for durability)
import pika

connection = pika.BlockingConnection(pika.ConnectionParameters('rabbitmq'))
channel = connection.channel()

# Durable exchange survives broker restart
channel.exchange_declare('order_events', exchange_type='fanout', durable=True)

# Publish with mandatory delivery confirmation
channel.confirm_delivery()
channel.basic_publish(
    exchange='order_events',
    routing_key='',
    body=json.dumps({'order_id': 12345, 'event': 'placed', 'timestamp': '...'}),
    properties=pika.BasicProperties(
        delivery_mode=2,  # Persistent message (written to disk)
        content_type='application/json',
    ),
)
```

```python
# Consumer (with manual ACK for at-least-once delivery)
def handle_order_event(ch, method, properties, body):
    event = json.loads(body)
    try:
        process_payment(event)
        ch.basic_ack(delivery_tag=method.delivery_tag)  # ACK only after success
    except Exception:
        # Requeue for retry (with dead-letter exchange for poison messages)
        ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

channel.basic_qos(prefetch_count=10)  # Don't overwhelm the consumer
channel.basic_consume(queue='payment_trigger', on_message_callback=handle_order_event)
channel.start_consuming()
```

### When to graduate to Kafka

Switch when ANY of these become true:
- Volume exceeds 100K events/second sustained
- You need event replay (rebuild read models, audit trail, debugging)
- You're building event sourcing (events ARE the source of truth)
- Multiple teams need independent consumption at different speeds
- You need exactly-once semantics with idempotent consumers

### When Redis Streams makes sense

- You already run Redis and want zero new infrastructure
- Events are non-critical (cache invalidation, real-time notifications)
- Retention is short (hours, not days)
- **Never** mix cache data and business-critical events in the same Redis instance'''
    ),
    (
        "thinking/design-caching-strategy",
        "Our app has a product catalog page that gets 10,000 requests/minute but the underlying database query takes 200ms. The catalog changes maybe 5 times per day. What caching strategy should we use?\n\nWe're running Python/FastAPI with PostgreSQL.",
        r'''<think>
Let me break down the problem:

- 10,000 requests/minute = ~167 requests/second
- Each request costs 200ms of DB time
- Without caching: 167 × 200ms = 33.4 seconds of DB time per second — that's 33 concurrent DB queries constantly. PostgreSQL connection pool would need to be huge.
- Data changes 5 times/day — extremely read-heavy, almost static

This is the textbook case for aggressive caching. The question is: what layer(s) to cache at, and how to invalidate.

**Layer 1: Application-level cache (in-memory)**
Store the query result in the Python process memory. Zero network overhead.
- Pro: Fastest possible (nanoseconds to read from dict)
- Con: Each of the N app server processes has its own copy. Invalidation means notifying all processes.
- Con: Memory usage × N processes
- For catalog data that changes 5x/day, this is fine. Even with stale data for 30 seconds, it's acceptable.

**Layer 2: Redis cache**
Store serialized result in Redis. One copy shared across all servers.
- Pro: Shared state, single invalidation point
- Con: Network RTT (~0.5ms per request), serialization overhead
- Pro: TTL-based expiration built in

**Layer 3: HTTP cache (CDN or reverse proxy)**
If the catalog page returns the same data for all users, cache the entire HTTP response.
- Pro: Requests never reach the app server at all
- Con: Invalidation is harder (purge CDN cache)
- Pro: Scales infinitely

**Layer 4: Database query cache (materialized view)**
PostgreSQL materialized view with periodic REFRESH.
- Pro: Simplifies application code
- Con: Still requires DB connection per request

**For this case, I'd recommend a multi-layer approach:**

1. **In-process cache with TTL** — serves 99% of requests
2. **Redis as fallback** — fills process cache after restart or TTL expiry
3. **Active invalidation on write** — when catalog changes, purge cache immediately

Actually, for 5 changes/day with 167 req/s, even a simple TTL of 60 seconds means:
- Max stale time: 60 seconds (acceptable for a product catalog)
- DB queries: once per minute per process (maybe 10 processes = 10 queries/minute vs 10,000)
- 99.9% cache hit rate

That's a 1000x reduction in DB load. For a product catalog, 60 seconds of staleness is almost always acceptable.

But we can do better: active invalidation. When the catalog is updated (5x/day), publish a cache invalidation event. All processes immediately clear their cache. This gives us:
- 0 seconds of staleness (on active invalidation)
- With TTL as a safety net (in case invalidation message is lost)

For the invalidation broadcast, Redis Pub/Sub is perfect. Each app process subscribes to a "cache_invalidation" channel. When the catalog is updated, publish a message. All subscribers clear their local cache.

Let me design this:

```
Write path (5x/day):
  Update DB → Publish invalidation to Redis Pub/Sub → All processes clear cache

Read path (167/s):
  Check in-memory cache → HIT: return (0ms)
                        → MISS: Check Redis → HIT: set in-memory, return (0.5ms)
                                            → MISS: Query DB, set both caches, return (200ms)
```

For the in-memory cache, I'll use `cachetools.TTLCache` or a simple dict with timestamp. For FastAPI specifically, I could use `lru_cache` but it doesn't support TTL natively.

Actually, let me think about cache stampede. When the TTL expires or cache is invalidated, all 167 concurrent requests will hit the DB simultaneously. That's a thundering herd.

Solutions:
1. **Lock-based recomputation**: Only one request recomputes, others wait
2. **Stale-while-revalidate**: Serve stale data while one request refreshes in background
3. **Probabilistic early expiration**: Each request has a small probability of refreshing before TTL, spreading the load

For 5 changes/day, stampede is minimal risk. But it's good practice to handle it. I'll use a simple async lock.
</think>

With 10K req/min and 5 changes/day, you can serve 99.99% of requests from memory with zero DB load.

### Architecture: Two-layer cache with active invalidation

```
Read path (167 requests/second):
  ┌────────────┐     ┌───────┐     ┌──────────┐
  │ In-memory  │────→│ Redis │────→│ PostgreSQL│
  │ (0.001ms)  │miss │(0.5ms)│miss │  (200ms)  │
  └────────────┘     └───────┘     └──────────┘
        ↑                                │
        └──── fill cache ────────────────┘

Write path (5 times/day):
  Update DB → Redis Pub/Sub → All processes clear in-memory cache
```

### Implementation

```python
import asyncio
import json
import time
from functools import wraps

import redis.asyncio as aioredis

# --- Cache layer ---

class CatalogCache:
    def __init__(self, redis_url: str = 'redis://localhost:6379'):
        self.redis = aioredis.from_url(redis_url)
        self._local: dict[str, tuple[float, any]] = {}  # key → (expires_at, data)
        self._locks: dict[str, asyncio.Lock] = {}
        self._ttl = 120  # 2 min TTL (safety net, invalidation is primary)

    async def get(self, key: str):
        """Two-layer lookup: in-memory → Redis → None."""
        # Layer 1: In-memory
        if key in self._local:
            expires_at, data = self._local[key]
            if time.monotonic() < expires_at:
                return data
            del self._local[key]

        # Layer 2: Redis
        raw = await self.redis.get(f'cache:{key}')
        if raw:
            data = json.loads(raw)
            self._local[key] = (time.monotonic() + self._ttl, data)
            return data

        return None

    async def set(self, key: str, data, ttl: int = None):
        """Write to both layers."""
        ttl = ttl or self._ttl
        self._local[key] = (time.monotonic() + ttl, data)
        await self.redis.setex(f'cache:{key}', ttl, json.dumps(data))

    async def invalidate(self, key: str):
        """Clear from both layers and notify other processes."""
        self._local.pop(key, None)
        await self.redis.delete(f'cache:{key}')
        await self.redis.publish('cache_invalidation', key)

    def clear_local(self, key: str):
        """Called when receiving invalidation from another process."""
        self._local.pop(key, None)

    def get_lock(self, key: str) -> asyncio.Lock:
        """Prevent cache stampede: only one request recomputes."""
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]


cache = CatalogCache()


# --- Pub/Sub listener (run on startup) ---

async def listen_for_invalidation():
    """Background task: clear local cache when other processes invalidate."""
    pubsub = cache.redis.pubsub()
    await pubsub.subscribe('cache_invalidation')
    async for message in pubsub.listen():
        if message['type'] == 'message':
            key = message['data'].decode()
            cache.clear_local(key)


@app.on_event('startup')
async def start_cache_listener():
    asyncio.create_task(listen_for_invalidation())


# --- Endpoints ---

@app.get('/api/catalog')
async def get_catalog(category: str = 'all'):
    cache_key = f'catalog:{category}'

    # Try cache first
    data = await cache.get(cache_key)
    if data is not None:
        return data

    # Cache miss: acquire lock to prevent stampede
    async with cache.get_lock(cache_key):
        # Double-check after acquiring lock (another request may have filled it)
        data = await cache.get(cache_key)
        if data is not None:
            return data

        # Query database
        data = await fetch_catalog_from_db(category)  # 200ms
        await cache.set(cache_key, data)
        return data


@app.put('/api/catalog/products/{product_id}')
async def update_product(product_id: int, product: ProductUpdate):
    await update_product_in_db(product_id, product)
    # Invalidate all catalog caches (simple approach for 5x/day)
    await cache.invalidate('catalog:all')
    for cat in await get_all_categories():
        await cache.invalidate(f'catalog:{cat}')
    return {'status': 'updated'}
```

### Performance impact

```
Before caching:
  10,000 req/min × 200ms DB time = 33 concurrent DB queries
  DB connection pool: needs 33+ connections
  P99 latency: 200ms+

After caching:
  DB queries: ~5/day (only on invalidation, +1/process on cold start)
  DB connection pool: 2-3 connections sufficient
  P99 latency: <1ms (in-memory hit)
  Cache hit rate: 99.99%
```

### Cache stampede protection explained

Without the lock, when the cache expires:
```
Request 1: cache miss → query DB (200ms)
Request 2: cache miss → query DB (200ms)  ← simultaneous
Request 3: cache miss → query DB (200ms)  ← 167 requests all hit DB
...
```

With the `asyncio.Lock`:
```
Request 1: cache miss → acquire lock → query DB → fill cache → release lock
Request 2: cache miss → wait for lock → lock acquired → cache HIT → return
Request 3: cache miss → wait for lock → lock acquired → cache HIT → return
```

Only one DB query instead of 167.

### When to add a CDN layer

If the catalog is the same for all users (no personalization), add HTTP caching:

```python
@app.get('/api/catalog')
async def get_catalog(category: str = 'all'):
    data = await get_cached_catalog(category)
    return JSONResponse(
        content=data,
        headers={
            'Cache-Control': 'public, max-age=60, stale-while-revalidate=300',
            'ETag': hashlib.md5(json.dumps(data).encode()).hexdigest(),
        }
    )
```

This offloads traffic to the CDN entirely. App servers only handle cache misses and writes.'''
    ),
]
