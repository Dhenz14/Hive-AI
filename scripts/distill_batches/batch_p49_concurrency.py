"""Concurrency — threading, multiprocessing, concurrent.futures, and synchronization patterns."""

PAIRS = [
    (
        "python/threading-multiprocessing",
        "Show Python concurrency patterns: threading for I/O, multiprocessing for CPU, and concurrent.futures.",
        '''Python concurrency patterns:

```python
import threading
import multiprocessing as mp
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from queue import Queue, Empty
import time
from typing import Callable, TypeVar, Any
import logging

logger = logging.getLogger(__name__)
T = TypeVar("T")


# --- ThreadPoolExecutor for I/O-bound tasks ---

def fetch_urls(urls: list[str], max_workers: int = 10) -> list[dict]:
    """Fetch multiple URLs concurrently."""
    import urllib.request

    def fetch_one(url: str) -> dict:
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                return {"url": url, "status": resp.status, "size": len(resp.read())}
        except Exception as e:
            return {"url": url, "error": str(e)}

    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_url = {executor.submit(fetch_one, url): url for url in urls}
        for future in as_completed(future_to_url):
            results.append(future.result())
    return results


# --- ProcessPoolExecutor for CPU-bound tasks ---

def parallel_compute(data_chunks: list[list], func: Callable,
                     max_workers: int = None) -> list:
    """Process data chunks in parallel using multiple processes."""
    max_workers = max_workers or mp.cpu_count()

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = [executor.submit(func, chunk) for chunk in data_chunks]
        results = [f.result() for f in futures]
    return results


def compute_heavy(numbers: list[int]) -> list[int]:
    """CPU-intensive function (run in separate process)."""
    return [n ** 2 + sum(range(n % 1000)) for n in numbers]

# Usage:
# chunks = [data[i:i+1000] for i in range(0, len(data), 1000)]
# results = parallel_compute(chunks, compute_heavy)


# --- Producer-consumer with Queue ---

class ProducerConsumer:
    def __init__(self, num_workers: int = 4):
        self.queue: Queue = Queue(maxsize=100)
        self.num_workers = num_workers
        self.results: list = []
        self._lock = threading.Lock()

    def producer(self, items: list):
        """Add items to queue."""
        for item in items:
            self.queue.put(item)
        # Signal workers to stop
        for _ in range(self.num_workers):
            self.queue.put(None)

    def worker(self, process_fn: Callable):
        """Process items from queue."""
        while True:
            item = self.queue.get()
            if item is None:
                break
            try:
                result = process_fn(item)
                with self._lock:
                    self.results.append(result)
            except Exception as e:
                logger.error("Worker error: %s", e)
            finally:
                self.queue.task_done()

    def run(self, items: list, process_fn: Callable) -> list:
        # Start workers
        workers = [
            threading.Thread(target=self.worker, args=(process_fn,))
            for _ in range(self.num_workers)
        ]
        for w in workers:
            w.start()

        # Start producer
        producer = threading.Thread(target=self.producer, args=(items,))
        producer.start()

        # Wait for completion
        producer.join()
        for w in workers:
            w.join()

        return self.results


# --- Thread-safe data structures ---

class ThreadSafeCounter:
    def __init__(self):
        self._value = 0
        self._lock = threading.Lock()

    def increment(self, amount: int = 1):
        with self._lock:
            self._value += amount

    @property
    def value(self) -> int:
        with self._lock:
            return self._value


class ThreadSafeCache:
    """Read-write lock for cache (multiple readers, single writer)."""

    def __init__(self):
        self._cache: dict = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Any:
        with self._lock:
            return self._cache.get(key)

    def set(self, key: str, value: Any):
        with self._lock:
            self._cache[key] = value

    def get_or_set(self, key: str, factory: Callable) -> Any:
        with self._lock:
            if key not in self._cache:
                self._cache[key] = factory()
            return self._cache[key]


# --- Parallel map with progress ---

def parallel_map(func: Callable[[T], Any], items: list[T],
                 max_workers: int = 10,
                 use_processes: bool = False) -> list:
    """Map function over items with progress tracking."""
    Executor = ProcessPoolExecutor if use_processes else ThreadPoolExecutor
    total = len(items)
    results = [None] * total
    completed = 0

    with Executor(max_workers=max_workers) as executor:
        future_to_idx = {
            executor.submit(func, item): i
            for i, item in enumerate(items)
        }

        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                results[idx] = future.result()
            except Exception as e:
                results[idx] = e
            completed += 1
            if completed % 100 == 0 or completed == total:
                logger.info("Progress: %d/%d", completed, total)

    return results
```

Concurrency rules:
1. **Threads for I/O** — HTTP requests, file I/O, database queries (GIL doesn't matter)
2. **Processes for CPU** — math, image processing, data crunching (bypass GIL)
3. **`as_completed`** — process results as they finish, not in submission order
4. **Queue for producer-consumer** — thread-safe work distribution
5. **Lock for shared state** — always protect mutable shared data'''
    ),
    (
        "python/synchronization",
        "Show Python synchronization primitives: locks, events, semaphores, barriers, and thread-safe patterns.",
        '''Synchronization primitives and patterns:

```python
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable


# --- Read-write lock ---

class ReadWriteLock:
    """Multiple concurrent readers, exclusive writer."""

    def __init__(self):
        self._readers = 0
        self._readers_lock = threading.Lock()
        self._write_lock = threading.Lock()

    @contextmanager
    def read(self):
        with self._readers_lock:
            self._readers += 1
            if self._readers == 1:
                self._write_lock.acquire()
        try:
            yield
        finally:
            with self._readers_lock:
                self._readers -= 1
                if self._readers == 0:
                    self._write_lock.release()

    @contextmanager
    def write(self):
        self._write_lock.acquire()
        try:
            yield
        finally:
            self._write_lock.release()


# Usage:
class ThreadSafeDict:
    def __init__(self):
        self._data = {}
        self._rw_lock = ReadWriteLock()

    def get(self, key: str) -> Any:
        with self._rw_lock.read():
            return self._data.get(key)

    def set(self, key: str, value: Any):
        with self._rw_lock.write():
            self._data[key] = value


# --- Semaphore for rate limiting ---

class ConnectionPool:
    """Limit concurrent connections using semaphore."""

    def __init__(self, max_connections: int = 10):
        self._semaphore = threading.Semaphore(max_connections)
        self._connections: list = []
        self._lock = threading.Lock()

    @contextmanager
    def acquire(self):
        self._semaphore.acquire()
        conn = self._get_connection()
        try:
            yield conn
        finally:
            self._release_connection(conn)
            self._semaphore.release()

    def _get_connection(self):
        with self._lock:
            if self._connections:
                return self._connections.pop()
        return create_new_connection()

    def _release_connection(self, conn):
        with self._lock:
            self._connections.append(conn)


# --- Event for signaling between threads ---

class GracefulShutdown:
    """Coordinate shutdown across threads."""

    def __init__(self):
        self._stop_event = threading.Event()

    def request_shutdown(self):
        self._stop_event.set()

    def should_stop(self) -> bool:
        return self._stop_event.is_set()

    def wait(self, timeout: float = None) -> bool:
        return self._stop_event.wait(timeout)

# Usage:
# shutdown = GracefulShutdown()
#
# def worker():
#     while not shutdown.should_stop():
#         process_next_item()
#
# # In main thread:
# signal.signal(signal.SIGTERM, lambda *_: shutdown.request_shutdown())


# --- Barrier for synchronized phases ---

def parallel_phases(n_workers: int, phases: list[Callable]):
    """Run workers through synchronized phases."""
    barrier = threading.Barrier(n_workers)
    results = [[] for _ in range(n_workers)]

    def worker(worker_id: int):
        for phase_fn in phases:
            result = phase_fn(worker_id)
            results[worker_id].append(result)
            barrier.wait()  # All workers must finish phase before next

    threads = [
        threading.Thread(target=worker, args=(i,))
        for i in range(n_workers)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


# --- Once (lazy initialization) ---

class Once:
    """Execute initialization exactly once, thread-safely."""

    def __init__(self):
        self._done = False
        self._lock = threading.Lock()
        self._result = None

    def do(self, func: Callable, *args, **kwargs) -> Any:
        if self._done:
            return self._result
        with self._lock:
            if not self._done:
                self._result = func(*args, **kwargs)
                self._done = True
        return self._result

# Usage:
# _init = Once()
# def get_config():
#     return _init.do(load_config_from_file)


# --- Debounce (delay until activity stops) ---

class Debouncer:
    """Call function only after delay with no new calls."""

    def __init__(self, delay: float, func: Callable):
        self.delay = delay
        self.func = func
        self._timer: threading.Timer = None
        self._lock = threading.Lock()

    def __call__(self, *args, **kwargs):
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(
                self.delay, self.func, args, kwargs
            )
            self._timer.start()

    def cancel(self):
        with self._lock:
            if self._timer:
                self._timer.cancel()

# Usage:
# save = Debouncer(1.0, save_to_disk)
# save(data)  # Starts 1s timer
# save(data)  # Resets timer (previous call canceled)
# save(data)  # Resets again — only final call executes
```

Synchronization patterns:
1. **Read-write lock** — multiple readers, exclusive writer (better than plain lock)
2. **Semaphore** — limit concurrent access to a resource
3. **Event** — signal between threads (graceful shutdown, ready notification)
4. **Barrier** — synchronize threads at phase boundaries
5. **Once** — thread-safe lazy initialization (singleton pattern)'''
    ),
]
