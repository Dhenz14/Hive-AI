"""Phase 3C: Metacognition — Socratic Self-Questioning (Part 4)

Scenarios: "Am I introducing tight coupling?", "Could this fail silently?",
"Am I anchored on my first idea?"
"""

PAIRS = [
    (
        "thinking/meta-socratic-tight-coupling-payment",
        r'''I'm building an e-commerce checkout flow. Here's my order processing:

```python
class OrderService:
    def __init__(self):
        self.stripe = stripe
        self.sendgrid = SendGridClient(api_key=SENDGRID_KEY)
        self.inventory_db = InventoryDatabase()
        self.analytics = MixpanelClient(token=MIXPANEL_TOKEN)

    def process_order(self, order):
        # Charge payment
        charge = self.stripe.Charge.create(
            amount=order.total_cents,
            currency='usd',
            source=order.payment_token
        )

        # Update inventory
        for item in order.items:
            self.inventory_db.decrement(item.sku, item.quantity)

        # Send confirmation email
        self.sendgrid.send(
            to=order.customer_email,
            template='order_confirmation',
            data={'order_id': order.id, 'total': order.total}
        )

        # Track analytics
        self.analytics.track('purchase', {
            'order_id': order.id,
            'amount': order.total,
            'items': len(order.items)
        })

        return charge
```

Is this a good design?''',
        r'''<think>
My initial approach: The code is clear — it processes an order step by step.

Q: Am I introducing tight coupling? Let me check the dependency graph.
A: OrderService directly depends on:
  - stripe (payment provider)
  - SendGrid (email provider)
  - InventoryDatabase (internal DB)
  - Mixpanel (analytics)

If we switch from Stripe to PayPal, we modify OrderService. If we switch from SendGrid to SES, we modify OrderService. OrderService knows about EVERYTHING.

Q: What's the blast radius of a change?
A: Changing any external service requires modifying the core business logic class. This violates the Single Responsibility Principle — OrderService does payment, email, inventory, AND analytics.

Q: What happens when one step fails?
A: If payment succeeds but email fails → order is charged but no confirmation. If payment succeeds but inventory fails → oversold items. If analytics is down → the whole order fails because of a non-critical side effect.

Q: Should analytics failure really break a customer's purchase?
A: Absolutely not. Analytics is a side effect. Email is a side effect. Only payment and inventory are critical to the order. These should be decoupled.

Q: How would I test this?
A: I'd need to mock stripe, SendGrid, InventoryDatabase, and Mixpanel. That's 4 mocks for one test. A sign of too many dependencies.

Q: What's the right architecture?
A: Domain events. OrderService processes the order (payment + inventory). Then publishes an "OrderCompleted" event. Email and analytics subscribe to that event independently.

This separates critical path (payment, inventory) from side effects (email, analytics).
</think>

**This is tightly coupled.** OrderService knows about 4 external services and any change to any of them touches your core business logic.

**Problems:**
1. **Analytics failure breaks checkout** — Mixpanel down → customers can't buy
2. **Email failure breaks checkout** — SendGrid issue → charge with no confirmation
3. **4 mocks to test one class** — testing smell
4. **Vendor lock-in** — switching Stripe→PayPal means modifying order logic
5. **No partial failure handling** — all-or-nothing on unrelated operations

**Fix with domain events:**

```python
class OrderService:
    def __init__(self, payment_gateway, inventory, event_bus):
        self.payment = payment_gateway      # Interface, not Stripe
        self.inventory = inventory
        self.events = event_bus

    def process_order(self, order):
        # Critical path only
        charge = self.payment.charge(order.total_cents, order.payment_token)
        self.inventory.reserve(order.items)

        # Publish event — side effects happen independently
        self.events.publish('order_completed', {
            'order_id': order.id,
            'customer_email': order.customer_email,
            'total': order.total,
            'items': order.items,
        })
        return charge

# Side effects are independent subscribers
class EmailNotifier:
    def on_order_completed(self, event):
        try:
            send_confirmation(event['customer_email'], event['order_id'])
        except Exception:
            logger.error("Email failed, will retry", extra=event)

class AnalyticsTracker:
    def on_order_completed(self, event):
        try:
            track_purchase(event['order_id'], event['total'])
        except Exception:
            pass  # Analytics failure is acceptable
```

**What this fixes:**
- Analytics/email failures don't break checkout
- OrderService only depends on interfaces (payment, inventory)
- Switching Stripe→PayPal: implement a new PaymentGateway, don't touch OrderService
- Testing: mock 2 things (payment, inventory), not 4
- New side effects (SMS, webhooks): add a subscriber, don't modify OrderService'''
    ),
    (
        "thinking/meta-socratic-anchored-microservices",
        r'''We're starting a new SaaS product — a project management tool like a simple Trello. The team is 2 backend developers. I want to build it with microservices from the start: separate services for users, boards, cards, notifications, and file uploads. Should I?''',
        r'''<think>
My initial approach: Microservices for a project management tool...

Q: Am I anchored on the microservices hype? Let me challenge this.
A: The user wants to build microservices because it's the "modern" approach. But let me evaluate the actual situation:
  - 2 developers
  - New product (not yet proven in market)
  - Simple Trello-like tool

Q: What does a microservices architecture actually require?
A:
  - Service discovery / API gateway
  - Inter-service communication (HTTP/gRPC/message queue)
  - Distributed tracing and logging
  - Independent deployment pipelines (5 pipelines for 5 services)
  - Database per service (5 databases to manage)
  - Network failure handling between services
  - Data consistency across services (no simple JOINs)
  - Docker/Kubernetes orchestration

That's infrastructure work that could take MONTHS before you ship a single feature.

Q: With 2 developers, how many services can they effectively maintain?
A: Roughly 1-2 each. But they also need to build features, fix bugs, talk to customers. Managing 5 services means most of their time goes to infrastructure, not product.

Q: What's the biggest risk for a new SaaS product?
A: Building the wrong product. Speed of iteration matters more than architecture. A monolith lets you pivot in days. Microservices require redesigning service boundaries.

Q: Is there a middle ground?
A: Yes — a well-structured monolith with clear module boundaries. When a module genuinely needs independent scaling or the team grows to 10+, extract it.

Q: What would happen if they started with a monolith?
A: They'd ship 10x faster, iterate with customers, find product-market fit, THEN have the knowledge to make good service boundary decisions. Premature decomposition creates distributed monoliths — the worst of both worlds.
</think>

**No. Start with a monolith.** With 2 developers and an unproven product, microservices will kill your velocity.

**What microservices actually cost you:**

| Requirement | Monolith | 5 Microservices |
|------------|---------|-----------------|
| Deploy pipeline | 1 | 5 to build and maintain |
| Databases | 1 | 5 to manage |
| Inter-service calls | Function call | HTTP/gRPC + failure handling |
| Data JOINs | Simple SQL | Cross-service API calls |
| Debugging | Stack trace | Distributed tracing |
| Local dev setup | `python manage.py runserver` | docker-compose with 5 services |
| Time to first feature | Days | Weeks (after infra) |

**What you should build:**

```
project_management/
├── users/          # Module, not service
│   ├── models.py
│   ├── views.py
│   └── services.py
├── boards/
│   ├── models.py
│   ├── views.py
│   └── services.py
├── cards/
│   ├── models.py
│   ├── views.py
│   └── services.py
├── notifications/
│   └── services.py
└── uploads/
    └── services.py
```

**Same logical separation, zero distributed systems complexity.** Clear module boundaries. When you NEED to extract a service later, the boundaries are already clean.

**When to extract a microservice:**
- A specific module needs independent scaling (uploads processing 10x more than everything else)
- Team grows to 8+ developers with clear domain ownership
- A module has genuinely different infrastructure needs (different language, different scaling pattern)

**The pattern that works:**
1. Ship monolith (week 1)
2. Get customers, iterate on product (months 1-6)
3. Find product-market fit (months 6-12)
4. Extract services based on REAL scaling bottlenecks (year 2+)

Netflix, Shopify, and Etsy all started as monoliths and extracted services when they had the traffic and team to justify it.'''
    ),
    (
        "thinking/meta-socratic-silent-failure-migration",
        r'''I wrote a database migration script to add a new column and backfill data:

```python
def migrate():
    db.execute("ALTER TABLE users ADD COLUMN full_name VARCHAR(255)")

    users = db.execute("SELECT id, first_name, last_name FROM users").fetchall()
    for user in users:
        full_name = f"{user.first_name} {user.last_name}"
        db.execute(
            "UPDATE users SET full_name = %s WHERE id = %s",
            (full_name, user.id)
        )

    db.commit()
    print("Migration complete!")
```

Looks straightforward. Any issues?''',
        r'''<think>
My initial approach: Adds a column, backfills full_name from first_name + last_name.

Q: Could this fail silently? Let me think about failure modes.

Q: What if first_name or last_name is NULL?
A: f"{None} {None}" = "None None". The full_name would be the string "None None" instead of null or empty. This is a silent data corruption.

Q: What happens if the migration crashes halfway?
A: Say it processes 50,000 of 100,000 users and then fails. The ALTER TABLE already committed (DDL is auto-committed in most databases). Half the users have full_name, half don't. Running the migration again fails because the column already exists.

Q: Is this migration idempotent?
A: No. Running it twice fails on ALTER TABLE. Need "ADD COLUMN IF NOT EXISTS" or check before adding.

Q: What about the transaction?
A: ALTER TABLE is DDL — in PostgreSQL it's transactional, but in MySQL it auto-commits. The db.commit() at the end only commits the UPDATEs. If the script crashes, the column exists but data is partially backfilled.

Q: What about performance on a large table?
A: Loading ALL users into memory (fetchall) with 10M users = out of memory. Each UPDATE is a separate query — 10M individual queries will take hours. Need batch updates.

Q: What about locking?
A: ALTER TABLE ADD COLUMN in PostgreSQL acquires ACCESS EXCLUSIVE lock. The table is LOCKED for all reads and writes during the migration. On a large table, this could mean minutes of downtime.

Q: What happens to the full_name column if first_name changes later?
A: It becomes stale. Need a trigger, computed column, or application logic to keep it in sync.

Multiple silent failure modes and production safety issues.
</think>

**Multiple issues that would cause silent data corruption or downtime in production.**

**Issue 1: NULL handling silently corrupts data**
```python
# If first_name is None:
f"{None} Smith"  # → "None Smith" (string "None"!)
f"{None} {None}" # → "None None"

# Fix:
full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()
```

**Issue 2: Not idempotent — fails on re-run**
```python
# Fix: check before adding
db.execute("""
    ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255)
""")
```

**Issue 3: Loads entire table into memory**
```python
# 10M users → OOM crash
users = db.execute("SELECT ...").fetchall()  # All in memory

# Fix: batch processing
BATCH_SIZE = 1000
offset = 0
while True:
    users = db.execute(
        "SELECT id, first_name, last_name FROM users LIMIT %s OFFSET %s",
        (BATCH_SIZE, offset)
    ).fetchall()
    if not users:
        break
    for user in users:
        # ... update
    db.commit()  # Commit each batch
    offset += BATCH_SIZE
```

**Issue 4: Table lock during ALTER TABLE**
```python
# PostgreSQL: ADD COLUMN with a default locks the table
# Fix: add column as nullable (no lock), then backfill
db.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS full_name VARCHAR(255)")
# No DEFAULT — column is nullable, no table rewrite needed
```

**Issue 5: No progress tracking or error handling**
```python
# If it crashes at row 50,000 of 100,000, you don't know where to resume
# Fix: track progress, handle errors
for i, user in enumerate(users):
    try:
        # update...
        if i % 1000 == 0:
            db.commit()
            print(f"Processed {i} users")
    except Exception as e:
        logger.error(f"Failed user {user.id}: {e}")
```

**Issue 6: Data staleness**
After this migration, if someone updates first_name, full_name becomes stale. Either:
- Remove full_name and compute it in queries
- Add application logic to update full_name on name changes
- Use a database generated column (PostgreSQL 12+):
  ```sql
  ALTER TABLE users ADD COLUMN full_name VARCHAR(255)
      GENERATED ALWAYS AS (first_name || ' ' || last_name) STORED;
  ```'''
    ),
    (
        "thinking/meta-socratic-right-problem-slow-page",
        r'''Our product listing page is slow — it takes 5 seconds to load. The page shows 50 products with images, prices, and reviews. My manager wants me to add Redis caching. Should I just add caching?''',
        r'''<think>
My initial approach: Add Redis caching to speed up the product listing.

Q: Am I solving the right problem? WHY is the page taking 5 seconds?
A: "The page is slow" doesn't tell me WHERE the slowness is. Before adding caching, I need to identify the bottleneck:
  - Is it the database query?
  - Is it the API response time?
  - Is it frontend rendering?
  - Is it image loading?
  - Is it a slow network?

Q: What could cause a 5-second page load?
A: Let me think systematically:
  1. N+1 query problem: Loading 50 products, then loading reviews for each product separately = 51 queries
  2. Unindexed queries: Full table scan on products
  3. Large unoptimized images: 50 × 2MB images = 100MB to download
  4. Missing pagination: Loading ALL products, showing 50
  5. Slow third-party API: Fetching reviews from external service
  6. Frontend: Rendering 50 products with heavy JavaScript
  7. No CDN: Images served from application server

Q: Would caching even fix the actual problem?
A: If the bottleneck is image loading (most likely for a product page), Redis caching the database queries saves maybe 100ms — the page is still 4.9 seconds slow. Caching the wrong layer gives zero improvement.

Q: What should I do BEFORE adding caching?
A: MEASURE. Use browser DevTools to see:
  - Network waterfall (is it images? API calls?)
  - API response time (is the backend slow?)
  - Database query time (check slow query log)

Then fix the actual bottleneck, not the assumed one.

Q: What are the most common causes of slow product pages?
A: In my experience: unoptimized images > N+1 queries > missing indexes > everything else. Caching is rarely the first fix needed.
</think>

**Don't add caching yet. First find WHERE the 5 seconds is being spent.**

Caching is a solution to a specific problem — you don't know the problem yet. Here's how to diagnose:

**Step 1: Browser DevTools → Network tab**
```
Is it the API response time or the frontend/images?

Common findings:
- API responds in 200ms, but 50 images take 4 seconds → Image problem
- API takes 4 seconds → Backend problem
- Everything loads in 1s, but page renders slowly → Frontend problem
```

**Step 2: If backend is slow → check queries**
```python
# Enable SQL logging
import logging
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

# Common finding: N+1 queries
# BAD: 51 queries (1 for products + 50 for reviews)
products = Product.query.all()
for p in products:
    print(p.reviews)  # Each triggers a separate query

# FIX: eager loading (1-2 queries)
products = Product.query.options(joinedload(Product.reviews)).all()
```

**Most likely causes (in order of probability):**

| Cause | Fix | Impact |
|-------|-----|--------|
| Unoptimized images | Compress, resize, use WebP, add CDN | 2-3 seconds saved |
| N+1 queries | `joinedload()` or `subqueryload()` | 1-3 seconds saved |
| Missing index | `CREATE INDEX ON products(category_id)` | 1-2 seconds saved |
| Loading all products | Add pagination (LIMIT 50 OFFSET 0) | 0.5-2 seconds saved |
| No CDN for static assets | CloudFront/Cloudflare | 1-2 seconds saved |

**When caching IS the answer:**
- After you've fixed the above issues
- A specific query is still slow (>200ms) AND called frequently
- The data doesn't need real-time freshness

**What to tell your manager:** "I need 2 hours to profile the page and find the actual bottleneck. Caching might not be the fix — if images are the problem, Redis won't help at all."'''
    ),
    (
        "thinking/meta-socratic-tight-coupling-imports",
        r'''I'm building a Python web app with this structure:

```python
# views.py
from models import User, Order
from services import PaymentService, EmailService, InventoryService
from utils import format_currency, validate_email, generate_slug
from config import STRIPE_KEY, SENDGRID_KEY, DATABASE_URL
from cache import cache_response
from auth import require_login, require_admin

@require_login
def checkout_view(request):
    user = User.get(request.user_id)
    order = Order.create(user, request.cart)
    PaymentService(STRIPE_KEY).charge(order)
    InventoryService().reserve(order.items)
    EmailService(SENDGRID_KEY).send_confirmation(user, order)
    cache_response.invalidate('product_list')
    return {'order_id': order.id, 'total': format_currency(order.total)}
```

My view has 7 imports and touches 6 different modules. Is this fine?''',
        r'''<think>
My initial approach: Lots of imports, but each serves a purpose...

Q: Am I introducing tight coupling? Let me analyze the dependency graph.
A: The checkout_view directly depends on:
  - models (User, Order)
  - services (PaymentService, EmailService, InventoryService)
  - utils (format_currency)
  - config (STRIPE_KEY, SENDGRID_KEY)
  - cache (cache_response)
  - auth (decorators)

That's 6 modules with 12 imported names. This view KNOWS about payment implementation, email implementation, inventory implementation, cache invalidation details, and configuration values.

Q: What changes would require modifying this view?
A:
  - Switching payment provider → change PaymentService import and STRIPE_KEY
  - Switching email provider → change EmailService import and SENDGRID_KEY
  - Adding SMS notification → add another import and call
  - Changing cache strategy → modify invalidation call
  - Adding analytics → add yet another import and call

Every new business requirement modifies this view function.

Q: Is the view doing too much?
A: Yes. A view's job is to:
  1. Parse the request
  2. Call the appropriate business logic
  3. Format the response

This view is ORCHESTRATING the entire checkout process, including side effects. The business logic should be in a service.

Q: What's the right level of coupling for a view?
A: The view should know about ONE service:

```python
@require_login
def checkout_view(request):
    result = checkout_service.process(request.user_id, request.cart)
    return {'order_id': result.order_id, 'total': format_currency(result.total)}
```

Now the view has 2 concerns: parse request, format response. Everything else is in checkout_service.

Q: Does this just move the coupling to checkout_service?
A: Partially, yes. But that's where the orchestration BELONGS — in a service layer, not in a view. And checkout_service can use dependency injection to decouple from specific implementations.
</think>

**The view is doing too much.** It's orchestrating 4 services, managing config keys, and handling cache invalidation. That's a service layer's job, not a view's.

**Current coupling: view touches everything**
```
views.py → models, PaymentService, EmailService, InventoryService,
           config, cache, auth, utils
```

**Fix: thin view + service layer**
```python
# views.py — only parses request and formats response
from services.checkout import CheckoutService
from utils import format_currency
from auth import require_login

checkout_service = CheckoutService()

@require_login
def checkout_view(request):
    result = checkout_service.process(request.user_id, request.cart)
    return {'order_id': result.order_id, 'total': format_currency(result.total)}
```

```python
# services/checkout.py — orchestrates the business logic
class CheckoutService:
    def __init__(self, payment, inventory, notifications):
        self.payment = payment
        self.inventory = inventory
        self.notifications = notifications

    def process(self, user_id, cart):
        user = User.get(user_id)
        order = Order.create(user, cart)
        self.payment.charge(order)
        self.inventory.reserve(order.items)
        self.notifications.order_completed(user, order)  # Email is a detail
        return order
```

**What this fixes:**
- View has 3 imports instead of 7
- View doesn't know about Stripe, SendGrid, or cache
- Switching payment provider: change CheckoutService init, not the view
- Adding SMS: modify notifications service, not the view
- Testing: mock CheckoutService, not 4 individual services

**Rule of thumb for views:**
1. Parse request
2. Call ONE service method
3. Format response

If a view has more than 3-4 imports from your own code, it's probably doing too much.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
