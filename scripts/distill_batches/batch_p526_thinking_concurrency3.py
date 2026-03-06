"""Phase 1G: Foundation Thinking — Concurrency & Distributed Systems (Part 3/5)
Async patterns, queuing theory, back-pressure, rate limiting."""

PAIRS = [
    (
        "thinking/concurrency-backpressure",
        "Our data pipeline ingests events from Kafka at 50K/sec but our database can only handle 10K writes/sec. Events pile up in memory until our service OOMs and crashes. How do we handle this?",
        r'''<think>
This is a back-pressure problem — the producer is faster than the consumer. Without back-pressure, the buffer between them grows unbounded until memory is exhausted.

Solutions:
1. Bounded buffer + blocking (back-pressure to producer)
2. Batch writes (reduce per-write overhead)
3. Rate limiting the consumer
4. Dropping/sampling (if data loss is acceptable)
5. Scaling the bottleneck (more DB write capacity)

The best approach combines batching + bounded buffer + monitoring.
</think>

## The Problem: Unbounded Buffering

```
Kafka (50K/s) → [buffer grows forever] → DB (10K/s)
                       ↓
                   OOM crash 💥
```

## Fix 1: Batch Writes (Most Impact)

```python
import asyncio
from collections import deque

class BatchWriter:
    def __init__(self, db, batch_size=1000, flush_interval=1.0):
        self._db = db
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._buffer = deque(maxlen=50_000)  # Bounded!
        self._running = True

    async def add(self, record):
        if len(self._buffer) >= self._buffer.maxlen:
            raise BackPressureError("Buffer full, slow down")
        self._buffer.append(record)

    async def run(self):
        while self._running:
            if len(self._buffer) >= self._batch_size:
                await self._flush()
            else:
                await asyncio.sleep(self._flush_interval)
                if self._buffer:
                    await self._flush()

    async def _flush(self):
        batch = []
        for _ in range(min(self._batch_size, len(self._buffer))):
            batch.append(self._buffer.popleft())

        # Single bulk insert instead of 1000 individual inserts
        await self._db.execute_many(
            "INSERT INTO events (type, data, timestamp) VALUES ($1, $2, $3)",
            [(e['type'], e['data'], e['ts']) for e in batch]
        )
        # 1 bulk insert of 1000 rows ≈ 10x faster than 1000 individual inserts
```

## Fix 2: Consumer with Back-Pressure

```python
from aiokafka import AIOKafkaConsumer

async def consume_with_backpressure():
    consumer = AIOKafkaConsumer(
        'events',
        bootstrap_servers='kafka:9092',
        group_id='event-writer',
        enable_auto_commit=False,  # Manual commit after processing
        max_poll_records=1000,      # Limit records per poll
    )
    await consumer.start()

    writer = BatchWriter(db, batch_size=1000)
    asyncio.create_task(writer.run())

    try:
        async for msg in consumer:
            try:
                await writer.add(json.loads(msg.value))
            except BackPressureError:
                # Buffer full — pause consuming until buffer drains
                consumer.pause(consumer.assignment())
                await asyncio.sleep(5)
                consumer.resume(consumer.assignment())
                continue

            # Commit offset only after successfully buffered
            if msg.offset % 1000 == 0:
                await consumer.commit()
    finally:
        await consumer.stop()
```

## Fix 3: Monitoring Buffer Health

```python
import prometheus_client

buffer_size = prometheus_client.Gauge(
    'event_buffer_size', 'Current events in write buffer'
)
buffer_capacity = prometheus_client.Gauge(
    'event_buffer_capacity', 'Max buffer capacity'
)
write_latency = prometheus_client.Histogram(
    'db_batch_write_seconds', 'Time to flush a batch to DB'
)

class MonitoredBatchWriter(BatchWriter):
    async def _flush(self):
        buffer_size.set(len(self._buffer))
        with write_latency.time():
            await super()._flush()
```

## Throughput Math

```
Individual inserts:  10K/s (DB limit)
Batch inserts (1000): 10K batches × 1000 = 10M rows/s theoretical
Realistic batch:      50-100K rows/s

Batching turns a 5x overload into comfortable headroom.
```

**Rule**: Never have an unbounded buffer between a fast producer and a slow consumer. Batch writes, bound buffers, and add monitoring.'''
    ),
    (
        "thinking/concurrency-rate-limiting-algorithms",
        "I need to implement API rate limiting. What are the different algorithms and which should I use?",
        r'''<think>
Rate limiting algorithms:
1. Fixed Window — simple, allows burst at window boundaries
2. Sliding Window Log — precise but memory-intensive
3. Sliding Window Counter — good balance of precision and efficiency
4. Token Bucket — smooth rate, allows controlled bursts
5. Leaky Bucket — constant output rate

For most APIs:
- Token bucket for general rate limiting
- Sliding window counter for simplicity
- Leaky bucket for strict rate control
</think>

## The 4 Main Algorithms

### 1. Token Bucket (Most Common, Best Default)

```python
import time
import threading

class TokenBucket:
    """Allows bursts up to bucket capacity, refills at steady rate."""

    def __init__(self, rate: float, capacity: int):
        self.rate = rate          # Tokens per second
        self.capacity = capacity  # Max burst size
        self._tokens = capacity
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def allow(self) -> bool:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self.capacity,
                self._tokens + elapsed * self.rate,
            )
            self._last_refill = now

            if self._tokens >= 1:
                self._tokens -= 1
                return True
            return False

# Usage: 100 requests/minute with burst of 10
limiter = TokenBucket(rate=100/60, capacity=10)

if limiter.allow():
    process_request()
else:
    return Response(status=429, headers={'Retry-After': '1'})
```

### 2. Sliding Window Counter (Redis, Distributed)

```python
import redis
import time

def is_rate_limited(redis_client, user_id, limit=100, window=60):
    """100 requests per 60 seconds per user."""
    now = time.time()
    key = f"rate_limit:{user_id}"

    pipe = redis_client.pipeline()
    pipe.zremrangebyscore(key, 0, now - window)  # Remove old entries
    pipe.zadd(key, {str(now): now})               # Add current request
    pipe.zcard(key)                                # Count requests in window
    pipe.expire(key, window)                       # Auto-cleanup
    _, _, count, _ = pipe.execute()

    return count > limit

# Usage in middleware
@app.before_request
def rate_limit():
    if is_rate_limited(redis, request.user_id, limit=100, window=60):
        return Response(
            json.dumps({'error': 'Rate limit exceeded'}),
            status=429,
            headers={
                'Retry-After': '60',
                'X-RateLimit-Limit': '100',
                'X-RateLimit-Remaining': '0',
                'X-RateLimit-Reset': str(int(time.time()) + 60),
            },
        )
```

### 3. Fixed Window (Simplest)

```python
def fixed_window_check(redis_client, user_id, limit=100, window=60):
    window_key = f"rate:{user_id}:{int(time.time()) // window}"
    count = redis_client.incr(window_key)
    if count == 1:
        redis_client.expire(window_key, window)
    return count > limit

# Problem: allows 2x burst at window boundaries
# At 0:59 → 100 requests (allowed)
# At 1:00 → 100 more requests (new window, allowed)
# = 200 requests in 2 seconds
```

## Comparison

| Algorithm | Burst Handling | Memory | Accuracy | Best For |
|-----------|---------------|--------|----------|----------|
| Token Bucket | Controlled bursts | O(1) | Good | General API rate limiting |
| Sliding Window | No burst | O(n) | Exact | Per-user fairness |
| Fixed Window | 2x burst at edges | O(1) | Approximate | Simple cases |
| Leaky Bucket | No burst | O(1) | Good | Constant-rate output |

**Default choice**: Token bucket for API rate limiting, sliding window counter (Redis) for distributed systems.'''
    ),
    (
        "thinking/concurrency-async-task-orchestration",
        "I need to orchestrate a complex workflow: fetch user data, then based on the user's tier, either fetch premium content or standard content, then merge results. Some steps can run in parallel, others depend on previous results. How do I structure this?",
        r'''<think>
This is an async task dependency graph. The key is identifying what can run in parallel vs what has sequential dependencies.

The workflow:
1. Fetch user data (must be first — other steps depend on it)
2. Based on user tier:
   a. Premium: fetch premium content + standard content in parallel
   b. Standard: fetch only standard content
3. Merge results

Let me also consider error handling — what if one of the parallel tasks fails?
</think>

## Map the Dependency Graph

```
fetch_user ──→ check_tier ──→ fetch_content_a ──→ merge
                           └→ fetch_content_b ──┘
                           └→ fetch_preferences ─┘
```

## Implementation

```python
import asyncio

async def build_user_dashboard(user_id: int) -> dict:
    # Step 1: Sequential — everything depends on user data
    user = await fetch_user(user_id)

    # Step 2: Parallel — these are independent of each other
    if user.tier == 'premium':
        content, preferences, recommendations = await asyncio.gather(
            fetch_premium_content(user.id),
            fetch_user_preferences(user.id),
            fetch_recommendations(user.id),
        )
    else:
        content, preferences = await asyncio.gather(
            fetch_standard_content(user.id),
            fetch_user_preferences(user.id),
        )
        recommendations = []

    # Step 3: Merge results
    return {
        'user': user.to_dict(),
        'content': content,
        'preferences': preferences,
        'recommendations': recommendations,
    }
```

## With Error Handling (Partial Results)

```python
async def build_user_dashboard(user_id: int) -> dict:
    user = await fetch_user(user_id)  # Critical — fail if this fails

    # Non-critical tasks — partial results are OK
    results = await asyncio.gather(
        fetch_content(user),
        fetch_preferences(user.id),
        fetch_recommendations(user.id),
        return_exceptions=True,  # Don't crash if one fails
    )

    content, preferences, recommendations = results

    return {
        'user': user.to_dict(),
        'content': content if not isinstance(content, Exception) else [],
        'preferences': preferences if not isinstance(preferences, Exception) else {},
        'recommendations': recommendations if not isinstance(recommendations, Exception) else [],
        'errors': [
            str(r) for r in results if isinstance(r, Exception)
        ],
    }
```

## Complex Pipelines: TaskGroup (Python 3.11+)

```python
async def complex_pipeline(user_id: int):
    async with asyncio.TaskGroup() as tg:
        # All tasks run concurrently
        user_task = tg.create_task(fetch_user(user_id))
        # Can't use user_task.result() yet — it's not done

    user = user_task.result()  # Now it's done

    async with asyncio.TaskGroup() as tg:
        # Second wave — depends on first wave
        if user.tier == 'premium':
            content_task = tg.create_task(fetch_premium_content(user.id))
        else:
            content_task = tg.create_task(fetch_standard_content(user.id))
        pref_task = tg.create_task(fetch_preferences(user.id))

    return {
        'user': user,
        'content': content_task.result(),
        'preferences': pref_task.result(),
    }
```

## Rule of Thumb

```
Sequential (await one by one): When B depends on A's result
Parallel (asyncio.gather):     When tasks are independent
Staged (multiple gather):      When wave 2 depends on wave 1
```'''
    ),
    (
        "thinking/concurrency-worker-pool",
        "I need to process 100,000 images (resize, watermark, convert). Each image takes about 2 seconds. How do I parallelize this efficiently in Python?",
        r'''<think>
100,000 images × 2 seconds = 200,000 seconds = 55+ hours sequential.

Image processing is CPU-bound, so we need multiprocessing (not threading) to bypass the GIL.

With 8 cores: 55 hours / 8 = ~7 hours.
With chunking and progress tracking.

Approach:
1. ProcessPoolExecutor for CPU-bound work
2. Chunk the work for progress tracking
3. Handle errors gracefully (don't lose all progress)
4. Save results incrementally
</think>

## Efficient Parallel Image Processing

```python
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import multiprocessing

def process_image(input_path: str) -> dict:
    """Runs in a separate process — CPU-bound work."""
    try:
        from PIL import Image
        img = Image.open(input_path)
        img = img.resize((800, 600))
        img = add_watermark(img)
        output_path = input_path.replace('/input/', '/output/')
        img.save(output_path, 'WEBP', quality=85)
        return {'path': input_path, 'status': 'success'}
    except Exception as e:
        return {'path': input_path, 'status': 'error', 'error': str(e)}

def process_all_images(input_dir: str, max_workers: int = None):
    images = list(Path(input_dir).glob('**/*.{jpg,png,jpeg}'))
    total = len(images)
    max_workers = max_workers or multiprocessing.cpu_count()

    print(f"Processing {total} images with {max_workers} workers")

    completed = 0
    errors = []

    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(process_image, str(img)): img
            for img in images
        }

        for future in as_completed(futures):
            result = future.result()
            completed += 1

            if result['status'] == 'error':
                errors.append(result)

            if completed % 1000 == 0:
                print(f"Progress: {completed}/{total} "
                      f"({completed/total*100:.1f}%) "
                      f"Errors: {len(errors)}")

    print(f"Done: {completed} processed, {len(errors)} errors")
    return errors

# With 8 cores: ~7 hours instead of 55+ hours
process_all_images('/data/input/', max_workers=8)
```

## With Progress Bar and Resume Support

```python
import json
from tqdm import tqdm

def process_with_resume(input_dir, progress_file='progress.json'):
    images = list(Path(input_dir).glob('**/*.jpg'))

    # Load previous progress
    done = set()
    if Path(progress_file).exists():
        done = set(json.loads(Path(progress_file).read_text()))
        print(f"Resuming: {len(done)} already processed")

    remaining = [img for img in images if str(img) not in done]

    with ProcessPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(process_image, str(img)): img for img in remaining}

        with tqdm(total=len(remaining), desc="Processing") as pbar:
            for future in as_completed(futures):
                result = future.result()
                done.add(result['path'])
                pbar.update(1)

                # Save progress every 100 images
                if len(done) % 100 == 0:
                    Path(progress_file).write_text(json.dumps(list(done)))

    Path(progress_file).write_text(json.dumps(list(done)))
```

## Performance Comparison

```
Sequential:     100,000 × 2s = 55.6 hours
4 processes:    100,000 × 2s / 4 = 13.9 hours
8 processes:    100,000 × 2s / 8 = 6.9 hours
16 processes:   Diminishing returns (CPU contention, I/O bottleneck)
```

**Rule**: `max_workers = cpu_count()` for CPU-bound work. Going higher adds overhead without benefit.'''
    ),
    (
        "thinking/concurrency-graceful-shutdown",
        "Our worker process sometimes loses tasks when we deploy. The deployment kills the process while it's in the middle of processing a task. How do we handle graceful shutdown?",
        r'''<think>
Graceful shutdown = catch the termination signal, stop accepting new work, finish current work, then exit.

Key signals:
- SIGTERM: "please stop" (sent by Kubernetes, systemd, Docker)
- SIGINT: "ctrl+C" (development)

The pattern:
1. Register signal handlers
2. Set a "shutting down" flag
3. Stop accepting new tasks
4. Wait for current tasks to finish (with timeout)
5. Clean up resources
6. Exit
</think>

## Graceful Shutdown Pattern

```python
import signal
import threading
import time

class GracefulWorker:
    def __init__(self):
        self._shutdown_event = threading.Event()
        self._active_tasks = 0
        self._lock = threading.Lock()

        # Register signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum, frame):
        print(f"Received signal {signum}, shutting down gracefully...")
        self._shutdown_event.set()

    def run(self):
        print("Worker started, waiting for tasks...")

        while not self._shutdown_event.is_set():
            task = self._get_next_task(timeout=1)
            if task is None:
                continue

            with self._lock:
                self._active_tasks += 1

            try:
                self._process_task(task)
                self._acknowledge_task(task)
            except Exception:
                self._requeue_task(task)  # Return to queue for retry
            finally:
                with self._lock:
                    self._active_tasks -= 1

        # Shutdown: wait for active tasks to finish
        self._drain(timeout=30)
        print("Worker shut down cleanly")

    def _drain(self, timeout):
        """Wait for active tasks to complete."""
        deadline = time.time() + timeout
        while self._active_tasks > 0 and time.time() < deadline:
            print(f"Waiting for {self._active_tasks} tasks to finish...")
            time.sleep(1)

        if self._active_tasks > 0:
            print(f"WARNING: {self._active_tasks} tasks still active after timeout")

    def _get_next_task(self, timeout):
        """Get task from queue with timeout."""
        if self._shutdown_event.is_set():
            return None
        try:
            return self.task_queue.get(timeout=timeout)
        except queue.Empty:
            return None
```

## Async Version (FastAPI / asyncio)

```python
import asyncio
import signal

class AsyncWorker:
    def __init__(self):
        self._tasks: set[asyncio.Task] = set()
        self._shutdown = asyncio.Event()

    async def run(self):
        loop = asyncio.get_event_loop()
        loop.add_signal_handler(signal.SIGTERM, self._shutdown.set)
        loop.add_signal_handler(signal.SIGINT, self._shutdown.set)

        consumer = asyncio.create_task(self._consume())
        await self._shutdown.wait()

        # Stop consuming new tasks
        consumer.cancel()

        # Wait for in-flight tasks
        if self._tasks:
            print(f"Draining {len(self._tasks)} active tasks...")
            await asyncio.wait(self._tasks, timeout=30)

        print("Shutdown complete")

    async def _consume(self):
        while True:
            task_data = await self._get_next_task()
            task = asyncio.create_task(self._process(task_data))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)
```

## Kubernetes Deployment

```yaml
# deployment.yaml
spec:
  containers:
    - name: worker
      lifecycle:
        preStop:
          exec:
            command: ["sleep", "5"]  # Wait for load balancer to drain
      terminationGracePeriodSeconds: 60  # Give worker 60s to finish
```

**Key principle**: Never kill a process without giving it time to finish its current work. SIGTERM → finish tasks → SIGKILL (only after timeout).'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
