"""Phase 1G: Foundation Thinking — Concurrency & Distributed Systems (Part 8)

Async/await patterns: fan-out/fan-in, pipeline stages, semaphore-based concurrency
limiting, and structured concurrency with task groups.
"""

PAIRS = [
    (
        "thinking/concurrency-async-fan-out",
        r'''We need to fetch data from 5 different APIs and combine the results. Currently
we call them sequentially, taking ~10 seconds total:

```python
async def get_dashboard_data(user_id: str):
    profile = await fetch_profile(user_id)          # 2s
    orders = await fetch_orders(user_id)             # 3s
    recommendations = await fetch_recommendations(user_id)  # 2s
    notifications = await fetch_notifications(user_id)      # 1.5s
    analytics = await fetch_analytics(user_id)       # 1.5s

    return {
        "profile": profile,
        "orders": orders,
        "recommendations": recommendations,
        "notifications": notifications,
        "analytics": analytics,
    }
```

How do we parallelize this properly, handling partial failures gracefully?''',
        r'''<think>
These 5 calls are independent — they can all run concurrently. Using asyncio.gather()
would bring total time from ~10s down to ~3s (the slowest call).

But we need to handle failures gracefully. Options:
1. `asyncio.gather(return_exceptions=True)` — returns exceptions as values instead of raising
2. `asyncio.TaskGroup` (Python 3.11+) — structured concurrency, cancels all on first error
3. Manual tasks with individual try/except — most flexible

For a dashboard, partial data is better than no data. If recommendations fail, we still
want to show profile and orders. So `return_exceptions=True` is the right approach.

We should also add timeouts per call so one slow service doesn't block the entire dashboard.
</think>

## Fan-Out with Partial Failure Handling

```python
import asyncio
from typing import Any

async def get_dashboard_data(user_id: str):
    # Fan-out: all 5 calls run concurrently
    results = await asyncio.gather(
        fetch_with_timeout(fetch_profile(user_id), timeout=5.0),
        fetch_with_timeout(fetch_orders(user_id), timeout=5.0),
        fetch_with_timeout(fetch_recommendations(user_id), timeout=3.0),
        fetch_with_timeout(fetch_notifications(user_id), timeout=3.0),
        fetch_with_timeout(fetch_analytics(user_id), timeout=3.0),
        return_exceptions=True,  # don't fail on first error
    )

    # Fan-in: combine results, substituting defaults for failures
    keys = ["profile", "orders", "recommendations", "notifications", "analytics"]
    defaults = [{}, [], [], [], {}]

    dashboard = {}
    errors = []
    for key, result, default in zip(keys, results, defaults):
        if isinstance(result, Exception):
            errors.append(f"{key}: {result}")
            dashboard[key] = default  # graceful degradation
        else:
            dashboard[key] = result

    dashboard["_errors"] = errors
    dashboard["_partial"] = len(errors) > 0
    return dashboard

async def fetch_with_timeout(coro, timeout: float):
    """Wrap a coroutine with a timeout."""
    return await asyncio.wait_for(coro, timeout=timeout)
```

### Python 3.11+ with TaskGroup (fail-fast variant)

```python
async def get_dashboard_data_strict(user_id: str):
    """Fail-fast: if ANY call fails, cancel all others."""
    async with asyncio.TaskGroup() as tg:
        t_profile = tg.create_task(fetch_profile(user_id))
        t_orders = tg.create_task(fetch_orders(user_id))
        t_recs = tg.create_task(fetch_recommendations(user_id))
        t_notifs = tg.create_task(fetch_notifications(user_id))
        t_analytics = tg.create_task(fetch_analytics(user_id))

    # All tasks completed successfully (or ExceptionGroup raised)
    return {
        "profile": t_profile.result(),
        "orders": t_orders.result(),
        "recommendations": t_recs.result(),
        "notifications": t_notifs.result(),
        "analytics": t_analytics.result(),
    }
```

**When to use which:**
- `gather(return_exceptions=True)` — partial results OK (dashboards, search)
- `TaskGroup` — all-or-nothing (transactions, batch processing)
- Total time: ~3s (slowest call) instead of ~10s (sum of all calls)'''
    ),
    (
        "thinking/concurrency-async-pipeline",
        r'''We have an async data processing pipeline: read CSV rows, validate each row,
enrich with API call, then write to database. Currently it processes one row at a
time end-to-end:

```python
async def process_csv(filepath):
    results = []
    async with aiofiles.open(filepath) as f:
        async for line in f:
            row = parse_csv_line(line)
            validated = await validate(row)
            enriched = await enrich_from_api(validated)  # HTTP call, ~200ms
            await write_to_db(enriched)                  # ~50ms
            results.append(enriched)
    return results
```

With 10,000 rows, this takes ~2500 seconds. How do we pipeline the stages?''',
        r'''<think>
Current approach: each row goes through all 4 stages sequentially. Total per row ~250ms,
so 10,000 rows = 2,500 seconds.

A pipeline approach would overlap stages:
- While row N is being enriched, row N+1 is being validated
- While row N is being written to DB, row N+1 is being enriched, row N+2 is being validated

But the real win is concurrent fan-out within each stage. The enrich step is I/O-bound
(HTTP call), so we can have many in-flight at once with a semaphore to limit concurrency.

Architecture:
1. Producer stage: read + parse CSV (fast, CPU-light)
2. Validate stage: validate rows (fast)
3. Enrich stage: API calls with concurrency limit (bottleneck, parallelize)
4. Write stage: batch DB writes (parallelize with batching)

Use asyncio.Queue between stages to decouple throughput.
With 50 concurrent enrichment calls: 10,000 * 200ms / 50 = 40 seconds.
With batched DB writes (100 per batch): 100 * 50ms = 5 seconds.
Total: ~45 seconds vs 2,500 seconds.
</think>

## Async Pipeline with Concurrent Stages

```python
import asyncio
import aiofiles

CONCURRENCY_ENRICH = 50   # max concurrent API calls
BATCH_SIZE_DB = 100        # rows per DB batch insert
QUEUE_SIZE = 200           # backpressure between stages

async def process_csv_pipeline(filepath):
    q_parsed = asyncio.Queue(maxsize=QUEUE_SIZE)
    q_validated = asyncio.Queue(maxsize=QUEUE_SIZE)
    q_enriched = asyncio.Queue(maxsize=QUEUE_SIZE)

    async def stage_read():
        """Stage 1: Read and parse CSV lines."""
        async with aiofiles.open(filepath) as f:
            async for line in f:
                row = parse_csv_line(line)
                await q_parsed.put(row)
        await q_parsed.put(None)  # sentinel

    async def stage_validate():
        """Stage 2: Validate rows (fast, single worker)."""
        while True:
            row = await q_parsed.get()
            if row is None:
                await q_validated.put(None)
                break
            validated = await validate(row)
            if validated:
                await q_validated.put(validated)

    async def stage_enrich():
        """Stage 3: Enrich via API with concurrency limit."""
        sem = asyncio.Semaphore(CONCURRENCY_ENRICH)
        tasks = set()

        async def enrich_one(row):
            async with sem:
                enriched = await enrich_from_api(row)
                await q_enriched.put(enriched)

        while True:
            row = await q_validated.get()
            if row is None:
                # Wait for all in-flight enrichments to complete
                if tasks:
                    await asyncio.gather(*tasks)
                await q_enriched.put(None)
                break
            task = asyncio.create_task(enrich_one(row))
            tasks.add(task)
            task.add_done_callback(tasks.discard)

    async def stage_write():
        """Stage 4: Batch write to database."""
        batch = []
        results = []
        while True:
            item = await q_enriched.get()
            if item is None:
                if batch:
                    await write_batch_to_db(batch)
                    results.extend(batch)
                break
            batch.append(item)
            if len(batch) >= BATCH_SIZE_DB:
                await write_batch_to_db(batch)
                results.extend(batch)
                batch = []
        return results

    # Run all stages concurrently as a pipeline
    _, _, _, results = await asyncio.gather(
        stage_read(),
        stage_validate(),
        stage_enrich(),
        stage_write(),
    )
    return results

async def write_batch_to_db(rows):
    """Insert multiple rows in one query."""
    values = [(r["id"], r["name"], r["data"]) for r in rows]
    await db.executemany(
        "INSERT INTO enriched_data (id, name, data) VALUES ($1, $2, $3)",
        values,
    )
```

**Performance breakdown (10,000 rows):**

| Approach | Enrich time | DB time | Total |
|----------|------------|---------|-------|
| Sequential | 10K * 200ms = 2000s | 10K * 50ms = 500s | ~2500s |
| Pipeline (50 concurrent) | 10K * 200ms / 50 = 40s | 100 batches * 50ms = 5s | ~45s |
| Speedup | **50x** | **100x** | **~55x** |

**Key design points:**
- Queues between stages decouple throughput and provide backpressure
- Semaphore limits API concurrency (don't overwhelm external service)
- Batched DB writes reduce round trips from 10,000 to 100
- Each stage can be independently scaled'''
    ),
    (
        "thinking/concurrency-async-semaphore",
        r'''We're scraping 10,000 URLs concurrently, but the target server rate-limits us
and our system runs out of file descriptors:

```python
import asyncio
import aiohttp

async def scrape_all(urls):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch(session, url) for url in urls]  # 10,000 tasks!
        return await asyncio.gather(*tasks)

async def fetch(session, url):
    async with session.get(url) as resp:
        return await resp.text()

urls = load_urls()  # 10,000 URLs
results = asyncio.run(scrape_all(urls))
```

This creates 10,000 simultaneous connections. How do we limit concurrency properly?''',
        r'''<think>
Problems with launching 10,000 concurrent requests:
1. File descriptor limit (typically 1024 on Linux by default)
2. Memory: 10,000 open connections and response buffers
3. Server rate-limiting: too many connections gets us blocked
4. DNS resolution bottleneck
5. All tasks are created immediately, even before any complete

Solutions:
1. `asyncio.Semaphore` — limit concurrent tasks
2. `aiohttp.TCPConnector(limit=N)` — limit at the connection pool level
3. Process URLs in batches — but less efficient than semaphore
4. `asyncio.Queue` with worker pool — producer-consumer

Semaphore is the cleanest. Also should use TCPConnector limit as defense-in-depth.
For rate limiting, add a delay or use a token bucket.
</think>

## Fix: Semaphore + Connection Pool Limits

```python
import asyncio
import aiohttp
from typing import Optional

MAX_CONCURRENT = 50      # max simultaneous requests
RATE_LIMIT_DELAY = 0.1   # seconds between requests (10 req/s)

async def scrape_all(urls: list[str]) -> list[Optional[str]]:
    sem = asyncio.Semaphore(MAX_CONCURRENT)
    connector = aiohttp.TCPConnector(
        limit=MAX_CONCURRENT,       # connection pool limit
        limit_per_host=10,          # per-host limit (be polite)
        ttl_dns_cache=300,          # cache DNS lookups
    )

    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [
            bounded_fetch(sem, session, url)
            for url in urls
        ]
        return await asyncio.gather(*tasks)

async def bounded_fetch(
    sem: asyncio.Semaphore,
    session: aiohttp.ClientSession,
    url: str,
) -> Optional[str]:
    async with sem:  # blocks when MAX_CONCURRENT tasks are running
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status == 429:  # rate limited
                    retry_after = int(resp.headers.get("Retry-After", 5))
                    await asyncio.sleep(retry_after)
                    # Retry once
                    async with session.get(url) as retry_resp:
                        return await retry_resp.text()
                return await resp.text()
        except Exception as e:
            print(f"Failed {url}: {e}")
            return None
```

### Alternative: Worker Pool with Queue (more control)

```python
async def scrape_with_workers(urls: list[str], num_workers: int = 50):
    queue = asyncio.Queue()
    results = {}

    for url in urls:
        await queue.put(url)

    async def worker(worker_id: int):
        while True:
            try:
                url = queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            async with aiohttp.ClientSession() as session:
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                        results[url] = await resp.text()
                except Exception as e:
                    results[url] = None
                finally:
                    queue.task_done()
            await asyncio.sleep(RATE_LIMIT_DELAY)  # rate limiting

    workers = [
        asyncio.create_task(worker(i))
        for i in range(num_workers)
    ]
    await asyncio.gather(*workers)
    return results
```

**Comparison:**

| Approach | Connections | Memory | Rate Control | Code Complexity |
|----------|-----------|--------|-------------|----------------|
| Bare gather | 10,000 | Very high | None | Low |
| Semaphore | 50 | Low | Basic | Low |
| Worker pool | 50 | Low | Per-worker delay | Medium |
| Queue + workers | 50 | Bounded | Fine-grained | Medium |

The semaphore approach is the simplest correct solution for most scraping tasks.'''
    ),
    (
        "thinking/concurrency-structured-concurrency",
        r'''Our async code has fire-and-forget tasks that sometimes cause errors after the
parent function has returned:

```python
async def handle_request(request):
    data = await parse_request(request)

    # Fire and forget — no await, no tracking
    asyncio.create_task(send_analytics(data))
    asyncio.create_task(update_cache(data))
    asyncio.create_task(notify_subscribers(data))

    result = await process(data)
    return result
    # Function returns, but background tasks are still running
    # If they fail, the exception is silently swallowed
    # If the event loop shuts down, they get cancelled mid-execution
```

How do we properly manage these background tasks?''',
        r'''<think>
Problems with fire-and-forget tasks:
1. Unhandled exceptions are silently swallowed (Python 3.12 warns about this)
2. Tasks may outlive their logical scope
3. No way to know when all tasks for a request are done
4. Cancelled on event loop shutdown without cleanup
5. Hard to test — no way to wait for completion

Structured concurrency principle: every task has a clear owner and lifetime.
A task should not outlive the scope that created it.

Solutions:
1. **Python 3.11+ TaskGroup** — tasks are bound to a scope, all must complete
2. **Background task set** — track tasks explicitly, handle errors
3. **Request-scoped task group** — tie background work to request lifecycle

For the "fire and forget but still handle errors" case, we need to separate:
- Tasks that MUST complete before returning (use TaskGroup)
- Tasks that are truly best-effort (use a managed background set with error logging)
</think>

## Structured Concurrency with TaskGroup (Python 3.11+)

### Option 1: All tasks must complete before returning

```python
async def handle_request(request):
    data = await parse_request(request)

    async with asyncio.TaskGroup() as tg:
        # Background tasks — all bound to this scope
        tg.create_task(send_analytics(data))
        tg.create_task(update_cache(data))
        tg.create_task(notify_subscribers(data))

        # Main processing runs concurrently with background tasks
        result_task = tg.create_task(process(data))

    # ALL tasks have completed (or ExceptionGroup is raised)
    return result_task.result()
```

### Option 2: Best-effort background tasks with error handling

```python
class BackgroundTasks:
    """Managed set of background tasks with error handling."""

    def __init__(self):
        self._tasks: set[asyncio.Task] = set()

    def add(self, coro, name: str = None):
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._on_done)
        return task

    def _on_done(self, task: asyncio.Task):
        self._tasks.discard(task)
        if task.cancelled():
            return
        exc = task.exception()
        if exc:
            logger.error(
                f"Background task {task.get_name()} failed: {exc}",
                exc_info=exc,
            )

    async def wait_all(self, timeout: float = None):
        """Wait for all pending tasks (e.g., during shutdown)."""
        if self._tasks:
            done, pending = await asyncio.wait(
                self._tasks, timeout=timeout
            )
            for task in pending:
                task.cancel()

# Usage in request handler
bg = BackgroundTasks()

async def handle_request(request):
    data = await parse_request(request)

    # Background tasks are tracked and errors logged
    bg.add(send_analytics(data), name="analytics")
    bg.add(update_cache(data), name="cache")
    bg.add(notify_subscribers(data), name="notify")

    result = await process(data)
    return result

# On server shutdown
async def shutdown():
    await bg.wait_all(timeout=10.0)
```

### Option 3: Request-scoped tasks (FastAPI-style)

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def request_scope():
    """Every task created in this scope must finish before exit."""
    tasks = []
    try:
        yield tasks
    finally:
        if tasks:
            results = await asyncio.gather(
                *tasks, return_exceptions=True
            )
            for r in results:
                if isinstance(r, Exception):
                    logger.error(f"Request task failed: {r}")

async def handle_request(request):
    async with request_scope() as tasks:
        data = await parse_request(request)
        tasks.append(asyncio.create_task(send_analytics(data)))
        tasks.append(asyncio.create_task(update_cache(data)))
        result = await process(data)
    # All tasks guaranteed complete here
    return result
```

**Key principle:** Every concurrent task should have a clear owner responsible for its lifetime, errors, and cancellation.'''
    ),
    (
        "thinking/concurrency-async-timeout-patterns",
        r'''Our service makes calls to multiple external APIs, but sometimes one API hangs
forever, causing our entire request to time out:

```python
async def get_enriched_data(item_id: str):
    try:
        # If api_b hangs, this whole function hangs
        data_a = await api_a.fetch(item_id)
        data_b = await api_b.fetch(item_id)  # known to hang sometimes
        data_c = await api_c.fetch(item_id)
        return merge(data_a, data_b, data_c)
    except Exception:
        return None  # catch-all hides the real problem
```

How do we add proper timeout handling for individual calls and the overall operation?''',
        r'''<think>
Problems:
1. No timeouts on individual API calls — one hanging call blocks everything
2. Sequential calls — should be parallel since they're independent
3. Bare `except Exception` catches everything including cancellation — hides bugs
4. Returns None on any error — no visibility into what failed

We need:
1. Per-call timeouts using `asyncio.wait_for()`
2. Overall request timeout as a budget
3. Parallel execution since calls are independent
4. Specific exception handling with fallbacks
</think>

## Layered Timeout Pattern

```python
import asyncio
from dataclasses import dataclass
from typing import Any, Optional

@dataclass
class FetchResult:
    source: str
    data: Any = None
    error: str = None
    timed_out: bool = False

async def fetch_with_timeout(
    name: str,
    coro,
    timeout: float,
    default=None,
) -> FetchResult:
    """Fetch with per-call timeout and error capture."""
    try:
        data = await asyncio.wait_for(coro, timeout=timeout)
        return FetchResult(source=name, data=data)
    except asyncio.TimeoutError:
        return FetchResult(
            source=name, data=default,
            error=f"Timed out after {timeout}s", timed_out=True,
        )
    except asyncio.CancelledError:
        raise  # NEVER catch CancelledError
    except Exception as e:
        return FetchResult(
            source=name, data=default,
            error=f"{type(e).__name__}: {e}",
        )

async def get_enriched_data(item_id: str):
    # Overall budget for the entire operation
    OVERALL_TIMEOUT = 10.0

    try:
        results = await asyncio.wait_for(
            asyncio.gather(
                # Per-call timeouts (shorter than overall)
                fetch_with_timeout(
                    "api_a", api_a.fetch(item_id),
                    timeout=3.0, default={},
                ),
                fetch_with_timeout(
                    "api_b", api_b.fetch(item_id),
                    timeout=5.0, default={},  # api_b is slow, gets more time
                ),
                fetch_with_timeout(
                    "api_c", api_c.fetch(item_id),
                    timeout=3.0, default={},
                ),
            ),
            timeout=OVERALL_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.error("Overall enrichment timeout exceeded")
        return None

    # Log any partial failures
    for r in results:
        if r.error:
            logger.warning(f"{r.source} failed: {r.error}")

    data_a, data_b, data_c = results
    return merge(data_a.data, data_b.data, data_c.data)
```

### Timeout Budget Pattern (remaining time shrinks)

```python
class TimeoutBudget:
    """Track remaining time across sequential operations."""

    def __init__(self, total: float):
        self.deadline = asyncio.get_event_loop().time() + total

    @property
    def remaining(self) -> float:
        return max(0, self.deadline - asyncio.get_event_loop().time())

    @property
    def expired(self) -> bool:
        return self.remaining <= 0

    async def run(self, coro, min_timeout: float = 0.5):
        """Run a coroutine within the remaining budget."""
        timeout = max(min_timeout, self.remaining)
        return await asyncio.wait_for(coro, timeout=timeout)

# Usage for sequential calls that share a time budget
async def sequential_with_budget(item_id: str):
    budget = TimeoutBudget(total=10.0)

    data_a = await budget.run(api_a.fetch(item_id))  # uses up to 10s
    data_b = await budget.run(api_b.fetch(item_id))  # uses remaining time
    data_c = await budget.run(api_c.fetch(item_id))  # uses remaining time

    return merge(data_a, data_b, data_c)
```

**Rules of async timeout handling:**
1. Always set per-call timeouts — never trust external services
2. Set an overall budget shorter than your own SLA
3. Never catch `CancelledError` (it's how timeouts and shutdown work)
4. Log timeouts with context — they indicate infrastructure issues
5. Provide defaults for non-critical data sources'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
