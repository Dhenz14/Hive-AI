"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 14)"""

PAIRS = [
    (
        "thinking/multiperspective-feature-flags-adoption",
        "Should we adopt feature flags? Some devs say it's unnecessary complexity — just use git branches. Others say it's essential for safe deploys. Who's right?",
        r'''<think>
Feature flags vs git branches. Different perspectives.

**Against feature flags:**
- "Just use branches" — merge when ready, deploy when merged
- Feature flags add if/else everywhere, make code harder to read
- Stale flags become tech debt (forgotten flags never cleaned up)
- Testing complexity: need to test all flag combinations

**For feature flags:**
- Decouple deployment from release (deploy code, turn on feature later)
- Instant rollback without redeployment (flip flag off)
- Gradual rollout (1% → 10% → 50% → 100%)
- A/B testing built in
- Non-engineers can toggle features (product managers, support)

**When branches are sufficient:**
- Small team, simple deploy process
- Features that are all-or-nothing
- No need for gradual rollout

**When feature flags are essential:**
- Large team deploying frequently
- Need to decouple deploy from release
- Want instant rollback without redeploy
- A/B testing requirements
- Long-running features that need to be merged but not released

For most teams: feature flags are worth it for critical features, but not for everything.
</think>

Both sides have valid points. Here's when each approach wins.

## Git Branches Alone (When It's Enough)

```
WORKFLOW:
  Develop on branch → merge to main → deploy → feature is live

WORKS WELL WHEN:
  ✓ Small team (< 5 developers)
  ✓ Simple, fast deploys (< 5 minutes)
  ✓ Features are small and ship quickly
  ✓ Rollback = deploy previous version (acceptable delay)
  ✓ No need for gradual rollout or A/B testing

BREAKS DOWN WHEN:
  ✗ Feature takes 3 weeks → long-lived branch → merge conflicts
  ✗ Deploy takes 30 minutes → rollback takes 30 minutes
  ✗ Multiple teams deploy to same service → coordination overhead
  ✗ Need to release to 5% of users first → can't with branches
```

## Feature Flags (When They're Worth It)

```
WORKFLOW:
  Develop behind flag → merge to main (flag OFF) → deploy →
  turn flag ON for 5% → monitor → 50% → 100%

WHEN THEY'RE ESSENTIAL:
  ✓ Need instant rollback (flag OFF = instant, no redeploy)
  ✓ Long-running features (merge daily, keep flag off until ready)
  ✓ Gradual rollout (1% → 10% → 100%)
  ✓ A/B testing (50% see new feature, 50% see old)
  ✓ Non-engineer release control (PM decides when to launch)
  ✓ Multiple teams deploying to same codebase
```

## Practical Implementation (Keep It Simple)

```python
# Don't over-engineer. Start with a simple flag system.

# Option 1: Environment variable flags (simplest)
import os

def is_enabled(flag_name: str) -> bool:
    return os.environ.get(f"FEATURE_{flag_name}", "false").lower() == "true"

# Usage:
if is_enabled("NEW_CHECKOUT"):
    return new_checkout_flow(order)
else:
    return old_checkout_flow(order)


# Option 2: Database-backed flags (more flexible)
class FeatureFlags:
    def __init__(self, db):
        self.db = db
        self._cache = {}

    def is_enabled(self, flag: str, user_id: int = None) -> bool:
        flag_config = self._get_flag(flag)
        if not flag_config:
            return False

        if flag_config.rollout_percentage == 100:
            return True
        if flag_config.rollout_percentage == 0:
            return False

        # Gradual rollout: deterministic per user
        if user_id:
            return (hash(f"{flag}:{user_id}") % 100) < flag_config.rollout_percentage
        return False

# Gradual rollout:
# Day 1: UPDATE feature_flags SET rollout_percentage = 5 WHERE name = 'new_checkout';
# Day 2: UPDATE feature_flags SET rollout_percentage = 25 WHERE name = 'new_checkout';
# Day 3: UPDATE feature_flags SET rollout_percentage = 100 WHERE name = 'new_checkout';
# Problem: UPDATE feature_flags SET rollout_percentage = 0 WHERE name = 'new_checkout';
#          (instant rollback — no redeploy needed)
```

## The Compromise: Flags for Critical Features Only

```
DON'T flag everything (that's the "unnecessary complexity" camp's valid concern).
DO flag:
  □ New user-facing features (gradual rollout)
  □ Risky infrastructure changes (database migration, new payment provider)
  □ Anything that MUST be instantly rollbackable
  □ A/B tests

DON'T flag:
  □ Bug fixes (just fix them)
  □ Internal refactors (no user impact)
  □ Small UI tweaks (low risk)
  □ Dependency updates (flag adds no value)

ALWAYS clean up:
  □ After feature is 100% rolled out → remove the flag + old code
  □ Set a calendar reminder: "clean up FEATURE_NEW_CHECKOUT in 2 weeks"
  □ Track flag count: if you have > 20 active flags, you have a problem
```'''
    ),
    (
        "thinking/backtrack-over-abstraction-to-simple-code",
        "A senior dev on our team refactored our codebase to use the Strategy pattern, Factory pattern, and Repository pattern. Now a simple database query goes through 5 layers of abstraction. Is this normal?",
        r'''<think>
Over-abstraction — a common problem when design patterns are applied without clear need.

**The problem:**
What was: `db.query("SELECT * FROM users WHERE id = ?", id)`
Is now: UserFactory → UserRepository → UserQueryStrategy → UserMapper → db.query(...)

5 layers for a simple SELECT. This is pattern abuse.

**Why this happens:**
- Developers learn patterns and apply them everywhere ("when you have a hammer...")
- SOLID principles taken to the extreme
- "Future-proofing" for requirements that may never come
- Resume-driven development (impressive on a CV, bad in code)

**When patterns ARE appropriate:**
- Strategy pattern: when you have MULTIPLE strategies that are SWAPPED at runtime
- Factory pattern: when object creation is complex or needs to vary
- Repository pattern: when you need to abstract the data source (switching databases)

**When they're NOT appropriate:**
- One strategy → no need for Strategy pattern
- Simple constructor → no need for Factory
- One database that will never change → Repository adds zero value

**The right approach: add abstraction when you feel the PAIN, not before.**
"Three strikes and you refactor" — wait until you have 3 similar cases before abstracting.

I should help them simplify without insulting the senior dev's work.
</think>

This is **over-engineering**. Design patterns solve specific problems — applying them without those problems creates unnecessary complexity.

## What Over-Abstraction Looks Like

```python
# WHAT THE CODE SHOULD BE:
def get_user(user_id):
    return db.query("SELECT * FROM users WHERE id = %s", user_id)

# WHAT IT BECAME:
class UserQueryStrategy:
    def build_query(self, criteria): ...

class UserByIdStrategy(UserQueryStrategy):
    def build_query(self, criteria):
        return "SELECT * FROM users WHERE id = %s", (criteria["id"],)

class UserRepository:
    def __init__(self, query_strategy_factory, mapper):
        self.strategy_factory = query_strategy_factory
        self.mapper = mapper

    def find_by_id(self, user_id):
        strategy = self.strategy_factory.create("by_id")
        query, params = strategy.build_query({"id": user_id})
        row = self.db.execute(query, params)
        return self.mapper.to_entity(row)

class UserMapper:
    def to_entity(self, row):
        return User(id=row["id"], name=row["name"], email=row["email"])

class UserQueryStrategyFactory:
    def create(self, strategy_type):
        strategies = {"by_id": UserByIdStrategy, "by_email": UserByEmailStrategy}
        return strategies[strategy_type]()

# To get a user: 5 classes, 3 levels of indirection
# Original: 1 function, 1 line
```

## When Each Pattern Is ACTUALLY Needed

```python
# STRATEGY PATTERN: useful when you swap behavior at RUNTIME
# ✗ NOT NEEDED: one query strategy that never changes
# ✓ NEEDED: multiple payment processors, chosen per transaction
class PaymentProcessor:
    def charge(self, amount): ...

class StripeProcessor(PaymentProcessor): ...
class PayPalProcessor(PaymentProcessor): ...

def process_payment(order, processor: PaymentProcessor):
    processor.charge(order.total)
# The processor CHANGES based on user choice — that's the Strategy pattern


# FACTORY PATTERN: useful when creation is COMPLEX
# ✗ NOT NEEDED: User(id=1, name="Alice") — just use the constructor
# ✓ NEEDED: object creation requires configuration, validation, or varies by type
def create_notification(type, user):
    if type == "email":
        return EmailNotification(user.email, smtp_config)
    elif type == "sms":
        return SMSNotification(user.phone, twilio_config)
    elif type == "push":
        return PushNotification(user.device_token, firebase_config)


# REPOSITORY PATTERN: useful when you ACTUALLY switch data sources
# ✗ NOT NEEDED: PostgreSQL that will never change
# ✓ NEEDED: tests use in-memory store, production uses PostgreSQL
class UserRepository:
    def get(self, id): ...

class PostgresUserRepository(UserRepository):
    def get(self, id): return db.query(...)

class InMemoryUserRepository(UserRepository):
    def get(self, id): return self.users[id]
# This lets tests run without a database — legitimate use
```

## The Right Amount of Abstraction

```
THE RULE: "Three strikes and you refactor"

Strike 1: Write it inline. Simple, direct, readable.
Strike 2: You write something similar. Copy-paste is OK.
Strike 3: Third time → NOW extract the abstraction.

BEFORE ADDING A PATTERN, ASK:
  "What CONCRETE problem does this pattern solve TODAY?"

  ✓ "We need to swap payment processors per transaction" → Strategy
  ✓ "Tests need a different data source than production" → Repository
  ✓ "Object creation varies by type and is complex" → Factory

  ✗ "We MIGHT need to swap databases someday" → YAGNI
  ✗ "Design patterns are best practice" → Not without a reason
  ✗ "It's more architecturally clean" → Clean for whom?
```

## How to Simplify (Diplomatically)

```python
# Step 1: Remove layers that add no behavior
# If UserMapper just copies fields → remove it, use the row directly
# If UserQueryStrategyFactory only has one strategy → remove it, use the strategy directly

# Step 2: Inline single-implementation abstractions
# If UserRepository has ONE implementation → it's not abstracting anything
# Replace with a module-level function

# Step 3: Keep abstractions that are actually USED
# If Repository pattern enables test mocking → keep it
# If Strategy pattern is used with one strategy → remove it

# The goal: every layer of indirection must EARN its place
# by solving a concrete, current problem.
```'''
    ),
    (
        "thinking/causal-slow-page-load-waterfall",
        "Our web page takes 8 seconds to load. The backend API responds in 200ms. Where are the other 7.8 seconds going?",
        r'''<think>
8 second page load but 200ms API — 7.8 seconds unaccounted for. Let me think about what else happens in a page load.

**Full page load chain:**
1. DNS lookup (50-100ms first visit)
2. TCP connection (50-100ms)
3. TLS handshake (50-100ms)
4. Request sent → server processing (200ms) → response received
5. HTML parsed → discovers CSS, JS, images
6. CSS downloaded and parsed (render-blocking)
7. JavaScript downloaded, parsed, and executed (render-blocking)
8. JavaScript may make API calls → wait for response → render
9. Images and fonts downloaded
10. Layout and paint

**Most likely causes of 7.8s gap:**

1. **JavaScript bundle too large**: 2MB of JavaScript takes seconds to download and parse
2. **Render-blocking resources**: CSS and JS in <head> block rendering
3. **Waterfall loading**: resources loaded sequentially instead of parallel
4. **Client-side rendering**: page is blank until JS downloads, parses, and fetches data
5. **Too many HTTP requests**: 50+ resources each with their own round-trip
6. **Large images**: unoptimized 5MB hero image
7. **Web fonts**: font files block text rendering (FOIT)
8. **Third-party scripts**: analytics, chat widgets, ad trackers loading synchronously

The 200ms API time is just one piece. The browser has to do a LOT of work before and after that API call.
</think>

The API response is only one piece of the puzzle. The other 7.8 seconds is **browser rendering pipeline + resource loading**.

## Where the Time Goes (Typical Breakdown)

```
Page Load Timeline:

  0.0s  DNS lookup                    50ms
  0.05s TCP + TLS connection         100ms
  0.15s HTML request + response      200ms ← your API time
  0.35s Parse HTML, discover resources
  0.4s  Download CSS (render-blocking) 200ms
  0.6s  Download JS bundle (2MB!)     1500ms ← LIKELY BOTTLENECK
  2.1s  Parse + compile JavaScript     800ms ← LIKELY BOTTLENECK
  2.9s  JS executes, makes API call    200ms ← ANOTHER round-trip
  3.1s  API response received
  3.1s  JS renders the page            200ms
  3.3s  Download images (5 images)    2000ms
  5.3s  Download web fonts             500ms
  5.8s  Third-party scripts (analytics) 2000ms
  7.8s  Everything loaded. Page interactive.
```

## Diagnosis: Use Chrome DevTools

```
1. Open Chrome DevTools → Network tab
2. Reload the page
3. Look at the WATERFALL chart:
   - Which resources are large? (sort by Size)
   - Which resources are slow? (sort by Time)
   - What's blocking what? (look for long bars)

4. Check the Performance tab:
   - LCP (Largest Contentful Paint): when does the main content appear?
   - FID (First Input Delay): when can the user interact?
   - CLS (Cumulative Layout Shift): does the page jump around?

5. Run Lighthouse:
   - Chrome DevTools → Lighthouse → Generate report
   - Shows specific recommendations with estimated time savings
```

## Most Common Fixes (In Order of Impact)

```html
<!-- FIX 1: Defer/async JavaScript (biggest win usually) -->

<!-- ❌ BLOCKS RENDERING: browser stops everything to download + parse JS -->
<head>
    <script src="bundle.js"></script>  <!-- 2MB, blocks for 3 seconds -->
</head>

<!-- ✅ DEFER: download in parallel, execute after HTML parsed -->
<head>
    <script defer src="bundle.js"></script>
</head>

<!-- ✅ ASYNC: download in parallel, execute when ready (for independent scripts) -->
<script async src="analytics.js"></script>
```

```
FIX 2: Code splitting (don't load everything upfront)

❌ One bundle: bundle.js = 2MB (ALL code for ALL pages)
✅ Split bundles: home.js = 50KB, dashboard.js = 200KB, admin.js = 300KB

// React/Next.js:
const Dashboard = React.lazy(() => import('./Dashboard'));
// Dashboard code only loads when user navigates to /dashboard
```

```
FIX 3: Optimize images (often 50%+ of page weight)

❌ hero-image.png: 5MB, 4000×3000px
✅ hero-image.webp: 200KB, 1200×800px (sized for viewport)

<img src="hero.webp"
     loading="lazy"          <!-- Only load when visible -->
     width="1200" height="800"
     alt="Hero image">

<!-- Use srcset for responsive images -->
<img srcset="hero-400.webp 400w, hero-800.webp 800w, hero-1200.webp 1200w"
     sizes="(max-width: 600px) 400px, (max-width: 1000px) 800px, 1200px"
     src="hero-1200.webp">
```

```
FIX 4: Preload critical resources

<head>
    <!-- Tell browser to start downloading these immediately -->
    <link rel="preload" href="/fonts/inter.woff2" as="font" crossorigin>
    <link rel="preload" href="/api/user" as="fetch" crossorigin>
    <!-- Browser starts downloading WHILE parsing HTML, not after JS runs -->
</head>
```

## Quick Wins Checklist

```
□ Defer all non-critical JavaScript
□ Code-split: only load JS needed for current page
□ Compress images (WebP format, appropriate dimensions)
□ Lazy-load below-fold images
□ Preload critical fonts and API calls
□ Enable gzip/brotli compression on server
□ Remove unused CSS (PurgeCSS)
□ Minimize third-party scripts (each one adds 100-500ms)
□ Use a CDN for static assets
□ Set long cache headers for static resources
```'''
    ),
    (
        "thinking/analogy-message-queue-to-post-office-mailbox",
        "What's the difference between a message queue and directly calling an API? When should I use a queue instead of a direct HTTP call?",
        r'''<think>
Message queue vs direct API call — the post office vs phone call analogy.

**Phone call (HTTP API call):**
- Synchronous: you call, they pick up, you talk, you hang up
- You WAIT for the answer
- If they don't pick up, you know immediately (error)
- Both parties must be available at the same time

**Post office mailbox (message queue):**
- Asynchronous: you drop the letter in the mailbox, walk away
- You DON'T wait for a response
- If the recipient is on vacation, the letter waits in their mailbox
- Sender and receiver don't need to be available at the same time

This maps perfectly to the technical trade-offs.
</think>

Think of it as **phone call vs mailbox**: one is real-time, the other is drop-and-go.

## The Analogy

```
HTTP API CALL = PHONE CALL:
  You call Bob: "Process this order"
  Bob picks up: "Sure, done. Order #42 confirmed."
  You hang up with the answer.

  ✓ Immediate response (you KNOW it worked)
  ✗ Both must be available (if Bob is busy → you wait or fail)
  ✗ If Bob's phone is off → call fails

MESSAGE QUEUE = MAILBOX:
  You drop a letter in Bob's mailbox: "Process this order"
  You walk away immediately. You don't wait.
  Bob checks his mailbox when he's ready.
  Bob processes the order. Maybe sends a letter back later.

  ✓ You don't wait (instant for you)
  ✓ Bob can be on vacation (letter waits in mailbox)
  ✓ If 1000 letters arrive, Bob processes them at his own pace
  ✗ You don't know if it worked until later
```

## When to Use Each

```
USE HTTP (phone call) WHEN:
  You need the answer NOW to continue.

  "Show me this user's profile" → need data to render the page
  "Is this credit card valid?" → need to know before confirming order
  "Create this record and give me the ID" → need ID for next step

USE MESSAGE QUEUE (mailbox) WHEN:
  You DON'T need the answer to continue.

  "Send a welcome email" → user doesn't wait for email delivery
  "Generate a PDF report" → user can download it later
  "Update search index" → can be seconds behind
  "Process this payment" → confirm order, process payment async
  "Sync data to analytics" → analytics can be delayed
```

## Side-by-Side Example

```python
# SYNCHRONOUS (HTTP): user waits for everything
@app.post("/orders")
def create_order(data):
    order = db.create_order(data)           # 50ms
    payment = payment_api.charge(data)       # 500ms ← user waits
    email_api.send_confirmation(order)       # 200ms ← user waits
    analytics_api.track("order_created")     # 100ms ← user waits
    search_api.index_order(order)            # 150ms ← user waits
    return {"order_id": order.id}
    # Total: 1000ms — user waited for everything

# ASYNCHRONOUS (queue): user gets response fast, rest happens in background
@app.post("/orders")
def create_order(data):
    order = db.create_order(data)           # 50ms
    payment = payment_api.charge(data)       # 500ms (must be sync — need to know if it worked)

    # These don't need to block the user:
    queue.publish("order.created", {"order_id": order.id})  # 5ms
    return {"order_id": order.id}
    # Total: 555ms — user gets response 2x faster

# Consumers process in the background:
@queue.subscribe("order.created")
def handle_order_created(event):
    order = db.get_order(event["order_id"])
    email_service.send_confirmation(order)     # Takes 200ms, but user doesn't wait
    analytics.track("order_created", order)    # Takes 100ms, user doesn't wait
    search.index_order(order)                  # Takes 150ms, user doesn't wait
```

## Key Differences

```
                    HTTP (phone call)    Queue (mailbox)
─────────────────────────────────────────────────────────
Response            Immediate            None / later
Both must be up     Yes                  No (messages wait)
Failure handling    Caller sees error    Message retried later
Ordering            One at a time        Processed at consumer's pace
Scaling             Caller slows if      Queue buffers the overflow
                    server is slow
Debugging           Request → Response   Message published → consumed
                    (clear flow)         (harder to trace)
Complexity          Low                  Medium (queue infrastructure)
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
