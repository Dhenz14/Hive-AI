"""Phase 3E: Metacognition — Learning From Mistakes (Part 4)

Additional pairs for scenarios 4-5: wrong abstraction, premature optimization.
"""

PAIRS = [
    (
        "thinking/meta-mistakes-wrong-abstraction-base-class",
        r'''I created a base class for all our API integrations but now every new integration requires overriding most methods and the base class keeps growing:

```python
class BaseAPIIntegration:
    def authenticate(self): ...
    def make_request(self, method, url, **kwargs): ...
    def parse_response(self, response): ...
    def handle_rate_limit(self, response): ...
    def handle_pagination(self, response): ...
    def retry_on_failure(self, func, max_retries=3): ...
    def transform_data(self, data): ...
    def validate_config(self): ...
    def health_check(self): ...

class StripeIntegration(BaseAPIIntegration):
    # Overrides 7 of 9 methods...

class TwilioIntegration(BaseAPIIntegration):
    # Overrides 6 of 9 methods, adds 3 new ones...
```

The base class was supposed to reduce duplication but it's become a burden.''',
        r'''<think>
I made an error: I created an abstraction before understanding the actual commonality between integrations. The base class assumes all API integrations share the same structure, but they don't.

The mistake was: premature abstraction based on superficial similarity. "They're all API integrations" → "they must share a base class." But Stripe (payment API with idempotency keys) and Twilio (messaging API with webhooks) have fundamentally different interaction patterns.

The root cause was: inheritance bias — reaching for a class hierarchy as the first tool for code reuse. When most subclasses override most methods, the base class isn't capturing real shared behavior — it's just imposing a structure that doesn't fit.

Generalizable lesson: If subclasses override more than half the base class methods, the abstraction is wrong. Prefer composition over inheritance. Extract only the truly shared behavior into small, focused utilities, and let each integration compose what it needs.

Checklist item: Before creating a base class, list the methods. For each, ask: "Will ALL subclasses use the same implementation?" If fewer than half, don't create the base class.

Similar situations where this lesson applies:
1. AbstractRepository pattern where every repo has different query patterns
2. BaseController in web frameworks where each endpoint is unique
3. Generic "BaseService" classes that every service overrides differently
</think>

**The abstraction is wrong.** When most subclasses override most methods, the base class provides pain, not reuse.

**The fix — composition with small utilities:**

```python
# Instead of a monolithic base class, extract small reusable pieces:

class RetryPolicy:
    def __init__(self, max_retries=3, backoff=1.0):
        self.max_retries = max_retries
        self.backoff = backoff

    def execute(self, func):
        for attempt in range(self.max_retries):
            try:
                return func()
            except TransientError:
                time.sleep(self.backoff * 2**attempt)
        raise MaxRetriesExceeded()

class RateLimiter:
    def __init__(self, requests_per_second):
        self.rps = requests_per_second
        # ...

# Each integration composes what it needs:
class StripeIntegration:
    def __init__(self, api_key):
        self.client = httpx.Client(base_url="https://api.stripe.com")
        self.retry = RetryPolicy(max_retries=3)
        self.rate_limiter = RateLimiter(rps=25)

class TwilioIntegration:
    def __init__(self, account_sid, auth_token):
        self.client = httpx.Client(base_url="https://api.twilio.com")
        self.retry = RetryPolicy(max_retries=5, backoff=2.0)
        # No rate limiter needed for Twilio
```

**The lesson: wait for 3 concrete examples before abstracting.** If you'd built Stripe, Twilio, and SendGrid integrations FIRST, you'd see what they actually share (retry logic, maybe HTTP client setup) and what they don't (everything else). The abstraction would be small and correct.

**Signs your abstraction is wrong:**
- Subclasses override > 50% of base methods
- The base class keeps growing with new methods
- New subclasses need to "work around" the base class
- You find yourself adding `if isinstance()` checks'''
    ),
    (
        "thinking/meta-mistakes-wrong-abstraction-generic-handler",
        r'''I built a generic event handler system but it's become a nightmare to debug:

```python
class EventBus:
    handlers = defaultdict(list)

    @classmethod
    def register(cls, event_type, handler):
        cls.handlers[event_type].append(handler)

    @classmethod
    def emit(cls, event_type, **data):
        for handler in cls.handlers[event_type]:
            handler(**data)

# Usage scattered across codebase:
EventBus.register("user_created", send_welcome_email)
EventBus.register("user_created", create_default_workspace)
EventBus.register("user_created", notify_admin)
EventBus.register("order_placed", reduce_inventory)
EventBus.register("order_placed", send_confirmation)
```

When something goes wrong with user creation, I have no idea which handler failed or what order they ran in. The event bus was supposed to decouple things but it's made everything harder to understand.''',
        r'''<think>
I made an error: I created an event bus for what should have been explicit function calls. The event bus adds indirection without real benefits in this case.

The mistake was: applying a pattern (event-driven architecture) where it doesn't fit. Event buses are valuable for truly decoupled systems (microservices, plugins, cross-boundary communication). For a monolithic application where you control all the handlers, explicit function calls are clearer and easier to debug.

The root cause was: premature decoupling — separating things that actually belong together. When user creation always needs a welcome email, workspace, and admin notification, those aren't "events" — they're steps in a process. Making them implicit through an event bus just hides the workflow.

Generalizable lesson: Indirection has a cost. Event buses, dependency injection, observer patterns — all trade explicitness for flexibility. Only use them when you actually need the flexibility (e.g., plugins, cross-service communication, truly independent concerns). For a monolith, explicit calls are almost always better.

Checklist item: Before adding an event bus/observer, ask: "Do the producer and consumer actually need to be decoupled? Will there be producers I don't control?"

Similar situations where this lesson applies:
1. Overusing dependency injection when there's only one implementation
2. Using message queues between components that could just call each other
3. Abstract factory pattern when you only ever create one type
</think>

**The event bus is the wrong abstraction here.** You've hidden a simple workflow behind indirection.

**What you have:** Implicit, unordered, hard-to-debug event handling.
**What you need:** An explicit, ordered, debuggable workflow.

**Fix — just write the workflow explicitly:**
```python
def create_user(user_data):
    user = db.create(User, **user_data)

    # Clear, ordered, debuggable:
    send_welcome_email(user)
    create_default_workspace(user)
    notify_admin_of_new_user(user)

    return user

def place_order(order_data):
    order = db.create(Order, **order_data)

    reduce_inventory(order)
    send_order_confirmation(order)

    return order
```

**Benefits of explicit calls over event bus:**
- Stack traces show you exactly what failed and where
- You control execution order
- You can see the full workflow by reading one function
- IDE "go to definition" works
- You can add error handling per step

**When an event bus IS the right choice:**
- Plugin systems where you don't control the handlers
- Cross-service communication (microservices)
- Truly optional side effects (analytics, logging)
- When the same event has 10+ handlers added by different teams

**The lesson: don't decouple things that belong together.** If you control both the producer and consumer and they always run together, an explicit function call is better than an event bus. Indirection is a cost, not a feature.'''
    ),
    (
        "thinking/meta-mistakes-wrong-abstraction-dry-violation",
        r'''I followed DRY strictly and extracted a shared function, but now changes to one caller break the other:

```python
def format_entity_display(entity, entity_type):
    """Shared formatter for users and products"""
    if entity_type == "user":
        name = f"{entity.first_name} {entity.last_name}"
        subtitle = entity.email
    elif entity_type == "product":
        name = entity.title
        subtitle = f"${entity.price:.2f}"

    badges = []
    if entity_type == "user" and entity.is_admin:
        badges.append("Admin")
    if entity_type == "user" and entity.is_verified:
        badges.append("Verified")
    if entity_type == "product" and entity.stock == 0:
        badges.append("Out of Stock")
    if entity_type == "product" and entity.is_featured:
        badges.append("Featured")

    return {"name": name, "subtitle": subtitle, "badges": badges}
```

Every time we add a feature to user display, we risk breaking product display.''',
        r'''<think>
I made an error: I merged two unrelated functions because they had superficially similar structure (name + subtitle + badges). But "user display" and "product display" are different concepts that evolve independently.

The mistake was: applying DRY to coincidental similarity rather than genuine duplication. DRY means "don't repeat knowledge" — but user formatting and product formatting are different knowledge, even if the code structure looks similar.

The root cause was: treating DRY as an absolute rule. DRY is about avoiding duplicated LOGIC, not duplicated CODE. Two pieces of code that look the same but change for different reasons should NOT be merged.

Generalizable lesson: Duplication is far cheaper than the wrong abstraction. If two pieces of code look similar but serve different purposes and change for different reasons, let them be separate. The "wrong abstraction" (merging unrelated concerns) is worse than "a little duplication."

Checklist item: Before extracting "shared" code, ask: "Do these callers change for the same reason?" If not, the similarity is coincidental and shouldn't be merged.

Similar situations where this lesson applies:
1. Shared validation logic between create and update endpoints (they diverge over time)
2. Shared UI components for different pages (they need different behaviors)
3. Shared database query builders for different domains
</think>

**Split it back into two functions.** This isn't real duplication — it's coincidental similarity.

```python
def format_user_display(user):
    return {
        "name": f"{user.first_name} {user.last_name}",
        "subtitle": user.email,
        "badges": [
            *(["Admin"] if user.is_admin else []),
            *(["Verified"] if user.is_verified else []),
        ],
    }

def format_product_display(product):
    return {
        "name": product.title,
        "subtitle": f"${product.price:.2f}",
        "badges": [
            *(["Out of Stock"] if product.stock == 0 else []),
            *(["Featured"] if product.is_featured else []),
        ],
    }
```

**Why the merged version was wrong:**
- Adding "Premium" badge to users risks breaking product display
- The `if entity_type ==` branches are a code smell — they mean you merged two things that shouldn't be merged
- Each function evolves independently for different business reasons

**The real DRY principle:** Don't Repeat *Knowledge*, not "don't repeat code structure." Two functions with similar structure but different purposes are NOT violations of DRY.

**Rules of thumb:**
- If merged code has `if type == X` / `if type == Y` branches → split it
- If changing one caller's behavior requires touching another caller's code → wrong abstraction
- "A little duplication is far cheaper than the wrong abstraction" — Sandi Metz'''
    ),
    (
        "thinking/meta-mistakes-premature-opt-denormalize",
        r'''I denormalized our database for performance before we had any traffic:

```sql
-- Instead of joining users + orders + products, I put everything in one table:
CREATE TABLE order_details_denormalized (
    order_id INT,
    user_name VARCHAR,
    user_email VARCHAR,
    product_name VARCHAR,
    product_price DECIMAL,
    quantity INT,
    order_date TIMESTAMP,
    -- ... 20 more columns from 4 tables
);
```

Now updating a user's email requires updating thousands of rows, and our data has inconsistencies. Was this premature?''',
        r'''<think>
I made an error: I denormalized the database before proving that joins were actually a performance bottleneck. Now I have data integrity issues that are MUCH harder to fix than slow queries.

The mistake was: optimizing for read performance at the cost of write correctness, without evidence that read performance was a problem.

The root cause was: premature optimization driven by fear of joins. "Joins are slow" is a persistent myth for small-to-medium datasets. PostgreSQL can join millions of rows efficiently with proper indexes. Denormalization should be a last resort after proving joins are the bottleneck.

Generalizable lesson: Start normalized. Only denormalize specific queries that are measured bottlenecks, and even then prefer materialized views or caching over physical denormalization. Data integrity is harder to fix than slow queries.

Checklist item: Before denormalizing, ask: "Have I measured that this join is actually slow? What's the actual query time? Can an index fix it?"

Similar situations where this lesson applies:
1. Pre-computing aggregates before knowing if they're needed
2. Using NoSQL "for performance" before trying relational + indexes
3. Embedding related data in documents (MongoDB) prematurely
</think>

**Yes — textbook premature optimization.** You traded data integrity for theoretical read speed, before proving reads were slow.

**The problems you now have:**
1. **Data inconsistency**: User changes email → thousands of rows have stale data
2. **Write amplification**: Every user/product update must update all related rows
3. **Storage bloat**: Duplicating user/product data across every order row

**What you should have done:**
```sql
-- Normalized (correct starting point):
CREATE TABLE users (id SERIAL, name VARCHAR, email VARCHAR);
CREATE TABLE products (id SERIAL, name VARCHAR, price DECIMAL);
CREATE TABLE orders (id SERIAL, user_id INT REFERENCES users, product_id INT REFERENCES products, quantity INT, order_date TIMESTAMP);

-- If the JOIN is slow, add indexes first:
CREATE INDEX idx_orders_user ON orders(user_id);
CREATE INDEX idx_orders_date ON orders(order_date);

-- If STILL slow after indexes, use a materialized view (not physical denormalization):
CREATE MATERIALIZED VIEW order_details AS
SELECT o.id, u.name, u.email, p.name AS product, p.price, o.quantity, o.order_date
FROM orders o JOIN users u ON o.user_id = u.id JOIN products p ON o.product_id = p.id;

REFRESH MATERIALIZED VIEW order_details;  -- Refresh on schedule
```

**The optimization ladder:**
1. Proper indexes (solves 90% of slow queries)
2. Query optimization (EXPLAIN ANALYZE)
3. Caching layer (Redis for hot data)
4. Materialized views (pre-computed joins, refreshable)
5. Physical denormalization (LAST RESORT, only for extreme scale)

**The lesson: profile before optimizing.** Most "slow join" fears are unfounded. PostgreSQL joins millions of rows in milliseconds with proper indexes. Denormalization creates real problems to solve imaginary ones.'''
    ),
    (
        "thinking/meta-mistakes-premature-opt-microservices",
        r'''We're a 3-person startup and we split our app into 8 microservices before launch. Now we spend most of our time debugging network issues, managing deployments, and dealing with distributed transactions. Was this a mistake?''',
        r'''<think>
I made an error: splitting into microservices before the application had traffic, clear domain boundaries, or a team large enough to support them.

The mistake was: choosing an architecture (microservices) based on what large companies do at scale, without considering that the costs of distributed systems outweigh the benefits at small scale.

The root cause was: resume-driven development and cargo culting. "Netflix uses microservices, so we should too." But Netflix has thousands of engineers — the organizational complexity justifies architectural complexity. A 3-person team managing 8 services means each person is responsible for ~3 services, with all the operational overhead that entails.

Generalizable lesson: Architecture should match team size and actual scale, not anticipated scale. Start with a well-structured monolith, and extract services only when you have concrete reasons (team scaling, independent deployment needs, different scaling profiles). Premature microservices are the distributed systems equivalent of premature optimization.

Checklist item: Before splitting into services, ask: "Do we have enough people to own each service? Do we have the infra team to manage service mesh, monitoring, and deployments?"

Similar situations where this lesson applies:
1. Adding Kubernetes for a single-server workload
2. Implementing event sourcing before understanding the domain
3. Using a message queue between two components that could share a database
</think>

**Yes — this is premature architecture optimization.** You're paying the microservices tax without the microservices benefits.

**Costs you're paying (with 3 people):**
- Network debugging between 8 services
- 8 separate deployments to coordinate
- Distributed tracing to follow a single request
- Distributed transactions (2PC, sagas) instead of simple DB transactions
- 8 repos/CI pipelines/monitoring dashboards to maintain
- Service discovery, health checks, retry logic for every call

**Benefits you're NOT getting (yet):**
- ❌ Independent team scaling (you have 3 people)
- ❌ Independent deployment cadence (you deploy everything together anyway)
- ❌ Different tech stacks per service (you use the same stack everywhere)
- ❌ Independent scaling of hot services (you don't have enough traffic)

**The fix — merge back into a modular monolith:**
```
# Instead of 8 services, one app with clear module boundaries:
myapp/
├── users/          # Was user-service
│   ├── models.py
│   ├── routes.py
│   └── service.py
├── orders/         # Was order-service
├── payments/       # Was payment-service
├── inventory/      # Was inventory-service
└── shared/
    └── database.py # One database, simple transactions
```

Function calls replace HTTP calls. Database transactions replace distributed sagas. One deployment instead of eight.

**When to extract a service later:**
- A module needs to scale independently (10x more traffic than others)
- A separate team will own it (> 8 engineers)
- It has genuinely different runtime requirements (GPU, different language)

**The lesson: start with a monolith, extract services when forced to.** A well-structured monolith is faster to develop, debug, and deploy than microservices — until you outgrow it.'''
    ),
    (
        "thinking/meta-mistakes-premature-opt-algorithm",
        r'''I spent a week implementing a custom B-tree for our in-memory lookup table instead of using a dictionary. My colleague says it was premature. The B-tree is 10x more code and slightly slower than a dict for our data size (~10K items). But B-trees have better cache locality, right?''',
        r'''<think>
I made an error: I optimized for cache locality in an in-memory data structure when a simple dictionary would have been faster AND simpler for the actual data size.

The mistake was: applying theoretical algorithmic knowledge without measuring. Yes, B-trees have better cache locality than hash tables for large datasets on disk. But for 10K items entirely in memory, Python dict (hash table) is extremely fast and is implemented in C — beating any Python-level B-tree implementation.

The root cause was: theoretical knowledge without practical measurement. B-tree cache locality matters when data spans multiple cache lines/pages (millions of items or disk-backed storage). At 10K items, the entire dataset fits in L2 cache. Also, a pure Python B-tree has huge constant-factor overhead compared to CPython's C-implemented dict.

Generalizable lesson: Theoretical algorithmic advantages don't always translate to real-world wins. Constant factors, implementation language, actual data size, and hardware reality all matter. Always benchmark with your actual data before choosing a complex data structure.

Checklist item: Before implementing a custom data structure, ask: "What's my N? Is the built-in data structure actually too slow? Have I benchmarked?"

Similar situations where this lesson applies:
1. Implementing a custom allocator instead of using malloc
2. Using a skip list instead of a sorted array for small collections
3. Writing custom SIMD code when NumPy already does it in C
</think>

**Your colleague is right.** Here's why:

**Theory vs reality:**
- B-tree cache locality advantage: relevant for millions of items spanning many cache lines
- Your data: 10K items, fits entirely in L2 cache (~256KB-1MB)
- Python dict: implemented in C, heavily optimized by CPython core developers
- Your B-tree: implemented in Python, 100x interpreter overhead per operation

**Actual performance comparison:**
```python
# Dict: O(1) average, implemented in C
d = {i: f"value_{i}" for i in range(10_000)}
d[5000]  # ~50 nanoseconds

# Custom Python B-tree: O(log n) with Python overhead
tree = BTree()
for i in range(10_000): tree.insert(i, f"value_{i}")
tree.search(5000)  # ~5,000 nanoseconds (Python loop overhead)
```

Your B-tree is ~100x slower with 10x more code.

**When custom data structures ARE justified:**
- Millions of items where built-ins are measured to be too slow
- Specialized operations (range queries, nearest-neighbor) that dicts don't support
- Performance-critical inner loops after profiling proves the bottleneck
- Using C extensions (not pure Python) for the implementation

**The lesson: profile before implementing custom data structures.** Built-in data structures in Python are implemented in C and are fast enough for most use cases. The crossover point where algorithmic complexity beats constant-factor overhead is usually much higher than you think.

**Week spent on B-tree → 0 real benefit. That week could have shipped a feature users care about.**'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
