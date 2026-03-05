"""Python concurrency deep dive — multiprocessing, threading, GIL, concurrent.futures, shared memory."""

PAIRS = [
    (
        "python/multiprocessing-patterns",
        "Show Python multiprocessing patterns: process pools, shared memory, IPC, and when to use multiprocessing vs threading vs asyncio.",
        '''Python concurrency: choosing the right tool and using it well:

```python
import multiprocessing as mp
from multiprocessing import shared_memory
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
import threading
import asyncio
import time
import numpy as np
from typing import Callable

# --- When to use what ---
# CPU-bound (math, image processing, ML): multiprocessing
# I/O-bound (HTTP, DB, files):            asyncio (best) or threading
# Mixed:                                   process pool + async event loop

# --- ProcessPoolExecutor (simplest API) ---

def cpu_intensive(n: int) -> float:
    """Simulate CPU-bound work."""
    total = 0.0
    for i in range(n):
        total += i ** 0.5
    return total

def parallel_process(tasks: list[int], max_workers: int = None) -> list[float]:
    """Process CPU-bound tasks in parallel."""
    results = []
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        futures = {executor.submit(cpu_intensive, t): t for t in tasks}

        # Collect results as they complete
        for future in as_completed(futures):
            task = futures[future]
            try:
                result = future.result(timeout=60)
                results.append(result)
            except Exception as e:
                print(f"Task {task} failed: {e}")

    return results

# --- Shared Memory (zero-copy between processes) ---

def create_shared_array(data: np.ndarray) -> tuple[str, tuple, str]:
    """Create shared memory backed numpy array."""
    shm = shared_memory.SharedMemory(create=True, size=data.nbytes)
    shared_array = np.ndarray(data.shape, dtype=data.dtype, buffer=shm.buf)
    shared_array[:] = data[:]
    return shm.name, data.shape, str(data.dtype)

def worker_with_shared_memory(shm_name: str, shape: tuple, dtype: str,
                               start: int, end: int) -> float:
    """Worker that reads from shared memory (zero-copy)."""
    existing_shm = shared_memory.SharedMemory(name=shm_name)
    array = np.ndarray(shape, dtype=np.dtype(dtype), buffer=existing_shm.buf)

    # Process slice without copying
    result = float(array[start:end].sum())
    existing_shm.close()
    return result

def parallel_sum_shared(data: np.ndarray, n_workers: int = 4) -> float:
    """Sum large array using shared memory across processes."""
    shm_name, shape, dtype = create_shared_array(data)
    chunk_size = len(data) // n_workers

    try:
        with ProcessPoolExecutor(max_workers=n_workers) as executor:
            futures = []
            for i in range(n_workers):
                start = i * chunk_size
                end = start + chunk_size if i < n_workers - 1 else len(data)
                futures.append(executor.submit(
                    worker_with_shared_memory,
                    shm_name, shape, dtype, start, end,
                ))
            total = sum(f.result() for f in futures)
    finally:
        # Clean up shared memory
        shm = shared_memory.SharedMemory(name=shm_name)
        shm.close()
        shm.unlink()

    return total

# --- Producer-Consumer with multiprocessing.Queue ---

def producer_consumer_pipeline():
    """Multi-stage pipeline with queues."""
    input_queue = mp.Queue(maxsize=100)
    output_queue = mp.Queue(maxsize=100)
    sentinel = None  # Poison pill

    def producer(queue, n_items):
        for i in range(n_items):
            data = generate_data(i)
            queue.put(data)
        queue.put(sentinel)

    def worker(in_q, out_q):
        while True:
            item = in_q.get()
            if item is sentinel:
                in_q.put(sentinel)  # Pass sentinel to next worker
                break
            result = process_item(item)
            out_q.put(result)

    def consumer(queue, results):
        while True:
            item = queue.get()
            if item is sentinel:
                break
            results.append(item)

    # Start pipeline
    n_workers = mp.cpu_count()
    manager = mp.Manager()
    results = manager.list()

    prod = mp.Process(target=producer, args=(input_queue, 10000))
    workers = [mp.Process(target=worker, args=(input_queue, output_queue))
               for _ in range(n_workers)]
    cons = mp.Process(target=consumer, args=(output_queue, results))

    prod.start()
    for w in workers:
        w.start()
    cons.start()

    prod.join()
    for w in workers:
        w.join()
    output_queue.put(sentinel)
    cons.join()

    return list(results)

# --- Threading for I/O-bound (with rate limiting) ---

def fetch_urls_threaded(urls: list[str], max_concurrent: int = 10) -> list[dict]:
    """Fetch multiple URLs with thread pool and rate limiting."""
    import urllib.request
    semaphore = threading.Semaphore(max_concurrent)
    results = []
    lock = threading.Lock()

    def fetch_one(url: str):
        with semaphore:  # Limit concurrency
            try:
                with urllib.request.urlopen(url, timeout=10) as resp:
                    data = resp.read()
                with lock:
                    results.append({"url": url, "size": len(data), "status": 200})
            except Exception as e:
                with lock:
                    results.append({"url": url, "error": str(e)})

    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        executor.map(fetch_one, urls)

    return results

# --- Async + multiprocessing hybrid ---

async def hybrid_pipeline(urls: list[str]) -> list[dict]:
    """Fetch URLs async, process CPU-bound in process pool."""
    import aiohttp

    # I/O phase: async fetch
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_async(session, url) for url in urls]
        raw_data = await asyncio.gather(*tasks, return_exceptions=True)

    # CPU phase: process pool
    loop = asyncio.get_event_loop()
    with ProcessPoolExecutor() as pool:
        futures = [
            loop.run_in_executor(pool, cpu_intensive_transform, data)
            for data in raw_data if not isinstance(data, Exception)
        ]
        results = await asyncio.gather(*futures)

    return results
```

Decision matrix:
| Workload | Best Tool | Why |
|----------|-----------|-----|
| Many HTTP calls | asyncio | Non-blocking I/O, 10K+ concurrent |
| File I/O | threading | GIL released during I/O ops |
| Math/ML | multiprocessing | Bypasses GIL, true parallelism |
| Mixed | async + process pool | Best of both worlds |
| Shared numpy | shared_memory | Zero-copy across processes |'''
    ),
    (
        "python/context-managers-advanced",
        "Show advanced context manager patterns in Python: nested contexts, async context managers, reentrant locks, and resource lifecycle management.",
        '''Advanced context manager patterns:

```python
from contextlib import contextmanager, asynccontextmanager, ExitStack, AsyncExitStack
from typing import Generator, AsyncGenerator, Optional
import asyncio
import threading
import time

# --- Composable resource management ---

@contextmanager
def database_connection(url: str):
    """Manage database connection lifecycle."""
    conn = connect(url)
    try:
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
    finally:
        conn.close()

@contextmanager
def database_transaction(conn):
    """Nested transaction (savepoint)."""
    savepoint = conn.execute("SAVEPOINT sp1")
    try:
        yield conn
    except Exception:
        conn.execute("ROLLBACK TO SAVEPOINT sp1")
        raise
    else:
        conn.execute("RELEASE SAVEPOINT sp1")

# Composable usage:
# with database_connection(url) as conn:
#     with database_transaction(conn):
#         conn.execute("INSERT ...")

# --- ExitStack for dynamic resource management ---

def process_files(file_paths: list[str]) -> list[str]:
    """Open variable number of files safely."""
    results = []
    with ExitStack() as stack:
        files = [
            stack.enter_context(open(path))
            for path in file_paths
        ]
        # All files open, process together
        for f in files:
            results.append(f.read())
    # All files closed, even if one fails
    return results

def conditional_resources(use_cache: bool, use_metrics: bool):
    """Conditionally acquire resources."""
    with ExitStack() as stack:
        db = stack.enter_context(database_connection(DB_URL))

        cache = None
        if use_cache:
            cache = stack.enter_context(redis_connection(REDIS_URL))

        metrics = None
        if use_metrics:
            metrics = stack.enter_context(metrics_client(METRICS_URL))

        return do_work(db, cache, metrics)

# --- Async context managers ---

@asynccontextmanager
async def async_http_session():
    """Manage aiohttp session lifecycle."""
    import aiohttp
    session = aiohttp.ClientSession()
    try:
        yield session
    finally:
        await session.close()

@asynccontextmanager
async def async_timeout(seconds: float):
    """Timeout context for async operations."""
    task = asyncio.current_task()
    loop = asyncio.get_event_loop()
    handle = loop.call_later(seconds, task.cancel)
    try:
        yield
    except asyncio.CancelledError:
        raise TimeoutError(f"Operation timed out after {seconds}s")
    finally:
        handle.cancel()

# --- Reentrant context manager ---

class ReentrantResource:
    """Context manager that can be entered multiple times."""
    def __init__(self):
        self._lock = threading.RLock()
        self._count = 0
        self._resource = None

    def __enter__(self):
        self._lock.acquire()
        self._count += 1
        if self._count == 1:
            self._resource = expensive_setup()
        return self._resource

    def __exit__(self, *exc):
        self._count -= 1
        if self._count == 0:
            self._resource.cleanup()
            self._resource = None
        self._lock.release()

# --- Timing context manager ---

@contextmanager
def timer(label: str) -> Generator[dict, None, None]:
    """Measure execution time of a block."""
    result = {"label": label}
    start = time.perf_counter()
    try:
        yield result
    finally:
        result["elapsed"] = time.perf_counter() - start
        result["elapsed_ms"] = result["elapsed"] * 1000

# Usage:
# with timer("database_query") as t:
#     run_query()
# print(f"{t['label']}: {t['elapsed_ms']:.2f}ms")

# --- Redirect/capture context managers ---

@contextmanager
def temporary_env(**env_vars):
    """Temporarily set environment variables."""
    import os
    old_values = {}
    for key, value in env_vars.items():
        old_values[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

# Usage:
# with temporary_env(DATABASE_URL="sqlite:///test.db", DEBUG="1"):
#     run_tests()

# --- Class-based async context manager ---

class ManagedPool:
    """Async connection pool with lifecycle management."""
    def __init__(self, url: str, min_size: int = 5, max_size: int = 20):
        self.url = url
        self.min_size = min_size
        self.max_size = max_size
        self.pool = None

    async def __aenter__(self):
        self.pool = await create_pool(
            self.url, min_size=self.min_size, max_size=self.max_size
        )
        return self.pool

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.pool:
            await self.pool.close()
        return False  # Don't suppress exceptions
```

Context manager selection:
- **`@contextmanager`** — simple setup/teardown with generator syntax
- **`ExitStack`** — dynamic number of resources, conditional acquisition
- **`__enter__/__exit__`** — stateful, reentrant, or complex lifecycle
- **`@asynccontextmanager`** — async setup/teardown
- **`AsyncExitStack`** — dynamic async resources'''
    ),
    (
        "python/descriptors-metaclasses",
        "Explain Python descriptors and metaclasses with practical examples: validation descriptors, ORM-style field definitions, and plugin registration.",
        '''Python descriptors and metaclasses for framework-level code:

```python
from typing import Any, Optional, Callable
import weakref

# --- Descriptors: control attribute access ---

class Validated:
    """Descriptor that validates on set."""

    def __init__(self, validator: Callable[[Any], bool], error_msg: str = "Invalid value"):
        self.validator = validator
        self.error_msg = error_msg
        self.data = weakref.WeakKeyDictionary()

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return self.data.get(obj)

    def __set__(self, obj, value):
        if not self.validator(value):
            raise ValueError(f"{self.name}: {self.error_msg} (got {value!r})")
        self.data[obj] = value

# Reusable validators
def positive(x): return isinstance(x, (int, float)) and x > 0
def non_empty_string(x): return isinstance(x, str) and len(x.strip()) > 0
def in_range(lo, hi): return lambda x: lo <= x <= hi

class Product:
    name = Validated(non_empty_string, "must be non-empty string")
    price = Validated(positive, "must be positive number")
    quantity = Validated(lambda x: isinstance(x, int) and x >= 0, "must be non-negative int")
    rating = Validated(in_range(0, 5), "must be 0-5")

    def __init__(self, name: str, price: float, quantity: int):
        self.name = name
        self.price = price
        self.quantity = quantity
        self.rating = 0

# p = Product("Widget", -5, 10)  # ValueError: price: must be positive number

# --- ORM-style field descriptor ---

class Field:
    """Database column descriptor (SQLAlchemy-like)."""

    def __init__(self, column_type: str, primary_key: bool = False,
                 nullable: bool = True, default: Any = None):
        self.column_type = column_type
        self.primary_key = primary_key
        self.nullable = nullable
        self.default = default
        self.data = weakref.WeakKeyDictionary()

    def __set_name__(self, owner, name):
        self.name = name
        self.column_name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return self.data.get(obj, self.default)

    def __set__(self, obj, value):
        if value is None and not self.nullable:
            raise ValueError(f"{self.name} cannot be NULL")
        self.data[obj] = value

# --- Metaclass for model registration ---

class ModelRegistry:
    _models: dict[str, type] = {}

    @classmethod
    def register(cls, model_class):
        table_name = getattr(model_class, '__tablename__',
                             model_class.__name__.lower())
        cls._models[table_name] = model_class

    @classmethod
    def get_model(cls, table_name: str) -> Optional[type]:
        return cls._models.get(table_name)

class ModelMeta(type):
    """Metaclass that auto-registers models and collects fields."""

    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)

        # Skip base Model class
        if name == 'Model':
            return cls

        # Collect field descriptors
        fields = {}
        for key, value in namespace.items():
            if isinstance(value, Field):
                fields[key] = value
        cls._fields = fields

        # Auto-generate __tablename__ if not set
        if '__tablename__' not in namespace:
            # CamelCase to snake_case
            import re
            cls.__tablename__ = re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()

        # Register model
        ModelRegistry.register(cls)

        return cls

class Model(metaclass=ModelMeta):
    """Base model class."""

    def __init__(self, **kwargs):
        for name, field in self._fields.items():
            value = kwargs.get(name, field.default)
            setattr(self, name, value)

    def to_dict(self) -> dict:
        return {name: getattr(self, name) for name in self._fields}

    def __repr__(self):
        fields = ", ".join(f"{k}={v!r}" for k, v in self.to_dict().items())
        return f"{self.__class__.__name__}({fields})"

# Usage (auto-registered, fields collected):
class UserProfile(Model):
    id = Field("INTEGER", primary_key=True, nullable=False)
    username = Field("VARCHAR(100)", nullable=False)
    email = Field("VARCHAR(255)", nullable=False)
    bio = Field("TEXT", default="")

user = UserProfile(id=1, username="alice", email="alice@example.com")
print(user)  # UserProfile(id=1, username='alice', email='alice@example.com', bio='')
print(UserProfile._fields)  # {'id': <Field>, 'username': <Field>, ...}
print(UserProfile.__tablename__)  # 'user_profile'

# --- Plugin system with metaclass ---

class PluginMeta(type):
    plugins: dict[str, type] = {}

    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        if bases:  # Don't register the base class itself
            plugin_name = namespace.get("name", name.lower())
            mcs.plugins[plugin_name] = cls
        return cls

class Plugin(metaclass=PluginMeta):
    name: str = ""
    def execute(self, data): raise NotImplementedError

class JsonPlugin(Plugin):
    name = "json"
    def execute(self, data): return json.dumps(data)

class CsvPlugin(Plugin):
    name = "csv"
    def execute(self, data): return to_csv(data)

# Auto-discovered:
# PluginMeta.plugins == {"json": JsonPlugin, "csv": CsvPlugin}
```

When to use:
- **Descriptors** — reusable attribute behavior (validation, lazy loading, caching)
- **`__set_name__`** — descriptor knows its attribute name (Python 3.6+)
- **Metaclasses** — auto-registration, field collection, DSL-like APIs
- **`__init_subclass__`** — simpler alternative to metaclasses for subclass hooks'''
    ),
]
