"""Phase 2F: Advanced Reasoning — Uncertainty Calibration (Part 5/6)"""

PAIRS = [
    (
        "thinking/uncertainty-caching-strategy",
        "We need a caching strategy for our API. We have user profiles, product listings, search results, and real-time inventory counts. What should we cache and for how long?",
        r'''<think>
Caching strategy — different data types need different approaches. Let me reason through each with calibrated confidence.

**User profiles:**
- Change frequency: rarely (users update profile maybe once a month)
- Staleness tolerance: moderate (showing slightly outdated bio is acceptable)
- Read frequency: very high (profile loaded on every page)
- Cache recommendation: YES, cache aggressively
- TTL: 15-30 minutes
- Invalidation: write-through (update cache on profile save)
- Confidence: 90% — this is well-understood territory. Almost every application caches user profiles.

**Product listings:**
- Change frequency: low-medium (prices, descriptions change weekly)
- Staleness tolerance: depends on whether price is shown
  - Description/images: high tolerance → cache 1 hour
  - Price: low tolerance (wrong price is a liability) → cache 5 minutes or invalidate on change
- Read frequency: very high (browse, search results)
- Confidence: 80% — the price caching is the tricky part. If they have dynamic pricing (sales, A/B tests), my TTL recommendation might be too long. Need to know their pricing update frequency.

**Search results:**
- Change frequency: depends on index freshness
- Staleness tolerance: moderate (users won't notice if results are 5 minutes old)
- Read frequency: high, but highly variable (long tail of unique queries)
- Cache hit rate: potentially low for diverse queries
- Cache recommendation: YES, but only for popular queries
- TTL: 5-10 minutes
- Confidence: 70% — search caching effectiveness depends heavily on query distribution. If most queries are unique (long tail), cache hit rate will be low and the complexity isn't worth it. If 20% of queries cover 80% of traffic, caching is highly effective. I'd need to see query analytics.

**Real-time inventory counts:**
- Change frequency: continuously (every purchase changes it)
- Staleness tolerance: VERY LOW — showing "in stock" when it's out of stock is a terrible user experience (overselling)
- Read frequency: high
- Cache recommendation: DON'T cache traditionally. Use a different approach.
- Confidence: 85% — for high-volume items, even 30 seconds of caching is dangerous. However, for items with thousands in stock, brief caching (10s) might be acceptable. For items with <10 in stock, no caching. This threshold approach has moderate uncertainty.

**Uncertainty acknowledgments:**
- I don't know their traffic patterns — cache sizing depends on this
- I don't know if they have a CDN — CDN caching changes the strategy
- I don't know their read/write ratio — this affects invalidation strategy
- I don't know their infrastructure budget — Redis cluster vs single instance
</think>

Here's a caching strategy by data type, with my confidence levels for each recommendation:

## Cache Strategy Matrix

| Data Type | Cache? | TTL | Invalidation | Confidence |
|-----------|--------|-----|-------------|------------|
| User profiles | Yes, aggressively | 15-30 min | Write-through | **90%** |
| Product descriptions | Yes | 1 hour | Event-based | **85%** |
| Product prices | Carefully | 2-5 min | Write-through | **75%** |
| Search results | Popular queries only | 5-10 min | TTL-based | **70%** |
| Inventory counts | Don't cache traditionally | N/A | See below | **85%** |

## Implementation

```python
import redis
import json
from functools import wraps
from typing import Any

cache = redis.Redis(host="localhost", port=6379, db=0)


# --- Tier 1: Aggressive caching (user profiles) ---
# Confidence: 90% — well-proven pattern

def get_user_profile(user_id: int) -> dict:
    cache_key = f"user:{user_id}:profile"
    cached = cache.get(cache_key)
    if cached:
        return json.loads(cached)

    profile = db.get_user_profile(user_id)
    cache.setex(cache_key, 1800, json.dumps(profile))  # 30 min TTL
    return profile

def update_user_profile(user_id: int, data: dict):
    db.update_user_profile(user_id, data)
    # Write-through: update cache immediately
    cache.setex(f"user:{user_id}:profile", 1800, json.dumps(data))


# --- Tier 2: Moderate caching (product listings) ---
# Confidence: 80% — price TTL depends on your pricing update frequency

def get_product(product_id: int) -> dict:
    cache_key = f"product:{product_id}"
    cached = cache.get(cache_key)
    if cached:
        return json.loads(cached)

    product = db.get_product(product_id)
    # Cache for 5 minutes (price-safe TTL)
    # If you rarely change prices, you could go up to 30 minutes
    cache.setex(cache_key, 300, json.dumps(product))
    return product

def update_product(product_id: int, data: dict):
    db.update_product(product_id, data)
    cache.delete(f"product:{product_id}")  # Invalidate on write


# --- Tier 3: Selective caching (search results) ---
# Confidence: 70% — effectiveness depends on query distribution

def cached_search(query: str, page: int = 1) -> dict:
    # Only cache if query is "popular" (appears frequently)
    cache_key = f"search:{hash(query)}:page{page}"

    cached = cache.get(cache_key)
    if cached:
        return json.loads(cached)

    results = search_engine.search(query, page=page)

    # Only cache if this query has been seen before recently
    # (prevents cache pollution from unique queries)
    query_count_key = f"search_count:{hash(query)}"
    count = cache.incr(query_count_key)
    cache.expire(query_count_key, 3600)

    if count >= 3:  # Cache after 3rd occurrence
        cache.setex(cache_key, 600, json.dumps(results))  # 10 min TTL

    return results


# --- Tier 4: Real-time data (inventory) ---
# Confidence: 85% — DON'T use traditional cache-aside pattern

class InventoryCache:
    """
    Instead of caching counts, use Redis as the SOURCE OF TRUTH
    for hot inventory data, synced with the database.
    """

    def get_stock(self, product_id: int) -> int:
        """Read from Redis (always current)."""
        stock = cache.get(f"inventory:{product_id}")
        if stock is None:
            # Cold start: load from DB, set in Redis
            stock = db.get_stock_count(product_id)
            cache.set(f"inventory:{product_id}", stock)
        return int(stock)

    def decrement_stock(self, product_id: int) -> int:
        """Atomic decrement — prevents overselling."""
        key = f"inventory:{product_id}"
        new_count = cache.decr(key)

        if new_count < 0:
            # Oversold — revert and reject
            cache.incr(key)
            raise OutOfStockError(product_id)

        # Async sync to database (eventual consistency is fine here
        # because Redis is the source of truth for stock counts)
        sync_stock_to_db.delay(product_id, new_count)

        return new_count
```

## What I'm Less Sure About (70% Confidence)

**Search result caching** depends heavily on your query distribution:
- If 20% of queries cover 80% of traffic → caching is highly effective
- If queries are mostly unique (long tail) → cache hit rate will be <10%, not worth the complexity
- **Recommendation:** measure your cache hit rate for 1 week before committing to this approach

**Product price caching** depends on your update patterns:
- If prices change via admin panel (predictable) → write-through invalidation works perfectly
- If prices change via dynamic pricing algorithms (continuous) → you need shorter TTL or no caching
- If wrong prices have legal implications → err on the side of shorter TTL

## Infrastructure Sizing

```python
# Rough cache size estimates (verify with your data):
# - 10K user profiles × 2KB each = ~20MB
# - 50K products × 1KB each = ~50MB
# - Search results: depends on caching threshold
# - Total: likely <500MB — single Redis instance is fine

# When to upgrade to Redis Cluster:
# - Cache size > 10GB
# - Need > 100K operations/second
# - Need geographic distribution
```'''
    ),
    (
        "thinking/uncertainty-error-monitoring-tooling",
        "Should we use Sentry, Datadog, or build our own error monitoring? We're a startup with 12 developers, a Django backend, React frontend, and a growing number of microservices.",
        r'''<think>
Error monitoring tool selection for a startup. Let me reason through each option with calibrated confidence.

**Sentry:**
- Best-in-class error tracking and alerting
- Excellent Python/Django and React SDKs
- Source maps for frontend, stack traces with local variables
- Issue grouping (deduplication) is very good
- Performance monitoring added recently (but not its core strength)
- Pricing: free tier for low volume, paid plans scale with events
- Confidence in recommendation: 85% for error tracking specifically

**Datadog:**
- Full observability platform: APM, logs, metrics, error tracking
- Excellent for microservices (distributed tracing)
- Good Django/React integrations
- More expensive than Sentry for just error tracking
- But if you need APM + logs + metrics, it's one vendor
- Pricing: per-host pricing gets expensive fast, especially with microservices
- Confidence: 75% — depends heavily on budget and observability needs

**Build your own:**
- Almost certainly a bad idea at 12 developers
- Error tracking requires: collection, deduplication, alerting, source map handling, release tracking, assignment
- Building this in-house would take 2-3 months of senior developer time
- Maintaining it is ongoing work
- Confidence this is wrong: 95% — don't build observability infrastructure at a startup

Let me think about what combination makes sense...

**The nuance:** Sentry and Datadog aren't really competing — they solve different problems:
- Sentry: "What errors are happening? How do I fix them?"
- Datadog: "How is my system performing? Where are bottlenecks?"

At 12 developers with growing microservices, they probably need BOTH error tracking and APM/observability. But budget matters for a startup.

**My recommendation with confidence levels:**
- Use Sentry for error tracking (90% confident)
- Use a lighter observability tool for APM initially (Grafana Cloud or self-hosted Prometheus + Grafana) (75% confident)
- As microservices grow, evaluate Datadog for full observability (70% confident on timing)
- Do NOT build your own (95% confident)

**Uncertainty:**
- I don't know their budget constraints
- I don't know how many errors they generate (affects Sentry pricing)
- I don't know their microservice count (affects Datadog pricing)
- I don't know if they have existing monitoring (Prometheus, Grafana)
</think>

Short answer: **Sentry for error tracking** (90% confident), **don't build your own** (95% confident), and evaluate Datadog later when microservices complexity justifies the cost.

## Decision Matrix

| Criterion | Sentry | Datadog | Build Own |
|-----------|--------|---------|-----------|
| Error tracking quality | ★★★★★ | ★★★☆☆ | ★★☆☆☆ (after months) |
| Setup time | 30 minutes | 1-2 hours | 2-3 months |
| Django/React support | Excellent | Good | Whatever you build |
| Distributed tracing | Basic | Excellent | Don't even try |
| Monthly cost (12 devs) | ~$80-300 | ~$500-2000 | Developer time ($15K+) |
| Maintenance burden | Zero | Zero | Ongoing |

## What I'm Most Confident About (90-95%)

**Use Sentry for error tracking.** At your stage, this is the right call:

```python
# Django setup — 5 minutes
# pip install sentry-sdk
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.celery import CeleryIntegration

sentry_sdk.init(
    dsn=os.environ["SENTRY_DSN"],
    integrations=[DjangoIntegration(), CeleryIntegration()],
    traces_sample_rate=0.1,  # 10% of requests for performance monitoring
    environment=os.environ.get("APP_ENV", "development"),
    release=os.environ.get("GIT_SHA", "unknown"),

    # Filter noise
    before_send=lambda event, hint: (
        None if "DisallowedHost" in str(event.get("exception", "")) else event
    ),
)
```

```javascript
// React setup — 5 minutes
// npm install @sentry/react
import * as Sentry from "@sentry/react";

Sentry.init({
  dsn: process.env.REACT_APP_SENTRY_DSN,
  environment: process.env.REACT_APP_ENV,
  integrations: [Sentry.browserTracingIntegration()],
  tracesSampleRate: 0.1,
});
```

**Don't build your own** (95% confident). The opportunity cost of 2-3 developer-months at a 12-person startup is enormous. That's time not spent on your product.

## What I'm Moderately Confident About (70-75%)

**Start with free/cheap observability, upgrade to Datadog when needed:**

```yaml
# Phase 1 (now): Sentry + Prometheus/Grafana
# Cost: ~$100/month
# Covers: errors, basic metrics, basic alerting

# Phase 2 (when you hit 5+ microservices): Add Datadog APM
# Cost: ~$500-1500/month
# Trigger: when debugging cross-service issues takes > 1 hour
# because you can't trace requests across services

# Phase 3 (when you hit 15+ microservices): Full Datadog
# Cost: ~$2000-5000/month
# Trigger: when Prometheus query complexity outpaces your team's expertise
```

## Where I Have Less Certainty (What to Verify)

**Sentry pricing** (70% confident on cost estimate):
- Free tier: 5K errors/month — might be enough for early stage
- Team plan: $26/month for 50K errors — likely sufficient for 12 devs
- If you generate >100K errors/month, you have bigger problems than monitoring costs
- **Verify:** your current error volume before choosing a tier

**When to add Datadog** (65% confident):
- My "5+ microservices" threshold is a rough heuristic
- Some teams need distributed tracing at 3 services; others are fine at 10
- **Verify:** try debugging a cross-service issue. If it takes >2 hours, you need APM
- Alternative: Grafana Tempo (free, open-source distributed tracing) might delay the Datadog need

**Sentry's performance monitoring vs dedicated APM** (60% confident):
- Sentry added performance monitoring, but it's not as deep as Datadog's APM
- For basic "which endpoints are slow?" — Sentry's tracing is sufficient
- For "why is this database query slow in production?" — Datadog is better
- I'd start with Sentry's built-in tracing and see if it meets your needs

The overall strategy: start cheap (Sentry + basic metrics), add expensive tooling when you have specific pain points that justify the cost. Premature Datadog adoption is a common startup expense mistake.'''
    ),
    (
        "thinking/uncertainty-typescript-strictness",
        "We're enabling TypeScript strict mode on our 150K-line React codebase. Should we go all-in at once or incrementally? The team is split.",
        r'''<think>
TypeScript strict mode migration on a large codebase. Let me think about this with calibrated confidence.

**What does strict mode enable?**
- `strictNullChecks`: variables can't be null/undefined unless explicitly typed
- `noImplicitAny`: must annotate types that can't be inferred
- `strictFunctionTypes`: stricter function type checking
- `strictPropertyInitialization`: class properties must be initialized
- `noImplicitThis`: must type `this` in functions

The most impactful (and painful) are `strictNullChecks` and `noImplicitAny`.

**Option A: All-in (Big Bang)**
Pros:
- No "mixed mode" confusion
- Done in one sprint
- Everyone learns strict mode at the same time

Cons:
- 150K lines will likely produce 2,000-5,000+ strict errors
- Everything breaks at once
- Team is blocked while fixing errors
- Risk of "just add `as any` to make it compile" shortcuts
- Massive PR that's unreviewable

**Option B: Incremental (per-file or per-directory)**
Pros:
- Manageable chunks
- Team learns gradually
- No blocking period
- Easier code review

Cons:
- "Mixed mode" — some files are strict, others aren't
- Need tooling to track progress
- Can take months to complete
- Some developers might never migrate their files

**My assessment:**
For 150K lines, big bang is almost certainly wrong. I'm about 85% confident of this. The error count will be overwhelming and quality will suffer.

But pure incremental is also problematic — without a deadline, it never finishes. I've seen teams at "60% migrated" for years.

**The right approach (80% confident):** hybrid — enable strict flags individually, not all at once, with a clear timeline and per-flag phases.

Phase 1: Enable `noImplicitAny` (catches the most bugs, easiest to fix)
Phase 2: Enable `strictNullChecks` (hardest, most impactful)
Phase 3: Enable remaining strict flags (usually few errors)

Each phase uses incremental migration with a deadline.

**Uncertainty:**
- I don't know their TypeScript skill level (affects approach)
- I don't know their test coverage (affects risk of regressions)
- I don't know their deployment frequency (affects rollback ability)
- At 150K lines, the error count could vary wildly (1,000 to 10,000)
</think>

Go **incremental, flag-by-flag** — not all-in and not "whenever we feel like it." Here's why, with confidence levels:

## Why Not Big Bang (85% Confident)

At 150K lines, enabling full `strict: true` will produce an estimated **2,000-8,000 errors** (based on typical React codebases). Fixing these all at once means:
- A multi-week blocking period where the team can't ship features
- A massive un-reviewable PR (or hundreds of small ones merged in chaos)
- "Fix strict errors" shortcuts like `as any` and `!` that make the code WORSE

## The Phased Approach (80% Confident)

```jsonc
// tsconfig.json — enable flags ONE AT A TIME
{
  "compilerOptions": {
    // Phase 1 (Week 1-2): Easy wins
    "noImplicitReturns": true,
    "noFallthroughCasesInSwitch": true,
    "forceConsistentCasingInFileNames": true,

    // Phase 2 (Week 3-6): Medium difficulty
    "noImplicitAny": true,
    "strictFunctionTypes": true,
    "strictPropertyInitialization": true,

    // Phase 3 (Week 7-12): The hard one
    "strictNullChecks": true,

    // Phase 4: Victory
    // "strict": true  // Enable this after all individual flags pass
  }
}
```

### Phase 1: Easy Wins (1-2 weeks, ~100 errors)

```typescript
// noImplicitReturns — add explicit returns
// ❌ Before:
function getLabel(type: string) {
  if (type === 'admin') return 'Administrator'
  // implicit return undefined for other types
}

// ✅ After:
function getLabel(type: string): string {
  if (type === 'admin') return 'Administrator'
  return type // explicit return
}
```

### Phase 2: noImplicitAny (3-4 weeks, ~500-1500 errors)

```typescript
// ❌ Before (implicit any):
function processItems(items) {  // items: any
  return items.map(item => item.name)  // item: any
}

// ✅ After:
interface Item { name: string; id: number }
function processItems(items: Item[]): string[] {
  return items.map(item => item.name)
}

// For event handlers (common source of implicit any):
// ❌
const handleChange = (e) => setState(e.target.value)
// ✅
const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
  setState(e.target.value)
}
```

### Phase 3: strictNullChecks (4-6 weeks, ~1000-3000 errors)

This is the hardest but most valuable flag. It catches real null-pointer bugs.

```typescript
// ❌ Before: pretends everything is always defined
function getUserName(userId: string): string {
  const user = users.find(u => u.id === userId)
  return user.name // 💥 Runtime error if user not found!
}

// ✅ After: handles the null case
function getUserName(userId: string): string | undefined {
  const user = users.find(u => u.id === userId)
  return user?.name
}

// Common pattern: API responses
interface ApiResponse<T> {
  data: T | null  // explicitly nullable
  error: string | null
  loading: boolean
}

// Component handles all states:
function UserProfile({ userId }: { userId: string }) {
  const { data, error, loading } = useUser(userId)
  if (loading) return <Spinner />
  if (error) return <Error message={error} />
  if (!data) return <NotFound />
  return <Profile user={data} />  // data is narrowed to non-null here
}
```

## Tracking Progress

```bash
# Count remaining errors per flag (run before enabling each flag)
npx tsc --noImplicitAny --noEmit 2>&1 | grep "error TS" | wc -l
npx tsc --strictNullChecks --noEmit 2>&1 | grep "error TS" | wc -l
```

## What I'm Less Sure About (65-70%)

**Timeline estimates:** My "12 weeks total" assumes:
- 2-3 developers spending ~30% of time on migration
- Moderate TypeScript experience on the team
- Decent test coverage to catch regressions
If your team is new to TypeScript, double the timeline. If you have extensive tests, you can go faster.

**Whether `strictNullChecks` is worth the pain** at your scale (75%):
- It IS the most valuable flag for catching real bugs
- But at 150K lines, it may produce 3000+ errors
- Some teams decide to enable it only for NEW files and gradually migrate old ones
- I'd recommend full migration, but I understand if the team chooses gradual for this flag specifically

**The `// @ts-expect-error` escape hatch** (70%):
- For the hardest-to-fix errors, you might temporarily add `@ts-expect-error` with a TODO
- This is better than `as any` because it REMOVES itself when the underlying type is fixed
- But it can become technical debt if not tracked
- Set a rule: max 50 `@ts-expect-error` comments, with a quarterly review to eliminate them'''
    ),
    (
        "thinking/uncertainty-kubernetes-adoption",
        "Our CTO wants to move to Kubernetes. We currently deploy 5 services to EC2 instances with Ansible. We have 3 DevOps engineers. Is Kubernetes the right move?",
        r'''<think>
Kubernetes adoption evaluation. Let me be honest about the trade-offs with calibrated uncertainty.

**Current state:**
- 5 services on EC2 with Ansible
- 3 DevOps engineers
- This is a functioning, understood system

**What Kubernetes gives you:**
- Container orchestration (scheduling, scaling, self-healing)
- Service discovery and load balancing
- Rolling deployments, easy rollback
- Resource efficiency (bin-packing containers)
- Standardized deployment model

**What Kubernetes costs you:**
- Learning curve: 3-6 months for the DevOps team to be proficient
- Operational complexity: etcd, control plane, networking (CNI), storage (CSI), ingress, service mesh
- Debugging complexity: pod scheduling, networking issues, resource limits, OOM kills
- Security surface: RBAC, network policies, pod security, secrets management
- Cost: EKS is $0.10/hour per cluster ($73/month) plus worker nodes

**The honest assessment:**
For 5 services with 3 DevOps engineers, Kubernetes is OVERKILL. I'm 80% confident of this.

Why?
- 5 services don't need container orchestration — Ansible can handle this fine
- 3 DevOps engineers will spend 6+ months becoming proficient, during which they can't do other work
- The operational overhead of K8s will consume most of their time
- You don't have the scale that justifies K8s complexity

**When does K8s make sense?**
- 15+ services (orchestration overhead justified)
- 5+ DevOps engineers (capacity to operate K8s)
- Need for auto-scaling, self-healing at scale
- Multiple teams deploying independently
- Already containerized workloads

**Alternatives:**
- ECS (Fargate): 80% of K8s benefits, 20% of the complexity
- Docker Compose + EC2: simplest container deployment
- Nomad: simpler orchestrator than K8s

**Uncertainty:**
- I don't know their growth trajectory (if going to 20 services in a year, K8s might make sense)
- I don't know if they have containerized workloads already
- I don't know if the CTO has K8s experience
- I don't know their team's existing skills
</think>

For 5 services and 3 DevOps engineers, Kubernetes is almost certainly overkill right now. Here's my honest assessment:

## The Bottom Line (80% Confident)

| Factor | Your Situation | K8s Threshold |
|--------|---------------|---------------|
| Services | 5 | 15+ |
| DevOps team | 3 people | 5+ people |
| Deployment frequency | ? (likely weekly) | Multiple daily |
| Auto-scaling need | Low | High |
| Current pain level | Low (Ansible works) | High |

**Kubernetes is designed for organizations with 50+ services and dedicated platform teams.** At 5 services, the operational overhead of K8s will CONSUME your 3-person DevOps team.

## What K8s Will Actually Cost You

```
Month 1-3: Learning phase
  - 3 DevOps engineers × 50% time = 1.5 FTE on K8s learning
  - Zero feature work from DevOps during this period
  - EKS cluster cost: ~$150-300/month (cluster + nodes)

Month 3-6: Migration phase
  - Dockerizing all 5 services (if not already)
  - Writing Helm charts / K8s manifests
  - Setting up CI/CD for K8s
  - Networking: ingress, DNS, TLS, service mesh
  - Debugging mysterious pod crashes, OOM kills, CrashLoopBackoff

Month 6+: Ongoing operations
  - K8s version upgrades (every 3-4 months, breaking changes)
  - etcd maintenance
  - Node scaling and capacity planning
  - Security: RBAC, network policies, pod security standards
  - 1 of 3 DevOps engineers is now "the K8s person" full-time
```

## What I'd Recommend Instead (85% Confident)

**Option 1: ECS Fargate** — if you want containers without orchestration overhead

```yaml
# task-definition.json — this is your entire "K8s manifest"
{
  "family": "my-service",
  "containerDefinitions": [{
    "name": "app",
    "image": "123456789.dkr.ecr.us-east-1.amazonaws.com/my-service:latest",
    "portMappings": [{"containerPort": 8000}],
    "memory": 512,
    "cpu": 256
  }]
}
# That's it. No etcd, no control plane, no node management.
# AWS handles scheduling, scaling, and self-healing.
```

**Option 2: Improve your current Ansible setup** — if it mostly works

```yaml
# Add what K8s would give you, without K8s:
# 1. Zero-downtime deploys (rolling restart)
- name: Deploy new version
  hosts: app_servers
  serial: 1  # One server at a time
  tasks:
    - name: Pull new code
      git: repo=... dest=/app version={{ git_sha }}
    - name: Restart service
      systemd: name=myapp state=restarted
    - name: Wait for health check
      uri: url=http://localhost:8000/health status_code=200
      retries: 10
      delay: 5

# 2. Auto-scaling: AWS Auto Scaling Groups
# 3. Service discovery: AWS ALB + Route53
# 4. Health checks: ALB health checks + CloudWatch alarms
```

## When to Reconsider K8s (70% Confident on Timing)

Revisit Kubernetes when you hit ANY of these:
- **15+ services**: orchestration overhead becomes justified
- **5+ DevOps engineers**: team capacity to operate K8s
- **Multiple product teams** deploying independently (K8s namespaces shine here)
- **Specific K8s features needed**: complex scheduling, GPU workloads, custom operators
- **Current tooling is painful**: Ansible deploys take >30 min, rollbacks are scary

## What I'm Less Sure About

**If your growth trajectory is aggressive** (65% confident): If you're going from 5 to 20+ services in the next 12 months, starting K8s now might make sense to avoid a harder migration later. But I'd still recommend ECS Fargate as a stepping stone — it's much easier to migrate from ECS to K8s than from Ansible to K8s.

**The CTO's motivation** (uncertain): If the CTO wants K8s because:
- "It's the industry standard" → this is resume-driven architecture, push back
- "We're about to scale 10x" → valid, but verify the timeline
- "I've run K8s before and know the operational cost" → more credible, but still evaluate if 5 services justifies it
- "Recruiters say candidates want K8s experience" → valid but expensive way to recruit

The right question isn't "should we use K8s?" — it's "what problem are we solving?" If the answer is "our deployments are unreliable" or "we can't scale," there are simpler solutions than Kubernetes.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
