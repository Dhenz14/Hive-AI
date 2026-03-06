"""Phase 3B: Metacognition — Socratic Approach to Architecture Decisions (Part 7)

Training the model to guide users through architecture decisions by asking
probing questions rather than prescribing solutions, helping them discover
the right architecture for their specific context.
"""

PAIRS = [
    (
        "thinking/meta-socratic-architecture-monolith-vs-micro",
        r'''We're a 5-person startup building an e-commerce platform. Should we use microservices or a monolith?''',
        r'''<think>
For a 5-person startup, the answer is almost certainly "monolith," but rather than just telling them that, I should guide them to discover why through questions about their specific context. The Socratic approach helps them build the reasoning skills to make future architecture decisions too.

Key questions to explore:
1. What's their deployment complexity tolerance?
2. Do they have ops/DevOps expertise?
3. What's their timeline to market?
4. Do they have fundamentally different scaling requirements for different components?

If they can't answer "yes" to the scaling question and "experienced" to the ops question, microservices will slow them down.
</think>

Before I give you an answer, let me ask some questions that will reveal the right choice for YOUR situation.

**Question 1: How many independent deployments can your team manage?**

With 5 people, consider: each microservice needs its own CI/CD, monitoring, error tracking, and on-call rotation. If you have 8 services, that's 8 deployment pipelines, 8 sets of logs to check, 8 services that can fail independently at 3 AM.

Can your team of 5 handle that operational load while also building features?

**Question 2: Do you have different scaling requirements for different parts?**

Think specifically:
- Does your product search need to handle 100x more traffic than your checkout?
- Does your recommendation engine need GPUs while your checkout needs none?
- Does image processing need to scale independently of order processing?

If everything scales together (which is typical for early-stage), separate services add complexity without benefit.

**Question 3: What's your time-to-market pressure?**

With microservices, before you write business logic, you need:
```
- Service discovery
- Inter-service communication (REST? gRPC? message queue?)
- Distributed tracing
- API gateway
- Docker + orchestration
- Shared authentication between services
```

With a monolith, you start writing business logic on day 1.

How many weeks can you spend on infrastructure before shipping features?

**Question 4: What does your team know?**

- Has anyone on the team built and operated microservices in production?
- Does anyone have Kubernetes experience?
- Can someone be dedicated to DevOps/infrastructure?

If the answer to all three is "no," microservices will be a learning project, not a productivity multiplier.

**What your answers probably reveal:**

If you're a 5-person startup with typical constraints:
- Time-to-market matters → monolith ships faster
- Small team → can't support the ops overhead of microservices
- Scaling needs aren't differentiated yet → monolith scales fine with a good database and caching layer
- You don't yet know where your boundaries are → premature service boundaries will be wrong

**The pragmatic path:**
```
Now:     Well-structured monolith (modular, clean boundaries in code)
         Deploy as one unit, iterate fast

Later:   When a SPECIFIC module needs independent scaling,
         extract it into a service (Strangler Fig pattern)
         This is how Shopify, GitHub, and Basecamp operate
```

**The question to ask later:** "Which specific component would benefit from being a separate service, and why?" If you can't answer that concretely, you don't need microservices yet.'''
    ),
    (
        "thinking/meta-socratic-architecture-database-choice",
        r'''We're building a social media app. Should we use PostgreSQL or MongoDB? Our data doesn't have a fixed schema because users can create custom profile fields.''',
        r'''<think>
The "flexible schema" argument for MongoDB is one of the most common architectural decisions people make for the wrong reasons. But rather than dismissing MongoDB, I should guide them to evaluate the full picture.

Key Socratic questions:
1. What queries will you run? (Social media = complex relationship queries = relational strength)
2. How flexible is the schema really? (Usually 90% is structured, 10% is flexible)
3. What else does the app need? (Transactions, joins, full-text search)
4. Have you looked at PostgreSQL's JSONB? (Best of both worlds)

I want them to discover that "flexible schema" is one requirement among many, and that PostgreSQL's JSONB often satisfies it while keeping relational strengths for the rest.
</think>

Good question. Before choosing, let me ask you some questions about how your data will actually be used.

**Question 1: What does your query pattern look like?**

Social media apps typically need:
```
- "Show me posts from people I follow" (relationship query)
- "Find mutual friends between two users" (graph traversal)
- "Show posts liked by friends" (join across 3 tables)
- "Search users by name, location, custom field" (filtering + search)
- "Get user's feed sorted by time with engagement counts" (aggregation)
```

How many of these queries involve relationships between entities? If most do, that's a strong signal toward relational databases (joins are their superpower).

**Question 2: How "schemaless" is your data really?**

Let's break down your data model:
```
Users:         id, name, email, created_at          → Fixed structure
Posts:         id, author_id, content, created_at    → Fixed structure
Followers:     follower_id, following_id, created_at → Fixed structure
Likes:         user_id, post_id, created_at          → Fixed structure
Custom fields: key, value (varying types)            → Flexible part
```

What percentage of your data is truly schema-flexible? In most "schemaless" apps, it's 5-10%. Does that 5-10% justify choosing a database optimized for flexibility at the cost of everything else?

**Question 3: Have you considered PostgreSQL's JSONB?**

```sql
-- Fixed schema for structured data (fast, indexed, type-safe)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Flexible schema for custom fields (in the same database!)
CREATE TABLE user_profiles (
    user_id INT REFERENCES users(id),
    custom_fields JSONB DEFAULT '{}'
);

-- You can query JSONB efficiently:
SELECT * FROM user_profiles
WHERE custom_fields->>'favorite_color' = 'blue';

-- You can even index JSONB fields:
CREATE INDEX idx_custom_fields ON user_profiles USING GIN (custom_fields);
```

This gives you:
- Relational power for 90% of your data (joins, transactions, constraints)
- Schema flexibility for the custom fields
- One database to operate, not two

**Question 4: What's your team's experience?**

- Who knows SQL on your team? → PostgreSQL is familiar
- Who knows MongoDB query syntax? → Different learning curve
- Who will manage the database in production? → PostgreSQL has more DBA tooling and community knowledge

**Question 5: What happens when you need transactions?**

Social media example: "User A sends a message to User B, which creates a notification and updates the unread count." This needs:
```
START TRANSACTION;
  INSERT INTO messages (...);
  INSERT INTO notifications (...);
  UPDATE users SET unread_count = unread_count + 1 WHERE id = $recipient;
COMMIT;
```

PostgreSQL handles this natively. MongoDB added transactions in 4.0+, but they're more complex and have limitations.

**What your answers likely point to:**

Given that social media is relationship-heavy, mostly structured, and needs transactions, PostgreSQL with JSONB for flexible fields is likely the better fit. But I want YOU to make that decision based on YOUR answers, not my recommendation.'''
    ),
    (
        "thinking/meta-socratic-architecture-event-driven",
        r'''Our team lead wants to move to event-driven architecture. Everything would communicate through a message queue. Is this a good idea?''',
        r'''<think>
Event-driven architecture is powerful but often adopted without understanding the tradeoffs. The Socratic approach should help them evaluate whether their specific problems require event-driven architecture or whether the team lead is chasing a pattern they read about.

Key questions:
1. What problem is this solving? (If they can't articulate it, red flag)
2. What's currently painful about synchronous communication?
3. Can they handle eventual consistency?
4. Do they have the operational maturity for message queue infrastructure?
</think>

Before evaluating the architecture, let me ask: what problem is this solving?

**Question 1: What's painful about your current architecture?**

Be specific:
- (a) "Services are tightly coupled — changing one breaks others"
- (b) "One slow service makes everything slow"
- (c) "We need to process things asynchronously (emails, reports, etc.)"
- (d) "We want to add new consumers of events without modifying producers"
- (e) "Our team lead read about it and thinks it sounds good"

If (a)-(d): event-driven architecture may help. Let's dig deeper.
If (e): this is architecture by hype, and you should push back with specific questions.

**Question 2: Can your business logic handle eventual consistency?**

Event-driven means asynchronous. That means:
```
Synchronous (current):
  User clicks "Buy" → Order created → Inventory updated → Confirmation shown
  All happens in one request. User sees result immediately.

Event-driven:
  User clicks "Buy" → Order event published → "Order submitted" shown
  [Later] Inventory service processes event → updates stock
  [Later] Email service processes event → sends confirmation

  What if inventory is out of stock when the event is processed?
  The user already saw "Order submitted."
```

Is your product OK with showing "processing" instead of instant confirmation? Which operations MUST be synchronous?

**Question 3: Are you prepared for these operational realities?**

```
Message queue infrastructure:
  - What happens when the queue goes down? (Everything stops)
  - Who monitors queue depth? (Growing queue = consumer can't keep up)
  - How do you handle message ordering? (Messages can arrive out of order)
  - How do you handle duplicate messages? (At-least-once delivery)
  - How do you debug a failed event? (No stack trace across services)
  - How do you replay events after a bug fix?
```

**Question 4: What does "everything through a queue" mean for debugging?**

Currently, when something goes wrong:
```
Synchronous: Stack trace shows exactly what happened, in order
Event-driven:
  1. Check producer logs — was the event published?
  2. Check message queue — was it delivered?
  3. Check consumer logs — was it processed?
  4. Check DLQ — did it fail and end up in the dead letter queue?
  5. Check timing — did events arrive out of order?

Debugging time: 5 minutes → 2 hours
```

Does your team have distributed tracing set up? If not, start there before going event-driven.

**My Socratic suggestion:**

Instead of "everything through a queue," answer this: **which specific interactions benefit from being asynchronous?**

```
Probably should be synchronous:
  - User authentication
  - Reading data for display
  - Input validation
  - Payment processing (user waits for result)

Good candidates for events:
  - Sending emails/notifications
  - Updating search indexes
  - Analytics/audit logging
  - Generating reports
  - Syncing data to external systems
```

Start by making the clearly async operations event-driven. Keep the synchronous paths synchronous. Evaluate after 3 months whether more should be converted.

**The question to ask your team lead:** "Which specific problem does event-driven architecture solve for us that we can't solve more simply?"'''
    ),
    (
        "thinking/meta-socratic-architecture-caching-layer",
        r'''Should we add a Redis caching layer in front of our database? Our API latency is around 200ms and we want to get it under 50ms.''',
        r'''<think>
200ms to under 50ms is a specific, measurable goal. Rather than immediately saying "yes, add Redis," I should guide them to understand WHERE the 200ms is being spent. Caching only helps if the database is the bottleneck.

Socratic questions:
1. Where is the 200ms? (DB? Application code? Network? Serialization?)
2. What's the read vs write ratio? (Caching helps reads, not writes)
3. What's the cache invalidation strategy? (Hardest part of caching)
4. Can you optimize the query instead? (Often faster and simpler)
</think>

200ms to 50ms is a clear goal. Before adding Redis, let me ask some questions to see if caching is the right tool.

**Question 1: Where is the 200ms?**

Can you measure this?
```python
import time

@app.get("/api/products")
async def list_products():
    t0 = time.perf_counter()

    # Database
    t1 = time.perf_counter()
    products = await db.fetch_all("SELECT ...")
    t2 = time.perf_counter()

    # Business logic
    result = process_products(products)
    t3 = time.perf_counter()

    # Serialization
    response = jsonify(result)
    t4 = time.perf_counter()

    print(f"DB:{(t2-t1)*1000:.0f}ms Logic:{(t3-t2)*1000:.0f}ms "
          f"Serialize:{(t4-t3)*1000:.0f}ms Total:{(t4-t0)*1000:.0f}ms")
    return response
```

What do you see?
```
Scenario A: DB:180ms Logic:10ms Serialize:10ms → Fix the query
Scenario B: DB:20ms  Logic:170ms Serialize:10ms → Fix the business logic
Scenario C: DB:20ms  Logic:10ms  Serialize:170ms → Fix serialization
Scenario D: DB:180ms Logic:5ms   Serialize:5ms (inherently expensive query) → Caching IS the answer
```

Only Scenario D justifies adding Redis. The others have cheaper fixes.

**Question 2: If the database IS the bottleneck, have you tried these first?**

```sql
-- Check for missing indexes
EXPLAIN (ANALYZE, BUFFERS) SELECT ... ;  -- Your slow query

-- Common 10x improvements:
-- Add missing index:     1 minute fix, 0 additional infrastructure
-- Rewrite N+1 queries:   1 hour fix
-- Add a database index:  Instant, no new components
-- Increase work_mem:     Config change
```

Would any of these get you from 180ms to under 50ms without adding a new component?

**Question 3: If you still need caching, what's your read/write ratio?**

```
Reads per second:  ___
Writes per second: ___

If reads >> writes (100:1): Caching is very effective
If reads ≈ writes (1:1):   Caching helps less, invalidation is complex
```

**Question 4: How stale can the data be?**

```
Product catalog: 5 minutes stale is fine
  → Cache with TTL of 300 seconds, simple to implement

User's own data (profile, cart): Must be current
  → Cache invalidation on every write, more complex

Financial data: Can never be stale
  → Caching is risky, optimize the query instead
```

**Question 5: If you add Redis, what's your invalidation strategy?**

This is the hardest part:
```
When a product is updated, you must:
  - Invalidate the product cache entry
  - Invalidate any list/search cache that includes this product
  - Invalidate any aggregation cache that counts/summarizes products
  - Handle the race condition: cache invalidated, new request arrives
    before the DB write is committed → cache repopulated with old data
```

Have you thought through cache invalidation for your specific data model?

**My guidance based on your answers:**

Answer the questions above, then:
- If the query can be optimized: do that first (minutes, not days)
- If caching is needed AND data can be stale: add Redis with TTL
- If caching is needed AND data must be current: consider materialized views or denormalization instead
- If you add Redis: start with one endpoint, measure the improvement, then expand'''
    ),
    (
        "thinking/meta-socratic-architecture-api-gateway",
        r'''We have 6 microservices and users hit them directly. Someone suggested adding an API gateway. When is that worth the complexity?''',
        r'''<think>
API gateway is a common addition to microservice architectures. Rather than just saying "yes, add one," I should help them evaluate whether they need one based on their specific pain points.

The Socratic approach: identify what problems they currently have that a gateway would solve, and whether those problems exist yet.

Key questions:
1. What problems are they experiencing with direct service access?
2. Do they have cross-cutting concerns (auth, rate limiting, CORS)?
3. Are they duplicating logic across services?
4. Is the client complexity manageable?
</think>

Let me help you decide by asking about your current pain points.

**Question 1: What does your client code look like right now?**

With 6 services accessed directly, your frontend probably does:
```javascript
// Does your frontend look like this?
const user = await fetch('https://user-service.internal/users/123');
const orders = await fetch('https://order-service.internal/orders?user=123');
const recommendations = await fetch('https://rec-service.internal/rec/123');
const notifications = await fetch('https://notif-service.internal/count/123');

// Is this painful? How many API calls per page load?
```

If your frontend makes 3+ calls to different services per page load, a gateway that aggregates them into one call is valuable. If most pages hit one service, the complexity isn't worth it.

**Question 2: Where does authentication happen?**

```
Option A (current?): Each service validates JWT independently
  → auth logic duplicated 6 times
  → if auth changes, update 6 services
  → if one service has a bug, security gap

Option B (with gateway): Gateway validates JWT, passes user context
  → auth logic in one place
  → services trust the gateway's user header
  → single point of auth enforcement
```

Is duplicated auth logic causing bugs or slowing feature development?

**Question 3: Do you have cross-cutting concerns duplicated across services?**

Check each box that applies:
```
- [ ] Rate limiting implemented in each service separately
- [ ] CORS headers configured in each service
- [ ] Request logging duplicated across services
- [ ] Error format varies between services
- [ ] SSL termination handled per-service
- [ ] API versioning strategy differs between services
```

Each checked box is a point in favor of a gateway. If none are checked, you may not need one yet.

**Question 4: Who are your API consumers?**

```
Internal frontend only:
  → Gateway is nice-to-have for aggregation
  → You control the client, so complexity is manageable

Mobile app + web + third-party integrations:
  → Gateway is important for consistent interface
  → Different clients need different response shapes (BFF pattern)

Public API for external developers:
  → Gateway is essential for rate limiting, key management, documentation
```

**Question 5: What's your operational capacity?**

An API gateway is another service that:
- Must have high availability (it's on the critical path for ALL traffic)
- Needs monitoring and alerting
- Can be a single point of failure if not configured correctly
- Adds latency (typically 1-5ms)

Can your team operate one more critical service?

**Decision framework based on your answers:**

```
Checked 0-1 cross-cutting concerns + internal frontend only:
  → Skip the gateway, use a reverse proxy (nginx) for routing

Checked 2-4 + multiple client types:
  → Add a lightweight gateway (Kong, Traefik, or custom BFF)

Checked 4+ + public API:
  → API gateway is essential (Kong, AWS API Gateway, or similar)

Current pain is mostly routing:
  → Just use nginx or Traefik as a reverse proxy, not a full gateway
```

What's causing you the most pain today? That determines whether a gateway is the right investment or whether a simpler solution works.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
