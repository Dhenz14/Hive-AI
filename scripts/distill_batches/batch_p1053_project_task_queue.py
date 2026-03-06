PAIRS = [
    ("projects/task-queue", r'''<think>
A Redis-backed task queue needs to handle job serialization, queue operations,
and worker coordination. I will use a simple Redis list-based queue with
JSON-serialized job payloads and a reliable queue pattern (BRPOPLPUSH).
</think>
Build a Redis-backed task queue with job serialization, priority support, and reliable dequeuing.''', r'''import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import redis


class JobStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    DEAD = "dead"


@dataclass
class Job:
    """Represents a task in the queue."""
    id: str
    task_name: str
    args: list
    kwargs: dict
    priority: int = 0
    max_retries: int = 3
    retry_count: int = 0
    status: str = "pending"
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    error: Optional[str] = None
    result: Any = None
    queue_name: str = "default"

    def serialize(self) -> str:
        data = asdict(self)
        return json.dumps(data)

    @classmethod
    def deserialize(cls, raw: str) -> "Job":
        data = json.loads(raw)
        return cls(**data)


class TaskQueue:
    """Redis-backed task queue with priority support."""

    def __init__(self, redis_url: str = "redis://localhost:6379", prefix: str = "tq"):
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._prefix = prefix
        self._task_registry: Dict[str, Callable] = {}

    def _key(self, *parts: str) -> str:
        return ":".join([self._prefix] + list(parts))

    def register_task(self, name: str, func: Callable) -> None:
        """Register a task handler function."""
        self._task_registry[name] = func

    def task(self, name: Optional[str] = None):
        """Decorator to register a task handler."""
        def decorator(func: Callable) -> Callable:
            task_name = name or f"{func.__module__}.{func.__qualname__}"
            self.register_task(task_name, func)
            func.delay = lambda *a, **kw: self.enqueue(task_name, *a, **kw)
            return func
        return decorator

    def enqueue(
        self,
        task_name: str,
        *args,
        priority: int = 0,
        max_retries: int = 3,
        queue_name: str = "default",
        **kwargs,
    ) -> Job:
        """Add a job to the queue."""
        job = Job(
            id=str(uuid.uuid4()),
            task_name=task_name,
            args=list(args),
            kwargs=kwargs,
            priority=priority,
            max_retries=max_retries,
            queue_name=queue_name,
        )

        pipe = self._redis.pipeline()
        # Store job data
        pipe.hset(self._key("jobs"), job.id, job.serialize())
        # Add to priority queue using sorted set (lower score = higher priority)
        queue_key = self._key("queue", queue_name)
        score = -priority * 1e10 + job.created_at
        pipe.zadd(queue_key, {job.id: score})
        # Track pending count
        pipe.incr(self._key("stats", "enqueued"))
        pipe.execute()

        return job

    def dequeue(self, queue_name: str = "default", timeout: int = 5) -> Optional[Job]:
        """Dequeue the highest priority job. Blocking with timeout."""
        queue_key = self._key("queue", queue_name)
        processing_key = self._key("processing", queue_name)

        # Atomic pop from sorted set
        result = self._redis.zpopmin(queue_key, count=1)
        if not result:
            # Block-wait for new items
            time.sleep(min(timeout, 1))
            result = self._redis.zpopmin(queue_key, count=1)
            if not result:
                return None

        job_id = result[0][0]
        raw = self._redis.hget(self._key("jobs"), job_id)
        if not raw:
            return None

        job = Job.deserialize(raw)
        job.status = JobStatus.PROCESSING
        job.started_at = time.time()

        # Move to processing set
        pipe = self._redis.pipeline()
        pipe.sadd(processing_key, job_id)
        pipe.hset(self._key("jobs"), job_id, job.serialize())
        pipe.execute()

        return job

    def complete(self, job: Job, result: Any = None) -> None:
        """Mark a job as completed."""
        job.status = JobStatus.COMPLETED
        job.completed_at = time.time()
        job.result = result

        pipe = self._redis.pipeline()
        pipe.hset(self._key("jobs"), job.id, job.serialize())
        pipe.srem(self._key("processing", job.queue_name), job.id)
        pipe.incr(self._key("stats", "completed"))
        pipe.execute()

    def fail(self, job: Job, error: str) -> None:
        """Mark a job as failed, retry if possible."""
        job.retry_count += 1
        job.error = error

        pipe = self._redis.pipeline()
        pipe.srem(self._key("processing", job.queue_name), job.id)

        if job.retry_count <= job.max_retries:
            job.status = JobStatus.PENDING
            score = -job.priority * 1e10 + time.time()
            pipe.zadd(self._key("queue", job.queue_name), {job.id: score})
            pipe.incr(self._key("stats", "retried"))
        else:
            job.status = JobStatus.DEAD
            pipe.lpush(self._key("dead_letter"), job.id)
            pipe.incr(self._key("stats", "dead"))

        pipe.hset(self._key("jobs"), job.id, job.serialize())
        pipe.execute()

    def get_job(self, job_id: str) -> Optional[Job]:
        """Retrieve a job by ID."""
        raw = self._redis.hget(self._key("jobs"), job_id)
        return Job.deserialize(raw) if raw else None

    def get_stats(self) -> dict:
        """Get queue statistics."""
        return {
            "enqueued": int(self._redis.get(self._key("stats", "enqueued")) or 0),
            "completed": int(self._redis.get(self._key("stats", "completed")) or 0),
            "retried": int(self._redis.get(self._key("stats", "retried")) or 0),
            "dead": int(self._redis.get(self._key("stats", "dead")) or 0),
        }
'''),
    ("projects/task-queue", r'''Implement a worker pool that processes jobs from the task queue with concurrency control and graceful shutdown.''', r'''import logging
import os
import signal
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class Worker:
    """A single worker that processes jobs from the queue."""

    def __init__(self, worker_id: str, queue, task_registry: Dict[str, Callable]):
        self.worker_id = worker_id
        self._queue = queue
        self._registry = task_registry
        self._running = False
        self._current_job = None

    def process_one(self) -> bool:
        """Process a single job. Returns True if a job was processed."""
        job = self._queue.dequeue(timeout=2)
        if not job:
            return False

        self._current_job = job
        handler = self._registry.get(job.task_name)

        if not handler:
            self._queue.fail(job, f"Unknown task: {job.task_name}")
            logger.error(f"Worker {self.worker_id}: Unknown task {job.task_name}")
            self._current_job = None
            return True

        try:
            logger.info(f"Worker {self.worker_id}: Processing job {job.id} ({job.task_name})")
            result = handler(*job.args, **job.kwargs)
            self._queue.complete(job, result)
            logger.info(f"Worker {self.worker_id}: Completed job {job.id}")
        except Exception as e:
            logger.error(f"Worker {self.worker_id}: Job {job.id} failed: {e}")
            self._queue.fail(job, str(e))
        finally:
            self._current_job = None

        return True

    def run(self) -> None:
        """Run the worker loop."""
        self._running = True
        logger.info(f"Worker {self.worker_id} started")

        while self._running:
            try:
                self.process_one()
            except Exception as e:
                logger.error(f"Worker {self.worker_id}: Unexpected error: {e}")
                time.sleep(1)

        logger.info(f"Worker {self.worker_id} stopped")

    def stop(self) -> None:
        """Signal the worker to stop after the current job."""
        self._running = False


class WorkerPool:
    """Manages a pool of workers with concurrency control."""

    def __init__(
        self,
        queue,
        concurrency: int = 4,
        queue_names: Optional[List[str]] = None,
    ):
        self._queue = queue
        self._concurrency = concurrency
        self._queue_names = queue_names or ["default"]
        self._workers: List[Worker] = []
        self._executor: Optional[ThreadPoolExecutor] = None
        self._futures: List[Future] = []
        self._shutdown_event = threading.Event()
        self._started = False

    def start(self) -> None:
        """Start the worker pool."""
        if self._started:
            return

        logger.info(f"Starting worker pool with {self._concurrency} workers")
        self._executor = ThreadPoolExecutor(max_workers=self._concurrency)
        self._started = True

        for i in range(self._concurrency):
            worker_id = f"worker-{os.getpid()}-{i}"
            worker = Worker(worker_id, self._queue, self._queue._task_registry)
            self._workers.append(worker)
            future = self._executor.submit(worker.run)
            self._futures.append(future)

        # Install signal handlers for graceful shutdown
        self._install_signal_handlers()
        logger.info("Worker pool started")

    def stop(self, timeout: float = 30.0) -> None:
        """Gracefully stop all workers."""
        if not self._started:
            return

        logger.info("Stopping worker pool...")
        for worker in self._workers:
            worker.stop()

        self._shutdown_event.set()

        if self._executor:
            self._executor.shutdown(wait=True)

        self._workers.clear()
        self._futures.clear()
        self._started = False
        logger.info("Worker pool stopped")

    def _install_signal_handlers(self) -> None:
        """Install signal handlers for graceful shutdown."""
        def handler(signum, frame):
            logger.info(f"Received signal {signum}, initiating graceful shutdown")
            self.stop()

        try:
            signal.signal(signal.SIGTERM, handler)
            signal.signal(signal.SIGINT, handler)
        except (OSError, ValueError):
            pass  # Signal handling not available (e.g., not main thread)

    def wait(self) -> None:
        """Block until shutdown is requested."""
        self._shutdown_event.wait()

    def get_status(self) -> dict:
        """Get status of all workers."""
        return {
            "pool_size": self._concurrency,
            "active_workers": len(self._workers),
            "workers": [
                {
                    "id": w.worker_id,
                    "running": w._running,
                    "current_job": w._current_job.id if w._current_job else None,
                }
                for w in self._workers
            ],
        }

    @property
    def is_running(self) -> bool:
        return self._started


def run_workers(queue, concurrency: int = 4) -> None:
    """Convenience function to start workers and block until shutdown."""
    pool = WorkerPool(queue, concurrency=concurrency)
    pool.start()
    try:
        pool.wait()
    except KeyboardInterrupt:
        pool.stop()
'''),
    ("projects/task-queue", r'''<think>
Retry logic needs exponential backoff with configurable parameters.
Dead letter queues store permanently failed jobs for inspection.
I should make retry policies configurable per task.
</think>
Implement retry logic with exponential backoff and a dead letter queue for permanently failed jobs.''', r'''import math
import time
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Callable

logger = logging.getLogger(__name__)


@dataclass
class RetryPolicy:
    """Configuration for job retry behavior."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 300.0
    exponential_base: float = 2.0
    jitter: bool = True
    retry_on: Optional[list] = None  # List of exception class names to retry on

    def get_delay(self, attempt: int) -> float:
        """Calculate the delay before the next retry."""
        delay = self.base_delay * (self.exponential_base ** attempt)
        delay = min(delay, self.max_delay)
        if self.jitter:
            import random
            delay = delay * (0.5 + random.random())
        return delay

    def should_retry(self, error: Exception, attempt: int) -> bool:
        """Determine if the job should be retried."""
        if attempt >= self.max_retries:
            return False
        if self.retry_on:
            error_name = type(error).__name__
            return error_name in self.retry_on
        return True


# Default retry policies for common scenarios
RETRY_POLICIES = {
    "default": RetryPolicy(max_retries=3, base_delay=1.0),
    "aggressive": RetryPolicy(max_retries=5, base_delay=0.5, max_delay=60.0),
    "patient": RetryPolicy(max_retries=10, base_delay=5.0, max_delay=600.0),
    "no_retry": RetryPolicy(max_retries=0),
    "network": RetryPolicy(
        max_retries=5,
        base_delay=2.0,
        max_delay=120.0,
        retry_on=["ConnectionError", "TimeoutError", "HTTPError"],
    ),
}


class RetryManager:
    """Manages retry logic for jobs with configurable policies."""

    def __init__(self, queue):
        self._queue = queue
        self._policies: Dict[str, RetryPolicy] = dict(RETRY_POLICIES)

    def register_policy(self, name: str, policy: RetryPolicy) -> None:
        """Register a custom retry policy."""
        self._policies[name] = policy

    def get_policy(self, policy_name: str) -> RetryPolicy:
        """Get a retry policy by name."""
        return self._policies.get(policy_name, self._policies["default"])

    def handle_failure(self, job, error: Exception, policy_name: str = "default") -> str:
        """Handle a job failure. Returns the action taken."""
        policy = self.get_policy(policy_name)

        if policy.should_retry(error, job.retry_count):
            delay = policy.get_delay(job.retry_count)
            logger.info(
                f"Job {job.id} will retry in {delay:.1f}s "
                f"(attempt {job.retry_count + 1}/{policy.max_retries})"
            )
            self._schedule_retry(job, delay)
            return "retried"
        else:
            logger.warning(f"Job {job.id} sent to dead letter queue after {job.retry_count} retries")
            self._send_to_dead_letter(job, error)
            return "dead_lettered"

    def _schedule_retry(self, job, delay: float) -> None:
        """Schedule a job for retry after a delay."""
        job.retry_count += 1
        job.status = "pending"
        # In a real implementation, use Redis ZADD with score = time.time() + delay
        # For delayed execution support
        retry_at = time.time() + delay
        self._queue._redis.zadd(
            self._queue._key("delayed"),
            {job.id: retry_at},
        )
        self._queue._redis.hset(
            self._queue._key("jobs"),
            job.id,
            job.serialize(),
        )

    def _send_to_dead_letter(self, job, error: Exception) -> None:
        """Send a permanently failed job to the dead letter queue."""
        job.status = "dead"
        job.error = str(error)
        job.completed_at = time.time()

        pipe = self._queue._redis.pipeline()
        pipe.hset(self._queue._key("jobs"), job.id, job.serialize())
        pipe.lpush(self._queue._key("dead_letter"), job.id)
        pipe.srem(self._queue._key("processing", job.queue_name), job.id)
        pipe.incr(self._queue._key("stats", "dead"))
        pipe.execute()


class DeadLetterQueue:
    """Manages permanently failed jobs for inspection and replay."""

    def __init__(self, queue):
        self._queue = queue

    def list_jobs(self, offset: int = 0, limit: int = 20) -> List[dict]:
        """List dead letter jobs with pagination."""
        job_ids = self._queue._redis.lrange(
            self._queue._key("dead_letter"), offset, offset + limit - 1
        )
        jobs = []
        for job_id in job_ids:
            raw = self._queue._redis.hget(self._queue._key("jobs"), job_id)
            if raw:
                job = self._queue._queue_class.deserialize(raw) if hasattr(self._queue, '_queue_class') else json.loads(raw)
                jobs.append(job if isinstance(job, dict) else job.__dict__)
        return jobs

    def count(self) -> int:
        """Get the number of dead letter jobs."""
        return self._queue._redis.llen(self._queue._key("dead_letter"))

    def retry_job(self, job_id: str) -> bool:
        """Retry a dead letter job by re-enqueueing it."""
        raw = self._queue._redis.hget(self._queue._key("jobs"), job_id)
        if not raw:
            return False

        from .queue import Job
        job = Job.deserialize(raw)
        if job.status != "dead":
            return False

        # Remove from dead letter queue
        self._queue._redis.lrem(self._queue._key("dead_letter"), 1, job_id)

        # Re-enqueue with reset retry count
        job.status = "pending"
        job.retry_count = 0
        job.error = None
        job.started_at = None
        job.completed_at = None

        score = -job.priority * 1e10 + time.time()
        pipe = self._queue._redis.pipeline()
        pipe.hset(self._queue._key("jobs"), job.id, job.serialize())
        pipe.zadd(self._queue._key("queue", job.queue_name), {job.id: score})
        pipe.execute()

        logger.info(f"Dead letter job {job_id} re-enqueued")
        return True

    def retry_all(self) -> int:
        """Retry all dead letter jobs. Returns count of retried jobs."""
        count = 0
        while True:
            job_id = self._queue._redis.rpop(self._queue._key("dead_letter"))
            if not job_id:
                break
            if self.retry_job(job_id):
                count += 1
        return count

    def purge(self, older_than: Optional[float] = None) -> int:
        """Delete dead letter jobs. Optionally filter by age."""
        if older_than is None:
            count = self.count()
            self._queue._redis.delete(self._queue._key("dead_letter"))
            return count

        now = time.time()
        removed = 0
        job_ids = self._queue._redis.lrange(self._queue._key("dead_letter"), 0, -1)
        for job_id in job_ids:
            raw = self._queue._redis.hget(self._queue._key("jobs"), job_id)
            if raw:
                data = json.loads(raw)
                if data.get("completed_at") and (now - data["completed_at"]) > older_than:
                    self._queue._redis.lrem(self._queue._key("dead_letter"), 1, job_id)
                    self._queue._redis.hdel(self._queue._key("jobs"), job_id)
                    removed += 1
        return removed
'''),
    ("projects/task-queue", r'''Build a monitoring dashboard data provider for the task queue, with metrics collection and health checks.''', r'''import time
import threading
import logging
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class MetricPoint:
    """A single metric measurement."""
    timestamp: float
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


class MetricsCollector:
    """Collects and stores time-series metrics for the task queue."""

    def __init__(self, retention_seconds: float = 3600.0):
        self._metrics: Dict[str, Deque[MetricPoint]] = {}
        self._retention = retention_seconds
        self._lock = threading.Lock()

    def record(self, name: str, value: float, labels: Optional[Dict[str, str]] = None) -> None:
        """Record a metric value."""
        point = MetricPoint(
            timestamp=time.time(),
            value=value,
            labels=labels or {},
        )
        with self._lock:
            if name not in self._metrics:
                self._metrics[name] = deque(maxlen=10000)
            self._metrics[name].append(point)

    def get_series(
        self,
        name: str,
        duration: float = 300.0,
        labels: Optional[Dict[str, str]] = None,
    ) -> List[dict]:
        """Get metric values for the last `duration` seconds."""
        cutoff = time.time() - duration
        with self._lock:
            points = self._metrics.get(name, deque())
            result = []
            for p in points:
                if p.timestamp < cutoff:
                    continue
                if labels:
                    if not all(p.labels.get(k) == v for k, v in labels.items()):
                        continue
                result.append({"timestamp": p.timestamp, "value": p.value})
            return result

    def get_latest(self, name: str) -> Optional[float]:
        """Get the most recent value for a metric."""
        with self._lock:
            points = self._metrics.get(name, deque())
            return points[-1].value if points else None

    def cleanup(self) -> None:
        """Remove expired metric points."""
        cutoff = time.time() - self._retention
        with self._lock:
            for name, points in self._metrics.items():
                while points and points[0].timestamp < cutoff:
                    points.popleft()


class QueueMonitor:
    """Monitors queue health and collects dashboard data."""

    def __init__(self, queue, poll_interval: float = 10.0):
        self._queue = queue
        self._poll_interval = poll_interval
        self._metrics = MetricsCollector()
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the monitoring loop in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info("Queue monitor started")

    def stop(self) -> None:
        """Stop the monitoring loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)

    def _monitor_loop(self) -> None:
        """Periodically collect metrics from the queue."""
        while self._running:
            try:
                self._collect_metrics()
                self._metrics.cleanup()
            except Exception as e:
                logger.error(f"Monitor error: {e}")
            time.sleep(self._poll_interval)

    def _collect_metrics(self) -> None:
        """Collect current queue metrics."""
        stats = self._queue.get_stats()
        self._metrics.record("queue.enqueued_total", stats["enqueued"])
        self._metrics.record("queue.completed_total", stats["completed"])
        self._metrics.record("queue.dead_total", stats["dead"])
        self._metrics.record("queue.retried_total", stats["retried"])

        # Queue depth (pending jobs)
        pending = stats["enqueued"] - stats["completed"] - stats["dead"]
        self._metrics.record("queue.depth", max(0, pending))

        # Throughput (completed per second since last check)
        self._metrics.record("queue.throughput", stats["completed"])

    def health_check(self) -> dict:
        """Perform a health check on the queue system."""
        checks = {
            "redis_connected": False,
            "queue_depth_ok": True,
            "dead_letter_ok": True,
            "worker_active": True,
        }

        try:
            self._queue._redis.ping()
            checks["redis_connected"] = True
        except Exception:
            checks["redis_connected"] = False

        stats = self._queue.get_stats()
        depth = stats["enqueued"] - stats["completed"] - stats["dead"]

        if depth > 10000:
            checks["queue_depth_ok"] = False

        if stats["dead"] > 100:
            checks["dead_letter_ok"] = False

        healthy = all(checks.values())
        return {
            "healthy": healthy,
            "checks": checks,
            "stats": stats,
            "timestamp": time.time(),
        }

    def get_dashboard_data(self) -> dict:
        """Get data for a monitoring dashboard."""
        health = self.health_check()
        return {
            "health": health,
            "metrics": {
                "depth": self._metrics.get_series("queue.depth", duration=600),
                "throughput": self._metrics.get_series("queue.throughput", duration=600),
                "enqueued": self._metrics.get_latest("queue.enqueued_total"),
                "completed": self._metrics.get_latest("queue.completed_total"),
                "dead": self._metrics.get_latest("queue.dead_total"),
            },
            "timestamp": time.time(),
        }
'''),
    ("projects/task-queue", r'''Create a task scheduler that supports cron-like scheduling for recurring jobs in the task queue.''', r'''import re
import time
import threading
import logging
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class CronField:
    """Represents a single field in a cron expression."""
    values: set  # Set of valid integer values

    @classmethod
    def parse(cls, expr: str, min_val: int, max_val: int) -> "CronField":
        """Parse a cron field expression into a set of values."""
        values = set()
        for part in expr.split(","):
            part = part.strip()
            if part == "*":
                values.update(range(min_val, max_val + 1))
            elif "/" in part:
                base, step = part.split("/")
                step = int(step)
                if base == "*":
                    start = min_val
                else:
                    start = int(base)
                values.update(range(start, max_val + 1, step))
            elif "-" in part:
                start, end = part.split("-")
                values.update(range(int(start), int(end) + 1))
            else:
                values.add(int(part))
        return cls(values=values)


@dataclass
class CronSchedule:
    """Parsed cron schedule."""
    minute: CronField
    hour: CronField
    day_of_month: CronField
    month: CronField
    day_of_week: CronField

    @classmethod
    def parse(cls, expression: str) -> "CronSchedule":
        """Parse a cron expression string."""
        # Support common shortcuts
        shortcuts = {
            "@yearly": "0 0 1 1 *",
            "@monthly": "0 0 1 * *",
            "@weekly": "0 0 * * 0",
            "@daily": "0 0 * * *",
            "@hourly": "0 * * * *",
        }
        expression = shortcuts.get(expression, expression)
        parts = expression.split()
        if len(parts) != 5:
            raise ValueError(f"Invalid cron expression: {expression}")

        return cls(
            minute=CronField.parse(parts[0], 0, 59),
            hour=CronField.parse(parts[1], 0, 23),
            day_of_month=CronField.parse(parts[2], 1, 31),
            month=CronField.parse(parts[3], 1, 12),
            day_of_week=CronField.parse(parts[4], 0, 6),
        )

    def matches(self, dt: datetime) -> bool:
        """Check if a datetime matches this schedule."""
        return (
            dt.minute in self.minute.values
            and dt.hour in self.hour.values
            and dt.day in self.day_of_month.values
            and dt.month in self.month.values
            and dt.weekday() in self.day_of_week.values  # Monday=0
        )

    def next_run(self, after: datetime) -> datetime:
        """Calculate the next run time after the given datetime."""
        candidate = after.replace(second=0, microsecond=0)
        # Advance by one minute to avoid matching current time
        from datetime import timedelta
        candidate += timedelta(minutes=1)

        # Brute force search (max ~525960 minutes in a year)
        for _ in range(525960):
            if self.matches(candidate):
                return candidate
            candidate += timedelta(minutes=1)

        raise ValueError("Could not find next run time within one year")


@dataclass
class ScheduledJob:
    """A recurring job with a cron schedule."""
    name: str
    task_name: str
    schedule: CronSchedule
    args: list = field(default_factory=list)
    kwargs: dict = field(default_factory=dict)
    enabled: bool = True
    last_run: Optional[float] = None
    next_run: Optional[float] = None


class TaskScheduler:
    """Cron-like scheduler for recurring task queue jobs."""

    def __init__(self, queue, check_interval: float = 30.0):
        self._queue = queue
        self._check_interval = check_interval
        self._jobs: Dict[str, ScheduledJob] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def add_job(
        self,
        name: str,
        task_name: str,
        cron_expression: str,
        args: Optional[list] = None,
        kwargs: Optional[dict] = None,
    ) -> ScheduledJob:
        """Add a recurring job with a cron schedule."""
        schedule = CronSchedule.parse(cron_expression)
        job = ScheduledJob(
            name=name,
            task_name=task_name,
            schedule=schedule,
            args=args or [],
            kwargs=kwargs or {},
            next_run=schedule.next_run(datetime.now()).timestamp(),
        )
        self._jobs[name] = job
        logger.info(f"Scheduled job '{name}' with cron '{cron_expression}'")
        return job

    def remove_job(self, name: str) -> bool:
        """Remove a scheduled job."""
        return self._jobs.pop(name, None) is not None

    def enable_job(self, name: str) -> None:
        job = self._jobs.get(name)
        if job:
            job.enabled = True

    def disable_job(self, name: str) -> None:
        job = self._jobs.get(name)
        if job:
            job.enabled = False

    def start(self) -> None:
        """Start the scheduler."""
        self._running = True
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("Task scheduler started")

    def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
        logger.info("Task scheduler stopped")

    def _run_loop(self) -> None:
        """Main scheduler loop."""
        while self._running:
            now = time.time()
            for job in self._jobs.values():
                if not job.enabled:
                    continue
                if job.next_run and now >= job.next_run:
                    self._execute_job(job)
                    next_dt = job.schedule.next_run(datetime.now())
                    job.next_run = next_dt.timestamp()
            time.sleep(self._check_interval)

    def _execute_job(self, job: ScheduledJob) -> None:
        """Enqueue a scheduled job for execution."""
        try:
            self._queue.enqueue(
                job.task_name,
                *job.args,
                **job.kwargs,
            )
            job.last_run = time.time()
            logger.info(f"Scheduled job '{job.name}' enqueued")
        except Exception as e:
            logger.error(f"Failed to enqueue scheduled job '{job.name}': {e}")

    def list_jobs(self) -> List[dict]:
        """List all scheduled jobs."""
        return [
            {
                "name": j.name,
                "task": j.task_name,
                "enabled": j.enabled,
                "last_run": j.last_run,
                "next_run": j.next_run,
            }
            for j in self._jobs.values()
        ]
'''),
]
