"""Thinking-trace pairs: advanced Celery debugging."""

PAIRS = [
    (
        "thinking/debugging",
        r'''My Celery tasks are not being routed to the correct queue. I have two queues -- "default" and "priority" -- but all tasks end up in "default" regardless of the routing configuration. Here is my setup:

# celery_config.py
from celery import Celery

app = Celery("myapp", broker="redis://localhost:6379/0")

app.conf.task_routes = {
    "myapp.tasks.send_email": {"queue": "priority"},
    "myapp.tasks.generate_report": {"queue": "default"},
}

# tasks.py
from celery_config import app

@app.task
def send_email(to, subject, body):
    # ... send email ...
    pass

@app.task
def generate_report(report_id):
    # ... generate report ...
    pass

# Running workers:
# celery -A celery_config worker -Q default,priority --loglevel=info

# All tasks go to "default" queue. What is wrong?''',
        r'''<think>
All tasks go to "default" despite having routing configured. Let me look at this more carefully.

The routes are defined as `"myapp.tasks.send_email": {"queue": "priority"}`. But the tasks are defined in `tasks.py` with `@app.task` -- no explicit `name=` parameter. So what is the actual auto-generated name?

Celery generates task names as `module_name.function_name`. The tasks are in `tasks.py`, so the auto-generated name would be `tasks.send_email`, not `myapp.tasks.send_email`. The route key does not match the actual task name, so the route never applies and Celery falls back to the default queue.

Could it be something else? Maybe the worker is not actually listening on the priority queue? The command shows `-Q default,priority`, so that looks correct. Could it be an import ordering issue where `task_routes` is set after the tasks are registered? Actually no, routes are checked at send time, not at registration time.

What about `.delay()` vs `.apply_async()`? Could the caller be explicitly specifying a queue that overrides the route? That is possible but the user did not mention it.

Let me go back to the name mismatch theory. I can verify: if you run `celery -A celery_config inspect registered`, it would show the actual names. The name `myapp` in `Celery("myapp", ...)` is the app name, but it does NOT prefix task names. Task names come from the module where they are defined. So `"myapp.tasks.send_email"` in the routes will never match `"tasks.send_email"` -- that is definitely the bug.

The fix is either: (a) change the route keys to match the actual names (`tasks.send_email`), or (b) set explicit `name=` on each task decorator to force the expected name. Option (b) is more robust because it survives file reorganization.
</think>

The issue is a **task name mismatch** in your routing configuration. Celery auto-generates task names from the module path, and the names in `task_routes` do not match the actual names.

```python
# ============================================================
# DIAGNOSIS: Check actual task names
# ============================================================
# When you define @app.task in tasks.py, the auto-generated name is:
#   "tasks.send_email" (module.function)
# NOT:
#   "myapp.tasks.send_email"
#
# Your routing uses "myapp.tasks.send_email" which never matches,
# so Celery falls back to the default queue.

# Run this to see actual task names:
# celery -A celery_config inspect registered

# ============================================================
# FIX 1: Use correct task names in routes
# ============================================================

# celery_config.py
from celery import Celery

app = Celery("myapp", broker="redis://localhost:6379/0")

# Use the ACTUAL auto-generated names
app.conf.task_routes = {
    "tasks.send_email": {"queue": "priority"},
    "tasks.generate_report": {"queue": "default"},
}

# ============================================================
# FIX 2: Set explicit task names to avoid ambiguity
# ============================================================

# tasks.py
from celery_config import app

@app.task(name="myapp.tasks.send_email")
def send_email(to, subject, body):
    """Now the name matches the route exactly."""
    pass

@app.task(name="myapp.tasks.generate_report")
def generate_report(report_id):
    pass

# celery_config.py routes stay as they were:
app.conf.task_routes = {
    "myapp.tasks.send_email": {"queue": "priority"},
    "myapp.tasks.generate_report": {"queue": "default"},
}

# ============================================================
# FIX 3: Use a router class for complex routing logic
# ============================================================

class TaskRouter:
    """Route tasks based on custom logic."""

    def route_for_task(self, task, args=None, kwargs=None):
        # Route by task name pattern
        if "email" in task or "notification" in task:
            return {"queue": "priority"}
        if "report" in task or "export" in task:
            return {"queue": "default"}
        # Fallback
        return {"queue": "default"}

app.conf.task_routes = (TaskRouter(),)

# ============================================================
# FIX 4: Use wildcard patterns in routes
# ============================================================

app.conf.task_routes = {
    "tasks.send_*": {"queue": "priority"},
    "tasks.generate_*": {"queue": "default"},
    # Catch-all
    "*": {"queue": "default"},
}

# ============================================================
# VERIFICATION: Confirm routing works
# ============================================================

# 1. Check what queue a task would be routed to:
from celery_config import app as celery_app

router = celery_app.amqp.router
route = router.route(
    celery_app.amqp.queues, "tasks.send_email", args=(), kwargs={}
)
print(f"send_email routes to: {route}")

# 2. Run separate workers per queue for isolation:
# Terminal 1: celery -A celery_config worker -Q priority -c 4 --loglevel=info
# Terminal 2: celery -A celery_config worker -Q default -c 2 --loglevel=info

# 3. Monitor queues in Redis:
# redis-cli LLEN priority   (shows pending task count)
# redis-cli LLEN default

# 4. When calling tasks, verify the queue:
result = send_email.apply_async(
    args=("user@example.com", "Hello", "Body"),
    # You can also override the queue at call time:
    # queue="priority",
)
print(f"Task {result.id} sent to queue")
```

**Debugging checklist for Celery routing:**
1. Run `celery inspect registered` to see actual task names
2. Compare registered names against your `task_routes` keys
3. Use explicit `name=` parameter in `@app.task()` to avoid auto-naming surprises
4. Use `router.route()` to programmatically verify routing before deploying
5. Run separate workers per queue to confirm isolation''',
    ),
    (
        "thinking/debugging",
        r'''My Celery chord is hanging indefinitely. The header tasks complete but the callback never executes. Here is my code:

from celery import chord, group
from celery_app import app

@app.task
def fetch_data(source_id):
    return {"source": source_id, "data": get_data(source_id)}

@app.task
def aggregate_results(results):
    combined = {}
    for r in results:
        combined[r["source"]] = r["data"]
    return combined

# This hangs -- header tasks finish but aggregate_results never runs
result = chord(
    [fetch_data.s(i) for i in range(10)],
    aggregate_results.s()
)()

print(result.get(timeout=60))  # TimeoutError after 60 seconds''',
        r'''<think>
A chord that hangs -- the header tasks finish but the callback never fires. This is one of the trickiest Celery issues.

First question: is there a result backend configured? I do not see one in the code. The Celery app is created with `Celery("myapp", broker="redis://...")` but no `backend=` parameter. Chords rely on the result backend to know when all header tasks are complete. Without a result backend, the chord has no way to detect that all 10 fetch_data tasks finished, so the callback never triggers. That could be the entire problem right there.

But let me consider other possibilities in case the user has a backend configured elsewhere. Could it be the RPC backend? If they have `result_backend = "rpc://"`, that would not work either -- RPC is a peer-to-peer backend that cannot aggregate results from multiple tasks.

What about task failures? If even one of the 10 `fetch_data` tasks throws an exception, the chord callback is never called by default. The chord just sits there forever. The user would not necessarily know because the failed task's exception is stored in the result backend (if it exists), not raised to the caller until they inspect it.

Actually, there is a more subtle issue: deadlock from prefetch. Say the worker has `concurrency=4`. It starts processing 4 header tasks. The remaining 6 header tasks are queued. But Celery might also prefetch the callback task. Now the callback is sitting in the worker's prefetch buffer, but it cannot execute until all header tasks finish, and header tasks cannot finish until worker slots open up. If the worker grabbed the callback before the remaining header tasks... wait, that should not deadlock because the callback is only triggered after all headers complete. Unless the worker's prefetch buffer is full and it is not pulling new header tasks.

I think the most likely cause here is the missing result backend. Let me lead with that and also cover the failure-handling and prefetch scenarios.
</think>

Celery chords hanging is one of the most common Celery issues. Here are the causes and fixes:

```python
from celery import Celery, chord, group, chain
from celery.exceptions import ChordError

# ============================================================
# CAUSE 1: No result backend (most common)
# ============================================================
# Chords REQUIRE a result backend. Without one, the chord
# has no way to know when all header tasks are done.

# WRONG:
# app = Celery("myapp", broker="redis://localhost:6379/0")
# No backend = chord hangs forever

# CORRECT:
app = Celery(
    "myapp",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/1",  # REQUIRED for chords
)

# ============================================================
# CAUSE 2: Using RPC backend (does not support chords)
# ============================================================
# WRONG:
# app.conf.result_backend = "rpc://"
# RPC backend is peer-to-peer and cannot aggregate results

# CORRECT backends for chords: redis, database, memcached

# ============================================================
# CAUSE 3: Header task failure kills the chord silently
# ============================================================

@app.task(bind=True, max_retries=3)
def fetch_data(self, source_id):
    try:
        data = get_data(source_id)
        return {"source": source_id, "data": data}
    except Exception as exc:
        # Retry on failure instead of letting it kill the chord
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

@app.task
def aggregate_results(results):
    combined = {}
    for r in results:
        if r is not None:
            combined[r["source"]] = r["data"]
    return combined

# Add error callback to see chord failures
@app.task
def chord_error_handler(request, exc, traceback):
    print(f"Chord failed! Task {request.id}: {exc}")

result = chord(
    [fetch_data.s(i) for i in range(10)],
    aggregate_results.s()
).on_error(chord_error_handler.s())()

# ============================================================
# CAUSE 4: Worker deadlock from prefetch
# ============================================================
# If you have concurrency=4 and launch a chord with 10 tasks,
# the callback task might be prefetched but cannot run because
# all 4 worker slots are busy with header tasks.

# FIX: Use task_acks_late and worker_prefetch_multiplier
app.conf.update(
    # Do not prefetch more tasks than the worker can handle
    worker_prefetch_multiplier=1,
    # Acknowledge tasks after they complete, not when received
    task_acks_late=True,
    # Prevent the callback from being prefetched too early
    worker_concurrency=4,
)

# BETTER FIX: Route chord callbacks to a separate queue
app.conf.task_routes = {
    "myapp.tasks.aggregate_results": {"queue": "callbacks"},
}
# Run a dedicated worker: celery -A myapp worker -Q callbacks -c 2

# ============================================================
# CAUSE 5: Chord results expire before callback runs
# ============================================================
app.conf.result_expires = 3600  # Results expire after 1 hour
# If header tasks are slow and results expire before all finish,
# the chord callback never has complete data

# FIX: Increase result expiry
app.conf.result_expires = 86400  # 24 hours

# ============================================================
# ALTERNATIVE: Replace chord with manual aggregation
# ============================================================
# If chords are too fragile, do it manually:

@app.task
def fetch_and_collect(source_ids):
    """Fetch all sources sequentially (simpler, no chord needed)."""
    results = []
    for sid in source_ids:
        try:
            results.append({"source": sid, "data": get_data(sid)})
        except Exception as e:
            results.append({"source": sid, "error": str(e)})
    return results

# Or use group + polling:
async def aggregate_with_group(source_ids):
    """Use group and poll results instead of chord."""
    job = group(fetch_data.s(i) for i in source_ids)()
    results = job.get(timeout=120, interval=0.5)
    return aggregate_results(results)
```

**Key takeaways:**
1. Chords always need a result backend (Redis or database, NOT RPC)
2. Add `.on_error()` callback to see why chords fail
3. Set `worker_prefetch_multiplier=1` to prevent deadlocks
4. Handle header task failures with retries
5. Consider replacing chords with simpler patterns if reliability is critical''',
    ),
    (
        "thinking/debugging",
        r'''My Celery worker is consuming messages too aggressively, grabbing all available tasks and leaving other workers idle. Memory usage spikes because tasks are loaded into memory before they can be processed. How do I control prefetching?''',
        r'''<think>
The worker is grabbing all available tasks and other workers sit idle. This sounds like aggressive prefetching.

How does Celery prefetching work? By default, `worker_prefetch_multiplier=4`, which means each worker process prefetches 4 messages. With `concurrency=8` (the default on an 8-core machine), that is 4 * 8 = 32 messages grabbed at once. If you have 3 workers and 100 tasks, the first worker to connect might grab 32, leaving 68 for the other two. That is uneven but not terrible. But if tasks are slow and keep arriving, one worker can accumulate a huge backlog while others idle.

Could this be a `task_acks_late` issue? By default, Celery acknowledges tasks when they are received (prefetched), not when they are completed. So if a worker crashes, those prefetched tasks are lost. Setting `task_acks_late=True` means tasks are ack'd after completion, so if a worker dies, the tasks return to the queue. But does that help with distribution? Not directly -- you still need to reduce the prefetch multiplier.

What about setting `worker_prefetch_multiplier=1`? That means each process only grabs 1 extra task. With concurrency=8, that is 8 prefetched messages total. That is much fairer. But there is a tradeoff: with prefetch=1, the worker might briefly idle between tasks while waiting for the next message from the broker, slightly reducing throughput. For CPU-bound or I/O-bound tasks that take seconds, this overhead is negligible. For very fast tasks (millisecond-level), the reduced prefetch could hurt throughput.

Actually, the user also mentions memory spikes. That makes sense -- if 32 tasks are prefetched and each carries a large payload (like a dataset), they all sit in memory waiting to be processed. Reducing prefetch directly fixes the memory issue too.

So the recommendation is: `worker_prefetch_multiplier=1` + `task_acks_late=True` for fair distribution and crash safety. For memory-heavy tasks, also set `worker_max_memory_per_child` to hard-cap memory usage per worker process.
</think>

Celery's default prefetching behavior can cause uneven work distribution and memory issues. Here is how to control it:

```python
from celery import Celery

app = Celery("myapp", broker="redis://localhost:6379/0")

# ============================================================
# PROBLEM: Default prefetch settings
# ============================================================
# Default: worker_prefetch_multiplier = 4
# With concurrency=8, each worker prefetches 4 * 8 = 32 messages
# If you have 100 tasks and 3 workers, worker 1 might grab 32,
# leaving only 68 for the other two workers.

# ============================================================
# FIX 1: Reduce prefetch multiplier
# ============================================================
app.conf.update(
    # Each worker process prefetches only 1 task at a time
    worker_prefetch_multiplier=1,

    # Acknowledge task AFTER it completes, not when received
    # This means if a worker crashes, the task returns to the queue
    task_acks_late=True,

    # Reject tasks back to the queue when worker shuts down
    worker_cancel_long_running_tasks_on_connection_loss=True,
)

# ============================================================
# FIX 2: Disable prefetch entirely (for long-running tasks)
# ============================================================
app.conf.update(
    # -1 means "do not limit" but with acks_late, effectively
    # the worker only takes one at a time
    worker_prefetch_multiplier=1,
    task_acks_late=True,

    # For truly fair scheduling, use the solo pool:
    # celery -A myapp worker --pool=solo
    # This processes one task at a time (no concurrency)
)

# ============================================================
# FIX 3: Use task rate limits for resource-intensive tasks
# ============================================================

@app.task(rate_limit="10/m")  # Max 10 per minute per worker
def heavy_task(data):
    """Memory-intensive task that should be rate-limited."""
    process_large_dataset(data)

@app.task(rate_limit="100/m")  # 100 per minute
def light_task(item_id):
    """Light task that can run more frequently."""
    update_item(item_id)

# ============================================================
# FIX 4: Set memory limits to prevent OOM
# ============================================================
app.conf.update(
    # Restart worker after processing N tasks (prevents memory leaks)
    worker_max_tasks_per_child=100,

    # Restart worker if memory exceeds limit (in KB)
    worker_max_memory_per_child=200_000,  # 200 MB
)

# ============================================================
# FIX 5: Use priority queues for mixed workloads
# ============================================================
from kombu import Queue

app.conf.task_queues = (
    Queue("high", routing_key="high"),
    Queue("default", routing_key="default"),
    Queue("low", routing_key="low"),
)

# Start workers with different concurrency per queue:
# celery -A myapp worker -Q high -c 4 --prefetch-multiplier=1
# celery -A myapp worker -Q default -c 8 --prefetch-multiplier=2
# celery -A myapp worker -Q low -c 2 --prefetch-multiplier=1

# ============================================================
# MONITORING: Check queue depths and worker utilization
# ============================================================

def check_queue_health():
    """Monitor queue depths to detect prefetch imbalance."""
    inspector = app.control.inspect()

    # Active tasks (currently executing)
    active = inspector.active()
    # Reserved tasks (prefetched, waiting to execute)
    reserved = inspector.reserved()
    # Scheduled tasks (ETA/countdown)
    scheduled = inspector.scheduled()

    for worker, tasks in (reserved or {}).items():
        active_count = len((active or {}).get(worker, []))
        reserved_count = len(tasks)
        print(
            f"{worker}: active={active_count}, "
            f"reserved={reserved_count}"
        )
        if reserved_count > 10:
            print(f"  WARNING: {worker} has too many prefetched tasks!")

    # Check Redis queue lengths
    import redis
    r = redis.Redis(host="localhost", port=6379, db=0)
    for queue_name in ["high", "default", "low"]:
        length = r.llen(queue_name)
        print(f"Queue '{queue_name}': {length} pending tasks")

# Run: python -c "from tasks import check_queue_health; check_queue_health()"
```

**Summary of settings:**
- `worker_prefetch_multiplier=1` -- fair distribution across workers
- `task_acks_late=True` -- tasks survive worker crashes
- `worker_max_tasks_per_child=100` -- prevents memory leaks
- `worker_max_memory_per_child=200000` -- hard memory limit
- Use separate queues and workers for different task types''',
    ),
    (
        "thinking/debugging",
        r'''I have Celery tasks with different priorities but higher priority tasks are not being processed first. Here is my setup:

from celery import Celery

app = Celery("myapp", broker="redis://localhost:6379/0")

@app.task(priority=9)
def urgent_task(data):
    process_urgent(data)

@app.task(priority=1)
def background_task(data):
    process_background(data)

# I queue 100 background_tasks, then queue 1 urgent_task
# The urgent_task waits behind all 100 background_tasks
# Priority is not working!''',
        r'''<think>
The user sets `priority=9` on one task and `priority=1` on another, but priority is ignored. Let me think about why.

The broker is Redis: `broker="redis://localhost:6379/0"`. That is the key detail. Redis queues are just lists -- LPUSH to add, BRPOP to remove. Lists are FIFO. There is no concept of priority in a Redis list. So the `priority` parameter on `@app.task` is effectively ignored when using Redis as the broker.

Wait, does Celery's Redis transport support priorities at all? Actually yes, there is an opt-in mechanism: `broker_transport_options = {"priority_steps": list(range(10))}`. This creates separate Redis lists for each priority level (like `celery:0`, `celery:1`, etc.) and the worker polls them in order. But this is not enabled by default, so without that config, priorities are silently ignored.

Could the user switch to RabbitMQ instead? RabbitMQ has native priority queue support -- you set `task_queue_max_priority=10` and the `priority` parameter just works. But switching brokers is a big infrastructure change.

The more practical solution for Redis is to use separate queues: `urgent`, `normal`, `background`. Then you start workers with `-Q urgent,normal,background` and Celery consumes from queues left to right -- it drains `urgent` before checking `normal`. This gives effective priority ordering without any special transport options.

The tradeoff between priority_steps and separate queues: priority_steps is simpler (one queue, just add priorities) but adds polling overhead since the worker checks 10 lists on each cycle. Separate queues let you allocate different numbers of workers per priority level, giving you finer control over capacity. For production, I would lean toward separate queues with dedicated workers.
</think>

Task priorities in Celery are **not supported by the Redis broker by default**. Redis uses FIFO lists, and the `priority` parameter is silently ignored. Here is how to actually implement task priorities:

```python
from celery import Celery
from kombu import Queue, Exchange

# ============================================================
# WHY PRIORITY DOES NOT WORK WITH REDIS (default)
# ============================================================
# Redis broker uses LPUSH/BRPOP on a list, which is strictly FIFO.
# The priority=N parameter on @app.task is ignored unless you
# configure priority steps or use RabbitMQ.

# ============================================================
# SOLUTION 1: Use separate queues (RECOMMENDED for Redis)
# ============================================================

app = Celery("myapp", broker="redis://localhost:6379/0")

app.conf.task_queues = (
    Queue("urgent", Exchange("urgent"), routing_key="urgent"),
    Queue("normal", Exchange("normal"), routing_key="normal"),
    Queue("background", Exchange("background"), routing_key="background"),
)

app.conf.task_routes = {
    "myapp.tasks.urgent_task": {"queue": "urgent"},
    "myapp.tasks.background_task": {"queue": "background"},
}

@app.task(name="myapp.tasks.urgent_task")
def urgent_task(data):
    process_urgent(data)

@app.task(name="myapp.tasks.background_task")
def background_task(data):
    process_background(data)

# Run workers with queue priority ordering:
# celery -A myapp worker -Q urgent,normal,background -c 4
#
# Workers consume from queues LEFT to RIGHT:
# - First drain all tasks from "urgent"
# - Then check "normal"
# - Then check "background"
# This gives effective priority ordering!

# ============================================================
# SOLUTION 2: Enable Redis priority support (limited)
# ============================================================

app2 = Celery("myapp2", broker="redis://localhost:6379/0")
app2.conf.broker_transport_options = {
    # Create N separate queues internally for priority levels
    "priority_steps": list(range(10)),  # 0-9 priority levels
    # Separator for priority queue names
    "sep": ":",
    # Queue order (higher priority = lower number)
    "queue_order_strategy": "priority",
}

# Now priority parameter works (0 = highest, 9 = lowest)
@app2.task
def task_with_priority(data):
    pass

# Call with explicit priority
task_with_priority.apply_async(args=("data",), priority=0)  # urgent
task_with_priority.apply_async(args=("data",), priority=9)  # low

# NOTE: This creates separate Redis lists for each priority level
# (e.g., "celery:0", "celery:1", ..., "celery:9")
# Worker polls them in order, which adds slight overhead.

# ============================================================
# SOLUTION 3: Use RabbitMQ for native priority support
# ============================================================

app3 = Celery("myapp3", broker="amqp://guest:guest@localhost:5672//")

# RabbitMQ supports native queue priorities
app3.conf.task_queue_max_priority = 10  # Enable priority on queues
app3.conf.task_default_priority = 5     # Default priority level

@app3.task(priority=9)  # This WORKS with RabbitMQ
def urgent_rabbitmq_task(data):
    pass

@app3.task(priority=1)
def background_rabbitmq_task(data):
    pass

# ============================================================
# SOLUTION 4: Manual priority with task ETA (workaround)
# ============================================================
from datetime import datetime, timedelta

def submit_with_priority(task, args, priority_level):
    """Higher priority = sooner ETA."""
    if priority_level == "urgent":
        # Execute immediately
        task.apply_async(args=args)
    elif priority_level == "normal":
        # Slight delay
        task.apply_async(args=args, countdown=1)
    elif priority_level == "low":
        # Larger delay
        task.apply_async(args=args, countdown=10)

# ============================================================
# PRODUCTION PATTERN: Dedicated workers per priority
# ============================================================
# Start separate worker pools with different concurrency:
#
# # Urgent: more workers, higher concurrency
# celery -A myapp worker -Q urgent -c 8 -n urgent@%h
#
# # Normal: moderate
# celery -A myapp worker -Q normal -c 4 -n normal@%h
#
# # Background: minimal resources
# celery -A myapp worker -Q background -c 1 -n background@%h
#
# This ensures urgent tasks always have dedicated capacity.
```

**Recommendation:** Use separate queues (Solution 1) with Redis. It is the most reliable approach and gives you full control over worker allocation per priority level. Native priority support in Redis (Solution 2) works but adds overhead and complexity.''',
    ),
    (
        "thinking/debugging",
        r'''My Celery result backend (Redis) keeps losing connection and tasks fail with "ConnectionError: Error while reading from socket". The tasks themselves succeed but I cannot retrieve results. How do I make the result backend connection resilient?''',
        r'''<think>
Tasks succeed but result retrieval fails with ConnectionError. So the task execution is fine (it uses the broker connection), but the result backend connection (separate Redis connection) is dying.

Why would the result backend connection drop? Let me think through possibilities. Could it be Redis restarting? That would affect the broker too, but the user says tasks succeed -- so the broker connection is stable. That is odd. Unless the broker and result backend are on different Redis instances or different servers.

Actually, a more likely cause: idle connection timeout. The result backend connection might sit idle between result retrievals. If Redis has a `timeout` config (default 0 = no timeout) or there is a firewall/load balancer between the app and Redis with an idle timeout, the TCP connection gets silently dropped. The next time Celery tries to read a result, the socket is dead and it gets ConnectionError.

Could it be connection pool exhaustion? If many tasks finish simultaneously and all try to store results at once, they might exceed the connection pool limit. But that would typically cause a different error, more like "too many connections" or a pool timeout.

What about the `socket_keepalive` option? Without TCP keepalive, the OS does not detect a dead connection until someone tries to use it. Enabling keepalive would send periodic probes and detect dead connections early.

The fix should be multi-layered: (1) enable `redis_retry_on_timeout=True` so Celery retries on timeout errors, (2) set `socket_keepalive=True` to detect dead connections, (3) set `result_backend_always_retry=True` so result operations are retried automatically, and (4) for tasks where you do not need the result, use `ignore_result=True` to bypass the result backend entirely. That last point is actually the biggest win -- if half your tasks are fire-and-forget, you eliminate half the result backend load.
</think>

Redis result backend connection issues in Celery can be fixed with proper retry configuration and connection pool management:

```python
from celery import Celery
from celery.exceptions import TimeoutError as CeleryTimeout
import redis

app = Celery("myapp")

# ============================================================
# FIX 1: Configure result backend with retry and pool settings
# ============================================================
app.conf.update(
    # Result backend URL with connection parameters
    result_backend="redis://localhost:6379/1",

    # Retry connecting to result backend
    result_backend_transport_options={
        "retry_policy": {
            "timeout": 5.0,
        },
        # Connection pool settings
        "max_connections": 20,
        # Socket timeout prevents hanging on dead connections
        "socket_timeout": 5.0,
        "socket_connect_timeout": 5.0,
        # Keep-alive prevents idle connection drops
        "socket_keepalive": True,
    },

    # How long to keep results (seconds)
    result_expires=3600,

    # Retry result backend operations
    result_backend_always_retry=True,
    result_backend_max_retries=10,

    # Redis-specific settings
    redis_max_connections=20,
    redis_socket_timeout=5.0,
    redis_socket_connect_timeout=5.0,
    redis_retry_on_timeout=True,

    # Broker connection retry (separate from result backend)
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
)

# ============================================================
# FIX 2: Handle result retrieval errors gracefully
# ============================================================

@app.task(bind=True)
def process_data(self, data):
    """Task that stores its result in Redis."""
    result = heavy_computation(data)
    return result

def get_result_safely(async_result, timeout=30, fallback=None):
    """Retrieve a task result with error handling."""
    try:
        return async_result.get(timeout=timeout)
    except CeleryTimeout:
        print(f"Task {async_result.id} did not complete in {timeout}s")
        return fallback
    except ConnectionError as e:
        print(f"Result backend connection error: {e}")
        # Task may have succeeded but we cannot read the result
        # Check task state as a fallback
        try:
            state = async_result.state
            if state == "SUCCESS":
                print("Task succeeded but result is unreachable")
            elif state == "FAILURE":
                print("Task failed")
            elif state == "PENDING":
                print("Task is still pending or result expired")
        except Exception:
            print("Cannot determine task state")
        return fallback
    except Exception as e:
        print(f"Unexpected error getting result: {e}")
        return fallback

# Usage:
result = process_data.delay(my_data)
value = get_result_safely(result, timeout=60, fallback={"status": "unknown"})

# ============================================================
# FIX 3: Use result_extended for better state tracking
# ============================================================
app.conf.result_extended = True
# This stores additional metadata: task args, kwargs, worker name,
# timestamps for started/completed. Helpful for debugging.

# ============================================================
# FIX 4: Implement a health check for the result backend
# ============================================================

def check_result_backend_health():
    """Verify the result backend is reachable."""
    try:
        # Try to ping the Redis result backend
        backend = app.backend
        if hasattr(backend, "client"):
            # Redis backend
            backend.client.ping()
            info = backend.client.info("memory")
            used_mb = info["used_memory"] / (1024 * 1024)
            print(f"Result backend OK. Memory: {used_mb:.1f} MB")
            return True
        else:
            print(f"Backend type: {type(backend).__name__}")
            return True
    except redis.ConnectionError as e:
        print(f"Result backend DOWN: {e}")
        return False
    except Exception as e:
        print(f"Result backend check failed: {e}")
        return False

# ============================================================
# FIX 5: Use ignore_result for fire-and-forget tasks
# ============================================================

@app.task(ignore_result=True)  # Never stores result in Redis
def send_notification(user_id, message):
    """Fire-and-forget task -- no result backend needed."""
    notify_user(user_id, message)

# This completely avoids result backend issues for tasks
# where you do not need the return value.

# Apply globally for tasks that do not need results:
app.conf.task_ignore_result = True
# Then opt-in per task:
@app.task(ignore_result=False)
def task_that_needs_result(data):
    return compute(data)

# ============================================================
# FIX 6: Monitor connection pool usage
# ============================================================

def monitor_redis_connections():
    """Check for connection pool exhaustion."""
    r = redis.Redis(host="localhost", port=6379, db=1)
    info = r.info("clients")
    print(f"Connected clients: {info['connected_clients']}")
    print(f"Blocked clients: {info['blocked_clients']}")
    print(f"Max clients: {r.config_get('maxclients')}")

    if info["connected_clients"] > 100:
        print("WARNING: High connection count -- possible pool leak")
```

**Key settings to prevent connection issues:**
1. `redis_retry_on_timeout=True` -- auto-retry on timeout
2. `socket_keepalive=True` -- prevent idle connection drops
3. `result_backend_always_retry=True` -- retry result backend operations
4. `ignore_result=True` on fire-and-forget tasks -- avoid backend entirely
5. Set explicit `socket_timeout` to prevent infinite hangs''',
    ),
]
