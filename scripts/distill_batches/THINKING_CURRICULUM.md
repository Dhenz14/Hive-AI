# Hive AI Thinking Curriculum: 1,600 Pairs Master Plan

**STATUS: COMPLETE** — 1,638/1,600 pairs written across 327 batch files (March 2026)

## Architecture: 4 Phases × 400 Pairs

The human brain doesn't learn to think in one step. Neither should the model.
Each phase builds on the previous one. Order matters.

```
Phase 1: FOUNDATION (434/400 pairs)  →  "Learn to think step-by-step"     ✓ COMPLETE
Phase 2: ADVANCED (401/400 pairs)    →  "Learn to think WELL"             ✓ COMPLETE
Phase 3: META (403/400 pairs)        →  "Learn to judge your own thinking" ✓ COMPLETE
Phase 4: AUTONOMY (400/400 pairs)    →  "Learn to improve yourself"       ✓ COMPLETE
```

---

## Phase 1: Foundation Thinking (400 pairs)
**Goal**: The model learns to decompose problems and reason step-by-step.

### 1A. Systematic Debugging (60 pairs)
Step-by-step execution tracing, hypothesis formation, root cause isolation.

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Off-by-one errors in loops/boundaries | 4 | Trace concrete values through iterations |
| 2 | Null/None reference chains | 4 | Follow data flow to find where None enters |
| 3 | Race conditions (threads, async) | 5 | Interleave execution timelines |
| 4 | Memory leaks (references, closures, caches) | 4 | Trace object lifecycle and GC roots |
| 5 | Silent data corruption (floats, encoding, timezone) | 5 | Check type coercion at each boundary |
| 6 | Import/dependency cycles | 3 | Trace module loading order |
| 7 | State mutation bugs (aliasing, shared refs) | 4 | Track every reference to the same object |
| 8 | Async/await ordering bugs | 4 | Draw the event loop timeline |
| 9 | Configuration drift (env vs code vs default) | 3 | Trace config resolution priority chain |
| 10 | Encoding/unicode bugs (UTF-8, bytes vs str) | 4 | Track encoding at every I/O boundary |
| 11 | Regex bugs (greedy, backtracking, escaping) | 3 | Manually step through the NFA |
| 12 | Type coercion bugs (JS truthiness, Python int/str) | 3 | Trace type at each operation |
| 13 | ORM/query bugs (lazy loading, N+1, wrong join) | 4 | Translate ORM to actual SQL, trace results |
| 14 | Concurrency bugs (deadlock, livelock, starvation) | 4 | Draw lock acquisition timeline |
| 15 | Signal/interrupt handling bugs | 3 | Trace what happens mid-operation |
| 16 | Serialization bugs (pickle, JSON, protobuf) | 3 | Compare in-memory object vs serialized form |

### 1B. Security Analysis (50 pairs)
Trace attack vectors, assess exploitability, reason about defense layers.

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | SQL injection (UNION, blind, second-order) | 4 | Construct the actual exploit payload |
| 2 | XSS (stored, reflected, DOM-based) | 4 | Trace user input to rendered output |
| 3 | SSRF (cloud metadata, internal scanning) | 3 | Map what the server can reach |
| 4 | Authentication bypass (JWT, session, OAuth) | 5 | Find the logic gap in the auth chain |
| 5 | Authorization flaws (IDOR, privilege escalation) | 4 | Check every access control decision |
| 6 | Deserialization attacks (pickle, YAML, XML) | 3 | Show how arbitrary code executes |
| 7 | Path traversal / file inclusion | 3 | Trace path resolution step by step |
| 8 | CSRF / CORS misconfiguration | 3 | Show the cross-origin attack flow |
| 9 | Cryptographic mistakes (ECB, weak PRNG, timing) | 4 | Demonstrate the mathematical weakness |
| 10 | Dependency/supply chain vulnerabilities | 3 | Trace the compromised package path |
| 11 | Race condition exploits (TOCTOU) | 3 | Show the timing window |
| 12 | API key/secret exposure patterns | 3 | Trace where secrets leak (logs, errors, git) |
| 13 | Mass assignment / prototype pollution | 3 | Show which fields an attacker controls |
| 14 | Command injection (shell, eval, template) | 3 | Construct the breakout payload |
| 15 | Business logic flaws (price manipulation, replay) | 2 | Trace the trust boundary violation |

### 1C. Performance Optimization (50 pairs)
Profile → identify bottleneck → reason about fix → verify improvement.

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | N+1 query patterns (Django, SQLAlchemy, Rails) | 4 | Count actual queries, show the JOIN fix |
| 2 | Memory profiling (peak, leak, fragmentation) | 4 | Trace object allocation timeline |
| 3 | Algorithm complexity analysis (real code, not textbook) | 5 | Count operations for concrete inputs |
| 4 | Database index strategy (compound, partial, covering) | 4 | Trace EXPLAIN plan before/after |
| 5 | Connection pool tuning | 3 | Analyze wait time vs pool size vs load |
| 6 | Caching strategy (what/where/when to cache) | 4 | Analyze hit rate, invalidation, stampede |
| 7 | API latency optimization (parallel, async, background) | 4 | Draw the dependency DAG, find critical path |
| 8 | Serialization performance (JSON vs msgpack vs protobuf) | 3 | Benchmark with realistic payloads |
| 9 | Batch vs stream processing tradeoffs | 3 | Calculate throughput/latency for each |
| 10 | GIL-aware optimization (threads vs processes vs async) | 4 | Profile CPU vs I/O time ratio |
| 11 | Lazy loading vs eager loading | 3 | Trace actual access patterns |
| 12 | String/allocation optimization (builders, interning) | 3 | Count allocations and copies |
| 13 | Network optimization (compression, keepalive, HTTP/2) | 3 | Measure actual bytes on wire |
| 14 | ReDoS and regex optimization | 3 | Trace the backtracking explosion |

### 1D. Architecture & Design (50 pairs)
Evaluate tradeoffs, reason about constraints, justify decisions.

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Monolith vs microservices (for specific requirements) | 3 | Evaluate against team size, complexity, scale |
| 2 | Database selection (SQL vs NoSQL vs hybrid) | 4 | Match data model + query patterns to engine |
| 3 | Event-driven vs request-response | 3 | Analyze coupling, latency, reliability needs |
| 4 | API design (REST vs GraphQL vs gRPC) | 3 | Match to client patterns and team skills |
| 5 | Caching architecture (local, distributed, CDN) | 3 | Calculate hit rates, analyze invalidation |
| 6 | Message queue selection (Kafka vs RabbitMQ vs Redis) | 3 | Match throughput, durability, ordering needs |
| 7 | Authentication architecture (JWT vs session vs OAuth) | 3 | Evaluate security model, revocation, scale |
| 8 | Search architecture (PostgreSQL FTS vs Elasticsearch) | 3 | Match query complexity to engine capability |
| 9 | File storage architecture (local vs S3 vs CDN) | 3 | Calculate cost, latency, durability |
| 10 | Rate limiting design (token bucket, sliding window) | 3 | Calculate capacity, analyze failure modes |
| 11 | Circuit breaker and resilience patterns | 3 | Analyze cascade failure scenarios |
| 12 | Data pipeline architecture (batch vs stream vs lambda) | 3 | Match latency requirements to architecture |
| 13 | Multi-tenancy design (shared vs isolated) | 3 | Evaluate cost, security, complexity |
| 14 | Deployment strategy (blue-green, canary, rolling) | 3 | Analyze risk, speed, rollback capability |
| 15 | State management (stateless vs stateful services) | 3 | Trace state lifecycle and failure modes |
| 16 | CQRS / event sourcing decision | 3 | Analyze read/write patterns and audit needs |

