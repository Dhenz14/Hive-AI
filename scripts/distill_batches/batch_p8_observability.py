"""
Batch P8 — Observability and Monitoring Deep Dive
Covers: OpenTelemetry instrumentation, distributed tracing, metrics/alerting,
structured logging, chaos engineering and reliability.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    # --- 1. OpenTelemetry Instrumentation ---
    (
        "observability/opentelemetry-instrumentation",
        "Explain OpenTelemetry instrumentation in depth covering traces, metrics, and logs correlation with the OTel SDK, including auto and manual instrumentation, span attributes, custom metrics such as counters histograms and gauges, and context propagation across services using W3C trace context headers.",
        r"""# OpenTelemetry Instrumentation: Traces, Metrics, and Logs Correlation

## Why OpenTelemetry Is the Industry Standard

**OpenTelemetry** (OTel) has become the de facto standard for observability instrumentation **because** it provides a single, vendor-neutral framework that unifies traces, metrics, and logs under one coherent API. Before OTel, teams had to juggle incompatible libraries — Jaeger for tracing, Prometheus client for metrics, and various structured logging libraries — each with its own context propagation mechanism. This fragmentation meant that correlating a slow database query (visible in traces) with a spike in error rate (visible in metrics) and the corresponding error log required manual effort and often different dashboards.

**The fundamental value proposition** of OpenTelemetry is the correlation of all three signals through shared context. Every trace ID that flows through your system can link a span to the metrics emitted during that span's execution and to the log entries produced within that span's scope. This is **best practice** for production observability, **however** achieving full correlation requires careful instrumentation setup that many teams get wrong.

## Setting Up the OTel SDK

### Provider Configuration and Resource Attributes

The first step is configuring the **TracerProvider**, **MeterProvider**, and **LoggerProvider** with proper resource attributes. Resource attributes describe the service emitting telemetry — **therefore** they appear on every span, metric, and log, enabling filtering and grouping in your observability backend.

```python
import logging
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.flask import FlaskInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from typing import Optional


def configure_opentelemetry(
    service_name: str,
    service_version: str = "1.0.0",
    otlp_endpoint: str = "http://localhost:4317",
    environment: str = "production",
) -> None:
    # Build the resource that identifies this service
    resource = Resource.create(
        {
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            "deployment.environment": environment,
            "host.name": __import__("socket").gethostname(),
        }
    )

    # --- Traces ---
    tracer_provider = TracerProvider(resource=resource)
    span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
    tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
    trace.set_tracer_provider(tracer_provider)

    # --- Metrics ---
    metric_reader = PeriodicExportingMetricReader(
        OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True),
        export_interval_millis=15000,  # Export every 15 seconds
    )
    meter_provider = MeterProvider(resource=resource, metric_readers=[metric_reader])
    metrics.set_meter_provider(meter_provider)

    # --- Logs ---
    logger_provider = LoggerProvider(resource=resource)
    log_exporter = OTLPLogExporter(endpoint=otlp_endpoint, insecure=True)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(log_exporter))

    # Bridge Python logging to OTel
    handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    logging.getLogger().addHandler(handler)
```

A **common mistake** is forgetting to set the resource attributes, which leads to telemetry data arriving at your backend without any service identification. This makes it nearly impossible to filter traces by service in a microservices environment.

### Auto-Instrumentation vs. Manual Instrumentation

**Auto-instrumentation** patches popular libraries (Flask, Django, requests, SQLAlchemy, psycopg2, redis) to emit spans automatically. This is the **best practice** starting point **because** it captures 80% of useful telemetry with zero code changes. **However**, auto-instrumentation alone misses business-specific context — you need **manual instrumentation** to add custom spans for domain logic, attach semantic attributes, and record business metrics.

```python
from opentelemetry import trace, metrics
from opentelemetry.trace import StatusCode, Status
from opentelemetry.metrics import Counter, Histogram, UpDownCounter
from typing import Dict, Any, Optional
import time

# Get a tracer and meter for this module
tracer = trace.get_tracer("order.service", "1.0.0")
meter = metrics.get_meter("order.service", "1.0.0")

# Custom metrics — counters, histograms, and gauges
orders_created: Counter = meter.create_counter(
    name="orders.created.total",
    description="Total number of orders created",
    unit="1",
)

order_value_histogram: Histogram = meter.create_histogram(
    name="orders.value.dollars",
    description="Distribution of order values in dollars",
    unit="USD",
)

active_orders_gauge: UpDownCounter = meter.create_up_down_counter(
    name="orders.active.count",
    description="Number of currently active (unfulfilled) orders",
    unit="1",
)


def process_order(order_data: Dict[str, Any], user_id: str) -> Dict[str, Any]:
    # Manual span with rich attributes for business context
    with tracer.start_as_current_span(
        "process_order",
        attributes={
            "order.user_id": user_id,
            "order.item_count": len(order_data.get("items", [])),
            "order.payment_method": order_data.get("payment_method", "unknown"),
        },
    ) as span:
        try:
            # Validate order — child span for sub-operation
            with tracer.start_as_current_span("validate_order") as validate_span:
                validated = validate_order_items(order_data)
                validate_span.set_attribute("order.valid", validated)
                if not validated:
                    span.set_status(Status(StatusCode.ERROR, "Validation failed"))
                    span.add_event("order_validation_failed", {
                        "reason": "invalid_items",
                        "user_id": user_id,
                    })
                    return {"status": "error", "message": "Validation failed"}

            # Calculate total and record business metrics
            total = calculate_order_total(order_data)
            span.set_attribute("order.total_dollars", total)

            # Record metrics with attributes for dimensional analysis
            orders_created.add(1, {"payment_method": order_data.get("payment_method", "unknown")})
            order_value_histogram.record(total, {"currency": "USD"})
            active_orders_gauge.add(1)

            # Span events capture point-in-time occurrences within a span
            span.add_event("order_processed_successfully", {
                "order.total": total,
                "order.item_count": len(order_data.get("items", [])),
            })

            return {"status": "success", "total": total}

        except Exception as exc:
            span.set_status(Status(StatusCode.ERROR, str(exc)))
            span.record_exception(exc)
            raise


def validate_order_items(order_data: Dict[str, Any]) -> bool:
    # Validation logic placeholder
    return len(order_data.get("items", [])) > 0


def calculate_order_total(order_data: Dict[str, Any]) -> float:
    return sum(item.get("price", 0) * item.get("qty", 1) for item in order_data.get("items", []))
```

### W3C Trace Context Propagation

**Context propagation** is the mechanism by which trace and span IDs flow across service boundaries. The **W3C Trace Context** standard defines two HTTP headers: `traceparent` (containing trace ID, parent span ID, and trace flags) and `tracestate` (vendor-specific key-value pairs). This is critical **because** without propagation, each service creates independent traces, and you lose the ability to see the full request path through your distributed system.

