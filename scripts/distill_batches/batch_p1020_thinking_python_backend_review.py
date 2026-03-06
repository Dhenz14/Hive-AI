"""Thinking-trace code review pairs: Python backend (FastAPI, Django, Flask, Celery, SQLAlchemy)."""

PAIRS = [
    (
        "thinking/code-review",
        r'''Here is some code that works but has issues. Review it and suggest improvements:

```python
from fastapi import FastAPI, Query
from databases import Database

app = FastAPI()
db = Database("postgresql://app:secret@db:5432/myapp")

@app.on_event("startup")
async def startup():
    await db.connect()

@app.get("/users/search")
async def search_users(
    name: str = Query(None),
    role: str = Query(None),
    sort_by: str = Query("created_at"),
    order: str = Query("desc"),
    limit: int = Query(50),
    offset: int = Query(0),
):
    query = "SELECT id, name, email, role FROM users WHERE 1=1"
    if name:
        query += f" AND name LIKE '%{name}%'"
    if role:
        query += f" AND role = '{role}'"
    query += f" ORDER BY {sort_by} {order}"
    query += f" LIMIT {limit} OFFSET {offset}"
    rows = await db.fetch_all(query)
    return {"users": [dict(r) for r in rows], "total": len(rows)}
```''',
        r'''<think>
Systematic review of this FastAPI search endpoint:

First read: a user search endpoint that builds a SQL query from query parameters. It connects to PostgreSQL on startup and runs dynamic queries.

Now let me look for problems in priority order.

Critical security issues -- I see multiple SQL injection vectors:
1. `name` is interpolated directly into a LIKE clause with f-string. An attacker can inject: `'; DROP TABLE users; --`
2. `role` is similarly injectable
3. `sort_by` allows arbitrary column names -- or even subqueries. An attacker could pass `(SELECT password FROM users LIMIT 1)` as the sort column
4. `order` is not validated -- should only be "asc" or "desc" but could be anything
5. Even `limit` and `offset`, while typed as int by FastAPI, the sort_by/order injection is worse

The total count is wrong -- `len(rows)` returns the count of the current page, not the total number of matching records. Pagination is broken without a proper COUNT query.

Performance issues:
- `LIKE '%name%'` with a leading wildcard defeats indexes. On a large table this is a full table scan every time.
- No index hints or search optimization (should use full-text search or trigram index for name search)

Other problems:
- Database URL with credentials hardcoded in source
- `on_event("startup")` is deprecated in newer FastAPI; should use lifespan
- No connection pool configuration
- No error handling whatsoever
- No pagination metadata in response (total pages, has_next, etc.)

Priority: SQL injection is the showstopper. That must be fixed first. Then the broken pagination, then everything else.
</think>

## Code Review

### Critical Issues

**SQL Injection (Severity: Critical)**

Every string parameter is directly interpolated into the SQL query using f-strings. This is textbook SQL injection -- the most dangerous vulnerability in web applications.

Vulnerable parameters:
- `name`: `' OR 1=1; DROP TABLE users; --` would destroy your data
- `role`: same injection vector
- `sort_by`: can inject subqueries like `(SELECT password FROM users LIMIT 1)`
- `order`: not validated against an allowlist

**Hardcoded credentials**: The database URL contains plaintext credentials in source code. This will end up in version control.

### Broken Functionality

**Pagination total is wrong**: `len(rows)` returns the number of rows on the current page, not the total matching count. A client cannot know how many pages exist. You need a separate `COUNT(*)` query.

### Performance

**Leading wildcard LIKE**: `LIKE '%name%'` cannot use a B-tree index. On a table with millions of rows, every search is a sequential scan. Use PostgreSQL's `pg_trgm` extension with a GIN index, or full-text search with `tsvector`.

### Maintainability

- `on_event("startup")` is deprecated -- use FastAPI's `lifespan` context manager
- No error handling: if the DB is down, the client gets an unformatted 500
- No input validation on `limit` (a user could request `limit=1000000`)
- Response structure lacks pagination metadata

### Refactored Code

```python
import os
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, Query, HTTPException
from databases import Database

DATABASE_URL = os.environ["DATABASE_URL"]  # never hardcode credentials

db = Database(DATABASE_URL, min_size=5, max_size=20)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await db.connect()
    yield
    await db.disconnect()


app = FastAPI(lifespan=lifespan)

# Allowlists prevent injection in ORDER BY / sort direction
SORTABLE_COLUMNS = {"created_at", "name", "email", "role"}
MAX_PAGE_SIZE = 100


@app.get("/users/search")
async def search_users(
    name: str = Query(None, max_length=200),
    role: str = Query(None, max_length=50),
    sort_by: str = Query("created_at"),
    order: Literal["asc", "desc"] = Query("desc"),
    limit: int = Query(50, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
):
    # Validate sort column against allowlist
    if sort_by not in SORTABLE_COLUMNS:
        raise HTTPException(
            status_code=400,
            detail=f"sort_by must be one of: {', '.join(sorted(SORTABLE_COLUMNS))}",
        )

    # Build query with parameterized values -- NEVER interpolate user input
    conditions = []
    values = {}

    if name:
        # Use pg_trgm similarity or ILIKE with parameter binding
        conditions.append("name ILIKE :name_pattern")
        values["name_pattern"] = f"%{name}%"
    if role:
        conditions.append("role = :role")
        values["role"] = role

    where_clause = " AND ".join(conditions) if conditions else "TRUE"

    # Count total matches (separate query for accurate pagination)
    count_query = f"SELECT COUNT(*) FROM users WHERE {where_clause}"
    total = await db.fetch_val(count_query, values)

    # sort_by and order are validated above, safe to interpolate
    data_query = (
        f"SELECT id, name, email, role FROM users "
        f"WHERE {where_clause} "
        f"ORDER BY {sort_by} {order} "
        f"LIMIT :limit OFFSET :offset"
    )
    values["limit"] = limit
    values["offset"] = offset

    try:
        rows = await db.fetch_all(data_query, values)
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")

    return {
        "users": [dict(r) for r in rows],
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_next": offset + limit < total,
    }
```

### Key Changes Summary

| Before | After |
|--------|-------|
| f-string SQL interpolation | Parameterized queries with `:param` binding |
| No sort_by validation | Allowlist of valid columns |
| `order` accepts anything | `Literal["asc", "desc"]` type constraint |
| Hardcoded DB credentials | `os.environ["DATABASE_URL"]` |
| `len(rows)` as total | Separate `COUNT(*)` query |
| No limit cap | `MAX_PAGE_SIZE = 100` |
| Deprecated `on_event` | `lifespan` context manager |
| No error handling | try/except with proper HTTP status codes |
'''),

    (
        "thinking/code-review",
        r'''Here is some code that works but has issues. Review it and suggest improvements:

```python
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from .models import Order, OrderItem, Product

@login_required
def dashboard(request):
    orders = Order.objects.filter(user=request.user).order_by('-created_at')[:20]
    order_data = []
    for order in orders:
        items = OrderItem.objects.filter(order=order)
        item_list = []
        for item in items:
            product = Product.objects.get(id=item.product_id)
            item_list.append({
                'name': product.name,
                'price': product.price,
                'quantity': item.quantity,
                'subtotal': product.price * item.quantity,
            })
        order_data.append({
            'id': order.id,
            'date': order.created_at,
            'status': order.status,
            'items': item_list,
            'total': sum(i['subtotal'] for i in item_list),
        })
    return render(request, 'dashboard.html', {'orders': order_data})
```''',
        r'''<think>
Let me analyze this Django dashboard view systematically.

First read: it loads a user's 20 most recent orders, then for each order fetches items, and for each item fetches the product. Builds a nested data structure for the template.

The big problem is immediately obvious: N+1 queries. Let me count:
1. 1 query for orders (up to 20)
2. For each order: 1 query for items -> up to 20 queries
3. For each item: 1 query for the product -> if each order has ~5 items, that's 100 queries

Total: potentially 1 + 20 + 100 = 121 database queries for a single page load. This will be slow and will crush the database under load.

Are there bugs? `Product.objects.get(id=item.product_id)` will raise `Product.DoesNotExist` if the product was deleted. That's a 500 error on the dashboard -- very bad. Data integrity issues shouldn't crash user-facing pages.

Other issues:
- Computing totals in Python instead of the database. The DB is much faster at aggregation.
- No caching -- this dashboard is probably hit frequently
- Building dicts manually instead of using Django serialization or model methods
- The `subtotal` calculation uses `product.price` at query time, not the price at purchase time. If prices change, historical order totals change. This is a data modeling bug -- OrderItem should store the price at time of purchase.

Priority: N+1 queries is the performance killer. The price-at-purchase bug is a correctness issue. The missing DoesNotExist handling is a reliability issue.
</think>

## Code Review

### Critical Issues

**N+1 Query Problem (Severity: High)**

This view executes up to 121 database queries for a single page load:
- 1 query for orders
- 1 query per order for items (up to 20)
- 1 query per item for the product (potentially 100+)

Under load with concurrent users, this will saturate your database connection pool.

**Missing error handling**: `Product.objects.get(id=item.product_id)` raises `Product.DoesNotExist` (a 500 error) if a product was deleted. Users see a crash on their dashboard because of a data integrity edge case.

**Historical price bug**: The code uses `product.price` (current price) to calculate order totals. If a product's price changes from $10 to $15, all historical orders retroactively show the new price. `OrderItem` should store `price_at_purchase`.

### Performance

The nested loop with individual queries is the textbook example of what `select_related` and `prefetch_related` exist to solve. Django's ORM can fetch all of this in 2-3 queries with proper prefetching.

### Maintainability

- Manual dict construction is fragile -- if fields change, this code must be updated
- Business logic (total calculation) is in the view instead of the model
- No pagination beyond the hardcoded `[:20]`

### Refactored Code

```python
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import F, Sum, DecimalField
from .models import Order, OrderItem, Product


@login_required
def dashboard(request):
    # 1 query for orders + 1 query for items + 1 query for products = 3 total
    orders = (
        Order.objects
        .filter(user=request.user)
        .prefetch_related(
            'items__product'  # eagerly load items AND their products
        )
        .annotate(
            total=Sum(
                F('items__price_at_purchase') * F('items__quantity'),
                output_field=DecimalField(),
            )
        )
        .order_by('-created_at')[:20]
    )

    order_data = []
    for order in orders:
        item_list = [
            {
                'name': item.product.name if item.product else 'Deleted Product',
                'price': item.price_at_purchase,
                'quantity': item.quantity,
                'subtotal': item.price_at_purchase * item.quantity,
            }
            for item in order.items.all()  # no extra query -- prefetched
        ]
        order_data.append({
            'id': order.id,
            'date': order.created_at,
            'status': order.get_status_display(),
            'items': item_list,
            'total': order.total or 0,
        })

    return render(request, 'dashboard.html', {'orders': order_data})
```

**Assumes this migration for OrderItem:**
```python
# Add price_at_purchase to OrderItem if not already present
class OrderItem(models.Model):
    order = models.ForeignKey(Order, related_name='items', on_delete=models.CASCADE)
    product = models.ForeignKey(Product, null=True, on_delete=models.SET_NULL)
    quantity = models.PositiveIntegerField()
    price_at_purchase = models.DecimalField(max_digits=10, decimal_places=2)
```

### Key Changes Summary

| Before | After |
|--------|-------|
| ~121 queries per page load | 3 queries (orders + prefetch items + prefetch products) |
| `Product.objects.get()` crashes on deleted products | `on_delete=SET_NULL` + graceful fallback |
| Uses current `product.price` | Uses `price_at_purchase` stored at order time |
| Totals computed in Python loop | `annotate(Sum(...))` computed in database |
| Raw string status | `get_status_display()` for human-readable status |
'''),

    (
        "thinking/code-review",
        r'''Here is some code that works but has issues. Review it and suggest improvements:

```python
import hashlib
import time
from functools import wraps
from flask import Flask, request, jsonify, g

app = Flask(__name__)
API_KEYS = {
    "key_abc123_example": {"user_id": 1, "role": "admin"},
    "key_def456_example": {"user_id": 2, "role": "viewer"},
}

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        api_key = request.headers.get("X-API-Key", "")
        if api_key in API_KEYS:
            g.current_user = API_KEYS[api_key]
            return f(*args, **kwargs)
        return jsonify({"error": "unauthorized"}), 401
    return decorated

def require_role(role):
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            if g.current_user["role"] == role:
                return f(*args, **kwargs)
            return jsonify({"error": "forbidden"}), 403
        return decorated
    return decorator

@app.route("/admin/users", methods=["GET"])
@require_auth
@require_role("admin")
def list_users():
    return jsonify({"users": list(API_KEYS.values())})
```''',
        r'''<think>
Let me analyze this Flask auth middleware carefully.

First read: API key authentication with role-based access control. Keys are stored in a dict, checked on each request with a decorator, and roles are enforced with a second decorator.

Security issues -- this is where the real problems are:

1. **Timing attack on API key comparison**: `if api_key in API_KEYS` uses Python's standard dict lookup, which does string comparison. But the bigger issue is that dict lookup uses hash comparison, which actually IS constant time for the hash step. Wait -- actually the concern here is different. The `in` operator for a dict hashes the key and checks the bucket, so it's roughly constant time. But the real issue is that for string keys, Python still needs to do an equality check after the hash matches, and that equality check short-circuits. In practice this is hard to exploit on a dict, but the principle is wrong -- we should use `hmac.compare_digest` for secret comparison.

Actually, let me reconsider. The bigger problems are:

2. **API keys stored in plaintext in source code**. This is terrible -- they'll be in version control, visible to anyone with repo access. Keys should be hashed and stored in a database.

3. **No key hashing**: Even if moved to a DB, keys should be stored as hashes (like passwords), not plaintext.

4. **No rate limiting**: An attacker can brute-force API keys with no throttling.

5. **Leaking API key data**: The `/admin/users` endpoint returns `list(API_KEYS.values())` -- which returns user_id and role for every API key holder. But worse, if someone modifies this, they might accidentally return the keys themselves.

6. **Decorator ordering matters but is fragile**: `@require_role` accesses `g.current_user`, but if someone puts `@require_role` before `@require_auth`, it crashes with a missing attribute. There's no defensive check.

7. **No logging of auth failures**: Failed auth attempts are invisible -- you can't detect brute-force attacks.

8. **The API key format is predictable**: `key_abc123_example` suggests sequential or simple key generation.

Priority: plaintext keys in source code is the worst. Then timing-safe comparison. Then rate limiting and logging.
</think>

## Code Review

### Critical Issues

**Plaintext API keys in source code (Severity: Critical)**

API keys are hardcoded in a Python dict committed to version control. Anyone with repo access (including CI/CD logs, error traces, or a compromised developer machine) has full admin access. Keys must be hashed and stored in a database, never in source.

**Timing attack vulnerability (Severity: High)**

While Python dict lookup is hash-based (roughly constant time), the final equality check after hash collision short-circuits on the first differing byte. Use `hmac.compare_digest` for constant-time comparison of secrets. More importantly, you should be comparing hashes of keys, not raw keys.

**No rate limiting on authentication (Severity: High)**

An attacker can make unlimited authentication attempts. With the `apikey_` prefix known, the search space for brute force is reduced. There's no throttling, no lockout, and no logging of failures.

### Security Design

- `require_role` silently assumes `g.current_user` exists -- if decorators are reordered, you get a 500 error instead of a 401
- `/admin/users` returns internal user metadata; if the response structure changes, keys could leak
- No audit logging of who accessed what

### Refactored Code

```python
import hashlib
import hmac
import logging
import os
import secrets
import time
from functools import wraps

from flask import Flask, request, jsonify, g

app = Flask(__name__)
logger = logging.getLogger(__name__)


def hash_api_key(key: str) -> str:
    """One-way hash for API key storage. Use SHA-256 since keys are
    high-entropy (unlike passwords, no need for bcrypt)."""
    return hashlib.sha256(key.encode()).hexdigest()


# In production, load from database. Keys stored as hashes only.
# To register: store hash_api_key(raw_key), give raw_key to user once.
API_KEY_HASHES = {
    hash_api_key(os.environ["ADMIN_API_KEY"]): {"user_id": 1, "role": "admin"},
    hash_api_key(os.environ["VIEWER_API_KEY"]): {"user_id": 2, "role": "viewer"},
}

# Simple in-memory rate limiter (use Redis in production)
_auth_failures: dict[str, list[float]] = {}
MAX_FAILURES = 5
WINDOW_SECONDS = 300


def _is_rate_limited(ip: str) -> bool:
    now = time.monotonic()
    attempts = _auth_failures.get(ip, [])
    # Keep only recent attempts
    attempts = [t for t in attempts if now - t < WINDOW_SECONDS]
    _auth_failures[ip] = attempts
    return len(attempts) >= MAX_FAILURES


def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        client_ip = request.remote_addr

        if _is_rate_limited(client_ip):
            logger.warning("Rate limited auth attempt from %s", client_ip)
            return jsonify({"error": "too many requests"}), 429

        api_key = request.headers.get("X-API-Key", "")
        key_hash = hash_api_key(api_key)

        # Constant-time lookup: iterate all hashes to prevent timing leaks
        matched_user = None
        for stored_hash, user_data in API_KEY_HASHES.items():
            if hmac.compare_digest(key_hash, stored_hash):
                matched_user = user_data
                break

        if matched_user is None:
            _auth_failures.setdefault(client_ip, []).append(time.monotonic())
            logger.warning("Failed auth from %s", client_ip)
            # Constant delay to prevent timing analysis
            time.sleep(0.1)
            return jsonify({"error": "unauthorized"}), 401

        g.current_user = matched_user
        return f(*args, **kwargs)

    return decorated


def require_role(*allowed_roles):
    """Accept one or more roles. Checks that auth ran first."""
    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            user = getattr(g, "current_user", None)
            if user is None:
                # Decorator misordering -- fail safe, not open
                logger.error("require_role used without require_auth on %s", f.__name__)
                return jsonify({"error": "unauthorized"}), 401
            if user["role"] not in allowed_roles:
                logger.warning("Forbidden: user %s tried %s", user["user_id"], f.__name__)
                return jsonify({"error": "forbidden"}), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


@app.route("/admin/users", methods=["GET"])
@require_auth
@require_role("admin")
def list_users():
    # Return only safe fields, never key hashes
    users = [{"user_id": u["user_id"], "role": u["role"]} for u in API_KEY_HASHES.values()]
    return jsonify({"users": users})
```

### Key Changes Summary

| Before | After |
|--------|-------|
| Plaintext keys in source | Hashed keys, raw keys in env vars |
| `if key in dict` (timing leak) | `hmac.compare_digest` on hashes |
| No rate limiting | IP-based rate limiting with lockout window |
| No logging | Auth failures and forbidden access logged |
| `require_role` crashes if auth missing | Defensive `getattr` check, fails closed |
| Single role check | `require_role(*allowed_roles)` accepts multiple roles |
'''),

    (
        "thinking/code-review",
        r'''Here is some code that works but has issues. Review it and suggest improvements:

```python
from celery import Celery
from myapp.models import Order
from myapp.services import PaymentGateway, EmailService, InventoryService

app = Celery('tasks', broker='redis://localhost:6379/0')

@app.task
def process_order(order_id):
    order = Order.objects.get(id=order_id)

    # Charge the customer
    payment = PaymentGateway()
    charge = payment.charge(order.user.credit_card, order.total)
    order.payment_id = charge.id
    order.save()

    # Update inventory
    inventory = InventoryService()
    for item in order.items.all():
        inventory.decrement(item.product_id, item.quantity)

    # Send confirmation email
    email = EmailService()
    email.send_order_confirmation(order.user.email, order)

    order.status = 'completed'
    order.save()
```''',
        r'''<think>
Let me analyze this Celery task for processing orders.

First read: it charges a customer, decrements inventory, sends a confirmation email, and marks the order complete. Standard order processing flow.

This is a great example of code that works in the happy path but falls apart in production. Let me think through failure scenarios:

**Idempotency -- the biggest problem:**
If this task is retried (network blip, worker crash, broker redelivery), the customer gets charged AGAIN. Celery guarantees at-least-once delivery, meaning tasks CAN be executed multiple times. There's no check for "did we already charge this order?"

Failure scenario walkthrough:
1. Task runs, charges customer successfully ($50)
2. Worker crashes before `order.save()` with payment_id
3. Celery retries the task
4. Customer is charged AGAIN ($50) -- double charge!

Even if save succeeds, if the worker crashes after inventory decrement but before email, the retry decrements inventory AGAIN.

**No atomicity / compensation:**
The three operations (charge, inventory, email) are not wrapped in any transaction or saga pattern. If inventory decrement fails (out of stock), the customer is already charged but gets no product. There's no rollback of the payment.

**No retry configuration:**
- No `max_retries`
- No `retry_backoff`
- No `acks_late` (task is acknowledged before completion by default)

**Error handling:**
- `Order.objects.get(id=order_id)` raises `DoesNotExist` with no catch
- No exception handling on payment, inventory, or email failures
- A failure in email (non-critical) prevents the order from being marked complete

**Other issues:**
- Instantiating service classes inside the task (should be injected or module-level)
- No logging
- No timeout on external service calls
- `order.user.credit_card` suggests raw card data in the database (PCI violation)

Priority: idempotency and double-charging is the showstopper. Then atomicity/compensation. Then retry config.
</think>

## Code Review

### Critical Issues

**No idempotency -- double charging customers (Severity: Critical)**

Celery provides at-least-once delivery. If a worker crashes after charging the customer but before saving, the retry charges them again. This is not theoretical -- it happens regularly in production under load. Every side-effecting task MUST be idempotent.

**No compensation / saga pattern (Severity: Critical)**

If inventory decrement fails (product out of stock), the customer has already been charged. There is no rollback. The order is stuck in a partially-completed state with money taken but no product fulfilled.

**PCI violation hint**: `order.user.credit_card` suggests raw card numbers in your database. Use a payment token from Stripe/Braintree instead.

### Reliability

- No `acks_late`: task is acknowledged before execution. If the worker dies mid-task, the message is lost.
- No `max_retries` or backoff: infinite retries with no delay will hammer failing services.
- No timeout on external calls: a hung payment gateway blocks the worker forever.
- Email failure (non-critical) prevents order completion (critical).

### Refactored Code

```python
import logging
from celery import Celery
from celery.exceptions import MaxRetriesExceededError
from django.db import transaction
from myapp.models import Order
from myapp.services import PaymentGateway, EmailService, InventoryService

logger = logging.getLogger(__name__)
app = Celery('tasks', broker='redis://localhost:6379/0')

payment_gateway = PaymentGateway()
inventory_service = InventoryService()
email_service = EmailService()


@app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    acks_late=True,                    # acknowledge AFTER completion
    reject_on_worker_lost=True,        # requeue if worker dies
)
def process_order(self, order_id):
    logger.info("Processing order %s (attempt %d)", order_id, self.request.retries + 1)

    try:
        order = Order.objects.get(id=order_id)
    except Order.DoesNotExist:
        logger.error("Order %s not found, not retrying", order_id)
        return  # don't retry -- order doesn't exist

    # ---- STEP 1: Charge (idempotent) ----
    if not order.payment_id:
        try:
            charge = payment_gateway.charge(
                token=order.payment_token,  # use token, not raw card
                amount=order.total,
                idempotency_key=f"order-{order_id}",  # prevents double charge
            )
            order.payment_id = charge.id
            order.save(update_fields=["payment_id"])
        except Exception as exc:
            logger.exception("Payment failed for order %s", order_id)
            raise self.retry(exc=exc)
    else:
        logger.info("Order %s already charged (payment %s)", order_id, order.payment_id)

    # ---- STEP 2: Reserve inventory (idempotent) ----
    if order.status != "inventory_reserved":
        try:
            with transaction.atomic():
                for item in order.items.select_related("product").all():
                    inventory_service.decrement(
                        product_id=item.product_id,
                        quantity=item.quantity,
                        reference=f"order-{order_id}",  # idempotency key
                    )
                order.status = "inventory_reserved"
                order.save(update_fields=["status"])
        except inventory_service.OutOfStockError:
            logger.warning("Out of stock for order %s, initiating refund", order_id)
            _refund_order.delay(order_id)
            return
        except Exception as exc:
            logger.exception("Inventory update failed for order %s", order_id)
            raise self.retry(exc=exc)

    # ---- STEP 3: Mark complete ----
    order.status = "completed"
    order.save(update_fields=["status"])
    logger.info("Order %s completed", order_id)

    # ---- STEP 4: Send email (non-critical, separate task) ----
    send_confirmation_email.delay(order_id)


@app.task(bind=True, max_retries=3, default_retry_delay=120)
def send_confirmation_email(self, order_id):
    """Separate task so email failure doesn't block order completion."""
    try:
        order = Order.objects.select_related("user").get(id=order_id)
        email_service.send_order_confirmation(order.user.email, order)
    except Exception as exc:
        logger.exception("Email failed for order %s", order_id)
        raise self.retry(exc=exc)


@app.task(bind=True, max_retries=5, default_retry_delay=30)
def _refund_order(self, order_id):
    """Compensation task: refund if fulfillment fails."""
    try:
        order = Order.objects.get(id=order_id)
        if order.payment_id:
            payment_gateway.refund(order.payment_id)
            order.status = "refunded"
            order.save(update_fields=["status"])
            logger.info("Refunded order %s", order_id)
    except Exception as exc:
        logger.exception("Refund failed for order %s", order_id)
        raise self.retry(exc=exc)
```

### Key Changes Summary

| Before | After |
|--------|-------|
| No idempotency -- double charges on retry | Idempotency keys on payment + status checkpoints |
| No compensation -- charge taken on inventory failure | Separate refund task on out-of-stock |
| Email failure blocks order completion | Email in separate non-blocking task |
| No retry config | `max_retries`, `acks_late`, `reject_on_worker_lost` |
| No error handling | Per-step exception handling with logging |
| Raw credit card data implied | Payment token reference |
| Task acked before execution | `acks_late=True` -- acked after success |
'''),

    (
        "thinking/code-review",
        r'''Here is some code that works but has issues. Review it and suggest improvements:

```python
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

engine = create_engine("postgresql://app:pass@localhost/mydb")
SessionLocal = sessionmaker(bind=engine)

class UserRepository:
    def __init__(self):
        self.session = SessionLocal()

    def get_user(self, user_id: int):
        return self.session.query(User).filter(User.id == user_id).first()

    def get_users_by_email_domain(self, domain: str):
        return self.session.query(User).filter(
            User.email.like(f"%@{domain}")
        ).all()

    def create_user(self, name: str, email: str):
        user = User(name=name, email=email)
        self.session.add(user)
        self.session.commit()
        return user

    def update_user_name(self, user_id: int, name: str):
        user = self.session.query(User).filter(User.id == user_id).first()
        user.name = name
        self.session.commit()
        return user

    def bulk_deactivate(self, user_ids: list[int]):
        for uid in user_ids:
            user = self.session.query(User).filter(User.id == uid).first()
            if user:
                user.is_active = False
                self.session.commit()

    def search_users(self, query: str):
        sql = text(f"SELECT * FROM users WHERE name LIKE '%{query}%'")
        return self.session.execute(sql).fetchall()
```''',
        r"""<think>
Let me analyze this SQLAlchemy repository class.

First read: a UserRepository that wraps SQLAlchemy session operations. Creates a session in __init__ and uses it for all operations.

**Session management -- the core architectural problem:**
The session is created in `__init__` and never closed. This is a session leak. Every time a `UserRepository` is instantiated, a database connection is taken from the pool and never returned. In a web application creating a repository per request, you'll exhaust the connection pool quickly.

Even worse: if the session encounters an error (integrity constraint, connection drop), it becomes invalidated. But since it's stored as instance state, all subsequent operations on that repository instance will fail too.

**SQL injection in search_users:**
`f"SELECT * FROM users WHERE name LIKE '%{query}%'"` -- wrapping it in `text()` doesn't make it safe. The f-string interpolation happens before `text()` sees it. Classic SQL injection.

**Bugs:**
- `update_user_name`: if user_id doesn't exist, `.first()` returns `None`, then `user.name = name` raises `AttributeError`. No null check.
- `bulk_deactivate`: commits inside the loop -- if it fails on user #50 of 100, the first 49 are deactivated but the rest aren't. Should be atomic.
- `bulk_deactivate`: N+1 queries. Loads each user individually instead of a bulk UPDATE.

**Performance:**
- `bulk_deactivate` with individual queries + commits is O(n) queries and O(n) commits. Should be a single UPDATE statement.
- `get_users_by_email_domain` with `LIKE '%@domain'` -- leading wildcard prevents index use.

**Other:**
- Hardcoded database URL
- No transaction management / rollback on error
- `self.session.commit()` in every method means the caller has no control over transaction boundaries

Priority: session leak is the production killer. SQL injection is the security killer. Then the transaction handling.
</think>

## Code Review

### Critical Issues

**Session leak (Severity: Critical)**

The session is created in `__init__` and **never closed**. Each `UserRepository()` instance grabs a database connection from the pool. In a web framework creating one per request, you will exhaust the connection pool within minutes under load, causing the entire application to hang waiting for connections.

```python
# This connection is NEVER returned to the pool
self.session = SessionLocal()
```

**SQL injection in `search_users` (Severity: Critical)**

```python
sql = text(f"SELECT * FROM users WHERE name LIKE '%{query}%'")
```

The `text()` function does not sanitize -- the f-string interpolates before `text()` is called. An attacker can pass `' OR 1=1; DROP TABLE users; --` as the query.

**`update_user_name` crashes on missing user (Severity: Medium)**

`.first()` returns `None` when no match is found. The next line `user.name = name` raises `AttributeError: 'NoneType' object has no attribute 'name'`. This gives the caller an unhelpful traceback instead of a clear "user not found" error.

### Performance

**`bulk_deactivate` is O(n) queries with O(n) commits:**
- Loads each user one at a time (N queries)
- Commits after each one (N disk flushes)
- For 10,000 users, this takes minutes instead of milliseconds
- Not atomic: a failure partway through leaves data half-updated

### Transaction Design

Every method calls `self.session.commit()` independently. The caller has no ability to group operations into a transaction. If you need to create a user AND assign them to a team atomically, you cannot -- each operation commits separately.

### Refactored Code

```python
from contextlib import contextmanager
from typing import Optional
import os

from sqlalchemy import create_engine, update
from sqlalchemy.orm import sessionmaker, Session

engine = create_engine(
    os.environ["DATABASE_URL"],
    pool_size=10,
    pool_pre_ping=True,  # detect stale connections
)
SessionLocal = sessionmaker(bind=engine)


@contextmanager
def get_session():
    '''Session lifecycle managed by context manager -- no leaks possible.'''
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()  # ALWAYS returns connection to pool


class UserRepository:
    def __init__(self, session: Session):
        '''Session is injected, not owned. Caller controls lifecycle.'''
        self.session = session

    def get_user(self, user_id: int) -> Optional[User]:
        return self.session.query(User).filter(User.id == user_id).first()

    def get_users_by_email_domain(self, domain: str) -> list[User]:
        return self.session.query(User).filter(
            User.email.ilike(f"%@{domain}")  # ilike for case-insensitive
        ).all()

    def create_user(self, name: str, email: str) -> User:
        user = User(name=name, email=email)
        self.session.add(user)
        self.session.flush()  # flush, don't commit -- let caller control tx
        return user

    def update_user_name(self, user_id: int, name: str) -> Optional[User]:
        user = self.get_user(user_id)
        if user is None:
            return None  # caller decides how to handle missing user
        user.name = name
        self.session.flush()
        return user

    def bulk_deactivate(self, user_ids: list[int]) -> int:
        '''Single UPDATE statement -- O(1) instead of O(n).'''
        if not user_ids:
            return 0
        result = self.session.execute(
            update(User)
            .where(User.id.in_(user_ids))
            .values(is_active=False)
        )
        self.session.flush()
        return result.rowcount

    def search_users(self, query: str) -> list[User]:
        '''Use ORM with parameterized query -- no SQL injection possible.'''
        return self.session.query(User).filter(
            User.name.ilike(f"%{query}%")
        ).limit(100).all()  # limit prevents unbounded result sets


# Usage:
# with get_session() as session:
#     repo = UserRepository(session)
#     user = repo.create_user("Alice", "alice@example.com")
#     repo.update_user_name(user.id, "Alice Smith")
#     # both operations commit together when context exits
```

### Key Changes Summary

| Before | After |
|--------|-------|
| Session created in `__init__`, never closed | Session injected, lifecycle managed by `get_session()` context manager |
| Raw SQL with f-string interpolation | ORM query with parameterized `.ilike()` |
| `commit()` in every method | `flush()` only -- caller controls transaction boundary |
| `bulk_deactivate`: N queries + N commits | Single `UPDATE ... WHERE id IN (...)` |
| `update_user_name` crashes on None | Returns `None`, caller decides |
| No rollback on error | Context manager rolls back on exception |
| Hardcoded database URL | `os.environ["DATABASE_URL"]` |
| No connection pool config | `pool_size`, `pool_pre_ping` configured |
"""),
]
