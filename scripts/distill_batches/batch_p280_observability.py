"""Observability patterns — structured logging, distributed tracing, metrics."""

PAIRS = [
    (
        "architecture/structured-logging",
        "Show structured logging patterns: JSON logs, correlation IDs, context propagation, and log aggregation.",
        '''Structured logging with context:

```python
import json
import time
import logging
import uuid
from contextvars import ContextVar
from typing import Any

# Request context propagation
request_id_var: ContextVar[str] = ContextVar("request_id", default="")
user_id_var: ContextVar[str] = ContextVar("user_id", default="")
trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


class StructuredFormatter(logging.Formatter):
    """JSON log formatter with automatic context injection."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": self._format_time(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            # Automatic context injection
            "request_id": request_id_var.get(""),
            "user_id": user_id_var.get(""),
            "trace_id": trace_id_var.get(""),
        }

        # Add extra fields from record
        if hasattr(record, "extra_data"):
            log_entry.update(record.extra_data)

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }

        return json.dumps(log_entry, default=str)

    def _format_time(self, record):
        return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))


class ContextLogger:
    """Logger with automatic context and structured extras."""

    def __init__(self, name: str):
        self.logger = logging.getLogger(name)

    def info(self, msg: str, **kwargs):
        self._log(logging.INFO, msg, **kwargs)

    def error(self, msg: str, **kwargs):
        self._log(logging.ERROR, msg, **kwargs)

    def warn(self, msg: str, **kwargs):
        self._log(logging.WARNING, msg, **kwargs)

    def _log(self, level: int, msg: str, **kwargs):
        record = self.logger.makeRecord(
            self.logger.name, level, "", 0, msg, (), None
        )
        record.extra_data = kwargs
        self.logger.handle(record)


# Middleware for request context
async def logging_middleware(request, call_next):
    req_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))

    token_req = request_id_var.set(req_id)
    token_trace = trace_id_var.set(trace_id)

    logger = ContextLogger("api")
    logger.info("request_start", method=request.method,
                path=str(request.url), client=request.client.host)

    start = time.perf_counter()
    try:
        response = await call_next(request)
        duration = (time.perf_counter() - start) * 1000
        logger.info("request_end", status=response.status_code,
                     duration_ms=round(duration, 2))
        response.headers["X-Request-ID"] = req_id
        return response
    except Exception as e:
        duration = (time.perf_counter() - start) * 1000
        logger.error("request_error", error=str(e),
                      duration_ms=round(duration, 2))
        raise
    finally:
        request_id_var.reset(token_req)
        trace_id_var.reset(token_trace)
```

Key patterns:
1. **JSON format** — machine-parseable logs for aggregation tools (ELK, Datadog, Loki)
2. **ContextVars** — automatic request_id/trace_id injection; no manual threading
3. **Correlation IDs** — trace a request across services; propagate via headers
4. **Structured extras** — key-value pairs alongside message; queryable in log aggregator
5. **Request lifecycle** — log start/end/error with duration; baseline observability'''
    ),
    (
        "architecture/distributed-tracing",
        "Show distributed tracing: span creation, context propagation, trace visualization, and OpenTelemetry integration.",
        '''Distributed tracing with OpenTelemetry:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.b3 import B3MultiFormat
from functools import wraps
import time


def setup_tracing(service_name: str, otlp_endpoint: str):
    """Initialize OpenTelemetry tracing."""
    provider = TracerProvider(
        resource=trace.get_tracer_provider().resource.merge(
            {"service.name": service_name, "deployment.environment": "production"}
        )
    )
    exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    set_global_textmap(B3MultiFormat())


tracer = trace.get_tracer("my-service")


def traced(name: str = None, attributes: dict = None):
    """Decorator to trace function execution."""
    def decorator(fn):
        span_name = name or f"{fn.__module__}.{fn.__name__}"
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                try:
                    result = await fn(*args, **kwargs)
                    span.set_status(trace.StatusCode.OK)
                    return result
                except Exception as e:
                    span.set_status(trace.StatusCode.ERROR, str(e))
                    span.record_exception(e)
                    raise
        return wrapper
    return decorator


class TracedService:
    """Service with manual span management."""

    @traced("order.process")
    async def process_order(self, order_id: str):
        span = trace.get_current_span()
        span.set_attribute("order.id", order_id)

        # Child span for validation
        with tracer.start_as_current_span("order.validate") as child:
            await self.validate(order_id)
            child.set_attribute("validation.passed", True)

        # Child span for payment
        with tracer.start_as_current_span("order.charge") as child:
            result = await self.charge_payment(order_id)
            child.set_attribute("payment.amount", result["amount"])
            child.add_event("payment_processed", {"transaction_id": result["tx_id"]})

        return {"status": "completed"}
```

Key patterns:
1. **Automatic instrumentation** — FastAPI, httpx, SQLAlchemy instrumented automatically
2. **Context propagation** — trace context flows via HTTP headers (B3, W3C traceparent)
3. **Span hierarchy** — parent → child spans show call tree; identify slow operations
4. **Span attributes** — add business context (order_id, amount) for debugging
5. **OTLP export** — send traces to Jaeger, Tempo, or any OTLP-compatible backend'''
    ),
]
"""
