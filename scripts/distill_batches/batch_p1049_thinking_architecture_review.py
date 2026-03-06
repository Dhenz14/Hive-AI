r"""Thinking-trace pairs: architecture code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this layered architecture and identify violations:

```python
# controllers/user_controller.py
from flask import request, jsonify
from models.user import User
from database import db
import bcrypt
import redis
import jwt

redis_client = redis.Redis()

class UserController:
    def register(self):
        data = request.get_json()

        if len(data.get("password", "")) < 8:
            return jsonify({"error": "Password too short"}), 400

        existing = db.session.query(User).filter_by(email=data["email"]).first()
        if existing:
            return jsonify({"error": "Email taken"}), 409

        hashed = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt())
        user = User(
            username=data["username"],
            email=data["email"],
            password_hash=hashed.decode()
        )
        db.session.add(user)
        db.session.commit()

        redis_client.delete("user_list")
        redis_client.delete("user_count")

        token = jwt.encode(
            {"user_id": user.id},
            "secret-key",
            algorithm="HS256"
        )

        return jsonify({"token": token, "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email
        }}), 201

    def get_profile(self, user_id):
        cache_key = f"user:{user_id}"
        cached = redis_client.get(cache_key)
        if cached:
            return jsonify(json.loads(cached))

        user = db.session.query(User).get(user_id)
        if not user:
            return jsonify({"error": "Not found"}), 404

        orders_count = db.session.execute(
            "SELECT COUNT(*) FROM orders WHERE user_id = :uid",
            {"uid": user_id}
        ).scalar()

        profile = {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "orders_count": orders_count,
            "is_premium": orders_count > 10 or user.total_spent > 1000
        }

        redis_client.setex(cache_key, 300, json.dumps(profile))
        return jsonify(profile)

    def update_preferences(self, user_id):
        data = request.get_json()
        user = db.session.query(User).get(user_id)

        if data.get("theme") not in ["light", "dark", "auto"]:
            return jsonify({"error": "Invalid theme"}), 400
        if data.get("language") not in ["en", "es", "fr", "de"]:
            return jsonify({"error": "Invalid language"}), 400

        user.theme = data["theme"]
        user.language = data["language"]
        user.notifications_enabled = data.get("notifications", True)
        db.session.commit()

        redis_client.delete(f"user:{user_id}")

        return jsonify({"status": "updated"})
```''', r'''<think>
This code has severe layered architecture violations. In a proper layered architecture (Controller -> Service -> Repository -> Database), each layer should only communicate with the layer directly below it. Let me identify the violations.

Layer violations:
1. Controller directly accesses the database (db.session.query, db.session.commit). The controller should call a service layer which calls a repository.
2. Controller directly accesses Redis cache. Caching is an infrastructure concern that belongs in the repository or service layer.
3. Controller contains business logic:
   - Password validation (len >= 8)
   - Premium status calculation (orders_count > 10 or total_spent > 1000)
   - Theme/language validation
4. Controller directly uses bcrypt for password hashing - this is service-layer responsibility.
5. Controller creates JWT tokens - this is an auth service responsibility.
6. Controller performs raw SQL queries (SELECT COUNT(*) FROM orders) - this belongs in a repository.

Additional issues:
- Hardcoded "secret-key" for JWT
- No service layer at all
- No repository layer
- Business rule (is_premium) is calculated in the controller, not encapsulated in the domain model
- Cache invalidation mixed with request handling
- Raw SQL mixed with ORM queries
- No error handling for database operations
- User serialization (to_dict) done manually inline

Proper structure:
```
Controller -> validates HTTP input, calls service, returns HTTP response
Service -> implements business logic, orchestrates repositories
Repository -> data access, caching
Model -> domain objects with business methods
```
</think>

## Code Review: Layered Architecture Violations

### CRITICAL - Controller Directly Accesses Database
The controller layer uses `db.session.query`, `db.session.add`, `db.session.commit`, and raw SQL queries. In a layered architecture, controllers should only handle HTTP concerns (request parsing, response formatting). Data access belongs in a repository layer.

**Fix:** Introduce a repository and service layer:
```python
# repositories/user_repository.py
class UserRepository:
    def __init__(self, db_session):
        self.session = db_session

    def find_by_email(self, email):
        return self.session.query(User).filter_by(email=email).first()

    def find_by_id(self, user_id):
        return self.session.query(User).get(user_id)

    def create(self, user):
        self.session.add(user)
        self.session.commit()
        return user

    def get_order_count(self, user_id):
        return self.session.query(Order).filter_by(user_id=user_id).count()
```

### CRITICAL - Business Logic in Controller
The controller contains business rules:
- Password validation (`len >= 8`)
- Premium status calculation (`orders_count > 10 or total_spent > 1000`)
- Theme/language validation

These rules belong in a service or domain model layer. If the premium threshold changes, a developer must modify a controller -- the wrong place.

**Fix:**
```python
# services/user_service.py
class UserService:
    def __init__(self, user_repo, auth_service, cache):
        self.repo = user_repo
        self.auth = auth_service
        self.cache = cache

    def register(self, username, email, password):
        self._validate_registration(username, email, password)
        password_hash = self.auth.hash_password(password)
        user = User(username=username, email=email, password_hash=password_hash)
        self.repo.create(user)
        self.cache.invalidate_user_lists()
        token = self.auth.create_token(user.id)
        return user, token

# models/user.py
class User:
    @property
    def is_premium(self):
        return self.order_count > 10 or self.total_spent > 1000
```

### HIGH - Controller Manages Cache Directly
Redis operations (`redis_client.get`, `redis_client.setex`, `redis_client.delete`) are scattered throughout the controller. Caching is an infrastructure concern that should be transparent to the controller.

**Fix:** Implement caching in the repository or service layer:
```python
class CachedUserRepository(UserRepository):
    def __init__(self, db_session, cache):
        super().__init__(db_session)
        self.cache = cache

    def find_by_id(self, user_id):
        cache_key = f"user:{user_id}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached
        user = super().find_by_id(user_id)
        if user:
            self.cache.set(cache_key, user.to_dict(), ttl=300)
        return user
```

### HIGH - Controller Creates JWT Tokens
Token creation with a hardcoded secret key is in the controller. Authentication and token management belong in a dedicated auth service.

**Fix:**
```python
# services/auth_service.py
class AuthService:
    def __init__(self, secret_key):
        self.secret_key = secret_key

    def hash_password(self, password):
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def create_token(self, user_id):
        return jwt.encode(
            {"user_id": user_id, "exp": time.time() + 3600},
            self.secret_key, algorithm="HS256"
        )
```

### MEDIUM - Mixed ORM and Raw SQL
`get_profile` uses the ORM for user lookup (`User.query.get`) but raw SQL for order count (`SELECT COUNT(*)`). This inconsistency suggests ad-hoc queries being added without going through proper repository methods.

### MEDIUM - Validation Rules Hardcoded
Theme options (`["light", "dark", "auto"]`) and language options (`["en", "es", "fr", "de"]`) are hardcoded in the controller. These should be configurable constants or database-driven.

**Refactored controller (thin layer):**
```python
class UserController:
    def __init__(self, user_service):
        self.service = user_service

    def register(self):
        data = request.get_json()
        try:
            user, token = self.service.register(
                data["username"], data["email"], data["password"]
            )
            return jsonify({"token": token, "user": user.to_dict()}), 201
        except ValidationError as e:
            return jsonify({"error": str(e)}), 400
        except DuplicateEmailError:
            return jsonify({"error": "Email taken"}), 409
```'''),

    ("thinking/code-review", r'''Review this service boundary design and identify issues:

```python
# services/order_service.py
class OrderService:
    def __init__(self, db):
        self.db = db

    def create_order(self, user_id, items):
        user = self.db.query("SELECT * FROM users WHERE id = %s", (user_id,))
        if not user:
            raise ValueError("User not found")

        if not user["email_verified"]:
            raise ValueError("Email not verified")

        if user["account_status"] == "suspended":
            raise ValueError("Account suspended")

        total = 0
        order_items = []
        for item in items:
            product = self.db.query(
                "SELECT * FROM products WHERE id = %s", (item["product_id"],)
            )
            if not product:
                raise ValueError(f"Product {item['product_id']} not found")

            if product["stock"] < item["quantity"]:
                raise ValueError(f"Insufficient stock for {product['name']}")

            price = product["price"]
            if user["tier"] == "premium":
                price *= 0.9
            elif user["tier"] == "vip":
                price *= 0.85

            line_total = price * item["quantity"]
            total += line_total

            order_items.append({
                "product_id": product["id"],
                "quantity": item["quantity"],
                "unit_price": price,
                "line_total": line_total
            })

            self.db.execute(
                "UPDATE products SET stock = stock - %s WHERE id = %s",
                (item["quantity"], product["id"])
            )

        tax = self._calculate_tax(user, total)
        shipping = self._calculate_shipping(user, order_items)

        order_id = self.db.execute(
            "INSERT INTO orders (user_id, subtotal, tax, shipping, total, status) "
            "VALUES (%s, %s, %s, %s, %s, 'pending') RETURNING id",
            (user_id, total, tax, shipping, total + tax + shipping)
        )

        for item in order_items:
            self.db.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, unit_price, line_total) "
                "VALUES (%s, %s, %s, %s, %s)",
                (order_id, item["product_id"], item["quantity"],
                 item["unit_price"], item["line_total"])
            )

        self.db.commit()

        self._send_confirmation_email(user, order_id, order_items, total, tax, shipping)
        self._update_analytics(user_id, order_id, total)
        self._check_loyalty_rewards(user_id, total)

        return order_id

    def _calculate_tax(self, user, total):
        state = self.db.query(
            "SELECT state FROM addresses WHERE user_id = %s AND is_default = true",
            (user["id"],)
        )
        tax_rate = self.db.query(
            "SELECT rate FROM tax_rates WHERE state = %s", (state,)
        )
        return total * (tax_rate or 0)

    def _calculate_shipping(self, user, items):
        total_weight = sum(
            self.db.query(
                "SELECT weight FROM products WHERE id = %s", (i["product_id"],)
            ) * i["quantity"]
            for i in items
        )
        return self.db.query(
            "SELECT calculate_shipping(%s, %s)",
            (user["id"], total_weight)
        )

    def _send_confirmation_email(self, user, order_id, items, subtotal, tax, shipping):
        import smtplib
        # ... email sending code

    def _update_analytics(self, user_id, order_id, total):
        self.db.execute(
            "UPDATE user_stats SET total_orders = total_orders + 1, "
            "total_spent = total_spent + %s WHERE user_id = %s",
            (total, user_id)
        )

    def _check_loyalty_rewards(self, user_id, total):
        stats = self.db.query(
            "SELECT total_spent FROM user_stats WHERE user_id = %s", (user_id,)
        )
        if stats["total_spent"] > 5000:
            self.db.execute(
                "UPDATE users SET tier = 'vip' WHERE id = %s", (user_id,)
            )
        elif stats["total_spent"] > 1000:
            self.db.execute(
                "UPDATE users SET tier = 'premium' WHERE id = %s", (user_id,)
            )
```''', r'''<think>
This "service" has massive service boundary problems. Let me identify the architectural issues.

Bounded context violations:
1. OrderService directly queries and modifies users (email_verified, account_status, tier). User management belongs to a UserService/User domain.
2. OrderService directly modifies product stock. Inventory management belongs to an InventoryService.
3. OrderService queries addresses and tax rates. Tax calculation is its own domain.
4. OrderService queries product weights for shipping. Shipping calculation is its own domain.
5. OrderService updates user_stats. Analytics belongs to its own service.
6. OrderService modifies user tier based on spending. Loyalty/rewards is its own domain.
7. OrderService sends emails. Notifications belong to their own service.

The OrderService is a "god service" that reaches into every domain. Changes to user accounts, inventory, tax rates, shipping, analytics, or loyalty all require modifying OrderService.

Transaction issues:
- Stock is decremented inside the loop before the order is committed. If the order creation fails after decrementing stock, the stock is permanently reduced without a corresponding order.
- Actually, everything happens within a single db.commit() call, but the stock UPDATE and order INSERT are separate statements. If the commit fails, the stock changes should roll back (if using a proper transaction). But the email, analytics, and loyalty operations happen after commit, so they might fail independently.

N+1 queries:
- Each item triggers a product lookup, a stock update, and another product lookup for weight calculation. With 10 items, that's 30+ queries.

Data access:
- All data access is through raw SQL strings passed to self.db. No repository pattern, no ORM, no type safety.

The proper approach:
1. OrderService should only handle order creation logic
2. It should call InventoryService.reserve_stock()
3. It should call PricingService.calculate_price()
4. It should call TaxService.calculate_tax()
5. It should call ShippingService.calculate_shipping()
6. Post-order events (email, analytics, loyalty) should be handled via events/messages
</think>

## Code Review: Service Boundary Design

### CRITICAL - God Service Crosses All Domain Boundaries
`OrderService` directly queries and modifies data belonging to at least 6 other domains: users, products/inventory, addresses, tax rates, analytics/stats, and loyalty tiers. Any change to user accounts, inventory, tax rules, or loyalty programs requires modifying the order service.

**Fix:** Define clear service boundaries:
```python
class OrderService:
    def __init__(self, user_service, inventory_service, pricing_service,
                 tax_service, shipping_service, event_bus):
        self.users = user_service
        self.inventory = inventory_service
        self.pricing = pricing_service
        self.tax = tax_service
        self.shipping = shipping_service
        self.events = event_bus

    def create_order(self, user_id, items):
        user = self.users.get_verified_user(user_id)
        priced_items = self.pricing.price_items(items, user.tier)
        self.inventory.reserve_stock(priced_items)
        subtotal = sum(item.line_total for item in priced_items)
        tax = self.tax.calculate(user_id, subtotal)
        shipping = self.shipping.calculate(user_id, priced_items)
        order = self._persist_order(user_id, priced_items, subtotal, tax, shipping)
        self.events.publish("order.created", order)
        return order
```

### CRITICAL - Stock Decrement Before Order Creation
Stock is decremented in the item loop via individual UPDATE statements, then the order INSERT happens later, then `db.commit()` is called. If the order INSERT fails (constraint violation, connection drop), the stock decrements may or may not roll back depending on transaction configuration. This can lead to phantom stock reductions.

**Fix:** Either use a reservation pattern (reserve stock, create order, confirm reservation) or ensure everything is in a single transaction with proper rollback:
```python
def create_order(self, user_id, items):
    try:
        # All operations in one transaction
        order_id = self._create_order_record(...)
        self._create_order_items(order_id, ...)
        self._decrement_stock(items)
        self.db.commit()
    except Exception:
        self.db.rollback()
        raise
```

### HIGH - User Domain Logic in Order Service
The order service checks `user["email_verified"]`, `user["account_status"]`, and applies tier-based pricing (`user["tier"] == "premium"`). These are user domain concerns. The order service should ask the user service whether the user is eligible to place orders, not inspect user attributes directly.

**Fix:**
```python
class UserService:
    def get_verified_user(self, user_id):
        user = self.repo.find_by_id(user_id)
        if not user:
            raise UserNotFoundError()
        if not user.email_verified:
            raise UnverifiedEmailError()
        if user.account_status == "suspended":
            raise AccountSuspendedError()
        return user
```

### HIGH - Loyalty Tier Updates in Order Service
`_check_loyalty_rewards` modifies user tiers based on spending thresholds. This is loyalty program logic that belongs in a dedicated LoyaltyService. When tier thresholds change, the order service should not need modification.

**Fix:** Publish an event and let the loyalty service handle it:
```python
# LoyaltyService subscribes to "order.created" events
class LoyaltyService:
    def on_order_created(self, event):
        total_spent = self.stats_repo.get_total_spent(event.user_id)
        new_tier = self._determine_tier(total_spent)
        if new_tier != event.user.tier:
            self.user_repo.update_tier(event.user_id, new_tier)
```

### HIGH - N+1 Query Pattern
Each order item triggers individual product queries for pricing, stock updates, and weight calculations. 10 items = 30+ database queries.

**Fix:** Batch-fetch all products at once:
```python
product_ids = [item["product_id"] for item in items]
products = self.inventory.get_products(product_ids)
```

### MEDIUM - Side Effects After Commit Are Not Transactional
Email, analytics, and loyalty updates happen after `db.commit()`. If any fails, the order exists but downstream effects are incomplete. Use an event/message queue for eventual consistency.

### MEDIUM - All Data Access via Raw SQL
No repository pattern, no ORM, no type safety. SQL strings are scattered throughout business logic, making it fragile and hard to maintain.'''),

    ("thinking/code-review", r'''Review this API gateway and service mesh code:

```python
import requests
import time
import json
import logging
from functools import wraps
from flask import Flask, request, jsonify, g

app = Flask(__name__)
logger = logging.getLogger(__name__)

SERVICES = {
    "user-service": "http://localhost:8001",
    "product-service": "http://localhost:8002",
    "order-service": "http://localhost:8003",
    "payment-service": "http://localhost:8004",
    "notification-service": "http://localhost:8005",
}

def proxy_request(service_name, path, method="GET", data=None, headers=None):
    base_url = SERVICES.get(service_name)
    if not base_url:
        return {"error": f"Unknown service: {service_name}"}, 500

    url = f"{base_url}{path}"
    try:
        response = requests.request(
            method=method,
            url=url,
            json=data,
            headers=headers,
            timeout=30
        )
        return response.json(), response.status_code
    except requests.Timeout:
        return {"error": "Service timeout"}, 504
    except Exception as e:
        return {"error": str(e)}, 502

@app.before_request
def before_request():
    g.start_time = time.time()
    g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

@app.after_request
def after_request(response):
    duration = time.time() - g.start_time
    logger.info(f"{request.method} {request.path} {response.status_code} {duration:.3f}s")
    response.headers["X-Request-ID"] = g.request_id
    return response

@app.route("/api/users/<int:user_id>")
def get_user(user_id):
    return proxy_request("user-service", f"/users/{user_id}")

@app.route("/api/users/<int:user_id>/orders")
def get_user_orders(user_id):
    user_data, status = proxy_request("user-service", f"/users/{user_id}")
    if status != 200:
        return jsonify(user_data), status

    orders_data, status = proxy_request("order-service", f"/orders?user_id={user_id}")
    if status != 200:
        return jsonify(orders_data), status

    for order in orders_data:
        items = []
        for item in order.get("items", []):
            product, _ = proxy_request(
                "product-service", f"/products/{item['product_id']}"
            )
            item["product"] = product
            items.append(item)
        order["items"] = items

    return jsonify({"user": user_data, "orders": orders_data})

@app.route("/api/checkout", methods=["POST"])
def checkout():
    data = request.get_json()
    user_id = data["user_id"]
    items = data["items"]

    user, status = proxy_request("user-service", f"/users/{user_id}")
    if status != 200:
        return jsonify({"error": "User not found"}), 404

    for item in items:
        product, status = proxy_request(
            "product-service", f"/products/{item['product_id']}"
        )
        if status != 200:
            return jsonify({"error": f"Product {item['product_id']} not found"}), 404
        if product["stock"] < item["quantity"]:
            return jsonify({"error": f"Insufficient stock for {product['name']}"}), 400

    order, status = proxy_request(
        "order-service", "/orders",
        method="POST",
        data={"user_id": user_id, "items": items}
    )
    if status != 201:
        return jsonify({"error": "Order creation failed"}), 500

    payment, status = proxy_request(
        "payment-service", "/payments",
        method="POST",
        data={"order_id": order["id"], "amount": order["total"]}
    )
    if status != 200:
        proxy_request(
            "order-service", f"/orders/{order['id']}/cancel",
            method="POST"
        )
        return jsonify({"error": "Payment failed"}), 402

    proxy_request(
        "notification-service", "/notifications",
        method="POST",
        data={"user_id": user_id, "type": "order_confirmation", "order_id": order["id"]}
    )

    return jsonify(order), 201
```''', r'''<think>
This API gateway has significant architectural and reliability issues. Let me analyze them.

Service discovery:
- Hardcoded service URLs. In a production environment, services move, scale, and restart. Hardcoded URLs do not support service discovery, load balancing, or multiple instances.

N+1 API calls:
- get_user_orders fetches the user, then orders, then loops through each order's items and fetches each product individually. With 5 orders and 3 items each, that is 2 + 15 = 17 HTTP calls. This is the N+1 problem at the API gateway level.

Checkout saga:
- The checkout endpoint performs a multi-step process (validate user, validate products, create order, process payment, send notification) with compensating actions only for payment failure. What if:
  - The order is created but notification fails? The order exists but the user is not notified.
  - Stock check passes but stock changes between the check and order creation? Race condition.
  - Payment succeeds but the cancel request fails? The order is paid but marked for cancellation.

Reliability:
- No retry logic on failed requests
- No circuit breaker for failing services
- 30-second timeout is very long. If all services are slow, the gateway blocks threads for 30 seconds each.
- No rate limiting
- No request/response caching
- proxy_request exposes internal error messages to clients (str(e))

Security:
- No authentication at the gateway level
- Internal service headers are forwarded without filtering
- No request body size limit
- Error messages from downstream services are returned directly (information leakage)

Missing:
- No health checks on downstream services
- No load balancing across service instances
- No request tracing propagation (the X-Request-ID is set but not forwarded to downstream services)
- No response caching for GET requests
</think>

## Code Review: API Gateway and Service Communication

### CRITICAL - Hardcoded Service URLs (No Service Discovery)
`SERVICES` uses hardcoded localhost URLs. In production with container orchestration (Kubernetes, ECS), service instances have dynamic IPs and ports. Adding a service instance or restarting one requires code changes and redeployment.

**Fix:** Use service discovery:
```python
# Kubernetes: use service DNS names
SERVICES = {
    "user-service": os.environ.get("USER_SERVICE_URL", "http://user-service:8001"),
    "product-service": os.environ.get("PRODUCT_SERVICE_URL", "http://product-service:8002"),
}
# Or use a service registry like Consul
```

### CRITICAL - N+1 API Calls in get_user_orders
The endpoint makes 1 user request + 1 orders request + N product requests (one per item across all orders). With 5 orders and 3 items each, this is 17 synchronous HTTP calls. Response time is the sum of all call latencies.

**Fix:** Add batch endpoints to downstream services and fetch in parallel:
```python
@app.route("/api/users/<int:user_id>/orders")
def get_user_orders(user_id):
    # Parallel fetch user and orders
    import asyncio
    user_future = fetch_async("user-service", f"/users/{user_id}")
    orders_future = fetch_async("order-service", f"/orders?user_id={user_id}")
    user_data, orders_data = await asyncio.gather(user_future, orders_future)

    # Batch fetch all products
    product_ids = set()
    for order in orders_data:
        for item in order.get("items", []):
            product_ids.add(item["product_id"])

    products, _ = proxy_request(
        "product-service",
        f"/products?ids={','.join(str(id) for id in product_ids)}"
    )
    product_map = {p["id"]: p for p in products}
    # Enrich items with product data
```

### CRITICAL - Incomplete Saga Compensation in Checkout
The checkout creates an order, then processes payment. If payment fails, the order is cancelled. But:
1. Stock was validated but never reserved -- another request can claim the stock between validation and order creation (race condition)
2. If the cancel request fails after payment failure, the order is orphaned
3. If payment succeeds but notification fails, the user is not informed
4. There is no compensation if the order-service create call succeeds but the gateway crashes before processing payment

**Fix:** Implement a proper saga pattern with reliable compensation:
```python
class CheckoutSaga:
    def execute(self, user_id, items):
        steps = [
            ("reserve_stock", self._reserve_stock, self._release_stock),
            ("create_order", self._create_order, self._cancel_order),
            ("process_payment", self._process_payment, self._refund_payment),
            ("send_notification", self._notify, None),  # Non-critical, no compensation
        ]
        completed = []
        for name, execute, compensate in steps:
            try:
                result = execute()
                completed.append((name, compensate))
            except Exception as e:
                # Roll back completed steps in reverse
                for step_name, comp in reversed(completed):
                    if comp:
                        comp()
                raise SagaFailedError(f"Failed at {name}: {e}")
```

### HIGH - No Request ID Propagation
The gateway generates a `X-Request-ID` and returns it in the response, but never forwards it to downstream service calls. Distributed tracing is broken -- there is no way to correlate gateway logs with downstream service logs.

**Fix:**
```python
def proxy_request(service_name, path, method="GET", data=None):
    headers = {"X-Request-ID": g.request_id}
    response = requests.request(method=method, url=url, json=data, headers=headers)
```

### HIGH - No Circuit Breaker or Retry Logic
A single failing service (e.g., product-service down) causes all requests that touch that service to fail with a 30-second timeout. No circuit breaker prevents cascading failures, and no retry handles transient errors.

### MEDIUM - Internal Errors Exposed to Clients
`proxy_request` returns `str(e)` in error responses, which can contain internal URLs, stack traces, and connection details.

**Fix:** Return generic error messages:
```python
except Exception as e:
    logger.error(f"Service {service_name} error: {e}")
    return {"error": "Service unavailable"}, 502
```

### MEDIUM - No Rate Limiting
The gateway has no request rate limiting. A single client can overwhelm all downstream services.

### LOW - No Response Caching
GET requests to product-service and user-service could be cached at the gateway level to reduce downstream load and improve latency.'''),

    ("thinking/code-review", r'''Review this event-driven architecture and identify issues:

```python
import json
import time
import threading
import logging
from typing import Callable, Dict, List
from queue import Queue

logger = logging.getLogger(__name__)

class EventBus:
    def __init__(self):
        self.handlers: Dict[str, List[Callable]] = {}
        self.queue = Queue()
        self.dead_letter = []
        self._worker = threading.Thread(target=self._process, daemon=True)
        self._worker.start()

    def subscribe(self, event_type: str, handler: Callable):
        if event_type not in self.handlers:
            self.handlers[event_type] = []
        self.handlers[event_type].append(handler)

    def publish(self, event_type: str, data: dict):
        event = {
            "type": event_type,
            "data": data,
            "timestamp": time.time(),
            "id": str(uuid.uuid4())
        }
        self.queue.put(event)
        logger.info(f"Published event: {event_type}")

    def _process(self):
        while True:
            event = self.queue.get()
            handlers = self.handlers.get(event["type"], [])

            if not handlers:
                logger.warning(f"No handlers for event: {event['type']}")
                self.dead_letter.append(event)
                continue

            for handler in handlers:
                try:
                    handler(event["data"])
                except Exception as e:
                    logger.error(
                        f"Handler {handler.__name__} failed for "
                        f"{event['type']}: {e}"
                    )

            self.queue.task_done()

    def publish_and_wait(self, event_type: str, data: dict, timeout: float = 5.0):
        self.publish(event_type, data)
        self.queue.join()

class OrderEventHandler:
    def __init__(self, db, email_service, inventory_service):
        self.db = db
        self.email = email_service
        self.inventory = inventory_service

    def on_order_created(self, data):
        order_id = data["order_id"]
        user_id = data["user_id"]
        items = data["items"]

        for item in items:
            self.inventory.decrease_stock(item["product_id"], item["quantity"])

        user = self.db.get_user(user_id)
        self.email.send_order_confirmation(user.email, order_id)

        self.db.update_user_stats(user_id, data["total"])

    def on_order_cancelled(self, data):
        for item in data["items"]:
            self.inventory.increase_stock(item["product_id"], item["quantity"])

        user = self.db.get_user(data["user_id"])
        self.email.send_cancellation(user.email, data["order_id"])

    def on_payment_completed(self, data):
        self.db.update_order_status(data["order_id"], "paid")
        order = self.db.get_order(data["order_id"])
        self.email.send_receipt(order.user.email, order)

class AnalyticsEventHandler:
    def __init__(self, analytics_db):
        self.db = analytics_db

    def on_any_event(self, event_type, data):
        self.db.insert_event(event_type, json.dumps(data), time.time())

# Setup
event_bus = EventBus()
order_handler = OrderEventHandler(db, email_service, inventory_service)
analytics_handler = AnalyticsEventHandler(analytics_db)

event_bus.subscribe("order.created", order_handler.on_order_created)
event_bus.subscribe("order.cancelled", order_handler.on_order_cancelled)
event_bus.subscribe("payment.completed", order_handler.on_payment_completed)
```''', r'''<think>
Let me analyze this event-driven architecture for reliability, correctness, and design issues.

In-memory event bus:
1. CRITICAL: Events are stored in an in-memory Queue. If the process crashes, all unprocessed events are lost. In an event-driven architecture, events MUST be durably persisted before being processed.

2. Single worker thread: Only one thread processes events. This is a bottleneck. If on_order_created takes 5 seconds (email sending), all other events wait.

3. No event ordering guarantees per entity. Events for different orders are processed sequentially even though they are independent.

4. No retry mechanism. If a handler fails, the event is logged and discarded. Critical business operations (stock adjustment, email) are permanently lost.

5. dead_letter is an in-memory list. If the process crashes, dead letters are also lost.

Handler issues:
6. on_order_created performs stock decrements AND email sending AND stats updates in a single handler. If the email fails, stock is already decremented but the user is not notified. These should be separate handlers for different concerns.

7. The handler does multiple side effects with no transaction. If increase_stock succeeds for 2 of 3 items but fails on the third, stock is partially restored.

8. AnalyticsEventHandler.on_any_event has the wrong signature - it expects (event_type, data) but handlers receive only (data). It will fail when called.

publish_and_wait:
9. This defeats the purpose of asynchronous event processing. It publishes an event and then blocks until the queue is empty. But queue.join() waits for ALL events in the queue, not just the one that was published.

10. If there are events ahead in the queue, publish_and_wait blocks until all of them are processed too.

Missing:
- No event deduplication (same event processed twice)
- No event versioning
- No event schema validation
- No back-pressure mechanism
- No distributed support (in-process only)
- No correlation/causation tracking
- subscribe is not thread-safe (modifying self.handlers without locks)
</think>

## Code Review: Event-Driven Architecture

### CRITICAL - Events Lost on Process Crash
Events are stored in an in-memory `Queue`. If the process crashes, restarts, or is deployed, all unprocessed events are permanently lost. For an event-driven system handling order creation, stock management, and payments, this is unacceptable.

**Fix:** Use a durable message broker (RabbitMQ, Kafka, Redis Streams):
```python
class DurableEventBus:
    def __init__(self, redis_client):
        self.redis = redis_client

    def publish(self, event_type, data):
        event = {"type": event_type, "data": data, "id": str(uuid.uuid4())}
        self.redis.xadd(f"events:{event_type}", {"payload": json.dumps(event)})

    def consume(self, event_type, handler, consumer_group):
        while True:
            messages = self.redis.xreadgroup(
                consumer_group, "worker-1",
                {f"events:{event_type}": ">"},
                count=10, block=5000
            )
            for stream, entries in messages:
                for msg_id, fields in entries:
                    handler(json.loads(fields["payload"]))
                    self.redis.xack(stream, consumer_group, msg_id)
```

### CRITICAL - No Retry on Handler Failure
When a handler throws an exception, the event is logged and permanently discarded. If `on_order_created` fails after decrementing stock but before sending email, the stock is reduced, the customer is not notified, and the event is gone.

**Fix:** Implement retry with exponential backoff:
```python
def _process_with_retry(self, event, handler, max_retries=3):
    for attempt in range(max_retries):
        try:
            handler(event["data"])
            return
        except Exception as e:
            if attempt == max_retries - 1:
                self.dead_letter.append(event)
                logger.error(f"Handler permanently failed: {e}")
            else:
                time.sleep(2 ** attempt)
```

### HIGH - Single Worker Thread Is a Bottleneck
One thread processes all events sequentially. If an email send takes 3 seconds, all other events (stock updates, payment processing) are blocked for 3 seconds. In a high-throughput system, the queue grows faster than it can be processed.

**Fix:** Use a thread pool:
```python
from concurrent.futures import ThreadPoolExecutor

class EventBus:
    def __init__(self, num_workers=4):
        self.executor = ThreadPoolExecutor(max_workers=num_workers)

    def _process(self):
        while True:
            event = self.queue.get()
            handlers = self.handlers.get(event["type"], [])
            for handler in handlers:
                self.executor.submit(self._safe_handle, handler, event)
```

### HIGH - on_order_created Does Too Much
A single handler decrements stock, sends email, AND updates user stats. If email fails, stock is already decremented. These should be separate handlers so failures are isolated:
```python
event_bus.subscribe("order.created", inventory_handler.decrease_stock)
event_bus.subscribe("order.created", email_handler.send_confirmation)
event_bus.subscribe("order.created", stats_handler.update_user_stats)
```

### HIGH - AnalyticsEventHandler Has Wrong Signature
`on_any_event(self, event_type, data)` expects two arguments, but the event bus calls handlers with only `handler(event["data"])`. This handler will always fail with `TypeError`.

**Fix:** Either change the handler signature to `on_any_event(self, data)` or change the bus to pass the full event.

### MEDIUM - publish_and_wait Blocks on ALL Events
`queue.join()` waits until every event in the queue is processed, not just the published event. If there are 100 events ahead in the queue, the caller blocks until all 100 are processed.

### MEDIUM - subscribe Is Not Thread-Safe
`self.handlers[event_type].append(handler)` modifies a shared dictionary from potentially multiple threads without locking.

### MEDIUM - Dead Letter Queue Is In-Memory
`self.dead_letter` is a list that is lost on process restart. Dead letters should be persisted for later analysis and reprocessing.

### LOW - No Event Deduplication
If the same event is published twice (network retry, publisher bug), it is processed twice. Stock could be decremented twice for the same order.'''),

    ("thinking/code-review", r'''Review this dependency injection setup and identify issues:

```python
# app.py
from flask import Flask
import psycopg2
import redis
import os

app = Flask(__name__)

# Global instances
db_connection = psycopg2.connect(os.environ["DATABASE_URL"])
redis_client = redis.Redis(host="localhost", port=6379)
smtp_server = None

def get_db():
    global db_connection
    if db_connection.closed:
        db_connection = psycopg2.connect(os.environ["DATABASE_URL"])
    return db_connection

def get_redis():
    return redis_client

def get_smtp():
    global smtp_server
    if smtp_server is None:
        import smtplib
        smtp_server = smtplib.SMTP(os.environ["SMTP_HOST"], 587)
        smtp_server.starttls()
        smtp_server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
    return smtp_server

class UserService:
    def __init__(self):
        self.db = get_db()
        self.cache = get_redis()

    def get_user(self, user_id):
        cached = self.cache.get(f"user:{user_id}")
        if cached:
            return json.loads(cached)
        cursor = self.db.cursor()
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()
        self.cache.setex(f"user:{user_id}", 300, json.dumps(user))
        return user

class OrderService:
    def __init__(self):
        self.db = get_db()
        self.user_service = UserService()
        self.email = get_smtp()

    def create_order(self, user_id, items):
        user = self.user_service.get_user(user_id)
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO orders ...")
        self.db.commit()
        self.email.sendmail("from@app.com", user["email"], "Order confirmed")

class PaymentService:
    def __init__(self):
        self.db = get_db()
        self.order_service = OrderService()

    def process_payment(self, order_id, amount):
        cursor = self.db.cursor()
        cursor.execute("INSERT INTO payments ...")
        self.db.commit()
        self.order_service.update_order_status(order_id, "paid")

# Route setup
user_service = UserService()
order_service = OrderService()
payment_service = PaymentService()

@app.route("/api/users/<int:user_id>")
def get_user(user_id):
    return jsonify(user_service.get_user(user_id))

@app.route("/api/orders", methods=["POST"])
def create_order():
    data = request.get_json()
    return jsonify(order_service.create_order(data["user_id"], data["items"]))
```''', r'''<think>
This code has severe dependency injection and lifecycle management issues.

Global mutable state:
1. db_connection is a single global connection shared across all requests. In a multi-threaded web server (like gunicorn with threads), multiple threads share this connection, causing data corruption and race conditions.
2. redis_client is a global singleton - Redis client is actually thread-safe, so this is less of an issue.
3. smtp_server is a global SMTP connection. SMTP connections can time out, and sharing across threads is not safe.

Tight coupling:
4. Services create their own dependencies in __init__. OrderService creates a UserService internally. PaymentService creates an OrderService internally. This makes testing impossible without the real dependencies.
5. The dependency graph creates duplicate instances: PaymentService creates OrderService which creates UserService. The module-level order_service and user_service are separate instances from those inside PaymentService.

Connection management:
6. get_db() checks if connection is closed and reconnects, but the global connection is shared. If one thread closes it, all other threads lose their connection.
7. get_smtp() creates a persistent SMTP connection that can time out. No reconnection logic beyond the initial None check.
8. No connection pooling for database.

Lifecycle:
9. Services are instantiated at module import time. If DATABASE_URL is not set, the import fails. This makes testing harder.
10. The SMTP connection is lazy (created on first use) but the DB connection is eager (created at import).

Testing:
11. Cannot substitute test doubles. UserService always gets the real database via get_db(). To test UserService, you need a real PostgreSQL instance.
12. No interface/protocol definitions for dependencies.

Circular dependency risk:
13. PaymentService -> OrderService -> UserService. If OrderService ever needs PaymentService (e.g., to check payment status), a circular dependency is created.
</think>

## Code Review: Dependency Injection Issues

### CRITICAL - Single Shared Database Connection Across Threads
`db_connection` is a single global `psycopg2` connection shared across all request-handling threads. PostgreSQL connections are not thread-safe. Concurrent queries from different threads will interleave data on the connection, causing corrupted results, partial reads, and transaction conflicts.

**Fix:** Use a connection pool:
```python
from psycopg2.pool import ThreadedConnectionPool

pool = ThreadedConnectionPool(
    minconn=2, maxconn=20,
    dsn=os.environ["DATABASE_URL"]
)

def get_db():
    if "db" not in g:
        g.db = pool.getconn()
    return g.db

@app.teardown_appcontext
def return_db(exception):
    db = g.pop("db", None)
    if db is not None:
        pool.putconn(db)
```

### CRITICAL - Services Create Own Dependencies (No Injection)
Services instantiate their dependencies internally:
```python
class OrderService:
    def __init__(self):
        self.db = get_db()          # Coupled to global
        self.user_service = UserService()  # Creates new instance
        self.email = get_smtp()     # Coupled to global
```

This creates several problems:
- Cannot substitute test doubles (mocks, fakes)
- Duplicate instances (PaymentService creates its own OrderService, which creates its own UserService, separate from the module-level instances)
- Hidden dependency graph

**Fix:** Inject dependencies through constructors:
```python
class OrderService:
    def __init__(self, db_pool, user_service, email_client):
        self.db_pool = db_pool
        self.users = user_service
        self.email = email_client

# Composition root
user_service = UserService(db_pool, redis_client)
order_service = OrderService(db_pool, user_service, email_client)
payment_service = PaymentService(db_pool, order_service)
```

### HIGH - Duplicate Service Instances
Module-level code creates `user_service = UserService()`, but `OrderService.__init__` also creates `self.user_service = UserService()`. These are separate instances with separate database connections and caches. Updates through one are invisible to the other.

**Fix:** Create services once in a composition root and inject shared instances.

### HIGH - Global SMTP Connection
`get_smtp()` creates a single SMTP connection on first use and reuses it forever. SMTP connections can time out, be closed by the server, or have TLS issues. No reconnection logic exists beyond the initial `is None` check.

**Fix:** Create SMTP connections per-use or use a connection pool:
```python
class EmailClient:
    def send(self, from_addr, to_addr, message):
        with smtplib.SMTP(os.environ["SMTP_HOST"], 587) as server:
            server.starttls()
            server.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])
            server.sendmail(from_addr, to_addr, message)
```

### MEDIUM - Eager Connection at Import Time
`db_connection = psycopg2.connect(...)` runs at import time. If `DATABASE_URL` is not set or the database is unreachable, the entire module fails to import. This makes testing and development difficult.

**Fix:** Use lazy initialization or a factory pattern that creates connections on demand.

### MEDIUM - No Interfaces for Dependencies
Services depend on concrete implementations. There are no Protocol or ABC definitions. Testing requires the real database and Redis, even for unit tests.

**Fix:** Define protocols:
```python
class UserRepository(Protocol):
    def get_user(self, user_id: int) -> Optional[dict]: ...
    def create_user(self, data: dict) -> dict: ...
```

### LOW - Inconsistent Initialization (Eager vs Lazy)
Database connection is created eagerly at import. SMTP is created lazily on first use. Redis is created eagerly. This inconsistency makes the initialization sequence unpredictable and difficult to reason about.'''),
]
