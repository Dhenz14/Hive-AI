PAIRS = [
    ("thinking/debugging", r'''I'm getting this error when trying to run an async function from a Jupyter notebook:

```
RuntimeError: This event loop is already running
```

Here's my code:

```python
import asyncio

async def fetch_data():
    await asyncio.sleep(1)
    return {"status": "ok"}

result = asyncio.run(fetch_data())
```

I tried using `loop.run_until_complete()` too but got the same error. What's going on?''', r'''<think>
Let me analyze this error carefully. The user is getting "This event loop is already running" when calling asyncio.run() from a Jupyter notebook.

My first instinct is that asyncio.run() is just broken somehow... but wait, that does not make sense because asyncio.run() works fine in normal scripts. The key detail here is "Jupyter notebook." Could it be a version issue with asyncio? Hmm, no -- I considered that, but the error message is specifically about an already-running loop, not a missing API.

Actually, the real cause is that Jupyter itself runs on top of an asyncio event loop (via tornado). When you call asyncio.run(), it tries to create a new event loop and run it, but there is already an event loop running in the current thread -- the one Jupyter is using. Since Python only allows one event loop per thread, this fails. Therefore, asyncio.run() is fundamentally incompatible with environments that already have a running loop.

Wait, could the user be running this outside Jupyter? I considered that possibility, but this error almost exclusively happens in environments with a pre-existing event loop (Jupyter, some web frameworks, etc.). The user explicitly mentions Jupyter, so that confirms it.

The standard fix is to use `await` directly in Jupyter cells (since Jupyter supports top-level await), or use the nest_asyncio library which patches asyncio to allow nested event loops. I initially thought about suggesting loop.run_until_complete() as an alternative, but actually that has the same underlying problem because asyncio.run() calls loop.run_until_complete() internally, and that method checks if the loop is already running.
</think>

This is a classic Jupyter notebook issue. Jupyter (via IPython and tornado) already has an asyncio event loop running in the background. When you call `asyncio.run()`, it attempts to start a new event loop, but Python only allows one event loop per thread, and one is already active.

There are two solutions:

**Solution 1: Use top-level await (preferred in Jupyter)**

Jupyter notebooks support top-level `await` natively since IPython 7.0. Simply write:

```python
async def fetch_data():
    await asyncio.sleep(1)
    return {"status": "ok"}

result = await fetch_data()
print(result)
```

No need for `asyncio.run()` at all -- Jupyter will handle scheduling the coroutine on its existing event loop.

**Solution 2: Use nest_asyncio (for library code)**

If you have library code that calls `asyncio.run()` internally and you cannot modify it:

```python
import nest_asyncio
nest_asyncio.apply()

import asyncio

async def fetch_data():
    await asyncio.sleep(1)
    return {"status": "ok"}

result = asyncio.run(fetch_data())
```

`nest_asyncio` patches the event loop to allow reentrant calls to `run_until_complete()`.

**Why loop.run_until_complete() also fails:**

It performs the same check internally -- if the loop is already running, it raises the same RuntimeError. The check exists because running a loop inside itself would cause reentrancy issues with the event loop's internal state.

**Prevention tips:**

- In Jupyter or IPython, always use `await` directly instead of `asyncio.run()`
- In scripts or CLI tools, `asyncio.run()` works fine because there is no pre-existing loop
- If writing a library, consider accepting an optional event loop parameter or providing both sync and async APIs
- Use `asyncio.get_running_loop()` to detect if a loop is active before deciding which approach to use'''),

    ("thinking/debugging", r'''My async web scraper is producing warnings and some results are None:

```
RuntimeWarning: coroutine 'fetch_page' was never awaited
  fetch_page(url)
```

Code:

```python
import asyncio
import aiohttp

async def fetch_page(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.text()

async def scrape_all(urls):
    results = []
    for url in urls:
        result = fetch_page(url)  # line 11
        results.append(result)
    return results

urls = ["http://example.com/1", "http://example.com/2", "http://example.com/3"]
results = asyncio.run(scrape_all(urls))
print(results)  # prints [<coroutine object>, <coroutine object>, ...]
```

Why am I getting coroutine objects instead of actual HTML?''', r'''<think>
Let me look at this code carefully. The warning says "coroutine 'fetch_page' was never awaited" and points to line 11. Could it be a threading issue? Hmm, no -- the error message is very specific about unawaited coroutines, not threads.

Looking at line 11: `result = fetch_page(url)` -- wait, there is no `await` keyword. When you call an async function without `await`, Python does not execute it. Instead, it returns a coroutine object. The coroutine is created but never actually run. So `results` ends up being a list of unawaited coroutine objects, not the actual HTML content. That explains both the warning and the unexpected output.

I initially thought the fix is just adding `await`... but actually, I should also point out that even with `await`, this code is sequential -- it awaits each page one at a time in a for loop. For a web scraper, the user probably wants concurrent fetching, since the whole point of async is parallelism on I/O. Therefore I should suggest asyncio.gather() for proper concurrency.

Also, creating a new ClientSession for each request is wasteful because each session spins up its own connection pool. The session should be shared across requests to benefit from connection reuse and keep-alive.
</think>

The bug is on line 11: you are calling `fetch_page(url)` without `await`. In Python, calling an async function without `await` does not execute it -- it merely creates a coroutine object and returns it immediately. The actual function body never runs.

**The immediate fix:**

```python
async def scrape_all(urls):
    results = []
    for url in urls:
        result = await fetch_page(url)  # Added await
        results.append(result)
    return results
```

However, this fetches pages sequentially, which defeats the purpose of async. Here is the proper concurrent version:

**The correct concurrent approach:**

```python
import asyncio
import aiohttp

async def fetch_page(session, url):
    async with session.get(url) as response:
        return await response.text()

async def scrape_all(urls):
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_page(session, url) for url in urls]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

urls = ["http://example.com/1", "http://example.com/2", "http://example.com/3"]
results = asyncio.run(scrape_all(urls))
```

Key improvements:

1. **`await` is used** so coroutines actually execute
2. **`asyncio.gather()`** runs all fetches concurrently instead of one-by-one
3. **`return_exceptions=True`** prevents one failed request from killing all others -- failed ones return the exception object instead of raising
4. **Shared `ClientSession`** reuses TCP connections via connection pooling, which is much more efficient than creating a new session per request

**Prevention tips:**

- Enable the Python warning filter: `python -W error::RuntimeWarning` to turn unawaited coroutine warnings into hard errors during development
- Use a linter like `pylint` or `flake8-async` which can catch missing await calls statically
- Remember the rule: if a function is defined with `async def`, you almost always need `await` when calling it'''),

    ("thinking/debugging", r'''I have an async task that should be cancellable, but the cancellation seems to be ignored:

```python
import asyncio

async def long_running_task():
    try:
        while True:
            data = process_batch()  # sync CPU-bound work, takes ~30 seconds
            await save_results(data)
    except asyncio.CancelledError:
        print("Task was cancelled, cleaning up...")
        raise

async def main():
    task = asyncio.create_task(long_running_task())
    await asyncio.sleep(5)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        print("Main: task cancelled successfully")

asyncio.run(main())
```

The task.cancel() call does nothing for 30 seconds. The cancellation only takes effect after process_batch() finishes. How do I make cancellation immediate?''', r'''<think>
The user says cancellation is "ignored" for 30 seconds. Could there be a bug in task.cancel()? Hmm, no -- task.cancel() is well-tested in the stdlib. Let me think about what actually happens here.

asyncio.Task.cancel() works by injecting a CancelledError at the next await point. The key phrase is "next await point." If the code is running synchronous CPU-bound work (process_batch() taking 30 seconds), there are no await points during that time. The event loop is completely blocked -- it cannot process the cancellation until control returns to the event loop.

Wait, so the cancellation is not actually "ignored" -- it is queued and will be delivered at the next await, which is `await save_results(data)`. That is why it takes ~30 seconds. The user's mental model assumes cancel() is like killing a thread, but actually asyncio is cooperative, not preemptive.

I considered suggesting run_in_executor as the primary fix since it moves blocking work off the event loop... but actually, run_in_executor itself is not directly cancellable either. The thread will continue running even if the future is cancelled. Therefore, for true cancellability of CPU-bound work, you need either multiprocessing with proper signal handling, or you need to break the work into smaller chunks with periodic await checkpoints.

So the solutions in order of practicality are:
1. Break the work into smaller chunks with periodic await points
2. Run the CPU-bound work in an executor so at least the event loop stays responsive
3. Use multiprocessing for true CPU-bound work with actual interruption
</think>

The issue is that asyncio cancellation only works at `await` points. When `process_batch()` is running synchronous CPU-bound code for 30 seconds, the event loop is completely blocked. No other coroutines run, no cancellation can be delivered, nothing happens until that synchronous call returns.

`task.cancel()` sets a flag that causes `CancelledError` to be raised at the next `await` point -- which is `await save_results(data)`, 30 seconds later.

**Solution 1: Run CPU-bound work in an executor**

```python
import asyncio
from concurrent.futures import ProcessPoolExecutor

executor = ProcessPoolExecutor(max_workers=4)

async def long_running_task():
    loop = asyncio.get_running_loop()
    try:
        while True:
            data = await loop.run_in_executor(executor, process_batch)
            await save_results(data)
    except asyncio.CancelledError:
        print("Task was cancelled, cleaning up...")
        raise
```

This moves `process_batch()` to a separate process, freeing the event loop. Cancellation can now be delivered while the CPU work runs in the background.

**Solution 2: Insert periodic checkpoints**

If you can modify `process_batch()`, break it into smaller chunks:

```python
async def long_running_task():
    try:
        while True:
            for chunk in get_chunks():
                data = process_chunk(chunk)  # takes ~1 second
                await asyncio.sleep(0)  # checkpoint: yield to event loop
            await save_results(all_data)
    except asyncio.CancelledError:
        print("Task was cancelled, cleaning up...")
        raise
```

`await asyncio.sleep(0)` yields control to the event loop without any actual delay, allowing pending cancellations to be processed.

**Important caveat with run_in_executor:** Even though the asyncio Future gets cancelled, the underlying thread or process continues running to completion. If you need to truly stop the work, you need to use a shared flag or event:

```python
cancel_event = multiprocessing.Event()

def process_batch(cancel_event):
    for i in range(1000):
        if cancel_event.is_set():
            return None
        do_work(i)
```

**Prevention tips:**
- Never run long synchronous operations directly in async code
- Use `asyncio.to_thread()` (Python 3.9+) as a simpler alternative to `run_in_executor`
- Design CPU-bound work to be interruptible with checkpoints
- Consider using `anyio` which provides better cancellation semantics via cancel scopes'''),

    ("thinking/debugging", r'''My asyncio.gather is swallowing exceptions silently:

```python
import asyncio

async def task_a():
    await asyncio.sleep(1)
    return "A done"

async def task_b():
    await asyncio.sleep(0.5)
    raise ValueError("B failed!")

async def task_c():
    await asyncio.sleep(2)
    return "C done"

async def main():
    results = await asyncio.gather(task_a(), task_b(), task_c())
    print(f"Results: {results}")

asyncio.run(main())
```

Output:
```
Traceback (most recent call last):
  File "main.py", line 17, in <module>
    asyncio.run(main())
  File "main.py", line 15, in main
    results = await asyncio.gather(task_a(), task_b(), task_c())
  File "main.py", line 9, in task_b
    raise ValueError("B failed!")
ValueError: B failed!
```

The problem is task_c never completes. When task_b fails, everything stops. I want all tasks to run to completion and then handle errors. But when I use return_exceptions=True, I'm not sure how to properly distinguish results from exceptions.''', r'''<think>
The user has two related problems. Let me untangle them.

First, without return_exceptions=True, asyncio.gather cancels remaining tasks when one fails (task_c never finishes). Could this be a bug in gather? No -- this is actually the documented default behavior. Gather propagates the first exception and cancels the rest.

Second, with return_exceptions=True, they need to distinguish successful results from exceptions in the results list. The obvious approach is `isinstance(result, Exception)`. But wait -- what if a task legitimately returns an Exception object as its value? That is rare but technically possible, and it would be a false positive. Hmm, in practice this almost never happens though, so isinstance is fine for most codebases.

I considered recommending only the return_exceptions=True pattern, but actually a better modern approach (Python 3.11+) is asyncio.TaskGroup, which provides structured concurrency. The user might not be on 3.11+ though. Therefore I should provide both approaches -- the gather-based pattern for older Python and TaskGroup for 3.11+.

Let me also think about whether TaskGroup solves the "collect all results even on failure" problem directly... actually no, TaskGroup by default cancels all tasks if one fails (like gather without return_exceptions). You need to wrap each task in a try/except inside the group to collect all results. So it is not strictly simpler for this use case.
</think>

The default behavior of `asyncio.gather` is to cancel all remaining tasks when any one task raises an exception. This is why task_c never completes. Here is how to handle this properly:

**Solution with return_exceptions=True and proper error handling:**

```python
import asyncio

async def task_a():
    await asyncio.sleep(1)
    return "A done"

async def task_b():
    await asyncio.sleep(0.5)
    raise ValueError("B failed!")

async def task_c():
    await asyncio.sleep(2)
    return "C done"

async def main():
    results = await asyncio.gather(
        task_a(), task_b(), task_c(),
        return_exceptions=True
    )

    for i, result in enumerate(results):
        if isinstance(result, Exception):
            print(f"Task {i} failed: {type(result).__name__}: {result}")
        else:
            print(f"Task {i} succeeded: {result}")

    # Separate successes from failures
    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]

    if failures:
        print(f"{len(failures)} task(s) failed")
        # Optionally re-raise the first failure
        # raise failures[0]

asyncio.run(main())
```

Output:
```
Task 0 succeeded: A done
Task 1 failed: ValueError: B failed!
Task 2 succeeded: C done
1 task(s) failed
```

**Modern approach with TaskGroup (Python 3.11+):**

```python
import asyncio

async def main():
    results = {}

    async def run_task(name, coro):
        try:
            results[name] = await coro
        except Exception as e:
            results[name] = e

    async with asyncio.TaskGroup() as tg:
        tg.create_task(run_task("a", task_a()))
        tg.create_task(run_task("b", task_b()))
        tg.create_task(run_task("c", task_c()))

    for name, result in results.items():
        if isinstance(result, Exception):
            print(f"Task {name} failed: {result}")
        else:
            print(f"Task {name} succeeded: {result}")
```

Note that TaskGroup without the try/except wrapper will raise an ExceptionGroup if any task fails, which is the structured concurrency approach -- all tasks are cancelled if one fails, similar to gather's default behavior.

**A reusable helper pattern:**

```python
async def safe_gather(*coros):
    """Run coroutines concurrently, returning (successes, failures) tuple."""
    results = await asyncio.gather(*coros, return_exceptions=True)
    successes = []
    failures = []
    for r in results:
        if isinstance(r, Exception):
            failures.append(r)
        else:
            successes.append(r)
    return successes, failures
```

**Key takeaway:** Always decide upfront whether you want fail-fast (default gather) or collect-all-results (return_exceptions=True) behavior. Most production code wants the latter, with explicit error handling for each result.'''),

    ("thinking/debugging", r'''My aiohttp application is crashing under load with connection pool exhaustion:

```
aiohttp.client_exceptions.ServerDisconnectedError: Server disconnected

During handling of the above exception, another exception occurred:

Traceback (most recent call last):
  File "app.py", line 45, in handle_request
    async with session.get(url) as resp:
  File "aiohttp/client.py", line 1138, in __aenter__
    self._resp = await self._coro
  File "aiohttp/client.py", line 536, in _request
    conn = await self._connector.connect(req, traces=traces)
  File "aiohttp/connector.py", line 542, in connect
    raise ClientConnectorError(key, exc) from exc
aiohttp.client_exceptions.ClientConnectorError: Cannot connect to host api.example.com:443 ssl:True [Too many open files]
```

Relevant code:

```python
from aiohttp import web

async def handle_request(request):
    url = f"https://api.example.com/data/{request.match_info['id']}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
    return web.json_response(data)

app = web.Application()
app.router.add_get('/proxy/{id}', handle_request)
web.run_app(app)
```

Under 500 concurrent requests, this crashes. How do I fix it?''', r'''<think>
Let me look at this error. "Too many open files" under 500 concurrent requests... could this be an OS-level ulimit issue? That might be part of it, but wait -- the code is creating a new ClientSession for every incoming request. That is the real problem.

Each ClientSession creates its own connection pool (TCPConnector). Under 500 concurrent requests, that is 500 separate connection pools, each potentially opening multiple TCP connections. So you could have thousands of file descriptors open simultaneously. Therefore the "too many open files" error is a direct consequence of the session-per-request pattern, not just an OS config issue.

I initially thought about just increasing ulimit as a fix, but actually that only masks the underlying problem. The real fix is to create a single ClientSession at app startup and reuse it across all requests. aiohttp's documentation explicitly warns against creating a session per request, because ClientSession is designed to be long-lived -- it handles connection pooling, keep-alive, and cookie sharing internally.

Hmm, I should also consider: what about timeouts? Even with a shared session, if the upstream API is slow, connections could accumulate. So I need to set explicit connection limits via TCPConnector and add request timeouts to prevent hanging connections from piling up. And the session lifecycle should be managed via on_startup/on_shutdown hooks to ensure clean shutdown.
</think>

The root cause is creating a new `aiohttp.ClientSession` for every incoming request. Each session creates its own TCP connection pool, so 500 concurrent requests means 500 separate connection pools, each opening new TCP connections. This quickly exhausts the OS file descriptor limit.

The aiohttp documentation explicitly states: "Don't create a session per request." A session is designed to be long-lived and shared.

**Fixed code:**

```python
import aiohttp
from aiohttp import web, ClientTimeout, TCPConnector

async def create_session(app):
    """Create a shared session on app startup."""
    connector = TCPConnector(
        limit=100,          # max simultaneous connections total
        limit_per_host=30,  # max simultaneous connections per host
        ttl_dns_cache=300,  # cache DNS lookups for 5 minutes
        enable_cleanup_closed=True,
    )
    timeout = ClientTimeout(
        total=30,           # total request timeout
        connect=5,          # connection timeout
        sock_read=10,       # read timeout
    )
    app['session'] = aiohttp.ClientSession(
        connector=connector,
        timeout=timeout,
    )

async def close_session(app):
    """Close session on app shutdown."""
    await app['session'].close()

async def handle_request(request):
    url = f"https://api.example.com/data/{request.match_info['id']}"
    session = request.app['session']  # reuse shared session
    try:
        async with session.get(url) as resp:
            data = await resp.json()
        return web.json_response(data)
    except aiohttp.ClientError as e:
        return web.json_response(
            {"error": str(e)}, status=502
        )

app = web.Application()
app.on_startup.append(create_session)
app.on_shutdown.append(close_session)
app.router.add_get('/proxy/{id}', handle_request)
web.run_app(app)
```

**Key changes explained:**

1. **Single shared session** created at startup, stored in `app['session']`, closed at shutdown
2. **TCPConnector limits** cap the total number of open connections (100) and per-host connections (30), preventing file descriptor exhaustion
3. **Timeouts** prevent slow upstream responses from holding connections indefinitely
4. **Error handling** catches connection errors and returns a proper 502 instead of crashing
5. **Cleanup on shutdown** ensures all connections are properly closed when the app stops

**Also increase the OS file descriptor limit** for production:
```bash
# In /etc/security/limits.conf or systemd unit
ulimit -n 65536
```

**Prevention tips:**
- Always create ClientSession at the application level, not per-request
- Set explicit connection limits based on your upstream server capacity
- Monitor open file descriptors: `ls /proc/<pid>/fd | wc -l`
- Use `aiohttp.ClientSession` as a context manager at the app lifecycle level, not the request level'''),
]