### 1E. Code Review & Refactoring (50 pairs)
Read code, identify problems, reason about improvements.

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | God class decomposition | 4 | Identify responsibility clusters |
| 2 | Callback hell → async/await | 3 | Trace control flow, find parallelizable paths |
| 3 | Hardcoded values → configuration | 3 | Identify what changes vs what's fixed |
| 4 | Copy-paste code → abstractions | 4 | Find the variation points between copies |
| 5 | Tight coupling → dependency injection | 4 | Trace dependencies, identify interfaces |
| 6 | Imperative → functional transforms | 3 | Map mutation to immutable pipelines |
| 7 | Monolithic function → pipeline pattern | 3 | Identify stages and data flow |
| 8 | Sync → async migration | 4 | Identify I/O boundaries and parallelism |
| 9 | Raw SQL → ORM (and when NOT to) | 3 | Compare readability, performance, safety |
| 10 | Inheritance → composition | 3 | Identify "is-a" vs "has-a" confusion |
| 11 | Global state → explicit passing | 3 | Trace all readers and writers of the global |
| 12 | Error code returns → exceptions (and vice versa) | 3 | Analyze error propagation patterns |
| 13 | Feature flag cleanup | 3 | Trace all branches, identify dead code |
| 14 | API surface reduction | 3 | Identify what's public vs what should be internal |
| 15 | Test refactoring (flaky, slow, brittle tests) | 4 | Identify root cause of test problems |

### 1F. Testing Strategy (40 pairs)
Reason about what to test, at what level, with what approach.

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Unit vs integration vs e2e decision | 4 | Analyze what each level catches |
| 2 | Mock vs real dependency decision | 4 | Evaluate isolation vs realism tradeoff |
| 3 | Test design for complex business logic | 4 | Identify equivalence classes and boundaries |
| 4 | Property-based testing design | 4 | Identify invariants that must always hold |
| 5 | Snapshot testing strategy | 3 | Analyze change frequency vs review burden |
| 6 | Test data management | 3 | Analyze factory patterns, fixtures, builders |
| 7 | Flaky test root cause analysis | 4 | Categorize: shared state, timing, ordering |
| 8 | Coverage-driven test gap analysis | 3 | Find untested critical paths |
| 9 | Mutation testing interpretation | 3 | Analyze surviving mutants → missing assertions |
| 10 | Contract testing for APIs | 3 | Define consumer-driven contracts |
| 11 | Load/stress test design | 3 | Calculate expected load, define thresholds |
| 12 | Chaos engineering test design | 2 | Identify failure modes to inject |

### 1G. Concurrency & Distributed Systems (50 pairs)
Reason about parallel execution, consistency, failure modes.

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Deadlock detection and prevention | 4 | Draw lock acquisition graphs |
| 2 | Race condition identification | 4 | Interleave execution timelines |
| 3 | Producer-consumer patterns | 3 | Analyze backpressure and buffer sizing |
| 4 | Thread pool sizing | 3 | Calculate optimal size from I/O ratio |
| 5 | Distributed consensus (leader election, quorum) | 3 | Trace message sequences in split-brain |
| 6 | Eventual consistency patterns | 3 | Analyze conflict resolution strategies |
| 7 | Distributed transaction patterns (saga, 2PC) | 4 | Trace failure at each step, show compensation |
| 8 | Idempotency design | 3 | Identify replay scenarios and dedup keys |
| 9 | Async/await patterns (fan-out, pipeline, semaphore) | 4 | Draw the event loop timeline |
| 10 | Lock-free data structures | 3 | Trace CAS operations and ABA problem |
| 11 | Backpressure and flow control | 3 | Calculate producer vs consumer rate mismatch |
| 12 | Retry strategy (exponential backoff, jitter, circuit) | 4 | Analyze thundering herd and cascade failure |
| 13 | Connection pooling and lifecycle | 3 | Trace connection state through requests |
| 14 | Partition tolerance tradeoffs (CAP theorem applied) | 3 | Analyze what happens during network split |
| 15 | Actor model patterns | 3 | Trace message passing and mailbox overflow |

### 1H. Data Modeling & DevOps (50 pairs)
Database schema design, deployment, infrastructure reasoning.

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Schema polymorphism (STI, CTI, concrete table) | 3 | Evaluate query patterns vs normalization |
| 2 | Soft delete vs hard delete + archive | 3 | Analyze query complexity and compliance |
| 3 | Pagination strategies (offset, cursor, keyset) | 3 | Analyze performance at scale |
| 4 | Time-series data modeling | 3 | Optimize for write throughput and range queries |
| 5 | Multi-tenant schema design | 3 | Evaluate isolation vs cost vs complexity |
| 6 | Migration strategy (zero-downtime schema changes) | 4 | Plan backward-compatible migration steps |
| 7 | Denormalization decisions | 3 | Calculate read/write ratio and consistency cost |
| 8 | JSON columns vs normalized tables | 3 | Analyze query patterns and schema flexibility |
| 9 | Docker optimization (layers, cache, multi-stage) | 3 | Trace build cache invalidation |
| 10 | Zero-downtime deployment | 3 | Plan rolling update with health checks |
| 11 | CI/CD pipeline design | 3 | Optimize for speed and reliability |
| 12 | Logging/observability strategy | 3 | Design structured logging with correlation |
| 13 | Infrastructure as code patterns | 3 | Evaluate drift detection and state management |
| 14 | Backup and disaster recovery | 3 | Calculate RPO/RTO and test recovery |
| 15 | Secret management | 3 | Trace secret lifecycle and rotation |
| 16 | Container orchestration decisions | 3 | Evaluate Docker Compose vs K8s vs Nomad |

**Phase 1 Total: 400 pairs**

---

## Phase 2: Advanced Reasoning (400 pairs)
**Goal**: The model learns reasoning TECHNIQUES that most models never see.

### 2A. Backtracking & Dead-End Recovery (60 pairs)
**THE SECRET SAUCE.** Most training data shows linear reasoning: think → answer.
Real reasoning involves wrong turns, dead ends, and recovery. This teaches the
model that getting stuck is NORMAL and recoverable.

