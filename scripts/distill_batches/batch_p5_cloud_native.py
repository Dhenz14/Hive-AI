"""
Batch P5 — Cloud-Native Patterns
Covers: serverless architecture, container orchestration beyond K8s,
Infrastructure as Code, service mesh, multi-cloud strategies.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    # --- 1. Serverless Architecture Deep Dive ---
    (
        "cloud-native/serverless-architecture",
        "Explain serverless architecture patterns in depth including cold start optimization strategies, provisioned concurrency configuration, event-driven design with fan-out and fan-in, and build a complete Python AWS Lambda application with API Gateway integration, DynamoDB data layer, structured logging, middleware patterns, and proper error handling for production workloads.",
        r"""# Serverless Architecture: Cold Starts, Event-Driven Patterns, and Production Lambda

## The Serverless Execution Model

Serverless computing fundamentally changes how we think about infrastructure. Instead of provisioning servers and paying for idle capacity, you pay only for actual compute time measured in milliseconds. **However**, this model introduces unique challenges that traditional architectures do not face — cold starts, execution time limits, statelessness constraints, and vendor-specific integration patterns.

The core insight is that serverless is not "no servers" but rather **servers you do not manage**. AWS Lambda, for example, runs your code inside a micro-VM (Firecracker), which AWS provisions, patches, and scales automatically. The **trade-off** is that you lose control over the execution environment in exchange for operational simplicity. This trade-off is worth it for event-driven workloads, APIs with variable traffic, and data processing pipelines — but it is a **common mistake** to force serverless onto latency-sensitive or long-running workloads where containers or VMs are a better fit.

## Cold Start Mechanics and Optimization

A cold start occurs when Lambda must initialize a new execution environment. This involves downloading your deployment package, starting the runtime, and running your initialization code. The total cold start latency depends on several factors:

```
Cold Start Breakdown (typical Python Lambda):
  1. Firecracker microVM spin-up:   ~30-50ms  (AWS internal, not controllable)
  2. Runtime initialization:         ~50-100ms (Python interpreter startup)
  3. Deployment package download:    ~50-500ms (depends on package size)
  4. Module imports:                 ~100-2000ms (depends on dependencies)
  5. Handler init code:              ~10-500ms (DB connections, config loading)

  Total cold start:                  ~240-3150ms
  Warm invocation:                   ~1-10ms (reuses existing environment)
```

**Best practice**: Minimize deployment package size. Every megabyte of dependencies adds cold start latency. Use Lambda layers for shared libraries and strip unnecessary files from packages. Because Python imports are lazy by default, importing heavy libraries like `boto3` at module level versus inside the handler makes a significant difference — module-level imports happen during cold start but are cached for warm invocations.

### Provisioned Concurrency Configuration

For latency-critical paths, provisioned concurrency keeps execution environments warm. This effectively eliminates cold starts but costs money for idle environments. **Therefore**, apply it surgically only to your hot paths.

```python
# serverless_config.py
# Infrastructure configuration for provisioned concurrency
# using AWS SAM template (template.yaml equivalent in Python dict form)

import json
from typing import Any

def generate_sam_template(
    function_name: str,
    provisioned_count: int,
    memory_mb: int = 512,
    timeout_seconds: int = 30,
    reserved_concurrent: int = 100,
) -> dict[str, Any]:
    # Generate a SAM-compatible CloudFormation template
    # with provisioned concurrency and auto-scaling
    template: dict[str, Any] = {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Transform": "AWS::Serverless-2016-10-31",
        "Globals": {
            "Function": {
                "Runtime": "python3.12",
                "MemorySize": memory_mb,
                "Timeout": timeout_seconds,
                "Tracing": "Active",
                "Environment": {
                    "Variables": {
                        "LOG_LEVEL": "INFO",
                        "POWERTOOLS_SERVICE_NAME": function_name,
                    }
                },
            }
        },
        "Resources": {
            function_name: {
                "Type": "AWS::Serverless::Function",
                "Properties": {
                    "Handler": "app.handler",
                    "CodeUri": f"src/{function_name}/",
                    "ReservedConcurrentExecutions": reserved_concurrent,
                    "ProvisionedConcurrencyConfig": {
                        "ProvisionedConcurrentExecutions": provisioned_count
                    },
                    "AutoPublishAlias": "live",
                    "Events": {
                        "ApiEvent": {
                            "Type": "Api",
                            "Properties": {
                                "Path": f"/{function_name.lower()}/{{proxy+}}",
                                "Method": "ANY",
                            },
                        }
                    },
                },
            },
            # Auto-scaling for provisioned concurrency
            f"{function_name}ScalableTarget": {
                "Type": "AWS::ApplicationAutoScaling::ScalableTarget",
                "Properties": {
                    "MaxCapacity": reserved_concurrent,
                    "MinCapacity": provisioned_count,
                    "ResourceId": f"function:{function_name}:live",
                    "ScalableDimension": "lambda:function:ProvisionedConcurrency",
                    "ServiceNamespace": "lambda",
                },
            },
            f"{function_name}ScalingPolicy": {
                "Type": "AWS::ApplicationAutoScaling::ScalingPolicy",
                "Properties": {
                    "PolicyName": f"{function_name}-utilization-policy",
                    "PolicyType": "TargetTrackingScaling",
                    "ScalableTargetId": {"Ref": f"{function_name}ScalableTarget"},
                    "TargetTrackingScalingPolicyConfiguration": {
                        "TargetValue": 0.7,
                        "PredefinedMetricSpecification": {
                            "PredefinedMetricType": "LambdaProvisionedConcurrencyUtilization"
                        },
                    },
                },
            },
        },
    }
    return template


def validate_provisioned_config(config: dict[str, Any]) -> list[str]:
    # Validate provisioned concurrency settings for common pitfalls
    errors: list[str] = []
    resources = config.get("Resources", {})
    for name, resource in resources.items():
        props = resource.get("Properties", {})
        if "ProvisionedConcurrencyConfig" in props:
            pc = props["ProvisionedConcurrencyConfig"]["ProvisionedConcurrentExecutions"]
            reserved = props.get("ReservedConcurrentExecutions", 1000)
            if pc > reserved:
                errors.append(
                    f"{name}: provisioned ({pc}) exceeds reserved ({reserved})"
                )
            if pc < 1:
                errors.append(f"{name}: provisioned must be >= 1, got {pc}")
    return errors
```

## Event-Driven Fan-Out and Fan-In

Serverless excels at event-driven architectures where events trigger independent processing pipelines. The **fan-out** pattern distributes work across parallel Lambda invocations, while **fan-in** aggregates results. A **pitfall** here is assuming all invocations complete — you must handle partial failures.

## Complete Production Lambda Application

```python
# app.py
# Production-grade Lambda handler with API Gateway, DynamoDB,
# middleware, structured logging, and comprehensive error handling

from __future__ import annotations

import json
import os
import time
import uuid
import traceback
import logging
from decimal import Decimal
from typing import Any, Callable
from functools import wraps

import boto3
from boto3.dynamodb.conditions import Key, Attr

# Module-level initialization (runs once during cold start)
# This is a best practice because these are reused across warm invocations
logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))

# Connection reuse: initialize clients at module level
_dynamodb = boto3.resource("dynamodb")
_table = _dynamodb.Table(os.environ.get("TABLE_NAME", "items"))
_sqs = boto3.client("sqs")

COLD_START = True


class AppError(Exception):
    # Application-level error with HTTP status code
    def __init__(self, message: str, status_code: int = 400, error_code: str = "BAD_REQUEST"):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


def api_response(status_code: int, body: Any, headers: dict[str, str] | None = None) -> dict:
    # Build a properly formatted API Gateway response
    default_headers = {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
        "X-Request-Id": str(uuid.uuid4()),
    }
    if headers:
        default_headers.update(headers)
    return {
        "statusCode": status_code,
        "headers": default_headers,
        "body": json.dumps(body, default=str),
    }


def middleware_chain(*middlewares: Callable) -> Callable:
    # Compose multiple middleware functions into a processing chain.
    # Each middleware receives (event, context) and can modify or short-circuit.
    def decorator(handler_func: Callable) -> Callable:
        @wraps(handler_func)
        def wrapper(event: dict, context: Any) -> dict:
            for mw in middlewares:
                result = mw(event, context)
                if result is not None:
                    return result  # Middleware short-circuited
            return handler_func(event, context)
        return wrapper
    return decorator


def log_middleware(event: dict, context: Any) -> dict | None:
    # Structured logging middleware
    global COLD_START
    logger.info(json.dumps({
        "message": "request_started",
        "method": event.get("httpMethod"),
        "path": event.get("path"),
        "cold_start": COLD_START,
        "request_id": context.aws_request_id if context else "local",
        "remaining_ms": context.get_remaining_time_in_millis() if context else 0,
    }))
    COLD_START = False
    return None  # Continue chain


def auth_middleware(event: dict, context: Any) -> dict | None:
    # Simple API key authentication middleware
    headers = event.get("headers") or {}
    api_key = headers.get("x-api-key") or headers.get("X-Api-Key")
    if not api_key:
        return api_response(401, {"error": "Missing API key", "code": "UNAUTHORIZED"})
    # In production, validate against Secrets Manager or parameter store
    return None  # Continue chain


def rate_limit_middleware(event: dict, context: Any) -> dict | None:
    # Token bucket rate limiting using DynamoDB
    source_ip = (event.get("requestContext", {})
                 .get("identity", {})
                 .get("sourceIp", "unknown"))
    # Simplified: in production use DynamoDB atomic counters
    return None  # Continue chain


class ItemService:
    # Service layer for item CRUD operations against DynamoDB.
    # Separating business logic from the handler improves testability.

    def __init__(self, table: Any) -> None:
        self.table = table

    def create_item(self, data: dict[str, Any]) -> dict[str, Any]:
        # Create a new item with generated ID and timestamps
        item_id = str(uuid.uuid4())
        now = int(time.time())
        item = {
            "pk": f"ITEM#{item_id}",
            "sk": "METADATA",
            "item_id": item_id,
            "created_at": now,
            "updated_at": now,
            "gsi1pk": f"STATUS#{data.get('status', 'active')}",
            "gsi1sk": str(now),
            **{k: v for k, v in data.items() if k not in ("pk", "sk")},
        }
        # Convert floats to Decimal for DynamoDB compatibility
        item = self._sanitize_for_dynamo(item)
        self.table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(pk)",
        )
        logger.info(json.dumps({"message": "item_created", "item_id": item_id}))
        return item

    def get_item(self, item_id: str) -> dict[str, Any] | None:
        # Retrieve item by ID using consistent read for accuracy
        response = self.table.get_item(
            Key={"pk": f"ITEM#{item_id}", "sk": "METADATA"},
            ConsistentRead=True,
        )
        return response.get("Item")

    def list_items(
        self, status: str = "active", limit: int = 20, last_key: str | None = None
    ) -> dict[str, Any]:
        # List items by status using GSI with pagination
        kwargs: dict[str, Any] = {
            "IndexName": "gsi1-index",
            "KeyConditionExpression": Key("gsi1pk").eq(f"STATUS#{status}"),
            "Limit": limit,
            "ScanIndexForward": False,
        }
        if last_key:
            kwargs["ExclusiveStartKey"] = json.loads(last_key)
        response = self.table.query(**kwargs)
        result: dict[str, Any] = {"items": response.get("Items", [])}
        if "LastEvaluatedKey" in response:
            result["next_token"] = json.dumps(response["LastEvaluatedKey"], default=str)
        return result

    def _sanitize_for_dynamo(self, obj: Any) -> Any:
        # Recursively convert floats to Decimal for DynamoDB
        if isinstance(obj, float):
            return Decimal(str(obj))
        if isinstance(obj, dict):
            return {k: self._sanitize_for_dynamo(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._sanitize_for_dynamo(i) for i in obj]
        return obj


# Initialize service at module level for connection reuse
_service = ItemService(_table)


@middleware_chain(log_middleware, auth_middleware, rate_limit_middleware)
def handler(event: dict, context: Any) -> dict:
    # Main Lambda handler with routing
    method = event.get("httpMethod", "GET")
    path = event.get("path", "/")
    path_params = event.get("pathParameters") or {}

    try:
        if method == "POST" and "/items" in path:
            body = json.loads(event.get("body") or "{}")
            item = _service.create_item(body)
            return api_response(201, {"item": item})

        elif method == "GET" and "item_id" in path_params:
            item = _service.get_item(path_params["item_id"])
            if not item:
                raise AppError("Item not found", 404, "NOT_FOUND")
            return api_response(200, {"item": item})

        elif method == "GET" and "/items" in path:
            qs = event.get("queryStringParameters") or {}
            result = _service.list_items(
                status=qs.get("status", "active"),
                limit=int(qs.get("limit", "20")),
                last_key=qs.get("next_token"),
            )
            return api_response(200, result)

        else:
            return api_response(404, {"error": "Route not found"})

    except AppError as e:
        return api_response(e.status_code, {"error": str(e), "code": e.error_code})
    except json.JSONDecodeError:
        return api_response(400, {"error": "Invalid JSON body"})
    except Exception:
        logger.error(traceback.format_exc())
        return api_response(500, {"error": "Internal server error"})
```

