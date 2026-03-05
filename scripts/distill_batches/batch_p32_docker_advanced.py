"""Docker advanced — multi-stage builds, compose patterns, optimization, and security."""

PAIRS = [
    (
        "devops/docker-multistage",
        "Show Docker multi-stage build patterns: optimized Python images, layer caching, security hardening, and production-ready Dockerfiles.",
        '''Production Docker patterns for Python applications:

```dockerfile
# --- Multi-stage Python build ---

# Stage 1: Build dependencies
FROM python:3.12-slim AS builder

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages into a virtual env
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy and install requirements first (layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Production image
FROM python:3.12-slim AS production

# Install only runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual env from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Non-root user
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app
WORKDIR /app

# Copy application code
COPY --chown=app:app . .

# Security: drop all capabilities
USER app

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

CMD ["gunicorn", "app:create_app()", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--access-logfile", "-"]
```

```dockerfile
# --- Optimized Node.js build ---

FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --only=production

FROM node:20-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine AS production
WORKDIR /app
# Copy only production deps and build output
COPY --from=deps /app/node_modules ./node_modules
COPY --from=build /app/dist ./dist
COPY --from=build /app/package.json .

RUN addgroup -g 1001 -S app && adduser -S app -u 1001
USER app

EXPOSE 3000
CMD ["node", "dist/server.js"]
```

```dockerfile
# --- Layer caching best practices ---

# BAD: Invalidates cache on ANY code change
COPY . .
RUN pip install -r requirements.txt

# GOOD: Dependencies cached separately from code
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

# BETTER: Use BuildKit cache mounts
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Build args for cache busting only when needed
ARG DEPS_HASH
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt
```

Optimization checklist:
1. **Multi-stage** — build tools stay out of production image
2. **Slim/Alpine base** — smaller attack surface and image size
3. **Layer ordering** — dependencies before code (cache deps layer)
4. **Non-root user** — never run as root in production
5. **BuildKit cache mounts** — persist pip/npm cache across builds
6. **No dev dependencies** — only production requirements in final image
7. **HEALTHCHECK** — enable orchestrator health monitoring'''
    ),
    (
        "devops/docker-compose-patterns",
        "Show Docker Compose patterns for development and production: service orchestration, networking, volumes, health checks, and environment management.",
        '''Docker Compose patterns for local development and production:

```yaml
# docker-compose.yml — Development environment
services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
      target: development  # Multi-stage target
    volumes:
      - .:/app           # Live code reloading
      - /app/node_modules # Prevent overwrite
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://app:secret@db:5432/appdb
      - REDIS_URL=redis://redis:6379/0
      - DEBUG=true
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 30s

  worker:
    build:
      context: .
      target: development
    command: celery -A app.celery worker -l info
    volumes:
      - .:/app
    environment:
      - DATABASE_URL=postgresql://app:secret@db:5432/appdb
      - REDIS_URL=redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy

  db:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./scripts/init.sql:/docker-entrypoint-initdb.d/init.sql
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: appdb
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U app -d appdb"]
      interval: 5s
      timeout: 3s
      retries: 10

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    ports:
      - "6379:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
    volumes:
      - redisdata:/data

  # Development tools
  mailhog:
    image: mailhog/mailhog
    ports:
      - "1025:1025"  # SMTP
      - "8025:8025"  # Web UI

volumes:
  pgdata:
  redisdata:

# Named network with custom subnet
networks:
  default:
    driver: bridge
```

```yaml
# docker-compose.override.yml — auto-loaded, dev-specific
services:
  api:
    command: uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
    environment:
      - LOG_LEVEL=debug
```

```yaml
# docker-compose.prod.yml — production overrides
# Usage: docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
services:
  api:
    build:
      target: production
    volumes: []  # No bind mounts in prod
    environment:
      - DEBUG=false
    deploy:
      replicas: 3
      resources:
        limits:
          cpus: "1.0"
          memory: 512M
        reservations:
          cpus: "0.25"
          memory: 256M
      restart_policy:
        condition: on-failure
        delay: 5s
        max_attempts: 3

  db:
    ports: []  # Don't expose in prod
    environment:
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password

secrets:
  db_password:
    file: ./secrets/db_password.txt
```

```bash
# Common commands
docker compose up -d                          # Start all services
docker compose logs -f api                    # Follow API logs
docker compose exec db psql -U app appdb      # Connect to DB
docker compose down -v                        # Stop + remove volumes
docker compose build --no-cache api           # Rebuild without cache
docker compose run --rm api pytest            # Run tests in fresh container
docker compose ps --format json               # Service status as JSON
```

Patterns:
1. **Override files** — `docker-compose.yml` (base) + `.override.yml` (dev) + `.prod.yml` (prod)
2. **Health checks** — `depends_on: condition: service_healthy` for startup ordering
3. **Named volumes** — persist data; anonymous volumes prevent overwrites
4. **Secrets** — use file-based secrets, not environment variables in production
5. **Resource limits** — prevent containers from consuming all host resources'''
    ),
    (
        "devops/docker-security",
        "Show Docker security best practices: image scanning, minimal images, secrets management, and runtime security.",
        '''Docker security hardening for production:

```dockerfile
# --- Minimal, secure base image ---
# Use distroless for smallest attack surface
FROM python:3.12-slim AS builder
WORKDIR /build
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/deps -r requirements.txt
COPY . .

FROM gcr.io/distroless/python3-debian12
COPY --from=builder /deps /deps
COPY --from=builder /build /app
WORKDIR /app
ENV PYTHONPATH=/deps
CMD ["main.py"]

# No shell, no package manager, no OS utilities = tiny attack surface
```

```dockerfile
# --- Security hardening checklist ---

# 1. Pin exact versions (not :latest)
FROM python:3.12.3-slim@sha256:abc123...

# 2. Don't run as root
RUN groupadd -r app && useradd -r -g app app
USER app

# 3. Drop capabilities
# In docker run: --cap-drop=ALL --cap-add=NET_BIND_SERVICE

# 4. Read-only filesystem
# In docker run: --read-only --tmpfs /tmp

# 5. No new privileges
# In docker run: --security-opt=no-new-privileges

# 6. Don't store secrets in image
# BAD:
ENV API_KEY=secret123
COPY .env /app/.env

# GOOD: Use runtime secrets
# docker run -e API_KEY --secret id=api_key,src=api_key.txt
```

```python
# --- Image scanning in CI/CD ---
# .github/workflows/docker.yml

SCAN_WORKFLOW = """
name: Docker Build & Scan
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Build image
        run: docker build -t app:${{ github.sha }} .

      - name: Run Trivy vulnerability scanner
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: app:${{ github.sha }}
          format: 'sarif'
          output: 'trivy-results.sarif'
          severity: 'CRITICAL,HIGH'
          exit-code: '1'  # Fail on critical/high

      - name: Run Dockle (best practices)
        uses: goodwithtech/dockle-action@main
        with:
          image: app:${{ github.sha }}
          exit-code: '1'
          exit-level: warn
"""
```

```yaml
# --- Docker runtime security (compose) ---
services:
  api:
    image: app:latest
    read_only: true
    tmpfs:
      - /tmp:size=100M
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE
    ulimits:
      nofile:
        soft: 65536
        hard: 65536
      nproc:
        soft: 4096
        hard: 4096
    # Limit syscalls
    # seccomp profile for additional hardening
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 1G
          pids: 256  # Prevent fork bombs
```

Security layers:
1. **Build time** — minimal base, pinned versions, no secrets in layers, `.dockerignore`
2. **Image scanning** — Trivy/Snyk for CVEs, Dockle for best practices
3. **Runtime** — non-root, read-only fs, dropped capabilities, resource limits
4. **Secrets** — Docker secrets or external vault, never ENV vars in images
5. **Network** — internal networks, no unnecessary port exposure'''
    ),
]
"""
