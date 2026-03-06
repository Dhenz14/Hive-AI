"""Phase 2: Advanced Reasoning — Mixed Subcategories (Part 30 — Final)"""

PAIRS = [
    (
        "thinking/causal-database-deadlock",
        "Our app occasionally throws 'deadlock detected' errors from PostgreSQL. It happens maybe once a day, always during high traffic. What causes deadlocks and how do I fix them?",
        r'''<think>
Database deadlocks — two transactions each hold a lock that the other needs.

**What a deadlock is:**
Transaction A: locks row 1, then tries to lock row 2
Transaction B: locks row 2, then tries to lock row 1
→ A waits for B's lock on row 2
→ B waits for A's lock on row 1
→ Neither can proceed → PostgreSQL detects this → kills one transaction

**Why it happens during high traffic:**
More concurrent transactions → more chance of two transactions locking the same rows in different order.

**Fixes:**
1. Always lock rows in the SAME ORDER (e.g., by ID ascending)
2. Keep transactions short (less time holding locks)
3. Use SELECT ... FOR UPDATE with NOWAIT or SKIP LOCKED
4. Retry the failed transaction (deadlocks are expected in concurrent systems)
</think>

A deadlock is two transactions waiting for each other — neither can proceed, so PostgreSQL kills one.

## What Happens

```
TRANSACTION A:                    TRANSACTION B:
UPDATE accounts SET               UPDATE accounts SET
  balance = balance - 100           balance = balance - 50
  WHERE id = 1;                     WHERE id = 2;
-- Locks row 1 ✓                  -- Locks row 2 ✓

UPDATE accounts SET               UPDATE accounts SET
  balance = balance + 100           balance = balance + 50
  WHERE id = 2;                     WHERE id = 1;
-- Wants lock on row 2...         -- Wants lock on row 1...
-- But B holds it → WAIT          -- But A holds it → WAIT

→ A waits for B. B waits for A.
→ DEADLOCK! PostgreSQL kills one transaction.
```

## Fix 1: Consistent Lock Ordering

```python
# ❌ DEADLOCK-PRONE: lock order depends on who sends/receives
def transfer(from_id, to_id, amount):
    with db.transaction():
        db.execute("UPDATE accounts SET balance = balance - %s WHERE id = %s", amount, from_id)
        db.execute("UPDATE accounts SET balance = balance + %s WHERE id = %s", amount, to_id)
# transfer(1, 2, 100) locks row 1 then row 2
# transfer(2, 1, 50) locks row 2 then row 1 → DEADLOCK

# ✅ FIXED: always lock in the same order (lower ID first)
def transfer(from_id, to_id, amount):
    first, second = sorted([from_id, to_id])
    with db.transaction():
        # Always lock lower ID first, regardless of transfer direction
        db.execute("SELECT * FROM accounts WHERE id IN (%s, %s) ORDER BY id FOR UPDATE",
                   first, second)
        db.execute("UPDATE accounts SET balance = balance - %s WHERE id = %s", amount, from_id)
        db.execute("UPDATE accounts SET balance = balance + %s WHERE id = %s", amount, to_id)
# Now both transfer(1,2) and transfer(2,1) lock row 1 first → no deadlock
```

## Fix 2: Keep Transactions Short

```python
# ❌ DEADLOCK-PRONE: long transaction holds locks
def process_order(order):
    with db.transaction():
        update_inventory(order)       # Locks inventory rows
        charge_payment(order)         # Network call to Stripe (2-5 seconds!)
        update_order_status(order)    # Locks order row
        send_confirmation(order)      # Network call to email service
    # Locks held for 5+ seconds → high chance of deadlock

# ✅ FIXED: minimize time in transaction
def process_order(order):
    # Step 1: quick database transaction (locks held < 50ms)
    with db.transaction():
        update_inventory(order)
        update_order_status(order)

    # Step 2: external calls OUTSIDE the transaction (no locks held)
    charge_payment(order)
    send_confirmation(order)
```

## Fix 3: Retry on Deadlock

```python
# Deadlocks in concurrent systems are EXPECTED — handle them gracefully
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential
from psycopg2.errors import DeadlockDetected

@retry(
    retry=retry_if_exception_type(DeadlockDetected),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.1, max=2),
)
def transfer(from_id, to_id, amount):
    with db.transaction():
        # If deadlock detected, transaction is rolled back automatically
        # Tenacity retries it → succeeds on the next attempt
        ...
```

**Deadlocks are normal in concurrent systems.** Fix them by: consistent lock ordering, short transactions, and automatic retry.'''
    ),
    (
        "thinking/analogy-dns-phonebook",
        "How does DNS work? When I type google.com in my browser, how does it know which server to connect to?",
        r'''<think>
DNS explained via the phone book analogy — DNS is literally the internet's phone book.

You know the name (google.com) but need the number (IP address) to make the call (connect).

The DNS resolution process:
1. Check local cache (your phone's contacts)
2. Ask recursive resolver (call 411/directory assistance)
3. Resolver asks root server → TLD server → authoritative server
4. Get the IP address back
5. Connect to that IP
</think>

DNS is the internet's **phone book** — it translates names you remember (google.com) into numbers computers need (142.250.80.46).

## The Analogy

```
PHONE BOOK:
  You want to call "Pizza Palace"
  → You don't know their phone number
  → Look up "Pizza Palace" in the phone book
  → Find: 555-0123
  → Dial 555-0123 → connected!

DNS:
  You want to visit "google.com"
  → Your computer doesn't know google.com's IP address
  → Ask DNS: "What's the IP for google.com?"
  → DNS says: 142.250.80.46
  → Browser connects to 142.250.80.46 → Google loads!
```

## How the Lookup Works

```
YOU TYPE: google.com

STEP 1: CHECK YOUR CACHE (your phone's contacts)
  Browser: "Do I already know google.com's IP?"
  → Found in cache: 142.250.80.46 (visited recently)
  → DONE! Skip everything else.

STEP 2: ASK YOUR DNS RESOLVER (call directory assistance)
  If not cached, ask your ISP's DNS server (or 8.8.8.8 / 1.1.1.1)
  "What's the IP for google.com?"

STEP 3: RESOLVER ASKS THE HIERARCHY (directory assistance chain)
  Resolver → Root server: "Who handles .com?"
  Root: "Ask the .com TLD server at 192.5.6.30"

  Resolver → .com TLD server: "Who handles google.com?"
  TLD: "Ask Google's nameserver at 216.239.32.10"

  Resolver → Google's nameserver: "What's the IP for google.com?"
  Google: "142.250.80.46"

STEP 4: ANSWER RETURNED
  Resolver → Your computer: "google.com is 142.250.80.46"
  Your computer caches this for next time (TTL: e.g., 5 minutes)
  Browser connects to 142.250.80.46

TOTAL TIME: ~20-50ms (first time), ~0ms (cached)
```

```
THE HIERARCHY (like a library system):

  ROOT SERVERS (13 sets worldwide)
  "Which bookshelf has .com books?"
       │
  TLD SERVERS (.com, .org, .net, .io)
  "Which section has google.com?"
       │
  AUTHORITATIVE SERVERS (google's own DNS)
  "google.com is at 142.250.80.46"
```

## Why This Matters for Developers

```python
# DNS is why you can change servers without users noticing

# BEFORE: your app runs on server 1.2.3.4
# DNS record: myapp.com → 1.2.3.4

# You migrate to a new server: 5.6.7.8
# Update DNS: myapp.com → 5.6.7.8
# Users still type myapp.com → DNS gives them the new IP
# No URL changes, no bookmarks broken

# DNS is also why:
# - You can have multiple servers behind one domain (load balancing)
# - You can have subdomains (api.myapp.com, blog.myapp.com)
# - You can point your domain to any hosting provider
# - Email routing works (MX records: "mail for myapp.com goes to this server")
```

DNS is invisible infrastructure you use hundreds of times a day without knowing it. Every URL you visit starts with a DNS lookup.'''
    ),
    (
        "thinking/adversarial-insecure-direct-object-reference",
        "My API lets users access their orders by ID: GET /api/orders/123. A penetration tester says this has an IDOR vulnerability. What does that mean?",
        r'''<think>
IDOR (Insecure Direct Object Reference) — one of the OWASP Top 10 and one of the most common API vulnerabilities.

**The vulnerability:**
If the API uses the ID directly to fetch data without checking if the requesting user OWNS that order, any user can access any other user's orders by guessing/incrementing IDs.

GET /api/orders/123 → my order ✓
GET /api/orders/124 → someone else's order! ✗
GET /api/orders/125 → another person's order! ✗

**Why it's common:**
Developers often check "is the user authenticated?" but forget to check "does this user have permission to access THIS specific resource?"

**Fixes:**
1. Always filter by user_id (WHERE order_id = ? AND user_id = ?)
2. Use UUIDs instead of sequential IDs (harder to guess, but NOT a security fix)
3. Authorization checks on every access
</think>

**IDOR means any user can access any other user's data** by simply changing the ID in the URL.

## The Attack

```
YOUR API:
  GET /api/orders/123 → authenticated user sees their order ✓

ATTACKER (also authenticated, different user):
  GET /api/orders/123 → sees YOUR order data ✗
  GET /api/orders/124 → sees another user's order ✗
  GET /api/orders/125 → sees another user's order ✗
  ...
  # Script to download ALL orders:
  for id in range(1, 10000):
      response = requests.get(f"/api/orders/{id}",
                              headers={"Authorization": f"Bearer {attacker_token}"})
      if response.status_code == 200:
          save(response.json())  # Names, addresses, purchase history...

WHAT THE ATTACKER GETS:
  - Every customer's order history
  - Shipping addresses (PII)
  - Email addresses
  - Purchase amounts
  - Product preferences
```

## Why It Happens

```python
# ❌ VULNERABLE: checks authentication but NOT authorization
@app.get("/api/orders/{order_id}")
async def get_order(order_id: int, user = Depends(get_current_user)):
    # ✓ User is authenticated (logged in)
    # ✗ But: does this user OWN this order? NOT CHECKED!
    order = await db.query("SELECT * FROM orders WHERE id = %s", order_id)
    if not order:
        raise HTTPException(404)
    return order
    # Any authenticated user can access ANY order by changing the ID

# ✅ FIXED: check that the user OWNS the resource
@app.get("/api/orders/{order_id}")
async def get_order(order_id: int, user = Depends(get_current_user)):
    order = await db.query(
        "SELECT * FROM orders WHERE id = %s AND user_id = %s",
        order_id, user.id  # Filter by user_id!
    )
    if not order:
        raise HTTPException(404)  # Returns 404, not 403 (don't reveal existence)
    return order
```

## Comprehensive Fix

```python
# Apply the same pattern everywhere:

# ❌ VULNERABLE
GET /api/invoices/{id}      → db.get(Invoice, id)
GET /api/documents/{id}     → db.get(Document, id)
PUT /api/profiles/{id}      → db.update(Profile, id, data)
DELETE /api/addresses/{id}  → db.delete(Address, id)

# ✅ FIXED: always scope to current user
GET /api/invoices/{id}      → db.get(Invoice, id, user_id=user.id)
GET /api/documents/{id}     → db.get(Document, id, user_id=user.id)
PUT /api/profiles/{id}      → if id != user.id: raise 403
DELETE /api/addresses/{id}  → db.get(Address, id, user_id=user.id)

# Helper to enforce this:
async def get_owned_resource(model, resource_id, user_id):
    resource = await db.query(
        f"SELECT * FROM {model.__tablename__} WHERE id = %s AND user_id = %s",
        resource_id, user_id
    )
    if not resource:
        raise HTTPException(404)  # 404 not 403 — don't reveal existence
    return resource
```

## Defense in Depth

```
LAYER 1: Authorization check (required)
  "Does this user own this resource?"
  → Filter queries by user_id

LAYER 2: UUIDs instead of sequential IDs (supplementary)
  /api/orders/550e8400-e29b-41d4-a716-446655440000
  → Harder to guess than /api/orders/124
  → NOT a security fix (UUIDs are not secrets)
  → But raises the bar for casual discovery

LAYER 3: Rate limiting on enumeration attempts
  100 rapid GET /api/orders/1, /api/orders/2, /api/orders/3...
  → Rate limit or block this pattern

LAYER 4: Automated testing
  Write tests that verify user A cannot access user B's resources
```

**IDOR is the #1 most common API vulnerability.** Every endpoint that takes a resource ID must verify that the current user has permission to access that specific resource.'''
    ),
    (
        "thinking/backtrack-monolithic-frontend-to-microfrontends",
        "Our React frontend is 2 million lines of code and takes 20 minutes to build. Every team steps on each other's toes. Should we adopt micro-frontends?",
        r'''<think>
2M lines, 20-minute builds, teams stepping on each other — this is a genuine scale problem where micro-frontends might be justified.

But let me think about alternatives first before jumping to micro-frontends (which add significant complexity).

**The actual problems:**
1. 20-minute builds → developer experience issue
2. Teams stepping on each other → code ownership issue
3. Slow to ship → coupling issue

**Possible solutions in order of complexity:**
1. Code splitting + lazy loading (reduce build impact)
2. Module federation (webpack 5) — share modules between independently built apps
3. Monorepo with incremental builds (Nx, Turborepo) — only rebuild what changed
4. Micro-frontends (full separation — each team has its own app)

Micro-frontends are the nuclear option. Try simpler approaches first.

But at 2M lines with multiple teams, option 3 or 4 might genuinely be needed.
</think>

At 2M lines with multiple teams, you have a real problem. But micro-frontends are the **nuclear option** — try simpler solutions first.

## Solutions in Order of Complexity

### Try First: Incremental Builds (Nx / Turborepo)

```
PROBLEM: 20-minute builds because EVERYTHING rebuilds every time
FIX: Only rebuild what CHANGED

Before (monolithic build):
  Change 1 component → rebuild ALL 2M lines → 20 minutes

After (incremental with Nx):
  Change 1 component → Nx detects: only this module changed
  → Rebuild only that module → 30 seconds
  → Other modules use cached builds

# Setup with Nx:
npx create-nx-workspace@latest my-org

# Structure:
apps/
  dashboard/     # Team A's app
  checkout/      # Team B's app
  admin/         # Team C's app
libs/
  shared-ui/     # Shared component library
  auth/          # Shared auth module
  api-client/    # Shared API client

# Nx only rebuilds affected projects:
nx affected:build  # Builds only what changed since last commit
```

### Try Second: Module Federation (Webpack 5)

```
PROBLEM: teams step on each other because it's one codebase
FIX: separate builds that compose at runtime

Each team builds their section independently:
  Team A builds: checkout (standalone React app)
  Team B builds: product catalog (standalone React app)
  Team C builds: user account (standalone React app)

Shell app loads them at runtime:
  shell app (the container) loads each team's build dynamically
  → Teams deploy independently
  → No shared build process
  → Each team has their own repo, CI, deploy cycle

// webpack.config.js (shell app)
new ModuleFederationPlugin({
    remotes: {
        checkout: 'checkout@https://checkout.cdn.com/remoteEntry.js',
        catalog: 'catalog@https://catalog.cdn.com/remoteEntry.js',
        account: 'account@https://account.cdn.com/remoteEntry.js',
    },
});

// Usage in shell app:
const Checkout = React.lazy(() => import('checkout/CheckoutApp'));
const Catalog = React.lazy(() => import('catalog/CatalogApp'));
```

### Last Resort: Full Micro-Frontends

```
WHEN MICRO-FRONTENDS ARE JUSTIFIED:
  □ 5+ teams working on the same frontend
  □ Teams need completely independent deploy cycles
  □ Teams want different tech stacks (React, Vue, Angular)
  □ The other solutions have been tried and aren't sufficient

THE COST OF MICRO-FRONTENDS:
  - Shared state management is complex (how do apps communicate?)
  - Consistent look and feel requires a design system
  - Routing across micro-frontends is tricky
  - Performance overhead (multiple frameworks, duplicate dependencies)
  - Testing across boundaries is harder
  - User experience can suffer (page transitions, loading states)
```

## What to Actually Do

```
STEP 1: Profile the build (find what's slow)
  npx webpack --profile --json > stats.json
  npx webpack-bundle-analyzer stats.json
  → Identify the biggest modules, longest compilation steps

STEP 2: Split into packages/modules (monorepo approach)
  Use Nx or Turborepo for incremental builds
  → 20 min build → 2-3 min build (only changed modules)

STEP 3: Code ownership (CODEOWNERS file)
  # .github/CODEOWNERS
  /src/checkout/**  @checkout-team
  /src/catalog/**   @catalog-team
  /src/account/**   @account-team
  → PRs require team review, reduces stepping on toes

STEP 4: Evaluate if more separation is needed
  If teams STILL conflict after steps 1-3 → Module Federation
  If teams need completely independent stacks → Micro-frontends

MOST TEAMS: steps 1-3 solve the problem.
At 2M lines with many teams: step 4 might be needed.
```'''
    ),
    (
        "thinking/multiperspective-technical-debt-payoff",
        "Our codebase has a lot of technical debt. Management wants new features. Engineering wants to pay down the debt. How do we balance this?",
        r'''<think>
Technical debt vs features — this is one of the most common tensions in software teams.

**Management's perspective:**
- Features = revenue
- Customers don't pay for "cleaner code"
- Competitors are shipping features while we refactor
- "We can fix it later" (which never comes)

**Engineering's perspective:**
- Technical debt slows down EVERY future feature
- The codebase is getting harder to modify
- Bugs increase because the code is hard to understand
- Developer morale drops (nobody wants to work in a mess)
- Eventually we'll be unable to ship features at all

**The synthesis:**
Both are right. You can't stop shipping features, and you can't ignore debt forever. The answer is to embed debt reduction INTO feature work — not as a separate initiative.
</think>

Both sides are right, and neither should "win." The answer is to **embed debt reduction into feature work**, not treat it as a separate initiative.

## Why Both Sides Are Right

```
MANAGEMENT IS RIGHT:
  "We need features to survive"
  - Revenue comes from features, not refactoring
  - Competitors don't wait while you clean up code
  - A clean codebase with no customers = a failed business

ENGINEERING IS RIGHT:
  "Debt makes everything slower"
  - Feature that should take 2 days → takes 2 weeks (working around debt)
  - Bugs increase because the code is fragile
  - New developers take months to be productive
  - Eventually you can't ship features at all

THE REALITY:
  Feature velocity NOW depends on technical debt from THE PAST
  Feature velocity TOMORROW depends on what you do TODAY

  Ignoring debt → short-term speed, long-term paralysis
  Only paying debt → no revenue, company dies
```

## The Practical Balance

```
THE 80/20 APPROACH:
  80% of engineering time: features (the business stays alive)
  20% of engineering time: debt reduction (the business stays healthy)

  Sprint planning:
    8 story points of features + 2 story points of debt reduction
    Every sprint. Non-negotiable. Like exercise.

THE "BOY SCOUT RULE":
  "Leave the code better than you found it"

  Working on a feature in the checkout module?
  → Also clean up the checkout module while you're there
  → Don't ask permission. Don't make it a separate ticket.
  → It's part of doing the feature properly.

  This is the MOST EFFECTIVE debt reduction strategy:
  - No separate "refactoring sprints" (management hates these)
  - No asking permission (it's just good engineering)
  - Debt is reduced WHERE features are being built
  - Over time, the most-modified code gets the cleanest
```

## How to Communicate With Management

```
DON'T SAY:
  "We need to refactor the codebase"
  → Management hears: "We want to do invisible work for months"

DO SAY:
  "The checkout module has 3x more bugs than other modules
   because of accumulated technical debt. Spending 2 sprints
   cleaning it up will reduce checkout bugs by 50% and make
   future checkout features 2x faster to build."

FRAME IT AS:
  - Risk reduction: "This code will cause outages if we don't fix it"
  - Velocity investment: "This will let us ship features 2x faster"
  - Bug prevention: "This is why we have 10 checkout bugs per month"
  - Retention: "Senior engineers are leaving because of code quality"

QUANTIFY IT:
  Before: "We should refactor the auth module"
  After: "Auth changes take 3x longer than equivalent changes in
         other modules. Refactoring will save 40 engineering hours
         per quarter."
```

## The Debt Reduction Strategies

```
STRATEGY 1: THE BOY SCOUT RULE (continuous, no permission needed)
  Every PR leaves the code slightly better
  Small improvements compound over time
  Best for: diffuse, widespread debt

STRATEGY 2: DEDICATED PERCENTAGE (built into sprint planning)
  20% of each sprint for debt reduction
  Team chooses the highest-impact items
  Best for: systematic improvement

STRATEGY 3: TECH DEBT SPIKE (focused burst)
  1-2 week focused effort on one specific area
  Best for: critical debt that blocks multiple features
  Frame as: "Investment sprint" not "refactoring sprint"

STRATEGY 4: OPPORTUNISTIC (piggyback on features)
  "This feature touches the payment module. Let's
   also fix the payment module's test coverage."
  Best for: debt near active feature development

ALL FOUR should be used simultaneously.
```

## How to Prioritize Which Debt to Pay

```
NOT ALL DEBT IS EQUAL:

HIGH PRIORITY (fix now):
  - Debt in code you modify FREQUENTLY
    (you pay the interest every time you touch it)
  - Security vulnerabilities
  - Missing tests for critical paths
  - Flaky CI pipeline (blocks everyone)

LOW PRIORITY (fix when convenient):
  - Debt in code you RARELY modify
    (you're not paying interest if you never touch it)
  - Cosmetic issues (naming, formatting)
  - "Old" patterns that work fine

THE RULE:
  Focus debt reduction where it reduces FUTURE development time.
  Clean code nobody touches = wasted effort.
  Clean code everyone touches every week = high ROI.
```'''
    ),
    (
        "thinking/firstprinciples-why-database-transactions",
        "Why do we need database transactions? Can't I just run my queries one at a time?",
        r'''<think>
Database transactions from first principles.

**What happens without transactions:**
Multiple queries that should be atomic (all or nothing) can partially complete:
1. Deduct money from account A: UPDATE accounts SET balance = balance - 100 WHERE id = 1
2. Power outage / crash / error
3. Add money to account B: never executes
Result: $100 disappeared. Account A lost $100, Account B gained $0.

**What transactions provide (ACID):**
- Atomicity: all or nothing (if step 2 fails, step 1 is rolled back)
- Consistency: database moves from one valid state to another
- Isolation: concurrent transactions don't interfere
- Durability: once committed, data survives crashes

The key insight: transactions exist because THINGS FAIL. Power outages, crashes, bugs, disk errors — any step in a multi-step operation can fail. Transactions ensure the database is never in a partial, inconsistent state.
</think>

Because **things fail in the middle**. Transactions ensure your database is never left in a half-finished, inconsistent state.

## The Problem Without Transactions

```
BANK TRANSFER: move $100 from Alice to Bob

WITHOUT TRANSACTION:
  Query 1: UPDATE accounts SET balance = balance - 100 WHERE name = 'Alice'
  ✓ Alice: $500 → $400

  ... server crashes / power outage / bug / timeout ...

  Query 2: UPDATE accounts SET balance = balance + 100 WHERE name = 'Bob'
  ✗ Never runs

  RESULT:
  Alice: $400 (lost $100)
  Bob: $500 (gained $0)
  $100 has VANISHED from the system.

WITH TRANSACTION:
  BEGIN;
    UPDATE accounts SET balance = balance - 100 WHERE name = 'Alice';
    -- crash happens here --
  ROLLBACK;  -- automatic on crash

  RESULT:
  Alice: $500 (unchanged — entire transaction rolled back)
  Bob: $500 (unchanged)
  Money is safe. No partial update.
```

## What Transactions Guarantee (ACID)

```
ATOMICITY: "All or nothing"
  Either ALL queries in the transaction succeed,
  or NONE of them take effect.
  No partial updates. Ever.

CONSISTENCY: "Valid state to valid state"
  The database moves from one valid state to another.
  Constraints (foreign keys, unique, check) are always satisfied.

ISOLATION: "Concurrent transactions don't interfere"
  Two users transferring money at the same time
  don't see each other's intermediate states.

DURABILITY: "Committed = permanent"
  Once a transaction is committed, the data survives
  even if the server crashes immediately after.
```

## In Code

```python
# ❌ WITHOUT TRANSACTION: partial updates possible
def transfer(from_id, to_id, amount):
    db.execute("UPDATE accounts SET balance = balance - %s WHERE id = %s", amount, from_id)
    # If the next line fails: from_id lost money, to_id didn't gain it
    db.execute("UPDATE accounts SET balance = balance + %s WHERE id = %s", amount, to_id)

# ✅ WITH TRANSACTION: all or nothing
def transfer(from_id, to_id, amount):
    with db.transaction():  # BEGIN
        db.execute("UPDATE accounts SET balance = balance - %s WHERE id = %s", amount, from_id)
        db.execute("UPDATE accounts SET balance = balance + %s WHERE id = %s", amount, to_id)
    # COMMIT (if both succeed) or ROLLBACK (if either fails)

# Another example: creating an order
def create_order(user_id, items):
    with db.transaction():
        order = db.insert("orders", {"user_id": user_id, "status": "pending"})
        for item in items:
            db.insert("order_items", {"order_id": order.id, "product_id": item.id})
            db.execute("UPDATE products SET stock = stock - 1 WHERE id = %s", item.id)
        # If any product is out of stock → exception → ROLLBACK
        # No order created, no stock decremented, nothing changed
```

## When You Need Transactions

```
USE TRANSACTIONS WHEN:
  □ Multiple tables must be updated together (order + order_items + inventory)
  □ Data must be consistent (money transfer: debit + credit)
  □ Failure partway through would leave bad data
  □ You check a value then update based on it (check-then-act)

SINGLE QUERIES DON'T NEED EXPLICIT TRANSACTIONS:
  A single INSERT, UPDATE, or DELETE is already atomic.
  UPDATE users SET name = 'Dan' WHERE id = 42;
  → This either succeeds completely or fails completely.
  → No transaction needed for a single statement.
```

**Transactions exist because the real world is unreliable.** Servers crash, networks fail, disks fill up, bugs happen. Transactions ensure that no matter what fails, your data stays consistent.'''
    ),
    (
        "thinking/uncertainty-when-to-optimize",
        "My app has some slow endpoints (500-800ms response time). Should I optimize them now or wait until we have more users?",
        r'''<think>
When to optimize — depends on several factors.

**Arguments for optimizing now:**
- 500-800ms is noticeable to users (impacts UX)
- Slow code tends to get slower as data grows
- Easier to optimize now than after the codebase grows
- Sets good performance habits

**Arguments for waiting:**
- "Premature optimization is the root of all evil" (Knuth)
- If you have 100 users, nobody notices
- Feature development might be more valuable
- Performance problems often change as the product evolves

**The right framework:**
Don't optimize based on user count. Optimize based on:
1. Is it impacting user experience? (>200ms is noticeable)
2. Is it the bottleneck? (is this what's slowing down development or user satisfaction?)
3. Is the fix easy? (some optimizations are 5-minute fixes)
4. Will it get worse? (O(n²) with growing data → fix now)

500-800ms for an API endpoint IS slow. This is worth investigating but maybe not worth a major refactoring effort.

Confidence: 70% "quick wins now, save big refactors for later"
</think>

**70% confidence: grab the quick wins now, save major refactors for when they're clearly needed.**

## The Framework: Optimize Based on Impact, Not User Count

```
DON'T ASK: "How many users do we have?"
DO ASK:

1. IS IT IMPACTING USER EXPERIENCE?
   < 100ms: feels instant → don't touch it
   100-300ms: acceptable → optimize if easy
   300-1000ms: noticeably slow → investigate now
   > 1000ms: unacceptably slow → fix immediately

   Your 500-800ms endpoints: noticeably slow. Worth investigating.

2. IS THE FIX EASY? (many "slow" endpoints have simple fixes)
   - Missing database index → 5-minute fix, 100x improvement
   - N+1 query problem → 30-minute fix, 10x improvement
   - Missing cache → 1-hour fix, 5x improvement
   - Architecture redesign → weeks of work

   Check for quick wins FIRST. Most performance problems have simple causes.

3. WILL IT GET WORSE?
   O(1): stays the same with more data → can wait
   O(n): grows linearly → fix before data 10x
   O(n²): grows quadratically → fix NOW (100 users OK, 1000 users = 100x slower)
```

## Quick Diagnosis (30 Minutes)

```python
# Step 1: Add timing to identify WHERE time is spent
import time

async def slow_endpoint(request):
    t0 = time.time()

    users = await get_users()          # Query 1
    t1 = time.time()
    print(f"get_users: {(t1-t0)*1000:.0f}ms")

    orders = await get_orders(users)   # Query 2
    t2 = time.time()
    print(f"get_orders: {(t2-t1)*1000:.0f}ms")

    enriched = await enrich(orders)    # External API
    t3 = time.time()
    print(f"enrich: {(t3-t2)*1000:.0f}ms")

    return enriched

# Output:
# get_users: 5ms       ← fine
# get_orders: 450ms    ← THIS IS THE PROBLEM
# enrich: 50ms         ← fine

# Now you know: get_orders is slow. Look at that query.
# Probably missing index or N+1 problem.
```

```sql
-- Step 2: Check the slow query
EXPLAIN ANALYZE SELECT * FROM orders WHERE user_id IN (...);

-- If you see "Seq Scan" → add an index (5-minute fix)
CREATE INDEX idx_orders_user_id ON orders(user_id);
-- 450ms → 5ms. Done.
```

## The Decision Matrix

```
                    EASY FIX           HARD FIX
SLOW NOW (>500ms):  DO IT NOW ✓        PLAN IT (schedule for next sprint)

FAST NOW (<200ms):  DO IT IF FREE      DON'T (premature optimization)

WILL GET WORSE:     DO IT NOW ✓        PLAN IT (before it becomes critical)

EXAMPLES:
  Missing index + slow query → EASY + SLOW → fix now (5 min)
  N+1 query + 500ms → EASY + SLOW → fix now (30 min)
  Architecture redesign → HARD + SLOW → plan for next sprint
  "This loop is O(n²) but n=10" → HARD + FAST → wait until n grows
```

**Start with profiling. Most 500-800ms endpoints have a simple root cause (missing index, N+1 query, unnecessary API call) that can be fixed in under an hour.**'''
    ),
    (
        "thinking/analogy-ci-cd-assembly-line",
        "Why is CI/CD compared to an assembly line? I want to understand the concept intuitively.",
        r'''<think>
CI/CD as an assembly line — this is a great analogy for understanding why automation matters.

The assembly line revolutionized manufacturing in the same way CI/CD revolutionized software:
- Before assembly lines: each car built by hand, one at a time, quality varies
- After assembly lines: standardized process, consistent quality, fast output

Similarly:
- Before CI/CD: each deploy manual, risky, quality varies
- After CI/CD: standardized pipeline, consistent quality, fast deploys
</think>

The assembly line analogy shows why CI/CD is a **fundamental improvement**, not just automation.

## The Analogy

```
BEFORE ASSEMBLY LINES (1900):
  One craftsman builds an entire car from scratch
  → Quality depends on the individual craftsman
  → Takes weeks per car
  → Mistakes discovered at the end (after everything is assembled)
  → One car at a time
  → Expensive, slow, inconsistent

BEFORE CI/CD:
  One developer builds, tests, and deploys manually
  → Quality depends on the individual developer
  → Deploys take hours and are stressful
  → Bugs discovered in production (after deployment)
  → One deploy at a time (batch up changes)
  → Risky, slow, inconsistent

ASSEMBLY LINE (Ford, 1913):
  Car moves through STATIONS, each doing ONE thing:
  Station 1: Install engine       → quality check
  Station 2: Attach wheels        → quality check
  Station 3: Wire electronics     → quality check
  Station 4: Paint               → quality check
  Station 5: Final inspection    → passes? → ship to dealer

  → Consistent quality (same process every time)
  → Fast (many cars built simultaneously)
  → Defects caught EARLY (at the station, not at the end)
  → Anyone can operate a station (standardized)

CI/CD PIPELINE:
  Code moves through STAGES, each doing ONE thing:
  Stage 1: Lint code              → passes? → continue
  Stage 2: Run unit tests         → passes? → continue
  Stage 3: Build the application  → passes? → continue
  Stage 4: Run integration tests  → passes? → continue
  Stage 5: Deploy to staging      → passes? → continue
  Stage 6: Deploy to production   → health check → done

  → Consistent quality (same checks every time)
  → Fast (automated, runs in minutes)
  → Defects caught EARLY (at the failing stage, not in production)
  → Anyone can deploy (push code, pipeline handles the rest)
```

## Why the Assembly Line Model Works

```
KEY PRINCIPLE: DEFECTS ARE CHEAPEST TO FIX EARLY

  ASSEMBLY LINE:
    Defective engine found at Station 1 → replace engine ($500)
    Defective engine found at final inspection → disassemble car ($5,000)
    Defective engine found by customer → recall ($50,000)

  CI/CD:
    Bug caught by linter (Stage 1) → fix in 1 minute
    Bug caught by unit test (Stage 2) → fix in 10 minutes
    Bug caught in staging (Stage 5) → fix in 1 hour
    Bug found in production (no CI/CD) → 1 day to debug + fix + deploy + verify

  Each stage catches problems BEFORE they flow downstream.
  The earlier you catch a defect, the cheaper it is to fix.
```

## The Pipeline in Practice

```yaml
# Your CI/CD "assembly line" — each stage is a quality gate

name: Deploy Pipeline

on:
  push:
    branches: [main]

jobs:
  # Station 1: Code quality
  lint:
    runs-on: ubuntu-latest
    steps:
      - run: npm run lint        # Catches style issues, unused vars

  # Station 2: Unit tests
  test:
    needs: lint                  # Only runs if lint passes
    runs-on: ubuntu-latest
    steps:
      - run: npm test            # Catches logic bugs

  # Station 3: Build
  build:
    needs: test                  # Only runs if tests pass
    runs-on: ubuntu-latest
    steps:
      - run: npm run build       # Catches build errors

  # Station 4: Integration tests
  integration:
    needs: build
    runs-on: ubuntu-latest
    steps:
      - run: npm run test:e2e    # Catches integration issues

  # Station 5: Deploy
  deploy:
    needs: integration
    runs-on: ubuntu-latest
    steps:
      - run: deploy.sh           # Only deploys if EVERYTHING passes
      - run: curl https://app.com/health  # Final quality check

# If ANY station fails → pipeline stops → bug never reaches production
```

Like an assembly line, each stage has one job, catches one type of defect, and only passes good work to the next stage. The result: consistent quality, fast output, and defects caught early.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
