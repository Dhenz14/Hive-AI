"""Thinking-trace pairs: concurrency patterns, race conditions, and parallel programming."""

PAIRS = [
    (
        "thinking/concurrency-deadlock",
        "We have two services that transfer money between accounts. Occasionally the system freezes and stops processing. Here's the code:\n\n```python\nimport threading\n\naccount_locks = {}  # account_id -> Lock\n\ndef get_lock(account_id):\n    if account_id not in account_locks:\n        account_locks[account_id] = threading.Lock()\n    return account_locks[account_id]\n\ndef transfer(from_id, to_id, amount):\n    from_lock = get_lock(from_id)\n    to_lock = get_lock(to_id)\n    \n    from_lock.acquire()\n    to_lock.acquire()\n    \n    try:\n        from_balance = get_balance(from_id)\n        if from_balance >= amount:\n            set_balance(from_id, from_balance - amount)\n            set_balance(to_id, get_balance(to_id) + amount)\n    finally:\n        to_lock.release()\n        from_lock.release()\n```",
        r'''<think>
Classic deadlock. Let me trace through the scenario:

**Thread 1**: `transfer(A, B, 100)`
**Thread 2**: `transfer(B, A, 50)`

```
Time 1: Thread 1 acquires lock_A       Thread 2 acquires lock_B
Time 2: Thread 1 tries to acquire lock_B  → BLOCKED (Thread 2 holds it)
         Thread 2 tries to acquire lock_A  → BLOCKED (Thread 1 holds it)
```

Both threads are waiting for a lock the other holds. Neither can proceed. Classic circular wait deadlock.

**The four conditions for deadlock (Coffman conditions):**
1. Mutual exclusion: locks are exclusive ✓
2. Hold and wait: thread holds one lock while waiting for another ✓
3. No preemption: can't force a thread to release its lock ✓
4. Circular wait: A→B and B→A ✓

Break any one condition to prevent deadlock. The easiest is #4: **prevent circular wait by imposing a global lock ordering**.

**Fix: Always acquire locks in a consistent order (by account ID)**

```python
def transfer(from_id, to_id, amount):
    # Always lock lower ID first — breaks circular wait
    first, second = sorted([from_id, to_id])
    lock1, lock2 = get_lock(first), get_lock(second)
    ...
```

Now both `transfer(A, B)` and `transfer(B, A)` acquire `lock_A` first (if A < B). No circular wait possible.

**Additional bug: `get_lock` has a race condition**

```python
def get_lock(account_id):
    if account_id not in account_locks:  # Thread 1 checks: not in dict
        account_locks[account_id] = threading.Lock()  # Thread 1 creates lock
    # Thread 2 also checked "not in dict" before Thread 1 wrote — creates a SECOND lock
    return account_locks[account_id]
```

Two threads could create different Lock objects for the same account. One thread's lock doesn't protect against the other's. This is a TOCTOU race.

Fix: use `setdefault` (atomic in CPython due to GIL, but not guaranteed) or a dedicated lock for the dictionary:

```python
_dict_lock = threading.Lock()
def get_lock(account_id):
    with _dict_lock:
        if account_id not in account_locks:
            account_locks[account_id] = threading.Lock()
        return account_locks[account_id]
```

Or simpler: use `defaultdict` which is atomic for `__missing__` in CPython:
```python
from collections import defaultdict
account_locks = defaultdict(threading.Lock)
```

Actually, `defaultdict` with `threading.Lock` as the factory creates locks on demand. But `defaultdict.__getitem__` isn't guaranteed atomic across Python implementations. The safest is `_dict_lock`.

**Third issue: the balance operations aren't atomic**

```python
from_balance = get_balance(from_id)
if from_balance >= amount:
    set_balance(from_id, from_balance - amount)
    set_balance(to_id, get_balance(to_id) + amount)
```

This is fine because both accounts are locked. But if `set_balance` or `get_balance` fails (DB error), we could have debited `from_id` without crediting `to_id`. Needs a DB transaction.
</think>

**Deadlock from circular lock ordering.** When Thread 1 does `transfer(A, B)` and Thread 2 does `transfer(B, A)` simultaneously:

```
Thread 1: holds lock_A, waiting for lock_B
Thread 2: holds lock_B, waiting for lock_A
→ Permanent freeze
```

### Three bugs in this code

| Bug | Severity | Impact |
|-----|----------|--------|
| Deadlock from inconsistent lock order | Critical | System freezes, requires restart |
| Race condition in `get_lock()` | High | Two threads get different locks for same account |
| No transaction for balance updates | High | Partial transfer on error (money lost) |

### Fixed version

```python
import threading
from collections import defaultdict
from contextlib import ExitStack

# Thread-safe lock registry
_registry_lock = threading.Lock()
_account_locks: dict[str, threading.Lock] = {}

def get_lock(account_id: str) -> threading.Lock:
    """Thread-safe lock-per-account registry."""
    with _registry_lock:
        if account_id not in _account_locks:
            _account_locks[account_id] = threading.Lock()
        return _account_locks[account_id]

def transfer(from_id: str, to_id: str, amount: float) -> bool:
    if from_id == to_id:
        raise ValueError("Cannot transfer to same account")

    # DEADLOCK FIX: Always acquire locks in sorted order
    # transfer(A, B) and transfer(B, A) both lock A first → no circular wait
    ordered_ids = sorted([from_id, to_id])
    locks = [get_lock(aid) for aid in ordered_ids]

    # Acquire in order using ExitStack for exception-safe release
    with ExitStack() as stack:
        for lock in locks:
            stack.enter_context(lock)  # Calls lock.acquire(), registers lock.release()

        from_balance = get_balance(from_id)
        if from_balance < amount:
            return False

        # In production: wrap in DB transaction
        set_balance(from_id, from_balance - amount)
        set_balance(to_id, get_balance(to_id) + amount)
        return True
```

### Why sorted order prevents deadlock

```
transfer(A, B): locks [A, B] in order A → B
transfer(B, A): locks [A, B] in order A → B  (same order!)

Thread 1: acquires lock_A
Thread 2: tries to acquire lock_A → waits
Thread 1: acquires lock_B → does transfer → releases both
Thread 2: acquires lock_A → acquires lock_B → does transfer
→ No deadlock possible
```

### For production: use the database, not application locks

Application-level locks don't survive server restarts and don't work across multiple servers. Use `SELECT ... FOR UPDATE`:

```python
def transfer(from_id: str, to_id: str, amount: float) -> bool:
    """Database-level locking — works across servers."""
    ordered_ids = sorted([from_id, to_id])

    with db.begin():  # Transaction
        # Lock rows in consistent order
        accounts = {
            aid: db.execute(
                "SELECT * FROM accounts WHERE id = ? FOR UPDATE",
                (aid,)
            ).fetchone()
            for aid in ordered_ids
        }

        if accounts[from_id].balance < amount:
            return False

        db.execute("UPDATE accounts SET balance = balance - ? WHERE id = ?",
                   (amount, from_id))
        db.execute("UPDATE accounts SET balance = balance + ? WHERE id = ?",
                   (amount, to_id))
        return True
    # Transaction commits or rolls back atomically
```'''
    ),
    (
        "thinking/concurrency-async-patterns",
        "I'm confused about when to use threading vs asyncio vs multiprocessing in Python. I have three tasks:\n1. A web scraper that fetches 1000 URLs\n2. A data pipeline that transforms 10GB of CSV data\n3. A web server handling 500 concurrent connections\n\nWhich concurrency model for each?",
        r'''<think>
This is a fundamental Python concurrency question. Let me reason through each task based on what's actually happening at the hardware level.

**The GIL constraint:**
Python's Global Interpreter Lock means only ONE thread can execute Python bytecode at a time. Threads give concurrency (interleaving) but NOT parallelism (simultaneous execution). However, the GIL is RELEASED during I/O operations (network, disk, sleep). So:
- I/O-bound work: threads are fine (GIL released during wait)
- CPU-bound work: threads are useless (GIL blocks parallelism)
- CPU-bound work needs multiprocessing (separate processes, separate GILs)

**Task 1: Web scraper (1000 URLs)**

This is I/O-bound. Each request is ~200ms of waiting for the network. CPU time per request is tiny (parsing response headers, maybe HTML parsing).

Options:
- `threading` with ThreadPoolExecutor: works, simple. 50 threads can process 50 URLs concurrently. Memory overhead: ~8MB per thread (stack).
- `asyncio` with aiohttp: works, more efficient. One thread, thousands of concurrent connections via event loop. Memory overhead: ~few KB per coroutine.
- `multiprocessing`: overkill. You don't need CPU parallelism for network I/O.

Best: **asyncio** — 1000 concurrent connections in one thread, minimal memory.
Alternative: **threading** (ThreadPoolExecutor) — simpler code, fine for 50-100 concurrent requests.

For 1000 URLs, asyncio wins because threads at 1000 would use 8GB of stack space. With asyncio, 1000 coroutines use maybe 10MB total.

**Task 2: CSV data pipeline (10GB)**

This is CPU-bound. Transforming data means parsing, computing, serializing. Python bytecode execution all the way. The GIL blocks threading from helping.

Options:
- `threading`: useless for CPU-bound work (GIL)
- `asyncio`: useless for CPU-bound work (single thread)
- `multiprocessing` with ProcessPoolExecutor: works! Each process has its own GIL. 8 cores = 8x speedup.
- Pandas/NumPy (C extensions): release the GIL internally. Pandas operations on large arrays are already multi-threaded at the C level. `df.groupby().sum()` doesn't need multiprocessing.
- `concurrent.futures.ProcessPoolExecutor`: simple API for splitting work across processes.

Best: **multiprocessing** (chunk the CSV, process chunks in parallel).
But: if using Pandas/NumPy, the C extensions already release the GIL — multithreading CAN help because the GIL isn't held during NumPy operations. Benchmark before adding complexity.

Also: 10GB CSV → consider streaming/chunked processing to avoid loading into memory. `pd.read_csv(chunksize=100_000)` + multiprocessing.

**Task 3: Web server (500 concurrent connections)**

This is I/O-bound. Each connection is mostly waiting — waiting for the request, waiting for the DB, waiting for the response to send.

Options:
- `threading`: 500 threads × 8MB stack = 4GB. Feasible but wasteful.
- `asyncio`: 500 coroutines × few KB = tiny. Event loop handles all connections in one thread.
- `multiprocessing`: each process handles some connections. Uvicorn does this with `--workers 4`.

Best: **asyncio** — this is literally what asyncio was designed for. FastAPI/Starlette, aiohttp, Sanic all use this model.

For maximum throughput: asyncio + multiprocessing. Run 4 worker processes (one per core), each running an asyncio event loop handling 125+ connections. This is what `uvicorn --workers 4` does.

**Summary matrix:**
| Task | Bottleneck | Best model | Why |
|------|-----------|-----------|-----|
| 1000 URLs | Network I/O | asyncio | Minimal memory, max concurrency |
| 10GB CSV | CPU | multiprocessing | Bypass GIL for true parallelism |
| 500 connections | Network I/O | asyncio | Efficient connection handling |
</think>

### The decision framework

```
Is the bottleneck I/O (network, disk)?
  YES → asyncio (or threading for simpler code)
  NO → Is it CPU (computation, parsing)?
    YES → multiprocessing (bypass the GIL)
    NO → You don't need concurrency
```

### Your three tasks

| Task | Bottleneck | Model | Reasoning |
|------|-----------|-------|-----------|
| 1000 URLs | Network I/O | **asyncio** | 1000 coroutines = ~10MB. 1000 threads = ~8GB. |
| 10GB CSV transform | CPU | **multiprocessing** | GIL blocks threads from parallel CPU work |
| 500 connections | Network I/O | **asyncio** | This is exactly what async web frameworks do |

### Task 1: Web scraper with asyncio

```python
import asyncio
import aiohttp

async def fetch(session: aiohttp.ClientSession, url: str) -> str:
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        return await resp.text()

async def scrape_all(urls: list[str], max_concurrent: int = 50) -> list[str]:
    semaphore = asyncio.Semaphore(max_concurrent)  # Don't open 1000 connections at once

    async def fetch_limited(session, url):
        async with semaphore:
            return await fetch(session, url)

    async with aiohttp.ClientSession() as session:
        tasks = [fetch_limited(session, url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)

# 1000 URLs in ~20 seconds (50 concurrent × 200ms avg response)
results = asyncio.run(scrape_all(urls))
```

### Task 2: CSV pipeline with multiprocessing

```python
from concurrent.futures import ProcessPoolExecutor
import pandas as pd

def process_chunk(chunk_path: str) -> pd.DataFrame:
    """Runs in a separate process — has its own GIL."""
    df = pd.read_csv(chunk_path)
    # CPU-heavy transformations
    df['computed'] = df['value'].apply(complex_calculation)
    df = df.groupby('category').agg({'computed': 'sum'}).reset_index()
    return df

def process_pipeline(input_path: str, n_workers: int = 8):
    # Split into chunks (or use chunksize)
    chunks = split_csv(input_path, n_chunks=n_workers)

    with ProcessPoolExecutor(max_workers=n_workers) as pool:
        results = list(pool.map(process_chunk, chunks))

    # Merge results
    combined = pd.concat(results).groupby('category').sum().reset_index()
    combined.to_parquet('output.parquet')
```

### Task 3: Web server with asyncio

```python
# This is what FastAPI/uvicorn already does:
# uvicorn app:app --workers 4

# Each worker = 1 process with 1 asyncio event loop
# 4 workers × 125 connections each = 500 concurrent
# Memory: ~200MB total (vs 4GB with threading)

from fastapi import FastAPI
app = FastAPI()

@app.get('/data/{id}')
async def get_data(id: int):
    # async DB call — event loop handles other requests while waiting
    result = await db.fetch_one("SELECT * FROM data WHERE id = $1", id)
    return result
```

### Why the GIL makes threading useless for CPU work

```python
import threading, time

def cpu_work():
    total = 0
    for i in range(50_000_000):
        total += i

# Single thread: 4.2 seconds
# Two threads: 4.5 seconds (SLOWER due to GIL contention)
# Two processes: 2.1 seconds (true parallelism)
```

Threads fight over the GIL every 5ms (Python's switch interval). The overhead of acquiring/releasing the GIL makes threaded CPU work *slower* than single-threaded.

### Quick reference

```
asyncio:          One thread, thousands of I/O tasks
                  Best for: network clients, web servers, DB queries
                  Bad for: CPU computation (blocks the event loop)

threading:        Multiple threads, one GIL
                  Best for: simple I/O parallelism (<100 tasks)
                  Bad for: CPU computation (GIL blocks parallelism)

multiprocessing:  Multiple processes, multiple GILs
                  Best for: CPU-heavy work (data processing, ML)
                  Bad for: shared state (must serialize between processes)

Combo:            multiprocessing + asyncio
                  Best for: max throughput (uvicorn --workers 4)
                  Each process runs its own async event loop
```'''
    ),
    (
        "thinking/concurrency-producer-consumer",
        "I need to build a pipeline that reads messages from an API, processes them, and writes results to a database. The API returns messages in batches of 100, processing takes ~50ms per message, and DB writes should be batched. How should I structure this?",
        r'''<think>
This is a classic producer-consumer pipeline. Let me think about the stages and their characteristics:

**Stage 1: API reader (I/O-bound)**
- Fetches batches of 100 messages
- Latency: probably 200-500ms per API call
- This is network I/O → asyncio or threading

**Stage 2: Processor (CPU-bound)**
- 50ms per message
- 100 messages per batch = 5 seconds per batch
- This is CPU work → multiprocessing would help, but 50ms suggests it's not trivially parallelizable

Actually, 50ms per message is borderline. If it's pure Python computation, multiprocessing helps. If it's a library call (parsing, regex, etc.), threading might work because C extensions release the GIL.

For now, assume CPU-bound (pure Python processing).

**Stage 3: DB writer (I/O-bound)**
- Batched writes
- Latency: 10-50ms per batch insert
- Network I/O → asyncio or threading

**Pipeline design options:**

**Option A: Sequential**
```
fetch 100 → process 100 → write 100 → fetch 100 → ...
```
Total per batch: 300ms (fetch) + 5000ms (process) + 30ms (write) = 5.33s
Throughput: 100/5.33s ≈ 19 messages/second

**Option B: Overlapping with queues**
```
Fetcher → [Queue] → Processor → [Queue] → Writer
```
All three stages run concurrently. The fetcher fills the queue while the processor works on the previous batch. The writer batches and writes while the processor works on the next batch.

Throughput limited by the slowest stage: processor at 5s per 100 = 20 msg/s.

**Option C: Parallel processors**
```
Fetcher → [Queue] → Processor 1 ─→ [Queue] → Writer
                  → Processor 2 ─↗
                  → Processor 3 ─↗
                  → Processor 4 ─↗
```
4 processors: 100 messages / 4 = 25 messages each. Processing: 25 × 50ms = 1.25s.
Now the fetcher (300ms) is faster than the processors (1.25s), so we're not fetch-bottlenecked.
Throughput: 100/1.25s ≈ 80 msg/s. 4x improvement.

With 8 processors: 100/0.625s ≈ 160 msg/s.

**Option D: Asyncio pipeline with thread pool for CPU work**
```
async fetcher → asyncio.Queue → thread pool (CPU processing) → asyncio.Queue → async DB writer
```

This uses asyncio for the I/O stages and offloads CPU work to a thread pool. If the processing is truly CPU-bound, this won't help (GIL). But if processing involves any I/O or C extensions, it could.

**My recommendation: Option C with asyncio.Queue**

Use `asyncio` for the pipeline coordination and I/O stages. Use `concurrent.futures.ProcessPoolExecutor` for the CPU-bound processing stage.

Actually, mixing asyncio and multiprocessing is fiddly. Let me think about a simpler approach.

**Simple approach: `queue.Queue` + threads/processes**

```python
import queue
import threading
from concurrent.futures import ProcessPoolExecutor

fetch_queue = queue.Queue(maxsize=5)   # Buffer 5 batches
write_queue = queue.Queue(maxsize=10)  # Buffer 10 batches of results

def fetcher():
    while True:
        batch = api.fetch_batch(limit=100)
        if not batch:
            fetch_queue.put(None)  # Sentinel
            break
        fetch_queue.put(batch)

def processor():
    while True:
        batch = fetch_queue.get()
        if batch is None:
            fetch_queue.put(None)  # Pass sentinel to other processors
            write_queue.put(None)
            break
        results = [process_message(msg) for msg in batch]
        write_queue.put(results)

def writer():
    batch = []
    while True:
        results = write_queue.get()
        if results is None:
            if batch:
                db.batch_insert(batch)
            break
        batch.extend(results)
        if len(batch) >= 500:
            db.batch_insert(batch)
            batch = []
```

This is clean but processors share the GIL. For true parallelism, I need to use ProcessPoolExecutor for the processing stage.

Let me design the asyncio version — it's cleaner for the I/O stages and integrates well with `run_in_executor` for CPU offloading.
</think>

### Producer-consumer pipeline with backpressure

```
┌─────────┐    Queue     ┌────────────┐    Queue    ┌────────┐
│ Fetcher │───(max 5)──→│ Processors │───(max 10)─→│ Writer │
│ (async) │              │ (4 workers)│             │(async) │
└─────────┘              └────────────┘             └────────┘
   300ms/batch            1.25s/batch (4×)          20ms/batch
```

### Implementation

```python
import asyncio
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass

@dataclass
class PipelineConfig:
    fetch_batch_size: int = 100
    write_batch_size: int = 500
    max_fetch_buffer: int = 5      # Backpressure: pause fetching if 5 batches queued
    max_write_buffer: int = 10
    num_processors: int = 4

# CPU-bound work — must be a top-level function for multiprocessing
def process_message(message: dict) -> dict:
    """Runs in a separate process."""
    # Your 50ms-per-message processing logic
    result = heavy_computation(message)
    return result

def process_batch(messages: list[dict]) -> list[dict]:
    """Process a batch of messages (runs in subprocess)."""
    return [process_message(msg) for msg in messages]


class Pipeline:
    def __init__(self, api_client, db_client, config: PipelineConfig = None):
        self.api = api_client
        self.db = db_client
        self.config = config or PipelineConfig()
        self._fetch_queue: asyncio.Queue = None
        self._write_queue: asyncio.Queue = None
        self._executor: ProcessPoolExecutor = None
        self._stats = {'fetched': 0, 'processed': 0, 'written': 0}

    async def run(self):
        """Run the full pipeline until API is exhausted."""
        self._fetch_queue = asyncio.Queue(maxsize=self.config.max_fetch_buffer)
        self._write_queue = asyncio.Queue(maxsize=self.config.max_write_buffer)
        self._executor = ProcessPoolExecutor(max_workers=self.config.num_processors)

        try:
            # All three stages run concurrently
            await asyncio.gather(
                self._fetcher(),
                self._processor(),
                self._writer(),
            )
        finally:
            self._executor.shutdown(wait=True)

        print(f"Pipeline complete: {self._stats}")

    async def _fetcher(self):
        """Stage 1: Fetch batches from API (I/O-bound, async)."""
        while True:
            batch = await self.api.fetch_batch(limit=self.config.fetch_batch_size)
            if not batch:
                await self._fetch_queue.put(None)  # Signal: no more data
                break
            await self._fetch_queue.put(batch)  # Blocks if queue full (backpressure)
            self._stats['fetched'] += len(batch)

    async def _processor(self):
        """Stage 2: Process messages (CPU-bound, offloaded to process pool)."""
        loop = asyncio.get_event_loop()

        while True:
            batch = await self._fetch_queue.get()
            if batch is None:
                await self._write_queue.put(None)  # Pass the signal
                break

            # Offload CPU work to process pool (bypasses GIL)
            results = await loop.run_in_executor(self._executor, process_batch, batch)

            await self._write_queue.put(results)
            self._stats['processed'] += len(results)

    async def _writer(self):
        """Stage 3: Batch-write results to DB (I/O-bound, async)."""
        buffer = []

        while True:
            results = await self._write_queue.get()
            if results is None:
                # Flush remaining
                if buffer:
                    await self.db.batch_insert(buffer)
                    self._stats['written'] += len(buffer)
                break

            buffer.extend(results)

            # Write when buffer is large enough
            if len(buffer) >= self.config.write_batch_size:
                await self.db.batch_insert(buffer)
                self._stats['written'] += len(buffer)
                buffer = []


# Usage
async def main():
    pipeline = Pipeline(
        api_client=ApiClient('https://api.example.com'),
        db_client=AsyncDBClient('postgresql://localhost/mydb'),
        config=PipelineConfig(num_processors=4),
    )
    await pipeline.run()

asyncio.run(main())
```

### Throughput analysis

```
Sequential:           100 msgs / 5.33s = 19 msg/s
Pipeline (1 proc):    100 msgs / 5.0s  = 20 msg/s  (bottleneck: processor)
Pipeline (4 procs):   100 msgs / 1.25s = 80 msg/s  (bottleneck: processor)
Pipeline (8 procs):   100 msgs / 0.63s = 160 msg/s (bottleneck: fetcher at 300ms)
```

### Backpressure explained

Without `maxsize` on queues, a fast fetcher fills memory before the slow processor catches up:

```
Fetcher: 100 msgs every 300ms → 333 msg/s into queue
Processor: 100 msgs every 5s → 20 msg/s out of queue
After 1 minute: 18,800 messages buffered in memory
```

With `maxsize=5`: the fetcher blocks after 5 batches (500 messages). Memory is bounded. The fast producer slows to match the slow consumer.

### Error handling addition

```python
async def _processor(self):
    loop = asyncio.get_event_loop()
    while True:
        batch = await self._fetch_queue.get()
        if batch is None:
            await self._write_queue.put(None)
            break

        try:
            results = await loop.run_in_executor(self._executor, process_batch, batch)
            await self._write_queue.put(results)
        except Exception as e:
            # Option 1: Dead-letter queue (don't lose messages)
            logger.error(f"Processing failed: {e}")
            await self._dead_letter_queue.put((batch, str(e)))
            # Option 2: Retry with backoff
            # Option 3: Skip and continue (for non-critical data)
```'''
    ),
]
