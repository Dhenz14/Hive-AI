"""Async/concurrency training pairs: real-world concurrency problems (all thinking)."""

pairs = [
    {
        "instruction": r'''I need to build an async API crawler that respects rate limits (max 10 requests/second) and handles retries with exponential backoff. How should I design this?''',
        "output": r'''<think>
A rate-limited async crawler needs several components:

1. Rate limiting -- need to control requests per second. Options:
   - Token bucket (smooth, allows bursts)
   - Sliding window (strict per-second limit)
   - Semaphore with delay (simple but not precise)

I think a token bucket is the best approach. It adds tokens at a fixed rate, and each request consumes one token. If no tokens are available, the request waits.

2. Retry with exponential backoff -- when a request fails with 429 or 5xx, wait and retry. The backoff should be: base_delay * 2^attempt + jitter.

3. Concurrency limit -- even with rate limiting, we should cap concurrent requests to avoid overwhelming the target or running out of file descriptors. Use a semaphore.

4. Result collection -- need to track successes and failures.

Actually, let me reconsider the architecture. The cleanest approach is:
- AsyncRateLimiter class using token bucket
- AsyncRetrier wrapper for individual requests
- Main crawler that combines both with a semaphore for max concurrency

I should also handle specific HTTP status codes differently: 429 (rate limited) should respect Retry-After header, 5xx should retry with backoff, 4xx should not retry.
</think>

Here is a production-quality rate-limited async crawler:

```python
import asyncio
import time
import random
import logging
from typing import Any, Optional
from dataclasses import dataclass, field
import httpx

logger = logging.getLogger(__name__)

# ============================================================
# Token bucket rate limiter
# ============================================================

class AsyncRateLimiter:
    """Token bucket rate limiter for async code."""

    def __init__(self, rate: float, burst: int = 1):
        self.rate = rate  # tokens per second
        self.burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self):
        """Wait until a token is available."""
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self._last_refill
                self._tokens = min(
                    self.burst,
                    self._tokens + elapsed * self.rate,
                )
                self._last_refill = now

                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return

            # No token available -- wait a bit
            await asyncio.sleep(1.0 / self.rate)

# ============================================================
# Retry logic with exponential backoff
# ============================================================

@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    jitter: float = 0.5
    retryable_statuses: set[int] = field(
        default_factory=lambda: {429, 500, 502, 503, 504}
    )

async def retry_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    config: RetryConfig = RetryConfig(),
    **kwargs,
) -> httpx.Response:
    """Execute HTTP request with retry and backoff."""
    last_error = None

    for attempt in range(config.max_retries + 1):
        try:
            response = await client.request(method, url, **kwargs)

            if response.status_code not in config.retryable_statuses:
                return response

            # Retryable status code
            if attempt == config.max_retries:
                return response  # return last response

            # Check for Retry-After header (429 responses)
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                delay = float(retry_after)
            else:
                delay = min(
                    config.base_delay * (2 ** attempt)
                    + random.uniform(0, config.jitter),
                    config.max_delay,
                )

            logger.warning(
                "Retrying %s (status %d, attempt %d/%d, delay %.1fs)",
                url, response.status_code, attempt + 1,
                config.max_retries, delay,
            )
            await asyncio.sleep(delay)

        except (httpx.ConnectError, httpx.ReadTimeout) as e:
            last_error = e
            if attempt == config.max_retries:
                raise
            delay = min(
                config.base_delay * (2 ** attempt),
                config.max_delay,
            )
            logger.warning(
                "Connection error for %s: %s (retry in %.1fs)",
                url, e, delay,
            )
            await asyncio.sleep(delay)

    raise last_error or RuntimeError("Retry loop ended unexpectedly")

# ============================================================
# Crawler
# ============================================================

@dataclass
class CrawlResult:
    url: str
    status: int
    data: Any = None
    error: Optional[str] = None

class AsyncCrawler:
    """Rate-limited async API crawler with retry."""

    def __init__(
        self,
        rate_limit: float = 10.0,  # requests per second
        max_concurrent: int = 20,
        timeout: float = 30.0,
    ):
        self.rate_limiter = AsyncRateLimiter(
            rate=rate_limit, burst=int(rate_limit)
        )
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.timeout = timeout
        self.retry_config = RetryConfig()
        self._stats = {"success": 0, "failed": 0, "retried": 0}

    async def fetch_one(
        self,
        client: httpx.AsyncClient,
        url: str,
    ) -> CrawlResult:
        """Fetch a single URL with rate limiting and retry."""
        await self.rate_limiter.acquire()

        async with self.semaphore:
            try:
                response = await retry_request(
                    client, "GET", url,
                    config=self.retry_config,
                    timeout=self.timeout,
                )
                if response.status_code == 200:
                    self._stats["success"] += 1
                    return CrawlResult(
                        url=url,
                        status=response.status_code,
                        data=response.json(),
                    )
                else:
                    self._stats["failed"] += 1
                    return CrawlResult(
                        url=url,
                        status=response.status_code,
                        error=f"HTTP {response.status_code}",
                    )
            except Exception as e:
                self._stats["failed"] += 1
                return CrawlResult(
                    url=url, status=0, error=str(e)
                )

    async def crawl(self, urls: list[str]) -> list[CrawlResult]:
        """Crawl multiple URLs with rate limiting."""
        async with httpx.AsyncClient(
            follow_redirects=True,
            limits=httpx.Limits(
                max_connections=50,
                max_keepalive_connections=20,
            ),
        ) as client:
            tasks = [
                asyncio.create_task(self.fetch_one(client, url))
                for url in urls
            ]
            results = await asyncio.gather(*tasks)

        logger.info(
            "Crawl complete: %d success, %d failed",
            self._stats["success"], self._stats["failed"],
        )
        return results

# ============================================================
# Usage
# ============================================================

async def main():
    logging.basicConfig(level=logging.INFO)

    crawler = AsyncCrawler(
        rate_limit=10.0,
        max_concurrent=20,
        timeout=30.0,
    )

    urls = [
        f"https://httpbin.org/get?page={i}"
        for i in range(100)
    ]

    start = time.monotonic()
    results = await crawler.crawl(urls)
    elapsed = time.monotonic() - start

    successes = [r for r in results if r.error is None]
    failures = [r for r in results if r.error is not None]

    print(f"Completed in {elapsed:.1f}s")
    print(f"Success: {len(successes)}, Failed: {len(failures)}")
    if failures:
        for f in failures[:5]:
            print(f"  FAIL: {f.url} -- {f.error}")

# asyncio.run(main())
```

Design decisions:
- Token bucket allows short bursts while maintaining average rate
- Semaphore caps concurrent connections separately from rate limit
- Retry respects `Retry-After` headers from the server
- httpx connection pooling reuses TCP connections'''
    },
    {
        "instruction": r'''I need to process thousands of files in parallel using Python. The processing is CPU-bound (parsing and transforming data). How do I design this for maximum throughput?''',
        "output": r'''<think>
Parallel file processing with CPU-bound work. The key considerations:

1. File discovery is I/O-bound (listing directories), processing is CPU-bound
2. Need ProcessPoolExecutor since threads do not help with CPU-bound work (GIL)
3. Should not load all files into memory at once -- process in batches
4. Need to handle errors per-file without killing the whole batch
5. Progress reporting

The architecture should be:
- Main process: discovers files, submits work to process pool, collects results
- Worker processes: read file, process, return result

But wait -- should I read the file in the worker or in the main process? If I read in the main process and send the content, I have to serialize it across processes (slow for large files). If I read in the worker, each worker does its own I/O which is fine since I/O is fast compared to CPU processing.

For large numbers of files (thousands), I should use imap_unordered for streaming results rather than map() which waits for all results. And I should set chunksize to batch multiple files per IPC round-trip.

The optimal number of workers is os.cpu_count() for CPU-bound work. Going higher adds context-switching overhead.
</think>

```python
import multiprocessing
import os
import time
import json
import logging
from pathlib import Path
from typing import Any, Optional
from dataclasses import dataclass
from concurrent.futures import ProcessPoolExecutor, as_completed

logger = logging.getLogger(__name__)

@dataclass
class FileResult:
    path: str
    success: bool
    output: Any = None
    error: Optional[str] = None
    processing_time: float = 0.0

# ============================================================
# Worker function (runs in separate process)
# ============================================================

def process_single_file(file_path: str) -> FileResult:
    """Process one file -- runs in a worker process."""
    start = time.monotonic()
    try:
        # Read file
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        # CPU-bound processing (simulate with actual work)
        lines = content.split("\n")
        word_count = sum(len(line.split()) for line in lines)
        line_count = len(lines)

        # Simulate heavier processing
        tokens = content.lower().split()
        word_freq = {}
        for token in tokens:
            cleaned = "".join(c for c in token if c.isalnum())
            if cleaned:
                word_freq[cleaned] = word_freq.get(cleaned, 0) + 1

        top_words = sorted(
            word_freq.items(), key=lambda x: x[1], reverse=True
        )[:20]

        result = {
            "lines": line_count,
            "words": word_count,
            "unique_words": len(word_freq),
            "top_words": top_words,
            "size_bytes": len(content.encode("utf-8")),
        }

        elapsed = time.monotonic() - start
        return FileResult(
            path=file_path,
            success=True,
            output=result,
            processing_time=elapsed,
        )

    except Exception as e:
        elapsed = time.monotonic() - start
        return FileResult(
            path=file_path,
            success=False,
            error=str(e),
            processing_time=elapsed,
        )

# ============================================================
# Parallel file processor
# ============================================================

class ParallelFileProcessor:
    def __init__(
        self,
        max_workers: Optional[int] = None,
        chunk_size: int = 10,
    ):
        self.max_workers = max_workers or os.cpu_count()
        self.chunk_size = chunk_size

    def discover_files(
        self,
        directory: str,
        pattern: str = "*.txt",
        recursive: bool = True,
    ) -> list[str]:
        """Find files to process."""
        root = Path(directory)
        if recursive:
            files = list(root.rglob(pattern))
        else:
            files = list(root.glob(pattern))
        return [str(f) for f in files if f.is_file()]

    def process_all(
        self,
        file_paths: list[str],
        callback=None,
    ) -> list[FileResult]:
        """Process all files in parallel with progress reporting."""
        total = len(file_paths)
        results: list[FileResult] = []
        completed = 0
        start = time.monotonic()

        print(
            f"Processing {total} files with "
            f"{self.max_workers} workers..."
        )

        # Method 1: ProcessPoolExecutor with as_completed
        with ProcessPoolExecutor(
            max_workers=self.max_workers
        ) as executor:
            future_to_path = {
                executor.submit(process_single_file, path): path
                for path in file_paths
            }

            for future in as_completed(future_to_path):
                result = future.result()
                results.append(result)
                completed += 1

                if callback:
                    callback(result, completed, total)

                if completed % 100 == 0 or completed == total:
                    elapsed = time.monotonic() - start
                    rate = completed / elapsed if elapsed > 0 else 0
                    print(
                        f"  Progress: {completed}/{total} "
                        f"({rate:.0f} files/sec)"
                    )

        elapsed = time.monotonic() - start
        successes = sum(1 for r in results if r.success)
        failures = sum(1 for r in results if not r.success)

        print(f"\nCompleted in {elapsed:.1f}s")
        print(f"  Success: {successes}, Failed: {failures}")
        print(f"  Throughput: {total / elapsed:.1f} files/sec")

        return results

    def process_with_pool(
        self, file_paths: list[str]
    ) -> list[FileResult]:
        """Alternative: multiprocessing.Pool with imap_unordered."""
        results = []
        total = len(file_paths)

        with multiprocessing.Pool(
            processes=self.max_workers,
            maxtasksperchild=500,  # restart workers to prevent leaks
        ) as pool:
            for i, result in enumerate(
                pool.imap_unordered(
                    process_single_file,
                    file_paths,
                    chunksize=self.chunk_size,
                ),
                1,
            ):
                results.append(result)
                if i % 100 == 0:
                    print(f"  {i}/{total} files processed")

        return results

# ============================================================
# Usage
# ============================================================

def main():
    processor = ParallelFileProcessor(
        max_workers=os.cpu_count(),
        chunk_size=10,
    )

    # Discover files
    files = processor.discover_files(
        "/path/to/data",
        pattern="*.json",
        recursive=True,
    )
    print(f"Found {len(files)} files")

    if not files:
        return

    # Process in parallel
    results = processor.process_all(files)

    # Aggregate results
    total_words = sum(
        r.output["words"] for r in results if r.success
    )
    total_lines = sum(
        r.output["lines"] for r in results if r.success
    )
    avg_time = sum(r.processing_time for r in results) / len(results)

    print(f"\nAggregates:")
    print(f"  Total words: {total_words:,}")
    print(f"  Total lines: {total_lines:,}")
    print(f"  Avg processing time: {avg_time:.4f}s per file")

    # Report failures
    failures = [r for r in results if not r.success]
    if failures:
        print(f"\nFailed files ({len(failures)}):")
        for r in failures[:10]:
            print(f"  {r.path}: {r.error}")

if __name__ == "__main__":
    main()
```

Performance tips:
- Use `os.cpu_count()` workers for CPU-bound work
- Set `chunksize` for `imap_unordered` to reduce IPC overhead
- Use `maxtasksperchild` to prevent memory leaks in long-running jobs
- Read files in workers (not main process) to avoid serialization overhead
- Use `as_completed()` or `imap_unordered()` for progress reporting'''
    },
    {
        "instruction": r'''How do I implement a thread-safe cache with TTL (time-to-live) that handles concurrent updates correctly and avoids thundering herd problems?''',
        "output": r'''<think>
A concurrent cache with TTL needs to handle several tricky scenarios:

1. Basic TTL -- entries expire after a set time
2. Thread safety -- multiple threads reading/writing simultaneously
3. Thundering herd -- when a popular entry expires, many threads simultaneously try to recompute it. Only ONE should compute, others should wait.
4. Memory management -- expired entries should be cleaned up periodically

The thundering herd problem is the most interesting. The solution is to use a "lock per key" approach: when a cache miss occurs, the first thread locks the key and computes the value. Other threads waiting for the same key block on the lock and get the cached result once the first thread finishes.

For async code, I would use asyncio.Lock per key. For threaded code, threading.Lock per key.

I need to be careful about memory leaks from the per-key locks. If I create a lock for every unique key, the lock dict grows unbounded. I should clean up locks that are no longer in use.

Let me implement both a sync (threading) and async version.
</think>

Here is a concurrent cache that handles TTL and thundering herd:

```python
import asyncio
import threading
import time
import logging
from typing import Any, Callable, Optional, TypeVar
from dataclasses import dataclass
from collections import OrderedDict

logger = logging.getLogger(__name__)
T = TypeVar("T")

@dataclass
class CacheEntry:
    value: Any
    expires_at: float
    created_at: float

    @property
    def is_expired(self) -> bool:
        return time.monotonic() > self.expires_at

# ============================================================
# Thread-safe cache with TTL and thundering herd prevention
# ============================================================

class TTLCache:
    """Thread-safe cache with TTL and thundering herd prevention.

    When multiple threads request the same expired key
    simultaneously, only one thread computes the new value.
    Others wait and receive the computed result.
    """

    def __init__(
        self,
        default_ttl: float = 300.0,
        max_size: int = 10000,
        cleanup_interval: float = 60.0,
    ):
        self._default_ttl = default_ttl
        self._max_size = max_size
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        self._global_lock = threading.Lock()
        self._key_locks: dict[str, threading.Lock] = {}
        self._key_lock_refs: dict[str, int] = {}

        # Start background cleanup thread
        self._cleanup_stop = threading.Event()
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            args=(cleanup_interval,),
            daemon=True,
        )
        self._cleanup_thread.start()

    def get(self, key: str) -> Optional[Any]:
        """Get a cached value. Returns None if missing or expired."""
        with self._global_lock:
            entry = self._cache.get(key)
            if entry is None or entry.is_expired:
                return None
            self._cache.move_to_end(key)
            return entry.value

    def set(self, key: str, value: Any, ttl: Optional[float] = None):
        """Set a cache value with TTL."""
        ttl = ttl if ttl is not None else self._default_ttl
        entry = CacheEntry(
            value=value,
            expires_at=time.monotonic() + ttl,
            created_at=time.monotonic(),
        )
        with self._global_lock:
            self._cache[key] = entry
            self._cache.move_to_end(key)
            # Evict oldest if over max size
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], T],
        ttl: Optional[float] = None,
    ) -> T:
        """Get cached value or compute it. Prevents thundering herd.

        Only ONE thread computes for a given key at a time.
        Other threads wait and get the cached result.
        """
        # Fast path: check cache without key lock
        value = self.get(key)
        if value is not None:
            return value

        # Slow path: acquire per-key lock
        key_lock = self._acquire_key_lock(key)
        try:
            # Double-check after acquiring lock
            value = self.get(key)
            if value is not None:
                return value

            # We are the one thread that computes
            logger.debug("Computing value for key: %s", key)
            start = time.monotonic()
            value = compute_fn()
            elapsed = time.monotonic() - start
            logger.debug(
                "Computed %s in %.3fs", key, elapsed
            )

            self.set(key, value, ttl)
            return value
        finally:
            self._release_key_lock(key)

    def _acquire_key_lock(self, key: str) -> threading.Lock:
        with self._global_lock:
            if key not in self._key_locks:
                self._key_locks[key] = threading.Lock()
                self._key_lock_refs[key] = 0
            self._key_lock_refs[key] += 1
            lock = self._key_locks[key]
        lock.acquire()
        return lock

    def _release_key_lock(self, key: str):
        with self._global_lock:
            lock = self._key_locks[key]
            lock.release()
            self._key_lock_refs[key] -= 1
            # Clean up lock if no one is waiting
            if self._key_lock_refs[key] == 0:
                del self._key_locks[key]
                del self._key_lock_refs[key]

    def _cleanup_loop(self, interval: float):
        while not self._cleanup_stop.wait(timeout=interval):
            self._cleanup_expired()

    def _cleanup_expired(self):
        with self._global_lock:
            expired_keys = [
                k for k, v in self._cache.items() if v.is_expired
            ]
            for key in expired_keys:
                del self._cache[key]
            if expired_keys:
                logger.debug("Cleaned up %d expired entries", len(expired_keys))

    def stats(self) -> dict[str, Any]:
        with self._global_lock:
            total = len(self._cache)
            expired = sum(
                1 for v in self._cache.values() if v.is_expired
            )
            return {
                "total_entries": total,
                "expired_entries": expired,
                "active_entries": total - expired,
                "pending_locks": len(self._key_locks),
            }

    def shutdown(self):
        self._cleanup_stop.set()
        self._cleanup_thread.join(timeout=5)

# ============================================================
# Demo: thundering herd prevention
# ============================================================

def demo():
    cache = TTLCache(default_ttl=5.0, max_size=1000)
    call_count = {"expensive_fn": 0}

    def expensive_computation(key: str) -> dict:
        call_count["expensive_fn"] += 1
        time.sleep(1.0)  # simulate slow computation
        return {"key": key, "computed_at": time.time()}

    # Simulate thundering herd: 20 threads requesting same key
    results = []
    errors = []

    def worker(thread_id: int):
        try:
            result = cache.get_or_compute(
                "popular_key",
                lambda: expensive_computation("popular_key"),
            )
            results.append((thread_id, result))
        except Exception as e:
            errors.append((thread_id, str(e)))

    threads = [
        threading.Thread(target=worker, args=(i,))
        for i in range(20)
    ]
    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.monotonic() - start

    print(f"20 threads, elapsed: {elapsed:.2f}s")
    print(f"expensive_fn called: {call_count['expensive_fn']} time(s)")
    print(f"Results: {len(results)}, Errors: {len(errors)}")
    # Expected: expensive_fn called 1 time (not 20!)

    cache.shutdown()

if __name__ == "__main__":
    demo()
```

Key design features:
- Per-key locking prevents thundering herd (only one thread computes)
- Lock cleanup prevents memory leaks from accumulating key locks
- LRU eviction via `OrderedDict.move_to_end()` keeps cache bounded
- Background cleanup thread removes expired entries periodically
- Double-checked locking after acquiring key lock for correctness'''
    },
    {
        "instruction": r'''How do I implement graceful shutdown in a Python async application with multiple long-running tasks, open connections, and pending work?''',
        "output": r'''<think>
Graceful shutdown is one of the hardest concurrency problems to get right. The requirements:

1. Stop accepting new work
2. Let in-progress work finish (with a timeout)
3. Close connections cleanly (database, HTTP, WebSocket)
4. Save any pending state
5. Cancel truly stuck tasks after timeout

The challenge is coordinating all of this. In an async app, you need to:
- Handle SIGTERM and SIGINT signals
- Cancel background tasks
- Drain queues
- Close connection pools
- Wait for everything with a deadline

The common mistake is calling sys.exit() or os._exit() which kills everything immediately without cleanup. Another mistake is not setting a shutdown timeout, so the app hangs forever if a task does not respond to cancellation.

I should show a complete shutdown coordinator that handles all of these concerns.
</think>

```python
import asyncio
import signal
import logging
import time
from typing import Any, Callable, Coroutine
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# ============================================================
# Shutdown coordinator
# ============================================================

class GracefulShutdown:
    """Coordinates graceful shutdown of an async application."""

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout
        self._shutdown_event = asyncio.Event()
        self._tasks: set[asyncio.Task] = set()
        self._cleanup_handlers: list[Callable] = []
        self._is_shutting_down = False

    @property
    def is_shutting_down(self) -> bool:
        return self._is_shutting_down

    def should_continue(self) -> bool:
        """Check in long-running loops."""
        return not self._shutdown_event.is_set()

    async def wait_for_shutdown(self):
        """Block until shutdown signal received."""
        await self._shutdown_event.wait()

    def register_cleanup(self, handler: Callable):
        """Register an async cleanup function."""
        self._cleanup_handlers.append(handler)

    def create_task(self, coro, name: str = None) -> asyncio.Task:
        """Create a tracked task that will be cancelled on shutdown."""
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def setup_signals(self):
        """Register signal handlers for SIGINT and SIGTERM."""
        loop = asyncio.get_running_loop()

        def signal_handler():
            if self._is_shutting_down:
                logger.warning("Force shutdown (second signal)")
                raise SystemExit(1)
            logger.info("Shutdown signal received")
            self._is_shutting_down = True
            self._shutdown_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)

    async def shutdown(self):
        """Execute the shutdown sequence."""
        logger.info(
            "Starting graceful shutdown (timeout: %.0fs)", self.timeout
        )
        start = time.monotonic()

        # Phase 1: Run cleanup handlers
        logger.info("Phase 1: Running cleanup handlers...")
        for handler in reversed(self._cleanup_handlers):
            try:
                result = handler()
                if asyncio.iscoroutine(result):
                    await asyncio.wait_for(result, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning(
                    "Cleanup handler timed out: %s", handler
                )
            except Exception as e:
                logger.error("Cleanup handler failed: %s", e)

        # Phase 2: Cancel tracked tasks
        remaining_timeout = max(
            1.0, self.timeout - (time.monotonic() - start)
        )
        if self._tasks:
            logger.info(
                "Phase 2: Cancelling %d tasks...", len(self._tasks)
            )
            for task in self._tasks:
                task.cancel()

            done, pending = await asyncio.wait(
                self._tasks, timeout=remaining_timeout
            )
            if pending:
                logger.warning(
                    "%d tasks did not finish after cancellation",
                    len(pending),
                )

        elapsed = time.monotonic() - start
        logger.info("Shutdown complete in %.1fs", elapsed)

# ============================================================
# Example application using GracefulShutdown
# ============================================================

class Application:
    def __init__(self):
        self.shutdown = GracefulShutdown(timeout=30.0)
        self._db_pool = None
        self._http_client = None

    async def start(self):
        """Initialize resources and start workers."""
        self.shutdown.setup_signals()

        # Initialize resources
        logger.info("Initializing resources...")
        # self._db_pool = await asyncpg.create_pool(DSN)
        # self._http_client = httpx.AsyncClient()

        # Register cleanup in reverse order of initialization
        self.shutdown.register_cleanup(self._close_http)
        self.shutdown.register_cleanup(self._close_db)
        self.shutdown.register_cleanup(self._drain_queue)

        # Start background workers
        self.shutdown.create_task(
            self._worker("fetcher"), name="fetcher"
        )
        self.shutdown.create_task(
            self._worker("processor"), name="processor"
        )
        self.shutdown.create_task(
            self._health_checker(), name="health-check"
        )

        logger.info("Application started")

        # Wait for shutdown signal
        await self.shutdown.wait_for_shutdown()

        # Execute shutdown sequence
        await self.shutdown.shutdown()

    async def _worker(self, name: str):
        """Long-running worker that checks shutdown flag."""
        logger.info("[%s] Worker started", name)
        try:
            while self.shutdown.should_continue():
                # Do work
                await asyncio.sleep(1.0)
                logger.debug("[%s] Processing...", name)
        except asyncio.CancelledError:
            logger.info("[%s] Worker cancelled, cleaning up", name)
            # Finish current item before exiting
            await asyncio.sleep(0.1)  # simulate cleanup
            raise  # re-raise to mark task as cancelled

    async def _health_checker(self):
        """Periodic health check."""
        try:
            while self.shutdown.should_continue():
                # Check database, external services, etc.
                logger.debug("Health check: OK")
                await asyncio.sleep(10.0)
        except asyncio.CancelledError:
            pass

    async def _drain_queue(self):
        """Process remaining items in the queue."""
        logger.info("Draining work queue...")
        await asyncio.sleep(0.5)  # simulate draining
        logger.info("Queue drained")

    async def _close_http(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
        logger.info("HTTP client closed")

    async def _close_db(self):
        """Close database pool."""
        if self._db_pool:
            await self._db_pool.close()
        logger.info("Database pool closed")

# ============================================================
# Entry point
# ============================================================

async def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    app = Application()
    await app.start()

if __name__ == "__main__":
    asyncio.run(main())
```

Shutdown phases:
1. Signal received -- set shutdown flag, stop accepting new work
2. Run cleanup handlers -- drain queues, flush buffers, save state
3. Cancel background tasks -- send CancelledError, wait with timeout
4. Close resources -- connections, pools, file handles
5. Exit -- if tasks are stuck after timeout, force exit

Key rules:
- Always re-raise `CancelledError` after cleanup
- Use `should_continue()` checks in loops for cooperative shutdown
- Set a hard timeout to prevent hanging forever
- Handle second signal as force-quit (immediate exit)'''
    },
    {
        "instruction": r'''How do I implement backpressure in an async Python pipeline to prevent fast producers from overwhelming slow consumers?''',
        "output": r'''<think>
Backpressure is the mechanism that slows down producers when consumers cannot keep up. Without it, the system runs out of memory as unbounded queues grow.

In async Python, backpressure comes from several mechanisms:
1. Bounded asyncio.Queue -- put() blocks when full
2. Semaphore -- limits how many items are in-flight
3. Flow control signals -- explicit pause/resume
4. Adaptive rate limiting -- dynamically adjust producer rate based on consumer lag

The simplest approach is bounded queues, but for multi-stage pipelines, you need backpressure to propagate backwards through all stages. If stage 3 is slow, stage 2's output queue fills up, which slows stage 2, which fills stage 1's output queue, which slows stage 1 -- pressure propagates backwards naturally with bounded queues.

I should show a multi-stage pipeline with proper backpressure, monitoring, and the ability to detect when the system is under pressure.
</think>

Backpressure prevents fast producers from overwhelming slow consumers. Here is how to implement it in async Python:

```python
import asyncio
import time
import random
import logging
from typing import Any, AsyncIterator, Callable, TypeVar
from dataclasses import dataclass

logger = logging.getLogger(__name__)
T = TypeVar("T")

# ============================================================
# Bounded async pipeline with backpressure
# ============================================================

@dataclass
class PipelineMetrics:
    items_produced: int = 0
    items_consumed: int = 0
    producer_waits: int = 0  # times producer blocked on full queue
    consumer_waits: int = 0  # times consumer blocked on empty queue
    max_queue_depth: int = 0

class BackpressuredQueue:
    """Async queue with backpressure monitoring."""

    def __init__(self, name: str, maxsize: int = 100):
        self.name = name
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=maxsize)
        self._maxsize = maxsize
        self.metrics = PipelineMetrics()

    async def put(self, item: Any):
        if self._queue.full():
            self.metrics.producer_waits += 1
            logger.debug(
                "[%s] Backpressure: queue full (%d), producer waiting",
                self.name, self._maxsize,
            )
        await self._queue.put(item)
        self.metrics.items_produced += 1
        depth = self._queue.qsize()
        if depth > self.metrics.max_queue_depth:
            self.metrics.max_queue_depth = depth

    async def get(self) -> Any:
        if self._queue.empty():
            self.metrics.consumer_waits += 1
        item = await self._queue.get()
        self.metrics.items_consumed += 1
        return item

    def task_done(self):
        self._queue.task_done()

    async def join(self):
        await self._queue.join()

    @property
    def pressure_ratio(self) -> float:
        """0.0 = empty, 1.0 = full."""
        return self._queue.qsize() / self._maxsize

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "depth": self._queue.qsize(),
            "maxsize": self._maxsize,
            "pressure": f"{self.pressure_ratio:.0%}",
            "producer_waits": self.metrics.producer_waits,
            "produced": self.metrics.items_produced,
            "consumed": self.metrics.items_consumed,
        }

# ============================================================
# Multi-stage pipeline with backpressure
# ============================================================

_SENTINEL = object()

class AsyncPipeline:
    """Multi-stage async pipeline with automatic backpressure."""

    def __init__(self):
        self._stages: list[tuple[str, Callable, int, int]] = []
        self._queues: list[BackpressuredQueue] = []
        self._tasks: list[asyncio.Task] = []

    def add_stage(
        self,
        name: str,
        processor: Callable,
        workers: int = 1,
        queue_size: int = 100,
    ):
        """Add a processing stage to the pipeline."""
        self._stages.append((name, processor, workers, queue_size))

    async def run(self, items: AsyncIterator):
        """Run the pipeline with the given input."""
        # Create queues between stages
        self._queues = [
            BackpressuredQueue(name, maxsize=qsize)
            for name, _, _, qsize in self._stages
        ]

        # Start monitor
        monitor = asyncio.create_task(self._monitor())

        # Start workers for each stage
        for i, (name, processor, workers, _) in enumerate(self._stages):
            input_q = self._queues[i]
            output_q = self._queues[i + 1] if i + 1 < len(self._queues) else None

            for w in range(workers):
                task = asyncio.create_task(
                    self._stage_worker(
                        f"{name}-{w}", processor, input_q, output_q
                    )
                )
                self._tasks.append(task)

        # Feed items into the first queue
        first_queue = self._queues[0]
        count = 0
        async for item in items:
            await first_queue.put(item)
            count += 1

        # Send sentinels to first stage
        num_first_workers = self._stages[0][2]
        for _ in range(num_first_workers):
            await first_queue.put(_SENTINEL)

        # Wait for pipeline to drain
        for q in self._queues:
            await q.join()

        # Stop monitor
        monitor.cancel()
        try:
            await monitor
        except asyncio.CancelledError:
            pass

        # Print final stats
        self._print_stats()

    async def _stage_worker(
        self,
        name: str,
        processor: Callable,
        input_q: BackpressuredQueue,
        output_q: BackpressuredQueue | None,
    ):
        while True:
            item = await input_q.get()
            if item is _SENTINEL:
                input_q.task_done()
                # Propagate sentinel to next stage
                if output_q:
                    await output_q.put(_SENTINEL)
                break

            try:
                result = await processor(item)
                if output_q and result is not None:
                    await output_q.put(result)
            except Exception as e:
                logger.error("[%s] Error: %s", name, e)
            finally:
                input_q.task_done()

    async def _monitor(self):
        """Periodically log pipeline health."""
        while True:
            await asyncio.sleep(2.0)
            statuses = [q.status() for q in self._queues]
            pressured = [
                s for s in statuses if s["producer_waits"] > 0
            ]
            if pressured:
                for s in pressured:
                    logger.warning(
                        "Backpressure at %s: depth=%d/%d waits=%d",
                        s["name"], s["depth"], s["maxsize"],
                        s["producer_waits"],
                    )

    def _print_stats(self):
        print("\nPipeline Statistics:")
        print(f"{'Stage':<20} {'Produced':>10} {'Consumed':>10} "
              f"{'Waits':>8} {'Max Depth':>10}")
        print("-" * 62)
        for q in self._queues:
            m = q.metrics
            print(
                f"{q.name:<20} {m.items_produced:>10} "
                f"{m.items_consumed:>10} {m.producer_waits:>8} "
                f"{m.max_queue_depth:>10}"
            )

# ============================================================
# Example: data processing pipeline
# ============================================================

async def generate_items(count: int) -> AsyncIterator[dict]:
    for i in range(count):
        await asyncio.sleep(0.01)  # fast producer
        yield {"id": i, "raw_data": f"item-{i}"}

async def stage_validate(item: dict) -> dict:
    await asyncio.sleep(0.02)  # quick
    item["validated"] = True
    return item

async def stage_enrich(item: dict) -> dict:
    await asyncio.sleep(0.1)  # slow -- bottleneck!
    item["enriched"] = True
    return item

async def stage_store(item: dict) -> None:
    await asyncio.sleep(0.03)
    # Write to database

async def main():
    logging.basicConfig(level=logging.INFO)

    pipeline = AsyncPipeline()
    pipeline.add_stage("validate", stage_validate, workers=2, queue_size=50)
    pipeline.add_stage("enrich", stage_enrich, workers=8, queue_size=20)
    pipeline.add_stage("store", stage_store, workers=4, queue_size=50)

    start = time.monotonic()
    await pipeline.run(generate_items(200))
    elapsed = time.monotonic() - start

    print(f"\nTotal time: {elapsed:.1f}s")
    print(f"Throughput: {200 / elapsed:.1f} items/sec")

# asyncio.run(main())
```

Key principles:
- Bounded queues create natural backpressure (producers block when full)
- Scale workers at the bottleneck stage (enrich has 8 workers)
- Keep queue sizes small for fast backpressure propagation
- Monitor `producer_waits` to identify bottleneck stages
- The slowest stage determines overall throughput'''
    },
]
