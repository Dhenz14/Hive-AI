PAIRS = [

    ("async/structured-concurrency",
     r"""Explain structured concurrency in Python async programming including TaskGroups, nurseries, cancellation propagation, resource cleanup, and error handling in concurrent contexts with practical examples""",
     r"""# Structured Concurrency in Python Async Programming

Structured concurrency is a paradigm that fundamentally rethinks how we organize concurrent operations. The core idea is simple but powerful: **concurrent tasks should be scoped to a well-defined lifetime**, and that lifetime should follow the structure of your code. This stands in contrast to "fire-and-forget" concurrency where tasks are launched without any guarantee of when — or whether — they complete.

## Why Structured Concurrency Matters

Traditional async programming with `asyncio.create_task()` suffers from a critical flaw: tasks can outlive the scope that created them. This leads to resource leaks, orphaned coroutines, and errors that silently vanish into the void. Structured concurrency fixes this **because** it enforces a parent-child relationship between tasks, ensuring that a parent scope cannot exit until all child tasks have completed or been cancelled.

The concept originates from Trio's "nurseries" (introduced by Nathaniel J. Smith) and has since been adopted into Python's standard library as `TaskGroup` in Python 3.11+. Erlang's supervision trees pioneered similar ideas decades earlier, **however** the Python ecosystem only recently embraced them at the language level.

## TaskGroups: Python's Built-in Structured Concurrency

Python 3.11 introduced `asyncio.TaskGroup`, which provides structured concurrency out of the box:

```python
import asyncio
from typing import Any

async def fetch_user(user_id: int) -> dict[str, Any]:
    # Simulate an API call
    await asyncio.sleep(0.1)
    return {"id": user_id, "name": f"User_{user_id}"}

async def fetch_orders(user_id: int) -> list[dict[str, Any]]:
    # Simulate a database query
    await asyncio.sleep(0.15)
    return [{"order_id": i, "user_id": user_id} for i in range(3)]

async def fetch_preferences(user_id: int) -> dict[str, str]:
    await asyncio.sleep(0.05)
    return {"theme": "dark", "language": "en"}

async def load_user_profile(user_id: int) -> dict[str, Any]:
    # All tasks are scoped to this block — none can escape
    async with asyncio.TaskGroup() as tg:
        user_task = tg.create_task(fetch_user(user_id))
        orders_task = tg.create_task(fetch_orders(user_id))
        prefs_task = tg.create_task(fetch_preferences(user_id))

    # Only reached when ALL tasks have completed
    return {
        "user": user_task.result(),
        "orders": orders_task.result(),
        "preferences": prefs_task.result(),
    }

asyncio.run(load_user_profile(42))
```

The **best practice** here is that the `async with` block guarantees all three tasks complete before we access their results. There is no possibility of a dangling task.

## Cancellation Propagation

One of the most important aspects of structured concurrency is how cancellation propagates through the task tree. When one task in a `TaskGroup` raises an exception, all sibling tasks are cancelled automatically:

```python
import asyncio
import logging
from typing import Any

logger = logging.getLogger(__name__)

class ServiceUnavailableError(Exception):
    pass

async def fetch_critical_data() -> dict[str, Any]:
    await asyncio.sleep(0.1)
    raise ServiceUnavailableError("Database is down")

async def fetch_supplemental_data() -> dict[str, Any]:
    # This task will be cancelled when fetch_critical_data fails
    try:
        await asyncio.sleep(10.0)  # Long-running operation
        return {"extra": "data"}
    except asyncio.CancelledError:
        logger.info("Supplemental fetch was cancelled — cleaning up")
        # Perform any necessary cleanup here
        raise  # Always re-raise CancelledError

async def resilient_data_loader() -> dict[str, Any]:
    try:
        async with asyncio.TaskGroup() as tg:
            critical = tg.create_task(fetch_critical_data())
            supplemental = tg.create_task(fetch_supplemental_data())
    except* ServiceUnavailableError as exc_group:
        logger.error(f"Critical service failed: {exc_group.exceptions}")
        return {"fallback": True, "reason": "service_unavailable"}

    return {
        "critical": critical.result(),
        "supplemental": supplemental.result(),
    }
```

A **common mistake** is swallowing `CancelledError` instead of re-raising it. When a task catches `CancelledError` and does not propagate it, the structured concurrency contract is broken — the parent scope cannot know the task has been properly terminated. **Therefore**, always re-raise `CancelledError` after performing cleanup.

## Resource Cleanup with Structured Concurrency

Structured concurrency pairs naturally with async context managers for resource lifecycle management:

```python
import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator, Any

class AsyncConnectionPool:
    def __init__(self, max_connections: int = 10) -> None:
        self._semaphore = asyncio.Semaphore(max_connections)
        self._connections: list[Any] = []

    async def initialize(self) -> None:
        # Pre-warm the connection pool
        for _ in range(5):
            conn = await self._create_connection()
            self._connections.append(conn)

    async def _create_connection(self) -> dict[str, Any]:
        await asyncio.sleep(0.01)  # Simulate connection setup
        return {"connected": True, "id": id(object())}

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[dict[str, Any]]:
        async with self._semaphore:
            conn = self._connections.pop() if self._connections else await self._create_connection()
            try:
                yield conn
            finally:
                # Return connection to pool even if task is cancelled
                self._connections.append(conn)

    async def close(self) -> None:
        self._connections.clear()

@asynccontextmanager
async def managed_pool(max_connections: int = 10) -> AsyncIterator[AsyncConnectionPool]:
    pool = AsyncConnectionPool(max_connections)
    await pool.initialize()
    try:
        yield pool
    finally:
        await pool.close()

async def process_batch(items: list[int]) -> list[str]:
    results: list[str] = []

    async with managed_pool(max_connections=5) as pool:
        async with asyncio.TaskGroup() as tg:
            async def process_item(item: int) -> None:
                async with pool.acquire() as conn:
                    await asyncio.sleep(0.01)  # Simulate work
                    results.append(f"Processed {item} via {conn['id']}")

            for item in items:
                tg.create_task(process_item(item))

    # Pool is guaranteed to be closed here, even if tasks failed
    return results
```

The **trade-off** with structured concurrency is that it can feel more restrictive than fire-and-forget patterns. You cannot easily launch a "background" task that outlives its parent scope. **However**, this restriction is precisely what makes the code reliable — every task has an owner, and every owner waits for its tasks.

## Error Handling with ExceptionGroups

Python 3.11 introduced `ExceptionGroup` and the `except*` syntax specifically to support structured concurrency. When multiple tasks fail simultaneously, their exceptions are collected into an `ExceptionGroup`:

A **pitfall** developers encounter is using bare `except Exception` instead of `except*` with TaskGroups. The TaskGroup wraps multiple exceptions into an `ExceptionGroup`, and a bare `except` will catch the group as a whole rather than letting you handle individual exception types selectively. **Best practice** is to always use `except*` with `TaskGroup` code so you can pattern-match on the specific exception types within the group.

## Summary / Key Takeaways

- **Structured concurrency scopes task lifetimes** to code blocks, preventing orphaned tasks and resource leaks.
- **TaskGroup** (Python 3.11+) is the standard library implementation; use it instead of raw `create_task()` for concurrent work.
- **Cancellation propagates automatically** — when one task fails, siblings are cancelled. Always re-raise `CancelledError` after cleanup.
- **Pair structured concurrency with async context managers** for deterministic resource lifecycle management.
- **Use `except*` syntax** to handle individual exception types within `ExceptionGroup` results from failed TaskGroups.
- The main **trade-off** is reduced flexibility for background tasks, but the reliability gains are substantial for production systems.
"""),

    ("async/actor-model",
     r"""How do you implement the actor model pattern in Python async code inspired by Erlang and Akka including message passing, supervision trees, backpressure mechanisms, and state isolation""",
     r"""# The Actor Model in Python Async Programming

The actor model is a mathematical model of concurrent computation where **actors** are the universal primitives. Each actor can receive messages, make local decisions, create more actors, send messages, and determine how to respond to the next message. Originally formalized by Carl Hewitt in 1973 and popularized by Erlang and Akka, the actor model provides a powerful abstraction for building fault-tolerant, concurrent systems. Python's `asyncio` gives us the building blocks to implement actor-like patterns, even though it lacks a native actor framework.

## Core Principles of the Actor Model

The key insight behind actors is **state isolation**. Each actor owns its state exclusively — no other actor can read or modify it directly. Communication happens solely through asynchronous message passing. This eliminates shared mutable state, which is the root cause of most concurrency bugs. **Because** there is no shared memory, there are no locks, no race conditions, and no deadlocks from competing state access.

In Erlang and Akka, actors also embody the "let it crash" philosophy: rather than defensively handling every possible error, actors are designed to fail fast and be restarted by a supervisor. This approach produces remarkably resilient systems **because** the error handling logic is separated from the business logic.

## Implementing a Basic Actor in Python

```python
import asyncio
from typing import Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum, auto

class MessageType(Enum):
    COMMAND = auto()
    QUERY = auto()
    STOP = auto()

@dataclass
class Message:
    msg_type: MessageType
    payload: dict[str, Any]
    reply_to: asyncio.Future[Any] | None = None

class Actor:
    # Base class for all actors — encapsulates mailbox and processing loop

    def __init__(self, name: str, mailbox_size: int = 100) -> None:
        self.name = name
        self._mailbox: asyncio.Queue[Message] = asyncio.Queue(maxsize=mailbox_size)
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._state: dict[str, Any] = {}

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._run_loop())

    async def _run_loop(self) -> None:
        while self._running:
            try:
                message = await asyncio.wait_for(
                    self._mailbox.get(), timeout=1.0
                )
                await self._handle_message(message)
            except asyncio.TimeoutError:
                continue
            except Exception as exc:
                await self._on_error(exc)

    async def _handle_message(self, message: Message) -> None:
        if message.msg_type == MessageType.STOP:
            self._running = False
            if message.reply_to and not message.reply_to.done():
                message.reply_to.set_result(True)
            return

        result = await self.receive(message)
        if message.reply_to and not message.reply_to.done():
            message.reply_to.set_result(result)

    async def receive(self, message: Message) -> Any:
        # Override in subclasses to define behavior
        raise NotImplementedError

    async def _on_error(self, exc: Exception) -> None:
        # Hook for supervision — default just logs
        print(f"Actor {self.name} error: {exc}")

    async def send(self, message: Message) -> None:
        # Non-blocking send with backpressure via bounded queue
        await self._mailbox.put(message)

    async def ask(self, msg_type: MessageType, payload: dict[str, Any]) -> Any:
        # Request-response pattern — sends message and awaits reply
        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        message = Message(msg_type=msg_type, payload=payload, reply_to=future)
        await self.send(message)
        return await future

    async def stop(self) -> None:
        future: asyncio.Future[Any] = asyncio.get_event_loop().create_future()
        await self.send(Message(MessageType.STOP, {}, reply_to=future))
        await future
        if self._task:
            await self._task
```

## State Isolation with Typed Actors

**Best practice** is to define actors with explicit, typed state so that the isolation guarantees are obvious at the code level:

```python
import asyncio
from dataclasses import dataclass, field
from typing import Any

@dataclass
class AccountState:
    # Private state — only the owning actor can access this
    balance: float = 0.0
    transaction_count: int = 0
    frozen: bool = False

class BankAccountActor(Actor):
    def __init__(self, account_id: str) -> None:
        super().__init__(name=f"account-{account_id}")
        self._account = AccountState()
        self._account_id = account_id

    async def receive(self, message: Message) -> Any:
        action = message.payload.get("action")

        if action == "deposit":
            if self._account.frozen:
                return {"error": "Account is frozen"}
            amount = message.payload["amount"]
            self._account.balance += amount
            self._account.transaction_count += 1
            return {"balance": self._account.balance}

        elif action == "withdraw":
            if self._account.frozen:
                return {"error": "Account is frozen"}
            amount = message.payload["amount"]
            if amount > self._account.balance:
                return {"error": "Insufficient funds"}
            self._account.balance -= amount
            self._account.transaction_count += 1
            return {"balance": self._account.balance}

        elif action == "get_balance":
            return {"balance": self._account.balance, "txn_count": self._account.transaction_count}

        elif action == "freeze":
            self._account.frozen = True
            return {"frozen": True}

        return {"error": f"Unknown action: {action}"}
```

Notice that `AccountState` is never shared with any other actor. Even if a hundred concurrent requests arrive, they are serialized through the actor's mailbox. This is the fundamental **trade-off** of the actor model: you sacrifice parallelism within a single actor for the simplicity of sequential message processing.

## Supervision Trees

The supervision tree pattern, borrowed directly from Erlang/OTP, organizes actors into a hierarchy where parent actors monitor and restart child actors on failure:

```python
import asyncio
from enum import Enum, auto
from typing import Type, Any

class RestartStrategy(Enum):
    ONE_FOR_ONE = auto()   # Restart only the failed child
    ONE_FOR_ALL = auto()   # Restart all children if one fails
    REST_FOR_ONE = auto()  # Restart the failed child and all children started after it

class Supervisor:
    # Monitors child actors and restarts them according to a strategy

    def __init__(
        self,
        name: str,
        strategy: RestartStrategy = RestartStrategy.ONE_FOR_ONE,
        max_restarts: int = 3,
        restart_window_seconds: float = 60.0,
    ) -> None:
        self.name = name
        self.strategy = strategy
        self.max_restarts = max_restarts
        self.restart_window = restart_window_seconds
        self._children: dict[str, Actor] = {}
        self._child_factories: dict[str, Callable[[], Actor]] = {}
        self._restart_counts: dict[str, list[float]] = {}

    async def add_child(
        self, name: str, factory: Callable[[], Actor]
    ) -> Actor:
        actor = factory()
        self._children[name] = actor
        self._child_factories[name] = factory
        self._restart_counts[name] = []
        await actor.start()
        return actor

    async def _restart_child(self, name: str) -> bool:
        now = asyncio.get_event_loop().time()
        recent = [t for t in self._restart_counts[name]
                  if now - t < self.restart_window]
        self._restart_counts[name] = recent

        if len(recent) >= self.max_restarts:
            print(f"Supervisor {self.name}: max restarts exceeded for {name}")
            return False

        self._restart_counts[name].append(now)

        old_actor = self._children[name]
        try:
            await old_actor.stop()
        except Exception:
            pass

        new_actor = self._child_factories[name]()
        self._children[name] = new_actor
        await new_actor.start()
        print(f"Supervisor {self.name}: restarted {name}")
        return True

    async def handle_child_failure(self, failed_name: str) -> None:
        if self.strategy == RestartStrategy.ONE_FOR_ONE:
            await self._restart_child(failed_name)
        elif self.strategy == RestartStrategy.ONE_FOR_ALL:
            for name in self._children:
                await self._restart_child(name)
```

A **common mistake** is building supervision trees that are too flat. In practice, you want a hierarchy: a top-level supervisor manages subsystem supervisors, which in turn manage individual worker actors. This mirrors Erlang's application structure and provides granular failure isolation. **Therefore**, design your supervision tree to match your system's failure domains.

## Backpressure Mechanisms

Backpressure is critical in actor systems to prevent fast producers from overwhelming slow consumers. The bounded `asyncio.Queue` provides natural backpressure — when the mailbox is full, `send()` will await until space is available. **However**, more sophisticated strategies exist for production systems, such as dropping oldest messages, rejecting new messages, or dynamically adjusting processing rates.

The **pitfall** with unbounded mailboxes is that memory grows without limit under load. Always use bounded queues in production actor systems and monitor queue depths as a health indicator.

## Summary / Key Takeaways

- **The actor model isolates state** within individual actors, eliminating shared mutable state and the bugs it causes.
- **Message passing through bounded queues** provides natural backpressure and serializes access to actor state.
- **Supervision trees** separate error handling from business logic — let actors crash and restart cleanly.
- **The ask pattern** (request-response) bridges actor messaging with Python's `await` semantics using futures.
- The primary **trade-off** is that single-actor throughput is limited by sequential message processing, but the system scales by adding more actors.
- **Best practice**: design your supervision hierarchy to match your system's failure domains, keeping related actors under common supervisors.
"""),

    ("async/reactive-streams",
     r"""Describe reactive streams and backpressure protocols for Python async programming including publishers, subscribers, operators like map filter buffer and merge, and async iterators for stream processing""",
     r"""# Reactive Streams and Backpressure in Python Async Programming

Reactive streams represent a paradigm for processing potentially unbounded sequences of data with **non-blocking backpressure**. The core problem they solve is this: when a data producer emits items faster than a consumer can process them, what happens? Without backpressure, you either drop data, buffer infinitely (and run out of memory), or block the producer. Reactive streams provide a principled solution **because** they give the consumer explicit control over how much data it requests from the producer.

## The Reactive Streams Contract

The reactive streams specification (originally from the JVM ecosystem, formalized as java.util.concurrent.Flow) defines four interfaces: **Publisher**, **Subscriber**, **Subscription**, and **Processor**. In Python, we can model these cleanly with protocols and async iterators.

The fundamental contract is:
1. A subscriber subscribes to a publisher
2. The publisher sends a subscription object to the subscriber
3. The subscriber requests N items through the subscription
4. The publisher sends at most N items
5. The publisher signals completion or error

This demand-driven model is what makes reactive streams fundamentally different from push-based event systems. **Because** the subscriber controls the flow rate, the system naturally adapts to the slowest component.

## Building Reactive Stream Primitives

```python
import asyncio
from typing import TypeVar, Generic, AsyncIterator, Callable, Awaitable, Any
from dataclasses import dataclass
from abc import ABC, abstractmethod

T = TypeVar("T")
U = TypeVar("U")

class Subscription:
    # Represents the link between publisher and subscriber

    def __init__(self) -> None:
        self._demand = 0
        self._demand_event = asyncio.Event()
        self._cancelled = False

    def request(self, n: int) -> None:
        if n <= 0:
            raise ValueError("Demand must be positive")
        self._demand += n
        self._demand_event.set()

    def cancel(self) -> None:
        self._cancelled = True
        self._demand_event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    async def wait_for_demand(self) -> int:
        while self._demand == 0 and not self._cancelled:
            self._demand_event.clear()
            await self._demand_event.wait()
        current = self._demand
        self._demand = 0
        return current

class Publisher(Generic[T], ABC):
    @abstractmethod
    async def subscribe(self, subscriber: "Subscriber[T]") -> None:
        ...

class Subscriber(Generic[T], ABC):
    @abstractmethod
    async def on_subscribe(self, subscription: Subscription) -> None:
        ...

    @abstractmethod
    async def on_next(self, item: T) -> None:
        ...

    @abstractmethod
    async def on_error(self, error: Exception) -> None:
        ...

    @abstractmethod
    async def on_complete(self) -> None:
        ...
```

## Async Iterators as Reactive Streams

Python's async iterator protocol is a natural fit for reactive streams. **However**, raw async iterators lack explicit backpressure signaling — the consumer implicitly applies backpressure by the rate at which it calls `__anext__()`. This is sufficient for many use cases and much simpler than the full reactive streams protocol:

```python
import asyncio
from typing import TypeVar, AsyncIterator, Callable, Awaitable, AsyncGenerator

T = TypeVar("T")
U = TypeVar("U")

class AsyncStream(AsyncIterator[T]):
    # Wraps an async iterable with operator chaining

    def __init__(self, source: AsyncIterator[T]) -> None:
        self._source = source

    def __aiter__(self) -> "AsyncStream[T]":
        return self

    async def __anext__(self) -> T:
        return await self._source.__anext__()

    def map(self, fn: Callable[[T], U | Awaitable[U]]) -> "AsyncStream[U]":
        # Transforms each element; fn can be sync or async
        source = self._source

        async def _mapped() -> AsyncGenerator[U, None]:
            async for item in source:
                result = fn(item)
                if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                    yield await result
                else:
                    yield result  # type: ignore

        return AsyncStream(_mapped().__aiter__())

    def filter(self, predicate: Callable[[T], bool | Awaitable[bool]]) -> "AsyncStream[T]":
        # Keeps only elements where predicate returns True
        source = self._source

        async def _filtered() -> AsyncGenerator[T, None]:
            async for item in source:
                result = predicate(item)
                if asyncio.iscoroutine(result) or asyncio.isfuture(result):
                    keep = await result
                else:
                    keep = result
                if keep:
                    yield item

        return AsyncStream(_filtered().__aiter__())

    def buffer(self, size: int) -> "AsyncStream[list[T]]":
        # Collects elements into batches of the given size
        source = self._source

        async def _buffered() -> AsyncGenerator[list[T], None]:
            batch: list[T] = []
            async for item in source:
                batch.append(item)
                if len(batch) >= size:
                    yield batch
                    batch = []
            if batch:
                yield batch

        return AsyncStream(_buffered().__aiter__())

    def take(self, n: int) -> "AsyncStream[T]":
        source = self._source

        async def _taken() -> AsyncGenerator[T, None]:
            count = 0
            async for item in source:
                if count >= n:
                    break
                yield item
                count += 1

        return AsyncStream(_taken().__aiter__())
```

## Merge Operator and Fan-In Patterns

Merging multiple streams into one is a fundamental operator. The **best practice** is to use `asyncio.Queue` as an intermediary so that all source streams can push items concurrently:

```python
import asyncio
from typing import TypeVar, AsyncIterator, AsyncGenerator

T = TypeVar("T")

async def merge(*streams: AsyncIterator[T], buffer_size: int = 64) -> AsyncGenerator[T, None]:
    # Merges multiple async streams into a single stream.
    # Items are yielded in the order they become available.
    queue: asyncio.Queue[T | None] = asyncio.Queue(maxsize=buffer_size)
    active_producers = len(streams)
    sentinel = object()

    async def producer(source: AsyncIterator[T]) -> None:
        nonlocal active_producers
        try:
            async for item in source:
                await queue.put(item)
        except Exception as exc:
            await queue.put(None)  # Signal this producer is done
            raise
        finally:
            active_producers -= 1
            await queue.put(None)  # sentinel: this producer is done

    tasks = [asyncio.create_task(producer(s)) for s in streams]

    finished_count = 0
    while finished_count < len(streams):
        item = await queue.get()
        if item is None:
            finished_count += 1
            continue
        yield item

    # Ensure all producer tasks are cleaned up
    for task in tasks:
        if not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
```

A **common mistake** with stream merging is forgetting to handle cleanup when the consumer stops reading early. If the consumer breaks out of the `async for` loop, the producer tasks must be cancelled; otherwise, they continue running and pumping items into a queue nobody reads. **Therefore**, always pair merge operations with proper task cancellation.

## Backpressure Strategies

There are several backpressure strategies, each with different **trade-offs**:

1. **Bounded buffering**: Use a fixed-size queue; producer blocks when full. Simple and predictable.
2. **Dropping**: Discard newest or oldest items when the buffer is full. Appropriate for time-series data where only the latest value matters.
3. **Windowing**: Collect items over a time window and process them as a batch. Reduces per-item overhead.
4. **Rate limiting**: Use a semaphore or token bucket to cap throughput. Good for API call rate limits.

The **pitfall** with unbounded streams is that they create the illusion of handling load while silently consuming memory. Always instrument your stream processing pipelines with queue depth metrics so you can detect backpressure problems before they cause out-of-memory crashes.

## Putting It All Together

Here is an example of a complete stream processing pipeline:

```python
async def process_events() -> None:
    # Create a source stream from an async generator
    async def event_source() -> AsyncGenerator[dict, None]:
        for i in range(1000):
            await asyncio.sleep(0.001)
            yield {"id": i, "type": "click" if i % 3 == 0 else "view", "value": i * 1.5}

    stream = AsyncStream(event_source().__aiter__())

    # Pipeline: filter clicks -> extract values -> batch by 10
    pipeline = (
        stream
        .filter(lambda e: e["type"] == "click")
        .map(lambda e: e["value"])
        .buffer(10)
        .take(5)
    )

    async for batch in pipeline:
        total = sum(batch)
        print(f"Batch total: {total}, items: {len(batch)}")
```

## Summary / Key Takeaways

- **Reactive streams solve the producer-consumer speed mismatch** through demand-driven backpressure, where the consumer controls the data flow rate.
- **Python's async iterators provide implicit backpressure** — the consumer's `__anext__()` call rate naturally limits the producer.
- **Operators like map, filter, buffer, and merge** compose into declarative data processing pipelines that are readable and maintainable.
- **Bounded queues are essential** for any production stream processing to prevent unbounded memory growth.
- The **trade-off** with reactive streams is increased complexity compared to simple request-response patterns, but they excel at handling high-throughput, real-time data flows.
- **Best practice**: always instrument your pipelines with metrics for queue depth and processing latency to detect backpressure issues early.
"""),

    ("async/testing-patterns",
     r"""What are the best async testing patterns in Python including event loop fixtures, mocking async I/O operations, time travel testing for timeouts, deadlock detection strategies, and test isolation techniques""",
     r"""# Async Testing Patterns in Python

Testing asynchronous code presents unique challenges that synchronous testing never encounters. Event loops, coroutine scheduling, timing-dependent behavior, and concurrent resource access all introduce failure modes that are subtle and often non-deterministic. A robust async testing strategy addresses these challenges systematically, producing tests that are **fast, deterministic, and isolated**. This guide covers the essential patterns for testing async Python code effectively.

## Event Loop Fixtures and Test Setup

The foundation of async testing is proper event loop management. The most widely used framework is `pytest-asyncio`, which provides fixtures and decorators for running async tests. **However**, getting the event loop configuration right is critical — a **common mistake** is sharing event loop state between tests, leading to flaky failures.

```python
import asyncio
import pytest
import pytest_asyncio
from typing import AsyncIterator, Any

# Configure pytest-asyncio to create a fresh loop per test
# In pyproject.toml or conftest.py:
# [tool.pytest.ini_options]
# asyncio_mode = "auto"

@pytest_asyncio.fixture
async def db_connection() -> AsyncIterator[dict[str, Any]]:
    # Setup: create a fresh connection for each test
    conn = {"connected": True, "data": {}}
    yield conn
    # Teardown: clean up after each test
    conn["connected"] = False
    conn["data"].clear()

@pytest_asyncio.fixture
async def message_queue() -> AsyncIterator[asyncio.Queue[str]]:
    queue: asyncio.Queue[str] = asyncio.Queue(maxsize=100)
    yield queue
    # Drain the queue to prevent warnings about pending items
    while not queue.empty():
        queue.get_nowait()

@pytest.mark.asyncio
async def test_database_write(db_connection: dict[str, Any]) -> None:
    db_connection["data"]["key"] = "value"
    assert db_connection["data"]["key"] == "value"

@pytest.mark.asyncio
async def test_database_isolation(db_connection: dict[str, Any]) -> None:
    # This test gets a FRESH connection — previous test's data is gone
    assert "key" not in db_connection["data"]
```

**Best practice** is to use `asyncio_mode = "auto"` so that every `async def test_*` function is automatically treated as an async test. This eliminates the need for `@pytest.mark.asyncio` on every test, reducing boilerplate and preventing the subtle bug where you forget the decorator and your test silently becomes a no-op (it returns a coroutine object that is never awaited).

## Mocking Async I/O Operations

Mocking async functions requires special handling **because** standard `unittest.mock.MagicMock` does not produce awaitables by default. Python 3.8+ provides `AsyncMock` for this purpose:

```python
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock
from typing import Any
import pytest

# The code under test
class UserService:
    def __init__(self, http_client: Any, cache: Any) -> None:
        self._http = http_client
        self._cache = cache

    async def get_user(self, user_id: int) -> dict[str, Any]:
        # Check cache first
        cached = await self._cache.get(f"user:{user_id}")
        if cached is not None:
            return cached

        # Fetch from API
        response = await self._http.get(f"/users/{user_id}")
        user_data = response["data"]

        # Store in cache
        await self._cache.set(f"user:{user_id}", user_data, ttl=300)
        return user_data

@pytest.mark.asyncio
async def test_get_user_cache_miss() -> None:
    mock_http = AsyncMock()
    mock_http.get.return_value = {"data": {"id": 42, "name": "Alice"}}

    mock_cache = AsyncMock()
    mock_cache.get.return_value = None  # Cache miss

    service = UserService(mock_http, mock_cache)
    user = await service.get_user(42)

    assert user["name"] == "Alice"
    mock_http.get.assert_awaited_once_with("/users/42")
    mock_cache.set.assert_awaited_once()

@pytest.mark.asyncio
async def test_get_user_cache_hit() -> None:
    mock_http = AsyncMock()
    mock_cache = AsyncMock()
    mock_cache.get.return_value = {"id": 42, "name": "Alice"}

    service = UserService(mock_http, mock_cache)
    user = await service.get_user(42)

    assert user["name"] == "Alice"
    # HTTP should NOT have been called — served from cache
    mock_http.get.assert_not_awaited()

@pytest.mark.asyncio
async def test_get_user_api_failure() -> None:
    mock_http = AsyncMock()
    mock_http.get.side_effect = ConnectionError("API unreachable")
    mock_cache = AsyncMock()
    mock_cache.get.return_value = None

    service = UserService(mock_http, mock_cache)
    with pytest.raises(ConnectionError, match="API unreachable"):
        await service.get_user(42)
```

A **pitfall** is using `MagicMock` where `AsyncMock` is needed. If you `await` a `MagicMock`, it raises `TypeError: object MagicMock can't be used in 'await' expression`. **Therefore**, always verify that your mocks match the async/sync nature of the functions they replace.

## Time Travel Testing

Testing timeout behavior, debouncing, retry delays, and other time-dependent logic is notoriously difficult. Running real delays makes tests slow and flaky. The solution is to mock or manipulate the event loop's clock:

```python
import asyncio
from typing import Any, Callable, Awaitable
from unittest.mock import patch, AsyncMock
import pytest

class RetryWithBackoff:
    # Retries an async operation with exponential backoff

    def __init__(
        self,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
    ) -> None:
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay

    async def execute(
        self, operation: Callable[[], Awaitable[Any]]
    ) -> Any:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return await operation()
            except Exception as exc:
                last_error = exc
                if attempt < self.max_retries:
                    delay = min(
                        self.base_delay * (2 ** attempt),
                        self.max_delay,
                    )
                    await asyncio.sleep(delay)
        raise last_error  # type: ignore

@pytest.mark.asyncio
async def test_retry_backoff_timing() -> None:
    sleep_calls: list[float] = []
    original_sleep = asyncio.sleep

    async def mock_sleep(delay: float, *args: Any) -> None:
        sleep_calls.append(delay)
        # Do not actually sleep — just record the delay

    operation = AsyncMock(
        side_effect=[ConnectionError(), ConnectionError(), "success"]
    )
    retry = RetryWithBackoff(max_retries=3, base_delay=1.0)

    with patch("asyncio.sleep", side_effect=mock_sleep):
        result = await retry.execute(operation)

    assert result == "success"
    assert operation.await_count == 3
    # Verify exponential backoff: 1.0, 2.0 seconds
    assert sleep_calls == [1.0, 2.0]

@pytest.mark.asyncio
async def test_retry_exhaustion() -> None:
    operation = AsyncMock(side_effect=ConnectionError("always fails"))
    retry = RetryWithBackoff(max_retries=2, base_delay=0.01)

    with patch("asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(ConnectionError, match="always fails"):
            await retry.execute(operation)

    assert operation.await_count == 3  # Initial + 2 retries
```

The **trade-off** with mocking `asyncio.sleep` is that it removes the actual concurrency timing from your tests. For integration tests where you need to verify real concurrent behavior, use short but real delays. For unit tests, mock time aggressively to keep tests fast and deterministic.

## Deadlock Detection Strategies

Deadlocks in async code typically manifest as tasks waiting on each other's results indefinitely. **Because** Python's `asyncio` runs on a single thread, classical lock-based deadlocks are rare, but logical deadlocks (circular await chains) are common:

```python
import asyncio
from typing import Any
import pytest

async def detect_potential_deadlock(
    coro: Any, timeout: float = 5.0, label: str = "operation"
) -> Any:
    # Wraps a coroutine with a timeout to catch hangs
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        # Gather diagnostic information
        tasks = asyncio.all_tasks()
        task_info = []
        for task in tasks:
            coro_repr = repr(task.get_coro())
            stack = task.get_stack()
            task_info.append(f"  Task: {task.get_name()}, coro: {coro_repr}")
            for frame in stack:
                task_info.append(f"    at {frame.f_code.co_filename}:{frame.f_lineno}")
        diagnostic = "\n".join(task_info)
        raise TimeoutError(
            f"Potential deadlock detected in '{label}' after {timeout}s.\n"
            f"Active tasks:\n{diagnostic}"
        )

@pytest.mark.asyncio
async def test_no_deadlock_in_pipeline() -> None:
    async def healthy_pipeline() -> str:
        await asyncio.sleep(0.01)
        return "done"

    result = await detect_potential_deadlock(
        healthy_pipeline(), timeout=1.0, label="pipeline"
    )
    assert result == "done"
```

**Best practice** for deadlock prevention in tests: always use `asyncio.wait_for()` with reasonable timeouts around operations that involve multiple cooperating tasks. This converts silent hangs into loud failures with actionable diagnostics.

## Test Isolation Techniques

Test isolation ensures that each test runs in a clean environment, unaffected by other tests. For async code, this means isolating event loop state, shared resources, and global singletons:

A **common mistake** is using module-level singletons (connection pools, caches, event buses) that accumulate state across tests. **Therefore**, always use fixtures to create fresh instances, and ensure teardown logic properly releases all resources — including cancelling any background tasks that might have been spawned.

## Summary / Key Takeaways

- **Use `pytest-asyncio` with `asyncio_mode = "auto"`** for seamless async test execution with fresh event loops per test.
- **Always use `AsyncMock`** instead of `MagicMock` for mocking async functions — mixing them up causes `TypeError` at runtime.
- **Mock `asyncio.sleep` for time travel testing** — record delay values to verify backoff logic without actually waiting.
- **Wrap concurrent operations with `asyncio.wait_for()`** to detect deadlocks as loud timeout failures rather than silent hangs.
- **Create fresh resources per test via fixtures** and tear them down completely, including draining queues and cancelling tasks.
- The fundamental **trade-off** in async testing is between realism (real concurrency, real timing) and speed/determinism (mocked time, isolated resources). Use unit tests for the latter and integration tests for the former.
"""),

    ("async/performance-optimization",
     r"""How do you optimize async Python application performance with connection pooling, semaphores for rate limiting, batching strategies, profiling async code, and identifying common async bottlenecks""",
     r"""# Async Python Performance Optimization

Performance optimization for async Python applications is fundamentally different from optimizing synchronous code. In synchronous programs, bottlenecks are usually CPU-bound operations. In async programs, the bottlenecks are almost always **I/O-bound waits and scheduling overhead**. Understanding this distinction is critical **because** the tools and techniques for optimizing each are entirely different. This guide covers the most impactful optimization strategies for production async Python systems.

## Connection Pooling

Connection pooling is the single most impactful optimization for most async applications. Creating a new TCP connection for every request involves DNS resolution, TCP handshake, and potentially TLS negotiation — easily 50-200ms of overhead. A connection pool amortizes this cost across many requests:

```python
import asyncio
from typing import Any, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
import time

@dataclass
class PooledConnection:
    # Represents a reusable connection with health tracking
    id: int
    created_at: float = field(default_factory=time.monotonic)
    last_used: float = field(default_factory=time.monotonic)
    request_count: int = 0

    @property
    def age_seconds(self) -> float:
        return time.monotonic() - self.created_at

    @property
    def idle_seconds(self) -> float:
        return time.monotonic() - self.last_used

class AsyncConnectionPool:
    # A production-grade async connection pool with health checks and eviction

    def __init__(
        self,
        min_size: int = 2,
        max_size: int = 20,
        max_idle_seconds: float = 300.0,
        max_lifetime_seconds: float = 3600.0,
        connection_timeout: float = 10.0,
    ) -> None:
        self._min_size = min_size
        self._max_size = max_size
        self._max_idle = max_idle_seconds
        self._max_lifetime = max_lifetime_seconds
        self._connection_timeout = connection_timeout
        self._pool: asyncio.Queue[PooledConnection] = asyncio.Queue(maxsize=max_size)
        self._size = 0
        self._semaphore = asyncio.Semaphore(max_size)
        self._next_id = 0

    async def initialize(self) -> None:
        # Pre-warm the pool with min_size connections
        for _ in range(self._min_size):
            conn = await self._create_connection()
            await self._pool.put(conn)

    async def _create_connection(self) -> PooledConnection:
        self._next_id += 1
        self._size += 1
        # Simulate actual connection creation (TCP, TLS, etc.)
        await asyncio.sleep(0.01)
        return PooledConnection(id=self._next_id)

    def _is_healthy(self, conn: PooledConnection) -> bool:
        if conn.age_seconds > self._max_lifetime:
            return False
        if conn.idle_seconds > self._max_idle:
            return False
        return True

    @asynccontextmanager
    async def acquire(self) -> AsyncIterator[PooledConnection]:
        await self._semaphore.acquire()
        try:
            conn = await self._get_healthy_connection()
            conn.last_used = time.monotonic()
            conn.request_count += 1
            try:
                yield conn
            finally:
                if self._is_healthy(conn):
                    await self._pool.put(conn)
                else:
                    self._size -= 1
        finally:
            self._semaphore.release()

    async def _get_healthy_connection(self) -> PooledConnection:
        while True:
            try:
                conn = self._pool.get_nowait()
                if self._is_healthy(conn):
                    return conn
                self._size -= 1
            except asyncio.QueueEmpty:
                return await asyncio.wait_for(
                    self._create_connection(),
                    timeout=self._connection_timeout,
                )

    async def close(self) -> None:
        while not self._pool.empty():
            try:
                self._pool.get_nowait()
                self._size -= 1
            except asyncio.QueueEmpty:
                break
```

**Best practice** is to set `min_size` to handle your baseline traffic without creating connections on-demand, and `max_size` to your downstream service's connection limit. A **common mistake** is setting `max_size` too high, which can overwhelm databases — most databases perform worse with hundreds of connections than with a well-tuned pool of 20-50.

## Semaphores for Rate Limiting

Semaphores are the primary tool for limiting concurrency in async code. They serve two critical purposes: **rate limiting** (preventing API abuse) and **resource protection** (preventing resource exhaustion):

```python
import asyncio
import time
from typing import TypeVar, Callable, Awaitable, Any

T = TypeVar("T")

class RateLimiter:
    # Token bucket rate limiter using asyncio semaphore

    def __init__(
        self,
        max_concurrent: int = 10,
        requests_per_second: float = 50.0,
    ) -> None:
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._rate = requests_per_second
        self._min_interval = 1.0 / requests_per_second
        self._last_request = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        await self._semaphore.acquire()
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request = time.monotonic()

    def release(self) -> None:
        self._semaphore.release()

    async def execute(
        self,
        func: Callable[..., Awaitable[T]],
        *args: Any,
        **kwargs: Any,
    ) -> T:
        await self.acquire()
        try:
            return await func(*args, **kwargs)
        finally:
            self.release()

# Usage: process 1000 API calls with max 10 concurrent, 50/sec
async def fetch_all_users(user_ids: list[int]) -> list[dict[str, Any]]:
    limiter = RateLimiter(max_concurrent=10, requests_per_second=50.0)

    async def fetch_user(uid: int) -> dict[str, Any]:
        await asyncio.sleep(0.05)  # Simulate API call
        return {"id": uid, "name": f"User_{uid}"}

    tasks = [limiter.execute(fetch_user, uid) for uid in user_ids]
    return await asyncio.gather(*tasks)
```

The **trade-off** with rate limiting is throughput versus safety. Too aggressive a rate limit wastes capacity; too lenient and you risk being throttled or banned by upstream services. **Therefore**, start conservative and increase based on monitoring data.

## Batching Strategies

Batching transforms many small operations into fewer large ones, dramatically reducing per-operation overhead. This is especially impactful for database writes and API calls:

```python
import asyncio
from typing import TypeVar, Generic, Callable, Awaitable, Any
from dataclasses import dataclass

T = TypeVar("T")
R = TypeVar("R")

class AsyncBatcher(Generic[T, R]):
    # Collects individual items and processes them in batches.
    # Each caller gets their individual result back despite batch execution.

    def __init__(
        self,
        batch_handler: Callable[[list[T]], Awaitable[list[R]]],
        max_batch_size: int = 50,
        max_wait_seconds: float = 0.05,
    ) -> None:
        self._handler = batch_handler
        self._max_size = max_batch_size
        self._max_wait = max_wait_seconds
        self._pending: list[tuple[T, asyncio.Future[R]]] = []
        self._lock = asyncio.Lock()
        self._flush_task: asyncio.Task[None] | None = None

    async def submit(self, item: T) -> R:
        future: asyncio.Future[R] = asyncio.get_event_loop().create_future()

        async with self._lock:
            self._pending.append((item, future))

            if len(self._pending) >= self._max_size:
                batch = self._pending[:]
                self._pending.clear()
                asyncio.create_task(self._process_batch(batch))
            elif self._flush_task is None or self._flush_task.done():
                self._flush_task = asyncio.create_task(self._timed_flush())

        return await future

    async def _timed_flush(self) -> None:
        await asyncio.sleep(self._max_wait)
        async with self._lock:
            if self._pending:
                batch = self._pending[:]
                self._pending.clear()
                await self._process_batch(batch)

    async def _process_batch(
        self, batch: list[tuple[T, asyncio.Future[R]]]
    ) -> None:
        items = [item for item, _ in batch]
        futures = [fut for _, fut in batch]
        try:
            results = await self._handler(items)
            for fut, result in zip(futures, results):
                if not fut.done():
                    fut.set_result(result)
        except Exception as exc:
            for fut in futures:
                if not fut.done():
                    fut.set_exception(exc)

# Example: batch database inserts
async def batch_insert(records: list[dict[str, Any]]) -> list[int]:
    # Simulate bulk insert returning IDs
    await asyncio.sleep(0.01)
    return list(range(len(records)))

batcher = AsyncBatcher(batch_insert, max_batch_size=100, max_wait_seconds=0.05)
```

**However**, batching introduces latency for individual requests — each item waits up to `max_wait_seconds` for the batch to fill. This is a deliberate **trade-off**: individual latency increases slightly, but aggregate throughput improves dramatically. For a system handling 10,000 database writes per second, batching can reduce the number of actual database round-trips from 10,000 to 100.

## Profiling Async Code

Profiling async code requires specialized tools **because** standard profilers measure wall-clock time, which includes time spent waiting on I/O (not useful for optimization). What you want to measure is: where does the event loop spend time, and which coroutines block it?

```python
import asyncio
import time
from typing import Any, Callable, Awaitable
from functools import wraps
from contextlib import asynccontextmanager
from typing import AsyncIterator

class AsyncProfiler:
    # Lightweight profiler for async operations

    def __init__(self) -> None:
        self._timings: dict[str, list[float]] = {}

    def track(self, name: str) -> Callable:
        # Decorator for tracking coroutine execution time
        def decorator(func: Callable[..., Awaitable[Any]]) -> Callable[..., Awaitable[Any]]:
            @wraps(func)
            async def wrapper(*args: Any, **kwargs: Any) -> Any:
                start = time.perf_counter()
                try:
                    return await func(*args, **kwargs)
                finally:
                    elapsed = time.perf_counter() - start
                    self._timings.setdefault(name, []).append(elapsed)
            return wrapper
        return decorator

    @asynccontextmanager
    async def measure(self, name: str) -> AsyncIterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            elapsed = time.perf_counter() - start
            self._timings.setdefault(name, []).append(elapsed)

    def report(self) -> dict[str, dict[str, float]]:
        result: dict[str, dict[str, float]] = {}
        for name, times in self._timings.items():
            sorted_times = sorted(times)
            n = len(sorted_times)
            result[name] = {
                "count": n,
                "total": sum(sorted_times),
                "mean": sum(sorted_times) / n,
                "p50": sorted_times[n // 2],
                "p95": sorted_times[int(n * 0.95)] if n >= 20 else sorted_times[-1],
                "p99": sorted_times[int(n * 0.99)] if n >= 100 else sorted_times[-1],
                "max": sorted_times[-1],
            }
        return result

# Detect event loop blocking
def install_slow_callback_detector(threshold_ms: float = 100.0) -> None:
    # Warns when a callback blocks the event loop too long
    loop = asyncio.get_event_loop()
    loop.slow_callback_duration = threshold_ms / 1000.0
    # asyncio will log warnings for callbacks exceeding this threshold
```

The **pitfall** most developers encounter is accidentally blocking the event loop with synchronous operations — CPU-heavy computation, synchronous file I/O, or DNS resolution. These show up as high `slow_callback_duration` warnings. **Best practice** is to offload blocking work to a thread pool using `asyncio.to_thread()` (Python 3.9+) or `loop.run_in_executor()`.

## Common Async Bottlenecks

Here are the most frequent performance problems in async Python applications, ranked by how often they occur in production:

1. **Missing connection pooling**: Creating new connections per request adds 50-200ms overhead each time.
2. **Event loop blocking**: Synchronous I/O or CPU work in a coroutine starves all other tasks.
3. **Excessive task creation**: Spawning millions of tasks overwhelms the scheduler. Use semaphores to bound concurrency.
4. **Unbounded gather**: `asyncio.gather(*huge_list)` creates all tasks immediately. Use batching or semaphores.
5. **DNS resolution**: `getaddrinfo()` is synchronous by default in many libraries. Use `aiodns` for async DNS.

A **common mistake** is assuming that making code async automatically makes it faster. Async improves **throughput** for I/O-bound workloads by overlapping waits, but it adds scheduling overhead. For CPU-bound tasks, async is slower than synchronous code. **Therefore**, only use async where you have genuine I/O concurrency to exploit.

## Summary / Key Takeaways

- **Connection pooling** is typically the highest-impact optimization — pre-create and reuse connections to eliminate per-request setup costs.
- **Use semaphores for concurrency control** to prevent overwhelming downstream services while maximizing throughput within safe limits.
- **Batching transforms many small operations into few large ones**, trading individual latency for aggregate throughput improvement.
- **Profile async code with purpose-built tools** that distinguish I/O wait time from actual processing time; use `slow_callback_duration` to detect event loop blocking.
- **Offload blocking work to thread pools** with `asyncio.to_thread()` — never perform synchronous I/O or heavy CPU work inside a coroutine.
- The fundamental **trade-off** in async performance is between concurrency (doing many things at once) and overhead (scheduler, task creation, context switching). Profile to find the optimal balance for your workload.
"""),

]
