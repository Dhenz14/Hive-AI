"""Code translation pairs: Synchronous code to async equivalents."""

PAIRS = [
    (
        "code-translation/sync-to-async",
        r'''Convert this synchronous Python web scraper to async:

import requests
from bs4 import BeautifulSoup
import time

def fetch_page(url):
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return resp.text

def extract_links(html, base_url):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http"):
            links.append(href)
        elif href.startswith("/"):
            links.append(base_url.rstrip("/") + href)
    return links

def crawl(urls, max_depth=2):
    visited = set()
    results = {}
    for url in urls:
        if url in visited:
            continue
        visited.add(url)
        try:
            html = fetch_page(url)
            links = extract_links(html, url)
            results[url] = {"links": len(links), "size": len(html)}
        except Exception as e:
            results[url] = {"error": str(e)}
    return results

start = time.time()
data = crawl(["https://example.com", "https://httpbin.org"])
print(f"Done in {time.time() - start:.2f}s")''',
        r'''<think>
Converting sync requests-based scraper to async. Key changes:

1. `requests.get()` -> `aiohttp.ClientSession.get()` with `async with`
2. Sequential `for url in urls` -> `asyncio.gather()` or `asyncio.Semaphore` for bounded concurrency
3. `time.time()` still works but `asyncio.get_event_loop().time()` is also an option

BeautifulSoup parsing is CPU-bound, not I/O-bound, so it stays synchronous. But we should be aware that blocking the event loop with heavy parsing could be an issue for very large pages. For now, it's fine.

I need to add a concurrency limiter since we don't want to blast hundreds of requests simultaneously. A semaphore with, say, 10 concurrent connections is reasonable.

The visited set needs care -- in async, multiple coroutines could check and add to the set concurrently. Since we're using asyncio (single-threaded), the set operations between awaits are safe. But I should note this.
</think>

```python
import asyncio
import aiohttp
from bs4 import BeautifulSoup
import time

async def fetch_page(session, url):
    async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        resp.raise_for_status()
        return await resp.text()

def extract_links(html, base_url):
    # CPU-bound parsing stays synchronous -- no benefit from async here
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if href.startswith("http"):
            links.append(href)
        elif href.startswith("/"):
            links.append(base_url.rstrip("/") + href)
    return links

async def crawl_url(session, semaphore, url):
    async with semaphore:
        try:
            html = await fetch_page(session, url)
            links = extract_links(html, url)
            return url, {"links": len(links), "size": len(html)}
        except Exception as e:
            return url, {"error": str(e)}

async def crawl(urls, max_concurrent=10):
    semaphore = asyncio.Semaphore(max_concurrent)
    async with aiohttp.ClientSession() as session:
        tasks = [
            crawl_url(session, semaphore, url)
            for url in set(urls)  # deduplicate
        ]
        pairs = await asyncio.gather(*tasks)
    return dict(pairs)

start = time.time()
data = asyncio.run(crawl(["https://example.com", "https://httpbin.org"]))
print("Done in {:.2f}s".format(time.time() - start))
```

Key changes from sync to async:

- `requests.get()` -> `aiohttp.ClientSession.get()` with `async with` context manager
- Sequential `for url in urls: fetch(url)` -> `asyncio.gather(*tasks)` for concurrent execution
- Added `asyncio.Semaphore(10)` to limit concurrent connections -- without this, 1000 URLs would open 1000 connections simultaneously
- `extract_links` stays synchronous -- it's CPU-bound HTML parsing, not I/O
- `visited` set deduplication moved to `set(urls)` upfront since gather launches all tasks at once
- The async version fetches all URLs concurrently instead of one at a time, so wall-clock time drops from O(n * latency) to roughly O(latency)''',
    ),
    (
        "code-translation/sync-to-async",
        r'''Convert this synchronous Node.js file processing to async with proper streaming:

const fs = require("fs");

function processLargeFile(inputPath, outputPath) {
  const content = fs.readFileSync(inputPath, "utf-8");
  const lines = content.split("\n");

  const processed = lines
    .filter(line => line.trim().length > 0)
    .map(line => line.toUpperCase())
    .join("\n");

  fs.writeFileSync(outputPath, processed);
  return lines.length;
}

function processMultipleFiles(pairs) {
  const results = [];
  for (const [input, output] of pairs) {
    try {
      const count = processLargeFile(input, output);
      results.push({ input, count, status: "ok" });
    } catch (err) {
      results.push({ input, error: err.message, status: "error" });
    }
  }
  return results;
}''',
        r'''```javascript
const fs = require("fs");
const { createReadStream, createWriteStream } = require("fs");
const { createInterface } = require("readline");
const { pipeline } = require("stream/promises");
const { Transform } = require("stream");

// Stream-based processing -- never loads entire file into memory
async function processLargeFile(inputPath, outputPath) {
  let lineCount = 0;

  const upperTransform = new Transform({
    transform(chunk, encoding, callback) {
      const line = chunk.toString().trim();
      lineCount++;
      if (line.length > 0) {
        this.push(line.toUpperCase() + "\n");
      }
      callback();
    },
  });

  const rl = createInterface({
    input: createReadStream(inputPath, "utf-8"),
    crlfDelay: Infinity,
  });

  const output = createWriteStream(outputPath);

  for await (const line of rl) {
    lineCount++;
    const trimmed = line.trim();
    if (trimmed.length > 0) {
      const ok = output.write(trimmed.toUpperCase() + "\n");
      if (!ok) {
        // Backpressure: wait for drain before continuing
        await new Promise(resolve => output.once("drain", resolve));
      }
    }
  }

  output.end();
  await new Promise(resolve => output.once("finish", resolve));
  return lineCount;
}

async function processMultipleFiles(pairs) {
  // Process files concurrently with a concurrency limit
  const results = [];
  const CONCURRENCY = 4;

  for (let i = 0; i < pairs.length; i += CONCURRENCY) {
    const batch = pairs.slice(i, i + CONCURRENCY);
    const batchResults = await Promise.all(
      batch.map(async ([input, output]) => {
        try {
          const count = await processLargeFile(input, output);
          return { input, count, status: "ok" };
        } catch (err) {
          return { input, error: err.message, status: "error" };
        }
      })
    );
    results.push(...batchResults);
  }
  return results;
}

module.exports = { processLargeFile, processMultipleFiles };
```

Key changes from sync to async:

- `fs.readFileSync()` loading entire file -> `createReadStream` + `readline` processing line-by-line (constant memory usage)
- `fs.writeFileSync()` -> `createWriteStream` with backpressure handling via `drain` event
- Sequential `for` loop -> batched `Promise.all()` with concurrency limit
- `content.split("\n")` allocates a huge array for large files -> `for await (const line of rl)` processes one line at a time
- Error handling stays try/catch but wraps async operations
- Added backpressure: if the write buffer is full, we wait for `drain` before writing more''',
    ),
    (
        "code-translation/sync-to-async",
        r'''Convert this synchronous Python database access pattern to async:

import sqlite3
import time

def get_db():
    conn = sqlite3.connect("app.db")
    conn.row_factory = sqlite3.Row
    return conn

def get_user_with_orders(user_id):
    db = get_db()
    try:
        user = db.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if not user:
            return None
        orders = db.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        for order in orders:
            items = db.execute(
                "SELECT * FROM order_items WHERE order_id = ?",
                (order["id"],),
            ).fetchall()
        return {
            "user": dict(user),
            "orders": [
                {**dict(o), "items": [dict(i) for i in items]}
                for o in orders
            ],
        }
    finally:
        db.close()''',
        r'''<think>
Sync sqlite3 to async. The main options for async SQLite in Python:

1. `aiosqlite` -- async wrapper around sqlite3, uses a background thread
2. `databases` library with SQLite backend
3. `sqlalchemy` with async engine

I'll use `aiosqlite` since it's the closest drop-in replacement.

Key changes:
- `sqlite3.connect()` -> `aiosqlite.connect()` as async context manager
- `db.execute().fetchone()` -> `await db.execute()` then `await cursor.fetchone()`
- The `try/finally` with `db.close()` -> `async with` handles cleanup
- The N+1 query pattern (looping through orders to fetch items) is even worse in async because each await is a round trip. I should note this but keep the translation faithful.

Actually, I should also show how to improve it with a JOIN or at least concurrent fetching. But the user asked for translation, not optimization. I'll translate faithfully and add a note.
</think>

```python
import aiosqlite

async def get_db():
    db = await aiosqlite.connect("app.db")
    db.row_factory = aiosqlite.Row
    return db

async def get_user_with_orders(user_id):
    async with aiosqlite.connect("app.db") as db:
        db.row_factory = aiosqlite.Row

        cursor = await db.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        )
        user = await cursor.fetchone()
        if not user:
            return None

        cursor = await db.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        )
        orders = await cursor.fetchall()

        # Fetch items for each order
        order_list = []
        for order in orders:
            cursor = await db.execute(
                "SELECT * FROM order_items WHERE order_id = ?",
                (order["id"],),
            )
            items = await cursor.fetchall()
            order_list.append(
                {**dict(order), "items": [dict(i) for i in items]}
            )

        return {
            "user": dict(user),
            "orders": order_list,
        }

# Usage:
# import asyncio
# result = asyncio.run(get_user_with_orders(1))
```

Key changes from sync to async:

- `sqlite3.connect()` -> `aiosqlite.connect()` as `async with` (auto-closes on exit)
- `db.execute(...).fetchone()` -> two separate awaits: `await db.execute()` then `await cursor.fetchone()`
- `try/finally/db.close()` -> `async with` context manager handles cleanup
- Every database call needs `await` since it runs in a background thread

Note: The N+1 query pattern (one query per order for items) is especially costly in async since each `await` yields control. Better approach:

```python
# Fetch all items at once with an IN clause
order_ids = [o["id"] for o in orders]
placeholders = ",".join("?" * len(order_ids))
cursor = await db.execute(
    "SELECT * FROM order_items WHERE order_id IN (" + placeholders + ")",
    order_ids,
)
all_items = await cursor.fetchall()
# Then group by order_id in Python
```''',
    ),
    (
        "code-translation/sync-to-async",
        r'''Convert this synchronous Python task queue worker to async:

import time
import json
import redis

def process_task(task):
    task_type = task["type"]
    if task_type == "email":
        send_email(task["to"], task["subject"], task["body"])
    elif task_type == "resize":
        resize_image(task["path"], task["width"], task["height"])
    elif task_type == "report":
        generate_report(task["report_id"])
    else:
        raise ValueError(f"Unknown task type: {task_type}")

def worker(queue_name="tasks", batch_size=10):
    r = redis.Redis()
    print(f"Worker listening on {queue_name}")
    while True:
        # BLPOP blocks until a message arrives (timeout 5s)
        result = r.blpop(queue_name, timeout=5)
        if result is None:
            continue
        _, raw = result
        task = json.loads(raw)
        try:
            process_task(task)
            print(f"Completed: {task['type']}")
        except Exception as e:
            # Push to dead letter queue
            r.rpush("dead_letters", json.dumps({
                "task": task, "error": str(e)
            }))
            print(f"Failed: {task['type']}: {e}")

if __name__ == "__main__":
    worker()''',
        r'''```python
import asyncio
import json
import redis.asyncio as aioredis

async def process_task(task):
    task_type = task["type"]
    if task_type == "email":
        await send_email(task["to"], task["subject"], task["body"])
    elif task_type == "resize":
        await resize_image(task["path"], task["width"], task["height"])
    elif task_type == "report":
        await generate_report(task["report_id"])
    else:
        raise ValueError("Unknown task type: " + task_type)

async def handle_task(r, task_data):
    task = json.loads(task_data)
    try:
        await process_task(task)
        print("Completed: " + task["type"])
    except Exception as e:
        await r.rpush("dead_letters", json.dumps({
            "task": task, "error": str(e),
        }))
        print("Failed: " + task["type"] + ": " + str(e))

async def worker(queue_name="tasks", max_concurrent=10):
    r = aioredis.Redis()
    sem = asyncio.Semaphore(max_concurrent)
    print("Async worker listening on " + queue_name)

    try:
        while True:
            result = await r.blpop(queue_name, timeout=5)
            if result is None:
                continue
            _, raw = result

            # Process task concurrently with bounded parallelism
            async def bounded_handle(data=raw):
                async with sem:
                    await handle_task(r, data)

            asyncio.create_task(bounded_handle())
    except asyncio.CancelledError:
        print("Worker shutting down")
    finally:
        await r.aclose()

async def main():
    # Run multiple workers concurrently
    await asyncio.gather(
        worker("tasks"),
        worker("priority_tasks"),
    )

if __name__ == "__main__":
    asyncio.run(main())
```

Key changes from sync to async:

- `redis.Redis()` -> `redis.asyncio.Redis()` (aioredis merged into redis-py 4.2+)
- `r.blpop()` blocking call -> `await r.blpop()` non-blocking await
- Sequential task processing -> `asyncio.create_task()` for concurrent processing with semaphore limiting
- `while True` with blocking pop -> same pattern but `await` yields to event loop between tasks
- Can now run multiple workers on different queues via `asyncio.gather()` in one process
- Added `asyncio.CancelledError` handling for graceful shutdown
- The sync version processes one task at a time; the async version handles up to `max_concurrent` tasks simultaneously
- CPU-bound tasks (like resize_image) should use `asyncio.to_thread()` to avoid blocking the event loop''',
    ),
    (
        "code-translation/sync-to-async",
        r'''Convert this synchronous Python retry logic to async with exponential backoff:

import time
import random

def retry(func, max_retries=3, base_delay=1.0, max_delay=30.0):
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return func()
        except Exception as e:
            last_error = e
            if attempt == max_retries:
                break
            delay = min(base_delay * (2 ** attempt), max_delay)
            jitter = random.uniform(0, delay * 0.1)
            print(f"Attempt {attempt + 1} failed: {e}. Retrying in {delay + jitter:.1f}s")
            time.sleep(delay + jitter)
    raise last_error

# Usage:
# result = retry(lambda: requests.get("https://flaky-api.com/data").json())''',
        r'''```python
import asyncio
import random
from typing import Callable, TypeVar, Awaitable

T = TypeVar("T")

async def retry(
    func: Callable[..., Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
) -> T:
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return await func()
        except Exception as e:
            last_error = e
            if attempt == max_retries:
                break
            delay = min(base_delay * (2 ** attempt), max_delay)
            jitter = random.uniform(0, delay * 0.1)
            total = delay + jitter
            print(
                "Attempt {} failed: {}. Retrying in {:.1f}s".format(
                    attempt + 1, e, total
                )
            )
            await asyncio.sleep(total)
    raise last_error

# Usage with aiohttp:
# async def fetch():
#     async with aiohttp.ClientSession() as session:
#         async with session.get("https://flaky-api.com/data") as resp:
#             resp.raise_for_status()
#             return await resp.json()
# result = await retry(fetch)

# As a decorator:
def with_retry(**kwargs):
    def decorator(func):
        async def wrapper(*args, **kw):
            return await retry(lambda: func(*args, **kw), **kwargs)
        return wrapper
    return decorator

# @with_retry(max_retries=5, base_delay=0.5)
# async def fetch_data(url):
#     ...
```

Key changes from sync to async:

- `time.sleep(delay)` -> `await asyncio.sleep(delay)`. This is the critical change -- sync sleep blocks the entire thread; async sleep yields control to the event loop so other coroutines can run
- `func()` -> `await func()` since the wrapped function is now a coroutine
- Type hint changes: `Callable` -> `Callable[..., Awaitable[T]]` to indicate the function returns an awaitable
- The exponential backoff logic (delay calculation, jitter) stays identical -- it's pure math, not I/O
- Added a decorator version `with_retry()` for cleaner usage with async functions
- In the sync version, sleeping blocks the whole thread. In async, other tasks make progress during the retry delay''',
    ),
]