```python
from opentelemetry import context, trace
from opentelemetry.propagate import set_global_textmap, inject, extract
from opentelemetry.propagators.composite import CompositePropagator
from opentelemetry.trace.propagation import TraceContextTextMapPropagator
from opentelemetry.baggage.propagation import W3CBaggagePropagator
from opentelemetry import baggage
import requests
from typing import Dict, Any

# Configure W3C propagators (traceparent + baggage)
set_global_textmap(
    CompositePropagator([
        TraceContextTextMapPropagator(),
        W3CBaggagePropagator(),
    ])
)

tracer = trace.get_tracer("gateway.service")


def call_downstream_service(url: str, payload: Dict[str, Any]) -> requests.Response:
    # Inject trace context into outgoing request headers
    headers: Dict[str, str] = {}
    inject(headers)  # Adds traceparent and tracestate headers automatically

    with tracer.start_as_current_span(
        "http_client_call",
        attributes={"http.url": url, "http.method": "POST"},
    ) as span:
        response = requests.post(url, json=payload, headers=headers)
        span.set_attribute("http.status_code", response.status_code)
        return response


def extract_context_from_incoming_request(request_headers: Dict[str, str]):
    # Extract trace context from incoming request headers
    # This links the incoming request to the parent trace
    ctx = extract(carrier=request_headers)
    token = context.attach(ctx)

    # Now any spans created will be children of the extracted parent span
    with tracer.start_as_current_span("handle_incoming_request") as span:
        # Also read baggage for cross-cutting concerns
        tenant_id = baggage.get_baggage("tenant.id", ctx)
        if tenant_id:
            span.set_attribute("tenant.id", tenant_id)

    context.detach(token)
```

A **pitfall** that many teams encounter is using custom header names for trace propagation instead of the W3C standard. This breaks interoperability with third-party services and API gateways that only support the standard `traceparent` header. **Therefore**, always use the W3C propagators unless you have a specific legacy requirement.

## Trade-offs in OTel Configuration

The **trade-off** between comprehensive instrumentation and performance overhead is real. Each span consumes memory and CPU for attribute serialization and export. **Best practice** is to use `BatchSpanProcessor` (not `SimpleSpanProcessor`) in production, configure reasonable `export_interval_millis` for metrics, and apply sampling to reduce trace volume. A common starting point is a 10% head-based sampling rate for high-throughput services, increasing to 100% for critical or low-traffic paths.

**However**, over-sampling in high-traffic environments can overwhelm your backend (Jaeger, Tempo, or Datadog), leading to dropped spans and incomplete traces. Tail-based sampling (discussed in the distributed tracing pair) is the **best practice** for capturing all interesting traces without the volume cost.

## Summary and Key Takeaways

- **OpenTelemetry unifies traces, metrics, and logs** through shared resource attributes and context propagation, eliminating the need for separate instrumentation libraries.
- **Auto-instrumentation** provides immediate visibility into HTTP, database, and RPC calls, **however** manual instrumentation is essential for business-specific context and custom metrics.
- **W3C Trace Context** is the standard propagation format — always use it to ensure cross-service and cross-vendor compatibility.
- **Custom metrics** (counters, histograms, gauges) should capture business KPIs alongside technical metrics, with dimensional attributes for powerful filtering and aggregation.
- **The key trade-off** is instrumentation depth vs. performance overhead — use batch processors, sampling, and selective manual instrumentation to balance visibility with resource cost.
- **Common mistakes** include forgetting resource attributes, using `SimpleSpanProcessor` in production, and propagating context with non-standard headers."""
    ),

    # --- 2. Distributed Tracing Deep Dive ---
    (
        "observability/distributed-tracing-deep-dive",
        "Provide a deep dive into distributed tracing covering span hierarchies, baggage propagation, head-based and tail-based and adaptive sampling strategies, trace analysis patterns, and implement tracing middleware for HTTP services gRPC interceptors and async task correlation with production-ready code examples.",
        r"""# Distributed Tracing Deep Dive: Spans, Sampling, and Cross-Service Correlation

## Understanding Span Hierarchies and Trace Structure

A **distributed trace** represents the complete journey of a request through a distributed system, captured as a directed acyclic graph (DAG) of **spans**. Each span records a named, timed operation with metadata. The hierarchy is established through parent-child relationships: a root span has no parent, and every subsequent span references its parent via `parent_span_id`. This is fundamental **because** the hierarchy reveals causal relationships — if span B is a child of span A, we know A triggered B.

**The anatomy of a span** includes: a globally unique `trace_id` (128-bit), a `span_id` (64-bit), the `parent_span_id`, the operation name, start/end timestamps, status code, attributes (key-value metadata), events (timestamped annotations), and links (references to other traces). Understanding this structure is critical **because** every decision about sampling, storage, and analysis depends on how spans relate to each other.

**However**, the tree structure can become complex in practice. A single API call might fan out to 10 microservices, each making database queries and cache lookups, producing hundreds of spans. Without careful **span naming conventions** and **attribute discipline**, trace visualization tools like Jaeger or Grafana Tempo become overwhelming. **Best practice** is to use semantic conventions: `http.method`, `http.route`, `db.system`, `rpc.service`, `rpc.method` — these standardized attributes enable cross-service querying.

## Tracing Middleware for HTTP Services

### Flask/FastAPI Middleware with Rich Span Attributes

While auto-instrumentation handles basic HTTP spans, a custom middleware gives you control over attribute enrichment, error classification, and performance tracking. **Therefore**, production services typically layer custom middleware on top of auto-instrumentation.

```python
import time
import logging
from typing import Callable, Any
from functools import wraps
from opentelemetry import trace, context, baggage
from opentelemetry.propagate import extract
from opentelemetry.trace import StatusCode, SpanKind
from opentelemetry.semconv.trace import SpanAttributes
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)
tracer = trace.get_tracer("http.middleware", "1.0.0")


class TracingMiddleware(BaseHTTPMiddleware):
    # Production tracing middleware for FastAPI/Starlette
    # Extracts incoming context, creates server spans, enriches with
    # business attributes, and records latency metrics

    SENSITIVE_HEADERS = {"authorization", "cookie", "x-api-key"}

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract parent context from incoming headers
        parent_ctx = extract(carrier=dict(request.headers))
        token = context.attach(parent_ctx)

        # Build span name from HTTP method and route template
        route = request.scope.get("route")
        route_path = route.path if route else request.url.path
        span_name = f"{request.method} {route_path}"

        try:
            with tracer.start_as_current_span(
                span_name,
                kind=SpanKind.SERVER,
                attributes={
                    SpanAttributes.HTTP_METHOD: request.method,
                    SpanAttributes.HTTP_URL: str(request.url),
                    SpanAttributes.HTTP_ROUTE: route_path,
                    SpanAttributes.HTTP_SCHEME: request.url.scheme,
                    SpanAttributes.NET_HOST_NAME: request.url.hostname or "unknown",
                    SpanAttributes.HTTP_CLIENT_IP: request.client.host if request.client else "unknown",
                    "http.request_content_length": request.headers.get("content-length", "0"),
                },
            ) as span:
                # Extract baggage for cross-cutting concerns
                tenant_id = baggage.get_baggage("tenant.id")
                if tenant_id:
                    span.set_attribute("tenant.id", tenant_id)

                # Record safe headers as span attributes
                for header_name, header_value in request.headers.items():
                    if header_name.lower() not in self.SENSITIVE_HEADERS:
                        span.set_attribute(f"http.request.header.{header_name}", header_value)

                # Execute the actual request handler
                start_time = time.perf_counter()
                response = await call_next(request)
                duration_ms = (time.perf_counter() - start_time) * 1000

                # Record response attributes
                span.set_attribute(SpanAttributes.HTTP_STATUS_CODE, response.status_code)
                span.set_attribute("http.response.duration_ms", duration_ms)

                # Classify errors by status code
                if response.status_code >= 500:
                    span.set_status(StatusCode.ERROR, f"HTTP {response.status_code}")
                    span.add_event("server_error", {"http.status_code": response.status_code})
                elif response.status_code >= 400:
                    span.add_event("client_error", {"http.status_code": response.status_code})

                return response

        except Exception as exc:
            span = trace.get_current_span()
            span.set_status(StatusCode.ERROR, str(exc))
            span.record_exception(exc)
            logger.error(f"Request failed: {exc}", exc_info=True)
            raise
        finally:
            context.detach(token)
```

