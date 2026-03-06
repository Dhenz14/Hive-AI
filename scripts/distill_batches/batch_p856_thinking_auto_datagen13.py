"""Phase 4A: Self-Improvement -- Training Data Generation (Part 13)

Generate and evaluate training pairs for concurrency and threading topics.
Each answer creates 3 graded training pairs with quality analysis.
"""

PAIRS = [
    (
        "thinking/auto-datagen-concurrency-basics",
        r'''Generate 3 high-quality training pairs that teach concurrency fundamentals in Python (threads vs processes vs async). For each pair, explain why it's effective training data.''',
        r'''<think>
Concurrency is one of the most misunderstood topics:
1. Threads vs processes vs async -- when to use which
2. The GIL and its actual implications
3. Common pitfalls: race conditions, deadlocks

Progression: understanding the GIL -> choosing the right model -> avoiding pitfalls
</think>

Here are 3 training pairs for concurrency fundamentals:

**Pair 1 (Beginner):**
```
Q: What is the difference between threads, processes, and async in Python? When should I use each one?

A: Each concurrency model solves a different type of problem:

**Threads** -- shared memory, limited by the GIL for CPU work:
```python
import threading

def download(url):
    response = requests.get(url)
    return response.text

# Good for I/O-bound tasks (network, disk)
threads = [threading.Thread(target=download, args=(url,)) for url in urls]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

**Processes** -- separate memory, true parallelism:
```python
from multiprocessing import Pool

def compute_hash(data):
    return hashlib.sha256(data).hexdigest()

# Good for CPU-bound tasks (computation, hashing, image processing)
with Pool(4) as pool:
    results = pool.map(compute_hash, data_chunks)
```

**Async** -- single thread, cooperative multitasking:
```python
import asyncio, aiohttp

async def fetch(session, url):
    async with session.get(url) as resp:
        return await resp.text()

# Good for high-concurrency I/O (thousands of connections)
async def main():
    async with aiohttp.ClientSession() as session:
        tasks = [fetch(session, url) for url in urls]
        results = await asyncio.gather(*tasks)
```

**Decision guide:**
| Task type | Best model | Why |
|-----------|-----------|-----|
| Download 100 files | Threads or Async | I/O-bound, GIL not a problem |
| Process 100 images | Multiprocessing | CPU-bound, needs true parallelism |
| Handle 10,000 websockets | Async | High concurrency, low CPU per task |
| Simple script, 3 tasks | Threading | Easiest to add to existing code |
```

**Why this is effective:** Gives a concrete decision framework instead of abstract explanations. Each model has a code example the learner can run immediately.

**Pair 2 (Intermediate):**
```
Q: I have a Python web scraper that downloads 500 pages sequentially and it takes 10 minutes. How do I speed it up with threads, and what pitfalls should I watch for?

A: Here is a thread pool approach with proper error handling:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import requests

results = {}
results_lock = threading.Lock()
failed = []

def scrape_page(url):
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return url, response.text
    except requests.RequestException as e:
        return url, None

# Use ThreadPoolExecutor for managed thread pools
with ThreadPoolExecutor(max_workers=20) as executor:
    futures = {executor.submit(scrape_page, url): url for url in urls}

    for future in as_completed(futures):
        url, content = future.result()
        if content:
            with results_lock:
                results[url] = content
        else:
            failed.append(url)

print(f"Scraped {len(results)}, failed {len(failed)}")
```

**Pitfalls to watch:**
1. Too many threads -- 20-50 is usually optimal, not 500
2. No timeout -- one hung connection blocks a thread forever
3. Shared mutable state without locks -- race condition
4. No error handling -- one exception kills the thread silently
5. Rate limiting -- you might get IP-banned at 500 concurrent requests
```

**Why this is effective:** Starts from a real problem (slow scraper), shows production-quality code with locks and error handling, and explicitly calls out the pitfalls.

**Pair 3 (Advanced):**
```
Q: Explain the Python GIL. Does it mean Python threads are useless? When does the GIL actually matter and when does it not?

A: The GIL (Global Interpreter Lock) is a mutex that protects Python object reference counts. Only one thread can execute Python bytecode at a time.

**When the GIL DOES NOT matter (threads work fine):**
- Network I/O: the GIL is released during socket operations
- File I/O: the GIL is released during disk reads/writes
- C extensions: NumPy, PIL release the GIL during computation
- Sleep/wait: the GIL is released during time.sleep()

**When the GIL DOES matter (threads don't help):**
- Pure Python computation (loops, math, string processing)
- CPU-bound code that doesn't call C extensions

**Proof:**
```python
import threading, time

def cpu_work():
    total = 0
    for i in range(10_000_000):
        total += i * i

# Sequential: ~2.0 seconds
start = time.time()
cpu_work()
cpu_work()
print(f"Sequential: {time.time() - start:.1f}s")

# Threaded: ~2.0 seconds (NO speedup due to GIL)
start = time.time()
t1 = threading.Thread(target=cpu_work)
t2 = threading.Thread(target=cpu_work)
t1.start(); t2.start()
t1.join(); t2.join()
print(f"Threaded: {time.time() - start:.1f}s")

# Multiprocessing: ~1.0 seconds (true parallelism)
from multiprocessing import Process
start = time.time()
p1 = Process(target=cpu_work)
p2 = Process(target=cpu_work)
p1.start(); p2.start()
p1.join(); p2.join()
print(f"Multiprocessing: {time.time() - start:.1f}s")
```

**Summary:** Python threads are NOT useless. They are excellent for I/O-bound work. They are useless for CPU-bound pure Python work. Know the difference.
```

**Why this is effective:** Demolishes the common myth that "Python threads are useless" with a concrete benchmark the learner can run themselves. Shows exactly when the GIL matters and when it does not.'''
    ),
    (
        "thinking/auto-datagen-race-conditions",
        r'''Generate 3 high-quality training pairs that teach race condition detection and prevention. For each pair, explain why it's effective training data.''',
        r'''<think>
Race conditions are subtle and hard to teach:
1. The bug only appears intermittently
2. Students need to understand WHY it happens (interleaving)
3. Multiple prevention strategies: locks, atomics, queues, immutability

Progression: identifying a race -> using locks -> lock-free alternatives
</think>

Here are 3 training pairs for race condition detection and prevention:

**Pair 1 (Beginner):**
```
Q: My multi-threaded counter gives wrong results. Sometimes I get 9,997 instead of 10,000. What is happening?

```python
import threading

counter = 0

def increment():
    global counter
    for _ in range(1000):
        counter += 1

threads = [threading.Thread(target=increment) for _ in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()
print(counter)  # Expected: 10000, Got: 9973 (varies each run)
```

A: You have a **race condition**. `counter += 1` is NOT atomic -- it is actually three operations:

```
Thread A: read counter (value: 5)
Thread B: read counter (value: 5)      <-- both read 5
Thread A: compute 5 + 1 = 6
Thread B: compute 5 + 1 = 6            <-- both compute 6
Thread A: write counter = 6
Thread B: write counter = 6            <-- one increment is LOST
```

**Fix with a lock:**
```python
import threading

counter = 0
lock = threading.Lock()

def increment():
    global counter
    for _ in range(1000):
        with lock:           # Only one thread at a time
            counter += 1     # Now this is safe

threads = [threading.Thread(target=increment) for _ in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()
print(counter)  # Always 10000
```
```

**Why this is effective:** Shows the exact interleaving that causes the bug, making the invisible problem visible. The fix is simple and directly addresses the cause.

**Pair 2 (Intermediate):**
```
Q: I am using locks to protect shared state, but my program sometimes freezes. Two threads seem to be waiting for each other. What is happening and how do I fix it?

A: You have a **deadlock**. Two threads each hold a lock the other needs:

```python
# DEADLOCK EXAMPLE
lock_a = threading.Lock()
lock_b = threading.Lock()

def thread_1():
    with lock_a:              # Acquires lock_a
        time.sleep(0.1)       # Small delay makes deadlock likely
        with lock_b:          # Waits for lock_b (held by thread_2)
            print("Thread 1 done")

def thread_2():
    with lock_b:              # Acquires lock_b
        time.sleep(0.1)
        with lock_a:          # Waits for lock_a (held by thread_1)
            print("Thread 2 done")

# FROZEN -- both threads waiting forever
```

**Fix 1: Always acquire locks in the same order:**
```python
def thread_1():
    with lock_a:
        with lock_b:
            print("Thread 1 done")

def thread_2():
    with lock_a:          # Same order as thread_1
        with lock_b:
            print("Thread 2 done")
```

**Fix 2: Use timeout to detect deadlocks:**
```python
def thread_1():
    with lock_a:
        acquired = lock_b.acquire(timeout=5)
        if not acquired:
            print("Potential deadlock detected!")
            return
        try:
            print("Thread 1 done")
        finally:
            lock_b.release()
```

**Fix 3: Use a single coarser lock:**
```python
big_lock = threading.Lock()

def thread_1():
    with big_lock:
        print("Thread 1 done")

def thread_2():
    with big_lock:
        print("Thread 2 done")
```

**Prevention rules:**
1. Always acquire multiple locks in a consistent global order
2. Hold locks for the shortest time possible
3. Prefer fewer, coarser locks over many fine-grained locks
4. Use `threading.RLock()` if the same thread needs to re-acquire a lock
```

**Why this is effective:** Shows the exact deadlock scenario visually, then provides three different fixes with trade-offs. Gives prevention rules the learner can apply to any codebase.

**Pair 3 (Advanced):**
```
Q: How can I avoid locks entirely when sharing data between threads? I have heard about thread-safe queues and immutable data structures.

A: Lock-free concurrency patterns avoid the complexity and performance cost of locks:

**Pattern 1: Thread-safe queues (producer-consumer)**
```python
import threading
from queue import Queue

work_queue = Queue()
results_queue = Queue()

def producer():
    for item in data_source:
        work_queue.put(item)
    work_queue.put(None)  # Sentinel to signal "done"

def consumer():
    while True:
        item = work_queue.get()
        if item is None:
            work_queue.put(None)  # Pass sentinel to next consumer
            break
        result = process(item)
        results_queue.put(result)
```
Queue handles all locking internally. You never touch a lock.

**Pattern 2: Immutable data (no shared mutable state)**
```python
from dataclasses import dataclass
from typing import FrozenSet

@dataclass(frozen=True)
class AppState:
    users: tuple
    config: FrozenSet[str]

# Each thread gets its own copy or a reference to immutable data
# No locks needed because nobody can modify the data
```

**Pattern 3: Thread-local storage**
```python
import threading

local_data = threading.local()

def worker(name):
    local_data.name = name  # Each thread has its own 'name'
    do_work()

def do_work():
    print(f"Worker: {local_data.name}")  # Reads THIS thread's value
```

**When to use each:**
| Pattern | Use when | Avoid when |
|---------|---------|------------|
| Queue | Producer-consumer pipeline | Random access to shared data |
| Immutable data | Read-heavy, rare updates | Frequent mutations needed |
| Thread-local | Per-thread context (DB connections) | Data must be shared |
| Locks | All else fails | Performance-critical hot paths |
```

**Why this is effective:** Goes beyond "use locks" to teach architectural patterns that eliminate races by design. Each pattern has a clear use case so the learner knows when to apply it.'''
    ),
    (
        "thinking/auto-datagen-thread-pool-patterns",
        r'''Generate 3 high-quality training pairs that teach thread pool and executor patterns in Python. For each pair, explain why it's effective training data.''',
        r'''<think>
Thread pool patterns are practical and immediately useful:
1. concurrent.futures is the modern Pythonic API
2. Patterns: map, submit+as_completed, callback chains
3. Error handling in pools is tricky and often missed

Progression: basic ThreadPoolExecutor -> advanced patterns -> error handling and monitoring
</think>

Here are 3 training pairs for thread pool and executor patterns:

**Pair 1 (Beginner):**
```
Q: How do I use ThreadPoolExecutor to run tasks concurrently? I want to download 50 URLs in parallel instead of one by one.

A: `concurrent.futures.ThreadPoolExecutor` manages a pool of threads for you:

```python
from concurrent.futures import ThreadPoolExecutor
import requests

urls = ["https://example.com/page1", "https://example.com/page2", ...]

# Method 1: executor.map() -- simple, ordered results
def fetch(url):
    return requests.get(url, timeout=10).text

with ThreadPoolExecutor(max_workers=10) as executor:
    # Results come back in the SAME order as urls
    results = list(executor.map(fetch, urls))

print(f"Downloaded {len(results)} pages")
```

**Key points:**
- `max_workers=10` means 10 threads running simultaneously
- `with` block ensures all threads finish before continuing
- `executor.map()` returns results in input order
- If any call raises an exception, it is re-raised when you iterate results
- Rule of thumb for I/O: `max_workers = min(32, len(tasks))`
```

**Why this is effective:** Shows the simplest possible pattern first. The learner can copy this, change the function and inputs, and have working concurrent code in minutes.

**Pair 2 (Intermediate):**
```
Q: How do I handle errors and get results as they complete (not in order) using ThreadPoolExecutor?

A: Use `submit()` + `as_completed()` for maximum control:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

urls = [...]

def fetch(url):
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return {"url": url, "size": len(response.content), "status": response.status_code}

results = []
errors = []

with ThreadPoolExecutor(max_workers=10) as executor:
    # submit() returns a Future object for each task
    future_to_url = {executor.submit(fetch, url): url for url in urls}

    # as_completed() yields futures as they finish (fastest first)
    for future in as_completed(future_to_url):
        url = future_to_url[future]
        try:
            result = future.result()  # Raises if fetch() raised
            results.append(result)
            print(f"OK: {url} ({result['size']} bytes)")
        except Exception as e:
            errors.append({"url": url, "error": str(e)})
            print(f"FAIL: {url} -- {e}")

print(f"\nCompleted: {len(results)}, Failed: {len(errors)}")
```

**Why submit + as_completed is better than map:**
| Feature | map() | submit() + as_completed() |
|---------|-------|--------------------------|
| Result order | Input order | Completion order (faster!) |
| Error handling | Stops at first error | Handle each error individually |
| Progress tracking | No | Yes (print as each completes) |
| Cancel remaining | No | Yes (future.cancel()) |
```

**Why this is effective:** Teaches the more powerful pattern with a direct comparison table showing when to use each approach. Error handling is built in from the start.

**Pair 3 (Advanced):**
```
Q: How do I build a robust task pipeline with retry logic, rate limiting, and progress reporting using executors?

A: Here is a production-grade executor pattern:

```python
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time

class RobustExecutor:
    def __init__(self, max_workers=10, max_retries=3, rate_limit=None):
        self.max_workers = max_workers
        self.max_retries = max_retries
        self.rate_limit = rate_limit  # Max tasks per second
        self.semaphore = threading.Semaphore(rate_limit) if rate_limit else None
        self.stats = {"completed": 0, "failed": 0, "retried": 0}
        self.stats_lock = threading.Lock()

    def _rate_limited_call(self, fn, *args):
        if self.semaphore:
            self.semaphore.acquire()
            try:
                result = fn(*args)
            finally:
                # Release after a delay to enforce rate limit
                threading.Timer(1.0, self.semaphore.release).start()
        else:
            result = fn(*args)
        return result

    def _call_with_retry(self, fn, *args):
        last_error = None
        for attempt in range(self.max_retries):
            try:
                return self._rate_limited_call(fn, *args)
            except Exception as e:
                last_error = e
                with self.stats_lock:
                    self.stats["retried"] += 1
                wait = 2 ** attempt  # Exponential backoff
                time.sleep(wait)
        raise last_error

    def run(self, fn, items, callback=None):
        results = []
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(self._call_with_retry, fn, item): item
                for item in items
            }
            total = len(futures)
            for i, future in enumerate(as_completed(futures), 1):
                item = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                    with self.stats_lock:
                        self.stats["completed"] += 1
                    if callback:
                        callback(item, result, None)
                except Exception as e:
                    with self.stats_lock:
                        self.stats["failed"] += 1
                    if callback:
                        callback(item, None, e)
                # Progress
                print(f"\rProgress: {i}/{total} "
                      f"({self.stats['completed']} ok, "
                      f"{self.stats['failed']} fail, "
                      f"{self.stats['retried']} retries)", end="")
        print()
        return results

# Usage:
executor = RobustExecutor(max_workers=5, max_retries=3, rate_limit=10)
results = executor.run(fetch_url, urls, callback=save_result)
print(executor.stats)
```

**Features:**
- Automatic retry with exponential backoff
- Rate limiting to avoid overwhelming the target
- Progress reporting with live stats
- Per-task callback for streaming results
- Thread-safe statistics collection
```

**Why this is effective:** Shows a production-quality pattern the learner can adapt. Combines multiple concurrency concepts (locks, semaphores, executors) into a cohesive class with clear separation of concerns.'''
    ),
    (
        "thinking/auto-datagen-async-patterns",
        r'''Generate 3 high-quality training pairs that teach async/await patterns and common async pitfalls. For each pair, explain why it's effective training data.''',
        r'''<think>
Async patterns are essential for modern Python:
1. asyncio basics -- event loop, coroutines, tasks
2. Common patterns -- gather, semaphore, timeout
3. Pitfalls -- blocking the event loop, forgetting await, mixing sync/async

Progression: basic coroutines -> practical patterns -> avoiding common mistakes
</think>

Here are 3 training pairs for async/await patterns:

**Pair 1 (Beginner):**
```
Q: I am trying to use async/await in Python but I do not understand when code actually runs concurrently. Can you explain with a clear example?

A: The key insight: `await` is where concurrency happens. When one coroutine awaits I/O, others can run.

```python
import asyncio
import time

async def task(name, delay):
    print(f"{name}: starting")
    await asyncio.sleep(delay)   # <-- Yields control here
    print(f"{name}: done after {delay}s")
    return name

# SEQUENTIAL (no concurrency, 6 seconds total):
async def sequential():
    result1 = await task("A", 2)   # Wait 2s
    result2 = await task("B", 2)   # Wait 2s
    result3 = await task("C", 2)   # Wait 2s
    return [result1, result2, result3]

# CONCURRENT (all at once, 2 seconds total):
async def concurrent():
    results = await asyncio.gather(
        task("A", 2),
        task("B", 2),
        task("C", 2),
    )
    return results

start = time.time()
asyncio.run(concurrent())
print(f"Total: {time.time() - start:.1f}s")  # ~2.0s, not 6.0s
```

**The rule:** `await` on a single coroutine is sequential. `asyncio.gather()` runs multiple coroutines concurrently.
```

**Why this is effective:** Directly contrasts sequential vs concurrent with the same tasks. The timing proof makes the benefit tangible.

**Pair 2 (Intermediate):**
```
Q: How do I limit concurrency with asyncio? I need to fetch 1000 URLs but only 20 at a time, not all 1000 simultaneously.

A: Use `asyncio.Semaphore` to limit concurrent tasks:

```python
import asyncio
import aiohttp

async def fetch(session, url, semaphore):
    async with semaphore:  # Only N coroutines enter at once
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            return {"url": url, "status": resp.status, "size": len(await resp.read())}

async def fetch_all(urls, max_concurrent=20):
    semaphore = asyncio.Semaphore(max_concurrent)
    results = []
    errors = []

    async with aiohttp.ClientSession() as session:
        tasks = [fetch(session, url, semaphore) for url in urls]
        for coro in asyncio.as_completed(tasks):
            try:
                result = await coro
                results.append(result)
            except Exception as e:
                errors.append(str(e))

    return results, errors

urls = [f"https://example.com/page/{i}" for i in range(1000)]
results, errors = asyncio.run(fetch_all(urls, max_concurrent=20))
print(f"Fetched: {len(results)}, Errors: {len(errors)}")
```

**Without semaphore:** 1000 simultaneous connections -- crashes, timeouts, bans.
**With semaphore(20):** Only 20 active at a time, others wait their turn.
```

**Why this is effective:** Solves a real problem (too many concurrent requests) with the standard asyncio pattern. Shows error handling and practical limits.

**Pair 3 (Advanced):**
```
Q: What are the most common async/await mistakes and how do I avoid them?

A: Here are the top async pitfalls with fixes:

**Mistake 1: Blocking the event loop**
```python
# BAD -- blocks ALL other coroutines while this runs
async def process():
    result = requests.get("https://api.example.com")  # Sync HTTP!
    data = heavy_computation(result)  # CPU-bound!
    return data

# GOOD -- use async HTTP and run CPU work in executor
async def process():
    async with aiohttp.ClientSession() as session:
        async with session.get("https://api.example.com") as resp:
            result = await resp.json()

    loop = asyncio.get_event_loop()
    data = await loop.run_in_executor(None, heavy_computation, result)
    return data
```

**Mistake 2: Forgetting to await**
```python
# BAD -- coroutine is created but never executed
async def main():
    fetch_data()  # Returns coroutine object, does nothing!

# GOOD
async def main():
    await fetch_data()  # Actually runs the coroutine
```

**Mistake 3: Not handling task exceptions**
```python
# BAD -- exception is silently swallowed
async def main():
    task = asyncio.create_task(might_fail())
    await asyncio.sleep(10)
    # If might_fail() raised, you will never know

# GOOD -- always await tasks or add done callbacks
async def main():
    task = asyncio.create_task(might_fail())
    try:
        await task
    except Exception as e:
        print(f"Task failed: {e}")
```

**Mistake 4: Creating too many tasks without limits**
```python
# BAD -- 100,000 concurrent tasks exhaust memory
tasks = [asyncio.create_task(fetch(url)) for url in million_urls]

# GOOD -- use semaphore or batch processing
semaphore = asyncio.Semaphore(100)
async def limited_fetch(url):
    async with semaphore:
        return await fetch(url)
tasks = [asyncio.create_task(limited_fetch(url)) for url in million_urls]
```

**Quick reference:**
| Mistake | Symptom | Fix |
|---------|---------|-----|
| Blocking call in async | Everything freezes | Use async library or run_in_executor |
| Missing await | "coroutine was never awaited" warning | Add await |
| Unhandled task exception | Silent failures | Always await or add error handling |
| Unlimited concurrency | Memory explosion, connection errors | Use Semaphore |
```

**Why this is effective:** Covers the four most common async mistakes with bad/good code pairs. The quick reference table makes it a useful cheat sheet the learner will return to.'''
    ),
    (
        "thinking/auto-datagen-concurrent-data-structures",
        r'''Generate 3 high-quality training pairs that teach thread-safe data structure usage and patterns. For each pair, explain why it's effective training data.''',
        r'''<think>
Thread-safe data structures are essential for correct concurrent programs:
1. Python's built-in thread-safe structures (Queue, deque with some caveats)
2. Making custom data structures thread-safe
3. Common patterns: concurrent caches, counters, accumulators

Progression: using built-in thread-safe types -> protecting custom structures -> advanced concurrent patterns
</think>

Here are 3 training pairs for thread-safe data structures:

**Pair 1 (Beginner):**
```
Q: Which Python data structures are thread-safe? Can I safely use a regular dict or list from multiple threads?

A: **Most Python built-in operations on built-in types ARE atomic due to the GIL**, but compound operations are NOT safe.

```python
import threading

# SAFE -- single atomic operations:
shared_list = []
shared_list.append(item)    # Atomic (GIL protects single bytecode op)
shared_dict = {}
shared_dict[key] = value    # Atomic

# NOT SAFE -- compound operations:
counter = 0
counter += 1                # Read + add + write = 3 operations!

if key not in d:
    d[key] = value          # Check + set = TOCTOU race condition

# EXPLICITLY THREAD-SAFE structures:
from queue import Queue            # Thread-safe FIFO queue
from queue import LifoQueue        # Thread-safe stack
from queue import PriorityQueue    # Thread-safe priority queue
from collections import deque      # append/pop are atomic

# SAFE usage of Queue:
q = Queue()
q.put(item)       # Blocks if full (maxsize), thread-safe
item = q.get()    # Blocks if empty, thread-safe
```

**Rule of thumb:**
- Single read or single write to a built-in type: usually safe
- Read-then-write or check-then-act: NOT safe, use a lock
- When in doubt: use Queue or add a lock
```

**Why this is effective:** Directly answers the common question about what is/is not safe without being either too paranoid ("lock everything") or too cavalier ("the GIL makes everything safe").

**Pair 2 (Intermediate):**
```
Q: How do I build a thread-safe cache that multiple threads can read and write concurrently without corrupting data?

A: Use `threading.Lock` with a dict, or use `functools.lru_cache` for simple cases:

```python
import threading
from typing import Optional, Any

class ThreadSafeCache:
    def __init__(self, max_size: int = 1000):
        self._cache: dict = {}
        self._lock = threading.RLock()  # RLock allows re-entrant locking
        self._max_size = max_size
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            if key in self._cache:
                self._hits += 1
                return self._cache[key]
            self._misses += 1
            return None

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            if len(self._cache) >= self._max_size:
                # Evict oldest entry (FIFO)
                oldest_key = next(iter(self._cache))
                del self._cache[oldest_key]
            self._cache[key] = value

    def get_or_compute(self, key: str, compute_fn) -> Any:
        """Get from cache, or compute and store."""
        with self._lock:
            if key in self._cache:
                self._hits += 1
                return self._cache[key]

        # Compute outside the lock (allows concurrent computation)
        value = compute_fn()

        with self._lock:
            # Double-check: another thread might have computed it
            if key not in self._cache:
                self._cache[key] = value
            self._misses += 1
            return self._cache.get(key, value)

    @property
    def stats(self):
        with self._lock:
            total = self._hits + self._misses
            rate = self._hits / total if total > 0 else 0
            return {"hits": self._hits, "misses": self._misses, "hit_rate": f"{rate:.1%}"}

# Usage:
cache = ThreadSafeCache(max_size=500)

def worker(user_id):
    profile = cache.get_or_compute(
        f"user:{user_id}",
        lambda: fetch_user_profile(user_id)
    )
    return profile
```

**Design choices explained:**
- `RLock` instead of `Lock`: allows get_or_compute to call get internally
- Compute outside the lock: avoids holding the lock during slow I/O
- Double-check after compute: prevents duplicate entries from concurrent calls
```

**Why this is effective:** Shows a realistic, production-quality cache with subtle design decisions explained. The get_or_compute pattern with double-checked locking is a real-world pattern they will encounter.

**Pair 3 (Advanced):**
```
Q: How do I implement a thread-safe counter and accumulator that multiple worker threads can update efficiently?

A: Several approaches, from simple to high-performance:

```python
import threading
from collections import defaultdict

# Approach 1: Simple locked counter
class ThreadSafeCounter:
    def __init__(self):
        self._count = 0
        self._lock = threading.Lock()

    def increment(self, n=1):
        with self._lock:
            self._count += n

    @property
    def value(self):
        return self._count  # Single read is atomic

# Approach 2: Per-thread counters (high-performance)
class ShardedCounter:
    """Each thread has its own counter. Sum on read.
    Avoids lock contention for write-heavy workloads."""

    def __init__(self):
        self._local = threading.local()
        self._shards = []
        self._shards_lock = threading.Lock()

    def increment(self, n=1):
        if not hasattr(self._local, 'counter'):
            self._local.counter = [0]
            with self._shards_lock:
                self._shards.append(self._local.counter)
        self._local.counter[0] += n  # No lock needed -- thread-local

    @property
    def value(self):
        with self._shards_lock:
            return sum(shard[0] for shard in self._shards)

# Approach 3: Thread-safe accumulator with categories
class ThreadSafeAccumulator:
    def __init__(self):
        self._data = defaultdict(lambda: {"count": 0, "total": 0.0, "min": float("inf"), "max": float("-inf")})
        self._lock = threading.Lock()

    def record(self, category: str, value: float):
        with self._lock:
            entry = self._data[category]
            entry["count"] += 1
            entry["total"] += value
            entry["min"] = min(entry["min"], value)
            entry["max"] = max(entry["max"], value)

    def summary(self):
        with self._lock:
            result = {}
            for cat, entry in self._data.items():
                result[cat] = {
                    "count": entry["count"],
                    "avg": entry["total"] / entry["count"] if entry["count"] > 0 else 0,
                    "min": entry["min"],
                    "max": entry["max"],
                }
            return result

# Usage:
stats = ThreadSafeAccumulator()

def worker(urls):
    for url in urls:
        start = time.time()
        response = requests.get(url)
        elapsed = time.time() - start
        stats.record("http_requests", elapsed)
        stats.record(f"status_{response.status_code}", elapsed)

# After all threads complete:
print(stats.summary())
# {"http_requests": {"count": 500, "avg": 0.23, "min": 0.05, "max": 2.1},
#  "status_200": {"count": 485, ...}, "status_404": {"count": 15, ...}}
```

**Performance comparison:**
| Pattern | Writes/sec (10 threads) | Lock contention |
|---------|------------------------|----------------|
| Simple locked counter | ~2M | High |
| Sharded counter | ~20M | None |
| Accumulator | ~1.5M | Medium |

Use sharded counter when writes vastly outnumber reads.
```

**Why this is effective:** Shows three progressively more sophisticated approaches, each solving a real problem. The performance comparison gives the learner guidance on when to use each pattern.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
