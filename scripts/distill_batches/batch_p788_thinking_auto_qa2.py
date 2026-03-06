"""Phase 4F: Self-Improvement — Quality Assurance (Part 2)"""

PAIRS = [
    (
        "thinking/auto-qa-explanation-rubric",
        r'''Rate my explanation of OAuth 2.0 on: accuracy, completeness, clarity, and actionability.

My explanation: "OAuth 2.0 is a way to log into apps using Google or Facebook instead of creating a new password. When you click 'Login with Google', the app sends you to Google, you enter your password there, and Google tells the app you're legit. The app never sees your Google password. It's more secure because you only trust Google with your password, not every random app."''',
        r'''<think>
Let me evaluate this explanation against each rubric dimension.

ACCURACY (Is everything stated factually correct?):
- "a way to log into apps using Google or Facebook" — This conflates OAuth 2.0 with social login. OAuth 2.0 is an authorization framework, not an authentication protocol. Social login uses OpenID Connect (built on top of OAuth 2.0). The core purpose of OAuth 2.0 is delegated authorization (granting access to resources), not identity verification.
- "Google tells the app you're legit" — Misleading. In OAuth 2.0, Google issues an access token granting specific permissions. It doesn't verify identity (that's OIDC's ID token).
- "The app never sees your Google password" — Correct. This is a key benefit.
- "you only trust Google with your password" — Correct in the social login context.

So there's a fundamental accuracy issue: the explanation describes OIDC/social login and labels it OAuth 2.0.

COMPLETENESS (Does it cover the essential concepts?):
- Missing: authorization vs authentication distinction
- Missing: access tokens, scopes, grant types
- Missing: the concept of delegated authorization (e.g., letting an app access your Google Drive without giving it your password)
- Missing: refresh tokens, token expiry
- Missing: different flows (authorization code, implicit, client credentials)
- Only covers one use case (social login) out of many

CLARITY (Is it understandable to the target audience?):
- Very clear language, no jargon
- Good concrete example (Login with Google)
- Logical flow: problem → mechanism → benefit
- Accessible to beginners

ACTIONABILITY (Can someone do something with this knowledge?):
- No next steps provided
- No mention of how to implement it
- No links to specifications or libraries
- Someone reading this couldn't build an OAuth integration
</think>

**Explanation Quality Rubric — OAuth 2.0**

| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Accuracy | 4/10 | 35% | 1.4 |
| Completeness | 3/10 | 25% | 0.75 |
| Clarity | 9/10 | 25% | 2.25 |
| Actionability | 2/10 | 15% | 0.30 |
| **Overall** | | | **4.7/10** |

**Accuracy (4/10):**
The explanation contains a fundamental conceptual error: it describes OAuth 2.0 as an authentication mechanism ("a way to log into apps"). OAuth 2.0 is an *authorization* framework — it governs what an app can access on your behalf, not who you are. "Login with Google" actually uses OpenID Connect, which is a separate identity layer built on top of OAuth 2.0. The statement "Google tells the app you're legit" is specifically what OIDC does (via an ID token), not what bare OAuth 2.0 does. The correct OAuth 2.0 example would be: "You let a photo printing app access your Google Photos without giving it your Google password." The "never sees your password" part is accurate and well-stated.

**Completeness (3/10):**
Critical missing concepts: access tokens (the actual mechanism), scopes (what permissions are granted), grant types (authorization code, client credentials, etc.), the distinction between authorization and authentication, refresh tokens, and token expiry. The explanation covers only one surface-level use case out of a rich protocol family.

**Clarity (9/10):**
This is the explanation's strongest dimension. Language is plain and jargon-free. The concrete "Login with Google" example is relatable. The logical flow — why it exists, how it works, why it's better — is well-structured. A complete beginner would feel they understand the concept (even if what they understand is technically OIDC, not OAuth 2.0).

**Actionability (2/10):**
A developer reading this could not implement OAuth 2.0. No mention of libraries, endpoints, token handling, or security considerations. No next steps or resources provided.

**Recommended revision:** Correct the auth/authz distinction, add a true OAuth 2.0 example (delegated API access), briefly mention tokens and scopes, and link to a getting-started guide for implementation.'''
    ),
    (
        "thinking/auto-qa-guide-rubric",
        r'''Rate my debugging guide on: correctness of steps, coverage of common causes, and efficiency of process.

My guide for "Python app crashes with MemoryError":
1. Check if you have enough RAM — try adding more memory to your machine
2. Look at the error traceback to find which line caused it
3. Try using a smaller dataset
4. If it persists, rewrite the code in C++ which uses less memory
5. Consider upgrading to a server with more RAM''',
        r'''<think>
Let me evaluate this debugging guide against the rubric dimensions.

CORRECTNESS OF STEPS:
1. "Check if you have enough RAM" — Vague. How? No mention of monitoring tools (htop, task manager, psutil). "Adding more memory" is a hardware fix, not debugging.
2. "Look at the error traceback" — Correct and should actually be step 1, not step 2. This is the first thing you do.
3. "Try using a smaller dataset" — This is a workaround, not a fix. It doesn't identify the root cause.
4. "Rewrite in C++" — Wildly disproportionate. C++ can also have memory issues. This is not a debugging step at all. Also factually misleading — C++ doesn't inherently "use less memory" for the same algorithm; it just gives you manual control.
5. "Upgrade to a server with more RAM" — Again, throwing hardware at the problem without understanding the cause. If there's a memory leak, more RAM just delays the crash.

The steps are not WRONG per se (except #4 which is bad advice), but they're shallow — they treat symptoms, not causes.

COVERAGE OF COMMON CAUSES:
Missing:
- Memory leaks (circular references, unclosed resources)
- Loading entire file into memory instead of streaming/chunking
- Inefficient data structures (list of dicts vs. numpy array vs. pandas)
- Accumulating data in a loop without releasing
- Not using generators for large iterables
- Pandas/numpy operations that create copies
- 32-bit Python limitation (~2-4GB)

EFFICIENCY OF PROCESS:
The order is wrong. Step 2 (read the traceback) should be step 1. The guide jumps to expensive solutions (more RAM, rewrite in C++) before investigating the actual cause. An efficient debugging process would be: read traceback → profile memory → identify the bottleneck → fix the code → test.
</think>

**Debugging Guide Quality Rubric — MemoryError**

| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Correctness of steps | 3/10 | 40% | 1.2 |
| Coverage of common causes | 2/10 | 35% | 0.7 |
| Efficiency of process | 2/10 | 25% | 0.5 |
| **Overall** | | | **2.4/10** |

**Correctness of Steps (3/10):**
Step 2 (read the traceback) is correct but should be step 1. Step 3 (smaller dataset) is a valid workaround but not a diagnostic step. Step 4 ("rewrite in C++") is disproportionate and misleading — C++ doesn't inherently use less memory for the same algorithm, it simply provides manual memory management. Rewriting an entire application to debug a memory issue is never an appropriate debugging step. Step 5 (upgrade hardware) treats the symptom, not the cause — if there is a memory leak, more RAM merely delays the inevitable crash.

**Coverage of Common Causes (2/10):**
The guide misses virtually every common cause of Python MemoryError: memory leaks from circular references or unclosed resources, loading entire large files into memory instead of streaming, inefficient data structures (list of dicts using 10x the memory of a numpy array), accumulating results in a loop without releasing intermediate data, pandas operations that silently create full copies of DataFrames, and the 32-bit Python address space limitation.

**Efficiency of Process (2/10):**
The guide reaches for expensive solutions (hardware upgrades, language rewrites) before performing any actual diagnosis. An efficient debugging process should be:

```
1. Read the full traceback — identify the exact line and operation
2. Profile memory usage — use tracemalloc or memory_profiler
   python -m memory_profiler my_script.py
3. Identify the bottleneck — which object/operation consumes the most
4. Apply targeted fix:
   - Stream/chunk file I/O instead of loading entirely
   - Use generators instead of lists for large iterables
   - Use numpy/pandas vectorized ops instead of Python loops
   - Delete intermediate objects and call gc.collect()
   - Process data in batches
5. Verify — confirm peak memory dropped below available RAM
6. Only then consider infrastructure changes if the data truly
   requires more memory than the code can optimize away
```

**Verdict:** This guide would lead a developer to spend money on hardware or weeks rewriting in C++ when the actual fix is probably changing `data = file.readlines()` to `for line in file:`. Fundamentally ineffective.'''
    ),
    (
        "thinking/auto-qa-architecture-rubric",
        r'''Rate my architecture recommendation on: appropriateness for scale, operational complexity, and cost.

Context: A startup with 3 developers building an internal tool for 50 users.

My recommendation: "Use a microservices architecture with Kubernetes. Set up separate services for user management, authentication, the main business logic, notifications, and reporting. Use Kafka for async messaging between services, Redis for caching, PostgreSQL for the main database, and MongoDB for the reporting service. Deploy on AWS EKS with Terraform for infrastructure as code."''',
        r'''<think>
Let me evaluate this architecture recommendation against the rubric dimensions, keeping the context in mind: 3 developers, internal tool, 50 users.

APPROPRIATENESS FOR SCALE:
- 50 users is trivially small. A single Flask/Django app on a $5/month server handles this easily.
- Microservices with 5 services for 50 users is massive over-engineering.
- The architecture would handle millions of users, but that's not the requirement.
- If the startup grows, they can decompose later (monolith-first strategy).
- The recommendation solves a scaling problem that doesn't exist.

OPERATIONAL COMPLEXITY:
- Kubernetes: requires dedicated DevOps knowledge. With 3 developers, at least one person becomes the de facto Kubernetes admin, reducing development capacity by 33%.
- 5 microservices: each needs its own CI/CD pipeline, deployment config, health checks, logging, monitoring.
- Kafka: requires cluster management, topic management, consumer group coordination, monitoring for lag.
- Three different databases (PostgreSQL, MongoDB, Redis): three different backup strategies, three different failure modes, three different sets of expertise.
- Terraform: good practice but adds another tool to learn and maintain.
- Network complexity: service discovery, inter-service authentication, distributed tracing needed.
- Total operational burden is probably 10-20x what a monolith would require.

COST:
- AWS EKS: ~$73/month just for the control plane, before any nodes.
- Minimum 3 nodes for availability: ~$150-300/month for modest instances.
- Kafka (MSK): starts at ~$200/month.
- Multiple databases: RDS PostgreSQL (~$50+), DocumentDB/MongoDB (~$100+), ElastiCache Redis (~$50+).
- Conservative estimate: $500-1000/month minimum.
- A monolith on a single EC2 instance or Heroku: $20-50/month.
- For 50 users on an internal tool, spending $1000/month on infrastructure is hard to justify.

The recommendation is technically sound but catastrophically mismatched to the context.
</think>

**Architecture Recommendation Rubric**

| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Appropriateness for scale | 2/10 | 40% | 0.8 |
| Operational complexity | 1/10 | 35% | 0.35 |
| Cost efficiency | 2/10 | 25% | 0.5 |
| **Overall** | | | **1.65/10** |

**Appropriateness for Scale (2/10):**
This architecture is designed for thousands to millions of users. The actual requirement is 50 users on an internal tool. A single Django or Rails monolith on one server handles 50 users with resources to spare — likely using under 1% of a modest machine's capacity. The recommendation over-provisions by roughly two orders of magnitude. The "start with a monolith" principle exists precisely for this scenario: you can always decompose into services later when actual bottlenecks emerge. Premature decomposition creates distributed system problems without any of the benefits.

**Operational Complexity (1/10):**
This is the most damaging dimension. With 3 developers total:

- **Kubernetes** effectively requires a dedicated operator. That is 33% of the team doing infrastructure instead of product development.
- **5 microservices** means 5 CI/CD pipelines, 5 deployment configurations, inter-service communication patterns, distributed tracing, and service mesh considerations.
- **Kafka** is a complex distributed system requiring cluster management, partition tuning, consumer group coordination, and lag monitoring.
- **3 different databases** (PostgreSQL, MongoDB, Redis) mean three backup strategies, three failure domains, three monitoring setups, and three sets of expertise the team must maintain.

A realistic estimate: the team spends 60-70% of their time on infrastructure and 30-40% building the actual product.

**Cost Efficiency (2/10):**
Conservative monthly estimate: EKS control plane ($73) + 3 nodes ($200) + managed Kafka ($200) + RDS ($50) + DocumentDB ($100) + ElastiCache ($50) + data transfer + monitoring = **$700-1,000/month**. For 50 internal users, that is $14-20 per user per month on infrastructure alone. A single $20/month VPS running a monolith with PostgreSQL achieves the same outcome.

**Appropriate recommendation for this context:**

```
- Single Django/Rails/FastAPI monolith
- PostgreSQL (single database, handles all needs at this scale)
- Deploy on a single VM or PaaS (Heroku, Railway, Fly.io)
- Cost: $20-50/month
- Ops burden: near zero
- All 3 developers ship product features
```'''
    ),
    (
        "thinking/auto-qa-security-rubric",
        r'''Rate my security advice on: threat coverage, practicality, and priority ordering.

The user asked: "How do I secure my Node.js Express API?"

My advice:
1. Use HTTPS
2. Implement rate limiting
3. Validate all inputs
4. Use parameterized queries to prevent SQL injection
5. Set security headers (helmet.js)
6. Keep dependencies updated''',
        r'''<think>
Let me evaluate this security advice against the rubric.

THREAT COVERAGE:
What threats does the advice address?
1. HTTPS — eavesdropping, MITM attacks. Yes.
2. Rate limiting — DoS, brute force. Yes.
3. Input validation — injection, XSS (partially). Yes.
4. Parameterized queries — SQL injection specifically. Yes.
5. Security headers — XSS, clickjacking, MIME sniffing. Yes.
6. Dependency updates — known CVEs. Yes.

What threats are MISSING?
- Authentication and authorization (the biggest one! No mention of JWT security, session management, password hashing, OAuth)
- CORS configuration (critical for APIs)
- Error handling (stack traces leaking to users)
- Logging and monitoring (how do you detect an attack?)
- Secrets management (API keys, DB passwords)
- File upload security (if applicable)
- CSRF protection
- Request size limits
- JWT-specific issues (algorithm confusion, weak secrets)
- NoSQL injection (Express apps often use MongoDB, not SQL)

The advice covers network/transport and some application-layer threats but completely misses identity/access control.

PRACTICALITY:
- All items are implementable. Good.
- But they're vague. "Use HTTPS" — how? Let's Encrypt? Cloud load balancer? "Validate all inputs" — with what? Joi? express-validator? Zod?
- No code examples or library recommendations.
- A developer would need significant additional research to implement each point.

PRIORITY ORDERING:
- HTTPS first is reasonable as a foundation.
- But authentication/authorization is missing entirely, and it's typically the #1 priority.
- Input validation at #3 is too low — it should be #2 after authentication.
- The ordering is roughly sensible for what's included but the absence of auth makes the entire priority list incomplete.
</think>

**Security Advice Rubric — Node.js Express API**

| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Threat coverage | 4/10 | 40% | 1.6 |
| Practicality | 4/10 | 30% | 1.2 |
| Priority ordering | 5/10 | 30% | 1.5 |
| **Overall** | | | **4.3/10** |

**Threat Coverage (4/10):**
The advice addresses transport security, injection, DoS, and known vulnerabilities — good foundational items. However, it is missing the single most critical category for an API: **authentication and authorization**. An API without proper auth is an open door regardless of how well the other items are implemented. Specific omissions:

- **Authentication** — JWT handling, session management, password hashing (bcrypt), OAuth 2.0 flows
- **Authorization** — role-based access control, resource ownership checks
- **CORS configuration** — critical for APIs; misconfigured CORS negates many other protections
- **Secrets management** — API keys, database credentials, JWT secrets must not be in code
- **Error handling** — stack traces and internal details must not leak to clients
- **Logging and monitoring** — without audit logs, you cannot detect or investigate breaches
- **NoSQL injection** — Express apps commonly use MongoDB, where parameterized SQL queries are irrelevant; MongoDB operator injection (`$gt`, `$ne`) is the actual threat

**Practicality (4/10):**
Each item is stated as a principle without implementation guidance. "Validate all inputs" is correct but a developer needs to know: use `zod` or `joi` for schema validation, apply it as Express middleware, validate both body and query parameters. Similarly, "Use HTTPS" should specify: terminate TLS at a reverse proxy (nginx) or cloud load balancer, use Let's Encrypt for certificates, enforce HSTS. Without specifics, developers must do significant additional research.

**Priority Ordering (5/10):**
The ordering is reasonable for the items included, but the missing items would significantly change the priority list.

**Recommended priority order for Express API security:**

```
1. Authentication (JWT/session with bcrypt, secure token storage)
2. Authorization (middleware checking roles/ownership on every route)
3. HTTPS + HSTS (transport encryption)
4. Input validation (zod/joi middleware on all routes)
5. CORS (whitelist specific origins, not wildcard)
6. Security headers (helmet.js — one line of code, high value)
7. Rate limiting (express-rate-limit on auth endpoints especially)
8. Error handling (never expose stack traces; generic error responses)
9. Parameterized queries / NoSQL injection prevention
10. Dependency auditing (npm audit, Dependabot)
11. Logging and monitoring (winston + alerting on auth failures)
12. Secrets management (env vars via dotenv, never committed)
```'''
    ),
    (
        "thinking/auto-qa-optimization-rubric",
        r'''Rate my performance optimization advice on: measurement basis, expected impact, and implementation complexity.

Context: A Django web app with slow page loads (~8 second average).

My advice:
1. Switch from Django to FastAPI for better performance
2. Add Redis caching on all database queries
3. Use a CDN for static assets
4. Enable gzip compression
5. Rewrite the slowest views in Cython''',
        r'''<think>
Let me evaluate this optimization advice against the rubric.

MEASUREMENT BASIS (Is the advice grounded in profiling data?):
- None of the advice references any measurement or profiling. We don't know WHY pages take 8 seconds.
- Could be: N+1 queries, missing database indexes, unoptimized queries, large uncompressed responses, slow external API calls, template rendering, synchronous blocking, missing pagination.
- Without knowing the cause, the advice is guessing. The #1 rule of optimization is "measure first."
- "Switch frameworks" is the ultimate non-measurement-based advice — it assumes Django itself is the bottleneck, which is almost never true for an 8-second page load.

EXPECTED IMPACT:
1. Switch to FastAPI: Django's framework overhead is milliseconds, not seconds. An 8-second page load is caused by application code (queries, business logic), not framework overhead. Impact: negligible on the actual problem, possibly negative due to rewrite time.
2. Redis caching on ALL queries: Blanket caching without identifying which queries are slow is wasteful. It also introduces cache invalidation complexity. Some queries may run in 1ms and don't need caching. Impact: potentially high IF the slow queries are identified, but "cache everything" is a sledgehammer approach.
3. CDN for static assets: Good practice. If the 8 seconds includes loading CSS/JS/images, this helps. But if the 8 seconds is server response time (TTFB), CDN won't help at all. Impact: unknown without knowing the breakdown.
4. Gzip compression: If responses are large HTML/JSON, this reduces transfer time. Easy win. But if the 8 seconds is server processing, compression adds time (small). Impact: moderate if transfer is the bottleneck, negligible if processing is.
5. Cython for views: Views are I/O bound (database, templates, HTTP), not CPU bound. Cython optimizes CPU-bound Python. Rewriting I/O-bound code in Cython has essentially zero impact. Impact: near zero.

IMPLEMENTATION COMPLEXITY:
1. Framework switch: Months of work. Complete rewrite. Extremely high.
2. Redis on all queries: Moderate to high. Cache invalidation is notoriously hard.
3. CDN: Low. Configure in settings + DNS change.
4. Gzip: Trivial. One middleware setting.
5. Cython: High. Requires C compilation, different deployment, debugging difficulty.
</think>

**Optimization Advice Rubric — Django 8s Page Load**

| Dimension | Score | Weight | Weighted |
|-----------|-------|--------|----------|
| Measurement basis | 1/10 | 40% | 0.4 |
| Expected impact | 3/10 | 35% | 1.05 |
| Implementation complexity | 3/10 | 25% | 0.75 |
| **Overall** | | | **2.2/10** |

**Measurement Basis (1/10):**
This is the critical failure. None of the five recommendations references any profiling, measurement, or diagnosis. An 8-second page load is a symptom with dozens of possible causes — N+1 database queries, missing indexes, unoptimized ORM usage, slow external API calls, synchronous blocking, or enormous template context. Without running Django Debug Toolbar, `EXPLAIN ANALYZE` on queries, or application performance monitoring, every recommendation is a guess. The first rule of performance optimization is: **measure before you optimize**.

**Expected Impact (3/10):**

| Advice | Likely Impact | Why |
|--------|--------------|-----|
| Switch to FastAPI | Near zero | Django framework overhead is ~5-10ms. The remaining 7,990ms is your application code. FastAPI would have the same slow queries. |
| Redis on all queries | Unknown | Blanket caching without knowing which queries are slow wastes effort and creates cache invalidation bugs. |
| CDN for static assets | Low-moderate | Only helps if the 8s includes asset loading. If TTFB is 8s, CDN has zero effect. |
| Gzip compression | Low | Reduces transfer size but doesn't address server processing time. |
| Rewrite views in Cython | Near zero | Django views are I/O-bound (database, network), not CPU-bound. Cython only accelerates CPU computation. |

**Implementation Complexity (3/10):**
The advice recommends a framework rewrite (months of work) and Cython compilation (complex deployment) before trying trivially easy diagnostics. The effort-to-impact ratio is inverted.

**What the advice should be:**

```
Step 1: MEASURE (30 minutes)
  - Install django-debug-toolbar
  - Identify: How many queries per page? How long each?
  - Check: Is it TTFB or frontend loading?

Step 2: FIX THE TOP BOTTLENECK (usually one of these)
  - N+1 queries → add select_related()/prefetch_related()
  - Missing index → add db_index=True on filtered fields
  - Loading too much data → add pagination, defer() unused fields
  - Slow external API → make it async or cache the response

Step 3: VERIFY
  - Re-measure. Target: <500ms TTFB.
  - Repeat step 2 for next bottleneck if needed.
```

In most Django apps, steps 1-2 alone take the response from 8 seconds to under 500ms, with 1-2 hours of work and zero architectural changes.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
