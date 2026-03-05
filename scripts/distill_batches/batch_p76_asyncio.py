"""Python — asyncio deep patterns, structured concurrency, and async generators."""

PAIRS = [
    (
        "python/asyncio-patterns",
        "Show advanced asyncio patterns: task groups, structured concurrency, semaphores, event loops, and cancellation.",
        '''Advanced asyncio patterns:

```python
import asyncio
from asyncio import TaskGroup, Semaphore, Queue
from contextlib import asynccontextmanager
from typing import AsyncIterator
import logging

logger = logging.getLogger(__name__)


# --- Structured concurrency with TaskGroup (3.11+) ---

async def fetch_all_users(user_ids: list[int]) -> list[dict]:
    """Fetch users concurrently with structured concurrency."""
    results: list[dict] = []

    async with TaskGroup() as tg:
        for uid in user_ids:
            tg.create_task(fetch_and_collect(uid, results))

    # All tasks guaranteed complete here (or exception raised)
    return results


async def fetch_and_collect(uid: int, results: list[dict]):
    user = await fetch_user(uid)
    results.append(user)


# --- Semaphore (limit concurrency) ---

async def fetch_many_with_limit(
    urls: list[str], max_concurrent: int = 10
) -> list[str]:
    """Fetch URLs with concurrency limit."""
    sem = Semaphore(max_concurrent)
    results = [None] * len(urls)

    async def bounded_fetch(idx: int, url: str):
        async with sem:  # At most max_concurrent running
            results[idx] = await fetch_url(url)

    async with TaskGroup() as tg:
        for i, url in enumerate(urls):
            tg.create_task(bounded_fetch(i, url))

    return results


# --- Producer-consumer with asyncio.Queue ---

async def pipeline(urls: list[str], workers: int = 5):
    """Producer-consumer pipeline with async queue."""
    queue: Queue[str | None] = Queue(maxsize=100)

    async def producer():
        for url in urls:
            await queue.put(url)
        # Signal workers to stop
        for _ in range(workers):
            await queue.put(None)

    async def consumer(worker_id: int):
        while True:
            item = await queue.get()
            if item is None:
                break
            try:
                result = await process(item)
                logger.info("Worker %d processed: %s", worker_id, result)
            except Exception as e:
                logger.error("Worker %d failed on %s: %s", worker_id, item, e)
            finally:
                queue.task_done()

    async with TaskGroup() as tg:
        tg.create_task(producer())
        for i in range(workers):
            tg.create_task(consumer(i))


# --- Timeouts and cancellation ---

async def fetch_with_timeout(url: str, timeout: float = 5.0) -> str:
    """Fetch with timeout, returning fallback on timeout."""
    try:
        async with asyncio.timeout(timeout):
            return await fetch_url(url)
    except TimeoutError:
        logger.warning("Timeout fetching %s", url)
        return ""


async def cancellable_operation():
    """Handle cancellation gracefully."""
    try:
        while True:
            await asyncio.sleep(1)
            # Do periodic work
    except asyncio.CancelledError:
        # Cleanup before propagating
        await cleanup()
        raise  # Always re-raise CancelledError


# --- Async context manager for resource lifecycle ---

@asynccontextmanager
async def managed_connection(host: str, port: int):
    """Async context manager for connection lifecycle."""
    conn = await create_connection(host, port)
    try:
        yield conn
    finally:
        await conn.close()


# --- Shield from cancellation ---

async def critical_save(data: dict):
    """Protect critical operation from cancellation."""
    # Even if parent task is cancelled, this completes
    await asyncio.shield(save_to_database(data))


# --- Running sync code in async context ---

import concurrent.futures

async def run_cpu_bound(data: list[int]) -> int:
    """Run CPU-bound work in thread/process pool."""
    loop = asyncio.get_running_loop()

    # Thread pool for I/O-bound blocking code
    result = await loop.run_in_executor(
        None,  # Default ThreadPoolExecutor
        blocking_io_function, data,
    )

    # Process pool for CPU-bound work
    with concurrent.futures.ProcessPoolExecutor() as pool:
        result = await loop.run_in_executor(
            pool, cpu_heavy_function, data,
        )

    return result
```

Asyncio patterns:
1. **`TaskGroup`** — structured concurrency ensures all tasks complete or all fail
2. **`Semaphore`** — limit concurrency to prevent resource exhaustion
3. **`asyncio.Queue`** — producer-consumer with backpressure (maxsize)
4. **`asyncio.timeout()`** — clean timeout handling (3.11+)
5. **`asyncio.shield()`** — protect critical operations from cancellation'''
    ),
    (
        "python/async-generators",
        "Show async generator and async iterator patterns: streaming data, async for, and async comprehensions.",
        '''Async generators and iterators:

```python
import asyncio
from typing import AsyncIterator, AsyncGenerator
from dataclasses import dataclass


# --- Async generator (yield values asynchronously) ---

async def stream_pages(url: str, max_pages: int = 100) -> AsyncGenerator[dict, None]:
    """Paginate through API results lazily."""
    next_cursor = None

    for _ in range(max_pages):
        response = await fetch_page(url, cursor=next_cursor)
        for item in response["items"]:
            yield item

        next_cursor = response.get("next_cursor")
        if not next_cursor:
            break


# Usage: async for item in stream_pages("/api/users"):
#            process(item)


# --- Async iterator class ---

@dataclass
class AsyncBatchReader:
    """Read from a source in batches, yielding items one by one."""
    source: str
    batch_size: int = 100
    _buffer: list = None
    _offset: int = 0
    _exhausted: bool = False

    def __aiter__(self):
        self._buffer = []
        self._offset = 0
        self._exhausted = False
        return self

    async def __anext__(self):
        if not self._buffer:
            if self._exhausted:
                raise StopAsyncIteration

            # Fetch next batch
            batch = await fetch_batch(
                self.source, offset=self._offset, limit=self.batch_size
            )
            if len(batch) < self.batch_size:
                self._exhausted = True
            if not batch:
                raise StopAsyncIteration

            self._buffer = batch
            self._offset += len(batch)

        return self._buffer.pop(0)


# --- Async comprehensions ---

async def process_users():
    # Async list comprehension
    users = [user async for user in stream_pages("/api/users")]

    # Async generator expression
    names = (user["name"] async for user in stream_pages("/api/users"))

    # Async comprehension with filter
    active = [
        user async for user in stream_pages("/api/users")
        if user["status"] == "active"
    ]

    # Async dict comprehension
    user_map = {
        user["id"]: user
        async for user in stream_pages("/api/users")
    }


# --- Merging multiple async streams ---

async def merge_streams(
    *streams: AsyncIterator[dict],
) -> AsyncGenerator[dict, None]:
    """Merge multiple async iterators into one stream."""
    queue: asyncio.Queue[dict | None] = asyncio.Queue()
    active = len(streams)

    async def drain(stream: AsyncIterator[dict]):
        nonlocal active
        try:
            async for item in stream:
                await queue.put(item)
        finally:
            active -= 1
            if active == 0:
                await queue.put(None)  # Signal completion

    async with asyncio.TaskGroup() as tg:
        for stream in streams:
            tg.create_task(drain(stream))

        while True:
            item = await queue.get()
            if item is None:
                break
            yield item


# --- Rate-limited async iteration ---

async def rate_limited(
    iterable: AsyncIterator, requests_per_second: float = 10
) -> AsyncGenerator:
    """Wrap async iterator with rate limiting."""
    interval = 1.0 / requests_per_second

    async for item in iterable:
        yield item
        await asyncio.sleep(interval)


# Usage:
# async for user in rate_limited(stream_pages("/api/users"), rps=5):
#     await process_user(user)


# --- Async context manager + iterator combo ---

class ManagedStream:
    """Async iterator that manages its own connection lifecycle."""

    def __init__(self, url: str):
        self.url = url
        self.conn = None

    async def __aenter__(self):
        self.conn = await connect(self.url)
        return self

    async def __aexit__(self, *exc):
        if self.conn:
            await self.conn.close()

    def __aiter__(self):
        return self

    async def __anext__(self):
        data = await self.conn.read()
        if data is None:
            raise StopAsyncIteration
        return data


# Usage:
# async with ManagedStream("wss://feed") as stream:
#     async for message in stream:
#         handle(message)
```

Async generator patterns:
1. **`async def ... yield`** — produce values lazily with await between yields
2. **`async for`** — consume async iterators cleanly
3. **`__aiter__`/`__anext__`** — async iterator protocol for stateful iteration
4. **Stream merging** — combine multiple async sources into unified stream
5. **Rate limiting** — wrap any async iterator with throttling'''
    ),
    (
        "python/pathlib-advanced",
        "Show advanced pathlib patterns: file operations, tree walking, temp files, and atomic writes.",
        '''Advanced pathlib and file handling:

```python
from pathlib import Path, PurePosixPath, PureWindowsPath
import tempfile
import shutil
import os
import json
from contextlib import contextmanager


# --- Basic pathlib operations ---

# Path construction (OS-aware)
project = Path(__file__).resolve().parent.parent
config_dir = project / "config"
data_file = config_dir / "settings.json"

# Path properties
print(data_file.name)       # "settings.json"
print(data_file.stem)       # "settings"
print(data_file.suffix)     # ".json"
print(data_file.parent)     # .../config
print(data_file.parts)      # ('/', 'home', ..., 'settings.json')

# Check existence
data_file.exists()
data_file.is_file()
data_file.is_dir()
data_file.is_symlink()


# --- File I/O ---

# Read/write text
content = data_file.read_text(encoding="utf-8")
data_file.write_text("new content", encoding="utf-8")

# Read/write bytes
raw = data_file.read_bytes()
data_file.write_bytes(b"\\x00\\x01\\x02")

# JSON round-trip
data = json.loads(data_file.read_text())
data_file.write_text(json.dumps(data, indent=2))


# --- Directory operations ---

# Create directories
output = project / "output" / "reports"
output.mkdir(parents=True, exist_ok=True)

# List directory
for child in config_dir.iterdir():
    print(child.name, child.is_file())

# Glob patterns
py_files = list(project.rglob("*.py"))           # Recursive
test_files = list(project.glob("tests/test_*.py"))  # Non-recursive
configs = list(project.glob("**/*.{json,yaml}"))  # NOT supported — use:
configs = [p for p in project.rglob("*") if p.suffix in (".json", ".yaml")]


# --- Tree walking ---

def dir_tree(path: Path, prefix: str = "", max_depth: int = 3) -> str:
    """Generate directory tree string."""
    if max_depth <= 0:
        return prefix + "...\\n"

    lines = []
    entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))

    for i, entry in enumerate(entries):
        is_last = i == len(entries) - 1
        connector = "└── " if is_last else "├── "
        lines.append(f"{prefix}{connector}{entry.name}")

        if entry.is_dir() and not entry.name.startswith("."):
            extension = "    " if is_last else "│   "
            lines.append(dir_tree(entry, prefix + extension, max_depth - 1))

    return "\\n".join(lines)


# --- File size and stats ---

def human_size(size_bytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"

def dir_size(path: Path) -> int:
    """Total size of directory contents."""
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


# --- Atomic write (write to temp, then rename) ---

@contextmanager
def atomic_write(target: Path, mode: str = "w", **kwargs):
    """Write to temp file, rename on success. Prevents partial writes."""
    tmp = target.with_suffix(target.suffix + ".tmp")
    try:
        with open(tmp, mode, **kwargs) as f:
            yield f
        tmp.replace(target)  # Atomic on same filesystem
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

# Usage:
# with atomic_write(Path("data.json")) as f:
#     json.dump(large_data, f)


# --- Temporary files and directories ---

def process_with_temp():
    """Use temporary directory for intermediate files."""
    with tempfile.TemporaryDirectory(prefix="myapp_") as tmpdir:
        tmp = Path(tmpdir)
        intermediate = tmp / "step1.csv"
        intermediate.write_text("col1,col2\\n1,2\\n")

        # Process...
        result = tmp / "result.json"
        result.write_text('{"status": "ok"}')

        # Copy result to final location
        shutil.copy2(result, Path("output/result.json"))
    # tmpdir auto-deleted here


# --- Safe file operations ---

def safe_move(src: Path, dst: Path):
    """Move file with backup."""
    if dst.exists():
        backup = dst.with_suffix(dst.suffix + ".bak")
        shutil.copy2(dst, backup)
    shutil.move(str(src), str(dst))

def find_duplicates(directory: Path) -> dict[str, list[Path]]:
    """Find files with identical content (by hash)."""
    import hashlib
    hashes: dict[str, list[Path]] = {}
    for f in directory.rglob("*"):
        if f.is_file():
            h = hashlib.md5(f.read_bytes()).hexdigest()
            hashes.setdefault(h, []).append(f)
    return {h: paths for h, paths in hashes.items() if len(paths) > 1}
```

Pathlib patterns:
1. **`Path / "subdir"`** — operator overload for cross-platform path construction
2. **`.rglob("*.py")`** — recursive glob without manual os.walk
3. **`atomic_write()`** — temp + rename prevents corrupted partial writes
4. **`TemporaryDirectory`** — auto-cleanup for intermediate processing
5. **`.read_text()` / `.write_text()`** — one-liner file I/O with encoding'''
    ),
]
