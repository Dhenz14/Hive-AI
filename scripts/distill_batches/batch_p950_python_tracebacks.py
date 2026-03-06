"""Thinking-trace pairs: real-world Python traceback debugging."""

PAIRS = [
    (
        "thinking/debug-circular-import-recursion",
        r'''I'm getting a RecursionError when starting my Flask app. It only happens when I added a new module. Here's the traceback:

```
Traceback (most recent call last):
  File "app.py", line 1, in <module>
    from routes import api_bp
  File "/app/routes/__init__.py", line 3, in <module>
    from routes.users import users_bp
  File "/app/routes/users.py", line 2, in <module>
    from services.auth import verify_token
  File "/app/services/auth.py", line 4, in <module>
    from models.user import User
  File "/app/models/user.py", line 3, in <module>
    from services.permissions import check_permission
  File "/app/services/permissions.py", line 2, in <module>
    from models.user import User
  File "/app/models/user.py", line 3, in <module>
    from services.permissions import check_permission
  File "/app/services/permissions.py", line 2, in <module>
    from models.user import User
  ... (repeats hundreds of times)
RecursionError: maximum recursion depth exceeded
```

Here's my code:

```python
# models/user.py
from sqlalchemy import Column, Integer, String
from database import db
from services.permissions import check_permission

class User(db.Model):
    id = Column(Integer, primary_key=True)
    username = Column(String(80))
    role = Column(String(20))

    def can(self, action):
        return check_permission(self, action)
```

```python
# services/permissions.py
from models.user import User

ROLE_PERMISSIONS = {
    'admin': ['read', 'write', 'delete'],
    'editor': ['read', 'write'],
    'viewer': ['read'],
}

def check_permission(user: User, action: str) -> bool:
    return action in ROLE_PERMISSIONS.get(user.role, [])
```

What's going on?''',
        r'''<think>
Let me trace the import chain carefully:

1. `app.py` imports from `routes`
2. `routes/users.py` imports `verify_token` from `services/auth`
3. `services/auth.py` imports `User` from `models/user`
4. `models/user.py` imports `check_permission` from `services/permissions`
5. `services/permissions.py` imports `User` from `models/user`
6. But `models/user` is still being initialized (step 4 hasn't finished)...

Wait, does Python actually re-execute the module? I need to think about this more carefully. Python's import system has a module cache (sys.modules). When `services/permissions.py` tries to import `models/user`, Python finds it in sys.modules BUT the module object is only partially initialized -- the `from services.permissions import check_permission` line in `models/user.py` hasn't completed yet. So Python returns the partially-initialized module, and the `from models.user import User` statement fails because `User` hasn't been defined yet in the partial module.

Hmm, actually the traceback shows the recursion going hundreds of levels deep, not an ImportError on a partial module. That means Python IS re-executing the module file rather than returning the partial module. Let me reconsider... Could it be that the import paths differ slightly (e.g., relative vs absolute) causing Python to treat them as different modules and not cache properly? That would explain the infinite recursion rather than a simple ImportError. Actually, in some cases depending on whether the module was added to sys.modules before execution began, the behavior differs. The repeating traceback pattern confirms circular re-execution.

This is a classic circular import. The cycle is:
  models/user -> services/permissions -> models/user

The key question: does `services/permissions.py` actually NEED the `User` class at import time? Looking at the code, `User` is used only as a type hint in the function signature. The function body only accesses `user.role`, which is a plain attribute access -- it does not need the User class at runtime at all. So the import is only needed for static type checking, not for execution.

I considered several fixes:
1. Use `from __future__ import annotations` in permissions.py -- this defers annotation evaluation, so the import is never executed at runtime. Simplest one-line fix.
2. Move the import inside the function -- works but clutters every function that needs it.
3. Use TYPE_CHECKING guard -- cleanest for type-hint-only imports, makes the intent explicit.
4. Restructure so permissions uses duck typing -- removes the dependency entirely but loses type checking benefit.

I initially leaned toward option 1 since it is just one line, but actually option 3 is better because it clearly communicates WHY the import is conditional. Option 1 changes ALL annotations in the file to be lazy, which could mask other import issues. Option 3 is surgical -- only the problematic import is guarded. I will recommend option 3 with a mention of the alternatives.
</think>

## Root Cause: Circular Import

You have a circular dependency chain:

```
models/user.py  --->  services/permissions.py  --->  models/user.py (CYCLE!)
```

Python's import system works by executing module files top-to-bottom. When `models/user.py` starts executing, it hits `from services.permissions import check_permission` on line 3. Python then starts executing `services/permissions.py`, which hits `from models.user import User` on line 1. But `models/user.py` hasn't finished executing yet (it's stuck at line 3), so Python tries to import it again, creating the infinite recursion.

## Why It Wasn't Caught Earlier

This only surfaced when you added the `services/auth.py` import path. Before that, `models/user.py` may have been imported first through a different path where the cycle wasn't triggered, or the `check_permission` import was added recently.

## The Fix

`services/permissions.py` uses `User` only as a type annotation, not at runtime. Use the `TYPE_CHECKING` guard:

```python
# services/permissions.py
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models.user import User

ROLE_PERMISSIONS = {
    'admin': ['read', 'write', 'delete'],
    'editor': ['read', 'write'],
    'viewer': ['read'],
}

def check_permission(user: User, action: str) -> bool:
    return action in ROLE_PERMISSIONS.get(user.role, [])
```

**What this does:**
- `from __future__ import annotations` makes ALL annotations lazy (strings, not evaluated at import time)
- `TYPE_CHECKING` is `False` at runtime but `True` for mypy/pyright, so the import only happens during static analysis
- The function body uses `user.role` via duck typing -- it never needs the actual `User` class at runtime

## Alternative: Lazy Import

If you did need `User` at runtime (e.g., `isinstance` checks), move the import inside the function:

```python
# services/permissions.py
def check_permission(user, action: str) -> bool:
    from models.user import User  # imported lazily, after both modules are fully loaded
    assert isinstance(user, User)
    return action in ROLE_PERMISSIONS.get(user.role, [])
```

## Prevention

1. **Draw your dependency graph.** If module A imports from B and B imports from A, you have a cycle.
2. **Models should be leaf nodes** -- they should not import from service layers. If a model needs service-layer logic, inject it via methods that do lazy imports or accept callables.
3. **Use `from __future__ import annotations`** as a default in all files (it will become the default in a future Python version anyway).
4. **Linters can catch this**: `pylint` has `cyclic-import` and `import-error` checks; `ruff` has `INP001`.''',
    ),
    (
        "thinking/debug-nonetype-attributeerror",
        r'''My data processing pipeline randomly crashes with this error. It doesn't happen on every run, only with certain input files:

```
Traceback (most recent call last):
  File "pipeline.py", line 47, in process_batch
    result = transform(record)
  File "pipeline.py", line 32, in transform
    cleaned = record.get("metadata", {}).get("tags", [])
  File "pipeline.py", line 33, in transform
    primary_tag = cleaned[0].strip().lower()
IndexError: list index out of range
```

Wait, actually sometimes I get a different error on the same line:

```
Traceback (most recent call last):
  File "pipeline.py", line 32, in transform
    cleaned = record.get("metadata", {}).get("tags", [])
AttributeError: 'NoneType' object has no attribute 'get'
```

Here's the code:

```python
def transform(record: dict) -> dict:
    cleaned = record.get("metadata", {}).get("tags", [])
    primary_tag = cleaned[0].strip().lower()
    category = TAG_CATEGORIES.get(primary_tag, "uncategorized")
    return {**record, "category": category, "primary_tag": primary_tag}
```

Sample input data that works:
```json
{"id": 1, "metadata": {"tags": ["python", "web"]}}
```

What's happening?''',
        r'''<think>
Two different errors from similar code. Let me analyze each carefully.

**Error 1: IndexError on `cleaned[0]`**
This happens when `cleaned` is an empty list `[]`. That means the record has `metadata.tags` but it is an empty list: `{"metadata": {"tags": []}}`. Straightforward.

**Error 2: AttributeError: 'NoneType' object has no attribute 'get'**
This is trickier. The chained `.get()` call is:
```python
record.get("metadata", {}).get("tags", [])
```

My first instinct was that this fails when "metadata" is missing from the record. But wait -- if the key is missing, `.get("metadata", {})` returns the default `{}`, and then `{}.get("tags", [])` returns `[]`. That is fine. So the key IS present...

But what if the key exists with value `None`? Let me think through this:
```python
record.get("metadata", {})  # returns None (the actual stored value), NOT {}
```
The default `{}` is only used when the key is MISSING, not when it exists with a falsy value. This is a very common Python gotcha -- `.get()` defaults apply to absent keys, not to None values. So `None.get("tags", [])` raises AttributeError.

Hmm, I initially assumed this only happens with None, but actually it could happen with any non-dict value for metadata -- an integer, a string, a list. Any of those would fail on `.get()`. Though None is by far the most common case in real data (e.g., JSON null).

So the problematic inputs are:
1. `{"id": 2, "metadata": None}` -> AttributeError (None has no .get)
2. `{"id": 3, "metadata": {"tags": []}}` -> IndexError (empty list, no [0])
3. `{"id": 4, "metadata": {"tags": None}}` -> would cause TypeError on `None[0]`

There is also a hidden fourth case I almost missed: what if tags contains non-string elements? `cleaned[0].strip()` would fail on integers or None values inside the list. But the primary bugs are the None-propagation through chained `.get()` and the unchecked empty list access.

The fix should use `or {}` instead of default parameters, since `or` treats None (and all falsy values) as triggers for the fallback.
</think>

## Root Cause: None Propagation Through `.get()` Chaining

You have two distinct bugs, both stemming from the same unsafe assumption about your data.

### Bug 1: `AttributeError: 'NoneType' object has no attribute 'get'`

The key insight: **`.get(key, default)` only returns the default when the key is MISSING, not when the key exists with a `None` value.**

```python
# Key missing -> default is used (works fine)
{}.get("metadata", {})  # returns {}

# Key present with None -> None is returned, NOT the default
{"metadata": None}.get("metadata", {})  # returns None, not {}!
```

So when your input has `{"metadata": None}`, the chain becomes:
```python
None.get("tags", [])  # BOOM: AttributeError
```

### Bug 2: `IndexError: list index out of range`

When tags is an empty list `{"metadata": {"tags": []}}`, `cleaned` is `[]`, and `cleaned[0]` raises `IndexError`.

There's also a hidden Bug 3 you haven't hit yet: if `tags` is `None`, you'll get `TypeError: 'NoneType' object is not subscriptable`.

### The Fix

```python
def transform(record: dict) -> dict:
    metadata = record.get("metadata") or {}
    tags = metadata.get("tags") or []
    primary_tag = tags[0].strip().lower() if tags else None
    category = TAG_CATEGORIES.get(primary_tag, "uncategorized") if primary_tag else "uncategorized"
    return {**record, "category": category, "primary_tag": primary_tag}
```

**Key changes:**
1. **`or {}` instead of default parameter**: `record.get("metadata") or {}` returns `{}` for BOTH missing keys AND `None` values. The `or` operator treats `None` as falsy.
2. **Guard on empty list**: `tags[0] if tags else None` prevents the `IndexError`.
3. **Each step is its own variable**: No more chaining, which makes debugging and None-handling explicit.

### Defensive Alternative With Validation

If bad data should be flagged rather than silently defaulted:

```python
def transform(record: dict) -> dict:
    metadata = record.get("metadata")
    if not isinstance(metadata, dict):
        log.warning(f"Record {record.get('id')}: metadata is {type(metadata).__name__}, expected dict")
        return {**record, "category": "uncategorized", "primary_tag": None}

    tags = metadata.get("tags")
    if not isinstance(tags, list) or len(tags) == 0:
        log.warning(f"Record {record.get('id')}: tags is {type(tags).__name__} / empty")
        return {**record, "category": "uncategorized", "primary_tag": None}

    primary_tag = tags[0].strip().lower()
    category = TAG_CATEGORIES.get(primary_tag, "uncategorized")
    return {**record, "category": category, "primary_tag": primary_tag}
```

### The General Rule

**Never chain `.get()` calls on untrusted data.** The pattern `d.get("a", {}).get("b", [])` is safe ONLY when you can guarantee intermediate values are never `None`. For API responses, database results, and user input -- you can't guarantee that. Use `or {}` or explicit `isinstance` checks.''',
    ),
    (
        "thinking/debug-asyncio-cancelled-error",
        r'''My async web scraper crashes during shutdown with this error. It happens when I Ctrl+C while it's running:

```
^C
Task was destroyed but it is pending!
task: <Task pending name='Task-15' coro=<scrape_page() running at scraper.py:28> wait_for=<Future pending cb=[Task.task_wakeup()]>>

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "scraper.py", line 58, in main
    results = await asyncio.gather(*tasks)
  File "scraper.py", line 28, in scrape_page
    async with session.get(url) as response:
  File "aiohttp/client.py", line 1138, in __aenter__
    self._resp = await self._coro
asyncio.CancelledError

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "scraper.py", line 72, in <module>
    asyncio.run(main())
  File "asyncio/runners.py", line 44, in run
    return loop.run_until_complete(main)
KeyboardInterrupt

ERROR: 12 results lost, database connection not closed properly
```

```python
import asyncio
import aiohttp

async def scrape_page(session, url):
    async with session.get(url) as response:
        html = await response.text()
        data = parse_html(html)
        await save_to_db(data)
        return data

async def main():
    urls = load_urls()  # ~500 URLs
    async with aiohttp.ClientSession() as session:
        tasks = [scrape_page(session, url) for url in urls]
        results = await asyncio.gather(*tasks)
    print(f"Scraped {len(results)} pages")

asyncio.run(main())
```

How do I make this gracefully handle Ctrl+C without losing data or leaking connections?''',
        r'''<think>
The problem is multi-layered. Let me trace what happens when Ctrl+C is pressed.

1. `asyncio.gather()` launches all 500 tasks simultaneously. That is already concerning -- 500 concurrent HTTP connections could exhaust file descriptors or get rate-limited. But the immediate issue is shutdown behavior.

2. When Ctrl+C happens, `asyncio.run()` cancels the main task. This propagates `CancelledError` to all pending tasks via the gather.

3. Hmm, but which tasks are actually affected? Tasks could be in several states:
   - Waiting for `session.get()` (mid-download) -- cancellation is fine, no data to save
   - Between `response.text()` and `parse_html()` -- parsed data is lost
   - Between `parse_html()` and `save_to_db()` -- this is the critical window where we have results but have not persisted them
   - Inside `save_to_db()` -- mid-write, could leave the DB in an inconsistent state

4. Wait, there is another issue I almost missed: the `aiohttp.ClientSession` context manager tries to close when the `async with` block exits, but pending tasks are still referencing the session. That is why we get "Task was destroyed but it is pending." The session is closed while tasks still hold references to it.

5. No signal handling means Ctrl+C is a raw KeyboardInterrupt, which is essentially an uncontrolled crash.

I initially thought we could just wrap `gather()` in a try/except, but that is not enough because CancelledError propagates differently from regular exceptions. The gather would cancel all tasks without giving them a chance to flush partial work.

The fix needs multiple layers:
- Signal handler to set a "shutdown" flag instead of crashing immediately
- Semaphore to limit concurrency (so at most ~20 tasks are in-flight, not 500)
- CancelledError handling inside each task to queue partial results for flushing
- Use `asyncio.wait()` instead of `gather()` to get access to done/pending sets
- Proper shutdown sequence: signal -> stop new work -> cancel pending -> flush -> close session -> close DB

I considered using `asyncio.shield()` to protect save_to_db from cancellation, but that only delays the cancellation -- it does not prevent it. The queue-based approach is more robust.
</think>

## Root Cause: No Graceful Shutdown Handling

When you press Ctrl+C, `asyncio.run()` cancels the running task. This sends `CancelledError` to all 500 in-flight tasks simultaneously. Tasks in the middle of `save_to_db()` get interrupted, the session closes while tasks still reference it, and partial results are lost.

There are actually four problems here:

1. **No signal handler** -- Ctrl+C is an uncontrolled nuke, not a graceful shutdown
2. **No cancellation handling** in `scrape_page` -- tasks can't clean up
3. **500 concurrent requests** -- too many; you're also likely to get rate-limited or exhaust file descriptors
4. **No separation between "cancel pending work" and "finish in-progress work"**

## The Fix

```python
import asyncio
import signal
import aiohttp
from contextlib import suppress

# Shutdown event visible to all tasks
shutdown_event = asyncio.Event()

async def scrape_page(session, url, semaphore, results_queue):
    """Scrape a single page with cancellation awareness."""
    async with semaphore:
        if shutdown_event.is_set():
            return None  # Don't start new work during shutdown

        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                html = await response.text()
        except asyncio.CancelledError:
            # Cancelled during download -- nothing to save, just exit cleanly
            raise
        except aiohttp.ClientError as e:
            print(f"Failed to fetch {url}: {e}")
            return None

        # Parse is synchronous and fast -- won't be interrupted
        data = parse_html(html)

        try:
            await save_to_db(data)
            return data
        except asyncio.CancelledError:
            # We have parsed data but save was interrupted.
            # Queue it for the shutdown handler to flush.
            await results_queue.put(data)
            raise

async def flush_pending(results_queue):
    """Save any results that were interrupted mid-save."""
    count = 0
    while not results_queue.empty():
        data = results_queue.get_nowait()
        try:
            await save_to_db(data)
            count += 1
        except Exception as e:
            print(f"Failed to flush pending result: {e}")
    if count:
        print(f"Flushed {count} interrupted results during shutdown")

async def main():
    urls = load_urls()
    semaphore = asyncio.Semaphore(20)  # Max 20 concurrent requests
    results_queue = asyncio.Queue()

    # Set up graceful shutdown on SIGINT (Ctrl+C)
    loop = asyncio.get_running_loop()

    def signal_handler():
        if not shutdown_event.is_set():
            print("\nShutting down gracefully... (press Ctrl+C again to force)")
            shutdown_event.is_set() or shutdown_event.set()
        else:
            raise KeyboardInterrupt  # Second Ctrl+C = force quit

    loop.add_signal_handler(signal.SIGINT, signal_handler)

    async with aiohttp.ClientSession() as session:
        tasks = [
            asyncio.create_task(scrape_page(session, url, semaphore, results_queue))
            for url in urls
        ]

        # Wait for all tasks, but handle shutdown
        done, pending = await asyncio.wait(tasks, return_when=asyncio.ALL_COMPLETED)

        # If shutdown was requested, cancel remaining pending tasks
        if shutdown_event.is_set() and pending:
            print(f"Cancelling {len(pending)} pending tasks...")
            for task in pending:
                task.cancel()
            # Wait for cancellation to complete
            await asyncio.gather(*pending, return_exceptions=True)

    # Flush any results that were interrupted mid-save
    await flush_pending(results_queue)

    # Collect successful results
    successful = [t.result() for t in done if not t.cancelled() and t.exception() is None and t.result() is not None]
    print(f"Scraped {len(successful)} pages successfully")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Force quit.")
```

## Why This Works

1. **Signal handler sets an event** instead of crashing. Tasks check the event before starting new work.
2. **`CancelledError` is caught in `scrape_page`** at the critical point (between parse and save). Interrupted data is queued for later flushing.
3. **Semaphore limits concurrency to 20**, so at most 20 tasks are in-flight during shutdown -- not 500.
4. **`asyncio.wait()` instead of `gather()`** gives you access to `done` and `pending` sets, so you can cancel only what hasn't finished.
5. **Flush step** after session closure saves any data that was parsed but not yet written.

## Note on Windows

`loop.add_signal_handler()` doesn't work on Windows. For cross-platform support, use:

```python
# Instead of add_signal_handler
if sys.platform != "win32":
    loop.add_signal_handler(signal.SIGINT, signal_handler)
else:
    # On Windows, Ctrl+C raises KeyboardInterrupt in the main thread
    # Wrap asyncio.run() in try/except and set the event there
    signal.signal(signal.SIGINT, lambda s, f: shutdown_event.set())
```''',
    ),
    (
        "thinking/debug-pickle-lambda-multiprocessing",
        r'''I'm using Python's multiprocessing Pool to parallelize data processing and I get this error:

```
Traceback (most recent call last):
  File "parallel_process.py", line 24, in <module>
    results = pool.map(process_item, items)
  File "/usr/lib/python3.11/multiprocessing/pool.py", line 367, in map
    return self._map_async(func, iterable, mapstar, chunksize).get()
  File "/usr/lib/python3.11/multiprocessing/pool.py", line 774, in get
    raise self._value
  File "/usr/lib/python3.11/multiprocessing/pool.py", line 540, in _handle_tasks
    put(task)
  File "/usr/lib/python3.11/multiprocessing/connection.py", line 206, in send
    self._send_bytes(_ForkingPickler.dumps(obj))
  File "/usr/lib/python3.11/multiprocessing/reduction.py", line 51, in dumps
    cls(buf, protocol).dump(obj)
_pickle.PicklingError: Can't pickle <function <lambda> at 0x7f3b2c1d5940>: attribute lookup <lambda> on __main__ failed
```

Here's my code:

```python
from multiprocessing import Pool
from dataclasses import dataclass, field
from typing import Callable

@dataclass
class ProcessingConfig:
    threshold: float = 0.5
    transform: Callable = field(default_factory=lambda: lambda x: x)
    filter_fn: Callable = field(default_factory=lambda: lambda x: x > 0)

def process_item(item):
    config = ProcessingConfig()
    if config.filter_fn(item['value']):
        return config.transform(item['value'])
    return None

if __name__ == '__main__':
    items = [{'value': i} for i in range(-10, 10)]
    with Pool(4) as pool:
        results = pool.map(process_item, items)
    print(results)
```

But wait -- I'm not passing the lambda to pool.map, I'm passing `process_item` which is a regular function. Why is pickle involved with the lambda at all?''',
        r'''<think>
Interesting question. The user is right that `process_item` is a regular module-level function, which IS picklable. And the lambda is created inside `process_item`, not passed to `pool.map`. So why is pickle even touching a lambda?

Let me trace the pickle path. `pool.map(process_item, items)` pickles:
1. `process_item` (the function) -- module-level, should be picklable by qualified name
2. Each item in `items` -- plain dicts, definitely picklable

So where does the lambda come from? The error says "attribute lookup <lambda> on __main__ failed", which means pickle is trying to serialize a lambda object and look it up by name in the module. But lambdas have no proper name, so the lookup fails.

Wait, `process_item` creates `ProcessingConfig()` inside the function body. Those lambdas only exist at runtime inside the worker process. They are never passed across the pickle boundary... unless the user's real code is different from what they showed.

Hmm, could it be a "fork" vs "spawn" issue? On Linux with "fork" start method, child processes inherit memory, so lambdas in the parent's memory just work. On Windows or macOS with "spawn" (default since Python 3.8+), the child is a fresh interpreter that re-imports the module. But even with "spawn", `process_item` is serialized by qualified name (not by value), so its body code is re-created in the child via import.

Actually, I think the code as shown would probably work fine. The error must be coming from a pattern the user simplified away. Let me think about what patterns DO trigger this...

Oh -- I bet the real code has a module-level config:
```python
config = ProcessingConfig()  # lambdas created here at module level
def process_item(item):
    if config.filter_fn(item['value']):  # config is a free variable
```
Now `process_item` is a closure over `config`. When pickle serializes the function, it needs to serialize `config` too, which contains lambdas. That would trigger the error.

Or they could be using `functools.partial`:
```python
process = partial(process_item, config=ProcessingConfig())
pool.map(process, items)  # partial pickles its args, including config with lambdas
```

Given the traceback location (`_handle_tasks` -> `put(task)` in the parent process), the lambda IS being pickled as part of the task. The most educational answer should explain the shown code (which might actually work), then show the common patterns that DO trigger this error, and provide fixes for each.

The fixes are:
1. Replace lambdas with named module-level functions (always picklable)
2. Use Pool(initializer=...) to create config in each worker (never crosses pickle boundary)
3. Use cloudpickle or joblib which can serialize lambdas
</think>

## Root Cause: Lambdas Can't Be Pickled, and Multiprocessing Pickles Everything

Python's `multiprocessing` uses pickle to serialize data sent between the parent process and worker processes. Lambdas (anonymous functions) cannot be pickled because pickle works by storing the function's qualified name and module -- lambdas don't have a unique name pickle can look up.

### Why Pickle Is Involved

With the `"spawn"` start method (default on Windows and macOS since Python 3.8), worker processes are fresh Python interpreters. Everything sent to them -- functions, arguments, globals they depend on -- must be serialized via pickle. Even on Linux with `"fork"`, return values are pickled back to the parent.

### The Likely Real Problem

The code you showed creates `ProcessingConfig()` inside `process_item`, which would actually work because the lambdas are created fresh in each worker. **Your real code likely does one of these:**

**Pattern A: Module-level config captured in closure**
```python
config = ProcessingConfig()  # lambdas created here in main process

def process_item(item):
    # config is a free variable -- pickle must serialize it
    if config.filter_fn(item['value']):
        return config.transform(item['value'])
```

**Pattern B: Config passed via functools.partial**
```python
from functools import partial
config = ProcessingConfig()
process = partial(process_item, config=config)  # pickle must serialize config
pool.map(process, items)  # BOOM: config contains lambdas
```

Both patterns cause pickle to try to serialize the `ProcessingConfig` object, which contains lambda attributes.

### The Fix

**Option 1: Replace lambdas with named functions**
```python
def identity(x):
    return x

def positive_filter(x):
    return x > 0

@dataclass
class ProcessingConfig:
    threshold: float = 0.5
    transform: Callable = field(default=identity)
    filter_fn: Callable = field(default=positive_filter)
```

Named module-level functions are picklable because pickle can look them up by name.

**Option 2: Use an initializer to create config in each worker**
```python
_worker_config = None

def init_worker(threshold):
    global _worker_config
    _worker_config = ProcessingConfig(threshold=threshold)

def process_item(item):
    if _worker_config.filter_fn(item['value']):
        return _worker_config.transform(item['value'])
    return None

with Pool(4, initializer=init_worker, initargs=(0.5,)) as pool:
    results = pool.map(process_item, items)
```

The initializer runs once per worker process. The config (with its lambdas) is created locally in each worker and never crosses a pickle boundary.

**Option 3: Use `concurrent.futures.ProcessPoolExecutor` with `cloudpickle`**

If you need to pass complex objects, `cloudpickle` can serialize lambdas:
```python
import cloudpickle
import pickle
pickle.Pickler = cloudpickle.Pickler  # Monkey-patch (not ideal for production)
```

Or switch to `loky` (used by `joblib`), which uses `cloudpickle` by default:
```python
from joblib import Parallel, delayed
results = Parallel(n_jobs=4)(delayed(process_item)(item) for item in items)
```

### Prevention Rules

1. **Never put lambdas in objects that might cross process boundaries.** Use named functions.
2. **If a function references module-level state, that state must be picklable.** Check with `pickle.dumps(obj)` before using multiprocessing.
3. **Prefer `Pool(initializer=...)` for complex worker state** instead of passing it through function arguments.
4. **Test with `"spawn"` start method** even on Linux, since `"fork"` hides these bugs by sharing memory instead of pickling.''',
    ),
    (
        "thinking/debug-unicode-decode-csv",
        r'''I'm reading CSV files from multiple sources and getting this intermittent error:

```
Traceback (most recent call last):
  File "ingest.py", line 15, in load_csv
    reader = csv.DictReader(f)
  File "ingest.py", line 16, in load_csv
    for row in reader:
  File "/usr/lib/python3.11/csv.py", line 111, in __next__
    self.fieldnames
  File "/usr/lib/python3.11/csv.py", line 98, in fieldnames
    self._fieldnames = next(self.reader)
  File "/usr/lib/python3.11/codecs.py", line 322, in decode
    (result, size) = self._buffer_decode(data, self.errors, final)
UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9 in position 42: invalid continuation byte
```

My code:
```python
import csv

def load_csv(filepath):
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row

# Works fine for most files
for row in load_csv('data/customers_us.csv'):
    process(row)

# Crashes on this one
for row in load_csv('data/customers_eu.csv'):
    process(row)
```

The EU file opens fine in Excel. What's going on?''',
        r'''<think>
The error: `UnicodeDecodeError: 'utf-8' codec can't decode byte 0xe9 in position 42`

What is byte 0xe9? My first thought was that it could be a corrupted file, but 0xe9 is a perfectly valid byte in Latin-1 encoding -- it is the character e-acute (e with accent). This is extremely common in European names like "Rene", "Jose", "cafe".

But wait, why does UTF-8 reject it? In UTF-8, e-acute is encoded as two bytes: 0xc3 0xa9. The single byte 0xe9 is a leading byte for a 3-byte sequence in UTF-8 (since 0xe9 = 11101001 starts with 1110, indicating 3 bytes). But the following byte apparently is not a valid continuation byte (which must start with 10xxxxxx). So UTF-8 rejects it as malformed.

Hmm, so the file was saved in Latin-1 (ISO-8859-1) or Windows-1252 encoding. These are single-byte encodings where every byte 0x00-0xFF maps to a character. They are common on European Windows systems and in software that predates UTF-8 adoption. Python 3's `open()` defaults to UTF-8 on Linux/Mac (technically `locale.getpreferredencoding()`), so it chokes on non-UTF-8 files.

The user says "Excel opens it fine" -- that is because Excel has built-in encoding detection heuristics. It silently tries multiple encodings until one works. Python is strict by default, which is actually better for data integrity even if it is more annoying.

Could this also be a Windows-1252 file rather than Latin-1? Windows-1252 is a superset of Latin-1 that adds characters in the 0x80-0x9F range (like curly quotes, em dashes, euro sign). For byte 0xe9 specifically they are identical, but for a robust solution I should handle both.

The fix needs to:
1. Handle the immediate file (specify encoding='latin-1')
2. Build a robust solution for mixed-encoding files from multiple sources using chardet or charset-normalizer
3. Add a safety net with errors='replace' to prevent crashes on edge cases
</think>

## Root Cause: Latin-1 Encoded File Read as UTF-8

The byte `0xe9` is the character `é` in Latin-1 (ISO-8859-1) / Windows-1252 encoding. Your European CSV file was saved with Latin-1 encoding (common on Windows systems in Europe), but Python 3's `open()` defaults to UTF-8 on most platforms.

In UTF-8, `é` is two bytes (`0xc3 0xa9`). In Latin-1, it's one byte (`0xe9`). When the UTF-8 decoder hits `0xe9` without the expected continuation byte, it crashes.

Excel works because it uses heuristics to guess the encoding. Python is strict by default.

## Quick Fix

If you know the file is Latin-1:

```python
def load_csv(filepath):
    with open(filepath, 'r', encoding='latin-1') as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row
```

But this is fragile -- if you receive files from multiple sources, they may use different encodings.

## Robust Fix: Detect Encoding

```python
import csv
import chardet
from pathlib import Path

def detect_encoding(filepath, sample_size=10000):
    """Read a chunk of the file and detect its encoding."""
    raw = Path(filepath).read_bytes()[:sample_size]

    # Check for BOM (Byte Order Mark) first -- most reliable signal
    if raw.startswith(b'\xef\xbb\xbf'):
        return 'utf-8-sig'
    if raw.startswith(b'\xff\xfe'):
        return 'utf-16-le'
    if raw.startswith(b'\xfe\xff'):
        return 'utf-16-be'

    # Use chardet for statistical detection
    result = chardet.detect(raw)
    encoding = result['encoding']
    confidence = result['confidence']

    # chardet sometimes returns 'ascii' for files that are actually utf-8
    # (if the sample has no non-ASCII chars). Treat ascii as utf-8.
    if encoding and encoding.lower() == 'ascii':
        encoding = 'utf-8'

    # Low confidence? Fall back to latin-1, which never fails
    # (it maps all 256 byte values to characters)
    if confidence < 0.7:
        return 'latin-1'

    return encoding or 'utf-8'

def load_csv(filepath):
    encoding = detect_encoding(filepath)
    with open(filepath, 'r', encoding=encoding, errors='replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row
```

Install `chardet`: `pip install chardet` (or the faster `charset-normalizer` which has the same API).

## Why `errors='replace'` as a Safety Net

Even with detection, edge cases exist (files with mixed encodings, corrupted bytes). The `errors='replace'` parameter replaces undecodable bytes with `U+FFFD` (the replacement character) instead of crashing. For data pipelines, a few garbled characters are better than a total crash.

Other error modes:
- `errors='ignore'` -- silently drops bad bytes (dangerous: data loss)
- `errors='surrogateescape'` -- preserves raw bytes as surrogates (useful for round-tripping)
- `errors='replace'` -- replaces with `\ufffd` (best for display/processing)

## Production-Grade Approach

For a real data pipeline ingesting CSVs from many sources:

```python
import csv
import logging
from charset_normalizer import from_path

log = logging.getLogger(__name__)

def load_csv_robust(filepath):
    """Load a CSV with automatic encoding detection and logging."""
    # charset_normalizer is more accurate than chardet for mixed Western encodings
    detection = from_path(filepath).best()
    if detection is None:
        log.error(f"Could not detect encoding for {filepath}, falling back to latin-1")
        encoding = 'latin-1'
    else:
        encoding = detection.encoding
        log.info(f"{filepath}: detected encoding={encoding}")

    # Track replacement characters for data quality monitoring
    replaced_count = 0
    def counting_error_handler(err):
        nonlocal replaced_count
        replaced_count += 1
        return ('\ufffd', err.end)

    import codecs
    codecs.register_error('count_and_replace', counting_error_handler)

    with open(filepath, 'r', encoding=encoding, errors='count_and_replace') as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row

    if replaced_count > 0:
        log.warning(f"{filepath}: {replaced_count} characters could not be decoded")
```

## Common Encodings by Source

| Source | Likely Encoding |
|--------|----------------|
| European Windows (Excel) | `windows-1252` (superset of latin-1) |
| East Asian (CJK) | `shift_jis`, `gb2312`, `euc-kr` |
| Modern web/API exports | `utf-8` (often with BOM: `utf-8-sig`) |
| Old Unix/Mac systems | `iso-8859-1` or `macroman` |
| Database exports | Usually `utf-8`, but check DB's `character_set` |

## Prevention

1. **Standardize encoding at the source.** If you control the export, always export as UTF-8 with BOM (`utf-8-sig`), which all tools recognize.
2. **Validate on ingest.** Run encoding detection on every new file and log it.
3. **Never use bare `open()`** for external data -- always specify `encoding` and `errors`.''',
    ),
]
