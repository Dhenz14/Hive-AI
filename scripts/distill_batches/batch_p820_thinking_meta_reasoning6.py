"""Phase 3A: Metacognition — Evaluating Reasoning Chain Validity (Part 6)

Training the model to examine its own reasoning chains for logical soundness,
identifying gaps, unsupported jumps, and weak inferences.
"""

PAIRS = [
    (
        "thinking/meta-reasoning-chain-validity-perf",
        r'''Our API response times doubled after we added input validation. The validation uses regex. Therefore, regex is causing the performance problem and we should remove the validation.''',
        r'''<think>
Let me evaluate the reasoning chain presented here step by step.

Claim 1: "API response times doubled after we added input validation" — This is an observed correlation. Assuming the measurement is accurate, this is a valid data point.

Claim 2: "The validation uses regex" — This is a factual claim about the implementation. Accepted.

Conclusion: "Regex is causing the performance problem and we should remove the validation."

Let me check this reasoning chain:

1. Post hoc ergo propter hoc fallacy? Not necessarily — temporal correlation after a specific code change is stronger evidence than general correlation. But there could be other changes deployed simultaneously.

2. Is the causal mechanism plausible? Yes — regex CAN cause severe performance issues (catastrophic backtracking, ReDoS). But not all regex is slow.

3. Unsupported logical jump: "uses regex" → "regex is the cause." The validation COULD be slow for other reasons:
   - Making additional database queries for validation
   - Calling external services
   - The regex patterns might be fine but there are too many of them
   - The validation runs on every field, not just the ones that need it

4. False dichotomy in the conclusion: "remove the validation" vs. "fix the regex." These aren't the only options. You could optimize the regex, use non-regex validation, validate only critical fields, or cache validation results.

5. Missing diagnostic step: No profiling data is presented. "Response times doubled" → "must be regex" skips the step of actually measuring where the time is spent.

The reasoning chain has a valid starting observation but makes unsupported jumps and reaches a conclusion that's both potentially wrong and potentially harmful (removing input validation has security implications).
</think>

Your reasoning chain has several problems. Let me break it down.

**The logical structure:**
```
Premise 1: Response times doubled after adding validation  ✓ Valid observation
Premise 2: Validation uses regex                          ✓ Factual claim
Conclusion: Regex is the cause, remove validation          ✗ Multiple logical errors
```

**Error 1: Skipping diagnosis**
You went from "times doubled" to "regex is the cause" without profiling. The validation code might be slow for reasons unrelated to regex:
```python
# Maybe the "validation" does more than regex
def validate_input(data):
    # This regex is fine — O(n) time
    if not re.match(r'^[a-zA-Z0-9_]+$', data.username):
        raise ValueError("Invalid username")

    # THIS might be the actual bottleneck:
    existing = db.query("SELECT id FROM users WHERE username = %s", data.username)
    if existing:
        raise ValueError("Username taken")
```

**Error 2: "Regex" is not inherently slow**
Most regex patterns run in microseconds. Only specific patterns cause catastrophic backtracking:
```python
# Fast — O(n) time
re.match(r'^\d{3}-\d{3}-\d{4}$', phone)

# Potentially catastrophic — exponential backtracking
re.match(r'^(a+)+$', evil_input)
```

**Error 3: False dichotomy**
"Remove validation" is not the only alternative to "keep slow validation":
- Fix the specific slow pattern
- Use non-regex validation where appropriate
- Validate asynchronously
- Cache validation results

**Error 4: Ignoring consequences**
Removing input validation to fix performance is a security regression. It's like removing the brakes to make a car faster.

**What sound reasoning looks like:**
```
1. Response times doubled after validation was added
2. Profile the validation code to identify the specific bottleneck
3. If regex: identify which pattern, check for backtracking
4. If not regex: find actual cause (DB call? network? allocation?)
5. Fix the specific bottleneck while keeping validation
```

**Action:** Add timing around each validation step, or use a profiler. The answer will be obvious in 5 minutes.'''
    ),
    (
        "thinking/meta-reasoning-chain-validity-scaling",
        r'''We tested our microservice and it handles 500 requests/second on one server. We have 10 servers. Therefore, we can handle 5000 requests/second in production.''',
        r'''<think>
Let me evaluate this reasoning chain for logical validity.

The argument structure:
- Premise: 1 server handles 500 req/s
- Premise: We have 10 servers
- Conclusion: 500 × 10 = 5000 req/s

This assumes perfect linear scalability, which is rarely true. Let me identify the specific flaws:

1. Shared resource bottlenecks: All 10 servers likely share a database, cache, or message queue. The database becomes the bottleneck well before 5000 req/s if it was already being stressed at 500 req/s.

2. Amdahl's Law: Speedup is limited by the serial (non-parallelizable) portion of the workload. Shared locks, sequential DB operations, etc.

3. Testing conditions vs production: The benchmark at 500 req/s may have been done with:
   - Synthetic/simple requests vs real complex ones
   - Warm caches vs cold
   - No concurrent users competing for shared resources
   - No network overhead between services

4. Load balancer overhead: Adding a load balancer adds latency and becomes its own potential bottleneck.

5. Contention increases non-linearly: 10 servers contending for the same database row locks, connection pools, etc. create exponentially more contention.

6. The Universal Scalability Law (Gunther): Throughput = N / (1 + α(N-1) + βN(N-1)) where α is contention and β is coherence overhead. For N=10, even small α and β values significantly reduce throughput below the linear 5000.

This is a well-known anti-pattern in capacity planning. Linear extrapolation of single-node benchmarks is almost always wrong.
</think>

This reasoning contains a critical and common flaw: assuming linear scalability. Let me dissect why.

**The assumed reasoning:**
```
1 server  = 500 req/s
10 servers = 500 × 10 = 5000 req/s  ← Almost never true
```

**Why linear scaling rarely holds:**

**Problem 1: Shared resources don't scale with servers**
```
[Server 1] ──┐
[Server 2] ──┤
[Server 3] ──┼──→ [Single Database] ← THIS is your bottleneck
   ...       │
[Server 10]──┘

At 500 req/s:  DB handles 500 queries comfortably
At 5000 req/s: DB connection pool exhausted, lock contention, query queuing
```

**Problem 2: Contention increases non-linearly**
```
 Servers │ Theoretical │ Realistic (with contention)
─────────┼─────────────┼───────────────────────────
    1    │     500     │     500
    2    │    1000     │     900
    5    │    2500     │    1800
   10    │    5000     │    2500-3000
   20    │   10000     │    3000-4000 (diminishing returns)
```

**Problem 3: Test conditions differ from production**
- Benchmarks often hit warm caches; production has cache misses
- Synthetic load is uniform; real traffic has hot spots
- Single-server tests don't exercise distributed coordination

**Problem 4: New failure modes at scale**
- Connection pool exhaustion to shared services
- Network bandwidth between services
- Load balancer becomes a bottleneck
- Distributed tracing/logging overhead

**Sound reasoning for capacity planning:**
```
1. Benchmark a single server under realistic load       → 500 req/s
2. Identify shared dependencies (DB, cache, queues)
3. Benchmark shared dependencies independently           → DB handles 2000 queries/s
4. Load test with 2, 5, 10 servers to measure actual scaling curve
5. Find the bottleneck (usually the database)
6. Plan capacity based on measured scaling, not arithmetic
```

**The realistic capacity plan:**
```
Single server: 500 req/s
Database limit: ~2000 queries/s (measure this!)
Actual capacity with 10 servers: min(5000, 2000) = ~2000 req/s
To reach 5000: scale the database too (read replicas, caching, sharding)
```

Always load test at target scale. Never multiply single-node benchmarks.'''
    ),
    (
        "thinking/meta-reasoning-chain-validity-rewrites",
        r'''Our codebase is 5 years old and hard to work with. We should rewrite it in a modern framework. The rewrite will take 6 months and solve all our problems.''',
        r'''<think>
This is a classic reasoning chain I need to examine carefully. This is one of the most well-documented anti-patterns in software engineering (Joel Spolsky's "Things You Should Never Do" and numerous case studies).

Let me evaluate each claim:

Premise 1: "Codebase is 5 years old and hard to work with" — This is probably true. But age alone doesn't mean a rewrite is needed. "Hard to work with" is subjective and could mean many things.

Premise 2: "We should rewrite it in a modern framework" — This is presented as the logical solution to premise 1, but it's a massive leap. Multiple unsupported assumptions:
- That the difficulty is inherent to the technology, not the domain complexity
- That a new framework would make the SAME domain problems easier
- That the team understands the current system well enough to rewrite it
- That a new framework won't introduce its own problems

Premise 3: "The rewrite will take 6 months" — This is almost certainly wrong. Software rewrites are notoriously under-estimated. The original code took 5 years to evolve and contains countless implicit decisions, bug fixes, and edge case handling.

Conclusion: "Solve all our problems" — This is magical thinking. The problems that make the codebase "hard to work with" are likely domain complexity, accumulated business rules, and edge cases — which will ALL be present in the rewrite.

Known evidence against this reasoning:
- Netscape's rewrite (killed the company)
- The second system effect (Brooks, The Mythical Man-Month)
- Every study on software rewrites shows they take 2-3x the estimate
- During rewrite, the old system still needs maintenance (two codebases!)

I should present this analysis clearly and offer alternatives.
</think>

This reasoning chain is one of the most well-documented traps in software engineering. Let me examine each link.

**Claim 1: "5 years old and hard to work with"**
Probably true, but misattributed. The difficulty is usually:
- Accumulated business rules (present in ANY implementation)
- Missing documentation (won't magically appear in a rewrite)
- Technical debt in specific areas (fixable incrementally)
- Tribal knowledge that left with former team members

**Claim 2: "Rewrite in a modern framework"**
Unsupported assumptions:
```
Assumption: The technology is the problem
Reality:    The domain complexity is the problem

Assumption: Modern framework = easier code
Reality:    Same business rules + new framework = same complexity + learning curve

Assumption: We understand the current system well enough to rewrite it
Reality:    If we did, we could fix it incrementally
```

**Claim 3: "6 months"**
Almost certainly wrong. Historical data on rewrites:
```
Original system:  5 years of development
Estimated rewrite: 6 months
Actual rewrite:    18-36 months (consistently 3-5x estimates)
Reason: The ugly code you want to replace contains thousands of
        implicit decisions, edge cases, and bug fixes that MUST
        be replicated
```

**Claim 4: "Solve all our problems"**
This is the biggest logical error. During the rewrite:
- The old system still needs maintenance (now you have TWO codebases)
- No new features ship for the rewrite duration (competitors advance)
- The new system re-introduces bugs the old system had fixed years ago
- Team morale drops when the "6-month" rewrite hits month 14

**What sound reasoning looks like:**

Instead of a full rewrite, use the Strangler Fig pattern:
```
1. Identify the SPECIFIC pain points (not "everything is bad")
2. Draw a boundary around the worst module
3. Build a new service/module behind the same API
4. Redirect traffic from old to new incrementally
5. Repeat for the next worst module

Timeline: Each module takes 2-4 weeks, delivers value immediately
Risk:     Low — old system still works, rollback is trivial
```

**When IS a rewrite justified?**
- The technology is literally unsupported (no security patches)
- The architecture fundamentally cannot meet new requirements (e.g., single-tenant to multi-tenant)
- The codebase is small enough to rewrite in 2-4 weeks
- You have comprehensive tests that define the expected behavior

In most cases, incremental improvement beats rewrite.'''
    ),
    (
        "thinking/meta-reasoning-chain-validity-nosql",
        r'''Our PostgreSQL queries are slow. MongoDB is faster because it's NoSQL. Let's migrate to MongoDB.''',
        r'''<think>
Let me evaluate this reasoning chain link by link.

Premise 1: "Our PostgreSQL queries are slow" — This might be true, but it's vague. Which queries? All of them? Slow means what — 100ms? 10 seconds? Under what load?

Premise 2: "MongoDB is faster because it's NoSQL" — This is a category error and a false generalization:
- "NoSQL is faster" is not universally true
- MongoDB trades consistency and joins for write throughput
- For read-heavy workloads with complex queries, PostgreSQL is often faster
- MongoDB can be very slow for queries it's not optimized for (ad-hoc aggregations, joins)
- The speed difference usually comes from schema design, not the database engine

Logical jump: "PostgreSQL slow" → "switch databases" skips the crucial step of understanding WHY PostgreSQL is slow. Common causes:
- Missing indexes (fix takes minutes)
- N+1 query patterns (fix takes hours)
- Bad query structure (fix takes hours)
- Insufficient connection pooling
- Under-provisioned hardware
- No query caching layer

Conclusion: "Let's migrate to MongoDB" — This involves:
- Rewriting the data access layer
- Redesigning the schema (document vs relational)
- Losing ACID transactions, foreign keys, complex joins
- Learning a new operational model
- Migrating data
- Likely 3-6 months of work

When the actual fix might be:
- Adding an index: 1 minute
- Adding connection pooling: 1 hour
- Query optimization: 1 day

This is a classic case of solving the wrong problem with maximum effort.
</think>

This reasoning chain has multiple critical flaws. Let me trace through each one.

**Link 1: "PostgreSQL queries are slow"**
Vague. Before changing databases, answer:
```sql
-- Which queries? Run this to find the slowest:
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Why are they slow?
EXPLAIN (ANALYZE, BUFFERS)
SELECT ... -- your slow query here
```

**Link 2: "MongoDB is faster because it's NoSQL"**
This is a false generalization:
```
Myth:    NoSQL = faster
Reality: NoSQL = different tradeoffs

MongoDB is faster at:          PostgreSQL is faster at:
- Simple key-value lookups     - Complex queries with JOINs
- Writes to denormalized docs  - Aggregations on normalized data
- Schema-flexible inserts       - Consistent reads with ACID
- Horizontal write scaling      - Complex WHERE clauses with indexes
```

**Link 3: "Let's migrate"**
The cost-benefit analysis is wildly off:

```
Option A: Fix PostgreSQL queries
  Cost:  Hours to days
  Risk:  Low
  Fixes: The actual problem

Option B: Migrate to MongoDB
  Cost:  3-6 months
  Risk:  High (new failure modes, lost features)
  Fixes: Maybe nothing (if the problem was missing indexes)
  Loses: ACID transactions, foreign keys, complex queries
```

**What's actually causing your slow queries (ranked by likelihood):**

```
1. Missing index        → CREATE INDEX (1 minute fix)
2. N+1 query pattern    → Add JOINs or eager loading (1 hour fix)
3. No connection pool   → Add PgBouncer (1 hour fix)
4. Sequential scans     → EXPLAIN ANALYZE, add appropriate index
5. Table bloat          → VACUUM FULL or pg_repack
6. Under-provisioned    → Increase shared_buffers, work_mem
```

**Sound reasoning:**
```
1. "Queries are slow" → Identify which queries
2. EXPLAIN ANALYZE    → Understand why they're slow
3. Fix root cause     → Usually indexes or query structure
4. Re-measure         → Verify improvement
5. Only THEN consider architecture changes if fundamentally limited
```

Don't solve a query optimization problem with a database migration.'''
    ),
    (
        "thinking/meta-reasoning-chain-validity-microservices",
        r'''Netflix uses microservices and they handle millions of users. We should break our monolith into microservices so we can scale too.''',
        r'''<think>
This is an argument from authority/analogy. Let me evaluate the reasoning chain.

Premise 1: "Netflix uses microservices" — True.
Premise 2: "Netflix handles millions of users" — True.
Implied causation: Netflix handles millions of users BECAUSE of microservices.
Conclusion: We should adopt microservices to achieve similar scale.

Logical errors:

1. Survivorship bias — We hear about Netflix's success with microservices. We don't hear about the hundreds of companies that adopted microservices and failed, or that Netflix's scale is enabled by thousands of engineers, custom tooling, and massive infrastructure investment.

2. Confusing correlation with causation — Netflix uses microservices AND handles millions of users, but the causation is more complex. Netflix also has:
   - Thousands of engineers
   - Custom-built infrastructure (Eureka, Zuul, Hystrix)
   - Years of iterative architecture evolution
   - Started as a monolith and broke it apart over time

3. False analogy — Netflix's problems (streaming video at global scale) are almost certainly different from the questioner's problems. Scale requirements differ by orders of magnitude.

4. Ignoring the costs of microservices:
   - Distributed system complexity
   - Network latency between services
   - Data consistency challenges
   - Operational overhead (deployment, monitoring, debugging)
   - Team structure requirements (Conway's Law)

5. The actual history: Netflix started as a monolith and migrated to microservices as they grew. They didn't start with microservices.

Many successful companies run monoliths at significant scale: Shopify, Stack Overflow (famously handles millions of users on a monolith), Basecamp.
</think>

This is a textbook logical fallacy — argument from authority combined with false analogy. Let me trace the errors.

**The reasoning structure:**
```
Netflix uses X       ✓ True
Netflix is successful ✓ True
Therefore X causes success  ✗ Non sequitur
Therefore we should use X   ✗ False analogy
```

**Error 1: Correlation is not causation**
Netflix also has:
- 10,000+ engineers building custom tooling
- $30B+ annual revenue to fund infrastructure
- Years of iterative evolution (they STARTED as a monolith)
- Custom service mesh, discovery, circuit breaking

You're proposing to adopt the architecture without the supporting ecosystem.

**Error 2: Survivorship bias**
You hear about Netflix. You don't hear about companies that adopted microservices and:
- Spent 2 years in "distributed monolith" hell
- Couldn't debug cross-service issues
- Doubled their infrastructure costs
- Eventually merged services back together

**Error 3: Scale mismatch**
```
Netflix:    ~250M subscribers, ~15% of global internet traffic
Your app:   Probably <100K users (even "millions" is 100x smaller)

Stack Overflow: 100M+ monthly visitors → runs on a monolith
Shopify:        Handles Black Friday traffic → modular monolith
Basecamp:       Millions of users → monolith by choice
```

**Error 4: Ignoring the costs**

| Monolith | Microservices |
|----------|--------------|
| Deploy one thing | Deploy and coordinate 20+ services |
| One database, ACID transactions | Distributed data, eventual consistency |
| Function call between modules | Network call (latency, failures) |
| One log file | Distributed tracing required |
| Debug with a stack trace | Debug across service boundaries |
| 1 team can manage | Needs team-per-service (Conway's Law) |

**Sound reasoning for scaling:**
```
1. What is our ACTUAL bottleneck? (measure, don't guess)
2. Can we scale the monolith? (usually yes: caching, read replicas, CDN)
3. Is there ONE specific component that needs independent scaling?
   → Extract THAT into a service (not everything at once)
4. Do we have the team structure for microservices?
   → < 50 engineers? Probably not.
```

**When microservices ARE justified:**
- Multiple teams need to deploy independently (organizational, not technical)
- Specific components have drastically different scaling needs
- You need different technology stacks for different problems
- Your monolith is already well-modularized with clear boundaries

Start with a well-structured monolith. Extract services when you have a specific, measured reason to.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
