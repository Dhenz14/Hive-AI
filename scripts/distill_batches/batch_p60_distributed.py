"""Distributed systems — consensus, leader election, distributed locks, and saga pattern."""

PAIRS = [
    (
        "distributed/leader-election",
        "Show leader election patterns: Redis-based, database-based, and heartbeat mechanisms.",
        '''Leader election patterns:

```python
import asyncio
import time
import logging
import os
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class RedisLeaderElection:
    """Leader election using Redis SET NX with TTL."""

    def __init__(self, redis, key: str = "leader",
                 ttl: int = 30, renew_interval: int = 10):
        self.redis = redis
        self.key = f"election:{key}"
        self.ttl = ttl
        self.renew_interval = renew_interval
        self.node_id = f"{os.getpid()}@{os.uname().nodename}"
        self._is_leader = False
        self._running = True

    @property
    def is_leader(self) -> bool:
        return self._is_leader

    async def try_acquire(self) -> bool:
        """Try to become leader using atomic SET NX."""
        acquired = await self.redis.set(
            self.key, self.node_id, nx=True, ex=self.ttl
        )
        if acquired:
            self._is_leader = True
            logger.info("Node %s became leader", self.node_id)
        return acquired

    async def renew(self) -> bool:
        """Renew leadership if we're still the leader."""
        current = await self.redis.get(self.key)
        if current and current.decode() == self.node_id:
            await self.redis.expire(self.key, self.ttl)
            return True
        self._is_leader = False
        return False

    async def resign(self):
        """Voluntarily give up leadership."""
        current = await self.redis.get(self.key)
        if current and current.decode() == self.node_id:
            await self.redis.delete(self.key)
        self._is_leader = False
        logger.info("Node %s resigned leadership", self.node_id)

    async def run(self, on_elected: Callable = None,
                  on_demoted: Callable = None):
        """Main election loop."""
        was_leader = False

        while self._running:
            if self._is_leader:
                renewed = await self.renew()
                if not renewed:
                    logger.warning("Lost leadership")
                    if on_demoted:
                        await on_demoted()
                    was_leader = False
            else:
                acquired = await self.try_acquire()
                if acquired and not was_leader:
                    was_leader = True
                    if on_elected:
                        await on_elected()

            await asyncio.sleep(self.renew_interval)


# --- Distributed lock with fencing token ---

class DistributedLock:
    """Redis distributed lock with fencing tokens (Redlock-like)."""

    def __init__(self, redis, name: str, ttl: int = 30):
        self.redis = redis
        self.name = f"lock:{name}"
        self.ttl = ttl
        self._token: Optional[str] = None

    async def acquire(self, timeout: float = 10.0) -> bool:
        """Try to acquire lock with timeout."""
        import secrets
        token = secrets.token_urlsafe(16)
        deadline = time.time() + timeout

        while time.time() < deadline:
            acquired = await self.redis.set(
                self.name, token, nx=True, ex=self.ttl
            )
            if acquired:
                self._token = token
                return True
            await asyncio.sleep(0.1)

        return False

    async def release(self) -> bool:
        """Release lock only if we hold it (atomic check + delete)."""
        if not self._token:
            return False

        # Lua script for atomic compare-and-delete
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        result = await self.redis.eval(script, 1, self.name, self._token)
        self._token = None
        return result == 1

    async def extend(self, additional_ttl: int = 30) -> bool:
        """Extend lock TTL if we still hold it."""
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        result = await self.redis.eval(
            script, 1, self.name, self._token, additional_ttl
        )
        return result == 1

    async def __aenter__(self):
        if not await self.acquire():
            raise LockAcquisitionError(f"Failed to acquire lock: {self.name}")
        return self

    async def __aexit__(self, *args):
        await self.release()


# Usage:
# lock = DistributedLock(redis, "order-processing")
# async with lock:
#     await process_order(order_id)


# --- Database-based leader election ---

class PostgresLeaderElection:
    """Leader election using PostgreSQL advisory locks."""

    def __init__(self, pool, lock_id: int = 1):
        self.pool = pool
        self.lock_id = lock_id

    async def try_lead(self, task: Callable) -> bool:
        """Try to acquire advisory lock and run task."""
        async with self.pool.acquire() as conn:
            acquired = await conn.fetchval(
                "SELECT pg_try_advisory_lock($1)", self.lock_id
            )
            if not acquired:
                return False

            try:
                await task()
            finally:
                await conn.fetchval(
                    "SELECT pg_advisory_unlock($1)", self.lock_id
                )
            return True
```

Leader election patterns:
1. **Redis SET NX** — atomic acquire with TTL for auto-expiry on crash
2. **Heartbeat renewal** — periodically extend TTL to maintain leadership
3. **Lua script release** — atomic compare-and-delete prevents releasing others' locks
4. **Fencing tokens** — prevent stale leaders from making changes
5. **Advisory locks** — PostgreSQL native locking for single-database deployments'''
    ),
    (
        "distributed/saga-pattern",
        "Show saga pattern for distributed transactions: orchestrator, compensating actions, and state machine.",
        '''Saga pattern for distributed transactions:

```python
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Any
import asyncio
import logging
import json
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class SagaStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    COMPENSATING = auto()
    FAILED = auto()
    COMPENSATED = auto()


@dataclass
class SagaStep:
    name: str
    action: Callable                  # Forward action
    compensation: Callable            # Rollback action
    status: str = "pending"
    result: Any = None
    error: str | None = None


@dataclass
class SagaContext:
    """Shared context for saga steps."""
    saga_id: str
    data: dict = field(default_factory=dict)
    results: dict = field(default_factory=dict)

    def set(self, key: str, value: Any):
        self.results[key] = value

    def get(self, key: str) -> Any:
        return self.results.get(key)


class SagaOrchestrator:
    """Orchestrate distributed transaction with compensating actions."""

    def __init__(self, saga_id: str):
        self.saga_id = saga_id
        self.steps: list[SagaStep] = []
        self.context = SagaContext(saga_id=saga_id)
        self.status = SagaStatus.PENDING
        self._completed_steps: list[SagaStep] = []

    def add_step(self, name: str, action: Callable,
                 compensation: Callable) -> 'SagaOrchestrator':
        self.steps.append(SagaStep(
            name=name, action=action, compensation=compensation
        ))
        return self

    async def execute(self) -> SagaContext:
        """Execute all steps; compensate on failure."""
        self.status = SagaStatus.RUNNING
        logger.info("Starting saga %s", self.saga_id)

        for step in self.steps:
            try:
                logger.info("Executing step: %s", step.name)
                step.status = "running"
                result = await step.action(self.context)
                step.result = result
                step.status = "completed"
                self._completed_steps.append(step)
                logger.info("Step %s completed", step.name)

            except Exception as e:
                step.status = "failed"
                step.error = str(e)
                logger.error("Step %s failed: %s", step.name, e)

                # Compensate completed steps in reverse order
                await self._compensate()
                self.status = SagaStatus.FAILED
                raise SagaFailedError(
                    f"Saga {self.saga_id} failed at step {step.name}: {e}",
                    completed_steps=[s.name for s in self._completed_steps],
                    failed_step=step.name,
                )

        self.status = SagaStatus.COMPLETED
        logger.info("Saga %s completed successfully", self.saga_id)
        return self.context

    async def _compensate(self):
        """Execute compensating actions in reverse order."""
        self.status = SagaStatus.COMPENSATING
        logger.info("Compensating saga %s", self.saga_id)

        for step in reversed(self._completed_steps):
            try:
                logger.info("Compensating step: %s", step.name)
                await step.compensation(self.context)
                step.status = "compensated"
            except Exception as e:
                logger.critical(
                    "COMPENSATION FAILED for step %s: %s. "
                    "Manual intervention required!",
                    step.name, e
                )
                step.status = "compensation_failed"
                # Log to dead letter / alert system

        self.status = SagaStatus.COMPENSATED


# --- Example: Order placement saga ---

async def create_order_saga(order_data: dict) -> SagaContext:
    saga = SagaOrchestrator(f"order-{order_data['order_id']}")
    saga.context.data = order_data

    saga.add_step(
        name="reserve_inventory",
        action=reserve_inventory,
        compensation=release_inventory,
    ).add_step(
        name="process_payment",
        action=process_payment,
        compensation=refund_payment,
    ).add_step(
        name="create_shipment",
        action=create_shipment,
        compensation=cancel_shipment,
    ).add_step(
        name="send_confirmation",
        action=send_confirmation,
        compensation=send_cancellation,
    )

    return await saga.execute()


# Step implementations
async def reserve_inventory(ctx: SagaContext):
    items = ctx.data["items"]
    reservation_id = await inventory_service.reserve(items)
    ctx.set("reservation_id", reservation_id)

async def release_inventory(ctx: SagaContext):
    reservation_id = ctx.get("reservation_id")
    if reservation_id:
        await inventory_service.release(reservation_id)

async def process_payment(ctx: SagaContext):
    payment_id = await payment_service.charge(
        customer_id=ctx.data["customer_id"],
        amount=ctx.data["total"],
    )
    ctx.set("payment_id", payment_id)

async def refund_payment(ctx: SagaContext):
    payment_id = ctx.get("payment_id")
    if payment_id:
        await payment_service.refund(payment_id)

async def create_shipment(ctx: SagaContext):
    tracking = await shipping_service.create(
        address=ctx.data["shipping_address"],
        items=ctx.data["items"],
    )
    ctx.set("tracking_number", tracking)

async def cancel_shipment(ctx: SagaContext):
    tracking = ctx.get("tracking_number")
    if tracking:
        await shipping_service.cancel(tracking)

async def send_confirmation(ctx: SagaContext):
    await notification_service.send(
        ctx.data["customer_id"],
        "order_confirmed",
        {"tracking": ctx.get("tracking_number")},
    )

async def send_cancellation(ctx: SagaContext):
    await notification_service.send(
        ctx.data["customer_id"],
        "order_cancelled",
        {"reason": "Processing error, full refund issued"},
    )
```

Saga patterns:
1. **Orchestrator** — central coordinator manages step sequence and compensation
2. **Compensating actions** — each step has a paired undo operation
3. **Reverse compensation** — compensate completed steps in LIFO order
4. **Shared context** — steps pass results via `SagaContext` (reservation IDs, etc.)
5. **Compensation failure logging** — log critical failures for manual intervention'''
    ),
]
