"""
Multi-turn conversation training pairs - DevOps infrastructure setup
Covers: Dockerfile -> docker-compose -> CI/CD -> monitoring -> production deploy
Progressive complexity through conversation flow
"""

pairs = [
    {
        "instruction": r'''[Previous conversation]
User: I have a Python Flask API and I want to containerize it. I've never used Docker before. Where do I start?
Assistant: Start by creating a Dockerfile in your project root. It defines how to build your container image. You'll also need a .dockerignore file to exclude unnecessary files. What Python version are you using, and does your app have a requirements.txt?

[Current message]
User: Python 3.11, and yes I have requirements.txt. My app entry point is app.py and it runs on port 5000. Show me the Dockerfile.''',
        "output": r'''Since you have a standard Flask setup with requirements.txt and app.py, here's a production-ready Dockerfile:

```dockerfile
# Use slim image -- much smaller than the full Python image
FROM python:3.11-slim AS base

# Prevent Python from writing .pyc files and enable unbuffered output
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Create a non-root user for security
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --create-home appuser

WORKDIR /app

# Install dependencies first (cached layer if requirements.txt unchanged)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Switch to non-root user
USER appuser

# Expose the port your app runs on
EXPOSE 5000

# Use gunicorn instead of Flask dev server for production
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "app:app"]
```

And create a `.dockerignore` file to keep the image lean:

```
__pycache__
*.pyc
.git
.gitignore
.env
*.md
.venv
venv
tests/
.pytest_cache
```

Key design decisions:

1. **Layer ordering** -- COPY requirements.txt before the rest of the code. Docker caches layers, so if only your code changes (not dependencies), the pip install layer is reused. This makes rebuilds fast.

2. **Non-root user** -- Running as root inside a container is a security risk. The appuser has no sudo access.

3. **gunicorn** -- Flask's built-in server is single-threaded and not meant for production. Add `gunicorn` to your requirements.txt.

4. **--no-cache-dir** -- Saves space by not caching downloaded packages inside the image.

Build and test it:

```bash
docker build -t myflaskapp .
docker run -p 5000:5000 myflaskapp
```

Then visit http://localhost:5000 to verify it works.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I containerized my Flask API with Docker. Now I need to add a PostgreSQL database and Redis cache. Should I run them all in one container?
Assistant: No -- each service should be its own container. That's the Docker best practice. Use docker-compose to define and link multiple containers together. It handles networking between them automatically.

[Current message]
User: OK show me how to set up docker-compose with my Flask app, PostgreSQL, and Redis. I need the data to persist when containers restart.''',
        "output": r'''Since you already have the Dockerfile for your Flask app from our earlier work, here's the docker-compose setup that adds PostgreSQL and Redis with persistent storage:

```yaml
# docker-compose.yml
version: "3.8"

services:
  api:
    build: .
    ports:
      - "5000:5000"
    environment:
      - DATABASE_URL=postgresql://bloguser:secretpass@db:5432/blogdb
      - REDIS_URL=redis://cache:6379/0
      - FLASK_ENV=production
    depends_on:
      db:
        condition: service_healthy
      cache:
        condition: service_started
    restart: unless-stopped

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: bloguser
      POSTGRES_PASSWORD: secretpass
      POSTGRES_DB: blogdb
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./init.sql:/docker-entrypoint-initdb.d/init.sql
    ports:
      - "5432:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bloguser -d blogdb"]
      interval: 5s
      timeout: 5s
      retries: 5
    restart: unless-stopped

  cache:
    image: redis:7-alpine
    volumes:
      - redisdata:/data
    command: redis-server --appendonly yes
    ports:
      - "6379:6379"
    restart: unless-stopped

volumes:
  pgdata:
  redisdata:
```

Key points about this setup:

1. **Named volumes** (`pgdata`, `redisdata`) -- these persist data across container restarts and rebuilds. Without them, you lose your database every time the container stops.

2. **depends_on with healthcheck** -- the API container waits until PostgreSQL is actually ready to accept connections, not just until the container starts. This prevents "connection refused" errors on startup.

3. **Service names as hostnames** -- inside the Docker network, your Flask app connects to `db:5432` and `cache:6379`. Docker's internal DNS resolves these automatically.

4. **Redis AOF persistence** -- `--appendonly yes` writes every operation to disk, so Redis data survives restarts.

Update your Flask app's config to read from environment variables:

```python
# config.py
import os

DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///local.db')
REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
```

Run it all:

```bash
# Start everything
docker-compose up -d

# Check status
docker-compose ps

# View logs
docker-compose logs -f api

# Stop everything (data persists)
docker-compose down

# Stop AND delete volumes (destroys data)
docker-compose down -v
```

The init.sql file in the db volume mount runs once when the PostgreSQL container is first created -- put your CREATE TABLE statements there.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I have docker-compose working with Flask, PostgreSQL, and Redis. Now I want to add CI/CD. I'm using GitHub and want to run tests automatically on every push.
Assistant: GitHub Actions is the natural choice since you're already on GitHub. You'll create a workflow YAML file that defines your CI pipeline. It can build your Docker image, run tests, and even deploy on merge to main.

User: I use pytest for testing. Some tests need the database and Redis. How do I handle that in CI?
Assistant: GitHub Actions supports service containers -- you can spin up PostgreSQL and Redis alongside your test runner. They work just like docker-compose services but are managed by the CI runner.

[Current message]
User: Show me the complete GitHub Actions workflow. I want it to: run linting, run tests with database, build the Docker image, and push to Docker Hub when merging to main.''',
        "output": r'''Building on your existing docker-compose setup and pytest test suite, here's the full CI/CD workflow:

```yaml
# .github/workflows/ci.yml
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

env:
  DOCKER_IMAGE: yourusername/myflaskapp

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install linting tools
        run: pip install flake8 black isort

      - name: Run flake8
        run: flake8 . --max-line-length 120 --exclude .venv,migrations

      - name: Check formatting with black
        run: black --check --line-length 120 .

      - name: Check import ordering
        run: isort --check-only --profile black .

  test:
    runs-on: ubuntu-latest
    needs: lint

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: testuser
          POSTGRES_PASSWORD: testpass
          POSTGRES_DB: testdb
        ports:
          - 5432:5432
        options: >-
          --health-cmd "pg_isready -U testuser -d testdb"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 5

      redis:
        image: redis:7-alpine
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 5s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: "pip"

      - name: Install dependencies
        run: pip install -r requirements.txt -r requirements-test.txt

      - name: Run tests with coverage
        env:
          DATABASE_URL: postgresql://testuser:testpass@localhost:5432/testdb
          REDIS_URL: redis://localhost:6379/0
        run: pytest --cov=app --cov-report=xml -v

      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          file: ./coverage.xml

  build-and-push:
    runs-on: ubuntu-latest
    needs: test
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'

    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-buildx-action@v3

      - uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_TOKEN }}

      - uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{ env.DOCKER_IMAGE }}:latest
            ${{ env.DOCKER_IMAGE }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
```

You need to set two repository secrets in GitHub (Settings -> Secrets):
- `DOCKER_USERNAME` -- your Docker Hub username
- `DOCKER_TOKEN` -- a Docker Hub access token (not your password)

The pipeline flow is: lint -> test -> build-and-push. The build job only runs on pushes to main (not on PRs), so you don't waste CI minutes building images for every PR. The `cache-from: type=gha` uses GitHub Actions cache to speed up Docker builds by reusing layers.

Create a `requirements-test.txt` for test-only dependencies:

```
pytest
pytest-cov
```

The service containers use the same healthcheck pattern as your docker-compose, so tests won't start until PostgreSQL and Redis are fully ready.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My CI/CD pipeline builds and pushes Docker images to Docker Hub. Now I need monitoring. The app is running on a single VPS. What should I set up?
Assistant: For a single VPS, I'd recommend a lightweight monitoring stack: Prometheus for metrics collection, Grafana for dashboards, and either Loki or just structured logging for log aggregation. You can run all of these as Docker containers alongside your app.

User: Let's start simple. How do I add Prometheus metrics to my Flask app?
Assistant: Install the prometheus-flask-instrumentator package. It automatically tracks request count, latency, and error rates. Then configure Prometheus to scrape your app's /metrics endpoint.

[Current message]
User: Show me how to add Prometheus to my Flask app and set up Prometheus + Grafana in docker-compose. I want to see request latency and error rate dashboards.''',
        "output": r'''Since you already have docker-compose with Flask, PostgreSQL, and Redis from our earlier setup, we'll add Prometheus instrumentation to the app and two new services to the compose file.

Step 1 -- Instrument your Flask app:

```python
# app.py
from flask import Flask
from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST
import time

app = Flask(__name__)

# Define metrics
REQUEST_COUNT = Counter(
    'http_requests_total',
    'Total HTTP requests',
    ['method', 'endpoint', 'status']
)

REQUEST_LATENCY = Histogram(
    'http_request_duration_seconds',
    'HTTP request latency in seconds',
    ['method', 'endpoint'],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0]
)

@app.before_request
def start_timer():
    from flask import g
    g.start_time = time.time()

@app.after_request
def record_metrics(response):
    from flask import g, request
    if request.path == '/metrics':
        return response
    latency = time.time() - g.start_time
    REQUEST_LATENCY.labels(
        method=request.method,
        endpoint=request.path
    ).observe(latency)
    REQUEST_COUNT.labels(
        method=request.method,
        endpoint=request.path,
        status=response.status_code
    ).inc()
    return response

@app.route('/metrics')
def metrics():
    from flask import Response
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)
```

Step 2 -- Add Prometheus and Grafana to docker-compose.yml:

```yaml
  # Add these to your existing services section:
  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
      - promdata:/prometheus
    ports:
      - "9090:9090"
    restart: unless-stopped

  grafana:
    image: grafana/grafana:latest
    volumes:
      - grafdata:/var/lib/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=changeme
    depends_on:
      - prometheus
    restart: unless-stopped

# Add to your volumes section:
volumes:
  pgdata:
  redisdata:
  promdata:
  grafdata:
```

Step 3 -- Create Prometheus config:

```yaml
# monitoring/prometheus.yml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'flask-api'
    static_configs:
      - targets: ['api:5000']
    metrics_path: /metrics
    scrape_interval: 5s
```

Step 4 -- Set up Grafana dashboards:

After running `docker-compose up -d`, go to http://localhost:3000 (admin/changeme).

Add Prometheus as a data source:
- URL: `http://prometheus:9090`
- Click "Save & Test"

Create a dashboard with these PromQL queries:

Request rate:
```
rate(http_requests_total[5m])
```

Average latency by endpoint:
```
rate(http_request_duration_seconds_sum[5m]) / rate(http_request_duration_seconds_count[5m])
```

95th percentile latency:
```
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))
```

Error rate (5xx responses):
```
sum(rate(http_requests_total{status=~"5.."}[5m])) / sum(rate(http_requests_total[5m]))
```

Add `prometheus-client` to your requirements.txt. The /metrics endpoint is excluded from its own tracking to avoid recursive counting.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I have my Flask app with Docker, CI/CD, and Prometheus monitoring all working. Now I need to deploy to production. I have an Ubuntu VPS with 4GB RAM and I bought a domain name.
Assistant: Great -- for a single VPS deployment you'll need: nginx as a reverse proxy with SSL, your docker-compose stack, and Let's Encrypt for free SSL certificates. I'd use nginx on the host (not containerized) to handle SSL termination.

User: Why nginx on the host instead of in Docker?
Assistant: Managing SSL certificates is easier on the host -- certbot can auto-renew without Docker volume gymnastics. Nginx on the host proxies to your Docker containers on localhost. It also means you can restart your app containers without dropping SSL connections.

[Current message]
User: Makes sense. Walk me through the full production deployment -- nginx config, SSL setup, and getting docker-compose running on the VPS.''',
        "output": r'''Since you have the VPS and domain ready, here's the step-by-step production deployment building on everything we've set up.

Step 1 -- Initial server setup:

```bash
# SSH into your VPS
ssh root@your-server-ip

# Update and install essentials
apt update && apt upgrade -y
apt install -y nginx certbot python3-certbot-nginx docker.io docker-compose

# Enable Docker
systemctl enable docker
systemctl start docker

# Create a deploy user (don't run Docker as root)
adduser deploy
usermod -aG docker deploy
```

Step 2 -- Deploy your app:

```bash
# As the deploy user
su - deploy
mkdir -p /home/deploy/app
cd /home/deploy/app

# Clone your repo (or scp your files)
git clone https://github.com/yourusername/myflaskapp.git .

# Create production .env file
cat > .env << 'ENVEOF'
DATABASE_URL=postgresql://bloguser:STRONG_PASSWORD_HERE@db:5432/blogdb
REDIS_URL=redis://cache:6379/0
FLASK_ENV=production
POSTGRES_USER=bloguser
POSTGRES_PASSWORD=STRONG_PASSWORD_HERE
POSTGRES_DB=blogdb
ENVEOF

# Start the stack
docker-compose --env-file .env up -d
```

Step 3 -- Configure nginx:

```nginx
# /etc/nginx/sites-available/myflaskapp
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    # Redirect HTTP to HTTPS (certbot will modify this)
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Timeouts
        proxy_connect_timeout 30s;
        proxy_read_timeout 60s;
        proxy_send_timeout 60s;
    }

    # Don't expose metrics publicly
    location /metrics {
        deny all;
        return 404;
    }

    # Security headers
    add_header X-Frame-Options DENY;
    add_header X-Content-Type-Options nosniff;
    add_header X-XSS-Protection "1; mode=block";
}
```

```bash
# Enable the site
ln -s /etc/nginx/sites-available/myflaskapp /etc/nginx/sites-enabled/
rm /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
```

Step 4 -- SSL with Let's Encrypt:

```bash
certbot --nginx -d yourdomain.com -d www.yourdomain.com
# Follow the prompts, select "redirect HTTP to HTTPS"

# Certbot auto-renewal is set up automatically
# Verify with:
certbot renew --dry-run
```

Step 5 -- Create a deploy script for future updates:

```bash
# /home/deploy/deploy.sh
#!/bin/bash
set -e
cd /home/deploy/app
git pull origin main
docker-compose build api
docker-compose up -d api
echo "Deployed at $(date)"
```

Step 6 -- Lock down the server:

```bash
# Only expose ports 80, 443, and SSH
ufw allow 22
ufw allow 80
ufw allow 443
ufw enable

# Remove the port mappings for Prometheus/Grafana/DB from docker-compose
# in production -- access them through an SSH tunnel instead:
# ssh -L 3000:localhost:3000 deploy@your-server-ip
```

Remove `ports` entries for db, cache, prometheus, and grafana in your production docker-compose so they are only accessible internally within the Docker network. The nginx `/metrics` deny block prevents external access to Prometheus data.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My production Flask app is running but I need log aggregation. Right now I'm just using print statements and checking docker-compose logs manually.
Assistant: You should switch from print statements to Python's logging module with structured JSON output. That makes logs parseable by any log aggregation tool. For collection, we can add Loki to your existing Prometheus + Grafana stack.

[Current message]
User: Show me how to set up structured logging in Flask and connect it to Loki so I can search logs in Grafana.''',
        "output": r'''Building on your existing monitoring stack with Prometheus and Grafana, here's how to add structured logging with Loki.

Step 1 -- Structured JSON logging in your Flask app:

```python
# logging_config.py
import logging
import json
import sys
from datetime import datetime

class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        if record.exc_info and record.exc_info[0]:
            log_data['exception'] = self.formatException(record.exc_info)
        # Add extra fields if provided
        for key in ('request_id', 'user_id', 'endpoint', 'method', 'status', 'duration_ms'):
            val = getattr(record, key, None)
            if val is not None:
                log_data[key] = val
        return json.dumps(log_data)

def setup_logging(app):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    app.logger.handlers = [handler]
    app.logger.setLevel(logging.INFO)
    # Also capture werkzeug and sqlalchemy logs
    logging.getLogger('werkzeug').handlers = [handler]
    logging.getLogger('sqlalchemy.engine').handlers = [handler]
    logging.getLogger('sqlalchemy.engine').setLevel(logging.WARNING)
```

```python
# In app.py, add request logging middleware:
import uuid
import time

@app.before_request
def before_request():
    from flask import g, request
    g.request_id = str(uuid.uuid4())[:8]
    g.start_time = time.time()

@app.after_request
def log_request(response):
    from flask import g, request
    duration = (time.time() - g.start_time) * 1000
    app.logger.info(
        'request completed',
        extra={
            'request_id': g.request_id,
            'method': request.method,
            'endpoint': request.path,
            'status': response.status_code,
            'duration_ms': round(duration, 2),
        }
    )
    return response
```

Step 2 -- Add Loki and Promtail to docker-compose:

```yaml
  loki:
    image: grafana/loki:2.9.0
    ports:
      - "3100:3100"
    volumes:
      - lokidata:/loki
    command: -config.file=/etc/loki/local-config.yaml
    restart: unless-stopped

  promtail:
    image: grafana/promtail:2.9.0
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./monitoring/promtail.yml:/etc/promtail/config.yml
    command: -config.file=/etc/promtail/config.yml
    depends_on:
      - loki
    restart: unless-stopped

volumes:
  lokidata:
```

Step 3 -- Promtail config to collect Docker container logs:

```yaml
# monitoring/promtail.yml
server:
  http_listen_port: 9080

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: docker
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
        refresh_interval: 5s
    relabel_configs:
      - source_labels: ['__meta_docker_container_name']
        target_label: 'container'
      - source_labels: ['__meta_docker_container_log_stream']
        target_label: 'stream'
    pipeline_stages:
      - json:
          expressions:
            level: level
            message: message
            endpoint: endpoint
      - labels:
          level:
          endpoint:
```

Step 4 -- In Grafana, add Loki as a data source (URL: `http://loki:3100`), then query logs with LogQL:

```
{container="app-api-1"} | json | level="ERROR"
{container="app-api-1"} | json | duration_ms > 1000
{container="app-api-1"} | json | endpoint="/api/posts"
```

All your logs are now structured JSON, collected automatically from Docker, and searchable in Grafana alongside your Prometheus metrics.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I need to add a staging environment that mirrors production. Currently I only have production running on my VPS.
Assistant: You have several options: a separate VPS for staging, Docker contexts to manage multiple environments, or using docker-compose override files to run staging on the same server with different ports. Since you're on a single VPS with 4GB RAM, the override approach is most cost-effective.

[Current message]
User: Let's do the docker-compose override approach. How do I run staging alongside production on the same VPS without conflicts?''',
        "output": r'''Building on your existing production docker-compose setup, here's how to run a staging environment in parallel using separate compose projects.

Step 1 -- Create a staging compose override file:

```yaml
# docker-compose.staging.yml
version: "3.8"

services:
  api:
    build: .
    ports:
      - "5001:5000"  # Different host port
    environment:
      - DATABASE_URL=postgresql://bloguser:stagingpass@db:5432/staging_db
      - REDIS_URL=redis://cache:6379/1
      - FLASK_ENV=staging
    depends_on:
      db:
        condition: service_healthy

  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: bloguser
      POSTGRES_PASSWORD: stagingpass
      POSTGRES_DB: staging_db
    volumes:
      - staging_pgdata:/var/lib/postgresql/data
    ports:
      - "5433:5432"
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U bloguser -d staging_db"]
      interval: 5s
      timeout: 5s
      retries: 5

  cache:
    image: redis:7-alpine
    volumes:
      - staging_redisdata:/data
    command: redis-server --appendonly yes
    ports:
      - "6380:6379"

volumes:
  staging_pgdata:
  staging_redisdata:
```

Step 2 -- Use Docker Compose project names to isolate environments:

```bash
# Production (already running)
docker-compose -p prod up -d

# Staging (separate network, volumes, containers)
docker-compose -p staging -f docker-compose.staging.yml up -d

# Check both environments
docker-compose -p prod ps
docker-compose -p staging ps
```

The `-p` flag gives each environment its own project namespace. Containers, networks, and volumes are prefixed with the project name, so there are no conflicts.

Step 3 -- Add staging to nginx:

```nginx
# /etc/nginx/sites-available/staging
server {
    listen 80;
    server_name staging.yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:5001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # Basic auth to prevent public access
    auth_basic "Staging Environment";
    auth_basic_user_file /etc/nginx/.htpasswd_staging;

    location /metrics {
        deny all;
        return 404;
    }
}
```

```bash
# Create basic auth credentials for staging
apt install apache2-utils
htpasswd -c /etc/nginx/.htpasswd_staging developer

# Enable site and get SSL
ln -s /etc/nginx/sites-available/staging /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx
certbot --nginx -d staging.yourdomain.com
```

Step 4 -- Deploy script that handles both environments:

```bash
#!/bin/bash
# deploy.sh
set -e
ENV=${1:-staging}  # default to staging

cd /home/deploy/app
git fetch origin

if [ "$ENV" = "staging" ]; then
    git checkout develop
    git pull origin develop
    docker-compose -p staging -f docker-compose.staging.yml build api
    docker-compose -p staging -f docker-compose.staging.yml up -d api
    echo "Deployed to STAGING at $(date)"
elif [ "$ENV" = "production" ]; then
    git checkout main
    git pull origin main
    docker-compose -p prod build api
    docker-compose -p prod up -d api
    echo "Deployed to PRODUCTION at $(date)"
fi
```

Usage: `./deploy.sh staging` or `./deploy.sh production`. Redis uses database 1 (`/1` in the URL) for staging vs database 0 for production, keeping cached data separate even though they share a Redis instance to save RAM.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My app is getting popular and I need zero-downtime deployments. Right now when I deploy, there's a few seconds of downtime while the container restarts.
Assistant: The standard approaches are: rolling updates (start new container, then stop old one), blue-green deployment (run two identical environments and switch traffic), or using Docker Swarm/Kubernetes for orchestrated rolling updates. For your single-VPS setup, a simple blue-green approach with nginx is the easiest.

User: Blue-green sounds good. But I don't want to maintain two full copies of the database. Can I share the database between blue and green?
Assistant: Absolutely -- the database stays shared. Blue and green are just two copies of your API container pointing at the same PostgreSQL and Redis. Nginx switches which one receives traffic.

[Current message]
User: Show me how to implement blue-green deployments on my VPS with docker-compose and nginx.''',
        "output": r'''Building on your existing nginx and docker-compose setup, here's a blue-green deployment system that shares the database.

Step 1 -- Create a deployment script:

```bash
#!/bin/bash
# /home/deploy/blue-green-deploy.sh
set -e

APP_DIR=/home/deploy/app
NGINX_CONF=/etc/nginx/conf.d/upstream.conf

# Determine which slot is currently live
CURRENT=$(cat "$APP_DIR/.active-slot" 2>/dev/null || echo "blue")
if [ "$CURRENT" = "blue" ]; then
    TARGET="green"
    TARGET_PORT=5001
    OLD_PORT=5000
else
    TARGET="blue"
    TARGET_PORT=5000
    OLD_PORT=5001
fi

echo "Current: $CURRENT (port $OLD_PORT)"
echo "Deploying to: $TARGET (port $TARGET_PORT)"

cd "$APP_DIR"
git pull origin main

# Build and start the new slot
docker-compose -p "$TARGET" -f "docker-compose.$TARGET.yml" build api
docker-compose -p "$TARGET" -f "docker-compose.$TARGET.yml" up -d api

# Wait for the new slot to be healthy
echo "Waiting for $TARGET to be healthy..."
for i in $(seq 1 30); do
    if curl -sf "http://127.0.0.1:$TARGET_PORT/health" > /dev/null 2>&1; then
        echo "$TARGET is healthy!"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "ERROR: $TARGET failed health check. Aborting."
        docker-compose -p "$TARGET" -f "docker-compose.$TARGET.yml" down
        exit 1
    fi
    sleep 1
done

# Switch nginx to point at the new slot
echo "upstream api_backend { server 127.0.0.1:$TARGET_PORT; }" \
    | sudo tee "$NGINX_CONF" > /dev/null
sudo nginx -t && sudo systemctl reload nginx

# Record which slot is now active
echo "$TARGET" > "$APP_DIR/.active-slot"

# Stop the old slot after a grace period
echo "Waiting 10s before stopping $CURRENT..."
sleep 10
docker-compose -p "$CURRENT" -f "docker-compose.$CURRENT.yml" stop api

echo "Deployment complete. $TARGET is live on port $TARGET_PORT."
```

Step 2 -- Blue and green compose files (they share the same db/cache network):

```yaml
# docker-compose.blue.yml
version: "3.8"
services:
  api:
    build: .
    ports:
      - "5000:5000"
    environment:
      - DATABASE_URL=postgresql://bloguser:pass@db:5432/blogdb
      - REDIS_URL=redis://cache:6379/0
    networks:
      - shared
    restart: unless-stopped

networks:
  shared:
    external: true
    name: prod_default
```

```yaml
# docker-compose.green.yml
version: "3.8"
services:
  api:
    build: .
    ports:
      - "5001:5000"
    environment:
      - DATABASE_URL=postgresql://bloguser:pass@db:5432/blogdb
      - REDIS_URL=redis://cache:6379/0
    networks:
      - shared
    restart: unless-stopped

networks:
  shared:
    external: true
    name: prod_default
```

Step 3 -- Update nginx to use the upstream config:

```nginx
# /etc/nginx/sites-available/myflaskapp
include /etc/nginx/conf.d/upstream.conf;

server {
    listen 443 ssl;
    server_name yourdomain.com;

    location / {
        proxy_pass http://api_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # SSL config managed by certbot
}
```

Step 4 -- Add a health endpoint to your Flask app:

```python
@app.route('/health')
def health():
    # Verify database connectivity
    try:
        db.session.execute('SELECT 1')
        return {'status': 'healthy'}, 200
    except Exception as e:
        return {'status': 'unhealthy', 'error': str(e)}, 503
```

Run `./blue-green-deploy.sh` and it builds the new version, health-checks it, switches traffic atomically via nginx reload, then stops the old version. Users experience zero downtime because nginx reload is graceful -- existing connections finish on the old backend while new connections go to the new one.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I need to set up database backups for my production PostgreSQL running in Docker. What's the best approach?
Assistant: For PostgreSQL in Docker, use pg_dump to create logical backups. Run it on a schedule with cron, and store backups both locally and in S3. Logical backups with pg_dump are more portable than physical backups for your setup.

User: How often should I back up? And how long should I keep them?
Assistant: For a blog platform, daily full backups with 30-day retention is solid. If you need point-in-time recovery, enable WAL archiving. But for most cases, daily pg_dump is sufficient and much simpler to manage.

[Current message]
User: Show me the backup script and cron setup. I want daily backups stored locally and uploaded to S3, with automatic cleanup of old backups.''',
        "output": r'''Building on the daily backup strategy we discussed, here's a complete backup system for your dockerized PostgreSQL.

Step 1 -- The backup script:

```bash
#!/bin/bash
# /home/deploy/backup.sh
set -euo pipefail

# Configuration
BACKUP_DIR=/home/deploy/backups
S3_BUCKET=s3://your-blog-backups
RETENTION_DAYS=30
DB_CONTAINER=prod-db-1
DB_USER=bloguser
DB_NAME=blogdb
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/blogdb_$DATE.sql.gz"
LOG_FILE="$BACKUP_DIR/backup.log"

mkdir -p "$BACKUP_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log "Starting backup..."

# Create the backup using pg_dump inside the container
docker exec "$DB_CONTAINER" pg_dump \
    -U "$DB_USER" \
    -d "$DB_NAME" \
    --format=plain \
    --no-owner \
    --no-privileges \
    | gzip > "$BACKUP_FILE"

# Verify the backup is not empty
FILESIZE=$(stat -f%z "$BACKUP_FILE" 2>/dev/null || stat --printf="%s" "$BACKUP_FILE")
if [ "$FILESIZE" -lt 1000 ]; then
    log "ERROR: Backup file too small ($FILESIZE bytes). Possible failure."
    exit 1
fi

log "Backup created: $BACKUP_FILE ($FILESIZE bytes)"

# Upload to S3
if command -v aws > /dev/null 2>&1; then
    aws s3 cp "$BACKUP_FILE" "$S3_BUCKET/daily/$(basename $BACKUP_FILE)"
    log "Uploaded to S3: $S3_BUCKET/daily/$(basename $BACKUP_FILE)"
else
    log "WARNING: aws cli not found. Skipping S3 upload."
fi

# Clean up local backups older than retention period
DELETED=$(find "$BACKUP_DIR" -name "blogdb_*.sql.gz" -mtime +"$RETENTION_DAYS" -delete -print | wc -l)
log "Cleaned up $DELETED old local backups"

# Clean up old S3 backups (S3 lifecycle rules are better for this,
# but this works as a fallback)
if command -v aws > /dev/null 2>&1; then
    CUTOFF=$(date -d "-${RETENTION_DAYS} days" +%Y%m%d 2>/dev/null || \
             date -v-${RETENTION_DAYS}d +%Y%m%d)
    aws s3 ls "$S3_BUCKET/daily/" | while read -r line; do
        FILE=$(echo "$line" | awk '{print $4}')
        FILE_DATE=$(echo "$FILE" | grep -o '[0-9]\{8\}')
        if [ -n "$FILE_DATE" ] && [ "$FILE_DATE" -lt "$CUTOFF" ]; then
            aws s3 rm "$S3_BUCKET/daily/$FILE"
            log "Removed old S3 backup: $FILE"
        fi
    done
fi

log "Backup complete."
```

Step 2 -- Restore script (you need this before you need it):

```bash
#!/bin/bash
# /home/deploy/restore.sh
set -euo pipefail

BACKUP_FILE=${1:?"Usage: restore.sh <backup_file.sql.gz>"}
DB_CONTAINER=prod-db-1
DB_USER=bloguser
DB_NAME=blogdb

echo "WARNING: This will overwrite the $DB_NAME database!"
echo "Backup file: $BACKUP_FILE"
read -p "Continue? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Aborted."
    exit 1
fi

# Drop and recreate the database
docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d postgres \
    -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='$DB_NAME' AND pid != pg_backend_pid();"
docker exec "$DB_CONTAINER" dropdb -U "$DB_USER" "$DB_NAME"
docker exec "$DB_CONTAINER" createdb -U "$DB_USER" "$DB_NAME"

# Restore from backup
gunzip -c "$BACKUP_FILE" | docker exec -i "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME"

echo "Restore complete. Verify your data."
```

Step 3 -- Set up cron:

```bash
chmod +x /home/deploy/backup.sh /home/deploy/restore.sh

# Edit crontab for the deploy user
crontab -e

# Add this line -- runs at 3 AM daily
0 3 * * * /home/deploy/backup.sh >> /home/deploy/backups/cron.log 2>&1
```

Step 4 -- Test the backup and restore cycle:

```bash
# Create a backup
./backup.sh

# List backups
ls -lh /home/deploy/backups/

# Test restore on staging (NEVER test on production)
./restore.sh /home/deploy/backups/blogdb_20250306_030000.sql.gz
```

The script validates backup size as a basic integrity check. For extra safety, you can add a periodic restore test that loads the backup into the staging database and runs a query count -- this catches silent corruption that file size checks miss.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My Docker image builds are really slow in CI -- about 8 minutes each. The pip install step takes the longest since I have a lot of dependencies.
Assistant: Several things can speed this up: Docker layer caching (which you already have from the Dockerfile we set up), BuildKit cache mounts, multi-stage builds, and pre-built base images. Let me see your current build times breakdown.

User: The main bottleneck is pip install -- it downloads and compiles numpy, pandas, and some ML libraries every time. Even though requirements.txt hasn't changed, CI doesn't seem to cache the Docker layers.
Assistant: That's because GitHub Actions uses ephemeral runners -- each build gets a fresh machine with no Docker cache. You need to explicitly cache Docker layers using GitHub Actions cache or a registry cache.

[Current message]
User: Show me how to make my Docker builds fast in CI. I want to use BuildKit and proper caching.''',
        "output": r'''Building on the CI pipeline we set up earlier, here's how to dramatically speed up Docker builds using BuildKit cache mounts and registry-based caching.

Step 1 -- Optimize the Dockerfile with BuildKit cache mounts:

```dockerfile
# syntax=docker/dockerfile:1
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --create-home appuser

WORKDIR /app

# Use BuildKit cache mount for pip
# This caches downloaded wheels across builds
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install -r requirements.txt

COPY . .
USER appuser
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "app:app"]
```

Step 2 -- Multi-stage build to separate heavy dependencies:

```dockerfile
# syntax=docker/dockerfile:1

# Stage 1: Install dependencies
FROM python:3.11-slim AS deps
WORKDIR /app
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --prefix=/install -r requirements.txt

# Stage 2: Build the final image
FROM python:3.11-slim AS runtime

RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid 1000 --create-home appuser

WORKDIR /app

# Copy pre-installed packages from deps stage
COPY --from=deps /install /usr/local

COPY . .
USER appuser
EXPOSE 5000
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "app:app"]
```

Step 3 -- Update the GitHub Actions workflow for maximum caching:

```yaml
  build-and-push:
    runs-on: ubuntu-latest
    needs: test
    if: github.ref == 'refs/heads/main' && github.event_name == 'push'

    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-buildx-action@v3

      - uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKER_USERNAME }}
          password: ${{ secrets.DOCKER_TOKEN }}

      - uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: |
            ${{ env.DOCKER_IMAGE }}:latest
            ${{ env.DOCKER_IMAGE }}:${{ github.sha }}
          cache-from: |
            type=registry,ref=${{ env.DOCKER_IMAGE }}:buildcache
          cache-to: |
            type=registry,ref=${{ env.DOCKER_IMAGE }}:buildcache,mode=max
```

The key difference from our earlier workflow is `type=registry` caching instead of `type=gha`. Registry-based caching stores layer cache in Docker Hub alongside your image. Benefits:

- **Persistent** -- survives across CI runs (unlike GHA cache which has size limits)
- **mode=max** -- caches ALL layers including intermediate build stages, not just the final image
- **Shared** -- multiple branches can reuse the same cache

Expected improvement: if requirements.txt has not changed, the pip install step hits cache and takes seconds instead of minutes. Even when requirements change, only changed packages are rebuilt.

For the absolute fastest builds, consider a pre-built base image:

```bash
# Build once, push to registry
docker build -t yourusername/myflaskapp-base:deps -f Dockerfile.deps .
docker push yourusername/myflaskapp-base:deps

# Then your main Dockerfile starts FROM your own base
# Only rebuild the base when requirements.txt changes
```

This takes builds from 8 minutes to under 1 minute in most cases.'''
    },
]