### gRPC Interceptor for Tracing

gRPC uses interceptors (the equivalent of middleware) for cross-cutting concerns. The **trade-off** with gRPC tracing is that unary calls are straightforward, but streaming RPCs require careful span lifecycle management — you cannot simply wrap the entire stream in one span **because** individual messages may need their own spans for debugging.

```python
import grpc
import time
from opentelemetry import trace, context
from opentelemetry.propagate import inject, extract
from opentelemetry.trace import SpanKind, StatusCode
from typing import Any, Callable, Tuple


tracer = trace.get_tracer("grpc.interceptor", "1.0.0")


class TracingServerInterceptor(grpc.ServerInterceptor):
    # Server-side gRPC interceptor that extracts trace context
    # from incoming metadata and creates server spans

    def intercept_service(self, continuation: Callable, handler_call_details: grpc.HandlerCallDetails):
        # Extract trace context from gRPC metadata
        metadata = dict(handler_call_details.invocation_metadata or [])
        parent_ctx = extract(carrier=metadata)
        token = context.attach(parent_ctx)

        method = handler_call_details.method  # e.g., /package.Service/Method
        span = tracer.start_span(
            name=method,
            kind=SpanKind.SERVER,
            attributes={
                "rpc.system": "grpc",
                "rpc.service": method.rsplit("/", 1)[0].lstrip("/"),
                "rpc.method": method.rsplit("/", 1)[-1],
            },
        )
        ctx = trace.set_span_in_context(span)
        context.attach(ctx)

        try:
            handler = continuation(handler_call_details)
            return handler
        except Exception as exc:
            span.set_status(StatusCode.ERROR, str(exc))
            span.record_exception(exc)
            raise
        finally:
            span.end()
            context.detach(token)


class TracingClientInterceptor(grpc.UnaryUnaryClientInterceptor):
    # Client-side gRPC interceptor that injects trace context
    # into outgoing metadata for downstream propagation

    def intercept_unary_unary(
        self,
        continuation: Callable,
        client_call_details: grpc.ClientCallDetails,
        request: Any,
    ):
        # Inject trace context into outgoing metadata
        metadata = list(client_call_details.metadata or [])
        carrier: dict = {}
        inject(carrier=carrier)
        for key, value in carrier.items():
            metadata.append((key, value))

        new_details = grpc.ClientCallDetails(
            method=client_call_details.method,
            timeout=client_call_details.timeout,
            metadata=metadata,
            credentials=client_call_details.credentials,
            wait_for_ready=client_call_details.wait_for_ready,
            compression=client_call_details.compression,
        )

        method = client_call_details.method
        with tracer.start_as_current_span(
            name=f"grpc_client {method}",
            kind=SpanKind.CLIENT,
            attributes={
                "rpc.system": "grpc",
                "rpc.method": method.rsplit("/", 1)[-1] if "/" in method else method,
            },
        ) as span:
            start = time.perf_counter()
            response = continuation(new_details, request)
            duration_ms = (time.perf_counter() - start) * 1000
            span.set_attribute("rpc.duration_ms", duration_ms)
            return response
```

### Async Task Correlation with Celery

A **common mistake** is losing trace context when dispatching async tasks to Celery or similar task queues. The task runs in a different process (or even a different machine), so the trace context must be explicitly serialized into the task arguments and restored on the worker side.

```python
import celery
from opentelemetry import trace, context
from opentelemetry.propagate import inject, extract
from opentelemetry.trace import SpanKind
from typing import Any, Dict

tracer = trace.get_tracer("celery.tracing", "1.0.0")

app = celery.Celery("tasks", broker="redis://localhost:6379/0")


def send_traced_task(task_name: str, args: tuple = (), kwargs: dict = None) -> celery.result.AsyncResult:
    # Serialize trace context into task headers for propagation
    carrier: Dict[str, str] = {}
    inject(carrier=carrier)

    with tracer.start_as_current_span(
        f"celery.send:{task_name}",
        kind=SpanKind.PRODUCER,
        attributes={"celery.task_name": task_name},
    ):
        # Pass trace context as Celery headers
        result = app.send_task(
            task_name,
            args=args,
            kwargs=kwargs or {},
            headers=carrier,
        )
        return result


class TracedTask(celery.Task):
    # Base task class that restores trace context on the worker side

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        # Extract trace context from task headers
        headers = self.request.get("headers", {}) or {}
        parent_ctx = extract(carrier=headers)
        token = context.attach(parent_ctx)

        with tracer.start_as_current_span(
            f"celery.run:{self.name}",
            kind=SpanKind.CONSUMER,
            attributes={
                "celery.task_name": self.name,
                "celery.task_id": self.request.id or "unknown",
                "celery.retries": self.request.retries or 0,
            },
        ):
            try:
                return self.run(*args, **kwargs)
            finally:
                context.detach(token)
```

## Sampling Strategies: Head-Based, Tail-Based, and Adaptive

### Head-Based Sampling

**Head-based sampling** makes the sampling decision at the root span — before any work is done. The decision (sample or drop) propagates to all downstream services via the `traceparent` header's trace flags. This is the simplest approach, **however** it has a critical flaw: you might drop the 0.1% of traces that contain errors or extreme latency. **Therefore**, head-based sampling is only appropriate when error traces are not disproportionately valuable, which is rarely the case in production.

### Tail-Based Sampling

**Tail-based sampling** defers the decision until the trace is complete, allowing the collector to examine all spans before deciding whether to keep the trace. This is the **best practice** for production **because** you can keep 100% of error traces and high-latency traces while dropping routine successful traces. The **trade-off** is complexity: tail-based sampling requires a stateful collector (like the OpenTelemetry Collector with the `tail_sampling` processor) that buffers spans until a decision can be made.

### Adaptive Sampling

**Adaptive sampling** dynamically adjusts the sampling rate based on traffic volume and error rates. During low traffic, it samples 100%; during peak load, it reduces to 1% for successful requests while maintaining 100% for errors. This is the most sophisticated approach, **however** it requires careful tuning to avoid oscillation effects where the sampling rate fluctuates rapidly.

## Summary and Key Takeaways

- **Span hierarchies** establish causal relationships between operations — use semantic naming conventions and standardized attributes for queryability across services.
- **HTTP tracing middleware** should extract incoming context, create server spans with rich attributes, classify errors by status code, and record latency metrics.
- **gRPC interceptors** mirror HTTP middleware but must handle both unary and streaming call types, with the **trade-off** of span granularity for streaming RPCs.
- **Async task correlation** requires explicit context serialization into task headers — a **common mistake** is assuming Celery or other task queues automatically propagate trace context.
- **Tail-based sampling** is the **best practice** for production systems, **because** it preserves all error and high-latency traces while controlling storage costs. **However**, it requires a stateful collector layer.
- **The key pitfall** is under-investing in trace context propagation — without end-to-end context flow, distributed tracing degenerates into per-service logging with extra overhead."""
    ),

    # --- 3. Metrics and Alerting ---
    (
        "observability/metrics-alerting-slo",
        "Explain production metrics and alerting strategies including the RED method for request-driven services, USE method for resource monitoring, SLI SLO and error budget calculations, and implement Prometheus metrics collection with recording rules alerting rules and Grafana dashboard JSON configuration for a microservices architecture.",
        r"""# Metrics and Alerting: RED, USE, SLIs/SLOs, and Prometheus in Production

## Choosing the Right Metrics Framework

