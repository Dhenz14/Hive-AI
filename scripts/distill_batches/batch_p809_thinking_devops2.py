"""Phase 1H: Foundation Thinking — Data Modeling & DevOps (Part 6)

Docker optimization: layer caching, multi-stage builds, image size reduction,
and production-ready container patterns.
"""

PAIRS = [
    (
        "thinking/devops-docker-layer-cache",
        r'''Our Docker build takes 8 minutes because it reinstalls all Python dependencies every time, even when only application code changes:

FROM python:3.12
WORKDIR /app
COPY . .
RUN pip install -r requirements.txt
RUN python manage.py collectstatic --noinput
CMD ["gunicorn", "myapp.wsgi:application", "-b", "0.0.0.0:8000"]

The requirements.txt hasn't changed in weeks, but pip install runs on every build. How do we fix this?''',
        r'''<think>
The problem is Docker layer caching and the order of COPY commands.

**How Docker layer caching works:**

Each Dockerfile instruction creates a layer. Docker caches layers and reuses them if:
1. The instruction hasn't changed
2. The files being copied haven't changed
3. All previous layers are also cache hits

The CRITICAL rule: once a layer is invalidated, ALL subsequent layers are also invalidated.

**What's happening in their Dockerfile:**

```
COPY . .              ← Copies ALL files. ANY file change invalidates this layer
RUN pip install ...   ← This layer depends on the COPY above, so it's also invalidated
```

Even if only `views.py` changes, `COPY . .` invalidates, which forces `pip install` to re-run.

**The fix: Copy dependency files FIRST, install, THEN copy app code**

```dockerfile
COPY requirements.txt .    ← Only invalidated when requirements.txt changes
RUN pip install ...        ← Cached unless requirements.txt changed
COPY . .                   ← App code changes only invalidate this and below
```

Now `pip install` only runs when `requirements.txt` changes. App code changes skip straight to `COPY . .`.

**Additional optimizations:**

1. Use `--no-cache-dir` with pip to avoid storing wheel cache in the image
2. Use a `.dockerignore` to exclude unnecessary files from COPY
3. Pin the base image digest for reproducible builds
4. Use multi-stage build to exclude build tools from the final image

Let me also address `collectstatic` — it should be after `COPY . .` since it needs the app code, but it's a fast operation so that's fine.
</think>

### Root cause: `COPY . .` before `pip install` invalidates the dependency cache

Docker invalidates ALL layers after the first changed layer. Copying all files before installing dependencies means ANY code change triggers a full reinstall.

### Fixed Dockerfile with optimal layer ordering

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Layer 1: System dependencies (rarely changes)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Layer 2: Python dependencies (changes when requirements.txt changes)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Layer 3: Application code (changes frequently)
COPY . .

# Layer 4: Static files (depends on app code)
RUN python manage.py collectstatic --noinput

# Non-root user for security
RUN adduser --disabled-password --no-create-home appuser
USER appuser

EXPOSE 8000
CMD ["gunicorn", "myapp.wsgi:application", "-b", "0.0.0.0:8000", "--workers", "4"]
```

### Add .dockerignore to speed up COPY

```
# .dockerignore
.git
.gitignore
__pycache__
*.pyc
.env
.venv
node_modules
docker-compose*.yml
Dockerfile*
README.md
docs/
tests/
.pytest_cache
.coverage
*.egg-info
```

### Layer cache behavior after fix

```
Code change (views.py):
  COPY requirements.txt .     → CACHED (requirements.txt unchanged)
  RUN pip install ...          → CACHED (depends on requirements.txt only)
  COPY . .                     → REBUILT (code changed)
  RUN collectstatic            → REBUILT (depends on code)
  Total: ~30 seconds (was 8 minutes)

Dependency change (requirements.txt):
  COPY requirements.txt .     → REBUILT (file changed)
  RUN pip install ...          → REBUILT (dependency changed)
  COPY . .                     → REBUILT (layer above changed)
  Total: ~8 minutes (unavoidable, dependencies changed)

No changes:
  All layers                   → CACHED
  Total: ~2 seconds
```

### Advanced: Split requirements for better caching

```dockerfile
# If you have stable base deps and frequently-changing project deps:
COPY requirements-base.txt .
RUN pip install --no-cache-dir -r requirements-base.txt

COPY requirements-dev.txt .
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY . .
```

This way, adding a small dev dependency only re-installs dev deps, not the entire stack.'''
    ),
    (
        "thinking/devops-docker-multistage",
        r'''Our Go application's Docker image is 1.2GB. The app binary itself is only 15MB. Here's the Dockerfile:

FROM golang:1.22
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 go build -o server ./cmd/server
EXPOSE 8080
CMD ["./server"]

How do we reduce the image size? We also have a React frontend that gets built and served by the Go server.''',
        r'''<think>
The image is 1.2GB because `golang:1.22` base image is ~800MB (includes the full Go toolchain, gcc, etc.) and `go mod download` pulls in all dependencies. The final binary is only 15MB but the image includes everything needed to BUILD, not just RUN.

**Multi-stage build:** Use one stage to build, another to run. The final image only contains the binary.

**For the Go binary:**
```dockerfile
# Build stage
FROM golang:1.22 AS builder
...
RUN CGO_ENABLED=0 go build -o server ./cmd/server

# Run stage
FROM scratch  # or alpine:3.19
COPY --from=builder /app/server /server
CMD ["/server"]
```

`scratch` is an empty image — the final image is literally just the binary (~15MB). But `scratch` has no shell, no CA certificates, no timezone data. If the app makes HTTPS calls or uses time zones, you need those.

Options for the run stage:
- `scratch`: ~15MB, no shell, no debug tools. For pure Go binaries.
- `alpine:3.19`: ~7MB base + 15MB binary = ~22MB. Has shell, package manager.
- `distroless/static`: ~2MB base, no shell but has CA certs and tzdata. Google's recommended approach.
- `debian:bookworm-slim`: ~80MB base. When you need glibc.

**For the React frontend:**
Build with Node, output static files, copy to the Go binary's static directory.

```dockerfile
FROM node:20 AS frontend
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ .
RUN npm run build  # Outputs to /frontend/dist

FROM golang:1.22 AS backend
...
COPY --from=frontend /frontend/dist /app/static
RUN CGO_ENABLED=0 go build -o server ./cmd/server

FROM gcr.io/distroless/static
COPY --from=backend /app/server /server
COPY --from=backend /app/static /static
CMD ["/server"]
```

**Additional optimizations:**
1. `CGO_ENABLED=0` produces a statically linked binary (no glibc dependency)
2. `-ldflags="-s -w"` strips debug info, reducing binary by ~30%
3. Use `.dockerignore` to exclude test files, docs, etc.
</think>

### Why it's 1.2GB: The build tools are in the final image

The `golang:1.22` base image includes the Go compiler, gcc, git, and all build dependencies. You only need the 15MB binary to run.

### Optimized multi-stage Dockerfile

```dockerfile
# ==========================================
# Stage 1: Build React frontend
# ==========================================
FROM node:20-alpine AS frontend

WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --production=false

COPY frontend/ .
RUN npm run build
# Output: /frontend/dist/ (static HTML/JS/CSS)

# ==========================================
# Stage 2: Build Go backend
# ==========================================
FROM golang:1.22-alpine AS backend

WORKDIR /app

# Cache Go modules
COPY go.mod go.sum ./
RUN go mod download

# Copy source and frontend assets
COPY . .
COPY --from=frontend /frontend/dist ./static/

# Build statically-linked binary with stripped debug info
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 \
    go build -ldflags="-s -w" -o server ./cmd/server

# ==========================================
# Stage 3: Minimal production image
# ==========================================
FROM gcr.io/distroless/static-debian12

# Copy only the binary and static files
COPY --from=backend /app/server /server
COPY --from=backend /app/static /static

EXPOSE 8080
USER nonroot:nonroot
ENTRYPOINT ["/server"]
```

### Image size comparison

```
golang:1.22 (original):           1.2 GB
golang:1.22-alpine (build only):  ~300 MB (not used in final)
Multi-stage with alpine:           ~22 MB
Multi-stage with distroless:       ~17 MB
Multi-stage with scratch:          ~15 MB
```

### Choosing the right base for the final stage

```dockerfile
# Option A: scratch (smallest, no shell, no debugging)
FROM scratch
COPY --from=backend /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=backend /usr/share/zoneinfo /usr/share/zoneinfo
COPY --from=backend /app/server /server
# Must include CA certs if app makes HTTPS calls
# Must include zoneinfo if app uses time.LoadLocation()

# Option B: distroless (recommended — includes CA certs, tzdata, no shell)
FROM gcr.io/distroless/static-debian12
COPY --from=backend /app/server /server
# Has CA certs, tzdata, /etc/passwd. No shell, no package manager.

# Option C: alpine (when you need a shell for debugging)
FROM alpine:3.19
RUN apk --no-cache add ca-certificates tzdata
COPY --from=backend /app/server /server
```

### Build cache optimization for CI/CD

```dockerfile
# For CI where the Docker cache isn't persistent, use BuildKit cache mounts:

FROM golang:1.22-alpine AS backend
WORKDIR /app

COPY go.mod go.sum ./

# Cache Go modules in a BuildKit mount (survives across builds)
RUN --mount=type=cache,target=/go/pkg/mod \
    go mod download

COPY . .

# Cache the build cache
RUN --mount=type=cache,target=/go/pkg/mod \
    --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -ldflags="-s -w" -o server ./cmd/server
```

```bash
# Enable BuildKit for cache mounts
DOCKER_BUILDKIT=1 docker build -t myapp .
```

### Security scanning the final image

```bash
# Scan for vulnerabilities (fewer packages = fewer vulns)
docker scout cves myapp:latest

# Results comparison:
# golang:1.22 base:     142 vulnerabilities (87 in OS packages)
# distroless base:        3 vulnerabilities (all low severity)
# scratch base:           0 vulnerabilities
```'''
    ),
    (
        "thinking/devops-docker-python-optimization",
        r'''Our Python ML service Docker image is 4.2GB and takes 15 minutes to build. It includes PyTorch, transformers, and a fine-tuned model:

FROM python:3.12
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
COPY models/my-model/ /app/models/my-model/
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0"]

requirements.txt includes torch, transformers, numpy, scipy, fastapi, uvicorn. The model directory is 1.5GB. How do we reduce image size and build time?''',
        r'''<think>
Let me analyze where the 4.2GB comes from:

- `python:3.12` base: ~900MB (includes build tools, gcc, etc.)
- PyTorch: ~800MB-2GB (CPU version is ~800MB, CUDA is ~2GB)
- transformers + dependencies: ~200MB
- numpy/scipy: ~100MB
- Model files: 1.5GB
- Total: ~3.5-4.5GB depending on PyTorch variant

**Optimization strategies:**

1. **Use slim base image**: `python:3.12-slim` saves ~700MB vs full `python:3.12`

2. **CPU-only PyTorch if no GPU**: Default pip install pulls CUDA-enabled PyTorch even if you don't use GPU.
   - `torch` default: ~2GB (includes CUDA libraries)
   - `torch` CPU only: ~200MB
   - Install from CPU index: `pip install torch --index-url https://download.pytorch.org/whl/cpu`

3. **Multi-stage build**: Install build dependencies in one stage, copy only runtime files to final stage

4. **Model as a separate layer**: Copy the model file BEFORE application code so it's cached (models change less often than code)

5. **Model download at runtime**: Don't include the model in the image at all — download from S3/GCS on startup. This makes the image smaller and model updates don't require rebuilds.

6. **Pip optimizations**:
   - `--no-cache-dir`: Don't store pip cache in image
   - `--no-compile`: Don't generate .pyc files during install (saves ~5% space)
   - Compile only needed packages

Let me calculate the potential savings:

Current: 4.2GB
- Slim base: -700MB → 3.5GB
- CPU-only PyTorch: -1.2GB → 2.3GB
- Externalize model: -1.5GB → 0.8GB
- Multi-stage + cleanup: -100MB → 0.7GB

From 4.2GB to ~0.7GB is an 83% reduction.

Build time:
- Layer ordering (requirements.txt first) fixes the cache issue
- BuildKit cache mounts for pip cache make repeated builds faster
- If model is external, that's 1.5GB less to COPY
</think>

### Size breakdown of the 4.2GB image

```
python:3.12 base image:     ~900 MB
PyTorch (default = CUDA):   ~1,800 MB  ← biggest offender
transformers + deps:        ~200 MB
Model files:                ~1,500 MB
Application code:           ~10 MB
pip cache (left in image):  ~300 MB
```

### Optimized Dockerfile (4.2GB to ~700MB)

```dockerfile
# ==========================================
# Stage 1: Build dependencies
# ==========================================
FROM python:3.12-slim AS builder

WORKDIR /app

# Install build dependencies needed for numpy/scipy compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# KEY: Install CPU-only PyTorch (200MB vs 1.8GB)
RUN pip install --no-cache-dir \
    --target=/app/deps \
    torch --index-url https://download.pytorch.org/whl/cpu

# Install remaining dependencies
RUN pip install --no-cache-dir \
    --target=/app/deps \
    -r requirements.txt

# ==========================================
# Stage 2: Runtime image
# ==========================================
FROM python:3.12-slim

WORKDIR /app

# Copy only the installed packages (no build tools)
COPY --from=builder /app/deps /usr/local/lib/python3.12/site-packages/

# Copy application code
COPY app/ ./app/
COPY config/ ./config/

# Model: download at startup instead of baking into image
# (see model_loader.py below)
ENV MODEL_PATH=/app/models/my-model
ENV MODEL_SOURCE=s3://my-bucket/models/my-model-v3/

# Non-root user
RUN useradd --no-create-home appuser
USER appuser

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### requirements.txt optimization

```
# requirements.txt — pin versions, use CPU-only torch
--extra-index-url https://download.pytorch.org/whl/cpu
torch==2.2.0+cpu
transformers==4.38.0
tokenizers==0.15.0
numpy==1.26.4
fastapi==0.110.0
uvicorn[standard]==0.27.0
# Don't install scipy unless actually used — it's 100MB
# Don't install jupyter, pytest, etc. in production image
```

### Model loading at startup (externalize from image)

```python
import os
import boto3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def ensure_model_loaded():
    """Download model from S3 if not already cached locally."""
    model_path = Path(os.environ.get("MODEL_PATH", "/app/models/my-model"))
    model_source = os.environ.get("MODEL_SOURCE", "")

    if model_path.exists() and any(model_path.iterdir()):
        logger.info(f"Model already loaded at {model_path}")
        return model_path

    if not model_source:
        raise RuntimeError("MODEL_SOURCE not set and model not found locally")

    logger.info(f"Downloading model from {model_source}...")
    model_path.mkdir(parents=True, exist_ok=True)

    s3 = boto3.client("s3")
    bucket, prefix = model_source.replace("s3://", "").split("/", 1)

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            local_file = model_path / key[len(prefix):]
            local_file.parent.mkdir(parents=True, exist_ok=True)
            s3.download_file(bucket, key, str(local_file))

    logger.info(f"Model downloaded to {model_path}")
    return model_path
```

### If you MUST include the model in the image

```dockerfile
# Put model copy BEFORE app code (model changes less often)
COPY models/my-model/ /app/models/my-model/
# This 1.5GB layer is cached unless the model changes

COPY app/ ./app/
# App code changes don't re-copy the model
```

### Size comparison

```
Original:                          4,200 MB
+ slim base:                       3,300 MB  (-900 MB)
+ CPU-only PyTorch:                1,500 MB  (-1,800 MB)
+ multi-stage (no build tools):    1,400 MB  (-100 MB)
+ externalize model:                 700 MB  (-700 MB via S3)
+ no pip cache:                      650 MB  (-50 MB)

Final: ~650 MB (85% reduction)
```

### Build time comparison

```
Original (no cache):               15 min
+ layer ordering:                   2 min (code change only)
+ BuildKit cache mount:            90 sec (code change only)
+ externalized model:              60 sec (no 1.5GB COPY)
```'''
    ),
    (
        "thinking/devops-docker-security-hardening",
        r'''Our security audit flagged several issues with our Docker containers:

1. Running as root
2. Base image has 142 known CVEs
3. Secrets (API keys) passed as build args visible in image history
4. No resource limits
5. Writable filesystem

How do we harden our containers for production?''',
        r'''<think>
Let me address each security issue systematically.

**1. Running as root:**
By default, Docker containers run as root (UID 0). If an attacker escapes the container, they're root on the host. Fix: create and use a non-root user.

**2. Base image CVEs:**
Large base images (ubuntu, python, node) include hundreds of packages, many with vulnerabilities. Fix: use minimal base images (alpine, distroless, slim variants) and scan regularly.

**3. Secrets in build args:**
`docker build --build-arg API_KEY=xxx` is stored in the image's layer history. Anyone with access to the image can see it with `docker history`. Fix: use Docker secrets, mount secrets at build time with BuildKit, or inject at runtime via environment variables/secret managers.

**4. No resource limits:**
Without limits, a single container can consume all CPU/memory, causing denial of service. Fix: set resource limits in docker-compose or Kubernetes.

**5. Writable filesystem:**
If an attacker compromises the app, they can modify binaries or drop malware. Fix: read-only root filesystem with specific writable tmpfs mounts for temp files.

Let me provide a comprehensive hardened Dockerfile and compose config.
</think>

### Hardened Dockerfile

```dockerfile
# Use a specific digest (not just tag) for reproducibility
FROM python:3.12-slim@sha256:abc123... AS builder

WORKDIR /app

# Install dependencies in build stage
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/app/deps -r requirements.txt

# ---- Production stage ----
FROM python:3.12-slim@sha256:abc123...

WORKDIR /app

# Fix #1: Non-root user (created BEFORE copying app files)
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --no-create-home --shell /usr/sbin/nologin appuser

# Copy dependencies and application
COPY --from=builder /app/deps /usr/local/lib/python3.12/site-packages/
COPY --chown=appuser:appgroup . .

# Fix #2: Remove unnecessary packages and clean up
RUN apt-get update && apt-get upgrade -y && \
    apt-get purge -y --auto-remove && \
    rm -rf /var/lib/apt/lists/* /tmp/* /root/.cache

# Fix #3: Never use build args for secrets (see docker-compose below)
# Secrets are injected at RUNTIME, not build time

# Switch to non-root user
USER appuser:appgroup

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

EXPOSE 8000
ENTRYPOINT ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Hardened docker-compose.yml

```yaml
version: "3.8"

services:
  api:
    image: myapp:latest
    build:
      context: .
      dockerfile: Dockerfile

    # Fix #4: Resource limits
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 1G
        reservations:
          cpus: "0.5"
          memory: 256M

    # Fix #5: Read-only filesystem
    read_only: true
    tmpfs:
      - /tmp:size=100M,noexec,nosuid
      - /app/tmp:size=50M,noexec,nosuid

    # Fix #3: Secrets via Docker secrets (not env vars or build args)
    secrets:
      - db_password
      - api_key
    environment:
      - DB_PASSWORD_FILE=/run/secrets/db_password
      - API_KEY_FILE=/run/secrets/api_key
      - DB_HOST=postgres

    # Security options
    security_opt:
      - no-new-privileges:true
    cap_drop:
      - ALL
    cap_add:
      - NET_BIND_SERVICE  # Only if binding to port < 1024

    # Networking
    ports:
      - "8000:8000"
    networks:
      - internal

    # Logging
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

secrets:
  db_password:
    file: ./secrets/db_password.txt
  api_key:
    file: ./secrets/api_key.txt

networks:
  internal:
    driver: bridge
```

### Application code: Read secrets from files

```python
import os
from pathlib import Path

def get_secret(name: str) -> str:
    """Read secret from Docker secret file or env var."""
    # Docker secrets are mounted as files
    secret_file = os.environ.get(f"{name}_FILE")
    if secret_file and Path(secret_file).exists():
        return Path(secret_file).read_text().strip()
    # Fallback to env var (for local dev)
    value = os.environ.get(name)
    if value:
        return value
    raise ValueError(f"Secret {name} not found in file or environment")

DB_PASSWORD = get_secret("DB_PASSWORD")
API_KEY = get_secret("API_KEY")
```

### Fix #3: BuildKit secrets for build-time secrets

```dockerfile
# If you need a secret during BUILD (e.g., private PyPI token):
# NEVER use --build-arg (visible in docker history)

# Instead, use BuildKit secret mounts:
RUN --mount=type=secret,id=pip_token \
    PIP_INDEX_URL="https://$(cat /run/secrets/pip_token)@pypi.example.com/simple/" \
    pip install --no-cache-dir -r requirements.txt
```

```bash
# Build with the secret (never stored in the image)
DOCKER_BUILDKIT=1 docker build \
    --secret id=pip_token,src=.pip_token \
    -t myapp .
```

### Image scanning in CI/CD

```yaml
# GitHub Actions: scan image before push
- name: Scan Docker image for vulnerabilities
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: myapp:${{ github.sha }}
    format: table
    exit-code: 1
    severity: CRITICAL,HIGH
    # Fail the build if CRITICAL or HIGH CVEs are found
```

### Security checklist

| Issue | Fix | Docker directive |
|-------|-----|-----------------|
| Running as root | Non-root USER | `USER appuser` |
| Base image CVEs | Minimal base + scan | `FROM python:3.12-slim` + Trivy |
| Secrets in history | Runtime secrets | `--mount=type=secret` / Docker secrets |
| No resource limits | CPU/memory limits | `deploy.resources.limits` |
| Writable filesystem | Read-only root | `read_only: true` + `tmpfs` |
| Privilege escalation | Drop capabilities | `cap_drop: ALL` + `no-new-privileges` |
| Unpinned base | Pin by digest | `FROM image@sha256:...` |'''
    ),
    (
        "thinking/devops-docker-compose-production",
        r'''We're running a Django app with Celery workers, PostgreSQL, Redis, and Nginx in docker-compose. Our development compose file works but we need to make it production-ready:

version: "3"
services:
  web:
    build: .
    command: python manage.py runserver 0.0.0.0:8000
    volumes:
      - .:/app
    ports:
      - "8000:8000"
    depends_on:
      - db
      - redis
  db:
    image: postgres
    environment:
      POSTGRES_PASSWORD: password123
  redis:
    image: redis
  celery:
    build: .
    command: celery -A myapp worker -l info
    volumes:
      - .:/app

What are the production problems and how do we fix them?''',
        r'''<think>
Let me catalog all the production issues:

1. **`runserver` in production**: Django's dev server is single-threaded, not for production. Use gunicorn.

2. **Volume mount `.:/app`**: Mounts host code into container — for dev hot-reload only. In production, code should be baked into the image.

3. **No Nginx**: Direct Django exposure. Need a reverse proxy for static files, SSL termination, request buffering.

4. **`image: postgres` without version tag**: Will pull `latest`, which can break on major upgrades. Pin the version.

5. **`POSTGRES_PASSWORD: password123`**: Hardcoded password in compose file. Use secrets or env files.

6. **No health checks**: compose doesn't know if services are actually ready.

7. **`depends_on` without health check**: Services start in order but don't wait for readiness. Django might start before PostgreSQL is accepting connections.

8. **No resource limits**: Any service can consume all resources.

9. **No restart policy**: If a service crashes, it stays down.

10. **No logging configuration**: Default Docker logging can fill disk.

11. **Redis without persistence config**: Data loss on restart.

12. **No SSL/TLS**: No HTTPS.

13. **No backup strategy for PostgreSQL data**.

14. **Celery without concurrency, autoscale, or beat scheduler**.

15. **No named volumes for data persistence**: Implied anonymous volumes that can be lost on `docker-compose down`.

Let me fix all of these.
</think>

### Production issues found (15 problems)

1. Django dev server (`runserver`) instead of gunicorn
2. Host volume mounts (`.:/app`) — dev only
3. No reverse proxy (Nginx) for static files / SSL
4. Unversioned images (`postgres`, `redis`)
5. Hardcoded password in compose file
6. No health checks
7. `depends_on` without readiness checks
8. No resource limits
9. No restart policy
10. No logging limits
11. Redis without persistence
12. No SSL/TLS
13. No data persistence (named volumes)
14. Celery without proper configuration
15. No `.env` file separation

### Production-ready docker-compose.yml

```yaml
version: "3.8"

services:
  # ===========================================
  # Nginx reverse proxy
  # ===========================================
  nginx:
    image: nginx:1.25-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/certs:/etc/nginx/certs:ro
      - static_files:/var/www/static:ro
      - media_files:/var/www/media:ro
    depends_on:
      web:
        condition: service_healthy
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 256M
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  # ===========================================
  # Django web application
  # ===========================================
  web:
    build:
      context: .
      dockerfile: Dockerfile
    command: >
      gunicorn myapp.wsgi:application
      --bind 0.0.0.0:8000
      --workers 4
      --worker-class gthread
      --threads 2
      --timeout 120
      --access-logfile -
      --error-logfile -
    env_file:
      - .env.production
    volumes:
      - static_files:/app/staticfiles
      - media_files:/app/media
    expose:
      - "8000"  # Internal only (Nginx proxies to this)
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/')"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 1G
    read_only: true
    tmpfs:
      - /tmp
    security_opt:
      - no-new-privileges:true
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "5"

  # ===========================================
  # Celery worker
  # ===========================================
  celery:
    build:
      context: .
      dockerfile: Dockerfile
    command: >
      celery -A myapp worker
      --loglevel info
      --concurrency 4
      --max-tasks-per-child 1000
      --without-heartbeat
    env_file:
      - .env.production
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "celery", "-A", "myapp", "inspect", "ping"]
      interval: 60s
      timeout: 10s
      retries: 3
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 2G
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  # ===========================================
  # Celery beat scheduler
  # ===========================================
  celery-beat:
    build:
      context: .
      dockerfile: Dockerfile
    command: >
      celery -A myapp beat
      --loglevel info
      --schedule /tmp/celerybeat-schedule
    env_file:
      - .env.production
    depends_on:
      redis:
        condition: service_healthy
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: "0.25"
          memory: 256M

  # ===========================================
  # PostgreSQL
  # ===========================================
  db:
    image: postgres:16-alpine
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./backups:/backups
    env_file:
      - .env.production
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: "2.0"
          memory: 2G
    shm_size: 256m  # Needed for PostgreSQL shared memory
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"

  # ===========================================
  # Redis
  # ===========================================
  redis:
    image: redis:7-alpine
    command: redis-server --appendonly yes --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redis_data:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: "0.5"
          memory: 512M

volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local
  static_files:
    driver: local
  media_files:
    driver: local
```

### Environment file (.env.production)

```bash
# .env.production (NOT committed to git — add to .gitignore)
POSTGRES_USER=myapp
POSTGRES_PASSWORD=<generated-strong-password>
POSTGRES_DB=myapp_production
DATABASE_URL=postgresql://myapp:<password>@db:5432/myapp_production
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
DJANGO_SETTINGS_MODULE=myapp.settings.production
SECRET_KEY=<generated-django-secret>
ALLOWED_HOSTS=example.com,www.example.com
DEBUG=false
```

### Nginx configuration

```nginx
upstream django {
    server web:8000;
}

server {
    listen 80;
    server_name example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    server_name example.com;

    ssl_certificate /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;

    client_max_body_size 10M;

    location /static/ {
        alias /var/www/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /var/www/media/;
        expires 7d;
    }

    location / {
        proxy_pass http://django;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 30s;
        proxy_read_timeout 120s;
    }
}
```

### Comparison: Dev vs Production

| Aspect | Development | Production |
|--------|------------|-----------|
| Web server | `runserver` | gunicorn (4 workers) |
| Code mounting | Volume mount (hot reload) | Baked into image |
| Ports exposed | `8000:8000` (direct) | `80/443` via Nginx |
| Database password | `password123` | `.env.production` (gitignored) |
| Health checks | None | All services |
| Resource limits | None | CPU + memory limits |
| Restart policy | None | `unless-stopped` |
| SSL/TLS | None | Nginx terminates SSL |
| Logging | Unlimited | 10MB max, 3 files |'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
