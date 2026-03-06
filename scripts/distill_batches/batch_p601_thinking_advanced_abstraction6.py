"""Phase 2G: Advanced Reasoning — Abstraction Laddering (Part 6/6)"""

PAIRS = [
    (
        "thinking/abstraction-logging-to-observability-pillar",
        "We have logging in some places, metrics in others, and recently added tracing. Each uses a different library, different format, different storage. How do I unify our observability?",
        r'''<think>
Let me climb the abstraction ladder from scattered observability tools to a unified strategy.

**Concrete level — the mess:**
- Logging: Python's logging module → text files, some structured JSON
- Metrics: StatsD in some services, Prometheus in others
- Tracing: recently added OpenTelemetry in one service

Each was added ad-hoc to solve an immediate problem.

**Pattern level — what these have in common:**
All three answer questions about system behavior:
- Logs: "What happened?" (events with context)
- Metrics: "How much/how fast?" (numerical measurements over time)
- Traces: "What path did a request take?" (cross-service execution flow)

They're the three PILLARS of observability, and they should be correlated.

**Principle level — unified observability:**
A single request generates all three signal types. They should be connected:
- A log entry should have the trace ID
- A metric spike should link to example traces
- A trace should contain structured log events

The unifying concept: CONTEXT PROPAGATION. A request context (trace_id, span_id, user_id, request_id) flows through all three pillars, allowing you to jump between them.

**Policy level:**
Every service emits logs, metrics, and traces with consistent context. OpenTelemetry is the standard that unifies all three.
</think>

Your three observability tools are actually three views of the SAME system behavior. The fix is **context propagation** — a shared request context that connects logs, metrics, and traces.

## The Abstraction Ladder

```
POLICY:    Every request emits correlated logs, metrics, and traces through one SDK
              ↑
PRINCIPLE: Context propagation — trace_id connects all three pillars
              ↑
PATTERN:   Logs answer WHAT, metrics answer HOW MUCH, traces answer WHERE
              ↑
CONCRETE:  3 separate tools, 3 formats, 3 storage systems
```

## Before: Disconnected Pillars

```
Incident happens. You have:

LOGS:     "Payment failed for order 12345" at 14:32:05
METRICS:  payment_errors spike at 14:32 (but which requests?)
TRACES:   ... you can't find the trace because there's no correlation

You grep through 3 different systems trying to piece together what happened.
```

## After: Connected Pillars

```
Incident happens. You have:

TRACE:    trace_id=abc123 → shows request flow across services
          ├── api-gateway (2ms)
          ├── order-service (15ms)
          └── payment-service (FAILED after 5000ms timeout)

LOGS:     filter by trace_id=abc123 → shows exact error:
          "Stripe API timeout: connection refused"

METRICS:  payment_service_latency_p99 spiked at 14:32
          → click through to example traces → abc123

All three are connected by trace_id. 5 minutes to root cause, not 2 hours.
```

## Implementation: OpenTelemetry Unifies Everything

```python
# One SDK for all three pillars
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource
import logging
import json

# Setup: one resource identity for the service
resource = Resource.create({"service.name": "order-service", "service.version": "2.4.1"})

# Tracer
tracer = trace.get_tracer("order-service")

# Meter
meter = metrics.get_meter("order-service")
order_counter = meter.create_counter("orders.created", description="Orders created")
order_latency = meter.create_histogram("orders.latency_ms", description="Order processing time")

# Logger with trace context
class TraceContextFilter(logging.Filter):
    def filter(self, record):
        span = trace.get_current_span()
        ctx = span.get_span_context()
        record.trace_id = format(ctx.trace_id, '032x') if ctx.trace_id else ""
        record.span_id = format(ctx.span_id, '016x') if ctx.span_id else ""
        return True

logger = logging.getLogger("order-service")
logger.addFilter(TraceContextFilter())

# JSON formatter includes trace context in every log line
class JSONFormatter(logging.Formatter):
    def format(self, record):
        return json.dumps({
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "trace_id": getattr(record, 'trace_id', ''),
            "span_id": getattr(record, 'span_id', ''),
            "service": "order-service",
        })


# --- Usage: all three pillars from one request ---

@app.post("/orders")
async def create_order(order_data: dict):
    with tracer.start_as_current_span("create_order") as span:
        # TRACE: span captures timing and metadata
        span.set_attribute("order.customer_id", order_data["customer_id"])

        # LOG: includes trace_id automatically
        logger.info("Creating order for customer %s", order_data["customer_id"])

        try:
            order = await process_order(order_data)

            # METRICS: count and latency
            order_counter.add(1, {"status": "success"})
            span.set_attribute("order.id", order.id)

            logger.info("Order %s created successfully", order.id)
            return order

        except PaymentError as e:
            order_counter.add(1, {"status": "payment_failed"})
            span.set_status(trace.StatusCode.ERROR, str(e))
            logger.error("Payment failed: %s", e)
            raise
```

## The Correlation in Practice

```json
// LOG ENTRY (automatically includes trace context):
{
  "timestamp": "2024-01-15T14:32:05Z",
  "level": "ERROR",
  "message": "Payment failed: Stripe timeout",
  "trace_id": "abc123def456...",
  "span_id": "789xyz...",
  "service": "order-service"
}

// In your observability platform (Grafana, Datadog, etc.):
// 1. See error in logs → click trace_id → see full trace
// 2. See metric spike → click "example traces" → see what's slow
// 3. See slow trace → click "logs" tab → see error details
```

## Migration Plan (Incremental)

```
Week 1: Add OpenTelemetry SDK to ONE service
  - Add trace context to all log lines
  - Add basic request tracing

Week 2: Add metrics via OpenTelemetry
  - Replace StatsD/custom metrics with OTel meters
  - Same data, unified SDK

Week 3-4: Roll out to remaining services
  - One service at a time
  - Existing logging continues working (just adds trace context)

Week 5: Connect in your observability platform
  - Grafana: Loki (logs) + Tempo (traces) + Prometheus (metrics)
  - Or: Datadog ingests all three from OTel exporters
```

The insight: logs, metrics, and traces aren't separate concerns — they're three views of the same system behavior. OpenTelemetry unifies them through context propagation, turning scattered signals into connected observability.'''
    ),
    (
        "thinking/abstraction-feature-development-to-capability-building",
        "Every time product asks for a new feature, we build it from scratch. We've built user notification systems three times for different features — email for billing, push for social, in-app for onboarding. Each is separate. How do I stop this pattern?",
        r'''<think>
Let me climb the abstraction ladder from feature-by-feature development to capability building.

**Concrete level — what's happening:**
- Feature A (billing) needed email notifications → built email sender
- Feature B (social) needed push notifications → built push sender
- Feature C (onboarding) needed in-app notifications → built in-app sender

Each is a separate implementation, separate config, separate testing.

**Pattern level — what's repeated:**
All three do the same thing: deliver a message to a user through a channel. The differences are:
- Channel (email, push, in-app)
- Template (billing vs social vs onboarding)
- Trigger (event-based vs scheduled)
- Preferences (user opt-in/out per channel)

**Principle level — capability vs feature:**
The team is building FEATURES when they should be building CAPABILITIES.
- Feature: "send billing email" (single-use, tightly coupled)
- Capability: "notify a user" (reusable, decoupled)

A capability is a building block that multiple features compose.

**Policy level — platform thinking:**
Build capabilities as internal platform services. When product asks for "notifications for feature X," the answer is "which channels and what template?" not "let me build a notification system."
</think>

You're building **features** when you should be building **capabilities**. Here's the distinction:

## The Abstraction Ladder

```
POLICY:    Build capabilities once, compose features from them
              ↑
PRINCIPLE: A capability is a reusable building block with a stable interface
              ↑
PATTERN:   Notifications, payments, search — these are capabilities, not features
              ↑
CONCRETE:  3 separate notification systems for 3 different features
```

## Feature vs Capability

```
FEATURE thinking (what you're doing):
  Product: "Billing needs email alerts"
  Dev: builds billing email sender
  Product: "Social needs push notifications"
  Dev: builds social push sender (from scratch)
  Product: "Onboarding needs in-app tips"
  Dev: builds onboarding in-app system (from scratch)
  → 3 implementations of "send message to user"

CAPABILITY thinking (what you should do):
  Dev: builds notification service (once)
  Product: "Billing needs email alerts"
  Dev: adds billing template, configures email channel → 1 day
  Product: "Social needs push notifications"
  Dev: adds social template, configures push channel → 1 day
  Product: "Onboarding needs in-app tips"
  Dev: adds onboarding template, configures in-app channel → 1 day
```

## The Notification Capability (Built Once)

```python
from dataclasses import dataclass
from enum import Enum
from typing import Any

class Channel(Enum):
    EMAIL = "email"
    PUSH = "push"
    IN_APP = "in_app"
    SMS = "sms"

@dataclass
class Notification:
    user_id: int
    template: str        # "billing.invoice_due", "social.new_follower"
    channel: Channel
    data: dict[str, Any]  # Template variables
    priority: str = "normal"

class NotificationService:
    """The capability: send any notification through any channel."""

    def __init__(self):
        self.channels = {
            Channel.EMAIL: EmailChannel(),
            Channel.PUSH: PushChannel(),
            Channel.IN_APP: InAppChannel(),
        }
        self.templates = TemplateRegistry()

    async def send(self, notification: Notification):
        # Check user preferences
        if not await self.user_wants(notification.user_id, notification.channel,
                                     notification.template):
            return

        # Render template
        content = self.templates.render(notification.template, notification.data)

        # Send through channel
        channel = self.channels[notification.channel]
        await channel.deliver(notification.user_id, content)

    async def send_multi(self, user_id: int, template: str, data: dict,
                         channels: list[Channel] | None = None):
        """Send same notification through multiple channels."""
        if channels is None:
            channels = await self.preferred_channels(user_id, template)
        for ch in channels:
            await self.send(Notification(
                user_id=user_id, template=template,
                channel=ch, data=data
            ))


# --- Features just USE the capability ---

# Billing feature: 2 lines
async def on_invoice_due(invoice):
    await notifications.send_multi(
        user_id=invoice.user_id,
        template="billing.invoice_due",
        data={"amount": invoice.total, "due_date": invoice.due_date},
        channels=[Channel.EMAIL],
    )

# Social feature: 2 lines
async def on_new_follower(user_id, follower):
    await notifications.send_multi(
        user_id=user_id,
        template="social.new_follower",
        data={"follower_name": follower.name},
        channels=[Channel.PUSH, Channel.IN_APP],
    )

# Onboarding feature: 2 lines
async def on_user_signup(user):
    await notifications.send_multi(
        user_id=user.id,
        template="onboarding.welcome",
        data={"name": user.name},
        channels=[Channel.IN_APP, Channel.EMAIL],
    )
```

## Identifying Capabilities in Your Codebase

Look for code that's been built 2+ times:

| Pattern You See | Capability to Build |
|-----------------|-------------------|
| 3 notification systems | **Notification Service** |
| File upload in 4 features | **File Storage Service** |
| Search in products, users, orders | **Search Service** |
| PDF generation in invoices, reports, exports | **Document Generation Service** |
| Permission checks in 20 endpoints | **Authorization Service** |
| Audit logging scattered everywhere | **Audit Trail Service** |

## The Rule of Three

```
First time: Build it inline (you don't know the pattern yet)
Second time: Notice the pattern, but it's OK to duplicate
Third time: Extract the capability — now you know the interface

Don't abstract prematurely. Wait until you've built something
2-3 times and understand the variations before extracting.
```

The shift from feature thinking to capability thinking is the difference between a codebase that gets harder to work with over time and one that gets easier. Each capability you build makes the NEXT feature cheaper.'''
    ),
    (
        "thinking/abstraction-config-flags-to-runtime-controls",
        "We have feature flags, A/B tests, config overrides, maintenance mode toggles, and gradual rollouts all implemented with different systems. Some are in config files, some in database, some in environment variables. How do I unify this?",
        r'''<think>
Let me climb the abstraction ladder.

**Concrete level — what they have:**
- Feature flags: database table checked at runtime
- A/B tests: third-party service (LaunchDarkly/Optimizely)
- Config overrides: environment variables
- Maintenance mode: boolean in config file
- Gradual rollouts: custom code with percentage checks

**Pattern level — what's common:**
All of these answer the same question: "For this context (user, request, time), what value should this control have?"

They differ in:
- Targeting (all users, percentage, specific users, specific conditions)
- Value type (boolean, string, number, JSON)
- Lifecycle (permanent config, temporary experiment, temporary flag)
- Change mechanism (deploy, database update, API call)

**Principle level — runtime controls:**
All five are RUNTIME CONTROLS — values that modify system behavior without code deployment. The abstraction is:

```
control(name, context) → value
```

Where context might include: user_id, environment, time, request properties.

**Policy level:**
A unified runtime control plane where all controls (flags, experiments, configs, toggles) are managed through one interface with consistent targeting, auditing, and lifecycle management.
</think>

All five systems are doing the same thing: **returning a value based on context without a deploy**. Unify them as a Runtime Control Plane.

## The Abstraction Ladder

```
POLICY:    One control plane for all runtime behavior modification
              ↑
PRINCIPLE: control(name, context) → value — same interface for all control types
              ↑
PATTERN:   Feature flags, A/B tests, configs — all are targeted value resolution
              ↑
CONCRETE:  5 different systems for 5 types of controls
```

## Unified Implementation

```python
from dataclasses import dataclass, field
from typing import Any
from enum import Enum
import hashlib
import json

class ControlType(Enum):
    FEATURE_FLAG = "feature_flag"     # Boolean: on/off
    EXPERIMENT = "experiment"          # String: variant A/B/C
    CONFIG = "config"                  # Any: runtime config value
    ROLLOUT = "rollout"               # Boolean: percentage-based
    MAINTENANCE = "maintenance"        # Boolean: system-wide toggle

@dataclass
class EvaluationContext:
    """Who/what is requesting this control value."""
    user_id: str | None = None
    environment: str = "production"
    ip_address: str | None = None
    user_agent: str | None = None
    properties: dict[str, Any] = field(default_factory=dict)

@dataclass
class Control:
    name: str
    control_type: ControlType
    default_value: Any
    # Targeting rules (evaluated in order, first match wins)
    rules: list[dict] = field(default_factory=list)
    # Rollout percentage (for ROLLOUT type)
    rollout_percentage: int = 0
    # Experiment variants (for EXPERIMENT type)
    variants: dict[str, int] = field(default_factory=dict)  # variant → weight
    # Metadata
    description: str = ""
    owner: str = ""
    expires_at: str | None = None

class ControlPlane:
    """Unified runtime control evaluation."""

    def __init__(self, storage):
        self.storage = storage  # Database, Redis, or in-memory
        self._cache = {}

    def evaluate(self, name: str, context: EvaluationContext) -> Any:
        """Evaluate a control for a given context. One interface for everything."""
        control = self._get_control(name)
        if not control:
            return None

        # Check targeting rules first
        for rule in control.rules:
            if self._matches_rule(rule, context):
                return rule["value"]

        # Type-specific evaluation
        if control.control_type == ControlType.ROLLOUT:
            return self._evaluate_rollout(control, context)
        elif control.control_type == ControlType.EXPERIMENT:
            return self._evaluate_experiment(control, context)
        else:
            return control.default_value

    def _evaluate_rollout(self, control: Control, ctx: EvaluationContext) -> bool:
        """Deterministic percentage-based rollout."""
        if not ctx.user_id:
            return control.default_value
        hash_val = int(hashlib.md5(
            f"{control.name}:{ctx.user_id}".encode()
        ).hexdigest(), 16) % 100
        return hash_val < control.rollout_percentage

    def _evaluate_experiment(self, control: Control, ctx: EvaluationContext) -> str:
        """Deterministic A/B variant assignment."""
        if not ctx.user_id:
            return control.default_value
        hash_val = int(hashlib.md5(
            f"{control.name}:{ctx.user_id}".encode()
        ).hexdigest(), 16) % 100
        cumulative = 0
        for variant, weight in control.variants.items():
            cumulative += weight
            if hash_val < cumulative:
                return variant
        return control.default_value


# --- Usage: ONE interface for everything ---

controls = ControlPlane(storage=database)
ctx = EvaluationContext(user_id="user_123", environment="production")

# Feature flag (was: database boolean lookup)
if controls.evaluate("new_dashboard", ctx):
    show_new_dashboard()

# A/B test (was: third-party SDK call)
variant = controls.evaluate("checkout_flow_experiment", ctx)
# Returns "control", "variant_a", or "variant_b"

# Config override (was: environment variable)
max_upload_size = controls.evaluate("max_upload_mb", ctx)
# Returns 100 for most users, 500 for enterprise tier

# Maintenance mode (was: config file boolean)
if controls.evaluate("maintenance_mode", ctx):
    return maintenance_page()

# Gradual rollout (was: custom percentage code)
if controls.evaluate("new_payment_flow", ctx):
    use_new_payment_flow()
```

## Admin Interface

```python
# All controls managed through one API
@admin_app.post("/controls")
def create_control(data: dict):
    control = Control(
        name="new_search_algorithm",
        control_type=ControlType.ROLLOUT,
        default_value=False,
        rollout_percentage=10,  # Start with 10% of users
        rules=[
            # Override: always on for internal users
            {"condition": {"property": "email", "endswith": "@company.com"},
             "value": True},
            # Override: always off for specific customer
            {"condition": {"user_id": "customer_456"},
             "value": False},
        ],
        owner="search-team",
        expires_at="2024-06-01",
        description="New search ranking algorithm",
    )
    storage.save(control)
```

## What You Consolidated

| Before (5 systems) | After (1 control plane) |
|---|---|
| Feature flags in database | `ControlType.FEATURE_FLAG` |
| A/B tests in LaunchDarkly | `ControlType.EXPERIMENT` |
| Config in env vars | `ControlType.CONFIG` |
| Maintenance toggle in config file | `ControlType.MAINTENANCE` |
| Custom rollout code | `ControlType.ROLLOUT` |

One system, one admin interface, one audit log, one SDK. Adding any new type of runtime control is just a new `ControlType` enum value.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
