"""
Shell/CLI training pairs - Docker CLI beyond basics (multi-stage, buildx, compose, cleanup).
Mix: 2 thinking, 3 direct.
"""

pairs = [
    {
        "instruction": r'''My Docker images are huge (2+ GB). Show me how to write a multi-stage Dockerfile for a Python app that produces a small final image.''',
        "output": r'''<think>
Multi-stage builds let you separate the build environment from the runtime environment. For Python, the main bloat comes from:
1. Build tools (gcc, python-dev, etc.) needed to compile wheels
2. pip cache
3. Using a fat base image

Strategy:
- Stage 1: Use a full Python image to install dependencies and build wheels
- Stage 2: Use a slim or alpine image with only the runtime deps
- Copy only the installed packages from stage 1

I should also mention .dockerignore since copying unnecessary files inflates build context.
</think>

```dockerfile
# Stage 1: Build dependencies
FROM python:3.12 AS builder

WORKDIR /app

# Install build dependencies for compiled packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime image
FROM python:3.12-slim

WORKDIR /app

# Install only runtime libraries (not build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code
COPY . .

# Non-root user
RUN useradd -r -s /bin/false appuser
USER appuser

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

Create a `.dockerignore`:

```
.git
.venv
__pycache__
*.pyc
.env
node_modules
tests/
docs/
```

Build and check the size:

```bash
docker build -t myapp:latest .
docker images myapp
# Should be 200-400MB instead of 2GB+
```

The key savings come from:
- `python:3.12-slim` base (~150MB vs ~1GB for full)
- No compiler toolchain in the final image
- `--no-cache-dir` avoids keeping pip download cache
- `.dockerignore` reduces build context'''
    },
    {
        "instruction": r'''How do I clean up Docker disk space? I'm running out of disk on my dev machine.''',
        "output": r'''```bash
# See what's using space
docker system df
# Shows: images, containers, volumes, build cache

# Nuclear option -- remove everything unused
docker system prune -a --volumes
# Removes: stopped containers, unused networks, unused images, unused volumes, build cache

# More targeted cleanup:

# Remove stopped containers
docker container prune -f

# Remove dangling images (untagged)
docker image prune -f

# Remove ALL unused images (not just dangling)
docker image prune -a -f

# Remove unused volumes (careful -- this deletes data!)
docker volume prune -f

# Remove build cache
docker builder prune -f

# Remove build cache older than 24 hours
docker builder prune --filter "until=24h" -f
```

Find the biggest images:

```bash
docker images --format '{{.Size}}\t{{.Repository}}:{{.Tag}}' | sort -rh | head -20
```

Find large volumes:

```bash
docker system df -v | grep -A 100 "VOLUME NAME"
```

Automate periodic cleanup with a cron job:

```bash
# Clean images older than 7 days, runs weekly
0 3 * * 0 docker image prune -a --filter "until=168h" -f >> /var/log/docker-cleanup.log 2>&1
```

Set Docker to limit build cache:

```bash
# In /etc/docker/daemon.json
# { "builder": { "gc": { "defaultKeepStorage": "10GB" } } }
```'''
    },
    {
        "instruction": r'''Show me a docker compose setup for a typical web app with a database, Redis cache, and the app itself, with proper networking and health checks.''',
        "output": r'''```yaml
# docker-compose.yml
services:
  app:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://appuser:secret@db:5432/myapp
      REDIS_URL: redis://redis:6379/0
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_healthy
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
    restart: unless-stopped
    networks:
      - backend

  db:
    image: postgres:16-alpine
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    environment:
      POSTGRES_USER: appuser
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: myapp
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U appuser -d myapp"]
      interval: 10s
      timeout: 3s
      retries: 5
    restart: unless-stopped
    networks:
      - backend

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 256mb --maxmemory-policy allkeys-lru
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5
    restart: unless-stopped
    networks:
      - backend

volumes:
  pgdata:
  redisdata:

networks:
  backend:
    driver: bridge
```

Common commands:

```bash
docker compose up -d           # start in background
docker compose logs -f app     # follow app logs
docker compose ps              # check status
docker compose down            # stop and remove containers
docker compose down -v         # also remove volumes (data!)
```'''
    },
    {
        "instruction": r'''How do I debug a running Docker container that seems to be misbehaving?''',
        "output": r'''<think>
Debugging containers requires different approaches:
1. Inspect logs
2. Exec into the container
3. Check resource usage
4. Inspect networking
5. Check the container's filesystem

I should cover the practical commands a developer would actually use when something goes wrong.
</think>

```bash
# Check container logs
docker logs mycontainer --tail 100 -f
# --tail 100 shows last 100 lines, -f follows

# Check logs with timestamps
docker logs mycontainer --since "30m" -t

# Get a shell inside the running container
docker exec -it mycontainer /bin/bash
# If bash isn't available (alpine):
docker exec -it mycontainer /bin/sh

# Check resource usage (CPU, memory, network IO)
docker stats mycontainer --no-stream

# Inspect container configuration
docker inspect mycontainer | jq '.[0].State'
docker inspect mycontainer | jq '.[0].NetworkSettings.Networks'

# Check what processes are running inside
docker top mycontainer

# Check container filesystem changes (vs the image)
docker diff mycontainer
# A = added, C = changed, D = deleted

# Copy files out for inspection
docker cp mycontainer:/app/logs/error.log ./error.log

# Check container events
docker events --filter container=mycontainer --since "1h"
```

If the container keeps crashing:

```bash
# See the exit code
docker inspect mycontainer --format='{{.State.ExitCode}}'

# Check OOM kill
docker inspect mycontainer --format='{{.State.OOMKilled}}'

# Run the image interactively to debug startup
docker run -it --entrypoint /bin/sh myimage:latest

# Override the command to keep it alive for debugging
docker run -d --name debug-container myimage:latest tail -f /dev/null
docker exec -it debug-container /bin/sh
```

Network debugging:

```bash
# Check if the container can reach other services
docker exec mycontainer ping db
docker exec mycontainer nc -zv db 5432

# Inspect the network
docker network inspect backend
```'''
    },
    {
        "instruction": r'''How do I use docker buildx to build multi-platform images for both AMD64 and ARM64?''',
        "output": r'''```bash
# Create a new buildx builder with multi-platform support
docker buildx create --name multibuilder --use --bootstrap

# Verify it supports multiple platforms
docker buildx inspect multibuilder

# Build and push for multiple architectures
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t myregistry/myapp:latest \
  --push \
  .

# Build without pushing (load into local Docker -- single platform only)
docker buildx build --platform linux/amd64 -t myapp:latest --load .

# Build with specific cache options for faster rebuilds
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  --cache-from type=registry,ref=myregistry/myapp:cache \
  --cache-to type=registry,ref=myregistry/myapp:cache,mode=max \
  -t myregistry/myapp:v1.2.3 \
  --push \
  .
```

Dockerfile tips for multi-platform builds:

```dockerfile
# Use platform-aware base images (official images support this)
FROM --platform=$BUILDPLATFORM python:3.12-slim AS builder

# For cross-compilation, use TARGETPLATFORM and BUILDPLATFORM args
ARG TARGETPLATFORM
ARG BUILDPLATFORM
RUN echo "Building on $BUILDPLATFORM for $TARGETPLATFORM"
```

Check manifest after pushing:

```bash
docker manifest inspect myregistry/myapp:latest
# Shows the digest for each platform

# Clean up the builder when done
docker buildx rm multibuilder
```'''
    },
]
