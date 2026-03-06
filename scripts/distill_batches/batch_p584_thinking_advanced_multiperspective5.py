"""Phase 2D: Advanced Reasoning — Multi-Perspective Analysis (Part 5/8)"""

PAIRS = [
    (
        "thinking/multiperspective-logging-strategy",
        "We're debating our logging strategy. Some want structured JSON logs everywhere, others want human-readable text logs. We use ELK stack for production but developers read logs locally. What approach should we take?",
        r'''<think>
This is a classic tension — machine-parseable vs human-readable. Let me analyze from multiple stakeholder perspectives.

**Developer perspective (local development):**
Reading JSON logs locally is painful. `{"timestamp":"2024-01-15T10:30:00Z","level":"INFO","message":"User logged in","user_id":123}` is much harder to scan than `10:30:00 INFO User logged in (user_id=123)`. Developers need quick visual scanning during debugging. They'll hate being forced to pipe everything through `jq`.

**SRE/Operations perspective:**
Structured JSON is essential. When you're searching through millions of log lines in Kibana, you need fields you can filter, aggregate, and alert on. Text logs require regex parsing which is fragile and slow. "Give me all ERROR logs where response_time > 500ms and service=payments" is trivial with structured logs, nightmarish with text.

**Security/Compliance perspective:**
Structured logs are non-negotiable for audit trails. You need consistent fields for user actions, IP addresses, request IDs. Compliance auditors want queryable evidence, not grep results.

**Cost perspective:**
JSON logs are larger (field names repeated in every line). At scale this affects storage costs and ingestion rates. But the queryability benefits far outweigh storage costs in most cases.

**Performance perspective:**
JSON serialization has overhead, but it's negligible compared to I/O. The real performance concern is log volume — structured logs make it easier to implement sampling and filtering.

**Synthesis — the hybrid approach:**
The key insight is that the LOG FORMAT and the LOG DISPLAY are separate concerns. You can write structured logs and render them differently per context.

Most modern logging libraries support formatters. Use structured JSON as the canonical format, but configure a human-readable formatter for local development.
</think>

Use structured JSON as your canonical log format everywhere, but configure **environment-specific formatters** to solve the readability tension.

## The Architecture

```python
import logging
import json
import os
from datetime import datetime

class StructuredFormatter(logging.Formatter):
    """JSON formatter for production/ELK ingestion."""
    def format(self, record):
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }
        # Merge any extra fields passed via `extra={}`
        if hasattr(record, "extra_fields"):
            log_entry.update(record.extra_fields)
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(log_entry)

class DevFormatter(logging.Formatter):
    """Human-readable formatter for local development."""
    COLORS = {
        "DEBUG": "\033[36m",    # Cyan
        "INFO": "\033[32m",     # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",    # Red
        "CRITICAL": "\033[35m", # Magenta
    }
    RESET = "\033[0m"

    def format(self, record):
        color = self.COLORS.get(record.levelname, "")
        timestamp = datetime.utcnow().strftime("%H:%M:%S.%f")[:-3]
        extras = ""
        if hasattr(record, "extra_fields"):
            extras = " " + " ".join(
                f"{k}={v}" for k, v in record.extra_fields.items()
            )
        msg = f"{color}{timestamp} {record.levelname:<7}{self.RESET} {record.getMessage()}{extras}"
        if record.exc_info:
            msg += "\n" + self.formatException(record.exc_info)
        return msg

def setup_logging():
    env = os.getenv("APP_ENV", "development")
    handler = logging.StreamHandler()
    if env == "development":
        handler.setFormatter(DevFormatter())
    else:
        handler.setFormatter(StructuredFormatter())
    logging.root.addHandler(handler)
    logging.root.setLevel(logging.INFO)
```

## Why This Works for Everyone

| Stakeholder | Need | Solution |
|------------|------|---------|
| Developers | Readable local logs | DevFormatter with colors |
| SRE/Ops | Queryable production logs | StructuredFormatter → ELK |
| Security | Audit trail | Consistent structured fields |
| Cost | Manageable volume | Same log calls, format is presentation |

## Key Rules

1. **Log calls are format-agnostic** — always use `logger.info("msg", extra={"extra_fields": {...}})`
2. **Never string-interpolate sensitive data** into the message — use extra fields
3. **Correlation IDs** (`request_id`, `trace_id`) go in extra fields, making distributed tracing work in both formats
4. **Log levels are consistent** regardless of environment — don't log DEBUG in production just because it's JSON

The structured-vs-readable debate is a false dichotomy. The data model should always be structured; only the rendering changes per environment.'''
    ),
    (
        "thinking/multiperspective-api-versioning",
        "Our REST API serves both mobile apps and third-party integrations. We need to make breaking changes to several endpoints. What API versioning strategy should we use? The team is split between URL versioning (/v1/), header versioning, and query parameter versioning.",
        r'''<think>
API versioning strategy — let me evaluate from multiple perspectives.

**Mobile app developer perspective:**
Mobile apps are deployed to app stores. Users don't all update simultaneously. You might have v1 and v2 clients active for YEARS. The versioning mechanism needs to be:
- Easy to implement in HTTP clients
- Visible and debuggable (can I tell which version I'm hitting from logs?)
- Cacheable (CDNs need to distinguish versions)

URL versioning (/v1/users) wins here — it's dead simple. Every HTTP client handles different base URLs trivially. It's visible in every log line and access log. CDNs cache /v1/users and /v2/users separately with no config.

**Third-party integrator perspective:**
Third parties read your docs and build integrations. They want:
- Clear migration guides between versions
- Long deprecation windows
- Easy-to-understand which version they're using

Again URL versioning is clearest. `Accept: application/vnd.myapi.v2+json` is confusing and easy to get wrong. Query params (?version=2) feel hacky and get lost in copy-paste.

**Backend developer perspective:**
How do you route requests to different handler versions?
- URL: trivial — different route registrations, can even be different services
- Header: need middleware to parse and route, more complex
- Query param: awkward, pollutes the query namespace

URL versioning makes it easiest to run versions as separate deployments during migration.

**API purist/REST perspective:**
URL versioning "violates REST" because the resource identity changes (/v1/users/123 vs /v2/users/123 are "different resources" but represent the same user). Header versioning is "more RESTful" because the resource stays the same, only the representation changes.

But... pragmatism beats purity. Nobody has ever lost a customer because their API wasn't RESTful enough. Many have lost customers because their versioning was confusing.

**DevOps/infrastructure perspective:**
URL versioning enables:
- Separate deployments per version (blue/green between versions)
- Load balancer routing by path prefix
- Independent scaling of old vs new versions
- Clean shutdown of deprecated versions (just stop the v1 service)

Header/query versioning requires the same deployment to handle all versions, coupling their lifecycles.

**Conclusion:**
URL path versioning wins on almost every practical dimension. The REST purity argument is academically interesting but irrelevant in practice.
</think>

Use **URL path versioning** (`/v1/`, `/v2/`). It wins on every practical dimension despite being "less RESTful" in theory.

## Implementation Strategy

```python
# FastAPI example — clean version separation
from fastapi import FastAPI, APIRouter

app = FastAPI()

# Version 1 routes
v1 = APIRouter(prefix="/v1")

@v1.get("/users/{user_id}")
async def get_user_v1(user_id: int):
    user = await fetch_user(user_id)
    return {"id": user.id, "name": user.name}  # flat response

# Version 2 routes — breaking changes
v2 = APIRouter(prefix="/v2")

@v2.get("/users/{user_id}")
async def get_user_v2(user_id: int):
    user = await fetch_user(user_id)
    return {  # nested response with more data
        "data": {
            "id": user.id,
            "profile": {"display_name": user.name, "avatar_url": user.avatar},
        },
        "meta": {"api_version": "2", "deprecated_fields": []},
    }

app.include_router(v1)
app.include_router(v2)
```

## Versioning Policy

1. **Only version on breaking changes** — additive changes (new fields, new endpoints) don't need a new version
2. **Support N-1 versions minimum** — when v3 launches, v2 stays active, v1 enters deprecation
3. **12-month deprecation window** — announce, warn via `Sunset` header, then shut down:

```python
from fastapi import Response

@v1.get("/users/{user_id}")
async def get_user_v1(user_id: int, response: Response):
    response.headers["Sunset"] = "Sat, 01 Mar 2025 00:00:00 GMT"
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '</v2/users/{user_id}>; rel="successor-version"'
    # ... normal response
```

4. **Version the entire API, not individual endpoints** — `/v2/` means the whole surface, even unchanged endpoints. This prevents the confusion of "which version is /users on?"

## Why Not the Others

| Approach | Downside |
|----------|----------|
| Header (`Accept: application/vnd.api.v2+json`) | Invisible in logs/URLs, hard to debug, CDN cache complications, confusing for integrators |
| Query param (`?version=2`) | Gets lost in copy-paste, pollutes query namespace, feels like a filter not a version |
| No versioning (evolve in place) | Works only if you never make breaking changes — unrealistic for real APIs |

URL versioning is boring and obvious, which is exactly what you want for infrastructure that third parties depend on.'''
    ),
    (
        "thinking/multiperspective-testing-pyramid",
        "Our team writes mostly end-to-end tests with Selenium. They're slow, flaky, and hard to maintain. Someone suggested we flip to mostly unit tests. But our unit tests never seem to catch real bugs — they just test mocks. What's the right testing strategy?",
        r'''<think>
The classic testing pyramid debate. But the user's experience reveals something deeper — both extremes have failed them. Let me analyze from multiple perspectives.

**The "mostly E2E" experience (their current state):**
- Slow: Selenium tests take minutes each, full suite takes hours
- Flaky: timing issues, network dependencies, browser quirks cause random failures
- Expensive to maintain: UI changes break dozens of tests
- But they DO catch real integration bugs that unit tests miss
- The trust problem: team trusts E2E results more because they test "real" behavior

**The "mostly unit tests" experience (what was suggested):**
- Fast: thousands run in seconds
- Reliable: no external dependencies
- But... "they just test mocks" — this is a REAL problem, not a skill issue
- A unit test that mocks the database, mocks the HTTP client, and mocks the filesystem is testing nothing but the glue code between mocks
- Passing unit tests give false confidence — "all green" but the app is broken

**The integration test perspective (the missing middle):**
The real gap is integration tests — tests that verify components work together WITHOUT going through the full UI. These are the highest-value tests that most teams under-invest in.

**The "testing trophy" perspective (Kent C. Dodds):**
Instead of a pyramid (many unit, some integration, few E2E), use a trophy shape:
- Static analysis (types, linting) at the base
- MOST tests are integration tests
- Some unit tests for complex logic
- Few E2E tests for critical paths

This resonates with the user's experience — unit tests of trivial code are low value, E2E tests are expensive. Integration tests are the sweet spot.

**The pragmatic/economic perspective:**
What's the cost of a bug in each layer?
- Logic bug caught by unit test: cheapest to fix
- Integration bug caught by integration test: moderate cost
- Bug caught by E2E test: expensive (slow feedback loop)
- Bug caught in production: most expensive

But what's the cost of WRITING and MAINTAINING each test type?
- Unit test: cheap to write, cheap to maintain, but may not catch real bugs
- Integration test: moderate to write, moderate to maintain, catches real bugs
- E2E test: expensive to write, expensive to maintain, catches real bugs

**ROI maximization says: integration tests first, unit tests for complex logic, E2E for critical paths only.**

**The "test the boundaries" perspective:**
The problem with "unit test everything" is that bugs live at boundaries — between your code and the database, between services, between user input and your validation. Mocking those boundaries means you're specifically NOT testing where bugs live.
</think>

Your instinct is right: both extremes are failing you. The answer is **integration tests as the primary layer**, not unit tests OR E2E tests.

## The Problem With Both Extremes

```
Your current state:          What was suggested:
   ╱╲                            ╱╲
  ╱E2E╲  ← slow, flaky        ╱ E2E╲  ← almost none
 ╱──────╲                     ╱───────╲
╱ Integration ╲ ← too few    ╱ Integr. ╲ ← too few
╱──────────────╲             ╱───────────╲
   Unit tests   ← too few   ╱ Unit tests  ╲ ← test mocks
                             ╱───────────────╲
```

**Both neglect integration tests**, which is where real bugs actually live.

## The Right Strategy: Testing Trophy

```python
# LAYER 1: Static analysis (free, catches typos and type errors)
# Use mypy/pyright, ESLint, ruff — this is your first defense

# LAYER 2: Integration tests (YOUR PRIMARY INVESTMENT)
# Test real components together, but without a browser

import pytest
from httpx import AsyncClient
from app.main import app
from app.database import get_test_db

@pytest.fixture
async def client():
    """Real app, real database (test instance), real HTTP."""
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture(autouse=True)
async def clean_db():
    """Reset DB between tests — fast with transactions."""
    async with get_test_db() as db:
        await db.begin()
        yield db
        await db.rollback()  # Instant cleanup

async def test_user_registration_and_login(client):
    """Integration test: real app + real DB, no browser."""
    # Register
    resp = await client.post("/api/register", json={
        "email": "test@example.com", "password": "secure123"
    })
    assert resp.status_code == 201
    user_id = resp.json()["id"]

    # Login with those credentials
    resp = await client.post("/api/login", json={
        "email": "test@example.com", "password": "secure123"
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()

    # Verify the token works
    token = resp.json()["access_token"]
    resp = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    assert resp.json()["id"] == user_id


# LAYER 3: Unit tests ONLY for complex pure logic
# Don't unit test CRUD. Don't unit test glue code. Don't mock everything.
# DO unit test: algorithms, calculations, parsing, business rules

def test_pricing_calculation():
    """Unit test: pure logic, no mocks needed."""
    cart = Cart(items=[
        Item("widget", price=10.00, qty=3),
        Item("gadget", price=25.00, qty=1),
    ])
    cart.apply_discount(PercentDiscount(10))

    assert cart.subtotal == 55.00
    assert cart.discount_amount == 5.50
    assert cart.total == 49.50
    assert cart.tax(rate=0.08) == 3.96


# LAYER 4: E2E tests ONLY for critical user journeys
# Maximum 10-20 E2E tests for the entire app
# Cover: signup, login, core purchase flow, payment

# Use Playwright (faster than Selenium) for the few E2E tests you keep
```

## Migration Plan From Your Current State

1. **Identify your top 5 critical user paths** — these keep E2E tests
2. **Delete all other E2E tests** (yes, delete them)
3. **Rewrite deleted E2E tests as integration tests** — same scenarios, but hitting the API directly without a browser
4. **Add unit tests only for complex business logic** — pricing, permissions, scheduling algorithms

## The Rule of Thumb

| Test type | When to use | Roughly |
|-----------|-------------|---------|
| Static analysis | Always, everything | automated |
| Integration | Default choice for any feature test | 60-70% |
| Unit | Complex logic, algorithms, calculations | 20-30% |
| E2E | Critical money/data paths only | 5-10% |

The reason "unit tests just test mocks" is because you're unit testing code that's mostly glue between components. That glue only breaks when components interact — which is exactly what integration tests verify.'''
    ),
    (
        "thinking/multiperspective-onboarding-dx",
        "New developers joining our team take 2-3 weeks to make their first commit. Our codebase is a large Django monolith with custom middleware, celery tasks, and multiple third-party integrations. How do we improve developer onboarding?",
        r'''<think>
2-3 weeks to first commit is a serious productivity problem. Let me think about this from multiple perspectives.

**New developer's perspective:**
What's happening during those 2-3 weeks?
- Days 1-3: Setting up the development environment (Docker, env vars, database seeding, third-party service credentials)
- Days 4-7: Reading documentation (if it exists), trying to understand the architecture
- Days 8-10: Getting assigned a task, trying to find where the relevant code lives
- Days 11-15: Making changes, not sure if they work, waiting for code review from someone who knows the codebase
- The emotional experience: overwhelmed, afraid to break things, impostor syndrome

**Tech lead perspective:**
The onboarding investment is real:
- Senior devs spend 5-10 hours/week helping new hires
- Knowledge is tribal — lives in Slack threads and people's heads
- "Just read the code" doesn't work for a large Django monolith
- But writing documentation feels like wasted time because it goes stale

**Business perspective:**
If developers cost $150k/year, 2-3 weeks of unproductive time = $6k-9k per hire. For a team that hires 10 people/year, that's $60-90k in lost productivity. Plus the hidden cost: some good developers leave during this period because they think the codebase is a mess.

**DevOps perspective:**
Most onboarding time is environment setup. If `docker compose up` doesn't get a working system in under 10 minutes, that's the #1 problem to fix. Every third-party integration needs a local mock or sandbox.

**Architecture perspective:**
A monolith that's hard to onboard onto has a discoverability problem. New developers can't form a mental model of the system. The custom middleware and Celery tasks are probably undocumented side effects that surprise people.

Let me think about what actually moves the needle most...

The highest-impact changes, in order:
1. One-command dev environment setup (eliminates days 1-3)
2. Architecture decision records + system map (eliminates days 4-7)
3. "Starter tasks" with exact file pointers (eliminates days 8-10)
4. Fast CI + preview environments (eliminates days 11-15)
</think>

The 2-3 week onboarding is solvable. Here's the high-impact plan, ordered by ROI:

## 1. One-Command Dev Setup (Eliminates Days 1-3)

```yaml
# docker-compose.yml — EVERYTHING needed to run locally
services:
  app:
    build: .
    command: python manage.py runserver 0.0.0.0:8000
    volumes:
      - .:/app
    env_file: .env.dev  # Checked into repo, no secrets
    depends_on:
      db: {condition: service_healthy}
      redis: {condition: service_healthy}
      celery: {condition: service_started}
    ports: ["8000:8000"]

  db:
    image: postgres:16
    environment:
      POSTGRES_DB: myapp_dev
      POSTGRES_PASSWORD: devpassword
    volumes:
      - ./scripts/seed_dev_data.sql:/docker-entrypoint-initdb.d/seed.sql
    healthcheck:
      test: pg_isready -U postgres
      interval: 2s
      retries: 10

  redis:
    image: redis:7-alpine
    healthcheck:
      test: redis-cli ping
      interval: 2s

  celery:
    build: .
    command: celery -A config worker -l info
    volumes: [".:/app"]
    env_file: .env.dev
    depends_on:
      db: {condition: service_healthy}
      redis: {condition: service_healthy}

  # Mock third-party services locally
  stripe-mock:
    image: stripe/stripe-mock:latest
    ports: ["12111:12111"]

  mailhog:
    image: mailhog/mailhog
    ports: ["8025:8025"]  # Web UI for email testing
```

```makefile
# Makefile — the only file new devs need to read
.PHONY: setup dev test

setup:  ## First-time setup (run this on day 1)
	cp .env.example .env.dev
	docker compose build
	docker compose run --rm app python manage.py migrate
	docker compose run --rm app python manage.py seed_dev_data
	@echo "✓ Ready! Run 'make dev' to start."

dev:  ## Start everything
	docker compose up

test:  ## Run test suite
	docker compose exec app pytest --tb=short

shell:  ## Django shell
	docker compose exec app python manage.py shell_plus
```

**Goal: `git clone && make setup && make dev` in under 10 minutes.**

## 2. System Map (Eliminates Days 4-7)

Create ONE file — `ARCHITECTURE.md` — that gives the mental model:

```markdown
# System Architecture

## Request Flow
Browser → nginx → Django middleware stack → Views → Services → Models → PostgreSQL
                                          ↘ Celery tasks → Redis (broker) → Workers

## Directory Map (where to find things)
apps/
  accounts/     → User auth, profiles, permissions
  orders/       → Order lifecycle, checkout, payments (Stripe)
  inventory/    → Product catalog, stock management
  notifications/ → Email (SendGrid), SMS (Twilio), push

config/
  settings/     → base.py (shared), dev.py, prod.py
  middleware.py  → RequestID, TenantContext, RateLimiting
  celery.py     → Celery app config

## Key Patterns
- All business logic in services.py (not views, not models)
- Custom middleware adds `request.tenant` and `request.request_id`
- Celery tasks are fire-and-forget; use `task.apply_async(countdown=X)` for delays
- Payments go through `apps/orders/services/payment_service.py` — never call Stripe directly

## The 5 Things That Surprise New Developers
1. TenantMiddleware silently filters all querysets by tenant — you'll never see cross-tenant data
2. `@audit_log` decorator on views auto-logs to the audit table
3. Celery tasks retry 3x by default (see config/celery.py)
4. Dev environment uses stripe-mock, not real Stripe
5. `python manage.py seed_dev_data` creates a test user: admin@dev.local / password123
```

## 3. Starter Task System (Eliminates Days 8-10)

```markdown
## Starter Tasks (label: "good-first-issue" in your issue tracker)

Each starter task includes:
- [ ] Exact file(s) to modify
- [ ] Related test file to update
- [ ] Link to similar past PR as reference
- [ ] Name of team member to ask if stuck

Example: "Add `last_login_ip` field to User profile"
- Modify: apps/accounts/models.py (User model)
- Migration: python manage.py makemigrations accounts
- Test: apps/accounts/tests/test_models.py
- Similar PR: #1234
- Ask: @sarah
```

## 4. Fast Feedback Loop (Eliminates Days 11-15)

- **Pre-commit hooks**: `ruff check` + `ruff format` so style issues never reach code review
- **CI under 10 minutes**: if it's slower, parallelize or split the test suite
- **PR template** with checklist so reviewers don't block on formatting issues

## Measuring Success

Track "time to first merged PR" for each new hire. Target: **under 5 working days**. The investment in onboarding tooling pays for itself after 2-3 hires.'''
    ),
    (
        "thinking/multiperspective-feature-flags",
        "Should we implement feature flags in our application? We're a team of 8 developers working on a B2B SaaS product with ~500 enterprise customers. We deploy twice a week. Some people think feature flags add unnecessary complexity.",
        r'''<think>
Feature flags for a B2B SaaS — let me evaluate from multiple perspectives.

**Product manager perspective:**
Enterprise customers often need:
- Gradual rollouts ("let's test with 10 customers first")
- Customer-specific features (enterprise tier vs standard)
- Kill switches for features that cause issues
- Beta programs for strategic customers
Without feature flags, every feature is all-or-nothing at deploy time. That's terrifying with 500 enterprise customers where one broken feature could mean a churned $100K/year account.

**Developer perspective (pro):**
- Trunk-based development: merge to main even with incomplete features behind flags
- No long-lived feature branches that become merge nightmares
- Confident deploys: ship code dark, enable later
- Instant rollback of a feature without a full deployment

**Developer perspective (anti):**
- Feature flags are `if` statements scattered through the codebase
- Dead flags accumulate (flag was turned on 6 months ago, nobody removed the check)
- Testing complexity doubles — every flag combination is a potential state
- "Temporary" flags become permanent
- Debugging: "why does this work for customer A but not B?" → flag state investigation

**Operations perspective:**
- Feature flags enable decoupling deploy from release — deploy is technical (ship code), release is business (enable feature)
- Incident response: toggle a flag instead of emergency deploy
- But: flag state is now runtime configuration that needs to be tracked, versioned, and auditable

**Architecture perspective:**
- With 8 developers and twice-weekly deploys, you DON'T need a sophisticated system
- Don't buy LaunchDarkly ($$$) when a database table + admin panel suffices
- Flag evaluation needs to be fast — don't add a network call per flag check

**The "unnecessary complexity" argument:**
Valid if: you only have 2-3 features in flight, deploys are fast and safe, you can roll back quickly.
Invalid if: you have enterprise customers with different needs, features need gradual rollout, or incidents require instant disable.

For 500 enterprise customers with B2B SaaS? Feature flags are necessary, not optional. The complexity argument loses to the risk argument.

But the complexity concerns ARE real — you need hygiene practices to prevent flag debt.
</think>

For 500 enterprise customers on B2B SaaS, feature flags aren't optional — they're risk management. But the complexity concerns are valid, so you need a disciplined approach.

## Start Simple: Database-Backed Flags

Don't buy a third-party service yet. Build the minimum:

```python
# models.py
from django.db import models

class FeatureFlag(models.Model):
    name = models.CharField(max_length=100, unique=True, db_index=True)
    enabled_globally = models.BooleanField(default=False)
    enabled_for_customers = models.ManyToManyField(
        "Customer", blank=True, related_name="feature_flags"
    )
    rollout_percentage = models.IntegerField(default=0)  # 0-100
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateField(
        null=True, blank=True,
        help_text="Flag must be cleaned up by this date"
    )
    owner = models.CharField(max_length=100, help_text="Developer responsible for cleanup")

    def is_enabled_for(self, customer) -> bool:
        if self.enabled_globally:
            return True
        if self.enabled_for_customers.filter(id=customer.id).exists():
            return True
        if self.rollout_percentage > 0:
            return (hash(f"{self.name}:{customer.id}") % 100) < self.rollout_percentage
        return False


# flags.py — the only interface your code uses
from functools import lru_cache
from django.core.cache import cache

def flag_enabled(flag_name: str, customer) -> bool:
    """Check if a feature flag is enabled for a customer. Cached 60s."""
    cache_key = f"ff:{flag_name}:{customer.id}"
    result = cache.get(cache_key)
    if result is not None:
        return result

    try:
        flag = FeatureFlag.objects.get(name=flag_name)
        result = flag.is_enabled_for(customer)
    except FeatureFlag.DoesNotExist:
        result = False

    cache.set(cache_key, result, timeout=60)
    return result
```

## Usage Pattern — Keep It Clean

```python
# views.py — feature flag usage
from app.flags import flag_enabled

def dashboard_view(request):
    context = {"customer": request.customer}

    if flag_enabled("new_analytics_dashboard", request.customer):
        context["analytics"] = get_new_analytics(request.customer)
        template = "dashboard/v2.html"
    else:
        context["analytics"] = get_legacy_analytics(request.customer)
        template = "dashboard/v1.html"

    return render(request, template, context)
```

## The Hygiene Rules (Prevents Complexity Debt)

1. **Every flag has an owner and expiry date** — enforced at creation time
2. **Maximum flag lifetime: 90 days** — after that, it's either fully on (remove flag, keep code) or fully off (remove flag AND code)
3. **Weekly flag audit** — a cron job that alerts on expired flags:

```python
# management/commands/audit_flags.py
from datetime import date

class Command(BaseCommand):
    def handle(self, **options):
        expired = FeatureFlag.objects.filter(expires_at__lt=date.today())
        for flag in expired:
            self.stderr.write(
                f"EXPIRED FLAG: {flag.name} (owner: {flag.owner}, "
                f"expired: {flag.expires_at})"
            )
        if expired.exists():
            send_slack_alert(f"{expired.count()} feature flags past expiry!")
```

4. **Maximum 15 active flags at any time** — if you need a 16th, clean up an old one first
5. **Flags in tests**: test BOTH paths explicitly

## When to Upgrade to a Service

Stay with the DB approach until you need:
- A/B testing with statistical analysis
- Flags that change sub-second (real-time)
- Non-developer flag management (PM self-serve)
- More than 50 concurrent flags

At your scale (8 devs, 500 customers, 2x/week deploys), the simple approach will serve you for years.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