The difference between a team that is alerted to problems before users notice and a team that discovers outages from customer complaints lies entirely in **metrics strategy**. Two complementary frameworks dominate modern observability: the **RED method** for request-driven services and the **USE method** for infrastructure resources. Understanding when to apply each is essential **because** applying the wrong framework to the wrong layer produces either noise (too many irrelevant alerts) or silence (missing the signals that matter).

**Best practice** is to layer both: RED metrics on your application services (APIs, workers, gateways) and USE metrics on the underlying infrastructure (CPU, memory, disk, network). The SLI/SLO framework then ties these metrics to business commitments, providing the **error budget** concept that enables principled trade-offs between reliability investment and feature velocity.

## The RED Method: Rate, Errors, Duration

The **RED method** (coined by Tom Wilkie) captures the three signals that matter most for request-driven services:

- **Rate**: Requests per second — the throughput of your service
- **Errors**: Failed requests per second — the failure rate
- **Duration**: Latency distribution — how long requests take (p50, p95, p99)

These three metrics, combined with dimensional labels (endpoint, method, status code), provide a complete picture of service health. **However**, a **common mistake** is only tracking average latency instead of percentiles. The average hides the tail — a service with 50ms average but 5-second p99 is failing 1% of its users badly, and that 1% often includes your most important customers running complex queries. **Therefore**, always instrument with histograms (not summaries) so you can compute arbitrary percentiles server-side and aggregate across instances.

### Implementing RED Metrics with Prometheus

```python
import time
import logging
from typing import Callable, Any
from functools import wraps
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry, generate_latest
from prometheus_client import CONTENT_TYPE_LATEST
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, PlainTextResponse

logger = logging.getLogger(__name__)

# Create a custom registry (best practice to avoid polluting the default)
registry = CollectorRegistry()

# RED metrics with dimensional labels
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests (Rate dimension of RED)",
    labelnames=["method", "endpoint", "status_code"],
    registry=registry,
)

REQUEST_ERRORS = Counter(
    "http_request_errors_total",
    "Total HTTP request errors (Errors dimension of RED)",
    labelnames=["method", "endpoint", "error_type"],
    registry=registry,
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds (Duration dimension of RED)",
    labelnames=["method", "endpoint"],
    # Custom buckets tuned for API latency — default buckets are too coarse
    buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
    registry=registry,
)

# USE metrics for connection pools and internal resources
POOL_UTILIZATION = Gauge(
    "db_pool_utilization_ratio",
    "Database connection pool utilization (USE: Utilization)",
    labelnames=["pool_name"],
    registry=registry,
)

POOL_SATURATION = Gauge(
    "db_pool_waiting_threads",
    "Threads waiting for a database connection (USE: Saturation)",
    labelnames=["pool_name"],
    registry=registry,
)


class MetricsMiddleware(BaseHTTPMiddleware):
    # Middleware that records RED metrics for every HTTP request

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        method = request.method
        route = request.scope.get("route")
        endpoint = route.path if route else request.url.path

        start_time = time.perf_counter()
        try:
            response = await call_next(request)
            status_code = str(response.status_code)

            # Record rate and duration
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code=status_code).inc()
            REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(
                time.perf_counter() - start_time
            )

            # Record errors (5xx responses)
            if response.status_code >= 500:
                REQUEST_ERRORS.labels(
                    method=method, endpoint=endpoint, error_type="server_error"
                ).inc()

            return response

        except Exception as exc:
            REQUEST_COUNT.labels(method=method, endpoint=endpoint, status_code="500").inc()
            REQUEST_ERRORS.labels(
                method=method, endpoint=endpoint, error_type=type(exc).__name__
            ).inc()
            REQUEST_DURATION.labels(method=method, endpoint=endpoint).observe(
                time.perf_counter() - start_time
            )
            raise


async def metrics_endpoint(request: Request) -> PlainTextResponse:
    # Expose metrics in Prometheus text format
    return PlainTextResponse(
        generate_latest(registry).decode("utf-8"),
        media_type=CONTENT_TYPE_LATEST,
    )
```

## SLI, SLO, and Error Budgets

An **SLI** (Service Level Indicator) is a quantitative measure of service health — for example, "the proportion of requests that complete in under 300ms." An **SLO** (Service Level Objective) is a target for the SLI — for example, "99.9% of requests complete in under 300ms over a 30-day rolling window." The **error budget** is the inverse: with a 99.9% SLO, you have a 0.1% error budget, which translates to approximately 43 minutes of downtime per 30-day window.

The **trade-off** that error budgets encode is profound: when the budget is healthy, the team can ship aggressively and take risks; when the budget is nearly exhausted, the team must freeze features and focus on reliability. This transforms reliability from a vague aspiration into a measurable, actionable constraint.

### Prometheus Recording and Alerting Rules

```yaml
# prometheus-rules.yaml
# Recording rules precompute expensive queries for dashboard performance
# Alerting rules fire when SLOs are at risk

groups:
  - name: red_recording_rules
    interval: 30s
    rules:
      # Request rate per endpoint (5-minute smoothed)
      - record: http:requests:rate5m
        expr: sum(rate(http_requests_total[5m])) by (method, endpoint)

      # Error rate per endpoint
      - record: http:errors:rate5m
        expr: sum(rate(http_request_errors_total[5m])) by (method, endpoint)

      # Error ratio (errors / total requests)
      - record: http:error_ratio:rate5m
        expr: |
          sum(rate(http_request_errors_total[5m])) by (endpoint)
          /
          sum(rate(http_requests_total[5m])) by (endpoint)

      # P99 latency per endpoint
      - record: http:latency:p99_5m
        expr: histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint))

      # P95 latency per endpoint
      - record: http:latency:p95_5m
        expr: histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, endpoint))

  - name: slo_alerting_rules
    rules:
      # Multi-window multi-burn-rate alerting (Google SRE approach)
      # Fast burn: 14.4x burn rate over 1 hour (exhausts budget in ~2 days)
      - alert: SLOErrorBudgetFastBurn
        expr: |
          (
            sum(rate(http_request_errors_total[1h])) by (endpoint)
            /
            sum(rate(http_requests_total[1h])) by (endpoint)
          ) > (14.4 * 0.001)
        for: 2m
        labels:
          severity: critical
          team: platform
        annotations:
          summary: "SLO error budget burning at 14.4x rate for {{ $labels.endpoint }}"
          description: "Error rate {{ $value | humanizePercentage }} exceeds 14.4x the 0.1% error budget"
          runbook_url: "https://wiki.internal/runbooks/slo-budget-burn"

      # Slow burn: 3x burn rate over 6 hours (exhausts budget in ~10 days)
      - alert: SLOErrorBudgetSlowBurn
        expr: |
          (
            sum(rate(http_request_errors_total[6h])) by (endpoint)
            /
            sum(rate(http_requests_total[6h])) by (endpoint)
          ) > (3 * 0.001)
        for: 15m
        labels:
          severity: warning
          team: platform
        annotations:
          summary: "SLO error budget slow burn for {{ $labels.endpoint }}"

      # Latency SLO: P99 exceeding target
      - alert: LatencySLOBreach
        expr: http:latency:p99_5m > 0.3
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "P99 latency {{ $value }}s exceeds 300ms SLO for {{ $labels.endpoint }}"

      # Saturation alert for connection pools
      - alert: DBPoolSaturation
        expr: db_pool_waiting_threads > 5
        for: 3m
        labels:
          severity: warning
        annotations:
          summary: "Database pool {{ $labels.pool_name }} has {{ $value }} waiting threads"
```

