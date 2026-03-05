"""Cloud patterns — serverless, event-driven architecture, multi-tenancy, cost optimization."""

PAIRS = [
    (
        "cloud/serverless-patterns",
        "Show serverless architecture patterns with AWS Lambda: API handling, event processing, cold starts, and cost optimization.",
        '''Serverless patterns for production workloads:

```python
# --- Lambda handler with middleware pattern ---

import json
import os
import time
import logging
from functools import wraps
from typing import Any, Callable

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Middleware decorators
def cors(handler):
    @wraps(handler)
    def wrapper(event, context):
        response = handler(event, context)
        response.setdefault("headers", {}).update({
            "Access-Control-Allow-Origin": os.environ.get("ALLOWED_ORIGIN", "*"),
            "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type,Authorization",
        })
        return response
    return wrapper

def error_handler(handler):
    @wraps(handler)
    def wrapper(event, context):
        try:
            return handler(event, context)
        except ValidationError as e:
            return {"statusCode": 400, "body": json.dumps({"error": str(e)})}
        except NotFoundError as e:
            return {"statusCode": 404, "body": json.dumps({"error": str(e)})}
        except Exception as e:
            logger.exception("Unhandled error")
            return {"statusCode": 500, "body": json.dumps({"error": "Internal error"})}
    return wrapper

def log_metrics(handler):
    @wraps(handler)
    def wrapper(event, context):
        start = time.time()
        response = handler(event, context)
        duration = (time.time() - start) * 1000
        logger.info("request_completed", extra={
            "duration_ms": round(duration, 2),
            "status": response.get("statusCode"),
            "remaining_ms": context.get_remaining_time_in_millis(),
        })
        return response
    return wrapper

# --- Connection reuse (warm start optimization) ---

# Initialize OUTSIDE handler for connection reuse across invocations
import boto3
from functools import lru_cache

# These persist between warm invocations
dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_NAME"])

@lru_cache(maxsize=1)
def get_secret(secret_name: str) -> str:
    """Cache secrets in memory (warm starts reuse)."""
    client = boto3.client("secretsmanager")
    return client.get_secret_value(SecretId=secret_name)["SecretString"]

# --- API Gateway Lambda handler ---

@cors
@error_handler
@log_metrics
def api_handler(event, context):
    method = event["httpMethod"]
    path = event["path"]
    body = json.loads(event.get("body") or "{}")

    # Router
    if method == "GET" and path.startswith("/users/"):
        user_id = path.split("/")[-1]
        return get_user(user_id)
    elif method == "POST" and path == "/users":
        return create_user(body)
    else:
        return {"statusCode": 404, "body": json.dumps({"error": "Not found"})}

def get_user(user_id: str):
    response = table.get_item(Key={"pk": f"USER#{user_id}", "sk": "PROFILE"})
    item = response.get("Item")
    if not item:
        raise NotFoundError(f"User {user_id} not found")
    return {"statusCode": 200, "body": json.dumps(item, default=str)}

# --- SQS event processor (batch handling) ---

def sqs_handler(event, context):
    """Process SQS messages with partial batch failure."""
    failed_ids = []

    for record in event["Records"]:
        try:
            body = json.loads(record["body"])
            process_message(body)
        except Exception as e:
            logger.error(f"Failed to process {record['messageId']}: {e}")
            failed_ids.append(record["messageId"])

    # Return failed items for retry (partial batch failure)
    if failed_ids:
        return {
            "batchItemFailures": [
                {"itemIdentifier": mid} for mid in failed_ids
            ]
        }
    return {"batchItemFailures": []}

# --- DynamoDB Stream handler (CDC) ---

def stream_handler(event, context):
    for record in event["Records"]:
        event_name = record["eventName"]  # INSERT, MODIFY, REMOVE
        if event_name == "INSERT":
            new_image = record["dynamodb"]["NewImage"]
            handle_new_item(new_image)
        elif event_name == "MODIFY":
            old_image = record["dynamodb"]["OldImage"]
            new_image = record["dynamodb"]["NewImage"]
            handle_update(old_image, new_image)

# --- Step Functions (orchestration) ---

STEP_FUNCTION_DEFINITION = {
    "Comment": "Order processing pipeline",
    "StartAt": "ValidateOrder",
    "States": {
        "ValidateOrder": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:us-east-1:123:function:validate-order",
            "Retry": [{"ErrorEquals": ["ServiceUnavailable"], "MaxAttempts": 3}],
            "Catch": [{"ErrorEquals": ["ValidationError"], "Next": "RejectOrder"}],
            "Next": "ProcessPayment",
        },
        "ProcessPayment": {
            "Type": "Task",
            "Resource": "arn:aws:lambda:us-east-1:123:function:process-payment",
            "TimeoutSeconds": 30,
            "Next": "ParallelFulfillment",
        },
        "ParallelFulfillment": {
            "Type": "Parallel",
            "Branches": [
                {"StartAt": "UpdateInventory", "States": {"UpdateInventory": {"Type": "Task", "Resource": "...", "End": True}}},
                {"StartAt": "SendConfirmation", "States": {"SendConfirmation": {"Type": "Task", "Resource": "...", "End": True}}},
            ],
            "Next": "Complete",
        },
        "Complete": {"Type": "Succeed"},
        "RejectOrder": {"Type": "Fail", "Error": "OrderRejected"},
    },
}
```

Cost optimization:
- **Right-size memory** — CPU scales with memory, profile to find sweet spot
- **ARM (Graviton)** — 20% cheaper, often faster for Lambda
- **Provisioned concurrency** — eliminate cold starts for latency-sensitive
- **Reserved concurrency** — prevent runaway scaling
- **Batch processing** — SQS batch size, partial failures
- **Connection reuse** — initialize clients outside handler'''
    ),
    (
        "cloud/dynamodb-patterns",
        "Show DynamoDB single-table design patterns: access patterns, GSI overloading, composite keys, and query optimization.",
        '''DynamoDB single-table design for scalable applications:

```python
import boto3
from boto3.dynamodb.conditions import Key, Attr
from datetime import datetime, timezone
import json

# --- Single Table Design ---
# One table serves multiple entity types via key design

# Access patterns:
# 1. Get user by ID
# 2. Get user's orders
# 3. Get order by ID
# 4. Get orders by date range
# 5. Get user by email (GSI)

# Key design:
# PK                    SK                      Data
# USER#u123            PROFILE                  {name, email, ...}
# USER#u123            ORDER#2024-03-15#o456    {total, status, ...}
# ORDER#o456           METADATA                 {user_id, total, ...}
# ORDER#o456           ITEM#i789                {product, qty, price}

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("AppTable")

class DynamoRepository:
    def __init__(self, table):
        self.table = table

    # --- User operations ---

    def create_user(self, user_id: str, name: str, email: str):
        self.table.put_item(Item={
            "pk": f"USER#{user_id}",
            "sk": "PROFILE",
            "entity_type": "USER",
            "user_id": user_id,
            "name": name,
            "email": email,
            "gsi1pk": f"EMAIL#{email}",  # GSI for email lookup
            "gsi1sk": f"USER#{user_id}",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

    def get_user(self, user_id: str) -> dict:
        response = self.table.get_item(Key={
            "pk": f"USER#{user_id}",
            "sk": "PROFILE",
        })
        return response.get("Item")

    def get_user_by_email(self, email: str) -> dict:
        response = self.table.query(
            IndexName="GSI1",
            KeyConditionExpression=Key("gsi1pk").eq(f"EMAIL#{email}"),
        )
        items = response.get("Items", [])
        return items[0] if items else None

    # --- Order operations ---

    def create_order(self, order_id: str, user_id: str,
                     items: list[dict], total: float):
        now = datetime.now(timezone.utc).isoformat()

        # Transaction: create order + items atomically
        transact_items = [
            # Order under user (for user's orders query)
            {
                "Put": {
                    "TableName": self.table.name,
                    "Item": {
                        "pk": {"S": f"USER#{user_id}"},
                        "sk": {"S": f"ORDER#{now}#{order_id}"},
                        "entity_type": {"S": "ORDER"},
                        "order_id": {"S": order_id},
                        "total": {"N": str(total)},
                        "status": {"S": "pending"},
                        "created_at": {"S": now},
                    },
                }
            },
            # Order metadata (for order lookup by ID)
            {
                "Put": {
                    "TableName": self.table.name,
                    "Item": {
                        "pk": {"S": f"ORDER#{order_id}"},
                        "sk": {"S": "METADATA"},
                        "entity_type": {"S": "ORDER"},
                        "user_id": {"S": user_id},
                        "total": {"N": str(total)},
                        "status": {"S": "pending"},
                        "gsi1pk": {"S": f"STATUS#pending"},
                        "gsi1sk": {"S": now},
                    },
                }
            },
        ]

        # Add order items
        for item in items:
            transact_items.append({
                "Put": {
                    "TableName": self.table.name,
                    "Item": {
                        "pk": {"S": f"ORDER#{order_id}"},
                        "sk": {"S": f"ITEM#{item['sku']}"},
                        "entity_type": {"S": "ORDER_ITEM"},
                        "product_name": {"S": item["name"]},
                        "quantity": {"N": str(item["quantity"])},
                        "price": {"N": str(item["price"])},
                    },
                }
            })

        client = boto3.client("dynamodb")
        client.transact_write_items(TransactItems=transact_items)

    def get_user_orders(self, user_id: str, limit: int = 20) -> list[dict]:
        """Get user's orders sorted by date (newest first)."""
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(f"USER#{user_id}") &
                Key("sk").begins_with("ORDER#")
            ),
            ScanIndexForward=False,  # Newest first
            Limit=limit,
        )
        return response.get("Items", [])

    def get_order_with_items(self, order_id: str) -> dict:
        """Get order metadata + all items in one query."""
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"ORDER#{order_id}"),
        )
        items = response.get("Items", [])
        order = {}
        order_items = []
        for item in items:
            if item["sk"] == "METADATA":
                order = item
            elif item["sk"].startswith("ITEM#"):
                order_items.append(item)
        order["items"] = order_items
        return order

    def get_orders_by_status(self, status: str, limit: int = 50) -> list[dict]:
        """Get orders by status using GSI."""
        response = self.table.query(
            IndexName="GSI1",
            KeyConditionExpression=Key("gsi1pk").eq(f"STATUS#{status}"),
            ScanIndexForward=False,
            Limit=limit,
        )
        return response.get("Items", [])

    # --- Pagination ---

    def paginated_query(self, user_id: str, page_size: int = 20,
                        last_key: dict = None) -> tuple[list[dict], dict]:
        kwargs = {
            "KeyConditionExpression": Key("pk").eq(f"USER#{user_id}"),
            "Limit": page_size,
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = last_key

        response = self.table.query(**kwargs)
        items = response.get("Items", [])
        next_key = response.get("LastEvaluatedKey")
        return items, next_key
```

Single-table design principles:
1. **Start with access patterns** — list all queries before designing keys
2. **Composite sort keys** — enable range queries (`ORDER#2024-03-15#o456`)
3. **GSI overloading** — one GSI serves multiple entity lookups
4. **Denormalize** — duplicate data to avoid joins (no JOINs in DynamoDB)
5. **Transactions** — use for multi-item consistency (25 items max)
6. **Avoid scans** — every query should use partition key'''
    ),
    (
        "cloud/multi-tenancy",
        "Explain multi-tenancy patterns: database isolation levels, tenant routing, resource limits, and data partitioning strategies.",
        '''Multi-tenancy architecture patterns:

```python
from dataclasses import dataclass
from enum import Enum
from typing import Optional
from contextvars import ContextVar
from functools import wraps

# --- Tenant context ---

current_tenant: ContextVar[Optional[str]] = ContextVar("current_tenant", default=None)

class IsolationLevel(Enum):
    SHARED_SCHEMA = "shared"     # Shared tables, tenant_id column
    SCHEMA_PER_TENANT = "schema" # Separate schema per tenant
    DB_PER_TENANT = "database"   # Separate database per tenant

@dataclass
class TenantConfig:
    tenant_id: str
    name: str
    isolation: IsolationLevel
    tier: str  # "free", "pro", "enterprise"
    db_schema: Optional[str] = None
    db_url: Optional[str] = None
    rate_limit_rps: int = 100
    storage_limit_gb: int = 10
    max_users: int = 50

# --- Tenant-aware middleware ---

from fastapi import FastAPI, Request, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware

class TenantMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, tenant_store):
        super().__init__(app)
        self.tenant_store = tenant_store

    async def dispatch(self, request: Request, call_next):
        # Extract tenant from subdomain, header, or JWT
        tenant_id = self._resolve_tenant(request)
        if not tenant_id:
            raise HTTPException(401, "Tenant not identified")

        config = await self.tenant_store.get_config(tenant_id)
        if not config:
            raise HTTPException(404, "Tenant not found")

        # Set tenant context
        token = current_tenant.set(tenant_id)
        request.state.tenant = config

        try:
            response = await call_next(request)
            return response
        finally:
            current_tenant.reset(token)

    def _resolve_tenant(self, request: Request) -> Optional[str]:
        # Strategy 1: Subdomain (acme.app.com)
        host = request.headers.get("host", "")
        parts = host.split(".")
        if len(parts) > 2:
            return parts[0]

        # Strategy 2: Header
        tenant = request.headers.get("X-Tenant-ID")
        if tenant:
            return tenant

        # Strategy 3: JWT claim
        # return decode_jwt(request).get("tenant_id")
        return None

# --- Database routing ---

class TenantDatabaseRouter:
    """Route queries to correct database/schema based on tenant."""

    def __init__(self):
        self.connections = {}

    def get_connection(self, tenant_config: TenantConfig):
        if tenant_config.isolation == IsolationLevel.DB_PER_TENANT:
            return self._get_dedicated_db(tenant_config)
        elif tenant_config.isolation == IsolationLevel.SCHEMA_PER_TENANT:
            return self._get_schema_connection(tenant_config)
        else:
            return self._get_shared_connection()

    def _get_dedicated_db(self, config):
        if config.tenant_id not in self.connections:
            self.connections[config.tenant_id] = create_pool(config.db_url)
        return self.connections[config.tenant_id]

    def _get_schema_connection(self, config):
        conn = self._get_shared_connection()
        conn.execute(f"SET search_path TO {config.db_schema}, public")
        return conn

    def _get_shared_connection(self):
        return self.connections.setdefault("shared", create_pool(SHARED_DB_URL))

# --- Row-level security (shared schema) ---

# PostgreSQL RLS policies:
RLS_SETUP = """
-- Enable RLS on tables
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- Create policy: tenant can only see own data
CREATE POLICY tenant_isolation ON orders
    USING (tenant_id = current_setting('app.tenant_id'));

CREATE POLICY tenant_isolation ON users
    USING (tenant_id = current_setting('app.tenant_id'));

-- Set tenant context on each connection
SET app.tenant_id = 'tenant-123';
-- Now all queries automatically filter by tenant
SELECT * FROM orders;  -- Only sees tenant-123 orders
"""

# Python implementation:
class TenantAwareRepository:
    def __init__(self, db_pool):
        self.pool = db_pool

    async def query(self, sql: str, params: list = None):
        tenant_id = current_tenant.get()
        if not tenant_id:
            raise RuntimeError("No tenant context set")

        async with self.pool.acquire() as conn:
            # Set RLS context
            await conn.execute(f"SET app.tenant_id = '{tenant_id}'")
            return await conn.fetch(sql, *(params or []))

# --- Resource limits per tenant tier ---

class TenantRateLimiter:
    TIER_LIMITS = {
        "free": {"rps": 10, "daily_requests": 1000, "storage_gb": 1},
        "pro": {"rps": 100, "daily_requests": 100000, "storage_gb": 50},
        "enterprise": {"rps": 1000, "daily_requests": None, "storage_gb": 500},
    }

    def __init__(self, redis_client):
        self.redis = redis_client

    async def check_rate_limit(self, tenant_config: TenantConfig) -> bool:
        limits = self.TIER_LIMITS[tenant_config.tier]
        rps_limit = limits["rps"]

        key = f"ratelimit:{tenant_config.tenant_id}"
        current = await self.redis.incr(key)
        if current == 1:
            await self.redis.expire(key, 1)

        return current <= rps_limit
```

Isolation tradeoffs:
| Pattern | Isolation | Cost | Complexity | Use When |
|---------|-----------|------|------------|----------|
| Shared tables | Low | Lowest | Low | SaaS, many small tenants |
| Schema per tenant | Medium | Medium | Medium | Compliance needs |
| DB per tenant | Highest | Highest | High | Enterprise, strict compliance |
| Row-level security | Medium | Low | Low | PostgreSQL, shared infra |'''
    ),
    (
        "cloud/cost-optimization",
        "Show cloud cost optimization strategies: right-sizing, spot instances, reserved capacity, storage tiering, and FinOps practices.",
        '''Cloud cost optimization patterns:

```python
import boto3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

# --- Right-sizing analyzer ---

@dataclass
class ResourceMetrics:
    resource_id: str
    resource_type: str
    avg_cpu: float
    max_cpu: float
    avg_memory: float
    max_memory: float
    avg_network: float
    current_cost_monthly: float

class RightSizingAnalyzer:
    """Analyze resource utilization and recommend right-sizing."""

    # Instance family progression (cost order)
    INSTANCE_SIZES = {
        "t3": ["nano", "micro", "small", "medium", "large", "xlarge", "2xlarge"],
        "m5": ["large", "xlarge", "2xlarge", "4xlarge", "8xlarge"],
        "c5": ["large", "xlarge", "2xlarge", "4xlarge", "9xlarge"],
    }

    def analyze(self, metrics: list[ResourceMetrics]) -> list[dict]:
        recommendations = []
        for m in metrics:
            rec = self._evaluate(m)
            if rec:
                recommendations.append(rec)
        return sorted(recommendations, key=lambda r: r["savings"], reverse=True)

    def _evaluate(self, m: ResourceMetrics) -> Optional[dict]:
        # Underutilized: consistently low CPU + memory
        if m.max_cpu < 20 and m.max_memory < 30:
            return {
                "resource_id": m.resource_id,
                "action": "downsize",
                "reason": f"Max CPU {m.max_cpu:.0f}%, max memory {m.max_memory:.0f}%",
                "savings": m.current_cost_monthly * 0.5,  # Estimate
            }

        # Idle: very low utilization
        if m.avg_cpu < 2 and m.avg_network < 1:
            return {
                "resource_id": m.resource_id,
                "action": "terminate_or_schedule",
                "reason": f"Avg CPU {m.avg_cpu:.1f}%, appears idle",
                "savings": m.current_cost_monthly * 0.9,
            }

        # Over-provisioned memory (CPU used but memory isn't)
        if m.avg_cpu > 40 and m.max_memory < 20:
            return {
                "resource_id": m.resource_id,
                "action": "switch_to_compute_optimized",
                "reason": "CPU-heavy, memory underused — switch to C-family",
                "savings": m.current_cost_monthly * 0.3,
            }

        return None

# --- Spot Instance Manager ---

class SpotInstanceManager:
    """Manage spot instances with fallback to on-demand."""

    def __init__(self):
        self.ec2 = boto3.client("ec2")

    def request_spot_fleet(self, config: dict):
        """Request spot fleet with diversified instance types."""
        response = self.ec2.request_spot_fleet(
            SpotFleetRequestConfig={
                "IamFleetRole": config["fleet_role_arn"],
                "TargetCapacity": config["target_capacity"],
                "SpotPrice": str(config.get("max_price", "0.50")),
                "AllocationStrategy": "capacityOptimized",
                "InstanceInterruptionBehavior": "terminate",
                "LaunchSpecifications": [
                    # Diversify across instance types and AZs
                    {
                        "InstanceType": instance_type,
                        "SubnetId": subnet,
                        "ImageId": config["ami_id"],
                        "KeyName": config.get("key_name"),
                    }
                    for instance_type in config.get("instance_types",
                        ["m5.large", "m5a.large", "m5d.large", "m4.large"])
                    for subnet in config["subnet_ids"]
                ],
                # On-demand base capacity for reliability
                "OnDemandTargetCapacity": max(1, config["target_capacity"] // 10),
                "OnDemandAllocationStrategy": "lowestPrice",
            }
        )
        return response

# --- Storage Lifecycle Policies ---

STORAGE_LIFECYCLE = {
    "S3 Intelligent-Tiering": {
        "description": "Auto-moves objects between tiers based on access",
        "recommended_for": "Unknown or changing access patterns",
        "savings": "Up to 95% vs S3 Standard",
    },
    "lifecycle_policy": {
        "Rules": [
            {
                "ID": "ArchiveOldData",
                "Status": "Enabled",
                "Transitions": [
                    {"Days": 30, "StorageClass": "STANDARD_IA"},      # ~40% cheaper
                    {"Days": 90, "StorageClass": "GLACIER_IR"},       # ~68% cheaper
                    {"Days": 365, "StorageClass": "DEEP_ARCHIVE"},    # ~95% cheaper
                ],
                "Expiration": {"Days": 2555},  # Delete after 7 years
            },
        ]
    },
}

# --- Cost allocation and tagging ---

REQUIRED_TAGS = {
    "Environment": ["production", "staging", "development"],
    "Team": ["platform", "backend", "data", "ml"],
    "CostCenter": None,  # Any value
    "Service": None,
}

def audit_tags(region: str = "us-east-1") -> list[dict]:
    """Find resources missing required tags."""
    client = boto3.client("resourcegroupstaggingapi", region_name=region)
    untagged = []

    paginator = client.get_paginator("get_resources")
    for page in paginator.paginate():
        for resource in page["ResourceTagMappingList"]:
            tags = {t["Key"]: t["Value"] for t in resource.get("Tags", [])}
            missing = [k for k in REQUIRED_TAGS if k not in tags]
            if missing:
                untagged.append({
                    "arn": resource["ResourceARN"],
                    "missing_tags": missing,
                    "existing_tags": tags,
                })

    return untagged
```

FinOps checklist:
1. **Tagging** — enforce tags for cost allocation by team/service
2. **Right-sizing** — weekly analysis of CPU/memory utilization
3. **Spot/preemptible** — 60-90% savings for fault-tolerant workloads
4. **Reserved capacity** — 1-3 year commitments for steady-state
5. **Storage tiering** — lifecycle policies for aging data
6. **Idle resources** — terminate unused instances, EIPs, volumes
7. **Data transfer** — CDN, VPC endpoints, same-AZ communication'''
    ),
]
