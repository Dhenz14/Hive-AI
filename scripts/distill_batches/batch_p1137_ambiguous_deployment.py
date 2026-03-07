"""
Ambiguous request handling pairs - vague deployment requests
"""

pairs = [
    {
        "instruction": r'''Deploy this app for me.''',
        "output": r'''<think>
"Deploy this" -- deploy where? AWS, GCP, Azure, DigitalOcean, Heroku, Vercel, a VPS, on-prem servers? What kind of app -- web server, API, static site, background worker? What's the tech stack? What are the requirements -- just get it running, or production-grade with SSL, monitoring, auto-scaling? Budget constraints? This is way too open-ended without knowing the basics.
</think>

Before I can deploy anything, I need to understand:

1. **What kind of app?** Web app, API, static site, background worker?
2. **What's the stack?** Language, framework, database, any other services (Redis, queues)?
3. **Where do you want it?** Cloud provider preference? Or whatever's easiest?
4. **What's the scale?** Side project (cheapest option) or production with real users (reliability matters)?

Here's a deployment setup for the most common case -- a Python web app to a cloud provider. I'll show two options:

```dockerfile
# Option A: Docker-based (works anywhere)
# Dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# Use gunicorn for production (not the dev server)
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "4"]
```

```yaml
# docker-compose.yml -- app + database
version: "3.8"
services:
  web:
    build: .
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: postgresql://user:pass@db:5432/appdb
      SECRET_KEY: ${SECRET_KEY}
    depends_on:
      - db
    restart: unless-stopped

  db:
    image: postgres:15
    volumes:
      - pgdata:/var/lib/postgresql/data
    environment:
      POSTGRES_DB: appdb
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass

volumes:
  pgdata:
```

```bash
# Option B: Quick deploy to a $5/mo VPS (DigitalOcean, Hetzner, etc.)

# On your server:
sudo apt update && sudo apt install -y docker.io docker-compose-plugin

# Clone and deploy
git clone https://github.com/you/your-app.git
cd your-app
docker compose up -d

# Set up HTTPS with Caddy (auto-SSL, easier than nginx + certbot)
# Caddyfile
# yourdomain.com {
#     reverse_proxy localhost:8000
# }
```

The cheapest path for a side project is a single VPS ($5-6/month) with Docker Compose. For production with uptime guarantees, I'd recommend a managed platform (Railway, Render, or AWS ECS). Tell me your situation and I'll give you the specific steps.'''
    },
    {
        "instruction": r'''Set up CI/CD for our project.''',
        "output": r'''<think>
"Set up CI/CD" -- using what? GitHub Actions, GitLab CI, Jenkins, CircleCI? What does the pipeline need to do -- run tests, lint, build, deploy? Deploy where? What's the branching strategy -- trunk-based, gitflow, feature branches? What language/framework determines the build steps. I need to know the platform and requirements, but I can provide a solid GitHub Actions template since that's most common.
</think>

CI/CD pipelines vary a lot. A few questions:

1. **Where's the code hosted?** GitHub, GitLab, Bitbucket? (Determines the CI tool)
2. **What should the pipeline do?** Lint, test, build, deploy? All of those?
3. **Where does it deploy?** (AWS, Docker registry, Vercel, VPS, etc.)
4. **What's the branching strategy?** Deploy on push to main? Require PR reviews?

Here's a solid GitHub Actions setup that covers the most common needs:

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_DB: testdb
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: pip install -r requirements.txt -r requirements-dev.txt

      - name: Lint
        run: |
          ruff check .
          ruff format --check .

      - name: Run tests
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/testdb
        run: pytest --cov=app --cov-report=xml -v

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: coverage.xml

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'
    steps:
      - uses: actions/checkout@v4

      - name: Build and push Docker image
        run: |
          echo "${{ secrets.DOCKER_PASSWORD }}" | docker login -u "${{ secrets.DOCKER_USERNAME }}" --password-stdin
          docker build -t youruser/yourapp:${{ github.sha }} .
          docker push youruser/yourapp:${{ github.sha }}

      # Add your deployment step here:
      # SSH to server, update docker-compose, pull new image, restart
      # Or: deploy to AWS ECS, Kubernetes, Railway, etc.
```

```text
What this gives you:
- Every PR: lint + test (blocks merge if failing)
- Push to main: lint + test + build Docker image + deploy
- Postgres available during tests
- Dependency caching for fast runs
- Coverage reporting
```

Tell me your hosting target and I'll fill in the deployment step. The CI part (lint + test) is fairly universal.'''
    },
    {
        "instruction": r'''Make this production ready.''',
        "output": r'''<think>
"Production ready" -- this is one of the most overloaded phrases in software. It could mean: add error handling, add logging, add monitoring, harden security, add health checks, handle graceful shutdown, set up proper configuration management, add rate limiting, set up backups, add SSL, configure proper web server (not the dev server), handle secrets properly... I don't know the current state or what's missing. Need to assess.
</think>

"Production ready" means different things to different teams. Help me prioritize:

1. **What's the app's current state?** Working prototype? Already deployed but fragile? Passing tests?
2. **What are the stakes?** Internal tool vs. customer-facing? Handling payments or sensitive data?
3. **What's the stack?** Framework, database, how it's currently running?

Here's a production readiness checklist covering the essentials. Most apps need all of these:

```python
# 1. Use a production web server (NOT the dev server)
# BAD: python app.py (or flask run, uvicorn with --reload)
# GOOD: gunicorn with workers

# gunicorn.conf.py
import multiprocessing

bind = "0.0.0.0:8000"
workers = multiprocessing.cpu_count() * 2 + 1
timeout = 30
accesslog = "-"
errorlog = "-"
loglevel = "info"


# 2. Structured logging (not print statements)
import logging
import json

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "message": record.getMessage(),
            "module": record.module,
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_data)

logger = logging.getLogger("app")
handler = logging.StreamHandler()
handler.setFormatter(JSONFormatter())
logger.addHandler(handler)


# 3. Health check endpoint
@app.get("/health")
def health():
    checks = {}
    # Database connectivity
    try:
        db.execute("SELECT 1")
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
    # Redis connectivity (if applicable)
    try:
        redis_client.ping()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    healthy = all(v == "ok" for v in checks.values())
    return checks, 200 if healthy else 503


# 4. Graceful shutdown
import signal

def shutdown_handler(signum, frame):
    logger.info("Shutting down gracefully...")
    # Close database connections, finish in-flight requests, etc.
    db.dispose()
    sys.exit(0)

signal.signal(signal.SIGTERM, shutdown_handler)


# 5. Configuration from environment (not hardcoded)
import os

class Config:
    DATABASE_URL = os.environ["DATABASE_URL"]
    SECRET_KEY = os.environ["SECRET_KEY"]
    DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
```

```text
Production readiness checklist:
[x] Production web server (gunicorn/uvicorn without --reload)
[x] Environment-based configuration (no hardcoded secrets)
[x] Structured logging
[x] Health check endpoint
[x] Graceful shutdown handling
[ ] Error tracking (Sentry or similar)
[ ] HTTPS with valid certificate
[ ] Database backups and tested restore
[ ] Rate limiting on public endpoints
[ ] Monitoring and alerting
[ ] CI/CD pipeline with tests
```

Share your current setup and I'll tell you exactly what's missing.'''
    },
    {
        "instruction": r'''Containerize our application.''',
        "output": r'''<think>
"Containerize the app" -- with Docker presumably, but I need to know the language/framework to write the Dockerfile, what services the app depends on (database, Redis, message queue), whether they want docker-compose for local dev or just a Dockerfile for CI/production, and whether there are any build steps (frontend assets, compiled languages). The Dockerfile varies significantly by stack.
</think>

To write a good Dockerfile, I need to know:

1. **What's the tech stack?** (Python/Node/Go/Java/etc. and framework)
2. **What services does it depend on?** Database, Redis, message queue?
3. **Any build steps?** Frontend assets to compile, TypeScript to transpile?
4. **Docker Compose too?** For local dev with all services, or just a Dockerfile for CI/deployment?

Here's a production-quality Docker setup for a Python web app (the most common request):

```dockerfile
# Dockerfile -- multi-stage build for smaller image
FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies (if needed, e.g., for psycopg2)
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev && \
    rm -rf /var/lib/apt/lists/*

# Install Python dependencies separately (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN adduser --disabled-password --no-create-home appuser
USER appuser

EXPOSE 8000

CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "4"]
```

```yaml
# docker-compose.yml -- full local dev environment
version: "3.8"

services:
  app:
    build: .
    ports:
      - "8000:8000"
    environment:
      - DATABASE_URL=postgresql://user:pass@db:5432/myapp
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=dev-secret-key-change-in-prod
    depends_on:
      db:
        condition: service_healthy
      redis:
        condition: service_started
    volumes:
      - .:/app  # mount source for live reloading in dev
    command: uvicorn app:app --host 0.0.0.0 --port 8000 --reload

  db:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: myapp
      POSTGRES_USER: user
      POSTGRES_PASSWORD: pass
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U user -d myapp"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"

volumes:
  pgdata:
```

```bash
# Usage:
docker compose up -d          # start everything
docker compose logs -f app    # follow app logs
docker compose down           # stop everything
docker compose down -v        # stop and delete data volumes
```

```text
Key decisions in this setup:
- slim base image (not full Debian -- 150MB vs 900MB)
- Non-root user (security best practice)
- Dependencies installed before code (layer caching)
- Dev uses volume mount + --reload, prod uses COPY + gunicorn
- Health checks on database (app waits until DB is ready)
```

Tell me your stack and I'll customize the Dockerfile and compose file.'''
    },
    {
        "instruction": r'''We need monitoring for our application.''',
        "output": r'''<think>
"We need monitoring" -- monitoring what? Application performance (response times, error rates)? Infrastructure (CPU, memory, disk)? Business metrics (sign-ups, revenue)? Uptime monitoring (is it up or down)? Log aggregation? Alerting? Each is a different tool and setup. I need to know what they want to watch, what problems they're trying to prevent/detect, and budget (self-hosted vs SaaS).
</think>

Monitoring covers several layers. Let me understand your priorities:

1. **What's most important to know?** Is the app up? Are requests slow? Are there errors? Are we running out of resources?
2. **Build or buy?** Open to SaaS (Datadog, New Relic) or prefer self-hosted (Prometheus + Grafana)?
3. **What's the stack/infrastructure?** Docker, Kubernetes, VMs, serverless?

Here's a practical monitoring setup covering the four essential layers:

```python
# Layer 1: Application metrics (what your code is doing)
# Using prometheus_client for self-hosted, or adapt for any provider

from prometheus_client import Counter, Histogram, generate_latest
import time

REQUEST_COUNT = Counter("http_requests_total", "Total requests", ["method", "endpoint", "status"])
REQUEST_LATENCY = Histogram("http_request_duration_seconds", "Request latency", ["endpoint"])

# Middleware to auto-track all requests
@app.middleware("http")
async def metrics_middleware(request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration = time.perf_counter() - start

    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.url.path,
        status=response.status_code,
    ).inc()
    REQUEST_LATENCY.labels(endpoint=request.url.path).observe(duration)

    return response

# Expose metrics endpoint for Prometheus to scrape
@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

```yaml
# Layer 2: Infrastructure monitoring with Prometheus + Grafana
# docker-compose.monitoring.yml
version: "3.8"
services:
  prometheus:
    image: prom/prometheus
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
```

```yaml
# prometheus.yml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: "app"
    static_configs:
      - targets: ["app:8000"]
```

```python
# Layer 3: Error tracking (catch exceptions you don't know about)
# Using Sentry (free tier available)
import sentry_sdk

sentry_sdk.init(
    dsn="https://your-key@sentry.io/project-id",
    traces_sample_rate=0.1,  # sample 10% of requests for performance
)

# Layer 4: Uptime monitoring (is the app reachable from outside?)
# Use a service like UptimeRobot (free), Pingdom, or BetterUptime
# Point it at your /health endpoint
# Set up alerts via email, Slack, or PagerDuty
```

```text
Monitoring priority order:
1. Uptime check (is it up? alert if not -- 5 min setup)
2. Error tracking (Sentry -- catch crashes -- 15 min setup)
3. Request metrics (response times, error rates -- 1 hour setup)
4. Infrastructure metrics (CPU, memory, disk -- 2 hour setup)
5. Business metrics (sign-ups, revenue -- custom)
6. Log aggregation (centralized searchable logs -- half day setup)
```

Start with #1 and #2 -- they take minutes and catch 80% of issues. Tell me your infrastructure and I'll give you the specific setup steps.'''
    },
]
