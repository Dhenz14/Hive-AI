"""Phase 2F: Advanced Reasoning — Uncertainty Calibration (Part 7/8)"""

PAIRS = [
    (
        "thinking/uncertainty-serverless-vs-containers",
        "Should we move our API from ECS containers to AWS Lambda? Our API handles 50-200 requests per second with occasional spikes to 1000 rps. Average response time needs to be under 200ms.",
        r'''<think>
Serverless vs containers for this specific workload. Let me think carefully about the characteristics.

**Workload profile:**
- 50-200 rps baseline → moderate, steady traffic
- Spikes to 1000 rps → 5-20x burst
- 200ms latency requirement → cold starts are a concern

**Lambda analysis:**
Pros:
- Auto-scaling handles the 5-20x bursts perfectly — no capacity planning
- Pay per invocation — could be cheaper during low-traffic periods
- No server management, patching, etc.

Cons:
- Cold starts: typically 200-800ms for Node.js, 1-3s for Java/Python with heavy deps
  - At 50+ rps, containers stay warm, but during low periods or burst scaling, cold starts happen
  - 200ms latency requirement means cold starts would violate SLA
- At 200 rps sustained, Lambda cost adds up: 200 rps × 86,400 sec/day × $0.0000002 per request = ~$3.5/day just for invocations, plus duration charges
- Connection management: if the API talks to a database, Lambda's ephemeral nature makes connection pooling tricky (need RDS Proxy or similar)
- 15-minute execution limit — fine for APIs but limits background processing

**ECS analysis:**
At 200 rps sustained, a few containers handle this easily. Scaling to 1000 rps needs maybe 5x capacity — ECS auto-scaling handles this but with ~2-3 minute ramp-up time.

**Hybrid possibility:**
Keep ECS for baseline, use Lambda for overflow? Adds complexity.

**My confidence assessment:**
- 75% confidence: Stay with ECS containers. The steady baseline traffic (50-200 rps) and 200ms latency requirement favor containers. Cold starts are the killer.
- 15% confidence: Lambda could work IF they use provisioned concurrency for the baseline and have lightweight functions (Node.js, minimal deps)
- 10% confidence: Hybrid approach worth exploring but added complexity probably not justified

The workload doesn't match Lambda's sweet spot (bursty, low-frequency, tolerant of latency variation). It matches containers' sweet spot (sustained throughput, consistent latency).
</think>

Based on your workload characteristics, I'd recommend **staying with ECS containers** — confidence: **75%**.

## Analysis by Key Factor

### Cold Starts vs Your Latency Requirement

```
Your requirement: < 200ms average response time

Lambda cold start times (typical):
  Node.js (minimal):     200-500ms   ← barely meets SLA
  Node.js (with SDK):    400-800ms   ← violates SLA
  Python (with deps):    500-1500ms  ← violates SLA
  Java/Spring:           2000-5000ms ← way over

At 50+ rps, most invocations hit warm containers.
But during:
  - Scale-up events (spike to 1000 rps) → new cold starts
  - After quiet periods (night/weekends) → cold starts
  - Deployment updates → all instances cold start

Cold starts would cause P95/P99 latency spikes above 200ms.
```

### Cost Comparison (Rough Estimates)

```
ECS (Fargate):
  3 tasks × 0.5 vCPU × 1GB RAM running 24/7
  ≈ $90/month
  Scales to 15 tasks during spikes
  Average: ≈ $120-150/month

Lambda:
  200 rps average × 86,400 sec/day × 30 days = 518M requests/month
  Invocation cost: 518M × $0.20/1M = $103/month
  Duration (100ms avg, 256MB): 518M × 0.1s × $0.0000133 = $689/month
  Total: ≈ $790/month  ← 5-6x more expensive at sustained load

Lambda with provisioned concurrency:
  50 provisioned instances to avoid cold starts
  ≈ $550/month provisioned + invocation costs
  Total: ≈ $800+/month  ← even worse
```

### Where Lambda WOULD Make Sense (For Reference)

```
Good Lambda fit:              Your workload:
  0-10 rps average            50-200 rps average        ✗
  Tolerant of 500ms+ P99      Need < 200ms average      ✗
  Very bursty (0 to 1000)     Sustained with spikes     ✗
  Event-driven (S3, SQS)      Synchronous API           ✗
  Short-lived processing      Request-response API      ~
```

## Recommendation

```
STAY WITH ECS CONTAINERS (75% confidence)
  ✓ Consistent sub-200ms latency (no cold starts)
  ✓ 5-6x cheaper at your traffic volume
  ✓ Database connection pooling works naturally
  ✓ Handles sustained throughput well

CONSIDER IMPROVING ECS SCALING instead:
  - Use target tracking scaling on request count
  - Pre-warm capacity with scheduled scaling before known peaks
  - Use ECS Service Connect for service mesh benefits

WHEN I'D CHANGE MY MIND (→ Lambda):
  - If traffic drops to < 10 rps average (cost crossover point)
  - If latency requirement relaxes to < 500ms
  - If workload becomes event-driven rather than synchronous API
  - If team bandwidth for server management is truly zero
```

**The 25% uncertainty** comes from: I don't know your dependency weight (lighter functions = smaller cold starts), whether you're already using provisioned concurrency, or if there are operational costs I'm not seeing (on-call burden, patching time) that would shift the total cost of ownership.'''
    ),
    (
        "thinking/uncertainty-graphql-vs-rest-api",
        "We're building a new public API for our SaaS product. Should we go with GraphQL or REST? We have about 15 resource types and our clients are mostly web and mobile apps.",
        r'''<think>
GraphQL vs REST for a public SaaS API. This is a genuinely debatable choice — I need to think about what "public API" means here specifically.

**Key factors:**

1. **Public API** — this is the big one. Public APIs have external consumers you can't control.
   - REST: universally understood, every developer knows it, extensive tooling
   - GraphQL: growing adoption but many developers haven't used it, learning curve for consumers
   - For public APIs, REST is strongly favored due to simplicity for consumers

2. **15 resource types** — moderate complexity
   - REST: 15 resources = ~30-45 endpoints (CRUD + custom actions). Manageable.
   - GraphQL: shines when relationships between types are complex and clients need flexible queries

3. **Web and mobile clients** — different data needs
   - Mobile wants minimal data (bandwidth), web wants richer data
   - GraphQL's query flexibility helps here — clients ask for exactly what they need
   - REST can solve this with sparse fieldsets (`?fields=id,name,email`) or BFF pattern

4. **Versioning and evolution:**
   - REST: URL versioning (`/v2/users`) is well-understood
   - GraphQL: schema evolution with deprecation — arguably better but requires discipline

5. **Caching:**
   - REST: HTTP caching works out of the box (GET responses, CDN caching, ETags)
   - GraphQL: all queries are POST to single endpoint — HTTP caching doesn't work, need application-level caching

6. **Rate limiting:**
   - REST: easy — rate limit per endpoint
   - GraphQL: hard — one query can be cheap or expensive depending on nesting depth

7. **Documentation:**
   - REST: OpenAPI/Swagger is industry standard, excellent tooling
   - GraphQL: self-documenting schema is great, but playground tools are less mature for public consumption

**My assessment:**
- 60% confidence: REST is the better choice for a public API
- 30% confidence: GraphQL could work well, especially if client flexibility is paramount
- 10% confidence: Hybrid (REST for public, GraphQL for internal/first-party apps)

The "public" qualifier pushes me toward REST. If this were an internal API, I'd lean more toward GraphQL.

Actually, let me reconsider. Many successful public APIs use GraphQL (GitHub, Shopify, Yelp). The ecosystem has matured. But these companies also maintain REST APIs alongside GraphQL.

I'll stick with 60/30/10 but acknowledge this is a close call.
</think>

This is a genuinely close decision. My recommendation: **REST for the public API** — confidence: **60%**.

## Decision Matrix

```
Factor                  REST            GraphQL         Winner
─────────────────────────────────────────────────────────────
Consumer familiarity    Universal       Growing         REST
Learning curve          Low             Moderate        REST
Client data flexibility Fixed responses Exact queries   GraphQL
Mobile optimization     Needs work      Built-in        GraphQL
HTTP caching            Native          Manual          REST
Rate limiting           Simple          Complex         REST
Documentation           OpenAPI/Swagger Introspection   Tie
Versioning              URL versions    Deprecation     GraphQL
Tooling ecosystem       Mature          Maturing        REST
Over/under-fetching     Common issue    Solved          GraphQL
```

## Why REST Edges Ahead for *Public* APIs

```python
# REST: any developer can use it in 30 seconds
import requests
response = requests.get("https://api.yourapp.com/v1/users/42")
user = response.json()

# GraphQL: requires understanding queries, schemas, variables
import requests
query = """
  query GetUser($id: ID!) {
    user(id: $id) {
      id
      name
      email
      subscription { plan status }
    }
  }
"""
response = requests.post("https://api.yourapp.com/graphql",
    json={"query": query, "variables": {"id": "42"}})
user = response.json()["data"]["user"]
```

```
For YOUR public API consumers:
  - They didn't choose your tech stack — you're imposing it
  - Every extra concept = higher integration cost = fewer integrations
  - REST: "GET /users/42" is self-explanatory
  - GraphQL: "write a query in this schema language" is a learning curve
```

## When I'd Flip to GraphQL (the 30%)

```
GraphQL becomes the better choice if:
  ✓ Your clients have wildly different data needs
    (mobile needs 3 fields, web needs 30, admin needs 50)
  ✓ Relationships between resources are deeply nested
    (orders → items → products → reviews → users)
  ✓ Your clients are mostly first-party (your own web/mobile apps)
  ✓ You're willing to invest in query complexity analysis & rate limiting
  ✓ Your consumers are developers who already know GraphQL
```

## The Hybrid Approach (10% — But Worth Considering)

```
What GitHub and Shopify do:
  PUBLIC:   REST API (v3) — simple, cacheable, rate-limited
  POWER:   GraphQL API — flexible, for advanced integrations

  This lets you:
  - Offer simple REST for most consumers
  - Offer GraphQL for power users who need flexibility
  - Share the same backend resolvers/services

  Downside: maintaining two API surfaces
```

## Practical REST Recommendations

```python
# Solve the over-fetching problem without GraphQL:

# 1. Sparse fieldsets (like JSON:API)
GET /v1/users/42?fields=id,name,email
# Returns only requested fields — mobile gets small payload

# 2. Compound documents / includes
GET /v1/users/42?include=subscription,recent_orders
# Returns related resources in one request — reduces N+1 calls

# 3. Resource-specific endpoints for common patterns
GET /v1/users/42/dashboard
# Returns a pre-composed view optimized for the dashboard screen
```

## My Uncertainty Sources

```
Why I'm not more confident (only 60%):
  - I don't know how different your web vs mobile data needs are
    (if very different → GraphQL's flexibility matters more)
  - I don't know your consumers' technical sophistication
    (enterprise developers may prefer GraphQL's type safety)
  - I don't know the relationship complexity between your 15 types
    (deeply nested relationships → GraphQL shines)
  - GraphQL ecosystem is rapidly maturing — this advice may age poorly

What would increase my confidence:
  - "Our consumers are mostly non-technical integrators" → 90% REST
  - "Our consumers are sophisticated dev teams" → 50/50
  - "We only have our own web + mobile apps" → 70% GraphQL
```'''
    ),
    (
        "thinking/uncertainty-redis-vs-memcached",
        "We need a caching layer for our web app. Should we use Redis or Memcached? We're caching database query results and API responses. About 50GB of cacheable data, 100k reads/sec.",
        r'''<think>
Redis vs Memcached for caching. This is often presented as a close decision but with the details given, I can actually be fairly confident.

**Workload characteristics:**
- Database query results and API responses — key-value lookups, JSON blobs
- 50GB cacheable data — substantial, needs multiple nodes or large instances
- 100k reads/sec — high throughput but both Redis and Memcached handle this easily

**Redis advantages:**
- Data structures (hashes, sets, sorted sets, lists) — not needed here though, just caching
- Persistence (RDB/AOF) — for a cache, not critical (cache can be rebuilt)
- Replication — useful for read scaling and HA
- Lua scripting — overkill for simple caching
- Pub/sub — not relevant
- Cluster mode — handles sharding natively
- TTL per key — both support this
- Eviction policies — both support LRU

**Memcached advantages:**
- Multi-threaded — better utilization of multi-core machines
  - Redis is single-threaded per instance (though Redis 6+ has I/O threading)
- Simpler — less operational complexity
- Memory efficient for simple key-value — no overhead of Redis data structure metadata
- Proven at scale for this exact use case — Facebook/Meta runs it at massive scale
- Slab allocator — better memory allocation for uniform-size values

**For THIS workload specifically:**
- 50GB data: Memcached is slightly better at pure memory efficiency for large key-value datasets
- 100k reads/sec: Both handle this trivially. Redis single instance does 100k+ ops/sec. Memcached multi-threaded does even more per instance.
- Simple caching: No need for Redis's data structures
- Database query results: Serialized JSON/binary blobs — perfect for Memcached's simple model

BUT: Redis has won the market. Better ecosystem, more cloud support (ElastiCache supports both but Redis gets more features), better documentation, more developers know it, more client libraries.

**Confidence:**
- 65% Redis — it's the safer default choice. Better ecosystem, more features if you need them later, better HA/replication story, teams already know it
- 30% Memcached — technically slightly better fit for pure large-scale caching (multi-threaded, memory efficient), but the difference is marginal
- 5% Both / something else — maybe you want Redis for some caching + Memcached for bulk caching, or maybe a CDN handles the API response caching

This is a case where "you can't go wrong with either" is actually true, but I'll give a clear recommendation.
</think>

For pure caching of query results and API responses: **either works well, but go with Redis** — confidence: **65%**.

## Why This Is a Close Call

```
For YOUR specific use case (key-value caching):
  Both Redis and Memcached are excellent.
  The technical differences are marginal.
  The ecosystem/operational differences tip it toward Redis.
```

## Technical Comparison for Your Workload

```
                        Redis               Memcached
──────────────────────────────────────────────────────
100k reads/sec          ✓ Easy              ✓ Easy
                        (100k+ ops/sec      (200k+ ops/sec
                         per instance)       per instance, multi-threaded)

50GB data               ✓ Cluster mode      ✓ Consistent hashing
                        (shard across        (shard across
                         multiple nodes)      multiple nodes)

Memory efficiency       Good                Slightly better
(for simple K-V)        (~80 bytes overhead  (~60 bytes overhead
                         per key)             per key)

Threading model         Single-threaded*    Multi-threaded
                        (*I/O threads in 6+) (better multi-core use)

Data types needed       Strings only        Strings only
(for your use case)     (you won't use      (perfect match)
                         sets/hashes/etc)
```

## Why Redis Wins Despite Memcached's Technical Edge

```
1. ECOSYSTEM (biggest factor):
   - Redis: every cloud provider offers managed Redis
   - Memcached: supported but fewer managed options, less investment
   - Redis client libraries are better maintained across all languages

2. FUTURE FLEXIBILITY:
   - Today: simple key-value caching
   - Tomorrow: maybe you want rate limiting, session storage,
     leaderboards, pub/sub, job queues
   - Redis handles all of these. Memcached handles none.
   - Adding a feature to existing Redis is free; adding a new system is not.

3. HIGH AVAILABILITY:
   - Redis: built-in replication + Sentinel or Cluster mode
   - Memcached: no built-in replication — if a node dies, that cache is gone
   - For 50GB of cached data, losing a node means a thundering herd
     hitting your database

4. TEAM FAMILIARITY:
   - Most developers have used Redis; fewer have used Memcached
   - More Stack Overflow answers, tutorials, and operational knowledge
```

## When I'd Flip to Memcached (the 30%)

```
Choose Memcached if:
  ✓ You ONLY need simple caching and will NEVER need other features
  ✓ You want maximum memory efficiency for large datasets
  ✓ You need multi-threaded performance on fewer, larger machines
  ✓ Your team has Memcached operational expertise
  ✓ You're running at Meta-scale (trillions of requests/day)
    where Memcached's efficiency advantage compounds

At Meta/Facebook scale:
  - 1% memory efficiency = terabytes of RAM saved = millions of dollars
  - At your scale (50GB): 1% = 500MB = ~$5/month in cloud costs
  - The efficiency argument doesn't matter at your scale
```

## Practical Setup Recommendation

```
Redis Cluster for 50GB + 100k rps:

Option A: Managed (recommended)
  AWS ElastiCache / GCP Memorystore / Azure Cache
  - 3 shards × 2 replicas (6 nodes)
  - cache.r6g.xlarge (26GB RAM each)
  - Total: ~78GB capacity, 600k+ rps
  - Cost: ~$1,200/month

Option B: Self-hosted
  - 3 Redis instances (primary) + 3 replicas
  - 32GB RAM each, dedicated cache servers
  - Use Redis Cluster mode for automatic sharding

Key configuration:
  maxmemory-policy: allkeys-lru     # Evict least recently used
  maxmemory: 20gb                   # Per instance
  tcp-keepalive: 60
  timeout: 300
```

```python
# Cache pattern for database queries
import redis
import json
import hashlib

cache = redis.Redis(host='redis-cluster', port=6379, decode_responses=True)

def cached_query(query, params, ttl=300):
    # Create deterministic cache key from query + params
    key = f"dbcache:{hashlib.sha256(f'{query}:{params}'.encode()).hexdigest()[:16]}"

    cached = cache.get(key)
    if cached:
        return json.loads(cached)

    result = db.execute(query, params)
    cache.setex(key, ttl, json.dumps(result))
    return result
```

## Confidence Breakdown

```
65% Redis:     Safe default, better ecosystem, future flexibility
30% Memcached: Technically slightly better fit for pure caching workload
5%  Other:     CDN for API responses, application-level caching, or both

What would change my mind:
  - "We're at 500GB+ scale" → Memcached's efficiency matters more
  - "We already run Memcached" → stick with it, no reason to migrate
  - "We need pub/sub and rate limiting too" → 95% Redis
  - "We need maximum simplicity" → Redis (ironically simpler to operate now)
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
