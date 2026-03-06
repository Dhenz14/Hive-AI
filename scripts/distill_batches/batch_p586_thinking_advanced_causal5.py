"""Phase 2E: Advanced Reasoning — Causal & Counterfactual Analysis (Part 5/8)"""

PAIRS = [
    (
        "thinking/causal-memory-leak-websocket",
        "Our WebSocket server's memory usage grows linearly over time. After about 12 hours it hits 4GB and OOM-kills. We're using Python asyncio with websockets library. Connection count stays stable at ~2000. What's causing the leak?",
        r'''<think>
WebSocket server with stable connections but growing memory. Let me reason through the causal chain.

Key observations:
- Memory grows linearly (not exponentially) → leak is proportional to TIME, not connections
- Connection count is stable at ~2000 → connections are being recycled properly
- 12 hours to 4GB → roughly 300MB/hour growth rate

If connections are stable but memory grows, something is accumulating PER-TIME-UNIT, not per-connection. What accumulates over time?

**Hypothesis 1: Message history accumulation**
Are messages being buffered or stored in memory? Many WebSocket implementations keep a send queue. If messages aren't being consumed fast enough, the queue grows. But this would correlate with slow consumers, not time.

**Hypothesis 2: Asyncio task accumulation**
Each connection likely spawns tasks. If tasks aren't being properly awaited or cancelled on disconnect, they accumulate. `asyncio.all_tasks()` would grow over time. This is a VERY common Python asyncio leak.

Let me think about this more carefully. Connection count is stable, meaning connections come and go. But if each disconnected connection leaves behind orphaned tasks or callbacks...

**Hypothesis 3: Event handler / callback accumulation**
If the server registers event handlers (on_message, on_close) and doesn't unregister them on disconnect, the handler list grows. Each handler holds a reference to the connection object, preventing garbage collection.

**Hypothesis 4: Logging or metrics accumulation**
Are log records being accumulated in memory? A logging handler that buffers (MemoryHandler, QueueHandler with no consumer) would cause linear growth.

**Hypothesis 5: Connection metadata not cleaned up**
A common pattern: `connections = {}` dict mapping connection_id → metadata. If entries aren't removed on disconnect, this dict grows forever.

Let me rank by likelihood:
1. Connection metadata dict not cleaned up (most common, matches linear growth)
2. Asyncio tasks not cancelled on disconnect (second most common)
3. Message queue accumulation for slow consumers

**Counterfactual analysis:**
- If we had no metadata dict → would memory still grow? Need to check.
- If we properly cancelled tasks on disconnect → would memory stabilize? Very likely if this is the cause.
- If connections truly cycled properly → the leak must be in something that SURVIVES connection lifecycle.

The key diagnostic: `len(asyncio.all_tasks())` — if this grows over time while connection count is stable, orphaned tasks are the leak.
</think>

With stable connections but linear memory growth, the leak is in something that **survives connection lifecycle** — likely orphaned asyncio tasks or unreleased references. Here's the diagnostic approach:

## Step 1: Identify What's Accumulating

```python
import asyncio
import gc
import tracemalloc

# Add a diagnostic endpoint to your server
async def debug_memory(websocket, path):
    if path == "/debug/memory":
        import objgraph
        stats = {
            "asyncio_tasks": len(asyncio.all_tasks()),
            "gc_objects": len(gc.get_objects()),
            "websocket_connections": len(connected_clients),
        }
        # Top growing types
        stats["top_types"] = objgraph.most_common_types(limit=10)
        await websocket.send(json.dumps(stats))
```

Run this every 10 minutes and watch what grows. The culprit is almost always one of these:

## Most Likely Cause: Orphaned Tasks on Disconnect

```python
# ❌ THE BUG: tasks created per-connection, never cancelled
connected_clients = {}

async def handler(websocket):
    client_id = id(websocket)
    connected_clients[client_id] = websocket

    # These tasks run forever — even after disconnect
    asyncio.create_task(send_heartbeat(websocket))    # LEAKED
    asyncio.create_task(process_user_events(websocket))  # LEAKED

    try:
        async for message in websocket:
            await handle_message(websocket, message)
    finally:
        del connected_clients[client_id]
        # Tasks are still running! websocket is closed but tasks
        # catch the exception and silently spin, or hold references


# ✅ THE FIX: track and cancel tasks per connection
async def handler(websocket):
    client_id = id(websocket)
    connected_clients[client_id] = websocket

    # Create tasks and track them
    tasks = [
        asyncio.create_task(send_heartbeat(websocket)),
        asyncio.create_task(process_user_events(websocket)),
    ]

    try:
        async for message in websocket:
            await handle_message(websocket, message)
    finally:
        # Cancel ALL tasks for this connection
        for task in tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        del connected_clients[client_id]
```

## Second Most Likely: Metadata Dict Leak

```python
# ❌ THE BUG: metadata added but never removed
user_sessions = {}
message_counts = {}

async def handler(websocket):
    user_id = await authenticate(websocket)
    user_sessions[user_id] = {"connected_at": time.time(), "ws": websocket}
    message_counts[user_id] = 0

    try:
        async for message in websocket:
            message_counts[user_id] += 1
            await handle_message(websocket, message)
    except websockets.ConnectionClosed:
        pass
    # BUG: user_sessions[user_id] and message_counts[user_id] never deleted
    # Each reconnecting user leaves the OLD entry (with ws reference)


# ✅ THE FIX: always clean up in finally
    finally:
        user_sessions.pop(user_id, None)
        message_counts.pop(user_id, None)
```

## Third Possibility: Message Queue Backpressure

```python
# ❌ THE BUG: unbounded queue for slow consumers
async def broadcast(message):
    for ws in connected_clients.values():
        # If ws is slow, this queues messages internally
        # websockets library buffers outgoing messages in memory
        await ws.send(message)  # Doesn't actually block until buffer is full


# ✅ THE FIX: use write limit and skip slow consumers
import websockets

async def broadcast(message):
    disconnected = []
    for client_id, ws in connected_clients.items():
        try:
            # Check if outgoing buffer is too large
            if ws.transport.get_write_buffer_size() > 1_000_000:  # 1MB
                logger.warning("Slow consumer %s, skipping", client_id)
                continue
            await asyncio.wait_for(ws.send(message), timeout=5.0)
        except (websockets.ConnectionClosed, asyncio.TimeoutError):
            disconnected.append(client_id)

    for client_id in disconnected:
        connected_clients.pop(client_id, None)
```

## Diagnostic Timeline

| Check | Command | If growing = cause |
|-------|---------|-------------------|
| Task count | `len(asyncio.all_tasks())` | Orphaned tasks |
| Dict sizes | `len(user_sessions)` vs connection count | Metadata leak |
| Object count | `objgraph.most_common_types()` | Which type is leaking |
| Memory snapshot | `tracemalloc.take_snapshot().statistics('lineno')` | Exact line allocating |

Start with `asyncio.all_tasks()` — in 90% of Python WebSocket memory leaks, orphaned tasks are the cause.'''
    ),
    (
        "thinking/causal-test-flakiness-systematic",
        "About 15% of our CI runs fail with at least one flaky test. We've tried re-running failures and marking tests as flaky, but the problem keeps getting worse. We have ~3000 tests in a Django test suite. How do we systematically fix this?",
        r'''<think>
15% failure rate across 3000 tests — this is a systemic problem, not individual test issues. Let me trace the causal chain.

**What makes tests flaky?** Let me categorize by root cause:

1. **Shared mutable state between tests**
   - Tests modify database state and cleanup is incomplete
   - Global variables, class-level caches, module-level state
   - Django's `TestCase` with `setUpClass` sharing state

2. **Time-dependent tests**
   - `datetime.now()` comparisons that fail at midnight
   - Tests that assume specific timing ("this should complete in < 100ms")
   - Timezone issues

3. **Ordering dependencies**
   - Test A creates data that test B accidentally relies on
   - Test C deletes data that test D needs
   - Run tests in random order → failures appear

4. **External dependencies**
   - Network calls to real services (even in tests)
   - File system operations in shared temp directories
   - Port conflicts when running parallel

5. **Race conditions in async/threaded code**
   - Signal handlers firing in unexpected order
   - Django's `post_save` signals causing side effects

**Why "re-running" makes it worse:**
Re-running masks the problem. Teams stop investigating root causes. The test suite becomes unreliable → developers stop trusting it → they ignore real failures → bugs ship.

**Why "marking as flaky" makes it worse:**
Marking tests as flaky is admitting defeat. It means "this test sometimes lies." If enough tests are flaky, the suite provides no signal.

**The systematic approach:**
1. CLASSIFY: What type of flakiness does each failing test have?
2. ISOLATE: Can you reproduce the flakiness deterministically?
3. FIX: Address the root cause, not the symptom
4. PREVENT: Add infrastructure that prevents new flaky tests

Let me think about the most impactful fixes...

With 3000 tests and 15% failure rate, probably 50-100 tests are flaky. But they likely share 5-6 root causes. Fix the root causes and you fix most of the flakiness.
</think>

15% flakiness in a 3000-test suite is a systemic problem with a few root causes — not hundreds of individual bugs. Here's the systematic approach:

## Step 1: Classify the Flakiness (1 day)

```python
# scripts/classify_flaky_tests.py
"""Run test suite 10 times, track which tests fail and when."""

import subprocess
import json
from collections import defaultdict

results = defaultdict(lambda: {"pass": 0, "fail": 0, "errors": []})

for run in range(10):
    proc = subprocess.run(
        ["python", "manage.py", "test", "--parallel", "4",
         "--verbosity", "0", "--shuffle"],  # Random order!
        capture_output=True, text=True
    )
    # Parse test results (use pytest-json-report for better output)
    for test_id, outcome, error in parse_results(proc.stdout, proc.stderr):
        results[test_id][outcome] += 1
        if outcome == "fail":
            results[test_id]["errors"].append(error)

# Classify
flaky = {
    test_id: data for test_id, data in results.items()
    if 0 < data["fail"] < 10  # Sometimes passes, sometimes fails
}

# Group by error pattern
for test_id, data in flaky.items():
    errors = data["errors"]
    if any("IntegrityError" in e for e in errors):
        data["category"] = "shared_state"
    elif any("AssertionError" in e and "time" in e.lower() for e in errors):
        data["category"] = "time_dependent"
    elif any("ConnectionError" in e for e in errors):
        data["category"] = "external_dependency"
    elif any("DoesNotExist" in e for e in errors):
        data["category"] = "ordering_dependency"
    else:
        data["category"] = "unknown"

print(json.dumps(flaky, indent=2))
```

## Step 2: Fix by Category (highest impact first)

### Category 1: Shared State (Usually 40% of flaky tests)

```python
# ❌ COMMON BUG: setUpClass shares state across tests
class UserTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create(email="test@example.com")  # SHARED

    def test_update_name(self):
        self.user.name = "Alice"
        self.user.save()  # Mutates shared state

    def test_check_default_name(self):
        self.assertEqual(self.user.name, "")  # FAILS if test_update runs first


# ✅ FIX: Use setUp (per-test) or TransactionTestCase with fixtures
class UserTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(email="test@example.com")  # Fresh per test

    def test_update_name(self):
        self.user.name = "Alice"
        self.user.save()

    def test_check_default_name(self):
        self.assertEqual(self.user.name, "")  # Always passes
```

### Category 2: Time-Dependent (Usually 25% of flaky tests)

```python
# ❌ COMMON BUG: using real time
def test_token_not_expired(self):
    token = create_token(expires_in=3600)
    self.assertFalse(token.is_expired)  # Usually passes... unless CI is slow


# ✅ FIX: freeze time
from freezegun import freeze_time

@freeze_time("2024-06-15 12:00:00")
def test_token_not_expired(self):
    token = create_token(expires_in=3600)
    self.assertFalse(token.is_expired)  # Always passes

@freeze_time("2024-06-15 13:00:01")
def test_token_expired(self):
    with freeze_time("2024-06-15 12:00:00"):
        token = create_token(expires_in=3600)
    self.assertTrue(token.is_expired)  # Always passes
```

### Category 3: Ordering Dependencies (Usually 20% of flaky tests)

```python
# Detect ordering dependencies by running with --shuffle
# pytest-randomly or Django's --shuffle flag

# ❌ COMMON BUG: test relies on auto-increment IDs
def test_get_latest_order(self):
    order = Order.objects.create(total=100)
    resp = self.client.get(f"/api/orders/{order.id}/")
    # Assumes order.id is 1, but previous tests may have created orders

# ✅ FIX: use the actual ID, never assume
def test_get_latest_order(self):
    order = Order.objects.create(total=100)
    resp = self.client.get(f"/api/orders/{order.id}/")
    self.assertEqual(resp.json()["id"], order.id)
```

### Category 4: External Dependencies (Usually 15%)

```python
# ❌ COMMON BUG: test hits real service
def test_send_notification(self):
    send_sms("+15551234567", "Hello")  # Calls Twilio!


# ✅ FIX: mock at the boundary
from unittest.mock import patch

@patch("myapp.notifications.twilio_client.messages.create")
def test_send_notification(self, mock_create):
    mock_create.return_value.sid = "SM123"
    send_sms("+15551234567", "Hello")
    mock_create.assert_called_once()
```

## Step 3: Prevent New Flakiness

```ini
# pytest.ini — enforcement
[pytest]
# Always randomize test order to catch ordering deps immediately
addopts = -p randomly --randomly-seed=last

# Fail if any test takes too long (likely waiting on network)
timeout = 10
```

```python
# conftest.py — block network access in tests
import socket

@pytest.fixture(autouse=True)
def block_network(monkeypatch):
    """No test should make real network calls."""
    def guard(*args, **kwargs):
        raise RuntimeError(
            "Tests must not make real network calls. "
            "Mock the external dependency."
        )
    monkeypatch.setattr(socket, "socket", guard)
```

## Expected Impact

| Fix | Effort | Flaky tests fixed |
|-----|--------|------------------|
| setUp instead of setUpClass | 2 days | ~40% of flaky tests |
| freezegun for time-dependent | 1 day | ~25% |
| --shuffle + fix ordering deps | 2 days | ~20% |
| Network blocking fixture | 0.5 day | ~15% |

One week of focused work should drop your flakiness rate from 15% to under 1%.'''
    ),
    (
        "thinking/causal-deploy-rollback-cascade",
        "We deployed a database migration that added a NOT NULL column with a default value. After the deploy, we noticed errors and tried to rollback the code, but the OLD code couldn't read from the table anymore. What went wrong and how do we prevent this?",
        r'''<think>
Classic forward-only migration trap. Let me trace the causal chain.

**The sequence of events:**
1. Migration adds NOT NULL column with a default value
2. New code deploys, works fine with the new column
3. Errors detected (maybe in the new code's logic, not the schema)
4. Team rolls back CODE to the previous version
5. Old code fails because it doesn't know about the new column

Wait, that shouldn't cause failures by itself. Adding a column shouldn't break old code that doesn't reference it. Let me think about what ACTUALLY breaks...

**What actually broke:**
Several possibilities:
1. `SELECT *` — old code does `SELECT * FROM table`, ORM maps all columns, the new NOT NULL column with default works for new rows but...
2. The old code INSERTS rows without specifying the new column. If the default is application-level (not database-level), inserts fail with NOT NULL violation.
3. The migration altered the table in a way that caused a table lock, and running queries timed out.

Most likely cause: **The default was set at the ORM level, not the database level.**

```python
# Django migration
migrations.AddField("Order", "priority",
    models.IntegerField(default=0))  # ORM default, NOT db default!
```

Django adds the column as NOT NULL with a one-time database default to backfill existing rows, then REMOVES the database default. Future inserts must provide the value from application code.

So when old code (which doesn't know about `priority`) inserts a new Order, PostgreSQL rejects it:
`ERROR: null value in column "priority" violates not-null constraint`

**Counterfactual analysis:**
- If the column was NULLABLE → old code inserts would succeed (NULL is allowed)
- If the database default was preserved → old code inserts would succeed (DB applies default)
- If old code didn't INSERT → reads would work fine (extra column is ignored)

**The root cause:** Schema and code were coupled — rolling back code without rolling back schema created an incompatible state.
</think>

The root cause is that Django (and most ORMs) set column defaults at the **application level**, not the database level. Here's the full causal chain:

## What Happened

```
Timeline:
1. Migration runs: ALTER TABLE orders ADD COLUMN priority INT NOT NULL DEFAULT 0
   ↓ Django backfills existing rows with 0
   ↓ Then REMOVES the database default (Django's behavior!)
   ↓ Now the column is NOT NULL with NO database default

2. New code deploys: Order.objects.create(priority=1)  ← works fine

3. Errors found in new code logic, team rolls back CODE

4. Old code runs: Order.objects.create(name="Widget", total=100)
   ↓ Old code doesn't know about `priority` column
   ↓ INSERT INTO orders (name, total) VALUES ('Widget', 100)
   ↓ PostgreSQL: ERROR - null value in column "priority" violates not-null constraint
   ↓ 💥 ALL order creation is broken
```

## Why Django Does This

Django's migration creates a database default temporarily to backfill, then drops it. The reasoning: Django wants the application to be the single source of truth for defaults, not the database. But this makes rollbacks unsafe.

## The Fix: Three Rules for Safe Migrations

### Rule 1: Add columns as NULLABLE first

```python
# ✅ SAFE: nullable column — old code can insert without it
class Migration(migrations.Migration):
    operations = [
        migrations.AddField("Order", "priority",
            models.IntegerField(null=True, blank=True)),  # NULLABLE
    ]

# Later migration (after old code is gone):
# Make it NOT NULL with a default
class Migration(migrations.Migration):
    operations = [
        migrations.RunSQL(
            "UPDATE orders SET priority = 0 WHERE priority IS NULL",
            migrations.RunSQL.noop,
        ),
        migrations.AlterField("Order", "priority",
            models.IntegerField(default=0)),
    ]
```

### Rule 2: If NOT NULL is required, preserve the DB default

```python
# ✅ SAFE: use RunSQL to keep the database default
class Migration(migrations.Migration):
    operations = [
        migrations.RunSQL(
            # Add column with a PERSISTENT database default
            "ALTER TABLE orders ADD COLUMN priority INTEGER NOT NULL DEFAULT 0",
            # Reverse
            "ALTER TABLE orders DROP COLUMN priority",
        ),
        # Tell Django the field exists (without Django managing the default)
        migrations.AddField("Order", "priority",
            models.IntegerField(default=0),
        ),
    ]
```

### Rule 3: Always test rollback compatibility

```python
# Add to your CI pipeline
def test_migration_rollback_compatibility():
    """
    Verify that the PREVIOUS version of the code works
    with the CURRENT database schema.
    """
    # 1. Run migrations (new schema)
    call_command("migrate")

    # 2. Check that basic operations work without the new field
    from django.db import connection
    with connection.cursor() as cursor:
        # Simulate old code inserting without new column
        cursor.execute(
            "INSERT INTO orders (name, total, created_at) "
            "VALUES ('test', 100, NOW())"
        )
        # If this raises, the migration is NOT rollback-safe
```

## Prevention Checklist

Before merging any migration:

```markdown
- [ ] New columns are NULLABLE, or have a PERSISTENT database default
- [ ] Old code can INSERT/UPDATE without knowing about new columns
- [ ] Old code can SELECT without breaking on new columns
- [ ] Migration has been tested with BOTH old and new code versions
- [ ] No column renames (use add new + backfill + remove old)
- [ ] No column type changes without a transition period
```

The golden rule: **your database schema must be compatible with BOTH the current and previous version of your code at all times.** This is the expand-contract pattern applied to every migration.'''
    ),
    (
        "thinking/causal-cpu-spike-json-parsing",
        "Our Python API server suddenly started using 100% CPU on all cores. Response times went from 50ms to 5 seconds. Nothing was deployed in the last 24 hours. Traffic volume is normal. The spike started at exactly 2:47 PM yesterday. What diagnostic approach should I take?",
        r'''<think>
Sudden CPU spike with no deploy and normal traffic — this is interesting. The exact timestamp (2:47 PM) suggests a specific trigger event, not gradual degradation.

Let me think about what could cause 100% CPU without a deploy or traffic increase:

**Hypothesis 1: Data-driven CPU spike**
The code didn't change, but the DATA did. At 2:47 PM, someone:
- Uploaded a very large document/payload
- Created a record with unusual data (deeply nested JSON, huge text field)
- Triggered a report/query on a dataset that just crossed a size threshold

This is the most likely cause given the exact timestamp and no deploys.

**Hypothesis 2: Background job trigger**
A scheduled task (cron, Celery beat) kicked off at 2:47 PM:
- A periodic data aggregation job
- A cache rebuild that's now processing more data than before
- A report generation task

But this would typically affect only the workers, not the API server.

**Hypothesis 3: External dependency change**
A service you depend on started returning different responses:
- An API returning much larger payloads (JSON parsing is CPU-intensive for large payloads)
- A database query plan changed (PostgreSQL auto-vacuum can trigger plan changes)
- A CDN or cache expired, causing cache stampede

**Hypothesis 4: Regex catastrophe**
A user input hit a catastrophic backtracking regex. This can pin a CPU core at 100% for minutes. If multiple requests hit the same regex, all cores are saturated.

**Hypothesis 5: Infinite loop triggered by edge case data**
An edge case in business logic caused an infinite or very long loop.

**Diagnostic approach:**
The exact timestamp is the key. What happened at 2:47 PM?
1. Check application logs around 2:47
2. Check database logs for slow queries
3. Profile the running process NOW (what's it spending CPU on?)
4. Check for any data changes at that timestamp

Let me prioritize the profiling approach since the issue is ongoing.
</think>

The exact timestamp (2:47 PM) with no deploy means something CHANGED IN THE DATA or environment, not the code. Here's the diagnostic approach:

## Step 1: Profile What's Eating CPU RIGHT NOW (5 minutes)

```bash
# Attach py-spy to the running process (no restart needed)
pip install py-spy
py-spy top --pid $(pgrep -f "gunicorn")

# Or get a flame graph
py-spy record --pid $(pgrep -f "gunicorn") -o profile.svg --duration 30
```

This immediately tells you which function is consuming CPU. Common findings:

| py-spy shows time in... | Likely cause |
|---|---|
| `json.loads` / `json.dumps` | Parsing huge JSON payloads |
| `re.match` / `re.search` | Catastrophic regex backtracking |
| `xml.etree` / `lxml` | Parsing malformed/huge XML |
| `sqlalchemy` serialization | ORM materializing huge result sets |
| Your business logic function | Algorithmic complexity with large input |

## Step 2: Find the Trigger Event (10 minutes)

```sql
-- What happened at 2:47 PM? Check for unusual data.
-- Large records created around that time:
SELECT id, created_at, pg_column_size(data) as size_bytes
FROM api_requests
WHERE created_at BETWEEN '2024-01-15 14:45:00' AND '2024-01-15 14:50:00'
ORDER BY pg_column_size(data) DESC
LIMIT 20;

-- Check for any large objects inserted:
SELECT relname, n_tup_ins
FROM pg_stat_user_tables
WHERE n_tup_ins > 0
ORDER BY n_tup_ins DESC;
```

```bash
# Check application logs around the trigger time
grep "14:4[5-9]\|14:5[0-9]" /var/log/app/api.log | head -50

# Check for any cron/scheduled tasks
grep "14:47" /var/log/syslog
crontab -l | grep "14:47\|2:47"
```

## Step 3: Common Root Causes and Fixes

### Most Likely: Giant JSON Payload

```python
# ❌ THE BUG: no size limit on request body
@app.route("/api/webhook", methods=["POST"])
def webhook():
    data = request.get_json()  # Parses ANY size payload
    process(data)  # Iterates over potentially millions of items

# ✅ THE FIX: limit payload size
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB max

@app.route("/api/webhook", methods=["POST"])
def webhook():
    data = request.get_json()
    if isinstance(data.get("items"), list) and len(data["items"]) > 10000:
        abort(413, "Too many items in payload")
    process(data)
```

### Second Most Likely: Catastrophic Regex

```python
# ❌ THE BUG: user input triggers exponential backtracking
import re
EMAIL_REGEX = re.compile(r"^([a-zA-Z0-9_.+-]+)+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

def validate_email(email: str):
    return EMAIL_REGEX.match(email)  # Takes MINUTES for crafted input

# Test: validate_email("a" * 50 + "@") → hangs

# ✅ THE FIX: use atomic groups or simple validation
import re
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")
# Removed the nested group ()+  which caused backtracking

# Or better: use a library
from email_validator import validate_email
```

### Third: Query Plan Regression

```sql
-- Check for slow queries starting at 2:47 PM
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- If a query that was fast is now slow, check the plan:
EXPLAIN (ANALYZE, BUFFERS) SELECT ... -- the slow query

-- Common cause: auto-vacuum changed statistics, planner chose seq scan over index
-- Fix: ANALYZE the table to refresh statistics
ANALYZE problematic_table;
```

## The Immediate Mitigation

While you investigate:

```bash
# Set a request timeout to prevent CPU-bound requests from running forever
# gunicorn.conf.py
timeout = 30  # Kill worker after 30s

# Or with uvicorn
uvicorn app:app --timeout-keep-alive 30
```

The pattern: no-deploy CPU spikes are almost always **data-driven** — the code handles normal data fine, but a specific payload or data volume crosses a complexity threshold. The exact timestamp is your best clue: find what data was created or received at 2:47 PM.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
