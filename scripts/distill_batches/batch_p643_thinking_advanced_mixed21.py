"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 21)"""

PAIRS = [
    (
        "thinking/analogy-dependency-injection-power-outlets",
        "What is dependency injection and why should I use it? It sounds overly complicated for what it does.",
        r'''<think>
Dependency injection — often overcomplicated in explanations. Let me use a simple analogy.

**The power outlet analogy:**
A lamp doesn't have a built-in power plant. It has a plug. You plug it into whatever power source is available — wall outlet, generator, battery pack. The lamp doesn't care WHERE the power comes from, just that it gets power.

This is dependency injection:
- The lamp = your class/function
- Power = the dependency (database, API client, etc.)
- Plug = the interface/parameter
- Wall outlet = production dependency
- Battery pack = test dependency

Without DI: the lamp has a built-in power plant (hardcoded dependency)
- Can't test the lamp without a power plant
- Can't use the lamp with different power sources
- If the power plant breaks, you throw away the lamp

With DI: the lamp takes power through a plug (injected dependency)
- Test with a battery (mock)
- Use any power source (swap implementations)
- Lamp works anywhere

The key insight: DI isn't a framework or pattern — it's just "pass dependencies as parameters instead of creating them inside the function."
</think>

Dependency injection is simpler than it sounds. It's just **passing dependencies as parameters instead of creating them inside your code**.

## The Analogy: Lamps and Power Outlets

```
WITHOUT DEPENDENCY INJECTION:
  A lamp with a built-in power plant.
  → Can only work with that specific power plant
  → Can't test the lamp without running the power plant
  → If the power plant changes, you rebuild the lamp
  → Every lamp has its own power plant (wasteful)

WITH DEPENDENCY INJECTION:
  A lamp with a plug.
  → Plug into wall outlet (production)
  → Plug into battery pack (testing)
  → Plug into generator (different environment)
  → The lamp doesn't care where power comes from
```

## In Code

```python
# ❌ WITHOUT DI: hardcoded dependency (built-in power plant)
class OrderService:
    def __init__(self):
        self.db = PostgresDatabase("localhost:5432/prod")  # Hardcoded!
        self.email = SmtpEmailSender("smtp.gmail.com")     # Hardcoded!

    def create_order(self, data):
        order = self.db.insert("orders", data)   # Always hits real database
        self.email.send(data["email"], "Order confirmed")  # Always sends real email
        return order

# Problems:
# 1. Tests hit the REAL database and send REAL emails
# 2. Can't use a different database or email provider
# 3. Can't run without network access

# ✅ WITH DI: dependencies passed in (lamp with a plug)
class OrderService:
    def __init__(self, db, email_sender):  # Dependencies are PARAMETERS
        self.db = db
        self.email = email_sender

    def create_order(self, data):
        order = self.db.insert("orders", data)
        self.email.send(data["email"], "Order confirmed")
        return order

# PRODUCTION: plug in real services
order_service = OrderService(
    db=PostgresDatabase("localhost:5432/prod"),
    email_sender=SmtpEmailSender("smtp.gmail.com"),
)

# TESTING: plug in fakes (no database, no emails)
def test_create_order():
    fake_db = FakeDatabase()           # In-memory, fast
    fake_email = FakeEmailSender()     # Records emails, doesn't send
    service = OrderService(fake_db, fake_email)

    service.create_order({"email": "test@test.com", "item": "widget"})

    assert fake_db.last_insert["item"] == "widget"
    assert fake_email.last_sent_to == "test@test.com"
    # No real database hit. No real email sent. Test runs in 1ms.
```

## That's It. That's Dependency Injection.

```
DI is NOT:
  ✗ A framework (Spring, Guice, etc.)
  ✗ A complex design pattern
  ✗ An enterprise-only concept
  ✗ Something that requires annotations or decorators

DI IS:
  ✓ Passing dependencies as parameters
  ✓ Instead of creating them inside your code
  ✓ So you can swap them out (for testing, different environments, etc.)

  # DI in one line:
  def get_users(db):          # ← this is dependency injection
      return db.query("SELECT * FROM users")

  # NOT DI:
  def get_users():
      db = Database("localhost")  # ← hardcoded dependency
      return db.query("SELECT * FROM users")
```

## When It Matters Most

```
1. TESTING (biggest benefit)
   Without DI: tests need real database, real APIs, real email servers
   With DI: tests use fakes/mocks, run in milliseconds

2. SWAPPING IMPLEMENTATIONS
   Without DI: changing from S3 to GCS means rewriting every file that uses S3
   With DI: change one line where you create the storage dependency

3. CONFIGURATION PER ENVIRONMENT
   dev:  OrderService(db=LocalDB(),    email=ConsoleEmailPrinter())
   test: OrderService(db=InMemoryDB(), email=FakeEmail())
   prod: OrderService(db=PostgresDB(), email=SendGridEmail())
```'''
    ),
    (
        "thinking/causal-high-cpu-usage-event-loop-blocking",
        "Our Node.js server CPU usage spikes to 100% and the entire application freezes for several seconds. It doesn't crash, just becomes unresponsive and then recovers. This happens randomly several times a day.",
        r'''<think>
Node.js 100% CPU spikes that freeze the entire app then recover. This is almost certainly event loop blocking.

**Causal analysis:**
Node.js is single-threaded. One CPU-intensive operation blocks the ENTIRE event loop. All other requests wait. When the operation finishes, everything resumes.

**What causes event loop blocking?**
1. **Synchronous file operations** — fs.readFileSync on large files
2. **JSON.parse/stringify on large objects** — serializing a 10MB object
3. **Complex regex on long strings** — catastrophic backtracking (ReDoS)
4. **Synchronous crypto operations** — crypto.pbkdf2Sync, bcryptSync
5. **Large array operations** — sorting/filtering millions of elements
6. **Tight loops** — for loop over large dataset without yielding

**"Randomly several times a day" suggests:**
It's triggered by specific data, not time-based. Some requests have larger payloads or trigger expensive operations:
- A user with 50,000 records vs typical 500
- An API response that's 10MB instead of 10KB
- An input string that triggers regex backtracking

**Diagnosis approach:**
Use `--prof` or `clinic.js` to profile during spikes. Or add event loop monitoring to detect which operation is blocking.
</think>

Node.js is **single-threaded**. One CPU-intensive operation blocks the entire event loop — every request waits until it finishes.

## Root Cause

```
Normal:
  Event loop: req1 → req2 → req3 → req4 → req5  (1ms each)
  All responses: fast ✓

During spike:
  Event loop: req1 → [BLOCKED 5 seconds] → req2 → req3 → req4...
  ONE operation is hogging the CPU for 5 seconds
  All other requests queued behind it → entire app unresponsive
  Operation finishes → queue drains → app "recovers"
```

## Most Likely Causes

```javascript
// 1. JSON.parse/stringify on large objects
// ❌ BLOCKS: serializing a 10MB API response
app.get('/export', async (req, res) => {
    const data = await db.getAllRecords();  // 50,000 records
    res.json(data);  // JSON.stringify(data) → blocks event loop for 3 seconds
});

// ✅ FIX: stream the response
app.get('/export', async (req, res) => {
    res.setHeader('Content-Type', 'application/json');
    res.write('[');
    const cursor = db.getAllRecordsCursor();
    let first = true;
    for await (const record of cursor) {
        if (!first) res.write(',');
        res.write(JSON.stringify(record));
        first = false;
    }
    res.write(']');
    res.end();
});

// 2. Synchronous file operations
// ❌ BLOCKS: reading a large file synchronously
const data = fs.readFileSync('/path/to/large-file.csv', 'utf-8');

// ✅ FIX: use async version
const data = await fs.promises.readFile('/path/to/large-file.csv', 'utf-8');

// 3. Regex catastrophic backtracking (ReDoS)
// ❌ BLOCKS: bad regex on certain inputs
const emailRegex = /^([a-zA-Z0-9]+\.)*[a-zA-Z0-9]+@([a-zA-Z0-9]+\.)+[a-zA-Z]{2,}$/;
emailRegex.test("aaaaaaaaaaaaaaaaaaaaaaaaaaa@");
// With nested quantifiers (.)* on specific inputs → exponential backtracking → CPU spike

// ✅ FIX: use simple regex or validator library
const validator = require('validator');
validator.isEmail(input);  // Well-tested, no backtracking issues

// 4. Synchronous crypto
// ❌ BLOCKS: synchronous password hashing
const hash = bcrypt.hashSync(password, 12);  // Blocks for ~300ms

// ✅ FIX: use async version
const hash = await bcrypt.hash(password, 12);  // Non-blocking

// 5. Large array operations
// ❌ BLOCKS: sorting 1 million items
const sorted = hugeArray.sort((a, b) => a.score - b.score);  // Blocks for seconds

// ✅ FIX: move to worker thread
const { Worker } = require('worker_threads');
```

## Diagnosis: Find the Blocker

```javascript
// Add event loop monitoring to find WHEN the loop blocks
const monitor = require('blocked-at');

monitor((time, stack) => {
    console.error(`Event loop blocked for ${time}ms:`);
    console.error(stack);  // Shows WHICH code is blocking
}, { threshold: 100 });  // Alert when blocked > 100ms

// OUTPUT:
// Event loop blocked for 3200ms:
//   at JSON.stringify (internal)
//   at /app/routes/export.js:42:12
//   at ...
// → Now you know: JSON.stringify in export.js line 42 is the culprit
```

```bash
# Profile with clinic.js (best Node.js profiling tool)
npx clinic doctor -- node server.js
# Generate load during spike window
# Clinic produces a flamegraph showing where CPU time is spent
```

## Prevention: Worker Threads for CPU Work

```javascript
// For ANY operation that might take >100ms, use a worker thread
const { Worker, isMainThread, parentPort } = require('worker_threads');

if (isMainThread) {
    // Main thread: handle HTTP requests, delegate CPU work
    app.get('/process', async (req, res) => {
        const result = await runInWorker('./heavy-task.js', req.body);
        res.json(result);
    });

    function runInWorker(file, data) {
        return new Promise((resolve, reject) => {
            const worker = new Worker(file, { workerData: data });
            worker.on('message', resolve);
            worker.on('error', reject);
        });
    }
} else {
    // Worker thread: CPU-intensive work runs here
    // This does NOT block the main event loop
    const { workerData } = require('worker_threads');
    const result = heavyComputation(workerData);
    parentPort.postMessage(result);
}
```

**Key insight:** Node.js freezes because it has ONE thread for everything. Any CPU-intensive work (>50ms) should be moved to a worker thread or a background process.'''
    ),
    (
        "thinking/backtrack-big-bang-rewrite-to-strangler",
        "We want to rewrite our legacy PHP monolith in Python. The plan is to spend 6 months building the new system, then switch over. Is this a good plan?",
        r'''<think>
Big bang rewrite of a legacy system — this is one of the most well-documented failure modes in software engineering.

**Why big bang rewrites fail:**
1. The existing system keeps getting new features during the 6 months
2. You underestimate the complexity (6 months → 12 months → 18 months)
3. No business value delivered until the switch (management loses patience)
4. The new system has NEW bugs while lacking years of edge-case fixes from the old system
5. The switchover is terrifying (all or nothing)
6. You lose institutional knowledge embedded in the old code ("why is this weird condition here?" → turns out it handles a critical edge case)

Joel Spolsky famously called this "the single worst strategic mistake that any software company can make."

**Backtrack to: Strangler Fig pattern**
Instead of building a new system alongside the old one, gradually replace pieces of the old system. Like a strangler fig tree that grows around a host tree, eventually replacing it entirely.

**The approach:**
1. Put a proxy/API gateway in front of the old system
2. New features go to the new system
3. Migrate existing features one at a time
4. Each migration delivers value immediately
5. Eventually the old system has no remaining functionality → remove it
</think>

**This plan will almost certainly fail.** Big bang rewrites are one of the most well-documented failure modes in software engineering.

## Why Big Bang Rewrites Fail

```
THE PLAN:
  Month 0:  Start building New System alongside Old System
  Month 6:  Switch everyone to New System, turn off Old System
  → Clean, modern codebase! Everyone's happy!

WHAT ACTUALLY HAPPENS:
  Month 0:  Start building New System
  Month 2:  "The old system needs a critical bug fix" → fix in old, not in new
  Month 4:  "Can't we add this feature to the old system while we wait?"
  Month 6:  New System is 60% done (you underestimated by 2x)
  Month 8:  Management: "We've spent 8 months with no business value"
  Month 10: Team is demoralized. New system still missing edge cases.
  Month 12: New System "ready". Switch over.
  Month 12.5: Customers: "WHERE IS FEATURE X?" "WHY IS Y BROKEN?"
            The old system had 5 years of edge-case fixes that nobody
            documented and nobody remembered to reimplement.
  Month 13: Roll back to old system. New system abandoned.
            12 months wasted.
```

## Backtrack: The Strangler Fig Pattern

```
Instead of REPLACING the old system, GROW AROUND IT.

THE STRANGLER FIG APPROACH:
  1. Put a proxy in front of the old system
  2. Route new features to new Python services
  3. Migrate existing features ONE BY ONE to Python
  4. Each migration is independently valuable and deployable
  5. Eventually, old PHP system handles nothing → remove it

  Week 1:  [Proxy] → 100% PHP
  Month 1: [Proxy] → 95% PHP, 5% Python (new user auth)
  Month 3: [Proxy] → 80% PHP, 20% Python (+ payment processing)
  Month 6: [Proxy] → 50% PHP, 50% Python (+ product catalog)
  Month 12: [Proxy] → 10% PHP, 90% Python (+ order management)
  Month 15: [Proxy] → 0% PHP, 100% Python → remove old system
```

## How to Implement the Strangler

```
STEP 1: Add a reverse proxy (Nginx, Kong, or API Gateway)

  All traffic → Nginx → PHP app  (no change to users)

STEP 2: Build new feature in Python
  /api/v2/recommendations → Python service  (NEW, never existed in PHP)
  Everything else → PHP app

STEP 3: Migrate one existing feature
  /api/users/auth → Python service  (was PHP, now Python)
  Everything else → PHP app

  CRITICAL: keep the URL structure the same
  Users and frontends don't know anything changed
```

```nginx
# Nginx routing — gradual migration
upstream php_app {
    server php-app:8080;
}

upstream python_app {
    server python-app:8000;
}

# Migrated routes → Python
location /api/auth/     { proxy_pass http://python_app; }
location /api/users/    { proxy_pass http://python_app; }
location /api/payments/ { proxy_pass http://python_app; }

# Everything else → still PHP
location / { proxy_pass http://php_app; }

# Each migration: add one more location block
# Rollback: remove the location block → traffic goes back to PHP
```

## Why This Works Better

```
BIG BANG REWRITE:
  ✗ No value for 6-12 months
  ✗ All risk concentrated in one switchover moment
  ✗ Must reimplement EVERYTHING before launching anything
  ✗ Old system gets features that new system doesn't have
  ✗ Team demoralized by invisible progress

STRANGLER FIG:
  ✓ Value delivered every sprint (each migrated feature works immediately)
  ✓ Risk distributed (each migration is small and reversible)
  ✓ Can stop at any point (partial migration is still useful)
  ✓ Old and new coexist (no "big switch" moment)
  ✓ Team sees progress weekly (visible, measurable migration)
  ✓ Can prioritize: migrate the most painful parts first

MIGRATION ORDER (by pain/value):
  1. Parts that change most often (fastest developer productivity gain)
  2. Parts with the worst bugs (highest user impact)
  3. Parts that need new features (build new + migrate)
  4. Stable parts that rarely change (lowest priority — leave for last)
```

The strangler fig approach has been successfully used by Amazon, Netflix, Shopify, and countless others. The big bang rewrite has a graveyard of failed attempts.'''
    ),
    (
        "thinking/multiperspective-code-review-practices",
        "Our team is debating code review practices. Some think every PR needs at least 2 approvals, others think senior devs should be able to merge without review. What's the right approach?",
        r'''<think>
Code review practices debate. Let me analyze multiple perspectives.

**Perspective 1: Strict reviews (2+ approvals)**
Pros:
- Catches more bugs (multiple eyes)
- Knowledge sharing (everyone sees all code)
- Prevents single person from shipping broken code
- Consistent quality standards
Cons:
- Slow (waiting for 2 reviewers)
- Bottleneck (especially with timezone differences)
- Review fatigue (reviewers rubber-stamp)
- Senior devs frustrated by waiting for juniors to review their code

**Perspective 2: Senior devs merge without review**
Pros:
- Fast (no waiting)
- Respects experience and judgment
- Unblocked by reviewer availability
Cons:
- Senior devs make mistakes too
- No knowledge sharing
- Creates a two-tier system (demoralizing for juniors)
- Bus factor (only one person knows the code)

**Perspective 3: Risk-based review**
- Critical code (auth, payments, data migrations): 2+ reviewers
- Normal features: 1 reviewer
- Trivial changes (typos, config): self-merge with notification
- This is the pragmatic middle ground

**My synthesis:**
The right approach depends on team size, domain risk, and culture. But risk-based review is the best default.
</think>

Both extremes have problems. The pragmatic approach is **risk-based review** — scale review rigor to the risk of the change.

## Each Perspective's Strongest Point

```
STRICT (2+ APPROVALS):
  Strongest argument: "Last month a senior dev shipped a SQL injection
  vulnerability. A second reviewer would have caught it."
  → Even experts make mistakes. Reviews aren't about skill level.

  Weakness: review fatigue. After the 5th PR waiting 24 hours for
  a second approval, reviewers start rubber-stamping.

SELF-MERGE FOR SENIORS:
  Strongest argument: "I waited 3 days for a review on a 2-line config
  change. My feature was blocked the entire time."
  → Slow reviews kill velocity and frustrate experienced developers.

  Weakness: "I'm senior enough to not need review" is how security
  vulnerabilities and subtle bugs ship to production.
```

## The Pragmatic Middle Ground: Risk-Based Review

```
TIER 1: CRITICAL CHANGES → 2 reviewers required
  - Authentication / authorization code
  - Payment processing
  - Database migrations on production data
  - Security-sensitive code (crypto, input validation)
  - Infrastructure / CI/CD pipeline changes
  - Public API contract changes

TIER 2: NORMAL CHANGES → 1 reviewer required
  - New features
  - Bug fixes
  - Refactoring
  - Most code changes

TIER 3: LOW-RISK CHANGES → self-merge + notify team
  - Typo fixes in comments/docs
  - Dependency version bumps (with passing CI)
  - Config changes in non-production environments
  - Adding/updating tests only

HOW TO IMPLEMENT:
  - CODEOWNERS file designates who MUST review specific paths
  - CI enforces minimum approvals by path
  - Self-merges auto-post to team channel for visibility
```

```yaml
# .github/CODEOWNERS — enforce reviewers by path
# Critical paths: require specific reviewers
/src/auth/**           @security-team
/src/payments/**       @payments-team @security-team
/migrations/**         @database-team
/.github/workflows/**  @platform-team

# Everything else: any team member can review
*                      @dev-team
```

## What Good Reviews Actually Look Like

```
CODE REVIEWS ARE NOT:
  ✗ A gate to assert authority
  ✗ Nitpicking style preferences
  ✗ Rewriting someone's code your way
  ✗ A checkbox to satisfy process

CODE REVIEWS ARE:
  ✓ "Does this do what the ticket says?"
  ✓ "Could this break in production?"
  ✓ "Is there a security concern?"
  ✓ "Will future-me understand this code?"
  ✓ "Are there missing tests for important behavior?"

REVIEW TIME TARGETS:
  - Acknowledge PR within 2 hours (during work hours)
  - Complete review within 4 hours for small PRs
  - Complete review within 1 business day for large PRs
  - If you can't review in time, say so → author finds another reviewer
```

## Practical Recommendations

```
FOR YOUR TEAM:
  1. Default to 1 required reviewer
  2. Use CODEOWNERS for 2-reviewer paths (auth, payments, infra)
  3. Allow self-merge for trivial changes with passing CI
  4. Set review time SLAs (respond within 4 hours)
  5. Small PRs (< 400 lines) — faster reviews, fewer conflicts

ANTI-PATTERNS TO AVOID:
  ✗ "I'll review it later" (becomes never)
  ✗ Reviews > 24 hours old (context lost, conflicts accumulate)
  ✗ Approving without reading (rubber-stamping)
  ✗ Blocking on style preferences (use automated formatters instead)
  ✗ Only senior devs can approve (juniors learn by reviewing too)
```

The goal isn't to prevent all bugs (that's what tests and monitoring are for). The goal is knowledge sharing, catching design issues, and maintaining consistency. Scale the review depth to match the risk.'''
    ),
    (
        "thinking/uncertainty-sql-vs-nosql-ecommerce",
        "We're building an e-commerce platform. Should we use PostgreSQL or MongoDB? Our CTO says MongoDB is more modern and scalable.",
        r'''<think>
SQL vs NoSQL for e-commerce. This is one of the clearest cases for SQL.

**E-commerce data characteristics:**
- Orders reference products, users, addresses, payment methods
- Inventory counts must be exact (no overselling)
- Financial calculations must be precise
- Complex queries: "orders by user in last 30 days with product details and shipping status"
- Transactions: "decrement inventory AND create order AND charge payment" must all succeed or all fail

**PostgreSQL for e-commerce:**
- ACID transactions (critical for financial operations)
- JOINs (order → user → products → addresses = natural relational query)
- Constraints (foreign keys prevent orphaned data)
- Exact numeric types (DECIMAL for money, not floating point)
- Proven at massive scale for e-commerce (Shopify uses MySQL, Amazon uses custom RDBMS)

**MongoDB for e-commerce:**
- Flexible schema (could embed products in orders... but then product updates don't propagate)
- Horizontal scaling (sharding)
- Fast reads for denormalized data
- BUT: no real transactions until recently (and they're slow)
- JOINs are expensive ($lookup is slow and limited)
- Eventual consistency risks for inventory

**Confidence: 90% PostgreSQL**

MongoDB might work if: catalog is the primary use case (read-heavy, flexible product attributes), or if they need extreme horizontal scaling. But for the transactional core of e-commerce (orders, payments, inventory), SQL wins decisively.
</think>

**90% confidence: PostgreSQL.** E-commerce is one of the strongest use cases for relational databases.

## Why E-Commerce Needs SQL

```
E-COMMERCE DATA IS INHERENTLY RELATIONAL:

  User → has many → Orders
  Order → has many → OrderItems
  OrderItem → references → Product
  Order → references → ShippingAddress
  Order → references → PaymentMethod
  Product → has many → Reviews
  Product → belongs to → Category

  These relationships ARE the data model.
  SQL was DESIGNED for exactly this.
```

## The Critical Requirement: Transactions

```python
# E-commerce requires ATOMIC operations:

# "Customer buys last item in stock"
# These MUST happen together or NOT AT ALL:
#   1. Check inventory > 0
#   2. Decrement inventory
#   3. Create order
#   4. Charge payment

# ❌ MongoDB (before v4.0: no transactions)
# What could happen without transactions:
#   1. Check inventory: 1 remaining ✓
#   2. Decrement inventory: 0 remaining ✓
#   3. Create order → SUCCESS
#   4. Charge payment → FAILS (card declined)
#   Now: inventory is 0, order exists, no payment. Data is inconsistent.
#   Another customer saw inventory=1 between steps 1 and 2 → oversold.

# ✅ PostgreSQL: ACID transactions
with db.transaction():
    product = db.query("SELECT stock FROM products WHERE id = %s FOR UPDATE", product_id)
    if product.stock < quantity:
        raise OutOfStockError()
    db.execute("UPDATE products SET stock = stock - %s WHERE id = %s", quantity, product_id)
    order = db.execute("INSERT INTO orders (...) VALUES (...) RETURNING id")
    charge_payment(order.id)  # If this fails, EVERYTHING rolls back
# All or nothing. Data always consistent.
```

## The Query Problem

```sql
-- Common e-commerce query: "order history with details"
-- PostgreSQL: one query, clean and fast
SELECT o.id, o.created_at, o.total,
       u.name, u.email,
       oi.quantity, oi.price,
       p.name as product_name, p.image_url,
       a.city, a.country
FROM orders o
JOIN users u ON u.id = o.user_id
JOIN order_items oi ON oi.order_id = o.id
JOIN products p ON p.id = oi.product_id
JOIN addresses a ON a.id = o.shipping_address_id
WHERE o.user_id = 42
ORDER BY o.created_at DESC;

-- MongoDB equivalent: multiple queries or $lookup pipeline
-- $lookup (MongoDB's JOIN) is slow and limited to 2 collections
-- For 5 related collections, you need 4 $lookups or multiple queries
-- OR you denormalize (embed product data in orders)
-- BUT then product name changes don't update old orders
-- (which might actually be what you want for historical records,
--  but then inventory, pricing, and current product data need
--  a separate source of truth)
```

## When MongoDB WOULD Be Better

```
MongoDB makes sense for parts of e-commerce, not the core:

PRODUCT CATALOG (maybe):
  Products have wildly different attributes:
  - Shoes: size, color, material, width
  - Electronics: RAM, storage, screen_size, battery
  - Books: author, ISBN, pages, format

  MongoDB's flexible schema handles this well.
  BUT: PostgreSQL's JSONB column does too:
    CREATE TABLE products (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        price DECIMAL(10,2) NOT NULL,
        attributes JSONB  -- flexible per-product attributes
    );

SEARCH / RECOMMENDATIONS:
  Full-text search → Elasticsearch (not Postgres OR Mongo)
  Recommendations → Redis or dedicated ML service

SESSION / CART DATA:
  Temporary, per-user, doesn't need ACID → Redis

ANALYTICS / EVENT LOGS:
  Write-heavy, rarely queried → ClickHouse, BigQuery, or MongoDB
```

## The Bottom Line

```
CORE E-COMMERCE (orders, payments, inventory, users):
  → PostgreSQL. ACID transactions are non-negotiable.
  → Shopify (MySQL), Amazon (custom RDBMS), most e-commerce: SQL

SUPPORTING SERVICES:
  → Search: Elasticsearch
  → Caching/sessions: Redis
  → Analytics: ClickHouse or BigQuery
  → Product attributes: PostgreSQL JSONB (or MongoDB if you want)

"MongoDB is more modern and scalable":
  - "Modern" ≠ better for your use case
  - PostgreSQL scales to massive sizes (Shopify handles millions of stores)
  - Horizontal scaling is a problem you don't have yet
  - When you do, shard PostgreSQL or use Citus
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