Format:
```
<think>
Let me try approach A...
[works through it]
Wait, this won't work because [specific reason].
Let me backtrack and try approach B instead...
[works through it]
This is better because [comparison to failed approach].
</think>
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Algorithm: greedy fails → needs DP | 5 | Show why greedy misses cases, switch to DP |
| 2 | Architecture: sync fails → needs async | 4 | Show sync bottleneck, redesign for async |
| 3 | DB: single query fails → needs CTE/subquery | 4 | Show why JOIN gives wrong results |
| 4 | Security: first fix is bypassable → needs deeper fix | 5 | Show bypass, then defense-in-depth |
| 5 | Refactor: extract method fails → needs extract class | 4 | Show why method isn't enough encapsulation |
| 6 | Test: unit test insufficient → needs integration | 4 | Show what unit test misses |
| 7 | Concurrency: lock fails → needs lock-free design | 4 | Show deadlock with locks, redesign |
| 8 | Performance: cache fails → needs algorithmic fix | 4 | Show cache doesn't help, need better algorithm |
| 9 | Design: inheritance fails → needs composition | 4 | Show diamond problem or rigidity |
| 10 | API: REST awkward → needs different paradigm | 4 | Show where REST doesn't fit the domain |
| 11 | Data model: normalized fails → needs denormalize | 4 | Show query cost, justify denormalization |
| 12 | Config: env vars fail → needs feature flags | 4 | Show deployment-time vs runtime config needs |
| 13 | Error handling: catch-all fails → needs specific handlers | 4 | Show masked errors from broad catch |
| 14 | Parsing: regex fails → needs proper parser | 3 | Show regex can't handle nesting/context |
| 15 | Migration: big bang fails → needs strangler fig | 3 | Show risk analysis of each approach |

### 2B. Adversarial Self-Testing (60 pairs)
The model tries to BREAK its own solution before presenting it.

Format:
```
<think>
Here's my solution: [code]
Now let me try to break it...
Edge case 1: empty input → [traces behavior] → handles correctly
Edge case 2: concurrent access → [traces behavior] → BUG! Fix: [fix]
Edge case 3: very large input → [traces behavior] → O(n²) problem. Fix: [fix]
Updated solution: [fixed code]
</think>
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Algorithm edge cases (empty, single, max, negative) | 5 | Enumerate boundary values systematically |
| 2 | API endpoint fuzzing (malformed input, huge payload) | 5 | Test each parameter with adversarial values |
| 3 | SQL query edge cases (NULL, empty string, Unicode) | 4 | Test each WHERE clause with edge values |
| 4 | Concurrency stress testing (100 concurrent requests) | 5 | Simulate interleaved execution |
| 5 | Auth bypass attempts on own security code | 5 | Try every known bypass technique |
| 6 | State machine impossible transitions | 4 | Enumerate all transition combinations |
| 7 | Resource exhaustion (memory, connections, file handles) | 4 | Calculate worst-case resource usage |
| 8 | Unicode and encoding edge cases | 4 | Test with emoji, RTL, null bytes, BOM |
| 9 | Timezone and date boundary cases | 4 | Test DST, leap year, year boundary |
| 10 | Floating point precision traps | 4 | Test with values known to cause issues |
| 11 | Error propagation completeness | 4 | Verify every error path is handled |
| 12 | Configuration combination testing | 4 | Test feature flag interactions |
| 13 | Backward compatibility verification | 4 | Test old clients against new API |
| 14 | Network failure scenarios (timeout, partial, corrupt) | 4 | Test each failure mode |

### 2C. Analogical Reasoning (50 pairs)
Transfer knowledge between domains. "This is like X because..."

Format:
```
<think>
This problem reminds me of [analogous problem] because both involve
[shared structure]. In that domain, the solution was [approach].
Adapting that here: [modified approach for current domain].
The analogy breaks down at [specific point] because [difference],
so I need to adjust [specific adjustment].
</think>
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Circuit breaker ↔ electrical fuse | 4 | Map concepts between domains |
| 2 | Database index ↔ book index | 3 | Transfer lookup optimization reasoning |
| 3 | Backpressure ↔ traffic congestion | 3 | Transfer flow control reasoning |
| 4 | Dependency injection ↔ power outlets | 3 | Transfer interface/implementation separation |
| 5 | Git branching ↔ parallel universes | 3 | Transfer merge/conflict reasoning |
| 6 | Caching ↔ short-term memory | 3 | Transfer eviction/refresh reasoning |
| 7 | Load balancer ↔ checkout lanes | 3 | Transfer queue theory reasoning |
| 8 | Microservices ↔ team organization | 4 | Transfer Conway's Law reasoning |
| 9 | Eventual consistency ↔ bank reconciliation | 3 | Transfer conflict resolution reasoning |
| 10 | Token bucket ↔ water tank with faucet | 3 | Transfer rate control reasoning |
| 11 | Mutex ↔ bathroom lock | 3 | Transfer exclusive access reasoning |
| 12 | Observer pattern ↔ newspaper subscription | 3 | Transfer pub/sub reasoning |
| 13 | Strangler fig pattern ↔ actual strangler fig tree | 3 | Transfer gradual replacement reasoning |
| 14 | MapReduce ↔ vote counting by precinct | 3 | Transfer parallel aggregation reasoning |
| 15 | A/B testing ↔ clinical trials | 3 | Transfer experimental design reasoning |
| 16 | Saga pattern ↔ travel booking with cancellation | 3 | Transfer compensation reasoning |

### 2D. Multi-Perspective Analysis (50 pairs)
Analyze the same problem from multiple angles simultaneously.

Format:
```
<think>
Let me evaluate this from multiple angles:

CORRECTNESS: Does it produce the right result? [analysis]
PERFORMANCE: How does it scale? [analysis]
SECURITY: Can it be exploited? [analysis]
MAINTAINABILITY: Can someone else understand this in 6 months? [analysis]
OPERABILITY: How do we monitor and debug this in production? [analysis]

Tensions between perspectives:
- Performance wants X but security requires Y → [resolution]
- Maintainability wants Z but performance needs W → [tradeoff decision]
</think>
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | User authentication system | 4 | Security vs UX vs performance |
| 2 | Data pipeline architecture | 4 | Throughput vs latency vs cost |
| 3 | API rate limiting | 3 | Security vs availability vs complexity |
| 4 | Database schema design | 4 | Normalization vs query performance vs flexibility |
| 5 | Error handling strategy | 4 | Robustness vs debuggability vs user experience |
| 6 | Caching strategy | 3 | Freshness vs performance vs memory |
| 7 | Logging verbosity | 3 | Debuggability vs performance vs storage cost |
| 8 | Test coverage targets | 3 | Confidence vs development speed vs maintenance |
| 9 | Dependency management | 3 | Security (updates) vs stability (pinning) |
| 10 | Microservice boundary decisions | 4 | Independence vs complexity vs latency |
| 11 | Configuration management | 3 | Flexibility vs security vs simplicity |
| 12 | Code review depth | 3 | Quality vs velocity vs team morale |
| 13 | Technical debt decisions | 4 | Ship now vs fix now vs schedule later |
| 14 | Open source dependency decisions | 3 | Features vs maintenance risk vs lock-in |

### 2E. Causal & Counterfactual Reasoning (50 pairs)
"Why did this happen?" and "What if we had done X instead?"

