"""Async/concurrency training pairs: Python threading."""

pairs = [
    {
        "instruction": r'''How does the Python GIL (Global Interpreter Lock) affect threading? When should I use threads vs multiprocessing?''',
        "output": r'''<think>
The GIL is one of the most misunderstood aspects of Python. Let me think through what it actually does and does not do.

The GIL prevents multiple threads from executing Python bytecode simultaneously. This means CPU-bound Python code cannot benefit from multiple threads -- only one thread runs Python code at a time. However, the GIL is released during I/O operations (file reads, network calls, etc.) and during calls to C extensions that explicitly release it (numpy, etc.).

So threads ARE useful for I/O-bound work (waiting for network, disk, database) because the GIL is released while waiting. But for CPU-bound work, you need multiprocessing to actually use multiple cores.

Wait, I should also mention Python 3.13's free-threaded build (PEP 703) which removes the GIL experimentally. And the fact that some C extensions like numpy release the GIL during computation, so numpy operations CAN benefit from threads.

Actually, let me keep it practical. The decision tree is:
- I/O-bound -> asyncio (best) or threading (also fine)
- CPU-bound pure Python -> multiprocessing
- CPU-bound C extension (numpy, etc.) -> threading may work since GIL is released
</think>

The GIL prevents multiple threads from running Python bytecode at the same time. This affects what threading can and cannot do:

```python
import threading
import time
import hashlib
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

# ============================================================
# Demo: GIL prevents CPU parallelism with threads
# ============================================================

def cpu_bound_work(n: int) -> int:
    """Pure Python CPU work -- affected by GIL."""
    total = 0
    for i in range(n):
        total += i * i
    return total

def io_bound_work(seconds: float) -> str:
    """I/O wait -- GIL is released during sleep/network/disk."""
    time.sleep(seconds)
    return "done"

def benchmark(label: str, fn, args_list: list):
    start = time.monotonic()
    results = [fn(*args) for args in args_list]
    elapsed = time.monotonic() - start
    print(f"{label}: {elapsed:.2f}s")
    return results

# --- CPU-bound: threads do NOT help ---

def cpu_sequential():
    start = time.monotonic()
    for _ in range(4):
        cpu_bound_work(5_000_000)
    print(f"CPU sequential: {time.monotonic() - start:.2f}s")

def cpu_threaded():
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(cpu_bound_work, [5_000_000] * 4))
    # Same or SLOWER than sequential due to GIL contention
    print(f"CPU threaded: {time.monotonic() - start:.2f}s")

def cpu_multiprocess():
    start = time.monotonic()
    with ProcessPoolExecutor(max_workers=4) as pool:
        list(pool.map(cpu_bound_work, [5_000_000] * 4))
    # ~4x faster (true parallelism)
    print(f"CPU multiprocess: {time.monotonic() - start:.2f}s")

# --- I/O-bound: threads DO help ---

def io_sequential():
    start = time.monotonic()
    for _ in range(4):
        io_bound_work(1.0)
    print(f"I/O sequential: {time.monotonic() - start:.2f}s")  # ~4s

def io_threaded():
    start = time.monotonic()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(io_bound_work, [1.0] * 4))
    print(f"I/O threaded: {time.monotonic() - start:.2f}s")  # ~1s

# ============================================================
# Decision guide
# ============================================================

# I/O-bound (network, disk, database):
#   -> asyncio (best for many concurrent I/O operations)
#   -> threading (fine, especially with existing sync libraries)
#
# CPU-bound pure Python:
#   -> multiprocessing (true parallelism, bypasses GIL)
#
# CPU-bound C extension (numpy, PIL):
#   -> threading may work (many C extensions release the GIL)
#   -> multiprocessing as fallback
#
# Mixed I/O + CPU:
#   -> asyncio + ProcessPoolExecutor for CPU parts
#   -> asyncio.to_thread() for blocking I/O libraries

if __name__ == "__main__":
    cpu_sequential()
    cpu_threaded()
    cpu_multiprocess()
    io_sequential()
    io_threaded()
```

Key takeaways:
- The GIL makes CPU-bound threads run sequentially (no speedup)
- The GIL is released during I/O, so threads speed up I/O-bound work
- Use `multiprocessing` or `ProcessPoolExecutor` for CPU-bound parallelism
- Python 3.13+ has an experimental free-threaded build (no GIL)'''
    },
    {
        "instruction": r'''Show me how to use Python's threading.Lock, RLock, and Condition variables for thread-safe programming.''',
        "output": r'''<think>
Thread synchronization primitives in Python:

1. Lock -- basic mutual exclusion. Only one thread can hold it. Non-reentrant, so the same thread will deadlock if it tries to acquire twice.
2. RLock -- reentrant lock. Same thread can acquire multiple times (must release the same number of times). Useful when a locked method calls another locked method.
3. Condition -- allows threads to wait for a condition to be true. Built on top of a Lock. Has wait(), notify(), notify_all().

I should show practical examples of each, including common mistakes like forgetting to use a context manager (which can leave a lock held if an exception occurs).

Actually, a subtle point about Lock vs RLock: RLock has overhead because it tracks the owning thread and acquisition count. Use Lock when you do not need reentrancy.
</think>

```python
import threading
import time
from typing import Any
from collections import deque

# ============================================================
# Lock -- basic mutual exclusion
# ============================================================

class BankAccount:
    """Thread-safe bank account using Lock."""

    def __init__(self, balance: float = 0.0):
        self._balance = balance
        self._lock = threading.Lock()

    @property
    def balance(self) -> float:
        with self._lock:  # always use context manager
            return self._balance

    def deposit(self, amount: float) -> float:
        with self._lock:
            self._balance += amount
            return self._balance

    def withdraw(self, amount: float) -> float:
        with self._lock:
            if amount > self._balance:
                raise ValueError("Insufficient funds")
            self._balance -= amount
            return self._balance

    def transfer_to(self, other: "BankAccount", amount: float):
        # DANGER: acquiring two locks can deadlock!
        # Always acquire in consistent order to prevent deadlock
        first, second = sorted(
            [self, other], key=lambda a: id(a)
        )
        with first._lock:
            with second._lock:
                self._balance -= amount
                other._balance += amount

# ============================================================
# RLock -- reentrant lock (same thread can acquire multiple times)
# ============================================================

class ThreadSafeCache:
    """Cache where methods call each other (needs RLock)."""

    def __init__(self, max_size: int = 100):
        self._data: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._max_size = max_size

    def get(self, key: str) -> Any:
        with self._lock:
            return self._data.get(key)

    def put(self, key: str, value: Any):
        with self._lock:
            if len(self._data) >= self._max_size:
                self._evict()  # calls another locked method
            self._data[key] = value

    def _evict(self):
        with self._lock:  # RLock allows this (same thread)
            # With a regular Lock, this would DEADLOCK
            # because put() already holds the lock
            if self._data:
                oldest = next(iter(self._data))
                del self._data[oldest]

    def get_or_create(self, key: str, factory):
        with self._lock:
            val = self.get(key)  # re-acquires the RLock (OK)
            if val is None:
                val = factory()
                self.put(key, val)  # re-acquires again (OK)
            return val

# ============================================================
# Condition -- wait for a condition to become true
# ============================================================

class BoundedBuffer:
    """Thread-safe bounded buffer using Condition variables."""

    def __init__(self, capacity: int = 10):
        self._buffer: deque = deque()
        self._capacity = capacity
        self._lock = threading.Lock()
        self._not_full = threading.Condition(self._lock)
        self._not_empty = threading.Condition(self._lock)

    def put(self, item: Any):
        with self._not_full:
            while len(self._buffer) >= self._capacity:
                self._not_full.wait()  # release lock, wait, reacquire
            self._buffer.append(item)
            self._not_empty.notify()  # wake up a consumer

    def get(self, timeout: float | None = None) -> Any:
        with self._not_empty:
            while len(self._buffer) == 0:
                if not self._not_empty.wait(timeout=timeout):
                    raise TimeoutError("Buffer empty after timeout")
            item = self._buffer.popleft()
            self._not_full.notify()  # wake up a producer
            return item

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._buffer)

# ============================================================
# Usage demo
# ============================================================

def demo_bounded_buffer():
    buf = BoundedBuffer(capacity=5)

    def producer(name: str, count: int):
        for i in range(count):
            buf.put(f"{name}-{i}")
            print(f"[{name}] produced item {i}")
            time.sleep(0.05)

    def consumer(name: str, count: int):
        for _ in range(count):
            item = buf.get(timeout=5.0)
            print(f"[{name}] consumed: {item}")
            time.sleep(0.1)

    threads = [
        threading.Thread(target=producer, args=("P1", 10)),
        threading.Thread(target=producer, args=("P2", 10)),
        threading.Thread(target=consumer, args=("C1", 10)),
        threading.Thread(target=consumer, args=("C2", 10)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

if __name__ == "__main__":
    demo_bounded_buffer()
```

Key rules:
- Always use `with lock:` (context manager) -- never bare acquire/release
- Use `Lock` by default; only use `RLock` when methods call each other
- Acquire multiple locks in a consistent order to prevent deadlocks
- Use `Condition` when threads need to wait for a state change'''
    },
    {
        "instruction": r'''How do I use concurrent.futures.ThreadPoolExecutor effectively in Python? Show real-world patterns.''',
        "output": r'''```python
import concurrent.futures
import time
import urllib.request
import json
from typing import Any, Callable
from pathlib import Path

# ============================================================
# Basic: submit and map
# ============================================================

def fetch_url(url: str) -> dict[str, Any]:
    """Fetch a URL (blocking)."""
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return {
                "url": url,
                "status": resp.status,
                "size": len(resp.read()),
            }
    except Exception as e:
        return {"url": url, "error": str(e)}

def basic_usage():
    urls = [
        "https://httpbin.org/get",
        "https://httpbin.org/delay/1",
        "https://httpbin.org/status/404",
    ]

    # map() -- ordered results, simple API
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(fetch_url, urls))
    for r in results:
        print(r)

    # submit() -- returns Future objects, more control
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(fetch_url, url): url for url in urls}
        for future in concurrent.futures.as_completed(futures):
            url = futures[future]
            result = future.result()
            print(f"{url} -> {result.get('status', 'error')}")

# ============================================================
# Pattern: progress tracking with as_completed
# ============================================================

def process_file(path: Path) -> dict:
    """Process a single file (CPU-light, I/O-heavy)."""
    content = path.read_text()
    lines = content.count("\n") + 1
    words = len(content.split())
    return {"path": str(path), "lines": lines, "words": words}

def process_files_with_progress(directory: Path, pattern: str = "*.py"):
    files = list(directory.rglob(pattern))
    total = len(files)
    results = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(process_file, f): f for f in files
        }

        for i, future in enumerate(
            concurrent.futures.as_completed(futures), 1
        ):
            filepath = futures[future]
            try:
                result = future.result()
                results.append(result)
            except Exception as e:
                print(f"Error processing {filepath}: {e}")

            if i % 10 == 0 or i == total:
                print(f"Progress: {i}/{total} files")

    return results

# ============================================================
# Pattern: timeout and cancellation
# ============================================================

def slow_task(task_id: int, duration: float) -> str:
    time.sleep(duration)
    return f"task-{task_id} completed"

def with_timeout():
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        future = pool.submit(slow_task, 1, 10.0)

        try:
            # Wait at most 2 seconds for result
            result = future.result(timeout=2.0)
        except concurrent.futures.TimeoutError:
            print("Task timed out, cancelling...")
            cancelled = future.cancel()
            print(f"Cancel successful: {cancelled}")
            # Note: cancel() only works if the task has not started yet.
            # Once a thread is running, cancel() returns False.

# ============================================================
# Pattern: rate-limited thread pool
# ============================================================

import threading

class RateLimitedPool:
    """Thread pool with rate limiting."""

    def __init__(self, max_workers: int, max_per_second: float):
        self._pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=max_workers
        )
        self._semaphore = threading.Semaphore(max_workers)
        self._min_interval = 1.0 / max_per_second
        self._last_call = 0.0
        self._rate_lock = threading.Lock()

    def _rate_limited_call(self, fn: Callable, *args) -> Any:
        with self._rate_lock:
            now = time.monotonic()
            wait = self._last_call + self._min_interval - now
            if wait > 0:
                time.sleep(wait)
            self._last_call = time.monotonic()
        return fn(*args)

    def submit(self, fn: Callable, *args) -> concurrent.futures.Future:
        return self._pool.submit(self._rate_limited_call, fn, *args)

    def shutdown(self, wait: bool = True):
        self._pool.shutdown(wait=wait)

def rate_limited_example():
    pool = RateLimitedPool(max_workers=4, max_per_second=5)
    try:
        futures = [
            pool.submit(fetch_url, f"https://httpbin.org/get?i={i}")
            for i in range(20)
        ]
        for f in concurrent.futures.as_completed(futures):
            print(f.result().get("status", "error"))
    finally:
        pool.shutdown()

if __name__ == "__main__":
    basic_usage()
```

Tips:
- Use `map()` for simple ordered results; `submit()` + `as_completed()` for progress tracking
- Set `max_workers` based on workload: ~5x CPU count for I/O, ~1x for CPU
- `future.result(timeout=N)` prevents waiting forever
- `cancel()` only works for tasks not yet started -- running threads cannot be interrupted'''
    },
    {
        "instruction": r'''What are thread-safe data structures in Python? Which standard library types are safe to use from multiple threads without explicit locking?''',
        "output": r'''<think>
This is a nuanced topic. Due to the GIL, many Python operations are "accidentally" thread-safe -- individual bytecode operations are atomic. But relying on this is fragile because:

1. What counts as a single bytecode operation can change between Python versions
2. Compound operations (check-then-act) are NOT atomic even with the GIL

The actually thread-safe structures in the stdlib:
- queue.Queue, queue.LifoQueue, queue.PriorityQueue -- designed for threading
- collections.deque -- append/appendleft/pop/popleft are atomic (CPython implementation detail)
- logging module -- thread-safe by design

Things that are NOT thread-safe despite the GIL:
- dict operations like d[key] += 1 (read-modify-write is NOT atomic)
- list operations like lst.append() are atomic but lst.sort() is not
- set operations -- individual adds are atomic but iterations are not

Hmm, actually I need to be more precise. In CPython, the GIL makes individual bytecode instructions atomic. So `dict[key] = value` is a single STORE_SUBSCR bytecode and IS atomic. But `dict[key] += 1` is multiple bytecodes (load, add, store) and is NOT atomic. The problem is that people confuse "atomic operation" with "thread-safe compound operation."

I should recommend always using proper synchronization rather than relying on GIL guarantees.
</think>

The GIL makes some operations accidentally atomic, but you should not rely on this. Use purpose-built thread-safe structures:

```python
import threading
import queue
from collections import deque
from typing import Any

# ============================================================
# SAFE: queue.Queue -- purpose-built for threading
# ============================================================

def queue_example():
    q = queue.Queue(maxsize=100)  # thread-safe, blocking

    def producer():
        for i in range(20):
            q.put(i)  # blocks if full
        q.put(None)   # sentinel

    def consumer():
        while True:
            item = q.get()   # blocks if empty
            if item is None:
                break
            print(f"Got: {item}")
            q.task_done()

    t1 = threading.Thread(target=producer)
    t2 = threading.Thread(target=consumer)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

# Also available:
# queue.LifoQueue -- stack (last-in, first-out)
# queue.PriorityQueue -- sorted by priority
# queue.SimpleQueue -- minimal, no maxsize, no task_done

# ============================================================
# SAFE WITH CAVEATS: deque (atomic append/pop in CPython)
# ============================================================

# deque.append(), deque.appendleft(), deque.pop(), deque.popleft()
# are atomic in CPython due to the GIL. But this is an
# implementation detail, not a language guarantee.

# For a simple thread-safe buffer, deque with maxlen works:
buffer = deque(maxlen=1000)
# buffer.append(item)     -- safe
# item = buffer.popleft() -- safe, but raises IndexError if empty

# ============================================================
# NOT SAFE: compound operations on built-in types
# ============================================================

counter = 0
counter_lock = threading.Lock()

def unsafe_increment():
    global counter
    # NOT SAFE: counter += 1 is multiple bytecodes
    # (LOAD_GLOBAL, LOAD_CONST, BINARY_ADD, STORE_GLOBAL)
    counter += 1

def safe_increment():
    global counter
    with counter_lock:
        counter += 1

# ============================================================
# Thread-safe counter (no manual locking needed)
# ============================================================

class AtomicCounter:
    """Thread-safe counter using a lock internally."""

    def __init__(self, initial: int = 0):
        self._value = initial
        self._lock = threading.Lock()

    def increment(self, n: int = 1) -> int:
        with self._lock:
            self._value += n
            return self._value

    def decrement(self, n: int = 1) -> int:
        with self._lock:
            self._value -= n
            return self._value

    @property
    def value(self) -> int:
        with self._lock:
            return self._value

# ============================================================
# Thread-safe dict wrapper
# ============================================================

class ThreadSafeDict:
    """Dict with per-operation locking."""

    def __init__(self):
        self._data: dict[str, Any] = {}
        self._lock = threading.RLock()

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._data.get(key, default)

    def set(self, key: str, value: Any):
        with self._lock:
            self._data[key] = value

    def setdefault(self, key: str, factory) -> Any:
        """Atomic get-or-create."""
        with self._lock:
            if key not in self._data:
                self._data[key] = factory()
            return self._data[key]

    def update_value(self, key: str, fn) -> Any:
        """Atomic read-modify-write."""
        with self._lock:
            old = self._data.get(key)
            new = fn(old)
            self._data[key] = new
            return new

    def items(self) -> list[tuple[str, Any]]:
        with self._lock:
            return list(self._data.items())

# ============================================================
# Usage
# ============================================================

def demo():
    counter = AtomicCounter()
    safe_dict = ThreadSafeDict()

    def worker(worker_id: int):
        for i in range(100):
            counter.increment()
            safe_dict.update_value(
                "total",
                lambda v: (v or 0) + 1,
            )

    threads = [
        threading.Thread(target=worker, args=(i,))
        for i in range(10)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"Counter: {counter.value}")  # exactly 1000
    print(f"Dict total: {safe_dict.get('total')}")  # exactly 1000

if __name__ == "__main__":
    demo()
```

Summary:
- `queue.Queue` -- always safe, purpose-built for threading
- `deque.append()`/`popleft()` -- atomic in CPython (implementation detail)
- `dict[key] = val` -- atomic in CPython, but `dict[key] += 1` is NOT
- Always use explicit locks for compound operations (read-modify-write)
- When in doubt, wrap with a lock -- the overhead is negligible'''
    },
    {
        "instruction": r'''What are daemon threads in Python and how do they affect application shutdown? What are the gotchas?''',
        "output": r'''Daemon threads are killed when the main thread exits. Non-daemon threads keep the program alive. Here are the details and gotchas:

```python
import threading
import time
import signal
import sys
from typing import Any

# ============================================================
# Basic: daemon vs non-daemon
# ============================================================

def background_work(name: str, duration: float):
    print(f"[{name}] started")
    try:
        time.sleep(duration)
        print(f"[{name}] completed")
    finally:
        # WARNING: for daemon threads, this may NOT run
        # if the main thread exits first
        print(f"[{name}] cleanup")

def daemon_demo():
    # Non-daemon (default): program waits for this thread
    t1 = threading.Thread(
        target=background_work, args=("worker", 2.0)
    )
    t1.start()
    # Program will not exit until t1 finishes

    # Daemon: killed when main thread exits
    t2 = threading.Thread(
        target=background_work, args=("daemon", 10.0),
        daemon=True,
    )
    t2.start()
    # If main thread ends, t2 is killed immediately
    # Its finally block may NOT execute!

# ============================================================
# GOTCHA: daemon threads skip cleanup
# ============================================================

def write_important_data():
    """NEVER use daemon=True for this!"""
    try:
        # Simulate writing to a file
        time.sleep(1)
        print("Writing critical data...")
        time.sleep(1)
        print("Data written successfully")
    finally:
        # If this is a daemon thread and main exits,
        # this cleanup code is SKIPPED
        print("Closing file handle")

# ============================================================
# CORRECT: use an event to signal shutdown
# ============================================================

class GracefulWorker:
    """Worker thread that shuts down cleanly."""

    def __init__(self, name: str):
        self.name = name
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._run,
            name=name,
            daemon=False,  # non-daemon so cleanup runs
        )

    def start(self):
        self._thread.start()

    def stop(self, timeout: float = 5.0):
        """Signal the thread to stop and wait."""
        self._stop_event.set()
        self._thread.join(timeout=timeout)
        if self._thread.is_alive():
            print(f"[{self.name}] WARNING: did not stop in time")

    def _run(self):
        print(f"[{self.name}] started")
        try:
            while not self._stop_event.is_set():
                # Do work in small increments
                self._do_work()
                # Check for stop signal periodically
                self._stop_event.wait(timeout=0.5)
        finally:
            self._cleanup()

    def _do_work(self):
        time.sleep(0.1)  # simulate work

    def _cleanup(self):
        print(f"[{self.name}] cleaning up resources")

# ============================================================
# Pattern: application with graceful shutdown
# ============================================================

class Application:
    def __init__(self):
        self._workers: list[GracefulWorker] = []
        self._running = True

    def add_worker(self, name: str) -> GracefulWorker:
        worker = GracefulWorker(name)
        self._workers.append(worker)
        return worker

    def start(self):
        for w in self._workers:
            w.start()
        print(f"Started {len(self._workers)} workers")

    def shutdown(self, timeout: float = 10.0):
        print("Shutting down...")
        for w in self._workers:
            w.stop(timeout=timeout / len(self._workers))
        print("All workers stopped")

def main():
    app = Application()
    app.add_worker("fetcher")
    app.add_worker("processor")
    app.add_worker("reporter")
    app.start()

    # Register signal handler for graceful shutdown
    def handle_signal(signum, frame):
        app.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    try:
        # Main thread waits
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        app.shutdown()

if __name__ == "__main__":
    main()
```

Rules:
- Use `daemon=True` only for truly disposable background tasks (heartbeats, metrics)
- Never use daemon threads for I/O that must complete (writes, sends)
- Use `threading.Event` to signal threads to stop gracefully
- Always `join()` non-daemon threads before exit
- Set reasonable timeouts on `join()` to avoid hanging on shutdown'''
    },
]