### Grafana Dashboard Configuration

A **pitfall** in dashboard design is building dashboards that look impressive but fail to answer the question "is my service healthy?" in under 5 seconds. **Best practice** is to lead with the RED overview, then provide drill-down panels for each dimension.

```json
{
  "dashboard": {
    "title": "Service Health - RED Overview",
    "uid": "red-overview-v1",
    "tags": ["red", "slo", "production"],
    "timezone": "browser",
    "refresh": "30s",
    "panels": [
      {
        "title": "Request Rate (req/s)",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 8, "x": 0, "y": 0},
        "targets": [
          {
            "expr": "sum(http:requests:rate5m) by (endpoint)",
            "legendFormat": "{{ endpoint }}"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "reqps",
            "custom": {"lineWidth": 2, "fillOpacity": 10}
          }
        }
      },
      {
        "title": "Error Rate (%)",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 8, "x": 8, "y": 0},
        "targets": [
          {
            "expr": "http:error_ratio:rate5m * 100",
            "legendFormat": "{{ endpoint }}"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percent",
            "thresholds": {
              "steps": [
                {"color": "green", "value": null},
                {"color": "yellow", "value": 0.05},
                {"color": "red", "value": 0.1}
              ]
            }
          }
        }
      },
      {
        "title": "P99 Latency (seconds)",
        "type": "timeseries",
        "gridPos": {"h": 8, "w": 8, "x": 16, "y": 0},
        "targets": [
          {
            "expr": "http:latency:p99_5m",
            "legendFormat": "p99 {{ endpoint }}"
          },
          {
            "expr": "http:latency:p95_5m",
            "legendFormat": "p95 {{ endpoint }}"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "s",
            "custom": {"lineWidth": 2}
          }
        }
      },
      {
        "title": "SLO Error Budget Remaining (%)",
        "type": "gauge",
        "gridPos": {"h": 8, "w": 8, "x": 0, "y": 8},
        "targets": [
          {
            "expr": "1 - (sum(increase(http_request_errors_total[30d])) / sum(increase(http_requests_total[30d]))) / 0.001",
            "legendFormat": "Budget Remaining"
          }
        ],
        "fieldConfig": {
          "defaults": {
            "unit": "percentunit",
            "min": 0, "max": 1,
            "thresholds": {
              "steps": [
                {"color": "red", "value": null},
                {"color": "yellow", "value": 0.25},
                {"color": "green", "value": 0.5}
              ]
            }
          }
        }
      }
    ]
  }
}
```

## The USE Method for Infrastructure Metrics

The **USE method** (by Brendan Gregg) applies to resources: CPU, memory, disk, network, connection pools. For each resource, measure **Utilization** (percentage of time the resource is busy), **Saturation** (queue depth or work waiting), and **Errors** (error events). This is complementary to RED **because** RED tells you *what* is happening to user requests while USE tells you *why* — a spike in p99 latency (RED) might be caused by CPU saturation (USE) or disk I/O errors (USE).

## Summary and Key Takeaways

- **RED method** (Rate, Errors, Duration) is the **best practice** for monitoring request-driven services — always use percentile latencies, not averages.
- **USE method** (Utilization, Saturation, Errors) complements RED by monitoring infrastructure resources and explaining *why* RED metrics degrade.
- **SLI/SLO/error budgets** transform reliability from a vague goal into a measurable constraint, enabling principled **trade-offs** between feature velocity and reliability investment.
- **Multi-window, multi-burn-rate alerting** is the gold standard for SLO-based alerts, **because** it catches both fast outages and slow degradation without alert fatigue.
- **Prometheus recording rules** precompute expensive queries for dashboard performance — a **common mistake** is running raw `histogram_quantile` in dashboards, causing slow load times.
- **The key pitfall** is over-alerting: every alert must be actionable. If an alert fires and the on-call engineer has nothing to do, the alert should be removed or downgraded to a dashboard annotation."""
    ),

    # --- 4. Structured Logging Patterns ---
    (
        "observability/structured-logging-patterns",
        "Explain structured logging patterns for production services covering log levels, correlation IDs, contextual fields, log aggregation with ELK stack and Grafana Loki, and implement a structured logger with request context propagation, performance tracking, error enrichment, and log sampling strategies for high-traffic services.",
        r"""# Structured Logging Patterns: From Printf to Production-Grade Log Pipelines

## Why Structured Logging Matters

The transition from `print(f"User {user_id} placed order {order_id}")` to structured logging is one of the most impactful observability improvements a team can make, **because** structured logs are machine-parseable, queryable, and correlatable. An unstructured log line is a string that a human can read; a structured log entry is a JSON object that a machine can index, aggregate, and alert on. In a microservices architecture handling thousands of requests per second, the ability to query `SELECT * FROM logs WHERE correlation_id = 'abc-123' AND level = 'error'` across all services in under a second is the difference between a 5-minute incident and a 5-hour one.

**However**, structured logging done poorly creates its own problems. Logs that include unbounded fields (full request bodies, stack traces repeated at every log level, or high-cardinality user IDs as indexed labels) can overwhelm your log aggregation backend, explode storage costs, and make queries slower than grepping through flat files. **Therefore**, a disciplined approach to what you log, at what level, and with which fields is essential.

## Log Level Strategy

The **best practice** log level strategy treats levels as a contract with your operations team:

- **CRITICAL/FATAL**: The process is about to crash or has entered an unrecoverable state. Pages the on-call immediately.
- **ERROR**: An operation failed and requires attention, but the service continues. Creates a ticket or triggers an alert.
- **WARNING**: Something unexpected happened but was handled. No immediate action needed, but indicates a potential problem.
- **INFO**: Normal operational events — request handled, job completed, configuration loaded. The default level for production.
- **DEBUG**: Detailed diagnostic information. Never enabled in production by default.

A **common mistake** is logging at ERROR level for client-caused issues (400 Bad Request, 404 Not Found). These are not errors in your service — they are normal operation. Logging them at ERROR creates alert fatigue and masks real problems. **Best practice** is to log client errors at INFO or WARNING level, reserving ERROR for situations where your code failed to do what it should have done.

### Implementing a Structured Logger with Context Propagation