## Testing Serverless Functions Locally

Testing Lambda functions requires mocking AWS services. The **best practice** is to design your code with dependency injection so you can swap DynamoDB for a local mock.

```python
# test_app.py
# Unit tests for Lambda handler using moto for DynamoDB mocking

import json
import os
import pytest

os.environ["TABLE_NAME"] = "test-items"
os.environ["LOG_LEVEL"] = "DEBUG"

from unittest.mock import MagicMock
import boto3
# moto mocks AWS services locally
from moto import mock_aws


@mock_aws
def setup_dynamodb():
    # Create a test DynamoDB table matching production schema
    client = boto3.client("dynamodb", region_name="us-east-1")
    client.create_table(
        TableName="test-items",
        KeySchema=[
            {"AttributeName": "pk", "KeyType": "HASH"},
            {"AttributeName": "sk", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "pk", "AttributeType": "S"},
            {"AttributeName": "sk", "AttributeType": "S"},
            {"AttributeName": "gsi1pk", "AttributeType": "S"},
            {"AttributeName": "gsi1sk", "AttributeType": "S"},
        ],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "gsi1-index",
                "KeySchema": [
                    {"AttributeName": "gsi1pk", "KeyType": "HASH"},
                    {"AttributeName": "gsi1sk", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        BillingMode="PAY_PER_REQUEST",
    )
    return boto3.resource("dynamodb", region_name="us-east-1").Table("test-items")


@mock_aws
def test_create_and_get_item():
    table = setup_dynamodb()
    from app import ItemService

    svc = ItemService(table)
    created = svc.create_item({"name": "Test Widget", "price": 29.99})
    assert "item_id" in created
    assert created["name"] == "Test Widget"

    fetched = svc.get_item(created["item_id"])
    assert fetched is not None
    assert fetched["name"] == "Test Widget"


@mock_aws
def test_handler_missing_api_key():
    # Handler should reject requests without an API key
    from app import handler

    event = {
        "httpMethod": "GET",
        "path": "/items",
        "headers": {},
        "requestContext": {"identity": {"sourceIp": "127.0.0.1"}},
    }
    context = MagicMock()
    context.aws_request_id = "test-123"
    context.get_remaining_time_in_millis.return_value = 30000

    response = handler(event, context)
    assert response["statusCode"] == 401
    body = json.loads(response["body"])
    assert body["code"] == "UNAUTHORIZED"
```

## Summary and Key Takeaways

- **Cold starts** are the primary latency concern in serverless; mitigate with small packages, provisioned concurrency on hot paths, and module-level initialization for connection reuse.
- **Provisioned concurrency** eliminates cold starts but costs money — apply it only where latency SLAs demand it and use auto-scaling to avoid over-provisioning.
- **Event-driven fan-out/fan-in** is the natural serverless pattern; design for partial failures by using dead letter queues and idempotency keys.
- **Best practice**: Separate business logic (service classes) from Lambda handler glue code to enable local testing without full AWS emulation.
- **Pitfall**: Do not put connection initialization inside the handler function — place it at module level so warm invocations reuse existing connections.
- The middleware pattern keeps cross-cutting concerns (logging, auth, rate limiting) composable and testable, therefore reducing handler complexity.
"""
    ),

    # --- 2. Container Orchestration Beyond K8s ---
    (
        "cloud-native/container-orchestration-beyond-k8s",
        "Compare container orchestration platforms beyond Kubernetes including HashiCorp Nomad and AWS ECS, covering task definitions, resource management, scheduling algorithms, and build a Go implementation of a simplified task scheduler that demonstrates bin-packing, affinity rules, and health checking for understanding orchestration internals.",
        r"""# Container Orchestration Beyond Kubernetes: Nomad, ECS, and Scheduler Internals

## Why Look Beyond Kubernetes?

Kubernetes has become the default container orchestrator, but it is not always the right tool. Its operational complexity — etcd management, API server scaling, CRD sprawl, RBAC policies, network plugins — makes it overkill for many workloads. **However**, alternatives like HashiCorp Nomad and AWS ECS offer compelling trade-offs that are worth understanding.

**Common mistake**: Teams adopt Kubernetes because it is the industry standard without evaluating whether their workload complexity justifies K8s operational overhead. A team running 10 microservices does not need the same orchestration platform as a team running 500. **Therefore**, understanding the alternatives helps you make informed architectural decisions.

## Nomad vs ECS vs Kubernetes: Architecture Comparison

```
Feature Comparison Matrix:

                    Kubernetes        Nomad              ECS
Architecture:       Control plane +   Single binary      AWS managed
                    etcd + kubelet    + agents            control plane
Scheduling:         kube-scheduler    Built-in eval      Proprietary
                    (bin-packing,     engine (bin-pack,   (binpack, spread,
                    spread)           spread, custom)     random)
Service Discovery:  CoreDNS + kube-   Consul (optional)  CloudMap / ALB
                    proxy/services    or built-in
Secrets:            K8s Secrets       Vault native        SSM / Secrets Mgr
                    (base64, not      (encrypted,         (encrypted, IAM
                    encrypted)        rotatable)          integrated)
Multi-region:       Federation        Native multi-       Cross-region via
                    (complex)         region/datacenter   Global Accelerator
Non-container:      Poor (VMs via     Native: Docker,     Containers only
                    KubeVirt)         exec, Java, QEMU    (Fargate / EC2)
Learning curve:     Steep             Moderate            Low (AWS native)
Operational cost:   High              Low-Medium          Low (managed)
```

## AWS ECS Task Definition Deep Dive

ECS uses task definitions as the atomic unit of deployment — analogous to a K8s Pod spec but integrated with the AWS ecosystem. **Best practice**: Use Fargate for stateless workloads to avoid EC2 instance management, and EC2 launch type only for GPU or specialized hardware needs.

```json
// ecs-task-definition.json
// Complete ECS task definition with sidecar pattern, logging, and secrets
{
  "family": "api-service",
  "networkMode": "awsvpc",
  "requiresCompatibilities": ["FARGATE"],
  "cpu": "512",
  "memory": "1024",
  "executionRoleArn": "arn:aws:iam::123456789:role/ecsTaskExecutionRole",
  "taskRoleArn": "arn:aws:iam::123456789:role/apiServiceTaskRole",
  "containerDefinitions": [
    {
      "name": "api",
      "image": "123456789.dkr.ecr.us-east-1.amazonaws.com/api:v1.2.3",
      "essential": true,
      "portMappings": [
        {"containerPort": 8080, "protocol": "tcp"}
      ],
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:8080/health || exit 1"],
        "interval": 15,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 30
      },
      "environment": [
        {"name": "PORT", "value": "8080"},
        {"name": "ENV", "value": "production"}
      ],
      "secrets": [
        {"name": "DB_URL", "valueFrom": "arn:aws:ssm:us-east-1:123456789:parameter/prod/db-url"},
        {"name": "API_KEY", "valueFrom": "arn:aws:secretsmanager:us-east-1:123456789:secret:api-key"}
      ],
      "logConfiguration": {
        "logDriver": "awslogs",
        "options": {
          "awslogs-group": "/ecs/api-service",
          "awslogs-region": "us-east-1",
          "awslogs-stream-prefix": "api"
        }
      },
      "dependsOn": [
        {"containerName": "envoy-proxy", "condition": "HEALTHY"}
      ]
    },
    {
      "name": "envoy-proxy",
      "image": "envoyproxy/envoy:v1.28-latest",
      "essential": true,
      "portMappings": [
        {"containerPort": 9901, "protocol": "tcp"}
      ],
      "healthCheck": {
        "command": ["CMD-SHELL", "curl -f http://localhost:9901/ready || exit 1"],
        "interval": 10,
        "timeout": 5,
        "retries": 3,
        "startPeriod": 15
      },
      "memory": 256,
      "cpu": 128
    }
  ]
}
```

## HashiCorp Nomad Job Specification

Nomad's job specification is simpler than Kubernetes manifests, **because** it does not require separate Service, Deployment, ConfigMap, and Ingress resources — everything is declared in a single job file.

