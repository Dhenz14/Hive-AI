"""Concurrency patterns — async/await deep dive, actor model, CSP channels, lock-free structures, parallel algorithms."""

PAIRS = [
    (
        "concurrency/async-await-deep-dive",
        "Show a deep dive into async/await patterns in Python and TypeScript including structured concurrency, cancellation, backpressure, and error propagation with production-grade task groups.",
        '''Deep dive into async/await with structured concurrency and backpressure:

```python
"""Structured concurrency, cancellation, and backpressure patterns."""

import asyncio
import signal
import time
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

T = TypeVar("T")
R = TypeVar("R")


# ============================================================
# 1. Structured concurrency with TaskGroup + cancellation
# ============================================================

@dataclass
class WorkResult(Generic[T]):
    value: T | None = None
    error: Exception | None = None
    elapsed_ms: float = 0.0

    @property
    def ok(self) -> bool:
        return self.error is None


async def fetch_with_timeout(
    url: str, timeout: float = 10.0
) -> WorkResult[dict]:
    """Fetch URL with per-task timeout and structured error capture."""
    start = time.monotonic()
    try:
        async with asyncio.timeout(timeout):
            # Simulated HTTP fetch
            await asyncio.sleep(0.1)
            return WorkResult(
                value={"url": url, "status": 200},
                elapsed_ms=(time.monotonic() - start) * 1000,
            )
    except TimeoutError:
        return WorkResult(
            error=TimeoutError(f"Timeout after {timeout}s for {url}"),
            elapsed_ms=(time.monotonic() - start) * 1000,
        )
    except Exception as exc:
        return WorkResult(
            error=exc,
            elapsed_ms=(time.monotonic() - start) * 1000,
        )


async def fetch_all_structured(urls: list[str]) -> list[WorkResult[dict]]:
    """Fetch multiple URLs with structured concurrency.

    If any critical fetch fails, cancels remaining tasks.
    Non-critical failures are captured but don't cancel siblings.
    """
    results: list[WorkResult[dict]] = [WorkResult() for _ in urls]

    async with asyncio.TaskGroup() as tg:
        for i, url in enumerate(urls):

            async def _fetch(idx: int, u: str) -> None:
                results[idx] = await fetch_with_timeout(u)

            tg.create_task(_fetch(i, url))

    return results


# ============================================================
# 2. Backpressure with bounded async queue
# ============================================================

class BackpressureQueue(Generic[T]):
    """Async queue with backpressure, metrics, and graceful shutdown."""

    def __init__(self, maxsize: int = 100) -> None:
        self._queue: asyncio.Queue[T | None] = asyncio.Queue(maxsize=maxsize)
        self._produced = 0
        self._consumed = 0
        self._dropped = 0
        self._closed = False

    @property
    def pressure(self) -> float:
        """0.0 = empty, 1.0 = full."""
        return self._queue.qsize() / self._queue.maxsize

    async def put(self, item: T, timeout: float = 5.0) -> bool:
        """Put item with timeout. Returns False if queue full after timeout."""
        if self._closed:
            raise RuntimeError("Queue is closed")
        try:
            async with asyncio.timeout(timeout):
                await self._queue.put(item)
                self._produced += 1
                return True
        except TimeoutError:
            self._dropped += 1
            return False

    async def get(self) -> T | None:
        """Get item. Returns None when queue is closed and drained."""
        item = await self._queue.get()
        if item is not None:
            self._consumed += 1
        return item

    async def close(self) -> None:
        """Signal producers to stop; drain remaining items."""
        self._closed = True
        await self._queue.put(None)  # sentinel

    def stats(self) -> dict[str, int | float]:
        return {
            "produced": self._produced,
            "consumed": self._consumed,
            "dropped": self._dropped,
            "pending": self._queue.qsize(),
            "pressure": round(self.pressure, 3),
        }


async def producer(queue: BackpressureQueue[dict], batch_id: int) -> None:
    """Adaptive producer that slows down under backpressure."""
    for i in range(100):
        # Adaptive delay based on queue pressure
        if queue.pressure > 0.8:
            await asyncio.sleep(0.1)  # Back off when queue is filling up
        elif queue.pressure > 0.5:
            await asyncio.sleep(0.01)

        success = await queue.put({"batch": batch_id, "item": i})
        if not success:
            break  # Queue full for too long, stop producing


async def consumer(
    queue: BackpressureQueue[dict],
    process_fn: Callable[[dict], Coroutine[Any, Any, None]],
) -> None:
    """Consumer that processes items until queue is closed."""
    while True:
        item = await queue.get()
        if item is None:
            break
        await process_fn(item)


# ============================================================
# 3. Graceful shutdown with signal handling
# ============================================================

class GracefulRunner:
    """Manages async service lifecycle with graceful shutdown."""

    def __init__(self) -> None:
        self._shutdown_event = asyncio.Event()
        self._tasks: list[asyncio.Task[Any]] = []

    async def run(self, *coros: Coroutine[Any, Any, None]) -> None:
        """Run coroutines with graceful shutdown on SIGINT/SIGTERM."""
        loop = asyncio.get_running_loop()

        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, self._handle_signal, sig)

        # Start all tasks
        for coro in coros:
            self._tasks.append(asyncio.create_task(coro))

        # Wait for shutdown signal
        await self._shutdown_event.wait()

        # Cancel all tasks and wait for cleanup
        for task in self._tasks:
            task.cancel()

        results = await asyncio.gather(*self._tasks, return_exceptions=True)
        for r in results:
            if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError):
                print(f"Task error during shutdown: {r}")

    def _handle_signal(self, sig: signal.Signals) -> None:
        print(f"Received {sig.name}, shutting down...")
        self._shutdown_event.set()


# ============================================================
# 4. Async iterator with rate limiting
# ============================================================

class RateLimitedIterator(Generic[T]):
    """Wraps an async iterator with token-bucket rate limiting."""

    def __init__(
        self,
        source: AsyncIterator[T],
        rate: float,        # items per second
        burst: int = 1,     # max burst size
    ) -> None:
        self._source = source
        self._rate = rate
        self._burst = burst
        self._tokens = float(burst)
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def _acquire_token(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(
                self._burst, self._tokens + elapsed * self._rate
            )
            self._last_refill = now

            if self._tokens < 1.0:
                wait_time = (1.0 - self._tokens) / self._rate
                await asyncio.sleep(wait_time)
                self._tokens = 0.0
            else:
                self._tokens -= 1.0

    def __aiter__(self) -> AsyncIterator[T]:
        return self

    async def __anext__(self) -> T:
        await self._acquire_token()
        return await self._source.__anext__()


async def paginated_api_fetch(
    base_url: str, max_pages: int = 100
) -> AsyncIterator[dict]:
    """Async generator that paginates an API."""
    cursor: str | None = None
    for _ in range(max_pages):
        # Simulated API call
        await asyncio.sleep(0.01)
        page = {"data": [{"id": 1}], "next_cursor": None}
        for item in page["data"]:
            yield item
        cursor = page.get("next_cursor")
        if cursor is None:
            break


async def main() -> None:
    source = paginated_api_fetch("https://api.example.com/items")
    limited = RateLimitedIterator(source, rate=10.0, burst=5)

    async for item in limited:
        print(item)  # Max 10 items/second, burst of 5
```

**Key concepts:**

| Pattern | Problem Solved | Mechanism |
|---------|---------------|-----------|
| TaskGroup | Fire-and-forget tasks leak | Structured lifetime = parent waits for all children |
| Backpressure queue | Fast producer overwhelms slow consumer | Bounded queue + adaptive delay |
| Graceful shutdown | Ctrl+C leaves work half-done | Signal handlers + task cancellation + drain |
| Rate-limited iterator | API rate limits / resource protection | Token bucket algorithm over async iterator |
| `asyncio.timeout()` | Hanging tasks | Context manager cancels after deadline |

**Best practices:**
- Always use `asyncio.TaskGroup` (Python 3.11+) instead of bare `create_task`
- Implement backpressure at producer side, not consumer side
- Use `asyncio.timeout()` over `asyncio.wait_for()` for cleaner scoping
- Handle `CancelledError` in cleanup paths (e.g., close DB connections)
- Monitor queue pressure metrics in production for capacity planning'''
    ),
    (
        "concurrency/actor-model",
        "Implement the actor model pattern in Python with typed messages, supervision trees, and fault isolation, similar to Erlang/Akka patterns.",
        '''Actor model implementation in Python with supervision and fault isolation:

```python
"""Actor model — typed messages, supervision, fault isolation."""

import asyncio
import logging
import traceback
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum, auto
from typing import Any, Generic, TypeVar
from uuid import UUID, uuid4

logger = logging.getLogger(__name__)

T = TypeVar("T")


# ============================================================
# 1. Message protocol
# ============================================================

@dataclass(frozen=True)
class Envelope(Generic[T]):
    """Typed message envelope with metadata."""
    payload: T
    sender: "ActorRef | None" = None
    correlation_id: UUID = field(default_factory=uuid4)
    reply_to: "ActorRef | None" = None


@dataclass(frozen=True)
class PoisonPill:
    """Tells an actor to shut down gracefully."""
    reason: str = "shutdown"


@dataclass(frozen=True)
class ChildFailed:
    """Notification that a child actor has failed."""
    child_id: str
    error: Exception
    restart_count: int


# ============================================================
# 2. Actor base class
# ============================================================

class ActorRef:
    """Handle to send messages to an actor without direct reference."""

    def __init__(self, actor_id: str, mailbox: asyncio.Queue[Any]) -> None:
        self.actor_id = actor_id
        self._mailbox = mailbox

    async def tell(self, message: Any, sender: "ActorRef | None" = None) -> None:
        """Fire-and-forget message send."""
        await self._mailbox.put(Envelope(payload=message, sender=sender))

    async def ask(
        self, message: Any, timeout: float = 5.0
    ) -> Any:
        """Request-response pattern with timeout."""
        reply_queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=1)
        reply_ref = ActorRef(f"{self.actor_id}:reply", reply_queue)
        await self._mailbox.put(
            Envelope(payload=message, sender=None, reply_to=reply_ref)
        )
        async with asyncio.timeout(timeout):
            envelope = await reply_queue.get()
            return envelope.payload


class Actor(ABC):
    """Base actor with lifecycle hooks and message processing."""

    def __init__(self, actor_id: str, mailbox_size: int = 1000) -> None:
        self.actor_id = actor_id
        self._mailbox: asyncio.Queue[Any] = asyncio.Queue(maxsize=mailbox_size)
        self._ref = ActorRef(actor_id, self._mailbox)
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._children: dict[str, "Actor"] = {}

    @property
    def ref(self) -> ActorRef:
        return self._ref

    async def pre_start(self) -> None:
        """Called before the actor starts processing messages."""
        pass

    async def post_stop(self) -> None:
        """Called after the actor stops processing messages."""
        pass

    async def pre_restart(self, error: Exception) -> None:
        """Called before an actor is restarted after failure."""
        await self.post_stop()

    @abstractmethod
    async def receive(self, envelope: Envelope[Any]) -> None:
        """Process a single message. Override in subclass."""
        ...

    async def _run(self) -> None:
        """Main actor loop."""
        self._running = True
        await self.pre_start()
        logger.info("Actor %s started", self.actor_id)

        try:
            while self._running:
                envelope = await self._mailbox.get()

                if isinstance(envelope.payload, PoisonPill):
                    logger.info(
                        "Actor %s received PoisonPill: %s",
                        self.actor_id, envelope.payload.reason,
                    )
                    break

                try:
                    await self.receive(envelope)
                except Exception as exc:
                    logger.error(
                        "Actor %s failed processing message: %s",
                        self.actor_id, exc,
                    )
                    raise  # Let supervisor handle
        finally:
            self._running = False
            await self.post_stop()
            logger.info("Actor %s stopped", self.actor_id)

    def start(self) -> asyncio.Task[None]:
        self._task = asyncio.create_task(self._run())
        return self._task

    async def stop(self) -> None:
        await self.ref.tell(PoisonPill())
        if self._task:
            await self._task

    def spawn_child(self, child: "Actor") -> ActorRef:
        self._children[child.actor_id] = child
        child.start()
        return child.ref

    async def reply(self, envelope: Envelope[Any], response: Any) -> None:
        """Reply to an ask() call."""
        if envelope.reply_to:
            await envelope.reply_to.tell(response)


# ============================================================
# 3. Supervision strategies
# ============================================================

class SupervisorStrategy(StrEnum):
    ONE_FOR_ONE = auto()   # Restart only the failed child
    ALL_FOR_ONE = auto()   # Restart all children if one fails
    ESCALATE = auto()       # Propagate failure to parent


class Supervisor(Actor):
    """Supervisor actor that manages child lifecycles."""

    def __init__(
        self,
        actor_id: str,
        strategy: SupervisorStrategy = SupervisorStrategy.ONE_FOR_ONE,
        max_restarts: int = 3,
        restart_window_secs: float = 60.0,
    ) -> None:
        super().__init__(actor_id)
        self.strategy = strategy
        self.max_restarts = max_restarts
        self.restart_window_secs = restart_window_secs
        self._restart_counts: dict[str, list[float]] = {}
        self._child_factories: dict[str, Callable[[], Actor]] = {}

    def supervise(
        self, child_id: str, factory: Callable[[], Actor]
    ) -> ActorRef:
        """Register and start a supervised child actor."""
        self._child_factories[child_id] = factory
        self._restart_counts[child_id] = []
        child = factory()
        child._task = child.start()
        self._children[child_id] = child

        # Monitor child task for failures
        child._task.add_done_callback(
            lambda t, cid=child_id: asyncio.create_task(
                self._on_child_done(cid, t)
            )
        )
        return child.ref

    async def _on_child_done(
        self, child_id: str, task: asyncio.Task[None]
    ) -> None:
        """Handle child task completion or failure."""
        exc = task.exception() if not task.cancelled() else None
        if exc is None:
            return  # Normal shutdown

        import time
        now = time.monotonic()
        restarts = self._restart_counts.get(child_id, [])
        # Prune old restarts outside window
        restarts = [t for t in restarts if now - t < self.restart_window_secs]
        restarts.append(now)
        self._restart_counts[child_id] = restarts

        if len(restarts) > self.max_restarts:
            logger.error(
                "Child %s exceeded max restarts (%d in %.0fs), stopping",
                child_id, self.max_restarts, self.restart_window_secs,
            )
            return

        logger.warning(
            "Child %s failed (attempt %d/%d), restarting: %s",
            child_id, len(restarts), self.max_restarts, exc,
        )

        if self.strategy == SupervisorStrategy.ONE_FOR_ONE:
            await self._restart_child(child_id)
        elif self.strategy == SupervisorStrategy.ALL_FOR_ONE:
            for cid in list(self._children.keys()):
                await self._restart_child(cid)
        elif self.strategy == SupervisorStrategy.ESCALATE:
            raise exc

    async def _restart_child(self, child_id: str) -> None:
        factory = self._child_factories.get(child_id)
        if not factory:
            return
        old = self._children.pop(child_id, None)
        if old and old._running:
            await old.stop()
        self.supervise(child_id, factory)

    async def receive(self, envelope: Envelope[Any]) -> None:
        # Supervisor can route messages to children
        if isinstance(envelope.payload, dict) and "target" in envelope.payload:
            target_id = envelope.payload["target"]
            child = self._children.get(target_id)
            if child:
                await child.ref.tell(envelope.payload.get("message"))


# ============================================================
# 4. Concrete actor example: order processor
# ============================================================

@dataclass(frozen=True)
class ProcessOrder:
    order_id: str
    items: list[str]
    total_cents: int


@dataclass(frozen=True)
class OrderProcessed:
    order_id: str
    status: str


class OrderProcessor(Actor):
    def __init__(self) -> None:
        super().__init__(f"order-processor-{uuid4().hex[:8]}")
        self._processed = 0

    async def receive(self, envelope: Envelope[Any]) -> None:
        match envelope.payload:
            case ProcessOrder(order_id=oid, items=items, total_cents=total):
                logger.info("Processing order %s: %d items, $%.2f",
                            oid, len(items), total / 100)
                # Simulate processing
                await asyncio.sleep(0.01)
                self._processed += 1
                await self.reply(
                    envelope,
                    OrderProcessed(order_id=oid, status="completed"),
                )
            case _:
                logger.warning("Unknown message type: %s", type(envelope.payload))


async def main() -> None:
    # Create supervisor with one-for-one strategy
    supervisor = Supervisor(
        "order-supervisor",
        strategy=SupervisorStrategy.ONE_FOR_ONE,
        max_restarts=5,
        restart_window_secs=30.0,
    )
    supervisor.start()

    # Spawn supervised workers
    worker_ref = supervisor.supervise(
        "worker-1", OrderProcessor
    )

    # Send work via ask pattern
    result = await worker_ref.ask(
        ProcessOrder(order_id="ORD-001", items=["A", "B"], total_cents=4999)
    )
    print(result)  # OrderProcessed(order_id='ORD-001', status='completed')

    await supervisor.stop()

asyncio.run(main())
```

**Actor model concepts:**

| Concept | Description | Implementation |
|---------|-------------|----------------|
| Mailbox | Async message queue per actor | `asyncio.Queue` with backpressure |
| Tell | Fire-and-forget messaging | `ref.tell(msg)` |
| Ask | Request-response with timeout | `ref.ask(msg, timeout)` |
| Supervision | Parent manages child failures | `Supervisor` with restart strategies |
| PoisonPill | Graceful shutdown signal | Sentinel message in mailbox |
| Location transparency | Send messages without knowing internals | `ActorRef` abstraction |

**Best practices:**
- Keep actor state private; communicate only via messages
- Use supervision trees: leaf actors do work, parents handle failures
- Prefer tell over ask to avoid coupling sender to receiver lifecycle
- Use PoisonPill for graceful shutdown, task cancellation for hard stop
- Bound mailbox size to prevent unbounded memory growth'''
    ),
    (
        "concurrency/csp-channels-go-style",
        "Implement Go-style CSP (Communicating Sequential Processes) channels in Python with select, fan-in, fan-out, and pipeline patterns.",
        '''Go-style CSP channels in Python with select, fan-in/fan-out, and pipelines:

```python
"""CSP channels — Go-style concurrency in Python with typed channels."""

import asyncio
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Generic, TypeVar

T = TypeVar("T")


# ============================================================
# 1. Typed channel implementation
# ============================================================

class Channel(Generic[T]):
    """Go-style typed channel with close semantics."""

    def __init__(self, buffer_size: int = 0) -> None:
        # buffer_size=0 means unbuffered (rendezvous channel)
        self._queue: asyncio.Queue[T | None] = asyncio.Queue(
            maxsize=max(1, buffer_size)
        )
        self._closed = False
        self._close_event = asyncio.Event()
        self._num_receivers = 0

    async def send(self, value: T) -> None:
        """Send a value into the channel. Blocks if channel is full."""
        if self._closed:
            raise ChannelClosedError("Cannot send to closed channel")
        await self._queue.put(value)

    async def receive(self) -> T:
        """Receive a value from the channel. Raises ChannelClosedError when closed and drained."""
        value = await self._queue.get()
        if value is None and self._closed:
            # Re-insert sentinel for other receivers
            await self._queue.put(None)
            raise ChannelClosedError("Channel is closed")
        return value  # type: ignore[return-value]

    def close(self) -> None:
        """Close the channel. No more sends allowed."""
        if not self._closed:
            self._closed = True
            self._close_event.set()
            # Put sentinel for each potential receiver
            try:
                self._queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    @property
    def closed(self) -> bool:
        return self._closed

    def __aiter__(self) -> AsyncIterator[T]:
        return self._iterator()

    async def _iterator(self) -> AsyncIterator[T]:
        """Iterate over channel values until closed."""
        while True:
            try:
                value = await self.receive()
                yield value
            except ChannelClosedError:
                break


class ChannelClosedError(Exception):
    pass


# ============================================================
# 2. Select — wait on multiple channels (Go-style select)
# ============================================================

@dataclass
class SelectCase(Generic[T]):
    channel: Channel[T]
    label: str = ""


async def select(*cases: SelectCase[T]) -> tuple[str, T]:
    """Wait for the first channel to have a value available.

    Returns (label, value) of the first ready channel.
    Similar to Go's select statement.
    """
    tasks: dict[asyncio.Task[T], SelectCase[T]] = {}

    for case in cases:
        task = asyncio.create_task(case.channel.receive())
        tasks[task] = case

    try:
        done, pending = await asyncio.wait(
            tasks.keys(), return_when=asyncio.FIRST_COMPLETED
        )

        # Cancel pending tasks
        for task in pending:
            task.cancel()

        # Get result from first completed
        completed_task = next(iter(done))
        case = tasks[completed_task]

        result = completed_task.result()
        return (case.label, result)

    except ChannelClosedError:
        # Cancel all pending
        for task in tasks:
            if not task.done():
                task.cancel()
        raise


# ============================================================
# 3. Fan-out / Fan-in patterns
# ============================================================

async def fan_out(
    source: Channel[T],
    workers: int,
    process_fn,
    output: Channel,
) -> None:
    """Distribute work from source across multiple workers."""

    async def worker(worker_id: int) -> None:
        async for item in source:
            result = await process_fn(worker_id, item)
            await output.send(result)

    async with asyncio.TaskGroup() as tg:
        for i in range(workers):
            tg.create_task(worker(i))

    output.close()


async def fan_in(*channels: Channel[T]) -> Channel[T]:
    """Merge multiple channels into a single output channel."""
    merged: Channel[T] = Channel(buffer_size=len(channels) * 10)
    active = len(channels)

    async def forward(ch: Channel[T]) -> None:
        nonlocal active
        async for value in ch:
            await merged.send(value)
        active -= 1
        if active == 0:
            merged.close()

    for ch in channels:
        asyncio.create_task(forward(ch))

    return merged


# ============================================================
# 4. Pipeline pattern
# ============================================================

async def pipeline_example() -> None:
    """Multi-stage processing pipeline using channels."""

    # Stage 1: Generate numbers
    numbers: Channel[int] = Channel(buffer_size=10)

    async def generate() -> None:
        for i in range(100):
            await numbers.send(i)
        numbers.close()

    # Stage 2: Square (fan-out to multiple workers)
    squared: Channel[int] = Channel(buffer_size=10)

    async def square(worker_id: int, n: int) -> int:
        await asyncio.sleep(random.uniform(0.001, 0.01))  # Simulate work
        return n * n

    # Stage 3: Filter (keep only even results)
    filtered: Channel[int] = Channel(buffer_size=10)

    async def filter_even() -> None:
        async for value in squared:
            if value % 2 == 0:
                await filtered.send(value)
        filtered.close()

    # Stage 4: Accumulate results
    async def accumulate() -> int:
        total = 0
        count = 0
        async for value in filtered:
            total += value
            count += 1
        return total

    # Wire pipeline together
    asyncio.create_task(generate())
    asyncio.create_task(fan_out(numbers, workers=4, process_fn=square, output=squared))
    asyncio.create_task(filter_even())
    result = await accumulate()
    print(f"Sum of even squares: {result}")


# ============================================================
# 5. Ticker / timer channels (Go-style)
# ============================================================

class Ticker:
    """Go-style ticker that sends ticks at regular intervals."""

    def __init__(self, interval_seconds: float) -> None:
        self.interval = interval_seconds
        self.channel: Channel[float] = Channel(buffer_size=1)
        self._task: asyncio.Task[None] | None = None

    def start(self) -> Channel[float]:
        self._task = asyncio.create_task(self._tick())
        return self.channel

    async def _tick(self) -> None:
        import time
        while not self.channel.closed:
            await asyncio.sleep(self.interval)
            try:
                await self.channel.send(time.monotonic())
            except ChannelClosedError:
                break

    def stop(self) -> None:
        self.channel.close()
        if self._task:
            self._task.cancel()


async def timeout_channel(seconds: float) -> Channel[None]:
    """Go-style time.After — channel that fires once after delay."""
    ch: Channel[None] = Channel(buffer_size=1)

    async def _fire() -> None:
        await asyncio.sleep(seconds)
        try:
            await ch.send(None)
        except ChannelClosedError:
            pass
        ch.close()

    asyncio.create_task(_fire())
    return ch


async def select_with_timeout() -> None:
    """Example: process work items with timeout and periodic status."""
    work: Channel[str] = Channel(buffer_size=5)
    timeout = await timeout_channel(10.0)
    ticker = Ticker(2.0)
    tick_ch = ticker.start()

    # Populate some work
    for item in ["task-1", "task-2", "task-3"]:
        await work.send(item)

    processed = 0
    running = True
    while running:
        try:
            label, value = await select(
                SelectCase(work, "work"),
                SelectCase(tick_ch, "tick"),
                SelectCase(timeout, "timeout"),
            )

            match label:
                case "work":
                    print(f"Processing: {value}")
                    processed += 1
                case "tick":
                    print(f"Status: processed {processed} items")
                case "timeout":
                    print("Timeout reached, stopping")
                    running = False
        except ChannelClosedError:
            break

    ticker.stop()


asyncio.run(select_with_timeout())
```

**CSP patterns comparison:**

| Go Pattern | Python Equivalent | Description |
|-----------|------------------|-------------|
| `ch <- value` | `await ch.send(value)` | Send to channel |
| `value := <-ch` | `value = await ch.receive()` | Receive from channel |
| `for v := range ch` | `async for v in ch` | Iterate until closed |
| `select { case ... }` | `await select(...)` | Multiplex channels |
| `go func()` | `asyncio.create_task(...)` | Spawn concurrent work |
| `close(ch)` | `ch.close()` | Signal no more values |
| `time.Tick(d)` | `Ticker(d).start()` | Periodic ticks |
| `time.After(d)` | `timeout_channel(d)` | One-shot timer |

**Best practices:**
- Use buffered channels for producer-consumer with different speeds
- Use unbuffered channels (buffer_size=0) for synchronization points
- Always close channels from the sender side, never the receiver
- Fan-out for CPU-bound work parallelism, fan-in to collect results
- Use select with a timeout channel to prevent indefinite blocking'''
    ),
    (
        "concurrency/lock-free-parallel-algorithms",
        "Implement lock-free data structures and parallel algorithms in Python and Go, including a lock-free stack, parallel merge sort, and work-stealing scheduler.",
        '''Lock-free data structures and parallel algorithms:

```python
"""Lock-free structures and parallel algorithms using atomics and asyncio."""

import asyncio
import multiprocessing as mp
import os
import time
from collections.abc import Callable, Sequence
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from dataclasses import dataclass, field
from multiprocessing import shared_memory
from threading import Thread
from typing import Generic, TypeVar

import ctypes
import struct

T = TypeVar("T")


# ============================================================
# 1. Lock-free stack (Treiber stack) using CAS
# ============================================================

class AtomicReference(Generic[T]):
    """Simulated CAS (Compare-And-Swap) reference for Python.

    In production, use ctypes or cffi to wrap actual atomic ops.
    Python's GIL makes this safe for CPython, but the pattern
    is important for understanding lock-free algorithms.
    """

    def __init__(self, value: T | None = None) -> None:
        self._value = value
        self._version = 0  # ABA counter

    def get(self) -> tuple[T | None, int]:
        return self._value, self._version

    def compare_and_swap(
        self, expected: T | None, expected_version: int, new_value: T | None
    ) -> bool:
        """Atomically set value if current matches expected value + version."""
        if self._value is expected and self._version == expected_version:
            self._value = new_value
            self._version += 1
            return True
        return False


@dataclass
class StackNode(Generic[T]):
    value: T
    next_node: "StackNode[T] | None" = None


class LockFreeStack(Generic[T]):
    """Treiber's lock-free stack using CAS operations."""

    def __init__(self) -> None:
        self._top = AtomicReference[StackNode[T]]()
        self._size = 0

    def push(self, value: T) -> None:
        new_node = StackNode(value=value)
        while True:
            old_top, version = self._top.get()
            new_node.next_node = old_top
            if self._top.compare_and_swap(old_top, version, new_node):
                self._size += 1
                return
            # CAS failed, retry (contention)

    def pop(self) -> T | None:
        while True:
            old_top, version = self._top.get()
            if old_top is None:
                return None
            new_top = old_top.next_node
            if self._top.compare_and_swap(old_top, version, new_top):
                self._size -= 1
                return old_top.value
            # CAS failed, retry

    def peek(self) -> T | None:
        top, _ = self._top.get()
        return top.value if top else None

    @property
    def size(self) -> int:
        return self._size


# ============================================================
# 2. Parallel merge sort using multiprocessing
# ============================================================

def _merge(left: list[int], right: list[int]) -> list[int]:
    """Merge two sorted lists."""
    result: list[int] = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            result.append(left[i])
            i += 1
        else:
            result.append(right[j])
            j += 1
    result.extend(left[i:])
    result.extend(right[j:])
    return result


def _merge_sort_sequential(arr: list[int]) -> list[int]:
    """Standard recursive merge sort."""
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = _merge_sort_sequential(arr[:mid])
    right = _merge_sort_sequential(arr[mid:])
    return _merge(left, right)


def _sort_chunk(chunk: list[int]) -> list[int]:
    """Sort a chunk (for ProcessPoolExecutor)."""
    return _merge_sort_sequential(chunk)


def parallel_merge_sort(
    arr: list[int],
    num_workers: int | None = None,
    min_chunk_size: int = 10_000,
) -> list[int]:
    """Parallel merge sort using process pool.

    Splits array into chunks, sorts each in parallel,
    then merges results in a tree pattern.
    """
    if num_workers is None:
        num_workers = min(mp.cpu_count(), 8)

    n = len(arr)
    if n <= min_chunk_size:
        return _merge_sort_sequential(arr)

    # Split into chunks for parallel sorting
    chunk_size = max(min_chunk_size, n // num_workers)
    chunks = [arr[i:i + chunk_size] for i in range(0, n, chunk_size)]

    # Sort chunks in parallel
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        sorted_chunks = list(executor.map(_sort_chunk, chunks))

    # Tree-merge sorted chunks
    while len(sorted_chunks) > 1:
        next_level: list[list[int]] = []
        for i in range(0, len(sorted_chunks), 2):
            if i + 1 < len(sorted_chunks):
                next_level.append(_merge(sorted_chunks[i], sorted_chunks[i + 1]))
            else:
                next_level.append(sorted_chunks[i])
        sorted_chunks = next_level

    return sorted_chunks[0]


# ============================================================
# 3. Work-stealing scheduler
# ============================================================

@dataclass
class WorkItem:
    task_id: str
    fn: Callable[[], any]
    priority: int = 0


class WorkStealingDeque(Generic[T]):
    """Double-ended queue for work stealing.

    Owner pushes/pops from the bottom (LIFO for locality).
    Thieves steal from the top (FIFO for load balancing).
    """

    def __init__(self, capacity: int = 1024) -> None:
        self._items: list[T | None] = [None] * capacity
        self._bottom = 0  # Owner's end
        self._top = 0     # Thieves' end

    def push(self, item: T) -> None:
        """Owner pushes to bottom."""
        idx = self._bottom % len(self._items)
        self._items[idx] = item
        self._bottom += 1

    def pop(self) -> T | None:
        """Owner pops from bottom (LIFO)."""
        if self._bottom <= self._top:
            return None
        self._bottom -= 1
        idx = self._bottom % len(self._items)
        item = self._items[idx]
        self._items[idx] = None
        if self._bottom < self._top:
            self._bottom = self._top
            return None
        return item

    def steal(self) -> T | None:
        """Thief steals from top (FIFO)."""
        if self._top >= self._bottom:
            return None
        idx = self._top % len(self._items)
        item = self._items[idx]
        self._top += 1
        return item

    @property
    def size(self) -> int:
        return max(0, self._bottom - self._top)


class WorkStealingScheduler:
    """Simple work-stealing scheduler with multiple worker threads."""

    def __init__(self, num_workers: int = 4) -> None:
        self.num_workers = num_workers
        self._queues = [WorkStealingDeque[WorkItem]() for _ in range(num_workers)]
        self._running = False
        self._threads: list[Thread] = []
        self._results: dict[str, any] = {}
        self._completed = 0
        self._stolen = 0

    def submit(self, task_id: str, fn: Callable[[], any]) -> None:
        """Submit work to the least-loaded worker."""
        min_idx = min(range(self.num_workers), key=lambda i: self._queues[i].size)
        self._queues[min_idx].push(WorkItem(task_id=task_id, fn=fn))

    def start(self) -> None:
        self._running = True
        for i in range(self.num_workers):
            t = Thread(target=self._worker_loop, args=(i,), daemon=True)
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        self._running = False
        for t in self._threads:
            t.join(timeout=5.0)

    def _worker_loop(self, worker_id: int) -> None:
        my_queue = self._queues[worker_id]
        while self._running:
            # Try own queue first
            item = my_queue.pop()
            if item is None:
                # Try stealing from a random other worker
                import random
                victim = random.choice(
                    [i for i in range(self.num_workers) if i != worker_id]
                )
                item = self._queues[victim].steal()
                if item:
                    self._stolen += 1

            if item:
                try:
                    result = item.fn()
                    self._results[item.task_id] = result
                    self._completed += 1
                except Exception as exc:
                    self._results[item.task_id] = exc
            else:
                time.sleep(0.001)  # No work available, brief sleep

    @property
    def stats(self) -> dict[str, int]:
        return {
            "completed": self._completed,
            "stolen": self._stolen,
            "pending": sum(q.size for q in self._queues),
        }


# ============================================================
# 4. Parallel map-reduce
# ============================================================

def parallel_map_reduce(
    data: Sequence[T],
    map_fn: Callable[[T], any],
    reduce_fn: Callable[[any, any], any],
    initial: any = None,
    num_workers: int | None = None,
) -> any:
    """Generic parallel map-reduce over a sequence.

    Map phase runs in parallel across processes.
    Reduce phase merges results sequentially.
    """
    if num_workers is None:
        num_workers = min(mp.cpu_count(), len(data))

    # Parallel map
    with ProcessPoolExecutor(max_workers=num_workers) as executor:
        mapped = list(executor.map(map_fn, data))

    # Sequential reduce
    result = initial
    for item in mapped:
        if result is None:
            result = item
        else:
            result = reduce_fn(result, item)
    return result


# Example: word count across files
def count_words(text: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for word in text.lower().split():
        counts[word] = counts.get(word, 0) + 1
    return counts

def merge_counts(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:
    merged = dict(a)
    for word, count in b.items():
        merged[word] = merged.get(word, 0) + count
    return merged

# Usage:
# texts = [open(f).read() for f in glob("*.txt")]
# total_counts = parallel_map_reduce(texts, count_words, merge_counts)
```

**Pattern comparison:**

| Pattern | Synchronization | Best For | Tradeoff |
|---------|----------------|----------|----------|
| Lock-free stack | CAS retry loop | High-contention LIFO | Simple but ABA-prone |
| Parallel merge sort | Fork-join | Large array sorting | Memory overhead from copies |
| Work stealing | Lock-free deques | Irregular workloads | Complexity in stealing logic |
| Map-reduce | Process pool | Embarrassingly parallel | Serialization overhead |

**Best practices:**
- Use `ProcessPoolExecutor` for CPU-bound work (bypasses GIL)
- Use `ThreadPoolExecutor` for I/O-bound work
- Set `min_chunk_size` to amortize process spawn overhead (typically 10K+ items)
- In real systems, use proven libraries (e.g., `concurrent.futures`, `ray`, `dask`) over hand-rolled lock-free structures
- Profile before parallelizing: overhead can outweigh gains for small workloads'''
    ),
]
"""
