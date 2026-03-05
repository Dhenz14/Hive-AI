"""Message queues — RabbitMQ, SQS, patterns for reliable messaging."""

PAIRS = [
    (
        "architecture/message-queue-patterns",
        "Show message queue patterns: publish/subscribe, work queues, dead letter queues, and exactly-once processing with RabbitMQ and Python.",
        '''Message queue patterns for reliable async processing:

```python
import aio_pika
import json
import asyncio
from dataclasses import dataclass, asdict
from typing import Callable, Awaitable
from datetime import datetime, timezone

# --- Publisher with confirmation ---

class RabbitPublisher:
    def __init__(self, url: str = "amqp://guest:guest@localhost/"):
        self.url = url
        self.connection = None
        self.channel = None

    async def connect(self):
        self.connection = await aio_pika.connect_robust(self.url)
        self.channel = await self.connection.channel()
        # Enable publisher confirms
        await self.channel.set_qos(prefetch_count=10)

    async def declare_exchange(self, name: str,
                                exchange_type: str = "topic") -> aio_pika.Exchange:
        return await self.channel.declare_exchange(
            name, aio_pika.ExchangeType(exchange_type), durable=True
        )

    async def publish(self, exchange: aio_pika.Exchange,
                      routing_key: str, message: dict,
                      headers: dict = None):
        body = json.dumps(message, default=str).encode()
        await exchange.publish(
            aio_pika.Message(
                body=body,
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=message.get("id", ""),
                timestamp=datetime.now(timezone.utc),
                headers=headers or {},
            ),
            routing_key=routing_key,
        )

    async def close(self):
        if self.connection:
            await self.connection.close()


# --- Consumer with retry and DLQ ---

class RabbitConsumer:
    def __init__(self, url: str = "amqp://guest:guest@localhost/"):
        self.url = url
        self.handlers: dict[str, Callable] = {}

    async def connect(self):
        self.connection = await aio_pika.connect_robust(self.url)
        self.channel = await self.connection.channel()
        await self.channel.set_qos(prefetch_count=10)

    async def setup_queue_with_dlq(
        self, queue_name: str, exchange_name: str,
        routing_key: str, max_retries: int = 3
    ):
        """Queue with dead-letter exchange for failed messages."""
        exchange = await self.channel.declare_exchange(
            exchange_name, aio_pika.ExchangeType.TOPIC, durable=True
        )

        # Dead letter exchange and queue
        dlx = await self.channel.declare_exchange(
            f"{exchange_name}.dlx", aio_pika.ExchangeType.TOPIC, durable=True
        )
        dlq = await self.channel.declare_queue(
            f"{queue_name}.dlq", durable=True
        )
        await dlq.bind(dlx, routing_key="#")

        # Main queue with DLQ config
        queue = await self.channel.declare_queue(
            queue_name,
            durable=True,
            arguments={
                "x-dead-letter-exchange": f"{exchange_name}.dlx",
                "x-dead-letter-routing-key": routing_key,
                "x-message-ttl": 86400000,  # 24h max
            },
        )
        await queue.bind(exchange, routing_key)
        return queue

    async def consume(self, queue: aio_pika.Queue,
                      handler: Callable[[dict], Awaitable[None]],
                      max_retries: int = 3):
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process(requeue=False):
                    try:
                        body = json.loads(message.body)
                        await handler(body)
                    except Exception as e:
                        retry_count = (message.headers or {}).get(
                            "x-retry-count", 0
                        )
                        if retry_count < max_retries:
                            # Republish with incremented retry count
                            await self._retry_message(
                                message, retry_count + 1
                            )
                        else:
                            # Max retries: goes to DLQ via nack
                            print(f"DLQ: {message.message_id}: {e}")

    async def _retry_message(self, original, retry_count: int):
        """Republish with exponential backoff via TTL."""
        delay_ms = min(1000 * (2 ** retry_count), 60000)
        # Use a delay queue with TTL
        delay_queue = await self.channel.declare_queue(
            f"retry.{delay_ms}ms",
            durable=True,
            arguments={
                "x-message-ttl": delay_ms,
                "x-dead-letter-exchange": "",  # Default exchange
                "x-dead-letter-routing-key": original.routing_key or "",
            },
        )
        headers = dict(original.headers or {})
        headers["x-retry-count"] = retry_count
        await self.channel.default_exchange.publish(
            aio_pika.Message(
                body=original.body,
                headers=headers,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                message_id=original.message_id,
            ),
            routing_key=delay_queue.name,
        )


# --- Event-driven architecture ---

@dataclass
class OrderCreatedEvent:
    order_id: str
    user_id: str
    items: list
    total: float
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()

class EventBus:
    def __init__(self, publisher: RabbitPublisher, exchange_name: str):
        self.publisher = publisher
        self.exchange_name = exchange_name
        self.exchange = None

    async def setup(self):
        self.exchange = await self.publisher.declare_exchange(
            self.exchange_name, "topic"
        )

    async def emit(self, event_type: str, event):
        await self.publisher.publish(
            self.exchange,
            routing_key=event_type,
            message={
                "type": event_type,
                "data": asdict(event) if hasattr(event, "__dataclass_fields__") else event,
            },
        )

# Usage:
# await event_bus.emit("order.created", OrderCreatedEvent(...))
# Consumers bind to "order.*" or "order.created" specifically
```

Patterns:
1. **Work queue** — distribute tasks across workers with prefetch
2. **Pub/Sub** — topic exchange for event fan-out to multiple consumers
3. **Dead letter queue** — capture failed messages for investigation
4. **Retry with backoff** — TTL-based delay queues for automatic retry
5. **Publisher confirms** — ensure messages are persisted before acking'''
    ),
    (
        "architecture/sqs-patterns",
        "Show AWS SQS patterns: standard vs FIFO queues, visibility timeout, batch processing, and Lambda integration.",
        '''AWS SQS patterns for serverless messaging:

```python
import boto3
import json
import hashlib
from datetime import datetime, timezone
from typing import Callable

# --- SQS client wrapper ---

class SQSClient:
    def __init__(self, queue_url: str, region: str = "us-east-1"):
        self.sqs = boto3.client("sqs", region_name=region)
        self.queue_url = queue_url

    def send_message(self, body: dict, group_id: str = None,
                     dedup_id: str = None, delay_seconds: int = 0):
        """Send a message. group_id and dedup_id required for FIFO."""
        params = {
            "QueueUrl": self.queue_url,
            "MessageBody": json.dumps(body, default=str),
            "DelaySeconds": delay_seconds,
        }
        if group_id:
            params["MessageGroupId"] = group_id
        if dedup_id:
            params["MessageDeduplicationId"] = dedup_id
        elif group_id:
            # Auto-generate dedup ID from content
            params["MessageDeduplicationId"] = hashlib.sha256(
                json.dumps(body, sort_keys=True).encode()
            ).hexdigest()

        return self.sqs.send_message(**params)

    def send_batch(self, messages: list[dict], group_id: str = None):
        """Send up to 10 messages in a batch."""
        entries = []
        for i, msg in enumerate(messages[:10]):
            entry = {
                "Id": str(i),
                "MessageBody": json.dumps(msg, default=str),
            }
            if group_id:
                entry["MessageGroupId"] = group_id
                entry["MessageDeduplicationId"] = hashlib.sha256(
                    json.dumps(msg, sort_keys=True).encode()
                ).hexdigest()
            entries.append(entry)

        response = self.sqs.send_message_batch(
            QueueUrl=self.queue_url, Entries=entries
        )
        return {
            "successful": len(response.get("Successful", [])),
            "failed": len(response.get("Failed", [])),
        }

    def receive_and_process(self, handler: Callable[[dict], None],
                             batch_size: int = 10,
                             visibility_timeout: int = 30):
        """Long-poll and process messages."""
        response = self.sqs.receive_message(
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=min(batch_size, 10),
            WaitTimeSeconds=20,  # Long polling (reduces API calls)
            VisibilityTimeout=visibility_timeout,
            AttributeNames=["All"],
        )

        messages = response.get("Messages", [])
        successful = []

        for msg in messages:
            try:
                body = json.loads(msg["Body"])
                handler(body)
                successful.append({
                    "Id": msg["MessageId"],
                    "ReceiptHandle": msg["ReceiptHandle"],
                })
            except Exception as e:
                print(f"Failed {msg['MessageId']}: {e}")
                # Message becomes visible again after visibility timeout

        # Batch delete successful messages
        if successful:
            self.sqs.delete_message_batch(
                QueueUrl=self.queue_url,
                Entries=[
                    {"Id": s["Id"], "ReceiptHandle": s["ReceiptHandle"]}
                    for s in successful
                ],
            )

        return len(successful)


# --- Lambda SQS handler ---

def lambda_handler(event, context):
    """Process SQS messages in Lambda (batch)."""
    batch_item_failures = []

    for record in event["Records"]:
        try:
            body = json.loads(record["body"])
            process_message(body)
        except Exception as e:
            # Report individual failures (partial batch response)
            batch_item_failures.append({
                "itemIdentifier": record["messageId"]
            })

    # Return failures — only failed messages retry
    return {"batchItemFailures": batch_item_failures}


def process_message(body: dict):
    """Business logic for each message."""
    msg_type = body.get("type")
    if msg_type == "order.created":
        handle_order_created(body["data"])
    elif msg_type == "payment.completed":
        handle_payment_completed(body["data"])
    else:
        raise ValueError(f"Unknown message type: {msg_type}")
```

```yaml
# --- CloudFormation for SQS + DLQ ---
Resources:
  OrderQueue:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: orders.fifo
      FifoQueue: true
      ContentBasedDeduplication: true
      VisibilityTimeout: 60
      MessageRetentionPeriod: 1209600  # 14 days
      RedrivePolicy:
        deadLetterTargetArn: !GetAtt OrderDLQ.Arn
        maxReceiveCount: 3

  OrderDLQ:
    Type: AWS::SQS::Queue
    Properties:
      QueueName: orders-dlq.fifo
      FifoQueue: true
      MessageRetentionPeriod: 1209600

  # Lambda trigger
  OrderProcessor:
    Type: AWS::Lambda::EventSourceMapping
    Properties:
      EventSourceArn: !GetAtt OrderQueue.Arn
      FunctionName: !Ref OrderProcessorFunction
      BatchSize: 10
      MaximumBatchingWindowInSeconds: 5
      FunctionResponseTypes:
        - ReportBatchItemFailures
```

SQS vs RabbitMQ:
- **SQS Standard** — at-least-once, unlimited throughput, best-effort ordering
- **SQS FIFO** — exactly-once, ordered within message group, 3000 msg/s
- **RabbitMQ** — flexible routing (topic/fanout), lower latency, more control
- **Both** — DLQ for failed messages, visibility timeout for processing safety'''
    ),
]
"""