```hcl
# nomad-job.hcl
# Nomad job specification with rolling deployment, health checks,
# resource constraints, and Consul service mesh integration

job "api-service" {
  datacenters = ["dc1", "dc2"]
  type        = "service"

  # Rolling update strategy
  update {
    max_parallel     = 2
    health_check     = "checks"
    min_healthy_time = "30s"
    healthy_deadline = "5m"
    auto_revert      = true
    canary           = 1
  }

  # Spread across availability zones
  spread {
    attribute = "${node.datacenter}"
    weight    = 100
  }

  group "api" {
    count = 6

    network {
      port "http" { to = 8080 }
      port "metrics" { to = 9090 }
    }

    # Consul Connect service mesh
    service {
      name = "api-service"
      port = "http"

      connect {
        sidecar_service {
          proxy {
            upstreams {
              destination_name = "database"
              local_bind_port  = 5432
            }
          }
        }
      }

      check {
        type     = "http"
        path     = "/health"
        interval = "10s"
        timeout  = "3s"
      }
    }

    task "api" {
      driver = "docker"

      config {
        image = "registry.example.com/api:v1.2.3"
        ports = ["http", "metrics"]
      }

      resources {
        cpu    = 500   # MHz
        memory = 512   # MB
      }

      # Vault secrets integration
      vault {
        policies = ["api-service"]
      }

      template {
        data = <<-EOF
          DB_URL={{ with secret "database/creds/api" }}{{ .Data.connection_url }}{{ end }}
          API_KEY={{ with secret "secret/data/api-key" }}{{ .Data.data.value }}{{ end }}
        EOF
        destination = "secrets/env"
        env         = true
      }
    }
  }
}
```

## Go Implementation: A Simplified Task Scheduler

Understanding orchestration internals requires building one. The following Go implementation demonstrates the core scheduling concepts: **bin-packing** (fitting tasks onto nodes efficiently), **affinity rules** (preferring certain nodes), and **health checking** (detecting and replacing failed tasks).

```go
package scheduler

import (
	"context"
	"fmt"
	"log"
	"sort"
	"sync"
	"time"
)

// Resource represents allocatable compute resources on a node.
type Resource struct {
	CPUMillis  int64 // CPU in millicores (1000 = 1 core)
	MemoryMB   int64 // Memory in megabytes
	DiskMB     int64 // Ephemeral disk in megabytes
}

// Sub subtracts another resource from this one, returning the remainder.
func (r Resource) Sub(other Resource) Resource {
	return Resource{
		CPUMillis: r.CPUMillis - other.CPUMillis,
		MemoryMB:  r.MemoryMB - other.MemoryMB,
		DiskMB:    r.DiskMB - other.DiskMB,
	}
}

// Fits checks whether the given resource request fits within available capacity.
func (r Resource) Fits(request Resource) bool {
	return r.CPUMillis >= request.CPUMillis &&
		r.MemoryMB >= request.MemoryMB &&
		r.DiskMB >= request.DiskMB
}

// Score computes a bin-packing score: higher means the node is more tightly packed
// after placing this task (therefore wasting less capacity).
func (r Resource) BinPackScore(request Resource) float64 {
	remaining := r.Sub(request)
	cpuUtil := 1.0 - float64(remaining.CPUMillis)/float64(r.CPUMillis+1)
	memUtil := 1.0 - float64(remaining.MemoryMB)/float64(r.MemoryMB+1)
	// Weighted average: memory is typically the bottleneck
	return cpuUtil*0.4 + memUtil*0.6
}

// Node represents a worker machine in the cluster.
type Node struct {
	ID         string
	Labels     map[string]string
	Total      Resource
	Allocated  Resource
	Healthy    bool
	LastHealth time.Time
}

// Available returns the remaining allocatable resources.
func (n *Node) Available() Resource {
	return n.Total.Sub(n.Allocated)
}

// TaskState represents the current state of a scheduled task.
type TaskState int

const (
	TaskPending TaskState = iota
	TaskRunning
	TaskFailed
	TaskCompleted
)

// Task represents a unit of work to be scheduled.
type Task struct {
	ID        string
	Group     string            // Grouping for anti-affinity
	Request   Resource          // Resource requirements
	Affinity  map[string]string // Preferred node labels
	NodeID    string            // Assigned node (empty if unscheduled)
	State     TaskState
	HealthURL string            // HTTP endpoint for health checks
	Retries   int
	MaxRetry  int
}

// ScheduleResult captures the outcome of a scheduling attempt.
type ScheduleResult struct {
	TaskID string
	NodeID string
	Score  float64
	Err    error
}

// Scheduler is the core orchestration engine that assigns tasks to nodes.
type Scheduler struct {
	mu    sync.RWMutex
	nodes map[string]*Node
	tasks map[string]*Task
}

// NewScheduler creates a new scheduler instance.
func NewScheduler() *Scheduler {
	return &Scheduler{
		nodes: make(map[string]*Node),
		tasks: make(map[string]*Task),
	}
}

// RegisterNode adds a node to the cluster.
func (s *Scheduler) RegisterNode(node *Node) {
	s.mu.Lock()
	defer s.mu.Unlock()
	node.Healthy = true
	node.LastHealth = time.Now()
	s.nodes[node.ID] = node
	log.Printf("[scheduler] Node registered: %s (cpu=%d mem=%d)",
		node.ID, node.Total.CPUMillis, node.Total.MemoryMB)
}

// Schedule assigns a task to the best available node using bin-packing
// with affinity scoring. This is the heart of the scheduling algorithm.
func (s *Scheduler) Schedule(task *Task) ScheduleResult {
	s.mu.Lock()
	defer s.mu.Unlock()

	type candidate struct {
		node  *Node
		score float64
	}

	var candidates []candidate

	for _, node := range s.nodes {
		// Filter: skip unhealthy nodes
		if !node.Healthy {
			continue
		}
		// Filter: check resource capacity
		if !node.Available().Fits(task.Request) {
			continue
		}
		// Filter: anti-affinity — avoid colocating tasks in the same group
		if s.hasGroupConflict(node.ID, task.Group) {
			continue
		}

		// Score: bin-packing efficiency
		binScore := node.Available().BinPackScore(task.Request)

		// Score: affinity bonus for matching labels
		affinityScore := 0.0
		for key, val := range task.Affinity {
			if node.Labels[key] == val {
				affinityScore += 0.2
			}
		}

		totalScore := binScore*0.7 + affinityScore*0.3
		candidates = append(candidates, candidate{node: node, score: totalScore})
	}

	if len(candidates) == 0 {
		return ScheduleResult{
			TaskID: task.ID,
			Err:    fmt.Errorf("no feasible node for task %s (cpu=%d mem=%d)",
				task.ID, task.Request.CPUMillis, task.Request.MemoryMB),
		}
	}

	// Sort by score descending: highest score = best fit
	sort.Slice(candidates, func(i, j int) bool {
		return candidates[i].score > candidates[j].score
	})

	best := candidates[0]
	// Allocate resources on the chosen node
	best.node.Allocated.CPUMillis += task.Request.CPUMillis
	best.node.Allocated.MemoryMB += task.Request.MemoryMB
	best.node.Allocated.DiskMB += task.Request.DiskMB

	task.NodeID = best.node.ID
	task.State = TaskRunning
	s.tasks[task.ID] = task

	log.Printf("[scheduler] Task %s -> Node %s (score=%.3f)", task.ID, best.node.ID, best.score)
	return ScheduleResult{TaskID: task.ID, NodeID: best.node.ID, Score: best.score}
}

// hasGroupConflict checks if any running task in the same group is on this node.
func (s *Scheduler) hasGroupConflict(nodeID, group string) bool {
	if group == "" {
		return false
	}
	for _, t := range s.tasks {
		if t.NodeID == nodeID && t.Group == group && t.State == TaskRunning {
			return true
		}
	}
	return false
}

// Deallocate releases resources when a task completes or is evicted.
func (s *Scheduler) Deallocate(taskID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()

	task, ok := s.tasks[taskID]
	if !ok {
		return fmt.Errorf("task %s not found", taskID)
	}
	node, ok := s.nodes[task.NodeID]
	if !ok {
		return fmt.Errorf("node %s not found for task %s", task.NodeID, taskID)
	}

	node.Allocated.CPUMillis -= task.Request.CPUMillis
	node.Allocated.MemoryMB -= task.Request.MemoryMB
	node.Allocated.DiskMB -= task.Request.DiskMB
	task.State = TaskCompleted
	return nil
}

// HealthCheckLoop runs periodic health checks and reschedules failed tasks.
// This demonstrates the reconciliation loop pattern used by all orchestrators.
func (s *Scheduler) HealthCheckLoop(ctx context.Context, interval time.Duration) {
	ticker := time.NewTicker(interval)
	defer ticker.Stop()

	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			s.reconcile()
		}
	}
}

// reconcile checks all tasks and reschedules any that have failed.
func (s *Scheduler) reconcile() {
	s.mu.RLock()
	var failedTasks []*Task
	for _, task := range s.tasks {
		if task.State == TaskFailed && task.Retries < task.MaxRetry {
			failedTasks = append(failedTasks, task)
		}
	}
	s.mu.RUnlock()

	for _, task := range failedTasks {
		log.Printf("[reconcile] Rescheduling failed task %s (attempt %d/%d)",
			task.ID, task.Retries+1, task.MaxRetry)
		_ = s.Deallocate(task.ID)
		task.Retries++
		task.State = TaskPending
		result := s.Schedule(task)
		if result.Err != nil {
			log.Printf("[reconcile] Failed to reschedule %s: %v", task.ID, result.Err)
		}
	}
}
```

## Summary and Key Takeaways

- **Kubernetes is not the only option**: Nomad offers simpler operations with native Vault/Consul integration, while ECS provides a fully managed experience tightly coupled to AWS.
- **Best practice**: Choose your orchestrator based on team size, operational maturity, and workload complexity — not industry hype.
- **Bin-packing** maximizes resource utilization by preferring nodes that will be most tightly packed after placement, **therefore** reducing the total number of nodes needed.
- **Affinity and anti-affinity** rules control task placement for performance (co-locate with data) and resilience (spread across failure domains).
- **Pitfall**: Health check intervals that are too aggressive cause flapping; too lenient means slow failure detection. A 10-15 second interval with 3 retries is a solid starting point.
- The **reconciliation loop** is the fundamental pattern in all orchestrators — continuously comparing desired state to actual state and taking corrective action.
"""
    ),

    # --- 3. Infrastructure as Code Comparison ---
    (
        "cloud-native/infrastructure-as-code-comparison",
        "Compare Infrastructure as Code tools including Terraform, Pulumi, and AWS CDK in depth covering state management strategies, drift detection mechanisms, testing approaches for infrastructure code, and provide a complete Python AWS CDK example that deploys a production-grade VPC, ECS Fargate service, and RDS database with proper networking, security groups, and monitoring.",
        r"""# Infrastructure as Code: Terraform vs Pulumi vs CDK

