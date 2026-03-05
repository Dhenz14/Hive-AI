"""Saga pattern — distributed transactions, compensation, orchestration."""

PAIRS = [
    (
        "architecture/saga-orchestrator",
        "Show the saga pattern for distributed transactions: orchestrator-based saga with compensation steps for rollback.",
        '''Saga pattern — distributed transaction management:

```python
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Any, Optional


class SagaStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    FAILED = "failed"


@dataclass
class SagaStep:
    name: str
    action: Callable            # Forward action
    compensation: Callable       # Rollback action
    status: SagaStatus = SagaStatus.PENDING
    result: Any = None
    error: Optional[str] = None


class SagaOrchestrator:
    """Orchestrate distributed transactions with compensation.

    Each step has an action and a compensation (undo).
    If any step fails, compensate all completed steps in reverse.
    """

    def __init__(self, saga_id: str):
        self.saga_id = saga_id
        self.steps: list[SagaStep] = []
        self.status = SagaStatus.PENDING
        self.completed_steps: list[SagaStep] = []

    def add_step(self, name: str, action: Callable, compensation: Callable):
        self.steps.append(SagaStep(name=name, action=action,
                                    compensation=compensation))

    async def execute(self) -> dict:
        """Execute saga steps in order; compensate on failure."""
        self.status = SagaStatus.RUNNING

        for step in self.steps:
            step.status = SagaStatus.RUNNING
            try:
                step.result = await step.action(self.saga_id)
                step.status = SagaStatus.COMPLETED
                self.completed_steps.append(step)
            except Exception as e:
                step.status = SagaStatus.FAILED
                step.error = str(e)
                await self._compensate()
                return self._build_result()

        self.status = SagaStatus.COMPLETED
        return self._build_result()

    async def _compensate(self):
        """Compensate completed steps in reverse order."""
        self.status = SagaStatus.COMPENSATING
        for step in reversed(self.completed_steps):
            try:
                await step.compensation(self.saga_id, step.result)
                step.status = SagaStatus.PENDING  # Reset to pre-action state
            except Exception as e:
                # Compensation failed — needs manual intervention
                step.error = f"Compensation failed: {e}"

        self.status = SagaStatus.FAILED

    def _build_result(self) -> dict:
        return {
            "saga_id": self.saga_id,
            "status": self.status.value,
            "steps": [
                {"name": s.name, "status": s.status.value, "error": s.error}
                for s in self.steps
            ],
        }


# Example: Order processing saga
async def create_order_saga(order_data: dict) -> dict:
    saga = SagaOrchestrator(saga_id=f"order-{order_data['id']}")

    # Step 1: Reserve inventory
    saga.add_step(
        "reserve_inventory",
        action=lambda sid: reserve_inventory(order_data["items"]),
        compensation=lambda sid, result: release_inventory(result["reservation_id"]),
    )

    # Step 2: Process payment
    saga.add_step(
        "process_payment",
        action=lambda sid: charge_payment(order_data["payment"]),
        compensation=lambda sid, result: refund_payment(result["transaction_id"]),
    )

    # Step 3: Create shipment
    saga.add_step(
        "create_shipment",
        action=lambda sid: create_shipment(order_data["shipping"]),
        compensation=lambda sid, result: cancel_shipment(result["shipment_id"]),
    )

    # Step 4: Send confirmation
    saga.add_step(
        "send_confirmation",
        action=lambda sid: send_order_email(order_data["email"]),
        compensation=lambda sid, result: send_cancellation_email(order_data["email"]),
    )

    return await saga.execute()
```

Key patterns:
1. **Forward + compensation** — every step has an undo action; enables reliable rollback
2. **Sequential execution** — steps run in order; failure at any point triggers reverse compensation
3. **Idempotent operations** — both actions and compensations must be safe to retry
4. **Manual intervention** — if compensation fails, flag for human review; don't lose data
5. **Saga log** — record every step's status for debugging and recovery'''
    ),
    (
        "architecture/outbox-pattern",
        "Show the transactional outbox pattern for reliable event publishing: write events atomically with data, then relay.",
        '''Transactional outbox for reliable events:

```python
import json
import asyncio
from datetime import datetime
from dataclasses import dataclass


@dataclass
class OutboxEvent:
    id: str
    aggregate_type: str
    aggregate_id: str
    event_type: str
    payload: dict
    created_at: datetime
    published: bool = False
    published_at: datetime | None = None


class TransactionalOutbox:
    """Write events to outbox table in same transaction as data.

    Guarantees: data change and event are atomic.
    Background relay publishes events to message broker.
    """

    def __init__(self, db_pool, message_broker):
        self.db = db_pool
        self.broker = message_broker

    async def save_with_event(self, sql: str, params: tuple,
                               event: OutboxEvent):
        """Atomically save data and outbox event."""
        async with self.db.acquire() as conn:
            async with conn.transaction():
                await conn.execute(sql, *params)
                await conn.execute(
                    """INSERT INTO outbox (id, aggregate_type, aggregate_id,
                       event_type, payload, created_at, published)
                       VALUES ($1, $2, $3, $4, $5, $6, false)""",
                    event.id, event.aggregate_type, event.aggregate_id,
                    event.event_type, json.dumps(event.payload),
                    event.created_at,
                )

    async def relay_events(self, batch_size: int = 100):
        """Background job: publish unpublished events to broker."""
        async with self.db.acquire() as conn:
            rows = await conn.fetch(
                """SELECT * FROM outbox WHERE published = false
                   ORDER BY created_at LIMIT $1 FOR UPDATE SKIP LOCKED""",
                batch_size,
            )

            for row in rows:
                try:
                    await self.broker.publish(
                        topic=f"{row['aggregate_type']}.{row['event_type']}",
                        message=json.loads(row["payload"]),
                        headers={"event_id": row["id"]},
                    )
                    await conn.execute(
                        """UPDATE outbox SET published = true,
                           published_at = $1 WHERE id = $2""",
                        datetime.utcnow(), row["id"],
                    )
                except Exception as e:
                    # Will be retried on next relay cycle
                    pass

    async def start_relay_loop(self, interval: float = 1.0):
        """Continuously relay unpublished events."""
        while True:
            await self.relay_events()
            await asyncio.sleep(interval)

    async def cleanup_old_events(self, days: int = 7):
        """Delete old published events."""
        async with self.db.acquire() as conn:
            await conn.execute(
                """DELETE FROM outbox WHERE published = true
                   AND published_at < NOW() - INTERVAL '$1 days'""",
                days,
            )
```

Key patterns:
1. **Atomic write** — data + event in same DB transaction; guaranteed consistency
2. **FOR UPDATE SKIP LOCKED** — multiple relay workers without double-publishing
3. **At-least-once delivery** — relay retries until published; consumers must be idempotent
4. **Background relay** — polling loop publishes events to broker; decoupled from request
5. **Cleanup** — delete old published events to prevent outbox table growth'''
    ),
]
"""
