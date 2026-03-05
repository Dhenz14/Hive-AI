"""Observability patterns — structured logging, distributed tracing, metrics, alerting."""

PAIRS = [
    (
        "devops/structured-logging",
        "Show how to implement structured logging in Python with structlog. Include context propagation, log levels, and JSON output for log aggregation.",
        '''Structured logging with structlog for production observability:

```python
import structlog
import logging
import uuid
from contextvars import ContextVar
from functools import wraps
from typing import Any

# --- Context management ---
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")

def add_context(logger, method_name, event_dict):
    """Inject request context into every log entry."""
    if rid := request_id_var.get():
        event_dict["request_id"] = rid
    if uid := user_id_var.get():
        event_dict["user_id"] = uid
    return event_dict

# --- Configure structlog ---

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        add_context,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        # Dev: pretty console output; Prod: JSON
        structlog.dev.ConsoleRenderer()  # or structlog.processors.JSONRenderer()
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

log = structlog.get_logger()

# --- Usage in application code ---

class OrderService:
    def __init__(self):
        self.log = structlog.get_logger().bind(service="order")

    def create_order(self, user_id: str, items: list[dict]) -> dict:
        self.log.info("creating_order",
                      user_id=user_id,
                      item_count=len(items))

        try:
            order = self._process_order(user_id, items)
            total = sum(i["price"] * i["qty"] for i in items)

            self.log.info("order_created",
                         order_id=order["id"],
                         total=total,
                         currency="USD")
            return order

        except InsufficientStockError as e:
            self.log.warning("order_failed_stock",
                           user_id=user_id,
                           sku=e.sku,
                           requested=e.requested,
                           available=e.available)
            raise

        except Exception as e:
            self.log.error("order_failed_unexpected",
                          user_id=user_id,
                          error=str(e),
                          exc_info=True)
            raise

# --- Middleware for request context ---

# FastAPI middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
import time

class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request_id_var.set(request_id)

        log.info("request_started",
                 method=request.method,
                 path=request.url.path,
                 client_ip=request.client.host)

        start = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start) * 1000

            log.info("request_completed",
                     method=request.method,
                     path=request.url.path,
                     status=response.status_code,
                     duration_ms=round(duration_ms, 2))

            response.headers["X-Request-ID"] = request_id
            return response

        except Exception as e:
            duration_ms = (time.perf_counter() - start) * 1000
            log.error("request_failed",
                      method=request.method,
                      path=request.url.path,
                      duration_ms=round(duration_ms, 2),
                      exc_info=True)
            raise

# --- Log correlation with tracing ---

def bind_trace_context(trace_id: str, span_id: str):
    """Bind OpenTelemetry trace context to logs."""
    structlog.contextvars.bind_contextvars(
        trace_id=trace_id,
        span_id=span_id,
    )

# Output (JSON mode):
# {"event": "order_created", "level": "info", "timestamp": "2024-03-15T10:30:00Z",
#  "request_id": "abc-123", "service": "order", "order_id": "ord-456",
#  "total": 99.99, "currency": "USD", "trace_id": "deadbeef...", "span_id": "cafebabe..."}
```

Structured logging rules:
1. **Events, not sentences**: `"order_created"` not `"Order was created successfully"`
2. **Key-value data**: structured fields, not string interpolation
3. **Consistent field names**: `user_id` everywhere, not sometimes `userId`
4. **Context propagation**: request_id, trace_id flow through all log entries
5. **Appropriate levels**: INFO for business events, WARN for degradation, ERROR for failures'''
    ),
    (
        "devops/distributed-tracing",
        "Explain distributed tracing with OpenTelemetry in Python. Show instrumentation, context propagation, and span management for microservices.",
        '''OpenTelemetry distributed tracing for microservice observability:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.b3 import B3MultiFormat
import httpx

# --- Setup ---

def setup_tracing(service_name: str, otlp_endpoint: str = "http://otel-collector:4317"):
    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.2.0",
        "deployment.environment": "production",
    })

    provider = TracerProvider(resource=resource)
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)

    # Propagation format (W3C TraceContext is default)
    # set_global_textmap(B3MultiFormat())  # Use B3 if needed

    return trace.get_tracer(service_name)

tracer = setup_tracing("order-service")

# --- Auto-instrumentation ---

from fastapi import FastAPI

app = FastAPI()
FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()
SQLAlchemyInstrumentor().instrument(engine=db_engine)

# --- Manual instrumentation ---

class OrderService:
    def __init__(self):
        self.tracer = trace.get_tracer("order-service")

    async def create_order(self, user_id: str, items: list[dict]) -> dict:
        with self.tracer.start_as_current_span(
            "create_order",
            attributes={
                "user.id": user_id,
                "order.item_count": len(items),
            },
        ) as span:
            # Validate inventory
            with self.tracer.start_as_current_span("validate_inventory"):
                for item in items:
                    available = await self._check_stock(item["sku"])
                    if available < item["qty"]:
                        span.set_status(
                            trace.StatusCode.ERROR,
                            f"Insufficient stock for {item['sku']}"
                        )
                        span.add_event("stock_check_failed", {
                            "sku": item["sku"],
                            "requested": item["qty"],
                            "available": available,
                        })
                        raise InsufficientStockError(item["sku"])

            # Calculate total
            with self.tracer.start_as_current_span("calculate_total") as calc_span:
                total = sum(i["price"] * i["qty"] for i in items)
                calc_span.set_attribute("order.total", total)

            # Call payment service (trace context propagated automatically)
            with self.tracer.start_as_current_span("process_payment"):
                async with httpx.AsyncClient() as client:
                    resp = await client.post(
                        "http://payment-service/charge",
                        json={"user_id": user_id, "amount": total},
                    )
                    if resp.status_code != 200:
                        span.record_exception(PaymentError(resp.text))
                        span.set_status(trace.StatusCode.ERROR)
                        raise PaymentError(resp.text)

            # Save to database (auto-instrumented by SQLAlchemy instrumentor)
            order = await self._save_order(user_id, items, total)

            span.set_attribute("order.id", order["id"])
            span.add_event("order_created", {"order_id": order["id"]})
            return order

    async def _check_stock(self, sku: str) -> int:
        """Call inventory service — trace context auto-propagated."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"http://inventory-service/stock/{sku}")
            return resp.json()["available"]

# --- Custom context propagation ---

from opentelemetry import context
from opentelemetry.propagate import inject, extract

def propagate_to_message_queue(message: dict) -> dict:
    """Inject trace context into message headers for async messaging."""
    headers = {}
    inject(headers)
    message["_trace_headers"] = headers
    return message

def extract_from_message_queue(message: dict):
    """Extract trace context from message and set as current."""
    headers = message.get("_trace_headers", {})
    ctx = extract(headers)
    return ctx

# Message consumer
async def handle_message(message: dict):
    ctx = extract_from_message_queue(message)
    with tracer.start_as_current_span(
        "process_message",
        context=ctx,
        kind=trace.SpanKind.CONSUMER,
    ):
        await process(message)
```

Trace visualization:
```
order-service: create_order (250ms)
├── order-service: validate_inventory (50ms)
│   ├── inventory-service: GET /stock/SKU001 (15ms)
│   └── inventory-service: GET /stock/SKU002 (12ms)
├── order-service: calculate_total (1ms)
├── order-service: process_payment (120ms)
│   └── payment-service: POST /charge (115ms)
│       └── payment-service: stripe_api_call (100ms)
└── order-service: save_order (30ms)
    └── postgres: INSERT orders (25ms)
```

Key practices:
- Auto-instrument frameworks (FastAPI, SQLAlchemy, httpx) first
- Add manual spans only for business-critical operations
- Propagate context through message queues explicitly
- Set meaningful span attributes and events for debugging'''
    ),
    (
        "devops/metrics-alerting",
        "Show how to implement application metrics with Prometheus in Python. Include custom metrics, histograms, and alerting rules.",
        '''Application metrics with Prometheus client library:

```python
from prometheus_client import (
    Counter, Histogram, Gauge, Summary, Info,
    start_http_server, CollectorRegistry, generate_latest,
    CONTENT_TYPE_LATEST,
)
from functools import wraps
import time
import psutil

# --- Define metrics ---

REGISTRY = CollectorRegistry()

# Request metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
    registry=REGISTRY,
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=REGISTRY,
)

# Business metrics
ORDERS_CREATED = Counter(
    "orders_created_total",
    "Total orders created",
    ["payment_method", "region"],
    registry=REGISTRY,
)

ORDER_VALUE = Histogram(
    "order_value_dollars",
    "Order value in dollars",
    buckets=[10, 25, 50, 100, 250, 500, 1000, 5000],
    registry=REGISTRY,
)

# System metrics
ACTIVE_CONNECTIONS = Gauge(
    "db_active_connections",
    "Active database connections",
    ["pool"],
    registry=REGISTRY,
)

QUEUE_SIZE = Gauge(
    "task_queue_size",
    "Number of pending tasks in queue",
    ["queue_name"],
    registry=REGISTRY,
)

APP_INFO = Info(
    "app",
    "Application metadata",
    registry=REGISTRY,
)
APP_INFO.info({
    "version": "1.2.0",
    "python_version": "3.12",
    "environment": "production",
})

# --- Instrumentation decorators ---

def track_request(method: str, endpoint: str):
    """Decorator to track request metrics."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            status = "500"
            try:
                result = await func(*args, **kwargs)
                status = str(getattr(result, "status_code", 200))
                return result
            except Exception:
                status = "500"
                raise
            finally:
                duration = time.perf_counter() - start
                REQUEST_COUNT.labels(method, endpoint, status).inc()
                REQUEST_DURATION.labels(method, endpoint).observe(duration)
        return wrapper
    return decorator

# --- FastAPI integration ---

from fastapi import FastAPI, Request, Response

app = FastAPI()

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    # Normalize path to avoid cardinality explosion
    # /users/123 → /users/{id}
    path = request.url.path
    for pattern, replacement in [
        (r"/users/\\d+", "/users/{id}"),
        (r"/orders/\\d+", "/orders/{id}"),
    ]:
        import re
        path = re.sub(pattern, replacement, path)

    REQUEST_COUNT.labels(request.method, path, response.status_code).inc()
    REQUEST_DURATION.labels(request.method, path).observe(duration)
    return response

@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(REGISTRY),
        media_type=CONTENT_TYPE_LATEST,
    )

# --- Business metric usage ---

class OrderService:
    def create_order(self, order):
        # ... create order logic ...
        ORDERS_CREATED.labels(
            payment_method=order.payment_method,
            region=order.region,
        ).inc()
        ORDER_VALUE.observe(order.total)

# --- Background metric collector ---

import asyncio

async def collect_system_metrics():
    while True:
        # Database pool metrics
        pool_stats = get_db_pool_stats()
        ACTIVE_CONNECTIONS.labels("primary").set(pool_stats["active"])
        ACTIVE_CONNECTIONS.labels("replica").set(pool_stats["replica_active"])

        # Queue metrics
        for queue_name in ["orders", "emails", "reports"]:
            size = get_queue_size(queue_name)
            QUEUE_SIZE.labels(queue_name).set(size)

        await asyncio.sleep(15)
```

Prometheus alerting rules:
```yaml
# alerts.yml
groups:
  - name: application
    rules:
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m]))
          / sum(rate(http_requests_total[5m])) > 0.01
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Error rate above 1%"
          description: "{{ $value | humanizePercentage }} of requests failing"

      - alert: HighLatency
        expr: |
          histogram_quantile(0.99,
            sum(rate(http_request_duration_seconds_bucket[5m])) by (le)
          ) > 2.0
        for: 5m
        labels:
          severity: warning

      - alert: QueueBacklog
        expr: task_queue_size > 1000
        for: 10m
        labels:
          severity: warning

      - alert: DatabaseConnectionExhaustion
        expr: db_active_connections / db_max_connections > 0.8
        for: 5m
        labels:
          severity: critical
```

Metric naming conventions:
- `_total` suffix for counters
- `_seconds` / `_bytes` for units
- `_bucket` / `_count` / `_sum` auto-generated for histograms
- Keep label cardinality low (<100 values per label)'''
    ),
]
