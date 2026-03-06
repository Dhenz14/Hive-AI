"""Thinking-trace pairs: real-world DevOps tasks with vague requests."""

PAIRS = [
    (
        "thinking/practical",
        r'''our docker image is 2.3GB and takes forever to build''',
        r'''<think>
A 2.3GB Docker image is extremely bloated. Let me think about what could cause this...

It could be a fat base image, but wait -- even ubuntu:22.04 is only ~75MB, so the base image alone does not explain 2.3GB. There must be multiple compounding issues. Let me enumerate them:

1. Using a fat base image (ubuntu/debian instead of Alpine or distroless) -- contributes maybe 50-100MB
2. Not using multi-stage builds -- this is probably the biggest contributor, because build tools, compilers, and dev dependencies all stay in the final image. A C compiler plus headers can easily add 500MB+.
3. Poor layer caching (COPY . . before installing dependencies, so every code change reinstalls everything) -- this does not affect image size directly, but makes builds painfully slow
4. Not cleaning up package manager caches (apt cache, pip cache, npm cache) -- hmm, actually this can be huge. The apt cache alone can be 200-400MB after installing packages.
5. Including unnecessary files (.git, node_modules, __pycache__, test files) -- .git for a large repo can be gigabytes
6. Installing dev dependencies in production image

For a typical Python web app, the image should be 100-200MB. For a Node.js app, 150-300MB. For a Go app, 10-30MB. So 2.3GB is 10-20x larger than it needs to be.

I initially considered suggesting just switching to Alpine, but actually Alpine uses musl libc which causes subtle compatibility issues with some Python packages (numpy, pandas, etc.) that expect glibc. Therefore the safer recommendation is python:3.x-slim, which is Debian-based but strips out unnecessary packages.

The fix involves:
1. Multi-stage build: build stage has all tools, final stage only has runtime
2. Slim base images (not Alpine unless they are sure their dependencies work with musl)
3. Proper layer ordering for cache efficiency (copy dependency files first, install, then copy code)
4. .dockerignore to exclude unnecessary files
5. Clean up caches in the same layer as the install -- this is critical because Docker layers are immutable, so deleting in a later layer does not reclaim space

I will assume a Python web app since that is most common for this question, but the principles apply to any language.
</think>

A 2.3GB image usually means a fat base image + no multi-stage build + poor layer caching. Here is how to shrink it to ~150MB and make builds fast.

**The typical bloated Dockerfile (before):**

```dockerfile
# PROBLEM 1: Full Ubuntu is 75MB base, plus apt installs add hundreds of MB
FROM ubuntu:22.04

# PROBLEM 2: Installing build tools that are not needed at runtime
RUN apt-get update && apt-get install -y \
    python3 python3-pip python3-dev \
    gcc g++ make \
    libpq-dev libffi-dev \
    curl wget git

WORKDIR /app

# PROBLEM 3: Copying everything first means any code change invalidates
# the dependency install cache layer
COPY . .

# PROBLEM 4: pip cache stays in the image
RUN pip3 install -r requirements.txt

# PROBLEM 5: Dev dependencies installed in production
RUN pip3 install pytest black flake8 mypy

EXPOSE 8000
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0"]
```

**The optimized Dockerfile (after):**

```dockerfile
# ============================================
# Stage 1: Build stage
# Has all the compilers and build tools.
# This stage is NOT included in the final image.
# ============================================
FROM python:3.12-slim AS builder

# Install build dependencies (only needed to compile C extensions)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy ONLY dependency files first.
# This layer is cached as long as requirements.txt does not change.
# Code changes do NOT invalidate this layer.
COPY requirements.txt .

# Install dependencies into a virtual environment.
# --no-cache-dir prevents pip from storing downloaded packages.
# Using a venv makes it easy to copy just the installed packages.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir -r requirements.txt

# ============================================
# Stage 2: Production stage
# Only has the Python runtime and installed packages.
# No compilers, no build tools, no caches.
# ============================================
FROM python:3.12-slim AS production

# Install only runtime dependencies (not build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser

WORKDIR /app

# Copy the virtual environment from the build stage
# This brings the installed packages WITHOUT pip cache or build tools
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code (separate layer so code changes are fast)
COPY --chown=appuser:appuser ./app ./app
COPY --chown=appuser:appuser ./alembic ./alembic
COPY --chown=appuser:appuser alembic.ini .

# Switch to non-root user
USER appuser

# Health check so orchestrators can detect unhealthy containers
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

EXPOSE 8000

# Use exec form (not shell form) so signals are handled properly
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
```

**The .dockerignore file (critical -- keeps garbage out):**

```
# .dockerignore
.git
.gitignore
.github
.vscode
.idea

# Python artifacts
__pycache__
*.pyc
*.pyo
*.egg-info
.pytest_cache
.mypy_cache
.coverage
htmlcov

# Virtual environments
.venv
venv
env

# Node (if any frontend)
node_modules
.next

# Docker
Dockerfile
docker-compose*.yml
.dockerignore

# Documentation and tests
docs
tests
*.md
LICENSE

# OS files
.DS_Store
Thumbs.db

# Environment files (secrets should come from env vars or secrets manager)
.env
.env.*
```

**Layer caching optimization for CI/CD:**

```yaml
# GitHub Actions example with Docker layer caching
name: Build and Push

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ghcr.io/${{ github.repository }}:${{ github.sha }}
          # Cache layers in the registry itself
          cache-from: type=registry,ref=ghcr.io/${{ github.repository }}:buildcache
          cache-to: type=registry,ref=ghcr.io/${{ github.repository }}:buildcache,mode=max
```

**Size comparison:**

| Approach | Image size | Build time (cold) | Build time (code change only) |
|---|---|---|---|
| Original (Ubuntu + no multi-stage) | 2.3 GB | 5-8 min | 5-8 min (no caching) |
| Multi-stage + slim | ~180 MB | 2-3 min | ~15 sec (deps cached) |
| Multi-stage + Alpine | ~120 MB | 2-3 min | ~15 sec |
| Distroless (if no shell needed) | ~90 MB | 2-3 min | ~15 sec |

**Quick wins to check immediately:**

```bash
# See what is taking up space in your image
docker history your-image:latest --human --no-trunc

# Use dive for an interactive layer explorer
# (shows which files are in each layer)
docker run --rm -it -v /var/run/docker.sock:/var/run/docker.sock wagoodman/dive your-image:latest
```

The key insight: the final production image should contain ONLY the runtime, your code, and installed packages. Everything else -- compilers, build tools, package manager caches, source control history -- belongs in the build stage and gets thrown away.'''),
    (
        "thinking/practical",
        r'''set up CI/CD for our Python project, we use GitHub''',
        r'''<think>
The user wants CI/CD for a Python project on GitHub. They did not specify a lot of important details:
- What kind of project (web app, library, CLI tool?)
- What they want to deploy to (AWS, GCP, Heroku, Docker registry?)
- What testing framework they use
- What Python versions to support
- Whether they have existing tests, linting, etc.

I could ask for clarification, but actually a good CI/CD setup for Python is 80% the same regardless of specifics. Let me make reasonable assumptions for a typical Python web project and note where they would customize.

My initial thought was to put everything in one big workflow job, but wait -- that is a common anti-pattern. If linting fails, you do not need to wait for the test matrix to finish. Therefore I should use separate jobs that can run in parallel and fail independently.

I will include:
- Test with pytest across multiple Python versions
- Lint with ruff (modern, fast, replaces flake8+isort+pyupgrade) -- I considered recommending flake8 but ruff is strictly better now: faster, more rules, single tool
- Type check with mypy
- Security scan dependencies
- Build and push Docker image
- Deploy to staging on PR merge, production on release tag

The workflow should:
1. Be fast (use caching aggressively -- because a slow CI pipeline means developers stop running it)
2. Run tests in parallel where possible
3. Fail fast (lint first since it is fastest, typically under 5 seconds)
4. Have separate jobs for different concerns (not one giant job)
5. Use GitHub environments for deployment protection
6. Include dependency caching for pip

Hmm, I also need to handle the Python version matrix carefully. Testing on 3.9-3.12 is reasonable, but 3.8 is EOL so I should not include it even though some teams still use it.

I will provide a complete, production-ready workflow that they can customize.
</think>

Here is a complete CI/CD setup for a Python project. It covers testing, linting, security scanning, building, and deploying with proper caching to keep it fast.

**.github/workflows/ci.yml -- Main CI pipeline:**

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

# Cancel in-progress runs for the same branch/PR
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

env:
  PYTHON_DEFAULT: "3.12"

jobs:
  # ======================================
  # Job 1: Lint (fastest, runs first)
  # ======================================
  lint:
    name: Lint & Format
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_DEFAULT }}

      - name: Install ruff
        run: pip install ruff

      - name: Check formatting
        run: ruff format --check .

      - name: Check linting
        run: ruff check .

  # ======================================
  # Job 2: Type checking
  # ======================================
  typecheck:
    name: Type Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_DEFAULT }}
          cache: pip

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install mypy

      - name: Run mypy
        run: mypy app/ --ignore-missing-imports

  # ======================================
  # Job 3: Tests (matrix across Python versions)
  # ======================================
  test:
    name: Test (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    needs: [lint]  # only run tests if lint passes

    strategy:
      fail-fast: false  # run all versions even if one fails
      matrix:
        python-version: ["3.10", "3.11", "3.12"]

    services:
      # Spin up PostgreSQL for integration tests
      postgres:
        image: postgres:16
        env:
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
          POSTGRES_DB: testdb
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

      # Redis for caching tests
      redis:
        image: redis:7
        ports:
          - 6379:6379
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip

      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install -r requirements-dev.txt

      - name: Run tests
        env:
          DATABASE_URL: postgresql://test:test@localhost:5432/testdb
          REDIS_URL: redis://localhost:6379/0
          ENVIRONMENT: test
        run: |
          pytest tests/ \
            -v \
            --tb=short \
            --cov=app \
            --cov-report=xml \
            --cov-report=term-missing \
            -n auto  # parallel execution with pytest-xdist

      - name: Upload coverage
        if: matrix.python-version == '3.12'
        uses: codecov/codecov-action@v4
        with:
          file: coverage.xml
          token: ${{ secrets.CODECOV_TOKEN }}

  # ======================================
  # Job 4: Security scan
  # ======================================
  security:
    name: Security Scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: ${{ env.PYTHON_DEFAULT }}

      - name: Check dependencies for vulnerabilities
        run: |
          pip install pip-audit
          pip-audit -r requirements.txt

      - name: Check for secrets in code
        uses: trufflesecurity/trufflehog@main
        with:
          extra_args: --only-verified

  # ======================================
  # Job 5: Build Docker image
  # ======================================
  build:
    name: Build Docker Image
    runs-on: ubuntu-latest
    needs: [test, typecheck, security]
    if: github.event_name == 'push'  # only build on push, not PRs

    permissions:
      packages: write
      contents: read

    outputs:
      image_tag: ${{ steps.meta.outputs.tags }}

    steps:
      - uses: actions/checkout@v4

      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v3

      - name: Login to GitHub Container Registry
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ghcr.io/${{ github.repository }}
          tags: |
            type=sha,prefix=
            type=ref,event=branch
            type=semver,pattern={{version}}

      - name: Build and push
        uses: docker/build-push-action@v5
        with:
          context: .
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          labels: ${{ steps.meta.outputs.labels }}
          cache-from: type=gha
          cache-to: type=gha,mode=max

  # ======================================
  # Job 6: Deploy to staging
  # ======================================
  deploy-staging:
    name: Deploy to Staging
    runs-on: ubuntu-latest
    needs: [build]
    if: github.ref == 'refs/heads/main'
    environment:
      name: staging
      url: https://staging.myapp.com

    steps:
      - uses: actions/checkout@v4

      - name: Deploy to staging
        env:
          DEPLOY_KEY: ${{ secrets.STAGING_DEPLOY_KEY }}
        run: |
          # Replace with your actual deploy command
          # Examples:
          # kubectl set image deployment/myapp myapp=ghcr.io/${{ github.repository }}:${{ github.sha }}
          # aws ecs update-service --cluster staging --service myapp --force-new-deployment
          echo "Deploying ${{ github.sha }} to staging"
```

**.github/workflows/release.yml -- Production releases:**

```yaml
name: Release

on:
  release:
    types: [published]

jobs:
  deploy-production:
    name: Deploy to Production
    runs-on: ubuntu-latest
    environment:
      name: production
      url: https://myapp.com

    steps:
      - uses: actions/checkout@v4

      - name: Verify image exists
        run: |
          docker manifest inspect ghcr.io/${{ github.repository }}:${{ github.event.release.tag_name }} \
            || (echo "Image not found for tag ${{ github.event.release.tag_name }}" && exit 1)

      - name: Deploy to production
        env:
          DEPLOY_KEY: ${{ secrets.PRODUCTION_DEPLOY_KEY }}
        run: |
          echo "Deploying ${{ github.event.release.tag_name }} to production"
          # Your deploy command here
```

**Recommended project structure:**

```
myproject/
    .github/
        workflows/
            ci.yml
            release.yml
    app/
        __init__.py
        main.py
        ...
    tests/
        __init__.py
        conftest.py      # shared fixtures
        test_api.py
        test_models.py
    requirements.txt      # production dependencies
    requirements-dev.txt  # test/dev dependencies
    Dockerfile
    .dockerignore
    pyproject.toml        # ruff, mypy, pytest config
```

**pyproject.toml (tool configuration):**

```toml
[tool.ruff]
target-version = "py310"
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "N", "W", "UP", "B", "SIM"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v --tb=short"

[tool.mypy]
python_version = "3.12"
warn_return_any = true
warn_unused_configs = true

[tool.coverage.run]
source = ["app"]
omit = ["tests/*"]
```

**Pipeline flow:**

```
Push to PR:     lint -> test (3.10, 3.11, 3.12) + typecheck + security
Push to main:   lint -> test + typecheck + security -> build image -> deploy staging
Create release: deploy production (uses image already built)
```

The key design choices: lint runs first because it is fastest and catches most issues. Tests run in parallel across Python versions. Security scanning runs alongside tests (not blocking). Docker build only happens after all checks pass. Production deploys require a GitHub Release (manual gate).'''),
    (
        "thinking/practical",
        r'''our app crashes in production but works fine locally''',
        r'''<think>
"Works locally, crashes in production" is one of the most common and frustrating problems. The root cause is almost always an environment difference, but which difference? That is the hard part.

My first instinct is "it is probably a missing env var" -- but actually, let me think more carefully. Missing env vars usually cause immediate crashes on startup, not subtle failures. If it "crashes" (not "fails to start"), the cause might be more nuanced.

Let me rank the likely causes:

1. Environment variables missing or different
   - Database URL, API keys, secrets not set in production
   - Different config values (DEBUG=True locally hides errors) -- wait, this is a sneaky one. In many frameworks, DEBUG mode catches exceptions and shows a nice error page, while production mode lets them propagate as 500 errors

2. Resource constraints
   - Production has less memory than dev machine (containerized with limits)
   - CPU limits causing timeouts
   - Disk space full

3. Network differences
   - Services on different hosts (not localhost)
   - DNS resolution differences
   - Firewall rules blocking connections
   - TLS/SSL certificate issues -- hmm, this one is very common. Local dev often skips TLS verification

4. Dependency differences
   - Different Python/Node/runtime version
   - System libraries missing (libpq, libc, etc.)
   - pip install without pinned versions -> different package versions. I have seen this cause production crashes weeks after the last deploy, because a transitive dependency released a breaking change

5. Data differences
   - Production data has edge cases that dev data does not
   - Encoding issues (UTF-8 data that ASCII-only local data does not have)
   - Scale issues (works with 100 rows, crashes with 10M rows)

6. File system differences
   - Read-only file system in container -- actually this is more common than people think, many container runtimes default to read-only root filesystem
   - Different paths (/tmp, /var, etc.)
   - Missing directories

7. Permissions
   - Running as non-root in production (as it should)
   - File ownership issues

I considered just listing these causes, but that is not very helpful. The user needs a systematic diagnostic approach -- a checklist they can follow to narrow down the problem. I should also give preventive measures, because the real fix is making the production environment observable so you can actually see what is happening before it crashes.
</think>

"Works locally, crashes in production" is always caused by an environment difference. Here is a systematic approach to find and fix the problem, plus preventive measures so it does not happen again.

**Step 1: Add diagnostic endpoints and startup checks**

```python
# diagnostic.py -- Add to your app for production debugging

import os
import sys
import platform
import socket
import importlib.metadata
from datetime import datetime
from typing import Optional

import psutil  # pip install psutil


class EnvironmentDiagnostic:
    """Collects diagnostic info about the running environment.

    Add this to your app's health check endpoint so you can compare
    production vs local environments side by side.
    """

    @staticmethod
    def collect() -> dict:
        """Gather comprehensive environment information."""
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "hostname": socket.gethostname(),
            "python": {
                "version": sys.version,
                "executable": sys.executable,
                "platform": platform.platform(),
                "arch": platform.machine(),
            },
            "resources": {
                "memory_total_mb": psutil.virtual_memory().total // (1024 * 1024),
                "memory_available_mb": psutil.virtual_memory().available // (1024 * 1024),
                "memory_percent_used": psutil.virtual_memory().percent,
                "cpu_count": os.cpu_count(),
                "disk_free_gb": round(
                    psutil.disk_usage("/").free / (1024 ** 3), 1
                ),
            },
            "environment": {
                # Check critical env vars exist (do NOT log their values)
                "DATABASE_URL": "set" if os.environ.get("DATABASE_URL") else "MISSING",
                "REDIS_URL": "set" if os.environ.get("REDIS_URL") else "MISSING",
                "SECRET_KEY": "set" if os.environ.get("SECRET_KEY") else "MISSING",
                "DEBUG": os.environ.get("DEBUG", "not set"),
                "ENVIRONMENT": os.environ.get("ENVIRONMENT", "not set"),
            },
            "network": EnvironmentDiagnostic._check_connectivity(),
            "packages": EnvironmentDiagnostic._get_package_versions(),
            "writable_paths": EnvironmentDiagnostic._check_paths(),
        }

    @staticmethod
    def _check_connectivity() -> dict:
        """Test connectivity to critical services."""
        checks = {}

        # Database
        db_url = os.environ.get("DATABASE_URL", "")
        if db_url:
            try:
                # Parse host from URL
                from urllib.parse import urlparse
                parsed = urlparse(db_url)
                host = parsed.hostname or "localhost"
                port = parsed.port or 5432
                sock = socket.create_connection((host, port), timeout=5)
                sock.close()
                checks["database"] = f"reachable ({host}:{port})"
            except Exception as exc:
                checks["database"] = f"UNREACHABLE: {exc}"
        else:
            checks["database"] = "NOT CONFIGURED"

        # Redis
        redis_url = os.environ.get("REDIS_URL", "")
        if redis_url:
            try:
                from urllib.parse import urlparse
                parsed = urlparse(redis_url)
                host = parsed.hostname or "localhost"
                port = parsed.port or 6379
                sock = socket.create_connection((host, port), timeout=5)
                sock.close()
                checks["redis"] = f"reachable ({host}:{port})"
            except Exception as exc:
                checks["redis"] = f"UNREACHABLE: {exc}"

        # DNS resolution
        try:
            socket.getaddrinfo("dns.google", 443, socket.AF_INET)
            checks["dns"] = "working"
        except Exception as exc:
            checks["dns"] = f"FAILED: {exc}"

        return checks

    @staticmethod
    def _get_package_versions() -> dict:
        """Get installed package versions for comparison with local."""
        critical_packages = [
            "fastapi", "uvicorn", "sqlalchemy", "psycopg2-binary",
            "pydantic", "redis", "celery", "requests", "httpx",
        ]
        versions = {}
        for pkg in critical_packages:
            try:
                versions[pkg] = importlib.metadata.version(pkg)
            except importlib.metadata.PackageNotFoundError:
                versions[pkg] = "NOT INSTALLED"
        return versions

    @staticmethod
    def _check_paths() -> dict:
        """Check if expected paths exist and are writable."""
        paths_to_check = ["/tmp", "/app", "/app/logs", "/app/uploads"]
        results = {}
        for path in paths_to_check:
            if os.path.exists(path):
                results[path] = "writable" if os.access(path, os.W_OK) else "READ-ONLY"
            else:
                results[path] = "DOES NOT EXIST"
        return results
```

**Step 2: Add structured logging with context**

```python
# logging_config.py -- Structured logging for production

import logging
import json
import sys
import traceback
from datetime import datetime


class JSONFormatter(logging.Formatter):
    """JSON log formatter for production.

    Structured logs are searchable in log aggregation tools
    (CloudWatch, Datadog, ELK, etc.) unlike plain text.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Include exception info if present
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else None,
                "message": str(record.exc_info[1]) if record.exc_info[1] else None,
                "traceback": traceback.format_exception(*record.exc_info),
            }

        # Include extra fields
        for key in ["request_id", "user_id", "endpoint", "method", "status_code"]:
            if hasattr(record, key):
                log_entry[key] = getattr(record, key)

        return json.dumps(log_entry, default=str)


def configure_logging(level: str = "INFO"):
    """Set up structured JSON logging for production."""
    import os
    env = os.environ.get("ENVIRONMENT", "development")

    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    handler = logging.StreamHandler(sys.stdout)

    if env == "production":
        handler.setFormatter(JSONFormatter())
    else:
        # Human-readable format for local development
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s %(name)s:%(lineno)d  %(message)s"
        ))

    root_logger.addHandler(handler)

    # Quiet down noisy libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
```

**Step 3: Startup validation (fail fast with clear errors)**

```python
# startup_checks.py -- Run before the app starts accepting traffic

import os
import sys
import logging

logger = logging.getLogger(__name__)


class StartupError(Exception):
    """Raised when a critical startup check fails."""
    pass


def validate_environment():
    """Check that all required configuration is present.

    Call this BEFORE starting the web server. Better to fail immediately
    with a clear error than to start serving and crash on the first request.
    """
    errors = []

    # Required environment variables
    required_vars = [
        "DATABASE_URL",
        "SECRET_KEY",
    ]
    for var in required_vars:
        if not os.environ.get(var):
            errors.append(f"Missing required environment variable: {var}")

    # Check SECRET_KEY is not the default
    secret = os.environ.get("SECRET_KEY", "")
    if secret in ("changeme", "secret", "dev-secret", ""):
        errors.append("SECRET_KEY is set to a default/weak value")

    if errors:
        for err in errors:
            logger.error("Startup check failed: %s", err)
        raise StartupError(
            f"{len(errors)} startup check(s) failed:\n" + "\n".join(f"  - {e}" for e in errors)
        )

    logger.info("All startup checks passed")


def validate_database():
    """Verify database is reachable and schema is up to date."""
    import sqlalchemy

    db_url = os.environ.get("DATABASE_URL", "")
    try:
        engine = sqlalchemy.create_engine(db_url)
        with engine.connect() as conn:
            result = conn.execute(sqlalchemy.text("SELECT 1"))
            result.fetchone()
        logger.info("Database connection verified")
    except Exception as exc:
        raise StartupError(f"Cannot connect to database: {exc}") from exc


def validate_redis():
    """Verify Redis is reachable."""
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        logger.warning("REDIS_URL not set -- caching disabled")
        return

    try:
        import redis
        r = redis.from_url(redis_url, socket_timeout=5)
        r.ping()
        logger.info("Redis connection verified")
    except Exception as exc:
        raise StartupError(f"Cannot connect to Redis: {exc}") from exc


def run_all_checks():
    """Run all startup validations. Fails fast with clear error messages."""
    try:
        validate_environment()
        validate_database()
        validate_redis()
        logger.info("All startup checks passed -- ready to serve traffic")
    except StartupError as exc:
        logger.critical("APPLICATION CANNOT START: %s", exc)
        sys.exit(1)


# In your app's entry point:
# from startup_checks import run_all_checks
# run_all_checks()
# app = create_app()
```

**Step 4: Docker health check and graceful shutdown**

```python
# health.py -- Health check endpoint

from fastapi import APIRouter, Response
from diagnostic import EnvironmentDiagnostic

router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check -- used by load balancers and orchestrators."""
    return {"status": "healthy"}


@router.get("/health/detailed")
async def detailed_health():
    """Detailed diagnostic info -- protect this endpoint in production."""
    return EnvironmentDiagnostic.collect()


@router.get("/ready")
async def readiness_check(db=Depends(get_db)):
    """Readiness check -- verifies the app can actually serve requests.

    Kubernetes uses this to decide whether to send traffic.
    Unlike /health (is the process alive?), /ready means
    'can this instance handle requests right now?'
    """
    try:
        # Verify database is responding
        await db.execute("SELECT 1")
        return {"status": "ready"}
    except Exception as exc:
        return Response(
            content=f'{{"status": "not ready", "reason": "{exc}"}}',
            status_code=503,
            media_type="application/json",
        )
```

**Common causes checklist (check these first):**

| Symptom | Likely cause | Fix |
|---|---|---|
| ImportError / ModuleNotFoundError | Missing dependency in production | Pin all deps in requirements.txt, use pip freeze |
| ConnectionRefusedError | Service not reachable | Check network/DNS, service discovery |
| PermissionError | Running as non-root (good!) | Fix file permissions, use /tmp for temp files |
| MemoryError / OOMKilled | Container memory limit too low | Increase limit or optimize memory usage |
| TimeoutError | Slow network between services | Add connection timeouts, check latency |
| FileNotFoundError | Path does not exist in container | Use environment variables for paths, create dirs on startup |
| SSL/TLS errors | Certificate issues | Check cert chain, CA bundle, system time |

The diagnostic endpoint (`/health/detailed`) is your best friend. Hit it locally and in production, diff the output, and the cause will be obvious.'''),
    (
        "thinking/practical",
        r'''need to set up monitoring for our microservices, we have 5 services''',
        r'''<think>
The user has 5 microservices and needs monitoring. They did not specify a lot of context:
- What infrastructure (Kubernetes, ECS, bare EC2, Docker Compose?)
- What language/framework the services use
- Current observability tools (any existing logging, metrics, tracing?)
- Budget (self-hosted vs managed)
- What they care about most (uptime, performance, errors, cost?)

I could recommend Datadog or New Relic, but wait -- for 5 services those managed solutions can cost $200-500/month, which might be more than their infrastructure budget. Let me go with a self-hosted stack instead, since it is free and gives them full control.

For 5 services, I will recommend a practical, self-hosted stack that covers the three pillars of observability:
1. Metrics: Prometheus + Grafana (industry standard, free)
2. Logging: Already covered in most setups (stdout -> log aggregator) -- hmm, actually I should mention Loki since it integrates perfectly with Grafana
3. Tracing: I initially wanted to skip this at 5-service scale, but actually distributed tracing is exactly when you need it most -- when requests cross service boundaries and you cannot figure out which service is slow

Key things to monitor for microservices:
- The Four Golden Signals (latency, traffic, errors, saturation) per service -- these cover 90% of problems
- Inter-service communication (who calls whom, latency, error rates)
- Infrastructure metrics (CPU, memory, disk, network)
- Business metrics (orders/minute, active users, etc.) -- because infrastructure can look fine while the business is broken

I will provide:
1. Docker Compose setup for Prometheus + Grafana
2. Python middleware for exposing metrics (works with FastAPI/Flask)
3. Pre-built Grafana dashboard config
4. Alerting rules for the most critical conditions

I considered building an elaborate multi-tool setup, but actually monitoring 5 services should not require a dedicated platform team. I will keep it practical and focused on what matters most.
</think>

For 5 services, a self-hosted Prometheus + Grafana stack is the right call -- free, proven, and not overkill. Here is a complete setup.

**Project structure:**

```
monitoring/
    docker-compose.yml
    prometheus/
        prometheus.yml
        alerts.yml
    grafana/
        provisioning/
            dashboards/
                dashboard.yml
                services.json
            datasources/
                prometheus.yml
```

**docker-compose.yml:**

```yaml
version: "3.8"

services:
  prometheus:
    image: prom/prometheus:v2.50.0
    volumes:
      - ./prometheus/prometheus.yml:/etc/prometheus/prometheus.yml
      - ./prometheus/alerts.yml:/etc/prometheus/alerts.yml
      - prometheus_data:/prometheus
    ports:
      - "9090:9090"
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"
      - "--storage.tsdb.retention.time=30d"
      - "--web.enable-lifecycle"  # allows config reload via HTTP
    restart: unless-stopped

  grafana:
    image: grafana/grafana:10.3.0
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_PASSWORD:-admin}
      GF_USERS_ALLOW_SIGN_UP: "false"
    restart: unless-stopped

  alertmanager:
    image: prom/alertmanager:v0.27.0
    volumes:
      - ./alertmanager/alertmanager.yml:/etc/alertmanager/alertmanager.yml
    ports:
      - "9093:9093"
    restart: unless-stopped

volumes:
  prometheus_data:
  grafana_data:
```

**prometheus/prometheus.yml:**

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

# Load alerting rules
rule_files:
  - "alerts.yml"

# Send alerts to Alertmanager
alerting:
  alertmanagers:
    - static_configs:
        - targets: ["alertmanager:9093"]

# Scrape each service's /metrics endpoint
scrape_configs:
  - job_name: "api-gateway"
    static_configs:
      - targets: ["api-gateway:8000"]
    metrics_path: /metrics

  - job_name: "user-service"
    static_configs:
      - targets: ["user-service:8001"]
    metrics_path: /metrics

  - job_name: "order-service"
    static_configs:
      - targets: ["order-service:8002"]
    metrics_path: /metrics

  - job_name: "payment-service"
    static_configs:
      - targets: ["payment-service:8003"]
    metrics_path: /metrics

  - job_name: "notification-service"
    static_configs:
      - targets: ["notification-service:8004"]
    metrics_path: /metrics

  # Monitor Prometheus itself
  - job_name: "prometheus"
    static_configs:
      - targets: ["localhost:9090"]
```

**prometheus/alerts.yml (critical alerts):**

```yaml
groups:
  - name: service_health
    rules:
      # Service is down
      - alert: ServiceDown
        expr: up == 0
        for: 1m
        labels:
          severity: critical
        annotations:
          summary: "{{ $labels.job }} is down"
          description: "{{ $labels.job }} has been unreachable for more than 1 minute."

      # High error rate (> 5% of requests returning 5xx)
      - alert: HighErrorRate
        expr: |
          (
            sum(rate(http_requests_total{status=~"5.."}[5m])) by (job)
            /
            sum(rate(http_requests_total[5m])) by (job)
          ) > 0.05
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "High error rate on {{ $labels.job }}"
          description: "{{ $labels.job }} has {{ $value | humanizePercentage }} error rate."

      # High latency (p95 > 2 seconds)
      - alert: HighLatency
        expr: |
          histogram_quantile(0.95, sum(rate(http_request_duration_seconds_bucket[5m])) by (le, job))
          > 2
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High latency on {{ $labels.job }}"
          description: "{{ $labels.job }} p95 latency is {{ $value }}s."

      # Memory usage > 85%
      - alert: HighMemoryUsage
        expr: process_resident_memory_bytes / 1024 / 1024 > 500
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High memory usage on {{ $labels.job }}"
          description: "{{ $labels.job }} is using {{ $value }}MB of memory."

  - name: business_metrics
    rules:
      # No orders in 15 minutes during business hours
      - alert: NoOrders
        expr: |
          sum(increase(orders_created_total[15m])) == 0
          and on() hour() >= 9
          and on() hour() <= 21
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "No new orders in 15 minutes"
```

**Python metrics middleware (add to each service):**

```python
# metrics.py -- Drop-in metrics for FastAPI services
# pip install prometheus-client

import time
from prometheus_client import (
    Counter,
    Histogram,
    Gauge,
    Info,
    generate_latest,
    CONTENT_TYPE_LATEST,
)
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware


# --- Metric definitions ---

REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"],
)

REQUEST_DURATION = Histogram(
    "http_request_duration_seconds",
    "HTTP request duration in seconds",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
)

REQUESTS_IN_PROGRESS = Gauge(
    "http_requests_in_progress",
    "Number of HTTP requests currently being processed",
    ["method"],
)

APP_INFO = Info(
    "app",
    "Application information",
)

# Add your business-specific metrics here
ORDERS_CREATED = Counter(
    "orders_created_total",
    "Total orders created",
    ["payment_method"],
)

DB_QUERY_DURATION = Histogram(
    "db_query_duration_seconds",
    "Database query duration",
    ["query_type"],  # select, insert, update, delete
)


# --- Middleware ---

class MetricsMiddleware(BaseHTTPMiddleware):
    """Automatically tracks request count, duration, and in-progress for all endpoints."""

    async def dispatch(self, request: Request, call_next):
        method = request.method
        # Normalize path to avoid high-cardinality labels
        # /users/123 -> /users/{id}
        path = self._normalize_path(request.url.path)

        REQUESTS_IN_PROGRESS.labels(method=method).inc()
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            status = str(response.status_code)
        except Exception:
            status = "500"
            raise
        finally:
            duration = time.perf_counter() - start_time
            REQUEST_COUNT.labels(
                method=method, endpoint=path, status=status
            ).inc()
            REQUEST_DURATION.labels(
                method=method, endpoint=path
            ).observe(duration)
            REQUESTS_IN_PROGRESS.labels(method=method).dec()

        return response

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Replace dynamic path segments to prevent label explosion.

        /users/123/orders/456 -> /users/{id}/orders/{id}
        """
        parts = path.strip("/").split("/")
        normalized = []
        for part in parts:
            if part.isdigit() or (len(part) > 20 and "-" in part):  # UUIDs
                normalized.append("{id}")
            else:
                normalized.append(part)
        return "/" + "/".join(normalized)


# --- Setup function ---

def setup_metrics(app: FastAPI, service_name: str, version: str = "1.0.0"):
    """Add metrics endpoint and middleware to a FastAPI app."""
    APP_INFO.info({"name": service_name, "version": version})
    app.add_middleware(MetricsMiddleware)

    @app.get("/metrics", include_in_schema=False)
    async def metrics():
        return Response(
            content=generate_latest(),
            media_type=CONTENT_TYPE_LATEST,
        )


# --- Usage in your service ---
# app = FastAPI()
# setup_metrics(app, service_name="order-service", version="2.1.0")
#
# @app.post("/orders")
# async def create_order(order: OrderCreate):
#     result = await process_order(order)
#     ORDERS_CREATED.labels(payment_method=order.payment_method).inc()
#     return result
```

**What you get out of the box:**

| Metric | What it tells you |
|---|---|
| http_requests_total | Traffic volume, error rates per endpoint |
| http_request_duration_seconds | Latency percentiles (p50, p95, p99) |
| http_requests_in_progress | Current load / concurrency |
| process_resident_memory_bytes | Memory usage per service (built into prometheus_client) |
| orders_created_total | Business metric -- revenue proxy |
| up | Whether each service is reachable |

**Quick start:**

```bash
# Start monitoring stack
cd monitoring && docker compose up -d

# Grafana: http://localhost:3000 (admin / admin)
# Prometheus: http://localhost:9090
# Alertmanager: http://localhost:9093

# Add to each service:
# pip install prometheus-client
# Then call setup_metrics(app, "my-service") in your app startup
```

For 5 services, this stack uses about 200MB of RAM total and handles millions of time series. When you outgrow this (20+ services, need distributed tracing), look at Grafana Cloud's free tier or add OpenTelemetry for traces.'''),
    (
        "thinking/practical",
        r'''database migrations keep conflicting when two devs work on the same branch''',
        r'''<think>
Migration conflicts are a classic problem with sequential migration tools like Alembic, Django migrations, and similar. Let me trace through exactly how this happens:

1. Dev A creates migration 003_add_users_table.py
2. Dev B creates migration 003_add_products_table.py
3. Both branch from migration 002
4. When merged, the migration tool sees two migrations claiming to follow 002 -- conflict

The root cause is that these tools use a linear chain of migrations, and two developers extending the same chain creates a fork. It is essentially the same problem as a git merge conflict, but for database state.

My first thought was "just use timestamp-based migration IDs to avoid collisions" -- but wait, that only reduces the collision chance, it does not fix the fundamental problem. Two migrations can still claim the same parent even with timestamps. The real issue is the parent-child relationship, not the naming.

Solutions:
1. Alembic: Use `merge` command to create a merge migration (like a git merge commit)
2. Django: Has `--merge` flag to handle this
3. Prevention: CI checks that detect conflicts before merge
4. Team process: coordination around migrations

Hmm, I initially focused on resolution, but actually the better approach is prevention through CI plus team practices. You should not be manually resolving migration conflicts in production -- you should catch them before they get merged:
- CI job that checks for migration conflicts on every PR
- Use timestamp-based migration IDs instead of sequential numbers (reduces collision chance, even if it does not eliminate it)
- Alembic has `branch_labels` that can help
- Have a team convention: coordinate when creating migrations, since two people touching the schema at the same time is inherently risky

I will provide both prevention (CI checks) and resolution (merge scripts) for Alembic since it is the most common Python migration tool. I will also cover Django briefly because the problem is framework-agnostic.
</think>

Migration conflicts happen because two developers create migrations that both extend the same parent. Here is how to prevent them automatically with CI checks and resolve them when they happen.

**The problem:**

```
migration_002 (base)
    |
    +-- migration_003_add_users (Dev A)
    |
    +-- migration_003_add_products (Dev B)  <-- conflict!
```

**Solution 1: CI check that catches conflicts before merge**

```yaml
# .github/workflows/ci.yml -- Add this job

  migration-check:
    name: Check Migration Conflicts
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          # Fetch main branch too so we can compare
          fetch-depth: 0

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
          cache: pip

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Check for multiple migration heads
        run: |
          # Get current heads -- if there is more than one, we have a conflict
          heads=$(alembic heads 2>&1)
          head_count=$(echo "$heads" | grep -c "^[a-f0-9]")

          if [ "$head_count" -gt 1 ]; then
            echo "ERROR: Migration conflict detected!"
            echo "Found $head_count migration heads:"
            echo "$heads"
            echo ""
            echo "To fix, run: alembic merge heads -m 'merge migrations'"
            echo "Then commit the merge migration."
            exit 1
          fi

          echo "OK: Single migration head found"
          echo "$heads"

      - name: Verify migrations apply cleanly
        env:
          DATABASE_URL: sqlite:///test.db
        run: |
          # Apply all migrations to a fresh database
          alembic upgrade head

          # Verify downgrade works too
          alembic downgrade base

          echo "OK: Migrations apply and rollback cleanly"

      - name: Check for missing migration
        run: |
          # Detect if someone changed a model without creating a migration
          output=$(alembic check 2>&1) || true
          if echo "$output" | grep -q "New upgrade operations detected"; then
            echo "WARNING: Model changes detected without a corresponding migration"
            echo "$output"
            echo ""
            echo "Run: alembic revision --autogenerate -m 'describe your change'"
            exit 1
          fi
          echo "OK: No unmigrated model changes"
```

**Solution 2: Automatic conflict resolution script**

```python
#!/usr/bin/env python3
"""resolve_migrations.py -- Detect and fix migration conflicts.

Run this after pulling/merging when you have migration conflicts.

Usage:
    python resolve_migrations.py check    # Check for conflicts
    python resolve_migrations.py fix      # Auto-fix by creating merge migration
"""

import subprocess
import sys
import re


def get_migration_heads() -> list[str]:
    """Get all current migration head revisions."""
    result = subprocess.run(
        ["alembic", "heads"],
        capture_output=True,
        text=True,
    )
    heads = []
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if line:
            # Extract revision ID (first word, hex string)
            match = re.match(r"([a-f0-9]+)", line)
            if match:
                heads.append(match.group(1))
    return heads


def get_current_revision() -> str:
    """Get the current database revision."""
    result = subprocess.run(
        ["alembic", "current"],
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def check_conflicts() -> bool:
    """Check if there are migration conflicts (multiple heads)."""
    heads = get_migration_heads()
    if len(heads) <= 1:
        print(f"No conflicts. Single head: {heads[0] if heads else 'none'}")
        return False

    print(f"CONFLICT: Found {len(heads)} migration heads:")
    for head in heads:
        # Get details of each head
        result = subprocess.run(
            ["alembic", "show", head],
            capture_output=True,
            text=True,
        )
        print(f"  {head}:")
        for line in result.stdout.strip().split("\n"):
            if "Rev:" in line or "Parent:" in line or "Message:" in line:
                print(f"    {line.strip()}")
    return True


def fix_conflicts():
    """Create a merge migration to resolve conflicts."""
    heads = get_migration_heads()
    if len(heads) <= 1:
        print("No conflicts to fix.")
        return

    print(f"Creating merge migration for {len(heads)} heads...")

    # Create the merge revision
    result = subprocess.run(
        [
            "alembic", "merge", "heads",
            "-m", "merge_migration_branches",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print(f"ERROR: Failed to create merge migration:")
        print(result.stderr)
        sys.exit(1)

    print("Merge migration created successfully!")
    print(result.stdout)

    # Verify single head now
    new_heads = get_migration_heads()
    if len(new_heads) == 1:
        print(f"Conflict resolved. New single head: {new_heads[0]}")
    else:
        print(f"WARNING: Still have {len(new_heads)} heads. Manual intervention needed.")


def verify_migrations():
    """Verify all migrations apply cleanly to a fresh database."""
    print("Testing migrations on fresh database...")

    # Upgrade to head
    result = subprocess.run(
        ["alembic", "upgrade", "head"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: Migrations failed to apply:")
        print(result.stderr)
        return False

    # Downgrade back to base
    result = subprocess.run(
        ["alembic", "downgrade", "base"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"ERROR: Migration downgrade failed:")
        print(result.stderr)
        return False

    print("All migrations apply and rollback cleanly.")
    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python resolve_migrations.py [check|fix|verify]")
        sys.exit(1)

    command = sys.argv[1]
    if command == "check":
        has_conflicts = check_conflicts()
        sys.exit(1 if has_conflicts else 0)
    elif command == "fix":
        fix_conflicts()
    elif command == "verify":
        success = verify_migrations()
        sys.exit(0 if success else 1)
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)
```

**Solution 3: Prevention through team practices**

Add this to your Alembic configuration to use timestamp-based revision IDs instead of random hashes, which makes conflicts easier to understand:

```python
# alembic/env.py -- Add near the top

import time

def process_revision_directives(context, revision, directives):
    """Use timestamp-based revision IDs to reduce collision risk
    and make migration order obvious from filenames."""
    if directives:
        script = directives[0]
        # Use timestamp as revision ID
        script.rev_id = str(int(time.time()))


# In run_migrations_online():
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            process_revision_directives=process_revision_directives,
            # ...
        )
```

**Git pre-commit hook (catches conflicts before commit):**

```bash
#!/bin/bash
# .git/hooks/pre-commit (or use pre-commit framework)

# Check for migration conflicts before allowing commit
if git diff --cached --name-only | grep -q "alembic/versions/"; then
    echo "Migration files detected -- checking for conflicts..."

    head_count=$(alembic heads 2>/dev/null | grep -c "^[a-f0-9]")
    if [ "$head_count" -gt 1 ]; then
        echo "ERROR: Migration conflict detected ($head_count heads)"
        echo "Run: python resolve_migrations.py fix"
        exit 1
    fi
fi
```

**Django equivalent (if you use Django instead of Alembic):**

```bash
# Check for conflicts
python manage.py showmigrations --list | grep -E "^\[ \]"

# Fix conflicts
python manage.py makemigrations --merge

# CI check
python manage.py migrate --check  # exits non-zero if unapplied migrations exist
```

**Team workflow:**

1. Before creating a migration, pull the latest main branch
2. Create the migration on a fresh branch from main
3. CI automatically checks for conflicts on every PR
4. If conflicts are detected, run `python resolve_migrations.py fix` to create a merge migration
5. Pre-commit hook prevents committing conflicting migrations

The CI check is the most important piece -- it catches the problem before it reaches main, when it is cheapest to fix.'''),
]
