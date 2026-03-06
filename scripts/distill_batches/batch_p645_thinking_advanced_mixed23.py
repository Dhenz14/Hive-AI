"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 23)"""

PAIRS = [
    (
        "thinking/adversarial-open-redirect",
        "I have a login page that redirects users back to where they came from using a 'next' URL parameter: /login?next=/dashboard. Is this safe?",
        r'''<think>
Open redirect vulnerability. The `next` parameter can be exploited if not validated.

**The attack:**
1. Attacker crafts: `https://your-app.com/login?next=https://evil.com/fake-login`
2. User sees your-app.com in the URL bar → trusts it
3. User logs in successfully on your real site
4. Your app redirects to https://evil.com/fake-login
5. evil.com shows a fake "session expired, please log in again" page
6. User enters credentials AGAIN → attacker captures them
7. evil.com redirects back to your real app → user never suspects anything

**Why it's dangerous:**
- The URL starts with YOUR domain (looks legitimate)
- Phishing emails: "Click here to verify your account" → link goes to your real domain
- After the redirect, user is on attacker's site but trusts the flow

**Additional attack vectors:**
- `//evil.com` — protocol-relative URL
- `/\evil.com` — backslash confusion
- `https://evil.com@your-app.com` — URL authority confusion
- `javascript:alert(1)` — XSS via redirect
- `%2F%2Fevil.com` — URL-encoded bypass

**Fix: validate that the redirect URL is a relative path on your domain.**
</think>

**No, this is an open redirect vulnerability.** An attacker can redirect users to a phishing site after they log in on your real site.

## The Attack

```
NORMAL USE:
  /login?next=/dashboard
  → User logs in → redirected to /dashboard ✓

ATTACK:
  /login?next=https://evil.com/fake-login
  → User sees your-app.com in the URL → trusts it
  → User logs in on YOUR real site (credentials are safe so far)
  → Your app redirects to evil.com/fake-login
  → evil.com shows: "Session expired. Please log in again."
  → User enters password AGAIN → attacker captures it
  → evil.com redirects back to your real app
  → User never realizes they were phished

PHISHING EMAIL:
  "Your account has suspicious activity. Click here to verify:"
  https://your-app.com/login?next=https://evil.com/steal-creds
  ↑ This URL is 100% on YOUR domain. Email filters won't flag it.
```

## Bypass Attempts Attackers Will Try

```python
# Attacker tries various formats to bypass naive validation:

next = "https://evil.com"           # Absolute URL
next = "//evil.com"                 # Protocol-relative
next = "/\\evil.com"                # Backslash confusion
next = "https://evil.com@your.com"  # URL authority confusion
next = "javascript:alert(1)"       # XSS via redirect
next = "%2F%2Fevil.com"            # URL-encoded //
next = "https://your-app.com.evil.com"  # Subdomain trick
next = "\x00https://evil.com"       # Null byte injection
```

## The Fix

```python
from urllib.parse import urlparse

def is_safe_redirect(url):
    """Only allow relative URLs on our own domain."""
    if not url:
        return False

    parsed = urlparse(url)

    # Must not have a scheme (no http://, https://, javascript:)
    if parsed.scheme:
        return False

    # Must not have a netloc (no //evil.com)
    if parsed.netloc:
        return False

    # Must start with / (relative path)
    if not url.startswith('/'):
        return False

    # Must not start with // (protocol-relative)
    if url.startswith('//'):
        return False

    # Must not contain backslash (confusion attack)
    if '\\' in url:
        return False

    return True

# Usage in login handler:
@app.post("/login")
async def login(request):
    # ... verify credentials ...

    next_url = request.query_params.get("next", "/dashboard")

    if not is_safe_redirect(next_url):
        next_url = "/dashboard"  # Default to safe URL

    return RedirectResponse(next_url)
```

```python
# Django has this built in:
from django.utils.http import url_has_allowed_host_and_scheme

next_url = request.GET.get('next', '/')
if not url_has_allowed_host_and_scheme(
    next_url,
    allowed_hosts={request.get_host()},
    require_https=request.is_secure(),
):
    next_url = '/'
```

## Alternative: Allowlist Approach

```python
# Even safer: only allow specific known paths
ALLOWED_REDIRECTS = {
    '/dashboard',
    '/profile',
    '/settings',
    '/orders',
}

def get_safe_redirect(next_param):
    if next_param in ALLOWED_REDIRECTS:
        return next_param
    return '/dashboard'
```

**Rule: never redirect to a URL from user input without validating it's a relative path on your own domain.** This applies to any redirect parameter, not just login flows.'''
    ),
    (
        "thinking/causal-flaky-tests-time-dependent",
        "We have tests that pass locally but fail in CI about 20% of the time. They're not the same tests each time. When we rerun the CI pipeline, they usually pass. What's causing this?",
        r'''<think>
Flaky tests that pass locally, fail 20% in CI, different tests each time. Let me reason through the causes.

**Key observations:**
1. Different tests fail each time → not a specific bug in one test
2. Pass locally, fail in CI → environment difference
3. 20% failure rate → probabilistic, not deterministic
4. Rerunning fixes it → timing or ordering issue

**Most likely causes:**

1. **Test ordering / shared state**
   - Tests share a database or global state
   - When run in certain orders, one test's side effects affect another
   - CI may run tests in parallel or different order than local

2. **Timing/race conditions**
   - Tests rely on setTimeout, sleep, or timing
   - CI runners are slower → timeouts hit differently
   - Async operations complete in different order

3. **Resource contention**
   - CI runners have less CPU/RAM → slower execution
   - Database connections timeout
   - Network calls to external services flake

4. **Time-dependent tests**
   - Tests that check "created today" or compare timestamps
   - CI might run near midnight (timezone issues)
   - Tests that assume current time

5. **Random ordering exposing shared state**
   - pytest-randomly, Jest --randomize → different order each run
   - One test creates data that another test accidentally depends on

**The "different tests each time" is the key clue.**
This strongly suggests test ordering + shared state. Test A leaves data behind → Test B (which runs after A sometimes) finds unexpected data → fails. But next run, the order is different → B runs before A → passes.
</think>

The "different tests each time" is the key diagnostic. This is almost always **shared state + test ordering**.

## Root Cause Analysis

```
WHY "different tests fail each time":
  Test A creates a user with email "test@test.com"
  Test B (later) creates a user with email "test@test.com" → UNIQUE constraint error

  Run 1: A runs before B → B fails (duplicate email)
  Run 2: B runs before A → both pass (B creates first, A creates second)
  Run 3: C runs between them → different failure entirely

  The tests aren't individually broken — they CONTAMINATE each other.

WHY "pass locally, fail in CI":
  Local: sequential execution, always same order → consistent
  CI: parallel execution OR randomized order → inconsistent
  CI runners also slower (shared infrastructure) → timing issues
```

## Fix 1: Isolate Test State

```python
# ❌ SHARED STATE: tests contaminate each other
class TestUserCreation:
    def test_create_user(self):
        user = User.create(email="test@test.com")  # Left in DB after test
        assert user.id is not None

class TestUserLogin:
    def test_login(self):
        user = User.create(email="test@test.com")  # FAILS: duplicate email!
        token = login(user.email, "password")
        assert token is not None

# ✅ FIXED: each test cleans up after itself (or use transactions)

# Option A: Django's TestCase (each test runs in a transaction that rolls back)
from django.test import TestCase

class TestUserCreation(TestCase):  # Automatically rolls back DB after each test
    def test_create_user(self):
        user = User.create(email="test@test.com")  # Rolled back after test
        assert user.id is not None

# Option B: pytest with database cleanup
@pytest.fixture(autouse=True)
def clean_db():
    yield
    User.objects.all().delete()  # Clean up after each test

# Option C: unique data per test
import uuid
def test_create_user():
    email = f"test-{uuid.uuid4()}@test.com"  # Unique every run
    user = User.create(email=email)
    assert user.id is not None
```

## Fix 2: Remove Time Dependencies

```python
# ❌ FLAKY: depends on current time
def test_new_user_trial():
    user = User.create()
    assert user.trial_ends_at > datetime.now()  # What if test runs at 23:59:59?

# ✅ FIXED: freeze time
from freezegun import freeze_time

@freeze_time("2024-06-15 12:00:00")
def test_new_user_trial():
    user = User.create()
    assert user.trial_ends_at == datetime(2024, 7, 15, 12, 0, 0)  # Deterministic


# ❌ FLAKY: timing-dependent assertion
def test_background_job():
    start_background_job()
    time.sleep(2)  # "Should be done in 2 seconds"... on a slow CI runner? Maybe not.
    assert job.status == "completed"

# ✅ FIXED: poll with timeout instead of fixed sleep
import time

def test_background_job():
    start_background_job()
    deadline = time.time() + 10  # Wait UP TO 10 seconds
    while time.time() < deadline:
        if job.status == "completed":
            break
        time.sleep(0.1)
    assert job.status == "completed"
```

## Fix 3: Don't Hit External Services

```python
# ❌ FLAKY: depends on external API being available
def test_send_email():
    result = email_service.send("user@test.com", "Welcome!")
    assert result.status == "sent"
    # Fails when: SMTP server is slow, network flakes, rate limited

# ✅ FIXED: mock external services
from unittest.mock import patch

def test_send_email():
    with patch('app.email_service.send') as mock_send:
        mock_send.return_value = {"status": "sent"}
        result = email_service.send("user@test.com", "Welcome!")
        assert result["status"] == "sent"
        mock_send.assert_called_once()
```

## Diagnostic Steps

```bash
# 1. Find if it's ordering-dependent
# Run tests in random order (if not already):
pytest --randomly-seed=12345  # Same seed = same order = reproducible
# If failures change with seed → ordering problem

# 2. Find which test contaminates which
# Run the failing test in isolation:
pytest tests/test_orders.py::test_create_order -v
# If it passes alone → another test is contaminating it

# 3. Find the contaminator
pytest --last-failed --first-failed  # Run the failure first next time

# 4. Check for leftover state
pytest -x --tb=short  # Stop on first failure, show which test ran before it
```

The fix is almost always: isolate test state (transactions, unique data, cleanup), mock external dependencies, and freeze time. These three changes eliminate 90% of flaky tests.'''
    ),
    (
        "thinking/multiperspective-microservices-communication",
        "Should our microservices communicate synchronously via REST or asynchronously via a message queue? Different team members have strong opinions both ways.",
        r'''<think>
Sync vs async microservice communication — a genuine multi-perspective analysis.

**Synchronous (REST/gRPC) perspective:**
- Simple to understand and debug
- Request/response pattern is natural
- Easy to implement
- Good for queries (need immediate response)
- Good for commands where you need confirmation

**Asynchronous (message queue) perspective:**
- Decouples services (producer doesn't wait for consumer)
- Better fault tolerance (messages persisted, processed when consumer is ready)
- Better for high throughput (buffer spikes)
- Natural for event-driven architecture
- Handles slow consumers gracefully

**The real answer: use BOTH, depending on the operation.**
- Sync: when you need an immediate response (GET user, validate payment)
- Async: when you can fire-and-forget (send email, update analytics, generate report)
- Async: when crossing domain boundaries (order placed → inventory, shipping, notifications)

The mistake is choosing one for everything.
</think>

Both are right — for different situations. The answer is **use both**, chosen by the nature of each interaction.

## When Each Pattern Fits

```
SYNCHRONOUS (REST/gRPC) — when you NEED the answer NOW:

  User clicks "View Order" →
    Frontend → Order Service: "GET /orders/123"
    Order Service → User Service: "GET /users/42"  (need user name for response)
    Order Service → response with order + user name
    Frontend displays the order

  The frontend CANNOT render without the data.
  Synchronous is the natural fit.

ASYNCHRONOUS (Message Queue) — when you DON'T need an immediate response:

  User clicks "Place Order" →
    Order Service: create order, return "Order placed!" to user
    Order Service → publishes "OrderPlaced" event to message queue
    → Inventory Service: decrement stock (whenever it picks up the message)
    → Email Service: send confirmation email (whenever ready)
    → Analytics Service: track purchase (can be delayed minutes)
    → Shipping Service: create shipment (can be delayed)

  The user doesn't need to WAIT for inventory, email, analytics, shipping.
  Asynchronous is the natural fit.
```

## Decision Framework

```
ASK: "Does the caller NEED the result to continue?"

  YES → synchronous
    "Show me the user's profile"  → need the data to render
    "Is this coupon code valid?"  → need the answer to proceed
    "Authenticate this token"     → must verify before allowing access

  NO → asynchronous
    "Send a welcome email"        → user doesn't wait for email delivery
    "Update the search index"     → eventual consistency is fine
    "Generate a PDF report"       → notify when done, don't wait
    "Notify other services"       → they'll process when ready

  BOTH → hybrid
    "Place an order"
    → Sync: validate + save order + charge payment (user waits)
    → Async: send email + update inventory + notify shipping (user doesn't wait)
```

## Common Patterns

```python
# HYBRID: synchronous for the critical path, async for side effects
@app.post("/orders")
async def create_order(data: OrderRequest):
    # SYNCHRONOUS — user waits for these:
    user = await user_service.get(data.user_id)          # Need user data
    payment = await payment_service.charge(data.total)    # Need payment result

    if payment.status != "success":
        raise PaymentError("Payment failed")

    order = await db.create_order(data)

    # ASYNCHRONOUS — user does NOT wait for these:
    await message_queue.publish("order.created", {
        "order_id": order.id,
        "user_id": user.id,
        "items": data.items,
    })
    # Email service, inventory service, analytics service
    # will pick this up and process independently

    return {"order_id": order.id, "status": "created"}  # Return immediately
```

## Trade-offs Table

```
                    SYNCHRONOUS         ASYNCHRONOUS
Latency:            Adds to total       Doesn't add to user-facing latency
Coupling:           Tight (both must    Loose (producer doesn't know
                    be up)              about consumers)
Debugging:          Easy (request →     Harder (message → where did it go?)
                    response)
Failure handling:   Immediate error     Message retried later
Data consistency:   Strong              Eventual
Complexity:         Lower               Higher (queue, dead letters, ordering)
Scaling:            Limited by slowest  Each service scales independently
                    service in chain
```

## Practical Recommendations

```
START WITH:
  Synchronous REST for most things (simpler, sufficient for most cases)
  Add async for specific use cases:
  □ Sending notifications (email, SMS, push)
  □ Cross-domain events ("order placed" → multiple services react)
  □ Long-running tasks (report generation, data processing)
  □ Fan-out patterns (one event → many consumers)

DON'T:
  ✗ Make everything async "for scalability" (adds complexity for no benefit)
  ✗ Make everything sync (chains of 10 sync calls = slow and fragile)
  ✗ Use async to avoid dealing with failure (failed messages still need handling)
```

Use REST when the caller needs the answer. Use a message queue when the caller doesn't. Most systems need both.'''
    ),
    (
        "thinking/firstprinciples-why-https",
        "Why do we need HTTPS? Our website doesn't handle passwords or credit cards — it's just a blog. Is HTTP fine?",
        r'''<think>
Why HTTPS from first principles, even for a blog.

**What HTTP actually means:**
HTTP sends data in PLAIN TEXT. Anyone between the user and the server can:
1. READ everything (passwords, cookies, content)
2. MODIFY anything (inject ads, malware, redirect links)
3. IMPERSONATE the server (man-in-the-middle)

**Who is "anyone between the user and the server"?**
- The WiFi hotspot operator (coffee shop, airport, hotel)
- The ISP
- Any router along the path
- Anyone on the same network (in unencrypted WiFi)
- Government surveillance systems
- Corporate proxy servers

**Why HTTPS matters even for a blog:**
1. **Content integrity** — ISPs inject ads into HTTP pages. Your blog post about privacy could have ads for tracking software injected by the ISP.
2. **User privacy** — which articles users read is private. HTTP exposes every URL to observers.
3. **Authentication cookies** — if you have a login (CMS admin), cookies sent over HTTP can be stolen.
4. **Trust signals** — browsers warn "Not Secure" for HTTP. Users bounce.
5. **SEO** — Google ranks HTTPS higher.
6. **Required for modern web** — Service workers, HTTP/2, geolocation API all require HTTPS.
7. **Free with Let's Encrypt** — no cost excuse anymore.
</think>

HTTP sends everything in **plain text**. Even for a blog, this means anyone between your user and your server can read and modify everything.

## What Happens Without HTTPS

```
USER'S BROWSER ←→ [WiFi Router] ←→ [ISP] ←→ [Routers] ←→ YOUR SERVER

WITH HTTP (plain text):
  Every entity in that chain can:

  1. READ everything:
     - Which pages the user visits
     - Any cookies (session tokens, login cookies)
     - Form data (search queries, comments, login credentials)

  2. MODIFY anything:
     - Inject ads into your blog posts
     - Replace download links with malware
     - Inject cryptocurrency miners (ISPs have done this)
     - Redirect users to phishing pages

  3. IMPERSONATE your server:
     - Show a completely different page
     - Steal credentials for your CMS admin panel

WITH HTTPS (encrypted):
  Every entity sees:
  - That the user connected to your-blog.com
  - How much data was transferred
  - Nothing else. Content is encrypted end-to-end.
```

## Real-World Attacks That Happen on HTTP

```
1. ISP AD INJECTION (very common):
   You serve: clean blog post about cooking
   User sees: your blog post + injected ads for gambling sites
   ISPs like Comcast, AT&T have been caught doing this.

2. WIFI HOTSPOT ATTACK (trivial):
   User reads your blog at a coffee shop
   Attacker on same WiFi: captures session cookie
   Attacker: logs into your WordPress admin panel
   → Defaces your entire blog

3. GOVERNMENT SURVEILLANCE:
   HTTP: "User 42 read articles about [sensitive topic]"
   HTTPS: "User 42 visited your-blog.com" (can't see which pages)

4. MALWARE INJECTION:
   You serve: download link for your free ebook
   Attacker modifies: download link points to malware.exe
   User trusts the download because it came from YOUR site
```

## Why "Just a Blog" Still Needs HTTPS

```
"We don't handle passwords"
  → Do you have a CMS admin login? WordPress? That's a password.
  → Do users have accounts for comments? Those are passwords.
  → Even without logins, session cookies can be hijacked.

"We don't handle credit cards"
  → You handle user ATTENTION and TRUST.
  → Injected ads and malware destroy both.

"Our content is public anyway"
  → WHICH content a user reads is private.
  → Reading a blog about cancer treatment ≠ public information.

"It's too complicated/expensive"
  → Let's Encrypt: free, automated, takes 5 minutes.
  → Most hosting providers include it by default.

PRACTICAL REASONS:
  □ Browsers show "Not Secure" warning → users leave
  □ Google ranks HTTPS sites higher → better SEO
  □ HTTP/2 requires HTTPS → faster site
  □ Service Workers require HTTPS → offline support, push notifications
  □ Geolocation API requires HTTPS
  □ Progressive Web Apps require HTTPS
```

## Setup (It's Free and Takes 5 Minutes)

```bash
# Let's Encrypt with certbot (free, automatic renewal)
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-blog.com -d www.your-blog.com

# That's it. HTTPS is now active with auto-renewal.

# Or if using a hosting provider:
# Netlify, Vercel, GitHub Pages, Cloudflare: HTTPS is automatic and free
# Just enable it in settings.
```

**There is no legitimate reason to use HTTP in 2024+.** HTTPS is free, fast, and required by modern browsers and APIs. The question isn't "why HTTPS?" — it's "why would anyone still use HTTP?"'''
    ),
    (
        "thinking/backtrack-singleton-to-dependency-injection",
        "I use the Singleton pattern for my database connection, logger, and config. Now my tests are incredibly hard to write because everything uses the global singleton. How do I fix this?",
        r'''<think>
Singleton pattern making testing hard — this is a textbook case of why singletons are considered an anti-pattern by many.

**Why singletons make testing hard:**
1. Global state — one test changes the singleton, affects all subsequent tests
2. Can't swap the implementation — tests can't use a fake database
3. Hidden dependencies — functions call Database.instance() internally, no way to inject a mock
4. Order-dependent tests — singleton holds state between tests

**Backtrack from singleton to dependency injection:**
Instead of classes reaching out to get their own dependencies (pull model), pass dependencies IN (push model).

The key insight: the singleton pattern hides dependencies. DI makes them explicit.

**Migration path:**
1. Keep the singleton instances (for now)
2. Add constructor parameters for dependencies
3. Default to singleton values (backward compatible)
4. In tests, pass in mocks/fakes
5. Eventually remove the singletons entirely
</think>

Singletons make testing hard because they **hide dependencies**. The fix is to make dependencies explicit via parameters.

## The Problem

```python
# ❌ SINGLETON PATTERN: hidden dependencies, untestable
class Database:
    _instance = None

    @classmethod
    def instance(cls):
        if cls._instance is None:
            cls._instance = cls("postgres://prod-server/db")
        return cls._instance

class UserService:
    def get_user(self, user_id):
        db = Database.instance()  # Hidden dependency! Tests can't control this
        return db.query("SELECT * FROM users WHERE id = %s", user_id)

class OrderService:
    def create_order(self, data):
        db = Database.instance()          # Same hidden dependency
        logger = Logger.instance()        # Another hidden dependency
        config = Config.instance()        # And another

        order = db.insert("orders", data)
        logger.info(f"Order created: {order.id}")
        if config.get("send_emails"):
            EmailService.instance().send(data["email"], "Order confirmed")
        return order

# TESTING THIS IS A NIGHTMARE:
def test_create_order():
    # How do I:
    # - Use a test database instead of production?
    # - Prevent real emails from being sent?
    # - Control what config returns?
    # Answer: monkey-patching, which is fragile and error-prone
    service = OrderService()
    service.create_order({"email": "test@test.com"})
    # This just hit the PRODUCTION DATABASE and sent a REAL EMAIL
```

## Backtrack: Dependency Injection (Gradual Migration)

```python
# ✅ STEP 1: Add parameters with defaults (backward compatible)
class UserService:
    def __init__(self, db=None):
        self.db = db or Database.instance()  # Default to singleton

    def get_user(self, user_id):
        return self.db.query("SELECT * FROM users WHERE id = %s", user_id)

class OrderService:
    def __init__(self, db=None, logger=None, config=None, email=None):
        self.db = db or Database.instance()
        self.logger = logger or Logger.instance()
        self.config = config or Config.instance()
        self.email = email or EmailService.instance()

    def create_order(self, data):
        order = self.db.insert("orders", data)
        self.logger.info(f"Order created: {order.id}")
        if self.config.get("send_emails"):
            self.email.send(data["email"], "Order confirmed")
        return order

# PRODUCTION CODE: unchanged (uses defaults)
service = OrderService()  # Still works, uses singletons

# TESTING: now easy! Pass in fakes
def test_create_order():
    fake_db = FakeDatabase()
    fake_logger = FakeLogger()
    fake_config = FakeConfig({"send_emails": False})
    fake_email = FakeEmailService()

    service = OrderService(
        db=fake_db,
        logger=fake_logger,
        config=fake_config,
        email=fake_email,
    )

    order = service.create_order({"email": "test@test.com"})

    assert fake_db.last_insert_table == "orders"
    assert fake_email.sent_count == 0  # No email sent (config disabled)
    # No production database touched. No real email sent. Test runs in 1ms.
```

## Step 2: Wire Dependencies at the Top Level

```python
# Create all dependencies in ONE place (composition root)
# app.py
def create_app():
    db = Database("postgres://prod-server/db")
    logger = Logger()
    config = Config.from_env()
    email = EmailService(config.smtp_host)

    user_service = UserService(db=db)
    order_service = OrderService(db=db, logger=logger, config=config, email=email)

    app = FastAPI()
    app.state.user_service = user_service
    app.state.order_service = order_service
    return app

# test_app.py
def create_test_app():
    db = FakeDatabase()  # In-memory
    logger = FakeLogger()
    config = FakeConfig({"send_emails": False})
    email = FakeEmailService()

    user_service = UserService(db=db)
    order_service = OrderService(db=db, logger=logger, config=config, email=email)

    app = FastAPI()
    app.state.user_service = user_service
    app.state.order_service = order_service
    return app
```

## The Pattern

```
SINGLETON (pull model):
  Class reaches OUT to get its dependencies
  → Dependencies hidden → can't test → can't swap → global state

DEPENDENCY INJECTION (push model):
  Dependencies pushed IN through constructor
  → Dependencies explicit → easy to test → easy to swap → no global state

MIGRATION PATH:
  1. Add constructor parameters with defaults → backward compatible
  2. In tests, pass in fakes → tests work immediately
  3. Create a composition root → wire everything in one place
  4. Remove singleton .instance() methods → fully DI
  5. Each step is independent and safe
```'''
    ),
    (
        "thinking/analogy-database-indexes-textbook-index",
        "Our database queries are getting slow as the data grows. Someone suggested adding indexes but I don't understand what they do or when to use them.",
        r'''<think>
Database indexes — the textbook index analogy is perfect because that's literally where the name comes from.

**Without an index:**
To find a topic in a 500-page textbook without an index, you read every page. That's a "full table scan" in database terms.

**With an index:**
Turn to the back of the book. Look up "photosynthesis" → page 234, 278, 312. Go directly to those pages.

**Key properties of indexes:**
1. Faster reads (lookup by indexed column)
2. Slower writes (index must be updated on insert/update/delete)
3. Uses extra space (the index itself is stored on disk)
4. Trade-off: read speed vs write speed vs storage

**When to add indexes:**
- Columns you search by frequently (WHERE clauses)
- Columns you join on (foreign keys)
- Columns you sort by (ORDER BY)

**When NOT to add indexes:**
- Tables with very few rows (scan is fast enough)
- Columns that change constantly (index rebuild overhead)
- Columns with very low cardinality (boolean, status with 3 values)
</think>

A database index works exactly like the **index at the back of a textbook**.

## The Analogy

```
WITHOUT AN INDEX:
  "Find all mentions of 'photosynthesis' in this 500-page textbook"
  → Read page 1... nope
  → Read page 2... nope
  → Read page 3... nope
  → ... (500 pages later)
  → Found them on pages 234, 278, 312
  → Time: read all 500 pages (SLOW)

  = SELECT * FROM articles WHERE topic = 'photosynthesis'
  → Database scans ALL 500,000 rows
  → Finds 3 matching rows
  → Time: read all 500,000 rows (SLOW)

WITH AN INDEX:
  Turn to the index at the back of the book:
  "Photosynthesis... see pages 234, 278, 312"
  → Go directly to those pages
  → Time: look up one entry + read 3 pages (FAST)

  = CREATE INDEX idx_topic ON articles(topic)
  → Database looks up 'photosynthesis' in the index
  → Index says: "rows 234, 278, 312"
  → Database reads only those 3 rows
  → Time: one index lookup + 3 row reads (FAST)
```

## In Practice

```sql
-- WITHOUT INDEX: database scans every row
EXPLAIN SELECT * FROM orders WHERE user_id = 42;
-- Seq Scan on orders (rows: 1,000,000, time: 850ms)
-- Scanned ALL 1 million rows to find user 42's 15 orders

-- ADD INDEX:
CREATE INDEX idx_orders_user_id ON orders(user_id);

-- WITH INDEX: database goes directly to matching rows
EXPLAIN SELECT * FROM orders WHERE user_id = 42;
-- Index Scan using idx_orders_user_id (rows: 15, time: 0.5ms)
-- Looked up user_id=42 in the index → found 15 rows → read only those
-- 1700x faster!
```

## When to Add Indexes

```sql
-- 1. Columns in WHERE clauses (the most common need)
SELECT * FROM users WHERE email = 'dan@example.com';
CREATE INDEX idx_users_email ON users(email);

-- 2. Columns in JOIN conditions
SELECT * FROM orders JOIN users ON orders.user_id = users.id;
CREATE INDEX idx_orders_user_id ON orders(user_id);
-- (Primary keys are automatically indexed)

-- 3. Columns in ORDER BY
SELECT * FROM products ORDER BY created_at DESC LIMIT 20;
CREATE INDEX idx_products_created ON products(created_at DESC);

-- 4. Composite indexes for multi-column queries
SELECT * FROM orders WHERE user_id = 42 AND status = 'pending';
CREATE INDEX idx_orders_user_status ON orders(user_id, status);
-- Order matters! (user_id, status) helps queries filtering by user_id
-- or by user_id+status, but NOT by status alone
```

## The Trade-off

```
INDEXES ARE NOT FREE:

  BENEFIT: faster reads (SELECT, JOIN, ORDER BY)

  COST 1: slower writes
    Every INSERT/UPDATE/DELETE must ALSO update the index
    1 index: ~10% slower writes
    10 indexes: ~100% slower writes (2x slower)

  COST 2: storage space
    An index is a separate data structure on disk
    Can be 10-30% of the table size

  RULE OF THUMB:
    Read-heavy table (SELECT 90%, INSERT 10%): add indexes freely
    Write-heavy table (INSERT 90%, SELECT 10%): add indexes sparingly

  DON'T INDEX:
    - Boolean columns (only 2 values → index barely helps)
    - Columns rarely queried
    - Very small tables (< 1000 rows → scan is fast enough)
    - Columns that change constantly (index rebuilt every update)
```

## Finding Missing Indexes

```sql
-- PostgreSQL: find slow queries
SELECT query, calls, mean_exec_time
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Look for Seq Scan in EXPLAIN output → add index on that column
EXPLAIN ANALYZE SELECT * FROM orders WHERE created_at > '2024-01-01';
-- If you see "Seq Scan" → needs an index
-- If you see "Index Scan" → already indexed
```

**The golden rule:** if you have a WHERE clause on a column in a table with more than a few thousand rows, that column probably needs an index.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
