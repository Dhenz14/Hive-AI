"""Phase 2G: Advanced Reasoning — Abstraction Laddering (Part 5/6)"""

PAIRS = [
    (
        "thinking/abstraction-pagination-to-data-windowing",
        "I keep implementing pagination differently everywhere — offset-based for some endpoints, cursor-based for others, page-number for admin views. How do I unify this?",
        r'''<think>
Let me climb the abstraction ladder from specific pagination implementations to the underlying concept.

**Concrete level — what they have:**
- Offset pagination: `LIMIT 20 OFFSET 40` (page 3)
- Cursor pagination: `WHERE id > last_seen_id LIMIT 20`
- Page number: `?page=3&per_page=20`

Each is implemented separately with different APIs, different response formats, different query patterns.

**Pattern level — what's common:**
All three are doing the same thing: returning a WINDOW of data from a larger ordered set. The differences are how you SPECIFY the window:
- Offset: "skip N items, take M items"
- Cursor: "items after this marker, take M items"
- Page number: "page P of size M" (which is really offset = (P-1)*M)

**Principle level — data windowing:**
The concept is DATA WINDOWING — viewing a subset of an ordered collection through a movable frame. The window has:
- A POSITION (where in the dataset)
- A SIZE (how many items to show)
- A DIRECTION (forward, backward, or random access)
- An ORDERING (what determines the sequence)

**Policy level — the abstraction:**
A DataWindow interface that supports multiple positioning strategies:
- Random access (offset/page) — when you need to jump to arbitrary positions
- Sequential access (cursor) — when you're scrolling through results
- The response format should be unified regardless of positioning strategy
</think>

Your pagination variants are all instances of **data windowing** — viewing a subset of ordered data through a movable frame.

## The Abstraction Ladder

```
POLICY:    Data windowing — a movable frame over an ordered collection
              ↑
PRINCIPLE: Every window has: position, size, ordering, and navigation info
              ↑
PATTERN:   Position via offset, cursor, or page number
              ↑
CONCRETE:  3 separate pagination implementations
```

## The Unified Implementation

```python
from dataclasses import dataclass
from typing import TypeVar, Generic, Any
from enum import Enum

T = TypeVar("T")

class WindowStrategy(Enum):
    OFFSET = "offset"
    CURSOR = "cursor"
    PAGE = "page"

@dataclass
class WindowRequest:
    """Unified pagination request — works for any strategy."""
    size: int = 20
    # Offset-based
    offset: int | None = None
    # Page-based (converts to offset internally)
    page: int | None = None
    # Cursor-based
    cursor: str | None = None
    # Ordering
    order_by: str = "id"
    order_dir: str = "asc"

    @property
    def strategy(self) -> WindowStrategy:
        if self.cursor is not None:
            return WindowStrategy.CURSOR
        if self.page is not None:
            return WindowStrategy.PAGE
        return WindowStrategy.OFFSET

    @property
    def effective_offset(self) -> int:
        if self.page is not None:
            return (self.page - 1) * self.size
        return self.offset or 0

@dataclass
class WindowResponse(Generic[T]):
    """Unified pagination response — same format regardless of strategy."""
    items: list[T]
    total: int | None  # None for cursor-based (count is expensive)
    has_next: bool
    has_previous: bool
    # Navigation helpers (all optional, depends on strategy)
    next_cursor: str | None = None
    previous_cursor: str | None = None
    page: int | None = None
    total_pages: int | None = None

    def to_dict(self) -> dict:
        result = {
            "items": self.items,
            "has_next": self.has_next,
            "has_previous": self.has_previous,
        }
        if self.total is not None:
            result["total"] = self.total
        if self.page is not None:
            result["page"] = self.page
            result["total_pages"] = self.total_pages
        if self.next_cursor is not None:
            result["next_cursor"] = self.next_cursor
        if self.previous_cursor is not None:
            result["previous_cursor"] = self.previous_cursor
        return result


class DataWindow:
    """Apply a window to any SQLAlchemy query."""

    @staticmethod
    def apply(query, model, request: WindowRequest) -> WindowResponse:
        # Apply ordering
        order_col = getattr(model, request.order_by)
        if request.order_dir == "desc":
            query = query.order_by(order_col.desc())
        else:
            query = query.order_by(order_col.asc())

        if request.strategy == WindowStrategy.CURSOR:
            return DataWindow._cursor_window(query, model, request, order_col)
        else:
            return DataWindow._offset_window(query, model, request)

    @staticmethod
    def _offset_window(query, model, request: WindowRequest) -> WindowResponse:
        total = query.count()
        offset = request.effective_offset
        items = query.offset(offset).limit(request.size + 1).all()

        has_next = len(items) > request.size
        if has_next:
            items = items[:request.size]

        page = request.page or (offset // request.size + 1)
        total_pages = (total + request.size - 1) // request.size

        return WindowResponse(
            items=items, total=total,
            has_next=has_next, has_previous=offset > 0,
            page=page, total_pages=total_pages,
        )

    @staticmethod
    def _cursor_window(query, model, request: WindowRequest, order_col) -> WindowResponse:
        if request.cursor:
            cursor_value = decode_cursor(request.cursor)
            query = query.filter(order_col > cursor_value)

        items = query.limit(request.size + 1).all()
        has_next = len(items) > request.size
        if has_next:
            items = items[:request.size]

        next_cursor = encode_cursor(getattr(items[-1], request.order_by)) if has_next and items else None
        prev_cursor = request.cursor  # The current cursor IS the previous cursor

        return WindowResponse(
            items=items, total=None,  # No count for cursor pagination
            has_next=has_next, has_previous=request.cursor is not None,
            next_cursor=next_cursor, previous_cursor=prev_cursor,
        )


# --- Usage: one interface for all endpoints ---

@app.get("/api/orders")
def list_orders():
    query = db.query(Order).filter(Order.active == True)
    window = WindowRequest(
        size=int(request.args.get("size", 20)),
        page=request.args.get("page", type=int),
        cursor=request.args.get("cursor"),
        order_by=request.args.get("order_by", "created_at"),
        order_dir=request.args.get("order_dir", "desc"),
    )
    result = DataWindow.apply(query, Order, window)
    return jsonify(result.to_dict())
```

## What You Gained

| Before | After |
|--------|-------|
| 3 different pagination APIs | 1 unified `WindowRequest/WindowResponse` |
| Different response formats per endpoint | Same format everywhere |
| Adding cursor support = new implementation | Change one parameter |
| Frontend handles 3 pagination patterns | Frontend handles 1 pattern |

The abstraction insight: offset, cursor, and page-number pagination are all **data windowing** — same concept, different positioning strategies. Unify the interface, let the strategy be a parameter.'''
    ),
    (
        "thinking/abstraction-health-checks-to-observability-contract",
        "Our services have health check endpoints but they're all different. Some return 200 for 'up', some return JSON with component statuses, some check the database, some don't. During incidents, we waste time figuring out what each health check actually tells us. How do I standardize this?",
        r'''<think>
Let me climb the abstraction ladder from health checks to observability contracts.

**Concrete level — the mess:**
- Service A: `GET /health` → 200 OK (just proves the HTTP server is running)
- Service B: `GET /healthz` → `{"status": "ok", "db": "connected"}` (checks DB)
- Service C: `GET /ping` → "pong" (literally useless)
- Service D: `GET /health` → checks DB, cache, queue, external API (too many deps, often fails when external API is down)

**Pattern level — categories of health:**
Looking at these, there are really different TYPES of health:
1. **Liveness**: "Is the process running?" (restart if not)
2. **Readiness**: "Can it handle traffic?" (remove from load balancer if not)
3. **Startup**: "Has it finished initializing?" (don't check liveness until ready)
4. **Dependency health**: "Are its dependencies available?"

These are the Kubernetes probe categories, and they exist for a reason — each type triggers a different action.

**Principle level — observability contract:**
Each service should advertise a standardized OBSERVABILITY CONTRACT:
- What health dimensions it reports
- What each dimension means
- What action to take when each dimension is unhealthy
- What dependencies it considers critical vs optional

**Policy level:**
Health checks are part of a service's OPERATIONAL INTERFACE — as important as its API contract. They should be versioned, documented, and standardized.
</think>

Your health checks are all answering different questions. The fix is a standardized **health contract** with distinct probe types, each triggering a different operational response.

## The Abstraction Ladder

```
POLICY:    Observability contract — each service declares its operational interface
              ↑
PRINCIPLE: Three probe types: liveness, readiness, dependency health
              ↑
PATTERN:   Standardized response format with component status
              ↑
CONCRETE:  Random /health, /healthz, /ping endpoints returning different things
```

## The Standard

```python
from enum import Enum
from dataclasses import dataclass, field
from datetime import datetime
import asyncio

class HealthStatus(Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"  # Working but impaired
    UNHEALTHY = "unhealthy"

@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus
    message: str = ""
    response_time_ms: float | None = None

@dataclass
class HealthResponse:
    status: HealthStatus
    service: str
    version: str
    uptime_seconds: float
    components: list[ComponentHealth] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def to_dict(self) -> dict:
        return {
            "status": self.status.value,
            "service": self.service,
            "version": self.version,
            "uptime_seconds": self.uptime_seconds,
            "timestamp": self.timestamp,
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    **({"response_time_ms": c.response_time_ms} if c.response_time_ms else {}),
                }
                for c in self.components
            ],
        }

    @property
    def http_status(self) -> int:
        if self.status == HealthStatus.HEALTHY:
            return 200
        if self.status == HealthStatus.DEGRADED:
            return 200  # Still serving traffic
        return 503


class HealthChecker:
    """Standardized health checking with configurable components."""

    def __init__(self, service_name: str, version: str):
        self.service_name = service_name
        self.version = version
        self.start_time = datetime.utcnow()
        self._checks: dict[str, tuple] = {}  # name → (check_fn, critical)

    def add_check(self, name: str, check_fn, critical: bool = True):
        """Register a health check component.

        critical=True: failure makes service UNHEALTHY (remove from LB)
        critical=False: failure makes service DEGRADED (keep in LB, alert)
        """
        self._checks[name] = (check_fn, critical)

    async def check_all(self) -> HealthResponse:
        components = []
        overall = HealthStatus.HEALTHY

        for name, (check_fn, critical) in self._checks.items():
            start = datetime.utcnow()
            try:
                await asyncio.wait_for(check_fn(), timeout=5.0)
                elapsed = (datetime.utcnow() - start).total_seconds() * 1000
                components.append(ComponentHealth(
                    name=name, status=HealthStatus.HEALTHY,
                    response_time_ms=round(elapsed, 1)
                ))
            except Exception as e:
                elapsed = (datetime.utcnow() - start).total_seconds() * 1000
                status = HealthStatus.UNHEALTHY if critical else HealthStatus.DEGRADED
                components.append(ComponentHealth(
                    name=name, status=status,
                    message=str(e), response_time_ms=round(elapsed, 1)
                ))
                if critical and overall != HealthStatus.UNHEALTHY:
                    overall = HealthStatus.UNHEALTHY
                elif not critical and overall == HealthStatus.HEALTHY:
                    overall = HealthStatus.DEGRADED

        uptime = (datetime.utcnow() - self.start_time).total_seconds()
        return HealthResponse(
            status=overall, service=self.service_name,
            version=self.version, uptime_seconds=uptime,
            components=components,
        )


# --- Service setup ---

health = HealthChecker("order-service", version="2.4.1")

# Critical: if these fail, service can't function
health.add_check("database", check_postgres, critical=True)
health.add_check("redis", check_redis, critical=True)

# Non-critical: service is degraded but still works
health.add_check("email_service", check_email_api, critical=False)
health.add_check("analytics", check_analytics_api, critical=False)


# --- Three endpoints, three purposes ---

@app.get("/health/live")
async def liveness():
    """Liveness probe: is the process running?
    Kubernetes: restarts pod if this fails."""
    return {"status": "alive"}  # Always 200 if process is running

@app.get("/health/ready")
async def readiness():
    """Readiness probe: can it handle traffic?
    Load balancer: removes from pool if this fails."""
    result = await health.check_all()
    return JSONResponse(result.to_dict(), status_code=result.http_status)

@app.get("/health/detail")
async def health_detail():
    """Detailed health: for dashboards and debugging.
    NOT used by load balancers (too much information)."""
    result = await health.check_all()
    return JSONResponse(result.to_dict())
```

## Response Examples

```json
// GET /health/ready — 200 (healthy)
{
  "status": "healthy",
  "service": "order-service",
  "version": "2.4.1",
  "uptime_seconds": 86421.5,
  "components": [
    {"name": "database", "status": "healthy", "response_time_ms": 2.3},
    {"name": "redis", "status": "healthy", "response_time_ms": 0.8},
    {"name": "email_service", "status": "healthy", "response_time_ms": 45.2}
  ]
}

// GET /health/ready — 200 (degraded, still serving)
{
  "status": "degraded",
  "service": "order-service",
  "components": [
    {"name": "database", "status": "healthy", "response_time_ms": 2.1},
    {"name": "redis", "status": "healthy", "response_time_ms": 0.9},
    {"name": "email_service", "status": "unhealthy", "message": "Connection refused"}
  ]
}

// GET /health/ready — 503 (unhealthy, remove from LB)
{
  "status": "unhealthy",
  "service": "order-service",
  "components": [
    {"name": "database", "status": "unhealthy", "message": "Connection timed out"},
    {"name": "redis", "status": "healthy", "response_time_ms": 0.7}
  ]
}
```

## The Operational Contract

| Probe | URL | Checks | Failure Action |
|-------|-----|--------|---------------|
| Liveness | `/health/live` | Process alive | Restart container |
| Readiness | `/health/ready` | Critical deps | Remove from load balancer |
| Detail | `/health/detail` | All components | Dashboard / alerting |

Every service implements the same three endpoints, same response format, same semantics. During incidents, you know exactly what each health check tells you without reading source code.'''
    ),
    (
        "thinking/abstraction-permissions-to-policy-engine",
        "Our permission checks are scattered everywhere — some in views, some in serializers, some in model methods. We have role-based checks, ownership checks, and feature flag checks all mixed together. How do I clean this up?",
        r'''<think>
Let me climb the abstraction ladder from scattered permission checks to a policy engine.

**Concrete level — the mess:**
```python
# In views:
if request.user.role == 'admin' or request.user.id == obj.owner_id:
    ...

# In serializers:
if user.is_staff or user.has_perm('orders.view_financials'):
    data['revenue'] = obj.revenue

# In models:
def can_edit(self, user):
    return user.id == self.owner_id or user.role in ('admin', 'editor')
```

Each check is ad-hoc. No consistency, no auditability, hard to test.

**Pattern level — what's common:**
Every permission check answers the same question:
"Can SUBJECT perform ACTION on RESOURCE?"

The differences are in HOW the answer is determined:
- Role-based: subject's role allows the action
- Ownership: subject owns the resource
- Attribute-based: some property of subject/resource/context determines access
- Feature flags: feature is enabled for this subject

**Principle level — policy-based access control:**
All permission checks are POLICIES — rules that evaluate a (subject, action, resource) tuple and return allow/deny. Policies should be:
- Centralized (defined in one place)
- Composable (combine multiple rules)
- Testable (unit test policies independently)
- Auditable (log every decision)

**Policy level:**
A policy engine where:
- POLICIES are registered as functions
- The engine evaluates applicable policies for each request
- Decisions are logged for audit
- Policies are tested independently from the code they protect
</think>

Your scattered checks are all answering the same question: **"Can this subject perform this action on this resource?"** Centralize them into a policy engine.

## The Abstraction Ladder

```
POLICY:    All access decisions go through a central policy engine
              ↑
PRINCIPLE: Every check is: can(subject, action, resource) → allow/deny
              ↑
PATTERN:   Role checks, ownership checks, feature flags — all are policies
              ↑
CONCRETE:  if user.role == 'admin' scattered in 50 files
```

## The Implementation

```python
from dataclasses import dataclass
from typing import Any, Callable
from enum import Enum
import logging

logger = logging.getLogger("access_policy")

class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"
    ABSTAIN = "abstain"  # This policy doesn't apply

# A policy is a function: (subject, action, resource) → Decision
PolicyFn = Callable[[Any, str, Any], Decision]

class PolicyEngine:
    """Central access control — replaces scattered permission checks."""

    def __init__(self):
        self._policies: list[tuple[str, PolicyFn]] = []

    def register(self, name: str, policy_fn: PolicyFn):
        """Register a policy. Policies are evaluated in order."""
        self._policies.append((name, policy_fn))

    def can(self, subject, action: str, resource=None) -> bool:
        """Evaluate all policies. DENY wins over ALLOW (deny-overrides)."""
        decision = Decision.DENY  # Default deny
        deciding_policy = "default"

        for name, policy_fn in self._policies:
            result = policy_fn(subject, action, resource)
            if result == Decision.DENY:
                # Explicit deny always wins
                logger.info("ACCESS DENIED: %s -> %s on %s (policy: %s)",
                           subject, action, resource, name)
                return False
            if result == Decision.ALLOW:
                decision = Decision.ALLOW
                deciding_policy = name

        allowed = decision == Decision.ALLOW
        logger.info("ACCESS %s: %s -> %s on %s (policy: %s)",
                    "GRANTED" if allowed else "DENIED",
                    subject, action, resource, deciding_policy)
        return allowed


# --- Define policies as simple functions ---

engine = PolicyEngine()

# Policy 1: Admins can do everything
def admin_policy(user, action, resource):
    if hasattr(user, 'role') and user.role == 'admin':
        return Decision.ALLOW
    return Decision.ABSTAIN

# Policy 2: Owners can edit their own resources
def ownership_policy(user, action, resource):
    if action in ('edit', 'delete') and resource:
        if hasattr(resource, 'owner_id') and resource.owner_id == user.id:
            return Decision.ALLOW
    return Decision.ABSTAIN

# Policy 3: Role-based access
ROLE_PERMISSIONS = {
    'editor': {'view', 'edit', 'create'},
    'viewer': {'view'},
    'billing': {'view', 'view_financials'},
}

def role_policy(user, action, resource):
    permissions = ROLE_PERMISSIONS.get(user.role, set())
    if action in permissions:
        return Decision.ALLOW
    return Decision.ABSTAIN

# Policy 4: Suspended users can't do anything
def suspension_policy(user, action, resource):
    if hasattr(user, 'suspended') and user.suspended:
        return Decision.DENY  # Explicit DENY overrides all ALLOWs
    return Decision.ABSTAIN

# Register in order (deny policies should be first)
engine.register("suspension", suspension_policy)
engine.register("admin", admin_policy)
engine.register("ownership", ownership_policy)
engine.register("role", role_policy)


# --- Usage in views: clean and consistent ---

from functools import wraps

def requires(action: str):
    """Decorator for views — checks policy engine."""
    def decorator(view_fn):
        @wraps(view_fn)
        def wrapper(request, *args, **kwargs):
            resource = kwargs.get('obj')  # Set by middleware or fetched in view
            if not engine.can(request.user, action, resource):
                return JsonResponse({"error": "Forbidden"}, status=403)
            return view_fn(request, *args, **kwargs)
        return wrapper
    return decorator

@app.route("/orders/<int:order_id>", methods=["PUT"])
@requires("edit")
def update_order(request, order_id):
    # If we get here, the policy engine already approved the action
    ...

@app.route("/orders/<int:order_id>/financials")
@requires("view_financials")
def view_financials(request, order_id):
    ...
```

## What You Gained

| Before (scattered checks) | After (policy engine) |
|---|---|
| `if user.role == 'admin'` in 50 files | One `admin_policy` function |
| Can't answer "who can do what?" | Read the policies list |
| No audit trail | Every decision logged |
| Can't test permissions in isolation | Unit test each policy function |
| Adding a new role = edit 50 files | Add one entry to ROLE_PERMISSIONS |

The abstraction insight: role checks, ownership checks, and feature flags are all POLICIES. When you centralize them into a policy engine, the scattered `if` statements become a clean, testable, auditable access control system.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
