"""Distributed systems — microservices communication, service mesh, distributed transactions, observability."""

PAIRS = [
    (
        "distributed/service-discovery",
        "Explain service discovery patterns: client-side vs server-side discovery, health checking, and service registry with practical examples.",
        '''Service discovery patterns for microservices:

```python
import asyncio
import hashlib
import random
import time
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

@dataclass
class ServiceInstance:
    service_name: str
    instance_id: str
    host: str
    port: int
    metadata: dict = field(default_factory=dict)
    health: HealthStatus = HealthStatus.HEALTHY
    registered_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    weight: int = 100

    @property
    def address(self) -> str:
        return f"{self.host}:{self.port}"

class ServiceRegistry:
    """In-memory service registry with health checking."""

    def __init__(self, heartbeat_timeout: int = 30):
        self.services: dict[str, dict[str, ServiceInstance]] = {}
        self.heartbeat_timeout = heartbeat_timeout

    def register(self, instance: ServiceInstance):
        if instance.service_name not in self.services:
            self.services[instance.service_name] = {}
        self.services[instance.service_name][instance.instance_id] = instance

    def deregister(self, service_name: str, instance_id: str):
        if service_name in self.services:
            self.services[service_name].pop(instance_id, None)

    def heartbeat(self, service_name: str, instance_id: str):
        inst = self.services.get(service_name, {}).get(instance_id)
        if inst:
            inst.last_heartbeat = time.time()

    def get_healthy_instances(self, service_name: str) -> list[ServiceInstance]:
        instances = self.services.get(service_name, {}).values()
        now = time.time()
        return [
            inst for inst in instances
            if inst.health == HealthStatus.HEALTHY
            and (now - inst.last_heartbeat) < self.heartbeat_timeout
        ]

# --- Client-side load balancing ---

class LoadBalancer:
    def __init__(self, registry: ServiceRegistry):
        self.registry = registry

    def round_robin(self, service_name: str) -> Optional[ServiceInstance]:
        instances = self.registry.get_healthy_instances(service_name)
        if not instances:
            return None
        # Use hash of current time for simple round-robin
        idx = int(time.time() * 1000) % len(instances)
        return instances[idx]

    def weighted_random(self, service_name: str) -> Optional[ServiceInstance]:
        instances = self.registry.get_healthy_instances(service_name)
        if not instances:
            return None
        weights = [inst.weight for inst in instances]
        return random.choices(instances, weights=weights, k=1)[0]

    def least_connections(self, service_name: str,
                          connection_counts: dict[str, int]) -> Optional[ServiceInstance]:
        instances = self.registry.get_healthy_instances(service_name)
        if not instances:
            return None
        return min(instances,
                   key=lambda i: connection_counts.get(i.instance_id, 0))

# --- Service mesh sidecar pattern ---

class SidecarProxy:
    """L7 proxy for service-to-service communication."""

    def __init__(self, service_name: str, registry: ServiceRegistry):
        self.service_name = service_name
        self.registry = registry
        self.circuit_breakers: dict[str, CircuitBreaker] = {}
        self.retry_config = RetryConfig(max_retries=3, backoff_base=0.1)

    async def call(self, target_service: str, path: str,
                   method: str = "GET", body: dict = None) -> dict:
        instances = self.registry.get_healthy_instances(target_service)
        if not instances:
            raise ServiceUnavailableError(f"No healthy instances of {target_service}")

        last_error = None
        for attempt in range(self.retry_config.max_retries):
            instance = random.choice(instances)
            cb = self._get_circuit_breaker(instance.instance_id)

            if not cb.allow_request():
                continue

            try:
                result = await self._http_call(instance, path, method, body)
                cb.record_success()
                return result
            except Exception as e:
                cb.record_failure()
                last_error = e
                await asyncio.sleep(self.retry_config.backoff_base * (2 ** attempt))

        raise last_error or ServiceUnavailableError("All retries exhausted")

# --- Health check patterns ---

class HealthChecker:
    """Comprehensive health check for a service."""

    def __init__(self):
        self.checks: list[tuple[str, callable]] = []

    def add_check(self, name: str, check_fn):
        self.checks.append((name, check_fn))

    async def run(self) -> dict:
        results = {}
        overall = HealthStatus.HEALTHY

        for name, check_fn in self.checks:
            try:
                start = time.time()
                await check_fn()
                results[name] = {
                    "status": "healthy",
                    "latency_ms": round((time.time() - start) * 1000, 2),
                }
            except Exception as e:
                results[name] = {"status": "unhealthy", "error": str(e)}
                overall = HealthStatus.UNHEALTHY

        return {"status": overall.value, "checks": results}

# Usage:
checker = HealthChecker()
checker.add_check("database", lambda: db.execute("SELECT 1"))
checker.add_check("redis", lambda: redis.ping())
checker.add_check("downstream_api", lambda: http.get("http://api/health"))
```

Service discovery patterns:
- **Client-side** (Eureka, Consul): client queries registry, picks instance
- **Server-side** (AWS ALB, K8s Service): load balancer routes requests
- **DNS-based** (Consul DNS, CoreDNS): service.namespace.svc.cluster.local
- **Service mesh** (Istio, Linkerd): sidecar proxy handles all networking'''
    ),
    (
        "distributed/circuit-breaker",
        "Implement the circuit breaker pattern in Python. Show states, thresholds, half-open testing, and integration with retry logic.",
        '''Circuit breaker pattern for resilient service calls:

```python
import time
import asyncio
from dataclasses import dataclass
from enum import Enum, auto
from typing import Callable, Any, Optional
from functools import wraps
import logging

log = logging.getLogger(__name__)

class CircuitState(Enum):
    CLOSED = auto()    # Normal operation, requests flow through
    OPEN = auto()      # Failing, reject requests immediately
    HALF_OPEN = auto() # Testing if service recovered

@dataclass
class CircuitConfig:
    failure_threshold: int = 5       # Failures before opening
    success_threshold: int = 3       # Successes to close from half-open
    timeout: float = 30.0            # Seconds before trying half-open
    half_open_max_calls: int = 3     # Max concurrent half-open calls

class CircuitBreaker:
    def __init__(self, name: str, config: CircuitConfig = None):
        self.name = name
        self.config = config or CircuitConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.half_open_calls = 0

    def allow_request(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if time.monotonic() - self.last_failure_time >= self.config.timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                self.success_count = 0
                log.info(f"Circuit {self.name}: OPEN → HALF_OPEN")
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            return self.half_open_calls < self.config.half_open_max_calls

        return False

    def record_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.config.success_threshold:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                log.info(f"Circuit {self.name}: HALF_OPEN → CLOSED")
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

    def record_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.monotonic()

        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
            log.warning(f"Circuit {self.name}: HALF_OPEN → OPEN")
        elif (self.state == CircuitState.CLOSED and
              self.failure_count >= self.config.failure_threshold):
            self.state = CircuitState.OPEN
            log.warning(f"Circuit {self.name}: CLOSED → OPEN "
                       f"(failures={self.failure_count})")

# --- Decorator for easy usage ---

def circuit_breaker(name: str, config: CircuitConfig = None):
    cb = CircuitBreaker(name, config)

    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            if not cb.allow_request():
                raise CircuitOpenError(f"Circuit {name} is open")

            try:
                result = await fn(*args, **kwargs)
                cb.record_success()
                return result
            except Exception as e:
                cb.record_failure()
                raise

        wrapper.circuit_breaker = cb
        return wrapper
    return decorator

class CircuitOpenError(Exception):
    pass

# --- Combined retry + circuit breaker ---

@dataclass
class RetryConfig:
    max_retries: int = 3
    backoff_base: float = 0.1
    backoff_max: float = 10.0
    retryable_exceptions: tuple = (ConnectionError, TimeoutError)

async def resilient_call(fn: Callable, retry_config: RetryConfig,
                         circuit: CircuitBreaker,
                         fallback: Optional[Callable] = None) -> Any:
    """Retry with exponential backoff + circuit breaker + fallback."""

    if not circuit.allow_request():
        if fallback:
            log.info(f"Circuit open, using fallback for {circuit.name}")
            return await fallback()
        raise CircuitOpenError(f"Circuit {circuit.name} is open")

    last_error = None
    for attempt in range(retry_config.max_retries):
        try:
            result = await fn()
            circuit.record_success()
            return result
        except retry_config.retryable_exceptions as e:
            last_error = e
            circuit.record_failure()

            if not circuit.allow_request():
                break

            delay = min(
                retry_config.backoff_base * (2 ** attempt),
                retry_config.backoff_max,
            )
            # Add jitter
            delay *= (0.5 + 0.5 * (hash(str(time.time())) % 100) / 100)
            await asyncio.sleep(delay)
        except Exception as e:
            circuit.record_failure()
            raise

    if fallback:
        return await fallback()
    raise last_error

# --- Usage example ---

payment_circuit = CircuitBreaker("payment-service", CircuitConfig(
    failure_threshold=3, timeout=60, success_threshold=2,
))

async def charge_customer(user_id: str, amount: float):
    async def _call():
        return await http_client.post(
            "http://payment-service/charge",
            json={"user_id": user_id, "amount": amount},
            timeout=5.0,
        )

    async def _fallback():
        # Queue for later processing
        await message_queue.send("payment-retry", {
            "user_id": user_id, "amount": amount,
        })
        return {"status": "queued"}

    return await resilient_call(
        _call,
        RetryConfig(max_retries=3),
        payment_circuit,
        fallback=_fallback,
    )
```

Circuit breaker states:
```
CLOSED ──(failures >= threshold)──> OPEN
  ↑                                   │
  │                               (timeout)
  │                                   ↓
  └──(successes >= threshold)── HALF_OPEN
                                   │
                              (failure)
                                   ↓
                                 OPEN
```'''
    ),
    (
        "distributed/idempotency",
        "Show idempotency patterns for distributed systems: idempotency keys, exactly-once processing, and deduplication strategies.",
        '''Idempotency patterns for reliable distributed systems:

```python
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Optional
from datetime import datetime, timezone

# --- Idempotency Key Store ---

@dataclass
class IdempotencyRecord:
    key: str
    status: str  # "processing", "completed", "failed"
    response: Optional[dict] = None
    created_at: float = 0
    expires_at: float = 0

class IdempotencyStore:
    """Store idempotency keys with Redis for deduplication."""

    def __init__(self, redis_client, ttl: int = 86400):
        self.redis = redis_client
        self.ttl = ttl

    async def check_and_set(self, key: str) -> Optional[IdempotencyRecord]:
        """Atomic check-and-set. Returns existing record or None."""
        record_key = f"idempotency:{key}"

        # Try to set processing status (NX = only if not exists)
        created = await self.redis.set(
            record_key,
            json.dumps({
                "status": "processing",
                "created_at": time.time(),
            }),
            nx=True,
            ex=self.ttl,
        )

        if created:
            return None  # New request, proceed

        # Key exists — check status
        raw = await self.redis.get(record_key)
        if raw:
            data = json.loads(raw)
            return IdempotencyRecord(
                key=key,
                status=data["status"],
                response=data.get("response"),
                created_at=data["created_at"],
            )
        return None

    async def complete(self, key: str, response: dict):
        """Mark request as completed with response."""
        record_key = f"idempotency:{key}"
        await self.redis.setex(
            record_key,
            self.ttl,
            json.dumps({
                "status": "completed",
                "response": response,
                "created_at": time.time(),
            }),
        )

    async def fail(self, key: str, error: str):
        """Mark request as failed (allows retry)."""
        record_key = f"idempotency:{key}"
        await self.redis.delete(record_key)

# --- Idempotent API endpoint ---

from fastapi import FastAPI, Request, HTTPException, Header

app = FastAPI()
store = IdempotencyStore(redis_client)

@app.post("/api/payments")
async def create_payment(
    request: Request,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
):
    # Check for duplicate
    existing = await store.check_and_set(idempotency_key)

    if existing:
        if existing.status == "completed":
            return existing.response  # Return cached response
        if existing.status == "processing":
            raise HTTPException(409, "Request is still processing")

    try:
        # Process payment
        body = await request.json()
        result = await process_payment(body)
        response = {"payment_id": result.id, "status": "success"}

        # Cache response
        await store.complete(idempotency_key, response)
        return response

    except Exception as e:
        # Allow retry on failure
        await store.fail(idempotency_key, str(e))
        raise

# --- Message deduplication (for queues) ---

class MessageDeduplicator:
    """Deduplicate messages in event-driven systems."""

    def __init__(self, redis_client, window: int = 3600):
        self.redis = redis_client
        self.window = window

    def message_id(self, message: dict) -> str:
        """Generate deterministic ID from message content."""
        content = json.dumps(message, sort_keys=True, default=str)
        return hashlib.sha256(content.encode()).hexdigest()

    async def is_duplicate(self, message_id: str) -> bool:
        """Check if message was already processed."""
        key = f"dedup:{message_id}"
        exists = await self.redis.exists(key)
        return bool(exists)

    async def mark_processed(self, message_id: str):
        """Mark message as processed."""
        key = f"dedup:{message_id}"
        await self.redis.setex(key, self.window, "1")

    async def process_once(self, message: dict, handler) -> bool:
        """Process message exactly once."""
        mid = self.message_id(message)

        if await self.is_duplicate(mid):
            return False  # Already processed

        try:
            await handler(message)
            await self.mark_processed(mid)
            return True
        except Exception:
            # Don't mark as processed — allow retry
            raise

# --- Database-level idempotency ---

IDEMPOTENT_INSERT = """
-- Use unique constraint for idempotent writes
INSERT INTO payments (idempotency_key, user_id, amount, status)
VALUES ($1, $2, $3, 'pending')
ON CONFLICT (idempotency_key) DO NOTHING
RETURNING *;

-- If RETURNING is empty, the record already exists
-- Fetch the existing record:
SELECT * FROM payments WHERE idempotency_key = $1;
"""

IDEMPOTENT_STATE_MACHINE = """
-- Only transition if in expected state (idempotent state changes)
UPDATE orders
SET status = 'shipped',
    shipped_at = NOW()
WHERE order_id = $1
  AND status = 'processing'  -- Only if currently processing
RETURNING *;
-- Returns empty if already shipped (idempotent)
"""
```

Idempotency patterns:
1. **Idempotency keys** — client-generated unique key per operation
2. **Natural idempotency** — `PUT /users/123` is naturally idempotent
3. **Database constraints** — unique indexes prevent duplicates
4. **State machines** — conditional updates (`WHERE status = 'pending'`)
5. **Message dedup** — content hash + time window
6. **Exactly-once = at-least-once + idempotent processing**'''
    ),
    (
        "distributed/saga-pattern-deep",
        "Show a detailed saga pattern implementation: orchestration-based saga with compensating transactions, timeouts, and failure recovery.",
        '''Orchestration-based saga for distributed transactions:

```python
import asyncio
import json
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Optional
from uuid import uuid4

class StepStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    COMPENSATING = auto()
    COMPENSATED = auto()
    FAILED = auto()

@dataclass
class SagaStep:
    name: str
    action: Callable        # Forward action
    compensation: Callable  # Rollback action
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    timeout: float = 30.0

@dataclass
class SagaState:
    saga_id: str
    name: str
    steps: list[SagaStep]
    current_step: int = 0
    status: str = "running"  # running, completed, compensating, failed
    context: dict = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)

class SagaOrchestrator:
    """Orchestrate distributed transactions with compensation."""

    def __init__(self, state_store, event_publisher):
        self.state_store = state_store
        self.publisher = event_publisher

    async def execute(self, saga: SagaState) -> dict:
        """Execute saga steps forward, compensate on failure."""
        await self.state_store.save(saga)

        try:
            # Execute steps forward
            for i, step in enumerate(saga.steps):
                saga.current_step = i
                step.status = StepStatus.RUNNING
                await self.state_store.save(saga)

                try:
                    result = await asyncio.wait_for(
                        step.action(saga.context),
                        timeout=step.timeout,
                    )
                    step.result = result
                    step.status = StepStatus.COMPLETED
                    saga.context[f"{step.name}_result"] = result

                    await self.publisher.publish(f"saga.{saga.name}.step_completed", {
                        "saga_id": saga.saga_id,
                        "step": step.name,
                    })

                except Exception as e:
                    step.status = StepStatus.FAILED
                    step.error = str(e)

                    await self.publisher.publish(f"saga.{saga.name}.step_failed", {
                        "saga_id": saga.saga_id,
                        "step": step.name,
                        "error": str(e),
                    })

                    # Compensate completed steps in reverse
                    await self._compensate(saga, i)
                    return {"status": "failed", "error": str(e), "saga_id": saga.saga_id}

            saga.status = "completed"
            await self.state_store.save(saga)
            return {"status": "completed", "saga_id": saga.saga_id, "context": saga.context}

        except Exception as e:
            saga.status = "failed"
            await self.state_store.save(saga)
            raise

    async def _compensate(self, saga: SagaState, failed_step_index: int):
        """Run compensating transactions in reverse order."""
        saga.status = "compensating"
        await self.state_store.save(saga)

        for i in range(failed_step_index - 1, -1, -1):
            step = saga.steps[i]
            if step.status != StepStatus.COMPLETED:
                continue

            step.status = StepStatus.COMPENSATING
            await self.state_store.save(saga)

            try:
                await asyncio.wait_for(
                    step.compensation(saga.context),
                    timeout=step.timeout,
                )
                step.status = StepStatus.COMPENSATED
            except Exception as e:
                step.status = StepStatus.FAILED
                step.error = f"Compensation failed: {e}"
                # Log for manual intervention
                await self.publisher.publish("saga.compensation_failed", {
                    "saga_id": saga.saga_id,
                    "step": step.name,
                    "error": str(e),
                })

        saga.status = "compensated"
        await self.state_store.save(saga)

# --- Order fulfillment saga ---

async def create_order_saga(user_id: str, items: list, payment_method: str):
    """Saga: Reserve Inventory → Charge Payment → Create Shipment."""

    async def reserve_inventory(ctx):
        result = await inventory_service.reserve(ctx["items"])
        return {"reservation_id": result.id}

    async def release_inventory(ctx):
        rid = ctx.get("reserve_inventory_result", {}).get("reservation_id")
        if rid:
            await inventory_service.release(rid)

    async def charge_payment(ctx):
        result = await payment_service.charge(
            user_id=ctx["user_id"],
            amount=ctx["total"],
            method=ctx["payment_method"],
        )
        return {"payment_id": result.id}

    async def refund_payment(ctx):
        pid = ctx.get("charge_payment_result", {}).get("payment_id")
        if pid:
            await payment_service.refund(pid)

    async def create_shipment(ctx):
        result = await shipping_service.create(
            reservation_id=ctx["reserve_inventory_result"]["reservation_id"],
            user_id=ctx["user_id"],
        )
        return {"shipment_id": result.id}

    async def cancel_shipment(ctx):
        sid = ctx.get("create_shipment_result", {}).get("shipment_id")
        if sid:
            await shipping_service.cancel(sid)

    saga = SagaState(
        saga_id=str(uuid4()),
        name="create_order",
        steps=[
            SagaStep("reserve_inventory", reserve_inventory, release_inventory, timeout=10),
            SagaStep("charge_payment", charge_payment, refund_payment, timeout=30),
            SagaStep("create_shipment", create_shipment, cancel_shipment, timeout=15),
        ],
        context={
            "user_id": user_id,
            "items": items,
            "payment_method": payment_method,
            "total": sum(i["price"] * i["qty"] for i in items),
        },
    )

    orchestrator = SagaOrchestrator(state_store, event_publisher)
    return await orchestrator.execute(saga)
```

Saga execution flow:
```
Forward:  Reserve Inventory → Charge Payment → Create Shipment → SUCCESS
              ✓                    ✓                 ✗ (fails)

Compensate: Cancel Shipment(skip) ← Refund Payment ← Release Inventory
```

Key principles:
1. **Every action has compensation** — reverse the effect
2. **Compensations are idempotent** — safe to retry
3. **Persist saga state** — survive process crashes
4. **Timeouts on every step** — prevent infinite waits
5. **Dead letter for failed compensations** — manual intervention'''
    ),
]
