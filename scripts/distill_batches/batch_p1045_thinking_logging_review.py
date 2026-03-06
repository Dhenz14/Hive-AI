r"""Thinking-trace pairs: logging and observability code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this logging implementation and identify issues:

```python
import logging
import json
import time
import traceback
import os
from datetime import datetime

LOG_FILE = "app.log"
ERROR_LOG = "errors.log"

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    filename=LOG_FILE
)

logger = logging.getLogger("myapp")

error_handler = logging.FileHandler(ERROR_LOG)
error_handler.setLevel(logging.ERROR)
logger.addHandler(error_handler)

class RequestLogger:
    def log_request(self, request, response, duration):
        logger.info(
            f"Request: {request.method} {request.path} "
            f"Status: {response.status_code} "
            f"Duration: {duration:.3f}s "
            f"IP: {request.remote_addr} "
            f"User-Agent: {request.headers.get('User-Agent')} "
            f"Body: {request.get_data(as_text=True)} "
            f"Response: {response.get_data(as_text=True)}"
        )

    def log_error(self, request, error):
        logger.error(
            f"Error: {request.method} {request.path} "
            f"Error: {str(error)} "
            f"Traceback: {traceback.format_exc()} "
            f"Headers: {dict(request.headers)} "
            f"Body: {request.get_data(as_text=True)}"
        )

    def log_db_query(self, query, params, duration):
        logger.debug(
            f"SQL: {query} Params: {params} Duration: {duration:.3f}s"
        )

    def log_external_call(self, service, endpoint, duration, status):
        logger.info(
            f"External: {service} {endpoint} "
            f"Status: {status} Duration: {duration:.3f}s"
        )

class MetricsCollector:
    def __init__(self):
        self.metrics = {}

    def increment(self, name, value=1, tags=None):
        key = f"{name}:{json.dumps(tags or {}, sort_keys=True)}"
        if key not in self.metrics:
            self.metrics[key] = 0
        self.metrics[key] += value

    def gauge(self, name, value, tags=None):
        key = f"{name}:{json.dumps(tags or {}, sort_keys=True)}"
        self.metrics[key] = value

    def timing(self, name, duration, tags=None):
        key = f"{name}:{json.dumps(tags or {}, sort_keys=True)}"
        if key not in self.metrics:
            self.metrics[key] = []
        self.metrics[key].append(duration)

    def flush(self):
        for key, value in self.metrics.items():
            if isinstance(value, list):
                avg = sum(value) / len(value) if value else 0
                logger.info(f"METRIC {key} avg={avg:.3f} count={len(value)}")
            else:
                logger.info(f"METRIC {key} value={value}")
        self.metrics = {}

    def get_summary(self):
        summary = {}
        for key, value in self.metrics.items():
            if isinstance(value, list):
                summary[key] = {
                    "count": len(value),
                    "avg": sum(value) / len(value),
                    "min": min(value),
                    "max": max(value)
                }
            else:
                summary[key] = {"value": value}
        return summary

class AlertManager:
    def __init__(self, thresholds):
        self.thresholds = thresholds
        self.alert_history = []

    def check(self, metric_name, value):
        threshold = self.thresholds.get(metric_name)
        if threshold and value > threshold:
            alert = {
                "metric": metric_name,
                "value": value,
                "threshold": threshold,
                "time": datetime.now().isoformat()
            }
            self.alert_history.append(alert)
            logger.critical(
                f"ALERT: {metric_name} = {value} exceeds {threshold}"
            )
            self._send_alert(alert)

    def _send_alert(self, alert):
        import requests
        try:
            requests.post(
                "https://alerts.example.com/webhook",
                json=alert,
                timeout=5
            )
        except Exception:
            pass
```''', r'''<think>
Let me analyze this logging and metrics implementation.

Logging issues:

1. logging.basicConfig with filename=LOG_FILE sends all output to a file. No console output. In development and containerized environments, stdout/stderr logging is essential.

2. DEBUG level globally. In production, this generates enormous log volumes. DEBUG should only be enabled for specific loggers during troubleshooting.

3. No log rotation. LOG_FILE and ERROR_LOG grow without limit until disk is full.

4. log_request logs request body and response body. This is a CRITICAL security issue - passwords, tokens, credit card numbers, PII will all appear in logs.

5. log_error logs all headers (including Authorization, Cookie) and request body. Same security concern.

6. log_db_query logs SQL parameters which could contain PII (email, SSN in WHERE clauses).

7. No structured logging - everything is concatenated into a single string. Log aggregation tools (ELK, Splunk) cannot parse individual fields without regex.

8. error_handler is added to the "myapp" logger but basicConfig was configured on the root logger. The error_handler will only capture errors logged by "myapp" logger, not from other modules.

MetricsCollector:

9. In-memory metrics storage. In a multi-process deployment, each process has its own metrics. Aggregation across processes is impossible.

10. Not thread-safe. self.metrics is modified by multiple threads without locking.

11. timing() stores all raw values in a list. For high-throughput services, this list grows unboundedly between flushes.

12. flush() logs metrics via logger.info. Metrics should go to a dedicated metrics backend (Prometheus, StatsD, Datadog), not the application log.

13. get_summary() calls sum(value) / len(value) for averages. If value is empty, this raises ZeroDivisionError (though the condition checks, min/max on empty list will raise ValueError).

14. flush() resets self.metrics = {} which is not atomic. A metric could be recorded between the iteration and the reset, losing that data point.

AlertManager:

15. alert_history grows without limit - memory leak.

16. _send_alert silently swallows all exceptions. Alert delivery failures are invisible.

17. No alert deduplication or cooldown. The same alert fires on every check. A metric that stays above threshold triggers continuous alerts.

18. Importing requests inside _send_alert on every call is unusual (though not a bug).

19. check() only supports "greater than" comparison. No support for "less than" thresholds or rate-of-change alerts.
</think>

## Code Review: Logging and Observability

### CRITICAL - Sensitive Data Logged in Plaintext
`log_request` logs request body (passwords, credit cards), response body (tokens, PII), and User-Agent. `log_error` logs all headers (Authorization tokens, session cookies) and request body. This creates a massive compliance and security liability.

**Fix:** Sanitize sensitive data before logging:
```python
SENSITIVE_FIELDS = {"password", "token", "credit_card", "ssn", "authorization", "cookie"}

def _sanitize(self, data):
    if isinstance(data, dict):
        return {
            k: "***" if k.lower() in SENSITIVE_FIELDS else self._sanitize(v)
            for k, v in data.items()
        }
    return data

def log_request(self, request, response, duration):
    logger.info(json.dumps({
        "method": request.method,
        "path": request.path,
        "status": response.status_code,
        "duration_ms": round(duration * 1000, 2),
        "ip": request.remote_addr,
    }))
```

### HIGH - No Log Rotation (Disk Exhaustion)
`LOG_FILE` and `ERROR_LOG` are plain `FileHandler` outputs with no rotation. On a busy server, these files grow until the disk is full, crashing the application and potentially the host.

**Fix:**
```python
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    LOG_FILE, maxBytes=50*1024*1024, backupCount=5
)
```

### HIGH - DEBUG Level in Production
`logging.basicConfig(level=logging.DEBUG)` generates enormous log volumes in production. Every SQL query, every internal function call produces a log line. This wastes disk space, slows I/O, and makes finding real issues difficult.

**Fix:** Use WARNING or INFO for production, configure per-logger:
```python
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("myapp")
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
```

### HIGH - No Structured Logging
All log messages are concatenated strings: `f"Request: {method} {path} Status: {status}"`. Log aggregation tools cannot parse individual fields without fragile regex patterns.

**Fix:** Use JSON structured logging:
```python
import json_log_formatter

formatter = json_log_formatter.JSONFormatter()
handler.setFormatter(formatter)

logger.info("request_completed", extra={
    "method": request.method,
    "path": request.path,
    "status": response.status_code,
    "duration_ms": duration * 1000
})
```

### HIGH - In-Memory Metrics Not Aggregatable
`MetricsCollector` stores metrics in process memory. In a multi-process deployment (gunicorn with 4 workers), each worker has its own metrics. Total request counts, average response times, and error rates are fragmented and inaccurate.

**Fix:** Use a proper metrics backend:
```python
from prometheus_client import Counter, Histogram

REQUEST_COUNT = Counter("http_requests_total", "Total requests", ["method", "path", "status"])
REQUEST_DURATION = Histogram("http_request_duration_seconds", "Request duration")
```

### MEDIUM - Unbounded Timing Data
`timing()` appends every duration to a list. Between flushes, this list grows without limit. A service handling 1000 requests/second accumulates 3.6 million entries per hour.

**Fix:** Use a fixed-size reservoir sample or streaming statistics (running mean, variance).

### MEDIUM - Alert Flooding (No Cooldown)
`AlertManager.check()` fires an alert every time a metric exceeds the threshold. A metric that stays above threshold triggers an alert on every check interval, flooding the alert channel and causing alert fatigue.

**Fix:** Add cooldown period:
```python
def check(self, metric_name, value):
    if metric_name in self.last_alert_time:
        if time.time() - self.last_alert_time[metric_name] < self.cooldown:
            return
    # ... fire alert
    self.last_alert_time[metric_name] = time.time()
```

### MEDIUM - Alert Delivery Failure Silently Swallowed
`_send_alert` catches all exceptions with `pass`. If the webhook URL is wrong or the service is down, alerts are never delivered and no one knows.

### MEDIUM - MetricsCollector Not Thread-Safe
`self.metrics` is modified from multiple threads without locking. Concurrent increments can lose updates.

### LOW - No Console Output
`basicConfig(filename=LOG_FILE)` sends all output to a file only. In containerized environments (Docker, Kubernetes), applications should log to stdout/stderr for log aggregation.'''),

    ("thinking/code-review", r'''Review this distributed tracing implementation:

```python
import uuid
import time
import json
import logging
import threading
from contextlib import contextmanager
from typing import Optional, Dict, List

logger = logging.getLogger(__name__)

class Span:
    def __init__(self, name: str, trace_id: str, parent_id: Optional[str] = None):
        self.name = name
        self.trace_id = trace_id
        self.span_id = str(uuid.uuid4())[:8]
        self.parent_id = parent_id
        self.start_time = time.time()
        self.end_time = None
        self.tags: Dict[str, str] = {}
        self.logs: List[Dict] = []
        self.status = "ok"

    def set_tag(self, key: str, value: str):
        self.tags[key] = value

    def log(self, message: str, **kwargs):
        self.logs.append({
            "timestamp": time.time(),
            "message": message,
            **kwargs
        })

    def finish(self):
        self.end_time = time.time()

    def duration_ms(self):
        if self.end_time:
            return (self.end_time - self.start_time) * 1000
        return (time.time() - self.start_time) * 1000

    def to_dict(self):
        return {
            "name": self.name,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "parent_id": self.parent_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": self.duration_ms(),
            "tags": self.tags,
            "logs": self.logs,
            "status": self.status
        }

_current_span = threading.local()

class Tracer:
    def __init__(self):
        self.spans = []
        self.exporters = []

    def start_span(self, name: str, trace_id: Optional[str] = None) -> Span:
        parent = getattr(_current_span, "span", None)

        if trace_id is None:
            trace_id = parent.trace_id if parent else str(uuid.uuid4())

        span = Span(
            name=name,
            trace_id=trace_id,
            parent_id=parent.span_id if parent else None
        )

        _current_span.span = span
        self.spans.append(span)
        return span

    def end_span(self, span: Span):
        span.finish()
        _current_span.span = None

        for exporter in self.exporters:
            try:
                exporter.export(span)
            except Exception:
                pass

    @contextmanager
    def trace(self, name: str, trace_id: Optional[str] = None):
        span = self.start_span(name, trace_id)
        try:
            yield span
        except Exception as e:
            span.status = "error"
            span.set_tag("error.message", str(e))
            span.set_tag("error.type", type(e).__name__)
            raise
        finally:
            self.end_span(span)

    def add_exporter(self, exporter):
        self.exporters.append(exporter)

class ConsoleExporter:
    def export(self, span: Span):
        logger.info(json.dumps(span.to_dict()))

class HttpExporter:
    def __init__(self, endpoint: str):
        self.endpoint = endpoint
        self.buffer = []
        self.buffer_size = 100

    def export(self, span: Span):
        self.buffer.append(span.to_dict())
        if len(self.buffer) >= self.buffer_size:
            self.flush()

    def flush(self):
        if not self.buffer:
            return
        import requests
        try:
            requests.post(
                self.endpoint,
                json={"spans": self.buffer},
                timeout=5
            )
            self.buffer = []
        except Exception as e:
            logger.error(f"Failed to export spans: {e}")

tracer = Tracer()

def trace_middleware(app):
    def middleware(request):
        trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
        with tracer.trace("http_request", trace_id=trace_id) as span:
            span.set_tag("http.method", request.method)
            span.set_tag("http.url", request.path)
            response = app(request)
            span.set_tag("http.status", str(response.status_code))
            return response
    return middleware
```''', r'''<think>
Let me analyze this distributed tracing implementation.

Span ID:
- span_id uses str(uuid.uuid4())[:8] which truncates the UUID to 8 characters. This is only 32 bits of entropy, giving a collision probability of about 1 in 4 billion. In a high-throughput system generating millions of spans, collisions become likely.

Thread-local span management:
- _current_span stores the current span in thread-local storage. end_span sets it to None. This breaks span nesting: if span A starts span B, and span B ends, _current_span is set to None instead of being restored to span A. Parent-child relationships within a thread are lost after the first child span ends.

Tracer.spans:
- self.spans is an unbounded list that stores ALL spans ever created. In a production service, this is a severe memory leak. Thousands of spans per second will exhaust memory within minutes.
- Not thread-safe. Multiple threads appending to self.spans can cause corruption.

HttpExporter:
- self.buffer is not thread-safe. Multiple threads calling export() simultaneously can corrupt the buffer.
- flush() is not atomic: after sending, self.buffer = [] loses any spans added between the send and the reset.
- If flush() fails, spans remain in the buffer and are retried on the next flush. But there is no limit on buffer size during failures, so memory grows unboundedly.
- buffer_size of 100 means spans are held in memory until 100 accumulate. In low-traffic periods, spans may never be flushed.

Exporter error handling:
- end_span catches all exporter exceptions with pass. If an exporter fails, spans are silently dropped. No retry, no fallback storage.

Context propagation:
- trace_middleware reads X-Trace-ID header but doesn't propagate it to outgoing requests. The trace breaks at service boundaries.
- No support for propagation standards like W3C TraceContext or B3 headers.

Missing:
- No sampling strategy. Every request is traced, which is expensive in production.
- No span kind (server, client, producer, consumer).
- No service name in spans.
- No rate limiting on span creation.
- No periodic flush for HttpExporter (only flushes when buffer is full).
</think>

## Code Review: Distributed Tracing Implementation

### CRITICAL - Broken Span Nesting
`end_span` sets `_current_span.span = None` regardless of nesting level. If span A starts child span B, and span B ends, the current span becomes None instead of reverting to span A. All subsequent spans in the request have no parent, breaking the trace tree.

**Fix:** Maintain a span stack:
```python
def start_span(self, name, trace_id=None):
    parent = getattr(_current_span, "span", None)
    # ...
    if not hasattr(_current_span, "stack"):
        _current_span.stack = []
    _current_span.stack.append(parent)
    _current_span.span = span
    return span

def end_span(self, span):
    span.finish()
    stack = getattr(_current_span, "stack", [])
    _current_span.span = stack.pop() if stack else None
```

### CRITICAL - Unbounded Span List (Memory Leak)
`self.spans.append(span)` stores every span ever created in memory. A service handling 1000 requests/second with 5 spans per request accumulates 5000 Span objects per second, exhausting memory within hours.

**Fix:** Remove the spans list entirely. Spans should be exported and discarded, not accumulated:
```python
def end_span(self, span):
    span.finish()
    _current_span.span = None
    for exporter in self.exporters:
        exporter.export(span)
```

### HIGH - HttpExporter Buffer Not Thread-Safe
Multiple threads call `export()` simultaneously, appending to `self.buffer` without synchronization. The `flush()` method is also not atomic -- spans added between `requests.post()` and `self.buffer = []` are lost.

**Fix:**
```python
import threading

class HttpExporter:
    def __init__(self, endpoint, buffer_size=100):
        self.endpoint = endpoint
        self.buffer = []
        self.buffer_size = buffer_size
        self._lock = threading.Lock()

    def export(self, span):
        with self._lock:
            self.buffer.append(span.to_dict())
            if len(self.buffer) >= self.buffer_size:
                batch = self.buffer
                self.buffer = []
        if batch:
            self._send(batch)
```

### HIGH - Truncated Span IDs Risk Collisions
`str(uuid.uuid4())[:8]` produces only 8 hex characters (32 bits of entropy). With millions of spans, collision probability becomes significant (birthday paradox: ~50% chance at ~65,000 spans). Colliding span IDs corrupt trace trees.

**Fix:** Use the full UUID or at least 16 characters:
```python
self.span_id = uuid.uuid4().hex  # Full 32 hex chars
```

### HIGH - No Periodic Flush in HttpExporter
Spans are only flushed when the buffer reaches 100 entries. During low-traffic periods, spans sit in memory indefinitely and are never exported. On application shutdown, buffered spans are lost.

**Fix:** Add a periodic flush timer:
```python
def __init__(self, endpoint, buffer_size=100, flush_interval=10):
    # ...
    self._flush_timer = threading.Timer(flush_interval, self._periodic_flush)
    self._flush_timer.daemon = True
    self._flush_timer.start()
```

### MEDIUM - No Trace Sampling
Every request is traced, which is expensive in production. For high-throughput services, 100% tracing creates excessive overhead in span creation, export, and storage.

**Fix:** Implement probability-based sampling:
```python
import random

class Tracer:
    def __init__(self, sample_rate=0.1):
        self.sample_rate = sample_rate

    def start_span(self, name, trace_id=None):
        if random.random() > self.sample_rate:
            return NoOpSpan()  # Lightweight no-op
```

### MEDIUM - No Outgoing Context Propagation
`trace_middleware` reads the incoming `X-Trace-ID` header but does not propagate it to outgoing HTTP requests. Traces break at service boundaries.

**Fix:** Instrument the HTTP client to inject trace headers:
```python
def traced_request(method, url, **kwargs):
    span = getattr(_current_span, "span", None)
    if span:
        headers = kwargs.setdefault("headers", {})
        headers["X-Trace-ID"] = span.trace_id
        headers["X-Parent-Span-ID"] = span.span_id
    return requests.request(method, url, **kwargs)
```

### MEDIUM - Exporter Failures Silently Drop Spans
`end_span` catches all exporter exceptions with `pass`. Failed exports are permanent data loss with no logging or retry.

### LOW - No Service Name in Spans
Spans lack a `service` field. In a microservices environment, it is impossible to identify which service generated a span without this metadata.'''),

    ("thinking/code-review", r'''Review this health check and monitoring endpoint code:

```python
from flask import Flask, jsonify
import psutil
import time
import os
import redis
import psycopg2
from datetime import datetime

app = Flask(__name__)

@app.route("/health")
def health_check():
    return jsonify({"status": "ok"})

@app.route("/health/detailed")
def detailed_health():
    checks = {}

    # Database check
    try:
        conn = psycopg2.connect(os.environ["DATABASE_URL"])
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        cursor.close()
        conn.close()
        checks["database"] = {"status": "ok"}
    except Exception as e:
        checks["database"] = {"status": "error", "message": str(e)}

    # Redis check
    try:
        r = redis.from_url(os.environ["REDIS_URL"])
        r.ping()
        checks["redis"] = {"status": "ok"}
    except Exception as e:
        checks["redis"] = {"status": "error", "message": str(e)}

    # Disk check
    disk = psutil.disk_usage("/")
    checks["disk"] = {
        "status": "ok" if disk.percent < 90 else "warning",
        "percent_used": disk.percent,
        "free_gb": disk.free / (1024 ** 3)
    }

    # Memory check
    mem = psutil.virtual_memory()
    checks["memory"] = {
        "status": "ok" if mem.percent < 90 else "warning",
        "percent_used": mem.percent,
        "available_mb": mem.available / (1024 ** 2)
    }

    # CPU check
    cpu_percent = psutil.cpu_percent(interval=1)
    checks["cpu"] = {
        "status": "ok" if cpu_percent < 80 else "warning",
        "percent": cpu_percent
    }

    overall = "ok"
    for check in checks.values():
        if check["status"] == "error":
            overall = "error"
            break
        if check["status"] == "warning":
            overall = "warning"

    return jsonify({
        "status": overall,
        "checks": checks,
        "timestamp": datetime.now().isoformat(),
        "hostname": os.uname().nodename,
        "pid": os.getpid(),
        "uptime": time.time() - START_TIME
    })

@app.route("/metrics")
def metrics():
    process = psutil.Process()

    return jsonify({
        "process": {
            "cpu_percent": process.cpu_percent(),
            "memory_mb": process.memory_info().rss / (1024 ** 2),
            "threads": process.num_threads(),
            "open_files": len(process.open_files()),
            "connections": len(process.connections()),
        },
        "system": {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage("/").percent,
            "load_avg": os.getloadavg(),
        },
        "app": {
            "request_count": REQUEST_COUNT,
            "error_count": ERROR_COUNT,
            "avg_response_time": sum(RESPONSE_TIMES) / len(RESPONSE_TIMES) if RESPONSE_TIMES else 0,
        }
    })

@app.route("/debug/config")
def debug_config():
    return jsonify({
        "environment": os.environ.get("FLASK_ENV"),
        "database_url": os.environ.get("DATABASE_URL"),
        "redis_url": os.environ.get("REDIS_URL"),
        "secret_key": app.config.get("SECRET_KEY"),
        "debug": app.debug,
        "all_env": dict(os.environ)
    })

START_TIME = time.time()
REQUEST_COUNT = 0
ERROR_COUNT = 0
RESPONSE_TIMES = []
```''', r'''<think>
Let me analyze these health check and monitoring endpoints.

Security - CRITICAL:

1. /debug/config exposes:
   - DATABASE_URL (with password)
   - REDIS_URL (with password if configured)
   - SECRET_KEY (allows forging sessions/tokens)
   - ALL environment variables (dict(os.environ)) which may include AWS keys, API tokens, etc.
   This is an information disclosure vulnerability of the highest severity. If this endpoint is accessible in production (no authentication), anyone can extract all secrets.

2. /health/detailed includes error messages from database and Redis connection failures. These could reveal connection strings, hostnames, and internal network topology.

Performance issues:

3. CPU check uses psutil.cpu_percent(interval=1) which BLOCKS for 1 second to measure CPU usage. The health check endpoint takes at least 1 second to respond, which is unacceptable for load balancer health checks that expect sub-second responses.

4. /health/detailed creates a new database connection and Redis connection on every call. If the health check is called frequently (every 5-10 seconds per load balancer), this adds connection overhead. The connections should be pooled or reused.

Reliability:

5. If the database check hangs (connection timeout), the entire health check blocks. No timeout on the database connection attempt.

6. /health returns 200 with {"status": "ok"} regardless of actual system health. This is the endpoint load balancers typically use, but it provides no value if it always returns OK.

7. RESPONSE_TIMES is a global list that grows unboundedly. No size limit, no time windowing.

8. Global variables REQUEST_COUNT, ERROR_COUNT, RESPONSE_TIMES are not thread-safe. Multiple concurrent requests incrementing these values can lose updates.

9. START_TIME is undefined for the /health/detailed endpoint reference (it is defined at module level, which is fine).

10. /metrics endpoint exposes process.open_files() and process.connections() which could reveal internal file paths and network connections.

11. /health/detailed overall status logic: if any check is "error", overall is "error." But the HTTP status code is always 200. Load balancers need non-200 status codes to detect unhealthy instances.

Missing:
- No authentication on any endpoint
- No readiness vs liveness distinction
- No graceful degradation (if Redis is down, is the app still functional?)
</think>

## Code Review: Health Check and Monitoring Endpoints

### CRITICAL - /debug/config Exposes All Secrets
The `/debug/config` endpoint returns `DATABASE_URL` (with password), `SECRET_KEY`, and `dict(os.environ)` (ALL environment variables including AWS keys, API tokens, and any other secrets). This endpoint has no authentication. Anyone who discovers it can extract every secret in the application.

**Fix:** Remove this endpoint entirely. Debug information should only be available through authenticated internal tools:
```python
# DELETE THIS ENTIRE ENDPOINT
# If debugging is needed, use a secure internal admin panel with authentication
```

### CRITICAL - Health Check Blocks for 1 Second
`psutil.cpu_percent(interval=1)` blocks the request thread for 1 full second to measure CPU usage. Load balancers typically expect health check responses within 100-500ms. A 1-second response time can cause the load balancer to mark the instance as unhealthy.

**Fix:** Use `psutil.cpu_percent(interval=None)` which returns the CPU usage since the last call (non-blocking), or cache the value and update it asynchronously:
```python
cpu_percent = psutil.cpu_percent(interval=None)  # Non-blocking
```

### HIGH - Health Check Always Returns HTTP 200
`/health/detailed` returns the overall status in the JSON body but always responds with HTTP 200. Load balancers and orchestrators (Kubernetes, ECS) check the HTTP status code, not the response body. An unhealthy service appears healthy to the infrastructure.

**Fix:**
```python
status_code = 200 if overall == "ok" else 503 if overall == "error" else 200
return jsonify({...}), status_code
```

### HIGH - New Connections Created on Every Health Check
`detailed_health` creates a new `psycopg2.connect()` and `redis.from_url()` on every invocation. With health checks running every 5-10 seconds from multiple load balancers, this creates significant connection churn.

**Fix:** Use the application's existing connection pool or maintain a dedicated health check connection.

### HIGH - Error Messages Expose Internal Details
`"message": str(e)` for database and Redis failures can reveal connection strings, hostnames, IP addresses, and internal network topology.

**Fix:** Return generic status without detailed error messages:
```python
checks["database"] = {"status": "error"}
logger.error(f"Health check database failure: {e}")  # Log internally only
```

### MEDIUM - Unbounded RESPONSE_TIMES List
`RESPONSE_TIMES` is a global list that grows without limit. A service handling 1000 requests/second accumulates 86 million entries per day, eventually exhausting memory.

**Fix:** Use a fixed-size circular buffer:
```python
from collections import deque
RESPONSE_TIMES = deque(maxlen=1000)
```

### MEDIUM - Global Counters Not Thread-Safe
`REQUEST_COUNT`, `ERROR_COUNT`, and `RESPONSE_TIMES` are modified by concurrent request threads without locking. Increments can be lost.

**Fix:** Use `threading.Lock` or atomic counters.

### MEDIUM - No Separate Liveness and Readiness Checks
Kubernetes and modern orchestrators distinguish between liveness (is the process alive?) and readiness (can it serve traffic?). The basic `/health` endpoint should be liveness (always fast, minimal checks). A separate `/ready` endpoint should verify dependencies.

### MEDIUM - No Authentication on Monitoring Endpoints
`/metrics` exposes process details including open files and network connections. `/health/detailed` shows internal architecture. These should require authentication or be restricted to internal networks.

### LOW - No Database Connection Timeout
The `psycopg2.connect()` call has no timeout. If the database is unreachable, the health check hangs indefinitely.

**Fix:**
```python
conn = psycopg2.connect(os.environ["DATABASE_URL"], connect_timeout=3)
```'''),

    ("thinking/code-review", r'''Review this log aggregation and analysis code:

```python
import re
import json
import gzip
from datetime import datetime, timedelta
from collections import Counter, defaultdict
from typing import List, Dict, Optional

class LogParser:
    LOG_PATTERN = re.compile(
        r'(?P<timestamp>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) '
        r'(?P<level>\w+) '
        r'(?P<logger>\S+) '
        r'(?P<message>.*)'
    )

    def parse_line(self, line: str) -> Optional[Dict]:
        match = self.LOG_PATTERN.match(line)
        if match:
            return match.groupdict()
        return None

    def parse_file(self, filepath: str) -> List[Dict]:
        entries = []
        with open(filepath) as f:
            for line in f:
                entry = self.parse_line(line.strip())
                if entry:
                    entries.append(entry)
        return entries

    def parse_json_logs(self, filepath: str) -> List[Dict]:
        entries = []
        with open(filepath) as f:
            for line in f:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return entries

class LogAnalyzer:
    def __init__(self, parser: LogParser):
        self.parser = parser
        self.entries = []

    def load(self, filepath: str):
        if filepath.endswith(".gz"):
            with gzip.open(filepath, "rt") as f:
                content = f.read()
                for line in content.split("\n"):
                    entry = self.parser.parse_line(line)
                    if entry:
                        self.entries.append(entry)
        elif filepath.endswith(".json") or filepath.endswith(".jsonl"):
            self.entries.extend(self.parser.parse_json_logs(filepath))
        else:
            self.entries.extend(self.parser.parse_file(filepath))

    def error_summary(self) -> Dict:
        errors = [e for e in self.entries if e.get("level") == "ERROR"]
        error_messages = Counter(e.get("message", "")[:100] for e in errors)
        return {
            "total_errors": len(errors),
            "unique_errors": len(error_messages),
            "top_errors": error_messages.most_common(10)
        }

    def response_time_analysis(self) -> Dict:
        times = []
        for entry in self.entries:
            if "duration_ms" in entry:
                times.append(float(entry["duration_ms"]))

        if not times:
            return {"error": "No response time data"}

        times.sort()
        return {
            "count": len(times),
            "avg": sum(times) / len(times),
            "p50": times[len(times) // 2],
            "p95": times[int(len(times) * 0.95)],
            "p99": times[int(len(times) * 0.99)],
            "max": times[-1]
        }

    def find_slow_requests(self, threshold_ms: float = 1000) -> List[Dict]:
        return [
            e for e in self.entries
            if "duration_ms" in e and float(e["duration_ms"]) > threshold_ms
        ]

    def traffic_by_hour(self) -> Dict[str, int]:
        hourly = defaultdict(int)
        for entry in self.entries:
            ts = entry.get("timestamp", "")
            if ts:
                hour = ts[:13]
                hourly[hour] += 1
        return dict(sorted(hourly.items()))

    def search(self, query: str, level: Optional[str] = None) -> List[Dict]:
        results = []
        for entry in self.entries:
            if level and entry.get("level") != level:
                continue
            if query in json.dumps(entry):
                results.append(entry)
        return results
```''', r'''<think>
Let me analyze this log parsing and analysis code.

Memory issues:

1. parse_file and parse_json_logs load all entries into a list in memory. For large log files (multiple GB), this exhausts memory.

2. LogAnalyzer.entries accumulates all entries from all loaded files. Loading multiple files compounds the memory problem.

3. load() for gzip files reads the ENTIRE file into memory with f.read(), then splits by newline. This doubles memory usage (compressed + uncompressed content + parsed entries).

4. search() calls json.dumps(entry) for every entry for every search query. This serializes the entire log entry to JSON just to do a string search. Extremely inefficient for large datasets.

Correctness issues:

5. response_time_analysis percentile calculation is incorrect for edge cases:
   - p95 uses int(len(times) * 0.95) which can be off-by-one. For 100 entries, index 95 is the 96th entry, not the 95th percentile.
   - For small datasets (e.g., 1 entry), int(1 * 0.99) = 0, so p99 equals p50 equals the only value. Not necessarily wrong but the index calculation is imprecise.

6. error_summary truncates messages to 100 characters: e.get("message", "")[:100]. This groups different errors that share the first 100 characters, giving incorrect unique error counts.

7. traffic_by_hour assumes timestamp format starts with "YYYY-MM-DD HH" (ts[:13]). For JSON log entries, the timestamp might be ISO 8601 with "T" separator or a Unix timestamp, causing incorrect grouping.

Performance issues:

8. parse_line compiles a regex once (good) but the pattern is very permissive. (?P<message>.*) captures everything after the first three tokens, including multi-line stack traces that might span multiple lines.

9. find_slow_requests converts duration_ms to float for every entry every time it is called. Should be done once during parsing.

10. No streaming/generator pattern. All methods return full lists. For large log files, the caller has no way to process entries incrementally.

Missing:

11. No support for multi-line log entries (stack traces span multiple lines).
12. No timezone handling in timestamps.
13. No log rotation handling (reading the current file while it is being written to).
14. parse_json_logs silently skips malformed JSON lines without logging or counting how many were skipped.
</think>

## Code Review: Log Aggregation and Analysis

### CRITICAL - All Entries Loaded Into Memory
`parse_file`, `parse_json_logs`, and `load` accumulate all parsed entries in lists. For production log files (often several GB), this exhausts application memory. The gzip handler is especially bad, reading the entire decompressed file content with `f.read()` before processing.

**Fix:** Use generators for streaming processing:
```python
def parse_file(self, filepath):
    with open(filepath) as f:
        for line in f:
            entry = self.parse_line(line.strip())
            if entry:
                yield entry

def load(self, filepath):
    # Stream entries instead of accumulating
    if filepath.endswith(".gz"):
        with gzip.open(filepath, "rt") as f:
            for line in f:  # Stream line by line
                entry = self.parser.parse_line(line.strip())
                if entry:
                    yield entry
```

### HIGH - search() Serializes Every Entry to JSON
`search()` calls `json.dumps(entry)` for every log entry to perform a string containment check. For 1 million entries, this serializes 1 million dicts to JSON strings per search query. This is orders of magnitude slower than searching field values directly.

**Fix:** Search specific fields:
```python
def search(self, query, level=None):
    results = []
    for entry in self.entries:
        if level and entry.get("level") != level:
            continue
        if any(query in str(v) for v in entry.values()):
            results.append(entry)
    return results
```

### HIGH - Incorrect Percentile Calculation
`times[int(len(times) * 0.95)]` can produce off-by-one errors and index-out-of-bounds for small datasets. For 10 entries, `int(10 * 0.99)` = 9, which is the last element (max), not p99.

**Fix:** Use a proper percentile calculation:
```python
import math

def _percentile(self, sorted_data, p):
    k = (len(sorted_data) - 1) * (p / 100)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return sorted_data[int(k)]
    return sorted_data[f] * (c - k) + sorted_data[c] * (k - f)
```

### MEDIUM - Error Message Truncation Conflates Different Errors
`e.get("message", "")[:100]` groups errors by their first 100 characters. Two different errors that share a long common prefix are counted as the same error. Example: "Failed to connect to service-A: timeout" and "Failed to connect to service-A: connection refused" might share 40+ characters and still be distinct, but longer similar messages would be incorrectly merged.

**Fix:** Use a hash of the full message or normalize error messages with a smarter grouping strategy.

### MEDIUM - No Multi-Line Log Entry Support
The regex parser assumes each log entry is a single line. Java/Python stack traces span multiple lines, so the traceback is either missed entirely or parsed as separate (malformed) entries.

**Fix:** Detect continuation lines (lines that don't match the timestamp pattern) and append them to the previous entry.

### MEDIUM - Inconsistent Timestamp Handling
`traffic_by_hour` uses `ts[:13]` assuming the format "YYYY-MM-DD HH". JSON log entries might use ISO 8601 ("2024-01-15T14:30:00Z"), Unix timestamps, or other formats. This produces incorrect hour groupings.

**Fix:** Parse timestamps properly:
```python
from dateutil import parser as dateparser

def traffic_by_hour(self):
    hourly = defaultdict(int)
    for entry in self.entries:
        ts = entry.get("timestamp")
        if ts:
            try:
                dt = dateparser.parse(str(ts))
                hour = dt.strftime("%Y-%m-%d %H")
                hourly[hour] += 1
            except (ValueError, TypeError):
                continue
    return dict(sorted(hourly.items()))
```

### MEDIUM - Silently Skipping Malformed JSON
`parse_json_logs` catches `JSONDecodeError` and continues without logging. If 50% of lines are malformed, the caller has no idea that half the data was discarded.

**Fix:** Count and report skipped lines:
```python
def parse_json_logs(self, filepath):
    entries = []
    skipped = 0
    with open(filepath) as f:
        for line in f:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                skipped += 1
    if skipped:
        logger.warning(f"Skipped {skipped} malformed lines in {filepath}")
    return entries
```

### LOW - No Timezone Handling
Timestamps are compared and grouped as strings without timezone awareness. Logs from servers in different timezones are mixed incorrectly.'''),

    ("thinking/code-review", r'''Review this alerting and anomaly detection code:

```python
import time
import smtplib
import statistics
from email.mime.text import MIMEText
from collections import deque
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class AlertRule:
    name: str
    metric: str
    condition: str  # "above", "below", "equals"
    threshold: float
    window_seconds: int = 60
    cooldown_seconds: int = 300
    severity: str = "warning"
    last_triggered: float = 0

@dataclass
class MetricPoint:
    name: str
    value: float
    timestamp: float
    tags: Dict[str, str] = field(default_factory=dict)

class MetricStore:
    def __init__(self, max_points: int = 10000):
        self.metrics: Dict[str, deque] = {}
        self.max_points = max_points

    def record(self, point: MetricPoint):
        if point.name not in self.metrics:
            self.metrics[point.name] = deque(maxlen=self.max_points)
        self.metrics[point.name].append(point)

    def get_window(self, metric: str, window_seconds: int) -> List[MetricPoint]:
        if metric not in self.metrics:
            return []
        cutoff = time.time() - window_seconds
        return [p for p in self.metrics[metric] if p.timestamp > cutoff]

    def get_rate(self, metric: str, window_seconds: int) -> float:
        points = self.get_window(metric, window_seconds)
        if len(points) < 2:
            return 0
        time_diff = points[-1].timestamp - points[0].timestamp
        return len(points) / time_diff

class AlertManager:
    def __init__(self, store: MetricStore):
        self.store = store
        self.rules: List[AlertRule] = []
        self.handlers: List[Callable] = []
        self.alert_history = []

    def add_rule(self, rule: AlertRule):
        self.rules.append(rule)

    def add_handler(self, handler: Callable):
        self.handlers.append(handler)

    def check_rules(self):
        for rule in self.rules:
            points = self.store.get_window(rule.metric, rule.window_seconds)
            if not points:
                continue

            values = [p.value for p in points]
            current = statistics.mean(values)

            triggered = False
            if rule.condition == "above" and current > rule.threshold:
                triggered = True
            elif rule.condition == "below" and current < rule.threshold:
                triggered = True
            elif rule.condition == "equals" and current == rule.threshold:
                triggered = True

            if triggered:
                now = time.time()
                if now - rule.last_triggered < rule.cooldown_seconds:
                    continue
                rule.last_triggered = now
                alert = {
                    "rule": rule.name,
                    "metric": rule.metric,
                    "value": current,
                    "threshold": rule.threshold,
                    "severity": rule.severity,
                    "timestamp": datetime.now().isoformat()
                }
                self.alert_history.append(alert)
                for handler in self.handlers:
                    handler(alert)

    def check_anomalies(self, metric: str, sensitivity: float = 2.0):
        points = self.store.get_window(metric, 3600)
        if len(points) < 30:
            return None

        values = [p.value for p in points]
        mean = statistics.mean(values)
        stdev = statistics.stdev(values)

        recent = self.store.get_window(metric, 300)
        recent_mean = statistics.mean([p.value for p in recent])

        if abs(recent_mean - mean) > sensitivity * stdev:
            return {
                "metric": metric,
                "type": "anomaly",
                "expected": mean,
                "actual": recent_mean,
                "deviation": abs(recent_mean - mean) / stdev
            }
        return None

class EmailAlertHandler:
    def __init__(self, smtp_host: str, smtp_port: int, sender: str, recipients: List[str]):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.sender = sender
        self.recipients = recipients

    def __call__(self, alert: Dict):
        msg = MIMEText(
            f"Alert: {alert['rule']}\n"
            f"Metric: {alert['metric']}\n"
            f"Value: {alert['value']}\n"
            f"Threshold: {alert['threshold']}\n"
            f"Severity: {alert['severity']}"
        )
        msg['Subject'] = f"[{alert['severity'].upper()}] {alert['rule']}"
        msg['From'] = self.sender
        msg['To'] = ', '.join(self.recipients)

        server = smtplib.SMTP(self.smtp_host, self.smtp_port)
        server.send_message(msg)
        server.quit()

class SlackAlertHandler:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def __call__(self, alert: Dict):
        import requests
        color = "#ff0000" if alert["severity"] == "critical" else "#ffaa00"
        payload = {
            "attachments": [{
                "color": color,
                "title": alert["rule"],
                "text": f"Metric `{alert['metric']}` is {alert['value']:.2f} (threshold: {alert['threshold']})",
                "ts": time.time()
            }]
        }
        requests.post(self.webhook_url, json=payload)

def run_alert_loop(manager: AlertManager, interval: int = 10):
    while True:
        manager.check_rules()
        time.sleep(interval)
```''', r'''<think>
Let me analyze this alerting and anomaly detection system.

1. Thread safety:
- MetricStore.metrics is a dict of deques accessed from potentially multiple threads (one recording metrics, one checking alerts). No synchronization. Concurrent record() and get_window() can cause data corruption.
- AlertRule.last_triggered is mutated during check_rules(). If check_rules() is called concurrently, two threads can both pass the cooldown check and fire duplicate alerts.
- alert_history grows without bound.

2. Alert evaluation:
- check_rules uses statistics.mean(values) to compare against the threshold. A single spike in a metric could be averaged away if the rest of the window is normal. For alerting on spikes, you typically want max or percentile, not mean.
- `rule.condition == "equals" and current == rule.threshold` compares floating point numbers with ==. Due to floating point precision, this almost never triggers.

3. Anomaly detection:
- check_anomalies uses a 1-hour window for baseline and 5-minute window for recent. If stdev is 0 (constant metric), division by zero when calculating deviation: abs(recent_mean - mean) / stdev.
- The z-score approach assumes normal distribution. Many metrics (request latency, error rates) follow heavy-tailed distributions where z-score anomaly detection produces many false positives.
- If recent returns 0 points (no data in last 5 minutes), statistics.mean([]) raises StatisticsError.

4. get_rate calculation:
- Returns len(points) / time_diff. If all points have the same timestamp (burst), time_diff is 0, causing division by zero.

5. EmailAlertHandler:
- Creates a new SMTP connection for every alert. In a burst of alerts, this opens many connections.
- No TLS/SSL. Credentials (if needed) would be sent in plaintext.
- No error handling. If the SMTP server is down, the exception propagates and can crash the alert loop.
- No timeout on SMTP connection.

6. SlackAlertHandler:
- No error handling on requests.post. If Slack is down, the handler crashes.
- No timeout on the HTTP request. A hung request blocks the entire alert processing.
- Webhook URL is stored in code or passed directly. Should come from environment variables.

7. run_alert_loop:
- Runs forever with time.sleep. No graceful shutdown mechanism.
- If check_rules() raises an exception, the loop crashes and alerting stops entirely. Should catch exceptions and continue.
- Only checks rules, does not call check_anomalies. Anomaly detection is defined but never invoked in the loop.

8. Handler failures:
- If any handler raises an exception during check_rules, subsequent handlers are not called. One broken handler (e.g., email server down) prevents Slack alerts too.

9. MetricStore.get_window:
- Iterates all points in the deque to filter by timestamp. For 10,000 points, this is O(n) on every rule check. Since points are time-ordered, binary search could be used.

Let me write the review.
</think>

## Code Review: Alerting and Anomaly Detection System

### CRITICAL - Division by Zero in Multiple Locations

**DZ1: get_rate divides by zero on burst data (Severity: CRITICAL)**
```python
time_diff = points[-1].timestamp - points[0].timestamp
return len(points) / time_diff
```
If all points have the same timestamp (burst of events), `time_diff` is 0. Add a guard:
```python
if time_diff == 0:
    return float('inf') if len(points) > 1 else 0
```

**DZ2: check_anomalies divides by zero when stdev is 0 (Severity: CRITICAL)**
```python
if abs(recent_mean - mean) > sensitivity * stdev:
    return { ... "deviation": abs(recent_mean - mean) / stdev }
```
For a constant metric (stdev=0), the comparison `> sensitivity * 0` triggers on any deviation, and the division by zero in the return value crashes. Guard:
```python
if stdev == 0:
    return None  # Constant metric, no anomaly possible
```

**DZ3: check_anomalies crashes on empty recent window (Severity: CRITICAL)**
If no data points exist in the last 5 minutes, `statistics.mean([])` raises `StatisticsError`. Check length before computing:
```python
recent = self.store.get_window(metric, 300)
if not recent:
    return None
```

### HIGH - No Thread Safety

**TS1: Concurrent access to metrics dict (Severity: HIGH)**
`MetricStore.metrics` is modified by `record()` and read by `get_window()` without locking. Concurrent access from the recording thread and the alert-checking thread can corrupt the dict. Add a threading.Lock:
```python
class MetricStore:
    def __init__(self, max_points=10000):
        self.metrics = {}
        self.max_points = max_points
        self._lock = threading.Lock()

    def record(self, point):
        with self._lock:
            if point.name not in self.metrics:
                self.metrics[point.name] = deque(maxlen=self.max_points)
            self.metrics[point.name].append(point)
```

### HIGH - Handler Failure Breaks Alert Chain

**HF1: One broken handler prevents all subsequent handlers (Severity: HIGH)**
```python
for handler in self.handlers:
    handler(alert)
```
If `EmailAlertHandler` raises (SMTP server down), `SlackAlertHandler` never fires. Wrap each handler:
```python
for handler in self.handlers:
    try:
        handler(alert)
    except Exception as e:
        logger.error(f"Alert handler {handler} failed: {e}")
```

### HIGH - Email Handler Has No Error Handling

**EM1: SMTP failures crash the alert loop (Severity: HIGH)**
`EmailAlertHandler.__call__` creates an SMTP connection with no timeout, no TLS, and no try/except. If the SMTP server is unreachable, the connection hangs indefinitely or raises, crashing `run_alert_loop`.

**Fix:**
```python
def __call__(self, alert):
    try:
        server = smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=10)
        server.starttls()
        server.send_message(msg)
        server.quit()
    except Exception as e:
        logger.error(f"Failed to send alert email: {e}")
```

### HIGH - Alert Loop Has No Exception Handling

**AL1: Single exception kills all alerting (Severity: HIGH)**
```python
def run_alert_loop(manager, interval=10):
    while True:
        manager.check_rules()
        time.sleep(interval)
```
Any exception in `check_rules()` terminates the loop permanently. Add error handling:
```python
while True:
    try:
        manager.check_rules()
    except Exception as e:
        logger.error(f"Alert check failed: {e}")
    time.sleep(interval)
```

### MEDIUM - Float Equality Comparison

**FE1: equals condition never triggers (Severity: MEDIUM)**
```python
elif rule.condition == "equals" and current == rule.threshold:
```
Comparing floating point numbers with `==` almost never evaluates to True due to precision errors. Use an epsilon:
```python
elif rule.condition == "equals" and abs(current - rule.threshold) < 1e-9:
```

### MEDIUM - Mean Hides Spikes

**MS1: Alert threshold compared to mean value (Severity: MEDIUM)**
`statistics.mean(values)` averages the entire window. A brief CPU spike to 100% is averaged down if the rest of the window is at 40%. For spike detection, use max or a high percentile:
```python
if rule.condition == "above":
    check_value = max(values)  # or percentile(values, 95)
elif rule.condition == "below":
    check_value = min(values)
```

### MEDIUM - Anomaly Detection Never Runs

**AD1: check_anomalies not called in alert loop (Severity: MEDIUM)**
`run_alert_loop` only calls `check_rules()`. The `check_anomalies` method is defined but never invoked, making the anomaly detection feature dead code.

### MEDIUM - Unbounded Alert History

**AH1: alert_history grows without limit (Severity: MEDIUM)**
Every triggered alert is appended to `self.alert_history` with no size cap or TTL. Use a bounded deque:
```python
self.alert_history = deque(maxlen=10000)
```

### LOW - No Graceful Shutdown

**GS1: Alert loop runs forever with no exit (Severity: LOW)**
`run_alert_loop` has no mechanism for graceful shutdown. Use a threading.Event for cancellation:
```python
def run_alert_loop(manager, interval=10, stop_event=None):
    while not (stop_event and stop_event.is_set()):
        manager.check_rules()
        if stop_event:
            stop_event.wait(timeout=interval)
        else:
            time.sleep(interval)
```

### LOW - Slack Handler Missing Timeout

**ST1: requests.post without timeout (Severity: LOW)**
`requests.post(self.webhook_url, json=payload)` has no timeout. A hung Slack endpoint blocks alert processing. Add `timeout=10`.'''),
]
