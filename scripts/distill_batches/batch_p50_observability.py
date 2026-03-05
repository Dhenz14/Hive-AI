"""Observability — distributed tracing, structured logging, metrics, and alerting."""

PAIRS = [
    (
        "devops/opentelemetry",
        "Show OpenTelemetry patterns: tracing, spans, context propagation, and integration with Python services.",
        """OpenTelemetry distributed tracing:

```python
from opentelemetry import trace, metrics, context
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource, SERVICE_NAME
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.b3 import B3MultiFormat
from functools import wraps
import logging

logger = logging.getLogger(__name__)


# --- Setup ---

def setup_telemetry(service_name: str, otlp_endpoint: str = "localhost:4317"):
    resource = Resource.create({SERVICE_NAME: service_name})

    # Tracing
    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True),
            max_queue_size=2048,
            max_export_batch_size=512,
        )
    )
    trace.set_tracer_provider(tracer_provider)

    # Metrics
    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True),
                export_interval_millis=60000,
            )
        ],
    )
    metrics.set_meter_provider(meter_provider)

    # Auto-instrument libraries
    FastAPIInstrumentor().instrument()
    HTTPXClientInstrumentor().instrument()
    SQLAlchemyInstrumentor().instrument()

    return tracer_provider


# --- Manual spans ---

tracer = trace.get_tracer("myapp")

async def process_order(order_id: str):
    with tracer.start_as_current_span(
        "process_order",
        attributes={"order.id": order_id},
    ) as span:
        # Validate
        with tracer.start_as_current_span("validate_order"):
            order = await validate(order_id)
            span.set_attribute("order.total", order.total)
            span.set_attribute("order.items_count", len(order.items))

        # Charge payment
        with tracer.start_as_current_span("charge_payment") as payment_span:
            try:
                payment_id = await charge(order)
                payment_span.set_attribute("payment.id", payment_id)
            except Exception as e:
                payment_span.set_status(trace.Status(
                    trace.StatusCode.ERROR, str(e)
                ))
                payment_span.record_exception(e)
                raise

        # Fulfill
        with tracer.start_as_current_span("fulfill_order"):
            await fulfill(order)

        span.set_attribute("order.status", "completed")


# --- Custom metrics ---

meter = metrics.get_meter("myapp")

# Counter
request_counter = meter.create_counter(
    name="http.requests.total",
    description="Total HTTP requests",
    unit="1",
)

# Histogram
request_duration = meter.create_histogram(
    name="http.request.duration",
    description="HTTP request duration",
    unit="ms",
)

# Up/down counter
active_connections = meter.create_up_down_counter(
    name="connections.active",
    description="Active connections",
)


# --- Middleware for metrics ---

from fastapi import FastAPI, Request
import time

app = FastAPI()

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = (time.perf_counter() - start) * 1000

    labels = {
        "method": request.method,
        "path": request.url.path,
        "status": str(response.status_code),
    }

    request_counter.add(1, labels)
    request_duration.record(duration, labels)

    return response


# --- Trace context in logs ---

class TraceContextFilter(logging.Filter):
    def filter(self, record):
        span = trace.get_current_span()
        if span and span.is_recording():
            ctx = span.get_span_context()
            record.trace_id = format(ctx.trace_id, "032x")
            record.span_id = format(ctx.span_id, "016x")
        else:
            record.trace_id = "0" * 32
            record.span_id = "0" * 16
        return True

# Log format: %(asctime)s [%(trace_id)s/%(span_id)s] %(message)s
# Now logs correlate with traces


# --- Decorator for tracing functions ---

def traced(name: str = None, record_args: bool = False):
    def decorator(func):
        span_name = name or f"{func.__module__}.{func.__name__}"
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                if record_args:
                    span.set_attribute("args", str(args)[:200])
                    span.set_attribute("kwargs", str(kwargs)[:200])
                try:
                    result = await func(*args, **kwargs)
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(trace.Status(trace.StatusCode.ERROR))
                    raise
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name):
                return func(*args, **kwargs)
        import asyncio
        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper
    return decorator

@traced("order.calculate_total")
async def calculate_total(order_id: str) -> float:
    ...
```

OpenTelemetry patterns:
1. **Auto-instrumentation** — instrument FastAPI, httpx, SQLAlchemy automatically
2. **Manual spans** — add context to business logic operations
3. **Attributes** — attach IDs, counts, status to spans for debugging
4. **Trace-log correlation** — include trace_id in log records
5. **Metrics** — counters, histograms, and gauges for dashboards"""
    ),
    (
        "devops/alerting-patterns",
        "Show alerting patterns: alert design, escalation, runbooks, and on-call best practices.",
        """Alerting and incident response patterns:

```yaml
# --- Prometheus alerting rules ---
# alerts/slo_alerts.yml

groups:
  - name: slo-alerts
    rules:
      # Error rate SLO (99.9% success)
      - alert: HighErrorRate
        expr: |
          (
            sum(rate(http_requests_total{status=~"5.."}[5m]))
            /
            sum(rate(http_requests_total[5m]))
          ) > 0.001
        for: 5m
        labels:
          severity: critical
          team: backend
        annotations:
          summary: "Error rate {{ $value | humanizePercentage }} exceeds 0.1% SLO"
          runbook: "https://wiki.example.com/runbooks/high-error-rate"
          dashboard: "https://grafana.example.com/d/slo"

      # Latency SLO (P99 < 500ms)
      - alert: HighLatency
        expr: |
          histogram_quantile(0.99,
            sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
          ) > 0.5
        for: 10m
        labels:
          severity: warning
          team: backend
        annotations:
          summary: "P99 latency {{ $value | humanizeDuration }} exceeds 500ms"
          runbook: "https://wiki.example.com/runbooks/high-latency"

      # Burn rate alert (multi-window)
      - alert: ErrorBudgetBurnRate
        expr: |
          (
            sum(rate(http_requests_total{status=~"5.."}[1h]))
            / sum(rate(http_requests_total[1h]))
          ) > (14.4 * 0.001)
          and
          (
            sum(rate(http_requests_total{status=~"5.."}[5m]))
            / sum(rate(http_requests_total[5m]))
          ) > (14.4 * 0.001)
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Error budget burning 14.4x faster than allowed"

  - name: infrastructure-alerts
    rules:
      - alert: HighCPU
        expr: |
          (1 - avg by(instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])))
          > 0.85
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "CPU usage {{ $value | humanizePercentage }} on {{ $labels.instance }}"

      - alert: DiskSpaceLow
        expr: |
          (node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"})
          < 0.10
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Disk space {{ $value | humanizePercentage }} on {{ $labels.instance }}"

      - alert: PodRestartLoop
        expr: |
          increase(kube_pod_container_status_restarts_total[1h]) > 5
        labels:
          severity: warning
        annotations:
          summary: "Pod {{ $labels.pod }} restarted {{ $value }} times in 1h"
```

```python
# --- Alertmanager routing ---
# alertmanager.yml (conceptual Python equivalent)

alert_config = {
    "route": {
        "receiver": "default-slack",
        "group_by": ["alertname", "team"],
        "group_wait": "30s",
        "group_interval": "5m",
        "repeat_interval": "4h",
        "routes": [
            {
                "match": {"severity": "critical"},
                "receiver": "pagerduty-oncall",
                "repeat_interval": "15m",
            },
            {
                "match": {"severity": "warning"},
                "receiver": "slack-warnings",
                "repeat_interval": "1h",
            },
            {
                "match": {"team": "backend"},
                "receiver": "slack-backend",
            },
        ],
    },
    "receivers": [
        {
            "name": "pagerduty-oncall",
            "pagerduty_configs": [{
                "routing_key": "$PD_ROUTING_KEY",
                "severity": "critical",
            }],
        },
        {
            "name": "slack-warnings",
            "slack_configs": [{
                "channel": "#alerts-warnings",
                "title": "{{ .GroupLabels.alertname }}",
                "text": "{{ range .Alerts }}{{ .Annotations.summary }}\n{{ end }}",
            }],
        },
    ],
    "inhibit_rules": [
        {
            # Don't fire HighLatency if HighErrorRate is already firing
            "source_match": {"alertname": "HighErrorRate"},
            "target_match": {"alertname": "HighLatency"},
            "equal": ["team"],
        },
    ],
}
```

Alerting best practices:
1. **Alert on symptoms** (error rate, latency) not causes (CPU, memory)
2. **Multi-window burn rate** — detect SLO violations early with less noise
3. **Inhibition rules** — suppress redundant alerts when root cause is active
4. **Runbook links** — every alert includes a link to resolution steps
5. **Escalation tiers** — warning to Slack, critical to PagerDuty"""
    ),
]
