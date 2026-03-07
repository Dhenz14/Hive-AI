"""Async/concurrency training pairs: async debugging (all thinking)."""

pairs = [
    {
        "instruction": r'''My Python async application periodically freezes for a few seconds. I suspect something is blocking the event loop but I cannot figure out what. How do I detect and fix event loop blocking?''',
        "output": r'''<think>
Event loop blocking -- this is a common async debugging problem. The event loop is single-threaded, so any synchronous call that takes more than a few milliseconds will freeze ALL coroutines. Common culprits: synchronous file I/O, DNS resolution, CPU-heavy computation, synchronous HTTP libraries like requests, database drivers without async support.

How to detect it? asyncio has a debug mode that logs warnings when a coroutine takes too long. You enable it with asyncio.run(main(), debug=True) or PYTHONASYNCIODEBUG=1. The default threshold is 100ms but you can lower it with loop.slow_callback_duration.

But actually, I should also mention a more proactive approach: a watchdog task that periodically checks if the loop is responsive. If a simple sleep(0.1) takes 2 seconds wall-clock time, something blocked the loop for ~1.9s. This is a great production monitoring pattern.

For fixing it, the answer is always: move blocking work to a thread or process pool using asyncio.to_thread() or loop.run_in_executor().
</think>

Here is how to detect and fix event loop blocking:

```python
import asyncio
import time
import logging
import functools
from typing import Callable, Any

logger = logging.getLogger(__name__)

# ============================================================
# Detection method 1: asyncio debug mode
# ============================================================

async def app_with_debug():
    # This will log a warning because time.sleep blocks the loop
    time.sleep(0.5)  # BAD: blocks event loop
    await asyncio.sleep(0.1)

# Run with debug=True to see warnings about slow callbacks
# asyncio.run(app_with_debug(), debug=True)

# Or set the threshold lower:
# loop = asyncio.get_running_loop()
# loop.slow_callback_duration = 0.05  # warn if >50ms

# ============================================================
# Detection method 2: watchdog coroutine
# ============================================================

async def event_loop_watchdog(
    check_interval: float = 0.5,
    warn_threshold: float = 0.1,
):
    """Detect event loop blocking by measuring sleep accuracy."""
    while True:
        before = time.monotonic()
        await asyncio.sleep(check_interval)
        after = time.monotonic()

        actual_delay = after - before
        blocking_time = actual_delay - check_interval

        if blocking_time > warn_threshold:
            logger.warning(
                "Event loop was blocked for %.3fs "
                "(expected %.3fs sleep, got %.3fs)",
                blocking_time,
                check_interval,
                actual_delay,
            )

# ============================================================
# Detection method 3: monkey-patch to find the culprit
# ============================================================

def patch_blocking_calls():
    """Warn when common blocking calls are used in async context."""
    import io

    original_open = io.open

    @functools.wraps(original_open)
    def patched_open(*args, **kwargs):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            import traceback
            logger.warning(
                "Synchronous open() called inside async context!\n%s",
                "".join(traceback.format_stack()),
            )
        return original_open(*args, **kwargs)

    io.open = patched_open

# ============================================================
# Fixing: move blocking work to threads
# ============================================================

def blocking_dns_lookup(hostname: str) -> str:
    """Simulates a slow blocking call."""
    import socket
    return socket.gethostbyname(hostname)

def blocking_file_read(path: str) -> str:
    with open(path, "r") as f:
        return f.read()

async def fixed_handler():
    # WRONG: blocks the event loop
    # result = blocking_dns_lookup("example.com")

    # RIGHT: run in thread pool
    result = await asyncio.to_thread(
        blocking_dns_lookup, "example.com"
    )

    # RIGHT: file I/O in thread
    content = await asyncio.to_thread(
        blocking_file_read, "config.json"
    )
    return result, content

async def main():
    # Start watchdog as background task
    watchdog = asyncio.create_task(event_loop_watchdog())

    # Simulate a blocking call to trigger the watchdog
    await asyncio.sleep(0.1)
    time.sleep(1.0)  # This will trigger the watchdog warning
    await asyncio.sleep(1.0)

    watchdog.cancel()

asyncio.run(main(), debug=True)
```

Summary:
- Enable `debug=True` in development to catch blocking calls
- Use a watchdog coroutine in production for continuous monitoring
- Fix by moving blocking work to `asyncio.to_thread()` or `run_in_executor()`'''
    },
    {
        "instruction": r'''I have a deadlock in my async Python code. Two coroutines seem to be waiting on each other. How do I diagnose and fix async deadlocks?''',
        "output": r'''<think>
Async deadlocks are tricky. In traditional threading, deadlocks happen when two threads hold locks and each waits for the other. In asyncio, the analogous situation happens with:

1. Two coroutines waiting on each other via asyncio.Event or asyncio.Future
2. A queue.put() blocking because the queue is full, while the consumer is waiting on something the producer should provide
3. Awaiting a task that is waiting for the current task

Wait, actually there is a subtle difference. Since asyncio is single-threaded, you cannot have a classic lock-based deadlock in the same way. But you CAN have logical deadlocks where coroutines are waiting on conditions that will never be satisfied.

The most common async deadlock pattern I have seen: bounded queue where producer fills the queue and blocks on put(), but the consumer is in the same TaskGroup and has not started yet because the producer filled the queue synchronously before yielding.

Another common one: calling asyncio.run() or loop.run_until_complete() from inside a running event loop. That tries to run a nested loop which is not allowed and hangs.

For diagnosis: you can dump the state of all tasks, check what each is waiting on, and look for cycles.
</think>

Async deadlocks occur when coroutines wait on conditions that can never be satisfied. Here is how to diagnose and fix them:

```python
import asyncio
import sys
import traceback
from typing import Any

# ============================================================
# Deadlock pattern 1: Circular event waits
# ============================================================

async def deadlock_circular():
    event_a = asyncio.Event()
    event_b = asyncio.Event()

    async def task_1():
        await event_b.wait()  # waits for task_2
        event_a.set()         # signals task_2 (never reached)

    async def task_2():
        await event_a.wait()  # waits for task_1
        event_b.set()         # signals task_1 (never reached)

    # DEADLOCK: both tasks wait forever
    # await asyncio.gather(task_1(), task_2())

    # FIX: break the cycle -- one task must signal first
    async def task_1_fixed():
        event_a.set()         # signal first, then wait
        await event_b.wait()

    await asyncio.gather(task_1_fixed(), task_2())

# ============================================================
# Deadlock pattern 2: Full bounded queue
# ============================================================

async def deadlock_queue():
    queue: asyncio.Queue[int] = asyncio.Queue(maxsize=2)

    async def producer():
        for i in range(10):
            await queue.put(i)  # blocks when queue is full

    async def consumer():
        await asyncio.sleep(0)  # yield to let producer run first
        while True:
            item = await queue.get()
            await asyncio.sleep(0.1)
            queue.task_done()

    # DEADLOCK if consumer never starts because producer
    # fills queue before consumer gets a chance to run.
    # FIX: ensure consumer starts before producer fills queue
    consumer_task = asyncio.create_task(consumer())
    await producer()
    await queue.join()
    consumer_task.cancel()

# ============================================================
# Diagnosis: dump all task states
# ============================================================

def dump_async_tasks():
    """Print the state and stack of all running tasks."""
    tasks = asyncio.all_tasks()
    print(f"\n{'='*60}")
    print(f"ASYNC TASK DUMP: {len(tasks)} tasks")
    print(f"{'='*60}")
    for task in tasks:
        print(f"\nTask: {task.get_name()} [{task._state}]")
        # Get the coroutine stack
        frames = task.get_stack()
        for frame in frames:
            filename = frame.f_code.co_filename
            lineno = frame.f_lineno
            funcname = frame.f_code.co_name
            print(f"  File {filename}:{lineno} in {funcname}")

async def deadlock_detector(timeout: float = 10.0):
    """Detect potential deadlocks by monitoring task progress."""
    prev_stacks: dict[str, list] = {}

    for _ in range(int(timeout / 2)):
        await asyncio.sleep(2.0)
        current_stacks = {}
        for task in asyncio.all_tasks():
            name = task.get_name()
            frames = task.get_stack()
            stack_sig = [
                (f.f_code.co_filename, f.f_lineno)
                for f in frames
            ]
            current_stacks[name] = stack_sig

        # Check for tasks stuck in the same place
        for name, stack in current_stacks.items():
            if name in prev_stacks and stack == prev_stacks[name]:
                print(f"WARNING: Task {name} appears stuck!")
                dump_async_tasks()

        prev_stacks = current_stacks

# ============================================================
# Prevention: always use timeouts
# ============================================================

async def safe_wait_for_event(
    event: asyncio.Event,
    timeout: float = 5.0,
    label: str = "unknown",
) -> bool:
    """Wait for an event with a timeout to prevent deadlocks."""
    try:
        await asyncio.wait_for(event.wait(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        print(f"Potential deadlock: {label} timed out after {timeout}s")
        dump_async_tasks()
        return False

async def main():
    await deadlock_circular()
    await deadlock_queue()
    print("All deadlock examples resolved")

asyncio.run(main())
```

Prevention rules:
- Always use timeouts on waits (`asyncio.wait_for`, `asyncio.timeout`)
- Start consumers before producers when using bounded queues
- Avoid circular dependencies between events/futures
- Use `dump_async_tasks()` when debugging hangs'''
    },
    {
        "instruction": r'''My asyncio tasks keep silently disappearing. I create them with create_task() but exceptions are swallowed and some tasks just vanish. How do I track and debug task lifecycle issues?''',
        "output": r'''<think>
This is the classic "task leaking" problem. There are several related issues:

1. Fire-and-forget tasks -- create_task() returns a Task, but if you do not store a reference, the task can be garbage collected before it finishes (Python uses weak references internally for tasks). Wait, actually that changed -- since Python 3.12 or so, asyncio keeps a strong reference to tasks. But in earlier versions, this was a real problem.

Actually let me reconsider. The GC issue is: if you do `asyncio.create_task(coro())` without saving the return value, the Task object might be GC'd. asyncio does keep an internal set of tasks, but in some edge cases (especially with weak references), tasks could vanish. The official docs actually warn about this and recommend keeping a reference.

2. Exception swallowing -- if a task raises and nobody awaits it, the exception is lost. Python logs "Task exception was never retrieved" but only when the task is GC'd, which might be much later.

3. Task reference management -- you need to store task references somewhere and clean them up.

I should show a TaskTracker class that solves all of these problems.
</think>

Task lifecycle bugs come from three sources: lost references, unhandled exceptions, and missing cleanup. Here is how to fix all three:

```python
import asyncio
import logging
import weakref
from typing import Any, Coroutine

logger = logging.getLogger(__name__)

# ============================================================
# Problem 1: Task garbage collected before completion
# ============================================================

async def demo_task_gc():
    # BAD: no reference kept -- task may be GC'd!
    asyncio.create_task(some_work())

    # GOOD: keep a reference
    task = asyncio.create_task(some_work())
    await task

async def some_work():
    await asyncio.sleep(1)
    return "done"

# ============================================================
# Problem 2: Exceptions silently lost
# ============================================================

async def failing_work():
    await asyncio.sleep(0.1)
    raise RuntimeError("Something broke!")

async def demo_lost_exception():
    # BAD: exception silently lost
    asyncio.create_task(failing_work())
    await asyncio.sleep(2)
    # Python eventually logs:
    # "Task exception was never retrieved"
    # But this may appear much later or not at all

# ============================================================
# Solution: TaskTracker with lifecycle management
# ============================================================

class TaskTracker:
    """Track all tasks, log exceptions, prevent GC issues."""

    def __init__(self, name: str = "default"):
        self.name = name
        self._tasks: set[asyncio.Task] = set()
        self._completed: int = 0
        self._failed: int = 0

    def create_task(
        self,
        coro: Coroutine[Any, Any, Any],
        name: str | None = None,
    ) -> asyncio.Task:
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)  # strong reference prevents GC
        task.add_done_callback(self._on_task_done)
        return task

    def _on_task_done(self, task: asyncio.Task):
        self._tasks.discard(task)
        self._completed += 1

        if task.cancelled():
            logger.debug(
                "[%s] Task %s was cancelled",
                self.name, task.get_name(),
            )
            return

        exc = task.exception()
        if exc is not None:
            self._failed += 1
            logger.error(
                "[%s] Task %s failed with %s: %s",
                self.name,
                task.get_name(),
                type(exc).__name__,
                exc,
                exc_info=exc,
            )

    @property
    def active_count(self) -> int:
        return len(self._tasks)

    def status(self) -> dict[str, Any]:
        return {
            "active": self.active_count,
            "completed": self._completed,
            "failed": self._failed,
            "task_names": [t.get_name() for t in self._tasks],
        }

    async def cancel_all(self, timeout: float = 5.0):
        """Cancel all tracked tasks and wait for cleanup."""
        if not self._tasks:
            return

        logger.info(
            "[%s] Cancelling %d tasks", self.name, len(self._tasks)
        )
        for task in self._tasks:
            task.cancel()

        done, pending = await asyncio.wait(
            self._tasks, timeout=timeout
        )
        if pending:
            logger.warning(
                "[%s] %d tasks did not finish after cancel",
                self.name, len(pending),
            )

    async def wait_all(self, timeout: float | None = None):
        """Wait for all tracked tasks to complete."""
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=timeout)

# ============================================================
# Usage
# ============================================================

tracker = TaskTracker("my-app")

async def background_job(job_id: int):
    await asyncio.sleep(0.5)
    if job_id % 3 == 0:
        raise ValueError(f"Job {job_id} failed")
    return f"job-{job_id} done"

async def main():
    logging.basicConfig(level=logging.DEBUG)

    # Create tracked tasks
    for i in range(10):
        tracker.create_task(
            background_job(i),
            name=f"job-{i}",
        )

    print(f"Active tasks: {tracker.active_count}")

    # Wait for completion
    await tracker.wait_all(timeout=5.0)

    status = tracker.status()
    print(f"Completed: {status['completed']}")
    print(f"Failed: {status['failed']}")

    # Cleanup
    await tracker.cancel_all()

asyncio.run(main())
```

Key rules:
- Always store task references (use a set or a tracker)
- Add `done_callback` to every task to catch exceptions immediately
- Use `TaskGroup` when possible -- it handles all of this automatically
- In production, log task creation and completion for observability'''
    },
    {
        "instruction": r'''I have a complex async Python application where some coroutines are extremely slow but I cannot figure out which ones. How do I profile async code to find performance bottlenecks?''',
        "output": r'''<think>
Profiling async code is different from profiling sync code because:
1. Wall-clock time per coroutine includes time spent waiting (which is fine for async)
2. What you really want to know is: which coroutines take too long to yield back to the event loop, and which coroutines have excessive total runtime

Standard profilers like cProfile do not work well with async because they measure CPU time per function, not per-coroutine-resumption. You need tools that understand the event loop.

Options:
1. Manual instrumentation with decorators that track per-coroutine timing
2. asyncio debug mode (slow_callback_duration)
3. Third-party: aiomonitor, py-spy (sampling profiler that works with async)

Actually, the most practical approach is a combination: a timing decorator for development, and structured logging with timing for production. Let me show both.

I should also mention that sometimes the bottleneck is not a slow coroutine but too many coroutines competing. The event loop is single-threaded, so if you have 10000 coroutines all becoming ready at once, just iterating through them takes time.
</think>

Profiling async code requires measuring both wall-clock time and event loop blocking time. Here are practical techniques:

```python
import asyncio
import time
import functools
import logging
from typing import Any, Callable
from collections import defaultdict
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ============================================================
# Tool 1: Async timing decorator
# ============================================================

def async_profile(func):
    """Decorator to measure coroutine execution time."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        start_wall = time.monotonic()
        start_cpu = time.process_time()
        try:
            result = await func(*args, **kwargs)
            return result
        finally:
            wall_time = time.monotonic() - start_wall
            cpu_time = time.process_time() - start_cpu
            io_time = wall_time - cpu_time
            logger.info(
                "PROFILE %s: wall=%.3fs cpu=%.3fs io=%.3fs",
                func.__name__, wall_time, cpu_time, io_time,
            )
    return wrapper

@async_profile
async def fetch_user_data(user_id: int) -> dict:
    await asyncio.sleep(0.5)  # simulate I/O
    return {"id": user_id}

# ============================================================
# Tool 2: Coroutine profiler that tracks all tasks
# ============================================================

@dataclass
class CoroutineStats:
    name: str
    call_count: int = 0
    total_wall_time: float = 0.0
    max_wall_time: float = 0.0
    total_cpu_time: float = 0.0

class AsyncProfiler:
    """Profile all decorated coroutines."""

    def __init__(self):
        self.stats: dict[str, CoroutineStats] = defaultdict(
            lambda: CoroutineStats(name="unknown")
        )

    def track(self, func):
        name = func.__qualname__

        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start_wall = time.monotonic()
            start_cpu = time.process_time()
            try:
                return await func(*args, **kwargs)
            finally:
                wall = time.monotonic() - start_wall
                cpu = time.process_time() - start_cpu
                stats = self.stats[name]
                stats.name = name
                stats.call_count += 1
                stats.total_wall_time += wall
                stats.max_wall_time = max(stats.max_wall_time, wall)
                stats.total_cpu_time += cpu

        return wrapper

    def report(self) -> str:
        lines = [
            f"{'Function':<40} {'Calls':>6} {'Total':>8} "
            f"{'Max':>8} {'CPU':>8}"
        ]
        lines.append("-" * 76)
        for name, s in sorted(
            self.stats.items(),
            key=lambda x: x[1].total_wall_time,
            reverse=True,
        ):
            lines.append(
                f"{s.name:<40} {s.call_count:>6} "
                f"{s.total_wall_time:>7.3f}s "
                f"{s.max_wall_time:>7.3f}s "
                f"{s.total_cpu_time:>7.3f}s"
            )
        return "\n".join(lines)

# ============================================================
# Tool 3: Event loop lag monitor
# ============================================================

async def monitor_loop_lag(
    interval: float = 0.1,
    threshold: float = 0.05,
):
    """Continuously measure event loop responsiveness."""
    while True:
        t0 = time.monotonic()
        await asyncio.sleep(interval)
        lag = time.monotonic() - t0 - interval
        if lag > threshold:
            # Something blocked the loop
            logger.warning("Event loop lag: %.3fs", lag)

# ============================================================
# Usage example
# ============================================================

profiler = AsyncProfiler()

@profiler.track
async def fetch_from_db(query: str) -> list:
    await asyncio.sleep(0.2)
    return [{"id": 1}]

@profiler.track
async def call_external_api(url: str) -> dict:
    await asyncio.sleep(0.5)
    return {"status": "ok"}

@profiler.track
async def process_data(data: list) -> list:
    # CPU-bound -- this blocks the loop!
    result = []
    for i in range(100000):
        result.append(i * i)
    return result

async def main():
    monitor = asyncio.create_task(monitor_loop_lag())

    for _ in range(5):
        db_data = await fetch_from_db("SELECT * FROM users")
        api_data = await call_external_api("https://api.example.com")
        await process_data(db_data)

    monitor.cancel()
    print("\n" + profiler.report())

asyncio.run(main())
```

The profiler report shows which coroutines consume the most time, helping you find bottlenecks. High CPU time relative to wall time indicates blocking work that should be offloaded to a thread pool.'''
    },
    {
        "instruction": r'''How do I properly handle exception groups (ExceptionGroup) when using asyncio.TaskGroup? I keep getting unhandled ExceptionGroup errors that crash my application.''',
        "output": r'''<think>
ExceptionGroup handling is new in Python 3.11 and catches many people off guard. When a TaskGroup has multiple task failures, it raises an ExceptionGroup containing all the individual exceptions. You cannot catch this with a regular try/except -- you need except* syntax.

But there are subtleties. Let me think about the tricky cases:

1. If you use `except Exception` it will NOT catch ExceptionGroup (since 3.11, ExceptionGroup inherits from BaseException -- wait, no. Actually ExceptionGroup inherits from Exception. Let me check... Yes, ExceptionGroup IS an Exception subclass. So `except Exception` DOES catch it. But `except ValueError` does NOT catch an ExceptionGroup containing ValueErrors.

2. The `except*` syntax matches individual exceptions INSIDE the group. Multiple except* blocks can each handle different exception types from the same group.

3. You can nest ExceptionGroups, which gets complex.

4. If you want to handle ExceptionGroup in code that also needs to support Python < 3.11, you need the exceptiongroup backport.

Let me show the common patterns for handling these properly.
</think>

`ExceptionGroup` (Python 3.11+) bundles multiple exceptions from concurrent tasks. Here is how to handle them properly:

```python
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

# ============================================================
# The problem: TaskGroup raises ExceptionGroup
# ============================================================

async def task_a():
    await asyncio.sleep(0.1)
    raise ValueError("bad input in task A")

async def task_b():
    await asyncio.sleep(0.2)
    raise ConnectionError("network failure in task B")

async def task_c():
    await asyncio.sleep(0.3)
    return "success"

async def naive_handling():
    # WRONG: except Exception catches ExceptionGroup as a whole
    # but you cannot inspect individual errors easily
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(task_a())
            tg.create_task(task_b())
            tg.create_task(task_c())
    except Exception as e:
        # e is an ExceptionGroup -- awkward to inspect
        print(f"Got: {type(e).__name__}: {e}")

# ============================================================
# Correct: use except* to match individual exception types
# ============================================================

async def proper_handling():
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(task_a())
            tg.create_task(task_b())
            tg.create_task(task_c())
    except* ValueError as eg:
        # eg is an ExceptionGroup containing only ValueErrors
        for exc in eg.exceptions:
            logger.warning("Validation error: %s", exc)
    except* ConnectionError as eg:
        # This block also runs (from the same ExceptionGroup)
        for exc in eg.exceptions:
            logger.error("Connection error: %s", exc)

# ============================================================
# Pattern: convert ExceptionGroup to single exception
# ============================================================

class AggregateError(Exception):
    """Wraps multiple errors into one for simpler handling."""
    def __init__(self, errors: list[Exception]):
        self.errors = errors
        messages = [f"{type(e).__name__}: {e}" for e in errors]
        super().__init__(
            f"{len(errors)} errors: {'; '.join(messages)}"
        )

async def simplified_error_handling():
    """Collapse ExceptionGroup into a single exception."""
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(task_a())
            tg.create_task(task_b())
    except ExceptionGroup as eg:
        # Flatten nested groups
        flat_errors = []
        def flatten(group):
            for exc in group.exceptions:
                if isinstance(exc, ExceptionGroup):
                    flatten(exc)
                else:
                    flat_errors.append(exc)
        flatten(eg)
        raise AggregateError(flat_errors) from eg

# ============================================================
# Pattern: partial failure tolerance
# ============================================================

async def fetch_with_fallback(source: str) -> dict[str, Any]:
    await asyncio.sleep(0.1)
    if source == "flaky":
        raise ConnectionError(f"{source} is down")
    return {"source": source, "data": "ok"}

async def tolerant_fetch(sources: list[str]) -> list[dict]:
    """Fetch from multiple sources, tolerate partial failures."""
    results: list[dict[str, Any]] = []
    errors: list[Exception] = []

    # Use individual try/except per task instead of TaskGroup
    # when you want partial failure tolerance
    async def safe_fetch(source: str):
        try:
            result = await fetch_with_fallback(source)
            results.append(result)
        except Exception as e:
            errors.append(e)

    async with asyncio.TaskGroup() as tg:
        for source in sources:
            tg.create_task(safe_fetch(source))

    # All tasks succeed (errors caught inside safe_fetch)
    logger.info(
        "Fetched %d/%d sources (%d errors)",
        len(results), len(sources), len(errors),
    )
    return results

async def main():
    logging.basicConfig(level=logging.INFO)

    # Proper except* handling
    await proper_handling()

    # Partial failure tolerance
    results = await tolerant_fetch(
        ["api", "flaky", "cache", "flaky", "db"]
    )
    print(f"Got {len(results)} results")

asyncio.run(main())
```

Key takeaways:
- Use `except*` to match specific exception types inside the group
- Multiple `except*` blocks can each handle different types from the same group
- Wrap per-task errors in try/except inside the task for partial failure tolerance
- `ExceptionGroup` can be nested -- use recursive flattening when needed'''
    },
]
