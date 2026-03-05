"""Microservices — service mesh, circuit breaker, saga pattern, and distributed tracing."""

PAIRS = [
    (
        "patterns/circuit-breaker",
        "Show circuit breaker pattern: states, failure detection, half-open testing, and fallback handling.",
        '''Circuit breaker pattern:

```python
import asyncio
import time
import logging
from enum import StrEnum, auto
from dataclasses import dataclass, field
from typing import Callable, Awaitable, TypeVar, Any
from functools import wraps

logger = logging.getLogger(__name__)
T = TypeVar("T")


class CircuitState(StrEnum):
    CLOSED = auto()      # Normal operation
    OPEN = auto()        # Failing, reject requests
    HALF_OPEN = auto()   # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    failure_threshold: int = 5        # Failures before opening
    success_threshold: int = 3        # Successes to close from half-open
    timeout: float = 30.0             # Seconds before half-open attempt
    half_open_max_calls: int = 3      # Max concurrent calls in half-open


class CircuitBreaker:
    """Prevent cascading failures by stopping calls to failing services."""

    def __init__(self, name: str, config: CircuitBreakerConfig | None = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = 0.0
        self.half_open_calls = 0
        self._lock = asyncio.Lock()

    async def call(
        self,
        fn: Callable[..., Awaitable[T]],
        *args,
        fallback: Callable[..., Awaitable[T]] | None = None,
        **kwargs,
    ) -> T:
        """Execute function with circuit breaker protection."""
        async with self._lock:
            if not self._should_allow():
                if fallback:
                    logger.warning("Circuit %s OPEN, using fallback", self.name)
                    return await fallback(*args, **kwargs)
                raise CircuitOpenError(
                    f"Circuit '{self.name}' is {self.state}, "
                    f"retry after {self._retry_after():.1f}s"
                )

        try:
            result = await fn(*args, **kwargs)
            await self._on_success()
            return result
        except Exception as e:
            await self._on_failure(e)
            if fallback:
                return await fallback(*args, **kwargs)
            raise

    def _should_allow(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if time.monotonic() - self.last_failure_time >= self.config.timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                self.success_count = 0
                logger.info("Circuit %s -> HALF_OPEN", self.name)
                return True
            return False

        # HALF_OPEN: allow limited calls
        if self.half_open_calls < self.config.half_open_max_calls:
            self.half_open_calls += 1
            return True
        return False

    async def _on_success(self):
        async with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.config.success_threshold:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    logger.info("Circuit %s -> CLOSED (recovered)", self.name)
            else:
                self.failure_count = 0

    async def _on_failure(self, error: Exception):
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = time.monotonic()

            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                logger.warning("Circuit %s -> OPEN (half-open test failed)", self.name)
            elif self.failure_count >= self.config.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(
                    "Circuit %s -> OPEN (failures=%d)",
                    self.name, self.failure_count,
                )

    def _retry_after(self) -> float:
        elapsed = time.monotonic() - self.last_failure_time
        return max(0, self.config.timeout - elapsed)


class CircuitOpenError(Exception):
    pass


# --- Decorator ---

def circuit_breaker(name: str, **config_kwargs):
    """Decorator to apply circuit breaker to async functions."""
    cb = CircuitBreaker(name, CircuitBreakerConfig(**config_kwargs))

    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            return await cb.call(fn, *args, **kwargs)
        wrapper.circuit = cb  # Expose for monitoring
        return wrapper
    return decorator


# --- Usage ---

@circuit_breaker("payment-service", failure_threshold=3, timeout=60)
async def charge_payment(amount: float, card_token: str) -> dict:
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://payments.internal/charge",
            json={"amount": amount, "token": card_token},
            timeout=5.0,
        )
        response.raise_for_status()
        return response.json()


# With fallback
payment_cb = CircuitBreaker("payment", CircuitBreakerConfig(failure_threshold=3))

async def charge_with_fallback(amount: float, token: str):
    return await payment_cb.call(
        charge_payment, amount, token,
        fallback=queue_for_retry,  # Queue for later if circuit open
    )
```

Circuit breaker patterns:
1. **Three states** — CLOSED (normal), OPEN (rejecting), HALF_OPEN (testing recovery)
2. **Failure threshold** — open circuit after N consecutive failures
3. **Timeout + half-open** — periodically test if service recovered
4. **Fallback** — graceful degradation when circuit is open (queue, cache, default)
5. **`_lock`** — thread-safe state transitions prevent race conditions'''
    ),
    (
        "patterns/saga-pattern",
        "Show the Saga pattern for distributed transactions: orchestration, compensating actions, and error handling.",
        '''Saga pattern for distributed transactions:

```python
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Any
from enum import StrEnum, auto
from datetime import datetime, timezone
import uuid

logger = logging.getLogger(__name__)


class StepStatus(StrEnum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    COMPENSATING = auto()
    COMPENSATED = auto()
    FAILED = auto()


@dataclass
class SagaStep:
    name: str
    action: Callable[..., Awaitable[Any]]
    compensation: Callable[..., Awaitable[None]]
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: str | None = None


@dataclass
class SagaContext:
    """Shared context passed between saga steps."""
    saga_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    data: dict = field(default_factory=dict)
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class SagaOrchestrator:
    """Orchestrate distributed transaction with compensating actions."""

    def __init__(self, name: str):
        self.name = name
        self.steps: list[SagaStep] = []

    def step(
        self,
        name: str,
        action: Callable,
        compensation: Callable,
    ) -> "SagaOrchestrator":
        """Add a step with its compensating action."""
        self.steps.append(SagaStep(
            name=name,
            action=action,
            compensation=compensation,
        ))
        return self

    async def execute(self, context: SagaContext) -> tuple[bool, SagaContext]:
        """Execute all steps. Compensate on failure."""
        completed_steps: list[SagaStep] = []

        logger.info("Saga '%s' [%s] started", self.name, context.saga_id)

        for step in self.steps:
            step.status = StepStatus.RUNNING
            logger.info("Step '%s' executing...", step.name)

            try:
                step.result = await step.action(context)
                step.status = StepStatus.COMPLETED
                completed_steps.append(step)
                logger.info("Step '%s' completed", step.name)
            except Exception as e:
                step.status = StepStatus.FAILED
                step.error = str(e)
                logger.error("Step '%s' failed: %s", step.name, e)

                # Compensate in reverse order
                await self._compensate(completed_steps, context)
                return False, context

        logger.info("Saga '%s' [%s] completed successfully", self.name, context.saga_id)
        return True, context

    async def _compensate(self, completed_steps: list[SagaStep], context: SagaContext):
        """Run compensating actions in reverse order."""
        logger.warning("Starting compensation for %d steps", len(completed_steps))

        for step in reversed(completed_steps):
            step.status = StepStatus.COMPENSATING
            try:
                await step.compensation(context)
                step.status = StepStatus.COMPENSATED
                logger.info("Step '%s' compensated", step.name)
            except Exception as e:
                step.status = StepStatus.FAILED
                logger.error(
                    "CRITICAL: Compensation failed for '%s': %s. Manual intervention required.",
                    step.name, e,
                )


# --- Example: Order placement saga ---

async def create_order(ctx: SagaContext) -> dict:
    order = await order_service.create(
        customer_id=ctx.data["customer_id"],
        items=ctx.data["items"],
    )
    ctx.data["order_id"] = order["id"]
    return order

async def cancel_order(ctx: SagaContext):
    await order_service.cancel(ctx.data["order_id"])


async def reserve_inventory(ctx: SagaContext) -> dict:
    reservation = await inventory_service.reserve(
        items=ctx.data["items"],
        order_id=ctx.data["order_id"],
    )
    ctx.data["reservation_id"] = reservation["id"]
    return reservation

async def release_inventory(ctx: SagaContext):
    await inventory_service.release(ctx.data["reservation_id"])


async def process_payment(ctx: SagaContext) -> dict:
    payment = await payment_service.charge(
        customer_id=ctx.data["customer_id"],
        amount=ctx.data["total"],
        order_id=ctx.data["order_id"],
    )
    ctx.data["payment_id"] = payment["id"]
    return payment

async def refund_payment(ctx: SagaContext):
    await payment_service.refund(ctx.data["payment_id"])


async def send_confirmation(ctx: SagaContext):
    await notification_service.send_order_confirmation(
        customer_id=ctx.data["customer_id"],
        order_id=ctx.data["order_id"],
    )

async def noop_compensation(ctx: SagaContext):
    pass  # Notification doesn't need compensation


# --- Build and execute saga ---

place_order_saga = (
    SagaOrchestrator("place-order")
    .step("create_order", create_order, cancel_order)
    .step("reserve_inventory", reserve_inventory, release_inventory)
    .step("process_payment", process_payment, refund_payment)
    .step("send_confirmation", send_confirmation, noop_compensation)
)

async def place_order(customer_id: str, items: list[dict], total: float):
    context = SagaContext(data={
        "customer_id": customer_id,
        "items": items,
        "total": total,
    })

    success, ctx = await place_order_saga.execute(context)

    if not success:
        raise OrderFailedError("Order placement failed, all changes rolled back")

    return {"order_id": ctx.data["order_id"]}
```

Saga patterns:
1. **Compensating actions** — each step defines its undo operation
2. **Reverse compensation** — on failure, undo completed steps in reverse order
3. **`SagaContext`** — shared data flows between steps (order_id, payment_id, etc.)
4. **Orchestrator** — central coordinator manages step execution and rollback
5. **Idempotent compensations** — compensations must be safe to retry on failure'''
    ),
]
