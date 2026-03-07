"""
Ambiguous request handling pairs - vague performance complaints
"""

pairs = [
    {
        "instruction": r'''My app is slow. Can you fix it?''',
        "output": r'''<think>
This is extremely vague. "Slow" could mean anything -- slow initial load, slow API responses, slow database queries, slow rendering, memory leaks causing degradation over time. I don't know the tech stack, whether this is frontend or backend, what "slow" means quantitatively, or what changed recently. I need to ask targeted questions before I can help effectively.
</think>

A few things I'd want to understand before diving in:

1. **What part feels slow?** Is it the initial page load, specific user actions (like searching or saving), API response times, or does the app slow down the longer it runs?
2. **What's your tech stack?** (Language, framework, database, hosting)
3. **When did it start?** Was it always slow or did performance degrade after a recent change or traffic increase?

In the meantime, here's a general diagnostic starting point. Most "slow app" issues fall into a few buckets, and you can narrow it down with basic profiling:

```python
import time
import functools
import logging

logger = logging.getLogger(__name__)

def profile_endpoint(func):
    """Decorator to log execution time of any function or route handler."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        start = time.perf_counter()
        result = func(*args, **kwargs)
        elapsed_ms = (time.perf_counter() - start) * 1000
        logger.info(f"{func.__name__} took {elapsed_ms:.1f}ms")
        if elapsed_ms > 500:
            logger.warning(f"SLOW: {func.__name__} took {elapsed_ms:.1f}ms")
        return result
    return wrapper

# Apply to suspect functions:
# @profile_endpoint
# def get_users():
#     ...
```

Also check the usual suspects:
- **Database**: Are you missing indexes? Run `EXPLAIN ANALYZE` on your slowest queries.
- **N+1 queries**: Are you hitting the DB in a loop instead of batching?
- **No caching**: Are you recomputing expensive results on every request?
- **Large payloads**: Are you returning way more data than the client needs?

Once you tell me which area is slow, I can give you a targeted fix.'''
    },
    {
        "instruction": r'''The API is laggy, please optimize it.''',
        "output": r'''<think>
"Laggy API" -- could be network latency, slow server processing, large response payloads, missing caching, database bottleneck, or even DNS/TLS overhead. I don't know which endpoints are slow, what the response times look like, or what the API does. Need to clarify scope before recommending specific fixes.
</think>

Before I can optimize effectively, I'd want to know:

1. **Which endpoints are slow?** All of them, or specific ones? What response times are you seeing vs. what you'd expect?
2. **What does the API do?** REST/GraphQL? What database? Any external service calls?
3. **What's the load?** Requests per second, concurrent users?

That said, here's a practical approach to identify and fix the most common API performance issues:

```python
# Step 1: Add middleware to log response times per endpoint
import time
from fastapi import Request

# For FastAPI (adapt for Flask/Django as needed)
@app.middleware("http")
async def log_request_time(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    print(f"{request.method} {request.url.path} -- {duration_ms:.0f}ms")
    response.headers["X-Response-Time"] = f"{duration_ms:.0f}ms"
    return response

# Step 2: Add caching for expensive, rarely-changing data
from functools import lru_cache

@lru_cache(maxsize=256)
def get_config_by_key(key: str):
    # This hits the DB once, then serves from memory
    return db.query(Config).filter(Config.key == key).first()

# Step 3: Check for N+1 queries -- this is the #1 cause of slow APIs
# BAD:
# for user in users:
#     orders = db.query(Order).filter(Order.user_id == user.id).all()

# GOOD:
# users = db.query(User).options(joinedload(User.orders)).all()
```

Common quick wins ranked by impact:
- Add database indexes on columns used in WHERE/JOIN clauses
- Use eager loading instead of lazy loading (fixes N+1)
- Add response caching for read-heavy endpoints
- Paginate large result sets instead of returning everything
- Use connection pooling for your database

Share your slowest endpoint's code and I'll pinpoint the exact issue.'''
    },
    {
        "instruction": r'''The page takes forever to load. Help!''',
        "output": r'''<think>
"Page takes forever" -- is this a server-rendered page or an SPA? Could be a frontend issue (huge JS bundle, unoptimized images, render-blocking resources) or a backend issue (slow API call that blocks rendering). I don't know the framework, what the page shows, or how long "forever" actually is. Need to distinguish frontend vs backend bottleneck.
</think>

A few quick questions to narrow this down:

1. **What kind of page?** Server-rendered (Django/Rails/PHP) or a single-page app (React/Vue/Angular)?
2. **How slow is "forever"?** 3 seconds? 15 seconds? Is it the first load only or every load?
3. **What does the page display?** A big data table? Images? A dashboard with charts?

Here's how to diagnose it yourself right now -- open your browser DevTools (F12) and check the Network tab:

```text
Things to look for in DevTools Network tab:
- Is there one request that takes way longer than the rest? (backend bottleneck)
- Is the JS bundle huge (>500KB gzipped)? (frontend bottleneck)
- Are there dozens of API calls firing? (N+1 frontend problem)
- Are images unoptimized (>200KB each)? (asset problem)
```

Assuming it's a React/Vue SPA with a slow initial load, the most common fixes are:

```javascript
// 1. Lazy-load routes so you don't ship everything upfront
import { lazy, Suspense } from 'react';

const Dashboard = lazy(() => import('./pages/Dashboard'));
const Settings = lazy(() => import('./pages/Settings'));

function App() {
    return (
        <Suspense fallback={<div>Loading...</div>}>
            <Routes>
                <Route path="/" element={<Dashboard />} />
                <Route path="/settings" element={<Settings />} />
            </Routes>
        </Suspense>
    );
}

// 2. Don't fetch everything on mount -- paginate or virtualize
// BAD: fetch all 10,000 rows on page load
// GOOD: fetch first 50, load more on scroll

// 3. Compress and resize images at build time
// Use next/image, or run: npx sharp-cli resize 800 input.png -o output.webp
```

If the bottleneck is a slow backend call, share the endpoint code and I'll help optimize that instead.'''
    },
    {
        "instruction": r'''Our database queries are slow, can you optimize them?''',
        "output": r'''<think>
"Queries are slow" -- which queries? All of them? A few specific ones? What database engine? How big are the tables? Are there indexes? Is it a read-heavy or write-heavy workload? This is way too vague to act on without more details. I should ask for the specific slow queries and the schema.
</think>

I'd love to help, but I need a bit more context:

1. **Which database?** PostgreSQL, MySQL, SQLite, MongoDB, something else?
2. **Which queries are slow?** Can you share the SQL (or ORM code) for the worst offenders?
3. **How big are the tables?** Thousands of rows or millions?

Without seeing the actual queries, here's a systematic approach to find and fix slow queries:

```sql
-- Step 1: Find your slowest queries (PostgreSQL example)
-- Enable slow query logging:
ALTER SYSTEM SET log_min_duration_statement = 200;  -- log queries > 200ms
SELECT pg_reload_conf();

-- Or query pg_stat_statements for top offenders:
SELECT query, calls, mean_exec_time, total_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Step 2: Analyze a slow query
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM orders WHERE customer_id = 12345;

-- If you see "Seq Scan" on a large table, you need an index:
CREATE INDEX idx_orders_customer_id ON orders(customer_id);

-- Step 3: Common fixes

-- Missing composite index for multi-column WHERE clauses:
-- If you query: WHERE status = 'active' AND created_at > '2025-01-01'
CREATE INDEX idx_orders_status_created ON orders(status, created_at);

-- Covering index to avoid table lookups entirely:
CREATE INDEX idx_orders_covering ON orders(customer_id)
    INCLUDE (status, total);
```

The most common causes of slow queries:
- **Missing indexes** on columns in WHERE, JOIN, and ORDER BY clauses
- **SELECT * instead of selecting only needed columns** -- fetches unnecessary data
- **No LIMIT** on queries that could return thousands of rows
- **Subqueries that should be JOINs** (or vice versa depending on the case)
- **Stale statistics** -- run `ANALYZE tablename;` to update the query planner

Share your slowest query and its EXPLAIN output and I'll give you the exact fix.'''
    },
    {
        "instruction": r'''Our app crashes under load. Fix it.''',
        "output": r'''<think>
"Crashes under load" -- this could be out-of-memory kills, thread/connection pool exhaustion, unhandled exceptions under concurrency, database connection limits, file descriptor limits, or even hitting OS-level resource caps. I don't know the stack, the scale, what "load" means, or what the crash looks like. Need to know error messages, how much load triggers it, and the architecture.
</think>

This is a critical issue, so let me ask a few targeted questions to avoid wasting time:

1. **What does "crash" look like?** Process exits? OOM kill? HTTP 502/503? Unresponsive and needs restart?
2. **What's the stack?** Language, framework, web server, database, and how are you deploying (containers, VMs, serverless)?
3. **What load triggers it?** Rough numbers -- 100 concurrent users? 1000 requests/sec? Does it happen gradually or suddenly?

Here's a diagnostic checklist and common fixes for load-related crashes:

```python
# 1. Check if it's an OOM kill (most common "crash under load")
# In your container/server, check:
# dmesg | grep -i "oom\|killed"
# docker inspect <container> | grep OOMKilled

# 2. Connection pool exhaustion -- very common with databases
# BAD: creating a new connection per request
# GOOD: use a connection pool with proper limits

from sqlalchemy import create_engine

engine = create_engine(
    "postgresql://user:pass@localhost/db",
    pool_size=20,          # max persistent connections
    max_overflow=10,       # extra connections under burst
    pool_timeout=30,       # wait time before giving up
    pool_recycle=1800,     # recycle stale connections
    pool_pre_ping=True,    # verify connections are alive
)

# 3. Add graceful degradation with rate limiting
from fastapi import FastAPI
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()

@app.get("/api/data")
@limiter.limit("100/minute")
async def get_data(request):
    return {"data": "..."}

# 4. Add health checks and resource monitoring
import psutil

@app.get("/health")
def health_check():
    memory = psutil.virtual_memory()
    return {
        "status": "ok" if memory.percent < 90 else "degraded",
        "memory_percent": memory.percent,
        "cpu_percent": psutil.cpu_percent(),
    }
```

Key areas to investigate:
- **Memory leaks**: Does memory grow steadily until crash? Profile with tracemalloc
- **Connection limits**: DB, Redis, or external API connection pools too small
- **Sync blocking**: A sync call blocking the event loop (if using async framework)
- **No backpressure**: Accepting requests faster than you can process them

Share the error logs or crash output and I'll identify the root cause.'''
    },
]
