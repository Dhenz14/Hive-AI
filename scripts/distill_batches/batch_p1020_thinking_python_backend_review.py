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
Okay, let me look at this FastAPI search endpoint carefully. My first instinct is to check how the query is built... and immediately I see f-string interpolation everywhere. That's a red flag.

Let me trace through what happens with malicious input. If someone passes `name = "'; DROP TABLE users; --"`, that gets interpolated directly into the LIKE clause. So yeah, textbook SQL injection. But wait, it's not just the name -- role has the same issue. And sort_by... hmm, sort_by is even worse because it goes into the ORDER BY clause without any quotes. An attacker could pass something like `(SELECT password FROM users LIMIT 1)` as the sort column and potentially extract data. The order parameter is the same -- no validation that it's actually "asc" or "desc".

I initially thought limit and offset might be safe since FastAPI types them as int, but the real danger is the string parameters. Still, even with int typing, the pattern of string interpolation is dangerous as a habit.

Now let me look at the pagination logic. The endpoint returns `"total": len(rows)` -- but wait, that's just the count of the current page, not the total matching records. If there are 10,000 users matching the filter and you request limit=50, the client gets `total: 50` and thinks there are only 50 results. The pagination is fundamentally broken without a separate COUNT(*) query.

What about performance? The LIKE clause uses `'%{name}%'` with a leading wildcard. That means PostgreSQL cannot use a B-tree index -- it has to do a full sequential scan on every search. For a small table that's fine, but with millions of users this endpoint will be painfully slow. They should be using pg_trgm with a GIN index, or full-text search with tsvector.

Let me also check for other issues I might have missed... the database URL has credentials hardcoded right in the source code -- that will end up in version control. The `on_event("startup")` pattern is deprecated in newer FastAPI versions. There's no connection pool configuration, no error handling at all, and the response lacks proper pagination metadata like has_next or total_pages.

Actually, let me reconsider the priority here. The SQL injection is the most critical because it's an active security vulnerability. The broken pagination is a functionality bug. The performance issue with LIKE will only matter at scale. So the fix order should be: (1) parameterize all queries, (2) fix the total count, (3) add sort_by validation against an allowlist, (4) address the other issues.
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
Hmm, looking at this Django dashboard view... the first thing that jumps out is the nested loop structure. Let me count the queries to see how bad it is.

There's 1 query to get the orders (up to 20). Then for each order, there's a query to get items -- that's up to 20 more. And then for each item, there's a `Product.objects.get()` to fetch the product. If each order has maybe 5 items on average, that's 100 product queries. So we're looking at roughly 1 + 20 + 100 = 121 database queries for a single page load. That's the classic N+1 problem, but actually it's N+1 nested two levels deep, making it even worse.

Wait, but is the query count the only issue? Let me look more carefully at the product fetch... `Product.objects.get(id=item.product_id)` -- what happens if a product was deleted? That raises `Product.DoesNotExist`, which bubbles up as a 500 error. So a user's entire dashboard crashes because one historical product was removed from the catalog. That's really bad for a user-facing page.

Actually, there's something more subtle I almost missed. The subtotal calculation uses `product.price` -- the current price. But this is an order dashboard showing historical orders. If a product's price changed from $10 to $15 last month, all the old orders now show the new price. The totals are wrong retroactively. This is a data modeling bug -- the OrderItem should store `price_at_purchase` so historical orders remain accurate.

Let me think about what Django gives us to fix the query problem. `select_related` can handle the author FK in one go, and `prefetch_related('items__product')` would eagerly load both the items and their products in just 2-3 queries total instead of 121. For the comment count, we could use `annotate(Count(...))` and let the database handle the aggregation rather than computing totals in Python.

So the priority should be: (1) fix the N+1 queries with prefetch_related -- that's the performance killer, (2) add price_at_purchase to OrderItem -- that's a correctness issue that affects every historical order, (3) handle the DoesNotExist case gracefully -- maybe use SET_NULL on the product FK so deleted products don't crash the page.
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
Alright, let me look at this Flask auth middleware. API key authentication with role-based decorators. My first thought is to check how the keys are stored and compared.

The keys are right there in the source code as a dict literal. That's immediately a problem -- these will end up in version control, visible to anyone with repo access. But let me think about whether there's a more subtle issue first...

The comparison `if api_key in API_KEYS` uses Python dict lookup. I initially thought this was a timing attack vector, but wait -- dict lookup hashes the key first and checks the bucket, which is roughly constant time for the hash step. However, after the hash matches a bucket, Python does a full string equality check, and that comparison short-circuits on the first differing byte. In practice, exploiting this on a dict is very difficult because you'd need hash collisions, but the principle is still wrong for secret comparison. We should use `hmac.compare_digest` for constant-time comparison.

Actually, let me reconsider the priority here. The timing attack is hard to exploit in practice. The much bigger problem is that the keys are plaintext in source code. Even if we moved them to a database, they should be stored as hashes -- just like passwords. An attacker who gets database access shouldn't be able to recover the actual API keys.

