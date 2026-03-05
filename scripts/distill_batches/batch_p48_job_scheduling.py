"""Job scheduling — task queues, background workers, cron patterns, and distributed scheduling."""

PAIRS = [
    (
        "python/celery-patterns",
        "Show Celery task queue patterns: task definition, retry logic, chains/groups, and monitoring.",
        '''Celery task queue patterns:

```python
from celery import Celery, chain, group, chord, shared_task
from celery.utils.log import get_task_logger
from celery.signals import task_failure, task_success
from datetime import timedelta
import time

app = Celery("myapp")
app.config_from_object({
    "broker_url": "redis://localhost:6379/0",
    "result_backend": "redis://localhost:6379/1",
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],
    "timezone": "UTC",
    "task_track_started": True,
    "task_time_limit": 300,          # Hard kill after 5 min
    "task_soft_time_limit": 240,     # SoftTimeLimitExceeded after 4 min
    "worker_prefetch_multiplier": 1, # Fair scheduling
    "task_acks_late": True,          # Ack after completion (at-least-once)
    "worker_max_tasks_per_child": 100,  # Restart worker after 100 tasks
})

logger = get_task_logger(__name__)


# --- Task with retry ---

@app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,        # Exponential backoff
    retry_backoff_max=600,     # Max 10 min between retries
    retry_jitter=True,         # Random jitter
)
def send_email(self, to: str, subject: str, body: str):
    try:
        smtp_client.send(to=to, subject=subject, body=body)
        logger.info("Email sent to %s", to)
    except ConnectionError as exc:
        logger.warning("SMTP connection failed, retrying...")
        raise self.retry(exc=exc)


# --- Task with rate limiting ---

@app.task(rate_limit="10/m")  # Max 10 per minute per worker
def call_external_api(endpoint: str, payload: dict) -> dict:
    response = requests.post(endpoint, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()


# --- Priority queues ---

@app.task(queue="high_priority")
def process_payment(order_id: str):
    ...

@app.task(queue="low_priority")
def generate_report(report_id: str):
    ...

# Worker command: celery -A myapp worker -Q high_priority,default,low_priority


# --- Task chains and groups ---

def process_order(order_id: str):
    """Chain: validate -> charge -> fulfill -> notify (sequential)."""
    workflow = chain(
        validate_order.s(order_id),
        charge_payment.s(),        # Receives result of previous
        fulfill_order.s(),
        send_confirmation.s(),
    )
    workflow.apply_async()


def process_batch_images(image_urls: list[str]):
    """Group: process all images in parallel, then aggregate."""
    workflow = chord(
        group(resize_image.s(url) for url in image_urls),
        aggregate_results.s(),     # Called when all complete
    )
    workflow.apply_async()


@app.task
def validate_order(order_id: str) -> dict:
    order = db.get_order(order_id)
    if not order.items:
        raise ValueError("Empty order")
    return {"order_id": order_id, "total": order.total}

@app.task
def charge_payment(order_data: dict) -> dict:
    payment_id = stripe.charge(order_data["total"])
    return {**order_data, "payment_id": payment_id}

@app.task
def fulfill_order(order_data: dict) -> dict:
    warehouse.ship(order_data["order_id"])
    return order_data

@app.task
def send_confirmation(order_data: dict):
    send_email.delay(
        to=get_customer_email(order_data["order_id"]),
        subject="Order Confirmed",
        body=f"Order {order_data['order_id']} has been shipped!",
    )


# --- Periodic tasks (cron) ---

app.conf.beat_schedule = {
    "cleanup-expired-sessions": {
        "task": "myapp.tasks.cleanup_sessions",
        "schedule": timedelta(hours=1),
    },
    "daily-report": {
        "task": "myapp.tasks.generate_daily_report",
        "schedule": crontab(hour=6, minute=0),  # 6 AM UTC
    },
    "weekly-digest": {
        "task": "myapp.tasks.send_weekly_digest",
        "schedule": crontab(hour=9, minute=0, day_of_week=1),  # Monday 9 AM
    },
}

from celery.schedules import crontab

@app.task
def cleanup_sessions():
    deleted = db.execute(
        "DELETE FROM sessions WHERE expires_at < NOW()"
    )
    logger.info("Cleaned up %d expired sessions", deleted)


# --- Signals for monitoring ---

@task_failure.connect
def handle_task_failure(sender, task_id, exception, **kwargs):
    logger.error("Task %s failed: %s", sender.name, exception)
    # Send to error tracking (Sentry, etc.)

@task_success.connect
def handle_task_success(sender, result, **kwargs):
    # Track metrics
    metrics.increment(f"task.{sender.name}.success")
```

Celery patterns:
1. **`bind=True`** — access `self` for manual retry control
2. **`task_acks_late`** — acknowledge after completion for at-least-once delivery
3. **`chain`** for sequential, **`group`** for parallel, **`chord`** for fan-out/fan-in
4. **Rate limiting** — prevent overwhelming external APIs
5. **Priority queues** — separate workers for different priority levels'''
    ),
    (
        "python/apscheduler-patterns",
        "Show APScheduler patterns: scheduled jobs, triggers, job stores, and production configuration.",
        '''APScheduler job scheduling patterns:

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.combining import OrTrigger
from apscheduler.jobstores.redis import RedisJobStore
from apscheduler.executors.pool import ThreadPoolExecutor, ProcessPoolExecutor
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


def create_scheduler() -> AsyncIOScheduler:
    """Production scheduler with Redis job store."""
    jobstores = {
        "default": RedisJobStore(
            host="localhost",
            port=6379,
            db=2,
        ),
    }

    executors = {
        "default": ThreadPoolExecutor(20),     # I/O-bound tasks
        "processpool": ProcessPoolExecutor(4),  # CPU-bound tasks
    }

    job_defaults = {
        "coalesce": True,         # Combine missed runs into one
        "max_instances": 1,       # Prevent overlapping runs
        "misfire_grace_time": 300, # Allow 5 min late execution
    }

    scheduler = AsyncIOScheduler(
        jobstores=jobstores,
        executors=executors,
        job_defaults=job_defaults,
        timezone="UTC",
    )

    # Register jobs
    register_jobs(scheduler)

    return scheduler


def register_jobs(scheduler: AsyncIOScheduler):
    # Cron trigger — run at specific times
    scheduler.add_job(
        daily_report,
        trigger=CronTrigger(hour=6, minute=0),
        id="daily_report",
        name="Generate daily report",
        replace_existing=True,
    )

    # Interval trigger — run every N minutes
    scheduler.add_job(
        health_check,
        trigger=IntervalTrigger(minutes=5),
        id="health_check",
        name="Check service health",
        replace_existing=True,
    )

    # Complex cron expression
    scheduler.add_job(
        weekly_cleanup,
        trigger=CronTrigger(
            day_of_week="sun",
            hour=2,
            minute=0,
        ),
        id="weekly_cleanup",
        name="Weekly data cleanup",
        replace_existing=True,
    )

    # CPU-bound task uses process pool
    scheduler.add_job(
        compute_analytics,
        trigger=CronTrigger(hour="*/6"),  # Every 6 hours
        id="analytics",
        executor="processpool",
        replace_existing=True,
    )


# --- Job functions ---

async def daily_report():
    logger.info("Generating daily report")
    try:
        data = await fetch_report_data()
        report = generate_report(data)
        await send_report_email(report)
        logger.info("Daily report sent successfully")
    except Exception as e:
        logger.error("Daily report failed: %s", e)
        await notify_ops(f"Daily report failed: {e}")


async def health_check():
    """Check external service health."""
    services = {
        "database": check_db_health,
        "redis": check_redis_health,
        "api": check_api_health,
    }
    for name, check_fn in services.items():
        try:
            await check_fn()
        except Exception as e:
            logger.error("Health check failed for %s: %s", name, e)
            await notify_ops(f"Service {name} is unhealthy: {e}")


async def weekly_cleanup():
    """Clean up old data."""
    deleted_sessions = await db.execute(
        "DELETE FROM sessions WHERE expires_at < NOW() - INTERVAL '7 days'"
    )
    deleted_logs = await db.execute(
        "DELETE FROM audit_logs WHERE created_at < NOW() - INTERVAL '90 days'"
    )
    logger.info("Cleanup: %d sessions, %d logs deleted",
                deleted_sessions, deleted_logs)


# --- Dynamic job management ---

class JobManager:
    def __init__(self, scheduler: AsyncIOScheduler):
        self.scheduler = scheduler

    def schedule_one_time(self, func, run_at: datetime, **kwargs):
        """Schedule a one-time job."""
        return self.scheduler.add_job(
            func,
            trigger="date",
            run_date=run_at,
            kwargs=kwargs,
        )

    def list_jobs(self) -> list[dict]:
        return [
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time),
                "trigger": str(job.trigger),
            }
            for job in self.scheduler.get_jobs()
        ]

    def pause_job(self, job_id: str):
        self.scheduler.pause_job(job_id)

    def resume_job(self, job_id: str):
        self.scheduler.resume_job(job_id)

    def remove_job(self, job_id: str):
        self.scheduler.remove_job(job_id)


# --- Integration with FastAPI ---

from fastapi import FastAPI

app = FastAPI()
scheduler = create_scheduler()

@app.on_event("startup")
async def startup():
    scheduler.start()

@app.on_event("shutdown")
async def shutdown():
    scheduler.shutdown()

@app.get("/jobs")
async def list_jobs():
    manager = JobManager(scheduler)
    return manager.list_jobs()
```

Scheduling patterns:
1. **`coalesce=True`** — if scheduler was down, run missed job once (not N times)
2. **`max_instances=1`** — prevent overlapping runs of same job
3. **Redis job store** — persist jobs across restarts, share across instances
4. **Thread vs process pool** — threads for I/O-bound, processes for CPU-bound
5. **Replace existing** — `replace_existing=True` for idempotent job registration'''
    ),
]
