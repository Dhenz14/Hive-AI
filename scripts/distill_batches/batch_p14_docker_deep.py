"""p14 docker deep"""

PAIRS = [
    (
        "devops/docker-image-optimization",
        "Explain Docker image optimization including multi-stage builds, layer caching strategies, minimizing image size with distroless/Alpine bases, BuildKit features, and security scanning. Include practical Dockerfile patterns for Python and Node.js applications.",
        '''Docker images directly impact deployment speed, security surface, and resource costs. A well-optimized image is small, builds fast, and contains only what's needed to run the application.

### Multi-Stage Builds

The most impactful optimization -- separate build dependencies from runtime:

```dockerfile
# ============================================================
# Python Application -- Multi-Stage Build
# ============================================================

# Stage 1: Build dependencies in a full Python image
FROM python:3.12-slim AS builder

# Install build tools needed for compiled packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime image -- no compilers, no build tools
FROM python:3.12-slim AS runtime

# Only install runtime C libraries (not dev headers)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Non-root user for security
RUN useradd -r -s /bin/false appuser
USER appuser

WORKDIR /app
COPY . .

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
```

```dockerfile
# ============================================================
# Node.js Application -- Multi-Stage Build
# ============================================================

# Stage 1: Install dependencies
FROM node:20-alpine AS deps
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --only=production && cp -R node_modules prod_modules
RUN npm ci  # All dependencies including devDependencies

# Stage 2: Build the application
FROM node:20-alpine AS builder
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY . .
RUN npm run build

# Stage 3: Production runtime
FROM node:20-alpine AS runtime
WORKDIR /app

# Only production dependencies
COPY --from=deps /app/prod_modules ./node_modules
COPY --from=builder /app/dist ./dist
COPY package.json .

RUN addgroup -g 1001 -S nodejs && adduser -S nextjs -u 1001
USER nextjs

EXPOSE 3000
CMD ["node", "dist/server.js"]
```

### Layer Caching Strategy

Docker caches each layer. When a layer changes, all subsequent layers are rebuilt. Order instructions from least-changing to most-changing:

```dockerfile
FROM python:3.12-slim

# Layer 1: System packages (changes rarely)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl && rm -rf /var/lib/apt/lists/*

# Layer 2: Python dependencies (changes occasionally)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Layer 3: Application code (changes frequently)
COPY . .

# WRONG ORDER (busts cache on every code change):
# COPY . .                        <-- code change invalidates this
# RUN pip install -r requirements.txt  <-- rebuilt unnecessarily!
```

**Advanced caching with BuildKit mount caches:**

```dockerfile
# syntax=docker/dockerfile:1.4
FROM python:3.12-slim

# Mount pip cache to persist between builds
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

# Mount apt cache
RUN --mount=type=cache,target=/var/cache/apt \
    --mount=type=cache,target=/var/lib/apt \
    apt-get update && apt-get install -y gcc
```

### Minimal Base Images

```dockerfile
# Size comparison for a simple Go binary:
# golang:1.22         ~800MB  (full SDK)
# golang:1.22-alpine  ~250MB  (Alpine + SDK)
# alpine:3.19         ~7MB    (just Alpine)
# gcr.io/distroless/static  ~2MB  (no shell, no OS)
# scratch             ~0MB    (empty filesystem)

# Distroless for Python (no shell, no package manager)
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --target=/app/deps -r requirements.txt
COPY . .

FROM gcr.io/distroless/python3-debian12
COPY --from=builder /app /app
WORKDIR /app
ENV PYTHONPATH=/app/deps
CMD ["app.py"]

# Scratch image for static Go binaries
FROM golang:1.22 AS builder
WORKDIR /app
COPY go.* ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /server

FROM scratch
COPY --from=builder /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=builder /server /server
ENTRYPOINT ["/server"]
```

### .dockerignore

Critical for build performance and security:

```
# .dockerignore
.git
.gitignore
node_modules
__pycache__
*.pyc
.env
.env.*
*.md
docs/
tests/
.pytest_cache
.mypy_cache
.coverage
htmlcov/
Dockerfile
docker-compose*.yml
.dockerignore
```

### Security Best Practices

```dockerfile
FROM python:3.12-slim

# Pin package versions for reproducibility
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5=15.* \
    && rm -rf /var/lib/apt/lists/*

# Don't run as root
RUN groupadd -r app && useradd -r -g app -s /sbin/nologin app

# Copy with explicit ownership
COPY --chown=app:app . /app

# Drop privileges
USER app

# Read-only filesystem (set at runtime)
# docker run --read-only --tmpfs /tmp myapp

# Health check
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use COPY not ADD (ADD auto-extracts tars, fetches URLs)
COPY requirements.txt .

# Never store secrets in image layers
# BAD:  COPY .env .
# GOOD: Use runtime secrets or Docker secrets
```

### BuildKit Advanced Features

```dockerfile
# syntax=docker/dockerfile:1.4

# Secret mounts -- never stored in layers
FROM python:3.12-slim
RUN --mount=type=secret,id=pip_conf,target=/etc/pip.conf \
    pip install -r requirements.txt

# Build with: docker build --secret id=pip_conf,src=./pip.conf .

# SSH forwarding for private repos
RUN --mount=type=ssh \
    pip install git+ssh://git@github.com/private/repo.git

# Heredocs for inline files
RUN <<EOF
    apt-get update
    apt-get install -y curl
    rm -rf /var/lib/apt/lists/*
EOF

# Parallel builds with named stages
FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/ .
RUN npm ci && npm run build

FROM python:3.12-slim AS backend
WORKDIR /backend
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Both stages build in parallel with BuildKit!
FROM python:3.12-slim AS final
COPY --from=backend /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=frontend /frontend/dist /app/static
COPY backend/ /app/
CMD ["uvicorn", "app:app", "--host", "0.0.0.0"]
```

**Key optimization metrics**: (1) Target <100MB for application images, <50MB for microservices, (2) Build time under 2 minutes with warm cache, (3) Zero high/critical vulnerabilities from `docker scout` or `trivy`, (4) Non-root user, minimal capabilities, read-only filesystem where possible.'''
    ),
    (
        "devops/docker-compose-production",
        "Explain Docker Compose patterns for production-grade local development and staging including service dependencies, health checks, volume management, networking, environment configuration, and compose profiles for different environments.",
        '''Docker Compose bridges the gap between development and production by defining multi-service applications declaratively. Production-grade compose files go beyond basic service definitions.

### Service Dependencies and Health Checks

```yaml
# docker-compose.yml
version: "3.9"

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: myapp
      POSTGRES_USER: myapp
      POSTGRES_PASSWORD_FILE: /run/secrets/db_password
    secrets:
      - db_password
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql:ro
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U myapp -d myapp"]
      interval: 5s
      timeout: 3s
      retries: 5
      start_period: 10s
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "1.0"

  redis:
    image: redis:7-alpine
    command: redis-server --maxmemory 128mb --maxmemory-policy allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 3
    volumes:
      - redis_data:/data

  api:
    build:
      context: .
      dockerfile: Dockerfile
      target: runtime  # Multi-stage target
      cache_from:
        - type=local,src=/tmp/.buildx-cache
    depends_on:
      postgres:
        condition: service_healthy  # Wait for health check
      redis:
        condition: service_healthy
    environment:
      DATABASE_URL: postgresql://myapp:${DB_PASSWORD}@postgres:5432/myapp
      REDIS_URL: redis://redis:6379/0
      LOG_LEVEL: ${LOG_LEVEL:-info}
    ports:
      - "${API_PORT:-8000}:8000"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 3
      start_period: 15s
    restart: unless-stopped

  worker:
    build:
      context: .
      target: runtime
    depends_on:
      api:
        condition: service_healthy
    command: celery -A tasks worker --loglevel=info --concurrency=4
    environment:
      DATABASE_URL: postgresql://myapp:${DB_PASSWORD}@postgres:5432/myapp
      REDIS_URL: redis://redis:6379/0
    deploy:
      replicas: 2
      resources:
        limits:
          memory: 256M

  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./nginx/certs:/etc/nginx/certs:ro
    depends_on:
      api:
        condition: service_healthy

secrets:
  db_password:
    file: ./secrets/db_password.txt

volumes:
  postgres_data:
    driver: local
  redis_data:
    driver: local
```

### Compose Profiles for Environments

```yaml
# docker-compose.yml with profiles
services:
  api:
    build: .
    profiles: ["dev", "staging", "prod"]
    # ... base config

  # Only in dev: hot-reload, debug tools
  api-dev:
    build:
      context: .
      target: development
    profiles: ["dev"]
    volumes:
      - .:/app  # Mount source for hot reload
      - /app/node_modules  # Exclude node_modules
    environment:
      DEBUG: "true"
      WATCHFILES_FORCE_POLLING: "true"
    command: uvicorn app:app --reload --host 0.0.0.0

  # Only in dev: database admin
  pgadmin:
    image: dpage/pgadmin4
    profiles: ["dev"]
    ports:
      - "5050:80"
    environment:
      PGADMIN_DEFAULT_EMAIL: admin@local.dev
      PGADMIN_DEFAULT_PASSWORD: admin

  # Only in staging: monitoring stack
  prometheus:
    image: prom/prometheus
    profiles: ["staging", "prod"]
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml:ro

  grafana:
    image: grafana/grafana
    profiles: ["staging", "prod"]
    ports:
      - "3000:3000"
```

```bash
# Start specific profile
docker compose --profile dev up
docker compose --profile staging up

# Multiple profiles
docker compose --profile dev --profile monitoring up
```

### Override Files for Environment-Specific Config

```yaml
# docker-compose.override.yml (auto-loaded, for development)
services:
  api:
    build:
      target: development
    volumes:
      - .:/app
    environment:
      DEBUG: "true"
    ports:
      - "8000:8000"
      - "5678:5678"  # Debugger port
```

```yaml
# docker-compose.prod.yml
services:
  api:
    build:
      target: runtime
    restart: always
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    deploy:
      replicas: 3
      resources:
        limits:
          memory: 512M
          cpus: "2.0"
```

```bash
# Production: explicit file selection (skips override)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

### Networking Patterns

```yaml
services:
  # Frontend network: exposed to internet
  nginx:
    networks:
      - frontend
      - backend

  # API: only accessible from nginx and workers
  api:
    networks:
      - backend
      - db

  # Database: only accessible from API
  postgres:
    networks:
      - db

networks:
  frontend:
    driver: bridge
  backend:
    driver: bridge
    internal: false
  db:
    driver: bridge
    internal: true  # No external access
```

### Volume Patterns

```yaml
services:
  api:
    volumes:
      # Named volume: persistent data
      - app_data:/app/data

      # Bind mount (dev only): source code
      - ./src:/app/src:cached

      # tmpfs: ephemeral data (no disk I/O)
      - type: tmpfs
        target: /app/tmp
        tmpfs:
          size: 100M

      # Read-only config
      - ./config:/app/config:ro

volumes:
  app_data:
    driver: local
    driver_opts:
      type: none
      o: bind
      device: /data/app  # Host directory
```

**Key patterns**: (1) Always use `depends_on` with `condition: service_healthy`, (2) Use profiles to share one compose file across environments, (3) Isolate networks so databases aren't exposed, (4) Pin image tags -- never use `:latest` in staging/prod, (5) Use secrets for credentials, environment variables for non-sensitive config.'''
    ),
    (
        "devops/docker-networking-internals",
        "Explain Docker networking internals including bridge networks, overlay networks for Swarm, DNS resolution, iptables rules, network namespaces, veth pairs, and troubleshooting container networking issues.",
        '''Understanding how Docker networking works at the Linux kernel level helps you debug connectivity issues and design secure network topologies.

### Bridge Network Architecture

The default Docker bridge (`docker0`) is a Linux bridge device that connects containers via virtual ethernet (veth) pairs:

```
Host Network Stack
    │
    ├── eth0 (physical NIC, e.g., 192.168.1.100)
    │
    ├── docker0 (bridge, 172.17.0.1/16)
    │     │
    │     ├── veth1234 ←──────-> eth0 (container A, 172.17.0.2)
    │     │                     [network namespace A]
    │     │
    │     └── veth5678 ←──────-> eth0 (container B, 172.17.0.3)
    │                           [network namespace B]
    │
    └── br-customnet (user bridge, 172.18.0.1/16)
          │
          └── vethABCD ←──────-> eth0 (container C, 172.18.0.2)
                                [network namespace C]
```

### Network Namespaces

Each container gets an isolated network namespace:

```bash
# List all network namespaces (Docker creates them at runtime)
sudo ls -la /var/run/docker/netns/

# Inspect a container's network namespace
CONTAINER_PID=$(docker inspect --format '{{.State.Pid}}' mycontainer)
sudo nsenter -t $CONTAINER_PID -n ip addr show
sudo nsenter -t $CONTAINER_PID -n ip route show
sudo nsenter -t $CONTAINER_PID -n ss -tlnp

# What happens when you create a container:
# 1. Docker creates a new network namespace
# 2. Creates a veth pair (two virtual NICs connected like a pipe)
# 3. Moves one end into the container namespace as eth0
# 4. Attaches the other end to the bridge
# 5. Assigns an IP from the bridge's subnet via IPAM
# 6. Sets the bridge IP as the container's default gateway
```

### DNS Resolution

User-defined bridge networks include an embedded DNS server:

```bash
# Default bridge: containers resolve by IP only (no DNS)
docker run --network bridge alpine ping containerB  # FAILS

# User-defined bridge: automatic DNS resolution
docker network create mynet
docker run --name web --network mynet alpine
docker run --network mynet alpine ping web  # WORKS!

# DNS server runs at 127.0.0.11 inside each container
docker exec mycontainer cat /etc/resolv.conf
# nameserver 127.0.0.11
# options ndots:0
```

```python
# Programmatic DNS debugging in Python
import socket

def debug_container_dns(hostname: str):
    """Debug DNS resolution from inside a container."""
    try:
        # Standard resolution
        ip = socket.gethostbyname(hostname)
        print(f"A record: {hostname} -> {ip}")

        # Full resolution with aliases
        hostname, aliases, ips = socket.gethostbyname_ex(hostname)
        print(f"Canonical: {hostname}")
        print(f"Aliases: {aliases}")
        print(f"IPs: {ips}")

        # SRV records for service discovery
        import dns.resolver
        answers = dns.resolver.resolve(f"_http._tcp.{hostname}", "SRV")
        for rdata in answers:
            print(f"SRV: {rdata.target}:{rdata.port} "
                  f"priority={rdata.priority} weight={rdata.weight}")
    except Exception as e:
        print(f"DNS resolution failed: {e}")
```

### iptables Rules

Docker manipulates iptables for port mapping and isolation:

```bash
# View Docker's iptables rules
sudo iptables -t nat -L -n -v     # NAT rules (port mapping)
sudo iptables -t filter -L -n -v  # Filter rules (isolation)

# Port mapping: -p 8080:80 creates these rules:
# 1. DNAT in PREROUTING chain:
#    Destination 0.0.0.0:8080 -> 172.17.0.2:80
# 2. MASQUERADE in POSTROUTING chain:
#    Source from bridge subnet -> host IP

# Inter-container communication:
# On default bridge: containers CAN communicate (ICC=true)
# To disable: dockerd --icc=false

# Network isolation between user-defined networks:
# Docker adds DROP rules between different bridge networks
# Containers on netA cannot reach containers on netB
```

### Troubleshooting Container Networking

```bash
# Step 1: Verify container network configuration
docker inspect --format '{{json .NetworkSettings.Networks}}' mycontainer | jq .

# Step 2: Check connectivity from inside the container
docker exec mycontainer ping -c 3 google.com       # External
docker exec mycontainer ping -c 3 other-container   # Internal

# Step 3: Check DNS resolution
docker exec mycontainer nslookup other-container
docker exec mycontainer dig other-container

# Step 4: Check if port is listening
docker exec mycontainer netstat -tlnp
docker exec mycontainer ss -tlnp

# Step 5: Packet capture on the bridge
sudo tcpdump -i docker0 -nn port 80
# Or on a specific veth pair
VETH=$(docker exec mycontainer cat /sys/class/net/eth0/iflink)
HOST_VETH=$(ip link | grep "^${VETH}:" | awk '{print $2}' | tr -d ':')
sudo tcpdump -i $HOST_VETH -nn

# Step 6: Check iptables for dropped packets
sudo iptables -t filter -L DOCKER-ISOLATION-STAGE-1 -n -v
sudo iptables -t nat -L DOCKER -n -v
```

```python
# Python script for container network diagnostics
import subprocess
import json
from dataclasses import dataclass


@dataclass
class ContainerNetInfo:
    name: str
    id: str
    ip: str
    gateway: str
    network: str
    ports: dict


def get_container_network_info(container: str) -> ContainerNetInfo:
    result = subprocess.run(
        ["docker", "inspect", container],
        capture_output=True, text=True'''
    ),
    (
        "devops/docker-security-hardening",
        "Explain Docker security hardening including running as non-root, dropping capabilities, seccomp profiles, AppArmor/SELinux, read-only filesystems, resource limits, vulnerability scanning, and secrets management.",
        '''Containers share the host kernel, so a container escape gives full host access. Security hardening reduces the blast radius and prevents exploitation.

### Non-Root Containers

The most impactful single change -- don't run processes as root inside containers:

```dockerfile
FROM python:3.12-slim

# Create a dedicated user
RUN groupadd -r appuser && useradd -r -g appuser -s /sbin/nologin appuser

# Set ownership of application directory
WORKDIR /app
COPY --chown=appuser:appuser . .

# Install dependencies as root, then drop privileges
RUN pip install --no-cache-dir -r requirements.txt

# Switch to non-root user
USER appuser

# This process runs as UID 1000, not root
CMD ["python", "app.py"]
```

```bash
# Verify: check the running user
docker exec mycontainer whoami  # Should NOT be "root"
docker exec mycontainer id      # uid should not be 0

# Enforce at runtime even if Dockerfile forgot:
docker run --user 1000:1000 myimage

# Kubernetes: enforce via SecurityContext
# securityContext:
#   runAsNonRoot: true
#   runAsUser: 1000
#   allowPrivilegeEscalation: false
```

### Dropping Linux Capabilities

Docker grants a default set of capabilities. Drop all and add back only what's needed:

```bash
# See default capabilities
docker run --rm alpine cat /proc/1/status | grep Cap

# Drop ALL capabilities (strictest)
docker run --cap-drop=ALL myimage

# Drop all, add back specific ones
docker run \
  --cap-drop=ALL \
  --cap-add=NET_BIND_SERVICE \  # Bind to ports < 1024
  myimage

# Common capabilities and when you need them:
# NET_BIND_SERVICE - bind to privileged ports (80, 443)
# CHOWN            - change file ownership
# SETUID/SETGID    - change process UID/GID
# DAC_OVERRIDE     - bypass file permission checks
# SYS_PTRACE       - debugging (NEVER in production)
# NET_RAW          - raw sockets (ping)
```

### Read-Only Filesystem

Prevent runtime modifications to the container filesystem:

```bash
docker run --read-only \
  --tmpfs /tmp:rw,noexec,nosuid,size=64m \
  --tmpfs /var/run:rw,noexec,nosuid,size=1m \
  myimage

# In docker-compose:
# services:
#   api:
#     read_only: true
#     tmpfs:
#       - /tmp:size=64m
#       - /var/run:size=1m
```

### Seccomp Profiles

Restrict which system calls a container can make:

```json
{'''
    ),
    (
        "action",
        "} ] }",
        '''```bash
# Apply custom seccomp profile
docker run --security-opt seccomp=./strict-profile.json myimage

# Disable seccomp (NEVER do this in production)
# docker run --security-opt seccomp=unconfined myimage
```

### Resource Limits

Prevent resource exhaustion attacks (fork bombs, memory leaks):

```bash
docker run \
  --memory=256m \
  --memory-swap=256m \        # No swap (memory == memory-swap)
  --cpus=1.5 \                # 1.5 CPU cores max
  --pids-limit=100 \          # Prevent fork bombs
  --ulimit nofile=1024:1024 \ # File descriptor limit
  myimage
```

```yaml
# docker-compose.yml
services:
  api:
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: "1.5"
        reservations:
          memory: 128M
          cpus: "0.5"
    ulimits:
      nofile:
        soft: 1024
        hard: 2048
      nproc: 100
```

### Vulnerability Scanning

```bash
# Docker Scout (built-in)
docker scout cves myimage:latest
docker scout recommendations myimage:latest

# Trivy (comprehensive, free)
trivy image myimage:latest
trivy image --severity HIGH,CRITICAL myimage:latest

# Grype (Anchore)
grype myimage:latest

# In CI/CD pipeline
trivy image --exit-code 1 --severity CRITICAL myimage:latest
# Exit code 1 if any CRITICAL vulnerabilities found -> fail the build
```

### Secrets Management

```bash
# Docker secrets (Swarm mode)
echo "supersecretpassword" | docker secret create db_password -
docker service create --secret db_password myimage

# Inside container, secret is at /run/secrets/db_password
# It's a tmpfs mount -- never written to disk

# For non-Swarm: use BuildKit secrets for build-time
docker build --secret id=npmrc,src=$HOME/.npmrc .

# In Dockerfile:
# RUN --mount=type=secret,id=npmrc,target=/root/.npmrc npm install
```

```python
# Reading secrets in application code
from pathlib import Path
import os


def get_secret(name: str) -> str:
    """Read a Docker secret, falling back to environment variable."""
    # Docker secrets are files in /run/secrets/
    secret_path = Path(f"/run/secrets/{name}")
    if secret_path.exists():
        return secret_path.read_text().strip()

    # Fallback to environment variable (for development)
    env_value = os.environ.get(name.upper())
    if env_value:
        return env_value

    raise ValueError(
        f"Secret '{name}' not found in /run/secrets/ "
        f"or environment variable {name.upper()}"'''
    ),
    (
        "devops/container-orchestration-patterns",
        "Explain container orchestration patterns including sidecar, ambassador, adapter, init containers, health probes (liveness, readiness, startup), pod disruption budgets, and anti-affinity rules. Focus on the pattern concepts that apply across Kubernetes and other orchestrators.",
        '''Container orchestration patterns are reusable architectural solutions for deploying, scaling, and managing containerized applications. These patterns work across Kubernetes, Nomad, ECS, and other orchestrators.

### Sidecar Pattern

A helper container that extends the main application container without modifying it:

```yaml
# Kubernetes Pod with sidecar
apiVersion: v1
kind: Pod
metadata:
  name: web-with-logging
spec:
  containers:
    # Main application
    - name: web
      image: myapp:1.0
      ports:
        - containerPort: 8080
      volumeMounts:
        - name: logs
          mountPath: /var/log/app

    # Sidecar: ships logs to central logging
    - name: log-shipper
      image: fluent-bit:latest
      volumeMounts:
        - name: logs
          mountPath: /var/log/app
          readOnly: true
      env:
        - name: FLUENT_ELASTICSEARCH_HOST
          value: elasticsearch.logging.svc

  volumes:
    - name: logs
      emptyDir: {}
```

```python
# Sidecar pattern in code: envoy proxy sidecar
# The application doesn't know about mTLS, retries, or circuit breaking
# -- the sidecar handles it transparently.

# app.py -- simple HTTP server, no service mesh awareness
from fastapi import FastAPI

app = FastAPI()

@app.get("/api/users")
async def get_users():
    # This call goes through the local envoy sidecar
    # which adds mTLS, retries, circuit breaking
    async with httpx.AsyncClient() as client:
        # Calls localhost:15001 (envoy outbound)
        # Envoy routes to the actual user-service
        resp = await client.get("http://user-service:8080/users")
        return resp.json()

# Common sidecar use cases:
# 1. Service mesh proxy (Envoy, Linkerd)
# 2. Log collection (Fluent Bit, Filebeat)
# 3. Secret injection (Vault Agent)
# 4. TLS termination
# 5. Metric collection (Prometheus exporter)
```

### Ambassador Pattern

A proxy container that simplifies external service access:

```yaml
# Ambassador pattern: local proxy for external database
apiVersion: v1
kind: Pod
spec:
  containers:
    - name: app
      image: myapp:1.0
      env:
        # App connects to localhost -- ambassador handles routing
        - name: DATABASE_HOST
          value: "localhost"
        - name: DATABASE_PORT
          value: "5432"

    # Ambassador: Cloud SQL proxy
    - name: cloudsql-proxy
      image: gcr.io/cloud-sql-connectors/cloud-sql-proxy:2
      args:
        - "--structured-logs"
        - "project:region:instance"
      securityContext:
        runAsNonRoot: true
```

### Init Containers

Run-to-completion containers that execute before the main containers:

```yaml
apiVersion: v1
kind: Pod
spec:
  initContainers:
    # Wait for database to be ready
    - name: wait-for-db
      image: busybox
      command: ['sh', '-c',
        'until nc -z postgres-service 5432; do
           echo waiting for postgres; sleep 2;
         done']

    # Run database migrations
    - name: migrate
      image: myapp:1.0
      command: ['python', 'manage.py', 'migrate']
      env:
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-credentials
              key: url

    # Download ML model from S3
    - name: download-model
      image: amazon/aws-cli
      command: ['aws', 's3', 'cp',
        's3://models/latest/model.bin', '/models/model.bin']
      volumeMounts:
        - name: model-storage
          mountPath: /models

  containers:
    - name: app
      image: myapp:1.0
      volumeMounts:
        - name: model-storage
          mountPath: /models
          readOnly: true

  volumes:
    - name: model-storage
      emptyDir: {}
```

### Health Probes

Three types of probes for different lifecycle stages:

```yaml
apiVersion: v1
kind: Pod
spec:
  containers:
    - name: app
      image: myapp:1.0

      # Startup probe: for slow-starting apps
      # Disables liveness/readiness until app is ready
      startupProbe:
        httpGet:
          path: /health/startup
          port: 8080
        failureThreshold: 30    # 30 * 10s = 5 minutes to start
        periodSeconds: 10

      # Liveness probe: is the process healthy?
      # Failure -> container restart
      livenessProbe:
        httpGet:
          path: /health/live
          port: 8080
        initialDelaySeconds: 0  # Startup probe handles delay
        periodSeconds: 15
        timeoutSeconds: 3
        failureThreshold: 3

      # Readiness probe: can it handle traffic?
      # Failure -> removed from service endpoints (no traffic)
      readinessProbe:
        httpGet:
          path: /health/ready
          port: 8080
        periodSeconds: 5
        timeoutSeconds: 3
        failureThreshold: 2
```

```python
from fastapi import FastAPI
from contextlib import asynccontextmanager
import asyncio

app = FastAPI()

# Application state
_db_pool = None
_cache_client = None
_ready = False


@app.get("/health/startup")
async def startup_check():
    """Has the application finished initializing?"""
    if _db_pool is None:
        return {"status": "starting"}, 503
    return {"status": "started"}


@app.get("/health/live")
async def liveness_check():
    """Is the process alive and not deadlocked?"""
    # Keep this SIMPLE -- if this handler runs, we're alive.
    # Don't check external dependencies here!
    # A database being down should NOT restart your container.
    return {"status": "alive"}


@app.get("/health/ready")
async def readiness_check():
    """Can this instance handle traffic right now?"""
    checks = {}

    # Check database connectivity
    try:
        async with _db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {e}"
        return {"status": "not_ready", "checks": checks}, 503

    # Check cache connectivity
    try:
        await _cache_client.ping()
        checks["cache"] = "ok"
    except Exception:
        checks["cache"] = "degraded"
        # Cache failure might not warrant unready status

    return {"status": "ready", "checks": checks}
```

### Pod Disruption Budgets

Ensure availability during voluntary disruptions (node upgrades, scaling):

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: api-pdb
spec:
  # At least 2 replicas must stay running during disruptions
  minAvailable: 2
  # OR: at most 1 can be unavailable
  # maxUnavailable: 1
  selector:
    matchLabels:
      app: api
```

### Anti-Affinity for High Availability

Spread replicas across failure domains:

```yaml
apiVersion: apps/v1
kind: Deployment
spec:
  replicas: 3
  template:
    spec:
      affinity:
        # Don't put two API pods on the same node
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchLabels:
                  app: api
              topologyKey: kubernetes.io/hostname

          # Prefer spreading across availability zones
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchLabels:
                    app: api
                topologyKey: topology.kubernetes.io/zone
```

### Adapter Pattern

Transforms output from a container to match expected formats:

```yaml
# Adapter: converts legacy metrics to Prometheus format
apiVersion: v1
kind: Pod
spec:
  containers:
    - name: legacy-app
      image: legacy:1.0
      # Exposes metrics in custom format at :9100/stats

    - name: metrics-adapter
      image: custom-exporter:1.0
      env:
        - name: SOURCE_URL
          value: "http://localhost:9100/stats"
        - name: OUTPUT_FORMAT
          value: "prometheus"
      ports:
        - containerPort: 9090  # Prometheus scrape target
```

**Pattern selection guide**: (1) **Sidecar** when you need to extend without modifying -- logging, proxying, monitoring, (2) **Ambassador** when simplifying access to external services -- cloud databases, APIs, (3) **Adapter** when standardizing interfaces -- metric formats, log formats, (4) **Init container** when you need setup before the main app -- migrations, downloads, wait-for-dependency, (5) Always implement all three probe types -- startup for slow apps, liveness for deadlock detection, readiness for traffic management.'''
    ),
]
