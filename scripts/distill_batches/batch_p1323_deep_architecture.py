"""Deep reasoning training pairs: software architecture with extended think blocks."""

PAIRS = [
    (
        "deep_reasoning/connection-pool-health-checks",
        r'''Design a connection pool in Python with health checks, max connections, connection timeout, and connection stealing from idle holders.''',
        r'''<think>
The key constraint is thread safety — multiple threads will request connections concurrently,
so all pool state must be protected. I also need to handle the lifecycle: create, validate,
lend, reclaim, destroy.

Trade-off: I could use a simple list with a lock, but a threading.Condition gives me
blocking-with-timeout semantics for free. A queue would work too, but I need to inspect
connections for health checks, which queues make awkward.

Interface should be:
- Pool(factory, max_size, timeout, health_check, idle_threshold)
- pool.acquire(timeout) -> Connection
- pool.release(conn)
- Context manager support for auto-release

Failure modes:
1. Health check fails on acquire — discard and create fresh
2. All connections busy and max reached — block up to timeout, then raise
3. Connection stolen from idle holder — the holder must handle InvalidConnection gracefully
4. Factory raises during creation — propagate, don't corrupt pool state

I'll use a Condition variable pattern because it lets waiters sleep until a connection
is returned or a slot opens up. For stealing, I'll track which thread holds each connection
and how long it's been idle (last_used timestamp). If a waiter times out but there's a
connection held by a thread that hasn't used it beyond idle_threshold, we can forcibly
reclaim it and mark the old wrapper as invalid.

The connection wrapper is important — I won't hand out raw connections. Instead, a
PooledConnection proxy that tracks validity. When stolen, the proxy is marked invalid
so the original holder gets a clear error on next use.
</think>

```python
import threading
import time
import logging
from typing import Callable, Optional, Any

logger = logging.getLogger(__name__)


class InvalidConnection(Exception):
    """Raised when using a connection that was stolen or invalidated."""
    pass


class PoolExhausted(Exception):
    """Raised when no connection is available within the timeout."""
    pass


class PooledConnection:
    """Proxy wrapper that can be invalidated when stolen."""

    def __init__(self, raw_conn: Any, pool: "ConnectionPool"):
        self._raw = raw_conn
        self._pool = pool
        self._valid = True
        self._last_used = time.monotonic()
        self._holder_thread = threading.current_thread().ident

    @property
    def valid(self) -> bool:
        return self._valid

    def invalidate(self):
        self._valid = False

    def execute(self, *args, **kwargs):
        if not self._valid:
            raise InvalidConnection("This connection was reclaimed by the pool")
        self._last_used = time.monotonic()
        return self._raw.execute(*args, **kwargs)

    def __getattr__(self, name: str):
        if not self._valid:
            raise InvalidConnection("This connection was reclaimed by the pool")
        self._last_used = time.monotonic()
        return getattr(self._raw, name)


class ConnectionPool:
    def __init__(
        self,
        factory: Callable[[], Any],
        max_size: int = 10,
        acquire_timeout: float = 5.0,
        health_check: Optional[Callable[[Any], bool]] = None,
        idle_steal_threshold: float = 30.0,
    ):
        self._factory = factory
        self._max_size = max_size
        self._acquire_timeout = acquire_timeout
        self._health_check = health_check or (lambda c: True)
        self._idle_steal_threshold = idle_steal_threshold

        self._lock = threading.Condition()
        self._idle: list[PooledConnection] = []
        self._in_use: dict[int, PooledConnection] = {}  # id -> PooledConnection
        self._total_created = 0
        self._closed = False

    def acquire(self, timeout: Optional[float] = None) -> PooledConnection:
        timeout = timeout if timeout is not None else self._acquire_timeout
        deadline = time.monotonic() + timeout

        with self._lock:
            while True:
                if self._closed:
                    raise PoolExhausted("Pool is closed")

                # Try to get a healthy idle connection
                while self._idle:
                    conn = self._idle.pop()
                    try:
                        if self._health_check(conn._raw):
                            conn._holder_thread = threading.current_thread().ident
                            conn._last_used = time.monotonic()
                            self._in_use[id(conn)] = conn
                            return conn
                    except Exception:
                        pass
                    # Health check failed, discard
                    self._total_created -= 1
                    logger.debug("Discarded unhealthy connection, pool size now %d", self._total_created)

                # Try to create a new connection
                if self._total_created < self._max_size:
                    try:
                        raw = self._factory()
                        self._total_created += 1
                        conn = PooledConnection(raw, self)
                        self._in_use[id(conn)] = conn
                        return conn
                    except Exception as e:
                        logger.error("Failed to create connection: %s", e)
                        raise

                # Try to steal from idle holders
                stolen = self._try_steal()
                if stolen is not None:
                    stolen._holder_thread = threading.current_thread().ident
                    stolen._last_used = time.monotonic()
                    self._in_use[id(stolen)] = stolen
                    return stolen

                # Wait for a connection to be released
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PoolExhausted(
                        f"No connection available within {timeout}s "
                        f"(max={self._max_size}, in_use={len(self._in_use)})"
                    )
                self._lock.wait(timeout=remaining)

    def _try_steal(self) -> Optional[PooledConnection]:
        """Steal the longest-idle in-use connection if it exceeds threshold."""
        now = time.monotonic()
        candidates = [
            (conn, now - conn._last_used)
            for conn in self._in_use.values()
            if (now - conn._last_used) > self._idle_steal_threshold
        ]
        if not candidates:
            return None

        # Steal the one idle longest
        candidates.sort(key=lambda x: x[1], reverse=True)
        victim = candidates[0][0]

        # Invalidate the old wrapper, create new wrapper for same raw conn
        del self._in_use[id(victim)]
        victim.invalidate()
        logger.warning(
            "Stole connection from thread %s (idle %.1fs)",
            victim._holder_thread,
            now - victim._last_used,
        )

        # Re-check health before handing out
        try:
            if self._health_check(victim._raw):
                new_conn = PooledConnection(victim._raw, self)
                return new_conn
        except Exception:
            pass

        # Stolen connection is unhealthy, discard it
        self._total_created -= 1
        return None

    def release(self, conn: PooledConnection):
        with self._lock:
            key = id(conn)
            if key in self._in_use:
                del self._in_use[key]
                if conn.valid and not self._closed:
                    self._idle.append(conn)
                else:
                    self._total_created -= 1
                self._lock.notify()

    def close(self):
        with self._lock:
            self._closed = True
            for conn in self._idle:
                conn.invalidate()
            for conn in self._in_use.values():
                conn.invalidate()
            self._idle.clear()
            self._in_use.clear()
            self._total_created = 0
            self._lock.notify_all()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "total": self._total_created,
                "idle": len(self._idle),
                "in_use": len(self._in_use),
                "max_size": self._max_size,
            }


class managed_connection:
    """Context manager for automatic acquire/release."""

    def __init__(self, pool: ConnectionPool, timeout: Optional[float] = None):
        self._pool = pool
        self._timeout = timeout
        self._conn = None

    def __enter__(self) -> PooledConnection:
        self._conn = self._pool.acquire(self._timeout)
        return self._conn

    def __exit__(self, *exc):
        if self._conn is not None:
            self._pool.release(self._conn)


# --- Usage and edge case testing ---

class FakeConnection:
    def __init__(self, conn_id):
        self.conn_id = conn_id
        self.healthy = True

    def execute(self, query):
        return f"Result from conn-{self.conn_id}: {query}"

    def ping(self):
        return self.healthy


def test_pool():
    counter = {"n": 0}

    def factory():
        counter["n"] += 1
        return FakeConnection(counter["n"])

    def health_check(raw_conn):
        return raw_conn.ping()

    pool = ConnectionPool(
        factory=factory,
        max_size=2,
        acquire_timeout=1.0,
        health_check=health_check,
        idle_steal_threshold=0.5,
    )

    # Basic acquire/release
    with managed_connection(pool) as conn:
        result = conn.execute("SELECT 1")
        assert "conn-1" in result
    assert pool.stats["idle"] == 1

    # Exhaust pool and test timeout
    c1 = pool.acquire()
    c2 = pool.acquire()
    assert pool.stats["in_use"] == 2
    try:
        pool.acquire(timeout=0.1)
        assert False, "Should have raised"
    except PoolExhausted:
        pass  # Expected

    # Test stealing: simulate c1 going idle
    c1._last_used = time.monotonic() - 10
    c3 = pool.acquire(timeout=2.0)  # Should steal c1
    assert not c1.valid
    try:
        c1.execute("SELECT fail")
        assert False, "Should have raised"
    except InvalidConnection:
        pass  # Expected — stolen connection

    # Test unhealthy connection discard
    pool.release(c2)
    pool.release(c3)
    for c in pool._idle:
        c._raw.healthy = False
    conn = pool.acquire()  # Discards unhealthy, creates new
    assert conn._raw.healthy
    pool.release(conn)

    pool.close()
    print("All connection pool tests passed.")


if __name__ == "__main__":
    test_pool()
```'''
    ),
    (
        "deep_reasoning/circuit-breaker-half-open",
        r'''Implement a circuit breaker pattern in Python with closed, open, and half-open states. Include failure threshold, success threshold for half-open recovery, configurable reset timer, and per-operation timeout.''',
        r'''<think>
The circuit breaker is a stability pattern — it prevents cascading failures by stopping
calls to a failing service. Three states: CLOSED (normal), OPEN (failing, reject calls),
HALF_OPEN (testing recovery).

Key constraints:
1. Thread safety — multiple threads call through the breaker concurrently
2. State transitions must be atomic — two threads shouldn't both transition to HALF_OPEN
3. The timer for OPEN->HALF_OPEN is wall-clock based, not call-count based

Trade-off: I could use an enum + lock, or a state machine with state objects. State objects
are cleaner for extensibility (adding states like FORCED_OPEN) but heavier. Since we have
only 3 states, an enum with a single lock is simpler and sufficient.

Interface:
- CircuitBreaker(failure_threshold, success_threshold, reset_timeout, call_timeout)
- breaker.call(fn, *args, **kwargs) -> result
- breaker.state -> CircuitState
- Decorator form: @circuit_breaker(...)

Failure modes:
- What if the half-open test call hangs? Need per-call timeout.
- What if failures happen in bursts? Use a sliding window, not lifetime count.
- What if the service partially recovers? success_threshold in HALF_OPEN requires
  N consecutive successes before closing.

I'll use a sliding window for failure counting — only recent failures matter. When open,
a timer controls when to try half-open. In half-open, limit concurrency to 1 test call
at a time to avoid flooding a recovering service.
</think>

```python
import threading
import time
import functools
from enum import Enum
from typing import Callable, Any, Optional
from collections import deque
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when the circuit is open and rejecting calls."""
    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f"Circuit is OPEN. Retry after {retry_after:.1f}s")


class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        success_threshold: int = 2,
        reset_timeout: float = 30.0,
        call_timeout: float = 10.0,
        failure_window: float = 60.0,
    ):
        self._failure_threshold = failure_threshold
        self._success_threshold = success_threshold
        self._reset_timeout = reset_timeout
        self._call_timeout = call_timeout
        self._failure_window = failure_window

        self._lock = threading.Lock()
        self._state = CircuitState.CLOSED
        self._failures: deque[float] = deque()  # timestamps of recent failures
        self._half_open_successes = 0
        self._opened_at: float = 0
        self._half_open_in_progress = False

        self._executor = ThreadPoolExecutor(max_workers=4)
        self._listeners: list[Callable[[CircuitState, CircuitState], None]] = []

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                if time.monotonic() - self._opened_at >= self._reset_timeout:
                    self._transition(CircuitState.HALF_OPEN)
            return self._state

    def _transition(self, new_state: CircuitState):
        old = self._state
        if old == new_state:
            return
        self._state = new_state
        if new_state == CircuitState.HALF_OPEN:
            self._half_open_successes = 0
            self._half_open_in_progress = False
        elif new_state == CircuitState.CLOSED:
            self._failures.clear()
            self._half_open_in_progress = False
        elif new_state == CircuitState.OPEN:
            self._opened_at = time.monotonic()
            self._half_open_in_progress = False
        for listener in self._listeners:
            try:
                listener(old, new_state)
            except Exception:
                pass

    def _prune_old_failures(self):
        cutoff = time.monotonic() - self._failure_window
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()

    def _record_failure(self):
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._transition(CircuitState.OPEN)
                return

            self._failures.append(time.monotonic())
            self._prune_old_failures()
            if len(self._failures) >= self._failure_threshold:
                self._transition(CircuitState.OPEN)

    def _record_success(self):
        with self._lock:
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                self._half_open_in_progress = False
                if self._half_open_successes >= self._success_threshold:
                    self._transition(CircuitState.CLOSED)

    def call(self, fn: Callable, *args, **kwargs) -> Any:
        with self._lock:
            # Check for OPEN -> HALF_OPEN transition
            if self._state == CircuitState.OPEN:
                elapsed = time.monotonic() - self._opened_at
                if elapsed >= self._reset_timeout:
                    self._transition(CircuitState.HALF_OPEN)
                else:
                    raise CircuitOpenError(self._reset_timeout - elapsed)

            if self._state == CircuitState.HALF_OPEN:
                if self._half_open_in_progress:
                    raise CircuitOpenError(1.0)  # another test in flight
                self._half_open_in_progress = True

        # Execute with timeout
        try:
            future = self._executor.submit(fn, *args, **kwargs)
            result = future.result(timeout=self._call_timeout)
            self._record_success()
            return result
        except FuturesTimeout:
            self._record_failure()
            raise TimeoutError(f"Call timed out after {self._call_timeout}s")
        except CircuitOpenError:
            raise
        except Exception as e:
            self._record_failure()
            raise

    def on_state_change(self, listener: Callable[[CircuitState, CircuitState], None]):
        self._listeners.append(listener)

    def reset(self):
        with self._lock:
            self._transition(CircuitState.CLOSED)


def circuit_breaker(**kwargs):
    """Decorator form of CircuitBreaker."""
    breaker = CircuitBreaker(**kwargs)

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kw):
            return breaker.call(fn, *args, **kw)
        wrapper.breaker = breaker
        return wrapper
    return decorator


# --- Usage and tests ---

def test_circuit_breaker():
    state_changes = []

    breaker = CircuitBreaker(
        failure_threshold=3,
        success_threshold=2,
        reset_timeout=0.5,
        call_timeout=1.0,
        failure_window=10.0,
    )
    breaker.on_state_change(lambda old, new: state_changes.append((old, new)))

    call_count = {"n": 0}

    def flaky_service(succeed: bool):
        call_count["n"] += 1
        if not succeed:
            raise ConnectionError("Service down")
        return "ok"

    # 3 failures should open the circuit
    for _ in range(3):
        try:
            breaker.call(flaky_service, False)
        except ConnectionError:
            pass
    assert breaker.state == CircuitState.OPEN

    # Calls should be rejected while open
    try:
        breaker.call(flaky_service, True)
        assert False, "Should have raised"
    except CircuitOpenError as e:
        assert e.retry_after > 0

    # Wait for reset timeout, circuit goes to HALF_OPEN
    time.sleep(0.6)
    assert breaker.state == CircuitState.HALF_OPEN

    # One success in half-open (need 2 to close)
    result = breaker.call(flaky_service, True)
    assert result == "ok"
    assert breaker.state == CircuitState.HALF_OPEN

    # Second success closes the circuit
    result = breaker.call(flaky_service, True)
    assert result == "ok"
    assert breaker.state == CircuitState.CLOSED

    # Verify state transitions were recorded
    assert (CircuitState.CLOSED, CircuitState.OPEN) in state_changes
    assert (CircuitState.OPEN, CircuitState.HALF_OPEN) in state_changes
    assert (CircuitState.HALF_OPEN, CircuitState.CLOSED) in state_changes

    # Test failure in half-open goes back to open
    breaker2 = CircuitBreaker(failure_threshold=1, reset_timeout=0.2, call_timeout=1.0)
    try:
        breaker2.call(flaky_service, False)
    except ConnectionError:
        pass
    assert breaker2.state == CircuitState.OPEN
    time.sleep(0.3)
    try:
        breaker2.call(flaky_service, False)  # half-open test fails
    except ConnectionError:
        pass
    assert breaker2.state == CircuitState.OPEN

    print("All circuit breaker tests passed.")


if __name__ == "__main__":
    test_circuit_breaker()
```'''
    ),
    (
        "deep_reasoning/pubsub-topic-filtering-replay",
        r'''Build a pub/sub system in Python with topic filtering via glob patterns, persistent subscriptions that survive reconnect, and message replay from a configurable history buffer.''',
        r'''<think>
This is an in-process pub/sub — not distributed, but needs to handle the same semantics:
topic routing, durable subscriptions, and replay.

Key design decisions:
1. Topic matching — glob patterns (e.g., "orders.*", "events.**") are intuitive. I'll use
   fnmatch-style matching. "**" matches multiple levels (orders.us.east), "*" matches one.
2. Persistent subscriptions — a subscription outlives the subscriber. Messages arriving while
   disconnected queue up. On reconnect, the subscriber gets missed messages.
3. Replay — maintain a ring buffer per topic. New subscribers can request replay of last N
   messages or messages since a timestamp.

Trade-off: storing messages per-topic vs globally. Per-topic is simpler for replay but uses
more memory. Global store with topic index would be more memory-efficient but adds complexity.
Since this is in-process, per-topic ring buffer is fine.

Interface:
- PubSub()
- pubsub.publish(topic, message) -> message_id
- pubsub.subscribe(subscriber_id, pattern, handler) -> Subscription
- subscription.pause() / subscription.resume()
- pubsub.replay(subscriber_id, topic, since=timestamp|count)

Failure mode: what if a handler raises? Don't kill the publisher. Log the error, optionally
dead-letter the message, continue to other subscribers.

Threading: publishers and subscribers may be on different threads. Use a lock for the
subscription registry and per-subscription queues. Message delivery can be sync or async —
I'll use a delivery thread per active subscription for non-blocking publish.
</think>

```python
import threading
import time
import fnmatch
import logging
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional, Any

logger = logging.getLogger(__name__)


@dataclass
class Message:
    id: str
    topic: str
    payload: Any
    timestamp: float
    headers: dict = field(default_factory=dict)


@dataclass
class Subscription:
    subscriber_id: str
    pattern: str
    handler: Callable[[Message], None]
    active: bool = True
    pending: deque = field(default_factory=deque)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def matches(self, topic: str) -> bool:
        # Convert topic.subtopic to path-like for matching
        # "**" matches multiple segments, "*" matches one
        pattern = self.pattern.replace(".", "/")
        topic_path = topic.replace(".", "/")
        # Handle ** for recursive matching
        if "**" in pattern:
            pattern = pattern.replace("**", "*/*/*/*")  # crude multi-level
        return fnmatch.fnmatch(topic_path, pattern)

    def pause(self):
        with self._lock:
            self.active = False

    def resume(self):
        with self._lock:
            self.active = True


class PubSub:
    def __init__(self, history_size: int = 1000):
        self._lock = threading.Lock()
        self._subscriptions: dict[str, list[Subscription]] = {}  # subscriber_id -> list
        self._history: dict[str, deque[Message]] = {}  # topic -> ring buffer
        self._history_size = history_size
        self._global_history: deque[Message] = deque(maxlen=history_size * 10)
        self._dead_letters: deque[tuple[Message, str, Exception]] = deque(maxlen=100)
        self._delivery_threads: dict[str, threading.Thread] = {}
        self._running = True

    def publish(self, topic: str, payload: Any, headers: Optional[dict] = None) -> str:
        msg = Message(
            id=str(uuid.uuid4()),
            topic=topic,
            payload=payload,
            timestamp=time.time(),
            headers=headers or {},
        )

        with self._lock:
            # Store in history
            if topic not in self._history:
                self._history[topic] = deque(maxlen=self._history_size)
            self._history[topic].append(msg)
            self._global_history.append(msg)

            # Find matching subscriptions
            matching: list[Subscription] = []
            for sub_list in self._subscriptions.values():
                for sub in sub_list:
                    if sub.matches(topic):
                        matching.append(sub)

        # Deliver outside the lock
        for sub in matching:
            self._deliver(sub, msg)

        return msg.id

    def _deliver(self, sub: Subscription, msg: Message):
        with sub._lock:
            if sub.active:
                try:
                    sub.handler(msg)
                except Exception as e:
                    logger.error("Handler error for %s on %s: %s", sub.subscriber_id, msg.topic, e)
                    self._dead_letters.append((msg, sub.subscriber_id, e))
            else:
                # Subscriber paused — queue for later
                sub.pending.append(msg)

    def subscribe(
        self,
        subscriber_id: str,
        pattern: str,
        handler: Callable[[Message], None],
    ) -> Subscription:
        sub = Subscription(
            subscriber_id=subscriber_id,
            pattern=pattern,
            handler=handler,
        )
        with self._lock:
            if subscriber_id not in self._subscriptions:
                self._subscriptions[subscriber_id] = []
            self._subscriptions[subscriber_id].append(sub)
        return sub

    def unsubscribe(self, subscriber_id: str):
        with self._lock:
            self._subscriptions.pop(subscriber_id, None)

    def replay(
        self,
        topic_pattern: str,
        handler: Callable[[Message], None],
        since: Optional[float] = None,
        last_n: Optional[int] = None,
    ) -> list[Message]:
        """Replay historical messages matching topic pattern."""
        messages = []
        with self._lock:
            for topic, history in self._history.items():
                # Check if topic matches pattern
                test_sub = Subscription("_replay", topic_pattern, handler)
                if not test_sub.matches(topic):
                    continue
                for msg in history:
                    if since is not None and msg.timestamp < since:
                        continue
                    messages.append(msg)

        messages.sort(key=lambda m: m.timestamp)
        if last_n is not None:
            messages = messages[-last_n:]

        for msg in messages:
            try:
                handler(msg)
            except Exception as e:
                logger.error("Replay handler error: %s", e)

        return messages

    def drain_pending(self, subscriber_id: str):
        """Deliver all messages queued while subscriber was paused."""
        with self._lock:
            subs = self._subscriptions.get(subscriber_id, [])

        for sub in subs:
            with sub._lock:
                while sub.pending and sub.active:
                    msg = sub.pending.popleft()
                    try:
                        sub.handler(msg)
                    except Exception as e:
                        logger.error("Drain error: %s", e)
                        self._dead_letters.append((msg, subscriber_id, e))

    @property
    def dead_letters(self):
        return list(self._dead_letters)


# --- Usage and tests ---

def test_pubsub():
    bus = PubSub(history_size=100)
    received = {"orders": [], "all": [], "errors": []}

    # Subscribe to specific topic
    bus.subscribe("order-svc", "orders.*", lambda m: received["orders"].append(m))
    # Subscribe to all events
    bus.subscribe("logger", "**", lambda m: received["all"].append(m))

    # Publish messages
    bus.publish("orders.created", {"order_id": 1, "amount": 99.99})
    bus.publish("orders.shipped", {"order_id": 1})
    bus.publish("users.signup", {"user_id": 42})

    assert len(received["orders"]) == 2  # orders.created + orders.shipped
    assert len(received["all"]) == 3      # everything

    # Test pause/resume (persistent subscription)
    sub = bus.subscribe("analytics", "orders.*", lambda m: received["errors"].append(m))
    sub.pause()
    bus.publish("orders.cancelled", {"order_id": 2})
    assert len(received["errors"]) == 0  # paused, message is queued
    assert len(sub.pending) == 1

    sub.resume()
    bus.drain_pending("analytics")
    assert len(received["errors"]) == 1  # now delivered

    # Test replay
    replayed = []
    bus.replay("orders.*", lambda m: replayed.append(m), last_n=2)
    assert len(replayed) == 2  # last 2 order messages

    # Test error handling in handler
    def bad_handler(msg):
        raise ValueError("Handler crashed")

    bus.subscribe("crasher", "orders.*", bad_handler)
    bus.publish("orders.created", {"order_id": 3})  # should not raise
    assert len(bus.dead_letters) == 1

    print("All pub/sub tests passed.")


if __name__ == "__main__":
    test_pubsub()
```'''
    ),
    (
        "deep_reasoning/cqrs-event-sourcing",
        r'''Implement CQRS with event sourcing in Python. Include command validation, event store with append-only semantics, read model projection, and snapshotting for performance.''',
        r'''<think>
CQRS separates reads from writes. Event sourcing means the write side persists events, not
state. The read model is a projection rebuilt from events.

The architecture has these components:
1. Commands — intent to change state, validated before execution
2. Aggregates — domain objects that enforce invariants, emit events
3. Event Store — append-only log of events per aggregate
4. Projections — read models built by replaying events
5. Snapshots — periodic state snapshots to avoid replaying entire history

Key constraint: the event store must be append-only. No updates, no deletes. This gives us
a complete audit trail and enables temporal queries.

Trade-off: rebuilding read models from scratch on every query is correct but slow. Snapshots
help but add complexity. I'll implement snapshots every N events.

Interface:
- Command -> CommandHandler -> Aggregate -> Events -> EventStore
- EventStore -> Projector -> ReadModel
- aggregate.load(events) to rebuild state
- event_store.append(aggregate_id, events, expected_version) for optimistic concurrency

Failure mode: concurrent writes to the same aggregate. Two commands load version 5, both
try to append at version 6. The second must fail with a concurrency error. This is optimistic
locking via expected_version.

I'll keep this in-memory but design the EventStore interface so it could be backed by a
database. The Projector processes events into denormalized read models.
</think>

```python
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional
from abc import ABC, abstractmethod


# --- Events ---

@dataclass(frozen=True)
class Event:
    event_id: str
    aggregate_id: str
    event_type: str
    data: dict
    timestamp: float
    version: int


class ConcurrencyError(Exception):
    pass


class ValidationError(Exception):
    pass


# --- Event Store ---

class EventStore:
    def __init__(self, snapshot_interval: int = 10):
        self._streams: dict[str, list[Event]] = {}
        self._snapshots: dict[str, tuple[int, dict]] = {}  # agg_id -> (version, state)
        self._snapshot_interval = snapshot_interval
        self._all_events: list[Event] = []  # global ordered log
        self._subscribers: list = []

    def append(self, aggregate_id: str, events: list[Event], expected_version: int):
        stream = self._streams.get(aggregate_id, [])
        current_version = len(stream)

        if current_version != expected_version:
            raise ConcurrencyError(
                f"Expected version {expected_version}, "
                f"but aggregate {aggregate_id} is at version {current_version}"
            )

        for event in events:
            stream.append(event)
            self._all_events.append(event)

        self._streams[aggregate_id] = stream

        # Notify subscribers
        for sub in self._subscribers:
            for event in events:
                sub(event)

    def load_events(self, aggregate_id: str, after_version: int = 0) -> list[Event]:
        stream = self._streams.get(aggregate_id, [])
        return stream[after_version:]

    def save_snapshot(self, aggregate_id: str, version: int, state: dict):
        self._snapshots[aggregate_id] = (version, state)

    def load_snapshot(self, aggregate_id: str) -> Optional[tuple[int, dict]]:
        return self._snapshots.get(aggregate_id)

    def subscribe(self, handler):
        self._subscribers.append(handler)

    @property
    def should_snapshot(self):
        return self._snapshot_interval

    def get_all_events(self) -> list[Event]:
        return list(self._all_events)


# --- Aggregate ---

class Aggregate(ABC):
    def __init__(self, aggregate_id: str):
        self.id = aggregate_id
        self.version = 0
        self._pending_events: list[Event] = []

    def _apply_event(self, event: Event, is_new: bool = True):
        handler = getattr(self, f"_on_{event.event_type}", None)
        if handler:
            handler(event.data)
        if is_new:
            self._pending_events.append(event)
        self.version = event.version

    def _emit(self, event_type: str, data: dict):
        event = Event(
            event_id=str(uuid.uuid4()),
            aggregate_id=self.id,
            event_type=event_type,
            data=data,
            timestamp=time.time(),
            version=self.version + 1,
        )
        self._apply_event(event, is_new=True)

    def load_from_events(self, events: list[Event]):
        for event in events:
            self._apply_event(event, is_new=False)

    def load_from_snapshot(self, version: int, state: dict):
        self.version = version
        self._restore_state(state)

    @abstractmethod
    def _restore_state(self, state: dict):
        pass

    @abstractmethod
    def snapshot_state(self) -> dict:
        pass

    def get_pending_events(self) -> list[Event]:
        events = self._pending_events[:]
        self._pending_events.clear()
        return events


# --- Example: Bank Account Aggregate ---

class BankAccount(Aggregate):
    def __init__(self, aggregate_id: str):
        super().__init__(aggregate_id)
        self.balance = 0
        self.owner = ""
        self.is_open = False

    def open_account(self, owner: str, initial_deposit: float):
        if self.is_open:
            raise ValidationError("Account already open")
        if initial_deposit < 0:
            raise ValidationError("Initial deposit must be non-negative")
        self._emit("account_opened", {"owner": owner, "initial_deposit": initial_deposit})

    def deposit(self, amount: float):
        if not self.is_open:
            raise ValidationError("Account is not open")
        if amount <= 0:
            raise ValidationError("Deposit must be positive")
        self._emit("money_deposited", {"amount": amount})

    def withdraw(self, amount: float):
        if not self.is_open:
            raise ValidationError("Account is not open")
        if amount <= 0:
            raise ValidationError("Withdrawal must be positive")
        if amount > self.balance:
            raise ValidationError(f"Insufficient funds: balance={self.balance}, requested={amount}")
        self._emit("money_withdrawn", {"amount": amount})

    def _on_account_opened(self, data):
        self.owner = data["owner"]
        self.balance = data["initial_deposit"]
        self.is_open = True

    def _on_money_deposited(self, data):
        self.balance += data["amount"]

    def _on_money_withdrawn(self, data):
        self.balance -= data["amount"]

    def _restore_state(self, state: dict):
        self.balance = state["balance"]
        self.owner = state["owner"]
        self.is_open = state["is_open"]

    def snapshot_state(self) -> dict:
        return {"balance": self.balance, "owner": self.owner, "is_open": self.is_open}


# --- Read Model / Projection ---

class AccountSummaryProjection:
    """Denormalized read model for account summaries."""

    def __init__(self):
        self.accounts: dict[str, dict] = {}
        self.total_deposits = 0
        self.total_withdrawals = 0

    def handle_event(self, event: Event):
        handler = getattr(self, f"_on_{event.event_type}", None)
        if handler:
            handler(event)

    def _on_account_opened(self, event: Event):
        self.accounts[event.aggregate_id] = {
            "owner": event.data["owner"],
            "balance": event.data["initial_deposit"],
            "transaction_count": 1,
            "last_activity": event.timestamp,
        }

    def _on_money_deposited(self, event: Event):
        acct = self.accounts[event.aggregate_id]
        acct["balance"] += event.data["amount"]
        acct["transaction_count"] += 1
        acct["last_activity"] = event.timestamp
        self.total_deposits += event.data["amount"]

    def _on_money_withdrawn(self, event: Event):
        acct = self.accounts[event.aggregate_id]
        acct["balance"] -= event.data["amount"]
        acct["transaction_count"] += 1
        acct["last_activity"] = event.timestamp
        self.total_withdrawals += event.data["amount"]

    def get_account(self, account_id: str) -> Optional[dict]:
        return self.accounts.get(account_id)

    def get_stats(self) -> dict:
        return {
            "num_accounts": len(self.accounts),
            "total_deposits": self.total_deposits,
            "total_withdrawals": self.total_withdrawals,
        }


# --- Repository ---

class AccountRepository:
    def __init__(self, event_store: EventStore):
        self._store = event_store

    def load(self, account_id: str) -> BankAccount:
        account = BankAccount(account_id)
        snapshot = self._store.load_snapshot(account_id)
        if snapshot:
            version, state = snapshot
            account.load_from_snapshot(version, state)
            events = self._store.load_events(account_id, after_version=version)
        else:
            events = self._store.load_events(account_id)
        account.load_from_events(events)
        return account

    def save(self, account: BankAccount):
        events = account.get_pending_events()
        expected = account.version - len(events)
        self._store.append(account.id, events, expected)

        # Snapshot if needed
        if account.version % self._store.should_snapshot == 0:
            self._store.save_snapshot(account.id, account.version, account.snapshot_state())


# --- Usage and tests ---

def test_cqrs():
    store = EventStore(snapshot_interval=5)
    projection = AccountSummaryProjection()
    store.subscribe(projection.handle_event)
    repo = AccountRepository(store)

    # Command: open account
    acct = BankAccount("acct-001")
    acct.open_account("Alice", 100.0)
    repo.save(acct)

    # Command: deposit
    acct = repo.load("acct-001")
    acct.deposit(50.0)
    repo.save(acct)

    # Command: withdraw
    acct = repo.load("acct-001")
    acct.withdraw(30.0)
    repo.save(acct)

    # Read model query
    summary = projection.get_account("acct-001")
    assert summary["balance"] == 120.0
    assert summary["transaction_count"] == 3

    # Validation: overdraw
    acct = repo.load("acct-001")
    try:
        acct.withdraw(999.0)
        assert False, "Should have raised"
    except ValidationError as e:
        assert "Insufficient funds" in str(e)

    # Optimistic concurrency
    acct1 = repo.load("acct-001")
    acct2 = repo.load("acct-001")
    acct1.deposit(10.0)
    repo.save(acct1)
    acct2.deposit(20.0)
    try:
        repo.save(acct2)
        assert False, "Should have raised"
    except ConcurrencyError:
        pass  # Expected

    # Verify event store has full history
    events = store.load_events("acct-001")
    assert len(events) == 4  # opened, deposited, withdrawn, deposited
    assert events[0].event_type == "account_opened"

    # Test snapshot: do enough operations to trigger
    acct = repo.load("acct-001")
    acct.deposit(1.0)
    repo.save(acct)  # version=5, triggers snapshot

    snapshot = store.load_snapshot("acct-001")
    assert snapshot is not None
    version, state = snapshot
    assert version == 5
    assert state["balance"] == 131.0

    # Rebuild from snapshot
    acct_rebuilt = repo.load("acct-001")
    assert acct_rebuilt.balance == 131.0

    print("All CQRS event sourcing tests passed.")


if __name__ == "__main__":
    test_cqrs()
```'''
    ),
    (
        "deep_reasoning/distributed-task-scheduler",
        r'''Design a distributed task scheduler in Python supporting cron expressions, task persistence, leader election among scheduler nodes, and guaranteed at-least-once execution.''',
        r'''<think>
A distributed task scheduler must solve several hard problems:
1. Cron parsing — converting "*/5 * * * *" to actual fire times
2. Persistence — tasks survive restarts
3. Leader election — only one node fires each task
4. At-least-once — if the leader crashes mid-execution, another takes over

Key constraint: we need distributed coordination without requiring Kafka or ZooKeeper as
dependencies. I'll use a shared storage backend (abstracted) with atomic compare-and-swap
for leader election and task locking.

Trade-off: I could use a distributed lock per task (fine-grained) or a single leader that
owns all scheduling (coarse-grained). Single leader is simpler but creates a SPOF during
leader transitions. Per-task locking is more resilient but adds lock contention. I'll go
with single leader + fast failover since cron granularity is typically minutes.

Interface:
- Scheduler(node_id, store)
- scheduler.register(task_id, cron_expr, handler)
- scheduler.start() / scheduler.stop()
- store.acquire_leadership(node_id, ttl) -> bool
- store.get_pending_tasks(now) -> list

Failure modes:
- Leader crashes: heartbeat TTL expires, another node acquires leadership
- Task handler crashes: mark task as failed, retry with backoff
- Clock skew between nodes: use store's clock, not local time
- Duplicate execution during leader transition: idempotent handlers are caller's responsibility

I'll implement a simple cron parser supporting minute/hour/day/month/weekday with *, ranges,
and intervals. The in-memory store is replaceable with Redis or PostgreSQL.
</think>

```python
import threading
import time
import json
import re
from datetime import datetime
from typing import Callable, Optional, Any
from dataclasses import dataclass, field
from abc import ABC, abstractmethod


# --- Cron Parser ---

class CronExpression:
    """Parses cron expressions: minute hour day month weekday."""

    def __init__(self, expr: str):
        parts = expr.strip().split()
        if len(parts) != 5:
            raise ValueError(f"Cron expression must have 5 fields, got {len(parts)}: {expr}")
        self._minute = self._parse_field(parts[0], 0, 59)
        self._hour = self._parse_field(parts[1], 0, 23)
        self._day = self._parse_field(parts[2], 1, 31)
        self._month = self._parse_field(parts[3], 1, 12)
        self._weekday = self._parse_field(parts[4], 0, 6)

    def _parse_field(self, field: str, min_val: int, max_val: int) -> set[int]:
        values = set()
        for part in field.split(","):
            if part == "*":
                values.update(range(min_val, max_val + 1))
            elif "/" in part:
                base, step = part.split("/")
                start = min_val if base == "*" else int(base)
                values.update(range(start, max_val + 1, int(step)))
            elif "-" in part:
                lo, hi = part.split("-")
                values.update(range(int(lo), int(hi) + 1))
            else:
                values.add(int(part))
        return values

    def matches(self, dt: datetime) -> bool:
        return (
            dt.minute in self._minute
            and dt.hour in self._hour
            and dt.day in self._day
            and dt.month in self._month
            and dt.weekday() in self._weekday
        )

    def next_fire(self, after: datetime) -> datetime:
        """Find the next datetime matching the cron expression."""
        candidate = after.replace(second=0, microsecond=0)
        candidate = candidate.replace(minute=candidate.minute + 1) if candidate.minute < 59 else \
            candidate.replace(hour=candidate.hour + 1, minute=0) if candidate.hour < 23 else \
            candidate.replace(day=candidate.day + 1, hour=0, minute=0)
        # Brute force search up to 366 days ahead
        for _ in range(366 * 24 * 60):
            if self.matches(candidate):
                return candidate
            candidate = datetime(
                candidate.year, candidate.month, candidate.day,
                candidate.hour, candidate.minute
            )
            # Increment by 1 minute
            import calendar
            minute = candidate.minute + 1
            hour = candidate.hour
            day = candidate.day
            month = candidate.month
            year = candidate.year
            if minute >= 60:
                minute = 0
                hour += 1
            if hour >= 24:
                hour = 0
                day += 1
            max_day = calendar.monthrange(year, month)[1]
            if day > max_day:
                day = 1
                month += 1
            if month > 12:
                month = 1
                year += 1
            candidate = datetime(year, month, day, hour, minute)
        raise ValueError("No matching time found within 366 days")


# --- Store Interface ---

@dataclass
class TaskRecord:
    task_id: str
    cron_expr: str
    last_run: Optional[float] = None
    next_run: Optional[float] = None
    status: str = "idle"  # idle, running, failed
    retry_count: int = 0
    max_retries: int = 3
    locked_by: Optional[str] = None
    lock_until: Optional[float] = None


class SchedulerStore(ABC):
    @abstractmethod
    def acquire_leadership(self, node_id: str, ttl: float) -> bool: ...
    @abstractmethod
    def renew_leadership(self, node_id: str, ttl: float) -> bool: ...
    @abstractmethod
    def get_leader(self) -> Optional[str]: ...
    @abstractmethod
    def save_task(self, task: TaskRecord): ...
    @abstractmethod
    def get_due_tasks(self, now: float) -> list[TaskRecord]: ...
    @abstractmethod
    def lock_task(self, task_id: str, node_id: str, ttl: float) -> bool: ...
    @abstractmethod
    def complete_task(self, task_id: str, next_run: float): ...
    @abstractmethod
    def fail_task(self, task_id: str): ...


class InMemoryStore(SchedulerStore):
    """In-memory store for testing. Replace with Redis/PostgreSQL for production."""

    def __init__(self):
        self._lock = threading.Lock()
        self._leader: Optional[str] = None
        self._leader_until: float = 0
        self._tasks: dict[str, TaskRecord] = {}

    def acquire_leadership(self, node_id: str, ttl: float) -> bool:
        with self._lock:
            now = time.time()
            if self._leader is None or self._leader_until < now:
                self._leader = node_id
                self._leader_until = now + ttl
                return True
            return self._leader == node_id

    def renew_leadership(self, node_id: str, ttl: float) -> bool:
        with self._lock:
            if self._leader == node_id:
                self._leader_until = time.time() + ttl
                return True
            return False

    def get_leader(self) -> Optional[str]:
        with self._lock:
            if self._leader_until < time.time():
                self._leader = None
            return self._leader

    def save_task(self, task: TaskRecord):
        with self._lock:
            self._tasks[task.task_id] = task

    def get_due_tasks(self, now: float) -> list[TaskRecord]:
        with self._lock:
            return [
                t for t in self._tasks.values()
                if t.next_run is not None and t.next_run <= now and t.status != "running"
            ]

    def lock_task(self, task_id: str, node_id: str, ttl: float) -> bool:
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return False
            now = time.time()
            if task.locked_by and task.lock_until and task.lock_until > now:
                return False
            task.locked_by = node_id
            task.lock_until = now + ttl
            task.status = "running"
            return True

    def complete_task(self, task_id: str, next_run: float):
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.status = "idle"
                task.last_run = time.time()
                task.next_run = next_run
                task.locked_by = None
                task.lock_until = None
                task.retry_count = 0

    def fail_task(self, task_id: str):
        with self._lock:
            task = self._tasks.get(task_id)
            if task:
                task.retry_count += 1
                if task.retry_count >= task.max_retries:
                    task.status = "failed"
                else:
                    task.status = "idle"
                    task.next_run = time.time() + (2 ** task.retry_count)
                task.locked_by = None
                task.lock_until = None


class Scheduler:
    def __init__(self, node_id: str, store: SchedulerStore, heartbeat_interval: float = 5.0):
        self._node_id = node_id
        self._store = store
        self._heartbeat_interval = heartbeat_interval
        self._handlers: dict[str, Callable] = {}
        self._crons: dict[str, CronExpression] = {}
        self._running = False
        self._threads: list[threading.Thread] = []

    def register(self, task_id: str, cron_expr: str, handler: Callable, max_retries: int = 3):
        cron = CronExpression(cron_expr)
        self._handlers[task_id] = handler
        self._crons[task_id] = cron
        next_fire = cron.next_fire(datetime.now())
        self._store.save_task(TaskRecord(
            task_id=task_id,
            cron_expr=cron_expr,
            next_run=next_fire.timestamp(),
            max_retries=max_retries,
        ))

    def start(self):
        self._running = True
        t1 = threading.Thread(target=self._leader_loop, daemon=True)
        t2 = threading.Thread(target=self._schedule_loop, daemon=True)
        t1.start()
        t2.start()
        self._threads = [t1, t2]

    def stop(self):
        self._running = False
        for t in self._threads:
            t.join(timeout=5)

    def _leader_loop(self):
        while self._running:
            ttl = self._heartbeat_interval * 3
            if self._store.get_leader() == self._node_id:
                self._store.renew_leadership(self._node_id, ttl)
            else:
                self._store.acquire_leadership(self._node_id, ttl)
            time.sleep(self._heartbeat_interval)

    def _schedule_loop(self):
        while self._running:
            if self._store.get_leader() != self._node_id:
                time.sleep(1)
                continue

            now = time.time()
            due_tasks = self._store.get_due_tasks(now)
            for task in due_tasks:
                if task.task_id not in self._handlers:
                    continue
                if not self._store.lock_task(task.task_id, self._node_id, 300):
                    continue
                threading.Thread(
                    target=self._execute_task,
                    args=(task,),
                    daemon=True,
                ).start()

            time.sleep(1)

    def _execute_task(self, task: TaskRecord):
        handler = self._handlers.get(task.task_id)
        if not handler:
            return
        try:
            handler()
            cron = self._crons[task.task_id]
            next_fire = cron.next_fire(datetime.now())
            self._store.complete_task(task.task_id, next_fire.timestamp())
        except Exception as e:
            self._store.fail_task(task.task_id)


# --- Usage and tests ---

def test_scheduler():
    store = InMemoryStore()
    execution_log = []

    # Test cron parsing
    cron = CronExpression("*/5 * * * *")
    now = datetime(2025, 6, 15, 10, 3)
    assert cron.matches(datetime(2025, 6, 15, 10, 5))
    assert not cron.matches(datetime(2025, 6, 15, 10, 3))
    nxt = cron.next_fire(now)
    assert nxt.minute == 5

    # Test leader election
    assert store.acquire_leadership("node-1", ttl=2.0)
    assert store.get_leader() == "node-1"
    assert not store.acquire_leadership("node-2", ttl=2.0)  # node-1 holds

    # Test task registration and manual execution
    scheduler = Scheduler("node-1", store, heartbeat_interval=0.5)

    def my_job():
        execution_log.append(time.time())

    # Register with a cron that fires every minute
    scheduler.register("cleanup", "* * * * *", my_job)

    # Manually set next_run to now to trigger immediately
    task = store._tasks["cleanup"]
    task.next_run = time.time() - 1

    scheduler.start()
    time.sleep(2)
    scheduler.stop()

    assert len(execution_log) >= 1, "Task should have executed at least once"

    # Test retry on failure
    fail_count = {"n": 0}

    def failing_job():
        fail_count["n"] += 1
        raise RuntimeError("Intentional failure")

    store2 = InMemoryStore()
    store2.acquire_leadership("node-1", 10)
    sched2 = Scheduler("node-1", store2, heartbeat_interval=0.5)
    sched2.register("flaky", "* * * * *", failing_job, max_retries=3)
    store2._tasks["flaky"].next_run = time.time() - 1

    sched2.start()
    time.sleep(3)
    sched2.stop()

    assert fail_count["n"] >= 1

    print("All distributed scheduler tests passed.")


if __name__ == "__main__":
    test_scheduler()
```'''
    ),
    (
        "deep_reasoning/rule-engine-condition-trees",
        r'''Implement a rule engine in Python with condition trees (AND/OR/NOT), operator precedence, typed comparisons, and action execution when rules match.''',
        r'''<think>
A rule engine evaluates conditions against a fact set and executes actions when rules match.
The key design challenge is the condition tree — it needs to be composable, serializable,
and efficient to evaluate.

Design choices:
1. Conditions as a tree of nodes: LeafCondition (field op value), AND, OR, NOT combinators
2. Operator set: ==, !=, >, <, >=, <=, in, contains, matches (regex)
3. Type coercion: compare same types, raise on mismatch
4. Actions: callables executed with the matching context

Trade-off: I could use a DSL string parser or a builder API. A builder API is type-safe and
IDE-friendly. A DSL is more user-friendly for non-programmers. I'll do both — builder API
as the primary interface with an optional DSL parser.

Interface:
- Condition.field("age").gt(18) & Condition.field("country").eq("US")
- Rule(name, condition, priority, action)
- Engine.add_rule(rule)
- Engine.evaluate(facts) -> list[RuleResult]

Failure modes:
- Missing field in facts: should return False, not crash (configurable)
- Circular rules: not possible with tree structure (DAG)
- Conflicting rules: priority-based ordering, optional conflict resolution

Operator precedence: NOT > AND > OR. Python's __and__, __or__, __invert__ give us this
naturally with the builder pattern.
</think>

```python
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import Enum


class Operator(Enum):
    EQ = "=="
    NEQ = "!="
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="
    IN = "in"
    CONTAINS = "contains"
    MATCHES = "matches"
    EXISTS = "exists"


class Condition(ABC):
    @abstractmethod
    def evaluate(self, facts: dict) -> bool:
        pass

    def __and__(self, other: "Condition") -> "AndCondition":
        return AndCondition(self, other)

    def __or__(self, other: "Condition") -> "OrCondition":
        return OrCondition(self, other)

    def __invert__(self) -> "NotCondition":
        return NotCondition(self)

    @staticmethod
    def field(name: str) -> "FieldBuilder":
        return FieldBuilder(name)

    @abstractmethod
    def describe(self) -> str:
        pass


class LeafCondition(Condition):
    def __init__(self, field_name: str, operator: Operator, value: Any = None):
        self.field_name = field_name
        self.operator = operator
        self.value = value

    def evaluate(self, facts: dict) -> bool:
        if self.operator == Operator.EXISTS:
            return self.field_name in facts

        if self.field_name not in facts:
            return False

        fact_value = facts[self.field_name]
        op = self.operator

        try:
            if op == Operator.EQ:
                return fact_value == self.value
            elif op == Operator.NEQ:
                return fact_value != self.value
            elif op == Operator.GT:
                return fact_value > self.value
            elif op == Operator.LT:
                return fact_value < self.value
            elif op == Operator.GTE:
                return fact_value >= self.value
            elif op == Operator.LTE:
                return fact_value <= self.value
            elif op == Operator.IN:
                return fact_value in self.value
            elif op == Operator.CONTAINS:
                return self.value in fact_value
            elif op == Operator.MATCHES:
                return bool(re.search(self.value, str(fact_value)))
        except TypeError:
            return False

        return False

    def describe(self) -> str:
        return f"{self.field_name} {self.operator.value} {self.value!r}"


class AndCondition(Condition):
    def __init__(self, *children: Condition):
        self.children = list(children)

    def evaluate(self, facts: dict) -> bool:
        return all(c.evaluate(facts) for c in self.children)

    def describe(self) -> str:
        parts = [c.describe() for c in self.children]
        return "(" + " AND ".join(parts) + ")"


class OrCondition(Condition):
    def __init__(self, *children: Condition):
        self.children = list(children)

    def evaluate(self, facts: dict) -> bool:
        return any(c.evaluate(facts) for c in self.children)

    def describe(self) -> str:
        parts = [c.describe() for c in self.children]
        return "(" + " OR ".join(parts) + ")"


class NotCondition(Condition):
    def __init__(self, child: Condition):
        self.child = child

    def evaluate(self, facts: dict) -> bool:
        return not self.child.evaluate(facts)

    def describe(self) -> str:
        return f"NOT ({self.child.describe()})"


class FieldBuilder:
    """Fluent builder for leaf conditions."""

    def __init__(self, field_name: str):
        self._field = field_name

    def eq(self, value: Any) -> LeafCondition:
        return LeafCondition(self._field, Operator.EQ, value)

    def neq(self, value: Any) -> LeafCondition:
        return LeafCondition(self._field, Operator.NEQ, value)

    def gt(self, value: Any) -> LeafCondition:
        return LeafCondition(self._field, Operator.GT, value)

    def lt(self, value: Any) -> LeafCondition:
        return LeafCondition(self._field, Operator.LT, value)

    def gte(self, value: Any) -> LeafCondition:
        return LeafCondition(self._field, Operator.GTE, value)

    def lte(self, value: Any) -> LeafCondition:
        return LeafCondition(self._field, Operator.LTE, value)

    def is_in(self, values: list) -> LeafCondition:
        return LeafCondition(self._field, Operator.IN, values)

    def contains(self, value: Any) -> LeafCondition:
        return LeafCondition(self._field, Operator.CONTAINS, value)

    def matches(self, pattern: str) -> LeafCondition:
        return LeafCondition(self._field, Operator.MATCHES, pattern)

    def exists(self) -> LeafCondition:
        return LeafCondition(self._field, Operator.EXISTS)


@dataclass
class RuleResult:
    rule_name: str
    matched: bool
    action_result: Any = None
    error: Optional[str] = None


@dataclass
class Rule:
    name: str
    condition: Condition
    action: Callable[[dict], Any]
    priority: int = 0  # higher = runs first
    stop_on_match: bool = False  # if True, skip lower-priority rules


class RuleEngine:
    def __init__(self, strict: bool = False):
        self._rules: list[Rule] = []
        self._strict = strict

    def add_rule(self, rule: Rule):
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def evaluate(self, facts: dict) -> list[RuleResult]:
        results = []
        for rule in self._rules:
            matched = rule.condition.evaluate(facts)
            result = RuleResult(rule_name=rule.name, matched=matched)

            if matched:
                try:
                    result.action_result = rule.action(facts)
                except Exception as e:
                    result.error = str(e)

                results.append(result)
                if rule.stop_on_match:
                    break
            elif self._strict:
                results.append(result)

        return results

    def explain(self, facts: dict) -> str:
        """Show which rules match and why."""
        lines = []
        for rule in self._rules:
            matched = rule.condition.evaluate(facts)
            status = "MATCH" if matched else "SKIP"
            lines.append(f"[{status}] {rule.name} (priority={rule.priority})")
            lines.append(f"  Condition: {rule.condition.describe()}")
        return "\n".join(lines)


# --- Usage and tests ---

def test_rule_engine():
    engine = RuleEngine()
    actions_log = []

    # Rule 1: Premium discount for high-value loyal customers
    premium_condition = (
        Condition.field("total_purchases").gt(1000) &
        Condition.field("loyalty_years").gte(2) &
        Condition.field("country").is_in(["US", "CA", "UK"])
    )
    engine.add_rule(Rule(
        name="premium_discount",
        condition=premium_condition,
        action=lambda facts: actions_log.append(("discount", 0.2, facts["customer_id"])),
        priority=10,
    ))

    # Rule 2: New customer welcome offer
    new_customer_condition = (
        Condition.field("loyalty_years").lt(1) &
        ~Condition.field("welcome_sent").exists()
    )
    engine.add_rule(Rule(
        name="welcome_offer",
        condition=new_customer_condition,
        action=lambda facts: actions_log.append(("welcome", facts["customer_id"])),
        priority=5,
    ))

    # Rule 3: Fraud detection — suspicious patterns
    fraud_condition = (
        Condition.field("transaction_amount").gt(5000) &
        Condition.field("country").neq("US") &
        Condition.field("email").matches(r".*@tempmail\.")
    )
    engine.add_rule(Rule(
        name="fraud_alert",
        condition=fraud_condition,
        action=lambda facts: actions_log.append(("flag_fraud", facts["customer_id"])),
        priority=100,  # highest priority
        stop_on_match=True,
    ))

    # Test premium customer
    results = engine.evaluate({
        "customer_id": "C001",
        "total_purchases": 1500,
        "loyalty_years": 3,
        "country": "US",
    })
    assert any(r.rule_name == "premium_discount" and r.matched for r in results)
    assert ("discount", 0.2, "C001") in actions_log

    # Test new customer
    actions_log.clear()
    results = engine.evaluate({
        "customer_id": "C002",
        "loyalty_years": 0,
        "total_purchases": 0,
        "country": "US",
    })
    assert any(r.rule_name == "welcome_offer" and r.matched for r in results)

    # Test fraud — should stop on match
    actions_log.clear()
    results = engine.evaluate({
        "customer_id": "C003",
        "transaction_amount": 9999,
        "country": "RU",
        "email": "sketchy@tempmail.com",
        "total_purchases": 2000,
        "loyalty_years": 5,
    })
    assert len(results) == 1  # stopped after fraud rule
    assert results[0].rule_name == "fraud_alert"

    # Test missing field handling
    results = engine.evaluate({"customer_id": "C004"})  # minimal facts
    matched = [r for r in results if r.matched]
    assert len(matched) == 0  # nothing should match with missing fields

    # Test NOT condition
    cond = ~Condition.field("banned").eq(True)
    assert cond.evaluate({"banned": False})
    assert cond.evaluate({})  # missing field -> eq returns False -> NOT False = True
    assert not cond.evaluate({"banned": True})

    # Test explain
    explanation = engine.explain({"customer_id": "C001", "total_purchases": 500,
                                   "loyalty_years": 1, "country": "US"})
    assert "SKIP" in explanation  # shouldn't match premium

    print("All rule engine tests passed.")


if __name__ == "__main__":
    test_rule_engine()
```'''
    ),
    (
        "deep_reasoning/api-gateway-rate-limit-cache",
        r'''Build an API gateway in Python with rate limiting (token bucket), JWT authentication, request routing to backend services, and response caching with TTL.''',
        r'''<think>
An API gateway sits in front of multiple services, handling cross-cutting concerns. The key
components are:

1. Rate limiting — token bucket is smoother than fixed window. Each client gets a bucket
   that refills at a steady rate, allowing bursts up to bucket capacity.
2. Authentication — JWT validation. Must be fast (no DB lookup per request ideally).
3. Routing — map incoming paths to backend services via prefix matching.
4. Response caching — cache GET responses by (path, query) with TTL. Must handle cache
   invalidation on non-GET methods.

Trade-off: rate limiting per-IP vs per-API-key. Per-API-key is more accurate for
authenticated APIs. I'll support both, defaulting to API key when authenticated.

Interface:
- Gateway(routes, rate_limit_config, jwt_secret)
- gateway.handle_request(request) -> response
- Middleware pipeline: auth -> rate_limit -> cache_check -> route -> cache_store

Failure modes:
- Backend service is down: return 502 with a meaningful error
- JWT expired: return 401 before rate limiting (don't count expired requests)
- Cache stampede: when a popular cached item expires, many requests hit the backend.
  I'll use a lock-per-key approach to let only one request through.

The gateway won't be a real HTTP server — it processes Request/Response objects. This makes
it testable without network dependencies and pluggable into any framework.
</think>

```python
import time
import threading
import hashlib
import json
import hmac
import base64
from dataclasses import dataclass, field
from typing import Any, Optional, Callable
from enum import Enum


# --- JWT (minimal implementation for demo) ---

class JWTError(Exception):
    pass


def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * padding)


def jwt_encode(payload: dict, secret: str) -> str:
    header = _b64encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64encode(json.dumps(payload).encode())
    signature = hmac.new(secret.encode(), f"{header}.{body}".encode(), "sha256").digest()
    return f"{header}.{body}.{_b64encode(signature)}"


def jwt_decode(token: str, secret: str) -> dict:
    try:
        header_b64, body_b64, sig_b64 = token.split(".")
    except ValueError:
        raise JWTError("Invalid token format")

    expected_sig = hmac.new(secret.encode(), f"{header_b64}.{body_b64}".encode(), "sha256").digest()
    actual_sig = _b64decode(sig_b64)

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise JWTError("Invalid signature")

    payload = json.loads(_b64decode(body_b64))
    if "exp" in payload and payload["exp"] < time.time():
        raise JWTError("Token expired")

    return payload


# --- Token Bucket Rate Limiter ---

class TokenBucket:
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.refill_rate = refill_rate  # tokens per second
        self._tokens = float(capacity)
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, tokens: int = 1) -> bool:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self.capacity, self._tokens + elapsed * self.refill_rate)
            self._last_refill = now

            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    @property
    def available(self) -> float:
        return self._tokens


class RateLimiter:
    def __init__(self, capacity: int = 100, refill_rate: float = 10.0):
        self._capacity = capacity
        self._refill_rate = refill_rate
        self._buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def allow(self, client_id: str) -> bool:
        with self._lock:
            if client_id not in self._buckets:
                self._buckets[client_id] = TokenBucket(self._capacity, self._refill_rate)
        return self._buckets[client_id].consume()

    def get_remaining(self, client_id: str) -> float:
        bucket = self._buckets.get(client_id)
        return bucket.available if bucket else self._capacity


# --- Response Cache ---

@dataclass
class CacheEntry:
    response: "Response"
    expires_at: float
    lock: threading.Lock = field(default_factory=threading.Lock)


class ResponseCache:
    def __init__(self, default_ttl: float = 60.0):
        self._store: dict[str, CacheEntry] = {}
        self._default_ttl = default_ttl
        self._lock = threading.Lock()

    def _key(self, method: str, path: str, query: str) -> str:
        raw = f"{method}:{path}:{query}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, method: str, path: str, query: str = "") -> Optional["Response"]:
        key = self._key(method, path, query)
        with self._lock:
            entry = self._store.get(key)
        if entry and time.time() < entry.expires_at:
            return entry.response
        return None

    def put(self, method: str, path: str, response: "Response",
            query: str = "", ttl: Optional[float] = None):
        key = self._key(method, path, query)
        entry = CacheEntry(
            response=response,
            expires_at=time.time() + (ttl or self._default_ttl),
        )
        with self._lock:
            self._store[key] = entry

    def invalidate(self, path_prefix: str):
        with self._lock:
            # Can't reverse the hash, so we clear everything with matching prefix
            # In production, maintain a prefix -> keys index
            self._store.clear()


# --- Request / Response ---

@dataclass
class Request:
    method: str
    path: str
    query: str = ""
    headers: dict = field(default_factory=dict)
    body: Any = None

    @property
    def auth_token(self) -> Optional[str]:
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            return auth[7:]
        return None


@dataclass
class Response:
    status: int
    body: Any
    headers: dict = field(default_factory=dict)


# --- Backend Route ---

@dataclass
class Route:
    prefix: str
    handler: Callable[[Request], Response]
    require_auth: bool = True
    cacheable: bool = False
    cache_ttl: float = 60.0


class Gateway:
    def __init__(self, jwt_secret: str, rate_capacity: int = 100, rate_refill: float = 10.0):
        self._jwt_secret = jwt_secret
        self._rate_limiter = RateLimiter(rate_capacity, rate_refill)
        self._cache = ResponseCache()
        self._routes: list[Route] = []

    def add_route(self, route: Route):
        self._routes.append(route)
        self._routes.sort(key=lambda r: len(r.prefix), reverse=True)  # longest prefix first

    def handle_request(self, request: Request) -> Response:
        # 1. Find matching route
        route = self._match_route(request.path)
        if not route:
            return Response(404, {"error": "Not found"})

        # 2. Authentication
        user_claims = None
        if route.require_auth:
            token = request.auth_token
            if not token:
                return Response(401, {"error": "Missing authentication"})
            try:
                user_claims = jwt_decode(token, self._jwt_secret)
            except JWTError as e:
                return Response(401, {"error": str(e)})

        # 3. Rate limiting (by user ID if authenticated, else by IP-like header)
        client_id = (user_claims or {}).get("sub", request.headers.get("X-Client-IP", "anonymous"))
        if not self._rate_limiter.allow(client_id):
            remaining = self._rate_limiter.get_remaining(client_id)
            return Response(429, {"error": "Rate limit exceeded"}, {
                "X-RateLimit-Remaining": str(int(remaining)),
                "Retry-After": "1",
            })

        # 4. Cache check (GET only)
        if request.method == "GET" and route.cacheable:
            cached = self._cache.get(request.method, request.path, request.query)
            if cached:
                cached.headers["X-Cache"] = "HIT"
                return cached

        # 5. Forward to backend
        try:
            # Inject user claims into request for downstream
            if user_claims:
                request.headers["X-User-ID"] = user_claims.get("sub", "")
                request.headers["X-User-Roles"] = ",".join(user_claims.get("roles", []))

            response = route.handler(request)
        except Exception as e:
            return Response(502, {"error": f"Backend error: {e}"})

        # 6. Cache store
        if request.method == "GET" and route.cacheable and 200 <= response.status < 300:
            self._cache.put(request.method, request.path, response,
                          request.query, route.cache_ttl)
            response.headers["X-Cache"] = "MISS"
        elif request.method in ("POST", "PUT", "DELETE"):
            self._cache.invalidate(route.prefix)

        return response

    def _match_route(self, path: str) -> Optional[Route]:
        for route in self._routes:
            if path.startswith(route.prefix):
                return route
        return None


# --- Usage and tests ---

def test_gateway():
    secret = "test-secret-key"

    # Backend handlers
    def users_handler(req: Request) -> Response:
        return Response(200, {"users": [{"id": 1, "name": "Alice"}]})

    def orders_handler(req: Request) -> Response:
        if req.method == "POST":
            return Response(201, {"order_id": 42})
        return Response(200, {"orders": []})

    def public_handler(req: Request) -> Response:
        return Response(200, {"status": "healthy"})

    def failing_handler(req: Request) -> Response:
        raise ConnectionError("Service unavailable")

    # Setup gateway
    gw = Gateway(jwt_secret=secret, rate_capacity=5, rate_refill=2.0)
    gw.add_route(Route("/api/users", users_handler, require_auth=True, cacheable=True, cache_ttl=30))
    gw.add_route(Route("/api/orders", orders_handler, require_auth=True))
    gw.add_route(Route("/health", public_handler, require_auth=False))
    gw.add_route(Route("/api/broken", failing_handler, require_auth=True))

    # Create valid JWT
    token = jwt_encode({"sub": "user-1", "roles": ["admin"], "exp": time.time() + 3600}, secret)

    # Test: unauthenticated request to protected route
    resp = gw.handle_request(Request("GET", "/api/users"))
    assert resp.status == 401

    # Test: valid authentication
    resp = gw.handle_request(Request("GET", "/api/users", headers={"Authorization": f"Bearer {token}"}))
    assert resp.status == 200
    assert resp.headers.get("X-Cache") == "MISS"

    # Test: cache hit
    resp = gw.handle_request(Request("GET", "/api/users", headers={"Authorization": f"Bearer {token}"}))
    assert resp.status == 200
    assert resp.headers.get("X-Cache") == "HIT"

    # Test: public endpoint (no auth required)
    resp = gw.handle_request(Request("GET", "/health"))
    assert resp.status == 200

    # Test: expired JWT
    expired_token = jwt_encode({"sub": "user-2", "exp": time.time() - 100}, secret)
    resp = gw.handle_request(Request("GET", "/api/users", headers={"Authorization": f"Bearer {expired_token}"}))
    assert resp.status == 401

    # Test: rate limiting
    for _ in range(10):
        resp = gw.handle_request(Request("GET", "/health"))
    # After 5 requests with capacity=5, should get rate limited
    # (some may have been refilled, but eventually hits limit)
    rate_limited = False
    for _ in range(20):
        resp = gw.handle_request(Request("GET", "/health"))
        if resp.status == 429:
            rate_limited = True
            break
    assert rate_limited, "Should have been rate limited"

    # Test: backend failure returns 502
    resp = gw.handle_request(Request("GET", "/api/broken", headers={"Authorization": f"Bearer {token}"}))
    assert resp.status == 502

    # Test: 404 for unknown route
    resp = gw.handle_request(Request("GET", "/unknown"))
    assert resp.status == 404

    print("All API gateway tests passed.")


if __name__ == "__main__":
    test_gateway()
```'''
    ),
    (
        "deep_reasoning/service-mesh-sidecar-proxy",
        r'''Implement a service mesh sidecar proxy in Python with load balancing (round-robin + least-connections), retry with exponential backoff, and circuit breaking per upstream.''',
        r'''<think>
A sidecar proxy intercepts all traffic for a service, adding load balancing, retries, and
circuit breaking transparently. The service itself just talks to localhost; the sidecar
handles routing to upstream instances.

Key design decisions:
1. Load balancing — round-robin for stateless calls, least-connections when backend
   processing time varies significantly. I'll make the strategy pluggable.
2. Retry — exponential backoff with jitter. Must be idempotent-aware: only retry GET/PUT,
   not POST by default (configurable).
3. Circuit breaking — per-upstream-instance, not per-service. One bad instance shouldn't
   block traffic to healthy ones.

Trade-off: the sidecar could buffer requests during retries (adding latency but improving
success rate) or fail fast (lower latency but more errors). I'll use a retry budget —
limit total retries to a percentage of traffic to prevent retry storms.

Interface:
- SidecarProxy(upstreams, lb_strategy, retry_policy, circuit_config)
- proxy.forward(request) -> response
- Health check endpoint for the sidecar itself

Failure modes:
- All upstreams are circuit-broken: return 503 immediately
- Retry budget exhausted: fail without retry even if retries remain
- Upstream returns 5xx: retry. 4xx: don't retry (client error).
- Connection timeout: count as failure for circuit breaker

I won't use real sockets. The proxy works with abstract Request/Response and callable
backends, making it testable and framework-agnostic.
</think>

```python
import time
import random
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional, Any
from enum import Enum


@dataclass
class ProxyRequest:
    method: str
    path: str
    headers: dict = field(default_factory=dict)
    body: Any = None


@dataclass
class ProxyResponse:
    status: int
    body: Any = None
    headers: dict = field(default_factory=dict)
    upstream: str = ""
    latency_ms: float = 0


class UpstreamError(Exception):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(message)


# --- Load Balancing Strategies ---

class LoadBalancer(ABC):
    @abstractmethod
    def pick(self, healthy: list[str]) -> Optional[str]:
        pass

    @abstractmethod
    def on_request_start(self, upstream: str):
        pass

    @abstractmethod
    def on_request_end(self, upstream: str):
        pass


class RoundRobinLB(LoadBalancer):
    def __init__(self):
        self._index = 0

    def pick(self, healthy: list[str]) -> Optional[str]:
        if not healthy:
            return None
        chosen = healthy[self._index % len(healthy)]
        self._index += 1
        return chosen

    def on_request_start(self, upstream: str):
        pass

    def on_request_end(self, upstream: str):
        pass


class LeastConnectionsLB(LoadBalancer):
    def __init__(self):
        self._active: dict[str, int] = {}
        self._lock = threading.Lock()

    def pick(self, healthy: list[str]) -> Optional[str]:
        if not healthy:
            return None
        with self._lock:
            for h in healthy:
                if h not in self._active:
                    self._active[h] = 0
            return min(healthy, key=lambda h: self._active.get(h, 0))

    def on_request_start(self, upstream: str):
        with self._lock:
            self._active[upstream] = self._active.get(upstream, 0) + 1

    def on_request_end(self, upstream: str):
        with self._lock:
            self._active[upstream] = max(0, self._active.get(upstream, 0) - 1)


# --- Per-Upstream Circuit Breaker ---

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class UpstreamCircuit:
    def __init__(self, failure_threshold: int = 3, reset_timeout: float = 10.0,
                 half_open_max: int = 1):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.reset_timeout = reset_timeout
        self.opened_at = 0.0
        self.half_open_active = 0
        self.half_open_max = half_open_max
        self.lock = threading.Lock()

    def allow_request(self) -> bool:
        with self.lock:
            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if time.monotonic() - self.opened_at >= self.reset_timeout:
                    self.state = CircuitState.HALF_OPEN
                    self.half_open_active = 0
                    return True
                return False
            # HALF_OPEN
            if self.half_open_active < self.half_open_max:
                self.half_open_active += 1
                return True
            return False

    def record_success(self):
        with self.lock:
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
            self.failure_count = 0

    def record_failure(self):
        with self.lock:
            self.failure_count += 1
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                self.opened_at = time.monotonic()
            elif self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                self.opened_at = time.monotonic()


# --- Retry Policy ---

@dataclass
class RetryPolicy:
    max_retries: int = 3
    base_delay: float = 0.1
    max_delay: float = 5.0
    jitter: float = 0.1
    retryable_methods: set = field(default_factory=lambda: {"GET", "PUT", "DELETE", "HEAD"})
    retryable_statuses: set = field(default_factory=lambda: {500, 502, 503, 504})
    retry_budget_pct: float = 0.2  # max 20% of recent traffic can be retries

    def delay(self, attempt: int) -> float:
        delay = min(self.base_delay * (2 ** attempt), self.max_delay)
        jitter = random.uniform(-self.jitter, self.jitter) * delay
        return max(0, delay + jitter)


# --- Sidecar Proxy ---

class SidecarProxy:
    def __init__(
        self,
        upstreams: dict[str, Callable[[ProxyRequest], ProxyResponse]],
        lb_strategy: Optional[LoadBalancer] = None,
        retry_policy: Optional[RetryPolicy] = None,
        circuit_config: Optional[dict] = None,
    ):
        self._upstreams = upstreams  # name -> handler
        self._lb = lb_strategy or RoundRobinLB()
        self._retry_policy = retry_policy or RetryPolicy()
        self._circuits: dict[str, UpstreamCircuit] = {}
        circuit_config = circuit_config or {}

        for name in upstreams:
            self._circuits[name] = UpstreamCircuit(
                failure_threshold=circuit_config.get("failure_threshold", 3),
                reset_timeout=circuit_config.get("reset_timeout", 10.0),
            )

        self._request_count = 0
        self._retry_count = 0
        self._lock = threading.Lock()

    def _get_healthy_upstreams(self) -> list[str]:
        return [name for name, circuit in self._circuits.items() if circuit.allow_request()]

    def _retry_budget_ok(self) -> bool:
        with self._lock:
            if self._request_count == 0:
                return True
            return (self._retry_count / max(self._request_count, 1)) < self._retry_policy.retry_budget_pct

    def forward(self, request: ProxyRequest) -> ProxyResponse:
        with self._lock:
            self._request_count += 1

        retryable = request.method in self._retry_policy.retryable_methods
        last_error = None
        attempts = 0
        max_attempts = self._retry_policy.max_retries + 1 if retryable else 1

        while attempts < max_attempts:
            healthy = self._get_healthy_upstreams()
            if not healthy:
                return ProxyResponse(503, {"error": "All upstreams unavailable"})

            upstream_name = self._lb.pick(healthy)
            if not upstream_name:
                return ProxyResponse(503, {"error": "No upstream selected"})

            self._lb.on_request_start(upstream_name)
            start = time.monotonic()

            try:
                handler = self._upstreams[upstream_name]
                response = handler(request)
                elapsed = (time.monotonic() - start) * 1000
                response.upstream = upstream_name
                response.latency_ms = elapsed
                self._lb.on_request_end(upstream_name)

                if response.status in self._retry_policy.retryable_statuses:
                    self._circuits[upstream_name].record_failure()
                    last_error = response
                    attempts += 1
                    if attempts < max_attempts and retryable and self._retry_budget_ok():
                        with self._lock:
                            self._retry_count += 1
                        delay = self._retry_policy.delay(attempts - 1)
                        time.sleep(delay)
                        continue
                    return response

                self._circuits[upstream_name].record_success()
                return response

            except Exception as e:
                self._lb.on_request_end(upstream_name)
                self._circuits[upstream_name].record_failure()
                last_error = ProxyResponse(502, {"error": str(e)}, upstream=upstream_name)
                attempts += 1
                if attempts < max_attempts and retryable and self._retry_budget_ok():
                    with self._lock:
                        self._retry_count += 1
                    delay = self._retry_policy.delay(attempts - 1)
                    time.sleep(delay)
                    continue

        return last_error or ProxyResponse(503, {"error": "All attempts failed"})

    def get_circuit_states(self) -> dict[str, str]:
        return {name: circuit.state.value for name, circuit in self._circuits.items()}


# --- Usage and tests ---

def test_sidecar():
    call_log = []

    def make_handler(name: str, fail_count: int = 0):
        state = {"fails": 0}
        def handler(req: ProxyRequest) -> ProxyResponse:
            call_log.append(name)
            if state["fails"] < fail_count:
                state["fails"] += 1
                return ProxyResponse(500, {"error": "Internal error"})
            return ProxyResponse(200, {"from": name, "path": req.path})
        return handler

    # 3 upstreams: svc-1 always works, svc-2 fails first 2 times, svc-3 always fails
    upstreams = {
        "svc-1": make_handler("svc-1"),
        "svc-2": make_handler("svc-2", fail_count=2),
        "svc-3": make_handler("svc-3", fail_count=999),
    }

    proxy = SidecarProxy(
        upstreams=upstreams,
        lb_strategy=RoundRobinLB(),
        retry_policy=RetryPolicy(max_retries=2, base_delay=0.01, retry_budget_pct=0.5),
        circuit_config={"failure_threshold": 3, "reset_timeout": 0.5},
    )

    # Basic forwarding
    resp = proxy.forward(ProxyRequest("GET", "/api/data"))
    assert resp.status == 200

    # Test retry on failure — should eventually get a healthy upstream
    call_log.clear()
    for _ in range(10):
        resp = proxy.forward(ProxyRequest("GET", "/api/data"))
    # Most should succeed (svc-1 always works, svc-2 works after initial failures)
    successes = sum(1 for _ in range(5) if proxy.forward(ProxyRequest("GET", "/test")).status == 200)
    assert successes > 0

    # Test circuit breaking — svc-3 should get circuit-broken
    for _ in range(20):
        proxy.forward(ProxyRequest("GET", "/api/data"))

    states = proxy.get_circuit_states()
    assert states["svc-3"] == "open", f"svc-3 should be open, got {states['svc-3']}"

    # Test non-retryable method (POST)
    call_log.clear()
    failing_proxy = SidecarProxy(
        upstreams={"fail-svc": make_handler("fail-svc", fail_count=999)},
        retry_policy=RetryPolicy(max_retries=3, base_delay=0.01),
    )
    resp = failing_proxy.forward(ProxyRequest("POST", "/api/create"))
    assert resp.status == 500
    assert len(call_log) == 1  # POST should not retry

    # Test least-connections LB
    lc_proxy = SidecarProxy(
        upstreams={
            "fast": make_handler("fast"),
            "slow": make_handler("slow"),
        },
        lb_strategy=LeastConnectionsLB(),
        retry_policy=RetryPolicy(max_retries=0),
    )
    for _ in range(6):
        lc_proxy.forward(ProxyRequest("GET", "/test"))

    print("All sidecar proxy tests passed.")


if __name__ == "__main__":
    test_sidecar()
```'''
    ),
    (
        "deep_reasoning/saga-distributed-transactions",
        r'''Implement the Saga pattern for distributed transactions in Python with compensation (rollback) actions, both orchestration and choreography modes, and timeout handling.''',
        r'''<think>
The Saga pattern manages distributed transactions without 2PC (two-phase commit). Instead of
a single atomic transaction, it's a sequence of local transactions with compensating actions
for rollback.

Two approaches:
1. Orchestrator — a central coordinator drives the saga step by step
2. Choreography — each service publishes events, and the next service reacts

Trade-off: Orchestrator is easier to understand and debug (centralized logic), but creates
a single point of coordination. Choreography is more decoupled but harder to trace and
reason about. I'll implement the orchestrator pattern as primary, with a choreography
event bus as secondary.

Interface:
- SagaStep(name, action, compensation)
- Saga(steps) — defines the sequence
- SagaOrchestrator.execute(saga, context) -> SagaResult
- Each step's action/compensation takes a context dict and returns updated context

Failure modes:
- Step 3 fails: compensate steps 2, 1 in reverse order
- Compensation itself fails: log it, retry, eventually dead-letter
- Step times out: treat as failure, compensate
- Concurrent sagas: each gets its own context, no shared state
- Partial compensation failure: record which compensations succeeded for manual recovery

I'll track the full execution history so we can diagnose issues.
</think>

```python
import time
import threading
import uuid
import traceback
from dataclasses import dataclass, field
from typing import Callable, Optional, Any
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout


class SagaStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPENSATING = "compensating"
    COMPENSATED = "compensated"
    FAILED = "failed"  # compensation also failed


class StepStatus(Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    COMPENSATED = "compensated"
    COMPENSATION_FAILED = "compensation_failed"
    TIMED_OUT = "timed_out"


@dataclass
class StepResult:
    step_name: str
    status: StepStatus
    duration_ms: float = 0
    error: Optional[str] = None
    compensation_error: Optional[str] = None


@dataclass
class SagaResult:
    saga_id: str
    status: SagaStatus
    steps: list[StepResult] = field(default_factory=list)
    context: dict = field(default_factory=dict)
    total_duration_ms: float = 0


@dataclass
class SagaStep:
    name: str
    action: Callable[[dict], dict]       # takes context, returns updated context
    compensation: Callable[[dict], None]  # takes context, rolls back
    timeout: float = 30.0                 # seconds


class SagaOrchestrator:
    def __init__(self, max_compensation_retries: int = 3):
        self._max_comp_retries = max_compensation_retries
        self._executor = ThreadPoolExecutor(max_workers=4)

    def execute(self, steps: list[SagaStep], initial_context: Optional[dict] = None) -> SagaResult:
        saga_id = str(uuid.uuid4())[:8]
        context = dict(initial_context or {})
        context["_saga_id"] = saga_id
        result = SagaResult(saga_id=saga_id, status=SagaStatus.RUNNING, context=context)
        completed_steps: list[tuple[SagaStep, StepResult]] = []

        start = time.monotonic()

        for step in steps:
            step_result = self._execute_step(step, context)
            result.steps.append(step_result)

            if step_result.status == StepStatus.SUCCEEDED:
                completed_steps.append((step, step_result))
            else:
                # Step failed — compensate in reverse
                result.status = SagaStatus.COMPENSATING
                self._compensate(completed_steps, context, result)
                break
        else:
            result.status = SagaStatus.COMPLETED

        result.total_duration_ms = (time.monotonic() - start) * 1000
        result.context = context
        return result

    def _execute_step(self, step: SagaStep, context: dict) -> StepResult:
        start = time.monotonic()
        try:
            future = self._executor.submit(step.action, context)
            updated = future.result(timeout=step.timeout)
            if isinstance(updated, dict):
                context.update(updated)
            elapsed = (time.monotonic() - start) * 1000
            return StepResult(step.name, StepStatus.SUCCEEDED, duration_ms=elapsed)
        except FuturesTimeout:
            elapsed = (time.monotonic() - start) * 1000
            return StepResult(step.name, StepStatus.TIMED_OUT, duration_ms=elapsed,
                            error=f"Timed out after {step.timeout}s")
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return StepResult(step.name, StepStatus.FAILED, duration_ms=elapsed,
                            error=str(e))

    def _compensate(self, completed: list[tuple[SagaStep, StepResult]],
                    context: dict, result: SagaResult):
        all_compensated = True
        for step, step_result in reversed(completed):
            comp_error = None
            for attempt in range(self._max_comp_retries):
                try:
                    step.compensation(context)
                    step_result.status = StepStatus.COMPENSATED
                    comp_error = None
                    break
                except Exception as e:
                    comp_error = str(e)
                    time.sleep(0.1 * (2 ** attempt))  # backoff

            if comp_error:
                step_result.status = StepStatus.COMPENSATION_FAILED
                step_result.compensation_error = comp_error
                all_compensated = False

        result.status = SagaStatus.COMPENSATED if all_compensated else SagaStatus.FAILED


# --- Choreography Mode (Event-Driven) ---

class SagaEventBus:
    """Simple event bus for choreography-style sagas."""

    def __init__(self):
        self._handlers: dict[str, list[Callable]] = {}
        self._saga_states: dict[str, dict] = {}
        self._lock = threading.Lock()

    def on(self, event_type: str, handler: Callable[[str, dict], None]):
        self._handlers.setdefault(event_type, []).append(handler)

    def emit(self, saga_id: str, event_type: str, data: dict):
        with self._lock:
            state = self._saga_states.setdefault(saga_id, {"events": []})
            state["events"].append({"type": event_type, "data": data, "time": time.time()})

        for handler in self._handlers.get(event_type, []):
            try:
                handler(saga_id, data)
            except Exception as e:
                self.emit(saga_id, f"{event_type}_failed",
                         {"error": str(e), "original": data})

    def get_saga_history(self, saga_id: str) -> list[dict]:
        with self._lock:
            return self._saga_states.get(saga_id, {}).get("events", [])


# --- Usage and tests ---

def test_saga():
    log = []

    # Simulate: Order Saga — reserve inventory, charge payment, ship order
    def reserve_inventory(ctx):
        log.append("reserve_inventory")
        ctx["inventory_reserved"] = True
        return ctx

    def unreserve_inventory(ctx):
        log.append("compensate_inventory")
        ctx["inventory_reserved"] = False

    def charge_payment(ctx):
        log.append("charge_payment")
        if ctx.get("force_payment_fail"):
            raise ValueError("Payment declined")
        ctx["payment_charged"] = True
        return ctx

    def refund_payment(ctx):
        log.append("compensate_payment")
        ctx["payment_charged"] = False

    def ship_order(ctx):
        log.append("ship_order")
        ctx["shipped"] = True
        return ctx

    def cancel_shipment(ctx):
        log.append("compensate_shipment")
        ctx["shipped"] = False

    steps = [
        SagaStep("reserve_inventory", reserve_inventory, unreserve_inventory),
        SagaStep("charge_payment", charge_payment, refund_payment),
        SagaStep("ship_order", ship_order, cancel_shipment),
    ]

    orchestrator = SagaOrchestrator()

    # Happy path
    result = orchestrator.execute(steps, {"order_id": "ORD-001"})
    assert result.status == SagaStatus.COMPLETED
    assert all(s.status == StepStatus.SUCCEEDED for s in result.steps)
    assert log == ["reserve_inventory", "charge_payment", "ship_order"]

    # Failure path — payment fails, should compensate inventory
    log.clear()
    result = orchestrator.execute(steps, {"order_id": "ORD-002", "force_payment_fail": True})
    assert result.status == SagaStatus.COMPENSATED
    assert result.steps[0].status == StepStatus.COMPENSATED
    assert result.steps[1].status == StepStatus.FAILED
    assert "reserve_inventory" in log
    assert "compensate_inventory" in log

    # Timeout test
    log.clear()
    def slow_step(ctx):
        time.sleep(5)
        return ctx

    timeout_steps = [
        SagaStep("slow", slow_step, lambda ctx: None, timeout=0.1),
    ]
    result = orchestrator.execute(timeout_steps)
    assert result.steps[0].status == StepStatus.TIMED_OUT

    # Choreography test
    bus = SagaEventBus()
    choreo_log = []

    bus.on("order_created", lambda sid, data: (
        choreo_log.append("inventory_reserved"),
        bus.emit(sid, "inventory_reserved", data),
    ))
    bus.on("inventory_reserved", lambda sid, data: (
        choreo_log.append("payment_charged"),
        bus.emit(sid, "payment_charged", data),
    ))
    bus.on("payment_charged", lambda sid, data: (
        choreo_log.append("order_completed"),
        bus.emit(sid, "order_completed", data),
    ))

    bus.emit("saga-1", "order_created", {"order_id": "ORD-003"})
    assert "inventory_reserved" in choreo_log
    assert "payment_charged" in choreo_log
    assert "order_completed" in choreo_log

    history = bus.get_saga_history("saga-1")
    assert len(history) == 4  # created, reserved, charged, completed

    print("All saga tests passed.")


if __name__ == "__main__":
    test_saga()
```'''
    ),
    (
        "deep_reasoning/actor-model-message-passing",
        r'''Implement the Actor model in Python with typed message passing, a supervision hierarchy (restart/stop strategies), and a mailbox with backpressure.''',
        r'''<think>
The Actor model: each actor is an isolated unit with its own state, processing messages
sequentially from a mailbox. No shared memory — all communication through messages.

Key constraints:
1. Actors must process messages one at a time (no concurrent access to state)
2. Supervision — when an actor crashes, its parent decides: restart, stop, or escalate
3. Mailbox — bounded queue with backpressure (tell() blocks or drops when full)
4. Location transparency — actors are referenced by address, not direct reference

Design:
- Actor: base class with on_receive(message) handler
- ActorRef: handle for sending messages, decoupled from Actor instance
- ActorSystem: top-level container, manages lifecycle
- Supervisor: parent actor that monitors children

Trade-off: thread-per-actor vs thread pool. Thread-per-actor is simpler but doesn't scale
to thousands of actors. Thread pool + cooperative scheduling is more scalable. For this
implementation I'll use a thread pool with one worker per active actor (up to pool size),
with actors sharing workers when idle.

Failure mode: if on_receive raises, the supervisor catches it. Restart strategy creates a
new actor instance but preserves the mailbox. Stop strategy kills the actor and notifies
dependents. Escalate passes the failure to the supervisor's supervisor.

I'll use threading.Event for mailbox signaling and a bounded deque for backpressure.
</think>

```python
import threading
import time
import queue
import traceback
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Type
from enum import Enum
from concurrent.futures import ThreadPoolExecutor


class SupervisorStrategy(Enum):
    RESTART = "restart"
    STOP = "stop"
    ESCALATE = "escalate"


@dataclass
class ActorMessage:
    content: Any
    sender: Optional["ActorRef"] = None
    message_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


class MailboxFull(Exception):
    pass


class ActorStopped(Exception):
    pass


class ActorRef:
    """Handle for communicating with an actor without direct reference."""

    def __init__(self, address: str, mailbox: queue.Queue, system: "ActorSystem"):
        self.address = address
        self._mailbox = mailbox
        self._system = system

    def tell(self, message: Any, sender: Optional["ActorRef"] = None, timeout: float = 5.0):
        msg = ActorMessage(content=message, sender=sender)
        try:
            self._mailbox.put(msg, timeout=timeout)
        except queue.Full:
            raise MailboxFull(f"Mailbox full for actor {self.address}")

    def ask(self, message: Any, timeout: float = 5.0) -> Any:
        """Send and wait for response (request-reply)."""
        response_box: queue.Queue = queue.Queue(maxsize=1)
        reply_ref = ActorRef(f"{self.address}/reply", response_box, self._system)
        self.tell(message, sender=reply_ref)
        try:
            reply = response_box.get(timeout=timeout)
            return reply.content
        except queue.Empty:
            raise TimeoutError(f"No reply from {self.address} within {timeout}s")

    def __repr__(self):
        return f"ActorRef({self.address})"


class Actor(ABC):
    def __init__(self):
        self.self_ref: Optional[ActorRef] = None
        self.context: Optional["ActorContext"] = None

    @abstractmethod
    def on_receive(self, message: Any, sender: Optional[ActorRef] = None):
        pass

    def pre_start(self):
        pass

    def post_stop(self):
        pass

    def pre_restart(self, error: Exception):
        pass

    def reply(self, message: Any, sender: Optional[ActorRef] = None):
        if sender:
            sender.tell(message)


@dataclass
class ActorContext:
    system: "ActorSystem"
    parent: Optional[ActorRef]
    children: dict = field(default_factory=dict)  # name -> ActorRef
    supervisor_strategy: SupervisorStrategy = SupervisorStrategy.RESTART

    def spawn(self, name: str, actor_class: Type[Actor], *args,
              mailbox_size: int = 100, **kwargs) -> ActorRef:
        return self.system.spawn(actor_class, name, *args,
                                mailbox_size=mailbox_size,
                                parent=self, **kwargs)


class ActorSystem:
    def __init__(self, max_workers: int = 8):
        self._actors: dict[str, dict] = {}  # address -> {actor, ref, mailbox, thread, alive}
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._lock = threading.Lock()
        self._running = True

    def spawn(self, actor_class: Type[Actor], name: str, *args,
              mailbox_size: int = 100, parent: Optional[ActorContext] = None,
              supervisor_strategy: SupervisorStrategy = SupervisorStrategy.RESTART,
              **kwargs) -> ActorRef:
        address = name
        mailbox: queue.Queue = queue.Queue(maxsize=mailbox_size)
        ref = ActorRef(address, mailbox, self)

        actor = actor_class(*args, **kwargs)
        actor.self_ref = ref
        actor.context = ActorContext(
            system=self,
            parent=parent.parent if parent else None,
            supervisor_strategy=supervisor_strategy,
        )

        entry = {
            "actor": actor,
            "actor_class": actor_class,
            "args": args,
            "kwargs": kwargs,
            "ref": ref,
            "mailbox": mailbox,
            "alive": True,
            "supervisor_strategy": supervisor_strategy,
        }

        with self._lock:
            self._actors[address] = entry

        actor.pre_start()
        self._executor.submit(self._run_actor, address)

        if parent:
            parent.children[name] = ref

        return ref

    def _run_actor(self, address: str):
        while self._running:
            with self._lock:
                entry = self._actors.get(address)
                if not entry or not entry["alive"]:
                    return

            try:
                msg = entry["mailbox"].get(timeout=0.5)
            except queue.Empty:
                continue

            try:
                entry["actor"].on_receive(msg.content, sender=msg.sender)
            except Exception as e:
                self._handle_failure(address, e)

    def _handle_failure(self, address: str, error: Exception):
        with self._lock:
            entry = self._actors.get(address)
            if not entry:
                return
            strategy = entry["supervisor_strategy"]

        if strategy == SupervisorStrategy.RESTART:
            self._restart_actor(address, error)
        elif strategy == SupervisorStrategy.STOP:
            self.stop(address)
        elif strategy == SupervisorStrategy.ESCALATE:
            # In a full implementation, propagate to parent
            self.stop(address)

    def _restart_actor(self, address: str, error: Exception):
        with self._lock:
            entry = self._actors.get(address)
            if not entry:
                return

        old_actor = entry["actor"]
        old_actor.pre_restart(error)

        new_actor = entry["actor_class"](*entry["args"], **entry["kwargs"])
        new_actor.self_ref = entry["ref"]
        new_actor.context = old_actor.context

        entry["actor"] = new_actor
        new_actor.pre_start()

    def stop(self, address: str):
        with self._lock:
            entry = self._actors.get(address)
            if entry:
                entry["alive"] = False
                entry["actor"].post_stop()

    def shutdown(self):
        self._running = False
        with self._lock:
            for entry in self._actors.values():
                entry["alive"] = False
                entry["actor"].post_stop()
        self._executor.shutdown(wait=True)


# --- Usage and tests ---

class CounterActor(Actor):
    def __init__(self):
        super().__init__()
        self.count = 0

    def on_receive(self, message, sender=None):
        if message == "increment":
            self.count += 1
        elif message == "get":
            self.reply(self.count, sender)
        elif message == "crash":
            raise RuntimeError("Intentional crash")


class EchoActor(Actor):
    def __init__(self):
        super().__init__()
        self.received = []

    def on_receive(self, message, sender=None):
        self.received.append(message)
        self.reply(f"echo: {message}", sender)


def test_actors():
    system = ActorSystem(max_workers=4)

    # Basic message passing
    counter_ref = system.spawn(CounterActor, "counter")
    counter_ref.tell("increment")
    counter_ref.tell("increment")
    counter_ref.tell("increment")
    time.sleep(0.3)

    result = counter_ref.ask("get", timeout=2.0)
    assert result == 3, f"Expected 3, got {result}"

    # Test ask pattern (request-reply)
    echo_ref = system.spawn(EchoActor, "echo")
    reply = echo_ref.ask("hello", timeout=2.0)
    assert reply == "echo: hello"

    # Test crash + restart (supervisor restarts actor)
    counter_ref.tell("crash")
    time.sleep(0.5)
    # Actor should be restarted with fresh state
    counter_ref.tell("increment")
    time.sleep(0.3)
    result = counter_ref.ask("get", timeout=2.0)
    assert result == 1, f"After restart expected 1, got {result}"

    # Test mailbox backpressure
    small_ref = system.spawn(EchoActor, "small", mailbox_size=2)
    small_ref.tell("msg1")
    small_ref.tell("msg2")
    try:
        small_ref.tell("msg3", timeout=0.1)  # mailbox full
        # May succeed if messages were consumed
    except MailboxFull:
        pass  # Expected when mailbox is full

    # Test stop strategy
    stop_ref = system.spawn(
        CounterActor, "stop-on-crash",
        supervisor_strategy=SupervisorStrategy.STOP,
    )
    stop_ref.tell("crash")
    time.sleep(0.5)
    entry = system._actors.get("stop-on-crash")
    assert entry is None or not entry["alive"]

    system.shutdown()
    print("All actor model tests passed.")


if __name__ == "__main__":
    test_actors()
```'''
    ),
    (
        "deep_reasoning/object-pool-lazy-init",
        r'''Implement a generic object pool in Python with lazy initialization, object validation on borrow, automatic cleanup of stale objects, and pool resizing.''',
        r'''<think>
An object pool manages a set of reusable objects (DB connections, HTTP sessions, heavy-weight
resources). The goal is to amortize creation cost across many uses.

Key design decisions:
1. Lazy initialization — don't create all objects upfront. Create on demand up to max_size.
2. Validation — before handing out an object, verify it's still usable (e.g., connection alive).
3. Cleanup — periodically evict objects that have been idle too long (they may have timed out
   on the server side anyway).
4. Resizing — support shrinking the pool when demand drops, expanding when it grows.

Trade-off: I could use a simple list or a more sophisticated approach with generation tracking.
Generation tracking lets me invalidate all objects from before a certain time (useful for
after a backend restart). I'll use a tagged wrapper that tracks creation time and last use.

Interface:
- ObjectPool(factory, validator, max_size, min_size, max_idle_time)
- pool.borrow(timeout) -> obj
- pool.return_obj(obj)
- Context manager support
- pool.resize(new_max)

Failure modes:
- Factory raises during creation: propagate, don't corrupt pool state
- Validator raises: treat as invalid, discard
- Return of an object not from this pool: reject
- Double return: detect and ignore

Threading: use Condition for efficient blocking when pool is exhausted.
</think>

```python
import threading
import time
import uuid
from typing import TypeVar, Generic, Callable, Optional
from dataclasses import dataclass, field

T = TypeVar("T")


class PoolExhausted(Exception):
    pass


class InvalidPoolObject(Exception):
    pass


@dataclass
class PooledObject(Generic[T]):
    obj: T
    pool_id: str
    object_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    created_at: float = field(default_factory=time.monotonic)
    last_used: float = field(default_factory=time.monotonic)
    borrow_count: int = 0
    _returned: bool = False


class ObjectPool(Generic[T]):
    def __init__(
        self,
        factory: Callable[[], T],
        validator: Optional[Callable[[T], bool]] = None,
        destructor: Optional[Callable[[T], None]] = None,
        max_size: int = 10,
        min_size: int = 0,
        max_idle_time: float = 300.0,
        max_lifetime: float = 3600.0,
        cleanup_interval: float = 60.0,
    ):
        self._factory = factory
        self._validator = validator or (lambda obj: True)
        self._destructor = destructor or (lambda obj: None)
        self._max_size = max_size
        self._min_size = min_size
        self._max_idle_time = max_idle_time
        self._max_lifetime = max_lifetime
        self._pool_id = str(uuid.uuid4())[:8]

        self._lock = threading.Condition()
        self._idle: list[PooledObject[T]] = []
        self._in_use: dict[str, PooledObject[T]] = {}  # object_id -> PooledObject
        self._total_created = 0
        self._closed = False

        # Start cleanup thread
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop,
                                                args=(cleanup_interval,), daemon=True)
        self._cleanup_thread.start()

    def borrow(self, timeout: float = 5.0) -> T:
        deadline = time.monotonic() + timeout

        with self._lock:
            while True:
                if self._closed:
                    raise PoolExhausted("Pool is closed")

                # Try to get a valid idle object
                while self._idle:
                    pooled = self._idle.pop()
                    if self._is_valid(pooled):
                        pooled.last_used = time.monotonic()
                        pooled.borrow_count += 1
                        pooled._returned = False
                        self._in_use[pooled.object_id] = pooled
                        return pooled.obj
                    else:
                        self._destroy(pooled)

                # Try to create a new one
                if self._total_created < self._max_size:
                    try:
                        obj = self._factory()
                        self._total_created += 1
                        pooled = PooledObject(obj=obj, pool_id=self._pool_id)
                        pooled.borrow_count = 1
                        pooled._returned = False
                        self._in_use[pooled.object_id] = pooled
                        return obj
                    except Exception:
                        raise

                # Wait for a return
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise PoolExhausted(
                        f"No object available within {timeout}s "
                        f"(max={self._max_size}, in_use={len(self._in_use)})"
                    )
                self._lock.wait(timeout=remaining)

    def return_obj(self, obj: T):
        with self._lock:
            # Find the pooled wrapper
            target = None
            for oid, pooled in self._in_use.items():
                if pooled.obj is obj:
                    target = pooled
                    break

            if target is None:
                return  # Not from this pool or already returned

            if target._returned:
                return  # Double return

            target._returned = True
            target.last_used = time.monotonic()
            del self._in_use[target.object_id]

            if not self._closed and self._is_valid(target):
                self._idle.append(target)
            else:
                self._destroy(target)

            self._lock.notify()

    def _is_valid(self, pooled: PooledObject[T]) -> bool:
        now = time.monotonic()
        # Check max lifetime
        if now - pooled.created_at > self._max_lifetime:
            return False
        # Check idle time
        if now - pooled.last_used > self._max_idle_time:
            return False
        # Custom validator
        try:
            return self._validator(pooled.obj)
        except Exception:
            return False

    def _destroy(self, pooled: PooledObject[T]):
        try:
            self._destructor(pooled.obj)
        except Exception:
            pass
        self._total_created -= 1

    def _cleanup_loop(self, interval: float):
        while not self._closed:
            time.sleep(interval)
            self._cleanup()

    def _cleanup(self):
        with self._lock:
            to_remove = []
            # Keep at least min_size objects
            total_healthy = len(self._idle) + len(self._in_use)

            for pooled in self._idle:
                if total_healthy <= self._min_size:
                    break
                if not self._is_valid(pooled):
                    to_remove.append(pooled)
                    total_healthy -= 1

            for pooled in to_remove:
                self._idle.remove(pooled)
                self._destroy(pooled)

    def resize(self, new_max: int):
        with self._lock:
            old_max = self._max_size
            self._max_size = max(new_max, self._min_size)
            if new_max > old_max:
                self._lock.notify_all()  # wake up waiters

    def close(self):
        with self._lock:
            self._closed = True
            for pooled in self._idle:
                self._destroy(pooled)
            self._idle.clear()
            self._lock.notify_all()

    @property
    def stats(self) -> dict:
        with self._lock:
            return {
                "idle": len(self._idle),
                "in_use": len(self._in_use),
                "total_created": self._total_created,
                "max_size": self._max_size,
            }

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class pooled_object:
    """Context manager for auto borrow/return."""
    def __init__(self, pool: ObjectPool, timeout: float = 5.0):
        self._pool = pool
        self._timeout = timeout
        self._obj = None

    def __enter__(self):
        self._obj = self._pool.borrow(self._timeout)
        return self._obj

    def __exit__(self, *exc):
        if self._obj is not None:
            self._pool.return_obj(self._obj)


# --- Usage and tests ---

class HeavyResource:
    _counter = 0

    def __init__(self):
        HeavyResource._counter += 1
        self.resource_id = HeavyResource._counter
        self.healthy = True

    def process(self, data: str) -> str:
        if not self.healthy:
            raise RuntimeError("Resource is broken")
        return f"processed-{data}-by-{self.resource_id}"

    def close(self):
        self.healthy = False


def test_object_pool():
    HeavyResource._counter = 0
    destroyed = []

    pool = ObjectPool(
        factory=HeavyResource,
        validator=lambda r: r.healthy,
        destructor=lambda r: (destroyed.append(r.resource_id), r.close()),
        max_size=3,
        min_size=1,
        max_idle_time=1.0,
        max_lifetime=10.0,
        cleanup_interval=100,  # manual cleanup in test
    )

    # Lazy init — nothing created yet
    assert pool.stats["total_created"] == 0

    # Borrow creates on demand
    with pooled_object(pool) as res:
        result = res.process("hello")
        assert "processed-hello" in result
    assert pool.stats["idle"] == 1
    assert pool.stats["total_created"] == 1

    # Reuse idle object
    with pooled_object(pool) as res:
        assert res.resource_id == 1  # same object reused

    # Exhaust pool
    r1 = pool.borrow()
    r2 = pool.borrow()
    r3 = pool.borrow()
    assert pool.stats["in_use"] == 3
    try:
        pool.borrow(timeout=0.1)
        assert False, "Should raise"
    except PoolExhausted:
        pass

    pool.return_obj(r1)
    pool.return_obj(r2)
    pool.return_obj(r3)

    # Validation — mark one as unhealthy
    r = pool.borrow()
    pool.return_obj(r)
    r.healthy = False
    r2 = pool.borrow()  # Should get a new object since r is invalid
    assert r2.resource_id != r.resource_id or r2.healthy
    pool.return_obj(r2)

    # Test idle expiry
    time.sleep(1.2)
    pool._cleanup()
    # Should have cleaned up idle objects past max_idle_time
    # but kept min_size

    # Resize
    pool.resize(5)
    assert pool.stats["max_size"] == 5

    pool.close()
    print("All object pool tests passed.")


if __name__ == "__main__":
    test_object_pool()
```'''
    ),
    (
        "deep_reasoning/specification-pattern",
        r'''Implement the Specification pattern in Python for composable business rules with AND, OR, NOT composition, rule explanations, and integration with filtering collections.''',
        r'''<think>
The Specification pattern encapsulates a business rule into a reusable, composable object.
Each specification answers "does this candidate satisfy the rule?" with a boolean.

The key value proposition over plain functions: composability and explainability. You can
build complex rules from simple ones and trace which sub-rules passed or failed.

Interface:
- Specification.is_satisfied_by(candidate) -> bool
- spec1 & spec2 (AND), spec1 | spec2 (OR), ~spec (NOT)
- spec.explain(candidate) -> explanation tree showing pass/fail for each sub-rule
- Collection filtering: filter(items, spec)

Design:
- Base Specification ABC with is_satisfied_by and explain
- Leaf specifications: field comparisons, callables, type checks
- Composite: AndSpec, OrSpec, NotSpec
- ExplanationNode: tree structure for trace output

Trade-off: I could make explain() return a flat list or a tree. Tree preserves the
logical structure and is more useful for debugging nested rules. But it's more complex
to render. I'll do tree structure with a to_string() helper.

This pattern is useful for:
- Query builders (translate specs to SQL WHERE clauses)
- Validation (explain which rules failed)
- Policy engines (compose authorization rules)
</think>

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, TypeVar, Sequence, Optional

T = TypeVar("T")


@dataclass
class ExplanationNode:
    rule_name: str
    satisfied: bool
    children: list["ExplanationNode"] = field(default_factory=list)
    details: str = ""

    def to_string(self, indent: int = 0) -> str:
        prefix = "  " * indent
        icon = "PASS" if self.satisfied else "FAIL"
        line = f"{prefix}[{icon}] {self.rule_name}"
        if self.details:
            line += f" ({self.details})"
        lines = [line]
        for child in self.children:
            lines.append(child.to_string(indent + 1))
        return "\n".join(lines)


class Specification(ABC):
    @abstractmethod
    def is_satisfied_by(self, candidate: Any) -> bool:
        pass

    @abstractmethod
    def explain(self, candidate: Any) -> ExplanationNode:
        pass

    def __and__(self, other: "Specification") -> "AndSpecification":
        return AndSpecification(self, other)

    def __or__(self, other: "Specification") -> "OrSpecification":
        return OrSpecification(self, other)

    def __invert__(self) -> "NotSpecification":
        return NotSpecification(self)

    def filter(self, items: Sequence[T]) -> list[T]:
        return [item for item in items if self.is_satisfied_by(item)]

    def first(self, items: Sequence[T]) -> Optional[T]:
        for item in items:
            if self.is_satisfied_by(item):
                return item
        return None


class AndSpecification(Specification):
    def __init__(self, *specs: Specification):
        self.specs = list(specs)

    def is_satisfied_by(self, candidate: Any) -> bool:
        return all(s.is_satisfied_by(candidate) for s in self.specs)

    def explain(self, candidate: Any) -> ExplanationNode:
        children = [s.explain(candidate) for s in self.specs]
        satisfied = all(c.satisfied for c in children)
        return ExplanationNode("AND", satisfied, children)

    def __and__(self, other: Specification) -> "AndSpecification":
        # Flatten nested ANDs
        if isinstance(other, AndSpecification):
            return AndSpecification(*self.specs, *other.specs)
        return AndSpecification(*self.specs, other)


class OrSpecification(Specification):
    def __init__(self, *specs: Specification):
        self.specs = list(specs)

    def is_satisfied_by(self, candidate: Any) -> bool:
        return any(s.is_satisfied_by(candidate) for s in self.specs)

    def explain(self, candidate: Any) -> ExplanationNode:
        children = [s.explain(candidate) for s in self.specs]
        satisfied = any(c.satisfied for c in children)
        return ExplanationNode("OR", satisfied, children)

    def __or__(self, other: Specification) -> "OrSpecification":
        if isinstance(other, OrSpecification):
            return OrSpecification(*self.specs, *other.specs)
        return OrSpecification(*self.specs, other)


class NotSpecification(Specification):
    def __init__(self, spec: Specification):
        self.spec = spec

    def is_satisfied_by(self, candidate: Any) -> bool:
        return not self.spec.is_satisfied_by(candidate)

    def explain(self, candidate: Any) -> ExplanationNode:
        child = self.spec.explain(candidate)
        return ExplanationNode("NOT", not child.satisfied, [child])


# --- Leaf Specifications ---

class FieldSpec(Specification):
    """Check a field against a value with an operator."""

    def __init__(self, field_name: str, operator: str, value: Any):
        self.field_name = field_name
        self.operator = operator
        self.value = value

    def _get_field(self, candidate: Any) -> Any:
        if isinstance(candidate, dict):
            return candidate.get(self.field_name)
        return getattr(candidate, self.field_name, None)

    def is_satisfied_by(self, candidate: Any) -> bool:
        actual = self._get_field(candidate)
        if actual is None:
            return False
        ops = {
            "==": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            ">": lambda a, b: a > b,
            "<": lambda a, b: a < b,
            ">=": lambda a, b: a >= b,
            "<=": lambda a, b: a <= b,
            "in": lambda a, b: a in b,
            "contains": lambda a, b: b in a,
        }
        op_fn = ops.get(self.operator)
        if not op_fn:
            return False
        try:
            return op_fn(actual, self.value)
        except TypeError:
            return False

    def explain(self, candidate: Any) -> ExplanationNode:
        actual = self._get_field(candidate)
        satisfied = self.is_satisfied_by(candidate)
        return ExplanationNode(
            f"{self.field_name} {self.operator} {self.value!r}",
            satisfied,
            details=f"actual={actual!r}",
        )


class PredicateSpec(Specification):
    """Wraps a callable predicate with a name for explanation."""

    def __init__(self, name: str, predicate: Callable[[Any], bool]):
        self.name = name
        self.predicate = predicate

    def is_satisfied_by(self, candidate: Any) -> bool:
        try:
            return self.predicate(candidate)
        except Exception:
            return False

    def explain(self, candidate: Any) -> ExplanationNode:
        satisfied = self.is_satisfied_by(candidate)
        return ExplanationNode(self.name, satisfied)


# --- Convenience builders ---

def field_eq(name: str, value: Any) -> FieldSpec:
    return FieldSpec(name, "==", value)

def field_gt(name: str, value: Any) -> FieldSpec:
    return FieldSpec(name, ">", value)

def field_lt(name: str, value: Any) -> FieldSpec:
    return FieldSpec(name, "<", value)

def field_gte(name: str, value: Any) -> FieldSpec:
    return FieldSpec(name, ">=", value)

def field_in(name: str, values: list) -> FieldSpec:
    return FieldSpec(name, "in", values)


# --- Usage and tests ---

def test_specification():
    # Product data
    products = [
        {"name": "Laptop", "price": 999, "category": "electronics", "in_stock": True, "rating": 4.5},
        {"name": "Mouse", "price": 25, "category": "electronics", "in_stock": True, "rating": 4.0},
        {"name": "Desk", "price": 300, "category": "furniture", "in_stock": False, "rating": 3.8},
        {"name": "Chair", "price": 450, "category": "furniture", "in_stock": True, "rating": 4.2},
        {"name": "Book", "price": 15, "category": "books", "in_stock": True, "rating": 4.9},
    ]

    # Simple specs
    is_electronics = field_eq("category", "electronics")
    is_in_stock = field_eq("in_stock", True)
    is_affordable = FieldSpec("price", "<", 100)
    is_high_rated = field_gte("rating", 4.0)

    # Composition: affordable electronics in stock
    deal_spec = is_electronics & is_in_stock & is_affordable
    deals = deal_spec.filter(products)
    assert len(deals) == 1
    assert deals[0]["name"] == "Mouse"

    # OR: electronics or furniture
    elec_or_furn = is_electronics | field_eq("category", "furniture")
    result = elec_or_furn.filter(products)
    assert len(result) == 4  # Laptop, Mouse, Desk, Chair

    # NOT: not electronics
    not_electronics = ~is_electronics
    result = not_electronics.filter(products)
    assert all(p["category"] != "electronics" for p in result)

    # Complex: high-rated AND (affordable OR in-stock) AND NOT furniture
    complex_spec = (
        is_high_rated &
        (is_affordable | is_in_stock) &
        ~field_eq("category", "furniture")
    )
    result = complex_spec.filter(products)
    names = [p["name"] for p in result]
    assert "Laptop" in names  # high rated, in stock, not furniture
    assert "Mouse" in names   # high rated, in stock AND affordable
    assert "Book" in names    # high rated, in stock, not furniture
    assert "Desk" not in names  # not in stock and not high rated enough... actually 3.8 < 4.0
    assert "Chair" not in names  # furniture

    # Explain
    laptop = products[0]
    explanation = deal_spec.explain(laptop)
    output = explanation.to_string()
    assert "FAIL" in output  # Laptop is not affordable
    assert "PASS" in output  # But it is electronics and in stock

    # Explanation tree structure
    assert explanation.rule_name == "AND"
    assert not explanation.satisfied  # overall fails

    # Custom predicate spec
    has_short_name = PredicateSpec("name_length <= 5", lambda p: len(p["name"]) <= 5)
    short_named = has_short_name.filter(products)
    assert all(len(p["name"]) <= 5 for p in short_named)

    # first() helper
    first_deal = deal_spec.first(products)
    assert first_deal["name"] == "Mouse"

    # No match returns None
    impossible = field_gt("price", 10000)
    assert impossible.first(products) is None

    print("All specification pattern tests passed.")


if __name__ == "__main__":
    test_specification()
```'''
    ),
    (
        "deep_reasoning/unit-of-work-change-tracking",
        r'''Implement the Unit of Work pattern in Python with identity map, automatic change tracking (dirty checking), batch commit, and rollback support.''',
        r'''<think>
Unit of Work tracks all changes during a business transaction and commits them atomically.
It works with an Identity Map to ensure each entity is loaded only once.

Core components:
1. Identity Map — cache of loaded entities by (type, id), ensures one instance per entity
2. Change tracking — detect which entities were created, modified, or deleted
3. Batch commit — flush all changes in a single "transaction"
4. Rollback — discard all pending changes

Design decisions:
- How to detect changes? Two approaches:
  a) Snapshot comparison — save original state on load, compare at commit time
  b) Dirty flag — entities mark themselves dirty on attribute change
  Snapshot comparison is more transparent (no entity base class needed) but slower for
  large objects. Dirty flag is faster but invasive. I'll use snapshot comparison with
  an optional dirty flag override for performance-critical paths.

Interface:
- UnitOfWork(repository)
- uow.get(entity_type, entity_id) -> entity
- uow.register_new(entity)
- uow.register_deleted(entity)
- uow.commit() -> flushes all changes
- uow.rollback() -> discards changes

The repository is abstracted — could be a database, file system, or API. The UoW
coordinates but doesn't implement persistence directly.

Failure mode: if commit partially fails (3 of 5 updates succeed), we need to handle
this. Options: all-or-nothing via transaction, or record which operations succeeded.
I'll support both via a configurable commit strategy.
</think>

```python
import copy
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Optional, Type, TypeVar, Generic
from enum import Enum

T = TypeVar("T")


class EntityState(Enum):
    CLEAN = "clean"
    NEW = "new"
    DIRTY = "dirty"
    DELETED = "deleted"


class CommitError(Exception):
    def __init__(self, message: str, committed: list, failed: list):
        self.committed = committed
        self.failed = failed
        super().__init__(message)


# --- Entity Base ---

@dataclass
class Entity:
    """Base class for trackable entities."""
    id: Any = None

    def _get_identity(self) -> tuple:
        return (type(self).__name__, self.id)


# --- Repository Interface ---

class Repository(ABC):
    @abstractmethod
    def find(self, entity_type: Type[T], entity_id: Any) -> Optional[T]:
        pass

    @abstractmethod
    def insert(self, entity: Entity):
        pass

    @abstractmethod
    def update(self, entity: Entity):
        pass

    @abstractmethod
    def delete(self, entity: Entity):
        pass


class InMemoryRepository(Repository):
    """Simple in-memory repository for testing."""

    def __init__(self):
        self.store: dict[tuple, dict] = {}  # (type_name, id) -> dict
        self.operations: list[tuple[str, Any]] = []  # log of operations

    def find(self, entity_type: Type[T], entity_id: Any) -> Optional[T]:
        key = (entity_type.__name__, entity_id)
        data = self.store.get(key)
        if data is None:
            return None
        entity = entity_type(**data)
        return entity

    def insert(self, entity: Entity):
        key = entity._get_identity()
        self.store[key] = asdict(entity)
        self.operations.append(("INSERT", key))

    def update(self, entity: Entity):
        key = entity._get_identity()
        self.store[key] = asdict(entity)
        self.operations.append(("UPDATE", key))

    def delete(self, entity: Entity):
        key = entity._get_identity()
        self.store.pop(key, None)
        self.operations.append(("DELETE", key))


# --- Identity Map ---

class IdentityMap:
    def __init__(self):
        self._entities: dict[tuple, Entity] = {}
        self._snapshots: dict[tuple, dict] = {}  # original state for dirty checking

    def get(self, entity_type: Type, entity_id: Any) -> Optional[Entity]:
        key = (entity_type.__name__, entity_id)
        return self._entities.get(key)

    def register(self, entity: Entity, snapshot: Optional[dict] = None):
        key = entity._get_identity()
        self._entities[key] = entity
        if snapshot is not None:
            self._snapshots[key] = snapshot

    def remove(self, entity: Entity):
        key = entity._get_identity()
        self._entities.pop(key, None)
        self._snapshots.pop(key, None)

    def is_dirty(self, entity: Entity) -> bool:
        key = entity._get_identity()
        original = self._snapshots.get(key)
        if original is None:
            return False  # No snapshot = new or not tracked
        current = asdict(entity)
        return current != original

    def all_entities(self) -> list[Entity]:
        return list(self._entities.values())

    def clear(self):
        self._entities.clear()
        self._snapshots.clear()


# --- Unit of Work ---

class UnitOfWork:
    def __init__(self, repository: Repository):
        self._repo = repository
        self._identity_map = IdentityMap()
        self._new: list[Entity] = []
        self._deleted: list[Entity] = []
        self._committed = False

    def get(self, entity_type: Type[T], entity_id: Any) -> Optional[T]:
        """Load entity, using identity map for deduplication."""
        # Check identity map first
        cached = self._identity_map.get(entity_type, entity_id)
        if cached is not None:
            return cached

        # Load from repository
        entity = self._repo.find(entity_type, entity_id)
        if entity is not None:
            snapshot = asdict(entity)
            self._identity_map.register(entity, snapshot=snapshot)
        return entity

    def register_new(self, entity: Entity):
        """Register a new entity to be inserted on commit."""
        self._new.append(entity)
        self._identity_map.register(entity)

    def register_deleted(self, entity: Entity):
        """Mark an entity for deletion on commit."""
        self._deleted.append(entity)

    def commit(self):
        """Flush all changes: inserts, updates, deletes."""
        committed = []
        failed = []

        try:
            # Process inserts
            for entity in self._new:
                try:
                    self._repo.insert(entity)
                    committed.append(("INSERT", entity._get_identity()))
                except Exception as e:
                    failed.append(("INSERT", entity._get_identity(), str(e)))

            # Process updates (dirty check)
            for entity in self._identity_map.all_entities():
                if entity in self._new or entity in self._deleted:
                    continue
                if self._identity_map.is_dirty(entity):
                    try:
                        self._repo.update(entity)
                        committed.append(("UPDATE", entity._get_identity()))
                    except Exception as e:
                        failed.append(("UPDATE", entity._get_identity(), str(e)))

            # Process deletes
            for entity in self._deleted:
                try:
                    self._repo.delete(entity)
                    committed.append(("DELETE", entity._get_identity()))
                except Exception as e:
                    failed.append(("DELETE", entity._get_identity(), str(e)))

            if failed:
                raise CommitError(
                    f"{len(failed)} operations failed",
                    committed=committed,
                    failed=failed,
                )

            # Clear tracking state after successful commit
            self._new.clear()
            self._deleted.clear()
            # Update snapshots to current state
            for entity in self._identity_map.all_entities():
                self._identity_map._snapshots[entity._get_identity()] = asdict(entity)

            self._committed = True

        except CommitError:
            raise

    def rollback(self):
        """Discard all pending changes, revert to loaded state."""
        # Revert dirty entities to their snapshots
        for entity in self._identity_map.all_entities():
            key = entity._get_identity()
            snapshot = self._identity_map._snapshots.get(key)
            if snapshot:
                for attr, value in snapshot.items():
                    setattr(entity, attr, value)

        # Discard new registrations
        for entity in self._new:
            self._identity_map.remove(entity)
        self._new.clear()
        self._deleted.clear()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()


# --- Example Entities ---

@dataclass
class User(Entity):
    id: int = 0
    name: str = ""
    email: str = ""
    role: str = "user"


@dataclass
class Order(Entity):
    id: int = 0
    user_id: int = 0
    total: float = 0.0
    status: str = "pending"


# --- Usage and tests ---

def test_unit_of_work():
    repo = InMemoryRepository()

    # Seed some data
    repo.store[("User", 1)] = {"id": 1, "name": "Alice", "email": "alice@example.com", "role": "admin"}
    repo.store[("User", 2)] = {"id": 2, "name": "Bob", "email": "bob@example.com", "role": "user"}
    repo.store[("Order", 100)] = {"id": 100, "user_id": 1, "total": 99.99, "status": "pending"}

    # Test identity map deduplication
    with UnitOfWork(repo) as uow:
        user1a = uow.get(User, 1)
        user1b = uow.get(User, 1)
        assert user1a is user1b  # same instance

    # Test dirty tracking + commit
    repo.operations.clear()
    with UnitOfWork(repo) as uow:
        user = uow.get(User, 1)
        assert user.name == "Alice"
        user.name = "Alice Updated"  # dirty

        order = uow.get(Order, 100)
        # order not modified — should not be updated

        uow.commit()

    assert ("UPDATE", ("User", 1)) in repo.operations
    assert ("UPDATE", ("Order", 100)) not in repo.operations
    assert repo.store[("User", 1)]["name"] == "Alice Updated"

    # Test register new
    repo.operations.clear()
    with UnitOfWork(repo) as uow:
        new_user = User(id=3, name="Charlie", email="charlie@example.com")
        uow.register_new(new_user)
        uow.commit()

    assert ("INSERT", ("User", 3)) in repo.operations
    assert repo.store[("User", 3)]["name"] == "Charlie"

    # Test register deleted
    repo.operations.clear()
    with UnitOfWork(repo) as uow:
        user = uow.get(User, 2)
        uow.register_deleted(user)
        uow.commit()

    assert ("DELETE", ("User", 2)) in repo.operations
    assert ("User", 2) not in repo.store

    # Test rollback
    with UnitOfWork(repo) as uow:
        user = uow.get(User, 1)
        original_name = user.name
        user.name = "SHOULD NOT PERSIST"
        uow.rollback()
        assert user.name == original_name

    # Test context manager rollback on exception
    try:
        with UnitOfWork(repo) as uow:
            user = uow.get(User, 1)
            user.name = "SHOULD ALSO NOT PERSIST"
            raise ValueError("Something went wrong")
    except ValueError:
        pass
    assert repo.store[("User", 1)]["name"] != "SHOULD ALSO NOT PERSIST"

    print("All Unit of Work tests passed.")


if __name__ == "__main__":
    test_unit_of_work()
```'''
    ),
    (
        "deep_reasoning/outbox-pattern-reliable-events",
        r'''Implement the Outbox pattern in Python for reliable event publishing. Events are stored in a transactional outbox table alongside domain changes, then published asynchronously by a relay process.''',
        r'''<think>
The Outbox pattern solves the dual-write problem: when you need to update a database AND
publish an event, doing them separately risks inconsistency (DB update succeeds but event
publish fails, or vice versa).

Solution: store events in an outbox table in the SAME database transaction as the domain
change. A separate relay process reads unpublished events and publishes them, marking them
as published.

Key design decisions:
1. Outbox table: stores event_id, aggregate_id, event_type, payload, created_at, published_at
2. Relay process: polls the outbox, publishes to the message broker, marks as published
3. At-least-once semantics: if the relay crashes after publishing but before marking, it
   will re-publish. Consumers must be idempotent.
4. Ordering: events for the same aggregate must be published in order

Trade-off: polling vs change data capture (CDC). Polling is simpler but adds latency.
CDC is real-time but requires database-specific support. I'll implement polling with
configurable interval.

Interface:
- OutboxStore: transactional store for domain + events
- OutboxRelay: background process that publishes events
- EventPublisher: abstraction for the message broker

Failure modes:
- Relay crashes mid-batch: next run re-publishes from last checkpoint
- Publisher is down: relay retries with backoff, events queue up in outbox
- Outbox grows unbounded: cleanup job deletes old published events
</think>

```python
import time
import threading
import json
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from abc import ABC, abstractmethod
from collections import defaultdict


@dataclass
class OutboxEvent:
    event_id: str
    aggregate_id: str
    aggregate_type: str
    event_type: str
    payload: dict
    created_at: float
    published_at: Optional[float] = None
    retry_count: int = 0
    sequence: int = 0  # per-aggregate ordering


class OutboxStore:
    """Simulates a transactional store with outbox table."""

    def __init__(self):
        self._lock = threading.Lock()
        self._domain_data: dict[str, dict] = {}
        self._outbox: list[OutboxEvent] = []
        self._sequence_counters: dict[str, int] = defaultdict(int)
        self._in_transaction = False
        self._tx_domain_ops: list[tuple[str, str, dict]] = []  # (op, key, data)
        self._tx_events: list[OutboxEvent] = []

    def begin_transaction(self):
        self._lock.acquire()
        self._in_transaction = True
        self._tx_domain_ops = []
        self._tx_events = []

    def save_entity(self, key: str, data: dict):
        if not self._in_transaction:
            raise RuntimeError("Must be in a transaction")
        self._tx_domain_ops.append(("save", key, data))

    def delete_entity(self, key: str):
        if not self._in_transaction:
            raise RuntimeError("Must be in a transaction")
        self._tx_domain_ops.append(("delete", key, {}))

    def add_outbox_event(self, aggregate_id: str, aggregate_type: str,
                         event_type: str, payload: dict):
        if not self._in_transaction:
            raise RuntimeError("Must be in a transaction")
        seq = self._sequence_counters[aggregate_id] + 1
        self._sequence_counters[aggregate_id] = seq

        event = OutboxEvent(
            event_id=str(uuid.uuid4()),
            aggregate_id=aggregate_id,
            aggregate_type=aggregate_type,
            event_type=event_type,
            payload=payload,
            created_at=time.time(),
            sequence=seq,
        )
        self._tx_events.append(event)

    def commit_transaction(self):
        if not self._in_transaction:
            raise RuntimeError("No active transaction")
        try:
            # Apply domain operations
            for op, key, data in self._tx_domain_ops:
                if op == "save":
                    self._domain_data[key] = data
                elif op == "delete":
                    self._domain_data.pop(key, None)

            # Store outbox events
            self._outbox.extend(self._tx_events)

        finally:
            self._in_transaction = False
            self._tx_domain_ops = []
            self._tx_events = []
            self._lock.release()

    def rollback_transaction(self):
        if not self._in_transaction:
            return
        self._tx_domain_ops = []
        self._tx_events = []
        self._in_transaction = False
        self._lock.release()

    def get_unpublished_events(self, batch_size: int = 100) -> list[OutboxEvent]:
        with self._lock:
            unpublished = [e for e in self._outbox if e.published_at is None]
            # Sort by aggregate then sequence for ordering guarantee
            unpublished.sort(key=lambda e: (e.aggregate_id, e.sequence))
            return unpublished[:batch_size]

    def mark_published(self, event_ids: list[str]):
        with self._lock:
            now = time.time()
            for event in self._outbox:
                if event.event_id in event_ids:
                    event.published_at = now

    def increment_retry(self, event_id: str):
        with self._lock:
            for event in self._outbox:
                if event.event_id == event_id:
                    event.retry_count += 1
                    break

    def cleanup_published(self, older_than: float):
        with self._lock:
            cutoff = time.time() - older_than
            self._outbox = [
                e for e in self._outbox
                if e.published_at is None or e.published_at > cutoff
            ]

    def get_entity(self, key: str) -> Optional[dict]:
        with self._lock:
            return self._domain_data.get(key)

    @property
    def outbox_size(self) -> int:
        with self._lock:
            return len([e for e in self._outbox if e.published_at is None])


class EventPublisher(ABC):
    @abstractmethod
    def publish(self, event: OutboxEvent) -> bool:
        pass


class InMemoryPublisher(EventPublisher):
    def __init__(self, fail_on: Optional[set] = None):
        self.published: list[OutboxEvent] = []
        self._fail_on = fail_on or set()

    def publish(self, event: OutboxEvent) -> bool:
        if event.event_type in self._fail_on:
            return False
        self.published.append(event)
        return True


class OutboxRelay:
    """Background process that reads outbox and publishes events."""

    def __init__(self, store: OutboxStore, publisher: EventPublisher,
                 poll_interval: float = 1.0, batch_size: int = 100,
                 max_retries: int = 5):
        self._store = store
        self._publisher = publisher
        self._poll_interval = poll_interval
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._dead_letters: list[OutboxEvent] = []

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._relay_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _relay_loop(self):
        while self._running:
            self.process_batch()
            time.sleep(self._poll_interval)

    def process_batch(self) -> int:
        """Process one batch of events. Returns count published."""
        events = self._store.get_unpublished_events(self._batch_size)
        if not events:
            return 0

        published_ids = []
        for event in events:
            if event.retry_count >= self._max_retries:
                self._dead_letters.append(event)
                published_ids.append(event.event_id)  # remove from outbox
                continue

            success = self._publisher.publish(event)
            if success:
                published_ids.append(event.event_id)
            else:
                self._store.increment_retry(event.event_id)

        if published_ids:
            self._store.mark_published(published_ids)

        return len(published_ids)

    @property
    def dead_letters(self) -> list[OutboxEvent]:
        return list(self._dead_letters)


# --- Domain Service using Outbox ---

class OrderService:
    def __init__(self, store: OutboxStore):
        self._store = store

    def create_order(self, order_id: str, user_id: str, items: list[dict], total: float):
        self._store.begin_transaction()
        try:
            self._store.save_entity(f"order:{order_id}", {
                "order_id": order_id,
                "user_id": user_id,
                "items": items,
                "total": total,
                "status": "created",
            })
            self._store.add_outbox_event(
                aggregate_id=order_id,
                aggregate_type="Order",
                event_type="OrderCreated",
                payload={"order_id": order_id, "user_id": user_id, "total": total},
            )
            self._store.commit_transaction()
        except Exception:
            self._store.rollback_transaction()
            raise

    def cancel_order(self, order_id: str, reason: str):
        self._store.begin_transaction()
        try:
            order = self._store.get_entity(f"order:{order_id}")
            if not order:
                raise ValueError(f"Order {order_id} not found")
            order["status"] = "cancelled"
            self._store.save_entity(f"order:{order_id}", order)
            self._store.add_outbox_event(
                aggregate_id=order_id,
                aggregate_type="Order",
                event_type="OrderCancelled",
                payload={"order_id": order_id, "reason": reason},
            )
            self._store.commit_transaction()
        except Exception:
            self._store.rollback_transaction()
            raise


# --- Tests ---

def test_outbox_pattern():
    store = OutboxStore()
    publisher = InMemoryPublisher()
    relay = OutboxRelay(store, publisher, poll_interval=0.1, max_retries=3)

    service = OrderService(store)

    # Create order — should save entity AND outbox event atomically
    service.create_order("ORD-1", "USR-1", [{"sku": "A", "qty": 2}], 49.99)

    order = store.get_entity("order:ORD-1")
    assert order is not None
    assert order["status"] == "created"
    assert store.outbox_size == 1

    # Cancel order — another atomic operation
    service.cancel_order("ORD-1", "Customer request")
    assert store.outbox_size == 2
    order = store.get_entity("order:ORD-1")
    assert order["status"] == "cancelled"

    # Run relay to publish
    relay.start()
    time.sleep(0.5)
    relay.stop()

    assert store.outbox_size == 0
    assert len(publisher.published) == 2
    assert publisher.published[0].event_type == "OrderCreated"
    assert publisher.published[1].event_type == "OrderCancelled"
    # Verify ordering
    assert publisher.published[0].sequence < publisher.published[1].sequence

    # Test failure handling — publisher fails on certain event types
    store2 = OutboxStore()
    failing_publisher = InMemoryPublisher(fail_on={"PaymentFailed"})
    relay2 = OutboxRelay(store2, failing_publisher, poll_interval=0.1, max_retries=2)

    store2.begin_transaction()
    store2.add_outbox_event("ORD-2", "Order", "PaymentFailed", {"reason": "declined"})
    store2.commit_transaction()

    # Process multiple times — should retry and eventually dead-letter
    for _ in range(5):
        relay2.process_batch()

    assert len(relay2.dead_letters) == 1
    assert relay2.dead_letters[0].event_type == "PaymentFailed"

    # Test rollback — if domain logic fails, no event is stored
    store3 = OutboxStore()
    service3 = OrderService(store3)
    try:
        service3.cancel_order("NONEXISTENT", "bad")
    except ValueError:
        pass
    assert store3.outbox_size == 0  # no event stored

    # Test cleanup
    store.cleanup_published(older_than=0)
    # All published events should be cleaned

    print("All outbox pattern tests passed.")


if __name__ == "__main__":
    test_outbox_pattern()
```'''
    ),
    (
        "deep_reasoning/bulkhead-fault-isolation",
        r'''Implement the Bulkhead pattern in Python for fault isolation. Use thread pool partitioning and semaphore-based bulkheads to prevent one failing service from consuming all resources and cascading to other services.''',
        r'''<think>
The Bulkhead pattern isolates components so a failure in one doesn't bring down the whole
system. Named after ship bulkheads that prevent flooding from spreading.

Two implementation approaches:
1. Thread pool bulkhead — each service gets its own thread pool with a fixed size.
   If service A's pool is exhausted, service B is unaffected.
2. Semaphore bulkhead — limit concurrent calls to each service via semaphore. Lighter
   weight than thread pools but doesn't isolate blocking calls as well.

Trade-off: thread pool isolation is stronger (a blocking call in service A's pool can't
starve service B's pool) but uses more resources. Semaphore is lightweight but shares
the calling thread — a blocking call still ties up the caller's thread.

I'll implement both and let the user choose. The interface should be the same.

Interface:
- Bulkhead(name, max_concurrent, max_wait, type="thread_pool"|"semaphore")
- bulkhead.execute(fn, *args, **kwargs) -> result
- bulkhead.metrics -> {active, queued, rejected, completed, failed}
- @bulkhead decorator

Failure modes:
- Bulkhead full: reject immediately or queue with timeout
- Function times out: count as failure, don't leak the thread
- Bulkhead is shut down while calls are in flight: graceful drain

I'll also implement a BulkheadRegistry for managing multiple bulkheads and monitoring.
</think>

```python
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future, TimeoutError as FuturesTimeout
from dataclasses import dataclass, field
from typing import Callable, Any, Optional
from enum import Enum
import functools


class BulkheadRejected(Exception):
    """Raised when the bulkhead is full and rejects a call."""
    def __init__(self, name: str, active: int, max_concurrent: int):
        self.bulkhead_name = name
        super().__init__(
            f"Bulkhead '{name}' rejected: {active}/{max_concurrent} slots in use"
        )


class BulkheadType(Enum):
    THREAD_POOL = "thread_pool"
    SEMAPHORE = "semaphore"


@dataclass
class BulkheadMetrics:
    active: int = 0
    queued: int = 0
    completed: int = 0
    rejected: int = 0
    failed: int = 0
    total_duration_ms: float = 0

    @property
    def avg_duration_ms(self) -> float:
        total = self.completed + self.failed
        return self.total_duration_ms / total if total > 0 else 0


class Bulkhead:
    def __init__(
        self,
        name: str,
        max_concurrent: int = 10,
        max_wait: float = 1.0,
        bulkhead_type: BulkheadType = BulkheadType.SEMAPHORE,
        call_timeout: float = 30.0,
    ):
        self.name = name
        self._max_concurrent = max_concurrent
        self._max_wait = max_wait
        self._type = bulkhead_type
        self._call_timeout = call_timeout
        self._metrics = BulkheadMetrics()
        self._lock = threading.Lock()
        self._closed = False

        if bulkhead_type == BulkheadType.THREAD_POOL:
            self._executor = ThreadPoolExecutor(
                max_workers=max_concurrent,
                thread_name_prefix=f"bulkhead-{name}",
            )
            self._semaphore = threading.Semaphore(max_concurrent)
        else:
            self._executor = None
            self._semaphore = threading.Semaphore(max_concurrent)

    def execute(self, fn: Callable, *args, **kwargs) -> Any:
        if self._closed:
            raise BulkheadRejected(self.name, 0, 0)

        # Try to acquire a slot
        acquired = self._semaphore.acquire(timeout=self._max_wait)
        if not acquired:
            with self._lock:
                self._metrics.rejected += 1
            raise BulkheadRejected(
                self.name, self._max_concurrent - self._semaphore._value,
                self._max_concurrent,
            )

        with self._lock:
            self._metrics.active += 1

        start = time.monotonic()
        try:
            if self._type == BulkheadType.THREAD_POOL:
                future = self._executor.submit(fn, *args, **kwargs)
                try:
                    result = future.result(timeout=self._call_timeout)
                except FuturesTimeout:
                    future.cancel()
                    raise TimeoutError(f"Call timed out after {self._call_timeout}s")
            else:
                # Semaphore mode: run in calling thread
                result = fn(*args, **kwargs)

            with self._lock:
                self._metrics.completed += 1
                self._metrics.total_duration_ms += (time.monotonic() - start) * 1000

            return result

        except Exception:
            with self._lock:
                self._metrics.failed += 1
                self._metrics.total_duration_ms += (time.monotonic() - start) * 1000
            raise

        finally:
            with self._lock:
                self._metrics.active -= 1
            self._semaphore.release()

    @property
    def metrics(self) -> BulkheadMetrics:
        with self._lock:
            return BulkheadMetrics(
                active=self._metrics.active,
                queued=self._metrics.queued,
                completed=self._metrics.completed,
                rejected=self._metrics.rejected,
                failed=self._metrics.failed,
                total_duration_ms=self._metrics.total_duration_ms,
            )

    def shutdown(self, wait: bool = True):
        self._closed = True
        if self._executor:
            self._executor.shutdown(wait=wait)


class BulkheadRegistry:
    """Central registry for managing multiple bulkheads."""

    def __init__(self):
        self._bulkheads: dict[str, Bulkhead] = {}
        self._lock = threading.Lock()

    def register(self, bulkhead: Bulkhead):
        with self._lock:
            self._bulkheads[bulkhead.name] = bulkhead

    def get(self, name: str) -> Optional[Bulkhead]:
        return self._bulkheads.get(name)

    def all_metrics(self) -> dict[str, BulkheadMetrics]:
        return {name: bh.metrics for name, bh in self._bulkheads.items()}

    def shutdown_all(self):
        for bh in self._bulkheads.values():
            bh.shutdown()


def bulkhead(name: str, max_concurrent: int = 10, max_wait: float = 1.0,
             bulkhead_type: BulkheadType = BulkheadType.SEMAPHORE):
    """Decorator to apply bulkhead to a function."""
    bh = Bulkhead(name, max_concurrent, max_wait, bulkhead_type)

    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            return bh.execute(fn, *args, **kwargs)
        wrapper.bulkhead = bh
        return wrapper
    return decorator


# --- Usage and tests ---

def test_bulkhead():
    # Test semaphore bulkhead
    sem_bulkhead = Bulkhead(
        "payment-service",
        max_concurrent=2,
        max_wait=0.2,
        bulkhead_type=BulkheadType.SEMAPHORE,
    )

    results = []

    def slow_payment(order_id: str) -> str:
        time.sleep(0.3)
        return f"paid-{order_id}"

    def fast_query(query: str) -> str:
        return f"result-{query}"

    # Fill up the semaphore bulkhead
    threads = []
    for i in range(2):
        t = threading.Thread(target=lambda i=i: results.append(sem_bulkhead.execute(slow_payment, f"ORD-{i}")))
        t.start()
        threads.append(t)

    time.sleep(0.05)  # let threads acquire semaphore

    # Third call should be rejected (max_concurrent=2, both slots busy)
    try:
        sem_bulkhead.execute(fast_query, "test")
        rejected = False
    except BulkheadRejected:
        rejected = True

    for t in threads:
        t.join()

    assert rejected, "Third concurrent call should be rejected"
    assert sem_bulkhead.metrics.rejected >= 1

    # Test thread pool bulkhead
    tp_bulkhead = Bulkhead(
        "inventory-service",
        max_concurrent=3,
        max_wait=0.5,
        bulkhead_type=BulkheadType.THREAD_POOL,
    )

    result = tp_bulkhead.execute(fast_query, "stock-check")
    assert result == "result-stock-check"
    assert tp_bulkhead.metrics.completed == 1

    # Test fault isolation — one bulkhead failing doesn't affect another
    registry = BulkheadRegistry()
    orders_bh = Bulkhead("orders", max_concurrent=2, max_wait=0.1)
    users_bh = Bulkhead("users", max_concurrent=2, max_wait=0.1)
    registry.register(orders_bh)
    registry.register(users_bh)

    def failing_order_service():
        time.sleep(1)
        raise ConnectionError("Order service down")

    # Saturate orders bulkhead
    order_threads = []
    for _ in range(2):
        t = threading.Thread(target=lambda: None if not orders_bh.execute(failing_order_service) else None)
        t.daemon = True
        t.start()
        order_threads.append(t)

    time.sleep(0.05)

    # Users bulkhead should still work fine
    user_result = users_bh.execute(fast_query, "user-lookup")
    assert user_result == "result-user-lookup"

    # Orders bulkhead should reject new requests
    try:
        orders_bh.execute(fast_query, "new-order")
    except BulkheadRejected:
        pass  # Expected — orders is saturated

    for t in order_threads:
        t.join(timeout=2)

    # Test decorator
    @bulkhead("email-service", max_concurrent=5)
    def send_email(to: str, subject: str):
        return f"sent to {to}"

    assert send_email("alice@test.com", "Hello") == "sent to alice@test.com"
    assert send_email.bulkhead.metrics.completed == 1

    # Verify metrics
    all_metrics = registry.all_metrics()
    assert "orders" in all_metrics
    assert "users" in all_metrics
    assert all_metrics["users"].completed == 1

    registry.shutdown_all()
    sem_bulkhead.shutdown()
    tp_bulkhead.shutdown()

    print("All bulkhead tests passed.")


if __name__ == "__main__":
    test_bulkhead()
```'''
    ),
    (
        "deep_reasoning/feature-flag-gradual-rollout",
        r'''Build a feature flag system in Python with boolean and percentage-based rollout, user segmentation, A/B testing support, and runtime toggle without restart.''',
        r'''<think>
Feature flags decouple deployment from release. The key capabilities:
1. Boolean flags — on/off globally
2. Percentage rollout — enable for X% of users (deterministic, same user always gets same result)
3. User segmentation — enable for specific user attributes (beta users, region, plan)
4. A/B testing — assign users to variants with traffic allocation
5. Runtime toggle — change flags without restarting the application

Design decisions:
- Deterministic hashing for percentage rollout: hash(flag_name + user_id) % 100 gives stable
  bucket assignment. Same user always gets the same flag value for the same flag.
- Rule evaluation order: explicit overrides > segment rules > percentage rollout > default
- Storage: in-memory with an optional external loader (file, API, database)

Trade-off: I could make this eventually consistent (cache with TTL refresh) or strongly
consistent (check on every evaluation). For feature flags, eventual consistency is fine —
a few seconds of stale data is acceptable and it reduces load.

Interface:
- FeatureFlagService(loader)
- service.is_enabled(flag_name, context={user_id, ...}) -> bool
- service.get_variant(flag_name, context) -> variant_name
- service.set_flag(flag_name, config) — runtime update
- FlagConfig: rules, percentage, variants, default

Failure mode: flag not found — default to disabled (fail closed). Loader fails to refresh
— use last known good config. Context missing required field — fall through to default.
</think>

```python
import hashlib
import time
import threading
import json
from dataclasses import dataclass, field
from typing import Any, Optional, Callable
from enum import Enum


@dataclass
class SegmentRule:
    """Match users by attribute."""
    attribute: str
    operator: str  # eq, neq, in, not_in, gt, lt, contains
    value: Any

    def matches(self, context: dict) -> bool:
        actual = context.get(self.attribute)
        if actual is None:
            return False
        try:
            if self.operator == "eq":
                return actual == self.value
            elif self.operator == "neq":
                return actual != self.value
            elif self.operator == "in":
                return actual in self.value
            elif self.operator == "not_in":
                return actual not in self.value
            elif self.operator == "gt":
                return actual > self.value
            elif self.operator == "lt":
                return actual < self.value
            elif self.operator == "contains":
                return self.value in actual
        except TypeError:
            return False
        return False


@dataclass
class Variant:
    name: str
    weight: int  # percentage weight (all variants should sum to 100)
    config: dict = field(default_factory=dict)


@dataclass
class FlagConfig:
    name: str
    enabled: bool = False
    description: str = ""
    # Percentage rollout (0-100, only if enabled=True)
    rollout_percentage: int = 100
    # Segment rules — if any match, flag is enabled regardless of percentage
    include_rules: list[SegmentRule] = field(default_factory=list)
    exclude_rules: list[SegmentRule] = field(default_factory=list)
    # User overrides — explicit per-user enable/disable
    user_overrides: dict[str, bool] = field(default_factory=dict)
    # A/B test variants
    variants: list[Variant] = field(default_factory=list)
    # Metadata
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


def _stable_hash(key: str) -> int:
    """Deterministic hash that returns 0-99."""
    h = hashlib.md5(key.encode()).hexdigest()
    return int(h[:8], 16) % 100


class FeatureFlagService:
    def __init__(self, loader: Optional[Callable[[], dict[str, FlagConfig]]] = None,
                 refresh_interval: float = 30.0):
        self._flags: dict[str, FlagConfig] = {}
        self._lock = threading.RLock()
        self._loader = loader
        self._refresh_interval = refresh_interval
        self._listeners: list[Callable[[str, FlagConfig], None]] = []
        self._evaluation_log: list[dict] = []
        self._running = True

        if loader:
            self._refresh()
            self._refresh_thread = threading.Thread(target=self._refresh_loop, daemon=True)
            self._refresh_thread.start()

    def set_flag(self, config: FlagConfig):
        """Set or update a flag at runtime."""
        with self._lock:
            config.updated_at = time.time()
            self._flags[config.name] = config
            for listener in self._listeners:
                try:
                    listener(config.name, config)
                except Exception:
                    pass

    def is_enabled(self, flag_name: str, context: Optional[dict] = None) -> bool:
        context = context or {}
        with self._lock:
            config = self._flags.get(flag_name)

        if config is None:
            return False  # Unknown flag = disabled (fail closed)

        if not config.enabled:
            return False

        user_id = context.get("user_id", "")

        # Check explicit user overrides first
        if user_id and user_id in config.user_overrides:
            return config.user_overrides[user_id]

        # Check exclude rules — if any match, flag is disabled for this user
        for rule in config.exclude_rules:
            if rule.matches(context):
                return False

        # Check include rules — if any match, flag is enabled regardless of percentage
        for rule in config.include_rules:
            if rule.matches(context):
                return True

        # Percentage rollout
        if config.rollout_percentage >= 100:
            return True
        if config.rollout_percentage <= 0:
            return False

        if not user_id:
            return False  # Can't do percentage without user_id

        bucket = _stable_hash(f"{flag_name}:{user_id}")
        return bucket < config.rollout_percentage

    def get_variant(self, flag_name: str, context: Optional[dict] = None) -> Optional[str]:
        """Get the variant assigned to a user for A/B testing."""
        context = context or {}

        if not self.is_enabled(flag_name, context):
            return None

        with self._lock:
            config = self._flags.get(flag_name)

        if not config or not config.variants:
            return None

        user_id = context.get("user_id", "anonymous")
        bucket = _stable_hash(f"{flag_name}:variant:{user_id}")

        cumulative = 0
        for variant in config.variants:
            cumulative += variant.weight
            if bucket < cumulative:
                return variant.name

        return config.variants[-1].name  # fallback to last

    def get_variant_config(self, flag_name: str, context: Optional[dict] = None) -> dict:
        """Get the config for the assigned variant."""
        variant_name = self.get_variant(flag_name, context)
        if not variant_name:
            return {}

        with self._lock:
            config = self._flags.get(flag_name)
            if not config:
                return {}
            for v in config.variants:
                if v.name == variant_name:
                    return v.config
        return {}

    def on_change(self, listener: Callable[[str, FlagConfig], None]):
        self._listeners.append(listener)

    def _refresh(self):
        if not self._loader:
            return
        try:
            flags = self._loader()
            with self._lock:
                self._flags.update(flags)
        except Exception:
            pass  # Keep last known good

    def _refresh_loop(self):
        while self._running:
            time.sleep(self._refresh_interval)
            self._refresh()

    def all_flags(self) -> dict[str, dict]:
        with self._lock:
            return {
                name: {
                    "enabled": cfg.enabled,
                    "rollout_percentage": cfg.rollout_percentage,
                    "variants": [v.name for v in cfg.variants],
                    "description": cfg.description,
                }
                for name, cfg in self._flags.items()
            }

    def shutdown(self):
        self._running = False


# --- Usage and tests ---

def test_feature_flags():
    service = FeatureFlagService()

    # Basic boolean flag
    service.set_flag(FlagConfig(name="dark_mode", enabled=True))
    assert service.is_enabled("dark_mode")
    assert not service.is_enabled("nonexistent_flag")

    # Disabled flag
    service.set_flag(FlagConfig(name="experimental", enabled=False))
    assert not service.is_enabled("experimental")

    # Percentage rollout (deterministic)
    service.set_flag(FlagConfig(name="new_checkout", enabled=True, rollout_percentage=50))

    # Same user always gets same result
    ctx = {"user_id": "user-123"}
    result1 = service.is_enabled("new_checkout", ctx)
    result2 = service.is_enabled("new_checkout", ctx)
    assert result1 == result2  # deterministic

    # Different users may get different results
    results = set()
    for i in range(100):
        r = service.is_enabled("new_checkout", {"user_id": f"user-{i}"})
        results.add(r)
    assert True in results and False in results  # ~50% split

    # User segmentation — include beta users
    service.set_flag(FlagConfig(
        name="beta_feature",
        enabled=True,
        rollout_percentage=0,  # disabled by percentage
        include_rules=[SegmentRule("plan", "eq", "beta")],
    ))
    assert service.is_enabled("beta_feature", {"user_id": "u1", "plan": "beta"})
    assert not service.is_enabled("beta_feature", {"user_id": "u2", "plan": "free"})

    # Exclude rules — block certain regions
    service.set_flag(FlagConfig(
        name="payments_v2",
        enabled=True,
        rollout_percentage=100,
        exclude_rules=[SegmentRule("country", "in", ["CN", "RU"])],
    ))
    assert service.is_enabled("payments_v2", {"user_id": "u1", "country": "US"})
    assert not service.is_enabled("payments_v2", {"user_id": "u2", "country": "CN"})

    # User overrides
    service.set_flag(FlagConfig(
        name="admin_panel",
        enabled=True,
        rollout_percentage=0,
        user_overrides={"admin-1": True, "banned-1": False},
    ))
    assert service.is_enabled("admin_panel", {"user_id": "admin-1"})
    assert not service.is_enabled("admin_panel", {"user_id": "banned-1"})
    assert not service.is_enabled("admin_panel", {"user_id": "regular-1"})

    # A/B testing with variants
    service.set_flag(FlagConfig(
        name="checkout_experiment",
        enabled=True,
        rollout_percentage=100,
        variants=[
            Variant("control", 50, {"button_color": "blue"}),
            Variant("treatment_a", 30, {"button_color": "green"}),
            Variant("treatment_b", 20, {"button_color": "red"}),
        ],
    ))

    # Verify deterministic variant assignment
    ctx = {"user_id": "test-user-42"}
    v1 = service.get_variant("checkout_experiment", ctx)
    v2 = service.get_variant("checkout_experiment", ctx)
    assert v1 == v2  # same user, same variant
    assert v1 in ("control", "treatment_a", "treatment_b")

    # Get variant config
    config = service.get_variant_config("checkout_experiment", ctx)
    assert "button_color" in config

    # Verify distribution across many users
    variant_counts = {"control": 0, "treatment_a": 0, "treatment_b": 0}
    for i in range(1000):
        v = service.get_variant("checkout_experiment", {"user_id": f"user-{i}"})
        variant_counts[v] += 1
    # Should be roughly 50/30/20 (allow wide margin for hash distribution)
    assert variant_counts["control"] > 300
    assert variant_counts["treatment_a"] > 150
    assert variant_counts["treatment_b"] > 50

    # Runtime toggle without restart
    changes = []
    service.on_change(lambda name, cfg: changes.append(name))
    service.set_flag(FlagConfig(name="dark_mode", enabled=False))
    assert not service.is_enabled("dark_mode")
    assert "dark_mode" in changes

    # All flags view
    flags = service.all_flags()
    assert "dark_mode" in flags
    assert "checkout_experiment" in flags

    service.shutdown()
    print("All feature flag tests passed.")


if __name__ == "__main__":
    test_feature_flags()
```'''
    ),
    (
        "deep_reasoning/request-response-correlation",
        r'''Implement a request-response correlation system for async messaging in Python. The system sends requests via a message queue and correlates responses by correlation ID, with timeout and multi-response support.''',
        r'''<think>
In async messaging, request-response is harder than in synchronous systems because the
sender and receiver are decoupled. The sender needs to:
1. Attach a correlation ID to the request
2. Wait for a response with the same correlation ID
3. Handle timeout if no response comes
4. Optionally handle multiple responses (scatter-gather)

Key design decisions:
- Correlation ID: UUID generated by the sender, included in both request and response
- Reply-to address: the sender tells the responder where to send the reply
- Pending requests registry: maps correlation_id -> Future/Event

Trade-off: I could use a single reply queue shared by all senders, or per-sender reply
queues. Single queue is simpler but requires a dispatcher. Per-sender is isolated but
creates more queues. I'll use a single reply queue with a dispatcher thread.

Interface:
- CorrelatedMessenger(transport)
- messenger.request(destination, payload, timeout) -> response
- messenger.scatter(destinations, payload, timeout) -> list[responses]
- messenger.on_request(destination, handler)

Failure modes:
- Timeout: remove pending entry, raise TimeoutError
- Duplicate response (retry on responder side): ignore duplicates
- Reply queue goes down: pending requests all time out
- Responder sends to wrong correlation ID: ignored (no matching pending entry)
</think>

```python
import uuid
import time
import threading
import queue
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from concurrent.futures import Future


@dataclass
class Message:
    payload: Any
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    reply_to: str = ""
    destination: str = ""
    timestamp: float = field(default_factory=time.time)
    headers: dict = field(default_factory=dict)


class MessageTransport:
    """In-memory message transport simulating a message broker."""

    def __init__(self):
        self._queues: dict[str, queue.Queue] = {}
        self._lock = threading.Lock()

    def get_queue(self, name: str) -> queue.Queue:
        with self._lock:
            if name not in self._queues:
                self._queues[name] = queue.Queue()
            return self._queues[name]

    def send(self, destination: str, message: Message):
        message.destination = destination
        q = self.get_queue(destination)
        q.put(message)

    def receive(self, queue_name: str, timeout: float = 1.0) -> Optional[Message]:
        q = self.get_queue(queue_name)
        try:
            return q.get(timeout=timeout)
        except queue.Empty:
            return None


@dataclass
class PendingRequest:
    correlation_id: str
    future: Future
    created_at: float = field(default_factory=time.monotonic)
    timeout: float = 30.0
    expected_responses: int = 1
    received_responses: list = field(default_factory=list)


class CorrelatedMessenger:
    def __init__(self, transport: MessageTransport, reply_queue: str = ""):
        self._transport = transport
        self._reply_queue = reply_queue or f"reply-{uuid.uuid4().hex[:8]}"
        self._pending: dict[str, PendingRequest] = {}
        self._lock = threading.Lock()
        self._running = True
        self._handlers: dict[str, Callable[[Message], Any]] = {}

        # Start reply listener
        self._reply_thread = threading.Thread(target=self._listen_replies, daemon=True)
        self._reply_thread.start()

        # Start timeout checker
        self._timeout_thread = threading.Thread(target=self._check_timeouts, daemon=True)
        self._timeout_thread.start()

    def request(self, destination: str, payload: Any, timeout: float = 5.0,
                headers: Optional[dict] = None) -> Any:
        """Send a request and wait for a correlated response."""
        correlation_id = str(uuid.uuid4())
        future: Future = Future()

        with self._lock:
            self._pending[correlation_id] = PendingRequest(
                correlation_id=correlation_id,
                future=future,
                timeout=timeout,
            )

        msg = Message(
            payload=payload,
            correlation_id=correlation_id,
            reply_to=self._reply_queue,
            headers=headers or {},
        )
        self._transport.send(destination, msg)

        try:
            return future.result(timeout=timeout)
        except Exception:
            with self._lock:
                self._pending.pop(correlation_id, None)
            raise

    def scatter(self, destinations: list[str], payload: Any,
                timeout: float = 5.0) -> list[Any]:
        """Send to multiple destinations and collect all responses."""
        correlation_id = str(uuid.uuid4())
        future: Future = Future()

        with self._lock:
            self._pending[correlation_id] = PendingRequest(
                correlation_id=correlation_id,
                future=future,
                timeout=timeout,
                expected_responses=len(destinations),
            )

        msg = Message(
            payload=payload,
            correlation_id=correlation_id,
            reply_to=self._reply_queue,
        )

        for dest in destinations:
            self._transport.send(dest, Message(
                payload=payload,
                correlation_id=correlation_id,
                reply_to=self._reply_queue,
                destination=dest,
            ))

        try:
            return future.result(timeout=timeout)
        except Exception:
            with self._lock:
                pending = self._pending.pop(correlation_id, None)
            if pending and pending.received_responses:
                return pending.received_responses  # partial results
            raise

    def on_request(self, queue_name: str, handler: Callable[[Any], Any]):
        """Register a request handler for a queue. Runs in a background thread."""
        def listener():
            while self._running:
                msg = self._transport.receive(queue_name, timeout=0.5)
                if msg is None:
                    continue
                try:
                    result = handler(msg.payload)
                    if msg.reply_to:
                        reply = Message(
                            payload=result,
                            correlation_id=msg.correlation_id,
                            destination=msg.reply_to,
                        )
                        self._transport.send(msg.reply_to, reply)
                except Exception as e:
                    if msg.reply_to:
                        error_reply = Message(
                            payload={"error": str(e)},
                            correlation_id=msg.correlation_id,
                            headers={"error": "true"},
                        )
                        self._transport.send(msg.reply_to, error_reply)

        t = threading.Thread(target=listener, daemon=True)
        t.start()

    def _listen_replies(self):
        while self._running:
            msg = self._transport.receive(self._reply_queue, timeout=0.5)
            if msg is None:
                continue

            with self._lock:
                pending = self._pending.get(msg.correlation_id)
                if not pending:
                    continue  # Unknown correlation ID, ignore

                if pending.future.done():
                    continue  # Already resolved (duplicate)

                pending.received_responses.append(msg.payload)

                if len(pending.received_responses) >= pending.expected_responses:
                    if pending.expected_responses == 1:
                        pending.future.set_result(msg.payload)
                    else:
                        pending.future.set_result(list(pending.received_responses))
                    del self._pending[msg.correlation_id]

    def _check_timeouts(self):
        while self._running:
            time.sleep(0.2)
            now = time.monotonic()
            with self._lock:
                expired = [
                    cid for cid, p in self._pending.items()
                    if now - p.created_at > p.timeout and not p.future.done()
                ]
                for cid in expired:
                    pending = self._pending.pop(cid)
                    pending.future.set_exception(
                        TimeoutError(f"No response for correlation {cid} "
                                   f"within {pending.timeout}s")
                    )

    def shutdown(self):
        self._running = False


# --- Usage and tests ---

def test_correlation():
    transport = MessageTransport()

    # Service A (requester)
    client = CorrelatedMessenger(transport, reply_queue="client-replies")

    # Service B (responder)
    responder = CorrelatedMessenger(transport)
    responder.on_request("math-service", lambda payload: {
        "result": payload["a"] + payload["b"]
    })

    time.sleep(0.2)  # let listeners start

    # Simple request-response
    result = client.request("math-service", {"a": 10, "b": 20}, timeout=2.0)
    assert result["result"] == 30

    # Multiple sequential requests
    for i in range(5):
        result = client.request("math-service", {"a": i, "b": i}, timeout=2.0)
        assert result["result"] == i * 2

    # Timeout test — no responder on this queue
    try:
        client.request("nonexistent-service", {"data": "hello"}, timeout=0.3)
        assert False, "Should have timed out"
    except TimeoutError:
        pass  # Expected

    # Scatter-gather
    responder2 = CorrelatedMessenger(transport)
    responder2.on_request("price-svc-1", lambda p: {"price": 10.0, "source": "svc1"})
    responder3 = CorrelatedMessenger(transport)
    responder3.on_request("price-svc-2", lambda p: {"price": 12.0, "source": "svc2"})

    time.sleep(0.2)

    results = client.scatter(
        ["price-svc-1", "price-svc-2"],
        {"item": "widget"},
        timeout=2.0,
    )
    assert len(results) == 2
    prices = {r["source"]: r["price"] for r in results}
    assert prices["svc1"] == 10.0
    assert prices["svc2"] == 12.0

    # Test error response from handler
    responder4 = CorrelatedMessenger(transport)
    responder4.on_request("error-svc", lambda p: (_ for _ in ()).throw(ValueError("bad input")))
    time.sleep(0.2)

    result = client.request("error-svc", {"bad": "data"}, timeout=2.0)
    assert "error" in result  # error response

    client.shutdown()
    responder.shutdown()
    responder2.shutdown()
    responder3.shutdown()
    responder4.shutdown()

    print("All request-response correlation tests passed.")


if __name__ == "__main__":
    test_correlation()
```'''
    ),
    (
        "deep_reasoning/sidecar-cross-cutting-concerns",
        r'''Implement the Sidecar pattern for cross-cutting concerns in Python. The sidecar transparently adds logging, metrics collection, authentication, and request tracing to any service without modifying service code.''',
        r'''<think>
The Sidecar pattern attaches cross-cutting concerns to a service as a co-deployed companion.
The service code stays clean — all observability, auth, and tracing logic lives in the sidecar.

Key design decisions:
1. The sidecar intercepts all inbound/outbound calls via a middleware pipeline
2. Each concern is a pluggable middleware: logging, metrics, auth, tracing
3. The service doesn't import or reference the sidecar — it's wired in externally

Trade-off: I could use decorators on each service method (invasive but explicit) or a
proxy wrapper (transparent but harder to debug). The sidecar should be a proxy — the
service registers its handlers, and the sidecar wraps them automatically.

Interface:
- Sidecar(service)
- sidecar.add_middleware(middleware)
- Each middleware: before_request(ctx), after_response(ctx, response), on_error(ctx, error)
- Middleware pipeline executes in order for before, reverse for after (like WSGI)

Failure modes:
- Middleware raises: don't break the service call, log and continue
- Auth middleware rejects: short-circuit, return 401 before reaching service
- Metrics collection is slow: use async/non-blocking publish
- Trace context missing: create new trace, log warning

I'll make the middleware protocol simple and composable. Each middleware can modify the
request context, short-circuit the pipeline, or observe without changing anything.
</think>

```python
import time
import uuid
import threading
import functools
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from abc import ABC, abstractmethod
from collections import defaultdict


@dataclass
class RequestContext:
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    trace_id: str = ""
    span_id: str = ""
    method: str = ""
    path: str = ""
    headers: dict = field(default_factory=dict)
    body: Any = None
    user: Optional[dict] = None
    start_time: float = field(default_factory=time.monotonic)
    metadata: dict = field(default_factory=dict)


@dataclass
class ResponseContext:
    status: int = 200
    body: Any = None
    headers: dict = field(default_factory=dict)
    duration_ms: float = 0
    error: Optional[Exception] = None


class Middleware(ABC):
    @abstractmethod
    def before_request(self, ctx: RequestContext) -> Optional[ResponseContext]:
        """Process before the service. Return ResponseContext to short-circuit."""
        pass

    @abstractmethod
    def after_response(self, ctx: RequestContext, response: ResponseContext):
        """Process after the service response."""
        pass

    def on_error(self, ctx: RequestContext, error: Exception):
        """Called when an error occurs."""
        pass


# --- Logging Middleware ---

class LoggingMiddleware(Middleware):
    def __init__(self):
        self.logs: list[dict] = []

    def before_request(self, ctx: RequestContext) -> Optional[ResponseContext]:
        self.logs.append({
            "type": "request",
            "request_id": ctx.request_id,
            "trace_id": ctx.trace_id,
            "method": ctx.method,
            "path": ctx.path,
            "time": time.time(),
        })
        return None

    def after_response(self, ctx: RequestContext, response: ResponseContext):
        self.logs.append({
            "type": "response",
            "request_id": ctx.request_id,
            "status": response.status,
            "duration_ms": response.duration_ms,
        })

    def on_error(self, ctx: RequestContext, error: Exception):
        self.logs.append({
            "type": "error",
            "request_id": ctx.request_id,
            "error": str(error),
        })


# --- Metrics Middleware ---

class MetricsMiddleware(Middleware):
    def __init__(self):
        self._lock = threading.Lock()
        self.counters: dict[str, int] = defaultdict(int)
        self.latencies: dict[str, list[float]] = defaultdict(list)

    def before_request(self, ctx: RequestContext) -> Optional[ResponseContext]:
        with self._lock:
            self.counters[f"{ctx.method}:{ctx.path}:total"] += 1
        return None

    def after_response(self, ctx: RequestContext, response: ResponseContext):
        key = f"{ctx.method}:{ctx.path}"
        with self._lock:
            self.counters[f"{key}:{response.status}"] += 1
            self.latencies[key].append(response.duration_ms)

    def on_error(self, ctx: RequestContext, error: Exception):
        with self._lock:
            self.counters[f"{ctx.method}:{ctx.path}:error"] += 1

    def get_summary(self) -> dict:
        with self._lock:
            summary = {}
            for key, lats in self.latencies.items():
                if lats:
                    sorted_lats = sorted(lats)
                    summary[key] = {
                        "count": len(lats),
                        "avg_ms": sum(lats) / len(lats),
                        "p50_ms": sorted_lats[len(lats) // 2],
                        "p99_ms": sorted_lats[int(len(lats) * 0.99)],
                        "max_ms": sorted_lats[-1],
                    }
            return summary


# --- Auth Middleware ---

class AuthMiddleware(Middleware):
    def __init__(self, token_validator: Callable[[str], Optional[dict]],
                 public_paths: Optional[set] = None):
        self._validator = token_validator
        self._public_paths = public_paths or set()

    def before_request(self, ctx: RequestContext) -> Optional[ResponseContext]:
        if ctx.path in self._public_paths:
            return None

        token = ctx.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return ResponseContext(status=401, body={"error": "Missing auth token"})

        user = self._validator(token)
        if user is None:
            return ResponseContext(status=401, body={"error": "Invalid token"})

        ctx.user = user
        return None

    def after_response(self, ctx: RequestContext, response: ResponseContext):
        pass


# --- Tracing Middleware ---

class TracingMiddleware(Middleware):
    def __init__(self):
        self.spans: list[dict] = []

    def before_request(self, ctx: RequestContext) -> Optional[ResponseContext]:
        if not ctx.trace_id:
            ctx.trace_id = str(uuid.uuid4())[:16]
        ctx.span_id = str(uuid.uuid4())[:8]
        return None

    def after_response(self, ctx: RequestContext, response: ResponseContext):
        self.spans.append({
            "trace_id": ctx.trace_id,
            "span_id": ctx.span_id,
            "method": ctx.method,
            "path": ctx.path,
            "status": response.status,
            "duration_ms": response.duration_ms,
            "error": str(response.error) if response.error else None,
        })

    def on_error(self, ctx: RequestContext, error: Exception):
        self.spans.append({
            "trace_id": ctx.trace_id,
            "span_id": ctx.span_id,
            "error": str(error),
        })


# --- Sidecar Proxy ---

class Sidecar:
    """Transparent proxy that wraps a service with middleware."""

    def __init__(self):
        self._middleware: list[Middleware] = []
        self._handlers: dict[str, Callable] = {}  # "METHOD:path" -> handler

    def add_middleware(self, middleware: Middleware):
        self._middleware.append(middleware)

    def register_handler(self, method: str, path: str, handler: Callable):
        key = f"{method}:{path}"
        self._handlers[key] = handler

    def handle(self, method: str, path: str, body: Any = None,
               headers: Optional[dict] = None) -> ResponseContext:
        ctx = RequestContext(
            method=method,
            path=path,
            body=body,
            headers=headers or {},
        )

        # Before-request pipeline
        for mw in self._middleware:
            try:
                short_circuit = mw.before_request(ctx)
                if short_circuit is not None:
                    # After-response in reverse for short-circuits
                    for prev_mw in reversed(self._middleware[:self._middleware.index(mw)]):
                        try:
                            prev_mw.after_response(ctx, short_circuit)
                        except Exception:
                            pass
                    return short_circuit
            except Exception:
                pass  # Middleware error shouldn't break the pipeline

        # Find and execute handler
        handler_key = f"{method}:{path}"
        handler = self._handlers.get(handler_key)

        if handler is None:
            response = ResponseContext(status=404, body={"error": "Not found"})
        else:
            try:
                result = handler(ctx)
                response = ResponseContext(
                    status=200,
                    body=result,
                    duration_ms=(time.monotonic() - ctx.start_time) * 1000,
                )
            except Exception as e:
                response = ResponseContext(
                    status=500,
                    body={"error": str(e)},
                    error=e,
                    duration_ms=(time.monotonic() - ctx.start_time) * 1000,
                )
                for mw in self._middleware:
                    try:
                        mw.on_error(ctx, e)
                    except Exception:
                        pass

        response.duration_ms = (time.monotonic() - ctx.start_time) * 1000

        # After-response pipeline (reverse order)
        for mw in reversed(self._middleware):
            try:
                mw.after_response(ctx, response)
            except Exception:
                pass

        return response


# --- Usage and tests ---

def test_sidecar():
    # Create sidecar with all middleware
    sidecar = Sidecar()

    logger = LoggingMiddleware()
    metrics = MetricsMiddleware()
    tracer = TracingMiddleware()

    # Simple token validator
    valid_tokens = {"token-123": {"user_id": "alice", "role": "admin"}}
    auth = AuthMiddleware(
        token_validator=lambda t: valid_tokens.get(t),
        public_paths={"/health"},
    )

    sidecar.add_middleware(tracer)   # outermost
    sidecar.add_middleware(logger)
    sidecar.add_middleware(auth)
    sidecar.add_middleware(metrics)  # innermost

    # Register service handlers (service code is clean — no middleware concerns)
    sidecar.register_handler("GET", "/users", lambda ctx: [
        {"id": 1, "name": "Alice"},
        {"id": 2, "name": "Bob"},
    ])
    sidecar.register_handler("GET", "/health", lambda ctx: {"status": "ok"})
    sidecar.register_handler("POST", "/orders", lambda ctx: {"order_id": 42})
    sidecar.register_handler("GET", "/error", lambda ctx: (_ for _ in ()).throw(
        RuntimeError("Something broke")))

    # Test: authenticated request
    resp = sidecar.handle("GET", "/users", headers={"Authorization": "Bearer token-123"})
    assert resp.status == 200
    assert len(resp.body) == 2

    # Test: unauthenticated request (short-circuited by auth)
    resp = sidecar.handle("GET", "/users")
    assert resp.status == 401

    # Test: public path (no auth needed)
    resp = sidecar.handle("GET", "/health")
    assert resp.status == 200

    # Test: error handling
    resp = sidecar.handle("GET", "/error", headers={"Authorization": "Bearer token-123"})
    assert resp.status == 500

    # Test: 404
    resp = sidecar.handle("GET", "/nonexistent", headers={"Authorization": "Bearer token-123"})
    assert resp.status == 404

    # Verify logging captured all requests
    request_logs = [l for l in logger.logs if l["type"] == "request"]
    assert len(request_logs) >= 4

    # Verify metrics
    summary = metrics.get_summary()
    assert "GET:/users" in summary or "GET:/health" in summary

    # Verify tracing
    assert len(tracer.spans) >= 3
    for span in tracer.spans:
        assert span["trace_id"]  # auto-generated
        assert span["span_id"]

    # Verify trace propagation
    resp = sidecar.handle("GET", "/health")
    last_span = tracer.spans[-1]
    assert last_span["trace_id"] != ""

    print("All sidecar pattern tests passed.")


if __name__ == "__main__":
    test_sidecar()
```'''
    ),
    (
        "deep_reasoning/leader-election-distributed-locking",
        r'''Implement leader election using distributed locking in Python. Support lock acquisition with TTL, heartbeat-based lease renewal, leader change callbacks, and graceful handoff.''',
        r'''<think>
Leader election ensures only one node in a cluster performs a specific role at a time.
Using distributed locks: a node acquires a lock with a TTL, becomes leader, and renews
the lease periodically via heartbeats.

Key design decisions:
1. Lock with TTL — if the leader crashes, the lock expires and another node can acquire
2. Heartbeat renewal — the leader extends the TTL before it expires
3. Fencing token — monotonically increasing number to detect stale leaders. If a node
   thinks it's leader but its fencing token is old, it should step down.
4. Graceful handoff — the current leader can voluntarily release, allowing faster transition

Trade-off: short TTL means faster failover but more heartbeat traffic. Long TTL means
less traffic but slower failover. I'll make it configurable with sensible defaults.

Interface:
- LeaderElection(node_id, lock_store, ttl, heartbeat_interval)
- election.start()
- election.stop()
- election.is_leader -> bool
- election.on_elected(callback)
- election.on_demoted(callback)
- election.resign() — voluntary step-down

Failure modes:
- Leader process freezes (GC pause): TTL expires, another node takes over. When the frozen
  leader wakes up, it checks its fencing token and steps down.
- Network partition: the leader can't renew. A new leader emerges on the other side.
  Now we have split-brain. Fencing tokens help — operations check the token.
- Clock skew: dangerous with TTL-based locking. Safety margin in TTL helps.

I'll abstract the lock store so it can be backed by Redis, etcd, or PostgreSQL.
</think>

```python
import threading
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class LockInfo:
    holder: str
    fencing_token: int
    acquired_at: float
    expires_at: float


class LockStore(ABC):
    """Abstract distributed lock store."""

    @abstractmethod
    def try_acquire(self, key: str, holder: str, ttl: float) -> Optional[LockInfo]:
        """Try to acquire the lock. Returns LockInfo if successful, None otherwise."""
        pass

    @abstractmethod
    def renew(self, key: str, holder: str, ttl: float) -> bool:
        """Renew the lock if still held by this holder."""
        pass

    @abstractmethod
    def release(self, key: str, holder: str) -> bool:
        """Release the lock if held by this holder."""
        pass

    @abstractmethod
    def get_info(self, key: str) -> Optional[LockInfo]:
        """Get current lock information."""
        pass


class InMemoryLockStore(LockStore):
    """Thread-safe in-memory lock store for testing."""

    def __init__(self):
        self._lock = threading.Lock()
        self._locks: dict[str, LockInfo] = {}
        self._fencing_counter = 0

    def try_acquire(self, key: str, holder: str, ttl: float) -> Optional[LockInfo]:
        with self._lock:
            now = time.monotonic()
            existing = self._locks.get(key)

            if existing and existing.expires_at > now and existing.holder != holder:
                return None  # Held by someone else

            self._fencing_counter += 1
            info = LockInfo(
                holder=holder,
                fencing_token=self._fencing_counter,
                acquired_at=now,
                expires_at=now + ttl,
            )
            self._locks[key] = info
            return info

    def renew(self, key: str, holder: str, ttl: float) -> bool:
        with self._lock:
            existing = self._locks.get(key)
            if not existing or existing.holder != holder:
                return False
            now = time.monotonic()
            if existing.expires_at < now:
                return False  # Already expired
            existing.expires_at = now + ttl
            return True

    def release(self, key: str, holder: str) -> bool:
        with self._lock:
            existing = self._locks.get(key)
            if existing and existing.holder == holder:
                del self._locks[key]
                return True
            return False

    def get_info(self, key: str) -> Optional[LockInfo]:
        with self._lock:
            info = self._locks.get(key)
            if info and info.expires_at < time.monotonic():
                del self._locks[key]
                return None
            return info


class LeaderElection:
    def __init__(
        self,
        node_id: str,
        lock_store: LockStore,
        lock_key: str = "leader",
        ttl: float = 10.0,
        heartbeat_interval: float = 3.0,
        acquisition_interval: float = 2.0,
    ):
        self._node_id = node_id
        self._store = lock_store
        self._lock_key = lock_key
        self._ttl = ttl
        self._heartbeat_interval = heartbeat_interval
        self._acquisition_interval = acquisition_interval

        self._is_leader = False
        self._fencing_token: Optional[int] = None
        self._lock = threading.Lock()
        self._running = False

        self._on_elected: list[Callable[[int], None]] = []  # callback(fencing_token)
        self._on_demoted: list[Callable[[], None]] = []
        self._thread: Optional[threading.Thread] = None

    @property
    def is_leader(self) -> bool:
        with self._lock:
            return self._is_leader

    @property
    def fencing_token(self) -> Optional[int]:
        with self._lock:
            return self._fencing_token

    def on_elected(self, callback: Callable[[int], None]):
        self._on_elected.append(callback)

    def on_demoted(self, callback: Callable[[], None]):
        self._on_demoted.append(callback)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._election_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._is_leader:
            self.resign()
        if self._thread:
            self._thread.join(timeout=5)

    def resign(self):
        """Voluntarily give up leadership."""
        with self._lock:
            was_leader = self._is_leader
            self._is_leader = False
            self._fencing_token = None

        if was_leader:
            self._store.release(self._lock_key, self._node_id)
            for cb in self._on_demoted:
                try:
                    cb()
                except Exception:
                    pass

    def _election_loop(self):
        while self._running:
            with self._lock:
                currently_leader = self._is_leader

            if currently_leader:
                # Renew the lease
                renewed = self._store.renew(self._lock_key, self._node_id, self._ttl)
                if not renewed:
                    # Lost leadership (lock expired or was taken)
                    self._demote()
                time.sleep(self._heartbeat_interval)
            else:
                # Try to acquire leadership
                info = self._store.try_acquire(self._lock_key, self._node_id, self._ttl)
                if info:
                    self._promote(info.fencing_token)
                time.sleep(self._acquisition_interval)

    def _promote(self, fencing_token: int):
        with self._lock:
            self._is_leader = True
            self._fencing_token = fencing_token

        for cb in self._on_elected:
            try:
                cb(fencing_token)
            except Exception:
                pass

    def _demote(self):
        with self._lock:
            self._is_leader = False
            self._fencing_token = None

        for cb in self._on_demoted:
            try:
                cb()
            except Exception:
                pass


# --- Fencing Token Guard ---

class FencedOperation:
    """Ensures operations are only performed by the current leader."""

    def __init__(self, lock_store: LockStore, lock_key: str):
        self._store = lock_store
        self._lock_key = lock_key

    def execute(self, fencing_token: int, fn: Callable, *args, **kwargs):
        """Execute only if the fencing token is still valid (current leader)."""
        info = self._store.get_info(self._lock_key)
        if info is None or info.fencing_token != fencing_token:
            raise PermissionError(
                f"Stale fencing token {fencing_token}. "
                f"Current: {info.fencing_token if info else 'none'}"
            )
        return fn(*args, **kwargs)


# --- Usage and tests ---

def test_leader_election():
    store = InMemoryLockStore()
    events = {"node1": [], "node2": []}

    # Node 1
    node1 = LeaderElection("node-1", store, ttl=1.0, heartbeat_interval=0.3,
                           acquisition_interval=0.3)
    node1.on_elected(lambda t: events["node1"].append(("elected", t)))
    node1.on_demoted(lambda: events["node1"].append(("demoted",)))

    # Node 2
    node2 = LeaderElection("node-2", store, ttl=1.0, heartbeat_interval=0.3,
                           acquisition_interval=0.3)
    node2.on_elected(lambda t: events["node2"].append(("elected", t)))
    node2.on_demoted(lambda: events["node2"].append(("demoted",)))

    # Start both
    node1.start()
    time.sleep(0.5)
    node2.start()
    time.sleep(1.0)

    # Exactly one should be leader
    assert node1.is_leader != node2.is_leader, "Exactly one node should be leader"

    leader = node1 if node1.is_leader else node2
    follower = node2 if node1.is_leader else node1
    leader_name = "node1" if node1.is_leader else "node2"

    # Verify fencing token
    assert leader.fencing_token is not None
    assert leader.fencing_token > 0

    # Test fenced operation
    fenced = FencedOperation(store, "leader")
    result = fenced.execute(leader.fencing_token, lambda: "did-work")
    assert result == "did-work"

    # Stale fencing token should fail
    try:
        fenced.execute(0, lambda: "should-not-run")
        assert False, "Should have raised"
    except PermissionError:
        pass

    # Test resignation and failover
    old_token = leader.fencing_token
    leader.resign()
    time.sleep(1.5)  # wait for follower to acquire

    assert follower.is_leader, "Follower should become leader after resignation"
    assert follower.fencing_token > old_token, "New fencing token should be higher"

    # Verify stale leader can't do fenced operations
    try:
        fenced.execute(old_token, lambda: "stale-work")
        assert False, "Old token should be rejected"
    except PermissionError:
        pass

    node1.stop()
    node2.stop()

    # Verify callbacks fired
    assert any(e[0] == "elected" for e in events["node1"]) or \
           any(e[0] == "elected" for e in events["node2"])

    print("All leader election tests passed.")


if __name__ == "__main__":
    test_leader_election()
```'''
    ),
    (
        "deep_reasoning/backpressure-adaptive-rate",
        r'''Implement a back-pressure mechanism for a producer-consumer system in Python with adaptive rate limiting, queue depth monitoring, load shedding, and producer throttling.''',
        r'''<think>
Back-pressure prevents a fast producer from overwhelming a slow consumer. Without it,
unbounded queues grow until OOM, or messages get dropped unpredictably.

Key design decisions:
1. Bounded buffer with feedback — the queue signals the producer when it's getting full
2. Adaptive rate — automatically slow the producer based on consumer throughput
3. Load shedding — when the queue is critically full, start dropping low-priority messages
4. Producer throttling — the producer's send rate is dynamically adjusted

Trade-off: blocking vs non-blocking backpressure. Blocking (producer waits) is simplest
and guarantees no data loss but can cause producer-side cascading slowdowns. Non-blocking
with feedback (producer gets rate limit signals) is more flexible. I'll implement both.

Interface:
- BackpressureQueue(capacity, low_watermark, high_watermark)
- queue.put(item, priority) -> accepted/rejected
- queue.get() -> item
- queue.pressure_level -> 0.0 to 1.0
- AdaptiveProducer(queue, initial_rate)
- AdaptiveConsumer(queue, handler)

The algorithm:
- Below low_watermark: producer runs at max rate
- Between low and high: linearly reduce producer rate
- Above high watermark: shed low-priority items, minimal producer rate
- Queue empty: consumer backs off (no busy-waiting)

I'll use a token bucket for rate control, adjusted based on queue depth feedback.
</think>

```python
import threading
import time
import heapq
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from enum import IntEnum
from collections import deque


class Priority(IntEnum):
    LOW = 0
    NORMAL = 1
    HIGH = 2
    CRITICAL = 3


@dataclass(order=True)
class QueueItem:
    priority: int  # negative for max-heap behavior
    sequence: int  # tiebreaker for FIFO within same priority
    data: Any = field(compare=False)
    timestamp: float = field(default_factory=time.monotonic, compare=False)


class BackpressureSignal:
    """Signal from queue to producer about current pressure."""
    def __init__(self, level: float, recommended_rate: float, shedding: bool):
        self.level = level  # 0.0 (empty) to 1.0 (full)
        self.recommended_rate = recommended_rate  # items per second
        self.shedding = shedding  # True if queue is shedding low-priority items


class BackpressureQueue:
    def __init__(
        self,
        capacity: int = 1000,
        low_watermark: float = 0.5,
        high_watermark: float = 0.8,
        shed_threshold: float = 0.9,
        max_rate: float = 100.0,
        min_rate: float = 1.0,
    ):
        self._capacity = capacity
        self._low_wm = low_watermark
        self._high_wm = high_watermark
        self._shed_threshold = shed_threshold
        self._max_rate = max_rate
        self._min_rate = min_rate

        self._heap: list[QueueItem] = []
        self._sequence = 0
        self._lock = threading.Condition()
        self._closed = False

        # Metrics
        self._total_enqueued = 0
        self._total_dequeued = 0
        self._total_shed = 0
        self._total_rejected = 0

    @property
    def depth(self) -> int:
        return len(self._heap)

    @property
    def pressure_level(self) -> float:
        return len(self._heap) / self._capacity if self._capacity > 0 else 0

    @property
    def signal(self) -> BackpressureSignal:
        level = self.pressure_level
        shedding = level >= self._shed_threshold

        if level <= self._low_wm:
            rate = self._max_rate
        elif level <= self._high_wm:
            # Linear interpolation between max and min rate
            ratio = (level - self._low_wm) / (self._high_wm - self._low_wm)
            rate = self._max_rate - ratio * (self._max_rate - self._min_rate)
        else:
            rate = self._min_rate

        return BackpressureSignal(level, rate, shedding)

    def put(self, data: Any, priority: Priority = Priority.NORMAL,
            block: bool = True, timeout: float = 5.0) -> bool:
        with self._lock:
            if self._closed:
                return False

            level = self.pressure_level

            # Load shedding — reject low priority when above shed threshold
            if level >= self._shed_threshold and priority <= Priority.LOW:
                self._total_shed += 1
                return False

            # Queue full — reject or block
            if len(self._heap) >= self._capacity:
                if not block:
                    self._total_rejected += 1
                    return False
                deadline = time.monotonic() + timeout
                while len(self._heap) >= self._capacity:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        self._total_rejected += 1
                        return False
                    self._lock.wait(timeout=remaining)
                    if self._closed:
                        return False

            self._sequence += 1
            item = QueueItem(
                priority=-priority,  # negative for max-heap (highest priority first)
                sequence=self._sequence,
                data=data,
            )
            heapq.heappush(self._heap, item)
            self._total_enqueued += 1
            self._lock.notify()
            return True

    def get(self, timeout: float = 1.0) -> Optional[Any]:
        with self._lock:
            while not self._heap:
                if self._closed:
                    return None
                self._lock.wait(timeout=timeout)
                if not self._heap:
                    return None

            item = heapq.heappop(self._heap)
            self._total_dequeued += 1
            self._lock.notify()  # wake up blocked producers
            return item.data

    def close(self):
        with self._lock:
            self._closed = True
            self._lock.notify_all()

    @property
    def stats(self) -> dict:
        return {
            "depth": self.depth,
            "capacity": self._capacity,
            "pressure": round(self.pressure_level, 3),
            "enqueued": self._total_enqueued,
            "dequeued": self._total_dequeued,
            "shed": self._total_shed,
            "rejected": self._total_rejected,
        }


class AdaptiveProducer:
    """Producer that adjusts its rate based on queue backpressure signals."""

    def __init__(self, queue: BackpressureQueue, produce_fn: Callable[[], Any],
                 initial_rate: float = 50.0):
        self._queue = queue
        self._produce_fn = produce_fn
        self._rate = initial_rate
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._produced = 0
        self._rate_history: list[tuple[float, float]] = []

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._produce_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _produce_loop(self):
        while self._running:
            # Check backpressure signal
            signal = self._queue.signal
            self._rate = signal.recommended_rate
            self._rate_history.append((time.monotonic(), self._rate))

            # Produce at the current rate
            data = self._produce_fn()
            priority = Priority.NORMAL
            accepted = self._queue.put(data, priority, block=False)
            if accepted:
                self._produced += 1

            # Sleep to match rate
            if self._rate > 0:
                time.sleep(1.0 / self._rate)

    @property
    def stats(self) -> dict:
        return {
            "produced": self._produced,
            "current_rate": round(self._rate, 2),
        }


class AdaptiveConsumer:
    """Consumer that processes items from the queue."""

    def __init__(self, queue: BackpressureQueue, handler: Callable[[Any], None],
                 num_workers: int = 1):
        self._queue = queue
        self._handler = handler
        self._num_workers = num_workers
        self._running = False
        self._threads: list[threading.Thread] = []
        self._consumed = 0
        self._errors = 0
        self._lock = threading.Lock()

    def start(self):
        self._running = True
        for i in range(self._num_workers):
            t = threading.Thread(target=self._consume_loop, daemon=True, name=f"consumer-{i}")
            t.start()
            self._threads.append(t)

    def stop(self):
        self._running = False
        for t in self._threads:
            t.join(timeout=5)

    def _consume_loop(self):
        while self._running:
            item = self._queue.get(timeout=0.5)
            if item is None:
                continue
            try:
                self._handler(item)
                with self._lock:
                    self._consumed += 1
            except Exception:
                with self._lock:
                    self._errors += 1

    @property
    def stats(self) -> dict:
        with self._lock:
            return {"consumed": self._consumed, "errors": self._errors}


# --- Usage and tests ---

def test_backpressure():
    q = BackpressureQueue(
        capacity=20,
        low_watermark=0.3,
        high_watermark=0.7,
        shed_threshold=0.9,
        max_rate=100.0,
        min_rate=5.0,
    )

    # Test basic put/get with priority
    q.put("low-1", Priority.LOW)
    q.put("critical-1", Priority.CRITICAL)
    q.put("normal-1", Priority.NORMAL)

    # Higher priority comes out first
    assert q.get() == "critical-1"
    assert q.get() == "normal-1"
    assert q.get() == "low-1"

    # Test pressure-based rate recommendation
    assert q.signal.level == 0.0
    assert q.signal.recommended_rate == 100.0  # max rate when empty

    # Fill to 50% — should start reducing rate
    for i in range(10):
        q.put(f"item-{i}")
    signal = q.signal
    assert 0.4 < signal.level < 0.6
    assert signal.recommended_rate < 100.0  # reduced

    # Fill more — should reduce further
    for i in range(6):
        q.put(f"more-{i}")
    signal = q.signal
    assert signal.level >= 0.7

    # Test load shedding — fill to 90%+
    for i in range(4):
        q.put(f"fill-{i}", Priority.HIGH)

    # Now at capacity, low priority should be shed
    assert not q.put("shed-me", Priority.LOW, block=False)
    assert q.stats["shed"] >= 1

    # High priority still accepted (if capacity available)
    # Drain some first
    for _ in range(5):
        q.get()

    accepted = q.put("high-priority", Priority.HIGH, block=False)
    assert accepted

    # Drain all
    while q.depth > 0:
        q.get()

    # Test adaptive producer-consumer
    q2 = BackpressureQueue(capacity=50, low_watermark=0.3, high_watermark=0.7,
                           max_rate=200.0, min_rate=10.0)
    consumed_items = []
    counter = {"n": 0}

    def produce():
        counter["n"] += 1
        return f"item-{counter['n']}"

    def consume(item):
        time.sleep(0.02)  # simulate slow consumer
        consumed_items.append(item)

    producer = AdaptiveProducer(q2, produce, initial_rate=100.0)
    consumer = AdaptiveConsumer(q2, consume, num_workers=2)

    consumer.start()
    producer.start()
    time.sleep(2)
    producer.stop()
    time.sleep(1)
    consumer.stop()
    q2.close()

    # Producer should have adapted its rate
    assert producer.stats["produced"] > 0
    assert consumer.stats["consumed"] > 0

    # The rate should have decreased at some point due to backpressure
    if producer._rate_history:
        rates = [r for _, r in producer._rate_history]
        assert min(rates) < 200.0, "Rate should have decreased due to backpressure"

    print(f"Produced: {producer.stats['produced']}, Consumed: {consumer.stats['consumed']}")
    print(f"Queue stats: {q2.stats}")
    print("All backpressure tests passed.")


if __name__ == "__main__":
    test_backpressure()
```'''
    ),
]
