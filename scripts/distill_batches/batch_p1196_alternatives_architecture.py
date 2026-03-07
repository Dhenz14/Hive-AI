"""
Proactive alternatives training pairs - Software architecture decisions
"""

pairs = [
    {
        "instruction": r'''We're a team of 3 developers building an e-commerce platform. We want to use microservices from the start -- separate services for users, products, orders, payments, and inventory. Can you help us design the service boundaries?''',
        "output": r'''<think>
A 3-person team running 5+ microservices will spend more time on infrastructure (service discovery, distributed tracing, API gateways, deployment pipelines per service) than on features. Microservices solve scaling problems that a 3-person team does not have yet. A modular monolith gives them clean boundaries that can be extracted later. I should be respectful since microservices are popular and the team clearly thought about it.
</think>

Those service boundaries make sense conceptually. Before you commit though, I want to flag something: with 3 developers and 5+ services, you will spend a significant chunk of your time on infrastructure rather than features -- separate CI/CD pipelines, inter-service communication, distributed debugging, and deployment orchestration.

A modular monolith gives you the same clean separation with much less overhead:

```
ecommerce/
    users/
        models.py
        services.py      # Business logic
        api.py            # Route handlers
        repository.py     # Data access
    products/
        models.py
        services.py
        api.py
        repository.py
    orders/
        models.py
        services.py
        api.py
        repository.py
    payments/
        ...
    inventory/
        ...
    shared/
        events.py         # Internal event bus
        middleware.py
```

Key rules to keep it modular:

1. **No cross-module imports of models** -- modules communicate through service interfaces
2. **Each module owns its tables** -- products module never queries the users table directly
3. **Use an internal event bus** for cross-cutting concerns

```python
# orders/services.py
from shared.events import publish

class OrderService:
    def __init__(self, order_repo, payment_client, inventory_client):
        self.order_repo = order_repo
        self.payment_client = payment_client
        self.inventory_client = inventory_client

    def place_order(self, user_id: int, items: list) -> Order:
        order = self.order_repo.create(user_id, items)
        self.inventory_client.reserve(items)
        self.payment_client.charge(order.total)
        publish("order.placed", {"order_id": order.id})
        return order
```

When your team grows and you can clearly identify which module needs independent scaling, extracting it into a real service is straightforward because the boundaries already exist. Many successful companies (Shopify, GitHub) ran monoliths well past the 3-person stage.'''
    },
    {
        "instruction": r'''I need to add authentication to my web app. I'm thinking of building it from scratch -- hashing passwords with bcrypt, managing sessions in Redis, handling password resets via email tokens. I want full control over the auth flow. Can you help me design this?''',
        "output": r'''<think>
Custom auth is one of the highest-risk things to build from scratch. It is not just bcrypt -- it is timing attacks, token invalidation, rate limiting, CSRF, session fixation, password policies, and more. Libraries like Passport.js, Django's auth, or managed services like Auth0/Clerk handle all of this. But the user wants control, so I should acknowledge that and suggest a middle ground -- use a library but customize the flow.
</think>

Building auth from scratch teaches you a lot, and wanting control over the flow is understandable. That said, authentication has a huge surface area for security bugs -- timing attacks on token comparison, session fixation, CSRF on login forms, rate limiting on password attempts, secure token generation for resets, and more. Even experienced teams get bitten by edge cases.

A solid middle ground: use a proven auth library that gives you control without reinventing the security primitives.

For a Python app (Flask/FastAPI):

```python
# Flask-Login + Flask-Security give you full control
# while handling the dangerous crypto parts

from flask_security import Security, SQLAlchemyUserDatastore
from flask_security.utils import hash_password, verify_password

# You control the user model
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True)
    password = db.Column(db.String(255))
    active = db.Column(db.Boolean)
    # Add your custom fields
    organization_id = db.Column(db.Integer)

# You control the login flow
@app.route("/login", methods=["POST"])
def custom_login():
    user = User.query.filter_by(email=request.json["email"]).first()
    if user and verify_password(request.json["password"], user.password):
        login_user(user)
        # Your custom logic here
        log_login_event(user)
        return jsonify({"status": "ok"})
    return jsonify({"status": "error"}), 401
```

For Node.js, Passport.js gives similar flexibility -- you write the strategy, it handles session serialization.

If you want to skip managing passwords entirely, consider OAuth2/OIDC providers where users sign in with Google/GitHub. You get security without maintaining password infrastructure.

If you still want to go fully custom, at minimum use: `bcrypt` (not SHA-256) for hashing, `secrets.token_urlsafe(32)` for reset tokens, constant-time comparison via `hmac.compare_digest`, and rate limiting on all auth endpoints.'''
    },
    {
        "instruction": r'''I'm building a dashboard that shows live metrics -- CPU usage, request counts, error rates. Updates should appear every second. I'm planning to use REST endpoints and poll them from the frontend with setInterval. Can you help me set up the polling?''',
        "output": r'''<think>
Polling every second means one HTTP request per second per client. For a few users that is fine, but it wastes bandwidth since most responses will be "no change." Server-Sent Events (SSE) is a much better fit -- the server pushes updates when they happen over a single long-lived connection. WebSockets are overkill for one-directional data. SSE is simpler and works with regular HTTP. I should show both approaches.
</think>

Polling will work, but for 1-second updates you will be making a lot of requests where nothing changed. With 50 users on the dashboard, that is 50 requests per second hitting your API even during quiet periods.

Server-Sent Events (SSE) is a great fit here -- the server pushes updates over a single HTTP connection. It is simpler than WebSockets since your data flows one direction (server to client):

Backend (Python/FastAPI):

```python
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio
import json

app = FastAPI()

async def metrics_stream():
    while True:
        metrics = {
            "cpu": get_cpu_usage(),
            "requests": get_request_count(),
            "errors": get_error_rate(),
            "timestamp": time.time()
        }
        yield f"data: {json.dumps(metrics)}\n\n"
        await asyncio.sleep(1)

@app.get("/metrics/stream")
async def stream_metrics():
    return StreamingResponse(
        metrics_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"}
    )
```

Frontend:

```javascript
const source = new EventSource("/metrics/stream");

source.onmessage = (event) => {
    const metrics = JSON.parse(event.data);
    updateCpuChart(metrics.cpu);
    updateRequestCounter(metrics.requests);
    updateErrorRate(metrics.errors);
};

source.onerror = () => {
    // EventSource auto-reconnects, but you can add custom logic
    console.log("Connection lost, reconnecting...");
};
```

Benefits over polling:
- **One connection** instead of one request per second per client
- **Automatic reconnection** built into the EventSource API
- **Lower latency** -- updates arrive the moment they are available
- **Less server load** -- no parsing a new HTTP request every second

SSE works in all modern browsers. The only case where you would need WebSockets instead is if the client also needs to send data back to the server frequently (like a chat app). For a read-only dashboard, SSE is the simpler choice.'''
    },
    {
        "instruction": r'''I'm storing product data in PostgreSQL. Each product has a bunch of attributes that vary by category -- electronics have voltage, wattage, connectivity; clothing has size, material, color; food has ingredients, allergens, nutrition facts. I'm thinking of using a wide table with nullable columns for every possible attribute. How should I structure this?''',
        "output": r'''<think>
A wide table with nullable columns becomes unmanageable as categories grow -- hundreds of columns, mostly NULL. The three common patterns are: EAV (entity-attribute-value), JSONB column, or table-per-category. PostgreSQL's JSONB is the sweet spot -- it keeps flexible attributes queryable and indexed while the core product fields stay in proper columns. This is the hybrid approach.
</think>

A wide table will technically work, but once you have 20+ categories with different attributes, you will end up with hundreds of nullable columns -- hard to maintain and wasteful in storage.

PostgreSQL's JSONB column gives you the best of both worlds -- structured columns for shared fields, flexible JSON for category-specific attributes:

```sql
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    category VARCHAR(50) NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    sku VARCHAR(50) UNIQUE,
    created_at TIMESTAMP DEFAULT NOW(),
    -- Flexible attributes per category
    attributes JSONB NOT NULL DEFAULT '{}'
);

-- Electronics product
INSERT INTO products (name, category, price, attributes) VALUES (
    'USB-C Charger', 'electronics', 29.99,
    '{"voltage": 120, "wattage": 65, "connectivity": ["USB-C", "USB-A"]}'
);

-- Clothing product
INSERT INTO products (name, category, price, attributes) VALUES (
    'Cotton T-Shirt', 'clothing', 19.99,
    '{"size": "M", "material": "cotton", "color": "navy"}'
);
```

JSONB is fully queryable and indexable:

```sql
-- Find all electronics over 60 watts
SELECT * FROM products
WHERE category = 'electronics'
  AND (attributes->>'wattage')::int > 60;

-- Find clothing in a specific color
SELECT * FROM products
WHERE category = 'clothing'
  AND attributes->>'color' = 'navy';

-- Index for fast lookups on common queries
CREATE INDEX idx_products_attrs ON products USING GIN (attributes);

-- Partial index for category-specific queries
CREATE INDEX idx_electronics_wattage ON products
    ((attributes->>'wattage'))
    WHERE category = 'electronics';
```

You can also add validation with CHECK constraints:

```sql
-- Ensure electronics always have voltage
ALTER TABLE products ADD CONSTRAINT chk_electronics
    CHECK (category != 'electronics' OR attributes ? 'voltage');
```

This hybrid approach keeps your shared fields normalized and queryable with standard SQL while letting each category define its own attributes without schema changes.'''
    },
    {
        "instruction": r'''I have a SaaS app with about 30 customers. Right now everyone shares one PostgreSQL database with a `tenant_id` column on every table. It works but I'm worried about data isolation as we grow. Should I create a separate database for each tenant?''',
        "output": r'''<think>
Separate databases per tenant is maximum isolation but creates operational nightmares -- 30+ databases to migrate, back up, monitor, and connection-pool. Schema-per-tenant in the same database is the middle ground: good isolation via PostgreSQL schemas, single database to manage, easy migrations with a loop. For 30 tenants this is the sweet spot. Separate databases make sense at 1000+ tenants or when customers demand it contractually.
</think>

Your current shared-table approach works, but the concern about isolation is valid -- one bad WHERE clause and you leak data across tenants. Separate databases per tenant is the other extreme, but managing 30+ databases (migrations, backups, monitoring, connection pools) gets painful quickly.

The middle ground is schema-per-tenant in the same database:

```sql
-- Create a schema per tenant
CREATE SCHEMA tenant_acme;
CREATE SCHEMA tenant_globex;

-- Same tables in each schema
CREATE TABLE tenant_acme.users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255),
    name VARCHAR(255)
);

CREATE TABLE tenant_globex.users (
    id SERIAL PRIMARY KEY,
    email VARCHAR(255),
    name VARCHAR(255)
);
```

Then set the schema at the start of each request:

```python
# Middleware or connection setup
def set_tenant(conn, tenant_name: str):
    schema = f"tenant_{tenant_name}"
    conn.execute(f"SET search_path TO {schema}, public")

# Now all queries automatically use the right schema
# No tenant_id needed -- impossible to accidentally cross tenants
cursor.execute("SELECT * FROM users")  # hits tenant_acme.users
```

Running migrations across all tenants:

```python
def migrate_all_tenants(migration_sql: str):
    tenants = get_all_tenant_schemas()
    for schema in tenants:
        with get_connection() as conn:
            conn.execute(f"SET search_path TO {schema}")
            conn.execute(migration_sql)
            conn.commit()
```

Benefits over your current approach:
- **True isolation** -- no risk of cross-tenant data leaks
- **Per-tenant backups** -- can dump/restore individual schemas
- **Single database** -- one connection pool, one set of monitoring

Benefits over separate databases:
- **One migration run** per deploy instead of 30
- **Shared connection pool** instead of 30 separate pools
- **Easier cross-tenant analytics** when you need it (just set search_path to multiple schemas)

At your scale of 30 tenants, schema separation is the sweet spot. Separate databases start making sense if you have contractual data residency requirements or need to put specific tenants on dedicated hardware.'''
    },
]
