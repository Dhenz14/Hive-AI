"""Phase 2F: Advanced Reasoning — Uncertainty & Confidence Calibration (Part 2/3)
Expressing genuine uncertainty: 'will this approach work at 100x scale?',
'which testing strategy is most cost-effective?', 'should we add this dependency?'"""

PAIRS = [
    (
        "thinking/uncertainty-scale-100x",
        "We're using WebSockets to push real-time notifications to users. Currently works fine for 5K concurrent connections. Will it handle 500K connections when we scale?",
        r'''<think>
Let me think about what I'm confident about vs what I don't know.

What I'm confident about (>90%):
- A single server process can handle 10K-50K WebSocket connections (depending on implementation)
- 500K connections = need multiple servers + load balancing
- WebSocket connections are long-lived → different scaling characteristics than HTTP
- Memory per connection: 10-50KB typically → 500K × 50KB = 25GB just for connections
- Heartbeat/keepalive overhead: 500K connections × ping every 30s = 16K pings/sec

What I'm moderately confident about (60-80%):
- The sticky session requirement for WebSockets makes horizontal scaling harder
- Most WebSocket scaling issues are about MESSAGE FANOUT, not connection count
  - "Send notification to 500K users" = 500K messages to dispatch
  - This is the hard part, not the connections themselves
- Redis Pub/Sub or a message broker is needed for cross-server message distribution

What I'm genuinely uncertain about (<50%):
- Will THEIR specific implementation handle it? Depends on:
  - Language/runtime (Go handles more connections than Python)
  - Message frequency (1 msg/hour vs 1 msg/second per user)
  - Message size (10 bytes vs 10KB)
  - Server resources (how much RAM per server?)
  - Whether they need reliable delivery or best-effort

I should NOT say "yes it will work" or "no it won't" without knowing these details. I should quantify the uncertainty and tell them what they need to measure.
</think>

**I can't give a confident yes/no without knowing your specifics. Here's what determines the answer:**

**What I'm confident about (90%+)**:
```
Single server capacity:
  Python (asyncio): 5K-20K connections per process
  Node.js:          10K-50K connections per process
  Go:               100K-500K connections per process
  Elixir/Erlang:    500K-2M connections per process

For 500K connections, you WILL need multiple servers regardless of language.
```

**The critical questions I can't answer without your data**:
```
Question                          | If THIS → can handle 500K | If THAT → trouble
----------------------------------|--------------------------|-------------------
Message frequency per user?       | 1/hour (easy)            | 1/second (hard)
Message size?                     | <1KB (easy)              | >10KB (hard)
Broadcast vs targeted?            | Targeted (easy)          | "Send to all" (hard)
Language/runtime?                 | Go/Elixir (easy)         | Python (need many processes)
Reliable delivery required?       | Best-effort (easy)       | Guaranteed (much harder)
```

**The calculation you should do**:
```python
# Memory budget
connections = 500_000
memory_per_conn_kb = 50  # Measure this in YOUR app
total_memory_gb = connections * memory_per_conn_kb / 1024 / 1024
# 500K × 50KB = 25GB — need servers with enough RAM

# Message throughput
msgs_per_user_per_second = 0.1  # One message every 10 seconds average
total_msgs_per_second = connections * msgs_per_user_per_second
# 500K × 0.1 = 50K messages/second — achievable but non-trivial

# Heartbeat overhead
heartbeat_interval_seconds = 30
heartbeats_per_second = connections / heartbeat_interval_seconds
# 500K / 30 = 16.7K pings/second — significant overhead

# Server count needed
connections_per_server = 50_000  # Conservative estimate
servers_needed = connections / connections_per_server
# 500K / 50K = 10 servers minimum

print(f"Memory needed: {total_memory_gb:.1f} GB")
print(f"Message rate: {total_msgs_per_second:.0f} msgs/sec")
print(f"Servers needed: {servers_needed:.0f}")
```

**What I'm 80% confident you'll need at 500K**:
```
1. Multiple WebSocket servers behind a load balancer
   → Sticky sessions (route same user to same server)
   → Or use a shared message bus

2. Redis Pub/Sub or similar for cross-server messaging
   → Server A receives "notify user X"
   → User X is connected to Server B
   → Server A publishes to Redis → Server B receives → delivers to user X

3. Connection management
   → Graceful reconnection (clients will disconnect, need to reconnect)
   → Connection draining during deploys
   → Dead connection cleanup (heartbeat timeout)
```

**My honest probability assessment**:
```
60% chance: Your current architecture handles 500K with horizontal scaling
            (add servers, add Redis Pub/Sub, optimize memory per connection)

30% chance: You need architectural changes
            (message fanout is the bottleneck, need dedicated push infrastructure)

10% chance: You need to switch approaches entirely
            (SSE instead of WebSocket, or polling for low-frequency updates)
```

**What to do NOW**: Load test with 50K connections. If that works, 500K is achievable with 10x more servers. If 50K shows problems, 500K will require architectural changes.'''
    ),
    (
        "thinking/uncertainty-add-dependency",
        "We need to parse YAML config files. Should we add PyYAML as a dependency, or write our own parser for the subset we need? Our config files are simple key-value pairs with maybe one level of nesting.",
        r'''<think>
Let me think about this honestly. This seems like it should be an obvious "use PyYAML" answer, but let me consider both sides.

Arguments for PyYAML (the dependency):
- Battle-tested, handles all YAML edge cases
- Maintained, security patches
- Everyone knows it
- 5 minutes to implement vs hours to write a parser
- YAML is complex — even "simple" YAML has gotchas (Norway problem: `NO` = False)

Arguments for writing your own:
- PyYAML has security issues (yaml.load arbitrary code execution)
- PyYAML is slow for large files
- Another dependency to maintain, update, audit
- Your config is "simple" — maybe you don't even need YAML?
- PyYAML has a C extension that can cause installation issues

But wait — I need to challenge the premise. If the config is "simple key-value pairs with one level of nesting," do they even need YAML? TOML, INI, JSON, or even .env files might be better choices for simple config.

My honest assessment:
- 85% chance: use PyYAML (or better, use tomllib which is stdlib in Python 3.11+)
- 10% chance: use TOML instead of YAML (better for config, fewer gotchas)
- 5% chance: write your own (only if they have a specific reason to avoid dependencies)

But I should express that the REAL question might be "should we use YAML at all for simple config?"
</think>

**90% confident: use an existing library. But you might be solving the wrong problem.**

**The straightforward answer**: Use PyYAML (or better, `tomllib` if Python 3.11+). Writing a YAML parser is much harder than you think.

**Why "simple YAML" is a trap**:
```yaml
# You think your YAML is simple:
name: myapp
debug: true
port: 8080

# But YAML has gotchas even in "simple" cases:
country: NO      # ← Parsed as boolean False! (the "Norway problem")
version: 1.0     # ← Parsed as float, not string "1.0"
password: 12345  # ← Parsed as integer, not string
api_key: null    # ← Parsed as None, not string "null"
time: 12:30:00   # ← Parsed as integer 45000 (seconds since midnight!)

# Writing your own parser means handling ALL of these correctly.
# Even if you "only support a subset," users WILL write these values.
```

**But here's the real question (80% confident this is better)**:
```python
# If your config is "simple key-value pairs with one level of nesting,"
# you probably don't need YAML at all.

# Option 1: TOML (stdlib in Python 3.11+) — BEST for config files
# No third-party dependency needed!
import tomllib  # Built into Python 3.11+

with open("config.toml", "rb") as f:
    config = tomllib.load(f)

# config.toml — no gotchas, clear syntax
# [server]
# name = "myapp"
# debug = true
# port = 8080

# Option 2: JSON — already in stdlib, no dependency
import json
with open("config.json") as f:
    config = json.load(f)
# Downside: no comments allowed in JSON

# Option 3: .env file — simplest possible
# APP_NAME=myapp
# DEBUG=true
# PORT=8080
from dotenv import load_dotenv  # or just os.getenv()
```

**Decision matrix**:
```
Format  | Stdlib? | Comments? | Nesting? | Gotchas? | Best for
--------|---------|-----------|----------|----------|---------
TOML    | 3.11+   | Yes       | Yes      | Few      | App config ✅
JSON    | Yes     | No        | Yes      | Few      | API/data
YAML    | No      | Yes       | Deep     | Many     | K8s/Ansible
.env    | ~Yes    | Yes       | No       | None     | Simple key-value
INI     | Yes     | Yes       | 1 level  | Few      | Legacy config
```

**My recommendation with confidence levels**:
```
If Python 3.11+:  Use TOML (tomllib) — 95% confident this is best
                  Zero dependencies, no gotchas, designed for config files

If Python < 3.11: Use PyYAML with safe_load — 80% confident
                  pip install pyyaml, use yaml.safe_load() (NEVER yaml.load())

Writing your own: 5% — only if you have a hard no-dependencies requirement
                  AND your config is truly key=value with no nesting
```

**If you must use PyYAML**:
```python
import yaml

# NEVER this (arbitrary code execution vulnerability):
config = yaml.load(open("config.yaml"))

# ALWAYS this (safe):
config = yaml.safe_load(open("config.yaml"))
```'''
    ),
    (
        "thinking/uncertainty-testing-strategy",
        "We have limited engineering time for testing. Should we focus on unit tests, integration tests, or end-to-end tests? We can't do all three well.",
        r'''<think>
This is a genuinely context-dependent question. The "testing pyramid" (lots of unit tests, fewer integration, fewest E2E) is conventional wisdom, but it's not always right.

What I'm fairly confident about:
- The right testing strategy depends on the type of application
- "Do all three poorly" is worse than "do one well"
- Integration tests catch the most REAL bugs per test
- Unit tests are fastest and cheapest to maintain
- E2E tests are most expensive but catch the most user-facing issues

What I'm less certain about:
- Whether this team's "limited time" means 20% or 5% of engineering time
- What kind of app this is (API? UI? data pipeline? library?)
- Whether they have CI/CD (tests without CI are much less valuable)
- Their current test coverage (starting from zero vs improving existing)

Different apps need different strategies:
- Library/utility: Unit tests dominate (no infrastructure dependencies)
- API/backend: Integration tests dominate (test the real database, real endpoints)
- UI-heavy app: E2E tests dominate (test what users actually see)
- Data pipeline: Integration tests (test with real data shapes)

I should express this uncertainty and help them make the right choice for THEIR situation.
</think>

**There's no universal answer. The right strategy depends on your app type.** Here's how to decide:

**My confidence in each recommendation by app type**:

```
App type              | Focus on            | Confidence | Why
----------------------|---------------------|------------|----
REST/GraphQL API      | Integration tests   | 85%        | Test real DB + HTTP
UI-heavy web app      | E2E tests          | 75%        | Test what users see
Internal library      | Unit tests          | 90%        | Pure logic, no infra
Data pipeline         | Integration tests   | 80%        | Test with real data shapes
Microservices         | Contract tests      | 70%        | Test service boundaries
Legacy (no tests)     | Integration tests   | 80%        | Highest ROI first
```

**The conventional "testing pyramid" is wrong for many apps**:
```
CONVENTIONAL WISDOM (testing pyramid):
  △ Few E2E tests
  ▲ Some integration tests
  ████ Many unit tests
  → Makes sense for libraries and pure-logic code

REALITY FOR MOST WEB APPS (testing trophy — Kent C. Dodds):
  △ Few E2E tests
  ████ Many integration tests  ← MOST value here
  ▲ Some unit tests
  → Integration tests catch the most real bugs per test
```

**If I had to pick ONE type (with limited time)**:

```python
# FOR AN API: Integration tests (85% confident this is right)
# One integration test replaces 5-10 unit tests

# Instead of:
def test_validate_email():          # Unit test
    assert validate_email("a@b.com") == True
def test_hash_password():           # Unit test
    assert hash_password("pass") != "pass"
def test_create_user_db():          # Unit test with mock
    mock_db.insert.return_value = User(id=1)
    # ... 10 more lines of mock setup
def test_send_welcome_email():      # Unit test with mock
    mock_email.send.assert_called_once()
# 4 unit tests, lots of mocks, tests implementation details

# Write ONE integration test that covers the whole flow:
@pytest.mark.integration
async def test_user_registration(test_client, test_db):
    response = await test_client.post("/api/register", json={
        "email": "alice@example.com",
        "password": "secure_password_123",
    })
    assert response.status_code == 201

    # Verify the user was actually created in the real DB
    user = await test_db.fetch_one("SELECT * FROM users WHERE email = $1", "alice@example.com")
    assert user is not None
    assert user["password_hash"] != "secure_password_123"  # Hashed

    # Verify welcome email was queued
    emails = await test_db.fetch("SELECT * FROM email_queue WHERE to_address = $1", "alice@example.com")
    assert len(emails) == 1
# ONE test that catches: validation bugs, DB bugs, hashing bugs, email bugs
```

**What I genuinely don't know** (and you need to decide):
```
Question                              Impact on strategy
─────────────────────────────         ─────────────────────────
Is your code mostly business logic?   → Unit tests (test the logic)
Is your code mostly glue/integration? → Integration tests (test the glue)
Do you have a CI/CD pipeline?         → Tests without CI are 50% less valuable
Is the team comfortable with Docker?  → Needed for integration tests with real DB
How often do deploys break?           → If often → E2E smoke tests are highest ROI
```

**If forced to give ONE recommendation without context (70% confident)**: Write integration tests for your 5 most critical user flows. They catch the most real bugs per hour of engineering time invested. Add unit tests later for complex business logic. Add E2E tests for the most critical happy path.'''
    ),
    (
        "thinking/uncertainty-intermittent-failure",
        "We have an intermittent bug that happens about once per week. Users see a 500 error, but by the time we check, everything looks fine. Logs show a generic 'NullPointerException' in our Java service. How do I find and fix this?",
        r'''<think>
Intermittent bugs are the hardest to diagnose because they leave minimal evidence. Let me think about what I know and don't know.

What I'm fairly confident about (>80%):
- "Generic NullPointerException" means a null value reached code that didn't expect it
- Once per week = triggered by a specific condition, not random
- "By the time we check, everything looks fine" = the condition is transient
- We need better logging/monitoring to catch it next time

What I'm moderately confident about (60-80%):
- Common causes of intermittent NPE:
  1. Race condition: two threads access shared mutable state
  2. Cache expiry: cached value returns null after TTL
  3. External service returning null in edge cases
  4. Database connection pool returning stale connection
  5. GC pause + timeout causing a null where a live reference was expected

What I'm uncertain about (<50%):
- Whether this is a race condition or a data-dependent condition
- Whether "once per week" is time-based (cron) or load-based (happens during peaks)
- What the actual null reference is — "generic NPE" is useless without line number

My honest assessment: I can't diagnose this from the description alone. But I can recommend a systematic approach to CATCH it next time it happens.
</think>

**Honest answer: I can't diagnose this without more data. But I can tell you how to catch it.**

**The problem with intermittent bugs**: By definition, you can't reproduce them on demand. So instead of trying to find the bug, **instrument the code to catch it next time**.

**Step 1: Get actionable error information** (90% confident this is your first problem):
```java
// BEFORE: Generic NPE with no context
// java.lang.NullPointerException
//   at com.myapp.OrderService.processOrder(OrderService.java:42)

// AFTER: Rich context when the null appears
public Order processOrder(OrderRequest request) {
    Objects.requireNonNull(request, "OrderRequest was null");
    Objects.requireNonNull(request.getUserId(), "userId was null in OrderRequest");
    Objects.requireNonNull(request.getItems(), "items was null in OrderRequest");

    User user = userService.getUser(request.getUserId());
    if (user == null) {
        // Don't NPE — log the specific condition
        logger.error("User not found for userId={}, requestId={}, timestamp={}",
            request.getUserId(), request.getRequestId(), Instant.now());
        throw new UserNotFoundException(request.getUserId());
    }

    // ... rest of logic
}
```

**Step 2: Correlate with conditions** (find the pattern):
```python
# Track WHEN it happens — find the pattern
# Once per week could mean:
# - Weekly cron job creates the condition
# - Peak load on Monday mornings
# - Cache expires every 7 days
# - External service maintenance window

# Add structured logging around the failing code:
logger.info("process_order_start",
    extra={
        "user_id": request.user_id,
        "item_count": len(request.items),
        "cache_age_seconds": cache.age("user:" + request.user_id),
        "db_pool_active": db_pool.active_connections,
        "db_pool_idle": db_pool.idle_connections,
        "thread_count": threading.active_count(),
        "heap_usage_mb": get_heap_usage(),
        "timestamp": datetime.utcnow().isoformat(),
    }
)
```

**Step 3: Set a trap** (70% confident one of these will catch it):
```java
// Hypothesis 1: Race condition (check with thread-safety analysis)
// Add @ThreadSafe or use synchronized in suspected areas
// Enable -XX:+HeapDumpOnOutOfMemoryError

// Hypothesis 2: Cache returns null after expiry
// Add logging to cache get/set:
public Object getFromCache(String key) {
    Object value = cache.get(key);
    if (value == null) {
        logger.debug("Cache MISS for key={}, this could cause NPE downstream", key);
    }
    return value;
}

// Hypothesis 3: External service returning null
// Log all external responses:
User user = externalUserService.getUser(userId);
logger.info("External user service response: userId={}, result={}", userId,
    user != null ? "found" : "NULL");

// Hypothesis 4: Database connection issue
// Monitor connection pool health:
// Add metrics for: pool size, active connections, wait time, timeout events
```

**My ranked hypotheses** (from most to least likely):
```
Probability | Cause                          | How to verify
65%         | Cache returns null after TTL    | Log cache hit/miss around NPE code
            | (user/session cache expires)     | Check if failures correlate with cache age

20%         | Race condition (concurrent      | Enable thread dump on error
            | request modifies shared state)   | Check if failures correlate with load spikes

10%         | External service intermittently  | Log all external service responses
            | returns null                     | Check if failures correlate with partner downtime

5%          | Database connection pool issue   | Monitor pool metrics
            | (stale connection returns null)  | Check if failures correlate with DB maintenance
```

**What I'd bet on (65% confident)**: It's a cache expiry issue. Some user data is cached, the cache entry expires, the code assumes the cached value is never null, and NPE. Once per week lines up with a 7-day TTL. Add null checks after every cache read.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
