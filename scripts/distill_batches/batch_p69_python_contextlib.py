"""Python — contextlib, decorators, and advanced patterns."""

PAIRS = [
    (
        "python/contextlib-patterns",
        "Show contextlib patterns: context managers, ExitStack, suppress, redirect, and async context managers.",
        '''contextlib patterns:

```python
from contextlib import (
    contextmanager, asynccontextmanager,
    ExitStack, AsyncExitStack,
    suppress, redirect_stdout, redirect_stderr,
    closing, nullcontext,
)
import asyncio
import time
import logging
import sys
from io import StringIO
from typing import Iterator, AsyncIterator, Any

logger = logging.getLogger(__name__)


# --- Custom context managers with @contextmanager ---

@contextmanager
def timer(label: str = "Operation") -> Iterator[dict]:
    """Time a block of code."""
    stats = {"label": label, "elapsed": 0}
    start = time.perf_counter()
    try:
        yield stats
    finally:
        stats["elapsed"] = time.perf_counter() - start
        logger.info("%s took %.3fs", label, stats["elapsed"])

# with timer("database query") as t:
#     result = db.query(...)
# print(t["elapsed"])  # 0.123


@contextmanager
def temporary_env(**env_vars) -> Iterator[None]:
    """Temporarily set environment variables."""
    import os
    old = {}
    for key, value in env_vars.items():
        old[key] = os.environ.get(key)
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

# with temporary_env(DATABASE_URL="sqlite:///:memory:", DEBUG="true"):
#     run_tests()


@contextmanager
def file_transaction(path: str, mode: str = "w") -> Iterator:
    """Write to temp file, then atomic rename on success."""
    import tempfile
    import os
    from pathlib import Path

    dir_path = str(Path(path).parent)
    fd, tmp_path = tempfile.mkstemp(dir=dir_path)
    try:
        with os.fdopen(fd, mode) as f:
            yield f
        os.replace(tmp_path, path)  # Atomic rename
    except Exception:
        os.unlink(tmp_path)
        raise

# with file_transaction("config.json") as f:
#     json.dump(config, f)
# File only appears if write succeeds


# --- Async context manager ---

@asynccontextmanager
async def db_transaction(pool) -> AsyncIterator:
    """Database transaction with auto-rollback on error."""
    conn = await pool.acquire()
    tx = conn.transaction()
    await tx.start()
    try:
        yield conn
        await tx.commit()
    except Exception:
        await tx.rollback()
        raise
    finally:
        await pool.release(conn)

# async with db_transaction(pool) as conn:
#     await conn.execute("INSERT INTO ...")
#     await conn.execute("UPDATE ...")
# Both execute or neither does


# --- ExitStack for dynamic resource management ---

def process_multiple_files(paths: list[str]) -> list[str]:
    """Open variable number of files safely."""
    results = []
    with ExitStack() as stack:
        files = [
            stack.enter_context(open(path))
            for path in paths
        ]
        # All files open, all will be closed on exit
        for f in files:
            results.append(f.read())
    return results


async def setup_services(configs: list[dict]):
    """Dynamically initialize multiple async services."""
    async with AsyncExitStack() as stack:
        services = {}
        for config in configs:
            service = await create_service(config)
            await stack.enter_async_context(service)
            services[config["name"]] = service

        # All services active, all will be cleaned up
        yield services


# --- suppress (ignore specific exceptions) ---

# Instead of try/except/pass:
with suppress(FileNotFoundError):
    Path("temp.txt").unlink()

# Instead of:
# try:
#     Path("temp.txt").unlink()
# except FileNotFoundError:
#     pass

# Multiple exceptions:
with suppress(KeyError, IndexError):
    value = data["key"][0]


# --- redirect_stdout for capturing output ---

def capture_output(fn, *args, **kwargs) -> tuple[Any, str]:
    """Run function and capture its stdout."""
    buffer = StringIO()
    with redirect_stdout(buffer):
        result = fn(*args, **kwargs)
    return result, buffer.getvalue()

# result, output = capture_output(print, "hello")
# output == "hello\\n"


# --- nullcontext (conditional context managers) ---

def process(data, use_lock: bool = False):
    """Optionally use a lock."""
    import threading
    lock = threading.Lock()

    cm = lock if use_lock else nullcontext()
    with cm:
        # Process data (with or without lock)
        return transform(data)


# --- Composing context managers ---

@contextmanager
def managed_service(name: str, debug: bool = False):
    """Composed context manager with setup/teardown."""
    logger.info("Starting %s", name)

    with ExitStack() as stack:
        if debug:
            stack.enter_context(timer(name))

        db = stack.enter_context(get_db_connection())
        cache = stack.enter_context(get_cache_connection())

        service = Service(name, db=db, cache=cache)
        try:
            yield service
        finally:
            logger.info("Stopping %s", name)
```

contextlib patterns:
1. **`@contextmanager`** — generator-based context managers (yield = body runs)
2. **`ExitStack`** — manage variable number of resources dynamically
3. **`suppress()`** — cleaner than empty try/except for expected exceptions
4. **Atomic file writes** — write to temp, then `os.replace()` on success
5. **`nullcontext()`** — no-op context manager for conditional resource use'''
    ),
    (
        "python/decorator-patterns",
        "Show Python decorator patterns: with arguments, class decorators, stacking, and preserving signatures.",
        '''Python decorator patterns:

```python
import functools
import time
import asyncio
import logging
from typing import Callable, TypeVar, ParamSpec, Any, overload
from collections import defaultdict

P = ParamSpec("P")
R = TypeVar("R")
logger = logging.getLogger(__name__)


# --- Basic decorator with arguments ---

def retry(max_attempts: int = 3, delay: float = 1.0,
          exceptions: tuple = (Exception,)):
    """Retry decorator with configurable attempts and delay."""
    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except exceptions as e:
                    if attempt == max_attempts - 1:
                        raise
                    logger.warning(
                        "%s attempt %d failed: %s",
                        fn.__name__, attempt + 1, e
                    )
                    time.sleep(delay * (2 ** attempt))
            raise RuntimeError("Unreachable")
        return wrapper
    return decorator

@retry(max_attempts=3, delay=0.5, exceptions=(ConnectionError, TimeoutError))
def fetch_data(url: str) -> dict:
    pass


# --- Decorator that works with and without arguments ---

def log_calls(_fn=None, *, level: str = "INFO"):
    """Use as @log_calls or @log_calls(level='DEBUG')."""
    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            log_fn = getattr(logger, level.lower())
            log_fn("Calling %s", fn.__name__)
            result = fn(*args, **kwargs)
            log_fn("%s returned %r", fn.__name__, result)
            return result
        return wrapper

    if _fn is not None:
        return decorator(_fn)
    return decorator

@log_calls  # Without arguments
def simple_fn(): pass

@log_calls(level="DEBUG")  # With arguments
def debug_fn(): pass


# --- Async-aware decorator ---

def timed(fn: Callable[P, R]) -> Callable[P, R]:
    """Works with both sync and async functions."""
    if asyncio.iscoroutinefunction(fn):
        @functools.wraps(fn)
        async def async_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = time.perf_counter()
            result = await fn(*args, **kwargs)
            elapsed = time.perf_counter() - start
            logger.info("%s took %.3fs", fn.__name__, elapsed)
            return result
        return async_wrapper
    else:
        @functools.wraps(fn)
        def sync_wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            start = time.perf_counter()
            result = fn(*args, **kwargs)
            elapsed = time.perf_counter() - start
            logger.info("%s took %.3fs", fn.__name__, elapsed)
            return result
        return sync_wrapper

@timed
def sync_fn(): pass

@timed
async def async_fn(): pass


# --- Rate limiting decorator ---

def rate_limit(calls: int, period: float):
    """Allow max N calls per period seconds."""
    def decorator(fn: Callable[P, R]) -> Callable[P, R]:
        timestamps: list[float] = []

        @functools.wraps(fn)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
            now = time.time()
            # Remove old timestamps
            while timestamps and timestamps[0] < now - period:
                timestamps.pop(0)

            if len(timestamps) >= calls:
                wait = timestamps[0] + period - now
                raise RateLimitExceeded(
                    f"Rate limit: {calls}/{period}s. Retry in {wait:.1f}s"
                )

            timestamps.append(now)
            return fn(*args, **kwargs)
        return wrapper
    return decorator

@rate_limit(calls=10, period=60)
def api_call(): pass


# --- Class decorator ---

def singleton(cls):
    """Make a class a singleton."""
    instances = {}

    @functools.wraps(cls)
    def get_instance(*args, **kwargs):
        if cls not in instances:
            instances[cls] = cls(*args, **kwargs)
        return instances[cls]

    return get_instance

@singleton
class Database:
    def __init__(self, url: str):
        self.url = url


# --- Method decorator with access to self ---

def validate_state(*valid_states: str):
    """Ensure object is in valid state before method call."""
    def decorator(method):
        @functools.wraps(method)
        def wrapper(self, *args, **kwargs):
            if hasattr(self, "state") and self.state not in valid_states:
                raise InvalidStateError(
                    f"Cannot call {method.__name__} in state {self.state}. "
                    f"Valid states: {valid_states}"
                )
            return method(self, *args, **kwargs)
        return wrapper
    return decorator


class Order:
    state: str = "draft"

    @validate_state("draft")
    def submit(self):
        self.state = "submitted"

    @validate_state("submitted")
    def approve(self):
        self.state = "approved"


# --- Stacking decorators (order matters) ---

@retry(max_attempts=3)
@timed
@log_calls
def important_operation():
    """Applied bottom-up: log_calls wraps timed wraps retry."""
    pass
```

Decorator patterns:
1. **`functools.wraps`** — always use to preserve function metadata
2. **`_fn=None` trick** — decorator works with or without arguments
3. **Async-aware** — check `iscoroutinefunction` to handle both sync/async
4. **`ParamSpec`** — preserve decorated function's type signature
5. **Stacking order** — decorators apply bottom-up (innermost first)'''
    ),
]
"""
