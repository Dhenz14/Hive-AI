"""
Batch p1068: Multi-step project building - Application Monitoring System
Topics: health checks, metric collection, alerting rules, dashboard data, SLO tracking
"""

PAIRS = [
    ("projects/monitoring_health_checks", r'''Build a production health check system in Python that supports liveness, readiness, and custom component checks with configurable timeouts and dependencies.''', r'''import time
import threading
import logging
from enum import Enum
from typing import Callable, Dict, Optional, List
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)


class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class CheckResult:
    name: str
    status: HealthStatus
    message: str = ""
    duration_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict = field(default_factory=dict)


@dataclass
class HealthCheck:
    name: str
    check_fn: Callable[[], CheckResult]
    timeout_seconds: float = 5.0
    critical: bool = False
    dependencies: List[str] = field(default_factory=list)
    interval_seconds: float = 30.0
    last_result: Optional[CheckResult] = None


class HealthCheckRegistry:
    """Central registry for all application health checks."""

    def __init__(self, max_workers: int = 10):
        self._checks: Dict[str, HealthCheck] = {}
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        self._background_thread: Optional[threading.Thread] = None
        self._running = False

    def register(self, name: str, check_fn: Callable, timeout: float = 5.0,
                 critical: bool = False, dependencies: List[str] = None,
                 interval: float = 30.0):
        """Register a new health check."""
        with self._lock:
            self._checks[name] = HealthCheck(
                name=name,
                check_fn=check_fn,
                timeout_seconds=timeout,
                critical=critical,
                dependencies=dependencies or [],
                interval_seconds=interval,
            )
        logger.info("Registered health check: %s (critical=%s)", name, critical)

    def _run_single_check(self, check: HealthCheck) -> CheckResult:
        start = time.monotonic()
        try:
            future = self._executor.submit(check.check_fn)
            result = future.result(timeout=check.timeout_seconds)
            result.duration_ms = (time.monotonic() - start) * 1000
            return result
        except TimeoutError:
            return CheckResult(
                name=check.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check timed out after {check.timeout_seconds}s",
                duration_ms=(time.monotonic() - start) * 1000,
            )
        except Exception as exc:
            return CheckResult(
                name=check.name,
                status=HealthStatus.UNHEALTHY,
                message=f"Check failed: {exc}",
                duration_ms=(time.monotonic() - start) * 1000,
            )

    def _resolve_order(self) -> List[str]:
        """Topological sort of checks based on dependencies."""
        visited = set()
        order = []

        def visit(name):
            if name in visited:
                return
            visited.add(name)
            check = self._checks.get(name)
            if check:
                for dep in check.dependencies:
                    visit(dep)
            order.append(name)

        for name in self._checks:
            visit(name)
        return order

    def run_all(self) -> Dict[str, CheckResult]:
        """Run all registered checks respecting dependency order."""
        results = {}
        order = self._resolve_order()

        for name in order:
            check = self._checks.get(name)
            if not check:
                continue
            deps_healthy = all(
                results.get(d, CheckResult(d, HealthStatus.UNHEALTHY)).status
                == HealthStatus.HEALTHY
                for d in check.dependencies
            )
            if not deps_healthy:
                results[name] = CheckResult(
                    name=name,
                    status=HealthStatus.UNHEALTHY,
                    message="Dependency check failed",
                )
            else:
                result = self._run_single_check(check)
                results[name] = result
            check.last_result = results[name]

        return results

    def liveness(self) -> CheckResult:
        """Basic liveness probe - is the process alive."""
        return CheckResult(name="liveness", status=HealthStatus.HEALTHY, message="ok")

    def readiness(self) -> Dict:
        """Readiness probe - are all critical checks passing."""
        results = self.run_all()
        critical_checks = {
            n: r for n, r in results.items() if self._checks[n].critical
        }
        all_ready = all(
            r.status == HealthStatus.HEALTHY for r in critical_checks.values()
        )
        overall = HealthStatus.HEALTHY if all_ready else HealthStatus.UNHEALTHY
        return {
            "status": overall.value,
            "checks": {n: r.status.value for n, r in results.items()},
        }

    def start_background(self):
        """Start background check loop."""
        self._running = True
        self._background_thread = threading.Thread(target=self._loop, daemon=True)
        self._background_thread.start()

    def _loop(self):
        while self._running:
            self.run_all()
            time.sleep(min(
                (c.interval_seconds for c in self._checks.values()), default=30
            ))

    def stop(self):
        self._running = False


def database_check(dsn: str) -> Callable:
    """Factory for database health checks."""
    def check():
        try:
            import sqlite3
            conn = sqlite3.connect(dsn, timeout=3)
            conn.execute("SELECT 1")
            conn.close()
            return CheckResult(name="database", status=HealthStatus.HEALTHY, message="connected")
        except Exception as exc:
            return CheckResult(name="database", status=HealthStatus.UNHEALTHY, message=str(exc))
    return check


def disk_space_check(path: str = "/", min_free_gb: float = 1.0) -> Callable:
    """Factory for disk space health checks."""
    def check():
        import shutil
        usage = shutil.disk_usage(path)
        free_gb = usage.free / (1024 ** 3)
        status = HealthStatus.HEALTHY if free_gb >= min_free_gb else HealthStatus.DEGRADED
        return CheckResult(
            name="disk_space", status=status,
            message=f"{free_gb:.1f}GB free",
            metadata={"free_gb": free_gb, "total_gb": usage.total / (1024 ** 3)},
        )
    return check
'''),

    ("projects/monitoring_metrics", r'''<think>
The user needs a metric collection system. My first instinct is to wrap the Prometheus client library... but wait, building from scratch teaches more and avoids a heavy dependency. So I should build something that supports counters, gauges, histograms, and summaries - similar to Prometheus client concepts but implemented fresh.

I considered including summaries too, but actually summaries require streaming quantile estimation (like t-digest or ck-digest), which adds significant complexity. Histograms with configurable buckets are more practical for a from-scratch implementation since you can derive percentiles from bucket boundaries. So I will skip summaries for now.

Thread safety is a concern - could be that a simple global lock is enough... hmm, but that would serialize all metric updates across all types. Since counters, gauges, and histograms are independent, each metric instance should have its own lock. Therefore per-metric locking gives better concurrency.

Key components:
- Counter: monotonically increasing value
- Gauge: value that can go up and down
- Histogram: distribution of values in buckets
- Registry to hold all metrics
- Export in Prometheus text format
</think>

Build a metrics collection library in Python supporting counters, gauges, and histograms with labels, thread-safe operations, and Prometheus-compatible text export.''', r'''<think>
I need thread-safe metric types with label support. Each metric family has a name and optional labels. I considered using a single lock on the registry for simplicity, but wait - that would mean incrementing one counter blocks reading another gauge entirely. Per-metric locks are better because they allow concurrent updates to different metrics.

For the label system, I could store children in a dict keyed by label name-value pairs... actually, tuples of label values (positional) are cleaner since the label names are fixed at metric creation time. This avoids repeated string key lookups.

The histogram needs configurable buckets. I initially thought about auto-generating log-scale buckets, but the Prometheus convention uses explicit bucket boundaries, and that is simpler to reason about. Therefore I will take explicit buckets and always append +Inf as the final boundary.
</think>

import time
import threading
import math
from typing import Dict, List, Tuple, Optional, Sequence
from collections import defaultdict


class MetricFamily:
    """Base class for metric families with label support."""

    def __init__(self, name: str, help_text: str = "", label_names: Tuple[str, ...] = ()):
        self.name = name
        self.help_text = help_text
        self.label_names = label_names
        self._lock = threading.Lock()
        self._children: Dict[Tuple[str, ...], object] = {}

    def labels(self, *label_values, **label_kwargs):
        if label_kwargs:
            label_values = tuple(label_kwargs.get(n, "") for n in self.label_names)
        with self._lock:
            if label_values not in self._children:
                self._children[label_values] = self._new_child()
            return self._children[label_values]

    def _new_child(self):
        raise NotImplementedError

    def collect(self) -> List[Dict]:
        raise NotImplementedError


class _CounterChild:
    def __init__(self):
        self._value = 0.0
        self._lock = threading.Lock()
        self._created = time.time()

    def inc(self, amount: float = 1.0):
        if amount < 0:
            raise ValueError("Counter can only increase")
        with self._lock:
            self._value += amount

    @property
    def value(self) -> float:
        return self._value


class Counter(MetricFamily):
    def _new_child(self):
        return _CounterChild()

    def inc(self, amount: float = 1.0):
        """Increment the no-label counter."""
        self.labels().inc(amount)

    @property
    def value(self) -> float:
        return self.labels().value

    def collect(self) -> str:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} counter"]
        with self._lock:
            for label_vals, child in self._children.items():
                label_str = self._format_labels(label_vals)
                lines.append(f"{self.name}_total{label_str} {child.value}")
        return "\n".join(lines)

    def _format_labels(self, vals: Tuple[str, ...]) -> str:
        if not self.label_names or not any(vals):
            return ""
        pairs = [f'{n}="{v}"' for n, v in zip(self.label_names, vals)]
        return "{" + ",".join(pairs) + "}"


class _GaugeChild:
    def __init__(self):
        self._value = 0.0
        self._lock = threading.Lock()

    def set(self, value: float):
        with self._lock:
            self._value = value

    def inc(self, amount: float = 1.0):
        with self._lock:
            self._value += amount

    def dec(self, amount: float = 1.0):
        with self._lock:
            self._value -= amount

    @property
    def value(self) -> float:
        return self._value


class Gauge(MetricFamily):
    def _new_child(self):
        return _GaugeChild()

    def set(self, value: float):
        self.labels().set(value)

    def inc(self, amount: float = 1.0):
        self.labels().inc(amount)

    def dec(self, amount: float = 1.0):
        self.labels().dec(amount)

    @property
    def value(self) -> float:
        return self.labels().value

    def collect(self) -> str:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} gauge"]
        with self._lock:
            for label_vals, child in self._children.items():
                label_str = self._format_labels(label_vals)
                lines.append(f"{self.name}{label_str} {child.value}")
        return "\n".join(lines)

    def _format_labels(self, vals):
        if not self.label_names or not any(vals):
            return ""
        pairs = [f'{n}="{v}"' for n, v in zip(self.label_names, vals)]
        return "{" + ",".join(pairs) + "}"


DEFAULT_BUCKETS = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)


class _HistogramChild:
    def __init__(self, buckets: Sequence[float]):
        self._upper_bounds = sorted(buckets) + [float("inf")]
        self._buckets = [0] * len(self._upper_bounds)
        self._sum = 0.0
        self._count = 0
        self._lock = threading.Lock()

    def observe(self, value: float):
        with self._lock:
            self._sum += value
            self._count += 1
            for i, bound in enumerate(self._upper_bounds):
                if value <= bound:
                    self._buckets[i] += 1


class Histogram(MetricFamily):
    def __init__(self, name, help_text="", label_names=(), buckets=DEFAULT_BUCKETS):
        super().__init__(name, help_text, label_names)
        self._buckets_def = buckets

    def _new_child(self):
        return _HistogramChild(self._buckets_def)

    def observe(self, value: float):
        self.labels().observe(value)

    def time(self):
        """Context manager to time a block."""
        return _Timer(self)

    def collect(self) -> str:
        lines = [f"# HELP {self.name} {self.help_text}", f"# TYPE {self.name} histogram"]
        with self._lock:
            for label_vals, child in self._children.items():
                label_str = self._format_labels(label_vals)
                cumulative = 0
                for i, bound in enumerate(child._upper_bounds):
                    cumulative += child._buckets[i]
                    le = "+Inf" if math.isinf(bound) else str(bound)
                    lbl = self._merge_labels(label_vals, "le", le)
                    lines.append(f"{self.name}_bucket{lbl} {cumulative}")
                lines.append(f"{self.name}_sum{label_str} {child._sum}")
                lines.append(f"{self.name}_count{label_str} {child._count}")
        return "\n".join(lines)

    def _format_labels(self, vals):
        if not self.label_names or not any(vals):
            return ""
        pairs = [f'{n}="{v}"' for n, v in zip(self.label_names, vals)]
        return "{" + ",".join(pairs) + "}"

    def _merge_labels(self, vals, extra_name, extra_val):
        pairs = [f'{n}="{v}"' for n, v in zip(self.label_names, vals) if v]
        pairs.append(f'{extra_name}="{extra_val}"')
        return "{" + ",".join(pairs) + "}"


class _Timer:
    def __init__(self, histogram):
        self._histogram = histogram

    def __enter__(self):
        self._start = time.monotonic()
        return self

    def __exit__(self, *args):
        self._histogram.observe(time.monotonic() - self._start)


class MetricRegistry:
    """Global registry for all metrics with export support."""

    def __init__(self):
        self._metrics: Dict[str, MetricFamily] = {}
        self._lock = threading.Lock()

    def counter(self, name, help_text="", label_names=()) -> Counter:
        return self._register(Counter(name, help_text, label_names))

    def gauge(self, name, help_text="", label_names=()) -> Gauge:
        return self._register(Gauge(name, help_text, label_names))

    def histogram(self, name, help_text="", label_names=(), buckets=DEFAULT_BUCKETS) -> Histogram:
        return self._register(Histogram(name, help_text, label_names, buckets))

    def _register(self, metric):
        with self._lock:
            if metric.name in self._metrics:
                return self._metrics[metric.name]
            self._metrics[metric.name] = metric
        return metric

    def collect_all(self) -> str:
        """Export all metrics in Prometheus text format."""
        sections = []
        with self._lock:
            metrics = list(self._metrics.values())
        for m in metrics:
            sections.append(m.collect())
        return "\n\n".join(sections) + "\n"


GLOBAL_REGISTRY = MetricRegistry()
'''),

    ("projects/monitoring_alerting", r'''Build an alerting rules engine in Python that evaluates metric thresholds, supports configurable severity levels, cooldown periods, and notification routing with escalation policies.''', r'''import time
import logging
import threading
from enum import Enum
from typing import Callable, Dict, List, Optional, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class Severity(Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"
    PAGE = "page"


class AlertState(Enum):
    OK = "ok"
    PENDING = "pending"
    FIRING = "firing"
    RESOLVED = "resolved"


@dataclass
class Alert:
    rule_name: str
    severity: Severity
    state: AlertState
    message: str
    value: float
    threshold: float
    fired_at: float = 0.0
    resolved_at: float = 0.0
    notified_at: float = 0.0
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)


@dataclass
class AlertRule:
    name: str
    metric_fn: Callable[[], float]
    threshold: float
    comparison: str  # "gt", "lt", "gte", "lte", "eq"
    severity: Severity = Severity.WARNING
    for_seconds: float = 0.0
    cooldown_seconds: float = 300.0
    message_template: str = "{name}: {value} {comparison} {threshold}"
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    notification_channels: List[str] = field(default_factory=lambda: ["default"])


COMPARISONS = {
    "gt": lambda v, t: v > t,
    "lt": lambda v, t: v < t,
    "gte": lambda v, t: v >= t,
    "lte": lambda v, t: v <= t,
    "eq": lambda v, t: v == t,
}


@dataclass
class EscalationPolicy:
    name: str
    levels: List[Dict[str, Any]] = field(default_factory=list)

    def add_level(self, wait_minutes: float, channels: List[str]):
        self.levels.append({"wait_minutes": wait_minutes, "channels": channels})
        return self


class NotificationChannel:
    """Base notification channel."""

    def __init__(self, name: str):
        self.name = name

    def send(self, alert: Alert) -> bool:
        raise NotImplementedError


class LogChannel(NotificationChannel):
    def send(self, alert: Alert) -> bool:
        logger.warning("[ALERT-%s] %s: %s", alert.severity.value.upper(),
                       alert.rule_name, alert.message)
        return True


class WebhookChannel(NotificationChannel):
    def __init__(self, name: str, url: str, headers: Dict[str, str] = None):
        super().__init__(name)
        self.url = url
        self.headers = headers or {}

    def send(self, alert: Alert) -> bool:
        import json
        import urllib.request
        payload = json.dumps({
            "rule": alert.rule_name,
            "severity": alert.severity.value,
            "state": alert.state.value,
            "message": alert.message,
            "value": alert.value,
            "threshold": alert.threshold,
            "labels": alert.labels,
        }).encode()
        req = urllib.request.Request(self.url, data=payload, headers={
            "Content-Type": "application/json", **self.headers,
        })
        try:
            urllib.request.urlopen(req, timeout=10)
            return True
        except Exception as exc:
            logger.error("Webhook send failed: %s", exc)
            return False


class AlertEngine:
    """Evaluates alert rules against live metrics."""

    def __init__(self):
        self._rules: Dict[str, AlertRule] = {}
        self._states: Dict[str, AlertState] = {}
        self._pending_since: Dict[str, float] = {}
        self._last_notification: Dict[str, float] = {}
        self._channels: Dict[str, NotificationChannel] = {}
        self._escalation_policies: Dict[str, EscalationPolicy] = {}
        self._alert_history: List[Alert] = []
        self._lock = threading.Lock()

    def add_channel(self, channel: NotificationChannel):
        self._channels[channel.name] = channel

    def add_escalation_policy(self, policy: EscalationPolicy):
        self._escalation_policies[policy.name] = policy

    def add_rule(self, rule: AlertRule):
        with self._lock:
            self._rules[rule.name] = rule
            self._states[rule.name] = AlertState.OK

    def evaluate_all(self) -> List[Alert]:
        """Evaluate all rules and return any alerts that fired or resolved."""
        alerts = []
        now = time.time()

        with self._lock:
            for name, rule in self._rules.items():
                try:
                    value = rule.metric_fn()
                except Exception as exc:
                    logger.error("Failed to evaluate metric for %s: %s", name, exc)
                    continue

                compare_fn = COMPARISONS.get(rule.comparison)
                if not compare_fn:
                    continue

                threshold_breached = compare_fn(value, rule.threshold)
                current_state = self._states[name]

                if threshold_breached:
                    if current_state == AlertState.OK:
                        if rule.for_seconds > 0:
                            self._states[name] = AlertState.PENDING
                            self._pending_since[name] = now
                        else:
                            self._states[name] = AlertState.FIRING
                            alert = self._create_alert(rule, value, AlertState.FIRING, now)
                            self._notify(alert, rule)
                            alerts.append(alert)
                    elif current_state == AlertState.PENDING:
                        pending_duration = now - self._pending_since.get(name, now)
                        if pending_duration >= rule.for_seconds:
                            self._states[name] = AlertState.FIRING
                            alert = self._create_alert(rule, value, AlertState.FIRING, now)
                            self._notify(alert, rule)
                            alerts.append(alert)
                    elif current_state == AlertState.FIRING:
                        last_notified = self._last_notification.get(name, 0)
                        if now - last_notified >= rule.cooldown_seconds:
                            alert = self._create_alert(rule, value, AlertState.FIRING, now)
                            self._notify(alert, rule)
                            alerts.append(alert)
                else:
                    if current_state in (AlertState.FIRING, AlertState.PENDING):
                        self._states[name] = AlertState.RESOLVED
                        alert = self._create_alert(rule, value, AlertState.RESOLVED, now)
                        alert.resolved_at = now
                        self._notify(alert, rule)
                        alerts.append(alert)
                        self._states[name] = AlertState.OK

        return alerts

    def _create_alert(self, rule: AlertRule, value: float, state: AlertState,
                      now: float) -> Alert:
        message = rule.message_template.format(
            name=rule.name, value=value,
            comparison=rule.comparison, threshold=rule.threshold,
        )
        alert = Alert(
            rule_name=rule.name, severity=rule.severity, state=state,
            message=message, value=value, threshold=rule.threshold,
            fired_at=now, labels=rule.labels, annotations=rule.annotations,
        )
        self._alert_history.append(alert)
        return alert

    def _notify(self, alert: Alert, rule: AlertRule):
        now = time.time()
        for ch_name in rule.notification_channels:
            channel = self._channels.get(ch_name)
            if channel:
                try:
                    channel.send(alert)
                except Exception as exc:
                    logger.error("Notification failed on channel %s: %s", ch_name, exc)
        self._last_notification[rule.name] = now
        alert.notified_at = now

    def get_active_alerts(self) -> List[Alert]:
        return [a for a in self._alert_history if a.state == AlertState.FIRING]
'''),

    ("projects/monitoring_dashboard", r'''<think>
For a dashboard data API, I need to think about what operations a monitoring dashboard needs. My first thought is just to expose raw metric values, but wait - dashboards need aggregated, windowed data, not raw points. A chart showing 100k individual data points would be unusable.

So the key operations are:
1. Time-series queries with aggregation (avg, sum, max, min, count)
2. Windowed data with configurable granularity
3. Current status overview panels
4. Support for chart-ready data formatting

I considered using pandas for the aggregation logic since it handles time windows elegantly, but actually that would be a heavy dependency for what amounts to simple bucketing and math. Since we control the data format, plain Python with bisect for time-range lookups should be efficient enough.

I will build a dashboard data service that aggregates metric time series and provides query endpoints for dashboard panels. The store needs to handle retention too - hmm, a ring buffer per series could work, but simpler to just use a list with periodic cleanup.
</think>

Build a dashboard data service in Python that stores time-series metric data, supports windowed aggregation queries, and provides chart-ready formatted output for monitoring dashboards.''', r'''<think>
The dashboard service needs efficient time-series storage with aggregation capabilities. I initially thought about a ring buffer approach with fixed slots, but actually that couples the storage granularity to the insertion rate, which varies. A sorted list with max-length truncation is more flexible.

For windowed aggregation, I could use bisect to find the start/end indices of each window... wait, that is an optimization for later. For now, a linear scan filtering points into time buckets is simpler and correct. Since dashboard queries typically cover at most a day of data, the performance will be fine.

I also need to handle percentile aggregation (p50, p95, p99). I considered using a streaming approximation like t-digest, but since we already have all the points in memory, simple sorted interpolation is exact and straightforward. Therefore the query API should support grouping by time windows and multiple aggregation functions including percentiles.
</think>

import time
import bisect
import threading
import math
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from collections import defaultdict
from enum import Enum


class AggregationType(Enum):
    AVG = "avg"
    SUM = "sum"
    MIN = "min"
    MAX = "max"
    COUNT = "count"
    P50 = "p50"
    P95 = "p95"
    P99 = "p99"


@dataclass
class DataPoint:
    timestamp: float
    value: float
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class TimeSeriesQuery:
    metric_name: str
    start_time: float
    end_time: float
    window_seconds: float = 60.0
    aggregation: AggregationType = AggregationType.AVG
    label_filters: Dict[str, str] = field(default_factory=dict)
    group_by: List[str] = field(default_factory=list)


@dataclass
class ChartSeries:
    name: str
    timestamps: List[float] = field(default_factory=list)
    values: List[float] = field(default_factory=list)
    labels: Dict[str, str] = field(default_factory=dict)


class TimeSeriesStore:
    """In-memory time series storage with retention and downsampling."""

    def __init__(self, max_age_seconds: float = 86400, max_points_per_series: int = 100000):
        self._series: Dict[str, List[DataPoint]] = defaultdict(list)
        self._lock = threading.Lock()
        self._max_age = max_age_seconds
        self._max_points = max_points_per_series

    def record(self, metric_name: str, value: float, labels: Dict[str, str] = None,
               timestamp: float = None):
        """Record a data point."""
        ts = timestamp or time.time()
        point = DataPoint(timestamp=ts, value=value, labels=labels or {})
        key = self._make_key(metric_name, labels or {})
        with self._lock:
            series = self._series[key]
            bisect.insort_left(series, point, key=lambda p: p.timestamp)
            if len(series) > self._max_points:
                self._series[key] = series[-self._max_points:]

    def _make_key(self, name: str, labels: Dict[str, str]) -> str:
        label_str = ",".join(f"{k}={v}" for k, v in sorted(labels.items()))
        return f"{name}{{{label_str}}}"

    def query(self, q: TimeSeriesQuery) -> List[ChartSeries]:
        """Execute a time series query and return chart-ready data."""
        matching_series = self._find_matching(q.metric_name, q.label_filters)
        if q.group_by:
            grouped = self._group_series(matching_series, q.group_by)
        else:
            grouped = {"_all": [p for pts in matching_series.values() for p in pts]}

        results = []
        for group_key, points in grouped.items():
            filtered = [p for p in points if q.start_time <= p.timestamp <= q.end_time]
            if not filtered:
                continue
            windows = self._window_aggregate(filtered, q.start_time, q.end_time,
                                             q.window_seconds, q.aggregation)
            series = ChartSeries(
                name=group_key,
                timestamps=[w[0] for w in windows],
                values=[w[1] for w in windows],
            )
            results.append(series)
        return results

    def _find_matching(self, metric_name: str, filters: Dict[str, str]) -> Dict[str, List[DataPoint]]:
        matched = {}
        with self._lock:
            for key, points in self._series.items():
                if not key.startswith(metric_name):
                    continue
                if filters:
                    if points and all(
                        points[0].labels.get(k) == v for k, v in filters.items()
                    ):
                        matched[key] = list(points)
                else:
                    matched[key] = list(points)
        return matched

    def _group_series(self, series: Dict[str, List[DataPoint]],
                      group_by: List[str]) -> Dict[str, List[DataPoint]]:
        grouped = defaultdict(list)
        for key, points in series.items():
            for point in points:
                group_key = ",".join(f"{g}={point.labels.get(g, '')}" for g in group_by)
                grouped[group_key].append(point)
        return dict(grouped)

    def _window_aggregate(self, points: List[DataPoint], start: float, end: float,
                          window: float, agg: AggregationType) -> List[Tuple[float, float]]:
        results = []
        current = start
        while current < end:
            window_end = current + window
            bucket = [p.value for p in points if current <= p.timestamp < window_end]
            if bucket:
                value = self._aggregate(bucket, agg)
                results.append((current + window / 2, value))
            current = window_end
        return results

    def _aggregate(self, values: List[float], agg: AggregationType) -> float:
        if agg == AggregationType.AVG:
            return sum(values) / len(values)
        elif agg == AggregationType.SUM:
            return sum(values)
        elif agg == AggregationType.MIN:
            return min(values)
        elif agg == AggregationType.MAX:
            return max(values)
        elif agg == AggregationType.COUNT:
            return float(len(values))
        elif agg in (AggregationType.P50, AggregationType.P95, AggregationType.P99):
            pct = {"p50": 50, "p95": 95, "p99": 99}[agg.value]
            return self._percentile(values, pct)
        return 0.0

    def _percentile(self, values: List[float], pct: float) -> float:
        sorted_vals = sorted(values)
        idx = (pct / 100.0) * (len(sorted_vals) - 1)
        lower = int(math.floor(idx))
        upper = int(math.ceil(idx))
        if lower == upper:
            return sorted_vals[lower]
        frac = idx - lower
        return sorted_vals[lower] * (1 - frac) + sorted_vals[upper] * frac

    def cleanup(self):
        """Remove data points older than retention period."""
        cutoff = time.time() - self._max_age
        with self._lock:
            for key in list(self._series.keys()):
                self._series[key] = [
                    p for p in self._series[key] if p.timestamp >= cutoff
                ]
                if not self._series[key]:
                    del self._series[key]


class DashboardService:
    """High-level dashboard API for panel queries."""

    def __init__(self, store: TimeSeriesStore):
        self.store = store

    def panel_timeseries(self, metric: str, duration_seconds: float = 3600,
                         window: float = 60, agg: str = "avg",
                         filters: Dict = None) -> Dict:
        now = time.time()
        q = TimeSeriesQuery(
            metric_name=metric,
            start_time=now - duration_seconds,
            end_time=now,
            window_seconds=window,
            aggregation=AggregationType(agg),
            label_filters=filters or {},
        )
        series_list = self.store.query(q)
        return {
            "type": "timeseries",
            "metric": metric,
            "series": [
                {"name": s.name, "data": list(zip(s.timestamps, s.values))}
                for s in series_list
            ],
        }

    def panel_stat(self, metric: str, agg: str = "avg",
                   duration_seconds: float = 300, filters: Dict = None) -> Dict:
        now = time.time()
        q = TimeSeriesQuery(
            metric_name=metric,
            start_time=now - duration_seconds,
            end_time=now,
            window_seconds=duration_seconds,
            aggregation=AggregationType(agg),
            label_filters=filters or {},
        )
        series_list = self.store.query(q)
        value = series_list[0].values[0] if series_list and series_list[0].values else 0
        return {"type": "stat", "metric": metric, "value": value, "agg": agg}

    def status_overview(self, checks: Dict[str, str]) -> Dict:
        total = len(checks)
        healthy = sum(1 for v in checks.values() if v == "healthy")
        return {
            "type": "status",
            "total": total,
            "healthy": healthy,
            "degraded": sum(1 for v in checks.values() if v == "degraded"),
            "unhealthy": total - healthy - sum(1 for v in checks.values() if v == "degraded"),
            "checks": checks,
        }
'''),

    ("projects/monitoring_slo", r'''Build an SLO (Service Level Objective) tracking system in Python that monitors error budgets, calculates burn rates, supports rolling windows, and generates compliance reports.''', r'''import time
import threading
import math
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from collections import deque
from enum import Enum


class SLOType(Enum):
    AVAILABILITY = "availability"
    LATENCY = "latency"
    THROUGHPUT = "throughput"


@dataclass
class SLODefinition:
    name: str
    slo_type: SLOType
    target: float  # e.g. 0.999 for 99.9%
    window_days: int = 30
    description: str = ""
    labels: Dict[str, str] = field(default_factory=dict)


@dataclass
class SLIDataPoint:
    timestamp: float
    good: int = 0
    total: int = 0
    latency_ms: float = 0.0


@dataclass
class BurnRateAlert:
    slo_name: str
    short_window_minutes: float
    long_window_minutes: float
    threshold: float
    severity: str = "warning"


class SLOTracker:
    """Tracks SLO compliance using error budget methodology."""

    def __init__(self):
        self._definitions: Dict[str, SLODefinition] = {}
        self._data: Dict[str, deque] = {}
        self._burn_rate_alerts: Dict[str, List[BurnRateAlert]] = {}
        self._lock = threading.Lock()

    def define_slo(self, slo: SLODefinition):
        """Register an SLO definition."""
        max_points = slo.window_days * 24 * 60  # one point per minute
        with self._lock:
            self._definitions[slo.name] = slo
            self._data[slo.name] = deque(maxlen=max_points)
        return self

    def add_burn_rate_alert(self, slo_name: str, short_window_min: float,
                            long_window_min: float, threshold: float,
                            severity: str = "warning"):
        """Add multi-window burn rate alert for an SLO."""
        alert = BurnRateAlert(
            slo_name=slo_name,
            short_window_minutes=short_window_min,
            long_window_minutes=long_window_min,
            threshold=threshold,
            severity=severity,
        )
        with self._lock:
            if slo_name not in self._burn_rate_alerts:
                self._burn_rate_alerts[slo_name] = []
            self._burn_rate_alerts[slo_name].append(alert)

    def record(self, slo_name: str, good: int, total: int,
               latency_ms: float = 0.0, timestamp: float = None):
        """Record an SLI measurement."""
        ts = timestamp or time.time()
        point = SLIDataPoint(timestamp=ts, good=good, total=total, latency_ms=latency_ms)
        with self._lock:
            if slo_name in self._data:
                self._data[slo_name].append(point)

    def current_sli(self, slo_name: str, window_minutes: float = None) -> float:
        """Calculate current SLI value over the given window."""
        with self._lock:
            slo = self._definitions.get(slo_name)
            points = list(self._data.get(slo_name, []))
        if not slo or not points:
            return 1.0

        if window_minutes:
            cutoff = time.time() - (window_minutes * 60)
            points = [p for p in points if p.timestamp >= cutoff]

        if slo.slo_type == SLOType.AVAILABILITY:
            total_good = sum(p.good for p in points)
            total_all = sum(p.total for p in points)
            return total_good / total_all if total_all > 0 else 1.0
        elif slo.slo_type == SLOType.LATENCY:
            total_good = sum(p.good for p in points)
            total_all = sum(p.total for p in points)
            return total_good / total_all if total_all > 0 else 1.0
        return 1.0

    def error_budget(self, slo_name: str) -> Dict:
        """Calculate error budget status."""
        with self._lock:
            slo = self._definitions.get(slo_name)
            points = list(self._data.get(slo_name, []))
        if not slo:
            return {"error": "SLO not found"}

        window_seconds = slo.window_days * 86400
        cutoff = time.time() - window_seconds
        points = [p for p in points if p.timestamp >= cutoff]

        total_requests = sum(p.total for p in points)
        total_good = sum(p.good for p in points)
        total_bad = total_requests - total_good

        allowed_bad = total_requests * (1 - slo.target)
        budget_remaining = allowed_bad - total_bad
        budget_fraction = budget_remaining / allowed_bad if allowed_bad > 0 else 1.0

        return {
            "slo_name": slo.name,
            "target": slo.target,
            "current_sli": total_good / total_requests if total_requests > 0 else 1.0,
            "total_requests": total_requests,
            "error_count": total_bad,
            "budget_total": allowed_bad,
            "budget_remaining": max(0, budget_remaining),
            "budget_fraction": max(0, budget_fraction),
            "budget_exhausted": budget_remaining <= 0,
            "window_days": slo.window_days,
        }

    def burn_rate(self, slo_name: str, window_minutes: float) -> float:
        """Calculate burn rate over a time window.

        Burn rate = 1 means consuming budget at exactly the rate
        that would exhaust it at the end of the window.
        Burn rate > 1 means consuming budget faster than sustainable.
        """
        with self._lock:
            slo = self._definitions.get(slo_name)
            points = list(self._data.get(slo_name, []))
        if not slo or not points:
            return 0.0

        cutoff = time.time() - (window_minutes * 60)
        window_points = [p for p in points if p.timestamp >= cutoff]

        total = sum(p.total for p in window_points)
        good = sum(p.good for p in window_points)
        if total == 0:
            return 0.0

        error_rate = (total - good) / total
        allowed_error_rate = 1 - slo.target
        if allowed_error_rate == 0:
            return float("inf") if error_rate > 0 else 0.0
        return error_rate / allowed_error_rate

    def check_burn_rate_alerts(self, slo_name: str) -> List[Dict]:
        """Evaluate burn rate alerts using multi-window strategy."""
        alerts = self._burn_rate_alerts.get(slo_name, [])
        fired = []
        for alert in alerts:
            short_rate = self.burn_rate(slo_name, alert.short_window_minutes)
            long_rate = self.burn_rate(slo_name, alert.long_window_minutes)
            if short_rate >= alert.threshold and long_rate >= alert.threshold:
                fired.append({
                    "slo": slo_name,
                    "severity": alert.severity,
                    "short_window_min": alert.short_window_minutes,
                    "long_window_min": alert.long_window_minutes,
                    "short_burn_rate": round(short_rate, 2),
                    "long_burn_rate": round(long_rate, 2),
                    "threshold": alert.threshold,
                })
        return fired

    def compliance_report(self) -> Dict:
        """Generate compliance report for all SLOs."""
        report = {"generated_at": time.time(), "slos": []}
        with self._lock:
            names = list(self._definitions.keys())
        for name in names:
            budget = self.error_budget(name)
            slo = self._definitions[name]
            status = "met" if budget["current_sli"] >= slo.target else "breached"
            report["slos"].append({
                "name": name,
                "type": slo.slo_type.value,
                "target": f"{slo.target * 100:.2f}%",
                "current": f"{budget['current_sli'] * 100:.2f}%",
                "status": status,
                "budget_remaining_pct": f"{budget['budget_fraction'] * 100:.1f}%",
                "window_days": slo.window_days,
                "error_count": budget["error_count"],
                "total_requests": budget["total_requests"],
            })
        return report
'''),
]
