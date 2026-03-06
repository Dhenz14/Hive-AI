"""Phase 2C: Advanced Reasoning — Analogical Reasoning (Part 6/8)"""

PAIRS = [
    (
        "thinking/analogy-cache-invalidation-to-library-catalog",
        "How do I explain cache invalidation strategies to my team? They keep getting confused about when to use TTL vs write-through vs event-based invalidation.",
        r'''<think>
Cache invalidation — one of the two hard problems in computer science. I need an analogy that covers multiple strategies.

**Library catalog analogy:**
A library has a catalog (cache) that tells you where books are. The actual bookshelves (database) are the source of truth. The catalog needs to stay in sync with the shelves.

Strategies:
1. **TTL (Time-to-Live)**: "Reprint the catalog every month"
   - Simple, but for the month between reprints, some books might have moved
   - You might go to shelf 4A for a book that was moved to 7C last week

2. **Write-through**: "Every time a librarian shelves a book, they also update the catalog"
   - Catalog is always accurate
   - But shelving takes longer (you have to update two things)

3. **Write-behind**: "Librarians note changes on a sticky note, and update the catalog at the end of the day"
   - Shelving is fast (just write the sticky note)
   - But catalog is slightly behind during the day

4. **Event-based (invalidation on write)**: "When a book moves, tear out that page of the catalog so the next person knows to check the shelf directly"
   - Don't maintain a stale entry — just remove it
   - Next person checks the shelf (cache miss → database query), and the catalog gets a fresh entry

5. **Cache-aside (lazy loading)**: "The catalog is initially empty. The first person who asks for a book checks the shelf, then writes the location in the catalog for the next person."
   - No upfront catalog maintenance
   - First lookup is slow (cache miss), subsequent ones are fast

**Where the analogy works:**
- Source of truth vs cache ✓
- Staleness vs consistency trade-off ✓
- Cost of maintaining sync ✓

**Where it breaks:**
- Libraries don't have millions of lookups per second
- Cache eviction (throwing out entries when catalog is full) doesn't map perfectly
- Distributed caching (multiple catalog copies) is hard to analogize
</think>

Think of caching like a **library catalog** — it tells you where to find books without checking every shelf. The question is: how do you keep the catalog accurate when books move?

## The Analogy

```
Database  = The actual bookshelves (source of truth)
Cache     = The catalog card index (quick lookup)
Cache hit = Found the book location in the catalog ✓
Cache miss = Catalog doesn't know → go check the shelf directly
Stale data = Catalog says shelf 4A, but the book moved to 7C
```

## Five Strategies, Compared

### 1. TTL (Time-to-Live)
**"Reprint the catalog every month"**

```python
# Simple: data expires after a fixed time
cache.set("user:123", user_data, ttl=300)  # Expires in 5 minutes

# After 5 minutes, next request → cache miss → fresh DB query
```

| Pros | Cons |
|------|------|
| Simplest to implement | Data can be stale for up to TTL duration |
| No coordination needed | Short TTL = more DB load; long TTL = more staleness |
| Works for any data | Can't force refresh when data changes |

**Use when:** Staleness is acceptable (product listings, public profiles, config).

### 2. Write-Through
**"Every time a librarian shelves a book, update the catalog immediately"**

```python
def update_user(user_id, data):
    # Update BOTH database and cache atomically
    db.update(user_id, data)
    cache.set(f"user:{user_id}", data, ttl=3600)
    # Cache is always fresh — reads never see stale data
```

| Pros | Cons |
|------|------|
| Cache is always current | Writes are slower (update two places) |
| No stale data | Must remember to update cache on EVERY write path |
| Simple mental model | What if cache update fails? Inconsistency. |

**Use when:** You need strong consistency and can afford slower writes (user sessions, auth tokens).

### 3. Cache-Aside (Lazy Loading)
**"Catalog starts empty. First person to ask checks the shelf, then writes the location in the catalog."**

```python
def get_user(user_id):
    # 1. Check catalog (cache)
    cached = cache.get(f"user:{user_id}")
    if cached:
        return cached  # Cache hit — fast

    # 2. Cache miss — check the shelf (database)
    user = db.get_user(user_id)

    # 3. Write to catalog for next person
    cache.set(f"user:{user_id}", user, ttl=300)
    return user

def update_user(user_id, data):
    db.update(user_id, data)
    cache.delete(f"user:{user_id}")  # Remove stale entry
    # Next read will populate the cache with fresh data
```

| Pros | Cons |
|------|------|
| Only caches data that's actually read | First read after invalidation is slow |
| Simple and widely used | Small window of staleness possible |
| Cache only holds hot data | Must invalidate on every write |

**Use when:** Read-heavy workloads with occasional writes (most web apps — this is the default choice).

### 4. Event-Based Invalidation
**"When a book moves, send an announcement. Anyone with a catalog entry for that book tears it out."**

```python
# Publisher: when data changes, emit an event
def update_user(user_id, data):
    db.update(user_id, data)
    event_bus.publish("user.updated", {"user_id": user_id})

# Subscriber: invalidate cache on event
@event_bus.subscribe("user.updated")
def invalidate_user_cache(event):
    cache.delete(f"user:{event['user_id']}")

# Works across services: Service A updates → Service B's cache invalidated
```

| Pros | Cons |
|------|------|
| Decoupled — writer doesn't know about cache | Event delivery complexity (what if event is lost?) |
| Works across services | Eventual consistency (brief staleness between event and invalidation) |
| Scalable | Need event infrastructure (Redis Pub/Sub, Kafka, etc.) |

**Use when:** Multiple services cache the same data, or when write paths can't know about all caches.

### 5. Write-Behind (Write-Back)
**"Librarians note changes on sticky notes, update the catalog at end of day"**

```python
# Writes go to cache first, async-flushed to database
def update_user(user_id, data):
    cache.set(f"user:{user_id}", data)  # Fast — cache only
    write_queue.enqueue("user", user_id, data)  # Async flush to DB

# Background worker flushes periodically
@worker.task
def flush_writes():
    for table, id, data in write_queue.drain():
        db.update(id, data)
```

| Pros | Cons |
|------|------|
| Fastest writes (cache only) | Data loss risk if cache crashes before flush |
| Batches DB writes (efficient) | Complex — need write queue, flush logic |
| Great for high-write workloads | Reads from DB are stale during flush delay |

**Use when:** Write-heavy, can tolerate brief data loss risk (metrics, analytics, activity logs).

## Decision Flowchart

```
Is staleness acceptable for a few minutes?
├── YES → TTL-based caching (simplest)
└── NO → Is the data written by your service?
    ├── YES → Cache-aside with invalidation on write
    └── NO → Event-based invalidation (cross-service)

Is write performance critical?
├── YES → Write-behind (async flush)
└── NO → Write-through (synchronous update)
```

For most web applications, **cache-aside with TTL** is the right default. Add event-based invalidation when you need cross-service consistency.'''
    ),
    (
        "thinking/analogy-dependency-injection-to-power-outlets",
        "I keep reading about dependency injection but the explanations are always abstract and confusing. Can you explain it in a way that actually makes sense?",
        r'''<think>
Dependency injection — one of those concepts that sounds complicated but is actually simple. I need a concrete analogy.

**Power outlet analogy:**
Your laptop needs electricity. Two ways to get it:

1. **Without DI (hardcoded dependency):** The laptop has a nuclear reactor built inside. It generates its own power. You can never change the power source without rebuilding the laptop.

Wait, that's too extreme. Let me think of something more relatable...

**Restaurant analogy:**
A chef needs ingredients. Two approaches:

1. **Without DI:** Chef walks to the farm, picks tomatoes, milks the cow, grinds the wheat. The recipe (code) is tightly coupled to the ingredient source (dependency).

2. **With DI:** Restaurant manager delivers ingredients to the kitchen. Chef just uses whatever arrives. Chef doesn't know or care if tomatoes are from Farm A or Farm B. The ingredients are "injected" into the kitchen.

This is good but let me think of something even simpler...

**LEGO analogy:**
That might work... but let me try the most universal analogy: electrical outlets.

**Power outlet analogy (refined):**
- Your lamp needs electricity
- It doesn't generate its own power (that would be a hardcoded dependency)
- It has a PLUG (interface) that fits into any OUTLET (dependency provider)
- The lamp doesn't care WHERE the electricity comes from (solar, grid, generator)
- You can change the power source without changing the lamp

DI is: instead of a device generating its own power, it has a plug that accepts power from outside.

In code:
- The plug = the constructor parameter or function argument
- The outlet = whatever provides the dependency
- The device = your class/function

This maps well to testing too:
- Production: plug into the real database (wall outlet)
- Testing: plug into a mock database (battery pack)
- Same device, different power source, same behavior
</think>

Dependency injection is just **plugging things in from the outside instead of building them inside**. Think of electrical appliances.

## The Analogy: Power Outlets

```
WITHOUT dependency injection:
  Your lamp has a nuclear reactor built in.
  Want to test the lamp? Need a nuclear reactor.
  Want to use solar power? Rebuild the lamp.

WITH dependency injection:
  Your lamp has a PLUG.
  Wall outlet? Works. ✓
  Generator? Works. ✓
  Battery pack? Works. ✓
  Testing? Plug into a test outlet. ✓
  The lamp doesn't care WHERE power comes from.
```

## In Code: Before and After

```python
# ❌ WITHOUT DI: hardcoded dependency (nuclear reactor inside the lamp)

class OrderService:
    def __init__(self):
        # Creates its OWN database connection
        self.db = PostgresDatabase("postgres://prod-server:5432/mydb")
        # Creates its OWN payment processor
        self.payments = StripeClient(api_key="sk_live_xxx")

    def create_order(self, items):
        order = self.db.insert("orders", items)
        self.payments.charge(order.total)
        return order

# Problem: How do you TEST this?
# It connects to the REAL database and charges REAL money!
# You can't swap PostgresDatabase for a test database.
# You can't swap StripeClient for a fake payment processor.
```

```python
# ✅ WITH DI: dependencies plugged in from outside (lamp with a plug)

class OrderService:
    def __init__(self, db, payments):
        # Receives dependencies — doesn't create them
        self.db = db          # Any database that has an .insert() method
        self.payments = payments  # Any payment processor with a .charge() method

    def create_order(self, items):
        order = self.db.insert("orders", items)
        self.payments.charge(order.total)
        return order


# PRODUCTION: plug in real dependencies
service = OrderService(
    db=PostgresDatabase("postgres://prod-server:5432/mydb"),
    payments=StripeClient(api_key="sk_live_xxx"),
)

# TESTING: plug in fake dependencies
service = OrderService(
    db=InMemoryDatabase(),         # Fast, no real DB needed
    payments=FakePaymentProcessor(),  # Doesn't charge real money
)

# STAGING: plug in staging dependencies
service = OrderService(
    db=PostgresDatabase("postgres://staging:5432/mydb"),
    payments=StripeClient(api_key="sk_test_xxx"),
)
```

## Why This Matters: Testing

```python
# Without DI: testing is a nightmare
def test_create_order():
    service = OrderService()  # Connects to real DB, charges real cards!
    # Can't test without production infrastructure running


# With DI: testing is trivial
class FakeDB:
    def __init__(self):
        self.records = []
    def insert(self, table, data):
        record = {"id": len(self.records) + 1, **data}
        self.records.append(record)
        return type('Order', (), record)()

class FakePayments:
    def __init__(self):
        self.charges = []
    def charge(self, amount):
        self.charges.append(amount)

def test_create_order():
    db = FakeDB()
    payments = FakePayments()
    service = OrderService(db, payments)

    service.create_order({"item": "Widget", "total": 29.99})

    assert len(db.records) == 1
    assert payments.charges == [29.99]
    # No real database. No real charges. Fast. Reliable.
```

## Three Ways to "Plug Things In"

```python
# 1. Constructor injection (most common — plug in when creating)
class OrderService:
    def __init__(self, db, payments):  # Dependencies are parameters
        self.db = db
        self.payments = payments

# 2. Function injection (simplest — plug in per call)
def create_order(db, payments, items):  # Dependencies are function args
    order = db.insert("orders", items)
    payments.charge(order.total)
    return order

# 3. Framework injection (Django, FastAPI — framework plugs things in)
from fastapi import Depends

def get_db():
    db = Database()
    try:
        yield db
    finally:
        db.close()

@app.post("/orders")
def create_order(items: list, db=Depends(get_db)):
    # FastAPI "plugs in" the db dependency automatically
    return db.insert("orders", items)
```

## The One-Sentence Summary

```
Dependency Injection = "Don't build your own power source.
                        Have a plug. Let someone else provide the electricity."
```

That's it. Pass dependencies in instead of creating them internally. It makes code testable, flexible, and decoupled. No frameworks or complex patterns needed — just use function/constructor parameters.'''
    ),
    (
        "thinking/analogy-ci-cd-to-assembly-line",
        "How do I explain our CI/CD pipeline to non-technical stakeholders who want to understand why we invest time in it?",
        r'''<think>
CI/CD for non-technical stakeholders. They need to understand the VALUE, not the technology.

**Assembly line / manufacturing analogy:**
This is the classic analogy and it works well because manufacturing executives understand quality control.

Before CI/CD = handcrafted products:
- Each craftsman builds the entire product by hand
- Quality varies by craftsman
- Defects found by customers
- Can't scale production

With CI/CD = automated assembly line:
- Standardized process, automated quality checks
- Every product goes through the same inspections
- Defects caught before shipping
- Can scale production

This maps perfectly:
- Code commit = raw materials entering the assembly line
- CI (testing) = quality inspection stations
- CD (deployment) = shipping to customers
- Defects caught in CI = defects caught before shipping = saves money

The key business metric: cost of finding a bug
- In development: $1
- In testing/CI: $10
- In staging: $100
- In production: $1,000-10,000 (customer impact, emergency fixes, reputation)
</think>

Think of our CI/CD pipeline as an **automated assembly line with quality inspection stations**. Every code change passes through the same inspections before it reaches customers.

## The Analogy

```
WITHOUT CI/CD (handcrafted):
  Developer writes code → Ships directly to customers
  Quality depends on individual developer's attention
  Defects found BY CUSTOMERS (expensive, embarrassing)

WITH CI/CD (assembly line):
  Developer writes code
    → Inspection Station 1: Does it compile? ✓
    → Inspection Station 2: Do all 3,000 tests pass? ✓
    → Inspection Station 3: Security scan clear? ✓
    → Inspection Station 4: Performance acceptable? ✓
    → Approved for shipping → Delivered to customers
  Defects caught BEFORE customers see them
```

## Why It Saves Money

```
Cost of finding a bug:

  During development:    ~$1      (developer fixes it immediately)
  During CI/CD testing:  ~$10     (automated test catches it)
  In staging:            ~$100    (manual testing finds it)
  In production:         ~$10,000 (customer complaint, emergency fix,
                                   potential data loss, reputation damage)

Our CI/CD pipeline catches bugs at the $10 stage
instead of the $10,000 stage.
```

## What Each Station Does (Business Terms)

| Pipeline Stage | Manufacturing Analogy | Business Value |
|---------------|----------------------|---------------|
| **Build** | Assembling the product | "Can we even build it?" |
| **Unit Tests** | Testing individual components | "Does each part work correctly?" |
| **Integration Tests** | Testing assembled product | "Do the parts work together?" |
| **Security Scan** | Safety inspection | "Is it safe for customers?" |
| **Staging Deploy** | Test drive / QA | "Does it work in real conditions?" |
| **Production Deploy** | Ship to customers | "Deliver with confidence" |

## The Numbers That Matter

```
BEFORE CI/CD:
  - Deploy frequency: once every 2 weeks (risky, big batches)
  - Time to fix production bug: 4-8 hours (emergency)
  - Bugs found by customers: ~5 per month
  - Developer confidence in deploys: low ("deploy Friday? No way.")

AFTER CI/CD:
  - Deploy frequency: multiple times per day (small, safe changes)
  - Time to fix production bug: <1 hour (small change, easy to identify)
  - Bugs found by customers: ~0.5 per month (caught by pipeline)
  - Developer confidence in deploys: high ("deploy Friday? Sure.")
```

## Why We Invest Time in It

The pipeline costs time to build and maintain, but it pays for itself through:
1. **Fewer production incidents** → less emergency work → happier customers
2. **Faster delivery** → deploy daily instead of biweekly → features reach customers faster
3. **Lower risk per deploy** → small changes → easy to identify and fix problems
4. **Developer productivity** → less time fighting fires → more time building features

The assembly line metaphor works because every manufacturing executive understands that automated quality inspection is cheaper than product recalls.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
