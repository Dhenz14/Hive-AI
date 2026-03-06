"""Phase 2D: Advanced Reasoning — Multi-Perspective Analysis (Part 8/8)"""

PAIRS = [
    (
        "thinking/multiperspective-monorepo-vs-polyrepo",
        "Our company has 12 microservices across 3 teams. We're debating whether to move everything into a monorepo or keep separate repos. Each side has strong opinions. Can you break this down?",
        r'''<think>
Monorepo vs polyrepo — this is a genuinely divisive topic. Let me think through multiple perspectives.

**Team Lead perspective (values velocity):**
Monorepo: "One PR can update the API contract AND all consumers. No more coordinating releases across repos."
Polyrepo: "Each team moves at their own pace. No waiting for other teams' CI to pass."

**DevOps/Platform Engineer perspective (values infrastructure):**
Monorepo: "One CI/CD pipeline to maintain, one build system, unified tooling."
Polyrepo: "Smaller repos clone/build faster. CI only runs for what changed."
But monorepo needs: build tool that understands what changed (Bazel, Nx, Turborepo).

**Junior Developer perspective (values simplicity):**
Monorepo: "I can find any code by searching one repo. Easy to understand the whole system."
Polyrepo: "The repo is small and focused. I only need to understand my service."

**Security/Compliance perspective:**
Monorepo: "Everyone has access to everything. Hard to restrict who sees billing code vs user code."
Polyrepo: "Fine-grained repo permissions. Billing team can't accidentally access PII code."

**Scale perspective:**
Monorepo: At Google/Meta scale, custom tooling makes it work. At 12 services, standard Git handles it.
Polyrepo: At 12 services, 12 repos is manageable. At 200 services, 200 repos becomes repo sprawl.

For THIS company specifically: 12 services, 3 teams.
- Small enough that monorepo complexity (custom build tools) might not be worth it
- But small enough that polyrepo overhead (12 repos, 12 CI configs) is also manageable
- The deciding factor is probably: do teams share code? Do API changes need coordinating?
</think>

This needs multiple perspectives — each stakeholder has legitimate concerns.

## The Perspectives

### Team Lead View: "How fast can we ship?"

```
MONOREPO wins for cross-cutting changes:
  Change shared API contract → update all consumers → ONE pull request
  Before: "Please update your service to use the new endpoint"
          → 4 PRs across 4 repos → coordinating merge order → 3 days

  After:  One PR changes the contract + all consumers
          → Reviewed together → merged atomically → 2 hours

POLYREPO wins for independent work:
  Team A ships 5 times/day, Team B ships weekly.
  In monorepo: Team A's broken test blocks Team B's deploy.
  In polyrepo: complete independence.
```

### DevOps/Platform View: "How much infrastructure do I maintain?"

```
MONOREPO:
  ✓ One CI/CD pipeline configuration
  ✓ One set of linting rules, one test framework
  ✓ Dependency versions aligned across all services
  ✗ CI must be smart about what to build (Bazel/Nx/Turborepo)
  ✗ Git clone takes longer as repo grows
  ✗ One flaky test can block all deploys

POLYREPO:
  ✓ Small repos, fast clones, fast CI
  ✓ Independent deploy pipelines
  ✗ 12 repos × (CI config + linting + formatting + Dockerfile) = 12 copies
  ✗ "Works on service A but uses different linting rules than service B"
  ✗ Dependency version drift (service A on React 17, service B on React 19)
```

### Security/Compliance View: "Who has access to what?"

```
MONOREPO:
  ✗ Everyone with repo access sees ALL code
  ✗ Billing code, PII handling, internal tools — all visible
  ✗ GitHub CODEOWNERS helps but doesn't restrict READ access
  ✗ Compliance audits for "who accessed payment code" are harder

POLYREPO:
  ✓ Fine-grained repo permissions per team
  ✓ Payment service repo: only payment team has access
  ✓ Easier compliance: "only these 4 people can access PCI-scoped code"
  ✓ Audit trail per repository
```

### Developer Experience View: "How easy is my daily work?"

```
MONOREPO:
  ✓ One git clone, one IDE workspace, one search
  ✓ "How does service X call service Y?" → just read the code
  ✓ Shared libraries updated in place (no publish/version/install cycle)
  ✗ IDE can be slow with 12 services loaded
  ✗ Git log is noisy (changes from all teams)

POLYREPO:
  ✓ Small, focused workspace — IDE is fast
  ✓ Git log only shows relevant changes
  ✓ Clear ownership boundaries
  ✗ "Where is that shared utility?" → which repo?
  ✗ Shared library updates: change lib → publish → update 12 package.jsons
```

## Decision Framework for Your Situation

```
12 services, 3 teams — key questions:

1. "How often do changes span multiple services?"
   Frequently (weekly+) → MONOREPO (atomic cross-cutting changes)
   Rarely (monthly)     → POLYREPO (independent work matters more)

2. "Do services share significant code?"
   Yes (shared models, utils, proto files) → MONOREPO
   No (services are truly independent)     → POLYREPO

3. "Do you have DevOps capacity for build tooling?"
   Yes (can set up Nx/Turborepo/Bazel)     → MONOREPO viable
   No (team is stretched thin)             → POLYREPO (simpler)

4. "Are there compliance/security constraints?"
   Yes (PCI, HIPAA, SOC2 scope boundaries) → POLYREPO (access control)
   No (internal tooling, all same trust)    → Either works

5. "How aligned are your teams' tech stacks?"
   Same language/framework (all Node.js)   → MONOREPO (shared tooling)
   Mixed (Go + Python + TypeScript)        → POLYREPO (different toolchains)
```

## The Middle Ground (Often Overlooked)

```
You don't have to choose one extreme:

OPTION: Grouped repos (2-4 repos, not 1 or 12)
  Repo 1: Platform services (auth, users, notifications)  — Team 1
  Repo 2: Commerce services (orders, payments, shipping)  — Team 2
  Repo 3: Content services (catalog, search, reviews)     — Team 3
  Repo 4: Shared libraries (contracts, utils, proto files)

  Benefits:
    - Cross-cutting changes within a domain are atomic
    - Teams own their repos
    - Shared libraries in one place
    - Not too many repos to manage
    - Compliance boundaries can align with repo boundaries

This is what most companies at your scale actually do.
```

## My Take

```
For 12 services, 3 teams:
  - If teams share significant code and frequently change contracts:
    → Monorepo with Nx/Turborepo (worth the tooling investment)

  - If teams work independently with stable APIs between services:
    → Polyrepo or grouped repos (simpler, less tooling)

  - If you're not sure yet:
    → Start with grouped repos (1 per team + 1 shared)
    → Migrate to monorepo if you hit coordination pain
    → Migrating repos together is easier than splitting them apart
```'''
    ),
    (
        "thinking/multiperspective-when-to-rewrite-vs-refactor",
        "We have a 5-year-old Django app that's becoming hard to maintain. The codebase is ~50K lines with minimal tests. Some people want to rewrite in a modern stack, others say we should incrementally refactor. What's the right call?",
        r'''<think>
The classic rewrite vs refactor debate. Joel Spolsky wrote about this — "Things You Should Never Do" — the Netscape cautionary tale. But sometimes rewrites ARE the right choice. Let me think through multiple perspectives.

**The "Rewrite" camp:**
- "The code is spaghetti, we'd be faster starting fresh"
- "We want to use a modern stack (FastAPI, Next.js, etc.)"
- "The architecture doesn't support our current needs"
- Emotional: developers are frustrated with the old code

**The "Refactor" camp:**
- "A rewrite takes 2-3x longer than estimated, always"
- "The old code has 5 years of bug fixes and edge cases baked in"
- "We can't stop shipping features for 6-12 months"
- "Second system effect: the rewrite will be over-engineered"

**CTO/Business perspective:**
- Rewrite = months of no new features = lost revenue/competitive advantage
- Refactor = slow but continuous feature delivery
- BUT: if the old code actively blocks important features, the cost of NOT rewriting grows

**Developer perspective:**
- Rewrite: exciting, fun, learn new tech, clean slate
- Refactor: tedious, dealing with legacy mess, feels like failure
- Warning: developer excitement about rewrites is often emotional, not rational

**User perspective:**
- Don't care about the tech stack
- Care about: features ship, bugs get fixed, app doesn't break
- Rewrite risk: "feature parity" takes forever, users get frustrated
- Refactor risk: slow improvement, some bugs persist

**Pragmatic perspective (the Strangler Fig pattern):**
You don't have to choose one extreme. Build new features in a new service/module, gradually migrate old features, eventually the old code withers away.

For THIS specific case:
- 50K lines: medium-sized, not enormous
- Minimal tests: risky to refactor (no safety net) but also risky to rewrite (might miss behaviors)
- 5 years old: not ancient, Django is still actively maintained
- "Hard to maintain": is it the code or the architecture?

I'd lean toward the Strangler Fig approach — rewrite incrementally rather than big-bang.
</think>

Both camps have valid points. Let me break down the perspectives, then give you the path that usually works.

## The "Rewrite Everything" Perspective

```
Arguments FOR rewrite:
  ✓ Clean architecture from day one
  ✓ Modern tooling, better developer experience
  ✓ Fix fundamental architecture problems (not just surface code)
  ✓ Opportunity to design for current scale, not 2021 scale

The hidden costs they're underestimating:
  ✗ "6 months" = actually 12-18 months (always)
  ✗ 5 years of subtle bug fixes and edge cases get lost
  ✗ Feature parity is a moving target (old app keeps getting feature requests)
  ✗ Two systems to maintain during transition
  ✗ "Second system effect" — tendency to over-engineer the rewrite
  ✗ Team morale drops at month 8 when it's "almost done" for the 3rd time
```

## The "Refactor Incrementally" Perspective

```
Arguments FOR refactoring:
  ✓ Continuous feature delivery — business doesn't stop
  ✓ Each refactor is low-risk (small changes, easy to revert)
  ✓ Preserves 5 years of institutional knowledge in the code
  ✓ Django is still modern and actively maintained

The hidden costs they're underestimating:
  ✗ "Minimal tests" means refactoring is dangerous (no safety net)
  ✗ If the ARCHITECTURE is wrong, refactoring code inside it doesn't help
  ✗ Polishing code in a bad structure is rearranging deck chairs
  ✗ Developer fatigue from working in legacy code they dislike
  ✗ Some problems (wrong database choice, wrong data model) can't be refactored
```

## The Right Question to Ask First

```
"Is the problem the CODE or the ARCHITECTURE?"

CODE problems (→ refactor):
  - Functions are too long
  - Naming is inconsistent
  - No separation of concerns
  - Business logic mixed with views
  - Duplicated code everywhere
  These can all be fixed incrementally without a rewrite.

ARCHITECTURE problems (→ consider rewrite/strangler):
  - Data model is fundamentally wrong
  - Sync processing where async is needed
  - Monolith can't scale for current traffic
  - Wrong technology for the problem domain
  These CANNOT be refactored away — they need structural change.

For your 50K-line Django app, ask:
  "If this code were perfectly clean but same architecture,
   would it work for our next 3 years?"
  Yes → refactor the code
  No  → the architecture needs to change
```

## The Path That Usually Works: Strangler Fig Pattern

```
Neither big-bang rewrite nor pure refactoring.
Instead: BUILD NEW NEXT TO OLD, MIGRATE GRADUALLY.

Phase 1: Stop the bleeding (2-4 weeks)
  ├── Add tests to the most critical paths
  │   (login, checkout, payment — even just integration tests)
  ├── Set up CI/CD if not present
  └── Document the current architecture (boxes and arrows)

Phase 2: New features in new code (ongoing)
  ├── New features get their own clean module/service
  │   (clean Django app, or a separate FastAPI service)
  ├── Route new endpoints to new code
  ├── Old code continues serving old endpoints
  └── No changes to old code except bug fixes

Phase 3: Migrate high-value paths (quarter by quarter)
  ├── Identify the most problematic/highest-traffic old modules
  ├── Rewrite ONE module at a time in the new architecture
  ├── Put a proxy/router in front to gradually shift traffic
  ├── Old: /api/orders → old Django view
  │   New: /api/orders → new service (once ready and tested)
  └── Verify with feature flags + A/B traffic splitting

Phase 4: Old code shrinks naturally
  ├── As modules are migrated, old code handles less and less
  ├── Eventually the old app serves nothing
  └── Decommission when last endpoint is migrated
```

```python
# Example: Strangler routing with Django + new FastAPI service
# nginx.conf or reverse proxy

# Old paths → old Django app (still running)
location /api/users/ {
    proxy_pass http://old-django:8000;
}
location /api/orders/ {
    proxy_pass http://old-django:8000;
}

# New feature → new service
location /api/recommendations/ {
    proxy_pass http://new-fastapi:8001;   # Brand new, clean code
}

# Migrated path → now served by new code
location /api/products/ {
    proxy_pass http://new-fastapi:8001;   # Was Django, now migrated
}
```

## Decision Matrix for Your Specific Case

```
50K lines Django, minimal tests, 5 years old:

                        Big Rewrite    Strangler Fig    Pure Refactor
──────────────────────────────────────────────────────────────────────
Time to first value     6-18 months    2-4 weeks        1-2 weeks
Risk level              Very high      Medium           Low
Feature delivery        STOPS          Continuous       Continuous
Addresses architecture  Yes            Yes              No
Developer satisfaction  High (at first) High             Low
Business disruption     Major          Minimal          None
Preserves edge cases    No             Gradually        Yes
```

## My Recommendation

```
1. DON'T do a big-bang rewrite (too risky for 50K LOC with no tests)
2. DON'T just refactor (if the architecture is the actual problem)
3. DO use Strangler Fig:
   - Stabilize the old app (add critical tests, 2 weeks)
   - Build new features in clean modules (immediate)
   - Migrate the most painful parts first (ongoing)
   - Old app shrinks over 6-12 months until it can be decommissioned

The Strangler Fig approach gives you the clean architecture
of a rewrite with the risk profile of incremental refactoring.
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
