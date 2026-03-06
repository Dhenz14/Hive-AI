"""Phase 1C: Foundation Thinking — Performance Optimization (Part 3/4)
Caching strategies, network optimization, concurrency patterns."""

PAIRS = [
    (
        "thinking/perf-cache-stampede",
        "When a popular cache key expires, 1000 concurrent requests all miss the cache simultaneously and hit the database:\n\n```python\nimport redis\nimport json\n\nr = redis.Redis()\n\ndef get_trending_products():\n    cached = r.get('trending_products')\n    if cached:\n        return json.loads(cached)\n    \n    # Cache miss — expensive query (2 seconds)\n    products = db.execute('''\n        SELECT p.*, COUNT(o.id) as order_count\n        FROM products p\n        JOIN order_items o ON p.id = o.product_id\n        WHERE o.created_at > NOW() - INTERVAL '24 hours'\n        GROUP BY p.id\n        ORDER BY order_count DESC\n        LIMIT 50\n    ''').fetchall()\n    \n    r.setex('trending_products', 300, json.dumps(products))  # 5 min TTL\n    return products\n```\n\n1000 requests × 2 second query = database dies. How to prevent this?",
        r'''<think>
Cache stampede (thundering herd). When the cache expires, all concurrent requests see the miss and all execute the expensive query simultaneously.

Solutions:
1. Lock-based: only one request regenerates, others wait
2. Probabilistic early expiration: refresh before TTL expires
3. Background refresh: never let the cache go empty
</think>

**Cache stampede (thundering herd).** All 1000 requests see the miss simultaneously and all hammer the database.

## Fix: Lock + Stale-While-Revalidate

```python
import redis
import json
import time

r = redis.Redis()
LOCK_TTL = 10  # seconds

def get_trending_products():
    cached = r.get('trending_products')
    if cached:
        data = json.loads(cached)
        # Check if within stale window (last 30 sec before expiry)
        ttl = r.ttl('trending_products')
        if ttl < 30:
            # Proactively refresh in background
            _maybe_refresh()
        return data

    # Cache miss — try to acquire regeneration lock
    return _maybe_refresh() or _wait_for_cache()

def _maybe_refresh():
    """Only ONE request regenerates. Others get stale data or wait."""
    lock_acquired = r.set(
        'lock:trending_products', '1',
        nx=True,  # Only set if doesn't exist
        ex=LOCK_TTL,
    )

    if not lock_acquired:
        return None  # Someone else is refreshing

    try:
        products = _fetch_trending_from_db()
        r.setex('trending_products', 300, json.dumps(products))
        return products
    finally:
        r.delete('lock:trending_products')

def _wait_for_cache(timeout=5):
    """Wait for another request to populate the cache."""
    for _ in range(timeout * 10):
        cached = r.get('trending_products')
        if cached:
            return json.loads(cached)
        time.sleep(0.1)
    # Fallback: fetch ourselves
    return _fetch_trending_from_db()
```

**Key patterns:**
1. **Lock** — only one request hits the DB, others wait
2. **Stale-while-revalidate** — serve old data while refreshing in background
3. **Probabilistic early refresh** — refresh at random times before expiry to avoid synchronized expiration'''
    ),
    (
        "thinking/perf-http-connection-reuse",
        "A microservice makes 500 HTTP calls per request to various internal services. Each call takes 50ms but the total is 8 seconds (not 50ms × parallelism):\n\n```python\nimport requests\n\ndef enrich_records(records):\n    enriched = []\n    for record in records:  # 500 records\n        resp = requests.get(f'http://enrichment-service/api/{record[\"id\"]}')\n        record['enrichment'] = resp.json()\n        enriched.append(record)\n    return enriched\n```",
        r'''<think>
Multiple issues:
1. Sequential calls (not parallel)
2. Each `requests.get()` creates a new TCP connection — 500 TCP handshakes
3. No connection reuse

With `requests.Session()`, connections are reused (HTTP keep-alive). Plus parallelism.
</think>

**500 sequential calls, each creating a new TCP connection** (TCP + HTTP handshake overhead per call). No parallelism.

## Fix: Session (Connection Reuse) + Parallelism

```python
import requests
from concurrent.futures import ThreadPoolExecutor

# Session reuses TCP connections (HTTP keep-alive)
session = requests.Session()
# Configure connection pool size
adapter = requests.adapters.HTTPAdapter(
    pool_connections=20,
    pool_maxsize=20,
)
session.mount('http://', adapter)

def enrich_single(record):
    resp = session.get(f'http://enrichment-service/api/{record["id"]}')
    record['enrichment'] = resp.json()
    return record

def enrich_records(records):
    with ThreadPoolExecutor(max_workers=20) as pool:
        return list(pool.map(enrich_single, records))
```

**Or batch API (best solution):**
```python
def enrich_records(records):
    ids = [r['id'] for r in records]
    # Single request for all 500 records
    resp = session.post(
        'http://enrichment-service/api/batch',
        json={'ids': ids}
    )
    enrichments = resp.json()
    for record in records:
        record['enrichment'] = enrichments.get(str(record['id']))
    return records
```

**Performance:**
| Approach | Time |
|----------|------|
| Sequential, new connections | 8s |
| Sequential, session (reuse) | 4s |
| Parallel (20 threads), session | 400ms |
| Batch API (1 request) | 80ms |'''
    ),
    (
        "thinking/perf-gzip-compression-api",
        "API responses average 2MB of JSON. Users on slow connections experience 10+ second load times:\n\n```python\n@app.route('/api/data')\ndef get_data():\n    data = get_large_dataset()  # 2MB JSON\n    return jsonify(data)\n```",
        r'''<think>
2MB uncompressed JSON over a slow connection (1Mbps) = 16 seconds. JSON compresses very well (typically 85-90% reduction). 2MB → ~300KB with gzip.
</think>

2MB JSON over a 1Mbps connection = 16 seconds. JSON is highly compressible — gzip typically achieves 85-90% reduction.

## Fix: Enable Compression

```python
from flask import Flask
from flask_compress import Compress

app = Flask(__name__)
Compress(app)  # Automatically gzips responses > 500 bytes

# Or manually with middleware:
from gzip import compress

@app.after_request
def compress_response(response):
    if (response.content_length and response.content_length > 500
            and 'gzip' in request.headers.get('Accept-Encoding', '')):
        response.data = compress(response.data, compresslevel=6)
        response.headers['Content-Encoding'] = 'gzip'
        response.headers['Content-Length'] = len(response.data)
    return response
```

**Impact:**
| | Size | Time (1 Mbps) |
|---|------|---------------|
| Uncompressed | 2 MB | 16s |
| gzip level 6 | 250 KB | 2s |
| Brotli | 200 KB | 1.6s |

**Also consider:** pagination (don't send 2MB in one response), and streaming JSON for very large responses.'''
    ),
    (
        "thinking/perf-database-connection-leak-async",
        "Our async Python service gradually runs out of database connections despite using a pool:\n\n```python\nimport asyncpg\n\npool = None\n\nasync def init_pool():\n    global pool\n    pool = await asyncpg.create_pool(dsn='postgresql://...', max_size=20)\n\nasync def get_user(user_id):\n    conn = await pool.acquire()\n    row = await conn.fetchrow('SELECT * FROM users WHERE id = $1', user_id)\n    return dict(row) if row else None\n    # Connection never released!\n```",
        r'''<think>
`pool.acquire()` checks out a connection but it's never returned. `pool.release(conn)` or `async with pool.acquire() as conn` is needed.
</think>

**`pool.acquire()` checks out a connection that's never released.** After 20 requests, the pool is exhausted.

## Fix: Use `async with` (Automatic Release)

```python
async def get_user(user_id):
    async with pool.acquire() as conn:  # Auto-released on exit
        row = await conn.fetchrow('SELECT * FROM users WHERE id = $1', user_id)
        return dict(row) if row else None
```

**Or use `pool.fetchrow()` directly (simplest):**
```python
async def get_user(user_id):
    row = await pool.fetchrow('SELECT * FROM users WHERE id = $1', user_id)
    return dict(row) if row else None
```

`pool.fetchrow()` handles acquire/release internally. **Always prefer context managers** (`async with`) for resources — they guarantee cleanup even on exceptions.'''
    ),
    (
        "thinking/perf-slow-startup-lazy-loading",
        "A CLI tool takes 5 seconds to start, even for `--help`:\n\n```python\nimport pandas as pd\nimport tensorflow as tf\nimport sklearn\nfrom transformers import pipeline\nimport click\n\n@click.group()\ndef cli():\n    pass\n\n@cli.command()\ndef analyze():\n    \"\"\"Run analysis pipeline.\"\"\"\n    df = pd.read_csv('data.csv')\n    model = pipeline('sentiment-analysis')\n    ...\n\n@cli.command()\ndef version():\n    \"\"\"Show version.\"\"\"\n    print('v1.0.0')\n\nif __name__ == '__main__':\n    cli()\n```",
        r'''<think>
All imports happen at module level. `import tensorflow` alone takes 2-3 seconds. `from transformers import pipeline` adds another 1-2 seconds. Even `--help` or `version` pays this cost.

Fix: lazy imports — only import heavy libraries when the command that needs them runs.
</think>

**All heavy imports execute at startup.** `import tensorflow` alone takes 2-3 seconds. Even `cli version` pays the full import cost.

## Fix: Lazy Imports Inside Commands

```python
import click

@click.group()
def cli():
    pass

@cli.command()
def analyze():
    """Run analysis pipeline."""
    import pandas as pd  # Only imported when 'analyze' runs
    from transformers import pipeline

    df = pd.read_csv('data.csv')
    model = pipeline('sentiment-analysis')
    ...

@cli.command()
def version():
    """Show version."""
    print('v1.0.0')  # Instant — no heavy imports

if __name__ == '__main__':
    cli()
```

**Before:** `cli version` → 5 seconds (loads TensorFlow, transformers)
**After:** `cli version` → 50ms, `cli analyze` → 5 seconds (only when needed)

**Rule:** Import heavy libraries inside the functions that use them, not at module level. This applies to CLI tools, serverless functions, and any code where not every path needs every dependency.'''
    ),
    (
        "thinking/perf-multiprocessing-cpu-bound",
        "A CPU-bound data transformation takes 60 seconds on an 8-core machine using only 1 core:\n\n```python\ndef transform_record(record):\n    # Heavy CPU computation: ~6ms per record\n    return complex_calculation(record)\n\ndef process_all(records):  # 10,000 records\n    return [transform_record(r) for r in records]\n```\n\nThreading doesn't help due to Python's GIL. What's the best parallelization strategy?",
        r'''<think>
CPU-bound work → GIL prevents threading from parallelizing. Need multiprocessing.

10,000 records × 6ms = 60 seconds single-core. With 8 cores: 60/8 = 7.5 seconds theoretical.

Use ProcessPoolExecutor for clean API. Consider chunk size for reducing IPC overhead.
</think>

**Python's GIL prevents threads from parallelizing CPU-bound work.** One core does all the work while 7 sit idle.

## Fix: `ProcessPoolExecutor`

```python
from concurrent.futures import ProcessPoolExecutor
import os

def transform_record(record):
    return complex_calculation(record)

def process_all(records):
    workers = os.cpu_count()  # 8 cores
    # chunksize reduces IPC overhead — send batches, not individual items
    chunksize = max(1, len(records) // (workers * 4))

    with ProcessPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(transform_record, records, chunksize=chunksize))
    return results
```

**Performance:**
| Approach | Cores Used | Time |
|----------|-----------|------|
| List comprehension | 1 | 60s |
| ThreadPoolExecutor | 1 (GIL) | 60s |
| ProcessPoolExecutor (8) | 8 | ~8s |

**Key:** `chunksize` parameter is critical. Without it, each of 10,000 records is pickled/unpickled individually (huge IPC overhead). With `chunksize=300`, records are sent in batches, reducing IPC to ~33 calls.

**For numerical data, consider `numpy` vectorization** — often faster than multiprocessing with zero IPC overhead.'''
    ),
    (
        "thinking/perf-redis-pipeline-batching",
        "Setting 10,000 keys in Redis takes 5 seconds due to network round trips:\n\n```python\nimport redis\n\nr = redis.Redis()\n\ndef cache_products(products):\n    for product in products:  # 10,000 products\n        r.set(f'product:{product[\"id\"]}', json.dumps(product), ex=3600)\n```",
        r'''<think>
Each `r.set()` is a network round trip (~0.5ms for localhost, more for remote). 10,000 × 0.5ms = 5 seconds.

Redis pipeline batches multiple commands into a single round trip.
</think>

**10,000 network round trips** (~0.5ms each = 5 seconds). Redis processes commands in microseconds — the bottleneck is network latency.

## Fix: Redis Pipeline

```python
def cache_products(products):
    pipe = r.pipeline()  # Buffer commands
    for product in products:
        pipe.set(f'product:{product["id"]}', json.dumps(product), ex=3600)
    pipe.execute()  # Send ALL commands in one round trip
```

**Before:** 10,000 round trips × 0.5ms = 5 seconds
**After:** 1 round trip = 50ms (100x faster)

For very large batches, chunk the pipeline (10K commands per execute call) to avoid excessive memory usage in the Redis buffer.'''
    ),
    (
        "thinking/perf-frontend-bundle-size",
        "A React app's initial bundle is 3MB, taking 15 seconds to load on 3G connections. The app has 50 routes but loads everything upfront:\n\n```javascript\nimport AdminDashboard from './pages/AdminDashboard';\nimport Analytics from './pages/Analytics';\nimport Settings from './pages/Settings';\nimport UserProfile from './pages/UserProfile';\n// ... 46 more imports\n\nfunction App() {\n    return (\n        <Router>\n            <Route path='/admin' component={AdminDashboard} />\n            <Route path='/analytics' component={Analytics} />\n            <Route path='/settings' component={Settings} />\n            <Route path='/profile' component={UserProfile} />\n            {/* ... 46 more routes */}\n        </Router>\n    );\n}\n```",
        r'''<think>
All 50 routes are imported upfront, meaning the entire app's code is in the initial bundle. Most users only visit 2-3 pages. Solution: code splitting with React.lazy + Suspense.
</think>

**All 50 pages loaded upfront.** Users visiting `/profile` download 3MB including admin dashboards they'll never see.

## Fix: Code Splitting with Lazy Loading

```javascript
import React, { Suspense, lazy } from 'react';

// Each page is loaded only when navigated to
const AdminDashboard = lazy(() => import('./pages/AdminDashboard'));
const Analytics = lazy(() => import('./pages/Analytics'));
const Settings = lazy(() => import('./pages/Settings'));
const UserProfile = lazy(() => import('./pages/UserProfile'));

function App() {
    return (
        <Router>
            <Suspense fallback={<LoadingSpinner />}>
                <Route path='/admin' component={AdminDashboard} />
                <Route path='/analytics' component={Analytics} />
                <Route path='/settings' component={Settings} />
                <Route path='/profile' component={UserProfile} />
            </Suspense>
        </Router>
    );
}
```

**Impact:**
| | Initial Bundle | First Load (3G) |
|---|---------------|-----------------|
| All routes bundled | 3 MB | 15s |
| Code-split | 200 KB | 2s |

Each route is a separate chunk, loaded on-demand. The initial bundle only contains the router and shared components. Users download code for pages they actually visit.'''
    ),
    (
        "thinking/perf-database-read-replica",
        "A read-heavy application (95% reads, 5% writes) is bottlenecked on a single database. Read queries compete with writes for the same resources:\n\n```python\n# All queries go to the same database\ndef get_user(user_id):\n    return db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()\n\ndef create_order(user_id, items):\n    db.execute('INSERT INTO orders ...', (user_id, ...))\n    db.commit()\n\ndef get_dashboard(user_id):\n    # Expensive read query that locks rows and blocks writes\n    return db.execute('''\n        SELECT ... FROM orders\n        JOIN products ON ...\n        WHERE user_id = ?\n        GROUP BY ...\n    ''', (user_id,)).fetchall()\n```",
        r'''<think>
Read-heavy workload on single DB. Reads compete with writes for CPU, I/O, and locks. Solution: read replicas. Route reads to replicas, writes to primary.
</think>

**95% of load is reads competing with writes on a single server.** Expensive dashboard queries lock rows and slow down order creation.

## Fix: Read Replica Routing

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Primary for writes
primary_engine = create_engine('postgresql://primary:5432/myapp')
PrimarySession = sessionmaker(bind=primary_engine)

# Read replicas for queries (can have multiple)
replica_engine = create_engine('postgresql://replica:5432/myapp')
ReplicaSession = sessionmaker(bind=replica_engine)

def get_write_session():
    return PrimarySession()

def get_read_session():
    return ReplicaSession()

# Reads go to replica — no contention with writes
def get_user(user_id):
    session = get_read_session()
    try:
        return session.query(User).get(user_id)
    finally:
        session.close()

# Writes go to primary
def create_order(user_id, items):
    session = get_write_session()
    try:
        session.add(Order(user_id=user_id, items=items))
        session.commit()
    finally:
        session.close()

# Heavy reads go to replica — doesn't block writes
def get_dashboard(user_id):
    session = get_read_session()
    try:
        return session.execute(dashboard_query, {'user_id': user_id}).fetchall()
    finally:
        session.close()
```

**Note:** Read replicas have slight replication lag (typically <100ms). For reads that MUST see the latest write (e.g., user just created an order, redirected to order page), route to primary:
```python
def get_order_after_create(order_id):
    return get_write_session().query(Order).get(order_id)  # Primary — guaranteed fresh
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
