"""Phase 2A: Advanced Reasoning — Backtracking & Dead-End Recovery (Part 7/8)"""

PAIRS = [
    (
        "thinking/backtrack-raw-sql-to-query-builder",
        "I've been building SQL queries with string concatenation for our reporting system. It's getting unwieldy with 20+ optional filters. Here's what I have:\n\n```python\ndef get_report(filters):\n    sql = \"SELECT * FROM orders WHERE 1=1\"\n    params = []\n    if filters.get('status'):\n        sql += f\" AND status = '{filters['status']}'\"\n    if filters.get('min_amount'):\n        sql += f\" AND amount >= {filters['min_amount']}\"\n    if filters.get('date_from'):\n        sql += f\" AND created_at >= '{filters['date_from']}'\"\n    # ... 17 more filters\n    return db.execute(sql)\n```\n\nHow should I improve this?",
        r'''<think>
Let me look at this code. First, the MASSIVE security issue: SQL injection everywhere. String interpolation of user input into SQL. But beyond that, the architecture is a mess. Let me think about how to fix this.

**First approach: just parameterize the existing code**
```python
sql += " AND status = %s"
params.append(filters['status'])
```
This fixes the injection but doesn't fix the maintainability. With 20 filters, you still have 20 if-blocks. Let me think bigger...

**Second approach: use an ORM (SQLAlchemy)**
```python
query = session.query(Order)
if filters.get('status'):
    query = query.filter(Order.status == filters['status'])
```
This is safer and more Pythonic, but still 20 if-blocks. The structure is the same, just with different syntax.

Wait, let me backtrack. Both approaches preserve the fundamental structure of "20 conditional blocks." The REAL problem is that the filter logic is imperative when it should be declarative.

**Third approach (backtracking): declarative filter mapping**
What if I define a mapping from filter names to query operations? Then the 20 if-blocks become a data structure:

```python
FILTERS = {
    'status': lambda q, v: q.filter(Order.status == v),
    'min_amount': lambda q, v: q.filter(Order.amount >= v),
    'date_from': lambda q, v: q.filter(Order.created_at >= v),
}
```

Then the entire function is:
```python
def get_report(filters):
    query = session.query(Order)
    for key, value in filters.items():
        if value is not None and key in FILTERS:
            query = FILTERS[key](query, value)
    return query.all()
```

This scales to 100 filters without growing the function. New filters are added as data, not code. Let me go with this.

But wait — what about complex filters like "amount BETWEEN min AND max" or "status IN (list)"? The lambda approach handles these:
```python
'amount_range': lambda q, v: q.filter(Order.amount.between(v['min'], v['max'])),
'statuses': lambda q, v: q.filter(Order.status.in_(v)),
```

This is the right pattern. Let me also address the SQL injection in the original.
</think>

Your code has a **critical SQL injection vulnerability** AND a structural problem. Let me trace through the solutions:

## The SQL Injection (Fix Immediately)

```python
# ❌ YOUR CODE: direct string interpolation = SQL injection
sql += f" AND status = '{filters['status']}'"
# Attack: filters['status'] = "'; DROP TABLE orders; --"
# Result: SELECT * FROM orders WHERE 1=1 AND status = ''; DROP TABLE orders; --'

# Even "just parameterizing" is a band-aid on the structural problem
```

## My Thinking Process

**Attempt 1:** Parameterize the SQL → fixes security but still 20 if-blocks.
**Attempt 2:** Use ORM → safer syntax but still 20 if-blocks.
**Backtrack:** The problem isn't the SQL syntax — it's that filter logic is **imperative** when it should be **declarative**.

## The Solution: Declarative Filter Registry

```python
from sqlalchemy import and_
from sqlalchemy.orm import Session
from datetime import date
from typing import Any, Callable

# Each filter is a function: (query, value) → query
FilterFunc = Callable  # (Query, Any) -> Query

# Define filters as DATA, not code
REPORT_FILTERS: dict[str, FilterFunc] = {
    # Simple equality
    "status": lambda q, v: q.filter(Order.status == v),
    "customer_id": lambda q, v: q.filter(Order.customer_id == v),
    "region": lambda q, v: q.filter(Order.region == v),

    # Comparisons
    "min_amount": lambda q, v: q.filter(Order.amount >= v),
    "max_amount": lambda q, v: q.filter(Order.amount <= v),

    # Date ranges
    "date_from": lambda q, v: q.filter(Order.created_at >= v),
    "date_to": lambda q, v: q.filter(Order.created_at <= v),

    # List membership
    "statuses": lambda q, v: q.filter(Order.status.in_(v)),
    "exclude_regions": lambda q, v: q.filter(~Order.region.in_(v)),

    # Pattern matching
    "name_contains": lambda q, v: q.filter(Order.name.ilike(f"%{v}%")),

    # Joins
    "customer_tier": lambda q, v: q.join(Customer).filter(Customer.tier == v),

    # Complex conditions
    "has_refund": lambda q, v: (
        q.filter(Order.refund_amount > 0) if v
        else q.filter(Order.refund_amount == 0)
    ),
}


def get_report(session: Session, filters: dict[str, Any]) -> list[Order]:
    """Apply all provided filters and return matching orders."""
    query = session.query(Order)

    for key, value in filters.items():
        if value is None:
            continue
        filter_func = REPORT_FILTERS.get(key)
        if filter_func is None:
            raise ValueError(f"Unknown filter: {key}")
        query = filter_func(query, value)

    return query.all()


# Usage — clean and readable
orders = get_report(session, {
    "status": "shipped",
    "min_amount": 100,
    "date_from": date(2024, 1, 1),
    "region": "US",
})
```

## Why This Is Better

| Aspect | Your 20 if-blocks | Declarative registry |
|--------|-------------------|---------------------|
| Adding a filter | Add if-block + SQL string | Add one line to dict |
| SQL injection risk | Every filter is a risk | ORM handles parameterization |
| Testing | Test the whole function | Test individual filters |
| Readability | Scroll through 60 lines | Scan a clean mapping |
| Reuse | Copy-paste the function | Share the registry across endpoints |

## Adding Sorting and Pagination

```python
SORT_FIELDS = {
    "created_at": Order.created_at,
    "amount": Order.amount,
    "status": Order.status,
}

def get_report(session, filters, sort_by="created_at", sort_dir="desc",
               page=1, per_page=50):
    query = session.query(Order)

    # Apply filters
    for key, value in filters.items():
        if value is not None and key in REPORT_FILTERS:
            query = REPORT_FILTERS[key](query, value)

    # Apply sorting
    sort_col = SORT_FIELDS.get(sort_by, Order.created_at)
    query = query.order_by(sort_col.desc() if sort_dir == "desc" else sort_col.asc())

    # Apply pagination
    total = query.count()
    results = query.offset((page - 1) * per_page).limit(per_page).all()

    return {"total": total, "page": page, "results": results}
```

The key insight from backtracking: when you have N conditional blocks doing the same structural thing, replace imperative conditionals with a declarative data structure.'''
    ),
    (
        "thinking/backtrack-monolithic-config-to-layered",
        "Our application config is a nightmare. We have a single settings.py with 500+ lines. It mixes database settings, API keys, feature flags, logging config, and business rules. Different environments (dev, staging, prod) are handled with if/else blocks throughout. How do I untangle this?",
        r'''<think>
Let me think about approaches to fixing this config mess.

**First approach: split into separate files per environment**
```
settings/
  base.py      # Shared settings
  dev.py       # from base import *; override stuff
  staging.py
  prod.py
```
Django uses this pattern. It works but has problems:
- `import *` is dangerous — hard to track what's overridden
- Secrets end up in config files
- Environment-specific logic is still scattered

Let me think more carefully...

**Second approach: single file with environment variables**
```python
DB_HOST = os.environ.get("DB_HOST", "localhost")
```
This is better for secrets (12-factor app). But with 500+ settings, this file is still a mess. And it doesn't address the mixing of DIFFERENT TYPES of config.

Wait, let me backtrack. The REAL problem isn't environments — it's that the file mixes fundamentally different things:
1. Infrastructure config (DB, cache, queue connections)
2. Secrets (API keys, passwords)
3. Feature flags (dynamic business toggles)
4. Business rules (pricing tiers, limits)
5. Framework config (logging, middleware, serializers)

These have different lifecycles:
- Infrastructure: changes per environment, rarely changes per deploy
- Secrets: changes per environment, must be secure, rotated periodically
- Feature flags: changes dynamically, shouldn't require deploy
- Business rules: changes with product decisions
- Framework config: changes with code changes

They should NOT be in the same file. Each type needs a different management mechanism.

**Third approach (after backtracking): layered config by concern**
Split by CONCERN, not by environment. Each layer handles its own environment differences.

This is the right approach.
</think>

The problem isn't just organization — it's that your config mixes things with **different lifecycles**. Let me trace through the solutions:

**First attempt:** Split by environment (dev.py, prod.py) → still a mess, just in multiple files.
**Second attempt:** Use env vars everywhere → better for secrets, but 500 settings in one file is still unreadable.
**Backtrack:** The real issue is mixing 5 different TYPES of config. Split by **concern**, not environment.

## The Layered Architecture

```
config/
  __init__.py          # Assembles the final config
  infrastructure.py    # DB, cache, queue connections
  framework.py         # Logging, middleware, serializers
  business_rules.py    # Pricing, limits, policies
  feature_flags.py     # Dynamic toggles (or from database)
  # Secrets come from environment variables / vault — NEVER in files
```

### Layer 1: Infrastructure (changes per environment)

```python
# config/infrastructure.py
import os

class DatabaseConfig:
    HOST = os.environ.get("DB_HOST", "localhost")
    PORT = int(os.environ.get("DB_PORT", "5432"))
    NAME = os.environ.get("DB_NAME", "myapp_dev")
    USER = os.environ.get("DB_USER", "postgres")
    PASSWORD = os.environ["DB_PASSWORD"]  # No default — MUST be set
    POOL_SIZE = int(os.environ.get("DB_POOL_SIZE", "5"))

    @classmethod
    def url(cls):
        return f"postgresql://{cls.USER}:{cls.PASSWORD}@{cls.HOST}:{cls.PORT}/{cls.NAME}"

class CacheConfig:
    URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    DEFAULT_TTL = int(os.environ.get("CACHE_TTL", "300"))

class QueueConfig:
    BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/1")
    RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/2")
```

### Layer 2: Framework (changes with code)

```python
# config/framework.py
import os

ENVIRONMENT = os.environ.get("APP_ENV", "development")

LOGGING = {
    "version": 1,
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json" if ENVIRONMENT == "production" else "simple",
        },
    },
    "root": {
        "level": "INFO" if ENVIRONMENT == "production" else "DEBUG",
        "handlers": ["console"],
    },
}

MIDDLEWARE = [
    "middleware.request_id",
    "middleware.logging",
    "middleware.auth",
]

CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",")
```

### Layer 3: Business Rules (changes with product decisions)

```python
# config/business_rules.py
"""Business rules — these are PRODUCT decisions, not infrastructure."""

class PricingTiers:
    FREE_MAX_USERS = 5
    FREE_MAX_STORAGE_MB = 100
    PRO_MAX_USERS = 50
    PRO_MAX_STORAGE_MB = 10_000
    ENTERPRISE_MAX_USERS = None  # Unlimited

class RateLimits:
    API_CALLS_PER_MINUTE_FREE = 60
    API_CALLS_PER_MINUTE_PRO = 600
    API_CALLS_PER_MINUTE_ENTERPRISE = 6000

class RetentionPolicy:
    LOG_RETENTION_DAYS = 90
    DELETED_ACCOUNT_RETENTION_DAYS = 30
    SESSION_TIMEOUT_MINUTES = 30
```

### Layer 4: Feature Flags (changes dynamically)

```python
# config/feature_flags.py
"""Feature flags — for database-backed flags, see app/flags.py"""

import os

# Static flags (deploy-time toggles)
ENABLE_NEW_DASHBOARD = os.environ.get("FF_NEW_DASHBOARD", "false") == "true"
ENABLE_BULK_EXPORT = os.environ.get("FF_BULK_EXPORT", "false") == "true"
ENABLE_AI_SUGGESTIONS = os.environ.get("FF_AI_SUGGESTIONS", "false") == "true"

# For dynamic flags, use the database-backed FeatureFlag model
# from app.flags import flag_enabled
```

### Assembly Point

```python
# config/__init__.py
from config.infrastructure import DatabaseConfig, CacheConfig, QueueConfig
from config.framework import LOGGING, MIDDLEWARE, CORS_ORIGINS, ENVIRONMENT
from config.business_rules import PricingTiers, RateLimits, RetentionPolicy
from config import feature_flags

# Validate critical config on startup
def validate():
    required_env = ["DB_PASSWORD", "SECRET_KEY"]
    missing = [var for var in required_env if var not in os.environ]
    if missing:
        raise EnvironmentError(
            f"Missing required environment variables: {', '.join(missing)}"
        )

validate()
```

## Environment-Specific Config

Instead of if/else blocks, use `.env` files:

```bash
# .env.dev (committed, no secrets)
APP_ENV=development
DB_HOST=localhost
DB_NAME=myapp_dev
DB_POOL_SIZE=2
CORS_ORIGINS=http://localhost:3000
FF_NEW_DASHBOARD=true

# .env.prod (NOT committed, managed by infra team)
APP_ENV=production
DB_HOST=prod-db.internal
DB_NAME=myapp
DB_POOL_SIZE=20
CORS_ORIGINS=https://app.example.com,https://www.example.com
```

## Before vs After

| Before (500-line settings.py) | After (layered config) |
|---|---|
| "Where is the DB timeout set?" → grep through 500 lines | Look in `infrastructure.py` |
| "What's the free tier user limit?" → mixed with DB settings | Look in `business_rules.py` |
| "Is feature X enabled?" → hidden in an if/else block | Look in `feature_flags.py` |
| Secrets scattered in the file | Secrets only in env vars |
| Changing business rules touches the same file as infra | Independent, clear ownership |'''
    ),
    (
        "thinking/backtrack-eager-loading-to-dataloader",
        "I have an N+1 query problem in my GraphQL API. For a query that returns 50 users, each with their posts and each post with its comments, I'm seeing 2500+ database queries. I tried eager loading with JOINs but now the response is slow because of massive joins. What's the right approach?",
        r'''<think>
N+1 query problem in GraphQL. Let me think through the approaches.

**First approach: Eager loading with JOINs**
The user already tried this. With users → posts → comments:
```sql
SELECT * FROM users
JOIN posts ON posts.user_id = users.id
JOIN comments ON comments.post_id = posts.id
```
This creates a cartesian product. If each user has 10 posts and each post has 20 comments:
50 users × 10 posts × 20 comments = 10,000 rows returned, with lots of duplicate user/post data.
The database query might be fast, but transferring and deserializing 10,000 rows with duplicate data is slow.

**Second approach: Lazy loading (the N+1 problem)**
```
1 query for 50 users
50 queries for posts (one per user)
50 × ~10 = 500 queries for comments (one per post)
Total: ~551 queries
```
Wait, the user said 2500+, which suggests deeper nesting or more posts/comments. Either way, too many queries.

Let me backtrack. Both approaches have fundamental problems with GraphQL because GraphQL resolvers execute independently — each resolver doesn't know what other resolvers need.

**Third approach (the right one): DataLoader pattern**
This is specifically designed for GraphQL. The key insight:

Instead of loading data one-at-a-time (N+1) or all-at-once (JOIN explosion), DataLoader BATCHES requests within a single execution tick:

1. Resolver for user 1 asks for posts for user_id=1
2. Resolver for user 2 asks for posts for user_id=2
3. ... resolver for user 50 asks for posts for user_id=50
4. DataLoader COLLECTS all 50 requests, executes ONE query:
   `SELECT * FROM posts WHERE user_id IN (1, 2, ..., 50)`
5. Distributes results back to each resolver

This gives us:
- 1 query for users
- 1 query for all posts (batched)
- 1 query for all comments (batched)
= 3 queries total, regardless of result size

This is the right approach for GraphQL. No cartesian product, no N+1.
</think>

Both eager loading (JOIN explosion) and lazy loading (N+1) are wrong for GraphQL. The right answer is the **DataLoader pattern** — batch individual resolver requests into bulk queries.

## Why Each Approach Fails

```
Lazy loading (N+1):
  50 users → 50 post queries → ~500 comment queries = 551 queries ❌

Eager loading (JOIN):
  1 massive query, but returns 10,000 rows with duplicate data ❌
  50 users × 10 posts × 20 comments = cartesian explosion

DataLoader (batching):
  1 query for users + 1 query for posts + 1 query for comments = 3 queries ✅
```

## How DataLoader Works

```python
from collections import defaultdict
from typing import Any

class DataLoader:
    """
    Batches individual load requests within a single event loop tick.
    Instead of N queries for N items, executes 1 query for all N items.
    """

    def __init__(self, batch_fn):
        self._batch_fn = batch_fn  # Function that loads many keys at once
        self._queue: list[int] = []
        self._cache: dict[int, Any] = {}
        self._futures: dict[int, asyncio.Future] = {}

    async def load(self, key: int):
        """Request a single item. Will be batched with other requests."""
        if key in self._cache:
            return self._cache[key]

        if key not in self._futures:
            future = asyncio.get_event_loop().create_future()
            self._futures[key] = future
            self._queue.append(key)

            # Schedule batch execution at end of current tick
            if len(self._queue) == 1:
                asyncio.get_event_loop().call_soon(self._dispatch)

        return await self._futures[key]

    def _dispatch(self):
        """Execute the batch load for all queued keys."""
        keys = list(self._queue)
        self._queue.clear()

        # One query for ALL keys
        results = asyncio.ensure_future(self._batch_fn(keys))
        results.add_done_callback(lambda f: self._resolve(keys, f.result()))

    def _resolve(self, keys, results):
        for key, result in zip(keys, results):
            self._cache[key] = result
            self._futures.pop(key).set_result(result)


# --- Batch loading functions ---

async def batch_load_posts(user_ids: list[int]) -> list[list[Post]]:
    """Load posts for multiple users in ONE query."""
    # One query instead of N:
    posts = await db.execute(
        "SELECT * FROM posts WHERE user_id = ANY($1) ORDER BY created_at DESC",
        user_ids
    )
    # Group by user_id, maintaining order of input keys
    posts_by_user = defaultdict(list)
    for post in posts:
        posts_by_user[post.user_id].append(post)
    return [posts_by_user.get(uid, []) for uid in user_ids]


async def batch_load_comments(post_ids: list[int]) -> list[list[Comment]]:
    """Load comments for multiple posts in ONE query."""
    comments = await db.execute(
        "SELECT * FROM comments WHERE post_id = ANY($1) ORDER BY created_at",
        post_ids
    )
    comments_by_post = defaultdict(list)
    for comment in comments:
        comments_by_post[comment.post_id].append(comment)
    return [comments_by_post.get(pid, []) for pid in post_ids]
```

## Using DataLoader in GraphQL Resolvers

```python
import strawberry
from strawberry.types import Info

# Create loaders per-request (important: don't share across requests)
def get_context():
    return {
        "post_loader": DataLoader(batch_load_posts),
        "comment_loader": DataLoader(batch_load_comments),
    }

@strawberry.type
class User:
    id: int
    name: str

    @strawberry.field
    async def posts(self, info: Info) -> list["Post"]:
        # This looks like it loads ONE user's posts,
        # but DataLoader batches all 50 users' requests into ONE query
        return await info.context["post_loader"].load(self.id)

@strawberry.type
class Post:
    id: int
    title: str
    user_id: int

    @strawberry.field
    async def comments(self, info: Info) -> list["Comment"]:
        return await info.context["comment_loader"].load(self.id)
```

## Query Execution Timeline

```
GraphQL query: { users { name posts { title comments { text } } } }

WITHOUT DataLoader:
  t=0:  SELECT * FROM users                          (1 query)
  t=1:  SELECT * FROM posts WHERE user_id = 1        (query 2)
  t=2:  SELECT * FROM posts WHERE user_id = 2        (query 3)
  ...
  t=50: SELECT * FROM posts WHERE user_id = 50       (query 51)
  t=51: SELECT * FROM comments WHERE post_id = 1     (query 52)
  ...
  t=550: SELECT * FROM comments WHERE post_id = 500  (query 551)

WITH DataLoader:
  t=0:  SELECT * FROM users                                    (query 1)
  t=1:  SELECT * FROM posts WHERE user_id IN (1,2,...,50)      (query 2)
  t=2:  SELECT * FROM comments WHERE post_id IN (1,2,...,500)  (query 3)
  DONE. 3 queries total.
```

The key insight from backtracking: JOIN-based eager loading fights the GraphQL execution model. DataLoader works WITH it — each resolver remains simple and independent, but requests are transparently batched at the data layer.'''
    ),
    (
        "thinking/backtrack-cron-to-event-driven-scheduling",
        "We have 30 cron jobs that run at various intervals. Some depend on others completing first. We handle dependencies by scheduling the dependent job 30 minutes after the prerequisite, hoping it's done by then. Failures go unnoticed until someone checks logs. How do I fix this?",
        r'''<think>
Cron with implicit dependencies via timing offsets — this is a brittle architecture. Let me think about solutions.

**First approach: better cron management**
Use something like systemd timers or crontab with better logging. Add monitoring alerts for failed jobs. But this doesn't solve the dependency problem — you're still guessing timing offsets.

**Second approach: use a job queue with chaining**
Celery with canvas (chain, group, chord):
```python
chain(job_a.s(), job_b.s(), job_c.s())()
```
This solves ordering. But Celery chains are imperative — the dependency graph is scattered across code. And it doesn't handle "job A triggers jobs B, C, and D which all need to complete before job E runs."

Let me backtrack. The real problem is they need a DAG (Directed Acyclic Graph) workflow — jobs with explicit dependencies, where each job runs ONLY when its dependencies complete successfully.

**Third approach (after backtracking): workflow orchestrator**
This is what tools like Airflow, Prefect, or Dagster solve. But those might be overkill for 30 cron jobs. Let me think about a lighter weight option...

Actually, for 30 jobs with dependencies, Prefect or a simple DAG runner IS the right answer. The alternative (building a custom DAG executor) would be reinventing the wheel.

But let me provide both: a lightweight custom solution for teams that don't want a new dependency, and a Prefect solution for teams ready to adopt a tool.
</think>

Timing-based dependencies between cron jobs is fundamentally fragile. Let me trace through the solutions:

**Attempt 1:** Better cron monitoring → still guessing timing offsets.
**Attempt 2:** Celery chains → solves ordering but not complex DAGs.
**Backtrack:** What you need is a **DAG (Directed Acyclic Graph) executor** — jobs run only when dependencies complete.

## The Problem Visualized

```
CURRENT (timing-based, fragile):
  00:00  Job A runs (takes 5-45 minutes unpredictably)
  00:30  Job B runs (HOPES A is done — sometimes it isn't)
  01:00  Job C runs (depends on A AND B)
  01:30  Job D runs... you get the idea

CORRECT (dependency-based):
  Job A completes → triggers Job B
  Job A completes → triggers Job C
  Job B + Job C complete → triggers Job D
```

## Solution 1: Lightweight DAG Runner (No New Dependencies)

```python
"""Simple DAG-based job scheduler using only stdlib + your existing DB."""
import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Callable, Awaitable

logger = logging.getLogger(__name__)

class JobStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class Job:
    name: str
    fn: Callable[[], Awaitable[None]]
    depends_on: list[str] = field(default_factory=list)
    status: JobStatus = JobStatus.PENDING
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None

class DAGRunner:
    def __init__(self):
        self.jobs: dict[str, Job] = {}

    def add(self, name: str, fn, depends_on: list[str] | None = None):
        self.jobs[name] = Job(name=name, fn=fn, depends_on=depends_on or [])

    def _ready_jobs(self) -> list[Job]:
        """Jobs whose dependencies are all completed."""
        ready = []
        for job in self.jobs.values():
            if job.status != JobStatus.PENDING:
                continue
            deps_met = all(
                self.jobs[dep].status == JobStatus.COMPLETED
                for dep in job.depends_on
            )
            if deps_met:
                ready.append(job)
        return ready

    async def run(self):
        """Execute all jobs respecting dependency order."""
        while True:
            ready = self._ready_jobs()
            if not ready:
                # Check if we're done or deadlocked
                pending = [j for j in self.jobs.values() if j.status == JobStatus.PENDING]
                running = [j for j in self.jobs.values() if j.status == JobStatus.RUNNING]
                if not pending and not running:
                    break  # All done
                if pending and not running:
                    failed_deps = [j.name for j in self.jobs.values() if j.status == JobStatus.FAILED]
                    logger.error("Deadlock: jobs %s waiting on failed: %s",
                                [j.name for j in pending], failed_deps)
                    break
                await asyncio.sleep(1)
                continue

            # Run all ready jobs in parallel
            tasks = [self._run_job(job) for job in ready]
            await asyncio.gather(*tasks)

    async def _run_job(self, job: Job):
        job.status = JobStatus.RUNNING
        job.started_at = datetime.utcnow()
        logger.info("Starting job: %s", job.name)
        try:
            await job.fn()
            job.status = JobStatus.COMPLETED
            job.completed_at = datetime.utcnow()
            duration = (job.completed_at - job.started_at).total_seconds()
            logger.info("Completed job: %s (%.1fs)", job.name, duration)
        except Exception as e:
            job.status = JobStatus.FAILED
            job.error = str(e)
            logger.error("Failed job: %s — %s", job.name, e)
            await send_alert(f"Job {job.name} failed: {e}")


# --- Define your 30 jobs as a DAG ---

dag = DAGRunner()

dag.add("extract_orders", extract_orders_from_api)
dag.add("extract_products", extract_products_from_api)
dag.add("transform_orders", transform_order_data, depends_on=["extract_orders"])
dag.add("transform_products", transform_product_data, depends_on=["extract_products"])
dag.add("load_warehouse", load_to_warehouse,
        depends_on=["transform_orders", "transform_products"])  # Waits for BOTH
dag.add("generate_reports", generate_daily_reports, depends_on=["load_warehouse"])
dag.add("send_emails", send_report_emails, depends_on=["generate_reports"])

# Run nightly — ONE cron entry instead of 30
# 0 0 * * * python run_pipeline.py
asyncio.run(dag.run())
```

## Solution 2: Prefect (If You Want a Real Tool)

```python
from prefect import flow, task
from prefect.tasks import task_input_hash

@task(retries=2, retry_delay_seconds=60)
def extract_orders():
    return api.get_orders(date=today())

@task(retries=2)
def extract_products():
    return api.get_products()

@task
def transform_orders(raw_orders):
    return [clean(order) for order in raw_orders]

@task
def load_warehouse(orders, products):
    db.bulk_insert("warehouse.orders", orders)
    db.bulk_insert("warehouse.products", products)

@flow(name="nightly-pipeline")
def nightly_pipeline():
    # Prefect automatically builds the DAG from data dependencies
    raw_orders = extract_orders()
    raw_products = extract_products()  # Runs in PARALLEL with orders
    clean_orders = transform_orders(raw_orders)  # Waits for extract_orders
    clean_products = transform_products(raw_products)
    load_warehouse(clean_orders, clean_products)  # Waits for BOTH transforms
    generate_reports()
    send_emails()

# Prefect handles: retries, logging, alerting, monitoring UI, scheduling
```

## What You Gain

| Before (30 crons) | After (1 DAG) |
|---|---|
| 30 crontab entries | 1 scheduled pipeline |
| Timing-guessed dependencies | Explicit dependency graph |
| Silent failures | Automatic alerting on failure |
| No retry logic | Configurable retries per job |
| Can't see what's running | Visual dashboard of pipeline status |
| Cascading failures | Failed job blocks dependents (by design) |

The key backtrack: cron is a SCHEDULER, not an ORCHESTRATOR. When jobs have dependencies, you need orchestration — explicit "run B only after A succeeds."'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
