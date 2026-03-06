"""Phase 2G: Advanced Reasoning — Abstraction Laddering (Part 4/6)"""

PAIRS = [
    (
        "thinking/abstraction-rate-limiting-to-resource-governance",
        "I keep adding rate limiting to different parts of our API — per-user limits, per-endpoint limits, per-IP limits. Each one is a separate implementation. How do I unify this?",
        r'''<think>
Let me climb the abstraction ladder from concrete implementations to the underlying principle.

**Concrete level — what they have:**
- Per-user rate limiting (token bucket per user ID)
- Per-endpoint rate limiting (sliding window per route)
- Per-IP rate limiting (fixed window per IP address)
Each is probably implemented separately with different algorithms, different storage, different configuration.

**Pattern level — what's common:**
All three are doing the same thing: tracking a count of events within a time window, associated with some key, and deciding allow/deny based on a threshold. The differences are:
- The KEY changes (user_id, endpoint, IP)
- The WINDOW changes (per-second, per-minute, per-hour)
- The LIMIT changes (100/min for users, 1000/min for endpoints)
- The ALGORITHM changes (token bucket, sliding window, fixed window)

**Principle level — what this really is:**
This is RESOURCE GOVERNANCE — controlling access to a shared resource based on identity, policy, and consumption. Rate limiting is one form. But so are:
- Quotas (monthly API call limits)
- Concurrency limits (max 10 simultaneous connections)
- Bandwidth throttling
- Cost budgets ("this customer can use $X of compute per month")

**Policy level — the abstraction:**
What they need is a Resource Governance Engine where:
- A RESOURCE is anything that can be consumed (API calls, compute, storage)
- A SUBJECT is the consumer (user, IP, API key, tenant)
- A POLICY defines the rules (limit, window, algorithm, action-on-exceed)
- A DECISION is the output (allow, deny, throttle, queue)

This unifies all their rate limiting AND opens the door to quotas, throttling, and cost governance without new implementations.
</think>

Your separate rate limiters are all instances of the same pattern. Let me walk up the abstraction ladder:

## The Ladder

```
POLICY:    Resource Governance — controlling consumption of shared resources
              ↑
PRINCIPLE: Track consumption by subject against a policy, decide allow/deny
              ↑
PATTERN:   Counter + key + window + threshold → decision
              ↑
CONCRETE:  per-user limit, per-endpoint limit, per-IP limit (your 3 implementations)
```

## The Unified Implementation

```python
from dataclasses import dataclass
from enum import Enum
from typing import Protocol
import time
import redis

class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    THROTTLE = "throttle"

@dataclass
class GovernancePolicy:
    """A single policy: who, what, how much, how often."""
    name: str
    limit: int
    window_seconds: int
    action_on_exceed: Decision = Decision.DENY

class GovernanceEngine:
    """Unified resource governance — replaces all separate rate limiters."""

    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client

    def check(self, subject: str, resource: str, policy: GovernancePolicy) -> Decision:
        """
        Check if a subject can access a resource under a policy.

        subject: "user:123", "ip:10.0.0.1", "apikey:abc"
        resource: "api:/users", "compute", "storage"
        """
        key = f"gov:{policy.name}:{subject}:{resource}"
        now = time.time()
        window_start = now - policy.window_seconds

        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)  # Clean old entries
        pipe.zcard(key)                                # Count current entries
        pipe.zadd(key, {str(now): now})               # Add this request
        pipe.expire(key, policy.window_seconds + 1)   # Auto-cleanup
        _, current_count, _, _ = pipe.execute()

        if current_count >= policy.limit:
            # Undo the add — we're over limit
            self.redis.zrem(key, str(now))
            return policy.action_on_exceed

        return Decision.ALLOW

    def remaining(self, subject: str, resource: str, policy: GovernancePolicy) -> int:
        """How many requests remain in the current window."""
        key = f"gov:{policy.name}:{subject}:{resource}"
        window_start = time.time() - policy.window_seconds
        self.redis.zremrangebyscore(key, 0, window_start)
        used = self.redis.zcard(key)
        return max(0, policy.limit - used)


# --- Define policies (replaces 3 separate implementations) ---

POLICIES = {
    "user_api": GovernancePolicy(
        name="user_api", limit=100, window_seconds=60
    ),
    "endpoint_global": GovernancePolicy(
        name="endpoint_global", limit=1000, window_seconds=60
    ),
    "ip_abuse": GovernancePolicy(
        name="ip_abuse", limit=50, window_seconds=10,
        action_on_exceed=Decision.DENY
    ),
    # New policies are just data — no new code needed
    "tenant_monthly_quota": GovernancePolicy(
        name="tenant_quota", limit=100_000, window_seconds=86400 * 30
    ),
}


# --- Middleware usage ---

def rate_limit_middleware(request, call_next):
    engine = GovernanceEngine(get_redis())

    # Check all applicable policies — same engine, different subjects
    checks = [
        (f"user:{request.user_id}", f"api:{request.path}", POLICIES["user_api"]),
        (f"endpoint:{request.path}", "global", POLICIES["endpoint_global"]),
        (f"ip:{request.client_ip}", "api", POLICIES["ip_abuse"]),
    ]

    for subject, resource, policy in checks:
        decision = engine.check(subject, resource, policy)
        if decision != Decision.ALLOW:
            remaining = engine.remaining(subject, resource, policy)
            return Response(
                status=429,
                headers={
                    "X-RateLimit-Limit": str(policy.limit),
                    "X-RateLimit-Remaining": str(remaining),
                    "X-RateLimit-Policy": policy.name,
                    "Retry-After": str(policy.window_seconds),
                }
            )

    return call_next(request)
```

## What You Gained

| Before (3 implementations) | After (1 engine + N policies) |
|---|---|
| 3 different algorithms | 1 sliding window (covers all cases) |
| 3 Redis key patterns | 1 consistent key pattern |
| Adding a new limit = new code | Adding a new limit = new policy dict entry |
| No unified rate limit headers | Consistent `X-RateLimit-*` headers |
| Can't answer "what are all our limits?" | `POLICIES` dict IS the answer |

The abstraction insight: rate limiting, quotas, and throttling are all **resource governance** — same engine, different policies. New governance rules are data, not code.'''
    ),
    (
        "thinking/abstraction-timeout-to-deadline-propagation",
        "I'm setting timeouts in different places — HTTP client timeouts, database query timeouts, cache timeouts, Celery task timeouts. But they don't coordinate. A 30s HTTP timeout calls a 30s database query, so the DB query might finish right as the HTTP request times out. How do I fix this?",
        r'''<think>
This is a real problem that most developers encounter. Let me climb the abstraction ladder.

**Concrete level — the problem:**
- HTTP client timeout: 30s
- Database query timeout: 30s
- Cache timeout: 5s
- Celery task timeout: 60s

When an HTTP request comes in with 30s timeout, it calls the DB with 30s timeout. If the DB takes 29s, the response arrives at the HTTP layer with 1s left — barely enough to serialize and send. If the DB takes 31s, the HTTP client already gave up but the DB is still working (wasted resources).

**Pattern level — what's wrong:**
Each timeout is set independently as an absolute value. But timeouts are RELATIVE — they should be "how much time do I have LEFT from my caller's perspective?"

**Principle level — deadline propagation:**
This is the concept Google calls "deadline propagation" in gRPC. Instead of each layer having its own timeout, you pass a DEADLINE (absolute point in time) through the call chain. Each layer computes its own timeout as `deadline - now - buffer`.

This is how gRPC context deadlines work, and it's the right abstraction.

**Policy level — resource budget management:**
Even more broadly, this is about BUDGET PROPAGATION. Time is one budget, but you could propagate:
- Time budget (deadline)
- Retry budget (max retries remaining across the chain)
- Cost budget (don't spend more than $X on this request)

Let me focus on the practical deadline propagation pattern since that's what they need.
</think>

The fix is **deadline propagation** — pass an absolute deadline through your call chain instead of setting independent timeouts.

## The Abstraction Ladder

```
POLICY:    Budget propagation — pass remaining resource budgets through call chains
              ↑
PRINCIPLE: Deadline propagation — a single absolute deadline flows through all layers
              ↑
PATTERN:   Each layer computes: my_timeout = deadline - now - buffer
              ↑
CONCRETE:  Your independent 30s/30s/5s/60s timeouts that don't coordinate
```

## Implementation

```python
import time
from contextvars import ContextVar
from dataclasses import dataclass

# Thread/async-safe deadline context
_deadline: ContextVar[float | None] = ContextVar("deadline", default=None)

@dataclass
class Deadline:
    """Propagated deadline through the call chain."""
    absolute_time: float  # Unix timestamp when we MUST be done

    @classmethod
    def from_timeout(cls, timeout_seconds: float) -> "Deadline":
        return cls(absolute_time=time.monotonic() + timeout_seconds)

    @property
    def remaining(self) -> float:
        """Seconds remaining before deadline."""
        return max(0, self.absolute_time - time.monotonic())

    @property
    def expired(self) -> bool:
        return self.remaining <= 0

    def timeout_for(self, buffer_seconds: float = 0.5) -> float:
        """Compute timeout for a sub-operation, reserving buffer for overhead."""
        remaining = self.remaining - buffer_seconds
        if remaining <= 0:
            raise DeadlineExceeded(
                f"Only {self.remaining:.1f}s left, need {buffer_seconds:.1f}s buffer"
            )
        return remaining

class DeadlineExceeded(TimeoutError):
    pass


def get_deadline() -> Deadline | None:
    return _deadline.get()

def set_deadline(timeout_seconds: float) -> Deadline:
    d = Deadline.from_timeout(timeout_seconds)
    _deadline.set(d)
    return d


# --- Middleware sets the deadline at the edge ---

async def deadline_middleware(request, call_next):
    """Set a request-wide deadline at the entry point."""
    set_deadline(25.0)  # 25s total budget for any request
    try:
        return await call_next(request)
    except DeadlineExceeded:
        return Response(status=504, body="Request deadline exceeded")


# --- Each layer respects the deadline ---

async def get_user_with_orders(user_id: int):
    deadline = get_deadline()

    # Database call: use remaining time minus buffer
    db_timeout = deadline.timeout_for(buffer_seconds=1.0)
    user = await db.execute(
        "SELECT * FROM users WHERE id = $1",
        user_id,
        timeout=db_timeout  # Might be 24s, 15s, or 3s depending on when we get here
    )

    # Cache check: use remaining time minus buffer
    cache_timeout = deadline.timeout_for(buffer_seconds=0.5)
    orders = await cache.get(
        f"orders:{user_id}",
        timeout=min(cache_timeout, 2.0)  # Cache should be fast; cap at 2s
    )

    if orders is None:
        # Another DB call: deadline keeps shrinking
        db_timeout = deadline.timeout_for(buffer_seconds=0.5)
        orders = await db.execute(
            "SELECT * FROM orders WHERE user_id = $1",
            user_id,
            timeout=db_timeout
        )

    return user, orders


# --- HTTP client calls propagate the deadline ---

async def call_payment_service(order_id: int):
    deadline = get_deadline()
    timeout = deadline.timeout_for(buffer_seconds=1.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(f"http://payments/orders/{order_id}")
        return resp.json()
```

## Before vs After

```
BEFORE (independent timeouts):
  HTTP request (30s timeout)
    └→ DB query (30s timeout)     ← Could use ALL 30s, leaving 0s for response
    └→ Cache lookup (5s timeout)  ← Fixed regardless of remaining time
    └→ HTTP call (30s timeout)    ← Could outlive the parent request

AFTER (deadline propagation):
  HTTP request (deadline = now + 25s)
    └→ DB query (timeout = 23.5s) ← Leaves 1.5s buffer
    └→ Cache lookup (timeout = min(remaining-0.5, 2.0))
    └→ HTTP call (timeout = remaining - 1.0)  ← Always fits within parent
```

The key insight: **timeouts are a budget, not a configuration.** Each layer spends from the same budget, and the budget only shrinks as it flows through the chain. This is how Google, AWS, and gRPC handle timeouts at scale.'''
    ),
    (
        "thinking/abstraction-error-handling-to-error-strategy",
        "Our codebase has try/except blocks everywhere, each handling errors differently. Some log and re-raise, some swallow errors, some return None, some return default values. It's impossible to predict what happens when something fails. How do I clean this up?",
        r'''<think>
Let me climb the abstraction ladder on error handling.

**Concrete level — the mess:**
```python
# Pattern 1: swallow and return None
try:
    user = db.get_user(id)
except Exception:
    user = None

# Pattern 2: log and re-raise
try:
    result = api.call()
except Exception as e:
    logger.error(f"API call failed: {e}")
    raise

# Pattern 3: return default
try:
    config = load_config()
except FileNotFoundError:
    config = DEFAULT_CONFIG

# Pattern 4: swallow silently
try:
    send_notification(user)
except Exception:
    pass
```

Each developer handles errors based on gut feeling. No consistency, no strategy.

**Pattern level — categorizing the behaviors:**
Looking at these, there are really only a few STRATEGIES for handling errors:
1. **Propagate** — let the caller deal with it (re-raise, maybe wrap)
2. **Recover** — provide a fallback value or behavior
3. **Absorb** — the operation is optional, failure is acceptable
4. **Transform** — convert to a domain-specific error

The problem isn't that they use different strategies — it's that the CHOICE of strategy is arbitrary. There's no policy for when to use which.

**Principle level — error handling strategy:**
The strategy should be determined by the CRITICALITY of the operation:
- CRITICAL operations (payments, data writes): propagate — never silently fail
- DEGRADABLE operations (recommendations, analytics): recover with fallback
- OPTIONAL operations (notifications, metrics): absorb — log and continue
- BOUNDARY operations (external APIs, user input): transform to domain errors

**Policy level — error contracts:**
Each function should have an explicit ERROR CONTRACT:
- What errors can it raise?
- What does the caller need to handle?
- What has already been handled internally?

This is what Java's checked exceptions tried to solve (badly), and what Rust's Result type solves (well). In Python, we can approximate with clear conventions.
</think>

The fix isn't better try/except blocks — it's an **error handling strategy** based on operation criticality. Here's the abstraction ladder:

```
POLICY:    Every function has an error contract — explicit about what it handles vs propagates
              ↑
PRINCIPLE: Error strategy depends on operation criticality, not developer preference
              ↑
PATTERN:   4 strategies: Propagate, Recover, Absorb, Transform
              ↑
CONCRETE:  Random try/except blocks with inconsistent behavior
```

## The Four Error Strategies

```python
import logging
from functools import wraps
from typing import TypeVar, Callable

T = TypeVar("T")
logger = logging.getLogger(__name__)


# --- Strategy 1: PROPAGATE (critical operations) ---
# Don't catch at all, or catch-log-reraise. Caller MUST handle.

def charge_payment(order_id: int, amount: float) -> str:
    """Process payment. Raises PaymentError on failure — caller must handle."""
    try:
        result = stripe.charges.create(amount=amount, currency="usd")
        return result.id
    except stripe.CardError as e:
        raise PaymentDeclined(str(e)) from e
    except stripe.StripeError as e:
        raise PaymentServiceError(str(e)) from e
    # No generic except — unknown errors propagate naturally


# --- Strategy 2: RECOVER (degradable operations) ---
# Provide a fallback. Caller gets a result either way.

def get_recommendations(user_id: int) -> list[Product]:
    """Get personalized recommendations. Falls back to popular items."""
    try:
        return recommendation_engine.for_user(user_id)
    except RecommendationError:
        logger.warning("Recommendation engine failed for user %s, using fallback", user_id)
        return get_popular_products(limit=10)


# --- Strategy 3: ABSORB (optional operations) ---
# Fire-and-forget. Failure is acceptable and expected.

def absorb_errors(operation_name: str):
    """Decorator for optional operations that should never break the main flow."""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except Exception:
                logger.warning("Optional operation '%s' failed", operation_name, exc_info=True)
                return None
        return wrapper
    return decorator

@absorb_errors("send_welcome_email")
def send_welcome_email(user_id: int):
    """Send welcome email. Failure doesn't affect registration."""
    email_service.send_template("welcome", user_id=user_id)


# --- Strategy 4: TRANSFORM (boundary operations) ---
# Convert external/raw errors into domain errors at system boundaries.

class UserNotFound(Exception):
    def __init__(self, user_id: int):
        self.user_id = user_id
        super().__init__(f"User {user_id} not found")

class UserServiceUnavailable(Exception):
    pass

def get_user(user_id: int) -> User:
    """Fetch user. Raises UserNotFound or UserServiceUnavailable."""
    try:
        row = db.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    except DatabaseConnectionError as e:
        raise UserServiceUnavailable() from e

    if row is None:
        raise UserNotFound(user_id)

    return User.from_row(row)
```

## The Decision Matrix

Apply this at code review — every try/except should match one strategy:

| Operation Type | Strategy | Example | What to do |
|---|---|---|---|
| Money, data writes, auth | **Propagate** | Payments, DB writes | Raise domain error |
| Has a reasonable fallback | **Recover** | Recommendations, cache | Log + return fallback |
| Truly optional side-effect | **Absorb** | Emails, metrics, analytics | Log warning + continue |
| System boundary (API, DB, user input) | **Transform** | External calls, parsing | Convert to domain error |

## The Cleanup Process

1. **Grep for bare `except Exception: pass`** — these are bugs. Each one needs a conscious decision: is this ABSORB (add logging) or should it PROPAGATE?

2. **Grep for `except Exception: return None`** — is `None` a valid return? If the caller doesn't check for `None`, this is a hidden bug. Usually should be PROPAGATE or RECOVER with an explicit fallback.

3. **Add the strategy as a comment** at each try/except during review:

```python
# RECOVER: cache miss is expected, fall back to DB
try:
    return cache.get(key)
except CacheError:
    logger.debug("Cache miss for %s", key)
    return db.get(key)
```

This makes error handling reviewable and consistent. New developers can look at the strategy comment and understand the intent immediately.'''
    ),
    (
        "thinking/abstraction-migrations-to-schema-evolution",
        "We keep having database migration problems. Migrations conflict when two developers modify the same model. Deployments fail because migrations run before the new code is ready. Rollbacks are terrifying because we don't have down migrations. How do I fix our migration process?",
        r'''<think>
Let me climb the abstraction ladder from migration mechanics to schema evolution strategy.

**Concrete level — their problems:**
1. Migration conflicts: two devs add a field to the same model, migrations have conflicting dependencies
2. Deploy ordering: migrations run before new code, or new code deploys before migrations
3. No down migrations: can't rollback schema changes

**Pattern level — what's really happening:**
These are symptoms of treating migrations as "files that Django generates." The real issues:
- Migrations are coupled to the deploy cycle (they shouldn't be)
- Schema changes and code changes happen atomically (they can't in production)
- Rollback strategy is an afterthought (it should be designed in)

**Principle level — schema evolution:**
Database schema changes must follow the expand-contract pattern:
1. EXPAND: add new schema (columns, tables) — backward compatible
2. MIGRATE: move data to new schema
3. CONTRACT: remove old schema — only after ALL code uses new schema

This means every breaking schema change becomes TWO non-breaking changes deployed separately.

**Policy level — safe schema evolution policy:**
- Schema changes and code changes are ALWAYS separate deployments
- Every schema change must be backward-compatible with the PREVIOUS version of the code
- Down migrations are unnecessary if you never make irreversible changes
- Conflicts are prevented by clear ownership boundaries
</think>

Your migration problems stem from treating schema changes as part of code deploys. The fix is the **expand-contract pattern** — separate schema evolution from code evolution.

## The Abstraction Ladder

```
POLICY:    Schema changes are always backward-compatible and deployed separately from code
              ↑
PRINCIPLE: Expand-Contract pattern — every breaking change becomes two safe changes
              ↑
PATTERN:   Add new → migrate data → remove old (never modify in place)
              ↑
CONCRETE:  Migration conflicts, deploy failures, scary rollbacks
```

## Expand-Contract in Practice

**Example: Rename `users.name` → `users.first_name` + `users.last_name`**

```python
# ❌ WRONG: One migration, one deploy (breaks everything)
# migrations/0045_rename_name_field.py
# operations = [RenameField("User", "name", "first_name"), AddField("User", "last_name")]
# This breaks all running code that references `name`

# ✅ RIGHT: Three deployments over 3 days

# --- Deploy 1: EXPAND (add new columns, keep old) ---
# migrations/0045_add_name_columns.py
from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [("users", "0044_previous")]
    operations = [
        migrations.AddField("User", "first_name",
            models.CharField(max_length=100, default="", blank=True)),
        migrations.AddField("User", "last_name",
            models.CharField(max_length=100, default="", blank=True)),
    ]

# Code: write to BOTH old and new columns
class User(models.Model):
    name = models.CharField(max_length=200)       # Old — still works
    first_name = models.CharField(max_length=100)  # New
    last_name = models.CharField(max_length=100)   # New

    def save(self, **kwargs):
        # Dual-write: keep old column in sync during transition
        if self.first_name and not self.name:
            self.name = f"{self.first_name} {self.last_name}".strip()
        super().save(**kwargs)


# --- Deploy 2: MIGRATE (backfill data, switch reads to new columns) ---
# migrations/0046_backfill_name_columns.py
def backfill_names(apps, schema_editor):
    User = apps.get_model("users", "User")
    for user in User.objects.filter(first_name="").iterator(chunk_size=1000):
        parts = user.name.split(" ", 1)
        user.first_name = parts[0]
        user.last_name = parts[1] if len(parts) > 1 else ""
        user.save(update_fields=["first_name", "last_name"])

class Migration(migrations.Migration):
    dependencies = [("users", "0045_add_name_columns")]
    operations = [migrations.RunPython(backfill_names, migrations.RunPython.noop)]

# Code: read from new columns, still write to both


# --- Deploy 3: CONTRACT (remove old column, after verifying all code uses new) ---
# migrations/0047_remove_old_name.py
class Migration(migrations.Migration):
    dependencies = [("users", "0046_backfill_name_columns")]
    operations = [
        migrations.RemoveField("User", "name"),
    ]
```

## Solving Your Three Problems

### Problem 1: Migration Conflicts

```python
# settings.py or team convention
# Rule: migrations are created on main, never on feature branches

# Workflow:
# 1. Developer makes model changes on feature branch
# 2. PR gets approved
# 3. Merge to main
# 4. On main: python manage.py makemigrations
# 5. Commit the migration
# 6. If conflict: python manage.py makemigrations --merge
```

### Problem 2: Deploy Ordering

```makefile
# Makefile — migrations ALWAYS run before code swap

deploy:
    # 1. Run migrations against current DB (backward-compatible!)
    python manage.py migrate --no-input
    # 2. Health check — verify old code still works with new schema
    curl -f http://localhost:8000/health
    # 3. Swap to new code
    supervisorctl restart app
    # 4. Health check new code
    curl -f http://localhost:8000/health
```

Because migrations are always backward-compatible (expand phase only adds), the old code works fine with the new schema.

### Problem 3: Rollbacks

With expand-contract, rollbacks are trivial:
- **Expand phase**: new columns exist but old code ignores them → rollback is safe, new columns are harmless
- **Migrate phase**: data is copied, old column still has valid data → rollback reads old column
- **Contract phase**: old column removed → this is the ONLY irreversible step, and by this point you've validated everything

You don't need down migrations because you never make destructive changes until you're 100% certain.

## The Safety Checklist

Before any migration merges:

- [ ] Is this migration backward-compatible with the currently deployed code?
- [ ] Can we rollback the code deploy without a schema rollback?
- [ ] For data migrations: is there a chunk_size to avoid locking the table?
- [ ] For column additions: does it have a default (to avoid table rewrite)?
- [ ] For column removals: has all code stopped referencing this column?'''
    ),
    (
        "thinking/abstraction-retries-to-resilience-budget",
        "Our microservices all have retry logic, but during outages the retries make things worse. Service A retries 3x to B, B retries 3x to C. So one failure at C causes 9 requests. Add more layers and it's exponential. How do I fix retry storms?",
        r'''<think>
This is the classic retry amplification problem. Let me ladder up.

**Concrete level — the problem:**
A → B → C, each with 3 retries.
C fails once → B retries 3x → A retries 3x (each retry to B triggers 3 to C) = 9 requests to C.
With 4 layers: 3^3 = 27 requests from one failure. This CAUSES the outage it's trying to survive.

**Pattern level — what's wrong:**
Each service has local retry logic that's reasonable in isolation. But retries are not composable — they multiply through the call chain. The system has no GLOBAL view of retry budget.

**Principle level — resilience budget:**
Instead of each service deciding independently, the system needs a SHARED BUDGET for retries. This is similar to deadline propagation — a remaining-retry-budget flows through the chain.

Google's approach: "retry budget" — each service tracks the ratio of retries to total requests. If retries exceed 10% of traffic, STOP retrying. This provides natural backpressure.

**Policy level — adaptive resilience:**
The broader principle is that resilience mechanisms (retries, timeouts, circuit breakers) must be COORDINATED across the system, not configured independently. They need to sense global system state and adapt.
</think>

Retry amplification is one of the most common causes of cascading failures. The fix is a **retry budget** — a system-wide limit on retry volume.

## The Abstraction Ladder

```
POLICY:    Resilience mechanisms must be coordinated, not independent
              ↑
PRINCIPLE: Retry budget — cap total retries as a percentage of traffic
              ↑
PATTERN:   Track retry ratio; stop retrying when budget exhausted
              ↑
CONCRETE:  3×3×3 = 27 requests from one failure (retry storm)
```

## Implementation: Retry Budget

```python
import time
import random
from collections import deque
from threading import Lock

class RetryBudget:
    """
    Limits retries to a percentage of total traffic.
    When retries exceed the budget, requests fail fast instead of amplifying.
    """

    def __init__(self, budget_ratio: float = 0.1, window_seconds: float = 60.0):
        """
        budget_ratio: max fraction of requests that can be retries (0.1 = 10%)
        window_seconds: sliding window for tracking
        """
        self.budget_ratio = budget_ratio
        self.window = window_seconds
        self._requests: deque[tuple[float, bool]] = deque()  # (timestamp, is_retry)
        self._lock = Lock()

    def _cleanup(self):
        cutoff = time.monotonic() - self.window
        while self._requests and self._requests[0][0] < cutoff:
            self._requests.popleft()

    def record_request(self, is_retry: bool = False):
        with self._lock:
            self._requests.append((time.monotonic(), is_retry))
            self._cleanup()

    def can_retry(self) -> bool:
        """Check if we're within retry budget."""
        with self._lock:
            self._cleanup()
            if not self._requests:
                return True  # No data yet, allow retry
            total = len(self._requests)
            retries = sum(1 for _, is_retry in self._requests if is_retry)
            return (retries / total) < self.budget_ratio


class ResilientClient:
    """HTTP client with retry budget, circuit breaker, and hedging."""

    def __init__(self, service_name: str, max_retries: int = 3):
        self.service_name = service_name
        self.max_retries = max_retries
        self.retry_budget = RetryBudget(budget_ratio=0.1)  # Max 10% retries
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0

    async def call(self, method: str, url: str, **kwargs) -> Response:
        # Circuit breaker check
        if time.monotonic() < self._circuit_open_until:
            raise CircuitOpen(f"{self.service_name} circuit is open")

        self.retry_budget.record_request(is_retry=False)

        last_error = None
        for attempt in range(1 + self.max_retries):
            if attempt > 0:
                # Check retry budget before retrying
                if not self.retry_budget.can_retry():
                    raise RetryBudgetExhausted(
                        f"{self.service_name}: retry budget exhausted, "
                        f"failing fast to prevent amplification"
                    )
                self.retry_budget.record_request(is_retry=True)

                # Exponential backoff with jitter
                delay = min(2 ** attempt + random.uniform(0, 1), 30)
                await asyncio.sleep(delay)

            try:
                resp = await self._do_request(method, url, **kwargs)
                self._consecutive_failures = 0
                return resp
            except RetryableError as e:
                last_error = e
                self._consecutive_failures += 1

                # Circuit breaker: open after 5 consecutive failures
                if self._consecutive_failures >= 5:
                    self._circuit_open_until = time.monotonic() + 30.0

        raise last_error


# --- Usage: replaces raw retry loops everywhere ---

payments = ResilientClient("payments", max_retries=2)
inventory = ResilientClient("inventory", max_retries=2)

async def process_order(order_id: int):
    # Each client manages its OWN retry budget independently
    # During an outage, retry budget fills up → requests fail fast
    # Instead of 3×3=9 requests, you get 1 request + 0-1 retries
    payment = await payments.call("POST", f"/charge/{order_id}")
    stock = await inventory.call("POST", f"/reserve/{order_id}")
    return payment, stock
```

## Before vs After

```
BEFORE (retry storm):
User → A (3 retries) → B (3 retries) → C (down)
= 1 × 3 × 3 = 9 requests to C per user request
= 10,000 users × 9 = 90,000 requests hammering C

AFTER (retry budget):
User → A (budget: 10%) → B (budget: 10%) → C (down)
= First few retries go through
= Budget fills up within seconds
= Subsequent requests fail fast at A
= C gets breathing room to recover
```

## The Three Coordinated Mechanisms

1. **Retry budget** (shown above): caps retry volume as % of traffic
2. **Circuit breaker**: stops ALL calls after consecutive failures
3. **Deadline propagation**: ensures retries don't outlive the caller's patience

These three together form a resilient system. Any one alone is insufficient — retries without budgets cause storms, circuit breakers without retries are too aggressive, and neither works without deadline awareness.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
