"""Apache Flink — stream processing, windowing (tumbling/sliding/session), event-time processing, watermarks, exactly-once semantics, state management."""

PAIRS = [
    (
        "data-engineering/flink-stream-processing",
        "Show how to build a production PyFlink streaming application with Kafka sources, transformations, windowed aggregations, and sinks. Include environment configuration with checkpointing for fault tolerance.",
        '''Production PyFlink streaming application with Kafka integration and checkpointing:

```python
"""
PyFlink streaming application: Kafka source, transformations,
windowed aggregations, and fault-tolerant checkpointing.
"""

from pyflink.datastream import StreamExecutionEnvironment, RuntimeExecutionMode
from pyflink.datastream.connectors.kafka import (
    KafkaSource, KafkaOffsetsInitializer,
    KafkaSink, KafkaRecordSerializationSchema,
)
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common import WatermarkStrategy, Types, Configuration
from pyflink.datastream.functions import (
    MapFunction, FlatMapFunction, FilterFunction,
    KeyedProcessFunction, RuntimeContext,
)
from pyflink.datastream.state import ValueStateDescriptor, MapStateDescriptor
from pyflink.common.typeinfo import TypeInformation
import json
from typing import Any, Iterator
from datetime import datetime


def create_streaming_env(
    parallelism: int = 4,
    checkpoint_interval_ms: int = 60_000,
    checkpoint_dir: str = "s3://my-bucket/flink/checkpoints",
) -> StreamExecutionEnvironment:
    """Configure Flink streaming environment with production settings."""
    config = Configuration()
    config.set_string("execution.checkpointing.mode", "EXACTLY_ONCE")
    config.set_string(
        "execution.checkpointing.interval", f"{checkpoint_interval_ms}ms"
    )
    config.set_string("state.checkpoints.dir", checkpoint_dir)
    config.set_string(
        "execution.checkpointing.externalized-checkpoint-retention",
        "RETAIN_ON_CANCELLATION",
    )
    # State backend: RocksDB for large state
    config.set_string("state.backend.type", "rocksdb")
    config.set_string("state.backend.incremental", "true")
    # Restart strategy
    config.set_string("restart-strategy.type", "exponential-delay")
    config.set_string("restart-strategy.exponential-delay.initial-backoff", "1s")
    config.set_string("restart-strategy.exponential-delay.max-backoff", "60s")

    env = StreamExecutionEnvironment.get_execution_environment(config)
    env.set_runtime_mode(RuntimeExecutionMode.STREAMING)
    env.set_parallelism(parallelism)
    return env


def create_kafka_source(
    brokers: str, topic: str, group_id: str,
) -> KafkaSource:
    """Create a Kafka source with exactly-once semantics."""
    return (
        KafkaSource.builder()
        .set_bootstrap_servers(brokers)
        .set_topics(topic)
        .set_group_id(group_id)
        .set_starting_offsets(KafkaOffsetsInitializer.latest())
        .set_value_only_deserializer(SimpleStringSchema())
        .set_property("enable.auto.commit", "false")
        .set_property("isolation.level", "read_committed")
        .build()
    )


def create_kafka_sink(
    brokers: str, topic: str,
) -> KafkaSink:
    """Create a Kafka sink with exactly-once delivery."""
    return (
        KafkaSink.builder()
        .set_bootstrap_servers(brokers)
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic(topic)
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        .set_delivery_guarantee("exactly-once")
        .set_transactional_id_prefix("flink-txn")
        .build()
    )


class ParseEventFunction(MapFunction):
    """Parse raw JSON strings into typed event tuples."""

    def map(self, value: str):
        event = json.loads(value)
        return (
            event.get("user_id", "unknown"),
            event.get("event_type", "unknown"),
            float(event.get("amount", 0.0)),
            int(event.get("timestamp", 0)),
        )


class EnrichEventFunction(MapFunction):
    """Enrich events with derived fields."""

    def map(self, value):
        user_id, event_type, amount, ts = value
        hour = datetime.utcfromtimestamp(ts / 1000).hour
        day_part = (
            "morning" if 6 <= hour < 12
            else "afternoon" if 12 <= hour < 18
            else "evening" if 18 <= hour < 22
            else "night"
        )
        return (user_id, event_type, amount, ts, day_part)


class FilterHighValueFunction(FilterFunction):
    """Filter to high-value transactions only."""

    def __init__(self, threshold: float = 1000.0):
        self.threshold = threshold

    def filter(self, value):
        return value[2] >= self.threshold


class FraudDetectionFunction(KeyedProcessFunction):
    """
    Stateful fraud detection: flags users with >5 transactions
    exceeding threshold within a 5-minute window.
    """

    def open(self, runtime_context: RuntimeContext):
        self.tx_count = runtime_context.get_state(
            ValueStateDescriptor("tx_count", Types.INT())
        )
        self.window_start = runtime_context.get_state(
            ValueStateDescriptor("window_start", Types.LONG())
        )

    def process_element(self, value, ctx):
        current_time = ctx.timestamp()
        window = self.window_start.value()

        # Reset window if expired (5 minutes = 300_000 ms)
        if window is None or current_time - window > 300_000:
            self.tx_count.update(1)
            self.window_start.update(current_time)
        else:
            count = (self.tx_count.value() or 0) + 1
            self.tx_count.update(count)

            if count > 5:
                alert = json.dumps({
                    "alert": "fraud_suspected",
                    "user_id": value[0],
                    "tx_count_in_window": count,
                    "latest_amount": value[2],
                    "timestamp": current_time,
                })
                yield alert

    def on_timer(self, timestamp, ctx):
        # Clean up expired state
        self.tx_count.clear()
        self.window_start.clear()


def build_pipeline():
    """Build the complete Flink streaming pipeline."""
    env = create_streaming_env(
        parallelism=4,
        checkpoint_interval_ms=30_000,
        checkpoint_dir="s3://data-platform/flink/checkpoints/fraud",
    )

    # Source
    source = create_kafka_source(
        brokers="kafka:9092",
        topic="transactions",
        group_id="fraud-detection-v1",
    )

    # Pipeline
    stream = (
        env.from_source(
            source, WatermarkStrategy.no_watermarks(), "Kafka Source"
        )
        .map(ParseEventFunction())
        .filter(FilterHighValueFunction(threshold=500.0))
        .map(EnrichEventFunction())
        .key_by(lambda x: x[0])  # Key by user_id
        .process(FraudDetectionFunction())
    )

    # Sink alerts to Kafka
    sink = create_kafka_sink(
        brokers="kafka:9092",
        topic="fraud-alerts",
    )
    stream.sink_to(sink)

    env.execute("Fraud Detection Pipeline")
```

**Flink checkpointing configuration:**

| Setting | Value | Purpose |
|---|---|---|
| Mode | EXACTLY_ONCE | No duplicate processing |
| Interval | 30-60s | Balance latency vs. overhead |
| Backend | RocksDB | Large state on disk + incremental |
| Retention | RETAIN_ON_CANCELLATION | Manual restart from checkpoint |
| Restart | Exponential delay 1s-60s | Resilient to transient failures |

**Key patterns:**
- Use `EXACTLY_ONCE` checkpointing mode with RocksDB state backend for production
- Kafka source with `read_committed` isolation level for exactly-once consumption
- Kafka sink with transactional producer for exactly-once delivery
- `KeyedProcessFunction` for stateful per-key processing with timer-based cleanup
- Incremental checkpoints reduce checkpoint size for large state
- Exponential delay restart strategy prevents thundering herd on recovery
- Configure checkpoint directory on durable storage (S3/HDFS) for fault tolerance'''
    ),
    (
        "data-engineering/flink-windowing",
        "Demonstrate all Flink windowing strategies: tumbling, sliding, session, and global windows with event-time processing. Show how to handle late data with allowed lateness and side outputs.",
        '''All Flink windowing strategies with event-time semantics and late data handling:

```python
"""
Flink windowing: tumbling, sliding, session, and global windows
with event-time processing, watermarks, and late data handling.
"""

from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.window import (
    TumblingEventTimeWindows, SlidingEventTimeWindows,
    EventTimeSessionWindows, GlobalWindows, CountTrigger,
)
from pyflink.datastream.functions import (
    ProcessWindowFunction, AggregateFunction,
    MapFunction, RuntimeContext,
)
from pyflink.common import (
    WatermarkStrategy, Types, Time, Duration,
)
from pyflink.common.watermark_strategy import (
    TimestampAssigner,
)
from pyflink.datastream.output_tag import OutputTag
import json
from typing import Iterable


# --- Event-time watermark assignment ---

class EventTimestampAssigner(TimestampAssigner):
    """Extract event timestamps from JSON events."""

    def extract_timestamp(self, value, record_timestamp: int) -> int:
        """Return event time in milliseconds."""
        if isinstance(value, tuple):
            return value[3]  # timestamp field at index 3
        return record_timestamp


def create_watermark_strategy(
    max_out_of_orderness_ms: int = 5000,
) -> WatermarkStrategy:
    """
    Create bounded-out-of-orderness watermark strategy.
    Events arriving up to max_out_of_orderness late are still
    processed in their correct window.
    """
    return (
        WatermarkStrategy
        .for_bounded_out_of_orderness(
            Duration.of_millis(max_out_of_orderness_ms)
        )
        .with_timestamp_assigner(EventTimestampAssigner())
    )


# --- Aggregate functions ---

class CountAndSumAggregate(AggregateFunction):
    """Incrementally compute count and sum in a window."""

    def create_accumulator(self):
        return (0, 0.0)  # (count, sum)

    def add(self, value, accumulator):
        return (accumulator[0] + 1, accumulator[1] + value[2])

    def get_result(self, accumulator):
        return accumulator

    def merge(self, a, b):
        return (a[0] + b[0], a[1] + b[1])


class WindowResultFunction(ProcessWindowFunction):
    """Enrich window results with window metadata."""

    def process(
        self, key: str, context: ProcessWindowFunction.Context,
        elements: Iterable,
    ):
        window = context.window()
        for count, total in elements:
            yield json.dumps({
                "user_id": key,
                "window_start": window.start,
                "window_end": window.end,
                "event_count": count,
                "total_amount": round(total, 2),
                "avg_amount": round(total / count, 2) if count > 0 else 0,
            })


# --- Late data side output ---
LATE_DATA_TAG = OutputTag("late-data")


# --- Window demonstrations ---

def tumbling_window_example(keyed_stream):
    """
    Tumbling window: fixed-size, non-overlapping windows.
    Use case: hourly/daily aggregations, periodic reports.

    |---window1---|---window2---|---window3---|
    |  5 minutes  |  5 minutes  |  5 minutes  |
    """
    return (
        keyed_stream
        .window(TumblingEventTimeWindows.of(Time.minutes(5)))
        .allowed_lateness(Time.minutes(1))
        .side_output_late_data(LATE_DATA_TAG)
        .aggregate(
            CountAndSumAggregate(),
            WindowResultFunction(),
        )
    )


def sliding_window_example(keyed_stream):
    """
    Sliding window: fixed-size windows that overlap.
    Window size=10 min, slide=2 min means each event
    appears in 5 windows.

    |------window1------|
      |------window2------|
        |------window3------|
    """
    return (
        keyed_stream
        .window(SlidingEventTimeWindows.of(
            Time.minutes(10),  # window size
            Time.minutes(2),   # slide interval
        ))
        .allowed_lateness(Time.minutes(1))
        .aggregate(
            CountAndSumAggregate(),
            WindowResultFunction(),
        )
    )


def session_window_example(keyed_stream):
    """
    Session window: dynamic windows based on activity gaps.
    Window closes after 30 minutes of inactivity per key.

    |--session1--|  gap  |---session2---|  gap  |--session3--|
    """
    return (
        keyed_stream
        .window(EventTimeSessionWindows.with_gap(Time.minutes(30)))
        .allowed_lateness(Time.minutes(5))
        .side_output_late_data(LATE_DATA_TAG)
        .aggregate(
            CountAndSumAggregate(),
            WindowResultFunction(),
        )
    )


def global_window_with_trigger(keyed_stream):
    """
    Global window with custom trigger: fires every N events.
    Useful for count-based batching regardless of time.
    """
    return (
        keyed_stream
        .window(GlobalWindows.create())
        .trigger(CountTrigger.of(100))
        .aggregate(
            CountAndSumAggregate(),
            WindowResultFunction(),
        )
    )


# --- Complete pipeline with all window types ---

def build_windowed_pipeline():
    """Build pipeline demonstrating all window types."""
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(4)

    # Configure checkpointing
    env.enable_checkpointing(30_000)

    # Create source with watermarks
    # (In production, use KafkaSource)
    raw_stream = env.from_collection(
        [
            ("user-1", "purchase", 99.99, 1704067200000),
            ("user-1", "purchase", 149.50, 1704067260000),
            ("user-2", "purchase", 25.00, 1704067320000),
            ("user-1", "refund", 49.99, 1704067380000),
            ("user-2", "purchase", 199.00, 1704067500000),
        ],
        type_info=Types.TUPLE([
            Types.STRING(), Types.STRING(),
            Types.DOUBLE(), Types.LONG(),
        ]),
    )

    # Assign watermarks
    watermarked = raw_stream.assign_timestamps_and_watermarks(
        create_watermark_strategy(max_out_of_orderness_ms=5000)
    )

    # Key by user_id
    keyed = watermarked.key_by(lambda x: x[0])

    # Apply different window strategies
    tumbling_result = tumbling_window_example(keyed)
    sliding_result = sliding_window_example(keyed)
    session_result = session_window_example(keyed)

    # Handle late data from tumbling windows
    late_data = tumbling_result.get_side_output(LATE_DATA_TAG)
    late_data.print("LATE")

    # Print results
    tumbling_result.print("TUMBLING")
    sliding_result.print("SLIDING")
    session_result.print("SESSION")

    env.execute("Windowing Demo")


# --- Watermark monitoring ---

class WatermarkMonitor(MapFunction):
    """Monitor watermark progression for debugging."""

    def open(self, runtime_context: RuntimeContext):
        self.events_processed = 0
        self.max_event_time = 0
        self.min_event_time = float("inf")

    def map(self, value):
        self.events_processed += 1
        event_time = value[3]
        self.max_event_time = max(self.max_event_time, event_time)
        self.min_event_time = min(self.min_event_time, event_time)

        if self.events_processed % 10000 == 0:
            skew = self.max_event_time - self.min_event_time
            print(
                f"Watermark monitor: processed={self.events_processed}, "
                f"event_time_skew={skew}ms"
            )
        return value
```

**Window type comparison:**

| Window Type | Size | Overlap | Use Case |
|---|---|---|---|
| Tumbling | Fixed | None | Hourly reports, daily aggregates |
| Sliding | Fixed | Overlapping | Moving averages, trend detection |
| Session | Dynamic | None | User sessions, activity tracking |
| Global + Trigger | Infinite | N/A | Count-based batching, custom logic |

**Late data handling:**

| Mechanism | Behavior |
|---|---|
| Watermark | Declares "no events before this time" will arrive |
| Allowed lateness | Keeps window state open past watermark for updates |
| Side output | Routes events arriving after allowed lateness to separate stream |
| Out-of-orderness | Tolerance for events arriving out of timestamp order |

**Key patterns:**
- Use bounded-out-of-orderness watermark strategy with realistic skew tolerance
- `allowed_lateness` keeps window state for late updates without side output
- Side output late data for separate processing (reprocessing queue, dead letter)
- Tumbling windows for non-overlapping periodic aggregation
- Sliding windows for overlapping trend analysis (each event in multiple windows)
- Session windows for per-user activity detection with configurable gap timeout
- Global windows with count triggers for batch-size-based processing'''
    ),
    (
        "data-engineering/flink-event-time-watermarks",
        "Explain event-time processing and watermark strategies in Flink with custom watermark generators, handling out-of-order events, and strategies for dealing with idle sources.",
        '''Event-time processing and custom watermark strategies in Flink:

```python
"""
Flink event-time processing: custom watermark generators,
out-of-order event handling, and idle source management.
"""

from pyflink.datastream import StreamExecutionEnvironment
from pyflink.common import (
    WatermarkStrategy, Types, Duration, Configuration,
)
from pyflink.common.watermark_strategy import (
    WatermarkGenerator, WatermarkGeneratorSupplier,
    WatermarkOutput, TimestampAssigner,
)
from pyflink.datastream.functions import (
    MapFunction, KeyedProcessFunction, RuntimeContext,
)
from pyflink.datastream.state import ValueStateDescriptor
import json
import time
from typing import Optional


# --- Custom watermark generators ---

class BoundedOutOfOrderGenerator(WatermarkGenerator):
    """
    Standard bounded-out-of-orderness watermark generator.
    Watermark = max_event_time - max_out_of_orderness.

    Timeline:
    Events:    |e1(t=100)|e2(t=95)|e3(t=110)|e4(t=105)|
    Max time:  |100      |100     |110      |110      |
    Watermark: |95       |95      |105      |105      | (delay=5)
    """

    def __init__(self, max_out_of_orderness_ms: int = 5000):
        self.max_out_of_orderness = max_out_of_orderness_ms
        self.max_timestamp = -(2**63)  # Long.MIN_VALUE

    def on_event(self, event, event_timestamp: int, output: WatermarkOutput):
        """Update max timestamp on each event."""
        self.max_timestamp = max(self.max_timestamp, event_timestamp)

    def on_periodic_emit(self, output: WatermarkOutput):
        """Emit watermark periodically."""
        output.emit_watermark(
            self.max_timestamp - self.max_out_of_orderness
        )


class PunctuatedWatermarkGenerator(WatermarkGenerator):
    """
    Punctuated watermark generator: emits watermarks based on
    special marker events in the stream rather than periodically.

    Useful when the source embeds watermark signals in the data.
    """

    def __init__(self):
        self.max_timestamp = -(2**63)

    def on_event(self, event, event_timestamp: int, output: WatermarkOutput):
        self.max_timestamp = max(self.max_timestamp, event_timestamp)

        # Check if this is a watermark marker event
        if isinstance(event, dict) and event.get("type") == "watermark":
            output.emit_watermark(event_timestamp)
        elif isinstance(event, tuple) and len(event) > 4:
            if event[4] == "watermark_marker":
                output.emit_watermark(event_timestamp)

    def on_periodic_emit(self, output: WatermarkOutput):
        # No periodic emission for punctuated strategy
        pass


class ProgressiveWatermarkGenerator(WatermarkGenerator):
    """
    Progressive watermark generator: advances watermarks
    based on processing time when event time stalls.

    Prevents indefinite watermark stalls during low-traffic periods.
    """

    def __init__(
        self,
        max_out_of_orderness_ms: int = 5000,
        stall_timeout_ms: int = 30_000,
    ):
        self.max_out_of_orderness = max_out_of_orderness_ms
        self.stall_timeout = stall_timeout_ms
        self.max_timestamp = -(2**63)
        self.last_event_processing_time = 0

    def on_event(self, event, event_timestamp: int, output: WatermarkOutput):
        self.max_timestamp = max(self.max_timestamp, event_timestamp)
        self.last_event_processing_time = int(time.time() * 1000)

    def on_periodic_emit(self, output: WatermarkOutput):
        now = int(time.time() * 1000)
        time_since_last = now - self.last_event_processing_time

        if (self.last_event_processing_time > 0
                and time_since_last > self.stall_timeout):
            # Advance watermark by elapsed processing time
            advanced = self.max_timestamp + (
                time_since_last - self.stall_timeout
            )
            output.emit_watermark(advanced - self.max_out_of_orderness)
        else:
            output.emit_watermark(
                self.max_timestamp - self.max_out_of_orderness
            )


# --- Multi-source timestamp alignment ---

class MultiSourceTimestampAssigner(TimestampAssigner):
    """
    Assigns timestamps from events that may come from
    multiple sources with different clock skews.
    """

    def __init__(self, clock_skew_tolerance_ms: int = 10_000):
        self.clock_skew_tolerance = clock_skew_tolerance_ms
        self.max_seen = 0

    def extract_timestamp(self, value, record_timestamp: int) -> int:
        if isinstance(value, dict):
            event_ts = value.get("event_time", value.get("timestamp", 0))
        elif isinstance(value, tuple) and len(value) > 3:
            event_ts = value[3]
        else:
            event_ts = record_timestamp

        # Sanity check: reject events too far in the future
        now_ms = int(time.time() * 1000)
        if event_ts > now_ms + self.clock_skew_tolerance:
            # Clamp to current time
            return now_ms

        self.max_seen = max(self.max_seen, event_ts)
        return event_ts


# --- Event-time aware processing ---

class EventTimeSessionDetector(KeyedProcessFunction):
    """
    Detect user sessions using event-time timers.
    Sessions expire after 30 minutes of event-time inactivity.
    """

    SESSION_TIMEOUT = 30 * 60 * 1000  # 30 minutes in ms

    def open(self, runtime_context: RuntimeContext):
        self.session_start = runtime_context.get_state(
            ValueStateDescriptor("session_start", Types.LONG())
        )
        self.event_count = runtime_context.get_state(
            ValueStateDescriptor("event_count", Types.INT())
        )
        self.last_activity = runtime_context.get_state(
            ValueStateDescriptor("last_activity", Types.LONG())
        )
        self.timer_ts = runtime_context.get_state(
            ValueStateDescriptor("timer_ts", Types.LONG())
        )

    def process_element(self, value, ctx):
        """Process each event and manage session timers."""
        current_time = ctx.timestamp()
        user_id = value[0]

        # Check if this is a new session
        last = self.last_activity.value()
        if last is None or (current_time - last) > self.SESSION_TIMEOUT:
            # Start new session
            self.session_start.update(current_time)
            self.event_count.update(1)
        else:
            self.event_count.update((self.event_count.value() or 0) + 1)

        self.last_activity.update(current_time)

        # Register/update event-time timer for session expiry
        old_timer = self.timer_ts.value()
        if old_timer is not None:
            ctx.timer_service().delete_event_time_timer(old_timer)

        new_timer = current_time + self.SESSION_TIMEOUT
        ctx.timer_service().register_event_time_timer(new_timer)
        self.timer_ts.update(new_timer)

    def on_timer(self, timestamp, ctx):
        """Timer fires when session expires (no events for 30 min)."""
        session_start = self.session_start.value()
        last = self.last_activity.value()
        count = self.event_count.value()

        if last is not None and (timestamp - last) >= self.SESSION_TIMEOUT:
            # Session ended
            duration_ms = last - session_start if session_start else 0
            yield json.dumps({
                "event": "session_ended",
                "user_id": ctx.get_current_key(),
                "session_start": session_start,
                "session_end": last,
                "duration_ms": duration_ms,
                "event_count": count,
            })

            # Clear state
            self.session_start.clear()
            self.event_count.clear()
            self.last_activity.clear()
            self.timer_ts.clear()


# --- Watermark monitoring and debugging ---

class WatermarkDebugFunction(MapFunction):
    """Debug function that logs watermark progression."""

    def open(self, runtime_context: RuntimeContext):
        self.events_seen = 0
        self.max_event_time = 0
        self.late_events = 0

    def map(self, value):
        self.events_seen += 1
        if isinstance(value, tuple) and len(value) > 3:
            event_time = value[3]
        else:
            event_time = 0

        if event_time < self.max_event_time:
            self.late_events += 1
        else:
            self.max_event_time = event_time

        if self.events_seen % 50000 == 0:
            late_pct = (
                self.late_events / self.events_seen * 100
                if self.events_seen > 0 else 0
            )
            print(
                f"[Watermark Debug] events={self.events_seen}, "
                f"max_event_time={self.max_event_time}, "
                f"late_events={self.late_events} ({late_pct:.1f}%)"
            )
        return value


def build_event_time_pipeline():
    """Build pipeline with event-time processing."""
    env = StreamExecutionEnvironment.get_execution_environment()
    env.set_parallelism(2)
    env.enable_checkpointing(30_000)

    # Set watermark emission interval
    env.get_config().set_auto_watermark_interval(200)  # 200ms

    source = env.from_collection(
        [
            ("user-1", "click", 1.0, 1704067200000),
            ("user-1", "click", 1.0, 1704067260000),
            ("user-1", "purchase", 99.0, 1704067500000),
            ("user-2", "click", 1.0, 1704067100000),  # Out of order
            ("user-1", "click", 1.0, 1704069200000),  # 30+ min gap
        ],
        type_info=Types.TUPLE([
            Types.STRING(), Types.STRING(),
            Types.DOUBLE(), Types.LONG(),
        ]),
    )

    # Apply watermark strategy with 5s out-of-orderness
    # and 60s idle timeout
    watermarked = source.assign_timestamps_and_watermarks(
        WatermarkStrategy
        .for_bounded_out_of_orderness(Duration.of_seconds(5))
        .with_timestamp_assigner(MultiSourceTimestampAssigner())
        .with_idleness(Duration.of_seconds(60))
    )

    # Debug watermarks
    debugged = watermarked.map(WatermarkDebugFunction())

    # Session detection with event-time timers
    sessions = (
        debugged
        .key_by(lambda x: x[0])
        .process(EventTimeSessionDetector())
    )

    sessions.print("SESSIONS")
    env.execute("Event-Time Pipeline")
```

**Watermark strategy comparison:**

| Strategy | When to Use | Trade-off |
|---|---|---|
| Bounded out-of-orderness | Most common; known max lateness | Simple but fixed tolerance |
| Punctuated | Source embeds watermark signals | Precise but requires cooperation |
| Progressive | Low-traffic sources with stalls | Prevents stuck watermarks |
| With idleness | Multi-partition with inactive partitions | Prevents idle source blocking |

**Key patterns:**
- Set `max_out_of_orderness` to observed 99th percentile event lateness
- Use `with_idleness()` to prevent idle Kafka partitions from blocking watermark progress
- Register event-time timers in `KeyedProcessFunction` for session timeout detection
- Delete old timers before registering new ones to prevent state accumulation
- Monitor watermark progression and late event percentage for tuning
- Clamp future timestamps to prevent clock-skew from advancing watermarks incorrectly
- Set auto-watermark-interval (200ms default) to control watermark emission frequency'''
    ),
    (
        "data-engineering/flink-exactly-once",
        "Explain how Flink achieves exactly-once semantics end-to-end with Kafka, including two-phase commit sinks, checkpoint barriers, and how to recover from failures without data loss or duplication.",
        '''Flink exactly-once semantics: checkpoint barriers, two-phase commit, and end-to-end guarantees:

```python
"""
Flink exactly-once semantics: end-to-end guarantees with
checkpoint barriers, two-phase commit sinks, and idempotent
writes for external systems.
"""

from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.connectors.kafka import (
    KafkaSource, KafkaOffsetsInitializer,
    KafkaSink, KafkaRecordSerializationSchema,
)
from pyflink.common.serialization import SimpleStringSchema
from pyflink.common import WatermarkStrategy, Types, Configuration
from pyflink.datastream.functions import (
    MapFunction, SinkFunction, RuntimeContext,
    KeyedProcessFunction,
)
from pyflink.datastream.state import (
    ValueStateDescriptor, MapStateDescriptor,
    ListStateDescriptor,
)
import json
import hashlib
import time
from typing import Any, Optional


# --- Exactly-once Kafka pipeline configuration ---

def create_exactly_once_pipeline():
    """
    End-to-end exactly-once pipeline:
    Kafka Source -> Processing -> Kafka Sink

    Exactly-once guarantee chain:
    1. Source: Kafka offsets committed with checkpoints
    2. State: RocksDB state snapshotted at checkpoint barriers
    3. Sink: Two-phase commit Kafka producer

    Checkpoint barrier flow:
    ┌──────────┐   barrier   ┌───────────┐   barrier   ┌──────────┐
    │  Source   │──────────→ │  Operator  │──────────→ │   Sink   │
    │(save     │             │(snapshot   │             │(pre-     │
    │ offsets) │             │ state)     │             │ commit)  │
    └──────────┘             └───────────┘             └──────────┘
                                                            │
                            All operators complete ─────────┘
                                                            │
                                                       ┌──────────┐
                                                       │  Commit  │
                                                       │(finalize)│
                                                       └──────────┘
    """
    config = Configuration()

    # Checkpoint configuration for exactly-once
    config.set_string("execution.checkpointing.mode", "EXACTLY_ONCE")
    config.set_string("execution.checkpointing.interval", "30s")
    config.set_string("execution.checkpointing.min-pause", "10s")
    config.set_string("execution.checkpointing.timeout", "120s")
    config.set_string(
        "execution.checkpointing.max-concurrent-checkpoints", "1"
    )
    config.set_string(
        "execution.checkpointing.externalized-checkpoint-retention",
        "RETAIN_ON_CANCELLATION",
    )

    # Unaligned checkpoints for better throughput under backpressure
    config.set_string(
        "execution.checkpointing.unaligned.enabled", "true"
    )

    # State backend
    config.set_string("state.backend.type", "rocksdb")
    config.set_string("state.backend.incremental", "true")
    config.set_string(
        "state.checkpoints.dir", "s3://checkpoints/exactly-once-demo"
    )

    env = StreamExecutionEnvironment.get_execution_environment(config)
    env.set_parallelism(4)

    # Kafka source with exactly-once consumption
    source = (
        KafkaSource.builder()
        .set_bootstrap_servers("kafka:9092")
        .set_topics("input-events")
        .set_group_id("exactly-once-consumer")
        .set_starting_offsets(KafkaOffsetsInitializer.committed())
        .set_value_only_deserializer(SimpleStringSchema())
        # Critical: read_committed sees only committed transactions
        .set_property("isolation.level", "read_committed")
        .build()
    )

    # Kafka sink with two-phase commit
    sink = (
        KafkaSink.builder()
        .set_bootstrap_servers("kafka:9092")
        .set_record_serializer(
            KafkaRecordSerializationSchema.builder()
            .set_topic("output-events")
            .set_value_serialization_schema(SimpleStringSchema())
            .build()
        )
        # Two-phase commit for exactly-once delivery
        .set_delivery_guarantee("exactly-once")
        .set_transactional_id_prefix("eo-pipeline")
        # Transaction timeout must be <= broker transaction.max.timeout.ms
        .set_property("transaction.timeout.ms", "900000")  # 15 min
        .build()
    )

    # Build pipeline
    stream = env.from_source(
        source, WatermarkStrategy.no_watermarks(), "Kafka Source"
    )

    processed = (
        stream
        .map(DeduplicationFunction())
        .key_by(lambda x: json.loads(x).get("key", "default"))
        .process(ExactlyOnceAggregator())
    )

    processed.sink_to(sink)
    env.execute("Exactly-Once Pipeline")


# --- Deduplication for at-least-once sources ---

class DeduplicationFunction(MapFunction):
    """
    Deduplication for sources without exactly-once guarantees.
    Uses a content hash to detect duplicates.
    """

    def open(self, runtime_context: RuntimeContext):
        # In production, use MapState for per-key dedup
        self.seen_hashes: set = set()
        self.window_size = 100_000  # Max dedup window

    def map(self, value: str) -> Optional[str]:
        content_hash = hashlib.sha256(value.encode()).hexdigest()[:16]

        if content_hash in self.seen_hashes:
            return None  # Duplicate, skip

        self.seen_hashes.add(content_hash)

        # Evict oldest if window exceeded
        if len(self.seen_hashes) > self.window_size:
            self.seen_hashes = set(
                list(self.seen_hashes)[self.window_size // 2:]
            )

        return value


class ExactlyOnceAggregator(KeyedProcessFunction):
    """
    Stateful aggregator that maintains correctness across
    checkpoint/restore cycles.

    On failure recovery:
    1. State rolls back to last successful checkpoint
    2. Kafka source replays from committed offsets
    3. Kafka sink aborts uncommitted transactions
    4. Result: exactly-once processing guaranteed
    """

    def open(self, runtime_context: RuntimeContext):
        self.count = runtime_context.get_state(
            ValueStateDescriptor("count", Types.LONG())
        )
        self.total = runtime_context.get_state(
            ValueStateDescriptor("total", Types.DOUBLE())
        )
        self.last_output_time = runtime_context.get_state(
            ValueStateDescriptor("last_output", Types.LONG())
        )

    def process_element(self, value, ctx):
        event = json.loads(value)
        amount = float(event.get("amount", 0))

        current_count = (self.count.value() or 0) + 1
        current_total = (self.total.value() or 0.0) + amount

        self.count.update(current_count)
        self.total.update(current_total)

        # Emit aggregate every 100 events
        if current_count % 100 == 0:
            self.last_output_time.update(ctx.timestamp())
            yield json.dumps({
                "key": ctx.get_current_key(),
                "count": current_count,
                "total": round(current_total, 2),
                "avg": round(current_total / current_count, 2),
                "timestamp": ctx.timestamp(),
            })


# --- Idempotent database sink ---

class IdempotentDatabaseSink(SinkFunction):
    """
    Idempotent sink pattern for databases that don't support
    two-phase commit. Uses checkpoint ID + sequence number
    for deduplication.

    Table schema:
    CREATE TABLE results (
        sink_id VARCHAR(64),
        checkpoint_id BIGINT,
        sequence_num BIGINT,
        key VARCHAR(255),
        value JSONB,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        PRIMARY KEY (sink_id, checkpoint_id, sequence_num)
    );
    """

    def __init__(self, sink_id: str, connection_string: str):
        self.sink_id = sink_id
        self.connection_string = connection_string
        self.sequence = 0
        self.checkpoint_id = 0

    def invoke(self, value, context):
        """
        Idempotent write: INSERT ... ON CONFLICT DO NOTHING.
        If replay occurs after failure, duplicate writes are
        silently ignored by the primary key constraint.
        """
        self.sequence += 1

        # In production, use actual DB connection
        sql = """
            INSERT INTO results (
                sink_id, checkpoint_id, sequence_num, key, value
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (sink_id, checkpoint_id, sequence_num)
            DO NOTHING;
        """
        # execute(sql, (self.sink_id, self.checkpoint_id,
        #               self.sequence, key, value))


# --- Two-phase commit explanation ---

TWO_PHASE_COMMIT_FLOW = """
Two-Phase Commit Protocol for Exactly-Once Sinks:

Phase 1: Pre-commit (on checkpoint barrier)
┌──────────────────────────────────────────────┐
│ 1. Checkpoint barrier arrives at sink        │
│ 2. Sink flushes buffered records             │
│ 3. Sink calls KafkaProducer.flush()          │
│ 4. Sink snapshots transaction ID to state    │
│ 5. Sink acknowledges checkpoint to JM        │
└──────────────────────────────────────────────┘

Phase 2: Commit (after all operators complete checkpoint)
┌──────────────────────────────────────────────┐
│ 1. JobManager notifies: checkpoint complete  │
│ 2. Sink calls KafkaProducer.commitTransaction│
│ 3. Records become visible to consumers       │
│ 4. Old transaction state cleaned up          │
└──────────────────────────────────────────────┘

On Failure:
┌──────────────────────────────────────────────┐
│ 1. Uncommitted transactions are aborted      │
│ 2. State restores from last checkpoint       │
│ 3. Source replays from checkpoint offsets     │
│ 4. Processing resumes with clean state       │
│ 5. No duplicates: old txn records invisible  │
└──────────────────────────────────────────────┘
"""
```

**Exactly-once guarantee requirements:**

| Component | Requirement | Flink Mechanism |
|---|---|---|
| Source | Replayable from offset | Kafka committed offsets |
| Processing | State snapshot + replay | Checkpoint barriers + RocksDB |
| Kafka Sink | Atomic visibility | Two-phase commit transactions |
| DB Sink | No duplicate writes | Idempotent upserts with dedup key |

**Checkpoint configuration trade-offs:**

| Setting | Low Value | High Value |
|---|---|---|
| Interval | More overhead, faster recovery | Less overhead, more replay |
| Timeout | Fails fast on slow checkpoints | Tolerates slow checkpoints |
| Min pause | More frequent checkpoints | Less checkpoint overlap |
| Unaligned | N/A | Better throughput under backpressure |

**Key patterns:**
- Kafka source `read_committed` + sink `exactly-once` for end-to-end guarantees
- Two-phase commit: pre-commit on barrier, commit after all operators snapshot
- Transactional ID prefix must be unique per pipeline to avoid conflicts
- Transaction timeout must be less than broker `transaction.max.timeout.ms`
- Unaligned checkpoints improve throughput under backpressure at cost of larger state
- Idempotent database sinks use (sink_id, checkpoint_id, sequence) as dedup key
- On failure, uncommitted Kafka transactions are invisible to `read_committed` consumers'''
    ),
    (
        "data-engineering/flink-state-management",
        "Show advanced Flink state management patterns including keyed state, operator state, state TTL, queryable state, and state migration strategies for schema evolution.",
        '''Advanced Flink state management: keyed state, TTL, queryable state, and schema evolution:

```python
"""
Flink state management: keyed state types, TTL configuration,
broadcast state, and state schema evolution strategies.
"""

from pyflink.datastream import StreamExecutionEnvironment
from pyflink.datastream.functions import (
    KeyedProcessFunction, RuntimeContext,
    KeyedBroadcastProcessFunction,
    BroadcastProcessFunction,
)
from pyflink.datastream.state import (
    ValueStateDescriptor, ListStateDescriptor,
    MapStateDescriptor, ReducingStateDescriptor,
    StateTtlConfig,
)
from pyflink.common import Types, Time, Duration, Configuration
import json
import time
from typing import Any, Optional, Iterator
from dataclasses import dataclass


# --- State TTL (Time-To-Live) configuration ---

def create_ttl_config(
    ttl_hours: int = 24,
    update_on_read: bool = True,
    cleanup_in_background: bool = True,
) -> StateTtlConfig:
    """
    Configure state TTL for automatic expiration.

    TTL prevents unbounded state growth by expiring entries
    that haven't been accessed within the TTL window.
    """
    builder = (
        StateTtlConfig.new_builder(Time.hours(ttl_hours))
        .set_state_visibility(
            StateTtlConfig.StateVisibility.NeverReturnExpired
        )
    )

    if update_on_read:
        builder.set_update_type(
            StateTtlConfig.UpdateType.OnReadAndWrite
        )
    else:
        builder.set_update_type(
            StateTtlConfig.UpdateType.OnCreateAndWrite
        )

    if cleanup_in_background:
        builder.cleanup_in_rocksdb_compact_filter(1000)

    return builder.build()


# --- Comprehensive keyed state example ---

class UserProfileAggregator(KeyedProcessFunction):
    """
    Demonstrates all keyed state types with TTL for managing
    per-user profiles and activity metrics.

    State types:
    - ValueState: single value per key (latest profile)
    - ListState: append-only list per key (recent events)
    - MapState: key-value map per key (feature counters)
    """

    def open(self, runtime_context: RuntimeContext):
        # ValueState: latest user profile snapshot
        profile_desc = ValueStateDescriptor(
            "user_profile", Types.STRING()
        )
        profile_desc.enable_time_to_live(
            create_ttl_config(ttl_hours=168)  # 7 days
        )
        self.profile = runtime_context.get_state(profile_desc)

        # ListState: recent events (last N)
        events_desc = ListStateDescriptor(
            "recent_events", Types.STRING()
        )
        events_desc.enable_time_to_live(
            create_ttl_config(ttl_hours=24)  # 1 day
        )
        self.recent_events = runtime_context.get_list_state(events_desc)

        # MapState: feature counters
        counters_desc = MapStateDescriptor(
            "feature_counters", Types.STRING(), Types.LONG()
        )
        counters_desc.enable_time_to_live(
            create_ttl_config(ttl_hours=720)  # 30 days
        )
        self.counters = runtime_context.get_map_state(counters_desc)

        # ValueState: session tracking
        session_desc = ValueStateDescriptor(
            "session_data", Types.STRING()
        )
        session_desc.enable_time_to_live(
            create_ttl_config(
                ttl_hours=1,
                update_on_read=True,  # Extend TTL on reads
            )
        )
        self.session = runtime_context.get_state(session_desc)

    def process_element(self, value, ctx):
        """Process user events with stateful aggregation."""
        event = json.loads(value) if isinstance(value, str) else value
        user_id = ctx.get_current_key()
        event_type = event.get("type", "unknown")
        timestamp = ctx.timestamp()

        # Update profile (ValueState)
        profile = self.profile.value()
        if profile:
            profile_data = json.loads(profile)
        else:
            profile_data = {
                "user_id": user_id,
                "first_seen": timestamp,
                "total_events": 0,
            }
        profile_data["last_seen"] = timestamp
        profile_data["total_events"] += 1
        self.profile.update(json.dumps(profile_data))

        # Append to recent events (ListState)
        self.recent_events.add(json.dumps({
            "type": event_type,
            "timestamp": timestamp,
        }))

        # Trim list to last 100 events
        all_events = list(self.recent_events.get())
        if len(all_events) > 100:
            self.recent_events.clear()
            for e in all_events[-100:]:
                self.recent_events.add(e)

        # Increment feature counter (MapState)
        current = self.counters.get(event_type)
        self.counters.put(event_type, (current or 0) + 1)

        # Session management (ValueState with short TTL)
        session_raw = self.session.value()
        if session_raw:
            session_data = json.loads(session_raw)
            session_data["event_count"] += 1
            session_data["last_activity"] = timestamp
        else:
            session_data = {
                "session_start": timestamp,
                "event_count": 1,
                "last_activity": timestamp,
            }
        self.session.update(json.dumps(session_data))

        # Emit enriched event
        yield json.dumps({
            "user_id": user_id,
            "event_type": event_type,
            "total_events": profile_data["total_events"],
            "session_events": session_data["event_count"],
            "feature_count": self.counters.get(event_type),
            "timestamp": timestamp,
        })

    def on_timer(self, timestamp, ctx):
        """Clean up on timer expiry."""
        pass


# --- Broadcast state for dynamic configuration ---

# Descriptor for broadcast state (rules/config)
RULES_DESCRIPTOR = MapStateDescriptor(
    "rules", Types.STRING(), Types.STRING()
)


class DynamicRuleProcessor(KeyedBroadcastProcessFunction):
    """
    Use broadcast state to dynamically update processing rules
    without restarting the pipeline.

    Pattern: Rules broadcast stream + Events keyed stream
    - Rules stream: small, infrequent config updates
    - Events stream: high-volume keyed events

    ┌─────────────┐
    │ Rules Topic  │──broadcast──┐
    └─────────────┘              │
                                 ▼
                    ┌──────────────────────┐
                    │ KeyedBroadcast       │
                    │ ProcessFunction      │──→ output
                    │ (rules + events)     │
                    └──────────────────────┘
                                 ▲
    ┌─────────────┐              │
    │ Events Topic │──keyed──────┘
    └─────────────┘
    """

    def process_broadcast_element(self, value, ctx):
        """Handle rule updates (broadcast side)."""
        rule = json.loads(value)
        rule_id = rule.get("rule_id", "default")

        # Update broadcast state (visible to all parallel instances)
        ctx.get_broadcast_state(RULES_DESCRIPTOR).put(
            rule_id, json.dumps(rule)
        )

    def process_element(self, value, ctx):
        """Process events against current rules (keyed side)."""
        event = json.loads(value)
        rules_state = ctx.get_broadcast_state(RULES_DESCRIPTOR)

        # Apply all active rules
        for rule_id in rules_state.keys():
            rule = json.loads(rules_state.get(rule_id))

            if self._matches_rule(event, rule):
                yield json.dumps({
                    "event": event,
                    "matched_rule": rule_id,
                    "action": rule.get("action", "alert"),
                })

    def _matches_rule(self, event: dict, rule: dict) -> bool:
        """Check if event matches a rule's conditions."""
        conditions = rule.get("conditions", {})
        for field, expected in conditions.items():
            if event.get(field) != expected:
                return False
        return True


# --- State migration and schema evolution ---

STATE_SCHEMA_EVOLUTION = """
State Schema Evolution Strategies:

1. Compatible changes (automatic):
   - Adding new fields with defaults
   - Widening numeric types (int -> long)

2. State migration (savepoint-based):
   a. Take savepoint: flink savepoint <job_id> <path>
   b. Modify state schema in new code version
   c. Resume from savepoint: flink run -s <savepoint_path> new_job.jar

3. State processor API (offline migration):
   - Read state from savepoint programmatically
   - Transform state schema offline
   - Write new savepoint with migrated state

4. Dual-read pattern (zero-downtime):
   - New code reads both old and new state format
   - Lazy migration: convert on first read
   - After full migration, remove old format support

Example dual-read migration:
"""


class StateMigrationExample(KeyedProcessFunction):
    """
    Demonstrates dual-read state migration pattern.
    Migrates from v1 (flat counter) to v2 (structured profile).
    """

    CURRENT_VERSION = 2

    def open(self, runtime_context: RuntimeContext):
        # v1 state (old format: simple counter)
        self.v1_counter = runtime_context.get_state(
            ValueStateDescriptor("counter_v1", Types.LONG())
        )
        # v2 state (new format: structured profile)
        self.v2_profile = runtime_context.get_state(
            ValueStateDescriptor("profile_v2", Types.STRING())
        )
        # Version tracker
        self.state_version = runtime_context.get_state(
            ValueStateDescriptor("state_version", Types.INT())
        )

    def process_element(self, value, ctx):
        version = self.state_version.value() or 1

        if version < self.CURRENT_VERSION:
            self._migrate_state(version)

        # Process with v2 state
        profile_raw = self.v2_profile.value()
        profile = json.loads(profile_raw) if profile_raw else {
            "count": 0, "total": 0.0, "first_seen": ctx.timestamp(),
        }

        event = json.loads(value)
        profile["count"] += 1
        profile["total"] += float(event.get("amount", 0))
        profile["last_seen"] = ctx.timestamp()

        self.v2_profile.update(json.dumps(profile))

        yield json.dumps({
            "key": ctx.get_current_key(),
            "profile": profile,
        })

    def _migrate_state(self, from_version: int):
        """Migrate state from old version to current."""
        if from_version == 1:
            # Read v1 counter
            old_count = self.v1_counter.value() or 0

            # Create v2 profile from v1 data
            profile = {
                "count": old_count,
                "total": 0.0,  # Unknown in v1
                "first_seen": 0,
                "migrated_from_v1": True,
            }
            self.v2_profile.update(json.dumps(profile))

            # Clean up v1 state
            self.v1_counter.clear()

        # Mark as migrated
        self.state_version.update(self.CURRENT_VERSION)
```

**Keyed state types and their use cases:**

| State Type | Structure | Use Case |
|---|---|---|
| ValueState | Single value per key | Latest profile, running aggregate |
| ListState | Ordered list per key | Recent events, sliding windows |
| MapState | Key-value map per key | Feature counters, lookup tables |
| ReducingState | Aggregated value per key | Running sum, count, min/max |
| AggregatingState | Custom aggregator per key | Complex aggregations |

**State TTL configuration options:**

| Option | Behavior |
|---|---|
| OnCreateAndWrite | TTL resets only on state writes |
| OnReadAndWrite | TTL resets on reads and writes (session-like) |
| NeverReturnExpired | Expired state invisible even before cleanup |
| cleanup_in_rocksdb | Background compaction removes expired entries |

**Key patterns:**
- Use State TTL to prevent unbounded state growth in long-running pipelines
- Configure different TTL durations per state descriptor based on data lifecycle
- Broadcast state enables dynamic rule updates without pipeline restart
- Trim `ListState` periodically to prevent memory issues (keep last N entries)
- Dual-read state migration pattern enables zero-downtime schema evolution
- Use version tracking state to trigger lazy migration on first access
- RocksDB compact filter cleanup removes expired state during compaction'''
    ),
]
