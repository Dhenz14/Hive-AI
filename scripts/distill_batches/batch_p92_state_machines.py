"""State machines — finite state machines, statecharts, and workflow engines."""

PAIRS = [
    (
        "patterns/state-machine",
        "Show finite state machine patterns: transitions, guards, actions, and hierarchical states.",
        '''State machine patterns:

```python
from dataclasses import dataclass, field
from typing import Any, Callable
from enum import Enum, auto
import logging

logger = logging.getLogger(__name__)


# --- Simple FSM ---

class OrderState(Enum):
    DRAFT = auto()
    SUBMITTED = auto()
    CONFIRMED = auto()
    SHIPPED = auto()
    DELIVERED = auto()
    CANCELLED = auto()
    REFUNDED = auto()


@dataclass
class Transition:
    event: str
    source: OrderState
    target: OrderState
    guard: Callable[..., bool] | None = None  # Condition to allow transition
    action: Callable | None = None             # Side effect on transition


class StateMachine:
    """Event-driven finite state machine."""

    def __init__(self, initial: OrderState, transitions: list[Transition]):
        self.state = initial
        self._transitions: dict[tuple[OrderState, str], Transition] = {}
        self._on_enter: dict[OrderState, list[Callable]] = {}
        self._on_exit: dict[OrderState, list[Callable]] = {}

        for t in transitions:
            self._transitions[(t.source, t.event)] = t

    def on_enter(self, state: OrderState, callback: Callable):
        self._on_enter.setdefault(state, []).append(callback)

    def on_exit(self, state: OrderState, callback: Callable):
        self._on_exit.setdefault(state, []).append(callback)

    def can_transition(self, event: str, context: dict | None = None) -> bool:
        """Check if transition is allowed."""
        key = (self.state, event)
        transition = self._transitions.get(key)
        if not transition:
            return False
        if transition.guard and not transition.guard(context or {}):
            return False
        return True

    def send(self, event: str, context: dict | None = None) -> OrderState:
        """Process event and transition state."""
        ctx = context or {}
        key = (self.state, event)
        transition = self._transitions.get(key)

        if not transition:
            raise ValueError(
                f"No transition for event '{event}' in state {self.state.name}"
            )

        if transition.guard and not transition.guard(ctx):
            raise ValueError(
                f"Guard rejected transition {self.state.name} -> {transition.target.name}"
            )

        old_state = self.state
        logger.info(
            "Transition: %s -[%s]-> %s",
            old_state.name, event, transition.target.name,
        )

        # Execute exit actions
        for cb in self._on_exit.get(old_state, []):
            cb(ctx)

        # Execute transition action
        if transition.action:
            transition.action(ctx)

        # Update state
        self.state = transition.target

        # Execute entry actions
        for cb in self._on_enter.get(self.state, []):
            cb(ctx)

        return self.state

    def get_available_events(self) -> list[str]:
        """Get events valid in current state."""
        return [
            event for (state, event) in self._transitions
            if state == self.state
        ]


# --- Define order workflow ---

def has_payment(ctx: dict) -> bool:
    return ctx.get("payment_verified", False)

def has_stock(ctx: dict) -> bool:
    return ctx.get("in_stock", True)

def send_confirmation_email(ctx: dict):
    logger.info("Sending confirmation email to %s", ctx.get("email"))

def notify_warehouse(ctx: dict):
    logger.info("Notifying warehouse for order %s", ctx.get("order_id"))


order_transitions = [
    Transition("submit", OrderState.DRAFT, OrderState.SUBMITTED),
    Transition("confirm", OrderState.SUBMITTED, OrderState.CONFIRMED,
               guard=lambda ctx: has_payment(ctx) and has_stock(ctx),
               action=send_confirmation_email),
    Transition("ship", OrderState.CONFIRMED, OrderState.SHIPPED,
               action=notify_warehouse),
    Transition("deliver", OrderState.SHIPPED, OrderState.DELIVERED),
    Transition("cancel", OrderState.DRAFT, OrderState.CANCELLED),
    Transition("cancel", OrderState.SUBMITTED, OrderState.CANCELLED),
    Transition("cancel", OrderState.CONFIRMED, OrderState.CANCELLED),
    Transition("refund", OrderState.DELIVERED, OrderState.REFUNDED),
]

# Usage:
# sm = StateMachine(OrderState.DRAFT, order_transitions)
# sm.send("submit")
# sm.send("confirm", {"payment_verified": True, "in_stock": True})
# sm.send("ship", {"order_id": "ORD-123"})
# sm.get_available_events()  # ["deliver"]


# --- Persistent state machine ---

class PersistentStateMachine(StateMachine):
    """FSM with audit log and persistence."""

    def __init__(self, entity_id: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.entity_id = entity_id
        self.history: list[dict] = []

    def send(self, event: str, context: dict | None = None) -> OrderState:
        old_state = self.state
        import time
        new_state = super().send(event, context)

        self.history.append({
            "entity_id": self.entity_id,
            "from_state": old_state.name,
            "to_state": new_state.name,
            "event": event,
            "timestamp": time.time(),
            "context": context,
        })

        return new_state

    def to_dict(self) -> dict:
        return {
            "entity_id": self.entity_id,
            "current_state": self.state.name,
            "available_events": self.get_available_events(),
            "history": self.history,
        }
```

State machine patterns:
1. **Transition table** — explicit (source, event) → target mappings
2. **Guards** — boolean conditions that must pass for transition to fire
3. **Actions** — side effects executed on transition (emails, notifications)
4. **`on_enter`/`on_exit`** — hooks for state entry/exit behavior
5. **Audit history** — log every state change with timestamp and context'''
    ),
    (
        "patterns/workflow-engine",
        "Show workflow engine patterns: step definitions, parallel steps, compensating actions, and persistence.",
        '''Workflow engine patterns:

```python
from dataclasses import dataclass, field
from typing import Callable, Awaitable, Any
from enum import Enum, auto
import asyncio
import logging
import uuid
import time

logger = logging.getLogger(__name__)


class StepStatus(Enum):
    PENDING = auto()
    RUNNING = auto()
    COMPLETED = auto()
    FAILED = auto()
    COMPENSATED = auto()


@dataclass
class StepResult:
    status: StepStatus
    output: Any = None
    error: str | None = None


@dataclass
class WorkflowStep:
    name: str
    execute: Callable[..., Awaitable[Any]]
    compensate: Callable[..., Awaitable[None]] | None = None
    timeout: float = 30.0
    retries: int = 0


@dataclass
class ParallelSteps:
    """Group of steps that execute concurrently."""
    name: str
    steps: list[WorkflowStep]


@dataclass
class WorkflowContext:
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    data: dict = field(default_factory=dict)
    results: dict[str, StepResult] = field(default_factory=dict)
    started_at: float = field(default_factory=time.time)


class WorkflowEngine:
    """Execute multi-step workflows with compensation on failure."""

    async def run(
        self,
        steps: list[WorkflowStep | ParallelSteps],
        context: WorkflowContext | None = None,
    ) -> WorkflowContext:
        ctx = context or WorkflowContext()
        completed_steps: list[WorkflowStep] = []

        try:
            for step in steps:
                if isinstance(step, ParallelSteps):
                    await self._run_parallel(step, ctx)
                    completed_steps.extend(step.steps)
                else:
                    await self._run_step(step, ctx)
                    completed_steps.append(step)

            logger.info("Workflow %s completed successfully", ctx.workflow_id)

        except Exception as e:
            logger.error("Workflow %s failed at step: %s", ctx.workflow_id, e)
            # Compensate in reverse order
            await self._compensate(completed_steps, ctx)
            raise

        return ctx

    async def _run_step(self, step: WorkflowStep, ctx: WorkflowContext):
        """Execute a single step with timeout and retries."""
        last_error = None

        for attempt in range(step.retries + 1):
            try:
                logger.info("Executing step: %s (attempt %d)", step.name, attempt + 1)

                result = await asyncio.wait_for(
                    step.execute(ctx),
                    timeout=step.timeout,
                )

                ctx.results[step.name] = StepResult(
                    status=StepStatus.COMPLETED, output=result,
                )
                ctx.data[step.name] = result
                return

            except asyncio.TimeoutError:
                last_error = f"Step {step.name} timed out after {step.timeout}s"
                logger.warning(last_error)

            except Exception as e:
                last_error = str(e)
                logger.warning("Step %s attempt %d failed: %s",
                             step.name, attempt + 1, e)

                if attempt < step.retries:
                    await asyncio.sleep(2 ** attempt)

        ctx.results[step.name] = StepResult(
            status=StepStatus.FAILED, error=last_error,
        )
        raise RuntimeError(f"Step {step.name} failed: {last_error}")

    async def _run_parallel(self, parallel: ParallelSteps, ctx: WorkflowContext):
        """Execute steps concurrently."""
        logger.info("Executing parallel group: %s", parallel.name)

        async with asyncio.TaskGroup() as tg:
            for step in parallel.steps:
                tg.create_task(self._run_step(step, ctx))

    async def _compensate(self, steps: list[WorkflowStep], ctx: WorkflowContext):
        """Run compensating actions in reverse order."""
        for step in reversed(steps):
            if step.compensate and step.name in ctx.results:
                try:
                    logger.info("Compensating step: %s", step.name)
                    await step.compensate(ctx)
                    ctx.results[step.name] = StepResult(
                        status=StepStatus.COMPENSATED,
                    )
                except Exception as e:
                    logger.error("Compensation failed for %s: %s", step.name, e)


# --- Example: Order fulfillment workflow ---

async def reserve_inventory(ctx: WorkflowContext):
    order = ctx.data.get("order", {})
    # Reserve items in warehouse
    return {"reservation_id": "RES-001", "items": order.get("items", [])}

async def unreserve_inventory(ctx: WorkflowContext):
    res = ctx.results.get("reserve_inventory")
    if res and res.output:
        pass  # Cancel reservation

async def charge_payment(ctx: WorkflowContext):
    return {"payment_id": "PAY-001", "amount": 99.99}

async def refund_payment(ctx: WorkflowContext):
    res = ctx.results.get("charge_payment")
    if res and res.output:
        pass  # Issue refund

async def create_shipment(ctx: WorkflowContext):
    return {"tracking_number": "TRK-001"}

async def send_notifications(ctx: WorkflowContext):
    return {"email_sent": True, "sms_sent": True}


order_workflow = [
    WorkflowStep("reserve_inventory", reserve_inventory,
                 compensate=unreserve_inventory, retries=2),
    WorkflowStep("charge_payment", charge_payment,
                 compensate=refund_payment, timeout=15.0),
    WorkflowStep("create_shipment", create_shipment, retries=1),
    ParallelSteps("notifications", [
        WorkflowStep("send_email", send_notifications),
        WorkflowStep("send_sms", send_notifications),
    ]),
]

# engine = WorkflowEngine()
# ctx = WorkflowContext(data={"order": {"items": ["item-1"], "total": 99.99}})
# result = await engine.run(order_workflow, ctx)
```

Workflow engine patterns:
1. **Step definitions** — execute + compensate + timeout + retries per step
2. **Compensating actions** — auto-rollback in reverse order on failure
3. **Parallel steps** — TaskGroup for concurrent step execution
4. **Context passing** — shared data dict flows through all steps
5. **Audit trail** — results dict tracks status/output of every step'''
    ),
]
"""
