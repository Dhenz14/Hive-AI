"""Thinking-trace pairs: AWS debugging."""

PAIRS = [
    (
        "thinking/debugging",
        r'''My AWS Lambda function has terrible cold start times (5+ seconds). It is a Python function that connects to RDS PostgreSQL. The function runs fine once warm but the first invocation after idle is painfully slow. How do I reduce cold start time?''',
        r'''<think>
Lambda cold start has several contributors:
1. Package size -- larger deployment packages take longer to load
2. Import time -- importing heavy libraries like SQLAlchemy at module level
3. VPC configuration -- Lambda in a VPC needs ENI (Elastic Network Interface) which adds 6-10 seconds (though this was improved with VPC networking improvements)
4. Database connection setup -- connecting to RDS takes time
5. Runtime initialization -- Python is slower to start than Node.js or Go

Strategies to fix:
1. Reduce package size (remove unused deps, use Lambda layers)
2. Lazy imports
3. Use RDS Proxy to avoid per-invocation connection overhead
4. Provisioned concurrency to eliminate cold starts entirely
5. Keep warm with scheduled events
</think>

Lambda cold starts in Python with RDS connections have multiple optimization points. Here is a comprehensive fix:

```python
# ============================================================
# BEFORE: Slow cold start (5+ seconds)
# ============================================================

# BAD: Heavy imports at module level
import boto3
import sqlalchemy
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pandas as pd  # 200MB+ import, takes 2+ seconds
import numpy as np

# BAD: Connection created at module level but outside handler
# This runs during INIT phase, adding to cold start
engine = create_engine(
    "postgresql://user:pass@rds-host:5432/mydb",
    pool_size=5,
    pool_pre_ping=True,
)
Session = sessionmaker(bind=engine)

def handler(event, context):
    session = Session()
    result = session.execute("SELECT * FROM items")
    return {"items": [dict(row) for row in result]}


# ============================================================
# AFTER: Optimized cold start
# ============================================================

import os
import json

# ONLY import what you need at module level
# Heavy imports are lazy-loaded inside the handler

# Connection is created once and reused across warm invocations
_db_connection = None

def get_connection():
    """Lazy connection initialization -- only on first call."""
    global _db_connection
    if _db_connection is None:
        # Import psycopg2 only when needed (lighter than SQLAlchemy)
        import psycopg2
        _db_connection = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            connect_timeout=5,
            # Use SSL for RDS
            sslmode="require",
        )
    return _db_connection


def handler(event, context):
    """Optimized handler with lazy loading."""
    try:
        conn = get_connection()
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, price FROM items LIMIT 100")
            columns = [desc[0] for desc in cur.description]
            rows = [dict(zip(columns, row)) for row in cur.fetchall()]

        return {
            "statusCode": 200,
            "body": json.dumps({"items": rows}),
        }
    except Exception as e:
        # Reset connection on error (might be stale)
        global _db_connection
        _db_connection = None
        return {
            "statusCode": 500,
            "body": json.dumps({"error": str(e)}),
        }


# ============================================================
# FIX 1: Use RDS Proxy to eliminate connection overhead
# ============================================================

# Instead of connecting directly to RDS:
#   DB_HOST=my-rds-instance.abc.us-east-1.rds.amazonaws.com
# Connect through RDS Proxy:
#   DB_HOST=my-proxy.proxy-abc.us-east-1.rds.amazonaws.com
#
# Benefits:
# - Connection pooling (reuses connections across Lambda instances)
# - IAM authentication (no passwords in env vars)
# - Handles connection draining during failover

# With IAM authentication (no password needed):
def get_rds_proxy_connection():
    global _db_connection
    if _db_connection is None:
        import psycopg2
        import boto3

        client = boto3.client("rds")
        token = client.generate_db_auth_token(
            DBHostname=os.environ["DB_HOST"],
            Port=5432,
            DBUsername=os.environ["DB_USER"],
            Region=os.environ["AWS_REGION"],
        )
        _db_connection = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=5432,
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=token,
            sslmode="require",
        )
    return _db_connection


# ============================================================
# FIX 2: Provisioned concurrency (eliminates cold start)
# ============================================================

# AWS CLI:
# aws lambda put-provisioned-concurrency-config \
#   --function-name my-function \
#   --qualifier prod \
#   --provisioned-concurrent-executions 5
#
# This keeps 5 Lambda instances warm at all times.
# Cost: ~$0.015 per GB-hour of provisioned concurrency.

# CDK / CloudFormation:
# MyFunction:
#   Type: AWS::Lambda::Function
#   Properties:
#     ...
# MyAlias:
#   Type: AWS::Lambda::Alias
#   Properties:
#     FunctionName: !Ref MyFunction
#     Name: prod
#     ProvisionedConcurrencyConfig:
#       ProvisionedConcurrentExecutions: 5


# ============================================================
# FIX 3: Reduce package size
# ============================================================

# requirements.txt -- minimal deps
# psycopg2-binary==2.9.9   # 3MB vs SQLAlchemy 15MB+
# Do NOT include: pandas, numpy, scipy, etc.

# Use Lambda Layers for shared dependencies:
# aws lambda publish-layer-version \
#   --layer-name psycopg2-layer \
#   --zip-file fileb://layer.zip \
#   --compatible-runtimes python3.11

# Package size targets:
# < 5 MB: Fast cold start (~200ms)
# 5-50 MB: Moderate cold start (~500ms-1s)
# 50-250 MB: Slow cold start (2-5s)
# Use docker-style packaging or SAM for large deps


# ============================================================
# FIX 4: Keep warm with scheduled events (budget option)
# ============================================================

# CloudWatch Events rule to ping every 5 minutes:
# aws events put-rule \
#   --name keep-warm \
#   --schedule-expression "rate(5 minutes)"
#
# aws events put-targets \
#   --rule keep-warm \
#   --targets "Id"="1","Arn"="arn:aws:lambda:...:my-function"

def handler(event, context):
    # Detect warm-up ping and return early
    if event.get("source") == "aws.events":
        return {"statusCode": 200, "body": "warm"}

    # Normal handler logic...
    conn = get_connection()
    # ...
```

**Cold start optimization checklist:**
1. Remove heavy unused imports (pandas, numpy, SQLAlchemy)
2. Use psycopg2 directly instead of SQLAlchemy (3MB vs 15MB+)
3. Use RDS Proxy for connection pooling
4. Lazy-load everything -- import inside the handler function
5. Use Provisioned Concurrency for latency-sensitive functions
6. Keep total package size under 10MB if possible''',
    ),
    (
        "thinking/debugging",
        r'''I'm processing SQS messages in a Lambda function but some messages are being processed twice. I also have messages that reappear after I thought they were processed. How do I handle SQS message duplication and ensure exactly-once processing?''',
        r'''<think>
SQS has two queue types:
1. Standard queues: at-least-once delivery (duplicates possible), best-effort ordering
2. FIFO queues: exactly-once processing (within dedup window), strict ordering

If the user is using a standard queue, duplicates are expected. But even with FIFO, there are edge cases.

The "messages reappearing" issue is likely related to visibility timeout: if the Lambda function takes longer than the visibility timeout, SQS makes the message visible again for another consumer.

Solutions:
1. Make processing idempotent
2. Use FIFO queue with deduplication
3. Increase visibility timeout
4. Use a deduplication store (DynamoDB)
</think>

SQS message duplication happens for several reasons. Here is how to handle it properly:

```python
import json
import os
import time
import hashlib
import boto3
from botocore.exceptions import ClientError

dynamodb = boto3.resource("dynamodb")
dedup_table = dynamodb.Table(os.environ.get("DEDUP_TABLE", "message-dedup"))

# ============================================================
# WHY MESSAGES ARE DUPLICATED
# ============================================================
# 1. Standard SQS queue delivers messages "at least once"
#    Duplicates are by design, not a bug.
# 2. Visibility timeout too short: if Lambda takes longer than
#    the timeout, SQS makes the message visible again.
# 3. Lambda retries: if Lambda fails, it retries with the same
#    batch, and partially processed messages get reprocessed.
# 4. Network issues: SQS might not receive the delete
#    acknowledgment, so it redelivers.

# ============================================================
# FIX 1: Make processing idempotent (MOST IMPORTANT)
# ============================================================

def handler(event, context):
    """Process SQS messages idempotently."""
    failed_message_ids = []

    for record in event["Records"]:
        message_id = record["messageId"]
        body = json.loads(record["body"])

        try:
            if is_already_processed(message_id):
                print(f"Skipping duplicate: {message_id}")
                continue

            process_message(body)
            mark_as_processed(message_id)

        except Exception as e:
            print(f"Error processing {message_id}: {e}")
            failed_message_ids.append(message_id)

    # Return failed messages for retry (partial batch failure)
    if failed_message_ids:
        return {
            "batchItemFailures": [
                {"itemIdentifier": mid} for mid in failed_message_ids
            ],
        }

    return {"batchItemFailures": []}


def is_already_processed(message_id: str) -> bool:
    """Check DynamoDB for duplicate message ID."""
    try:
        response = dedup_table.get_item(
            Key={"message_id": message_id},
            ProjectionExpression="message_id",
        )
        return "Item" in response
    except ClientError:
        # If DynamoDB is unavailable, process anyway (idempotent)
        return False


def mark_as_processed(message_id: str):
    """Record message as processed with TTL for auto-cleanup."""
    ttl = int(time.time()) + 86400 * 7  # 7 days
    dedup_table.put_item(
        Item={
            "message_id": message_id,
            "processed_at": int(time.time()),
            "ttl": ttl,
        },
        # Conditional write: only succeed if not already processed
        ConditionExpression="attribute_not_exists(message_id)",
    )


def process_message(body: dict):
    """Idempotent message processing."""
    order_id = body["order_id"]
    action = body["action"]

    if action == "create_order":
        # Use conditional writes to make this idempotent
        orders_table = dynamodb.Table("orders")
        try:
            orders_table.put_item(
                Item={
                    "order_id": order_id,
                    "status": "created",
                    "amount": body["amount"],
                    "created_at": int(time.time()),
                },
                # Only create if it does not exist yet
                ConditionExpression="attribute_not_exists(order_id)",
            )
        except ClientError as e:
            if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
                # Already created -- idempotent success
                print(f"Order {order_id} already exists, skipping")
            else:
                raise


# ============================================================
# FIX 2: Use FIFO queue for deduplication
# ============================================================

sqs = boto3.client("sqs")

# Producer: send with deduplication ID
def send_to_fifo_queue(queue_url, body, dedup_id=None, group_id="default"):
    """Send message to FIFO queue with dedup."""
    if dedup_id is None:
        # Generate dedup ID from content hash
        dedup_id = hashlib.sha256(
            json.dumps(body, sort_keys=True).encode()
        ).hexdigest()

    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(body),
        MessageGroupId=group_id,
        MessageDeduplicationId=dedup_id,
    )

# FIFO queues deduplicate within a 5-minute window.
# Same MessageDeduplicationId within 5 minutes = ignored.


# ============================================================
# FIX 3: Configure visibility timeout correctly
# ============================================================

# Lambda timeout MUST be less than SQS visibility timeout
# If Lambda timeout = 60s, visibility timeout should be >= 360s
# (6x Lambda timeout is recommended)

# aws sqs set-queue-attributes \
#   --queue-url https://sqs.region.amazonaws.com/123/my-queue \
#   --attributes VisibilityTimeout=360


# ============================================================
# FIX 4: Enable partial batch failure reporting
# ============================================================

# In Lambda event source mapping, enable:
# aws lambda update-event-source-mapping \
#   --uuid <mapping-uuid> \
#   --function-response-types ReportBatchItemFailures
#
# Then return batchItemFailures in the handler response
# (shown in handler above)
# This prevents successful messages from being retried
# when only some messages in a batch fail.
```

**Key takeaways:**
1. Always make processing **idempotent** -- this is the real fix, not preventing duplicates
2. Use DynamoDB conditional writes for deduplication tracking
3. Set visibility timeout to at least 6x Lambda timeout
4. Enable `ReportBatchItemFailures` to avoid reprocessing successful messages
5. Use FIFO queues if you need ordering and built-in 5-minute deduplication''',
    ),
    (
        "thinking/debugging",
        r'''I'm getting "Access Denied" errors on my AWS S3 operations despite having what I think are the correct IAM permissions. The error is:

botocore.exceptions.ClientError: An error occurred (AccessDenied) when calling the PutObject operation: Access Denied

My IAM policy allows s3:PutObject on the bucket. What could be wrong?''',
        r'''<think>
S3 Access Denied is one of the most frustrating AWS errors because there are many possible causes:

1. IAM policy does not actually apply to this resource (ARN mismatch)
2. S3 bucket policy denies access
3. S3 Block Public Access settings
4. KMS encryption key permissions
5. VPC endpoint policy
6. SCP (Service Control Policy) at the organization level
7. The IAM role being used is not the one you think
8. Object-level permissions vs bucket-level permissions (need /* in ARN)
9. MFA delete requirement
10. Cross-account access without proper trust

Let me provide a systematic debugging approach.
</think>

S3 "Access Denied" has over a dozen possible causes. Here is a systematic debugging approach:

```python
import boto3
import json
from botocore.exceptions import ClientError

s3 = boto3.client("s3")
iam = boto3.client("iam")
sts = boto3.client("sts")

# ============================================================
# STEP 1: Verify who you actually are
# ============================================================

def check_identity():
    """Confirm which IAM identity is being used."""
    identity = sts.get_caller_identity()
    print(f"Account: {identity['Account']}")
    print(f"ARN:     {identity['Arn']}")
    print(f"UserId:  {identity['UserId']}")
    # Common surprise: you are using a different role than expected!

check_identity()

# ============================================================
# STEP 2: Check your IAM policy
# ============================================================

# COMMON MISTAKE: ARN does not include /*
# This allows bucket-level operations but NOT object operations:
WRONG_POLICY = {
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Action": ["s3:PutObject"],
        "Resource": "arn:aws:s3:::my-bucket",  # WRONG!
    }],
}

# This allows object operations:
CORRECT_POLICY = {
    "Version": "2012-10-17",
    "Statement": [{
        "Effect": "Allow",
        "Action": [
            "s3:PutObject",
            "s3:GetObject",
            "s3:DeleteObject",
        ],
        "Resource": "arn:aws:s3:::my-bucket/*",  # /* for objects
    }, {
        "Effect": "Allow",
        "Action": [
            "s3:ListBucket",  # ListBucket needs bucket ARN (no /*)
        ],
        "Resource": "arn:aws:s3:::my-bucket",
    }],
}

# ============================================================
# STEP 3: Check S3 bucket policy for explicit denies
# ============================================================

def check_bucket_policy(bucket_name):
    """Check if bucket policy has explicit denies."""
    try:
        policy = s3.get_bucket_policy(Bucket=bucket_name)
        policy_doc = json.loads(policy["Policy"])
        for stmt in policy_doc.get("Statement", []):
            if stmt.get("Effect") == "Deny":
                print(f"FOUND DENY: {json.dumps(stmt, indent=2)}")
                # Check if the deny applies to your identity
        print("Bucket policy:")
        print(json.dumps(policy_doc, indent=2))
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchBucketPolicy":
            print("No bucket policy (not the issue)")
        else:
            print(f"Cannot read bucket policy: {e}")

# ============================================================
# STEP 4: Check S3 Block Public Access
# ============================================================

def check_block_public_access(bucket_name):
    """Check if Block Public Access is interfering."""
    try:
        config = s3.get_public_access_block(Bucket=bucket_name)
        block = config["PublicAccessBlockConfiguration"]
        print(f"Block public ACLs:       {block['BlockPublicAcls']}")
        print(f"Ignore public ACLs:      {block['IgnorePublicAcls']}")
        print(f"Block public policy:     {block['BlockPublicPolicy']}")
        print(f"Restrict public buckets: {block['RestrictPublicBuckets']}")
    except ClientError:
        print("Cannot read Block Public Access settings")

# ============================================================
# STEP 5: Check KMS key permissions
# ============================================================

def check_kms_encryption(bucket_name):
    """Check if SSE-KMS is enabled and you have key access."""
    try:
        encryption = s3.get_bucket_encryption(Bucket=bucket_name)
        rules = encryption["ServerSideEncryptionConfiguration"]["Rules"]
        for rule in rules:
            sse = rule["ApplyServerSideEncryptionByDefault"]
            algo = sse.get("SSEAlgorithm", "unknown")
            key_id = sse.get("KMSMasterKeyID", "aws/s3")
            print(f"Encryption: {algo}, Key: {key_id}")
            if algo == "aws:kms" and key_id != "aws/s3":
                print(
                    "CUSTOM KMS KEY detected. You need kms:GenerateDataKey "
                    "and kms:Decrypt permissions on this key."
                )
                # Check KMS key policy:
                kms = boto3.client("kms")
                try:
                    key_policy = kms.get_key_policy(
                        KeyId=key_id, PolicyName="default"
                    )
                    print(f"Key policy: {key_policy['Policy'][:500]}...")
                except ClientError as e:
                    print(f"Cannot read KMS key policy: {e}")
    except ClientError as e:
        if "ServerSideEncryptionConfigurationNotFound" in str(e):
            print("No server-side encryption (not the issue)")
        else:
            print(f"Cannot check encryption: {e}")

# ============================================================
# STEP 6: Use IAM Policy Simulator
# ============================================================

def simulate_access(role_arn, action, resource_arn):
    """Use IAM Policy Simulator to check if action is allowed."""
    iam_client = boto3.client("iam")
    result = iam_client.simulate_principal_policy(
        PolicySourceArn=role_arn,
        ActionNames=[action],
        ResourceArns=[resource_arn],
    )
    for eval_result in result["EvaluationResults"]:
        decision = eval_result["EvalDecision"]
        print(f"Action: {eval_result['EvalActionName']}")
        print(f"Resource: {eval_result['EvalResourceName']}")
        print(f"Decision: {decision}")
        if decision != "allowed":
            # Show which policy denied access
            for detail in eval_result.get("MatchedStatements", []):
                print(f"  Matched: {detail.get('SourcePolicyId')}")

# simulate_access(
#     "arn:aws:iam::123456789:role/MyRole",
#     "s3:PutObject",
#     "arn:aws:s3:::my-bucket/my-key"
# )

# ============================================================
# STEP 7: Enable CloudTrail for detailed error info
# ============================================================
# CloudTrail logs include the exact reason for AccessDenied.
# Check CloudTrail > Event History > filter by:
#   Event name: PutObject
#   Error code: AccessDenied
# The "errorMessage" field shows exactly which policy denied access.

# Run all checks:
BUCKET = "my-bucket"
print("=== Identity ===")
check_identity()
print("\n=== Bucket Policy ===")
check_bucket_policy(BUCKET)
print("\n=== Block Public Access ===")
check_block_public_access(BUCKET)
print("\n=== Encryption ===")
check_kms_encryption(BUCKET)
```

**Most common causes (in order):**
1. ARN missing `/*` -- `s3:::bucket` vs `s3:::bucket/*`
2. Wrong IAM role being assumed (check `sts.get_caller_identity()`)
3. KMS key permissions missing for encrypted buckets
4. S3 bucket policy with explicit Deny
5. SCP (Organization-level policy) blocking the action''',
    ),
    (
        "thinking/debugging",
        r'''I need to debug IAM permissions in AWS. My application is getting sporadic "AccessDenied" errors that are hard to reproduce. How do I systematically trace which IAM policy is blocking my requests?''',
        r'''<think>
Debugging IAM permissions in AWS is notoriously difficult because:
1. Multiple policies can apply (identity-based, resource-based, SCPs, permission boundaries)
2. Explicit deny always wins
3. The error message does not tell you which policy denied access
4. Assume-role chains can obscure the actual permissions

The best tools are:
1. CloudTrail - shows detailed access logs including deny reasons
2. IAM Policy Simulator - test policies without making real API calls
3. IAM Access Analyzer - find overly permissive or restrictive policies
4. AWS Config - track permission changes over time
</think>

Debugging IAM permissions requires a systematic approach using multiple AWS tools. Here is a complete debugging workflow:

```python
import boto3
import json
from datetime import datetime, timedelta

sts = boto3.client("sts")
iam = boto3.client("iam")
cloudtrail = boto3.client("cloudtrail")

# ============================================================
# STEP 1: Establish identity chain
# ============================================================

def trace_identity():
    """Trace the full identity chain to find the effective role."""
    identity = sts.get_caller_identity()
    print("Current identity:")
    print(f"  Account: {identity['Account']}")
    print(f"  ARN: {identity['Arn']}")

    # If this is an assumed role, find the source
    arn = identity["Arn"]
    if ":assumed-role/" in arn:
        role_name = arn.split("/")[1]
        print(f"  Assumed role: {role_name}")

        # Get the role's trust policy
        role = iam.get_role(RoleName=role_name)
        trust = role["Role"]["AssumeRolePolicyDocument"]
        print(f"  Trust policy: {json.dumps(trust, indent=2)}")

        # List attached policies
        attached = iam.list_attached_role_policies(RoleName=role_name)
        print("  Attached managed policies:")
        for policy in attached["AttachedPolicies"]:
            print(f"    - {policy['PolicyName']} ({policy['PolicyArn']})")

        # List inline policies
        inline = iam.list_role_policies(RoleName=role_name)
        print("  Inline policies:")
        for name in inline["PolicyNames"]:
            print(f"    - {name}")
            doc = iam.get_role_policy(RoleName=role_name, PolicyName=name)
            print(f"      {json.dumps(doc['PolicyDocument'], indent=6)}")

        # Check permission boundary
        boundary = role["Role"].get("PermissionsBoundary")
        if boundary:
            print(f"  Permission boundary: {boundary['PermissionsBoundaryArn']}")
            print("  WARNING: Permission boundary limits effective permissions")

trace_identity()

# ============================================================
# STEP 2: Search CloudTrail for access denied events
# ============================================================

def find_access_denied_events(hours_back=24, max_results=20):
    """Search CloudTrail for recent AccessDenied events."""
    end_time = datetime.utcnow()
    start_time = end_time - timedelta(hours=hours_back)

    print(f"\nSearching CloudTrail for AccessDenied events "
          f"(last {hours_back} hours)...")

    events = cloudtrail.lookup_events(
        LookupAttributes=[{
            "AttributeKey": "EventName",
            "AttributeValue": "PutObject",  # Change to your failing API call
        }],
        StartTime=start_time,
        EndTime=end_time,
        MaxResults=max_results,
    )

    denied_events = []
    for event in events.get("Events", []):
        detail = json.loads(event["CloudTrailEvent"])
        error_code = detail.get("errorCode", "")
        if "Denied" in error_code or "Unauthorized" in error_code:
            denied_events.append(detail)
            print(f"\n  Time: {event['EventTime']}")
            print(f"  Event: {detail['eventName']}")
            print(f"  Error: {error_code}")
            print(f"  Message: {detail.get('errorMessage', 'N/A')}")
            print(f"  Identity: {detail['userIdentity'].get('arn', 'N/A')}")
            print(f"  Source IP: {detail.get('sourceIPAddress', 'N/A')}")

            # The request parameters show exactly what was attempted
            params = detail.get("requestParameters", {})
            print(f"  Request: {json.dumps(params)[:200]}")

    if not denied_events:
        print("  No AccessDenied events found in this time window.")

    return denied_events

# find_access_denied_events(hours_back=24)

# ============================================================
# STEP 3: IAM Policy Simulator
# ============================================================

def simulate_permissions(principal_arn, actions, resource_arns):
    """Test if a principal can perform actions on resources."""
    print(f"\nSimulating permissions for: {principal_arn}")

    for action in actions:
        for resource in resource_arns:
            result = iam.simulate_principal_policy(
                PolicySourceArn=principal_arn,
                ActionNames=[action],
                ResourceArns=[resource],
            )

            for eval_result in result["EvaluationResults"]:
                decision = eval_result["EvalDecision"]
                status = "ALLOWED" if decision == "allowed" else "DENIED"
                print(f"  {action} on {resource}: {status}")

                if decision != "allowed":
                    # Show which statements matched
                    for stmt in eval_result.get("MatchedStatements", []):
                        src = stmt.get("SourcePolicyId", "unknown")
                        print(f"    Denied by: {src}")

                    # Show missing permissions
                    missing = eval_result.get(
                        "MissingContextValues", []
                    )
                    if missing:
                        print(f"    Missing context: {missing}")

# simulate_permissions(
#     "arn:aws:iam::123456789:role/MyRole",
#     ["s3:PutObject", "s3:GetObject", "kms:GenerateDataKey"],
#     ["arn:aws:s3:::my-bucket/*"],
# )

# ============================================================
# STEP 4: Check all policy layers
# ============================================================

def check_all_policies(role_name):
    """Check every policy layer that could affect permissions."""

    print(f"\n=== Policy audit for role: {role_name} ===")

    # 1. Identity-based policies (attached to the role)
    print("\n1. Identity-based policies:")
    attached = iam.list_attached_role_policies(RoleName=role_name)
    for pol in attached["AttachedPolicies"]:
        version = iam.get_policy(PolicyArn=pol["PolicyArn"])
        vid = version["Policy"]["DefaultVersionId"]
        doc = iam.get_policy_version(
            PolicyArn=pol["PolicyArn"], VersionId=vid
        )
        statements = doc["PolicyVersion"]["Document"]["Statement"]
        for stmt in statements:
            effect = stmt.get("Effect", "Allow")
            actions = stmt.get("Action", [])
            resources = stmt.get("Resource", [])
            if effect == "Deny":
                print(f"  DENY in {pol['PolicyName']}:")
                print(f"    Actions: {actions}")
                print(f"    Resources: {resources}")

    # 2. Permission boundary
    role = iam.get_role(RoleName=role_name)
    boundary = role["Role"].get("PermissionsBoundary")
    if boundary:
        print(f"\n2. Permission boundary: {boundary['PermissionsBoundaryArn']}")
    else:
        print("\n2. No permission boundary (not the issue)")

    # 3. Organization SCPs
    try:
        orgs = boto3.client("organizations")
        policies = orgs.list_policies(Filter="SERVICE_CONTROL_POLICY")
        print(f"\n3. Organization SCPs: {len(policies['Policies'])} found")
        for pol in policies["Policies"]:
            if pol["Name"] != "FullAWSAccess":
                print(f"  SCP: {pol['Name']} - check for restrictions")
    except Exception:
        print("\n3. Cannot check SCPs (need organization access)")

    # 4. Session policies (for assumed roles)
    print("\n4. Session policies: check assume-role call for inline policy")

# check_all_policies("MyRole")
```

**Debugging priority order:**
1. Verify identity with `sts.get_caller_identity()` (you may be the wrong role)
2. Check CloudTrail for the specific `errorMessage` (most informative)
3. Run IAM Policy Simulator to test permissions without side effects
4. Check all policy layers: identity-based, resource-based, boundaries, SCPs
5. Look for explicit Deny statements (they override everything)''',
    ),
    (
        "thinking/debugging",
        r'''I am using CloudWatch Logs Insights to debug issues in my AWS Lambda functions but the queries are slow and I am not finding the information I need. What are effective CloudWatch Insights query patterns for debugging Lambda?''',
        r'''<think>
CloudWatch Logs Insights is powerful but the query syntax is not well-known. Common patterns for Lambda debugging include:
1. Finding errors and exceptions
2. Correlating by request ID
3. Measuring cold starts
4. Finding slow invocations
5. Analyzing memory usage
6. Tracking specific user/order IDs across invocations

Let me provide practical query examples.
</think>

CloudWatch Logs Insights has a specialized query language that is powerful for Lambda debugging. Here are the most useful patterns:

```python
# All queries below are for CloudWatch Logs Insights.
# Run them in the AWS Console or via boto3.

import boto3
import json
from datetime import datetime, timedelta

logs_client = boto3.client("logs")

def run_insights_query(log_group, query, hours_back=1):
    """Run a CloudWatch Logs Insights query and return results."""
    end_time = int(datetime.utcnow().timestamp())
    start_time = end_time - (hours_back * 3600)

    response = logs_client.start_query(
        logGroupName=log_group,
        startTime=start_time,
        endTime=end_time,
        queryString=query,
        limit=100,
    )
    query_id = response["queryId"]

    # Poll for results
    import time
    while True:
        result = logs_client.get_query_results(queryId=query_id)
        if result["status"] == "Complete":
            return result["results"]
        if result["status"] == "Failed":
            raise RuntimeError("Query failed")
        time.sleep(1)


LOG_GROUP = "/aws/lambda/my-function"

# ============================================================
# QUERY 1: Find all errors in the last hour
# ============================================================

FIND_ERRORS = """
fields @timestamp, @message, @requestId
| filter @message like /(?i)(error|exception|traceback|failed)/
| sort @timestamp desc
| limit 50
"""

# ============================================================
# QUERY 2: Find cold starts and measure duration
# ============================================================

COLD_STARTS = """
filter @type = "REPORT"
| fields @timestamp,
    @duration,
    @billedDuration,
    @memorySize,
    @maxMemoryUsed,
    @initDuration
| filter ispresent(@initDuration)
| stats count() as coldStarts,
    avg(@initDuration) as avgColdStartMs,
    max(@initDuration) as maxColdStartMs,
    pct(@initDuration, 95) as p95ColdStartMs
    by bin(1h)
| sort bin(1h) desc
"""

# ============================================================
# QUERY 3: Find slow invocations (> 5 seconds)
# ============================================================

SLOW_INVOCATIONS = """
filter @type = "REPORT"
| fields @requestId, @duration, @maxMemoryUsed, @memorySize
| filter @duration > 5000
| sort @duration desc
| limit 20
"""

# ============================================================
# QUERY 4: Memory usage analysis
# ============================================================

MEMORY_ANALYSIS = """
filter @type = "REPORT"
| stats
    avg(@maxMemoryUsed / @memorySize * 100) as avgMemoryPct,
    max(@maxMemoryUsed / @memorySize * 100) as maxMemoryPct,
    count() as invocations
    by bin(1h)
| sort bin(1h) desc
"""

# If avgMemoryPct > 80%, you need more memory.
# If avgMemoryPct < 30%, you are over-provisioned.

# ============================================================
# QUERY 5: Trace a specific request end-to-end
# ============================================================

TRACE_REQUEST = """
fields @timestamp, @message
| filter @requestId = "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
| sort @timestamp asc
"""

# ============================================================
# QUERY 6: Find timeouts
# ============================================================

FIND_TIMEOUTS = """
filter @message like "Task timed out"
    or @message like "Duration:"
    and @duration > 29000
| fields @timestamp, @requestId, @duration, @message
| sort @timestamp desc
| limit 20
"""

# ============================================================
# QUERY 7: Error rate over time
# ============================================================

ERROR_RATE = """
filter @type = "REPORT"
| stats
    sum(strcontains(@message, "Error")) as errors,
    count() as total,
    sum(strcontains(@message, "Error")) / count() * 100 as errorRate
    by bin(5m)
| sort bin(5m) desc
"""

# ============================================================
# QUERY 8: Search structured JSON logs
# ============================================================

# If your Lambda uses structured logging (JSON):
# {"level": "error", "message": "DB failed", "user_id": "123"}

JSON_SEARCH = """
fields @timestamp, level, message, user_id, order_id
| filter level = "error"
| filter user_id = "12345"
| sort @timestamp desc
| limit 50
"""

# ============================================================
# QUERY 9: Invocation cost analysis
# ============================================================

COST_ANALYSIS = """
filter @type = "REPORT"
| stats
    count() as invocations,
    sum(@billedDuration) as totalBilledMs,
    avg(@billedDuration) as avgBilledMs,
    sum(@billedDuration / 1000 * @memorySize / 1024 * 0.0000166667)
        as estimatedCostUSD
    by bin(1d)
| sort bin(1d) desc
"""

# ============================================================
# USAGE: Run queries programmatically
# ============================================================

results = run_insights_query(LOG_GROUP, FIND_ERRORS, hours_back=1)
for row in results:
    fields = {f["field"]: f["value"] for f in row}
    print(f"{fields.get('@timestamp', 'N/A')}: {fields.get('@message', 'N/A')[:100]}")

# ============================================================
# TIPS FOR FASTER QUERIES
# ============================================================
# 1. Always add a time range (shorter = faster)
# 2. Use "filter" before "fields" to reduce scanning
# 3. Use "limit" to cap results
# 4. Query specific log groups, not all groups
# 5. Use structured JSON logging for better filtering
# 6. Create Contributor Insights rules for ongoing monitoring
```

**Best practices for Lambda logging:**
1. Use structured JSON logging (`json.dumps({"level": "error", ...})`)
2. Include `requestId` in all log entries for tracing
3. Log timing for critical operations (DB calls, API calls)
4. Set up CloudWatch Alarms on error rate using metric filters
5. Use `@initDuration` to monitor cold start trends''',
    ),
]
