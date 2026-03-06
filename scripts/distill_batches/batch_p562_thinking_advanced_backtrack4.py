"""Phase 2A: Advanced Reasoning — Backtracking & Dead-End Recovery (Part 4/5)
More complex backtracking: parsing fails → state machine, ORM fails → raw SQL,
microservice fails → modular monolith, validation fails → type system."""

PAIRS = [
    (
        "thinking/backtrack-orm-fails-raw-sql",
        "I'm trying to write a complex report query using Django ORM but the generated SQL is terrible — it creates 4 subqueries where 1 window function would do. The report takes 30 seconds. Should I drop the ORM entirely?",
        r'''<think>
Let me analyze this. The user's ORM-generated SQL is slow because it can't express window functions naturally. But "drop the ORM entirely" is probably an overreaction.

My first thought: the ORM approach failed for this query. But that doesn't mean we should abandon the ORM everywhere. The correct backtracking is:

1. Try ORM → fails (can't express window functions efficiently)
2. Try raw SQL for THIS query → works
3. Keep ORM for everything else

This is the 80/20 principle: use the ORM for 80% of queries (simple CRUD), use raw SQL for the 20% that need optimization.

Let me think about when ORM fails:
- Window functions (ROW_NUMBER, LAG, LEAD, running totals)
- Complex CTEs
- LATERAL joins
- Recursive queries
- Database-specific features (JSONB operators, full-text search)
- Bulk operations (COPY, INSERT ... ON CONFLICT)

But the ORM wins at:
- Simple CRUD (95% of queries)
- Protection against SQL injection
- Migration management
- Model validation
- Relationship management

The key insight: don't choose ORM OR raw SQL. Use both. Django explicitly supports raw queries via .raw() and connection.cursor().
</think>

Don't drop the ORM entirely — use raw SQL for **this query** while keeping the ORM for everything else. The ORM failed at one task; that doesn't make it wrong for the other 95%.

**Why the ORM-generated SQL is terrible for this report**:
```python
# Django ORM attempt — generates 4 nested subqueries
report = (
    Order.objects
    .values('customer_id')
    .annotate(
        total=Sum('amount'),
        rank=Window(  # Django 3.0+ supports this, but it's limited
            expression=RowNumber(),
            partition_by=F('region'),
            order_by=F('total').desc()
        ),
        prev_month=Subquery(  # Subquery for each row — O(n²)
            Order.objects.filter(
                customer_id=OuterRef('customer_id'),
                date__month=OuterRef('date__month') - 1,
            ).values('customer_id').annotate(t=Sum('amount')).values('t')
        ),
    )
)
# Generated SQL: 4 correlated subqueries, 30 seconds
```

**The fix — raw SQL for this specific query**:
```python
from django.db import connection

def get_monthly_report(region_id: int, month: date) -> list[dict]:
    """Complex report: use raw SQL where the ORM can't express it efficiently."""
    with connection.cursor() as cursor:
        cursor.execute("""
            WITH monthly_totals AS (
                SELECT
                    customer_id,
                    region_id,
                    DATE_TRUNC('month', order_date) AS month,
                    SUM(amount) AS total,
                    LAG(SUM(amount)) OVER (
                        PARTITION BY customer_id
                        ORDER BY DATE_TRUNC('month', order_date)
                    ) AS prev_month_total
                FROM orders
                WHERE region_id = %s
                  AND order_date >= %s - INTERVAL '2 months'
                  AND order_date < %s + INTERVAL '1 month'
                GROUP BY customer_id, region_id, DATE_TRUNC('month', order_date)
            )
            SELECT
                customer_id,
                total,
                prev_month_total,
                total - COALESCE(prev_month_total, 0) AS growth,
                ROW_NUMBER() OVER (ORDER BY total DESC) AS rank
            FROM monthly_totals
            WHERE month = %s
            ORDER BY total DESC
            LIMIT 100
        """, [region_id, month, month, month])

        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

# Time: 200ms (vs 30 seconds with ORM)
```

**Keep the ORM for everything else**:
```python
# Simple CRUD — ORM is perfect
order = Order.objects.create(customer=customer, amount=99.99)
orders = Order.objects.filter(customer=customer, status='active')
order.status = 'shipped'
order.save()

# Even moderately complex queries — ORM is fine
top_customers = (
    Order.objects
    .values('customer__name')
    .annotate(total=Sum('amount'))
    .order_by('-total')[:10]
)
```

**The rule: ORM for CRUD, raw SQL for reports**. Not "ORM vs raw SQL" — use both. Django explicitly supports this with `connection.cursor()` and `Model.objects.raw()`.'''
    ),
    (
        "thinking/backtrack-microservice-needs-modular-monolith",
        "We're a team of 4 developers building an MVP. The architect wants microservices from day 1 because 'we'll need to scale later.' We're spending more time on infrastructure (Docker, Kubernetes, service mesh, API gateways) than on product features. Is this right?",
        r'''<think>
This is a classic case of premature architecture. Let me think through why microservices fail for small teams on MVPs.

The microservice overhead for 4 developers:
- Each service needs: its own repo, CI/CD pipeline, deployment config, monitoring
- Inter-service communication: API contracts, serialization, network calls
- Distributed tracing: need to correlate requests across services
- Data consistency: no database transactions across services
- Kubernetes: cluster management, ingress, service discovery, secrets
- Service mesh: sidecar proxies, mTLS, traffic routing

For 4 developers building an MVP, this infrastructure work easily consumes 50-70% of their time. The "product" is 3 services with 2 API endpoints each, running on a $500/month Kubernetes cluster.

A modular monolith would:
- Be one deployable unit
- Have internal module boundaries (same as microservice boundaries, but in-process)
- Take 5 minutes to deploy (not 30 minutes across 3 services)
- Allow database transactions for consistency
- Be extractable into microservices LATER if needed

The Martin Fowler approach: "Monolith First" — build a well-structured monolith, THEN extract services when you have clear evidence of what needs to scale independently.

My first thought was "maybe microservices make sense for specific technical reasons," but for 4 developers on an MVP? No. The team size and product stage make this clearly wrong.

However, a MODULAR monolith is key — not a spaghetti monolith. Internal boundaries, clear interfaces between modules, separate database schemas per module. This makes future extraction easy.
</think>

**No. For 4 developers on an MVP, microservices are premature optimization of architecture.** You're optimizing for a scale problem you don't have, at the cost of velocity on the problems you do have.

**The math**:
```
Team of 4, microservices from day 1:
  Infrastructure work: 50-70% of engineering time
    - Docker configs, K8s manifests, CI/CD per service
    - Service discovery, API gateways, health checks
    - Distributed tracing, centralized logging
    - Inter-service auth, contract testing

  Product work: 30-50% of engineering time
    - The actual features users care about

Team of 4, modular monolith:
  Infrastructure work: 10-15% of engineering time
    - One deploy pipeline, one database, one server

  Product work: 85-90% of engineering time
    - Ship features 3x faster
```

**The right approach: modular monolith** (microservice boundaries without microservice overhead):
```python
# Project structure: modules with clear boundaries
myapp/
├── orders/              # Module 1: Order management
│   ├── models.py        # Order-specific models
│   ├── service.py       # OrderService (public API of this module)
│   ├── repository.py    # Data access
│   └── routes.py        # HTTP endpoints
├── payments/            # Module 2: Payment processing
│   ├── models.py
│   ├── service.py       # PaymentService (public API)
│   ├── repository.py
│   └── routes.py
├── notifications/       # Module 3: Email/SMS
│   ├── service.py       # NotificationService (public API)
│   └── routes.py
└── shared/              # Shared utilities only
    ├── auth.py
    └── config.py

# KEY RULE: Modules communicate through SERVICE INTERFACES, not direct DB access
# orders/service.py can call payments.service.charge()
# orders/service.py CANNOT import payments.models or query payments tables directly
# This creates the same boundaries as microservices, without the network hop

class OrderService:
    def __init__(self, payment_service: PaymentService, notification_service: NotificationService):
        self.payments = payment_service
        self.notifications = notification_service

    async def create_order(self, data: dict) -> Order:
        order = await self.repo.create(data)
        # Cross-module calls are FUNCTION CALLS, not HTTP requests
        # When you extract to microservices later, these become API calls
        await self.payments.charge(order.total, order.payment_method)
        await self.notifications.send_order_confirmation(order)
        return order
```

**When to extract into microservices** (not now):
```
Extract WHEN you have evidence, not guesses:
✅ One module needs to scale independently (e.g., image processing → 100x CPU)
✅ One module has a different deployment cadence (deploys 10x/day vs 1x/week)
✅ Team grows to 15+ engineers and modules need team ownership
✅ One module needs a different tech stack (ML model in Python, API in Go)

DON'T extract because:
❌ "We might need to scale" (you probably won't — most startups don't)
❌ "Microservices are best practice" (for large orgs, not 4-person teams)
❌ "It's easier to test separately" (a well-structured monolith is easier to test)
```

**The modular monolith extracts cleanly when you're ready**:
```python
# TODAY (modular monolith): function call
result = await payment_service.charge(amount, method)

# LATER (if needed): extract to microservice, change to HTTP call
result = await httpx.post(f"{PAYMENT_SERVICE_URL}/charge", json={...})

# The interface stays the same — only the transport changes.
# This is a 1-day refactor per module, not a 6-month rewrite.
```

Martin Fowler: "Almost all successful microservice stories started with a monolith that got too big and was broken up." The unsuccessful ones started with microservices.'''
    ),
    (
        "thinking/backtrack-validation-needs-types",
        "We have runtime validation everywhere — checking types, checking null, checking string formats. It's 30% of our codebase. Tests catch some issues, but bugs still slip through when a function receives the wrong type. Is there a better approach?",
        r'''<think>
The user has a codebase where 30% of the code is defensive validation. That's a huge amount of boilerplate that:
1. Makes the code hard to read (business logic buried in checks)
2. Is never complete (always another edge case)
3. Runs at runtime (bugs in production instead of at build time)

My first thought: "just add more validation." But that makes the 30% grow to 40%.

Backtrack: the real problem is that the TYPE SYSTEM isn't doing its job. If the types are correct by construction, you don't need runtime checks.

Approaches:
1. Stronger type hints + mypy/pyright → catch type errors before runtime
2. Pydantic models for boundaries (API input, DB output) → validate at edges, trust internally
3. NewType and branded types → make invalid states unrepresentable
4. Algebraic data types (Union, Optional with exhaustive matching)

The key insight: validate at system BOUNDARIES (user input, API responses, file I/O), then trust types internally. This is the "parse, don't validate" principle.

Before: check everything everywhere → 30% validation code
After: validate at boundaries, use types internally → 5% validation code, more bugs caught
</think>

The problem isn't missing validation — it's that you're **validating at the wrong layer**. Validate once at the boundary, then trust types internally.

**The "Parse, Don't Validate" principle**:
```
BEFORE (validate everywhere):

    User Input → [validate] → Function A → [validate] → Function B → [validate] → DB
                                  ↑                          ↑
                            30% of code                 redundant checks

AFTER (parse at boundary, trust types):

    User Input → [PARSE into typed object] → Function A → Function B → DB
                        ↑                        ↑              ↑
                  ONE validation point      no checks needed   no checks needed
```

**Before: defensive validation everywhere**:
```python
# 30% of your codebase looks like this
def process_order(order_data):
    if order_data is None:
        raise ValueError("order_data is None")
    if not isinstance(order_data, dict):
        raise TypeError("order_data must be dict")
    if "items" not in order_data:
        raise ValueError("missing items")
    if not isinstance(order_data["items"], list):
        raise TypeError("items must be list")
    if len(order_data["items"]) == 0:
        raise ValueError("items cannot be empty")
    for item in order_data["items"]:
        if not isinstance(item, dict):
            raise TypeError("each item must be dict")
        if "price" not in item:
            raise ValueError("item missing price")
        if not isinstance(item["price"], (int, float)):
            raise TypeError("price must be number")
        if item["price"] < 0:
            raise ValueError("price must be non-negative")
    # ... 20 more lines of validation
    # ACTUAL BUSINESS LOGIC STARTS HERE (finally)
    total = sum(item["price"] * item["qty"] for item in order_data["items"])
```

**After: parse at boundary, typed objects internally**:
```python
from pydantic import BaseModel, Field
from decimal import Decimal

# STEP 1: Define types that CANNOT be invalid
class OrderItem(BaseModel):
    product_id: str
    price: Decimal = Field(ge=0)  # Non-negative by construction
    quantity: int = Field(ge=1)    # At least 1 by construction

class Order(BaseModel):
    customer_id: str
    items: list[OrderItem] = Field(min_length=1)  # Non-empty by construction

# STEP 2: Parse at the BOUNDARY (API endpoint)
@app.post("/orders")
async def create_order(order: Order):  # Pydantic validates automatically
    # If we reach here, order is GUARANTEED valid
    # No validation needed inside any function
    return await order_service.process(order)

# STEP 3: Internal functions receive TYPED objects — no validation needed
def calculate_total(items: list[OrderItem]) -> Decimal:
    # No need to check if items is None, empty, has price, etc.
    # The type system guarantees all of this.
    return sum(item.price * item.quantity for item in items)

def apply_discount(total: Decimal, discount_pct: Decimal) -> Decimal:
    # No need to check if total is negative or discount is > 100
    # The types flowing through the system are already valid.
    return total * (1 - discount_pct / 100)
```

**For even stronger guarantees — branded/NewType**:
```python
from typing import NewType

# These are DIFFERENT types — can't accidentally mix them up
CustomerId = NewType('CustomerId', str)
OrderId = NewType('OrderId', str)
ProductId = NewType('ProductId', str)

def get_order(order_id: OrderId) -> Order: ...
def get_customer(customer_id: CustomerId) -> Customer: ...

# This is a TYPE ERROR (caught by mypy, before runtime):
get_order(customer_id)  # Error: expected OrderId, got CustomerId

# Without NewType, this silently passes:
get_order(customer_id)  # Both are str, no error — but wrong!
```

**The result**:
```
Before: 30% validation code, bugs still slip through at runtime
After:  5% validation code (at boundaries only), bugs caught at type-check time
```

The principle: make invalid states **unrepresentable**. If a function only accepts `Order` (not `dict`), you can't pass invalid data. The type system does the validation, not your code.'''
    ),
    (
        "thinking/backtrack-cron-fails-needs-scheduler",
        "Our cron jobs keep running into each other. A daily report job takes 2 hours some days, and the next day's job starts before it finishes. We tried adding lock files but now jobs silently skip when the lock is held. What's the right approach?",
        r'''<think>
The user has a progression of problems:

1. Cron jobs overlap → race conditions, duplicate processing
2. Added lock files → now jobs skip silently, missing their window
3. Neither solution is satisfactory

Let me think about why cron is insufficient for this:

Cron is a TIME-based scheduler:
- "Run at 3 AM" regardless of what else is happening
- No concept of "wait for the previous run to finish"
- No dependency management (job B needs job A to finish first)
- No retry logic (if a job fails, nothing happens until tomorrow)
- No monitoring (did the job run? Did it succeed? How long did it take?)

The lock file approach papers over the symptom but introduces a worse problem: silent failures.

What they actually need:
- A TASK scheduler (not a TIME scheduler)
- That manages execution order and dependencies
- That retries on failure
- That monitors completion
- That handles overlap by queuing, not skipping

Options:
1. APScheduler (Python library, simple)
2. Celery Beat (for existing Celery setups)
3. Prefect/Dagster/Airflow (for complex data pipelines)
4. Simple database-backed job queue

For their use case (daily jobs that sometimes overlap), APScheduler with max_instances=1 is the simplest fix. It queues the next run instead of skipping it.
</think>

Cron is a **time scheduler** — it fires at a time, regardless of state. You need a **task scheduler** that manages execution state, overlap, and failure.

**Why each approach fails**:
```
Cron alone:           Jobs overlap when one takes longer than expected
Cron + lock file:     Jobs skip silently — you miss the daily report
Cron + "check lock":  Complex, error-prone, you're reinventing a task scheduler
```

**The fix — a task scheduler with execution awareness**:

```python
# Option 1: APScheduler (simplest, for straightforward needs)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

scheduler = AsyncIOScheduler()

@scheduler.scheduled_job(
    CronTrigger(hour=3),        # Target time: 3 AM
    max_instances=1,             # KEY: only 1 instance at a time
    coalesce=True,               # If missed, run once (not N times)
    misfire_grace_time=3600,     # Allow 1 hour of drift
)
async def daily_report():
    """If yesterday's run is still going, TODAY's run waits in queue."""
    logger.info("Starting daily report")
    try:
        report = await generate_report()
        await send_report(report)
        logger.info("Daily report completed")
    except Exception as e:
        logger.error(f"Daily report failed: {e}")
        raise  # APScheduler can be configured to retry

scheduler.start()
```

```python
# Option 2: Database-backed job queue (for more control)
from datetime import datetime, timedelta
import asyncio

class JobScheduler:
    """Simple job scheduler with overlap prevention and retry."""

    async def run_exclusive(self, job_name: str, job_func, timeout_hours: int = 4):
        """Run a job, preventing overlap. Waits if previous run is still going."""
        # Try to acquire lock (with timeout for stale locks)
        acquired = await self.db.execute("""
            INSERT INTO job_locks (job_name, started_at, status)
            VALUES ($1, NOW(), 'running')
            ON CONFLICT (job_name) DO UPDATE
            SET started_at = NOW(), status = 'running'
            WHERE job_locks.status != 'running'
               OR job_locks.started_at < NOW() - INTERVAL '$2 hours'
            RETURNING id
        """, job_name, timeout_hours)

        if not acquired:
            logger.warning(f"Job {job_name} is still running from previous invocation")
            # QUEUE instead of skip — record that we need to run
            await self.db.execute("""
                INSERT INTO job_queue (job_name, requested_at)
                VALUES ($1, NOW())
                ON CONFLICT (job_name) DO UPDATE SET requested_at = NOW()
            """, job_name)
            return

        try:
            start = datetime.utcnow()
            await job_func()
            duration = (datetime.utcnow() - start).total_seconds()

            await self.db.execute("""
                UPDATE job_locks
                SET status = 'completed', completed_at = NOW(), duration_seconds = $2
                WHERE job_name = $1
            """, job_name, duration)

            logger.info(f"Job {job_name} completed in {duration:.0f}s")

            # Check if there's a queued run
            queued = await self.db.fetch_one(
                "DELETE FROM job_queue WHERE job_name = $1 RETURNING requested_at",
                job_name
            )
            if queued:
                logger.info(f"Running queued {job_name} (requested at {queued['requested_at']})")
                await self.run_exclusive(job_name, job_func, timeout_hours)

        except Exception as e:
            await self.db.execute("""
                UPDATE job_locks
                SET status = 'failed', error = $2, completed_at = NOW()
                WHERE job_name = $1
            """, job_name, str(e))
            logger.error(f"Job {job_name} failed: {e}")
            raise


# Monitoring: see all jobs, their status, and duration
# SELECT job_name, status, started_at, completed_at, duration_seconds, error
# FROM job_locks ORDER BY started_at DESC;
```

**Why this is better than cron + lock files**:
```
Feature              | Cron + Lock | Task Scheduler
---------------------|-------------|------------------
Overlap prevention   | Skip (bad)  | Queue (wait for previous)
Failure handling     | Silent      | Logged, retryable
Monitoring           | None        | Job status, duration, errors
Stale lock recovery  | Manual      | Automatic timeout
Missed run detection | None        | Coalesce or queue
```

**When to graduate to Celery Beat or Airflow**: When you have 10+ scheduled jobs, complex dependencies (job B depends on job A), or need distributed execution across multiple workers.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
