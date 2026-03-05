"""Thinking-trace pairs: architecture decisions with explicit tradeoff reasoning."""

PAIRS = [
    (
        "thinking/arch-monolith-vs-microservices",
        "We have a Django monolith serving 500 requests/sec with 15 developers. The CEO wants to move to microservices because 'Netflix does it.' Should we? What's the right approach?",
        '''<think>
Let me think about this carefully instead of jumping to a recommendation.

Current state: Django monolith, 500 req/s, 15 developers. That's actually a medium-sized system with a small-medium team.

Arguments FOR microservices:
- Independent deployment per service
- Teams can use different languages/frameworks
- Individual services can scale independently
- Fault isolation (one service down doesn't kill everything)

Arguments AGAINST microservices at this scale:
- 15 developers is too few. Netflix has thousands of engineers. Microservices need dedicated platform teams for: service discovery, distributed tracing, config management, CI/CD per service, API gateways.
- 500 req/s is trivially handled by a single Django instance. Even a modest server handles 1000+ req/s.
- Distributed systems are MUCH harder to debug. A stack trace becomes a distributed trace across 10 services.
- Data consistency goes from "database transaction" to "saga pattern with compensating transactions."
- Latency increases -- every inter-service call adds network round-trip time.
- The team will spend 6-12 months building infrastructure instead of features.

The real question: what problems are they actually experiencing?
- Slow deployments? -> Fix CI/CD, not architecture
- Team stepping on each other? -> Better module boundaries within the monolith
- Performance bottlenecks? -> Profile and optimize the hot path, or extract just that one piece
- Long test suites? -> Parallelize tests, not services

The "modular monolith" is almost certainly the right answer here. Keep one deployable unit but enforce clean module boundaries. If specific modules later need independent scaling, extract them one at a time with clear criteria.

Martin Fowler's rule: "Don't start with microservices. Start with a monolith, split it later."

I should give concrete criteria for WHEN to extract:
1. A module needs a different scaling profile (CPU-heavy vs I/O-heavy)
2. A module needs a different deployment cadence (daily vs monthly)
3. A module needs a different tech stack (ML model in Python, API in Go)
4. The team grows past ~30 engineers working on the same codebase
</think>

**Don't do it.** At 500 req/s with 15 developers, microservices will slow your team down, not speed it up. Here's the honest analysis:

**What Netflix has that you don't:**
- 2,000+ engineers (dedicated platform teams for service mesh, tracing, deployment)
- Millions of req/s requiring independent scaling
- 10+ years of internal tooling investment
- Entire teams just for service discovery, chaos engineering, and observability

**What microservices will cost you at your scale:**
- 6-12 months of infrastructure work (service discovery, API gateway, distributed tracing, per-service CI/CD) before shipping a single feature
- Every database transaction becomes a saga pattern
- Every stack trace becomes a distributed trace
- Debugging goes from "read the logs" to "correlate logs across 10 services"

**What to do instead -- modular monolith:**

```python
# project structure -- enforce boundaries without network calls
myapp/
    accounts/          # module boundary
        api.py         # public interface (only import this from outside)
        models.py      # internal (no cross-module model imports)
        services.py    # internal
        tests/
    payments/
        api.py         # public interface
        models.py
        services.py
        tests/
    orders/
        api.py
        models.py
        services.py
        tests/
    shared/            # truly shared utilities only
        auth.py
        pagination.py
```

```python
# Enforce module boundaries with an import linter
# myapp/accounts/api.py -- the ONLY public interface
from myapp.accounts.services import AccountService

def get_account(user_id: int) -> dict:
    return AccountService.get(user_id)

def create_account(email: str, name: str) -> dict:
    return AccountService.create(email, name)

# Other modules import from api.py ONLY:
# GOOD: from myapp.accounts.api import get_account
# BAD:  from myapp.accounts.models import Account  (cross-boundary)
```

**When to extract a service (concrete criteria):**
1. A module needs >10x different scaling (e.g., image processing at 50x CPU)
2. A module needs independent deployment cadence (ML model updates daily, API monthly)
3. The team grows past ~30 engineers in the same repo
4. A module needs a fundamentally different tech stack

**Extract one at a time, not big-bang.** Start with the module that meets criteria most clearly, run both paths in parallel for a month, then cut over.'''
    ),
    (
        "thinking/arch-database-choice",
        "We're building a social platform with posts, comments, likes, follower graphs, and a news feed. Should we use PostgreSQL, MongoDB, or a combination? We expect 1M users in year one.",
        '''<think>
Let me think through the data access patterns for each feature:

1. Posts and comments: classic relational data
   - Posts belong to users, comments belong to posts
   - Need ACID for write operations (don't want half-created posts)
   - Need efficient querying by user, by time, by topic
   - PostgreSQL is ideal here -- foreign keys, indexes, transactions

2. Likes: high-volume, simple structure
   - Basically a join table: (user_id, post_id, created_at)
   - Very write-heavy (many likes per second)
   - Need fast count queries and "has user X liked post Y" checks
   - PostgreSQL handles this fine with proper indexing. Counter cache for fast counts.

3. Follower graph: many-to-many relationships
   - (follower_id, followed_id) join table
   - Need "who does X follow?" and "who follows X?" queries
   - For 1M users, this is manageable in PostgreSQL. At 100M+ you might want a graph database.
   - PostgreSQL with proper indexes handles follower queries well at this scale.

4. News feed: the hard part
   - "Show me recent posts from people I follow, ranked by relevance"
   - Two approaches:
     a. Fan-out on read: query posts WHERE author_id IN (followed_ids) ORDER BY time. Slow for users following 1000+ people.
     b. Fan-out on write: when user posts, write to each follower's feed table. Fast reads, expensive writes. What Twitter/Instagram does.
   - At 1M users, fan-out on read is actually fine with proper indexing.

So what about MongoDB?
- Pros: flexible schema (good for evolving post content), good for document-like data
- Cons: no joins (need to denormalize), no transactions across collections (until v4+), harder to maintain referential integrity
- The "flexible schema" advantage is overrated -- you'll end up enforcing schema in application code anyway

For 1M users, PostgreSQL handles all of this. Adding MongoDB creates operational complexity (two databases to maintain, backup, monitor) without meaningful benefit.

When WOULD I recommend MongoDB? If posts have highly variable structure (some have images, some have polls, some have location data with different fields). But even then, PostgreSQL's JSONB column handles this well.

My recommendation: PostgreSQL only, with Redis for caching hot data (feed cache, like counts, online status).

Let me also think about scale: 1M users is actually not that big.
- Assuming 10% daily active, that's 100K DAU
- Maybe 500K reads/day, 50K writes/day
- PostgreSQL on a decent server handles this trivially
- A single PostgreSQL instance handles 10K+ queries/sec with proper indexing
</think>

**PostgreSQL only, with Redis for caching.** Skip MongoDB entirely at this scale. Here's why:

**1M users is smaller than you think:**
- ~100K daily active users (10% DAU is typical)
- ~500K reads/day, ~50K writes/day
- A single PostgreSQL instance handles 10K+ queries/sec
- You won't hit database bottlenecks for years

**Schema design (all PostgreSQL):**

```sql
-- Core tables with proper indexing
CREATE TABLE users (
    id BIGSERIAL PRIMARY KEY,
    username VARCHAR(30) UNIQUE NOT NULL,
    display_name VARCHAR(100),
    bio TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE posts (
    id BIGSERIAL PRIMARY KEY,
    author_id BIGINT REFERENCES users(id) NOT NULL,
    content TEXT NOT NULL,
    media JSONB DEFAULT '[]',  -- flexible structure for images, polls, etc.
    like_count INT DEFAULT 0,  -- counter cache (avoid COUNT queries)
    comment_count INT DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_posts_author_time ON posts(author_id, created_at DESC);

CREATE TABLE comments (
    id BIGSERIAL PRIMARY KEY,
    post_id BIGINT REFERENCES posts(id) NOT NULL,
    author_id BIGINT REFERENCES users(id) NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_comments_post ON comments(post_id, created_at);

CREATE TABLE likes (
    user_id BIGINT REFERENCES users(id),
    post_id BIGINT REFERENCES posts(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (user_id, post_id)
);

CREATE TABLE follows (
    follower_id BIGINT REFERENCES users(id),
    followed_id BIGINT REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (follower_id, followed_id)
);
CREATE INDEX idx_follows_reverse ON follows(followed_id);  -- "who follows me"
```

**News feed (fan-out on read -- correct at this scale):**

```python
async def get_feed(user_id: int, limit: int = 50, before: datetime = None):
    query = """
        SELECT p.*, u.username, u.display_name
        FROM posts p
        JOIN follows f ON f.followed_id = p.author_id
        JOIN users u ON u.id = p.author_id
        WHERE f.follower_id = $1
          AND ($2::timestamptz IS NULL OR p.created_at < $2)
        ORDER BY p.created_at DESC
        LIMIT $3
    """
    return await db.fetch(query, user_id, before, limit)
```

**Add Redis for hot-path caching only:**

```python
# Cache feed for 60 seconds -- eliminates repeated feed queries
async def get_cached_feed(user_id: int) -> list:
    key = f"feed:{user_id}"
    cached = await redis.get(key)
    if cached:
        return json.loads(cached)
    feed = await get_feed(user_id)
    await redis.setex(key, 60, json.dumps(feed))
    return feed

# Cache like counts (updated via trigger or application)
# Cache online status (ephemeral data, perfect for Redis)
```

**When to add complexity (not now):**
- **10M+ users**: Switch to fan-out on write (materialized feed table)
- **100M+ users**: Consider graph database for follower queries
- **Variable post types**: JSONB column handles this without MongoDB
- **Full-text search**: Add PostgreSQL `tsvector` or Elasticsearch'''
    ),
    (
        "thinking/arch-api-versioning",
        "We have a public REST API used by 200+ third-party integrators. We need to make breaking changes to 3 endpoints. How should we handle API versioning? We've never versioned before.",
        '''<think>
200+ integrators, breaking changes to 3 endpoints, never versioned before. This is a delicate situation because:

1. If we break their integrations, we lose trust and possibly customers
2. We need a versioning strategy that works going forward, not just for this change
3. We need a migration path that gives integrators time to update

Let me evaluate versioning approaches:

**URL path versioning** (api/v1/users, api/v2/users):
- Pros: Very explicit, easy to understand, easy to route
- Cons: Clutters URLs, makes it look like everything changed when maybe only 3 endpoints did
- Used by: Stripe, GitHub, Twitch

**Header versioning** (Accept: application/vnd.api+json; version=2):
- Pros: Clean URLs, proper use of content negotiation
- Cons: Harder to discover, harder to test in browser, easy to forget
- Used by: GitHub (also supports this)

**Query parameter** (?version=2):
- Pros: Simple, works everywhere
- Cons: Pollutes query string, easy to confuse with other params

For a first-time versioning effort with 200+ integrators, I'd go with URL path versioning because:
- Most visible and hardest to get wrong
- Integrators immediately see which version they're on
- Documentation is clearer
- Browser/curl testing is simpler
- Stripe does it this way and they're the gold standard for API design

But wait -- we only need to version 3 endpoints, not the whole API. If we use URL-level versioning (api/v1/ vs api/v2/), integrators might think EVERYTHING changed. Better approach:

Keep most endpoints unversioned, but introduce versioned routes only for the 3 that change. Or... version the whole API but keep v1 and v2 mostly identical, with only the 3 endpoints differing.

Actually, the cleanest approach: version the whole API (v1 and v2 exist), but v2 is just v1 with the 3 endpoint changes. All other endpoints behave identically in both versions. This gives a clean migration path.

Migration plan:
1. Release v2 alongside v1 (both live simultaneously)
2. Notify all 200+ integrators with migration guide
3. Give 6-12 month deprecation window
4. Monitor v1 usage, follow up with holdouts
5. Sunset v1 with 30-day final notice

I also need to think about: how to implement this without duplicating code for every endpoint. The answer is: use a thin versioning layer that transforms v1 requests/responses to match the internal API, while v2 maps 1:1.
</think>

**URL path versioning (`/api/v1/`, `/api/v2/`)** with a 12-month migration window. Here's the complete strategy:

**Why URL versioning (not headers/query params):**
- 200+ integrators need something impossible to miss
- Browser/curl testing works without special headers
- Documentation is unambiguous
- Stripe, GitHub, and Twitch use this pattern for good reason

**Implementation -- version only at the routing layer, not in business logic:**

```python
# Don't duplicate business logic. Use a thin compatibility layer.
# app/api/router.py

from fastapi import APIRouter, Request

v1 = APIRouter(prefix="/api/v1")
v2 = APIRouter(prefix="/api/v2")

# Unchanged endpoints -- same handler for both versions
from app.handlers import users, billing, analytics

v1.include_router(users.router)
v2.include_router(users.router)  # identical behavior
v1.include_router(analytics.router)
v2.include_router(analytics.router)

# Changed endpoints -- v1 gets compatibility shim, v2 gets new behavior
from app.handlers import orders_v2

# V2: new endpoint shape
v2.include_router(orders_v2.router)

# V1: compatibility wrapper that translates old format to new
@v1.get("/orders/{order_id}")
async def get_order_v1(order_id: int):
    """V1 compatibility: translates new response format to old."""
    order = await orders_v2.get_order(order_id)
    # Transform v2 response to v1 shape
    return {
        "id": order["id"],
        "total": order["amount"]["total"],      # v2 nests under "amount"
        "currency": "USD",                       # v2 moved to amount.currency
        "items": [                               # v2 renamed "line_items"
            {"name": i["description"], "price": i["unit_price"]}
            for i in order["line_items"]
        ],
    }
```

**Migration plan for 200+ integrators:**

```
Month 0:  Ship v2 alongside v1 (both fully functional)
          Email all integrators: migration guide + changelog
          Add deprecation header to v1 responses:
            Sunset: 2027-03-01
            Deprecation: true
            Link: <https://docs.example.com/migration>; rel="successor-version"

Month 1:  Follow up with integrators still on v1
Month 3:  Second notice, offer migration support
Month 6:  Start returning warning headers on v1
Month 9:  Rate-limit v1 (slower, not broken)
Month 11: Final 30-day sunset notice
Month 12: Shut down v1, return 410 Gone with migration link
```

**The deprecation header (add to all v1 responses):**

```python
from fastapi import Response

@v1.middleware("http")
async def add_deprecation_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["Deprecation"] = "true"
    response.headers["Sunset"] = "Sat, 01 Mar 2027 00:00:00 GMT"
    response.headers["Link"] = (
        '<https://api.example.com/api/v2>; rel="successor-version"'
    )
    return response
```

**Monitor migration progress:**

```python
# Track v1 vs v2 usage per integrator
@v1.middleware("http")
async def track_v1_usage(request: Request, call_next):
    api_key = request.headers.get("X-API-Key", "unknown")
    await metrics.increment("api.v1.requests", tags={"client": api_key})
    return await call_next(request)
```

**Key principle: v1 is a translation layer, not a code fork.** All business logic lives in v2. v1 handlers just transform request/response shapes. This means zero code duplication and v1 automatically gets bug fixes.'''
    ),
]
