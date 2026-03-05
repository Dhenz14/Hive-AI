"""OpenTelemetry instrumentation — SDK setup, auto-instrumentation, custom spans, Collector config, and context propagation."""

PAIRS = [
    (
        "observability/otel-sdk-setup",
        "Show how to set up the OpenTelemetry SDK for Python with traces, metrics, and logs including exporters and resource attributes.",
        '''OpenTelemetry SDK setup for traces, metrics, and logs in Python:

```python
# --- otel_setup.py --- Full SDK initialization ---

from __future__ import annotations

import logging
from typing import Optional

from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    ConsoleSpanExporter,
)
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    PeriodicExportingMetricReader,
    ConsoleMetricExporter,
)
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import (
    BatchLogRecordProcessor,
    ConsoleLogExporter,
)
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.semconv.resource import ResourceAttributes


def build_resource(
    service_name: str,
    service_version: str = "0.1.0",
    environment: str = "development",
) -> Resource:
    """Build an OTel Resource with standard semantic conventions."""
    return Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            ResourceAttributes.DEPLOYMENT_ENVIRONMENT: environment,
            ResourceAttributes.HOST_NAME: __import__("socket").gethostname(),
            ResourceAttributes.PROCESS_PID: __import__("os").getpid(),
            ResourceAttributes.TELEMETRY_SDK_LANGUAGE: "python",
        }
    )


def configure_tracing(
    resource: Resource,
    otlp_endpoint: Optional[str] = None,
    console: bool = False,
) -> TracerProvider:
    """Configure the global TracerProvider with exporters."""
    provider = TracerProvider(resource=resource)

    # OTLP gRPC exporter for production
    if otlp_endpoint:
        otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        provider.add_span_processor(
            BatchSpanProcessor(
                otlp_exporter,
                max_queue_size=2048,
                max_export_batch_size=512,
                schedule_delay_millis=5000,
            )
        )

    # Console exporter for local development
    if console:
        provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))

    trace.set_tracer_provider(provider)
    return provider


def configure_metrics(
    resource: Resource,
    otlp_endpoint: Optional[str] = None,
    export_interval_ms: int = 60000,
) -> MeterProvider:
    """Configure the global MeterProvider."""
    readers = []

    if otlp_endpoint:
        readers.append(
            PeriodicExportingMetricReader(
                OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True),
                export_interval_millis=export_interval_ms,
            )
        )
    else:
        readers.append(
            PeriodicExportingMetricReader(
                ConsoleMetricExporter(),
                export_interval_millis=export_interval_ms,
            )
        )

    provider = MeterProvider(resource=resource, metric_readers=readers)
    metrics.set_meter_provider(provider)
    return provider


def configure_logging(
    resource: Resource,
    otlp_endpoint: Optional[str] = None,
) -> LoggerProvider:
    """Configure OTel log bridge — connects Python logging to OTel."""
    provider = LoggerProvider(resource=resource)

    if otlp_endpoint:
        exporter = OTLPLogExporter(endpoint=otlp_endpoint, insecure=True)
    else:
        exporter = ConsoleLogExporter()

    provider.add_log_record_processor(BatchLogRecordProcessor(exporter))

    # Attach OTel handler to Python root logger
    handler = LoggingHandler(level=logging.INFO, logger_provider=provider)
    logging.getLogger().addHandler(handler)

    return provider


def init_telemetry(
    service_name: str,
    otlp_endpoint: Optional[str] = "http://localhost:4317",
    environment: str = "development",
) -> dict:
    """One-call initialization of all three signals."""
    resource = build_resource(service_name, environment=environment)
    tracer_provider = configure_tracing(resource, otlp_endpoint)
    meter_provider = configure_metrics(resource, otlp_endpoint)
    logger_provider = configure_logging(resource, otlp_endpoint)

    return {
        "resource": resource,
        "tracer_provider": tracer_provider,
        "meter_provider": meter_provider,
        "logger_provider": logger_provider,
    }
```

```python
# --- Usage in application entry point ---

from otel_setup import init_telemetry
from opentelemetry import trace, metrics

# Initialize all signals once at startup
providers = init_telemetry(
    service_name="order-service",
    otlp_endpoint="http://otel-collector:4317",
    environment="production",
)

# Acquire instrumentors
tracer = trace.get_tracer("order-service", "1.0.0")
meter = metrics.get_meter("order-service", "1.0.0")

# Create metrics instruments
order_counter = meter.create_counter(
    name="orders.created",
    description="Number of orders created",
    unit="1",
)

order_duration = meter.create_histogram(
    name="orders.processing_duration",
    description="Time to process an order",
    unit="ms",
)

# Use in business logic
with tracer.start_as_current_span("process_order") as span:
    span.set_attribute("order.id", "ORD-12345")
    order_counter.add(1, {"order.type": "standard"})
    # ... process order ...
```

```python
# --- Graceful shutdown ---

import atexit
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk._logs import LoggerProvider


def register_shutdown(providers: dict) -> None:
    """Ensure all pending telemetry is flushed on exit."""
    def _shutdown():
        tp: TracerProvider = providers["tracer_provider"]
        mp: MeterProvider = providers["meter_provider"]
        lp: LoggerProvider = providers["logger_provider"]

        tp.force_flush(timeout_millis=10000)
        tp.shutdown()
        mp.force_flush(timeout_millis=10000)
        mp.shutdown()
        lp.force_flush(timeout_millis=10000)
        lp.shutdown()

    atexit.register(_shutdown)
```

| Component | Class | Purpose |
|-----------|-------|---------|
| Resource | `Resource` | Service identity (name, version, env) |
| TracerProvider | `TracerProvider` | Creates tracers, manages span processors |
| MeterProvider | `MeterProvider` | Creates meters, manages metric readers |
| LoggerProvider | `LoggerProvider` | Bridges Python logging to OTel |
| BatchSpanProcessor | `BatchSpanProcessor` | Batches spans before export (perf) |
| OTLP Exporter | `OTLPSpanExporter` | Sends data via gRPC to Collector |

Key patterns:
1. Build a single `Resource` shared across all three signals for consistent identity
2. Use `BatchSpanProcessor` (never `SimpleSpanProcessor`) in production for batched export
3. Configure OTLP exporters pointing at the Collector, not directly at backends
4. Register shutdown hooks to flush buffered telemetry before process exit
5. Separate instrument creation (counter, histogram) from recording to allow reuse'''
    ),
    (
        "observability/otel-auto-instrumentation",
        "Demonstrate auto-instrumentation for a Python FastAPI application with SQLAlchemy and outgoing HTTP requests.",
        '''Auto-instrumentation for FastAPI + SQLAlchemy + requests using OpenTelemetry:

```python
# --- instrument.py --- Auto-instrumentation bootstrap ---

from __future__ import annotations

from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor

from otel_setup import init_telemetry


def instrument_app(app, engine=None) -> None:
    """Apply auto-instrumentation to all libraries.

    Call this ONCE at application startup, after creating the FastAPI app
    and SQLAlchemy engine.
    """
    # 1. Initialize SDK (traces, metrics, logs)
    init_telemetry(
        service_name="user-service",
        otlp_endpoint="http://otel-collector:4317",
        environment="production",
    )

    # 2. FastAPI — instruments all routes automatically
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="health,readiness,metrics",  # skip noisy endpoints
        server_request_hook=_server_request_hook,
        client_request_hook=_client_request_hook,
        client_response_hook=_client_response_hook,
    )

    # 3. SQLAlchemy — instruments all DB queries
    if engine:
        SQLAlchemyInstrumentor().instrument(
            engine=engine,
            enable_commenter=True,     # adds SQL comments with trace context
            commenter_options={
                "db_driver": True,
                "route": True,
                "framework": True,
            },
        )

    # 4. Outgoing HTTP — instruments requests library
    RequestsInstrumentor().instrument(
        excluded_urls="health,readiness",
        request_hook=_outgoing_request_hook,
        response_hook=_outgoing_response_hook,
    )

    # 5. Redis — instruments redis-py
    RedisInstrumentor().instrument()

    # 6. Logging — adds trace_id and span_id to log records
    LoggingInstrumentor().instrument(
        set_logging_format=True,
        log_level=__import__("logging").INFO,
    )


def _server_request_hook(span: trace.Span, scope: dict) -> None:
    """Enrich incoming request spans with custom attributes."""
    if span and span.is_recording():
        headers = dict(scope.get("headers", []))
        # Extract user ID from auth header if present
        user_id = headers.get(b"x-user-id", b"").decode()
        if user_id:
            span.set_attribute("enduser.id", user_id)


def _client_request_hook(span: trace.Span, scope: dict) -> None:
    """Hook for client request spans (ASGI sub-requests)."""
    pass


def _client_response_hook(span: trace.Span, message: dict) -> None:
    """Record response status on the span."""
    pass


def _outgoing_request_hook(span: trace.Span, request) -> None:
    """Enrich outgoing HTTP spans."""
    if span and span.is_recording():
        span.set_attribute("http.request.service", "user-service")


def _outgoing_response_hook(span: trace.Span, request, response) -> None:
    """Record response details for outgoing calls."""
    if span and span.is_recording() and response:
        if response.status_code >= 400:
            span.set_attribute("http.response.error", True)
```

```python
# --- main.py --- FastAPI application ---

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import create_engine, Column, Integer, String
from sqlalchemy.orm import Session, sessionmaker, declarative_base
import requests

app = FastAPI(title="User Service")

# Database setup
DATABASE_URL = "postgresql://user:pass@db:5432/users"
engine = create_engine(DATABASE_URL, pool_size=10, max_overflow=20)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    email = Column(String(255), unique=True, nullable=False)


# Apply auto-instrumentation BEFORE defining routes
from instrument import instrument_app
instrument_app(app, engine=engine)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    """Auto-instrumented: creates spans for HTTP + DB automatically."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Outgoing HTTP call — auto-instrumented by RequestsInstrumentor
    profile = requests.get(
        f"http://profile-service:8001/profiles/{user_id}",
        timeout=5,
    )
    return {"user": user.name, "profile": profile.json()}


@app.get("/health")
def health():
    """Excluded from tracing via excluded_urls config."""
    return {"status": "ok"}
```

```bash
# --- Alternative: zero-code instrumentation via CLI ---
# Install all auto-instrumentation packages at once:
pip install opentelemetry-distro opentelemetry-exporter-otlp
opentelemetry-bootstrap -a install

# Run with auto-instrumentation (no code changes needed):
OTEL_SERVICE_NAME=user-service \
OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317 \
OTEL_EXPORTER_OTLP_PROTOCOL=grpc \
OTEL_TRACES_SAMPLER=parentbased_traceidratio \
OTEL_TRACES_SAMPLER_ARG=0.1 \
OTEL_PYTHON_LOG_CORRELATION=true \
OTEL_PYTHON_LOGGING_AUTO_INSTRUMENTATION_ENABLED=true \
OTEL_PYTHON_DISABLED_INSTRUMENTATIONS=urllib3 \
opentelemetry-instrument uvicorn main:app --host 0.0.0.0 --port 8000

# Dockerfile for production
# FROM python:3.12-slim
# RUN pip install opentelemetry-distro opentelemetry-exporter-otlp && \
#     opentelemetry-bootstrap -a install
# ENTRYPOINT ["opentelemetry-instrument", "uvicorn", "main:app"]
```

| Instrumentation | Package | What it captures |
|----------------|---------|-----------------|
| FastAPI | `opentelemetry-instrumentation-fastapi` | Inbound HTTP spans, route, status |
| SQLAlchemy | `opentelemetry-instrumentation-sqlalchemy` | DB query spans, statement, duration |
| requests | `opentelemetry-instrumentation-requests` | Outbound HTTP spans, URL, status |
| Redis | `opentelemetry-instrumentation-redis` | Redis command spans |
| Logging | `opentelemetry-instrumentation-logging` | Adds trace_id/span_id to log records |
| Zero-code | `opentelemetry-distro` | Wraps all of the above via CLI |

Key patterns:
1. Call `instrument_app()` once at startup before routes are exercised
2. Exclude health/readiness endpoints from tracing to reduce noise
3. Use hooks (`server_request_hook`) to enrich spans with domain context (user ID, tenant)
4. Enable SQLAlchemy `commenter` to embed trace context in SQL comments for DBA visibility
5. For zero-code instrumentation, use `opentelemetry-instrument` CLI with env vars'''
    ),
    (
        "observability/otel-custom-spans",
        "Show how to create custom spans with attributes, events, status, and exception recording in OpenTelemetry.",
        '''Custom span management in OpenTelemetry for rich domain-specific telemetry:

```python
# --- custom_spans.py --- Rich span usage patterns ---

from __future__ import annotations

import time
from typing import Any
from contextlib import contextmanager
from functools import wraps

from opentelemetry import trace
from opentelemetry.trace import StatusCode, Status, SpanKind
from opentelemetry.semconv.trace import SpanAttributes

tracer = trace.get_tracer("payment-service", "2.1.0")


# --- Pattern 1: Context-manager spans with attributes ---

def process_payment(order_id: str, amount: float, currency: str) -> dict:
    """Manually instrumented payment processing."""
    with tracer.start_as_current_span(
        "process_payment",
        kind=SpanKind.INTERNAL,
        attributes={
            "payment.order_id": order_id,
            "payment.amount": amount,
            "payment.currency": currency,
        },
    ) as span:
        # Add event for audit trail
        span.add_event("payment.initiated", {
            "payment.method": "credit_card",
            "payment.gateway": "stripe",
        })

        try:
            # Step 1: Authorize
            auth_result = _authorize(order_id, amount, currency, span)

            # Step 2: Capture
            capture_result = _capture(auth_result["auth_id"], span)

            span.set_status(Status(StatusCode.OK))
            span.add_event("payment.completed", {
                "payment.transaction_id": capture_result["txn_id"],
            })
            return capture_result

        except PaymentDeclinedError as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e, attributes={
                "payment.decline_code": e.decline_code,
                "payment.retry_eligible": e.retryable,
            })
            raise

        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, f"Unexpected: {e}"))
            span.record_exception(e)
            raise


def _authorize(
    order_id: str, amount: float, currency: str, parent_span: trace.Span
) -> dict:
    """Child span for the authorization step."""
    with tracer.start_as_current_span(
        "payment.authorize",
        kind=SpanKind.CLIENT,
        attributes={
            SpanAttributes.RPC_SYSTEM: "grpc",
            SpanAttributes.RPC_SERVICE: "PaymentGateway",
            SpanAttributes.RPC_METHOD: "Authorize",
            "payment.order_id": order_id,
        },
    ) as span:
        start = time.monotonic()
        # ... call payment gateway ...
        latency_ms = (time.monotonic() - start) * 1000
        span.set_attribute("payment.gateway_latency_ms", latency_ms)
        return {"auth_id": "AUTH-9876", "status": "approved"}


def _capture(auth_id: str, parent_span: trace.Span) -> dict:
    """Child span for the capture step."""
    with tracer.start_as_current_span(
        "payment.capture",
        kind=SpanKind.CLIENT,
    ) as span:
        span.set_attribute("payment.auth_id", auth_id)
        return {"txn_id": "TXN-5432", "status": "captured"}


class PaymentDeclinedError(Exception):
    def __init__(self, message: str, decline_code: str, retryable: bool):
        super().__init__(message)
        self.decline_code = decline_code
        self.retryable = retryable
```

```python
# --- Pattern 2: Decorator-based instrumentation ---

from opentelemetry import trace
from functools import wraps
from typing import Callable, TypeVar, ParamSpec

P = ParamSpec("P")
T = TypeVar("T")

tracer = trace.get_tracer("inventory-service")


def traced(
    span_name: str | None = None,
    kind: SpanKind = SpanKind.INTERNAL,
    record_args: bool = False,
    attributes: dict[str, Any] | None = None,
) -> Callable:
    """Decorator that wraps a function in an OTel span.

    Usage:
        @traced("check_stock", record_args=True)
        def check_stock(sku: str, warehouse: str) -> int:
            ...
    """
    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        name = span_name or f"{func.__module__}.{func.__qualname__}"

        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            span_attrs = dict(attributes or {})
            span_attrs["code.function"] = func.__qualname__
            span_attrs["code.namespace"] = func.__module__

            if record_args:
                # Record safe string representations
                span_attrs["code.args"] = str(args)[:256]
                span_attrs["code.kwargs"] = str(kwargs)[:256]

            with tracer.start_as_current_span(
                name, kind=kind, attributes=span_attrs
            ) as span:
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    span.record_exception(e)
                    raise

        return wrapper
    return decorator


# Usage examples
@traced("inventory.check_stock", record_args=True)
def check_stock(sku: str, warehouse: str = "US-EAST") -> int:
    """Automatically traced with arguments recorded."""
    return 42


@traced("inventory.reserve", attributes={"inventory.operation": "reserve"})
def reserve_stock(sku: str, quantity: int) -> bool:
    """Traced with static attributes."""
    span = trace.get_current_span()
    span.set_attribute("inventory.sku", sku)
    span.set_attribute("inventory.quantity", quantity)
    span.add_event("stock.reserved", {"inventory.remaining": 38})
    return True
```

```python
# --- Pattern 3: Async spans and span links ---

import asyncio
from opentelemetry import trace, context
from opentelemetry.trace import SpanKind, Link

tracer = trace.get_tracer("order-service")


async def handle_order_event(event: dict) -> None:
    """Process an async event with a link to the producing span."""
    # Extract trace context from the event (producer side)
    producer_context = trace.get_current_span().get_span_context()

    # Create a new trace linked to the producer
    producer_link = Link(
        context=producer_context,
        attributes={"link.type": "producer", "event.type": event["type"]},
    )

    with tracer.start_as_current_span(
        "order.process_event",
        kind=SpanKind.CONSUMER,
        links=[producer_link],
        attributes={
            "messaging.system": "kafka",
            "messaging.destination": "orders",
            "messaging.operation": "process",
            "messaging.message.id": event["id"],
        },
    ) as span:
        await _process(event)
        span.add_event("event.processed")


async def _process(event: dict) -> None:
    """Simulated processing with nested async spans."""
    with tracer.start_as_current_span("order.validate") as span:
        await asyncio.sleep(0.01)  # simulate I/O
        span.set_attribute("order.valid", True)

    with tracer.start_as_current_span("order.persist") as span:
        await asyncio.sleep(0.02)
        span.set_attribute("order.persisted", True)


# --- Pattern 4: Baggage for cross-cutting concerns ---
from opentelemetry.baggage import set_baggage, get_baggage

def set_tenant_context(tenant_id: str) -> None:
    """Set tenant ID as baggage — propagated to all downstream services."""
    ctx = set_baggage("tenant.id", tenant_id)
    context.attach(ctx)

def get_tenant_id() -> str | None:
    """Retrieve tenant ID from baggage in any downstream service."""
    return get_baggage("tenant.id")
```

| Span Feature | Method | When to use |
|-------------|--------|-------------|
| Attributes | `span.set_attribute(k, v)` | Filterable/indexable metadata |
| Events | `span.add_event(name, attrs)` | Timestamped logs within a span |
| Status | `span.set_status(Status(...))` | Mark OK or ERROR |
| Exception | `span.record_exception(e)` | Capture stack trace as event |
| Links | `Link(context, attrs)` | Connect causally-related traces |
| Baggage | `set_baggage(k, v)` | Cross-service context (tenant, user) |
| SpanKind | `SpanKind.CLIENT/SERVER/...` | Classify span role in the graph |

Key patterns:
1. Always set `SpanKind` — helps backends render dependency graphs correctly
2. Use `record_exception()` with custom attributes for structured error context
3. Add events for significant business milestones (payment initiated, stock reserved)
4. Use the `@traced` decorator for uniform instrumentation across service methods
5. Use span links for async event processing where producer and consumer are separate traces'''
    ),
    (
        "observability/otel-collector-config",
        "Show how to configure the OpenTelemetry Collector with receivers, processors, and exporters for a production pipeline.",
        '''OpenTelemetry Collector configuration for a production observability pipeline:

```yaml
# --- otel-collector-config.yaml --- Production Collector pipeline ---

# Receivers: how data gets INTO the collector
receivers:
  otlp:
    protocols:
      grpc:
        endpoint: 0.0.0.0:4317
        max_recv_msg_size_mib: 16
        keepalive:
          server_parameters:
            max_connection_age: 60s
      http:
        endpoint: 0.0.0.0:4318
        cors:
          allowed_origins: ["*"]
          allowed_headers: ["*"]

  # Scrape Prometheus-format metrics from services
  prometheus:
    config:
      scrape_configs:
        - job_name: "app-metrics"
          scrape_interval: 15s
          static_configs:
            - targets: ["app:8080"]
          metrics_path: /metrics

  # Host metrics (CPU, memory, disk, network)
  hostmetrics:
    collection_interval: 30s
    scrapers:
      cpu:
        metrics:
          system.cpu.utilization:
            enabled: true
      memory: {}
      disk: {}
      network: {}

  # Collect container logs via filelog
  filelog:
    include: ["/var/log/containers/*.log"]
    operators:
      - type: json_parser
        timestamp:
          parse_from: attributes.time
          layout: "%Y-%m-%dT%H:%M:%S.%LZ"
      - type: move
        from: attributes.log
        to: body

# Processors: transform, filter, and enrich telemetry
processors:
  # Add metadata
  resource:
    attributes:
      - key: deployment.environment
        value: production
        action: upsert
      - key: collector.version
        value: "0.95.0"
        action: insert

  # Batch for export efficiency
  batch:
    send_batch_size: 8192
    send_batch_max_size: 16384
    timeout: 5s

  # Memory limiter to prevent OOM
  memory_limiter:
    check_interval: 1s
    limit_mib: 1500
    spike_limit_mib: 500

  # Tail-based sampling: keep errors + 10% of success
  tail_sampling:
    decision_wait: 10s
    num_traces: 100000
    expected_new_traces_per_sec: 1000
    policies:
      - name: errors
        type: status_code
        status_code: {status_codes: [ERROR]}
      - name: slow-requests
        type: latency
        latency: {threshold_ms: 2000}
      - name: probabilistic
        type: probabilistic
        probabilistic: {sampling_percentage: 10}

  # Drop noisy health-check spans
  filter/traces:
    error_mode: ignore
    traces:
      span:
        - 'attributes["http.route"] == "/health"'
        - 'attributes["http.route"] == "/readiness"'
        - 'attributes["http.route"] == "/metrics"'

  # Transform attributes
  attributes/traces:
    actions:
      - key: http.request.header.authorization
        action: delete    # never export auth headers
      - key: db.statement
        action: hash      # hash SQL to avoid PII in traces

# Exporters: where telemetry goes
exporters:
  # Jaeger for traces
  otlp/jaeger:
    endpoint: jaeger:4317
    tls:
      insecure: true

  # Prometheus remote-write for metrics
  prometheusremotewrite:
    endpoint: "http://mimir:9009/api/v1/push"
    resource_to_telemetry_conversion:
      enabled: true
    retry_on_failure:
      enabled: true
      max_elapsed_time: 120s

  # Loki for logs
  loki:
    endpoint: "http://loki:3100/loki/api/v1/push"
    labels:
      attributes:
        service.name: "service"
        severity: "severity"

  # Debug exporter for troubleshooting
  debug:
    verbosity: basic
    sampling_initial: 5
    sampling_thereafter: 200

# Extensions: health, metrics, profiling for the collector itself
extensions:
  health_check:
    endpoint: 0.0.0.0:13133
  pprof:
    endpoint: 0.0.0.0:1777
  zpages:
    endpoint: 0.0.0.0:55679

# Service: wire everything together
service:
  extensions: [health_check, pprof, zpages]
  telemetry:
    logs:
      level: info
    metrics:
      address: 0.0.0.0:8888

  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, filter/traces, attributes/traces, tail_sampling, batch]
      exporters: [otlp/jaeger]

    metrics:
      receivers: [otlp, prometheus, hostmetrics]
      processors: [memory_limiter, resource, batch]
      exporters: [prometheusremotewrite]

    logs:
      receivers: [otlp, filelog]
      processors: [memory_limiter, resource, batch]
      exporters: [loki]
```

```yaml
# --- docker-compose.yaml --- Collector deployment ---

version: "3.9"
services:
  otel-collector:
    image: otel/opentelemetry-collector-contrib:0.95.0
    command: ["--config=/etc/otel/config.yaml"]
    volumes:
      - ./otel-collector-config.yaml:/etc/otel/config.yaml:ro
      - /var/log/containers:/var/log/containers:ro
    ports:
      - "4317:4317"    # OTLP gRPC
      - "4318:4318"    # OTLP HTTP
      - "8888:8888"    # Collector metrics
      - "13133:13133"  # Health check
    deploy:
      resources:
        limits:
          memory: 2g
          cpus: "1.0"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:13133"]
      interval: 10s
      timeout: 5s
      retries: 3
    restart: unless-stopped

  jaeger:
    image: jaegertracing/all-in-one:1.54
    ports:
      - "16686:16686"  # Jaeger UI
      - "4317"         # OTLP (internal)

  loki:
    image: grafana/loki:2.9.4
    ports:
      - "3100:3100"

  grafana:
    image: grafana/grafana:10.3.1
    ports:
      - "3000:3000"
    environment:
      GF_AUTH_ANONYMOUS_ENABLED: "true"
      GF_AUTH_ANONYMOUS_ORG_ROLE: Admin
```

```python
# --- collector_health.py --- Monitoring the Collector itself ---

import requests
from dataclasses import dataclass


@dataclass
class CollectorHealth:
    status: str
    uptime: str
    pipelines: dict[str, str]


def check_collector_health(endpoint: str = "http://localhost:13133") -> CollectorHealth:
    """Check OTel Collector health endpoint."""
    resp = requests.get(endpoint, timeout=5)
    resp.raise_for_status()
    data = resp.json()
    return CollectorHealth(
        status=data.get("status", "unknown"),
        uptime=data.get("uptime", "unknown"),
        pipelines={},
    )


def get_collector_metrics(endpoint: str = "http://localhost:8888/metrics") -> dict:
    """Scrape Collector internal Prometheus metrics."""
    resp = requests.get(endpoint, timeout=5)
    lines = resp.text.splitlines()
    metrics = {}
    for line in lines:
        if line.startswith("#"):
            continue
        parts = line.split(" ")
        if len(parts) == 2:
            metrics[parts[0]] = float(parts[1])
    # Key metrics to monitor:
    # otelcol_exporter_sent_spans - spans successfully exported
    # otelcol_exporter_send_failed_spans - export failures
    # otelcol_processor_dropped_spans - spans dropped by processors
    # otelcol_receiver_accepted_spans - spans received
    return metrics
```

| Pipeline Stage | Component | Purpose |
|---------------|-----------|---------|
| Receivers | `otlp`, `prometheus`, `filelog` | Ingest data from apps and infrastructure |
| Processors | `memory_limiter` | Prevent Collector OOM under load |
| Processors | `batch` | Group telemetry for efficient export |
| Processors | `tail_sampling` | Keep errors + slow + 10% sample |
| Processors | `filter` | Drop noisy health-check spans |
| Processors | `attributes` | Scrub PII, hash sensitive fields |
| Exporters | `otlp/jaeger`, `prometheusremotewrite`, `loki` | Send to backends |

Key patterns:
1. Always place `memory_limiter` first in every pipeline to prevent OOM
2. Use `tail_sampling` for intelligent sampling — keep all errors and slow requests
3. Filter health/readiness spans at the Collector, not in application code
4. Hash or delete sensitive attributes (auth headers, SQL with PII) before export
5. Use `contrib` image for full processor/exporter support (not the core image)'''
    ),
    (
        "observability/otel-context-propagation",
        "Explain OpenTelemetry context propagation across services including W3C TraceContext, custom propagators, and cross-service correlation.",
        '''Context propagation across services with OpenTelemetry:

```python
# --- propagation_setup.py --- Configure propagators ---

from opentelemetry import context
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.composite import CompositeTextMapPropagator
from opentelemetry.propagators.textmap import (
    TextMapPropagator,
    CarrierT,
    Getter,
    Setter,
    default_getter,
    default_setter,
)
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry.propagators.b3 import B3MultiFormat
from typing import Optional, Sequence


def configure_propagation(formats: list[str] | None = None) -> None:
    """Configure global text map propagators.

    Args:
        formats: List of propagation formats to enable.
                 Options: "tracecontext", "baggage", "b3", "b3multi", "custom"
    """
    if formats is None:
        formats = ["tracecontext", "baggage"]

    propagators: list[TextMapPropagator] = []
    for fmt in formats:
        if fmt == "tracecontext":
            propagators.append(TraceContextTextMapPropagator())
        elif fmt == "baggage":
            propagators.append(W3CBaggagePropagator())
        elif fmt in ("b3", "b3multi"):
            propagators.append(B3MultiFormat())
        elif fmt == "custom":
            propagators.append(TenantPropagator())

    set_global_textmap(CompositeTextMapPropagator(propagators))


class TenantPropagator(TextMapPropagator):
    """Custom propagator that carries tenant context across services.

    Injects/extracts 'x-tenant-id' header for multi-tenant routing.
    """

    TENANT_HEADER = "x-tenant-id"

    def inject(
        self,
        carrier: CarrierT,
        context: Optional[context.Context] = None,
        setter: Setter = default_setter,
    ) -> None:
        tenant_id = _get_tenant_from_context(context)
        if tenant_id:
            setter.set(carrier, self.TENANT_HEADER, tenant_id)

    def extract(
        self,
        carrier: CarrierT,
        context: Optional[context.Context] = None,
        getter: Getter = default_getter,
    ) -> context.Context:
        tenant_id = getter.get(carrier, self.TENANT_HEADER)
        if tenant_id:
            return _set_tenant_in_context(tenant_id[0] if isinstance(tenant_id, list) else tenant_id, context)
        return context or context.get_current()

    @property
    def fields(self) -> set[str]:
        return {self.TENANT_HEADER}


# Context key for tenant
from opentelemetry.context import create_key
_TENANT_KEY = create_key("tenant-id")

def _get_tenant_from_context(ctx: Optional[context.Context] = None) -> Optional[str]:
    return context.get_value(_TENANT_KEY, ctx)

def _set_tenant_in_context(tenant_id: str, ctx: Optional[context.Context] = None) -> context.Context:
    return context.set_value(_TENANT_KEY, tenant_id, ctx)
```

```python
# --- cross_service.py --- Propagation across HTTP, gRPC, and messaging ---

import requests
from typing import Any
from opentelemetry import trace, context
from opentelemetry.propagate import inject, extract
from opentelemetry.trace import SpanKind

tracer = trace.get_tracer("gateway-service")


# --- HTTP propagation (requests library) ---

def call_downstream_http(url: str, payload: dict) -> dict:
    """Make an HTTP call with trace context propagated via headers."""
    with tracer.start_as_current_span(
        "http.call",
        kind=SpanKind.CLIENT,
        attributes={"http.url": url, "http.method": "POST"},
    ):
        headers: dict[str, str] = {}
        # Inject W3C traceparent + tracestate into HTTP headers
        inject(headers)
        # headers now contains:
        #   traceparent: 00-<trace_id>-<span_id>-01
        #   tracestate: <vendor-specific>
        #   x-tenant-id: <tenant> (if custom propagator active)

        response = requests.post(url, json=payload, headers=headers, timeout=10)
        return response.json()


# --- Server-side extraction (FastAPI middleware) ---

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


class TracePropagationMiddleware(BaseHTTPMiddleware):
    """Extract trace context from incoming requests and activate it."""

    async def dispatch(self, request: Request, call_next):
        # Extract context from incoming HTTP headers
        carrier = dict(request.headers)
        ctx = extract(carrier)

        # Activate the extracted context for this request
        token = context.attach(ctx)
        try:
            with tracer.start_as_current_span(
                f"{request.method} {request.url.path}",
                kind=SpanKind.SERVER,
                context=ctx,
                attributes={
                    "http.method": request.method,
                    "http.url": str(request.url),
                    "http.route": request.url.path,
                },
            ):
                response = await call_next(request)
                return response
        finally:
            context.detach(token)


# --- Kafka / message queue propagation ---

def produce_message(topic: str, key: str, value: dict) -> None:
    """Produce a Kafka message with trace context in headers."""
    with tracer.start_as_current_span(
        f"kafka.produce.{topic}",
        kind=SpanKind.PRODUCER,
        attributes={
            "messaging.system": "kafka",
            "messaging.destination": topic,
            "messaging.destination_kind": "topic",
        },
    ):
        headers: dict[str, str] = {}
        inject(headers)

        # Convert to Kafka header format: list of (key, bytes) tuples
        kafka_headers = [
            (k, v.encode("utf-8")) for k, v in headers.items()
        ]
        # producer.send(topic, key=key, value=value, headers=kafka_headers)


def consume_message(raw_headers: list[tuple[str, bytes]], body: dict) -> None:
    """Consume a Kafka message and extract trace context."""
    # Convert Kafka headers back to dict
    carrier = {k: v.decode("utf-8") for k, v in raw_headers}
    ctx = extract(carrier)

    with tracer.start_as_current_span(
        "kafka.consume",
        kind=SpanKind.CONSUMER,
        context=ctx,
        attributes={
            "messaging.system": "kafka",
            "messaging.operation": "process",
        },
    ):
        # Process message — all child spans are linked to producer trace
        _handle_message(body)


def _handle_message(body: dict) -> None:
    pass
```

```python
# --- manual_propagation.py --- Advanced patterns ---

from opentelemetry import trace, context
from opentelemetry.propagate import inject, extract
from opentelemetry.trace import SpanKind, Link
import threading
import asyncio


# --- Pattern: Propagate context across threads ---

def submit_background_task(func, *args) -> threading.Thread:
    """Run a function in a background thread with trace context."""
    # Capture current context
    ctx = context.get_current()

    def _wrapper():
        # Attach captured context in the new thread
        token = context.attach(ctx)
        try:
            func(*args)
        finally:
            context.detach(token)

    thread = threading.Thread(target=_wrapper)
    thread.start()
    return thread


# --- Pattern: Propagate context across async boundaries ---

async def run_parallel_with_context(tasks: list) -> list:
    """Run async tasks with shared trace context."""
    ctx = context.get_current()

    async def _wrap(coro):
        token = context.attach(ctx)
        try:
            return await coro
        finally:
            context.detach(token)

    return await asyncio.gather(*[_wrap(t) for t in tasks])


# --- Pattern: Serialize context for queue/DB storage ---

def serialize_context() -> dict[str, str]:
    """Serialize current trace context to a dict (for DB/queue storage)."""
    carrier: dict[str, str] = {}
    inject(carrier)
    return carrier


def restore_context(carrier: dict[str, str]) -> context.Context:
    """Restore trace context from a serialized dict."""
    return extract(carrier)


# Example: store trace context with a background job
def enqueue_job(job_type: str, payload: dict) -> str:
    """Enqueue a job with trace context preserved."""
    job = {
        "type": job_type,
        "payload": payload,
        "trace_context": serialize_context(),  # Store context
    }
    # db.jobs.insert(job)
    return "job-123"


def process_job(job: dict) -> None:
    """Process a job and restore the original trace context."""
    ctx = restore_context(job["trace_context"])
    token = context.attach(ctx)
    try:
        with trace.get_tracer("worker").start_as_current_span(
            f"job.{job['type']}",
            kind=SpanKind.CONSUMER,
        ) as span:
            span.set_attribute("job.type", job["type"])
            # Process — child spans link back to original request
    finally:
        context.detach(token)
```

| Propagation Format | Header(s) | Use case |
|-------------------|-----------|----------|
| W3C TraceContext | `traceparent`, `tracestate` | Standard — use by default |
| W3C Baggage | `baggage` | Cross-service key-value pairs |
| B3 (Zipkin) | `X-B3-TraceId`, `X-B3-SpanId`, ... | Legacy Zipkin compatibility |
| B3 Single | `b3` | Compact single-header variant |
| Custom | Any header | Tenant ID, feature flags |

Key patterns:
1. Always configure propagators at startup — default is W3C TraceContext + Baggage
2. Use `inject()` on the client side before sending requests, `extract()` on the server side
3. For message queues, serialize context into message headers (not the payload)
4. When crossing thread boundaries, capture and re-attach context explicitly
5. Serialize context to a dict for storage in databases or job queues for deferred processing'''
    ),
]
