"""Async/concurrency training pairs: race condition patterns (all thinking)."""

pairs = [
    {
        "instruction": r'''I have a TOCTOU (time-of-check-to-time-of-use) race condition in my Python code. The file exists when I check, but disappears before I read it. How do I fix this class of bugs?''',
        "output": r'''<think>
TOCTOU is a classic race condition pattern where the world changes between checking a condition and acting on it. The canonical example is:

if os.path.exists(filepath):
    data = open(filepath).read()  # file might be deleted between check and open!

But TOCTOU appears in many forms:
- Checking if a user has permission, then performing the action
- Checking if a database row exists, then inserting
- Checking if a lock file exists, then creating one

The general fix is to eliminate the gap between check and use by making them atomic. In file operations, this means using try/except instead of check-then-act. For databases, use INSERT ... ON CONFLICT or SELECT FOR UPDATE. For locks, use atomic operations like os.open() with O_CREAT | O_EXCL.

Actually, I should be more precise. The fix depends on what we are trying to do:
1. If we want to read a file that might not exist: try/except (EAFP)
2. If we want to create a file only if it does not exist: O_CREAT | O_EXCL
3. If we want to update a value atomically: compare-and-swap or database transactions

I should show multiple examples of the pattern and fix.
</think>

TOCTOU bugs occur when a condition changes between checking it and acting on it. The fix is to make check-and-act atomic:

```python
import os
import errno
import tempfile
import sqlite3
from pathlib import Path
from typing import Optional, Any

# ============================================================
# Example 1: File operations
# ============================================================

# BAD: TOCTOU -- file can disappear between check and read
def read_config_bad(path: str) -> Optional[str]:
    if os.path.exists(path):  # CHECK
        # Another process could delete the file HERE
        with open(path) as f:  # USE -- may raise FileNotFoundError!
            return f.read()
    return None

# GOOD: EAFP (Easier to Ask Forgiveness than Permission)
def read_config_good(path: str) -> Optional[str]:
    try:
        with open(path) as f:  # atomic check+use
            return f.read()
    except FileNotFoundError:
        return None

# BAD: TOCTOU -- another process can create the file first
def create_file_bad(path: str, content: str):
    if not os.path.exists(path):  # CHECK
        # Another process creates the file HERE
        with open(path, "w") as f:  # USE -- overwrites!
            f.write(content)

# GOOD: atomic create-if-not-exists
def create_file_good(path: str, content: str) -> bool:
    try:
        # O_CREAT | O_EXCL fails if file already exists (atomic)
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        try:
            os.write(fd, content.encode())
            return True
        finally:
            os.close(fd)
    except FileExistsError:
        return False

# ============================================================
# Example 2: Lock files
# ============================================================

# BAD: TOCTOU lock
def acquire_lock_bad(lockfile: str) -> bool:
    if not os.path.exists(lockfile):  # CHECK
        # Race: another process creates it HERE
        with open(lockfile, "w") as f:  # USE
            f.write(str(os.getpid()))
        return True
    return False

# GOOD: atomic lock file
def acquire_lock_good(lockfile: str) -> bool:
    try:
        fd = os.open(lockfile, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False

def release_lock(lockfile: str):
    try:
        os.unlink(lockfile)
    except FileNotFoundError:
        pass

# ============================================================
# Example 3: Database TOCTOU
# ============================================================

def get_or_create_user_bad(db: sqlite3.Connection, email: str) -> int:
    """BAD: race between SELECT and INSERT."""
    cursor = db.execute(
        "SELECT id FROM users WHERE email = ?", (email,)
    )
    row = cursor.fetchone()
    if row is None:  # CHECK
        # Another connection inserts the same email HERE
        db.execute(
            "INSERT INTO users (email) VALUES (?)", (email,)
        )  # USE -- may violate unique constraint!
        db.commit()
        cursor = db.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        )
        row = cursor.fetchone()
    return row[0]

def get_or_create_user_good(db: sqlite3.Connection, email: str) -> int:
    """GOOD: use INSERT ... ON CONFLICT (atomic)."""
    db.execute(
        "INSERT INTO users (email) VALUES (?) "
        "ON CONFLICT (email) DO NOTHING",
        (email,),
    )
    db.commit()
    cursor = db.execute(
        "SELECT id FROM users WHERE email = ?", (email,)
    )
    return cursor.fetchone()[0]

# ============================================================
# Example 4: Atomic temp file + rename pattern
# ============================================================

def safe_write(path: str, content: str):
    """Write to a file atomically using temp + rename."""
    dir_name = os.path.dirname(path) or "."
    # Write to a temp file in the same directory
    fd, tmp_path = tempfile.mkstemp(dir=dir_name)
    try:
        os.write(fd, content.encode())
        os.close(fd)
        # os.rename is atomic on the same filesystem (POSIX)
        os.rename(tmp_path, path)
    except BaseException:
        os.close(fd)
        os.unlink(tmp_path)
        raise

# ============================================================
# General TOCTOU prevention rules
# ============================================================

# 1. EAFP over LBYL: try the operation, catch the error
# 2. Use atomic operations: O_CREAT|O_EXCL, rename, INSERT ON CONFLICT
# 3. Use database transactions for multi-step operations
# 4. Use file locking (fcntl.flock) when atomic ops are not sufficient
# 5. Use temp file + rename for atomic file writes

if __name__ == "__main__":
    # Demo safe write
    safe_write("/tmp/test_toctou.txt", "atomic content")
    content = read_config_good("/tmp/test_toctou.txt")
    print(f"Content: {content}")
```

The core principle: never separate the check from the action. Either make them a single atomic operation, or use try/except to handle the race gracefully.'''
    },
    {
        "instruction": r'''Is Python's double-checked locking pattern safe? I am trying to implement a thread-safe singleton and I am not sure if my implementation has a race condition.''',
        "output": r'''<think>
Double-checked locking is a pattern to avoid acquiring a lock on every access by first checking without the lock, then rechecking with the lock. In languages like Java and C++, this pattern is notoriously tricky because of memory reordering -- a thread might see a partially constructed object.

In Python, the situation is different. Due to the GIL, there is no memory reordering issue within CPython. However, double-checked locking in Python is still subtly wrong without proper synchronization because:

1. The GIL does not guarantee that assignment is atomic for complex objects. Well, actually in CPython it is (STORE_NAME is a single bytecode), but this is an implementation detail.

2. The real issue is: can a thread see a partially initialized instance? In CPython, object construction (__init__) completes before the reference is stored, so another thread either sees None or the fully constructed object. But this is again a CPython implementation detail.

Actually, for practical Python, the simplest and safest singleton patterns are:
1. Module-level instance (Python modules are singletons)
2. Class with __new__ and a lock
3. Using a decorator

Let me show the common approaches and why the simple ones are better than double-checked locking.
</think>

Double-checked locking in Python works in CPython due to the GIL, but it is fragile and unnecessary. Here are safer patterns:

```python
import threading
from typing import Any, Optional

# ============================================================
# Approach 1: Double-checked locking (works but fragile)
# ============================================================

class SingletonDCL:
    """Double-checked locking -- works in CPython but not portable."""
    _instance: Optional["SingletonDCL"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:       # First check (no lock)
            with cls._lock:
                if cls._instance is None:  # Second check (with lock)
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self, value: str = "default"):
        if not self._initialized:
            self.value = value
            self._initialized = True

# Works in CPython because:
# 1. GIL prevents memory reordering
# 2. Reference assignment is atomic (single bytecode)
# But NOT guaranteed by the Python language spec!

# ============================================================
# Approach 2: Simple lock (always safe, negligible overhead)
# ============================================================

class SingletonLocked:
    """Always acquire the lock -- simplest correct approach."""
    _instance: Optional["SingletonLocked"] = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
        return cls._instance

    def __init__(self, value: str = "default"):
        with self._lock:
            if not self._initialized:
                self.value = value
                self._initialized = True

# ============================================================
# Approach 3: Module-level instance (BEST for Python)
# ============================================================

# config.py
class _Config:
    def __init__(self):
        self.db_url = "postgres://localhost/mydb"
        self.debug = False

# Module is only imported once -- this IS the singleton
config = _Config()

# Usage: from config import config
# No locking needed -- Python's import system handles it

# ============================================================
# Approach 4: Metaclass singleton (reusable pattern)
# ============================================================

class SingletonMeta(type):
    """Metaclass that ensures only one instance per class."""
    _instances: dict[type, Any] = {}
    _lock = threading.Lock()

    def __call__(cls, *args, **kwargs):
        with cls._lock:
            if cls not in cls._instances:
                instance = super().__call__(*args, **kwargs)
                cls._instances[cls] = instance
        return cls._instances[cls]

class Database(metaclass=SingletonMeta):
    def __init__(self, url: str = "sqlite:///db.sqlite"):
        self.url = url
        self.connected = False

    def connect(self):
        self.connected = True

# Usage
db1 = Database("postgres://localhost/mydb")
db2 = Database("different_url")  # returns same instance!
assert db1 is db2

# ============================================================
# Approach 5: functools.cache (Python 3.9+ lazy singleton)
# ============================================================

from functools import cache

@cache
def get_database():
    """Cached function -- called once, result reused."""
    return Database()

# Thread-safe in CPython because @cache uses a lock internally

# ============================================================
# Verification
# ============================================================

def verify_singleton():
    instances = []

    def create_instance():
        inst = Database()
        instances.append(id(inst))

    threads = [
        threading.Thread(target=create_instance)
        for _ in range(100)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    unique_ids = set(instances)
    assert len(unique_ids) == 1, f"Got {len(unique_ids)} instances!"
    print(f"Singleton verified: {len(instances)} calls, 1 instance")

if __name__ == "__main__":
    verify_singleton()
```

Recommendations:
- Use a module-level instance (approach 3) -- simplest and most Pythonic
- Use metaclass (approach 4) when you need multiple singleton classes
- Avoid double-checked locking -- it adds complexity for no real benefit in Python
- The lock overhead in approach 2 is negligible (microseconds per call)'''
    },
    {
        "instruction": r'''How do I implement a thread-safe producer-consumer pattern in Python? I need multiple producers and consumers processing a shared work queue without data corruption.''',
        "output": r'''<think>
Producer-consumer is a fundamental concurrency pattern. In Python, the cleanest implementation uses queue.Queue which is already thread-safe. But I should show some deeper patterns:

1. Basic queue.Queue producer-consumer
2. Graceful shutdown with poison pills vs Event
3. Multiple producers, multiple consumers
4. Bounded queue for backpressure
5. Priority queue variant

The tricky parts are:
- Shutdown coordination: how do consumers know when to stop? Poison pills (None sentinel per consumer) or a shared Event.
- Error handling: what happens when a consumer crashes? Need to ensure task_done() is called even on error.
- Backpressure: if producers are faster than consumers, the queue grows unbounded unless you use maxsize.

Let me show a production-quality implementation that handles all these.
</think>

Here is a complete producer-consumer implementation with proper shutdown and error handling:

```python
import threading
import queue
import time
import logging
import random
from typing import Any, Callable, Optional
from dataclasses import dataclass, field
from enum import Enum, auto

logger = logging.getLogger(__name__)

# ============================================================
# Basic producer-consumer with queue.Queue
# ============================================================

class WorkerState(Enum):
    IDLE = auto()
    BUSY = auto()
    STOPPED = auto()

@dataclass
class WorkItem:
    id: int
    payload: Any
    priority: int = 0
    created_at: float = field(default_factory=time.monotonic)

_SENTINEL = object()  # poison pill

class ProducerConsumerPipeline:
    """Thread-safe producer-consumer with graceful shutdown."""

    def __init__(
        self,
        num_consumers: int = 4,
        max_queue_size: int = 100,
        process_fn: Optional[Callable] = None,
    ):
        self._queue: queue.Queue = queue.Queue(maxsize=max_queue_size)
        self._results: queue.Queue = queue.Queue()
        self._num_consumers = num_consumers
        self._process_fn = process_fn or self._default_process
        self._consumers: list[threading.Thread] = []
        self._producers: list[threading.Thread] = []
        self._stats_lock = threading.Lock()
        self._processed = 0
        self._errors = 0

    @staticmethod
    def _default_process(item: WorkItem) -> Any:
        time.sleep(random.uniform(0.01, 0.1))
        return f"processed-{item.id}"

    def _consumer_loop(self, consumer_id: int):
        """Consumer thread main loop."""
        logger.debug("Consumer %d started", consumer_id)
        while True:
            item = self._queue.get()
            if item is _SENTINEL:
                self._queue.task_done()
                break
            try:
                result = self._process_fn(item)
                self._results.put((item.id, result))
                with self._stats_lock:
                    self._processed += 1
            except Exception as e:
                logger.error(
                    "Consumer %d error on item %d: %s",
                    consumer_id, item.id, e,
                )
                with self._stats_lock:
                    self._errors += 1
            finally:
                self._queue.task_done()
        logger.debug("Consumer %d stopped", consumer_id)

    def start(self):
        """Start consumer threads."""
        for i in range(self._num_consumers):
            t = threading.Thread(
                target=self._consumer_loop,
                args=(i,),
                name=f"consumer-{i}",
                daemon=False,
            )
            t.start()
            self._consumers.append(t)

    def submit(self, item: WorkItem, timeout: float = 30.0):
        """Submit a work item (blocks if queue is full)."""
        self._queue.put(item, timeout=timeout)

    def submit_batch(self, items: list[WorkItem]):
        """Submit multiple items."""
        for item in items:
            self.submit(item)

    def shutdown(self, wait: bool = True, timeout: float = 30.0):
        """Graceful shutdown: finish current work, then stop."""
        # Send one sentinel per consumer
        for _ in self._consumers:
            self._queue.put(_SENTINEL)

        if wait:
            # Wait for all items to be processed
            self._queue.join()
            for t in self._consumers:
                t.join(timeout=timeout)

        with self._stats_lock:
            stats = {
                "processed": self._processed,
                "errors": self._errors,
                "remaining": self._queue.qsize(),
            }
        return stats

    def get_results(self) -> list[tuple[int, Any]]:
        """Drain the results queue."""
        results = []
        while not self._results.empty():
            try:
                results.append(self._results.get_nowait())
            except queue.Empty:
                break
        return results

# ============================================================
# Usage
# ============================================================

def main():
    logging.basicConfig(level=logging.INFO)

    def heavy_process(item: WorkItem) -> dict:
        time.sleep(random.uniform(0.05, 0.15))
        return {"id": item.id, "result": item.payload.upper()}

    pipeline = ProducerConsumerPipeline(
        num_consumers=4,
        max_queue_size=50,
        process_fn=heavy_process,
    )
    pipeline.start()

    # Producer: submit work items
    start = time.monotonic()
    for i in range(100):
        pipeline.submit(WorkItem(id=i, payload=f"task-{i}"))

    # Shutdown and wait
    stats = pipeline.shutdown(wait=True)
    elapsed = time.monotonic() - start

    results = pipeline.get_results()
    print(f"Processed: {stats['processed']}")
    print(f"Errors: {stats['errors']}")
    print(f"Time: {elapsed:.2f}s")
    print(f"Results collected: {len(results)}")

if __name__ == "__main__":
    main()
```

Key design decisions:
- Bounded queue (`maxsize`) provides backpressure -- producers block when full
- Poison pill sentinel ensures each consumer stops exactly once
- `task_done()` in a `finally` block prevents join() from hanging on errors
- Non-daemon threads ensure cleanup completes before process exit
- Thread-safe stats via a dedicated lock'''
    },
    {
        "instruction": r'''How do I implement a read-write lock (RWLock) in Python? I have many readers and few writers, and I want readers to not block each other.''',
        "output": r'''<think>
A read-write lock allows multiple concurrent readers but only one writer (and no readers during writes). This is useful when reads vastly outnumber writes.

Python does not have a built-in RWLock, so I need to implement one. The standard approach uses:
- A mutex (Lock) to protect internal state
- A condition variable (Condition) for writer waiting
- A counter for active readers

There is a subtlety around writer starvation: if readers keep arriving, a writer might wait forever. I should show both a simple version (writer-starving) and a writer-preferring version.

The writer-preferring version adds a flag that prevents new readers from entering when a writer is waiting. This ensures writers get priority but can starve readers. A fair version alternates, but that is more complex.

For Python specifically, I should mention that the GIL already serializes access to Python objects, so a RWLock is most useful when protecting an external resource or when the critical section involves multiple operations that must be consistent.
</think>

Python lacks a built-in read-write lock. Here is a correct implementation with writer priority:

```python
import threading
import time
from typing import Any, Optional
from contextlib import contextmanager

class ReadWriteLock:
    """Read-write lock with writer priority.

    Multiple readers can hold the lock simultaneously.
    Writers get exclusive access (no readers or other writers).
    Writer priority prevents writer starvation.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._readers_ok = threading.Condition(self._lock)
        self._writers_ok = threading.Condition(self._lock)
        self._active_readers = 0
        self._active_writers = 0
        self._waiting_writers = 0

    def acquire_read(self):
        with self._lock:
            # Wait if a writer is active or waiting (writer priority)
            while self._active_writers > 0 or self._waiting_writers > 0:
                self._readers_ok.wait()
            self._active_readers += 1

    def release_read(self):
        with self._lock:
            self._active_readers -= 1
            if self._active_readers == 0:
                self._writers_ok.notify()

    def acquire_write(self):
        with self._lock:
            self._waiting_writers += 1
            while self._active_readers > 0 or self._active_writers > 0:
                self._writers_ok.wait()
            self._waiting_writers -= 1
            self._active_writers += 1

    def release_write(self):
        with self._lock:
            self._active_writers -= 1
            # Wake all waiting readers or one waiting writer
            if self._waiting_writers > 0:
                self._writers_ok.notify()
            else:
                self._readers_ok.notify_all()

    @contextmanager
    def read_lock(self):
        self.acquire_read()
        try:
            yield
        finally:
            self.release_read()

    @contextmanager
    def write_lock(self):
        self.acquire_write()
        try:
            yield
        finally:
            self.release_write()

# ============================================================
# Usage: thread-safe cache with RWLock
# ============================================================

class ThreadSafeCache:
    """Cache where reads are concurrent but writes are exclusive."""

    def __init__(self):
        self._data: dict[str, Any] = {}
        self._rw_lock = ReadWriteLock()

    def get(self, key: str) -> Optional[Any]:
        with self._rw_lock.read_lock():
            return self._data.get(key)

    def get_many(self, keys: list[str]) -> dict[str, Any]:
        with self._rw_lock.read_lock():
            return {k: self._data[k] for k in keys if k in self._data}

    def set(self, key: str, value: Any):
        with self._rw_lock.write_lock():
            self._data[key] = value

    def update(self, items: dict[str, Any]):
        with self._rw_lock.write_lock():
            self._data.update(items)

    def delete(self, key: str) -> bool:
        with self._rw_lock.write_lock():
            if key in self._data:
                del self._data[key]
                return True
            return False

    @property
    def size(self) -> int:
        with self._rw_lock.read_lock():
            return len(self._data)

# ============================================================
# Benchmark: RWLock vs plain Lock
# ============================================================

def benchmark():
    cache = ThreadSafeCache()
    plain_cache = {}
    plain_lock = threading.Lock()

    # Pre-populate
    for i in range(1000):
        cache.set(f"key-{i}", f"value-{i}")
        plain_cache[f"key-{i}"] = f"value-{i}"

    num_reads = 10000
    num_writes = 100

    # RWLock benchmark
    def rw_reader():
        for i in range(num_reads):
            cache.get(f"key-{i % 1000}")

    def rw_writer():
        for i in range(num_writes):
            cache.set(f"key-{i}", f"updated-{i}")

    start = time.monotonic()
    threads = [threading.Thread(target=rw_reader) for _ in range(8)]
    threads.append(threading.Thread(target=rw_writer))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    rw_time = time.monotonic() - start

    # Plain lock benchmark
    def plain_reader():
        for i in range(num_reads):
            with plain_lock:
                plain_cache.get(f"key-{i % 1000}")

    def plain_writer():
        for i in range(num_writes):
            with plain_lock:
                plain_cache[f"key-{i}"] = f"updated-{i}"

    start = time.monotonic()
    threads = [threading.Thread(target=plain_reader) for _ in range(8)]
    threads.append(threading.Thread(target=plain_writer))
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    plain_time = time.monotonic() - start

    print(f"RWLock: {rw_time:.3f}s")
    print(f"Plain Lock: {plain_time:.3f}s")
    print(f"Speedup: {plain_time / rw_time:.1f}x")

if __name__ == "__main__":
    benchmark()
```

Notes:
- Writer priority prevents writer starvation but can delay readers
- In CPython, the GIL limits the real-world benefit for pure Python operations
- RWLock shines when reads are expensive (complex data structures, external resources)
- For simple dict lookups, a plain Lock may be faster due to lower overhead'''
    },
    {
        "instruction": r'''How do I use atomic operations and compare-and-swap (CAS) patterns in Python to avoid race conditions without heavyweight locks?''',
        "output": r'''<think>
Atomic operations and CAS in Python -- this is interesting because Python does not have built-in CAS primitives like Java's AtomicInteger or C++'s compare_exchange. However, there are a few approaches:

1. Due to the GIL, certain operations on built-in types are "accidentally atomic" in CPython. Simple attribute assignments, dict[key] = value, and list.append() are single bytecodes. But compound operations like x += 1 are NOT atomic.

2. For true atomic operations, you can use:
   - threading.Lock (lightweight in CPython)
   - ctypes or multiprocessing.Value with lock=True
   - Python 3.13+ has PEP 703 (free-threading) considerations

3. For CAS-like patterns, you typically simulate it with a lock + compare. Or use database-level CAS (UPDATE ... WHERE version = X).

I should show practical patterns for lock-free-ish programming in Python, while being honest that Python does not support true lock-free programming in the way C++ or Java do.

Actually, the most practical approach for Python is just to use locks since they are fast under the GIL. But for the database CAS pattern and the optimistic concurrency pattern, those are genuinely useful.
</think>

Python lacks hardware-level CAS, but you can implement atomic patterns using the GIL and locks:

```python
import threading
import time
from typing import Any, Callable, Optional, TypeVar

T = TypeVar("T")

# ============================================================
# Atomic value with compare-and-swap
# ============================================================

class AtomicReference:
    """Thread-safe mutable reference with CAS support."""

    def __init__(self, value: Any = None):
        self._value = value
        self._lock = threading.Lock()

    def get(self) -> Any:
        with self._lock:
            return self._value

    def set(self, value: Any):
        with self._lock:
            self._value = value

    def compare_and_swap(self, expected: Any, new_value: Any) -> bool:
        """Set to new_value only if current value is expected.
        Returns True if swap succeeded.
        """
        with self._lock:
            if self._value is expected or self._value == expected:
                self._value = new_value
                return True
            return False

    def update(self, fn: Callable[[Any], Any]) -> Any:
        """Atomically update using a function. Returns new value."""
        with self._lock:
            self._value = fn(self._value)
            return self._value

    def get_and_set(self, new_value: Any) -> Any:
        """Atomically set new value and return old value."""
        with self._lock:
            old = self._value
            self._value = new_value
            return old

# ============================================================
# Atomic counter (most common use case)
# ============================================================

class AtomicCounter:
    """Fast thread-safe counter."""

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

    def compare_and_increment(self, expected: int) -> bool:
        """Increment only if current value equals expected."""
        with self._lock:
            if self._value == expected:
                self._value += 1
                return True
            return False

    @property
    def value(self) -> int:
        with self._lock:
            return self._value

# ============================================================
# Optimistic concurrency (CAS loop pattern)
# ============================================================

class OptimisticDict:
    """Dict with optimistic concurrency control.
    Readers never block. Writers retry on conflict.
    """

    def __init__(self):
        self._data: dict[str, tuple[Any, int]] = {}
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[tuple[Any, int]]:
        """Returns (value, version) or None."""
        with self._lock:
            entry = self._data.get(key)
            if entry is None:
                return None
            return entry  # (value, version)

    def put(self, key: str, value: Any) -> int:
        """Insert or overwrite. Returns new version."""
        with self._lock:
            existing = self._data.get(key)
            version = (existing[1] + 1) if existing else 1
            self._data[key] = (value, version)
            return version

    def cas_update(
        self, key: str, new_value: Any, expected_version: int
    ) -> bool:
        """Update only if the version matches (CAS)."""
        with self._lock:
            existing = self._data.get(key)
            if existing is None or existing[1] != expected_version:
                return False  # conflict -- caller must retry
            self._data[key] = (new_value, expected_version + 1)
            return True

    def update_with_retry(
        self,
        key: str,
        transform: Callable[[Any], Any],
        max_retries: int = 10,
    ) -> Any:
        """Read-modify-write with automatic retry on conflict."""
        for attempt in range(max_retries):
            entry = self.get(key)
            if entry is None:
                raise KeyError(key)

            current_value, version = entry
            new_value = transform(current_value)

            if self.cas_update(key, new_value, version):
                return new_value

            # Conflict: another thread updated -- retry
            time.sleep(0.001 * (attempt + 1))

        raise RuntimeError(
            f"CAS update failed after {max_retries} retries"
        )

# ============================================================
# Demo: concurrent counter updates with CAS
# ============================================================

def demo_cas():
    store = OptimisticDict()
    store.put("counter", 0)

    def increment_worker(n: int):
        for _ in range(n):
            store.update_with_retry(
                "counter", lambda v: v + 1
            )

    threads = [
        threading.Thread(target=increment_worker, args=(1000,))
        for _ in range(8)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    value, version = store.get("counter")
    print(f"Final counter: {value} (version {version})")
    # Expected: 8000

def demo_atomic():
    counter = AtomicCounter()

    def worker():
        for _ in range(10000):
            counter.increment()

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    print(f"Atomic counter: {counter.value}")  # 80000

if __name__ == "__main__":
    demo_atomic()
    demo_cas()
```

When to use each pattern:
- `AtomicCounter`/`AtomicReference` -- simple shared state, low contention
- `OptimisticDict` with CAS -- when reads vastly outnumber writes
- Plain `Lock` -- when critical sections are short and contention is low
- `RWLock` -- many concurrent readers, few writers, expensive reads'''
    },
]
