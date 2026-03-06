"""Phase 2G: Advanced Reasoning — Abstraction Laddering (Part 7/8)"""

PAIRS = [
    (
        "thinking/abstraction-circuit-breaker-to-fault-tolerance",
        "How do I implement a circuit breaker pattern for our API calls to a flaky third-party service?",
        r'''<think>
Circuit breaker — let me ladder this up from the concrete implementation to the abstract principle.

**Concrete level: Circuit breaker for one API call**
Three states: Closed (normal), Open (failing, reject immediately), Half-Open (testing recovery).
Track failure count, trip the breaker when threshold exceeded, reset after timeout.

**Pattern level: Circuit breaker as a general pattern**
This isn't just for API calls. It's for ANY operation that can fail repeatedly:
- Database queries
- File system operations
- Message queue publishing
- Even internal service calls

The pattern: "If something is failing, stop trying for a while instead of making things worse."

**Principle level: Fault tolerance through controlled degradation**
Circuit breakers are one tool in a broader toolkit:
- Circuit breaker: stop calling failing services
- Retry with backoff: try again, but slower
- Bulkhead: isolate failures so they don't cascade
- Timeout: don't wait forever
- Fallback: provide degraded service instead of no service

All of these are applications of the principle: "Failure is normal. Design for graceful degradation, not failure prevention."

**Policy level: Resilience engineering**
Systems should be resilient BY DEFAULT. This means:
- Every external dependency should have a circuit breaker
- Every network call should have a timeout
- Every critical path should have a fallback
- Monitoring should detect when circuit breakers trip

This is a design philosophy, not just a pattern.
</think>

Let me build this from concrete implementation up to the broader principle.

## Level 1: Concrete — Circuit Breaker Implementation

```python
import time
from enum import Enum
from functools import wraps

class CircuitState(Enum):
    CLOSED = "closed"        # Normal — requests flow through
    OPEN = "open"            # Failing — reject immediately
    HALF_OPEN = "half_open"  # Testing — allow one request to test recovery

class CircuitBreaker:
    def __init__(self, failure_threshold=5, recovery_timeout=30):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None

    def call(self, func, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN  # Try one request
            else:
                raise CircuitOpenError("Circuit is open — failing fast")

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        self.failure_count = 0
        self.state = CircuitState.CLOSED  # Reset to normal

    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN  # Trip the breaker


# Usage:
payment_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

def charge_customer(amount):
    try:
        return payment_breaker.call(payment_api.charge, amount)
    except CircuitOpenError:
        # Fail fast — don't even try calling the flaky service
        return queue_for_retry(amount)
```

## Level 2: Pattern — Circuit Breaker as Decorator

```python
# The pattern generalizes: any external call can be wrapped

def circuit_breaker(failure_threshold=5, recovery_timeout=30, fallback=None):
    breaker = CircuitBreaker(failure_threshold, recovery_timeout)

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return breaker.call(func, *args, **kwargs)
            except CircuitOpenError:
                if fallback:
                    return fallback(*args, **kwargs)
                raise
        wrapper.breaker = breaker  # Expose for monitoring
        return wrapper
    return decorator

# Apply to any external dependency:

@circuit_breaker(failure_threshold=3, recovery_timeout=60,
                 fallback=lambda q: cached_results(q))
def search_products(query):
    return elasticsearch_client.search(query)

@circuit_breaker(failure_threshold=5, recovery_timeout=120)
def send_email(to, subject, body):
    return smtp_client.send(to, subject, body)

@circuit_breaker(failure_threshold=2, recovery_timeout=300,
                 fallback=lambda user_id: {"plan": "free"})
def get_subscription(user_id):
    return billing_api.get_subscription(user_id)
```

## Level 3: Principle — Fault Tolerance Through Controlled Degradation

```
The circuit breaker is ONE tool. The broader principle:
"Failure is inevitable. Design for graceful degradation."

FAULT TOLERANCE TOOLKIT:

  CIRCUIT BREAKER — stop calling what's broken
    "The payment API failed 5 times → stop trying for 60 seconds"

  TIMEOUT — don't wait forever
    "If the API doesn't respond in 3 seconds, give up"

  RETRY WITH BACKOFF — try again, but slower
    "Failed? Wait 1s, retry. Failed? Wait 2s, retry. Wait 4s..."

  BULKHEAD — isolate failures
    "Payment API is slow → only use 5 of our 20 threads for payments
     so the other 15 can still serve product pages"

  FALLBACK — provide something instead of nothing
    "Can't reach recommendation engine → show popular products instead"

These COMPOSE together:

  Request → TIMEOUT(3s)
          → RETRY(3 attempts, exponential backoff)
          → CIRCUIT_BREAKER(5 failures → open)
          → BULKHEAD(max 5 concurrent calls)
          → FALLBACK(return cached/default)
```

## Level 4: Policy — Resilience as a Design Philosophy

```
Every external dependency MUST have:
  □ A timeout (no unbounded waits)
  □ A circuit breaker (stop hitting broken services)
  □ A fallback (degraded > down)
  □ Monitoring (know when breakers trip)

This isn't optional hardening — it's the DEFAULT way to call anything:

  # NOT: "call the API"
  # BUT: "call the API with timeout, retry, circuit breaker, and fallback"

  # In practice, use a library that composes these:
  # Python: tenacity + pybreaker
  # Java: Resilience4j
  # JavaScript: cockatiel / opossum
  # Go: sony/gobreaker + custom middleware

The mental model shift:
  OLD: "The API will work. Handle errors as exceptions."
  NEW: "The API will fail. Design for it."
```

## Monitoring (The Most Important Part)

```python
# A circuit breaker you can't observe is useless.
# You MUST know when breakers trip.

# Expose breaker state as metrics:
from prometheus_client import Gauge, Counter

breaker_state = Gauge('circuit_breaker_state', 'Circuit breaker state',
                      ['service'])
breaker_trips = Counter('circuit_breaker_trips_total', 'Times breaker tripped',
                        ['service'])

class ObservableCircuitBreaker(CircuitBreaker):
    def __init__(self, service_name, **kwargs):
        super().__init__(**kwargs)
        self.service_name = service_name

    def _on_failure(self):
        super()._on_failure()
        breaker_state.labels(self.service_name).set(
            1 if self.state == CircuitState.OPEN else 0
        )
        if self.state == CircuitState.OPEN:
            breaker_trips.labels(self.service_name).inc()
            alert_oncall(f"Circuit breaker OPEN for {self.service_name}")
```

The abstraction ladder: specific API call → reusable pattern → fault tolerance principle → resilience-by-default policy. Each level up makes the thinking applicable to more situations.'''
    ),
    (
        "thinking/abstraction-database-migration-to-schema-lifecycle",
        "How do I handle database migrations in production? We've been doing manual ALTER TABLE statements and it's nerve-wracking every deploy.",
        r'''<think>
Database migrations — let me ladder from the concrete problem to the abstract principle.

**Concrete: Manual ALTER TABLE is scary**
Why it's scary:
- ALTER TABLE can lock the table for minutes on large tables
- If it fails partway, the schema is in an unknown state
- No way to revert (there's no "un-ALTER TABLE")
- Hard to coordinate with application code deployment

**Pattern: Migration frameworks**
Django, Rails, Flyway, Alembic — all solve this with:
- Numbered migration files (001_add_users.sql, 002_add_email.sql)
- Track which migrations have run (in a migrations table)
- Run forward (apply) or backward (revert)
- Version control the schema changes alongside the code

**Principle: Schema as code, versioned and testable**
The database schema is a FIRST-CLASS ARTIFACT, just like application code.
It should be:
- Version controlled (migration files in git)
- Reviewed (PRs for schema changes)
- Tested (run migrations against test DB in CI)
- Reversible (each migration has an up AND down)
- Incremental (small changes, not big-bang alterations)

**Policy: Schema lifecycle management**
- Zero-downtime migrations (additive-only in production)
- Expand-contract pattern (add new → migrate data → remove old)
- Schema changes are separate deploys from code changes
- Migration review process for large tables
</think>

Let me build from your immediate problem up to the broader principle.

## Level 1: Concrete — Migration Framework Basics

```python
# Instead of manual ALTER TABLE, use a migration framework.
# Example: Alembic (Python/SQLAlchemy) or Django migrations

# Generate a migration:
# alembic revision --autogenerate -m "add email to users"

# Generated file: migrations/versions/003_add_email_to_users.py
def upgrade():
    op.add_column('users', sa.Column('email', sa.String(255), nullable=True))
    op.create_index('ix_users_email', 'users', ['email'])

def downgrade():
    op.drop_index('ix_users_email', 'users')
    op.drop_column('users', 'email')

# Apply:  alembic upgrade head
# Revert: alembic downgrade -1

# The framework:
# 1. Tracks which migrations have been applied (alembic_version table)
# 2. Runs them in order (001 → 002 → 003)
# 3. Ensures each migration runs exactly once
# 4. Provides rollback capability
```

## Level 2: Pattern — Zero-Downtime Migrations

```
The concrete migration framework still has a problem:
  ALTER TABLE users ADD COLUMN email → locks table → downtime

For production, use the EXPAND-CONTRACT pattern:

Step 1: EXPAND (add new, don't remove old)
  Deploy: Add new column (nullable, no constraints)
  ALTER TABLE users ADD COLUMN email VARCHAR(255) NULL;
  -- Fast, no lock on most databases (Postgres, MySQL 8+)
  -- Old code doesn't know about this column → no breakage

Step 2: MIGRATE (fill new column with data)
  Deploy: Backfill in batches
  UPDATE users SET email = old_email WHERE email IS NULL LIMIT 1000;
  -- Run in small batches to avoid locking
  -- New code starts writing to BOTH old and new columns

Step 3: CONTRACT (remove old, enforce new)
  Deploy: Make new column required, drop old column
  ALTER TABLE users ALTER COLUMN email SET NOT NULL;
  ALTER TABLE users DROP COLUMN old_email;
  -- Only AFTER all code uses new column
```

```
Timeline for a safe schema change:

  Day 1: Deploy migration (add column)     ← expand
  Day 1: Deploy code (write to both)       ← dual-write
  Day 2: Run backfill job                   ← migrate data
  Day 3: Deploy code (read from new only)   ← switch reads
  Day 4: Deploy migration (drop old column) ← contract

  Each step is independently deployable and reversible.
  At no point is the application broken.
```

## Level 3: Principle — Schema as Code

```
Your database schema is source code. Treat it that way.

VERSION CONTROLLED:
  migrations/
    001_create_users.py
    002_add_orders_table.py
    003_add_email_to_users.py
    004_add_index_on_email.py
  Every schema change is a file in git.
  You can see exactly how the schema evolved.

CODE REVIEWED:
  Schema changes get PRs, just like code.
  Reviewer checks:
    □ Will this lock a large table?
    □ Is there a rollback migration?
    □ Is this additive (safe) or destructive (needs expand-contract)?
    □ Does the application code handle both old AND new schema?

TESTED:
  CI pipeline:
    1. Start fresh database
    2. Run ALL migrations from scratch
    3. Run application tests against migrated schema
    4. Run migration rollbacks to verify they work

REVERSIBLE:
  Every migration has an UP and a DOWN.
  If deploy breaks → rollback migration → schema restored.
```

## Level 4: Policy — Schema Lifecycle Rules

```
Rules for production schema changes:

1. ADDITIVE ONLY in production deploys
   ✓ ADD column (nullable)
   ✓ ADD table
   ✓ ADD index (CONCURRENTLY)
   ✗ DROP column (use expand-contract)
   ✗ RENAME column (use expand-contract)
   ✗ Change column type (use expand-contract)

2. SEPARATE schema deploys from code deploys
   Deploy migration FIRST → verify → deploy code
   Not: deploy code + migration at the same time
   Why: if code deploy fails, migration can't be rolled back easily

3. LARGE TABLE CHECKLIST (> 1M rows)
   □ Will ALTER TABLE lock the table? (Check your DB version)
   □ Use CREATE INDEX CONCURRENTLY (Postgres) or pt-osc (MySQL)
   □ Backfill data in batches (1000-10000 rows at a time)
   □ Run during low-traffic window
   □ Have a rollback plan written down BEFORE starting

4. MIGRATION REVIEW PROCESS
   - Small tables (< 100K rows): standard PR review
   - Medium tables (100K-10M rows): DBA review
   - Large tables (> 10M rows): DBA review + scheduled maintenance window
```

The abstraction ladder: scary ALTER TABLE → migration framework → expand-contract pattern → schema-as-code principle → lifecycle management policy. Each level makes the practice more systematic and less dependent on individual heroics.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
