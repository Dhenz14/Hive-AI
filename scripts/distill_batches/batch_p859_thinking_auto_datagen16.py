"""Phase 4A: Self-Improvement -- Training Data Generation (Part 16)

Generate and evaluate training pairs for architecture decision topics.
Each answer creates 3 graded training pairs with quality analysis.
"""

PAIRS = [
    (
        "thinking/auto-datagen-arch-decision-monolith-vs-micro",
        r'''Generate 3 high-quality training pairs that teach how to make the monolith vs microservices decision for real projects. For each pair, explain why it's effective training data.''',
        r'''<think>
The monolith vs microservices decision is one of the most consequential architecture choices:
1. Most teams choose microservices for the wrong reasons
2. The decision depends on team size, complexity, and organizational structure
3. There is a spectrum, not a binary choice

Progression: understanding the trade-offs -> decision framework -> migration strategies
</think>

Here are 3 training pairs for monolith vs microservices decisions:

**Pair 1 (Beginner):**
```
Q: My team of 4 developers is starting a new SaaS product. Should we use microservices from the start? I hear that is the modern best practice.

A: **No. Start with a monolith.** Microservices are not a best practice -- they are a trade-off for a specific problem (large teams stepping on each other).

**Why a monolith is RIGHT for 4 developers:**

| Factor | Monolith | Microservices |
|--------|----------|--------------|
| Time to first feature | Days | Weeks (infrastructure first) |
| Deployment | One deploy | Coordinate N deploys |
| Debugging | One process, one log file | Distributed tracing across services |
| Database queries | Simple JOINs | Cross-service data fetching |
| Code sharing | Import a module | Publish a library or duplicate code |
| Infrastructure cost | $50/month | $300+/month (K8s, service mesh, etc.) |
| DevOps requirement | None (managed hosting) | Dedicated DevOps engineer |

**The real question to ask:**
"Do we have problems that microservices solve?"
- 50+ developers in one codebase? -> Microservices help
- Different components need different scaling? -> Microservices help
- Teams need to deploy independently? -> Microservices help
- None of the above? -> Monolith is correct

**Start here:**
```
Architecture: Monolith (Django/Rails/Next.js)
Database: PostgreSQL
Hosting: Render/Railway/Heroku
Deploy: git push
```

You can always extract microservices later when you have REAL problems to solve. You cannot un-microservice a premature architecture.
```

**Why this is effective:** Directly challenges the common misconception. The comparison table makes the cost concrete. The "real question to ask" framework is reusable.

**Pair 2 (Intermediate):**
```
Q: Our monolith is getting hard to work with. We have 30 developers and deployments are slow and risky. How do I decide which parts to extract into services?

A: **Extract services along team boundaries, not technical boundaries.**

**Wrong approach: Extract by technology layer**
```
DON'T do this:
  - API Gateway Service
  - Database Service
  - Authentication Service
  - Notification Service

Why it fails: Every feature change touches ALL services.
Adding "user notifications for new orders" requires changes to
the API, database, auth, and notification services.
```

**Right approach: Extract by business domain**
```
DO this:
  - Order Service (owned by the Orders team)
  - User Service (owned by the Platform team)
  - Billing Service (owned by the Payments team)

Why it works: Each service maps to a team. The team can
develop, test, and deploy independently.
```

**Decision framework -- extract when:**
```
Score each potential service 0-5:

1. Independent team?
   Does a dedicated team own this domain?
   0 = shared ownership, 5 = dedicated team

2. Independent deployment?
   Can this deploy without coordinating with other parts?
   0 = always deploys together, 5 = fully independent

3. Different scaling needs?
   Does this part need to scale differently?
   0 = scales with everything else, 5 = 10x different load

4. Different technology needs?
   Does this part benefit from a different language/runtime?
   0 = same tech is fine, 5 = fundamentally different requirement

5. Clear API boundary?
   Is there a clean interface between this and the rest?
   0 = deeply intertwined, 5 = already a clean module

Total score:
  0-10:  Keep in the monolith
  11-18: Consider extracting, but validate the boundary first
  19-25: Strong candidate for extraction
```

**Extraction order:** Start with the service that has the highest score AND the clearest boundary. Do NOT extract everything at once.
```

**Why this is effective:** The scoring framework is concrete and actionable. The wrong-vs-right approach examples prevent common mistakes. The emphasis on team boundaries reflects real industry experience.

**Pair 3 (Advanced):**
```
Q: We are migrating from a monolith to microservices. How do we do this without rewriting everything and without downtime?

A: Use the **Strangler Fig Pattern** -- gradually replace monolith functionality while both systems run in parallel:

```
Phase 1: Route through proxy
  Client -> [Proxy/Gateway] -> Monolith (handles everything)

Phase 2: Extract first service, proxy routes to both
  Client -> [Proxy/Gateway] -> New Service (handles /orders)
                             -> Monolith (handles everything else)

Phase 3: Continue extracting
  Client -> [Proxy/Gateway] -> Order Service
                             -> User Service
                             -> Monolith (shrinking)

Phase 4: Monolith is gone (or small enough to not matter)
  Client -> [Proxy/Gateway] -> Order Service
                             -> User Service
                             -> Billing Service
```

**Step-by-step extraction process:**

```
1. Add a reverse proxy in front of the monolith
   - All traffic goes through the proxy
   - The proxy forwards everything to the monolith
   - Zero behavior change (just a new routing layer)

2. Identify the first extraction candidate
   - Pick the domain with clearest boundaries
   - Pick something that is NOT in the critical path
   - Common first extractions: notifications, search, analytics

3. Build the new service alongside the monolith
   - New service handles the extracted domain
   - Both read from the same database initially (shared DB phase)
   - Proxy routes relevant traffic to the new service

4. Migrate the data
   - New service gets its own database
   - Sync data from monolith DB to service DB
   - Dual-write during migration (write to both)
   - Verify data consistency
   - Switch reads to the new database
   - Stop writing to the old database

5. Remove the old code from the monolith
   - Delete the code that the new service replaces
   - The monolith gets smaller with each extraction
```

**Critical rules:**
- Never do a "big bang" migration (rewrite everything at once)
- One service at a time, fully completed before starting the next
- Run both systems in parallel and compare outputs
- Always have a rollback plan (proxy can route back to monolith)
- Plan for 6-18 months for a significant migration
```

**Why this is effective:** Shows the complete migration strategy with a proven pattern name. The step-by-step process and critical rules prevent the most common migration disasters.'''
    ),
    (
        "thinking/auto-datagen-arch-decision-sync-vs-async",
        r'''Generate 3 high-quality training pairs that teach when to use synchronous vs asynchronous communication between system components. For each pair, explain why it's effective training data.''',
        r'''<think>
Sync vs async communication is a fundamental architecture decision:
1. Synchronous: request-response, simple but creates coupling
2. Asynchronous: message queues, decoupled but complex
3. The choice depends on consistency requirements and coupling tolerance

Progression: understanding the difference -> decision framework -> implementation patterns
</think>

Here are 3 training pairs for sync vs async architecture decisions:

**Pair 1 (Beginner):**
```
Q: What is the difference between synchronous and asynchronous communication between services? When should I use each?

A: **Synchronous** = caller WAITS for a response. **Asynchronous** = caller sends a message and continues.

```
SYNCHRONOUS (HTTP/RPC):
  Order Service --[HTTP POST /charge]--> Payment Service
  Order Service <--[200 OK, charged]---- Payment Service
  Order Service continues...

  The Order Service is BLOCKED until Payment Service responds.
  If Payment Service is slow (5s), Order Service waits 5s.
  If Payment Service is down, Order Service fails.

ASYNCHRONOUS (Message Queue):
  Order Service --[publish "charge" event]--> Message Queue
  Order Service continues immediately...

  ...later...

  Payment Service <--[consume "charge" event]-- Message Queue
  Payment Service processes the charge
  Payment Service --[publish "charged" event]--> Message Queue
```

**When to use each:**
| Scenario | Use sync | Use async |
|----------|---------|-----------|
| User is waiting for a response | YES | No |
| Need immediate confirmation | YES | No |
| Background processing | No | YES |
| High-volume event processing | No | YES |
| Service might be temporarily down | No | YES (queue buffers) |
| Simple request-response | YES | No (overkill) |
| Fan-out to multiple consumers | No | YES |

**Examples:**
- User login: SYNC (user needs immediate yes/no)
- Send welcome email: ASYNC (user does not wait for email delivery)
- Process payment: SYNC (user needs confirmation before showing receipt)
- Update search index: ASYNC (eventual consistency is fine)
- Generate PDF report: ASYNC (takes minutes, notify user when done)
```

**Why this is effective:** Clear visual diagrams, a decision table with common scenarios, and concrete examples the learner can map to their own projects.

**Pair 2 (Intermediate):**
```
Q: I am building an e-commerce checkout flow. Which parts should be synchronous and which should be asynchronous?

A: Split by what the USER needs to see immediately vs what can happen in the background:

```
CHECKOUT FLOW:

Step 1: Validate cart (SYNC)
  Why: User needs to know immediately if items are available.
  Pattern: HTTP call to Inventory Service
  Failure: Show "item out of stock" immediately

Step 2: Process payment (SYNC)
  Why: User needs payment confirmation before seeing "order placed."
  Pattern: HTTP call to Payment Service
  Failure: Show "payment declined" immediately

Step 3: Create order record (SYNC)
  Why: Need the order ID to show the confirmation page.
  Pattern: Direct database write
  Failure: Show error, refund payment

--- Everything below here is ASYNC ---

Step 4: Send confirmation email (ASYNC)
  Why: User does not wait for email delivery.
  Pattern: Publish OrderCreated event -> Email Service consumes

Step 5: Update inventory counts (ASYNC)
  Why: Eventual consistency is acceptable for display counts.
  Pattern: Publish OrderCreated event -> Inventory Service consumes

Step 6: Notify warehouse (ASYNC)
  Why: Warehouse picks items hours later.
  Pattern: Publish OrderCreated event -> Warehouse Service consumes

Step 7: Update analytics (ASYNC)
  Why: Analytics can be seconds behind.
  Pattern: Publish OrderCreated event -> Analytics Service consumes

Step 8: Fraud check (ASYNC with callback)
  Why: Can run in background, flag suspicious orders.
  Pattern: Publish OrderCreated -> Fraud Service -> may publish OrderFlagged
```

**Architecture diagram:**
```
User -> [API Gateway]
         |
         |-- SYNC --> Inventory Service (validate stock)
         |-- SYNC --> Payment Service (charge card)
         |-- SYNC --> Order DB (create record)
         |
         |-- ASYNC --> Message Queue
                        |-- Email Service
                        |-- Inventory Update
                        |-- Warehouse Notification
                        |-- Analytics
                        |-- Fraud Detection
```

**The boundary:** Everything the user SEES is sync. Everything that happens AFTER the confirmation page is async.
```

**Why this is effective:** Uses a universally understood scenario (checkout) to show exactly where to draw the sync/async boundary. The principle ("everything the user sees is sync") is a general rule the learner can apply elsewhere.

**Pair 3 (Advanced):**
```
Q: We switched to async messaging between services but now we have problems: messages arrive out of order, some are processed twice, and it is hard to debug. How do I fix these issues?

A: These are the three classic problems of async messaging. Here are the solutions:

**Problem 1: Out-of-order messages**
```
Cause: Multiple consumers process messages concurrently.
Message A (sent first) might be processed AFTER message B.

Solution 1: Sequence numbers
  Each message includes a monotonic sequence number.
  Consumer tracks the last processed sequence per entity.

  message = {
      "entity_id": "order-123",
      "sequence": 5,
      "event": "order_updated",
      "data": {...}
  }

  Consumer:
    last_seen = get_last_sequence("order-123")  # Returns 4
    if message.sequence <= last_seen:
        skip()  # Already processed or out of order
    else:
        process(message)
        set_last_sequence("order-123", message.sequence)

Solution 2: Partition by entity
  Route all messages for the same entity to the same partition/consumer.
  Kafka does this naturally with partition keys:

  producer.send("orders", key="order-123", value=event)
  # All events for order-123 go to the same partition -> processed in order
```

**Problem 2: Duplicate messages (at-least-once delivery)**
```
Cause: Message broker redelivers if consumer does not acknowledge in time.

Solution: Idempotent consumers
  Make processing the same message twice produce the same result.

  # BAD: Not idempotent
  def handle_payment(event):
      charge_customer(event.amount)  # Charges AGAIN on redelivery!

  # GOOD: Idempotent with deduplication
  def handle_payment(event):
      if already_processed(event.message_id):
          return  # Skip duplicate

      charge_customer(event.amount)
      mark_processed(event.message_id)  # Record in database

  # Implementation:
  CREATE TABLE processed_events (
      message_id UUID PRIMARY KEY,
      processed_at TIMESTAMPTZ DEFAULT NOW()
  );

  # In a transaction:
  BEGIN;
  INSERT INTO processed_events (message_id) VALUES (:msg_id)
      ON CONFLICT DO NOTHING;
  -- If insert succeeded, process the event
  -- If conflict (duplicate), skip
  COMMIT;
```

**Problem 3: Hard to debug**
```
Cause: No way to trace a request through multiple async hops.

Solution: Correlation IDs + event sourcing

  Every message carries a correlation_id from the original request:

  message = {
      "correlation_id": "req-abc-123",  # Original request ID
      "causation_id": "evt-456",        # Event that caused this one
      "message_id": "evt-789",          # This message's unique ID
      "event": "order_shipped",
      "data": {...}
  }

  Debugging: search all logs and events for correlation_id = "req-abc-123"

  Timeline reconstruction:
  14:23:01 [req-abc-123] API: POST /orders (causation: user click)
  14:23:02 [req-abc-123] OrderCreated (causation: API request)
  14:23:03 [req-abc-123] PaymentCharged (causation: OrderCreated)
  14:23:04 [req-abc-123] InventoryReserved (causation: OrderCreated)
  14:23:10 [req-abc-123] EmailSent (causation: OrderCreated)
  14:25:00 [req-abc-123] OrderShipped (causation: warehouse scan)
```

**Summary:**
| Problem | Solution | Trade-off |
|---------|----------|-----------|
| Out of order | Sequence numbers or partitioning | More complexity in consumer |
| Duplicates | Idempotent consumers | Need dedup storage |
| Hard to debug | Correlation IDs | More metadata per message |
```

**Why this is effective:** Addresses the three exact problems developers hit when adopting async messaging. Each solution is practical and includes implementation details, not just theory.'''
    ),
    (
        "thinking/auto-datagen-arch-decision-caching-strategy",
        r'''Generate 3 high-quality training pairs that teach caching architecture decisions: what to cache, where to cache, and how to handle cache invalidation. For each pair, explain why it's effective training data.''',
        r'''<think>
Caching is powerful but frequently misapplied:
1. "Cache everything" is not a strategy
2. Cache invalidation is the hard part
3. Multiple caching layers serve different purposes

Progression: deciding what to cache -> cache invalidation strategies -> multi-layer caching
</think>

Here are 3 training pairs for caching architecture decisions:

**Pair 1 (Beginner):**
```
Q: My API is slow and I want to add caching. Where do I start? What should I cache and what should I NOT cache?

A: **Cache the result of expensive operations that are read frequently and change rarely.**

**Decision matrix:**
| Data characteristic | Cache? | Why |
|--------------------|--------|-----|
| Read 100x, written 1x | YES | High read-to-write ratio |
| Changes every request | NO | Cache would always be stale |
| Expensive to compute (>100ms) | YES | Save computation time |
| Cheap to compute (<5ms) | NO | Caching overhead exceeds benefit |
| Same result for all users | YES | One cache entry serves everyone |
| Different per user | MAYBE | Cache per user, more memory |
| Must be 100% current | NO | Any staleness is unacceptable |
| Can be 30 seconds stale | YES | Short TTL is fine |

**Common things to cache:**
```python
# 1. Database query results (most common)
@cache(ttl=300)  # 5 minutes
def get_product_list(category):
    return db.query("SELECT * FROM products WHERE category = %s", category)

# 2. External API responses
@cache(ttl=3600)  # 1 hour
def get_exchange_rate(currency):
    return requests.get(f"https://api.exchange.com/rate/{currency}").json()

# 3. Computed results
@cache(ttl=60)  # 1 minute
def get_dashboard_stats():
    return {
        "total_users": db.count("users"),
        "revenue_today": db.sum("orders", "total", where="date = today"),
        "active_sessions": redis.scard("active_sessions"),
    }
```

**Things to NEVER cache:**
- Authentication/authorization results (security risk)
- Write operations (double-processing risk)
- User-specific data with privacy concerns
- Rapidly changing data (stock prices, live scores)
- Data that MUST be consistent (account balances)
```

**Why this is effective:** The decision matrix gives a clear framework. The examples show the most common (and correct) caching targets. The "never cache" list prevents dangerous mistakes.

**Pair 2 (Intermediate):**
```
Q: How do I handle cache invalidation? I keep getting bugs where users see stale data after making changes.

A: Cache invalidation is the hardest problem in caching. Here are the strategies:

**Strategy 1: Time-based expiration (TTL)**
```python
# Simplest: data expires after N seconds
cache.set("product:123", product_data, ttl=300)  # Expires in 5 minutes

# Pro: Simple, no invalidation logic needed
# Con: Data can be stale for up to TTL seconds
# Use when: Staleness is acceptable (dashboards, listings)
```

**Strategy 2: Write-through (invalidate on write)**
```python
# Delete cache when data changes
def update_product(product_id, new_data):
    db.update("products", product_id, new_data)
    cache.delete(f"product:{product_id}")  # Invalidate
    # Next read will miss cache and re-populate from DB

# Pro: Data is never stale after a write
# Con: Must invalidate in EVERY code path that writes
# Danger: Miss one write path and you have stale data
```

**Strategy 3: Write-behind (update cache on write)**
```python
# Update both cache and DB on every write
def update_product(product_id, new_data):
    db.update("products", product_id, new_data)
    cache.set(f"product:{product_id}", new_data, ttl=300)

# Pro: Cache is immediately up to date
# Con: Cache and DB can get out of sync if one fails
```

**Strategy 4: Event-driven invalidation**
```python
# Publish an event when data changes; cache subscriber invalidates
def update_product(product_id, new_data):
    db.update("products", product_id, new_data)
    event_bus.publish("product.updated", {"id": product_id})

# Cache invalidation subscriber:
@event_bus.subscribe("product.updated")
def invalidate_product_cache(event):
    product_id = event["id"]
    cache.delete(f"product:{product_id}")
    cache.delete(f"product_list:{get_category(product_id)}")
    cache.delete("featured_products")  # Any cache that includes this product
```

**The cache invalidation checklist:**
```
For EVERY cache key, answer:
1. What writes should invalidate this cache?
2. Are there indirect writes? (e.g., deleting a product should
   invalidate the category listing cache)
3. What happens if invalidation fails? (TTL as safety net)
4. Can you test that invalidation works?

Golden rule: Always set a TTL even with active invalidation.
If your invalidation has a bug, TTL ensures data is eventually fresh.
```
```

**Why this is effective:** Shows all four strategies with clear pros/cons. The checklist prevents the most common invalidation bugs. The golden rule (always set TTL) is a safety net the learner should always apply.

**Pair 3 (Advanced):**
```
Q: We have caching at multiple levels (browser, CDN, application, database). How do I design a coherent multi-layer caching strategy?

A: Design caching from the outside in, with each layer serving a different purpose:

```
Layer 1: Browser Cache (closest to user)
  What: Static assets (JS, CSS, images), API responses
  TTL: Long for assets (1 year with cache-busting), short for API (30s-5min)
  Control: Cache-Control headers
  Invalidation: Change the URL (app.abc123.js)

Layer 2: CDN Cache (edge servers worldwide)
  What: Public pages, static content, public API responses
  TTL: 1 minute to 1 hour
  Control: Cache-Control, Surrogate-Control headers
  Invalidation: Purge API or surrogate keys

Layer 3: Application Cache (Redis/Memcached)
  What: Database query results, computed data, session data
  TTL: 30 seconds to 30 minutes
  Control: Application code
  Invalidation: Event-driven + TTL fallback

Layer 4: Database Cache (query cache, buffer pool)
  What: Recently accessed rows and index pages
  TTL: Automatic (LRU eviction)
  Control: Database configuration
  Invalidation: Automatic on write
```

**Request flow:**
```
User request for /api/products?category=electronics

1. Browser cache: HIT? Return cached response (0ms)
2. CDN cache: HIT? Return cached response (10ms)
3. Application cache (Redis): HIT? Return cached data (1ms)
4. Database query cache: HIT? Return cached result (2ms)
5. Database disk: Execute query (50-500ms)

Each cache miss "falls through" to the next layer.
```

**Configuration example:**
```python
# Layer 1: Browser cache headers
@app.route("/api/products")
def get_products():
    products = fetch_products(request.args.get("category"))
    response = jsonify(products)
    response.headers["Cache-Control"] = "public, max-age=60"  # Browser: 60s
    response.headers["Surrogate-Control"] = "max-age=300"     # CDN: 5min
    response.headers["Surrogate-Key"] = "products"            # CDN purge key
    return response

# Layer 2: CDN purge on data change
def invalidate_product_caches():
    # Purge CDN by surrogate key
    cdn_client.purge_by_key("products")

# Layer 3: Redis cache in application
PRODUCT_CACHE_TTL = 120  # 2 minutes

def fetch_products(category):
    cache_key = f"products:{category}"
    cached = redis.get(cache_key)
    if cached:
        return json.loads(cached)

    products = db.query("SELECT ... WHERE category = %s", category)
    redis.setex(cache_key, PRODUCT_CACHE_TTL, json.dumps(products))
    return products

# Invalidation cascade on product update:
def on_product_updated(product_id):
    category = get_product_category(product_id)
    # Layer 3: Invalidate Redis
    redis.delete(f"products:{category}")
    redis.delete(f"product:{product_id}")
    # Layer 2: Purge CDN
    cdn_client.purge_by_key("products")
    # Layer 1: Browser will refetch after max-age expires (60s)
```

**Consistency vs performance trade-off:**
| Layer | Latency | Staleness tolerance | Invalidation control |
|-------|---------|-------------------|---------------------|
| Browser | 0ms | 30-60s OK | Cannot force (must wait for TTL) |
| CDN | 10ms | 1-5min OK | Purge API available |
| Application (Redis) | 1ms | 30s-2min OK | Full control (delete key) |
| Database | 2-500ms | 0s (authoritative) | Automatic |

**Key insight:** Each layer trades freshness for speed. The closer to the user, the faster but potentially more stale. Design your TTLs so that the maximum staleness at each layer is acceptable for your use case.
```

**Why this is effective:** Shows the complete multi-layer caching architecture with configuration code for each layer. The invalidation cascade demonstrates how changes propagate outward. The trade-off table helps the learner reason about TTL choices.'''
    ),
    (
        "thinking/auto-datagen-arch-decision-api-design",
        r'''Generate 3 high-quality training pairs that teach API design decisions: REST vs GraphQL vs gRPC, versioning strategies, and pagination patterns. For each pair, explain why it's effective training data.''',
        r'''<think>
API design decisions have long-lasting consequences:
1. The right API style depends on clients, team, and use case
2. Versioning strategy prevents breaking changes
3. Pagination is consistently done wrong in tutorials

Progression: choosing API style -> versioning -> pagination patterns
</think>

Here are 3 training pairs for API design decisions:

**Pair 1 (Beginner):**
```
Q: When should I use REST vs GraphQL vs gRPC? I keep hearing different opinions.

A: Each is designed for a different scenario:

**REST (HTTP + JSON)**
```
Best for: Public APIs, web applications, simple CRUD
Strengths: Simple, cacheable, universally understood, great tooling
Weaknesses: Over-fetching/under-fetching, multiple round trips

Example:
  GET /api/users/42          -> User data
  GET /api/users/42/orders   -> User's orders (second request)
```

**GraphQL**
```
Best for: Complex UIs with varied data needs, mobile apps, multiple clients
Strengths: Client gets exactly what it needs, one request, strong typing
Weaknesses: Complex server implementation, no HTTP caching, N+1 problem

Example:
  POST /graphql
  { user(id: 42) { name, orders { id, total } } }
  -> User data + orders in ONE request
```

**gRPC (Protocol Buffers)**
```
Best for: Internal service-to-service communication, high performance
Strengths: Fast (binary protocol), streaming, code generation, strong contracts
Weaknesses: Not browser-friendly, requires tooling, harder to debug

Example:
  UserService.GetUser(UserRequest{id: 42}) -> UserResponse
```

**Decision matrix:**
| Scenario | Best choice | Why |
|----------|-------------|-----|
| Public API for third parties | REST | Universally understood, easy to use |
| Internal microservice communication | gRPC | Fast, typed contracts, streaming |
| Mobile app with complex UI | GraphQL | Minimizes data transfer, one request |
| Simple web app CRUD | REST | Simple, well-supported by frameworks |
| Real-time streaming data | gRPC | Bidirectional streaming built in |
| Multiple client types (web, mobile, IoT) | GraphQL | Each client requests what it needs |
| Team of 1-3 developers | REST | Lowest complexity |
```

**Why this is effective:** Direct comparison with concrete examples and a clear decision matrix. Avoids the common mistake of recommending one style for everything.

**Pair 2 (Intermediate):**
```
Q: How should I version my REST API? I need to make breaking changes but I have existing clients depending on the current version.

A: There are three main approaches. Choose based on your client situation:

**Approach 1: URL versioning (most common, simplest)**
```
GET /api/v1/users/42
GET /api/v2/users/42

Pros: Obvious, easy to implement, easy to test
Cons: URL changes, harder to sunset old versions

Implementation:
  # Flask
  @app.route("/api/v1/users/<int:id>")
  def get_user_v1(id): ...

  @app.route("/api/v2/users/<int:id>")
  def get_user_v2(id): ...

  # Or with blueprints:
  v1 = Blueprint("v1", __name__, url_prefix="/api/v1")
  v2 = Blueprint("v2", __name__, url_prefix="/api/v2")
```

**Approach 2: Header versioning**
```
GET /api/users/42
Accept: application/vnd.myapi.v2+json

Pros: Clean URLs, content negotiation
Cons: Harder to test (need to set headers), less discoverable
```

**Approach 3: Additive changes only (no versioning)**
```
Never remove or rename fields. Only ADD new fields.
Old clients ignore new fields. New clients use new fields.

v1 response: {"name": "Alice", "email": "alice@example.com"}
v2 response: {"name": "Alice", "email": "alice@example.com",
              "display_name": "Alice W.", "avatar_url": "..."}

Pros: No version management, one codebase
Cons: Cannot change existing field types or semantics
```

**Recommendation:**
```
For most teams: URL versioning (v1, v2)
  - Only create v2 when you have BREAKING changes
  - Keep v1 running for at least 6 months after v2 launch
  - Document the migration path from v1 to v2
  - Log v1 usage to know when it is safe to deprecate

For internal APIs: Additive changes (no versioning)
  - You control all clients
  - Coordinate breaking changes with client teams
  - Deploy client and server together

Deprecation header:
  Sunset: Sat, 01 Mar 2025 00:00:00 GMT
  Deprecation: true
  Link: <https://docs.api.com/migration-v2>; rel="successor-version"
```
```

**Why this is effective:** Shows all three approaches with implementation details. The recommendation section gives clear guidance based on the common case. The deprecation headers are a practical detail most tutorials skip.

**Pair 3 (Advanced):**
```
Q: What is the best pagination pattern for an API? I am using OFFSET/LIMIT but it gets slow with large datasets and skips/duplicates records when data changes.

A: OFFSET pagination has fundamental problems. Here are the alternatives:

**Problem with OFFSET/LIMIT:**
```sql
-- Page 1: SELECT * FROM posts ORDER BY created_at DESC LIMIT 20 OFFSET 0
-- Page 2: SELECT * FROM posts ORDER BY created_at DESC LIMIT 20 OFFSET 20

-- Problem 1: SLOW on large offsets
-- OFFSET 1000000 means the database reads 1,000,000 rows and throws them away

-- Problem 2: Inconsistent results
-- If a new post is inserted while paginating,
-- items shift and you either skip or duplicate an item
```

**Solution 1: Cursor-based pagination (recommended)**
```python
# Use the last item's sort key as a cursor
# GET /api/posts?limit=20
{
    "data": [...20 posts...],
    "pagination": {
        "next_cursor": "eyJjcmVhdGVkX2F0IjoiMjAyNC0wMy0xNVQxNDoyMzowMVoiLCJpZCI6MTIzNH0=",
        "has_more": True
    }
}

# GET /api/posts?limit=20&cursor=eyJj...
# Decodes to: created_at < '2024-03-15T14:23:01Z' OR (created_at = '...' AND id < 1234)

# SQL:
SELECT * FROM posts
WHERE (created_at, id) < (:cursor_created_at, :cursor_id)
ORDER BY created_at DESC, id DESC
LIMIT 21;  -- Fetch 21 to know if there are more

# Implementation:
import base64, json

def encode_cursor(post):
    data = {"created_at": post.created_at.isoformat(), "id": post.id}
    return base64.b64encode(json.dumps(data).encode()).decode()

def decode_cursor(cursor):
    return json.loads(base64.b64decode(cursor.encode()).decode())
```

**Pros:** Fast at any depth, no skipped/duplicate items, works with real-time data
**Cons:** Cannot jump to page N, must traverse sequentially

**Solution 2: Keyset pagination (cursor without encoding)**
```python
# Expose the sort values directly
# GET /api/posts?limit=20&after_id=1234&after_date=2024-03-15

# Simpler but exposes internal IDs
```

**When to use which:**
| Pattern | Best for | Avoid when |
|---------|---------|------------|
| OFFSET/LIMIT | Small datasets (<10K rows), admin UIs with page numbers | Large datasets, user-facing feeds |
| Cursor-based | Feeds, timelines, real-time data, large datasets | Users need "go to page 47" |
| Keyset | Simple APIs where exposing IDs is OK | Public APIs (leaks internal structure) |

**API response format (industry standard):**
```json
{
    "data": [...],
    "pagination": {
        "next_cursor": "abc123",
        "previous_cursor": "xyz789",
        "has_more": true,
        "total_count": 15420
    }
}
```
Note: `total_count` is optional and expensive on large tables (requires COUNT(*) query). Include only if the UI needs it.
```

**Why this is effective:** Explains WHY OFFSET/LIMIT fails with concrete scenarios. Shows the complete implementation of cursor pagination including SQL, encoding, and API response format. The comparison table helps the learner choose the right pattern.'''
    ),
    (
        "thinking/auto-datagen-arch-decision-event-driven",
        r'''Generate 3 high-quality training pairs that teach when to use event-driven architecture versus request-response, and how to design event schemas. For each pair, explain why it's effective training data.''',
        r'''<think>
Event-driven architecture decisions are critical:
1. Not every system benefits from events
2. Event schema design determines long-term maintainability
3. Ordering, deduplication, and schema evolution are common pitfalls

Progression: when to use events -> designing event schemas -> handling event evolution
</think>

Here are 3 training pairs for event-driven architecture decisions:

**Pair 1 (Beginner):**
```
Q: What is event-driven architecture and when should I use it instead of direct API calls between services?

A: In event-driven architecture, services communicate by publishing and subscribing to events instead of calling each other directly.

**Direct API calls (request-response):**
```
Order Service --[POST /charge]--> Payment Service
Order Service <--[200 OK]-------- Payment Service
Order Service --[POST /ship]----> Shipping Service
Order Service <--[200 OK]-------- Shipping Service
Order Service --[POST /send]----> Email Service
Order Service <--[200 OK]-------- Email Service

Problem: Order Service KNOWS about all downstream services.
Adding a new service means changing Order Service code.
If Email Service is slow, Order Service is slow.
```

**Event-driven:**
```
Order Service --[publish OrderPlaced]--> Event Bus
                                          |
                     Payment Service <----+  (subscribes to OrderPlaced)
                     Shipping Service <---+  (subscribes to OrderPlaced)
                     Email Service <------+  (subscribes to OrderPlaced)
                     Analytics Service <--+  (subscribes to OrderPlaced)

Order Service does NOT know who is listening.
Adding Analytics Service requires ZERO changes to Order Service.
If Email Service is slow, Order Service is unaffected.
```

**Decision guide:**
| Scenario | Use events | Use direct calls |
|----------|-----------|-----------------|
| Multiple consumers need the same data | YES | No |
| Producer should not wait for consumer | YES | No |
| User needs immediate response | No | YES |
| Adding new consumers frequently | YES | No |
| Simple request-response | No | YES |
| Need guaranteed delivery order | Depends | YES (simpler) |
| Debugging must be straightforward | No (harder to trace) | YES |
```

**Why this is effective:** Clear visual comparison of both approaches. The decision guide gives specific criteria instead of vague recommendations.

**Pair 2 (Intermediate):**
```
Q: How should I design event schemas? What information should an event contain?

A: Good event schema design prevents painful migrations later.

**Two approaches:**

**Thin events (notification style):**
```json
{
    "event_type": "OrderPlaced",
    "order_id": "ord-123",
    "timestamp": "2024-03-15T14:23:01Z"
}
```
Consumer must call back to Order Service to get order details.
Pro: Small messages, always up-to-date data.
Con: Requires callback API, creates coupling.

**Fat events (self-contained):**
```json
{
    "event_type": "OrderPlaced",
    "event_id": "evt-456",
    "timestamp": "2024-03-15T14:23:01Z",
    "data": {
        "order_id": "ord-123",
        "customer_id": "cust-42",
        "items": [
            {"product_id": "prod-1", "name": "Widget", "quantity": 2, "price_cents": 1999}
        ],
        "total_cents": 3998,
        "shipping_address": {"city": "Portland", "state": "OR", "country": "US"}
    },
    "metadata": {
        "correlation_id": "req-abc-123",
        "source": "order-service",
        "version": "1.2"
    }
}
```
Consumer has everything it needs. No callback required.
Pro: Fully decoupled, consumers work independently.
Con: Larger messages, data might be stale if re-processed later.

**Recommended: Fat events for most cases.**

**Event schema best practices:**
1. Include event_id (for deduplication)
2. Include timestamp (for ordering)
3. Include correlation_id (for tracing)
4. Include version (for schema evolution)
5. Use past tense for event names (OrderPlaced, not PlaceOrder)
6. Include enough data that consumers do not need callbacks
7. Never include sensitive data (passwords, full credit card numbers)
```

**Why this is effective:** Shows both approaches with a clear recommendation. The best practices list is a concrete checklist the learner can apply immediately.

**Pair 3 (Advanced):**
```
Q: How do I handle event schema evolution? We need to add new fields and change the structure of our events without breaking existing consumers.

A: Event schema evolution is one of the hardest problems in event-driven systems:

**Rule 1: Only make backward-compatible changes**
```
SAFE changes (backward compatible):
  - Add a new optional field
  - Add a new event type
  - Add a new value to an enum

BREAKING changes (avoid):
  - Remove a field
  - Rename a field
  - Change a field's type
  - Change the meaning of a field
```

**Strategy 1: Additive-only schema evolution**
```json
// Version 1:
{"event_type": "OrderPlaced", "order_id": "123", "total": 50}

// Version 2 (new field added):
{"event_type": "OrderPlaced", "order_id": "123", "total": 50, "currency": "USD"}

// Old consumers ignore "currency" (they do not know about it).
// New consumers use "currency" with a default fallback.
```

**Strategy 2: Versioned events**
```json
// Publish both versions during migration:
{"event_type": "OrderPlaced", "version": 1, "order_id": "123", "total": 50}
{"event_type": "OrderPlaced", "version": 2, "order_id": "123", "total_cents": 5000, "currency": "USD"}

// Consumer:
def handle_order_placed(event):
    if event["version"] == 1:
        total_cents = event["total"] * 100  # Convert old format
        currency = "USD"  # Assume default
    elif event["version"] == 2:
        total_cents = event["total_cents"]
        currency = event["currency"]
```

**Strategy 3: Schema registry**
```
Use a schema registry (Confluent, AWS Glue) to:
1. Register every event schema version
2. Validate events against the schema before publishing
3. Check backward compatibility before registering a new version
4. Auto-reject breaking changes

This prevents breaking changes from reaching consumers.
```

**Migration timeline for breaking changes:**
```
Week 1: Add new field alongside old field (dual-write)
Week 2: Migrate all consumers to read new field
Week 3: Verify no consumer reads old field (check logs)
Week 4: Stop writing old field
Week 8: Remove old field from schema
```

**The golden rule:** Treat event schemas like public APIs -- you can add, but you cannot remove or change.
```

**Why this is effective:** Shows the complete lifecycle of schema evolution with three strategies at different complexity levels. The migration timeline gives a concrete process for breaking changes when they are unavoidable.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
