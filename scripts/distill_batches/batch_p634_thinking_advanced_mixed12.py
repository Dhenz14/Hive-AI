"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 12)"""

PAIRS = [
    (
        "thinking/backtrack-god-class-to-composition",
        "Our UserService class has 3000 lines and 50+ methods. It handles registration, authentication, profile updates, notifications, permissions, billing, and analytics. How do I refactor this?",
        r'''<think>
God class with too many responsibilities. Let me think about approaches.

**First approach: split by method groups**
Group related methods and move them to separate files:
- auth methods → auth_service.py
- billing methods → billing_service.py
- notification methods → notification_service.py

But wait — just moving methods to different files doesn't change the coupling. If they all share the same state (self.db, self.user_cache, etc.), you've just split one file into many without real separation.

**Let me backtrack to: identify actual responsibilities**

The Single Responsibility Principle says a class should have one reason to change. This UserService has at least 7 reasons to change:
1. Registration flow changes → change UserService
2. Auth method changes → change UserService
3. Billing provider changes → change UserService
4. Notification channel changes → change UserService
5. Permission model changes → change UserService
6. Analytics requirements change → change UserService
7. Profile fields change → change UserService

Each of these should be its own service.

**The right approach: composition**
Break UserService into focused services, each with a single responsibility. Then compose them where needed.
</think>

First I thought about splitting methods into files. Then I backtracked — the real fix is **separating responsibilities through composition**.

## The Problem

```python
# ❌ God class: 3000 lines, 50+ methods, 7 responsibilities
class UserService:
    def __init__(self, db, cache, email_client, stripe, analytics):
        self.db = db
        self.cache = cache
        self.email = email_client
        self.stripe = stripe
        self.analytics = analytics

    # Registration (responsibility 1)
    def register(self, email, password): ...
    def verify_email(self, token): ...
    def resend_verification(self, user_id): ...

    # Authentication (responsibility 2)
    def login(self, email, password): ...
    def logout(self, session_id): ...
    def refresh_token(self, token): ...
    def reset_password(self, email): ...

    # Profile (responsibility 3)
    def update_profile(self, user_id, data): ...
    def upload_avatar(self, user_id, file): ...
    def get_profile(self, user_id): ...

    # Notifications (responsibility 4)
    def send_welcome_email(self, user_id): ...
    def send_password_reset(self, email): ...
    def update_notification_prefs(self, user_id, prefs): ...

    # Permissions (responsibility 5)
    def check_permission(self, user_id, action): ...
    def assign_role(self, user_id, role): ...
    def get_permissions(self, user_id): ...

    # Billing (responsibility 6)
    def create_subscription(self, user_id, plan): ...
    def cancel_subscription(self, user_id): ...
    def update_payment_method(self, user_id, card): ...

    # Analytics (responsibility 7)
    def track_login(self, user_id): ...
    def get_user_activity(self, user_id): ...
    def generate_usage_report(self, user_id): ...
    # ... 30 more methods
```

## The Fix: Separate Services

```python
# ✅ Each service has ONE responsibility

class AuthService:
    """Handles authentication only."""
    def __init__(self, db, token_service):
        self.db = db
        self.tokens = token_service

    def login(self, email, password): ...
    def logout(self, session_id): ...
    def refresh_token(self, token): ...
    def reset_password(self, email): ...


class ProfileService:
    """Handles user profile data only."""
    def __init__(self, db, storage):
        self.db = db
        self.storage = storage

    def get_profile(self, user_id): ...
    def update_profile(self, user_id, data): ...
    def upload_avatar(self, user_id, file): ...


class BillingService:
    """Handles subscriptions and payments only."""
    def __init__(self, db, payment_provider):
        self.db = db
        self.payments = payment_provider

    def create_subscription(self, user_id, plan): ...
    def cancel_subscription(self, user_id): ...
    def update_payment_method(self, user_id, card): ...


class NotificationService:
    """Handles all user notifications."""
    def __init__(self, email_client, push_client):
        self.email = email_client
        self.push = push_client

    def send_welcome(self, user_id): ...
    def send_password_reset(self, email): ...


class PermissionService:
    """Handles authorization and roles."""
    def __init__(self, db):
        self.db = db

    def check_permission(self, user_id, action): ...
    def assign_role(self, user_id, role): ...
```

## Composing Services in Route Handlers

```python
# Route handlers use the specific service(s) they need

@app.post("/register")
async def register(data: RegisterRequest):
    user = await auth_service.register(data.email, data.password)
    await notification_service.send_welcome(user.id)
    await analytics_service.track_event("user_registered", user.id)
    return {"id": user.id}

@app.post("/subscribe")
async def subscribe(data: SubscribeRequest, user=Depends(get_current_user)):
    subscription = await billing_service.create_subscription(user.id, data.plan)
    return {"subscription_id": subscription.id}

# Each endpoint uses only the services it needs.
# No god object. Clear dependencies.
```

## Migration Strategy (Don't Rewrite Everything)

```python
# Step 1: Extract ONE responsibility at a time
# Start with the most independent one (e.g., notifications)

# OLD: UserService.send_welcome_email()
# NEW: NotificationService.send_welcome()

# Step 2: Update callers to use new service
# Old: user_service.send_welcome_email(user_id)
# New: notification_service.send_welcome(user_id)

# Step 3: Delete the method from UserService
# Repeat for each responsibility

# Step 4: What's left in UserService is the core user operations
# (probably just CRUD on the users table)

# Timeline: extract one service per sprint
# In 7 sprints, UserService is just a thin data access layer
```'''
    ),
    (
        "thinking/causal-high-error-rate-after-deploy",
        "We deployed a new version and our error rate jumped from 0.1% to 15%. The code changes look correct. Tests passed in CI. Staging was fine. What could cause errors only in production?",
        r'''<think>
Tests pass, staging fine, production broken. The code changes are "correct" — so what's different about production?

**Causal analysis: what differs between staging and production?**

1. **Data**: Production has real data. Edge cases, corrupted records, null values that test/staging data doesn't have.

2. **Scale**: Production has 100x the traffic. Race conditions, connection pool exhaustion, timeout thresholds that only manifest under load.

3. **Configuration**: Different env vars, different feature flags, different API keys, different database size.

4. **Dependencies**: Production talks to real external services (payment, email, etc.). Different API versions, rate limits, behavior.

5. **State**: Production database has 5 years of data. Staging has a recent snapshot or seed data. Old data might not conform to new code assumptions.

6. **Infrastructure**: Different server specs, different network topology, different load balancer config.

**Most common causes of "works in staging, fails in prod":**

1. Data assumption violation: new code assumes a column is NOT NULL but production has old rows with NULLs
2. Missing database migration: migration ran in staging but failed silently in production
3. Feature flag / config mismatch: a feature enabled in staging but configured differently in production
4. External service API version: staging uses sandbox API, production uses live API with different behavior
5. Scale-related: N+1 queries that are fast with staging's 1000 rows but timeout with production's 10M rows

The 15% error rate (not 100%) suggests it's data-dependent — only some requests hit the problematic code path.
</think>

Tests passing and staging working means the issue is **environmental**. Let me trace the likely causes.

## Diagnostic Framework: What's Different About Production?

```
The code is the SAME everywhere. What differs:

  STAGING           vs    PRODUCTION
  ────────────────────────────────────
  1,000 rows              10,000,000 rows
  Seed data (clean)       5 years of real data (messy)
  10 requests/sec         1,000 requests/sec
  Sandbox APIs            Live APIs
  Recent config           Possibly stale config
  Fresh migrations        Migration might have failed
```

## Most Likely: Data Assumption Violations (15% = Some Rows)

```python
# 15% error rate means SOME data triggers the bug, most doesn't.
# This strongly suggests: new code assumes something about data
# that's true for most rows but not all.

# EXAMPLE 1: Null values in old data
# New code:
def get_display_name(user):
    return user.first_name.strip() + " " + user.last_name.strip()
    # AttributeError: 'NoneType' has no attribute 'strip'
    # 15% of users registered before 2020 have NULL first_name

# FIX:
def get_display_name(user):
    first = (user.first_name or "").strip()
    last = (user.last_name or "").strip()
    return f"{first} {last}".strip() or user.email

# EXAMPLE 2: Data type mismatch
# New code expects integer, old data has string:
total = order.amount * quantity
# TypeError: can't multiply sequence by non-int
# Old orders stored amount as string "29.99" not decimal 29.99
```

## Diagnostic Steps

```bash
# 1. Check error logs for the SPECIFIC error
# What exception? What line? What input caused it?
grep "ERROR" /var/log/app/error.log | tail -50
# Look for: the stack trace tells you EXACTLY what failed

# 2. Check if migration ran successfully
python manage.py showmigrations | grep "\[ \]"
# Any unchecked migrations? They might not have applied in production.

# 3. Compare production config to staging
diff <(ssh staging env | sort) <(ssh production env | sort)
# Look for: missing env vars, different feature flags, wrong API keys

# 4. Check error distribution
# Is it ALL endpoints or specific ones?
# Is it ALL users or users with specific characteristics?
# GROUP BY to find the pattern:
SELECT
    request_path,
    COUNT(*) as errors
FROM error_logs
WHERE timestamp > NOW() - INTERVAL '1 hour'
GROUP BY request_path
ORDER BY errors DESC;
```

## Immediate Fix: Rollback (Then Investigate)

```bash
# If error rate is 15%, FIRST rollback to stop the bleeding:
# Deploy the previous version
git revert HEAD
git push  # Or: deploy the previous Docker image

# Error rate should drop back to 0.1%

# THEN investigate:
# 1. Look at the specific errors from the failed deploy
# 2. Find the data that triggers the bug
# 3. Fix the code to handle that data
# 4. Write a test with that specific data case
# 5. Redeploy with the fix
```

## Prevention

```python
# 1. Test with production-like data
# Don't test with perfect seed data. Test with messy real data:
# - NULL values in optional fields
# - Empty strings where you expect content
# - Unicode characters, emoji, RTL text
# - Very long strings (1000+ characters)
# - Old records with legacy data formats

# 2. Canary deploys
# Deploy new version to 5% of traffic first
# Monitor error rate for 10 minutes
# If OK → gradually increase to 100%
# If NOT OK → automatic rollback

# 3. Feature flags for new code paths
# Instead of deploying directly:
if feature_flags.is_enabled("new_display_name"):
    return new_get_display_name(user)
else:
    return old_get_display_name(user)
# Enable for 5% of users → monitor → enable for 100%
```'''
    ),
    (
        "thinking/abstraction-monitoring-alerting-to-observability",
        "We have server monitoring with CloudWatch and PagerDuty alerts. But when something goes wrong, we still spend hours figuring out WHAT went wrong. How do I improve our debugging speed?",
        r'''<think>
They have monitoring (metrics + alerts) but can't debug quickly. Let me ladder this up.

**Concrete: their current setup**
CloudWatch metrics (CPU, memory, error count) + PagerDuty alerts when thresholds are breached.

This tells them THAT something is wrong but not WHAT or WHY.

**Pattern: the three pillars of observability**
1. Metrics: numeric measurements over time (CPU, request count, error rate)
   → Good for: detecting problems, dashboards, alerting
   → Bad for: understanding WHY something broke

2. Logs: timestamped text records of events
   → Good for: detailed debugging, understanding what happened
   → Bad for: aggregation, correlation across services

3. Traces: request flow across services with timing
   → Good for: understanding WHERE time is spent, which service is slow
   → Bad for: broad patterns (better for individual request debugging)

They have metrics (pillar 1). They probably have basic logs (pillar 2 partially). They likely don't have traces (pillar 3).

**Principle: observability = being able to ask ANY question about your system without deploying new code**

**Policy: every service should emit structured logs, metrics, and traces by default**
</think>

You have monitoring (THAT something is wrong). You need observability (WHAT and WHY).

## Level 1: Your Current State

```
WHAT YOU HAVE (monitoring):
  CloudWatch: CPU is 95%! Error rate is 15%!
  PagerDuty: ALERT! Something is wrong!

  This tells you: "your house is on fire"
  This DOESN'T tell you: "the kitchen stove was left on"

WHAT YOU NEED (observability):
  "Error rate spiked at 14:32"
  → "It's the /api/orders endpoint"
  → "Specifically orders with promo codes"
  → "The promo-validation service is timing out"
  → "Because its database connection pool is exhausted"
  → "Because migration 47 added a slow query without an index"

  Time to root cause: 5 minutes instead of 2 hours.
```

## Level 2: The Three Pillars

```
PILLAR 1: METRICS (you have this)
  "CPU is 95%", "Error rate is 15%", "Latency p99 is 2s"
  Good for: detecting problems, dashboards, SLA tracking
  Tools: CloudWatch, Prometheus, Datadog

PILLAR 2: STRUCTURED LOGS (you probably need this)
  {"level": "error", "path": "/api/orders", "user_id": 42,
   "error": "connection pool exhausted", "service": "promo-validator"}
  Good for: understanding WHAT happened and to WHOM
  Tools: ELK Stack, Loki, CloudWatch Logs (with structured format)

PILLAR 3: DISTRIBUTED TRACES (you probably need this)
  Request #abc123:
    → API Gateway: 5ms
    → Order Service: 15ms
    → Promo Validator: 1,800ms ← BOTTLENECK
      → Database query: 1,750ms ← ROOT CAUSE
    → Payment Service: 45ms
  Good for: understanding WHERE time is spent across services
  Tools: Jaeger, Zipkin, AWS X-Ray, Datadog APT
```

## Level 3: Practical Implementation

```python
# ADD STRUCTURED LOGGING (biggest bang for the buck)
import structlog

logger = structlog.get_logger()

@app.middleware("http")
async def observability_middleware(request, call_next):
    request_id = request.headers.get("X-Request-ID", str(uuid4()))
    start = time.perf_counter()

    # Bind context that appears in ALL log messages for this request
    structlog.contextvars.bind_contextvars(
        request_id=request_id,
        path=request.url.path,
        method=request.method,
        user_id=getattr(request.state, 'user_id', None),
    )

    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000

    logger.info("request_completed",
        status=response.status_code,
        duration_ms=round(duration_ms),
    )
    # Output: {"event": "request_completed", "request_id": "abc123",
    #          "path": "/api/orders", "method": "POST", "user_id": 42,
    #          "status": 500, "duration_ms": 1823}

    return response

# Now when an alert fires, you can search:
#   status=500 AND path="/api/orders" → see all failed order requests
#   request_id="abc123" → see every log line for one request
#   user_id=42 → see everything that happened to this user
```

## Level 4: Debugging Workflow

```
BEFORE (2 hours to debug):
  1. PagerDuty: "Error rate > 5%"
  2. Check CloudWatch dashboard: yep, errors are up
  3. SSH into servers, grep logs
  4. "Which service? Which endpoint?"
  5. Read unstructured log files manually
  6. Eventually find the error after correlating timestamps

AFTER (5 minutes to debug):
  1. PagerDuty: "Error rate > 5% on /api/orders"
     (alert includes which endpoint — because metrics have labels)
  2. Dashboard: error rate for /api/orders spiked at 14:32
     (Grafana/Datadog dashboard with per-endpoint metrics)
  3. Search logs: status=500 path=/api/orders time>14:32
     → "promo_validator timeout after 5000ms"
  4. Search traces: find a slow request → trace shows:
     → promo_validator → database query 4800ms
  5. Check that query: missing index on promo_codes.code column
  6. Add index. Error rate drops to 0. Done.
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