```python
import logging
import json
import time
import uuid
import traceback
import sys
from contextvars import ContextVar
from typing import Any, Dict, Optional, Callable
from dataclasses import dataclass, field, asdict
from functools import wraps

# Context variables for request-scoped data
_correlation_id: ContextVar[str] = ContextVar("correlation_id", default="no-correlation")
_request_context: ContextVar[Dict[str, Any]] = ContextVar("request_context", default={})


@dataclass
class LogContext:
    # Immutable context that gets attached to every log entry
    # within a request scope
    correlation_id: str = ""
    service_name: str = ""
    environment: str = ""
    user_id: Optional[str] = None
    tenant_id: Optional[str] = None
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)


class StructuredJsonFormatter(logging.Formatter):
    # Formats log records as single-line JSON objects with all
    # contextual fields attached. Designed for ingestion by ELK,
    # Loki, Datadog, or any JSON-aware log aggregator.

    RESERVED_ATTRS = {
        "args", "created", "exc_info", "exc_text", "filename",
        "funcName", "levelname", "levelno", "lineno", "module",
        "msecs", "message", "msg", "name", "pathname", "process",
        "processName", "relativeCreated", "stack_info", "thread",
        "threadName",
    }

    def __init__(self, service_name: str = "unknown", environment: str = "production"):
        super().__init__()
        self.service_name = service_name
        self.environment = environment

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": self._format_timestamp(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "service": self.service_name,
            "environment": self.environment,
            "correlation_id": _correlation_id.get("no-correlation"),
            "source": {
                "file": record.pathname,
                "line": record.lineno,
                "function": record.funcName,
            },
        }

        # Merge request context (user_id, tenant_id, etc.)
        req_ctx = _request_context.get({})
        if req_ctx:
            log_entry["context"] = req_ctx

        # Add trace context if available (OTel integration)
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            span_context = span.get_span_context()
            if span_context.is_valid:
                log_entry["trace_id"] = format(span_context.trace_id, "032x")
                log_entry["span_id"] = format(span_context.span_id, "016x")
        except ImportError:
            pass

        # Add exception info with structured fields
        if record.exc_info and record.exc_info[1]:
            exc_type, exc_value, exc_tb = record.exc_info
            log_entry["error"] = {
                "type": exc_type.__name__ if exc_type else "Unknown",
                "message": str(exc_value),
                "stacktrace": traceback.format_exception(exc_type, exc_value, exc_tb),
            }

        # Add any extra fields passed via logger.info("msg", extra={...})
        for key, value in record.__dict__.items():
            if key not in self.RESERVED_ATTRS and not key.startswith("_"):
                log_entry.setdefault("extra", {})[key] = value

        return json.dumps(log_entry, default=str, ensure_ascii=False)

    def _format_timestamp(self, record: logging.LogRecord) -> str:
        from datetime import datetime, timezone
        dt = datetime.fromtimestamp(record.created, tz=timezone.utc)
        return dt.isoformat()


def configure_structured_logging(
    service_name: str,
    environment: str = "production",
    level: int = logging.INFO,
) -> logging.Logger:
    # Configure the root logger with structured JSON formatting
    logger = logging.getLogger()
    logger.setLevel(level)

    # Remove existing handlers to avoid duplicate output
    logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter(service_name, environment))
    logger.addHandler(handler)

    return logger
```

### Request Context Middleware and Performance Tracking

```python
import time
import uuid
import logging
from typing import Callable
from contextvars import copy_context
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)


class LogContextMiddleware(BaseHTTPMiddleware):
    # Middleware that sets up correlation ID and request context
    # for every incoming request. All log entries within the request
    # scope automatically include these fields.

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Extract or generate correlation ID
        correlation_id = (
            request.headers.get("x-correlation-id")
            or request.headers.get("x-request-id")
            or str(uuid.uuid4())
        )

        # Set context variables for the duration of this request
        _correlation_id.set(correlation_id)
        _request_context.set({
            "http_method": request.method,
            "http_path": str(request.url.path),
            "client_ip": request.client.host if request.client else "unknown",
            "user_agent": request.headers.get("user-agent", "unknown"),
        })

        # Log request start
        logger.info(
            "Request started",
            extra={
                "event": "request_start",
                "http_method": request.method,
                "http_path": str(request.url.path),
            },
        )

        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log request completion with performance data
            log_level = logging.WARNING if response.status_code >= 400 else logging.INFO
            logger.log(
                log_level,
                "Request completed",
                extra={
                    "event": "request_end",
                    "http_status": response.status_code,
                    "duration_ms": round(duration_ms, 2),
                    "slow_request": duration_ms > 1000,
                },
            )

            # Add correlation ID to response headers for client-side debugging
            response.headers["x-correlation-id"] = correlation_id
            return response

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                "Request failed with unhandled exception",
                extra={
                    "event": "request_error",
                    "duration_ms": round(duration_ms, 2),
                    "error_type": type(exc).__name__,
                },
                exc_info=True,
            )
            raise
```

### Log Sampling for High-Traffic Services

In high-traffic services (10,000+ requests per second), logging every request at INFO level generates enormous volume. **Best practice** is to implement log sampling: log 100% of errors and warnings, but only a percentage of INFO-level success logs. This preserves full error visibility while reducing volume by 90% or more. The **trade-off** is that you lose some visibility into successful requests, **however** your metrics and traces already cover that gap.

```python
import random
import logging
from typing import Optional


class SampledLogFilter(logging.Filter):
    # Sampling filter that passes all ERROR+ logs but only
    # a percentage of INFO/DEBUG logs. This dramatically reduces
    # log volume in high-traffic services without losing error visibility.

    def __init__(
        self,
        sample_rate: float = 0.1,   # 10% of INFO logs
        always_log_levels: Optional[set] = None,
    ):
        super().__init__()
        self.sample_rate = sample_rate
        self.always_log_levels = always_log_levels or {
            logging.WARNING, logging.ERROR, logging.CRITICAL
        }
        # Always log specific events regardless of sampling
        self.always_log_events = {"request_error", "startup", "shutdown", "config_change"}

    def filter(self, record: logging.LogRecord) -> bool:
        # Always pass high-severity logs
        if record.levelno in self.always_log_levels:
            return True

        # Always pass important events
        event = getattr(record, "event", None)
        if event in self.always_log_events:
            return True

        # Sample the rest
        return random.random() < self.sample_rate


def configure_sampled_logging(
    service_name: str,
    sample_rate: float = 0.1,
) -> logging.Logger:
    logger = configure_structured_logging(service_name)
    sampling_filter = SampledLogFilter(sample_rate=sample_rate)
    for handler in logger.handlers:
        handler.addFilter(sampling_filter)
    return logger
```

## Log Aggregation: ELK vs. Grafana Loki

The **trade-off** between **ELK** (Elasticsearch, Logstash, Kibana) and **Grafana Loki** is fundamentally about indexing strategy. ELK indexes full log content, enabling full-text search across all fields — **however** this indexing is extremely resource-intensive and expensive at scale. Loki indexes only labels (like `service`, `environment`, `level`) and stores log lines as compressed chunks, making it 10-100x cheaper to operate but requiring you to know which labels to filter by before grepping content.

**Best practice** for most teams is Loki **because** the label-based approach aligns perfectly with structured logging — you already have `service`, `level`, `correlation_id` as structured fields. A **pitfall** with Loki is creating too many label values (high cardinality), such as using `user_id` as a label. This creates millions of streams and degrades query performance. Keep labels low-cardinality (service, environment, level, pod) and use LogQL's `| json | line_format` for filtering on high-cardinality fields within the log content.

## Summary and Key Takeaways

- **Structured logging** (JSON format) is a prerequisite for effective log aggregation — unstructured log lines cannot be efficiently queried at scale.
- **Correlation IDs** must propagate across all services and appear in every log entry, enabling end-to-end request tracing through logs.
- **Log levels are a contract** with your ops team — a **common mistake** is logging client errors at ERROR level, creating alert fatigue and masking real problems.
- **Log sampling** reduces volume by 90%+ in high-traffic services while preserving 100% of error visibility — the **trade-off** is acceptable **because** metrics and traces cover the happy path.
- **Loki vs. ELK** is a **trade-off** between query flexibility (ELK) and operational cost (Loki) — Loki is the **best practice** for most teams, **however** avoid high-cardinality labels.
- **The key pitfall** is logging too much: every log entry has a storage cost, an indexing cost, and a signal-to-noise cost. Log what you need to debug, not what you might someday want to see."""
    ),

    # --- 5. Chaos Engineering and Reliability ---
    (
        "observability/chaos-engineering-reliability",
        "Explain chaos engineering and reliability practices including failure injection, GameDay exercises, steady-state hypothesis, blast radius control, and implement chaos experiments with Litmus and ChaosMesh configurations, failure injection middleware, and circuit breaker patterns with observability hooks for production resilience testing.",
        r"""# Chaos Engineering and Reliability: Controlled Failure for Stronger Systems

