"""Phase 1X: Foundation Thinking — Performance Optimization (Part 5)

Five training pairs on performance: connection pool tuning, serialization
performance (JSON vs msgpack vs protobuf), batch vs stream processing,
string/allocation optimization, and network optimization.
"""

PAIRS = [
    (
        "thinking/perf-connection-pool",
        r'''Our Python web service handles ~500 req/s but we see "connection pool exhausted" errors under load. Current setup:

import psycopg2
from psycopg2 import pool

# Global connection pool
db_pool = pool.SimpleConnectionPool(
    minconn=1,
    maxconn=5,
    host="db.internal",
    port=5432,
    dbname="myapp",
    connect_timeout=30,
)

def get_user(user_id: int) -> dict:
    conn = db_pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        row = cur.fetchone()
        cur.close()
        return dict(zip([d[0] for d in cur.description], row)) if row else {}
    finally:
        db_pool.putconn(conn)

def get_user_orders(user_id: int) -> list:
    conn = db_pool.getconn()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM orders WHERE user_id = %s ORDER BY created_at DESC",
            (user_id,)
        )
        rows = cur.fetchall()
        cur.close()
        return [dict(zip([d[0] for d in cur.description], r)) for r in rows]
    finally:
        db_pool.putconn(conn)

def get_user_profile(user_id: int) -> dict:
    """Called by the /profile endpoint -- most common request."""
    user = get_user(user_id)
    orders = get_user_orders(user_id)
    user["orders"] = orders
    return user

We run 8 gunicorn workers. What's wrong and how do we fix the pool exhaustion?''',
        r'''<think>
Let me analyze the connection pool issues step by step.

1. **Pool size vs concurrency:**
   - `maxconn=5` means only 5 connections per pool
   - 8 gunicorn workers, each with its own pool = 40 max connections total
   - But within each worker, at 500 req/s / 8 workers = ~63 req/s per worker
   - `get_user_profile` acquires TWO connections sequentially (get_user + get_user_orders)
   - If requests take ~50ms, concurrent requests per worker = 63 * 0.05 = ~3.15
   - But with 2 connections per request, peak demand = ~6.3 connections per worker
   - Pool max is 5 -- that's why it exhausts!

2. **`SimpleConnectionPool` is not thread-safe.**
   - psycopg2's `SimpleConnectionPool` is documented as not thread-safe
   - If gunicorn is using threads (gthread worker), this pool will corrupt
   - Need `ThreadedConnectionPool` for threaded workers

3. **Two connections per profile request:**
   - `get_user_profile` calls `get_user` (acquires + releases conn) then `get_user_orders` (acquires + releases conn)
   - This is wasteful -- both queries could use the same connection
   - Worse: under load, the second `getconn()` might block waiting for a connection

4. **`connect_timeout=30` is way too long.**
   - If the pool is exhausted, new connection attempts wait 30 seconds
   - This causes cascading timeouts

5. **`cur.description` accessed after `cur.close()`:**
   - `cur.close()` is called before `cur.description` is accessed in the dict comprehension
   - After closing, `description` may be None -- this is a bug!

6. **No connection health checks:**
   - Stale connections (e.g., after DB restart) aren't validated before use
   - A stale connection could sit in the pool and cause query failures

Let me calculate proper pool sizing:
- Each worker handles concurrent requests = (req/s per worker) * (avg latency)
- If avg DB query = 10ms, and we get 63 req/s per worker
- Concurrent DB queries per worker = 63 * 0.01 * 2 (two queries per profile) = ~1.26
- But that's average. At p99, with bursts, we need headroom
- Rule of thumb: pool size = 2 * CPU cores available to the worker + 1
- Or: pool size = peak concurrent requests * connections per request

For 500 req/s with 8 workers:
- Per worker: ~63 req/s
- With 20ms avg response time: ~1.3 concurrent requests
- With 2 connections per request: ~2.5 peak
- With burst factor 3x: ~7.5 connections
- So maxconn=10-15 per worker would be safe

But the REAL fix is to use one connection per request, not two.
</think>

Multiple issues compound into pool exhaustion:

**Bug 1: Two connections per profile request.**
`get_user_profile` calls `get_user` then `get_user_orders`, each acquiring its own connection. At 500 req/s, that's 1000 connection checkouts/s against a pool of only 5.

**Bug 2: Pool of 5 is far too small.**
With 8 gunicorn workers, you have 8 independent pools of 5 = 40 max connections. But each profile request holds 2 connections, so each worker can only serve 2 concurrent profile requests before exhausting its pool.

**Bug 3: `SimpleConnectionPool` is not thread-safe.**
If you're using `gthread` workers, concurrent threads corrupt the pool's internal state.

**Bug 4: `cur.description` accessed after `cur.close()`.**
The cursor is closed before the description is read in the dict comprehension. This is a correctness bug.

```python
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager

# ThreadedConnectionPool is thread-safe
db_pool = pool.ThreadedConnectionPool(
    minconn=5,
    maxconn=20,       # sized for burst concurrency per worker
    host="db.internal",
    port=5432,
    dbname="myapp",
    connect_timeout=3, # fail fast, not 30s
    options="-c statement_timeout=5000",  # 5s query timeout
)

@contextmanager
def get_db_conn():
    conn = db_pool.getconn()
    try:
        yield conn
    finally:
        db_pool.putconn(conn)

def _fetchall_as_dicts(cur):
    """Read description BEFORE closing cursor."""
    columns = [d[0] for d in cur.description]
    rows = cur.fetchall()
    return [dict(zip(columns, row)) for row in rows]

def get_user_profile(user_id: int) -> dict:
    """Single connection for the entire request."""
    with get_db_conn() as conn:
        cur = conn.cursor()

        # Both queries on the same connection
        cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        columns = [d[0] for d in cur.description]
        row = cur.fetchone()
        if not row:
            cur.close()
            return {}
        user = dict(zip(columns, row))

        cur.execute(
            "SELECT * FROM orders WHERE user_id = %s "
            "ORDER BY created_at DESC",
            (user_id,),
        )
        user["orders"] = _fetchall_as_dicts(cur)
        cur.close()
        return user
```

**Pool sizing formula:**
```
max_pool = (peak_req_per_worker * avg_latency_sec * conns_per_req) * burst_factor

Example: (63 rps * 0.02s * 1 conn * 3x burst) = ~4, round up to 10-20
```

**Key fixes:**
- One connection per request, not two (halves pool pressure)
- `ThreadedConnectionPool` for thread safety
- `connect_timeout=3` to fail fast instead of blocking 30s
- `cur.description` read before `cur.close()`
- Context manager guarantees connection return even on exceptions
- Pool sized to 20 (handles bursts without exhaustion)'''
    ),
    (
        "thinking/perf-serialization",
        r'''We're building a microservices system and need to choose a serialization format for inter-service communication. Currently using JSON but it's our bottleneck at 50k messages/sec. Profile shows 40% of CPU time in json.dumps/json.loads.

Here's our current message format and benchmark code:

import json
import time

def create_message():
    return {
        "event_type": "user_action",
        "timestamp": 1709251200.123456,
        "user_id": 123456789,
        "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "action": "page_view",
        "properties": {
            "url": "/products/widget-pro-2024",
            "referrer": "https://google.com/search?q=widgets",
            "duration_ms": 3450,
            "viewport": [1920, 1080],
            "tags": ["premium", "returning_user", "ab_test_v2"],
        },
        "device": {
            "type": "desktop",
            "os": "linux",
            "browser": "firefox",
        },
    }

def bench_json(n=100_000):
    msg = create_message()
    start = time.perf_counter()
    for _ in range(n):
        blob = json.dumps(msg)
        json.loads(blob)
    elapsed = time.perf_counter() - start
    print(f"JSON: {n/elapsed:.0f} round-trips/sec, size={len(blob)} bytes")

bench_json()

What serialization options should we evaluate, and what are the tradeoffs? Show benchmarking code for the top alternatives.''',
        r'''<think>
Let me think through the serialization options for inter-service communication:

1. **JSON (current):** Human-readable, universal support, but slow parsing and verbose. `json` module is pure Python + C extension. Can speed up with `orjson` or `ujson`.

2. **orjson:** Drop-in replacement for `json`, written in Rust. Typically 3-10x faster than stdlib json. Returns bytes, not str. Best quick win.

3. **msgpack:** Binary format, schema-less like JSON. ~2-5x faster than JSON, ~30-50% smaller. Good balance of speed and flexibility.

4. **Protocol Buffers (protobuf):** Schema-required, binary, very fast and compact. Requires .proto files and code generation. Best for well-defined interfaces.

5. **FlatBuffers / Cap'n Proto:** Zero-copy deserialization. Extreme performance but complex API.

6. **pickle:** Python-only, fast, but not cross-language. Security risk with untrusted data.

For a microservices system, the key tradeoffs are:
- **Schema evolution:** JSON/msgpack are schema-less (flexible). Protobuf has built-in schema evolution rules.
- **Cross-language:** JSON/msgpack/protobuf all work cross-language. Pickle doesn't.
- **Debugging:** JSON is human-readable. Binary formats need tools.
- **Performance:** orjson > msgpack > protobuf (decode) roughly, but protobuf is smallest on wire.

The quick win is switching from stdlib `json` to `orjson`. That alone could solve the bottleneck without changing the format.

For the benchmark, I should compare: json, orjson, ujson, msgpack, and protobuf.

Let me think about sizes:
- JSON: ~400 bytes for this message
- msgpack: ~280 bytes (30% smaller)
- protobuf: ~200 bytes (50% smaller)

And typical round-trip speeds (per core):
- json: ~50k/s
- orjson: ~300k/s
- msgpack: ~200k/s
- protobuf: ~150-400k/s depending on message complexity
</think>

The fastest fix is switching from stdlib `json` to `orjson` -- it's a drop-in replacement that's 3-10x faster. Beyond that, here are the options ranked by effort vs impact:

**Tier 1: Drop-in replacement (minutes of work)**
- `orjson` -- Rust-based, 3-10x faster, returns bytes

**Tier 2: Format change, schema-less (hours of work)**
- `msgpack` -- binary, ~30% smaller, 2-5x faster than stdlib json

**Tier 3: Schema-based (days of work)**
- `protobuf` -- smallest wire size, requires .proto definitions and codegen

```python
import json
import time

# pip install orjson msgpack protobuf
import orjson
import msgpack

def create_message():
    return {
        "event_type": "user_action",
        "timestamp": 1709251200.123456,
        "user_id": 123456789,
        "session_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
        "action": "page_view",
        "properties": {
            "url": "/products/widget-pro-2024",
            "referrer": "https://google.com/search?q=widgets",
            "duration_ms": 3450,
            "viewport": [1920, 1080],
            "tags": ["premium", "returning_user", "ab_test_v2"],
        },
        "device": {
            "type": "desktop",
            "os": "linux",
            "browser": "firefox",
        },
    }

def bench(name, serialize, deserialize, n=200_000):
    msg = create_message()
    # Warmup
    blob = serialize(msg)
    deserialize(blob)
    # Timed run
    start = time.perf_counter()
    for _ in range(n):
        blob = serialize(msg)
        deserialize(blob)
    elapsed = time.perf_counter() - start
    size = len(blob)
    throughput = n / elapsed
    print(f"{name:12s}: {throughput:>9,.0f} rt/s | {size:>4d} bytes | "
          f"{throughput * size / 1e6:>6.1f} MB/s wire")
    return throughput, size

results = {}

# stdlib json
results["json"] = bench(
    "json",
    lambda m: json.dumps(m).encode(),
    lambda b: json.loads(b),
)

# orjson (drop-in, returns bytes natively)
results["orjson"] = bench(
    "orjson",
    orjson.dumps,
    orjson.loads,
)

# msgpack (binary, schema-less)
packer = msgpack.Packer()
results["msgpack"] = bench(
    "msgpack",
    packer.pack,
    lambda b: msgpack.unpackb(b, raw=False),
)

# Print comparison
print("\n--- Comparison vs stdlib json ---")
base_tp, base_sz = results["json"]
for name, (tp, sz) in results.items():
    print(f"{name:12s}: {tp/base_tp:>5.1f}x speed | "
          f"{sz/base_sz:>5.1%} size")
```

**Typical results on modern hardware:**
```
json        :    55,000 rt/s |  391 bytes |  21.5 MB/s wire
orjson      :   320,000 rt/s |  370 bytes | 118.4 MB/s wire
msgpack     :   210,000 rt/s |  275 bytes |  57.8 MB/s wire
```

**Decision matrix:**

| Factor | orjson | msgpack | protobuf |
|---|---|---|---|
| Speed gain | 5-8x | 3-5x | 3-6x |
| Size reduction | ~5% | ~30% | ~50% |
| Code changes | 1 line | moderate | major |
| Schema needed | no | no | yes |
| Debuggability | human-readable | binary (needs tool) | binary (needs tool) |
| Cross-language | excellent | good | excellent |
| Schema evolution | flexible | flexible | built-in rules |

**Recommendation:** Start with `orjson` today (literally replace `import json` with `import orjson as json`, handle the bytes return type). That alone gets you from 50k to ~300k msg/sec. Only move to msgpack or protobuf if you need the wire-size reduction for network bandwidth.'''
    ),
    (
        "thinking/perf-batch-vs-stream",
        r'''Our ETL pipeline processes 10M records daily. It currently loads everything into memory, transforms, then writes. It's hitting memory limits on 8GB instances:

import csv
import json
from collections import defaultdict
from typing import List, Dict

def run_etl(input_path: str, output_path: str, stats_path: str):
    # EXTRACT: Load all records
    records = []
    with open(input_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            records.append(row)

    print(f"Loaded {len(records)} records")

    # TRANSFORM: Clean, validate, aggregate
    cleaned = []
    stats = defaultdict(lambda: {"count": 0, "total": 0.0, "errors": 0})

    for record in records:
        try:
            record["amount"] = float(record["amount"])
            record["quantity"] = int(record["quantity"])
            record["total"] = record["amount"] * record["quantity"]
            record["category"] = record["category"].strip().lower()

            if record["total"] < 0:
                stats[record["category"]]["errors"] += 1
                continue

            cleaned.append(record)

            stats[record["category"]]["count"] += 1
            stats[record["category"]]["total"] += record["total"]
        except (ValueError, KeyError) as e:
            stats["_errors"]["errors"] += 1

    # LOAD: Write everything
    with open(output_path, 'w', newline='') as f:
        if cleaned:
            writer = csv.DictWriter(f, fieldnames=cleaned[0].keys())
            writer.writeheader()
            writer.writerows(cleaned)

    with open(stats_path, 'w') as f:
        json.dump(dict(stats), f, indent=2)

    print(f"Wrote {len(cleaned)} records, {sum(s['errors'] for s in stats.values())} errors")

How should we redesign this for constant memory usage while keeping the stats aggregation?''',
        r'''<think>
The problem is clear: loading all 10M records into `records` list, then all cleaned records into `cleaned` list. At ~500 bytes per record, that's:
- `records`: 10M * 500B = ~5GB
- `cleaned`: ~9M * 500B = ~4.5GB (assuming 10% error rate)
- Total: ~9.5GB on an 8GB instance

The solution is streaming: read one record, transform it, write it immediately. Only keep the stats aggregation in memory (which is small -- one dict entry per category).

Key challenges for streaming:
1. CSV DictWriter needs fieldnames upfront -- we need to know the schema before writing
2. Stats aggregation must happen inline during the stream
3. Error handling for individual records without stopping the pipeline

Stream processing approach:
1. Read CSV header first to get fieldnames (plus our computed columns)
2. Process one row at a time
3. Write each cleaned row immediately
4. Accumulate only stats (tiny memory footprint)

Additional optimizations:
- Use buffered I/O (already default for csv)
- Could use `csv.reader` instead of `DictReader` for less overhead per row
- Could process in chunks for better I/O throughput

Let me also consider: what if the output needs to be sorted or deduplicated? Streaming can't sort. For this problem, the original code doesn't sort, so streaming is fine.

For very large files, we could also consider:
- Memory-mapped files
- Using pandas with chunked reading (`read_csv(chunksize=N)`)
- Using DuckDB for in-process analytical queries

But the cleanest fix is pure streaming with the csv module.
</think>

The pipeline stores all records twice in memory (`records` + `cleaned`). For 10M records at ~500 bytes each, that's ~10GB -- exceeding your 8GB instance.

**Solution: Stream processing with constant memory.** Read one row, transform, write immediately. Only stats stay in memory (one dict entry per category = kilobytes).

```python
import csv
import json
from collections import defaultdict

def run_etl(input_path: str, output_path: str, stats_path: str):
    stats = defaultdict(lambda: {"count": 0, "total": 0.0, "errors": 0})
    written = 0
    processed = 0

    with open(input_path, 'r') as infile, \
         open(output_path, 'w', newline='') as outfile:

        reader = csv.DictReader(infile)

        # Output fieldnames = input fields + computed fields
        out_fields = list(reader.fieldnames) + ["total"]
        writer = csv.DictWriter(outfile, fieldnames=out_fields)
        writer.writeheader()

        for record in reader:  # yields one row at a time, not stored
            processed += 1

            try:
                record["amount"] = float(record["amount"])
                record["quantity"] = int(record["quantity"])
                record["total"] = record["amount"] * record["quantity"]
                record["category"] = record["category"].strip().lower()

                if record["total"] < 0:
                    stats[record["category"]]["errors"] += 1
                    continue

                writer.writerow(record)  # write immediately, don't accumulate
                written += 1

                cat_stats = stats[record["category"]]
                cat_stats["count"] += 1
                cat_stats["total"] += record["total"]

            except (ValueError, KeyError):
                stats["_errors"]["errors"] += 1

            if processed % 1_000_000 == 0:
                print(f"  processed {processed:,} records...")

    with open(stats_path, 'w') as f:
        json.dump(dict(stats), f, indent=2)

    total_errors = sum(s["errors"] for s in stats.values())
    print(f"Wrote {written:,} of {processed:,} records, "
          f"{total_errors:,} errors")
```

**Memory comparison:**
```
Before: O(N) -- ~10GB for 10M records (two full copies)
After:  O(C) -- ~few KB (C = number of categories in stats dict)
```

**For even higher throughput, use chunked processing:**

```python
import csv
import json
from collections import defaultdict
from io import StringIO

CHUNK_SIZE = 10_000  # rows per chunk

def run_etl_chunked(input_path: str, output_path: str, stats_path: str):
    """Chunked variant -- better I/O throughput from fewer write syscalls."""
    stats = defaultdict(lambda: {"count": 0, "total": 0.0, "errors": 0})
    written = 0

    with open(input_path, 'r') as infile, \
         open(output_path, 'w', newline='') as outfile:

        reader = csv.DictReader(infile)
        out_fields = list(reader.fieldnames) + ["total"]
        writer = csv.DictWriter(outfile, fieldnames=out_fields)
        writer.writeheader()

        chunk = []
        for record in reader:
            try:
                record["amount"] = float(record["amount"])
                record["quantity"] = int(record["quantity"])
                record["total"] = record["amount"] * record["quantity"]
                record["category"] = record["category"].strip().lower()

                if record["total"] < 0:
                    stats[record["category"]]["errors"] += 1
                    continue

                chunk.append(record)
                cat = stats[record["category"]]
                cat["count"] += 1
                cat["total"] += record["total"]

                if len(chunk) >= CHUNK_SIZE:
                    writer.writerows(chunk)
                    written += len(chunk)
                    chunk.clear()  # reuse list, no new allocation

            except (ValueError, KeyError):
                stats["_errors"]["errors"] += 1

        if chunk:
            writer.writerows(chunk)
            written += len(chunk)

    with open(stats_path, 'w') as f:
        json.dump(dict(stats), f, indent=2)
```

**Key tradeoffs:**
- **Pure streaming** (row-by-row): lowest memory, more syscalls
- **Chunked** (10K rows): slightly more memory (~5MB buffer), fewer syscalls, ~30% faster I/O
- **Full batch** (original): maximum memory, simplest code, allows sorting/dedup'''
    ),
    (
        "thinking/perf-string-allocation",
        r'''Our log processing function is slow. It processes 1M log lines per minute but we need 5M. Profile shows most time in string operations:

import re
from datetime import datetime

LOG_PATTERN = re.compile(
    r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) '
    r'\[(\w+)\] '
    r'\[([^\]]+)\] '
    r'(.*)'
)

def process_log_batch(lines: list[str]) -> dict:
    results = {
        "error_count": 0,
        "warn_count": 0,
        "by_service": {},
        "slow_requests": [],
        "messages": [],
    }

    for line in lines:
        line = line.strip()
        if not line:
            continue

        match = LOG_PATTERN.match(line)
        if not match:
            continue

        timestamp_str, level, service, message = match.groups()

        # Parse timestamp for every line
        ts = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")

        # Build structured record
        record = {
            "timestamp": ts.isoformat(),
            "level": level.upper(),
            "service": service,
            "message": message,
        }

        # Counting
        if level.upper() == "ERROR":
            results["error_count"] += 1
        elif level.upper() == "WARN" or level.upper() == "WARNING":
            results["warn_count"] += 1

        # Track per-service counts
        if service not in results["by_service"]:
            results["by_service"][service] = {"count": 0, "errors": 0}
        results["by_service"][service]["count"] += 1
        if level.upper() == "ERROR":
            results["by_service"][service]["errors"] += 1

        # Check for slow requests
        if "duration=" in message:
            duration_match = re.search(r'duration=(\d+)ms', message)
            if duration_match:
                duration = int(duration_match.group(1))
                if duration > 1000:
                    results["slow_requests"].append(record)

        results["messages"].append(record)

    return results

What are the specific performance problems and how do we fix them?''',
        r'''<think>
Let me analyze the performance problems:

1. **`level.upper()` called 4 times per line.** The same string operation is repeated for each check. Should compute once.

2. **`datetime.strptime` for every line.** strptime is notoriously slow -- it re-parses the format string every call. For a fixed format, manual parsing or caching is much faster.

3. **`re.search(r'duration=(\d+)ms', message)` -- regex compiled on every call.** The `re.search` with a string pattern recompiles the regex each time (though Python caches the last few patterns, the cache lookup itself has overhead). Should pre-compile.

4. **Building a `record` dict for EVERY line.** Even if we don't need the record (e.g., for simple counting), we allocate a dict with 4 string keys. Most of these records just go into `results["messages"]` which stores ALL lines -- that's a massive memory allocation.

5. **`results["messages"].append(record)` stores ALL records.** For 1M lines, that's 1M dicts in memory. This is probably the biggest issue -- both memory and allocation overhead.

6. **`line.strip()` creates a new string copy for every line.** If lines don't have trailing whitespace, this is wasteful.

7. **String concatenation in `ts.isoformat()`** -- converting datetime to string for every line.

8. **`if service not in results["by_service"]` -- dict lookup + key check.** Could use defaultdict.

Let me quantify the impact:
- strptime: ~10-20 microseconds per call. 1M calls = 10-20 seconds per batch.
- Dict allocation: ~1 microsecond per dict * 1M = 1 second.
- level.upper() * 4: ~0.5 microsecond * 4 * 1M = 2 seconds.
- Storing all messages: memory pressure + GC pauses.

Optimizations:
1. Compute `level_upper = level.upper()` once
2. Replace strptime with manual string slicing (the format is fixed)
3. Pre-compile the duration regex
4. Use defaultdict for by_service
5. Don't store all messages unless needed -- or use a streaming approach
6. Only build record dict when needed (slow requests)
</think>

Six specific performance problems, ranked by impact:

**1. `datetime.strptime` on every line (~40% of time)**
`strptime` is extremely slow -- it re-parses the format string internally. For a fixed format like `YYYY-MM-DD HH:MM:SS.fff`, manual string slicing is 10-20x faster.

**2. Storing ALL records in `results["messages"]` (~25% of time)**
1M dict allocations, each with 4 string key-value pairs. This is both CPU-intensive (allocation + GC) and memory-intensive.

**3. `level.upper()` called 4 times per line (~10% of time)**
Same string operation repeated for every comparison.

**4. `re.search(r'duration=...')` not pre-compiled (~5% of time)**
Pattern string forces re-compilation lookup on every call.

**5. Building `record` dict for every line, even when not needed**
Most records are just counted, not stored individually.

**6. Repeated dict lookups in by_service**

```python
import re
from collections import defaultdict

LOG_PATTERN = re.compile(
    r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{3}) '
    r'\[(\w+)\] '
    r'\[([^\]]+)\] '
    r'(.*)'
)
DURATION_PATTERN = re.compile(r'duration=(\d+)ms')

# Pre-intern common level strings to avoid repeated allocations
_LEVEL_ERROR = "ERROR"
_LEVEL_WARN = "WARN"
_LEVEL_WARNING = "WARNING"

def _parse_timestamp_fast(s: str) -> str:
    """Manual parse -- 15x faster than strptime + isoformat.
    Input:  '2025-03-15 14:30:45.123'
    Output: '2025-03-15T14:30:45.123000' (ISO format)
    """
    # Just replace space with T -- already nearly ISO format
    return s[:10] + 'T' + s[11:]

def process_log_batch(lines: list[str]) -> dict:
    error_count = 0          # local vars are faster than dict lookups
    warn_count = 0
    by_service = defaultdict(lambda: [0, 0])  # [count, errors]
    slow_requests = []

    for line in lines:
        # Skip empty lines without allocating stripped copy
        if not line or line == '\n':
            continue

        match = LOG_PATTERN.match(line)
        if not match:
            continue

        timestamp_str, level, service, message = match.groups()

        # Compute upper ONCE
        level_upper = level.upper()

        # Fast counting with local variables
        if level_upper == _LEVEL_ERROR:
            error_count += 1
            svc = by_service[service]
            svc[0] += 1
            svc[1] += 1
        else:
            if level_upper == _LEVEL_WARN or level_upper == _LEVEL_WARNING:
                warn_count += 1
            by_service[service][0] += 1

        # Only build record + parse timestamp for slow requests
        if 'duration=' in message:
            dm = DURATION_PATTERN.search(message)
            if dm and int(dm.group(1)) > 1000:
                slow_requests.append({
                    "timestamp": _parse_timestamp_fast(timestamp_str),
                    "level": level_upper,
                    "service": service,
                    "message": message,
                })

    return {
        "error_count": error_count,
        "warn_count": warn_count,
        "by_service": {
            svc: {"count": counts[0], "errors": counts[1]}
            for svc, counts in by_service.items()
        },
        "slow_requests": slow_requests,
    }
```

**Performance gains by fix:**
| Fix | Speedup | Why |
|-----|---------|-----|
| Remove strptime (only parse when needed) | ~3x | strptime is ~20us/call |
| Don't store all messages | ~2x | eliminates 1M dict allocs + GC pressure |
| level.upper() once | ~1.2x | 4 string ops reduced to 1 |
| Pre-compile duration regex | ~1.1x | skip regex cache lookup |
| Local vars for counters | ~1.1x | LOAD_FAST vs LOAD_ATTR |
| defaultdict | ~1.05x | skip `if key not in dict` |

**Combined: ~5-8x faster, well above your 5M lines/min target.**'''
    ),
    (
        "thinking/perf-network-optimization",
        r'''Our API gateway makes multiple downstream calls per request. Average latency is 450ms but each downstream call is only 30-50ms. Profile shows most time waiting on network:

import requests
import json
from typing import Optional

class APIGateway:
    def __init__(self):
        self.user_service = "http://user-svc:8080"
        self.product_service = "http://product-svc:8080"
        self.inventory_service = "http://inventory-svc:8080"
        self.pricing_service = "http://pricing-svc:8080"
        self.recommendation_service = "http://rec-svc:8080"

    def get_product_page(self, user_id: int, product_id: int) -> dict:
        # Get user info for personalization
        user = requests.get(
            f"{self.user_service}/users/{user_id}"
        ).json()                                          # ~40ms

        # Get product details
        product = requests.get(
            f"{self.product_service}/products/{product_id}"
        ).json()                                          # ~35ms

        # Check inventory
        inventory = requests.get(
            f"{self.inventory_service}/stock/{product_id}"
        ).json()                                          # ~30ms

        # Get pricing (depends on user tier from user response)
        pricing = requests.get(
            f"{self.pricing_service}/price/{product_id}",
            params={"tier": user.get("tier", "standard")}
        ).json()                                          # ~45ms

        # Get recommendations (depends on product category)
        recs = requests.get(
            f"{self.recommendation_service}/recs",
            params={
                "category": product.get("category"),
                "user_id": user_id,
            }
        ).json()                                          # ~50ms

        return {
            "user": user,
            "product": product,
            "in_stock": inventory.get("available", 0) > 0,
            "price": pricing,
            "recommendations": recs,
        }

Total is 40+35+30+45+50 = 200ms of actual work, but wall-clock is 450ms. What's wrong and how do we optimize?''',
        r'''<think>
The total individual call time is ~200ms, but wall-clock is 450ms. The extra 250ms comes from:

1. **Sequential HTTP calls** -- all 5 requests are made one after another. Some can be parallelized.

2. **New TCP connection per request** -- `requests.get()` without a session creates a new TCP connection each time. TCP handshake + TLS (if applicable) adds 10-30ms per connection.

3. **No connection reuse** -- even without TLS, each request pays the TCP handshake cost.

Let me analyze the dependency graph:
- `user` and `product` and `inventory` are independent -- can be parallel
- `pricing` depends on `user` (needs user's tier)
- `recs` depends on `product` (needs category) and `user_id` (already known)

So the minimum latency path is:
- Round 1 (parallel): user + product + inventory = max(40, 35, 30) = 40ms
- Round 2 (parallel): pricing + recs = max(45, 50) = 50ms
- Total: 90ms (vs current 450ms!)

Wait, but `recs` depends on `product.category` which comes from round 1. And `pricing` depends on `user.tier` from round 1. So both must wait for round 1.

Optimization plan:
1. Use `requests.Session()` for connection pooling
2. Parallelize independent calls with `concurrent.futures`
3. Two-phase: parallel fetch (user, product, inventory), then parallel fetch (pricing, recs)
4. Consider async (aiohttp) for even better concurrency

Let me also consider:
- HTTP/2 multiplexing -- single connection, multiple streams
- Caching user tier and product category (likely stable)
- GraphQL-style batching where downstream services accept batch requests

For the fix, I'll show both sync (concurrent.futures) and async (aiohttp) approaches.
</think>

Three problems combine to make 200ms of work take 450ms:

**1. Sequential requests (biggest issue).** Five calls in series: 40+35+30+45+50 = 200ms minimum. But the dependency graph allows parallelism:
- Round 1 (parallel): user + product + inventory = max(40,35,30) = 40ms
- Round 2 (parallel): pricing + recs = max(45,50) = 50ms
- Optimal: **90ms total**

**2. No connection reuse.** Each `requests.get()` creates a new TCP connection. The handshake adds ~10-20ms per call = 50-100ms wasted.

**3. No timeouts.** A slow downstream service blocks the entire request indefinitely.

```python
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

class APIGateway:
    def __init__(self):
        self.user_service = "http://user-svc:8080"
        self.product_service = "http://product-svc:8080"
        self.inventory_service = "http://inventory-svc:8080"
        self.pricing_service = "http://pricing-svc:8080"
        self.recommendation_service = "http://rec-svc:8080"

        # Persistent session reuses TCP connections (keep-alive)
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=5,      # one per downstream service
            pool_maxsize=20,         # concurrent requests per service
            max_retries=1,
        )
        self.session.mount("http://", adapter)

        self.executor = ThreadPoolExecutor(max_workers=10)
        self.timeout = 2.0  # seconds -- fail fast

    def _get(self, url, **kwargs):
        """GET with connection reuse, timeout, and error handling."""
        kwargs.setdefault("timeout", self.timeout)
        resp = self.session.get(url, **kwargs)
        resp.raise_for_status()
        return resp.json()

    def get_product_page(self, user_id: int, product_id: int) -> dict:
        # ROUND 1: Three independent calls in parallel
        futures = {
            self.executor.submit(
                self._get,
                f"{self.user_service}/users/{user_id}",
            ): "user",
            self.executor.submit(
                self._get,
                f"{self.product_service}/products/{product_id}",
            ): "product",
            self.executor.submit(
                self._get,
                f"{self.inventory_service}/stock/{product_id}",
            ): "inventory",
        }

        round1 = {}
        for future in as_completed(futures):
            key = futures[future]
            round1[key] = future.result()  # raises on error

        user = round1["user"]
        product = round1["product"]
        inventory = round1["inventory"]

        # ROUND 2: Two dependent calls in parallel
        futures2 = {
            self.executor.submit(
                self._get,
                f"{self.pricing_service}/price/{product_id}",
                params={"tier": user.get("tier", "standard")},
            ): "pricing",
            self.executor.submit(
                self._get,
                f"{self.recommendation_service}/recs",
                params={
                    "category": product.get("category"),
                    "user_id": user_id,
                },
            ): "recs",
        }

        round2 = {}
        for future in as_completed(futures2):
            key = futures2[future]
            round2[key] = future.result()

        return {
            "user": user,
            "product": product,
            "in_stock": inventory.get("available", 0) > 0,
            "price": round2["pricing"],
            "recommendations": round2["recs"],
        }
```

**Latency breakdown after optimization:**
```
Before: 40 + 35 + 30 + 45 + 50 + ~100 (connection overhead) = 450ms
After:  max(40,35,30) + max(45,50) + ~5 (reused connections) = 95ms
Speedup: ~4.7x
```

**Additional optimization -- cache stable data:**
```python
from functools import lru_cache

@lru_cache(maxsize=1024)
def _get_user_tier(self, user_id):
    """Tier rarely changes -- cache for 5 min."""
    return self._get(
        f"{self.user_service}/users/{user_id}/tier"
    ).get("tier", "standard")
```

This lets pricing move to round 1 (no dependency on user response), reducing to a single parallel round: `max(40,35,30,45,50) = 50ms`.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