Now let me look at the decorator design. The `require_role` decorator accesses `g.current_user`, but there's no check that it actually exists. If a developer accidentally puts `@require_role("admin")` before `@require_auth` in the decorator stack, it crashes with an AttributeError instead of returning a clean 401. That's fragile -- a new team member could easily make this mistake.

Hmm, I also notice there's no rate limiting at all. An attacker can make unlimited authentication attempts. And with the key format being `key_abc123_example`, the prefix pattern is known, which reduces the brute-force search space. There's also no logging of failed auth attempts, so you'd never detect a brute-force attack in progress.

One more thing -- the `/admin/users` endpoint returns `list(API_KEYS.values())`, which currently just has user_id and role. But if someone later adds the key itself to the dict values, they'd accidentally leak all API keys through this endpoint. The response should explicitly select only safe fields.

So my priority ranking: (1) get keys out of source code and hash them, (2) use constant-time comparison on the hashed values, (3) add rate limiting and failure logging, (4) make the decorator ordering defensive.
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
Let me trace through what happens with this Celery task in different scenarios. The happy path is straightforward: charge customer, decrement inventory, send email, mark complete. But what about failure cases?

First, I need to think about Celery's delivery guarantees. Celery provides at-least-once delivery by default, meaning tasks CAN be executed more than once. So let me walk through a crash scenario:

1. Task runs, payment.charge() succeeds -- customer is charged $50
2. Worker crashes before order.save() with the payment_id
3. Celery retries the task
4. payment.charge() runs AGAIN -- customer is now charged $100

That's a double charge. This is not theoretical -- it happens regularly in production when workers restart under load or during deploys. The task has zero idempotency protection. There's no check like "if order.payment_id already exists, skip the charge."

But wait, the problem goes deeper than just the payment. Even if the payment save succeeds, what if the worker crashes after the inventory decrement but before the email? On retry, the inventory gets decremented again. Now the stock count is wrong.

Let me think about what happens when things fail in order. If the payment succeeds but inventory.decrement() raises an exception (say, out of stock), the customer has already been charged. There's no rollback, no refund task, no compensation logic at all. The order is stuck in a half-complete state: money taken, no product shipped.

Actually, I should also note that the email send is bundled into the same task as payment and inventory. Email is non-critical -- if the SMTP server is down, should that really prevent the order from being marked complete? It shouldn't. The email should be a separate task entirely.

Hmm, and looking at `order.user.credit_card` -- that implies raw credit card numbers in the database. That's a PCI compliance violation. They should be using a payment token from Stripe or similar.

What about the retry configuration? There's no `max_retries`, no `retry_backoff`, and the default `acks_late=False` means the task is acknowledged before it even starts executing. If the worker dies mid-task, the message is gone from the queue forever.

So the fix priority should be: (1) add idempotency keys to payment and status checkpoints for each step, (2) implement compensation -- a refund task that fires when inventory fails, (3) split email into its own non-blocking task, (4) configure proper retry behavior with acks_late=True.
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
Okay, let me look at this SQLAlchemy repository class. The first thing I notice is the session created in `__init__`... and I'm scanning for where it gets closed... and I don't see a close() anywhere. That's a session leak.

Let me think about what that means in practice. Every time someone creates a `UserRepository()`, it grabs a connection from the pool. In a web app where you create one per request, after pool_size requests (default is 5 for SQLAlchemy), the pool is exhausted. The next request blocks waiting for a connection, and eventually times out. The app appears to hang for no obvious reason.

But there's an even worse consequence I almost missed: if the session hits an error -- say an IntegrityError on create_user -- the session becomes invalidated. Since it's stored as instance state and never rolled back, all subsequent operations on that same repository instance will fail with "this session is in a rollback state" errors.

Now let me check for security issues... the search_users method uses `text(f"SELECT * FROM users WHERE name LIKE '%{query}%'")`. Wait, does `text()` handle the parameterization? No -- the f-string interpolation happens BEFORE `text()` is called. By the time text() sees the string, the user input is already baked in. This is SQL injection despite the apparent use of SQLAlchemy's text() function. Someone might look at this and think "it uses text(), so it must be safe" -- but that's wrong.

Let me look at the individual methods for bugs. In `update_user_name`, `.first()` returns None if the user doesn't exist, and then `user.name = name` raises AttributeError. No null check.

The `bulk_deactivate` method has multiple problems. First, it commits inside the loop -- so if it fails on user #50 of 100, the first 49 are deactivated but the rest aren't. That's not atomic. Second, it loads each user one at a time with individual queries -- that's O(n) queries when a single `UPDATE users SET is_active=False WHERE id IN (...)` would do it in one query.

Actually, let me reconsider the transaction design more broadly. Every single method calls `self.session.commit()`. This means the caller has zero control over transaction boundaries. If you need to create a user AND update their profile atomically, you can't -- each operation commits independently. The session should use flush() instead and let the caller control when to commit.

Priority order for fixes: (1) session lifecycle management -- use a context manager or dependency injection, (2) SQL injection in search_users, (3) transaction boundary control -- flush instead of commit, (4) the bulk_deactivate rewrite to a single UPDATE.
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