## Why Chaos Engineering Is Essential

**Chaos engineering** is the discipline of experimenting on a distributed system to build confidence in its ability to withstand turbulent conditions in production. The core insight is that complex systems fail in complex ways — **therefore** you cannot simply test individual components in isolation and expect the integrated system to be resilient. A **common mistake** is treating chaos engineering as "breaking things in production for fun." In reality, it is a rigorous experimental methodology with hypotheses, controlled variables, measured outcomes, and blast radius limits.

**The fundamental argument** for chaos engineering is economic: an unplanned outage discovered by customers costs 10-100x more than a controlled experiment that reveals the same weakness. Netflix's Chaos Monkey, which randomly terminates production instances, reduced their mean time to recovery (MTTR) from hours to minutes **because** every engineer was forced to build services that survived instance loss. **However**, chaos engineering without proper observability is dangerous — you need metrics, traces, and alerts in place *before* you start injecting failures, **because** you need to detect the impact of your experiments.

## The Chaos Engineering Process

### Steady-State Hypothesis

Every chaos experiment begins with a **steady-state hypothesis**: a measurable description of normal system behavior. For example: "Under normal conditions, our API returns 200 responses for 99.9% of requests with p99 latency under 300ms." The experiment then introduces a perturbation (kill a pod, add network latency, exhaust a connection pool) and observes whether the steady state is maintained. If the steady state breaks, you have discovered a weakness; if it holds, you have increased confidence in your resilience.

**Best practice** is to define steady state using your existing SLIs/SLOs — this creates a direct link between chaos experiments and business impact. The **trade-off** is that narrow steady-state definitions (only checking availability) miss subtle degradations, while overly broad definitions (checking every metric) create noise. Start with the RED metrics: request rate, error rate, and p99 latency.

### Blast Radius Control

**Blast radius control** is the most critical safety mechanism in chaos engineering. Every experiment must have well-defined boundaries: which services are affected, what percentage of traffic is impacted, and what conditions trigger an automatic abort. A **pitfall** is running chaos experiments during peak traffic without blast radius limits — this converts a controlled experiment into an unplanned outage.

```python
import time
import random
import logging
import threading
from typing import Callable, Optional, Dict, Any, List
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ExperimentStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    ABORTED = "aborted"


@dataclass
class SteadyStateMetric:
    # A metric that defines normal system behavior
    name: str
    query_fn: Callable[[], float]     # Function that returns current metric value
    min_threshold: Optional[float] = None
    max_threshold: Optional[float] = None

    def check(self) -> bool:
        value = self.query_fn()
        if self.min_threshold is not None and value < self.min_threshold:
            logger.warning(f"Steady state violated: {self.name}={value} < {self.min_threshold}")
            return False
        if self.max_threshold is not None and value > self.max_threshold:
            logger.warning(f"Steady state violated: {self.name}={value} > {self.max_threshold}")
            return False
        return True


@dataclass
class ChaosExperiment:
    # Framework for running chaos experiments with safety controls
    name: str
    description: str
    steady_state_metrics: List[SteadyStateMetric]
    blast_radius_percent: float = 5.0   # Affect max 5% of traffic
    max_duration_seconds: int = 300     # Auto-abort after 5 minutes
    abort_on_steady_state_violation: bool = True
    status: ExperimentStatus = ExperimentStatus.PENDING
    start_time: Optional[datetime] = None
    _abort_event: threading.Event = field(default_factory=threading.Event)

    def verify_steady_state(self) -> bool:
        # Verify all steady-state metrics are within thresholds
        results = []
        for metric in self.steady_state_metrics:
            ok = metric.check()
            results.append((metric.name, ok))
            if not ok:
                logger.error(f"Steady state check FAILED for {metric.name}")
        all_ok = all(ok for _, ok in results)
        logger.info(f"Steady state verification: {'PASS' if all_ok else 'FAIL'} - {results}")
        return all_ok

    def run(self, inject_fn: Callable[[], None], rollback_fn: Callable[[], None]) -> Dict[str, Any]:
        # Execute the chaos experiment with full safety controls
        logger.info(f"Starting chaos experiment: {self.name}")
        self.status = ExperimentStatus.RUNNING
        self.start_time = datetime.utcnow()

        # Step 1: Verify steady state BEFORE injection
        if not self.verify_steady_state():
            logger.error("Pre-experiment steady state check failed — aborting")
            self.status = ExperimentStatus.ABORTED
            return {"status": "aborted", "reason": "pre_experiment_steady_state_violation"}

        # Step 2: Inject failure
        try:
            logger.info(f"Injecting failure: {self.description}")
            inject_fn()

            # Step 3: Monitor during experiment
            monitor_interval = 10  # Check every 10 seconds
            elapsed = 0
            while elapsed < self.max_duration_seconds and not self._abort_event.is_set():
                time.sleep(monitor_interval)
                elapsed += monitor_interval

                if self.abort_on_steady_state_violation and not self.verify_steady_state():
                    logger.error("Steady state violated during experiment — aborting")
                    self.status = ExperimentStatus.ABORTED
                    rollback_fn()
                    return {
                        "status": "aborted",
                        "reason": "steady_state_violation",
                        "duration_seconds": elapsed,
                    }

            # Step 4: Rollback
            rollback_fn()
            logger.info("Failure injection rolled back")

            # Step 5: Verify steady state AFTER rollback
            time.sleep(30)  # Allow recovery time
            post_ok = self.verify_steady_state()
            self.status = ExperimentStatus.COMPLETED

            return {
                "status": "completed",
                "steady_state_maintained": post_ok,
                "duration_seconds": elapsed,
            }

        except Exception as exc:
            logger.error(f"Experiment failed with exception: {exc}", exc_info=True)
            rollback_fn()
            self.status = ExperimentStatus.ABORTED
            return {"status": "aborted", "reason": str(exc)}

    def abort(self) -> None:
        # Externally trigger experiment abort
        self._abort_event.set()
```

### Failure Injection Middleware

A **failure injection middleware** allows you to introduce controlled failures (latency, errors, connection drops) into your service at the HTTP layer. This is useful for testing how upstream services handle degraded dependencies. The key design principle is that the middleware is controlled by a feature flag or configuration service, not hardcoded — **therefore** you can enable and disable injection without deployments.

