"""Phase 4E: Self-Improvement — Autonomous Improvement (Part 8)

Autonomously updating knowledge of best practices — detecting when
established recommendations need revision and staying current.
"""

PAIRS = [
    (
        "thinking/auto-autonomous-detect-stale-practices",
        r'''How do I detect when a best practice I've been recommending has become outdated or been superseded by a better approach?''',
        r'''<think>
Best practices evolve constantly. What was recommended 3 years ago may be actively discouraged today. The challenge is detecting staleness in my own knowledge without external prompts.

**Signals that a practice may be stale:**
1. The ecosystem has released major new versions
2. The community has shifted terminology or approaches
3. New tools have emerged that make the old approach unnecessary
4. The original problem the practice solved no longer exists
5. Security or performance research has invalidated the approach

**Strategy:** Build internal checks that flag potentially stale recommendations.
</think>

**Detecting Stale Best Practices**

**The staleness detection framework:**

| Signal | Example | Action |
|--------|---------|--------|
| Major version released | React 18 → 19 | Review all React recommendations |
| New language features | Python 3.10+ match statement | Consider if old patterns should use it |
| Community consensus shift | "microservices for everything" → "right-size your architecture" | Update default recommendations |
| Security disclosure | Log4j vulnerability | Review all logging recommendations |
| Better tool emerged | Webpack → Vite | Evaluate if recommendation should change |

**The practice audit checklist:**
```
For each best practice you recommend, periodically verify:
□ When did I learn this? (>2 years ago → needs verification)
□ What version was current then? (major versions since → review)
□ Is the official documentation still recommending this?
□ Are tech leads at top companies still using this approach?
□ Has a simpler alternative emerged?
```

**Concrete examples of stale practices:**

**JavaScript (stale → current):**
```
2018: "Use Enzyme for React testing"
2024: "Use React Testing Library"
Why: Testing Library tests behavior, not implementation

2019: "Use Create React App for new projects"
2024: "Use Vite or Next.js"
Why: CRA is unmaintained, Vite is faster

2020: "Use Moment.js for dates"
2024: "Use date-fns or Temporal API"
Why: Moment.js is in maintenance mode, too large
```

**Python (stale → current):**
```
2019: "Use virtualenv for environments"
2024: "Use uv or poetry"
Why: uv is dramatically faster, poetry handles deps better

2018: "Use requirements.txt for dependencies"
2024: "Use pyproject.toml"
Why: PEP 621 standardized project metadata

2020: "Use Flask for APIs"
2024: "Consider FastAPI for new projects"
Why: FastAPI has async support, auto-docs, type validation
```

**The continuous update protocol:**
```
1. Track which recommendations you make most frequently
2. For each one, note the ecosystem version when you learned it
3. When a major version ships, audit related recommendations
4. When recommending anything, add a mental check:
   "Is this still the current best practice, or is this what
    I learned 3 years ago?"
5. When uncertain, say so: "As of [version], the recommendation
   is X. Check if this has changed in newer versions."
```

**The honesty principle:**
```
When you're not sure if a practice is current:

DON'T: Recommend it confidently anyway
DO: "The standard approach has been X. However, the ecosystem
    moves fast — verify this is still recommended for [version]."

Being honest about uncertainty is better than being confidently wrong.
```

**The meta-principle:** The longer you've held a belief about best practices, the more likely it needs updating. Treat long-held confidence as a prompt to re-verify, not as evidence of correctness. The tech world moves too fast for any recommendation to stay current indefinitely.'''
    ),
    (
        "thinking/auto-autonomous-track-ecosystem-evolution",
        r'''How do I keep track of how different technology ecosystems are evolving so I can update my recommendations proactively rather than reactively?''',
        r'''<think>
Tracking ecosystem evolution requires a systematic approach. You can't follow everything, so you need to prioritize which ecosystems to track and what signals to watch for.

**Key ecosystems to track (by impact):**
1. Programming languages (Python, JavaScript/TypeScript, Rust, Go)
2. Frontend frameworks (React, Vue, Svelte)
3. Backend frameworks (FastAPI, Express, Django)
4. Infrastructure (Docker, Kubernetes, cloud services)
5. Databases (PostgreSQL, Redis, MongoDB)
6. DevOps/CI-CD tools

**Signals of ecosystem shifts:**
- Official deprecation announcements
- Major conference talks shifting focus
- GitHub stars/activity trends
- New defaults in create/init tools
- Changes in job listings
</think>

**Tracking Ecosystem Evolution Systematically**

**The signal hierarchy (most reliable to least):**

| Signal | Reliability | Example |
|--------|-------------|---------|
| Official deprecation notice | Very high | "CRA is no longer recommended" |
| Official migration guide released | High | React class → hooks migration guide |
| Default changed in scaffolding tools | High | `npm create vite` replaces CRA |
| Major companies publicly migrating | Medium-high | "We moved from X to Y" blog posts |
| Conference talks shifting focus | Medium | "All talks are about Y now, none about X" |
| GitHub star velocity | Medium | New project gaining stars faster |
| Community sentiment on social media | Low-medium | "Everyone is using Y now" (hype vs. reality) |

**What to track per ecosystem:**

**For programming languages:**
```
Track:
  - New major version releases and feature highlights
  - What the new features REPLACE (old patterns to stop recommending)
  - Performance improvements that change optimization advice
  - New standard library additions that obsolete third-party libraries

Example — Python:
  3.10: match/case → can replace long if/elif chains
  3.11: TaskGroups → can replace manual asyncio.gather
  3.12: Better error messages → changes how you explain debugging
  3.13: Free-threaded mode → changes concurrency advice
```

**For frameworks:**
```
Track:
  - Major version breaking changes
  - New recommended patterns (official docs changes)
  - Ecosystem tool changes (bundler, test runner, etc.)
  - Community migration patterns

Example — React:
  16.8: Hooks → class components deprecated in practice
  18: Concurrent features → changes how you explain rendering
  19: Server Components → changes architecture recommendations
```

**The quarterly review protocol:**
```
Every 3 months, for your top 5 ecosystems:
1. Check: Any major version released?
2. Check: Any official deprecations?
3. Check: Any new "recommended" approaches in docs?
4. Check: Any significant new tools/libraries?
5. Update your internal recommendation set accordingly
```

**The "still recommended?" quick check:**
```
Before recommending any tool or pattern:
1. Check the project's README/docs — is it actively maintained?
2. Check the last release date — more than 1 year ago is a warning
3. Check if the official getting-started guide still uses this approach
4. Check if there's a migration guide TO something newer
```

**The meta-principle:** Technology ecosystems are living things — they evolve continuously. Your recommendations should have an expiration date in your mind. What you recommend today should be re-evaluated in 6-12 months. Build the re-evaluation into your process, not as an afterthought.'''
    ),
    (
        "thinking/auto-autonomous-update-security-practices",
        r'''Security best practices change rapidly. How do I ensure my security recommendations stay current and don't recommend practices that have been broken or deprecated?''',
        r'''<think>
Security is the highest-stakes area for stale practices. Recommending an outdated security practice can directly lead to breaches. Unlike other domains where outdated practices are merely suboptimal, outdated security practices are dangerous.

**Critical areas where security practices change:**
1. Authentication (password hashing, token management, MFA)
2. Encryption (algorithm strength, protocol versions)
3. Dependency management (vulnerability scanning)
4. API security (rate limiting, input validation, CORS)
5. Infrastructure (container security, secrets management)

**The stakes:** A developer who follows your security advice and gets breached because you recommended SHA-256 for passwords instead of bcrypt has been actively harmed.
</think>

**Keeping Security Recommendations Current**

**The security recommendation tiers:**

**CRITICAL — verify before every recommendation:**
```
Password hashing:
  WRONG (2015): SHA-256 with salt
  WRONG (2018): bcrypt with cost factor 10
  CURRENT: bcrypt with cost factor 12+, or argon2id
  WHY: Computing power increases; cost factors must increase

Token generation:
  WRONG: random.random() or Math.random()
  CURRENT: secrets.token_urlsafe() or crypto.randomBytes()
  WHY: Non-cryptographic RNGs are predictable

TLS versions:
  WRONG: TLS 1.0/1.1 (deprecated)
  CURRENT: TLS 1.2 minimum, prefer TLS 1.3
  WHY: Known vulnerabilities in older versions

JWT handling:
  WRONG: Algorithm in token header (alg: none attack)
  CURRENT: Server-side algorithm enforcement, short expiry, rotation
  WHY: Multiple attack vectors discovered since JWTs became popular
```

**HIGH — verify quarterly:**
```
Dependency scanning:
  Keep up with: CVE databases, Dependabot/Snyk alerts
  Recommendation: Automated scanning in CI/CD

CORS configuration:
  WRONG: Access-Control-Allow-Origin: *
  CURRENT: Explicit allowlist of origins

Content Security Policy:
  Evolving: New directives added regularly
  Recommendation: Always include, review headers annually

HTTP headers:
  Minimum set changes over time
  Currently: Strict-Transport-Security, Content-Security-Policy,
  X-Content-Type-Options, X-Frame-Options, Referrer-Policy
```

**The security staleness detection checklist:**
```
Before recommending any security practice:
□ Is the algorithm/protocol still considered secure? (check NIST, OWASP)
□ Has the minimum key length / cost factor increased?
□ Has this library had recent CVEs?
□ Is there a newer version of the standard (e.g., OAuth 2.0 → 2.1)?
□ Would a security auditor flag this in a penetration test?
```

**Known deprecation timeline to track:**
```
Deprecated:
  - MD5 for any security purpose
  - SHA-1 for any security purpose
  - TLS 1.0 and 1.1
  - 1024-bit RSA keys
  - Basic Auth over HTTP
  - JWT "alg: none"

Increasingly deprecated:
  - 2048-bit RSA (moving to 3072+ or Ed25519)
  - bcrypt cost 10 (moving to 12+)
  - Cookie-based sessions without SameSite

Watch list (may be deprecated soon):
  - SHA-256 for password hashing (argon2id preferred)
  - PKCS#1 v1.5 padding (use OAEP)
```

**The OWASP check:**
```
OWASP Top 10 updates every few years:
  2017 → 2021 → next update coming
Each update changes what the industry considers the biggest risks.
When the list updates, review ALL your security recommendations
against the new top 10.
```

**The meta-principle:** In security, "it used to be secure" means "it's not secure now." Never recommend a security practice without verifying it's current. When uncertain, recommend the strongest option and let the user downgrade if they have constraints. It's better to over-secure than under-secure.'''
    ),
    (
        "thinking/auto-autonomous-update-architecture-patterns",
        r'''Architecture patterns and best practices evolve more slowly than library choices, but they still change. How do I keep my architecture recommendations current?''',
        r'''<think>
Architecture patterns do evolve, but on a longer timescale (5-10 years vs. 1-2 years for libraries). The changes are also less binary — old patterns don't become "wrong," they become "less appropriate for modern contexts."

**Recent shifts in architecture thinking:**
1. Monolith → Microservices → "Right-sized services" / Modular monolith
2. REST → GraphQL → "Use the right one for the context"
3. Server-rendered → SPA → Server components / Islands architecture
4. Kubernetes everywhere → "Do you actually need K8s?"
5. NoSQL for everything → "PostgreSQL can do most things"
6. Event-driven everything → "Synchronous is fine for most use cases"

**The pattern:** Hype cycle → overcorrection → pragmatic middle ground
</think>

**Keeping Architecture Recommendations Current**

**The architecture hype cycle to track:**
```
1. New pattern emerges (excitement)
2. "Use it for everything!" (peak hype)
3. Failures emerge at scale (disillusionment)
4. Nuanced understanding develops (pragmatic adoption)
5. Pattern finds its appropriate niche (maturity)

Your recommendations should match phase 4-5, not phase 1-2.
```

**Current architecture landscape (as of 2025-2026):**

| Topic | Hype phase recommendation | Mature recommendation |
|-------|--------------------------|----------------------|
| Service architecture | "Always microservices" | "Start monolith, extract services when needed" |
| API style | "GraphQL replaces REST" | "REST for most, GraphQL for complex client needs" |
| Frontend rendering | "SPA everything" | "Server-rendered by default, SPA when needed" |
| Database choice | "NoSQL for scale" | "PostgreSQL handles most needs; specialize when you must" |
| Container orchestration | "Kubernetes for everything" | "K8s for large teams; simpler options for small teams" |
| Event-driven | "Events everywhere" | "Synchronous by default; events for decoupling" |

**The "context before pattern" principle:**
```
OLD approach: "The best pattern is X"
CURRENT approach: "For your context, the best pattern is X because..."

Architecture recommendations must be context-dependent:
  - Team size (3 vs. 300 engineers)
  - Scale requirements (1K vs. 1M requests/sec)
  - Operational maturity (startup vs. established ops team)
  - Domain complexity (CRUD app vs. financial trading)
```

**Architecture recommendation self-check:**
```
Before recommending an architecture pattern:
1. "Am I recommending this because it's right for this context,
    or because it's what I know?"
2. "What's the SIMPLEST architecture that would work here?"
3. "Would this team be able to OPERATE this architecture?"
4. "Is this pattern still recommended by practitioners
    who have used it at scale, or has the community moved on?"
```

**The "simplest thing that works" filter:**
```
Always start with the simplest viable architecture:
  1. Monolith with good module boundaries
  2. Add a cache if performance demands
  3. Add a message queue if you need async processing
  4. Extract a service only when a module has different scaling needs
  5. Add Kubernetes only when you have multiple services to orchestrate

Each step should be driven by a REAL problem, not anticipated problems.
```

**Tracking architecture evolution:**
```
Sources of truth (reliable):
  - Post-mortems from companies that adopted the pattern
  - ThoughtWorks Technology Radar (updated quarterly)
  - Conference talks that discuss FAILURES, not just successes
  - Architecture Decision Records from large open-source projects

Sources of hype (unreliable):
  - Vendor blog posts (selling their product)
  - "How we scaled to X" posts (survivorship bias)
  - Conference talks from companies promoting their tools
```

**The meta-principle:** Architecture patterns don't go from "right" to "wrong" — they go from "universally recommended" to "appropriate in specific contexts." Your job is not to recommend the newest pattern but to match the pattern to the context. The newest pattern is often overhyped; the oldest pattern is often underappreciated.'''
    ),
    (
        "thinking/auto-autonomous-version-recommendations",
        r'''How should I version my recommendations so users know when my advice was current and can verify if it still applies?''',
        r'''<think>
Versioning recommendations is a meta-practice that protects both the advisor and the user. It explicitly acknowledges that advice has a shelf life and gives the user tools to verify currency.

**Why version recommendations:**
1. Technology changes faster than any knowledge base can update
2. Users may read advice months or years after it was written
3. It builds trust by being transparent about limitations
4. It teaches users to check currency of any advice they receive

**What to version:**
- Language/framework version the advice targets
- Date of the recommendation
- Key dependencies and their versions
- Conditions under which the advice might change
</think>

**Versioning Recommendations for Longevity**

**The versioned recommendation format:**
```
UNVERSIONED (dangerous):
  "Use bcrypt for password hashing."

VERSIONED (safe):
  "Use bcrypt with cost factor 12 for password hashing
   (as of Python 3.11, bcrypt 4.x, 2025 security standards).
   Re-evaluate: if argon2id becomes the OWASP default, switch."
```

**What to version in every recommendation:**

**1. Runtime/Language version:**
```
"In Python 3.10+, use match/case for complex branching.
 For Python 3.9 and earlier, use if/elif chains."
```

**2. Framework version:**
```
"In React 18+, use useTransition for non-urgent updates.
 This API doesn't exist in React 17."
```

**3. Library versions:**
```
"Install: pip install fastapi==0.109 uvicorn==0.27
 Note: FastAPI's API surface is still evolving;
 check release notes when upgrading."
```

**4. Date context:**
```
"As of 2025, the recommended approach for container
 orchestration on small teams is Docker Compose or
 a managed Kubernetes service (EKS, GKE). Self-hosted
 Kubernetes is typically not worth the overhead for
 teams under 20 engineers."
```

**The shelf-life labels:**
```
Label your recommendations by stability:

[STABLE] — Unlikely to change (fundamentals)
  "Use parameterized queries to prevent SQL injection."

[CURRENT] — Best practice today, may evolve
  "Use argon2id for password hashing with memory cost 64MB."

[EVOLVING] — Actively changing, verify before using
  "Server Components in React 19 — check docs for latest patterns."

[EXPERIMENTAL] — Not yet established, use at your own risk
  "The Temporal API may replace date libraries in browsers."
```

**The "check if still valid" instructions:**
```
Include with recommendations that may change:

"To verify this is still current:
 1. Check [official docs URL] for the latest recommendation
 2. Search 'is [tool/practice] still recommended [current year]'
 3. Check the project's GitHub for recent major releases"
```

**The auto-versioning habit:**
```
For every recommendation, mentally attach:
  - Target version: "This is for [language/framework version]"
  - Valid until: "This is likely valid until [next major version / event]"
  - Verification: "Check [source] to verify"

Even if you don't always write these out, thinking them
prevents you from giving outdated advice confidently.
```

**The meta-principle:** All recommendations are implicitly versioned by when you learned them. Making that versioning explicit protects the user from following outdated advice and protects you from giving it. Transparency about the shelf-life of your knowledge is a feature, not a weakness.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
