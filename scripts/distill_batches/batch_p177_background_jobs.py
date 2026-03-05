"""Background job processing — Celery/Dramatiq patterns, job queues, scheduled tasks, job chaining, dead letter handling, progress tracking."""

PAIRS = [
    (
        "background-jobs/celery-patterns",
        "Show production Celery task patterns including retries, rate limiting, task routing, error handling, and idempotent task design with proper signal handling.",
        '''Production Celery task patterns with retries, routing, and idempotency:

```python
from __future__ import annotations

import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from celery import Celery, Task, chain, chord, group, signals
from celery.exceptions import MaxRetriesExceededError, Reject, SoftTimeLimitExceeded
from celery.utils.log import get_task_logger
from kombu import Exchange, Queue

logger = get_task_logger(__name__)


# ── Celery configuration ─────────────────────────────────────────

app = Celery("myapp")

app.config_from_object({
    "broker_url": "redis://localhost:6379/0",
    "result_backend": "redis://localhost:6379/1",
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],
    "timezone": "UTC",
    "enable_utc": True,

    # Reliability settings
    "task_acks_late": True,          # ack after task completes (not on receive)
    "task_reject_on_worker_lost": True,  # requeue if worker crashes
    "worker_prefetch_multiplier": 1,     # fetch one task at a time

    # Result expiry
    "result_expires": 3600 * 24,     # 24 hours

    # Concurrency
    "worker_concurrency": 4,

    # Task time limits
    "task_soft_time_limit": 300,     # soft limit: 5 minutes
    "task_time_limit": 360,          # hard limit: 6 minutes

    # Queue routing
    "task_queues": [
        Queue("default", Exchange("default"), routing_key="default"),
        Queue("high_priority", Exchange("priority"), routing_key="high"),
        Queue("low_priority", Exchange("priority"), routing_key="low"),
        Queue("email", Exchange("notifications"), routing_key="email"),
        Queue("reports", Exchange("reports"), routing_key="reports"),
    ],
    "task_default_queue": "default",
    "task_routes": {
        "myapp.tasks.send_email": {"queue": "email"},
        "myapp.tasks.generate_report": {"queue": "reports"},
        "myapp.tasks.process_payment": {"queue": "high_priority"},
    },
})


# ── Base task class with common behavior ──────────────────────────

class BaseTask(Task):
    """Base task with standardized error handling and logging."""

    abstract = True
    max_retries = 3
    default_retry_delay = 60   # 1 minute base delay

    def on_failure(self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: Any) -> None:
        logger.error(
            f"Task {self.name}[{task_id}] failed after {self.request.retries} retries: {exc}",
            exc_info=True,
        )

    def on_retry(self, exc: Exception, task_id: str, args: tuple, kwargs: dict, einfo: Any) -> None:
        logger.warning(
            f"Task {self.name}[{task_id}] retrying ({self.request.retries}/{self.max_retries}): {exc}",
        )

    def on_success(self, retval: Any, task_id: str, args: tuple, kwargs: dict) -> None:
        logger.info(f"Task {self.name}[{task_id}] completed successfully")


class IdempotentTask(BaseTask):
    """Task that checks idempotency before executing.

    Uses a Redis lock to ensure the same logical operation
    is not processed twice, even if the task is retried.
    """

    abstract = True
    idempotency_ttl = 3600 * 24  # 24 hours

    def _idempotency_key(self, args: tuple, kwargs: dict) -> str:
        """Generate a unique key for this task invocation."""
        payload = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return f"idempotent:{self.name}:{hashlib.sha256(payload.encode()).hexdigest()}"

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        from redis import Redis
        redis_client = Redis.from_url(app.conf.broker_url)
        key = self._idempotency_key(args, kwargs)

        # Check if already processed
        existing = redis_client.get(key)
        if existing:
            logger.info(f"Task {self.name} skipped (idempotent, already processed)")
            return json.loads(existing)

        # Execute the task
        result = super().__call__(*args, **kwargs)

        # Mark as processed
        redis_client.setex(key, self.idempotency_ttl, json.dumps(result, default=str))
        return result


# ── Task definitions ──────────────────────────────────────────────

@app.task(
    base=IdempotentTask,
    bind=True,
    max_retries=5,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,        # exponential backoff
    retry_backoff_max=600,     # max 10 minutes
    retry_jitter=True,         # add randomness to retry delay
    rate_limit="10/m",         # max 10 per minute
)
def process_payment(self: Task, order_id: str, amount: float, currency: str) -> dict:
    """Process a payment with automatic retries and rate limiting."""
    try:
        logger.info(f"Processing payment for order {order_id}: {amount} {currency}")

        # Simulate payment processing
        result = {
            "order_id": order_id,
            "transaction_id": f"txn_{uuid.uuid4().hex[:12]}",
            "amount": amount,
            "currency": currency,
            "status": "completed",
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

        return result

    except SoftTimeLimitExceeded:
        logger.error(f"Payment processing timed out for order {order_id}")
        raise Reject(reason="Soft time limit exceeded", requeue=False)


@app.task(
    base=BaseTask,
    bind=True,
    max_retries=3,
    autoretry_for=(ConnectionError,),
    retry_backoff=True,
)
def send_email(
    self: Task,
    to: str,
    subject: str,
    template: str,
    context: dict[str, Any],
) -> dict:
    """Send an email notification."""
    logger.info(f"Sending email to {to}: {subject}")

    # Simulate email sending
    return {
        "message_id": f"msg_{uuid.uuid4().hex[:8]}",
        "to": to,
        "subject": subject,
        "status": "sent",
        "sent_at": datetime.now(timezone.utc).isoformat(),
    }


@app.task(
    base=BaseTask,
    bind=True,
    soft_time_limit=600,     # 10 minutes
    time_limit=660,          # 11 minutes hard kill
)
def generate_report(
    self: Task,
    report_type: str,
    params: dict[str, Any],
) -> dict:
    """Generate a report with progress tracking."""
    total_steps = 100

    for step in range(total_steps):
        if step % 10 == 0:
            # Update progress metadata
            self.update_state(
                state="PROGRESS",
                meta={
                    "current": step,
                    "total": total_steps,
                    "percent": int(step / total_steps * 100),
                    "status": f"Processing step {step}/{total_steps}",
                },
            )
        time.sleep(0.1)  # simulate work

    return {
        "report_type": report_type,
        "file_url": f"/reports/{report_type}_{uuid.uuid4().hex[:8]}.pdf",
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


# ── Task chaining and workflows ──────────────────────────────────

@app.task(base=BaseTask, bind=True)
def validate_order(self: Task, order_data: dict) -> dict:
    """Step 1: Validate order data."""
    logger.info(f"Validating order {order_data.get(\'order_id\')}")
    return {**order_data, "validated": True}


@app.task(base=BaseTask, bind=True)
def reserve_inventory(self: Task, order_data: dict) -> dict:
    """Step 2: Reserve inventory items."""
    logger.info(f"Reserving inventory for order {order_data.get(\'order_id\')}")
    return {**order_data, "inventory_reserved": True}


@app.task(base=BaseTask, bind=True)
def finalize_order(self: Task, results: list[dict]) -> dict:
    """Final step: Aggregate results from parallel tasks."""
    logger.info(f"Finalizing order with {len(results)} results")
    return {"status": "finalized", "results": results}


def create_order_workflow(order_data: dict) -> Any:
    """Create an order processing workflow.

    Pipeline:
      validate -> reserve_inventory -> (charge_payment | send_confirmation) -> finalize
    """
    workflow = chain(
        # Sequential steps
        validate_order.s(order_data),
        reserve_inventory.s(),
        # Parallel tasks (chord: run group, then callback)
        chord(
            group(
                process_payment.s(
                    order_data["order_id"],
                    order_data["total"],
                    order_data.get("currency", "USD"),
                ),
                send_email.s(
                    to=order_data["customer_email"],
                    subject="Order Confirmation",
                    template="order_confirmed",
                    context=order_data,
                ),
            ),
            finalize_order.s(),
        ),
    )
    return workflow.apply_async()


# ── Signal handlers ───────────────────────────────────────────────

@signals.task_prerun.connect
def task_prerun_handler(task_id: str, task: Task, **kwargs: Any) -> None:
    """Log task start time for duration tracking."""
    logger.debug(f"Task {task.name}[{task_id}] starting")


@signals.worker_shutting_down.connect
def worker_shutdown_handler(**kwargs: Any) -> None:
    """Graceful shutdown: finish current tasks before stopping."""
    logger.info("Worker shutting down — completing in-progress tasks")
```

Celery configuration best practices:

| Setting | Value | Why |
|---|---|---|
| `task_acks_late` | True | Requeue on worker crash |
| `task_reject_on_worker_lost` | True | Prevent message loss |
| `worker_prefetch_multiplier` | 1 | Fair distribution to workers |
| `retry_backoff` | True | Exponential backoff on retries |
| `retry_jitter` | True | Prevent thundering herd |
| `rate_limit` | "10/m" | Protect downstream services |
| `soft_time_limit` | 300 | Graceful timeout handling |

Key patterns:
- **Idempotent tasks**: Redis lock prevents double-processing on retry
- **Task routing**: Separate queues for different priorities and workloads
- **Chord pattern**: Parallel tasks with a finalizer callback
- **Progress tracking**: `update_state()` for long-running tasks
- **Late ack**: Tasks redelivered if worker crashes mid-execution
- **Graceful shutdown**: Complete in-progress tasks on SIGTERM
'''
    ),
    (
        "background-jobs/dramatiq-patterns",
        "Implement background job processing with Dramatiq including middleware, priority queues, result backends, actor composition, and worker management.",
        '''Background job processing with Dramatiq, middleware, and actor composition:

```python
from __future__ import annotations

import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import dramatiq
from dramatiq.brokers.redis import RedisBroker
from dramatiq.middleware import (
    AgeLimit,
    Callbacks,
    CurrentMessage,
    Pipelines,
    Retries,
    ShutdownNotifications,
    TimeLimit,
)
from dramatiq.rate_limits import ConcurrentRateLimiter, WindowRateLimiter
from dramatiq.rate_limits.backends import RedisBackend
from dramatiq.results import Results
from dramatiq.results.backends.redis import RedisBackend as ResultsRedisBackend

logger = logging.getLogger("jobs.dramatiq")


# ── Broker setup with middleware ──────────────────────────────────

redis_broker = RedisBroker(url="redis://localhost:6379/0")

# Configure middleware stack
result_backend = ResultsRedisBackend(url="redis://localhost:6379/1")
rate_limit_backend = RedisBackend(url="redis://localhost:6379/2")

redis_broker.middleware = [
    AgeLimit(),                    # discard messages older than max_age
    TimeLimit(),                   # kill actors exceeding time_limit
    ShutdownNotifications(),       # notify actors of worker shutdown
    Callbacks(),                   # support on_success/on_failure callbacks
    Pipelines(),                   # pipe actors together
    Retries(max_retries=3),        # automatic retries with backoff
    Results(backend=result_backend),  # store return values
    CurrentMessage(),              # access current message in actor
]

dramatiq.set_broker(redis_broker)


# ── Custom middleware: structured logging ─────────────────────────

class StructuredLoggingMiddleware(dramatiq.Middleware):
    """Log actor execution with timing and structured metadata."""

    def before_process_message(self, broker: Any, message: dramatiq.Message) -> None:
        message.options["start_time"] = time.monotonic()
        logger.info(
            "Actor started",
            extra={
                "actor": message.actor_name,
                "message_id": message.message_id,
                "queue": message.queue_name,
                "retries": message.options.get("retries", 0),
            },
        )

    def after_process_message(
        self, broker: Any, message: dramatiq.Message,
        *, result: Any = None, exception: Exception | None = None,
    ) -> None:
        start = message.options.get("start_time", time.monotonic())
        elapsed_ms = (time.monotonic() - start) * 1000

        if exception:
            logger.error(
                "Actor failed",
                extra={
                    "actor": message.actor_name,
                    "message_id": message.message_id,
                    "elapsed_ms": round(elapsed_ms, 1),
                    "error": str(exception),
                },
            )
        else:
            logger.info(
                "Actor completed",
                extra={
                    "actor": message.actor_name,
                    "message_id": message.message_id,
                    "elapsed_ms": round(elapsed_ms, 1),
                },
            )


redis_broker.add_middleware(StructuredLoggingMiddleware())


# ── Rate limiters ─────────────────────────────────────────────────

# Max 10 concurrent API calls
api_concurrent_limiter = ConcurrentRateLimiter(
    rate_limit_backend, "api-calls", limit=10,
)

# Max 100 emails per minute
email_window_limiter = WindowRateLimiter(
    rate_limit_backend, "email-sends", limit=100, window=60_000,
)


# ── Actor definitions ─────────────────────────────────────────────

@dramatiq.actor(
    queue_name="high_priority",
    max_retries=5,
    min_backoff=1_000,        # 1 second
    max_backoff=300_000,      # 5 minutes
    time_limit=60_000,        # 1 minute hard limit
    store_results=True,
    max_age=3_600_000,        # discard if older than 1 hour
)
def process_order(order_id: str, items: list[dict], total: float) -> dict:
    """Process an order with rate-limited external API calls."""
    logger.info(f"Processing order {order_id}")

    # Rate-limited section
    with api_concurrent_limiter.acquire(raise_on_failure=False) as acquired:
        if not acquired:
            # Requeue with delay if rate limit hit
            msg = dramatiq.get_broker().get_actor("process_order").message(
                order_id, items, total,
            )
            msg.options["delay"] = 5000  # retry in 5 seconds
            raise dramatiq.RateLimitExceeded("API rate limit reached")

        # Process order
        result = {
            "order_id": order_id,
            "status": "processed",
            "items_count": len(items),
            "total": total,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        }

    return result


@dramatiq.actor(
    queue_name="notifications",
    max_retries=3,
    min_backoff=5_000,
    store_results=True,
)
def send_notification(
    channel: str,
    recipient: str,
    template: str,
    context: dict[str, Any],
) -> dict:
    """Send a notification via email, SMS, or push."""
    if channel == "email":
        with email_window_limiter.acquire(raise_on_failure=False) as acquired:
            if not acquired:
                raise dramatiq.RateLimitExceeded("Email rate limit reached")

    logger.info(f"Sending {channel} notification to {recipient}")

    return {
        "notification_id": f"notif_{uuid.uuid4().hex[:8]}",
        "channel": channel,
        "recipient": recipient,
        "status": "sent",
    }


@dramatiq.actor(
    queue_name="default",
    max_retries=2,
    time_limit=600_000,       # 10 minutes
    store_results=True,
)
def generate_report(report_type: str, params: dict[str, Any]) -> dict:
    """Generate a report — long-running task with shutdown awareness."""
    message = CurrentMessage.get_current_message()

    total_steps = 50
    for step in range(total_steps):
        # Check if worker is shutting down
        if message and hasattr(message, "options"):
            if message.options.get("shutdown_notification"):
                logger.warning("Worker shutting down — saving partial progress")
                # Save checkpoint and requeue
                return {"status": "interrupted", "checkpoint": step}

        time.sleep(0.2)  # simulate work

    return {
        "report_type": report_type,
        "url": f"/reports/{report_type}_{uuid.uuid4().hex[:8]}.csv",
    }


# ── Actor composition with pipelines ─────────────────────────────

@dramatiq.actor(store_results=True)
def validate_data(data: dict) -> dict:
    """Step 1: Validate input data."""
    return {**data, "validated": True}


@dramatiq.actor(store_results=True)
def enrich_data(data: dict) -> dict:
    """Step 2: Enrich data with external lookups."""
    return {**data, "enriched": True}


@dramatiq.actor(store_results=True)
def persist_data(data: dict) -> dict:
    """Step 3: Save to database."""
    return {**data, "persisted": True, "id": str(uuid.uuid4())}


@dramatiq.actor
def on_pipeline_success(message_data: Any, result: Any) -> None:
    """Callback when entire pipeline completes."""
    logger.info(f"Pipeline completed with result: {result}")


@dramatiq.actor
def on_pipeline_failure(message_data: Any, exception_data: Any) -> None:
    """Callback when pipeline fails at any step."""
    logger.error(f"Pipeline failed: {exception_data}")


def run_data_pipeline(input_data: dict) -> Any:
    """Create and run a data processing pipeline."""
    pipe = (
        validate_data.message(input_data)
        | enrich_data.message()
        | persist_data.message_with_options(
            on_success=on_pipeline_success,
            on_failure=on_pipeline_failure,
        )
    )
    pipe.run()
    return pipe


# ── Scheduled tasks with APScheduler integration ─────────────────

@dramatiq.actor(queue_name="scheduled")
def cleanup_expired_sessions() -> int:
    """Periodic task: clean up expired sessions."""
    logger.info("Cleaning up expired sessions")
    cleaned = 42  # simulate
    return cleaned


@dramatiq.actor(queue_name="scheduled")
def sync_inventory() -> dict:
    """Periodic task: sync inventory with external system."""
    logger.info("Syncing inventory")
    return {"synced_items": 150, "conflicts": 2}


# To schedule periodic tasks, use APScheduler alongside Dramatiq:
# from apscheduler.schedulers.blocking import BlockingScheduler
# scheduler = BlockingScheduler()
# scheduler.add_job(cleanup_expired_sessions.send, "interval", minutes=15)
# scheduler.add_job(sync_inventory.send, "cron", hour=2, minute=0)
# scheduler.start()
```

Dramatiq vs Celery comparison:

| Feature | Dramatiq | Celery |
|---|---|---|
| API style | Simple decorators | Complex configuration |
| Broker support | Redis, RabbitMQ | Redis, RabbitMQ, SQS, more |
| Rate limiting | Built-in (concurrent + window) | Built-in (per-task) |
| Pipelines | Pipe operator (`\\|`) | chain(), chord(), group() |
| Result backend | Optional middleware | Optional backend |
| Worker model | Threading + gevent | Prefork, eventlet, gevent |
| Shutdown handling | Graceful via middleware | Signal handling |

Key patterns:
- **Middleware stack**: Compose behavior (logging, timing, results) cleanly
- **Rate limiters**: Concurrent (max N parallel) and window (N per time period)
- **Pipeline operator**: Chain actors with `message() | next_actor.message()`
- **Callbacks**: `on_success` and `on_failure` for workflow orchestration
- **Shutdown awareness**: Check for shutdown notification in long tasks
'''
    ),
    (
        "background-jobs/redis-queue",
        "Build a lightweight job queue using Redis streams with consumer groups, acknowledgment, dead letter handling, and priority support without external task frameworks.",
        '''Lightweight job queue using Redis streams with consumer groups and DLQ:

```python
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Coroutine

import redis.asyncio as aioredis

logger = logging.getLogger("jobs.redis_queue")


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"


@dataclass
class Job:
    job_id: str
    job_type: str
    payload: dict[str, Any]
    priority: int = 0           # higher = more urgent
    max_retries: int = 3
    attempt: int = 0
    created_at: str = ""
    timeout_ms: int = 30_000    # per-job timeout
    metadata: dict[str, str] = field(default_factory=dict)

    def to_redis(self) -> dict[str, str]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "payload": json.dumps(self.payload),
            "priority": str(self.priority),
            "max_retries": str(self.max_retries),
            "attempt": str(self.attempt),
            "created_at": self.created_at or datetime.now(timezone.utc).isoformat(),
            "timeout_ms": str(self.timeout_ms),
            "metadata": json.dumps(self.metadata),
        }

    @classmethod
    def from_redis(cls, data: dict[bytes, bytes]) -> Job:
        d = {k.decode(): v.decode() for k, v in data.items()}
        return cls(
            job_id=d["job_id"],
            job_type=d["job_type"],
            payload=json.loads(d["payload"]),
            priority=int(d.get("priority", "0")),
            max_retries=int(d.get("max_retries", "3")),
            attempt=int(d.get("attempt", "0")),
            created_at=d.get("created_at", ""),
            timeout_ms=int(d.get("timeout_ms", "30000")),
            metadata=json.loads(d.get("metadata", "{}")),
        )


class RedisJobQueue:
    """Job queue using Redis Streams with consumer groups.

    Features:
    - Multiple priority queues (separate streams)
    - Consumer groups for parallel processing
    - Automatic claim of stale messages (crashed workers)
    - Dead letter queue for permanently failed jobs
    - Job result storage
    """

    PRIORITY_STREAMS = {
        "high": "jobs:high",
        "normal": "jobs:normal",
        "low": "jobs:low",
    }
    DLQ_STREAM = "jobs:dlq"
    RESULTS_PREFIX = "jobs:result:"

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        group_name: str = "workers",
        consumer_name: str | None = None,
        claim_timeout_ms: int = 60_000,   # reclaim after 1 minute
    ) -> None:
        self._redis: aioredis.Redis | None = None
        self._redis_url = redis_url
        self._group = group_name
        self._consumer = consumer_name or f"worker-{uuid.uuid4().hex[:8]}"
        self._claim_timeout = claim_timeout_ms
        self._handlers: dict[str, Callable] = {}
        self._running = False

    async def connect(self) -> None:
        self._redis = aioredis.from_url(self._redis_url)
        # Create consumer groups for each priority stream
        for stream in self.PRIORITY_STREAMS.values():
            try:
                await self._redis.xgroup_create(
                    stream, self._group, id="0", mkstream=True,
                )
            except aioredis.ResponseError as e:
                if "BUSYGROUP" not in str(e):
                    raise

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()

    def register(self, job_type: str, handler: Callable) -> None:
        """Register a handler function for a job type."""
        self._handlers[job_type] = handler

    # ── Enqueue ───────────────────────────────────────────────────

    async def enqueue(
        self,
        job_type: str,
        payload: dict[str, Any],
        priority: str = "normal",
        max_retries: int = 3,
        timeout_ms: int = 30_000,
        delay_ms: int = 0,
    ) -> str:
        """Add a job to the queue."""
        job = Job(
            job_id=f"job_{uuid.uuid4().hex[:12]}",
            job_type=job_type,
            payload=payload,
            priority={"high": 2, "normal": 1, "low": 0}.get(priority, 1),
            max_retries=max_retries,
            timeout_ms=timeout_ms,
        )

        stream = self.PRIORITY_STREAMS.get(priority, self.PRIORITY_STREAMS["normal"])

        if delay_ms > 0:
            # Use a sorted set for delayed jobs
            score = time.time() * 1000 + delay_ms
            await self._redis.zadd(
                "jobs:delayed",
                {json.dumps({"stream": stream, **job.to_redis()}): score},
            )
        else:
            await self._redis.xadd(stream, job.to_redis())

        logger.info(f"Enqueued job {job.job_id} ({job_type}) to {stream}")
        return job.job_id

    # ── Processing loop ───────────────────────────────────────────

    async def start_worker(self, concurrency: int = 4) -> None:
        """Start the worker loop processing jobs from all priority queues."""
        self._running = True
        tasks = [
            asyncio.create_task(self._process_loop()),
            asyncio.create_task(self._claim_stale_messages()),
            asyncio.create_task(self._promote_delayed_jobs()),
        ]
        # Add concurrent processors
        for _ in range(concurrency - 1):
            tasks.append(asyncio.create_task(self._process_loop()))

        await asyncio.gather(*tasks)

    async def stop(self) -> None:
        self._running = False

    async def _process_loop(self) -> None:
        """Main processing loop — read from priority queues in order."""
        streams = {
            self.PRIORITY_STREAMS["high"]: ">",
            self.PRIORITY_STREAMS["normal"]: ">",
            self.PRIORITY_STREAMS["low"]: ">",
        }

        while self._running:
            try:
                # XREADGROUP blocks until a message arrives
                results = await self._redis.xreadgroup(
                    self._group,
                    self._consumer,
                    streams=streams,
                    count=1,
                    block=2000,   # block for 2 seconds max
                )

                if not results:
                    continue

                for stream_name, messages in results:
                    for message_id, data in messages:
                        await self._process_message(
                            stream_name.decode(),
                            message_id.decode(),
                            data,
                        )

            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                await asyncio.sleep(1)

    async def _process_message(
        self, stream: str, message_id: str, data: dict,
    ) -> None:
        """Process a single message from the stream."""
        job = Job.from_redis(data)
        handler = self._handlers.get(job.job_type)

        if not handler:
            logger.warning(f"No handler for job type: {job.job_type}")
            await self._redis.xack(stream, self._group, message_id)
            return

        job.attempt += 1
        start = time.monotonic()

        try:
            result = await asyncio.wait_for(
                handler(job.payload),
                timeout=job.timeout_ms / 1000,
            )

            elapsed_ms = (time.monotonic() - start) * 1000

            # Store result
            await self._redis.setex(
                f"{self.RESULTS_PREFIX}{job.job_id}",
                3600 * 24,
                json.dumps({
                    "status": "completed",
                    "result": result,
                    "duration_ms": round(elapsed_ms, 1),
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }, default=str),
            )

            # Acknowledge the message
            await self._redis.xack(stream, self._group, message_id)
            logger.info(f"Job {job.job_id} completed in {elapsed_ms:.0f}ms")

        except asyncio.TimeoutError:
            await self._handle_failure(
                stream, message_id, job, "Timeout exceeded",
            )

        except Exception as e:
            await self._handle_failure(
                stream, message_id, job, str(e),
            )

    async def _handle_failure(
        self, stream: str, message_id: str, job: Job, error: str,
    ) -> None:
        """Handle a failed job — retry or dead-letter."""
        logger.error(f"Job {job.job_id} failed (attempt {job.attempt}/{job.max_retries}): {error}")

        # Acknowledge to remove from pending
        await self._redis.xack(stream, self._group, message_id)

        if job.attempt < job.max_retries:
            # Re-enqueue with incremented attempt count
            job.metadata["last_error"] = error[:500]
            retry_data = job.to_redis()
            retry_data["attempt"] = str(job.attempt)
            await self._redis.xadd(stream, retry_data)
            logger.info(f"Job {job.job_id} requeued for retry {job.attempt + 1}")
        else:
            # Dead letter
            dlq_data = job.to_redis()
            dlq_data["error"] = error[:500]
            dlq_data["dead_lettered_at"] = datetime.now(timezone.utc).isoformat()
            await self._redis.xadd(self.DLQ_STREAM, dlq_data)
            logger.warning(f"Job {job.job_id} moved to DLQ after {job.max_retries} attempts")

    async def _claim_stale_messages(self) -> None:
        """Periodically claim messages from crashed consumers."""
        while self._running:
            try:
                for stream in self.PRIORITY_STREAMS.values():
                    pending = await self._redis.xpending_range(
                        stream, self._group,
                        min="-", max="+", count=10,
                    )
                    for entry in pending:
                        idle_ms = entry.get("time_since_delivered", 0)
                        if idle_ms > self._claim_timeout:
                            msg_id = entry["message_id"]
                            claimed = await self._redis.xclaim(
                                stream, self._group, self._consumer,
                                min_idle_time=self._claim_timeout,
                                message_ids=[msg_id],
                            )
                            if claimed:
                                logger.info(f"Claimed stale message {msg_id}")
            except Exception as e:
                logger.error(f"Claim loop error: {e}")

            await asyncio.sleep(self._claim_timeout / 1000 / 2)

    async def _promote_delayed_jobs(self) -> None:
        """Move delayed jobs that are ready into their target streams."""
        while self._running:
            try:
                now_ms = time.time() * 1000
                ready = await self._redis.zrangebyscore(
                    "jobs:delayed", "-inf", str(now_ms), start=0, num=50,
                )
                for item in ready:
                    data = json.loads(item)
                    stream = data.pop("stream")
                    await self._redis.xadd(stream, data)
                    await self._redis.zrem("jobs:delayed", item)
            except Exception as e:
                logger.error(f"Delayed promotion error: {e}")

            await asyncio.sleep(1)

    # ── Query ─────────────────────────────────────────────────────

    async def get_result(self, job_id: str) -> dict | None:
        result = await self._redis.get(f"{self.RESULTS_PREFIX}{job_id}")
        return json.loads(result) if result else None
```

Redis Streams job queue features:

| Feature | Implementation |
|---|---|
| Priority queues | Separate streams per priority, read in order |
| Consumer groups | XREADGROUP for parallel, exclusive consumption |
| At-least-once | XACK after processing; reclaim stale messages |
| Dead letter queue | Separate stream for permanently failed jobs |
| Delayed jobs | Sorted set with score = ready-at timestamp |
| Result storage | Redis key with TTL per job ID |
| Stale claiming | XCLAIM for messages from crashed workers |

Key patterns:
- **No external framework needed** -- pure Redis primitives
- **Priority ordering**: Read high -> normal -> low streams in sequence
- **Consumer groups**: Multiple workers share the workload without duplication
- **XCLAIM**: Recover messages from workers that crashed mid-processing
- **Delayed promotion**: Background task moves delayed jobs when ready
'''
    ),
    (
        "background-jobs/job-chaining",
        "Implement job chaining and workflow orchestration with dependency graphs, compensation (saga), and parallel fan-out/fan-in patterns for complex multi-step processes.",
        '''Job chaining with dependency graphs, saga compensation, and fan-out/fan-in:

```python
from __future__ import annotations

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Coroutine

logger = logging.getLogger("jobs.workflow")


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    SKIPPED = "skipped"


@dataclass
class StepResult:
    status: StepStatus
    data: Any = None
    error: str = ""
    duration_ms: float = 0


@dataclass
class WorkflowStep:
    """A single step in a workflow."""
    name: str
    execute: Callable[..., Coroutine[Any, Any, Any]]
    compensate: Callable[..., Coroutine[Any, Any, None]] | None = None
    depends_on: list[str] = field(default_factory=list)
    timeout: float = 30.0
    max_retries: int = 2
    retry_delay: float = 1.0
    required: bool = True     # if False, workflow continues on failure


@dataclass
class WorkflowContext:
    """Shared context passed through the workflow."""
    workflow_id: str
    step_results: dict[str, StepResult] = field(default_factory=dict)
    data: dict[str, Any] = field(default_factory=dict)
    started_at: float = field(default_factory=time.monotonic)


class WorkflowStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    COMPENSATED = "compensated"
    PARTIALLY_COMPLETED = "partially_completed"


@dataclass
class WorkflowResult:
    workflow_id: str
    status: WorkflowStatus
    step_results: dict[str, StepResult]
    data: dict[str, Any]
    total_duration_ms: float


class WorkflowEngine:
    """Execute multi-step workflows with dependency ordering and saga compensation.

    Features:
    - DAG-based step ordering
    - Parallel execution of independent steps
    - Automatic compensation (saga rollback) on failure
    - Per-step retries with backoff
    - Timeout enforcement per step
    """

    async def execute(
        self,
        steps: list[WorkflowStep],
        initial_data: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        ctx = WorkflowContext(
            workflow_id=f"wf_{uuid.uuid4().hex[:12]}",
            data=initial_data or {},
        )

        logger.info(f"Starting workflow {ctx.workflow_id} with {len(steps)} steps")

        # Build execution levels from dependency graph
        levels = self._build_levels(steps)
        completed_steps: list[WorkflowStep] = []
        workflow_failed = False

        for level in levels:
            if workflow_failed:
                for step in level:
                    ctx.step_results[step.name] = StepResult(status=StepStatus.SKIPPED)
                continue

            # Execute all steps in this level concurrently
            runnable = []
            for step in level:
                deps_ok = all(
                    ctx.step_results.get(dep, StepResult(StepStatus.PENDING)).status
                    == StepStatus.COMPLETED
                    for dep in step.depends_on
                )
                if deps_ok:
                    runnable.append(step)
                else:
                    ctx.step_results[step.name] = StepResult(
                        status=StepStatus.SKIPPED,
                        error="Dependency not met",
                    )

            results = await asyncio.gather(
                *(self._execute_step(step, ctx) for step in runnable),
                return_exceptions=True,
            )

            for step, result in zip(runnable, results):
                if isinstance(result, Exception):
                    result = StepResult(status=StepStatus.FAILED, error=str(result))

                ctx.step_results[step.name] = result

                if result.status == StepStatus.COMPLETED:
                    completed_steps.append(step)
                elif result.status == StepStatus.FAILED and step.required:
                    workflow_failed = True

        # Determine final status
        if workflow_failed:
            await self._compensate(completed_steps, ctx)
            all_compensated = all(
                ctx.step_results[s.name].status in (StepStatus.COMPENSATED, StepStatus.COMPLETED)
                for s in steps
                if s.name in ctx.step_results
            )
            status = WorkflowStatus.COMPENSATED if all_compensated else WorkflowStatus.FAILED
        else:
            has_failures = any(r.status == StepStatus.FAILED for r in ctx.step_results.values())
            status = WorkflowStatus.PARTIALLY_COMPLETED if has_failures else WorkflowStatus.COMPLETED

        total_ms = (time.monotonic() - ctx.started_at) * 1000

        return WorkflowResult(
            workflow_id=ctx.workflow_id,
            status=status,
            step_results=ctx.step_results,
            data=ctx.data,
            total_duration_ms=round(total_ms, 1),
        )

    async def _execute_step(self, step: WorkflowStep, ctx: WorkflowContext) -> StepResult:
        """Execute a step with retries and timeout."""
        for attempt in range(step.max_retries + 1):
            start = time.monotonic()
            try:
                result = await asyncio.wait_for(step.execute(ctx), timeout=step.timeout)
                elapsed = (time.monotonic() - start) * 1000
                logger.info(f"Step \\'{step.name}\\' completed in {elapsed:.0f}ms")
                return StepResult(status=StepStatus.COMPLETED, data=result, duration_ms=elapsed)

            except asyncio.TimeoutError:
                elapsed = (time.monotonic() - start) * 1000
                if attempt < step.max_retries:
                    await asyncio.sleep(step.retry_delay * (2 ** attempt))
                    continue
                return StepResult(status=StepStatus.FAILED, error=f"Timeout after {step.timeout}s", duration_ms=elapsed)

            except Exception as e:
                elapsed = (time.monotonic() - start) * 1000
                if attempt < step.max_retries:
                    await asyncio.sleep(step.retry_delay * (2 ** attempt))
                    continue
                return StepResult(status=StepStatus.FAILED, error=str(e), duration_ms=elapsed)

        return StepResult(status=StepStatus.FAILED, error="Max retries exceeded")

    async def _compensate(self, completed_steps: list[WorkflowStep], ctx: WorkflowContext) -> None:
        """Run compensation in reverse order (saga pattern)."""
        logger.warning(f"Workflow {ctx.workflow_id} failed — running compensation")

        for step in reversed(completed_steps):
            if step.compensate is None:
                continue
            try:
                ctx.step_results[step.name] = StepResult(status=StepStatus.COMPENSATING)
                await asyncio.wait_for(step.compensate(ctx), timeout=step.timeout)
                ctx.step_results[step.name] = StepResult(status=StepStatus.COMPENSATED)
                logger.info(f"Compensated step \\'{step.name}\\'")
            except Exception as e:
                logger.error(f"Compensation failed for step \\'{step.name}\\': {e}")
                ctx.step_results[step.name] = StepResult(
                    status=StepStatus.FAILED, error=f"Compensation failed: {e}",
                )

    def _build_levels(self, steps: list[WorkflowStep]) -> list[list[WorkflowStep]]:
        """Topological sort into parallel execution levels."""
        levels: list[list[WorkflowStep]] = []
        assigned: set[str] = set()

        while len(assigned) < len(steps):
            current = [
                s for s in steps
                if s.name not in assigned
                and all(d in assigned for d in s.depends_on)
            ]
            if not current:
                current = [s for s in steps if s.name not in assigned]
            for s in current:
                assigned.add(s.name)
            levels.append(current)

        return levels


# ── Usage: order processing workflow ──────────────────────────────

async def order_workflow_example() -> WorkflowResult:
    engine = WorkflowEngine()

    async def validate_order(ctx: WorkflowContext) -> dict:
        order = ctx.data["order"]
        if not order.get("items"):
            raise ValueError("Order has no items")
        return {"validated": True}

    async def reserve_inventory(ctx: WorkflowContext) -> dict:
        return {"reservation_id": f"res_{uuid.uuid4().hex[:8]}"}

    async def undo_reserve_inventory(ctx: WorkflowContext) -> None:
        res_id = ctx.step_results["reserve_inventory"].data.get("reservation_id")
        logger.info(f"Releasing reservation {res_id}")

    async def charge_payment(ctx: WorkflowContext) -> dict:
        return {"transaction_id": f"txn_{uuid.uuid4().hex[:8]}", "amount": 99.99}

    async def refund_payment(ctx: WorkflowContext) -> None:
        txn_id = ctx.step_results["charge_payment"].data.get("transaction_id")
        logger.info(f"Refunding transaction {txn_id}")

    async def send_confirmation(ctx: WorkflowContext) -> dict:
        return {"email_sent": True}

    async def create_shipment(ctx: WorkflowContext) -> dict:
        return {"tracking_number": "TRACK123456"}

    steps = [
        WorkflowStep(name="validate", execute=validate_order),
        WorkflowStep(name="reserve_inventory", execute=reserve_inventory, compensate=undo_reserve_inventory, depends_on=["validate"]),
        WorkflowStep(name="charge_payment", execute=charge_payment, compensate=refund_payment, depends_on=["reserve_inventory"]),
        WorkflowStep(name="send_confirmation", execute=send_confirmation, depends_on=["charge_payment"], required=False),
        WorkflowStep(name="create_shipment", execute=create_shipment, depends_on=["charge_payment"]),
    ]

    return await engine.execute(
        steps,
        initial_data={"order": {"id": "ord-123", "items": [{"sku": "A1", "qty": 2}]}},
    )
```

Workflow patterns:

| Pattern | Description | Use case |
|---|---|---|
| Chain | Sequential A -> B -> C | Order processing pipeline |
| Fan-out/fan-in | Parallel [A, B, C] -> D | Batch processing with aggregation |
| Saga | Forward steps + reverse compensation | Distributed transactions |
| DAG | Arbitrary dependency graph | Complex workflows |
| Conditional | Skip steps based on previous results | A/B testing, feature flags |

Key design decisions:
- **DAG execution**: Steps at the same level run concurrently
- **Saga compensation**: Failed workflow rolls back completed steps in reverse
- **Required vs optional**: Non-critical steps don\'t abort the workflow
- **Per-step retries**: Each step has its own retry count and backoff
- **Context sharing**: Steps communicate through the shared WorkflowContext
'''
    ),
    (
        "background-jobs/progress-tracking",
        "Implement real-time job progress tracking with WebSocket notifications, percentage updates, ETA calculation, and a dashboard API for monitoring job status.",
        '''Real-time job progress tracking with WebSocket updates and monitoring API:

```python
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, FastAPI, Query, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

logger = logging.getLogger("jobs.progress")


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class ProgressUpdate:
    job_id: str
    state: JobState
    progress: float              # 0.0 to 1.0
    current_step: int = 0
    total_steps: int = 0
    message: str = ""
    eta_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "state": self.state.value,
            "progress": round(self.progress, 4),
            "percent": round(self.progress * 100, 1),
            "current_step": self.current_step,
            "total_steps": self.total_steps,
            "message": self.message,
            "eta_seconds": round(self.eta_seconds, 1) if self.eta_seconds else None,
            "metadata": self.metadata,
            "updated_at": self.updated_at or datetime.now(timezone.utc).isoformat(),
        }


class ProgressTracker:
    """Redis-backed job progress tracking with pub/sub for real-time updates.

    Progress data is stored in Redis hashes for persistence.
    Updates are published via Redis pub/sub for WebSocket subscribers.
    ETA is calculated using exponential moving average of step durations.
    """

    CHANNEL_PREFIX = "job:progress:"
    KEY_PREFIX = "job:status:"
    EMA_ALPHA = 0.3   # smoothing factor for ETA calculation

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client
        self._step_start_times: dict[str, float] = {}
        self._avg_step_duration: dict[str, float] = {}

    async def start_job(
        self,
        job_id: str,
        total_steps: int,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Initialize job progress tracking."""
        update = ProgressUpdate(
            job_id=job_id,
            state=JobState.RUNNING,
            progress=0.0,
            current_step=0,
            total_steps=total_steps,
            message="Starting...",
            metadata=metadata or {},
        )
        await self._save_and_publish(update)
        self._step_start_times[job_id] = time.monotonic()

    async def update_progress(
        self,
        job_id: str,
        current_step: int,
        message: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Update job progress with ETA calculation."""
        existing = await self._get_status(job_id)
        if not existing:
            return

        total = int(existing.get("total_steps", "1"))
        progress = min(current_step / total, 1.0) if total > 0 else 0

        eta = self._calculate_eta(job_id, current_step, total)

        update = ProgressUpdate(
            job_id=job_id,
            state=JobState.RUNNING,
            progress=progress,
            current_step=current_step,
            total_steps=total,
            message=message,
            eta_seconds=eta,
            metadata=metadata or json.loads(existing.get("metadata", "{}")),
        )
        await self._save_and_publish(update)

    async def complete_job(self, job_id: str, result: dict[str, Any] | None = None) -> None:
        existing = await self._get_status(job_id)
        total = int(existing.get("total_steps", "1")) if existing else 1

        update = ProgressUpdate(
            job_id=job_id,
            state=JobState.COMPLETED,
            progress=1.0,
            current_step=total,
            total_steps=total,
            message="Completed",
            eta_seconds=0,
            metadata={"result": result} if result else {},
        )
        await self._save_and_publish(update)
        self._cleanup(job_id)

    async def fail_job(self, job_id: str, error: str) -> None:
        existing = await self._get_status(job_id)
        step = int(existing.get("current_step", "0")) if existing else 0
        total = int(existing.get("total_steps", "0")) if existing else 0

        update = ProgressUpdate(
            job_id=job_id,
            state=JobState.FAILED,
            progress=step / total if total > 0 else 0,
            current_step=step,
            total_steps=total,
            message=f"Failed: {error}",
        )
        await self._save_and_publish(update)
        self._cleanup(job_id)

    def _calculate_eta(self, job_id: str, current_step: int, total_steps: int) -> float | None:
        if current_step <= 0:
            return None
        now = time.monotonic()
        start = self._step_start_times.get(job_id)
        if not start:
            return None

        elapsed = now - start
        avg_per_step = elapsed / current_step

        if job_id in self._avg_step_duration:
            old_avg = self._avg_step_duration[job_id]
            avg_per_step = self.EMA_ALPHA * avg_per_step + (1 - self.EMA_ALPHA) * old_avg
        self._avg_step_duration[job_id] = avg_per_step

        remaining_steps = total_steps - current_step
        return max(0, remaining_steps * avg_per_step)

    async def _save_and_publish(self, update: ProgressUpdate) -> None:
        update.updated_at = datetime.now(timezone.utc).isoformat()
        data = update.to_dict()

        key = f"{self.KEY_PREFIX}{update.job_id}"
        await self._redis.hset(key, mapping={
            k: json.dumps(v) if isinstance(v, (dict, list)) else str(v)
            for k, v in data.items()
        })
        await self._redis.expire(key, 3600 * 24)

        channel = f"{self.CHANNEL_PREFIX}{update.job_id}"
        await self._redis.publish(channel, json.dumps(data))

    async def _get_status(self, job_id: str) -> dict[str, str] | None:
        key = f"{self.KEY_PREFIX}{job_id}"
        data = await self._redis.hgetall(key)
        if not data:
            return None
        return {k.decode(): v.decode() for k, v in data.items()}

    def _cleanup(self, job_id: str) -> None:
        self._step_start_times.pop(job_id, None)
        self._avg_step_duration.pop(job_id, None)

    async def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        data = await self._get_status(job_id)
        if not data:
            return None
        return {
            k: json.loads(v) if v.startswith(("{", "[")) else v
            for k, v in data.items()
        }


# ── WebSocket manager for real-time updates ──────────────────────

class ProgressWebSocketManager:
    """Manages WebSocket connections for real-time progress streaming."""

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def stream_progress(self, websocket: WebSocket, job_id: str) -> None:
        """Stream progress updates for a specific job via WebSocket."""
        await websocket.accept()

        tracker = ProgressTracker(self._redis)
        current = await tracker.get_job_status(job_id)
        if current:
            await websocket.send_json(current)

        pubsub = self._redis.pubsub()
        channel = f"{ProgressTracker.CHANNEL_PREFIX}{job_id}"
        await pubsub.subscribe(channel)

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    await websocket.send_json(data)
                    if data.get("state") in ("completed", "failed", "cancelled"):
                        break
        except WebSocketDisconnect:
            pass
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()

    async def stream_multiple(self, websocket: WebSocket, job_ids: list[str]) -> None:
        """Stream progress for multiple jobs simultaneously."""
        await websocket.accept()

        pubsub = self._redis.pubsub()
        channels = [f"{ProgressTracker.CHANNEL_PREFIX}{jid}" for jid in job_ids]
        await pubsub.subscribe(*channels)

        completed: set[str] = set()

        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    await websocket.send_json(data)
                    if data.get("state") in ("completed", "failed"):
                        completed.add(data["job_id"])
                        if completed >= set(job_ids):
                            break
        except WebSocketDisconnect:
            pass
        finally:
            await pubsub.unsubscribe(*channels)
            await pubsub.aclose()


# ── REST API for job monitoring ───────────────────────────────────

class JobStatusResponse(BaseModel):
    job_id: str
    state: str
    progress: float
    percent: float
    current_step: int
    total_steps: int
    message: str
    eta_seconds: float | None
    updated_at: str


router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])
app = FastAPI()


@router.get("/{job_id}/status", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    redis_client = aioredis.from_url("redis://localhost:6379")
    tracker = ProgressTracker(redis_client)
    status = await tracker.get_job_status(job_id)
    await redis_client.aclose()

    if not status:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Job not found")

    return JobStatusResponse(**status)


@app.websocket("/ws/jobs/{job_id}")
async def websocket_job_progress(websocket: WebSocket, job_id: str) -> None:
    redis_client = aioredis.from_url("redis://localhost:6379")
    manager = ProgressWebSocketManager(redis_client)
    await manager.stream_progress(websocket, job_id)
    await redis_client.aclose()


app.include_router(router)
```

Progress tracking architecture:

| Component | Purpose | Technology |
|---|---|---|
| ProgressTracker | Store and publish updates | Redis hash + pub/sub |
| WebSocket manager | Real-time streaming to clients | FastAPI WebSocket + Redis sub |
| REST API | Polling fallback, dashboard | FastAPI endpoint |
| ETA calculator | Predict completion time | Exponential moving average |

Key patterns:
- **Redis hash** for persistent progress state (survives reconnects)
- **Redis pub/sub** for real-time push to WebSocket subscribers
- **EMA-based ETA**: Smooths out step duration variance for better estimates
- **Multi-job streaming**: Subscribe to multiple job channels simultaneously
- **Auto-close**: WebSocket closes when job reaches terminal state
- **Polling fallback**: REST endpoint for clients that cannot use WebSocket
'''
    ),
]