Format:
```
<think>
The bug manifests as [symptom].
Possible causes:
1. [Cause A] → would also produce [other symptom] → checking... no → ruled out
2. [Cause B] → would only happen if [condition] → checking... yes → likely
3. [Cause C] → would require [prerequisite] → not present → ruled out

Root cause: [Cause B].
Causal chain: [B] → [intermediate effect] → [symptom]

Counterfactual: If we had [alternative design], this wouldn't have happened because
[the causal chain would be broken at step X].
</think>
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Production outage root cause analysis | 5 | Eliminate causes systematically |
| 2 | Performance regression after deploy | 5 | Diff deploy changes against symptoms |
| 3 | Data inconsistency investigation | 4 | Trace data flow to find corruption point |
| 4 | Memory growth over time | 4 | Correlate memory with events/operations |
| 5 | Intermittent test failure | 4 | Identify non-determinism source |
| 6 | Security breach forensics | 4 | Reconstruct attack timeline |
| 7 | Deployment failure analysis | 4 | Trace deployment pipeline for failure point |
| 8 | API behavior change investigation | 4 | Compare request/response before and after |
| 9 | Database performance degradation | 4 | Correlate with data growth, query changes, load |
| 10 | User-reported bug reproduction | 4 | Narrow conditions until reproducible |
| 11 | Distributed system failure cascade | 4 | Trace failure propagation across services |
| 12 | "Works on my machine" resolution | 4 | Diff environments systematically |

### 2F. Uncertainty & Confidence Calibration (40 pairs)
**MOST MODELS CAN'T DO THIS.** Teach the model to express calibrated uncertainty.

Format:
```
<think>
I'm fairly confident about [X] because [strong evidence].
I'm less sure about [Y] — it depends on [unstated assumption].
I'm genuinely uncertain about [Z] — here are two equally plausible approaches:
  Option A: [reasoning] — better if [condition]
  Option B: [reasoning] — better if [other condition]
I'd need to know [specific question] to decide between them.
</think>
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | "Is this a bug or intentional behavior?" | 4 | Analyze evidence for both interpretations |
| 2 | "Which database is best for this use case?" | 4 | Express genuine uncertainty with conditions |
| 3 | "Will this optimization actually help?" | 4 | "It depends on [specific measurable thing]" |
| 4 | "Is this approach scalable enough?" | 4 | Quantify uncertainty with capacity math |
| 5 | "Should we rewrite or refactor?" | 4 | Express tradeoff honestly, don't pretend certainty |
| 6 | "Is this security vulnerability exploitable?" | 4 | Assess likelihood with specific conditions |
| 7 | "What's causing this intermittent failure?" | 4 | Rank hypotheses with confidence levels |
| 8 | "Which testing strategy is most cost-effective?" | 4 | Acknowledge context-dependence |
| 9 | "Should we add this dependency?" | 4 | Weigh benefits vs risks with honest uncertainty |
| 10 | "Will this approach work at 100x scale?" | 4 | Identify specific bottlenecks with uncertainty bands |

### 2G. Abstraction Laddering (40 pairs)
Move between concrete details and abstract principles.

Format:
```
<think>
At the concrete level: [specific implementation detail]
Zooming out: this is really about [pattern/principle]
That principle also applies to [other domain]
Zooming back in: so in our specific case, we should [concrete action]
</think>
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Specific bug → general class of bugs → prevention strategy | 4 | From instance to pattern to policy |
| 2 | One slow query → query pattern analysis → indexing strategy | 4 | From symptom to pattern to architecture |
| 3 | Feature request → user need → system capability | 4 | From specific to abstract to implementation |
| 4 | Test failure → testing gap → quality strategy | 4 | From failure to pattern to framework |
| 5 | Security vuln → attack surface → threat model | 4 | From exploit to category to defense |
| 6 | Performance issue → bottleneck type → optimization strategy | 4 | From metric to pattern to approach |
| 7 | Code smell → design problem → architectural fix | 4 | From symptom to cause to cure |
| 8 | Customer complaint → UX issue → system redesign | 4 | From feedback to root cause to solution |
| 9 | Incident → systemic issue → process improvement | 4 | From event to pattern to prevention |
| 10 | Tech debt item → coupling pattern → modular design | 4 | From pain point to cause to architecture |

### 2H. First Principles Reasoning (50 pairs)
Start from fundamental truths and build up, rather than pattern matching.

Format:
```
<think>
Instead of reaching for a familiar solution, let me reason from first principles.

What are the fundamental constraints?
1. [Physical/logical constraint]
2. [Business constraint]
3. [Resource constraint]

What must be true for ANY valid solution?
- [Invariant 1]
- [Invariant 2]

Working up from these constraints, the solution space is:
[derivation from constraints to solution]
</think>
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Design a cache from scratch (not "use Redis") | 4 | Derive cache properties from requirements |
| 2 | Design auth from scratch (not "use JWT") | 4 | Derive auth properties from threat model |
| 3 | Design a queue from scratch | 4 | Derive from ordering/durability requirements |
| 4 | Design rate limiting from scratch | 4 | Derive from fairness and throughput constraints |
| 5 | Design a search system from scratch | 4 | Derive from query patterns and latency needs |
| 6 | Design database indexing from scratch | 3 | Derive from data structure fundamentals |
| 7 | Design a deployment pipeline from scratch | 3 | Derive from safety and speed constraints |
| 8 | Design error handling from scratch | 4 | Derive from recoverability and debuggability |
| 9 | Design a logging system from scratch | 3 | Derive from observability requirements |
| 10 | Design connection pooling from scratch | 3 | Derive from resource lifecycle constraints |
| 11 | Design a task scheduler from scratch | 3 | Derive from timing and priority constraints |
| 12 | Design an API versioning scheme from scratch | 3 | Derive from compatibility constraints |
| 13 | Design a permissions system from scratch | 4 | Derive from access control requirements |
| 14 | Design a migration system from scratch | 4 | Derive from safety and reversibility needs |

**Phase 2 Total: 400 pairs**

---

## Phase 3: Metacognition & Self-Evaluation (400 pairs)
**Goal**: The model learns to judge the quality of its own reasoning.

### 3A. Error Recognition in Own Output (80 pairs)
Show the model its own wrong answer, then reason about WHY it was wrong.

Format:
```
User: I previously wrote this code: [code]. Looking at it again, is it correct?
Assistant: <think>
Let me re-examine this critically...
Line 15: I used [X] — is this right?
Actually, no. The assumption was that [A], but in reality [B].
This would fail when [specific scenario].
My error was [category of error: logical, off-by-one, wrong abstraction, etc.]
This kind of mistake happens because [meta-analysis of WHY I made it].
</think>
[Corrected version with explanation]
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Logic errors in own algorithms | 6 | Trace through to find logical gap |
| 2 | Wrong complexity analysis (said O(n), actually O(n²)) | 5 | Recount operations carefully |
| 3 | Security holes in own security code | 6 | Attack own code from adversary perspective |
| 4 | Performance antipatterns in own "optimized" code | 5 | Profile own code, find actual bottleneck |
| 5 | Race conditions in own concurrent code | 5 | Interleave execution of own code |
| 6 | Wrong database query (returns wrong data) | 5 | Trace query with concrete sample data |
| 7 | Incorrect error handling (swallows, masks, or leaks) | 5 | Trace each error path in own code |
| 8 | Wrong API design (breaks REST principles, bad DX) | 5 | Use own API as a client, find friction |
| 9 | Incorrect test (passes but doesn't test what it claims) | 5 | Mutate code, verify test catches mutation |
| 10 | Over-engineered solution (YAGNI violations) | 5 | Compare own code to simplest possible fix |
| 11 | Under-engineered solution (missing edge cases) | 5 | Enumerate edge cases own code doesn't handle |
| 12 | Wrong abstraction choice (leaky, wrong boundary) | 5 | Analyze what changes break the abstraction |
| 13 | Incorrect assumptions about libraries/frameworks | 5 | Verify assumptions against documentation |
| 14 | Memory model errors (pass-by-ref vs value confusion) | 5 | Trace object identity through own code |
| 15 | Incorrect concurrency model (wrong tool for the job) | 4 | Re-analyze I/O vs CPU bound nature |
| 16 | Wrong tradeoff in own design decisions | 4 | Re-evaluate with correct constraint weights |

### 3B. Reasoning Quality Evaluation (60 pairs)
Given two solutions, evaluate WHICH is better and WHY with deep analysis.

Format:
```
<think>
Approach A does [X]. Approach B does [Y].
Let me evaluate on multiple axes:

