"""Task queues — Celery, background jobs, cron scheduling, and job prioritization."""

PAIRS = [
    (
        "backend/celery-patterns",
        "Show Celery patterns: task definitions, chains, groups, error handling, and monitoring.",
        '''Celery task queue patterns:

```python
from celery import Celery, chain, group, chord, signature
from celery.utils.log import get_task_logger
from celery.exceptions import MaxRetriesExceededError
import time

# --- App configuration ---

app = Celery("myapp")
app.config_from_object({
    "broker_url": "redis://localhost:6379/0",
    "result_backend": "redis://localhost:6379/1",
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],
    "task_track_started": True,
    "task_time_limit": 300,          # Hard limit: 5 minutes
    "task_soft_time_limit": 240,     # Soft limit: 4 minutes (raises SoftTimeLimitExceeded)
    "worker_prefetch_multiplier": 1, # Fair scheduling
    "task_acks_late": True,          # Ack after completion (at-least-once)
    "task_reject_on_worker_lost": True,
    "worker_max_tasks_per_child": 100,  # Restart worker after 100 tasks (prevent memory leaks)
})

logger = get_task_logger(__name__)


# --- Basic task with retry ---

@app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,        # Exponential backoff
    retry_backoff_max=600,     # Max 10 min between retries
    retry_jitter=True,         # Add randomness
)
def send_email(self, to: str, subject: str, body: str):
    """Send email with automatic retry on connection errors."""
    try:
        # ... send email ...
        logger.info("Email sent to %s: %s", to, subject)
        return {"status": "sent", "to": to}
    except Exception as exc:
        logger.error("Failed to send email: %s", exc)
        raise self.retry(exc=exc)


# --- Task with custom error handling ---

@app.task(bind=True, max_retries=3)
def process_payment(self, order_id: str, amount: float):
    """Process payment with manual retry logic."""
    try:
        result = charge_card(order_id, amount)
        return {"order_id": order_id, "payment_id": result["id"]}

    except TemporaryError as exc:
        # Retry with exponential backoff
        raise self.retry(
            exc=exc,
            countdown=min(2 ** self.request.retries * 30, 600),
        )

    except PermanentError as exc:
        # Don't retry — mark as failed
        logger.error("Permanent payment failure for %s: %s", order_id, exc)
        update_order_status(order_id, "payment_failed")
        return {"order_id": order_id, "error": str(exc)}

    except MaxRetriesExceededError:
        logger.error("Max retries exceeded for order %s", order_id)
        update_order_status(order_id, "payment_failed")
        raise


# --- Task chains (sequential pipeline) ---

@app.task
def validate_order(order_id: str) -> dict:
    return {"order_id": order_id, "valid": True}

@app.task
def charge_payment(validation_result: dict) -> dict:
    return {**validation_result, "payment_id": "PAY-001"}

@app.task
def create_shipment(payment_result: dict) -> dict:
    return {**payment_result, "tracking": "TRK-001"}

@app.task
def send_confirmation(shipment_result: dict) -> dict:
    return {**shipment_result, "notified": True}

# Chain: each task passes result to next
order_pipeline = chain(
    validate_order.s("ORD-123"),
    charge_payment.s(),
    create_shipment.s(),
    send_confirmation.s(),
)
# result = order_pipeline.apply_async()


# --- Group (parallel execution) ---

@app.task
def generate_report(report_type: str, date_range: str) -> dict:
    return {"type": report_type, "rows": 1000}

# Run 3 reports in parallel
parallel_reports = group(
    generate_report.s("sales", "2024-Q1"),
    generate_report.s("inventory", "2024-Q1"),
    generate_report.s("customers", "2024-Q1"),
)
# result = parallel_reports.apply_async()
# results = result.get()  # List of 3 results


# --- Chord (parallel then callback) ---

@app.task
def merge_reports(results: list[dict]) -> dict:
    return {"merged": True, "total_rows": sum(r["rows"] for r in results)}

# Run reports in parallel, then merge
full_pipeline = chord(
    [
        generate_report.s("sales", "2024-Q1"),
        generate_report.s("inventory", "2024-Q1"),
    ],
    merge_reports.s(),
)


# --- Periodic tasks (Celery Beat) ---

app.conf.beat_schedule = {
    "cleanup-expired-sessions": {
        "task": "myapp.tasks.cleanup_sessions",
        "schedule": 3600.0,  # Every hour
    },
    "daily-report": {
        "task": "myapp.tasks.generate_daily_report",
        "schedule": {
            "hour": 6,
            "minute": 0,
        },
    },
    "check-health": {
        "task": "myapp.tasks.health_check",
        "schedule": 60.0,  # Every minute
        "options": {"expires": 30},  # Discard if not run within 30s
    },
}
```

Celery patterns:
1. **`autoretry_for`** — automatic retry for specific exception types
2. **`retry_backoff=True`** — exponential backoff with jitter
3. **`chain()`** — sequential pipeline where each task feeds the next
4. **`chord()`** — parallel group with callback when all complete
5. **`task_acks_late`** — acknowledge after completion for at-least-once delivery'''
    ),
    (
        "backend/job-scheduling",
        "Show job scheduling patterns: cron expressions, distributed locking, and job deduplication.",
        '''Job scheduling patterns:

```python
import asyncio
import hashlib
import time
import logging
from dataclasses import dataclass, field
from typing import Callable, Awaitable
from datetime import datetime, timedelta
from croniter import croniter

logger = logging.getLogger(__name__)


# --- Cron-based scheduler ---

@dataclass
class ScheduledJob:
    name: str
    cron: str                                    # Cron expression
    handler: Callable[..., Awaitable[None]]
    timeout: float = 300.0                       # 5 min default
    enabled: bool = True
    last_run: float | None = None
    run_count: int = 0


class Scheduler:
    """Lightweight async cron scheduler."""

    def __init__(self):
        self.jobs: dict[str, ScheduledJob] = {}
        self._running = False

    def register(self, job: ScheduledJob):
        self.jobs[job.name] = job

    async def start(self):
        """Run scheduler loop."""
        self._running = True
        logger.info("Scheduler started with %d jobs", len(self.jobs))

        while self._running:
            now = datetime.now()

            for job in self.jobs.values():
                if not job.enabled:
                    continue

                cron = croniter(job.cron, now - timedelta(seconds=1))
                next_run = cron.get_next(datetime)

                # Check if job should run now (within 1 second window)
                if abs((next_run - now).total_seconds()) < 1:
                    asyncio.create_task(self._execute(job))

            await asyncio.sleep(1)

    async def _execute(self, job: ScheduledJob):
        """Execute job with timeout and error handling."""
        logger.info("Executing job: %s", job.name)
        start = time.monotonic()

        try:
            await asyncio.wait_for(job.handler(), timeout=job.timeout)
            elapsed = time.monotonic() - start
            job.last_run = time.time()
            job.run_count += 1
            logger.info("Job %s completed in %.2fs", job.name, elapsed)

        except asyncio.TimeoutError:
            logger.error("Job %s timed out after %.0fs", job.name, job.timeout)

        except Exception as e:
            logger.exception("Job %s failed: %s", job.name, e)

    def stop(self):
        self._running = False


# --- Distributed lock (prevent duplicate execution) ---

class DistributedLock:
    """Redis-based distributed lock for job deduplication."""

    def __init__(self, redis_client):
        self.redis = redis_client

    async def acquire(self, name: str, ttl: int = 300) -> bool:
        """Try to acquire lock. Returns True if acquired."""
        lock_key = f"lock:{name}"
        # SET NX (only if not exists) with TTL
        acquired = await self.redis.set(
            lock_key, "locked", nx=True, ex=ttl,
        )
        return bool(acquired)

    async def release(self, name: str):
        """Release lock."""
        await self.redis.delete(f"lock:{name}")

    async def extend(self, name: str, ttl: int = 300) -> bool:
        """Extend lock TTL (for long-running jobs)."""
        lock_key = f"lock:{name}"
        return bool(await self.redis.expire(lock_key, ttl))


class DistributedScheduler(Scheduler):
    """Scheduler safe for multiple instances (distributed lock)."""

    def __init__(self, lock: DistributedLock):
        super().__init__()
        self.lock = lock

    async def _execute(self, job: ScheduledJob):
        # Only one instance runs the job
        if not await self.lock.acquire(f"job:{job.name}", ttl=int(job.timeout)):
            logger.debug("Job %s locked by another instance", job.name)
            return

        try:
            await super()._execute(job)
        finally:
            await self.lock.release(f"job:{job.name}")


# --- Job deduplication ---

class JobDeduplicator:
    """Prevent duplicate job submissions."""

    def __init__(self, redis_client):
        self.redis = redis_client

    def job_key(self, job_name: str, **params) -> str:
        """Generate deduplication key from job name + params."""
        param_str = str(sorted(params.items()))
        return hashlib.sha256(
            f"{job_name}:{param_str}".encode()
        ).hexdigest()[:16]

    async def submit_unique(
        self,
        job_name: str,
        handler: Callable,
        ttl: int = 3600,
        **params,
    ) -> bool:
        """Submit job only if not already queued/running."""
        key = f"dedup:{self.job_key(job_name, **params)}"

        if await self.redis.exists(key):
            logger.info("Job %s already queued, skipping", job_name)
            return False

        await self.redis.set(key, "queued", ex=ttl)

        try:
            await handler(**params)
            await self.redis.set(key, "completed", ex=ttl)
            return True
        except Exception:
            await self.redis.delete(key)
            raise


# --- Cron expression examples ---

# ┌──── minute (0-59)
# │ ┌──── hour (0-23)
# │ │ ┌──── day of month (1-31)
# │ │ │ ┌──── month (1-12)
# │ │ │ │ ┌──── day of week (0-6, 0=Sunday)
# │ │ │ │ │
# * * * * *

CRON_EXAMPLES = {
    "every_minute":      "* * * * *",
    "every_5_minutes":   "*/5 * * * *",
    "hourly":            "0 * * * *",
    "daily_6am":         "0 6 * * *",
    "weekdays_9am":      "0 9 * * 1-5",
    "monthly_first":     "0 0 1 * *",
    "every_30s":         "*/30 * * * * *",  # With seconds (non-standard)
}
```

Job scheduling patterns:
1. **Cron expressions** — standard time-based scheduling (`0 6 * * *` = daily 6am)
2. **Distributed lock** — Redis SET NX prevents duplicate execution across instances
3. **Job deduplication** — hash params to prevent re-queuing identical jobs
4. **Timeout per job** — prevent runaway jobs from blocking the scheduler
5. **Lock extension** — long-running jobs extend their lock TTL to stay safe'''
    ),
]
"""