```python
import time
import random
import logging
from typing import Callable, Optional, Dict
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse
from prometheus_client import Counter, Histogram

logger = logging.getLogger(__name__)

# Metrics for chaos injection observability
chaos_injections = Counter(
    "chaos_injections_total",
    "Total number of chaos failures injected",
    labelnames=["fault_type", "endpoint"],
)


class FaultInjectionConfig:
    # Configuration for fault injection — typically loaded from
    # a feature flag service or config map
    def __init__(self):
        self.enabled: bool = False
        self.latency_ms: int = 0           # Additional latency to inject
        self.error_rate: float = 0.0       # Probability of returning 500
        self.error_code: int = 500         # HTTP status code to return
        self.affected_endpoints: list = [] # Empty = all endpoints
        self.blast_radius: float = 0.05    # Max 5% of requests affected
        self.abort_rate: float = 0.0       # Probability of connection abort


# Global config — updated by feature flag service
fault_config = FaultInjectionConfig()


class FaultInjectionMiddleware(BaseHTTPMiddleware):
    # Middleware that injects controlled failures into HTTP requests.
    # Designed for chaos engineering experiments — never enabled
    # without blast radius limits and monitoring.

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if not fault_config.enabled:
            return await call_next(request)

        endpoint = request.url.path

        # Check if this endpoint is targeted
        if fault_config.affected_endpoints and endpoint not in fault_config.affected_endpoints:
            return await call_next(request)

        # Apply blast radius limit
        if random.random() > fault_config.blast_radius:
            return await call_next(request)

        # Inject latency fault
        if fault_config.latency_ms > 0:
            delay_seconds = fault_config.latency_ms / 1000.0
            # Add jitter to make it realistic
            actual_delay = delay_seconds * (0.5 + random.random())
            logger.info(f"Chaos: injecting {actual_delay:.3f}s latency on {endpoint}")
            chaos_injections.labels(fault_type="latency", endpoint=endpoint).inc()
            time.sleep(actual_delay)

        # Inject error fault
        if random.random() < fault_config.error_rate:
            logger.info(f"Chaos: injecting HTTP {fault_config.error_code} on {endpoint}")
            chaos_injections.labels(fault_type="error", endpoint=endpoint).inc()
            return JSONResponse(
                status_code=fault_config.error_code,
                content={"error": "chaos_injection", "type": "simulated_failure"},
            )

        # Inject connection abort
        if random.random() < fault_config.abort_rate:
            logger.info(f"Chaos: aborting connection on {endpoint}")
            chaos_injections.labels(fault_type="abort", endpoint=endpoint).inc()
            raise ConnectionAbortedError("Chaos injection: connection abort")

        return await call_next(request)
```

### Circuit Breaker with Observability Hooks

A **circuit breaker** prevents cascading failures by stopping requests to a failing dependency. The **trade-off** is between failing fast (returning an error immediately) and giving the dependency time to recover. The three states — **closed** (normal), **open** (failing fast), and **half-open** (testing recovery) — must be observable through metrics **because** a circuit breaker that silently opens leaves the team unaware that a dependency is down.

```python
import time
import logging
import threading
from typing import Callable, Any, TypeVar, Optional
from enum import Enum
from dataclasses import dataclass
from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger(__name__)

T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


# Observability metrics for circuit breaker state
circuit_state_gauge = Gauge(
    "circuit_breaker_state",
    "Current circuit breaker state (0=closed, 1=open, 2=half_open)",
    labelnames=["service", "operation"],
)

circuit_transitions = Counter(
    "circuit_breaker_transitions_total",
    "Circuit breaker state transitions",
    labelnames=["service", "operation", "from_state", "to_state"],
)

circuit_call_duration = Histogram(
    "circuit_breaker_call_duration_seconds",
    "Duration of calls through the circuit breaker",
    labelnames=["service", "operation", "result"],
)


class CircuitBreaker:
    # Production circuit breaker with full observability integration.
    # Emits metrics on state transitions, call durations, and failure rates.

    def __init__(
        self,
        service_name: str,
        operation_name: str,
        failure_threshold: int = 5,      # Failures before opening
        recovery_timeout: float = 30.0,  # Seconds before trying half-open
        half_open_max_calls: int = 3,    # Test calls in half-open state
        success_threshold: int = 2,      # Successes to close from half-open
    ):
        self.service = service_name
        self.operation = operation_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.success_threshold = success_threshold

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._half_open_calls = 0
        self._last_failure_time: Optional[float] = None
        self._lock = threading.Lock()

        # Initialize gauge
        circuit_state_gauge.labels(service=service_name, operation=operation_name).set(0)

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if recovery timeout has elapsed
                if (time.time() - (self._last_failure_time or 0)) >= self.recovery_timeout:
                    self._transition_to(CircuitState.HALF_OPEN)
            return self._state

    def _transition_to(self, new_state: CircuitState) -> None:
        old_state = self._state
        self._state = new_state
        state_value = {CircuitState.CLOSED: 0, CircuitState.OPEN: 1, CircuitState.HALF_OPEN: 2}
        circuit_state_gauge.labels(service=self.service, operation=self.operation).set(
            state_value[new_state]
        )
        circuit_transitions.labels(
            service=self.service,
            operation=self.operation,
            from_state=old_state.value,
            to_state=new_state.value,
        ).inc()
        logger.warning(
            f"Circuit breaker {self.service}/{self.operation}: {old_state.value} -> {new_state.value}"
        )

        # Reset counters on state change
        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0
            self._success_count = 0
        elif new_state == CircuitState.CLOSED:
            self._failure_count = 0

    def call(self, fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
        # Execute a function through the circuit breaker
        current_state = self.state

        if current_state == CircuitState.OPEN:
            circuit_call_duration.labels(
                service=self.service, operation=self.operation, result="rejected"
            ).observe(0)
            raise CircuitOpenError(
                f"Circuit breaker {self.service}/{self.operation} is OPEN"
            )

        if current_state == CircuitState.HALF_OPEN:
            with self._lock:
                if self._half_open_calls >= self.half_open_max_calls:
                    raise CircuitOpenError("Half-open call limit reached")
                self._half_open_calls += 1

        start = time.time()
        try:
            result = fn(*args, **kwargs)
            duration = time.time() - start
            circuit_call_duration.labels(
                service=self.service, operation=self.operation, result="success"
            ).observe(duration)
            self._on_success()
            return result
        except Exception as exc:
            duration = time.time() - start
            circuit_call_duration.labels(
                service=self.service, operation=self.operation, result="failure"
            ).observe(duration)
            self._on_failure()
            raise

    def _on_success(self) -> None:
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
            elif self._state == CircuitState.CLOSED:
                self._failure_count = max(0, self._failure_count - 1)

    def _on_failure(self) -> None:
        with self._lock:
            self._last_failure_time = time.time()
            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
            elif self._state == CircuitState.CLOSED:
                self._failure_count += 1
                if self._failure_count >= self.failure_threshold:
                    self._transition_to(CircuitState.OPEN)


class CircuitOpenError(Exception):
    # Raised when a call is rejected because the circuit is open
    pass
```

## Kubernetes-Native Chaos: Litmus and ChaosMesh

For Kubernetes environments, **Litmus** and **ChaosMesh** provide declarative chaos experiments as Custom Resources. The **trade-off** between the two: Litmus has a richer experiment library and a central hub for community experiments, while ChaosMesh has tighter Kubernetes integration and a more polished dashboard. Both support pod kill, network chaos, I/O chaos, and stress testing.

**Best practice** for GameDay exercises is to run them quarterly, with a clear scope, a facilitator, an observer who monitors dashboards, and a pre-defined rollback procedure. The goal is not to break things — it is to discover weaknesses in your detection, response, and recovery processes. **Therefore**, the observability stack (metrics, traces, alerts, runbooks) is as much under test as the application itself.

## Summary and Key Takeaways

- **Chaos engineering** is a rigorous experimental methodology, not random failure injection — every experiment needs a **steady-state hypothesis**, blast radius limits, and automatic abort conditions.
- **Failure injection middleware** enables controlled HTTP-layer chaos (latency, errors, connection drops) with feature-flag control and Prometheus metrics for visibility.
- **Circuit breakers** prevent cascading failures and must emit observability signals (state transitions, call durations, rejection counts) — a circuit breaker without metrics is a **common mistake** that leaves teams blind to dependency degradation.
- **Blast radius control** is the most critical safety mechanism — **best practice** is to start with 1-5% of traffic and expand only after verifying that monitoring detects the impact.
- **GameDay exercises** test the entire incident response pipeline (detection, alerting, runbooks, recovery), not just the application — **therefore** they are as much an observability test as a resilience test.
- **The key trade-off** in chaos engineering is between experiment realism and production risk. Start with staging environments, graduate to low-traffic production windows, and only run during peak traffic after building confidence through progressive expansion."""
    ),
]
