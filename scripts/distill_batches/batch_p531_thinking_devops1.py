"""Phase 1H: Foundation Thinking — Data Modeling & DevOps (Part 3/5)
CI/CD, Docker, deployment strategies, infrastructure as code."""

PAIRS = [
    (
        "thinking/devops-docker-best-practices",
        "Review our Dockerfile. It works but the image is 2.3GB and takes 15 minutes to build:\n\n```dockerfile\nFROM python:3.12\n\nCOPY . /app\nWORKDIR /app\n\nRUN pip install -r requirements.txt\nRUN python manage.py collectstatic --noinput\n\nEXPOSE 8000\nCMD [\"gunicorn\", \"myapp.wsgi\", \"-b\", \"0.0.0.0:8000\"]\n```",
        r'''<think>
Issues with this Dockerfile:
1. `python:3.12` is the full image (~900MB). Use `slim` or `alpine`.
2. `COPY . /app` copies everything including .git, __pycache__, node_modules. Use .dockerignore.
3. `COPY` before `pip install` means requirements change invalidates the pip cache. Copy requirements.txt first.
4. No multi-stage build — build tools and dev dependencies end up in the final image.
5. Running as root (security issue).
6. `collectstatic` should be in the build stage, not runtime.

Let me fix all of these.
</think>

Multiple issues. Here's the optimized version:

## Optimized Dockerfile

```dockerfile
# Stage 1: Build
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (cached if requirements unchanged)
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Copy app code
COPY . .
RUN python manage.py collectstatic --noinput

# Stage 2: Runtime (minimal image)
FROM python:3.12-slim

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local
COPY --from=builder /app /app

WORKDIR /app

# Security: run as non-root user
RUN useradd -m appuser
USER appuser

EXPOSE 8000
CMD ["gunicorn", "myapp.wsgi", "-b", "0.0.0.0:8000", "-w", "4"]
```

## .dockerignore

```
.git
.gitignore
__pycache__
*.pyc
.env
.venv
node_modules
*.md
tests/
docker-compose*.yml
```

## What Changed

| Before | After | Impact |
|--------|-------|--------|
| `python:3.12` (900MB) | `python:3.12-slim` (150MB) | -750MB |
| Copy all files first | Copy requirements.txt first | Build cache: pip install only reruns when requirements change |
| Single stage | Multi-stage | Build tools not in final image |
| Root user | Non-root `appuser` | Security best practice |
| No .dockerignore | .dockerignore added | Smaller context, faster COPY |

**Result**: 2.3GB → ~250MB, 15 min → 2 min (with cache: 30 seconds).'''
    ),
    (
        "thinking/devops-cicd-pipeline",
        "Design a CI/CD pipeline for our Python web app. We use GitHub, have a test suite, and deploy to a Kubernetes cluster. What should the pipeline look like?",
        r'''<think>
A production CI/CD pipeline needs:
1. Lint + format check (fast feedback)
2. Unit tests
3. Integration tests
4. Security scanning
5. Docker build
6. Deploy to staging
7. E2E tests on staging
8. Deploy to production (with approval)

Let me design this as GitHub Actions.
</think>

## GitHub Actions CI/CD Pipeline

```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  # Stage 1: Fast checks (parallel)
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install ruff mypy
      - run: ruff check src/
      - run: ruff format --check src/
      - run: mypy src/ --ignore-missing-imports

  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
        env: { POSTGRES_DB: test, POSTGRES_PASSWORD: test }
        ports: ["5432:5432"]
        options: --health-cmd pg_isready
      redis:
        image: redis:7
        ports: ["6379:6379"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r requirements.txt -r requirements-test.txt
      - run: pytest tests/ -x --tb=short --cov=src --cov-fail-under=80
        env:
          DATABASE_URL: postgresql://postgres:test@localhost/test
          REDIS_URL: redis://localhost:6379

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install pip-audit bandit safety
      - run: pip-audit                    # Known vulnerable packages
      - run: bandit -r src/ -ll           # Python security linter
      - run: gitleaks detect --source .   # Hardcoded secrets

  # Stage 2: Build (after all checks pass)
  build:
    needs: [lint, test, security]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: docker/setup-buildx-action@v3
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v5
        with:
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # Stage 3: Deploy to staging
  deploy-staging:
    needs: build
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - run: |
          kubectl set image deployment/myapp \
            myapp=ghcr.io/${{ github.repository }}:${{ github.sha }} \
            --namespace staging
      - run: kubectl rollout status deployment/myapp --namespace staging --timeout=300s

  # Stage 4: E2E tests on staging
  e2e:
    needs: deploy-staging
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: npx playwright install --with-deps
      - run: npx playwright test
        env:
          BASE_URL: https://staging.myapp.com

  # Stage 5: Deploy to production (manual approval)
  deploy-production:
    needs: e2e
    runs-on: ubuntu-latest
    environment: production  # Requires approval in GitHub settings
    steps:
      - uses: actions/checkout@v4
      - run: |
          kubectl set image deployment/myapp \
            myapp=ghcr.io/${{ github.repository }}:${{ github.sha }} \
            --namespace production
      - run: kubectl rollout status deployment/myapp --namespace production --timeout=300s
```

## Pipeline Flow

```
PR opened:
  lint ─┐
  test ─┼→ All pass → PR can merge
  security ┘

Merged to main:
  lint ─┐
  test ─┼→ build → deploy staging → E2E → [approval] → deploy production
  security ┘
```

## Key Design Decisions

1. **Parallel fast checks** — lint, test, security run simultaneously
2. **Docker layer caching** — rebuilds are fast (~30s with cache)
3. **Staging environment** — E2E tests run against real infrastructure
4. **Manual approval** — production deploy requires human click
5. **Rollback** — `kubectl rollout undo` if issues detected'''
    ),
    (
        "thinking/devops-deployment-strategies",
        "We're deploying a new version that changes the database schema. How do we deploy without downtime? What deployment strategy should we use?",
        r'''<think>
Deployment strategies:
1. Rolling update — gradually replace old pods with new ones
2. Blue-green — run two full environments, switch traffic
3. Canary — send a small % of traffic to new version
4. Feature flags — deploy code but toggle feature on/off

For schema changes, the key is making migrations backward-compatible (both old and new code must work with the same schema).

The process:
1. Deploy migration that's backward-compatible
2. Deploy new code (rolling update)
3. Clean up old schema artifacts

Let me explain with an example.
</think>

## Step 1: Make Database Migration Backward-Compatible

```
WRONG: Rename column in one step
  → Old code crashes because column doesn't exist

RIGHT: Expand-migrate-contract (3 deploys)
  Deploy 1: Add new column (old code still works)
  Deploy 2: New code reads new column (both work)
  Deploy 3: Drop old column (cleanup)
```

## Step 2: Choose Deployment Strategy

### Rolling Update (Default, Good for Most Cases)

```yaml
# Kubernetes deployment
spec:
  replicas: 4
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1        # Add 1 new pod before removing old
      maxUnavailable: 0  # Never remove a pod before new one is ready
```

```
v1 v1 v1 v1    ← Start: all v1
v1 v1 v1 v2    ← New pod added, health check passes
v1 v1 v2 v2    ← Old pod removed, new added
v1 v2 v2 v2    ← Continue
v2 v2 v2 v2    ← Complete
```

### Canary Deployment (For Risky Changes)

```yaml
# Deploy canary with 10% traffic
apiVersion: networking.istio.io/v1alpha3
kind: VirtualService
spec:
  http:
    - route:
        - destination:
            host: myapp
            subset: stable
          weight: 90
        - destination:
            host: myapp
            subset: canary
          weight: 10
```

```
Step 1: 10% traffic → v2 (canary)
Step 2: Monitor error rate, latency, logs
Step 3: If OK → 50% → 100%
Step 3: If bad → 0% (instant rollback)
```

### Blue-Green (For Major Changes)

```
Blue (current): v1 handling all traffic
Green (new):    v2 deployed, tested, idle

Switch:  DNS/load balancer flips from Blue to Green
Rollback: Flip back to Blue (instant)
```

## Decision Matrix

| Strategy | Downtime | Rollback Speed | Risk | Best For |
|----------|----------|---------------|------|----------|
| Rolling | Zero | ~1 min | Medium | Most deployments |
| Canary | Zero | Instant | Low | Risky changes, new features |
| Blue-Green | Zero | Instant | Low | Major version bumps |
| Recreate | Brief | Slow | High | Dev/staging only |

## Database Migration + Deployment Sequence

```
1. Run backward-compatible migration:
   $ kubectl apply -f migration-job.yaml
   # Adds new column, doesn't remove old one

2. Deploy new code (rolling update):
   $ kubectl set image deployment/app app=v2
   # New code writes to both columns
   # Old code still works with old column

3. Verify everything works (1-2 days)

4. Cleanup migration (next sprint):
   $ kubectl apply -f cleanup-migration-job.yaml
   # Remove old column, triggers, etc.
```

**Golden rule**: Never deploy a migration and code change that depend on each other simultaneously. Migration first, then code.'''
    ),
    (
        "thinking/devops-monitoring-alerting",
        "We keep getting paged at 3AM for issues that aren't actually critical. Our monitoring is either too noisy or misses real problems. How do we set up proper alerting?",
        r'''<think>
Alert fatigue is a real problem. The solution:
1. Categorize alerts by severity (page vs ticket vs log)
2. Alert on symptoms (user-facing impact) not causes (CPU high)
3. Actionable alerts only — if you can't do anything about it at 3AM, it shouldn't wake you up
4. SLO-based alerting
</think>

## The Alert Pyramid

```
              /  PAGE  \          ← Wakes someone up
             /  TICKET  \        ← Creates a ticket, fix next day
            /    LOG     \       ← Recorded, reviewed weekly
           / DASHBOARD    \      ← Visible but no notification
```

## Rule 1: Alert on Symptoms, Not Causes

```yaml
# BAD: Alerting on causes (noisy, often not impactful)
- alert: HighCPU
  expr: cpu_usage > 80%        # CPU is high but users aren't affected
  severity: page               # Wakes someone at 3AM for nothing

# GOOD: Alerting on symptoms (user-facing impact)
- alert: HighErrorRate
  expr: |
    rate(http_requests_total{status=~"5.."}[5m])
    / rate(http_requests_total[5m]) > 0.05
  for: 5m                      # Must persist for 5 min (not a spike)
  severity: page
  annotations:
    summary: "Error rate above 5% for 5 minutes"
    runbook: "https://wiki/runbooks/high-error-rate"
```

## Rule 2: Every Alert Must Be Actionable

```yaml
# PAGE (wake someone up):
# "Is a human needed RIGHT NOW to prevent user impact?"
- alert: ServiceDown
  expr: up{job="api"} == 0
  for: 2m
  severity: page

- alert: ErrorRateCritical
  expr: error_rate > 0.1  # 10% errors
  for: 5m
  severity: page

- alert: LatencyP99Critical
  expr: http_request_duration_seconds{quantile="0.99"} > 5
  for: 10m
  severity: page

# TICKET (fix tomorrow):
- alert: DiskSpaceWarning
  expr: disk_free_percent < 20
  for: 30m
  severity: ticket
  annotations:
    summary: "Disk space below 20%, clean up within 24h"

- alert: CertificateExpiringSoon
  expr: ssl_cert_expires_in_days < 14
  severity: ticket

# LOG ONLY (review weekly):
- alert: HighMemoryUsage
  expr: memory_usage > 80%
  severity: log
```

## Rule 3: Include Runbooks

Every page-level alert must link to a runbook:

```markdown
# Runbook: High Error Rate

## Symptoms
- Error rate above 5% on API

## Quick Diagnosis
1. Check which endpoints are failing:
   `kubectl logs -l app=api --tail=100 | grep ERROR`
2. Check if a dependency is down:
   `curl -s http://payment-service/health`
3. Check recent deployments:
   `kubectl rollout history deployment/api`

## Resolution
- If bad deploy: `kubectl rollout undo deployment/api`
- If dependency down: Enable circuit breaker feature flag
- If database: Check connection pool and slow queries
```

## The Four Golden Signals (Google SRE)

```yaml
# Monitor these for every service:

# 1. Latency (how long requests take)
- record: http_latency_p99
  expr: histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

# 2. Traffic (how much demand)
- record: http_requests_per_second
  expr: rate(http_requests_total[5m])

# 3. Errors (how many failures)
- record: http_error_rate
  expr: rate(http_requests_total{status=~"5.."}[5m]) / rate(http_requests_total[5m])

# 4. Saturation (how full is the system)
- record: cpu_saturation
  expr: 1 - avg(rate(node_cpu_seconds_total{mode="idle"}[5m]))
```

**Test**: If your on-call got paged 0 times last week, your alerts might be missing things. If they got paged 20 times, your alerts are too noisy. Target: 1-3 pages/week.'''
    ),
    (
        "thinking/devops-secrets-management",
        "Our application has API keys and database passwords hardcoded in config files that are committed to git. We know this is bad. What's the proper way to manage secrets?",
        r'''<think>
Secrets management hierarchy:
1. Environment variables (simplest, OK for small teams)
2. .env files (NOT committed to git)
3. Cloud secrets managers (AWS Secrets Manager, GCP Secret Manager, Azure Key Vault)
4. HashiCorp Vault (self-hosted, most flexible)

For most teams, start with environment variables in CI/CD + cloud secrets manager for production.
</think>

## Step 1: Remove Secrets from Git (Immediately)

```bash
# Check if secrets are in git history
gitleaks detect --source . --verbose

# If found, rotate ALL exposed secrets (don't just remove from code)
# Old secrets are in git history forever — consider them compromised
```

## Step 2: Use Environment Variables

```python
# BEFORE (BAD):
DATABASE_URL = "postgresql://admin:supersecret@db.example.com/myapp"
STRIPE_API_KEY = "sk_live_abc123"

# AFTER (GOOD):
import os

DATABASE_URL = os.environ["DATABASE_URL"]
STRIPE_API_KEY = os.environ["STRIPE_API_KEY"]

# With defaults for development only:
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
```

## Step 3: .env for Local Development

```bash
# .env (NEVER commit this file)
DATABASE_URL=postgresql://localhost/myapp_dev
STRIPE_API_KEY=sk_test_local_key
SECRET_KEY=dev-only-not-real

# .gitignore
.env
.env.local
.env.*.local
```

```python
# Load .env in development
from dotenv import load_dotenv
load_dotenv()  # Reads .env file into environment
```

## Step 4: CI/CD Secrets

```yaml
# GitHub Actions — secrets set in repository settings
deploy:
  steps:
    - run: ./deploy.sh
      env:
        DATABASE_URL: ${{ secrets.DATABASE_URL }}
        STRIPE_API_KEY: ${{ secrets.STRIPE_API_KEY }}
```

## Step 5: Cloud Secrets Manager (Production)

```python
# AWS Secrets Manager
import boto3
import json

def get_secret(name):
    client = boto3.client('secretsmanager')
    response = client.get_secret_value(SecretId=name)
    return json.loads(response['SecretString'])

# At startup:
secrets = get_secret('myapp/production')
DATABASE_URL = secrets['database_url']
STRIPE_KEY = secrets['stripe_api_key']
```

```yaml
# Kubernetes — mount secrets as environment variables
apiVersion: v1
kind: Secret
metadata:
  name: myapp-secrets
type: Opaque
data:
  DATABASE_URL: cG9zdGdyZXM6Ly8u...  # base64 encoded

---
apiVersion: apps/v1
kind: Deployment
spec:
  containers:
    - name: myapp
      envFrom:
        - secretRef:
            name: myapp-secrets
```

## Secrets Checklist

```
□ No secrets in source code or config files
□ .env files in .gitignore
□ Secrets rotated if ever exposed
□ Different secrets per environment (dev ≠ staging ≠ prod)
□ CI/CD secrets in the platform's secret store
□ Production secrets in a secrets manager
□ gitleaks in CI pipeline to prevent future leaks
```'''
    ),
    (
        "thinking/devops-infrastructure-as-code",
        "We've been manually creating servers and configuring them through SSH. Every server is slightly different and we can't reproduce our setup. How do we fix this?",
        r'''<think>
Infrastructure as Code (IaC) — define infrastructure in version-controlled files. Two main tools:
1. Terraform — for provisioning infrastructure (servers, networks, databases)
2. Ansible/Docker — for configuring servers and applications

For a modern setup:
- Terraform for cloud infrastructure
- Docker for application packaging
- Kubernetes (or Docker Compose) for orchestration

Let me show a practical example.
</think>

## The Problem: Snowflake Servers

```
Server A: Python 3.11, nginx 1.22, PostgreSQL 14, Ubuntu 20.04
Server B: Python 3.12, nginx 1.24, PostgreSQL 15, Ubuntu 22.04
Server C: Python 3.11, no nginx (?), PostgreSQL 14, Ubuntu 20.04

"It works on Server A but not Server B" → classic snowflake problem
```

## The Fix: Everything in Code

### 1. Terraform for Infrastructure

```hcl
# infrastructure/main.tf
provider "aws" {
  region = "us-east-1"
}

resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
  tags = { Name = "myapp-vpc" }
}

resource "aws_db_instance" "postgres" {
  identifier        = "myapp-db"
  engine            = "postgres"
  engine_version    = "16"
  instance_class    = "db.t3.medium"
  allocated_storage = 100
  db_name           = "myapp"
  username          = var.db_username
  password          = var.db_password
  multi_az          = true
  backup_retention_period = 7
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id      = "myapp-cache"
  engine          = "redis"
  node_type       = "cache.t3.medium"
  num_cache_nodes = 1
}

resource "aws_ecs_service" "api" {
  name            = "myapp-api"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.api.arn
  desired_count   = 3

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }
}
```

```bash
# Provision infrastructure
terraform init
terraform plan    # Preview changes
terraform apply   # Create/update infrastructure
```

### 2. Docker for Application

```dockerfile
# Dockerfile — identical environment everywhere
FROM python:3.12-slim
# ... (same as earlier example)
```

### 3. Docker Compose for Local Development

```yaml
# docker-compose.yml
services:
  api:
    build: .
    ports: ["8000:8000"]
    environment:
      DATABASE_URL: postgresql://postgres:dev@db/myapp
      REDIS_URL: redis://redis:6379
    depends_on: [db, redis]

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: myapp
      POSTGRES_PASSWORD: dev
    volumes:
      - pgdata:/var/lib/postgresql/data

  redis:
    image: redis:7

volumes:
  pgdata:
```

## Benefits

```
Before (manual):
  "How do we recreate the production setup?"
  "Nobody knows, the guy who set it up left"
  "Every server is different"

After (IaC):
  git clone → docker compose up  (local dev, 30 seconds)
  terraform apply                (production, 5 minutes)
  Everything version-controlled, reviewable, reproducible
```

**Start with Docker Compose** for local dev. Add Terraform when you need cloud infrastructure. The goal: anyone can recreate the entire stack from the repo alone.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