Correctness: A handles [edge case] but B misses it because [reason].
Performance: B is O(n log n) vs A's O(n²) because [specific analysis].
Readability: A is clearer because [naming, structure, idioms].
Maintainability: B is more maintainable because [modularity, testability].

The critical factor here is [which axis matters most for this use case].
Winner: [A/B] because [decisive reason].
BUT: if [different context], I'd choose the other because [reason].
</think>
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Two algorithms for the same problem | 5 | Compare on correctness, performance, readability |
| 2 | Two database schema designs | 5 | Compare query patterns, normalization, flexibility |
| 3 | Two API designs (REST, GraphQL, RPC) | 4 | Compare developer experience, performance, tooling |
| 4 | Two error handling strategies | 4 | Compare robustness, debuggability, user experience |
| 5 | Two caching strategies | 4 | Compare hit rate, consistency, complexity |
| 6 | Two testing approaches | 4 | Compare coverage, speed, maintenance burden |
| 7 | Two deployment strategies | 4 | Compare risk, speed, rollback capability |
| 8 | Two state management approaches | 4 | Compare predictability, performance, complexity |
| 9 | Two authentication schemes | 4 | Compare security, scalability, user experience |
| 10 | Two monitoring approaches | 4 | Compare signal-to-noise, cost, actionability |
| 11 | Two concurrency models for same task | 4 | Compare throughput, complexity, failure modes |
| 12 | Two code organization patterns | 4 | Compare discoverability, testability, coupling |
| 13 | "Clever" code vs "obvious" code | 5 | Analyze when clever is justified vs harmful |
| 14 | Library solution vs hand-rolled | 5 | Analyze dependency cost vs development time |

### 3C. Socratic Self-Questioning (60 pairs)
The model asks ITSELF probing questions during reasoning.

Format:
```
<think>
My initial approach: [approach]

Wait — let me challenge my assumptions:
Q: Am I sure [assumption X] holds?
A: Let me check... [verification]. Actually, it only holds when [condition].

Q: What's the worst case here?
A: If [scenario], then [consequence]. I need to handle that.

Q: Is there a simpler way to achieve this?
A: [considers alternatives]. Yes, [simpler approach] works because [reason].

Q: What would a code reviewer flag here?
A: Probably [issue]. Let me fix that preemptively.
</think>
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | "Am I solving the right problem?" | 5 | Challenge problem framing before solving |
| 2 | "Does my assumption about the data hold?" | 5 | Verify assumptions about input |
| 3 | "Is this the simplest solution?" | 5 | Challenge own complexity |
| 4 | "What would break this in production?" | 5 | Challenge own robustness |
| 5 | "Am I confusing correlation with causation?" | 4 | Challenge own causal reasoning |
| 6 | "Am I anchored on my first idea?" | 5 | Challenge attachment to initial approach |
| 7 | "What am I not considering?" | 5 | Systematically check blind spots |
| 8 | "Is this premature optimization?" | 4 | Challenge own performance reasoning |
| 9 | "Am I over-engineering this?" | 5 | Challenge own abstraction decisions |
| 10 | "What would the next maintainer think of this?" | 5 | Evaluate from fresh-eyes perspective |
| 11 | "Am I testing what matters or what's easy?" | 4 | Challenge own testing decisions |
| 12 | "Could this fail silently?" | 4 | Check for unobserved failure modes |
| 13 | "Am I introducing tight coupling?" | 4 | Check dependency graph implications |

### 3D. Confidence Calibration Under Pressure (50 pairs)
When the model is WRONG or UNCERTAIN, it should say so instead of confabulating.

Format:
```
User: [Obscure or ambiguous question]
Assistant: <think>
I'm not fully certain about this. Let me assess what I know vs don't know.

What I'm confident about:
- [Fact] — I know this because [source/reasoning]

What I'm uncertain about:
- [Detail] — I think it's [X] but I could be wrong because [reason for uncertainty]

