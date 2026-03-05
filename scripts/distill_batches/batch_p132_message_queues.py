"""Message queues — RabbitMQ, Kafka, and async task processing."""

PAIRS = [
    (
        "backend/rabbitmq-patterns",
        "Show RabbitMQ patterns: exchanges, queues, dead letter queues, and consumer patterns in Python.",
        '''RabbitMQ messaging patterns:

```python
import pika
import json
import logging
from dataclasses import dataclass, asdict
from typing import Callable, Any
from functools import wraps

logger = logging.getLogger(__name__)


# --- Connection management ---

class RabbitMQConnection:
    """Managed RabbitMQ connection with auto-reconnect."""

    def __init__(self, url: str = "amqp://guest:guest@localhost:5672/"):
        self.url = url
        self._connection = None
        self._channel = None

    @property
    def channel(self) -> pika.channel.Channel:
        if self._channel is None or self._channel.is_closed:
            self._connection = pika.BlockingConnection(
                pika.URLParameters(self.url)
            )
            self._channel = self._connection.channel()
            self._channel.basic_qos(prefetch_count=10)
        return self._channel

    def close(self):
        if self._connection and self._connection.is_open:
            self._connection.close()


# --- Exchange and queue setup ---

def setup_topology(channel: pika.channel.Channel):
    """Declare exchanges, queues, and bindings."""

    # Dead letter exchange
    channel.exchange_declare(
        exchange="dlx",
        exchange_type="direct",
        durable=True,
    )
    channel.queue_declare(
        queue="dead_letters",
        durable=True,
    )
    channel.queue_bind(
        queue="dead_letters",
        exchange="dlx",
        routing_key="dead",
    )

    # Main topic exchange
    channel.exchange_declare(
        exchange="events",
        exchange_type="topic",
        durable=True,
    )

    # Order processing queue with DLQ
    channel.queue_declare(
        queue="order.process",
        durable=True,
        arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "dead",
            "x-message-ttl": 86400000,   # 24h TTL
            "x-max-length": 100000,       # Max queue size
        },
    )
    channel.queue_bind(
        queue="order.process",
        exchange="events",
        routing_key="order.created",
    )

    # Notification queue (fan-out from multiple events)
    channel.queue_declare(queue="notifications", durable=True)
    for key in ["order.created", "order.shipped", "user.registered"]:
        channel.queue_bind(
            queue="notifications",
            exchange="events",
            routing_key=key,
        )


# --- Publisher ---

class EventPublisher:
    """Publish events with automatic serialization."""

    def __init__(self, connection: RabbitMQConnection):
        self.connection = connection

    def publish(
        self,
        routing_key: str,
        body: dict,
        exchange: str = "events",
        priority: int = 0,
    ):
        self.connection.channel.basic_publish(
            exchange=exchange,
            routing_key=routing_key,
            body=json.dumps(body),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Persistent
                content_type="application/json",
                priority=priority,
                headers={"routing_key": routing_key},
            ),
        )
        logger.info("Published %s", routing_key)


# --- Consumer with retry ---

def consume_with_retry(
    channel: pika.channel.Channel,
    queue: str,
    handler: Callable,
    max_retries: int = 3,
):
    """Consume messages with automatic retry and DLQ on failure."""

    def callback(ch, method, properties, body):
        retry_count = (properties.headers or {}).get("x-retry-count", 0)

        try:
            message = json.loads(body)
            handler(message)
            ch.basic_ack(delivery_tag=method.delivery_tag)

        except Exception as e:
            logger.error("Error processing message: %s (retry %d)", e, retry_count)

            if retry_count < max_retries:
                # Re-publish with incremented retry count
                ch.basic_publish(
                    exchange="",
                    routing_key=queue,
                    body=body,
                    properties=pika.BasicProperties(
                        delivery_mode=2,
                        headers={"x-retry-count": retry_count + 1},
                    ),
                )
                ch.basic_ack(delivery_tag=method.delivery_tag)
            else:
                # Send to DLQ (nack without requeue)
                ch.basic_nack(
                    delivery_tag=method.delivery_tag,
                    requeue=False,
                )
                logger.error("Message sent to DLQ after %d retries", max_retries)

    channel.basic_consume(queue=queue, on_message_callback=callback)
    logger.info("Consuming from %s...", queue)
    channel.start_consuming()


# --- Usage ---

# conn = RabbitMQConnection()
# setup_topology(conn.channel)
#
# publisher = EventPublisher(conn)
# publisher.publish("order.created", {"order_id": "123", "total": 99.99})
#
# def handle_order(msg):
#     print(f"Processing order {msg['order_id']}")
#
# consume_with_retry(conn.channel, "order.process", handle_order)
```

RabbitMQ patterns:
1. **Topic exchange** — route messages by pattern (`order.*`, `user.#`) for flexible routing
2. **Dead letter queue** — failed messages go to DLQ after max retries for later inspection
3. **`prefetch_count`** — limit unacked messages per consumer for fair dispatch
4. **Persistent messages** — `delivery_mode=2` survives broker restart
5. **Retry with count header** — re-publish with `x-retry-count` before DLQ escalation'''
    ),
    (
        "backend/kafka-patterns",
        "Show Apache Kafka patterns: producers, consumers, consumer groups, and exactly-once processing in Python.",
        '''Apache Kafka patterns:

```python
from confluent_kafka import (
    Producer, Consumer, KafkaError, KafkaException,
    TopicPartition,
)
from confluent_kafka.admin import AdminClient, NewTopic
import json
import logging
import signal
from typing import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


# --- Topic management ---

def ensure_topics(bootstrap_servers: str, topics: list[dict]):
    """Create topics if they don't exist."""
    admin = AdminClient({"bootstrap.servers": bootstrap_servers})

    new_topics = [
        NewTopic(
            t["name"],
            num_partitions=t.get("partitions", 6),
            replication_factor=t.get("replication", 3),
            config=t.get("config", {}),
        )
        for t in topics
    ]

    futures = admin.create_topics(new_topics)
    for topic, future in futures.items():
        try:
            future.result()
            logger.info("Created topic: %s", topic)
        except KafkaException as e:
            if e.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
                raise


# ensure_topics("localhost:9092", [
#     {"name": "orders", "partitions": 12, "config": {"retention.ms": "604800000"}},
#     {"name": "notifications", "partitions": 6},
# ])


# --- Producer with delivery callbacks ---

class KafkaProducer:
    """Kafka producer with JSON serialization and delivery tracking."""

    def __init__(self, bootstrap_servers: str):
        self._producer = Producer({
            "bootstrap.servers": bootstrap_servers,
            "acks": "all",                    # Wait for all replicas
            "enable.idempotence": True,       # Exactly-once semantics
            "max.in.flight.requests.per.connection": 5,
            "retries": 10,
            "linger.ms": 10,                  # Batch for 10ms
            "compression.type": "lz4",
        })
        self._delivery_count = 0

    def _delivery_callback(self, err, msg):
        if err:
            logger.error("Delivery failed: %s", err)
        else:
            self._delivery_count += 1

    def send(
        self,
        topic: str,
        value: dict,
        key: str | None = None,
        headers: dict | None = None,
    ):
        """Send message with optional key for partition routing."""
        self._producer.produce(
            topic=topic,
            value=json.dumps(value).encode("utf-8"),
            key=key.encode("utf-8") if key else None,
            headers=headers or {},
            callback=self._delivery_callback,
        )
        self._producer.poll(0)  # Trigger callbacks

    def flush(self, timeout: float = 10.0):
        """Wait for all messages to be delivered."""
        self._producer.flush(timeout)


# --- Consumer with graceful shutdown ---

class KafkaConsumer:
    """Kafka consumer with consumer group and offset management."""

    def __init__(
        self,
        bootstrap_servers: str,
        group_id: str,
        topics: list[str],
        auto_commit: bool = False,
    ):
        self._consumer = Consumer({
            "bootstrap.servers": bootstrap_servers,
            "group.id": group_id,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": auto_commit,
            "max.poll.interval.ms": 300000,
            "session.timeout.ms": 30000,
        })
        self._consumer.subscribe(topics)
        self._running = True

        # Graceful shutdown
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, *args):
        self._running = False

    def consume(
        self,
        handler: Callable[[dict], None],
        batch_size: int = 100,
        timeout: float = 1.0,
    ):
        """Consume messages with manual commit after processing."""
        try:
            while self._running:
                msg = self._consumer.poll(timeout)

                if msg is None:
                    continue
                if msg.error():
                    if msg.error().code() == KafkaError._PARTITION_EOF:
                        continue
                    raise KafkaException(msg.error())

                try:
                    value = json.loads(msg.value().decode("utf-8"))
                    handler(value)
                    # Commit after successful processing
                    self._consumer.commit(asynchronous=False)

                except json.JSONDecodeError:
                    logger.error("Invalid JSON at offset %d", msg.offset())
                    self._consumer.commit(asynchronous=False)  # Skip bad message

                except Exception as e:
                    logger.error("Handler error: %s", e)
                    # Don't commit — message will be redelivered

        finally:
            self._consumer.close()
            logger.info("Consumer shut down cleanly")


# --- Exactly-once transactional producer ---

def transactional_produce(bootstrap_servers: str, topic: str, messages: list[dict]):
    """Produce batch of messages atomically."""
    producer = Producer({
        "bootstrap.servers": bootstrap_servers,
        "transactional.id": "my-transaction-id",
        "acks": "all",
        "enable.idempotence": True,
    })

    producer.init_transactions()
    producer.begin_transaction()

    try:
        for msg in messages:
            producer.produce(
                topic=topic,
                value=json.dumps(msg).encode("utf-8"),
            )
        producer.commit_transaction()
    except Exception:
        producer.abort_transaction()
        raise


# --- Usage ---

# producer = KafkaProducer("localhost:9092")
# producer.send("orders", {"order_id": "123"}, key="customer-456")
# producer.flush()
#
# consumer = KafkaConsumer(
#     "localhost:9092",
#     group_id="order-processor",
#     topics=["orders"],
# )
# consumer.consume(lambda msg: print(f"Order: {msg}"))
```

Kafka patterns:
1. **`acks=all` + idempotence** — exactly-once delivery with all replicas acknowledging
2. **Consumer groups** — automatic partition assignment for horizontal scaling
3. **Manual commit** — commit offset only after successful processing (at-least-once)
4. **Key-based routing** — same key always goes to same partition (ordering guarantee)
5. **Transactional produce** — atomic batch writes with `begin/commit_transaction()`'''
    ),
    (
        "backend/celery-tasks",
        "Show Celery task patterns: task definition, retries, chains, groups, and monitoring.",
        '''Celery async task patterns:

```python
from celery import Celery, chain, group, chord, Task
from celery.exceptions import MaxRetriesExceededError
from celery.signals import task_failure, task_success
from celery.utils.log import get_task_logger
from datetime import timedelta
import httpx

logger = get_task_logger(__name__)

app = Celery("myapp")
app.config_from_object({
    "broker_url": "redis://localhost:6379/0",
    "result_backend": "redis://localhost:6379/1",
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],
    "task_track_started": True,
    "task_time_limit": 300,        # Hard kill after 5 min
    "task_soft_time_limit": 240,   # SoftTimeLimitExceeded after 4 min
    "worker_prefetch_multiplier": 1,
    "task_acks_late": True,        # Ack after completion (at-least-once)
    "task_reject_on_worker_lost": True,
})


# --- Basic task with retry ---

@app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(httpx.HTTPError, ConnectionError),
    retry_backoff=True,       # Exponential backoff
    retry_backoff_max=600,    # Max 10 min between retries
    retry_jitter=True,        # Add randomness to prevent thundering herd
)
def send_webhook(self, url: str, payload: dict) -> dict:
    """Send webhook with automatic retry on failure."""
    response = httpx.post(url, json=payload, timeout=30)
    response.raise_for_status()
    return {"status": response.status_code, "url": url}


# --- Task with manual retry and custom logic ---

@app.task(bind=True, max_retries=5)
def process_order(self, order_id: str) -> dict:
    """Process order with manual retry control."""
    try:
        order = fetch_order(order_id)

        if order["status"] == "pending_payment":
            # Retry later — payment not confirmed yet
            raise self.retry(countdown=30, exc=Exception("Payment pending"))

        result = fulfill_order(order)
        return {"order_id": order_id, "status": "fulfilled"}

    except MaxRetriesExceededError:
        logger.error("Order %s failed after max retries", order_id)
        mark_order_failed(order_id)
        return {"order_id": order_id, "status": "failed"}


# --- Task routing by queue ---

@app.task(queue="high_priority")
def send_alert(message: str, channel: str):
    """High-priority task routed to dedicated queue."""
    notify(channel, message)


@app.task(queue="bulk")
def generate_report(report_type: str, params: dict) -> str:
    """Long-running task on bulk queue."""
    return build_report(report_type, params)


# --- Workflows: chain, group, chord ---

def process_new_user(user_id: str):
    """Chain: sequential tasks, each gets previous result."""
    workflow = chain(
        validate_user.s(user_id),
        create_account.s(),      # Gets validate_user result
        send_welcome_email.s(),  # Gets create_account result
    )
    workflow.apply_async()


def send_bulk_notifications(user_ids: list[str], message: str):
    """Group: parallel tasks."""
    job = group(
        send_notification.s(uid, message) for uid in user_ids
    )
    result = job.apply_async()
    # result.get()  # Wait for all


def generate_dashboard(date: str):
    """Chord: parallel tasks + callback when all complete."""
    header = group(
        compute_revenue.s(date),
        compute_signups.s(date),
        compute_churn.s(date),
    )
    callback = build_dashboard.s(date)
    chord(header)(callback)  # callback gets list of results


# --- Periodic tasks (beat schedule) ---

app.conf.beat_schedule = {
    "cleanup-expired-sessions": {
        "task": "myapp.tasks.cleanup_sessions",
        "schedule": timedelta(hours=1),
    },
    "daily-report": {
        "task": "myapp.tasks.generate_daily_report",
        "schedule": crontab(hour=6, minute=0),
    },
}


# --- Monitoring signals ---

@task_failure.connect
def handle_task_failure(sender=None, task_id=None, exception=None, **kwargs):
    logger.error("Task %s failed: %s", task_id, exception)
    # Send alert to monitoring system


@task_success.connect
def handle_task_success(sender=None, result=None, **kwargs):
    # Track metrics
    pass
```

Celery patterns:
1. **`autoretry_for` + `retry_backoff`** — automatic exponential retry for transient errors
2. **`bind=True`** — access `self.retry()` for manual retry with custom countdown
3. **`chain()`** — sequential pipeline where each task receives previous result
4. **`chord(header)(callback)`** — parallel group with callback when all tasks complete
5. **`task_acks_late=True`** — acknowledge after processing for at-least-once delivery'''
    ),
]
