"""Deployment — Docker multi-stage builds, Terraform, and blue-green deployments."""

PAIRS = [
    (
        "devops/docker-advanced",
        "Show advanced Docker patterns: multi-stage builds, health checks, non-root users, and optimization.",
        '''Advanced Docker patterns:

```dockerfile
# --- Multi-stage build (Python) ---

# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.lock ./
RUN pip install --no-cache-dir --prefix=/install -r requirements.lock


# Stage 2: Runtime image
FROM python:3.12-slim AS runtime

# Create non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

WORKDIR /app

# Install only runtime system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000

EXPOSE ${PORT}

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Run with exec form (PID 1, receives signals properly)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]


# --- Multi-stage build (TypeScript/Node) ---

# FROM node:20-alpine AS deps
# WORKDIR /app
# COPY package.json pnpm-lock.yaml ./
# RUN corepack enable && pnpm install --frozen-lockfile
#
# FROM node:20-alpine AS builder
# WORKDIR /app
# COPY --from=deps /app/node_modules ./node_modules
# COPY . .
# RUN pnpm build
#
# FROM node:20-alpine AS runner
# WORKDIR /app
# RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001
# COPY --from=builder --chown=nextjs:nodejs /app/.next/standalone ./
# COPY --from=builder --chown=nextjs:nodejs /app/.next/static ./.next/static
# COPY --from=builder --chown=nextjs:nodejs /app/public ./public
# USER nextjs
# EXPOSE 3000
# CMD ["node", "server.js"]
```

```yaml
# --- docker-compose.yml (development) ---

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
      target: runtime   # Use specific stage
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/myapp
      - REDIS_URL=redis://redis:6379
    volumes:
      - ./src:/app/src   # Hot reload in dev
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: "2.0"

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: myapp
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    ports:
      - "6379:6379"

  worker:
    build: .
    command: python -m app.worker
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/myapp
      - REDIS_URL=redis://redis:6379
    depends_on:
      - db
      - redis
    restart: unless-stopped

volumes:
  pgdata:
```

```dockerfile
# --- .dockerignore ---

# .git
# .env
# .env.*
# __pycache__
# *.pyc
# .pytest_cache
# .mypy_cache
# .ruff_cache
# node_modules
# .next
# dist
# coverage
# *.md
# Dockerfile*
# docker-compose*
```

Docker patterns:
1. **Multi-stage builds** — separate builder (gcc, dev deps) from slim runtime image
2. **Non-root user** — `useradd` + `USER appuser` for security
3. **`HEALTHCHECK`** — container self-reports health for orchestrator awareness
4. **`depends_on: condition`** — wait for database to be healthy before starting app
5. **`.dockerignore`** — exclude .git, node_modules, caches from build context'''
    ),
    (
        "devops/terraform-basics",
        "Show Terraform patterns: resource definitions, modules, variables, and state management.",
        '''Terraform infrastructure patterns:

```hcl
# --- main.tf ---

terraform {
  required_version = ">= 1.5"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # Remote state (team collaboration)
  backend "s3" {
    bucket         = "myapp-terraform-state"
    key            = "prod/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}


# --- variables.tf ---

variable "project_name" {
  type        = string
  description = "Project name for resource naming"
}

variable "environment" {
  type        = string
  description = "Environment (dev, staging, prod)"
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "Environment must be dev, staging, or prod."
  }
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
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


# --- VPC and networking ---

module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "5.5.0"

  name = "${var.project_name}-${var.environment}"
  cidr = "10.0.0.0/16"

  azs             = ["${var.aws_region}a", "${var.aws_region}b", "${var.aws_region}c"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]

  enable_nat_gateway     = true
  single_nat_gateway     = var.environment != "prod"  # Save cost in non-prod
  enable_dns_hostnames   = true
}


# --- RDS database ---

resource "aws_db_instance" "main" {
  identifier = "${var.project_name}-${var.environment}"

  engine         = "postgres"
  engine_version = "16.2"
  instance_class = var.environment == "prod" ? "db.r6g.large" : "db.t3.medium"

  allocated_storage     = 100
  max_allocated_storage = 500  # Auto-scaling

  db_name  = "myapp"
  username = "admin"
  password = var.db_password  # From secrets manager

  multi_az               = var.environment == "prod"
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.db.id]

  backup_retention_period = var.environment == "prod" ? 30 : 7
  deletion_protection     = var.environment == "prod"
  skip_final_snapshot     = var.environment != "prod"

  performance_insights_enabled = true
}


# --- outputs.tf ---

output "vpc_id" {
  value = module.vpc.vpc_id
}

output "db_endpoint" {
  value     = aws_db_instance.main.endpoint
  sensitive = true
}

output "alb_dns_name" {
  value = aws_lb.main.dns_name
}


# --- terraform.tfvars (per environment) ---

# prod.tfvars:
# project_name  = "myapp"
# environment   = "prod"
# instance_type = "t3.large"
# min_instances = 3
# max_instances = 20
```

```bash
# --- Terraform workflow ---

# Initialize (download providers, configure backend)
terraform init

# Format code
terraform fmt -recursive

# Validate configuration
terraform validate

# Plan changes (preview before applying)
terraform plan -var-file=prod.tfvars -out=plan.tfplan

# Apply changes
terraform apply plan.tfplan

# Import existing resource into state
terraform import aws_db_instance.main myapp-prod

# Show current state
terraform state list
terraform state show aws_db_instance.main

# Destroy specific resource
terraform destroy -target=aws_db_instance.main
```

Terraform patterns:
1. **Remote state** — S3 + DynamoDB locking for team collaboration
2. **`validation` blocks** — enforce variable constraints at plan time
3. **Conditional expressions** — `var.environment == "prod" ? ... : ...` for env differences
4. **Community modules** — `terraform-aws-modules/vpc` for common infrastructure
5. **`-var-file`** — per-environment configuration files for the same codebase'''
    ),
    (
        "devops/blue-green-deploy",
        "Show blue-green and canary deployment patterns: traffic shifting, rollback, and health verification.",
        '''Blue-green and canary deployment patterns:

```python
import asyncio
import httpx
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum, auto

logger = logging.getLogger(__name__)


class DeploymentStrategy(StrEnum):
    BLUE_GREEN = auto()
    CANARY = auto()
    ROLLING = auto()


@dataclass
class Environment:
    name: str           # "blue" or "green"
    url: str            # Backend URL
    is_live: bool = False
    version: str = ""
    deployed_at: datetime | None = None


@dataclass
class CanaryConfig:
    initial_percent: int = 5
    increment: int = 10
    interval_seconds: int = 60
    success_threshold: float = 0.99  # 99% success rate
    max_latency_ms: float = 500


@dataclass
class HealthCheck:
    url: str
    expected_status: int = 200
    timeout: float = 5.0
    retries: int = 3
    interval: float = 2.0


# --- Blue-Green deployment ---

class BlueGreenDeployer:
    """Zero-downtime deployment by swapping live environments."""

    def __init__(self, load_balancer, environments: dict[str, Environment]):
        self.lb = load_balancer
        self.envs = environments

    @property
    def live_env(self) -> Environment:
        for env in self.envs.values():
            if env.is_live:
                return env
        raise RuntimeError("No live environment")

    @property
    def staging_env(self) -> Environment:
        for env in self.envs.values():
            if not env.is_live:
                return env
        raise RuntimeError("No staging environment")

    async def deploy(self, version: str) -> bool:
        """Deploy new version using blue-green strategy."""
        staging = self.staging_env
        live = self.live_env

        logger.info(
            "Deploying %s to %s (live: %s)",
            version, staging.name, live.name,
        )

        # Step 1: Deploy to staging environment
        await self._deploy_version(staging, version)

        # Step 2: Health check staging
        if not await self._health_check(staging):
            logger.error("Health check failed on %s", staging.name)
            return False

        # Step 3: Run smoke tests
        if not await self._smoke_tests(staging):
            logger.error("Smoke tests failed on %s", staging.name)
            return False

        # Step 4: Swap traffic
        logger.info("Swapping traffic: %s -> %s", live.name, staging.name)
        await self.lb.set_backend(staging.url)

        staging.is_live = True
        staging.deployed_at = datetime.now(timezone.utc)
        live.is_live = False

        # Step 5: Verify after swap
        await asyncio.sleep(10)
        if not await self._verify_live(staging):
            logger.error("Post-swap verification failed, rolling back")
            await self.rollback()
            return False

        logger.info("Deployment complete: %s is live with %s", staging.name, version)
        return True

    async def rollback(self):
        """Swap back to previous environment."""
        current_live = self.live_env
        previous = self.staging_env  # Was live before swap

        logger.warning("Rolling back: %s -> %s", current_live.name, previous.name)
        await self.lb.set_backend(previous.url)

        current_live.is_live = False
        previous.is_live = True

    async def _health_check(self, env: Environment) -> bool:
        async with httpx.AsyncClient() as client:
            for attempt in range(5):
                try:
                    resp = await client.get(f"{env.url}/health", timeout=5.0)
                    if resp.status_code == 200:
                        return True
                except httpx.RequestError:
                    pass
                await asyncio.sleep(2)
        return False

    async def _smoke_tests(self, env: Environment) -> bool:
        async with httpx.AsyncClient() as client:
            endpoints = ["/api/health", "/api/version", "/api/ready"]
            for endpoint in endpoints:
                try:
                    resp = await client.get(f"{env.url}{endpoint}", timeout=5.0)
                    if resp.status_code >= 500:
                        return False
                except httpx.RequestError:
                    return False
        return True

    async def _verify_live(self, env: Environment) -> bool:
        return await self._health_check(env)

    async def _deploy_version(self, env: Environment, version: str):
        env.version = version
        # Trigger deployment (e.g., update container image)
        logger.info("Deploying %s to %s environment", version, env.name)


# --- Canary deployment ---

class CanaryDeployer:
    """Gradually shift traffic to new version with automatic rollback."""

    def __init__(self, load_balancer, config: CanaryConfig):
        self.lb = load_balancer
        self.config = config

    async def deploy(self, old_url: str, new_url: str, version: str) -> bool:
        """Canary deployment with progressive traffic shift."""
        percent = self.config.initial_percent

        while percent <= 100:
            logger.info("Canary at %d%% for %s", percent, version)
            await self.lb.set_weight(new_url, percent)
            await self.lb.set_weight(old_url, 100 - percent)

            # Wait and observe
            await asyncio.sleep(self.config.interval_seconds)

            # Check metrics
            metrics = await self._get_metrics(new_url)
            if not self._is_healthy(metrics):
                logger.error(
                    "Canary unhealthy at %d%%: %s. Rolling back.",
                    percent, metrics,
                )
                await self.lb.set_weight(old_url, 100)
                await self.lb.set_weight(new_url, 0)
                return False

            percent += self.config.increment

        logger.info("Canary complete: %s is at 100%%", version)
        return True

    def _is_healthy(self, metrics: dict) -> bool:
        success_rate = metrics.get("success_rate", 0)
        latency_p95 = metrics.get("latency_p95_ms", float("inf"))

        return (
            success_rate >= self.config.success_threshold
            and latency_p95 <= self.config.max_latency_ms
        )

    async def _get_metrics(self, url: str) -> dict:
        # Query Prometheus/metrics endpoint
        return {"success_rate": 0.995, "latency_p95_ms": 200}
```

Deployment patterns:
1. **Blue-green** — deploy to idle environment, swap traffic after health check
2. **Instant rollback** — swap back to previous environment on failure
3. **Canary** — gradual traffic shift (5% → 15% → 25% → ... → 100%)
4. **Health + smoke tests** — verify before and after traffic swap
5. **Auto-rollback** — revert canary if success rate drops below threshold'''
    ),
]
"""
