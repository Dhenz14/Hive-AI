"""Phase 2E: Advanced Reasoning — Causal & Counterfactual Analysis (Part 3/5)
Systematic hypothesis elimination with evidence, root cause analysis:
connection pool exhaustion, data loss during deploy, flaky CI pipeline,
memory leak in long-running service, silent data corruption."""

PAIRS = [
    (
        "thinking/causal-connpool-exhaustion",
        "Our application suddenly started throwing 'connection pool exhausted' errors after a routine deploy. We didn't change any database code. What's happening?",
        r'''<think>
Let me systematically work through hypotheses for connection pool exhaustion after a deploy.

Symptom: Connection pool exhausted errors appeared after deploy.
Constraint: No database code was changed.

Hypothesis 1: The deploy itself is the cause (new code holds connections longer)
- "We didn't change database code" — but did we change code that USES the database?
- A new feature might make more DB calls per request
- Or a code path now makes N+1 queries instead of a batch query
- Test: compare request-to-query ratio before/after deploy
- Likelihood: MEDIUM — "didn't change DB code" could be incorrect or incomplete

Hypothesis 2: Connection leak (connections borrowed but not returned)
- New code opens a connection but exception path doesn't close it
- Even without changing "DB code," a try/except change could skip the conn.close()
- Test: monitor pool.checkedout() over time — if it only grows, it's a leak
- Likelihood: HIGH — most common cause of pool exhaustion

Hypothesis 3: Increased traffic (coincidental timing)
- Deploy happened to coincide with a traffic spike
- More concurrent requests = more connections needed
- Test: check request volume before/after deploy, compare to pool size
- Likelihood: LOW — too coincidental, but should verify

Hypothesis 4: Slow queries holding connections longer
- A new code path triggers a slow query (table scan, lock wait)
- Each connection is held for 5s instead of 50ms
- Same pool size, but connections are tied up 100x longer
- Little's Law: pool_needed = request_rate * connection_hold_time
- If hold_time increased 10x, you need 10x the pool
- Test: check pg_stat_activity for long-running queries
- Likelihood: HIGH

Hypothesis 5: Background job change
- Deploy included a new background task that uses DB connections
- Cron job or Celery task now runs during peak hours
- These connections come from the same pool
- Test: check if background workers share the pool with web workers
- Likelihood: MEDIUM

Hypothesis 6: Database migration from the deploy
- Migrations run during deploy, take locks on tables
- Subsequent queries wait for locks, holding connections
- Cascading: lock wait → slow queries → pool exhaustion
- Test: check pg_locks during deploy window
- Likelihood: HIGH — very common with ALTER TABLE on busy tables

Let me also think counterfactually:
- "What if we hadn't deployed?" → Would pool exhaustion still have happened?
  - If yes: external cause (traffic, DB issue)
  - If no: the deploy caused it

Most likely root cause: Hypothesis 6 (migration locks) or Hypothesis 4 (slow queries from new code path) causing connections to be held longer than expected.

Investigation order:
1. Check pg_stat_activity for active queries during the error window
2. Check if a migration ran and what it modified
3. Check pool metrics (checkedout, overflow) over time
4. Diff the deploy for any new DB-touching code paths
</think>

This is a classic post-deploy mystery. Let me walk through the likely causes systematically.

**Immediate diagnosis — check these in order:**

```sql
-- 1. What's holding all the connections right now?
SELECT pid, state, wait_event_type, wait_event,
       now() - query_start AS duration,
       left(query, 100) AS query
FROM pg_stat_activity
WHERE datname = 'mydb'
ORDER BY duration DESC;

-- Look for:
-- state = 'active' with long duration → slow queries
-- state = 'idle in transaction' → connection leak (started TX, never committed)
-- wait_event = 'Lock' → waiting for migration lock
```

```sql
-- 2. Check for lock contention (if migration ran)
SELECT blocked.pid AS blocked_pid,
       blocked.query AS blocked_query,
       blocking.pid AS blocking_pid,
       blocking.query AS blocking_query
FROM pg_stat_activity blocked
JOIN pg_locks bl ON bl.pid = blocked.pid
JOIN pg_locks kl ON kl.locktype = bl.locktype
    AND kl.database IS NOT DISTINCT FROM bl.database
    AND kl.relation IS NOT DISTINCT FROM bl.relation
JOIN pg_stat_activity blocking ON kl.pid = blocking.pid
WHERE NOT bl.granted AND kl.granted;
```

**Most likely cause: Migration locking**

```python
# If your deploy ran this migration:
class Migration:
    def forwards(self):
        # This takes an ACCESS EXCLUSIVE lock on the entire table
        db.execute("ALTER TABLE orders ADD COLUMN tracking_id VARCHAR(100)")

# While this lock is held (could be minutes on a big table):
# - ALL queries on 'orders' table queue up
# - Each queued query holds a connection from the pool
# - Pool fills up → "pool exhausted" for ALL queries, not just orders

# Fix: Use non-blocking migrations
class Migration:
    def forwards(self):
        db.execute("""
            ALTER TABLE orders
            ADD COLUMN tracking_id VARCHAR(100)
            -- Don't set NOT NULL or DEFAULT in same operation
        """)
        # For PostgreSQL: ADD COLUMN without DEFAULT is near-instant
        # The lock is held for milliseconds, not minutes
```

**Second most likely: Connection leak from new code path**

```python
# Spot the bug — new error handling code skips connection return:
def process_order(order_id):
    conn = pool.get_connection()
    try:
        order = conn.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
        if not order:
            return None  # BUG: connection never returned to pool!
        result = process(order)
        conn.close()  # Only reached on success path
        return result
    except Exception:
        conn.close()
        raise

# Fix: always use context manager
def process_order(order_id):
    with pool.get_connection() as conn:
        order = conn.execute("SELECT * FROM orders WHERE id = %s", (order_id,))
        if not order:
            return None  # Connection returned automatically
        return process(order)
```

**Third: Slow queries from new code (N+1 or missing index)**

```python
# New code looks innocent but triggers N+1:
def get_order_details(order_id):
    order = Order.query.get(order_id)
    # New feature: show item images
    for item in order.items:         # Lazy load: 1 query per item
        item.product.images          # Another lazy load per product!
    # 1 + N + N queries instead of 1 join

# Each query holds a connection. At 50 items per order:
# 101 sequential queries × 5ms each = 505ms connection hold time
# Before: 1 query × 5ms = 5ms hold time
# 100x increase → pool exhaustion

# Fix: eager load
order = (
    Order.query
    .options(joinedload(Order.items).joinedload(Item.product))
    .get(order_id)
)  # 1 query with JOINs
```

**Monitoring to add (prevent this from recurring):**

```python
# Alert on pool health metrics
import prometheus_client as prom

pool_checked_out = prom.Gauge('db_pool_checked_out', 'Connections in use')
pool_overflow = prom.Gauge('db_pool_overflow', 'Overflow connections')

# Alert rule: pool_checked_out > 0.8 * pool_size for > 1 minute
# This catches the problem BEFORE users see errors
```

Investigation order: check `pg_stat_activity` first (30 seconds to diagnose), then review migration files in the deploy, then check the code diff for new DB-touching paths.'''
    ),
    (
        "thinking/causal-dataloss-deploy",
        "We lost data during a deployment. Some users' recent actions (last ~5 minutes) disappeared. We use PostgreSQL with a Django app. What happened?",
        r'''<think>
Data loss during deployment. Let me systematically work through how this could happen.

Key fact: "last ~5 minutes" of data disappeared. This is a critical clue — it's a time-bounded loss, not random.

Hypothesis 1: Database was replaced/reset during deploy
- If deploy script drops and recreates the DB → total data loss (not matching "last 5 min")
- If deploy restores from a backup that was taken 5 min before deploy → matches!
- Test: check deploy scripts for any pg_restore, pg_dump, or DB reset commands
- Likelihood: MEDIUM

Hypothesis 2: Migration rolled back data
- A migration with RunSQL or data migration that deleted/modified rows
- Or: migration failed partway, auto-rollback undid recent transactions
- Test: check migration files for DELETE, TRUNCATE, or UPDATE statements
- Likelihood: MEDIUM

Hypothesis 3: Transaction rollback from long-running transaction
- Deploy process held an open transaction for the migration
- This transaction started 5 minutes before the data loss
- When deploy restarted the app, the transaction rolled back
- But... this wouldn't affect OTHER transactions' committed data
- Likelihood: LOW

Hypothesis 4: WAL replay issue
- If using streaming replication and the app was pointed to a replica
- If the replica was promoted without waiting for WAL to sync
- Data committed on primary but not yet replicated = lost
- Timeline: 5 minutes of async replication lag = plausible
- Test: check if the deploy switched database endpoints
- Likelihood: HIGH if using replication

Hypothesis 5: In-memory state not flushed
- App had a write-behind cache or batch insert buffer
- Deploy killed the app process without graceful shutdown
- Buffered writes (last 5 min) were never sent to DB
- Test: check if the app uses any write buffering/batching
- Likelihood: HIGH if app buffers writes

Hypothesis 6: Django's atomic transactions
- If views use @transaction.atomic and the deploy kills the process
- In-flight requests' transactions are rolled back by PostgreSQL
- But this only affects in-flight requests, not committed data
- Would lose data from requests that were mid-execution during kill
- Likelihood: LOW (would be seconds of data, not 5 minutes)

Hypothesis 7: Celery/background job queue
- Users' actions were queued as background jobs (not written to DB yet)
- Deploy restarted Celery workers → job queue lost
- If using Redis as broker without persistence, all pending jobs vanish
- 5 minutes of queued jobs = 5 minutes of "lost" data
- Test: check if user actions go through Celery, check Redis persistence config
- Likelihood: HIGH — very common

Hypothesis 8: Cache treated as source of truth
- Recent data was in Redis/memcache, not yet in PostgreSQL
- Deploy flushed the cache
- "Data" was only in cache, never persisted
- Test: check if any write paths store to cache first
- Likelihood: MEDIUM

Most likely: Hypothesis 5 or 7 (write buffering or job queue loss).

Counterfactual: "What if we had graceful shutdown?" → Buffers would flush, in-flight jobs would complete, no data loss.
</think>

5 minutes of data loss during deploy points to a specific set of causes. Let me narrow it down.

**Most likely causes (check in this order):**

**Cause 1: Background job queue was lost (most common)**

```python
# If user actions are processed via Celery:
@app.post("/api/submit-review")
def submit_review(review_data):
    # This LOOKS like it saved the data...
    process_review.delay(review_data)  # But it just queued a job!
    return {"status": "submitted"}

# The actual DB write happens in the worker:
@celery_app.task
def process_review(data):
    Review.objects.create(**data)  # THIS is the real save
```

```bash
# During deploy:
systemctl restart celery-worker  # Kills workers
# Pending jobs in Redis broker → gone (if Redis has no persistence)

# Check: How many jobs were pending?
redis-cli LLEN celery  # If this was > 0 during deploy → data loss
```

**Fix:**

```python
# Option A: Write to DB first, queue processing separately
@app.post("/api/submit-review")
def submit_review(review_data):
    review = Review.objects.create(**review_data, status="pending")  # DB first!
    process_review.delay(review.id)  # Queue enrichment, not creation
    return {"status": "submitted"}

# Option B: Use persistent broker
# celery_app.py
app.conf.broker_url = "redis://localhost:6379/0"
app.conf.broker_transport_options = {
    'visibility_timeout': 3600,
}
# AND configure Redis persistence:
# redis.conf: appendonly yes  (AOF persistence)

# Option C: Graceful worker shutdown
# deploy.sh:
celery -A myapp control shutdown  # Wait for in-flight tasks to finish
# NOT: kill -9 (loses in-progress work)
```

**Cause 2: Write-behind buffer not flushed**

```python
# Some apps batch DB writes for performance:
class WriteBuffer:
    def __init__(self):
        self.buffer = []

    def add(self, obj):
        self.buffer.append(obj)
        if len(self.buffer) >= 100:  # Flush every 100 items
            self.flush()

    def flush(self):
        Model.objects.bulk_create(self.buffer)
        self.buffer.clear()

# If deploy kills the process before flush → buffer lost
# Fix: flush on SIGTERM
import signal

def graceful_shutdown(signum, frame):
    write_buffer.flush()
    sys.exit(0)

signal.signal(signal.SIGTERM, graceful_shutdown)
```

**Cause 3: Database endpoint switched during deploy**

```python
# If you use read replicas and the deploy changed DATABASE_URL:
# Before deploy: DATABASE_URL = primary (writes go here)
# During deploy: DATABASE_URL = replica (writes go to replica??)
#   - Replica might reject writes, or
#   - Primary and replica diverged during switchover

# Check the deploy diff:
git diff HEAD~1 -- .env settings.py | grep DATABASE
```

**Cause 4: Unsafe migration**

```python
# Check recent migrations for data-destructive operations:
git log --oneline --name-only HEAD~1..HEAD -- */migrations/

# Look for:
# - RunSQL with DELETE or TRUNCATE
# - RemoveField on a field with data
# - Any custom data migration that modifies rows
```

**Preventing this in the future:**

```bash
# deploy.sh — safe deployment with graceful shutdown

# 1. Stop accepting new requests (drain connections)
# Tell load balancer to stop sending traffic
curl -X POST http://loadbalancer/drain/$SERVER_ID

# 2. Wait for in-flight requests to complete (30s max)
sleep 30

# 3. Gracefully stop workers (let them finish current tasks)
celery -A myapp control shutdown --timeout=60

# 4. Flush any buffers
python manage.py flush_buffers  # Custom management command

# 5. Run migrations
python manage.py migrate --noinput

# 6. Start new version
systemctl restart myapp

# 7. Health check
curl -sf http://localhost:8000/health || {
    echo "DEPLOY FAILED — rolling back"
    # rollback steps...
    exit 1
}

# 8. Resume traffic
curl -X POST http://loadbalancer/resume/$SERVER_ID
```

The root cause is almost certainly queued work that was discarded during restart. Rule of thumb: **never store user data exclusively in a queue or cache**. Write to the database first, then queue secondary processing.'''
    ),
    (
        "thinking/causal-flaky-ci",
        "Our CI pipeline fails about 20% of the time. The same tests pass when re-run. It's been getting worse over the past month. How do I debug this?",
        r'''<think>
Flaky CI that's getting progressively worse. Let me build hypotheses and narrow down.

Key clues:
1. Fails ~20% of the time (not random — 1 in 5 is suspiciously regular)
2. Passes on re-run (non-deterministic failure)
3. Getting worse over the past month (progressive degradation)

Hypothesis 1: Timing-dependent tests (race conditions)
- Tests depend on specific timing (sleep, setTimeout, async operations)
- Under CI load, timing varies more than on dev machines
- Getting worse because: more tests added, CI runners more loaded, or async code increased
- Test: check if the failing tests involve async operations, setTimeout, or polling
- Likelihood: HIGH

Hypothesis 2: Shared state between tests (test pollution)
- Test A modifies a global variable, database, or file
- Test B depends on a clean state
- When run in different order (CI randomizes or parallelizes), B fails
- Getting worse because: more tests = more pollution opportunities
- Test: run failing tests in isolation — do they pass?
- Likelihood: HIGH

Hypothesis 3: External service dependency
- Tests call a real external API (payment service, email API)
- External service has rate limits or occasional downtime
- Getting worse because: more tests hitting the API, or API becoming less reliable
- Test: check if failures correlate with network calls
- Likelihood: MEDIUM

Hypothesis 4: Resource exhaustion on CI runner
- CI runner runs out of memory, disk, or ports
- More tests = more resources needed
- At some threshold, tests start failing with OOM or "address already in use"
- Getting worse because: test suite is growing
- Test: check CI runner resource metrics during failing runs
- Likelihood: MEDIUM

Hypothesis 5: Database/Docker container startup timing
- CI starts a Postgres container, tests run before it's fully ready
- Health check is insufficient (port open but not accepting connections)
- Getting worse because: database is larger (more data to initialize) or CI runners are slower
- Test: add verbose logging to DB connection setup
- Likelihood: MEDIUM

Hypothesis 6: Time/date dependent tests
- Tests that check "created today" or "expires in 24 hours"
- Fail near midnight or at month boundaries
- But "getting worse over a month" doesn't fit well (would be periodic, not progressive)
- Likelihood: LOW

The "getting worse" clue strongly suggests Hypothesis 1 or 2 (more tests = more opportunities for pollution/races) or Hypothesis 4 (resource pressure increasing).

Investigation plan:
1. Collect data: which specific tests fail? Is it always the same ones or different?
2. If same tests: those tests have a timing or state bug
3. If different tests: the problem is environmental (resources, shared state, ordering)
4. Check CI runner metrics during failures
5. Run the full suite in isolation with --forked or similar
</think>

Flaky CI that's progressively worsening over a month has a pattern — it's not random. Let me help you diagnose it systematically.

**Step 1 — Collect the data (which tests are flaky?):**

```bash
# Run your suite 10 times, record failures
for i in $(seq 1 10); do
    pytest --tb=line --junitxml=results_$i.xml 2>&1 | tail -20 >> flaky_log.txt
done

# Extract just the failing test names
grep "FAILED" flaky_log.txt | sort | uniq -c | sort -rn
# Output like:
#   8 tests/test_api.py::test_concurrent_checkout
#   6 tests/test_ws.py::test_websocket_reconnect
#   3 tests/test_cache.py::test_expiry
```

```python
# Or use pytest-repeat for targeted flakiness detection
# pip install pytest-repeat
pytest tests/test_api.py::test_concurrent_checkout --count=20
# If it fails 4/20 times → confirmed flaky
```

**Step 2 — Diagnose based on pattern:**

**Pattern A: Same tests always fail (timing/race conditions):**

```python
# FLAKY — depends on timing
async def test_websocket_reconnect():
    ws = await connect_ws()
    await ws.close()
    await asyncio.sleep(0.5)  # "Should be enough time to reconnect"
    assert ws.connected  # Fails when CI is slow!

# FIXED — wait for the actual condition, not a time duration
async def test_websocket_reconnect():
    ws = await connect_ws()
    await ws.close()
    # Wait for reconnection with timeout
    for _ in range(50):  # 50 * 100ms = 5s max
        await asyncio.sleep(0.1)
        if ws.connected:
            break
    assert ws.connected, "Reconnect timed out after 5s"
```

```python
# FLAKY — order-dependent assertion on unordered data
def test_get_users():
    response = client.get("/users")
    assert response.json() == [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]
    # Fails when DB returns Bob first!

# FIXED — sort or use set comparison
def test_get_users():
    response = client.get("/users")
    users = sorted(response.json(), key=lambda u: u["id"])
    assert users == [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ]
```

**Pattern B: Different tests fail each run (test pollution):**

```python
# Test A pollutes global state:
def test_enable_feature():
    settings.FEATURE_FLAG = True
    assert feature_enabled()
    # Forgot to reset settings!

# Test B assumes default state:
def test_default_behavior():
    assert not feature_enabled()  # FAILS if test_enable_feature ran first

# FIXED — use fixtures that reset state
@pytest.fixture(autouse=True)
def reset_settings():
    original = dict(vars(settings))
    yield
    for key, value in original.items():
        setattr(settings, key, value)
```

```python
# Database pollution — test creates data that leaks to other tests
def test_create_user():
    User.objects.create(email="test@test.com")  # Left in DB!

def test_unique_email():
    User.objects.create(email="test@test.com")  # IntegrityError!

# FIXED — use transaction rollback per test
@pytest.fixture(autouse=True)
def db_transaction(db):
    """Each test runs in a transaction that gets rolled back."""
    # Django's TestCase does this automatically
    # For pytest-django: use @pytest.mark.django_db(transaction=True)
```

**Pattern C: Resource exhaustion (the "getting worse" clue):**

```bash
# Check CI runner during test execution:
# Memory
free -m  # Or: watch -n 1 free -m

# Disk
df -h

# Open file descriptors / connections
lsof | wc -l

# Port exhaustion (common with many HTTP tests)
ss -s  # Check TIME_WAIT count
```

```python
# Tests that don't close connections:
def test_api_call():
    response = requests.get("http://localhost:8000/api/data")
    assert response.status_code == 200
    # Connection not closed! Accumulates over 2000 tests

# FIXED — use a session that's cleaned up
@pytest.fixture
def http_client():
    with requests.Session() as session:
        yield session
    # Session closed, connections released

def test_api_call(http_client):
    response = http_client.get("http://localhost:8000/api/data")
    assert response.status_code == 200
```

**Step 3 — Systematic fix checklist:**

```yaml
# .github/workflows/ci.yml — add diagnostics
- name: Run tests with flaky detection
  run: |
    # Randomize test order to expose pollution
    pytest --randomly-seed=random -v \
           --timeout=30 \           # Kill stuck tests
           --tb=short \
           2>&1 | tee test_output.txt

- name: Upload failure artifacts
  if: failure()
  uses: actions/upload-artifact@v4
  with:
    name: test-failures
    path: test_output.txt
```

```ini
# pytest.ini — add timeout and strict markers
[pytest]
timeout = 30
timeout_method = signal
addopts = --strict-markers -x --tb=short
```

The "getting worse over a month" strongly suggests either accumulating test pollution (more tests = more interactions) or resource exhaustion (more tests = more memory/connections). Start by identifying which specific tests fail — that immediately tells you whether it's those tests' problem (timing) or the environment's problem (pollution/resources).'''
    ),
    (
        "thinking/causal-memoryleak-longrunning",
        "Our Python web service's memory usage grows steadily over days until it hits the container limit and gets OOM-killed. Restarting fixes it temporarily. How do I find the leak?",
        r'''<think>
Memory leak in a long-running Python service. Let me think through the diagnostic process systematically.

First, what IS a memory leak in Python?
- Python has garbage collection, so true leaks (unreachable memory never freed) are rare
- More common: "memory bloat" — objects that are reachable but shouldn't be kept
- Examples: growing caches, accumulating references, C extension leaks

Let me categorize the likely causes:

Category 1: Unbounded caches/dicts
- `cache = {}` that grows forever (no eviction, no TTL)
- Memoization decorators on functions with unique inputs
- Session stores, request logs, metrics stored in-memory
- This is the #1 cause of Python "memory leaks"

Category 2: Circular references that GC can't collect
- Objects with __del__ methods that form cycles (Python 2 issue, mostly fixed in 3)
- C extension objects that don't participate in GC
- Likelihood: LOW in modern Python

Category 3: Global/module-level accumulation
- Lists or sets that get appended to but never cleared
- Event listener registrations that accumulate
- Logger handlers added per-request

Category 4: C extension memory leaks
- Libraries like lxml, Pillow, or database drivers with C components
- Memory allocated by C code isn't tracked by Python's GC
- Can only be found with OS-level memory tools (valgrind, memray)

Category 5: Large object caching by framework
- SQLAlchemy identity map (session keeps all queried objects)
- Django ORM querysets cached in debug mode
- Response objects kept in middleware

Diagnostic approach:
1. First: is it Python objects or C-level memory?
   - Compare sys.getsizeof-based tracking vs OS RSS
   - If Python objects grow → categories 1, 3, 5
   - If RSS grows but Python objects don't → category 4

2. Find the growing objects:
   - Take heap snapshots at intervals
   - Diff them to find what's accumulating
   - tracemalloc (stdlib) or objgraph (3rd party)

3. Trace back to the source:
   - What code is creating these objects?
   - Why aren't they being freed?
   - What's holding references to them?
</think>

Memory that grows steadily over days is almost always an unbounded cache or accumulating references — not a "true" leak. Here's how to find it.

**Step 1 — Quick diagnosis (which kind of leak?):**

```python
# Add this endpoint to your running service
import os
import gc
import sys

@app.get("/debug/memory")
def memory_stats():
    import resource
    gc.collect()  # Force GC first

    return {
        # OS-level memory (what container sees)
        "rss_mb": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,

        # Python object counts by type
        "top_types": _count_objects_by_type(),

        # GC stats
        "gc_counts": gc.get_count(),
        "gc_objects": len(gc.get_objects()),
    }

def _count_objects_by_type():
    counts = {}
    for obj in gc.get_objects():
        t = type(obj).__name__
        counts[t] = counts.get(t, 0) + 1
    # Return top 20 most numerous types
    return dict(sorted(counts.items(), key=lambda x: -x[1])[:20])
```

```bash
# Hit this endpoint every hour, diff the results
# Watch for types whose count grows consistently:
# Hour 1: {"dict": 50000, "list": 30000, "str": 80000}
# Hour 2: {"dict": 55000, "list": 30000, "str": 90000}
# Hour 8: {"dict": 90000, "list": 30000, "str": 200000}
# → dicts and strs are accumulating
```

**Step 2 — Find exactly what's growing (tracemalloc):**

```python
# Enable at startup
import tracemalloc
tracemalloc.start(25)  # 25 frames of traceback

# Snapshot endpoint
_previous_snapshot = None

@app.get("/debug/memory/snapshot")
def memory_snapshot():
    global _previous_snapshot
    snapshot = tracemalloc.take_snapshot()

    if _previous_snapshot:
        # Diff: what GREW since last snapshot?
        stats = snapshot.compare_to(_previous_snapshot, 'lineno')
        top_growth = []
        for stat in stats[:20]:
            top_growth.append({
                "file": str(stat.traceback),
                "size_diff_kb": stat.size_diff / 1024,
                "count_diff": stat.count_diff,
            })
        _previous_snapshot = snapshot
        return {"top_growth": top_growth}

    _previous_snapshot = snapshot
    return {"status": "baseline captured, call again to see diff"}
```

```
# Example output after a few hours:
{
  "top_growth": [
    {"file": "myapp/cache.py:42", "size_diff_kb": 15000, "count_diff": 50000},
    {"file": "myapp/middleware.py:18", "size_diff_kb": 3000, "count_diff": 10000}
  ]
}
# → cache.py line 42 is the leak! 15MB growth.
```

**Step 3 — Common culprits and fixes:**

```python
# CULPRIT 1: Unbounded dict/cache (90% of Python "leaks")
# ❌ Grows forever
_cache = {}

def get_user_data(user_id):
    if user_id not in _cache:
        _cache[user_id] = db.get_user(user_id)
    return _cache[user_id]
# After 1M unique users → 1M entries → gigabytes of RAM

# ✅ Fixed: Use LRU cache with size limit
from functools import lru_cache

@lru_cache(maxsize=10000)  # Evicts oldest when full
def get_user_data(user_id):
    return db.get_user(user_id)

# Or with TTL (time-based expiry):
from cachetools import TTLCache
_cache = TTLCache(maxsize=10000, ttl=300)  # 5 min TTL, 10K max
```

```python
# CULPRIT 2: SQLAlchemy session not closed (identity map grows)
# ❌ Session accumulates all queried objects
@app.get("/users/{user_id}")
def get_user(user_id: int):
    session = Session()
    user = session.query(User).get(user_id)
    return user
    # Session never closed! Identity map keeps every queried User

# ✅ Fixed: Scoped session with proper cleanup
@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    return db.query(User).get(user_id)
    # get_db yields session and closes it after request
```

```python
# CULPRIT 3: Accumulating log handlers
# ❌ Adds a new handler every time this function is called
def setup_logging(request_id):
    logger = logging.getLogger("myapp")
    handler = logging.StreamHandler()
    handler.addFilter(lambda r: setattr(r, 'request_id', request_id))
    logger.addHandler(handler)  # NEVER removed!

# After 1M requests → 1M handlers on the logger → massive memory + CPU

# ✅ Fixed: Use contextvars instead
from contextvars import ContextVar
request_id_var = ContextVar('request_id', default='-')
```

```python
# CULPRIT 4: Event listeners not cleaned up
# ❌ Each WebSocket connection registers a listener, never unregisters
class WebSocketHandler:
    def on_connect(self, ws):
        event_bus.on("update", ws.send)  # Adds listener

    def on_disconnect(self, ws):
        pass  # Forgot to remove listener!
        # event_bus still holds reference to ws.send
        # ws object can never be garbage collected

# ✅ Fixed: Clean up on disconnect
    def on_disconnect(self, ws):
        event_bus.remove_listener("update", ws.send)
```

**Step 4 — Temporary mitigation while you fix the root cause:**

```yaml
# Kubernetes: restart before OOM
resources:
  limits:
    memory: "512Mi"  # Hard limit

# Or: use gunicorn's max-requests to periodically recycle workers
# gunicorn.conf.py
max_requests = 10000        # Restart worker after 10K requests
max_requests_jitter = 1000  # Add randomness to avoid all restarting at once
```

Start with tracemalloc snapshots — they'll point you to the exact line of code that's accumulating. In my experience, it's almost always an unbounded dict or a session/cache that's never cleaned up.'''
    ),
    (
        "thinking/causal-silent-corruption",
        "We discovered that about 2% of our financial records have incorrect amounts. The errors are small (off by a few cents) and accumulated over 6 months without anyone noticing. How do we find the source?",
        r'''<think>
Silent data corruption in financial records — small amounts, 2% error rate, accumulated over 6 months. This is a subtle bug. Let me think about what causes cents-level financial errors.

Key observations:
- "Off by a few cents" — not large errors, not random garbage
- 2% error rate — not ALL records, just some
- Accumulated over 6 months — been happening consistently
- Small enough to go unnoticed — systematic, not catastrophic

Hypothesis 1: Floating point arithmetic
- This is the #1 cause of cents-level financial errors
- 0.1 + 0.2 = 0.30000000000000004 in IEEE 754
- After rounding, this can gain or lose a penny
- 2% rate could mean: a specific code path uses float math
- Test: grep for float operations on money values
- Likelihood: VERY HIGH

Hypothesis 2: Rounding at the wrong step
- Calculate tax: $10.00 * 0.0825 = $0.825 → round to $0.83
- But if you calculate per-item then sum, vs sum then calculate, you get different results
- Rounding N items individually vs rounding the total can differ by up to N cents
- 2% rate: items where the per-item vs per-total rounding diverges
- Likelihood: HIGH

Hypothesis 3: Currency conversion errors
- If dealing with multiple currencies
- Exchange rates have many decimal places
- Intermediate calculations lose precision
- But the problem says "financial records" not "multi-currency" specifically
- Likelihood: MEDIUM (if multicurrency)

Hypothesis 4: Integer overflow or truncation
- If storing cents as integer but somewhere converting to float and back
- int → float → int can lose precision for large amounts
- But "off by a few cents" on all amounts suggests float math, not overflow
- Likelihood: LOW

Hypothesis 5: Concurrent modification
- Two processes update the same record simultaneously
- One overwrites the other's change
- But this would cause larger discrepancies, not consistently "a few cents"
- Likelihood: LOW

Hypothesis 6: Third-party integration mismatch
- Payment processor (Stripe) uses cents (integer)
- Your app uses dollars (float)
- Conversion between them introduces rounding errors
- Likelihood: HIGH

Most likely: Hypothesis 1 (float arithmetic) combined with Hypothesis 2 (rounding inconsistency), possibly triggered by Hypothesis 6 (integer/float conversion at integration boundary).

Investigation plan:
1. Analyze the corrupted records — is there a pattern?
   - Specific product? Specific calculation path? Specific time?
2. Grep for float operations on money
3. Check the payment integration for type conversions
4. Reproduce with known inputs
</think>

"Off by a few cents" in 2% of financial records over 6 months is almost certainly floating point arithmetic somewhere in your money calculations. Let me show you how to find and fix it.

**Step 1 — Analyze the corruption pattern:**

```sql
-- Find all records where our amount doesn't match what it should be
-- (assuming you have an audit log or can recalculate)
SELECT
    r.id,
    r.amount AS stored_amount,
    r.quantity * r.unit_price AS expected_amount,
    r.amount - (r.quantity * r.unit_price) AS discrepancy,
    ABS(r.amount - (r.quantity * r.unit_price)) AS abs_error,
    r.created_at
FROM financial_records r
WHERE ABS(r.amount - (r.quantity * r.unit_price)) > 0.001
  AND ABS(r.amount - (r.quantity * r.unit_price)) < 1.00
ORDER BY abs_error DESC;

-- Check if errors correlate with specific products/operations
SELECT
    operation_type,
    COUNT(*) AS error_count,
    AVG(ABS(discrepancy)) AS avg_error
FROM (/* above query */) errors
GROUP BY operation_type;

-- Are errors always in the same direction? (always positive = always rounding up)
SELECT
    CASE WHEN discrepancy > 0 THEN 'over' ELSE 'under' END AS direction,
    COUNT(*)
FROM (/* above query */) errors
GROUP BY direction;
```

**Step 2 — Find the float arithmetic (the cause in ~90% of cases):**

```bash
# Search for float operations on money-related variables
grep -rn "float\|/ 100\|* 0\.\|round(" --include="*.py" \
    app/billing/ app/payments/ app/orders/

# Look for patterns like:
# float(amount)
# amount / 100
# price * quantity (if price is float)
# round(x, 2) applied too late
```

```python
# THE BUG (example — will match your code somewhere):
def calculate_total(items):
    total = 0.0  # ← FLOAT! This is the root cause
    for item in items:
        subtotal = item.price * item.quantity  # float multiplication
        tax = subtotal * 0.0825               # float * float
        total += subtotal + tax               # accumulated float errors
    return round(total, 2)  # Rounding at the END — errors already accumulated

# Demonstration of the error:
>>> 0.1 + 0.2
0.30000000000000004

>>> sum(0.1 for _ in range(10))
0.9999999999999999  # NOT 1.0!

>>> 19.99 * 0.0825
1.649175  # Tax should be $1.65
>>> round(19.99 * 0.0825, 2)
1.65  # Looks OK...
>>> 33.33 * 3 * 0.0825
8.249175000000001  # But this rounds to 8.25, should it be 8.24?
# The error: 0.000000000000001 pushed it over the rounding boundary
```

**Step 3 — The fix (use Decimal for ALL money operations):**

```python
from decimal import Decimal, ROUND_HALF_UP

# BEFORE (float — lossy):
def calculate_total(items):
    total = 0.0
    for item in items:
        total += item.price * item.quantity * 1.0825
    return round(total, 2)

# AFTER (Decimal — exact):
def calculate_total(items):
    total = Decimal("0")
    tax_rate = Decimal("0.0825")
    for item in items:
        price = Decimal(str(item.price))   # Convert from float safely
        quantity = Decimal(str(item.quantity))
        subtotal = price * quantity
        tax = subtotal * tax_rate
        total += (subtotal + tax).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
    return total

# Key rules:
# 1. NEVER use float for money
# 2. Store as Decimal or integer cents in DB
# 3. Round at each line item, not just the total
# 4. Use Decimal(str(x)), never Decimal(x) for floats
```

**Step 4 — Fix at the database and integration layers:**

```python
# Django model — use DecimalField, NOT FloatField
class LineItem(models.Model):
    price = models.DecimalField(max_digits=10, decimal_places=2)  # NOT FloatField
    quantity = models.IntegerField()
    tax_rate = models.DecimalField(max_digits=5, decimal_places=4)
    total = models.DecimalField(max_digits=10, decimal_places=2)

# Stripe integration — they use integer cents
def charge_customer(amount_decimal: Decimal, currency: str = "usd"):
    # Convert Decimal dollars to integer cents for Stripe
    amount_cents = int(amount_decimal * 100)

    stripe.PaymentIntent.create(
        amount=amount_cents,  # Stripe wants cents as integer
        currency=currency,
    )

# NEVER do this:
# amount_cents = int(float(amount) * 100)  # Float * 100 can be 999 or 1001!
```

**Step 5 — Fix historical data:**

```sql
-- Recalculate all affected records using correct math
-- (Run this in a transaction, verify before committing)
BEGIN;

UPDATE financial_records
SET amount = ROUND(quantity * unit_price * (1 + tax_rate), 2)
WHERE ABS(amount - ROUND(quantity * unit_price * (1 + tax_rate), 2)) BETWEEN 0.001 AND 1.00;

-- Verify: how many rows affected?
-- ROLLBACK if the count seems wrong, COMMIT if correct
```

**Step 6 — Prevent recurrence:**

```python
# Add a linting rule to catch float usage on money
# custom_lint.py or ruff rule
BANNED_PATTERNS = [
    (r'FloatField.*price\|amount\|cost\|total', "Use DecimalField for money"),
    (r'float\(.*(price|amount|cost|total)', "Use Decimal for money"),
]

# Add a database constraint
ALTER TABLE financial_records
ADD CONSTRAINT amount_precision
CHECK (amount = ROUND(amount, 2));  # No sub-cent values
```

Summary: The root cause is IEEE 754 floating point arithmetic applied to money. Replace all `float` with `Decimal` in money code paths, round at each line item, and use integer cents for external integrations. Then do a one-time data correction for the 2% of affected records.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