## The IaC Landscape

Infrastructure as Code has evolved from simple shell scripts to sophisticated frameworks that model infrastructure as declarative specifications or imperative programs. The three dominant approaches — **Terraform** (HCL-based declarative), **Pulumi** (general-purpose language imperative), and **AWS CDK** (TypeScript/Python imperative generating CloudFormation) — each make different trade-offs around expressiveness, portability, and ecosystem maturity.

**Because** the choice of IaC tool affects your team's velocity for years, understanding these trade-offs deeply is more valuable than picking whatever is trending. A **common mistake** is choosing Terraform for everything when CDK would be simpler for an AWS-only shop, or choosing Pulumi without considering that your team already knows HCL.

## Architecture and State Management

```
State Management Comparison:

Terraform:
  - State file: terraform.tfstate (JSON)
  - Backends: S3+DynamoDB (locking), Terraform Cloud, Consul, GCS, azurerm
  - Locking: DynamoDB conditional writes, Consul sessions
  - State operations: terraform state mv/rm/import/pull/push
  - Sensitive data: Stored IN state (pitfall: encrypt your backend!)
  - Workspaces: Separate state per workspace (dev/staging/prod)

Pulumi:
  - State: Managed by Pulumi Cloud (default) or self-hosted backends
  - Backends: Pulumi Cloud, S3, Azure Blob, GCS, local filesystem
  - Locking: Built-in with Pulumi Cloud; backend-specific otherwise
  - State operations: pulumi state delete/unprotect
  - Sensitive data: Encrypted in state with per-stack encryption key
  - Stacks: Named stacks (similar to workspaces but with config inheritance)

CDK:
  - State: CloudFormation manages state (no separate state file!)
  - Backends: CloudFormation stack in AWS account
  - Locking: CloudFormation stack-level locks (IN_PROGRESS prevents concurrent updates)
  - State operations: Limited — CloudFormation drift detection
  - Sensitive data: Managed through SSM Parameter Store / Secrets Manager
  - Environments: CDK environments (account + region pairs)
```

**Best practice** for Terraform state: Always use remote state with locking. The classic setup is an S3 bucket with versioning enabled and a DynamoDB table for state locking. **However**, Terraform Cloud's managed state is increasingly the better option because it handles encryption, locking, access control, and audit logging automatically.

## Drift Detection

Drift occurs when actual infrastructure diverges from the declared state — someone manually changes a security group, an auto-scaling event modifies instance counts, or a different IaC pipeline touches the same resource.

```
Drift Detection Approaches:

Terraform:
  terraform plan          # Shows drift as changes to apply
  terraform refresh       # Updates state to match reality (deprecated flag)
  # Pitfall: refresh can LOSE desired state if manual changes are wrong

  # Best practice: run plan in CI on a schedule
  # terraform plan -detailed-exitcode returns:
  #   0 = no changes
  #   1 = error
  #   2 = changes detected (drift!)

Pulumi:
  pulumi preview          # Equivalent to terraform plan
  pulumi refresh          # Updates state to match reality
  # Advantage: refresh is safer because Pulumi tracks more metadata

CDK:
  # CloudFormation has built-in drift detection
  aws cloudformation detect-stack-drift --stack-name MyStack
  aws cloudformation describe-stack-drift-detection-status \
    --stack-drift-detection-id <id>
  # Returns: IN_SYNC, DRIFTED, NOT_CHECKED
  # Limitation: not all resource types support drift detection
```

## Testing Infrastructure Code

Testing IaC is fundamentally different from testing application code **because** you are testing side effects against a real (or simulated) cloud API. There are four levels of IaC testing:

1. **Static analysis**: Linting, policy checks (no cloud API calls)
2. **Unit tests**: Test the generated plan/template without deploying
3. **Integration tests**: Deploy to a real environment and verify
4. **Contract tests**: Verify outputs match consumer expectations

```python
# test_infrastructure.py
# Multi-level testing for IaC: static analysis, unit tests, and integration tests

import json
import pytest
from typing import Any

# --- Level 1: Static Analysis / Policy Checks ---

def check_s3_encryption_policy(template: dict[str, Any]) -> list[str]:
    # Validate that all S3 buckets in a CloudFormation template
    # have encryption enabled. This is a policy-as-code check.
    violations: list[str] = []
    resources = template.get("Resources", {})
    for logical_id, resource in resources.items():
        if resource.get("Type") == "AWS::S3::Bucket":
            props = resource.get("Properties", {})
            encryption = props.get("BucketEncryption")
            if not encryption:
                violations.append(
                    f"{logical_id}: S3 bucket missing BucketEncryption"
                )
            rules = (encryption or {}).get(
                "ServerSideEncryptionConfiguration", []
            )
            for rule in rules:
                algo = (
                    rule.get("ServerSideEncryptionByDefault", {})
                    .get("SSEAlgorithm")
                )
                if algo not in ("aws:kms", "AES256"):
                    violations.append(
                        f"{logical_id}: Invalid encryption algorithm: {algo}"
                    )
    return violations


def check_security_group_policy(template: dict[str, Any]) -> list[str]:
    # Ensure no security group allows 0.0.0.0/0 on SSH (port 22)
    violations: list[str] = []
    resources = template.get("Resources", {})
    for logical_id, resource in resources.items():
        if resource.get("Type") == "AWS::EC2::SecurityGroup":
            ingress_rules = resource.get("Properties", {}).get(
                "SecurityGroupIngress", []
            )
            for rule in ingress_rules:
                if rule.get("FromPort") == 22 and rule.get("CidrIp") == "0.0.0.0/0":
                    violations.append(
                        f"{logical_id}: SSH open to 0.0.0.0/0"
                    )
    return violations


# --- Level 2: Unit Tests (template validation without deployment) ---

class TestPolicyChecks:
    def test_s3_encryption_enforced(self):
        good_template = {
            "Resources": {
                "DataBucket": {
                    "Type": "AWS::S3::Bucket",
                    "Properties": {
                        "BucketEncryption": {
                            "ServerSideEncryptionConfiguration": [
                                {
                                    "ServerSideEncryptionByDefault": {
                                        "SSEAlgorithm": "aws:kms"
                                    }
                                }
                            ]
                        }
                    },
                }
            }
        }
        assert check_s3_encryption_policy(good_template) == []

    def test_s3_missing_encryption_flagged(self):
        bad_template = {
            "Resources": {
                "UnsafeBucket": {
                    "Type": "AWS::S3::Bucket",
                    "Properties": {"BucketName": "my-bucket"},
                }
            }
        }
        violations = check_s3_encryption_policy(bad_template)
        assert len(violations) == 1
        assert "missing BucketEncryption" in violations[0]

    def test_ssh_open_to_world_flagged(self):
        bad_template = {
            "Resources": {
                "BadSG": {
                    "Type": "AWS::EC2::SecurityGroup",
                    "Properties": {
                        "SecurityGroupIngress": [
                            {"FromPort": 22, "ToPort": 22, "CidrIp": "0.0.0.0/0"}
                        ]
                    },
                }
            }
        }
        violations = check_security_group_policy(bad_template)
        assert len(violations) == 1
        assert "SSH open to 0.0.0.0/0" in violations[0]
```

## Production AWS CDK Example

The following CDK application deploys a complete, production-grade stack with a VPC, ECS Fargate service, RDS PostgreSQL database, proper networking with public/private subnets, security groups, and CloudWatch monitoring.

