"""Observability — structured logging, metrics, SLOs, and incident response."""

PAIRS = [
    (
        "devops/prometheus-metrics",
        "Show Prometheus metrics patterns: counters, histograms, gauges, and custom metrics in Python.",
        '''Prometheus metrics patterns:

```python
from prometheus_client import (
    Counter, Histogram, Gauge, Summary, Info,
    generate_latest, CONTENT_TYPE_LATEST,
    CollectorRegistry, start_http_server,
)
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import time
import psutil


# --- Define metrics ---

# Counter: monotonically increasing (requests, errors)
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status_code"],
)

# Histogram: distribution (latency, request size)
REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

# Gauge: current value that goes up/down (connections, queue size)
ACTIVE_REQUESTS = Gauge(
    "http_active_requests",
    "Currently active HTTP requests",
)

IN_PROGRESS_TASKS = Gauge(
    "background_tasks_in_progress",
    "Number of background tasks currently running",
    ["task_type"],
)

# Summary: similar to histogram but calculates quantiles client-side
DB_QUERY_DURATION = Summary(
    "db_query_duration_seconds",
    "Database query duration",
    ["query_type"],
)

# Info: static labels (version, build info)
APP_INFO = Info("app", "Application info")
APP_INFO.info({
    "version": "2.1.0",
    "python_version": "3.12",
    "environment": "production",
})


# --- Custom business metrics ---

ORDERS_TOTAL = Counter(
    "orders_total",
    "Total orders placed",
    ["payment_method", "status"],
)

ORDER_VALUE = Histogram(
    "order_value_dollars",
    "Order value in dollars",
    buckets=[10, 25, 50, 100, 250, 500, 1000, 5000],
)

CACHE_HITS = Counter("cache_hits_total", "Cache hit count", ["cache_name"])
CACHE_MISSES = Counter("cache_misses_total", "Cache miss count", ["cache_name"])

QUEUE_SIZE = Gauge("task_queue_size", "Current task queue depth", ["queue_name"])


# --- Middleware for automatic HTTP metrics ---

app = FastAPI()

class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method
        path = request.url.path

        # Normalize path (avoid cardinality explosion)
        # /api/users/123 -> /api/users/{id}
        normalized = self._normalize_path(path)

        ACTIVE_REQUESTS.inc()
        start = time.monotonic()

        try:
            response = await call_next(request)
            status = str(response.status_code)
        except Exception:
            status = "500"
            raise
        finally:
            duration = time.monotonic() - start
            ACTIVE_REQUESTS.dec()

            REQUEST_COUNT.labels(
                method=method,
                endpoint=normalized,
                status_code=status,
            ).inc()

            REQUEST_LATENCY.labels(
                method=method,
                endpoint=normalized,
            ).observe(duration)

        return response

    @staticmethod
    def _normalize_path(path: str) -> str:
        parts = path.split("/")
        normalized = []
        for part in parts:
            # Replace UUIDs and numeric IDs with placeholder
            if part.isdigit() or len(part) == 36 and "-" in part:
                normalized.append("{id}")
            else:
                normalized.append(part)
        return "/".join(normalized)

app.add_middleware(MetricsMiddleware)


# --- Metrics endpoint ---

@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


# --- System metrics collector ---

SYSTEM_CPU = Gauge("system_cpu_percent", "System CPU usage percent")
SYSTEM_MEMORY = Gauge("system_memory_percent", "System memory usage percent")
SYSTEM_DISK = Gauge("system_disk_percent", "System disk usage percent")

async def collect_system_metrics():
    """Periodically collect system metrics."""
    while True:
        SYSTEM_CPU.set(psutil.cpu_percent())
        SYSTEM_MEMORY.set(psutil.virtual_memory().percent)
        SYSTEM_DISK.set(psutil.disk_usage("/").percent)
        await asyncio.sleep(15)


# --- Usage in application code ---

async def process_order(order):
    with REQUEST_LATENCY.labels(method="internal", endpoint="process_order").time():
        # ... process order ...
        ORDERS_TOTAL.labels(
            payment_method=order.payment_method,
            status="success",
        ).inc()
        ORDER_VALUE.observe(order.total)
```

Prometheus metrics patterns:
1. **Counter** — monotonic increase: requests, errors, orders (use `labels` for dimensions)
2. **Histogram** — latency distribution with configurable buckets for p50/p95/p99
3. **Gauge** — current value: active connections, queue depth, CPU usage
4. **Path normalization** — replace IDs with `{id}` to prevent label cardinality explosion
5. **`.time()` context manager** — automatically observe duration of code blocks'''
    ),
    (
        "devops/slo-error-budget",
        "Show SLO and error budget patterns: defining SLIs, calculating error budgets, and alerting on burn rate.",
        '''SLO and error budget patterns:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal


# --- SLI/SLO definitions ---

@dataclass
class SLI:
    """Service Level Indicator — what we measure."""
    name: str
    description: str
    metric_type: Literal["availability", "latency", "throughput", "error_rate"]
    query: str  # PromQL query


@dataclass
class SLO:
    """Service Level Objective — target for the SLI."""
    sli: SLI
    target: float          # e.g., 0.999 (99.9%)
    window: timedelta      # e.g., 30 days
    description: str = ""

    @property
    def error_budget(self) -> float:
        """Allowed error rate = 1 - target."""
        return 1 - self.target

    @property
    def error_budget_minutes(self) -> float:
        """Error budget in minutes per window."""
        return self.window.total_seconds() / 60 * self.error_budget


# --- Define SLOs ---

availability_sli = SLI(
    name="api_availability",
    description="Proportion of successful HTTP requests",
    metric_type="availability",
    query='sum(rate(http_requests_total{status_code!~"5.."}[5m])) / sum(rate(http_requests_total[5m]))',
)

latency_sli = SLI(
    name="api_latency_p99",
    description="99th percentile request latency",
    metric_type="latency",
    query='histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le))',
)

SLOS = [
    SLO(
        sli=availability_sli,
        target=0.999,            # 99.9% availability
        window=timedelta(days=30),
        description="99.9% of requests succeed over 30 days",
        # Error budget: 0.1% = 43.2 minutes/month
    ),
    SLO(
        sli=latency_sli,
        target=0.99,             # 99% of requests under 500ms
        window=timedelta(days=30),
        description="p99 latency under 500ms",
    ),
]


# --- Error budget calculator ---

@dataclass
class ErrorBudgetStatus:
    slo_name: str
    target: float
    current: float
    budget_total: float
    budget_consumed: float
    budget_remaining: float
    budget_remaining_percent: float
    is_healthy: bool
    burn_rate: float  # Current consumption rate

def calculate_error_budget(
    slo: SLO,
    current_value: float,
    window_elapsed: timedelta,
) -> ErrorBudgetStatus:
    """Calculate error budget consumption."""
    budget_total = slo.error_budget
    actual_error_rate = 1 - current_value

    # How much budget has been consumed
    budget_consumed = actual_error_rate
    budget_remaining = max(0, budget_total - budget_consumed)
    budget_remaining_pct = (budget_remaining / budget_total * 100) if budget_total > 0 else 0

    # Burn rate: how fast we're consuming budget
    # burn_rate = 1.0 means consuming at exactly the allowed rate
    # burn_rate = 2.0 means consuming at 2x the allowed rate (will exhaust in half the window)
    window_fraction = window_elapsed / slo.window
    if window_fraction > 0 and budget_total > 0:
        expected_consumption = budget_total * window_fraction
        burn_rate = budget_consumed / expected_consumption if expected_consumption > 0 else 0
    else:
        burn_rate = 0

    return ErrorBudgetStatus(
        slo_name=slo.sli.name,
        target=slo.target,
        current=current_value,
        budget_total=budget_total,
        budget_consumed=budget_consumed,
        budget_remaining=budget_remaining,
        budget_remaining_percent=round(budget_remaining_pct, 2),
        is_healthy=budget_remaining > 0,
        burn_rate=round(burn_rate, 2),
    )


# --- Prometheus alerting rules for SLOs ---

ALERT_RULES = """
# Burn rate alerting (Google SRE approach)
# Alert when error budget is being consumed too fast

groups:
  - name: slo-alerts
    rules:
      # Critical: 14.4x burn rate over 1 hour (exhausts budget in ~2 days)
      - alert: HighErrorBudgetBurn
        expr: |
          (
            1 - (
              sum(rate(http_requests_total{status_code!~"5.."}[1h]))
              / sum(rate(http_requests_total[1h]))
            )
          ) > (14.4 * 0.001)
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error budget burn rate"
          description: "Error budget burning at {{ $value | humanizePercentage }}/hr"

      # Warning: 6x burn rate over 6 hours (exhausts budget in ~5 days)
      - alert: ElevatedErrorBudgetBurn
        expr: |
          (
            1 - (
              sum(rate(http_requests_total{status_code!~"5.."}[6h]))
              / sum(rate(http_requests_total[6h]))
            )
          ) > (6 * 0.001)
        for: 15m
        labels:
          severity: warning

      # P99 latency SLO
      - alert: HighLatencyBurn
        expr: |
          histogram_quantile(0.99,
            sum(rate(http_request_duration_seconds_bucket[1h])) by (le)
          ) > 0.5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "P99 latency exceeds 500ms SLO"
"""

# Error budget for 99.9% availability over 30 days:
# Total budget: 0.1% = 43.2 minutes of downtime
# Burn rate 1.0x: consuming exactly at allowed rate
# Burn rate 2.0x: will exhaust budget in 15 days
# Burn rate 14.4x: will exhaust budget in ~2 days (critical alert)
```

SLO/Error budget patterns:
1. **SLI → SLO → Error budget** — measure, set target, calculate allowed failures
2. **Error budget = 1 - target** — 99.9% SLO gives 0.1% = 43 min/month budget
3. **Burn rate alerting** — alert on consumption rate, not raw error rate
4. **Multi-window** — 1h (fast detection) + 6h (sustained issues) burn rate alerts
5. **Budget remaining %** — decision input for deploy velocity vs stability tradeoffs'''
    ),
    (
        "devops/incident-response",
        "Show incident response patterns: runbook automation, status pages, and post-incident review templates.",
        '''Incident response patterns:

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum, auto
from typing import Any
import json
import logging

logger = logging.getLogger(__name__)


# --- Incident model ---

class Severity(StrEnum):
    SEV1 = auto()  # Critical: service down, data loss
    SEV2 = auto()  # Major: significant degradation
    SEV3 = auto()  # Minor: partial impact, workaround available
    SEV4 = auto()  # Low: cosmetic, minimal impact

class IncidentStatus(StrEnum):
    DETECTED = auto()
    INVESTIGATING = auto()
    IDENTIFIED = auto()
    MITIGATING = auto()
    RESOLVED = auto()
    POST_MORTEM = auto()


@dataclass
class IncidentUpdate:
    timestamp: datetime
    status: IncidentStatus
    message: str
    author: str


@dataclass
class Incident:
    id: str
    title: str
    severity: Severity
    status: IncidentStatus = IncidentStatus.DETECTED
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: datetime | None = None
    commander: str = ""
    affected_services: list[str] = field(default_factory=list)
    updates: list[IncidentUpdate] = field(default_factory=list)
    action_items: list[dict] = field(default_factory=list)

    def add_update(self, status: IncidentStatus, message: str, author: str):
        self.status = status
        self.updates.append(IncidentUpdate(
            timestamp=datetime.now(timezone.utc),
            status=status,
            message=message,
            author=author,
        ))
        if status == IncidentStatus.RESOLVED:
            self.resolved_at = datetime.now(timezone.utc)

    @property
    def duration_minutes(self) -> float | None:
        if self.resolved_at:
            return (self.resolved_at - self.created_at).total_seconds() / 60
        return None

    @property
    def time_to_detect(self) -> float | None:
        for update in self.updates:
            if update.status == IncidentStatus.INVESTIGATING:
                return (update.timestamp - self.created_at).total_seconds() / 60
        return None

    @property
    def time_to_mitigate(self) -> float | None:
        for update in self.updates:
            if update.status == IncidentStatus.MITIGATING:
                return (update.timestamp - self.created_at).total_seconds() / 60
        return None


# --- Automated runbook checks ---

class RunbookStep:
    def __init__(self, name: str, check_fn, fix_fn=None):
        self.name = name
        self.check_fn = check_fn
        self.fix_fn = fix_fn


class AutomatedRunbook:
    """Automated diagnostic and remediation steps."""

    def __init__(self, name: str):
        self.name = name
        self.steps: list[RunbookStep] = []

    def add_check(self, name: str, check_fn, fix_fn=None):
        self.steps.append(RunbookStep(name, check_fn, fix_fn))
        return self

    async def execute(self) -> list[dict]:
        results = []
        for step in self.steps:
            logger.info("Runbook check: %s", step.name)
            try:
                check_result = await step.check_fn()
                status = "pass" if check_result else "fail"

                if not check_result and step.fix_fn:
                    logger.warning("Auto-fixing: %s", step.name)
                    await step.fix_fn()
                    status = "auto_fixed"

            except Exception as e:
                status = "error"
                check_result = str(e)

            results.append({
                "step": step.name,
                "status": status,
                "details": check_result,
            })

        return results


# --- Example runbook for API service ---

async def check_database_connection():
    try:
        await db.execute("SELECT 1")
        return True
    except Exception:
        return False

async def check_redis_connection():
    try:
        await redis.ping()
        return True
    except Exception:
        return False

async def check_disk_space():
    import shutil
    usage = shutil.disk_usage("/")
    free_percent = usage.free / usage.total * 100
    return free_percent > 10  # At least 10% free

async def check_memory():
    import psutil
    return psutil.virtual_memory().percent < 90

async def restart_workers():
    import subprocess
    subprocess.run(["systemctl", "restart", "myapp-worker"])

api_runbook = (
    AutomatedRunbook("api-health")
    .add_check("Database connectivity", check_database_connection)
    .add_check("Redis connectivity", check_redis_connection)
    .add_check("Disk space > 10%", check_disk_space)
    .add_check("Memory < 90%", check_memory)
    .add_check("Worker health", check_redis_connection, fix_fn=restart_workers)
)


# --- Post-incident review template ---

POST_MORTEM_TEMPLATE = """
# Incident Post-Mortem: {title}

## Summary
- **Incident ID**: {incident_id}
- **Severity**: {severity}
- **Duration**: {duration_minutes:.0f} minutes
- **Time to Detect**: {ttd:.0f} minutes
- **Time to Mitigate**: {ttm:.0f} minutes
- **Affected Services**: {services}
- **Impact**: [Number of users affected, revenue impact, etc.]

## Timeline
{timeline}

## Root Cause
[Describe the underlying technical cause]

## Detection
[How was the incident detected? Automated alert or user report?]

## Resolution
[What steps were taken to resolve the incident?]

## Lessons Learned
### What went well
- [e.g., Alert fired within 2 minutes]

### What went poorly
- [e.g., Runbook was outdated]

### Where we got lucky
- [e.g., Happened during low-traffic period]

## Action Items
| Action | Owner | Priority | Due Date |
|--------|-------|----------|----------|
{action_items}

## Preventive Measures
[What changes will prevent this class of incident in the future?]
"""
```

Incident response patterns:
1. **Severity levels** — SEV1 (service down) to SEV4 (cosmetic) with escalation rules
2. **Status progression** — detected → investigating → identified → mitigating → resolved
3. **Automated runbook** — sequential diagnostic checks with optional auto-remediation
4. **Key metrics** — TTD (time to detect), TTM (time to mitigate), total duration
5. **Post-mortem template** — blameless review with timeline, root cause, and action items'''
    ),
]
"""
