"""Phase 2H: Advanced Reasoning — First Principles Derivation (Part 2/5)
Derive solutions from constraints rather than pattern-matching:
database connection pool, search engine, permission system, task scheduler, log aggregation."""

PAIRS = [
    (
        "thinking/firstprinciples-connection-pool",
        "I need to manage database connections in my Python web app. Right now every request opens and closes a connection. It's slow under load. What should I do?",
        r'''<think>
Let me derive a solution from first principles rather than just saying "use a connection pool."

What are the fundamental constraints?

1. Creating a DB connection is expensive (TCP handshake, auth, TLS negotiation) — ~5-50ms
2. Each request needs a connection, but only for a fraction of its lifetime
3. Connections consume server memory and DB has a max_connections limit
4. Under load, many requests arrive concurrently

What are the physics of this problem?

Opening a connection per request means:
- N concurrent requests = N connection setups = N * setup_time wasted
- If setup_time = 20ms and request takes 50ms, we spend 29% of time just connecting
- Under spike load, we might exceed max_connections and get errors

What if we reuse connections? A request finishes with a connection — the next request could use it.

This leads to a pool concept, but let me derive the properties it needs:

Property 1: Pre-created connections
- Create connections before they're needed
- Trade startup time for request-time savings
- How many? Need to balance memory vs availability

Property 2: Borrow/return semantics
- Request borrows a connection, returns it when done
- Must handle: what if request forgets to return? (leak)
- Need timeout-based reclamation

Property 3: Size bounds
- Minimum size: keep N connections warm even when idle (avoid cold start)
- Maximum size: never exceed DB's max_connections (shared across app instances)
- If max_size = DB_max / num_app_instances, we're safe

Property 4: Health checking
- Connections can go stale (DB restarts, network issues, idle timeout)
- Must validate before lending: "SELECT 1" or protocol-level ping
- Don't health-check on every borrow (too expensive) — check periodically or on error

Property 5: Queuing under exhaustion
- When all connections are borrowed, new requests must wait
- Need a max_wait timeout to avoid request hanging forever
- FIFO queue is fair; priority queue if some requests are more important

Property 6: Connection lifecycle
- Max lifetime: recycle connections after N minutes (prevents stale state)
- Max idle time: close connections that haven't been used (saves DB resources)

Let me also think about what size to set:
- Little's Law: pool_size = request_rate * avg_connection_hold_time
- If 100 req/s and each holds connection for 10ms: need 100 * 0.01 = 1 connection (in theory)
- But variance matters — add headroom for spikes
- Rule of thumb from PostgreSQL wiki: connections = (core_count * 2) + effective_spindle_count
- For SSD: roughly 2 * CPU cores of the DB server

Now let me implement this properly.
</think>

You're hitting a classic problem where connection setup cost dominates under load. Let me walk you through why a connection pool solves this from first principles, then implement one.

**Why per-request connections fail:**
- TCP + TLS + auth = ~20ms overhead per connection
- At 100 req/s, that's 2 seconds of pure connection overhead per second
- Under spikes, you'll also blow past `max_connections`

**The solution — derived from constraints:**

```python
# Use SQLAlchemy's pool (don't roll your own in production)
from sqlalchemy import create_engine
from sqlalchemy.pool import QueuePool

engine = create_engine(
    "postgresql://user:pass@localhost/mydb",
    poolclass=QueuePool,

    # Property 1 & 3: Size bounds
    pool_size=10,           # Warm connections kept ready
    max_overflow=20,        # Burst capacity (up to 30 total)

    # Property 5: Queuing under exhaustion
    pool_timeout=30,        # Max seconds to wait for a connection

    # Property 6: Connection lifecycle
    pool_recycle=1800,      # Recycle after 30 min (prevents stale)
    pool_pre_ping=True,     # Property 4: Health check before use
)
```

**How to size it:**

```python
# Little's Law: pool_size = throughput * avg_hold_time
# Example: 200 req/s, each holds connection for 15ms
# Theoretical minimum: 200 * 0.015 = 3 connections
# With safety margin (3-5x): 10-15 connections

# For PostgreSQL specifically:
# Optimal connections per DB server = (2 * cpu_cores) + spindles
# 8-core SSD server -> ~16 connections total across all app instances
# With 4 app instances: pool_size=4, max_overflow=4 per instance

import os
DB_POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", 5))
DB_MAX_OVERFLOW = int(os.environ.get("DB_MAX_OVERFLOW", 10))
```

**Critical: always return connections:**

```python
# WRONG - connection leak if exception occurs
conn = engine.connect()
result = conn.execute(text("SELECT ..."))
conn.close()

# RIGHT - context manager guarantees return
with engine.connect() as conn:
    result = conn.execute(text("SELECT ..."))
    # Connection returned to pool automatically

# For async (FastAPI + asyncpg):
from sqlalchemy.ext.asyncio import create_async_engine

async_engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost/mydb",
    pool_size=10,
    max_overflow=20,
)

async with async_engine.connect() as conn:
    result = await conn.execute(text("SELECT ..."))
```

**Monitoring to add:**

```python
# Track pool health
pool = engine.pool
print(f"Pool size: {pool.size()}")
print(f"Checked out: {pool.checkedout()}")
print(f"Overflow: {pool.overflow()}")
print(f"Checked in: {pool.checkedin()}")

# Alert if checked_out consistently equals pool_size + max_overflow
# That means you're saturated and requests are queuing
```

Start with `pool_size=5, max_overflow=10` and monitor. Increase if you see timeout errors; decrease if your DB is CPU-bound.'''
    ),
    (
        "thinking/firstprinciples-search-engine",
        "How would I build a simple full-text search for my app? I have about 500K documents (articles). I don't want to add Elasticsearch. What are my options?",
        r'''<think>
Let me think about what full-text search actually needs from first principles, rather than just recommending a tool.

What does "search" fundamentally require?

1. Given a query like "python async database", find documents containing those terms
2. Rank results by relevance (not just presence/absence)
3. Do it fast enough for interactive use (<100ms)

Why is naive search (LIKE '%term%') bad?
- Scans every row, every time — O(N * avg_doc_length)
- For 500K docs, each averaging 1KB = scanning 500MB per query
- No ranking — just yes/no match
- Can't handle stemming (search "running" won't find "run")

What data structure makes text lookup fast? An inverted index.

The key insight: instead of "for each document, does it contain the term?"
Flip it to: "for each term, which documents contain it?"

This is like a book index — you don't read every page to find "polymorphism",
you look up "polymorphism" in the index and get page numbers.

Building an inverted index:
1. Tokenize each document into terms
2. Normalize terms (lowercase, stem: "running" -> "run")
3. For each term, store list of (doc_id, position, frequency)
4. At query time: look up each query term, intersect/union the doc lists

Ranking — TF-IDF from first principles:
- Term Frequency (TF): "python" appears 5 times in doc A, 1 time in doc B → A is more relevant for "python"
- Inverse Document Frequency (IDF): "the" appears in 99% of docs (not useful), "asyncio" appears in 0.1% (very useful)
- Score = TF * IDF — rewards terms that are frequent in the doc but rare overall

Now, options for 500K docs:

Option 1: PostgreSQL full-text search (built-in inverted index!)
- tsvector/tsquery — PostgreSQL literally has an inverted index
- GIN index makes it fast
- Handles stemming, ranking, phrase search
- For 500K docs, this is the sweet spot

Option 2: SQLite FTS5
- If using SQLite, FTS5 extension does the same
- BM25 ranking built in

Option 3: Build with a library (Whoosh, Tantivy)
- More control but more maintenance
- Overkill for 500K docs with a DB already available

For 500K docs, PostgreSQL FTS is the clear winner — no new infrastructure, battle-tested, fast enough.
</think>

For 500K documents, you don't need Elasticsearch. PostgreSQL's built-in full-text search handles this easily. Let me explain why and how.

**Why LIKE '%term%' won't work:**
- Scans every row — no index can help with leading wildcards
- No ranking, no stemming, no relevance scoring
- Gets slower linearly with data growth

**PostgreSQL full-text search — it has an inverted index built in:**

```sql
-- Step 1: Add a tsvector column (the inverted index)
ALTER TABLE articles ADD COLUMN search_vector tsvector;

-- Step 2: Populate it (tokenizes + stems + normalizes)
UPDATE articles
SET search_vector = to_tsvector('english',
    coalesce(title, '') || ' ' ||
    coalesce(body, '') || ' ' ||
    coalesce(tags, '')
);

-- Step 3: Create a GIN index (makes lookups fast)
CREATE INDEX idx_articles_search ON articles USING GIN(search_vector);

-- Step 4: Search with ranking
SELECT id, title,
       ts_rank(search_vector, query) AS rank
FROM articles,
     to_tsquery('english', 'python & async & database') AS query
WHERE search_vector @@ query
ORDER BY rank DESC
LIMIT 20;
```

**Keep it updated automatically:**

```sql
-- Trigger to update search_vector on insert/update
CREATE OR REPLACE FUNCTION articles_search_trigger()
RETURNS trigger AS $$
BEGIN
    NEW.search_vector := to_tsvector('english',
        coalesce(NEW.title, '') || ' ' ||
        coalesce(NEW.body, '') || ' ' ||
        coalesce(NEW.tags, ''));
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trig_articles_search
    BEFORE INSERT OR UPDATE ON articles
    FOR EACH ROW EXECUTE FUNCTION articles_search_trigger();
```

**Weight title matches higher than body:**

```sql
-- 'A' weight = highest, 'D' = lowest
UPDATE articles SET search_vector =
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(tags, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(body, '')), 'C');
```

**In Python (SQLAlchemy):**

```python
from sqlalchemy import func, text

def search_articles(session, query_string: str, limit: int = 20):
    # Convert user input to tsquery safely
    # plainto_tsquery handles natural language input
    query = func.plainto_tsquery('english', query_string)

    results = (
        session.query(Article)
        .filter(Article.search_vector.op('@@')(query))
        .order_by(
            func.ts_rank(Article.search_vector, query).desc()
        )
        .limit(limit)
        .all()
    )
    return results
```

**Performance at 500K docs:**
- GIN index lookup: ~1-5ms for most queries
- Ranking + sorting top 20: ~5-20ms
- Total: well under 100ms

You only need Elasticsearch when you hit millions of documents, need fuzzy matching, faceted search, or distributed search across multiple nodes.'''
    ),
    (
        "thinking/firstprinciples-permission-system",
        "I'm designing a permission system for a multi-tenant SaaS app. Users belong to organizations, and I need granular permissions. How should I model this?",
        r'''<think>
Let me derive a permission system from first principles rather than just recommending RBAC.

What are the fundamental questions a permission system answers?

"Can subject S perform action A on resource R?"

That's it. Everything else is optimization and ergonomics.

Let me build up from constraints:

Constraint 1: Multi-tenant — organizations are isolated
- User in Org A must NEVER see/modify Org B's data
- This is the hardest constraint — security boundary

Constraint 2: Granular — not just admin/user
- "Can edit Project X but only view Project Y"
- Permissions are scoped to specific resources

Constraint 3: Manageable — admins can understand and configure it
- Pure ACLs (per-user, per-resource) don't scale — N users * M resources = N*M entries
- Need grouping mechanism

Let me evaluate approaches:

Approach 1: Simple role-based (RBAC)
- Roles: admin, editor, viewer
- Each role has a set of permissions
- User -> Role -> Permissions
- Problem: "editor on Project X but viewer on Project Y" requires resource-scoped roles
- Gets messy with fine-grained needs

Approach 2: Resource-scoped RBAC
- User has a role PER resource (or resource group)
- user_roles(user_id, role, resource_type, resource_id)
- Handles "editor on X, viewer on Y"
- But: role definitions are rigid — what if an "editor" needs slightly different perms on different resource types?

Approach 3: Attribute-based (ABAC)
- Rules like: "if user.department == 'engineering' and resource.sensitivity < 3 and time.is_business_hours"
- Maximum flexibility but hard to reason about and audit
- Overkill for most SaaS apps

Approach 4: Hybrid — roles + direct permission grants
- Roles provide baseline (80% of cases)
- Direct grants handle exceptions (20%)
- Best ergonomics for multi-tenant SaaS

Let me design the hybrid approach:

The model:
1. Permission = (action, resource_type) — e.g., ("edit", "project")
2. Role = named collection of permissions — e.g., "project_editor" = [edit, view, comment on projects]
3. Assignment = (user, role, scope) — e.g., (alice, project_editor, project:123)
4. Scope = tenant-level OR resource-level

Resolution: can user do X on resource R?
1. Get user's org_id, verify R belongs to same org (tenant isolation)
2. Check direct grants on R
3. Check role assignments scoped to R
4. Check role assignments scoped to R's parent (project -> workspace -> org)
5. If any path yields the permission, allow

The hierarchy matters for inheritance:
- Org admin -> all workspaces -> all projects (inherits down)
- Workspace editor -> all projects in that workspace
- Project viewer -> just that project

This gives us resource-scoped RBAC with hierarchical inheritance.
</think>

Here's a permission system derived from the core question every authorization check answers: **"Can user U perform action A on resource R?"**

**Data model:**

```sql
-- Tenancy boundary (hardest constraint)
CREATE TABLE organizations (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL
);

-- Resource hierarchy: Org -> Workspace -> Project
CREATE TABLE workspaces (
    id UUID PRIMARY KEY,
    org_id UUID NOT NULL REFERENCES organizations(id),
    name TEXT NOT NULL
);

CREATE TABLE projects (
    id UUID PRIMARY KEY,
    workspace_id UUID NOT NULL REFERENCES workspaces(id),
    name TEXT NOT NULL
);

-- Permissions are (action, resource_type) pairs
CREATE TABLE permissions (
    id UUID PRIMARY KEY,
    action TEXT NOT NULL,          -- 'view', 'edit', 'delete', 'manage_members'
    resource_type TEXT NOT NULL,   -- 'project', 'workspace', 'org'
    UNIQUE(action, resource_type)
);

-- Roles bundle permissions
CREATE TABLE roles (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,            -- 'project_editor', 'workspace_admin'
    org_id UUID REFERENCES organizations(id),  -- NULL = system role, non-NULL = custom
    UNIQUE(name, org_id)
);

CREATE TABLE role_permissions (
    role_id UUID REFERENCES roles(id),
    permission_id UUID REFERENCES permissions(id),
    PRIMARY KEY(role_id, permission_id)
);

-- KEY TABLE: role assignments scoped to a resource
CREATE TABLE user_role_assignments (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES users(id),
    role_id UUID NOT NULL REFERENCES roles(id),
    resource_type TEXT NOT NULL,   -- 'org', 'workspace', 'project'
    resource_id UUID NOT NULL,     -- The specific resource
    UNIQUE(user_id, role_id, resource_type, resource_id)
);
```

**Permission check with hierarchy inheritance:**

```python
from functools import lru_cache
from typing import Optional
import uuid

class PermissionService:
    def __init__(self, db):
        self.db = db

    def can(self, user_id: uuid.UUID, action: str,
            resource_type: str, resource_id: uuid.UUID) -> bool:
        """Core authorization check."""
        # Step 1: Build the resource hierarchy (child -> parent -> grandparent)
        hierarchy = self._get_resource_hierarchy(resource_type, resource_id)

        # Step 2: Check if any role assignment in the hierarchy grants this permission
        for scope_type, scope_id in hierarchy:
            if self._has_permission_at_scope(
                user_id, action, resource_type, scope_type, scope_id
            ):
                return True

        return False

    def _get_resource_hierarchy(self, resource_type: str,
                                 resource_id: uuid.UUID) -> list:
        """Returns [(type, id)] from specific to general."""
        hierarchy = [(resource_type, resource_id)]

        if resource_type == "project":
            project = self.db.get_project(resource_id)
            hierarchy.append(("workspace", project.workspace_id))
            workspace = self.db.get_workspace(project.workspace_id)
            hierarchy.append(("org", workspace.org_id))
        elif resource_type == "workspace":
            workspace = self.db.get_workspace(resource_id)
            hierarchy.append(("org", workspace.org_id))
        # org is top-level, no parent

        return hierarchy

    def _has_permission_at_scope(self, user_id, action,
                                  resource_type, scope_type, scope_id) -> bool:
        """Check if user has a role at this scope granting the action."""
        query = """
            SELECT 1 FROM user_role_assignments ura
            JOIN role_permissions rp ON rp.role_id = ura.role_id
            JOIN permissions p ON p.id = rp.permission_id
            WHERE ura.user_id = %s
              AND ura.resource_type = %s
              AND ura.resource_id = %s
              AND p.action = %s
              AND p.resource_type = %s
            LIMIT 1
        """
        return self.db.exists(query, [
            user_id, scope_type, scope_id, action, resource_type
        ])
```

**Tenant isolation (non-negotiable):**

```python
# EVERY query must include org_id filtering
# Use a middleware/decorator to enforce this

def require_same_org(func):
    """Decorator that verifies resource belongs to user's org."""
    def wrapper(self, user_id, resource_type, resource_id, *args, **kwargs):
        user_org = self.db.get_user_org(user_id)
        resource_org = self.db.get_resource_org(resource_type, resource_id)
        if user_org != resource_org:
            raise PermissionDenied("Resource not found")  # Don't leak existence
        return func(self, user_id, resource_type, resource_id, *args, **kwargs)
    return wrapper
```

**Default roles to seed:**

```python
SYSTEM_ROLES = {
    "org_admin": ["*:org", "*:workspace", "*:project"],   # Everything
    "workspace_admin": ["*:workspace", "*:project"],       # Within workspace
    "project_editor": ["view:project", "edit:project", "comment:project"],
    "project_viewer": ["view:project"],
}
```

This gives you hierarchical RBAC where an org_admin inherits all permissions downward, but a project_viewer only sees one project. Orgs can create custom roles for their specific needs.'''
    ),
    (
        "thinking/firstprinciples-task-scheduler",
        "I need to run background jobs in my web app — sending emails, processing uploads, generating reports. I've been using cron but it's getting unwieldy. What's the right architecture?",
        r'''<think>
Let me think about what background job processing fundamentally needs rather than just saying "use Celery."

What is a background job?

It's work that:
1. Shouldn't block the HTTP response (user doesn't want to wait)
2. Can tolerate some delay (seconds to minutes is OK)
3. Might fail and need retry
4. Might need to run on a schedule

What are the fundamental requirements?

Requirement 1: Decoupling
- Web request says "do this work" and moves on
- Something else actually does the work
- Need a way to pass the work description between them
- This is fundamentally a message/queue pattern

Requirement 2: Reliability
- What if the worker crashes mid-job? Job shouldn't be lost
- Need acknowledgment: "I finished this job" before removing from queue
- What if the job fails? Need retry with backoff

Requirement 3: Concurrency
- Multiple jobs may be runnable simultaneously
- Need multiple workers (or async processing)
- But some jobs shouldn't run concurrently (avoid double-sending an email)

Requirement 4: Scheduling
- "Run this every day at 3am" (replaces cron)
- "Run this in 30 minutes" (delayed execution)

Requirement 5: Observability
- What jobs are pending? Running? Failed?
- How long do jobs take?
- What errors occurred?

Now, what's the simplest architecture that satisfies all of these?

Producer -> Queue -> Consumer

The queue is the critical piece. Options:
- Redis (fast, simple, can lose data on crash without persistence)
- PostgreSQL (already have it, ACID, slightly slower)
- RabbitMQ (purpose-built, most features, another service to run)

For a web app that already has PostgreSQL... use PostgreSQL as the queue?

Actually, yes. PostgreSQL's SKIP LOCKED (added in 9.5) makes it a viable job queue:
- `SELECT ... FOR UPDATE SKIP LOCKED` = atomic dequeue
- ACID = jobs survive crashes
- No new infrastructure

For small-medium scale (< 1000 jobs/minute), this is perfect.
For high scale, graduate to Redis-backed (Celery/RQ) or dedicated queue.

But the user said cron is getting unwieldy, so they probably need:
1. A proper job queue (not cron) for async work
2. A scheduler for periodic tasks
3. Retry logic
4. Monitoring

The pragmatic answer: use a task queue library appropriate to their stack.
- Python: Celery (full-featured) or RQ (simpler) or Dramatiq (middle ground)
- Node: BullMQ
- Ruby: Sidekiq

Let me show the architecture and a practical implementation.
</think>

Cron breaks down because it has no retry logic, no queuing, no visibility, and no concurrency control. You need a proper task queue. Let me show you the architecture from first principles.

**What you fundamentally need:**

```
Web App (producer) → Queue (broker) → Worker (consumer)
    "send email to user 42"   [stored]   [picks up, executes]
```

**The simplest production setup (Python + Redis + Celery):**

```python
# celery_app.py
from celery import Celery

app = Celery('myapp', broker='redis://localhost:6379/0')

app.conf.update(
    # Reliability: don't acknowledge until task completes
    task_acks_late=True,

    # If worker crashes, re-queue the task
    task_reject_on_worker_lost=True,

    # Retry config
    task_default_retry_delay=60,       # 1 min between retries
    task_default_max_retries=3,

    # Concurrency
    worker_concurrency=4,              # 4 parallel workers

    # Serialization (avoid pickle for security)
    task_serializer='json',
    accept_content=['json'],
)
```

**Define tasks:**

```python
# tasks.py
from celery_app import app
from celery.utils.log import get_task_logger

logger = get_task_logger(__name__)

@app.task(bind=True, max_retries=3)
def send_email(self, user_id: int, template: str, context: dict):
    """Send email with automatic retry on failure."""
    try:
        user = get_user(user_id)
        email_service.send(user.email, template, context)
    except EmailServiceDown as e:
        # Exponential backoff: 60s, 120s, 240s
        raise self.retry(exc=e, countdown=60 * (2 ** self.request.retries))

@app.task(bind=True, max_retries=2)
def process_upload(self, upload_id: int):
    """Process uploaded file (resize images, extract text, etc.)."""
    upload = get_upload(upload_id)
    upload.status = "processing"
    upload.save()

    try:
        result = do_heavy_processing(upload.file_path)
        upload.status = "completed"
        upload.result = result
    except Exception as e:
        upload.status = "failed"
        upload.error = str(e)
        raise self.retry(exc=e, countdown=120)
    finally:
        upload.save()

@app.task
def generate_report(org_id: int, report_type: str, date_range: dict):
    """Generate and store a report."""
    data = fetch_report_data(org_id, report_type, date_range)
    pdf = render_report(data)
    store_report(org_id, report_type, pdf)
    notify_report_ready(org_id, report_type)
```

**Dispatch from web app:**

```python
# views.py (FastAPI example)
from tasks import send_email, process_upload

@app.post("/uploads/")
async def create_upload(file: UploadFile, user: User = Depends(get_user)):
    upload = save_upload(file, user)

    # Fire and forget — returns immediately
    process_upload.delay(upload.id)

    return {"upload_id": upload.id, "status": "processing"}

@app.post("/invite/")
async def invite_user(email: str, org: Org = Depends(get_org)):
    invite = create_invite(email, org)

    # Send email asynchronously
    send_email.delay(
        user_id=invite.inviter_id,
        template="invite",
        context={"invite_url": invite.url, "org_name": org.name}
    )

    return {"status": "invited"}
```

**Replace cron with periodic tasks:**

```python
# celery_app.py — add beat schedule
from celery.schedules import crontab

app.conf.beat_schedule = {
    'daily-report': {
        'task': 'tasks.generate_daily_report',
        'schedule': crontab(hour=3, minute=0),  # 3:00 AM
    },
    'cleanup-expired': {
        'task': 'tasks.cleanup_expired_sessions',
        'schedule': crontab(minute=0),  # Every hour
    },
    'health-check': {
        'task': 'tasks.system_health_check',
        'schedule': 300.0,  # Every 5 minutes
    },
}
```

**Run it:**

```bash
# Terminal 1: Worker (processes tasks)
celery -A celery_app worker --loglevel=info --concurrency=4

# Terminal 2: Beat (schedules periodic tasks)
celery -A celery_app beat --loglevel=info

# Terminal 3: Flower (monitoring dashboard)
celery -A celery_app flower --port=5555
```

**For simpler needs (no Redis), use PostgreSQL as the broker:**

```python
# If you don't want to run Redis, use django-db or sqlalchemy backend
# Good for < 1000 tasks/minute
app = Celery('myapp', broker='sqla+postgresql://user:pass@localhost/mydb')
```

Start with this architecture. Celery handles retry, concurrency, scheduling, and monitoring out of the box. You only need to scale Redis/workers as volume grows.'''
    ),
    (
        "thinking/firstprinciples-log-aggregation",
        "My microservices each write their own log files. Debugging issues across services is painful because I have to SSH into each server. How do I fix this?",
        r'''<think>
Let me derive a logging architecture from first principles.

What is the fundamental problem?

A single user request touches services A, B, C. When something goes wrong, I need to see
all three services' logs for that request, in chronological order.

Current state: logs are on individual servers → must SSH into each → manually correlate by timestamp.

What would the ideal state look like?
1. All logs in one place (searchable)
2. Correlated by request (trace all services for one request)
3. Structured (parse fields, not regex on strings)
4. Retained (don't lose logs when containers restart)

Let me derive each component:

Component 1: Structured logging
Why? Unstructured: "User 42 failed to login from 192.168.1.1"
You can't reliably extract user_id, action, ip with regex.
Structured: {"user_id": 42, "action": "login", "status": "failed", "ip": "192.168.1.1"}
Now you can filter: user_id=42 AND status=failed

Component 2: Correlation
When service A calls service B calls service C, how do I link them?
Answer: A unique request_id (trace_id) generated at the entry point, propagated to all downstream services.
Every log line includes this trace_id.
To see the full request flow: filter by trace_id.

Component 3: Centralization
Logs need to flow from N servers to 1 searchable store.
Pattern: Ship → Store → Search
- Ship: agent on each server reads logs and sends them
- Store: central storage (indexed for search)
- Search: UI to query across all services

The classic stack: ELK (Elasticsearch + Logstash + Kibana)
Lighter alternative: Loki + Promtail + Grafana
Lightest: just ship to a managed service (Datadog, CloudWatch, etc.)

For a small team, Loki is the sweet spot — it doesn't index log content (cheaper),
just labels (service, level), and you grep through content on query.

Component 4: Retention
Logs grow forever. Need rotation policy:
- Hot: last 7 days (fast search)
- Warm: 7-30 days (slower search)
- Cold: 30-90 days (compressed archive)
- Delete after 90 days (unless compliance requires more)

Let me put together a practical implementation.
</think>

The core problem: logs are scattered across servers with no correlation. You need structured logging, request correlation, and centralized search. Here's how to build it.

**Step 1: Structured logging in each service**

```python
# Use structlog — makes every log entry a JSON object
import structlog
import uuid

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.BoundLogger,
)

logger = structlog.get_logger()

# Output: {"event": "user_login", "user_id": 42, "status": "success",
#           "level": "info", "timestamp": "2026-03-05T10:30:00Z"}
logger.info("user_login", user_id=42, status="success")
```

**Step 2: Request correlation with trace_id**

```python
# middleware.py — propagate trace_id across services
import uuid
from contextvars import ContextVar

trace_id_var: ContextVar[str] = ContextVar('trace_id', default='')

class TraceMiddleware:
    """Extract or generate trace_id, add to all logs."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            # Propagate from upstream or generate new
            trace_id = (
                headers.get(b"x-trace-id", b"").decode()
                or str(uuid.uuid4())
            )
            trace_id_var.set(trace_id)

            # Bind to all subsequent log calls
            structlog.contextvars.bind_contextvars(
                trace_id=trace_id,
                service="order-service",  # Name of this service
            )

            # Add trace_id to response headers
            async def send_with_trace(message):
                if message["type"] == "http.response.start":
                    headers = list(message.get("headers", []))
                    headers.append((b"x-trace-id", trace_id.encode()))
                    message["headers"] = headers
                await send(message)

            await self.app(scope, receive, send_with_trace)
        else:
            await self.app(scope, receive, send)

# When calling downstream services, pass the trace_id
import httpx

async def call_payment_service(order_id: int):
    trace_id = trace_id_var.get()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://payment-service/charge",
            json={"order_id": order_id},
            headers={"X-Trace-Id": trace_id},  # Propagate!
        )
    return resp.json()
```

**Step 3: Centralize with Loki + Promtail + Grafana (lightweight stack)**

```yaml
# docker-compose.yml
services:
  loki:
    image: grafana/loki:latest
    ports: ["3100:3100"]
    volumes:
      - loki-data:/loki

  promtail:
    image: grafana/promtail:latest
    volumes:
      - /var/log:/var/log                    # Host logs
      - ./promtail-config.yml:/etc/promtail/config.yml
      - /var/run/docker.sock:/var/run/docker.sock  # Docker logs

  grafana:
    image: grafana/grafana:latest
    ports: ["3000:3000"]
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=changeme

# promtail-config.yml
server:
  http_listen_port: 9080

positions:
  filename: /tmp/positions.yaml

clients:
  - url: http://loki:3100/loki/api/v1/push

scrape_configs:
  - job_name: docker
    docker_sd_configs:
      - host: unix:///var/run/docker.sock
    relabel_configs:
      - source_labels: ['__meta_docker_container_name']
        target_label: 'container'
```

**Step 4: Query in Grafana**

```
# Find all logs for a specific request across all services:
{service=~".+"} |= "trace_id=abc-123"

# Find all errors in order-service in the last hour:
{service="order-service"} | json | level="error"

# Find slow requests (> 1s) in any service:
{service=~".+"} | json | duration > 1000
```

**The result:** One request touching 5 services? Search by trace_id and see the entire flow in chronological order, in one place. No more SSH.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
