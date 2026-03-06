"""Phase 2: Advanced Reasoning — Tradeoff Analysis (Part 2)

Training the model to systematically analyze engineering tradeoffs by
identifying competing concerns, evaluating context-dependent factors,
and arriving at well-reasoned recommendations rather than blanket advice.
"""

PAIRS = [
    (
        "thinking/advanced-tradeoff-cap-theorem",
        r'''We're building a distributed e-commerce platform. Our team keeps arguing about consistency vs availability. The checkout service needs to handle payments, and the product catalog needs to serve millions of reads. How should we think about this tradeoff differently for each service?''',
        r'''<think>
This is a classic CAP theorem discussion, but the question is more nuanced than just "pick CP or AP." The key insight is that different services within the same system can and should make different tradeoff decisions.

Let me think through each service:

Checkout/Payment service:
- Financial transactions MUST be consistent — double-charging or lost payments are catastrophic
- Users expect occasional slowness during checkout (they're already committed to buying)
- The blast radius of inconsistency is high: money, legal compliance, trust
- Favors consistency (CP) — it's better to reject a transaction than process it incorrectly

Product catalog:
- Stale data is tolerable — showing a price that's 30 seconds old rarely matters
- Users expect instant page loads — slow catalog = lost sales before checkout even happens
- The blast radius of unavailability is high: users bounce, revenue lost
- Favors availability (AP) — eventual consistency is fine here

But it's not purely binary. There are degrees:
- Checkout can use synchronous replication for payment state but async for order history
- Catalog can use strong consistency for inventory counts near zero (to avoid overselling) but eventual consistency for product descriptions

I should also mention that the "partition" in CAP is often misunderstood — in practice, network partitions are rare within a single datacenter, so the real tradeoff is usually between consistency and latency.
</think>

The critical insight your team needs: **this isn't one decision, it's many**. Different services should sit at different points on the consistency-availability spectrum.

## Checkout/Payment Service: Favor Consistency

```
Payment flow:
  User clicks "Pay"
    → Reserve inventory (strongly consistent)
    → Charge payment (strongly consistent)
    → Confirm order (strongly consistent)
    → Send confirmation email (eventually consistent — OK if delayed)
```

**Why consistency wins here:**
- Double-charging a customer is a support nightmare and legal risk
- Lost payments erode trust irreparably
- Users already tolerate 2-5 seconds of latency at checkout (they're committed)
- A brief "service unavailable, please retry" is far better than a silent payment error

**Implementation approach:**
- Synchronous replication for payment state
- Distributed transactions or saga pattern with compensation
- If a partition occurs, **reject the transaction** rather than risk inconsistency

## Product Catalog: Favor Availability

```
Catalog flow:
  User browses products
    → Serve from nearest replica (eventually consistent)
    → Cache aggressively (TTL: 30-60 seconds)
    → Inventory count: "In Stock" vs exact count (reduces consistency needs)
```

**Why availability wins here:**
- A product description that's 30 seconds stale causes zero harm
- A slow or unavailable catalog means users leave before reaching checkout
- Every 100ms of added latency costs roughly 1% in sales
- You can always show a "price may vary" disclaimer

## The Nuanced Middle Ground

Some data crosses the boundary:

| Data | Consistency Need | Why |
|------|-----------------|-----|
| Product descriptions | Low | Stale by minutes is fine |
| Prices | Medium | Stale by seconds is OK, but honor displayed price |
| Inventory (high stock) | Low | "In Stock" is sufficient |
| Inventory (low stock) | High | Overselling 1 of 3 remaining items is bad |
| Payment state | Critical | Must be strongly consistent |
| Order history | Medium | Eventual consistency OK, but shouldn't lose orders |

## Practical Architecture

```
                    ┌─────────────────┐
                    │   API Gateway    │
                    └────────┬────────┘
                             │
              ┌──────────────┼──────────────┐
              │              │              │
     ┌────────▼───────┐ ┌───▼────┐ ┌──────▼───────┐
     │ Product Catalog │ │ Cart   │ │   Checkout   │
     │   (AP - Redis   │ │(hybrid)│ │  (CP - RDBMS │
     │    + CDN cache) │ │        │ │   with sync  │
     │                 │ │        │ │   replication)│
     └─────────────────┘ └────────┘ └──────────────┘
```

**Stop arguing about one global policy.** Map each data flow to its actual consistency requirement, and you'll find that most of your system can be highly available while the critical financial paths remain strongly consistent.'''
    ),
    (
        "thinking/advanced-tradeoff-speed-vs-quality",
        r'''My engineering manager wants us to ship features faster. Our tech lead wants us to maintain high code quality with thorough code reviews, extensive testing, and clean architecture. They keep clashing. How do I think about the development speed vs code quality tradeoff?''',
        r'''<think>
This is one of the most common engineering tradeoffs and it's often framed as a false dichotomy. Let me think carefully about this.

The naive framing: speed and quality are on opposite ends of a slider. Move one way, you sacrifice the other.

The more nuanced reality: quality IS speed, but on different timescales.

Short-term (days to weeks):
- Skipping tests, reviews, and refactoring genuinely ships features faster
- For prototypes, throwaway code, or validating ideas, this is rational

Medium-term (weeks to months):
- Accumulated shortcuts create compounding drag
- Each new feature takes longer because it interacts with fragile, poorly-understood code
- Bug rates increase, eating into feature development time

Long-term (months to years):
- Low-quality codebases can reach a point where adding ANY feature is painfully slow
- The team spends most time on firefighting and workarounds
- Developer morale drops, causing turnover, which further degrades velocity

So the real question isn't speed vs quality — it's: what's the appropriate quality level for our current context?

Factors that shift the balance:
- Code lifespan: throwaway prototype vs core business logic
- Team size: solo developer vs large team
- Domain risk: marketing page vs financial calculations
- Change frequency: stable vs rapidly evolving requirements

I should also address the interpersonal aspect — the EM and tech lead aren't wrong, they're optimizing for different horizons.
</think>

This clash usually stems from both people being right — but about different time horizons. Let me reframe it.

## The Speed-Quality Curve Is Not Linear

```
Feature velocity
over time:         With sustained quality investment
                   ┌─────────────────────────────────────
                  /
                 /
                /   With shortcuts ("move fast")
    ───────────/─────────────────────
              /       ↘ declining velocity
             /          ↘
            /             ↘  ← "grinding halt"
           /
    ──────/

    Time →  Week 1    Month 3    Month 12    Month 24
```

**Short-term:** Skipping quality genuinely ships faster. This is real, not imagined.
**Medium-term:** The lines cross. Accumulated debt creates drag that exceeds the initial speed gain.
**Long-term:** Low-quality codebases approach a velocity floor where most effort goes to fighting the codebase rather than building features.

## Reframe the Conversation

Instead of "speed vs quality," ask: **what's the cost of a defect in this specific area?**

| Area | Defect Cost | Appropriate Quality Level |
|------|------------|--------------------------|
| Payment processing | Very high (money, trust, legal) | Maximum: extensive tests, formal reviews |
| Core domain logic | High (hard to fix later) | High: good tests, thorough review |
| Internal admin tools | Medium (small user base, fixable) | Moderate: basic tests, lighter review |
| Prototype / experiment | Low (may be thrown away) | Minimal: just make it work |
| Marketing landing page | Low (easy to change) | Minimal to moderate |

## Practical Compromise

Give your EM and tech lead this framework:

**1. Categorize work explicitly:**
```
Feature ticket template:
  - Quality tier: [Critical / Standard / Experimental]
  - Critical: Full test coverage, architecture review, documentation
  - Standard: Unit tests for logic, standard code review
  - Experimental: Manual testing OK, lightweight review, time-boxed
```

**2. Budget quality investment:**
- Allocate 15-20% of sprint capacity to tech debt reduction
- This isn't "slowing down" — it's maintaining future velocity
- Track deployment frequency and bug rates to prove the ROI

**3. Identify the ACTUAL bottlenecks:**
Often the speed problem isn't code quality — it's:
- Slow CI/CD pipelines (fix the pipeline, not the review process)
- Unclear requirements (features get reworked, not reviewed too slowly)
- Too many WIP items (context switching kills throughput)
- Approval bottlenecks (too few reviewers, not too many reviews)

**4. Time-box reviews, don't skip them:**
```
Instead of: "Skip review to ship faster"
Try:        "Reviews must complete within 4 business hours"
            "Reviews focus on correctness + maintainability, not style"
            "Use automated linting for style, humans for logic"
```

## The Key Message

Tell them both: **sustained speed requires sustained quality, but not maximum quality everywhere.** The engineering manager is right that the team shouldn't gold-plate every feature. The tech lead is right that shortcuts compound into severe drag. The answer is being deliberate about WHERE quality investment goes, not treating it as a global dial.'''
    ),
    (
        "thinking/advanced-tradeoff-api-simplicity-flexibility",
        r'''I'm designing a REST API for a SaaS product. Some team members want a simple API with obvious endpoints and minimal configuration. Others want a flexible, powerful API with filtering, field selection, custom projections, and composable queries. How do I balance simplicity vs flexibility in API design?''',
        r'''<think>
This is a fundamental API design tension. Let me think about both sides and the design principles that help navigate this.

Simple API advantages:
- Lower learning curve, faster time to first successful call
- Fewer ways to misuse the API
- Easier to document, easier to support
- Less surface area = fewer bugs, easier to maintain
- Most users only need basic operations

Flexible API advantages:
- Power users can optimize their usage (fewer round trips, less bandwidth)
- Reduces the need for custom endpoints per client need
- Can serve diverse use cases without API changes
- Prevents the "death by a thousand endpoints" problem

The trap: many teams try to build a flexible API from day one, before they understand actual usage patterns. This leads to over-engineering.

Key design principles:
1. Progressive disclosure — simple by default, flexible when needed
2. Sensible defaults — the zero-config path should work for 80% of cases
3. Layered complexity — basic → intermediate → advanced usage tiers
4. Consistency — flexible features should follow predictable patterns

Let me think about specific techniques:
- Default field sets with optional ?fields= parameter
- Pagination with sensible defaults
- Filtering that starts simple (exact match) and extends to operators
- Separate "search" endpoints for complex queries vs simple CRUD

I should also consider the audience: developer APIs for technical users can afford more complexity than APIs for low-code integrators.
</think>

The answer is progressive disclosure: **make the simple things simple and the complex things possible.**

## Design Principle: Layered Complexity

```
Layer 0 (Zero config):    GET /products          → works immediately
Layer 1 (Basic params):   GET /products?category=shoes&limit=20
Layer 2 (Field selection): GET /products?fields=id,name,price
Layer 3 (Advanced query):  GET /products?filter=price:gt:50&sort=-created_at
```

Each layer is opt-in. A developer who just needs products never sees the complexity of Layer 3.

## Concrete Design Patterns

**1. Sensible defaults everywhere:**
```json
GET /products

// Returns with defaults applied:
{
  "data": [...],       // Default field set (not ALL fields)
  "pagination": {
    "page": 1,
    "per_page": 25,    // Sensible default, not 10000
    "total": 342
  }
}
```

The developer didn't specify pagination, field selection, or sorting — but they got a useful, bounded response.

**2. Optional field selection (don't require it):**
```
GET /products                         → default fields (id, name, price, thumbnail)
GET /products?fields=id,name          → minimal response
GET /products?fields=id,name,reviews  → include expensive nested resource
```

Design your default field set to cover the common case. Put expensive fields (nested objects, computed values) behind explicit opt-in.

**3. Progressive filtering:**
```
# Simple (covers 80% of needs):
GET /products?category=shoes&color=red

# Intermediate (operators for range queries):
GET /products?price_gte=50&price_lte=200

# Advanced (for power users who need it):
GET /products?filter[price][gte]=50&filter[color][in]=red,blue
```

Start with simple key=value filtering. Only add operator syntax if users actually request it.

**4. Separate search from CRUD:**
```
# CRUD (simple, predictable):
GET    /products
GET    /products/123
POST   /products
PUT    /products/123
DELETE /products/123

# Search (where complexity lives):
POST /products/search
{
  "query": "running shoes",
  "filters": { "price": { "min": 50, "max": 200 } },
  "facets": ["brand", "color"],
  "sort": [{ "field": "relevance" }, { "field": "price", "order": "asc" }]
}
```

This keeps the CRUD endpoints clean while giving power users a dedicated surface for complex queries.

## Decision Framework

| Factor | Lean Simple | Lean Flexible |
|--------|------------|---------------|
| Primary users are non-technical | Yes | |
| Primary users are developers | | Yes |
| You have < 50 API consumers | Yes | |
| You have diverse consumer needs | | Yes |
| Requirements are well understood | Yes | |
| Requirements are unpredictable | | Yes |
| You can iterate the API quickly | Yes (add flexibility later) | |
| Breaking changes are very costly | | Yes (build flexibility in) |

## The Anti-Patterns to Avoid

**Over-engineering early:**
```
# Don't build this on day one:
GET /products?fields=name,price&include=reviews.author&
    filter[price][gte]=50&filter[tags][contains]=sale&
    sort=-price,name&page[size]=10&page[cursor]=abc123

# Build this on day one:
GET /products?category=shoes&page=1
```

**Inconsistent flexibility:**
```
# Bad: filtering works differently per endpoint
GET /products?min_price=50        (prefix style)
GET /orders?filter[status]=active (bracket style)
GET /users?status.eq=active       (dot style)

# Good: one pattern everywhere
GET /products?price_gte=50
GET /orders?status=active
GET /users?status=active
```

## My Recommendation

Ship a simple API first with these hooks for future flexibility:
1. Envelope your responses in `{ "data": [...], "pagination": {...} }` from day one
2. Use consistent naming conventions so filtering syntax can be added later
3. Track which endpoints get the most "I wish I could filter by X" requests
4. Add flexibility to the endpoints that actually need it, based on real usage data

The worst outcome is a complex API that nobody uses the advanced features of. The second worst is a simple API that forces power users into N+1 request patterns. Progressive disclosure avoids both.'''
    ),
    (
        "thinking/advanced-tradeoff-monolith-microservices",
        r'''We're a 5-person startup building a B2B SaaS product. Our CTO wants to go with microservices from the start because "that's how Netflix does it." I think a monolith would be simpler. Who's right? What should a small team actually build?''',
        r'''<think>
This is a very common debate, and the answer for a 5-person startup is almost always "start with a monolith" — but I should explain WHY rather than just assert it.

Let me think about what microservices actually cost vs benefit at this scale.

Microservices overhead for a small team:
- Service discovery, API gateways, load balancers for each service
- Distributed tracing and logging across services
- Network latency between services (vs in-process function calls)
- Data consistency across service boundaries
- Deployment complexity: CI/CD pipelines per service
- Local development: running 5-10 services on a laptop
- Debugging distributed failures is MUCH harder
- Schema evolution across service boundaries
- Team cognitive load: each person needs to understand multiple services + infrastructure

What microservices solve:
- Independent deployment of components (useful at scale)
- Independent scaling of components (useful with known hot spots)
- Team autonomy (useful when you have 50+ engineers)
- Technology heterogeneity (useful when different problems need different tools)
- Fault isolation (useful when you understand your failure modes)

At 5 people, NONE of these benefits meaningfully apply:
- You deploy together anyway because you're coordinating in one room
- You don't have scale problems yet (and may never)
- Team autonomy doesn't matter when everyone works on everything
- One tech stack is simpler when everyone needs to understand everything
- You don't know your failure modes yet

The Netflix argument is a classic survivorship bias / cargo cult reasoning issue. Netflix moved to microservices because they had hundreds of engineers and specific scaling needs. They also had years of experience with their monolith to understand where the boundaries should be.

I should recommend: modular monolith with clear boundaries, ready to extract services when (if) needed.
</think>

Your instinct is correct. For a 5-person team, **start with a well-structured monolith**. Here's the detailed reasoning.

## Why "Netflix Does It" Is the Wrong Argument

Netflix moved to microservices because they had:
- 2,000+ engineers who needed to deploy independently
- Extreme, well-understood scaling requirements (streaming video at global scale)
- Years of experience with a monolith that taught them exactly where to split
- Dedicated platform teams to manage the infrastructure complexity

Your startup has none of these. The Netflix comparison is survivorship bias — you don't hear about the startups that adopted microservices early and drowned in operational complexity before finding product-market fit.

## The Real Cost of Microservices at Your Scale

```
What 5 engineers spend time on with microservices:

  Feature development:     ~40%  ← This should be 80%+
  Infrastructure/DevOps:   ~25%  ← K8s, service mesh, API gateways
  Debugging distributed:   ~15%  ← "Which service dropped the request?"
  Data consistency issues:  ~10%  ← Distributed transactions, eventual consistency
  Local dev environment:    ~10%  ← "How do I run 8 services on my laptop?"
```

With a monolith:
```
  Feature development:     ~80%
  Infrastructure/DevOps:    ~5%  ← One app, one database, one deployment
  Debugging:                ~5%  ← Stack traces, not distributed traces
  Local dev:               ~10%  ← One process, one command
```

## What to Actually Build: A Modular Monolith

```
my-saas-app/
├── src/
│   ├── modules/
│   │   ├── auth/           # Authentication & authorization
│   │   │   ├── routes.py
│   │   │   ├── services.py
│   │   │   └── models.py
│   │   ├── billing/        # Subscription & payment
│   │   │   ├── routes.py
│   │   │   ├── services.py
│   │   │   └── models.py
│   │   ├── tenants/        # Multi-tenancy
│   │   │   ├── routes.py
│   │   │   ├── services.py
│   │   │   └── models.py
│   │   └── core_feature/   # Your actual product
│   │       ├── routes.py
│   │       ├── services.py
│   │       └── models.py
│   ├── shared/             # Cross-cutting concerns
│   │   ├── database.py
│   │   ├── events.py       # Internal event bus (future extraction point)
│   │   └── middleware.py
│   └── app.py              # Single entry point
├── tests/
├── Dockerfile              # ONE container
└── docker-compose.yml      # App + DB + Redis, that's it
```

**Key rules for the modular monolith:**
1. Modules communicate through defined interfaces (service classes), not by reaching into each other's database tables
2. Each module owns its own database tables
3. Use an internal event bus for cross-module notifications
4. No circular dependencies between modules

This gives you 90% of the organizational benefits of microservices with none of the operational cost.

## When to Extract a Service (Signs You're Ready)

| Signal | What to Extract |
|--------|----------------|
| One module needs to scale independently (e.g., 100x more reads) | Extract that module |
| Team grows to 15+ and modules have dedicated owners | Extract owned modules |
| A module needs a different tech stack (ML model in Python, app in Go) | Extract that module |
| A module has genuinely different deployment cadence | Extract that module |
| You need fault isolation (billing failure shouldn't break catalog) | Extract critical paths |

**Notice:** none of these signals exist at a 5-person startup.

## The Conversation with Your CTO

Frame it this way:

> "Microservices are a scaling solution, not a starting architecture. Our competitive advantage right now is iteration speed — how fast we can ship features and find product-market fit. A monolith maximizes the percentage of our engineering time spent on features vs infrastructure. We'll structure it modularly so extraction is straightforward when we actually need it."

If the CTO is worried about being "stuck" with a monolith, the modular approach is the insurance policy. Clean module boundaries make future extraction a well-understood, incremental process rather than a risky big-bang rewrite.'''
    ),
    (
        "thinking/advanced-tradeoff-build-vs-buy",
        r'''We need to add authentication, email sending, background job processing, and full-text search to our application. For each of these, how should we think about whether to build it ourselves or use a third-party service/library?''',
        r'''<think>
Build vs buy is one of the most impactful decisions engineering teams make. Let me think through a framework and then apply it to each specific capability.

General build vs buy framework:
1. Is it a core differentiator for our business?
   - If yes: lean toward build (or heavily customize)
   - If no: lean toward buy
2. What's the total cost of ownership?
   - Build: development time + maintenance + on-call + opportunity cost
   - Buy: license cost + integration time + vendor risk + customization limits
3. How well do off-the-shelf solutions fit our needs?
   - Perfect fit: definitely buy
   - 80% fit: probably buy + adapt
   - 50% fit: evaluate carefully
   - Poor fit: probably build
4. What's the operational burden?
   - Some "build" choices are actually "operate" choices (self-hosting vs managed)

Now for each capability:

Authentication:
- NOT a differentiator for almost any business
- Extremely complex to build correctly (security implications are enormous)
- Mature solutions exist: Auth0, Clerk, Firebase Auth, Supabase Auth
- Strong buy signal

Email sending:
- NOT a differentiator
- Infrastructure complexity (deliverability, reputation, bounce handling)
- Mature solutions: SendGrid, Postmark, SES, Resend
- Strong buy signal

Background job processing:
- NOT a differentiator, but deeply integrated with business logic
- Good libraries exist: Celery, Sidekiq, BullMQ
- The library approach (not SaaS) often makes most sense
- Medium — use a library, not a service

Full-text search:
- Depends on how central search is to the product
- If it's a search product: maybe build/heavily customize
- If it's "we need a search bar": use Elasticsearch/Algolia/Typesense
- Moderate to strong buy signal for most apps
</think>

Here's a framework and specific recommendations for each.

## The Build vs Buy Decision Matrix

For each capability, evaluate these four factors:

```
                     BUILD                          BUY
                       ←─────────────────────────────→
Core differentiator?   "This IS our product"          "Everyone needs this"
Fit of existing tools? Nothing fits our needs          Perfect fit exists
Security/compliance?   Unique requirements             Standard requirements
Team expertise?        We have deep expertise          We'd be learning as we go
```

## Authentication: BUY (Strong)

**Verdict: Use a managed auth service.**

| Factor | Assessment |
|--------|-----------|
| Differentiator? | No — users don't choose your product for its login page |
| Build cost? | Enormous: passwords, MFA, OAuth, session management, token rotation, brute force protection, account recovery, CSRF, XSS protection |
| Buy cost? | $0-$500/month for most startups |
| Risk of building? | HIGH — security vulnerabilities in auth are catastrophic |

```
Recommended options (in rough order):
1. Auth0 / Clerk     — Best DX, most features, higher price
2. Supabase Auth     — Good if you're already on Supabase
3. Firebase Auth     — Good if you're in Google ecosystem
4. NextAuth/Lucia    — Library approach if you want more control
```

**Never build your own password hashing, session management, or OAuth flow from scratch.** Even experienced security engineers use battle-tested libraries.

## Email Sending: BUY (Strong)

**Verdict: Use a transactional email service.**

| Factor | Assessment |
|--------|-----------|
| Differentiator? | No |
| Build cost? | Running mail servers is an entire specialty: IP reputation, SPF/DKIM/DMARC, bounce processing, deliverability monitoring |
| Buy cost? | $0-$100/month for most startups |
| Risk of building? | Your emails land in spam, you spend weeks debugging deliverability |

```
Recommended options:
1. Postmark        — Best deliverability for transactional email
2. Resend          — Modern API, good DX, React Email templates
3. AWS SES         — Cheapest at volume, more DIY
4. SendGrid        — Established, good if you also need marketing email
```

**What to build yourself:** Email templates and the logic for when to send what. **What to buy:** The actual sending infrastructure.

## Background Job Processing: USE A LIBRARY (Middle Ground)

**Verdict: Use an open-source library, not a SaaS service.**

| Factor | Assessment |
|--------|-----------|
| Differentiator? | No, but tightly coupled to your business logic |
| Build cost? | Moderate if from scratch (retry logic, dead letters, scheduling, monitoring) |
| Library cost? | Free, well-maintained options exist |
| SaaS cost? | Adds external dependency for core processing |

```
Recommended by language:
  Python:     Celery + Redis (or RQ for simpler needs)
  Node.js:    BullMQ + Redis
  Ruby:       Sidekiq + Redis
  Go:         Asynq or River (Postgres-backed)
  Java:       Spring Batch or Quartz

  Or if you want managed: Inngest, Trigger.dev
```

**Why a library, not a service?** Background jobs are deeply intertwined with your application code. A library gives you the queue mechanics (retry, scheduling, concurrency) while keeping the execution local and debuggable.

```python
# Example with Celery — you get retry, scheduling, monitoring for free
@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_invoice(self, invoice_id):
    try:
        invoice = Invoice.objects.get(id=invoice_id)
        pdf = generate_pdf(invoice)
        send_email(invoice.customer.email, attachment=pdf)
        invoice.mark_sent()
    except TransientError as e:
        self.retry(exc=e)
```

## Full-Text Search: BUY, Usually

**Verdict: Depends on how central search is to your product.**

| Scenario | Recommendation |
|----------|---------------|
| Search IS the product (marketplace, document search) | Self-host Elasticsearch/Meilisearch with heavy customization |
| Search is an important feature | Managed Elasticsearch (AWS OpenSearch) or Typesense |
| Search is a "nice to have" | Algolia (zero ops) or Postgres full-text search |
| Simple filtering/autocomplete | Postgres `ILIKE` or `tsvector` — no external service needed |

```sql
-- Often overlooked: Postgres full-text search handles many cases
-- No external service needed for basic search

CREATE INDEX idx_products_search ON products
  USING gin(to_tsvector('english', name || ' ' || description));

SELECT * FROM products
WHERE to_tsvector('english', name || ' ' || description)
  @@ plainto_tsquery('english', 'wireless headphones')
ORDER BY ts_rank(...) DESC;
```

If Postgres full-text search covers your needs, you've saved yourself an entire infrastructure component.

## Summary

| Capability | Recommendation | Key Reason |
|-----------|---------------|-----------|
| Authentication | Buy (managed service) | Security risk too high to DIY |
| Email | Buy (transactional service) | Deliverability is a whole specialty |
| Background jobs | Library (open source) | Tightly coupled to your code |
| Full-text search | Depends on centrality | Start simple, upgrade if needed |

**The meta-principle:** Build what differentiates you. Buy everything else. Your users are paying for your core product, not for your hand-rolled auth system.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
