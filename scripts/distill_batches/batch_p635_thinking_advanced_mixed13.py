"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 13)"""

PAIRS = [
    (
        "thinking/backtrack-inheritance-to-composition",
        "I have a deep class hierarchy: Animal → Pet → Dog → TrainedDog → ServiceDog. Every new requirement requires changing the hierarchy and it breaks existing classes. How do I fix this?",
        r'''<think>
Deep inheritance hierarchy causing brittleness. Classic "favor composition over inheritance" problem.

**Why the hierarchy breaks:**
When you add a new requirement that doesn't fit the hierarchy — e.g., "some dogs are therapy dogs but not trained in the traditional sense" — you can't model it. TherapyDog extends Dog but not TrainedDog? Or does it extend TrainedDog without all the training methods?

**The problem with deep inheritance:**
1. Fragile base class: changing Animal affects Pet, Dog, TrainedDog, ServiceDog
2. Rigid taxonomy: real-world concepts don't fit neat hierarchies
3. Diamond problem: what if a ServiceDog is also a CompanionAnimal?
4. Tight coupling: subclasses depend on parent implementation details

**First thought: flatten the hierarchy**
Make everything extend Animal directly. But then you lose shared behavior.

**Better: composition over inheritance**
Instead of IS-A relationships (ServiceDog IS A TrainedDog IS A Dog), use HAS-A relationships (a Dog HAS training behaviors, HAS service capabilities).

Behaviors become components that can be mixed and matched.
</think>

Deep inheritance is a dead end for evolving requirements. Let me show why, then the composition-based fix.

## Why Deep Inheritance Breaks

```python
# ❌ The hierarchy
class Animal:
    def eat(self): ...
    def sleep(self): ...

class Pet(Animal):
    def __init__(self, owner): ...

class Dog(Pet):
    def bark(self): ...
    def fetch(self): ...

class TrainedDog(Dog):
    def sit(self): ...
    def stay(self): ...
    def heel(self): ...

class ServiceDog(TrainedDog):
    def guide_blind(self): ...
    def alert_seizure(self): ...

# NEW REQUIREMENT: "Therapy dogs provide comfort but aren't trained like service dogs"
# Where does TherapyDog go?
#   TherapyDog(Dog)?         → loses trained behaviors it DOES have
#   TherapyDog(TrainedDog)?  → inherits guide_blind which it doesn't do
#   TherapyDog(ServiceDog)?  → wrong semantically

# NEW REQUIREMENT: "Some cats can also be therapy animals"
# TherapyCat(Cat)? But therapy behavior is the same as TherapyDog!
# Copy-paste? New shared base class? The hierarchy can't handle this.
```

## The Fix: Composition

```python
# ✅ Behaviors are independent, composable components

class Animal:
    def __init__(self, name, species):
        self.name = name
        self.species = species
        self.behaviors = []

    def add_behavior(self, behavior):
        self.behaviors.append(behavior)

# Behaviors are standalone capabilities
class Trainable:
    def sit(self): print(f"Sits")
    def stay(self): print(f"Stays")
    def heel(self): print(f"Heels")

class ServiceCapable:
    def __init__(self, service_type):
        self.service_type = service_type
    def perform_service(self):
        print(f"Performing {self.service_type} service")

class TherapyCapable:
    def provide_comfort(self): print("Providing comfort")
    def visit_hospital(self): print("Visiting hospital")

class Fetchable:
    def fetch(self, item): print(f"Fetches {item}")


# Now ANY animal can have ANY combination of behaviors:
buddy = Animal("Buddy", "dog")
buddy.training = Trainable()
buddy.service = ServiceCapable("guide")
# Buddy is a trained guide dog

whiskers = Animal("Whiskers", "cat")
whiskers.therapy = TherapyCapable()
# Whiskers is a therapy cat — no hierarchy change needed!

rex = Animal("Rex", "dog")
rex.training = Trainable()
rex.therapy = TherapyCapable()
rex.fetch = Fetchable()
# Rex is a trained therapy dog that plays fetch
# Try modeling this with inheritance!
```

## More Practical Example (Dataclass Approach)

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class TrainingProfile:
    commands: list[str] = field(default_factory=list)
    certified: bool = False
    trainer: Optional[str] = None

@dataclass
class ServiceProfile:
    service_type: str  # "guide", "hearing", "seizure-alert"
    handler_id: int
    vest_id: str

@dataclass
class TherapyProfile:
    facility_certified: bool = False
    specialization: str = "general"  # "pediatric", "geriatric", "PTSD"

@dataclass
class Animal:
    name: str
    species: str
    breed: Optional[str] = None
    training: Optional[TrainingProfile] = None
    service: Optional[ServiceProfile] = None
    therapy: Optional[TherapyProfile] = None

# Any combination works without changing any class:
guide_dog = Animal(
    name="Max", species="dog", breed="Lab",
    training=TrainingProfile(commands=["sit", "stay", "heel"], certified=True),
    service=ServiceProfile(service_type="guide", handler_id=42, vest_id="V-123"),
)

therapy_cat = Animal(
    name="Mimi", species="cat",
    therapy=TherapyProfile(facility_certified=True, specialization="pediatric"),
)

# New requirement: "emotional support animals"?
# Just add: emotional_support: Optional[EmotionalSupportProfile] = None
# ZERO existing code changes.
```

## When to Use Inheritance vs Composition

```
USE INHERITANCE when:
  ✓ The relationship is truly IS-A and won't change
  ✓ The hierarchy is shallow (max 2-3 levels)
  ✓ Subclasses need to override specific behavior (polymorphism)
  Example: Exception → ValueError, TypeError (stable, shallow)

USE COMPOSITION when:
  ✓ Objects have CAPABILITIES that can be mixed and matched
  ✓ Requirements change frequently (new combinations needed)
  ✓ You find yourself wanting multiple inheritance
  ✓ The hierarchy keeps growing deeper
  Example: Game entities with Health, Inventory, Movement, Combat components
```'''
    ),
    (
        "thinking/analogy-api-rate-limiting-to-water-supply",
        "We need to implement different rate limits for different API plans (free, pro, enterprise). Free users get 100 requests/hour, pro gets 1000, enterprise gets 10,000. How should I design this?",
        r'''<think>
Tiered rate limiting — the water supply analogy works well for different allocations.

**Water supply analogy:**
- API = water supply system
- Rate limit = water allocation per household
- Free plan = standard residential allocation (100 gallons/day)
- Pro plan = commercial allocation (1000 gallons/day)
- Enterprise = industrial allocation (10,000 gallons/day)
- Rate limit exceeded = water pressure drops to zero (request rejected)

But I should focus more on the implementation than the analogy here. The question is about DESIGN, not just explanation.

Key design decisions:
1. Where to store rate limit state (Redis is standard)
2. How to identify users (API key, JWT, IP)
3. What algorithm (token bucket per plan)
4. How to communicate limits (headers)
5. What happens when exceeded (429 with Retry-After)
</think>

Think of it like a **water utility with different allocation tiers** — each customer gets a different flow rate based on their plan.

## Design: Tiered Rate Limiting

```python
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import redis
import time

app = FastAPI()
cache = redis.Redis()

# Plan definitions
RATE_LIMITS = {
    "free":       {"requests": 100,   "window": 3600},  # 100/hour
    "pro":        {"requests": 1000,  "window": 3600},  # 1000/hour
    "enterprise": {"requests": 10000, "window": 3600},  # 10000/hour
}

def check_rate_limit(api_key: str, plan: str) -> dict:
    """Sliding window counter rate limiter."""
    limits = RATE_LIMITS.get(plan, RATE_LIMITS["free"])
    window = limits["window"]
    max_requests = limits["requests"]

    now = int(time.time())
    window_start = now - window
    key = f"ratelimit:{api_key}"

    pipe = cache.pipeline()
    # Remove old entries outside the window
    pipe.zremrangebyscore(key, 0, window_start)
    # Count requests in current window
    pipe.zcard(key)
    # Add current request
    pipe.zadd(key, {f"{now}:{id(now)}": now})
    # Set expiry on the key
    pipe.expire(key, window)
    results = pipe.execute()

    current_count = results[1]
    remaining = max(0, max_requests - current_count - 1)
    reset_at = now + window

    return {
        "allowed": current_count < max_requests,
        "limit": max_requests,
        "remaining": remaining,
        "reset": reset_at,
    }


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    api_key = request.headers.get("X-API-Key")
    if not api_key:
        return JSONResponse(status_code=401, content={"error": "API key required"})

    # Look up plan for this API key
    plan = get_plan_for_key(api_key)  # Returns "free", "pro", or "enterprise"

    result = check_rate_limit(api_key, plan)

    if not result["allowed"]:
        return JSONResponse(
            status_code=429,
            content={
                "error": "Rate limit exceeded",
                "limit": result["limit"],
                "reset_at": result["reset"],
            },
            headers={
                "X-RateLimit-Limit": str(result["limit"]),
                "X-RateLimit-Remaining": "0",
                "X-RateLimit-Reset": str(result["reset"]),
                "Retry-After": str(result["reset"] - int(time.time())),
            }
        )

    response = await call_next(request)

    # Always include rate limit headers (so clients can track usage)
    response.headers["X-RateLimit-Limit"] = str(result["limit"])
    response.headers["X-RateLimit-Remaining"] = str(result["remaining"])
    response.headers["X-RateLimit-Reset"] = str(result["reset"])

    return response
```

## Response Headers (Communicate Limits to Clients)

```
EVERY response should include rate limit headers:

HTTP/1.1 200 OK
X-RateLimit-Limit: 1000           ← Your plan allows 1000/hour
X-RateLimit-Remaining: 742        ← You have 742 left
X-RateLimit-Reset: 1709654400     ← Window resets at this Unix timestamp

HTTP/1.1 429 Too Many Requests    ← Rate limit exceeded
Retry-After: 1823                 ← Try again in 1823 seconds
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1709654400

{
    "error": {
        "code": "RATE_LIMITED",
        "message": "Rate limit exceeded. Upgrade to Pro for 1000 requests/hour.",
        "limit": 100,
        "reset_at": "2024-03-05T15:00:00Z"
    }
}
```

## Per-Endpoint Limits (Advanced)

```python
# Some endpoints are more expensive than others
ENDPOINT_COSTS = {
    "GET /api/users":    1,    # Cheap
    "POST /api/orders":  5,    # Medium
    "POST /api/reports": 50,   # Expensive (generates a report)
    "GET /api/search":   2,    # Moderate
}

# Instead of counting requests, count "cost units"
# Free plan: 100 units/hour
# GET /api/users: costs 1 unit → 100 calls/hour
# POST /api/reports: costs 50 units → 2 calls/hour

# This prevents abuse of expensive endpoints while being
# generous with cheap ones.
```

## Client-Side Handling

```python
import time
import requests

def api_call_with_rate_limit(url, api_key):
    response = requests.get(url, headers={"X-API-Key": api_key})

    if response.status_code == 429:
        retry_after = int(response.headers.get("Retry-After", 60))
        print(f"Rate limited. Waiting {retry_after}s...")
        time.sleep(retry_after)
        return api_call_with_rate_limit(url, api_key)  # Retry

    # Track remaining to avoid hitting limits
    remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
    if remaining < 10:
        print(f"Warning: only {remaining} requests remaining this window")

    return response
```'''
    ),
    (
        "thinking/causal-database-deadlock",
        "We're getting intermittent deadlock errors in our PostgreSQL database. They happen 2-3 times per day and always on the orders table. What's causing this and how do I fix it?",
        r'''<think>
Database deadlocks on the orders table. Let me reason through the causal chain.

**What is a deadlock?**
Two transactions each hold a lock the other needs:
- Transaction A: locks row 1, then tries to lock row 2
- Transaction B: locks row 2, then tries to lock row 1
- Both wait forever → database detects and kills one

**Why it happens on the orders table:**
The orders table is likely updated by multiple concurrent processes:
- Order creation (inserts + updates)
- Payment processing (updates order status)
- Inventory updates (updates related items)
- Background jobs (updates order status)

**Common causes of deadlocks:**
1. Inconsistent lock ordering: different code paths lock rows in different order
2. Foreign key locks: updating orders locks related rows in other tables
3. Index locks: updates to indexed columns cause lock escalation
4. Long transactions: holding locks for extended periods

**The fix:**
1. Consistent lock ordering: always update rows in the same order (e.g., by order_id ascending)
2. Keep transactions short: don't hold locks while doing external calls
3. Retry on deadlock: the database rolls back one transaction — just retry it
4. Use SELECT FOR UPDATE with SKIP LOCKED for queue-like patterns

**Diagnostic approach:**
Check PostgreSQL logs for the specific deadlock details (pg_stat_activity shows the conflicting queries).
</think>

Deadlocks happen when two transactions each hold a lock the other needs. Let me trace the cause.

## How Deadlocks Occur

```
TRANSACTION A:                     TRANSACTION B:
  UPDATE orders SET status='paid'    UPDATE orders SET status='shipped'
  WHERE id = 100;                    WHERE id = 200;
  -- Locks row 100 ✓                 -- Locks row 200 ✓

  UPDATE orders SET status='done'    UPDATE orders SET status='done'
  WHERE id = 200;                    WHERE id = 100;
  -- Wants row 200 → BLOCKED!        -- Wants row 100 → BLOCKED!

  Both wait for each other → DEADLOCK
  PostgreSQL detects it, kills one → "deadlock detected" error
```

## Find the Conflicting Queries

```sql
-- PostgreSQL logs deadlocks by default. Check:
-- log_min_messages = 'error' includes deadlocks

-- Or query pg_stat_activity during the deadlock window:
SELECT pid, state, query, wait_event_type, wait_event,
       pg_blocking_pids(pid) as blocked_by
FROM pg_stat_activity
WHERE datname = 'your_database'
  AND state != 'idle';

-- Enable deadlock logging with details:
-- In postgresql.conf:
-- log_lock_waits = on
-- deadlock_timeout = 1s
```

## Fix 1: Consistent Lock Ordering (Primary Fix)

```python
# ❌ CAUSES DEADLOCKS: different code paths lock rows in different order

# Process A: updates orders by user_id (arbitrary order)
def process_user_orders(user_id):
    orders = db.query("SELECT id FROM orders WHERE user_id = %s", user_id)
    for order in orders:
        db.execute("UPDATE orders SET processed = true WHERE id = %s", order.id)

# Process B: updates orders by batch (different order!)
def process_batch(order_ids):
    for order_id in order_ids:  # Could be in ANY order
        db.execute("UPDATE orders SET batch_status = 'done' WHERE id = %s", order_id)


# ✅ FIXED: always lock rows in the same order (e.g., ascending ID)
def process_user_orders(user_id):
    orders = db.query(
        "SELECT id FROM orders WHERE user_id = %s ORDER BY id",  # SORTED
        user_id
    )
    for order in orders:
        db.execute("UPDATE orders SET processed = true WHERE id = %s", order.id)

def process_batch(order_ids):
    for order_id in sorted(order_ids):  # SORTED — same order as Process A
        db.execute("UPDATE orders SET batch_status = 'done' WHERE id = %s", order_id)
```

## Fix 2: Keep Transactions Short

```python
# ❌ CAUSES DEADLOCKS: long transaction holds locks while doing external calls
def process_order(order_id):
    with db.transaction():
        order = db.query("SELECT * FROM orders WHERE id = %s FOR UPDATE", order_id)
        # Locks the row ↑

        result = payment_api.charge(order.total)  # 2-second external call!
        # Row is locked for 2 seconds — other transactions queue up

        db.execute("UPDATE orders SET status = 'paid' WHERE id = %s", order_id)

# ✅ FIXED: do external work OUTSIDE the transaction
def process_order(order_id):
    order = db.query("SELECT * FROM orders WHERE id = %s", order_id)

    result = payment_api.charge(order.total)  # No lock held during this

    with db.transaction():
        # Short transaction — only the database update
        db.execute(
            "UPDATE orders SET status = 'paid', payment_id = %s WHERE id = %s AND status = 'pending'",
            result.payment_id, order_id
        )
        # Lock held for milliseconds, not seconds
```

## Fix 3: Retry on Deadlock

```python
# Deadlocks are expected in concurrent systems.
# The database rolls back one transaction — just retry it.

import time
from psycopg2 import errors

def with_deadlock_retry(func, max_retries=3):
    for attempt in range(max_retries):
        try:
            return func()
        except errors.DeadlockDetected:
            if attempt == max_retries - 1:
                raise
            time.sleep(0.1 * (2 ** attempt))  # Backoff: 0.1s, 0.2s, 0.4s

# Usage:
with_deadlock_retry(lambda: process_order(order_id))
```

## Prevention Checklist

```
□ Lock rows in consistent order (always by ascending primary key)
□ Keep transactions as short as possible (no external calls inside)
□ Add deadlock retry logic (3 retries with backoff)
□ Use SELECT ... FOR UPDATE SKIP LOCKED for queue patterns
□ Monitor deadlock frequency (should be < 1/day after fixes)
□ Log deadlock details for diagnosis
```'''
    ),
    (
        "thinking/uncertainty-caching-strategy-what-to-cache",
        "We want to add caching to our API to improve performance. What should we cache? Everything? Only slow queries? How do I decide?",
        r'''<think>
What to cache — this requires calibrated thinking about trade-offs.

**The trade-off of caching:**
Every cached item has:
- Benefit: faster response, reduced DB load
- Cost: memory usage, stale data risk, cache invalidation complexity

Not everything should be cached. The decision depends on:
1. How often is it read? (high read = good cache candidate)
2. How often does it change? (low change = easy to cache)
3. How expensive is it to compute/fetch? (expensive = worth caching)
4. Can users tolerate stale data? (yes = cache-friendly)

**Framework:**
- High read + low change + expensive = DEFINITELY cache
- Low read + high change + cheap = DON'T cache
- Everything in between = evaluate case by case
</think>

Not everything should be cached. Here's a framework for deciding — confidence: **80%** in this approach.

## The Decision Framework

```
For each potential cache candidate, evaluate:

                    CACHE-FRIENDLY              CACHE-UNFRIENDLY
───────────────────────────────────────────────────────────────────
Read frequency      High (100+ reads/min)       Low (< 1 read/min)
Change frequency    Low (changes hourly/daily)   High (changes per request)
Computation cost    Expensive (50ms+ query)      Cheap (< 5ms)
Staleness tolerance OK if 30s old               Must be real-time
User-specific       Shared across users          Per-user unique data

CACHE SCORE:
  High read + low change + expensive + stale-OK = DEFINITELY CACHE
  Low read + high change + cheap + must-be-fresh = DON'T CACHE
```

## What to Cache (Practical Examples)

```python
# ✅ DEFINITELY CACHE: product catalog
# Read: 10,000 times/minute (every page load)
# Changes: a few times per day (admin updates)
# Cost: 50ms database query with JOINs
# Staleness: 5-minute-old prices are acceptable
@app.get("/products")
async def get_products(category: str):
    key = f"products:{category}"
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)
    products = await db.get_products(category)  # 50ms
    await redis.setex(key, 300, json.dumps(products))  # Cache 5 min
    return products


# ✅ CACHE: user profile (read-heavy, changes rarely)
# Read: every request (for auth/display)
# Changes: when user edits profile (rare)
# Invalidate: on profile update
@app.get("/users/{user_id}/profile")
async def get_profile(user_id: int):
    key = f"profile:{user_id}"
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)
    profile = await db.get_profile(user_id)
    await redis.setex(key, 600, json.dumps(profile))
    return profile

@app.put("/users/{user_id}/profile")
async def update_profile(user_id: int, data: ProfileUpdate):
    await db.update_profile(user_id, data)
    await redis.delete(f"profile:{user_id}")  # Invalidate cache


# ❌ DON'T CACHE: real-time inventory count
# Read: moderate
# Changes: EVERY purchase (high frequency)
# Staleness: showing "in stock" when sold out = bad UX + overselling
# Keep this as a direct database read


# ❌ DON'T CACHE: search results with many parameters
# cache key: "search:q=shoes&size=10&color=red&sort=price&page=3"
# Each unique combination = separate cache entry
# Hit rate would be < 1% (too many unique queries)
# Memory wasted on entries that are never read again


# ⚠️ MAYBE CACHE: dashboard analytics
# Read: moderate (every dashboard load)
# Cost: VERY expensive (aggregation over millions of rows, 2 seconds)
# Changes: real-time data
# SOLUTION: cache with short TTL (30 seconds) or background refresh
@app.get("/dashboard")
async def get_dashboard():
    cached = await redis.get("dashboard")
    if cached:
        return json.loads(cached)
    # Expensive: runs every 30 seconds, not every request
    data = await compute_dashboard_data()  # 2 seconds
    await redis.setex("dashboard", 30, json.dumps(data))
    return data
```

## Cache Invalidation Strategy

```
THE HARD PART isn't caching — it's knowing when to invalidate.

STRATEGY 1: TTL (Time-based expiry)
  Simple. Set TTL=300 → data is at most 5 minutes stale.
  Good for: products, settings, public content

STRATEGY 2: Event-based invalidation
  Delete cache when data changes.
  Good for: user profiles, order status

STRATEGY 3: Write-through
  Update cache AND database on every write.
  Good for: session data, frequently updated counters

STRATEGY 4: Background refresh
  Periodically rebuild cache before it expires.
  Good for: expensive dashboard queries, reports

CHOOSE BASED ON STALENESS TOLERANCE:
  Real-time needed → don't cache (or event-based invalidation)
  Seconds OK → TTL 10-30 seconds
  Minutes OK → TTL 300 seconds
  Hours OK → TTL 3600 seconds + event-based invalidation
```'''
    ),
    (
        "thinking/firstprinciples-why-api-keys-exist",
        "Why do APIs need keys? Why can't they just be open? I'm building a public API and wondering if I really need to require API keys.",
        r'''<think>
API keys from first principles. What problems do they solve?

**Without API keys:**
Your API is completely anonymous. Anyone can call it. You can't:
1. Identify WHO is making requests
2. Limit HOW MUCH any one consumer uses
3. BLOCK abusive consumers
4. TRACK usage for billing or analytics
5. REVOKE access to specific consumers

**What API keys provide:**
1. Identification: link requests to a consumer (not authentication — keys aren't passwords)
2. Rate limiting: enforce limits per consumer
3. Analytics: track usage patterns per consumer
4. Access control: revoke a specific key without affecting others
5. Billing: charge based on usage per key
6. Abuse prevention: block a specific abuser without blocking everyone

**Even for "public" APIs:**
Public doesn't mean unlimited. Weather APIs, map APIs, search APIs — all public but require keys because:
- Without limits, one bot can consume all your capacity
- Without identification, you can't block the bot without blocking everyone
- Without analytics, you don't know who your users are

**When you DON'T need keys:**
- Truly public static data (CDN-served)
- Internal services behind a firewall
- Simple webhooks with signature verification instead
</think>

Even for a public API, keys solve real problems. Let me derive why from the threats.

## Without API Keys: What Goes Wrong

```
YOUR PUBLIC API, NO KEYS:

Day 1:   100 users, 10,000 requests/day. Works fine.

Day 30:  Someone writes a bot that calls your API 1,000 times/second.
         Your server is overwhelmed. All users experience timeouts.
         You can't block the bot without blocking EVERYONE.
         (You could block their IP, but they switch to a VPN)

Day 60:  A competitor scrapes your entire database through the API.
         1 million requests over a weekend. You can't stop them.
         You can't even identify WHO did it.

Day 90:  Your API costs $500/month in server resources.
         Who's using it? You don't know.
         Is it 100 users or 10,000? You don't know.
         Could you charge heavy users? You can't identify them.
```

## What API Keys Provide

```
WITH API KEYS:

1. IDENTIFICATION (who is this?)
   Without key: "Request from 45.33.128.7" (meaningless)
   With key:    "Request from AcmeCorp (key: ak_abc123)"

2. RATE LIMITING (how much can they use?)
   Without key: can't limit per-user (only per-IP, easily bypassed)
   With key:    AcmeCorp: 1000 req/hour. Exceeded? → 429 Too Many Requests

3. ABUSE CONTROL (stop bad actors)
   Without key: block IP → they switch IP → cat-and-mouse game
   With key:    revoke key ak_abc123 → AcmeCorp is blocked immediately

4. ANALYTICS (who uses what?)
   Without key: "10,000 requests yesterday" (from whom? doing what?)
   With key:    "AcmeCorp: 5,000 requests to /search, BetaCo: 3,000 to /users"

5. BILLING (charge for usage)
   Without key: impossible (can't attribute usage)
   With key:    AcmeCorp: 50,000 requests × $0.001 = $50 invoice

6. GRADUATED ACCESS
   Without key: everyone gets everything
   With key:    Free tier: 100 req/day, read-only
                Pro tier: 10,000 req/day, read+write
                Enterprise: unlimited, custom features
```

## Implementation

```python
import secrets

# Generate API keys
def create_api_key(user_id: int, plan: str) -> str:
    key = f"ak_{secrets.token_urlsafe(32)}"
    db.execute(
        "INSERT INTO api_keys (key, user_id, plan, created_at) VALUES (%s, %s, %s, NOW())",
        key, user_id, plan
    )
    return key

# Validate and identify
@app.middleware("http")
async def api_key_middleware(request, call_next):
    key = request.headers.get("X-API-Key") or request.query_params.get("api_key")

    if not key:
        return JSONResponse(401, {"error": "API key required"})

    key_data = await db.get_api_key(key)
    if not key_data:
        return JSONResponse(401, {"error": "Invalid API key"})

    if key_data.revoked:
        return JSONResponse(403, {"error": "API key has been revoked"})

    # Attach consumer info to request for rate limiting and analytics
    request.state.api_key = key_data
    request.state.user_id = key_data.user_id
    request.state.plan = key_data.plan

    response = await call_next(request)
    return response
```

## When You DON'T Need API Keys

```
✗ Static content served via CDN (just serve it)
✗ Internal microservice-to-microservice calls (use mTLS or service mesh)
✗ Public read-only data with no rate limit concerns
✗ Webhooks (use signature verification instead)

But even "public" APIs almost always need keys because
without them, you have no way to manage capacity, block abuse,
or understand your users.
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
