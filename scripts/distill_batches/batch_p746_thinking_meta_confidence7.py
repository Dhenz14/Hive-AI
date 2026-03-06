"""Phase 3D: Metacognition — Confidence Calibration Under Pressure (Part 7)

Final batch to reach 50 pairs for Phase 3D.
"""

PAIRS = [
    (
        "thinking/meta-confidence-ambiguous-bug-data-loss",
        r'''Users are reporting that data they saved yesterday is gone today. Our database shows the records exist but the app doesn't display them. What's happening?''',
        r'''<think>
I'm uncertain but can systematically narrow the possibilities.

What I'm confident about:
- "Records exist in DB but app doesn't show them" rules out data loss — the problem is in the query or display layer
- This is NOT a database corruption issue — the data is there
- The gap between "data exists" and "data doesn't display" narrows the problem to: query filters, permissions, caching, or frontend rendering

What I'm uncertain about:
- Whether the records are correctly associated with the user's account
- Whether a recent code change affected the query filters
- Whether a cache is serving stale data (showing an old version without the new records)
- Whether the frontend received the data but fails to render it

Hypotheses ranked:
1. Query filter change (HIGH): A recent change to the WHERE clause excludes records that should be included
2. Caching stale data (HIGH): Redis or CDN serving yesterday's version
3. Permission/scope change (MEDIUM): User's role or scope changed, hiding records
4. Frontend rendering bug (MEDIUM): API returns data but UI doesn't render it
5. Data association issue (LOW): Records linked to wrong user/account
</think>

**Good news: the data isn't lost.** Since records exist in the database, this is a display/query issue, not data loss.

**I can't identify the exact cause, but here's how to diagnose (check in order):**

**1. Check if the API returns the data (2 minutes)**
```bash
# Hit the API directly — does it return the "missing" records?
curl -H "Authorization: Bearer <user_token>" https://api.yourapp.com/records

# If API returns them → frontend rendering bug
# If API doesn't return them → backend query/filter issue
```

**2. Check if caching is the problem (1 minute)**
```bash
# Clear cache and retry
redis-cli FLUSHDB  # If using Redis cache
# Or: add ?nocache=1 to the URL
# If data appears after cache clear → stale cache
```

**3. Check the database query (2 minutes)**
```sql
-- What the app queries:
SELECT * FROM records WHERE user_id = 123 AND is_active = true;
-- vs what exists:
SELECT * FROM records WHERE user_id = 123;
-- If counts differ: a filter is hiding records
-- Check: is_active, status, deleted_at, visibility fields
```

**4. Check recent deployments**
```bash
git log --since="2 days ago" --oneline
# Look for changes to: queries, filters, serializers, permissions
```

**Ranked hypotheses:**

| Cause | Probability | Diagnostic |
|-------|------------|-----------|
| Query filter excluding records | High | Compare raw DB vs API results |
| Stale cache | High | Clear cache, recheck |
| Permission/scope change | Medium | Compare user's roles before/after |
| Frontend rendering bug | Medium | Check browser Network tab |
| Soft-delete flag set incorrectly | Medium | Check `is_active`/`deleted_at` columns |

**What I'm uncertain about:** Whether this affects all users or specific users (which would change the diagnosis entirely).'''
    ),
    (
        "thinking/meta-confidence-emerging-tech-serverless",
        r'''Is serverless (AWS Lambda) the future of backend development? Should I build everything serverless?''',
        r'''<think>
I have opinions but should be honest about uncertainty in predictions.

What I'm confident about:
- Serverless is great for certain workloads (event-driven, variable traffic, glue code)
- Serverless is NOT great for everything (long-running processes, WebSockets, consistent low latency)
- "The future" claims are premature — containers and servers aren't going away
- Cold starts are a real issue for user-facing latency requirements
- Vendor lock-in is significant with serverless

What I'm uncertain about:
- Whether cold start improvements will eventually make serverless viable for all use cases
- The long-term cost comparison at scale (serverless can be expensive at high volume)
- Whether the developer experience will improve enough for complex applications
</think>

**Serverless is a great tool for specific use cases, but "build everything serverless" is premature.** Here's my honest assessment:

**What I'm confident about — serverless excels at:**
- Event-driven workloads (image processing, webhooks, file triggers)
- Variable/bursty traffic (scale to zero when idle)
- Scheduled tasks (cron-like functions)
- API endpoints with low traffic (<100 req/s)
- Glue code between AWS services

**What I'm confident about — serverless struggles with:**
- WebSockets / long-lived connections
- Sub-100ms latency requirements (cold starts)
- Long-running processes (>15 min timeout)
- Complex stateful applications
- High-volume APIs (cost becomes prohibitive)
- Local development and debugging

**Cost comparison I'm fairly confident about:**
```
Low traffic (1K requests/day):
  Lambda: ~$0.01/month  ← serverless wins
  EC2 t3.micro: $8/month

High traffic (1M requests/day):
  Lambda: ~$100-300/month
  EC2 t3.medium: $30/month  ← server wins

Very high traffic (100M requests/day):
  Lambda: ~$10,000-30,000/month  ← serverless loses badly
  EC2 fleet: ~$500-2,000/month
```

**What I'm uncertain about:**
- Whether cold starts will be "solved" in the future
- The true total cost when you include API Gateway, CloudWatch, etc.
- Whether serverless frameworks (SST, Serverless Framework) have matured enough for complex apps

**My honest recommendation:**
Use serverless for event-driven backends and low-traffic APIs. Use containers/servers for user-facing APIs with consistent traffic. Many successful architectures use BOTH — serverless for background processing, containers for the main API.

"Build everything serverless" is marketing, not engineering advice.'''
    ),
    (
        "thinking/meta-confidence-debug-no-repro-race",
        r'''We have a bug where sometimes two users end up with the same order number. It happens maybe once a week out of thousands of orders. We use auto-increment IDs and a separate order_number field. Our code:

```python
def create_order(user_id, items):
    last_order = Order.query.order_by(Order.order_number.desc()).first()
    new_number = (last_order.order_number + 1) if last_order else 1000
    order = Order(user_id=user_id, order_number=new_number, items=items)
    db.session.add(order)
    db.session.commit()
    return order
```

Why does this happen?''',
        r'''<think>
I'm quite confident about this one — this is a classic race condition.

What I'm confident about:
- This is a textbook TOCTOU (Time of Check to Time of Use) race condition
- Two concurrent requests read the same "last order number," both increment it, both try to insert with the same new number
- Once a week out of thousands = perfectly consistent with a race condition (happens when two orders are created within milliseconds)
- The fix is either a database sequence, a UNIQUE constraint, or SELECT FOR UPDATE

What I'm less certain about:
- Whether they have a UNIQUE constraint on order_number (if they don't, both inserts succeed with duplicate numbers — which matches the bug)
- Whether they're using multiple gunicorn workers (more workers = more likely race)
</think>

**I'm quite confident about this: it's a classic race condition.**

**What happens:**
```
Thread A: reads last order_number = 5042
Thread B: reads last order_number = 5042 (same value, concurrent)
Thread A: inserts order_number = 5043
Thread B: inserts order_number = 5043  ← DUPLICATE
```

This happens when two orders are created within milliseconds of each other — consistent with "once a week out of thousands."

**Fix — use a database sequence (best):**
```sql
-- PostgreSQL: create a sequence for order numbers
CREATE SEQUENCE order_number_seq START 1000;
ALTER TABLE orders ADD CONSTRAINT unique_order_number UNIQUE (order_number);
```

```python
def create_order(user_id, items):
    # Database generates the number atomically — no race condition
    result = db.session.execute(text("SELECT nextval('order_number_seq')"))
    new_number = result.scalar()
    order = Order(user_id=user_id, order_number=new_number, items=items)
    db.session.add(order)
    db.session.commit()
    return order
```

**Alternative fix — UNIQUE constraint + retry:**
```python
from sqlalchemy.exc import IntegrityError

def create_order(user_id, items, max_retries=3):
    for attempt in range(max_retries):
        try:
            last_order = Order.query.order_by(Order.order_number.desc()).first()
            new_number = (last_order.order_number + 1) if last_order else 1000
            order = Order(user_id=user_id, order_number=new_number, items=items)
            db.session.add(order)
            db.session.commit()
            return order
        except IntegrityError:
            db.session.rollback()
            continue
    raise Exception("Failed to generate unique order number")
```

**Why the database sequence is better:**
- Atomic — no race condition possible
- No retry logic needed
- Works across any number of concurrent workers
- Guaranteed unique and sequential

**What I'm uncertain about:**
- Whether you currently have a UNIQUE constraint on `order_number` (if not, add one immediately as a safety net regardless of the fix)'''
    ),
    (
        "thinking/meta-confidence-arch-unfamiliar-iot",
        r'''I'm building an IoT system to collect temperature readings from 10,000 sensors every 5 seconds. How should I design the data pipeline?''',
        r'''<think>
I have general knowledge of data pipeline architecture but I'm not an IoT domain expert.

What I'm confident about:
- 10,000 sensors × 1 reading/5 sec = 2,000 readings/second — substantial but manageable
- This is a time-series data problem — specialized databases (TimescaleDB, InfluxDB) are designed for this
- Standard REST APIs won't handle 2K writes/second well — need a message queue or specialized ingestion
- Data retention and downsampling are important for long-term storage

What I'm uncertain about:
- IoT-specific protocols (MQTT vs HTTP vs CoAP — I know MQTT is standard but I'm not an expert)
- Edge computing considerations (should sensors batch locally?)
- Reliability requirements (is missing a reading acceptable?)
- Network constraints (are sensors on cellular? WiFi? LoRa?)
- Whether 10K sensors are in one location or globally distributed

What I definitely don't know:
- The physical deployment environment
- Network bandwidth and reliability
- Required data retention period
- Real-time alerting requirements
- Whether sensors can buffer data locally
</think>

I can outline a general architecture, but **I want to flag that I'm not an IoT domain expert.** My confidence varies across different parts of this design.

**What I'm confident about — the data flow:**

```
Sensors → Message Broker → Processing → Time-Series DB → Visualization
```

**Scale calculation I'm confident about:**
```
10,000 sensors × 1 reading/5 sec = 2,000 writes/second
× ~100 bytes per reading = ~200 KB/s = ~17 GB/day
```

**Architecture I'm fairly confident about:**

```
Sensors ──MQTT──→ Mosquitto/EMQX ──→ Processing ──→ TimescaleDB
                   (message broker)    (Python/Go)    (time-series DB)
                                           │
                                           ├──→ Redis (real-time alerts)
                                           └──→ Grafana (dashboards)
```

**What I'm uncertain about:**

| Component | My confidence | Recommendation |
|-----------|-------------|----------------|
| MQTT as protocol | Medium | Standard for IoT, but verify for your sensors |
| TimescaleDB vs InfluxDB | Low | Both work; I'd lean TimescaleDB (PostgreSQL-based) but consult IoT engineers |
| Edge buffering | Low | Depends on network reliability — ask someone with field experience |
| Data retention policy | Can't advise | Depends on your compliance and analysis needs |

**What I'd confidently recommend:**
1. Use a time-series database (not regular PostgreSQL) — purpose-built for this workload
2. Use a message broker between sensors and DB — buffers bursts, decouples components
3. Downsample old data — keep 5-sec resolution for 7 days, 1-min averages for 90 days, hourly for years
4. Set up real-time alerting for anomalies (temperature out of range)

**What you should consult an IoT specialist about:**
- Sensor communication protocol (MQTT, CoAP, HTTP, proprietary)
- Network topology and reliability
- Edge computing needs
- Firmware update strategy
- Security (sensor authentication, data encryption in transit)

I can help with the backend data pipeline, but the IoT-specific decisions should involve someone with field deployment experience.'''
    ),
    (
        "thinking/meta-confidence-code-review-unfamiliar",
        r'''I found this in our codebase. Is this correct?

```python
import asyncio
from contextlib import asynccontextmanager

_lock = asyncio.Lock()
_cache = {}

@asynccontextmanager
async def get_or_create(key, factory):
    async with _lock:
        if key not in _cache:
            _cache[key] = await factory()
        yield _cache[key]
```''',
        r'''<think>
I can evaluate the async patterns but I'm uncertain about the intended use case.

What I'm confident about:
- This is an async context manager that provides cached lazy initialization
- The asyncio.Lock() ensures only one coroutine creates the value for a given key
- Module-level _lock and _cache mean this is global state — shared across the application

What I'm uncertain about:
- Whether the lock granularity is correct — locking on ALL keys while creating one key blocks everything
- Whether the intended use case requires a context manager (yield) or could be a simple function
- Whether the cache should have eviction/TTL
- Whether this runs in a single event loop or multiple (module-level lock only works within one loop)

What I'd flag in a review:
1. The lock is coarse-grained — creating key "A" blocks reads for key "B"
2. Module-level asyncio.Lock() might fail if created before the event loop starts
3. No error handling — if factory() fails, the key is never cached, and the next call tries again (this might be intentional)
4. No cache invalidation mechanism
</think>

I can evaluate the async patterns, but **I'm uncertain about the intended use case**, which affects whether this is correct.

**What I'm confident is correct:**
- The `asynccontextmanager` pattern works syntactically
- The lock prevents duplicate creation of the same key
- If factory() succeeds, subsequent calls return the cached value

**What I'd flag in review (potential issues):**

**1. Coarse-grained lock (likely a problem):**
```python
# Creating key "A" blocks ALL reads/creates for key "B"
async with _lock:  # Global lock — only one operation at a time
```

Fix with per-key locking:
```python
_locks = {}

@asynccontextmanager
async def get_or_create(key, factory):
    if key not in _locks:
        _locks[key] = asyncio.Lock()
    async with _locks[key]:  # Only locks this specific key
        if key not in _cache:
            _cache[key] = await factory()
        yield _cache[key]
```

**2. Module-level Lock() timing (uncertain):**
```python
# asyncio.Lock() created at module import time
# In some frameworks, the event loop doesn't exist yet
# Could cause: "no current event loop" error
_lock = asyncio.Lock()  # Might fail depending on when module is imported
```

**3. No error handling for factory():**
```python
# If factory() raises, key is not cached
# Next caller retries (maybe intentional, maybe not)
# If factory() partially completes, no cleanup
```

**4. No cache invalidation:**
```python
# Values cached forever — no TTL, no eviction
# Could leak memory if keys accumulate
```

**What I can't determine without more context:**
- Whether the context manager (yield) is needed, or a simple `async def` returning the value would work
- Whether the cache should ever be cleared
- Whether this code runs in multiple event loops (e.g., multiple processes)
- The intended lifecycle of cached values

This code works for simple cases, but the coarse lock could be a bottleneck under load.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
