"""
Code explanation training pairs - Async patterns (Python asyncio, JS promises, Go goroutines)
"""

pairs = [
    {
        "instruction": r'''Walk me through this Python async code:

```python
import asyncio
from contextlib import asynccontextmanager

class ConnectionPool:
    def __init__(self, max_size=10):
        self._semaphore = asyncio.Semaphore(max_size)
        self._connections = asyncio.Queue(maxsize=max_size)
        self._size = 0
        self._max_size = max_size

    async def _create_connection(self):
        await asyncio.sleep(0.1)  # simulate connection time
        self._size += 1
        return {"id": self._size, "active": True}

    @asynccontextmanager
    async def acquire(self):
        await self._semaphore.acquire()
        try:
            try:
                conn = self._connections.get_nowait()
            except asyncio.QueueEmpty:
                conn = await self._create_connection()
            yield conn
        finally:
            await self._connections.put(conn)
            self._semaphore.release()
```''',
        "output": r'''This implements an async connection pool -- a pattern that reuses expensive resources (database connections, HTTP sessions) across multiple concurrent tasks.

**The components:**

- `_semaphore` limits total concurrent usage to `max_size`. Even if 100 tasks try to acquire connections simultaneously, only 10 proceed; the rest await.
- `_connections` is an async queue holding idle connections ready for reuse.
- `_size` tracks how many connections have been created total.

**The `acquire` method (async context manager):**

1. `await self._semaphore.acquire()` -- blocks if all slots are taken. This is the throttling mechanism.

2. `self._connections.get_nowait()` -- tries to grab an idle connection from the pool without waiting. If one is available, great -- reuse it.

3. If the queue is empty (`QueueEmpty`), it creates a new connection. This is the "lazy initialization" pattern -- connections are only created when needed, not upfront.

4. `yield conn` -- the caller uses the connection inside an `async with` block.

5. The `finally` block runs when the caller is done (or if an exception occurs): the connection is returned to the queue, and the semaphore slot is released so another task can proceed.

**Key design decisions:**

- The semaphore and queue work together: the semaphore caps concurrency while the queue enables reuse. Without the semaphore, the pool could create unlimited connections if the queue is always empty.

- `_size += 1` is not thread-safe, but in asyncio that is fine -- there is only one thread, and `+=` does not yield control to the event loop, so no race condition occurs.

**Issue:** If `_create_connection` fails, the `finally` block still tries to `put(conn)`, but `conn` would be undefined. This would raise a `NameError`.'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain a JavaScript async pattern using Promise.allSettled with retry logic.
</think>

Explain what this code does and how the error handling works:

```javascript
async function fetchAllWithRetry(urls, maxRetries = 3) {
  const results = await Promise.allSettled(
    urls.map(url => fetchWithRetry(url, maxRetries))
  );

  const successes = [];
  const failures = [];

  for (const [i, result] of results.entries()) {
    if (result.status === 'fulfilled') {
      successes.push({ url: urls[i], data: result.value });
    } else {
      failures.push({ url: urls[i], error: result.reason.message });
    }
  }

  return { successes, failures };
}

async function fetchWithRetry(url, retries) {
  for (let attempt = 1; attempt <= retries; attempt++) {
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } catch (error) {
      if (attempt === retries) throw error;
      await new Promise(r => setTimeout(r, 1000 * attempt));
    }
  }
}
```''',
        "output": r'''<think>
This fetches multiple URLs concurrently with individual retry logic and categorizes results. I should explain Promise.allSettled vs Promise.all and the retry backoff.
</think>

This fetches data from multiple URLs concurrently, retrying failures individually, and returns categorized results.

**`fetchWithRetry` -- individual URL fetcher:**

Loops up to `retries` times. On each attempt:
1. Makes the HTTP request.
2. If the response status is not OK (4xx, 5xx), throws an error (since `fetch` only rejects on network errors, not HTTP errors).
3. On success, parses and returns the JSON body.
4. On failure, if attempts remain, waits with linear backoff (1s, 2s, 3s). If it was the last attempt, re-throws the error so the caller sees it.

**`fetchAllWithRetry` -- orchestrator:**

Uses `Promise.allSettled` to run all fetches concurrently. The critical difference from `Promise.all`:
- `Promise.all` short-circuits on the first rejection -- you lose results from successful fetches.
- `Promise.allSettled` waits for ALL promises to complete, regardless of success or failure. Each result is `{status: 'fulfilled', value}` or `{status: 'rejected', reason}`.

After all promises settle, it categorizes results into `successes` and `failures` arrays, pairing each with its original URL using the index.

**Practical implications:**

- If you fetch 10 URLs and 2 fail (even after retries), you still get the 8 successful results plus details about the 2 failures.
- Each URL retries independently -- one URL's retries do not delay another URL's fetch.
- All URLs start fetching simultaneously (`urls.map` kicks off all promises immediately). There is no concurrency limit, so fetching 1000 URLs would create 1000 simultaneous connections.

**The backoff timing:** `1000 * attempt` gives 1s, 2s, 3s -- linear, not exponential. Exponential backoff (`1000 * 2 ** attempt`) would be more standard for production use.'''
    },
    {
        "instruction": r'''What does this Go code do?

```go
func fanOut(ctx context.Context, input <-chan int, workers int) <-chan int {
    var wg sync.WaitGroup
    output := make(chan int)

    for i := 0; i < workers; i++ {
        wg.Add(1)
        go func() {
            defer wg.Done()
            for val := range input {
                select {
                case <-ctx.Done():
                    return
                case output <- val * val:
                }
            }
        }()
    }

    go func() {
        wg.Wait()
        close(output)
    }()

    return output
}
```''',
        "output": r'''This implements the fan-out concurrency pattern in Go -- distributing work from a single input channel across multiple worker goroutines, with support for cancellation.

**Setup:**
- Creates a `WaitGroup` to track active workers and an output channel for results.

**Worker goroutines:**
- Spawns `workers` goroutines, each doing the same thing: reading from the `input` channel, squaring the value, and sending it to `output`.
- `for val := range input` reads from the channel until it is closed. Multiple goroutines reading from the same channel is safe in Go -- each value is received by exactly one goroutine.
- The `select` statement handles two cases:
  - `ctx.Done()` -- if the context is cancelled (timeout, manual cancel), the goroutine exits immediately.
  - `output <- val * val` -- sends the result to the output channel.

**Cleanup goroutine:**
- A separate goroutine waits for all workers to finish (`wg.Wait()`) and then closes the output channel. This signals to downstream consumers that no more data is coming. Closing the channel is essential -- without it, any consumer doing `for result := range output` would block forever.

**Why this pattern is useful:**
If processing each value is slow (CPU-bound work, network calls), fan-out parallelizes it across multiple goroutines. The input channel serializes work distribution while the output channel collects results.

**Important behaviors:**
- Output order is non-deterministic. Values arrive in whatever order workers finish processing them.
- If `ctx` is cancelled, workers drain from `input` only until they hit the select. Some input values may be consumed but not processed.
- The `defer wg.Done()` ensures the WaitGroup counter decrements even if a goroutine exits early due to context cancellation.'''
    },
    {
        "instruction": r'''Explain this asyncio code:

```python
async def rate_limited(coros, rate=10, per=1.0):
    semaphore = asyncio.Semaphore(rate)
    results = []

    async def throttled(coro):
        async with semaphore:
            result = await coro
            await asyncio.sleep(per / rate)
            return result

    tasks = [asyncio.create_task(throttled(c)) for c in coros]
    for task in asyncio.as_completed(tasks):
        result = await task
        results.append(result)
    return results
```''',
        "output": r'''This executes multiple coroutines with rate limiting -- ensuring no more than a certain number run concurrently per time window.

**How the rate limiting works:**

- `Semaphore(rate)` allows at most `rate` (default 10) coroutines to be active simultaneously.
- After each coroutine completes, `asyncio.sleep(per / rate)` adds a delay before releasing the semaphore slot. With defaults of rate=10 and per=1.0, each slot sleeps for 0.1 seconds. This spaces out requests so you get roughly 10 completions per second.

**Execution flow:**

1. All coroutines are wrapped in `throttled()` and turned into tasks immediately via `create_task`. This schedules them all to run, but the semaphore gates actual execution.

2. `asyncio.as_completed(tasks)` yields futures in the order they finish (not the order they were submitted). Each yielded future is awaited to get the actual result.

3. Results are appended as they complete, so the order in `results` is completion order, not submission order.

**Issues with this implementation:**

- The `coros` parameter expects already-created coroutine objects (from calling an async function without await). But coroutine objects can only be awaited once. If the caller accidentally passes the same coroutine twice, it will fail.

- The rate limiting is approximate. The sleep happens after the coroutine completes, so if a coroutine takes a long time, the effective rate is lower than configured. For strict rate limiting, a token bucket algorithm would be more accurate.

- There is a subtle bug: if any coroutine raises an exception, `await task` will propagate it, and remaining results will be lost. Wrapping in try/except or using `return_exceptions=True` with `gather` would be more robust.'''
    },
    {
        "instruction": r'''<think>
The user wants me to explain a Python asyncio producer-consumer pattern with a bounded queue.
</think>

What does this async producer-consumer code do?

```python
async def producer(queue, items):
    for item in items:
        await queue.put(item)
        print(f"Produced: {item}")
    await queue.put(None)  # sentinel

async def consumer(queue, name, results):
    while True:
        item = await queue.get()
        if item is None:
            await queue.put(None)  # re-queue for other consumers
            break
        await asyncio.sleep(0.1)  # simulate work
        results.append((name, item * 2))
        queue.task_done()

async def main():
    queue = asyncio.Queue(maxsize=5)
    results = []
    consumers = [
        asyncio.create_task(consumer(queue, f"worker-{i}", results))
        for i in range(3)
    ]
    await producer(queue, range(20))
    await asyncio.gather(*consumers)
    return results
```''',
        "output": r'''<think>
This is a producer-consumer pattern with a bounded queue and sentinel-based shutdown. The sentinel re-queuing is the interesting part.
</think>

This implements an async producer-consumer pattern where one producer feeds work items to three parallel consumers through a bounded queue.

**The producer:**
Iterates over `items` (0 through 19) and puts each into the queue. Since `maxsize=5`, `queue.put()` will block (await) if the queue already has 5 items -- this provides backpressure, preventing the producer from overwhelming the consumers. After all items are sent, it puts `None` as a sentinel value to signal "no more work."

**The consumers:**
Each runs an infinite loop, pulling items from the queue. When a consumer gets `None`:
1. It puts `None` back into the queue -- this is the clever part. Since there are 3 consumers but only 1 sentinel, re-queuing ensures the other consumers also see the shutdown signal. Each consumer takes the sentinel, re-queues it, and exits.
2. It breaks out of the loop.

For normal items, it simulates processing (0.1s sleep), doubles the value, and appends the result with its worker name.

**`queue.task_done()`**: Signals that a dequeued item has been fully processed. This is used with `queue.join()` to wait for all items to be processed -- though `main` does not call `join()` here, relying on `gather` instead.

**The flow in `main`:**
The producer runs first (it is awaited directly, not as a task). While producing, consumers run concurrently because they were created as tasks. Once the producer finishes and consumers see the sentinel, `gather` waits for all consumers to exit.

**Subtle issue:** `task_done()` is not called for the sentinel item. If you later added `await queue.join()`, the join would hang because the internal counter would be off by one.'''
    },
]
