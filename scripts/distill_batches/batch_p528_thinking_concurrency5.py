"""Phase 1G: Foundation Thinking — Concurrency & Distributed Systems (Part 5/5)
Observability, monitoring, tracing in distributed systems, failure modes."""

PAIRS = [
    (
        "thinking/distributed-observability",
        "Our microservice architecture has 8 services. When a request fails, we can't figure out which service caused the problem. Logs are scattered across 8 different log streams. How do we debug distributed systems?",
        r'''<think>
The three pillars of observability:
1. Structured logging (with correlation IDs)
2. Distributed tracing (follow a request across services)
3. Metrics (aggregate performance/error data)

For the immediate problem of "which service caused the failure," distributed tracing with correlation IDs is the answer.
</think>

## The Three Pillars of Observability

### 1. Correlation IDs (Quick Win)

```python
# Middleware: attach a trace ID to every request
import uuid

class CorrelationMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, request, call_next):
        # Use incoming trace ID or create new one
        trace_id = request.headers.get('X-Trace-ID', str(uuid.uuid4()))
        request.state.trace_id = trace_id

        # Add to all log messages
        with structlog.contextvars.bound_contextvars(trace_id=trace_id):
            response = await call_next(request)
            response.headers['X-Trace-ID'] = trace_id
            return response

# When calling other services, pass the trace ID
async def call_inventory_service(product_id, trace_id):
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f'http://inventory/api/stock/{product_id}',
            headers={'X-Trace-ID': trace_id},
        )
        return response.json()
```

Now search ANY log system for `trace_id=abc-123` and see the entire request flow across all 8 services.

### 2. Distributed Tracing (OpenTelemetry)

```python
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

# Auto-instrument everything
FastAPIInstrumentor.instrument_app(app)
HTTPXClientInstrumentor().instrument()
SQLAlchemyInstrumentor().instrument(engine=db_engine)

# Custom spans for business logic
tracer = trace.get_tracer(__name__)

async def process_order(order_data):
    with tracer.start_as_current_span("process_order") as span:
        span.set_attribute("order.user_id", order_data['user_id'])
        span.set_attribute("order.item_count", len(order_data['items']))

        with tracer.start_as_current_span("validate_inventory"):
            await check_inventory(order_data['items'])

        with tracer.start_as_current_span("process_payment"):
            payment = await charge_customer(order_data)
            span.set_attribute("payment.id", payment.id)
```

Visualization in Jaeger/Zipkin:
```
[API Gateway] ──200ms──
  └─[Order Service] ──150ms──
      ├─[Inventory Service] ──30ms──
      │   └─[DB Query] ──5ms──
      ├─[Payment Service] ──80ms── ← Slow!
      │   └─[Stripe API] ──75ms──
      └─[Notification Service] ──20ms──
```

### 3. Metrics (Prometheus)

```python
from prometheus_client import Counter, Histogram

request_count = Counter(
    'http_requests_total',
    'Total requests',
    ['method', 'endpoint', 'status'],
)
request_latency = Histogram(
    'http_request_duration_seconds',
    'Request latency',
    ['method', 'endpoint'],
)
error_count = Counter(
    'service_errors_total',
    'Total errors by service and type',
    ['service', 'error_type'],
)

@app.middleware("http")
async def metrics_middleware(request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = time.time() - start

    request_count.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code,
    ).inc()
    request_latency.labels(
        method=request.method,
        endpoint=request.url.path,
    ).observe(duration)

    return response
```

## Debugging Workflow

```
1. Alert fires: "Order error rate > 5%"
2. Check metrics dashboard → Order Service error rate spiked at 14:30
3. Filter logs by time range → trace_id=abc-123 shows Payment Service timeout
4. Open trace in Jaeger → Payment Service → Stripe API taking 30s
5. Root cause: Stripe API degradation
6. Fix: Circuit breaker on Payment Service, queue orders during outage
```'''
    ),
    (
        "thinking/distributed-failure-modes",
        "What are all the ways a distributed system can fail? I want a mental checklist for designing resilient systems.",
        r'''<think>
Failure modes in distributed systems — let me categorize them:

1. Network failures (partition, latency, packet loss)
2. Node failures (crash, slow, Byzantine)
3. Timing failures (clock skew, timeout misconfiguration)
4. Data failures (corruption, inconsistency, loss)
5. Cascade failures (one failure causing others)
6. Human failures (misconfiguration, bad deploys)

For each, I should give the failure mode, how it manifests, and the mitigation.
</think>

## Distributed System Failure Checklist

### Network Failures

| Failure | Symptom | Mitigation |
|---------|---------|------------|
| Network partition | Service A can't reach B but both are up | Circuit breaker, retry with backoff |
| Asymmetric partition | A→B works, B→A doesn't | Health checks in both directions |
| DNS failure | Service discovery breaks | Cache DNS, use IP fallbacks |
| Network latency spike | Requests succeed but take 10x longer | Timeouts, deadline propagation |
| Packet loss | Intermittent failures, retries sometimes work | Idempotent APIs, retry with jitter |

### Node Failures

| Failure | Symptom | Mitigation |
|---------|---------|------------|
| Crash (fail-stop) | Process dies, connections reset | Health checks, auto-restart, redundancy |
| Slow node (gray failure) | Responds but very slowly | Timeout + circuit breaker |
| Memory leak | Gradual degradation over days | Memory limits, auto-restart on OOM |
| Disk full | Writes fail, logs stop | Monitoring, log rotation, alerts at 80% |
| CPU saturation | All requests slow | Auto-scaling, rate limiting |

### Data Failures

| Failure | Symptom | Mitigation |
|---------|---------|------------|
| Stale cache | Users see outdated data | TTL, cache invalidation events |
| Split brain | Two leaders, conflicting writes | Quorum, fencing tokens |
| Message duplication | Event processed twice | Idempotent consumers |
| Message loss | Events disappear | Persistent queues, acknowledgment |
| Clock skew | Timestamps out of order across servers | NTP, logical clocks, Lamport timestamps |

### Cascade Failures

| Failure | Symptom | Mitigation |
|---------|---------|------------|
| Retry storm | Failed service recovers but immediately overwhelmed by retries | Exponential backoff, jitter, circuit breaker |
| Connection pool exhaustion | Slow dependency causes all connections to wait | Timeouts, pool limits, bulkhead pattern |
| Cache stampede | Cache expires, all requests hit DB simultaneously | Cache warming, staggered TTL, lock-based refresh |
| Death spiral | Load → slow → timeouts → retries → more load | Rate limiting, load shedding, auto-scaling |

### Human Failures

| Failure | Symptom | Mitigation |
|---------|---------|------------|
| Bad configuration deploy | Partial outage after config change | Config validation, canary deploys |
| Database migration failure | Data corruption, schema mismatch | Backward-compatible migrations, rollback plan |
| Wrong service version | API incompatibility | Contract tests, API versioning |
| Forgot to scale | Traffic spike causes outage | Auto-scaling, load testing |

## Design Checklist

For every service interaction, ask:
```
□ What happens if this call fails?
□ What happens if this call takes 10x longer?
□ What happens if this call succeeds but the response is lost?
□ What happens if this is called twice?
□ What happens if the dependency is completely down for 1 hour?
□ What happens if the data is stale?
□ What happens if the data is corrupted?
□ What happens if we deploy a new version while requests are in flight?
```'''
    ),
    (
        "thinking/distributed-bulkhead-pattern",
        "One slow database query is causing all of our API endpoints to become slow because it exhausts the connection pool. How do we isolate failures?",
        r'''<think>
The Bulkhead pattern — inspired by ship compartments that prevent one flood from sinking the entire ship. Isolate resources so one failing component can't exhaust shared resources.

For database connections: separate pools for different operations.
For threads: separate thread pools for different services.
For HTTP clients: separate connection pools for different downstream services.
</think>

**Bulkhead pattern** — separate resource pools so one failure can't sink everything:

## The Problem

```
All endpoints share ONE connection pool (20 connections):
  /api/users        → uses 2 connections (fast)
  /api/orders       → uses 2 connections (fast)
  /api/reports      → uses 18 connections (SLOW QUERY!) ← Exhausts pool
  /api/users        → no connections available → TIMEOUT
  /api/orders       → no connections available → TIMEOUT
```

## The Fix: Separate Connection Pools

```python
from sqlalchemy import create_engine

# Separate pools for different workloads
fast_engine = create_engine(
    DATABASE_URL,
    pool_size=15,        # Majority of connections for fast queries
    max_overflow=5,
    pool_timeout=5,      # Fail fast if pool is full
)

slow_engine = create_engine(
    DATABASE_URL,
    pool_size=5,         # Limited connections for heavy queries
    max_overflow=2,
    pool_timeout=30,     # Allow longer waits for report queries
)

# Fast endpoints use fast pool
@app.get("/api/users/{id}")
async def get_user(id: int):
    with fast_engine.connect() as conn:
        return conn.execute(select(User).where(User.id == id)).one()

# Slow endpoints use slow pool — can't affect fast endpoints
@app.get("/api/reports/monthly")
async def monthly_report():
    with slow_engine.connect() as conn:
        return conn.execute(text("SELECT ... complex aggregation ...")).all()
```

## HTTP Client Bulkheads

```python
import httpx

# Separate HTTP clients for different downstream services
payment_client = httpx.AsyncClient(
    base_url="http://payment-service",
    limits=httpx.Limits(max_connections=20),
    timeout=5.0,
)

recommendation_client = httpx.AsyncClient(
    base_url="http://recommendation-service",
    limits=httpx.Limits(max_connections=10),
    timeout=2.0,  # Non-critical, fail fast
)

# If recommendation service is slow, it can't exhaust payment connections
```

## Thread Pool Bulkheads

```python
from concurrent.futures import ThreadPoolExecutor

# Separate thread pools
critical_pool = ThreadPoolExecutor(max_workers=10, thread_name_prefix="critical")
background_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="background")

# Critical work gets its own resources
async def process_payment(data):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(critical_pool, _charge, data)

# Background work can't starve critical work
async def update_analytics(data):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(background_pool, _track, data)
```

## Bulkhead Design Principle

```
Without bulkheads:
  [All resources shared] → One failure affects everything

With bulkheads:
  [Critical pool    ] → Payments, auth (protected)
  [Standard pool    ] → Normal API queries
  [Background pool  ] → Reports, analytics (isolated)
  [External API pool] → Third-party calls (isolated)
```

**Rule**: Any resource that can be exhausted (connections, threads, memory) should be partitioned by criticality.'''
    ),
    (
        "thinking/distributed-deadline-propagation",
        "Our API has a 30-second timeout, but it calls Service A (10s timeout) which calls Service B (10s timeout) which calls Service C (10s timeout). A request can take up to 30s at Service C, which means our API has already timed out. How do we handle cascading timeouts?",
        r'''<think>
Deadline propagation — pass the remaining time budget to downstream services so they can fail fast when there's no point in continuing.

Without deadline propagation:
- API sets 30s timeout
- Service A gets 10s timeout and uses 8s, passes to B
- Service B gets 10s timeout, starts processing
- By this time, 18s have elapsed, API only has 12s left
- Service C gets 10s timeout, takes 10s
- Total: 28s — API barely makes it
- But if B was slow, C doesn't know the API is already timing out

With deadline propagation:
- API sets deadline: "complete by T+30s"
- Service A checks: 30s remaining, proceeds
- Service A passes deadline to B: "complete by T+30s" (not a new 10s timeout)
- Service B checks: 22s remaining, proceeds
- Service B passes deadline to C: "complete by T+30s"
- If C can't finish before the deadline, it aborts immediately
</think>

## The Problem: Independent Timeouts Don't Compose

```
API (30s) → A (10s) → B (10s) → C (10s)

Timeline:
  0s   API receives request
  8s   A finishes, calls B
  18s  B finishes, calls C
  28s  C finishes
  30s  API timeout fires → returns 504 to user

User waited 30s, got an error, but ALL services actually succeeded!
The work was wasted because timeouts weren't coordinated.
```

## The Fix: Pass a Deadline, Not a Duration

```python
import time

class Deadline:
    def __init__(self, timeout_seconds: float):
        self.deadline = time.monotonic() + timeout_seconds

    @property
    def remaining(self) -> float:
        return max(0, self.deadline - time.monotonic())

    @property
    def expired(self) -> bool:
        return self.remaining <= 0

    def to_header(self) -> str:
        return str(self.deadline)

    @classmethod
    def from_header(cls, header_value: str) -> 'Deadline':
        d = cls.__new__(cls)
        d.deadline = float(header_value)
        return d

# Middleware: extract or create deadline
@app.middleware("http")
async def deadline_middleware(request, call_next):
    deadline_header = request.headers.get('X-Deadline')
    if deadline_header:
        deadline = Deadline.from_header(deadline_header)
    else:
        deadline = Deadline(timeout_seconds=30)

    if deadline.expired:
        return Response(status_code=504, content='Deadline exceeded')

    request.state.deadline = deadline
    response = await call_next(request)
    return response

# When calling downstream services, pass the deadline
async def call_service_b(data, deadline: Deadline):
    if deadline.remaining < 1.0:
        raise DeadlineExceeded("Not enough time to call Service B")

    async with httpx.AsyncClient() as client:
        response = await client.post(
            'http://service-b/api/process',
            json=data,
            headers={'X-Deadline': deadline.to_header()},
            timeout=deadline.remaining,  # Use remaining time as timeout
        )
        return response.json()
```

## With the Deadline

```
API (30s deadline) → A → B → C

Timeline:
  0s   API sets deadline T+30s, passes to A
  8s   A finishes, 22s remaining, passes deadline to B
  18s  B finishes, 12s remaining, passes deadline to C
  19s  C checks: 11s remaining → proceeds
  28s  C finishes → response flows back
  28s  API responds to user ✓

If B was slow:
  0s   API sets deadline T+30s
  8s   A finishes, passes deadline to B
  27s  B finishes, 3s remaining, passes deadline to C
  27s  C checks: 3s remaining → CAN'T finish in 3s → abort immediately
  27s  B gets abort → returns error fast
  27s  API returns partial error in 27s (not 30s timeout)
```

**Rule**: Pass a deadline (absolute time), not a timeout (duration). Each service checks remaining time and aborts early if there's not enough time to complete.'''
    ),
    (
        "thinking/distributed-load-shedding",
        "During traffic spikes, our service tries to handle all requests and becomes slow for everyone. How do we gracefully handle more traffic than we can process?",
        r'''<think>
Load shedding — intentionally dropping some requests when overloaded to maintain quality of service for the rest. Better to serve 80% of users well than 100% of users poorly.

Strategies:
1. Queue-based: reject when queue is full
2. Concurrency-based: limit concurrent requests
3. CPU-based: reject when CPU > threshold
4. Priority-based: drop low-priority requests first
</think>

**Load shedding** — reject excess requests fast so remaining requests get good service.

```
Without load shedding:
  1000 requests → all processed slowly → p99 = 30s, errors = 50%

With load shedding:
  1000 requests → 700 processed normally, 300 rejected immediately
  Served requests: p99 = 200ms ✓
  Rejected requests: instant 503 → client retries later
```

## Implementation: Concurrency Limiter

```python
import asyncio
from fastapi import FastAPI, Response

class LoadShedder:
    def __init__(self, max_concurrent: int, max_queue: int = 0):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._queue_size = 0
        self._max_queue = max_queue

    async def try_acquire(self) -> bool:
        if self._semaphore.locked() and self._queue_size >= self._max_queue:
            return False  # Shed load
        self._queue_size += 1
        await self._semaphore.acquire()
        self._queue_size -= 1
        return True

    def release(self):
        self._semaphore.release()

shedder = LoadShedder(max_concurrent=100, max_queue=50)

@app.middleware("http")
async def load_shedding_middleware(request, call_next):
    if not await shedder.try_acquire():
        return Response(
            content='{"error": "Service overloaded, try again later"}',
            status_code=503,
            headers={'Retry-After': '5'},
        )
    try:
        return await call_next(request)
    finally:
        shedder.release()
```

## Priority-Based Shedding

```python
class PriorityLoadShedder:
    """Shed low-priority traffic first."""

    def __init__(self, limits: dict):
        # limits = {'critical': 200, 'normal': 100, 'background': 20}
        self._counters = {k: 0 for k in limits}
        self._limits = limits

    def should_shed(self, priority: str) -> bool:
        if priority not in self._limits:
            return True

        # Always accept critical traffic (up to limit)
        if priority == 'critical':
            return self._counters['critical'] >= self._limits['critical']

        # Shed normal traffic when under pressure
        total_load = sum(self._counters.values())
        total_capacity = sum(self._limits.values())
        if total_load / total_capacity > 0.8:
            # Under pressure — shed non-critical
            return self._counters[priority] >= self._limits[priority]

        return self._counters[priority] >= self._limits[priority]

# Usage
@app.middleware("http")
async def priority_shedding(request, call_next):
    priority = classify_request(request)
    # Health checks and payments = critical
    # Normal API calls = normal
    # Analytics, thumbnails = background

    if shedder.should_shed(priority):
        return Response(status_code=503, headers={'Retry-After': '5'})
    return await call_next(request)
```

**When overloaded**: reject thumbnail generation (background) before rejecting product pages (normal) before rejecting checkout (critical).'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
