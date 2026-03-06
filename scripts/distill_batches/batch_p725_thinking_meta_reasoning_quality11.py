"""Phase 3B: Metacognition — Reasoning Quality Evaluation (Part 11)"""

PAIRS = [
    (
        "thinking/meta-reasoning-celery-vs-dramatiq",
        r'''For background task processing in Python, compare Celery vs Dramatiq:

Approach A — Celery:
```python
from celery import Celery

app = Celery('tasks', broker='redis://localhost:6379/0')

@app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_order(self, order_id):
    try:
        order = Order.query.get(order_id)
        charge_payment(order)
        send_confirmation_email(order)
        update_inventory(order)
    except PaymentError as e:
        self.retry(exc=e)

@app.task
def generate_report(report_type, date_range):
    data = fetch_report_data(report_type, date_range)
    pdf = render_pdf(data)
    upload_to_s3(pdf)

# Periodic tasks
app.conf.beat_schedule = {
    'daily-cleanup': {
        'task': 'tasks.cleanup_expired',
        'schedule': crontab(hour=2, minute=0),
    },
}
```

Approach B — Dramatiq:
```python
import dramatiq
from dramatiq.brokers.redis import RedisBroker

broker = RedisBroker(url="redis://localhost:6379/0")
dramatiq.set_broker(broker)

@dramatiq.actor(max_retries=3, min_backoff=60000)
def process_order(order_id):
    order = Order.query.get(order_id)
    charge_payment(order)
    send_confirmation_email(order)
    update_inventory(order)

@dramatiq.actor
def generate_report(report_type, date_range):
    data = fetch_report_data(report_type, date_range)
    pdf = render_pdf(data)
    upload_to_s3(pdf)

# Periodic tasks need APScheduler or separate tool
```

Which is better for a growing Python web application?''',
        r'''<think>
Comparing Celery vs Dramatiq for background task processing...

Approach A — Celery:
- Industry standard, massive ecosystem, tons of documentation
- Built-in periodic task scheduling (celery beat)
- Canvas for complex workflows (chains, groups, chords)
- BUT: complex configuration, many gotchas
- Pickle serialization default is a security risk
- Monitoring with Flower
- Large dependency tree
- Can be buggy with certain broker/backend combinations

Approach B — Dramatiq:
- Simpler API, fewer gotchas, better defaults
- No pickle — JSON serialization by default (secure)
- Built-in rate limiting, priority queues
- No built-in periodic task scheduler
- Smaller community, less documentation
- Fewer integrations (no built-in Django support package like django-celery)
- Cleaner codebase, more predictable behavior

Multi-axis evaluation:

Reliability: Dramatiq has better defaults — no silent task drops, better error handling out of the box. Celery has known issues with task acknowledgment timing and visibility timeouts.

Features: Celery wins — canvas workflows, beat scheduler, result backends, multiple broker support (Redis, RabbitMQ, SQS).

Simplicity: Dramatiq wins — simpler API, fewer configuration options, better defaults. Less time debugging framework issues.

Community/Ecosystem: Celery wins overwhelmingly — Stack Overflow answers, blog posts, django-celery-results, Flower monitoring, battle-tested at scale.

Monitoring: Celery wins with Flower. Dramatiq has dramatiq-dashboard but it's more basic.

Periodic tasks: Celery wins with built-in beat. Dramatiq requires APScheduler or cron.

Scale: Both handle production workloads fine. Celery is proven at massive scale (Instagram used it). Dramatiq is proven at moderate scale.

The critical factor: for a "growing" application, ecosystem and community matter more than API elegance. When you hit a weird edge case at 3am, Celery has the Stack Overflow answers.

Winner: Celery for a growing application.
BUT: if you're starting fresh and value simplicity over ecosystem, Dramatiq is genuinely better designed.
</think>

**Celery is the safer choice for a growing application**, primarily because of ecosystem and community.

**Why Celery for growth:**
- Extensive documentation, Stack Overflow answers, and blog posts for every edge case
- Built-in periodic task scheduling (beat) — no extra dependency
- Canvas for complex workflows: `chain(task1.s(), task2.s(), task3.s())()`
- Django integration via `django-celery-results`, `django-celery-beat`
- Monitoring with Flower (production-ready dashboard)
- Proven at massive scale (Instagram, Mozilla, etc.)

**Celery's real problems:**
- Default pickle serialization — **always set** `CELERY_TASK_SERIALIZER = 'json'`
- Visibility timeout gotchas with Redis broker
- Complex configuration with many surprising defaults
- Occasional task loss under broker pressure

**Why Dramatiq is actually better designed:**
- JSON serialization by default (secure)
- Built-in rate limiting per actor
- Priority queues out of the box
- Simpler, more predictable behavior
- Better retry/backoff defaults

**Decision framework:**

| Factor | Celery | Dramatiq |
|--------|--------|----------|
| Community | Massive | Small but growing |
| Periodic tasks | Built-in beat | Need APScheduler |
| Complex workflows | Canvas (chain/group) | Manual |
| Django integration | Excellent | Basic |
| Default security | Pickle (bad) | JSON (good) |
| API simplicity | Complex | Clean |
| Monitoring | Flower | Basic dashboard |

**Choose Celery** if: Django app, need periodic tasks, need complex workflows, want battle-tested at scale.
**Choose Dramatiq** if: New project, value simplicity, don't need periodic tasks, small team.'''
    ),
    (
        "thinking/meta-reasoning-alembic-vs-manual-migrations",
        r'''For database schema migrations in a Python project, compare Alembic auto-generation vs hand-written SQL migrations:

Approach A — Alembic autogenerate:
```python
# alembic revision --autogenerate -m "add user preferences"
# Generated migration:

def upgrade():
    op.add_column('users', sa.Column('preferences', sa.JSON(), nullable=True))
    op.create_index('ix_users_email', 'users', ['email'], unique=True)

def downgrade():
    op.drop_index('ix_users_email', 'users')
    op.drop_column('users', 'preferences')
```

Approach B — Hand-written SQL:
```python
# migrations/0042_add_user_preferences.py

UP = """
ALTER TABLE users ADD COLUMN preferences JSONB DEFAULT '{}';
CREATE UNIQUE INDEX CONCURRENTLY ix_users_email ON users (email);
"""

DOWN = """
DROP INDEX IF EXISTS ix_users_email;
ALTER TABLE users DROP COLUMN IF EXISTS preferences;
"""

def upgrade(conn):
    conn.execute(UP)

def downgrade(conn):
    conn.execute(DOWN)
```

Which approach is better?''',
        r'''<think>
Comparing Alembic autogenerate vs hand-written SQL migrations...

Approach A — Alembic autogenerate:
- Compares model definitions to actual DB schema, generates diff
- Handles most common operations automatically
- Generates both upgrade and downgrade
- Uses SQLAlchemy operations — portable across databases
- BUT: misses some things (data migrations, partial indexes, custom types, renamed columns vs drop+add)
- Autogenerate is a starting point, not a finished migration
- Tied to SQLAlchemy models

Approach B — Hand-written SQL:
- Full control over exact DDL
- Can use database-specific features (CONCURRENTLY, JSONB, partial indexes)
- Data migrations are natural (UPDATE statements)
- CONCURRENTLY index creation — doesn't lock table in production!
- BUT: must write downgrade manually
- No automatic detection of schema drift
- Need to know the SQL dialect well
- Easy to forget edge cases (IF EXISTS, IF NOT EXISTS)

Multi-axis evaluation:

Correctness: Hand-written wins for complex migrations. Alembic autogenerate can't detect column renames (sees drop + add), can't generate data migrations, misses some index types.

Safety in production: Hand-written wins. Notice `CREATE INDEX CONCURRENTLY` in approach B — this doesn't lock the table. Alembic's `create_index` generates a blocking `CREATE INDEX` that locks writes on large tables.

Developer productivity: Alembic wins for simple schema changes. Adding a column? Autogenerate handles it perfectly. No need to write SQL.

Portability: Alembic wins — works across PostgreSQL, MySQL, SQLite. Hand-written SQL is database-specific.

Review quality: Hand-written is easier to review — you see exactly what SQL will run. Alembic operations require understanding the SQLAlchemy operations API.

Handling complex changes: Hand-written wins. Data migrations (backfilling values), multi-step operations, conditional logic are natural in SQL but awkward in Alembic operations.

The critical factor: most teams should use Alembic autogenerate as a STARTING POINT, then review and customize the generated migration. Don't blindly trust autogenerate, but don't ignore its productivity benefits.

Winner: Alembic with manual review and customization.
BUT: for teams with strong SQL skills and complex production databases, hand-written migrations give more control and safety.
</think>

**Use Alembic autogenerate as a starting point, then review and customize.** Neither extreme is best.

**Why pure autogenerate is dangerous:**
- Sees column renames as drop + add (data loss!)
- Generates blocking `CREATE INDEX` instead of `CONCURRENTLY`
- Can't generate data migrations
- Misses partial indexes, custom constraints, DB-specific features
- May reorder operations incorrectly

**Why pure hand-written is overkill:**
- Simple "add column" migrations are tedious to write manually
- Easy to forget downgrade logic
- No automatic schema drift detection
- More error-prone for routine changes

**Best practice — hybrid approach:**

```bash
# 1. Generate the skeleton
alembic revision --autogenerate -m "add user preferences"

# 2. Review and fix the generated migration
# 3. Add CONCURRENTLY, data migrations, custom logic
```

```python
def upgrade():
    # Autogenerated (keep):
    op.add_column('users', sa.Column('preferences', sa.JSON(), nullable=True))

    # Modified from autogenerate (was blocking CREATE INDEX):
    op.execute('CREATE UNIQUE INDEX CONCURRENTLY ix_users_email ON users (email)')

    # Added manually (data migration):
    op.execute("UPDATE users SET preferences = '{}' WHERE preferences IS NULL")

def downgrade():
    op.drop_index('ix_users_email', 'users')
    op.drop_column('users', 'preferences')
```

**Key differences that matter in production:**

| Concern | Alembic auto | Hand-written SQL |
|---------|-------------|-----------------|
| Blocking indexes | Yes (dangerous) | CONCURRENTLY option |
| Data migrations | Can't generate | Natural |
| Column renames | Sees as drop+add | Correct ALTER |
| Simple add column | Perfect | Tedious |
| DB portability | Cross-database | DB-specific |
| Schema drift detection | Automatic | Manual |

**Rule**: Autogenerate for the skeleton, human review for production safety.'''
    ),
    (
        "thinking/meta-reasoning-monorepo-vs-multirepo",
        r'''For organizing 5 Python microservices that share some common code, compare monorepo vs multi-repo:

Approach A — Monorepo:
```
project/
├── services/
│   ├── auth-service/
│   │   ├── src/
│   │   ├── tests/
│   │   └── Dockerfile
│   ├── order-service/
│   │   ├── src/
│   │   ├── tests/
│   │   └── Dockerfile
│   └── notification-service/
│       ├── src/
│       ├── tests/
│       └── Dockerfile
├── shared/
│   ├── models/
│   ├── utils/
│   └── middleware/
├── pyproject.toml
└── CI/
    └── build-changed.sh
```

Approach B — Multi-repo:
```
auth-service/          (separate git repo)
├── src/
├── tests/
├── Dockerfile
└── pyproject.toml

order-service/         (separate git repo)
├── src/
├── tests/
├── Dockerfile
└── pyproject.toml

shared-lib/            (separate git repo, published as package)
├── src/
├── tests/
└── pyproject.toml
```

Which is better for a small team (3-5 developers)?''',
        r'''<think>
Comparing monorepo vs multi-repo for 5 Python microservices with shared code, small team...

Approach A — Monorepo:
- Single git clone, single PR for cross-service changes
- Shared code is just an import — no versioning, no publishing
- CI needs to detect which services changed (build-changed.sh)
- Atomic commits across services (refactor shared + all consumers in one PR)
- Everyone sees all code — better visibility
- Git history is shared — larger repo, potentially slower git operations
- IDE opens everything — can search/navigate across services

Approach B — Multi-repo:
- Each service is independent — separate CI, separate deploys
- Shared code must be published as a package (PyPI or private registry)
- Changing shared code requires: update shared-lib → publish → update dependency in each service → test each service
- Clear ownership boundaries
- Independent version histories
- BUT: diamond dependency problems with shared-lib versions
- Cross-service changes require coordinated PRs

Multi-axis evaluation:

Developer productivity: Monorepo wins for small team. One PR for "add user_id to shared model + update auth-service + update order-service." Multi-repo requires 3 coordinated PRs.

Shared code management: Monorepo wins massively. No package publishing, no version pinning, no "which version of shared-lib does order-service use?" No diamond dependencies.

CI complexity: Multi-repo wins for simple CI (each repo has its own pipeline). Monorepo needs "only build changed services" logic, which is doable but adds complexity.

Deployment independence: Roughly equal — both can deploy services independently. Monorepo just needs per-service Dockerfiles and targeted builds.

Code visibility: Monorepo wins. Everyone can search, read, and understand the full system. Multi-repo silos knowledge.

Scaling (team): Multi-repo wins for large teams (>20 developers, 50+ services). Clear ownership, independent merge queues. But 3-5 developers? Monorepo is fine.

Scaling (code): Monorepo can get slow with very large repos (Git, IDE). But 5 Python services? Negligible.

The critical factor: 3-5 developers managing 5 services with shared code. The overhead of publishing shared packages, coordinating multi-repo PRs, and managing version compatibility vastly outweighs monorepo's CI complexity.

Winner: Monorepo for a small team with shared code.
BUT: consider multi-repo if services are truly independent (no shared code), different teams own different services, or you need strict deployment boundaries.
</think>

**Monorepo is better for 3-5 developers sharing code across 5 services.** The coordination overhead of multi-repo doesn't pay off at this scale.

**Why monorepo wins for small teams:**
- **Atomic cross-service changes**: Refactor shared model + update all consumers in ONE PR
- **No package publishing**: Shared code is `from shared.models import User` — no PyPI, no versioning
- **Full visibility**: Everyone can search and understand the entire system
- **Simpler dependency management**: No diamond dependencies on shared-lib versions

**Why multi-repo hurts small teams:**
```
# To change a shared model in multi-repo:
1. Update shared-lib, bump version, publish    # PR #1
2. Wait for package to publish
3. Update auth-service pyproject.toml           # PR #2
4. Update order-service pyproject.toml          # PR #3
5. Update notification-service pyproject.toml   # PR #4
6. Hope nobody merged with the old version

# In monorepo:
1. Update shared/ and all services             # PR #1, done
```

**Monorepo CI trick** — only build what changed:

```bash
# build-changed.sh
CHANGED=$(git diff --name-only HEAD~1)
for service in services/*/; do
    if echo "$CHANGED" | grep -q "^$service\|^shared/"; then
        echo "Building $service..."
        docker build -t $(basename $service) $service
    fi
done
```

**When to switch to multi-repo:**
- Team grows to 15+ developers with distinct service ownership
- Services are truly independent (no shared code)
- Need independent release cadences with strict boundaries
- Git performance degrades (unlikely with 5 Python services)

| Axis | Monorepo | Multi-repo |
|------|---------|------------|
| Cross-service changes | 1 PR | N coordinated PRs |
| Shared code | Direct import | Published package |
| CI complexity | Need change detection | Simple per-repo CI |
| Team scaling | Good to ~15 devs | Better for large orgs |
| Visibility | Full | Siloed |
| Deployment | Per-service Dockerfile | Natural isolation |

**For your case**: monorepo, no question.'''
    ),
    (
        "thinking/meta-reasoning-structured-logging-vs-printf",
        r'''Compare structured logging vs traditional printf-style logging for a Python web service:

Approach A — Traditional logging:
```python
import logging

logger = logging.getLogger(__name__)

def process_order(order_id, user_id):
    logger.info(f"Processing order {order_id} for user {user_id}")
    try:
        result = charge_payment(order_id)
        logger.info(f"Payment charged: ${result.amount} for order {order_id}")
        send_email(user_id, order_id)
        logger.info(f"Confirmation email sent for order {order_id}")
    except PaymentError as e:
        logger.error(f"Payment failed for order {order_id}: {e}")
        raise
```

Approach B — Structured logging (structlog):
```python
import structlog

logger = structlog.get_logger()

def process_order(order_id, user_id):
    log = logger.bind(order_id=order_id, user_id=user_id)
    log.info("processing_order")
    try:
        result = charge_payment(order_id)
        log.info("payment_charged", amount=result.amount)
        send_email(user_id, order_id)
        log.info("confirmation_email_sent")
    except PaymentError as e:
        log.error("payment_failed", error=str(e), error_type=type(e).__name__)
        raise
```

Which is better for a production web service?''',
        r'''<think>
Comparing traditional printf logging vs structured logging...

Approach A — Traditional logging:
- Human-readable log lines
- Easy to write and understand
- f-string formatting — familiar to all Python developers
- But: parsing log lines to extract order_id requires regex
- Inconsistent formats across developers ("Processing order X" vs "Order X processing")
- Log aggregation tools (ELK, Datadog) struggle to index unstructured text
- Searching for "all logs related to order 12345" requires text search

Approach B — Structured logging:
- JSON output: `{"event": "payment_charged", "order_id": 123, "amount": 49.99}`
- `bind()` attaches context that flows through all subsequent log calls
- Machine-parseable — log aggregation tools index fields automatically
- Consistent field names enforced by code structure
- Search by field: `order_id:12345` in Kibana/Datadog
- Less human-readable in raw form (JSON lines)
- Small learning curve for structlog API

Multi-axis evaluation:

Debugging in production: Structured wins. "Show me all logs for order_id=12345 where event=payment_failed" is a precise query. Printf requires text search through inconsistent messages.

Development experience: Printf wins for quick scripts and local development. Easier to read in terminal output.

Log aggregation: Structured wins massively. ELK, Datadog, CloudWatch Insights all work better with structured fields. No regex parsing rules needed.

Consistency: Structured wins. `bind(order_id=order_id)` ensures order_id appears in every log line. Printf requires manually including it in every f-string (and developers WILL forget).

Performance: Roughly equal. Structured logging has slight overhead for JSON serialization, but it's negligible compared to I/O.

Cost: Structured logging can increase log storage costs (JSON is more verbose than plain text). But the queryability pays for itself.

Correlation: Structured wins with bind(). Add request_id at middleware level, it flows through all logs automatically. Printf requires passing request_id everywhere.

The critical factor: "production web service" means you WILL need to debug issues from logs. Structured logging makes this 10x faster.

Winner: Structured logging for production.
BUT: can configure structlog to render human-readable output in development.
</think>

**Structured logging (structlog) is better for production web services.** The debugging and observability advantages are decisive.

**Why structured logging wins in production:**
- **Precise queries**: `order_id:12345 AND event:payment_failed` vs grep through inconsistent text
- **Context binding**: `logger.bind(order_id=order_id)` — order_id appears in EVERY subsequent log automatically
- **Machine-parseable**: Log aggregation tools (ELK, Datadog, CloudWatch) index JSON fields natively
- **Consistent fields**: Code structure enforces field names, not developer discipline

**The killer feature — context binding:**
```python
# Structured: bind once, flows everywhere
log = logger.bind(order_id=order_id, user_id=user_id, request_id=req_id)
log.info("processing_order")           # All 3 fields included
log.info("payment_charged", amount=50) # All 3 fields + amount
log.error("payment_failed", error=e)   # All 3 fields + error

# Printf: must repeat in every line (and you WILL forget)
logger.info(f"Processing order {order_id} for user {user_id} req={req_id}")
logger.info(f"Payment charged ${amount} for order {order_id}")  # Forgot user_id, req_id
```

**Best of both worlds** — human-readable in dev, JSON in prod:
```python
import structlog

structlog.configure(
    processors=[
        structlog.dev.ConsoleRenderer()     # Dev: colored, readable
        # structlog.processors.JSONRenderer()  # Prod: JSON lines
    ]
)
```

| Axis | Printf logging | Structured logging |
|------|---------------|-------------------|
| Human readability | Better (raw) | JSON (needs formatter) |
| Production debugging | Text search | Field-based queries |
| Context propagation | Manual per line | bind() once |
| Log aggregation | Requires parsing | Native JSON indexing |
| Learning curve | None | Small (structlog API) |
| Consistency | Developer discipline | Code-enforced |

**For production**: always structured logging. Use `ConsoleRenderer` during development for readability.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
