"""Phase 2A: Advanced Reasoning — Trade-off Analysis (Part 1)
Multi-dimensional trade-off reasoning, contrastive analysis, calibrated uncertainty."""

PAIRS = [
    (
        "thinking/advanced-tradeoff-monolith-vs-micro",
        "We're a 4-person startup with a Django monolith handling $2M ARR. Our CTO wants to move to microservices because 'that's what Netflix does.' Should we?",
        r'''<think>
Let me systematically analyze this trade-off instead of jumping to a conclusion.

**Context factors:**
- 4-person team (very small)
- Django monolith (proven technology)
- $2M ARR (real revenue, can't afford downtime)
- CTO motivated by what large companies do

**Arguments FOR microservices:**
- Independent scaling of components
- Independent deployment of services
- Technology flexibility per service
- Fault isolation

**Arguments AGAINST microservices (for this team):**
- 4 engineers can't support distributed systems operations
- Distributed debugging, tracing, logging complexity
- Network reliability, latency between services
- Data consistency across services (distributed transactions)
- DevOps overhead (Docker, K8s, service mesh, monitoring)
- Each engineer would own ~2 services — bus factor nightmare
- Current monolith is working and generating revenue

**Quantitative analysis:**
- Microservices migration: ~6 months of engineering time
- 4 engineers × 6 months = 24 engineer-months diverted from features
- That's ~$500K in engineering cost
- For a $2M ARR company, that's 25% of revenue in migration cost

**My assessment:**
This is almost certainly premature. Netflix moved to microservices because they had THOUSANDS of engineers and the monolith was genuinely blocking them. A 4-person team will spend more time on operations than building product.

But I shouldn't dismiss the CTO entirely. There might be legitimate pain points. Let me identify what problems microservices would solve and suggest simpler alternatives.

**Confidence: 90%** that staying with the monolith is correct for a 4-person team at this stage.
</think>

**No.** This is almost certainly the wrong move for your team size and stage. Let me explain with specific analysis.

## The Math

```
Migration effort:     ~6 months × 4 engineers
Engineering cost:     ~$500K (25% of your ARR)
Features NOT shipped: 6 months of product development
Risk:                 Breaking a $2M revenue-generating system

What you get: The same functionality, now harder to debug,
deploy, and maintain with 4 people.
```

## Netflix vs You

| Netflix | Your Startup |
|---------|-------------|
| 2,000+ engineers | 4 engineers |
| Needed to deploy 100+ services independently | Deploy one app |
| Had team PER microservice | Each person would own 2+ services |
| Built their own infrastructure tools | Would use off-the-shelf tools |
| Migrated because monolith was BLOCKING them | Monolith is working fine |

## What Problems Microservices Actually Solve

Microservices solve **organizational scaling problems**, not technical ones:

```
Problem: 200 engineers stepping on each other's code → microservices
Problem: Need to deploy one component without touching others → microservices
Problem: Different components need different languages/runtimes → microservices

NOT a problem at 4 people:
- You can coordinate verbally
- You deploy together anyway
- You all use Python/Django
```

## What You Should Do Instead

### 1. Modular Monolith

```python
# Structure your Django app as modules with clear boundaries
myapp/
├── accounts/          # User authentication, profiles
│   ├── models.py
│   ├── services.py    # Business logic
│   └── api.py         # API endpoints
├── orders/            # Order processing
│   ├── models.py
│   ├── services.py
│   └── api.py
├── payments/          # Payment processing
│   ├── models.py
│   ├── services.py
│   └── api.py
└── shared/            # Cross-cutting concerns
    ├── events.py      # Internal event bus
    └── utils.py
```

### 2. Internal Event Bus (Future-Proofs for Split)

```python
# events.py — in-process now, message broker later
class EventBus:
    _handlers = defaultdict(list)

    @classmethod
    def publish(cls, event_type: str, data: dict):
        for handler in cls._handlers[event_type]:
            handler(data)

    @classmethod
    def subscribe(cls, event_type: str, handler):
        cls._handlers[event_type].append(handler)

# Usage: modules communicate via events, not direct imports
EventBus.publish('order.created', {'order_id': order.id})
```

### 3. When to ACTUALLY Consider Microservices

```
□ Team grows to 15+ engineers
□ Deployments blocked because multiple teams touch same code
□ One component needs fundamentally different scaling
□ You can dedicate 2+ engineers to platform/DevOps
□ You've already exhausted monolith optimization
```

**Bottom line**: Build features. Make money. Split when the monolith is genuinely blocking you, not because it's fashionable.'''
    ),
    (
        "thinking/advanced-tradeoff-sql-vs-nosql",
        "We're designing a new system that needs to handle user profiles, social connections (follows/friends), activity feeds, and messaging. Should we use PostgreSQL, MongoDB, or a combination?",
        r'''<think>
Let me analyze each data type separately — different data has different access patterns.

**User profiles:**
- Structured data (name, email, settings)
- Read-heavy, update-occasionally
- Needs transactions (account changes, billing)
- Relationships (user → orders, user → subscriptions)
- → Strong case for relational (PostgreSQL)

**Social connections (graph):**
- Many-to-many relationships (follows, friends)
- Graph traversal queries ("friends of friends", "mutual connections")
- High read, moderate write
- → Could work in both. PostgreSQL with join tables works up to millions. A graph DB (Neo4j) excels at deep traversals but adds operational complexity.
- For most apps: PostgreSQL is sufficient. Only switch to graph DB if you need 3+ hop traversals at scale.

**Activity feeds:**
- Write-heavy (every action generates feed items)
- Read-heavy (every page load reads the feed)
- Time-ordered, paginated
- Fan-out problem (1 post → N followers' feeds)
- → Could be PostgreSQL with good indexing, or Redis for the hot feed, or a time-series approach.

**Messaging:**
- Append-only (messages are never updated)
- Ordered by time
- Read by conversation (partition by conversation_id)
- Real-time delivery needed
- → PostgreSQL for storage, Redis pub/sub or WebSockets for real-time delivery.

**Overall assessment:**
PostgreSQL can handle ALL of these for a typical application up to millions of users. MongoDB doesn't add value here — all the data is relational. The only reason to add a second database would be for specific performance needs (Redis for caching/real-time).

Confidence: 85% PostgreSQL-only for MVP. Add Redis when you need caching or real-time. MongoDB doesn't fit this use case.
</think>

This needs per-feature analysis, not a blanket decision:

## Feature-by-Feature Analysis

### User Profiles → PostgreSQL (Clear Winner)

```sql
-- Structured, relational, needs constraints and transactions
CREATE TABLE users (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    settings JSONB DEFAULT '{}',  -- Flexible settings in JSONB
    created_at TIMESTAMPTZ DEFAULT NOW()
);
-- PostgreSQL gives you: ACID, constraints, joins to orders/billing, JSONB for flexibility
```

### Social Connections → PostgreSQL (Good Enough to 10M Users)

```sql
CREATE TABLE follows (
    follower_id UUID REFERENCES users(id),
    following_id UUID REFERENCES users(id),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (follower_id, following_id)
);

-- "Who does Alice follow?"
SELECT u.* FROM users u
JOIN follows f ON f.following_id = u.id
WHERE f.follower_id = 'alice-uuid';

-- "Mutual connections" (friends of friends)
SELECT DISTINCT f2.following_id FROM follows f1
JOIN follows f2 ON f1.following_id = f2.follower_id
WHERE f1.follower_id = 'alice-uuid'
  AND f2.following_id != 'alice-uuid';
-- Works fine up to millions of rows with proper indexes
```

### Activity Feeds → PostgreSQL + Redis Cache

```sql
-- PostgreSQL for durable storage
CREATE TABLE feed_items (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,        -- Feed owner
    actor_id UUID NOT NULL,       -- Who did the action
    action VARCHAR(50) NOT NULL,  -- 'liked', 'commented', 'posted'
    target_type VARCHAR(50),
    target_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_feed_user_time ON feed_items(user_id, created_at DESC);
```

```python
# Redis for hot feed cache (last 100 items per user)
def get_feed(user_id, page=1, size=20):
    cache_key = f"feed:{user_id}"
    cached = redis.lrange(cache_key, (page-1)*size, page*size-1)
    if cached:
        return [json.loads(item) for item in cached]
    # Cache miss: fetch from PostgreSQL
    items = db.query(
        "SELECT * FROM feed_items WHERE user_id = %s ORDER BY created_at DESC LIMIT %s",
        (user_id, 100)
    )
    for item in items:
        redis.rpush(cache_key, json.dumps(item))
    redis.expire(cache_key, 300)
    return items[:size]
```

### Messaging → PostgreSQL + WebSockets

```sql
CREATE TABLE messages (
    id UUID PRIMARY KEY,
    conversation_id UUID NOT NULL,
    sender_id UUID NOT NULL,
    body TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at DESC);
-- Partition by conversation_id if needed at scale
```

## Final Architecture

```
PostgreSQL:  Users, connections, feeds, messages (source of truth)
Redis:       Feed cache, session cache, real-time pub/sub
WebSockets:  Real-time message delivery

MongoDB: Not needed. All data is relational.
```

## When MongoDB WOULD Be the Right Choice

```
✓ Document-oriented data (CMS content, product catalogs with variable schemas)
✓ Rapid prototyping where schema is unknown
✓ Logging/analytics with high write throughput
✓ Data that's naturally hierarchical/nested

✗ Relational data (users, orders, connections)
✗ Transactions across multiple documents
✗ Complex queries with joins
```

**Default**: Start with PostgreSQL for everything. Add Redis when you need caching or real-time. Consider MongoDB only for genuinely document-oriented data.'''
    ),
    (
        "thinking/advanced-tradeoff-build-vs-buy",
        "Should we build our own authentication system or use Auth0/Clerk/Firebase Auth? We're a B2B SaaS with enterprise customers who need SSO, MFA, and RBAC.",
        r'''<think>
Build vs buy analysis for authentication. This is one of the clearest "buy" decisions in software, but let me reason through it properly.

**Requirements:**
- SSO (SAML, OIDC)
- MFA (TOTP, SMS, WebAuthn)
- RBAC (role-based access control)
- B2B (multi-tenant, org management)
- Enterprise customers (security audits, compliance)

**Cost to build:**
- SSO (SAML + OIDC): 2-4 months for one engineer
- MFA (TOTP, SMS, WebAuthn): 1-2 months
- Session management + token refresh: 1 month
- Password reset, email verification: 2 weeks
- RBAC: 1-2 months
- Security hardening: ongoing (timing attacks, brute force, credential stuffing)
- Compliance certifications: 3-6 months + $$$$
- Ongoing maintenance: 0.5 FTE forever

Total: ~6-12 months, $200K-$500K, then ongoing maintenance

**Cost to buy:**
- Auth0/Clerk: $500-$5000/month depending on users
- Integration: 1-2 weeks
- Already SOC2/GDPR compliant
- Already handles edge cases you haven't thought of

**Risk analysis:**
Building auth wrong = security breach = company-ending event for B2B SaaS. Auth is "table stakes" — it's expected to work perfectly, and you get zero competitive advantage from building it yourself.

**Exception:**
If auth IS your core product (identity provider, access management platform), then build.

Confidence: 95% buy for this scenario.
</think>

**Buy.** Authentication is one of the clearest "don't build it" decisions in software.

## Cost Comparison

| Factor | Build | Buy (Auth0/Clerk) |
|--------|-------|-------------------|
| Implementation time | 6-12 months | 1-2 weeks |
| Engineering cost | $200-500K | $500-5K/month |
| SSO (SAML/OIDC) | 2-4 months work | Checkbox in dashboard |
| MFA | 1-2 months work | Checkbox in dashboard |
| SOC2 compliance | 3-6 months + auditor fees | Already certified |
| Ongoing maintenance | 0.5 FTE | Vendor handles it |
| Security expertise needed | Must hire security engineer | Included |

## Why Auth Is Especially Bad to Build

1. **Zero competitive advantage** — No customer chooses your SaaS because you built great login. They expect it to work.

2. **Extremely high security bar** — One vulnerability in auth = data breach = enterprise customers leave. Auth vendors employ dedicated security teams.

3. **Edge cases you haven't considered:**
   - Timing-safe password comparison
   - Rate limiting per IP AND per account
   - Credential stuffing detection
   - Session fixation prevention
   - Token rotation and revocation
   - Password breach database checks
   - Adaptive MFA risk scoring
   - SAML response validation (XML signature attacks)
   - JWT algorithm confusion attacks

4. **Enterprise requirements keep growing:**
   - SCIM provisioning (user sync from AD)
   - Directory integration (LDAP, Azure AD)
   - Audit logs for every auth event
   - Custom MFA policies per org
   - Passwordless authentication
   - Step-up authentication for sensitive actions

## The Build-vs-Buy Framework

```
Build when:
  ✓ It IS your core product
  ✓ You need deep customization unavailable in any product
  ✓ Vendor lock-in is unacceptable
  ✓ You have the team to maintain it forever

Buy when:
  ✓ It's undifferentiated infrastructure (auth, email, payments)
  ✓ Time to market matters
  ✓ Security/compliance requirements are high
  ✓ Vendors do it better than you could
  ✓ Your engineering time is better spent on core product
```

## Other "Always Buy" Services

```
Authentication    → Auth0, Clerk, Firebase Auth
Payments          → Stripe, Braintree
Email delivery    → SendGrid, Postmark, SES
SMS               → Twilio
Search            → Algolia, Elasticsearch (managed)
Monitoring        → Datadog, Grafana Cloud
Error tracking    → Sentry
```

**Rule of thumb**: If it's not your core product and there's a mature vendor, buy it. Spend your engineering time on what makes your product unique.'''
    ),
    (
        "thinking/advanced-tradeoff-technical-debt",
        "We need to ship a feature in 2 weeks. The clean solution takes 4 weeks. My tech lead says 'just hack it for now and we'll refactor later.' But we said that about the last 5 features and never refactored. How do I think about this trade-off?",
        r'''<think>
This is the eternal technical debt trade-off. Let me think about it rigorously.

**The fundamental question**: Is the 2-week savings worth the ongoing cost of the hack?

**Types of technical debt:**
1. **Deliberate, prudent**: "We know this is a shortcut but the business value justifies it, and we have a plan to fix it." — Acceptable
2. **Deliberate, reckless**: "We don't have time for design" — Risky
3. **Inadvertent, prudent**: "Now we know how we should have done it" — Learning
4. **Inadvertent, reckless**: "What's architecture?" — Dangerous

The current situation sounds like repeated deliberate reckless debt — "just hack it" with no repayment plan. This compounds.

**Analyzing the specific trade-off:**
- 2-week hack saves 2 weeks now
- But each hack:
  - Slows down ALL future development in that area
  - Makes bugs harder to fix
  - Makes the eventual refactor more expensive
  - Increases onboarding time for new devs
  - Can't be easily tested

**Key insight**: "We'll refactor later" has a near-zero success rate without a concrete plan. The refactor ticket gets deprioritized because there's always another feature to ship.

**Possible approaches:**
1. Ship the hack, but ACTUALLY schedule the refactor (with a deadline)
2. Ship a "good enough" solution that's not as clean as ideal but avoids the worst debt
3. Negotiate the timeline — can we get 3 weeks instead of 2?
4. Scope down the feature to fit in 2 weeks cleanly

Let me recommend the practical middle path.
</think>

## The Honest Analysis

"Just hack it and refactor later" has a historical success rate of approximately **0%** at most companies. You said it 5 times and refactored 0 times. That's data, not pessimism.

## The Real Cost of Technical Debt

```
Week 0:  Hack saves 2 weeks! Ship fast! 🎉
Week 4:  New feature touches same area. Takes 1 extra week due to hack.
Week 8:  Bug in hacked code. 3 days to debug because nobody understands it.
Week 12: New developer onboards. Spends 2 days confused by the hack.
Week 16: Another feature. 1.5 extra weeks due to accumulated hacks.

Cumulative cost by month 4:  ~4 extra weeks
You've now SPENT more time than the clean solution would have taken.
```

## The Decision Framework

### Ask These 4 Questions

**1. Is this area going to be touched again?**
```
Yes → Build it right (debt will compound)
No  → Hack is fine (dead code doesn't accumulate interest)
```

**2. Is this a core flow or an edge case?**
```
Core flow (checkout, auth, data pipeline) → Build it right
Edge case (admin tool, rare error handler) → Hack is acceptable
```

**3. Can we scope down instead of cutting quality?**
```
"Feature X needs A, B, C, D" → Ship A and B cleanly, defer C and D
Better than shipping A, B, C, D poorly
```

**4. Can we negotiate the deadline?**
```
2 weeks for a hack → Ask for 3 weeks for a solid solution
Often possible when you explain the trade-off clearly to stakeholders
```

## The Practical Middle Path

Instead of "perfect" vs "hack," find the **minimum viable clean** solution:

```python
# HACK (don't do this):
def calculate_price(order):
    # TODO: fix this later
    if order.type == 'subscription':
        return order.base * 0.9  # Magic number, no tests, wrong for annual
    elif order.type == 'enterprise':
        return order.base * 0.7  # Hardcoded, doesn't account for seats
    # ... 50 more lines of if/elif with hardcoded values

# PERFECT (4 weeks):
# Full pricing engine with strategy pattern, database-driven rules,
# A/B testing support, price history tracking

# MINIMUM VIABLE CLEAN (2.5 weeks):
PRICING_RULES = {
    'subscription': {'discount': Decimal('0.10'), 'min_seats': 1},
    'enterprise': {'discount': Decimal('0.30'), 'min_seats': 10},
}

def calculate_price(order) -> Decimal:
    rule = PRICING_RULES.get(order.type)
    if not rule:
        raise ValueError(f"Unknown order type: {order.type}")
    discount = rule['discount']
    return (order.base_price * (1 - discount)).quantize(Decimal('0.01'))

# Not perfect, but:
# ✓ Testable
# ✓ Data-driven (easy to add new types)
# ✓ Uses Decimal for money
# ✓ Clear error handling
# ✓ Someone can understand it in 6 months
```

## Making "Refactor Later" Actually Happen

If you must take the shortcut:

1. **Create the ticket NOW** (not "someday")
2. **Set a deadline** (2 weeks after shipping the hack)
3. **Add a code comment with the ticket number** — `# HACK: See JIRA-1234 for refactor plan`
4. **Track debt metrics** — how many TODO/HACK comments exist?
5. **Allocate 20% of each sprint to debt repayment** (non-negotiable)

If you can't commit to steps 1-5, don't take the shortcut.'''
    ),
    (
        "thinking/advanced-tradeoff-consistency-models",
        "We're building a collaborative document editor where multiple users edit the same document simultaneously. What consistency model should we use? The options seem to be: locking (only one editor at a time), operational transform (like Google Docs), or CRDTs (like Figma). I need to understand the trade-offs deeply.",
        r'''<think>
This is a deep architectural trade-off with major implications. Let me analyze each approach:

**1. Pessimistic Locking (Exclusive Editing)**
- Only one user edits at a time
- Others get "read-only" until lock is released
- Simple to implement
- Terrible UX for collaboration
- Used in: SharePoint (old), SVN

**2. Optimistic Locking (Last Write Wins)**
- Multiple users edit independently
- On save, detect conflicts
- Manual merge required
- Used in: Git

**3. Operational Transform (OT)**
- Real-time collaboration
- Operations (insert, delete) are transformed against concurrent operations
- Requires a central server to order operations
- Complex algorithm — proven hard to get right
- Used in: Google Docs, Etherpad

**4. CRDTs (Conflict-free Replicated Data Types)**
- Real-time collaboration
- No central server needed (peer-to-peer possible)
- Mathematically guaranteed convergence
- Higher memory overhead (tombstones for deletions)
- Used in: Figma (sort of), Apple Notes, Linear

Let me compare across dimensions:

**Implementation complexity:**
Locking < Optimistic < CRDTs < OT
(OT is deceptively complex — many research papers on getting it right)

**User experience:**
OT ≈ CRDT > Optimistic > Locking

**Scalability:**
CRDT > OT > Locking > Optimistic
(CRDTs don't need a central server for ordering)

**Offline support:**
CRDT > Optimistic > OT > Locking
(CRDTs merge naturally after reconnection)

**Memory/bandwidth overhead:**
Locking < OT < Optimistic < CRDT
(CRDTs carry tombstones and metadata)

For a collaborative document editor specifically:
- OT is the proven choice (Google Docs has scaled it massively)
- CRDTs are the newer, theoretically cleaner choice (but more memory)
- Locking is too restrictive
- Optimistic locking doesn't work for real-time editing

Recommendation depends on requirements:
- Need offline editing? → CRDT
- Need proven at massive scale? → OT
- Simple enough use case? → CRDT with Yjs library
- Just need basic collaboration? → OT with existing library
</think>

## Deep Comparison

### 1. Locking (Exclusive Edit)
```
User A opens doc → gets lock
User B opens doc → "Read only - User A is editing"
User A closes   → lock released, B can now edit

Pros: Trivially simple, no conflicts ever
Cons: Not really "collaboration" — defeats the purpose
Use when: Simple forms, admin panels, config files
```

### 2. Operational Transform (Google Docs approach)
```
User A types "Hello" at position 0
User B types "World" at position 0 (simultaneously)

OT Server transforms B's operation:
  B's original: insert("World", pos=0)
  After transform: insert("World", pos=5)  // shifted by A's insertion

Result: "HelloWorld" on both screens
```

```
Pros:
✓ Proven at massive scale (Google Docs, 25+ years of research)
✓ Reasonable memory overhead
✓ Well-understood cursor/selection handling

Cons:
✗ Requires central server for operation ordering
✗ Algorithm is extremely hard to implement correctly
✗ Undo/redo is complex
✗ Adding new operation types requires new transform functions
✗ Offline support is difficult (need to rebase operations)
```

### 3. CRDTs (Figma-like approach)
```
User A inserts "Hello" → assigned unique position IDs
User B inserts "World" → assigned unique position IDs

No transformation needed — unique IDs define ordering.
Merge happens automatically, even after offline editing.
```

```
Pros:
✓ Mathematically guaranteed convergence
✓ Peer-to-peer possible (no central server required)
✓ Excellent offline support (merge naturally on reconnect)
✓ Adding new operation types is straightforward
✓ Simpler algorithm than OT (once you understand it)

Cons:
✗ Higher memory: deleted characters leave tombstones
✗ Document size grows over time (need garbage collection)
✗ More bandwidth (position metadata per character)
✗ Less mature ecosystem than OT
```

## Practical Implementation Options

### Option A: Use Yjs (CRDT Library) — Recommended for Most

```javascript
// Yjs — production-ready CRDT library
import * as Y from 'yjs'
import { WebsocketProvider } from 'y-websocket'

const doc = new Y.Doc()
const provider = new WebsocketProvider('wss://your-server', 'doc-id', doc)

// Shared text (CRDT handles conflicts automatically)
const ytext = doc.getText('content')
ytext.insert(0, 'Hello ')  // Automatically synced

// Bind to editor (Monaco, ProseMirror, CodeMirror, etc.)
import { MonacoBinding } from 'y-monaco'
new MonacoBinding(ytext, editor.getModel(), new Set([editor]))
```

### Option B: Use ShareDB (OT Library) — Proven for Documents

```javascript
// ShareDB — OT-based, battle-tested
const ShareDB = require('sharedb')
const richText = require('rich-text')
ShareDB.types.register(richText.type)

// Server
const backend = new ShareDB()
const connection = backend.connect()
const doc = connection.get('documents', 'doc-id')

doc.subscribe(() => {
  // OT handles concurrent edits automatically
})
```

## Decision Matrix

| Requirement | Best Choice |
|-------------|-------------|
| Real-time text editing (like Google Docs) | OT (ShareDB) or CRDT (Yjs) |
| Need offline editing | CRDT (Yjs) — clear winner |
| Peer-to-peer (no server) | CRDT (Yjs) |
| Rich text / complex documents | OT (ShareDB + rich-text) |
| Simple text / code editing | CRDT (Yjs + y-monaco) |
| Maximum proven reliability | OT (decades of Google-scale proof) |
| Fastest time to implement | CRDT (Yjs — better DX) |

## My Recommendation

For a new project in 2024+: **Yjs (CRDT)**. The DX is better, offline support is built-in, and the ecosystem (Monaco, ProseMirror, CodeMirror bindings) is mature. The memory overhead is manageable with garbage collection.

Use OT (ShareDB) only if you need rich-text OT specifically or are building on top of an existing OT-based system.'''
    ),
    (
        "thinking/advanced-tradeoff-api-versioning",
        "We need to make breaking changes to our REST API. We have 200+ API consumers. What's the best versioning strategy? I've seen URL versioning (/api/v2/), header versioning, and query parameter versioning.",
        r'''<think>
API versioning strategies — let me analyze each:

1. URL path: `/api/v1/users`, `/api/v2/users`
2. Header: `Accept: application/vnd.myapp.v2+json`
3. Query parameter: `/api/users?version=2`
4. No versioning (evolve in place with backward compatibility)

Factors:
- Developer experience (how easy to use)
- Cacheability
- Discoverability
- Implementation complexity
- Industry precedent

URL versioning is the most common and simplest to understand. Header versioning is "more REST-correct" but harder to use. Query params are a middle ground.

The real question isn't the versioning mechanism — it's the versioning STRATEGY. How do you manage multiple versions?

My strong opinion: avoid versioning as long as possible by making backward-compatible changes. When you must version, URL versioning wins on simplicity.
</think>

## The Best Strategy: Avoid Versioning

Before choosing a versioning scheme, ask: **can I avoid the breaking change entirely?**

### Backward-Compatible Changes (No Version Needed)

```json
// v1 response
{"id": 1, "name": "Alice"}

// Add a field — NOT breaking (old clients ignore it)
{"id": 1, "name": "Alice", "email": "alice@example.com"}

// Rename a field — keep both
{"id": 1, "name": "Alice", "full_name": "Alice Smith", "email": "alice@example.com"}

// Change a type — add new field, deprecate old
{"id": 1, "name": "Alice", "address": "123 Main St",
 "address_v2": {"street": "123 Main St", "city": "NYC", "zip": "10001"}}
```

**Rules for backward compatibility:**
- Adding fields: always safe
- Removing fields: breaking (don't do it)
- Renaming fields: add new, keep old (deprecated)
- Changing types: add new field with new type

### When You MUST Version

If you need to restructure the entire response shape, remove fields, or change fundamental behavior → version.

## Versioning Strategies Compared

| Strategy | Example | Pros | Cons |
|----------|---------|------|------|
| URL path | `/api/v2/users` | Simple, obvious, cacheable | URL bloat |
| Header | `Accept: application/vnd.api.v2+json` | "RESTful", clean URLs | Hard to test in browser |
| Query param | `/api/users?v=2` | Easy to use | Ugly, caching issues |
| **No versioning** | Evolve in place | No maintenance burden | Not always possible |

## My Recommendation: URL Versioning

```
GET /api/v1/users/123
GET /api/v2/users/123
```

**Why URL versioning wins:**
1. Immediately obvious which version you're using
2. Easy to test (just change the URL)
3. Load balancer can route different versions to different services
4. API docs can clearly separate versions
5. Used by: Stripe, GitHub, Twilio, Google

## Implementation Pattern

```python
# Router-based versioning (clean)
from fastapi import APIRouter

v1 = APIRouter(prefix="/api/v1")
v2 = APIRouter(prefix="/api/v2")

# v1: original format
@v1.get("/users/{id}")
def get_user_v1(id: int):
    user = db.get_user(id)
    return {"id": user.id, "name": user.name}

# v2: new format
@v2.get("/users/{id}")
def get_user_v2(id: int):
    user = db.get_user(id)
    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "created_at": user.created_at.isoformat(),
    }

app.include_router(v1)
app.include_router(v2)
```

## Version Lifecycle

```
1. Announce v2 with migration guide
2. Set deprecation date for v1 (6-12 months)
3. Add Sunset header to v1 responses
4. Monitor v1 usage — contact remaining consumers
5. Shut down v1 after sunset date
```

```python
# Deprecation header
@v1.middleware("http")
async def add_deprecation_header(request, call_next):
    response = await call_next(request)
    response.headers["Sunset"] = "Sat, 01 Jun 2025 00:00:00 GMT"
    response.headers["Deprecation"] = "true"
    response.headers["Link"] = '<https://api.myapp.com/v2>; rel="successor-version"'
    return response
```

**Rule**: Maintain at most 2 versions at a time. Supporting 3+ versions is an operational nightmare.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
