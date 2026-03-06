"""Thinking-trace pairs: async error handling patterns."""

PAIRS = [
    (
        "thinking/error-handling",
        r'''My async Python application has unhandled exceptions in tasks that silently disappear. I create tasks with asyncio.create_task() but never see the errors. How do I ensure no async exceptions are lost?''',
        r'''<think>
When you create a task with asyncio.create_task() and never await it or retrieve its result, any exception raised in that task is silently ignored (with a warning in Python 3.8+). This is one of the most common async bugs.

The fixes are:
1. Always store task references and handle results
2. Use task groups (Python 3.11+)
3. Set a global exception handler
4. Add done callbacks to tasks
</think>

Tasks created with `asyncio.create_task()` silently swallow exceptions if the task result is never retrieved. Here is how to prevent lost exceptions:

```python
import asyncio
import logging
import traceback
import sys
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================
# THE PROBLEM: Fire-and-forget tasks lose exceptions
# ============================================================

async def risky_task():
    await asyncio.sleep(1)
    raise ValueError("Something went wrong!")

async def main_bad():
    # BAD: Task exception is silently swallowed!
    asyncio.create_task(risky_task())
    # The task runs in the background, raises ValueError,
    # but nobody ever retrieves the result.
    # Python logs: "Task exception was never retrieved"
    await asyncio.sleep(5)

# ============================================================
# FIX 1: Add done callbacks to every task
# ============================================================

def handle_task_exception(task: asyncio.Task):
    """Callback that logs exceptions from completed tasks."""
    if task.cancelled():
        return
    exception = task.exception()
    if exception:
        logger.error(
            "Unhandled exception in task %s: %s\n%s",
            task.get_name(),
            exception,
            "".join(traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )),
        )

def create_tracked_task(coro, name: Optional[str] = None) -> asyncio.Task:
    """Create a task with automatic exception logging."""
    task = asyncio.create_task(coro, name=name)
    task.add_done_callback(handle_task_exception)
    return task

async def main_fix1():
    # Tasks now log their exceptions automatically
    create_tracked_task(risky_task(), name="risky")
    await asyncio.sleep(5)

# ============================================================
# FIX 2: Use TaskGroup (Python 3.11+) - RECOMMENDED
# ============================================================

async def main_fix2():
    try:
        async with asyncio.TaskGroup() as tg:
            tg.create_task(risky_task())
            tg.create_task(asyncio.sleep(5))
            # If any task fails, ALL tasks are cancelled
            # and the exception is raised as ExceptionGroup
    except* ValueError as eg:
        for exc in eg.exceptions:
            logger.error("Task failed: %s", exc)

# ============================================================
# FIX 3: Set global exception handler on the event loop
# ============================================================

def global_exception_handler(loop, context):
    """Handle exceptions that escape tasks and callbacks."""
    exception = context.get("exception")
    message = context.get("message", "Unhandled exception")

    if exception:
        logger.error(
            "Unhandled async exception: %s\n%s",
            message,
            "".join(traceback.format_exception(
                type(exception), exception, exception.__traceback__
            )),
        )
    else:
        logger.error("Unhandled async error: %s", message)

# Install the handler
loop = asyncio.get_event_loop()
loop.set_exception_handler(global_exception_handler)

# ============================================================
# FIX 4: Task manager that tracks all tasks
# ============================================================

class TaskManager:
    """Manage background tasks with proper error handling."""

    def __init__(self):
        self._tasks: set[asyncio.Task] = set()
        self._error_count = 0

    def create_task(
        self,
        coro,
        name: Optional[str] = None,
        on_error: Optional[callable] = None,
    ) -> asyncio.Task:
        """Create a tracked task."""
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(
            lambda t: self._on_task_done(t, on_error)
        )
        return task

    def _on_task_done(self, task: asyncio.Task, on_error=None):
        self._tasks.discard(task)

        if task.cancelled():
            logger.debug("Task %s was cancelled", task.get_name())
            return

        exception = task.exception()
        if exception:
            self._error_count += 1
            logger.error(
                "Task %s failed (%d total errors): %s",
                task.get_name(),
                self._error_count,
                exception,
                exc_info=exception,
            )
            if on_error:
                try:
                    on_error(exception)
                except Exception as e:
                    logger.error("Error in error handler: %s", e)

    async def cancel_all(self):
        """Cancel all running tasks."""
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

    @property
    def active_count(self) -> int:
        return len(self._tasks)

    @property
    def stats(self) -> dict:
        return {
            "active_tasks": self.active_count,
            "total_errors": self._error_count,
        }


# Usage:
task_mgr = TaskManager()

async def main_fix4():
    task_mgr.create_task(
        risky_task(),
        name="background-work",
        on_error=lambda e: alert_ops("Task failed: " + str(e)),
    )
    await asyncio.sleep(5)
    print(task_mgr.stats)

# ============================================================
# FIX 5: Async context manager for scoped tasks
# ============================================================

class ScopedTasks:
    """Tasks that are automatically cancelled when scope exits."""

    def __init__(self):
        self._tasks = set()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        # Cancel all tasks when leaving scope
        for task in self._tasks:
            if not task.done():
                task.cancel()
        # Wait for all tasks to finish
        if self._tasks:
            results = await asyncio.gather(
                *self._tasks, return_exceptions=True
            )
            for result in results:
                if isinstance(result, Exception) and not isinstance(
                    result, asyncio.CancelledError
                ):
                    logger.error("Task error during cleanup: %s", result)
        self._tasks.clear()
        return False  # Do not suppress exceptions

    def create_task(self, coro, name=None):
        task = asyncio.create_task(coro, name=name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task


async def handle_request():
    async with ScopedTasks() as tasks:
        # These tasks are automatically cancelled if the request fails
        tasks.create_task(fetch_data("source1"))
        tasks.create_task(fetch_data("source2"))
        await asyncio.sleep(10)
    # All tasks cleaned up here, even on exception
```

**Async exception handling rules:**
1. Never fire-and-forget with `asyncio.create_task()` -- always track or await
2. Use `TaskGroup` (Python 3.11+) for structured concurrency
3. Set a global exception handler on the event loop as a safety net
4. Add `done_callback` to every task for logging
5. Use scoped task managers that cancel tasks on scope exit''',
    ),
    (
        "thinking/error-handling",
        r'''How do I handle task group exceptions in Python 3.11+ when I want some tasks to be allowed to fail while others are critical? TaskGroup cancels all tasks when any one fails, but I want partial failure tolerance.''',
        r'''<think>
asyncio.TaskGroup has an all-or-nothing approach: if any task fails, all other tasks are cancelled and an ExceptionGroup is raised. This is good for operations that must all succeed, but bad for operations where some tasks are optional.

Solutions:
1. Wrap non-critical tasks in try/except so they never raise
2. Use asyncio.gather with return_exceptions=True for mixed criticality
3. Create separate TaskGroups for critical vs non-critical tasks
4. Build a custom task group that handles partial failures
</think>

`asyncio.TaskGroup` cancels all tasks on any failure. For partial failure tolerance, you need different strategies for critical vs non-critical tasks:

```python
import asyncio
import logging
from typing import Any, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)

# ============================================================
# PROBLEM: TaskGroup is all-or-nothing
# ============================================================

async def critical_task():
    """Must succeed."""
    await asyncio.sleep(1)
    return "critical result"

async def optional_task():
    """May fail without breaking the operation."""
    await asyncio.sleep(0.5)
    raise ConnectionError("Optional service down")

async def all_or_nothing():
    """TaskGroup cancels critical_task when optional_task fails!"""
    async with asyncio.TaskGroup() as tg:
        t1 = tg.create_task(critical_task())    # Gets cancelled!
        t2 = tg.create_task(optional_task())     # Fails
    # ExceptionGroup raised, t1 never completes

# ============================================================
# FIX 1: Wrap optional tasks to never propagate exceptions
# ============================================================

async def safe_optional(coro, fallback=None, name="task"):
    """Wrap a coroutine so it returns fallback on failure."""
    try:
        return await coro
    except asyncio.CancelledError:
        raise  # Always let cancellation propagate
    except Exception as e:
        logger.warning("Optional task '%s' failed: %s", name, e)
        return fallback

async def mixed_criticality_v1():
    async with asyncio.TaskGroup() as tg:
        # Critical tasks: not wrapped (failure cancels everything)
        t_critical = tg.create_task(critical_task())

        # Optional tasks: wrapped (failure returns fallback)
        t_optional = tg.create_task(
            safe_optional(optional_task(), fallback=None, name="optional")
        )

    # critical_task completed, optional_task returned fallback
    print(t_critical.result())    # "critical result"
    print(t_optional.result())    # None (fallback)

# ============================================================
# FIX 2: asyncio.gather with return_exceptions
# ============================================================

async def mixed_criticality_v2():
    """Use gather for tasks where some can fail."""
    results = await asyncio.gather(
        critical_task(),
        optional_task(),
        return_exceptions=True,  # Exceptions become return values
    )

    critical_result = results[0]
    optional_result = results[1]

    # Check each result
    if isinstance(critical_result, Exception):
        raise critical_result  # Re-raise critical failures

    if isinstance(optional_result, Exception):
        logger.warning("Optional task failed: %s", optional_result)
        optional_result = None  # Use fallback

    return {
        "critical": critical_result,
        "optional": optional_result,
    }

# ============================================================
# FIX 3: Custom resilient task group
# ============================================================

class TaskPriority(Enum):
    CRITICAL = "critical"     # Failure stops everything
    REQUIRED = "required"     # Must succeed, but others continue
    OPTIONAL = "optional"     # Can fail silently


@dataclass
class TaskResult:
    name: str
    priority: TaskPriority
    value: Any = None
    error: Optional[Exception] = None

    @property
    def succeeded(self) -> bool:
        return self.error is None


class ResilientTaskGroup:
    """Task group with configurable failure handling per task."""

    def __init__(self):
        self._tasks: list[tuple[str, TaskPriority, asyncio.Task]] = []
        self._results: list[TaskResult] = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            # Cancel all pending tasks on error
            for name, priority, task in self._tasks:
                if not task.done():
                    task.cancel()
            return False

        # Wait for all tasks
        for name, priority, task in self._tasks:
            try:
                value = await task
                self._results.append(TaskResult(
                    name=name, priority=priority, value=value,
                ))
            except asyncio.CancelledError:
                self._results.append(TaskResult(
                    name=name, priority=priority,
                    error=asyncio.CancelledError(),
                ))
            except Exception as e:
                self._results.append(TaskResult(
                    name=name, priority=priority, error=e,
                ))

                if priority == TaskPriority.CRITICAL:
                    # Cancel remaining tasks and raise
                    for n, p, t in self._tasks:
                        if not t.done():
                            t.cancel()
                    raise

        # Check required tasks
        required_failures = [
            r for r in self._results
            if r.priority == TaskPriority.REQUIRED and r.error
        ]
        if required_failures:
            errors = [r.error for r in required_failures]
            raise ExceptionGroup(
                "Required tasks failed",
                errors,
            )

        return False

    def create_task(
        self,
        coro,
        name: str,
        priority: TaskPriority = TaskPriority.REQUIRED,
    ):
        task = asyncio.create_task(coro, name=name)
        self._tasks.append((name, priority, task))
        return task

    @property
    def results(self) -> dict[str, TaskResult]:
        return {r.name: r for r in self._results}


# Usage:
async def process_order(order_id: str):
    async with ResilientTaskGroup() as group:
        # Must succeed -- failure cancels everything
        group.create_task(
            validate_payment(order_id),
            name="payment",
            priority=TaskPriority.CRITICAL,
        )

        # Must succeed -- but other tasks continue on failure
        group.create_task(
            reserve_inventory(order_id),
            name="inventory",
            priority=TaskPriority.REQUIRED,
        )

        # Nice to have -- failure is logged but ignored
        group.create_task(
            send_notification(order_id),
            name="notification",
            priority=TaskPriority.OPTIONAL,
        )

        group.create_task(
            update_analytics(order_id),
            name="analytics",
            priority=TaskPriority.OPTIONAL,
        )

    # Access results
    results = group.results
    print(f"Payment: {results['payment'].value}")
    print(f"Inventory: {results['inventory'].value}")

    # Optional results might have failed
    if results["notification"].error:
        logger.warning("Notification failed: %s", results["notification"].error)

# ============================================================
# FIX 4: Timeout with per-task deadlines
# ============================================================

async def with_per_task_timeout():
    """Different timeouts for different tasks."""
    async with asyncio.TaskGroup() as tg:
        # Critical task: longer timeout
        t1 = tg.create_task(
            asyncio.wait_for(critical_task(), timeout=30),
        )

        # Optional task: shorter timeout, wrapped for safety
        t2 = tg.create_task(
            safe_optional(
                asyncio.wait_for(optional_task(), timeout=5),
                fallback={"status": "skipped"},
                name="optional-with-timeout",
            ),
        )

    return t1.result(), t2.result()
```

**Task group patterns:**
1. **All critical**: Use `TaskGroup` -- any failure cancels all
2. **Mixed criticality**: Wrap optional tasks in `safe_optional()`
3. **Independent tasks**: Use `asyncio.gather(return_exceptions=True)`
4. **Custom logic**: Use `ResilientTaskGroup` with priority levels
5. Always let `CancelledError` propagate (never catch it in optional wrappers)''',
    ),
    (
        "thinking/error-handling",
        r'''How do I properly handle cancellation in async Python? When a task is cancelled, I need to ensure resources are cleaned up, but CancelledError can interrupt at any await point.''',
        r'''<think>
Cancellation in asyncio is tricky because:
1. CancelledError is raised at the next await point after cancel() is called
2. It can interrupt any await, including in cleanup code
3. In Python 3.9+, CancelledError inherits from BaseException, not Exception
4. You should almost never suppress CancelledError
5. Resources must be cleaned up even during cancellation

Proper patterns:
1. Use try/finally for cleanup (works with cancellation)
2. Shield critical sections from cancellation
3. Handle CancelledError explicitly when needed
4. Use asyncio.shield() for operations that must complete
</think>

Cancellation in asyncio requires careful resource management because `CancelledError` can interrupt at any `await` point:

```python
import asyncio
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# ============================================================
# THE PROBLEM: CancelledError interrupts at any await
# ============================================================

async def unsafe_task():
    conn = await connect_to_db()  # CancelledError could hit here
    try:
        await conn.execute("BEGIN")  # or here
        result = await conn.execute("INSERT INTO ...")  # or here
        await conn.execute("COMMIT")  # or here
    except Exception:
        await conn.execute("ROLLBACK")  # or here!
    finally:
        await conn.close()  # or even here!

# If CancelledError hits during execute(), the connection
# might be left in an inconsistent state.

# ============================================================
# FIX 1: Use try/finally with shielded cleanup
# ============================================================

async def safe_db_operation():
    """Database operation with cancellation-safe cleanup."""
    conn = await connect_to_db()
    try:
        await conn.execute("BEGIN")
        result = await conn.execute("INSERT INTO orders ...")
        await conn.execute("COMMIT")
        return result
    except asyncio.CancelledError:
        # Explicitly handle cancellation
        logger.info("DB operation cancelled, rolling back")
        # Shield the rollback from cancellation
        try:
            await asyncio.shield(conn.execute("ROLLBACK"))
        except asyncio.CancelledError:
            # shield re-raises CancelledError after the shielded
            # operation completes. We catch and re-raise after cleanup.
            pass
        raise  # ALWAYS re-raise CancelledError
    except Exception as e:
        logger.error("DB operation failed: %s", e)
        await conn.execute("ROLLBACK")
        raise
    finally:
        # Shield the close operation
        try:
            await asyncio.shield(conn.close())
        except asyncio.CancelledError:
            pass


# ============================================================
# FIX 2: Cancellation-safe context manager
# ============================================================

@asynccontextmanager
async def managed_connection(pool):
    """Async context manager with cancellation-safe cleanup."""
    conn = await pool.acquire()
    try:
        yield conn
    except asyncio.CancelledError:
        logger.debug("Connection context cancelled")
        raise
    finally:
        # Ensure the connection is released even on cancellation
        # Use shield to prevent cancellation during release
        try:
            await asyncio.shield(pool.release(conn))
        except asyncio.CancelledError:
            # Connection was released, but we got cancelled again
            pass

# Usage:
async def query_with_timeout(pool, query, timeout=10):
    async with managed_connection(pool) as conn:
        try:
            return await asyncio.wait_for(
                conn.execute(query),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Query timed out after %ds", timeout)
            raise


# ============================================================
# FIX 3: Shield critical sections
# ============================================================

async def process_payment(payment_data):
    """Payment processing that must not be interrupted mid-charge."""

    # Phase 1: Preparation (cancellable)
    validated = await validate_payment(payment_data)

    # Phase 2: Charge (NOT cancellable -- must complete)
    try:
        result = await asyncio.shield(
            execute_charge(validated)
        )
    except asyncio.CancelledError:
        # The charge completed (shield ensured that),
        # but we got cancelled. Log the charge result
        # before propagating cancellation.
        logger.warning(
            "Payment cancelled after charge was initiated. "
            "Charge may have completed -- check payment gateway."
        )
        raise

    # Phase 3: Record (cancellable, but should try)
    try:
        await record_payment(result)
    except asyncio.CancelledError:
        # Try to record even during cancellation
        try:
            await asyncio.shield(record_payment(result))
        except asyncio.CancelledError:
            pass
        raise

    return result


# ============================================================
# FIX 4: Graceful shutdown with cancellation
# ============================================================

class GracefulWorker:
    """Worker that handles cancellation gracefully."""

    def __init__(self):
        self._running = True
        self._current_task = None

    async def run(self):
        """Main loop that responds to cancellation."""
        try:
            while self._running:
                task = await self._get_next_task()
                if task is None:
                    await asyncio.sleep(1)
                    continue

                self._current_task = task
                try:
                    await self._process_task(task)
                except asyncio.CancelledError:
                    # Clean up current task before stopping
                    logger.info("Worker cancelling current task: %s", task)
                    await self._rollback_task(task)
                    raise
                finally:
                    self._current_task = None

        except asyncio.CancelledError:
            logger.info("Worker shutting down gracefully")
            # Do not re-raise -- we handled it

    async def _process_task(self, task):
        """Process a single task."""
        logger.info("Processing: %s", task)
        await asyncio.sleep(2)  # Simulate work
        logger.info("Completed: %s", task)

    async def _rollback_task(self, task):
        """Roll back an incomplete task."""
        try:
            await asyncio.shield(self._mark_task_failed(task))
        except asyncio.CancelledError:
            pass

    async def _get_next_task(self):
        return None  # Placeholder

    async def _mark_task_failed(self, task):
        pass  # Placeholder


# Graceful shutdown:
async def main():
    worker = GracefulWorker()
    task = asyncio.create_task(worker.run())

    # Run for a while, then shut down
    await asyncio.sleep(10)

    # Cancel and wait for graceful shutdown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass  # Worker handled its own cleanup

    logger.info("Shutdown complete")


# ============================================================
# FIX 5: Timeout with proper cancellation propagation
# ============================================================

async def operation_with_timeout(coro, timeout, cleanup=None):
    """Run with timeout, ensuring cleanup happens."""
    task = asyncio.create_task(coro)
    try:
        return await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
    except asyncio.TimeoutError:
        # Timeout: cancel the actual task
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        # Run cleanup if provided
        if cleanup:
            try:
                await asyncio.shield(cleanup())
            except asyncio.CancelledError:
                pass
        raise
```

**Cancellation rules:**
1. **Never suppress CancelledError** unless you are the final handler
2. Use `asyncio.shield()` for operations that MUST complete (charge, commit, close)
3. `shield()` still raises CancelledError after the shielded operation finishes
4. Use `try/finally` for cleanup -- it runs even on cancellation
5. In Python 3.9+, CancelledError is a BaseException -- `except Exception` does NOT catch it
6. Always test cancellation paths -- they are the most commonly untested code paths''',
    ),
    (
        "thinking/error-handling",
        r'''How do I implement "error boundaries" in async Python similar to how React error boundaries work? I want to contain errors within a scope so they do not crash the entire application.''',
        r'''<think>
Error boundaries in React catch rendering errors in child components. In async Python, the equivalent is containing errors within a defined scope so they do not propagate to the main application loop.

This involves:
1. Try/except around task groups
2. Scoped error handlers
3. Fallback rendering/responses
4. Error recovery and retry
5. Nested error boundaries (outer catches what inner misses)
</think>

Error boundaries in async Python contain failures within a scope, providing fallbacks and preventing cascading crashes:

```python
import asyncio
import logging
import traceback
from typing import Any, Callable, Optional, TypeVar
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)
T = TypeVar("T")


@dataclass
class ErrorBoundaryResult:
    """Result from an error boundary execution."""
    value: Any = None
    error: Optional[Exception] = None
    fallback_used: bool = False
    boundary_name: str = ""

    @property
    def succeeded(self) -> bool:
        return self.error is None


class ErrorBoundary:
    """Async error boundary that contains failures within a scope."""

    def __init__(
        self,
        name: str,
        fallback: Optional[Callable] = None,
        on_error: Optional[Callable] = None,
        retries: int = 0,
        retry_delay: float = 1.0,
    ):
        self.name = name
        self.fallback = fallback
        self.on_error = on_error
        self.retries = retries
        self.retry_delay = retry_delay
        self._error_count = 0

    async def execute(self, coro) -> ErrorBoundaryResult:
        """Execute a coroutine within the error boundary."""
        last_error = None

        for attempt in range(self.retries + 1):
            try:
                result = await coro
                return ErrorBoundaryResult(
                    value=result,
                    boundary_name=self.name,
                )
            except asyncio.CancelledError:
                raise  # Never catch cancellation
            except Exception as e:
                last_error = e
                self._error_count += 1

                logger.error(
                    "Error boundary '%s' caught error (attempt %d/%d): %s",
                    self.name,
                    attempt + 1,
                    self.retries + 1,
                    e,
                )

                # Notify error handler
                if self.on_error:
                    try:
                        if asyncio.iscoroutinefunction(self.on_error):
                            await self.on_error(e, self.name, attempt)
                        else:
                            self.on_error(e, self.name, attempt)
                    except Exception as handler_error:
                        logger.error(
                            "Error handler failed: %s", handler_error
                        )

                # Retry if attempts remain
                if attempt < self.retries:
                    await asyncio.sleep(self.retry_delay * (attempt + 1))
                    continue

        # All retries exhausted -- use fallback
        if self.fallback:
            try:
                if asyncio.iscoroutinefunction(self.fallback):
                    fallback_value = await self.fallback()
                else:
                    fallback_value = self.fallback()

                return ErrorBoundaryResult(
                    value=fallback_value,
                    error=last_error,
                    fallback_used=True,
                    boundary_name=self.name,
                )
            except Exception as fallback_error:
                logger.error(
                    "Fallback for '%s' also failed: %s",
                    self.name, fallback_error,
                )

        return ErrorBoundaryResult(
            error=last_error,
            fallback_used=False,
            boundary_name=self.name,
        )


# ============================================================
# CONTEXT MANAGER VERSION
# ============================================================

@asynccontextmanager
async def error_boundary(
    name: str,
    fallback_value: Any = None,
    on_error: Optional[Callable] = None,
    suppress: bool = True,
):
    """Async context manager error boundary."""
    try:
        yield
    except asyncio.CancelledError:
        raise
    except Exception as e:
        logger.error(
            "Error boundary '%s': %s\n%s",
            name, e, traceback.format_exc(),
        )
        if on_error:
            try:
                if asyncio.iscoroutinefunction(on_error):
                    await on_error(e)
                else:
                    on_error(e)
            except Exception:
                pass

        if not suppress:
            raise


# ============================================================
# USAGE: Nested error boundaries for a web application
# ============================================================

async def render_page(user_id: str) -> dict:
    """Render a page with nested error boundaries."""
    page = {"status": "ok", "sections": {}}

    # Header section: critical -- if it fails, show error page
    header_boundary = ErrorBoundary(
        name="header",
        fallback=lambda: {"user": "Guest", "nav": []},
        retries=1,
    )
    header_result = await header_boundary.execute(
        fetch_header_data(user_id)
    )
    page["sections"]["header"] = header_result.value
    if header_result.fallback_used:
        page["degraded"] = True

    # Main content: critical -- fail the whole page if broken
    try:
        page["sections"]["content"] = await fetch_main_content(user_id)
    except Exception as e:
        logger.error("Main content failed: %s", e)
        return {"status": "error", "message": "Page could not be loaded"}

    # Sidebar: optional -- show empty if broken
    sidebar_boundary = ErrorBoundary(
        name="sidebar",
        fallback=lambda: {"widgets": []},
        on_error=lambda e, n, a: logger.warning("Sidebar failed: %s", e),
    )
    sidebar_result = await sidebar_boundary.execute(
        fetch_sidebar_data(user_id)
    )
    page["sections"]["sidebar"] = sidebar_result.value

    # Recommendations: optional, low priority
    async with error_boundary("recommendations", fallback_value=[]):
        page["sections"]["recommendations"] = (
            await fetch_recommendations(user_id)
        )

    # Analytics: fire and forget, never block the page
    async with error_boundary("analytics", suppress=True):
        await track_page_view(user_id)

    return page


# ============================================================
# NESTED ERROR BOUNDARIES
# ============================================================

async def process_batch_with_boundaries(items: list) -> dict:
    """Process a batch with per-item error boundaries."""
    results = {"succeeded": [], "failed": []}

    for item in items:
        # Each item gets its own error boundary
        boundary = ErrorBoundary(
            name=f"item-{item['id']}",
            retries=2,
            retry_delay=0.5,
        )
        result = await boundary.execute(process_single_item(item))

        if result.succeeded:
            results["succeeded"].append({
                "id": item["id"],
                "result": result.value,
            })
        else:
            results["failed"].append({
                "id": item["id"],
                "error": str(result.error),
                "retried": boundary.retries > 0,
            })

    return results

async def process_single_item(item):
    """Process one item -- may fail."""
    await asyncio.sleep(0.1)
    if item.get("bad"):
        raise ValueError(f"Item {item['id']} is invalid")
    return {"processed": True}

# ============================================================
# COMPOSING BOUNDARIES
# ============================================================

async def resilient_service_call():
    """Compose multiple error boundaries."""

    # Outer boundary: catches anything the inner boundaries miss
    outer = ErrorBoundary(
        name="service-call",
        fallback=lambda: {"status": "degraded"},
        on_error=lambda e, n, a: alert_team(f"Service degraded: {e}"),
    )

    async def inner_logic():
        # Inner boundary: handles specific failures
        async with error_boundary("cache-lookup", suppress=True):
            cached = await cache.get("key")
            if cached:
                return cached

        # Try primary source
        primary = ErrorBoundary(
            name="primary-api",
            retries=2,
        )
        result = await primary.execute(fetch_from_primary())
        if result.succeeded:
            await cache.set("key", result.value)
            return result.value

        # Try backup source
        return await fetch_from_backup()

    return await outer.execute(inner_logic())
```

**Error boundary design rules:**
1. **Critical sections**: Do not use boundaries -- let errors propagate
2. **Optional sections**: Use boundaries with fallbacks
3. **Fire-and-forget**: Use boundaries with `suppress=True`
4. **Nesting**: Outer boundaries catch what inner boundaries miss
5. **Never catch CancelledError** inside boundaries
6. **Always log** the error even when suppressing it''',
    ),
    (
        "thinking/error-handling",
        r'''How do I implement timeout with proper cleanup for async operations? I want to cancel timed-out operations AND clean up resources, but asyncio.wait_for cancels the task and cleanup code might not run.''',
        r'''<think>
asyncio.wait_for has a specific behavior:
1. It creates an internal task for the coroutine
2. On timeout, it cancels the task and raises TimeoutError
3. The cancelled task's finally blocks may or may not run completely
4. If the task is shielded, the underlying operation continues

The issue is that cleanup in the cancelled task might need async operations, and those might not complete if the task is being cancelled.

Solutions:
1. Use try/finally with shield in the task itself
2. Use asyncio.timeout() context manager (Python 3.11+) which is more predictable
3. Separate the timeout from the cleanup
</think>

`asyncio.wait_for` cancels the task on timeout, which can prevent cleanup. Here is how to ensure proper resource cleanup:

```python
import asyncio
import logging
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

# ============================================================
# PROBLEM: wait_for cancels the task, cleanup may not finish
# ============================================================

async def operation_with_cleanup():
    resource = await acquire_resource()
    try:
        result = await long_computation(resource)
        return result
    finally:
        # This might not complete if the task is cancelled!
        await resource.close()  # CancelledError interrupts here

# asyncio.wait_for(operation_with_cleanup(), timeout=5)
# If timeout fires during long_computation, resource.close()
# gets a CancelledError and the resource leaks.

# ============================================================
# FIX 1: Shield cleanup from cancellation
# ============================================================

async def operation_safe_cleanup():
    resource = await acquire_resource()
    try:
        result = await long_computation(resource)
        return result
    finally:
        # Shield cleanup from cancellation
        try:
            await asyncio.shield(resource.close())
        except asyncio.CancelledError:
            # Shield completed the close, but re-raised CancelledError
            # We catch it here so the original CancelledError propagates
            pass

# ============================================================
# FIX 2: Separate timeout from the operation (recommended)
# ============================================================

async def run_with_timeout_and_cleanup(timeout_seconds: float):
    """Run operation with timeout, guaranteeing cleanup."""
    resource = await acquire_resource()

    try:
        # Only timeout the computation, not the cleanup
        result = await asyncio.wait_for(
            long_computation(resource),
            timeout=timeout_seconds,
        )
        return result
    except asyncio.TimeoutError:
        logger.warning("Operation timed out after %ds", timeout_seconds)
        raise
    finally:
        # Cleanup runs outside the timeout scope
        # Give cleanup its own generous timeout
        try:
            await asyncio.wait_for(resource.close(), timeout=5.0)
        except asyncio.TimeoutError:
            logger.error("Cleanup also timed out -- resource may leak")
        except Exception as e:
            logger.error("Cleanup failed: %s", e)

# ============================================================
# FIX 3: asyncio.timeout context manager (Python 3.11+)
# ============================================================

async def operation_with_timeout_cm():
    """Use asyncio.timeout for cleaner timeout handling."""
    resource = await acquire_resource()
    try:
        async with asyncio.timeout(10):
            # Only this block is subject to the timeout
            result = await long_computation(resource)
            return result
    except TimeoutError:
        logger.warning("Computation timed out")
        raise
    finally:
        # This runs after the timeout scope exits
        # It is NOT subject to the timeout
        await resource.close()

# ============================================================
# FIX 4: Timeout context manager with cleanup callback
# ============================================================

@asynccontextmanager
async def timeout_with_cleanup(
    seconds: float,
    cleanup_timeout: float = 5.0,
):
    """Timeout scope with guaranteed cleanup phase."""
    cleanup_callbacks = []

    class TimeoutScope:
        def add_cleanup(self, coro_func, *args, **kwargs):
            cleanup_callbacks.append((coro_func, args, kwargs))

    scope = TimeoutScope()

    try:
        async with asyncio.timeout(seconds):
            yield scope
    except (TimeoutError, asyncio.CancelledError):
        raise
    finally:
        # Run all cleanup callbacks with their own timeout
        for func, args, kwargs in cleanup_callbacks:
            try:
                await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=cleanup_timeout,
                )
            except asyncio.TimeoutError:
                logger.error("Cleanup timed out: %s", func.__name__)
            except Exception as e:
                logger.error("Cleanup failed: %s: %s", func.__name__, e)


# Usage:
async def complex_operation():
    async with timeout_with_cleanup(30, cleanup_timeout=5) as scope:
        db_conn = await connect_to_db()
        scope.add_cleanup(db_conn.close)

        cache_conn = await connect_to_cache()
        scope.add_cleanup(cache_conn.close)

        temp_file = await create_temp_file()
        scope.add_cleanup(delete_temp_file, temp_file)

        # Do the actual work
        result = await process_data(db_conn, cache_conn, temp_file)
        return result
    # All cleanup callbacks run even on timeout

# ============================================================
# FIX 5: Deadline propagation across async calls
# ============================================================

class Deadline:
    """Propagate a deadline across multiple async operations."""

    def __init__(self, timeout: float):
        self.deadline = asyncio.get_event_loop().time() + timeout

    @property
    def remaining(self) -> float:
        remaining = self.deadline - asyncio.get_event_loop().time()
        return max(0, remaining)

    @property
    def expired(self) -> bool:
        return self.remaining <= 0

    def check(self):
        if self.expired:
            raise TimeoutError("Deadline exceeded")

    @asynccontextmanager
    async def scope(self):
        """Create a timeout scope for the remaining deadline."""
        if self.expired:
            raise TimeoutError("Deadline already expired")
        async with asyncio.timeout(self.remaining):
            yield


async def multi_step_with_deadline():
    deadline = Deadline(timeout=30)

    # Step 1: uses some of the deadline
    async with deadline.scope():
        data = await fetch_data()

    # Step 2: uses remaining time
    deadline.check()
    async with deadline.scope():
        result = await process_data(data)

    # Step 3: remaining time
    deadline.check()
    async with deadline.scope():
        await save_result(result)

    return result
```

**Timeout + cleanup rules:**
1. Separate the timeout scope from the cleanup scope
2. Use `asyncio.shield()` for cleanup operations inside cancelled tasks
3. Give cleanup its own timeout (prevent cleanup from hanging forever)
4. Use `asyncio.timeout()` (3.11+) instead of `wait_for` when possible
5. Propagate deadlines across async call chains to enforce overall time limits
6. Always log when cleanup fails or times out -- resource leaks are silent bugs''',
    ),
]
