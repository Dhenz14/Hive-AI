"""Advanced observability patterns."""

PAIRS = [
    (
        "observability/opentelemetry-instrumentation",
        "Implement comprehensive OpenTelemetry instrumentation for a Python microservice covering traces, metrics, and logs with automatic and manual instrumentation, context propagation, and resource attributes.",
        '''OpenTelemetry instrumentation for traces, metrics, and logs:

```python
# --- OpenTelemetry unified instrumentation setup ---

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, Callable, Generator, Optional

from opentelemetry import context, metrics, trace
from opentelemetry.baggage import get_baggage, set_baggage
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
    OTLPMetricExporter,
)
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
    OTLPSpanExporter,
)
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.metrics import Counter, Histogram, UpDownCounter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.semconv.resource import ResourceAttributes
from opentelemetry.semconv.trace import SpanAttributes
from opentelemetry.trace import StatusCode

logger = logging.getLogger(__name__)


@dataclass
class OTelConfig:
    """OpenTelemetry configuration."""
    service_name: str
    service_version: str = "1.0.0"
    environment: str = "production"
    otlp_endpoint: str = "localhost:4317"
    metric_export_interval_ms: int = 60_000
    trace_sample_rate: float = 1.0
    log_correlation: bool = True
    extra_resource_attrs: dict[str, str] = field(default_factory=dict)


class TelemetryProvider:
    """Centralized OpenTelemetry provider managing traces, metrics, logs."""

    def __init__(self, config: OTelConfig) -> None:
        self.config = config
        self._resource = self._build_resource()
        self._tracer_provider: Optional[TracerProvider] = None
        self._meter_provider: Optional[MeterProvider] = None
        self._tracer: Optional[trace.Tracer] = None
        self._meter: Optional[metrics.Meter] = None

    def _build_resource(self) -> Resource:
        attrs = {
            ResourceAttributes.SERVICE_NAME: self.config.service_name,
            ResourceAttributes.SERVICE_VERSION: self.config.service_version,
            ResourceAttributes.DEPLOYMENT_ENVIRONMENT: self.config.environment,
            "host.name": os.environ.get("HOSTNAME", "unknown"),
            "service.instance.id": os.environ.get("POD_NAME", "local"),
        }
        attrs.update(self.config.extra_resource_attrs)
        return Resource.create(attrs)

    def initialize(self) -> None:
        self._setup_traces()
        self._setup_metrics()
        self._setup_auto_instrumentation()
        if self.config.log_correlation:
            self._setup_log_correlation()
        logger.info(
            "Telemetry initialized for %s v%s",
            self.config.service_name,
            self.config.service_version,
        )

    def _setup_traces(self) -> None:
        exporter = OTLPSpanExporter(endpoint=self.config.otlp_endpoint)
        processor = BatchSpanProcessor(exporter)
        self._tracer_provider = TracerProvider(resource=self._resource)
        self._tracer_provider.add_span_processor(processor)
        trace.set_tracer_provider(self._tracer_provider)
        self._tracer = trace.get_tracer(
            self.config.service_name, self.config.service_version
        )

    def _setup_metrics(self) -> None:
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=self.config.otlp_endpoint),
            export_interval_millis=self.config.metric_export_interval_ms,
        )
        self._meter_provider = MeterProvider(
            resource=self._resource, metric_readers=[reader]
        )
        metrics.set_meter_provider(self._meter_provider)
        self._meter = metrics.get_meter(
            self.config.service_name, self.config.service_version
        )

    def _setup_auto_instrumentation(self) -> None:
        HTTPXClientInstrumentor().instrument()
        RedisInstrumentor().instrument()
        logger.info("Auto-instrumentation enabled for httpx, redis")

    def _setup_log_correlation(self) -> None:
        old_factory = logging.getLogRecordFactory()

        def record_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
            record = old_factory(*args, **kwargs)
            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx.is_valid:
                record.trace_id = f"{ctx.trace_id:032x}"
                record.span_id = f"{ctx.span_id:016x}"
                record.trace_flags = f"{ctx.trace_flags:02x}"
            else:
                record.trace_id = "0" * 32
                record.span_id = "0" * 16
                record.trace_flags = "00"
            return record

        logging.setLogRecordFactory(record_factory)

    @property
    def tracer(self) -> trace.Tracer:
        if self._tracer is None:
            raise RuntimeError("Telemetry not initialized")
        return self._tracer

    @property
    def meter(self) -> metrics.Meter:
        if self._meter is None:
            raise RuntimeError("Telemetry not initialized")
        return self._meter

    def shutdown(self) -> None:
        if self._tracer_provider:
            self._tracer_provider.shutdown()
        if self._meter_provider:
            self._meter_provider.shutdown()
```

```python
# --- Manual instrumentation helpers ---

def traced(
    name: Optional[str] = None,
    attributes: Optional[dict[str, str]] = None,
    record_exception: bool = True,
) -> Callable:
    """Decorator for manual span creation with error recording."""
    def decorator(func: Callable) -> Callable:
        span_name = name or f"{func.__module__}.{func.__qualname__}"

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(
                span_name,
                attributes=attributes or {},
            ) as span:
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(StatusCode.OK)
                    return result
                except Exception as exc:
                    if record_exception:
                        span.record_exception(exc)
                    span.set_status(StatusCode.ERROR, str(exc))
                    raise

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(
                span_name,
                attributes=attributes or {},
            ) as span:
                try:
                    result = func(*args, **kwargs)
                    span.set_status(StatusCode.OK)
                    return result
                except Exception as exc:
                    if record_exception:
                        span.record_exception(exc)
                    span.set_status(StatusCode.ERROR, str(exc))
                    raise

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


@contextmanager
def span_context(
    name: str,
    attributes: Optional[dict[str, Any]] = None,
) -> Generator[trace.Span, None, None]:
    """Context manager for creating spans with automatic error handling."""
    tracer = trace.get_tracer(__name__)
    with tracer.start_as_current_span(name, attributes=attributes or {}) as span:
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            span.set_status(StatusCode.ERROR, str(exc))
            raise
        else:
            span.set_status(StatusCode.OK)


class ServiceMetrics:
    """Application-level metrics with semantic conventions."""

    def __init__(self, meter: metrics.Meter) -> None:
        self.request_count: Counter = meter.create_counter(
            "http.server.request.count",
            description="Total HTTP requests",
            unit="requests",
        )
        self.request_duration: Histogram = meter.create_histogram(
            "http.server.request.duration",
            description="HTTP request duration",
            unit="ms",
        )
        self.active_requests: UpDownCounter = meter.create_up_down_counter(
            "http.server.active_requests",
            description="Currently active requests",
        )
        self.db_query_duration: Histogram = meter.create_histogram(
            "db.client.operation.duration",
            description="Database query duration",
            unit="ms",
        )
        self.cache_hits: Counter = meter.create_counter(
            "cache.hit.count",
            description="Cache hit count",
        )
        self.cache_misses: Counter = meter.create_counter(
            "cache.miss.count",
            description="Cache miss count",
        )
        self.business_events: Counter = meter.create_counter(
            "business.event.count",
            description="Business-level events",
        )

    def record_request(
        self, method: str, route: str, status: int, duration_ms: float
    ) -> None:
        labels = {"http.method": method, "http.route": route,
                  "http.status_code": str(status)}
        self.request_count.add(1, labels)
        self.request_duration.record(duration_ms, labels)

    def record_db_query(
        self, operation: str, table: str, duration_ms: float
    ) -> None:
        self.db_query_duration.record(
            duration_ms, {"db.operation": operation, "db.table": table}
        )
```

```yaml
# --- OpenTelemetry Collector configuration ---
# otel-collector-config.yaml

receivers:
  otlp:
    protocols:
      grpc:
        endpoint: "0.0.0.0:4317"
      http:
        endpoint: "0.0.0.0:4318"

processors:
  batch:
    send_batch_size: 8192
    timeout: 5s
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
    spike_limit_mib: 128
  resource:
    attributes:
      - key: deployment.environment
        value: production
        action: upsert
  tail_sampling:
    decision_wait: 10s
    policies:
      - name: error-policy
        type: status_code
        status_code: {status_codes: [ERROR]}
      - name: slow-policy
        type: latency
        latency: {threshold_ms: 1000}
      - name: probabilistic-policy
        type: probabilistic
        probabilistic: {sampling_percentage: 10}

exporters:
  otlp/tempo:
    endpoint: "tempo:4317"
    tls:
      insecure: true
  prometheusremotewrite:
    endpoint: "http://mimir:9009/api/v1/push"
  loki:
    endpoint: "http://loki:3100/loki/api/v1/push"

service:
  pipelines:
    traces:
      receivers: [otlp]
      processors: [memory_limiter, tail_sampling, batch]
      exporters: [otlp/tempo]
    metrics:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [prometheusremotewrite]
    logs:
      receivers: [otlp]
      processors: [memory_limiter, batch]
      exporters: [loki]
```

Key patterns for OpenTelemetry instrumentation:

1. **Resource attributes** -- attach service name, version, environment, and instance ID to all telemetry
2. **Auto-instrumentation** -- use OTel instrumentors for frameworks (FastAPI, SQLAlchemy, httpx, Redis) for zero-code coverage
3. **Log correlation** -- inject trace_id and span_id into log records via a custom LogRecordFactory
4. **Manual spans** -- use decorators and context managers for business-logic-level tracing with proper error recording
5. **Semantic conventions** -- follow OTel semantic conventions for metric and attribute names
6. **Tail sampling** -- sample errors and slow requests at 100% but probabilistically sample normal traffic at the collector
7. **Batch processing** -- use BatchSpanProcessor and collector-level batching to reduce export overhead
8. **Unified pipeline** -- route traces to Tempo, metrics to Mimir, and logs to Loki through a single OTel Collector'''
    ),
    (
        "observability/distributed-tracing-jaeger-tempo",
        "Design a distributed tracing system using Tempo and Jaeger for a microservices architecture with trace correlation, span linking, baggage propagation, and trace-based testing.",
        '''Distributed tracing with Tempo and Jaeger:

```python
# --- Distributed tracing framework with span linking ---

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from opentelemetry import context, trace
from opentelemetry.baggage import get_baggage, set_baggage
from opentelemetry.trace import Link, SpanKind, StatusCode


class SpanCategory(str, Enum):
    HTTP_SERVER = "http_server"
    HTTP_CLIENT = "http_client"
    DATABASE = "database"
    CACHE = "cache"
    MESSAGE_PRODUCER = "message_producer"
    MESSAGE_CONSUMER = "message_consumer"
    INTERNAL = "internal"


@dataclass
class TraceContext:
    """Encapsulates trace context for cross-service propagation."""
    trace_id: str
    span_id: str
    baggage: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_current(cls) -> TraceContext:
        span = trace.get_current_span()
        ctx = span.get_span_context()
        return cls(
            trace_id=f"{ctx.trace_id:032x}",
            span_id=f"{ctx.span_id:016x}",
            baggage={
                k: get_baggage(k) or ""
                for k in ["tenant.id", "request.id", "user.id"]
                if get_baggage(k)
            },
        )

    def inject_headers(self) -> dict[str, str]:
        return {
            "traceparent": f"00-{self.trace_id}-{self.span_id}-01",
            **{f"baggage-{k}": v for k, v in self.baggage.items()},
        }


class TracingManager:
    """High-level tracing API for microservice instrumentation."""

    def __init__(self, service_name: str) -> None:
        self.service_name = service_name
        self.tracer = trace.get_tracer(service_name)

    def start_server_span(
        self,
        operation: str,
        headers: dict[str, str],
        attributes: Optional[dict[str, Any]] = None,
    ) -> trace.Span:
        """Start a server span from incoming request headers."""
        span = self.tracer.start_span(
            name=operation,
            kind=SpanKind.SERVER,
            attributes={
                "service.name": self.service_name,
                "span.category": SpanCategory.HTTP_SERVER.value,
                **(attributes or {}),
            },
        )
        return span

    def create_linked_span(
        self,
        name: str,
        linked_contexts: list[trace.SpanContext],
        attributes: Optional[dict[str, Any]] = None,
    ) -> trace.Span:
        """Create a span linked to other spans (fan-in pattern)."""
        links = [Link(ctx) for ctx in linked_contexts]
        return self.tracer.start_span(
            name=name,
            kind=SpanKind.INTERNAL,
            links=links,
            attributes=attributes or {},
        )

    def trace_database_call(
        self,
        operation: str,
        table: str,
        statement: str,
    ) -> trace.Span:
        """Create a span for database operations with semantic attrs."""
        return self.tracer.start_span(
            name=f"DB {operation} {table}",
            kind=SpanKind.CLIENT,
            attributes={
                "db.system": "postgresql",
                "db.operation": operation,
                "db.sql.table": table,
                "db.statement": statement[:1000],
                "span.category": SpanCategory.DATABASE.value,
            },
        )

    def trace_message_publish(
        self,
        topic: str,
        message_id: str,
    ) -> trace.Span:
        """Create a span for async message publishing."""
        return self.tracer.start_span(
            name=f"PUBLISH {topic}",
            kind=SpanKind.PRODUCER,
            attributes={
                "messaging.system": "kafka",
                "messaging.destination": topic,
                "messaging.message_id": message_id,
                "span.category": SpanCategory.MESSAGE_PRODUCER.value,
            },
        )


class BaggagePropagator:
    """Propagate business context across service boundaries."""

    STANDARD_KEYS = ["tenant.id", "request.id", "feature.flags",
                     "user.tier", "experiment.group"]

    @staticmethod
    def set_business_context(
        tenant_id: str,
        request_id: str,
        user_tier: str = "standard",
    ) -> None:
        ctx = context.get_current()
        ctx = set_baggage("tenant.id", tenant_id, ctx)
        ctx = set_baggage("request.id", request_id, ctx)
        ctx = set_baggage("user.tier", user_tier, ctx)
        context.attach(ctx)

    @staticmethod
    def get_tenant_id() -> Optional[str]:
        return get_baggage("tenant.id")
```

```python
# --- Trace-based testing framework ---

from dataclasses import dataclass
from typing import Any


@dataclass
class SpanAssertion:
    """Assertion for validating span properties in trace tests."""
    name_pattern: str
    kind: Optional[SpanKind] = None
    min_duration_ms: Optional[float] = None
    max_duration_ms: Optional[float] = None
    required_attributes: dict[str, Any] = field(default_factory=dict)
    status: Optional[StatusCode] = None
    child_count: Optional[int] = None


class TraceTestValidator:
    """Validate distributed traces against expected patterns."""

    def __init__(self, tempo_url: str = "http://tempo:3200") -> None:
        self.tempo_url = tempo_url

    async def get_trace(self, trace_id: str) -> dict[str, Any]:
        import httpx
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.tempo_url}/api/traces/{trace_id}"
            )
            resp.raise_for_status()
            return resp.json()

    async def validate_trace(
        self,
        trace_id: str,
        expected_spans: list[SpanAssertion],
        max_trace_duration_ms: Optional[float] = None,
    ) -> list[str]:
        """Validate trace structure against expected span patterns."""
        trace_data = await self.get_trace(trace_id)
        errors: list[str] = []
        spans = self._extract_spans(trace_data)

        for assertion in expected_spans:
            matching = [
                s for s in spans
                if assertion.name_pattern in s.get("operationName", "")
            ]
            if not matching:
                errors.append(
                    f"No span matching '{assertion.name_pattern}' found"
                )
                continue

            span = matching[0]
            duration_ms = span.get("duration", 0) / 1000

            if assertion.min_duration_ms and duration_ms < assertion.min_duration_ms:
                errors.append(
                    f"Span '{assertion.name_pattern}' too fast: "
                    f"{duration_ms:.1f}ms < {assertion.min_duration_ms}ms"
                )
            if assertion.max_duration_ms and duration_ms > assertion.max_duration_ms:
                errors.append(
                    f"Span '{assertion.name_pattern}' too slow: "
                    f"{duration_ms:.1f}ms > {assertion.max_duration_ms}ms"
                )

            for key, expected_val in assertion.required_attributes.items():
                actual = self._get_attr(span, key)
                if actual != expected_val:
                    errors.append(
                        f"Span '{assertion.name_pattern}' attr '{key}': "
                        f"expected {expected_val}, got {actual}"
                    )

        return errors

    def _extract_spans(self, trace_data: dict[str, Any]) -> list[dict]:
        spans = []
        for batch in trace_data.get("batches", []):
            for scope_spans in batch.get("scopeSpans", []):
                spans.extend(scope_spans.get("spans", []))
        return spans

    def _get_attr(self, span: dict, key: str) -> Any:
        for attr in span.get("attributes", []):
            if attr.get("key") == key:
                return attr.get("value", {}).get("stringValue")
        return None
```

```yaml
# --- Grafana Tempo configuration ---
# tempo.yaml

server:
  http_listen_port: 3200

distributor:
  receivers:
    otlp:
      protocols:
        grpc:
          endpoint: "0.0.0.0:4317"

ingester:
  max_block_duration: 5m
  max_block_bytes: 5_000_000

compactor:
  compaction:
    block_retention: 720h  # 30 days
    compacted_block_retention: 1h

storage:
  trace:
    backend: s3
    s3:
      bucket: tempo-traces
      endpoint: s3.us-east-1.amazonaws.com
      region: us-east-1
    wal:
      path: /var/tempo/wal
    block:
      bloom_filter_false_positive: 0.05
      v2_index_downsample_bytes: 1000
      v2_encoding: zstd

metrics_generator:
  registry:
    external_labels:
      source: tempo
  storage:
    path: /var/tempo/generator/wal
    remote_write:
      - url: http://mimir:9009/api/v1/push
  traces_storage:
    path: /var/tempo/generator/traces
  processor:
    service_graphs:
      dimensions: [service.namespace]
      enable_client_server_prefix: true
    span_metrics:
      dimensions: [http.method, http.status_code, http.route]

overrides:
  defaults:
    metrics_generator:
      processors: [service-graphs, span-metrics]
```

| Feature | Jaeger | Tempo | Zipkin |
|---------|--------|-------|--------|
| Storage backend | Elasticsearch, Cassandra | S3, GCS, Azure Blob | MySQL, Cassandra, ES |
| Query language | Custom | TraceQL | Custom |
| Sampling | Head-based | Tail (via Collector) | Head-based |
| Service graph | Manual | Auto-generated | No |
| Cost at scale | $$$ (indexed) | $ (object storage) | $$ |
| Native OTel | Yes | Yes | Partial |
| Metrics from traces | No | Yes (span metrics) | No |

Key patterns for distributed tracing:

1. **Span categories** -- classify spans (HTTP, DB, cache, messaging) for consistent filtering and dashboarding
2. **Baggage propagation** -- carry business context (tenant ID, request ID) across service boundaries automatically
3. **Span linking** -- connect causally-related spans across async boundaries (fan-in/fan-out patterns)
4. **Semantic conventions** -- use OTel semantic attribute names for cross-vendor interoperability
5. **TraceQL** -- leverage Tempo's query language to search traces by attributes, duration, and structure
6. **Trace-based testing** -- validate trace structure in integration tests to catch instrumentation regressions
7. **Span metrics** -- derive RED metrics (Rate, Errors, Duration) directly from traces to reduce metric cardinality'''
    ),
    (
        "observability/continuous-profiling-pyroscope",
        "Implement continuous profiling with Pyroscope and pprof for a Python/Go application, covering CPU profiling, memory allocation tracking, mutex contention, and profile-guided optimization.",
        '''Continuous profiling with Pyroscope and pprof:

```python
# --- Python continuous profiling with Pyroscope ---

from __future__ import annotations

import cProfile
import io
import logging
import os
import pstats
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Generator, Optional

import pyroscope

logger = logging.getLogger(__name__)


class ProfileType(str, Enum):
    CPU = "cpu"
    WALL = "wall"
    ALLOC_OBJECTS = "alloc_objects"
    ALLOC_SPACE = "alloc_space"
    INUSE_OBJECTS = "inuse_objects"
    INUSE_SPACE = "inuse_space"
    GOROUTINES = "goroutines"
    MUTEX_COUNT = "mutex_count"
    MUTEX_DURATION = "mutex_duration"
    BLOCK_COUNT = "block_count"
    BLOCK_DURATION = "block_duration"


@dataclass
class PyroscopeConfig:
    """Pyroscope profiling configuration."""
    server_address: str = "http://pyroscope:4040"
    application_name: str = "myapp"
    environment: str = "production"
    sample_rate: int = 100  # Hz
    enable_cpu: bool = True
    enable_memory: bool = True
    tags: dict[str, str] = field(default_factory=dict)
    auth_token: Optional[str] = None
    tenant_id: Optional[str] = None


class ContinuousProfiler:
    """Manage continuous profiling with Pyroscope integration."""

    def __init__(self, config: PyroscopeConfig) -> None:
        self.config = config
        self._running = False

    def start(self) -> None:
        """Initialize and start continuous profiling."""
        tags = {
            "env": self.config.environment,
            "hostname": os.environ.get("HOSTNAME", "unknown"),
            "pod": os.environ.get("POD_NAME", "unknown"),
            "version": os.environ.get("APP_VERSION", "unknown"),
            **self.config.tags,
        }
        pyroscope.configure(
            application_name=self.config.application_name,
            server_address=self.config.server_address,
            sample_rate=self.config.sample_rate,
            auth_token=self.config.auth_token or "",
            tags=tags,
        )
        self._running = True
        logger.info(
            "Continuous profiling started for %s at %dHz",
            self.config.application_name,
            self.config.sample_rate,
        )

    def stop(self) -> None:
        """Stop continuous profiling."""
        self._running = False
        pyroscope.shutdown()
        logger.info("Continuous profiling stopped")

    @contextmanager
    def tag_scope(
        self, **tags: str
    ) -> Generator[None, None, None]:
        """Add dynamic tags within a scope for flame graph filtering."""
        with pyroscope.tag_wrapper(tags):
            yield

    @contextmanager
    def profile_block(
        self, name: str, threshold_ms: float = 100.0
    ) -> Generator[dict[str, Any], None, None]:
        """Profile a specific code block and log if it exceeds threshold."""
        profiler = cProfile.Profile()
        result: dict[str, Any] = {"name": name}
        start = time.perf_counter()

        profiler.enable()
        try:
            yield result
        finally:
            profiler.disable()
            elapsed_ms = (time.perf_counter() - start) * 1000
            result["duration_ms"] = elapsed_ms

            if elapsed_ms > threshold_ms:
                stream = io.StringIO()
                stats = pstats.Stats(profiler, stream=stream)
                stats.sort_stats("cumulative")
                stats.print_stats(20)
                result["profile"] = stream.getvalue()
                logger.warning(
                    "Slow block '%s': %.1fms (threshold: %.1fms)\n%s",
                    name, elapsed_ms, threshold_ms, stream.getvalue()[:2000],
                )


class MemoryProfiler:
    """Track memory allocations and detect leaks."""

    def __init__(self) -> None:
        self._snapshots: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def take_snapshot(self, label: str = "") -> dict[str, Any]:
        """Capture current memory allocation snapshot."""
        import tracemalloc
        if not tracemalloc.is_tracing():
            tracemalloc.start(25)  # 25 frame depth

        snapshot = tracemalloc.take_snapshot()
        top_stats = snapshot.statistics("lineno")

        result = {
            "label": label,
            "timestamp": time.time(),
            "total_mb": sum(s.size for s in top_stats) / 1024 / 1024,
            "top_allocations": [
                {
                    "file": str(stat.traceback),
                    "size_kb": stat.size / 1024,
                    "count": stat.count,
                }
                for stat in top_stats[:20]
            ],
        }
        with self._lock:
            self._snapshots.append(result)
        return result

    def compare_snapshots(
        self, label_before: str, label_after: str
    ) -> list[dict[str, Any]]:
        """Compare two snapshots to find memory growth."""
        before = next(
            (s for s in self._snapshots if s["label"] == label_before), None
        )
        after = next(
            (s for s in self._snapshots if s["label"] == label_after), None
        )
        if not before or not after:
            return []

        growth = after["total_mb"] - before["total_mb"]
        return [{
            "total_growth_mb": growth,
            "before_mb": before["total_mb"],
            "after_mb": after["total_mb"],
        }]
```

```go
// --- Go continuous profiling with pprof and Pyroscope ---

package profiling

import (
	"context"
	"fmt"
	"log"
	"net/http"
	_ "net/http/pprof"
	"os"
	"runtime"
	"runtime/pprof"
	"sync"
	"time"

	pyroscope "github.com/grafana/pyroscope-go"
)

type ProfilerConfig struct {
	ApplicationName string
	ServerAddress   string
	Environment     string
	SampleRate      int
	EnableCPU       bool
	EnableMemory    bool
	EnableMutex     bool
	EnableBlock     bool
	MutexRate       int
	BlockRate       int
}

type ContinuousProfiler struct {
	config   ProfilerConfig
	profiler *pyroscope.Profiler
	mu       sync.Mutex
}

func NewProfiler(cfg ProfilerConfig) *ContinuousProfiler {
	return &ContinuousProfiler{config: cfg}
}

func (p *ContinuousProfiler) Start(ctx context.Context) error {
	p.mu.Lock()
	defer p.mu.Unlock()

	if p.config.EnableMutex && p.config.MutexRate > 0 {
		runtime.SetMutexProfileFraction(p.config.MutexRate)
	}
	if p.config.EnableBlock && p.config.BlockRate > 0 {
		runtime.SetBlockProfileRate(p.config.BlockRate)
	}

	profileTypes := []pyroscope.ProfileType{}
	if p.config.EnableCPU {
		profileTypes = append(profileTypes, pyroscope.ProfileCPU)
	}
	if p.config.EnableMemory {
		profileTypes = append(profileTypes,
			pyroscope.ProfileAllocObjects,
			pyroscope.ProfileAllocSpace,
			pyroscope.ProfileInuseObjects,
			pyroscope.ProfileInuseSpace,
		)
	}
	if p.config.EnableMutex {
		profileTypes = append(profileTypes,
			pyroscope.ProfileMutexCount,
			pyroscope.ProfileMutexDuration,
		)
	}
	if p.config.EnableBlock {
		profileTypes = append(profileTypes,
			pyroscope.ProfileBlockCount,
			pyroscope.ProfileBlockDuration,
		)
	}

	hostname, _ := os.Hostname()
	profiler, err := pyroscope.Start(pyroscope.Config{
		ApplicationName: p.config.ApplicationName,
		ServerAddress:   p.config.ServerAddress,
		Tags: map[string]string{
			"env":      p.config.Environment,
			"hostname": hostname,
			"version":  os.Getenv("APP_VERSION"),
		},
		ProfileTypes: profileTypes,
	})
	if err != nil {
		return fmt.Errorf("pyroscope start failed: %w", err)
	}

	p.profiler = profiler
	log.Printf("Profiling started for %s", p.config.ApplicationName)

	// Expose pprof on debug port
	go func() {
		mux := http.NewServeMux()
		mux.HandleFunc("/debug/pprof/", pprof.Index)
		server := &http.Server{Addr: ":6060", Handler: mux}
		go func() {
			<-ctx.Done()
			server.Close()
		}()
		if err := server.ListenAndServe(); err != http.ErrServerClosed {
			log.Printf("pprof server error: %v", err)
		}
	}()

	return nil
}

// TagScope adds dynamic tags for a profiling scope
func (p *ContinuousProfiler) TagScope(
	name, value string,
	fn func(),
) {
	pyroscope.TagWrapper(
		context.Background(),
		pyroscope.Labels(name, value),
		func(ctx context.Context) {
			fn()
		},
	)
}

func (p *ContinuousProfiler) Stop() error {
	p.mu.Lock()
	defer p.mu.Unlock()
	if p.profiler != nil {
		return p.profiler.Stop()
	}
	return nil
}
```

```yaml
# --- Pyroscope server configuration ---
# pyroscope-values.yaml (Helm)

pyroscope:
  replicaCount: 2
  resources:
    requests:
      cpu: 500m
      memory: 1Gi
    limits:
      cpu: 2000m
      memory: 4Gi

  config:
    storage:
      backend: s3
      s3:
        bucket_name: pyroscope-profiles
        region: us-east-1
    retention:
      max_duration: 720h  # 30 days
    limits:
      max_label_names_per_series: 30
      max_sessions_per_series: 16
      ingestion_rate_mb: 10
      ingestion_burst_size_mb: 20

  # Grafana data source for flame graphs
  grafanaDatasource:
    enabled: true

---
# Kubernetes deployment with profiling sidecar
apiVersion: apps/v1
kind: Deployment
metadata:
  name: myapp
spec:
  template:
    metadata:
      annotations:
        pyroscope.io/scrape: "true"
        pyroscope.io/port: "6060"
        pyroscope.io/profile-cpu-enabled: "true"
        pyroscope.io/profile-mem-enabled: "true"
    spec:
      containers:
        - name: app
          env:
            - name: PYROSCOPE_SERVER_ADDRESS
              value: "http://pyroscope:4040"
            - name: PYROSCOPE_APPLICATION_NAME
              value: "myapp"
```

| Profile Type | Language | Overhead | Use Case | Tool |
|-------------|----------|----------|----------|------|
| CPU | Python/Go | 1-5% | Hot path optimization | Pyroscope, py-spy |
| Heap (alloc) | Go | 1-3% | Memory leak detection | pprof, Pyroscope |
| tracemalloc | Python | 5-15% | Allocation tracking | tracemalloc, memray |
| Mutex | Go | 1-2% | Lock contention | pprof |
| Block | Go | 1-2% | Blocking operations | pprof |
| Wall clock | Python | 2-5% | I/O-bound profiling | Pyroscope, py-spy |
| Off-CPU | Go/Python | 2-5% | Scheduling delays | eBPF, async-profiler |

Key patterns for continuous profiling:

1. **Always-on profiling** -- run Pyroscope in production at 100Hz with <5% overhead to catch intermittent hot paths
2. **Dynamic tagging** -- use tag_wrapper/TagScope to filter flame graphs by endpoint, tenant, or feature flag
3. **Memory snapshot comparison** -- take before/after snapshots to isolate allocation growth and detect leaks
4. **Mutex profiling** -- enable Go mutex/block profiling to find lock contention under load
5. **Profile-guided optimization** -- use production flame graphs to identify the 20% of code consuming 80% of resources
6. **Debug endpoint** -- expose pprof on a separate port (6060) behind network policy for ad-hoc deep dives
7. **Retention policy** -- keep 30 days of profiles with S3 backend for cost-effective long-term storage'''
    ),
    (
        "observability/log-aggregation-loki-fluentbit",
        "Design a log aggregation pipeline using Grafana Loki, Fluent Bit, and structured logging with log correlation, multi-tenancy, and retention policies.",
        '''Log aggregation with Loki, Fluent Bit, and structured logging:

```python
# --- Structured logging with trace correlation ---

from __future__ import annotations

import json
import logging
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from opentelemetry import trace


@dataclass
class LogContext:
    """Structured log context with trace correlation."""
    service: str
    environment: str
    version: str
    hostname: str = field(default_factory=lambda: os.environ.get("HOSTNAME", "unknown"))
    pod: str = field(default_factory=lambda: os.environ.get("POD_NAME", "unknown"))
    namespace: str = field(default_factory=lambda: os.environ.get("POD_NAMESPACE", "default"))


class StructuredJsonFormatter(logging.Formatter):
    """JSON log formatter with OTel trace correlation."""

    LEVEL_MAP = {
        "DEBUG": "debug",
        "INFO": "info",
        "WARNING": "warn",
        "ERROR": "error",
        "CRITICAL": "fatal",
    }

    def __init__(self, log_context: LogContext) -> None:
        super().__init__()
        self.log_context = log_context

    def format(self, record: logging.LogRecord) -> str:
        span = trace.get_current_span()
        span_ctx = span.get_span_context()

        log_entry: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc
            ).isoformat(),
            "level": self.LEVEL_MAP.get(record.levelname, record.levelname),
            "message": record.getMessage(),
            "logger": record.name,
            "caller": f"{record.pathname}:{record.lineno}",
            "function": record.funcName,
            "service": self.log_context.service,
            "environment": self.log_context.environment,
            "version": self.log_context.version,
            "hostname": self.log_context.hostname,
            "pod": self.log_context.pod,
            "namespace": self.log_context.namespace,
        }

        # Trace correlation
        if span_ctx.is_valid:
            log_entry["trace_id"] = f"{span_ctx.trace_id:032x}"
            log_entry["span_id"] = f"{span_ctx.span_id:016x}"

        # Exception info
        if record.exc_info and record.exc_info[1]:
            log_entry["error"] = {
                "type": type(record.exc_info[1]).__name__,
                "message": str(record.exc_info[1]),
                "stacktrace": self.formatException(record.exc_info),
            }

        # Extra fields from record
        for key in ["request_id", "user_id", "tenant_id", "duration_ms",
                     "http_method", "http_path", "http_status"]:
            val = getattr(record, key, None)
            if val is not None:
                log_entry[key] = val

        return json.dumps(log_entry, default=str)


def setup_logging(
    service_name: str,
    level: str = "INFO",
    environment: str = "production",
    version: str = "1.0.0",
) -> None:
    """Configure structured JSON logging with trace correlation."""
    ctx = LogContext(
        service=service_name,
        environment=environment,
        version=version,
    )
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter(ctx))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper()))

    # Reduce noisy loggers
    for noisy in ["urllib3", "botocore", "httpx"]:
        logging.getLogger(noisy).setLevel(logging.WARNING)


class LogAggregator:
    """Query and analyze logs from Loki."""

    def __init__(self, loki_url: str = "http://loki:3100") -> None:
        self.loki_url = loki_url

    async def query_logs(
        self,
        logql: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        """Execute LogQL query against Loki."""
        import httpx

        params: dict[str, Any] = {"query": logql, "limit": limit}
        if start:
            params["start"] = int(start.timestamp() * 1e9)
        if end:
            params["end"] = int(end.timestamp() * 1e9)

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.loki_url}/loki/api/v1/query_range",
                params=params,
            )
            resp.raise_for_status()
            data = resp.json()

        results = []
        for stream in data.get("data", {}).get("result", []):
            labels = stream.get("stream", {})
            for ts, line in stream.get("values", []):
                results.append({
                    "timestamp": ts,
                    "labels": labels,
                    "line": line,
                })
        return results

    async def get_logs_for_trace(self, trace_id: str) -> list[dict[str, Any]]:
        """Get all logs correlated with a specific trace."""
        return await self.query_logs(
            f'{{service=~".+"}} |= `{trace_id}` | json'
        )

    async def get_error_rate(
        self, service: str, window: str = "5m"
    ) -> float:
        """Calculate error rate for a service over a time window."""
        result = await self.query_logs(
            f'sum(rate({{service="{service}"}} '
            f'| json | level="error" [{window}])) / '
            f'sum(rate({{service="{service}"}} [{window}]))'
        )
        if result:
            return float(result[0].get("line", 0))
        return 0.0
```

```yaml
# --- Fluent Bit configuration ---
# fluent-bit.conf

[SERVICE]
    Flush         5
    Log_Level     info
    Daemon        off
    Parsers_File  parsers.conf
    HTTP_Server   On
    HTTP_Listen   0.0.0.0
    HTTP_Port     2020
    storage.path  /var/log/flb-storage/
    storage.sync  normal
    storage.backlog.mem_limit 5M

[INPUT]
    Name              tail
    Tag               kube.*
    Path              /var/log/containers/*.log
    Parser            cri
    DB                /var/log/flb-kube.db
    Mem_Buf_Limit     10MB
    Skip_Long_Lines   On
    Refresh_Interval  10
    storage.type      filesystem

[FILTER]
    Name                kubernetes
    Match               kube.*
    Kube_URL            https://kubernetes.default.svc:443
    Kube_CA_File        /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
    Kube_Token_File     /var/run/secrets/kubernetes.io/serviceaccount/token
    Merge_Log           On
    K8S-Logging.Parser  On
    K8S-Logging.Exclude On
    Labels              On
    Annotations         Off

[FILTER]
    Name    modify
    Match   kube.*
    # Drop high-cardinality fields
    Remove  kubernetes.pod_id
    Remove  kubernetes.docker_id
    Remove  stream

[FILTER]
    Name    grep
    Match   kube.*
    # Exclude health check logs
    Exclude log ^GET /healthz

[FILTER]
    Name          multiline
    Match         kube.*
    multiline.key_content log
    multiline.parser      python-traceback

[OUTPUT]
    Name          loki
    Match         kube.*
    Host          loki-gateway
    Port          80
    Labels        job=fluentbit, namespace=$kubernetes['namespace_name'], pod=$kubernetes['pod_name'], container=$kubernetes['container_name']
    Label_Keys    $level, $service
    Remove_Keys   kubernetes, stream
    Line_Format   json
    Auto_Kubernetes_Labels off
    Tenant_ID     ${TENANT_ID}
    Workers       2
    Retry_Limit   5

---
# parsers.conf
[PARSER]
    Name        cri
    Format      regex
    Regex       ^(?<time>[^ ]+) (?<stream>stdout|stderr) (?<logtag>[^ ]*) (?<log>.*)$
    Time_Key    time
    Time_Format %Y-%m-%dT%H:%M:%S.%L%z

[MULTILINE_PARSER]
    Name          python-traceback
    Type          regex
    Flush_timeout 1000
    Rule          "start_state"  "/^Traceback/"        "cont"
    Rule          "cont"         "/^\s+/"              "cont"
    Rule          "cont"         "/^\w+Error/"         "end"
```

```yaml
# --- Loki configuration ---
# loki-config.yaml

auth_enabled: true  # Multi-tenancy

server:
  http_listen_port: 3100

common:
  path_prefix: /loki
  storage:
    s3:
      s3: s3://us-east-1/loki-chunks
      region: us-east-1
  ring:
    kvstore:
      store: memberlist
  replication_factor: 3

schema_config:
  configs:
    - from: "2024-01-01"
      store: tsdb
      object_store: s3
      schema: v13
      index:
        prefix: loki_index_
        period: 24h

limits_config:
  retention_period: 720h  # 30 days
  max_query_length: 721h
  max_query_parallelism: 32
  ingestion_rate_mb: 20
  ingestion_burst_size_mb: 30
  per_stream_rate_limit: 5MB
  max_entries_limit_per_query: 10000
  max_label_names_per_series: 30

  # Per-tenant overrides
  per_tenant_override_config: /etc/loki/overrides.yaml

compactor:
  working_directory: /loki/compactor
  compaction_interval: 10m
  retention_enabled: true
  retention_delete_delay: 2h
  retention_delete_worker_count: 150

query_scheduler:
  max_outstanding_requests_per_tenant: 4096

ruler:
  storage:
    type: s3
    s3:
      bucketnames: loki-rules
  alertmanager_url: http://alertmanager:9093
  ring:
    kvstore:
      store: memberlist
  rule_path: /loki/rules
```

| Feature | Loki | Elasticsearch | Datadog Logs | CloudWatch |
|---------|------|---------------|-------------|------------|
| Indexing strategy | Labels only | Full-text | Full-text | Full-text |
| Storage cost | $ (object store) | $$$$ (indexed) | $$$ | $$ |
| Query speed | Good (label filter) | Excellent | Excellent | Good |
| Query language | LogQL | KQL/Lucene | Custom | Insights |
| Multi-tenancy | Native | Index-per-tenant | Org-based | Account |
| Correlation | Trace ID -> Tempo | APM integration | Built-in | X-Ray |
| Retention | Configurable | ILM policies | Plan-based | Log groups |

Key patterns for log aggregation:

1. **Structured JSON logging** -- emit machine-parseable JSON from applications with consistent field names
2. **Trace correlation** -- embed trace_id and span_id in every log line for jump-to-trace from logs
3. **Label discipline** -- keep Loki label cardinality low (service, namespace, level) and filter content with LogQL
4. **Multi-line parsing** -- configure Fluent Bit multiline parser for Python tracebacks and Java stack traces
5. **Multi-tenancy** -- use Loki tenant_id header to isolate logs per team or environment
6. **Retention tiers** -- set different retention periods per tenant (30 days prod, 7 days dev) via overrides
7. **Backpressure handling** -- use filesystem-backed buffering in Fluent Bit with mem_buf_limit to survive Loki outages'''
    ),
    (
        "observability/slo-based-alerting",
        "Implement SLO-based alerting with error budgets, burn rate alerts, and multi-window alerting using Prometheus, Grafana, and Sloth for a production service.",
        '''SLO-based alerting with error budgets and burn rates:

```python
# --- SLO definition and error budget tracking ---

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SLIType(str, Enum):
    AVAILABILITY = "availability"     # success_ratio
    LATENCY = "latency"               # ratio below threshold
    THROUGHPUT = "throughput"          # requests per second
    CORRECTNESS = "correctness"       # correct response ratio
    FRESHNESS = "freshness"           # data age below threshold


class BurnRateSeverity(str, Enum):
    CRITICAL = "critical"   # 14.4x burn rate, 2% budget in 1h
    HIGH = "high"           # 6x burn rate, 5% budget in 6h
    MEDIUM = "medium"       # 3x burn rate, 10% budget in 3d
    LOW = "low"             # 1x burn rate, on track to exhaust


@dataclass
class SLODefinition:
    """Service Level Objective specification."""
    name: str
    service: str
    sli_type: SLIType
    target: float                     # e.g. 0.999 = 99.9%
    window_days: int = 30             # rolling window
    description: str = ""
    owner_team: str = ""
    alert_burn_rates: bool = True
    page_on_critical: bool = True

    @property
    def error_budget_fraction(self) -> float:
        return 1.0 - self.target

    @property
    def error_budget_minutes(self) -> float:
        return self.window_days * 24 * 60 * self.error_budget_fraction

    @property
    def error_budget_display(self) -> str:
        mins = self.error_budget_minutes
        if mins >= 60:
            return f"{mins / 60:.1f} hours"
        return f"{mins:.1f} minutes"


@dataclass
class ErrorBudgetStatus:
    """Current error budget consumption status."""
    slo: SLODefinition
    budget_total: float
    budget_consumed: float
    budget_remaining: float
    burn_rate_1h: float
    burn_rate_6h: float
    burn_rate_24h: float
    burn_rate_3d: float
    current_sli: float
    window_start: datetime
    window_end: datetime

    @property
    def budget_remaining_percent(self) -> float:
        if self.budget_total == 0:
            return 0.0
        return (self.budget_remaining / self.budget_total) * 100

    @property
    def is_budget_exhausted(self) -> bool:
        return self.budget_remaining <= 0

    @property
    def severity(self) -> Optional[BurnRateSeverity]:
        if self.burn_rate_1h >= 14.4 and self.burn_rate_6h >= 6.0:
            return BurnRateSeverity.CRITICAL
        if self.burn_rate_6h >= 6.0 and self.burn_rate_24h >= 3.0:
            return BurnRateSeverity.HIGH
        if self.burn_rate_24h >= 3.0 and self.burn_rate_3d >= 1.0:
            return BurnRateSeverity.MEDIUM
        if self.burn_rate_3d >= 1.0:
            return BurnRateSeverity.LOW
        return None

    @property
    def time_until_exhaustion(self) -> Optional[timedelta]:
        if self.burn_rate_1h <= 0:
            return None
        hours_left = (
            self.budget_remaining
            / (self.budget_total * self.burn_rate_1h / (self.slo.window_days * 24))
        )
        return timedelta(hours=max(0, hours_left))


class SLOMonitor:
    """Monitor SLOs and calculate error budgets from Prometheus."""

    def __init__(self, prometheus_url: str = "http://prometheus:9090") -> None:
        self.prometheus_url = prometheus_url

    async def get_error_budget_status(
        self, slo: SLODefinition
    ) -> ErrorBudgetStatus:
        """Calculate current error budget status from Prometheus metrics."""
        now = datetime.now(timezone.utc)
        window_start = now - timedelta(days=slo.window_days)

        sli_value = await self._query_sli(slo, f"{slo.window_days}d")
        burn_1h = await self._query_burn_rate(slo, "1h")
        burn_6h = await self._query_burn_rate(slo, "6h")
        burn_24h = await self._query_burn_rate(slo, "24h")
        burn_3d = await self._query_burn_rate(slo, "3d")

        budget_total = slo.error_budget_fraction
        budget_consumed = max(0.0, 1.0 - sli_value) if sli_value else 0.0
        budget_remaining = budget_total - budget_consumed

        return ErrorBudgetStatus(
            slo=slo,
            budget_total=budget_total,
            budget_consumed=budget_consumed,
            budget_remaining=budget_remaining,
            burn_rate_1h=burn_1h,
            burn_rate_6h=burn_6h,
            burn_rate_24h=burn_24h,
            burn_rate_3d=burn_3d,
            current_sli=sli_value or 0.0,
            window_start=window_start,
            window_end=now,
        )

    async def _query_sli(
        self, slo: SLODefinition, window: str
    ) -> Optional[float]:
        """Query SLI value from Prometheus."""
        import httpx

        if slo.sli_type == SLIType.AVAILABILITY:
            query = (
                f'sum(rate(http_requests_total{{service="{slo.service}",'
                f'code!~"5.."}}[{window}])) / '
                f'sum(rate(http_requests_total{{service="{slo.service}"}}[{window}]))'
            )
        elif slo.sli_type == SLIType.LATENCY:
            query = (
                f'sum(rate(http_request_duration_seconds_bucket{{service="{slo.service}",'
                f'le="0.5"}}[{window}])) / '
                f'sum(rate(http_request_duration_seconds_count{{service="{slo.service}"}}[{window}]))'
            )
        else:
            return None

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": query},
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("data", {}).get("result", [])
        if results:
            return float(results[0]["value"][1])
        return None

    async def _query_burn_rate(
        self, slo: SLODefinition, window: str
    ) -> float:
        """Query burn rate from Sloth-generated recording rules."""
        import httpx

        query = (
            f'slo:sli_error:ratio_rate_{window}{{slo_service="{slo.service}",'
            f'slo_name="{slo.name}"}} / '
            f'{slo.error_budget_fraction}'
        )
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.prometheus_url}/api/v1/query",
                params={"query": query},
            )
            resp.raise_for_status()
            data = resp.json()

        results = data.get("data", {}).get("result", [])
        if results:
            return float(results[0]["value"][1])
        return 0.0
```

```yaml
# --- Sloth SLO definitions ---
# slos/api-gateway.yaml

version: "prometheus/v1"
service: "api-gateway"
labels:
  team: platform
  tier: "0"

slos:
  - name: "requests-availability"
    objective: 99.9
    description: "99.9% of HTTP requests should succeed"
    sli:
      events:
        error_query: >
          sum(rate(http_requests_total{service="api-gateway",code=~"5.."}[{{.window}}]))
        total_query: >
          sum(rate(http_requests_total{service="api-gateway"}[{{.window}}]))
    alerting:
      name: ApiGatewayHighErrorRate
      labels:
        severity: "{{ if .BurnRateSeverity }}{{ .BurnRateSeverity }}{{ end }}"
        team: platform
      annotations:
        summary: "API Gateway error budget burn rate is too high"
        runbook: "https://runbooks.internal/api-gateway-errors"
      page_alert:
        labels:
          routing: "pagerduty"
      ticket_alert:
        labels:
          routing: "slack-platform"

  - name: "requests-latency"
    objective: 99.0
    description: "99% of requests should complete within 500ms"
    sli:
      events:
        error_query: >
          sum(rate(http_request_duration_seconds_count{service="api-gateway"}[{{.window}}]))
          -
          sum(rate(http_request_duration_seconds_bucket{service="api-gateway",le="0.5"}[{{.window}}]))
        total_query: >
          sum(rate(http_request_duration_seconds_count{service="api-gateway"}[{{.window}}]))
    alerting:
      name: ApiGatewayHighLatency
      labels:
        severity: "{{ if .BurnRateSeverity }}{{ .BurnRateSeverity }}{{ end }}"
        team: platform
      annotations:
        summary: "API Gateway latency SLO is burning budget too fast"
        runbook: "https://runbooks.internal/api-gateway-latency"
      page_alert:
        labels:
          routing: "pagerduty"
      ticket_alert:
        labels:
          routing: "slack-platform"
```

```yaml
# --- Multi-window burn rate Prometheus alerts ---
# Generated by Sloth, annotated for clarity

groups:
  - name: slo.api-gateway.alerts
    rules:
      # CRITICAL: 14.4x burn in 5m AND 6x burn in 1h -> page immediately
      # Consumes 2% of 30-day budget in 1 hour
      - alert: ApiGatewayHighErrorRate
        expr: |
          (
            slo:sli_error:ratio_rate_5m{slo_name="requests-availability"} > (14.4 * 0.001)
            and
            slo:sli_error:ratio_rate_1h{slo_name="requests-availability"} > (14.4 * 0.001)
          )
          or
          (
            slo:sli_error:ratio_rate_30m{slo_name="requests-availability"} > (6 * 0.001)
            and
            slo:sli_error:ratio_rate_6h{slo_name="requests-availability"} > (6 * 0.001)
          )
        for: 2m
        labels:
          severity: critical
          routing: pagerduty
        annotations:
          summary: "CRITICAL: API Gateway burning error budget at >14x rate"
          description: |
            Current 1h burn rate: {{ $value | humanize }}x
            Budget remaining: {{ with query "slo:error_budget:ratio{slo_name='requests-availability'}" }}{{ . | first | value | humanizePercentage }}{{ end }}
          runbook: "https://runbooks.internal/api-gateway-errors"

      # TICKET: 3x burn in 6h AND 1x burn in 3d -> create ticket
      - alert: ApiGatewayErrorBudgetWarn
        expr: |
          (
            slo:sli_error:ratio_rate_6h{slo_name="requests-availability"} > (3 * 0.001)
            and
            slo:sli_error:ratio_rate_3d{slo_name="requests-availability"} > (1 * 0.001)
          )
        for: 10m
        labels:
          severity: warning
          routing: slack-platform
        annotations:
          summary: "WARNING: API Gateway error budget consumption elevated"

      # Recording rules for burn rate windows
      - record: slo:sli_error:ratio_rate_5m
        expr: |
          sum(rate(http_requests_total{service="api-gateway",code=~"5.."}[5m]))
          /
          sum(rate(http_requests_total{service="api-gateway"}[5m]))
        labels:
          slo_name: requests-availability
          slo_service: api-gateway

      - record: slo:sli_error:ratio_rate_1h
        expr: |
          sum(rate(http_requests_total{service="api-gateway",code=~"5.."}[1h]))
          /
          sum(rate(http_requests_total{service="api-gateway"}[1h]))
        labels:
          slo_name: requests-availability
          slo_service: api-gateway

      # Error budget remaining (0-1, where 1 = full budget)
      - record: slo:error_budget:ratio
        expr: |
          1 - (
            slo:sli_error:ratio_rate_30d{slo_name="requests-availability"}
            / 0.001
          )
        labels:
          slo_name: requests-availability
          slo_service: api-gateway
```

| Burn Rate | Short Window | Long Window | Budget Consumed | Action |
|-----------|-------------|-------------|-----------------|--------|
| 14.4x | 5 min | 1 hour | 2% in 1h | Page (PagerDuty) |
| 6x | 30 min | 6 hours | 5% in 6h | Page (PagerDuty) |
| 3x | 6 hours | 3 days | 10% in 3d | Ticket (Slack/Jira) |
| 1x | 3 days | 30 days | 100% in 30d | Dashboard review |

| SLO Target | Error Budget (30d) | Max Downtime | Good For |
|------------|-------------------|--------------|----------|
| 99.99% | 0.01% | 4.3 minutes | Payment processing |
| 99.95% | 0.05% | 21.6 minutes | Core API |
| 99.9% | 0.1% | 43.2 minutes | User-facing services |
| 99.5% | 0.5% | 3.6 hours | Internal tools |
| 99.0% | 1.0% | 7.2 hours | Batch processing |

Key patterns for SLO-based alerting:

1. **Multi-window burn rates** -- combine short and long windows (5m+1h, 30m+6h) to reduce false positives while catching real incidents
2. **Error budget tracking** -- express reliability as a budget that gets spent, enabling data-driven release decisions
3. **Tiered severity** -- critical burn rates page immediately, moderate rates create tickets, slow burns go to dashboards
4. **Sloth code generation** -- define SLOs declaratively and generate Prometheus recording rules and alerts automatically
5. **SLI selection** -- choose the right SLI type: availability for APIs, latency for user-facing, correctness for data pipelines
6. **Budget-based freezes** -- automatically halt deployments when error budget drops below 20% remaining
7. **Burn rate calculation** -- burn rate = (error rate in window) / (error budget fraction); a value of 1x means budget will exhaust exactly at window end'''
    ),
]
"""
