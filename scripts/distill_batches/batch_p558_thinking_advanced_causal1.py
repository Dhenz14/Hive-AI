"""Phase 2E: Advanced Reasoning — Causal & Counterfactual Reasoning (Part 1/4)
Root cause analysis: production outages, performance regressions, data inconsistencies.
'Why did this happen?' and 'What if we had done X instead?'"""

PAIRS = [
    (
        "thinking/causal-production-outage-rca",
        "Our API went down at 3:14 AM. Monitoring shows: memory usage spiked from 2GB to 8GB over 10 minutes, then OOM killed the process. CPU was normal. Request rate was normal. The deploy at 2:00 AM was a 'minor CSS change'. What happened?",
        r'''<think>
Let me systematically eliminate possible causes.

The bug manifests as: memory spike from 2GB → 8GB in 10 minutes, with normal CPU and normal request rate.

Possible causes:
1. Memory leak introduced by the deploy
2. Scheduled job that runs at ~3 AM
3. Memory leak that was already present, just hit the threshold
4. External dependency returning larger-than-expected responses
5. Caching issue (unbounded cache growth)

Let me evaluate each:

Cause 1: Deploy at 2:00 AM was "minor CSS change"
- CSS changes shouldn't affect server memory... unless:
  - The deploy included other changes (check the diff!)
  - The deploy process itself causes memory spike (container restart, cache warming)
  - Someone snuck in a code change with the CSS
- If this were the cause, memory should spike immediately at 2:00 AM, not at 3:14 AM (74 minutes later)
- Verdict: Unlikely as DIRECT cause, but check the actual diff

Cause 2: Scheduled job at ~3 AM
- A cron job that loads large datasets into memory would explain the timing
- Normal CPU + high memory = loading data into memory without heavy processing
- This would also explain why request rate is normal (it's a background job, not user traffic)
- Verdict: LIKELY. Check for cron jobs scheduled between 3:00-3:15 AM.

Cause 3: Existing memory leak hitting threshold
- Memory leaks are usually linear growth over hours/days
- This was sudden (10 minutes) — not a slow leak
- Unless something accelerated it (batch processing)
- Verdict: Possible but the suddenness argues against slow leak

Cause 4: External dependency
- If an API we call started returning 100x larger responses
- Would cause memory spike as we buffer responses
- But normal request rate suggests normal external traffic
- Verdict: Possible, check response sizes in logs

Cause 5: Unbounded cache
- If a cache grows without eviction policy
- But should be gradual, not sudden
- Unless cache warming happens at 3 AM
- Verdict: Possible if cache warm-up is scheduled

Most likely: Cause 2 (scheduled job) because:
- Timing matches (3:14 AM, not 2:00 AM deploy time)
- Memory spike without CPU spike = loading data
- Normal request rate = not user traffic
- 10-minute spike = batch processing a dataset

Counterfactual: If we had a memory limit on the scheduled job (or ran it in a separate process), the main API would have been unaffected. If the job used streaming instead of loading everything into memory, it wouldn't have OOM'd at all.
</think>

**Root Cause Analysis — systematic elimination**:

```
Symptom: Memory 2GB → 8GB over 10 minutes at 3:14 AM
Concurrent: CPU normal, request rate normal, deploy at 2:00 AM

Hypothesis 1: Deploy caused it
  Evidence FOR: deploy happened 74 minutes before
  Evidence AGAINST: CSS change shouldn't affect memory; 74-minute delay
  if deploy → memory spike, should see spike at 2:00 AM, not 3:14
  VERDICT: ❌ Ruled out (timing doesn't match)

Hypothesis 2: Scheduled batch job at 3 AM
  Evidence FOR: timing matches; high memory + normal CPU = loading data
  Evidence FOR: normal request rate = not user traffic causing it
  Test: check crontab and scheduler logs for 3:00-3:15 window
  VERDICT: ✅ Most likely

Hypothesis 3: Slow memory leak hitting threshold
  Evidence AGAINST: spike took 10 minutes, leaks are gradual (hours/days)
  VERDICT: ❌ Ruled out (too sudden)

Hypothesis 4: External API returning oversized responses
  Test: check response size logs for external calls
  VERDICT: ❓ Possible but request rate was normal
```

**Investigation commands**:
```bash
# Check for scheduled jobs at that time
crontab -l | grep -i "3:"
kubectl get cronjobs -o wide

# Check deploy diff — was it REALLY just CSS?
git diff HEAD~1..HEAD --stat
# If more than CSS files changed → investigate further

# Check memory-heavy operations in logs
grep "3:1[0-9]" /var/log/app.log | grep -i "batch\|import\|sync\|export"

# Check for streaming vs load-all patterns
grep -r "\.fetchall()\|\.read()\|json\.load(" src/ | head -20
```

**Root cause found** (after investigation):
```python
# The culprit: nightly report job loads ALL orders into memory
@scheduler.cron("0 3 * * *")  # Runs at 3:00 AM
async def generate_daily_report():
    orders = await db.fetch("SELECT * FROM orders WHERE date = today()")
    # ← Loads 500K rows into memory at once!
    # Each row ≈ 10KB → 500K × 10KB = 5GB memory spike
    report = process_orders(orders)  # 10 minutes to process
    await send_report(report)
```

**The fix**:
```python
@scheduler.cron("0 3 * * *")
async def generate_daily_report():
    # Stream results instead of loading all into memory
    report = ReportBuilder()
    async for batch in db.fetch_batches(
        "SELECT * FROM orders WHERE date = today()",
        batch_size=1000  # Process 1000 at a time, ~10MB in memory
    ):
        report.add_batch(batch)
    await send_report(report.build())
```

**Counterfactual**: If we had run the report job in a **separate process** (not the API server), the OOM would have killed the report job, not the API. If we had used **streaming** from the start, memory would have stayed at ~50MB regardless of data size. If we had **memory limits** on the container, it would have restarted faster instead of swapping for 10 minutes.

**Prevention**: Add memory-limit alerts at 70% threshold. Run batch jobs in separate worker processes. Code review flag for `.fetchall()` on unbounded queries.'''
    ),
    (
        "thinking/causal-perf-regression-deploy",
        "After yesterday's deploy, our P99 latency went from 200ms to 1.5 seconds. P50 is unchanged at 50ms. The deploy added a user preferences feature. CPU and memory look normal. What's happening?",
        r'''<think>
Let me analyze the clues carefully.

Key observations:
1. P50 unchanged (50ms) but P99 jumped (200ms → 1500ms)
2. New "user preferences" feature deployed
3. CPU and memory normal

The fact that P50 is unchanged but P99 spiked tells me something important: MOST requests are fine, but a TAIL of requests is very slow. This rules out:
- Global slowdown (would affect P50 too)
- Database connection exhaustion (would affect all requests)
- Network issues (would affect all requests)

What causes P99 to spike while P50 stays the same?

Hypothesis 1: The new feature itself is slow for SOME users
- If "user preferences" loads data for users who have preferences set
- Users without preferences: fast (no extra query)
- Users with preferences: slow (extra query or N+1)
- This would affect the percentage of users who have preferences
- If 5% of users have preferences → P95 might be fine but P99 is slow

Hypothesis 2: New database query without index
- The preferences query hits the DB for every request
- Most times: fast (index hit or small table scan)
- Sometimes: slow (query plan chooses table scan on certain inputs)
- Would explain tail latency without affecting median

Hypothesis 3: External API call in the preferences feature
- If preferences include "load theme from CDN" or "sync with external service"
- Timeout set to 2 seconds → P99 = timeout duration
- Only affects users who trigger the feature

Hypothesis 4: Lock contention from new code
- If the preferences feature introduced a lock
- Most requests: uncontended (fast)
- Some requests: contend for the lock (slow)
- Would show as P99 spike without CPU increase

Let me think about what's most likely...

The "user preferences" feature probably added a database query on the hot path (every request checks user preferences). Most users don't have preferences yet (the feature is new), so the query returns empty quickly. But for users who DO have preferences, or when the query takes longer (no index), it adds significant latency.

Actually, the most common pattern: the preferences are loaded via a SYNCHRONOUS external call or a missing database index on the new table.

Let me check: P99 went from 200ms to 1500ms. That's a 1300ms addition. What takes exactly ~1300ms? A DNS resolution + TCP connection to an external service = ~1-2 seconds. Or a table scan on a million-row table without index.

Most likely: the new preferences feature makes a synchronous call to load something, and for ~1-5% of requests it's slow (connection pooling issue, DNS resolution, or missing index).
</think>

**The P99/P50 gap is the key diagnostic clue.** P50 unchanged means MOST requests are fine. P99 spiked means a TAIL of requests is very slow. This is NOT a global problem — it's specific to certain request paths or conditions.

**Systematic elimination**:
```
Clue: P50 = 50ms (unchanged), P99 = 1500ms (7.5x increase)
This means: ~95% of requests are unaffected, ~1-5% are very slow

Global causes? NO — would affect P50 too
  ❌ Database overload (all queries slower)
  ❌ Network congestion (all requests slower)
  ❌ Memory pressure / GC pauses (random, affects all)

Targeted causes? YES — only certain requests are slow
  ✅ New code path that's slow for SOME requests
  ✅ Missing database index on new table
  ✅ External call with high tail latency
  ✅ Lock contention from new code
```

**Investigation steps**:
```bash
# 1. Compare request latency BY ENDPOINT
# Did the new preferences endpoint add overall latency, or is it a sidecar effect?
SELECT path, percentile_cont(0.99) WITHIN GROUP (ORDER BY duration_ms)
FROM request_logs
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY path
ORDER BY percentile_cont DESC;

# 2. Check if slow requests correlate with the new feature
SELECT has_preferences, COUNT(*),
       percentile_cont(0.50) WITHIN GROUP (ORDER BY duration_ms) as p50,
       percentile_cont(0.99) WITHIN GROUP (ORDER BY duration_ms) as p99
FROM request_logs JOIN users ON request_logs.user_id = users.id
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY has_preferences;

# 3. Check for missing index on new table
EXPLAIN ANALYZE SELECT * FROM user_preferences WHERE user_id = 12345;
-- If "Seq Scan" appears → missing index!

# 4. Check for slow external calls
grep "preferences" /var/log/app.log | grep "duration" | sort -t= -k2 -n -r | head
```

**Root cause found** (most common pattern):
```python
# The deploy added this to the request middleware:
async def load_user_preferences(request):
    user = request.state.user
    # This query runs on EVERY request, but the table has no index on user_id!
    prefs = await db.fetch_one(
        "SELECT * FROM user_preferences WHERE user_id = $1", user.id
    )
    # For most users: table scan finds nothing quickly (early exit)
    # For users with preferences: table scan reads all rows → 1500ms
    request.state.preferences = prefs
```

**The fix**:
```sql
-- Immediate fix: add the missing index
CREATE INDEX CONCURRENTLY idx_user_prefs_user_id
ON user_preferences(user_id);
-- Query goes from 1500ms table scan → 0.1ms index lookup
```

```python
# Architectural fix: lazy-load preferences, don't block every request
class UserPreferences:
    def __init__(self, user_id: str, db):
        self._user_id = user_id
        self._db = db
        self._loaded = False
        self._prefs = {}

    async def get(self, key: str, default=None):
        if not self._loaded:
            row = await self._db.fetch_one(
                "SELECT * FROM user_preferences WHERE user_id = $1",
                self._user_id
            )
            self._prefs = dict(row) if row else {}
            self._loaded = True
        return self._prefs.get(key, default)

# Only loads preferences when actually accessed, not on every request
```

**Counterfactual analysis**:
- If the index had been included in the migration → no performance impact
- If preferences were lazy-loaded → only requests USING preferences would be affected
- If the feature had been behind a feature flag (disabled by default) → zero impact on existing users
- If there was a P99 latency alert at 500ms → caught in 5 minutes, not discovered next morning

**Prevention checklist for new features**:
```
□ New tables have indexes on foreign keys and WHERE clause columns
□ New queries tested with EXPLAIN ANALYZE on production-size data
□ New middleware is lazy (don't load data until needed)
□ P99 latency alerts configured per endpoint
□ Feature flags for gradual rollout
```'''
    ),
    (
        "thinking/causal-data-inconsistency",
        "Our order totals in the orders table don't match the sum of line items in the order_items table. About 2% of orders have mismatched totals. The discrepancy appeared gradually over the last 3 months. What could cause this?",
        r'''<think>
Data inconsistency between parent and child records, appearing gradually. Let me think about what could cause this.

The discrepancy is: orders.total != SUM(order_items.price * order_items.quantity)

Let me enumerate possible causes:

1. Race condition in concurrent updates
   - Two requests modify the same order simultaneously
   - Request A adds item → calculates total → writes total
   - Request B adds item → calculates total (without A's item) → writes total
   - Result: total reflects only B's items, missing A's
   - Would explain gradual appearance (happens when two updates collide)

2. Application-level calculation error
   - Rounding differences between float and decimal
   - Different code paths calculate totals differently
   - Mobile app vs web app calculate differently
   - Would be consistent and reproducible

3. Partial failure during multi-step operation
   - App inserts order_items, then updates order.total
   - If crash/timeout between these two steps → items exist without total update
   - Would explain gradual appearance (occasional crashes)

4. Direct database modification
   - Someone ran UPDATE orders SET total = ... directly
   - Or a migration modified totals incorrectly
   - Would be a one-time event, not gradual

5. Trigger/stored procedure bug
   - If a trigger recalculates totals, it might miss some items
   - Or fire before the transaction commits

6. Caching stale data
   - App reads cached total, adds item, recalculates from stale cached subtotals
   - Cache invalidation failure

7. Currency/rounding in bulk operations
   - Bulk discount applied to order but not individual items
   - Tax calculated on order total vs sum of item taxes
   - This wouldn't be a "bug" per se but intentional difference

Timing: "gradually over 3 months" — this rules out one-time events (migration, manual SQL). It points to a probabilistic cause: race condition (#1) or partial failure (#3) or edge case calculation (#2).

2% rate — not rare, but not every order. This is consistent with:
- Race condition: happens when two actions happen within a small window
- Partial failure: occasional connection drops or timeouts
- Specific code path: one of many checkout flows has a bug

Let me investigate which is most likely. The key question: do the discrepancies have a PATTERN?
- If discrepancy = exactly one line item → partial failure (item added, total not updated)
- If discrepancy = rounding error ($0.01-0.02) → floating point or rounding
- If discrepancy = matches another item → race condition (one item's value overwritten)
- If discrepancy only from mobile app → code path bug

I'll recommend the investigation approach.
</think>

**Systematic investigation — the discrepancy pattern reveals the cause**:

```sql
-- Step 1: Characterize the discrepancies
SELECT
    o.id,
    o.total AS stored_total,
    SUM(oi.price * oi.quantity) AS calculated_total,
    o.total - SUM(oi.price * oi.quantity) AS discrepancy,
    ABS(o.total - SUM(oi.price * oi.quantity)) AS abs_discrepancy,
    o.created_at,
    o.updated_at,
    o.source  -- web, mobile, api?
FROM orders o
JOIN order_items oi ON o.id = oi.order_id
GROUP BY o.id
HAVING o.total != SUM(oi.price * oi.quantity)
ORDER BY o.created_at DESC
LIMIT 100;
```

**Interpreting the pattern**:
```
If discrepancy pattern is...       Likely cause
────────────────────────────       ────────────────
Always $0.01-$0.02                 Floating point rounding
Always equals one line item's price  Race condition (item added after total calc)
Always negative (stored < actual)  Partial failure (items added, total not recalculated)
Only from source='mobile'          Mobile app calculation bug
Only on orders with 5+ updates     Race condition under concurrent edits
Random amounts, no pattern         Manual SQL or migration error
```

**Most likely cause: race condition in concurrent updates** (2% rate + gradual appearance):
```python
# THE BUG — no transaction isolation
async def add_item_to_order(order_id: str, item: dict):
    # Thread A reads current items        ← Thread B also reads here
    items = await db.fetch(
        "SELECT * FROM order_items WHERE order_id = $1", order_id
    )
    # Thread A inserts new item
    await db.execute(
        "INSERT INTO order_items (order_id, price, qty) VALUES ($1, $2, $3)",
        order_id, item["price"], item["qty"]
    )
    # Thread A calculates total from items ← STALE! Doesn't include Thread B's item
    total = sum(i["price"] * i["qty"] for i in items) + item["price"] * item["qty"]

    # Thread A writes total               ← OVERWRITES Thread B's total
    await db.execute(
        "UPDATE orders SET total = $1 WHERE id = $2",
        total, order_id
    )
    # If Thread B does the same thing concurrently, one thread's total wins
    # and the other's item is "invisible" to the stored total
```

**The fix — use a transaction with proper locking**:
```python
async def add_item_to_order(order_id: str, item: dict):
    async with db.transaction():
        # Lock the order row — other transactions wait
        await db.execute(
            "SELECT id FROM orders WHERE id = $1 FOR UPDATE",
            order_id
        )

        # Insert the item
        await db.execute(
            "INSERT INTO order_items (order_id, price, qty) VALUES ($1, $2, $3)",
            order_id, item["price"], item["qty"]
        )

        # Recalculate from the ACTUAL current items (inside the lock)
        result = await db.fetch_one(
            "SELECT SUM(price * qty) AS total FROM order_items WHERE order_id = $1",
            order_id
        )

        # Update total — guaranteed consistent because we hold the lock
        await db.execute(
            "UPDATE orders SET total = $1, updated_at = NOW() WHERE id = $2",
            result["total"], order_id
        )
```

**Fix existing data**:
```sql
-- One-time repair of all inconsistent orders
UPDATE orders o
SET total = (
    SELECT COALESCE(SUM(oi.price * oi.quantity), 0)
    FROM order_items oi
    WHERE oi.order_id = o.id
)
WHERE o.total != (
    SELECT COALESCE(SUM(oi.price * oi.quantity), 0)
    FROM order_items oi
    WHERE oi.order_id = o.id
);
```

**Counterfactual**: If the original code had used `SELECT ... FOR UPDATE` or calculated the total from `SUM()` in a single transaction, this inconsistency would never have occurred. If we had a nightly consistency check job, we'd have caught this in week 1, not month 3.

**Prevention**: Add a nightly consistency check that alerts when `orders.total != SUM(order_items)`. Consider removing the stored total entirely — calculate it on read from line items (single source of truth).'''
    ),
    (
        "thinking/causal-intermittent-test-failure",
        "Our CI/CD pipeline has a test that fails about 10% of the time. It's a test for our notification service that checks if an email was sent after creating an order. When it fails, the assertion `assert len(sent_emails) == 1` gets `0`. The test passes locally every time.",
        r'''<think>
Intermittent test failure — 10% failure rate. Passes locally, fails in CI. The assertion says 0 emails sent when expecting 1.

Let me enumerate possible causes of non-determinism:

1. Timing issue
   - The test creates an order and immediately checks for emails
   - Email sending might be async (background task, message queue)
   - Locally: fast enough that email is sent before assertion
   - CI: slower environment, email not sent yet when assertion runs
   - This is the MOST common cause of flaky tests

2. Test ordering / shared state
   - Another test sends emails and doesn't clean up
   - Or another test consumes the email from a shared inbox
   - Tests run in different order in CI
   - Test isolation failure

3. Resource contention in CI
   - CI runs tests in parallel
   - Multiple tests share the same email mock/inbox
   - One test reads another test's email, or the count includes other tests' emails

4. Environment difference
   - Local: uses synchronous email sending
   - CI: uses async email sending (different config)
   - Or CI has different timeouts

5. Race condition in the notification service itself
   - The order creation triggers an event
   - Event handler sends the email
   - If event processing is async, the email might not be sent by assertion time

Let me think about which is most likely...

"Passes locally every time" + "fails 10% in CI" strongly suggests timing. Local machine is fast, CI runner is shared/slower. The 10% failure rate matches a race condition window — most of the time the async operation completes in time, but sometimes it doesn't.

The fix: either make the test wait for the email (with a timeout and polling), or make the email sending synchronous in tests.
</think>

**Root cause: timing race condition.** The email is sent asynchronously, and your test doesn't wait for it.

**Causal chain**:
```
1. Test creates order (synchronous)
2. Order creation emits event (async — goes to queue/background task)
3. Event handler sends email (async — runs in background)
4. Test asserts len(sent_emails) == 1 (IMMEDIATELY — before step 3 completes)

Locally:  Fast machine → step 3 completes before step 4 → PASS (99.9%)
CI:       Shared runner → step 4 runs before step 3 completes → FAIL (10%)
```

**Evidence this is the cause**:
```
✅ Passes locally, fails in CI → environment speed difference
✅ 10% failure rate → race condition window (not random, not deterministic)
✅ Gets 0 emails (not wrong email) → email not sent YET, not wrong email
✅ Notification service is event-driven → inherently async
```

**Fix 1: Wait for the async operation (preferred)**:
```python
import asyncio
from unittest.mock import patch

async def test_order_sends_email():
    # Create order (triggers async email)
    order = await create_order({"item": "widget", "email": "test@test.com"})

    # WRONG: assert immediately
    # assert len(sent_emails) == 1  # ← Race condition!

    # RIGHT: poll with timeout
    async def wait_for_email(timeout: float = 5.0, interval: float = 0.1):
        elapsed = 0
        while elapsed < timeout:
            if len(sent_emails) >= 1:
                return
            await asyncio.sleep(interval)
            elapsed += interval
        raise TimeoutError(f"Expected email not sent within {timeout}s")

    await wait_for_email()
    assert len(sent_emails) == 1
    assert sent_emails[0]["to"] == "test@test.com"
```

**Fix 2: Make email sending synchronous in tests (simpler)**:
```python
@pytest.fixture
def sync_email(monkeypatch):
    """Force synchronous email sending in tests."""
    sent = []

    async def mock_send_email(to, subject, body):
        sent.append({"to": to, "subject": subject, "body": body})

    monkeypatch.setattr("app.notifications.send_email", mock_send_email)

    # Process events synchronously instead of queuing
    monkeypatch.setattr("app.events.process_async", False)

    return sent

async def test_order_sends_email(sync_email):
    order = await create_order({"item": "widget", "email": "test@test.com"})
    # Now safe to assert immediately — everything ran synchronously
    assert len(sync_email) == 1
```

**Fix 3: Use event signaling (best for complex async flows)**:
```python
async def test_order_sends_email():
    email_sent = asyncio.Event()

    original_send = app.notifications.send_email
    async def tracked_send(*args, **kwargs):
        await original_send(*args, **kwargs)
        email_sent.set()  # Signal that email was sent

    with patch("app.notifications.send_email", tracked_send):
        await create_order({"item": "widget", "email": "test@test.com"})
        await asyncio.wait_for(email_sent.wait(), timeout=5.0)  # Wait for signal
        # Now safe to assert
```

**Counterfactual**: If the notification service used synchronous email sending (or if the test framework processed all pending async tasks before assertions), this test would never be flaky. The root cause is testing async code with synchronous assertions — a category of bug that appears in nearly every codebase with async event processing.

**Prevention**: Add a lint rule or code review checklist item: "Tests for async operations must either await completion or use polling with timeout. Never assert immediately after triggering an async operation."'''
    ),
    (
        "thinking/causal-memory-growth",
        "Our Python web service's memory grows from 500MB to 4GB over 24 hours, then gets OOM-killed. After restart, it starts at 500MB again. No memory leak detector finds anything obvious. RSS grows linearly. What's happening?",
        r'''<think>
Memory grows linearly from 500MB to 4GB over 24 hours = ~145KB/minute growth. It's not a sudden spike — it's steady accumulation.

"No memory leak detector finds anything obvious" — this is interesting. Standard leak detectors (objgraph, tracemalloc) look for uncollected objects. If they find nothing, the leak might be:

1. Not a Python object leak (C extension memory, mmap, file descriptors)
2. A correctly referenced cache that grows unboundedly
3. Python memory fragmentation (memory allocated but not returned to OS)
4. Goroutine/thread leak (each thread has its own stack)

Let me think through each:

Hypothesis 1: Unbounded cache/dict
- A dict that caches results but never evicts
- Example: session store, request cache, DNS cache
- Leak detectors see these as "normal" objects — they're referenced, not leaked
- 145KB/min ≈ 8.4MB/hour ≈ if each request adds 1KB to a cache and you handle 145 req/min

Hypothesis 2: Python memory fragmentation
- Python allocates memory from the OS in large blocks (arenas)
- When objects are freed, the memory goes back to Python's free list, NOT to the OS
- RSS never decreases even after objects are garbage collected
- This is a known Python behavior, especially with many small allocations

Hypothesis 3: C extension memory leak
- numpy, pandas, lxml, PIL — C extensions manage their own memory
- Python's tracemalloc can't see C-level allocations
- A leaked numpy array won't show up in Python memory profiling

Hypothesis 4: Thread/connection leak
- Each new thread: ~8MB stack
- If threads are created but never joined/cleaned up
- But 145KB/min = 1 thread every 55 minutes — unlikely to be threads

Hypothesis 5: Log buffer / string accumulation
- Logging handlers that buffer messages
- In-memory log buffer that grows without flushing
- Or string formatting that creates many small strings

Most likely: Hypothesis 1 (unbounded cache) because:
- Linear growth = one item added per N requests
- Leak detectors don't flag it because the cache is correctly referenced
- Restart fixes it because the cache is re-initialized empty
- It's the most common cause of "memory growth that isn't a leak"

Investigation approach: use tracemalloc to take snapshots 1 hour apart and compare what's growing.
</think>

**Linear memory growth that "isn't a leak" = almost certainly an unbounded cache or accumulation.**

Standard leak detectors miss it because the objects are **correctly referenced** — they're not "leaked" in the GC sense, they're just never removed.

**Investigation — find what's growing**:
```python
# Add this to your app startup — take snapshots over time
import tracemalloc
import threading
import time

tracemalloc.start(25)  # Track 25 frames deep

def memory_snapshot_thread():
    snapshots = []
    while True:
        time.sleep(3600)  # Snapshot every hour
        snap = tracemalloc.take_snapshot()
        snapshots.append(snap)
        if len(snapshots) >= 2:
            # Compare last two snapshots — what GREW?
            stats = snapshots[-1].compare_to(snapshots[-2], 'lineno')
            print("\n=== MEMORY GROWTH (last hour) ===")
            for stat in stats[:10]:
                print(stat)
            # This tells you EXACTLY which line of code is allocating
            # the memory that's accumulating

threading.Thread(target=memory_snapshot_thread, daemon=True).start()
```

**Common culprits and fixes**:

```python
# CULPRIT 1: Unbounded dict/cache (most common)
class UserService:
    def __init__(self):
        self._cache = {}  # Grows forever!

    async def get_user(self, user_id):
        if user_id not in self._cache:
            self._cache[user_id] = await db.fetch_user(user_id)
        return self._cache[user_id]
        # After 24 hours: 500K users cached = 4GB

# FIX: Use LRU cache with max size
from functools import lru_cache
from cachetools import TTLCache

class UserService:
    def __init__(self):
        self._cache = TTLCache(maxsize=10000, ttl=300)  # Max 10K entries, 5 min TTL


# CULPRIT 2: Growing list of processed items
processed_ids = set()  # Grows forever!

async def handle_event(event):
    if event.id in processed_ids:
        return  # Dedup
    processed_ids.add(event.id)  # Never removed!
    await process(event)

# FIX: Use time-bounded dedup (Redis with TTL, or rotating set)
from collections import OrderedDict

class BoundedDedup:
    def __init__(self, max_size=100000):
        self._seen = OrderedDict()
        self._max = max_size

    def is_new(self, item_id) -> bool:
        if item_id in self._seen:
            return False
        self._seen[item_id] = True
        if len(self._seen) > self._max:
            self._seen.popitem(last=False)  # Remove oldest
        return True


# CULPRIT 3: Logging handlers with growing buffers
import logging

handler = logging.handlers.MemoryHandler(capacity=1000000)  # 1M log records in memory!
# FIX: Use bounded capacity and flush target
handler = logging.handlers.MemoryHandler(
    capacity=1000,
    flushTarget=logging.FileHandler("/var/log/app.log")
)


# CULPRIT 4: Python memory fragmentation
# Even after del and gc.collect(), RSS doesn't shrink because
# Python's arena allocator doesn't return memory to the OS
# FIX: Use pymalloc debug mode to detect, or:
import gc
gc.collect()
# On Linux, force return to OS:
import ctypes
ctypes.CDLL("libc.so.6").malloc_trim(0)
```

**Diagnostic checklist**:
```bash
# Check Python object counts over time
python -c "import objgraph; objgraph.show_growth(limit=20)"

# Check for file descriptor leaks
ls -la /proc/$(pidof python)/fd | wc -l  # Should be stable

# Check for thread leaks
python -c "import threading; print(threading.active_count())"  # Should be stable

# Compare RSS vs Python heap
# If RSS >> Python heap → C extension leak
# If RSS ≈ Python heap → Python object accumulation
```

**Counterfactual**: If every cache had a `maxsize` and `ttl` from the start, this never would have happened. The fix is simple — the hard part is finding WHICH cache is growing. `tracemalloc.compare_to()` is your best friend for this.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
