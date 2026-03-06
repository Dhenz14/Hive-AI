"""Thinking-trace pairs: error logging and monitoring."""

PAIRS = [
    (
        "thinking/error-handling",
        r'''How should I structure error logging in a production Python application? I want logs that are easy to search, aggregate, and alert on -- not just print statements scattered throughout the code.''',
        r'''<think>
Structured error logging for production. My first instinct is to reach for structlog or python-json-logger, but wait -- should I show a third-party dependency or build on stdlib logging? Actually, showing the pattern with stdlib is more universally applicable, and the concepts transfer directly to structlog.

Could I just use logging.basicConfig with a JSON formatter? Hmm, that is too simplistic. The real challenge is not formatting -- it is context enrichment. Every log line needs request ID, user ID, and service name, but those values live in different scopes (request context vs application config). I considered passing a context dict to every log call manually, but that is tedious and developers will forget.

The better approach is contextvars for request-scoped data. Since Python 3.7, ContextVar propagates correctly through async code, so a request ID set in middleware automatically appears in all log calls within that request. That is much cleaner than threading.local (which breaks with async).

One thing I almost overlooked: sensitive data filtering. If someone logs a request body that contains a password field, that password ends up in your log aggregation system forever. I initially thought "just tell developers not to log sensitive fields," but that relies on human discipline. Therefore I need an automatic filter in the logging pipeline that redacts known sensitive field names (password, token, ssn, etc.) before the log is emitted.

Performance is another concern -- JSON serialization on every log call adds overhead. Since most log lines are DEBUG/INFO that get filtered out in production, the formatter should be lazy and only serialize when the log actually gets emitted.
</think>

Structured logging is the foundation of production error observability. Here is a complete setup:

```python
import logging
import json
import time
import traceback
import uuid
from contextvars import ContextVar
from functools import wraps
from typing import Any

# ============================================================
# CONTEXT VARIABLES FOR REQUEST TRACKING
# ============================================================

request_id_var: ContextVar[str] = ContextVar("request_id", default="no-request")
user_id_var: ContextVar[str] = ContextVar("user_id", default="anonymous")
service_name_var: ContextVar[str] = ContextVar("service_name", default="app")


# ============================================================
# SENSITIVE DATA FILTER
# ============================================================

SENSITIVE_KEYS = {
    "password", "passwd", "secret", "token", "api_key",
    "apikey", "authorization", "credit_card", "ssn",
    "access_token", "refresh_token", "private_key",
}


def redact_sensitive(data: dict) -> dict:
    """Recursively redact sensitive fields from log data."""
    cleaned = {}
    for key, value in data.items():
        lower_key = key.lower().replace("-", "_")
        if lower_key in SENSITIVE_KEYS:
            cleaned[key] = "***REDACTED***"
        elif isinstance(value, dict):
            cleaned[key] = redact_sensitive(value)
        elif isinstance(value, list):
            cleaned[key] = [
                redact_sensitive(item) if isinstance(item, dict) else item
                for item in value
            ]
        else:
            cleaned[key] = value
    return cleaned


# ============================================================
# JSON LOG FORMATTER
# ============================================================

class StructuredFormatter(logging.Formatter):
    """Outputs each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S.") +
                         f"{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": service_name_var.get(),
            "request_id": request_id_var.get(),
            "user_id": user_id_var.get(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Add exception info if present
        if record.exc_info and record.exc_info[0] is not None:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": traceback.format_exception(*record.exc_info),
            }

        # Add any extra structured fields
        extra_fields = getattr(record, "extra_fields", {})
        if extra_fields:
            log_entry["context"] = redact_sensitive(extra_fields)

        return json.dumps(log_entry, default=str)


# ============================================================
# LOGGER SETUP
# ============================================================

def setup_logging(service_name: str = "myapp",
                  log_level: str = "INFO") -> logging.Logger:
    service_name_var.set(service_name)

    handler = logging.StreamHandler()
    handler.setFormatter(StructuredFormatter())

    logger = logging.getLogger(service_name)
    logger.setLevel(getattr(logging, log_level.upper()))
    logger.addHandler(handler)

    # Prevent duplicate handlers on repeated calls
    logger.propagate = False

    return logger


# ============================================================
# CONTEXT-AWARE LOGGING HELPERS
# ============================================================

class StructuredLogger:
    """Wraps stdlib logger to add structured context easily."""

    def __init__(self, logger: logging.Logger):
        self._logger = logger

    def _log(self, level: int, message: str, **kwargs):
        record = self._logger.makeRecord(
            self._logger.name, level, "(unknown)", 0,
            message, (), None,
        )
        record.extra_fields = kwargs
        self._logger.handle(record)

    def info(self, message: str, **kwargs):
        self._log(logging.INFO, message, **kwargs)

    def warning(self, message: str, **kwargs):
        self._log(logging.WARNING, message, **kwargs)

    def error(self, message: str, exc: Exception = None, **kwargs):
        record = self._logger.makeRecord(
            self._logger.name, logging.ERROR, "(unknown)", 0,
            message, (), (type(exc), exc, exc.__traceback__) if exc else None,
        )
        record.extra_fields = kwargs
        self._logger.handle(record)

    def critical(self, message: str, exc: Exception = None, **kwargs):
        record = self._logger.makeRecord(
            self._logger.name, logging.CRITICAL, "(unknown)", 0,
            message, (), (type(exc), exc, exc.__traceback__) if exc else None,
        )
        record.extra_fields = kwargs
        self._logger.handle(record)


# ============================================================
# USAGE IN A WEB APP
# ============================================================

log = StructuredLogger(setup_logging("order-service"))

def process_order(order_data: dict):
    request_id_var.set(str(uuid.uuid4()))
    user_id_var.set(order_data.get("user_id", "unknown"))

    log.info("Processing order", order_id=order_data.get("id"),
             item_count=len(order_data.get("items", [])))

    try:
        validate_order(order_data)
        charge_payment(order_data)
        log.info("Order processed successfully",
                 order_id=order_data["id"])
    except ValueError as exc:
        # Business logic error -- WARNING, not ERROR
        log.warning("Order validation failed",
                    order_id=order_data.get("id"),
                    reason=str(exc))
        raise
    except Exception as exc:
        # Unexpected error -- ERROR level with full traceback
        log.error("Order processing failed unexpectedly",
                  exc=exc,
                  order_id=order_data.get("id"),
                  payment_method=order_data.get("payment", {}).get("method"))
        raise
```

**Resulting JSON log line (one per event, easy to ship to Elasticsearch/Datadog):**

```json
{
  "timestamp": "2025-01-15T10:30:45.123Z",
  "level": "ERROR",
  "service": "order-service",
  "request_id": "a1b2c3d4-...",
  "user_id": "user_42",
  "message": "Order processing failed unexpectedly",
  "context": {"order_id": "ORD-789", "payment_method": "credit_card"},
  "exception": {"type": "ConnectionError", "message": "..."}
}
```

**Key principles:**

1. **JSON format**: one JSON object per line, machine-parseable for log aggregation
2. **Context propagation**: `ContextVar` carries request_id and user_id through async call stacks automatically
3. **Sensitive data redaction**: passwords, tokens, and API keys are scrubbed before logging
4. **Correct log levels**: WARNING for expected failures (validation), ERROR for unexpected ones, CRITICAL for service-threatening issues
5. **Correlation**: every log line includes request_id so you can trace a single request across all log entries''',
    ),
    (
        "thinking/error-handling",
        r'''How do I aggregate errors effectively in production? I want to group similar errors, track error rates, and avoid getting 10,000 alerts for the same issue.''',
        r'''<think>
Error aggregation -- the goal is to prevent alert fatigue by grouping identical errors. But what makes two errors "identical"? My first thought was same exception type + same message, but that is too narrow. A ValueError("invalid id: 42") and ValueError("invalid id: 99") are the same bug with different data. I need to fingerprint based on exception type + code location, stripping out variable data.

Could I use the full stack trace as the fingerprint? Hmm, actually that is too sensitive -- a minor refactor that changes line numbers would split one error group into two, even though it is the same bug. I considered using just the function names from the stack (ignoring line numbers), which is more stable across deploys.

Wait, there is another subtlety: the same root cause can manifest at different call sites. For example, a database connection timeout might surface as different exceptions depending on which query was running. Should those be grouped? Probably not automatically, but the system should support manual grouping rules.

For rate tracking, I need a sliding window counter -- not just "N errors total" but "N errors in the last 5 minutes." I initially considered a simple counter with periodic resets, but that has a boundary problem: if 100 errors happen right before the reset and 100 right after, neither window triggers a threshold of 150. Therefore I need a proper sliding window using time-bucketed counts.

The alerting layer should deduplicate: send one alert when an error group crosses the threshold, then suppress until the rate drops and rises again. Otherwise a sustained error condition generates continuous alerts.
</think>

Error aggregation prevents alert fatigue by grouping identical errors and tracking rates. Here is a practical implementation:

```python
import hashlib
import time
import traceback
from collections import defaultdict
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional


@dataclass
class ErrorGroup:
    """Represents a group of similar errors."""
    fingerprint: str
    exception_type: str
    message_template: str
    location: str          # module:function:line
    first_seen: float
    last_seen: float
    count: int = 0
    sample_traceback: str = ""
    sample_context: dict = field(default_factory=dict)

    @property
    def age_seconds(self) -> float:
        return time.time() - self.first_seen

    @property
    def rate_per_minute(self) -> float:
        elapsed = max(self.age_seconds, 1.0)
        return (self.count / elapsed) * 60


class ErrorAggregator:
    """Groups and deduplicates errors for alerting."""

    def __init__(self, flush_interval: int = 300):
        self._groups: dict[str, ErrorGroup] = {}
        self._lock = Lock()
        self._flush_interval = flush_interval
        self._alert_callbacks: list = []
        self._alerted_fingerprints: dict[str, float] = {}
        # Minimum seconds between alerts for the same error group
        self._alert_cooldown = 600  # 10 minutes

    def add_alert_callback(self, callback):
        self._alert_callbacks.append(callback)

    @staticmethod
    def compute_fingerprint(exc: Exception, tb_string: str) -> str:
        """Create a stable fingerprint for grouping similar errors.

        Groups by: exception class + the top frame location.
        This means the same error from the same code location
        maps to one group, regardless of variable data in the message.
        """
        exc_type = type(exc).__name__

        # Extract the innermost frame location
        tb_lines = tb_string.strip().splitlines()
        location = ""
        for line in reversed(tb_lines):
            stripped = line.strip()
            if stripped.startswith("File "):
                location = stripped
                break

        raw = f"{exc_type}::{location}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    def record(self, exc: Exception, context: dict = None):
        """Record an error occurrence."""
        tb_string = "".join(traceback.format_exception(
            type(exc), exc, exc.__traceback__
        ))
        fingerprint = self.compute_fingerprint(exc, tb_string)
        now = time.time()

        with self._lock:
            if fingerprint in self._groups:
                group = self._groups[fingerprint]
                group.count += 1
                group.last_seen = now
            else:
                # Extract location from traceback
                tb_lines = tb_string.strip().splitlines()
                location = "unknown"
                for line in reversed(tb_lines):
                    if line.strip().startswith("File "):
                        location = line.strip()
                        break

                group = ErrorGroup(
                    fingerprint=fingerprint,
                    exception_type=type(exc).__name__,
                    message_template=str(exc),
                    location=location,
                    first_seen=now,
                    last_seen=now,
                    count=1,
                    sample_traceback=tb_string,
                    sample_context=context or {},
                )
                self._groups[fingerprint] = group

        self._check_alerts(group)

    def _check_alerts(self, group: ErrorGroup):
        """Fire alert if thresholds are exceeded and cooldown has passed."""
        now = time.time()

        # Check cooldown
        last_alert = self._alerted_fingerprints.get(group.fingerprint, 0)
        if now - last_alert < self._alert_cooldown:
            return

        should_alert = False

        # Threshold: new error type (first occurrence)
        if group.count == 1:
            should_alert = True

        # Threshold: error rate spike (more than 10 per minute)
        if group.rate_per_minute > 10:
            should_alert = True

        # Threshold: high total count
        if group.count >= 100 and group.count % 100 == 0:
            should_alert = True

        if should_alert:
            self._alerted_fingerprints[group.fingerprint] = now
            for callback in self._alert_callbacks:
                try:
                    callback(group)
                except Exception:
                    pass  # Never let alerting crash the app

    def get_summary(self) -> list[dict]:
        """Get current error group summary, sorted by count."""
        with self._lock:
            groups = sorted(
                self._groups.values(),
                key=lambda g: g.count,
                reverse=True,
            )
        return [
            {
                "fingerprint": g.fingerprint,
                "type": g.exception_type,
                "message": g.message_template[:200],
                "location": g.location,
                "count": g.count,
                "rate_per_min": round(g.rate_per_minute, 2),
                "first_seen": g.first_seen,
                "last_seen": g.last_seen,
            }
            for g in groups
        ]

    def flush_old(self, max_age: int = 3600):
        """Remove error groups older than max_age seconds."""
        now = time.time()
        with self._lock:
            stale = [
                fp for fp, group in self._groups.items()
                if now - group.last_seen > max_age
            ]
            for fp in stale:
                del self._groups[fp]
                self._alerted_fingerprints.pop(fp, None)


# ============================================================
# USAGE
# ============================================================

aggregator = ErrorAggregator()

def send_slack_alert(group: ErrorGroup):
    print(f"ALERT: {group.exception_type} in {group.location}")
    print(f"  Count: {group.count}, Rate: {group.rate_per_minute:.1f}/min")

aggregator.add_alert_callback(send_slack_alert)

# Simulate repeated errors
for i in range(50):
    try:
        result = 1 / 0
    except ZeroDivisionError as exc:
        aggregator.record(exc, {"iteration": i})

# Check summary -- all 50 grouped under one fingerprint
summary = aggregator.get_summary()
print(f"Unique error groups: {len(summary)}")
print(f"Total occurrences: {summary[0]['count']}")
# Output: Unique error groups: 1
#         Total occurrences: 50
```

**Why this matters:**

1. **Fingerprinting** groups errors by type + code location, so 10,000 identical errors become one group with count=10000
2. **Alert cooldown** prevents repeated notifications for the same issue (configurable, default 10 minutes)
3. **Rate tracking** detects spikes -- a sudden burst of errors triggers an alert even if each individual error is known
4. **Periodic flush** prevents unbounded memory growth from old error groups
5. **Sample preservation** keeps one full traceback and context per group for debugging without storing all 10,000''',
    ),
    (
        "thinking/error-handling",
        r'''How do I set up effective alerting thresholds for errors? I keep getting either too many alerts (alert fatigue) or missing real problems because thresholds are too high.''',
        r'''<think>
Alert threshold tuning -- this is where most monitoring setups fail in practice. Static thresholds like "alert if errors > 100/minute" seem reasonable, but wait -- what if traffic doubled? 100 errors at 10K requests/min is 1% error rate (fine), but 100 errors at 1K requests/min is 10% (terrible). So absolute counts are almost always wrong for alerting. I need rate-based thresholds at minimum.

I considered purely dynamic thresholds based on historical patterns (alert if error rate is 2x the rolling average). But actually that has a dangerous failure mode: if the error rate slowly creeps up over weeks, the rolling average adjusts and the alert never fires. You slowly boil the frog. Therefore I need both dynamic thresholds (for spike detection) AND absolute SLO-based thresholds (as a hard floor).

The SRE approach is burn rate alerting: define an error budget from your SLO (e.g., 99.9% availability = 0.1% error budget), then alert based on how fast you are consuming that budget. A burn rate of 1x means you will exactly exhaust your monthly budget by month end. A burn rate of 14.4x means you will exhaust it in 5 hours -- that deserves a page.

Hmm, but single-window burn rate has a problem: a brief spike can trigger a page even though the overall budget is healthy. The fix is multi-window alerting -- require BOTH a short window (e.g., 5 min at 14.4x) AND a long window (e.g., 1 hour at 6x) before paging. This filters out transient blips while still catching sustained degradation.

Severity classification matters too: not every threshold breach deserves a 3am page. Pages for immediate threats, tickets for slow burns, log-only for informational anomalies.
</think>

Effective alerting requires layered thresholds that distinguish spikes from slow degradation. Here are the key patterns:

```python
import time
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class Severity(Enum):
    LOG = "log"           # Just record it
    TICKET = "ticket"     # Create a ticket for next business day
    PAGE = "page"         # Wake someone up


@dataclass
class AlertRule:
    name: str
    severity: Severity
    description: str


# ============================================================
# SLIDING WINDOW RATE TRACKER
# ============================================================

class SlidingWindowCounter:
    """Counts events in a sliding time window."""

    def __init__(self, window_seconds: int):
        self._window = window_seconds
        self._events: deque = deque()

    def record(self, timestamp: float = None):
        ts = timestamp or time.time()
        self._events.append(ts)
        self._trim(ts)

    def count(self, now: float = None) -> int:
        ts = now or time.time()
        self._trim(ts)
        return len(self._events)

    def rate_per_second(self, now: float = None) -> float:
        ts = now or time.time()
        self._trim(ts)
        if not self._events:
            return 0.0
        return len(self._events) / self._window

    def _trim(self, now: float):
        cutoff = now - self._window
        while self._events and self._events[0] < cutoff:
            self._events.popleft()


# ============================================================
# ERROR BUDGET TRACKER (SLO-BASED)
# ============================================================

class ErrorBudgetTracker:
    """Track error budget consumption based on SLO.

    Example: 99.9% availability SLO over 30 days
    = 0.1% error budget = 43.2 minutes of downtime allowed
    """

    def __init__(self, slo_target: float = 0.999,
                 window_days: int = 30):
        self.slo_target = slo_target
        self.window_seconds = window_days * 86400
        self.error_budget = 1.0 - slo_target  # 0.001 for 99.9%
        self._total_requests = SlidingWindowCounter(self.window_seconds)
        self._failed_requests = SlidingWindowCounter(self.window_seconds)

    def record_request(self, success: bool):
        now = time.time()
        self._total_requests.record(now)
        if not success:
            self._failed_requests.record(now)

    def budget_remaining(self) -> float:
        """Returns fraction of error budget remaining (0.0 to 1.0)."""
        total = self._total_requests.count()
        if total == 0:
            return 1.0
        failed = self._failed_requests.count()
        actual_error_rate = failed / total
        budget_consumed = actual_error_rate / self.error_budget
        return max(0.0, 1.0 - budget_consumed)

    def burn_rate(self, short_window: int = 300) -> float:
        """How fast the budget is being consumed right now.

        burn_rate = 1.0 means consuming budget at exactly the
        sustainable rate (will hit 0% at end of window).
        burn_rate = 10.0 means 10x the sustainable rate.
        """
        now = time.time()

        short_total = SlidingWindowCounter(short_window)
        short_failed = SlidingWindowCounter(short_window)

        # Re-count only events in the short window
        for ts in self._total_requests._events:
            if ts > now - short_window:
                short_total.record(ts)
        for ts in self._failed_requests._events:
            if ts > now - short_window:
                short_failed.record(ts)

        total = short_total.count(now)
        if total == 0:
            return 0.0
        short_error_rate = short_failed.count(now) / total
        return short_error_rate / self.error_budget


# ============================================================
# MULTI-WINDOW ALERT EVALUATOR
# ============================================================

class AlertEvaluator:
    """Evaluates multiple alert rules using different strategies."""

    def __init__(self):
        self._error_counter_1m = SlidingWindowCounter(60)
        self._error_counter_5m = SlidingWindowCounter(300)
        self._error_counter_1h = SlidingWindowCounter(3600)
        self._budget = ErrorBudgetTracker(slo_target=0.999)

    def record_request(self, success: bool):
        now = time.time()
        self._budget.record_request(success)
        if not success:
            self._error_counter_1m.record(now)
            self._error_counter_5m.record(now)
            self._error_counter_1h.record(now)

    def evaluate(self) -> list[AlertRule]:
        """Check all alert rules and return any that are firing."""
        fired = []

        # Rule 1: Spike detection -- many errors in 1 minute
        # Catches sudden outages immediately
        errors_1m = self._error_counter_1m.count()
        if errors_1m > 50:
            fired.append(AlertRule(
                name="error_spike",
                severity=Severity.PAGE,
                description=f"{errors_1m} errors in last 1 minute",
            ))

        # Rule 2: Sustained errors -- elevated rate over 5 minutes
        # Catches issues that are not a brief spike
        errors_5m = self._error_counter_5m.count()
        if errors_5m > 100:
            fired.append(AlertRule(
                name="sustained_errors",
                severity=Severity.PAGE,
                description=f"{errors_5m} errors in last 5 minutes",
            ))

        # Rule 3: Slow burn -- moderate errors over 1 hour
        # Catches gradual degradation that spike alerts miss
        errors_1h = self._error_counter_1h.count()
        if errors_1h > 500:
            fired.append(AlertRule(
                name="slow_burn",
                severity=Severity.TICKET,
                description=f"{errors_1h} errors in last 1 hour",
            ))

        # Rule 4: Budget burn rate -- SLO-based
        burn = self._budget.burn_rate(short_window=300)
        if burn > 14.4:
            # 14.4x burn rate = will exhaust 30-day budget in 2 hours
            fired.append(AlertRule(
                name="budget_critical",
                severity=Severity.PAGE,
                description=f"Error budget burn rate: {burn:.1f}x",
            ))
        elif burn > 6.0:
            # 6x = budget exhausted in ~5 days
            fired.append(AlertRule(
                name="budget_warning",
                severity=Severity.TICKET,
                description=f"Error budget burn rate: {burn:.1f}x",
            ))

        # Rule 5: Budget nearly exhausted
        remaining = self._budget.budget_remaining()
        if remaining < 0.1:
            fired.append(AlertRule(
                name="budget_exhausted",
                severity=Severity.PAGE,
                description=f"Error budget {remaining*100:.1f}% remaining",
            ))

        return fired


# ============================================================
# PRACTICAL SETUP
# ============================================================

evaluator = AlertEvaluator()

# In your request handler middleware:
def handle_request(request):
    try:
        response = process(request)
        evaluator.record_request(success=True)
        return response
    except Exception as exc:
        evaluator.record_request(success=False)
        # Check alerts periodically, not on every error
        alerts = evaluator.evaluate()
        for alert in alerts:
            if alert.severity == Severity.PAGE:
                send_pagerduty(alert)
            elif alert.severity == Severity.TICKET:
                create_jira_ticket(alert)
        raise
```

**Choosing the right thresholds:**

| Strategy | Catches | Misses | Use For |
|----------|---------|--------|---------|
| Static count (>50 in 1min) | Sudden spikes | Slow degradation | Outage detection |
| Sustained rate (>100 in 5min) | Ongoing issues | Brief blips | Partial failures |
| Burn rate (>14x) | Budget-threatening trends | One-off errors | SLO compliance |
| Budget remaining (<10%) | Cumulative impact | New spikes if budget is full | Monthly reviews |

**Best practices:**

1. **Layer your alerts**: fast window for spikes, slow window for burns, budget for trends
2. **PAGE vs TICKET**: only page for issues that need immediate human action
3. **Burn rate alerts** are the gold standard -- they automatically adjust sensitivity based on your SLO
4. **Review thresholds monthly**: tune based on actual alert frequency and false positive rate
5. **Alert on symptoms, not causes**: "error rate > 1%" is better than "database CPU > 90%"''',
    ),
    (
        "thinking/error-handling",
        r'''What are error budgets and how do I use them practically to make decisions about reliability vs feature velocity? I understand the concept but struggle with the implementation.''',
        r'''<think>
Error budgets -- the user wants practical implementation, not theory. My first thought is to compute (1 - SLO) * total_requests = allowed_failures and track against that. But wait, what time window? Monthly is standard, but a monthly budget means you could blow the entire budget on day 1 and then be paralyzed for 29 days. I need to think about the policy implications.

Could I use a rolling window instead of calendar months? That avoids the "budget resets on the 1st" gaming, but makes it harder to communicate ("we have 43% budget remaining" -- remaining of what period?). I considered both approaches and I think calendar months are more practical for human decision-making, with burn rate alerting to catch early-month blow-outs.

The real value of error budgets is in POLICY decisions:
- Budget > 50% remaining: deploy freely, experiment
- Budget 20-50%: slow down deployments, extra review
- Budget < 20%: freeze non-critical changes, focus on reliability
- Budget exhausted: full freeze, all hands on reliability

Hmm, but who enforces these policies? If it is just a dashboard, people ignore it. Therefore I need automated gates -- CI/CD checks that block deployments when the budget is low. Actually, I should be careful here: a hard block on ALL deployments is dangerous because it also blocks reliability fixes. The gate should block feature deployments but allow explicitly-tagged reliability fixes through.

I should show concrete code for budget tracking, policy evaluation, and deployment gating -- not just the math formulas.
</think>

Error budgets turn reliability into a measurable, spendable resource. Here is how to implement them end to end:

```python
import time
import json
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class BudgetPolicy(Enum):
    NORMAL = "normal"           # Business as usual
    CAUTION = "caution"         # Reduce risky deploys
    FREEZE = "freeze"           # Only reliability fixes
    EMERGENCY = "emergency"     # All hands on reliability


@dataclass
class SLODefinition:
    name: str
    target: float           # e.g., 0.999 for 99.9%
    window_days: int        # e.g., 30
    description: str

    @property
    def budget_fraction(self) -> float:
        """How much failure is allowed as a fraction."""
        return 1.0 - self.target

    @property
    def budget_minutes(self) -> float:
        """How many minutes of downtime are allowed."""
        return self.window_days * 24 * 60 * self.budget_fraction


class ErrorBudgetManager:
    """Tracks error budget consumption and enforces policies."""

    def __init__(self, slo: SLODefinition):
        self.slo = slo
        self._good_events = 0
        self._total_events = 0
        self._window_start = time.time()
        self._incident_minutes = 0.0

    def record_events(self, total: int, good: int):
        """Record a batch of events (e.g., from metrics pipeline)."""
        self._total_events += total
        self._good_events += good

    def record_incident(self, duration_minutes: float):
        """Record a service incident duration."""
        self._incident_minutes += duration_minutes

    @property
    def current_reliability(self) -> float:
        if self._total_events == 0:
            return 1.0
        return self._good_events / self._total_events

    @property
    def budget_consumed_fraction(self) -> float:
        """How much of the error budget has been consumed (0.0 to 1.0+)."""
        if self._total_events == 0:
            return 0.0
        bad_events = self._total_events - self._good_events
        allowed_bad = self._total_events * self.slo.budget_fraction
        if allowed_bad == 0:
            return float("inf") if bad_events > 0 else 0.0
        return bad_events / allowed_bad

    @property
    def budget_remaining_fraction(self) -> float:
        return max(0.0, 1.0 - self.budget_consumed_fraction)

    @property
    def budget_remaining_minutes(self) -> float:
        return self.slo.budget_minutes * self.budget_remaining_fraction

    def get_policy(self) -> BudgetPolicy:
        """Determine current operational policy based on budget state."""
        remaining = self.budget_remaining_fraction

        if remaining <= 0.0:
            return BudgetPolicy.EMERGENCY
        elif remaining < 0.25:
            return BudgetPolicy.FREEZE
        elif remaining < 0.50:
            return BudgetPolicy.CAUTION
        else:
            return BudgetPolicy.NORMAL

    def can_deploy(self, risk_level: str = "normal") -> tuple[bool, str]:
        """Gate deployments based on error budget state.

        risk_level: "low" (config change), "normal" (feature),
                    "high" (infra change)
        """
        policy = self.get_policy()

        if policy == BudgetPolicy.EMERGENCY:
            if risk_level == "low":
                return True, "Emergency: only reliability fixes allowed"
            return False, (
                f"BLOCKED: Error budget exhausted. "
                f"Reliability: {self.current_reliability:.4%} "
                f"(target: {self.slo.target:.4%})"
            )

        if policy == BudgetPolicy.FREEZE:
            if risk_level == "high":
                return False, (
                    f"BLOCKED: Budget at {self.budget_remaining_fraction:.1%}. "
                    f"High-risk deploys frozen."
                )
            return True, "Caution: budget low, prefer small safe changes"

        if policy == BudgetPolicy.CAUTION:
            return True, (
                f"OK but budget at {self.budget_remaining_fraction:.1%}. "
                f"Consider batching risky changes."
            )

        return True, "OK: budget healthy"

    def generate_report(self) -> dict:
        """Generate a status report for stakeholders."""
        policy = self.get_policy()
        return {
            "slo": {
                "name": self.slo.name,
                "target": f"{self.slo.target:.3%}",
                "window_days": self.slo.window_days,
            },
            "current": {
                "reliability": f"{self.current_reliability:.4%}",
                "total_events": self._total_events,
                "good_events": self._good_events,
                "bad_events": self._total_events - self._good_events,
            },
            "budget": {
                "total_minutes": round(self.slo.budget_minutes, 1),
                "consumed_fraction": f"{self.budget_consumed_fraction:.1%}",
                "remaining_fraction": f"{self.budget_remaining_fraction:.1%}",
                "remaining_minutes": round(self.budget_remaining_minutes, 1),
            },
            "policy": {
                "current": policy.value,
                "deploy_gate": self.can_deploy("normal")[1],
            },
        }


# ============================================================
# EXAMPLE USAGE
# ============================================================

# Define your SLO
api_slo = SLODefinition(
    name="API Availability",
    target=0.999,       # 99.9%
    window_days=30,
    description="API requests returning non-5xx responses",
)

print(f"Budget: {api_slo.budget_minutes:.1f} minutes over {api_slo.window_days} days")
# Output: Budget: 43.2 minutes over 30 days

manager = ErrorBudgetManager(api_slo)

# Simulate: 1 million requests, 500 failures
manager.record_events(total=1_000_000, good=999_500)

report = manager.generate_report()
print(json.dumps(report, indent=2))

# Check if we can deploy
can_deploy, reason = manager.can_deploy("high")
print(f"Can deploy high-risk change: {can_deploy}")
print(f"Reason: {reason}")


# ============================================================
# CI/CD INTEGRATION EXAMPLE
# ============================================================

def deployment_gate(manager: ErrorBudgetManager,
                     change_type: str) -> bool:
    """Call this in your CI/CD pipeline before deploying."""
    can_deploy, reason = manager.can_deploy(change_type)

    if not can_deploy:
        print(f"DEPLOYMENT BLOCKED: {reason}")
        print("Options:")
        print("  1. Fix reliability issues first")
        print("  2. Get VP approval to override")
        print("  3. Reduce change risk (feature flag, canary)")
        return False

    policy = manager.get_policy()
    if policy in (BudgetPolicy.CAUTION, BudgetPolicy.FREEZE):
        print(f"WARNING: {reason}")
        print("Proceeding with extra monitoring...")
        # Could auto-enable canary deployment here

    return True
```

**Decision framework based on budget state:**

| Budget Remaining | Policy | Deploys | Focus |
|-----------------|--------|---------|-------|
| > 50% | NORMAL | All changes OK | Ship features |
| 25-50% | CAUTION | Prefer safe changes | Monitor closely |
| 1-25% | FREEZE | No high-risk changes | Fix reliability |
| 0% | EMERGENCY | Only reliability fixes | All-hands reliability |

**Practical tips:**

1. **Start with one SLO**: pick your most important user-facing metric (usually API success rate or latency p99)
2. **Budget resets are your friend**: at window boundary, budget resets to 100% -- this naturally allows feature work after reliability improvements
3. **Negotiate with product**: "we have 43 minutes of downtime budget this month" makes reliability concrete for non-engineers
4. **Automate the gate**: put the budget check in CI/CD so it is not a manual decision
5. **Separate SLOs by tier**: your payment API might need 99.99% while your admin dashboard needs 99.5%''',
    ),
    (
        "thinking/error-handling",
        r'''How should I structure a postmortem after a production incident? What should go into it, and how do I make sure the findings actually lead to improvements rather than just being filed away?''',
        r'''<think>
Postmortems -- the user wants a system, not just a document template. My first thought is to provide a Markdown template with sections for timeline, root cause, and action items. But wait, templates alone do not work because people fill them out perfunctorily and the action items never get followed up. The real problem is the PROCESS around the document.

I considered integrating postmortem action items directly into Jira/Linear, but that couples the system to a specific tool. Actually, the better approach is to model the postmortem as structured data (not just free text) with action items that have owners, due dates, and status tracking. The action items can then be exported to whatever project management tool the team uses.

Hmm, there is a tension between thoroughness and overhead. If the postmortem process is too heavy, teams will skip it for "minor" incidents. But minor incidents often share root causes with major ones. I initially thought every incident needs a full postmortem, but actually a tiered approach works better: severity 1-2 get full postmortems with review meetings, severity 3-4 get a lightweight "mini-retro" with just root cause and one action item.

The blameless language aspect is critical but hard to enforce with code. What I can do is provide the template with blameless prompts ("What systems/processes allowed this to happen?" rather than "Who caused this?") and flag action items that reference individuals instead of systems. Since the goal is systemic improvement, every action item should change a system, process, or tool -- never "tell Bob to be more careful."
</think>

A good postmortem process combines a structured document with an action tracking system. Here is both:

```python
import json
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# ============================================================
# POSTMORTEM DATA MODEL
# ============================================================

class Severity(Enum):
    SEV1 = "sev1"  # Complete outage, revenue impact
    SEV2 = "sev2"  # Partial outage, degraded experience
    SEV3 = "sev3"  # Minor issue, limited user impact


class ActionStatus(Enum):
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    WONT_DO = "wont_do"


class ActionType(Enum):
    PREVENT = "prevent"      # Stop this from happening again
    DETECT = "detect"        # Catch it faster next time
    MITIGATE = "mitigate"    # Reduce impact when it happens
    PROCESS = "process"      # Improve team response


@dataclass
class TimelineEntry:
    timestamp: str          # "2025-01-15 14:32 UTC"
    description: str        # What happened
    actor: str              # Who/what did it (system or person)
    evidence: str = ""      # Link to log, metric, or screenshot


@dataclass
class ActionItem:
    description: str
    action_type: ActionType
    owner: str
    priority: str           # P0, P1, P2
    status: ActionStatus = ActionStatus.TODO
    ticket_url: str = ""
    due_date: str = ""
    completed_date: str = ""


@dataclass
class Postmortem:
    # Header
    title: str
    incident_id: str
    severity: Severity
    date: str
    duration_minutes: int
    authors: list[str]

    # Impact
    user_impact: str             # What users experienced
    revenue_impact: str          # Estimated financial impact
    affected_services: list[str]
    affected_users_count: int

    # Summary (2-3 sentences)
    summary: str

    # Root cause analysis
    root_cause: str              # Technical root cause
    contributing_factors: list[str]  # Things that made it worse
    trigger: str                 # What initiated the incident

    # Timeline
    timeline: list[TimelineEntry] = field(default_factory=list)

    # What went well / what did not
    went_well: list[str] = field(default_factory=list)
    went_poorly: list[str] = field(default_factory=list)
    got_lucky: list[str] = field(default_factory=list)

    # Action items
    action_items: list[ActionItem] = field(default_factory=list)

    def add_action(self, description: str, action_type: ActionType,
                    owner: str, priority: str = "P1") -> ActionItem:
        item = ActionItem(
            description=description,
            action_type=action_type,
            owner=owner,
            priority=priority,
        )
        self.action_items.append(item)
        return item

    def completion_rate(self) -> float:
        if not self.action_items:
            return 1.0
        done = sum(
            1 for a in self.action_items
            if a.status in (ActionStatus.DONE, ActionStatus.WONT_DO)
        )
        return done / len(self.action_items)

    def overdue_actions(self, current_date: str) -> list[ActionItem]:
        return [
            a for a in self.action_items
            if a.status == ActionStatus.TODO
            and a.due_date
            and a.due_date < current_date
        ]


# ============================================================
# EXAMPLE POSTMORTEM
# ============================================================

pm = Postmortem(
    title="Payment Processing Outage",
    incident_id="INC-2025-042",
    severity=Severity.SEV1,
    date="2025-01-15",
    duration_minutes=47,
    authors=["alice", "bob"],
    user_impact="Users could not complete purchases for 47 minutes",
    revenue_impact="Estimated $23,000 in lost transactions",
    affected_services=["payment-service", "checkout-api", "order-service"],
    affected_users_count=3200,
    summary=(
        "A database connection pool exhaustion in payment-service caused "
        "all payment requests to timeout. The issue was triggered by a "
        "slow query introduced in deploy v2.14.3 and amplified by missing "
        "connection timeout configuration."
    ),
    root_cause=(
        "Deploy v2.14.3 added a new payment reconciliation query that "
        "performed a full table scan on the transactions table (12M rows). "
        "Each query held a connection for 30+ seconds, exhausting the "
        "pool of 20 connections within 2 minutes of the deploy."
    ),
    contributing_factors=[
        "No query performance review in the PR process",
        "Connection pool size was default (20), not tuned for load",
        "No connection acquisition timeout -- threads waited indefinitely",
        "Canary deployment was not configured for this service",
        "No alert on connection pool utilization",
    ],
    trigger="Deployment of payment-service v2.14.3 at 14:30 UTC",
)

# Timeline
pm.timeline = [
    TimelineEntry("14:30", "payment-service v2.14.3 deployed", "deploy-bot"),
    TimelineEntry("14:32", "Connection pool utilization hits 100%", "system",
                  "grafana.com/d/abc123"),
    TimelineEntry("14:35", "First user reports checkout failures", "support"),
    TimelineEntry("14:38", "Error rate alert fires (>5% 5xx)", "pagerduty"),
    TimelineEntry("14:40", "On-call engineer acknowledges page", "alice"),
    TimelineEntry("14:45", "Root cause identified: pool exhaustion", "alice",
                  "Checked connection pool metrics in Grafana"),
    TimelineEntry("14:52", "Decision to rollback v2.14.3", "alice"),
    TimelineEntry("14:55", "Rollback initiated", "alice"),
    TimelineEntry("15:05", "Rollback complete, connections recovering", "system"),
    TimelineEntry("15:17", "All metrics nominal, incident resolved", "alice"),
]

pm.went_well = [
    "Error rate alert fired within 6 minutes",
    "On-call responded within 2 minutes of page",
    "Rollback procedure worked smoothly",
    "Team communicated clearly in incident channel",
]

pm.went_poorly = [
    "No canary deployment -- 100% of traffic hit bad code immediately",
    "Took 13 minutes from alert to rollback decision",
    "No connection pool monitoring dashboard existed",
    "Slow query was not caught in code review",
]

pm.got_lucky = [
    "The on-call engineer had recently debugged a similar pool issue",
    "The deploy happened during business hours, not at 3 AM",
]

# Action items -- each one is specific, assigned, and typed
pm.add_action(
    "Add connection pool utilization alert (>80% for 1 min)",
    ActionType.DETECT, owner="alice", priority="P0",
)
pm.add_action(
    "Set connection acquisition timeout to 5 seconds",
    ActionType.MITIGATE, owner="bob", priority="P0",
)
pm.add_action(
    "Enable canary deployment for payment-service",
    ActionType.PREVENT, owner="charlie", priority="P1",
)
pm.add_action(
    "Add EXPLAIN ANALYZE check to CI for new queries",
    ActionType.PREVENT, owner="alice", priority="P1",
)
pm.add_action(
    "Increase connection pool to 50, add pool metrics to dashboard",
    ActionType.MITIGATE, owner="bob", priority="P1",
)
pm.add_action(
    "Add query timeout of 10 seconds to database config",
    ActionType.MITIGATE, owner="bob", priority="P0",
)
pm.add_action(
    "Schedule quarterly game day to practice incident response",
    ActionType.PROCESS, owner="charlie", priority="P2",
)


# ============================================================
# ACTION ITEM TRACKING
# ============================================================

class PostmortemTracker:
    """Tracks postmortem action items across all incidents."""

    def __init__(self):
        self._postmortems: list[Postmortem] = []

    def add(self, pm: Postmortem):
        self._postmortems.append(pm)

    def overdue_report(self, current_date: str) -> list[dict]:
        results = []
        for pm in self._postmortems:
            overdue = pm.overdue_actions(current_date)
            if overdue:
                results.append({
                    "incident": pm.incident_id,
                    "overdue_count": len(overdue),
                    "items": [
                        {"desc": a.description, "owner": a.owner,
                         "due": a.due_date}
                        for a in overdue
                    ],
                })
        return results

    def completion_summary(self) -> dict:
        total = 0
        done = 0
        by_type = {}
        for pm in self._postmortems:
            for a in pm.action_items:
                total += 1
                type_name = a.action_type.value
                by_type.setdefault(type_name, {"total": 0, "done": 0})
                by_type[type_name]["total"] += 1
                if a.status == ActionStatus.DONE:
                    done += 1
                    by_type[type_name]["done"] += 1

        return {
            "total_actions": total,
            "completed": done,
            "completion_rate": f"{done/max(total,1)*100:.0f}%",
            "by_type": by_type,
        }
```

**The postmortem process that makes it stick:**

1. **Write within 48 hours** while memory is fresh -- assign an author during incident resolution
2. **Blameless language**: say "the deploy introduced a slow query" not "Bob deployed bad code"
3. **Every action item needs**: owner, priority, due date, and a tracking ticket
4. **Classify actions** as PREVENT/DETECT/MITIGATE/PROCESS -- if all your actions are MITIGATE, you are not fixing root causes
5. **Weekly review**: track overdue action items in team standup -- untracked items never get done
6. **Quarterly retro**: review all postmortems to find systemic patterns (e.g., "60% of incidents involve database changes")
7. **Share broadly**: postmortems are learning documents -- other teams should read them to avoid the same mistakes''',
    ),
]
