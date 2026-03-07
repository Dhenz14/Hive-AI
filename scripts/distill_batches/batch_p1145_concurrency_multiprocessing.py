"""Async/concurrency training pairs: Python multiprocessing."""

pairs = [
    {
        "instruction": r'''How do I use Python's multiprocessing.Pool and ProcessPoolExecutor for CPU-bound parallelism? What are the key differences?''',
        "output": r'''<think>
There are two main APIs for process pools in Python:
1. multiprocessing.Pool -- older, more features (initializer, maxtasksperchild, starmap)
2. concurrent.futures.ProcessPoolExecutor -- newer, cleaner API, integrates with asyncio

The key differences:
- Pool has starmap() for multiple arguments; ProcessPoolExecutor only has map() and submit()
- Pool has maxtasksperchild to restart workers periodically (good for memory leaks)
- ProcessPoolExecutor returns Future objects that work with as_completed()
- ProcessPoolExecutor integrates with asyncio via loop.run_in_executor()

Both use pickle to serialize data between processes, which is a major limitation. Large objects are slow to pickle, and some objects cannot be pickled at all (lambdas, closures, file handles).

I should show both APIs and when to prefer each.
</think>

Both APIs create worker processes for true parallelism. Here are the differences:

```python
import multiprocessing
import concurrent.futures
import time
import math
from typing import Any

# ============================================================
# CPU-bound work function (must be defined at module level)
# ============================================================

def compute_prime_count(n: int) -> dict[str, Any]:
    """Count primes up to n using trial division."""
    count = 0
    for num in range(2, n + 1):
        if all(num % i != 0 for i in range(2, int(math.sqrt(num)) + 1)):
            count += 1
    return {"n": n, "prime_count": count}

def init_worker(shared_value):
    """Initializer for Pool workers."""
    global SHARED_CONFIG
    SHARED_CONFIG = shared_value

# ============================================================
# multiprocessing.Pool
# ============================================================

def with_pool():
    numbers = [50000, 60000, 70000, 80000]

    start = time.monotonic()
    with multiprocessing.Pool(processes=4) as pool:
        # map() -- ordered results
        results = pool.map(compute_prime_count, numbers)

        # imap() -- lazy iterator (memory efficient)
        for result in pool.imap(compute_prime_count, numbers):
            print(f"n={result['n']}: {result['prime_count']} primes")

        # imap_unordered() -- results as they complete (fastest)
        for result in pool.imap_unordered(compute_prime_count, numbers):
            print(f"Completed: n={result['n']}")

        # apply_async() -- single task, non-blocking
        future = pool.apply_async(compute_prime_count, (50000,))
        result = future.get(timeout=30)

    elapsed = time.monotonic() - start
    print(f"Pool: {elapsed:.2f}s")

# Pool with initializer and maxtasksperchild
def with_pool_advanced():
    with multiprocessing.Pool(
        processes=4,
        initializer=init_worker,
        initargs=("config_value",),
        maxtasksperchild=100,  # restart worker after 100 tasks
    ) as pool:
        results = pool.map(compute_prime_count, range(1000, 5000, 1000))
    return results

# ============================================================
# concurrent.futures.ProcessPoolExecutor
# ============================================================

def with_executor():
    numbers = [50000, 60000, 70000, 80000]

    start = time.monotonic()
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        # map() -- ordered results
        results = list(pool.map(compute_prime_count, numbers))

        # submit() + as_completed() -- results as they finish
        futures = {
            pool.submit(compute_prime_count, n): n
            for n in numbers
        }
        for future in concurrent.futures.as_completed(futures):
            n = futures[future]
            try:
                result = future.result()
                print(f"n={n}: {result['prime_count']} primes")
            except Exception as e:
                print(f"n={n} failed: {e}")

    elapsed = time.monotonic() - start
    print(f"Executor: {elapsed:.2f}s")

# ============================================================
# ProcessPoolExecutor with asyncio
# ============================================================

import asyncio

async def async_cpu_work():
    """Run CPU-bound work from async code."""
    loop = asyncio.get_running_loop()
    numbers = [50000, 60000, 70000, 80000]

    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as pool:
        tasks = [
            loop.run_in_executor(pool, compute_prime_count, n)
            for n in numbers
        ]
        results = await asyncio.gather(*tasks)

    for r in results:
        print(f"n={r['n']}: {r['prime_count']} primes")
    return results

# ============================================================
# Comparison summary
# ============================================================

# multiprocessing.Pool:
#   + starmap() for multi-arg functions
#   + maxtasksperchild (prevents memory leaks)
#   + imap_unordered() for streaming results
#   - Older API, less composable
#
# ProcessPoolExecutor:
#   + Clean Future-based API
#   + Works with asyncio via run_in_executor()
#   + as_completed() for progress tracking
#   - No starmap or maxtasksperchild

if __name__ == "__main__":
    with_pool()
    with_executor()
```

Use `Pool` when you need `starmap`, `maxtasksperchild`, or `imap_unordered`. Use `ProcessPoolExecutor` when you want `Future` objects, `as_completed()`, or asyncio integration.'''
    },
    {
        "instruction": r'''How do I share data between processes in Python multiprocessing? Show shared memory, queues, and pipes.''',
        "output": r'''```python
import multiprocessing
from multiprocessing import shared_memory
import numpy as np
import time
from typing import Any

# ============================================================
# 1. multiprocessing.Queue -- simplest IPC
# ============================================================

def queue_producer(q: multiprocessing.Queue, items: list):
    for item in items:
        q.put(item)
    q.put(None)  # sentinel

def queue_consumer(q: multiprocessing.Queue, results: list):
    while True:
        item = q.get()
        if item is None:
            break
        results.append(item * 2)

def queue_example():
    q = multiprocessing.Queue(maxsize=100)
    manager = multiprocessing.Manager()
    results = manager.list()  # shared list across processes

    p1 = multiprocessing.Process(
        target=queue_producer, args=(q, list(range(20)))
    )
    p2 = multiprocessing.Process(
        target=queue_consumer, args=(q, results)
    )
    p1.start()
    p2.start()
    p1.join()
    p2.join()
    print(f"Queue results: {list(results)[:5]}...")

# ============================================================
# 2. multiprocessing.Pipe -- fast two-way communication
# ============================================================

def pipe_worker(conn):
    """Worker receives tasks and sends results via pipe."""
    while True:
        msg = conn.recv()
        if msg is None:
            break
        task_id, data = msg
        result = sum(data)  # process the data
        conn.send((task_id, result))
    conn.close()

def pipe_example():
    parent_conn, child_conn = multiprocessing.Pipe()

    worker = multiprocessing.Process(
        target=pipe_worker, args=(child_conn,)
    )
    worker.start()

    # Send tasks
    for i in range(5):
        parent_conn.send((i, list(range(i * 100))))

    # Receive results
    for _ in range(5):
        task_id, result = parent_conn.recv()
        print(f"Task {task_id}: result={result}")

    parent_conn.send(None)  # shutdown signal
    worker.join()

# ============================================================
# 3. multiprocessing.Value and Array -- shared memory (simple)
# ============================================================

def increment_counter(counter, lock, n: int):
    for _ in range(n):
        with lock:
            counter.value += 1

def shared_value_example():
    counter = multiprocessing.Value("i", 0)  # shared int
    lock = multiprocessing.Lock()

    processes = [
        multiprocessing.Process(
            target=increment_counter, args=(counter, lock, 10000)
        )
        for _ in range(4)
    ]
    for p in processes:
        p.start()
    for p in processes:
        p.join()

    print(f"Counter: {counter.value}")  # exactly 40000

# ============================================================
# 4. shared_memory -- zero-copy shared memory (Python 3.8+)
# ============================================================

def shared_memory_worker(shm_name: str, shape: tuple, dtype: str):
    """Worker accesses shared numpy array directly."""
    existing_shm = shared_memory.SharedMemory(name=shm_name)
    arr = np.ndarray(shape, dtype=dtype, buffer=existing_shm.buf)

    # Modify the shared array in-place
    arr[:] = arr * 2

    existing_shm.close()

def shared_memory_example():
    # Create a numpy array
    original = np.array([1, 2, 3, 4, 5], dtype=np.float64)

    # Create shared memory and copy data into it
    shm = shared_memory.SharedMemory(
        create=True, size=original.nbytes
    )
    shared_arr = np.ndarray(
        original.shape, dtype=original.dtype, buffer=shm.buf
    )
    shared_arr[:] = original  # copy data to shared memory

    print(f"Before: {shared_arr}")

    # Worker modifies the shared array directly (no copying!)
    p = multiprocessing.Process(
        target=shared_memory_worker,
        args=(shm.name, original.shape, str(original.dtype)),
    )
    p.start()
    p.join()

    print(f"After: {shared_arr}")  # [2, 4, 6, 8, 10]

    # Cleanup
    shm.close()
    shm.unlink()

# ============================================================
# 5. Manager -- shared complex objects (slower, uses proxies)
# ============================================================

def manager_worker(shared_dict, shared_list, worker_id: int):
    shared_dict[f"worker_{worker_id}"] = f"result_{worker_id}"
    shared_list.append(worker_id)

def manager_example():
    with multiprocessing.Manager() as manager:
        shared_dict = manager.dict()
        shared_list = manager.list()

        processes = [
            multiprocessing.Process(
                target=manager_worker,
                args=(shared_dict, shared_list, i),
            )
            for i in range(4)
        ]
        for p in processes:
            p.start()
        for p in processes:
            p.join()

        print(f"Dict: {dict(shared_dict)}")
        print(f"List: {list(shared_list)}")

if __name__ == "__main__":
    queue_example()
    pipe_example()
    shared_value_example()
    shared_memory_example()
    manager_example()
```

Performance ranking (fastest to slowest):
1. `shared_memory` -- zero-copy, best for large arrays
2. `Value`/`Array` -- shared memory for simple types
3. `Pipe` -- fast for two-process communication
4. `Queue` -- thread/process-safe, good for producer-consumer
5. `Manager` -- most flexible but slowest (uses network proxies)'''
    },
    {
        "instruction": r'''What is the difference between fork and spawn start methods in Python multiprocessing? What are the gotchas on different platforms?''',
        "output": r'''<think>
This is a really important topic because the default start method differs by platform and can cause subtle bugs.

The three start methods:
- fork: copies the parent process (COW). Fast startup. Default on Linux. NOT safe with threads or some C extensions.
- spawn: starts a fresh Python interpreter and imports the module. Slow startup. Default on Windows and macOS (since 3.8). Safe with threads.
- forkserver: starts a server process that forks on demand. Compromise between fork and spawn.

The big gotcha with fork:
- If the parent process has multiple threads, fork() copies the memory but NOT the other threads. This leaves locks in a potentially locked state with no thread to unlock them -- deadlock.
- This is why macOS changed the default to spawn in Python 3.8.
- Libraries like numpy, OpenSSL, and CUDA can break with fork because they have internal state that does not survive forking.

The big gotcha with spawn:
- The child process re-imports the module, so any code at module level runs again.
- If you do not guard your code with if __name__ == "__main__", you get infinite process spawning on Windows.
- Arguments to the child process must be picklable.

I should show practical examples of each and the common traps.
</think>

The start method determines how child processes are created. The wrong choice causes deadlocks, crashes, or infinite spawning:

```python
import multiprocessing
import sys
import os

# ============================================================
# Check and set the start method
# ============================================================

# Defaults:
#   Linux: "fork"
#   macOS (3.8+): "spawn"
#   Windows: "spawn" (fork not available)

print(f"Default start method: {multiprocessing.get_start_method()}")

# Set globally (must be called before creating any processes)
# multiprocessing.set_start_method("spawn")

# Or per-context (preferred -- does not affect other code)
ctx = multiprocessing.get_context("spawn")
# Use ctx.Process, ctx.Pool, ctx.Queue, etc.

# ============================================================
# FORK: fast but dangerous with threads
# ============================================================

# Pros:
# - Fast startup (copies parent memory via copy-on-write)
# - Child inherits all parent state (connections, objects)
# - No pickling needed for arguments

# Cons:
# - NOT safe if parent has multiple threads
# - Locks from other threads are copied in locked state -> deadlock
# - Some C libraries break (OpenSSL, CUDA, numpy internals)

import threading

lock = threading.Lock()

def fork_deadlock_demo():
    """This can deadlock with fork!"""
    # If another thread holds 'lock' when fork() happens,
    # the child process inherits the locked lock but NOT the
    # thread that would unlock it -> permanent deadlock

    def worker():
        # This may hang forever if lock was held during fork
        with lock:
            print("Worker acquired lock")

    # On Linux, this uses fork by default
    p = multiprocessing.Process(target=worker)
    p.start()
    p.join(timeout=5)
    if p.is_alive():
        print("DEADLOCK detected, killing process")
        p.terminate()

# ============================================================
# SPAWN: safe but slower
# ============================================================

# Pros:
# - Safe with threads (fresh interpreter, no inherited locks)
# - Works on all platforms
# - Clean state (no inherited file descriptors, etc.)

# Cons:
# - Slower startup (new Python interpreter)
# - Must re-import modules in child
# - Arguments must be picklable
# - Requires if __name__ == "__main__" guard

def spawn_worker(data: dict) -> str:
    """This function must be importable (defined at module level)."""
    return f"processed: {data}"

def spawn_example():
    ctx = multiprocessing.get_context("spawn")
    with ctx.Pool(4) as pool:
        results = pool.map(spawn_worker, [{"id": i} for i in range(10)])
    return results

# ============================================================
# GOTCHA: Windows/spawn requires __main__ guard
# ============================================================

# WITHOUT this guard, spawn re-imports this module in the child,
# which creates more processes, which import the module again...
# -> infinite process spawning!

# BAD (on Windows):
# pool = multiprocessing.Pool(4)  # at module level
# results = pool.map(fn, data)    # crashes!

# GOOD:
# if __name__ == "__main__":
#     pool = multiprocessing.Pool(4)
#     results = pool.map(fn, data)

# ============================================================
# GOTCHA: unpicklable objects with spawn
# ============================================================

# These CANNOT be sent to spawn processes:
# - lambda functions
# - local/nested functions
# - file handles
# - database connections
# - compiled regex (sometimes)

# BAD with spawn:
# pool.map(lambda x: x * 2, [1, 2, 3])
# -> PicklingError: Can't pickle <function <lambda>>

# GOOD: use module-level named functions
def double(x):
    return x * 2

# ============================================================
# Recommendation: always use spawn (or forkserver)
# ============================================================

def safe_parallel_map(fn, items, workers=None):
    """Cross-platform safe parallel map."""
    ctx = multiprocessing.get_context("spawn")
    workers = workers or min(len(items), os.cpu_count() or 1)
    with ctx.Pool(workers) as pool:
        return pool.map(fn, items)

# ============================================================
# forkserver: compromise (Linux only)
# ============================================================

# Starts a clean server process at the beginning.
# When you need a new worker, the server forks itself.
# Since the server has no threads, fork is safe.
# Faster than spawn (no re-importing) but safer than fork.

if __name__ == "__main__":
    results = safe_parallel_map(double, list(range(20)))
    print(f"Results: {results}")
```

Rules of thumb:
- Always use `spawn` unless you have a specific reason for `fork`
- Always wrap process creation in `if __name__ == "__main__"`
- Only pass picklable objects to child processes (no lambdas, no closures)
- If you must use `fork`, ensure no threads are running when you fork'''
    },
    {
        "instruction": r'''I keep getting pickling errors when using Python multiprocessing. What can and cannot be pickled, and how do I work around it?''',
        "output": r'''Pickling limitations are the most common source of multiprocessing errors. Here is what works and what does not:

```python
import multiprocessing
import pickle
from typing import Any

# ============================================================
# What CAN be pickled (works with multiprocessing)
# ============================================================

# Module-level functions
def process_item(x: int) -> int:
    return x * 2

# Module-level classes with simple attributes
class DataPoint:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y

# Built-in types: int, float, str, list, dict, tuple, set
# Named tuples, dataclasses, Enum values

# ============================================================
# What CANNOT be pickled (fails with multiprocessing)
# ============================================================

# Lambda functions
# bad_fn = lambda x: x * 2
# pickle.dumps(bad_fn)  # PicklingError!

# Nested/local functions
def outer():
    def inner(x):
        return x * 2
    # pickle.dumps(inner)  # PicklingError!

# File handles, sockets, database connections
# f = open("test.txt")
# pickle.dumps(f)  # TypeError!

# Threading locks
# lock = threading.Lock()
# pickle.dumps(lock)  # TypeError!

# Generators
# gen = (x for x in range(10))
# pickle.dumps(gen)  # TypeError!

# ============================================================
# Workaround 1: module-level functions instead of lambdas
# ============================================================

# BAD
# pool.map(lambda x: x ** 2, data)

# GOOD
def square(x):
    return x ** 2

def workaround_functions():
    with multiprocessing.Pool(4) as pool:
        results = pool.map(square, range(20))
    return results

# ============================================================
# Workaround 2: initializer for unpicklable resources
# ============================================================

# Global variable set by initializer in each worker process
_worker_db = None

def init_worker(db_url: str):
    """Called once per worker process."""
    global _worker_db
    # Create the connection in the worker (not pickled!)
    import sqlite3
    _worker_db = sqlite3.connect(db_url)

def query_worker(sql: str) -> list:
    """Uses the connection created by init_worker."""
    cursor = _worker_db.execute(sql)
    return cursor.fetchall()

def workaround_initializer():
    with multiprocessing.Pool(
        processes=4,
        initializer=init_worker,
        initargs=("my_database.db",),
    ) as pool:
        queries = ["SELECT 1", "SELECT 2"]
        results = pool.map(query_worker, queries)
    return results

# ============================================================
# Workaround 3: custom pickling with __getstate__/__setstate__
# ============================================================

class ModelWorker:
    """Object that needs special pickling."""

    def __init__(self, model_path: str):
        self.model_path = model_path
        self._model = None  # loaded lazily
        self._cache = {}

    def __getstate__(self) -> dict:
        """Called by pickle -- return what to serialize."""
        state = self.__dict__.copy()
        # Remove unpicklable attributes
        state["_model"] = None
        state["_cache"] = {}
        return state

    def __setstate__(self, state: dict):
        """Called by pickle -- restore from serialized data."""
        self.__dict__.update(state)
        # Recreate unpicklable resources
        self._load_model()

    def _load_model(self):
        # Simulate loading a model
        self._model = {"path": self.model_path, "loaded": True}

    def predict(self, data: Any) -> Any:
        if self._model is None:
            self._load_model()
        return {"input": data, "prediction": 0.5}

# ============================================================
# Workaround 4: shared memory for large data
# ============================================================

import numpy as np
from multiprocessing import shared_memory

def process_chunk(args: tuple) -> float:
    shm_name, offset, size, shape_0, dtype_str = args
    existing_shm = shared_memory.SharedMemory(name=shm_name)
    arr = np.ndarray(
        (shape_0,), dtype=np.dtype(dtype_str),
        buffer=existing_shm.buf,
    )
    chunk = arr[offset:offset + size]
    result = float(np.mean(chunk))
    existing_shm.close()
    return result

def shared_memory_workaround():
    """Avoid pickling large arrays by using shared memory."""
    data = np.random.rand(1_000_000).astype(np.float64)

    shm = shared_memory.SharedMemory(create=True, size=data.nbytes)
    shared_arr = np.ndarray(data.shape, dtype=data.dtype, buffer=shm.buf)
    shared_arr[:] = data

    chunk_size = 250_000
    args = [
        (shm.name, i, chunk_size, data.shape[0], str(data.dtype))
        for i in range(0, len(data), chunk_size)
    ]

    with multiprocessing.Pool(4) as pool:
        means = pool.map(process_chunk, args)

    print(f"Chunk means: {means}")
    shm.close()
    shm.unlink()

if __name__ == "__main__":
    workaround_functions()
    print("All workarounds demonstrated")
```

Summary of workarounds:
- Functions: define at module level (not lambda/nested)
- Connections/handles: use `initializer` to create in each worker
- Complex objects: implement `__getstate__`/`__setstate__`
- Large data: use `shared_memory` to avoid serialization entirely'''
    },
    {
        "instruction": r'''How do I properly use multiprocessing.Queue and multiprocessing.Pipe for inter-process communication in Python?''',
        "output": r'''```python
import multiprocessing
import time
import os
from dataclasses import dataclass
from typing import Any, Optional

# ============================================================
# Queue: multi-producer, multi-consumer
# ============================================================

@dataclass
class Task:
    id: int
    data: str

@dataclass
class Result:
    task_id: int
    output: str
    worker_pid: int

def queue_worker(
    task_queue: multiprocessing.Queue,
    result_queue: multiprocessing.Queue,
    worker_id: int,
):
    """Worker that reads tasks and writes results."""
    pid = os.getpid()
    while True:
        try:
            task = task_queue.get(timeout=2.0)
        except Exception:
            # Queue.Empty after timeout -- no more work
            break

        if task is None:
            # Poison pill -- shut down
            break

        # Process the task
        output = f"processed-{task.data}-by-{worker_id}"
        result = Result(
            task_id=task.id, output=output, worker_pid=pid
        )
        result_queue.put(result)

def queue_demo():
    num_workers = 4
    num_tasks = 20

    task_queue = multiprocessing.Queue(maxsize=50)
    result_queue = multiprocessing.Queue()

    # Start workers
    workers = []
    for i in range(num_workers):
        p = multiprocessing.Process(
            target=queue_worker,
            args=(task_queue, result_queue, i),
        )
        p.start()
        workers.append(p)

    # Submit tasks
    for i in range(num_tasks):
        task_queue.put(Task(id=i, data=f"item-{i}"))

    # Send poison pills (one per worker)
    for _ in range(num_workers):
        task_queue.put(None)

    # Collect results
    results = []
    for _ in range(num_tasks):
        result = result_queue.get(timeout=10.0)
        results.append(result)

    # Wait for workers to exit
    for w in workers:
        w.join()

    print(f"Processed {len(results)} tasks")
    for r in results[:3]:
        print(f"  Task {r.task_id}: {r.output} (PID {r.worker_pid})")

# ============================================================
# Pipe: fast, two endpoints, one-to-one
# ============================================================

def pipe_worker(conn, worker_id: int):
    """Worker communicates via pipe connection."""
    while True:
        try:
            msg = conn.recv()
        except EOFError:
            break

        if msg is None:
            break

        cmd, data = msg
        if cmd == "compute":
            result = sum(range(data))
            conn.send(("result", worker_id, result))
        elif cmd == "status":
            conn.send(("status", worker_id, "ok"))

    conn.close()

def pipe_demo():
    parent_conn, child_conn = multiprocessing.Pipe()

    worker = multiprocessing.Process(
        target=pipe_worker, args=(child_conn, 0)
    )
    worker.start()

    # Send commands and receive responses
    parent_conn.send(("compute", 1000))
    msg_type, wid, result = parent_conn.recv()
    print(f"Compute result: {result}")

    parent_conn.send(("status", None))
    msg_type, wid, status = parent_conn.recv()
    print(f"Worker status: {status}")

    # Shutdown
    parent_conn.send(None)
    worker.join()
    parent_conn.close()

# ============================================================
# Pattern: bidirectional RPC over pipes
# ============================================================

class ProcessRPC:
    """Simple RPC mechanism over multiprocessing pipes."""

    def __init__(self):
        self._parent_conn, self._child_conn = multiprocessing.Pipe()
        self._process: Optional[multiprocessing.Process] = None
        self._handlers: dict[str, Any] = {}

    def register(self, name: str, handler):
        self._handlers[name] = handler

    def start(self):
        self._process = multiprocessing.Process(
            target=self._worker_loop,
            args=(self._child_conn, self._handlers),
        )
        self._process.start()

    @staticmethod
    def _worker_loop(conn, handlers):
        while True:
            try:
                msg = conn.recv()
            except EOFError:
                break

            if msg is None:
                break

            request_id, method, args, kwargs = msg
            try:
                result = handlers[method](*args, **kwargs)
                conn.send((request_id, "ok", result))
            except Exception as e:
                conn.send((request_id, "error", str(e)))
        conn.close()

    def call(self, method: str, *args, **kwargs) -> Any:
        request_id = id(args)  # simple unique ID
        self._parent_conn.send((request_id, method, args, kwargs))
        rid, status, result = self._parent_conn.recv()
        if status == "error":
            raise RuntimeError(f"RPC error: {result}")
        return result

    def shutdown(self):
        self._parent_conn.send(None)
        if self._process:
            self._process.join(timeout=5.0)
        self._parent_conn.close()

def rpc_demo():
    rpc = ProcessRPC()
    rpc.register("add", lambda a, b: a + b)
    rpc.register("multiply", lambda a, b: a * b)
    rpc.start()

    print(f"add(3, 4) = {rpc.call('add', 3, 4)}")
    print(f"multiply(5, 6) = {rpc.call('multiply', 5, 6)}")

    rpc.shutdown()

if __name__ == "__main__":
    queue_demo()
    pipe_demo()
    rpc_demo()
```

When to use each:
- `Queue` -- multiple producers/consumers, buffered, thread+process safe
- `Pipe` -- two endpoints only, faster than Queue, lower overhead
- `Pipe` with RPC pattern -- when you need request/response semantics'''
    },
]
