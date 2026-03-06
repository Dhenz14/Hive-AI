"""Phase 2A: Advanced Reasoning — Backtracking & Dead-End Recovery (Part 2/5)
Concurrency lock fails → lock-free, regex fails → parser, big bang migration fails → strangler fig."""

PAIRS = [
    (
        "thinking/backtrack-lock-fails-lockfree",
        "We have a high-throughput counter service (100K increments/second). We used a mutex to protect the counter, but lock contention is killing performance — threads spend more time waiting than working. How do we fix this?",
        r'''<think>
Let me analyze the problem. 100K increments per second with mutex protection:

Each increment:
1. Acquire lock (may block if contended)
2. Read counter
3. Increment
4. Write counter
5. Release lock

With 100K ops/sec across multiple threads, the lock becomes a serial bottleneck. Even if the critical section is fast (nanoseconds), the lock acquisition and cache line bouncing between cores dominates.

My first thought was "use a read-write lock" — but that doesn't help here because ALL operations are writes.

Second thought: "shard the counter across multiple locks" — each thread increments a local counter, periodically merge. This reduces contention but adds complexity for reading the total.

Wait — for a simple counter, there's a much better approach: atomic operations. CAS (Compare-And-Swap) provides lock-free increment:

```
loop:
  old = counter.load()
  new = old + 1
  if counter.CAS(old, new): break
  else: retry (someone else incremented)
```

This is lock-free because:
- No thread ever blocks waiting for a lock
- If two threads race, one succeeds and one retries
- Under high contention, retries increase but no thread starves

But even atomics can have contention on a single cache line. For extreme throughput, I should mention the sharded counter approach too.

Let me compare:
- Mutex: O(1) per op, but serialized → throughput limited by lock overhead
- Atomic CAS: O(1) per op, lock-free → much higher throughput
- Sharded counter: O(1) per op, almost zero contention → highest throughput, reads are O(shards)

For 100K ops/sec, atomic CAS should be sufficient. Sharded counters for millions/sec.
</think>

For a simple counter at 100K ops/sec, **atomic operations** eliminate lock contention entirely. No mutex needed.

**Why mutex fails at high throughput**:
```python
import threading

counter = 0
lock = threading.Lock()

def increment():
    global counter
    with lock:  # Threads queue up here — serial bottleneck
        counter += 1

# 100K calls/sec × 8 threads = massive lock contention
# Threads spend 90%+ time waiting for the lock
```

**Fix 1: Atomic operations (best for simple counters)**:
```python
import ctypes
import threading

class AtomicCounter:
    """Lock-free counter using atomic increment."""
    def __init__(self):
        self._value = ctypes.c_long(0)
        self._lock = threading.Lock()  # Only for Python; in C/Rust, use std::atomic

    def increment(self) -> int:
        # In Python, we need a lock due to GIL limitations,
        # but in languages with real atomics:
        # return atomic_fetch_add(&self._value, 1)
        with self._lock:
            self._value.value += 1
            return self._value.value

# For TRUE lock-free in Python, use multiprocessing.Value
from multiprocessing import Value

shared_counter = Value('l', 0)  # 'l' = signed long

def increment_atomic():
    with shared_counter.get_lock():  # Hardware-level atomic in shared memory
        shared_counter.value += 1
```

**Fix 2: Sharded counter (for extreme throughput — millions/sec)**:
```python
import threading
from collections import defaultdict

class ShardedCounter:
    """Near-zero contention via per-thread sharding."""
    def __init__(self):
        self._shards: dict[int, int] = defaultdict(int)
        self._shard_locks: dict[int, threading.Lock] = defaultdict(threading.Lock)

    def increment(self):
        tid = threading.get_ident()
        # Each thread hits its own shard — no cross-thread contention
        with self._shard_locks[tid]:
            self._shards[tid] += 1

    def value(self) -> int:
        # Reading is O(shards) — acceptable for metrics/reporting
        return sum(self._shards.values())
```

**Performance comparison**:
```
Approach        | 8 threads, 100K ops/sec | Throughput
----------------|------------------------|----------
Mutex           | Heavy contention        | ~50K ops/sec
Atomic CAS      | Minimal contention      | ~500K ops/sec
Sharded counter | Zero contention         | ~2M ops/sec
```

**When to use each**:
- **Mutex**: Complex critical sections (multiple fields, invariants between them)
- **Atomic**: Single-value updates (counters, flags, pointers)
- **Sharded**: Extreme throughput where reads are infrequent (metrics, analytics)'''
    ),
    (
        "thinking/backtrack-regex-fails-parser",
        "I'm trying to parse nested HTML-like template tags: `{if condition}{nested {variable}}{/if}`. My regex keeps failing on nested braces. Each fix creates new edge cases.",
        r'''<think>
This is a classic case where regex fundamentally cannot solve the problem. Let me think about why.

Regular expressions can match regular languages (Type 3 in the Chomsky hierarchy). Nested/balanced structures like `{if}{nested {var}}{/if}` require a context-free grammar (Type 2). Regex can't count nesting depth — it has no "stack."

Some regex engines support recursive patterns (`(?R)` in PCRE), but even those become unmaintainable and fragile with real template syntax.

The user's progression probably looks like:
1. `\{[^}]+\}` — fails on `{nested {var}}`
2. `\{.*?\}` — non-greedy, still fails on nesting
3. `\{(?:[^{}]|\{[^{}]*\})*\}` — handles 1 level of nesting, fails on 2
4. Add more levels → regex is now 200 chars and handles 3 levels but not 4

Each fix adds complexity for one more nesting level, but the fundamental problem remains: regex can't handle ARBITRARY nesting depth.

The right approach: write a simple recursive descent parser. For this template language, it's actually quite straightforward:
1. Tokenize: scan for `{`, `}`, `{if`, `{/if}`, `{variable}`
2. Parse: recursively handle nesting
3. Evaluate: walk the AST

Let me show a clean implementation.
</think>

Regex **cannot** parse nested structures — this is a mathematical limitation, not a skill issue. Nested braces require a stack, and regex has no stack. Each "fix" just handles one more nesting level.

**The regex death spiral you're in**:
```python
# Attempt 1: Breaks on {nested {var}}
r'\{[^}]+\}'

# Attempt 2: Non-greedy, still wrong on nesting
r'\{.*?\}'

# Attempt 3: Handles 1 level of nesting, fails on 2
r'\{(?:[^{}]|\{[^{}]*\})*\}'

# Attempt 4: 2 levels... but what about 3?
r'\{(?:[^{}]|\{(?:[^{}]|\{[^{}]*\})*\})*\}'
# This is already unreadable and only handles 2 levels
```

**The fix — a simple recursive descent parser**:
```python
from dataclasses import dataclass
from typing import Union

# AST nodes
@dataclass
class Text:
    content: str

@dataclass
class Variable:
    name: str

@dataclass
class IfBlock:
    condition: str
    children: list['Node']

Node = Union[Text, Variable, IfBlock]

class TemplateParser:
    def __init__(self, source: str):
        self.source = source
        self.pos = 0

    def parse(self) -> list[Node]:
        nodes = []
        while self.pos < len(self.source):
            if self.source[self.pos:].startswith('{/'):
                break  # End tag — return to parent
            elif self.source[self.pos:].startswith('{if '):
                nodes.append(self._parse_if())
            elif self.source[self.pos] == '{':
                nodes.append(self._parse_variable())
            else:
                nodes.append(self._parse_text())
        return nodes

    def _parse_text(self) -> Text:
        start = self.pos
        while self.pos < len(self.source) and self.source[self.pos] != '{':
            self.pos += 1
        return Text(self.source[start:self.pos])

    def _parse_variable(self) -> Variable:
        self.pos += 1  # skip {
        start = self.pos
        depth = 1
        while self.pos < len(self.source) and depth > 0:
            if self.source[self.pos] == '{': depth += 1
            elif self.source[self.pos] == '}': depth -= 1
            if depth > 0: self.pos += 1
        name = self.source[start:self.pos]
        self.pos += 1  # skip }
        return Variable(name.strip())

    def _parse_if(self) -> IfBlock:
        # Parse {if condition}
        self.pos += 4  # skip '{if '
        end = self.source.index('}', self.pos)
        condition = self.source[self.pos:end].strip()
        self.pos = end + 1

        # Recursively parse children (handles ANY nesting depth)
        children = self.parse()

        # Expect {/if}
        if self.source[self.pos:].startswith('{/if}'):
            self.pos += 5
        return IfBlock(condition, children)


# Usage
template = "{if logged_in}Hello {username}, you have {if count}{count}{/if} items{/if}"
ast = TemplateParser(template).parse()
```

**Why the parser wins**:
- Handles **arbitrary** nesting depth (regex can't)
- Each method is ~10 lines and clear (regex at 2+ levels is unreadable)
- Easy to extend: add `{for}`, `{else}`, filters, etc.
- Proper error messages: "Unclosed {if} at line 5" vs regex returning `None`

**Rule of thumb**: If you need to count matching delimiters (braces, tags, parentheses), you need a parser, not a regex.'''
    ),
    (
        "thinking/backtrack-bigbang-fails-strangler",
        "We need to replace our legacy order processing system (PHP, 200K LOC) with a new Python service. Management wants a 'big bang' rewrite — build the new system, flip the switch on launch day. I think this is risky. How do I argue for a better approach?",
        r'''<think>
Big bang rewrites are one of the most dangerous things in software engineering. Let me think about why, and what the alternative is.

Historical failures of big bang rewrites:
- Netscape 6: rewrote from scratch, took 3 years, lost market share to IE
- The Chandler project: ambitious rewrite, never delivered
- Countless internal company projects that took 2x the estimated time

Why big bang fails:
1. The old system has 10+ years of accumulated business rules, edge cases, and bug fixes that ARE the specification
2. You don't know all the rules until you try to replicate them
3. The rewrite takes longer than planned (always)
4. During the rewrite, the old system still needs maintenance — now you're maintaining TWO systems
5. On launch day, everything breaks at once — you can't isolate which part is wrong
6. Rollback means throwing away months/years of work

The Strangler Fig pattern (Martin Fowler): gradually replace parts of the old system. Named after strangler fig trees that grow around a host tree, eventually replacing it.

The approach:
1. Put a proxy/router in front of both systems
2. New features go in the new system
3. Migrate existing features one at a time
4. Each migration can be independently tested and rolled back
5. Eventually the old system has nothing left — decommission it

For an order processing system:
- Start with the API gateway routing
- Migrate "create order" first (high value, well-understood)
- Then "order status"
- Then edge cases (refunds, partial fulfillment)
- Run both in parallel with data comparison for safety

This approach reduces risk from "everything at once" to "one feature at a time."
</think>

Big bang rewrites have an **extremely high failure rate**. Here's how to argue for the Strangler Fig pattern instead.

**Why big bang fails — concrete risks for management**:

| Risk | Big Bang | Strangler Fig |
|------|----------|---------------|
| Timeline overrun | Almost certain (2-3x typical) | Each piece ships independently |
| Business disruption | All at once on launch day | Zero — old system runs until replaced |
| Rollback plan | Throw away months of work | Flip one route back to old system |
| Bug discovery | All bugs surface simultaneously | Bugs isolated to one migrated feature |
| Business value delivery | Zero until complete rewrite ships | Value delivered with each migration |
| Team morale | 18 months of "almost done" | Regular wins every 2-4 weeks |

**The Strangler Fig architecture**:
```
                    ┌─────────────┐
   Clients ───────→│  API Gateway │
                    │  (router)   │
                    └──────┬──────┘
                           │
                ┌──────────┴──────────┐
                │                     │
         ┌──────▼──────┐      ┌──────▼──────┐
         │ Legacy PHP  │      │  New Python  │
         │ (shrinking) │      │ (growing)    │
         └──────┬──────┘      └──────┬──────┘
                │                     │
         ┌──────▼──────┐      ┌──────▼──────┐
         │  Legacy DB  │◄────►│   New DB     │
         │  (MySQL)    │ sync │ (PostgreSQL) │
         └─────────────┘      └──────────────┘
```

**Implementation plan — phased migration**:
```python
# API Gateway routing (nginx or code-based)
# Phase 1: Route new features to new service
# Phase 2: Migrate existing features one by one

# gateway/router.py
ROUTING_TABLE = {
    # Phase 1: New features go straight to new system
    "POST /orders/bulk-import": "new_service",

    # Phase 2: Migrate existing features gradually
    "POST /orders": "new_service",        # Migrated week 3
    "GET /orders/{id}": "new_service",    # Migrated week 5
    "GET /orders/{id}/status": "legacy",  # Not yet migrated
    "POST /orders/{id}/refund": "legacy", # Complex — migrate last

    # Default: legacy handles everything not yet migrated
    "*": "legacy",
}

# Shadow testing: run both, compare results, alert on divergence
async def shadow_test_route(request):
    legacy_result = await call_legacy(request)
    new_result = await call_new_service(request)

    if legacy_result != new_result:
        log_divergence(request, legacy_result, new_result)

    return legacy_result  # Serve legacy result until confident
```

**Migration order for order processing** (lowest risk first):
```
Week 1-2:  Read-only endpoints (GET /orders, GET /orders/{id})
Week 3-4:  Create order (POST /orders) with shadow testing
Week 5-6:  Order status updates
Week 7-8:  Payment processing (highest risk — extra shadow testing)
Week 9-10: Refunds and edge cases
Week 11-12: Decommission legacy routes, keep legacy system on standby
Week 13+:  Decommission legacy system entirely
```

**The argument to management**: "We can start delivering value in week 1, not month 18. If anything goes wrong, we flip one route back — 30-second rollback. The big bang approach means we bet the business on a single launch day."'''
    ),
    (
        "thinking/backtrack-normalized-needs-denormalize",
        "Our e-commerce product listing page takes 2 seconds to load. The query joins 7 tables: products, categories, brands, prices, inventory, images, and reviews_summary. The query plan shows nested loop joins with 50K rows. The DBA says 'add more indexes' but it's already heavily indexed.",
        r'''<think>
7-table JOIN with 50K rows — this is a classic "over-normalized for read-heavy workload" problem.

Let me think about what's happening:
```sql
SELECT p.*, c.name as category, b.name as brand,
       pr.current_price, pr.sale_price,
       i.quantity as stock,
       img.url as primary_image,
       rs.avg_rating, rs.review_count
FROM products p
JOIN categories c ON p.category_id = c.id
JOIN brands b ON p.brand_id = b.id
JOIN prices pr ON p.id = pr.product_id AND pr.region_id = ?
JOIN inventory i ON p.id = i.product_id AND i.warehouse_id = ?
JOIN images img ON p.id = img.product_id AND img.is_primary = true
LEFT JOIN reviews_summary rs ON p.id = rs.product_id
WHERE c.id = ? AND p.active = true
ORDER BY p.sort_order
LIMIT 48
```

Even with indexes, 7 joins have overhead:
- Each join is a lookup, even with index = O(log n) per join per row
- 48 rows × 7 joins = 336 index lookups minimum
- Nested loop joins can be much worse depending on query planner decisions
- The LEFT JOIN to reviews_summary might prevent certain optimizations

More indexes won't help because the problem isn't missing indexes — it's too many joins for a page that runs thousands of times per minute.

My first thought: "Use a materialized view." That's a step in the right direction but still a database solution for a database problem.

Better approach: denormalize the read model. Create a `product_listings` table that contains all the data needed for the listing page in a single row. This is the CQRS read model approach.

But I need to think about the write side: when does this denormalized data need to update?
- Price changes: update product_listings.price (event from pricing service)
- Inventory changes: update product_listings.stock (event from inventory)
- New review: update product_listings.avg_rating (event from reviews service)
- Image change: update product_listings.image_url (event from CMS)

Each of these is an independent update, not a complex multi-table transaction. This is where eventual consistency is totally fine — a product listing showing the price from 5 seconds ago is acceptable.

Trade-off: We're trading write complexity (updating the denormalized table on each change) for read performance (single table scan, no joins).

For an e-commerce listing page that's read 1000x for every write, this is an easy win.
</think>

When you're joining 7 tables for a **read-heavy page** that runs thousands of times per minute, the schema is over-normalized for its workload. More indexes can't fix "too many joins."

**Why indexes don't help here**:
```sql
-- Even with perfect indexes, 7 joins × 48 rows = 336+ index lookups
-- Each lookup: tree traversal + random I/O = ~0.1ms
-- Total: 30-50ms in theory, but query planner decisions, buffer cache
-- misses, and lock contention push it to 500ms-2s under load
```

**The fix: denormalized read model (CQRS pattern)**:
```sql
-- Single table optimized for the listing page query
CREATE TABLE product_listings (
    product_id      BIGINT PRIMARY KEY,
    name            VARCHAR(255),
    slug            VARCHAR(255),
    category_id     INTEGER,
    category_name   VARCHAR(100),
    brand_name      VARCHAR(100),
    current_price   DECIMAL(10,2),
    sale_price      DECIMAL(10,2),
    stock_level     INTEGER,
    primary_image   VARCHAR(500),
    avg_rating      DECIMAL(3,2),
    review_count    INTEGER,
    sort_order      INTEGER,
    active          BOOLEAN,
    updated_at      TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_listings_category ON product_listings(category_id, active, sort_order);

-- The listing query: ONE table, ONE index scan, ZERO joins
SELECT * FROM product_listings
WHERE category_id = 42 AND active = true
ORDER BY sort_order
LIMIT 48;
-- Execution time: 2ms (vs 2000ms)
```

**Keep the denormalized table updated with events**:
```python
# When price changes, update the listing
async def handle_price_changed(event: PriceChangedEvent):
    await db.execute("""
        UPDATE product_listings
        SET current_price = $1, sale_price = $2, updated_at = NOW()
        WHERE product_id = $3
    """, event.price, event.sale_price, event.product_id)

# When a review is submitted, update the summary
async def handle_review_submitted(event: ReviewSubmittedEvent):
    await db.execute("""
        UPDATE product_listings
        SET avg_rating = $1, review_count = $2, updated_at = NOW()
        WHERE product_id = $3
    """, event.new_avg, event.new_count, event.product_id)

# When inventory changes
async def handle_stock_updated(event: StockUpdatedEvent):
    await db.execute("""
        UPDATE product_listings
        SET stock_level = $1, updated_at = NOW()
        WHERE product_id = $2
    """, event.quantity, event.product_id)
```

**The trade-off**:
```
                  | Normalized (7 JOINs) | Denormalized listing |
|-----------------|---------------------|---------------------|
| Read speed      | 500ms-2s            | 2ms                 |
| Write complexity| Simple INSERT/UPDATE | Must update listing on each change |
| Data freshness  | Always current       | Eventually consistent (~seconds) |
| Storage         | No duplication       | Duplicates ~500 bytes/product |
| Schema changes  | Change one table     | Must update source + listing |
```

For an e-commerce listing page read 1000x per write, this is an obvious win. The listing being 5 seconds stale is invisible to users; the page loading in 2ms vs 2s is not.'''
    ),
    (
        "thinking/backtrack-env-vars-need-feature-flags",
        "We use environment variables for all configuration. Now product wants us to enable a new checkout flow for 10% of users, then gradually roll it out. I can't restart the servers to change env vars for each percentage bump. What's the right approach?",
        r'''<think>
This is a clear case where the configuration mechanism (env vars) doesn't match the use case (runtime, gradual, per-user rollout).

Environment variables are:
- Set at deploy time (require restart to change)
- Server-wide (same value for all requests)
- Binary (on/off), not percentage-based
- Not user-aware

Feature flags need to be:
- Changed at runtime (no restart/redeploy)
- Per-user or percentage-based targeting
- Gradually adjustable (10% → 25% → 50% → 100%)
- Auditable (who changed what when)
- Kill-switchable (turn off instantly if broken)

The env var approach would be:
1. Set NEW_CHECKOUT=10 in env
2. Restart all servers
3. Change to NEW_CHECKOUT=25
4. Restart all servers again
5. Repeat...

This is terrible: restarts cause brief downtime, the rollout isn't user-sticky (a user might see old checkout, then new, then old), and there's no instant kill switch.

The right approach: a feature flag system. Options:
1. Build a simple one (database-backed, cached)
2. Use a service (LaunchDarkly, Unleash, Flipt)

For the "10% of users" requirement, I need consistent hashing — user_id hashed to determine if they're in the 10%. This ensures the same user always sees the same variant (sticky sessions).

Let me show both a simple home-built solution and the concept.
</think>

Environment variables are **deploy-time, server-wide, and binary**. You need **runtime, per-user, gradual** rollout. These are fundamentally different configuration mechanisms.

**Why env vars fail for this**:
```python
# Can't do per-user targeting
# Can't change without restart
# Can't do percentage rollout
# Can't kill-switch instantly
NEW_CHECKOUT = os.environ.get("NEW_CHECKOUT", "false") == "true"
```

**Feature flag system — simple database-backed implementation**:
```python
import hashlib
from dataclasses import dataclass
from functools import lru_cache
import time

@dataclass
class FeatureFlag:
    name: str
    enabled: bool
    rollout_percentage: int  # 0-100
    allowed_user_ids: set[str]  # explicit overrides
    updated_at: float

class FeatureFlagService:
    def __init__(self, db):
        self.db = db
        self._cache: dict[str, FeatureFlag] = {}
        self._cache_ttl = 10  # seconds — balance freshness vs DB load
        self._last_refresh = 0

    def is_enabled(self, flag_name: str, user_id: str | None = None) -> bool:
        flag = self._get_flag(flag_name)
        if flag is None or not flag.enabled:
            return False

        # Explicit user override (for internal testing)
        if user_id and user_id in flag.allowed_user_ids:
            return True

        # Percentage rollout with consistent hashing
        if user_id and flag.rollout_percentage < 100:
            hash_input = f"{flag_name}:{user_id}"
            hash_value = int(hashlib.sha256(hash_input.encode()).hexdigest(), 16)
            user_bucket = hash_value % 100
            return user_bucket < flag.rollout_percentage

        return flag.rollout_percentage == 100

    def _get_flag(self, name: str) -> FeatureFlag | None:
        now = time.time()
        if now - self._last_refresh > self._cache_ttl:
            self._refresh_cache()
        return self._cache.get(name)

    def _refresh_cache(self):
        rows = self.db.execute(
            "SELECT name, enabled, rollout_percentage, allowed_user_ids, updated_at "
            "FROM feature_flags"
        ).fetchall()
        self._cache = {
            row.name: FeatureFlag(
                name=row.name,
                enabled=row.enabled,
                rollout_percentage=row.rollout_percentage,
                allowed_user_ids=set(row.allowed_user_ids or []),
                updated_at=row.updated_at,
            )
            for row in rows
        }
        self._last_refresh = time.time()


# Usage in route handler
flags = FeatureFlagService(db)

@app.post("/checkout")
async def checkout(request: Request, user: User = Depends(get_user)):
    if flags.is_enabled("new_checkout_flow", user.id):
        return await new_checkout(request, user)
    return await legacy_checkout(request, user)
```

**Admin API — change rollout without restart**:
```python
@app.put("/admin/flags/{flag_name}")
async def update_flag(flag_name: str, body: FlagUpdate, admin: Admin = Depends(require_admin)):
    await db.execute(
        "UPDATE feature_flags SET rollout_percentage = $1, updated_at = NOW() WHERE name = $2",
        body.rollout_percentage, flag_name
    )
    audit_log.info(f"{admin.email} set {flag_name} to {body.rollout_percentage}%")
    return {"status": "updated"}

# Rollout plan:
# Day 1: POST /admin/flags/new_checkout_flow {"rollout_percentage": 10}
# Day 3: PUT  /admin/flags/new_checkout_flow {"rollout_percentage": 25}
# Day 7: PUT  /admin/flags/new_checkout_flow {"rollout_percentage": 100}
# Oh no, bug! PUT /admin/flags/new_checkout_flow {"enabled": false}  ← instant kill
```

**Why consistent hashing matters**: `sha256("flag:user123") % 100` always gives the same bucket. So user123 is always in or always out of the 10% — no flickering between old and new UI on each page load.'''
    ),
    (
        "thinking/backtrack-catchall-needs-specific",
        "We have a `try/except Exception` around our main request handler. It catches everything and returns a 500 error. But now we can't tell the difference between a database timeout, a validation error, and an auth failure — they all look the same in logs and to users.",
        r'''<think>
This is the "Pokemon exception handling" anti-pattern — gotta catch 'em all. The broad catch masks the nature of errors, making debugging and user experience terrible.

The user's current code probably looks like:
```python
try:
    result = process_request(request)
    return {"data": result}
except Exception as e:
    logger.error(f"Error: {e}")
    return {"error": "Internal server error"}, 500
```

Problems:
1. A validation error (user's fault) returns 500 (server's fault)
2. A database timeout logs the same as a permission error
3. No way to set up alerts for specific error types
4. Users get unhelpful "Internal server error" for everything

The fix: structured exception hierarchy with specific handlers.

But I need to think about the progression. The first instinct might be to add specific except blocks:
```python
except ValidationError as e:
    return {"error": str(e)}, 400
except AuthError as e:
    return {"error": str(e)}, 401
except DatabaseError as e:
    logger.error(f"DB error: {e}")
    return {"error": "Service unavailable"}, 503
except Exception as e:
    logger.error(f"Unexpected: {e}")
    return {"error": "Internal server error"}, 500
```

That's better but doesn't scale — you'd need to add except blocks everywhere. The framework approach is better: exception handlers registered at the app level.

Let me show the full progression from bad → specific handlers → framework-level error handling.
</think>

Your catch-all is masking the nature of errors — a user typo, a database outage, and a security violation all look identical. This hurts debugging, monitoring, and user experience.

**Define an exception hierarchy**:
```python
class AppError(Exception):
    """Base for all application errors."""
    def __init__(self, message: str, status_code: int = 500, error_code: str = "INTERNAL"):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        super().__init__(message)

class ValidationError(AppError):
    def __init__(self, message: str, field: str | None = None):
        self.field = field
        super().__init__(message, status_code=400, error_code="VALIDATION_ERROR")

class AuthenticationError(AppError):
    def __init__(self, message: str = "Invalid credentials"):
        super().__init__(message, status_code=401, error_code="AUTH_FAILED")

class ForbiddenError(AppError):
    def __init__(self, message: str = "Permission denied"):
        super().__init__(message, status_code=403, error_code="FORBIDDEN")

class NotFoundError(AppError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(f"{resource} {resource_id} not found", status_code=404, error_code="NOT_FOUND")

class ConflictError(AppError):
    def __init__(self, message: str):
        super().__init__(message, status_code=409, error_code="CONFLICT")

class ServiceUnavailableError(AppError):
    def __init__(self, service: str, message: str = ""):
        self.service = service
        super().__init__(f"{service} unavailable: {message}", status_code=503, error_code="SERVICE_UNAVAILABLE")
```

**Register framework-level error handlers (instead of try/except everywhere)**:
```python
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    # Known errors: log at appropriate level, return specific status
    if exc.status_code >= 500:
        logger.error(f"[{exc.error_code}] {exc.message}", exc_info=True)
    else:
        logger.warning(f"[{exc.error_code}] {exc.message}")

    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error_code, "message": exc.message}
    )

@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    # TRULY unexpected errors: log as critical, alert on-call
    logger.critical(f"Unhandled exception: {exc}", exc_info=True)
    metrics.increment("unhandled_exceptions")  # Triggers PagerDuty alert
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL", "message": "An unexpected error occurred"}
    )
```

**Now your route handlers are clean**:
```python
@app.post("/orders")
async def create_order(body: OrderCreate, user: User = Depends(get_user)):
    # Each of these raises a SPECIFIC exception — no try/except needed
    if not body.items:
        raise ValidationError("Order must have at least one item", field="items")

    for item in body.items:
        product = await product_repo.get(item.product_id)
        if not product:
            raise NotFoundError("Product", item.product_id)
        if product.stock < item.quantity:
            raise ConflictError(f"Insufficient stock for {product.name}")

    try:
        charge = await payment_service.charge(user.payment_method, body.total)
    except ConnectionError:
        raise ServiceUnavailableError("payment", "Connection timeout")

    return await order_repo.create(user.id, body.items, charge.id)
```

**The monitoring payoff**:
```
# Before (useless): "Error: something went wrong" × 500/hour
# After (actionable):
[VALIDATION_ERROR] 340/hour — normal, user input errors
[SERVICE_UNAVAILABLE:payment] 12/hour — payment gateway flaky, investigate
[AUTH_FAILED] 8/hour — normal login failures
[INTERNAL] 2/hour ← THESE are the real bugs to fix
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
