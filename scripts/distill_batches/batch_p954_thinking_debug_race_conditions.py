PAIRS = [
    ("thinking/debugging", r'''We have a TOCTOU (time-of-check-to-time-of-use) bug in our file processing pipeline:

```python
import os

def safe_write(filepath, data):
    if not os.path.exists(filepath):
        with open(filepath, 'w') as f:
            f.write(data)
        return True
    else:
        print(f"File {filepath} already exists, skipping")
        return False
```

Two workers occasionally overwrite each other's output. The logs show:
```
Worker-1: Writing output to /data/results/batch_42.json
Worker-2: Writing output to /data/results/batch_42.json
Worker-1: Write complete
Worker-2: Write complete
```

Both workers checked os.path.exists() and got False, then both proceeded to write. How do I fix this race condition?''', r'''<think>
This is a classic TOCTOU (Time of Check, Time of Use) race condition. The gap between `os.path.exists(filepath)` and `open(filepath, 'w')` creates a window where another process can create the file.

Timeline:
1. Worker-1 calls os.path.exists() -> returns False
2. Worker-2 calls os.path.exists() -> returns False (file still does not exist)
3. Worker-1 opens file and starts writing
4. Worker-2 opens file and starts writing (overwrites Worker-1's data)

The fix needs to be atomic -- the check and the create must happen as a single operation. On POSIX systems, this is done with os.open() using O_CREAT | O_EXCL flags, which atomically creates a file only if it does not exist. If it does exist, it raises FileExistsError.

On Windows, similar behavior can be achieved with os.open() and O_CREAT | O_EXCL.

Another approach is file locking, but that is more complex and has portability issues.
</think>

This is a textbook TOCTOU race condition. The `os.path.exists()` check and the `open()` call are two separate operations with a gap between them. Any other process can create the file during that gap.

**The timeline of the bug:**
```
Time 0: Worker-1 checks os.path.exists() -> False
Time 1: Worker-2 checks os.path.exists() -> False
Time 2: Worker-1 opens file for writing
Time 3: Worker-2 opens file for writing (truncates Worker-1's partial data!)
Time 4: Both write, file contains Worker-2's data (or corrupted mix)
```

**Fix: Use atomic create with O_CREAT | O_EXCL**

```python
import os
import errno

def safe_write(filepath, data):
    try:
        # O_CREAT | O_EXCL atomically creates the file ONLY if it
        # does not exist. If it exists, raises FileExistsError.
        fd = os.open(filepath, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        try:
            os.write(fd, data.encode('utf-8'))
        finally:
            os.close(fd)
        return True
    except FileExistsError:
        print(f"File {filepath} already exists, skipping")
        return False
```

The `O_EXCL` flag makes the kernel perform the existence check and file creation as a single atomic operation. No other process can sneak in between.

**Alternative: Write to temp file, then atomic rename**

This is even safer because it prevents partial writes from being visible:

```python
import os
import tempfile

def safe_write(filepath, data):
    dir_name = os.path.dirname(filepath)

    # Write to a temporary file in the same directory
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix='.tmp')
    try:
        os.write(fd, data.encode('utf-8'))
        os.close(fd)
        fd = None

        # Atomic rename -- fails if target exists on some systems
        # On POSIX, os.rename is atomic but will overwrite
        # Use os.link + os.unlink for true atomic non-overwriting
        try:
            os.link(tmp_path, filepath)  # hard link, fails if exists
            os.unlink(tmp_path)
            return True
        except FileExistsError:
            os.unlink(tmp_path)
            print(f"File {filepath} already exists, skipping")
            return False
    except Exception:
        if fd is not None:
            os.close(fd)
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
```

**Alternative: File locking for read-modify-write patterns**

```python
import fcntl

def locked_write(filepath, data):
    lockfile = filepath + '.lock'
    with open(lockfile, 'w') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        try:
            if not os.path.exists(filepath):
                with open(filepath, 'w') as f:
                    f.write(data)
                return True
            return False
        finally:
            fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
```

**Prevention tips:**
- Never use check-then-act patterns with filesystem operations
- Prefer atomic operations (O_EXCL, rename, link) over lock files when possible
- Use the "ask forgiveness not permission" pattern -- try the operation and catch the error
- For databases, use transactions with appropriate isolation levels instead of file locks'''),

    ("thinking/debugging", r'''I thought Python's GIL would protect my shared data, but I'm getting corrupted results:

```python
import threading

counter = 0

def increment(n):
    global counter
    for _ in range(n):
        counter += 1

threads = []
for _ in range(10):
    t = threading.Thread(target=increment, args=(100000,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()

print(f"Expected: 1000000, Got: {counter}")
```

Output:
```
Expected: 1000000, Got: 683492
```

I thought the GIL prevents race conditions in Python?''', r'''<think>
This is one of the most common misconceptions about the GIL. Let me explain what is actually happening.

The GIL (Global Interpreter Lock) ensures that only one thread executes Python bytecode at a time. However, `counter += 1` is NOT a single bytecode operation. It compiles to multiple bytecode instructions:

1. LOAD_GLOBAL counter (read the current value)
2. LOAD_CONST 1
3. BINARY_ADD (compute counter + 1)
4. STORE_GLOBAL counter (write the new value back)

The GIL can be released between any two bytecode instructions. So:

Thread A: LOAD_GLOBAL counter -> gets 42
(GIL switches to Thread B)
Thread B: LOAD_GLOBAL counter -> gets 42
Thread B: LOAD_CONST 1
Thread B: BINARY_ADD -> 43
Thread B: STORE_GLOBAL counter -> stores 43
(GIL switches back to Thread A)
Thread A: LOAD_CONST 1
Thread A: BINARY_ADD -> 43
Thread A: STORE_GLOBAL counter -> stores 43

Both threads incremented from 42, but the result is 43 instead of 44. One increment was lost.

The GIL protects Python's internal data structures (like dict and list) from corruption, but it does not provide atomicity for multi-step operations.
</think>

This is the most common misconception about Python's GIL. The GIL does NOT prevent race conditions in your application logic. It only prevents Python's internal interpreter state from being corrupted.

**What the GIL actually guarantees:**
- Only one thread executes Python bytecode at a time
- Built-in data structure operations (dict lookup, list append) are thread-safe at the C level
- The interpreter itself will not crash from concurrent access

**What the GIL does NOT guarantee:**
- Atomicity of Python-level operations
- Consistency of multi-step read-modify-write sequences

**Why `counter += 1` is not atomic:**

It compiles to multiple bytecode instructions:
```
LOAD_GLOBAL   counter    # Read current value
LOAD_CONST    1
BINARY_ADD               # Compute new value
STORE_GLOBAL  counter    # Write new value
```

The GIL can release between any two instructions. Two threads can read the same value, both add 1, and both store the same result -- losing one increment.

```
Thread A: LOAD_GLOBAL counter  -> reads 42
          --- GIL switches to Thread B ---
Thread B: LOAD_GLOBAL counter  -> reads 42
Thread B: BINARY_ADD           -> computes 43
Thread B: STORE_GLOBAL counter -> writes 43
          --- GIL switches to Thread A ---
Thread A: BINARY_ADD           -> computes 43
Thread A: STORE_GLOBAL counter -> writes 43  (should be 44!)
```

**Fix 1: Use threading.Lock**

```python
import threading

counter = 0
lock = threading.Lock()

def increment(n):
    global counter
    for _ in range(n):
        with lock:
            counter += 1
```

This works but is slow due to lock acquisition overhead on every iteration.

**Fix 2: Batch the lock acquisition**

```python
def increment(n):
    global counter
    local_count = 0
    for _ in range(n):
        local_count += 1
    with lock:
        counter += local_count
```

Much faster -- each thread accumulates locally then updates the shared counter once.

**Fix 3: Use queue or atomic operations**

```python
from collections import Counter
import threading

results = []

def increment(n, thread_id):
    local = 0
    for _ in range(n):
        local += 1
    results.append(local)  # list.append IS atomic under GIL

total = sum(results)
```

**Fix 4: Use multiprocessing with shared memory (for CPU-bound work)**

```python
from multiprocessing import Process, Value

def increment(counter, n):
    for _ in range(n):
        with counter.get_lock():
            counter.value += 1
```

**Prevention tips:**
- Never assume any Python operation is atomic (even simple ones)
- Use `threading.Lock` for any shared mutable state
- Prefer message-passing (Queue) over shared state
- Use `concurrent.futures.ThreadPoolExecutor` for cleaner thread management
- For CPU-bound parallelism, use multiprocessing (the GIL limits threading to I/O-bound concurrency)'''),

    ("thinking/debugging", r'''My multiprocessing pool crashes with a pickle error on a class method:

```python
from multiprocessing import Pool

class DataProcessor:
    def __init__(self, config):
        self.config = config
        self.db_conn = create_connection(config['db_url'])

    def process_item(self, item):
        result = transform(item, self.config)
        return result

    def run(self, items):
        with Pool(4) as pool:
            results = pool.map(self.process_item, items)
        return results

processor = DataProcessor({'db_url': 'postgres://...', 'batch_size': 100})
results = processor.run(range(1000))
```

Error:
```
TypeError: cannot pickle 'psycopg2.extensions.connection' object

Traceback (most recent call last):
  File "processor.py", line 16, in run
    results = pool.map(self.process_item, items)
  File "multiprocessing/pool.py", line 364, in map
    return self._map_async(func, iterable).get()
  File "multiprocessing/pool.py", line 771, in get
    raise self._value
TypeError: cannot pickle 'psycopg2.extensions.connection' object
```

Why is it trying to pickle my database connection?''', r'''<think>
When you use `pool.map(self.process_item, items)`, multiprocessing needs to send the function and its arguments to worker processes. It does this via pickle serialization.

`self.process_item` is a bound method -- it is bound to `self`, which is the DataProcessor instance. To pickle a bound method, Python needs to pickle the entire instance, which includes all its attributes: `self.config` and `self.db_conn`.

Database connections (psycopg2, MySQL connectors, etc.) contain file descriptors and socket connections that cannot be serialized. Hence the pickle error.

The fix is to avoid passing the bound method or to separate the picklable data from the unpicklable objects.
</think>

When you pass `self.process_item` to `pool.map()`, Python's multiprocessing needs to serialize (pickle) the function to send it to worker processes. Since `process_item` is a bound method, pickling it requires pickling the entire `self` object, including `self.db_conn` -- a database connection that contains file descriptors and sockets which cannot be serialized.

**The pickle chain:**
```
pool.map(self.process_item, items)
  -> pickle self.process_item (bound method)
    -> pickle self (DataProcessor instance)
      -> pickle self.config (dict - OK)
      -> pickle self.db_conn (connection - FAILS!)
```

**Fix 1: Use a module-level function with only picklable arguments**

```python
from multiprocessing import Pool

def process_item(args):
    item, config = args
    result = transform(item, config)
    return result

class DataProcessor:
    def __init__(self, config):
        self.config = config
        self.db_conn = create_connection(config['db_url'])

    def run(self, items):
        args = [(item, self.config) for item in items]
        with Pool(4) as pool:
            results = pool.map(process_item, args)
        return results
```

**Fix 2: Use initializer to create per-worker connections**

```python
from multiprocessing import Pool

_worker_conn = None

def init_worker(config):
    """Called once per worker process at startup."""
    global _worker_conn
    _worker_conn = create_connection(config['db_url'])

def process_item(item_and_config):
    item, config = item_and_config
    result = transform(item, config)
    _worker_conn.execute(...)  # use the per-worker connection
    return result

class DataProcessor:
    def __init__(self, config):
        self.config = config

    def run(self, items):
        args = [(item, self.config) for item in items]
        with Pool(4, initializer=init_worker,
                  initargs=(self.config,)) as pool:
            results = pool.map(process_item, args)
        return results
```

This is the best approach when workers need database access -- each worker creates its own connection.

**Fix 3: Use __getstate__/__setstate__ to control pickling**

```python
class DataProcessor:
    def __init__(self, config):
        self.config = config
        self.db_conn = create_connection(config['db_url'])

    def __getstate__(self):
        state = self.__dict__.copy()
        del state['db_conn']  # exclude unpicklable attribute
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self.db_conn = create_connection(self.config['db_url'])
```

**Fix 4: Use concurrent.futures with ThreadPoolExecutor (if I/O bound)**

```python
from concurrent.futures import ThreadPoolExecutor

class DataProcessor:
    def run(self, items):
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(self.process_item, items))
        return results
```

Threads share memory, so no pickling is needed. The bound method and its `self` reference work fine. However, the GIL limits CPU parallelism.

**Prevention tips:**
- Keep multiprocessing worker functions at module level, not as methods
- Only pass simple, picklable data (dicts, lists, strings, numbers) to worker processes
- Create per-worker resources (DB connections, file handles) in the initializer
- Use `concurrent.futures.ProcessPoolExecutor` for a cleaner API than `multiprocessing.Pool`'''),

    ("thinking/debugging", r'''Two threads are deadlocked in my application. Thread dump shows:

```
Thread-1 (worker_a):
  File "app.py", line 23, in transfer
    lock_from.acquire()  # has lock_b, waiting for lock_a

Thread-2 (worker_b):
  File "app.py", line 23, in transfer
    lock_from.acquire()  # has lock_a, waiting for lock_b

"Thread-1" waiting on lock for account_a (held by Thread-2)
"Thread-2" waiting on lock for account_b (held by Thread-1)
```

Code:
```python
import threading

class BankAccount:
    def __init__(self, id, balance):
        self.id = id
        self.balance = balance
        self.lock = threading.Lock()

def transfer(from_account, to_account, amount):
    from_account.lock.acquire()
    # simulate some processing delay
    import time; time.sleep(0.01)
    to_account.lock.acquire()
    try:
        if from_account.balance >= amount:
            from_account.balance -= amount
            to_account.balance += amount
    finally:
        to_account.lock.release()
        from_account.lock.release()

# Thread 1: transfer(account_a, account_b, 100)
# Thread 2: transfer(account_b, account_a, 50)
```

Classic deadlock. What's the proper fix?''', r'''<think>
Classic deadlock scenario. Thread 1 acquires lock_a, then tries to acquire lock_b. Thread 2 acquires lock_b, then tries to acquire lock_a. Neither can proceed.

The standard solutions:
1. Lock ordering -- always acquire locks in a consistent order (e.g., by account ID)
2. Use a timeout and retry
3. Use a single global lock (simple but kills concurrency)

Lock ordering is the textbook correct approach.
</think>

This is a classic deadlock caused by inconsistent lock ordering. Thread 1 holds lock_a and waits for lock_b, while Thread 2 holds lock_b and waits for lock_a. Neither can proceed because each is waiting for a resource held by the other.

**The four conditions for deadlock (all must be true):**
1. Mutual exclusion -- locks are exclusive
2. Hold and wait -- threads hold one lock while waiting for another
3. No preemption -- locks cannot be forcibly taken from a thread
4. Circular wait -- Thread 1 waits for Thread 2 and vice versa

**Fix 1: Consistent lock ordering (best solution)**

Always acquire locks in the same order regardless of which account is the source or destination:

```python
def transfer(from_account, to_account, amount):
    # Always lock the account with the lower ID first
    if from_account.id < to_account.id:
        first, second = from_account, to_account
    else:
        first, second = to_account, from_account

    with first.lock:
        with second.lock:
            if from_account.balance >= amount:
                from_account.balance -= amount
                to_account.balance += amount
```

Now both threads acquire locks in the same order (lower ID first), eliminating the circular wait condition.

**Fix 2: Timeout with retry**

```python
import time
import random

def transfer(from_account, to_account, amount, max_retries=5):
    for attempt in range(max_retries):
        if from_account.lock.acquire(timeout=0.1):
            try:
                if to_account.lock.acquire(timeout=0.1):
                    try:
                        if from_account.balance >= amount:
                            from_account.balance -= amount
                            to_account.balance += amount
                        return True
                    finally:
                        to_account.lock.release()
            finally:
                from_account.lock.release()

        # Back off with jitter to avoid livelock
        time.sleep(random.uniform(0.01, 0.05))

    raise RuntimeError("Transfer failed: could not acquire locks")
```

**Fix 3: Use a context manager for ordered locking**

```python
import threading
from contextlib import contextmanager

@contextmanager
def acquire_locks(*locks_with_keys):
    """Acquire multiple locks in a consistent order."""
    sorted_pairs = sorted(locks_with_keys, key=lambda x: x[0])
    acquired = []
    try:
        for key, lock in sorted_pairs:
            lock.acquire()
            acquired.append(lock)
        yield
    finally:
        for lock in reversed(acquired):
            lock.release()

def transfer(from_account, to_account, amount):
    with acquire_locks(
        (from_account.id, from_account.lock),
        (to_account.id, to_account.lock),
    ):
        if from_account.balance >= amount:
            from_account.balance -= amount
            to_account.balance += amount
```

This is the most reusable pattern -- it works for any number of locks.

**Prevention tips:**
- Establish a global lock ordering convention (by ID, by memory address, by name)
- Document the locking protocol in your codebase
- Use `threading.RLock` (reentrant lock) if the same thread may need to re-acquire
- Consider lock-free alternatives: `queue.Queue`, `concurrent.futures`, or message-passing
- In production, set lock timeouts and log warnings when waits exceed thresholds
- Use tools like `faulthandler.dump_traceback()` to diagnose deadlocks in production'''),

    ("thinking/debugging", r'''Multiple threads are corrupting a shared dictionary even though I thought dict operations were thread-safe:

```python
import threading

shared_cache = {}

def update_cache(key, value):
    if key not in shared_cache:
        shared_cache[key] = []
    shared_cache[key].append(value)

threads = []
for i in range(100):
    t = threading.Thread(target=update_cache, args=(f"key_{i % 5}", i))
    threads.append(t)
    t.start()

for t in threads:
    t.join()

for key, values in shared_cache.items():
    print(f"{key}: {len(values)} items")
```

Output:
```
key_0: 17 items  (expected 20)
key_1: 19 items  (expected 20)
key_2: 20 items
key_3: 18 items  (expected 20)
key_4: 20 items
```

Some items are being lost! I thought Python dicts are thread-safe due to the GIL?''', r'''<think>
The issue is the check-then-act pattern:

```python
if key not in shared_cache:      # check
    shared_cache[key] = []       # act
shared_cache[key].append(value)  # act
```

Individual dict operations like `__contains__`, `__setitem__`, and list.append are atomic under the GIL. But the COMBINATION of "check if key exists, create list if not, then append" is not atomic.

Race scenario:
1. Thread A: checks "key_0" not in shared_cache -> True
2. Thread B: checks "key_0" not in shared_cache -> True
3. Thread A: shared_cache["key_0"] = [] (creates empty list)
4. Thread B: shared_cache["key_0"] = [] (overwrites with another empty list!)
5. Thread A: shared_cache["key_0"].append(0) -> appends to Thread B's list
6. Thread B: shared_cache["key_0"].append(5) -> appends to Thread B's list
But Thread A's append in step 5 might have gone to the first list that was overwritten in step 4.

Actually wait, let me re-think. After step 4, both threads reference the same new list. The lost items happen because between step 3 and step 5, thread B overwrites the list. If thread A had already appended to the first list before thread B overwrites it, that append is lost.

The fix: use defaultdict (setdefault is atomic in CPython) or a lock.
</think>

Individual dict operations are indeed atomic under the GIL, but your code performs a multi-step check-then-act sequence that is NOT atomic as a whole.

**The race condition:**

```python
if key not in shared_cache:      # Step 1: check
    shared_cache[key] = []       # Step 2: create list
shared_cache[key].append(value)  # Step 3: append
```

The GIL can release between any of these steps. Here is what happens:

```
Thread A: "key_0" not in shared_cache -> True
Thread B: "key_0" not in shared_cache -> True
Thread A: shared_cache["key_0"] = []     (List-1 created)
Thread A: shared_cache["key_0"].append(0) (appends to List-1)
Thread B: shared_cache["key_0"] = []     (List-2 replaces List-1!)
Thread B: shared_cache["key_0"].append(5) (appends to List-2)
# value 0 is now lost -- List-1 was discarded with it
```

**Fix 1: Use dict.setdefault() (atomic under CPython GIL)**

```python
def update_cache(key, value):
    shared_cache.setdefault(key, []).append(value)
```

`setdefault` is implemented as a single C function call that atomically checks and sets the default value. Combined with `list.append` (also atomic under the GIL), this is safe in CPython.

**Important caveat:** This relies on CPython's GIL. It is NOT safe in PyPy, Jython, or future GIL-free Python builds.

**Fix 2: Use collections.defaultdict**

```python
from collections import defaultdict

shared_cache = defaultdict(list)

def update_cache(key, value):
    shared_cache[key].append(value)
```

`defaultdict.__getitem__` atomically creates the default value if the key is missing.

**Fix 3: Use a lock (portable and future-proof)**

```python
import threading
from collections import defaultdict

shared_cache = defaultdict(list)
cache_lock = threading.Lock()

def update_cache(key, value):
    with cache_lock:
        shared_cache[key].append(value)
```

This is the only approach guaranteed to work across all Python implementations and future versions (including the no-GIL Python 3.13+ builds).

**Fix 4: Use thread-local accumulation (best performance)**

```python
import threading
from collections import defaultdict

def worker(keys_and_values):
    local_cache = defaultdict(list)
    for key, value in keys_and_values:
        local_cache[key].append(value)
    return local_cache

# Merge results after all threads complete
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [executor.submit(worker, chunk) for chunk in chunks]
    final_cache = defaultdict(list)
    for future in futures:
        for key, values in future.result().items():
            final_cache[key].extend(values)
```

This eliminates contention entirely by having each thread work on its own local data.

**Prevention tips:**
- Never rely on the GIL for application-level thread safety
- Any check-then-act pattern on shared data needs a lock
- Use `threading.Lock` for simple mutual exclusion
- Use `concurrent.futures` to structure parallel work with clean result collection
- Consider `queue.Queue` for producer-consumer patterns -- it handles all synchronization internally'''),
]
