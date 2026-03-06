"""Phase 1H: Foundation Thinking — Data Modeling & DevOps (Part 8)

Logging/observability, infrastructure as code, and backup/disaster recovery
with realistic configurations and production patterns.
"""

PAIRS = [
    (
        "thinking/devops-structured-logging",
        r'''Our Python microservices generate unstructured log messages like:

logger.info(f"Processing order {order_id} for user {user_id}, amount=${amount}")
logger.error(f"Failed to charge card for order {order_id}: {str(e)}")
logger.warning(f"Slow query detected: {query_time}ms")

We have 12 services generating ~50GB of logs per day. Searching for all logs related to a specific order requires grepping across multiple services. How should we structure our logging for better observability?''',
        r'''<think>
The problems with unstructured logging:

1. **Parsing is fragile**: Regex/grep to extract order_id from a free-text message breaks when message format changes
2. **No correlation**: Can't trace a request across 12 services without a shared trace ID
3. **No machine readability**: Log aggregation tools (ELK, Datadog, Loki) work much better with structured JSON
4. **Inconsistent fields**: Each developer formats messages differently
5. **Context loss**: The log line doesn't include service name, environment, deployment version, etc.

**The solution: Structured logging (JSON)**

Instead of:
```
2024-03-05 14:30:00 INFO Processing order 12345 for user 67, amount=$99.99
```

Emit:
```json
{"timestamp": "2024-03-05T14:30:00Z", "level": "info", "message": "Processing order", "order_id": 12345, "user_id": 67, "amount": 99.99, "service": "order-service", "trace_id": "abc123"}
```

**Key structured logging principles:**

1. **JSON format**: One JSON object per log line
2. **Standard fields**: timestamp, level, message, service, trace_id on every line
3. **Structured context**: Fields like order_id, user_id as separate JSON keys (not embedded in message)
4. **Correlation IDs**: trace_id and span_id propagated across services for distributed tracing
5. **Log levels used correctly**: DEBUG for development, INFO for business events, WARNING for degraded behavior, ERROR for failures, CRITICAL for system-down scenarios

**Python implementation:**

Use `structlog` or `python-json-logger`. structlog is the better choice because:
- Processors pipeline (add context at different stages)
- Bound loggers (attach context once, log many times)
- Works with stdlib logging and loguru

**Log aggregation stack:**
- ELK (Elasticsearch, Logstash, Kibana): Full-featured, expensive at scale
- Loki + Grafana: Log aggregation without full-text indexing, cheaper
- Datadog Logs: SaaS, easy setup, expensive at 50GB/day

At 50GB/day, cost matters. Loki is the most cost-effective for structured logs because it indexes labels (service, level, trace_id) but stores log lines compressed, not indexed.
</think>

### Move from unstructured text to structured JSON logging

### Before (unstructured, unqueryable)

```
2024-03-05 14:30:00 INFO Processing order 12345 for user 67, amount=$99.99
2024-03-05 14:30:01 ERROR Failed to charge card for order 12345: CardDeclined
```

### After (structured JSON, fully queryable)

```json
{"ts": "2024-03-05T14:30:00Z", "level": "info", "msg": "Processing order", "service": "order-svc", "order_id": 12345, "user_id": 67, "amount": 99.99, "trace_id": "a1b2c3", "span_id": "d4e5f6", "env": "production", "version": "1.5.2"}
{"ts": "2024-03-05T14:30:01Z", "level": "error", "msg": "Card charge failed", "service": "payment-svc", "order_id": 12345, "error": "CardDeclined", "trace_id": "a1b2c3", "span_id": "g7h8i9", "env": "production", "version": "1.5.2"}
```

### Python implementation with structlog

```python
# logging_config.py — shared across all 12 services
import structlog
import logging
import sys
import os

def configure_logging(service_name: str):
    """Configure structured JSON logging for a service."""

    structlog.configure(
        processors=[
            # Add context automatically
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", key="ts"),
            # Add service metadata
            structlog.processors.CallsiteParameterAdder(
                parameters=[
                    structlog.processors.CallsiteParameter.FUNC_NAME,
                    structlog.processors.CallsiteParameter.LINENO,
                ]
            ),
            # Format for output
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.WriteLoggerFactory(file=sys.stdout),
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if os.getenv("DEBUG") else logging.INFO
        ),
        cache_logger_on_first_use=True,
    )

    # Add global context (same for every log line from this service)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        service=service_name,
        env=os.getenv("ENVIRONMENT", "development"),
        version=os.getenv("APP_VERSION", "unknown"),
    )
```

### Request middleware: Auto-attach trace_id and request context

```python
import uuid
import time
import structlog
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

app = FastAPI()
logger = structlog.get_logger()

class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Get or generate trace ID (propagated from upstream service)
        trace_id = request.headers.get("X-Trace-ID", str(uuid.uuid4()))
        request_id = str(uuid.uuid4())

        # Bind context for all logs during this request
        structlog.contextvars.bind_contextvars(
            trace_id=trace_id,
            request_id=request_id,
            method=request.method,
            path=request.url.path,
            user_id=getattr(request.state, "user_id", None),
        )

        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        logger.info(
            "Request completed",
            status=response.status_code,
            duration_ms=duration_ms,
        )

        # Propagate trace ID to response
        response.headers["X-Trace-ID"] = trace_id

        # Clear request-scoped context
        structlog.contextvars.unbind_contextvars(
            "request_id", "method", "path"
        )

        return response

app.add_middleware(RequestLoggingMiddleware)
```

### Usage in application code

```python
logger = structlog.get_logger()

async def process_order(order_id: int, user_id: int, amount: float):
    # Bind order context — all subsequent logs include these fields
    log = logger.bind(order_id=order_id, user_id=user_id, amount=amount)

    log.info("Processing order")

    try:
        charge = await payment_service.charge(amount)
        log.info("Payment successful", charge_id=charge.id)
    except CardDeclinedError as e:
        log.error("Card charge failed", error=str(e), card_last4=e.last4)
        raise
    except Exception as e:
        log.error("Unexpected payment error", error=str(e), error_type=type(e).__name__)
        raise
```

### Querying structured logs (Loki/Grafana example)

```
# Find all logs for a specific order across all services
{service=~".+"} | json | order_id=12345

# Find all errors in payment service in the last hour
{service="payment-svc"} | json | level="error"

# Find slow requests (> 500ms)
{service="order-svc"} | json | duration_ms > 500

# Trace a request across all services using trace_id
{service=~".+"} | json | trace_id="a1b2c3"
```

### Log level guidelines

| Level | Use for | Example |
|-------|---------|---------|
| DEBUG | Developer diagnostics | `log.debug("Cache key computed", key=cache_key)` |
| INFO | Business events | `log.info("Order created", order_id=123)` |
| WARNING | Degraded but working | `log.warning("Slow query", duration_ms=850)` |
| ERROR | Failed operation | `log.error("Payment failed", error=str(e))` |
| CRITICAL | System unusable | `log.critical("Database connection lost")` |'''
    ),
    (
        "thinking/devops-terraform-iac",
        r'''We manage our AWS infrastructure manually through the console. We have:
- 3 ECS services (API, worker, admin)
- RDS PostgreSQL (primary + read replica)
- ElastiCache Redis cluster
- ALB with SSL termination
- S3 buckets for media and backups
- CloudFront CDN
- VPC with public/private subnets

Every environment (dev, staging, prod) was created manually and they've drifted. Prod has security groups that don't exist in staging, staging has an older RDS version, and dev is missing the Redis cluster entirely. How do we move to infrastructure as code?''',
        r'''<think>
Moving from manual (ClickOps) to IaC is a major undertaking. Let me think about the approach.

**Tool choice:**
- Terraform: Most popular, cloud-agnostic, declarative, large ecosystem
- AWS CDK: AWS-specific, imperative (TypeScript/Python), good for AWS-only shops
- Pulumi: Like CDK but cloud-agnostic, uses real programming languages
- CloudFormation: AWS native, JSON/YAML, verbose

For this case (AWS-only, 3 environments), Terraform is the standard choice. AWS CDK is also excellent if they prefer Python/TypeScript.

**Migration strategy:**

Option A: Import existing resources into Terraform
- Use `terraform import` to bring existing resources under Terraform management
- Pros: No downtime, preserves existing infrastructure
- Cons: Tedious (must import each resource individually), state can get messy

Option B: Recreate infrastructure with Terraform alongside
- Create new VPC/subnets/etc. with Terraform
- Migrate services from old to new infrastructure
- Pros: Clean state, no import issues
- Cons: Migration downtime, more complex

For production: Option A (import) for critical shared resources (VPC, RDS), Option B for stateless services (ECS tasks can be recreated).

**Module structure:**

```
infrastructure/
├── modules/           # Reusable modules
│   ├── vpc/
│   ├── ecs-service/
│   ├── rds/
│   ├── redis/
│   └── cdn/
├── environments/      # Per-environment config
│   ├── dev/
│   │   └── main.tf
│   ├── staging/
│   │   └── main.tf
│   └── prod/
│       └── main.tf
└── global/           # Shared resources
    └── iam/
```

Each environment uses the same modules with different variables (instance sizes, replica counts, etc.). This eliminates drift because all environments use identical code with different parameters.

**State management:**
- Remote state in S3 with DynamoDB locking
- Separate state file per environment (so dev terraform plan doesn't affect prod)
- State encryption at rest

Let me provide a practical Terraform setup focusing on the key modules and environment separation.
</think>

### Migration plan: Manual AWS to Terraform

### Step 1: Set up Terraform backend (do this first)

```hcl
# infrastructure/backend/main.tf
# Bootstrap: creates the S3 bucket and DynamoDB table for Terraform state
# Run this ONCE manually, then all other terraform uses this backend

provider "aws" {
  region = "us-east-1"
}

resource "aws_s3_bucket" "terraform_state" {
  bucket = "mycompany-terraform-state"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "terraform_state" {
  bucket = aws_s3_bucket.terraform_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "aws:kms"
    }
  }
}

resource "aws_dynamodb_table" "terraform_locks" {
  name         = "terraform-locks"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "LockID"

  attribute {
    name = "LockID"
    type = "S"
  }
}
```

### Step 2: Module structure

```
infrastructure/
├── modules/
│   ├── networking/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── ecs-service/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── outputs.tf
│   ├── rds/
│   │   └── ...
│   └── redis/
│       └── ...
├── environments/
│   ├── dev/
│   │   ├── main.tf
│   │   ├── variables.tf
│   │   └── terraform.tfvars
│   ├── staging/
│   │   └── ...
│   └── prod/
│       └── ...
└── backend/
    └── main.tf
```

### Step 3: Reusable ECS service module

```hcl
# modules/ecs-service/variables.tf
variable "service_name" {
  type = string
}

variable "environment" {
  type = string
}

variable "container_image" {
  type = string
}

variable "container_port" {
  type    = number
  default = 8000
}

variable "desired_count" {
  type    = number
  default = 2
}

variable "cpu" {
  type    = number
  default = 256
}

variable "memory" {
  type    = number
  default = 512
}

variable "vpc_id" {
  type = string
}

variable "subnet_ids" {
  type = list(string)
}

variable "alb_target_group_arn" {
  type = string
}

variable "environment_variables" {
  type    = map(string)
  default = {}
}
```

```hcl
# modules/ecs-service/main.tf
resource "aws_ecs_task_definition" "this" {
  family                   = "${var.service_name}-${var.environment}"
  network_mode             = "awsvpc"
  requires_compatibilities = ["FARGATE"]
  cpu                      = var.cpu
  memory                   = var.memory
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  container_definitions = jsonencode([{
    name      = var.service_name
    image     = var.container_image
    essential = true

    portMappings = [{
      containerPort = var.container_port
      protocol      = "tcp"
    }]

    environment = [
      for k, v in var.environment_variables : {
        name  = k
        value = v
      }
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = "/ecs/${var.service_name}-${var.environment}"
        "awslogs-region"        = data.aws_region.current.name
        "awslogs-stream-prefix" = "ecs"
      }
    }

    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:${var.container_port}/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])
}

resource "aws_ecs_service" "this" {
  name            = "${var.service_name}-${var.environment}"
  cluster         = aws_ecs_cluster.this.id
  task_definition = aws_ecs_task_definition.this.arn
  desired_count   = var.desired_count
  launch_type     = "FARGATE"

  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  network_configuration {
    subnets          = var.subnet_ids
    security_groups  = [aws_security_group.service.id]
    assign_public_ip = false
  }

  load_balancer {
    target_group_arn = var.alb_target_group_arn
    container_name   = var.service_name
    container_port   = var.container_port
  }

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  lifecycle {
    ignore_changes = [task_definition]  # Updated by CI/CD, not Terraform
  }
}
```

### Step 4: Environment configuration (eliminates drift)

```hcl
# environments/prod/main.tf
terraform {
  backend "s3" {
    bucket         = "mycompany-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = "us-east-1"
  default_tags {
    tags = {
      Environment = "production"
      ManagedBy   = "terraform"
      Team        = "platform"
    }
  }
}

module "networking" {
  source = "../../modules/networking"

  environment    = "prod"
  vpc_cidr       = "10.0.0.0/16"
  azs            = ["us-east-1a", "us-east-1b", "us-east-1c"]
  public_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  private_subnets = ["10.0.10.0/24", "10.0.11.0/24", "10.0.12.0/24"]
}

module "api" {
  source = "../../modules/ecs-service"

  service_name  = "api"
  environment   = "prod"
  container_image = "123456789.dkr.ecr.us-east-1.amazonaws.com/api:latest"
  desired_count = 3        # Prod: 3 replicas
  cpu           = 1024     # Prod: 1 vCPU
  memory        = 2048     # Prod: 2 GB
  vpc_id        = module.networking.vpc_id
  subnet_ids    = module.networking.private_subnet_ids
  alb_target_group_arn = module.alb.api_target_group_arn

  environment_variables = {
    DATABASE_URL = "postgresql://${module.rds.endpoint}/myapp"
    REDIS_URL    = "redis://${module.redis.endpoint}:6379"
    ENVIRONMENT  = "production"
  }
}

module "rds" {
  source = "../../modules/rds"

  environment        = "prod"
  engine_version     = "16.1"
  instance_class     = "db.r6g.xlarge"  # Prod: large instance
  allocated_storage  = 500
  multi_az           = true              # Prod: multi-AZ
  read_replicas      = 1                 # Prod: 1 read replica
  backup_retention   = 30                # Prod: 30-day backups
  vpc_id             = module.networking.vpc_id
  subnet_ids         = module.networking.private_subnet_ids
}

module "redis" {
  source = "../../modules/redis"

  environment    = "prod"
  node_type      = "cache.r6g.large"
  num_cache_nodes = 3
  vpc_id         = module.networking.vpc_id
  subnet_ids     = module.networking.private_subnet_ids
}
```

```hcl
# environments/dev/main.tf — same modules, smaller sizes
module "api" {
  source = "../../modules/ecs-service"

  service_name  = "api"
  environment   = "dev"
  desired_count = 1        # Dev: 1 replica
  cpu           = 256      # Dev: 0.25 vCPU
  memory        = 512      # Dev: 0.5 GB
  # ... same module, different params
}

module "rds" {
  source = "../../modules/rds"

  environment        = "dev"
  instance_class     = "db.t3.micro"   # Dev: smallest
  multi_az           = false            # Dev: single AZ
  read_replicas      = 0               # Dev: no replicas
  backup_retention   = 1               # Dev: 1-day backup
}

# Dev DOES get Redis now (eliminates the drift!)
module "redis" {
  source = "../../modules/redis"

  environment     = "dev"
  node_type       = "cache.t3.micro"
  num_cache_nodes = 1
}
```

### Step 5: Import existing resources

```bash
# Import existing VPC (don't recreate, import into state)
cd environments/prod
terraform import module.networking.aws_vpc.this vpc-0abc123def

# Import existing RDS
terraform import module.rds.aws_db_instance.this myapp-prod

# Import existing ECS cluster
terraform import module.api.aws_ecs_cluster.this myapp-prod

# After importing, run plan to check for drift
terraform plan
# This shows differences between actual state and desired state
# Fix the Terraform code until plan shows no changes
```

### Migration timeline

| Week | Action | Risk |
|------|--------|------|
| 1 | Set up backend, write modules | None (no infra changes) |
| 2 | Import dev environment | Low (dev only) |
| 3 | Import staging, fix drift | Low (staging only) |
| 4 | Import prod (read-only first) | None (plan only) |
| 5 | Apply prod (fix drift) | Medium (review carefully) |
| 6+ | All changes via Terraform PR | None (standard workflow) |'''
    ),
    (
        "thinking/devops-observability-metrics",
        r'''We're moving from "check logs when something breaks" to proactive monitoring. Our services have no metrics, no dashboards, and no alerts. The team gets paged by customers reporting issues before we notice them internally. What observability stack should we implement and what metrics matter most?''',
        r'''<think>
The three pillars of observability are: Metrics, Logs, Traces. They've started thinking about logs (previous topic). Now we need metrics and the overall observability strategy.

**What to monitor — the RED and USE methods:**

RED method (for request-driven services):
- Rate: requests per second
- Errors: error rate (% of requests that fail)
- Duration: latency (p50, p95, p99)

USE method (for infrastructure):
- Utilization: % of resource capacity being used
- Saturation: amount of work queued
- Errors: error events

**The four golden signals (Google SRE):**
1. Latency: how long requests take
2. Traffic: how much demand
3. Errors: rate of failed requests
4. Saturation: how full your resources are

**Metrics stack options:**
- Prometheus + Grafana: Open source, pull-based, industry standard
- Datadog: SaaS, all-in-one, expensive at scale
- CloudWatch: AWS native, basic but integrated
- Victoria Metrics: Prometheus-compatible, better performance at scale

For a team starting fresh, Prometheus + Grafana is the best choice:
- Free and open source
- Massive ecosystem of exporters
- Grafana has excellent dashboarding
- AlertManager for alerting
- Integrates with PagerDuty/Slack/etc.

**What metrics to instrument first (highest value):**

1. Request rate, error rate, latency per endpoint (RED)
2. Database connection pool (utilization, wait time)
3. Memory and CPU per container
4. Queue depth (Celery/Redis task backlog)
5. External dependency health (payment gateway, email service)

**Alerting philosophy:**
- Alert on symptoms (high error rate), not causes (CPU is 80%)
- Alert on things that need human action
- Every alert should have a runbook
- Start with few, high-signal alerts. Add more as you learn.
</think>

### The three pillars of observability you need

```
Metrics  → "What is happening?" (counters, gauges, histograms)
Logs     → "Why did it happen?" (structured events with context)
Traces   → "Where did it happen?" (request path across services)
```

### Stack recommendation: Prometheus + Grafana + Loki

```yaml
# docker-compose.monitoring.yml
version: "3.8"

services:
  prometheus:
    image: prom/prometheus:v2.50.0
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.retention.time=30d'

  grafana:
    image: grafana/grafana:10.3.0
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/dashboards:/etc/grafana/provisioning/dashboards
      - ./grafana/datasources:/etc/grafana/provisioning/datasources
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: "${GRAFANA_PASSWORD}"

  alertmanager:
    image: prom/alertmanager:v0.27.0
    volumes:
      - ./alertmanager.yml:/etc/alertmanager/alertmanager.yml
    ports:
      - "9093:9093"

  loki:
    image: grafana/loki:2.9.0
    ports:
      - "3100:3100"
    volumes:
      - loki_data:/loki

volumes:
  prometheus_data:
  grafana_data:
  loki_data:
```

### Instrument your Python services

```python
# metrics.py — shared metrics module
from prometheus_client import Counter, Histogram, Gauge, Info
import time

# RED metrics for HTTP requests
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency',
    ['method', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
)

# Business metrics
ORDERS_CREATED = Counter(
    'orders_created_total',
    'Total orders created',
    ['payment_method']
)

ORDERS_FAILED = Counter(
    'orders_failed_total',
    'Total failed orders',
    ['failure_reason']
)

ORDER_AMOUNT = Histogram(
    'order_amount_dollars',
    'Order amounts in dollars',
    buckets=[10, 25, 50, 100, 250, 500, 1000, 5000]
)

# Infrastructure metrics
DB_POOL_SIZE = Gauge(
    'db_connection_pool_size',
    'Database connection pool size',
    ['state']  # 'active', 'idle', 'waiting'
)

TASK_QUEUE_DEPTH = Gauge(
    'celery_task_queue_depth',
    'Number of tasks waiting in queue',
    ['queue_name']
)

APP_INFO = Info(
    'app',
    'Application information'
)
```

### FastAPI middleware for automatic HTTP metrics

```python
from fastapi import FastAPI, Request
from prometheus_client import make_asgi_app
import time

app = FastAPI()

# Expose /metrics endpoint for Prometheus to scrape
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    # Normalize path (replace IDs with placeholders for cardinality control)
    path = request.url.path
    for part in path.split('/'):
        if part.isdigit():
            path = path.replace(part, '{id}')

    method = request.method
    start = time.perf_counter()

    response = await call_next(request)

    duration = time.perf_counter() - start
    status = str(response.status_code)

    REQUEST_COUNT.labels(method=method, endpoint=path, status=status).inc()
    REQUEST_LATENCY.labels(method=method, endpoint=path).observe(duration)

    return response

# Business metric instrumentation
async def create_order(order_data):
    try:
        order = await process_order(order_data)
        ORDERS_CREATED.labels(payment_method=order.payment_method).inc()
        ORDER_AMOUNT.observe(float(order.total))
        return order
    except PaymentError as e:
        ORDERS_FAILED.labels(failure_reason="payment").inc()
        raise
    except InventoryError as e:
        ORDERS_FAILED.labels(failure_reason="inventory").inc()
        raise
```

### Prometheus scrape configuration

```yaml
# prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

rule_files:
  - "alerts/*.yml"

alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]

scrape_configs:
  - job_name: "api"
    static_configs:
      - targets: ["api:8000"]
    metrics_path: /metrics

  - job_name: "worker"
    static_configs:
      - targets: ["worker:8000"]

  - job_name: "node-exporter"
    static_configs:
      - targets: ["node-exporter:9100"]

  - job_name: "postgres"
    static_configs:
      - targets: ["postgres-exporter:9187"]

  - job_name: "redis"
    static_configs:
      - targets: ["redis-exporter:9121"]
```

### Alert rules (start with these 5)

```yaml
# alerts/critical.yml
groups:
  - name: critical
    rules:
      # 1. High error rate (symptom-based, most important)
      - alert: HighErrorRate
        expr: |
          sum(rate(http_requests_total{status=~"5.."}[5m]))
          / sum(rate(http_requests_total[5m]))
          > 0.05
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Error rate above 5%"
          runbook: "https://wiki/runbooks/high-error-rate"

      # 2. High latency
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
          > 2.0
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "p95 latency above 2 seconds"

      # 3. Service down
      - alert: ServiceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "{{ $labels.instance }} is down"

      # 4. Database connection exhaustion
      - alert: DBConnectionPoolExhausted
        expr: db_connection_pool_size{state="waiting"} > 5
        for: 2m
        labels:
          severity: warning
        annotations:
          summary: "Database connection pool has waiting requests"

      # 5. Task queue backing up
      - alert: TaskQueueBacklog
        expr: celery_task_queue_depth > 1000
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Celery task queue depth above 1000"
```

### Priority order for implementation

| Week | Implement | Value |
|------|----------|-------|
| 1 | HTTP metrics (RED) + /metrics endpoint | See error rates and latency |
| 2 | Grafana dashboards + 5 critical alerts | Get paged before customers |
| 3 | Database and Redis exporters | Diagnose infrastructure issues |
| 4 | Business metrics (orders, revenue) | Business visibility |
| 5 | Distributed tracing (OpenTelemetry) | Debug cross-service issues |'''
    ),
    (
        "thinking/devops-backup-disaster-recovery",
        r'''We run a PostgreSQL database with 500GB of data. Our current backup strategy is a daily pg_dump that takes 3 hours and is stored on the same server. Last week, an intern accidentally ran DROP TABLE on production during a training exercise. Recovery took 8 hours because we had to:
1. Find the latest backup (24 hours old)
2. Transfer it from the same server (which was also under load)
3. Restore the full dump
4. Accept 24 hours of data loss

How do we design a proper backup and disaster recovery strategy?''',
        r'''<think>
The current setup has multiple critical failures:

1. **Same-server storage**: If the server dies, backups die with it
2. **24-hour RPO**: A full day of data loss is unacceptable for most businesses
3. **3-hour RTO for pg_dump restore**: Too slow for a production database
4. **No point-in-time recovery**: Can only restore to the last dump, not to "5 minutes before the DROP TABLE"
5. **No access controls**: An intern shouldn't be able to DROP TABLE in production

**Backup strategy layers:**

Layer 1: Continuous WAL archiving (enables point-in-time recovery)
- PostgreSQL writes all changes to Write-Ahead Log (WAL)
- Archive WAL files to S3 continuously (every few seconds)
- Can restore to ANY point in time, not just dump times
- RPO: seconds (last WAL segment)

Layer 2: Base backups (weekly/daily)
- pg_basebackup: physical backup of the data directory
- Faster to restore than pg_dump (no SQL parsing)
- Stored in S3 (offsite)
- Combined with WAL replay for point-in-time recovery

Layer 3: Logical backups (weekly)
- pg_dump: logical SQL backup
- Useful for selective table restores and cross-version migration
- Slower but more flexible

Layer 4: Read replica
- Streaming replication to a second instance
- Near-zero RTO for hardware failures
- Doesn't protect against logical errors (DROP TABLE replicates too)

**RPO and RTO targets:**
- RPO (Recovery Point Objective): How much data can we lose? Target: < 1 minute
- RTO (Recovery Time Objective): How long until service is restored? Target: < 30 minutes

**For the DROP TABLE scenario specifically:**
- With WAL archiving, we can restore to "1 second before the DROP TABLE"
- Data loss: 0 (assuming we know when it happened)
- Recovery time: ~15-30 min to replay WAL to the target point

**Access control fixes:**
- Production access via IAM roles, not shared passwords
- Read-only access for non-admin users
- pg_hba.conf: separate roles for app (read/write) and admin (DDL)
- Statement logging so DROP TABLE is immediately visible
</think>

### Current failures and fixes

| Current | Problem | Fix |
|---------|---------|-----|
| Daily pg_dump | 24h data loss (RPO) | WAL archiving (seconds RPO) |
| Same server | Single point of failure | S3 offsite storage |
| 3-hour restore | Slow RTO | pg_basebackup + WAL replay |
| No access control | Intern runs DROP TABLE | Role-based access + audit |

### Layer 1: Continuous WAL archiving (enables point-in-time recovery)

```ini
# postgresql.conf
wal_level = replica                    # Required for archiving
archive_mode = on
archive_command = 'wal-g wal-push %p'  # wal-g archives to S3
archive_timeout = 60                    # Force archive every 60s (even if WAL not full)

# Or without wal-g, use native archive_command:
# archive_command = 'aws s3 cp %p s3://myapp-db-backups/wal/%f'
```

```bash
# Install wal-g (modern backup tool, faster than pg_basebackup + manual WAL)
# Configure wal-g with S3
export WALG_S3_PREFIX=s3://myapp-db-backups/production
export AWS_REGION=us-east-1
export PGDATA=/var/lib/postgresql/16/main
```

### Layer 2: Automated base backups

```bash
#!/bin/bash
# scripts/backup.sh — run daily via cron

set -euo pipefail

echo "Starting base backup..."
wal-g backup-push $PGDATA

# Verify the backup
wal-g backup-list

# Retain last 7 daily backups
wal-g delete retain 7 --confirm

echo "Backup complete: $(date)"
```

```cron
# /etc/cron.d/postgres-backup
# Daily base backup at 2 AM
0 2 * * * postgres /opt/scripts/backup.sh >> /var/log/backup.log 2>&1
```

### Layer 3: Point-in-time recovery (for the DROP TABLE scenario)

```bash
#!/bin/bash
# scripts/pitr-restore.sh
# Restore database to a specific point in time

TARGET_TIME="${1:?Usage: pitr-restore.sh '2026-03-05 14:30:00 UTC'}"

echo "=== POINT-IN-TIME RECOVERY ==="
echo "Restoring to: $TARGET_TIME"
echo "This will stop the current database and restore from backup."
read -p "Are you sure? (yes/no): " confirm
[ "$confirm" = "yes" ] || exit 1

# Step 1: Stop PostgreSQL
echo "Stopping PostgreSQL..."
systemctl stop postgresql

# Step 2: Save current data directory (just in case)
echo "Backing up current data directory..."
mv /var/lib/postgresql/16/main /var/lib/postgresql/16/main.old

# Step 3: Restore base backup
echo "Fetching latest base backup from S3..."
wal-g backup-fetch /var/lib/postgresql/16/main LATEST

# Step 4: Configure recovery target
cat > /var/lib/postgresql/16/main/recovery.signal << EOF
EOF

cat >> /var/lib/postgresql/16/main/postgresql.auto.conf << EOF
restore_command = 'wal-g wal-fetch %f %p'
recovery_target_time = '$TARGET_TIME'
recovery_target_action = 'promote'
EOF

# Step 5: Fix permissions
chown -R postgres:postgres /var/lib/postgresql/16/main

# Step 6: Start PostgreSQL (replays WAL up to target time)
echo "Starting PostgreSQL in recovery mode..."
systemctl start postgresql

echo "Recovery in progress. Check: SELECT pg_is_in_recovery();"
echo "Once promoted, verify data and remove old directory."
```

### Layer 4: Access control (prevent the DROP TABLE incident)

```sql
-- Create separate roles for different access levels
CREATE ROLE app_readonly;
GRANT CONNECT ON DATABASE myapp TO app_readonly;
GRANT USAGE ON SCHEMA public TO app_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO app_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO app_readonly;

CREATE ROLE app_readwrite;
GRANT CONNECT ON DATABASE myapp TO app_readwrite;
GRANT USAGE ON SCHEMA public TO app_readwrite;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO app_readwrite;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO app_readwrite;
-- NOTE: No CREATE, DROP, ALTER, TRUNCATE

CREATE ROLE app_admin;
GRANT ALL PRIVILEGES ON DATABASE myapp TO app_admin;

-- Application connects as readwrite (can't DROP TABLE)
CREATE USER app_user WITH PASSWORD '...' IN ROLE app_readwrite;

-- Migrations connect as admin (can ALTER TABLE)
CREATE USER migration_user WITH PASSWORD '...' IN ROLE app_admin;

-- Interns/training connect as readonly
CREATE USER training_user WITH PASSWORD '...' IN ROLE app_readonly;

-- Log all DDL statements for audit
ALTER SYSTEM SET log_statement = 'ddl';
SELECT pg_reload_conf();
```

### Monitoring backup health

```python
# scripts/verify_backups.py — run daily
import subprocess
import json
from datetime import datetime, timedelta

def check_backup_freshness():
    """Alert if the latest backup is older than 25 hours."""
    result = subprocess.run(
        ["wal-g", "backup-list", "--json"],
        capture_output=True, text=True
    )
    backups = json.loads(result.stdout)

    if not backups:
        send_alert("CRITICAL: No backups found!")
        return

    latest = max(backups, key=lambda b: b["time"])
    backup_age = datetime.utcnow() - datetime.fromisoformat(latest["time"])

    if backup_age > timedelta(hours=25):
        send_alert(f"WARNING: Latest backup is {backup_age.total_seconds()/3600:.1f} hours old")
    else:
        print(f"OK: Latest backup is {backup_age.total_seconds()/3600:.1f} hours old")

def test_restore():
    """Monthly: actually restore a backup to verify it works."""
    # Restore to a separate test instance
    subprocess.run([
        "docker", "run", "--rm",
        "-e", f"WALG_S3_PREFIX=s3://myapp-db-backups/production",
        "postgres-restore-test:latest",
        "/opt/scripts/test-restore.sh"
    ], check=True)
    print("OK: Backup restore test passed")

check_backup_freshness()
```

### Recovery scenarios and time

| Scenario | Without this plan | With this plan |
|----------|------------------|----------------|
| DROP TABLE | 8 hours, 24h data loss | 15 min, 0 data loss (PITR) |
| Server disk failure | Total loss (backups on same disk) | 30 min restore from S3 |
| Region outage | Total loss | Restore to another region |
| Corrupted data (gradual) | Undetectable | Audit log + selective restore |
| Ransomware | Pay ransom or lose data | Immutable S3 backups |

### S3 backup protection

```hcl
# Terraform: S3 bucket with immutable backups
resource "aws_s3_bucket" "db_backups" {
  bucket = "myapp-db-backups"
}

# Enable versioning (can't permanently delete old backups)
resource "aws_s3_bucket_versioning" "db_backups" {
  bucket = aws_s3_bucket.db_backups.id
  versioning_configuration {
    status = "Enabled"
  }
}

# Object Lock: prevent deletion for 30 days (ransomware protection)
resource "aws_s3_bucket_object_lock_configuration" "db_backups" {
  bucket = aws_s3_bucket.db_backups.id
  rule {
    default_retention {
      mode = "GOVERNANCE"
      days = 30
    }
  }
}

# Lifecycle: move old backups to Glacier after 30 days
resource "aws_s3_bucket_lifecycle_configuration" "db_backups" {
  bucket = aws_s3_bucket.db_backups.id
  rule {
    id     = "archive-old-backups"
    status = "Enabled"
    transition {
      days          = 30
      storage_class = "GLACIER"
    }
    expiration {
      days = 365  # Delete after 1 year
    }
  }
}
```'''
    ),
    (
        "thinking/devops-secrets-management",
        r'''Our team stores secrets in various insecure ways:
- .env files committed to Git (even though .gitignore exists, someone force-added them)
- API keys hardcoded in docker-compose.yml environment variables
- Database passwords in Terraform state files (plaintext in S3)
- Shared credentials in a team Slack channel
- Production SSH keys on individual developer laptops

We've already had one incident where an ex-employee still had access to production database credentials 3 months after leaving. How should we manage secrets properly?''',
        r'''<think>
This is a common but dangerous situation. Let me categorize the problems and solutions.

**Current problems:**

1. **.env files in Git**: Anyone who clones the repo (including public if it's open source) has all secrets. Git history preserves them even after deletion.

2. **Hardcoded in docker-compose.yml**: Same as above — secrets in version control.

3. **Terraform state in plaintext S3**: Terraform state contains every secret value in plain text. Anyone with S3 access can read them.

4. **Secrets in Slack**: No access control, no audit trail, persisted forever in Slack's servers, searchable by anyone in the channel.

5. **SSH keys on laptops**: No rotation, no revocation when employees leave, no audit of who accessed what.

6. **No credential rotation after offboarding**: The ex-employee problem. If secrets are shared (same password for everyone), you can't revoke one person's access without changing the password for everyone.

**Solution layers:**

Layer 1: Centralized secret management (HashiCorp Vault, AWS Secrets Manager, or similar)
- All secrets stored in one place with access control
- Audit log of who accessed which secret and when
- Automatic rotation
- Dynamic secrets (generated on-demand, expire automatically)

Layer 2: Secret injection at runtime
- Applications fetch secrets from the secret manager, not from files or env vars
- Kubernetes: use External Secrets Operator or Vault Agent Injector
- Docker: use Docker secrets (swarm) or mount from secret manager
- CI/CD: use the platform's secret management (GitHub Actions secrets, etc.)

Layer 3: Rotation and revocation
- Rotate all secrets on a schedule (90 days)
- Immediately rotate after any employee departure
- Use short-lived credentials where possible (IAM roles, JWT tokens)

Layer 4: Detection and prevention
- Git pre-commit hooks to detect secrets (detect-secrets, truffleHog)
- CI checks that fail if secrets are found in code
- Terraform state encryption

**Tool choice:**
- AWS Secrets Manager: Good for AWS-only shops, native integration, $0.40/secret/month
- HashiCorp Vault: Best for multi-cloud, dynamic secrets, complex policies. More operational overhead.
- 1Password/Bitwarden for teams: Good for human-readable secrets (passwords, API tokens shared among team)

For most teams: AWS Secrets Manager for application secrets + a team password manager for human secrets + pre-commit hooks for prevention.
</think>

### Immediate actions (do this today)

```bash
# 1. Check if secrets are in Git history
# Install truffleHog to scan entire repo history
pip install trufflehog
trufflehog git file://. --only-verified

# 2. If secrets are found: rotate ALL of them immediately
# The secrets are compromised the moment they hit Git, even in a private repo.
# Git history is permanent — deleting the file doesn't help.

# 3. Add pre-commit hook to prevent future leaks
pip install detect-secrets
detect-secrets scan > .secrets.baseline
```

### Pre-commit hook: Block secrets before they reach Git

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.4.0
    hooks:
      - id: detect-secrets
        args: ['--baseline', '.secrets.baseline']
        exclude: package-lock.json

  - repo: https://github.com/zricethezav/gitleaks
    rev: v8.18.0
    hooks:
      - id: gitleaks
```

```bash
# Install and activate
pip install pre-commit
pre-commit install

# Now: any commit containing a secret-like pattern is blocked
# git commit → "Potential secret detected in config.py line 15"
```

### Centralized secret management with AWS Secrets Manager

```python
# secrets_client.py — application secret loading
import json
import boto3
from functools import lru_cache

secrets_client = boto3.client("secretsmanager")

@lru_cache(maxsize=32)
def get_secret(secret_name: str) -> dict:
    """Fetch secret from AWS Secrets Manager with caching."""
    response = secrets_client.get_secret_value(SecretId=secret_name)
    return json.loads(response["SecretString"])

# Usage in application
def get_database_url() -> str:
    secret = get_secret("prod/database")
    return (
        f"postgresql://{secret['username']}:{secret['password']}"
        f"@{secret['host']}:{secret['port']}/{secret['dbname']}"
    )

def get_api_key(service: str) -> str:
    secret = get_secret(f"prod/api-keys")
    return secret[service]
```

### Terraform: Encrypted state + secret references

```hcl
# Backend: Encrypt state at rest with KMS
terraform {
  backend "s3" {
    bucket         = "mycompany-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    kms_key_id     = "arn:aws:kms:us-east-1:123456789:key/abc-123"
    dynamodb_table = "terraform-locks"
  }
}

# Reference secrets from Secrets Manager (not hardcoded)
data "aws_secretsmanager_secret_version" "db_password" {
  secret_id = "prod/database"
}

locals {
  db_creds = jsondecode(data.aws_secretsmanager_secret_version.db_password.secret_string)
}

resource "aws_db_instance" "main" {
  engine         = "postgres"
  instance_class = "db.r6g.xlarge"
  username       = local.db_creds["username"]
  password       = local.db_creds["password"]

  # Mark as sensitive so it doesn't appear in plan output
  lifecycle {
    ignore_changes = [password]
  }
}
```

### Automatic secret rotation

```python
# Lambda function for automatic database password rotation
import boto3
import json
import string
import secrets as sec_module

def lambda_handler(event, context):
    """AWS Secrets Manager rotation Lambda."""
    step = event["Step"]
    secret_id = event["SecretId"]

    sm = boto3.client("secretsmanager")

    if step == "createSecret":
        # Generate new password
        current = json.loads(
            sm.get_secret_value(SecretId=secret_id)["SecretString"]
        )
        new_password = ''.join(
            sec_module.choice(string.ascii_letters + string.digits + "!@#$%")
            for _ in range(32)
        )
        current["password"] = new_password
        sm.put_secret_value(
            SecretId=secret_id,
            SecretString=json.dumps(current),
            VersionStage="AWSPENDING",
        )

    elif step == "setSecret":
        # Apply the new password to the database
        pending = json.loads(
            sm.get_secret_value(SecretId=secret_id, VersionStage="AWSPENDING")["SecretString"]
        )
        # Connect to RDS and ALTER USER
        conn = psycopg2.connect(host=pending["host"], user="admin", password=get_admin_pw())
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(f"ALTER USER {pending['username']} PASSWORD %s", (pending["password"],))

    elif step == "testSecret":
        # Verify new password works
        pending = json.loads(
            sm.get_secret_value(SecretId=secret_id, VersionStage="AWSPENDING")["SecretString"]
        )
        conn = psycopg2.connect(
            host=pending["host"], user=pending["username"],
            password=pending["password"], dbname=pending["dbname"]
        )
        conn.close()

    elif step == "finishSecret":
        sm.update_secret_version_stage(
            SecretId=secret_id,
            VersionStage="AWSCURRENT",
            MoveToVersionId=event["ClientRequestToken"],
        )
```

### Offboarding checklist (the ex-employee problem)

```markdown
## Employee Offboarding — Security Checklist

### Immediate (within 1 hour of departure)
- [ ] Disable SSO/SAML account (cascades to all integrated services)
- [ ] Revoke AWS IAM user and delete access keys
- [ ] Remove from GitHub organization
- [ ] Remove from Vault/Secrets Manager access policies
- [ ] Remove SSH keys from all servers (authorized_keys)
- [ ] Revoke VPN certificates

### Within 24 hours
- [ ] Rotate all shared secrets the employee had access to:
  - [ ] Database passwords
  - [ ] API keys for third-party services
  - [ ] Service account tokens
- [ ] Review and revoke any personal access tokens
- [ ] Remove from team password manager (1Password/Bitwarden)
- [ ] Audit recent access logs for unusual activity

### Within 1 week
- [ ] Review Terraform state for any secrets they could have extracted
- [ ] Rotate SSH host keys if employee had root access
- [ ] Review and revoke any OAuth app authorizations
```

### Migration from insecure to secure (practical steps)

| Current (insecure) | Migration step | Target (secure) |
|-------------------|---------------|-----------------|
| .env in Git | Move to Secrets Manager | Runtime secret fetch |
| Hardcoded in compose | Use Docker secrets / env_file | External secret reference |
| Terraform plaintext state | Enable S3+KMS encryption | Encrypted state |
| Secrets in Slack | Team password manager | 1Password/Bitwarden |
| Shared SSH keys | Per-user keys + bastion | SSM Session Manager (no SSH) |
| No rotation | Rotation Lambda | 90-day auto-rotation |'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
