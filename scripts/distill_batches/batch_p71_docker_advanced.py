"""DevOps — Docker advanced, multi-stage builds, Compose, and Makefile patterns."""

PAIRS = [
    (
        "devops/dockerfile-patterns",
        "Show Dockerfile patterns: multi-stage builds, layer caching, security hardening, and Python optimization.",
        '''Dockerfile best practices:

```dockerfile
# --- Multi-stage Python build ---

# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies (cached unless requirements change)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt


# Stage 2: Production image
FROM python:3.12-slim AS production

# Install runtime-only dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Security: non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR /app

# Copy application code (last — changes most frequently)
COPY --chown=appuser:appuser . .

# Security hardening
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Metadata
LABEL maintainer="team@example.com"
LABEL version="1.0.0"

EXPOSE 8000

# Use exec form (PID 1 signal handling)
CMD ["gunicorn", "app:create_app()", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--timeout", "120", \
     "--access-logfile", "-"]


# --- Node.js multi-stage ---
# FROM node:20-alpine AS deps
# WORKDIR /app
# COPY package.json package-lock.json ./
# RUN npm ci --only=production
#
# FROM node:20-alpine AS build
# WORKDIR /app
# COPY package.json package-lock.json ./
# RUN npm ci
# COPY . .
# RUN npm run build
#
# FROM node:20-alpine
# WORKDIR /app
# COPY --from=deps /app/node_modules ./node_modules
# COPY --from=build /app/dist ./dist
# USER node
# CMD ["node", "dist/server.js"]
```

```yaml
# --- Docker Compose for development ---
# docker-compose.yml

services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
      target: production  # Use specific stage
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/mydb
      - REDIS_URL=redis://cache:6379/0
      - LOG_LEVEL=INFO
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_started
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 512M
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
      POSTGRES_DB: mydb
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d mydb"]
      interval: 5s
      timeout: 5s
      retries: 5

  cache:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redisdata:/data
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru

  worker:
    build: .
    command: celery -A app.celery worker -l info -c 4
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/mydb
      - REDIS_URL=redis://cache:6379/0
    depends_on:
      - db
      - cache

volumes:
  pgdata:
  redisdata:
```

Docker patterns:
1. **Multi-stage builds** — builder stage for compilation, slim final image
2. **Layer ordering** — dependencies before code (cache expensive layers)
3. **Non-root user** — `USER appuser` for security (never run as root)
4. **Exec form CMD** — `["cmd", "arg"]` for proper signal handling (PID 1)
5. **Health checks** — `HEALTHCHECK` for orchestrator integration'''
    ),
    (
        "devops/makefile-patterns",
        "Show Makefile patterns: project automation, phony targets, variables, and multi-language support.",
        '''Makefile patterns for project automation:

```makefile
# --- Variables ---
SHELL := /bin/bash
.DEFAULT_GOAL := help

# Project config
APP_NAME := myapp
VERSION := $(shell git describe --tags --always --dirty 2>/dev/null || echo "dev")
COMMIT := $(shell git rev-parse --short HEAD 2>/dev/null || echo "unknown")
BUILD_TIME := $(shell date -u +"%Y-%m-%dT%H:%M:%SZ")

# Docker
DOCKER_IMAGE := registry.example.com/$(APP_NAME)
DOCKER_TAG := $(VERSION)

# Python
PYTHON := python3
VENV := .venv
PIP := $(VENV)/bin/pip
PYTEST := $(VENV)/bin/pytest

# Colors
GREEN := \\033[0;32m
YELLOW := \\033[0;33m
RED := \\033[0;31m
NC := \\033[0m


# --- Help (auto-generated from comments) ---

.PHONY: help
help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "$(GREEN)%-20s$(NC) %s\n", $$1, $$2}'


# --- Setup ---

.PHONY: setup
setup: $(VENV)/bin/activate ## Set up development environment
	$(PIP) install -r requirements.txt -r requirements-dev.txt
	pre-commit install
	@echo "$(GREEN)Development environment ready!$(NC)"

$(VENV)/bin/activate:
	$(PYTHON) -m venv $(VENV)
	$(PIP) install --upgrade pip


# --- Development ---

.PHONY: run
run: ## Run development server
	$(VENV)/bin/uvicorn app:create_app --reload --port 8000

.PHONY: shell
shell: ## Start Python shell with app context
	$(VENV)/bin/python -c "from app import create_app; app = create_app()" -i

.PHONY: db-migrate
db-migrate: ## Run database migrations
	$(VENV)/bin/alembic upgrade head

.PHONY: db-rollback
db-rollback: ## Rollback last migration
	$(VENV)/bin/alembic downgrade -1

.PHONY: db-seed
db-seed: ## Seed database with test data
	$(VENV)/bin/python -m scripts.seed


# --- Testing ---

.PHONY: test
test: ## Run all tests
	$(PYTEST) tests/ -v --tb=short

.PHONY: test-unit
test-unit: ## Run unit tests only
	$(PYTEST) tests/unit/ -v --tb=short

.PHONY: test-integration
test-integration: ## Run integration tests
	$(PYTEST) tests/integration/ -v --tb=short -m integration

.PHONY: test-coverage
test-coverage: ## Run tests with coverage report
	$(PYTEST) tests/ --cov=app --cov-report=html --cov-report=term-missing
	@echo "$(GREEN)Coverage report: htmlcov/index.html$(NC)"

.PHONY: test-watch
test-watch: ## Run tests in watch mode
	$(VENV)/bin/ptw -- -v --tb=short


# --- Code Quality ---

.PHONY: lint
lint: ## Run all linters
	$(VENV)/bin/ruff check .
	$(VENV)/bin/mypy app/ --ignore-missing-imports

.PHONY: format
format: ## Format code
	$(VENV)/bin/ruff format .
	$(VENV)/bin/ruff check --fix .

.PHONY: check
check: lint test ## Run all checks (lint + test)


# --- Docker ---

.PHONY: docker-build
docker-build: ## Build Docker image
	docker build \
		--build-arg VERSION=$(VERSION) \
		--build-arg COMMIT=$(COMMIT) \
		--build-arg BUILD_TIME=$(BUILD_TIME) \
		-t $(DOCKER_IMAGE):$(DOCKER_TAG) \
		-t $(DOCKER_IMAGE):latest \
		.

.PHONY: docker-push
docker-push: docker-build ## Build and push Docker image
	docker push $(DOCKER_IMAGE):$(DOCKER_TAG)
	docker push $(DOCKER_IMAGE):latest

.PHONY: docker-up
docker-up: ## Start all services with Docker Compose
	docker compose up -d
	@echo "$(GREEN)Services started. API at http://localhost:8000$(NC)"

.PHONY: docker-down
docker-down: ## Stop all services
	docker compose down

.PHONY: docker-logs
docker-logs: ## Tail service logs
	docker compose logs -f --tail=100


# --- Deployment ---

.PHONY: deploy-staging
deploy-staging: check docker-push ## Deploy to staging
	kubectl set image deployment/$(APP_NAME) \
		$(APP_NAME)=$(DOCKER_IMAGE):$(DOCKER_TAG) \
		-n staging
	kubectl rollout status deployment/$(APP_NAME) -n staging

.PHONY: deploy-production
deploy-production: ## Deploy to production (requires confirmation)
	@echo "$(RED)Deploying $(VERSION) to PRODUCTION$(NC)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ]
	kubectl set image deployment/$(APP_NAME) \
		$(APP_NAME)=$(DOCKER_IMAGE):$(DOCKER_TAG) \
		-n production
	kubectl rollout status deployment/$(APP_NAME) -n production


# --- Cleanup ---

.PHONY: clean
clean: ## Remove build artifacts and caches
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	rm -rf dist build *.egg-info

.PHONY: clean-all
clean-all: clean ## Remove everything including venv
	rm -rf $(VENV)
```

Makefile patterns:
1. **Self-documenting** — `## Comment` after targets auto-generates `make help`
2. **`.PHONY`** — declare non-file targets to prevent conflicts with filenames
3. **Variable extraction** — `$(shell git ...)` for dynamic version/commit
4. **Dependency chain** — `deploy-staging: check docker-push` runs prerequisites
5. **Confirmation prompt** — `read -p "Are you sure?"` for destructive operations'''
    ),
    (
        "devops/shell-scripting",
        "Show shell scripting patterns: error handling, argument parsing, logging, and common utilities.",
        '''Shell scripting patterns:

```bash
#!/usr/bin/env bash
# deploy.sh — Production deployment script

# --- Strict mode ---
set -euo pipefail  # Exit on error, undefined vars, pipe failures
IFS=$\'\\n\\t\'       # Safer word splitting


# --- Constants and defaults ---

readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly SCRIPT_NAME="$(basename "$0")"
readonly LOG_FILE="/var/log/deploy.log"

# Colors
readonly RED=\'\\033[0;31m\'
readonly GREEN=\'\\033[0;32m\'
readonly YELLOW=\'\\033[0;33m\'
readonly NC=\'\\033[0m\'


# --- Logging ---

log() {
    local level="$1"; shift
    local msg="$*"
    local timestamp
    timestamp="$(date +\'%Y-%m-%d %H:%M:%S\')"
    echo -e "${timestamp} [${level}] ${msg}" | tee -a "$LOG_FILE"
}

info()  { log "INFO"  "${GREEN}$*${NC}"; }
warn()  { log "WARN"  "${YELLOW}$*${NC}"; }
error() { log "ERROR" "${RED}$*${NC}"; }

die() {
    error "$*"
    exit 1
}


# --- Cleanup on exit ---

cleanup() {
    local exit_code=$?
    if [[ $exit_code -ne 0 ]]; then
        error "Script failed with exit code $exit_code"
        # Rollback actions here
    fi
    # Remove temp files
    rm -f "${TMPFILE:-}"
    exit $exit_code
}
trap cleanup EXIT


# --- Argument parsing ---

usage() {
    cat <<EOF
Usage: ${SCRIPT_NAME} [OPTIONS] <environment>

Deploy application to specified environment.

Arguments:
    environment     Target environment (staging|production)

Options:
    -t, --tag TAG       Docker image tag (default: latest git tag)
    -n, --dry-run       Show what would be done without executing
    -f, --force         Skip confirmation prompts
    -v, --verbose       Enable verbose output
    -h, --help          Show this help message

Examples:
    ${SCRIPT_NAME} staging
    ${SCRIPT_NAME} -t v1.2.3 production
    ${SCRIPT_NAME} --dry-run production
EOF
}

# Defaults
TAG=""
DRY_RUN=false
FORCE=false
VERBOSE=false
ENVIRONMENT=""

parse_args() {
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -t|--tag)
                TAG="$2"
                shift 2
                ;;
            -n|--dry-run)
                DRY_RUN=true
                shift
                ;;
            -f|--force)
                FORCE=true
                shift
                ;;
            -v|--verbose)
                VERBOSE=true
                shift
                ;;
            -h|--help)
                usage
                exit 0
                ;;
            -*)
                die "Unknown option: $1"
                ;;
            *)
                ENVIRONMENT="$1"
                shift
                ;;
        esac
    done

    # Validate required arguments
    [[ -z "$ENVIRONMENT" ]] && die "Environment is required. See --help"
    [[ "$ENVIRONMENT" =~ ^(staging|production)$ ]] || \
        die "Invalid environment: $ENVIRONMENT (must be staging or production)"

    # Default tag from git
    TAG="${TAG:-$(git describe --tags --always 2>/dev/null || echo "latest")}"
}


# --- Utility functions ---

command_exists() {
    command -v "$1" &>/dev/null
}

require_commands() {
    for cmd in "$@"; do
        command_exists "$cmd" || die "Required command not found: $cmd"
    done
}

confirm() {
    local msg="${1:-Are you sure?}"
    if [[ "$FORCE" == true ]]; then
        return 0
    fi
    read -rp "${msg} [y/N] " response
    [[ "$response" =~ ^[Yy]$ ]]
}

run() {
    if [[ "$DRY_RUN" == true ]]; then
        info "[DRY RUN] $*"
    else
        [[ "$VERBOSE" == true ]] && info "Running: $*"
        "$@"
    fi
}

wait_for() {
    local url="$1"
    local timeout="${2:-60}"
    local start
    start="$(date +%s)"

    info "Waiting for $url ..."
    while ! curl -sf "$url" &>/dev/null; do
        if (( $(date +%s) - start > timeout )); then
            die "Timeout waiting for $url"
        fi
        sleep 2
    done
    info "$url is up!"
}


# --- Main deployment ---

deploy() {
    info "Deploying $TAG to $ENVIRONMENT"

    # Pre-checks
    require_commands docker kubectl curl

    if [[ "$ENVIRONMENT" == "production" ]]; then
        confirm "Deploy $TAG to PRODUCTION?" || die "Aborted"
    fi

    # Deploy
    run kubectl set image "deployment/myapp" \
        "myapp=registry.example.com/myapp:$TAG" \
        -n "$ENVIRONMENT"

    run kubectl rollout status "deployment/myapp" \
        -n "$ENVIRONMENT" --timeout=300s

    # Health check
    local url="https://${ENVIRONMENT}.example.com/health"
    wait_for "$url" 120

    info "Deployment of $TAG to $ENVIRONMENT complete!"
}


# --- Entry point ---

main() {
    parse_args "$@"
    deploy
}

main "$@"
```

Shell scripting patterns:
1. **`set -euo pipefail`** — strict mode catches errors, undefined vars, pipe failures
2. **Trap cleanup** — `trap cleanup EXIT` runs on any exit (success or failure)
3. **Argument parsing** — `while/case` loop handles long and short options
4. **`run()` wrapper** — supports dry-run mode and verbose logging
5. **`die()` function** — log error and exit with non-zero code'''
    ),
]
"""
