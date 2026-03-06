"""Phase 1G: Foundation Thinking — Concurrency & Distributed Systems (Part 6)

Producer-consumer patterns, backpressure mechanisms, bounded queues, and flow control
in concurrent and distributed pipelines.
"""

PAIRS = [
    (
        "thinking/concurrency-producer-consumer-basic",
        r'''We have a web scraper that produces URLs faster than our processor can handle them.
The program eventually runs out of memory:

```python
import asyncio
import aiohttp

async def producer(queue):
    """Crawl seed pages and discover URLs."""
    seeds = ["https://example.com/page/" + str(i) for i in range(100000)]
    for url in seeds:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                html = await resp.text()
                links = extract_links(html)
                for link in links:
                    await queue.put(link)  # unbounded!

async def consumer(queue):
    """Process each URL (slow: involves DB writes)."""
    while True:
        url = await queue.get()
        await process_and_store(url)  # takes ~2 seconds each
        queue.task_done()

async def main():
    queue = asyncio.Queue()  # no maxsize
    await asyncio.gather(
        producer(queue),
        consumer(queue),
    )
```

How do we fix the memory issue and balance producer/consumer speeds?''',
        r'''<think>
The core problem: asyncio.Queue() with no maxsize is unbounded. The producer discovers
links much faster than the single consumer can process them. The queue grows without limit.

Issues to fix:
1. Unbounded queue — set maxsize so producer blocks when queue is full
2. Only one consumer — need multiple consumers to match throughput
3. Session created per URL in producer — wasteful, should reuse
4. No graceful shutdown — producer never signals "done"

With maxsize, queue.put() becomes a natural backpressure point: when the queue is full,
the producer awaits until a consumer takes an item. This automatically throttles production
to match consumption rate.

Consumer count should be tuned: if each item takes ~2s and we want to process ~50/s,
we need ~100 concurrent consumers (though in practice we'd use a semaphore or limit).
</think>

## Fix: Bounded Queue + Multiple Consumers

```python
import asyncio
import aiohttp

QUEUE_MAX = 100      # backpressure threshold
NUM_CONSUMERS = 20   # concurrent processors
SENTINEL = None      # poison pill for shutdown

async def producer(queue: asyncio.Queue):
    """Crawl seed pages, respecting backpressure from the queue."""
    seeds = ["https://example.com/page/" + str(i) for i in range(100000)]
    async with aiohttp.ClientSession() as session:  # reuse session
        for url in seeds:
            async with session.get(url) as resp:
                html = await resp.text()
                links = extract_links(html)
                for link in links:
                    # This BLOCKS when queue is full — natural backpressure
                    await queue.put(link)

    # Signal all consumers to shut down
    for _ in range(NUM_CONSUMERS):
        await queue.put(SENTINEL)

async def consumer(queue: asyncio.Queue, worker_id: int):
    """Process URLs until sentinel received."""
    while True:
        url = await queue.get()
        if url is SENTINEL:
            queue.task_done()
            break
        try:
            await process_and_store(url)
        except Exception as e:
            print(f"Worker {worker_id} error on {url}: {e}")
        finally:
            queue.task_done()

async def main():
    queue = asyncio.Queue(maxsize=QUEUE_MAX)  # bounded!
    consumers = [
        asyncio.create_task(consumer(queue, i))
        for i in range(NUM_CONSUMERS)
    ]
    await producer(queue)
    await queue.join()         # wait for all items to be processed
    await asyncio.gather(*consumers)  # clean up consumer tasks
```

**Key points:**
- `maxsize=100` means `queue.put()` awaits when full — this IS the backpressure
- Multiple consumers drain the queue in parallel
- Sentinel/poison-pill pattern for graceful shutdown
- Session reuse avoids connection churn
- Memory stays bounded: at most `maxsize` items in the queue at any time'''
    ),
    (
        "thinking/concurrency-backpressure-streaming",
        r'''Our data pipeline reads from Kafka, transforms records, and writes to a database.
Under load, the DB writer falls behind and we get OOM kills:

```python
import threading
import queue

def kafka_reader(output_q):
    consumer = KafkaConsumer('events', bootstrap_servers='kafka:9092')
    for msg in consumer:
        record = deserialize(msg.value)
        output_q.put(record)

def transformer(input_q, output_q):
    while True:
        record = input_q.get()
        enriched = enrich(record)
        output_q.put(enriched)

def db_writer(input_q):
    while True:
        record = input_q.get()
        db.insert(record)  # slow: ~50ms per record

def main():
    q1 = queue.Queue()
    q2 = queue.Queue()
    threading.Thread(target=kafka_reader, args=(q1,)).start()
    threading.Thread(target=transformer, args=(q1, q2)).start()
    threading.Thread(target=db_writer, args=(q2,)).start()
```

How do we add backpressure so the pipeline doesn't collapse under load?''',
        r'''<think>
This is a classic multi-stage pipeline without backpressure. The Kafka reader is the
fastest stage. The DB writer at ~50ms/record is the bottleneck (~20 records/sec).

Problems:
1. Both queues are unbounded — memory grows without limit
2. Single DB writer thread is the bottleneck
3. No batch writes — inserting one record at a time is inefficient
4. Kafka consumer doesn't pause when downstream is overwhelmed

Solution layers:
1. Bounded queues — `queue.Queue(maxsize=N)` blocks producers when full
2. Batch the DB writes — insert 100 records at once instead of 1
3. Multiple writer threads if needed
4. Kafka consumer can pause/resume partitions based on queue depth

The bounded queue is the simplest and most effective backpressure mechanism. When q2 is
full, the transformer blocks on put(). When q1 is full, the Kafka reader blocks. This
propagates backpressure all the way to the source.
</think>

## Fix: Bounded Queues + Batched Writes

```python
import threading
import queue
import time

MAX_QUEUE = 500        # backpressure threshold per stage
BATCH_SIZE = 100       # records per DB batch insert
BATCH_TIMEOUT = 1.0    # max seconds to wait for a full batch
NUM_WRITERS = 3        # parallel DB writer threads

def kafka_reader(output_q):
    consumer = KafkaConsumer(
        'events',
        bootstrap_servers='kafka:9092',
        max_poll_records=100,  # limit fetch size
    )
    for msg in consumer:
        record = deserialize(msg.value)
        # Blocks when queue is full — backpressure to Kafka
        output_q.put(record)

def transformer(input_q, output_q):
    while True:
        record = input_q.get()
        if record is None:
            output_q.put(None)
            break
        enriched = enrich(record)
        output_q.put(enriched)  # blocks when output_q full

def db_writer(input_q, writer_id):
    """Batch records and write in bulk."""
    batch = []
    while True:
        try:
            record = input_q.get(timeout=BATCH_TIMEOUT)
            if record is None:
                break
            batch.append(record)
        except queue.Empty:
            pass  # timeout — flush partial batch

        if len(batch) >= BATCH_SIZE or (batch and len(batch) > 0):
            if batch:
                try:
                    db.insert_many(batch)  # bulk insert
                except Exception as e:
                    print(f"Writer {writer_id} error: {e}")
                    # could retry or dead-letter here
                finally:
                    batch = []

    # Flush remaining
    if batch:
        db.insert_many(batch)

def main():
    q1 = queue.Queue(maxsize=MAX_QUEUE)  # bounded!
    q2 = queue.Queue(maxsize=MAX_QUEUE)  # bounded!

    reader = threading.Thread(target=kafka_reader, args=(q1,))
    xformer = threading.Thread(target=transformer, args=(q1, q2))
    writers = [
        threading.Thread(target=db_writer, args=(q2, i))
        for i in range(NUM_WRITERS)
    ]

    reader.start()
    xformer.start()
    for w in writers:
        w.start()

    reader.join()
    xformer.join()
    for w in writers:
        w.join()
```

**Backpressure chain:** DB full -> q2 full -> transformer blocks -> q1 full -> Kafka reader blocks -> Kafka consumer lag grows (which is fine, Kafka retains messages).

**Batching impact:** 100 records/batch at 50ms overhead ~ 2000 records/sec vs 20/sec single-row.'''
    ),
    (
        "thinking/concurrency-reactive-backpressure",
        r'''We're using RxPY (reactive extensions) to process a sensor data stream, but our
subscriber can't keep up and we lose data:

```python
import rx
from rx import operators as ops
from rx.scheduler import EventLoopScheduler

def sensor_stream():
    """Emits 1000 readings/sec from hardware sensor."""
    return rx.interval(0.001)  # every 1ms

def process_reading(value):
    """Heavy computation: FFT analysis, takes ~50ms."""
    time.sleep(0.05)
    return analyze_fft(value)

sensor_stream().pipe(
    ops.map(process_reading),
).subscribe(
    on_next=lambda x: save_result(x),
    on_error=lambda e: print(f"Error: {e}"),
)
```

The map operator blocks, causing a massive backlog. What are our options for
handling this without losing important data?''',
        r'''<think>
The problem: sensor emits every 1ms (1000/s), but processing takes 50ms per item.
Without backpressure, items queue up unboundedly.

Reactive backpressure strategies:
1. **Buffering with window** — collect N items, process as batch
2. **Sampling/throttling** — only take every Nth item or one per time window
3. **Dropping** — drop items when busy (lossy but bounded memory)
4. **Latest** — always process the most recent item, drop intermediate
5. **Parallel processing** — fan out to multiple workers

The right choice depends on requirements:
- If every reading matters: buffer + batch process
- If only latest matters: sample or use switch_map
- If approximate is OK: throttle/sample at sustainable rate

For sensor data with FFT, we likely want windows/batches — FFT on a batch of samples
is actually more useful than single-sample FFT anyway.
</think>

## Reactive Backpressure Strategies

### Option 1: Buffer + Batch Process (no data loss)

```python
sensor_stream().pipe(
    # Collect 50ms worth of readings (50 samples) into a batch
    ops.buffer_with_time(0.05),
    # Process entire batch at once — FFT on 50 samples
    ops.map(lambda batch: analyze_fft_batch(batch)),
    # Use a bounded buffer to handle temporary spikes
    ops.flat_map(lambda x: rx.of(x), max_concurrent=4),
).subscribe(on_next=save_result)
```

### Option 2: Sample at Sustainable Rate (lossy, bounded)

```python
sensor_stream().pipe(
    # Only take one reading every 50ms (matches processing speed)
    ops.sample(0.05),
    # Process on a separate scheduler to avoid blocking
    ops.observe_on(EventLoopScheduler()),
    ops.map(process_reading),
).subscribe(on_next=save_result)
```

### Option 3: Drop When Busy (latest wins)

```python
from concurrent.futures import ThreadPoolExecutor

pool = ThreadPoolExecutor(max_workers=4)

sensor_stream().pipe(
    # Buffer the latest N, drop oldest if overflowing
    ops.buffer_with_count(50),
    # Only keep the latest buffer if we fall behind
    ops.flat_map(
        lambda batch: rx.from_future(
            pool.submit(analyze_fft_batch, batch)
        ),
        max_concurrent=4,  # at most 4 in-flight
    ),
).subscribe(on_next=save_result)
```

### Option 4: Explicit Backpressure with Semaphore

```python
import asyncio

semaphore = asyncio.Semaphore(4)  # max 4 concurrent

async def controlled_process(value):
    async with semaphore:
        return await asyncio.to_thread(process_reading, value)

# Using async generator with backpressure
async def pipeline():
    async for reading in sensor_aiter():
        result = await controlled_process(reading)
        await save_result_async(result)
```

**Decision guide:**
| Strategy | Data Loss | Memory | Latency | Best For |
|----------|-----------|--------|---------|----------|
| Buffer+Batch | None | Bounded | Batch delay | Analytics, FFT |
| Sample | Yes | Minimal | Low | Real-time display |
| Drop oldest | Yes | Bounded | Low | Latest-value monitoring |
| Semaphore | None* | Bounded | Variable | Mixed workloads |

*Semaphore approach blocks the producer, so upstream must tolerate pauses.'''
    ),
    (
        "thinking/concurrency-producer-consumer-multiprocess",
        r'''Our CPU-intensive image processing pipeline uses multiprocessing but deadlocks
under heavy load:

```python
import multiprocessing as mp

def producer(queue):
    for image_path in glob.glob("/data/images/*.jpg"):
        img = load_image(image_path)
        queue.put(img)  # puts full image array into queue
    queue.put(None)  # sentinel

def consumer(queue, result_queue):
    while True:
        img = queue.get()
        if img is None:
            queue.put(None)  # re-put sentinel for other consumers
            break
        result = heavy_cv_processing(img)
        result_queue.put(result)

def main():
    work_q = mp.Queue()
    result_q = mp.Queue()
    procs = []
    for _ in range(mp.cpu_count()):
        p = mp.Process(target=consumer, args=(work_q, result_q))
        p.start()
        procs.append(p)

    producer(work_q)

    for p in procs:
        p.join()

    results = []
    while not result_q.empty():
        results.append(result_q.get())
```

This deadlocks with large images. Why, and how do we fix it?''',
        r'''<think>
Several issues here:

1. **mp.Queue uses pipes with finite buffer.** When you put() large objects (image arrays
   can be megabytes), the underlying pipe buffer fills up. If a process is trying to put()
   into result_q while result_q's pipe is full, AND the main process is blocked in p.join()
   instead of draining result_q, we get a deadlock. The consumer can't finish because it
   can't put results, and main can't read results because it's waiting for consumers to finish.

2. **Putting full image arrays into the queue** is extremely expensive — mp.Queue pickles
   objects and sends them through a pipe. Large numpy arrays get copied between processes.
   Better to send file paths and let each worker load its own image.

3. **Sentinel propagation** with re-putting is fragile. If N consumers and 1 sentinel,
   only 1 consumer sees it, re-puts it, but timing issues can cause problems.

The classic deadlock: main calls p.join() before draining result_q. Consumer blocks on
result_q.put() because pipe is full. join() never returns.

Fix:
- Drain result_q BEFORE joining processes (or use a separate thread to drain)
- Send paths not data
- Use bounded queue for backpressure
- Proper shutdown with N sentinels
</think>

## Root Cause: Deadlock Between join() and Queue Pipe Buffer

The deadlock happens because:
1. Consumer calls `result_q.put(result)` — pipe buffer is full
2. Main calls `p.join()` — waits for consumer to exit
3. Consumer can't exit until `put()` completes
4. `put()` can't complete until someone reads from `result_q`
5. Nobody reads from `result_q` because main is stuck in `join()`

## Fixed Version

```python
import multiprocessing as mp
from multiprocessing import Queue
import glob

SENTINEL = "DONE"

def producer(queue, num_consumers):
    """Send file paths (not data!) and proper shutdown signals."""
    paths = glob.glob("/data/images/*.jpg")
    for path in paths:
        queue.put(path)  # send path, not image data
    # One sentinel per consumer — no re-put race condition
    for _ in range(num_consumers):
        queue.put(SENTINEL)

def consumer(work_q, result_q):
    """Load and process images locally."""
    while True:
        item = work_q.get()
        if item == SENTINEL:
            break
        try:
            img = load_image(item)  # load in worker process
            result = heavy_cv_processing(img)
            result_q.put((item, result))
        except Exception as e:
            result_q.put((item, None))  # don't lose track

def main():
    num_workers = mp.cpu_count()
    work_q = Queue(maxsize=num_workers * 2)   # backpressure
    result_q = Queue(maxsize=num_workers * 2)  # bounded results

    # Start consumers
    procs = []
    for _ in range(num_workers):
        p = mp.Process(target=consumer, args=(work_q, result_q))
        p.start()
        procs.append(p)

    # Run producer in a thread so main can drain results concurrently
    import threading
    prod_thread = threading.Thread(
        target=producer, args=(work_q, num_workers)
    )
    prod_thread.start()

    # Drain results WHILE consumers are running (prevents deadlock)
    results = []
    finished_count = 0
    while finished_count < num_workers:
        try:
            item = result_q.get(timeout=5.0)
            results.append(item)
        except Exception:
            # Check if all workers are still alive
            alive = sum(1 for p in procs if p.is_alive())
            if alive == 0:
                break

    prod_thread.join()
    for p in procs:
        p.join(timeout=10)

    print(f"Processed {len(results)} images")
```

**Key fixes:**
1. **Drain result_q before/during join()** — prevents pipe buffer deadlock
2. **Send paths, not images** — avoids pickling multi-MB arrays through pipes
3. **One sentinel per consumer** — no re-put race condition
4. **Bounded queues** — backpressure prevents memory explosion
5. **Producer in separate thread** — main is free to drain results'''
    ),
    (
        "thinking/concurrency-backpressure-http-api",
        r'''Our API server receives burst traffic and forwards requests to a slow downstream
service. During spikes, our server runs out of memory and connections:

```python
from fastapi import FastAPI
import httpx

app = FastAPI()
client = httpx.AsyncClient()

@app.post("/process")
async def process_request(data: dict):
    # Forward to slow ML inference service (~5 seconds per request)
    response = await client.post(
        "http://ml-service:8080/predict",
        json=data,
        timeout=30.0,
    )
    return response.json()
```

During a traffic spike (1000 req/s), the server creates thousands of concurrent
connections to the ML service, which crashes. How do we add backpressure?''',
        r'''<think>
The problem: every incoming request immediately fires an outbound HTTP call to the ML
service. With 1000 req/s and 5s processing time, that's 5000 concurrent connections.
The ML service can't handle that, and our server holds 5000 open connections in memory.

Backpressure options for an HTTP API:
1. **Semaphore** — limit concurrent outbound requests, queue the rest
2. **Connection pool limits** on the httpx client
3. **Rate limiting** — reject excess requests with 429
4. **Request queue with bounded depth** — accept, queue, reject when full
5. **Load shedding** — fast rejection when system is overloaded

Best approach: combine semaphore (limit concurrency to what ML service can handle) with
load shedding (reject with 503 when queue is too deep).

The semaphore approach is clean: if ML service handles 20 concurrent requests well, use
Semaphore(20). Requests 21+ wait. If wait queue gets too deep, shed load with 503.
</think>

## Fix: Semaphore + Load Shedding + Connection Pool Limits

```python
from fastapi import FastAPI, HTTPException
import httpx
import asyncio
import time

app = FastAPI()

# Limit concurrent requests to ML service
MAX_CONCURRENT = 20       # what ML service can handle
MAX_WAITING = 100         # max requests waiting in queue
SHED_TIMEOUT = 10.0       # max time to wait for a slot

# Track queue depth for load shedding
_waiting_count = 0
_semaphore = asyncio.Semaphore(MAX_CONCURRENT)

# Connection pool limits on the HTTP client
client = httpx.AsyncClient(
    limits=httpx.Limits(
        max_connections=MAX_CONCURRENT,
        max_keepalive_connections=MAX_CONCURRENT,
    ),
    timeout=httpx.Timeout(30.0, connect=5.0),
)

@app.post("/process")
async def process_request(data: dict):
    global _waiting_count

    # Load shedding: reject immediately if too many waiting
    if _waiting_count >= MAX_WAITING:
        raise HTTPException(
            status_code=503,
            detail="Service overloaded, try again later",
            headers={"Retry-After": "5"},
        )

    _waiting_count += 1
    try:
        # Wait for a concurrency slot (with timeout)
        try:
            await asyncio.wait_for(
                _semaphore.acquire(), timeout=SHED_TIMEOUT
            )
        except asyncio.TimeoutError:
            raise HTTPException(
                status_code=503,
                detail="Request timed out waiting for capacity",
                headers={"Retry-After": "10"},
            )

        try:
            response = await client.post(
                "http://ml-service:8080/predict",
                json=data,
            )
            return response.json()
        finally:
            _semaphore.release()
    finally:
        _waiting_count -= 1

@app.get("/health")
async def health():
    """Expose backpressure metrics for load balancer."""
    return {
        "status": "ok",
        "concurrent_requests": MAX_CONCURRENT - _semaphore._value,
        "waiting_requests": _waiting_count,
        "capacity_pct": round(
            (MAX_CONCURRENT - _semaphore._value) / MAX_CONCURRENT * 100
        ),
    }
```

**Backpressure layers:**

| Layer | Mechanism | Effect |
|-------|-----------|--------|
| Connection pool | `httpx.Limits(max_connections=20)` | Hard cap on outbound connections |
| Semaphore | `asyncio.Semaphore(20)` | Queue excess requests in-process |
| Load shedding | `_waiting_count >= 100` | Fast 503 rejection when overloaded |
| Timeout | `wait_for(..., timeout=10)` | Don't let requests wait forever |
| Health endpoint | `/health` | Load balancer can route away from overloaded instances |

**Client-side cooperation:** Return `Retry-After` header so clients use exponential backoff instead of hammering the server.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
