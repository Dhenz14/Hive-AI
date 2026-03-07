"""Documentation generation training pairs: config files, env variables, deployment settings."""

pairs = [
    {
        "instruction": r'''Document this Kubernetes deployment YAML for a team wiki. Explain what each section does and which values they should change vs leave alone:

apiVersion: apps/v1
kind: Deployment
metadata:
  name: api-server
  labels:
    app: api-server
    tier: backend
spec:
  replicas: 3
  selector:
    matchLabels:
      app: api-server
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  template:
    metadata:
      labels:
        app: api-server
        tier: backend
    spec:
      containers:
        - name: api
          image: registry.example.com/api-server:v2.4.1
          ports:
            - containerPort: 8080
          resources:
            requests:
              cpu: 250m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 1Gi
          env:
            - name: DATABASE_URL
              valueFrom:
                secretKeyRef:
                  name: db-credentials
                  key: url
            - name: LOG_LEVEL
              value: "info"
          readinessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
            initialDelaySeconds: 15
            periodSeconds: 20''',
        "output": r'''<think>
I need to explain this K8s deployment for a team that may include people who are not Kubernetes experts. I should explain each section clearly, highlight which values are commonly changed (image tag, replicas, resource limits, env vars) vs which are structural and rarely need changes (selector, labels, strategy type).
</think>

# API Server Deployment Configuration

This Kubernetes Deployment manages the api-server pods. Below is a section-by-section explanation.

## Key Sections

**Metadata** -- `name: api-server` is the deployment identity. Do not change it (that creates a new deployment). Labels like `app: api-server` are used by Services for routing.

**Replicas** -- `replicas: 3` runs three pod instances. Change this to scale. With `maxUnavailable: 0`, rollouts never take a pod down before a new one is ready (zero-downtime deploys).

**Image** -- Change the tag (e.g., `v2.4.1` -> `v2.5.0`) to deploy new code. CI updates this automatically.

**Resources** -- `requests` (250m CPU, 512Mi RAM) are the guaranteed minimum. `limits` (1 CPU, 1Gi RAM) are the hard ceiling. If the pod exceeds the memory limit, Kubernetes kills it. Adjust based on Grafana metrics.

## Environment Variables

```yaml
env:
  - name: DATABASE_URL         # Loaded from a Kubernetes Secret
    valueFrom:
      secretKeyRef:
        name: db-credentials   # Secret must exist in the same namespace
        key: url
  - name: LOG_LEVEL            # Hardcoded value
    value: "info"              # Change to "debug" for troubleshooting
```

**To update secrets:** edit the `db-credentials` Secret, then restart pods (`kubectl rollout restart deployment/api-server`).

## Health Checks

```yaml
readinessProbe:              # Gates traffic -- pod only receives requests after passing
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 5     # Wait 5s before first check
  periodSeconds: 10          # Check every 10s

livenessProbe:               # Restarts pod if it fails
  initialDelaySeconds: 15    # Wait 15s (longer than readiness -- app needs time to start)
  periodSeconds: 20          # Check every 20s
```

**Rarely change** unless the app's startup time changes. If pods are being killed during startup, increase `initialDelaySeconds` on the liveness probe.'''
    },
    {
        "instruction": r'''Document this nginx.conf for a reverse proxy setup. The audience is backend developers who need to understand and maintain it:

worker_processes auto;
events {
    worker_connections 1024;
}

http {
    upstream api_backend {
        least_conn;
        server api-1:8080 weight=3;
        server api-2:8080 weight=3;
        server api-3:8080 weight=1 backup;
    }

    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=30r/s;

    server {
        listen 80;
        server_name api.example.com;
        return 301 https://$host$request_uri;
    }

    server {
        listen 443 ssl http2;
        server_name api.example.com;

        ssl_certificate /etc/ssl/certs/api.crt;
        ssl_certificate_key /etc/ssl/private/api.key;

        client_max_body_size 25m;

        location /api/ {
            limit_req zone=api_limit burst=50 nodelay;
            proxy_pass http://api_backend/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            proxy_connect_timeout 5s;
            proxy_read_timeout 30s;
        }

        location /static/ {
            alias /var/www/static/;
            expires 30d;
            add_header Cache-Control "public, immutable";
        }

        location /healthz {
            access_log off;
            return 200 "ok";
        }
    }
}''',
        "output": r'''# Nginx Reverse Proxy Configuration

This nginx config serves as the entry point for all HTTP traffic to the API. It handles TLS termination, load balancing, rate limiting, and static file serving.

## Worker Settings

```nginx
worker_processes auto;         # One worker process per CPU core
events {
    worker_connections 1024;   # Max simultaneous connections per worker
}
```

`auto` is the recommended setting. Total max connections = worker_processes x worker_connections.

## Load Balancing (upstream block)

```nginx
upstream api_backend {
    least_conn;                        # Route to the server with fewest active connections
    server api-1:8080 weight=3;        # Primary -- gets 3x share of traffic
    server api-2:8080 weight=3;        # Primary -- gets 3x share of traffic
    server api-3:8080 weight=1 backup; # Only used if both primaries are down
}
```

- **least_conn** is better than round-robin when request durations vary (some endpoints are slower than others).
- **backup** means api-3 receives zero traffic under normal conditions. It activates only during failover.

## Rate Limiting

```nginx
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=30r/s;
```

- Limits each client IP to 30 requests per second.
- `10m` allocates 10 MB of shared memory for tracking (~160,000 IP addresses).
- Applied in the `/api/` location block with `burst=50 nodelay`: allows bursts up to 50 requests without queueing, but excess requests beyond the burst are rejected with 503.

## HTTP -> HTTPS Redirect

The first `server` block listens on port 80 and redirects all traffic to HTTPS with a 301 permanent redirect.

## HTTPS Server

### TLS

```nginx
listen 443 ssl http2;
ssl_certificate /etc/ssl/certs/api.crt;
ssl_certificate_key /etc/ssl/private/api.key;
```

HTTP/2 is enabled for multiplexed connections. Certificate files are managed by the ops team and renewed via certbot.

### Location Blocks

**`/api/`** -- Proxied to the backend cluster. Important headers:
- `X-Real-IP`: the client's actual IP (not nginx's)
- `X-Forwarded-Proto`: tells the backend whether the original request was HTTP or HTTPS
- Timeouts: 5s to establish a connection, 30s to read a response

**`/static/`** -- Served directly from disk with 30-day browser cache. The `immutable` directive tells browsers to never revalidate during the cache lifetime.

**`/healthz`** -- Returns 200 OK for load balancer health checks. Access logging is disabled to avoid log noise.

### Upload Size Limit

```nginx
client_max_body_size 25m;
```

Requests with bodies larger than 25 MB are rejected with 413 Request Entity Too Large. Increase this if your API accepts large file uploads.'''
    },
    {
        "instruction": r'''Document the environment variables for this Docker-based Python application. Here's the relevant code:

# settings.py
import os

class Settings:
    # Server
    HOST = os.getenv("APP_HOST", "0.0.0.0")
    PORT = int(os.getenv("APP_PORT", "8000"))
    WORKERS = int(os.getenv("APP_WORKERS", "4"))
    DEBUG = os.getenv("APP_DEBUG", "false").lower() == "true"

    # Database
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = int(os.getenv("DB_PORT", "5432"))
    DB_NAME = os.getenv("DB_NAME", "appdb")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "2"))
    DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))
    DB_SSL_MODE = os.getenv("DB_SSL_MODE", "prefer")

    # Cache
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CACHE_TTL = int(os.getenv("CACHE_TTL", "300"))

    # Auth
    JWT_SECRET = os.getenv("JWT_SECRET", "")
    JWT_EXPIRY_HOURS = int(os.getenv("JWT_EXPIRY_HOURS", "24"))
    ALLOWED_ORIGINS = os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")

    # External Services
    SMTP_HOST = os.getenv("SMTP_HOST", "")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SENTRY_DSN = os.getenv("SENTRY_DSN", "")''',
        "output": r'''# Environment Variables Reference

All configuration is done through environment variables. Defaults are provided for local development; production deployments must set the variables marked as **required**.

## Server

| Variable     | Type   | Default   | Description                                 |
|--------------|--------|-----------|---------------------------------------------|
| APP_HOST     | string | 0.0.0.0   | Bind address for the HTTP server            |
| APP_PORT     | int    | 8000      | Port the server listens on                  |
| APP_WORKERS  | int    | 4         | Number of worker processes (set to CPU count in production) |
| APP_DEBUG    | bool   | false     | Enable debug mode. **Must be false in production.** |

## Database

| Variable     | Type   | Default   | Description                                 |
|--------------|--------|-----------|---------------------------------------------|
| DB_HOST      | string | localhost | PostgreSQL hostname                         |
| DB_PORT      | int    | 5432      | PostgreSQL port                             |
| DB_NAME      | string | appdb     | Database name                               |
| DB_USER      | string | postgres  | Database user                               |
| DB_PASSWORD  | string | (empty)   | Database password. **Required in production.** |
| DB_POOL_MIN  | int    | 2         | Min connections in pool                     |
| DB_POOL_MAX  | int    | 10        | Max connections in pool                     |
| DB_SSL_MODE  | string | prefer    | Use `require` or `verify-full` in production |

## Cache

| Variable   | Type   | Default                    | Description                    |
|------------|--------|----------------------------|--------------------------------|
| REDIS_URL  | string | redis://localhost:6379/0   | Redis connection URL           |
| CACHE_TTL  | int    | 300                        | Default cache TTL in seconds   |

## Authentication

| Variable        | Type   | Default              | Description                              |
|-----------------|--------|----------------------|------------------------------------------|
| JWT_SECRET      | string | (empty)              | Signing key for JWT tokens. **Required.** Generate with: `python -c "import secrets; print(secrets.token_hex(32))"` |
| JWT_EXPIRY_HOURS| int    | 24                   | Token lifetime in hours                  |
| ALLOWED_ORIGINS | string | http://localhost:3000 | Comma-separated CORS origins             |

## External Services

| Variable      | Type   | Default | Description                                |
|---------------|--------|---------|--------------------------------------------|
| SMTP_HOST     | string | (empty) | SMTP server for outbound email             |
| SMTP_PORT     | int    | 587     | SMTP port (587 for STARTTLS, 465 for SSL)  |
| SMTP_USER     | string | (empty) | SMTP authentication username               |
| SMTP_PASSWORD | string | (empty) | SMTP authentication password               |
| SENTRY_DSN    | string | (empty) | Sentry error tracking DSN. Leave empty to disable. |'''
    },
    {
        "instruction": r'''Document this Terraform module's input variables and outputs for the team:

variable "environment" {
  type        = string
  description = "Deployment environment"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Must be dev, staging, or prod."
  }
}

variable "instance_type" {
  type    = string
  default = "t3.medium"
}

variable "min_instances" {
  type    = number
  default = 2
}

variable "max_instances" {
  type    = number
  default = 10
}

variable "enable_monitoring" {
  type    = bool
  default = true
}

variable "db_instance_class" {
  type    = string
  default = "db.r6g.large"
}

variable "db_storage_gb" {
  type    = number
  default = 100
}

variable "alert_email" {
  type    = string
  default = ""
}

output "alb_dns_name" {
  value = aws_lb.main.dns_name
}

output "rds_endpoint" {
  value = aws_db_instance.main.endpoint
}

output "asg_name" {
  value = aws_autoscaling_group.main.name
}''',
        "output": r'''<think>
This is a Terraform module with input variables and outputs. I need to document each variable with its purpose, type, default, and any validation rules. I should also recommend values for different environments since the environment variable accepts dev/staging/prod.
</think>

# Infrastructure Module: Application Stack

This Terraform module provisions an Application Load Balancer, Auto Scaling Group, and RDS database instance.

## Input Variables

### Required

| Variable      | Type   | Description                                          |
|---------------|--------|------------------------------------------------------|
| `environment` | string | Deployment environment. Must be `dev`, `staging`, or `prod`. Used for resource naming and tagging. |

### Optional

| Variable            | Type   | Default       | Description                                        |
|---------------------|--------|---------------|----------------------------------------------------|
| `instance_type`     | string | t3.medium     | EC2 instance type for the application servers       |
| `min_instances`     | number | 2             | Minimum instances in the Auto Scaling Group         |
| `max_instances`     | number | 10            | Maximum instances during scale-out                  |
| `enable_monitoring` | bool   | true          | Enable detailed CloudWatch monitoring and alarms    |
| `db_instance_class` | string | db.r6g.large  | RDS instance class for the PostgreSQL database      |
| `db_storage_gb`     | number | 100           | Allocated database storage in gigabytes             |
| `alert_email`       | string | (empty)       | Email for CloudWatch alarm notifications. No alerts if empty. |

## Outputs

| Output         | Description                                      |
|----------------|--------------------------------------------------|
| `alb_dns_name` | DNS name of the ALB. Point your CNAME here.      |
| `rds_endpoint` | RDS connection endpoint for DATABASE_URL.         |
| `asg_name`     | Auto Scaling Group name for scaling/CI integration.|

## Usage

```hcl
module "app" {
  source = "./modules/app-stack"
  environment       = "prod"
  instance_type     = "t3.large"
  min_instances     = 3
  max_instances     = 10
  db_instance_class = "db.r6g.xlarge"
  db_storage_gb     = 200
  alert_email       = "ops-team@example.com"
}
```'''
    },
    {
        "instruction": r'''Document this GitHub Actions workflow YAML for a team that is not familiar with CI/CD:

name: CI/CD Pipeline
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_PASSWORD: testpass
          POSTGRES_DB: testdb
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: pytest --cov --cov-report=xml
        env:
          DATABASE_URL: postgresql://postgres:testpass@localhost:5432/testdb

  build-and-push:
    needs: test
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    steps:
      - uses: actions/checkout@v4
      - uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v5
        with:
          push: true
          tags: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ github.sha }}''',
        "output": r'''# CI/CD Pipeline Documentation

This GitHub Actions workflow automatically tests your code and deploys it when changes are merged to main.

## When Does It Run?

- **On every pull request** targeting the `main` branch -- runs tests only
- **On every push to `main`** (i.e., when a PR is merged) -- runs tests, then builds and publishes a Docker image

## What It Does

### Job 1: Test

Runs pytest with code coverage against a real PostgreSQL 15 database (spun up automatically as a service container with health checks). Runs on every push and PR.

### Job 2: Build and Push

Builds a Docker image and pushes it to ghcr.io, tagged with the commit SHA. Only runs on pushes to main and only after tests pass (`needs: test`). Uses the built-in GITHUB_TOKEN -- no secrets to configure.

## Key Details

- **Image tags use the commit SHA** -- every merge produces a traceable image
- **Test failures block deployment** -- build-and-push is skipped if tests fail
- **Opening a PR:** tests run automatically (check the "Checks" tab)
- **Merging to main:** tests run again, then the image is built and pushed'''
    },
]