```python
# cdk_app/stacks/production_stack.py
# Complete production CDK stack: VPC + ECS Fargate + RDS + Monitoring

from constructs import Construct
from aws_cdk import (
    Stack,
    Duration,
    RemovalPolicy,
    CfnOutput,
    Tags,
    aws_ec2 as ec2,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_rds as rds,
    aws_secretsmanager as sm,
    aws_cloudwatch as cw,
    aws_cloudwatch_actions as cw_actions,
    aws_sns as sns,
    aws_logs as logs,
    aws_elasticloadbalancingv2 as elbv2,
)
from typing import Any


class ProductionStack(Stack):
    # Production-grade stack with VPC, ECS Fargate, RDS, and monitoring.
    # Follows AWS Well-Architected Framework principles.

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        env_name: str = "prod",
        db_instance_class: str = "r6g.large",
        container_cpu: int = 512,
        container_memory: int = 1024,
        desired_count: int = 3,
        **kwargs: Any,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Apply tags to all resources in this stack
        Tags.of(self).add("Environment", env_name)
        Tags.of(self).add("ManagedBy", "CDK")
        Tags.of(self).add("Project", "api-service")

        # --- VPC with public/private subnets across 3 AZs ---
        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=3,
            ip_addresses=ec2.IpAddresses.cidr("10.0.0.0/16"),
            nat_gateways=2,  # Cost optimization: 2 instead of 3
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="Public",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Private",
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24,
                ),
                ec2.SubnetConfiguration(
                    name="Isolated",
                    subnet_type=ec2.SubnetType.PRIVATE_ISOLATED,
                    cidr_mask=24,
                ),
            ],
            # Enable VPC Flow Logs for security auditing
            flow_logs={
                "FlowLog": ec2.FlowLogOptions(
                    destination=ec2.FlowLogDestination.to_cloud_watch_logs(),
                    traffic_type=ec2.FlowLogTrafficType.REJECT,
                )
            },
        )

        # --- Security Groups ---
        self.alb_sg = ec2.SecurityGroup(
            self, "AlbSg", vpc=self.vpc,
            description="ALB security group - allows inbound HTTPS",
        )
        self.alb_sg.add_ingress_rule(ec2.Peer.any_ipv4(), ec2.Port.tcp(443))

        self.ecs_sg = ec2.SecurityGroup(
            self, "EcsSg", vpc=self.vpc,
            description="ECS tasks - allows inbound from ALB only",
        )
        self.ecs_sg.add_ingress_rule(self.alb_sg, ec2.Port.tcp(8080))

        self.db_sg = ec2.SecurityGroup(
            self, "DbSg", vpc=self.vpc,
            description="RDS - allows inbound from ECS only",
        )
        self.db_sg.add_ingress_rule(self.ecs_sg, ec2.Port.tcp(5432))

        # --- RDS PostgreSQL in isolated subnets ---
        self.db_credentials = rds.DatabaseSecret(
            self, "DbCredentials", username="app_admin"
        )

        self.database = rds.DatabaseInstance(
            self,
            "Database",
            engine=rds.DatabaseInstanceEngine.postgres(
                version=rds.PostgresEngineVersion.VER_16_1
            ),
            instance_type=ec2.InstanceType(db_instance_class),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_ISOLATED
            ),
            security_groups=[self.db_sg],
            credentials=rds.Credentials.from_secret(self.db_credentials),
            multi_az=True,
            allocated_storage=100,
            max_allocated_storage=500,  # Auto-scaling storage
            storage_encrypted=True,
            backup_retention=Duration.days(14),
            deletion_protection=True if env_name == "prod" else False,
            removal_policy=RemovalPolicy.SNAPSHOT,
            monitoring_interval=Duration.seconds(60),
            enable_performance_insights=True,
            performance_insight_retention=(
                rds.PerformanceInsightRetention.DEFAULT  # 7 days free
            ),
            cloudwatch_logs_exports=["postgresql", "upgrade"],
        )

        # --- ECS Cluster and Fargate Service ---
        self.cluster = ecs.Cluster(
            self,
            "Cluster",
            vpc=self.vpc,
            container_insights_v2=ecs.ContainerInsights.ENABLED,
        )

        # Log group with retention
        log_group = logs.LogGroup(
            self,
            "ServiceLogs",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Fargate service with ALB
        self.fargate_service = ecs_patterns.ApplicationLoadBalancedFargateService(
            self,
            "FargateService",
            cluster=self.cluster,
            cpu=container_cpu,
            memory_limit_mib=container_memory,
            desired_count=desired_count,
            task_image_options=ecs_patterns.ApplicationLoadBalancedTaskImageOptions(
                image=ecs.ContainerImage.from_registry(
                    "123456789.dkr.ecr.us-east-1.amazonaws.com/api:latest"
                ),
                container_port=8080,
                secrets={
                    "DB_URL": ecs.Secret.from_secrets_manager(self.db_credentials),
                },
                environment={
                    "PORT": "8080",
                    "ENV": env_name,
                    "LOG_LEVEL": "INFO",
                },
                log_driver=ecs.LogDrivers.aws_logs(
                    stream_prefix="api",
                    log_group=log_group,
                ),
            ),
            security_groups=[self.ecs_sg],
            task_subnets=ec2.SubnetSelection(
                subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS
            ),
            public_load_balancer=True,
            circuit_breaker=ecs.DeploymentCircuitBreaker(
                rollback=True,
                enable=True,
            ),
        )

        # Health check configuration
        self.fargate_service.target_group.configure_health_check(
            path="/health",
            interval=Duration.seconds(15),
            timeout=Duration.seconds(5),
            healthy_threshold_count=2,
            unhealthy_threshold_count=3,
            healthy_http_codes="200",
        )

        # Auto-scaling
        scaling = self.fargate_service.service.auto_scale_task_count(
            min_capacity=desired_count,
            max_capacity=desired_count * 4,
        )
        scaling.scale_on_cpu_utilization(
            "CpuScaling",
            target_utilization_percent=65,
            scale_in_cooldown=Duration.seconds(300),
            scale_out_cooldown=Duration.seconds(60),
        )
        scaling.scale_on_request_count(
            "RequestScaling",
            requests_per_target=1000,
            target_group=self.fargate_service.target_group,
        )

        # --- CloudWatch Alarms and Monitoring ---
        alarm_topic = sns.Topic(self, "AlarmTopic", display_name="Production Alarms")

        # High CPU alarm
        cw.Alarm(
            self,
            "HighCpuAlarm",
            metric=self.fargate_service.service.metric_cpu_utilization(),
            threshold=85,
            evaluation_periods=3,
            comparison_operator=cw.ComparisonOperator.GREATER_THAN_THRESHOLD,
            treat_missing_data=cw.TreatMissingData.BREACHING,
        ).add_alarm_action(cw_actions.SnsAction(alarm_topic))

        # 5xx error alarm
        cw.Alarm(
            self,
            "Http5xxAlarm",
            metric=self.fargate_service.load_balancer.metric_http_code_elb(
                code=elbv2.HttpCodeElb.ELB_5XX_COUNT,
                period=Duration.minutes(5),
                statistic="Sum",
            ),
            threshold=10,
            evaluation_periods=2,
        ).add_alarm_action(cw_actions.SnsAction(alarm_topic))

        # RDS CPU alarm
        cw.Alarm(
            self,
            "DbCpuAlarm",
            metric=self.database.metric_cpu_utilization(
                period=Duration.minutes(5)
            ),
            threshold=80,
            evaluation_periods=3,
        ).add_alarm_action(cw_actions.SnsAction(alarm_topic))

        # --- Outputs ---
        CfnOutput(self, "AlbDns", value=self.fargate_service.load_balancer.load_balancer_dns_name)
        CfnOutput(self, "DbEndpoint", value=self.database.db_instance_endpoint_address)
        CfnOutput(self, "VpcId", value=self.vpc.vpc_id)
```

## Summary and Key Takeaways

- **Terraform** excels at multi-cloud with a massive provider ecosystem, but HCL's limited expressiveness becomes a **pitfall** for complex logic (conditionals, loops over heterogeneous data).
- **Pulumi** brings general-purpose languages to IaC, enabling real abstraction and code reuse; **however**, it has a smaller ecosystem and less community knowledge than Terraform.
- **CDK** is the best choice for AWS-only shops **because** it generates CloudFormation, which AWS supports natively with drift detection, rollback, and change sets.
- **Best practice**: Test IaC at multiple levels — static policy checks in pre-commit hooks, unit tests in CI, integration tests on a schedule.
- **Pitfall**: Terraform state contains secrets in plaintext — always encrypt your state backend and restrict access.
- **Therefore**, choose your IaC tool based on cloud strategy (multi-cloud vs single), team language preferences, and ecosystem maturity rather than feature checklists.
"""
    ),

    # --- 4. Service Mesh Deep Dive ---
    (
        "cloud-native/service-mesh-deep-dive",
        "Explain service mesh architecture in depth focusing on Envoy proxy internals including the xDS discovery API protocol, traffic management patterns like canary deployments and circuit breaking, mTLS certificate rotation with SPIFFE identities, and provide detailed configuration examples for Envoy listeners, clusters, routes, and Istio traffic management resources.",
        r"""# Service Mesh Deep Dive: Envoy Internals, xDS, mTLS, and Traffic Management

## What Problem Does a Service Mesh Solve?

In a microservices architecture, every service-to-service call crosses the network. This creates cross-cutting concerns that every service must handle: **retries**, **timeouts**, **circuit breaking**, **load balancing**, **mutual TLS**, **observability** (metrics, traces, access logs), and **traffic routing** (canary deployments, A/B testing). A service mesh extracts these concerns from application code into infrastructure.

The **trade-off** is operational complexity and latency overhead (typically 1-3ms per hop). **Therefore**, a service mesh is most valuable when you have 20+ services and need consistent security/observability policies. A **common mistake** is adopting a service mesh for 5 services — the overhead is not justified at that scale. Use simple client-side libraries (like gRPC retry policies) instead.

## Envoy Proxy Architecture

Envoy is the data plane proxy used by Istio, AWS App Mesh, and Consul Connect. It runs as a **sidecar** alongside each service instance, intercepting all inbound and outbound traffic. Understanding Envoy's internal architecture is essential for debugging mesh issues.

```
Envoy Request Flow (inbound):

  Client -> [Listener:0.0.0.0:8080]
                |
            [Filter Chain Match] (by SNI, ALPN, source IP)
                |
            [HTTP Connection Manager] (HCM filter)
                |
            [HTTP Filters] -> [Router] -> [Route Match]
                |                             |
            [Rate Limit]              [Route: /api/v1/*]
            [JWT Authn]                       |
            [RBAC AuthZ]              [Cluster: api-v1-backend]
            [CORS]                            |
                                      [Load Balancer] (round-robin, least-req, ring-hash)
                                              |
                                      [Health Check Filter]
                                              |
                                      [Endpoint: 10.0.1.5:8080]

  Key Envoy Concepts:
  - Listener: Binds to IP:port, dispatches to filter chains
  - Filter Chain: Ordered list of network/HTTP filters
  - Route: Maps incoming requests to clusters based on path/headers
  - Cluster: Group of upstream endpoints (like a K8s Service)
  - Endpoint: Individual backend instance (IP:port)
```

## The xDS Discovery API Protocol

xDS (x Discovery Service) is the API that the control plane uses to dynamically configure Envoy proxies. Instead of static config files, the control plane pushes configuration updates in real time via gRPC streams. This is how Istio, Consul, and other meshes keep thousands of Envoy proxies in sync.

```
xDS API Types:

  LDS (Listener Discovery Service):
    - Configures which ports Envoy listens on
    - Defines filter chains for each listener
    - Example: "Listen on port 8080, apply JWT auth + rate limit filters"

  RDS (Route Discovery Service):
    - Configures HTTP routing rules
    - Path matching, header matching, weighted routing
    - Example: "Route /api/v2/* to cluster-v2 with 10% canary weight"

  CDS (Cluster Discovery Service):
    - Configures upstream service clusters
    - Load balancing policy, circuit breaker settings, outlier detection
    - Example: "Cluster 'payments' uses least-request LB, 5s connect timeout"

  EDS (Endpoint Discovery Service):
    - Configures individual endpoints within clusters
    - Health status, locality-weighted routing, priority levels
    - Example: "Cluster 'payments' has endpoints 10.0.1.5:8080 (healthy),
               10.0.1.6:8080 (healthy), 10.0.1.7:8080 (draining)"

  SDS (Secret Discovery Service):
    - Distributes TLS certificates and keys
    - Enables certificate rotation without proxy restart
    - Example: "Here is the new mTLS cert for service 'orders', valid 24h"

  Protocol: Bidirectional gRPC stream (ADS = Aggregated Discovery Service)
  Flow: Envoy sends DiscoveryRequest -> Control plane sends DiscoveryResponse
  Consistency: Resources have versions; Envoy ACKs/NACKs each update
```

## Envoy Configuration Examples

### Static Bootstrap Configuration

```yaml
# envoy-bootstrap.yaml
# Minimal Envoy bootstrap that connects to an xDS control plane

admin:
  address:
    socket_address:
      address: 127.0.0.1
      port_value: 9901

# Dynamic configuration via xDS
dynamic_resources:
  lds_config:
    resource_api_version: V3
    api_config_source:
      api_type: GRPC
      transport_api_version: V3
      grpc_services:
        - envoy_grpc:
            cluster_name: xds_cluster
      set_node_on_first_message_only: true
  cds_config:
    resource_api_version: V3
    api_config_source:
      api_type: GRPC
      transport_api_version: V3
      grpc_services:
        - envoy_grpc:
            cluster_name: xds_cluster

# Static cluster for the xDS control plane itself
static_resources:
  clusters:
    - name: xds_cluster
      type: STRICT_DNS
      connect_timeout: 5s
      typed_extension_protocol_options:
        envoy.extensions.upstreams.http.v3.HttpProtocolOptions:
          "@type": type.googleapis.com/envoy.extensions.upstreams.http.v3.HttpProtocolOptions
          explicit_http_config:
            http2_protocol_options: {}
      load_assignment:
        cluster_name: xds_cluster
        endpoints:
          - lb_endpoints:
              - endpoint:
                  address:
                    socket_address:
                      address: istiod.istio-system.svc
                      port_value: 15010

node:
  id: "sidecar~10.0.1.5~api-v1-abc123.default~default.svc.cluster.local"
  cluster: "api-v1"
  metadata:
    NAMESPACE: default
    LABELS:
      app: api
      version: v1
```

