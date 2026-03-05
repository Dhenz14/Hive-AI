"""Serverless patterns: Lambda best practices, cold start mitigation, step functions, event bridges."""

PAIRS = [
    (
        "serverless/lambda-best-practices",
        "What are the best practices for writing production AWS Lambda functions in Python, including cold start optimization, structured responses, and proper error handling?",
        '''AWS Lambda functions require specific architectural patterns to handle cold starts, maximize concurrency, and maintain observability. Here is a production-grade Lambda function structure with all best practices applied.

```python
"""Production AWS Lambda function with best practices (2026)."""

import json
import os
import time
import logging
import uuid
from functools import lru_cache
from typing import Any
from dataclasses import dataclass, asdict
from datetime import datetime, timezone

import boto3
from botocore.config import Config as BotoConfig
from aws_lambda_powertools import Logger, Tracer, Metrics
from aws_lambda_powertools.event_handler import APIGatewayRestResolver
from aws_lambda_powertools.logging import correlation_paths
from aws_lambda_powertools.metrics import MetricUnit
from aws_lambda_powertools.utilities.typing import LambdaContext
from aws_lambda_powertools.utilities.validation import (
    validate, SchemaValidationError,
)
from aws_lambda_powertools.utilities.idempotency import (
    IdempotencyConfig,
    DynamoDBPersistenceLayer,
    idempotent_function,
)
from aws_lambda_powertools.utilities.parameters import get_parameter


# ── Module-level initialization (runs once during cold start) ──

logger = Logger(service="order-service")
tracer = Tracer(service="order-service")
metrics = Metrics(namespace="OrderService", service="order-service")

# Reuse connections across invocations via module-level clients
BOTO_CONFIG = BotoConfig(
    retries={"max_attempts": 3, "mode": "adaptive"},
    connect_timeout=5,
    read_timeout=10,
)


@lru_cache(maxsize=1)
def get_dynamodb_table():
    """Lazy-initialize DynamoDB table resource (cached)."""
    dynamodb = boto3.resource("dynamodb", config=BOTO_CONFIG)
    return dynamodb.Table(os.environ["ORDERS_TABLE"])


@lru_cache(maxsize=1)
def get_sqs_client():
    return boto3.client("sqs", config=BOTO_CONFIG)


@lru_cache(maxsize=1)
def get_config() -> dict:
    """Load config from SSM Parameter Store (cached for warm starts)."""
    raw = get_parameter(
        os.environ.get("CONFIG_PARAM", "/order-service/config"),
        transform="json",
        max_age=300,
    )
    return raw


# ── Idempotency Setup ─────────────────────────────────────────

persistence = DynamoDBPersistenceLayer(
    table_name=os.environ.get("IDEMPOTENCY_TABLE", "idempotency-store")
)
idempotency_config = IdempotencyConfig(
    expires_after_seconds=3600,
    event_key_jmespath="body.order_id",
)


# ── Data Models ────────────────────────────────────────────────

@dataclass
class OrderRequest:
    customer_id: str
    items: list[dict[str, Any]]
    shipping_address: str
    payment_method: str

    @classmethod
    def from_event(cls, body: dict) -> "OrderRequest":
        return cls(
            customer_id=body["customer_id"],
            items=body["items"],
            shipping_address=body["shipping_address"],
            payment_method=body["payment_method"],
        )


@dataclass
class ApiResponse:
    status_code: int
    body: dict[str, Any]
    headers: dict[str, str] | None = None

    def to_lambda_response(self) -> dict:
        return {
            "statusCode": self.status_code,
            "headers": {
                "Content-Type": "application/json",
                "X-Request-Id": logger.get_correlation_id() or "",
                **(self.headers or {}),
            },
            "body": json.dumps(self.body, default=str),
        }


# ── Business Logic (separate from handler) ────────────────────

@tracer.capture_method
@idempotent_function(
    data_keyword_argument="order_data",
    config=idempotency_config,
    persistence_store=persistence,
)
async def process_order(order_data: dict) -> dict:
    """Process an order -- idempotent and traceable."""
    request = OrderRequest.from_event(order_data)
    order_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    total = sum(
        item["price"] * item["quantity"] for item in request.items
    )

    order_record = {
        "order_id": order_id,
        "customer_id": request.customer_id,
        "items": request.items,
        "total": str(total),
        "status": "pending",
        "shipping_address": request.shipping_address,
        "created_at": now,
    }

    # Write to DynamoDB
    table = get_dynamodb_table()
    table.put_item(Item=order_record)

    # Publish event to SQS for downstream processing
    sqs = get_sqs_client()
    sqs.send_message(
        QueueUrl=os.environ["ORDER_EVENTS_QUEUE"],
        MessageBody=json.dumps({
            "event_type": "OrderCreated",
            "order_id": order_id,
            "customer_id": request.customer_id,
            "total": str(total),
            "timestamp": now,
        }),
        MessageGroupId=request.customer_id,
        MessageDeduplicationId=order_id,
    )

    metrics.add_metric(
        name="OrderCreated", unit=MetricUnit.Count, value=1
    )
    metrics.add_metric(
        name="OrderValue", unit=MetricUnit.Count, value=float(total)
    )

    return {"order_id": order_id, "status": "pending", "total": str(total)}


# ── Lambda Handler ─────────────────────────────────────────────

@logger.inject_lambda_context(
    correlation_id_path=correlation_paths.API_GATEWAY_REST
)
@tracer.capture_lambda_handler
@metrics.log_metrics(capture_cold_start_metric=True)
def handler(event: dict, context: LambdaContext) -> dict:
    """Main Lambda entry point."""
    start = time.monotonic()
    remaining_ms = context.get_remaining_time_in_millis()

    logger.info("Processing request", extra={
        "path": event.get("path"),
        "method": event.get("httpMethod"),
        "remaining_ms": remaining_ms,
    })

    try:
        body = json.loads(event.get("body", "{}"))
        result = process_order(order_data=body)

        elapsed = (time.monotonic() - start) * 1000
        metrics.add_metric(
            name="ProcessingTime", unit=MetricUnit.Milliseconds,
            value=elapsed,
        )

        return ApiResponse(
            status_code=201,
            body={"data": result, "request_id": context.aws_request_id},
        ).to_lambda_response()

    except SchemaValidationError as exc:
        logger.warning("Validation error", extra={"error": str(exc)})
        return ApiResponse(
            status_code=400,
            body={"error": "Invalid request", "details": str(exc)},
        ).to_lambda_response()

    except Exception as exc:
        logger.exception("Unhandled error processing order")
        metrics.add_metric(
            name="OrderError", unit=MetricUnit.Count, value=1
        )
        return ApiResponse(
            status_code=500,
            body={"error": "Internal server error"},
        ).to_lambda_response()
```

Cold start optimization strategies:

| Strategy | Impact | Complexity | Notes |
|----------|--------|------------|-------|
| Module-level init | High | Low | SDK clients, DB connections |
| lru_cache singletons | High | Low | Cache expensive resources |
| Provisioned Concurrency | Highest | Low (cost) | Eliminates cold starts |
| SnapStart (Java/Python) | High | Medium | Snapshot warm state |
| Minimize package size | Medium | Medium | Prune unused deps |
| Lazy imports | Medium | Low | Import inside handler |
| ARM64 (Graviton) | Medium | Low | 20% cheaper, faster |

Key patterns:
- Initialize SDK clients at module level so they persist across warm invocations
- Use lru_cache for singleton resources (DB connections, config)
- Separate business logic from the handler for testability
- Use Powertools for structured logging, tracing, metrics, and idempotency
- Always set timeouts on boto3 clients to prevent hanging
- Track cold starts as a metric to monitor provisioned concurrency needs
- Make all operations idempotent -- Lambda may retry your function
'''
    ),
    (
        "serverless/step-functions",
        "How do I design complex workflows using AWS Step Functions with error handling, parallel execution, and human approval steps?",
        '''AWS Step Functions orchestrate multi-step serverless workflows with built-in error handling, retries, and state management. Here is a production order fulfillment workflow.

```python
"""AWS Step Functions workflow definition using CDK (Python)."""

from aws_cdk import (
    Stack, Duration, RemovalPolicy,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    aws_lambda as lambda_,
    aws_sns as sns,
    aws_sns_subscriptions as subs,
    aws_dynamodb as dynamodb,
    aws_logs as logs,
)
from constructs import Construct


class OrderFulfillmentWorkflow(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── Lambda Functions ───────────────────────────────────
        validate_fn = self._create_lambda("ValidateOrder", "validate")
        inventory_fn = self._create_lambda("CheckInventory", "inventory")
        payment_fn = self._create_lambda("ProcessPayment", "payment")
        shipping_fn = self._create_lambda("CreateShipment", "shipping")
        notify_fn = self._create_lambda("NotifyCustomer", "notify")
        refund_fn = self._create_lambda("ProcessRefund", "refund")
        cancel_fn = self._create_lambda("CancelOrder", "cancel")

        # ── SNS for human approval ─────────────────────────────
        approval_topic = sns.Topic(self, "ApprovalTopic",
            display_name="Order Approval Requests",
        )

        # ── Step 1: Validate Order ─────────────────────────────
        validate_step = tasks.LambdaInvoke(
            self, "ValidateOrderStep",
            lambda_function=validate_fn,
            result_path="$.validation",
            retry_on_service_exceptions=True,
        )
        validate_step.add_retry(
            errors=["States.TaskFailed"],
            interval=Duration.seconds(2),
            max_attempts=3,
            backoff_rate=2.0,
        )

        # ── Step 2: Parallel inventory + fraud check ───────────
        check_inventory = tasks.LambdaInvoke(
            self, "CheckInventoryStep",
            lambda_function=inventory_fn,
            result_path="$.inventory",
        )
        check_inventory.add_retry(
            errors=["InsufficientInventoryError"],
            interval=Duration.seconds(5),
            max_attempts=2,
        )

        fraud_check = tasks.LambdaInvoke(
            self, "FraudCheckStep",
            lambda_function=self._create_lambda(
                "FraudCheck", "fraud"
            ),
            result_path="$.fraud",
        )

        parallel_checks = sfn.Parallel(
            self, "ParallelChecks",
            result_path="$.checks",
        )
        parallel_checks.branch(check_inventory)
        parallel_checks.branch(fraud_check)
        parallel_checks.add_catch(
            handler=self._create_fail_state("ChecksFailed"),
            errors=["States.ALL"],
            result_path="$.error",
        )

        # ── Step 3: High-value order approval ──────────────────
        needs_approval = sfn.Choice(self, "NeedsApproval")

        wait_for_approval = tasks.SnsPublish(
            self, "RequestApproval",
            topic=approval_topic,
            message=sfn.TaskInput.from_json_path_at(
                "States.Format('Order {} needs approval. "
                "Total: ${}', $.order_id, $.total)"
            ),
            result_path="$.approval_request",
        )

        approval_callback = sfn.CustomState(
            self, "WaitForApproval",
            state_json={
                "Type": "Task",
                "Resource": "arn:aws:states:::sqs:sendMessage.waitForTaskToken",
                "Parameters": {
                    "QueueUrl": "${ApprovalQueueUrl}",
                    "MessageBody": {
                        "TaskToken.$": "$$.Task.Token",
                        "OrderId.$": "$.order_id",
                        "Total.$": "$.total",
                    },
                },
                "TimeoutSeconds": 86400,
                "ResultPath": "$.approval",
            },
        )

        # ── Step 4: Process Payment ────────────────────────────
        process_payment = tasks.LambdaInvoke(
            self, "ProcessPaymentStep",
            lambda_function=payment_fn,
            result_path="$.payment",
        )
        process_payment.add_retry(
            errors=["PaymentGatewayTimeout"],
            interval=Duration.seconds(5),
            max_attempts=3,
            backoff_rate=2.0,
        )
        process_payment.add_catch(
            handler=self._compensation_chain(cancel_fn, notify_fn),
            errors=["PaymentDeclinedError"],
            result_path="$.payment_error",
        )

        # ── Step 5: Create Shipment ────────────────────────────
        create_shipment = tasks.LambdaInvoke(
            self, "CreateShipmentStep",
            lambda_function=shipping_fn,
            result_path="$.shipment",
        )
        create_shipment.add_catch(
            handler=self._compensation_chain(refund_fn, cancel_fn),
            errors=["States.ALL"],
            result_path="$.shipping_error",
        )

        # ── Step 6: Notify Customer ────────────────────────────
        notify_customer = tasks.LambdaInvoke(
            self, "NotifyCustomerStep",
            lambda_function=notify_fn,
            result_path="$.notification",
        )

        # ── Step 7: Update Order Status in DynamoDB ────────────
        update_status = tasks.DynamoPutItem(
            self, "UpdateOrderComplete",
            table=dynamodb.Table.from_table_name(
                self, "OrdersTable", "orders"
            ),
            item={
                "order_id": tasks.DynamoAttributeValue.from_string(
                    sfn.JsonPath.string_at("$.order_id")
                ),
                "status": tasks.DynamoAttributeValue.from_string(
                    "fulfilled"
                ),
            },
            result_path="$.db_update",
        )

        # ── Success / Failure States ──────────────────────────
        success = sfn.Succeed(self, "OrderFulfilled")
        failed = sfn.Fail(
            self, "OrderFailed",
            cause="Order processing failed",
            error="OrderFulfillmentError",
        )

        # ── Wire the State Machine ─────────────────────────────
        needs_approval.when(
            sfn.Condition.number_greater_than("$.total", 1000),
            wait_for_approval.next(approval_callback),
        ).otherwise(process_payment)

        approval_callback.next(process_payment)

        definition = (
            validate_step
            .next(parallel_checks)
            .next(needs_approval)
        )
        process_payment.next(create_shipment)
        create_shipment.next(notify_customer)
        notify_customer.next(update_status)
        update_status.next(success)

        # ── State Machine with Logging ─────────────────────────
        log_group = logs.LogGroup(
            self, "StepFunctionLogs",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        sfn.StateMachine(
            self, "OrderFulfillmentSM",
            definition_body=sfn.DefinitionBody.from_chainable(
                definition
            ),
            timeout=Duration.hours(25),
            tracing_enabled=True,
            logs=sfn.LogOptions(
                destination=log_group,
                level=sfn.LogLevel.ALL,
            ),
        )

    def _create_lambda(self, name: str, handler_mod: str) -> lambda_.Function:
        return lambda_.Function(
            self, name,
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler=f"handlers.{handler_mod}.handler",
            code=lambda_.Code.from_asset("lambda/"),
            timeout=Duration.seconds(30),
            memory_size=256,
            architecture=lambda_.Architecture.ARM_64,
            tracing=lambda_.Tracing.ACTIVE,
        )

    def _create_fail_state(self, name: str) -> sfn.Fail:
        return sfn.Fail(self, name, error=name)

    def _compensation_chain(self, *fns) -> sfn.Chain:
        steps = [
            tasks.LambdaInvoke(
                self, f"Compensate{fn.node.id}",
                lambda_function=fn,
                result_path=sfn.JsonPath.DISCARD,
            )
            for fn in fns
        ]
        chain = steps[0]
        for step in steps[1:]:
            chain = chain.next(step)
        return chain.next(sfn.Fail(self, "CompensationComplete"))
```

Step Functions patterns comparison:

| Pattern | Use Case | Complexity | Notes |
|---------|----------|------------|-------|
| Sequential | Simple pipelines | Low | Linear A then B then C |
| Parallel | Independent tasks | Medium | Fan-out / fan-in |
| Choice | Conditional branching | Medium | Route based on data |
| Map | Batch processing | Medium | Process array items |
| Wait for Callback | Human approval | High | External signal to resume |
| Retry + Catch | Error resilience | Low | Built-in retry with backoff |

Key patterns:
- Use Parallel state for independent checks (inventory + fraud) to reduce latency
- Add retry with exponential backoff on every task that calls external services
- Catch errors and route to compensation chains for saga-like rollback
- Use waitForTaskToken for human approval with configurable timeout
- Enable X-Ray tracing and CloudWatch logging on every state machine
- Keep individual Lambda functions small and focused on one task
- Use result_path to preserve the full context object through the workflow
'''
    ),
    (
        "serverless/cold-start-mitigation",
        "What are the most effective strategies for mitigating Lambda cold starts in Python, including provisioned concurrency, SnapStart, and code optimization?",
        '''Cold starts occur when Lambda creates a new execution environment. In Python, they typically add 200-800ms depending on package size and initialization. Here are battle-tested mitigation strategies.

```python
"""Cold start mitigation strategies for AWS Lambda (Python 3.13)."""

# ── Strategy 1: Lazy Initialization with Module Cache ──────────

import os
import json
from functools import lru_cache
from typing import Any

# GOOD: Module-level constants (no I/O, no cost)
TABLE_NAME = os.environ.get("TABLE_NAME", "orders")
REGION = os.environ.get("AWS_REGION", "us-east-1")
IS_COLD_START = True


# GOOD: Lazy singleton pattern -- only created on first use
class _ServiceContainer:
    """Lazy-initialized service container for Lambda."""

    def __init__(self):
        self._dynamodb = None
        self._s3 = None
        self._ssm_cache: dict[str, Any] = {}
        self._config: dict | None = None

    @property
    def dynamodb(self):
        if self._dynamodb is None:
            import boto3
            from botocore.config import Config
            self._dynamodb = boto3.resource(
                "dynamodb",
                config=Config(
                    retries={"max_attempts": 2, "mode": "adaptive"},
                    connect_timeout=3,
                    read_timeout=5,
                    max_pool_connections=10,
                ),
            )
        return self._dynamodb

    @property
    def s3(self):
        if self._s3 is None:
            import boto3
            self._s3 = boto3.client("s3")
        return self._s3

    @property
    def config(self) -> dict:
        if self._config is None:
            from aws_lambda_powertools.utilities.parameters import (
                get_parameter,
            )
            raw = get_parameter("/my-service/config", transform="json")
            self._config = raw
        return self._config


services = _ServiceContainer()


# ── Strategy 2: Minimize Import Footprint ──────────────────────

# BAD: Top-level heavy imports slow cold start
# import pandas as pd
# import numpy as np
# from PIL import Image

# GOOD: Conditional / deferred imports
def process_csv(data: bytes) -> list[dict]:
    """Import pandas only when needed."""
    import pandas as pd
    from io import BytesIO
    df = pd.read_csv(BytesIO(data))
    return df.to_dict(orient="records")


# ── Strategy 3: Connection Pooling with Keep-Alive ─────────────

def get_http_session():
    """Reusable HTTP session with connection pooling."""
    import urllib3
    from botocore.httpsession import URLLib3Session

    # botocore already uses urllib3; configure keep-alive
    http = urllib3.PoolManager(
        maxsize=10,
        retries=urllib3.Retry(
            total=3, backoff_factor=0.1,
            status_forcelist=[500, 502, 503],
        ),
        timeout=urllib3.Timeout(connect=3.0, read=10.0),
    )
    return http


# ── Strategy 4: Provisioned Concurrency via CDK ───────────────

def create_provisioned_lambda_cdk():
    """CDK code for provisioned concurrency setup."""
    cdk_code = """
from aws_cdk import (
    Stack, Duration,
    aws_lambda as lambda_,
    aws_applicationautoscaling as autoscaling,
)
from constructs import Construct

class OptimizedLambdaStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        fn = lambda_.Function(
            self, "OptimizedFn",
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler="handler.main",
            code=lambda_.Code.from_asset("lambda/"),
            memory_size=1024,       # More memory = more CPU
            timeout=Duration.seconds(30),
            architecture=lambda_.Architecture.ARM_64,
            environment={
                "POWERTOOLS_SERVICE_NAME": "my-service",
            },
        )

        # Create an alias for provisioned concurrency
        alias = fn.add_alias("live")

        # Set provisioned concurrency
        scaling = alias.add_auto_scaling(
            min_capacity=5,
            max_capacity=50,
        )

        # Scale based on utilization
        scaling.scale_on_utilization(
            utilization_target=0.7,
            disable_scale_in=False,
        )

        # Schedule-based scaling for known traffic patterns
        scaling.scale_on_schedule(
            "ScaleUpMorning",
            schedule=autoscaling.Schedule.cron(
                hour="8", minute="0"
            ),
            min_capacity=20,
        )
        scaling.scale_on_schedule(
            "ScaleDownNight",
            schedule=autoscaling.Schedule.cron(
                hour="22", minute="0"
            ),
            min_capacity=5,
        )
"""
    return cdk_code


# ── Strategy 5: Optimized Handler with Timing ─────────────────

def handler(event: dict, context) -> dict:
    """Handler that tracks cold start timing."""
    import time
    global IS_COLD_START

    start = time.monotonic()
    cold = IS_COLD_START
    IS_COLD_START = False

    try:
        # Business logic
        table = services.dynamodb.Table(TABLE_NAME)
        result = table.get_item(
            Key={"id": event.get("id", "default")}
        )
        item = result.get("Item", {})

        elapsed_ms = (time.monotonic() - start) * 1000

        return {
            "statusCode": 200,
            "body": json.dumps({
                "data": item,
                "meta": {
                    "cold_start": cold,
                    "duration_ms": round(elapsed_ms, 2),
                    "remaining_ms": context.get_remaining_time_in_millis(),
                },
            }, default=str),
        }
    except Exception as exc:
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(exc)}),
        }


# ── Strategy 6: Lambda Layer Optimization ──────────────────────

# Dockerfile for creating optimized Lambda layers
LAYER_DOCKERFILE = """
FROM public.ecr.aws/lambda/python:3.13

# Install only what you need, compiled for Lambda
RUN pip install --no-cache-dir \\
    --platform manylinux2014_aarch64 \\
    --only-binary=:all: \\
    --target /opt/python \\
    boto3 \\
    aws-lambda-powertools[all] \\
    pydantic

# Strip debug symbols and .pyc caches
RUN find /opt/python -name "*.dist-info" -exec rm -rf {} + 2>/dev/null; \\
    find /opt/python -name "__pycache__" -exec rm -rf {} + 2>/dev/null; \\
    find /opt/python -name "*.so" -exec strip --strip-debug {} + 2>/dev/null; \\
    exit 0
"""


# ── Strategy 7: Pre-warm Critical Paths ────────────────────────

def prewarm_handler(event: dict, context) -> dict:
    """Scheduled pre-warm function (runs every 5 min)."""
    import concurrent.futures
    import boto3

    client = boto3.client("lambda")
    functions_to_warm = [
        "order-service-create",
        "order-service-get",
        "payment-service-process",
    ]

    def invoke_warm(fn_name: str) -> str:
        client.invoke(
            FunctionName=fn_name,
            InvocationType="Event",
            Payload=json.dumps({"__prewarm": True}),
        )
        return f"Warmed {fn_name}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(invoke_warm, functions_to_warm))

    return {"warmed": results}
```

Cold start impact by strategy:

| Strategy | Cold Start Reduction | Cost Impact | Effort |
|----------|---------------------|-------------|--------|
| Module-level init | 30-50% | None | Low |
| Lazy imports | 10-30% | None | Low |
| ARM64 (Graviton) | 10-20% | -20% cost | None |
| Smaller packages | 20-40% | None | Medium |
| Lambda Layers | 10-20% | None | Medium |
| More memory (1024MB+) | 15-25% | +cost | None |
| Provisioned Concurrency | 100% | +cost | Low |
| SnapStart | 80-90% | None | Low |
| Pre-warming (scheduled) | 70-80% | +cost | Medium |

Key patterns:
- Use lazy singletons for SDK clients -- create on first use, reuse on warm starts
- Move heavy imports (pandas, PIL, etc.) inside functions that need them
- ARM64 (Graviton2) gives 20% better price-performance with faster cold starts
- Provisioned concurrency eliminates cold starts but costs per-hour per instance
- Strip Lambda layers of debug symbols, dist-info, and __pycache__ directories
- Track cold_start as a metric and alert when the cold start ratio exceeds your SLO
- Use auto-scaling on provisioned concurrency to match traffic patterns
'''
    ),
    (
        "serverless/event-bridge",
        "How do I design an event-driven serverless architecture using Amazon EventBridge with schema discovery, content filtering, and cross-account patterns?",
        '''Amazon EventBridge is the backbone of event-driven serverless architectures. It provides schema discovery, content-based filtering, and cross-account event routing. Here is a comprehensive implementation.

```python
"""EventBridge event-driven architecture with CDK."""

import json
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, asdict, field
from typing import Any
from enum import Enum

from aws_cdk import (
    Stack, Duration, RemovalPolicy,
    aws_events as events,
    aws_events_targets as targets,
    aws_lambda as lambda_,
    aws_sqs as sqs,
    aws_sns as sns,
    aws_iam as iam,
    aws_logs as logs,
    aws_pipes as pipes,
)
from constructs import Construct


# ── Event Definitions ──────────────────────────────────────────

class EventSource(str, Enum):
    ORDER_SERVICE = "com.myapp.orders"
    PAYMENT_SERVICE = "com.myapp.payments"
    INVENTORY_SERVICE = "com.myapp.inventory"
    SHIPPING_SERVICE = "com.myapp.shipping"


@dataclass
class CloudEvent:
    """CloudEvents-compliant event envelope."""
    source: str
    detail_type: str
    detail: dict[str, Any]
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    time: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    version: str = "1.0"
    correlation_id: str = ""
    trace_id: str = ""

    def to_eventbridge(self) -> dict:
        return {
            "Source": self.source,
            "DetailType": self.detail_type,
            "Detail": json.dumps({
                **self.detail,
                "metadata": {
                    "event_id": self.id,
                    "correlation_id": self.correlation_id,
                    "trace_id": self.trace_id,
                    "version": self.version,
                    "timestamp": self.time,
                },
            }),
        }


# ── Event Publisher ────────────────────────────────────────────

class EventPublisher:
    """Publish events to EventBridge with batching."""

    def __init__(self, bus_name: str = "default"):
        import boto3
        self.client = boto3.client("events")
        self.bus_name = bus_name
        self._batch: list[dict] = []
        self.MAX_BATCH = 10  # EventBridge limit

    def publish(self, event: CloudEvent) -> str:
        entry = event.to_eventbridge()
        entry["EventBusName"] = self.bus_name

        response = self.client.put_events(Entries=[entry])

        if response["FailedEntryCount"] > 0:
            failed = response["Entries"][0]
            raise EventPublishError(
                f"Failed to publish: {failed.get('ErrorMessage')}"
            )

        return response["Entries"][0]["EventId"]

    def add_to_batch(self, event: CloudEvent) -> None:
        entry = event.to_eventbridge()
        entry["EventBusName"] = self.bus_name
        self._batch.append(entry)

        if len(self._batch) >= self.MAX_BATCH:
            self.flush()

    def flush(self) -> list[str]:
        if not self._batch:
            return []

        event_ids = []
        # Process in chunks of 10 (EventBridge limit)
        for i in range(0, len(self._batch), self.MAX_BATCH):
            chunk = self._batch[i : i + self.MAX_BATCH]
            response = self.client.put_events(Entries=chunk)

            if response["FailedEntryCount"] > 0:
                for j, entry in enumerate(response["Entries"]):
                    if "ErrorCode" in entry:
                        # Retry failed entries
                        self.client.put_events(
                            Entries=[chunk[j]]
                        )

            event_ids.extend(
                e["EventId"] for e in response["Entries"]
                if "EventId" in e
            )

        self._batch.clear()
        return event_ids


class EventPublishError(Exception):
    pass


# ── CDK Infrastructure ────────────────────────────────────────

class EventDrivenStack(Stack):
    def __init__(self, scope: Construct, id: str, **kwargs):
        super().__init__(scope, id, **kwargs)

        # ── Custom Event Bus ───────────────────────────────────
        bus = events.EventBus(
            self, "AppEventBus",
            event_bus_name="app-events",
        )

        # Archive for replay capability
        bus.archive(
            "EventArchive",
            archive_name="app-events-archive",
            description="Archive all events for 90 days",
            retention=Duration.days(90),
            event_pattern=events.EventPattern(
                source=events.Match.prefix("com.myapp"),
            ),
        )

        # ── Dead Letter Queue ──────────────────────────────────
        dlq = sqs.Queue(
            self, "EventDLQ",
            queue_name="event-processing-dlq",
            retention_period=Duration.days(14),
        )

        # ── Rule 1: Order events -> Processing Lambda ──────────
        order_processor = self._create_lambda(
            "OrderProcessor", "order_processor"
        )
        events.Rule(
            self, "OrderCreatedRule",
            event_bus=bus,
            rule_name="order-created-processing",
            description="Route new orders to processor",
            event_pattern=events.EventPattern(
                source=["com.myapp.orders"],
                detail_type=["OrderCreated"],
                detail={
                    "total": [
                        {"numeric": [">", 0]}
                    ],
                    "status": ["pending"],
                },
            ),
            targets=[
                targets.LambdaFunction(
                    order_processor,
                    dead_letter_queue=dlq,
                    retry_attempts=2,
                    max_event_age=Duration.hours(1),
                ),
            ],
        )

        # ── Rule 2: High-value orders -> SNS alert ────────────
        alert_topic = sns.Topic(
            self, "HighValueOrderTopic",
            display_name="High Value Order Alerts",
        )
        events.Rule(
            self, "HighValueOrderRule",
            event_bus=bus,
            rule_name="high-value-order-alert",
            event_pattern=events.EventPattern(
                source=["com.myapp.orders"],
                detail_type=["OrderCreated"],
                detail={
                    "total": [{"numeric": [">=", 1000]}],
                },
            ),
            targets=[
                targets.SnsTopic(
                    alert_topic,
                    message=events.RuleTargetInput.from_event_path(
                        "$.detail"
                    ),
                ),
            ],
        )

        # ── Rule 3: Payment events -> SQS for batch ───────────
        payment_queue = sqs.Queue(
            self, "PaymentQueue",
            queue_name="payment-events",
            visibility_timeout=Duration.seconds(300),
            dead_letter_queue=sqs.DeadLetterQueue(
                queue=dlq, max_receive_count=3,
            ),
        )
        events.Rule(
            self, "PaymentRule",
            event_bus=bus,
            event_pattern=events.EventPattern(
                source=["com.myapp.payments"],
                detail_type=[
                    "PaymentProcessed",
                    "PaymentFailed",
                    "PaymentRefunded",
                ],
            ),
            targets=[
                targets.SqsQueue(
                    payment_queue,
                    dead_letter_queue=dlq,
                ),
            ],
        )

        # ── Rule 4: Catch-all logging ─────────────────────────
        log_group = logs.LogGroup(
            self, "EventLogGroup",
            log_group_name="/events/app-events",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )
        events.Rule(
            self, "CatchAllLogRule",
            event_bus=bus,
            event_pattern=events.EventPattern(
                source=events.Match.prefix("com.myapp"),
            ),
            targets=[
                targets.CloudWatchLogGroup(log_group),
            ],
        )

        # ── Cross-account event forwarding ─────────────────────
        # Allow partner account to put events on our bus
        bus.grant_put_events_to(
            iam.AccountPrincipal("123456789012")
        )

        # Forward specific events to partner account bus
        events.Rule(
            self, "CrossAccountRule",
            event_bus=bus,
            event_pattern=events.EventPattern(
                source=["com.myapp.shipping"],
                detail_type=["ShipmentDelivered"],
            ),
            targets=[
                targets.EventBus(
                    events.EventBus.from_event_bus_arn(
                        self, "PartnerBus",
                        "arn:aws:events:us-east-1:123456789012:"
                        "event-bus/partner-events",
                    )
                ),
            ],
        )

    def _create_lambda(
        self, name: str, handler_mod: str
    ) -> lambda_.Function:
        return lambda_.Function(
            self, name,
            runtime=lambda_.Runtime.PYTHON_3_13,
            handler=f"handlers.{handler_mod}.handler",
            code=lambda_.Code.from_asset("lambda/"),
            timeout=Duration.seconds(30),
            memory_size=256,
            architecture=lambda_.Architecture.ARM_64,
        )
```

EventBridge routing patterns:

| Pattern | Mechanism | Latency | Use Case |
|---------|-----------|---------|----------|
| Content filter | Event pattern matching | <1s | Route by event data |
| Fan-out | Multiple rules per event | <1s | Broadcast to services |
| Event archive | Built-in archive | N/A | Replay for debugging |
| Cross-account | Bus-to-bus forwarding | <2s | Multi-account arch |
| Schema registry | Auto-discovered schemas | N/A | Contract validation |
| Input transform | Target input transform | None | Reshape for consumer |

Key patterns:
- Use a custom event bus (not default) for application events to isolate from AWS service events
- Follow CloudEvents spec for event envelope standardization
- Use content-based filtering to route events precisely (numeric, prefix, exists)
- Always configure a DLQ on every target for failed event delivery
- Archive events for replay capability during debugging or projection rebuilds
- Batch events using put_events (up to 10 per call) for throughput
- Use correlation IDs in event metadata to trace requests across services
'''
    ),
]
