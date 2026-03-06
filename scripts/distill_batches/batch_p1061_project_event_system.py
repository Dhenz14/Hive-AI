PAIRS = [
    ("projects/event-system", r'''<think>
An event bus needs to handle subscriptions, async event delivery,
and dead letter handling for failed events. I will implement a
publish-subscribe pattern with support for both sync and async handlers.
</think>
Build an event system with an event bus, typed events, and both sync and async handler support.''', r'''import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Set, Type

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Base class for all events."""
    event_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    timestamp: float = field(default_factory=time.time)
    source: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def event_type(self) -> str:
        return self.__class__.__name__


@dataclass
class Subscription:
    """Represents a handler subscription."""
    handler: Callable
    event_type: str
    is_async: bool
    priority: int = 0
    filter_fn: Optional[Callable] = None
    subscription_id: str = field(default_factory=lambda: uuid.uuid4().hex)


class EventBus:
    """Publish-subscribe event bus with priority ordering and filtering."""

    def __init__(self):
        self._subscriptions: Dict[str, List[Subscription]] = {}
        self._global_handlers: List[Subscription] = []
        self._middleware: List[Callable] = []
        self._dead_letter_handlers: List[Callable] = []
        self._event_count = 0

    def subscribe(
        self,
        event_type: str,
        handler: Callable,
        priority: int = 0,
        filter_fn: Optional[Callable] = None,
    ) -> str:
        """Subscribe a handler to an event type. Returns subscription ID."""
        is_async = asyncio.iscoroutinefunction(handler)
        sub = Subscription(
            handler=handler,
            event_type=event_type,
            is_async=is_async,
            priority=priority,
            filter_fn=filter_fn,
        )

        if event_type not in self._subscriptions:
            self._subscriptions[event_type] = []
        self._subscriptions[event_type].append(sub)
        self._subscriptions[event_type].sort(key=lambda s: s.priority)

        return sub.subscription_id

    def unsubscribe(self, subscription_id: str) -> bool:
        """Remove a subscription by ID."""
        for event_type, subs in self._subscriptions.items():
            for i, sub in enumerate(subs):
                if sub.subscription_id == subscription_id:
                    subs.pop(i)
                    return True
        return False

    def subscribe_all(self, handler: Callable, priority: int = 0) -> str:
        """Subscribe to all events."""
        is_async = asyncio.iscoroutinefunction(handler)
        sub = Subscription(handler=handler, event_type="*", is_async=is_async, priority=priority)
        self._global_handlers.append(sub)
        return sub.subscription_id

    def add_middleware(self, middleware: Callable) -> None:
        """Add middleware that processes events before handlers."""
        self._middleware.append(middleware)

    def publish(self, event: Event) -> List[Any]:
        """Publish an event synchronously."""
        self._event_count += 1

        # Apply middleware
        for mw in self._middleware:
            event = mw(event)
            if event is None:
                return []  # Middleware filtered the event

        results = []
        handlers = self._get_handlers(event.event_type)

        for sub in handlers:
            if sub.filter_fn and not sub.filter_fn(event):
                continue
            try:
                if sub.is_async:
                    logger.warning(f"Skipping async handler in sync publish")
                    continue
                result = sub.handler(event)
                results.append(result)
            except Exception as e:
                logger.error(f"Handler error for {event.event_type}: {e}")
                self._handle_dead_letter(event, sub, e)

        return results

    async def publish_async(self, event: Event) -> List[Any]:
        """Publish an event asynchronously."""
        self._event_count += 1

        for mw in self._middleware:
            event = mw(event)
            if event is None:
                return []

        results = []
        handlers = self._get_handlers(event.event_type)

        for sub in handlers:
            if sub.filter_fn and not sub.filter_fn(event):
                continue
            try:
                if sub.is_async:
                    result = await sub.handler(event)
                else:
                    result = sub.handler(event)
                results.append(result)
            except Exception as e:
                logger.error(f"Handler error for {event.event_type}: {e}")
                self._handle_dead_letter(event, sub, e)

        return results

    def _get_handlers(self, event_type: str) -> List[Subscription]:
        """Get all handlers for an event type, including global handlers."""
        specific = self._subscriptions.get(event_type, [])
        all_handlers = list(specific) + list(self._global_handlers)
        all_handlers.sort(key=lambda s: s.priority)
        return all_handlers

    def on_dead_letter(self, handler: Callable) -> None:
        """Register a dead letter handler for failed events."""
        self._dead_letter_handlers.append(handler)

    def _handle_dead_letter(self, event: Event, sub: Subscription, error: Exception) -> None:
        for handler in self._dead_letter_handlers:
            try:
                handler(event, sub.handler, error)
            except Exception:
                pass

    @property
    def stats(self) -> dict:
        total_subs = sum(len(s) for s in self._subscriptions.values())
        return {
            "events_published": self._event_count,
            "subscriptions": total_subs,
            "global_handlers": len(self._global_handlers),
            "event_types": list(self._subscriptions.keys()),
        }
'''),
    ("projects/event-system", r'''Implement async event handlers with concurrent execution, timeout support, and error isolation.''', r'''import asyncio
import logging
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class AsyncEventDispatcher:
    """Dispatches events to async handlers with concurrency control."""

    def __init__(
        self,
        max_concurrency: int = 10,
        default_timeout: float = 30.0,
        error_handler: Optional[Callable] = None,
    ):
        self._semaphore = asyncio.Semaphore(max_concurrency)
        self._default_timeout = default_timeout
        self._error_handler = error_handler
        self._in_flight = 0
        self._total_dispatched = 0
        self._total_errors = 0

    async def dispatch(
        self,
        handlers: List[Callable],
        event: Any,
        concurrent: bool = True,
        timeout: Optional[float] = None,
    ) -> List[Any]:
        """Dispatch an event to multiple handlers."""
        effective_timeout = timeout or self._default_timeout

        if concurrent:
            return await self._dispatch_concurrent(handlers, event, effective_timeout)
        else:
            return await self._dispatch_sequential(handlers, event, effective_timeout)

    async def _dispatch_concurrent(
        self,
        handlers: List[Callable],
        event: Any,
        timeout: float,
    ) -> List[Any]:
        """Execute handlers concurrently with semaphore limiting."""
        tasks = [
            self._execute_handler(handler, event, timeout)
            for handler in handlers
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        final_results = []
        for result in results:
            if isinstance(result, Exception):
                self._total_errors += 1
                if self._error_handler:
                    self._error_handler(result)
                logger.error(f"Handler error: {result}")
            else:
                final_results.append(result)

        return final_results

    async def _dispatch_sequential(
        self,
        handlers: List[Callable],
        event: Any,
        timeout: float,
    ) -> List[Any]:
        """Execute handlers sequentially, stopping on first error."""
        results = []
        for handler in handlers:
            try:
                result = await self._execute_handler(handler, event, timeout)
                results.append(result)
            except Exception as e:
                self._total_errors += 1
                if self._error_handler:
                    self._error_handler(e)
                break
        return results

    async def _execute_handler(
        self,
        handler: Callable,
        event: Any,
        timeout: float,
    ) -> Any:
        """Execute a single handler with semaphore and timeout."""
        async with self._semaphore:
            self._in_flight += 1
            self._total_dispatched += 1
            try:
                if asyncio.iscoroutinefunction(handler):
                    return await asyncio.wait_for(
                        handler(event), timeout=timeout
                    )
                else:
                    return handler(event)
            finally:
                self._in_flight -= 1

    @property
    def stats(self) -> dict:
        return {
            "in_flight": self._in_flight,
            "total_dispatched": self._total_dispatched,
            "total_errors": self._total_errors,
        }


class RetryableHandler:
    """Wraps a handler with automatic retry on failure."""

    def __init__(
        self,
        handler: Callable,
        max_retries: int = 3,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
    ):
        self._handler = handler
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay

    async def __call__(self, event: Any) -> Any:
        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                if asyncio.iscoroutinefunction(self._handler):
                    return await self._handler(event)
                else:
                    return self._handler(event)
            except Exception as e:
                last_error = e
                if attempt < self._max_retries:
                    delay = min(
                        self._base_delay * (2 ** attempt),
                        self._max_delay,
                    )
                    logger.warning(
                        f"Handler retry {attempt + 1}/{self._max_retries} "
                        f"in {delay:.1f}s: {e}"
                    )
                    await asyncio.sleep(delay)

        raise last_error


class EventAggregator:
    """Aggregates events over a time window before dispatching."""

    def __init__(
        self,
        handler: Callable,
        window_seconds: float = 5.0,
        max_batch_size: int = 100,
    ):
        self._handler = handler
        self._window = window_seconds
        self._max_batch = max_batch_size
        self._buffer: List[Any] = []
        self._timer: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def add(self, event: Any) -> None:
        """Add an event to the aggregation buffer."""
        async with self._lock:
            self._buffer.append(event)

            if len(self._buffer) >= self._max_batch:
                await self._flush()
            elif self._timer is None:
                self._timer = asyncio.create_task(self._start_timer())

    async def _start_timer(self) -> None:
        await asyncio.sleep(self._window)
        async with self._lock:
            await self._flush()

    async def _flush(self) -> None:
        if not self._buffer:
            return
        batch = list(self._buffer)
        self._buffer.clear()
        if self._timer:
            self._timer.cancel()
            self._timer = None

        try:
            if asyncio.iscoroutinefunction(self._handler):
                await self._handler(batch)
            else:
                self._handler(batch)
        except Exception as e:
            logger.error(f"Aggregated handler error: {e}")
'''),
    ("projects/event-system", r'''Implement event replay and persistence with a log-based event store.''', r'''import json
import os
import time
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional


class EventStore:
    """Persistent event store using append-only log files."""

    def __init__(self, store_dir: str = "events"):
        self._dir = Path(store_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._sequence = self._get_last_sequence()

    def _get_log_path(self) -> Path:
        """Get current log file path (one per day)."""
        date_str = time.strftime("%Y%m%d")
        return self._dir / f"events_{date_str}.jsonl"

    def _get_last_sequence(self) -> int:
        """Find the last sequence number from existing logs."""
        max_seq = 0
        for log_file in self._dir.glob("events_*.jsonl"):
            with open(log_file, "r") as f:
                for line in f:
                    try:
                        data = json.loads(line)
                        seq = data.get("_sequence", 0)
                        max_seq = max(max_seq, seq)
                    except json.JSONDecodeError:
                        continue
        return max_seq

    def append(self, event) -> int:
        """Append an event to the store. Returns sequence number."""
        with self._lock:
            self._sequence += 1
            seq = self._sequence

            record = {
                "_sequence": seq,
                "_stored_at": time.time(),
                "event_type": event.event_type,
                "event_id": event.event_id,
                "timestamp": event.timestamp,
                "source": event.source,
                "data": event.metadata,
            }

            # Try to serialize event-specific fields
            if hasattr(event, "__dataclass_fields__"):
                for field_name in event.__dataclass_fields__:
                    if field_name not in ("event_id", "timestamp", "source", "metadata"):
                        record[field_name] = getattr(event, field_name)

            log_path = self._get_log_path()
            with open(log_path, "a") as f:
                f.write(json.dumps(record, default=str) + "\n")

            return seq

    def read_all(self, after_sequence: int = 0) -> Generator[dict, None, None]:
        """Read all events after a given sequence number."""
        log_files = sorted(self._dir.glob("events_*.jsonl"))
        for log_file in log_files:
            with open(log_file, "r") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                        if record.get("_sequence", 0) > after_sequence:
                            yield record
                    except json.JSONDecodeError:
                        continue

    def read_by_type(self, event_type: str, limit: int = 100) -> List[dict]:
        """Read events of a specific type."""
        results = []
        for record in self.read_all():
            if record.get("event_type") == event_type:
                results.append(record)
                if len(results) >= limit:
                    break
        return results

    def read_range(self, start_time: float, end_time: float) -> List[dict]:
        """Read events within a time range."""
        results = []
        for record in self.read_all():
            ts = record.get("timestamp", 0)
            if start_time <= ts <= end_time:
                results.append(record)
        return results

    @property
    def last_sequence(self) -> int:
        return self._sequence

    def get_stats(self) -> dict:
        log_files = list(self._dir.glob("events_*.jsonl"))
        total_size = sum(f.stat().st_size for f in log_files)
        return {
            "last_sequence": self._sequence,
            "log_files": len(log_files),
            "total_size_bytes": total_size,
        }


class EventReplayer:
    """Replays events from the store through an event bus."""

    def __init__(self, store: EventStore, event_bus):
        self._store = store
        self._bus = event_bus
        self._replay_speed = 1.0

    def replay_all(
        self,
        after_sequence: int = 0,
        event_types: Optional[List[str]] = None,
        speed: float = 1.0,
    ) -> dict:
        """Replay events from the store."""
        self._replay_speed = speed
        replayed = 0
        errors = 0
        last_timestamp = None

        for record in self._store.read_all(after_sequence):
            if event_types and record.get("event_type") not in event_types:
                continue

            # Simulate timing if speed > 0
            if speed > 0 and last_timestamp is not None:
                delay = (record["timestamp"] - last_timestamp) / speed
                if delay > 0:
                    time.sleep(min(delay, 5.0))

            last_timestamp = record.get("timestamp", 0)

            try:
                # Create a synthetic event from the record
                from . import Event
                event = Event(
                    event_id=record.get("event_id", ""),
                    timestamp=record.get("timestamp", 0),
                    source=record.get("source", "replay"),
                    metadata=record.get("data", {}),
                )
                self._bus.publish(event)
                replayed += 1
            except Exception as e:
                errors += 1

        return {
            "replayed": replayed,
            "errors": errors,
            "from_sequence": after_sequence,
            "to_sequence": self._store.last_sequence,
        }

    def replay_range(self, start_time: float, end_time: float) -> dict:
        """Replay events within a time range."""
        events = self._store.read_range(start_time, end_time)
        replayed = 0
        for record in events:
            try:
                from . import Event
                event = Event(
                    event_id=record.get("event_id", ""),
                    timestamp=record.get("timestamp", 0),
                    source="replay",
                    metadata=record.get("data", {}),
                )
                self._bus.publish(event)
                replayed += 1
            except Exception:
                pass
        return {"replayed": replayed, "total_in_range": len(events)}
'''),
    ("projects/event-system", r'''Build a dead letter handler for the event system with inspection, retry, and purge capabilities.''', r'''import json
import logging
import time
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Deque, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class DeadLetterEntry:
    """A failed event with error information."""
    entry_id: str
    event_type: str
    event_data: dict
    handler_name: str
    error_message: str
    error_type: str
    failed_at: float
    retry_count: int = 0
    max_retries: int = 3
    last_retry_at: Optional[float] = None
    resolved: bool = False

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "event_type": self.event_type,
            "handler": self.handler_name,
            "error": self.error_message,
            "error_type": self.error_type,
            "failed_at": self.failed_at,
            "retry_count": self.retry_count,
            "resolved": self.resolved,
        }


class DeadLetterQueue:
    """Stores and manages failed events for inspection and retry."""

    def __init__(self, max_entries: int = 10000):
        self._entries: Dict[str, DeadLetterEntry] = {}
        self._order: Deque[str] = deque(maxlen=max_entries)
        self._max_entries = max_entries
        self._lock = threading.Lock()
        self._total_received = 0

    def add(self, event: Any, handler: Callable, error: Exception) -> str:
        """Add a failed event to the dead letter queue."""
        import uuid
        entry_id = uuid.uuid4().hex[:16]

        event_data = {}
        if hasattr(event, "event_id"):
            event_data["event_id"] = event.event_id
        if hasattr(event, "metadata"):
            event_data["metadata"] = event.metadata
        if hasattr(event, "timestamp"):
            event_data["timestamp"] = event.timestamp

        entry = DeadLetterEntry(
            entry_id=entry_id,
            event_type=getattr(event, "event_type", type(event).__name__),
            event_data=event_data,
            handler_name=getattr(handler, "__qualname__", str(handler)),
            error_message=str(error),
            error_type=type(error).__name__,
            failed_at=time.time(),
        )

        with self._lock:
            self._entries[entry_id] = entry
            self._order.append(entry_id)
            self._total_received += 1

            # Evict oldest if over capacity
            while len(self._entries) > self._max_entries:
                oldest_id = self._order.popleft()
                self._entries.pop(oldest_id, None)

        logger.warning(
            f"Dead letter: event={entry.event_type} "
            f"handler={entry.handler_name} error={entry.error_message}"
        )
        return entry_id

    def get(self, entry_id: str) -> Optional[dict]:
        """Get a dead letter entry by ID."""
        entry = self._entries.get(entry_id)
        return entry.to_dict() if entry else None

    def list_entries(
        self,
        event_type: Optional[str] = None,
        resolved: Optional[bool] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[dict]:
        """List dead letter entries with filtering."""
        with self._lock:
            entries = list(self._entries.values())

        if event_type:
            entries = [e for e in entries if e.event_type == event_type]
        if resolved is not None:
            entries = [e for e in entries if e.resolved == resolved]

        entries.sort(key=lambda e: e.failed_at, reverse=True)
        page = entries[offset:offset + limit]
        return [e.to_dict() for e in page]

    def retry(self, entry_id: str, event_bus) -> bool:
        """Retry a dead letter entry."""
        with self._lock:
            entry = self._entries.get(entry_id)
            if not entry or entry.resolved:
                return False

            if entry.retry_count >= entry.max_retries:
                logger.error(f"Dead letter {entry_id} exceeded max retries")
                return False

            entry.retry_count += 1
            entry.last_retry_at = time.time()

        # Reconstruct and republish the event
        try:
            from . import Event
            event = Event(
                event_id=entry.event_data.get("event_id", ""),
                timestamp=entry.event_data.get("timestamp", time.time()),
                source="dead_letter_retry",
                metadata=entry.event_data.get("metadata", {}),
            )
            event_bus.publish(event)
            entry.resolved = True
            logger.info(f"Dead letter {entry_id} retried successfully")
            return True
        except Exception as e:
            logger.error(f"Dead letter retry failed for {entry_id}: {e}")
            return False

    def retry_all(self, event_bus, event_type: Optional[str] = None) -> dict:
        """Retry all unresolved dead letter entries."""
        retried = 0
        failed = 0
        entries = [
            e for e in self._entries.values()
            if not e.resolved and e.retry_count < e.max_retries
        ]
        if event_type:
            entries = [e for e in entries if e.event_type == event_type]

        for entry in entries:
            if self.retry(entry.entry_id, event_bus):
                retried += 1
            else:
                failed += 1

        return {"retried": retried, "failed": failed}

    def resolve(self, entry_id: str) -> bool:
        """Manually mark an entry as resolved."""
        entry = self._entries.get(entry_id)
        if entry:
            entry.resolved = True
            return True
        return False

    def purge(self, older_than_seconds: Optional[float] = None, resolved_only: bool = False) -> int:
        """Remove entries from the queue."""
        now = time.time()
        to_remove = []

        with self._lock:
            for eid, entry in self._entries.items():
                should_remove = False
                if resolved_only and entry.resolved:
                    should_remove = True
                elif older_than_seconds and (now - entry.failed_at) > older_than_seconds:
                    should_remove = True
                elif not older_than_seconds and not resolved_only:
                    should_remove = True

                if should_remove:
                    to_remove.append(eid)

            for eid in to_remove:
                self._entries.pop(eid, None)

        return len(to_remove)

    def get_stats(self) -> dict:
        with self._lock:
            unresolved = sum(1 for e in self._entries.values() if not e.resolved)
            by_type = {}
            for e in self._entries.values():
                by_type[e.event_type] = by_type.get(e.event_type, 0) + 1

            return {
                "total_entries": len(self._entries),
                "unresolved": unresolved,
                "total_received": self._total_received,
                "by_event_type": by_type,
            }
'''),
    ("projects/event-system", r'''<think>
Event persistence is important but I need a way to subscribe to
persistent events and automatically replay missed events when
a subscriber reconnects. This is the durable subscription pattern.
</think>
Implement durable subscriptions that track consumer position and support automatic catch-up on reconnect.''', r'''import json
import time
import threading
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional


@dataclass
class ConsumerPosition:
    """Tracks a consumer's position in the event stream."""
    consumer_id: str
    last_sequence: int = 0
    last_ack_at: float = 0.0
    total_processed: int = 0
    created_at: float = field(default_factory=time.time)


class DurableSubscriptionManager:
    """Manages durable subscriptions with position tracking and catch-up."""

    def __init__(self, event_store, event_bus):
        self._store = event_store
        self._bus = event_bus
        self._positions: Dict[str, ConsumerPosition] = {}
        self._handlers: Dict[str, Callable] = {}
        self._lock = threading.Lock()
        self._position_file: Optional[str] = None

    def set_position_file(self, filepath: str) -> None:
        """Set file for persisting consumer positions."""
        self._position_file = filepath
        self._load_positions()

    def subscribe(
        self,
        consumer_id: str,
        event_type: str,
        handler: Callable,
        start_from: str = "latest",
    ) -> None:
        """Create a durable subscription.

        Args:
            consumer_id: Unique identifier for this consumer
            event_type: Event type to subscribe to
            handler: Callback function for events
            start_from: 'latest', 'earliest', or a sequence number
        """
        with self._lock:
            if consumer_id not in self._positions:
                if start_from == "earliest":
                    last_seq = 0
                elif start_from == "latest":
                    last_seq = self._store.last_sequence
                else:
                    last_seq = int(start_from)

                self._positions[consumer_id] = ConsumerPosition(
                    consumer_id=consumer_id,
                    last_sequence=last_seq,
                )

        self._handlers[consumer_id] = handler

        # Subscribe to live events
        def wrapped_handler(event):
            self._process_event(consumer_id, event)

        self._bus.subscribe(event_type, wrapped_handler)

    def catch_up(self, consumer_id: str) -> dict:
        """Replay missed events for a consumer since their last position."""
        position = self._positions.get(consumer_id)
        handler = self._handlers.get(consumer_id)

        if not position or not handler:
            return {"error": "Consumer not found", "processed": 0}

        processed = 0
        errors = 0
        start_seq = position.last_sequence

        for record in self._store.read_all(after_sequence=start_seq):
            try:
                handler(record)
                position.last_sequence = record.get("_sequence", 0)
                position.total_processed += 1
                position.last_ack_at = time.time()
                processed += 1
            except Exception as e:
                errors += 1

        self._save_positions()

        return {
            "consumer_id": consumer_id,
            "processed": processed,
            "errors": errors,
            "from_sequence": start_seq,
            "to_sequence": position.last_sequence,
        }

    def _process_event(self, consumer_id: str, event) -> None:
        """Process a live event for a consumer."""
        handler = self._handlers.get(consumer_id)
        position = self._positions.get(consumer_id)

        if not handler or not position:
            return

        try:
            handler(event)
            if hasattr(event, "_sequence"):
                position.last_sequence = event._sequence
            position.total_processed += 1
            position.last_ack_at = time.time()
        except Exception as e:
            pass  # Dead letter handling happens at the bus level

    def acknowledge(self, consumer_id: str, sequence: int) -> None:
        """Manually acknowledge processing up to a sequence number."""
        position = self._positions.get(consumer_id)
        if position:
            position.last_sequence = max(position.last_sequence, sequence)
            position.last_ack_at = time.time()
            self._save_positions()

    def get_consumer_lag(self, consumer_id: str) -> int:
        """Get the number of unprocessed events for a consumer."""
        position = self._positions.get(consumer_id)
        if not position:
            return 0
        return max(0, self._store.last_sequence - position.last_sequence)

    def get_all_consumer_status(self) -> List[dict]:
        """Get status of all consumers."""
        latest = self._store.last_sequence
        result = []
        for cid, pos in self._positions.items():
            lag = max(0, latest - pos.last_sequence)
            result.append({
                "consumer_id": cid,
                "last_sequence": pos.last_sequence,
                "lag": lag,
                "total_processed": pos.total_processed,
                "last_ack_at": pos.last_ack_at,
            })
        return result

    def reset_consumer(self, consumer_id: str, to_sequence: int = 0) -> None:
        """Reset a consumer's position."""
        with self._lock:
            if consumer_id in self._positions:
                self._positions[consumer_id].last_sequence = to_sequence
                self._save_positions()

    def remove_consumer(self, consumer_id: str) -> bool:
        """Remove a consumer and its position."""
        with self._lock:
            removed = self._positions.pop(consumer_id, None) is not None
            self._handlers.pop(consumer_id, None)
            if removed:
                self._save_positions()
            return removed

    def _save_positions(self) -> None:
        """Persist consumer positions to disk."""
        if not self._position_file:
            return
        data = {}
        for cid, pos in self._positions.items():
            data[cid] = {
                "consumer_id": pos.consumer_id,
                "last_sequence": pos.last_sequence,
                "total_processed": pos.total_processed,
                "last_ack_at": pos.last_ack_at,
                "created_at": pos.created_at,
            }
        with open(self._position_file, "w") as f:
            json.dump(data, f, indent=2)

    def _load_positions(self) -> None:
        """Load consumer positions from disk."""
        if not self._position_file:
            return
        try:
            with open(self._position_file, "r") as f:
                data = json.load(f)
            for cid, pos_data in data.items():
                self._positions[cid] = ConsumerPosition(**pos_data)
        except (FileNotFoundError, json.JSONDecodeError):
            pass
'''),
]
