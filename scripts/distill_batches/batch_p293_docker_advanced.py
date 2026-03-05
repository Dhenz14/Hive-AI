"""Advanced Docker — multi-stage builds, security, compose, optimization."""

PAIRS = [
    (
        "devops/docker-multistage",
        "Show Docker multi-stage builds: minimal production images, build caching, security scanning, and distroless base images.",
        '''Docker multi-stage builds and optimization:

```dockerfile
# ---- Stage 1: Dependencies ----
FROM python:3.12-slim AS deps
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN pip install uv && uv sync --frozen --no-dev

# ---- Stage 2: Build ----
FROM python:3.12-slim AS build
WORKDIR /app
COPY --from=deps /app/.venv .venv
COPY src/ src/
COPY alembic/ alembic/
# Run any build steps (compile, collect static, etc.)
RUN .venv/bin/python -m compileall src/

# ---- Stage 3: Production (minimal) ----
FROM python:3.12-slim AS production
# Security: non-root user
RUN groupadd -r app && useradd -r -g app -d /app -s /sbin/nologin app
WORKDIR /app

# Only copy what's needed
COPY --from=build /app/.venv .venv
COPY --from=build /app/src src/
COPY --from=build /app/alembic alembic/

# Security hardening
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && rm -rf /var/lib/apt/lists/*

USER app
ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')"
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

```yaml
# docker-compose.yml for development
services:
  app:
    build:
      context: .
      target: build  # Use build stage for dev (has all tools)
      cache_from:
        - type=registry,ref=myregistry/myapp:cache
    volumes:
      - ./src:/app/src  # Hot reload
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://postgres:postgres@db:5432/myapp
      - REDIS_URL=redis://redis:6379
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    command: uvicorn src.main:app --reload --host 0.0.0.0

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: myapp
      POSTGRES_PASSWORD: postgres
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru

volumes:
  pgdata:
```

Key patterns:
1. **Multi-stage** — separate dependency, build, and production stages; final image is minimal
2. **Non-root user** — create app user; never run as root in production
3. **Layer caching** — copy dependency files first; source code changes don't rebuild deps
4. **Healthcheck** — container-level health verification; orchestrator can restart unhealthy containers
5. **Dev vs prod** — compose targets build stage with hot reload; prod uses minimal final stage'''
    ),
    (
        "devops/docker-security",
        "Show Docker security best practices: image scanning, secrets management, read-only filesystems, and resource limits.",
        '''Docker security hardening:

```dockerfile
# Use specific digest, not just tag (prevents supply chain attacks)
FROM python:3.12-slim@sha256:abc123... AS base

# Don't install unnecessary packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 && \
    apt-get purge -y --auto-remove && \
    rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Copy only needed files (use .dockerignore too)
COPY --chown=app:app src/ /app/src/

# Read-only filesystem
# Set at runtime: docker run --read-only --tmpfs /tmp
```

```yaml
# Secure compose configuration
services:
  app:
    image: myapp:latest
    read_only: true           # Read-only root filesystem
    tmpfs:
      - /tmp                  # Writable temp directory
    security_opt:
      - no-new-privileges     # Prevent privilege escalation
    cap_drop:
      - ALL                   # Drop all Linux capabilities
    cap_add:
      - NET_BIND_SERVICE      # Only add what's needed
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 1G
        reservations:
          cpus: "0.5"
          memory: 256M
    secrets:
      - db_password
      - api_key
    networks:
      - frontend
      - backend

  # Don't expose DB to frontend network
  db:
    networks:
      - backend

networks:
  frontend:
  backend:
    internal: true  # No external access

secrets:
  db_password:
    file: ./secrets/db_password.txt
  api_key:
    external: true  # Managed by orchestrator
```

```python
# Image scanning in CI
# Trivy scan: trivy image --severity HIGH,CRITICAL myapp:latest

# Docker Scout (built-in)
# docker scout cves myapp:latest
# docker scout recommendations myapp:latest

# Runtime security with Falco rules
rules = """
- rule: Write below /etc
  desc: Detect writes to /etc directory
  condition: >
    open_write and container and fd.directory = /etc
  output: "File below /etc opened for writing (file=%fd.name)"
  priority: ERROR
"""
```

Key patterns:
1. **Pinned digests** — `@sha256:...` prevents tag mutation attacks
2. **Read-only filesystem** — prevents runtime file tampering; use tmpfs for writable paths
3. **Capability dropping** — `cap_drop: ALL` + selective `cap_add`; principle of least privilege
4. **Network segmentation** — internal networks isolate backend services from external access
5. **Resource limits** — prevent container from consuming all host resources; OOM protection'''
    ),
]
"""
