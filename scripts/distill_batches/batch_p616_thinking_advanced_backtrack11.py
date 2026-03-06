"""Phase 2A: Advanced Reasoning — Backtracking & Dead-End Recovery (Part 11)"""

PAIRS = [
    (
        "thinking/backtrack-callback-hell-to-async-await",
        "Our Node.js codebase has deeply nested callbacks (5-6 levels deep). I tried converting to Promises but the code is still messy with .then() chains everywhere. How do I clean this up?",
        r'''<think>
Callback hell → Promises → async/await. Classic migration path where the first attempt (Promises with .then) is better but not the final answer.

**Current state: callback hell**
```javascript
getUser(userId, (err, user) => {
  if (err) { handleError(err); return; }
  getOrders(user.id, (err, orders) => {
    if (err) { handleError(err); return; }
    getPayments(orders[0].id, (err, payments) => {
      // 5-6 levels deep...
    });
  });
});
```

**First attempt: Promise chains**
```javascript
getUser(userId)
  .then(user => getOrders(user.id))
  .then(orders => getPayments(orders[0].id))
  .then(payments => ...)
  .catch(handleError);
```

Better — flat chain, one error handler. But problems:
1. Can't easily access intermediate values (need `user` later in the chain)
2. Conditional logic breaks the chain (if no orders, do X, else do Y)
3. Parallel operations need Promise.all with awkward destructuring
4. Still reads bottom-to-top in complex cases

**Let me backtrack from .then() chains to async/await**

Async/await is syntactic sugar over Promises but reads like synchronous code:
```javascript
async function processUser(userId) {
  const user = await getUser(userId);
  const orders = await getOrders(user.id);
  const payments = await getPayments(orders[0].id);
  // All intermediate variables accessible
  // Error handling with try/catch (familiar pattern)
}
```

This is the right answer. Let me also address common pitfalls in the migration.
</think>

Your Promise `.then()` chains are step one — but **async/await** is where you want to land. Let me show the progression and why each step wasn't enough.

## The Progression

```javascript
// LEVEL 1: Callback hell (where you started)
getUser(userId, (err, user) => {
    if (err) return handleError(err);
    getOrders(user.id, (err, orders) => {
        if (err) return handleError(err);
        getPayments(orders[0].id, (err, payments) => {
            if (err) return handleError(err);
            calculateTotal(payments, (err, total) => {
                if (err) return handleError(err);
                sendReceipt(user.email, total, (err) => {
                    if (err) return handleError(err);
                    console.log('Done!');
                });
            });
        });
    });
});


// LEVEL 2: Promise .then() chains (your current attempt)
getUser(userId)
    .then(user => getOrders(user.id))     // Lost access to `user` here
    .then(orders => getPayments(orders[0].id))
    .then(payments => calculateTotal(payments))
    .then(total => sendReceipt(???, total))  // Need `user.email` but lost it!
    .catch(handleError);

// Problem: you need `user` at the end but only had it at the start.
// Workaround: nested .then() — right back to nesting!


// LEVEL 3: async/await (the solution)
async function processUser(userId) {
    const user = await getUser(userId);
    const orders = await getOrders(user.id);
    const payments = await getPayments(orders[0].id);
    const total = await calculateTotal(payments);
    await sendReceipt(user.email, total);  // user is still in scope!
    console.log('Done!');
}

// Reads like synchronous code.
// All variables accessible.
// Error handling with try/catch.
```

## Migration Pattern: Callback → Promise → Async/Await

```javascript
// Step 1: Wrap callback functions in Promises (if no Promise version exists)
function getUserAsync(userId) {
    return new Promise((resolve, reject) => {
        getUser(userId, (err, user) => {
            if (err) reject(err);
            else resolve(user);
        });
    });
}

// Or use Node.js built-in:
const { promisify } = require('util');
const getUserAsync = promisify(getUser);
const getOrdersAsync = promisify(getOrders);

// Step 2: Use async/await with the promisified functions
async function processUser(userId) {
    try {
        const user = await getUserAsync(userId);
        const orders = await getOrdersAsync(user.id);
        // ...clean, flat, readable
    } catch (err) {
        handleError(err);
    }
}
```

## Common Pitfalls When Migrating

```javascript
// ❌ PITFALL 1: Sequential awaits when parallel is possible
async function getDashboard(userId) {
    const user = await getUser(userId);        // 100ms
    const orders = await getOrders(userId);    // 100ms
    const notifications = await getNotifs(userId); // 100ms
    // Total: 300ms (sequential) — but these are independent!
}

// ✅ FIX: Promise.all for independent operations
async function getDashboard(userId) {
    const [user, orders, notifications] = await Promise.all([
        getUser(userId),        // 100ms ─┐
        getOrders(userId),      // 100ms ─┤ all run in parallel
        getNotifs(userId),      // 100ms ─┘
    ]);
    // Total: 100ms (parallel)
}


// ❌ PITFALL 2: await inside a loop (N+1 problem)
async function getAllUserOrders(userIds) {
    const results = [];
    for (const id of userIds) {
        results.push(await getOrders(id));  // One at a time! Slow!
    }
    return results;
}

// ✅ FIX: Promise.all with map
async function getAllUserOrders(userIds) {
    return Promise.all(userIds.map(id => getOrders(id)));
    // All requests fire simultaneously
}


// ❌ PITFALL 3: forgetting error handling
async function riskyFunction() {
    const data = await fetchData();  // If this throws, unhandled rejection!
    return process(data);
}

// ✅ FIX: try/catch or let the caller handle it
async function safeFunction() {
    try {
        const data = await fetchData();
        return process(data);
    } catch (err) {
        logger.error('fetchData failed', err);
        return fallbackData();
    }
}
```

## Conditional Logic (Where .then() Chains Really Break)

```javascript
// ❌ Conditional logic in .then() chains = nightmare
getUser(userId)
    .then(user => {
        if (user.isAdmin) {
            return getAdminDashboard(user.id)
                .then(dashboard => ({ user, dashboard }));
        } else {
            return getUserDashboard(user.id)
                .then(dashboard => ({ user, dashboard }));
        }
    })
    .then(({ user, dashboard }) => renderPage(user, dashboard));
// Ugly, nested, hard to follow

// ✅ async/await: conditional logic reads naturally
async function loadDashboard(userId) {
    const user = await getUser(userId);

    const dashboard = user.isAdmin
        ? await getAdminDashboard(user.id)
        : await getUserDashboard(user.id);

    return renderPage(user, dashboard);
}
// Clean. Obvious. Easy to modify.
```'''
    ),
    (
        "thinking/backtrack-global-state-to-dependency-injection",
        "Our Python app uses global variables everywhere for configuration and database connections. It works but testing is impossible because we can't mock anything. How do I fix this?",
        r'''<think>
Global state making testing impossible — classic problem. Let me think through the progression.

**Current state: global variables**
```python
# config.py
DB_URL = os.environ["DATABASE_URL"]
db = create_engine(DB_URL)
redis = Redis(host="redis")
```

```python
# service.py
from config import db, redis

def get_user(user_id):
    return db.execute("SELECT * FROM users WHERE id = %s", user_id)
```

Testing problem: `from config import db` runs at import time, connects to real database. Can't swap in a test database.

**First approach: monkeypatching**
```python
# test_service.py
import service
service.db = mock_db  # Replace at runtime
```

This works but:
- Fragile — import order matters
- Easy to forget to reset
- Doesn't scale to many globals
- Tests affect each other if not properly cleaned up

Let me backtrack from monkeypatching.

**Better approach: dependency injection**
Instead of importing globals, pass dependencies as arguments:
```python
def get_user(db, user_id):
    return db.execute(...)
```

Now testing is trivial:
```python
def test_get_user():
    mock_db = Mock()
    mock_db.execute.return_value = {"id": 1, "name": "Alice"}
    result = get_user(mock_db, 1)
    assert result["name"] == "Alice"
```

But passing db to every function is tedious. Let me think about how to make this practical.

**Practical DI: class-based services or framework DI**
```python
class UserService:
    def __init__(self, db, cache):
        self.db = db
        self.cache = cache

    def get_user(self, user_id):
        return self.db.execute(...)
```

This is the right pattern. Dependencies are explicit, testable, and swappable.
</think>

Global state → monkeypatching (my first thought) → **dependency injection** (the right answer). Let me show the progression.

## The Problem with Global State

```python
# ❌ config.py — runs at import time
import os
from sqlalchemy import create_engine
from redis import Redis

DB_URL = os.environ["DATABASE_URL"]       # Must exist at import!
db = create_engine(DB_URL)                 # Connects to real DB at import!
redis_client = Redis(host="redis")         # Connects to real Redis!

# ❌ service.py — tightly coupled to globals
from config import db, redis_client

def get_user(user_id):
    cached = redis_client.get(f"user:{user_id}")
    if cached:
        return json.loads(cached)
    user = db.execute("SELECT * FROM users WHERE id = %s", (user_id,)).fetchone()
    redis_client.setex(f"user:{user_id}", 300, json.dumps(dict(user)))
    return dict(user)

# ❌ test_service.py — IMPOSSIBLE to test without real DB + Redis
# import service  ← this imports config → connects to real DB → fails in CI
```

## First Attempt: Monkeypatching (Dead End)

```python
# My first thought: just replace the globals at runtime
# ❌ Fragile, order-dependent, easy to forget cleanup

import service
from unittest.mock import Mock

def test_get_user():
    original_db = service.db
    service.db = Mock()  # Replace global
    service.db.execute.return_value.fetchone.return_value = {"id": 1}

    try:
        result = service.get_user(1)
        assert result["id"] == 1
    finally:
        service.db = original_db  # Must restore or other tests break!

# Problems:
# - Tests can affect each other if cleanup fails
# - Import order matters (import service before replacing globals)
# - Doesn't work if the global is used at module level elsewhere
# - Fragile: adding a new dependency means updating every test
```

## The Right Answer: Dependency Injection

```python
# ✅ service.py — dependencies are PARAMETERS, not globals
class UserService:
    def __init__(self, db, cache):
        self.db = db
        self.cache = cache

    def get_user(self, user_id):
        cached = self.cache.get(f"user:{user_id}")
        if cached:
            return json.loads(cached)
        user = self.db.execute(
            "SELECT * FROM users WHERE id = %s", (user_id,)
        ).fetchone()
        self.cache.setex(f"user:{user_id}", 300, json.dumps(dict(user)))
        return dict(user)


# ✅ test_service.py — easy to test with mocks
from unittest.mock import Mock

def test_get_user_cache_miss():
    mock_db = Mock()
    mock_cache = Mock()
    mock_cache.get.return_value = None  # Cache miss
    mock_db.execute.return_value.fetchone.return_value = {
        "id": 1, "name": "Alice"
    }

    service = UserService(db=mock_db, cache=mock_cache)
    result = service.get_user(1)

    assert result["name"] == "Alice"
    mock_cache.setex.assert_called_once()  # Verify it cached the result

def test_get_user_cache_hit():
    mock_db = Mock()
    mock_cache = Mock()
    mock_cache.get.return_value = '{"id": 1, "name": "Alice"}'  # Cache hit

    service = UserService(db=mock_db, cache=mock_cache)
    result = service.get_user(1)

    assert result["name"] == "Alice"
    mock_db.execute.assert_not_called()  # DB was never hit!


# ✅ app.py — wire up real dependencies in ONE place
from sqlalchemy import create_engine
from redis import Redis

db = create_engine(os.environ["DATABASE_URL"])
cache = Redis(host="redis")
user_service = UserService(db=db, cache=cache)
```

## Scaling DI: The Composition Root Pattern

```python
# For larger apps, create all services in ONE place (the "composition root")

# ✅ container.py — all wiring happens here
class Container:
    def __init__(self, config):
        self.db = create_engine(config["DATABASE_URL"])
        self.cache = Redis(host=config["REDIS_HOST"])
        self.user_service = UserService(self.db, self.cache)
        self.order_service = OrderService(self.db, self.user_service)
        self.payment_service = PaymentService(self.db, config["STRIPE_KEY"])

# Production:
container = Container(config=os.environ)

# Testing:
test_container = Container(config={
    "DATABASE_URL": "sqlite:///:memory:",
    "REDIS_HOST": "localhost",
    "STRIPE_KEY": "sk_test_fake",
})

# ✅ FastAPI with dependency injection (framework-native)
from fastapi import Depends

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_user_service(db=Depends(get_db)):
    return UserService(db=db, cache=redis_client)

@app.get("/users/{user_id}")
def read_user(user_id: int, service: UserService = Depends(get_user_service)):
    return service.get_user(user_id)

# In tests: override the dependency
app.dependency_overrides[get_user_service] = lambda: UserService(mock_db, mock_cache)
```

## Migration Strategy (Don't Rewrite Everything at Once)

```python
# Step 1: Wrap existing globals in a class (minimal change)
class UserService:
    def __init__(self, db=None, cache=None):
        self.db = db or global_db       # Falls back to global
        self.cache = cache or global_cache

# Step 2: Update callers one at a time
# Old: get_user(1)                      → still works (uses globals)
# New: UserService(db, cache).get_user(1) → testable

# Step 3: Once all callers are updated, remove the global fallback
class UserService:
    def __init__(self, db, cache):       # No more fallback
        self.db = db
        self.cache = cache
```'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