### Envoy Listener with HTTP Filters

```yaml
# envoy-listener.yaml
# Complete listener configuration with JWT auth, rate limiting,
# RBAC authorization, and routing to multiple clusters

resources:
  - "@type": type.googleapis.com/envoy.config.listener.v3.Listener
    name: inbound_0.0.0.0_8080
    address:
      socket_address:
        address: 0.0.0.0
        port_value: 8080
    filter_chains:
      - transport_socket:
          name: envoy.transport_sockets.tls
          typed_config:
            "@type": type.googleapis.com/envoy.extensions.transport_sockets.tls.v3.DownstreamTlsContext
            require_client_certificate: true
            common_tls_context:
              tls_certificate_sds_secret_configs:
                - name: "default"
                  sds_config:
                    resource_api_version: V3
                    api_config_source:
                      api_type: GRPC
                      grpc_services:
                        - envoy_grpc:
                            cluster_name: sds_cluster
              validation_context_sds_secret_config:
                name: "ROOTCA"
                sds_config:
                  resource_api_version: V3
                  api_config_source:
                    api_type: GRPC
                    grpc_services:
                      - envoy_grpc:
                          cluster_name: sds_cluster
        filters:
          - name: envoy.filters.network.http_connection_manager
            typed_config:
              "@type": type.googleapis.com/envoy.extensions.filters.network.http_connection_manager.v3.HttpConnectionManager
              stat_prefix: inbound_http
              access_log:
                - name: envoy.access_loggers.file
                  typed_config:
                    "@type": type.googleapis.com/envoy.extensions.access_loggers.file.v3.FileAccessLog
                    path: /dev/stdout
                    log_format:
                      json_format:
                        timestamp: "%START_TIME%"
                        method: "%REQ(:METHOD)%"
                        path: "%REQ(X-ENVOY-ORIGINAL-PATH?:PATH)%"
                        response_code: "%RESPONSE_CODE%"
                        duration_ms: "%DURATION%"
                        upstream_host: "%UPSTREAM_HOST%"
                        request_id: "%REQ(X-REQUEST-ID)%"
              route_config:
                name: local_route
                virtual_hosts:
                  - name: api_service
                    domains: ["*"]
                    routes:
                      # Canary route: 10% traffic to v2
                      - match:
                          prefix: "/api/"
                        route:
                          weighted_clusters:
                            clusters:
                              - name: api-v1
                                weight: 90
                              - name: api-v2
                                weight: 10
                          retry_policy:
                            retry_on: "5xx,reset,connect-failure"
                            num_retries: 3
                            per_try_timeout: 2s
                            retry_back_off:
                              base_interval: 0.1s
                              max_interval: 1s
                      - match:
                          prefix: "/health"
                        direct_response:
                          status: 200
                          body:
                            inline_string: '{"status":"healthy"}'
              http_filters:
                - name: envoy.filters.http.jwt_authn
                  typed_config:
                    "@type": type.googleapis.com/envoy.extensions.filters.http.jwt_authn.v3.JwtAuthentication
                    providers:
                      auth0:
                        issuer: "https://myapp.auth0.com/"
                        audiences: ["https://api.myapp.com"]
                        remote_jwks:
                          http_uri:
                            uri: "https://myapp.auth0.com/.well-known/jwks.json"
                            cluster: auth0_jwks
                            timeout: 5s
                          cache_duration: 600s
                    rules:
                      - match: { prefix: "/api/" }
                        requires: { provider_name: "auth0" }
                      - match: { prefix: "/health" }
                - name: envoy.filters.http.router
                  typed_config:
                    "@type": type.googleapis.com/envoy.extensions.filters.http.router.v3.Router
```

## mTLS Certificate Rotation with SPIFFE

SPIFFE (Secure Production Identity Framework for Everyone) provides cryptographic identities for services. In a mesh, each service gets a **SPIFFE ID** (like `spiffe://cluster.local/ns/default/sa/api-v1`) and a short-lived X.509 certificate. **Because** certificates expire every 24 hours (or less), automatic rotation is critical.

```
mTLS Certificate Lifecycle:

  1. Envoy proxy starts, generates a CSR (Certificate Signing Request)
  2. CSR is sent to the control plane (Istiod/Citadel) via SDS
  3. Control plane validates identity (K8s service account token)
  4. Control plane signs the CSR with the mesh CA
  5. Certificate (SVID) returned to Envoy via SDS stream
  6. Envoy uses cert for mTLS with other services
  7. Before expiry, Envoy requests a new certificate (step 1-6)

  SPIFFE ID format: spiffe://<trust-domain>/<path>
  Example: spiffe://cluster.local/ns/payments/sa/payment-processor

  Certificate rotation timeline:
  - Cert lifetime:    24 hours (Istio default)
  - Rotation trigger: When 80% of lifetime has elapsed (~19.2 hours)
  - Grace period:     Envoy accepts both old and new cert during rotation
  - Zero downtime:    SDS hot-swaps certs without proxy restart

  Best practice: Set cert lifetime to 1-24 hours. Shorter lifetimes
  reduce the blast radius of a compromised key, but increase CA load.
```

## Istio Traffic Management Resources

```yaml
# istio-traffic-management.yaml
# Complete Istio configuration for canary deployment with
# circuit breaking, fault injection, and traffic mirroring

# VirtualService: L7 routing rules
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: api-service
  namespace: default
spec:
  hosts:
    - api-service
  http:
    # Header-based routing for testing
    - match:
        - headers:
            x-canary:
              exact: "true"
      route:
        - destination:
            host: api-service
            subset: v2
    # Weighted canary routing
    - route:
        - destination:
            host: api-service
            subset: v1
          weight: 90
        - destination:
            host: api-service
            subset: v2
          weight: 10
      timeout: 10s
      retries:
        attempts: 3
        perTryTimeout: 3s
        retryOn: 5xx,reset,connect-failure,retriable-4xx
      # Mirror 5% of traffic to v2 for shadow testing
      mirror:
        host: api-service
        subset: v2
      mirrorPercentage:
        value: 5.0
---
# DestinationRule: Circuit breaking and load balancing
apiVersion: networking.istio.io/v1beta1
kind: DestinationRule
metadata:
  name: api-service
  namespace: default
spec:
  host: api-service
  trafficPolicy:
    connectionPool:
      tcp:
        maxConnections: 100
        connectTimeout: 5s
      http:
        h2UpgradePolicy: DEFAULT
        http1MaxPendingRequests: 100
        http2MaxRequests: 1000
        maxRequestsPerConnection: 10
        maxRetries: 3
    outlierDetection:
      consecutive5xxErrors: 5
      interval: 10s
      baseEjectionTime: 30s
      maxEjectionPercent: 50
    loadBalancer:
      simple: LEAST_REQUEST
  subsets:
    - name: v1
      labels:
        version: v1
      trafficPolicy:
        connectionPool:
          http:
            http2MaxRequests: 500
    - name: v2
      labels:
        version: v2
      trafficPolicy:
        connectionPool:
          http:
            http2MaxRequests: 100
---
# PeerAuthentication: Enforce mTLS
apiVersion: security.istio.io/v1beta1
kind: PeerAuthentication
metadata:
  name: default
  namespace: default
spec:
  mtls:
    mode: STRICT
---
# AuthorizationPolicy: RBAC for service-to-service
apiVersion: security.istio.io/v1beta1
kind: AuthorizationPolicy
metadata:
  name: api-service-authz
  namespace: default
spec:
  selector:
    matchLabels:
      app: api-service
  rules:
    - from:
        - source:
            principals:
              - "cluster.local/ns/default/sa/web-frontend"
              - "cluster.local/ns/default/sa/mobile-gateway"
      to:
        - operation:
            methods: ["GET", "POST"]
            paths: ["/api/*"]
    - from:
        - source:
            principals:
              - "cluster.local/ns/monitoring/sa/prometheus"
      to:
        - operation:
            methods: ["GET"]
            paths: ["/metrics", "/health"]
```

## Summary and Key Takeaways

- **Envoy** is the universal data plane proxy; understanding its listener-filter-route-cluster architecture is essential for debugging any service mesh.
- The **xDS protocol** (LDS, RDS, CDS, EDS, SDS) is the standard API for dynamic proxy configuration — it enables zero-downtime config updates across thousands of proxies.
- **mTLS with SPIFFE** provides cryptographic service identity; short-lived certificates (24h or less) rotated automatically via SDS minimize the impact of key compromise.
- **Best practice**: Start with permissive mTLS mode and gradually move to strict mode, validating that all service-to-service communication works correctly.
- **Pitfall**: Circuit breaker thresholds that are too aggressive cause cascading failures when one unhealthy instance ejects too many endpoints; **therefore**, set `maxEjectionPercent` to 50% or less.
- **However**, a service mesh adds latency and operational complexity — evaluate whether your scale (20+ services) justifies the investment before adopting one.
"""
    ),

    # --- 5. Multi-Cloud and Hybrid Strategies ---
    (
        "cloud-native/multi-cloud-hybrid-strategies",
        "Explain multi-cloud and hybrid cloud strategies covering abstraction layer design patterns, Crossplane for multi-cloud resource management with composition functions, Terraform workspaces for multi-environment deployment, cost optimization techniques across AWS Azure and GCP providers, and provide complete configuration examples with Python cost analysis tooling.",
        r"""# Multi-Cloud and Hybrid Cloud Strategies: Abstraction, Crossplane, and Cost Optimization

## Why Multi-Cloud?

Organizations pursue multi-cloud strategies for several reasons: **regulatory requirements** (data sovereignty), **vendor negotiation leverage**, **best-of-breed services** (GCP for ML, AWS for breadth, Azure for enterprise integration), and **disaster recovery** across provider failures. **However**, multi-cloud introduces enormous complexity in networking, identity, observability, and cost management.

**Common mistake**: Adopting multi-cloud "to avoid vendor lock-in" without a concrete business driver. The lowest-common-denominator approach — using only features available on all clouds — means you sacrifice the unique strengths of each provider. **Therefore**, the most effective multi-cloud strategy is intentional: use each cloud for what it does best, with clear abstraction boundaries between cloud-specific and cloud-agnostic components.

