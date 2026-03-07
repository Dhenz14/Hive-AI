"""Async/concurrency training pairs: Python asyncio fundamentals."""

pairs = [
    {
        "instruction": r'''What is the difference between a coroutine and a regular function in Python? How does the event loop execute coroutines?''',
        "output": r'''<think>
The user is asking about coroutines vs regular functions. Let me think about what makes them fundamentally different. A regular function runs to completion when called -- it blocks the caller. A coroutine defined with async def returns a coroutine object when called, it does not execute immediately. You need to await it or schedule it on the event loop.

Wait, I should clarify something. When you call an async def function, you get a coroutine object. That object does nothing until you either await it or pass it to asyncio.run(), create_task(), etc. The event loop is what actually drives execution -- it calls .send(None) on the coroutine to advance it, and when the coroutine hits an await, control returns to the event loop so it can run other coroutines.

I should show this concretely with code that demonstrates the lazy evaluation aspect and how the event loop schedules things.
</think>

A coroutine (defined with `async def`) differs from a regular function in how it executes:

```python
import asyncio

# Regular function -- runs immediately, blocks until done
def regular_greet(name: str) -> str:
    return f"Hello, {name}"

# Coroutine function -- returns a coroutine object when called
async def async_greet(name: str) -> str:
    await asyncio.sleep(0.1)  # yields control to event loop
    return f"Hello, {name}"

# Calling a regular function executes it immediately
result = regular_greet("Alice")  # "Hello, Alice"

# Calling a coroutine function does NOT execute it
coro = async_greet("Bob")  # <coroutine object async_greet at 0x...>
# Nothing has happened yet! The coroutine is suspended.

# The event loop drives execution
async def main():
    # await resumes the coroutine and waits for its result
    result = await async_greet("Bob")
    print(result)  # "Hello, Bob"

asyncio.run(main())
```

The event loop maintains a queue of ready coroutines. When a coroutine hits `await`, it suspends and the loop picks up the next ready coroutine:

```python
import asyncio
import time

async def task(name: str, delay: float) -> str:
    print(f"[{name}] started at {time.monotonic():.2f}")
    await asyncio.sleep(delay)  # suspends -- loop runs other tasks
    print(f"[{name}] finished at {time.monotonic():.2f}")
    return name

async def main():
    start = time.monotonic()

    # Sequential -- total time is sum of delays
    r1 = await task("A", 1.0)
    r2 = await task("B", 1.0)
    print(f"Sequential: {time.monotonic() - start:.2f}s")  # ~2.0s

    start = time.monotonic()

    # Concurrent -- total time is max of delays
    r1, r2 = await asyncio.gather(
        task("C", 1.0),
        task("D", 1.0),
    )
    print(f"Concurrent: {time.monotonic() - start:.2f}s")  # ~1.0s

asyncio.run(main())
```

Key points:
- `async def` creates a coroutine function; calling it returns a coroutine object
- The coroutine does not run until awaited or scheduled on the event loop
- `await` suspends the current coroutine, letting others run
- `asyncio.run()` creates an event loop, runs the top-level coroutine, then closes the loop
- Only one coroutine runs at a time (no parallelism, just concurrency)'''
    },
    {
        "instruction": r'''Show me how to use asyncio.gather() to run multiple async tasks concurrently in Python. Include error handling.''',
        "output": r'''`asyncio.gather()` runs multiple awaitables concurrently and collects their results in order:

```python
import asyncio
import random
from typing import Any

async def fetch_user(user_id: int) -> dict[str, Any]:
    """Simulate fetching user from database."""
    await asyncio.sleep(random.uniform(0.1, 0.5))
    if user_id == 999:
        raise ValueError(f"User {user_id} not found")
    return {"id": user_id, "name": f"User_{user_id}"}

async def fetch_many_users(user_ids: list[int]) -> list[dict[str, Any]]:
    """Fetch multiple users concurrently."""
    results = await asyncio.gather(
        *(fetch_user(uid) for uid in user_ids)
    )
    # results is a list in the same order as the input
    return results

# --- Error handling strategies ---

async def fetch_with_exceptions_returned(user_ids: list[int]):
    """return_exceptions=True collects errors instead of raising."""
    results = await asyncio.gather(
        *(fetch_user(uid) for uid in user_ids),
        return_exceptions=True,
    )
    successes = []
    failures = []
    for uid, result in zip(user_ids, results):
        if isinstance(result, Exception):
            failures.append((uid, result))
        else:
            successes.append(result)
    return successes, failures

async def fetch_with_per_task_handling(user_ids: list[int]):
    """Wrap each task to handle errors individually."""
    async def safe_fetch(uid: int) -> dict[str, Any] | None:
        try:
            return await fetch_user(uid)
        except ValueError:
            return None

    results = await asyncio.gather(
        *(safe_fetch(uid) for uid in user_ids)
    )
    return [r for r in results if r is not None]

async def main():
    # Happy path
    users = await fetch_many_users([1, 2, 3])
    print(f"Fetched {len(users)} users")

    # With a bad ID -- return_exceptions approach
    successes, failures = await fetch_with_exceptions_returned(
        [1, 2, 999, 4]
    )
    print(f"OK: {len(successes)}, Failed: {len(failures)}")
    for uid, err in failures:
        print(f"  User {uid}: {err}")

    # Per-task error handling approach
    users = await fetch_with_per_task_handling([1, 999, 3])
    print(f"Got {len(users)} valid users")

asyncio.run(main())
```

Without `return_exceptions=True`, the first exception cancels all remaining tasks and propagates immediately. With it, exceptions are returned as values in the results list.'''
    },
    {
        "instruction": r'''How do I use asyncio.TaskGroup in Python 3.11+ and how does it differ from asyncio.gather?''',
        "output": r'''<think>
TaskGroup vs gather -- I need to highlight the key differences. TaskGroup was added in 3.11 as structured concurrency. The big differences:

1. TaskGroup cancels ALL sibling tasks if any task raises an exception. gather with return_exceptions=True does NOT cancel siblings.
2. TaskGroup uses context manager syntax (async with) which enforces scope -- tasks cannot outlive the block.
3. TaskGroup raises ExceptionGroup (Python 3.11+) when multiple tasks fail, while gather raises the first exception.
4. You cannot do return_exceptions=True with TaskGroup -- if a task fails, it is always an error.

Hmm, actually wait -- gather without return_exceptions also cancels remaining tasks when one fails. The difference is that TaskGroup collects ALL exceptions into an ExceptionGroup, while gather only propagates the first one. Let me make sure I get this right in the code.
</think>

`TaskGroup` (Python 3.11+) provides structured concurrency -- tasks are scoped to a block and cannot leak:

```python
import asyncio
from typing import Any

async def fetch_data(source: str, delay: float) -> dict[str, Any]:
    await asyncio.sleep(delay)
    return {"source": source, "data": f"result from {source}"}

async def failing_task():
    await asyncio.sleep(0.1)
    raise RuntimeError("Something broke")

# --- Basic TaskGroup usage ---

async def fetch_all() -> list[dict[str, Any]]:
    async with asyncio.TaskGroup() as tg:
        task_a = tg.create_task(fetch_data("api", 0.3))
        task_b = tg.create_task(fetch_data("cache", 0.1))
        task_c = tg.create_task(fetch_data("db", 0.5))
    # All tasks guaranteed complete when we reach here
    return [task_a.result(), task_b.result(), task_c.result()]

# --- Error handling with TaskGroup ---

async def handle_taskgroup_errors():
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(fetch_data("api", 1.0))
            tg.create_task(failing_task())
            # When failing_task raises, the api task is CANCELLED
    except* RuntimeError as eg:
        # except* catches ExceptionGroup (PEP 654)
        for exc in eg.exceptions:
            print(f"Caught: {exc}")

# --- Key differences from gather ---

async def gather_example():
    # gather: first exception propagates, others may be lost
    try:
        results = await asyncio.gather(
            fetch_data("api", 1.0),
            failing_task(),
        )
    except RuntimeError as e:
        print(f"gather caught: {e}")
        # Only the FIRST exception -- others silently lost

    # gather with return_exceptions: NO cancellation on failure
    results = await asyncio.gather(
        fetch_data("api", 0.1),
        failing_task(),
        return_exceptions=True,
    )
    # results = [{"source": "api", ...}, RuntimeError("Something broke")]

async def taskgroup_example():
    # TaskGroup: ALL exceptions collected in ExceptionGroup
    # ALL sibling tasks cancelled on first failure
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(failing_task())
            tg.create_task(failing_task())
    except* RuntimeError as eg:
        print(f"TaskGroup caught {len(eg.exceptions)} errors")

async def main():
    results = await fetch_all()
    print(f"Got {len(results)} results")
    await handle_taskgroup_errors()

asyncio.run(main())
```

Summary of differences:
- `TaskGroup` enforces structured concurrency -- tasks cannot outlive the block
- `TaskGroup` cancels ALL siblings when any task fails
- `TaskGroup` raises `ExceptionGroup` with ALL errors (use `except*`)
- `gather` can return exceptions as values with `return_exceptions=True`
- `gather` only propagates the first exception by default'''
    },
    {
        "instruction": r'''How do I run a blocking function (like file I/O or CPU-bound code) inside an async Python application without blocking the event loop?''',
        "output": r'''Use `asyncio.to_thread()` (Python 3.9+) or `loop.run_in_executor()` to offload blocking work:

```python
import asyncio
import time
import hashlib
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from pathlib import Path

# --- Problem: blocking call freezes the event loop ---

async def bad_example():
    # This blocks the entire event loop for 2 seconds!
    time.sleep(2)
    # No other coroutines can run during that time

# --- Fix 1: asyncio.to_thread() for I/O-bound blocking ---

def read_large_file(path: str) -> str:
    """Regular blocking function."""
    with open(path, "r") as f:
        return f.read()

def compute_file_hash(path: str) -> str:
    """CPU-light but I/O-bound."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

async def process_files(paths: list[str]):
    # to_thread runs the function in a thread pool
    tasks = [asyncio.to_thread(compute_file_hash, p) for p in paths]
    hashes = await asyncio.gather(*tasks)
    return dict(zip(paths, hashes))

# --- Fix 2: run_in_executor() for more control ---

def cpu_heavy_work(data: bytes) -> str:
    """CPU-bound function -- needs a process pool."""
    return hashlib.pbkdf2_hmac(
        "sha256", data, b"salt", iterations=100_000
    ).hex()

async def run_with_executor():
    loop = asyncio.get_running_loop()

    # Thread pool for I/O-bound work
    with ThreadPoolExecutor(max_workers=4) as tpool:
        content = await loop.run_in_executor(
            tpool, read_large_file, "data.txt"
        )

    # Process pool for CPU-bound work (bypasses GIL)
    with ProcessPoolExecutor(max_workers=4) as ppool:
        result = await loop.run_in_executor(
            ppool, cpu_heavy_work, b"secret"
        )

    return content, result

# --- Practical pattern: async wrapper around blocking library ---

class AsyncFileProcessor:
    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)

    async def read(self, path: str) -> str:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self._executor, read_large_file, path
        )

    async def hash(self, path: str) -> str:
        return await asyncio.to_thread(compute_file_hash, path)

    def shutdown(self):
        self._executor.shutdown(wait=True)

async def main():
    processor = AsyncFileProcessor()
    try:
        content = await processor.read("example.txt")
        file_hash = await processor.hash("example.txt")
        print(f"Hash: {file_hash}")
    finally:
        processor.shutdown()

asyncio.run(main())
```

Rules of thumb:
- `asyncio.to_thread()` -- simplest option for I/O-bound blocking calls
- `ThreadPoolExecutor` -- I/O-bound work needing pool size control
- `ProcessPoolExecutor` -- CPU-bound work (bypasses GIL)
- Never call `time.sleep()`, blocking `requests.get()`, or heavy CPU work directly in async code'''
    },
    {
        "instruction": r'''Explain the Python asyncio event loop lifecycle: how asyncio.run() works, what happens with asyncio.get_event_loop(), and how to properly manage the loop.''',
        "output": r'''The event loop is the core scheduler that drives all async code. Here is how it works:

```python
import asyncio
import signal
from typing import Any

# ============================================================
# asyncio.run() -- the standard way (Python 3.7+)
# ============================================================

async def my_app():
    print("App running")
    await asyncio.sleep(1)
    return "done"

# asyncio.run() does three things:
# 1. Creates a NEW event loop
# 2. Runs the coroutine to completion
# 3. Closes the loop and cleans up pending tasks
result = asyncio.run(my_app())

# ============================================================
# What asyncio.run() does internally (simplified)
# ============================================================

def manual_run(coro):
    """Roughly what asyncio.run() does under the hood."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        # Cancel all remaining tasks
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        # Let cancellations propagate
        if pending:
            loop.run_until_complete(
                asyncio.gather(*pending, return_exceptions=True)
            )
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close()

# ============================================================
# get_event_loop() -- only inside a running loop
# ============================================================

async def inside_coroutine():
    # Safe: there IS a running loop
    loop = asyncio.get_running_loop()
    print(f"Loop running: {loop.is_running()}")  # True

    # Schedule a callback on the loop
    loop.call_later(1.0, lambda: print("delayed callback"))
    await asyncio.sleep(1.5)

# ============================================================
# Graceful shutdown pattern
# ============================================================

async def worker(name: str):
    try:
        while True:
            print(f"[{name}] working...")
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        print(f"[{name}] cleaning up...")
        # Do cleanup here (close connections, flush buffers)
        raise  # Re-raise so the task is properly cancelled

async def app_with_shutdown():
    shutdown_event = asyncio.Event()

    def handle_signal():
        print("Shutdown signal received")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_signal)

    # Start workers
    tasks = [
        asyncio.create_task(worker(f"worker-{i}"))
        for i in range(3)
    ]

    # Wait for shutdown signal
    await shutdown_event.wait()

    # Cancel all workers
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    print("Clean shutdown complete")

# ============================================================
# Common mistakes
# ============================================================

# WRONG: calling asyncio.run() twice in the same thread
# asyncio.run(my_app())
# asyncio.run(my_app())  # Works, but creates a new loop each time

# WRONG: calling asyncio.run() from inside a running loop
# async def bad():
#     asyncio.run(other_coro())  # RuntimeError!

# RIGHT: use await or create_task inside a running loop
async def good():
    result = await my_app()  # Just await it
```

Key rules:
- Use `asyncio.run()` as the single entry point -- call it once at the top level
- Inside async code, use `asyncio.get_running_loop()` (not `get_event_loop()`)
- Always handle `CancelledError` in long-running tasks for clean shutdown
- Never nest `asyncio.run()` calls -- use `await` instead'''
    },
]
