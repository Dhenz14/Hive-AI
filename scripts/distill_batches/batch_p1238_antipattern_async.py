"""
Anti-pattern training pairs - Async anti-patterns
Topics: fire-and-forget, swallowing exceptions, blocking event loop, callback pyramid, no backpressure
"""

pairs = [
    {
        "instruction": r'''I send analytics events in my async web handler. I don't want to slow down the response, so I fire and forget:

```python
import asyncio

async def handle_request(request):
    result = await process(request)

    # Fire and forget -- don't await
    asyncio.create_task(send_analytics(request, result))

    return Response(result)

async def send_analytics(request, result):
    async with aiohttp.ClientSession() as session:
        await session.post('https://analytics.example.com/events', json={
            'path': request.path,
            'status': result.status,
        })
```

Is there a problem with not awaiting the task?''',
        "output": r'''<think>
Fire-and-forget async task anti-pattern. The task is created but never awaited, so: (1) exceptions in send_analytics are silently lost, (2) if the server shuts down, in-flight tasks are cancelled without warning, (3) there is no limit on how many analytics tasks can be in flight simultaneously -- under high load this can exhaust memory. Need to store task references and handle errors.
</think>

Fire-and-forget tasks have three problems that will bite you in production.

**Problem 1: Silent exception loss.** If `send_analytics` raises an exception (network timeout, DNS failure), it vanishes silently. Python 3.11+ will log "Task exception was never retrieved," but many deployments suppress this.

**Problem 2: Lost on shutdown.** When your server shuts down, all un-awaited tasks are cancelled. Analytics events for the last few seconds of traffic are silently dropped.

**Problem 3: No backpressure.** Under high load, you create thousands of concurrent tasks. Each one opens an HTTP connection. You can exhaust file descriptors, memory, or overwhelm the analytics service.

**The fix -- track tasks and handle errors:**

```python
import asyncio
import logging

logger = logging.getLogger(__name__)

# Track active tasks
_background_tasks = set()

def fire_and_track(coro):
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    task.add_done_callback(_log_task_exception)

def _log_task_exception(task):
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.error("Background task failed: %s", exc)

async def handle_request(request):
    result = await process(request)
    fire_and_track(send_analytics(request, result))
    return Response(result)

# On shutdown, wait for pending tasks
async def shutdown():
    if _background_tasks:
        await asyncio.gather(*_background_tasks, return_exceptions=True)
```

**For high-throughput analytics, use a queue with backpressure:**

```python
analytics_queue = asyncio.Queue(maxsize=1000)

async def analytics_worker():
    async with aiohttp.ClientSession() as session:
        while True:
            event = await analytics_queue.get()
            try:
                await session.post(ANALYTICS_URL, json=event)
            except Exception as e:
                logger.error("Analytics send failed: %s", e)

# In handler -- bounded, non-blocking
analytics_queue.put_nowait(event)  # raises QueueFull if overloaded
```'''
    },
    {
        "instruction": r'''My async workers sometimes fail silently. I can't figure out why tasks just stop producing results:

```python
async def process_batch(items):
    tasks = []
    for item in items:
        task = asyncio.create_task(process_item(item))
        tasks.append(task)

    results = await asyncio.gather(*tasks, return_exceptions=True)
    return results

async def process_item(item):
    try:
        data = await fetch_data(item.url)
        transformed = await transform(data)
        await save_result(transformed)
    except Exception:
        pass  # don't crash the batch
```''',
        "output": r'''<think>
Swallowing exceptions in async code. The except Exception: pass silently eats all errors. Combined with return_exceptions=True in gather, failures are completely invisible. The function returns None for failed items (since save_result is never reached and nothing is returned). The user sees missing results but has zero diagnostic information. The "don't crash the batch" intent is valid but the implementation destroys all error visibility.
</think>

Your tasks fail silently because `except Exception: pass` swallows every error without logging, reporting, or returning anything. When `fetch_data` times out, `transform` raises a `ValueError`, or `save_result` hits a database error -- all of these are silently discarded.

**What the caller sees:**

```python
results = await process_batch(items)
# results = [None, None, <SavedResult>, None, None]
# Which items failed? Why? No way to know.
```

The `return_exceptions=True` in `gather` adds confusion -- it catches task-level exceptions, but your `except: pass` catches them first, so `gather` sees successful tasks that returned `None`.

**The fix -- log errors and return meaningful results:**

```python
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class ItemResult:
    item_id: str
    success: bool
    data: object = None
    error: str = None

async def process_item(item):
    try:
        data = await fetch_data(item.url)
        transformed = await transform(data)
        await save_result(transformed)
        return ItemResult(item.id, success=True, data=transformed)
    except Exception as e:
        logger.error(
            "Failed to process item %s: %s",
            item.id, e, exc_info=True
        )
        return ItemResult(item.id, success=False, error=str(e))

async def process_batch(items):
    tasks = [asyncio.create_task(process_item(item)) for item in items]
    results = await asyncio.gather(*tasks)

    succeeded = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    logger.info("Batch complete: %d succeeded, %d failed", succeeded, failed)

    return results
```

Now every failure is logged with a full traceback, the caller can inspect which items failed and why, and you can set up alerts on error rates. Never use bare `except: pass` -- it is the async equivalent of putting tape over a warning light.'''
    },
    {
        "instruction": r'''My async web server becomes unresponsive for a few seconds whenever a user uploads a large file. Other requests queue up:

```python
import hashlib

async def handle_upload(request):
    file_data = await request.read()

    # Compute hash for deduplication
    file_hash = hashlib.sha256(file_data).hexdigest()

    # Check if we already have this file
    existing = await db.find_by_hash(file_hash)
    if existing:
        return Response("Duplicate file", status=409)

    # Compress before saving
    import zlib
    compressed = zlib.compress(file_data, level=9)

    await storage.save(file_hash, compressed)
    return Response("Uploaded", status=201)
```''',
        "output": r'''<think>
Blocking the event loop with CPU-intensive synchronous operations. hashlib.sha256() on a large file and zlib.compress() with level 9 are CPU-bound operations that block the async event loop. While these run, no other coroutines can execute -- all other requests are frozen. The fix is to run CPU-bound work in a thread pool or process pool executor using asyncio.to_thread or loop.run_in_executor.
</think>

Your event loop is blocked by two CPU-intensive synchronous operations: `hashlib.sha256()` and `zlib.compress()`. While these run (potentially seconds for a large file), the event loop cannot process any other coroutines. Every other request is frozen.

**Why this happens:** `async` does not mean parallel. Python's event loop runs on a single thread. When you call a synchronous function that takes 3 seconds, the entire event loop is paused for 3 seconds. `await` only yields control when calling another coroutine or doing I/O.

**The fix -- offload CPU work to a thread or process pool:**

```python
import asyncio
import hashlib
import zlib

async def handle_upload(request):
    file_data = await request.read()

    # Run CPU-bound work in a thread pool
    file_hash = await asyncio.to_thread(
        hashlib.sha256, file_data
    )
    hex_hash = file_hash.hexdigest()

    existing = await db.find_by_hash(hex_hash)
    if existing:
        return Response("Duplicate file", status=409)

    # Compress in thread pool -- level 9 is slow
    compressed = await asyncio.to_thread(
        zlib.compress, file_data, 9
    )

    await storage.save(hex_hash, compressed)
    return Response("Uploaded", status=201)
```

`asyncio.to_thread()` runs the function in a separate thread, freeing the event loop to handle other requests while the CPU work happens.

**For truly CPU-heavy work, use a process pool** (avoids the GIL):

```python
from concurrent.futures import ProcessPoolExecutor

executor = ProcessPoolExecutor(max_workers=4)

async def handle_upload(request):
    file_data = await request.read()
    loop = asyncio.get_event_loop()

    file_hash = await loop.run_in_executor(
        executor, hashlib.sha256, file_data
    )
    ...
```

**Rule:** In async code, any synchronous call that takes more than 1ms should be offloaded. Common offenders: hashing, compression, image processing, JSON parsing of large payloads, and regex on large strings.'''
    },
    {
        "instruction": r'''I'm processing messages from a WebSocket and running async operations for each one. It works but sometimes I see "too many open files" errors:

```python
async def websocket_handler(ws):
    async for message in ws:
        data = json.loads(message)
        # Process each message concurrently
        asyncio.create_task(handle_message(data))

async def handle_message(data):
    async with aiohttp.ClientSession() as session:
        result = await session.post(PROCESSING_URL, json=data)
        response = await result.json()
        await save_to_database(response)
```''',
        "output": r'''<think>
No backpressure anti-pattern. Every incoming WebSocket message spawns a new task immediately, regardless of how many are already in flight. If messages arrive faster than handle_message can process them (due to slow HTTP calls or database writes), tasks pile up unbounded. Each task opens an HTTP connection (file descriptor), leading to "too many open files." Need a semaphore or bounded queue to limit concurrency.
</think>

You have no backpressure control. Every incoming WebSocket message immediately spawns a new concurrent task. If messages arrive at 1000/second but `handle_message` takes 500ms each, you quickly have 500+ simultaneous HTTP connections and database operations. This is why you hit "too many open files" -- each `aiohttp.ClientSession()` opens a new socket.

**The fix -- limit concurrency with a semaphore:**

```python
MAX_CONCURRENT = 50

async def websocket_handler(ws):
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    tasks = set()

    async for message in ws:
        data = json.loads(message)
        task = asyncio.create_task(
            bounded_handle(semaphore, data)
        )
        tasks.add(task)
        task.add_done_callback(tasks.discard)

    # Wait for remaining tasks on disconnect
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)

async def bounded_handle(semaphore, data):
    async with semaphore:  # blocks if 50 tasks are already running
        await handle_message(data)
```

**Also fix the ClientSession creation.** Creating a new session per message is wasteful -- each session creates a new connection pool:

```python
# Share one session across all messages
async def websocket_handler(ws):
    semaphore = asyncio.Semaphore(MAX_CONCURRENT)
    connector = aiohttp.TCPConnector(limit=MAX_CONCURRENT)

    async with aiohttp.ClientSession(connector=connector) as session:
        async for message in ws:
            data = json.loads(message)
            asyncio.create_task(
                bounded_handle(semaphore, session, data)
            )

async def bounded_handle(semaphore, session, data):
    async with semaphore:
        result = await session.post(PROCESSING_URL, json=data)
        response = await result.json()
        await save_to_database(response)
```

Now you have at most 50 concurrent operations, one shared connection pool, and proper task tracking. The semaphore provides natural backpressure -- when all 50 slots are busy, new tasks wait until a slot opens.'''
    },
    {
        "instruction": r'''I nest callbacks in my async JavaScript to ensure things run in order:

```javascript
async function syncData() {
    const users = await getUsers();

    users.forEach(async (user) => {
        const profile = await fetchProfile(user.id);

        profile.posts.forEach(async (post) => {
            const comments = await fetchComments(post.id);

            comments.forEach(async (comment) => {
                await processComment(comment);
                await updateStats(user.id);
            });
        });
    });

    console.log('All done!');  // This logs before anything finishes!
}
```''',
        "output": r'''<think>
Async forEach anti-pattern -- forEach does not await async callbacks. Each forEach fires off all its async callbacks concurrently but does not wait for them to complete. So "All done!" logs immediately while all the actual work is still in progress. This is a callback pyramid disguised as async/await. The fix is to use for...of loops or Promise.all with map.
</think>

`"All done!"` logs immediately because `forEach` does not await async callbacks. The `forEach` method ignores the returned promises -- it calls each callback, gets a Promise back, and throws it away.

**What actually happens:**
1. `getUsers()` is awaited correctly
2. `forEach` fires all user callbacks concurrently, not sequentially
3. Each inner `forEach` fires all post callbacks concurrently
4. `"All done!"` logs immediately because `forEach` returned synchronously
5. All the actual work is still running in the background

**The fix depends on what you want:**

**Sequential processing (one user at a time):**

```javascript
async function syncData() {
    const users = await getUsers();

    for (const user of users) {
        const profile = await fetchProfile(user.id);

        for (const post of profile.posts) {
            const comments = await fetchComments(post.id);

            for (const comment of comments) {
                await processComment(comment);
                await updateStats(user.id);
            }
        }
    }

    console.log('All done!');  // Now this is accurate
}
```

`for...of` respects `await` because it is a regular loop, not a callback-based method.

**Concurrent processing (all users in parallel):**

```javascript
async function syncData() {
    const users = await getUsers();

    await Promise.all(users.map(async (user) => {
        const profile = await fetchProfile(user.id);

        await Promise.all(profile.posts.map(async (post) => {
            const comments = await fetchComments(post.id);
            await Promise.all(comments.map(async (comment) => {
                await processComment(comment);
                await updateStats(user.id);
            }));
        }));
    }));

    console.log('All done!');  // Accurate -- all work is complete
}
```

**Rule:** Never use `forEach`, `map`, `filter`, or `reduce` with async callbacks unless you wrap the result in `Promise.all`. Use `for...of` for sequential async iteration.'''
    },
]