## Abstraction Layer Design Patterns

There are three levels of multi-cloud abstraction, each with different trade-offs:

```
Multi-Cloud Abstraction Levels:

Level 1: Application-Level Abstraction (Recommended for most teams)
  - Abstract at the service interface level
  - Each service uses cloud-native services internally
  - Cross-cloud communication via standard protocols (gRPC, HTTPS, AMQP)
  - Example: ML training on GCP (Vertex AI), serving on AWS (SageMaker)
  - Trade-off: Best performance, but requires cloud-specific expertise

Level 2: Infrastructure Abstraction (Crossplane, Terraform modules)
  - Abstract at the resource provisioning level
  - Unified API for creating databases, queues, storage across clouds
  - Example: "Give me a managed PostgreSQL" -> provisions RDS or Cloud SQL
  - Trade-off: Good portability, but abstraction leaks for advanced features

Level 3: Runtime Abstraction (Kubernetes everywhere)
  - Run workloads on K8s regardless of cloud (EKS, GKE, AKS)
  - Use K8s-native services (operators) instead of cloud-managed services
  - Example: Run CockroachDB operator instead of RDS/Cloud SQL
  - Trade-off: Maximum portability, but lose managed service benefits
                and increase operational burden significantly

Best practice: Use Level 1 for differentiated services, Level 2 for
commodity infrastructure, and Level 3 only for workloads that truly
need to run identically across clouds.
```

## Crossplane for Multi-Cloud Resource Management

Crossplane extends Kubernetes to become a universal control plane for infrastructure. Instead of Terraform's CLI-based workflow, Crossplane uses the Kubernetes API to manage cloud resources declaratively. **Because** Crossplane runs inside your cluster, it provides continuous reconciliation — if someone manually deletes a resource, Crossplane recreates it.

```yaml
# crossplane-composition.yaml
# Crossplane Composition that creates a "managed database" abstraction
# that works across AWS, GCP, and Azure

# Step 1: Define the abstract API (XRD - CompositeResourceDefinition)
apiVersion: apiextensions.crossplane.io/v1
kind: CompositeResourceDefinition
metadata:
  name: xmanageddatabases.platform.example.com
spec:
  group: platform.example.com
  names:
    kind: XManagedDatabase
    plural: xmanagedatabases
  claimNames:
    kind: ManagedDatabase
    plural: manageddatabases
  versions:
    - name: v1alpha1
      served: true
      referenceable: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              required: ["engine", "size", "region"]
              properties:
                engine:
                  type: string
                  enum: ["postgresql", "mysql"]
                version:
                  type: string
                  default: "16"
                size:
                  type: string
                  enum: ["small", "medium", "large"]
                  description: "small=2vCPU/4GB, medium=4vCPU/16GB, large=8vCPU/32GB"
                region:
                  type: string
                highAvailability:
                  type: boolean
                  default: true
                provider:
                  type: string
                  enum: ["aws", "gcp", "azure"]
                  default: "aws"
            status:
              type: object
              properties:
                endpoint:
                  type: string
                port:
                  type: integer
                secretName:
                  type: string
---
# Step 2: AWS Composition
apiVersion: apiextensions.crossplane.io/v1
kind: Composition
metadata:
  name: managed-database-aws
  labels:
    provider: aws
spec:
  compositeTypeRef:
    apiVersion: platform.example.com/v1alpha1
    kind: XManagedDatabase
  patchSets:
    - name: common-tags
      patches:
        - type: FromCompositeFieldPath
          fromFieldPath: metadata.labels
          toFieldPath: spec.forProvider.tags
          policy:
            mergeOptions:
              keepMapValues: true
  resources:
    # Subnet Group
    - name: subnet-group
      base:
        apiVersion: rds.aws.crossplane.io/v1alpha1
        kind: DBSubnetGroup
        spec:
          forProvider:
            description: "Managed by Crossplane"
            subnetIdSelector:
              matchLabels:
                access: private
          providerConfigRef:
            name: aws-provider
      patches:
        - type: FromCompositeFieldPath
          fromFieldPath: spec.region
          toFieldPath: spec.forProvider.region
    # RDS Instance
    - name: rds-instance
      base:
        apiVersion: rds.aws.crossplane.io/v1alpha1
        kind: DBInstance
        spec:
          forProvider:
            dbInstanceClass: db.r6g.large
            engine: postgres
            engineVersion: "16"
            masterUsername: admin
            allocatedStorage: 100
            storageEncrypted: true
            publiclyAccessible: false
            autoMinorVersionUpgrade: true
            backupRetentionPeriod: 14
            deletionProtection: true
          providerConfigRef:
            name: aws-provider
          writeConnectionSecretToRef:
            namespace: crossplane-system
      patches:
        - type: FromCompositeFieldPath
          fromFieldPath: spec.size
          toFieldPath: spec.forProvider.dbInstanceClass
          transforms:
            - type: map
              map:
                small: db.r6g.large
                medium: db.r6g.xlarge
                large: db.r6g.2xlarge
        - type: FromCompositeFieldPath
          fromFieldPath: spec.engine
          toFieldPath: spec.forProvider.engine
        - type: FromCompositeFieldPath
          fromFieldPath: spec.version
          toFieldPath: spec.forProvider.engineVersion
        - type: FromCompositeFieldPath
          fromFieldPath: spec.highAvailability
          toFieldPath: spec.forProvider.multiAZ
        - type: ToCompositeFieldPath
          fromFieldPath: status.atProvider.endpoint.address
          toFieldPath: status.endpoint
        - type: ToCompositeFieldPath
          fromFieldPath: status.atProvider.endpoint.port
          toFieldPath: status.port
---
# Step 3: Developer claims a database (cloud-agnostic!)
apiVersion: platform.example.com/v1alpha1
kind: ManagedDatabase
metadata:
  name: orders-db
  namespace: orders-team
spec:
  engine: postgresql
  version: "16"
  size: medium
  region: us-east-1
  highAvailability: true
  provider: aws
```

## Terraform Workspaces for Multi-Environment Deployment

Terraform workspaces provide isolated state for the same configuration across environments. **Best practice**: Use workspaces for environment separation (dev/staging/prod) but not for fundamentally different infrastructure — use separate root modules for that.

```hcl
# terraform/main.tf
# Multi-environment deployment using workspaces with environment-specific variables

terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  backend "s3" {
    bucket         = "myorg-terraform-state"
    key            = "api-service/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
    # Workspace prefix: each workspace gets its own state file
    # e.g., env:/dev/api-service/terraform.tfstate
    workspace_key_prefix = "env"
  }
}

# Environment-specific configuration
locals {
  env_config = {
    dev = {
      instance_type = "t3.small"
      db_class      = "db.t3.medium"
      min_capacity  = 1
      max_capacity  = 3
      multi_az      = false
      deletion_prot = false
    }
    staging = {
      instance_type = "t3.medium"
      db_class      = "db.r6g.large"
      min_capacity  = 2
      max_capacity  = 6
      multi_az      = true
      deletion_prot = false
    }
    prod = {
      instance_type = "r6g.large"
      db_class      = "db.r6g.xlarge"
      min_capacity  = 3
      max_capacity  = 20
      multi_az      = true
      deletion_prot = true
    }
  }

  env = local.env_config[terraform.workspace]

  common_tags = {
    Environment = terraform.workspace
    ManagedBy   = "Terraform"
    Project     = "api-service"
    Workspace   = terraform.workspace
  }
}

# Usage: terraform workspace select dev && terraform apply
```

## Cross-Provider Cost Optimization

Cost optimization across clouds requires understanding each provider's pricing model deeply. The following Python tool analyzes and compares costs across AWS, GCP, and Azure for common resource types.

