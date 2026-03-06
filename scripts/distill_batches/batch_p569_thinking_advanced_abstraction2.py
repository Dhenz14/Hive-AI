"""Phase 2G: Advanced Reasoning — Abstraction Laddering (Part 2/5)
Move between concrete instances, patterns, principles, and policies:
retry logic, config management, API error handling, test organization, deployment."""

PAIRS = [
    (
        "thinking/abstraction-retry-to-resilience",
        "My HTTP client code has retry logic scattered everywhere with slightly different implementations. How do I clean this up?",
        r'''<think>
Let me climb the abstraction ladder from the concrete problem to a general principle.

CONCRETE LEVEL (the specific bug):
```python
# In service_a.py
for i in range(3):
    try:
        resp = requests.get(url, timeout=5)
        break
    except requests.Timeout:
        time.sleep(1)

# In service_b.py
retries = 0
while retries < 5:
    try:
        resp = requests.post(url, json=data, timeout=10)
        if resp.status_code < 500:
            break
        retries += 1
    except Exception:
        retries += 1
        time.sleep(2 ** retries)
```

Different retry counts, different timeouts, different backoff strategies, different exception handling. Some retry on HTTP 5xx, some don't.

PATTERN LEVEL (what's the recurring structure?):
Every retry has the same shape:
1. Attempt the operation
2. If it fails with a retryable error, wait, then try again
3. Give up after N attempts
4. The differences are: max_retries, delay_strategy, which_errors_to_retry

This is a decorator/wrapper pattern — extract the retry logic, parameterize the differences.

PRINCIPLE LEVEL (why does this pattern exist?):
The principle is "resilience through retry with backoff." Network calls are unreliable.
Transient failures (timeouts, 503s, connection resets) are expected in distributed systems.
The correct response is: retry with exponential backoff + jitter, and circuit-break if the service is consistently down.

This is part of a broader principle: "design for failure" — every external call can fail, and the failure mode should be explicit and configurable.

POLICY LEVEL (organizational rule):
"All external HTTP calls MUST use the shared retry client with standard configuration.
Direct use of requests.get/post is not allowed for external services."

This policy:
- Prevents ad-hoc retry implementations
- Ensures consistent behavior (same backoff, same circuit breaking)
- Makes it easy to change retry strategy globally
- Enables centralized monitoring of retry rates

The fix should exist at the PATTERN level (shared retry wrapper) enforced by the POLICY level (lint rule or shared client).
</think>

You're seeing the same pattern reimplemented with slight variations — classic sign you need to extract a shared abstraction. Let me walk up the abstraction ladder.

**Level 1 — Concrete fix (shared retry mechanism):**

```python
# http_client.py — one place for all retry logic
import httpx
from tenacity import (
    retry, stop_after_attempt, wait_exponential,
    retry_if_exception_type, retry_if_result
)

def _is_retryable_status(response):
    """Retry on 429 (rate limit) and 5xx (server error)."""
    return response.status_code == 429 or response.status_code >= 500

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=30),
    retry=(
        retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError))
        | retry_if_result(_is_retryable_status)
    ),
)
def resilient_request(method: str, url: str, **kwargs):
    """Single entry point for all external HTTP calls."""
    kwargs.setdefault("timeout", 10.0)
    return httpx.request(method, url, **kwargs)

# Usage everywhere:
resp = resilient_request("GET", "https://api.example.com/data")
resp = resilient_request("POST", "https://api.example.com/submit", json=payload)
```

**Level 2 — Pattern (configurable resilience per service):**

```python
# Different external services have different reliability profiles
from dataclasses import dataclass

@dataclass
class ServiceConfig:
    base_url: str
    timeout: float = 10.0
    max_retries: int = 3
    backoff_base: float = 1.0
    circuit_breaker_threshold: int = 5  # failures before opening circuit

SERVICE_CONFIGS = {
    "payment": ServiceConfig(
        base_url="https://api.stripe.com",
        timeout=30.0,    # Payment is slow but critical
        max_retries=2,   # Don't retry too many times (idempotency risk)
    ),
    "email": ServiceConfig(
        base_url="https://api.sendgrid.com",
        timeout=5.0,
        max_retries=5,   # Email can retry aggressively
    ),
    "analytics": ServiceConfig(
        base_url="https://api.mixpanel.com",
        timeout=3.0,
        max_retries=1,   # Analytics is fire-and-forget
    ),
}

class ServiceClient:
    def __init__(self, config: ServiceConfig):
        self.config = config
        self.failure_count = 0

    def request(self, method, path, **kwargs):
        if self.failure_count >= self.config.circuit_breaker_threshold:
            raise CircuitOpenError(f"Circuit open for {self.config.base_url}")

        url = f"{self.config.base_url}{path}"
        # Use tenacity with config-driven parameters
        ...
```

**Level 3 — Principle: "Design for failure"**

Every external dependency will fail. The question isn't "if" but "how your code behaves when it does." The retry wrapper is one aspect. The full resilience toolkit includes:
- **Retry with backoff** — handles transient blips
- **Circuit breaker** — stops hammering a dead service
- **Timeout** — prevents hanging forever
- **Fallback** — degrade gracefully (cached data, default value)
- **Bulkhead** — isolate failures (one slow service doesn't block all threads)

**Level 4 — Policy: enforce it**

```python
# Add a lint rule or import hook that catches direct requests usage
# pyproject.toml
[tool.ruff.per-file-ignores]
# Ban raw requests/httpx calls outside http_client.py
"*.py" = ["TID252"]  # or custom rule

# Better: make ServiceClient the only way to make external calls
# If requests/httpx aren't in requirements.txt directly,
# only http_client.py imports them
```

Start by creating the shared `http_client.py`, migrate callsites one at a time, then add the lint rule to prevent regression.'''
    ),
    (
        "thinking/abstraction-config-to-environment",
        "I have config values hardcoded in different places — database URLs in code, API keys in .env files, feature flags in a JSON file, timeouts in constants. How should I organize configuration?",
        r'''<think>
Let me climb the abstraction ladder from the concrete mess to a principled config architecture.

CONCRETE LEVEL (the current state):
```python
# In database.py
DB_URL = "postgresql://user:pass@localhost/mydb"  # Hardcoded!

# In .env
STRIPE_API_KEY=sk_test_xxx

# In config.json
{"feature_flags": {"new_checkout": true}}

# In constants.py
REQUEST_TIMEOUT = 30
MAX_RETRIES = 3
```

Four different mechanisms, no hierarchy, no validation, no documentation of what config exists.

PATTERN LEVEL (what are the commonalities?):
All config values share these properties:
1. They have a name/key
2. They have a type (string, int, bool, URL)
3. They have a default (sometimes)
4. They come from a source (env var, file, hardcoded)
5. Some are secret (API keys, DB passwords)
6. They vary by environment (dev/staging/prod)

The 12-Factor App pattern: store config in environment variables.
Why? Because env vars are language-agnostic, don't get committed to git, and change between deploys without code changes.

But pure env vars have problems:
- No validation (typo in var name = silent None)
- No documentation (what env vars does this app need?)
- No typing (everything is a string)

PRINCIPLE LEVEL (what should config management achieve?):
1. Single source of truth — one place to see ALL config the app uses
2. Validated at startup — fail fast if required config is missing
3. Typed — DB_PORT is an int, DEBUG is a bool
4. Environment-specific — different values per environment
5. Secrets separate from non-secrets — different security handling
6. Documented — new developer can see what needs configuring

POLICY LEVEL:
"All configuration MUST be declared in the Settings class. No hardcoded values for anything that changes between environments. Secrets MUST come from environment variables, never files committed to git."
</think>

You have config scattered across 4 mechanisms with no validation or consistency. Here's how to fix it, organized by abstraction level.

**Concrete fix — one Settings class using Pydantic:**

```python
# config.py — THE single source of truth for all config
from pydantic_settings import BaseSettings
from pydantic import Field, PostgresDsn

class Settings(BaseSettings):
    """All app configuration. Validated at startup."""

    # Database
    database_url: PostgresDsn = Field(
        description="PostgreSQL connection string"
    )
    db_pool_size: int = Field(default=5, ge=1, le=50)

    # External services
    stripe_api_key: str = Field(description="Stripe secret key")
    stripe_webhook_secret: str = Field(default="")
    email_api_key: str = Field(default="")

    # Feature flags
    feature_new_checkout: bool = Field(default=False)
    feature_dark_mode: bool = Field(default=False)

    # Resilience
    request_timeout: float = Field(default=10.0, ge=1.0)
    max_retries: int = Field(default=3, ge=0, le=10)

    # App
    debug: bool = Field(default=False)
    log_level: str = Field(default="INFO")
    environment: str = Field(default="development")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        # STRIPE_API_KEY env var → stripe_api_key field
        "env_prefix": "",
    }

# Singleton — created once at startup
settings = Settings()

# If ANY required field is missing or invalid, app crashes immediately
# with a clear error message. No more silent None values.
```

**Pattern — environment-specific overrides:**

```bash
# .env.example (committed to git — documents ALL config)
DATABASE_URL=postgresql://user:pass@localhost/mydb
STRIPE_API_KEY=sk_test_xxx
FEATURE_NEW_CHECKOUT=false
DEBUG=true
LOG_LEVEL=DEBUG

# .env (NOT committed — local developer overrides)
DATABASE_URL=postgresql://dev:dev@localhost/devdb
STRIPE_API_KEY=sk_test_my_key

# Production: set env vars in your deployment platform
# (Kubernetes secrets, AWS Parameter Store, etc.)
```

**Usage everywhere — import settings, never hardcode:**

```python
# BEFORE (scattered):
import os
db_url = os.environ.get("DATABASE_URL", "postgresql://localhost/mydb")
timeout = 30  # magic number

# AFTER (centralized):
from config import settings

db_url = str(settings.database_url)  # typed, validated
timeout = settings.request_timeout    # documented, validated
```

**Principle — the config hierarchy:**

```
Priority (highest wins):
1. Environment variables     ← production secrets
2. .env file                 ← local dev overrides
3. Field defaults in code    ← sensible defaults

This means:
- Developers just need a .env file
- CI sets env vars for test config
- Production uses env vars (from secrets manager)
- Defaults make it work out of the box for common cases
```

**Policy — enforce it:**

```python
# In your linting/CI, ban patterns like:
# os.environ.get("ANYTHING") — use settings instead
# Hardcoded URLs, ports, or API keys in any .py file

# Startup check in main.py:
from config import settings  # Crashes immediately if config invalid

# For feature flags that change at runtime (not restart),
# graduate to a proper feature flag service (LaunchDarkly, Unleash)
# But for deploy-time flags, Settings is perfect.
```

Migrate incrementally: add each hardcoded value to Settings, update the callsite to use `settings.xxx`, delete the old code. One config value at a time.'''
    ),
    (
        "thinking/abstraction-apierror-to-contract",
        "My REST API returns errors inconsistently — sometimes a JSON object with 'error', sometimes just a status code, sometimes a string message. Clients are frustrated. How do I standardize?",
        r'''<think>
Abstraction ladder for API error handling:

CONCRETE LEVEL (the symptoms):
```python
# Endpoint A:
return {"error": "Not found"}, 404

# Endpoint B:
raise HTTPException(status_code=400, detail="Invalid email")

# Endpoint C:
return {"message": "Something went wrong", "code": "INTERNAL_ERROR"}, 500

# Endpoint D:
return "Unauthorized", 401  # Just a string!
```

Every endpoint invents its own error format. Clients can't reliably parse errors.

PATTERN LEVEL (what do all API errors need?):
Every error response should contain:
1. HTTP status code (in the response status line)
2. Machine-readable error code (for client logic: "VALIDATION_ERROR", not "Bad request")
3. Human-readable message (for debugging/display)
4. Field-level details (for validation: which fields failed and why)
5. Request ID (for support: "please send us your request_id")

This is basically RFC 7807 (Problem Details for HTTP APIs), which standardized this exact thing.

PRINCIPLE LEVEL (why consistency matters):
API errors are part of the contract. If success responses have a schema, error responses need one too.
Inconsistent errors mean:
- Clients write fragile parsing code with special cases per endpoint
- Support can't debug issues ("what error did you get?" "uh, some JSON thing")
- Mobile apps show raw error strings to users

The principle: **errors are a first-class part of your API contract, not an afterthought.**

POLICY LEVEL:
"All API errors MUST use the standard ErrorResponse schema. No endpoint may return a bare string or ad-hoc error object. Error middleware handles all unhandled exceptions."
</think>

API errors are part of your contract — they need a consistent schema just like success responses. Here's the fix at every level.

**The standard error schema (RFC 7807-inspired):**

```python
# schemas.py
from pydantic import BaseModel
from typing import Optional

class ErrorDetail(BaseModel):
    field: str           # "email", "items[0].quantity"
    message: str         # "must be a valid email address"
    code: str            # "invalid_format"

class ErrorResponse(BaseModel):
    error: str           # Machine-readable: "VALIDATION_ERROR"
    message: str         # Human-readable: "Request validation failed"
    details: list[ErrorDetail] = []  # Field-level errors
    request_id: str      # For support debugging

    # Example output:
    # {
    #   "error": "VALIDATION_ERROR",
    #   "message": "Request validation failed",
    #   "details": [
    #     {"field": "email", "message": "must be valid email", "code": "invalid_format"},
    #     {"field": "age", "message": "must be >= 0", "code": "out_of_range"}
    #   ],
    #   "request_id": "req_abc123"
    # }
```

**Error exception classes:**

```python
# exceptions.py
class AppError(Exception):
    """Base class for all application errors."""
    def __init__(self, status_code: int, error: str, message: str,
                 details: list = None):
        self.status_code = status_code
        self.error = error
        self.message = message
        self.details = details or []

class NotFoundError(AppError):
    def __init__(self, resource: str, resource_id: str):
        super().__init__(
            status_code=404,
            error="NOT_FOUND",
            message=f"{resource} with id '{resource_id}' not found",
        )

class ValidationError(AppError):
    def __init__(self, details: list):
        super().__init__(
            status_code=422,
            error="VALIDATION_ERROR",
            message="Request validation failed",
            details=details,
        )

class AuthenticationError(AppError):
    def __init__(self, message: str = "Invalid or expired credentials"):
        super().__init__(
            status_code=401,
            error="AUTHENTICATION_ERROR",
            message=message,
        )

class ForbiddenError(AppError):
    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            status_code=403,
            error="FORBIDDEN",
            message=message,
        )
```

**Middleware that catches everything:**

```python
# middleware.py (FastAPI)
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import uuid
import structlog

logger = structlog.get_logger()

async def error_handler(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:12])

    try:
        response = await call_next(request)
        return response

    except AppError as e:
        # Known application errors — expected
        return JSONResponse(
            status_code=e.status_code,
            content={
                "error": e.error,
                "message": e.message,
                "details": [d.__dict__ for d in e.details] if e.details else [],
                "request_id": request_id,
            },
        )

    except Exception as e:
        # Unknown errors — log full traceback, return generic message
        logger.exception("unhandled_error", request_id=request_id, path=request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_ERROR",
                "message": "An unexpected error occurred",
                "details": [],
                "request_id": request_id,
            },
        )

# Also handle Pydantic validation errors (from request body parsing)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = [
        {"field": " -> ".join(str(x) for x in err["loc"]),
         "message": err["msg"],
         "code": err["type"]}
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={
            "error": "VALIDATION_ERROR",
            "message": "Request validation failed",
            "details": details,
            "request_id": request.headers.get("X-Request-ID", "unknown"),
        },
    )
```

**Usage in endpoints — clean and consistent:**

```python
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    user = db.get_user(user_id)
    if not user:
        raise NotFoundError("User", str(user_id))
    return user

@app.post("/orders/")
async def create_order(order: OrderCreate):
    if not inventory.check(order.items):
        raise AppError(
            status_code=409,
            error="INSUFFICIENT_INVENTORY",
            message="Some items are out of stock",
            details=[
                ErrorDetail(field=f"items[{i}]", message="out of stock", code="out_of_stock")
                for i, item in enumerate(order.items) if not inventory.has(item)
            ],
        )
    return db.create_order(order)
```

Clients now get a predictable structure for every error — they parse `error` for logic, show `message` to users, and send `request_id` to support.'''
    ),
    (
        "thinking/abstraction-testorg-to-strategy",
        "My test suite is a mess — 2000 tests in flat files with no organization. Some tests take 30 seconds each. CI takes 45 minutes. How do I organize this?",
        r'''<think>
Abstraction ladder for test organization:

CONCRETE LEVEL (the symptoms):
- 2000 tests in flat structure (test_everything.py, test_utils.py, test_api.py — each with 200+ tests)
- Some are unit tests (fast, no I/O), some are integration tests (DB, API calls, slow)
- CI runs them all sequentially = 45 minutes
- Developers skip running tests locally because it's too slow
- Flaky tests (network-dependent) fail randomly

PATTERN LEVEL:
Tests naturally fall into categories:
1. Unit tests: test a function in isolation, mock dependencies, < 10ms each
2. Integration tests: test components working together, real DB, 100ms-1s each
3. End-to-end tests: test full user flows, real services, 1-30s each

The testing pyramid:
- Many unit tests (fast, cheap) — base
- Fewer integration tests (medium) — middle
- Few E2E tests (slow, expensive) — top

Organization should mirror this pyramid so you can:
- Run unit tests on every save (< 30 seconds)
- Run integration tests before commit (< 5 minutes)
- Run E2E tests in CI only (< 15 minutes)

PRINCIPLE LEVEL:
"Fast feedback loops drive developer productivity."
The purpose of test organization is NOT just neatness — it's enabling fast feedback.
If you can run the relevant unit tests in 2 seconds after changing a file, you catch bugs instantly.
If you have to wait 45 minutes, you context-switch and the bug costs 10x more to fix.

Corollary: Tests should be organized by speed and scope, not by feature.
(Feature organization is secondary — use directories for both.)

POLICY LEVEL:
"Unit tests MUST complete in < 60 seconds total. Integration tests MUST complete in < 10 minutes.
Any test requiring external services MUST be marked with @pytest.mark.integration.
CI runs all tiers in parallel. Pre-commit hook runs unit tests only."
</think>

The root problem isn't messy files — it's that test speed and scope are mixed together, killing your feedback loop. Here's how to restructure.

**Step 1 — Categorize by speed tier:**

```
tests/
    unit/                    # < 10ms per test, no I/O
        test_models.py
        test_validators.py
        test_utils.py
        test_pricing.py
    integration/             # 100ms-1s, real DB/cache
        test_repositories.py
        test_api_endpoints.py
        test_email_service.py
    e2e/                     # 1-30s, full flows
        test_checkout_flow.py
        test_user_registration.py
    conftest.py              # Shared fixtures
    conftest_integration.py  # DB setup/teardown
```

**Step 2 — Mark tests so you can run tiers independently:**

```python
# conftest.py
import pytest

# Auto-mark tests based on directory
def pytest_collection_modifyitems(items):
    for item in items:
        if "/integration/" in str(item.fspath):
            item.add_marker(pytest.mark.integration)
        elif "/e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)

# pytest.ini or pyproject.toml
# [tool.pytest.ini_options]
# markers = [
#     "integration: tests requiring database/external services",
#     "e2e: end-to-end tests requiring full stack",
# ]
```

**Step 3 — Run the right tier at the right time:**

```bash
# While coding (< 30 seconds):
pytest tests/unit/ -x -q

# Before commit (< 5 minutes):
pytest tests/unit/ tests/integration/ -x

# In CI (parallel, all tiers):
pytest tests/ -n auto --dist loadgroup

# Just the tests related to your changes:
pytest tests/ --co -q | grep "test_pricing" | xargs pytest
```

**Step 4 — Speed up integration tests:**

```python
# conftest_integration.py
import pytest
from sqlalchemy import create_engine

@pytest.fixture(scope="session")
def db_engine():
    """Create DB once for all integration tests, not per-test."""
    engine = create_engine("postgresql://test:test@localhost/testdb")
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)

@pytest.fixture(autouse=True)
def db_transaction(db_engine):
    """Wrap each test in a transaction and rollback — fast cleanup."""
    connection = db_engine.connect()
    transaction = connection.begin()
    yield connection
    transaction.rollback()
    connection.close()
```

**Step 5 — Parallelize CI:**

```yaml
# .github/workflows/test.yml
jobs:
  unit:
    runs-on: ubuntu-latest
    steps:
      - run: pytest tests/unit/ -n auto --timeout=10
    # Target: < 2 minutes

  integration:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16
    steps:
      - run: pytest tests/integration/ -n auto --timeout=30
    # Target: < 5 minutes

  e2e:
    runs-on: ubuntu-latest
    needs: [unit, integration]  # Only run if faster tests pass
    steps:
      - run: pytest tests/e2e/ --timeout=60
    # Target: < 10 minutes

  # Total CI time: ~10 min (parallel) instead of 45 min (sequential)
```

**Step 6 — Pre-commit hook for instant feedback:**

```bash
# .pre-commit-config.yaml or .git/hooks/pre-commit
#!/bin/bash
# Only run unit tests on changed files
changed_files=$(git diff --cached --name-only --diff-filter=ACMR | grep '\.py$')
if [ -n "$changed_files" ]; then
    pytest tests/unit/ -x -q --timeout=5
fi
```

Migration plan: spend one afternoon moving existing tests into `unit/` vs `integration/` vs `e2e/` directories. Tests that touch the DB or network go to integration. Tests that mock everything go to unit. Then enable parallel runs. You'll go from 45 minutes to ~10.'''
    ),
    (
        "thinking/abstraction-deployment-to-philosophy",
        "We deploy by SSHing into the server, pulling the latest code, and restarting the service. It works but feels fragile. What should we do instead?",
        r'''<think>
Abstraction ladder for deployment:

CONCRETE LEVEL (what they're doing):
```bash
ssh prod-server
cd /opt/myapp
git pull origin main
pip install -r requirements.txt
systemctl restart myapp
```

Problems:
- Manual steps = human error (forgot pip install, pulled wrong branch)
- No rollback (how do you go back? git checkout the old commit and restart?)
- Downtime during restart (service is down for seconds to minutes)
- No audit trail (who deployed what, when?)
- Works for 1 server, breaks with 2+ (do them in sequence? What if one fails?)

PATTERN LEVEL (what does deployment actually need?):
1. Build: create a deployable artifact (not "git pull")
2. Ship: get the artifact to the server(s)
3. Run: start the new version
4. Verify: health check — is it working?
5. Rollback: if not working, go back to previous version in < 1 minute

The key insight: separate the BUILD from the DEPLOY.
"git pull + pip install" = building ON the production server.
If pip install fails, you're stuck mid-deploy with a broken state.

Instead: build once, deploy the artifact.

PRINCIPLE LEVEL:
"Deployments should be boring, repeatable, and reversible."
- Boring: automated, no human decisions needed
- Repeatable: same process every time, same result
- Reversible: rollback in seconds, not minutes

Corollary: "If you can't deploy with one command, your deployment process is too complex."

POLICY LEVEL:
"All deployments go through CI/CD. No SSH to production for deployments.
Every deploy is a tagged artifact. Rollback is one button/command.
Zero-downtime required for all user-facing services."

Now, what's the RIGHT solution for their stage?

They SSH into ONE server. They're small. The right next step isn't Kubernetes — it's:
1. Automate the manual steps (script or CI/CD)
2. Add a rollback mechanism
3. Add health checking

Then later: containerize, add zero-downtime deploys.
</think>

Your SSH-and-pull approach has a single-point-of-failure problem: humans. Let me walk you from where you are to where you need to be, without over-engineering.

**Stage 1 — Automate what you have (today's fix):**

```bash
#!/bin/bash
# deploy.sh — run from your LOCAL machine, not on the server
set -euo pipefail

SERVER="prod-server"
APP_DIR="/opt/myapp"
COMMIT="${1:-main}"

echo "Deploying $COMMIT to $SERVER..."

ssh $SERVER << REMOTE
    set -euo pipefail
    cd $APP_DIR

    # Save current version for rollback
    git rev-parse HEAD > .previous_version

    # Deploy
    git fetch origin
    git checkout $COMMIT
    pip install -r requirements.txt
    python manage.py migrate --noinput

    # Restart and verify
    systemctl restart myapp
    sleep 3

    # Health check
    if ! curl -sf http://localhost:8000/health > /dev/null; then
        echo "HEALTH CHECK FAILED — rolling back!"
        git checkout \$(cat .previous_version)
        pip install -r requirements.txt
        systemctl restart myapp
        exit 1
    fi

    echo "Deploy successful: \$(git rev-parse --short HEAD)"
REMOTE
```

```bash
# Usage:
./deploy.sh           # Deploy latest main
./deploy.sh v1.2.3    # Deploy a specific tag
```

**Stage 2 — CI/CD pipeline (next week):**

```yaml
# .github/workflows/deploy.yml
name: Deploy
on:
  push:
    tags: ['v*']  # Deploy on version tags only

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt
      - run: pytest tests/

  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: startsWith(github.ref, 'refs/tags/v')
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to production
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.PROD_HOST }}
          username: deploy
          key: ${{ secrets.DEPLOY_KEY }}
          script: |
            cd /opt/myapp
            git rev-parse HEAD > .previous_version
            git fetch origin
            git checkout ${{ github.ref_name }}
            pip install -r requirements.txt
            python manage.py migrate --noinput
            systemctl restart myapp
            sleep 3
            curl -sf http://localhost:8000/health || {
                echo "Rollback!";
                git checkout $(cat .previous_version);
                pip install -r requirements.txt;
                systemctl restart myapp;
                exit 1;
            }
```

```bash
# Deploy = just tag and push:
git tag v1.2.3
git push origin v1.2.3
# CI runs tests, then deploys automatically
```

**Stage 3 — Zero-downtime (next month):**

```bash
# Use systemd socket activation or a reverse proxy (nginx/caddy)
# to do blue-green deploys on a single server:

# /opt/myapp-blue/  (current live)
# /opt/myapp-green/ (deploy target)

# 1. Deploy to green
# 2. Health check green
# 3. Switch nginx upstream from blue to green
# 4. Reload nginx (zero downtime)
# 5. Next deploy goes to blue
```

```nginx
# /etc/nginx/conf.d/myapp.conf
upstream myapp {
    server 127.0.0.1:8001;  # blue
    # server 127.0.0.1:8002;  # green (swap these to switch)
}
```

**Stage 4 — Containers (when you outgrow one server):**

```dockerfile
# Dockerfile — build once, run anywhere
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["gunicorn", "myapp:app", "-w", "4", "-b", "0.0.0.0:8000"]
```

Don't jump to Stage 4 until you need multiple servers. Stage 1 takes 30 minutes and solves your immediate problem. Stage 2 takes a few hours and makes deploys one-click.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
