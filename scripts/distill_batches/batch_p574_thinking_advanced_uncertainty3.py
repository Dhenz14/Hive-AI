"""Phase 2F: Advanced Reasoning — Uncertainty Calibration (Part 3/5)
Explicit confidence levels and conditions that would change the answer:
microservice boundaries, async vs sync, GraphQL adoption, monolith extraction,
technical interview assessment."""

PAIRS = [
    (
        "thinking/uncertainty-microservice-boundaries",
        "We're splitting our monolith into microservices. Where should we draw the service boundaries?",
        r'''<think>
This is a high-uncertainty question because the right boundaries depend on factors I don't fully know. Let me reason about what I know and don't know, and be explicit about my confidence.

What I know:
- They have a monolith they want to split
- They want to know WHERE to draw boundaries

What I don't know (and it matters a lot):
- Team structure (Conway's Law dictates boundaries more than code does)
- Which parts of the monolith are most problematic
- Scale requirements (which components need independent scaling?)
- Data coupling (which tables are shared across features?)
- Current pain points (what's actually driving this split?)

Let me reason about boundary strategies with calibrated confidence:

Strategy 1: Follow business domains (DDD bounded contexts)
- 85% confident this is the right starting approach
- Why: Domains that change independently should be separate services
- Example: "Orders" and "Users" change for different business reasons
- Conditions that lower my confidence:
  - If the team is < 10 people, microservices may be premature
  - If domains share heavily coupled data, boundaries will be painful

Strategy 2: Follow team ownership
- 90% confident this should be a factor
- Conway's Law: system architecture mirrors org structure
- If one team owns both "billing" and "shipping," splitting them into services adds overhead with no organizational benefit
- Only split what different teams can own independently

Strategy 3: Follow scaling requirements
- 70% confident this is relevant for them (might not need it yet)
- If "search" needs 10x the compute of "user profiles," separate them
- But: premature scaling optimization is common — many monoliths handle 1M+ users

Strategy 4: Follow deployment frequency
- 75% confident this matters
- If "payments" deploys daily but "reporting" deploys monthly, separate them
- Independent deployment is one of the top benefits of microservices

What would change my answer significantly:
- If they're < 10 engineers: 80% confident they should NOT split into microservices at all
- If they have clear team boundaries already: 90% confident, follow the teams
- If they're doing this for "resume-driven development": 95% confident, don't do it
- If specific parts of the monolith are causing scaling issues: start there

I should be honest about the uncertainty and ask clarifying questions while providing the framework.
</think>

I can give you a framework, but I need to be upfront: **where to draw boundaries depends heavily on factors I'd need to ask about**. Let me give you the decision framework with explicit confidence levels.

**Question 0 — should you split at all?**

| Team size | Confidence in "split" | Recommendation |
|---|---|---|
| < 10 engineers | 20% | Probably don't. Modular monolith instead. |
| 10-30 engineers | 60% | Split 2-3 high-pain-point areas |
| 30+ engineers | 85% | Yes, bounded contexts as services |

**If you should split, where to draw lines:**

**Factor 1: Business domains (85% confident this is the primary driver)**

```
Ask: "Which parts of the system change for different business reasons?"

Good boundaries (change independently):
  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐
  │   Catalog    │  │   Orders     │  │   Payments  │
  │ - products   │  │ - cart       │  │ - billing   │
  │ - categories │  │ - checkout   │  │ - invoices  │
  │ - search     │  │ - fulfillment│  │ - refunds   │
  └─────────────┘  └──────────────┘  └─────────────┘
  Changes when:     Changes when:     Changes when:
  marketing wants   ops changes       finance/compliance
  new features      shipping rules    requirements change

Bad boundaries (high coupling):
  ┌──────────┐  ┌──────────┐
  │ Product  │  │ Product  │
  │ Write    │  │ Read     │
  │ Service  │  │ Service  │
  └──────────┘  └──────────┘
  These always change together → shouldn't be separate services
```

**Factor 2: Team ownership (90% confident this must align)**

```
Conway's Law: Service boundaries MUST match team boundaries.

If Team A owns both "users" and "auth":
  → Keep them in one service
  → Splitting creates coordination overhead with zero benefit

If Team A owns "orders" and Team B owns "payments":
  → These should be separate services
  → Independent deployment, independent on-call
```

**Factor 3: Data coupling (the hidden trap — 80% confident this is where splits fail)**

```sql
-- Find coupling: which tables are JOINed together most?
-- If "orders" always JOINs "products" and "users":

SELECT * FROM orders
JOIN users ON orders.user_id = users.id
JOIN products ON order_items.product_id = products.id;

-- Splitting orders/users/products into 3 services means:
-- This single query becomes 3 API calls + data assembly
-- Latency: 5ms → 50ms
-- Complexity: 1 transaction → distributed transaction

-- BEFORE splitting, refactor to reduce JOINs:
-- Denormalize: store user_name on orders table
-- Event-driven: orders service stores a copy of product info
```

**Factor 4: Pain points first (75% confident — practical approach)**

```
Don't split everything at once. Start with the biggest pain point:

Common pain points → suggested first extraction:
- "Deploys are slow because of X" → extract X
- "X keeps crashing and takes everything down" → extract X
- "X needs to scale differently" → extract X
- "X has different compliance requirements" → extract X

Extract ONE service. Run it for 3 months. Learn from the experience.
Then decide whether to extract more.
```

**What would change my recommendation:**

```
If you tell me...                    I'd say...
───────────────────────────────────────────────────
Team is 5 engineers                  Don't split. Use modules in the monolith.
                                     (95% confident)

You have clear team boundaries       Follow the teams exactly.
already aligned to domains           (90% confident)

Everything shares one big database   Start with a modular monolith — separate
with 50+ cross-table JOINs          code but shared DB. Split DB later.
                                     (85% confident)

One component causes 90% of outages  Extract just that one component first.
                                     (90% confident)

CEO read a blog post about           Push back. Ask "what problem are we
microservices                        solving?" If no clear answer, don't split.
                                     (80% confident you should push back)
```

**The safe starting point (regardless of specifics):**

```
Step 1: Draw domain boundaries in the existing codebase
        (separate modules/packages, NOT separate services)

Step 2: Enforce boundaries with import rules
        (orders module can't import from payments internals)

Step 3: Run this way for 2-3 months
        (validates that your boundaries are right)

Step 4: Extract the highest-pain module into a service
        (now you know the boundary is correct)

This is a "modular monolith" and it gives you 80% of microservices'
benefits with 20% of the complexity.
```'''
    ),
    (
        "thinking/uncertainty-graphql-adoption",
        "Should we switch from REST to GraphQL for our API? We have about 30 REST endpoints serving a React frontend and a mobile app.",
        r'''<think>
This is a question where the right answer depends heavily on their specific pain points. I need to be calibrated about when GraphQL actually helps vs when it's hype-driven.

What I know:
- 30 REST endpoints (moderate-sized API)
- Two clients: React web + mobile app
- They're considering GraphQL

What I don't know:
- Are they experiencing over-fetching or under-fetching?
- How different are the data needs of web vs mobile?
- How complex is their data graph (deeply nested relationships)?
- Team's GraphQL experience?

Let me assess with explicit confidence:

Scenario A: Clients have very different data needs
- Web shows full product details, mobile shows summary
- REST response is one-size-fits-all (web gets too little, mobile gets too much)
- If this is their pain: 75% confident GraphQL helps
- But also: could solve with REST response filtering (fields=name,price)

Scenario B: Many round-trips for related data
- To show a user's dashboard: /user/1 + /user/1/orders + /user/1/notifications
- 3 round trips, significant on mobile networks
- If this is their pain: 80% confident GraphQL helps (single query)
- But also: could solve with REST aggregate endpoint (/user/1/dashboard)

Scenario C: Just heard GraphQL is better
- No specific pain point with REST
- 30 endpoints is not that many
- If this is the case: 85% confident they should stay with REST
- Migration cost is real: new tooling, new patterns, caching is harder

Scenario D: Complex, deeply nested data model
- Products → variants → prices → discounts → rules
- REST requires many endpoints or very complex query params
- If this is their pain: 70% confident GraphQL helps
- GraphQL excels at graph-shaped data queries

Key uncertainties:
- Caching: REST with HTTP caching is trivial (Cache-Control headers). GraphQL caching is harder (POST requests by default, need Apollo-style normalized cache)
- File uploads: REST handles this natively. GraphQL requires multipart spec or separate endpoint
- Error handling: REST has HTTP status codes. GraphQL always returns 200 with errors in body
- Performance: GraphQL N+1 problem (resolver per field) needs DataLoader to solve
- Security: GraphQL query complexity attacks (deeply nested queries consuming resources)

My overall assessment:
- 60% confident they should NOT switch for 30 endpoints with 2 clients
- 30% confident they should incrementally add GraphQL alongside REST
- 10% confident they should do a full migration

Conditions that would change my answer:
- If over-fetching is measured and significant → moves to 50/40/10
- If they have 5+ clients with very different needs → moves to 30/50/20
- If their data is highly relational/nested → moves to 40/45/15
</think>

My honest assessment: **60% confident you should stay with REST** for 30 endpoints and 2 clients. Let me explain why, and what would change my mind.

**The confidence breakdown:**

| Option | Confidence | When it's right |
|---|---|---|
| Stay with REST | 60% | No measured over/under-fetching problem |
| Add GraphQL alongside REST | 30% | Specific pain points with data fetching |
| Full migration to GraphQL | 10% | 5+ clients with very different data needs |

**What GraphQL actually solves (and what it doesn't):**

```
✅ Solves:
  - Over-fetching: mobile gets 50 fields when it needs 5
  - Under-fetching: 3 round-trips for one screen
  - Client diversity: web, mobile, TV, watch all need different shapes
  - Schema documentation: introspection gives you auto-docs + types

❌ Doesn't solve (and makes harder):
  - Caching: REST uses HTTP cache (trivial). GraphQL needs Apollo normalized cache (complex)
  - File uploads: REST handles natively. GraphQL needs workarounds
  - Rate limiting: REST limits by endpoint. GraphQL has one endpoint
  - Error handling: REST has status codes. GraphQL returns 200 with errors in body
  - Monitoring: REST logs show "/users/42". GraphQL logs show "POST /graphql" (unhelpful)
```

**Can you solve the pain with REST first?**

```python
# Pain: over-fetching (mobile gets too much data)
# REST fix: field filtering
GET /products/42?fields=id,name,price,thumbnail
# Much simpler than adopting GraphQL

# Pain: under-fetching (multiple round trips)
# REST fix: composite endpoints
GET /users/42/dashboard
# Returns: { user: {...}, recent_orders: [...], notifications: [...] }
# One request, tailored response

# Pain: different clients need different shapes
# REST fix: different response formats via Accept header or query param
GET /products/42?view=summary  # { id, name, price }
GET /products/42?view=full     # { id, name, price, description, reviews, ... }
```

**If you DO have real pain that REST can't solve — incremental GraphQL:**

```python
# Don't migrate everything. Add GraphQL alongside REST for specific use cases.

# Keep REST for:
# - Simple CRUD operations
# - File uploads
# - Webhooks
# - Third-party integrations

# Add GraphQL for:
# - Complex data queries (dashboard, search results)
# - Mobile-optimized responses

# FastAPI + Strawberry example:
import strawberry
from strawberry.fastapi import GraphQLRouter

@strawberry.type
class Product:
    id: int
    name: str
    price: float
    description: str
    reviews: list["Review"]

@strawberry.type
class Query:
    @strawberry.field
    async def product(self, id: int) -> Product:
        return await get_product_with_reviews(id)

    @strawberry.field
    async def user_dashboard(self, user_id: int) -> "Dashboard":
        # One query replaces 3 REST calls
        return await build_dashboard(user_id)

graphql_app = GraphQLRouter(strawberry.Schema(query=Query))
app.include_router(graphql_app, prefix="/graphql")
# REST endpoints still work at /api/*
```

**What would change my recommendation:**

```
If you tell me...                         My confidence shifts to...
───────────────────────────────────────────────────────────────────
"Mobile app makes 8 API calls per screen"  → 40% REST / 45% add GraphQL
"We're adding a TV app and a watch app"    → 20% REST / 50% add GraphQL
"Our data is deeply nested (5+ levels)"    → 30% REST / 50% add GraphQL
"Team has zero GraphQL experience"         → 75% REST / 20% add GraphQL
"We already use Apollo on the frontend"    → 40% REST / 45% add GraphQL
"Our REST API is well-documented with      → 80% REST / 15% add GraphQL
 OpenAPI and clients are happy"
```

**My recommendation for your specific case (30 endpoints, 2 clients):**

1. Measure: are your clients actually suffering from over-fetching or under-fetching? If you don't have concrete evidence, you don't have the problem.
2. If yes: try field filtering and composite endpoints in REST first (1 day of work).
3. If REST fixes don't cut it: add GraphQL for the specific pain-point queries alongside REST.
4. If you find yourself adding GraphQL to most endpoints: then consider a broader migration.

Don't migrate to GraphQL because it's trendy. Migrate because you have a measured data-fetching problem that REST can't solve efficiently.'''
    ),
    (
        "thinking/uncertainty-async-sync-choice",
        "I'm building a new API endpoint that needs to call 3 external services (payment, inventory, email). Should I make these calls synchronous or asynchronous?",
        r'''<think>
The right answer depends on the dependencies between the calls and latency requirements. Let me think about this carefully.

What I need to know:
1. Are the 3 calls independent or dependent (does call B need result of call A)?
2. Are all 3 required for the response, or can some be deferred?
3. What's the acceptable response time for the endpoint?

Let me analyze each external call:
- Payment: Likely REQUIRED for the response (user needs to know if payment succeeded)
- Inventory: Likely REQUIRED before payment (verify stock before charging)
- Email: Likely DEFERRABLE (confirmation email can be sent after responding)

This suggests a hybrid approach, but let me lay out all options with confidence:

Option A: All synchronous, sequential
```
[request] → [inventory 200ms] → [payment 500ms] → [email 300ms] → [response]
Total: ~1000ms
```
- Simple to implement and reason about
- But: user waits 300ms for email they don't need to wait for
- 60% confident this is TOO slow

Option B: Synchronous but parallel (asyncio)
```
[request] → [inventory 200ms] ─┐
            [payment 500ms] ───┤ → [response after all complete]
            [email 300ms] ─────┘
Total: ~500ms (max of the three)
```
- Problem: payment should happen AFTER inventory check
- Can't parallelize dependent operations
- Also: user still waits for email
- 30% confident this is right (has dependency issues)

Option C: Critical path synchronous, non-critical async
```
[request] → [inventory 200ms] → [payment 500ms] → [response 700ms]
                                                  → [email 300ms] (background)
```
- User waits only for what matters (inventory + payment)
- Email sent in background (if it fails, retry separately)
- 85% confident this is the right approach
- The pattern: "sync for what the user is waiting on, async for side effects"

Option D: All asynchronous (event-driven)
```
[request] → [queue checkout event] → [response immediately]
Worker: [inventory] → [payment] → [email]
```
- Fastest response (~50ms)
- But: user doesn't know if payment succeeded!
- Need to poll or use WebSocket for result
- 15% confident for a checkout flow (user NEEDS payment result)
- 80% confident for something like data processing or report generation

Conditions affecting my confidence:
- If this is a checkout flow: C is strongly preferred (85%)
- If this is a background job trigger: D is strongly preferred (80%)
- If all 3 services are fast and reliable (< 100ms): A is fine (70%)
- If the email MUST succeed before responding: B with proper error handling (70%)

Let me also consider error handling:
- Sync: if payment fails, easy to return error immediately
- Async background: if email fails, need separate retry mechanism
- Full async (D): if payment fails, need to notify user out-of-band

My recommendation: Option C with proper error handling.
</think>

The answer is **almost certainly a hybrid** — sync for what the user needs, async for side effects. Let me show you why.

**Your 3 calls have different characteristics:**

| Call | User needs result? | Can fail gracefully? | Typical latency |
|---|---|---|---|
| Inventory check | Yes (is it in stock?) | No (must know) | ~100ms |
| Payment | Yes (did it charge?) | No (must know) | ~500ms |
| Email | No (confirmation is nice-to-have) | Yes (retry later) | ~300ms |

**The right pattern (85% confident):**

```python
from fastapi import FastAPI, BackgroundTasks

@app.post("/checkout")
async def checkout(
    order: OrderRequest,
    background_tasks: BackgroundTasks,
):
    # SYNCHRONOUS: User must wait for these (critical path)
    # Step 1: Check inventory (must happen before payment)
    if not await inventory_service.check_stock(order.product_id, order.quantity):
        raise HTTPException(409, "Out of stock")

    # Step 2: Process payment (user needs to know result)
    try:
        payment = await payment_service.charge(
            user_id=order.user_id,
            amount=order.total,
        )
    except PaymentError as e:
        raise HTTPException(402, f"Payment failed: {e}")

    # Create the order
    db_order = await create_order(order, payment_id=payment.id)

    # ASYNCHRONOUS: User doesn't need to wait for these
    background_tasks.add_task(
        send_confirmation_email, order.user_id, db_order.id
    )
    background_tasks.add_task(
        update_analytics, "purchase", db_order.id
    )

    # Respond immediately after payment — don't wait for email
    return {"order_id": db_order.id, "status": "confirmed"}

# Response time: ~600ms (inventory + payment)
# vs ~900ms if email was also synchronous
```

**Why not fully async (event-driven)?**

```python
# This pattern is WRONG for checkout:
@app.post("/checkout")
async def checkout(order: OrderRequest):
    await message_queue.publish("checkout_requested", order.dict())
    return {"status": "processing"}  # 50ms response!

# Problem: user doesn't know if payment succeeded
# They see "processing" and... then what?
# Need polling, WebSockets, or push notification for the result
# Much worse UX for a checkout flow

# BUT this IS the right pattern for:
# - Report generation ("we'll email you when it's ready")
# - Data import ("processing your 10,000 row CSV")
# - Video transcoding ("we'll notify you when it's done")
```

**Making the async part reliable:**

```python
# BackgroundTasks is fine for simple cases, but for reliability:

# Option 1: Celery task (retries on failure)
@celery_app.task(bind=True, max_retries=3)
def send_confirmation_email(self, user_id: int, order_id: int):
    try:
        user = get_user(user_id)
        order = get_order(order_id)
        email_service.send("order_confirmation", user.email, order=order)
    except EmailServiceError as e:
        raise self.retry(exc=e, countdown=60)  # Retry in 1 min

# Option 2: Transactional outbox (guarantees delivery)
# Write the email task to DB in the same transaction as the order
# A separate worker picks it up and sends it
```

**Decision flowchart:**

```
Does the user need the result to continue?
├── Yes → SYNCHRONOUS
│   ├── Are calls independent? → asyncio.gather() (parallel)
│   └── Are calls dependent? → await sequentially
│
└── No → ASYNCHRONOUS (background)
    ├── Must complete eventually? → Celery with retries
    └── Best-effort? → BackgroundTasks
```

**Confidence qualifiers:**

```
85% confident in sync-critical + async-sideeffect pattern when:
  - Clear distinction between "user needs this" and "nice to have"
  - Response time < 2 seconds for sync path

What would change my answer:
  - If email MUST be sent before response (regulatory): make it sync (75%)
  - If all 3 calls are < 50ms: just do them all sync (80%)
  - If the endpoint is not user-facing (webhook/cron): go fully async (85%)
  - If you need < 100ms response time: fully async + WebSocket for result (70%)
```'''
    ),
    (
        "thinking/uncertainty-monolith-extraction",
        "We want to extract the 'notification' feature from our Django monolith into a separate service. It handles email, SMS, push notifications, and in-app messages. Is this a good candidate for extraction?",
        r'''<think>
Let me evaluate whether notification is a good extraction candidate. I need to assess coupling, independence, and operational benefits.

Factors that make it a GOOD candidate:
1. Notifications are a side effect, not on the critical path
   - Order doesn't fail if email can't send
   - This means the service boundary is natural
   - Confidence: 85% good sign

2. Different scaling characteristics
   - Notifications are bursty (marketing campaign = millions at once)
   - Core app is steady-state
   - Independent scaling is valuable
   - Confidence: 80% good sign

3. Multiple channels (email, SMS, push, in-app)
   - This is a self-contained domain
   - Has its own logic (templates, rate limiting, preferences)
   - Could be reused by other services in the future
   - Confidence: 85% good sign

4. Third-party integrations
   - Email → SendGrid/SES, SMS → Twilio, Push → Firebase
   - Isolating these dependencies makes the monolith simpler
   - If Twilio changes API, only notification service needs updating
   - Confidence: 80% good sign

Factors that make it a RISKY candidate:
1. User preferences coupling
   - "Don't email me about marketing" is stored... where?
   - If preferences are in the monolith's User model → tight coupling
   - Notification service needs to query user preferences
   - Confidence: 60% this will be a pain point

2. Template rendering
   - Email templates reference Django models (order.items, user.name)
   - If templates need rich data from the monolith → lots of data passing
   - Confidence: 65% this will cause complexity

3. In-app notifications specifically
   - These are read/written by the web UI
   - If the web app reads from the notification service DB, you've added latency
   - If you duplicate the data, you have consistency issues
   - Confidence: 70% in-app notifications should stay in the monolith

4. Transactional consistency
   - "Create order AND send confirmation" — what if order succeeds but notification service is down?
   - This is fine (eventual consistency is OK for notifications)
   - But some teams struggle with this mental model
   - Confidence: 80% this is manageable

Overall assessment:
- 70% confident this is a good extraction candidate
- BUT 80% confident in-app notifications should stay in the monolith
- 85% confident email/SMS/push can be extracted successfully
- 60% confident the team will underestimate the data coupling issues

Recommendation: Extract email/SMS/push into a notification service, keep in-app notifications in the monolith for now.
</think>

Notifications are generally a good extraction candidate — but with caveats. Let me give you a calibrated assessment.

**Overall: 70% confident this is a good extraction, with a major caveat**

**What makes notifications a strong candidate:**

```
✅ Side effect, not critical path (85% confident: good sign)
   Order succeeds even if email fails → natural service boundary

✅ Different scaling profile (80% confident: good sign)
   Marketing blast = 1M emails in 1 hour
   Normal traffic = 100 emails/hour
   Independent scaling saves money

✅ Self-contained domain (85% confident: good sign)
   Templates, rate limiting, preferences, delivery tracking
   Multiple channels (email, SMS, push) = coherent service

✅ Isolates third-party dependencies (80% confident: good sign)
   SendGrid, Twilio, Firebase SDKs stay out of your monolith
```

**The caveat that could bite you (separate by channel):**

```
⚠️  In-app notifications are DIFFERENT from email/SMS/push

Email/SMS/Push:                    In-app messages:
- Fire and forget                  - Read from UI on every page load
- Async is natural                 - Need low-latency reads
- External delivery                - Internal delivery
- User doesn't see delay           - User sees delay as slow UI

70% confident: Extract email/SMS/push
30% confident: Keep in-app notifications in the monolith (for now)
```

**The recommended architecture:**

```
Monolith (Django):
┌────────────────────────────────────────────┐
│  Order created → publish event             │
│  In-app notifications (read/write, fast)   │
│  User notification preferences (stays here)│
└──────────────┬─────────────────────────────┘
               │ Event: "order.created"
               ▼
Notification Service (new):
┌────────────────────────────────────────────┐
│  Subscribe to events                       │
│  Fetch user preferences (API call back)    │
│  Render templates                          │
│  Route to channel: email/SMS/push          │
│  Handle retries, rate limiting, tracking   │
└────────────────────────────────────────────┘
```

**Implementation approach:**

```python
# Step 1: In the monolith, publish events instead of sending directly
# BEFORE (tight coupling):
def create_order(order_data):
    order = Order.objects.create(**order_data)
    send_email("order_confirmation", order.user.email, context={"order": order})
    send_sms(order.user.phone, f"Order {order.id} confirmed!")
    send_push(order.user_id, "Order confirmed!")

# AFTER (event-driven):
def create_order(order_data):
    order = Order.objects.create(**order_data)
    publish_event("order.created", {
        "order_id": order.id,
        "user_id": order.user_id,
        "total": str(order.total),
        "items": [{"name": i.name, "qty": i.quantity} for i in order.items.all()],
    })
    # Notification service handles all channels
```

```python
# Step 2: Notification service consumes events
# notification_service/consumers.py
@event_handler("order.created")
async def handle_order_created(event):
    user_id = event["user_id"]

    # Fetch preferences (API call to monolith or cached)
    prefs = await get_user_preferences(user_id)

    if prefs.email_enabled:
        await send_email(
            template="order_confirmation",
            to=prefs.email,
            context=event,
        )

    if prefs.sms_enabled:
        await send_sms(
            to=prefs.phone,
            message=f"Order {event['order_id']} confirmed! Total: ${event['total']}",
        )

    if prefs.push_enabled:
        await send_push(
            user_id=user_id,
            title="Order confirmed!",
            body=f"Total: ${event['total']}",
        )
```

**Risks to plan for:**

```
Risk: Template data coupling (65% confident this will cause pain)
  Problem: Email template needs order.items[0].product.image_url
  You'd need to either:
  a) Pass ALL data in the event (makes events huge)
  b) Have notification service call back to monolith API (adds latency + coupling)
  c) Use pre-rendered HTML in the event (limits template flexibility)

  Recommendation: Start with (a) for simple templates, add (b) for complex ones.
  Accept some data duplication in events — it's the pragmatic choice.

Risk: Notification service down (80% confident this is manageable)
  If the service is down, events queue up in the message broker.
  When it comes back, it processes the backlog.
  Users get delayed notifications, not lost ones.
  This is acceptable for email/SMS/push.

Risk: User preferences (60% confident this will evolve)
  Start by calling the monolith API for preferences.
  If that becomes a bottleneck, sync preferences to notification service DB.
  Don't over-engineer upfront.
```

**Migration timeline suggestion:**

```
Week 1-2: Add event publishing to monolith (keep existing notification code)
Week 3-4: Build notification service, consume events, send email
Week 5: Add SMS and push to notification service
Week 6: Remove email/SMS/push code from monolith
Week 7-8: Monitor, fix edge cases, optimize

Keep in-app notifications in monolith for now.
Revisit in 6 months when you understand the service boundary better.
```

Bottom line: extract email/SMS/push — it's a natural boundary. Keep in-app notifications in the monolith. The biggest risk is template data coupling, so keep templates simple at first.'''
    ),
    (
        "thinking/uncertainty-technical-interview-assessment",
        "I'm reviewing a candidate's take-home project. The code works but has no tests, inconsistent error handling, and uses some older patterns. Should I pass or fail them?",
        r'''<think>
This is inherently uncertain because code quality is only one signal. Let me think about what the code tells me and what it doesn't.

What the positive signals suggest:
- "Code works" — they can deliver a working solution
- They completed the take-home — follow-through
- Presumably solves the problem correctly

What the negative signals suggest:
- No tests — either doesn't know how to test, doesn't think it's important, or ran out of time
- Inconsistent error handling — possibly inexperienced, possibly rushed
- Older patterns — could be experienced (old habits) or inexperienced (learned from old tutorials)

But I'm uncertain because:
1. Take-home context matters enormously
   - How long were they given? If 2 hours: no tests is forgivable. If 1 week: it's a signal.
   - What was the rubric? Did you ask for tests? If not, their absence isn't a negative.
   - What's the role level? Junior? These issues are expected. Senior? More concerning.

2. "Older patterns" is ambiguous
   - Using callbacks instead of async/await? → Outdated knowledge
   - Using classes instead of hooks (React)? → Different preference, not wrong
   - Using for loops instead of map/filter? → Might be from a different language background

3. Code in a take-home ≠ production code
   - People often skip things they'd do at work (tests, error handling, docs)
   - Take-home projects favor finishing over polish
   - Interview anxiety affects code quality

My confidence levels:
- If JUNIOR role, 2-hour time limit: 70% pass (these issues are normal)
- If JUNIOR role, 1-week deadline: 55% pass (should have added some tests)
- If SENIOR role, 2-hour time limit: 50% pass (want to see test instinct even in 2 hours)
- If SENIOR role, 1-week deadline: 30% pass (no tests in a week is a strong signal)

What would make me confident to pass:
- Code is logically well-structured (even without tests)
- The solution approach is thoughtful (not just "first thing that works")
- Problem-solving is strong (correct algorithm, handles edge cases in logic if not in error handling)
- "Older patterns" are just style, not fundamental misunderstanding

What would make me confident to fail:
- Code works by accident (brute force, no understanding of approach)
- Missing fundamental security practices (SQL injection, no input validation)
- Cannot explain their own code in the follow-up interview
- "No tests" because they don't know how, not because they ran out of time

The best approach: bring them to an interview to discuss the code. The code is a conversation starter, not a verdict.
</think>

This is genuinely uncertain — code alone doesn't tell you enough. Let me give you a framework with explicit confidence levels.

**My assessment depends heavily on context:**

| Role Level | Time Given | No Tests | Inconsistent Errors | Old Patterns | Overall |
|---|---|---|---|---|---|
| Junior, 2-4 hours | Expected | Minor flag | Expected | **70% pass** |
| Junior, 1 week | Yellow flag | Yellow flag | Minor flag | **55% pass** |
| Mid, 2-4 hours | Yellow flag | Yellow flag | Minor flag | **55% pass** |
| Mid, 1 week | Red flag | Red flag | Yellow flag | **35% pass** |
| Senior, 2-4 hours | Red flag | Red flag | Yellow flag | **30% pass** |
| Senior, 1 week | Dealbreaker? | Red flag | Red flag | **20% pass** |

**What to actually evaluate (beyond the surface issues):**

```
More important than tests/error handling:

1. Does the code THINK clearly?
   ✓ Clear function names that describe intent
   ✓ Logical data flow (not spaghetti)
   ✓ Sensible abstractions (not over or under-engineered)
   ✗ Working by accident (copied from Stack Overflow, doesn't understand it)

2. Does the solution approach show problem-solving?
   ✓ Correct algorithm choice
   ✓ Handles core edge cases in logic
   ✓ Shows awareness of trade-offs (comments like "chose X over Y because...")
   ✗ Brute force when better solutions are obvious

3. Is the code SAFE?
   ✓ No SQL injection, XSS, or obvious security holes
   ✓ Input validation present (even if inconsistent)
   ✗ User input directly in queries/templates → serious red flag regardless of level
```

**Before deciding — check your own process:**

```
Did your instructions include:
  "Please include tests"           → No tests is a red flag
  "Focus on working solution"      → No tests is expected
  "Spend no more than 3 hours"     → No tests is understandable
  (nothing about tests/quality)    → You can't penalize what you didn't ask for

Did you provide a rubric?
  If yes: evaluate against the rubric
  If no:  evaluate potential, not polish
```

**My recommendation: invite them back to discuss the code**

```markdown
Instead of pass/fail on the code alone, use it as a conversation:

1. "Walk me through your approach"
   - Do they understand their own code?
   - Can they explain WHY, not just WHAT?

2. "If you had more time, what would you add?"
   - If they say "tests, error handling, input validation"
     → They KNOW what's missing. Strong signal.
   - If they say "nothing, it's done"
     → They don't recognize the gaps. Weak signal.

3. "How would you test this function?" (point at a complex one)
   - Can they articulate test cases?
   - Do they think about edge cases?
   - Testing ABILITY matters more than test file presence.

4. "What would break if this got 1000x more traffic?"
   - Shows scalability thinking
   - Reveals whether "older patterns" are from inexperience or just style
```

**Red flags that override everything (auto-fail regardless of level):**

```
✗ SQL injection or command injection present
✗ Plaintext password storage
✗ Code clearly copied without understanding (variable names like 'temp1', 'x')
✗ Solution doesn't actually solve the stated problem
✗ Fundamental misunderstanding of core concepts for the role
```

**Green flags that override surface issues (auto-pass to interview):**

```
✓ Elegant solution to a hard part of the problem
✓ README explaining decisions and trade-offs
✓ Comments like "I'd add tests for X, Y, Z with more time"
✓ Clean git history showing iterative problem-solving
✓ Evidence of research (tried approach A, pivoted to B)
```

Bottom line: 65% confident you should advance them to discuss the code in person, unless you see auto-fail signals. The take-home tells you if they can solve problems. The interview tells you if they can grow, communicate, and think critically about their own code.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