```python
# cost_analyzer.py
# Multi-cloud cost analysis and optimization recommendation engine

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class CloudProvider(Enum):
    AWS = "aws"
    GCP = "gcp"
    AZURE = "azure"


@dataclass
class ResourceCost:
    # Represents the cost of a single cloud resource
    provider: CloudProvider
    service: str
    instance_type: str
    region: str
    hourly_cost: float
    monthly_cost: float  # hourly * 730 hours
    reserved_monthly: float  # 1-year reserved/committed pricing
    spot_hourly: float  # Spot/preemptible pricing (0 if unavailable)
    notes: str = ""


@dataclass
class CostComparison:
    # Comparison result across providers for equivalent resources
    resource_type: str
    description: str
    costs: list[ResourceCost]
    recommendation: str = ""
    potential_savings_pct: float = 0.0


class MultiCloudCostAnalyzer:
    # Analyzes and compares costs across AWS, GCP, and Azure.
    # Uses embedded pricing data (in production, query pricing APIs).

    # Pricing data (simplified, US East / us-central1 / East US)
    COMPUTE_PRICING: dict[str, dict[str, Any]] = {
        # 4 vCPU, 16 GB RAM equivalent
        "medium_compute": {
            "aws": {
                "type": "m6i.xlarge", "hourly": 0.192,
                "reserved_1y": 0.121, "spot": 0.058
            },
            "gcp": {
                "type": "n2-standard-4", "hourly": 0.194,
                "committed_1y": 0.122, "preemptible": 0.048
            },
            "azure": {
                "type": "D4s_v5", "hourly": 0.192,
                "reserved_1y": 0.118, "spot": 0.038
            },
        },
        # 8 vCPU, 32 GB RAM equivalent
        "large_compute": {
            "aws": {
                "type": "m6i.2xlarge", "hourly": 0.384,
                "reserved_1y": 0.242, "spot": 0.115
            },
            "gcp": {
                "type": "n2-standard-8", "hourly": 0.388,
                "committed_1y": 0.245, "preemptible": 0.097
            },
            "azure": {
                "type": "D8s_v5", "hourly": 0.384,
                "reserved_1y": 0.236, "spot": 0.077
            },
        },
    }

    DATABASE_PRICING: dict[str, dict[str, Any]] = {
        # Managed PostgreSQL, 4 vCPU, 16 GB RAM, 100 GB storage
        "medium_postgres": {
            "aws": {
                "type": "db.r6g.xlarge", "monthly": 438.0,
                "reserved_1y": 280.0, "storage_per_gb": 0.115
            },
            "gcp": {
                "type": "db-custom-4-16384", "monthly": 425.0,
                "committed_1y": 268.0, "storage_per_gb": 0.170
            },
            "azure": {
                "type": "GP_Gen5_4", "monthly": 450.0,
                "reserved_1y": 290.0, "storage_per_gb": 0.115
            },
        },
    }

    STORAGE_PRICING: dict[str, dict[str, float]] = {
        # Per GB/month for standard object storage
        "object_storage_per_gb": {
            "aws_s3_standard": 0.023,
            "gcp_standard": 0.020,
            "azure_hot": 0.018,
        },
        "object_storage_per_gb_infrequent": {
            "aws_s3_ia": 0.0125,
            "gcp_nearline": 0.010,
            "azure_cool": 0.010,
        },
    }

    def compare_compute(self, tier: str = "medium_compute") -> CostComparison:
        # Compare compute costs across all three providers
        pricing = self.COMPUTE_PRICING[tier]
        costs: list[ResourceCost] = []

        for provider_name, data in pricing.items():
            provider = CloudProvider(provider_name)
            costs.append(ResourceCost(
                provider=provider,
                service="Compute",
                instance_type=data["type"],
                region="us-east-1" if provider == CloudProvider.AWS else "us-central1",
                hourly_cost=data["hourly"],
                monthly_cost=round(data["hourly"] * 730, 2),
                reserved_monthly=round(data.get("reserved_1y", data.get("committed_1y", 0)) * 730, 2),
                spot_hourly=data.get("spot", data.get("preemptible", 0)),
            ))

        # Find cheapest options
        cheapest_ondemand = min(costs, key=lambda c: c.monthly_cost)
        cheapest_reserved = min(costs, key=lambda c: c.reserved_monthly)
        cheapest_spot = min(costs, key=lambda c: c.spot_hourly)
        most_expensive = max(costs, key=lambda c: c.monthly_cost)

        savings = (
            (most_expensive.monthly_cost - cheapest_reserved.reserved_monthly)
            / most_expensive.monthly_cost * 100
        )

        recommendation = (
            f"On-demand: {cheapest_ondemand.provider.value} ({cheapest_ondemand.instance_type}) "
            f"at ${cheapest_ondemand.monthly_cost}/mo. "
            f"Reserved: {cheapest_reserved.provider.value} at ${cheapest_reserved.reserved_monthly}/mo. "
            f"Spot/Preemptible: {cheapest_spot.provider.value} at ${cheapest_spot.spot_hourly}/hr "
            f"(best for fault-tolerant batch workloads)."
        )

        return CostComparison(
            resource_type=tier,
            description=f"Compute comparison for {tier}",
            costs=costs,
            recommendation=recommendation,
            potential_savings_pct=round(savings, 1),
        )

    def generate_optimization_report(
        self,
        workload: dict[str, Any],
    ) -> dict[str, Any]:
        # Generate a comprehensive cost optimization report.
        #
        # Args:
        #     workload: Dictionary describing the workload:
        #         - compute_instances: int
        #         - compute_tier: str ("medium_compute" or "large_compute")
        #         - storage_tb: float
        #         - db_count: int
        #         - fault_tolerant_pct: float (0-1, fraction eligible for spot)
        compute_tier = workload.get("compute_tier", "medium_compute")
        num_instances = workload.get("compute_instances", 10)
        storage_tb = workload.get("storage_tb", 1.0)
        db_count = workload.get("db_count", 1)
        spot_eligible = workload.get("fault_tolerant_pct", 0.3)

        comparison = self.compare_compute(compute_tier)

        # Calculate total costs per provider
        results: dict[str, dict[str, float]] = {}
        for cost in comparison.costs:
            provider = cost.provider.value
            spot_instances = int(num_instances * spot_eligible)
            ondemand_instances = num_instances - spot_instances

            compute_monthly = (
                ondemand_instances * cost.monthly_cost
                + spot_instances * cost.spot_hourly * 730
            )

            storage_key = f"{provider}_s3_standard" if provider == "aws" else (
                f"{provider}_standard" if provider == "gcp" else f"{provider}_hot"
            )
            storage_monthly = (
                storage_tb * 1024
                * self.STORAGE_PRICING["object_storage_per_gb"].get(storage_key, 0.023)
            )

            db_pricing = self.DATABASE_PRICING["medium_postgres"].get(provider, {})
            db_monthly = db_count * db_pricing.get("monthly", 450)

            total = compute_monthly + storage_monthly + db_monthly
            results[provider] = {
                "compute": round(compute_monthly, 2),
                "storage": round(storage_monthly, 2),
                "database": round(db_monthly, 2),
                "total": round(total, 2),
            }

        cheapest_provider = min(results, key=lambda p: results[p]["total"])
        most_expensive = max(results, key=lambda p: results[p]["total"])
        savings = (
            (results[most_expensive]["total"] - results[cheapest_provider]["total"])
            / results[most_expensive]["total"] * 100
        )

        return {
            "workload": workload,
            "costs_by_provider": results,
            "cheapest_provider": cheapest_provider,
            "potential_savings_pct": round(savings, 1),
            "recommendations": [
                f"Use {cheapest_provider.upper()} for lowest total cost "
                f"(${results[cheapest_provider]['total']:.2f}/mo)",
                f"Move {spot_eligible*100:.0f}% of compute to spot/preemptible "
                f"for additional savings",
                "Use reserved/committed pricing for baseline capacity",
                "Implement lifecycle policies to move cold storage to infrequent-access tiers",
            ],
        }


def run_cost_analysis() -> None:
    # Example usage of the cost analyzer
    analyzer = MultiCloudCostAnalyzer()

    # Compare compute
    compute = analyzer.compare_compute("medium_compute")
    print(f"=== {compute.description} ===")
    for cost in compute.costs:
        print(
            f"  {cost.provider.value:6s}: {cost.instance_type:18s} "
            f"On-demand=${cost.monthly_cost:>8.2f}/mo  "
            f"Reserved=${cost.reserved_monthly:>8.2f}/mo  "
            f"Spot=${cost.spot_hourly:.3f}/hr"
        )
    print(f"  Recommendation: {compute.recommendation}")
    print(f"  Potential savings: {compute.potential_savings_pct}%\n")

    # Full workload analysis
    report = analyzer.generate_optimization_report({
        "compute_instances": 20,
        "compute_tier": "large_compute",
        "storage_tb": 5.0,
        "db_count": 2,
        "fault_tolerant_pct": 0.4,
    })
    print("=== Full Workload Report ===")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    run_cost_analysis()
```

## Testing the Cost Analyzer

```python
# test_cost_analyzer.py
# Tests for the multi-cloud cost analysis tool

import pytest
from cost_analyzer import MultiCloudCostAnalyzer, CloudProvider, CostComparison


class TestMultiCloudCostAnalyzer:
    def setup_method(self) -> None:
        self.analyzer = MultiCloudCostAnalyzer()

    def test_compute_comparison_returns_all_providers(self) -> None:
        result = self.analyzer.compare_compute("medium_compute")
        providers = {c.provider for c in result.costs}
        assert providers == {CloudProvider.AWS, CloudProvider.GCP, CloudProvider.AZURE}

    def test_reserved_cheaper_than_ondemand(self) -> None:
        result = self.analyzer.compare_compute("medium_compute")
        for cost in result.costs:
            assert cost.reserved_monthly < cost.monthly_cost, (
                f"{cost.provider.value}: reserved (${cost.reserved_monthly}) "
                f"should be cheaper than on-demand (${cost.monthly_cost})"
            )

    def test_spot_cheaper_than_ondemand(self) -> None:
        result = self.analyzer.compare_compute("large_compute")
        for cost in result.costs:
            assert cost.spot_hourly < cost.hourly_cost, (
                f"{cost.provider.value}: spot should be cheaper than on-demand"
            )

    def test_optimization_report_structure(self) -> None:
        report = self.analyzer.generate_optimization_report({
            "compute_instances": 10,
            "compute_tier": "medium_compute",
            "storage_tb": 1.0,
            "db_count": 1,
            "fault_tolerant_pct": 0.3,
        })
        assert "costs_by_provider" in report
        assert "cheapest_provider" in report
        assert "recommendations" in report
        assert len(report["recommendations"]) >= 3
        # Verify all providers have cost breakdowns
        for provider in ["aws", "gcp", "azure"]:
            assert provider in report["costs_by_provider"]
            costs = report["costs_by_provider"][provider]
            assert "compute" in costs
            assert "storage" in costs
            assert "database" in costs
            assert "total" in costs

    def test_savings_percentage_is_reasonable(self) -> None:
        report = self.analyzer.generate_optimization_report({
            "compute_instances": 10,
            "compute_tier": "medium_compute",
            "storage_tb": 1.0,
            "db_count": 1,
            "fault_tolerant_pct": 0.3,
        })
        # Savings between providers should be between 0-50%
        assert 0 <= report["potential_savings_pct"] <= 50
```

## Hybrid Cloud Networking Patterns

```
Hybrid Connectivity Options:

1. VPN (IPsec tunnel):
   - Bandwidth: Up to 1.25 Gbps per tunnel (AWS), 3 Gbps (GCP)
   - Latency: Variable (internet path)
   - Cost: ~$0.05/hr per VPN gateway
   - Best for: Dev/test, low-bandwidth workloads

2. Direct Connect / Dedicated Interconnect / ExpressRoute:
   - Bandwidth: 1-100 Gbps dedicated
   - Latency: Predictable, low (private fiber)
   - Cost: $0.03/GB transfer + port fees ($200-$500/mo for 1 Gbps)
   - Best for: Production, data-intensive, latency-sensitive

3. Transit Gateway / Cloud Router:
   - Hub-and-spoke model for connecting multiple VPCs/VNets
   - Simplifies routing at scale (avoid N*N peering)
   - Cost: ~$0.05/hr + $0.02/GB processed

Best practice for hybrid: Use Direct Connect / Interconnect for
production traffic, VPN as a backup path, and Transit Gateway
to simplify multi-VPC routing. Always encrypt in transit regardless
of connection type (however, Direct Connect is NOT encrypted by default!).
```

## Summary and Key Takeaways

- **Multi-cloud is a strategy, not a goal**: Adopt it when driven by regulatory, resilience, or best-of-breed requirements — not "to avoid lock-in" alone.
- **Crossplane** provides Kubernetes-native multi-cloud resource management with continuous reconciliation; **however**, it requires a running K8s cluster and adds operational complexity.
- **Terraform workspaces** are the simplest multi-environment pattern; **best practice** is to use them for dev/staging/prod but keep workspace-specific configuration in `tfvars` files.
- **Cost optimization** across providers requires analyzing compute, storage, database, and data transfer costs together — the cheapest compute provider may not be cheapest for data egress.
- **Pitfall**: Data egress costs are the hidden tax of multi-cloud. Moving data between clouds costs $0.08-0.12/GB, which can exceed compute costs for data-intensive workloads. **Therefore**, co-locate data and compute.
- **Best practice**: Use reserved/committed pricing for baseline capacity (40-60% savings), spot/preemptible for fault-tolerant batch workloads (70-90% savings), and on-demand only for burst capacity.
"""
    ),
]
