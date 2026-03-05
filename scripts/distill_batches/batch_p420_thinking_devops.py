"""Thinking-trace pairs: DevOps, CI/CD, deployment, and infrastructure decisions."""

PAIRS = [
    (
        "thinking/devops-zero-downtime-deploy",
        "We have a Python web app (FastAPI + PostgreSQL) running on 3 servers behind an NGINX load balancer. Currently we deploy by SSHing into each server, pulling the latest code, and restarting. This causes ~30 seconds of errors per server during restart. How do we achieve zero-downtime deployments?",
        r'''<think>
Let me analyze the current deployment flow and identify where the downtime comes from.

**Current flow (per server):**
1. SSH in
2. `git pull` — fast, no downtime
3. `pip install -r requirements.txt` — might take 30s, still no downtime (old process running)
4. `systemctl restart app` — THIS IS THE PROBLEM
   - Old process gets SIGTERM → starts shutting down
   - New process starts → loads app, connects to DB, warms up
   - During this gap (maybe 5-30 seconds), the server returns 502/503
   - NGINX sends requests to this server → errors

With 3 servers and sequential deploys, that's 3 × 30s = 90 seconds of degraded service. With round-robin, 1/3 of requests fail during each server's restart window.

**Fix layers:**

**Layer 1: Graceful shutdown**
The app should finish processing in-flight requests before exiting. FastAPI/Uvicorn supports this:
```
uvicorn app:app --timeout-graceful-shutdown 30
```
When SIGTERM is received, Uvicorn:
1. Stops accepting new connections
2. Waits for in-flight requests to complete (up to 30s)
3. Then exits

But NGINX doesn't know the server is shutting down, so it keeps sending new requests → 502 errors.

**Layer 2: NGINX health checks + drain**
Before restarting a server, tell NGINX to stop sending traffic to it:

Option A: Remove the server from NGINX upstream, reload NGINX, then restart the app.
Option B: Have the app expose a health endpoint that returns 503 during shutdown. NGINX's health check detects this and stops routing.

Option B is better — no NGINX config changes needed.

```python
# Health endpoint
is_shutting_down = False

@app.get('/health')
async def health():
    if is_shutting_down:
        return JSONResponse({'status': 'draining'}, status_code=503)
    return {'status': 'healthy'}

@app.on_event('shutdown')
async def shutdown():
    global is_shutting_down
    is_shutting_down = True
    await asyncio.sleep(5)  # Give NGINX time to detect unhealthy + drain
```

NGINX config:
```nginx
upstream app {
    server 10.0.0.1:8000 max_fails=1 fail_timeout=5s;
    server 10.0.0.2:8000 max_fails=1 fail_timeout=5s;
    server 10.0.0.3:8000 max_fails=1 fail_timeout=5s;
}
```

When a server returns 503 on the health check, NGINX marks it as failed and routes to the other two servers.

**Layer 3: Rolling deployment**
Deploy one server at a time. Wait for it to be healthy before moving to the next.

```
1. Mark server 1 as draining (health → 503)
2. Wait for NGINX to stop routing to server 1 (~5s)
3. Pull code, install deps, restart on server 1
4. Wait for server 1 to be healthy again (health → 200)
5. Repeat for server 2, then server 3
```

At any point, at least 2 of 3 servers are handling traffic. Zero dropped requests.

**Layer 4: Socket-level zero downtime (advanced)**
Instead of restarting the process, use socket handoff:
- Old process passes the listening socket to the new process
- New process accepts connections on the same socket
- No gap at all

Gunicorn supports this natively with `gunicorn --graceful-timeout 30 --reload`. Uvicorn doesn't support socket handoff, but you can achieve it with systemd socket activation.

Actually, the simplest approach that gives true zero downtime: run the new process on a different port, health-check it, then swap NGINX upstream to point to the new port. Old process drains and exits.

**My recommendation:**
For this team (SSHing into servers, no containers), the rolling deploy with health checks is the right level of complexity. It's a 10x improvement for minimal infrastructure change.

If they want to go further: containers + orchestration (Docker Compose, or Kubernetes if they grow). But that's a bigger lift.
</think>

### Solution: Rolling deploy with health check draining

Zero configuration changes to NGINX. Each server gracefully drains before restart.

### Step 1: Add health endpoint with drain support

```python
import asyncio
import signal

class AppState:
    shutting_down: bool = False

state = AppState()

@app.get('/health')
async def health():
    if state.shutting_down:
        return JSONResponse({'status': 'draining'}, status_code=503)
    # Check actual dependencies
    try:
        await db.execute('SELECT 1')
    except Exception:
        return JSONResponse({'status': 'unhealthy'}, status_code=503)
    return {'status': 'healthy'}

@app.on_event('shutdown')
async def graceful_shutdown():
    state.shutting_down = True
    # Wait for NGINX to detect unhealthy and drain existing connections
    await asyncio.sleep(10)
```

### Step 2: NGINX health check config

```nginx
upstream app {
    server 10.0.0.1:8000 max_fails=2 fail_timeout=10s;
    server 10.0.0.2:8000 max_fails=2 fail_timeout=10s;
    server 10.0.0.3:8000 max_fails=2 fail_timeout=10s;
}

server {
    location / {
        proxy_pass http://app;
        proxy_next_upstream error timeout http_502 http_503;
        proxy_connect_timeout 2s;
    }

    # Active health checks (NGINX Plus) or passive (open source)
    location /health {
        proxy_pass http://app;
        access_log off;
    }
}
```

`proxy_next_upstream` makes NGINX retry on the next server if one returns 502/503 — instant failover.

### Step 3: Rolling deploy script

```bash
#!/bin/bash
# deploy.sh — zero-downtime rolling deployment
set -euo pipefail

SERVERS=("10.0.0.1" "10.0.0.2" "10.0.0.3")
APP_DIR="/opt/app"
HEALTH_URL="http://localhost:8000/health"
DEPLOY_USER="deploy"

deploy_server() {
    local server=$1
    echo "=== Deploying to $server ==="

    # 1. Signal graceful shutdown (app returns 503 on /health)
    ssh $DEPLOY_USER@$server "kill -SIGTERM \$(cat $APP_DIR/app.pid)" || true

    # 2. Wait for NGINX to drain traffic (10 seconds)
    echo "  Draining connections..."
    sleep 12

    # 3. Pull and restart
    ssh $DEPLOY_USER@$server "
        cd $APP_DIR &&
        git pull origin main &&
        source venv/bin/activate &&
        pip install -q -r requirements.txt &&
        systemctl restart app
    "

    # 4. Wait for new process to be healthy
    echo "  Waiting for health check..."
    for i in $(seq 1 30); do
        if ssh $DEPLOY_USER@$server "curl -sf $HEALTH_URL > /dev/null 2>&1"; then
            echo "  Server $server is healthy!"
            return 0
        fi
        sleep 2
    done

    echo "  ERROR: $server failed health check after 60s!"
    return 1
}

# Deploy one server at a time
for server in "${SERVERS[@]}"; do
    deploy_server "$server"
    echo ""
done

echo "=== Deployment complete ==="
```

### What happens during deploy

```
Timeline:
0s:   Server 1 receives SIGTERM, /health → 503
2s:   NGINX detects failure, stops routing to Server 1
      Servers 2+3 handle all traffic (67% each)
12s:  Server 1 restarts with new code
18s:  Server 1 /health → 200, NGINX routes to it again
      All 3 servers active
20s:  Server 2 receives SIGTERM...
      Servers 1+3 handle all traffic
...
60s:  All 3 servers running new code

Dropped requests: 0
```

### Database migrations (the tricky part)

If your deploy includes schema changes, you need **backward-compatible migrations**:

```python
# WRONG: Rename a column in one step (breaks old code on other servers)
# ALTER TABLE users RENAME COLUMN name TO full_name;

# RIGHT: Three-step migration across deploys

# Deploy 1: Add new column, write to both
# ALTER TABLE users ADD COLUMN full_name VARCHAR(255);
# UPDATE users SET full_name = name;
# App writes to BOTH name and full_name

# Deploy 2: Read from new column
# App reads from full_name, still writes to both

# Deploy 3: Drop old column
# ALTER TABLE users DROP COLUMN name;
```

Each deploy is backward-compatible with the previous version. The rolling deploy means both old and new code run simultaneously during the transition.

### Systemd service file

```ini
# /etc/systemd/system/app.service
[Unit]
Description=FastAPI Application
After=network.target

[Service]
User=deploy
WorkingDirectory=/opt/app
ExecStart=/opt/app/venv/bin/uvicorn app:app --host 0.0.0.0 --port 8000 --workers 4
ExecReload=/bin/kill -HUP $MAINPID
TimeoutStopSec=30
KillMode=mixed
KillSignal=SIGTERM
Restart=always
PIDFile=/opt/app/app.pid

[Install]
WantedBy=multi-user.target
```

`TimeoutStopSec=30` gives the app 30 seconds to drain before systemd force-kills it.'''
    ),
    (
        "thinking/devops-docker-optimization",
        "Our Docker image for a Python app takes 15 minutes to build and is 2.3GB. The Dockerfile:\n\n```dockerfile\nFROM python:3.11\nWORKDIR /app\nCOPY . .\nRUN pip install -r requirements.txt\nRUN python manage.py collectstatic --noinput\nCMD [\"gunicorn\", \"app:app\", \"--bind\", \"0.0.0.0:8000\"]\n```\n\nHow do I fix this?",
        r'''<think>
This Dockerfile has several classic problems. Let me analyze each:

**Problem 1: `python:3.11` base image is huge**
`python:3.11` is based on Debian and includes GCC, development headers, and lots of stuff we don't need at runtime. Size: ~900MB.

Fix: Use `python:3.11-slim` (150MB) or `python:3.11-alpine` (50MB, but Alpine has musl libc which can cause issues with some Python packages).

Actually, multi-stage build is even better. Build stage with full python image (for compiling C extensions), runtime stage with slim image.

**Problem 2: `COPY . .` before `pip install` breaks caching**
Docker caches each layer. When a file changes, that layer and ALL subsequent layers are invalidated.

Current order:
1. `COPY . .` — copies ALL files (including source code)
2. `pip install` — installs dependencies

If ANY source file changes (even a comment), Docker invalidates the COPY layer, which invalidates the pip install layer. So dependencies are reinstalled from scratch every build. That's 10+ minutes wasted.

Fix: Copy requirements.txt FIRST, install deps, THEN copy source code:
```dockerfile
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
```

Now, changing source code only invalidates the second COPY layer. The pip install layer is cached unless requirements.txt changes.

**Problem 3: No .dockerignore**
`COPY . .` copies EVERYTHING: .git, __pycache__, venv, node_modules, .env files, test data. This makes the build context huge (could be GBs) and includes sensitive files.

Fix: Create `.dockerignore`:
```
.git
__pycache__
*.pyc
venv
.env
*.sqlite3
node_modules
tests
docs
```

**Problem 4: No multi-stage build**
The final image contains pip cache, build tools, and intermediate files that aren't needed at runtime.

Fix: Build in one stage, copy only the installed packages to a slim runtime image:
```dockerfile
FROM python:3.11 AS builder
RUN pip install --prefix=/install -r requirements.txt

FROM python:3.11-slim
COPY --from=builder /install /usr/local
```

**Problem 5: Running as root**
No USER directive = running as root inside the container. Security risk.

Fix: Create a non-root user.

**Problem 6: No pip cache mount**
BuildKit supports cache mounts that persist pip's download cache across builds:
```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip pip install -r requirements.txt
```

This means even when requirements.txt changes, pip only downloads NEW packages. Existing packages are cached on the host.

**Expected improvements:**
- Build time: 15 min → 1-2 min (layer caching + pip cache mount)
- Image size: 2.3 GB → 200-300 MB (slim base + multi-stage)
- Rebuild on code change: 15 min → 10-30 seconds (only code layer changes)
</think>

### Optimized Dockerfile

```dockerfile
# syntax=docker/dockerfile:1

# ---- Build stage ----
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies (only if you have C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps FIRST (cached unless requirements.txt changes)
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install -r requirements.txt

# ---- Runtime stage ----
FROM python:3.11-slim

# Security: non-root user
RUN groupadd -r app && useradd -r -g app app

WORKDIR /app

# Copy only installed packages from builder (no gcc, no pip cache)
COPY --from=builder /install /usr/local

# Install runtime-only system deps (e.g., libpq for psycopg2)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy application code LAST (most frequently changing layer)
COPY --chown=app:app . .

# Collect static files
RUN python manage.py collectstatic --noinput

USER app

EXPOSE 8000

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "4"]
```

### .dockerignore

```
.git
.gitignore
__pycache__
*.pyc
*.pyo
venv
.env
.env.*
*.sqlite3
node_modules
tests
docs
*.md
Dockerfile
docker-compose*.yml
.dockerignore
```

### What each fix does

| Fix | Build time impact | Image size impact |
|-----|-------------------|-------------------|
| Copy requirements.txt before code | **-10 min** (deps cached on code change) | — |
| `--mount=type=cache,target=/root/.cache/pip` | **-5 min** (pip downloads cached) | — |
| Multi-stage build | — | **-900MB** (no gcc, pip cache, headers) |
| `python:3.11-slim` base | — | **-750MB** (no dev packages) |
| `.dockerignore` | **-30s** (smaller build context) | **-200MB+** (no .git, venv) |

### Expected results

```
Before:  Build: 15 min    Image: 2.3 GB
After:   Build: 1-2 min   Image: 200-300 MB
Rebuild: 10-30 seconds    (only code layer changes)
```

### Layer caching explained

```dockerfile
# Layer 1: Base image (cached forever)
FROM python:3.11-slim

# Layer 2: System deps (cached until Dockerfile changes)
RUN apt-get install ...

# Layer 3: Python deps (cached until requirements.txt changes)
COPY requirements.txt .        ← Only this file
RUN pip install ...             ← Cached!

# Layer 4: App code (rebuilt on every code change)
COPY . .                        ← This changes often

# When you change app code, only Layer 4 rebuilds.
# Layers 1-3 are cached. Takes seconds, not minutes.
```

### Build with BuildKit

```bash
# Enable BuildKit for cache mounts
DOCKER_BUILDKIT=1 docker build -t myapp .

# Or set globally in /etc/docker/daemon.json:
# {"features": {"buildkit": true}}
```'''
    ),
    (
        "thinking/devops-logging-strategy",
        "Our app writes logs to files on each server. When debugging production issues, we SSH into each server and grep the logs. With 10 servers, this is painful. What's the right logging setup?",
        r'''<think>
The current approach has several problems:

1. **Logs are distributed** — have to search 10 servers to find one request's logs
2. **Logs are ephemeral** — disk fills up, logs rotate, servers get replaced
3. **No correlation** — can't trace a request across services
4. **No alerting** — nobody knows about errors until users complain
5. **No structured data** — grep on text is fragile

**What we need:**
- Centralized log aggregation (one place to search)
- Structured logging (JSON, not text)
- Request correlation (trace IDs)
- Log levels (don't drown in DEBUG in production)
- Alerting on error patterns
- Retention policy (keep important logs, purge noise)

**Centralized logging stack options:**

**1. ELK (Elasticsearch + Logstash + Kibana)**
Industry standard. Elasticsearch for search/storage, Logstash for ingestion/parsing, Kibana for UI.
- Pros: powerful search, rich visualization, widely known
- Cons: heavy (Elasticsearch needs significant RAM), operational overhead
- Cost: $0 (self-hosted) to $$$ (Elastic Cloud)

**2. Loki + Grafana (Grafana Labs)**
Lightweight alternative to ELK. Loki is like "Prometheus for logs" — indexes only labels, not full text.
- Pros: much lighter than Elasticsearch, integrates with Grafana, cheaper storage
- Cons: no full-text search (grep-like queries only), less powerful analysis
- Cost: $0 (self-hosted) or Grafana Cloud free tier

**3. Cloud-native (CloudWatch, Cloud Logging)**
If on AWS/GCP, use their built-in logging.
- Pros: zero operational overhead, integrated with cloud services
- Cons: vendor lock-in, can get expensive at scale

**4. SaaS (Datadog, Splunk, Papertrail)**
- Pros: zero maintenance, powerful features
- Cons: expensive at scale (Datadog charges per GB ingested)

**For a team running their own servers (10 servers, SSH-based deploys):**

I'd recommend **Loki + Grafana** or **ELK** depending on team size. Loki is simpler to operate. ELK is more powerful for complex queries.

Actually, the most impactful change is **structured logging** — regardless of the aggregation tool. Moving from text logs to JSON logs is the single biggest improvement.

**Structured logging:**

Before (text):
```
2026-03-05 10:23:45 ERROR Failed to process order 12345 for user 67890
```

After (JSON):
```json
{"timestamp": "2026-03-05T10:23:45Z", "level": "error", "message": "Failed to process order",
 "order_id": 12345, "user_id": 67890, "error": "InsufficientFunds", "request_id": "req_abc123",
 "service": "order-service", "host": "server-03"}
```

The JSON version is machine-parseable. You can:
- Filter: `order_id = 12345`
- Aggregate: `count by error where level = "error"`
- Correlate: `request_id = "req_abc123"` across all services

**Request tracing:**

Every incoming HTTP request gets a unique `request_id`. This ID is:
1. Generated at the edge (load balancer or first service)
2. Passed in headers to downstream services
3. Included in every log line
4. Returned in error responses (for customer support: "what's your request ID?")

When debugging: search for `request_id = "req_abc123"` → see the full request lifecycle across all 10 servers.

**My recommendation stack:**

1. **structlog** for Python structured logging
2. **Promtail → Loki → Grafana** for aggregation and search
3. **Request ID middleware** for correlation
4. **Alertmanager** for error alerting
</think>

### Recommended stack: Structured logging → Loki → Grafana

```
┌──────────┐    ┌──────────┐    ┌───────┐    ┌─────────┐
│ App (×10)│───→│ Promtail │───→│ Loki  │───→│ Grafana │
│ (JSON)   │    │ (shipper)│    │(store)│    │ (search)│
└──────────┘    └──────────┘    └───────┘    └─────────┘
```

### Step 1: Structured logging in Python

```python
# pip install structlog

import structlog
import logging
import sys

def setup_logging():
    """Configure structured JSON logging."""
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,  # Request context
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),       # Output as JSON
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),  # stdout, not files
    )

logger = structlog.get_logger()

# Usage in code:
logger.info("order_created", order_id=12345, user_id=67890, total=99.99)
# → {"event": "order_created", "order_id": 12345, "user_id": 67890,
#    "total": 99.99, "level": "info", "timestamp": "2026-03-05T10:23:45Z"}

logger.error("payment_failed", order_id=12345, error="insufficient_funds",
             gateway_response_code=402)
# → {"event": "payment_failed", "order_id": 12345, "error": "insufficient_funds",
#    "gateway_response_code": 402, "level": "error", ...}
```

### Step 2: Request ID middleware

```python
import uuid
import structlog
from contextvars import ContextVar

request_id_var: ContextVar[str] = ContextVar('request_id', default='')

@app.middleware('http')
async def request_context(request, call_next):
    # Get or generate request ID
    request_id = request.headers.get('X-Request-ID', f'req_{uuid.uuid4().hex[:12]}')
    request_id_var.set(request_id)

    # Bind to all log messages in this request
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        method=request.method,
        path=request.url.path,
        client_ip=request.client.host,
    )

    logger.info("request_started")

    response = await call_next(request)

    logger.info("request_completed", status=response.status_code)

    response.headers['X-Request-ID'] = request_id
    return response
```

Now EVERY log line in this request includes `request_id`, `method`, `path`. Search by request ID to see the full story.

### Step 3: Log output (stdout, not files)

```python
# DON'T write to files in the app
# logging.FileHandler('/var/log/app.log')  ← NO

# DO write to stdout — let infrastructure handle collection
# structlog outputs to stdout by default
# Docker/systemd captures stdout → Promtail ships to Loki
```

### Log level guidelines

```python
logger.debug(...)   # Development only. Never in production.
logger.info(...)    # Business events: order created, user logged in, job completed
logger.warning(...) # Unusual but handled: retry attempt, slow query, deprecated API call
logger.error(...)   # Failure requiring attention: payment failed, DB connection lost
logger.critical(...) # System-level failure: out of memory, data corruption
```

### What to log (and what not to)

```python
# GOOD: Business events with structured data
logger.info("order_created", order_id=order.id, total=order.total, items=len(order.items))
logger.error("payment_declined", order_id=order.id, reason=gateway.error_code)

# BAD: Logging sensitive data
logger.info("user_login", email=user.email, password=user.password)  # NEVER
logger.info("payment", card_number=card.number)  # NEVER

# BAD: Noisy logs that provide no value
logger.info("entering function process_order")  # Don't log entry/exit
logger.info("query: SELECT * FROM orders WHERE id = 5")  # SQL logs belong in DB profiler
```

### Grafana dashboard query examples

```logql
# All errors in the last hour
{app="order-service"} |= "error" | json | level="error"

# Trace a specific request across all services
{app=~".+"} | json | request_id="req_abc123def456"

# Count errors by type in the last 24h
sum by (error) (count_over_time(
  {app="order-service"} | json | level="error" [24h]
))

# Slow requests (>1 second)
{app="order-service"} | json | event="request_completed" | duration > 1000
```

### Alerting on errors

```yaml
# Grafana alerting rule
- alert: HighErrorRate
  expr: |
    sum(rate({app="order-service"} | json | level="error" [5m]))
    / sum(rate({app="order-service"} | json [5m])) > 0.05
  for: 5m
  labels:
    severity: critical
  annotations:
    summary: "Error rate above 5% for 5 minutes"
```'''
    ),
]
