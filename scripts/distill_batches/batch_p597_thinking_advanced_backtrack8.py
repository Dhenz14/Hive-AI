"""Phase 2A: Advanced Reasoning — Backtracking & Dead-End Recovery (Part 8/8)"""

PAIRS = [
    (
        "thinking/backtrack-rest-api-to-graphql-partial",
        "Our REST API has grown to 47 endpoints. The frontend team is frustrated because they need to make 5-6 API calls per page to get all the data they need. Someone suggested migrating everything to GraphQL. Is that the right move?",
        r'''<think>
47 REST endpoints, frontend making 5-6 calls per page. Let me think about this.

**First approach: Migrate everything to GraphQL**
This is the suggestion. It would let the frontend request exactly what it needs in one query. But:
- 47 endpoints is a LOT to migrate
- The backend team needs to learn GraphQL resolvers, schema design, security
- GraphQL has its own complexity (N+1, query depth limits, caching)
- Existing mobile apps and third-party integrations use REST — you'd need to maintain both

This is a 3-6 month project with high risk. Let me think of something simpler...

**Second approach: Add BFF (Backend for Frontend) endpoints**
Create a few aggregate endpoints specifically for the frontend's page needs:
```
GET /api/pages/dashboard → returns users + stats + recent orders
GET /api/pages/product/123 → returns product + reviews + related
```

This solves the "5-6 calls per page" problem without any architecture change. But:
- Creates tight coupling between frontend pages and backend endpoints
- Every new page potentially needs a new endpoint
- Doesn't solve the "over-fetching" problem (getting fields you don't need)

Hmm, this is a band-aid. Let me think more...

**Third approach (backtracking): Keep REST, add a thin aggregation layer**
Wait — the real problem isn't REST. The real problem is:
1. Frontend needs data from multiple resources per page
2. REST gives one resource per endpoint

What if we kept REST for the data layer but added field selection and resource inclusion?

JSON:API and OData both solve this within REST:
```
GET /api/orders?include=customer,items.product&fields[order]=id,total,status
```

This gives the frontend query flexibility without migrating to GraphQL.

But this still might not be enough. Let me reconsider...

**Fourth approach: Partial GraphQL (hybrid)**
What if they don't migrate EVERYTHING to GraphQL? Instead:
- Keep existing REST endpoints for simple CRUD and external APIs
- Add a single GraphQL endpoint that wraps the REST layer for frontend consumption
- Frontend uses GraphQL for page-level queries
- Other consumers keep using REST

This gives the frontend team what they need WITHOUT:
- Rewriting 47 endpoints
- Forcing mobile apps to change
- Breaking third-party integrations

This is the right approach. GraphQL as a FRONTEND GATEWAY, not a replacement for REST.
</think>

Don't migrate everything to GraphQL. Let me trace through why each approach fails before landing on the right one:

**Attempt 1:** Full GraphQL migration → 3-6 months, high risk, breaks existing integrations.
**Attempt 2:** BFF endpoints per page → tight coupling, new endpoint for every new page.
**Attempt 3:** JSON:API/OData field selection → complex REST extensions, still awkward.
**Backtrack:** The insight: GraphQL isn't a replacement for REST — it's a **frontend gateway layer** that wraps your existing REST services.

## The Hybrid Architecture

```
BEFORE (frontend calls 47 REST endpoints):
  Frontend → GET /users/123
           → GET /users/123/orders
           → GET /orders/456/items
           → GET /products/789
           → GET /products/789/reviews
           = 5 round trips, lots of over-fetching

AFTER (GraphQL gateway + existing REST):
  Frontend → POST /graphql (one request)
           ↓
  GraphQL Gateway → calls existing REST endpoints internally
           ↓
  Frontend gets exactly the data it needs in one response
```

## Implementation: GraphQL Gateway Over REST

```python
# The GraphQL gateway wraps your existing REST service layer
# Your 47 REST endpoints stay untouched

import strawberry
from strawberry.fastapi import GraphQLRouter
from typing import Optional

# Reuse your existing service functions — no rewrite needed
from services.users import get_user, get_user_orders
from services.products import get_product, get_product_reviews
from services.orders import get_order_items

@strawberry.type
class Product:
    id: int
    name: str
    price: float

    @strawberry.field
    async def reviews(self, info) -> list["Review"]:
        # Calls existing service function (which uses REST/DB internally)
        return await get_product_reviews(self.id)

@strawberry.type
class OrderItem:
    id: int
    quantity: int
    price: float

    @strawberry.field
    async def product(self, info) -> Product:
        return await get_product(self.product_id)

@strawberry.type
class Order:
    id: int
    total: float
    status: str

    @strawberry.field
    async def items(self, info) -> list[OrderItem]:
        return await get_order_items(self.id)

@strawberry.type
class User:
    id: int
    name: str
    email: str

    @strawberry.field
    async def orders(self, info, limit: int = 10) -> list[Order]:
        return await get_user_orders(self.id, limit=limit)

@strawberry.type
class Query:
    @strawberry.field
    async def user(self, id: int) -> Optional[User]:
        return await get_user(id)

    @strawberry.field
    async def product(self, id: int) -> Optional[Product]:
        return await get_product(id)

schema = strawberry.Schema(query=Query)
graphql_app = GraphQLRouter(schema)

# Mount alongside your existing REST routes
app.include_router(graphql_app, prefix="/graphql")
# All 47 REST endpoints continue working at /api/...
```

## Frontend: One Request Per Page

```graphql
# Dashboard page — ONE request instead of 5-6
query DashboardPage($userId: Int!) {
  user(id: $userId) {
    name
    email
    orders(limit: 5) {
      id
      total
      status
      items {
        quantity
        product {
          name
          price
        }
      }
    }
  }
}
```

## What You Keep, What You Add

| Existing REST (keep) | New GraphQL (add) |
|---|---|
| 47 endpoints — untouched | 1 new `/graphql` endpoint |
| Mobile apps use REST | Frontend uses GraphQL |
| Third-party integrations use REST | Internal dashboard uses GraphQL |
| Service layer unchanged | GraphQL resolvers call service layer |
| REST API documentation | GraphQL schema IS the documentation |

## Migration Timeline

```
Week 1: Set up GraphQL server, define core types (User, Order, Product)
Week 2: Add resolvers that call existing service functions
Week 3: Frontend team starts migrating pages to GraphQL queries
Week 4: Add DataLoader for N+1 prevention
Ongoing: Add types/resolvers as frontend needs them

No rewrite. No breaking changes. Incremental adoption.
```

The backtracking insight: the problem wasn't REST — it was the frontend making too many calls. GraphQL solves this as an aggregation layer WITHOUT replacing your working REST infrastructure.'''
    ),
    (
        "thinking/backtrack-singleton-to-request-scoped",
        "I have a Python web app where I was using a singleton for database connections, but I'm getting threading issues. Multiple requests share the same connection and interfere with each other. I tried adding thread locks but now performance is terrible because requests serialize on the lock. How do I fix this?",
        r'''<think>
Database connection management — singleton → threading issues → locks → poor performance. Classic progression. Let me trace through the approaches.

**First attempt (user's): Singleton connection**
```python
class DB:
    _instance = None
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.conn = psycopg2.connect(...)
        return cls._instance
```
Problem: One connection shared across all threads. Two requests executing queries simultaneously on the same connection → corrupted results, transaction mixing, race conditions.

**Second attempt (user's): Thread locks**
```python
class DB:
    _lock = threading.Lock()
    def execute(self, query, params):
        with self._lock:
            self.conn.execute(query, params)
```
Problem: Now requests wait for each other. With 20 concurrent requests, 19 are waiting for 1 to finish. Effectively single-threaded.

**My first thought: thread-local connections**
```python
import threading
_local = threading.local()
def get_conn():
    if not hasattr(_local, 'conn'):
        _local.conn = psycopg2.connect(...)
    return _local.conn
```
Each thread gets its own connection. No sharing, no locks. But:
- Thread pools reuse threads → old connections might be stale/closed
- No limit on total connections (20 threads = 20 connections, could exceed DB max)
- Connections aren't returned to a pool for reuse

This is better but not right. Let me backtrack.

**The correct approach: connection POOL**
A connection pool maintains a set of connections. Each request borrows a connection, uses it, and returns it. No sharing, no locks on queries, bounded total connections.

This is what SQLAlchemy's pool, psycopg2.pool, Django's CONN_MAX_AGE, etc. provide.

Key insight: the singleton pattern was wrong because it confused "shared resource management" with "shared resource instance." You want shared MANAGEMENT (pool) but not shared INSTANCES (connections).
</think>

Each approach so far failed for a specific reason. Let me trace through:

**Attempt 1:** Singleton connection → threads corrupt each other's queries.
**Attempt 2:** Thread lock on singleton → serializes all requests (single-threaded performance).
**Backtrack:** The problem isn't sharing vs locking — it's that you need **connection pooling**: shared management, individual instances.

## Why Each Approach Fails

```python
# ATTEMPT 1: Singleton (broken)
# Thread A: BEGIN TRANSACTION
# Thread B: INSERT INTO orders...  ← runs inside Thread A's transaction!
# Thread A: ROLLBACK              ← rolls back Thread B's insert!
# Both threads share one connection = chaos

# ATTEMPT 2: Lock (correct but slow)
# Thread A: acquires lock, runs 50ms query
# Thread B: waits for lock...
# Thread C: waits for lock...
# 20 threads, 50ms each = 1000ms total (serialized)
# Should be 50ms with 20 parallel connections
```

## The Solution: Connection Pool

```python
# CORRECT: Pool manages connections, each request gets its own
from psycopg2 import pool

# Create pool at startup — shared management, individual connections
connection_pool = pool.ThreadedConnectionPool(
    minconn=5,     # Keep 5 connections warm
    maxconn=20,    # Never exceed 20 total
    host="localhost",
    database="myapp",
    user="myapp",
    password="secret",
)


class Database:
    """Request-scoped database access using connection pool."""

    def __init__(self):
        self.conn = None

    def __enter__(self):
        # Borrow a connection from the pool (blocks if all in use)
        self.conn = connection_pool.getconn()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.conn.rollback()
        else:
            self.conn.commit()
        # Return connection to pool (doesn't close it)
        connection_pool.putconn(self.conn)
        self.conn = None

    def execute(self, query, params=None):
        cursor = self.conn.cursor()
        cursor.execute(query, params)
        return cursor

    def fetchall(self, query, params=None):
        cursor = self.execute(query, params)
        return cursor.fetchall()

    def fetchone(self, query, params=None):
        cursor = self.execute(query, params)
        return cursor.fetchone()


# --- Usage in request handlers ---

@app.route('/api/orders')
def get_orders():
    with Database() as db:
        # This request has its OWN connection — no sharing, no locking
        orders = db.fetchall(
            "SELECT * FROM orders WHERE user_id = %s",
            (request.user_id,)
        )
    # Connection returned to pool here — available for next request
    return jsonify(orders)


@app.route('/api/orders', methods=['POST'])
def create_order():
    with Database() as db:
        # Transaction is scoped to THIS request
        db.execute(
            "INSERT INTO orders (user_id, total) VALUES (%s, %s)",
            (request.user_id, request.json['total'])
        )
        db.execute(
            "UPDATE inventory SET count = count - 1 WHERE product_id = %s",
            (request.json['product_id'],)
        )
    # Commits on success, rolls back on exception
    return jsonify({"status": "created"}), 201
```

## How Pooling Solves Everything

```
Singleton (1 connection, shared):
  Thread A ──→ [conn] ←── Thread B     ← CONFLICT
                ↑
  Thread C ─────┘                       ← CONFLICT

Lock (1 connection, serialized):
  Thread A ──→ [conn] (locked)
  Thread B ──→ waiting...
  Thread C ──→ waiting...               ← SLOW

Pool (N connections, parallel):
  Thread A ──→ [conn 1]  ← own connection
  Thread B ──→ [conn 2]  ← own connection
  Thread C ──→ [conn 3]  ← own connection
  (Thread D waits only if all 20 pool connections are busy)
```

## For Django/SQLAlchemy Users

```python
# Django: uses connection pooling by default (per-thread)
# Just configure CONN_MAX_AGE for persistent connections:
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'CONN_MAX_AGE': 600,  # Reuse connections for 10 minutes
    }
}

# SQLAlchemy: pool is built in
from sqlalchemy import create_engine
engine = create_engine(
    "postgresql://user:pass@localhost/mydb",
    pool_size=10,        # 10 connections in pool
    max_overflow=20,     # Up to 20 more during spikes
    pool_recycle=3600,   # Recycle connections after 1 hour
)
```

The key backtracking insight: a singleton was the wrong pattern because you confused shared MANAGEMENT with shared INSTANCES. A pool provides shared management (one pool, bounded connections) while giving each thread its own connection instance.'''
    ),
    (
        "thinking/backtrack-flat-routes-to-resource-router",
        "Our Express.js app has 60+ route definitions in a single routes.js file. It's becoming unmanageable. I tried splitting by feature into separate files but now we have circular import issues. How do I organize this?",
        r'''<think>
Route organization problem. Let me think through the approaches.

**First approach (user's): separate files by feature**
```
routes/
  users.js
  orders.js
  products.js
```
Each imports the app/router. But they had circular imports — probably because modules import each other or share middleware.

**Second approach: blueprint/router pattern**
```javascript
// users.js
const router = express.Router();
router.get('/', getUsers);
module.exports = router;

// app.js
app.use('/api/users', require('./routes/users'));
```
This should avoid circular imports because each file exports a router, not importing the app. If they still have circular imports, the issue is in shared utilities, not routes.

Wait, let me think about what causes circular imports in route files...
- `users.js` imports `orders.js` for user's orders
- `orders.js` imports `users.js` for order's user
→ Circular!

The fix isn't just file splitting — it's ensuring routes DON'T import each other. Each route module should be independent, using middleware and shared services.

**Third approach (after backtracking): resource-based routing with convention**
Instead of manually wiring routes, use a convention-based loader that auto-discovers route modules from a directory structure. Each module is self-contained.

This is what frameworks like NestJS and Django do — you define routes within each module and a central loader mounts them.

Let me provide the Express version.
</think>

The circular imports happen because route files import each other. Let me trace through:

**Attempt 1:** One big file → unmanageable at 60+ routes.
**Attempt 2:** Split by feature → circular imports (routes referencing each other).
**Backtrack:** Routes should NEVER import each other. Each module is self-contained, mounted by a central loader.

## The Solution: Self-Contained Route Modules

```
routes/
  index.js          ← Auto-loads all route modules
  users.js          ← Self-contained, exports router
  orders.js         ← Self-contained, exports router
  products.js       ← Self-contained, exports router
  auth.js           ← Self-contained, exports router
middleware/
  auth.js           ← Shared middleware (imported by routes, not circular)
services/
  userService.js    ← Business logic (imported by routes)
  orderService.js   ← Business logic (imported by routes)
```

### Each Route Module: Self-Contained

```javascript
// routes/users.js
const { Router } = require('express');
const { requireAuth, requireRole } = require('../middleware/auth');
const userService = require('../services/userService');

const router = Router();

router.get('/', requireAuth, async (req, res) => {
  const users = await userService.list(req.query);
  res.json(users);
});

router.get('/:id', requireAuth, async (req, res) => {
  const user = await userService.getById(req.params.id);
  if (!user) return res.status(404).json({ error: 'User not found' });
  res.json(user);
});

router.get('/:id/orders', requireAuth, async (req, res) => {
  // DON'T import orders route — call the service directly
  const orders = await require('../services/orderService').getByUserId(req.params.id);
  res.json(orders);
});

router.post('/', requireAuth, requireRole('admin'), async (req, res) => {
  const user = await userService.create(req.body);
  res.status(201).json(user);
});

router.put('/:id', requireAuth, async (req, res) => {
  const user = await userService.update(req.params.id, req.body);
  res.json(user);
});

router.delete('/:id', requireAuth, requireRole('admin'), async (req, res) => {
  await userService.delete(req.params.id);
  res.status(204).send();
});

module.exports = { prefix: '/api/users', router };
```

### Auto-Loader: No Manual Wiring

```javascript
// routes/index.js — auto-discovers and mounts all route modules
const fs = require('fs');
const path = require('path');

function loadRoutes(app) {
  const routeDir = __dirname;

  fs.readdirSync(routeDir)
    .filter(file => file !== 'index.js' && file.endsWith('.js'))
    .forEach(file => {
      const { prefix, router } = require(path.join(routeDir, file));
      app.use(prefix, router);
      console.log(`  Mounted: ${prefix} (${file})`);
    });
}

module.exports = loadRoutes;


// app.js — clean and simple
const express = require('express');
const loadRoutes = require('./routes');

const app = express();
app.use(express.json());
loadRoutes(app);
// That's it. All 60+ routes auto-loaded.
```

## Why This Eliminates Circular Imports

```
BEFORE (circular):
  users.js ──imports──→ orders.js
  orders.js ──imports──→ users.js    ← CIRCULAR!

AFTER (no cross-imports):
  users.js ──imports──→ userService.js
  orders.js ──imports──→ orderService.js
  (routes never import each other)

  If users need order data:
    users.js → orderService.js (service layer, not route layer)
```

The rule: **routes import services, never other routes.** Services can import other services (but use dependency injection to avoid circularity there too).

## Scaling to 100+ Routes

```
routes/
  v1/                    ← API version 1
    users.js
    orders.js
    products.js
  v2/                    ← API version 2 (breaking changes)
    users.js
    orders.js
  admin/                 ← Admin-only routes
    reports.js
    settings.js
  webhooks/              ← External webhook handlers
    stripe.js
    sendgrid.js
  index.js               ← Loads all subdirectories recursively
```

```javascript
// routes/index.js — recursive loader
function loadRoutes(app, dir = __dirname, basePrefix = '') {
  fs.readdirSync(dir, { withFileTypes: true }).forEach(entry => {
    if (entry.isDirectory()) {
      loadRoutes(app, path.join(dir, entry.name), `${basePrefix}/${entry.name}`);
    } else if (entry.name !== 'index.js' && entry.name.endsWith('.js')) {
      const { prefix, router } = require(path.join(dir, entry.name));
      app.use(prefix, router);
    }
  });
}
```

The backtracking insight: splitting routes by feature is correct, but routes must be SELF-CONTAINED. They import services and middleware — never other route modules.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
