"""Phase 4F: Self-Improvement — Quality Assurance (Part 10)

Quality checklists for performance tuning advice — ensuring performance
recommendations are measured, targeted, and don't sacrifice maintainability.
"""

PAIRS = [
    (
        "thinking/auto-qa-performance-diagnosis-quality",
        r'''What quality checks should I apply before giving performance tuning advice to ensure I'm solving the actual bottleneck and not optimizing the wrong thing?''',
        r'''<think>
The most common performance advice failure is optimizing something that isn't the bottleneck. Developers often have intuitions about what's slow that are completely wrong. Without measurement, performance tuning is guesswork.

**Knuth's law:** "Premature optimization is the root of all evil."
**The corollary:** Optimization without profiling is premature by definition.

**Quality dimensions:**
1. Is the performance problem measured (not assumed)?
2. Is the bottleneck identified (not guessed)?
3. Is the optimization targeted at the bottleneck?
4. Is the improvement measured after the change?
5. Does the optimization sacrifice readability or maintainability?
</think>

**Performance Tuning Advice Quality Checklist**

**Before giving ANY performance advice:**

**Step 1: Verify the problem exists**
```
□ IS THERE A MEASURED PERFORMANCE PROBLEM?

  "This seems slow" → NOT sufficient. Measure first.
  "This endpoint takes 2.3 seconds (p95)" → Measured. Good.

  Questions to ask:
  - What's the current performance? (exact numbers)
  - What's the target performance? (what's acceptable)
  - How was it measured? (tool, conditions, sample size)
  - Is it consistently slow or intermittent?

  If there are no measurements, the first advice is:
  "Measure first. Use [profiling tool] to identify the bottleneck."

□ IS THE PERFORMANCE ACTUALLY A PROBLEM?
  An API that takes 100ms is usually fine.
  An API that takes 5 seconds for a user-facing request is not.
  A batch job that takes 10 minutes at 3 AM is probably fine.

  Context determines whether performance is a problem:
  - User-facing request: < 200ms target
  - Background job: depends on SLA
  - Database query: < 100ms for indexed, < 1s for analytics
  - Page load: < 3 seconds for initial load

  Don't optimize something that's already fast enough.
```

**Step 2: Identify the bottleneck**
```
□ HAS THE BOTTLENECK BEEN PROFILED?

  Tools by platform:
  - Python: cProfile, py-spy, line_profiler
  - JavaScript: Chrome DevTools Performance tab, clinic.js
  - Java: JFR (Java Flight Recorder), async-profiler
  - Database: EXPLAIN ANALYZE, pg_stat_statements
  - Network: Chrome DevTools Network tab
  - System: htop, iostat, vmstat

  Common bottleneck locations (in order of frequency):
  1. Database queries (80% of web app performance issues)
  2. Network calls (API calls, external services)
  3. I/O operations (file system, disk)
  4. Memory allocation (GC pressure, large object creation)
  5. CPU computation (algorithms, serialization)

  Most developers guess CPU when the real problem is I/O.

□ IS THE OPTIMIZATION TARGETED AT THE BOTTLENECK?

  WRONG: "Let's switch to a faster JSON serializer"
  (JSON serialization is rarely the bottleneck)

  RIGHT: "EXPLAIN shows a sequential scan on a 5M row table.
  Adding an index on user_id would change this to an index
  scan, reducing query time from 800ms to 2ms."

  If your optimization isn't targeting the measured bottleneck,
  it won't help.
```

**Step 3: Validate the proposed optimization**
```
□ WILL THIS ACTUALLY HELP?

  Amdahl's Law: Optimizing something that takes 5% of total
  time can only improve total performance by 5% at most.

  If your endpoint takes 1000ms:
    - Database: 800ms (80%)
    - Business logic: 150ms (15%)
    - JSON serialization: 50ms (5%)

  Optimizing JSON → maximum 5% improvement → still 950ms
  Optimizing database → could get 80%+ improvement → 200ms

  Always optimize the biggest contributor first.

□ IS THERE A SIMPLER SOLUTION?

  Before complex optimization, check:
  - Is there a missing index? (most common database fix)
  - Is there an N+1 query? (most common ORM fix)
  - Is the same data being fetched multiple times? (caching)
  - Is the response too large? (pagination, field selection)
  - Is there unnecessary computation? (memoization)

  90% of performance issues are fixed by indexes, caching,
  or reducing unnecessary work — not by algorithmic optimization.

□ DOES IT SACRIFICE MAINTAINABILITY?

  Performance optimizations often make code harder to read:
  - Inlining functions (faster but duplicated logic)
  - Manual memory management (faster but error-prone)
  - Complex caching (faster but stale data bugs)
  - Denormalization (faster reads but data consistency issues)

  Ask: "Is the performance gain worth the maintainability cost?"
  A 10% speedup that makes the code 3x harder to maintain
  is usually not worth it.
```

**Step 4: Measure the improvement**
```
□ AFTER APPLYING THE OPTIMIZATION, WAS IT MEASURED?

  Before: Endpoint p95 = 2300ms
  After: Endpoint p95 = 180ms
  Improvement: 92% — justified.

  Before: Endpoint p95 = 200ms
  After: Endpoint p95 = 195ms
  Improvement: 2.5% — was this worth the complexity added?

  ALWAYS measure after optimization. Without measurement,
  you don't know if it helped, hurt, or did nothing.

□ DID IT INTRODUCE REGRESSIONS?
  Performance optimization can cause:
  - Correctness bugs (caching returns stale data)
  - Memory issues (trading CPU for memory)
  - Increased complexity (harder to debug)
  - Different failure modes (cache stampede, connection pool exhaustion)

  Run full test suite after optimization.
  Monitor for 24 hours in production.
```

**Common performance advice anti-patterns:**

| Anti-pattern | Why it's wrong |
|-------------|---------------|
| "Use a faster language" | The language is rarely the bottleneck |
| "Cache everything" | Caching introduces stale data and invalidation complexity |
| "Use async everywhere" | Async helps I/O-bound work, not CPU-bound |
| "Optimize the algorithm" | Usually the bottleneck is I/O, not algorithms |
| "Reduce function calls" | Modern compilers inline function calls |
| "Use a NoSQL database" | Most relational performance issues are missing indexes |

**The meta-principle:** Performance tuning follows the scientific method: measure, hypothesize, change ONE thing, measure again. Optimization without measurement is superstition. The fastest code in the world doesn't matter if it's optimizing something that takes 1% of total time. Always measure, always target the bottleneck, and always verify the improvement.'''
    ),
    (
        "thinking/auto-qa-performance-caching-advice",
        r'''What quality checks should I apply when recommending caching as a performance solution? Caching seems simple but I've seen it cause as many problems as it solves.''',
        r'''<think>
Caching is the most commonly recommended performance optimization, but it introduces significant complexity:
1. Cache invalidation (the hardest problem in CS)
2. Stale data (serving old data to users)
3. Cache stampede (all instances miss cache simultaneously)
4. Memory pressure (cache growing unboundedly)
5. Debugging difficulty (behavior differs from uncached path)

The key insight: caching trades consistency for speed. This trade-off must be explicitly evaluated.
</think>

**Caching Advice Quality Checklist**

**Before recommending caching:**

**Step 1: Is caching the right solution?**
```
□ IS THE DATA READ-HEAVY?
  Caching helps when: reads >> writes
  Caching hurts when: writes >= reads (constant invalidation)

  Good candidates:
  - Configuration data (reads: 1000/sec, writes: 1/day)
  - User profile data (reads: 100/sec per user, writes: 1/week)
  - Product catalog (reads: 10000/sec, writes: 10/day)

  Bad candidates:
  - Real-time counters (writes every second)
  - Chat messages (writes = reads)
  - Stock prices (stale data = wrong decisions)

□ IS STALE DATA ACCEPTABLE?
  "Is it OK if users see data that's [TTL] seconds old?"

  Acceptable staleness:
  - Product listings: 5-minute delay → probably fine
  - User dashboard: 30-second delay → probably fine
  - Account balance: 0 delay required → don't cache naively
  - Inventory count: Seconds matter for overselling → careful

  If the answer is "no staleness allowed" → caching is
  the wrong tool (or needs cache-aside with invalidation).

□ IS THE COMPUTATION EXPENSIVE ENOUGH TO JUSTIFY CACHING?
  Caching a 2ms query? The cache lookup itself takes 1ms.
  Net benefit: 1ms. Probably not worth the complexity.

  Caching a 500ms query? Cache lookup is 1ms.
  Net benefit: 499ms. Worth it.

  Rule of thumb: Cache things that take > 50ms to compute.
```

**Step 2: Cache strategy selection**
```
□ WHICH CACHING PATTERN?

  Cache-aside (most common):
    1. Check cache. Hit → return cached value.
    2. Miss → fetch from source, store in cache, return.
    Pros: Simple, app controls caching logic.
    Cons: First request always slow (cold cache).

  Write-through:
    1. Write to cache AND source simultaneously.
    2. Reads always hit cache.
    Pros: Cache always current.
    Cons: Write latency increases.

  Write-behind:
    1. Write to cache only. Cache writes to source asynchronously.
    Pros: Very fast writes.
    Cons: Data loss risk if cache crashes before writing to source.

  For most web apps: Cache-aside with TTL is the right choice.
  Only recommend write-through/behind for specific use cases.

□ WHERE TO CACHE?

  In-process (e.g., Python dict, functools.lru_cache):
    Pros: Fastest (no network hop), simplest
    Cons: Not shared between instances, memory per instance
    Use when: Single instance, or per-instance caching is OK

  Distributed (e.g., Redis, Memcached):
    Pros: Shared across instances, survives restarts
    Cons: Network hop (~1ms), operational overhead
    Use when: Multiple app instances need the same cache

  CDN (e.g., Cloudflare, CloudFront):
    Pros: Geographic distribution, offloads server
    Cons: Harder invalidation, TTL-based only
    Use when: Static or semi-static content
```

**Step 3: TTL and invalidation**
```
□ IS THE TTL APPROPRIATE?

  Too short (TTL=10s):
    Cache provides little benefit. Almost every request is a miss.
    → Only for data that changes very frequently and brief
       staleness is still valuable (reducing DB load).

  Too long (TTL=24h):
    Users may see very stale data. Changes take a day to propagate.
    → Only for truly static data (country lists, config values).

  Just right (TTL=5min):
    Most requests hit cache. Data is at most 5 minutes stale.
    → Good for frequently-read, infrequently-changed data.

  Guidelines:
    Configuration data: TTL = 5-15 minutes
    User profile: TTL = 1-5 minutes
    API responses: TTL = 30 seconds to 5 minutes
    Session data: TTL = session duration (30 minutes)

□ IS INVALIDATION NEEDED?

  TTL-only (simplest):
    Data is stale until TTL expires. No active invalidation.
    Works when: Staleness of [TTL] is acceptable.

  Active invalidation (more complex):
    When data changes, explicitly delete/update the cache.
    Works when: Staleness is not acceptable.
    Risk: Forgetting to invalidate → stale data bugs.

  If using active invalidation:
  □ Is EVERY write path covered? (Including admin panels,
    migrations, direct DB queries, background jobs)
  □ What happens if invalidation fails? (Cache stays stale)
  □ Is there a TTL as a safety net? (Even with invalidation,
    set a max TTL so stale data eventually expires)
```

**Step 4: Failure modes**
```
□ CACHE STAMPEDE PREVENTION:
  When cache expires, ALL requests hit the source simultaneously.
  1000 requests/sec → 1000 simultaneous DB queries → DB overload.

  Prevention:
  - Lock: Only one request refreshes cache, others wait
  - Probabilistic early expiration: Random early refresh
  - Background refresh: Refresh cache before it expires

□ CACHE FAILURE HANDLING:
  What happens if Redis is down?
  BAD: Application crashes
  GOOD: Falls back to source (DB), slower but functional

  try:
      result = cache.get(key)
  except CacheError:
      result = None  # treat as cache miss, continue
  if result is None:
      result = db.query(...)

□ MEMORY MANAGEMENT:
  Caches must have a maximum size or eviction policy.
  Otherwise, they grow until they OOM.

  Redis: Set maxmemory and maxmemory-policy
  In-process: Set maxsize on LRU cache
  Monitor: Track cache memory usage and hit rates
```

**The meta-principle:** Caching is not a free performance improvement — it's a trade-off between speed and consistency. Before recommending caching, verify that the data is read-heavy, staleness is acceptable, and the computation being cached is expensive enough to justify the complexity. Then choose the simplest caching strategy that meets the requirements. Every layer of caching complexity you add is a potential source of bugs.'''
    ),
    (
        "thinking/auto-qa-performance-database-optimization",
        r'''What quality checks should I apply when advising on database performance optimization specifically? Database issues seem to be the root cause of most performance problems.''',
        r'''<think>
Database performance optimization is the highest-impact performance tuning because databases are the bottleneck in 80%+ of web applications. But bad database optimization advice can make things worse (adding wrong indexes, denormalizing prematurely, etc.).

**The hierarchy of database optimization (most to least impactful):**
1. Query design (don't fetch what you don't need)
2. Indexing (make the query planner efficient)
3. Schema design (normalize/denormalize appropriately)
4. Configuration (memory, connections, workers)
5. Hardware (CPU, RAM, SSD)

Most developers jump to hardware when they should be looking at queries and indexes.
</think>

**Database Performance Optimization Quality Checklist**

**Before advising on database performance:**

**Step 1: Identify the slow queries**
```
□ HAVE SLOW QUERIES BEEN IDENTIFIED?

  Don't guess. Use database monitoring:

  PostgreSQL:
    - pg_stat_statements: Shows query statistics
    - log_min_duration_statement = 100  (log queries > 100ms)
    - auto_explain: Logs execution plans for slow queries

  MySQL:
    - slow_query_log: Enable slow query logging
    - long_query_time = 0.1  (log queries > 100ms)
    - performance_schema

  Application-level:
    - Django: django-debug-toolbar shows all queries
    - SQLAlchemy: echo=True logs all queries
    - Rails: bullet gem detects N+1 queries

  Focus on:
    - Queries that run most frequently
    - Queries that take the longest per execution
    - Queries that use the most total time (frequency x duration)

□ HAVE EXECUTION PLANS BEEN EXAMINED?

  EXPLAIN ANALYZE is the #1 diagnostic tool.

  What to look for in EXPLAIN output:
  - Seq Scan on large tables → needs an index
  - Nested Loop with high row count → consider Hash Join
  - Sort → consider adding an index to avoid sort
  - Actual rows >> Estimated rows → statistics need updating
    (run ANALYZE on the table)
```

**Step 2: Common fixes (in order of impact)**
```
□ FIX N+1 QUERIES FIRST

  The #1 web application database performance issue.

  Detection:
  - Same query executed 100+ times in one request
  - Query inside a loop that iterates over results

  Fix:
  - Use JOINs: fetch related data in one query
  - Use WHERE IN: batch lookup instead of one-at-a-time
  - Use ORM eager loading:
    Django: select_related(), prefetch_related()
    SQLAlchemy: joinedload(), selectinload()
    Rails: includes(), eager_load()

  Impact: Often 10-100x improvement.

□ ADD MISSING INDEXES

  Check every column used in:
  - WHERE clauses → index if queried frequently
  - JOIN conditions → index on foreign key columns
  - ORDER BY → index to avoid sort operation

  Composite indexes:
    Query: WHERE user_id = X AND status = 'active' ORDER BY created_at
    Index: CREATE INDEX idx ON orders(user_id, status, created_at)
    Column order in the index matters! Match the query pattern.

  Partial indexes (PostgreSQL):
    If 95% of queries filter on status = 'active':
    CREATE INDEX idx ON orders(user_id) WHERE status = 'active'
    → Smaller index, faster lookups, less write overhead.

□ REDUCE DATA TRANSFERRED

  SELECT * fetches all columns — often wasteful.
  Wide tables (20+ columns): SELECT only what you need.

  COUNT(*) on large tables is slow:
  - For exact count: maintain a counter table
  - For approximate count: pg_class.reltuples (PostgreSQL)

  Pagination:
  - OFFSET is O(n) — gets slower with larger offsets
  - Use cursor-based pagination for large datasets:
    WHERE id > last_seen_id ORDER BY id LIMIT 20

□ OPTIMIZE QUERY PATTERNS

  Avoid functions on indexed columns:
    BAD:  WHERE LOWER(email) = 'user@example.com'
          (can't use index on email)
    GOOD: WHERE email = 'user@example.com'
          (uses index, store lowercase in application)
    OR:   CREATE INDEX idx ON users(LOWER(email))
          (expression index)

  Avoid wildcard prefix:
    BAD:  WHERE name LIKE '%smith'  (full table scan)
    GOOD: WHERE name LIKE 'smith%'  (can use index)
    For full-text: Use full-text search (tsvector + GIN index)
```

**Step 3: Configuration checks**
```
□ IS THE DATABASE CONFIGURED FOR THE WORKLOAD?

  PostgreSQL key settings:
  - shared_buffers: 25% of available RAM
  - effective_cache_size: 75% of available RAM
  - work_mem: 4-64MB (per query, for sorts and joins)
  - maintenance_work_mem: 256MB-1GB (for VACUUM, CREATE INDEX)
  - random_page_cost: 1.1 for SSD (default 4.0 is for spinning disk!)

  The random_page_cost setting is often wrong:
  If you're on SSD and this is still 4.0, the planner
  will avoid index scans that would actually be fast.

□ IS CONNECTION POOLING IN PLACE?
  See the connection management checklist.
  Without pooling, the database spends more time managing
  connections than executing queries.

□ IS VACUUM RUNNING?
  PostgreSQL needs VACUUM to reclaim dead rows.
  If autovacuum is disabled or falling behind:
  - Tables bloat (larger than needed)
  - Indexes bloat
  - Transaction ID wraparound risk
  Check: pg_stat_user_tables.n_dead_tup
  If dead tuples > 10% of live tuples → VACUUM is behind.
```

**Step 4: Advanced optimizations (only if basics are covered)**
```
□ MATERIALIZED VIEWS:
  For complex queries that aggregate data:
  CREATE MATERIALIZED VIEW monthly_stats AS
    SELECT ... expensive query ...;
  REFRESH MATERIALIZED VIEW CONCURRENTLY monthly_stats;

  Use when: Same complex query runs frequently, data doesn't
  change between refreshes.

□ READ REPLICAS:
  Route read-heavy queries to a replica:
  - Writes → primary
  - Reads → replica
  Trade-off: Replication lag means reads might be slightly stale.

□ PARTITIONING:
  For tables > 100M rows:
  Partition by date (most common) or by tenant.
  Queries that include the partition key can skip entire partitions.

  Only recommend when simpler optimizations have been exhausted.
```

**The meta-principle:** Database performance optimization follows the 80/20 rule ruthlessly: 80% of performance problems are solved by fixing N+1 queries, adding missing indexes, and selecting only needed columns. Start with these before considering anything more complex. Use EXPLAIN ANALYZE to verify that your optimization actually changed the query plan. And always measure before and after — optimization without measurement is just hope.'''
    ),
    (
        "thinking/auto-qa-performance-frontend-advice",
        r'''What quality checks should I apply when advising on frontend performance? The metrics and optimization strategies seem different from backend performance.''',
        r'''<think>
Frontend performance is fundamentally different from backend because:
1. The user directly experiences the performance (perceived speed matters)
2. The environment is uncontrolled (different devices, networks, browsers)
3. The metrics are different (LCP, FID, CLS vs response time, throughput)
4. The bottleneck is often the network, not computation
5. The user's device capability varies enormously

**Frontend performance quality dimensions:**
- Core Web Vitals (Google's user experience metrics)
- Bundle size (how much JavaScript is sent to the browser)
- Network requests (number and size)
- Rendering performance (layout, paint, compositing)
- Perceived performance (what the user feels)
</think>

**Frontend Performance Advice Quality Checklist**

**Before advising on frontend performance:**

**Step 1: Measure with the right metrics**
```
□ ARE CORE WEB VITALS MEASURED?

  LCP (Largest Contentful Paint): < 2.5 seconds
    "How long until the main content is visible?"
    Bad LCP causes: Large images, slow server, render-blocking resources

  INP (Interaction to Next Paint): < 200ms
    "How long after clicking before the UI responds?"
    Bad INP causes: Heavy JavaScript, long tasks, layout thrashing

  CLS (Cumulative Layout Shift): < 0.1
    "How much does content jump around while loading?"
    Bad CLS causes: Images without dimensions, dynamic content injection,
    web fonts causing text reflow

  Measurement tools:
  - Chrome DevTools Lighthouse tab
  - PageSpeed Insights (lab + field data)
  - Chrome User Experience Report (real user data)
  - Web Vitals library (in-app measurement)

□ ARE MEASUREMENTS FROM REAL USERS?
  Lab testing (Lighthouse) != real-world performance.
  A page that scores 100 on Lighthouse on a dev machine may
  score 40 on a budget Android phone on 3G.

  Use Real User Monitoring (RUM) to measure actual user experience.
  Tools: Google Analytics, Datadog, New Relic, web-vitals library.
```

**Step 2: Common optimizations (in order of impact)**
```
□ REDUCE JAVASCRIPT BUNDLE SIZE

  The #1 frontend performance issue:
  Large JS bundles → long download → long parse → slow TTI

  Diagnosis:
    npm run build -- --stats
    Use webpack-bundle-analyzer or source-map-explorer
    to visualize what's in your bundle.

  Common fixes:
  - Code splitting: Load code for each route separately
  - Tree shaking: Remove unused exports
  - Dynamic imports: import() for rarely-used features
  - Replace heavy libraries:
    moment.js (300KB) → date-fns (tree-shakeable, ~15KB used)
    lodash (70KB) → lodash-es (tree-shakeable) or native JS

  Target: < 200KB JavaScript for initial page load (gzipped)

□ OPTIMIZE IMAGES

  Often the largest page weight contributor.

  Checklist:
  - Format: WebP or AVIF instead of JPEG/PNG (30-50% smaller)
  - Responsive: srcset with multiple sizes for different screens
  - Lazy loading: loading="lazy" for below-the-fold images
  - Dimensions: Always set width/height to prevent CLS
  - CDN: Serve images from a CDN near the user

□ MINIMIZE NETWORK REQUESTS

  Each HTTP request has overhead (DNS, TCP, TLS, TTFB).

  Fixes:
  - Bundle CSS/JS (but use code splitting for large apps)
  - Inline critical CSS (above-the-fold styles in <head>)
  - Preload key resources: <link rel="preload">
  - Prefetch next page: <link rel="prefetch">
  - HTTP/2: Multiplexing reduces request overhead

□ AVOID RENDER-BLOCKING RESOURCES

  CSS in <head> blocks rendering until downloaded and parsed.
  JS without defer/async blocks HTML parsing.

  Fixes:
  - CSS: Inline critical CSS, async load the rest
  - JS: Use defer for all scripts (loads in parallel, executes after HTML)
  - Fonts: font-display: swap (show fallback font while loading)
```

**Step 3: Validate the optimization**
```
□ DOES THE OPTIMIZATION TARGET THE ACTUAL BOTTLENECK?

  If LCP is bad:
  → Check: What is the "largest contentful paint" element?
    Usually a hero image or heading.
  → Optimize THAT specific element, not random things.

  If INP is bad:
  → Check: Which interaction is slow?
    Use Chrome DevTools Performance tab to profile clicks.
  → Optimize THAT specific handler, not all JavaScript.

  If CLS is bad:
  → Check: What's shifting?
    Use Layout Shift debugger in Chrome DevTools.
  → Fix THAT specific shift, not all layout.

□ HAS THE OPTIMIZATION BEEN MEASURED?

  Before: LCP = 4.2s, INP = 350ms, CLS = 0.25
  After: LCP = 2.1s, INP = 120ms, CLS = 0.05
  → Measurable improvement on the metrics that matter.

  Before: "The page feels slow"
  After: "The page feels faster"
  → Not measured. Maybe it helped, maybe placebo.

□ WAS IT TESTED ON SLOW DEVICES?

  Optimize for the slowest device your users actually use.
  Use Chrome DevTools throttling:
  - CPU: 4x slowdown
  - Network: Slow 3G
  - Device: Mid-range mobile

  If your optimization only helps on fast devices,
  it's not helping the users who need it most.
```

**Step 4: Anti-patterns to avoid**
```
□ NOT OVER-OPTIMIZING:
  A page that loads in 1.2s vs 1.0s → users won't notice.
  Don't sacrifice code readability for marginal gains.

□ NOT USING TOO MANY THIRD-PARTY SCRIPTS:
  Analytics, chat widgets, social buttons, A/B testing —
  each adds 50-200KB. Audit and remove unused ones.

  "We need 6 analytics tools" → Really? Consolidate.

□ NOT PREMATURE LAZY LOADING:
  Lazy loading everything makes above-the-fold content slower
  (adds loading indicator overhead). Only lazy load below-the-fold.

□ NOT IGNORING PERCEIVED PERFORMANCE:
  Sometimes UX tricks are better than actual optimization:
  - Skeleton screens (show layout immediately)
  - Optimistic updates (show success before server confirms)
  - Progressive loading (show content as it arrives)
  The user FEELS faster even if total time is the same.
```

**The meta-principle:** Frontend performance is about user experience, not about raw speed. A page that shows meaningful content in 1 second and finishes loading in 3 seconds feels faster than a page that shows nothing for 2 seconds then loads everything at once. Optimize for the metrics users actually feel (LCP, INP, CLS), measure on real devices with real networks, and always verify that your optimization moved the needle on the right metric.'''
    ),
    (
        "thinking/auto-qa-performance-scaling-advice",
        r'''What quality checks should I apply when advising on scaling a system? Scaling advice that's wrong for the situation can waste enormous amounts of money and engineering time.''',
        r'''<think>
Scaling advice is high-stakes because:
1. Over-scaling wastes money (running 50 servers when 3 would do)
2. Under-scaling causes outages (system crashes under load)
3. Wrong scaling strategy creates complexity (microservices when a monolith suffices)
4. Premature scaling wastes engineering time (building for 1M users when you have 1K)

**The fundamental question:** "Is scaling the right solution, or should we optimize first?"

Most systems don't need to scale — they need to be optimized. A well-optimized single server can handle far more load than most startups will ever see.
</think>

**Scaling Advice Quality Checklist**

**Before advising on scaling:**

**Step 1: Is scaling actually needed?**
```
□ HAS THE CURRENT SYSTEM BEEN OPTIMIZED?

  Before scaling OUT (more servers), scale UP (optimize):

  Common optimizations that avoid scaling:
  1. Add database indexes (free performance, no infrastructure)
  2. Add caching (Redis for frequently-read data)
  3. Fix N+1 queries (can give 10-100x improvement)
  4. Use connection pooling (reduce database load)
  5. Optimize slow queries (EXPLAIN ANALYZE)
  6. Enable compression (gzip/brotli for HTTP responses)
  7. Use a CDN (offload static assets)

  These optimizations together can often handle 10-100x
  the traffic of an unoptimized system, WITHOUT adding servers.

  "We need to scale" often really means "we need to optimize."

□ WHAT'S THE ACTUAL LOAD?

  Current: 100 requests/second
  Server can handle: 1000 requests/second (after optimization)
  Growth rate: 10% per month
  → You have 24 months before you need to scale.

  Don't scale for hypothetical traffic. Scale when you have
  evidence of actual growth approaching capacity.

□ WHAT'S THE BOTTLENECK?

  "The system is slow" → What specifically is slow?
  - Database → scale the database (read replicas, partitioning)
  - Application → scale the application (more instances)
  - Network → use a CDN, optimize payloads
  - Memory → add RAM or reduce memory usage

  Scaling the application servers when the database is the
  bottleneck just adds more load to the database → makes it worse.
```

**Step 2: Scaling strategy selection**
```
□ VERTICAL FIRST, HORIZONTAL SECOND

  Vertical scaling (bigger machine):
    Pros: No code changes, simple operations
    Cons: Has limits, single point of failure
    Best for: Database servers, small-medium loads

  Horizontal scaling (more machines):
    Pros: Virtually unlimited, redundancy
    Cons: Requires stateless design, load balancing, complexity
    Best for: Web servers, microservices, very high loads

  For most systems:
  1. Start with vertical scaling (use a bigger server)
  2. Add a read replica for the database
  3. Add a load balancer and second app server
  4. Only then consider more complex scaling

□ IS THE APPLICATION STATELESS?

  Before adding more app servers, the application must be stateless:
  - Sessions stored in Redis/database (not in-memory)
  - No local file storage (use S3 or equivalent)
  - No in-process cache that must be consistent across instances
    (use Redis for shared cache)

  If the app stores state in memory → you CANNOT scale horizontally
  without fixing this first.

□ IS THE DATABASE SCALING STRATEGY APPROPRIATE?

  Read-heavy workload:
  → Read replicas (route reads to replicas, writes to primary)

  Write-heavy workload:
  → Partitioning/sharding (split data across databases)
  → This is complex. Avoid unless absolutely necessary.

  Both:
  → CQRS (separate read and write databases)
  → Very complex. Only for high-scale systems.

  For most applications:
  "PostgreSQL with read replicas handles more load than
   you'll see for years. Don't shard until you must."
```

**Step 3: Cost and complexity check**
```
□ IS THE COST PROPORTIONAL TO THE BENEFIT?

  3 servers handling 1000 rps: $300/month
  Kubernetes cluster for "scalability": $2000/month
  → Is the extra complexity and cost justified?

  For < 50 servers: Simple load balancer + auto-scaling group
  For 50-500 servers: Kubernetes may be justified
  For > 500 servers: Kubernetes or equivalent is expected

□ CAN THE TEAM OPERATE THIS?

  A scaling solution the team can't operate is a liability.

  Team of 3 devs:
  → Docker Compose or simple cloud deployment
  → NOT Kubernetes (operational overhead too high)

  Team of 20+ devs with dedicated ops:
  → Kubernetes is viable

  The scaling solution must match operational maturity.

□ IS THIS PREMATURE?

  "We might need to handle 1M users someday"
  → Build for 10K users now. Refactor when approaching 100K.

  Instagram ran on a single Django server for months.
  Scaling too early wastes time on problems you don't have.
```

**Step 4: Monitoring and capacity planning**
```
□ IS THERE MONITORING TO DETECT WHEN SCALING IS NEEDED?

  Track:
  - CPU utilization (> 70% sustained → consider scaling)
  - Memory utilization (> 80% → risk of OOM)
  - Request latency p95 (increasing trend → approaching capacity)
  - Error rate (increasing → possibly overloaded)
  - Database connections (approaching max → pool or scale DB)

  Set alerts BEFORE hitting capacity:
  - Warning at 70% CPU
  - Critical at 85% CPU
  - This gives you time to react before an outage.

□ IS AUTO-SCALING CONFIGURED?

  For cloud deployments:
  - Scale out when CPU > 70% for 5 minutes
  - Scale in when CPU < 30% for 15 minutes
  - Set minimum instances = 2 (for redundancy)
  - Set maximum instances (cost protection)

  Auto-scaling prevents both over-provisioning (wasting money)
  and under-provisioning (causing outages).
```

**The meta-principle:** The best scaling strategy is the simplest one that meets your actual (not hypothetical) needs. Optimize before scaling. Scale vertically before horizontally. Use managed services before building infrastructure. And never scale for traffic you don't have — solve today's problems today, and build just enough headroom for the next 6-12 months of growth. Premature scaling is one of the most expensive mistakes in software engineering.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