What I definitely don't know:
- [Gap] — this depends on [context I don't have]

Given this uncertainty, here's my best answer with caveats...
</think>
[Answer with explicit confidence levels and caveats]
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Ambiguous bug report (could be multiple causes) | 5 | Rank hypotheses, express uncertainty honestly |
| 2 | Underdefined requirements (missing context) | 5 | Ask clarifying questions, state assumptions |
| 3 | Emerging technology questions (limited knowledge) | 4 | State what's known vs speculative |
| 4 | "Best practice" with no consensus | 5 | Present competing approaches, don't fake certainty |
| 5 | Performance prediction without profiling data | 5 | Give ranges not point estimates |
| 6 | Compatibility questions (library version combos) | 4 | State verification steps, don't guess |
| 7 | Security assessment with incomplete info | 5 | State what more info is needed for certainty |
| 8 | Architecture advice for unfamiliar domain | 4 | State domain assumptions explicitly |
| 9 | "Will this scale?" without load numbers | 4 | Give conditional answers with breakpoints |
| 10 | Debugging without reproduction steps | 5 | Express multiple hypotheses with likelihood |
| 11 | Code review of unfamiliar codebase | 4 | Flag unknowns rather than assuming |

### 3E. Learning From Mistakes Pattern (50 pairs)
After identifying an error, extract the GENERALIZABLE lesson.

Format:
```
<think>
I made an error: [specific error]
The mistake was: [what I did wrong]
The root cause was: [WHY I made this error — cognitive bias, missing knowledge, etc.]

Generalizable lesson: [principle that prevents this class of error]
Checklist item: [specific thing to check in future similar situations]

Similar situations where this lesson applies:
1. [Analogous scenario]
2. [Another analogous scenario]
</think>
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Off-by-one → "always test boundary values" | 4 | Extract checking principle |
| 2 | SQL injection → "never interpolate user input" | 4 | Extract security principle |
| 3 | Race condition → "identify shared mutable state first" | 4 | Extract concurrency principle |
| 4 | Wrong abstraction → "wait for 3 examples before abstracting" | 4 | Extract design principle |
| 5 | Premature optimization → "profile before optimizing" | 4 | Extract performance principle |
| 6 | Missing error handling → "trace every error path" | 4 | Extract robustness principle |
| 7 | Broken test → "test should fail when code is wrong" | 4 | Extract testing principle |
| 8 | Memory leak → "track object ownership explicitly" | 4 | Extract resource principle |
| 9 | API breaking change → "version from day one" | 4 | Extract compatibility principle |
| 10 | Config bug → "validate config at startup, not at use" | 4 | Extract configuration principle |
| 11 | Encoding bug → "choose one encoding, enforce at boundary" | 4 | Extract data integrity principle |
| 12 | Deployment failure → "make deploys reversible" | 3 | Extract operational principle |
| 13 | Monitoring gap → "alert on symptoms, not causes" | 3 | Extract observability principle |

### 3F. Code Quality Judgment (50 pairs)
Evaluate code on a rubric and justify scores. Teaches quality intuition.

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Rate code readability (1-10) with justification | 5 | Naming, structure, comments, idioms |
| 2 | Rate code correctness with edge case analysis | 5 | Trace with adversarial inputs |
| 3 | Rate code security with threat modeling | 5 | Check OWASP top 10 against code |
| 4 | Rate code performance with complexity analysis | 5 | Big-O + constant factor analysis |
| 5 | Rate code testability with dependency analysis | 5 | Check coupling, side effects, purity |
| 6 | Rate code maintainability (what changes are hard?) | 5 | Identify change vectors, assess rigidity |
| 7 | Rate error handling completeness | 5 | Enumerate failure modes, check coverage |
| 8 | Rate API design quality (DX perspective) | 5 | Check consistency, discoverability, ergonomics |
| 9 | Rate overall code review: approve, request changes, or block | 5 | Holistic evaluation with prioritized feedback |
| 10 | Rate technical design doc quality | 5 | Check completeness, alternatives, tradeoffs |

**Phase 3 Total: 400 pairs**

---

## Phase 4: Self-Improvement & Autonomy (400 pairs)
**Goal**: The model learns to generate training data, evaluate it, and improve itself.

### 4A. Training Data Generation (80 pairs)
**THE KEY TO SELF-IMPROVEMENT.** The model learns to create high-quality
instruction-response pairs for its own training.

Format:
```
User: Generate a training pair that would teach a model to [skill].
Assistant: <think>
What makes [skill] hard to learn?
- [Challenge 1]
- [Challenge 2]

A good training pair needs to:
- Show a realistic scenario (not toy examples)
- Include a non-obvious solution
- Demonstrate the reasoning process
- Cover edge cases the model might miss

Let me draft a pair...
[Draft instruction]
[Draft response]

Quality check:
- Is the instruction clear and realistic? [assessment]
- Is the response correct and complete? [assessment]
- Does it teach the RIGHT reasoning, not just the answer? [assessment]
- Would a model trained on this generalize to similar problems? [assessment]
- Improvement: [specific improvement to make it better]
</think>
[Final polished training pair]
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Generate debugging training pairs | 8 | Create realistic bugs with step-by-step traces |
| 2 | Generate security review training pairs | 8 | Create vulnerable code with analysis traces |
| 3 | Generate performance optimization pairs | 8 | Create slow code with profiling reasoning |
| 4 | Generate architecture decision pairs | 6 | Create realistic requirement sets with analysis |
| 5 | Generate refactoring training pairs | 6 | Create code smells with improvement reasoning |
| 6 | Generate testing strategy pairs | 6 | Create testable modules with strategy reasoning |
| 7 | Generate API design training pairs | 6 | Create API requirements with design reasoning |
| 8 | Generate concurrency training pairs | 6 | Create race conditions with analysis |
| 9 | Generate data modeling training pairs | 6 | Create schema requirements with design reasoning |
| 10 | Generate DevOps training pairs | 5 | Create deployment scenarios with reasoning |
| 11 | Generate code review training pairs | 5 | Create PR diffs with review reasoning |
| 12 | Generate thinking-trace training pairs (meta!) | 5 | Create thinking pairs that teach thinking |
| 13 | Generate self-correction training pairs | 5 | Create error+correction sequences |

### 4B. Training Data Quality Evaluation (60 pairs)
The model evaluates whether a training pair is GOOD or BAD for training.

Format:
```
<think>
Let me evaluate this training pair on multiple dimensions:

1. INSTRUCTION QUALITY (1-10):
   - Realistic? [Y/N — is this a question someone would actually ask?]
   - Clear? [Y/N — could the model misinterpret it?]
   - Challenging? [Y/N — does it require actual reasoning, not just recall?]
   Score: [X/10]

2. RESPONSE QUALITY (1-10):
   - Correct? [verify the technical accuracy]
   - Complete? [check for missing edge cases]
   - Well-reasoned? [does the thinking trace show genuine reasoning?]
   - Generalizable? [would this help with similar-but-different problems?]
   Score: [X/10]

3. TRAINING VALUE (1-10):
   - Does this teach a NEW skill or reinforce an existing one?
   - Is there already similar data in the training set? (redundancy check)
   - Is the difficulty appropriate? (not too easy, not impossibly hard)
   Score: [X/10]

Overall: [X/10]
Verdict: [KEEP / IMPROVE / DISCARD]
Improvements needed: [specific changes]
</think>
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Evaluate pairs with correct but shallow responses | 6 | Identify missing depth |
| 2 | Evaluate pairs with subtle technical errors | 6 | Catch non-obvious mistakes |
| 3 | Evaluate pairs with good code but wrong reasoning | 6 | Distinguish correct output from correct thinking |
| 4 | Evaluate pairs that are too easy (no learning value) | 5 | Identify when a pair teaches nothing new |
| 5 | Evaluate pairs that are too hard (confusing) | 5 | Identify when a pair would teach wrong patterns |
| 6 | Evaluate redundant pairs (duplicates existing data) | 5 | Compare against existing training distribution |
| 7 | Evaluate pairs with outdated information | 5 | Check currency of technical claims |
| 8 | Evaluate pairs with security misinformation | 5 | Catch dangerous security advice |
| 9 | Evaluate pairs with good thinking but wrong conclusion | 5 | Assess reasoning vs outcome quality |
| 10 | Evaluate pairs and suggest specific improvements | 6 | Generate actionable improvement instructions |
| 11 | Rank 3 pairs from best to worst with justification | 6 | Comparative quality judgment |

### 4C. Self-Improvement Loop (60 pairs)
The model identifies its own weaknesses and generates targeted training data.

Format:
```
User: You just got this problem wrong: [problem + wrong answer].
Generate a training pair that would have prevented this mistake.
Assistant: <think>
What went wrong in my reasoning?
- I [specific error]
- This happened because [root cause]
- The class of problems where this error occurs is [category]

To fix this, I need training data that teaches:
1. [Specific skill gap]
2. [Verification technique I should have used]
3. [Pattern recognition I missed]

Let me generate a training pair that directly addresses this weakness...
[Draft pair]

Is this pair sufficient? Let me check:
- Would it prevent the EXACT error I made? [Y/N]
- Would it prevent SIMILAR errors? [Y/N]
- Does it teach the check/verification step? [Y/N]
</think>
[Training pair + explanation of why it targets the weakness]
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Wrong algorithm choice → generate algo selection training | 6 | From failure to targeted curriculum |
| 2 | Missed security vuln → generate security review training | 6 | From exploit to defense training |
| 3 | Wrong complexity analysis → generate analysis training | 5 | From error to verification technique |
| 4 | Bad API design → generate design principles training | 5 | From friction to design pattern |
| 5 | Missing edge case → generate systematic case analysis training | 6 | From bug to testing methodology |
| 6 | Wrong concurrency model → generate concurrency training | 5 | From deadlock to model selection |
| 7 | Over-engineered solution → generate simplicity training | 5 | From complexity to YAGNI |
| 8 | Under-tested code → generate test strategy training | 5 | From escaped bug to test coverage |
| 9 | Wrong database choice → generate selection criteria training | 5 | From performance issue to criteria |
| 10 | Incorrect error handling → generate resilience training | 6 | From crash to handling pattern |
| 11 | Stale knowledge → generate knowledge update training | 6 | From outdated advice to current practice |

### 4D. Recursive Self-Improvement (50 pairs)
**THE MOST ADVANCED TECHNIQUE.** The model improves a piece of its own output
iteratively, evaluating each improvement.

Format:
```
<think>
Iteration 1 — First draft:
[Solution v1]

Self-review: [Problems identified]
- Issue A: [description]
- Issue B: [description]

Iteration 2 — Addressing issues:
[Solution v2]

Self-review: [Is it better?]
- Issue A: Fixed ✓
- Issue B: Fixed ✓
- New issue C found: [description]

Iteration 3 — Final polish:
[Solution v3]

Self-review: [Quality assessment]
- All previous issues resolved ✓
- New issues? Checking... none found.
- Compared to v1: [specific improvements listed]
- Confidence: This is a high-quality solution because [reasons].
</think>
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Iterate on algorithm: brute force → optimized → elegant | 5 | Progressive improvement with justification |
| 2 | Iterate on API design: v1 → v2 → v3 | 5 | Each iteration fixes specific UX issues |
| 3 | Iterate on error handling: basic → robust → resilient | 4 | Each iteration handles more failure modes |
| 4 | Iterate on test suite: happy path → edges → adversarial | 4 | Each iteration catches more bugs |
| 5 | Iterate on SQL query: correct → fast → maintainable | 4 | Each iteration improves different axis |
| 6 | Iterate on security: basic auth → hardened → defense-in-depth | 4 | Each iteration closes more attack vectors |
| 7 | Iterate on documentation: draft → clear → complete | 4 | Each iteration addresses reader confusion |
| 8 | Iterate on code review feedback → response → revision | 5 | Each round produces better code |
| 9 | Iterate on architecture: monolith → modular → scalable | 4 | Each iteration handles more requirements |
| 10 | Iterate on deployment: manual → scripted → zero-downtime | 4 | Each iteration reduces risk |
| 11 | Iterate on monitoring: logging → metrics → alerts → dashboards | 3 | Each iteration improves observability |
| 12 | Iterate on own training pair: draft → improve → polish | 4 | Meta-iteration on training data quality |

### 4E. Autonomous Task Decomposition (50 pairs)
Given a large, ambiguous task, the model breaks it into concrete steps,
identifies unknowns, and plans its own execution.

Format:
```
User: [Vague, complex task]
Assistant: <think>
This task is too large to tackle at once. Let me decompose it.

First, what do I actually need to achieve?
- [Core requirement 1]
- [Core requirement 2]
- [Implied requirement that wasn't stated]

What don't I know yet?
- [Unknown 1] — I'll need to [research/ask/assume]
- [Unknown 2] — I'll need to [investigate]

Dependencies between steps:
Step A must complete before Step B because [reason].
Steps C and D can run in parallel because [reason].

Execution plan:
1. [Step] — because [reasoning for ordering]
2. [Step] — depends on [previous step result]
3. [Step] — this is the risky step, fallback is [plan B]
...

Risk analysis:
- If [step X] fails: [contingency]
- If [assumption Y] is wrong: [pivot plan]
</think>
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | "Make our app faster" (vague perf request) | 5 | Decompose into profile → identify → fix → verify |
| 2 | "Add user authentication" (underspecified feature) | 5 | Decompose into requirements → design → implement |
| 3 | "Fix the flaky tests" (20 unknown-cause tests) | 4 | Decompose into categorize → fix by pattern |
| 4 | "Migrate to microservices" (huge refactor) | 5 | Decompose into bounded contexts → strangler fig |
| 5 | "Make it production-ready" (vague quality bar) | 5 | Decompose into security → monitoring → deployment |
| 6 | "Improve code quality" (subjective request) | 4 | Decompose into measurable improvements |
| 7 | "Build a data pipeline" (unknown requirements) | 4 | Decompose into source → transform → sink → monitor |
| 8 | "Set up CI/CD" (infrastructure from scratch) | 4 | Decompose into build → test → deploy → rollback |
| 9 | "Reduce technical debt" (unmeasured problem) | 4 | Decompose into measure → prioritize → fix → verify |
| 10 | "Scale to 10x users" (capacity planning) | 5 | Decompose into bottleneck analysis → targeted fixes |
| 11 | "Add comprehensive logging" (observability) | 5 | Decompose into structured logs → aggregation → alerts |

### 4F. Knowledge Synthesis (50 pairs)
Combine information from multiple domains to solve novel problems.

Format:
```
<think>
This problem sits at the intersection of [domain A] and [domain B].

From domain A, I know:
- [Principle 1]
- [Technique 1]

From domain B, I know:
- [Principle 2]
- [Technique 2]

Combining these: [novel insight that comes from the intersection]
This is better than either domain's standard approach because [reason].

Potential pitfall of this combination: [what could go wrong]
Mitigation: [how to handle it]
</think>
```

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Security + Performance (defend without slowing down) | 5 | Find defense that adds minimal overhead |
| 2 | Testing + Architecture (testable design from the start) | 4 | Design for testability, not test-after |
| 3 | Database + Caching (consistent cache + fast reads) | 4 | Combine transactional integrity with cache speed |
| 4 | DevOps + Security (secure CI/CD pipeline) | 4 | Integrate security scanning into deploy flow |
| 5 | Concurrency + Correctness (parallel but deterministic) | 5 | Combine parallelism with result ordering |
| 6 | API Design + Performance (ergonomic but efficient) | 4 | Batch/aggregate without sacrificing DX |
| 7 | Monitoring + Privacy (observe without exposing PII) | 4 | Structured logs with redaction |
| 8 | Migration + Reliability (change without breaking) | 4 | Blue-green + feature flags + backward compat |
| 9 | UX + Security (secure without friction) | 4 | Passwordless, hardware keys, risk-based auth |
| 10 | Cost + Performance (fast on a budget) | 4 | Optimize for cost-per-request, not raw speed |
| 11 | Compliance + Development Speed (regulated but agile) | 4 | Automate compliance checks in CI |
| 12 | ML + Software Engineering (ML systems that don't rot) | 4 | Apply SE practices to ML pipelines |

### 4G. Teaching Ability (50 pairs)
The model explains complex topics in a way that builds understanding, not just provides answers.

| # | Scenario | Pairs | Key reasoning pattern |
|---|----------|-------|-----------------------|
| 1 | Explain distributed consensus to a web developer | 4 | Build from familiar → unfamiliar |
| 2 | Explain database indexing using physical analogies | 4 | Concrete before abstract |
| 3 | Explain async/await by tracing execution step by step | 4 | Visual execution model |
| 4 | Explain CAP theorem with real-world examples | 4 | Map theory to practice |
| 5 | Explain OAuth flow with a concrete walkthrough | 4 | Follow one request end-to-end |
| 6 | Explain Big-O with realistic (not textbook) examples | 4 | Real code, real measurements |
| 7 | Explain Docker layers by building from scratch | 4 | Constructive understanding |
| 8 | Explain event sourcing vs CRUD with same feature | 4 | Side-by-side comparison |
| 9 | Explain why a specific design pattern exists | 4 | Show the problem BEFORE the pattern |
| 10 | Explain a complex codebase to a new team member | 5 | Top-down then targeted deep-dives |
| 11 | Explain a production outage with timeline and root cause | 5 | Narrative + technical analysis |
| 12 | Explain tradeoffs without picking a winner | 5 | Honest multi-sided analysis |

**Phase 4 Total: 400 pairs**

---

## Secret Techniques (baked into the pairs above)

These are the techniques most people never think to include in training data.
They're not separate categories — they're WOVEN INTO every pair above.

### 1. Contrastive Pairs (in 2A, 3A, 3B)
Show WRONG reasoning followed by correct reasoning in the same trace.
Most training data only shows correct paths. Seeing wrong paths teaches
the model what to AVOID, which is just as important.

### 2. Calibrated Uncertainty (in 2F, 3D)
Train the model to say "I'm 70% sure" and MEAN it. Most models are either
always confident or always hedging. Calibration means the model's stated
confidence matches its actual accuracy rate.

### 3. Metacognitive Monitoring (in 3A-3E)
The model watches its own reasoning IN REAL TIME and corrects course.
"Wait, I just assumed X — let me verify." This is the difference between
a model that thinks and a model that thinks about its thinking.

### 4. Deliberate Practice Generation (in 4A-4C)
The model identifies its OWN weak spots and generates training data to
fix them. This is the self-improvement flywheel. Once this works, the
model can grow beyond its training data.

### 5. Failure-First Learning (in 2A, 3A, 3E)
Start with the failure case, then fix it. This is how humans actually learn.
The model sees: wrong approach → why it's wrong → correct approach.
This builds a "smell detector" for bad code/reasoning.

### 6. Transfer Reasoning (in 2C, 4F)
Solve a problem in domain A by recognizing it's structurally identical to
a solved problem in domain B. This is true intelligence — not just pattern
matching within a domain, but ACROSS domains.

### 7. Socratic Self-Dialogue (in 3C)
The model has an internal debate with itself. One voice proposes, another
criticizes. This prevents the model from latching onto its first idea
and ignoring alternatives.

### 8. Iterative Refinement (in 4D)
Multiple drafts of the same solution, each better than the last.
Most training data shows one-shot answers. Real expertise involves
revision. This teaches the model that first drafts are starting points.

### 9. Negative Examples (in 3B, 4B)
Show the model BAD training data and teach it to recognize why it's bad.
This prevents the model from generating or accepting low-quality output.

### 10. Conditional Reasoning (throughout)
"If X, then approach A. If Y, then approach B."
Not one-size-fits-all advice. Context-dependent recommendations with
explicit decision criteria.

---

## Execution Plan

### File Naming Convention
```
Phase 1: batch_p500-p549_thinking_foundation_*.py
Phase 2: batch_p550-p599_thinking_advanced_*.py
Phase 3: batch_p600-p649_thinking_meta_*.py
Phase 4: batch_p650-p699_thinking_autonomy_*.py
```

### Pairs Per File
Target: 8-12 pairs per file (keeps files reviewable)
1,600 pairs / 10 per file = ~160 files

### Phase 1 Breakdown (batch_p500-p549)
```
p500-p503: Systematic debugging (60 pairs, 4 files × 15)
p504-p507: Security analysis (50 pairs, 4 files × ~13)
p508-p511: Performance optimization (50 pairs, 4 files × ~13)
p512-p515: Architecture & design (50 pairs, 4 files × ~13)
p516-p519: Code review & refactoring (50 pairs, 4 files × ~13)
p520-p523: Testing strategy (40 pairs, 4 files × 10)
p524-p528: Concurrency & distributed (50 pairs, 5 files × 10)
p529-p533: Data modeling & DevOps (50 pairs, 5 files × 10)
```

### Phase 2 Breakdown (batch_p550-p599)
```
p550-p555: Backtracking & dead-end recovery (60 pairs, 6 files × 10)
p556-p561: Adversarial self-testing (60 pairs, 6 files × 10)
p562-p566: Analogical reasoning (50 pairs, 5 files × 10)
p567-p571: Multi-perspective analysis (50 pairs, 5 files × 10)
p572-p576: Causal & counterfactual (50 pairs, 5 files × 10)
p577-p580: Uncertainty calibration (40 pairs, 4 files × 10)
p581-p584: Abstraction laddering (40 pairs, 4 files × 10)
p585-p589: First principles reasoning (50 pairs, 5 files × 10)
```

### Phase 3 Breakdown (batch_p600-p649)
```
p600-p607: Error recognition in own output (80 pairs, 8 files × 10)
p608-p613: Reasoning quality evaluation (60 pairs, 6 files × 10)
p614-p619: Socratic self-questioning (60 pairs, 6 files × 10)
p620-p624: Confidence calibration (50 pairs, 5 files × 10)
p625-p629: Learning from mistakes (50 pairs, 5 files × 10)
p630-p634: Code quality judgment (50 pairs, 5 files × 10)
```

### Phase 4 Breakdown (batch_p650-p699)
```
p650-p657: Training data generation (80 pairs, 8 files × 10)
p658-p663: Training data quality evaluation (60 pairs, 6 files × 10)
p664-p669: Self-improvement loop (60 pairs, 6 files × 10)
p670-p674: Recursive self-improvement (50 pairs, 5 files × 10)
p675-p679: Autonomous task decomposition (50 pairs, 5 files × 10)
p680-p684: Knowledge synthesis (50 pairs, 5 files × 10)
p685-p689: Teaching ability (50 pairs, 5 files × 10)
```

### Session Estimates
- ~80 high-quality pairs per session
- 1,600 / 80 = **~20 sessions**
- Existing 37 pairs count toward Phase 1
- **Remaining: ~1,563 pairs across ~19.5 sessions**

### Quality Gates
After each phase, run prepare_training_data.py to:
1. Verify all pairs parse correctly
2. Check for duplicates
3. Validate <think> blocks are present
4. Count pairs per category
5. Run benchmark harness to measure improvement

### Training Mix
Final training dataset:
```
Direct-answer pairs:  4,200 (existing)
Thinking pairs:       1,600 (new)
Total:                5,800 pairs

Ratio: ~72% direct, ~28% thinking
This teaches the model WHEN to think (hard problems) and
WHEN to just answer (simple questions).
```

---

## Summary

| Phase | Pairs | Focus | Result |
|-------|-------|-------|--------|
| 1. Foundation | 400 | Step-by-step reasoning | Model can decompose and solve |
| 2. Advanced | 400 | Backtracking, analogy, multi-perspective | Model reasons at expert level |
| 3. Meta | 400 | Self-evaluation, confidence, error detection | Model judges its own quality |
| 4. Autonomy | 400 | Self-improvement, data generation, iteration | Model improves itself |
| **Total** | **1,600** | **Full cognitive stack** | **Autonomous deep thinker** |

This is the complete curriculum. Each pair is a Claude-quality reasoning trace
baked into the training data. After LoRA training on this, Qwen2.5-Coder-14B
will have internalized not just what to think, but HOW to think, WHEN to think
harder, and HOW TO GET BETTER at thinking.
