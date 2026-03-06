PAIRS = [
    ("thinking/debugging", r'''Our cache is experiencing a thundering herd problem. When a popular cache key expires, hundreds of requests simultaneously hit the database:

```
10:00:00 Cache hit: product:featured (TTL: 300s)
10:05:00 Cache MISS: product:featured (expired)
10:05:00 DB query from worker-1: SELECT * FROM products WHERE featured=true
10:05:00 DB query from worker-2: SELECT * FROM products WHERE featured=true
10:05:00 DB query from worker-3: SELECT * FROM products WHERE featured=true
... (200 concurrent queries for the same data)
10:05:02 Database response time: 15000ms (overloaded!)
```

All 200 workers simultaneously discover the cache miss and query the database.''', r'''<think>
The thundering herd problem: when a popular cache key expires, all concurrent requests miss the cache simultaneously and all go to the database. This can overwhelm the database.

Solutions:
1. Cache stampede lock (only one request rebuilds the cache, others wait)
2. Stale-while-revalidate (serve stale data while refreshing in background)
3. Probabilistic early expiration
4. Cache warming / pre-refresh
</think>

The thundering herd occurs when a popular cache key expires and all concurrent requests simultaneously miss the cache and hit the database. With 200 workers and a 5-minute TTL, the moment the key expires, 200 identical database queries fire at once.

**Fix 1: Cache stampede lock (mutex)**

Only one request rebuilds the cache; others wait or get stale data:

```python
import redis
import time

r = redis.Redis()

def get_with_lock(key, ttl=300, lock_timeout=10, query_func=None):
    # Try cache first
    value = r.get(key)
    if value is not None:
        return json.loads(value)

    # Cache miss -- try to acquire rebuild lock
    lock_key = f"lock:{key}"
    lock_acquired = r.set(lock_key, "1", nx=True, ex=lock_timeout)

    if lock_acquired:
        try:
            # This worker rebuilds the cache
            value = query_func()
            r.setex(key, ttl, json.dumps(value))
            return value
        finally:
            r.delete(lock_key)
    else:
        # Another worker is rebuilding -- wait and retry
        for _ in range(lock_timeout * 10):
            time.sleep(0.1)
            value = r.get(key)
            if value is not None:
                return json.loads(value)

        # Timeout -- fall back to database
        return query_func()
```

**Fix 2: Stale-while-revalidate (best for user experience)**

Serve slightly stale data immediately while refreshing in the background:

```python
def get_with_swr(key, ttl=300, stale_ttl=60, query_func=None):
    # Store data with metadata
    raw = r.get(key)
    if raw:
        cached = json.loads(raw)
        if time.time() < cached['expires_at']:
            return cached['data']  # fresh data
        elif time.time() < cached['stale_until']:
            # Data is stale but usable -- serve it and refresh in background
            trigger_background_refresh(key, ttl, stale_ttl, query_func)
            return cached['data']

    # Cache miss or stale expired -- synchronous rebuild
    return rebuild_cache(key, ttl, stale_ttl, query_func)

def rebuild_cache(key, ttl, stale_ttl, query_func):
    data = query_func()
    cached = {
        'data': data,
        'expires_at': time.time() + ttl,
        'stale_until': time.time() + ttl + stale_ttl,
    }
    r.setex(key, ttl + stale_ttl, json.dumps(cached))
    return data

def trigger_background_refresh(key, ttl, stale_ttl, query_func):
    lock_key = f"refresh:{key}"
    if r.set(lock_key, "1", nx=True, ex=30):
        # Only one worker refreshes
        import threading
        threading.Thread(
            target=rebuild_cache,
            args=(key, ttl, stale_ttl, query_func),
            daemon=True,
        ).start()
```

**Fix 3: Probabilistic early expiration (XFetch)**

Each request has a small probability of refreshing the cache BEFORE it expires:

```python
import random
import math

def get_with_xfetch(key, ttl=300, beta=1.0, query_func=None):
    raw = r.get(key)
    if raw:
        cached = json.loads(raw)
        now = time.time()
        delta = cached.get('compute_time', 0.1)
        expiry = cached['expires_at']

        # Probabilistic decision: refresh early?
        # Higher beta = more aggressive early refresh
        xfetch_time = delta * beta * math.log(random.random())
        if now - xfetch_time < expiry:
            return cached['data']  # use cached value

    # Rebuild (either expired or probabilistically chosen)
    start = time.time()
    data = query_func()
    compute_time = time.time() - start

    cached = {
        'data': data,
        'expires_at': time.time() + ttl,
        'compute_time': compute_time,
    }
    r.setex(key, ttl, json.dumps(cached))
    return data
```

This spreads cache rebuilds over time instead of having all requests rebuild at the exact same moment.

**Fix 4: Cache warming with scheduled refresh**

```python
import asyncio

async def cache_warmer():
    """Pre-refresh popular keys before they expire."""
    popular_keys = [
        ('product:featured', 300, fetch_featured_products),
        ('stats:daily', 600, fetch_daily_stats),
    ]

    while True:
        for key, ttl, query_func in popular_keys:
            remaining_ttl = r.ttl(key)
            if remaining_ttl < 30:  # refresh 30s before expiry
                data = await query_func()
                r.setex(key, ttl, json.dumps(data))
        await asyncio.sleep(10)
```

**Prevention tips:**
- Use stale-while-revalidate for the best user experience
- Use cache stampede locks for expensive queries
- Pre-warm popular cache keys before they expire
- Stagger TTLs with jitter: `ttl + random.randint(0, 60)` to avoid synchronized expiration
- Monitor cache hit rates and miss spikes as indicators of thundering herd
- Use Redis Cluster or separate read replicas for high-traffic cache lookups'''),

    ("thinking/debugging", r'''Our cache invalidation is causing data inconsistency. Users see stale data after updates:

```python
def update_user(user_id, data):
    # Update database
    db.execute("UPDATE users SET name=%s WHERE id=%s", (data['name'], user_id))

    # Invalidate cache
    cache.delete(f'user:{user_id}')

def get_user(user_id):
    cached = cache.get(f'user:{user_id}')
    if cached:
        return json.loads(cached)

    user = db.execute("SELECT * FROM users WHERE id=%s", (user_id,)).fetchone()
    cache.setex(f'user:{user_id}', 300, json.dumps(dict(user)))
    return dict(user)
```

Race condition: User A updates their name. Between the DB update and cache delete, User B reads the stale cache. Or worse: after cache delete, User B reads from a read replica that hasn't replicated yet and caches the old data.''', r'''<think>
There are multiple race conditions here:

1. Between DB update and cache delete: requests read stale cache
2. After cache delete, before cache repopulation: a request reads from a stale DB replica and caches old data
3. Two concurrent reads after cache delete: both query the DB, one caches old data if there's replication lag

The classic cache invalidation problem. Solutions:
1. Write-through cache (update cache and DB together)
2. Cache-aside with version/timestamp
3. Use change data capture (CDC) for cache invalidation
4. Read from primary after writes
</think>

There are multiple race conditions in this cache invalidation pattern:

**Race 1: Read between DB update and cache delete**
```
t=0: Thread A updates DB (name="Bob")
t=1: Thread B reads cache -> gets stale "Alice"
t=2: Thread A deletes cache
```

**Race 2: Stale read replica caches old data**
```
t=0: Thread A updates primary DB (name="Bob")
t=1: Thread A deletes cache
t=2: Thread B reads cache -> MISS
t=3: Thread B reads from read replica -> gets "Alice" (replication lag!)
t=4: Thread B caches "Alice" for 300 seconds
```

**Fix 1: Delete cache BEFORE updating DB**

```python
def update_user(user_id, data):
    cache.delete(f'user:{user_id}')  # delete first
    db.execute("UPDATE users SET name=%s WHERE id=%s", (data['name'], user_id))
    # Optional: set cache with new data
    cache.setex(f'user:{user_id}', 300, json.dumps(data))
```

This ensures no stale data is served after the update starts. The brief window where cache is empty causes a DB read, which is acceptable.

**Fix 2: Use a cache version/generation counter**

```python
def update_user(user_id, data):
    # Increment version
    version = cache.incr(f'user:{user_id}:version')

    # Update database
    db.execute("UPDATE users SET name=%s WHERE id=%s", (data['name'], user_id))

    # Set cache with version
    cache.setex(f'user:{user_id}:{version}', 300, json.dumps(data))

def get_user(user_id):
    version = cache.get(f'user:{user_id}:version') or 0
    cached = cache.get(f'user:{user_id}:{version}')
    if cached:
        return json.loads(cached)

    # Read from PRIMARY (not replica) after cache miss
    user = db.execute(
        "SELECT * FROM users WHERE id=%s",
        (user_id,),
        using='primary'  # force primary read
    ).fetchone()

    cache.setex(f'user:{user_id}:{version}', 300, json.dumps(dict(user)))
    return dict(user)
```

**Fix 3: Write-through cache**

```python
def update_user(user_id, data):
    with db.begin() as txn:
        db.execute("UPDATE users SET name=%s WHERE id=%s", (data['name'], user_id))
        txn.commit()

        # Update cache atomically after DB commit
        new_user = db.execute("SELECT * FROM users WHERE id=%s", (user_id,)).fetchone()
        cache.setex(f'user:{user_id}', 300, json.dumps(dict(new_user)))
```

**Fix 4: Double-delete with delay**

```python
def update_user(user_id, data):
    # First delete
    cache.delete(f'user:{user_id}')

    # Update database
    db.execute("UPDATE users SET name=%s WHERE id=%s", (data['name'], user_id))

    # Second delete after replication lag window
    time.sleep(1)  # or use a delayed task queue
    cache.delete(f'user:{user_id}')
```

The delayed second delete catches any stale reads that were cached between the DB update and replication.

**Fix 5: Use Change Data Capture (CDC)**

```python
# Use Debezium or similar CDC tool to watch database changes
# and automatically invalidate/update cache

# Debezium captures: users table, row id=42, name changed to "Bob"
# Cache invalidation service receives this event and updates cache

# This is the most reliable approach for complex systems
```

**Prevention tips:**
- Read from primary database after cache misses that follow writes
- Use short TTLs (30-60s) for frequently-updated data
- Prefer write-through (update cache + DB together) over cache-aside (invalidate + lazy load)
- Use CDC for reliable cache invalidation in microservices
- Add a short delay between DB write and cache population to allow replication
- Monitor cache hit rates after updates to detect staleness issues'''),

    ("thinking/debugging", r'''Our Redis cache memory keeps growing even though we set TTLs on all keys:

```
$ redis-cli info memory
used_memory_human: 7.5G
maxmemory_human: 8G
evicted_keys: 0
expired_keys: 2345678

$ redis-cli dbsize
(integer) 15000000

$ redis-cli info keyspace
db0:keys=15000000,expires=15000000,avg_ttl=259200000
```

All 15 million keys have TTLs but average TTL is 3 days. Memory is near the limit. We expected much lower memory usage because keys should expire.''', r'''<think>
The issue is that TTL expiration in Redis is not immediate. Redis uses two strategies for expiring keys:

1. Lazy expiration: when a key is accessed, Redis checks if it has expired and deletes it
2. Active expiration: Redis periodically samples random keys with TTLs and deletes expired ones. It samples 20 random keys per cycle, deletes expired ones, and if > 25% were expired, repeats.

With 15 million keys and only periodic sampling, it takes time for all expired keys to be actually removed. If new keys are created faster than expired keys are removed, memory grows.

The avg_ttl of 3 days means keys live for 3 days on average, so there is always a large number of live keys.

Also, keys that are set but never accessed are only removed by the active expiration process, which is probabilistic and may not keep up.
</think>

Redis key expiration is not instantaneous. Redis uses two strategies to remove expired keys, and neither guarantees immediate removal:

1. **Lazy expiration**: Keys are checked when accessed. An expired key that is never accessed stays in memory.
2. **Active expiration**: Redis samples 20 random keys with TTLs, deletes expired ones. If more than 25% of the sample was expired, it repeats. This runs 10 times per second.

With 15 million keys, the active expiration process may not keep up, especially if expired keys accumulate faster than they are sampled.

**Why memory is high despite TTLs:**

```
15 million keys with average TTL of 3 days:
- At any given time, most keys are still valid (not yet expired)
- Keys created 2.9 days ago are still alive
- Only keys older than their TTL are candidates for deletion
- With high write rates, expired keys may not be sampled quickly enough
```

**Fix 1: Reduce TTLs**

```python
# Instead of 3-day TTL, use shorter TTLs with background refresh
cache.setex(key, 300, value)  # 5 minutes instead of 3 days

# Use a background job to refresh frequently-needed keys
async def cache_refresher():
    while True:
        for key, query in important_keys.items():
            data = await query()
            cache.setex(key, 300, json.dumps(data))
        await asyncio.sleep(60)
```

**Fix 2: Tune Redis active expiration**

```
# redis.conf
# Increase active expiration effort (1-10, default 1)
# Higher values use more CPU but expire keys faster
hz 25  # default is 10, increase for faster expiration

# Or in Redis 6.0+:
dynamic-hz yes  # auto-adjust based on load
```

**Fix 3: Use maxmemory-policy to handle memory pressure**

```
# When memory limit is reached, evict keys
maxmemory 8gb
maxmemory-policy allkeys-lfu  # evict least frequently used

# Or volatile-ttl: evict keys with shortest remaining TTL
maxmemory-policy volatile-ttl
```

**Fix 4: Use Redis memory optimization**

```python
# Use hashes for small objects (ziplist encoding)
# Instead of:
cache.set('user:1:name', 'Alice')    # ~60 bytes overhead per key
cache.set('user:1:email', 'a@b.com') # ~60 bytes overhead per key

# Use:
cache.hset('user:1', mapping={'name': 'Alice', 'email': 'a@b.com'})
# One key with ~60 bytes overhead + small hash overhead

# Configure hash encoding thresholds
# redis.conf:
# hash-max-ziplist-entries 128
# hash-max-ziplist-value 64
```

**Fix 5: Monitor and alert on memory usage**

```python
import redis

r = redis.Redis()
info = r.info('memory')
memory_pct = info['used_memory'] / info['maxmemory'] * 100

if memory_pct > 80:
    alert(f"Redis memory at {memory_pct:.1f}%")

# Check expiration backlog
keyspace = r.info('keyspace')
stats = r.info('stats')
print(f"Expired keys/s: {stats['expired_keys']}")
print(f"Evicted keys: {stats['evicted_keys']}")
```

**Fix 6: Use Redis SCAN to manually expire old keys**

```python
# Emergency cleanup: force expire old keys
cursor = 0
deleted = 0
while True:
    cursor, keys = r.scan(cursor, count=1000)
    for key in keys:
        ttl = r.ttl(key)
        if ttl == -1:  # no TTL set!
            r.expire(key, 3600)  # set 1-hour TTL
            deleted += 1
    if cursor == 0:
        break
print(f"Set TTL on {deleted} keys without expiration")
```

**Prevention tips:**
- Use the shortest reasonable TTL for each key type
- Monitor `used_memory` and `evicted_keys` metrics
- Set `maxmemory-policy` to handle memory pressure gracefully
- Increase `hz` for faster active expiration
- Use hashes for groups of related small values
- Never create keys without TTLs in a cache-only Redis instance
- Run `redis-cli --memkeys` periodically to find large keys'''),

    ("thinking/debugging", r'''Our cache invalidation cascade is causing a "cache avalanche" -- when one cache entry is invalidated, it triggers a chain of invalidations that eventually clears most of the cache:

```python
# Product cache depends on category cache
def invalidate_category(category_id):
    cache.delete(f'category:{category_id}')
    # Invalidate all products in this category
    product_ids = db.get_product_ids_for_category(category_id)
    for pid in product_ids:
        invalidate_product(pid)

def invalidate_product(product_id):
    cache.delete(f'product:{product_id}')
    # Invalidate all collections containing this product
    collection_ids = db.get_collections_for_product(product_id)
    for cid in collection_ids:
        cache.delete(f'collection:{cid}')
    # Invalidate search results that include this product
    cache.delete(f'search:featured')
    cache.delete(f'search:bestsellers')

# Updating one category invalidates 500 products,
# which invalidates 2000 collections and all search caches
```

One category update triggers thousands of cache deletes, causing a spike of database load as everything is re-fetched.''', r'''<think>
This is a cache invalidation cascade or "cache avalanche." One change at the top of a dependency tree cascades through all dependent caches, effectively clearing a large portion of the cache. When users then request these pages, they all hit the database simultaneously.

Solutions:
1. Lazy invalidation instead of eager cascade
2. Event-based async invalidation
3. Reduce dependency depth
4. Use versioned keys instead of deleting
5. Stagger the invalidation
</think>

A cache invalidation cascade (or cache avalanche) occurs when a single change propagates through a dependency tree, invalidating thousands of cache entries. The resulting flood of cache misses overwhelms the database.

**The cascade in your system:**
```
1 category update
  -> 500 product invalidations
    -> 2000 collection invalidations
      -> search cache invalidations
= ~2500 cache deletes + ~2500 DB queries to repopulate
```

**Fix 1: Lazy invalidation with version numbers**

Instead of deleting cache entries, increment a version counter. Stale entries are detected lazily on read:

```python
def update_category(category_id, data):
    # Update DB
    db.update_category(category_id, data)

    # Increment category version (one operation, no cascade)
    cache.incr(f'category:{category_id}:version')

def get_product(product_id):
    cached = cache.get(f'product:{product_id}')
    if cached:
        cached = json.loads(cached)
        # Check if any dependencies have changed
        category_version = cache.get(f'category:{cached["category_id"]}:version')
        if str(category_version) == cached.get('category_version'):
            return cached['data']

    # Cache miss or stale -- rebuild
    product = db.get_product(product_id)
    category_version = cache.get(f'category:{product["category_id"]}:version')
    cache.setex(f'product:{product_id}', 300, json.dumps({
        'data': product,
        'category_version': str(category_version),
    }))
    return product
```

This turns eager cascade invalidation into lazy per-request validation. No thundering herd.

**Fix 2: Async invalidation with rate limiting**

```python
import asyncio
from collections import deque

invalidation_queue = deque()

def invalidate_category(category_id):
    cache.delete(f'category:{category_id}')
    # Queue product invalidations instead of doing them immediately
    product_ids = db.get_product_ids_for_category(category_id)
    for pid in product_ids:
        invalidation_queue.append(('product', pid))

async def invalidation_worker():
    """Process invalidations at a controlled rate."""
    while True:
        if invalidation_queue:
            type_, id_ = invalidation_queue.popleft()
            if type_ == 'product':
                cache.delete(f'product:{id_}')
                # Don't cascade further -- let collections expire naturally
            await asyncio.sleep(0.01)  # rate limit: 100 invalidations/second
        else:
            await asyncio.sleep(0.1)
```

**Fix 3: Reduce dependency depth**

```python
# Instead of cascading invalidations, use a flat structure
def invalidate_category(category_id):
    cache.delete(f'category:{category_id}')
    # Products will check category freshness on next read (lazy)
    # Collections will check product freshness on next read (lazy)
    # No cascade!

def get_collection(collection_id):
    cached = cache.get(f'collection:{collection_id}')
    if cached:
        data = json.loads(cached)
        # Freshness check: are the included products still current?
        if all_products_fresh(data['product_ids']):
            return data
    # Rebuild on cache miss or stale data
    return rebuild_collection(collection_id)
```

**Fix 4: Use short TTLs instead of explicit invalidation**

```python
# Categories change rarely: long TTL
cache.setex(f'category:{cid}', 3600, data)  # 1 hour

# Products change sometimes: medium TTL
cache.setex(f'product:{pid}', 300, data)  # 5 minutes

# Collections are computed: short TTL
cache.setex(f'collection:{cid}', 60, data)  # 1 minute

# Search results: very short TTL
cache.setex(f'search:featured', 30, data)  # 30 seconds

# No explicit invalidation needed -- short TTLs handle staleness
```

**Fix 5: Use cache tags for batch invalidation**

```python
# Tag cache entries with their dependencies
def cache_with_tags(key, value, ttl, tags):
    cache.setex(key, ttl, json.dumps(value))
    for tag in tags:
        cache.sadd(f'tag:{tag}', key)

# Invalidate by tag
def invalidate_tag(tag):
    keys = cache.smembers(f'tag:{tag}')
    if keys:
        cache.delete(*keys)
    cache.delete(f'tag:{tag}')

# Usage
cache_with_tags('product:42', product_data, 300,
    tags=[f'category:{product["category_id"]}', 'products'])

# Invalidating a category only deletes directly tagged keys
invalidate_tag(f'category:{category_id}')
```

**Prevention tips:**
- Prefer lazy validation over eager cascade invalidation
- Limit dependency depth to maximum 2 levels
- Use short TTLs for derived/computed cache entries
- Rate-limit invalidation processing to prevent database spikes
- Monitor the ratio of cache deletes to cache sets as a cascade indicator
- Use cache tags to group related entries for efficient batch invalidation'''),

    ("thinking/debugging", r'''We are using a stale-while-revalidate caching strategy, but users are seeing stale data for much longer than expected. Our setup:

```python
import time
import threading
import redis

r = redis.Redis()

def get_with_swr(key, fetch_fn, ttl=300, stale_ttl=600):
    """Serve stale data while revalidating in background."""
    cached = r.get(key)
    if cached:
        data = json.loads(cached)
        age = time.time() - data['timestamp']
        if age < ttl:
            return data['value']  # Fresh
        elif age < stale_ttl:
            # Stale but usable -- trigger background refresh
            threading.Thread(target=_refresh, args=(key, fetch_fn, ttl)).start()
            return data['value']  # Return stale data immediately
    # No cache or too stale -- synchronous fetch
    return _refresh(key, fetch_fn, ttl)

def _refresh(key, fetch_fn, ttl):
    value = fetch_fn()
    r.set(key, json.dumps({'value': value, 'timestamp': time.time()}))
    return value
```

Logs show the background refresh thread is running but data stays stale for 10+ minutes:

```
15:00:00 get_with_swr: key=dashboard:stats age=301s -> stale, refreshing in background
15:00:00 _refresh: key=dashboard:stats fetched new data, writing to cache
15:00:05 get_with_swr: key=dashboard:stats age=306s -> stale, refreshing in background
15:00:10 get_with_swr: key=dashboard:stats age=311s -> stale, refreshing in background
```

The refresh runs every time but the data never becomes "fresh" again. What is happening?''', r'''<think>
Let me trace through this carefully. The _refresh function runs and writes new data to Redis. But subsequent reads still see stale data with increasing age... That means the write is either failing silently or the read is seeing old data.

Wait -- look at the _refresh function: it calls `r.set(key, ...)` but it does NOT set a TTL on the key. That is fine, the TTL is managed by the age check. But the real issue is elsewhere.

Look at the JSON structure: `{'value': value, 'timestamp': time.time()}`. When the background thread calls _refresh, it creates a NEW timestamp. So subsequent reads should see age close to 0. But the logs show age is still increasing (301, 306, 311).

That means either: (1) the write is not completing before the next read, or (2) the write is using a different key, or (3) the connection is different (different Redis DB), or (4) -- wait, let me re-read the _refresh function.

Actually, the most likely cause: the background thread is calling `fetch_fn()` which takes a long time (maybe it hits a slow database), and during that time, multiple threads are spawned because each request sees stale data and spawns a new background thread. But eventually the write completes. Unless the thread is crashing silently.

But the log says "fetched new data, writing to cache" -- so it does complete. So why is the next read still stale?

Oh! I see it now. The _refresh function calls `r.set(key, json.dumps({'value': value, 'timestamp': time.time()}))`. The `time.time()` is called AFTER `fetch_fn()` returns. If fetch takes 5 seconds, timestamp is 5 seconds old. But the log shows age increasing linearly, which means the write IS happening... or wait, maybe there is a race condition.

Actually, the real bug: multiple background threads. Thread A starts refresh at t=301. Thread B starts refresh at t=306 (because A has not finished yet). Thread A finishes and writes timestamp=t+303 (fetch took 2 seconds). Thread B finishes and writes timestamp=t+308. But new thread C starts at t=311 because age is now 311 - 308 = 3 seconds... that would be fresh, not stale.

Let me reconsider. The actual bug is likely that `_refresh` is missing `import json` in the thread context, or the thread is failing silently. No, the log says it completed.

Wait -- I think the real issue is that `r.set` is overwriting with the new data, BUT if multiple threads are racing, an older thread could overwrite a newer thread's data. But that still would not explain permanently stale data.

Let me look again more carefully: the `_refresh` function does `r.set(key, json.dumps(...))`. The key variable -- is it captured correctly by the thread? `threading.Thread(target=_refresh, args=(key, fetch_fn, ttl))` -- yes, args are passed correctly.

Actually, I think the most likely issue is that the `json` module is not imported in the _refresh scope... but the get function uses `json.loads` so it must be imported.

Wait. The real bug: `r.set()` returns True on success but what if there is a pipeline or transaction that is not committing? No, `r.set()` is immediate.

I think the actual bug is subtle: the stale_ttl window. Once age exceeds stale_ttl (600s), it falls through to the synchronous path. But between ttl (300) and stale_ttl (600), EVERY request spawns a new thread. The threads complete and write, but the NEXT request spawns ANOTHER thread before reading the updated value. This is a thundering herd of refresh threads.

But the core bug causing "never fresh": I bet the issue is that multiple concurrent _refresh calls are racing and one is overwriting the other with OLDER data. Or... the simplest explanation: the background thread writes succeed, but the CALLING thread already returned the stale value, and the NEXT request reads before the write propagates.

No, Redis writes are synchronous and immediately visible to other connections.

The actual, most likely bug: the _refresh function does not set a Redis TTL, so the key persists forever. But that is by design since the code manages freshness via the timestamp field. So that is fine.

I think the real bug is: there is no deduplication of background refreshes. Every request in the stale window spawns a thread. And the thread might be erroring out silently (threads swallow exceptions by default in Python). The log line "fetched new data, writing to cache" might be from ONE successful refresh, but subsequent ones are failing. Without exception handling in the thread, errors are lost.

That is the bug: the thread has no try/except, and Python threads silently swallow exceptions. The first refresh works, subsequent ones may fail (e.g., DB connection pool exhausted from too many concurrent threads), and the errors are never logged.
</think>

There are two bugs working together to keep data permanently stale:

**Bug 1: No deduplication of background refresh threads**

Every request during the stale window (300-600 seconds) spawns a new background thread. With 100 requests/second, you get 100 threads all trying to refresh the same key simultaneously.

**Bug 2: Background threads silently swallow exceptions**

Python threads do not propagate exceptions to the main thread. When the thread pool or database connection pool is exhausted (from Bug 1 spawning too many threads), the refresh fails silently with no logging.

```python
# The thread crashes here but you never see the error:
def _refresh(key, fetch_fn, ttl):
    value = fetch_fn()  # Raises exception -- silently swallowed!
    r.set(key, json.dumps({'value': value, 'timestamp': time.time()}))
    return value
```

**The fix -- add deduplication and error handling:**

```python
import time
import threading
import json
import logging
import redis

r = redis.Redis()
_refresh_locks = {}
_refresh_locks_lock = threading.Lock()
logger = logging.getLogger(__name__)

def get_with_swr(key, fetch_fn, ttl=300, stale_ttl=600):
    cached = r.get(key)
    if cached:
        data = json.loads(cached)
        age = time.time() - data['timestamp']
        if age < ttl:
            return data['value']
        elif age < stale_ttl:
            _maybe_refresh_background(key, fetch_fn, ttl)
            return data['value']
    return _refresh_sync(key, fetch_fn, ttl)

def _maybe_refresh_background(key, fetch_fn, ttl):
    """Only spawn ONE background refresh per key."""
    with _refresh_locks_lock:
        if key in _refresh_locks:
            return  # Already refreshing -- skip
        _refresh_locks[key] = True

    def _do_refresh():
        try:
            value = fetch_fn()
            r.set(key, json.dumps({
                'value': value,
                'timestamp': time.time()
            }))
            logger.info(f"Background refresh completed for {key}")
        except Exception:
            logger.exception(f"Background refresh FAILED for {key}")
        finally:
            with _refresh_locks_lock:
                _refresh_locks.pop(key, None)

    threading.Thread(target=_do_refresh, daemon=True).start()

def _refresh_sync(key, fetch_fn, ttl):
    value = fetch_fn()
    r.set(key, json.dumps({
        'value': value,
        'timestamp': time.time()
    }))
    return value
```

**Key changes:**
1. A lock dict (`_refresh_locks`) ensures only one background refresh runs per key at a time
2. `try/except` in the thread body catches and LOGS errors instead of swallowing them
3. The lock is released in a `finally` block so a failed refresh does not permanently block future refreshes
4. Threads are marked `daemon=True` so they do not prevent process shutdown

**Prevention tips:**
- Always wrap thread target functions in try/except -- Python threads silently swallow exceptions
- Deduplicate background work using locks or a task queue
- Use `concurrent.futures.ThreadPoolExecutor` instead of raw threads to limit concurrency and capture exceptions
- Add metrics for background refresh success/failure rates
- Consider using Redis distributed locks (`SET key NX EX`) for deduplication across multiple app instances'''),
]
