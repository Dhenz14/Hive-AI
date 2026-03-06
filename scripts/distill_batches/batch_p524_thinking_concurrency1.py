"""Phase 1G: Foundation Thinking — Concurrency & Distributed Systems (Part 1/5)
Threading, locking, race conditions, deadlocks, Python concurrency primitives."""

PAIRS = [
    (
        "thinking/concurrency-race-condition-patterns",
        "We have a ticket booking system and sometimes two users book the same seat. Here's our code:\n\n```python\ndef book_seat(user_id, seat_id):\n    seat = db.query('SELECT * FROM seats WHERE id = %s', seat_id)\n    if seat.status == 'available':\n        db.execute('UPDATE seats SET status = %s, booked_by = %s WHERE id = %s',\n                   ('booked', user_id, seat_id))\n        return {'success': True, 'seat': seat_id}\n    return {'success': False, 'error': 'Seat already booked'}\n```\n\nHow is double-booking possible and how do I fix it?",
        r"""<think>
This is a classic TOCTOU (Time Of Check, Time Of Use) race condition.

The timeline:
1. Thread A: SELECT seat → status='available'
2. Thread B: SELECT seat → status='available' (same seat, still available)
3. Thread A: UPDATE seat SET status='booked' → success
4. Thread B: UPDATE seat SET status='booked' → also success! Double booking!

The gap between CHECK (SELECT) and USE (UPDATE) is where the race lives.

Fixes:
1. SELECT FOR UPDATE — locks the row during the transaction
2. Atomic UPDATE with WHERE clause — only updates if still available
3. Unique constraint — database prevents duplicates

Option 2 is simplest and most performant.
</think>

This is a **TOCTOU race condition** — Time Of Check, Time Of Use:

```
Thread A: SELECT seat → available ✓
Thread B: SELECT seat → available ✓  (gap between check and update)
Thread A: UPDATE → booked
Thread B: UPDATE → booked again! 💥 Double booking
```

## Fix 1: Atomic UPDATE (Simplest, Best Performance)

```python
def book_seat(user_id, seat_id):
    # Combine check + update into ONE atomic statement
    result = db.execute(
        '''UPDATE seats
           SET status = 'booked', booked_by = %s
           WHERE id = %s AND status = 'available'
           RETURNING id''',
        (user_id, seat_id)
    )
    if result.rowcount == 1:
        return {'success': True, 'seat': seat_id}
    return {'success': False, 'error': 'Seat already booked'}
```

No gap between check and update — the database handles atomicity.

## Fix 2: SELECT FOR UPDATE (When You Need Complex Logic)

```python
def book_seat(user_id, seat_id):
    with db.transaction():
        seat = db.query(
            'SELECT * FROM seats WHERE id = %s FOR UPDATE',  # Locks the row
            seat_id
        )
        if seat.status != 'available':
            return {'success': False, 'error': 'Seat already booked'}

        # Complex business logic here (pricing, validation, etc.)
        validate_user_eligible(user_id, seat)

        db.execute(
            'UPDATE seats SET status = %s, booked_by = %s WHERE id = %s',
            ('booked', user_id, seat_id)
        )
        return {'success': True, 'seat': seat_id}
```

`FOR UPDATE` locks the row — Thread B blocks until Thread A's transaction completes.

## Fix 3: Unique Constraint (Defense in Depth)

```sql
-- Add as a safety net regardless of application logic
ALTER TABLE seats ADD CONSTRAINT unique_booking
    UNIQUE (id, status) WHERE status = 'booked';
-- Or: one-booking-per-seat constraint
CREATE UNIQUE INDEX idx_one_booking_per_seat
    ON bookings (seat_id) WHERE cancelled = false;
```

**Use Fix 1 for simple cases, Fix 2 when you need logic between read and write, and always add Fix 3 as a safety net.**"""
    ),
    (
        "thinking/concurrency-python-gil",
        "My Python web scraper uses threading but isn't faster than single-threaded. I have 8 CPU cores. What's wrong?\n\n```python\nimport threading\n\ndef scrape_and_parse(urls):\n    results = []\n    threads = []\n    for url in urls:\n        t = threading.Thread(target=lambda u: results.append(fetch_and_parse(u)), args=(url,))\n        threads.append(t)\n        t.start()\n    for t in threads:\n        t.join()\n    return results\n\ndef fetch_and_parse(url):\n    response = requests.get(url)        # I/O bound\n    return heavy_html_parsing(response)  # CPU bound\n```",
        r'''<think>
Two problems:

1. **GIL issue**: Python's Global Interpreter Lock means threads can't run CPU-bound Python code in parallel. `heavy_html_parsing` is CPU-bound, so threads take turns on one core. Threading helps with I/O (waiting for network) but not with CPU (parsing HTML).

2. **Thread safety**: `results.append()` in a lambda is actually thread-safe in CPython (due to GIL), but the closure over `url` in the lambda has a classic late-binding bug — all threads might use the last URL.

Wait, actually they pass `url` as `args=(url,)` but the lambda ignores the argument — `lambda u: results.append(fetch_and_parse(u))` takes `u` but the `args=(url,)` passes it correctly. Actually no, look closer: the lambda parameter is `u` and `args=(url,)` passes the current `url` as `u`. So the lambda does use `u`. That part is actually fine.

But the main issue is GIL + CPU-bound work.

Solution:
- Use `concurrent.futures.ThreadPoolExecutor` for I/O
- Use `multiprocessing` or `ProcessPoolExecutor` for CPU-bound parsing
- Or: separate I/O and CPU phases
</think>

Two issues: the **GIL blocks CPU parallelism**, and you're mixing I/O-bound and CPU-bound work.

## The GIL Problem

Python's Global Interpreter Lock means only ONE thread runs Python code at a time:

```
Threading with I/O (network wait): ✅ Parallel
Thread 1: [fetch]----wait----[fetch]----wait----
Thread 2: ------[fetch]----wait----[fetch]------
                    I/O releases the GIL

Threading with CPU (parsing): ❌ Sequential
Thread 1: [parse]........[parse]........
Thread 2: ........[parse]........[parse]
                    GIL forces turns
```

## Fix: Separate I/O from CPU Work

```python
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor

def scrape_and_parse(urls):
    # Phase 1: Fetch in threads (I/O-bound → threads are perfect)
    with ThreadPoolExecutor(max_workers=20) as pool:
        responses = list(pool.map(fetch, urls))

    # Phase 2: Parse in processes (CPU-bound → bypass GIL)
    with ProcessPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(heavy_html_parsing, responses))

    return results

def fetch(url):
    return requests.get(url).text  # Returns serializable data
```

## Or: Use asyncio for I/O (Even Better)

```python
import asyncio
import aiohttp
from concurrent.futures import ProcessPoolExecutor

async def scrape_and_parse(urls):
    # Phase 1: Async I/O (thousands of concurrent requests)
    async with aiohttp.ClientSession() as session:
        tasks = [fetch(session, url) for url in urls]
        html_pages = await asyncio.gather(*tasks)

    # Phase 2: CPU parsing in process pool
    loop = asyncio.get_event_loop()
    with ProcessPoolExecutor(max_workers=4) as pool:
        results = await asyncio.gather(*[
            loop.run_in_executor(pool, heavy_html_parsing, html)
            for html in html_pages
        ])

    return results

async def fetch(session, url):
    async with session.get(url) as response:
        return await response.text()
```

## When to Use What

| Work Type | Best Tool | Why |
|-----------|-----------|-----|
| Network I/O (HTTP, DB) | `asyncio` or `ThreadPoolExecutor` | Waiting releases GIL |
| File I/O | `ThreadPoolExecutor` | OS handles blocking |
| CPU computation | `ProcessPoolExecutor` | Each process has own GIL |
| Mixed I/O + CPU | Async I/O + Process pool | Best of both |

**Rule**: Threads for waiting, processes for computing. Never use threads for CPU-bound Python.'''
    ),
    (
        "thinking/concurrency-deadlock-detection",
        "Our Python service hangs in production every few days. We suspect a deadlock but can't reproduce it. How do I detect and fix deadlocks?\n\n```python\naccount_locks = {}\n\ndef get_lock(account_id):\n    if account_id not in account_locks:\n        account_locks[account_id] = threading.Lock()\n    return account_locks[account_id]\n\ndef transfer(from_id, to_id, amount):\n    from_lock = get_lock(from_id)\n    to_lock = get_lock(to_id)\n    \n    with from_lock:\n        with to_lock:\n            from_account = get_account(from_id)\n            to_account = get_account(to_id)\n            from_account.balance -= amount\n            to_account.balance += amount\n            save(from_account, to_account)\n```",
        r'''<think>
Classic deadlock: Thread A transfers from account 1→2, Thread B transfers from account 2→1.

Thread A: locks account 1, tries to lock account 2
Thread B: locks account 2, tries to lock account 1
Both wait forever → deadlock.

Also: `get_lock()` has a race condition — two threads could both see `account_id not in account_locks` and create separate locks.

Fixes:
1. Always acquire locks in a consistent order (e.g., by account ID)
2. Use `lock.acquire(timeout=...)` to detect deadlocks
3. Use database-level locking instead (SELECT FOR UPDATE with consistent ordering)
</think>

**Classic deadlock** — two threads lock resources in opposite order:

```
Thread A: transfer(1, 2, $100)    Thread B: transfer(2, 1, $50)
  lock(account_1) ✓                 lock(account_2) ✓
  lock(account_2) ⏳ WAIT            lock(account_1) ⏳ WAIT
       ↑ waiting for B                    ↑ waiting for A
                    DEADLOCK 💀
```

Also: `get_lock()` has a race condition — two threads can create separate Lock objects for the same account.

## Fix 1: Consistent Lock Ordering

```python
import threading

_lock_registry = {}
_registry_lock = threading.Lock()

def get_lock(account_id):
    with _registry_lock:  # Thread-safe registry
        if account_id not in _lock_registry:
            _lock_registry[account_id] = threading.Lock()
        return _lock_registry[account_id]

def transfer(from_id, to_id, amount):
    # ALWAYS lock in ascending ID order — prevents deadlock
    first_id, second_id = sorted([from_id, to_id])
    first_lock = get_lock(first_id)
    second_lock = get_lock(second_id)

    with first_lock:
        with second_lock:
            from_account = get_account(from_id)
            to_account = get_account(to_id)
            if from_account.balance < amount:
                raise InsufficientFunds()
            from_account.balance -= amount
            to_account.balance += amount
            save(from_account, to_account)
```

Now both threads lock in the same order — no deadlock possible.

## Fix 2: Timeout-Based Detection

```python
def transfer(from_id, to_id, amount):
    first_id, second_id = sorted([from_id, to_id])
    first_lock = get_lock(first_id)
    second_lock = get_lock(second_id)

    if not first_lock.acquire(timeout=5):
        raise DeadlockDetected(f"Timeout acquiring lock for account {first_id}")
    try:
        if not second_lock.acquire(timeout=5):
            raise DeadlockDetected(f"Timeout acquiring lock for account {second_id}")
        try:
            # ... transfer logic
            pass
        finally:
            second_lock.release()
    finally:
        first_lock.release()
```

## Fix 3: Use Database Locking (Best for Production)

```python
def transfer(from_id, to_id, amount):
    # Let the database handle locking — no application-level locks needed
    with db.transaction():
        # Lock rows in consistent order
        first_id, second_id = sorted([from_id, to_id])
        db.execute(
            'SELECT * FROM accounts WHERE id IN (%s, %s) ORDER BY id FOR UPDATE',
            (first_id, second_id)
        )

        from_acc = db.get_account(from_id)
        to_acc = db.get_account(to_id)

        if from_acc.balance < amount:
            raise InsufficientFunds()

        db.execute('UPDATE accounts SET balance = balance - %s WHERE id = %s',
                   (amount, from_id))
        db.execute('UPDATE accounts SET balance = balance + %s WHERE id = %s',
                   (amount, to_id))
```

## Deadlock Prevention Rules
1. **Always acquire locks in a consistent order** (alphabetical, numerical)
2. **Use timeouts** on lock acquisition to detect deadlocks
3. **Prefer database-level locking** over application-level locks
4. **Keep lock scope minimal** — hold locks for the shortest time possible'''
    ),
    (
        "thinking/concurrency-async-patterns",
        "I'm migrating a Flask app to async (FastAPI). What are the common async pitfalls I need to avoid?",
        r'''<think>
Common async migration pitfalls:
1. Blocking calls in async functions (defeats the purpose)
2. Not understanding the event loop model
3. Missing `await` (returns coroutine instead of result)
4. CPU-bound work blocking the event loop
5. Database connection pool misconfiguration
6. Background tasks that crash silently
7. Sync libraries that don't work in async context
</think>

## The 7 Async Pitfalls

### 1. Blocking the Event Loop

```python
# BAD: requests.get() blocks the entire event loop
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    response = requests.get(f"http://api.example.com/users/{user_id}")  # BLOCKS!
    return response.json()
    # While this waits, NO other requests can be processed

# GOOD: Use async HTTP client
import httpx

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    async with httpx.AsyncClient() as client:
        response = await client.get(f"http://api.example.com/users/{user_id}")
    return response.json()
```

### 2. Sync Database Calls in Async Handlers

```python
# BAD: SQLAlchemy sync engine blocks
@app.get("/orders")
async def get_orders():
    return db.session.query(Order).all()  # BLOCKS!

# GOOD: Use async SQLAlchemy
from sqlalchemy.ext.asyncio import AsyncSession

@app.get("/orders")
async def get_orders(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Order))
    return result.scalars().all()
```

### 3. Forgetting `await`

```python
# BAD: Returns a coroutine object, not the result
@app.get("/data")
async def get_data():
    result = fetch_from_cache()  # Missing await!
    return result  # Returns <coroutine object> not actual data

# GOOD:
async def get_data():
    result = await fetch_from_cache()
    return result
```

### 4. CPU-Bound Work Blocking the Loop

```python
# BAD: Heavy computation blocks all requests
@app.post("/analyze")
async def analyze(data: dict):
    result = heavy_computation(data)  # Blocks for 5 seconds
    return result
    # ALL other requests stall for 5 seconds

# GOOD: Run in thread/process pool
import asyncio
from concurrent.futures import ProcessPoolExecutor

executor = ProcessPoolExecutor(max_workers=4)

@app.post("/analyze")
async def analyze(data: dict):
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(executor, heavy_computation, data)
    return result
```

### 5. Fire-and-Forget Tasks That Crash Silently

```python
# BAD: Exception is silently lost
@app.post("/orders")
async def create_order(data: dict):
    order = await save_order(data)
    asyncio.create_task(send_confirmation(order))  # If this crashes, nobody knows
    return order

# GOOD: Handle task exceptions
async def tracked_task(coro):
    try:
        await coro
    except Exception:
        logger.exception("Background task failed")

@app.post("/orders")
async def create_order(data: dict):
    order = await save_order(data)
    asyncio.create_task(tracked_task(send_confirmation(order)))
    return order
```

### 6. Connection Pool Exhaustion

```python
# BAD: Creating new client per request
@app.get("/external")
async def proxy():
    async with httpx.AsyncClient() as client:  # New connection each time
        return await client.get("http://api.example.com/data")

# GOOD: Shared client with connection pool
client = httpx.AsyncClient(
    limits=httpx.Limits(max_connections=100, max_keepalive_connections=20)
)

@app.on_event("shutdown")
async def shutdown():
    await client.aclose()

@app.get("/external")
async def proxy():
    response = await client.get("http://api.example.com/data")
    return response.json()
```

### 7. Mixing Sync and Async Incorrectly

```python
# BAD: Calling async from sync
def sync_function():
    result = asyncio.run(async_function())  # Creates new event loop — crashes if one exists

# GOOD: Use run_in_executor for sync→async bridge
# Or keep the entire call chain async
```

**Migration rule**: Replace EVERY blocking I/O call (requests, psycopg2, open(), time.sleep) with its async equivalent before deploying.'''
    ),
    (
        "thinking/concurrency-producer-consumer",
        "I need to process uploaded files asynchronously. Users upload files, and a background worker processes them. What's the right pattern?",
        r'''<think>
Producer-consumer pattern with a queue. Options:
1. In-process queue (threading.Queue) — simple, single-server
2. Redis queue (RQ, Celery) — distributed, persistent
3. Message broker (RabbitMQ, Kafka) — enterprise, guaranteed delivery

For most web apps, a Redis-backed task queue (Celery or RQ) is the sweet spot.

Let me show the pattern progression.
</think>

**Producer-consumer with a task queue.** Here's the progression from simple to production-ready:

## Level 1: In-Process Queue (Development)

```python
import queue
import threading

task_queue = queue.Queue()

def upload_handler(request):
    """Producer: add work to queue."""
    file = save_upload(request.file)
    task_queue.put({'file_id': file.id, 'action': 'process'})
    return {'status': 'queued', 'file_id': file.id}

def worker():
    """Consumer: process work from queue."""
    while True:
        task = task_queue.get()
        try:
            process_file(task['file_id'])
        except Exception:
            logger.exception(f"Failed to process {task['file_id']}")
        finally:
            task_queue.task_done()

# Start worker thread
threading.Thread(target=worker, daemon=True).start()
```

**Problem**: If the server crashes, queued tasks are lost.

## Level 2: Redis Queue (Production)

```python
# tasks.py (Celery)
from celery import Celery

app = Celery('tasks', broker='redis://localhost:6379/0')

@app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_file(self, file_id):
    try:
        file = File.objects.get(id=file_id)
        file.status = 'processing'
        file.save()

        result = run_processing_pipeline(file)

        file.status = 'completed'
        file.result_url = result.url
        file.save()
    except TransientError as exc:
        file.status = 'retrying'
        file.save()
        raise self.retry(exc=exc)
    except Exception:
        file.status = 'failed'
        file.save()
        raise

# views.py (Producer)
def upload_handler(request):
    file = save_upload(request.file)
    file.status = 'queued'
    file.save()

    # Send to background worker
    process_file.delay(file.id)

    return {'status': 'queued', 'file_id': file.id}
```

```python
# API for checking status
@app.get("/api/files/{file_id}/status")
def check_status(file_id):
    file = File.objects.get(id=file_id)
    return {
        'file_id': file.id,
        'status': file.status,
        'result_url': file.result_url,
    }
```

## Level 3: With Progress Tracking

```python
@app.task(bind=True)
def process_file(self, file_id):
    file = File.objects.get(id=file_id)
    steps = ['validate', 'transform', 'compress', 'upload']

    for i, step in enumerate(steps):
        self.update_state(
            state='PROGRESS',
            meta={'step': step, 'progress': i / len(steps) * 100}
        )
        run_step(step, file)

    return {'status': 'completed', 'url': file.result_url}

# Check progress
@app.get("/api/files/{file_id}/progress")
def check_progress(file_id):
    result = AsyncResult(file_id)
    if result.state == 'PROGRESS':
        return result.info  # {'step': 'transform', 'progress': 50}
    return {'state': result.state}
```

## Key Patterns

1. **Idempotent tasks** — processing the same file twice should be safe
2. **Status tracking** — user can poll for progress
3. **Retry with backoff** — transient failures auto-retry
4. **Dead letter queue** — permanently failed tasks go to a DLQ for inspection
5. **Rate limiting** — don't overwhelm downstream services'''
    ),
    (
        "thinking/concurrency-thread-safe-singleton",
        "I need a thread-safe configuration manager that loads config once and provides it to all threads. How do I implement this correctly in Python?",
        r'''<think>
Thread-safe lazy initialization in Python. Options:
1. Module-level initialization (simplest, Python handles it)
2. threading.Lock for lazy init
3. Double-checked locking (broken in some languages, works in Python due to GIL but not recommended)

Actually in Python, the simplest and best approach is module-level initialization or using `functools.lru_cache` or a class with `__init_subclass__`. But for a true lazy singleton, threading.Lock is the right approach.

Let me show the progression.
</think>

## Option 1: Module-Level (Simplest, Usually Best)

```python
# config.py — Python imports are thread-safe and execute once
import json

def _load_config():
    with open('config.json') as f:
        return json.load(f)

CONFIG = _load_config()  # Loaded once at import time

# Usage (any thread):
from config import CONFIG
print(CONFIG['database_url'])
```

Python's import system uses a lock internally — `CONFIG` is initialized exactly once, even with multiple threads importing simultaneously.

## Option 2: Lazy Singleton with Lock (When Import-Time Init Is Too Early)

```python
import threading

class ConfigManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                # Double-check inside the lock
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._config = instance._load()
                    cls._instance = instance
        return cls._instance

    def _load(self):
        with open('config.json') as f:
            return json.load(f)

    def get(self, key, default=None):
        return self._config.get(key, default)

    def reload(self):
        """Thread-safe config reload."""
        with self._lock:
            self._config = self._load()

# Usage:
config = ConfigManager()
db_url = config.get('database_url')
```

## Option 3: `functools.lru_cache` (Cleanest for Functions)

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_config():
    """Called once, cached forever. Thread-safe in CPython."""
    with open('config.json') as f:
        return json.load(f)

# Usage:
config = get_config()
```

## Which to Use

| Scenario | Approach |
|----------|----------|
| Config available at import time | Module-level `CONFIG = load()` |
| Config needs lazy initialization | `@lru_cache` function |
| Config needs reloading at runtime | Singleton with Lock |
| Config from environment variables | Module-level (env vars available at import) |

**Default choice**: Module-level initialization. It's the simplest, thread-safe by design, and covers 90% of use cases.'''
    ),
    (
        "thinking/concurrency-connection-pool-patterns",
        "Our API is getting 'connection pool exhausted' errors under load. We use SQLAlchemy with a connection pool of 10. How do I diagnose and fix this?",
        r'''<think>
Connection pool exhaustion happens when:
1. Pool size is too small for the concurrency level
2. Connections aren't being returned (leaked)
3. Queries are too slow (holding connections too long)
4. N+1 queries use multiple connections per request
5. Long-running transactions hold connections

Diagnosis steps:
- Check pool size vs concurrent requests
- Check for connection leaks (not closing sessions)
- Check for slow queries holding connections
- Add pool event listeners to track

Fixes:
- Right-size the pool
- Fix connection leaks
- Add pool overflow (temporary connections)
- Add connection timeout
- Optimize slow queries
</think>

## Diagnosing the Problem

### Step 1: Check Pool Size vs Concurrency

```python
# If you have 10 pool connections and 20 concurrent requests,
# 10 requests will wait for connections
# Default: pool_size=5, max_overflow=10 = 15 total

# Check current pool status
from sqlalchemy import event

@event.listens_for(engine, "checkout")
def on_checkout(dbapi_conn, connection_rec, connection_proxy):
    logger.info(f"Connection checked out. Pool: {engine.pool.status()}")

@event.listens_for(engine, "checkin")
def on_checkin(dbapi_conn, connection_rec):
    logger.info(f"Connection returned. Pool: {engine.pool.status()}")
```

### Step 2: Find Connection Leaks

```python
# Common leak: session not closed after exception
def bad_handler():
    session = Session()
    user = session.query(User).get(1)  # Gets connection
    if not user:
        return None  # CONNECTION LEAK — session never closed!
    session.close()
    return user

# Fix: always use context manager
def good_handler():
    with Session() as session:
        user = session.query(User).get(1)
        return user
    # Connection automatically returned even if exception occurs
```

### Step 3: Find Slow Queries Hogging Connections

```python
@event.listens_for(engine, "before_cursor_execute")
def before_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info['query_start'] = time.time()

@event.listens_for(engine, "after_cursor_execute")
def after_execute(conn, cursor, statement, parameters, context, executemany):
    elapsed = time.time() - conn.info['query_start']
    if elapsed > 1.0:
        logger.warning(f"Slow query ({elapsed:.1f}s): {statement[:200]}")
```

## Fixing the Problem

```python
engine = create_engine(
    DATABASE_URL,
    pool_size=20,           # Base pool connections
    max_overflow=30,        # Temporary connections when pool is full
    pool_timeout=10,        # Wait 10s for connection before error
    pool_recycle=1800,      # Recycle connections every 30 min
    pool_pre_ping=True,     # Verify connection is alive before using
)
```

### Right-Sizing Formula

```
pool_size = max_concurrent_requests × connections_per_request
           = (web_workers × threads_per_worker) × 1
           = 4 workers × 4 threads × 1
           = 16

max_overflow = pool_size × 0.5  # 50% burst capacity
             = 8

# PostgreSQL max_connections must be > sum of all pool_sizes
# across all application instances
```

### Request-Scoped Sessions (Prevent Leaks)

```python
# FastAPI dependency
async def get_db():
    session = AsyncSession(engine)
    try:
        yield session
    finally:
        await session.close()  # ALWAYS returns connection

@app.get("/users/{id}")
async def get_user(id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.id == id))
    return result.scalar_one()
```'''
    ),
    (
        "thinking/concurrency-distributed-locking",
        "We have 4 API servers behind a load balancer. We need to ensure only one server processes a scheduled job at a time. `threading.Lock()` doesn't work across servers. What do I use?",
        r'''<think>
Distributed locking options:
1. Redis-based lock (Redlock)
2. Database advisory lock (PostgreSQL pg_advisory_lock)
3. ZooKeeper/etcd distributed lock
4. File-based lock (only works on shared filesystem)

For most web apps, Redis or PostgreSQL advisory locks are the simplest choices.

Redis: fast, well-supported (redis-py has lock built in)
PostgreSQL: no extra infrastructure if you already have it
</think>

## Option 1: Redis Distributed Lock (Most Common)

```python
import redis

redis_client = redis.Redis(host='localhost', port=6379)

def run_scheduled_job():
    lock = redis_client.lock(
        'scheduled_job:daily_report',
        timeout=300,        # Lock expires after 5 min (prevent deadlock)
        blocking=True,
        blocking_timeout=5, # Wait up to 5s for lock
    )

    acquired = lock.acquire()
    if not acquired:
        logger.info("Another server is running the job, skipping")
        return

    try:
        logger.info("Acquired lock, running daily report")
        generate_daily_report()
    finally:
        try:
            lock.release()
        except redis.exceptions.LockNotOwnedError:
            logger.warning("Lock expired before job completed")
```

## Option 2: PostgreSQL Advisory Lock (No Extra Infra)

```python
import hashlib

def run_scheduled_job():
    # Convert job name to a consistent integer for pg_advisory_lock
    lock_id = int(hashlib.md5(b'daily_report').hexdigest()[:8], 16)

    with db.engine.connect() as conn:
        # Try to acquire — returns immediately (non-blocking)
        result = conn.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": lock_id}
        ).scalar()

        if not result:
            logger.info("Another server holds the lock, skipping")
            return

        try:
            generate_daily_report()
        finally:
            conn.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": lock_id}
            )
```

## Option 3: Decorator for Reuse

```python
import functools

def distributed_lock(name, timeout=300):
    """Decorator: only one server runs this function at a time."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            lock = redis_client.lock(
                f'distributed_lock:{name}',
                timeout=timeout,
                blocking=False,
            )
            if not lock.acquire():
                logger.info(f"Lock '{name}' held by another server, skipping")
                return None
            try:
                return func(*args, **kwargs)
            finally:
                try:
                    lock.release()
                except redis.exceptions.LockNotOwnedError:
                    pass
        return wrapper
    return decorator

# Usage:
@distributed_lock('daily_report', timeout=600)
def generate_daily_report():
    ...

@distributed_lock('cleanup_expired', timeout=120)
def cleanup_expired_sessions():
    ...
```

## Comparison

| Method | Pros | Cons |
|--------|------|------|
| Redis lock | Fast, well-tested, auto-expiry | Extra infrastructure |
| PostgreSQL advisory lock | No extra infra | Tied to DB connection lifetime |
| ZooKeeper/etcd | Strongest guarantees | Complex infrastructure |

**Default choice**: Redis if you already use it, PostgreSQL advisory locks otherwise.'''
    ),
    (
        "thinking/concurrency-event-loop-blocking",
        "Our FastAPI app is slow under load. A single slow endpoint causes ALL other endpoints to become slow. What's happening?\n\n```python\n@app.get('/api/report')\nasync def generate_report():\n    data = await db.fetch_all('SELECT * FROM large_table')  # Async DB ✓\n    \n    # Process data (CPU-intensive)\n    result = []\n    for row in data:\n        processed = complex_calculation(row)  # Takes 100ms per row\n        result.append(processed)\n    \n    return {'report': result}\n```",
        r'''<think>
The problem: `complex_calculation` is CPU-bound and runs in the event loop thread. While it's running, the event loop can't process any other requests.

In async Python, there's one thread running the event loop. If you do CPU-bound work in that thread, everything blocks.

The fix: offload CPU-bound work to a thread pool or process pool.
</think>

The CPU-intensive loop **blocks the event loop**. While `complex_calculation` runs for 100ms × N rows, no other request can be processed:

```
Event Loop Thread:
  Request A: [db_query]---await---[CPU CPU CPU CPU CPU CPU]← ALL blocked
  Request B: ............................waiting.............
  Request C: ............................waiting.............
```

## Fix: Offload CPU Work

### Option 1: Run in Thread Pool

```python
import asyncio
from functools import partial

@app.get('/api/report')
async def generate_report():
    data = await db.fetch_all('SELECT * FROM large_table')

    # Offload CPU work to thread pool
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None,  # Default thread pool
        partial(process_data, data),
    )
    return {'report': result}

def process_data(data):
    """Runs in a thread — doesn't block event loop."""
    return [complex_calculation(row) for row in data]
```

### Option 2: Use Process Pool (True Parallelism)

```python
from concurrent.futures import ProcessPoolExecutor

# Create at startup, reuse
process_pool = ProcessPoolExecutor(max_workers=4)

@app.get('/api/report')
async def generate_report():
    data = await db.fetch_all('SELECT * FROM large_table')

    loop = asyncio.get_event_loop()

    # Split work across processes
    chunks = split_into_chunks(data, n=4)
    futures = [
        loop.run_in_executor(process_pool, process_chunk, chunk)
        for chunk in chunks
    ]
    results = await asyncio.gather(*futures)
    return {'report': flatten(results)}
```

### Option 3: FastAPI's Built-in Thread Pool

```python
# Simply make the endpoint sync — FastAPI auto-runs it in a thread pool
@app.get('/api/report')
def generate_report():  # No `async` keyword!
    data = db.fetch_all_sync('SELECT * FROM large_table')
    result = [complex_calculation(row) for row in data]
    return {'report': result}
# FastAPI runs sync endpoints in a thread pool automatically
```

## When to Use `async def` vs `def` in FastAPI

| Endpoint Type | Keyword | Why |
|--------------|---------|-----|
| Only I/O (DB, HTTP) | `async def` | Efficient, doesn't block loop |
| Only CPU work | `def` | Auto-runs in thread pool |
| Mixed I/O + CPU | `async def` + `run_in_executor` | I/O stays async, CPU offloaded |

**Rule**: If your `async def` function does anything CPU-intensive for >1ms, offload it. One blocking endpoint kills the performance of ALL endpoints.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
