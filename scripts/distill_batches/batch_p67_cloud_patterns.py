"""Cloud — multi-cloud patterns, serverless advanced, and cloud-native design."""

PAIRS = [
    (
        "cloud/serverless-patterns",
        "Show serverless patterns: fan-out, event-driven, API composition, and cold start mitigation.",
        '''Serverless architecture patterns:

```python
import json
import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Callable, Any

logger = logging.getLogger(__name__)


# --- Fan-out / Fan-in pattern ---

# Lambda -> SQS -> Multiple Workers -> DynamoDB aggregate

# Fan-out: split work into parallel chunks
async def fan_out_handler(event: dict) -> dict:
    """Split large job into smaller tasks."""
    import boto3
    sqs = boto3.client("sqs")

    items = event["items"]
    chunk_size = 100
    chunks = [items[i:i+chunk_size] for i in range(0, len(items), chunk_size)]

    # Send each chunk as a separate SQS message
    for i, chunk in enumerate(chunks):
        sqs.send_message(
            QueueUrl=QUEUE_URL,
            MessageBody=json.dumps({
                "job_id": event["job_id"],
                "chunk_index": i,
                "total_chunks": len(chunks),
                "items": chunk,
            }),
            MessageGroupId=event["job_id"],  # FIFO ordering per job
        )

    return {"chunks_created": len(chunks)}


# Fan-in: aggregate results
async def fan_in_handler(event: dict) -> dict:
    """Process chunk and check if all chunks complete."""
    import boto3
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table("job_results")

    chunk = json.loads(event["Records"][0]["body"])
    results = process_chunk(chunk["items"])

    # Atomically increment completed count
    response = table.update_item(
        Key={"job_id": chunk["job_id"]},
        UpdateExpression=(
            "SET completed_chunks = if_not_exists(completed_chunks, :zero) + :one, "
            "results = list_append(if_not_exists(results, :empty), :results)"
        ),
        ExpressionAttributeValues={
            ":one": 1, ":zero": 0,
            ":empty": [], ":results": [results],
        },
        ReturnValues="ALL_NEW",
    )

    completed = response["Attributes"]["completed_chunks"]
    if completed == chunk["total_chunks"]:
        # All chunks done — trigger final aggregation
        await aggregate_results(chunk["job_id"])

    return {"processed": len(results)}


# --- API composition (orchestrator pattern) ---

async def order_handler(event: dict) -> dict:
    """Compose multiple service calls for order processing."""
    import httpx

    body = json.loads(event["body"])

    async with httpx.AsyncClient(timeout=10.0) as client:
        # Parallel independent calls
        inventory_task = client.post(
            f"{INVENTORY_URL}/check",
            json={"items": body["items"]},
        )
        customer_task = client.get(
            f"{CUSTOMER_URL}/customers/{body['customer_id']}",
        )

        inventory_resp, customer_resp = await asyncio.gather(
            inventory_task, customer_task
        )

        if inventory_resp.status_code != 200:
            return {"statusCode": 409, "body": "Items unavailable"}

        # Sequential dependent call
        payment_resp = await client.post(
            f"{PAYMENT_URL}/charge",
            json={
                "customer_id": body["customer_id"],
                "amount": inventory_resp.json()["total"],
                "payment_method": customer_resp.json()["default_payment"],
            },
        )

        if payment_resp.status_code != 200:
            return {"statusCode": 402, "body": "Payment failed"}

    return {
        "statusCode": 201,
        "body": json.dumps({
            "order_id": payment_resp.json()["order_id"],
            "total": inventory_resp.json()["total"],
        }),
    }


# --- Cold start mitigation ---

# 1. Provisioned concurrency (AWS)
# Set via CloudFormation/CDK:
# ProvisionedConcurrencyConfig:
#   ProvisionedConcurrentExecutions: 5

# 2. Module-level initialization (runs once per container)
import boto3

# These are initialized ONCE per Lambda container (warm start reuses)
_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table("orders")
_http_client = None

def get_http_client():
    global _http_client
    if _http_client is None:
        import httpx
        _http_client = httpx.Client(timeout=10.0)
    return _http_client


# 3. Warming function
def warmer_handler(event, context):
    """Keep function warm with scheduled CloudWatch event."""
    if event.get("source") == "aws.events":
        logger.info("Warm-up ping")
        return {"statusCode": 200, "body": "warm"}
    return main_handler(event, context)


# --- Step Functions (state machine orchestration) ---

# Instead of chaining Lambdas directly, use Step Functions:
#
# {
#   "StartAt": "ValidateOrder",
#   "States": {
#     "ValidateOrder": {
#       "Type": "Task",
#       "Resource": "arn:aws:lambda:...:validate",
#       "Next": "CheckInventory",
#       "Catch": [{
#         "ErrorEquals": ["ValidationError"],
#         "Next": "OrderFailed"
#       }]
#     },
#     "CheckInventory": {
#       "Type": "Task",
#       "Resource": "arn:aws:lambda:...:check_inventory",
#       "Next": "ProcessPayment",
#       "Retry": [{
#         "ErrorEquals": ["States.TaskFailed"],
#         "IntervalSeconds": 2,
#         "MaxAttempts": 3,
#         "BackoffRate": 2
#       }]
#     },
#     "ProcessPayment": {
#       "Type": "Task",
#       "Resource": "arn:aws:lambda:...:process_payment",
#       "Next": "OrderComplete"
#     },
#     "OrderComplete": {
#       "Type": "Succeed"
#     },
#     "OrderFailed": {
#       "Type": "Fail",
#       "Error": "OrderProcessingFailed"
#     }
#   }
# }
```

Serverless patterns:
1. **Fan-out/fan-in** — split work into SQS messages, aggregate in DynamoDB
2. **API composition** — orchestrate parallel/sequential service calls in one Lambda
3. **Module-level init** — reuse DB clients across warm invocations
4. **Provisioned concurrency** — pre-warm containers for latency-sensitive endpoints
5. **Step Functions** — state machine for multi-step workflows with retry/catch'''
    ),
    (
        "cloud/infrastructure-as-code",
        "Show CDK patterns: constructs, stacks, environment config, and cross-stack references.",
        '''AWS CDK infrastructure patterns:

```python
from aws_cdk import (
    Stack, Duration, RemovalPolicy, CfnOutput,
    aws_lambda as lambda_,
    aws_apigateway as apigw,
    aws_dynamodb as dynamodb,
    aws_sqs as sqs,
    aws_sns as sns,
    aws_s3 as s3,
    aws_iam as iam,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda_event_sources as event_sources,
)
from constructs import Construct
from dataclasses import dataclass


# --- Environment config ---

@dataclass
class EnvConfig:
    account: str
    region: str
    stage: str  # dev, staging, prod
    domain: str
    log_retention_days: int = 30

    @property
    def is_prod(self) -> bool:
        return self.stage == "prod"

    @property
    def removal_policy(self) -> RemovalPolicy:
        return RemovalPolicy.RETAIN if self.is_prod else RemovalPolicy.DESTROY


# --- Reusable construct (L3) ---

class APIFunction(Construct):
    """Lambda function with API Gateway, DLQ, and monitoring."""

    def __init__(self, scope: Construct, id: str, *,
                 handler: str,
                 code_path: str,
                 environment: dict = None,
                 memory_size: int = 256,
                 timeout: Duration = Duration.seconds(30),
                 config: EnvConfig):
        super().__init__(scope, id)

        # Dead letter queue
        self.dlq = sqs.Queue(self, "DLQ",
            retention_period=Duration.days(14),
        )

        # Lambda function
        self.function = lambda_.Function(self, "Function",
            runtime=lambda_.Runtime.PYTHON_3_12,
            handler=handler,
            code=lambda_.Code.from_asset(code_path),
            memory_size=memory_size,
            timeout=timeout,
            environment={
                "STAGE": config.stage,
                "LOG_LEVEL": "DEBUG" if not config.is_prod else "INFO",
                **(environment or {}),
            },
            dead_letter_queue=self.dlq,
            tracing=lambda_.Tracing.ACTIVE,
            insights_version=lambda_.LambdaInsightsVersion.VERSION_1_0_229_0,
        )

        # Alarm on DLQ messages
        if config.is_prod:
            from aws_cdk import aws_cloudwatch as cw
            cw.Alarm(self, "DLQAlarm",
                metric=self.dlq.metric_approximate_number_of_messages_visible(),
                threshold=1,
                evaluation_periods=1,
            )


# --- Application stack ---

class APIStack(Stack):
    def __init__(self, scope: Construct, id: str, *,
                 config: EnvConfig, **kwargs):
        super().__init__(scope, id, **kwargs)

        # DynamoDB table
        table = dynamodb.Table(self, "OrdersTable",
            table_name=f"{config.stage}-orders",
            partition_key=dynamodb.Attribute(
                name="PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(
                name="SK", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=config.removal_policy,
            point_in_time_recovery=config.is_prod,
            stream=dynamodb.StreamViewType.NEW_AND_OLD_IMAGES,
        )

        # Add GSI
        table.add_global_secondary_index(
            index_name="GSI1",
            partition_key=dynamodb.Attribute(
                name="GSI1PK", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(
                name="GSI1SK", type=dynamodb.AttributeType.STRING),
        )

        # API Lambda
        api_fn = APIFunction(self, "OrderAPI",
            handler="handlers.api.handler",
            code_path="lambda/",
            environment={"TABLE_NAME": table.table_name},
            config=config,
        )
        table.grant_read_write_data(api_fn.function)

        # API Gateway
        api = apigw.RestApi(self, "API",
            rest_api_name=f"{config.stage}-orders-api",
            deploy_options=apigw.StageOptions(
                stage_name=config.stage,
                throttling_rate_limit=1000,
                throttling_burst_limit=500,
            ),
        )

        orders = api.root.add_resource("orders")
        orders.add_method("GET", apigw.LambdaIntegration(api_fn.function))
        orders.add_method("POST", apigw.LambdaIntegration(api_fn.function))

        order = orders.add_resource("{id}")
        order.add_method("GET", apigw.LambdaIntegration(api_fn.function))

        # Event processor (DynamoDB stream -> Lambda)
        processor = APIFunction(self, "StreamProcessor",
            handler="handlers.stream.handler",
            code_path="lambda/",
            config=config,
        )
        processor.function.add_event_source(
            event_sources.DynamoEventSource(table,
                starting_position=lambda_.StartingPosition.TRIM_HORIZON,
                batch_size=100,
                retry_attempts=3,
            )
        )

        # Scheduled task
        cleanup_fn = APIFunction(self, "Cleanup",
            handler="handlers.cleanup.handler",
            code_path="lambda/",
            environment={"TABLE_NAME": table.table_name},
            config=config,
        )
        table.grant_read_write_data(cleanup_fn.function)

        events.Rule(self, "CleanupSchedule",
            schedule=events.Schedule.rate(Duration.hours(1)),
            targets=[targets.LambdaFunction(cleanup_fn.function)],
        )

        # Outputs
        CfnOutput(self, "ApiUrl", value=api.url)
        CfnOutput(self, "TableName", value=table.table_name)
```

CDK patterns:
1. **L3 constructs** — reusable building blocks (Lambda + DLQ + monitoring)
2. **Environment config** — dataclass drives behavior per stage (dev/prod)
3. **`RemovalPolicy`** — RETAIN in prod, DESTROY in dev for easy cleanup
4. **DynamoDB streams** — event-driven processing from table changes
5. **Cross-stack outputs** — `CfnOutput` for service discovery between stacks'''
    ),
    (
        "cloud/twelve-factor",
        "Show twelve-factor app patterns: config, logging, backing services, and disposability.",
        '''Twelve-factor app patterns:

```python
import os
import sys
import json
import logging
import signal
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


# --- Factor 3: Config from environment ---

@dataclass
class AppConfig:
    """Load all config from environment variables."""

    # Required
    database_url: str = field(
        default_factory=lambda: os.environ["DATABASE_URL"]
    )
    redis_url: str = field(
        default_factory=lambda: os.environ["REDIS_URL"]
    )
    secret_key: str = field(
        default_factory=lambda: os.environ["SECRET_KEY"]
    )

    # Optional with defaults
    port: int = field(
        default_factory=lambda: int(os.getenv("PORT", "8000"))
    )
    workers: int = field(
        default_factory=lambda: int(os.getenv("WEB_CONCURRENCY", "4"))
    )
    debug: bool = field(
        default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true"
    )
    log_level: str = field(
        default_factory=lambda: os.getenv("LOG_LEVEL", "INFO")
    )

    # Feature flags
    enable_cache: bool = field(
        default_factory=lambda: os.getenv("ENABLE_CACHE", "true").lower() == "true"
    )

    def validate(self):
        """Fail fast on missing required config."""
        required = ["database_url", "redis_url", "secret_key"]
        missing = [f for f in required if not getattr(self, f)]
        if missing:
            raise ValueError(f"Missing required config: {missing}")


# --- Factor 11: Logs as event streams ---

def setup_logging(level: str = "INFO"):
    """Structured JSON logging to stdout."""
    import logging

    class JSONFormatter(logging.Formatter):
        def format(self, record):
            log_entry = {
                "timestamp": self.formatTime(record),
                "level": record.levelname,
                "message": record.getMessage(),
                "logger": record.name,
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
            }
            if record.exc_info:
                log_entry["exception"] = self.formatException(record.exc_info)
            # Add extra fields
            for key in record.__dict__:
                if key not in logging.LogRecord(
                    "", 0, "", 0, "", (), None
                ).__dict__ and key != "message":
                    log_entry[key] = record.__dict__[key]
            return json.dumps(log_entry)

    handler = logging.StreamHandler(sys.stdout)  # stdout, not stderr
    handler.setFormatter(JSONFormatter())

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper()))
    root.handlers = [handler]


# --- Factor 9: Disposability (fast startup, graceful shutdown) ---

class GracefulServer:
    """Server with graceful shutdown handling."""

    def __init__(self):
        self._running = True
        self._connections = set()
        self._tasks = set()

    def setup_signals(self):
        """Handle SIGTERM for graceful shutdown."""
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

    def _handle_signal(self, signum, frame):
        logger.info("Received signal %d, shutting down gracefully", signum)
        self._running = False

    async def shutdown(self, timeout: float = 30.0):
        """Graceful shutdown: finish in-flight, reject new."""
        import asyncio

        logger.info("Draining %d connections", len(self._connections))

        # Stop accepting new connections
        self._running = False

        # Wait for in-flight requests (with timeout)
        if self._tasks:
            done, pending = await asyncio.wait(
                self._tasks, timeout=timeout
            )
            if pending:
                logger.warning("Cancelling %d stuck tasks", len(pending))
                for task in pending:
                    task.cancel()

        # Close resources
        await self._cleanup()
        logger.info("Shutdown complete")

    async def _cleanup(self):
        """Close database pools, flush buffers, etc."""
        pass


# --- Factor 4: Backing services as attached resources ---

def create_backing_services(config: AppConfig) -> dict:
    """Initialize backing services from config URLs."""
    services = {}

    # Database (Factor 4: treat as attached resource)
    import asyncpg
    services["db"] = asyncpg.create_pool(
        dsn=config.database_url,
        min_size=2,
        max_size=config.workers * 2,
    )

    # Cache
    if config.enable_cache:
        import redis.asyncio as redis
        services["cache"] = redis.from_url(
            config.redis_url,
            decode_responses=True,
        )

    return services


# --- Factor 12: Admin processes ---

# Admin tasks run as one-off processes using the same codebase:
# python -m myapp.admin migrate
# python -m myapp.admin seed --count 1000
# python -m myapp.admin cleanup --older-than 30d

# NOT as special endpoints in the web process
```

Twelve-factor patterns:
1. **Config from env** — `os.environ["DATABASE_URL"]`, never in code or files
2. **Structured logging** — JSON to stdout, let log aggregator handle routing
3. **Graceful shutdown** — SIGTERM handler drains connections before exit
4. **Backing services** — database/cache as swappable URLs, not hardcoded
5. **Admin processes** — one-off tasks use same code, run as separate processes'''
    ),
]
"""
