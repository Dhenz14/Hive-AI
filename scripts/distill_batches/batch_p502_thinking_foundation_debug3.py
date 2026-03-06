"""Phase 1A: Foundation Thinking — Systematic Debugging (Part 3/4)
Concurrency bugs, deadlocks, livelocks, starvation, thread-safety issues."""

PAIRS = [
    (
        "thinking/debug-deadlock-nested-locks",
        "Our payment service hangs intermittently. Two functions both acquire locks on accounts but in different orders:\n\n```python\nimport threading\n\naccount_locks = {}\n\ndef get_lock(account_id):\n    if account_id not in account_locks:\n        account_locks[account_id] = threading.Lock()\n    return account_locks[account_id]\n\ndef transfer(from_id, to_id, amount):\n    from_lock = get_lock(from_id)\n    to_lock = get_lock(to_id)\n    \n    with from_lock:\n        # Debit from source\n        balance = get_balance(from_id)\n        if balance < amount:\n            raise InsufficientFunds()\n        set_balance(from_id, balance - amount)\n        \n        with to_lock:\n            # Credit to destination\n            set_balance(to_id, get_balance(to_id) + amount)\n\ndef audit_accounts(id_a, id_b):\n    with get_lock(id_a):\n        bal_a = get_balance(id_a)\n        with get_lock(id_b):\n            bal_b = get_balance(id_b)\n    return bal_a, bal_b\n```\n\nThe system locks up under concurrent transfers. Diagnose the issue.",
        r'''<think>
Let me trace through what happens with concurrent operations.

**Scenario: Deadlock from lock ordering**

Consider two concurrent calls:
- Thread 1: `transfer(A, B, 100)` → acquires lock(A), then tries lock(B)
- Thread 2: `transfer(B, A, 50)` → acquires lock(B), then tries lock(A)

Timeline:
1. Thread 1 acquires lock(A) ✓
2. Thread 2 acquires lock(B) ✓
3. Thread 1 tries to acquire lock(B) — BLOCKED (Thread 2 holds it)
4. Thread 2 tries to acquire lock(A) — BLOCKED (Thread 1 holds it)

Classic circular wait deadlock. Neither thread can proceed.

**Additional deadlock scenario:**
- Thread 1: `transfer(A, B, 100)` — locks A then B
- Thread 2: `audit_accounts(B, A)` — locks B then A

Same problem. The audit function also uses arbitrary ordering.

**Another bug: Race condition in get_lock()**
```python
def get_lock(account_id):
    if account_id not in account_locks:      # Thread 1 checks: not in dict
        account_locks[account_id] = threading.Lock()  # Thread 1 creates lock
    # Thread 2 might also create a DIFFERENT lock for same account_id
    return account_locks[account_id]
```
Two threads could create separate locks for the same account, defeating the mutual exclusion entirely.

**Fix 1: Consistent lock ordering**
Always acquire locks in a deterministic order (e.g., sorted by account ID). This breaks the circular wait condition.

**Fix 2: Thread-safe lock creation**
Use `defaultdict` or a dedicated lock for the lock dictionary.

**Fix 3: Use a timeout to detect deadlocks**
`lock.acquire(timeout=5)` — if it times out, release all held locks and retry.
</think>

There are **two bugs** causing the hangs:

## Bug 1: Deadlock from Inconsistent Lock Ordering

`transfer(A, B)` acquires lock(A) then lock(B), but `transfer(B, A)` acquires lock(B) then lock(A). When both run concurrently, each holds one lock and waits for the other — classic **circular wait deadlock**.

## Bug 2: Race Condition in `get_lock()`

The lock creation itself isn't thread-safe. Two threads can create separate `Lock` objects for the same account ID, meaning they don't actually exclude each other.

## Fix

```python
import threading
from contextlib import ExitStack

_master_lock = threading.Lock()
_account_locks: dict[str, threading.Lock] = {}

def get_lock(account_id: str) -> threading.Lock:
    with _master_lock:
        if account_id not in _account_locks:
            _account_locks[account_id] = threading.Lock()
        return _account_locks[account_id]

def _acquire_ordered(*account_ids: str) -> ExitStack:
    """Acquire locks in sorted order to prevent deadlock."""
    stack = ExitStack()
    for aid in sorted(set(account_ids)):
        lock = get_lock(aid)
        stack.enter_context(lock)
    return stack

def transfer(from_id: str, to_id: str, amount: float):
    with _acquire_ordered(from_id, to_id):
        balance = get_balance(from_id)
        if balance < amount:
            raise InsufficientFunds()
        set_balance(from_id, balance - amount)
        set_balance(to_id, get_balance(to_id) + amount)

def audit_accounts(id_a: str, id_b: str):
    with _acquire_ordered(id_a, id_b):
        return get_balance(id_a), get_balance(id_b)
```

**Key principles:**
1. **Consistent ordering** — always acquire locks in sorted order, breaking circular wait
2. **Thread-safe lock creation** — master lock protects the lock dictionary
3. **`ExitStack`** — cleanly manages multiple context managers with proper cleanup'''
    ),
    (
        "thinking/debug-livelock-retry-storm",
        "Two microservices keep retrying failed requests to each other and neither makes progress. Service A calls Service B, and if B returns 503, A retries immediately. B does the same when calling A. Under load, both services spend all their time retrying and never complete any work. Here's Service A's retry logic:\n\n```python\nimport requests\nimport time\n\ndef call_service_b(payload):\n    max_retries = 10\n    for attempt in range(max_retries):\n        try:\n            resp = requests.post('http://service-b/api', json=payload, timeout=5)\n            if resp.status_code == 200:\n                return resp.json()\n            elif resp.status_code == 503:\n                time.sleep(0.1)  # Fixed 100ms backoff\n                continue\n        except requests.Timeout:\n            time.sleep(0.1)\n            continue\n    raise ServiceUnavailable('Service B not responding')\n```",
        r'''<think>
Let me analyze why both services are stuck in a livelock.

**What is a livelock?**
Unlike a deadlock where threads are blocked, a livelock is where threads are active but making no progress. They keep reacting to each other's state changes but never move forward.

**Tracing the scenario:**
1. Service A sends request to B
2. B is overloaded, returns 503
3. A waits 100ms, retries
4. B is processing A's retry + its own retries to A + other requests
5. B returns 503 again because it's overwhelmed
6. Meanwhile, B is doing the same thing trying to reach A
7. Both services flood each other with retries, consuming all connection pool capacity

**Why the current retry logic fails:**

**Problem 1: Fixed backoff (0.1s)**
All retries happen at the same interval. When a service recovers briefly, ALL waiting clients retry simultaneously — a "thundering herd." This immediately re-overloads the service.

**Problem 2: No jitter**
Even with exponential backoff, if multiple callers start at the same time, they'll all retry at the same time (1s, 2s, 4s...). Jitter randomizes retry timing to spread the load.

**Problem 3: No circuit breaker**
The code will always try 10 times. If a service is down, every request wastes 10 attempts × 5s timeout = 50 seconds of connection holding. Under load, this exhausts connection pools.

**Problem 4: No distinction between transient and permanent failures**
503 (overloaded, try later) vs 500 (bug, won't fix itself) vs 429 (rate limited, use Retry-After header) all get the same treatment.

**Problem 5: Circular dependency**
A calls B, B calls A. Under load, this creates a feedback loop where each service's retries add to the other's load.

**The fix needs multiple layers:**
1. Exponential backoff with jitter
2. Circuit breaker pattern
3. Distinguish failure types
4. Break circular dependency if possible
</think>

This is a **livelock** — both services are active but making zero progress because their retry storms keep each other overloaded.

## Root Causes

1. **Fixed 100ms backoff** — all retries happen simultaneously, creating thundering herd
2. **No jitter** — synchronized retry waves keep re-overloading the target
3. **No circuit breaker** — continues hammering a known-down service
4. **Circular dependency** — A→B retries generate B→A retries, forming a feedback loop

## Fix: Exponential Backoff + Jitter + Circuit Breaker

```python
import requests
import time
import random
import threading
from dataclasses import dataclass, field
from enum import Enum

class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject immediately
    HALF_OPEN = "half_open"  # Testing if recovered

@dataclass
class CircuitBreaker:
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    _failures: int = 0
    _state: CircuitState = CircuitState.CLOSED
    _last_failure_time: float = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def allow_request(self) -> bool:
        with self._lock:
            if self._state == CircuitState.CLOSED:
                return True
            if self._state == CircuitState.OPEN:
                if time.time() - self._last_failure_time > self.recovery_timeout:
                    self._state = CircuitState.HALF_OPEN
                    return True  # Allow one probe request
                return False
            return True  # HALF_OPEN: allow the probe

    def record_success(self):
        with self._lock:
            self._failures = 0
            self._state = CircuitState.CLOSED

    def record_failure(self):
        with self._lock:
            self._failures += 1
            self._last_failure_time = time.time()
            if self._failures >= self.failure_threshold:
                self._state = CircuitState.OPEN

_breakers: dict[str, CircuitBreaker] = {}

def call_service_b(payload, max_retries=5):
    breaker = _breakers.setdefault("service-b", CircuitBreaker())

    if not breaker.allow_request():
        raise ServiceUnavailable("Circuit open for Service B")

    for attempt in range(max_retries):
        try:
            resp = requests.post(
                'http://service-b/api', json=payload, timeout=5
            )
            if resp.status_code == 200:
                breaker.record_success()
                return resp.json()
            elif resp.status_code == 503:
                breaker.record_failure()
                # Exponential backoff with full jitter
                base_delay = min(2 ** attempt, 30)  # Cap at 30s
                delay = random.uniform(0, base_delay)
                time.sleep(delay)
                continue
            elif resp.status_code == 429:
                # Respect Retry-After header
                retry_after = float(resp.headers.get('Retry-After', 5))
                time.sleep(retry_after)
                continue
            else:
                raise ServiceError(f"Unexpected status: {resp.status_code}")
        except requests.Timeout:
            breaker.record_failure()
            base_delay = min(2 ** attempt, 30)
            time.sleep(random.uniform(0, base_delay))
    raise ServiceUnavailable("Service B: max retries exceeded")
```

**Key fixes:** exponential backoff caps the storm, jitter desynchronizes retries, and the circuit breaker stops hammering a failing service entirely.'''
    ),
    (
        "thinking/debug-thread-starvation-unfair-lock",
        "Our web server has 8 worker threads processing requests. Under load, some requests complete in milliseconds while others time out after 30 seconds. Thread dumps show some threads haven't run in 20+ seconds. The hot path:\n\n```python\nimport threading\n\ncache_lock = threading.Lock()\ncache = {}\n\ndef get_data(key):\n    with cache_lock:\n        if key in cache:\n            return cache[key]\n    \n    # Cache miss — fetch from DB (slow, 50-200ms)\n    data = db.fetch(key)\n    \n    with cache_lock:\n        cache[key] = data\n    return data\n\ndef handle_request(request):\n    # Called by each worker thread\n    results = []\n    for key in request.keys:  # Could be 10-50 keys per request\n        results.append(get_data(key))\n    return results\n```",
        r'''<think>
Let me analyze the thread starvation issue.

**The pattern:**
- 8 worker threads, all calling `get_data()` for multiple keys
- Each call acquires `cache_lock` twice (once for read, once for write on miss)
- A request with 50 keys acquires the lock 50-100 times

**Why some threads starve:**

Python's `threading.Lock()` is **not fair**. When a lock is released, any waiting thread can acquire it — there's no guaranteed FIFO ordering. The OS scheduler tends to favor the thread that just released the lock (it's still running and on-CPU), so it can immediately re-acquire the lock.

**The starvation scenario:**
1. Thread 1 has a request with 50 keys
2. Thread 1 acquires lock, checks cache, releases lock
3. Thread 1 immediately re-acquires lock for the next key (OS favors it — it's hot on the CPU)
4. Thread 2 has been waiting since step 1 but keeps losing the race
5. Thread 1 loops through 50 keys, holding the lock ~100 times in quick succession
6. Thread 2 starves for the entire duration

**Additional issues:**

**Lock granularity:** One global lock for the entire cache. A read for key "A" blocks a read for key "B". This is a classic contention bottleneck.

**No read/write distinction:** Reads don't need exclusive access — multiple threads can safely read simultaneously. Only writes need exclusive access. Using a Lock() forces exclusive access for reads too.

**Solution approaches:**
1. `threading.RWLock` doesn't exist in stdlib, but `RLock` won't help. We need a read-write lock.
2. Better: use `concurrent.futures` or a thread-safe dict
3. Best: per-key locking or lock-free approaches

Actually, the simplest and most Pythonic fix: use a `threading.RLock` doesn't help. The real fix is reducing lock contention:

1. Switch to a `RWLock` pattern (readers-writer lock)
2. Or better: per-key locking to eliminate false contention
3. Or: use a concurrent-safe data structure
4. Or: batch the DB fetches to reduce lock acquisitions
</think>

The issue is **thread starvation** caused by two compounding problems:

## Root Cause 1: Unfair Lock + Tight Loop

Python's `threading.Lock()` has no fairness guarantee. Thread 1 processing 50 keys releases and immediately re-acquires the lock in a tight loop. The OS favors the running thread, so other threads waiting for the lock get repeatedly skipped.

## Root Cause 2: Global Lock Granularity

One lock for the entire cache means a read of key "A" blocks a read of key "B". With 8 threads hitting 10-50 keys each, contention is extreme.

## Fix: Read-Write Lock + Per-Key Locking

```python
import threading
from concurrent.futures import ThreadPoolExecutor

class RWLock:
    """Simple readers-writer lock (write-preferring)."""
    def __init__(self):
        self._readers = 0
        self._lock = threading.Lock()
        self._readers_lock = threading.Lock()
        self._write_lock = threading.Lock()

    def read_acquire(self):
        self._lock.acquire()
        with self._readers_lock:
            self._readers += 1
            if self._readers == 1:
                self._write_lock.acquire()
        self._lock.release()

    def read_release(self):
        with self._readers_lock:
            self._readers -= 1
            if self._readers == 0:
                self._write_lock.release()

    def write_acquire(self):
        self._lock.acquire()
        self._write_lock.acquire()

    def write_release(self):
        self._write_lock.release()
        self._lock.release()

cache_rw = RWLock()
cache: dict = {}
_key_locks: dict[str, threading.Lock] = {}
_key_locks_lock = threading.Lock()

def _get_key_lock(key: str) -> threading.Lock:
    with _key_locks_lock:
        if key not in _key_locks:
            _key_locks[key] = threading.Lock()
        return _key_locks[key]

def get_data(key: str):
    # Fast path: read lock (shared, non-blocking for other readers)
    cache_rw.read_acquire()
    try:
        if key in cache:
            return cache[key]
    finally:
        cache_rw.read_release()

    # Cache miss: per-key lock prevents duplicate DB fetches
    with _get_key_lock(key):
        # Double-check after acquiring key lock
        cache_rw.read_acquire()
        try:
            if key in cache:
                return cache[key]
        finally:
            cache_rw.read_release()

        data = db.fetch(key)

        cache_rw.write_acquire()
        try:
            cache[key] = data
        finally:
            cache_rw.write_release()
        return data

def handle_request(request):
    results = []
    for key in request.keys:
        results.append(get_data(key))
    return results
```

**Key improvements:**
1. **Read-write lock** — multiple readers proceed in parallel, only writes are exclusive
2. **Per-key locking** — cache miss for key "A" doesn't block anything related to key "B"
3. **Double-checked locking** — prevents duplicate DB fetches for the same key'''
    ),
    (
        "thinking/debug-gc-pause-latency-spike",
        "Our Python API has periodic latency spikes — every 30-60 seconds, response times jump from 5ms to 500ms+ for a few hundred milliseconds. The spikes don't correlate with traffic or CPU usage. Memory usage is steady at ~2GB. The code processes large lists of objects:\n\n```python\nclass PriceTick:\n    def __init__(self, symbol, price, timestamp, metadata):\n        self.symbol = symbol\n        self.price = price\n        self.timestamp = timestamp\n        self.metadata = metadata\n        self._cached_repr = None\n    \n    def __repr__(self):\n        if self._cached_repr is None:\n            self._cached_repr = f'{self.symbol}:{self.price}@{self.timestamp}'\n        return self._cached_repr\n\n# Global rolling window — keeps last 1M ticks\nrolling_window = []\nMAX_TICKS = 1_000_000\n\ndef add_tick(tick):\n    rolling_window.append(tick)\n    if len(rolling_window) > MAX_TICKS:\n        rolling_window.pop(0)  # Remove oldest\n```",
        r'''<think>
Let me analyze periodic latency spikes that don't correlate with load. This pattern screams garbage collection.

**Why GC causes spikes:**
Python's GC uses reference counting + a cyclic garbage collector. The cyclic GC runs periodically and must traverse all objects in the generation being collected. With 1M `PriceTick` objects, each having 5 attributes + a cached repr, that's millions of object references to traverse.

**Generation 2 collections are expensive:**
- Gen 0: new objects, collected frequently (fast)
- Gen 1: survived one collection
- Gen 2: survived two collections, collected rarely (slow, traverses ALL gen2 objects)

With 1M long-lived objects in gen2, a gen2 collection pauses the entire process while traversing all of them. 2GB of objects = hundreds of milliseconds pause.

**The rolling window pattern makes it worse:**

`rolling_window.pop(0)` on a list is O(n) — it shifts all 999,999 remaining elements. But more importantly for GC:
- Every `pop(0)` decrements refcount of the removed tick → potential cascade
- Every `append` creates a new object → pressure on gen0
- The churn means frequent promotions from gen0 → gen1 → gen2
- Gen2 gets bigger and bigger, making gen2 collections more expensive

**The `_cached_repr` creates reference cycles:**
Actually, `_cached_repr` is just a string, no cycle there. But the `metadata` dict could contain references back to the tick object — need to check. Even without cycles, the sheer volume of gen2 objects makes collection slow.

**Also:** `list.pop(0)` is O(n) for memory movement — with 1M items, that's copying ~8MB of pointers every tick. This itself causes CPU spikes.

**Fixes:**
1. Use `collections.deque(maxlen=MAX_TICKS)` — O(1) removal, no memory shifting
2. Use `__slots__` — reduces per-object overhead, fewer objects for GC to traverse
3. Disable cyclic GC if no cycles exist, or tune GC thresholds
4. Use `gc.freeze()` on long-lived objects to exclude them from collection
</think>

The spikes are caused by **Python's garbage collector** doing expensive generation-2 collections across your 1M+ objects, compounded by an O(n) list operation.

## Root Causes

**1. GC gen2 collection on millions of objects**
1M `PriceTick` objects (5+ attributes each = millions of references) live in gen2. When the cyclic GC collects gen2, it traverses ALL of them — causing a 200-500ms stop-the-world pause.

**2. `list.pop(0)` is O(n)**
Removing from the front of a list shifts all remaining elements. With 1M items, every tick copies ~8MB of pointers.

**3. High object churn promotes GC pressure**
Constant append/pop creates and destroys objects rapidly, triggering frequent collections.

## Fix

```python
import gc
from collections import deque

class PriceTick:
    __slots__ = ('symbol', 'price', 'timestamp', 'metadata', '_cached_repr')

    def __init__(self, symbol, price, timestamp, metadata):
        self.symbol = symbol
        self.price = price
        self.timestamp = timestamp
        self.metadata = metadata
        self._cached_repr = None

    def __repr__(self):
        if self._cached_repr is None:
            self._cached_repr = f'{self.symbol}:{self.price}@{self.timestamp}'
        return self._cached_repr

# deque with maxlen: O(1) append and automatic O(1) eviction
rolling_window: deque[PriceTick] = deque(maxlen=1_000_000)

def add_tick(tick):
    rolling_window.append(tick)  # Old ticks auto-evicted

# Tune GC for latency-sensitive workloads
gc.set_threshold(50_000, 30, 10)  # Less frequent collections
# Or for extreme latency: manually control collection timing
# gc.disable()
# ... run gc.collect() during known-idle windows
```

**Impact of each fix:**
- **`__slots__`** — 40-50% less memory per object, fewer references for GC to traverse
- **`deque(maxlen=N)`** — eliminates O(n) pop(0), reduces GC pressure from churn
- **GC tuning** — controls when the expensive gen2 sweep happens'''
    ),
    (
        "thinking/debug-connection-pool-exhaustion",
        "After running for a few hours, our Flask app starts returning 500 errors. All errors trace to `sqlalchemy.exc.TimeoutError: QueuePool limit of 5 overflow 10 reached`. Restarting fixes it temporarily. The code:\n\n```python\nfrom sqlalchemy import create_engine\nfrom sqlalchemy.orm import sessionmaker\n\nengine = create_engine('postgresql://...', pool_size=5, max_overflow=10)\nSession = sessionmaker(bind=engine)\n\n@app.route('/api/users/<int:user_id>')\ndef get_user(user_id):\n    session = Session()\n    user = session.query(User).get(user_id)\n    if not user:\n        return jsonify(error='Not found'), 404\n    \n    orders = session.query(Order).filter_by(user_id=user_id).all()\n    \n    return jsonify({\n        'user': user.to_dict(),\n        'orders': [o.to_dict() for o in orders]\n    })\n\n@app.route('/api/transfer', methods=['POST'])\ndef transfer():\n    session = Session()\n    data = request.json\n    try:\n        from_acc = session.query(Account).get(data['from_id'])\n        to_acc = session.query(Account).get(data['to_id'])\n        from_acc.balance -= data['amount']\n        to_acc.balance += data['amount']\n        session.commit()\n        return jsonify(success=True)\n    except Exception:\n        session.rollback()\n        return jsonify(error='Transfer failed'), 500\n```",
        r'''<think>
Let me trace the connection lifecycle in this code.

**The `get_user` endpoint:**
1. `session = Session()` — checks out a connection from the pool
2. Queries user and orders
3. Returns JSON response
4. **Session is NEVER closed** — the connection is never returned to the pool

**The `transfer` endpoint:**
1. `session = Session()` — checks out a connection
2. On success: `session.commit()` — commits but **doesn't close the session**
3. On exception: `session.rollback()` — rolls back but **doesn't close the session**
4. Connection is never returned to the pool

**The leak pattern:**
- Pool has 5 connections + 10 overflow = 15 max
- Each request checks out a connection and never returns it
- After 15 requests, pool is exhausted
- New requests wait for a connection, hit timeout, raise QueuePool error

Wait, but the user says it takes "a few hours" to fail. If connections were truly leaked every request, it would fail after 15 requests. So something is partially returning connections.

Actually, Python's garbage collector eventually finalizes the session objects, which closes the connections. But GC timing is non-deterministic — objects might persist in gen2 for a long time before collection. Under steady load, connections leak faster than GC can reclaim them.

Also, the `get_user` endpoint has an early return on 404 — the session is leaked in that path too. And if `to_dict()` raises an exception, the session leaks.

**The `transfer` endpoint has another bug:**
On exception, it does `session.rollback()` but not `session.close()`. The connection stays checked out in an error state.

**The proper fix:**
Use Flask-SQLAlchemy's scoped sessions, or at minimum, always close sessions with try/finally or context managers. Flask's `teardown_appcontext` is the idiomatic place to remove sessions.
</think>

The error is a classic **connection pool leak**. Sessions are created but **never closed**, so connections are never returned to the pool.

## Root Cause

Both endpoints create sessions with `Session()` but never call `session.close()`. The connections stay checked out:

- `get_user`: no close at all — leaks on every request (including 404 early return)
- `transfer`: calls commit/rollback but not close — connection stays checked out
- After 15 requests (5 pool + 10 overflow), pool is exhausted

It takes "hours" because Python's GC eventually finalizes orphaned sessions, but under load, leaks outpace GC reclamation.

## Fix: Scoped Session with Automatic Cleanup

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

engine = create_engine('postgresql://...', pool_size=5, max_overflow=10)
Session = scoped_session(sessionmaker(bind=engine))

@app.teardown_appcontext
def shutdown_session(exception=None):
    """Return connection to pool after every request."""
    Session.remove()

@app.route('/api/users/<int:user_id>')
def get_user(user_id):
    user = Session.query(User).get(user_id)
    if not user:
        return jsonify(error='Not found'), 404

    orders = Session.query(Order).filter_by(user_id=user_id).all()

    return jsonify({
        'user': user.to_dict(),
        'orders': [o.to_dict() for o in orders],
    })

@app.route('/api/transfer', methods=['POST'])
def transfer():
    data = request.json
    try:
        from_acc = Session.query(Account).get(data['from_id'])
        to_acc = Session.query(Account).get(data['to_id'])
        from_acc.balance -= data['amount']
        to_acc.balance += data['amount']
        Session.commit()
        return jsonify(success=True)
    except Exception:
        Session.rollback()
        return jsonify(error='Transfer failed'), 500
```

**Key changes:**
1. **`scoped_session`** — one session per thread, reused across the request
2. **`teardown_appcontext`** — guarantees `Session.remove()` runs after EVERY request, even on unhandled exceptions, returning the connection to the pool
3. No manual `Session()` construction — use the scoped proxy directly'''
    ),
    (
        "thinking/debug-serialization-pickle-version",
        "We cache expensive computation results using pickle. After deploying a new version of our app, cached results are causing crashes:\n\n```python\nimport pickle\nimport hashlib\n\nclass AnalysisResult:\n    def __init__(self, data, scores, metadata):\n        self.data = data\n        self.scores = scores\n        self.metadata = metadata\n\n# Old version (before deploy):\n# class AnalysisResult:\n#     def __init__(self, data, scores):\n#         self.data = data\n#         self.scores = scores\n\ndef cache_result(key, result):\n    serialized = pickle.dumps(result)\n    cache_key = hashlib.sha256(key.encode()).hexdigest()\n    redis_client.set(f'analysis:{cache_key}', serialized, ex=86400)\n\ndef get_cached_result(key):\n    cache_key = hashlib.sha256(key.encode()).hexdigest()\n    data = redis_client.get(f'analysis:{cache_key}')\n    if data:\n        return pickle.loads(data)  # Crashes here!\n    return None\n```\n\nError: `AttributeError: 'AnalysisResult' object has no attribute 'metadata'`",
        r'''<think>
Let me trace the pickle deserialization process.

**How pickle restores objects:**
1. Creates a new instance of the class (often bypassing `__init__`)
2. Sets `__dict__` from the pickled state

The old pickled data contains:
```python
{'data': ..., 'scores': ...}  # No 'metadata' field
```

The new code expects `self.metadata` to exist. When any code accesses `result.metadata` on a deserialized old object, it gets `AttributeError` because `__init__` was never called — pickle restored the old `__dict__` directly.

**The deeper problem:** pickle ties serialization to class structure. Any change to the class breaks deserialization of existing cached data:
- Adding attributes → AttributeError on the new attributes
- Removing attributes → orphan data, may cause issues
- Renaming attributes → both problems
- Moving the class to a different module → `ModuleNotFoundError`

**Fixes (from simple to robust):**

1. **`__getattr__` fallback** — quick fix for missing attributes
2. **Custom `__reduce__` or `__getstate__`/`__setstate__`** — version-aware deserialization
3. **Switch to a versioned format** — JSON with schema version, or protobuf
4. **Cache key versioning** — include class version in the cache key so old and new don't collide
</think>

Pickle restores the old object's `__dict__` (without `metadata`) but never calls `__init__`. Any access to `.metadata` on old cached objects raises `AttributeError`.

## The Problem

Pickle ties serialization to exact class structure. Adding `metadata` to the class doesn't retroactively add it to already-cached objects.

## Fix: Version-Aware Serialization

```python
import json
import hashlib

SCHEMA_VERSION = 2  # Bump on class changes

class AnalysisResult:
    def __init__(self, data, scores, metadata=None):
        self.data = data
        self.scores = scores
        self.metadata = metadata or {}

    def to_dict(self):
        return {
            '_v': SCHEMA_VERSION,
            'data': self.data,
            'scores': self.scores,
            'metadata': self.metadata,
        }

    @classmethod
    def from_dict(cls, d):
        version = d.get('_v', 1)
        if version == 1:
            # Migrate old format: no metadata field
            return cls(data=d['data'], scores=d['scores'], metadata={})
        return cls(data=d['data'], scores=d['scores'], metadata=d['metadata'])

def cache_result(key, result):
    serialized = json.dumps(result.to_dict())
    cache_key = hashlib.sha256(key.encode()).hexdigest()
    redis_client.set(f'analysis:{cache_key}', serialized, ex=86400)

def get_cached_result(key):
    cache_key = hashlib.sha256(key.encode()).hexdigest()
    data = redis_client.get(f'analysis:{cache_key}')
    if data:
        try:
            return AnalysisResult.from_dict(json.loads(data))
        except (json.JSONDecodeError, KeyError):
            # Old pickle data — invalidate and return miss
            redis_client.delete(f'analysis:{cache_key}')
            return None
    return None
```

**Why JSON over pickle:**
1. **Schema versioning** — `_v` field enables explicit migration logic
2. **Language-agnostic** — other services can read the cache
3. **No code execution** — pickle deserializes by executing code, which is a security risk
4. **Readable** — you can inspect cached values for debugging'''
    ),
    (
        "thinking/debug-config-drift-env-override",
        "Production is using the wrong database. Despite our config file pointing to the production DB, the app connects to the staging database. The config system:\n\n```python\nimport os\nimport yaml\n\ndef load_config(config_path='config.yaml'):\n    with open(config_path) as f:\n        file_config = yaml.safe_load(f)\n    \n    # Environment variables override file config\n    config = {}\n    config.update(file_config)\n    \n    for key, value in os.environ.items():\n        if key.startswith('APP_'):\n            config_key = key[4:].lower()  # APP_DB_HOST -> db_host\n            config[config_key] = value\n    \n    return config\n\n# config.yaml:\n# db_host: prod-db.internal\n# db_port: 5432\n# db_name: myapp_prod\n```\n\nWe've verified config.yaml is correct. `echo $APP_DB_HOST` returns empty. But the app is connecting to `staging-db.internal`.",
        r'''<think>
Let me think about where the staging DB hostname could be coming from.

**The stated facts:**
- config.yaml has `db_host: prod-db.internal` ✓
- `echo $APP_DB_HOST` returns empty ✓
- App connects to `staging-db.internal` ✗

**Where could `staging-db.internal` come from?**

1. **Environment variable with different prefix or casing?**
   The code checks `key.startswith('APP_')` and converts to lowercase. What about `APP_DB_HOST`? That would become `db_host` and override the file config. But the user says it's empty.

   Wait — `echo $APP_DB_HOST` was run in the user's shell, but the app might be running in a different environment (Docker, systemd, supervisor). Environment variables in the deployment config (Dockerfile, docker-compose, systemd unit) might differ from the developer's shell.

2. **YAML parsing issue?**
   `yaml.safe_load` on a file with `db_host: staging-db.internal` would do it. But the user says they verified the file. Could there be a different config.yaml being loaded? The path is relative — `config.yaml` resolves relative to the process's working directory, not the script location.

3. **Flat namespace collision:**
   The config file uses nested YAML:
   ```yaml
   db_host: prod-db.internal
   ```
   But what if it's actually:
   ```yaml
   database:
     host: prod-db.internal
   ```
   Then `file_config` would be `{'database': {'host': 'prod-db.internal'}}`, and `db_host` would never be set from the file. The env var override for `db_host` would be the only source.

4. **The env loop picks up ALL APP_ vars:**
   ```python
   for key, value in os.environ.items():
       if key.startswith('APP_'):
   ```
   Even if `APP_DB_HOST` is empty in the user's shell, it could be set in:
   - Docker Compose `environment` section
   - `.env` file loaded by Docker or systemd
   - CI/CD pipeline secrets
   - Supervisor/PM2 config
   - The process manager's own environment

5. **Hidden `.env` file:**
   Many frameworks auto-load `.env`. If there's a stale `.env` with `APP_DB_HOST=staging-db.internal`, it would override the config file.

The most likely cause: a `.env` file, Docker environment variable, or systemd EnvironmentFile that the user didn't check. The user ran `echo $APP_DB_HOST` in their own shell but the app runs in a different environment context.

**The config system itself also has a bug:** it doesn't validate or log which values came from which source. There's no way to debug which config source "won" without adding logging.
</think>

The environment variable isn't empty **where the app runs** — it's empty in **your shell**. The app's runtime environment (Docker, systemd, .env file) has a stale `APP_DB_HOST=staging-db.internal` that overrides the config file.

## Most Likely Culprits

Check these in order:
1. **`.env` file** in the project root (Docker Compose and many frameworks auto-load these)
2. **`docker-compose.yml`** `environment:` section
3. **Systemd unit** `EnvironmentFile=` directive
4. **CI/CD deployment** config (e.g., Kubernetes ConfigMap, ECS task definition)

```bash
# Debug: see what the APP actually sees
grep -r "staging-db" .env docker-compose* *.service deploy/ k8s/
```

## The Config System Bug

Even after fixing the stale env var, this config system is fragile because **it gives no visibility into override sources**:

```python
import os
import yaml
import logging

logger = logging.getLogger(__name__)

def load_config(config_path='config.yaml'):
    with open(config_path) as f:
        file_config = yaml.safe_load(f) or {}

    config = dict(file_config)
    overrides = {}

    for key, value in os.environ.items():
        if key.startswith('APP_'):
            config_key = key[4:].lower()
            if config_key in config and config[config_key] != value:
                logger.warning(
                    "Config override: %s = %r (was %r from %s)",
                    config_key, value, config[config_key], config_path,
                )
            config[config_key] = value
            overrides[config_key] = key

    # Log final resolved config (mask secrets)
    for k, v in sorted(config.items()):
        source = f"env:{overrides[k]}" if k in overrides else f"file:{config_path}"
        display = "***" if "password" in k or "secret" in k else v
        logger.info("Config: %s = %s [source: %s]", k, display, source)

    return config
```

**This logging would have immediately revealed:** `Config: db_host = staging-db.internal [source: env:APP_DB_HOST]`'''
    ),
    (
        "thinking/debug-signal-handler-deadlock",
        "Our long-running data pipeline process occasionally hangs on shutdown. We send SIGTERM and the process stops responding entirely. The code:\n\n```python\nimport signal\nimport logging\nimport threading\n\nlogger = logging.getLogger(__name__)\nshutdown_event = threading.Event()\ndb_lock = threading.Lock()\n\ndef graceful_shutdown(signum, frame):\n    logger.info('Received SIGTERM, shutting down...')\n    with db_lock:\n        flush_pending_writes()\n    shutdown_event.set()\n\nsignal.signal(signal.SIGTERM, graceful_shutdown)\n\ndef process_batch(batch):\n    with db_lock:\n        for item in batch:\n            write_to_db(item)\n            if shutdown_event.is_set():\n                logger.info('Shutdown requested, stopping batch')\n                return\n```",
        r'''<think>
This is a classic signal handler deadlock.

**The problem:**
Signal handlers in Python run in the **main thread**, interrupting whatever the main thread was doing. If the main thread was inside `process_batch` holding `db_lock`, then:

1. Main thread acquires `db_lock` in `process_batch`
2. SIGTERM arrives → Python interrupts main thread
3. `graceful_shutdown` runs — tries to acquire `db_lock`
4. **Deadlock** — the main thread is waiting for a lock that it already holds, but the signal handler is blocking the thread from returning to the code that would release the lock

`threading.Lock` is **not reentrant** — even the same thread can't acquire it twice. (An `RLock` would avoid this specific deadlock, but signal handlers should still not do complex work.)

**Additional problem:**
`logger.info()` in the signal handler is also dangerous. Python's `logging` module uses internal locks. If the signal interrupts during a logging call, the signal handler tries to acquire the same logging lock → deadlock.

**Signal handler rules:**
Signal handlers should only do minimal, async-signal-safe operations:
1. Set a flag/event
2. Write to a pipe/socket
3. That's it — no locks, no I/O, no logging, no memory allocation

**The fix:**
The signal handler should ONLY set the event. All cleanup logic should happen in normal code flow.
</think>

The process deadlocks because the **signal handler tries to acquire a lock the main thread already holds**.

## The Deadlock

1. Main thread is in `process_batch`, holding `db_lock`
2. SIGTERM arrives → Python interrupts main thread to run `graceful_shutdown`
3. `graceful_shutdown` tries `with db_lock:` — but the **same thread** already holds it
4. `threading.Lock` is non-reentrant → **permanent deadlock**

The `logger.info()` in the handler is also dangerous — Python's logging uses internal locks that may already be held when the signal fires.

## Fix: Signal Handler Does Minimum, Cleanup Happens in Main Flow

```python
import signal
import logging
import threading

logger = logging.getLogger(__name__)
shutdown_event = threading.Event()
db_lock = threading.Lock()

def graceful_shutdown(signum, frame):
    # ONLY set the flag — no locks, no logging, no I/O
    shutdown_event.set()

signal.signal(signal.SIGTERM, graceful_shutdown)

def process_batch(batch):
    with db_lock:
        for item in batch:
            if shutdown_event.is_set():
                logger.info('Shutdown requested, flushing and stopping')
                break
            write_to_db(item)
        # Flush happens inside the lock, in normal code flow
        if shutdown_event.is_set():
            flush_pending_writes()

def main():
    while not shutdown_event.is_set():
        batch = get_next_batch()
        if batch:
            process_batch(batch)
    logger.info('Clean shutdown complete')
```

**Rules for signal handlers:** only set a flag or write a byte to a pipe. All real work (logging, locks, I/O, cleanup) must happen in normal code flow that checks the flag.'''
    ),
    (
        "thinking/debug-dns-cache-stale-failover",
        "After a database failover to a new replica, our app keeps connecting to the dead primary for several minutes despite DNS being updated. The connection code:\n\n```python\nimport socket\nimport psycopg2\n\ndef get_db_connection():\n    return psycopg2.connect(\n        host='db.myapp.internal',\n        port=5432,\n        dbname='myapp',\n        user='app',\n        password='secret',\n        connect_timeout=5,\n    )\n\n# Connection pool\npool = []\nMAX_POOL = 10\n\ndef get_connection():\n    if pool:\n        conn = pool.pop()\n        try:\n            conn.cursor().execute('SELECT 1')\n            return conn\n        except Exception:\n            conn.close()\n    return get_db_connection()\n\ndef return_connection(conn):\n    if len(pool) < MAX_POOL:\n        pool.append(conn)\n    else:\n        conn.close()\n```",
        r'''<think>
Let me trace why the app sticks to the dead primary after DNS update.

**Layer 1: DNS caching**
When psycopg2 connects to `db.myapp.internal`, it resolves the hostname to an IP via DNS. The resolved IP is cached at multiple levels:
- OS-level DNS cache (nscd, systemd-resolved, etc.)
- The C library's `getaddrinfo` cache
- Python's `socket.getaddrinfo` may cache results

Even after DNS TTL expires, OS caches may serve stale records for minutes.

**Layer 2: Connection pool holds pre-resolved connections**
The bigger problem: `pool` holds existing TCP connections to the **old IP address**. DNS changes don't affect already-established TCP connections. The health check (`SELECT 1`) will only fail when:
- The dead primary's OS sends TCP RST (if it's truly dead)
- The TCP keepalive timeout expires (often 2+ hours by default!)
- The connect_timeout only applies to NEW connections

If the old primary's VM is completely gone (power off), the TCP stack won't get RSTs. Instead, the connection appears "open" until TCP keepalive or the next write attempt times out — which can take MINUTES with default TCP settings.

**Layer 3: The health check race**
Even when `SELECT 1` eventually fails, the code:
1. Pops a bad connection
2. Closes it
3. Creates a new one
But the new one might still resolve to the cached DNS (stale OS cache).

**The fix needs to address all layers:**
1. Force DNS re-resolution periodically
2. Set TCP keepalive to detect dead connections faster
3. Set connection max age so pooled connections are recycled
4. Use the DB driver's built-in health check with timeout
</think>

Three layers of caching prevent your app from finding the new database:

## Layer 1: Pooled Connections Keep the Old TCP Socket

Your pool holds established TCP connections to the **old IP**. DNS changes don't affect existing connections. The `SELECT 1` health check only fails once TCP detects the dead host — which can take **minutes** with default keepalive settings.

## Layer 2: OS DNS Cache Serves Stale Records

Even new connections resolve `db.myapp.internal` against a stale OS cache, reconnecting to the dead IP.

## Fix: Connection Max-Age + TCP Keepalive + Proper Pooling

```python
import time
import psycopg2
from psycopg2 import extensions

MAX_POOL = 10
MAX_CONN_AGE = 300  # Recycle connections every 5 minutes
TCP_KEEPALIVE_IDLE = 10  # Detect dead connections in ~30s
TCP_KEEPALIVE_INTERVAL = 5
TCP_KEEPALIVE_COUNT = 3

def get_db_connection():
    conn = psycopg2.connect(
        host='db.myapp.internal',
        port=5432,
        dbname='myapp',
        user='app',
        password='secret',
        connect_timeout=5,
        # TCP keepalive: detect dead connections fast
        keepalives=1,
        keepalives_idle=TCP_KEEPALIVE_IDLE,
        keepalives_interval=TCP_KEEPALIVE_INTERVAL,
        keepalives_count=TCP_KEEPALIVE_COUNT,
    )
    conn._created_at = time.monotonic()
    return conn

pool = []

def get_connection():
    while pool:
        conn, created = pool.pop()
        # Reject connections older than MAX_CONN_AGE (forces DNS re-resolve)
        if time.monotonic() - created > MAX_CONN_AGE:
            conn.close()
            continue
        try:
            # Quick health check with timeout
            conn.set_session(readonly=True)
            cur = conn.cursor()
            cur.execute('SELECT 1')
            cur.close()
            conn.set_session(readonly=False)
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
    return get_db_connection()

def return_connection(conn):
    if len(pool) < MAX_POOL:
        pool.append((conn, getattr(conn, '_created_at', time.monotonic())))
    else:
        conn.close()
```

**After failover, connections recycle within 5 minutes max.** TCP keepalive detects truly dead hosts in ~30 seconds. For production, use `psycopg2.pool.ThreadedConnectionPool` or pgBouncer.'''
    ),
    (
        "thinking/debug-hash-collision-dos",
        "Our API slows to a crawl when processing certain user-submitted JSON payloads. Normal requests take 5ms but these specific payloads take 30+ seconds. The payload is a JSON object with ~1000 keys. The processing code:\n\n```python\nfrom flask import request, jsonify\n\n@app.route('/api/aggregate', methods=['POST'])\ndef aggregate():\n    data = request.get_json()  # Parses JSON into Python dict\n    result = {}\n    for key, value in data.items():\n        category = categorize(key)\n        if category not in result:\n            result[category] = []\n        result[category].append(value)\n    return jsonify(result)\n```\n\nNothing in the code looks O(n^2). Why is it slow?",
        r'''<think>
The code looks O(n) — iterating over dict items and doing dict lookups. But it's taking 30 seconds for 1000 keys. Let me think about what could cause this.

**Hash collision attack (HashDoS):**

Python dicts are hash tables. When keys hash to the same bucket, lookups degrade from O(1) to O(n) as the bucket becomes a linked list. With 1000 colliding keys:
- Each `data.items()` iteration: O(1) — it's iterating, not looking up
- But `request.get_json()` parses JSON into a dict. If the JSON keys are crafted to produce hash collisions, building the dict is O(n²)
- Similarly, `result[category]` lookups become O(n) per lookup if categories collide

**Wait, Python 3.3+ has hash randomization** via `PYTHONHASHSEED`. So hash collision attacks on string keys shouldn't work because the hash function includes a random seed per process.

But... `request.get_json()` uses the `json` module which creates a Python dict. The JSON parsing itself isn't the issue — it's that the attacker might be exploiting something else.

Actually, let me reconsider. The user says "certain payloads" with ~1000 keys. Let me think about what `categorize(key)` does. If `categorize` is expensive (regex, DB lookup, etc.) and takes 30ms per call, then 1000 × 30ms = 30 seconds. But the question says "nothing looks O(n²)."

Actually, the most likely explanation given modern Python with hash randomization: the `categorize()` function is the bottleneck. But if we're being asked about hash collisions, let me consider the full picture.

In CPython, string hashing is randomized per-process, but:
1. Integer keys: hash(n) == n for small ints — predictable, no randomization
2. If `categorize()` returns integers, an attacker could craft inputs to cause collisions in `result`
3. JSON numbers parsed as Python ints have predictable hashes

Or: the payload processing triggers quadratic behavior somewhere else:
- If `categorize()` is O(n) itself
- If the JSON is deeply nested (recursive parsing)
- If there's a regex in `categorize()` that causes ReDoS

But the classic interview answer here is **HashDoS** — crafted dictionary keys causing hash collisions. Even with Python 3.3+ randomization, the attack is possible if the attacker can probe the hash seed (timing side-channel) or if PYTHONHASHSEED is set to a fixed value (disabled randomization).

Let me present both the HashDoS angle and the practical `categorize()` angle.
</think>

Two possible causes, both worth investigating:

## Possibility 1: Hash Collision DoS (HashDoS)

If `PYTHONHASHSEED=0` or a fixed seed is set (common in "reproducible" deployments), an attacker can craft 1000 JSON keys that all hash to the same bucket. Dict operations degrade from O(1) to O(n), making the overall parse **O(n²)**: 1000² = 1M operations.

```bash
# Check if hash randomization is disabled
python -c "import os; print(os.environ.get('PYTHONHASHSEED', 'random (safe)'))"
```

## Possibility 2: `categorize()` is Expensive

If `categorize(key)` does regex matching, DB lookups, or any O(n) work, then 1000 calls × slow function = 30 seconds. Profile it:

```python
import time

@app.route('/api/aggregate', methods=['POST'])
def aggregate():
    data = request.get_json()

    t0 = time.perf_counter()
    result = {}
    for key, value in data.items():
        category = categorize(key)  # Time this
        if category not in result:
            result[category] = []
        result[category].append(value)
    elapsed = time.perf_counter() - t0
    app.logger.info(f"Aggregation took {elapsed:.3f}s for {len(data)} keys")

    return jsonify(result)
```

## Defensive Fix (Covers Both)

```python
from flask import request, jsonify, abort
from collections import defaultdict

MAX_KEYS = 200  # Limit input size — kills HashDoS and slow categorize

@app.route('/api/aggregate', methods=['POST'])
def aggregate():
    data = request.get_json()
    if not isinstance(data, dict) or len(data) > MAX_KEYS:
        abort(400, f"Payload must be a JSON object with <= {MAX_KEYS} keys")

    result = defaultdict(list)
    for key, value in data.items():
        category = categorize(key)
        result[category].append(value)
    return jsonify(result)
```

**Key defense:** always limit input size at system boundaries. A 1000-key JSON object is suspicious — legitimate use cases rarely need that many keys in a single flat object.'''
    ),
    (
        "thinking/debug-unicode-normalization",
        "Users report that searching for their own files sometimes returns no results. A user uploads a file named 'café.txt' and then searches for 'café' — no results. But other users can search for it fine. The code:\n\n```python\nimport os\n\ndef upload_file(filename, content, user_id):\n    safe_name = filename.strip()\n    path = os.path.join(UPLOAD_DIR, str(user_id), safe_name)\n    os.makedirs(os.path.dirname(path), exist_ok=True)\n    with open(path, 'wb') as f:\n        f.write(content)\n    # Store in DB for search\n    db.execute(\n        'INSERT INTO files (user_id, filename) VALUES (?, ?)',\n        (user_id, safe_name)\n    )\n\ndef search_files(query, user_id):\n    return db.execute(\n        'SELECT filename FROM files WHERE user_id = ? AND filename LIKE ?',\n        (user_id, f'%{query}%')\n    ).fetchall()\n```",
        r'''<think>
The file is named 'café.txt' and searching for 'café' returns nothing. This is a Unicode normalization issue.

**The é character can be represented two ways in Unicode:**
1. **NFC (composed):** `é` = U+00E9 (single codepoint "LATIN SMALL LETTER E WITH ACUTE")
2. **NFD (decomposed):** `é` = U+0065 U+0301 (letter "e" + combining acute accent)

Both look identical when rendered, but they're different byte sequences:
- NFC: `\xc3\xa9` in UTF-8
- NFD: `\x65\xcc\x81` in UTF-8

**macOS is the key culprit:** The macOS filesystem (HFS+/APFS) normalizes filenames to NFD. So if a macOS user uploads `café.txt`, the filename is stored as NFD in the database. But when they search, their browser/client might send the query as NFC. The SQL LIKE comparison does byte-level matching, so NFC `café` ≠ NFD `café`.

**Why other users can search for it:** Users on Windows/Linux typically use NFC by default. If a Windows user types 'café' in the search, and a macOS user uploaded the file (stored as NFD), the search fails. But if a Windows user both uploaded AND searched, both are NFC, so it matches.

Wait, the user says they upload the file themselves and can't find it. So: the user (probably on macOS) uploads with NFD filename, then searches with NFC query (because the browser normalizes text input differently than filenames). Or vice versa.

**The fix:** Normalize all Unicode strings to a consistent form (NFC is the standard recommendation) on both input and query.
</think>

This is a **Unicode normalization** issue. The character `é` has two different binary representations:

- **NFC (composed):** `é` = U+00E9 (one codepoint)
- **NFD (decomposed):** `é` = U+0065 + U+0301 (e + combining accent)

They look identical but are different bytes. macOS filesystems use NFD, browsers often send NFC. So the filename is stored as one form and the search query arrives as the other. SQL `LIKE` does byte comparison → no match.

## Fix: Normalize All Unicode to NFC

```python
import os
import unicodedata

def normalize(text: str) -> str:
    """Normalize to NFC — the universal standard form."""
    return unicodedata.normalize('NFC', text)

def upload_file(filename, content, user_id):
    safe_name = normalize(filename.strip())
    path = os.path.join(UPLOAD_DIR, str(user_id), safe_name)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'wb') as f:
        f.write(content)
    db.execute(
        'INSERT INTO files (user_id, filename) VALUES (?, ?)',
        (user_id, safe_name)
    )

def search_files(query, user_id):
    query = normalize(query)  # Normalize search query too
    return db.execute(
        'SELECT filename FROM files WHERE user_id = ? AND filename LIKE ?',
        (user_id, f'%{query}%')
    ).fetchall()
```

**Fix existing data** with a migration:
```sql
-- For PostgreSQL:
UPDATE files SET filename = normalize(filename, NFC);
```

**Rule:** Normalize all user-supplied strings to NFC at the system boundary (upload, search, API input). This matches the W3C recommendation and what most platforms expect.'''
    ),
    (
        "thinking/debug-iterator-exhaustion",
        "A data pipeline processes records in two passes — first to validate, then to transform. The second pass always produces zero results:\n\n```python\ndef process_data(records_iter):\n    # Pass 1: Validate all records\n    valid_count = 0\n    error_count = 0\n    for record in records_iter:\n        if validate(record):\n            valid_count += 1\n        else:\n            error_count += 1\n    \n    print(f'Validated: {valid_count} valid, {error_count} errors')\n    # Output: \"Validated: 9500 valid, 500 errors\"\n    \n    # Pass 2: Transform valid records\n    results = []\n    for record in records_iter:  # Always 0 iterations!\n        if validate(record):\n            results.append(transform(record))\n    \n    print(f'Transformed: {len(results)} records')\n    # Output: \"Transformed: 0 records\"\n    return results\n\n# Called like:\nresults = process_data(read_csv_stream('data.csv'))\n```",
        r'''<think>
This is a classic iterator exhaustion bug.

`read_csv_stream('data.csv')` returns an iterator (generator). Iterators can only be consumed once. After Pass 1 loops through all records, the iterator is exhausted. Pass 2 tries to iterate the same iterator — it's already at the end, so the for loop body never executes.

This is different from a list — lists can be iterated multiple times because they store all elements in memory. Iterators/generators are lazy and stateful; once consumed, they're done.

The fix: either materialize into a list first, or use `itertools.tee`, or restructure to single-pass.
</think>

**Iterator exhaustion.** `read_csv_stream()` returns a generator, which can only be iterated **once**. Pass 1 consumes all records; Pass 2 sees an empty iterator.

## Fix Options

**Option 1: Materialize (if data fits in memory)**
```python
def process_data(records_iter):
    records = list(records_iter)  # Consume once, reuse the list

    valid_count = sum(1 for r in records if validate(r))
    error_count = len(records) - valid_count
    print(f'Validated: {valid_count} valid, {error_count} errors')

    results = [transform(r) for r in records if validate(r)]
    print(f'Transformed: {len(results)} records')
    return results
```

**Option 2: Single pass (memory-efficient)**
```python
def process_data(records_iter):
    results = []
    valid_count = 0
    error_count = 0

    for record in records_iter:  # Single iteration
        if validate(record):
            valid_count += 1
            results.append(transform(record))
        else:
            error_count += 1

    print(f'Validated: {valid_count} valid, {error_count} errors')
    print(f'Transformed: {len(results)} records')
    return results
```

**Option 2 is better** — it's a single pass, uses less memory, and doesn't call `validate()` twice per record. The general rule: if you need multiple passes over lazy data, either materialize it or restructure into a single pass.'''
    ),
    (
        "thinking/debug-boolean-trap-api-misuse",
        "Multiple callers are passing arguments to this function in the wrong order, causing silent data corruption. No errors are raised:\n\n```python\ndef create_user(name, email, is_admin, is_active, send_welcome):\n    user = User(\n        name=name,\n        email=email,\n        is_admin=is_admin,\n        is_active=is_active,\n    )\n    db.add(user)\n    if send_welcome:\n        send_welcome_email(user)\n    return user\n\n# Caller code found in review:\ncreate_user('Alice', 'alice@example.com', True, False, True)\ncreate_user('Bob', 'bob@co.com', False, True, False)\ncreate_user('Charlie', 'c@co.com', True, True, False)  # Is this admin=True or active=True?\n```\n\nThe bug: some admins were created as non-active, some non-admins were created as admins. How do we fix this API?",
        r'''<think>
This is the "boolean trap" — a function with multiple consecutive boolean parameters that are easy to mix up when called positionally.

`create_user('Alice', 'alice@example.com', True, False, True)` — which True is which? Without looking at the function signature, you can't tell if `True` is `is_admin`, `is_active`, or `send_welcome`. Callers inevitably get the order wrong, and since all arguments are the same type (bool), Python doesn't raise any error.

**Fixes:**
1. **Keyword-only arguments** — force callers to name the booleans
2. **Enum or flag object** instead of raw bools
3. **Separate functions** for different intent (create_admin vs create_user)
</think>

This is the **boolean trap** — multiple consecutive boolean parameters that are silently swapped by callers. Since all three are `bool`, Python happily accepts the wrong order.

## Fix: Keyword-Only Arguments

```python
def create_user(
    name: str,
    email: str,
    *,  # Everything after this is keyword-only
    is_admin: bool = False,
    is_active: bool = True,
    send_welcome: bool = True,
) -> User:
    user = User(
        name=name,
        email=email,
        is_admin=is_admin,
        is_active=is_active,
    )
    db.add(user)
    if send_welcome:
        send_welcome_email(user)
    return user

# Now callers MUST name the arguments:
create_user('Alice', 'alice@example.com', is_admin=True, is_active=False)
create_user('Bob', 'bob@co.com', is_active=True, send_welcome=False)

# Old positional calls now raise TypeError:
# create_user('Alice', 'alice@example.com', True, False, True)
# TypeError: create_user() takes 2 positional arguments but 5 were given
```

The `*` forces all boolean parameters to be keyword-only, making misuse impossible. Sensible defaults (`is_admin=False`, `is_active=True`) mean callers only specify what they're changing.'''
    ),
    (
        "thinking/debug-time-of-check-time-of-use",
        "Our file upload endpoint has a security vulnerability. A penetration tester was able to write files outside the upload directory despite our path validation:\n\n```python\nimport os\n\nUPLOAD_DIR = '/var/uploads'\n\ndef upload_file(filename, content):\n    # Validate: no path traversal\n    full_path = os.path.join(UPLOAD_DIR, filename)\n    real_path = os.path.realpath(full_path)\n    \n    if not real_path.startswith(UPLOAD_DIR):\n        raise SecurityError('Path traversal detected')\n    \n    # Check file doesn't already exist\n    if os.path.exists(real_path):\n        raise FileExistsError('File already exists')\n    \n    # Write the file\n    with open(real_path, 'wb') as f:\n        f.write(content)\n```\n\nThe validation looks correct — it resolves symlinks and checks the prefix. How was it bypassed?",
        r'''<think>
This is a classic TOCTOU (Time-of-Check-Time-of-Use) race condition.

**The race:**
1. `os.path.realpath(full_path)` resolves symlinks → gets legitimate path inside UPLOAD_DIR
2. Validation passes ✓
3. **WINDOW OF OPPORTUNITY** — between validation and `open()`
4. Attacker replaces a directory component with a symlink to `/etc/` (or wherever)
5. `open(real_path, 'wb')` follows the NEW symlink

Wait, `real_path` is already resolved to an absolute path without symlinks. So replacing a symlink after `realpath` wouldn't affect `real_path`... unless the attacker creates a symlink at `real_path` itself.

Actually, let me reconsider. The TOCTOU here is:
1. `realpath('/var/uploads/../../etc/passwd')` → catches traversal, raises error ✓
2. But what about: `filename = 'innocent.txt'`
3. `realpath('/var/uploads/innocent.txt')` → `/var/uploads/innocent.txt` ✓
4. Validation passes ✓
5. Attacker creates a **symlink** at `/var/uploads/innocent.txt` → `/etc/cron.d/backdoor`
6. `open('/var/uploads/innocent.txt', 'wb')` follows the symlink → writes to `/etc/cron.d/backdoor`

The race window is between step 3-4 (the check) and step 6 (the use). If the attacker has any ability to create symlinks in UPLOAD_DIR (perhaps via another vulnerability, or if they have limited write access), they can exploit this.

But actually the more common attack: if `UPLOAD_DIR` itself or a parent directory has a symlink that can be swapped. Or using race conditions on directory creation.

The fix is to use `O_NOFOLLOW` and `open()` relative to a directory file descriptor (openat2 with RESOLVE_NO_SYMLINKS), or at minimum, check realpath again after opening.

A simpler fix: generate random filenames server-side instead of trusting user filenames at all.
</think>

This is a **TOCTOU (Time-of-Check-Time-of-Use)** race condition. Between the validation and the `open()` call, an attacker can swap a directory or file with a symlink.

## The Attack

1. Attacker uploads `subdir/payload.txt` — validation passes, path is `/var/uploads/subdir/payload.txt`
2. **Race window** between `realpath()` check and `open()`
3. Attacker (with limited access to UPLOAD_DIR) replaces `subdir` with a symlink: `subdir → /etc/cron.d`
4. `open('/var/uploads/subdir/payload.txt')` follows the symlink → writes to `/etc/cron.d/payload.txt`

## Fix: Don't Trust User Filenames + O_NOFOLLOW

```python
import os
import uuid
import hashlib

UPLOAD_DIR = '/var/uploads'

def upload_file(filename, content):
    # Generate safe filename — never use user input in paths
    ext = os.path.splitext(filename)[1][:10]  # Keep extension, limit length
    safe_ext = ''.join(c for c in ext if c.isalnum() or c == '.')
    safe_name = f"{uuid.uuid4().hex}{safe_ext}"

    full_path = os.path.join(UPLOAD_DIR, safe_name)

    # Open with O_NOFOLLOW | O_CREAT | O_EXCL — atomic, no symlink following
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW

    try:
        fd = os.open(full_path, flags, 0o644)
        try:
            os.write(fd, content)
        finally:
            os.close(fd)
    except OSError as e:
        raise SecurityError(f"Failed to write file: {e}")

    # Verify after write (belt and suspenders)
    real_path = os.path.realpath(full_path)
    if not real_path.startswith(UPLOAD_DIR + os.sep):
        os.unlink(full_path)
        raise SecurityError("Path traversal detected post-write")

    # Store mapping: original_name → safe_name in DB
    db.execute(
        'INSERT INTO uploads (original_name, stored_name) VALUES (?, ?)',
        (filename, safe_name)
    )
    return safe_name
```

**Key defenses:**
1. **Never use user filenames** — generate random names, store the original in the DB
2. **`O_NOFOLLOW`** — kernel refuses to follow symlinks during open
3. **`O_EXCL`** — atomic create-or-fail, no race window
4. **Post-write verification** — belt and suspenders'''
    ),
    (
        "thinking/debug-deepcopy-performance-trap",
        "A function that copies user settings takes 200ms for some users. Profiling shows `copy.deepcopy` is the bottleneck:\n\n```python\nimport copy\n\ndef apply_overrides(base_settings, overrides):\n    \"\"\"Apply user overrides to base settings without mutating base.\"\"\"\n    settings = copy.deepcopy(base_settings)  # 200ms for large settings!\n    for key, value in overrides.items():\n        settings[key] = value\n    return settings\n\n# base_settings is a large nested dict loaded at startup:\n# { 'theme': { 'colors': { ... 200 entries ... }, 'fonts': { ... } },\n#   'permissions': { ... deeply nested ... },\n#   'features': { ... 500 feature flags ... } }\n```",
        r'''<think>
`copy.deepcopy` recursively copies every object in the entire nested structure. For a large settings dict with hundreds of entries and deep nesting, this is extremely expensive — it traverses and copies every dict, list, string, and object, maintaining a memo dict to handle circular references.

The fix depends on what `overrides` actually changes. If overrides only modify top-level keys, we only need a shallow copy. If they modify nested values, we need structural sharing (copy-on-write) — only copy the path that changes, share everything else.
</think>

`deepcopy` recursively copies every object in the entire tree, even the 99% that isn't being overridden. For a settings dict with hundreds of nested entries, this is pure waste.

## Fix: Structural Sharing (Copy Only What Changes)

```python
def apply_overrides(base_settings: dict, overrides: dict) -> dict:
    """Shallow copy top level, deep-merge only override paths."""
    # Shallow copy — O(n) where n = number of top-level keys, not total objects
    settings = {**base_settings}

    for key, value in overrides.items():
        if (
            key in settings
            and isinstance(settings[key], dict)
            and isinstance(value, dict)
        ):
            # Recursively merge only the changed branch
            settings[key] = apply_overrides(settings[key], value)
        else:
            settings[key] = value

    return settings

# Usage — only copies the 'theme' branch, shares 'permissions' and 'features'
new_settings = apply_overrides(base_settings, {
    'theme': {'colors': {'primary': '#ff0000'}}
})
```

**Before:** `deepcopy` copies all 700+ nested objects every call → 200ms
**After:** shallow dict merge copies only the path to the changed key → <1ms

The unchanged branches (`permissions`, `features`, most of `theme`) are shared references to the original — safe because we never mutate them.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
