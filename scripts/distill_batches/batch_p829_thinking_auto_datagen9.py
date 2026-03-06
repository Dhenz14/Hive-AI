"""Phase 4A: Self-Improvement — Training Data Generation (Part 9)

Generate and evaluate training pairs for debugging skill topics.
Each answer creates 3 graded training pairs with quality analysis.
"""

PAIRS = [
    (
        "thinking/auto-datagen-systematic-debugging",
        r'''Generate 3 high-quality training pairs that teach systematic debugging methodology. For each pair, explain why it's effective training data.''',
        r'''<think>
To create effective training data for systematic debugging, I need to consider:
1. Common mistakes: jumping to conclusions, changing random things, not reading error messages
2. Real scenarios: production bugs, race conditions, intermittent failures
3. Difficulty progression: reading error messages -> bisecting problems -> debugging distributed systems

The key insight is that debugging is a skill that can be learned systematically, not just trial and error.
</think>

Here are 3 training pairs for systematic debugging:

**Pair 1 (Beginner):**
```
Q: My Python script crashes with "TypeError: 'NoneType' object is not subscriptable" on line 42. I've been staring at the code for an hour. How do I fix this?

A: The error tells you exactly what's wrong — you're trying to index into something that is None. Here's a systematic approach:

**Step 1: Read the error precisely.**
"NoneType object is not subscriptable" means you're doing something like `result[0]` or `result['key']` where `result` is None.

**Step 2: Look at line 42 and find every subscript operation.**
```python
# Line 42 might look like:
data = response.json()['results'][0]['name']
# Any of these could be None: response.json(), ['results'], [0]
```

**Step 3: Add a print before line 42:**
```python
print(repr(response.json()))  # See exactly what you're working with
```

**Step 4: Handle the None case:**
```python
data = response.json()
if data and 'results' in data and data['results']:
    name = data['results'][0]['name']
else:
    name = None  # or raise a clear error
```

**The debugging principle:** Read the error message literally. "NoneType is not subscriptable" = "something is None and you're indexing it." Find the None.
```
*Why this is effective:* Teaches the most fundamental debugging skill — actually reading error messages — which most beginners skip entirely.

**Pair 2 (Intermediate):**
```
Q: My web application works fine locally but returns 500 errors in production. The logs just show "Internal Server Error" with no traceback. How do I debug this?

A: The gap between local and production is one of the most common debugging challenges. Here's a systematic approach:

**1. Get real error information (your first priority):**
```python
# In your Flask/Django app, ensure you're logging exceptions:
import logging
logging.basicConfig(level=logging.ERROR)

@app.errorhandler(500)
def handle_500(e):
    app.logger.exception("500 error")  # This logs the full traceback
    return "Internal Server Error", 500
```

**2. Check what's DIFFERENT between local and production:**
| Factor | Local | Production |
|--------|-------|------------|
| Environment variables | .env file | Server config |
| Database | SQLite/local PG | Remote PG/RDS |
| File paths | Relative work | May not exist |
| Permissions | Your user | App user |
| Network | localhost | Firewalls, DNS |
| Dependencies | Latest | Pinned/different |

**3. Reproduce with production-like config locally:**
```bash
# Use production environment variables locally:
DATABASE_URL=postgresql://prod-like-url python app.py
```

**4. Common culprits for "works locally, breaks in production":**
- Missing environment variables (DATABASE_URL, SECRET_KEY, API keys)
- File paths that don't exist on the server
- Database migrations not run in production
- Different Python/library versions
- Permission denied on file writes
```
*Why this is effective:* Addresses the real-world gap between environments, teaching a systematic elimination process rather than guesswork.

**Pair 3 (Advanced):**
```
Q: We have an intermittent bug — about 5% of API requests return wrong data. It only happens under load. How do I track this down?

A: Intermittent bugs under load almost always involve concurrency issues. Here's a systematic approach:

**1. Characterize the failure pattern:**
```bash
# Run a load test and capture failures:
hey -n 10000 -c 50 http://api/endpoint | tee results.txt
# Analyze: Do failures cluster in time? Under specific concurrency levels?
```

**2. Check for common concurrency bugs:**

**Race condition in shared state:**
```python
# BUG: Shared mutable state without locking
cache = {}
def get_user(user_id):
    if user_id not in cache:
        cache[user_id] = db.query(user_id)  # Two threads can interleave here
    return cache[user_id]
```

**Connection pool exhaustion:**
```python
# BUG: Not returning connections to the pool
def get_data():
    conn = pool.getconn()
    result = conn.execute(query)
    # If exception here, connection leaks
    return result  # conn never returned to pool
```

**Non-atomic read-modify-write:**
```python
# BUG: Read-modify-write without transaction
balance = db.get_balance(account_id)    # Thread A reads 100
balance -= amount                        # Thread B also reads 100
db.set_balance(account_id, balance)      # Both write 90, should be 80
```

**3. Add request-level tracing:**
```python
import uuid
@app.before_request
def add_request_id():
    request.id = str(uuid.uuid4())
    app.logger.info(f"[{request.id}] {request.method} {request.path}")
```

**4. Use thread-safe alternatives:**
- Replace dict cache with `functools.lru_cache` or Redis
- Use database transactions for read-modify-write
- Use connection pool context managers (with/finally)
```
*Why this is effective:* Teaches debugging skills that only apply under concurrency — the hardest class of bugs — with concrete patterns to look for.'''
    ),
    (
        "thinking/auto-datagen-reading-stack-traces",
        r'''Generate 3 high-quality training pairs that teach how to read and interpret stack traces effectively. For each pair, explain why it's effective training data.''',
        r'''<think>
Stack trace reading is fundamental but poorly taught. Key areas:
1. Understanding the structure of a traceback (bottom-up vs top-down)
2. Distinguishing your code from library code in the trace
3. Using the trace to identify root cause vs symptom

Progression: simple Python traceback -> multi-layer framework traceback -> async/concurrent stack traces
</think>

Here are 3 training pairs for reading stack traces:

**Pair 1 (Beginner):**
```
Q: I got this error and I don't know where to look:
Traceback (most recent call last):
  File "app.py", line 45, in main
    result = process_data(raw_input)
  File "app.py", line 23, in process_data
    cleaned = clean_record(record)
  File "app.py", line 12, in clean_record
    return record['name'].strip()
KeyError: 'name'

What does this mean and how do I read it?

A: A Python traceback reads BOTTOM TO TOP:

**Line to focus on FIRST — the bottom:**
```
KeyError: 'name'
```
This is the actual error: you tried to access a dictionary key 'name' that doesn't exist.

**Where it happened — second from bottom:**
```
File "app.py", line 12, in clean_record
    return record['name'].strip()
```
Line 12 of app.py, inside the function `clean_record`. The dictionary `record` doesn't have a 'name' key.

**How you got there — read upward for context:**
```
main() called process_data() called clean_record()
```

**The fix:** Check what `record` actually contains:
```python
def clean_record(record):
    print(record.keys())  # See what keys exist
    return record.get('name', '').strip()  # Use .get() for safety
```

**Rule of thumb:** Always read the LAST line first (the error), then the SECOND-TO-LAST line (where it happened), then work upward only if needed.
```
*Why this is effective:* Most beginners read tracebacks top-down and get confused by the call chain. Teaching bottom-up reading is the single most impactful debugging skill.

**Pair 2 (Intermediate):**
```
Q: I got a long traceback from Django and I can't tell which part is my code:
Traceback (most recent call last):
  File "/usr/lib/python3/django/core/handlers/exception.py", line 47, in inner
    response = get_response(request)
  File "/usr/lib/python3/django/core/handlers/base.py", line 181, in _get_response
    response = wrapped_callback(request, *callback_args, **callback_kwargs)
  File "/home/app/myproject/views.py", line 34, in user_profile
    orders = get_user_orders(user.id)
  File "/home/app/myproject/services.py", line 67, in get_user_orders
    return Order.objects.filter(user_id=uid).select_related('product')
  File "/usr/lib/python3/django/db/models/query.py", line 942, in filter
    return self._filter_or_exclude(False, args, kwargs)
  File "/usr/lib/python3/django/db/models/query.py", line 960, in _filter_or_exclude
    clone.query.add_q(Q(*args, **kwargs))
  File "/usr/lib/python3/django/db/models/sql/query.py", line 1388, in add_q
    clause, _ = self._add_q(q_object, self.used_aliases)
django.core.exceptions.FieldError: Cannot resolve keyword 'user_id' into field.

How do I find the actual problem in all this framework code?

A: **Filter out framework code. Focus on YOUR files.**

In this traceback, YOUR code is:
```
File "/home/app/myproject/views.py", line 34
File "/home/app/myproject/services.py", line 67
```

Everything in `/usr/lib/python3/django/` is framework internals — ignore it for now.

**The error:** `FieldError: Cannot resolve keyword 'user_id'`
**Your code that caused it:** `Order.objects.filter(user_id=uid)`

The field on your Order model is probably named `user` (a ForeignKey), not `user_id`. Django auto-creates `user_id` as the database column, but the ORM filter uses `user`:

```python
# Wrong:
Order.objects.filter(user_id=uid)

# Correct:
Order.objects.filter(user=uid)
# Or explicitly:
Order.objects.filter(user__id=uid)
```

**How to quickly scan long tracebacks:**
1. Read the LAST line (the error type and message)
2. Scan for YOUR file paths (not library/framework paths)
3. The bug is almost always in YOUR code, not the framework
```
*Why this is effective:* Real-world tracebacks are noisy with framework code. Teaching developers to visually filter for their own code paths dramatically speeds up debugging.

**Pair 3 (Advanced):**
```
Q: I'm getting a traceback that shows the error in a completely different place from where the actual bug is:
Traceback (most recent call last):
  File "app.py", line 89, in handle_request
    response = serialize_user(user)
  File "app.py", line 45, in serialize_user
    return {"name": user.name, "email": user.email, "age": user.age}
AttributeError: 'NoneType' object has no attribute 'name'

But serialize_user works fine when I test it directly. The bug must be somewhere else.

A: You're right — the traceback shows WHERE the error manifests, not WHERE the bug is. This is a "downstream error" — the real bug is UPSTREAM.

**The traceback tells you:** `user` is None when `serialize_user` is called.
**The real question:** Why is `user` None? Look at the CALLER:

```python
# Line 89: response = serialize_user(user)
# Where did 'user' come from? Look ABOVE line 89:

user = db.get_user(user_id)  # This returned None!
response = serialize_user(user)  # Crashes here, but the bug is above
```

**The real bug is in `db.get_user()` — it returned None instead of raising an error.**

**Defensive pattern to catch upstream bugs early:**
```python
user = db.get_user(user_id)
if user is None:
    raise ValueError(f"User {user_id} not found")  # Fail HERE with a clear message
response = serialize_user(user)
```

**General principle:** When a traceback doesn't make sense, the bug is upstream. Trace the variable backward through the code to find where it got its wrong value.

**Debugging technique — add assertions to catch bugs closer to the source:**
```python
def get_user(user_id):
    assert user_id is not None, "user_id must not be None"
    user = session.query(User).get(user_id)
    # Don't silently return None — let the caller know
    if user is None:
        raise LookupError(f"No user with id={user_id}")
    return user
```
```
*Why this is effective:* Teaches the critical concept that tracebacks show symptoms, not causes. Understanding upstream vs downstream errors is what separates competent debuggers from beginners.'''
    ),
    (
        "thinking/auto-datagen-debugger-tools",
        r'''Generate 3 high-quality training pairs that teach effective use of debugging tools (breakpoints, debuggers, logging). For each pair, explain why it's effective training data.''',
        r'''<think>
Most developers use print() debugging exclusively. Teaching them proper tools:
1. Using pdb/breakpoints in Python
2. Strategic logging vs print statements
3. Using browser DevTools for full-stack debugging

Progression: print debugging -> pdb/breakpoints -> structured logging for production
</think>

Here are 3 training pairs for debugging tools:

**Pair 1 (Beginner):**
```
Q: I use print() everywhere to debug my Python code. Is there a better way?

A: print() debugging works, but Python has a built-in debugger that's much more powerful:

**The upgrade path: print() -> breakpoint() -> logging**

**Instead of this:**
```python
def calculate_total(items):
    print(f"items = {items}")  # Debug
    total = 0
    for item in items:
        print(f"item = {item}")  # Debug
        price = item['price'] * item['quantity']
        print(f"price = {price}")  # Debug
        total += price
    print(f"total = {total}")  # Debug
    return total
```

**Do this:**
```python
def calculate_total(items):
    breakpoint()  # Drops you into an interactive debugger
    total = 0
    for item in items:
        price = item['price'] * item['quantity']
        total += price
    return total
```

**In the debugger (pdb), you can:**
```
(Pdb) p items          # Print any variable
(Pdb) p items[0]       # Inspect specific elements
(Pdb) n                # Execute next line
(Pdb) s                # Step INTO a function call
(Pdb) c                # Continue until next breakpoint
(Pdb) l                # Show code around current line
(Pdb) pp vars()        # Pretty-print all local variables
(Pdb) item['price'] * 2  # Evaluate any expression
```

**Why breakpoint() is better than print():**
1. You can inspect ANY variable without adding print statements for each one
2. You can step through code line by line
3. You can evaluate expressions on the fly
4. You don't need to remove debug prints afterward
5. You can change variable values during execution
```
*Why this is effective:* Directly addresses the most common debugging anti-pattern (print-everywhere) and provides a concrete upgrade path with the same familiar feel.

**Pair 2 (Intermediate):**
```
Q: When should I use logging instead of print statements? What log levels should I use?

A: Logging is for code you'll run in production. Print is for code you'll throw away.

**The key difference:**
```python
# print — goes to stdout, no context, no levels, no control
print(f"Processing order {order_id}")

# logging — goes anywhere, has levels, timestamps, context
import logging
logger = logging.getLogger(__name__)
logger.info("Processing order %s", order_id)
```

**When to use each log level:**
```python
import logging
logger = logging.getLogger(__name__)

# DEBUG: Detailed info for diagnosing problems (off in production)
logger.debug("Cache lookup for key=%s, hit=%s", key, hit)

# INFO: Confirmation that things work as expected
logger.info("Order %s placed successfully, total=%.2f", order_id, total)

# WARNING: Something unexpected but not an error (yet)
logger.warning("API rate limit at 80%%, backing off")

# ERROR: Something failed but the app continues
logger.error("Payment failed for order %s: %s", order_id, str(e))

# CRITICAL: The app can't continue
logger.critical("Database connection lost, shutting down")
```

**Production logging setup:**
```python
import logging

logging.basicConfig(
    level=logging.INFO,  # DEBUG in development
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()  # Also print to console
    ]
)
```

**Rule of thumb for what to log:**
- Log every external call (database, API, file I/O) at INFO
- Log every error with context (what were you trying to do?) at ERROR
- Log performance-sensitive operations with timing at DEBUG
- Never log passwords, tokens, or personal data
```
*Why this is effective:* Bridges the gap between development debugging (print) and production debugging (logging), with concrete rules for when to use each level.

**Pair 3 (Advanced):**
```
Q: How do I debug issues in production where I can't attach a debugger or add print statements?

A: Production debugging requires a different toolkit — you need observability built INTO the application before problems happen.

**The three pillars of production debugging:**

**1. Structured logging (searchable, parseable):**
```python
import structlog
logger = structlog.get_logger()

def process_order(order_id, user_id):
    log = logger.bind(order_id=order_id, user_id=user_id)
    log.info("processing_order_started")
    try:
        result = charge_payment(order_id)
        log.info("payment_charged", amount=result.amount)
    except PaymentError as e:
        log.error("payment_failed", error=str(e), retry_count=0)
        raise
```
Output: `{"event": "payment_failed", "order_id": "abc123", "user_id": "u456", "error": "card declined", "timestamp": "2024-01-15T10:30:00Z"}`

Searchable with: `jq '.event == "payment_failed"' app.log`

**2. Distributed tracing (follow a request across services):**
```python
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

def handle_request(request):
    with tracer.start_as_current_span("handle_request") as span:
        span.set_attribute("user_id", request.user_id)
        order = create_order(request)  # Automatically linked
        payment = process_payment(order)  # Automatically linked
        return {"order_id": order.id}
```

**3. Metrics and alerting:**
```python
from prometheus_client import Counter, Histogram

request_count = Counter('http_requests_total', 'Total requests', ['method', 'endpoint', 'status'])
request_duration = Histogram('http_request_duration_seconds', 'Request duration')

@request_duration.time()
def handle_request(request):
    response = do_work(request)
    request_count.labels(method='GET', endpoint='/api/orders', status=200).inc()
    return response
```

**Production debugging workflow:**
1. Alert fires (metric crossed threshold)
2. Check dashboard (which endpoint? which time range?)
3. Search structured logs (filter by time + endpoint)
4. Find the trace ID from logs
5. View distributed trace (see exactly where time was spent)
6. Identify root cause from trace + logs
```
*Why this is effective:* Teaches the production debugging mindset — you must instrument BEFORE problems happen. This is the skill gap between senior developers and everyone else.'''
    ),
    (
        "thinking/auto-datagen-debugging-memory-issues",
        r'''Generate 3 high-quality training pairs that teach debugging memory leaks and performance issues. For each pair, explain why it's effective training data.''',
        r'''<think>
Memory issues are notoriously hard to debug. Key areas:
1. Identifying memory leaks in Python/JavaScript
2. Using profiling tools to find bottlenecks
3. Understanding common memory leak patterns

Progression: recognizing symptoms -> using profiling tools -> fixing common patterns
</think>

Here are 3 training pairs for debugging memory issues:

**Pair 1 (Beginner):**
```
Q: My Python web application gets slower over time and eventually crashes with "MemoryError" after running for a few days. How do I find the memory leak?

A: A memory leak means objects are being created but never freed. Here's how to find it:

**Step 1: Confirm it's a memory leak**
```bash
# Watch memory usage over time:
watch -n 5 'ps aux | grep python'
# If RSS (resident memory) keeps growing, you have a leak
```

**Step 2: Find what's growing with tracemalloc:**
```python
import tracemalloc
tracemalloc.start()

# ... run your app for a while ...

# Take a snapshot and see what's using memory:
snapshot = tracemalloc.take_snapshot()
top = snapshot.statistics('lineno')
for stat in top[:10]:
    print(stat)
# Output shows which lines of code allocated the most memory
```

**Step 3: Common Python memory leak patterns:**

```python
# LEAK 1: Growing list/dict that's never cleared
_cache = {}
def get_data(key):
    _cache[key] = expensive_query(key)  # Cache grows forever!
    return _cache[key]
# FIX: Use functools.lru_cache(maxsize=1000) or TTL cache

# LEAK 2: Event listeners never removed
def setup():
    signal.connect(my_handler)  # Called every request = N handlers
# FIX: Connect once at startup, or disconnect in teardown

# LEAK 3: Circular references with __del__
class Node:
    def __init__(self):
        self.parent = None
        self.children = []
    def __del__(self):
        pass  # __del__ prevents garbage collection of cycles!
# FIX: Use weakref.ref() for parent references
```

**Quick diagnosis checklist:**
- [ ] Any global lists/dicts that grow without bounds?
- [ ] Any caches without size limits or TTL?
- [ ] Any event handlers registered repeatedly?
- [ ] Any circular references?
```
*Why this is effective:* Provides both the diagnostic tool (tracemalloc) and the most common leak patterns, so learners can identify leaks in their own code.

**Pair 2 (Intermediate):**
```
Q: My API endpoint is slow — it takes 3 seconds to respond. How do I find the bottleneck?

A: Don't guess — profile. Here's a systematic approach:

**Step 1: Measure, don't guess**
```python
import time

def slow_endpoint():
    t0 = time.perf_counter()
    users = get_users()          # How long?
    t1 = time.perf_counter()
    enriched = enrich_users(users)  # How long?
    t2 = time.perf_counter()
    result = serialize(enriched)    # How long?
    t3 = time.perf_counter()

    print(f"get_users: {t1-t0:.3f}s")
    print(f"enrich:    {t2-t1:.3f}s")
    print(f"serialize: {t3-t2:.3f}s")
    return result
```

**Step 2: Use cProfile for detailed breakdown:**
```python
import cProfile
cProfile.run('slow_endpoint()', sort='cumulative')
```
Output shows every function call, how many times it was called, and cumulative time.

**Step 3: Common bottleneck patterns:**

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| One DB query takes 2s | Missing index | Add index, check EXPLAIN |
| 100 DB queries, 20ms each | N+1 query problem | Use JOIN or eager loading |
| CPU at 100% during request | Expensive computation | Cache result, move to background |
| Waiting on external API | Slow third-party service | Add timeout, cache, async |
| Large JSON serialization | Too much data | Paginate, select fewer fields |

**Step 4: The N+1 query problem (most common):**
```python
# SLOW: 1 query for users + N queries for orders
users = db.query(User).all()
for user in users:
    user.orders = db.query(Order).filter_by(user_id=user.id).all()
    # This runs a separate query for EACH user!

# FAST: 2 queries total (joined)
users = db.query(User).options(joinedload(User.orders)).all()
```
```
*Why this is effective:* Teaches measurement-first debugging instead of guessing, and covers the most common web application performance issue (N+1 queries).

**Pair 3 (Advanced):**
```
Q: Our Node.js service has memory usage that grows from 200MB to 2GB over 24 hours, then crashes. We suspect a memory leak in our event processing pipeline. How do we diagnose this?

A: Node.js memory leaks require heap snapshots and careful analysis:

**Step 1: Take heap snapshots at intervals:**
```javascript
const v8 = require('v8');
const fs = require('fs');

function takeHeapSnapshot() {
    const filename = `/tmp/heap-${Date.now()}.heapsnapshot`;
    const snapshotStream = v8.writeHeapSnapshot(filename);
    console.log(`Heap snapshot written to ${filename}`);
}

// Take snapshots every hour:
setInterval(takeHeapSnapshot, 3600000);
// Also expose via admin endpoint:
app.get('/admin/heap-snapshot', (req, res) => {
    takeHeapSnapshot();
    res.send('Snapshot taken');
});
```

**Step 2: Compare snapshots in Chrome DevTools:**
1. Open Chrome DevTools -> Memory tab
2. Load two snapshots (1 hour apart)
3. Select "Comparison" view
4. Sort by "Size Delta" — the growing objects are your leak

**Step 3: Common Node.js memory leak patterns:**
```javascript
// LEAK 1: Closures capturing large objects
function processEvents(eventStream) {
    eventStream.on('data', (event) => {
        // This closure captures 'eventStream' and everything in scope
        const result = transform(event);
        // If listeners accumulate, so do closures + captured scope
    });
}
// FIX: Remove listeners when done: eventStream.removeListener()

// LEAK 2: Unbounded event emitter listeners
const emitter = new EventEmitter();
function handleRequest(req) {
    emitter.on('update', (data) => { /* ... */ });
    // Every request adds a listener that's never removed!
}
// FIX: Use emitter.once() or remove in cleanup

// LEAK 3: Global caches without eviction
const cache = new Map();
function lookup(key) {
    if (!cache.has(key)) {
        cache.set(key, expensiveComputation(key));
    }
    return cache.get(key);
}
// FIX: Use an LRU cache with max size
const LRU = require('lru-cache');
const cache = new LRU({ max: 500 });
```

**Step 4: Monitor with process.memoryUsage():**
```javascript
setInterval(() => {
    const mem = process.memoryUsage();
    console.log({
        rss: Math.round(mem.rss / 1024 / 1024) + 'MB',
        heapUsed: Math.round(mem.heapUsed / 1024 / 1024) + 'MB',
        heapTotal: Math.round(mem.heapTotal / 1024 / 1024) + 'MB',
        external: Math.round(mem.external / 1024 / 1024) + 'MB'
    });
}, 60000);
```

If `heapUsed` grows but `external` doesn't, the leak is in JavaScript objects. If `external` grows, it's in native bindings (Buffer, streams).
```
*Why this is effective:* Production memory debugging requires different tools than development debugging. This teaches the heap snapshot workflow and the specific patterns that cause leaks in event-driven systems.'''
    ),
    (
        "thinking/auto-datagen-debugging-network",
        r'''Generate 3 high-quality training pairs that teach debugging network and API issues. For each pair, explain why it's effective training data.''',
        r'''<think>
Network debugging is a distinct skill from code debugging:
1. Understanding HTTP status codes and what they actually mean
2. Using curl/Postman to isolate client vs server issues
3. Debugging timeout, DNS, and TLS issues

Progression: HTTP status codes -> isolating issues with curl -> debugging complex failures
</think>

Here are 3 training pairs for debugging network/API issues:

**Pair 1 (Beginner):**
```
Q: My frontend is calling my API and getting a CORS error. What does this mean and how do I fix it?

A: CORS (Cross-Origin Resource Sharing) is a browser security feature. It blocks your frontend from calling APIs on different domains unless the API explicitly allows it.

**Why it happens:**
```
Frontend: http://localhost:3000  (origin A)
API:      http://localhost:8000  (origin B)
Browser: "These are different origins. API, do you allow requests from origin A?"
API: (no CORS headers) -> Browser blocks the request
```

**The fix — add CORS headers on your API:**

Flask:
```python
from flask_cors import CORS
app = Flask(__name__)
CORS(app)  # Allow all origins (dev only!)

# Production — restrict to your frontend:
CORS(app, origins=["https://myapp.com"])
```

Express:
```javascript
const cors = require('cors');
app.use(cors());  // Allow all (dev only!)

// Production:
app.use(cors({ origin: 'https://myapp.com' }));
```

**Common CORS gotchas:**
1. CORS errors are BROWSER-ONLY — curl and Postman never have CORS issues
2. If curl works but the browser doesn't, it's always CORS
3. Preflight requests (OPTIONS) must also return CORS headers
4. Credentials (cookies) require `Access-Control-Allow-Credentials: true`

**Debug checklist:**
```bash
# Test with curl to confirm the API works:
curl -v http://localhost:8000/api/data

# Check CORS headers in the response:
curl -v -X OPTIONS http://localhost:8000/api/data \
  -H "Origin: http://localhost:3000" \
  -H "Access-Control-Request-Method: GET"
# Look for: Access-Control-Allow-Origin in response headers
```
```
*Why this is effective:* CORS is one of the most common and confusing errors for beginners. Teaching that it's browser-only (curl bypasses it) is the key insight.

**Pair 2 (Intermediate):**
```
Q: My API integration sometimes works and sometimes returns "Connection timed out" or "Connection refused." How do I systematically debug this?

A: "Timed out" and "Connection refused" are different errors with different causes:

**Connection refused (immediately):**
- The server is not running on that port
- A firewall is actively rejecting the connection
```bash
# Check if the port is open:
nc -zv api.example.com 443
# "Connection refused" = nothing listening on that port
```

**Connection timed out (after waiting):**
- The server exists but isn't responding
- A firewall is silently dropping packets
- Network routing issue
```bash
# Check if you can reach the server at all:
ping api.example.com
traceroute api.example.com
```

**Systematic debugging flow:**
```bash
# 1. DNS resolution — can you find the server?
nslookup api.example.com
dig api.example.com

# 2. TCP connectivity — can you connect?
nc -zv api.example.com 443
# or: telnet api.example.com 443

# 3. TLS handshake — is the certificate valid?
openssl s_client -connect api.example.com:443

# 4. HTTP request — does the API respond?
curl -v https://api.example.com/health

# 5. With your actual request — does YOUR call work?
curl -v -X POST https://api.example.com/endpoint \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}'
```

**The "sometimes works" mystery — common causes:**
| Pattern | Likely cause |
|---------|-------------|
| Fails every ~60 seconds | Connection/idle timeout |
| Fails under load | Rate limiting or server overload |
| Fails from one machine | DNS cache, network config |
| Fails for certain requests | Request size limit, specific input |
```
*Why this is effective:* Teaches the layered debugging approach (DNS -> TCP -> TLS -> HTTP -> Application) which mirrors the network stack and helps isolate which layer is failing.

**Pair 3 (Advanced):**
```
Q: Our microservice-to-microservice calls are failing intermittently with various errors: timeouts, 502 Bad Gateway, and occasional "connection reset by peer." This started after we deployed a new version of Service B. How do we debug this?

A: Intermittent failures across services require a systematic approach to identify the failing layer:

**1. Categorize the errors:**
```
- Timeout → Service B is slow to respond
- 502 Bad Gateway → Load balancer can't reach Service B
- Connection reset → Service B is crashing mid-request
```

These three errors together suggest Service B is unhealthy — it's overloaded, crashing, or both.

**2. Check Service B health directly:**
```bash
# Bypass the load balancer and hit Service B directly:
curl -v http://service-b-pod-ip:8080/health

# Check Service B metrics:
kubectl top pods -l app=service-b  # CPU/memory usage
kubectl logs -l app=service-b --tail=100  # Recent errors

# Check if pods are restarting:
kubectl get pods -l app=service-b -w  # Watch for restarts
```

**3. Check what changed in the new deployment:**
```bash
# Diff the deployment:
kubectl diff -f new-deployment.yaml

# Common causes after deployment:
# - Memory limit too low -> OOMKilled -> pod restart -> 502
# - Readiness probe failing -> removed from service -> 502
# - New code has memory leak -> slow response -> timeout
# - New dependency with connection issues -> connection reset
```

**4. Implement proper resilience in Service A:**
```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10)
)
def call_service_b(data):
    response = httpx.post(
        "http://service-b/api/process",
        json=data,
        timeout=httpx.Timeout(5.0, connect=2.0)  # Explicit timeouts
    )
    response.raise_for_status()
    return response.json()
```

**5. Add circuit breaker for cascading failure protection:**
```python
from pybreaker import CircuitBreaker

service_b_breaker = CircuitBreaker(
    fail_max=5,           # Open after 5 failures
    reset_timeout=30,     # Try again after 30 seconds
)

@service_b_breaker
def call_service_b(data):
    return httpx.post("http://service-b/api/process", json=data, timeout=5.0)
```

**Debugging summary:**
| Error | Check | Common fix |
|-------|-------|-----------|
| Timeout | Service B response time | Increase timeout, fix slow code |
| 502 | Load balancer + pod health | Fix readiness probe, increase resources |
| Connection reset | Service B crashes/restarts | Fix OOM, check logs for panics |
```
*Why this is effective:* Teaches microservice debugging as a distinct skill from monolith debugging, introducing concepts like circuit breakers and health checks that are essential for distributed systems.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
