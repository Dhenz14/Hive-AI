"""Phase 4F: Self-Improvement — Quality Assurance (Part 6)

Quality checklists for architecture recommendations — ensuring
architectural advice is appropriate, pragmatic, and context-aware.
"""

PAIRS = [
    (
        "thinking/auto-qa-architecture-context-check",
        r'''What quality checks should I apply before making any architecture recommendation to ensure it fits the user's actual context?''',
        r'''<think>
The most common failure in architecture advice is recommending a pattern without understanding the context. Microservices for a 2-person startup, Kubernetes for a side project, event sourcing for a CRUD app — all technically valid patterns applied to wrong contexts.

**Context factors that change the recommendation:**
1. Team size and skill level
2. Expected scale (now and in 6 months)
3. Operational maturity
4. Time constraints
5. Budget constraints
6. Existing infrastructure
7. Regulatory requirements
</think>

**Architecture Recommendation Quality Checklist**

**Before making ANY architecture recommendation:**

**Phase 1: Context Gathering (do I know enough?)**
```
□ TEAM SIZE: How many engineers will build and maintain this?
  1-3 → Monolith, simple deployment
  4-15 → Modular monolith, maybe 2-3 services
  15+ → Services make sense (team boundaries = service boundaries)

□ SCALE: What's the expected load?
  <100 users → Almost anything works. Choose simplest.
  100-10K users → Standard web stack is fine.
  10K-1M users → Need to think about caching, CDN, read replicas.
  1M+ → Need careful architecture, but START simpler and scale up.

□ TIMELINE: When does this need to be working?
  2 weeks → Use what you know. No time for new patterns.
  3 months → Can learn one new tool.
  6+ months → Can invest in architecture.

□ EXISTING INFRASTRUCTURE: What do they already have?
  Don't recommend Kubernetes if they're on Heroku and it's working.
  Don't recommend PostgreSQL if they have a production MySQL setup.

□ TEAM SKILLS: What does the team already know?
  Recommending Rust to a Python team adds months of learning.
  Recommending a familiar tool with known tradeoffs is often better.

□ BUDGET: What can they afford?
  Multi-region Kubernetes → Expensive
  Single server with good backups → Cheap and often sufficient
```

**Phase 2: Recommendation Quality**
```
□ SIMPLEST VIABLE: Is this the simplest architecture that works?
  If a simpler approach would work → recommend the simpler one.
  "You could use microservices, but a monolith with good module
   boundaries would be simpler and work fine for your scale."

□ TRADEOFFS STATED: Have I explained what you gain AND lose?
  Every architecture decision has tradeoffs:
  - Microservices: Flexibility vs. operational complexity
  - Event sourcing: Audit trail vs. query complexity
  - NoSQL: Write speed vs. query flexibility
  If I only state benefits, my recommendation is incomplete.

□ MIGRATION PATH: Can they evolve from this if needs change?
  Good architecture allows incremental change.
  "Start with a monolith. If module X needs to scale independently,
   extract it as a service later."

□ OPERATIONAL REQUIREMENTS: Can the team operate this?
  If they can't debug it, monitor it, and deploy it
  confidently → it's too complex for them.
```

**Phase 3: Anti-Pattern Check**
```
□ NOT RESUME-DRIVEN: Am I recommending this because it's
  the RIGHT choice, or because it's exciting/trendy?

□ NOT CARGO-CULTING: Am I recommending this because "Netflix uses it"?
  Netflix has 2000+ engineers. Most teams don't.

□ NOT PREMATURE: Am I solving a problem that exists today?
  "We might need to scale to 10M users" → Do you have 10K yet?
  Solve today's problems today. Solve tomorrow's problems tomorrow.

□ NOT ONE-SIZE-FITS-ALL: Am I using a template answer?
  If my answer would be the same regardless of context →
  I'm not accounting for context.
```

**The context-matching matrix:**
```
                 Small team    Medium team    Large team
                 (1-5)         (5-20)         (20+)
Simple app:      Monolith      Monolith       Modular monolith
Medium app:      Monolith      Modular mono   Few services
Complex app:     Modular mono  Few services   Microservices
```

**The meta-principle:** The best architecture is the simplest one that meets current requirements and allows evolution. Don't optimize for problems you don't have. Don't recommend complexity the team can't operate. Context determines correctness — there are no universally right architectures.'''
    ),
    (
        "thinking/auto-qa-architecture-database-choice",
        r'''What quality checks should I apply when recommending a database to someone? How do I avoid defaulting to my favorite database?''',
        r'''<think>
Database choice is one of the most common architecture questions and one of the most frequently answered poorly. Common mistakes:

1. Always recommending PostgreSQL because it's good at most things
2. Recommending NoSQL because "it scales better" (not always true)
3. Not considering the data model and access patterns
4. Ignoring operational burden (can the team run this database?)
5. Recommending multiple databases when one would suffice

**The right approach:** Understand the data model and access patterns FIRST, then match to the right database.
</think>

**Database Recommendation Quality Checklist**

**Before recommending any database:**

**Step 1: Understand the workload**
```
□ DATA MODEL: What does the data look like?
  - Relational (tables, joins) → SQL database
  - Document (nested, variable schema) → Document store
  - Graph (relationships between entities) → Graph database
  - Time-series (timestamped events) → Time-series database
  - Key-value (simple lookups) → Key-value store

□ ACCESS PATTERNS: How will data be read and written?
  - Complex queries with JOINs → SQL
  - Simple key lookups → Key-value (Redis, DynamoDB)
  - Full-text search → Elasticsearch (or PostgreSQL with extensions)
  - Aggregations over time → Time-series DB or columnar store

□ CONSISTENCY REQUIREMENTS: How important is data accuracy?
  - Financial data → Strong consistency (SQL with ACID)
  - Social media feeds → Eventual consistency is fine
  - Inventory tracking → Strong consistency for stock levels

□ SCALE: How much data and throughput?
  - <100GB, <1K writes/sec → Almost any database works
  - 100GB-1TB, moderate traffic → PostgreSQL, MySQL, MongoDB
  - >1TB or >10K writes/sec → Need careful selection
```

**Step 2: Avoid common biases**
```
□ NOT DEFAULTING: Am I considering alternatives to my default?
  My default might be PostgreSQL, but:
  - Redis is better for caching/sessions
  - DynamoDB is better for simple key-value at massive scale
  - TimescaleDB is better for time-series data
  - SQLite is better for embedded/edge applications

□ NOT FOLLOWING HYPE: Am I recommending this because it's trendy?
  MongoDB in 2015: "Use Mongo for everything!"
  Reality: Many teams migrated back to PostgreSQL.
  Lesson: Match the tool to the workload, not the hype.

□ NOT ADDING UNNECESSARY COMPLEXITY:
  "Use PostgreSQL for main data, Redis for caching,
   Elasticsearch for search, and Kafka for events"
  → Do they need 4 databases, or can PostgreSQL handle
     most of this with its built-in features?
```

**Step 3: Operational considerations**
```
□ CAN THE TEAM OPERATE IT?
  - Do they have experience with this database?
  - Can they handle backups, recovery, and upgrades?
  - Is there managed hosting available? (RDS, Atlas, etc.)

□ BACKUP AND RECOVERY:
  - How will they back up the data?
  - How long does recovery take?
  - Have they tested recovery?

□ SCALING PATH:
  - Read replicas for read-heavy workloads
  - Sharding for write-heavy workloads
  - When would they need to shard? (probably not soon)
```

**The database decision matrix:**
```
Workload                    → Recommendation
─────────────────────────     ──────────────────────
General web application     → PostgreSQL
Simple key-value cache      → Redis
Document-heavy, flexible    → MongoDB or PostgreSQL JSONB
Time-series / IoT           → TimescaleDB or InfluxDB
Full-text search            → Elasticsearch (or PG full-text)
Graph-heavy queries         → Neo4j or PostgreSQL with ltree
Massive scale, simple ops   → DynamoDB or Cassandra
Embedded / edge computing   → SQLite
Analytics / OLAP            → ClickHouse or DuckDB
```

**The "start with PostgreSQL" rule:**
```
When in doubt, PostgreSQL is a safe default because:
- JSONB for document-like data
- Full-text search built-in
- Time-series with TimescaleDB extension
- Graph queries with recursive CTEs
- ACID compliance
- Enormous community and tooling

Only recommend a specialized database when PostgreSQL
demonstrably can't handle the specific workload.
```

**The meta-principle:** The best database is the one your team can operate confidently and that matches your actual access patterns. A PostgreSQL database that the team knows well outperforms a theoretically superior database they can't manage. Match the tool to the workload AND the team.'''
    ),
    (
        "thinking/auto-qa-architecture-api-design",
        r'''What quality checks should I apply when reviewing or recommending API design decisions?''',
        r'''<think>
API design quality is critical because APIs are contracts — once published, they're hard to change without breaking clients. Quality checks need to ensure the API is:

1. Consistent (follows predictable patterns)
2. Complete (covers the use cases)
3. Minimal (doesn't expose unnecessary complexity)
4. Evolvable (can be extended without breaking changes)
5. Secure (authentication, authorization, input validation)
6. Well-documented (self-describing where possible)
</think>

**API Design Quality Checklist**

**Before approving or recommending any API design:**

**1. Naming and Consistency**
```
□ RESOURCE NAMING: Are resources named as nouns, not verbs?
  GOOD: /users, /orders, /products
  BAD:  /getUsers, /createOrder, /deleteProduct

□ CONSISTENT PLURALIZATION: Pick one and stick to it
  GOOD: /users, /orders, /products (all plural)
  BAD:  /user, /orders, /product (mixed)

□ CONSISTENT CASING: One convention throughout
  GOOD: snake_case everywhere (user_name, created_at)
  BAD:  Mixed (userName, created_at, OrderID)

□ HIERARCHICAL RESOURCES: Nested logically?
  GOOD: /users/123/orders (orders belonging to user 123)
  BAD:  /user-orders?user_id=123 (flat when hierarchy exists)
```

**2. HTTP Methods and Status Codes**
```
□ CORRECT METHODS:
  GET: Read (no side effects, cacheable)
  POST: Create
  PUT: Full update (replace entire resource)
  PATCH: Partial update (modify specific fields)
  DELETE: Remove

□ CORRECT STATUS CODES:
  200: Success (with body)
  201: Created (after POST)
  204: Success (no body, after DELETE)
  400: Bad request (client error, invalid input)
  401: Unauthorized (not authenticated)
  403: Forbidden (authenticated but not authorized)
  404: Not found
  409: Conflict (duplicate, version mismatch)
  422: Unprocessable entity (validation failed)
  500: Server error (never intentional)

□ NOT USING 200 FOR EVERYTHING:
  BAD: Always 200 with {"success": false, "error": "..."}
  GOOD: Appropriate status code with error body
```

**3. Security and Safety**
```
□ AUTHENTICATION: How are requests authenticated?
  API keys, OAuth2 tokens, JWTs — not in query strings.

□ AUTHORIZATION: Is access control per-resource?
  User A can't access User B's data via /users/B/orders.

□ INPUT VALIDATION: All inputs validated and sanitized?
  Types, ranges, lengths, formats.

□ RATE LIMITING: Protection against abuse?
  Return 429 Too Many Requests with Retry-After header.

□ PAGINATION: List endpoints are paginated?
  Never return unbounded lists.
  Include: page/offset, per_page/limit, total_count.
```

**4. Evolvability**
```
□ VERSIONING STRATEGY: How will the API evolve?
  URL: /v1/users, /v2/users
  Header: Accept: application/vnd.api+json;version=2
  Pick one and document it.

□ NO BREAKING CHANGES without version bump:
  Adding fields → OK (backward compatible)
  Removing fields → BREAKING
  Changing field type → BREAKING
  Changing endpoint URL → BREAKING

□ DEPRECATION PLAN: How are old versions retired?
  Announce → warn → deprecate → remove (with timeline).
```

**5. Developer Experience**
```
□ CONSISTENT ERROR FORMAT:
  {
    "error": {
      "code": "VALIDATION_ERROR",
      "message": "Email is required",
      "details": [{"field": "email", "issue": "required"}]
    }
  }

□ DISCOVERABLE: Can developers explore the API?
  OpenAPI/Swagger spec, interactive docs, clear examples.

□ FILTERABLE/SORTABLE: List endpoints support filtering?
  /users?role=admin&sort=-created_at&limit=20
```

**Common API design mistakes to flag:**
```
- Exposing internal database IDs as API identifiers
- Returning more data than the client needs (over-fetching)
- Deeply nested responses (>3 levels deep)
- Inconsistent error formats across endpoints
- No HATEOAS or pagination links for large collections
- PUT that partially updates (should be PATCH)
```

**The meta-principle:** An API is a user interface for developers. Apply the same usability principles: consistency, predictability, clear error messages, and progressive disclosure. A well-designed API makes the right thing easy and the wrong thing hard.'''
    ),
    (
        "thinking/auto-qa-architecture-scalability",
        r'''What quality checks should I apply when advising on scalability to make sure my advice is practical and not just theoretical?''',
        r'''<think>
Scalability advice often fails because it's theoretical rather than practical. Telling someone "use sharding" without explaining when, how, and at what cost doesn't help them.

**Common scalability advice failures:**
1. Premature: Recommending scaling solutions for problems that don't exist yet
2. Theoretical: Explaining concepts without practical implementation steps
3. Ignoring cost: Scaling solutions cost money and complexity
4. One-dimensional: Only considering request throughput, not data volume, team capacity, or operational complexity
5. Not staged: Recommending the final state instead of incremental steps
</think>

**Scalability Advice Quality Checklist**

**Before giving any scalability advice:**

**Step 1: Is scaling actually needed?**
```
□ CURRENT METRICS: What is the current load?
  Don't optimize for 1M users when you have 100.

□ GROWTH RATE: How fast is traffic growing?
  Doubling monthly → plan ahead
  Growing 10% monthly → you have time
  Flat → focus on features, not scaling

□ ACTUAL BOTTLENECK: What's actually slow?
  "We need to scale" could mean:
  - API response time is too high (optimize first)
  - Database is at capacity (add read replicas)
  - Running out of disk space (expand storage)
  - CPU constantly at 100% (vertical scale or optimize)

  Each needs a DIFFERENT solution.
```

**Step 2: Staged scaling advice**
```
□ INCREMENTAL STEPS: Not jumping to the end state?

  Stage 1 (0-1K users): Single server
    → Optimize code, add indexes, cache hot data

  Stage 2 (1K-10K users): Vertical scaling + caching
    → Bigger server, Redis cache, CDN for static assets

  Stage 3 (10K-100K users): Read replicas + load balancer
    → PostgreSQL read replicas, application load balancer

  Stage 4 (100K-1M users): Service extraction
    → Extract bottleneck services, message queues

  Stage 5 (1M+ users): Horizontal scaling
    → Sharding, multi-region, specialized databases

  Most applications never need to go beyond Stage 2 or 3.

□ CURRENT STAGE IDENTIFIED: Where are they now?
  Don't recommend Stage 5 to someone at Stage 1.
```

**Step 3: Practical implementation**
```
□ SPECIFIC ACTIONS: Not just concepts?
  BAD: "You should add caching"
  GOOD: "Cache the /api/products endpoint response in Redis
         with a 5-minute TTL. This endpoint is called 500
         times/minute and the data changes every 30 minutes.
         Expected result: 90% cache hit rate, reducing DB
         load by 450 queries/minute."

□ COST INCLUDED: What does this cost to implement and run?
  "Adding a Redis instance costs ~$50/month on AWS.
   Adding read replicas costs ~$200/month.
   This is worth it when your current DB is at 80%+ CPU."

□ OPERATIONAL COMPLEXITY: What new operational burden does this add?
  "Adding a cache means you now need to handle:
   - Cache invalidation (when data changes)
   - Cache failures (what if Redis goes down?)
   - Cache warming (on cold start)"
```

**Step 4: Verify the advice makes sense**
```
□ NOT PREMATURE: Is this solving a current problem?
□ NOT OVER-ENGINEERED: Is there a simpler solution?
□ MEASURABLE: How will they know if it worked?
□ REVERSIBLE: Can they undo this if it doesn't help?
□ TEAM-APPROPRIATE: Can the team build and operate this?
```

**Scalability red flags to catch:**
```
- "Use Kubernetes" for an app with 50 users
- "Add sharding" before trying read replicas
- "Use microservices for scale" (microservices are for team scaling,
  not necessarily traffic scaling)
- "Move to NoSQL for performance" (PostgreSQL handles most workloads)
- "Cache everything" without a cache invalidation strategy
```

**The meta-principle:** Scalability advice should be staged, measured, and proportional. The right question is never "how do we handle 10 million users?" It's "what's our next bottleneck and what's the minimum change to address it?" Scale incrementally, measure at each step, and don't solve problems you don't have yet.'''
    ),
    (
        "thinking/auto-qa-architecture-tradeoff-documentation",
        r'''How do I ensure that when I recommend an architecture, I'm clearly communicating the tradeoffs so the user can make an informed decision?''',
        r'''<think>
Architecture recommendations without tradeoffs are incomplete and potentially harmful. If you only present benefits, the user can't make an informed decision and will be surprised by the costs later.

**What tradeoffs to communicate:**
1. What you gain vs. what you lose
2. Short-term vs. long-term implications
3. Complexity added vs. problems solved
4. Cost (money, time, cognitive load)
5. What becomes harder with this choice
6. When this choice would be WRONG
</think>

**Architecture Tradeoff Communication Quality Checklist**

**For every architecture recommendation:**

**1. State what you LOSE, not just what you gain**
```
□ EXPLICIT COSTS: Have I listed the downsides?

  BAD: "Use microservices for better scalability and
        independent deployments."

  GOOD: "Microservices give you independent scaling and
         deployment per service.
         The cost:
         - Network latency between services (was a function call)
         - Distributed transaction complexity
         - Need for service discovery, load balancing, tracing
         - Operational overhead (N services × monitoring/deployment)
         - Data consistency challenges across service boundaries"

□ WHEN IT'S WRONG: Have I explained when NOT to use this?
  "Don't use microservices if:
   - Your team has fewer than 5 engineers
   - Your services share a single database
   - You don't have automated deployment pipelines
   - The domain boundaries aren't clear yet"
```

**2. Use a structured comparison format**
```
□ COMPARISON TABLE: Easy to scan trade-offs?

  | Factor | Monolith | Microservices |
  |--------|----------|---------------|
  | Dev speed (early) | Fast | Slow (infra overhead) |
  | Dev speed (late) | Slows as codebase grows | Fast (independent teams) |
  | Deployment | One deploy | N deploys |
  | Debugging | Easy (one process) | Hard (distributed tracing) |
  | Scaling | Scale everything together | Scale independently |
  | Team size needed | 1-10 | 10+ |
  | Ops complexity | Low | High |
```

**3. Quantify when possible**
```
□ CONCRETE NUMBERS: Have I estimated costs and benefits?

  BAD: "Caching will improve performance"
  GOOD: "Adding Redis caching for the product catalog will:
         - Reduce average response time from ~200ms to ~15ms
         - Reduce database load by ~80%
         - Cost: ~$50/month for Redis + ~2 days of dev work
         - Risk: Stale data for up to 5 minutes (the TTL)"
```

**4. Present the decision as a choice, not a decree**
```
□ OPTIONS PRESENTED: Have I given alternatives?

  "Option A: Monolith with good module boundaries
     Pro: Simple to develop, deploy, and debug
     Con: Harder to scale individual modules independently
     Best for: Teams <10, early-stage products

   Option B: Modular monolith with extractable services
     Pro: Simplicity of monolith with future flexibility
     Con: Requires discipline in module boundaries
     Best for: Teams 5-20, growing products

   Option C: Microservices from the start
     Pro: Independent scaling and deployment
     Con: High operational overhead from day one
     Best for: Teams 20+, well-understood domain

   My recommendation for YOUR context: Option B because [reasons]"

□ USER DECIDES: Is the final decision with the user?
  Present information, state your recommendation with reasoning,
  but make it clear THEY choose.
```

**5. Long-term implications**
```
□ EVOLUTION PATH: What happens in 1 year? 3 years?
  "If you choose a monolith now:
   Year 1: Fast development, easy debugging
   Year 2: Starting to feel large, maybe slow CI
   Year 3: May need to extract services for the largest modules
   This is NORMAL and fine — it means you've grown."

□ LOCK-IN: How hard is it to change this decision later?
  "Choosing PostgreSQL: Low lock-in (standard SQL, easy to migrate)
   Choosing DynamoDB: Higher lock-in (proprietary API, harder to leave)
   Choosing a niche database: Very high lock-in"
```

**The meta-principle:** Architecture recommendations are decisions under uncertainty. Presenting only benefits is dishonest; presenting only risks is unhelpful. The goal is to give the user enough information to make a decision they won't regret, even when circumstances change. Always answer: "What will we wish we had known before choosing this?"'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
