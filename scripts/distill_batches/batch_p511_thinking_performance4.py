"""Phase 1C: Foundation Thinking — Performance Optimization (Part 4/4)
Algorithm optimization, profiling, system-level performance."""

PAIRS = [
    (
        "thinking/perf-algorithm-quadratic-dedup",
        "A deduplication function takes 45 seconds on 100,000 records:\n\n```python\ndef deduplicate(records):\n    unique = []\n    for record in records:  # 100,000 records\n        is_dup = False\n        for existing in unique:  # Growing list, up to 100,000\n            if record['email'] == existing['email']:\n                is_dup = True\n                break\n        if not is_dup:\n            unique.append(record)\n    return unique\n```",
        r'''<think>
O(n²) — for each of 100K records, linear scan through the unique list. 100K² = 10 billion comparisons.

Fix: use a set for O(1) lookup.
</think>

**O(n²) — nested loop checking every record against every unique record.** 100K² = 10 billion comparisons.

## Fix: Set-Based O(n) Deduplication

```python
def deduplicate(records):
    seen = set()
    unique = []
    for record in records:
        key = record['email']
        if key not in seen:  # O(1) set lookup
            seen.add(key)
            unique.append(record)
    return unique
```

**Before:** O(n²) — 45 seconds
**After:** O(n) — 50ms (900x faster)

For composite keys: `key = (record['email'], record['phone'])`. The set does O(1) hash lookups instead of O(n) linear scans.'''
    ),
    (
        "thinking/perf-profiling-strategy",
        "An API endpoint is slow (3 seconds) but we don't know where the time is spent. The code calls multiple functions:\n\n```python\n@app.route('/api/report')\ndef generate_report():\n    data = fetch_data()          # DB queries\n    processed = process(data)     # CPU computation\n    enriched = enrich(processed)  # External API calls\n    formatted = format_output(enriched)  # String formatting\n    return jsonify(formatted)\n```\n\nDescribe the systematic profiling approach to find the bottleneck.",
        r'''<think>
Step-by-step profiling approach:
1. First, timing each section to identify the bottleneck
2. Then deep-dive into the slow section
3. Use the right profiler for the type of bottleneck (CPU vs I/O)
</think>

## Step 1: Coarse Timing to Find the Bottleneck

```python
import time

@app.route('/api/report')
def generate_report():
    t0 = time.perf_counter()

    data = fetch_data()
    t1 = time.perf_counter()

    processed = process(data)
    t2 = time.perf_counter()

    enriched = enrich(processed)
    t3 = time.perf_counter()

    formatted = format_output(enriched)
    t4 = time.perf_counter()

    app.logger.info(
        f"fetch={t1-t0:.3f}s process={t2-t1:.3f}s "
        f"enrich={t3-t2:.3f}s format={t4-t3:.3f}s total={t4-t0:.3f}s"
    )
    return jsonify(formatted)

# Output: fetch=0.2s process=0.1s enrich=2.5s format=0.2s total=3.0s
# → enrich() is the bottleneck
```

## Step 2: Deep-Dive the Bottleneck

**For I/O-bound code (enrich = external API calls):**
```python
# Check: how many API calls? How long each?
# Are they sequential? Can they be parallelized?
import cProfile
cProfile.run('enrich(processed)', sort='cumulative')
```

**For CPU-bound code:**
```python
# Line profiler — shows time per line
# pip install line-profiler
@profile  # Add decorator, run with: kernprof -l -v script.py
def process(data):
    ...
```

**For memory issues:**
```python
# pip install memory-profiler
@profile  # Run with: python -m memory_profiler script.py
def fetch_data():
    ...
```

## Step 3: Continuous Monitoring

```python
import functools
import time

def timed(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed = time.perf_counter() - start
        if elapsed > 0.5:  # Log slow calls
            app.logger.warning(f'{func.__name__} took {elapsed:.2f}s')
        return result
    return wrapper

@timed
def enrich(processed):
    ...
```

**The pattern:** coarse timing first → identify bottleneck → right profiler for the type → fix → verify with timing.'''
    ),
    (
        "thinking/perf-api-response-streaming",
        "An endpoint returns 10MB of JSON. Users see a blank screen for 8 seconds while the entire response is buffered:\n\n```python\n@app.route('/api/export')\ndef export():\n    records = db.execute('SELECT * FROM events LIMIT 500000').fetchall()\n    data = [dict(r) for r in records]  # Convert all 500K rows\n    return jsonify(data)  # Serialize entire response, then send\n```",
        r'''<think>
The entire response is built in memory before sending the first byte. The user waits for: DB query + conversion + JSON serialization + transfer.

Fix: streaming response. Start sending data as soon as the first records are available.
</think>

**The entire 10MB response is buffered before the first byte is sent.** User sees nothing for 8 seconds, then everything at once.

## Fix: Streaming JSON Response

```python
import json
from flask import Response

@app.route('/api/export')
def export():
    def generate():
        yield '['
        first = True
        for row in db.execute('SELECT * FROM events LIMIT 500000'):
            if not first:
                yield ','
            yield json.dumps(dict(row))
            first = False
        yield ']'

    return Response(generate(), mimetype='application/json')
```

**Benefits:**
1. **Time to first byte:** ~50ms (first record sent immediately)
2. **Memory:** O(1) — one row in memory at a time, not 500K
3. **User experience:** data starts appearing immediately instead of blank screen for 8 seconds

**For CSV exports (even better — no JSON overhead):**
```python
@app.route('/api/export.csv')
def export_csv():
    def generate():
        yield 'id,name,timestamp,value\n'
        for row in db.execute('SELECT * FROM events LIMIT 500000'):
            yield f'{row.id},{row.name},{row.timestamp},{row.value}\n'

    return Response(generate(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment; filename=export.csv'})
```'''
    ),
    (
        "thinking/perf-websocket-vs-polling",
        "A dashboard polls the server every second for real-time updates. With 5000 connected users, that's 5000 requests/second:\n\n```javascript\n// Client — polls every second\nsetInterval(async () => {\n    const resp = await fetch('/api/dashboard/updates');\n    const data = await resp.json();\n    if (data.updated) {\n        updateDashboard(data);\n    }\n}, 1000);\n```\n\n```python\n# Server — checks for updates\n@app.route('/api/dashboard/updates')\ndef check_updates():\n    # Returns whether anything changed since last check\n    updates = get_pending_updates(current_user.id)\n    return jsonify(updates)\n```\n\n90% of responses are `{\"updated\": false}` — wasted requests.",
        r'''<think>
Polling: 5000 users × 1 req/sec = 5000 req/sec, 90% wasted. Each request has HTTP overhead (headers, TCP, etc.).

Fix: WebSockets for server-push. Only send data when something actually changes.
</think>

**5000 req/sec, 90% returning "no updates."** Each poll has ~1KB HTTP overhead (headers, connection handling).

## Fix: WebSocket (Server Push)

```python
# Server — only sends when there's actually an update
from flask_socketio import SocketIO, emit

socketio = SocketIO(app)

@socketio.on('connect')
def handle_connect():
    join_room(f'user_{current_user.id}')

# When data changes, push to specific user
def notify_user_update(user_id, data):
    socketio.emit('dashboard_update', data, room=f'user_{user_id}')
```

```javascript
// Client — receives updates instantly, no polling
const socket = io();

socket.on('dashboard_update', (data) => {
    updateDashboard(data);
});
```

**Comparison:**
| | Polling (1s) | WebSocket |
|---|-------------|-----------|
| Requests/sec (5K users) | 5,000 | 0 (idle) |
| Latency to see update | 0-1000ms | <50ms |
| Wasted bandwidth | 90% | 0% |
| Server CPU | High (handling empty requests) | Minimal |

**For SSE (simpler alternative when data only flows server→client):**
```python
@app.route('/api/dashboard/stream')
def stream():
    def event_stream():
        while True:
            update = wait_for_update(current_user.id)  # Blocks until data available
            yield f'data: {json.dumps(update)}\n\n'
    return Response(event_stream(), mimetype='text/event-stream')
```'''
    ),
    (
        "thinking/perf-dns-prefetch-ttl",
        "Our microservice calls 5 internal services. Under high load, DNS resolution adds 20-50ms latency per request:\n\n```python\nimport requests\n\n# Each request does a DNS lookup\ndef call_user_service(user_id):\n    return requests.get(f'http://user-service.internal/users/{user_id}')\n\ndef call_order_service(order_id):\n    return requests.get(f'http://order-service.internal/orders/{order_id}')\n```",
        r'''<think>
Each HTTP request resolves the hostname via DNS. Under high load, DNS adds 20-50ms per resolution. System DNS cache helps but has limited size and TTL.

Fix: application-level DNS caching, or resolve once and reuse the IP with `requests.Session` and connection pooling.
</think>

**DNS resolution on every request adds 20-50ms.** Under high load, the system DNS cache gets thrashed.

## Fix: Connection Session + DNS Caching

```python
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.connection import create_connection
import socket

# Option 1: Session with connection pooling (reuses TCP connections, avoids most DNS)
session = requests.Session()
adapter = HTTPAdapter(
    pool_connections=10,  # Keep connections to 10 hosts
    pool_maxsize=20,      # 20 connections per host
    max_retries=3,
)
session.mount('http://', adapter)

# All calls reuse TCP connections — DNS only on first call per host
def call_user_service(user_id):
    return session.get(f'http://user-service.internal/users/{user_id}')

# Option 2: Application-level DNS cache for absolute minimum latency
_dns_cache = {}

def cached_getaddrinfo(host, port, *args, **kwargs):
    key = (host, port)
    if key not in _dns_cache:
        _dns_cache[key] = socket.getaddrinfo(host, port, *args, **kwargs)
    return _dns_cache[key]

# Monkey-patch (use carefully, or implement as a custom urllib3 resolver)
socket.getaddrinfo = cached_getaddrinfo
```

**Best approach:** `requests.Session` with connection pooling avoids DNS entirely for subsequent requests to the same host (TCP connections are reused). No DNS = no latency.'''
    ),
    (
        "thinking/perf-hot-key-sharding",
        "A Redis cache has one key accessed 100x more than others. This 'hot key' saturates a single Redis node:\n\n```python\ndef get_homepage_data():\n    data = redis.get('homepage:featured')  # Hit 10,000 times/sec\n    if not data:\n        data = compute_homepage()\n        redis.setex('homepage:featured', 60, data)\n    return data\n```\n\nWith Redis Cluster, this single key always routes to the same node, creating a hotspot.",
        r'''<think>
In Redis Cluster, keys are assigned to slots by hash. One key = one slot = one node. A hot key creates an asymmetric load.

Solutions:
1. Local in-process cache (L1) — avoids Redis entirely for hot keys
2. Key sharding — split hot key into N replicas, read from random one
3. Read-through cache with broadcast invalidation
</think>

**One key, one node.** `homepage:featured` always routes to the same Redis Cluster node, which becomes the bottleneck while other nodes are idle.

## Fix: Local Cache + Key Sharding

```python
import random
from cachetools import TTLCache

# L1: In-process cache — no network at all for hot keys
_local_cache = TTLCache(maxsize=100, ttl=5)  # 5-second local TTL

NUM_SHARDS = 8  # Spread hot key across 8 Redis keys

def get_homepage_data():
    # L1: Check local cache first (zero latency)
    if 'homepage' in _local_cache:
        return _local_cache['homepage']

    # L2: Read from random shard (distributes load across Redis nodes)
    shard = random.randint(0, NUM_SHARDS - 1)
    data = redis.get(f'homepage:featured:{shard}')

    if not data:
        data = compute_homepage()
        # Write to ALL shards
        pipe = redis.pipeline()
        for i in range(NUM_SHARDS):
            pipe.setex(f'homepage:featured:{i}', 60, data)
        pipe.execute()

    _local_cache['homepage'] = data  # Populate L1
    return data
```

**Load distribution:**
| Approach | Load per node |
|----------|--------------|
| Single key | 10,000 req/s (1 node) |
| 8 shards | 1,250 req/s per node |
| + Local cache (5s TTL) | ~2 req/s per node (99.98% L1 hit) |

The local cache eliminates nearly all Redis traffic for hot keys.'''
    ),
    (
        "thinking/perf-sql-window-function",
        "A Python script fetches all orders, then calculates running totals and rankings in Python. It takes 30 seconds:\n\n```python\ndef get_customer_report(customer_id):\n    orders = db.execute(\n        'SELECT * FROM orders WHERE customer_id = ? ORDER BY created_at',\n        (customer_id,)\n    ).fetchall()  # 50,000 orders\n    \n    # Calculate running total in Python\n    running_total = 0\n    results = []\n    for i, order in enumerate(orders):\n        running_total += order['total']\n        results.append({\n            **dict(order),\n            'running_total': running_total,\n            'rank': i + 1,\n        })\n    \n    return results\n```",
        r"""<think>
The calculation is done in Python after fetching all 50K rows. SQL window functions can do this much more efficiently in the database.
</think>

**Fetching 50K rows to Python for simple calculations the database can do natively.**

## Fix: SQL Window Functions

```sql
SELECT
    *,
    SUM(total) OVER (ORDER BY created_at) as running_total,
    ROW_NUMBER() OVER (ORDER BY created_at) as rank
FROM orders
WHERE customer_id = ?
ORDER BY created_at;
```

```python
def get_customer_report(customer_id):
    return db.execute('''
        SELECT
            *,
            SUM(total) OVER (ORDER BY created_at) as running_total,
            ROW_NUMBER() OVER (ORDER BY created_at) as rank
        FROM orders
        WHERE customer_id = ?
        ORDER BY created_at
    ''', (customer_id,)).fetchall()
```

**Before:** Fetch 50K rows + Python loop = 30 seconds
**After:** Single query with window functions = <500ms

**Common window functions:**
- `SUM() OVER (ORDER BY ...)` — running total
- `ROW_NUMBER() OVER (ORDER BY ...)` — sequential ranking
- `RANK() / DENSE_RANK()` — ranking with ties
- `LAG() / LEAD()` — access previous/next row
- `FIRST_VALUE() / LAST_VALUE()` — first/last in window"""
    ),
    (
        "thinking/perf-bloom-filter-existence-check",
        "Before querying the database for user existence, we want a fast 'definitely not exists' check to avoid unnecessary DB hits:\n\n```python\n# Current: every username check hits the DB\ndef is_username_taken(username):\n    return db.execute(\n        'SELECT 1 FROM users WHERE username = ?', (username,)\n    ).fetchone() is not None\n\n# Called during registration: user types, we check in real-time\n# 100 checks/second, but 95% of usernames are NOT taken\n```",
        r'''<think>
95% of checks return false (not taken). A Bloom filter can eliminate those DB queries entirely. Bloom filters have zero false negatives (if it says "not exists", it's definitely true) but small false positive rate (sometimes says "might exist" when it doesn't).
</think>

95% of usernames are available. A **Bloom filter** can eliminate those DB queries with zero false negatives.

## Fix: Bloom Filter as Fast Pre-Check

```python
from pybloom_live import BloomFilter

# Initialize with all existing usernames (at startup)
username_bloom = BloomFilter(capacity=10_000_000, error_rate=0.01)

def load_bloom():
    for row in db.execute('SELECT username FROM users'):
        username_bloom.add(row['username'])

def is_username_taken(username):
    # Bloom filter: "definitely not in set" or "probably in set"
    if username not in username_bloom:
        return False  # Guaranteed not taken — skip DB query

    # Might be a false positive (~1%) — verify with DB
    return db.execute(
        'SELECT 1 FROM users WHERE username = ?', (username,)
    ).fetchone() is not None

def register_user(username, ...):
    if is_username_taken(username):
        raise ValueError('Username taken')
    # Create user...
    username_bloom.add(username)  # Add to bloom filter
```

**Impact:**
| | DB Queries/sec | Latency |
|---|---------------|---------|
| Direct DB check | 100/sec | ~5ms |
| Bloom filter pre-check | 5/sec (only positives) | 0.01ms (95% of checks) |

**Bloom filter properties:**
- False negative rate: **0%** ("not in filter" = definitely not in DB)
- False positive rate: ~1% (configurable) — these still hit the DB
- Memory: ~10MB for 10M entries at 1% FP rate
- Lookup time: O(k) where k = number of hash functions (~7), essentially O(1)'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
