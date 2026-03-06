PAIRS = [
    ("thinking/debugging", r'''Our structured logging is producing malformed JSON that breaks our log aggregator:

```python
import logging
import json

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'message': record.getMessage(),
            'module': record.module,
        }
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_data)

handler = logging.StreamHandler()
handler.setFormatter(JsonFormatter())
logger = logging.getLogger('myapp')
logger.addHandler(handler)
```

Output sometimes contains unescaped newlines in the exception field:
```
{"timestamp": "2024-03-15 10:00:00", "level": "ERROR", "message": "Failed", "exception": "Traceback (most recent call last):
  File \"app.py\", line 42, in process
    raise ValueError(\"bad data\")
ValueError: bad data"}
```

The newlines in the exception break JSON parsing in Elasticsearch.''', r'''<think>
The issue is that `self.formatException(record.exc_info)` returns a multiline string with actual newline characters. When this is included in the JSON dict and serialized with `json.dumps()`, json.dumps SHOULD properly escape the newlines as `\n` in the output.

Wait, looking again at the output: if json.dumps is working correctly, newlines would be escaped as `\n` in the JSON string. The output shown has literal newlines. This could mean json.dumps is not being called, or something is post-processing the output.

Hmm, actually I need to reconsider. json.dumps with default settings DOES produce a single line with properly escaped `\n`. So the raw JSON output should be valid. But the real problem might be downstream: the log shipper (Filebeat, Fluentd) is splitting the log stream by newlines and treating each line as a separate JSON document. Even though json.dumps escapes newlines in string values, there could be other issues.

I initially thought this was purely a json.dumps problem, but wait -- could the StreamHandler itself be adding newlines? The logging StreamHandler calls stream.write(msg) and then stream.write(self.terminator), which adds a newline. That is expected and fine for NDJSON. But if the formatted output somehow contains unescaped newlines before json.dumps is called...

Actually, I think the most likely cause is that the exception string contains control characters or invalid UTF-8 bytes that json.dumps either chokes on or that the log shipper misinterprets. Because json.dumps with ensure_ascii=False might pass through problematic Unicode characters, the safe fix is to use ensure_ascii=True and add a default=str fallback for non-serializable types.

I should also consider the tradeoff between rolling your own formatter vs using python-json-logger or structlog, which handle all these edge cases already.
</think>

The `json.dumps()` function should escape newlines as `\n` in the output, producing valid single-line JSON. However, there are several ways this can break in practice:

1. A log shipper or aggregator splits log lines before parsing JSON
2. The exception string contains characters that break JSON (control characters, invalid UTF-8)
3. A logging handler or middleware processes the output after formatting

**Fix: Ensure single-line JSON output with proper escaping**

```python
import logging
import json
import traceback
from datetime import datetime, timezone

class JsonFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            'timestamp': datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }

        # Add exception info as a single escaped string
        if record.exc_info and record.exc_info[0] is not None:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': traceback.format_exception(*record.exc_info),
            }

        # Add extra fields
        if hasattr(record, 'extra_data'):
            log_data['extra'] = record.extra_data

        # ensure_ascii=True escapes all non-ASCII characters
        # separators removes extra whitespace
        return json.dumps(
            log_data,
            ensure_ascii=True,
            default=str,  # fallback serializer for non-JSON types
            separators=(',', ':'),  # compact output, no spaces
        )
```

**Key improvements:**

1. **`ensure_ascii=True`**: Escapes all non-ASCII characters, preventing encoding issues
2. **`default=str`**: Handles non-serializable types (datetime, Decimal, etc.) by converting to string instead of crashing
3. **`separators=(',', ':')`**: Produces compact single-line output
4. **Structured exception**: Separates exception type, message, and traceback for better querying

**Fix for log shippers that split by newlines:**

Some log shippers (Filebeat, Fluentd) assume one log entry per line. Even with properly escaped JSON, if the JSON is too long or contains certain patterns, it may be mishandled.

```python
# Docker logging driver fix:
# Use a multi-line pattern in Filebeat
# filebeat.yml:
# multiline.pattern: '^\{'
# multiline.negate: true
# multiline.match: after
```

**Testing your JSON formatter:**

```python
def test_json_formatter_handles_exceptions():
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name='test', level=logging.ERROR,
        pathname='test.py', lineno=1, msg='test error',
        args=None, exc_info=None,
    )
    # Add a real exception
    try:
        raise ValueError("test\nerror\nwith\nnewlines")
    except ValueError:
        import sys
        record.exc_info = sys.exc_info()

    output = formatter.format(record)

    # Must be valid JSON
    parsed = json.loads(output)
    assert parsed['level'] == 'ERROR'

    # Must be single line
    assert '\n' not in output
```

**Use a battle-tested library instead of rolling your own:**

```python
# python-json-logger
from pythonjsonlogger import jsonlogger

handler = logging.StreamHandler()
formatter = jsonlogger.JsonFormatter(
    '%(timestamp)s %(level)s %(name)s %(message)s',
    timestamp=True,
)
handler.setFormatter(formatter)
```

**Prevention tips:**
- Use `python-json-logger` or `structlog` instead of writing your own formatter
- Always test JSON output with exceptions, Unicode, and binary data
- Verify single-line output: `assert '\n' not in formatter.format(record)`
- Use `ensure_ascii=True` for maximum compatibility with log shippers
- Add a `default=str` fallback to handle non-serializable types gracefully'''),

    ("thinking/debugging", r'''Our log rotation is filling the disk because old logs are not being deleted:

```python
import logging
from logging.handlers import RotatingFileHandler

handler = RotatingFileHandler(
    '/var/log/myapp/app.log',
    maxBytes=100*1024*1024,  # 100MB per file
    backupCount=5,
)
logger = logging.getLogger('myapp')
logger.addHandler(handler)
```

Expected: 6 files max (app.log + app.log.1 through app.log.5) = 600MB
Actual: /var/log/myapp/ has 47GB of files:

```
$ ls -la /var/log/myapp/
app.log           100M
app.log.1         100M
app.log.2         100M
app.log.3         100M
app.log.4         100M
app.log.5         100M
worker.log        100M
worker.log.1      100M
... (50+ more files)
access.log        15G
error.log         12G
```

The RotatingFileHandler files are fine but there are other log files not managed by the rotation.''', r'''<think>
The RotatingFileHandler is working correctly for app.log (6 files * 100MB = 600MB). So the Python logging rotation is not the problem.

But looking at the directory listing, there are other files: worker.log, access.log (15GB!), and error.log (12GB). These are not managed by the RotatingFileHandler.

My first thought was that the RotatingFileHandler configuration was wrong, but actually it is doing exactly what it should. The real issue is that access.log and error.log have NO rotation at all. These are likely from a web server (Gunicorn or Nginx) that writes logs independently of the Python logging system.

I considered just adding more RotatingFileHandlers for the other files, but that won't work for access.log and error.log because those are written by Gunicorn/Nginx, not by the Python logging module. Because these are written by external processes, the fix needs to be at the OS level using logrotate, or by configuring the web server's own log rotation.

Wait, there is also the question of whether to use copytruncate or a signal-based rotation. Option A (copytruncate) is simpler -- it copies the file and truncates in place, so the writing process does not need to reopen the file. Option B (signal-based) sends SIGUSR1 to the process to reopen log files, which is cleaner but requires the process to handle the signal. Because Gunicorn and Nginx both support signal-based log reopening, that is the more robust approach for those servers.
</think>

The `RotatingFileHandler` is working correctly for `app.log` (6 files = 600MB). The disk space problem comes from other log files that have no rotation:

- `worker.log` -- likely from a separate worker process
- `access.log` (15GB) -- probably Gunicorn or Nginx access logs
- `error.log` (12GB) -- Gunicorn or Nginx error logs

These files grow indefinitely because they are not managed by any rotation mechanism.

**Fix 1: Configure system logrotate for all log files**

```
# /etc/logrotate.d/myapp
/var/log/myapp/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    maxsize 500M
    copytruncate
    postrotate
        # Signal the application to reopen log files
        kill -USR1 $(cat /var/run/myapp.pid) 2>/dev/null || true
    endscript
}
```

Key options:
- `daily rotate 7`: Keep 7 days of logs
- `compress`: gzip old files to save space
- `maxsize 500M`: Rotate if file exceeds 500MB even before the daily rotation
- `copytruncate`: Copy the file and truncate in place (avoids needing to signal the app)

**Fix 2: Configure Gunicorn access/error log rotation**

```python
# gunicorn.conf.py
accesslog = '/var/log/myapp/access.log'
errorlog = '/var/log/myapp/error.log'

# Use RotatingFileHandler for Gunicorn
import logging
from logging.handlers import RotatingFileHandler

def on_starting(server):
    access_handler = RotatingFileHandler(
        '/var/log/myapp/access.log',
        maxBytes=100*1024*1024,
        backupCount=5,
    )
    error_handler = RotatingFileHandler(
        '/var/log/myapp/error.log',
        maxBytes=100*1024*1024,
        backupCount=5,
    )
    logging.getLogger('gunicorn.access').addHandler(access_handler)
    logging.getLogger('gunicorn.error').addHandler(error_handler)
```

**Fix 3: Use TimedRotatingFileHandler for time-based rotation**

```python
from logging.handlers import TimedRotatingFileHandler

handler = TimedRotatingFileHandler(
    '/var/log/myapp/app.log',
    when='midnight',
    interval=1,
    backupCount=30,  # keep 30 days
    utc=True,
)
handler.suffix = '%Y-%m-%d'
```

**Fix 4: Log to stdout and let Docker/K8s handle rotation**

```python
# In containers, log to stdout
handler = logging.StreamHandler(sys.stdout)
logger.addHandler(handler)
```

```json
// Docker daemon.json
{
    "log-driver": "json-file",
    "log-opts": {
        "max-size": "50m",
        "max-file": "5"
    }
}
```

**Immediate cleanup:**

```bash
# Find and delete large log files
find /var/log/myapp -name "*.log" -size +1G -exec ls -lh {} \;

# Truncate a file in place (keeps file handle open)
truncate -s 0 /var/log/myapp/access.log

# Or if you need to keep recent data:
tail -n 10000 /var/log/myapp/access.log > /tmp/access_recent.log
cp /tmp/access_recent.log /var/log/myapp/access.log
```

**Monitoring disk usage:**

```bash
# Add to cron: alert if /var/log exceeds 80% capacity
0 * * * * [ $(df /var/log --output=pcent | tail -1 | tr -d '%' | tr -d ' ') -gt 80 ] && echo "Disk alert: /var/log over 80%" | mail -s "Disk Alert" ops@example.com
```

**Prevention tips:**
- Configure logrotate for ALL log files, not just your application logs
- Use `maxsize` in addition to time-based rotation to handle log spikes
- In containers, log to stdout and let the container runtime handle rotation
- Monitor disk usage on log partitions with alerts at 80% capacity
- Set up centralized logging (ELK, Datadog, CloudWatch) and reduce local retention
- Use `compress` in logrotate to reduce disk usage by 90%'''),

    ("thinking/debugging", r'''Our application is accidentally logging sensitive data:

```
2024-03-15 10:00:00 INFO Processing payment for user john@example.com
2024-03-15 10:00:00 DEBUG Request body: {"card_number": "4111111111111111", "cvv": "123", "amount": 99.99}
2024-03-15 10:00:01 INFO Payment successful, token: sk_live_abc123def456ghi789
```

The logs contain credit card numbers, CVVs, email addresses, and API keys. Our compliance team flagged this as a PCI DSS violation.''', r'''<think>
This is a serious security and compliance issue. PCI DSS requires that cardholder data (card numbers, CVVs) never be logged. The logs contain credit card numbers, CVVs, email addresses, and API keys in plaintext.

My first thought was to add a regex-based filter that masks sensitive patterns. But wait, regex-based redaction is a denylist approach -- it only catches patterns you explicitly define. If someone logs a new type of sensitive data (e.g., SSN, passport number), it would slip through until the pattern is added. Hmm, actually that is still better than no redaction at all.

I considered whether the better approach is an allowlist: instead of filtering OUT sensitive data, only log explicitly whitelisted safe fields. Because an allowlist cannot leak data it does not know about, it is inherently safer than a denylist. But it requires more upfront work to define what is safe.

The tradeoff: Option A (regex denylist filter) is easy to retrofit onto existing code but might miss new sensitive data types. Option B (structured logging with allowlisted fields) is more secure but requires refactoring all log calls. Option C (just disable DEBUG in production) is the quickest win and would eliminate the request body logging, but does not fix the INFO-level API key leak.

The real fix needs multiple layers: disable DEBUG in production (immediate), add redaction filters (short-term), and migrate to structured logging with safe fields only (long-term).
</think>

Logging sensitive data violates PCI DSS, GDPR, and other regulations. Credit card numbers and CVVs must never appear in logs, and API keys and personal data should be redacted.

**Fix 1: Add a log redaction filter**

```python
import logging
import re

class SensitiveDataFilter(logging.Filter):
    """Redact sensitive data from log messages."""

    PATTERNS = [
        # Credit card numbers (13-19 digits)
        (re.compile(r'\b(\d{4})\d{8,12}(\d{4})\b'), r'\1****\2'),

        # CVV (3-4 digits after card-related context)
        (re.compile(r'("cvv"\s*:\s*)"?\d{3,4}"?'), r'\1"***"'),

        # Email addresses
        (re.compile(r'[\w.+-]+@[\w.-]+\.\w+'), '[REDACTED_EMAIL]'),

        # API keys (common patterns)
        (re.compile(r'(sk_live_|sk_test_|api_key["\s:=]+)[a-zA-Z0-9]{16,}'),
         r'\1[REDACTED]'),

        # Bearer tokens
        (re.compile(r'(Bearer\s+)[a-zA-Z0-9._-]+'), r'\1[REDACTED]'),

        # SSN
        (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), '[REDACTED_SSN]'),

        # Password fields in JSON
        (re.compile(r'("password"\s*:\s*)"[^"]*"'), r'\1"[REDACTED]"'),
    ]

    def filter(self, record):
        record.msg = self._redact(str(record.msg))
        if record.args:
            record.args = tuple(
                self._redact(str(arg)) if isinstance(arg, str) else arg
                for arg in record.args
            )
        return True

    def _redact(self, text):
        for pattern, replacement in self.PATTERNS:
            text = pattern.sub(replacement, text)
        return text

# Apply to all handlers
logger = logging.getLogger('myapp')
logger.addFilter(SensitiveDataFilter())
```

After filter:
```
2024-03-15 10:00:00 INFO Processing payment for user [REDACTED_EMAIL]
2024-03-15 10:00:00 DEBUG Request body: {"card_number": "4111****1111", "cvv": "***", "amount": 99.99}
2024-03-15 10:00:01 INFO Payment successful, token: sk_live_[REDACTED]
```

**Fix 2: Use structured logging with explicit safe fields**

```python
import structlog

logger = structlog.get_logger()

def process_payment(user, card_data, amount):
    # Only log safe fields -- never log the full request
    logger.info(
        "processing_payment",
        user_id=user.id,          # ID, not email
        amount=amount,
        card_last_four=card_data['card_number'][-4:],
        # Never include: card_number, cvv, full email
    )
```

**Fix 3: Disable DEBUG level in production**

```python
import os

log_level = os.environ.get('LOG_LEVEL', 'INFO')
logging.basicConfig(level=getattr(logging, log_level))

# Production should NEVER run at DEBUG level
# DEBUG logging often includes request bodies and internal state
```

**Fix 4: Create a safe request logger**

```python
SAFE_HEADERS = {'Content-Type', 'Accept', 'User-Agent'}
REDACTED_FIELDS = {'card_number', 'cvv', 'password', 'token', 'secret', 'api_key'}

def safe_log_request(request):
    """Log request without sensitive data."""
    safe_headers = {
        k: v for k, v in request.headers.items()
        if k in SAFE_HEADERS
    }

    safe_body = None
    if request.is_json:
        body = request.get_json(silent=True) or {}
        safe_body = {
            k: '[REDACTED]' if k.lower() in REDACTED_FIELDS else v
            for k, v in body.items()
        }

    logger.info(
        "incoming_request",
        method=request.method,
        path=request.path,
        headers=safe_headers,
        body=safe_body,
    )
```

**Prevention tips:**
- Never log full request/response bodies in production
- Use an allowlist of loggable fields, not a denylist of sensitive fields
- Disable DEBUG level logging in production
- Add the redaction filter to ALL log handlers, including third-party libraries
- Run automated scans for PII/PCI data in log files
- Use structured logging that explicitly names each field
- Review log output in code reviews as a security checkpoint
- Store logs in encrypted storage with access controls'''),

    ("thinking/debugging", r'''We can't correlate logs across our microservices. A single user request generates logs in 5 different services but we can't trace the flow:

```
# Service A (API Gateway)
2024-03-15 10:00:00 INFO Received request POST /api/orders

# Service B (Order Service)
2024-03-15 10:00:01 INFO Creating order for user 42

# Service C (Payment Service)
2024-03-15 10:00:02 INFO Processing payment of $99.99

# Service D (Inventory Service)
2024-03-15 10:00:02 INFO Checking stock for product SKU-123

# Service E (Notification Service)
2024-03-15 10:00:03 ERROR Failed to send email: SMTP connection timeout
```

When the notification fails, how do I find all related logs from the original request?''', r'''<think>
This is the distributed tracing / correlation ID problem. With 5 services and no way to link their logs, debugging a failure requires manually correlating by timestamp, which is unreliable when services run on different clocks.

I initially thought about using timestamps to correlate, but that won't work reliably because clock skew between servers can be several milliseconds, and multiple requests might overlap in the same time window. The only reliable approach is a unique correlation ID that follows the request through all services.

I considered using the user ID as the correlation key, but that won't work because a user might have multiple concurrent requests. Hmm, actually even session ID is not enough because a single page load might trigger multiple API calls. The ID needs to be unique per request chain.

The solution is to generate a trace ID at the API Gateway and propagate it via HTTP headers (like X-Trace-ID) to all downstream services. Each service extracts the header, includes it in all log messages, and forwards it to any further downstream calls. Because the ID is unique per request chain, you can search for it in your log aggregator to see the complete flow.

The tradeoff between rolling your own trace propagation vs adopting OpenTelemetry: custom headers are simpler to start with, but OpenTelemetry provides standardized W3C Trace Context headers, automatic instrumentation, and export to visualization tools like Jaeger.
</think>

You need a correlation ID (trace ID) that follows the request through all services. The API Gateway generates a unique ID and passes it in HTTP headers to downstream services. Each service includes this ID in all log messages.

**Fix: Implement distributed tracing with correlation IDs**

```python
# middleware.py (used by all services)
import uuid
import logging
from contextvars import ContextVar

# Thread-safe context variable for the trace ID
trace_id_var = ContextVar('trace_id', default=None)
span_id_var = ContextVar('span_id', default=None)

class TracingMiddleware:
    def __init__(self, app):
        self.app = app

    def __call__(self, environ, start_response):
        # Extract or generate trace ID
        trace_id = environ.get('HTTP_X_TRACE_ID') or str(uuid.uuid4())
        parent_span = environ.get('HTTP_X_SPAN_ID')
        span_id = str(uuid.uuid4())[:8]

        trace_id_var.set(trace_id)
        span_id_var.set(span_id)

        # Add trace ID to response headers
        def traced_start_response(status, headers, exc_info=None):
            headers.append(('X-Trace-ID', trace_id))
            return start_response(status, headers, exc_info)

        return self.app(environ, traced_start_response)

# Log formatter that includes trace ID
class TracingFormatter(logging.Formatter):
    def format(self, record):
        record.trace_id = trace_id_var.get('unknown')
        record.span_id = span_id_var.get('unknown')
        return super().format(record)

formatter = TracingFormatter(
    '%(asctime)s [%(trace_id)s] [%(span_id)s] %(levelname)s %(name)s: %(message)s'
)
```

**Propagate trace ID to downstream services:**

```python
import requests

def call_downstream(url, data):
    """Make HTTP call with trace propagation."""
    trace_id = trace_id_var.get()
    span_id = span_id_var.get()

    headers = {
        'X-Trace-ID': trace_id,
        'X-Parent-Span-ID': span_id,
        'X-Span-ID': str(uuid.uuid4())[:8],
    }

    return requests.post(url, json=data, headers=headers)
```

**Result: Correlated logs across services:**

```
# Service A (API Gateway)
2024-03-15 10:00:00 [abc-123-def] [s1] INFO Received POST /api/orders

# Service B (Order Service)
2024-03-15 10:00:01 [abc-123-def] [s2] INFO Creating order for user 42

# Service C (Payment Service)
2024-03-15 10:00:02 [abc-123-def] [s3] INFO Processing payment of $99.99

# Service D (Inventory Service)
2024-03-15 10:00:02 [abc-123-def] [s4] INFO Checking stock for SKU-123

# Service E (Notification Service)
2024-03-15 10:00:03 [abc-123-def] [s5] ERROR Failed to send email: SMTP timeout
```

Now you can search for `abc-123-def` in your log aggregator to find ALL logs from this request.

**Use OpenTelemetry for production-grade tracing:**

```python
from opentelemetry import trace
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor

# Auto-instrument Flask and requests library
FlaskInstrumentor().instrument_app(app)
RequestsInstrumentor().instrument()

# Trace ID is automatically propagated via W3C Trace Context headers
```

OpenTelemetry handles trace ID generation, propagation, and export to backends like Jaeger, Zipkin, or Datadog.

**Searching correlated logs:**

```bash
# Elasticsearch/Kibana query
trace_id: "abc-123-def"

# Datadog
@trace_id:abc-123-def

# CloudWatch Logs Insights
filter @message like "abc-123-def"
| sort @timestamp asc
```

**Prevention tips:**
- Generate trace IDs at the entry point (API gateway, load balancer)
- Propagate trace IDs in ALL inter-service communication (HTTP, message queues, gRPC)
- Use W3C Trace Context headers for standardized propagation
- Include trace ID in error responses so users can report it for debugging
- Use OpenTelemetry for automatic instrumentation
- Configure your log aggregator to index the trace_id field for fast lookups'''),

    ("thinking/debugging", r'''Our logging configuration is wrong -- some loggers are too verbose and others are silent:

```python
import logging

logging.basicConfig(level=logging.DEBUG)

logger = logging.getLogger('myapp')
logger.setLevel(logging.INFO)

# This prints nothing!
logger.debug("Debug message")
logger.info("Info message")  # also nothing!
```

I set the root logger to DEBUG and myapp to INFO, but nothing gets printed. What's wrong?''', r'''<think>
The issue is likely that `logging.basicConfig()` is being called AFTER a handler has already been configured, or there is a handler/propagation issue.

Actually, wait. `logging.basicConfig(level=logging.DEBUG)` configures the root logger with a StreamHandler. Then `logger = logging.getLogger('myapp')` gets the 'myapp' logger and sets its level to INFO.

When logger.info("Info message") is called:
1. myapp logger checks: INFO >= INFO (its level) -> passes
2. Message propagates to root logger
3. Root logger's handler (StreamHandler) should output it

This should work. Unless basicConfig is not actually adding a handler because it was already called or something else configured the root logger first.

Let me think about what could cause this... Maybe the user is running this in a Jupyter notebook or an environment where logging is already configured, and basicConfig does nothing because the root logger already has handlers.

The key fact: `logging.basicConfig()` does nothing if the root logger already has handlers. Many frameworks (Django, Flask) configure logging during import.
</think>

The most likely cause is that `logging.basicConfig()` did nothing because the root logger was already configured. `basicConfig` only takes effect if the root logger has no handlers. If any library or framework has already configured logging (which happens during import in many cases), your `basicConfig` call is silently ignored.

**Diagnosing the issue:**

```python
import logging

# Check if root logger already has handlers
root = logging.getLogger()
print(f"Root handlers: {root.handlers}")
print(f"Root level: {root.level}")

logger = logging.getLogger('myapp')
print(f"myapp handlers: {logger.handlers}")
print(f"myapp level: {logger.level}")
print(f"myapp effective level: {logger.getEffectiveLevel()}")
```

**Common causes:**

1. **basicConfig called after logging is already configured:**
```python
import some_library  # this library configures logging internally
logging.basicConfig(level=logging.DEBUG)  # does NOTHING!
```

2. **No handler on the logger:**
```python
logger = logging.getLogger('myapp')
logger.setLevel(logging.INFO)
# No handler added! Messages propagate to root, but root might not have a handler
logger.info("test")  # goes nowhere
```

3. **Propagation is disabled:**
```python
logger = logging.getLogger('myapp')
logger.propagate = False  # messages don't reach root logger
# Without a handler on 'myapp', messages are dropped
```

**Fix: Configure logging explicitly**

```python
import logging

# Force reconfiguration (use force=True in Python 3.8+)
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(name)s %(levelname)s: %(message)s',
    force=True,  # removes existing handlers and reconfigures
)

logger = logging.getLogger('myapp')
logger.setLevel(logging.INFO)
logger.info("This works!")
```

**Fix 2: Add a handler directly to your logger**

```python
logger = logging.getLogger('myapp')
logger.setLevel(logging.INFO)

# Add a handler explicitly
handler = logging.StreamHandler()
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s %(name)s %(levelname)s: %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

logger.info("This definitely works!")
```

**Fix 3: Use dictConfig for complex setups**

```python
import logging.config

LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'standard': {
            'format': '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'standard',
            'level': 'DEBUG',
        },
    },
    'loggers': {
        'myapp': {
            'handlers': ['console'],
            'level': 'INFO',
        },
        'sqlalchemy': {
            'handlers': ['console'],
            'level': 'WARNING',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}

logging.config.dictConfig(LOGGING_CONFIG)
```

**Understanding the logging hierarchy:**

```
root (level=WARNING)
  |-- myapp (level=INFO)
  |     |-- myapp.db (level not set, inherits INFO)
  |     |-- myapp.api (level=DEBUG)
  |-- urllib3 (level not set, inherits WARNING)
  |-- sqlalchemy (level=WARNING)
```

A logger without an explicit level inherits from its parent. Messages propagate UP the hierarchy to parent loggers (unless `propagate=False`).

**Prevention tips:**
- Use `logging.basicConfig(force=True)` or `dictConfig` for reliable configuration
- Configure logging as early as possible in your application startup
- Set `disable_existing_loggers: False` in dictConfig to avoid silencing library loggers
- Always add at least one handler to your logger or the root logger
- Use `logger.getEffectiveLevel()` to check what level actually applies
- Set third-party library loggers to WARNING to reduce noise'''),
]
