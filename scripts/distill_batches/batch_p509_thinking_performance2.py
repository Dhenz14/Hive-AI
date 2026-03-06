"""Phase 1C: Foundation Thinking — Performance Optimization (Part 2/4)
Python-specific optimization, memory efficiency, algorithmic improvements."""

PAIRS = [
    (
        "thinking/perf-python-string-concatenation",
        "A log formatter builds strings by concatenation in a loop. With 100K log entries, it takes 30 seconds:\n\n```python\ndef format_logs(entries):\n    output = ''\n    for entry in entries:  # 100,000 entries\n        output += f'{entry[\"timestamp\"]} [{entry[\"level\"]}] {entry[\"message\"]}\\n'\n    return output\n```",
        r'''<think>
String concatenation in a loop is O(n²) because strings are immutable. Each `+=` creates a new string and copies all previous content. For 100K entries: 1 + 2 + 3 + ... + 100000 ≈ 5 billion character copies.

Fix: use `''.join()` or `io.StringIO` — both are O(n).
</think>

**String concatenation in a loop is O(n²).** Strings are immutable — each `+=` copies the entire string built so far. 100K iterations → ~5 billion character copies.

## Fix: `join()` Is O(n)

```python
def format_logs(entries):
    lines = [
        f'{entry["timestamp"]} [{entry["level"]}] {entry["message"]}'
        for entry in entries
    ]
    return '\n'.join(lines)
```

**Or `io.StringIO` for streaming:**
```python
import io

def format_logs(entries):
    buf = io.StringIO()
    for entry in entries:
        buf.write(f'{entry["timestamp"]} [{entry["level"]}] {entry["message"]}\n')
    return buf.getvalue()
```

**Before:** 30 seconds (O(n²) copies)
**After:** <100ms (O(n) — each character written once)'''
    ),
    (
        "thinking/perf-list-vs-generator-memory",
        "A data processing pipeline runs out of memory on large files:\n\n```python\ndef process_large_file(filepath):\n    # Read all lines into memory\n    with open(filepath) as f:\n        lines = f.readlines()  # 10GB file → 10GB in RAM\n    \n    # Filter\n    valid_lines = [line for line in lines if is_valid(line)]  # Another copy\n    \n    # Transform\n    results = [transform(line) for line in valid_lines]  # Third copy\n    \n    # Aggregate\n    total = sum(r['value'] for r in results)\n    return total\n```\n\nThe file is 10GB. This code uses 30GB+ of RAM.",
        r'''<think>
Three full copies in memory:
1. `lines` = all lines (10GB)
2. `valid_lines` = filtered subset (maybe 5GB)
3. `results` = transformed (maybe 5GB)
= ~20GB+

Fix: use generators for streaming processing. Process one line at a time.
</think>

**Three full copies of the data in memory.** The 10GB file becomes 30GB+ across `lines`, `valid_lines`, and `results`.

## Fix: Generator Pipeline — O(1) Memory

```python
def process_large_file(filepath):
    total = 0
    with open(filepath) as f:
        for line in f:  # Streams one line at a time
            if is_valid(line):
                result = transform(line)
                total += result['value']
    return total
```

**Or with composable generators:**
```python
def read_lines(filepath):
    with open(filepath) as f:
        yield from f  # One line at a time

def filter_valid(lines):
    for line in lines:
        if is_valid(line):
            yield line

def transform_lines(lines):
    for line in lines:
        yield transform(line)

def process_large_file(filepath):
    pipeline = transform_lines(filter_valid(read_lines(filepath)))
    return sum(r['value'] for r in pipeline)
```

**Memory usage:** 10GB file now uses ~1KB of RAM (one line at a time). The generators form a lazy pipeline — each line flows through all stages before the next is read.'''
    ),
    (
        "thinking/perf-dict-vs-list-lookup",
        "A permission checker is slow because it searches a list on every request:\n\n```python\n# Loaded at startup: 50,000 permission entries\nallowed_users = [\n    {'user_id': 1, 'resource': 'admin', 'action': 'read'},\n    {'user_id': 1, 'resource': 'admin', 'action': 'write'},\n    {'user_id': 2, 'resource': 'reports', 'action': 'read'},\n    # ... 50,000 entries\n]\n\ndef check_permission(user_id, resource, action):\n    for entry in allowed_users:  # O(n) scan every time!\n        if (entry['user_id'] == user_id and \n            entry['resource'] == resource and \n            entry['action'] == action):\n            return True\n    return False\n```\n\nWith 1000 requests/second, each scanning 50K entries, the server is CPU-bound.",
        r'''<think>
O(n) linear scan per request × 1000 requests/sec = 50 million comparisons/sec.

Fix: use a set or dict for O(1) lookup.
</think>

**O(n) list scan on every request.** 50K entries × 1000 requests/sec = 50M comparisons/second.

## Fix: Set for O(1) Lookup

```python
# Build lookup set at startup
_permissions = set()
for entry in allowed_users:
    _permissions.add(
        (entry['user_id'], entry['resource'], entry['action'])
    )

def check_permission(user_id, resource, action):
    return (user_id, resource, action) in _permissions  # O(1)
```

**Before:** 50,000 comparisons per request (O(n))
**After:** 1 hash lookup per request (O(1))
**Speedup:** ~50,000x per request'''
    ),
    (
        "thinking/perf-dataclass-slots",
        "A simulation creates 10 million point objects. Memory usage is 3.8GB:\n\n```python\nclass Point:\n    def __init__(self, x, y, z, label):\n        self.x = x\n        self.y = y\n        self.z = z\n        self.label = label\n\npoints = [Point(i, i*2, i*3, f'p{i}') for i in range(10_000_000)]\n```\n\nEach `Point` uses ~380 bytes due to the instance `__dict__`. How to reduce memory?",
        r'''<think>
Regular Python objects store attributes in a `__dict__` dictionary. A dict has significant overhead: hash table, pointers, resizing. For small objects with fixed attributes, this wastes most of the memory.

`__slots__` eliminates the __dict__, storing attributes in a fixed-size array. Saves ~50-60% memory per instance.
</think>

Python objects store attributes in a per-instance `__dict__` (hash table) — ~200 bytes overhead per object. For 10M objects, that's 2GB+ of dictionary overhead alone.

## Fix: `__slots__`

```python
class Point:
    __slots__ = ('x', 'y', 'z', 'label')

    def __init__(self, x, y, z, label):
        self.x = x
        self.y = y
        self.z = z
        self.label = label

points = [Point(i, i*2, i*3, f'p{i}') for i in range(10_000_000)]
```

**Or with `dataclass`:**
```python
from dataclasses import dataclass

@dataclass(slots=True)  # Python 3.10+
class Point:
    x: float
    y: float
    z: float
    label: str
```

**Memory comparison (10M objects):**
| Approach | Memory | Per Object |
|----------|--------|-----------|
| Regular class | 3.8 GB | ~380 bytes |
| `__slots__` | 1.5 GB | ~150 bytes |
| Named tuple | 1.2 GB | ~120 bytes |
| NumPy structured array | 0.3 GB | ~32 bytes |

`__slots__` removes `__dict__`, storing attributes in a compact fixed array. 60% memory reduction with zero code change to callers.'''
    ),
    (
        "thinking/perf-redundant-computation-cache",
        "A recursive Fibonacci implementation takes 30 seconds for n=40:\n\n```python\ndef fibonacci(n):\n    if n <= 1:\n        return n\n    return fibonacci(n - 1) + fibonacci(n - 2)\n\nresult = fibonacci(40)  # 30 seconds!\n```",
        r'''<think>
Naive recursive Fibonacci is O(2^n) — it recomputes the same subproblems exponentially many times. `fibonacci(40)` makes ~2^40 ≈ 1 trillion calls.

Fix: memoization (functools.lru_cache) or iterative approach.
</think>

**O(2^n) — recomputes the same values exponentially.** `fibonacci(40)` triggers ~1 trillion function calls because `fibonacci(38)` is computed twice, `fibonacci(37)` four times, etc.

## Fix: Memoization

```python
from functools import lru_cache

@lru_cache(maxsize=None)
def fibonacci(n):
    if n <= 1:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

fibonacci(40)  # Instant
```

**Or iterative (no recursion depth limit):**
```python
def fibonacci(n):
    if n <= 1:
        return n
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b
```

**Before:** O(2^n) — 30 seconds for n=40
**After:** O(n) — microseconds for n=40, works for n=100000+'''
    ),
    (
        "thinking/perf-csv-processing-chunked",
        "Processing a 5GB CSV file takes 20 minutes and uses 15GB RAM with pandas:\n\n```python\nimport pandas as pd\n\ndef process_sales_data(filepath):\n    df = pd.read_csv(filepath)  # Loads entire 5GB into memory\n    \n    # Group by region and calculate totals\n    result = df.groupby('region').agg({\n        'revenue': 'sum',\n        'orders': 'count',\n    }).reset_index()\n    \n    return result\n```",
        r'''<think>
pandas loads the entire CSV into memory. A 5GB CSV typically becomes 10-15GB in pandas due to object dtype overhead (strings stored as Python objects).

Fix: chunked reading, or use polars/duckdb for out-of-core processing.
</think>

pandas loads the entire 5GB into RAM. String columns inflate 2-3x due to Python object overhead → 15GB total.

## Fix Option 1: Chunked Processing

```python
import pandas as pd

def process_sales_data(filepath):
    totals = {}
    for chunk in pd.read_csv(filepath, chunksize=100_000):
        grouped = chunk.groupby('region').agg({
            'revenue': 'sum',
            'orders': 'count',
        })
        for region, row in grouped.iterrows():
            if region not in totals:
                totals[region] = {'revenue': 0, 'orders': 0}
            totals[region]['revenue'] += row['revenue']
            totals[region]['orders'] += row['orders']

    return pd.DataFrame.from_dict(totals, orient='index').reset_index()
```

## Fix Option 2: DuckDB (Best for Analytics)

```python
import duckdb

def process_sales_data(filepath):
    return duckdb.sql(f"""
        SELECT region, SUM(revenue) as revenue, COUNT(*) as orders
        FROM read_csv_auto('{filepath}')
        GROUP BY region
    """).df()
```

**Performance comparison (5GB CSV):**
| Method | Time | Memory |
|--------|------|--------|
| pandas (full load) | 20 min | 15 GB |
| pandas (chunked) | 5 min | 500 MB |
| DuckDB | 30 sec | 200 MB |
| Polars | 45 sec | 300 MB |

DuckDB and Polars are columnar and handle out-of-core processing natively.'''
    ),
    (
        "thinking/perf-async-io-bound",
        "An API endpoint makes 5 HTTP calls sequentially. Each takes 200ms, totaling 1 second:\n\n```python\nimport requests\n\ndef get_dashboard_data(user_id):\n    profile = requests.get(f'{USER_SERVICE}/users/{user_id}').json()\n    orders = requests.get(f'{ORDER_SERVICE}/users/{user_id}/orders').json()\n    notifications = requests.get(f'{NOTIF_SERVICE}/users/{user_id}/notifs').json()\n    recommendations = requests.get(f'{REC_SERVICE}/users/{user_id}/recs').json()\n    analytics = requests.get(f'{ANALYTICS_SERVICE}/users/{user_id}/stats').json()\n    \n    return {\n        'profile': profile,\n        'orders': orders,\n        'notifications': notifications,\n        'recommendations': recommendations,\n        'analytics': analytics,\n    }\n```",
        r'''<think>
5 sequential HTTP calls × 200ms each = 1000ms total. But they're independent — no dependency between them. Can run in parallel.
</think>

**5 independent calls run sequentially** — 200ms × 5 = 1 second. They have no dependencies and can run in parallel.

## Fix: Concurrent Requests

```python
import asyncio
import aiohttp

async def get_dashboard_data(user_id):
    async with aiohttp.ClientSession() as session:
        tasks = [
            session.get(f'{USER_SERVICE}/users/{user_id}'),
            session.get(f'{ORDER_SERVICE}/users/{user_id}/orders'),
            session.get(f'{NOTIF_SERVICE}/users/{user_id}/notifs'),
            session.get(f'{REC_SERVICE}/users/{user_id}/recs'),
            session.get(f'{ANALYTICS_SERVICE}/users/{user_id}/stats'),
        ]
        responses = await asyncio.gather(*tasks)
        profile, orders, notifs, recs, analytics = [
            await r.json() for r in responses
        ]

    return {
        'profile': profile,
        'orders': orders,
        'notifications': notifs,
        'recommendations': recs,
        'analytics': analytics,
    }
```

**Or with `concurrent.futures` (sync code):**
```python
from concurrent.futures import ThreadPoolExecutor

def get_dashboard_data(user_id):
    urls = {
        'profile': f'{USER_SERVICE}/users/{user_id}',
        'orders': f'{ORDER_SERVICE}/users/{user_id}/orders',
        'notifications': f'{NOTIF_SERVICE}/users/{user_id}/notifs',
        'recommendations': f'{REC_SERVICE}/users/{user_id}/recs',
        'analytics': f'{ANALYTICS_SERVICE}/users/{user_id}/stats',
    }

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {k: pool.submit(requests.get, url) for k, url in urls.items()}
        return {k: f.result().json() for k, f in futures.items()}
```

**Before:** 1000ms (sequential)
**After:** ~200ms (parallel — total time = slowest single call)'''
    ),
    (
        "thinking/perf-regex-compilation",
        "A log parser is slow because it compiles regex patterns on every line:\n\n```python\ndef parse_log_file(filepath):\n    results = []\n    with open(filepath) as f:\n        for line in f:  # 1,000,000 lines\n            # These compile a new regex object EVERY iteration\n            if re.match(r'^ERROR \\[(\\d{4}-\\d{2}-\\d{2})\\] (.+)$', line):\n                match = re.match(r'^ERROR \\[(\\d{4}-\\d{2}-\\d{2})\\] (.+)$', line)\n                results.append((match.group(1), match.group(2)))\n            elif re.match(r'^WARN \\[(\\d{4}-\\d{2}-\\d{2})\\] (.+)$', line):\n                match = re.match(r'^WARN \\[(\\d{4}-\\d{2}-\\d{2})\\] (.+)$', line)\n                results.append((match.group(1), match.group(2)))\n    return results\n```",
        r'''<think>
Two problems:
1. `re.match()` compiles the pattern every call (even though Python caches the last few, the code alternates between patterns, thrashing the cache)
2. Each pattern is matched TWICE — once to check, once to capture groups
</think>

**Two issues:** regex patterns compiled per call (cache thrashing with multiple patterns), and each pattern matched twice (check + capture).

## Fix: Pre-Compile + Single Match

```python
import re

ERROR_RE = re.compile(r'^ERROR \[(\d{4}-\d{2}-\d{2})\] (.+)$')
WARN_RE = re.compile(r'^WARN \[(\d{4}-\d{2}-\d{2})\] (.+)$')

def parse_log_file(filepath):
    results = []
    with open(filepath) as f:
        for line in f:
            match = ERROR_RE.match(line) or WARN_RE.match(line)
            if match:
                results.append((match.group(1), match.group(2)))
    return results
```

**Even faster — single pattern:**
```python
LOG_RE = re.compile(r'^(ERROR|WARN) \[(\d{4}-\d{2}-\d{2})\] (.+)$')

def parse_log_file(filepath):
    results = []
    with open(filepath) as f:
        for line in f:
            match = LOG_RE.match(line)
            if match:
                results.append((match.group(2), match.group(3)))
    return results
```

Pre-compiled regex: ~5x faster. Single pattern instead of two: another 2x. Combined: ~10x speedup.'''
    ),
    (
        "thinking/perf-json-serialization-bottleneck",
        "An API endpoint takes 2 seconds to serialize 50,000 records to JSON:\n\n```python\nimport json\nfrom datetime import datetime, date\nfrom decimal import Decimal\n\nclass CustomEncoder(json.JSONEncoder):\n    def default(self, obj):\n        if isinstance(obj, (datetime, date)):\n            return obj.isoformat()\n        if isinstance(obj, Decimal):\n            return float(obj)\n        return super().default(obj)\n\n@app.route('/api/export')\ndef export_data():\n    records = get_all_records()  # 50,000 dicts\n    return json.dumps(records, cls=CustomEncoder)\n```",
        r'''<think>
stdlib `json` is pure Python and slow for large payloads. The custom encoder adds overhead — `default()` is called for every non-serializable object, which means isinstance checks for every datetime/Decimal in 50K records.

Fix: use `orjson` (Rust-based, 10-20x faster) or pre-convert types.
</think>

`json.dumps` with a custom encoder is slow — the `default()` method is called per non-serializable object with isinstance checks. stdlib `json` is pure Python.

## Fix: Use `orjson` (10-20x Faster)

```python
import orjson

@app.route('/api/export')
def export_data():
    records = get_all_records()
    # orjson natively handles datetime, date, Decimal, UUID, numpy
    return orjson.dumps(records), 200, {'Content-Type': 'application/json'}
```

**If you can't use orjson, pre-convert in the query:**
```python
def get_all_records():
    rows = db.execute('SELECT id, name, created_at::text as created_at, '
                      'amount::float as amount FROM records')
    return [dict(r) for r in rows]
    # All values are now native JSON types — no custom encoder needed
```

**Benchmarks (50K records):**
| Library | Time |
|---------|------|
| json + CustomEncoder | 2000ms |
| json (pre-converted) | 800ms |
| orjson | 100ms |
| msgpack (binary) | 50ms |'''
    ),
    (
        "thinking/perf-image-resize-pillow",
        "A thumbnail generation service is CPU-bound, processing only 5 images/second:\n\n```python\nfrom PIL import Image\n\ndef create_thumbnail(input_path, output_path, size=(200, 200)):\n    img = Image.open(input_path)\n    img = img.resize(size, Image.LANCZOS)  # High quality but slow\n    img.save(output_path, 'JPEG', quality=85)\n```\n\nEach input image is 4000x3000 (12 megapixels). How to speed this up for batch processing?",
        r'''<think>
Several optimizations:
1. Use `img.thumbnail()` instead of `resize()` — it maintains aspect ratio and is optimized
2. Use `Image.BILINEAR` instead of `LANCZOS` — faster, quality difference is negligible for thumbnails
3. Use `img.draft()` to tell the JPEG decoder to only decode at the needed resolution
4. Process in parallel using multiprocessing (CPU-bound, so threads won't help with GIL)
5. Or use libvips (pillow-simd) which is 5-10x faster than Pillow
</think>

Several optimizations, each stacking:

## Fix: Multi-Level Optimization

```python
from PIL import Image
from concurrent.futures import ProcessPoolExecutor
import os

def create_thumbnail(input_path, output_path, size=(200, 200)):
    img = Image.open(input_path)

    # Optimization 1: draft() — JPEG decoder skips unnecessary pixels
    # Decodes at 1/8 resolution (500x375 instead of 4000x3000)
    img.draft('RGB', (size[0] * 4, size[1] * 4))

    # Optimization 2: thumbnail() — maintains aspect ratio, optimized path
    img.thumbnail(size, Image.BILINEAR)  # BILINEAR is 3x faster than LANCZOS

    img.save(output_path, 'JPEG', quality=85, optimize=False)

def batch_thumbnails(image_pairs, workers=None):
    """Process images in parallel using multiple CPU cores."""
    workers = workers or os.cpu_count()
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(create_thumbnail, inp, out)
            for inp, out in image_pairs
        ]
        for f in futures:
            f.result()  # Raise any exceptions
```

**Speedup breakdown:**
| Optimization | Speed |
|-------------|-------|
| Original (LANCZOS, full decode) | 5 img/s |
| + draft() (skip decode) | 15 img/s |
| + BILINEAR (faster resample) | 25 img/s |
| + ProcessPoolExecutor (8 cores) | 150 img/s |

For even more speed, use **`pillow-simd`** (SIMD-optimized Pillow fork) or **`libvips`** via `pyvips` — typically 5-10x faster than standard Pillow.'''
    ),
    (
        "thinking/perf-memory-profiling-leak",
        "A long-running service's memory grows from 200MB to 4GB over 24 hours. How to find the leak:\n\n```python\n# We suspect the leak is somewhere in request handling\n@app.route('/api/process', methods=['POST'])\ndef process_data():\n    data = request.json\n    result = heavy_computation(data)\n    cache_result(data['key'], result)\n    return jsonify(result)\n```\n\nDescribe the systematic approach to finding and fixing the memory leak.",
        r'''<think>
Systematic memory leak debugging approach:

1. Confirm the leak with monitoring (RSS over time)
2. Use tracemalloc to identify which code allocates the most memory
3. Use objgraph to find what's keeping objects alive
4. Common causes: caches without limits, event handler accumulation, global lists, closures capturing references
</think>

## Systematic Memory Leak Investigation

### Step 1: Confirm and Measure
```python
import tracemalloc
import psutil
import os

tracemalloc.start(25)  # Track 25 frames deep

@app.route('/debug/memory')
def memory_stats():
    process = psutil.Process(os.getpid())
    snapshot = tracemalloc.take_snapshot()
    top = snapshot.statistics('lineno')[:20]

    return jsonify({
        'rss_mb': process.memory_info().rss / 1024 / 1024,
        'top_allocations': [
            {'file': str(s.traceback), 'size_mb': s.size / 1024 / 1024}
            for s in top
        ],
    })
```

### Step 2: Compare Snapshots
```python
_baseline = None

@app.route('/debug/memory/snapshot')
def take_snapshot():
    global _baseline
    current = tracemalloc.take_snapshot()
    if _baseline:
        diff = current.compare_to(_baseline, 'lineno')
        result = [{'file': str(s.traceback), 'size_diff_mb': s.size_diff / 1024 / 1024}
                  for s in diff[:20]]
    else:
        result = 'Baseline set'
    _baseline = current
    return jsonify(result)
```

### Step 3: Find Reference Chains
```python
import objgraph

@app.route('/debug/memory/growth')
def show_growth():
    objgraph.show_growth(limit=20)  # Prints to stderr
    # For specific leak: find what's holding references
    # objgraph.show_backrefs(objgraph.by_type('MyClass')[:5], filename='refs.png')
    return jsonify(message='Check server logs')
```

### Common Culprits
```python
# 1. Unbounded cache — FIX: add maxsize
@lru_cache(maxsize=10000)  # NOT maxsize=None!
def heavy_computation(data):
    ...

# 2. Global list/dict growing — FIX: bound it
results_cache = {}  # Grows forever!
# FIX: use cachetools.TTLCache
from cachetools import TTLCache
results_cache = TTLCache(maxsize=1000, ttl=3600)

# 3. Event handlers / callbacks accumulating — FIX: weakref
import weakref
callbacks = weakref.WeakSet()
```

**The pattern:** measure (tracemalloc) → identify (compare snapshots) → trace (objgraph) → fix (bound caches, weakrefs, cleanup).'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
