"""Monitoring and alerting — Prometheus, Grafana, SLOs, error budgets."""

PAIRS = [
    (
        "devops/prometheus-metrics",
        "Show Prometheus metrics: custom counters, histograms, metric types, and PromQL queries for alerting.",
        '''Prometheus metrics and alerting:

```python
from prometheus_client import Counter, Histogram, Gauge, Summary, Info
from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
import time
from functools import wraps

# Metric types
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "Request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

ACTIVE_CONNECTIONS = Gauge(
    "active_connections",
    "Currently active connections",
)

QUEUE_SIZE = Gauge("task_queue_size", "Pending tasks in queue")

APP_INFO = Info("app", "Application metadata")
APP_INFO.info({"version": "2.3.1", "environment": "production"})


def track_request(method: str, endpoint: str):
    """Decorator to track request metrics."""
    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            ACTIVE_CONNECTIONS.inc()
            start = time.perf_counter()
            try:
                result = await fn(*args, **kwargs)
                status = getattr(result, "status_code", 200)
                REQUEST_COUNT.labels(method, endpoint, status).inc()
                return result
            except Exception as e:
                REQUEST_COUNT.labels(method, endpoint, 500).inc()
                raise
            finally:
                duration = time.perf_counter() - start
                REQUEST_DURATION.labels(method, endpoint).observe(duration)
                ACTIVE_CONNECTIONS.dec()
        return wrapper
    return decorator
```

```yaml
# Prometheus alerting rules
groups:
  - name: api-alerts
    rules:
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m]))
          / sum(rate(http_requests_total[5m])) > 0.01
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Error rate above 1% for 5 minutes"

      - alert: HighLatency
        expr: |
          histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m]))
          by (le)) > 2.0
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "P99 latency above 2 seconds"

      - alert: SLOBreach
        expr: |
          1 - (sum(rate(http_requests_total{status!~"5.."}[30d]))
          / sum(rate(http_requests_total[30d]))) > 0.001
        labels:
          severity: critical
        annotations:
          summary: "30-day error budget exhausted (SLO: 99.9%)"
```

Key patterns:
1. **Counter** — monotonically increasing; use rate() for per-second rate
2. **Histogram** — distribution of values in buckets; use histogram_quantile for percentiles
3. **Gauge** — goes up and down; active connections, queue size, temperature
4. **Label cardinality** — keep label combinations bounded; high cardinality kills Prometheus
5. **SLO alerts** — error budget monitoring; alert when burning budget too fast'''
    ),
    (
        "devops/slo-management",
        "Show SLO (Service Level Objective) management: defining SLIs, error budgets, burn rate alerts, and SLO dashboards.",
        '''SLO and error budget management:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass
class SLO:
    name: str
    target: float           # e.g., 0.999 = 99.9%
    window_days: int = 30   # Rolling window
    sli_query: str = ""     # PromQL query for SLI


@dataclass
class SLOStatus:
    slo: SLO
    current_sli: float
    error_budget_total: float
    error_budget_remaining: float
    burn_rate_1h: float
    burn_rate_6h: float
    healthy: bool


class SLOManager:
    """Track and manage SLOs with error budgets."""

    def __init__(self):
        self.slos: list[SLO] = []

    def add_slo(self, slo: SLO):
        self.slos.append(slo)

    def calculate_error_budget(self, slo: SLO, current_sli: float) -> dict:
        """Calculate error budget consumption.

        Error budget = 1 - SLO target
        For 99.9% SLO over 30 days:
        - Total budget: 0.1% = 43.2 minutes of downtime
        - If current SLI is 99.85%: consumed 50% of budget
        """
        total_budget = 1 - slo.target  # 0.001 for 99.9%
        consumed = max(0, (1 - current_sli))  # How much error occurred
        remaining = max(0, total_budget - consumed)
        consumption_pct = consumed / total_budget if total_budget > 0 else 0

        window_minutes = slo.window_days * 24 * 60
        budget_minutes = total_budget * window_minutes
        remaining_minutes = remaining * window_minutes

        return {
            "total_budget_pct": total_budget * 100,
            "consumed_pct": consumption_pct * 100,
            "remaining_pct": (1 - consumption_pct) * 100,
            "budget_minutes": budget_minutes,
            "remaining_minutes": remaining_minutes,
            "healthy": consumption_pct < 1.0,
        }

    def burn_rate_alert_thresholds(self, slo: SLO) -> list[dict]:
        """Multi-window burn rate alerts (Google SRE book).

        Fast burn: detecting major outages quickly
        Slow burn: detecting gradual degradation
        """
        budget = 1 - slo.target

        return [
            # Fast burn: exhausts budget in 1 hour → alert in 2 minutes
            {"short_window": "5m", "long_window": "1h",
             "burn_rate": slo.window_days * 24,  # 720x for 30-day window
             "severity": "critical"},
            # Medium burn: exhausts budget in 6 hours → alert in 15 minutes
            {"short_window": "30m", "long_window": "6h",
             "burn_rate": slo.window_days * 4,  # 120x
             "severity": "critical"},
            # Slow burn: exhausts budget in 3 days → alert in 1 hour
            {"short_window": "2h", "long_window": "1d",
             "burn_rate": slo.window_days / 3,  # 10x
             "severity": "warning"},
            # Very slow burn: exhausts budget in 10 days → alert in 3 hours
            {"short_window": "6h", "long_window": "3d",
             "burn_rate": slo.window_days / 10,  # 3x
             "severity": "warning"},
        ]


# Define standard SLOs
availability_slo = SLO(
    name="API Availability",
    target=0.999,  # 99.9%
    window_days=30,
    sli_query='sum(rate(http_requests_total{status!~"5.."}[5m])) / sum(rate(http_requests_total[5m]))',
)

latency_slo = SLO(
    name="API Latency",
    target=0.99,  # 99% of requests under 500ms
    window_days=30,
    sli_query='sum(rate(http_request_duration_seconds_bucket{le="0.5"}[5m])) / sum(rate(http_request_duration_seconds_count[5m]))',
)
```

Key patterns:
1. **Error budget** — allowed unreliability; 99.9% SLO = 43.2 min/month error budget
2. **Burn rate** — how fast budget is being consumed; fast burn = major outage
3. **Multi-window alerts** — short window (detection speed) + long window (avoid false positives)
4. **SLI queries** — specific PromQL measuring the indicator; availability, latency, etc.
5. **Budget-based decisions** — if budget exhausted, freeze deploys; if plenty, ship faster'''
    ),
]
