"""
Real-world project help training pairs - Codebase onboarding and understanding
"""

pairs = [
    {
        "instruction": r'''I just joined a team working on a Django project with about 200 files. There's no documentation. How do I quickly get an overview of the architecture -- which apps exist, how data flows, and where the important business logic lives?''',
        "output": r'''<think>
New dev, no docs, need to understand a Django project fast. I'll give them a systematic exploration approach that works for any Django codebase.
</think>

Here's a systematic approach that works in about 2 hours:

1. Start with the project structure:

```bash
# See all Django apps
find . -name "apps.py" -exec dirname {} \;

# Or look at INSTALLED_APPS
grep -A 30 "INSTALLED_APPS" */settings*.py
```

This tells you the domain boundaries -- each app should roughly correspond to a domain concept (users, orders, billing, etc).

2. Read the URL configuration to understand the API surface:

```bash
# Find the root URL conf
grep "ROOT_URLCONF" */settings*.py

# Then read it
cat config/urls.py

# Find all URL files
find . -name "urls.py" | xargs grep "path\|url(" | head -50
```

URLs tell you what the app actually DOES from a user perspective.

3. Read the models -- this is the single most important step:

```bash
# List all model classes
grep -rn "class.*models.Model" --include="*.py" | grep -v migration

# Read the most important ones (look for ForeignKey to understand relationships)
grep -rn "ForeignKey\|OneToOne\|ManyToMany" --include="models.py"
```

Sketch the entity relationships on paper. In a typical Django app:
- User -> Profile (OneToOne)
- User -> Order (ForeignKey)
- Order -> OrderItem -> Product

4. Find where the business logic lives:

```bash
# Check for service layers
find . -name "services.py" -o -name "utils.py" -o -name "helpers.py"

# If those don't exist, the logic is probably in views.py
wc -l */views.py  # longest files = most business logic
```

5. Check the management commands -- these reveal background processes:

```bash
find . -path "*/management/commands/*.py" | grep -v __
```

6. Look at middleware and signals for hidden behavior:

```bash
grep -r "MIDDLEWARE" */settings*.py
find . -name "signals.py"
```

Signals are particularly important -- they cause side effects that aren't obvious from reading views.

7. Read the test files for the most critical app. Tests (if they exist) are the best documentation of expected behavior:

```bash
wc -l */tests*.py | sort -n | tail -5  # most-tested = most critical
```

Create your own notes as you go. Even a simple text file like:

```
APPS:
- accounts: user registration, auth, profiles
- orders: order creation, payment, fulfillment
- inventory: product catalog, stock management

KEY FLOWS:
- Checkout: orders/views.py:create_order -> orders/services.py:process_payment -> ...
- User signup: accounts/views.py:register -> signals.py:create_profile
```

This becomes the documentation the project never had.'''
    },
    {
        "instruction": r'''I'm trying to understand a complex function I found in our codebase. It's a 150-line Python function called `reconcile_transactions` that processes bank data. It has no comments and the variable names are mostly single letters. I need to understand it well enough to modify it. How do I approach this?''',
        "output": r'''Work through it methodically. Don't try to understand the whole thing at once.

Step 1: Understand inputs and outputs first. Look at the function signature and return statement:

```python
def reconcile_transactions(t, b, w, threshold=0.01):
    # ... 150 lines ...
    return r, u, d
```

Find where this function is called:

```bash
grep -rn "reconcile_transactions" --include="*.py"
```

The call site tells you what the arguments actually are:

```python
# Somewhere in the codebase:
results, unmatched, discrepancies = reconcile_transactions(
    our_transactions, bank_records, lookback_window
)
```

Now you know: t = our transactions, b = bank records, w = lookback window.

Step 2: Add temporary annotations. Don't modify the function yet -- add comments to YOUR copy:

```python
def reconcile_transactions(t, b, w, threshold=0.01):
    # t = list of our Transaction objects
    # b = list of bank records (dicts)
    # w = lookback window in days
    # threshold = matching tolerance for amounts

    r = []   # matched results
    u = []   # unmatched transactions
    d = []   # discrepancies (partial matches)

    # Build lookup of bank records by date
    bl = {}
    for x in b:
        k = x['date'].strftime('%Y-%m-%d')
        if k not in bl:
            bl[k] = []
        bl[k].append(x)
    # bl = bank records grouped by date string
```

Step 3: Identify the algorithm's structure. Most long functions follow a pattern:

```
Lines 1-20:    Setup / data preparation
Lines 21-80:   Main processing loop
Lines 81-120:  Edge case handling
Lines 121-150: Cleanup and return
```

Draw boxes around these sections. Label each one with what it does.

Step 4: Write characterization tests BEFORE modifying anything:

```python
def test_reconcile_exact_match():
    our_txns = [{"id": 1, "amount": 100.00, "date": date(2024, 1, 15)}]
    bank = [{"ref": "A1", "amount": 100.00, "date": date(2024, 1, 15)}]
    matched, unmatched, disc = reconcile_transactions(our_txns, bank, 7)
    assert len(matched) == 1
    assert len(unmatched) == 0

def test_reconcile_no_match():
    our_txns = [{"id": 1, "amount": 100.00, "date": date(2024, 1, 15)}]
    bank = []
    matched, unmatched, disc = reconcile_transactions(our_txns, bank, 7)
    assert len(unmatched) == 1
```

These tests lock in current behavior so you'll know if your changes break something.

Step 5: Now you can safely rename variables and add real comments. Do this in a separate commit before making your actual changes, so the rename commit is easy to review and revert if needed.'''
    },
    {
        "instruction": r'''I need to explain our microservices architecture to a new team member. We have 8 services that communicate via REST and RabbitMQ. I know the system well but I'm not sure how to present it clearly. What's a good framework for explaining it?''',
        "output": r'''Use a top-down approach: big picture first, then zoom into each service, then show how they connect.

Layer 1 -- The one-sentence summary:

"We have 8 services: the API gateway handles all external requests, 4 domain services own specific business data, 2 infrastructure services handle cross-cutting concerns, and 1 async worker processes background jobs."

Layer 2 -- The service map. Draw or describe this:

```
External clients
      |
  [API Gateway] -- auth, routing, rate limiting
      |
  +---+---+---+
  |   |   |   |
[Users] [Orders] [Products] [Payments]
  |        |          |          |
  +--------+----------+----------+
                 |
            [RabbitMQ]
                 |
         [Notification Worker]

Infrastructure:
  [Auth Service] -- JWT validation, used by all services
  [File Service] -- S3 uploads, image processing
```

Layer 3 -- Each service in one paragraph. For each service, cover:
- What data it owns (its database tables)
- What it exposes (API endpoints)
- What it consumes (which other services it calls)
- What events it publishes/subscribes to

Example:

```
Orders Service:
  Owns: orders, order_items, shipping_addresses tables
  Exposes: POST /orders, GET /orders/{id}, PATCH /orders/{id}/status
  Calls: Products (to check stock), Payments (to charge), Users (to get address)
  Publishes: order.created, order.shipped, order.cancelled
  Subscribes: payment.completed, payment.failed
```

Layer 4 -- Walk through 2-3 key flows end-to-end:

```
Checkout Flow:
1. Client -> API Gateway -> Orders: POST /orders
2. Orders -> Products: check inventory (REST)
3. Orders -> Payments: charge card (REST)
4. Payments publishes payment.completed to RabbitMQ
5. Orders subscribes, updates order status to "confirmed"
6. Notification Worker subscribes, sends confirmation email
```

Layer 5 -- Practical stuff for the new dev:
- Where each service repo lives
- How to run everything locally (docker-compose?)
- Where logs go (centralized logging?)
- How to deploy a single service
- Which service to start reading first (usually the API gateway)

Give them this document plus a 30-minute whiteboard session walking through the checkout flow. That gets someone productive within a few days.'''
    },
    {
        "instruction": r'''I'm onboarding onto a React/TypeScript frontend with about 300 components. It uses Redux and has a custom design system. I need to start contributing quickly. What should I focus on first to be productive?''',
        "output": r'''<think>
Large React codebase, need to be productive fast. The key is not understanding everything but understanding just enough to make changes safely. Focus on: project structure, state management patterns, component patterns, and the build/dev workflow.
</think>

Focus on these things in this order:

1. Get the dev environment running (30 min). Read the README, run the app, and make sure hot reload works. Fix any setup issues NOW while you have patience.

2. Learn the file structure conventions (15 min):

```bash
# Common patterns -- figure out which one your project uses:
ls src/
# Option A: feature-based
#   src/features/orders/  (components, hooks, slice all together)
# Option B: type-based
#   src/components/  src/hooks/  src/store/  src/pages/
```

```bash
# Find the main routing file
grep -rn "Route\|createBrowser" src/ --include="*.tsx" -l
```

The routing file is your map -- it shows every page and which component renders it.

3. Understand the Redux structure (30 min). Don't read all the reducers -- just understand the pattern:

```bash
# Find all Redux slices or reducers
find src -name "*slice*" -o -name "*reducer*" | head -20

# Find the store configuration
find src -name "store.*" | head -5
```

Read ONE slice thoroughly. Understand:
- How state is shaped
- How actions are dispatched
- Whether they use Redux Toolkit (createSlice) or old-style reducers
- How async actions work (thunks? sagas? RTK Query?)

4. Study the design system (20 min):

```bash
# Find the component library
find src -path "*/design-system/*" -o -path "*/ui/*" -o -path "*/common/*" | head -20
```

Open Storybook if they have it (`npm run storybook`). If not, find the Button, Input, and Modal components -- these show the API patterns all components follow.

5. Read one complete feature top to bottom (1 hour). Pick a simple page -- something like a settings page or a list view. Trace the full path:

```
Page component -> reads from Redux store
               -> dispatches actions
               -> actions call API
               -> API response updates store
               -> component re-renders
```

6. Make your first change. Pick the smallest possible ticket. Something like "change button text" or "add a field to a form." This forces you to learn the PR process, linting rules, and test expectations.

Practical tips:
- Install React DevTools and Redux DevTools browser extensions
- Use your IDE's "Go to Definition" aggressively -- cmd+click every import
- Search for existing patterns before writing new code: `grep -rn "useSelector" src/ | head` shows how others read from the store
- Don't refactor anything for the first 2 weeks -- learn the existing patterns first'''
    },
    {
        "instruction": r'''I inherited a Python project that uses a custom ORM/query builder instead of SQLAlchemy. It's a homegrown library in a lib/ directory. I can't find docs for it. How do I figure out how it works so I can write queries?''',
        "output": r'''Read the code in layers: API surface first, then internals.

Step 1: Find the entry point -- how do other files use this library?

```bash
# Find imports from the lib
grep -rn "from lib" --include="*.py" | grep -v __pycache__ | head -20
grep -rn "import.*lib" --include="*.py" | grep -v __pycache__ | head -20
```

You'll see patterns like:

```python
from lib.db import Query, connect
from lib.models import User, Order
```

Step 2: Find real usage examples in the codebase -- this IS your documentation:

```bash
grep -rn "Query\|\.where\|\.select\|\.insert" --include="*.py" | grep -v "lib/" | head -30
```

Collect these examples:

```python
# Found in views.py:42
users = Query("users").where(active=True).order_by("-created_at").limit(10).all()

# Found in services.py:88
user = Query("users").where(id=user_id).first()

# Found in reports.py:15
totals = Query("orders").select("category", "SUM(amount) as total").group_by("category").all()

# Found in api.py:33
Query("users").insert(name=name, email=email)
```

Now you know the API: Query(table).where().order_by().limit().all/first().

Step 3: Read the Query class itself to understand edge cases:

```bash
# Find the main class
grep -n "class Query" lib/*.py
```

Look specifically for:
- What does `.all()` return? Dicts? Named tuples? Objects?
- How does `.where()` handle different operators (>, <, IN, LIKE)?
- Does it do parameter escaping (SQL injection safety)?
- How are transactions handled?

```bash
grep -n "def where\|def all\|def first\|def insert\|def update\|def delete" lib/db.py
```

Step 4: Check for operator syntax in where clauses:

```bash
# Search for non-equality filters
grep -rn "\.where(" --include="*.py" | grep -v "lib/" | grep -E "__|>|<|in|like"
```

You might find patterns like:

```python
# Django-style double underscore
Query("orders").where(amount__gt=100)
Query("users").where(name__like="%john%")
Query("orders").where(status__in=["pending", "processing"])
```

Step 5: Write a small test script to verify your understanding:

```python
# test_query.py -- run this against a dev database
from lib.db import Query, connect

connect("dev_db_url")

# Test basic select
users = Query("users").limit(3).all()
print(type(users), type(users[0]))  # list of dicts? objects?
print(users[0])

# Test where
user = Query("users").where(id=1).first()
print(type(user), user)
```

10 minutes of interactive testing tells you more than an hour of reading source code. After this you'll be able to write queries confidently.'''
    },
]
