"""AWS services — Lambda, S3, DynamoDB, and SQS patterns with boto3."""

PAIRS = [
    (
        "aws/lambda-patterns",
        "Show AWS Lambda patterns: handler structure, middleware, layers, error handling, and cold start optimization.",
        '''AWS Lambda production patterns:

```python
import json
import os
import logging
import time
from functools import wraps
from typing import Any, Callable
import boto3

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Initialize clients OUTSIDE handler (reused across invocations)
dynamodb = boto3.resource("dynamodb")
s3 = boto3.client("s3")
ssm = boto3.client("ssm")


# --- Middleware pattern ---

def cors_headers(handler):
    """Add CORS headers to API Gateway responses."""
    @wraps(handler)
    def wrapper(event, context):
        try:
            result = handler(event, context)
            if isinstance(result, dict) and "statusCode" in result:
                result.setdefault("headers", {}).update({
                    "Access-Control-Allow-Origin": os.environ.get("ALLOWED_ORIGIN", "*"),
                    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
                    "Access-Control-Allow-Headers": "Content-Type,Authorization",
                })
            return result
        except Exception:
            raise
    return wrapper


def error_handler(handler):
    """Catch exceptions and return proper API Gateway responses."""
    @wraps(handler)
    def wrapper(event, context):
        try:
            return handler(event, context)
        except ValueError as e:
            logger.warning("Validation error: %s", e)
            return {"statusCode": 400, "body": json.dumps({"error": str(e)})}
        except PermissionError as e:
            return {"statusCode": 403, "body": json.dumps({"error": str(e)})}
        except KeyError as e:
            return {"statusCode": 404, "body": json.dumps({"error": f"Not found: {e}"})}
        except Exception as e:
            logger.exception("Unhandled error")
            return {"statusCode": 500, "body": json.dumps({"error": "Internal server error"})}
    return wrapper


def log_event(handler):
    """Log request/response for debugging."""
    @wraps(handler)
    def wrapper(event, context):
        logger.info("Request: %s %s",
                     event.get("httpMethod", ""),
                     event.get("path", ""))
        start = time.time()
        result = handler(event, context)
        elapsed = time.time() - start
        logger.info("Response: %d in %.3fs",
                     result.get("statusCode", 0), elapsed)
        return result
    return wrapper


# --- API Gateway handler ---

@cors_headers
@error_handler
@log_event
def api_handler(event, context):
    method = event["httpMethod"]
    path = event.get("pathParameters", {})
    body = json.loads(event.get("body") or "{}")

    if method == "GET" and "id" in (path or {}):
        return get_item(path["id"])
    elif method == "POST":
        return create_item(body)
    elif method == "PUT" and "id" in (path or {}):
        return update_item(path["id"], body)
    elif method == "DELETE" and "id" in (path or {}):
        return delete_item(path["id"])
    else:
        return {"statusCode": 405, "body": json.dumps({"error": "Method not allowed"})}


def get_item(item_id: str) -> dict:
    table = dynamodb.Table(os.environ["TABLE_NAME"])
    response = table.get_item(Key={"id": item_id})
    item = response.get("Item")
    if not item:
        raise KeyError(item_id)
    return {
        "statusCode": 200,
        "body": json.dumps(item, default=str),
    }


def create_item(data: dict) -> dict:
    if not data.get("name"):
        raise ValueError("name is required")

    table = dynamodb.Table(os.environ["TABLE_NAME"])
    import uuid
    item = {
        "id": str(uuid.uuid4()),
        "name": data["name"],
        "created_at": int(time.time()),
    }
    table.put_item(Item=item)
    return {
        "statusCode": 201,
        "body": json.dumps(item, default=str),
    }


# --- SQS trigger handler ---

def sqs_handler(event, context):
    """Process SQS messages with partial batch failure."""
    failed_ids = []

    for record in event["Records"]:
        try:
            body = json.loads(record["body"])
            process_message(body)
        except Exception as e:
            logger.error("Failed to process %s: %s", record["messageId"], e)
            failed_ids.append(record["messageId"])

    # Return failed items for retry (requires ReportBatchItemFailures)
    if failed_ids:
        return {
            "batchItemFailures": [
                {"itemIdentifier": mid} for mid in failed_ids
            ]
        }
    return {"batchItemFailures": []}


# --- S3 trigger handler ---

def s3_handler(event, context):
    """Process S3 upload events."""
    for record in event["Records"]:
        bucket = record["s3"]["bucket"]["name"]
        key = record["s3"]["object"]["key"]

        logger.info("Processing s3://%s/%s", bucket, key)

        # Download and process
        response = s3.get_object(Bucket=bucket, Key=key)
        content = response["Body"].read()
        # ... process content ...

        # Move to processed prefix
        s3.copy_object(
            Bucket=bucket,
            CopySource=f"{bucket}/{key}",
            Key=f"processed/{key}",
        )
        s3.delete_object(Bucket=bucket, Key=key)
```

Lambda patterns:
1. **Init outside handler** — SDK clients, DB connections reuse across warm invocations
2. **Middleware stack** — compose CORS, error handling, logging as decorators
3. **Partial batch failure** — return `batchItemFailures` so only failed messages retry
4. **Typed responses** — consistent API Gateway response format
5. **Environment variables** — `TABLE_NAME`, `LOG_LEVEL` via Lambda config'''
    ),
    (
        "aws/dynamodb-patterns",
        "Show DynamoDB patterns: single-table design, GSI, query patterns, transactions, and batch operations.",
        '''DynamoDB single-table design patterns:

```python
import boto3
from boto3.dynamodb.conditions import Key, Attr
from typing import Optional
import time
import uuid

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("MyApp")


# --- Single-table design ---
# PK: partition key, SK: sort key
# Access patterns determine key design

# User:     PK=USER#<id>     SK=PROFILE
# Order:    PK=USER#<id>     SK=ORDER#<timestamp>#<id>
# Product:  PK=PRODUCT#<id>  SK=DETAIL
# GSI1:     GSI1PK=ORDER#<id>  GSI1SK=USER#<id>


def create_user(user_id: str, name: str, email: str) -> dict:
    item = {
        "PK": f"USER#{user_id}",
        "SK": "PROFILE",
        "GSI1PK": f"EMAIL#{email}",
        "GSI1SK": f"USER#{user_id}",
        "type": "user",
        "id": user_id,
        "name": name,
        "email": email,
        "created_at": int(time.time()),
    }
    table.put_item(
        Item=item,
        ConditionExpression="attribute_not_exists(PK)",  # Prevent overwrite
    )
    return item


def get_user(user_id: str) -> Optional[dict]:
    response = table.get_item(
        Key={"PK": f"USER#{user_id}", "SK": "PROFILE"},
    )
    return response.get("Item")


def get_user_by_email(email: str) -> Optional[dict]:
    """Query GSI to find user by email."""
    response = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"EMAIL#{email}"),
        Limit=1,
    )
    items = response.get("Items", [])
    return items[0] if items else None


def create_order(user_id: str, items: list[dict], total: float) -> dict:
    order_id = str(uuid.uuid4())
    timestamp = int(time.time())
    order = {
        "PK": f"USER#{user_id}",
        "SK": f"ORDER#{timestamp}#{order_id}",
        "GSI1PK": f"ORDER#{order_id}",
        "GSI1SK": f"USER#{user_id}",
        "type": "order",
        "id": order_id,
        "user_id": user_id,
        "items": items,
        "total": str(total),  # DynamoDB: use string for money
        "status": "pending",
        "created_at": timestamp,
    }
    table.put_item(Item=order)
    return order


def get_user_orders(user_id: str, limit: int = 20) -> list[dict]:
    """Get user's orders sorted by newest first."""
    response = table.query(
        KeyConditionExpression=(
            Key("PK").eq(f"USER#{user_id}") &
            Key("SK").begins_with("ORDER#")
        ),
        ScanIndexForward=False,  # Descending (newest first)
        Limit=limit,
    )
    return response["Items"]


def get_order_by_id(order_id: str) -> Optional[dict]:
    """Get order by ID using GSI."""
    response = table.query(
        IndexName="GSI1",
        KeyConditionExpression=Key("GSI1PK").eq(f"ORDER#{order_id}"),
        Limit=1,
    )
    items = response.get("Items", [])
    return items[0] if items else None


# --- Transactions ---

def place_order_with_inventory(user_id: str, product_id: str,
                                quantity: int, price: float):
    """Atomic: create order + decrement inventory."""
    order_id = str(uuid.uuid4())
    timestamp = int(time.time())

    client = boto3.client("dynamodb")
    client.transact_write_items(
        TransactItems=[
            {
                "Put": {
                    "TableName": "MyApp",
                    "Item": {
                        "PK": {"S": f"USER#{user_id}"},
                        "SK": {"S": f"ORDER#{timestamp}#{order_id}"},
                        "type": {"S": "order"},
                        "id": {"S": order_id},
                        "status": {"S": "confirmed"},
                        "total": {"N": str(price * quantity)},
                    },
                }
            },
            {
                "Update": {
                    "TableName": "MyApp",
                    "Key": {
                        "PK": {"S": f"PRODUCT#{product_id}"},
                        "SK": {"S": "DETAIL"},
                    },
                    "UpdateExpression": "SET inventory = inventory - :qty",
                    "ConditionExpression": "inventory >= :qty",
                    "ExpressionAttributeValues": {
                        ":qty": {"N": str(quantity)},
                    },
                }
            },
        ]
    )


# --- Batch operations ---

def batch_get_users(user_ids: list[str]) -> list[dict]:
    """Batch get up to 100 items."""
    keys = [{"PK": f"USER#{uid}", "SK": "PROFILE"} for uid in user_ids]

    # BatchGetItem handles max 100 items
    results = []
    for i in range(0, len(keys), 100):
        chunk = keys[i:i + 100]
        response = dynamodb.batch_get_item(
            RequestItems={"MyApp": {"Keys": chunk}}
        )
        results.extend(response["Responses"].get("MyApp", []))

        # Handle unprocessed keys (throttling)
        unprocessed = response.get("UnprocessedKeys", {})
        while unprocessed:
            response = dynamodb.batch_get_item(RequestItems=unprocessed)
            results.extend(response["Responses"].get("MyApp", []))
            unprocessed = response.get("UnprocessedKeys", {})

    return results
```

DynamoDB patterns:
1. **Single-table design** — model all entities in one table with PK/SK patterns
2. **GSI overloading** — reuse GSI columns for different access patterns
3. **Transactions** — atomic multi-item writes with conditions
4. **`begins_with`** — query hierarchical sort keys efficiently
5. **Batch operations** — handle unprocessed items from throttling'''
    ),
]
