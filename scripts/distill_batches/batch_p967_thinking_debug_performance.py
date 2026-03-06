PAIRS = [
    ("thinking/debugging", r'''I profiled my Python application with cProfile and the output is confusing:

```
         2847563 function calls (2756892 primitive calls) in 12.453 seconds

   Ordered by: cumulative time

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
        1    0.000    0.000   12.453   12.453 main.py:1(<module>)
        1    0.001    0.001   12.452   12.452 main.py:15(process_all)
     1000    0.025    0.000   12.102   0.012 processor.py:8(process_item)
     1000    0.015    0.000    8.234    0.008 db.py:23(query)
     1000    7.891    0.008    7.891    0.008 {method 'execute' of 'psycopg2...cursor'}
     1000    0.312    0.000    3.543    0.004 processor.py:25(transform)
  1000000    2.891    0.000    2.891    0.000 processor.py:30(validate_field)
     1000    0.098    0.000    0.340    0.000 processor.py:45(serialize)
```

The total time is 12.4 seconds. How do I read this to find the bottleneck?''', r'''<think>
Let me explain the cProfile columns and identify the bottleneck.

ncalls: number of times the function was called
tottime: total time spent IN this function (excluding calls to sub-functions)
percall: tottime / ncalls
cumtime: cumulative time (including sub-functions)
percall: cumtime / ncalls

Looking at the data:
- process_all: cumtime 12.452s (this is the main entry point, expected)
- process_item: called 1000 times, cumtime 12.102s each taking ~12ms
- query: called 1000 times, cumtime 8.234s (66% of total time!)
  - cursor.execute: tottime 7.891s (the actual DB execution)
- transform: 1000 calls, cumtime 3.543s
  - validate_field: 1,000,000 calls, tottime 2.891s
- serialize: 0.340s (negligible)

The biggest bottleneck is database queries at 8.234s (66% of total). The second issue is validate_field being called 1 million times (1000 per item) with 2.891s total.

The fix should focus on:
1. Reducing DB query count (batch queries)
2. Reducing validate_field calls or making it faster
</think>

Let me break down the cProfile columns and identify your bottlenecks.

**Understanding the columns:**

```
ncalls  - Number of times the function was called
tottime - Time spent INSIDE this function only (excluding subfunctions)
percall - tottime / ncalls
cumtime - Time spent in this function AND all functions it calls
percall - cumtime / ncalls
```

**Reading the profile top-down:**

```
process_all:   cumtime=12.45s  (entry point, contains everything)
  process_item:  cumtime=12.10s, called 1000 times (12ms each)
    query:         cumtime=8.23s  -> 66% of total time!
      execute:       tottime=7.89s  (actual DB wait time)
    transform:     cumtime=3.54s  -> 28% of total time
      validate_field: tottime=2.89s, called 1,000,000 times!
    serialize:     cumtime=0.34s  -> 3% (negligible)
```

**Bottleneck #1: Database queries (66% of time)**

1000 individual queries taking 8.2 seconds total. Each query takes ~8ms, which is reasonable per-query, but 1000 sequential queries is the problem.

Fix: Batch the queries.

```python
# BEFORE: 1000 individual queries (8.2s)
for item in items:
    result = db.query("SELECT * FROM data WHERE id = %s", item.id)

# AFTER: 1 batch query (~0.05s)
ids = [item.id for item in items]
results = db.query("SELECT * FROM data WHERE id = ANY(%s)", [ids])
results_by_id = {r.id: r for r in results}
```

This replaces 1000 round-trips with a single query, potentially reducing 8.2s to under 0.1s.

**Bottleneck #2: validate_field called 1 million times (23% of time)**

Each call takes only 2.89 microseconds, but 1 million calls add up to 2.89 seconds.

Fix: Reduce call count or optimize the function.

```python
# BEFORE: validate each field individually
def transform(item):
    for field in item.fields:  # ~1000 fields per item
        validate_field(field)

# AFTER: batch validation
def transform(item):
    validate_fields_batch(item.fields)  # single call, vectorized
```

Or use `__slots__`, avoid attribute lookups, or rewrite in C with Cython.

**Visualize the profile:**

```bash
# Generate visual flamegraph
pip install snakeviz
python -m cProfile -o profile.prof main.py
snakeviz profile.prof  # opens interactive visualization in browser
```

**Line-level profiling (more precise):**

```python
# pip install line_profiler
@profile
def transform(item):
    data = item.raw_data          # 0.1s
    validated = validate(data)     # 3.5s  <- found it!
    result = compute(validated)    # 0.2s
    return result
```

```bash
kernprof -l -v main.py
```

**Key profiling rules:**
- Focus on functions with high `tottime` (they do the actual work)
- Functions with high `cumtime` but low `tottime` are just calling slow subfunctions
- High `ncalls` with low per-call time means the function is fast but called too often
- Optimize the top 1-2 bottlenecks first -- Amdahl's Law says the rest gives diminishing returns

**Prevention tips:**
- Profile before optimizing -- never guess where the bottleneck is
- Use `py-spy` for sampling profiler that works in production (low overhead)
- Use `line_profiler` for line-by-line analysis of hot functions
- Profile with realistic data volumes, not toy datasets
- Re-profile after each optimization to verify improvement and find the next bottleneck'''),

    ("thinking/debugging", r'''My Python application uses 4GB of RAM for processing what should be a 500MB dataset:

```python
import tracemalloc

tracemalloc.start()

def process_data(filepath):
    with open(filepath) as f:
        data = json.load(f)  # 500MB JSON file

    results = []
    for record in data:
        transformed = transform(record)
        results.append(transformed)

    return results

results = process_data('data.json')

snapshot = tracemalloc.take_snapshot()
top_stats = snapshot.statistics('lineno')

for stat in top_stats[:10]:
    print(stat)
```

tracemalloc output:
```
data.json:0: size=2048.3 MiB, count=15234567, average=141 B
processor.py:12: size=1024.5 MiB, count=8000000, average=134 B
processor.py:8: size=512.2 MiB, count=4000000, average=134 B
```

Where is the memory going?''', r'''<think>
Let me analyze the memory usage:

1. `json.load(f)` on a 500MB JSON file: the in-memory representation of JSON data in Python is MUCH larger than the file size. JSON strings become Python str objects (each with 50+ bytes overhead). Numbers become Python int/float objects. Dicts and lists have per-object overhead. A 500MB JSON file easily becomes 2GB+ in Python memory.

2. `results = []` accumulating all transformed records: this creates another copy of all the data.

3. The `data` variable still holds the original parsed JSON while `results` is being built.

So peak memory = original JSON data (2GB) + results (1GB) + intermediate transforms = ~4GB.

Fixes:
1. Use streaming JSON parser (ijson)
2. Process records one at a time, don't hold everything in memory
3. Use generators instead of lists
4. Use more memory-efficient data structures
</think>

The 4GB memory usage comes from three sources:

**Source 1: JSON deserialization overhead (2GB for 500MB file)**

Python objects have significant overhead compared to raw JSON text:
- Each Python string: ~50 bytes overhead + string data
- Each Python int: 28 bytes (vs. 1-10 bytes in JSON)
- Each Python dict: ~232 bytes + entries
- Each Python list: ~56 bytes + pointers

A 500MB JSON file with millions of small objects easily expands to 2GB+ in Python memory.

**Source 2: Dual copies (data + results)**

```python
data = json.load(f)       # 2GB in memory
results = []
for record in data:       # data still in memory!
    transformed = transform(record)
    results.append(transformed)  # results grows to ~1GB
# Peak: data (2GB) + results (1GB) + intermediates = ~4GB
```

Both `data` and `results` exist simultaneously in memory.

**Fix 1: Stream JSON with ijson**

```python
import ijson

def process_data(filepath):
    results = []
    with open(filepath, 'rb') as f:
        for record in ijson.items(f, 'item'):
            transformed = transform(record)
            results.append(transformed)
    return results
```

`ijson` parses JSON incrementally, yielding one record at a time. Only one record is in memory at any point, not the entire 500MB file.

**Fix 2: Use generators for pipeline processing**

```python
import ijson

def stream_records(filepath):
    """Generator: yields one record at a time."""
    with open(filepath, 'rb') as f:
        yield from ijson.items(f, 'item')

def transform_stream(records):
    """Generator: transforms records lazily."""
    for record in records:
        yield transform(record)

def process_data(filepath):
    records = stream_records(filepath)
    transformed = transform_stream(records)

    # Write results directly to output, never holding all in memory
    with open('output.json', 'w') as f:
        f.write('[')
        for i, record in enumerate(transformed):
            if i > 0:
                f.write(',')
            json.dump(record, f)
        f.write(']')
```

Peak memory: ~1 record at a time instead of 4GB.

**Fix 3: Use pandas for structured data**

```python
import pandas as pd

# Read JSON in chunks
chunks = pd.read_json('data.json', lines=True, chunksize=10000)
for chunk in chunks:
    transformed = transform_df(chunk)
    transformed.to_csv('output.csv', mode='a', header=False)
```

**Fix 4: Use memory-mapped files for random access**

```python
import mmap
import orjson  # faster JSON library

with open('data.json', 'rb') as f:
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    data = orjson.loads(mm)  # orjson uses less memory than stdlib json
    mm.close()
```

`orjson` is 2-3x faster and uses less memory than the standard json module.

**Memory profiling tools:**

```python
# tracemalloc: built-in, shows allocation sites
tracemalloc.start()
# ... your code ...
snapshot = tracemalloc.take_snapshot()
top = snapshot.statistics('traceback')

# memory_profiler: line-by-line memory usage
# pip install memory_profiler
@profile
def process_data(filepath):
    data = json.load(open(filepath))  # +2048 MiB
    results = []
    for record in data:
        results.append(transform(record))  # +1024 MiB
```

**Prevention tips:**
- Never load an entire large file into memory when you can stream it
- Use generators and iterators for data pipelines
- Process and write results incrementally instead of collecting in a list
- Use `sys.getsizeof()` to check object sizes (but note: it does not include referenced objects)
- Consider `orjson` or `ujson` for faster, more memory-efficient JSON parsing
- Use `resource.getrusage(resource.RUSAGE_SELF).ru_maxrss` to track peak RSS'''),

    ("thinking/debugging", r'''My application is I/O bound but I can't tell if it's disk I/O or network I/O. How do I diagnose this?

The application processes files and makes API calls. CPU usage is only 5% but throughput is low:

```
$ top
  PID USER      PR  NI    VIRT    RES    SHR S  %CPU %MEM     TIME+
12345 app       20   0  512m   128m    24m S   5.0  3.2   0:45.23

$ iostat -x 1
Device   r/s   w/s  rkB/s  wkB/s  await  %util
sda     250.0  50.0 32000  6400   12.5   95.0

$ ss -s
Total: 342
TCP:   238 (estab 45, closed 180, orphaned 2, timewait 180)
```

Is this disk I/O bound or network I/O bound?''', r'''<think>
Let me analyze the metrics:

1. CPU at 5% -- clearly not CPU bound
2. Disk: 250 reads/s, 95% utilization, 12.5ms average wait. 95% disk utilization means the disk is basically saturated. 12.5ms await is high (typical SSD should be <1ms, HDD ~5-10ms).
3. Network: 238 TCP connections, 180 in TIME_WAIT state. That is a lot of TIME_WAIT, suggesting many short-lived connections.

The disk is at 95% utilization -- that is clearly the primary bottleneck. The high await time (12.5ms) confirms the disk is overloaded and requests are queuing.

But the network stats also show issues -- 180 TIME_WAIT connections suggest rapid connection creation/destruction, which might be contributing to latency.

The primary bottleneck is disk I/O at 95% utilization.
</think>

Based on the metrics, your primary bottleneck is **disk I/O**. The disk is at 95% utilization with 12.5ms average wait time. Let me explain how to read each metric:

**Disk I/O analysis (iostat):**

```
Device   r/s   w/s  rkB/s  wkB/s  await  %util
sda     250.0  50.0 32000  6400   12.5   95.0
```

- `%util = 95.0%`: Disk is nearly saturated. This is the clearest indicator.
- `await = 12.5ms`: Average I/O wait time. For SSD this should be <1ms. For HDD, <10ms. 12.5ms means I/O requests are queuing up.
- `r/s = 250`: 250 read operations per second
- `rkB/s = 32000`: Reading 32MB/s (average 128KB per read)

**Network analysis (ss):**

```
TCP: 238 (estab 45, closed 180, timewait 180)
```

- 180 TIME_WAIT connections indicate rapid connection churn
- Only 45 established connections -- not many concurrent network operations
- TIME_WAIT is not inherently bad but suggests connections are being created/destroyed frequently instead of being reused

**Deeper diagnosis:**

```bash
# 1. Which processes are doing the most disk I/O?
iotop -o  # shows only processes actively doing I/O

# 2. What files are being accessed?
strace -p 12345 -e trace=read,write,open -c
# Shows syscall counts and time spent in each

# 3. Is it random or sequential I/O?
# Random I/O is much slower than sequential
iostat -x 1
# If rrqm/s (merged reads) is low, it's random I/O
# If avgrq-sz (average request size) is small (< 8 sectors), it's random

# 4. Network latency check
curl -w "dns: %{time_namelookup} connect: %{time_connect} ttfb: %{time_starttransfer}\n" \
     -o /dev/null -s https://api.example.com/
```

**Fix the disk I/O bottleneck:**

```python
# 1. Use async I/O to overlap disk and network operations
import asyncio
import aiofiles

async def process_file(filepath):
    async with aiofiles.open(filepath, 'r') as f:
        data = await f.read()
    result = transform(data)
    return result

# 2. Reduce small reads with buffering
with open(filepath, 'r', buffering=1024*1024) as f:  # 1MB buffer
    data = f.read()

# 3. Use mmap for random access patterns
import mmap
with open(filepath, 'rb') as f:
    mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
    # Random reads are served from page cache when possible
```

**Fix the network connection churn:**

```python
# Use connection pooling to eliminate TIME_WAIT
import requests

session = requests.Session()  # reuses connections
adapter = requests.adapters.HTTPAdapter(
    pool_connections=10,
    pool_maxsize=20,
)
session.mount('https://', adapter)

# All requests reuse TCP connections -- no TIME_WAIT
for url in urls:
    response = session.get(url)
```

**I/O bound diagnostic checklist:**

```
1. Check CPU:    top / htop              -> if < 20%, I/O bound
2. Check disk:   iostat -x 1             -> %util > 80% = disk bound
3. Check network: ss -s / iftop          -> many connections / high bandwidth
4. Check waits:  pidstat -d 1            -> iodelay column shows I/O waits
5. Check files:  lsof -p <pid>           -> what files are open
6. Check syscalls: strace -c -p <pid>    -> time spent in I/O syscalls
```

**Prevention tips:**
- Profile I/O separately from CPU -- use `iotop` and `iostat` alongside `cProfile`
- Use connection pooling for HTTP clients to avoid TCP connection overhead
- Buffer small I/O operations into larger batches
- Use async I/O (asyncio, aiofiles) to overlap disk and network operations
- Consider SSDs for random I/O workloads (100x improvement over HDD)
- Monitor `%iowait` in `top` -- high iowait with low CPU means I/O bound'''),

    ("thinking/debugging", r'''My application's response time spikes every 30 seconds. Profiling shows it's GC pauses:

```
gc: collecting generation 2...
gc: objects in each generation: 0 0 1523456
gc: done, 12345 unreachable, 0 uncollectable, 0.892s elapsed
```

The generation 2 GC collection takes nearly 1 second and happens every 30 seconds, causing visible latency spikes.

```python
import gc
gc.set_debug(gc.DEBUG_STATS)

# Current thresholds:
print(gc.get_threshold())  # (700, 10, 10)

# GC stats:
print(gc.get_stats())
# [{'collections': 4523, 'collected': 892345, 'uncollectable': 0},
#  {'collections': 452, 'collected': 45678, 'uncollectable': 0},
#  {'collections': 45, 'collected': 12345, 'uncollectable': 0}]
```

How do I reduce the GC pause time?''', r'''<think>
Python's garbage collector uses a generational scheme with 3 generations. Generation 2 is for long-lived objects. When generation 2 is collected, the GC must traverse all objects in all generations, which is expensive when there are 1.5 million objects.

The 0.892s pause is because the GC is traversing 1,523,456 objects. The GC's time is proportional to the number of objects it must scan.

Solutions:
1. Reduce the number of long-lived objects in generation 2
2. Tune GC thresholds to collect more frequently (smaller pauses) or less frequently
3. Disable GC and use explicit collection at appropriate times
4. Use objects that don't participate in GC (tuples, strings, etc.)
5. Use gc.freeze() to exclude old objects from scanning
</think>

Python's generational GC traverses all objects in generation 2 during collection. With 1.5 million objects, this takes ~0.9 seconds. The GC time is proportional to the number of objects that must be scanned, not just the unreachable ones.

**Understanding the generations:**

```
Generation 0: newly created objects, collected most frequently
Generation 1: survived one gen-0 collection
Generation 2: survived one gen-1 collection (long-lived objects)
             This is where your 1.5M objects live
```

Threshold (700, 10, 10) means:
- Gen 0 collected when 700 new allocations since last gen-0 collection
- Gen 1 collected every 10 gen-0 collections
- Gen 2 collected every 10 gen-1 collections
- So gen 2 runs every ~100 gen-0 collections

**Fix 1: Use gc.freeze() to exclude stable objects (Python 3.7+)**

```python
import gc

# After initial setup/warmup, freeze all existing objects
# They won't be scanned in future GC runs
gc.collect()   # clean up first
gc.freeze()    # move all objects to a permanent set

# Now GC only scans objects created AFTER freeze()
# Gen 2 collections become much faster
```

This is ideal if most of your 1.5M objects are created at startup (caches, config, data structures) and rarely change.

**Fix 2: Tune GC thresholds**

```python
import gc

# Option A: Increase gen-2 threshold (less frequent, longer pauses)
gc.set_threshold(700, 10, 50)  # gen-2 every 500 gen-0 collections

# Option B: Decrease gen-2 threshold (more frequent, shorter pauses)
gc.set_threshold(700, 10, 5)   # gen-2 every 50 gen-0 collections
# Shorter pauses but more frequent, same total GC time

# Option C: Increase gen-0 threshold (fewer GC cycles overall)
gc.set_threshold(50000, 10, 10)
```

**Fix 3: Disable GC and collect manually at safe points**

```python
import gc

gc.disable()  # disable automatic GC

# In your request handler:
async def handle_request(request):
    response = process(request)
    return response

# Collect during idle periods (between requests)
async def periodic_gc():
    while True:
        await asyncio.sleep(5)
        gc.collect(generation=0)  # fast: only gen 0
        gc.collect(generation=1)  # medium: gen 0 + 1
        # Do full collection less frequently:
        if should_do_full_gc():
            gc.collect(generation=2)
```

**Fix 4: Reduce object count with __slots__**

```python
# BEFORE: each instance has a __dict__ (GC must scan it)
class Record:
    def __init__(self, id, name, value):
        self.id = id
        self.name = name
        self.value = value
# Memory per instance: ~400 bytes, participates in GC

# AFTER: __slots__ eliminates __dict__
class Record:
    __slots__ = ('id', 'name', 'value')
    def __init__(self, id, name, value):
        self.id = id
        self.name = name
        self.value = value
# Memory per instance: ~150 bytes, simpler GC scanning
```

**Fix 5: Use GC-free data structures**

```python
# Tuples, strings, ints, frozensets do NOT participate in GC cycle detection
# (they can't contain references to other objects in a cycle)

# BEFORE: list of dicts (GC must scan each dict)
records = [{'id': i, 'name': f'item_{i}'} for i in range(1000000)]

# AFTER: named tuples (GC doesn't scan them)
from collections import namedtuple
Record = namedtuple('Record', ['id', 'name'])
records = [Record(i, f'item_{i}') for i in range(1000000)]
```

**Prevention tips:**
- Use `gc.freeze()` after application startup/warmup
- Profile GC with `gc.set_debug(gc.DEBUG_STATS)` to see collection times
- Monitor GC pauses: `gc.callbacks` can log every collection
- Use `__slots__` on classes that have many instances
- Prefer tuples over dicts for immutable record-like data
- Consider using PyPy which has an incremental GC with shorter pauses'''),

    ("thinking/debugging", r'''My Redis cache hit rate dropped from 95% to 40% and response times increased. The cache seems to be evicting keys prematurely:

```
$ redis-cli info memory
used_memory: 8589934592  (8GB)
used_memory_rss: 10737418240  (10GB)
maxmemory: 8589934592  (8GB)
maxmemory_policy: allkeys-lru
mem_fragmentation_ratio: 1.25

$ redis-cli info stats
evicted_keys: 2345678
keyspace_hits: 4500000
keyspace_misses: 6750000
```

maxmemory is set to 8GB and used_memory is at the limit. Redis is evicting keys aggressively. But the actual RSS is 10GB. Where's the extra 2GB going?''', r'''<think>
The mem_fragmentation_ratio of 1.25 means RSS is 25% higher than used_memory. This is memory fragmentation -- the allocator (jemalloc) has allocated 10GB from the OS but only 8GB is used by Redis data. The 2GB gap is fragmented memory that cannot be reused.

With maxmemory=8GB and used_memory=8GB, Redis is at its limit and evicting keys. But because of fragmentation, the actual process uses 10GB. If the machine has only 10-12GB total, this could cause swapping.

The high eviction rate (2.3M keys) explains the drop in hit rate. Keys are being evicted faster than they can be reused.

Solutions:
1. Defragment Redis (active defrag)
2. Increase maxmemory
3. Reduce fragmentation by sizing keys consistently
4. Use Redis memory optimization techniques
</think>

The 2GB gap between `used_memory` (8GB) and `used_memory_rss` (10GB) is memory fragmentation. The `mem_fragmentation_ratio` of 1.25 confirms this: the memory allocator (jemalloc) has allocated 25% more OS memory than Redis is actually using for data.

With maxmemory set to 8GB and used_memory hitting that limit, Redis is aggressively evicting keys (2.3 million evicted). This causes the cache hit rate to plummet because frequently-accessed keys are being removed.

**Why fragmentation happens:**

Redis stores keys and values in variable-sized allocations. When keys are deleted or updated with different-sized values, the freed memory becomes fragmented -- small gaps that cannot be reused for larger allocations. jemalloc requests more memory from the OS instead.

**Fix 1: Enable active defragmentation**

```
# redis.conf
activedefrag yes
active-defrag-enabled yes
active-defrag-ignore-bytes 100mb
active-defrag-threshold-lower 10
active-defrag-threshold-upper 100
active-defrag-cycle-min 1
active-defrag-cycle-max 25
```

Or at runtime:
```
redis-cli CONFIG SET activedefrag yes
```

Active defrag moves data to eliminate gaps, reducing RSS without evicting keys.

**Fix 2: Increase maxmemory to account for fragmentation**

```
# If you have 12GB available, account for 25% fragmentation:
# Usable data memory: 12GB / 1.25 = 9.6GB
CONFIG SET maxmemory 9600mb
```

**Fix 3: Use better eviction policy**

```
# allkeys-lru: evicts least recently used from ALL keys
# volatile-lru: evicts least recently used from keys WITH expiry
# allkeys-lfu: evicts least FREQUENTLY used (better for most workloads)
CONFIG SET maxmemory-policy allkeys-lfu
```

`allkeys-lfu` (Least Frequently Used) keeps hot keys better than `allkeys-lru` because it considers access frequency, not just recency.

**Fix 4: Reduce memory usage per key**

```python
# Use shorter key names
# BAD:  user:session:authentication:token:12345
# GOOD: u:s:12345

# Use Redis hashes for small objects (memory-efficient encoding)
# BAD: multiple string keys
redis.set('user:1:name', 'Alice')
redis.set('user:1:email', 'alice@example.com')
# Each key has ~60 bytes overhead

# GOOD: single hash
redis.hset('user:1', mapping={'name': 'Alice', 'email': 'alice@example.com'})
# Hash with <128 fields uses ziplist encoding (very compact)

# Use MessagePack instead of JSON for values
import msgpack
redis.set('data:1', msgpack.packb(data))  # 30-50% smaller than JSON
```

**Fix 5: Set appropriate TTLs**

```python
# Set TTLs on all cached data
redis.setex('cache:key', 3600, value)  # expires in 1 hour

# Use shorter TTLs for less important data
redis.setex('cache:listing', 300, value)   # 5 minutes
redis.setex('cache:config', 86400, value)  # 1 day
```

**Monitoring commands:**

```bash
# Memory usage breakdown
redis-cli memory doctor

# Check for big keys causing fragmentation
redis-cli --bigkeys

# Memory usage of specific key
redis-cli memory usage mykey

# Distribution of key sizes
redis-cli --memkeys
```

**Prevention tips:**
- Monitor `mem_fragmentation_ratio` -- anything above 1.5 needs attention
- Enable active defragmentation in production
- Use consistent value sizes to reduce fragmentation
- Set maxmemory to 75-80% of available RAM to leave room for fragmentation
- Use `allkeys-lfu` eviction policy for cache workloads
- Set TTLs on all keys and monitor `evicted_keys` rate'''),
]
