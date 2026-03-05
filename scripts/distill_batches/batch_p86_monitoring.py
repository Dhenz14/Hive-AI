"""Observability — ELK stack, distributed tracing, and alerting patterns."""

PAIRS = [
    (
        "devops/elk-stack",
        "Show ELK stack patterns: Elasticsearch queries, Logstash pipelines, Kibana dashboards, and Filebeat configuration.",
        '''ELK stack patterns:

```yaml
# --- Filebeat configuration (log shipper) ---
# filebeat.yml

filebeat.inputs:
  - type: log
    enabled: true
    paths:
      - /var/log/app/*.log
    json.keys_under_root: true
    json.add_error_key: true
    fields:
      service: myapp
      environment: production
    multiline:
      pattern: '^\\{'
      negate: true
      match: after

  - type: container
    paths:
      - /var/lib/docker/containers/*/*.log
    processors:
      - add_docker_metadata: ~
      - add_kubernetes_metadata: ~

output.elasticsearch:
  hosts: ["elasticsearch:9200"]
  index: "logs-%{[fields.service]}-%{+yyyy.MM.dd}"
  pipeline: app-pipeline

setup.ilm.enabled: true
setup.ilm.rollover_alias: "logs"
setup.ilm.pattern: "{now/d}-000001"


# --- Logstash pipeline ---
# logstash/pipeline/app.conf

input {
  beats {
    port => 5044
  }
}

filter {
  # Parse JSON logs
  if [message] =~ /^\{/ {
    json {
      source => "message"
    }
  }

  # Parse timestamps
  date {
    match => ["timestamp", "ISO8601", "yyyy-MM-dd HH:mm:ss"]
    target => "@timestamp"
  }

  # Extract fields from log message
  grok {
    match => {
      "message" => "%{IPORHOST:client_ip} %{WORD:method} %{URIPATH:path} %{NUMBER:status:int} %{NUMBER:duration_ms:float}"
    }
    tag_on_failure => ["_grokparsefailure"]
  }

  # GeoIP lookup
  if [client_ip] {
    geoip {
      source => "client_ip"
      target => "geo"
    }
  }

  # Drop health check noise
  if [path] == "/health" or [path] == "/ready" {
    drop {}
  }

  # Add computed fields
  mutate {
    add_field => {
      "[@metadata][index]" => "logs-%{[service]}-%{+YYYY.MM.dd}"
    }
    remove_field => ["agent", "ecs", "host"]
  }
}

output {
  elasticsearch {
    hosts => ["elasticsearch:9200"]
    index => "%{[@metadata][index]}"
  }
}
```

```json
// --- Elasticsearch queries ---

// Search with filters
// POST /logs-myapp-*/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "level": "ERROR" } },
        { "range": { "@timestamp": { "gte": "now-1h" } } }
      ],
      "filter": [
        { "term": { "service": "myapp" } }
      ],
      "must_not": [
        { "match": { "message": "health check" } }
      ]
    }
  },
  "sort": [{ "@timestamp": "desc" }],
  "size": 50,
  "aggs": {
    "errors_per_minute": {
      "date_histogram": {
        "field": "@timestamp",
        "fixed_interval": "1m"
      }
    },
    "top_error_messages": {
      "terms": {
        "field": "message.keyword",
        "size": 10
      }
    }
  }
}

// --- Index Lifecycle Management ---
// PUT _ilm/policy/logs-policy
{
  "policy": {
    "phases": {
      "hot": {
        "actions": {
          "rollover": {
            "max_size": "50gb",
            "max_age": "1d"
          }
        }
      },
      "warm": {
        "min_age": "7d",
        "actions": {
          "shrink": { "number_of_shards": 1 },
          "forcemerge": { "max_num_segments": 1 }
        }
      },
      "delete": {
        "min_age": "30d",
        "actions": { "delete": {} }
      }
    }
  }
}
```

ELK patterns:
1. **Filebeat → Logstash → ES** — ship, parse, index pipeline
2. **JSON logging** — structured logs parse directly, no grok needed
3. **ILM policies** — auto-rollover, warm tier, delete old indices
4. **`bool` query** — combine must/filter/must_not for precise searches
5. **Date histogram aggs** — error rate over time for dashboards'''
    ),
    (
        "devops/distributed-tracing",
        "Show distributed tracing patterns: OpenTelemetry instrumentation, span context, and trace correlation.",
        '''Distributed tracing with OpenTelemetry:

```python
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.propagate import inject, extract
from opentelemetry.trace import StatusCode
import logging

logger = logging.getLogger(__name__)


# --- Setup ---

def setup_tracing(service_name: str, otlp_endpoint: str = "localhost:4317"):
    """Initialize OpenTelemetry tracing."""
    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.2.0",
        "deployment.environment": "production",
    })

    provider = TracerProvider(resource=resource)
    processor = BatchSpanProcessor(
        OTLPSpanExporter(endpoint=otlp_endpoint),
        max_queue_size=2048,
        max_export_batch_size=512,
    )
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    # Auto-instrument libraries
    FastAPIInstrumentor.instrument()
    HTTPXClientInstrumentor.instrument()
    SQLAlchemyInstrumentor().instrument()

    return provider


# --- Manual instrumentation ---

tracer = trace.get_tracer(__name__)


async def process_order(order_id: str) -> dict:
    """Example of manual span creation."""

    # Create a span for the overall operation
    with tracer.start_as_current_span(
        "process_order",
        attributes={
            "order.id": order_id,
            "order.source": "api",
        },
    ) as span:
        try:
            # Child span for validation
            with tracer.start_as_current_span("validate_order") as validate_span:
                order = await validate_order(order_id)
                validate_span.set_attribute("order.items_count", len(order["items"]))

            # Child span for payment
            with tracer.start_as_current_span("charge_payment") as payment_span:
                payment = await charge_payment(order)
                payment_span.set_attribute("payment.method", payment["method"])
                payment_span.set_attribute("payment.amount", payment["amount"])

            # Child span for fulfillment
            with tracer.start_as_current_span("create_shipment"):
                shipment = await create_shipment(order)

            span.set_attribute("order.status", "completed")
            return {"order": order, "payment": payment, "shipment": shipment}

        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            span.record_exception(e)
            raise


# --- Context propagation (cross-service) ---

import httpx

async def call_downstream_service(order: dict):
    """Propagate trace context to downstream service."""
    headers = {}
    inject(headers)  # Injects traceparent header

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://shipping-service/api/shipments",
            json=order,
            headers=headers,  # Trace context propagated
        )
        return response.json()


# --- Span events (lightweight annotations) ---

async def retry_operation(fn, max_retries: int = 3):
    span = trace.get_current_span()

    for attempt in range(max_retries):
        try:
            return await fn()
        except Exception as e:
            span.add_event(
                "retry_attempt",
                attributes={
                    "attempt": attempt + 1,
                    "error": str(e),
                },
            )
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)


# --- Trace-log correlation ---

class TraceLogFormatter(logging.Formatter):
    """Add trace/span IDs to log records."""

    def format(self, record):
        span = trace.get_current_span()
        ctx = span.get_span_context()

        if ctx.is_valid:
            record.trace_id = format(ctx.trace_id, '032x')
            record.span_id = format(ctx.span_id, '016x')
        else:
            record.trace_id = "0" * 32
            record.span_id = "0" * 16

        return super().format(record)

# Format: "%(asctime)s [%(trace_id)s/%(span_id)s] %(levelname)s %(message)s"
```

Distributed tracing patterns:
1. **Auto-instrumentation** — instrument FastAPI, httpx, SQLAlchemy automatically
2. **Nested spans** — parent/child relationships show call hierarchy
3. **`inject(headers)`** — propagate trace context across HTTP boundaries
4. **`record_exception()`** — attach error details to spans for debugging
5. **Trace-log correlation** — embed trace_id in logs to connect logs to traces'''
    ),
    (
        "devops/alerting-patterns",
        "Show alerting patterns: Prometheus alerting rules, PagerDuty integration, and runbook automation.",
        '''Alerting and incident response patterns:

```yaml
# --- Prometheus alerting rules ---
# alerts/application.yml

groups:
  - name: application
    interval: 30s
    rules:
      # High error rate
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m]))
          /
          sum(rate(http_requests_total[5m]))
          > 0.05
        for: 5m
        labels:
          severity: critical
          team: backend
        annotations:
          summary: "High error rate: {{ $value | humanizePercentage }}"
          description: "Error rate is {{ $value | humanizePercentage }} (>5%) for 5 minutes"
          runbook: "https://wiki.example.com/runbooks/high-error-rate"
          dashboard: "https://grafana.example.com/d/app-overview"

      # Latency SLO breach
      - alert: LatencySLOBreach
        expr: |
          histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[10m]))
          > 2.0
        for: 10m
        labels:
          severity: warning
          team: backend
        annotations:
          summary: "P99 latency above 2s: {{ $value | humanizeDuration }}"
          runbook: "https://wiki.example.com/runbooks/high-latency"

      # Pod restarts
      - alert: PodCrashLooping
        expr: |
          rate(kube_pod_container_status_restarts_total[15m]) * 60 * 15 > 3
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Pod {{ $labels.pod }} restarting frequently"

      # Disk space
      - alert: DiskSpaceLow
        expr: |
          (node_filesystem_avail_bytes / node_filesystem_size_bytes) < 0.1
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "Disk space below 10% on {{ $labels.instance }}"

      # Error budget burn rate (SLO)
      - alert: ErrorBudgetBurnRate
        expr: |
          (
            1 - (
              sum(rate(http_requests_total{status!~"5.."}[1h]))
              /
              sum(rate(http_requests_total[1h]))
            )
          ) / (1 - 0.999) > 14.4
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Error budget burning 14.4x faster than allowed"
          description: "At this rate, monthly error budget exhausted in 2 days"


# --- Alertmanager configuration ---
# alertmanager.yml

global:
  resolve_timeout: 5m
  slack_api_url: 'https://hooks.slack.com/services/xxx'

route:
  receiver: 'default'
  group_by: ['alertname', 'team']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  routes:
    - receiver: 'pagerduty-critical'
      match:
        severity: critical
      continue: true  # Also send to Slack

    - receiver: 'slack-warnings'
      match:
        severity: warning

receivers:
  - name: 'default'
    slack_configs:
      - channel: '#alerts'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.summary }}{{ end }}'

  - name: 'pagerduty-critical'
    pagerduty_configs:
      - service_key: '<pagerduty-integration-key>'
        description: '{{ .GroupLabels.alertname }}: {{ .CommonAnnotations.summary }}'

  - name: 'slack-warnings'
    slack_configs:
      - channel: '#alerts-warning'
        send_resolved: true

inhibit_rules:
  # Don't fire warning if critical already firing
  - source_match:
      severity: critical
    target_match:
      severity: warning
    equal: ['alertname']
```

```python
# --- Runbook automation ---

class RunbookAction:
    """Automated first-response actions for common alerts."""

    async def handle_high_error_rate(self, alert: dict):
        """Runbook: High error rate response."""
        steps = [
            ("Check recent deployments", self._check_deployments),
            ("Check dependency health", self._check_dependencies),
            ("Check database connections", self._check_db_pool),
            ("Capture thread dump", self._capture_diagnostics),
        ]

        results = []
        for name, action in steps:
            try:
                result = await action()
                results.append(f"✓ {name}: {result}")
            except Exception as e:
                results.append(f"✗ {name}: {e}")

        # Post findings to incident channel
        await self._post_to_slack(
            channel="#incidents",
            text=f"*Auto-diagnosis for {alert['alertname']}*\\n"
                 + "\\n".join(results),
        )
```

Alerting patterns:
1. **`for: 5m`** — require sustained condition before firing (avoid flapping)
2. **Error budget burn rate** — alert based on SLO consumption speed
3. **`group_by`** — aggregate related alerts into single notification
4. **`inhibit_rules`** — suppress warnings when critical already firing
5. **Runbook links** — every alert annotation includes runbook URL'''
    ),
]
