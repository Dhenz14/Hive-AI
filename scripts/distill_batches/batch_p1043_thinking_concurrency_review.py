r"""Thinking-trace pairs: concurrency code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this concurrent code and identify issues:

```python
import threading
import time
from typing import Dict, List, Optional

class UserSessionManager:
    def __init__(self):
        self.sessions: Dict[str, dict] = {}
        self.active_count = 0

    def create_session(self, user_id: str, data: dict) -> str:
        session_id = f"sess_{user_id}_{int(time.time())}"
        self.sessions[session_id] = {
            "user_id": user_id,
            "data": data,
            "created_at": time.time(),
            "last_active": time.time()
        }
        self.active_count += 1
        return session_id

    def get_session(self, session_id: str) -> Optional[dict]:
        session = self.sessions.get(session_id)
        if session:
            session["last_active"] = time.time()
        return session

    def delete_session(self, session_id: str) -> bool:
        if session_id in self.sessions:
            del self.sessions[session_id]
            self.active_count -= 1
            return True
        return False

    def cleanup_expired(self, max_age: int = 3600):
        now = time.time()
        expired = []
        for sid, session in self.sessions.items():
            if now - session["last_active"] > max_age:
                expired.append(sid)

        for sid in expired:
            self.delete_session(sid)

    def get_user_sessions(self, user_id: str) -> List[dict]:
        return [
            s for s in self.sessions.values()
            if s["user_id"] == user_id
        ]

class ConnectionPool:
    def __init__(self, max_size=10):
        self.max_size = max_size
        self.pool = []
        self.in_use = []
        self.lock = threading.Lock()

    def get_connection(self):
        self.lock.acquire()
        if self.pool:
            conn = self.pool.pop()
            self.in_use.append(conn)
            self.lock.release()
            return conn

        if len(self.in_use) < self.max_size:
            conn = self._create_connection()
            self.in_use.append(conn)
            self.lock.release()
            return conn

        self.lock.release()
        while True:
            time.sleep(0.1)
            self.lock.acquire()
            if self.pool:
                conn = self.pool.pop()
                self.in_use.append(conn)
                self.lock.release()
                return conn
            self.lock.release()

    def release_connection(self, conn):
        self.lock.acquire()
        if conn in self.in_use:
            self.in_use.remove(conn)
            self.pool.append(conn)
        self.lock.release()

    def _create_connection(self):
        import psycopg2
        return psycopg2.connect("postgresql://user:pass@localhost/db")
```''', r'''<think>
Let me analyze these concurrent data structures for thread safety issues.

UserSessionManager:
1. No synchronization at all. self.sessions is a shared dict accessed from multiple threads without any locking.
2. self.active_count += 1 and -= 1 are not atomic operations. The read-modify-write cycle can be interleaved by other threads, leading to incorrect counts.
3. create_session: Two threads creating sessions simultaneously could write to self.sessions concurrently. While Python's GIL makes dict assignment somewhat safe, the active_count increment is definitely not safe.
4. get_session modifies session["last_active"] without locking. Two threads accessing the same session simultaneously could have race conditions.
5. delete_session: Check-then-delete is not atomic. Thread A checks "session in dict", Thread B deletes the session, Thread A tries to delete - KeyError. But actually, Thread A would just decrement active_count incorrectly since it passed the check.
6. cleanup_expired iterates over self.sessions.items() while other threads may be modifying the dict. In Python 3, this can raise RuntimeError: dictionary changed size during iteration.
7. Session IDs use time.time() which has limited resolution. Two sessions for the same user created in the same second get the same ID.

ConnectionPool:
1. get_connection has a spin-wait loop (while True: sleep 0.1) when pool is exhausted. This wastes CPU and is not responsive. Should use a Condition variable or Semaphore.
2. lock.acquire() without try/finally for lock.release(). If any code between acquire and release raises an exception, the lock is never released = deadlock.
3. If _create_connection raises an exception (database down), the lock has already been released (it's released before the spin loop starts), but the connection count is wrong since in_use was never appended.
4. release_connection uses self.in_use.remove(conn) which is O(n). With many connections, this is slow under lock.
5. No connection health checking. A connection that has been idle or has timed out will be returned to the caller.
6. No timeout on get_connection - waits forever if pool is exhausted and no connections are returned.
7. _create_connection has hardcoded connection string.
8. Pool never closes connections - no shutdown method.
</think>

## Code Review: Concurrent Code

### CRITICAL - UserSessionManager Has No Thread Safety
`UserSessionManager` has no synchronization mechanisms at all. Multiple threads reading and writing `self.sessions` and `self.active_count` concurrently causes race conditions:
- `active_count += 1` is a read-modify-write that is not atomic
- `delete_session` has a check-then-delete race
- `cleanup_expired` iterates `self.sessions.items()` while other threads modify the dict, raising `RuntimeError: dictionary changed size during iteration`

**Fix:** Add a lock to protect all shared state:
```python
class UserSessionManager:
    def __init__(self):
        self.sessions = {}
        self.active_count = 0
        self._lock = threading.Lock()

    def create_session(self, user_id, data):
        session_id = f"sess_{user_id}_{uuid.uuid4().hex[:8]}"
        with self._lock:
            self.sessions[session_id] = {...}
            self.active_count += 1
        return session_id
```

### CRITICAL - ConnectionPool Spin-Wait Wastes CPU
When no connections are available, `get_connection` enters a `while True: time.sleep(0.1)` loop. This wastes CPU cycles and has poor responsiveness (up to 100ms latency after a connection becomes available). With many waiting threads, performance degrades severely.

**Fix:** Use a `threading.Condition` or `threading.Semaphore`:
```python
class ConnectionPool:
    def __init__(self, max_size=10):
        self.semaphore = threading.Semaphore(max_size)
        self.pool = []
        self.lock = threading.Lock()

    def get_connection(self, timeout=30):
        if not self.semaphore.acquire(timeout=timeout):
            raise TimeoutError("Connection pool exhausted")
        with self.lock:
            if self.pool:
                return self.pool.pop()
        return self._create_connection()
```

### CRITICAL - Lock Not Released on Exception
`get_connection` uses `self.lock.acquire()` and `self.lock.release()` without try/finally. If `_create_connection()` raises an exception (database down, auth failure), the lock is never released. All subsequent threads attempting to acquire the lock will deadlock permanently.

**Fix:** Always use `with self.lock:` context manager:
```python
def get_connection(self):
    with self.lock:
        if self.pool:
            conn = self.pool.pop()
            self.in_use.append(conn)
            return conn
        if len(self.in_use) < self.max_size:
            conn = self._create_connection()
            self.in_use.append(conn)
            return conn
    # Wait for available connection using Condition
```

### HIGH - Session ID Collision
`f"sess_{user_id}_{int(time.time())}"` uses seconds-resolution timestamps. Two sessions for the same user created in the same second produce identical IDs, with the second overwriting the first.

**Fix:** Use UUID or a cryptographically random component:
```python
import uuid
session_id = f"sess_{uuid.uuid4().hex}"
```

### HIGH - No Connection Pool Timeout
`get_connection` waits indefinitely when the pool is exhausted. A slow query or leaked connection causes all threads to block forever.

**Fix:** Add a timeout parameter that raises an exception after the deadline.

### MEDIUM - No Connection Health Checking
Connections returned from the pool may have timed out, been closed by the server, or become stale. Using a dead connection causes query failures.

**Fix:** Validate connections before returning them:
```python
def get_connection(self):
    with self.lock:
        while self.pool:
            conn = self.pool.pop()
            if self._is_healthy(conn):
                self.in_use.append(conn)
                return conn
            conn.close()  # Discard dead connection
```

### MEDIUM - No Pool Shutdown
The pool has no `close()` or `shutdown()` method. When the application stops, connections are abandoned without proper cleanup, leaking database resources.

### LOW - O(n) Connection Lookup in release_connection
`self.in_use.remove(conn)` scans the entire list. Use a set instead of a list for O(1) removal.'''),

    ("thinking/code-review", r'''Review this async code and identify issues:

```python
import asyncio
import aiohttp
import time
from typing import List, Dict

class AsyncDataFetcher:
    def __init__(self, base_url: str, max_concurrent: int = 50):
        self.base_url = base_url
        self.max_concurrent = max_concurrent
        self.cache = {}
        self.session = None

    async def fetch_all(self, ids: List[str]) -> Dict[str, dict]:
        self.session = aiohttp.ClientSession()
        tasks = [self.fetch_one(id) for id in ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        await self.session.close()

        return {
            id: result for id, result in zip(ids, results)
            if not isinstance(result, Exception)
        }

    async def fetch_one(self, id: str) -> dict:
        if id in self.cache:
            return self.cache[id]

        url = f"{self.base_url}/items/{id}"
        async with self.session.get(url) as response:
            data = await response.json()
            self.cache[id] = data
            return data

    async def fetch_with_retry(self, id: str, max_retries: int = 3) -> dict:
        for attempt in range(max_retries):
            try:
                return await self.fetch_one(id)
            except Exception:
                if attempt < max_retries - 1:
                    time.sleep(1)  # Wait before retry
                else:
                    raise

    async def process_batch(self, ids: List[str]) -> List[dict]:
        results = []
        for id in ids:
            result = await self.fetch_one(id)
            results.append(result)
        return results

    async def stream_results(self, ids: List[str]):
        for id in ids:
            try:
                result = await self.fetch_one(id)
                yield result
            except Exception:
                continue

    def sync_fetch(self, id: str) -> dict:
        loop = asyncio.get_event_loop()
        return loop.run_until_complete(self.fetch_one(id))

class AsyncWorkerPool:
    def __init__(self, num_workers: int = 10):
        self.num_workers = num_workers
        self.queue = asyncio.Queue()
        self.results = []
        self.running = True

    async def worker(self):
        while self.running:
            try:
                task = await asyncio.wait_for(
                    self.queue.get(), timeout=1.0
                )
                result = await task()
                self.results.append(result)
                self.queue.task_done()
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"Worker error: {e}")

    async def run(self, tasks):
        for task in tasks:
            await self.queue.put(task)

        workers = [
            asyncio.create_task(self.worker())
            for _ in range(self.num_workers)
        ]

        await self.queue.join()
        self.running = False

        for w in workers:
            w.cancel()

        return self.results
```''', r'''<think>
Let me analyze this async code for concurrency issues and antipatterns.

AsyncDataFetcher:

1. time.sleep(1) in fetch_with_retry: This is CRITICAL. time.sleep blocks the entire event loop, freezing all concurrent tasks for 1 second. Must use await asyncio.sleep(1).

2. No concurrency limit: fetch_all creates tasks for ALL ids simultaneously. With 10,000 IDs, it creates 10,000 concurrent HTTP requests, overwhelming the target server and possibly exhausting file descriptors. max_concurrent is defined but never used.

3. Session lifecycle: session is created in fetch_all but could be None when fetch_one is called directly. If fetch_one is called before fetch_all, it raises AttributeError on self.session.get().

4. Cache is not async-safe: self.cache is a regular dict accessed from multiple coroutines. While Python's GIL prevents data corruption, there's a TOCTOU race: two coroutines could both miss the cache for the same ID, both fetch, both write to cache.

5. process_batch is sequential: It awaits each fetch_one sequentially in a loop. This defeats the purpose of async. Should use gather or a semaphore-limited pattern.

6. sync_fetch uses asyncio.get_event_loop() which is deprecated in Python 3.10+ and will fail if there's already a running loop (e.g., in Jupyter or within an async context).

7. fetch_all silently drops exceptions: The dict comprehension filters out exceptions from gather results. Failed fetches are invisible to the caller.

8. Session not closed on exception: If any task raises before await self.session.close(), the session is leaked.

9. No timeout on individual requests. A single slow request can block forever.

AsyncWorkerPool:

1. self.results is shared across all workers without synchronization. While list.append is thread-safe in CPython, this pattern is fragile.

2. Worker exceptions are caught and printed, but the failed task is silently discarded. No retry or error collection.

3. self.running is a boolean flag checked in a loop. When set to False after queue.join(), workers may not see the change immediately if they're in the middle of processing.

4. Workers are cancelled after queue.join(), but cancel doesn't necessarily stop them immediately. If a task is mid-execution, it might leave things in an inconsistent state.

5. No way to get errors from failed tasks.

6. The queue holds callable coroutine factories (task()), not coroutines. This is fine but underdocumented.
</think>

## Code Review: Async Code

### CRITICAL - time.sleep Blocks the Event Loop
`fetch_with_retry` uses `time.sleep(1)` which blocks the entire event loop, freezing ALL concurrent coroutines for 1 second per retry. In an async context, this is catastrophic -- hundreds of concurrent tasks all freeze.

**Fix:** Use `await asyncio.sleep(1)` instead.

### CRITICAL - No Concurrency Limit Despite max_concurrent Field
`fetch_all` creates tasks for all IDs simultaneously: `tasks = [self.fetch_one(id) for id in ids]`. With 10,000 IDs, this opens 10,000 concurrent HTTP connections, overwhelming the target server, exhausting file descriptors, and potentially crashing the application. The `max_concurrent` parameter is defined but never used.

**Fix:** Use a semaphore to limit concurrency:
```python
async def fetch_all(self, ids):
    semaphore = asyncio.Semaphore(self.max_concurrent)

    async def limited_fetch(id):
        async with semaphore:
            return await self.fetch_one(id)

    async with aiohttp.ClientSession() as session:
        self.session = session
        tasks = [limited_fetch(id) for id in ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    return {id: r for id, r in zip(ids, results) if not isinstance(r, Exception)}
```

### HIGH - Session Not Closed on Exception
If any task raises an unhandled exception before `await self.session.close()`, the session leaks, leaving open connections and sockets. The session should be managed with `async with`.

**Fix:**
```python
async def fetch_all(self, ids):
    async with aiohttp.ClientSession() as session:
        self.session = session
        # ... fetch logic
```

### HIGH - Exceptions Silently Dropped
The dict comprehension in `fetch_all` filters out all exceptions: `if not isinstance(result, Exception)`. Failed fetches are invisible to the caller. There is no logging, no error collection, and no way to know which IDs failed.

**Fix:** Collect and report failures:
```python
successes = {}
failures = {}
for id, result in zip(ids, results):
    if isinstance(result, Exception):
        failures[id] = str(result)
    else:
        successes[id] = result
return {"data": successes, "errors": failures}
```

### HIGH - process_batch Is Sequential
```python
for id in ids:
    result = await self.fetch_one(id)
```
This awaits each request one at a time, completely eliminating the benefit of async I/O. With 100 requests at 100ms each, this takes 10 seconds instead of ~100ms with concurrency.

**Fix:** Use `asyncio.gather` with a semaphore.

### HIGH - sync_fetch Uses Deprecated Pattern
`asyncio.get_event_loop().run_until_complete()` is deprecated in Python 3.10+ and raises a RuntimeError if called from within a running event loop (e.g., inside another async function, Jupyter notebook).

**Fix:** Use `asyncio.run()` for top-level calls or expose only the async interface:
```python
def sync_fetch(self, id):
    return asyncio.run(self.fetch_one(id))
```

### MEDIUM - Cache Race Condition
Two coroutines fetching the same ID simultaneously both miss the cache, both make HTTP requests, and both write to the cache. While not a data corruption issue, it wastes resources. Use an async lock per key or asyncio.Lock to serialize cache checks.

### MEDIUM - Worker Pool Silently Discards Failed Tasks
In `AsyncWorkerPool.worker`, exceptions are caught and printed to stdout. Failed tasks are not retried, not recorded, and not returned to the caller.

### LOW - No Request Timeout
`self.session.get(url)` has no timeout parameter. A single slow endpoint can block a coroutine indefinitely.

**Fix:** `async with self.session.get(url, timeout=aiohttp.ClientTimeout(total=30)):`'''),

    ("thinking/code-review", r'''Review this thread-safe data structure and identify issues:

```python
import threading
import time
from collections import OrderedDict
from typing import Any, Optional

class ThreadSafeCache:
    def __init__(self, max_size: int = 1000, ttl: int = 300):
        self.max_size = max_size
        self.ttl = ttl
        self.cache = OrderedDict()
        self.lock = threading.Lock()
        self.hits = 0
        self.misses = 0

        self._cleanup_thread = threading.Thread(
            target=self._periodic_cleanup, daemon=True
        )
        self._cleanup_thread.start()

    def get(self, key: str) -> Optional[Any]:
        with self.lock:
            if key in self.cache:
                value, timestamp = self.cache[key]
                if time.time() - timestamp <= self.ttl:
                    self.cache.move_to_end(key)
                    self.hits += 1
                    return value
                else:
                    del self.cache[key]

            self.misses += 1
            return None

    def set(self, key: str, value: Any) -> None:
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = (value, time.time())

            while len(self.cache) > self.max_size:
                self.cache.popitem(last=False)

    def delete(self, key: str) -> bool:
        with self.lock:
            if key in self.cache:
                del self.cache[key]
                return True
            return False

    def get_or_set(self, key: str, factory) -> Any:
        value = self.get(key)
        if value is not None:
            return value

        new_value = factory()
        self.set(key, new_value)
        return new_value

    def _periodic_cleanup(self):
        while True:
            time.sleep(60)
            self._cleanup_expired()

    def _cleanup_expired(self):
        with self.lock:
            now = time.time()
            expired = [
                k for k, (v, ts) in self.cache.items()
                if now - ts > self.ttl
            ]
            for key in expired:
                del self.cache[key]

    def stats(self):
        total = self.hits + self.misses
        hit_rate = self.hits / total if total > 0 else 0
        return {
            "size": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": hit_rate
        }

    def clear(self):
        self.cache.clear()
        self.hits = 0
        self.misses = 0
```''', r'''<think>
Let me analyze this thread-safe cache implementation.

get_or_set race condition:
This is the most significant issue. get_or_set calls self.get() (which acquires and releases the lock), then if the value is None, calls factory() and self.set() (which acquires and releases the lock). Between get() and set(), another thread could set the same key. Two threads could both call factory() for the same key simultaneously, resulting in duplicate work. This is the classic TOCTOU (Time of Check to Time of Use) problem.

Also, if factory() returns None, the get_or_set method treats it as a cache miss and re-executes factory() on every call. This is because get() returns None for both "not found" and "found but expired."

clear() is not thread-safe:
clear() modifies self.cache, self.hits, and self.misses without acquiring the lock. Another thread could be reading cache in get() while clear() empties it.

stats() is not thread-safe:
stats() reads self.hits, self.misses, and len(self.cache) without the lock. These reads are not atomic - hits and misses could be inconsistent with each other.

_periodic_cleanup runs every 60 seconds regardless:
- No way to stop the cleanup thread (no stop flag, daemon thread just gets killed)
- If cleanup takes a long time (large cache), it holds the lock, blocking all get/set operations

Cache value equality to None:
get() returns None for both "key not in cache" and "key expired." If a caller intentionally caches None as a value, get() returns None and the caller cannot tell if it was a hit or miss. This also affects get_or_set as mentioned above.

Minor issues:
- set() does not check if value being stored is a deep copy or reference. Mutable objects stored in cache can be modified externally, corrupting cached data.
- No max TTL validation (could pass negative TTL)
- OrderedDict operations under lock are O(1) for most operations, which is good
- The daemon thread has no exception handling - if _cleanup_expired raises, the cleanup thread dies silently

Actually, looking more carefully at the locking:
- get() acquires lock - good
- set() acquires lock - good
- delete() acquires lock - good
- get_or_set - the individual get and set are locked, but the compound operation is not
- stats() - not locked
- clear() - not locked
</think>

## Code Review: Thread-Safe Cache

### CRITICAL - get_or_set Has TOCTOU Race Condition
`get_or_set` calls `self.get()` (acquires lock, checks cache, releases lock) and then calls `factory()` and `self.set()` as separate operations. Between get() releasing the lock and set() acquiring it, another thread can set the same key. Two threads both miss the cache for the same key, both execute `factory()`, and both write the result -- causing duplicate work and potentially duplicate side effects if factory() is not idempotent.

**Fix:** Make the entire get-or-create operation atomic:
```python
def get_or_set(self, key: str, factory) -> Any:
    with self.lock:
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp <= self.ttl:
                self.cache.move_to_end(key)
                self.hits += 1
                return value
            del self.cache[key]
        self.misses += 1

    # Execute factory outside the lock to avoid holding
    # the lock during potentially slow operations
    new_value = factory()

    with self.lock:
        # Check again in case another thread set it
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp <= self.ttl:
                return value
        self.cache[key] = (new_value, time.time())
        while len(self.cache) > self.max_size:
            self.cache.popitem(last=False)

    return new_value
```

### HIGH - clear() and stats() Not Thread-Safe
`clear()` modifies `self.cache`, `self.hits`, and `self.misses` without acquiring the lock. A concurrent `get()` could be iterating the cache while `clear()` empties it. Similarly, `stats()` reads these values without the lock, potentially seeing inconsistent snapshots.

**Fix:**
```python
def clear(self):
    with self.lock:
        self.cache.clear()
        self.hits = 0
        self.misses = 0

def stats(self):
    with self.lock:
        total = self.hits + self.misses
        return {
            "size": len(self.cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": self.hits / total if total > 0 else 0
        }
```

### HIGH - None Values Cannot Be Cached
`get()` returns `None` for both "key not found" and "key expired." If `factory()` returns `None` as a legitimate value, `get_or_set` will re-execute the factory on every call, defeating the cache entirely.

**Fix:** Use a sentinel value to distinguish cache misses:
```python
_MISSING = object()

def get(self, key: str, default=_MISSING) -> Any:
    with self.lock:
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp <= self.ttl:
                self.cache.move_to_end(key)
                self.hits += 1
                return value
            del self.cache[key]
        self.misses += 1
        return default
```

### MEDIUM - Cleanup Thread Has No Error Handling
If `_cleanup_expired` raises an unexpected exception, the daemon thread dies silently. No further cleanup runs, and expired entries accumulate indefinitely.

**Fix:**
```python
def _periodic_cleanup(self):
    while True:
        time.sleep(60)
        try:
            self._cleanup_expired()
        except Exception as e:
            logging.error(f"Cache cleanup failed: {e}")
```

### MEDIUM - Cleanup Blocks All Operations
`_cleanup_expired` holds the lock while iterating the entire cache and deleting expired entries. For a large cache, this blocks all `get()` and `set()` operations for the duration. In a high-throughput system, this causes periodic latency spikes every 60 seconds.

**Fix:** Limit cleanup to a bounded number of entries per cycle, or use a separate data structure to track expiry times.

### MEDIUM - Mutable Values Can Be Corrupted
Stored values are not copied. If a caller stores a dict and then modifies it externally, the cached value changes too. This leads to hard-to-debug inconsistencies.

**Fix:** Use `copy.deepcopy` in both get and set, or document that callers must not modify returned values.

### LOW - No Graceful Shutdown
The cleanup thread runs forever as a daemon. There is no way to stop it gracefully, which can cause issues during testing or application shutdown.'''),

    ("thinking/code-review", r'''Review this producer-consumer implementation and identify issues:

```python
import threading
import queue
import time
import logging
from typing import Callable, List, Any

logger = logging.getLogger(__name__)

class TaskQueue:
    def __init__(self, num_workers: int = 4, max_queue_size: int = 0):
        self.queue = queue.Queue(maxsize=max_queue_size)
        self.num_workers = num_workers
        self.workers: List[threading.Thread] = []
        self.results = []
        self.errors = []
        self.processed_count = 0
        self.lock = threading.Lock()
        self._started = False

    def start(self):
        if self._started:
            return
        self._started = True
        for i in range(self.num_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"worker-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)

    def submit(self, task: Callable, *args, **kwargs):
        if not self._started:
            self.start()
        self.queue.put((task, args, kwargs))

    def _worker_loop(self):
        while True:
            task, args, kwargs = self.queue.get()
            try:
                result = task(*args, **kwargs)
                with self.lock:
                    self.results.append(result)
                    self.processed_count += 1
            except Exception as e:
                logger.error(f"Task failed: {e}")
                self.errors.append({
                    "error": str(e),
                    "task": str(task),
                    "args": str(args)
                })
            finally:
                self.queue.task_done()

    def wait_for_completion(self, timeout=None):
        self.queue.join()

    def get_results(self):
        return self.results.copy()

    def shutdown(self, wait=True):
        if wait:
            self.queue.join()
        self._started = False

    def get_stats(self):
        return {
            "queue_size": self.queue.qsize(),
            "processed": self.processed_count,
            "errors": len(self.errors),
            "workers": len(self.workers),
        }

class BatchProcessor:
    def __init__(self, batch_size: int = 100, flush_interval: int = 5):
        self.batch_size = batch_size
        self.flush_interval = flush_interval
        self.buffer = []
        self.processor = None
        self.lock = threading.Lock()
        self._timer = None

    def set_processor(self, processor: Callable):
        self.processor = processor

    def add(self, item: Any):
        self.buffer.append(item)
        if len(self.buffer) >= self.batch_size:
            self.flush()

    def flush(self):
        if not self.buffer:
            return
        batch = self.buffer
        self.buffer = []
        try:
            self.processor(batch)
        except Exception as e:
            logger.error(f"Batch processing failed: {e}")
            self.buffer = batch + self.buffer

    def start_timer(self):
        self._timer = threading.Timer(self.flush_interval, self._timed_flush)
        self._timer.daemon = True
        self._timer.start()

    def _timed_flush(self):
        self.flush()
        self.start_timer()

    def stop(self):
        if self._timer:
            self._timer.cancel()
        self.flush()
```''', r'''<think>
Let me analyze both classes for concurrency issues.

TaskQueue:

1. shutdown does not actually stop workers. It sets self._started = False but the workers are in `while True` loops that never check this flag. Daemon threads will only stop when the main thread exits. If shutdown(wait=False) is called, workers continue running.

2. self.errors.append() in the except block is NOT protected by the lock. While self.results.append() is under self.lock, errors are appended without synchronization. Multiple threads can corrupt the errors list.

3. wait_for_completion ignores the timeout parameter. It calls self.queue.join() which blocks forever. The timeout parameter is accepted but never used, which is misleading.

4. get_results returns self.results.copy() but this is a shallow copy. If results contain mutable objects, the caller can modify them.

5. processed_count reads in get_stats are not locked. Minor issue due to GIL but not strictly thread-safe.

6. If start() is called multiple times (despite the _started check), the check-and-set on _started is not atomic. Two threads calling start() simultaneously could both see _started=False and create duplicate workers.

7. No mechanism to propagate worker exceptions to the caller. Errors are silently collected in self.errors.

8. max_queue_size=0 means unbounded queue by default. A fast producer can exhaust memory.

BatchProcessor:

1. add() and flush() have NO thread safety:
   - self.buffer.append(item) without lock
   - len(self.buffer) >= self.batch_size check without lock
   - flush() reads and replaces self.buffer without lock
   - Two threads calling add() simultaneously can corrupt the buffer

2. flush() has a race condition even within itself:
   - batch = self.buffer; self.buffer = [] is not atomic
   - Another thread could add an item between these two lines, and that item would be lost

3. On error in flush():
   - self.buffer = batch + self.buffer tries to prepend failed batch
   - But if another thread added items to self.buffer between the assignment and the error, those items are placed after the failed batch, disrupting order
   - Also, this means the failed batch will be retried on next flush, potentially causing infinite retry loops

4. _timed_flush calls flush() then start_timer() recursively. If flush() takes longer than flush_interval, flushes pile up. Also, the timer restarts after flush completes, so the actual interval is flush_interval + flush_duration.

5. start_timer creates a new Timer on each call without canceling the old one. If called multiple times, multiple timers run concurrently.

6. stop() calls flush() but flush() is not thread-safe. If the timer fires simultaneously with stop(), both could flush.
</think>

## Code Review: Producer-Consumer Implementation

### CRITICAL - BatchProcessor Has No Thread Safety
The entire `BatchProcessor` class is not thread-safe. `self.buffer` is modified by `add()`, `flush()`, and `_timed_flush()` from different threads without any locking:
- `self.buffer.append(item)` in `add()` can race with `batch = self.buffer; self.buffer = []` in `flush()`
- Items can be lost between the buffer swap lines
- `len(self.buffer) >= self.batch_size` can trigger a flush while another flush is in progress

**Fix:** Protect all buffer operations with the lock that already exists but is never used:
```python
def add(self, item):
    with self.lock:
        self.buffer.append(item)
        if len(self.buffer) >= self.batch_size:
            self._flush_locked()

def flush(self):
    with self.lock:
        self._flush_locked()

def _flush_locked(self):
    if not self.buffer:
        return
    batch = self.buffer
    self.buffer = []
    try:
        self.processor(batch)
    except Exception as e:
        logger.error(f"Batch processing failed: {e}")
        self.buffer = batch + self.buffer
```

### CRITICAL - TaskQueue.shutdown Does Not Stop Workers
`shutdown` sets `self._started = False` but workers run `while True` loops that never check this flag. Workers continue consuming from the queue indefinitely after shutdown. The shutdown method gives a false impression that workers have stopped.

**Fix:** Use a poison pill pattern:
```python
_SHUTDOWN = object()

def shutdown(self, wait=True):
    if wait:
        self.queue.join()
    for _ in self.workers:
        self.queue.put((_SHUTDOWN, (), {}))
    for w in self.workers:
        w.join(timeout=5)
    self._started = False

def _worker_loop(self):
    while True:
        task, args, kwargs = self.queue.get()
        if task is self._SHUTDOWN:
            self.queue.task_done()
            break
        # ... process task
```

### HIGH - self.errors Appended Without Lock
In `_worker_loop`, `self.results.append(result)` is protected by `self.lock`, but `self.errors.append(...)` is not. Multiple worker threads appending to `self.errors` simultaneously can corrupt the list.

**Fix:** Protect error appending with the same lock:
```python
except Exception as e:
    logger.error(f"Task failed: {e}")
    with self.lock:
        self.errors.append({...})
```

### HIGH - wait_for_completion Ignores Timeout
The `timeout` parameter is accepted but never used. `self.queue.join()` blocks indefinitely. A caller passing `timeout=30` expects the method to return after 30 seconds, but it blocks forever if tasks never complete.

**Fix:** Implement timeout support:
```python
def wait_for_completion(self, timeout=None):
    self.queue.all_tasks_done.acquire()
    try:
        if self.queue.unfinished_tasks:
            self.queue.all_tasks_done.wait(timeout=timeout)
    finally:
        self.queue.all_tasks_done.release()
```

### HIGH - Failed Batch Retried Infinitely
In `BatchProcessor.flush`, when `processor(batch)` fails, the batch is prepended back to the buffer: `self.buffer = batch + self.buffer`. On the next flush (via timer or size trigger), the same batch is retried. If the failure is permanent (invalid data, not transient), it blocks all subsequent batches forever.

**Fix:** Add a retry counter and dead-letter queue:
```python
if retry_count < self.max_retries:
    self.buffer = batch + self.buffer
else:
    logger.error(f"Dropping batch after {self.max_retries} retries")
    self.dead_letter.extend(batch)
```

### MEDIUM - Unbounded Queue Default
`max_queue_size=0` creates an unbounded queue. A fast producer can submit tasks faster than workers process them, causing unbounded memory growth.

### MEDIUM - Timer Accumulation
`start_timer` creates a new `threading.Timer` without canceling the previous one. If called multiple times (or if the timer fires while a manual flush is in progress), multiple concurrent timers schedule overlapping flushes.

### LOW - Task Arguments Logged as Strings
`self.errors.append({"args": str(args)})` converts arguments to strings. For large objects, this creates enormous error records. For sensitive data, this logs it in plaintext.'''),

    ("thinking/code-review", r'''Review this deadlock-prone code and identify issues:

```python
import threading
import time
import logging

logger = logging.getLogger(__name__)

class BankAccount:
    def __init__(self, account_id: str, balance: float):
        self.account_id = account_id
        self.balance = balance
        self.lock = threading.Lock()
        self.transaction_log = []

    def deposit(self, amount: float):
        with self.lock:
            self.balance += amount
            self.transaction_log.append(
                {"type": "deposit", "amount": amount, "time": time.time()}
            )

    def withdraw(self, amount: float) -> bool:
        with self.lock:
            if self.balance >= amount:
                self.balance -= amount
                self.transaction_log.append(
                    {"type": "withdraw", "amount": amount, "time": time.time()}
                )
                return True
            return False

    def get_balance(self) -> float:
        return self.balance

class TransferService:
    def __init__(self):
        self.accounts = {}
        self.global_lock = threading.Lock()

    def register_account(self, account: BankAccount):
        self.accounts[account.account_id] = account

    def transfer(self, from_id: str, to_id: str, amount: float) -> bool:
        from_account = self.accounts[from_id]
        to_account = self.accounts[to_id]

        with from_account.lock:
            if from_account.balance < amount:
                return False

            with to_account.lock:
                from_account.balance -= amount
                to_account.balance += amount

                from_account.transaction_log.append({
                    "type": "transfer_out",
                    "amount": amount,
                    "to": to_id,
                    "time": time.time()
                })
                to_account.transaction_log.append({
                    "type": "transfer_in",
                    "amount": amount,
                    "from": from_id,
                    "time": time.time()
                })
        return True

    def batch_transfer(self, transfers: list):
        results = []
        threads = []

        for from_id, to_id, amount in transfers:
            t = threading.Thread(
                target=lambda f, t, a: results.append(
                    self.transfer(f, t, a)
                ),
                args=(from_id, to_id, amount)
            )
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        return results

    def get_total_balance(self):
        total = 0
        for account in self.accounts.values():
            total += account.balance
        return total

    def audit(self):
        report = {}
        for aid, account in self.accounts.items():
            with account.lock:
                report[aid] = {
                    "balance": account.balance,
                    "transactions": len(account.transaction_log)
                }
        return report
```''', r'''<think>
Let me analyze this banking code for deadlock and concurrency issues.

DEADLOCK in transfer():
This is the classic deadlock scenario. transfer() acquires from_account.lock first, then to_account.lock. If Thread A transfers from account 1 to account 2, and Thread B simultaneously transfers from account 2 to account 1:
- Thread A acquires lock on account 1
- Thread B acquires lock on account 2
- Thread A tries to acquire lock on account 2 (blocked - Thread B holds it)
- Thread B tries to acquire lock on account 1 (blocked - Thread A holds it)
DEADLOCK. Neither thread can proceed.

The fix is lock ordering: always acquire locks in a consistent order (e.g., by account_id).

get_balance() is not thread-safe:
Returns self.balance without acquiring the lock. While this is a single attribute read (atomish in CPython due to GIL), it can return a stale or inconsistent value during a transfer.

get_total_balance() is not atomic:
Reads balances from all accounts without holding any locks. During the iteration, transfers can move money between accounts. The total could include money that was counted in the source account before transfer and again in the destination account after transfer (double-counting), or exclude money that was deducted from source but not yet added to destination.

audit() can deadlock:
audit() iterates over all accounts and locks each one individually. If a transfer is holding one account lock and waiting for another that audit has locked, deadlock occurs. The audit method acquires locks in dictionary iteration order, which may differ from the transfer lock ordering.

batch_transfer() issues:
- The lambda in the thread creation captures variables by reference, not by value. Since from_id, to_id, and amount change in the loop, all threads may use the values from the last iteration. Wait, actually the lambda uses args=(from_id, to_id, amount) so the values are passed correctly via args. But the lambda itself captures f, t, a as parameters, so this should be fine.
- Actually looking more carefully: lambda f, t, a: results.append(self.transfer(f, t, a)), args=(from_id, to_id, amount). This should work correctly because the values are bound via args.
- results.append() from multiple threads is not strictly thread-safe (though CPython GIL makes it work in practice).
- Multiple concurrent transfers can deadlock (as described above).
- Results order does not correspond to input order because threads complete in arbitrary order.

Float precision:
Using float for monetary values. 0.1 + 0.2 != 0.3 in floating point. Should use Decimal.

Transaction atomicity:
If the system crashes between from_account.balance -= amount and to_account.balance += amount, money disappears. In-memory operations are not durable. This is a fundamental design issue for a banking system, though for an in-memory implementation it's somewhat expected.
</think>

## Code Review: Bank Transfer System

### CRITICAL - Classic Deadlock in transfer()
`transfer` acquires `from_account.lock` then `to_account.lock`. When Thread A transfers from account 1 to 2 while Thread B transfers from account 2 to 1 simultaneously:
1. Thread A holds lock(account1), waits for lock(account2)
2. Thread B holds lock(account2), waits for lock(account1)
Both threads block permanently -- deadlock.

**Fix:** Always acquire locks in a consistent order (e.g., by account ID):
```python
def transfer(self, from_id, to_id, amount):
    from_account = self.accounts[from_id]
    to_account = self.accounts[to_id]

    # Consistent lock ordering prevents deadlock
    first, second = sorted(
        [from_account, to_account],
        key=lambda a: a.account_id
    )

    with first.lock:
        with second.lock:
            if from_account.balance < amount:
                return False
            from_account.balance -= amount
            to_account.balance += amount
            # ... log transactions
    return True
```

### CRITICAL - audit() Can Also Deadlock
`audit` iterates accounts and locks each one individually. If it holds account A's lock while a transfer holds account B's lock waiting for account A, deadlock occurs. The audit lock acquisition order depends on dictionary iteration order, which may conflict with transfer lock ordering.

**Fix:** Use the same consistent lock ordering, or use a global lock for audit:
```python
def audit(self):
    sorted_accounts = sorted(
        self.accounts.items(), key=lambda x: x[0]
    )
    locks = [acc.lock for _, acc in sorted_accounts]
    # Acquire all locks in order
    for lock in locks:
        lock.acquire()
    try:
        report = {}
        for aid, account in sorted_accounts:
            report[aid] = {
                "balance": account.balance,
                "transactions": len(account.transaction_log)
            }
        return report
    finally:
        for lock in reversed(locks):
            lock.release()
```

### HIGH - get_total_balance Is Not Atomic
`get_total_balance` reads balances from all accounts without holding any locks. During iteration, a transfer can deduct from account A (already summed) and add to account B (not yet summed), making the total appear lower than it should be. Or the reverse -- double-counting money.

**Fix:** Hold all account locks simultaneously (with consistent ordering) or use a snapshot:
```python
def get_total_balance(self):
    with self.global_lock:
        return sum(a.balance for a in self.accounts.values())
```

### HIGH - batch_transfer Triggers Multiple Concurrent Deadlock-Prone Transfers
`batch_transfer` spawns threads that call `transfer` concurrently. With the existing deadlock vulnerability, this is almost guaranteed to deadlock with enough transfers between overlapping accounts.

### MEDIUM - Float for Monetary Values
`balance: float` causes rounding errors in financial calculations. `0.1 + 0.2` does not equal `0.3` in floating point.

**Fix:** Use `decimal.Decimal`:
```python
from decimal import Decimal
balance: Decimal = Decimal("0.00")
```

### MEDIUM - get_balance Not Synchronized
`get_balance` reads `self.balance` without acquiring the lock. While CPython's GIL makes this safe for simple reads, it can return a value mid-transfer where the source account has been debited but the destination has not been credited.

### MEDIUM - batch_transfer Results Not Ordered
Results are appended by threads that complete in arbitrary order. The results list does not correspond to the input transfer list order. The caller cannot tell which transfers succeeded and which failed.

**Fix:** Use indexed results:
```python
results = [None] * len(transfers)
def run(index, f, t, a):
    results[index] = self.transfer(f, t, a)
```

### LOW - Transaction Log Grows Unboundedly
Each account's `transaction_log` list grows without limit. For long-running systems, this is a memory leak. Consider capping the log size or persisting to storage.'''),
]
