"""Temporal workflow engine — workflow/activity definitions, saga compensation, child workflows, worker deployment."""

PAIRS = [
    (
        "distributed/temporal-workflow-activities",
        "Show Temporal workflow and activity definitions in Python with proper error handling, retries, timeouts, and type-safe data classes.",
        '''Temporal workflow and activity definitions in Python:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Any

from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError


# ── Data classes for type-safe inputs/outputs ─────────────────────

@dataclass
class OrderRequest:
    order_id: str
    customer_id: str
    items: list[OrderItem]
    shipping_address: str
    payment_method_id: str


@dataclass
class OrderItem:
    product_id: str
    quantity: int
    unit_price: float


@dataclass
class OrderResult:
    order_id: str
    status: str
    tracking_number: str | None = None
    total_charged: float = 0.0
    error_message: str | None = None


@dataclass
class PaymentResult:
    transaction_id: str
    amount: float
    status: str


@dataclass
class InventoryReservation:
    reservation_id: str
    items: list[OrderItem]
    expires_at: str


class OrderStatus(str, Enum):
    PENDING = "pending"
    PAYMENT_PROCESSING = "payment_processing"
    INVENTORY_RESERVED = "inventory_reserved"
    SHIPPING = "shipping"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ── Activities (the actual work) ──────────────────────────────────

@activity.defn
async def validate_order(request: OrderRequest) -> bool:
    """Validate order data and customer eligibility."""
    activity.logger.info(f"Validating order {request.order_id}")

    if not request.items:
        raise ApplicationError(
            "Order must have at least one item",
            type="VALIDATION_ERROR",
            non_retryable=True,  # don't retry validation errors
        )

    if not request.shipping_address:
        raise ApplicationError(
            "Shipping address required",
            type="VALIDATION_ERROR",
            non_retryable=True,
        )

    # Simulate async API call
    await asyncio.sleep(0.1)
    return True


@activity.defn
async def reserve_inventory(request: OrderRequest) -> InventoryReservation:
    """Reserve inventory for order items."""
    activity.logger.info(
        f"Reserving inventory for {len(request.items)} items"
    )

    # Heartbeat for long-running activities
    for i, item in enumerate(request.items):
        activity.heartbeat(f"Reserving item {i + 1}/{len(request.items)}")
        await asyncio.sleep(0.05)  # simulate API call per item

    return InventoryReservation(
        reservation_id=f"res-{request.order_id}",
        items=request.items,
        expires_at="2025-12-31T23:59:59Z",
    )


@activity.defn
async def process_payment(
    customer_id: str,
    payment_method_id: str,
    amount: float,
) -> PaymentResult:
    """Charge the customer's payment method."""
    activity.logger.info(
        f"Processing payment of ${amount:.2f} for customer {customer_id}"
    )

    await asyncio.sleep(0.2)  # simulate payment gateway

    if amount > 10000:
        raise ApplicationError(
            "Amount exceeds single transaction limit",
            type="PAYMENT_LIMIT_EXCEEDED",
            non_retryable=True,
        )

    return PaymentResult(
        transaction_id=f"txn-{customer_id}-{int(amount)}",
        amount=amount,
        status="charged",
    )


@activity.defn
async def create_shipment(
    order_id: str,
    address: str,
    items: list[OrderItem],
) -> str:
    """Create shipping label and schedule pickup."""
    activity.logger.info(f"Creating shipment for order {order_id}")
    await asyncio.sleep(0.1)
    return f"TRACK-{order_id.upper()}"


@activity.defn
async def send_notification(
    customer_id: str,
    template: str,
    data: dict[str, Any],
) -> None:
    """Send email/SMS notification — fire and forget."""
    activity.logger.info(
        f"Sending {template} notification to {customer_id}"
    )
    await asyncio.sleep(0.05)
```

```python
# ── Workflow definition ───────────────────────────────────────────

@workflow.defn
class OrderWorkflow:
    """Orchestrates the full order fulfillment process.

    Workflow code must be deterministic — no I/O, no random,
    no datetime.now(). All side effects happen in activities.
    """

    def __init__(self) -> None:
        self._status = OrderStatus.PENDING
        self._cancel_requested = False

    @workflow.run
    async def run(self, request: OrderRequest) -> OrderResult:
        workflow.logger.info(f"Starting order workflow: {request.order_id}")

        # ── Step 1: Validate ──────────────────────────────────
        try:
            await workflow.execute_activity(
                validate_order,
                request,
                start_to_close_timeout=timedelta(seconds=10),
                retry_policy=RetryPolicy(maximum_attempts=1),
            )
        except ApplicationError as e:
            return OrderResult(
                order_id=request.order_id,
                status="failed",
                error_message=str(e),
            )

        # ── Step 2: Reserve inventory ─────────────────────────
        self._status = OrderStatus.INVENTORY_RESERVED
        reservation = await workflow.execute_activity(
            reserve_inventory,
            request,
            start_to_close_timeout=timedelta(seconds=30),
            heartbeat_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                maximum_interval=timedelta(seconds=30),
                backoff_coefficient=2.0,
                maximum_attempts=3,
            ),
        )

        # Check for cancellation between steps
        if self._cancel_requested:
            return OrderResult(
                order_id=request.order_id,
                status="cancelled",
            )

        # ── Step 3: Process payment ───────────────────────────
        self._status = OrderStatus.PAYMENT_PROCESSING
        total = sum(i.quantity * i.unit_price for i in request.items)

        payment = await workflow.execute_activity(
            process_payment,
            args=[request.customer_id, request.payment_method_id, total],
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=RetryPolicy(
                maximum_attempts=3,
                non_retryable_error_types=["PAYMENT_LIMIT_EXCEEDED"],
            ),
        )

        # ── Step 4: Create shipment ───────────────────────────
        self._status = OrderStatus.SHIPPING
        tracking = await workflow.execute_activity(
            create_shipment,
            args=[request.order_id, request.shipping_address, request.items],
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=RetryPolicy(maximum_attempts=5),
        )

        # ── Step 5: Notify (fire and forget) ──────────────────
        self._status = OrderStatus.COMPLETED
        await workflow.execute_activity(
            send_notification,
            args=[
                request.customer_id,
                "order_confirmed",
                {"order_id": request.order_id, "tracking": tracking},
            ],
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(maximum_attempts=2),
        )

        return OrderResult(
            order_id=request.order_id,
            status="completed",
            tracking_number=tracking,
            total_charged=payment.amount,
        )

    # ── Query: check current status ───────────────────────────
    @workflow.query
    def get_status(self) -> str:
        return self._status.value

    # ── Signal: request cancellation ──────────────────────────
    @workflow.signal
    async def cancel_order(self) -> None:
        self._cancel_requested = True
```

```python
# ── Worker setup and client usage ─────────────────────────────────

import asyncio
from temporalio.client import Client
from temporalio.worker import Worker


async def run_worker() -> None:
    """Start a Temporal worker that processes workflows and activities."""
    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue="order-processing",
        workflows=[OrderWorkflow],
        activities=[
            validate_order,
            reserve_inventory,
            process_payment,
            create_shipment,
            send_notification,
        ],
        max_concurrent_activities=20,
        max_concurrent_workflow_tasks=10,
    )

    print("Worker started on task queue: order-processing")
    await worker.run()


async def start_order(order_request: OrderRequest) -> OrderResult:
    """Client: start an order workflow and wait for result."""
    client = await Client.connect("localhost:7233")

    # Start workflow with a unique ID (idempotent)
    handle = await client.start_workflow(
        OrderWorkflow.run,
        order_request,
        id=f"order-{order_request.order_id}",
        task_queue="order-processing",
        execution_timeout=timedelta(hours=1),
    )

    print(f"Workflow started: {handle.id}")

    # Query status while running
    status = await handle.query(OrderWorkflow.get_status)
    print(f"Current status: {status}")

    # Wait for result
    result = await handle.result()
    return result


async def cancel_order(order_id: str) -> None:
    """Client: send cancellation signal to running workflow."""
    client = await Client.connect("localhost:7233")
    handle = client.get_workflow_handle(f"order-{order_id}")
    await handle.signal(OrderWorkflow.cancel_order)


# ── Entry point ──────────────────────────────────────────────────

if __name__ == "__main__":
    asyncio.run(run_worker())
```

| Concept | Purpose | Key Setting |
|---|---|---|
| Activity | Executes side effects (I/O, APIs) | `start_to_close_timeout` |
| Workflow | Orchestrates activities (deterministic) | `execution_timeout` |
| `RetryPolicy` | Automatic retry with backoff | `maximum_attempts`, `backoff_coefficient` |
| `heartbeat` | Detect stuck activities | `heartbeat_timeout` |
| Query | Read workflow state without mutation | Synchronous, returns current value |
| Signal | Send data to running workflow | Async, triggers state change |
| Task Queue | Routes work to specific workers | Named queue per service |

Key patterns:
1. Workflow code must be **deterministic** -- no I/O, no `datetime.now()`, no `random`.
2. All side effects go in `@activity.defn` functions -- they run on workers.
3. Use `non_retryable=True` on `ApplicationError` for validation / business logic errors.
4. `heartbeat_timeout` detects stuck activities (e.g., hanging HTTP calls).
5. Queries let external systems poll workflow state without signals.
6. Workflow ID should be business-meaningful (e.g., `order-{order_id}`) for idempotency.'''
    ),
    (
        "distributed/temporal-saga-compensation",
        "Show the saga pattern with Temporal: compensation activities, rollback on failure, and guaranteed cleanup for distributed transactions.",
        '''Temporal saga pattern with compensation activities:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError


# ── Data classes ──────────────────────────────────────────────────

@dataclass
class TripBookingRequest:
    trip_id: str
    customer_id: str
    flight: FlightRequest
    hotel: HotelRequest
    car: CarRentalRequest


@dataclass
class FlightRequest:
    origin: str
    destination: str
    departure: str
    return_date: str
    passengers: int


@dataclass
class HotelRequest:
    city: str
    check_in: str
    check_out: str
    rooms: int


@dataclass
class CarRentalRequest:
    city: str
    pickup: str
    return_date: str
    car_class: str


@dataclass
class BookingResult:
    trip_id: str
    status: str
    flight_confirmation: str | None = None
    hotel_confirmation: str | None = None
    car_confirmation: str | None = None
    compensations_executed: list[str] = field(default_factory=list)
    error: str | None = None


# ── Forward activities (book) ─────────────────────────────────────

@activity.defn
async def book_flight(req: FlightRequest) -> str:
    activity.logger.info(
        f"Booking flight {req.origin} -> {req.destination}"
    )
    await asyncio.sleep(0.2)
    # Simulate occasional failure
    return f"FL-{req.origin}-{req.destination}-CONF"


@activity.defn
async def book_hotel(req: HotelRequest) -> str:
    activity.logger.info(
        f"Booking hotel in {req.city}: {req.rooms} rooms"
    )
    await asyncio.sleep(0.2)
    return f"HTL-{req.city}-CONF"


@activity.defn
async def book_car(req: CarRentalRequest) -> str:
    activity.logger.info(
        f"Booking {req.car_class} car in {req.city}"
    )
    await asyncio.sleep(0.2)
    return f"CAR-{req.city}-CONF"


# ── Compensation activities (cancel / rollback) ──────────────────

@activity.defn
async def cancel_flight(confirmation: str) -> None:
    activity.logger.info(f"COMPENSATING: Cancelling flight {confirmation}")
    await asyncio.sleep(0.1)


@activity.defn
async def cancel_hotel(confirmation: str) -> None:
    activity.logger.info(f"COMPENSATING: Cancelling hotel {confirmation}")
    await asyncio.sleep(0.1)


@activity.defn
async def cancel_car(confirmation: str) -> None:
    activity.logger.info(f"COMPENSATING: Cancelling car {confirmation}")
    await asyncio.sleep(0.1)


@activity.defn
async def refund_payment(
    customer_id: str, amount: float, reason: str
) -> None:
    activity.logger.info(
        f"COMPENSATING: Refunding ${amount:.2f} to {customer_id}: {reason}"
    )
    await asyncio.sleep(0.1)
```

```python
# ── Saga helper class ────────────────────────────────────────────

from typing import Callable, Coroutine


@dataclass
class CompensationStep:
    """A recorded compensation action to run on rollback."""
    name: str
    activity_fn: Any
    args: list[Any]


class SagaContext:
    """Tracks compensation actions for automatic rollback."""

    def __init__(self) -> None:
        self._compensations: list[CompensationStep] = []
        self._executed: list[str] = []

    def add_compensation(
        self,
        name: str,
        activity_fn: Any,
        *args: Any,
    ) -> None:
        """Register a compensation to run if saga fails."""
        self._compensations.append(
            CompensationStep(name=name, activity_fn=activity_fn, args=list(args))
        )

    async def compensate(self) -> list[str]:
        """Execute all compensations in REVERSE order (LIFO).
        Each compensation runs even if previous ones fail."""
        errors: list[str] = []
        # Reverse order: last booked = first cancelled
        for step in reversed(self._compensations):
            try:
                workflow.logger.info(f"Running compensation: {step.name}")
                await workflow.execute_activity(
                    step.activity_fn,
                    args=step.args,
                    start_to_close_timeout=timedelta(seconds=30),
                    retry_policy=RetryPolicy(
                        maximum_attempts=5,
                        initial_interval=timedelta(seconds=2),
                        backoff_coefficient=2.0,
                    ),
                )
                self._executed.append(step.name)
            except Exception as e:
                # Log but continue — must attempt all compensations
                errors.append(f"{step.name}: {e}")
                workflow.logger.error(
                    f"Compensation {step.name} failed: {e}"
                )

        if errors:
            workflow.logger.error(
                f"Some compensations failed: {errors}"
            )

        return self._executed


# ── Saga workflow ─────────────────────────────────────────────────

ACTIVITY_TIMEOUT = timedelta(seconds=60)
RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    maximum_interval=timedelta(seconds=30),
    backoff_coefficient=2.0,
    maximum_attempts=3,
)


@workflow.defn
class TripBookingWorkflow:
    """Saga workflow: book flight + hotel + car, compensate on failure."""

    @workflow.run
    async def run(self, request: TripBookingRequest) -> BookingResult:
        saga = SagaContext()
        result = BookingResult(trip_id=request.trip_id, status="pending")

        try:
            # ── Step 1: Book flight ───────────────────────────
            flight_conf = await workflow.execute_activity(
                book_flight,
                request.flight,
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=RETRY,
            )
            result.flight_confirmation = flight_conf
            saga.add_compensation("cancel_flight", cancel_flight, flight_conf)

            # ── Step 2: Book hotel ────────────────────────────
            hotel_conf = await workflow.execute_activity(
                book_hotel,
                request.hotel,
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=RETRY,
            )
            result.hotel_confirmation = hotel_conf
            saga.add_compensation("cancel_hotel", cancel_hotel, hotel_conf)

            # ── Step 3: Book car ──────────────────────────────
            car_conf = await workflow.execute_activity(
                book_car,
                request.car,
                start_to_close_timeout=ACTIVITY_TIMEOUT,
                retry_policy=RETRY,
            )
            result.car_confirmation = car_conf
            saga.add_compensation("cancel_car", cancel_car, car_conf)

            # All steps succeeded
            result.status = "confirmed"
            return result

        except Exception as e:
            # Saga failed — run compensations in reverse order
            workflow.logger.error(f"Saga failed at step: {e}")
            result.status = "compensated"
            result.error = str(e)
            result.compensations_executed = await saga.compensate()
            return result
```

```python
# ── Testing saga compensation ─────────────────────────────────────

import pytest
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker


@pytest.mark.asyncio
async def test_saga_happy_path() -> None:
    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-trips",
            workflows=[TripBookingWorkflow],
            activities=[
                book_flight, book_hotel, book_car,
                cancel_flight, cancel_hotel, cancel_car,
            ],
        ):
            request = TripBookingRequest(
                trip_id="trip-001",
                customer_id="cust-42",
                flight=FlightRequest("SFO", "JFK", "2025-06-01", "2025-06-08", 2),
                hotel=HotelRequest("New York", "2025-06-01", "2025-06-08", 1),
                car=CarRentalRequest("New York", "2025-06-01", "2025-06-08", "sedan"),
            )

            result = await env.client.execute_workflow(
                TripBookingWorkflow.run,
                request,
                id="test-trip-001",
                task_queue="test-trips",
            )

            assert result.status == "confirmed"
            assert result.flight_confirmation is not None
            assert result.hotel_confirmation is not None
            assert result.car_confirmation is not None
            assert result.compensations_executed == []


@pytest.mark.asyncio
async def test_saga_compensation_on_failure() -> None:
    """Test that compensations run when a step fails."""

    @activity.defn(name="book_car")
    async def book_car_fails(req: CarRentalRequest) -> str:
        raise ApplicationError("No cars available", non_retryable=True)

    async with await WorkflowEnvironment.start_time_skipping() as env:
        async with Worker(
            env.client,
            task_queue="test-trips",
            workflows=[TripBookingWorkflow],
            activities=[
                book_flight, book_hotel, book_car_fails,
                cancel_flight, cancel_hotel, cancel_car,
            ],
        ):
            request = TripBookingRequest(
                trip_id="trip-002",
                customer_id="cust-42",
                flight=FlightRequest("SFO", "JFK", "2025-06-01", "2025-06-08", 2),
                hotel=HotelRequest("New York", "2025-06-01", "2025-06-08", 1),
                car=CarRentalRequest("New York", "2025-06-01", "2025-06-08", "sedan"),
            )

            result = await env.client.execute_workflow(
                TripBookingWorkflow.run,
                request,
                id="test-trip-002",
                task_queue="test-trips",
            )

            assert result.status == "compensated"
            # Compensations run in reverse: hotel first, then flight
            assert "cancel_hotel" in result.compensations_executed
            assert "cancel_flight" in result.compensations_executed
```

| Saga Aspect | Implementation | Why |
|---|---|---|
| Compensation order | LIFO (reverse) | Last booked = first cancelled |
| Compensation retry | Aggressive (5 attempts) | Must succeed to maintain consistency |
| Compensation failure | Log + continue | Try all compensations even if one fails |
| Non-retryable errors | `non_retryable=True` | Don't retry business logic failures |
| Idempotency | Unique workflow ID | Prevents duplicate bookings |
| Observability | `workflow.logger` | Structured logging with workflow context |

Key patterns:
1. Register compensations **immediately after** each successful forward step.
2. Compensations run in **reverse order** (LIFO) -- last resource acquired is first released.
3. Each compensation has **aggressive retries** -- it must eventually succeed.
4. If a compensation fails, **continue** with remaining compensations -- don't short-circuit.
5. Use `non_retryable=True` for business-rule failures that retries cannot fix.
6. The `SagaContext` helper is reusable across any saga workflow.'''
    ),
    (
        "distributed/temporal-child-workflows-signals",
        "Show Temporal child workflows and signals for complex orchestration: parent-child relationships, signal channels, and workflow-to-workflow communication.",
        '''Temporal child workflows and signals:

```python
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from temporalio import activity, workflow
from temporalio.common import RetryPolicy
from temporalio.workflow import (
    ChildWorkflowHandle,
    ParentClosePolicy,
)


# ── Data classes ──────────────────────────────────────────────────

@dataclass
class BatchProcessRequest:
    batch_id: str
    items: list[str]
    max_concurrent: int = 5
    notify_email: str = ""


@dataclass
class ItemResult:
    item_id: str
    status: str
    output: str | None = None
    error: str | None = None


@dataclass
class BatchResult:
    batch_id: str
    total: int
    succeeded: int
    failed: int
    results: list[ItemResult] = field(default_factory=list)


@dataclass
class ApprovalRequest:
    workflow_id: str
    item_id: str
    description: str
    requested_by: str


# ── Child workflow: processes a single item ───────────────────────

@activity.defn
async def process_item(item_id: str) -> str:
    """Simulate processing a single item."""
    activity.logger.info(f"Processing item: {item_id}")
    await asyncio.sleep(0.1)

    if "error" in item_id:
        raise Exception(f"Failed to process {item_id}")

    return f"result-for-{item_id}"


@activity.defn
async def send_batch_notification(
    email: str, batch_id: str, summary: dict[str, Any]
) -> None:
    activity.logger.info(f"Notifying {email} about batch {batch_id}")
    await asyncio.sleep(0.05)


@workflow.defn
class ItemProcessingWorkflow:
    """Child workflow that processes a single item with approval gate."""

    def __init__(self) -> None:
        self._approved: bool | None = None

    @workflow.run
    async def run(self, item_id: str, needs_approval: bool = False) -> ItemResult:
        # If approval is needed, wait for signal
        if needs_approval:
            workflow.logger.info(f"Item {item_id} waiting for approval")

            # Wait up to 24 hours for approval signal
            try:
                await workflow.wait_condition(
                    lambda: self._approved is not None,
                    timeout=timedelta(hours=24),
                )
            except asyncio.TimeoutError:
                return ItemResult(
                    item_id=item_id,
                    status="timeout",
                    error="Approval timed out after 24 hours",
                )

            if not self._approved:
                return ItemResult(
                    item_id=item_id,
                    status="rejected",
                    error="Item was rejected",
                )

        # Process the item
        try:
            output = await workflow.execute_activity(
                process_item,
                item_id,
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=RetryPolicy(maximum_attempts=3),
            )
            return ItemResult(
                item_id=item_id, status="completed", output=output
            )
        except Exception as e:
            return ItemResult(
                item_id=item_id, status="failed", error=str(e)
            )

    @workflow.signal
    async def approve(self) -> None:
        self._approved = True

    @workflow.signal
    async def reject(self) -> None:
        self._approved = False

    @workflow.query
    def approval_status(self) -> str:
        if self._approved is None:
            return "pending"
        return "approved" if self._approved else "rejected"
```

```python
# ── Parent workflow: orchestrates batch with child workflows ──────

@workflow.defn
class BatchProcessingWorkflow:
    """Parent workflow that fans out to child workflows."""

    def __init__(self) -> None:
        self._completed = 0
        self._total = 0
        self._pause_requested = False
        self._cancel_requested = False

    @workflow.run
    async def run(self, request: BatchProcessRequest) -> BatchResult:
        self._total = len(request.items)
        results: list[ItemResult] = []

        workflow.logger.info(
            f"Starting batch {request.batch_id} with {self._total} items, "
            f"max_concurrent={request.max_concurrent}"
        )

        # Process items in batches for concurrency control
        semaphore_count = 0
        pending_handles: list[tuple[str, ChildWorkflowHandle]] = []
        all_items = list(request.items)

        # Fan out child workflows with concurrency limit
        for i in range(0, len(all_items), request.max_concurrent):
            if self._cancel_requested:
                break

            # Wait if paused
            while self._pause_requested:
                await workflow.wait_condition(
                    lambda: not self._pause_requested,
                    timeout=timedelta(minutes=5),
                )

            chunk = all_items[i : i + request.max_concurrent]
            handles: list[tuple[str, ChildWorkflowHandle]] = []

            # Start child workflows in parallel
            for item_id in chunk:
                needs_approval = item_id.startswith("review-")

                handle = await workflow.start_child_workflow(
                    ItemProcessingWorkflow.run,
                    args=[item_id, needs_approval],
                    id=f"item-{request.batch_id}-{item_id}",
                    parent_close_policy=ParentClosePolicy.TERMINATE,
                    execution_timeout=timedelta(hours=25),
                    retry_policy=RetryPolicy(maximum_attempts=1),
                )
                handles.append((item_id, handle))

            # Wait for all children in this chunk
            for item_id, handle in handles:
                try:
                    result = await handle
                    results.append(result)
                except Exception as e:
                    results.append(ItemResult(
                        item_id=item_id,
                        status="failed",
                        error=str(e),
                    ))
                self._completed += 1

        # Send completion notification
        if request.notify_email:
            succeeded = sum(1 for r in results if r.status == "completed")
            failed = sum(1 for r in results if r.status != "completed")
            await workflow.execute_activity(
                send_batch_notification,
                args=[
                    request.notify_email,
                    request.batch_id,
                    {"succeeded": succeeded, "failed": failed, "total": self._total},
                ],
                start_to_close_timeout=timedelta(seconds=30),
            )

        succeeded = sum(1 for r in results if r.status == "completed")
        failed = len(results) - succeeded

        return BatchResult(
            batch_id=request.batch_id,
            total=self._total,
            succeeded=succeeded,
            failed=failed,
            results=results,
        )

    @workflow.signal
    async def pause(self) -> None:
        self._pause_requested = True
        workflow.logger.info("Batch processing paused")

    @workflow.signal
    async def resume(self) -> None:
        self._pause_requested = False
        workflow.logger.info("Batch processing resumed")

    @workflow.signal
    async def cancel_batch(self) -> None:
        self._cancel_requested = True
        workflow.logger.info("Batch cancellation requested")

    @workflow.query
    def progress(self) -> dict[str, Any]:
        return {
            "completed": self._completed,
            "total": self._total,
            "paused": self._pause_requested,
            "cancelled": self._cancel_requested,
            "percent": round(self._completed / max(self._total, 1) * 100, 1),
        }
```

```python
# ── Client usage: signals and queries ─────────────────────────────

from temporalio.client import Client


async def demo_batch_with_signals() -> None:
    client = await Client.connect("localhost:7233")

    # Start batch
    request = BatchProcessRequest(
        batch_id="batch-001",
        items=["item-1", "review-item-2", "item-3", "item-4", "review-item-5"],
        max_concurrent=3,
        notify_email="admin@example.com",
    )

    handle = await client.start_workflow(
        BatchProcessingWorkflow.run,
        request,
        id=f"batch-{request.batch_id}",
        task_queue="batch-processing",
    )

    # Poll progress
    for _ in range(10):
        progress = await handle.query(BatchProcessingWorkflow.progress)
        print(f"Progress: {progress['percent']}%")
        if progress["completed"] == progress["total"]:
            break
        await asyncio.sleep(1)

    # Approve a child workflow that's waiting
    child_handle = client.get_workflow_handle(
        f"item-batch-001-review-item-2"
    )
    await child_handle.signal(ItemProcessingWorkflow.approve)

    # Pause / resume the batch
    await handle.signal(BatchProcessingWorkflow.pause)
    await asyncio.sleep(2)
    await handle.signal(BatchProcessingWorkflow.resume)

    # Wait for final result
    result = await handle.result()
    print(f"Batch complete: {result.succeeded}/{result.total} succeeded")


# ── Worker with all workflows and activities ──────────────────────

from temporalio.worker import Worker


async def run_worker() -> None:
    client = await Client.connect("localhost:7233")

    worker = Worker(
        client,
        task_queue="batch-processing",
        workflows=[
            BatchProcessingWorkflow,
            ItemProcessingWorkflow,
        ],
        activities=[
            process_item,
            send_batch_notification,
        ],
        max_concurrent_workflow_tasks=20,
        max_concurrent_activities=50,
    )
    await worker.run()
```

| Feature | Mechanism | Use Case |
|---|---|---|
| Child workflow | `start_child_workflow()` | Fan-out, sub-orchestration |
| `ParentClosePolicy.TERMINATE` | Auto-cancel children if parent ends | Clean shutdown |
| `ParentClosePolicy.ABANDON` | Children continue independently | Fire-and-forget children |
| Signal | `@workflow.signal` | External input (approve, pause) |
| Query | `@workflow.query` | Read state without mutation |
| `wait_condition` | Block until predicate is true | Wait for signal + timeout |
| Concurrency control | Chunk + await pattern | Limit parallel children |

Key patterns:
1. Child workflows get their own history, retry, and timeout -- independent of parent.
2. `ParentClosePolicy.TERMINATE` ensures children don't orphan if parent is cancelled.
3. Use `wait_condition(lambda, timeout)` for approval gates with deadlines.
4. Signals enable pause/resume/cancel for long-running batch workflows.
5. Queries let UIs poll progress without sending signals.
6. Fan-out with concurrency limits: chunk items and await each batch of children.'''
    ),
    (
        "distributed/temporal-worker-deployment",
        "Show Temporal worker deployment and scaling: Docker containerization, Kubernetes deployment, health checks, and worker configuration best practices.",
        '''Temporal worker deployment and scaling:

```python
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from datetime import timedelta
from typing import Any

from temporalio.client import Client, TLSConfig
from temporalio.runtime import (
    PrometheusConfig,
    Runtime,
    TelemetryConfig,
)
from temporalio.worker import Worker


# ── Worker configuration ──────────────────────────────────────────

class WorkerConfig:
    """Worker configuration from environment variables."""

    def __init__(self) -> None:
        self.temporal_host: str = os.getenv(
            "TEMPORAL_HOST", "localhost:7233"
        )
        self.temporal_namespace: str = os.getenv(
            "TEMPORAL_NAMESPACE", "default"
        )
        self.task_queue: str = os.getenv(
            "TEMPORAL_TASK_QUEUE", "default-queue"
        )

        # TLS for Temporal Cloud
        self.tls_cert_path: str | None = os.getenv("TEMPORAL_TLS_CERT")
        self.tls_key_path: str | None = os.getenv("TEMPORAL_TLS_KEY")

        # Worker tuning
        self.max_concurrent_activities: int = int(
            os.getenv("WORKER_MAX_ACTIVITIES", "100")
        )
        self.max_concurrent_workflow_tasks: int = int(
            os.getenv("WORKER_MAX_WORKFLOWS", "40")
        )
        self.max_cached_workflows: int = int(
            os.getenv("WORKER_CACHED_WORKFLOWS", "1000")
        )

        # Metrics
        self.metrics_port: int = int(
            os.getenv("METRICS_PORT", "9090")
        )
        self.enable_metrics: bool = os.getenv(
            "ENABLE_METRICS", "true"
        ).lower() == "true"

        # Graceful shutdown
        self.shutdown_grace_period: int = int(
            os.getenv("SHUTDOWN_GRACE_PERIOD", "30")
        )

    def get_tls_config(self) -> TLSConfig | None:
        if not self.tls_cert_path or not self.tls_key_path:
            return None
        with open(self.tls_cert_path, "rb") as f:
            cert = f.read()
        with open(self.tls_key_path, "rb") as f:
            key = f.read()
        return TLSConfig(client_cert=cert, client_private_key=key)


# ── Worker with graceful shutdown and metrics ─────────────────────

async def create_worker(config: WorkerConfig) -> tuple[Client, Worker]:
    """Create Temporal client and worker with production settings."""

    # Set up runtime with Prometheus metrics
    runtime = None
    if config.enable_metrics:
        runtime = Runtime(
            telemetry=TelemetryConfig(
                metrics=PrometheusConfig(
                    bind_address=f"0.0.0.0:{config.metrics_port}"
                )
            )
        )

    # Connect to Temporal
    client = await Client.connect(
        config.temporal_host,
        namespace=config.temporal_namespace,
        tls=config.get_tls_config() or False,
        runtime=runtime,
    )

    # Import workflows and activities
    from workflows.order import OrderWorkflow, ItemProcessingWorkflow
    from activities.order import (
        validate_order, reserve_inventory,
        process_payment, create_shipment,
        send_notification,
    )

    worker = Worker(
        client,
        task_queue=config.task_queue,
        workflows=[
            OrderWorkflow,
            ItemProcessingWorkflow,
        ],
        activities=[
            validate_order,
            reserve_inventory,
            process_payment,
            create_shipment,
            send_notification,
        ],
        max_concurrent_activities=config.max_concurrent_activities,
        max_concurrent_workflow_tasks=config.max_concurrent_workflow_tasks,
        max_cached_workflows=config.max_cached_workflows,
        # Sticky execution: keep workflow history in memory
        sticky_queue_schedule_to_start_timeout=timedelta(seconds=10),
    )

    return client, worker


async def run_worker_with_shutdown() -> None:
    """Run worker with graceful shutdown on SIGTERM/SIGINT."""
    config = WorkerConfig()
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger("temporal-worker")

    logger.info(
        f"Starting worker: queue={config.task_queue}, "
        f"activities={config.max_concurrent_activities}, "
        f"workflows={config.max_concurrent_workflow_tasks}"
    )

    client, worker = await create_worker(config)
    shutdown_event = asyncio.Event()

    def signal_handler(sig: int, frame: Any) -> None:
        logger.info(f"Received signal {sig}, shutting down gracefully...")
        shutdown_event.set()

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Run worker until shutdown signal
    worker_task = asyncio.create_task(worker.run())
    shutdown_task = asyncio.create_task(shutdown_event.wait())

    done, _ = await asyncio.wait(
        [worker_task, shutdown_task],
        return_when=asyncio.FIRST_COMPLETED,
    )

    if shutdown_event.is_set():
        logger.info("Initiating graceful shutdown...")
        await worker.shutdown()
        logger.info("Worker shut down successfully")


if __name__ == "__main__":
    asyncio.run(run_worker_with_shutdown())
```

```yaml
# ── Dockerfile ────────────────────────────────────────────────────

# Dockerfile
# FROM python:3.12-slim
#
# WORKDIR /app
#
# COPY requirements.txt .
# RUN pip install --no-cache-dir -r requirements.txt
#
# COPY . .
#
# # Non-root user
# RUN adduser --disabled-password --gecos '' worker
# USER worker
#
# # Health check endpoint
# HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
#   CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:9090/metrics')"
#
# ENTRYPOINT ["python", "-m", "worker.main"]

# ── Kubernetes deployment ─────────────────────────────────────────
# k8s/worker-deployment.yaml

apiVersion: apps/v1
kind: Deployment
metadata:
  name: temporal-worker
  labels:
    app: temporal-worker
spec:
  replicas: 3
  selector:
    matchLabels:
      app: temporal-worker
  template:
    metadata:
      labels:
        app: temporal-worker
      annotations:
        prometheus.io/scrape: "true"
        prometheus.io/port: "9090"
        prometheus.io/path: "/metrics"
    spec:
      terminationGracePeriodSeconds: 60
      containers:
        - name: worker
          image: myregistry/temporal-worker:latest
          resources:
            requests:
              cpu: "500m"
              memory: "512Mi"
            limits:
              cpu: "2000m"
              memory: "2Gi"
          env:
            - name: TEMPORAL_HOST
              value: "temporal.temporal.svc.cluster.local:7233"
            - name: TEMPORAL_NAMESPACE
              value: "production"
            - name: TEMPORAL_TASK_QUEUE
              value: "order-processing"
            - name: WORKER_MAX_ACTIVITIES
              value: "100"
            - name: WORKER_MAX_WORKFLOWS
              value: "40"
            - name: ENABLE_METRICS
              value: "true"
            - name: METRICS_PORT
              value: "9090"
            - name: SHUTDOWN_GRACE_PERIOD
              value: "30"
          envFrom:
            - secretRef:
                name: temporal-tls-creds
          ports:
            - containerPort: 9090
              name: metrics
          livenessProbe:
            httpGet:
              path: /metrics
              port: 9090
            initialDelaySeconds: 10
            periodSeconds: 30
          readinessProbe:
            httpGet:
              path: /metrics
              port: 9090
            initialDelaySeconds: 5
            periodSeconds: 10
```

```python
# ── Health check server (alongside worker) ────────────────────────

from aiohttp import web


class HealthServer:
    """Lightweight HTTP server for K8s health probes."""

    def __init__(self, port: int = 8080) -> None:
        self._port = port
        self._healthy = True
        self._ready = False

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/health", self._health_handler)
        app.router.add_get("/ready", self._ready_handler)

        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self._port)
        await site.start()

    async def _health_handler(self, request: web.Request) -> web.Response:
        if self._healthy:
            return web.json_response({"status": "healthy"})
        return web.json_response(
            {"status": "unhealthy"}, status=503
        )

    async def _ready_handler(self, request: web.Request) -> web.Response:
        if self._ready:
            return web.json_response({"status": "ready"})
        return web.json_response(
            {"status": "not_ready"}, status=503
        )

    def set_ready(self) -> None:
        self._ready = True

    def set_unhealthy(self) -> None:
        self._healthy = False


# ── HPA (Horizontal Pod Autoscaler) ──────────────────────────────

HPA_MANIFEST = """
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: temporal-worker-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: temporal-worker
  minReplicas: 2
  maxReplicas: 20
  metrics:
    # Scale based on Temporal schedule-to-start latency
    - type: Pods
      pods:
        metric:
          name: temporal_activity_schedule_to_start_latency
        target:
          type: AverageValue
          averageValue: "5000"  # 5 seconds
    # Also scale on CPU
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
  behavior:
    scaleUp:
      stabilizationWindowSeconds: 60
      policies:
        - type: Pods
          value: 4
          periodSeconds: 60
    scaleDown:
      stabilizationWindowSeconds: 300
      policies:
        - type: Pods
          value: 2
          periodSeconds: 120
"""
```

| Tuning Parameter | Default | Guidance |
|---|---|---|
| `max_concurrent_activities` | 100 | CPU-bound: 2x cores; I/O-bound: 100-500 |
| `max_concurrent_workflow_tasks` | 40 | Typically 40-100; workflows are lightweight |
| `max_cached_workflows` | 1000 | More cache = less history replay; uses memory |
| `sticky_queue_schedule_to_start_timeout` | 10s | Keep workflow pinned to same worker |
| Replicas (K8s) | 1 | 2+ for HA; scale on schedule-to-start latency |
| `terminationGracePeriodSeconds` | 30 | Must exceed longest activity timeout |

Key patterns:
1. Use `SIGTERM` handler for graceful shutdown -- let running activities finish.
2. `terminationGracePeriodSeconds` must exceed your shutdown grace period.
3. Scale workers horizontally -- Temporal distributes work via task queues.
4. HPA on `schedule_to_start_latency` scales when workers can't keep up.
5. Prometheus metrics endpoint (`/metrics`) doubles as K8s health check.
6. TLS config from environment for Temporal Cloud; mount certs as K8s secrets.'''
    ),
]
