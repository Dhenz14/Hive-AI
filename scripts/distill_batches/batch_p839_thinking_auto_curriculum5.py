"""Phase 4C: Self-Improvement — Curriculum Design (Part 5)

Designing DevOps and infrastructure learning curricula.
"""

PAIRS = [
    (
        "thinking/auto-curriculum-devops-beginner",
        r'''Design a DevOps learning path for a developer who has only ever deployed by FTPing files to a shared hosting server. They want to learn modern deployment practices.''',
        r'''<think>
Starting from FTP-level knowledge, the progression needs to be:
1. Version control and basic deployment
2. Cloud platforms (managed hosting)
3. Containers (Docker)
4. CI/CD pipelines
5. Infrastructure as code
6. Monitoring and observability

Each step should replace something they currently do manually with something automated. The key is showing immediate value at each step.
</think>

**DevOps Learning Path: From FTP to Modern Deployment**

*Each level replaces a manual step with automation.*

**Level 1: Git-Based Deployment (Week 1-2)**

```
Replace: FTP upload → git push deploys

Goal: Deploy by pushing code, not uploading files.

Week 1: Git essentials
  - Clone, branch, commit, push, merge
  - Pull requests and code review
  - .gitignore (never commit node_modules, .env, uploads)
  - Branching strategy: main = production, feature branches for work

Week 2: Managed platform deployment
  Option A: Heroku (simplest)
    git push heroku main
    → Your app is live at https://yourapp.herokuapp.com

  Option B: Render / Railway
    Connect GitHub repo → auto-deploys on push to main

  What you just automated:
  BEFORE: Edit file → FTP upload → hope nothing breaks
  AFTER:  Edit file → git push → automatic deploy → rollback if needed

Milestone: App deploys automatically on git push.
No more FTP. Rollback is one click.
```

**Level 2: Environment Management (Week 3-4)**

```
Replace: Editing config files on the server → Environment variables

Week 3: Configuration management
  - Environment variables for all configuration
  - .env files for local development
  - Platform environment variables for production
  - NEVER hardcode database URLs, API keys, or secrets

  The three environments:
    Development: your laptop, local database, debug mode on
    Staging:     copy of production, test data, debug mode off
    Production:  real users, real data, debug mode OFF

Week 4: Database management
  - Database migrations (Django migrations, Alembic, Prisma migrate)
  - NEVER modify production database by hand
  - Seed data for development
  - Database backups (automated, daily)

  Workflow:
    1. Write migration code locally
    2. Test on staging database
    3. Deploy to production (migration runs automatically)

Milestone: Three environments (dev, staging, prod) with proper
configuration management. Database changes via migrations only.
```

**Level 3: Docker (Weeks 5-7)**

```
Replace: "It works on my machine" → "It works everywhere"

Week 5: Docker basics
  - What Docker is (packaged environment for your app)
  - Dockerfile: define how to build your app
  - docker build and docker run
  - Your first Dockerfile:
    FROM python:3.11-slim
    WORKDIR /app
    COPY requirements.txt .
    RUN pip install -r requirements.txt
    COPY . .
    CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000"]

Week 6: Docker Compose (multi-container)
  - App + database + Redis in one command
  - docker-compose.yml:
    services:
      app:
        build: .
        ports: ["8000:8000"]
        depends_on: [db, redis]
      db:
        image: postgres:15
        volumes: [pgdata:/var/lib/postgresql/data]
      redis:
        image: redis:7

  - docker compose up → entire stack running locally
  - Matches production environment exactly

Week 7: Docker for production
  - Multi-stage builds (smaller images)
  - Non-root user in container
  - Health checks
  - Logging (stdout/stderr)
  - Deploy Docker to cloud (Render, Railway, or AWS ECS)

Milestone: Application runs in Docker locally and in production.
"It works on my machine" is no longer a problem.
```

**Level 4: CI/CD (Weeks 8-9)**

```
Replace: Manual testing → Automated testing and deployment

Week 8: Continuous Integration
  - GitHub Actions basics
  - Run tests on every push
  - Run linter on every push
  - Block merge if tests fail

  .github/workflows/ci.yml:
    on: [push, pull_request]
    jobs:
      test:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - run: pip install -r requirements.txt
          - run: pytest

Week 9: Continuous Deployment
  - Auto-deploy to staging on push to main
  - Manual approval for production deploy
  - Rollback strategy (redeploy previous version)
  - Database migration in CI/CD pipeline

  Full pipeline:
    Push code → Run tests → Build Docker image → Deploy to staging
    → Manual approval → Deploy to production

Milestone: Code is tested automatically. Deployment is one click
(or automatic). Rollback is instant.
```

**Level 5: Infrastructure as Code (Weeks 10-11)**

```
Replace: Clicking in cloud console → Code that creates infrastructure

Week 10: Terraform basics
  - Declare infrastructure in code
  - terraform plan (see what would change)
  - terraform apply (make the changes)
  - State management

  Example:
    resource "aws_instance" "web" {
      ami           = "ami-0c55b159cbfafe1f0"
      instance_type = "t3.small"
      tags = { Name = "web-server" }
    }

  Benefits:
  - Reproducible (create identical staging and production)
  - Version controlled (git history of infrastructure changes)
  - Reviewable (PR for infrastructure changes)
  - Self-documenting

Week 11: Cloud services
  - Managed database (RDS/Cloud SQL)
  - Managed Redis (ElastiCache)
  - Object storage (S3)
  - Load balancer (ALB)
  - SSL certificates (ACM)

  Architecture in Terraform:
    [ALB] → [ECS Service (2 tasks)] → [RDS PostgreSQL]
                                    → [ElastiCache Redis]
                                    → [S3 for uploads]

Milestone: Entire infrastructure defined in code.
Can recreate the full environment with one command.
```

**Level 6: Monitoring and Observability (Week 12)**

```
Replace: "Is the site up?" (checking manually) → Automated monitoring

1. Uptime monitoring:
   - External checks every minute (UptimeRobot, Pingdom)
   - Alert on Slack/PagerDuty when site is down
   - Status page for users

2. Application monitoring:
   - Error tracking (Sentry)
   - Response time tracking
   - Request volume metrics
   - Database query performance

3. Log management:
   - Centralized logs (CloudWatch, Datadog, or ELK)
   - Structured logging (JSON format)
   - Log-based alerts (error rate spikes)

4. Dashboards:
   - Request rate and response time
   - Error rate
   - CPU/memory usage
   - Database connections and query time
   - Background job queue depth

Milestone: You know when something breaks BEFORE users tell you.
Dashboards show system health at a glance.
```

**The complete transformation:**
| Activity | Before (FTP era) | After (DevOps) |
|----------|-----------------|----------------|
| Deploy | FTP files manually | git push → auto-deploy |
| Test | Manually in browser | Automated test suite in CI |
| Config | Edit files on server | Environment variables |
| Database | Modify via phpMyAdmin | Migrations in code |
| Environment | "Works on my machine" | Docker (identical everywhere) |
| Infrastructure | Click in cloud console | Terraform code |
| Monitoring | "Is it down?" → check | Automated alerts |
| Rollback | Re-FTP old files | One-click redeploy |'''
    ),
    (
        "thinking/auto-curriculum-devops-docker-deep-dive",
        r'''Design a curriculum for going deep on Docker and containers. The developer can write a basic Dockerfile but doesn't understand layers, caching, networking, or production patterns.''',
        r'''<think>
Going from basic Dockerfile knowledge to container expertise requires understanding:
1. How Docker works under the hood (layers, images, filesystem)
2. Optimizing builds (caching, multi-stage, size reduction)
3. Networking and communication between containers
4. Data persistence (volumes, bind mounts)
5. Production patterns (health checks, logging, security)
6. Orchestration basics (Docker Compose, intro to Kubernetes)

Each topic builds understanding needed for the next.
</think>

**Docker Deep Dive Curriculum**

*From "I can write a Dockerfile" to "I understand containers."*

**Module 1: How Docker Actually Works (Week 1)**

```
Goal: Understand layers, images, and the build cache.

1. Image layers:
   Every instruction in a Dockerfile creates a LAYER.
   Layers are cached and shared between images.

   FROM python:3.11-slim     # Layer 1: base image (~120MB)
   COPY requirements.txt .   # Layer 2: just requirements.txt (~1KB)
   RUN pip install -r req..  # Layer 3: installed packages (~50MB)
   COPY . .                  # Layer 4: your application code (~5MB)

   Total image: ~175MB, but layers are shared with other Python images

2. Build cache:
   Docker reuses layers if nothing changed.
   ORDER MATTERS for cache efficiency:

   # BAD: Any code change invalidates pip install
   COPY . .
   RUN pip install -r requirements.txt

   # GOOD: pip install is cached unless requirements.txt changes
   COPY requirements.txt .
   RUN pip install -r requirements.txt
   COPY . .

   Result: Code changes rebuild in 2 seconds instead of 2 minutes.

3. Hands-on exercises:
   - Build an image, check layers with: docker history myimage
   - Change code, rebuild, observe cache hits/misses
   - Reorder Dockerfile instructions, measure build time difference
   - Use docker image inspect to see layer details

Milestone: Can explain why Dockerfile instruction order affects
build time, and can optimize any Dockerfile for caching.
```

**Module 2: Optimizing Docker Images (Week 2)**

```
Goal: Build small, fast, secure images.

1. Multi-stage builds:
   # Stage 1: Build (with all build tools)
   FROM node:18 AS builder
   WORKDIR /app
   COPY package*.json .
   RUN npm ci
   COPY . .
   RUN npm run build

   # Stage 2: Production (minimal, no build tools)
   FROM nginx:alpine
   COPY --from=builder /app/dist /usr/share/nginx/html

   Result: 500MB build image → 25MB production image

2. Base image selection:
   | Base image | Size | Use case |
   |-----------|------|----------|
   | ubuntu:22.04 | 78MB | When you need apt packages |
   | python:3.11 | 920MB | DON'T USE (too big) |
   | python:3.11-slim | 120MB | Default Python choice |
   | python:3.11-alpine | 50MB | Smallest but compilation issues |
   | node:18-slim | 180MB | Default Node choice |
   | gcr.io/distroless/python3 | 50MB | Maximum security (no shell) |

3. Reducing layer size:
   # BAD: Each RUN creates a layer, intermediate files stay
   RUN apt-get update
   RUN apt-get install -y gcc
   RUN pip install -r requirements.txt
   RUN apt-get remove -y gcc

   # GOOD: Single layer, clean up in same layer
   RUN apt-get update && \
       apt-get install -y --no-install-recommends gcc && \
       pip install -r requirements.txt && \
       apt-get purge -y gcc && \
       rm -rf /var/lib/apt/lists/*

4. .dockerignore:
   .git
   node_modules
   __pycache__
   .env
   *.md
   Dockerfile
   docker-compose.yml

Exercises:
   - Optimize an existing image from 1GB to <200MB
   - Use multi-stage builds for a React + Python app
   - Compare build times with and without .dockerignore
```

**Module 3: Networking (Week 3)**

```
Goal: Understand how containers communicate.

1. Docker networks:
   - bridge (default): containers on same host, isolated network
   - host: container shares host network (no isolation)
   - none: no networking

2. Container-to-container communication:
   # docker-compose.yml
   services:
     web:
       build: .
       ports: ["8000:8000"]    # Expose to host
     db:
       image: postgres:15
       # No ports needed — web connects via service name
     redis:
       image: redis:7

   # In your app code:
   DATABASE_URL = "postgresql://user:pass@db:5432/mydb"
   #                                      ^^
   #                     Service name IS the hostname!
   REDIS_URL = "redis://redis:6379"

3. Port mapping:
   ports:
     - "8000:8000"    # host:container
     - "5433:5432"    # Different host port (avoid conflicts)
     - "127.0.0.1:8000:8000"  # Only accessible from localhost

4. DNS and service discovery:
   - Docker Compose creates a DNS entry for each service name
   - Services can reach each other by name: http://web:8000
   - External access only through published ports

Exercises:
   - Set up a 3-service app (web, API, database)
   - Debug connectivity issues with: docker exec web ping db
   - Configure different networks for isolation
```

**Module 4: Data Persistence (Week 4)**

```
Goal: Understand volumes, bind mounts, and data lifecycle.

1. The problem: Container data is ephemeral
   docker run postgres  # Data stored inside container
   docker rm postgres   # ALL DATA GONE

2. Named volumes (production data):
   volumes:
     pgdata:  # Docker manages the storage location

   services:
     db:
       image: postgres:15
       volumes:
         - pgdata:/var/lib/postgresql/data

   # Container removed → data persists in the volume
   docker volume ls        # List volumes
   docker volume inspect pgdata  # See where data is stored

3. Bind mounts (development):
   services:
     web:
       build: .
       volumes:
         - ./src:/app/src    # Host directory → container directory
         # Edit on host, changes appear in container instantly

4. When to use which:
   | Use case | Volume type |
   |----------|-------------|
   | Database data | Named volume |
   | File uploads | Named volume |
   | Development code | Bind mount |
   | Config files | Bind mount or config |
   | Secrets | Docker secrets (not volumes) |

5. Backup and restore:
   # Backup a volume:
   docker run --rm -v pgdata:/data -v $(pwd):/backup alpine \
     tar czf /backup/pgdata-backup.tar.gz -C /data .

   # Restore:
   docker run --rm -v pgdata:/data -v $(pwd):/backup alpine \
     tar xzf /backup/pgdata-backup.tar.gz -C /data

Exercises:
   - Set up PostgreSQL with a persistent volume
   - Remove and recreate the container — verify data survives
   - Set up hot-reload development with bind mounts
   - Backup and restore a database volume
```

**Module 5: Production Patterns (Weeks 5-6)**

```
Week 5: Health checks, logging, and signals

1. Health checks:
   HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
     CMD curl -f http://localhost:8000/health || exit 1

   # Docker monitors container health and can restart unhealthy ones

2. Logging:
   # Write logs to stdout/stderr (Docker captures them)
   import logging
   logging.basicConfig(stream=sys.stdout, level=logging.INFO)

   # View logs:
   docker logs mycontainer
   docker logs --follow --tail 100 mycontainer

3. Graceful shutdown:
   # Your app must handle SIGTERM (Docker sends this on stop)
   import signal
   def shutdown_handler(signum, frame):
       print("Shutting down gracefully...")
       server.shutdown()
       db.close()
   signal.signal(signal.SIGTERM, shutdown_handler)

   # In Dockerfile:
   # Use exec form (not shell form) so signals reach your app:
   CMD ["python", "app.py"]       # GOOD: receives SIGTERM
   # CMD python app.py            # BAD: shell eats SIGTERM

Week 6: Security and resource management

1. Run as non-root:
   RUN adduser --disabled-password --no-create-home appuser
   USER appuser

2. Read-only filesystem:
   docker run --read-only --tmpfs /tmp myapp

3. Resource limits:
   services:
     web:
       deploy:
         resources:
           limits:
             memory: 512M
             cpus: '1.0'

4. Image scanning:
   docker scout cves myimage:latest
   # or: trivy image myimage:latest
```

**Module 6: Docker Compose for Real Projects (Week 7-8)**

```
Complete production-like setup:

docker-compose.yml:
  services:
    web:
      build: .
      ports: ["8000:8000"]
      environment:
        - DATABASE_URL=postgresql://user:pass@db:5432/app
        - REDIS_URL=redis://redis:6379
      depends_on:
        db:
          condition: service_healthy
      healthcheck:
        test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      restart: unless-stopped

    worker:
      build: .
      command: celery -A tasks worker
      depends_on: [redis, db]
      restart: unless-stopped

    db:
      image: postgres:15
      volumes: [pgdata:/var/lib/postgresql/data]
      environment:
        POSTGRES_PASSWORD: ${DB_PASSWORD}
      healthcheck:
        test: ["CMD", "pg_isready"]

    redis:
      image: redis:7-alpine
      volumes: [redisdata:/data]

    nginx:
      image: nginx:alpine
      ports: ["80:80", "443:443"]
      volumes:
        - ./nginx.conf:/etc/nginx/nginx.conf:ro
        - certbot-data:/etc/letsencrypt:ro

  volumes:
    pgdata:
    redisdata:
    certbot-data:

Exercises:
   - Build this complete stack
   - Test failover (kill a container, verify auto-restart)
   - Scale the web service: docker compose up --scale web=3
   - Add monitoring (Prometheus + Grafana containers)
```'''
    ),
    (
        "thinking/auto-curriculum-devops-monitoring",
        r'''Design a learning path for application monitoring and observability. The developer has deployed an app but has no monitoring — they only know something is wrong when users complain.''',
        r'''<think>
Monitoring is about answering: "Is my app healthy? If not, what's wrong?"

The progression should go from simple to comprehensive:
1. Uptime monitoring (is it up?)
2. Error tracking (what's failing?)
3. Metrics (how is it performing?)
4. Logging (what happened?)
5. Alerting (tell me when something's wrong)
6. Dashboards (show me the big picture)

Each level adds visibility that the previous level lacks.
</think>

**Monitoring and Observability Learning Path**

*From "users tell me it's down" to "I know before users notice."*

**Level 0: You Are Here — No Monitoring**

```
Current state:
  - No idea if the app is up or down
  - No idea how many errors are happening
  - No idea how fast (or slow) responses are
  - Learn about problems from user complaints or tweets

This is like driving a car with no dashboard — no speedometer,
no fuel gauge, no warning lights. You find out about problems
when the car stops.
```

**Level 1: Is It Up? — Uptime Monitoring (Day 1)**

```
The simplest possible monitoring. Set up in 10 minutes.

1. External uptime check:
   - UptimeRobot (free, checks every 5 minutes)
   - Pingdom or Better Uptime (more features)
   - Check: GET your homepage, expect 200 OK

2. Add a health check endpoint:
   @app.route('/health')
   def health():
       try:
           db.execute("SELECT 1")
           return {"status": "healthy", "database": "connected"}, 200
       except Exception as e:
           return {"status": "unhealthy", "error": str(e)}, 503

3. Alert on Slack/email/PagerDuty when site goes down.

What you now know:
  - Is the app responding? ✓
  - Is the database connected? ✓
  - How long has it been down? ✓

What you still don't know:
  - What errors are happening
  - How slow responses are
  - What users are experiencing
```

**Level 2: What's Breaking? — Error Tracking (Day 2-3)**

```
Capture every error with context.

1. Set up Sentry (free tier available):
   pip install sentry-sdk

   import sentry_sdk
   sentry_sdk.init(dsn="https://your-dsn@sentry.io/12345")

   # Sentry automatically captures:
   # - Unhandled exceptions with full stack trace
   # - Request context (URL, headers, user)
   # - Environment info (Python version, OS)
   # - Breadcrumbs (what happened before the error)

2. Custom error context:
   with sentry_sdk.push_scope() as scope:
       scope.set_user({"id": user.id, "email": user.email})
       scope.set_tag("feature", "checkout")
       scope.set_context("order", {"id": order.id, "total": order.total})
       # If an error happens here, all this context is attached

3. Error grouping and prioritization:
   - Sentry groups similar errors automatically
   - Shows: frequency, affected users, first/last seen
   - Priority: fix errors that affect the most users first

What you now know:
  - Every error with full context ✓
  - Which errors are most frequent ✓
  - Which users are affected ✓
  - Stack trace for debugging ✓
```

**Level 3: How Fast Is It? — Application Metrics (Week 1-2)**

```
Measure response times, request rates, and resource usage.

1. Application-level metrics with Prometheus:
   pip install prometheus-client

   from prometheus_client import Counter, Histogram, generate_latest

   REQUEST_COUNT = Counter(
       'http_requests_total', 'Total HTTP requests',
       ['method', 'endpoint', 'status']
   )
   REQUEST_DURATION = Histogram(
       'http_request_duration_seconds', 'Request duration',
       ['method', 'endpoint']
   )

   @app.before_request
   def start_timer():
       request._start_time = time.time()

   @app.after_request
   def record_metrics(response):
       duration = time.time() - request._start_time
       REQUEST_COUNT.labels(
           method=request.method,
           endpoint=request.path,
           status=response.status_code
       ).inc()
       REQUEST_DURATION.labels(
           method=request.method,
           endpoint=request.path
       ).observe(duration)
       return response

   @app.route('/metrics')
   def metrics():
       return generate_latest(), 200, {'Content-Type': 'text/plain'}

2. Key metrics to track:
   - Request rate (requests per second)
   - Error rate (5xx responses per second)
   - Response time (p50, p95, p99)
   - Database query time
   - Background job queue depth
   - Memory and CPU usage

3. The RED method (for services):
   - Rate: requests per second
   - Errors: errors per second
   - Duration: response time distribution

   The USE method (for resources):
   - Utilization: % of resource in use
   - Saturation: amount of queued work
   - Errors: error count
```

**Level 4: What Happened? — Structured Logging (Week 2-3)**

```
Logs tell the story of what happened and why.

1. Structured logging (JSON format):
   import structlog
   logger = structlog.get_logger()

   @app.route('/api/orders', methods=['POST'])
   def create_order():
       log = logger.bind(user_id=current_user.id)
       log.info("order_creation_started", items=len(request.json['items']))

       try:
           order = process_order(request.json)
           log.info("order_created", order_id=order.id, total=order.total)
           return jsonify(order)
       except PaymentError as e:
           log.error("payment_failed", error=str(e))
           raise

   # Output:
   # {"event": "order_created", "user_id": 42, "order_id": 789, "total": 99.99, "timestamp": "..."}

2. Log aggregation (centralized):
   - Send logs to CloudWatch, Datadog, or ELK stack
   - Search across all servers: "show me all errors for user_id=42"
   - Correlate logs with request_id across services

3. What to log:
   - DO: Business events, errors, performance, security events
   - DON'T: Passwords, tokens, credit card numbers, PII

4. Log levels:
   DEBUG → detailed troubleshooting (off in production)
   INFO  → normal operations (order created, user logged in)
   WARN  → unexpected but not broken (retry succeeded, cache miss rate high)
   ERROR → something failed (payment error, database timeout)
```

**Level 5: Tell Me When It's Wrong — Alerting (Week 3-4)**

```
Alerts should wake you up for real problems, not noise.

1. Alert on symptoms, not causes:
   GOOD alerts:
   - Error rate > 5% for 5 minutes (users are seeing errors)
   - Response time p95 > 2 seconds for 5 minutes (users are waiting)
   - Health check fails for 2 minutes (site is down)

   BAD alerts:
   - CPU > 80% (might be fine, depends on workload)
   - Single error occurred (errors happen, rate matters)
   - Disk > 70% (not urgent, can wait for business hours)

2. Alert severity:
   PAGE (wake someone up):
   - Site is down
   - Error rate > 10%
   - Data loss risk

   WARN (check during business hours):
   - Error rate > 2%
   - Response time degraded
   - Disk usage > 80%
   - Certificate expiring in 7 days

   INFO (review weekly):
   - Deployment completed
   - Background job retry
   - Unusual traffic pattern

3. Alert fatigue prevention:
   - If an alert fires more than once a day, it's noise — fix or delete it
   - Group related alerts (don't send 100 alerts for one outage)
   - Include runbook link in every alert (what to do when this fires)
   - Auto-resolve when the condition clears

4. On-call setup:
   - Rotation schedule (PagerDuty, Opsgenie)
   - Escalation policy (if no response in 15 min, alert next person)
   - Post-incident review for every page
```

**Level 6: Show Me Everything — Dashboards (Week 4)**

```
Dashboards provide at-a-glance system health.

1. The "Golden Signals" dashboard:
   Row 1: Traffic
   - Requests per second (by endpoint)
   - Active users (if applicable)

   Row 2: Errors
   - Error rate (% of requests returning 5xx)
   - Error count by type

   Row 3: Latency
   - Response time p50, p95, p99
   - Slow endpoints (response time by endpoint)

   Row 4: Saturation
   - CPU and memory usage
   - Database connections (used vs available)
   - Background job queue depth

2. Grafana setup:
   - Connect to Prometheus (metrics source)
   - Import community dashboards (don't build from scratch)
   - Add annotations for deployments (correlate changes with issues)

3. Business metrics dashboard:
   - Signups per hour
   - Orders per hour
   - Revenue (if applicable)
   - Feature usage (which features are popular?)

4. The morning check:
   Every morning, glance at dashboards for 2 minutes:
   - Any error rate spikes overnight?
   - Any latency degradation?
   - Any unusual traffic patterns?
   - Any alerts that fired and auto-resolved?

Milestone: Complete observability stack — uptime monitoring, error
tracking, metrics, logging, alerting, and dashboards. You know
about problems before users do.
```'''
    ),
    (
        "thinking/auto-curriculum-devops-cicd-mastery",
        r'''Design a curriculum for mastering CI/CD pipelines. The developer has a basic GitHub Actions workflow that runs tests, but wants to learn proper pipeline design for a team.''',
        r'''<think>
Going from basic "run tests on push" to a production-grade CI/CD pipeline:

1. Pipeline design principles
2. Testing stages (unit, integration, e2e)
3. Build and artifact management
4. Deployment strategies (blue-green, canary)
5. Pipeline security
6. Advanced patterns (monorepo, matrix builds)

The curriculum should produce a real, deployable pipeline at each stage.
</think>

**CI/CD Mastery Curriculum**

*From "tests run on push" to production-grade deployment pipelines.*

**Phase 1: Pipeline Design Principles (Week 1)**

```
Goal: Understand what a good pipeline looks like.

A good CI/CD pipeline is:
  1. Fast (< 10 minutes for CI, ideally < 5)
  2. Reliable (same result every time, no flaky tests)
  3. Informative (clear what failed and why)
  4. Secure (no secrets exposed, minimal permissions)

Pipeline stages (in order):
  1. Lint → 30 seconds (catch style issues instantly)
  2. Unit tests → 1-3 minutes (catch logic bugs)
  3. Build → 1-2 minutes (verify it compiles/builds)
  4. Integration tests → 3-5 minutes (verify components work together)
  5. Security scan → 1-2 minutes (catch vulnerabilities)
  6. Deploy to staging → 2-3 minutes
  7. E2E tests on staging → 3-5 minutes
  8. Deploy to production → 2-3 minutes (manual approval or auto)

  Total: ~15-25 minutes from push to production

Key principles:
  - Fail fast: cheap checks first (lint before tests)
  - Parallelize: run independent jobs simultaneously
  - Cache: don't reinstall dependencies every run
  - Reproduce: use pinned versions and locked dependencies
```

**Phase 2: Proper Testing Pipeline (Weeks 2-3)**

```
Week 2: Multi-stage testing

  .github/workflows/ci.yml:
    name: CI Pipeline
    on: [push, pull_request]

    jobs:
      lint:
        runs-on: ubuntu-latest
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-python@v5
            with: {python-version: '3.11'}
          - run: pip install ruff
          - run: ruff check .

      unit-tests:
        runs-on: ubuntu-latest
        needs: lint  # Only run if lint passes
        steps:
          - uses: actions/checkout@v4
          - uses: actions/setup-python@v5
            with: {python-version: '3.11'}
          - uses: actions/cache@v4
            with:
              path: ~/.cache/pip
              key: pip-${{ hashFiles('requirements.txt') }}
          - run: pip install -r requirements.txt
          - run: pytest --cov=app --cov-report=xml
          - uses: codecov/codecov-action@v4

      integration-tests:
        runs-on: ubuntu-latest
        needs: unit-tests
        services:
          postgres:
            image: postgres:15
            env: {POSTGRES_PASSWORD: test}
            ports: ['5432:5432']
          redis:
            image: redis:7
            ports: ['6379:6379']
        steps:
          - uses: actions/checkout@v4
          - run: pip install -r requirements.txt
          - run: pytest tests/integration/ -v
            env:
              DATABASE_URL: postgresql://postgres:test@localhost:5432/postgres

Week 3: Caching and parallelization

  Speed optimizations:
  1. Cache dependencies (don't pip install every run)
  2. Run independent test suites in parallel
  3. Use matrix builds for multi-version testing

  Matrix build example:
    strategy:
      matrix:
        python-version: ['3.10', '3.11', '3.12']
        os: [ubuntu-latest, macos-latest]
    runs-on: ${{ matrix.os }}
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pytest

  Test splitting for speed:
    # Split tests across parallel runners
    strategy:
      matrix:
        shard: [1, 2, 3, 4]
    steps:
      - run: pytest --shard-id=${{ matrix.shard }} --num-shards=4

Milestone: Pipeline runs lint, unit tests, and integration tests
in under 10 minutes with proper caching.
```

**Phase 3: Build and Deploy (Weeks 4-5)**

```
Week 4: Docker build pipeline

  build:
    needs: [unit-tests, integration-tests]
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: docker/setup-buildx-action@v3

      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - uses: docker/build-push-action@v5
        with:
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

Week 5: Deployment strategies

  1. Rolling deployment:
     - Replace instances one at a time
     - No downtime, gradual rollout
     - Rollback: deploy previous version

  2. Blue-green deployment:
     - Run new version alongside old version
     - Switch traffic all at once
     - Instant rollback: switch traffic back

  3. Canary deployment:
     - Send 5% of traffic to new version
     - Monitor for errors
     - Gradually increase to 100%
     - Rollback: route all traffic to old version

  GitHub Actions deployment:
    deploy-staging:
      needs: build
      runs-on: ubuntu-latest
      environment: staging
      steps:
        - run: |
            aws ecs update-service \
              --cluster staging \
              --service web \
              --force-new-deployment

    deploy-production:
      needs: deploy-staging
      runs-on: ubuntu-latest
      environment:
        name: production
        url: https://myapp.com
      steps:
        - run: |
            aws ecs update-service \
              --cluster production \
              --service web \
              --force-new-deployment

  The 'environment: production' setting in GitHub requires manual
  approval before the job runs.
```

**Phase 4: Advanced Patterns (Weeks 6-7)**

```
Week 6: Pipeline security

  1. Secret management:
     - Use GitHub Secrets for credentials
     - Use OIDC for cloud provider auth (no long-lived keys)
     - Never echo secrets in logs

  2. Dependency pinning:
     - Pin action versions to SHA (not tags)
     - Lock file for dependencies (package-lock.json, Pipfile.lock)
     - Dependabot for automated updates

  3. Least privilege:
     permissions:
       contents: read
       packages: write
       # Only grant what's needed

  4. Security scanning in pipeline:
     - Dependency audit (pip audit, npm audit)
     - Container image scanning (trivy)
     - Static analysis (bandit, semgrep)
     - Secret detection (gitleaks)

Week 7: Reusable workflows and advanced patterns

  1. Reusable workflows (DRY for CI/CD):
     # .github/workflows/reusable-deploy.yml
     on:
       workflow_call:
         inputs:
           environment:
             required: true
             type: string

     # Called from other workflows:
     deploy:
       uses: ./.github/workflows/reusable-deploy.yml
       with:
         environment: production

  2. Conditional deployments:
     # Only deploy from main branch:
     if: github.ref == 'refs/heads/main'

     # Only run E2E tests on PRs to main:
     if: github.event_name == 'pull_request' && github.base_ref == 'main'

  3. Notifications:
     - Slack notification on deploy success/failure
     - PR comment with test results and coverage
     - Deploy annotations in monitoring dashboards

Milestone: Production-grade CI/CD pipeline with security scanning,
multiple environments, deployment strategies, and team notifications.
```

**Phase 5: Pipeline Operations (Week 8)**

```
Maintain and improve the pipeline over time:

1. Pipeline metrics:
   - Track: build time, success rate, deploy frequency
   - Goal: < 10 min build, > 95% success, daily deploys
   - Alert if build time increases >20%

2. Flaky test management:
   - Quarantine flaky tests (don't block pipeline, but track)
   - Fix or delete quarantined tests within 1 week
   - Never ignore flaky tests long-term

3. Pipeline as code:
   - All pipeline config in version control
   - Changes to pipeline go through PR review
   - Document pipeline architecture for onboarding

4. DORA metrics (measure team performance):
   - Deployment frequency (how often you deploy)
   - Lead time for changes (commit to production)
   - Change failure rate (% of deploys that cause issues)
   - Mean time to recovery (how fast you fix issues)

   Elite: Deploy multiple times per day, < 1 hour lead time,
   < 5% failure rate, < 1 hour recovery time.
```'''
    ),
    (
        "thinking/auto-curriculum-devops-cloud-fundamentals",
        r'''A developer needs to learn cloud infrastructure (AWS specifically) but is overwhelmed by the number of services. Design a focused curriculum that covers only what they need to deploy and run a web application.''',
        r'''<think>
AWS has 200+ services. A web developer needs maybe 10-15 of them. The curriculum should filter aggressively and teach only what's needed.

Core services for a web app:
1. Compute: EC2 or ECS (run your app)
2. Database: RDS (managed PostgreSQL)
3. Storage: S3 (files and static assets)
4. Networking: VPC, ALB (load balancer)
5. DNS: Route 53
6. CDN: CloudFront
7. Secrets: Secrets Manager
8. Monitoring: CloudWatch
9. CI/CD: ECR (container registry)

Everything else can wait until specifically needed.
</think>

**AWS for Web Developers — The Essential 10 Services**

*Ignore the other 190+ services until you need them.*

**The Only Services You Need (and when):**

```
Must learn immediately:
  1. EC2 or ECS    → Run your application
  2. RDS           → Managed database
  3. S3            → File storage
  4. ALB           → Load balancer
  5. Route 53      → Domain and DNS
  6. IAM           → Security and access

Learn when you need them:
  7. CloudFront    → CDN (when you need global speed)
  8. ElastiCache   → Redis/Memcached (when you need caching)
  9. SQS/SNS       → Message queues (when you need async)
  10. CloudWatch   → Monitoring (set up from day 1)

Ignore until specifically needed:
  Lambda, DynamoDB, Kinesis, Redshift, SageMaker,
  and the other 180+ services
```

**Week 1: Your First AWS Deployment**

```
Goal: Get your app running on AWS.

Day 1-2: AWS account setup
  - Create account with MFA on root
  - Create IAM user for daily use (never use root)
  - Set up billing alerts ($5, $20, $50 thresholds)
  - Install AWS CLI

Day 3-4: EC2 basics (or ECS with Fargate)
  Option A — EC2 (virtual server):
    - Launch an instance (t3.small, Ubuntu)
    - SSH in, install your app
    - Open port 80/443 in security group
    - Your app is live at the public IP

  Option B — ECS Fargate (containers, recommended):
    - Push Docker image to ECR
    - Create ECS service with Fargate
    - Map to a load balancer
    - No servers to manage

Day 5: RDS (managed database)
  - Launch PostgreSQL on RDS
  - Put it in a private subnet (no public access)
  - Connect from your app via private network
  - Enable automated backups

Milestone: Application running on AWS with managed database.
```

**Week 2: Production Readiness**

```
Day 1: Load Balancer (ALB)
  - Create Application Load Balancer
  - Point it to your app instances
  - Add HTTPS with ACM certificate (free!)
  - Health checks to remove unhealthy instances

Day 2: Domain and DNS (Route 53)
  - Register domain or transfer DNS
  - Create A record pointing to ALB
  - Set up www redirect
  - Your app is live at https://yourdomain.com

Day 3: S3 for file storage
  - Create bucket for user uploads
  - Configure CORS for browser uploads
  - Set up IAM role for app access (not access keys)
  - Enable versioning and lifecycle rules

Day 4-5: Security review
  - VPC: app in private subnet, ALB in public
  - Security groups: minimal open ports
  - IAM: app has its own role with minimum permissions
  - RDS: no public access, encrypted at rest
  - S3: block public access, use signed URLs

Milestone: Production-ready deployment with HTTPS, custom domain,
file storage, and proper security.
```

**Week 3: Monitoring and Operations**

```
Day 1-2: CloudWatch
  - Application logs sent to CloudWatch Logs
  - Metrics: CPU, memory, request count
  - Alarms: notify on high error rate, CPU > 80%
  - Dashboard: key metrics at a glance

Day 3: Auto-scaling
  - Scale ECS tasks based on CPU or request count
  - Minimum 2 tasks for high availability
  - Maximum based on budget
  - Scale-in cooldown to prevent thrashing

Day 4-5: Backup and disaster recovery
  - RDS: automated daily backups, 7-day retention
  - S3: versioning enabled, cross-region replication optional
  - Test restore process (don't just hope backups work)
  - Document recovery procedures

Milestone: Monitored, auto-scaling, backed-up application.
```

**Week 4: Cost Optimization**

```
AWS can get expensive fast. Learn to control costs.

1. Right-sizing:
   - Start small (t3.small), upgrade only if metrics show need
   - Use Graviton instances (arm64) for 20% cost savings
   - Reserved instances for predictable workloads (up to 72% savings)

2. Storage costs:
   - S3 lifecycle rules: move old data to cheaper tiers
   - Delete unused EBS volumes and snapshots
   - RDS: right-size instance, delete old snapshots

3. Cost monitoring:
   - AWS Cost Explorer: see where money goes
   - Budgets: alert at spending thresholds
   - Tag resources by project for cost allocation

4. Cost reference for a typical web app:
   | Service | Monthly cost |
   |---------|-------------|
   | ECS Fargate (2 tasks, 0.5 vCPU) | ~$30 |
   | RDS PostgreSQL (db.t3.micro) | ~$15 |
   | ALB | ~$20 |
   | S3 (10GB) | ~$0.25 |
   | CloudWatch | ~$5 |
   | Route 53 | ~$1 |
   | Total | ~$70/month |

   This handles thousands of users comfortably.

Milestone: Understand AWS costs and have controls in place
to prevent surprise bills.
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
