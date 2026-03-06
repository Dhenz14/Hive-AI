r"""Thinking-trace pairs: design pattern refactoring code review."""

PAIRS = [
    ("thinking/code-review", r'''Review this code and suggest Strategy pattern refactoring:

```python
class NotificationSender:
    def send(self, user, message, channel):
        if channel == "email":
            import smtplib
            from email.mime.text import MIMEText
            msg = MIMEText(message)
            msg["Subject"] = "Notification"
            msg["From"] = "noreply@myapp.com"
            msg["To"] = user.email
            server = smtplib.SMTP("smtp.myapp.com", 587)
            server.starttls()
            server.login("noreply@myapp.com", os.environ["SMTP_PASSWORD"])
            server.send_message(msg)
            server.quit()

        elif channel == "sms":
            import twilio
            client = twilio.rest.Client(
                os.environ["TWILIO_SID"],
                os.environ["TWILIO_TOKEN"]
            )
            client.messages.create(
                to=user.phone,
                from_=os.environ["TWILIO_PHONE"],
                body=message
            )

        elif channel == "push":
            import firebase_admin
            from firebase_admin import messaging
            notification = messaging.Message(
                token=user.device_token,
                notification=messaging.Notification(
                    title="Notification",
                    body=message
                )
            )
            messaging.send(notification)

        elif channel == "slack":
            import requests
            requests.post(
                user.slack_webhook,
                json={"text": message}
            )

        elif channel == "in_app":
            from app.models import Notification
            notification = Notification(
                user_id=user.id,
                message=message,
                read=False
            )
            db.session.add(notification)
            db.session.commit()

        else:
            raise ValueError(f"Unknown channel: {channel}")

    def send_bulk(self, users, message, channel):
        results = []
        for user in users:
            try:
                self.send(user, message, channel)
                results.append({"user": user.id, "status": "sent"})
            except Exception as e:
                results.append({"user": user.id, "status": "failed", "error": str(e)})
        return results
```''', r'''<think>
This is a textbook case for the Strategy pattern. The send() method uses a long if/elif chain to select behavior based on the channel parameter. Each branch has completely different implementation code.

Issues with the current approach:
1. Open/Closed Principle violation: Adding a new channel requires modifying the send() method
2. All channel implementations in a single class with all their imports
3. Each channel creates new connections on every send (no connection pooling/reuse)
4. Testing requires mocking all external services even when testing one channel
5. send_bulk creates a new connection for each user (e.g., new SMTP connection per email)
6. No retry logic
7. No rate limiting
8. Imports inside the function body (performance hit on each call)

The Strategy pattern would:
1. Define a NotificationChannel interface/protocol
2. Create one class per channel
3. Register channels in a factory/registry
4. Allow adding new channels without modifying existing code
</think>

## Code Review: Strategy Pattern Refactoring

### HIGH - Open/Closed Principle Violation
Adding a new notification channel (e.g., WhatsApp, Telegram, webhook) requires modifying the `send()` method. Each modification risks breaking existing channels. The function grows linearly with each new channel.

**Refactor using Strategy pattern:**

```python
from typing import Protocol

class NotificationChannel(Protocol):
    def send(self, user, message) -> None:
        ...

class EmailChannel:
    def __init__(self):
        self.smtp_password = os.environ["SMTP_PASSWORD"]

    def send(self, user, message):
        msg = MIMEText(message)
        msg["Subject"] = "Notification"
        msg["From"] = "noreply@myapp.com"
        msg["To"] = user.email
        with smtplib.SMTP("smtp.myapp.com", 587) as server:
            server.starttls()
            server.login("noreply@myapp.com", self.smtp_password)
            server.send_message(msg)

class SmsChannel:
    def __init__(self):
        self.client = twilio.rest.Client(
            os.environ["TWILIO_SID"],
            os.environ["TWILIO_TOKEN"]
        )

    def send(self, user, message):
        self.client.messages.create(
            to=user.phone,
            from_=os.environ["TWILIO_PHONE"],
            body=message
        )

class PushChannel:
    def send(self, user, message):
        notification = messaging.Message(
            token=user.device_token,
            notification=messaging.Notification(title="Notification", body=message)
        )
        messaging.send(notification)

class SlackChannel:
    def send(self, user, message):
        requests.post(user.slack_webhook, json={"text": message})

class InAppChannel:
    def send(self, user, message):
        notification = Notification(user_id=user.id, message=message, read=False)
        db.session.add(notification)
        db.session.commit()
```

**Refactored NotificationSender:**
```python
class NotificationSender:
    def __init__(self):
        self.channels = {
            "email": EmailChannel(),
            "sms": SmsChannel(),
            "push": PushChannel(),
            "slack": SlackChannel(),
            "in_app": InAppChannel(),
        }

    def register_channel(self, name, channel):
        self.channels[name] = channel

    def send(self, user, message, channel):
        handler = self.channels.get(channel)
        if not handler:
            raise ValueError(f"Unknown channel: {channel}")
        handler.send(user, message)
```

### HIGH - New Connection Per Send (No Reuse)
Each call to `send()` with email creates a new SMTP connection, authenticates, sends one message, and disconnects. In `send_bulk` with 1000 users, this is 1000 SMTP connections. The Strategy classes above can maintain persistent connections.

### HIGH - No Error Isolation
If the Twilio SDK is not installed but only email is used, importing the module fails for all channels. Strategy classes isolate dependencies -- only the channels actually used need their dependencies installed.

### MEDIUM - Imports Inside Function Body
`import smtplib`, `import twilio`, etc. inside the function body are executed on every call. Moving imports to the class level (in Strategy classes) eliminates this repeated overhead.

### MEDIUM - send_bulk Has No Batching
For email, SMTP supports sending multiple messages on a single connection. The current implementation treats each user independently. Strategy classes can implement channel-specific batching:
```python
class EmailChannel:
    def send_bulk(self, users, message):
        with smtplib.SMTP("smtp.myapp.com", 587) as server:
            server.starttls()
            server.login(...)
            for user in users:
                msg = self._create_message(user, message)
                server.send_message(msg)
```

### LOW - No Retry or Rate Limiting
Failed sends are not retried. External services (Twilio, Firebase) may have rate limits that are not respected. Each Strategy class can implement its own retry and throttling logic.'''),

    ("thinking/code-review", r'''Review this code and suggest Repository pattern refactoring:

```python
from flask import Flask, request, jsonify
import psycopg2
import json

app = Flask(__name__)
DB_URL = "postgresql://user:pass@localhost/myapp"

@app.route("/api/products")
def list_products():
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, price, category, stock FROM products "
        "WHERE stock > 0 ORDER BY name"
    )
    products = []
    for row in cursor.fetchall():
        products.append({
            "id": row[0], "name": row[1], "price": float(row[2]),
            "category": row[3], "stock": row[4]
        })
    cursor.close()
    conn.close()
    return jsonify(products)

@app.route("/api/products/<int:product_id>")
def get_product(product_id):
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, name, description, price, category, stock, image_url "
        "FROM products WHERE id = %s", (product_id,)
    )
    row = cursor.fetchone()
    cursor.close()
    conn.close()

    if not row:
        return jsonify({"error": "Not found"}), 404

    return jsonify({
        "id": row[0], "name": row[1], "description": row[2],
        "price": float(row[3]), "category": row[4],
        "stock": row[5], "image_url": row[6]
    })

@app.route("/api/products", methods=["POST"])
def create_product():
    data = request.get_json()
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO products (name, description, price, category, stock, image_url) "
        "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
        (data["name"], data.get("description", ""), data["price"],
         data.get("category"), data.get("stock", 0), data.get("image_url"))
    )
    product_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"id": product_id}), 201

@app.route("/api/products/<int:product_id>", methods=["PUT"])
def update_product(product_id):
    data = request.get_json()
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()

    updates = []
    params = []
    for field in ["name", "description", "price", "category", "stock", "image_url"]:
        if field in data:
            updates.append(f"{field} = %s")
            params.append(data[field])

    if not updates:
        return jsonify({"error": "No fields to update"}), 400

    params.append(product_id)
    cursor.execute(
        f"UPDATE products SET {', '.join(updates)} WHERE id = %s",
        params
    )
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "updated"})

@app.route("/api/products/<int:product_id>", methods=["DELETE"])
def delete_product(product_id):
    conn = psycopg2.connect(DB_URL)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
    conn.commit()
    cursor.close()
    conn.close()
    return "", 204
```''', r'''<think>
This code has database access logic directly in Flask route handlers. Every endpoint creates its own connection, executes raw SQL, manually maps rows to dicts, and closes the connection. The issues are:

1. No separation between data access and request handling
2. Connection management duplicated in every route (create, use, close)
3. Row-to-dict mapping duplicated (different column sets per query)
4. Raw SQL scattered throughout route handlers
5. No connection pooling (new connection per request)
6. If an exception occurs between connect and close, the connection leaks
7. No transaction management (commit after single operation)
8. Business logic would have to go in route handlers

The Repository pattern would:
1. Create a ProductRepository class that encapsulates all database access
2. Provide clean methods (list, get, create, update, delete) that return domain objects
3. Handle connection management internally
4. Allow swapping the data source (e.g., from SQL to NoSQL) without changing routes
5. Enable unit testing routes without a database
</think>

## Code Review: Repository Pattern Refactoring

### HIGH - Database Access Coupled to Route Handlers
Every route handler directly creates connections, executes SQL, maps rows, and manages cleanup. This makes routes impossible to unit test without a database, duplicates connection management 5 times, and violates separation of concerns.

**Extract a ProductRepository:**
```python
class ProductRepository:
    def __init__(self, db_pool):
        self.pool = db_pool

    def list_in_stock(self):
        with self.pool.getconn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, name, price, category, stock "
                    "FROM products WHERE stock > 0 ORDER BY name"
                )
                return [self._row_to_product(row) for row in cursor.fetchall()]

    def get_by_id(self, product_id):
        with self.pool.getconn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT id, name, description, price, category, stock, image_url "
                    "FROM products WHERE id = %s", (product_id,)
                )
                row = cursor.fetchone()
                return self._row_to_product_detail(row) if row else None

    def create(self, data):
        with self.pool.getconn() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO products (name, description, price, category, stock, image_url) "
                    "VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                    (data["name"], data.get("description", ""), data["price"],
                     data.get("category"), data.get("stock", 0), data.get("image_url"))
                )
                conn.commit()
                return cursor.fetchone()[0]

    def update(self, product_id, data):
        allowed_fields = {"name", "description", "price", "category", "stock", "image_url"}
        updates = {k: v for k, v in data.items() if k in allowed_fields}
        if not updates:
            return False
        # ... build and execute UPDATE

    def delete(self, product_id):
        # ... execute DELETE

    def _row_to_product(self, row):
        return {"id": row[0], "name": row[1], "price": float(row[2]),
                "category": row[3], "stock": row[4]}
```

**Simplified route handlers:**
```python
product_repo = ProductRepository(connection_pool)

@app.route("/api/products")
def list_products():
    return jsonify(product_repo.list_in_stock())

@app.route("/api/products/<int:product_id>")
def get_product(product_id):
    product = product_repo.get_by_id(product_id)
    if not product:
        return jsonify({"error": "Not found"}), 404
    return jsonify(product)
```

### HIGH - Connection Leak on Exception
If an exception occurs between `psycopg2.connect()` and `conn.close()`, the connection is never closed. Over time, this exhausts database connections.

**Fix:** Use context managers (as shown in the repository above) or try/finally:
```python
conn = psycopg2.connect(DB_URL)
try:
    # ... use connection
finally:
    conn.close()
```

### HIGH - No Connection Pooling
Each request creates a new database connection. Connection creation involves TCP handshake, TLS negotiation, and authentication. Under load, this creates hundreds of connections per second.

**Fix:** Use a connection pool:
```python
from psycopg2.pool import ThreadedConnectionPool
pool = ThreadedConnectionPool(minconn=2, maxconn=20, dsn=DB_URL)
```

### MEDIUM - Row Mapping Duplicated and Fragile
Each route manually maps tuple indices to dict keys. The mapping in `list_products` (5 columns) differs from `get_product` (7 columns). Adding a column requires updating every mapping.

**Fix:** Use `cursor.description` or a dedicated mapping method in the repository (as shown above).

### MEDIUM - No Input Validation
`create_product` trusts all input without validation. Missing required fields (`name`, `price`) cause database errors instead of user-friendly 400 responses.

### LOW - Hardcoded Database URL
`DB_URL` is a module-level constant. Use environment variables or Flask configuration.'''),

    ("thinking/code-review", r'''Review this code and suggest Observer pattern refactoring:

```python
class OrderService:
    def __init__(self, db, email_client, sms_client, analytics,
                 inventory_service, payment_service, shipping_service,
                 loyalty_service, notification_service):
        self.db = db
        self.email = email_client
        self.sms = sms_client
        self.analytics = analytics
        self.inventory = inventory_service
        self.payment = payment_service
        self.shipping = shipping_service
        self.loyalty = loyalty_service
        self.notifications = notification_service

    def place_order(self, user, cart):
        order = self.db.create_order(user.id, cart.items, cart.total)

        self.payment.charge(user, order.total)

        for item in cart.items:
            self.inventory.decrease_stock(item.product_id, item.quantity)

        self.email.send(
            to=user.email,
            subject="Order Confirmation",
            body=f"Your order #{order.id} has been placed."
        )

        if user.phone:
            self.sms.send(user.phone, f"Order #{order.id} confirmed!")

        self.analytics.track("order_placed", {
            "order_id": order.id,
            "total": order.total,
            "items_count": len(cart.items)
        })

        self.loyalty.add_points(user.id, int(order.total))

        self.shipping.create_shipment(order)

        self.notifications.create(
            user.id, f"Order #{order.id} placed successfully"
        )

        return order

    def cancel_order(self, order_id, reason):
        order = self.db.get_order(order_id)
        order.status = "cancelled"
        self.db.save(order)

        self.payment.refund(order)

        for item in order.items:
            self.inventory.increase_stock(item.product_id, item.quantity)

        self.email.send(
            to=order.user.email,
            subject="Order Cancelled",
            body=f"Your order #{order.id} has been cancelled. Reason: {reason}"
        )

        self.analytics.track("order_cancelled", {
            "order_id": order.id,
            "reason": reason
        })

        self.loyalty.remove_points(order.user.id, int(order.total))

        self.shipping.cancel_shipment(order)

        self.notifications.create(
            order.user.id, f"Order #{order.id} cancelled"
        )

    def ship_order(self, order_id, tracking_number):
        order = self.db.get_order(order_id)
        order.status = "shipped"
        order.tracking_number = tracking_number
        self.db.save(order)

        self.email.send(
            to=order.user.email,
            subject="Order Shipped",
            body=f"Your order #{order.id} has been shipped. Track: {tracking_number}"
        )

        if order.user.phone:
            self.sms.send(
                order.user.phone,
                f"Order #{order.id} shipped! Track: {tracking_number}"
            )

        self.analytics.track("order_shipped", {
            "order_id": order.id,
            "tracking": tracking_number
        })

        self.notifications.create(
            order.user.id, f"Order #{order.id} shipped: {tracking_number}"
        )
```''', r'''<think>
This OrderService has 9 dependencies injected into the constructor. Each order lifecycle method (place, cancel, ship) must coordinate multiple services. The issues:

1. Too many dependencies (9!). The class knows about email, SMS, analytics, inventory, payment, shipping, loyalty, and notifications.
2. Adding a new side effect (e.g., updating a search index, sending a webhook) requires modifying every lifecycle method.
3. The core order logic (create order, update status) is mixed with side effects (send email, track analytics, add points).
4. If one side effect fails (e.g., analytics tracking), it should not prevent the order from being placed, but currently there is no error isolation.
5. Similar notification patterns repeat across all methods.

The Observer pattern would:
1. Define events (OrderPlaced, OrderCancelled, OrderShipped)
2. Let each service subscribe to relevant events
3. The OrderService only handles core logic and emits events
4. Each subscriber handles its own logic independently
</think>

## Code Review: Observer Pattern Refactoring

### HIGH - 9 Dependencies = Too Many Responsibilities
`OrderService.__init__` takes 9 service dependencies. The class coordinates email, SMS, analytics, inventory, payment, shipping, loyalty, and notifications for every order lifecycle event. Adding a new integration (webhook, search index, audit log) requires modifying the constructor and every lifecycle method.

**Refactor using Observer/Event pattern:**

```python
from dataclasses import dataclass
from typing import List, Callable, Dict

@dataclass
class OrderEvent:
    type: str
    order: object
    data: Dict = None

class EventBus:
    def __init__(self):
        self._handlers: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type, handler):
        self._handlers.setdefault(event_type, []).append(handler)

    def publish(self, event: OrderEvent):
        for handler in self._handlers.get(event.type, []):
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Event handler failed: {e}")
```

**Simplified OrderService:**
```python
class OrderService:
    def __init__(self, db, payment, inventory, event_bus):
        self.db = db
        self.payment = payment
        self.inventory = inventory
        self.events = event_bus

    def place_order(self, user, cart):
        order = self.db.create_order(user.id, cart.items, cart.total)
        self.payment.charge(user, order.total)
        for item in cart.items:
            self.inventory.decrease_stock(item.product_id, item.quantity)

        self.events.publish(OrderEvent("order.placed", order, {"user": user}))
        return order

    def cancel_order(self, order_id, reason):
        order = self.db.get_order(order_id)
        order.status = "cancelled"
        self.db.save(order)
        self.payment.refund(order)
        for item in order.items:
            self.inventory.increase_stock(item.product_id, item.quantity)

        self.events.publish(OrderEvent("order.cancelled", order, {"reason": reason}))
```

**Subscribers register independently:**
```python
# Each service subscribes to events it cares about
class EmailNotifier:
    def __init__(self, email_client, event_bus):
        event_bus.subscribe("order.placed", self.on_order_placed)
        event_bus.subscribe("order.cancelled", self.on_order_cancelled)
        event_bus.subscribe("order.shipped", self.on_order_shipped)

    def on_order_placed(self, event):
        self.email.send(to=event.data["user"].email, ...)

class AnalyticsTracker:
    def __init__(self, analytics, event_bus):
        event_bus.subscribe("order.placed", self.track)
        event_bus.subscribe("order.cancelled", self.track)

    def track(self, event):
        self.analytics.track(event.type, {"order_id": event.order.id})

class LoyaltyManager:
    def __init__(self, loyalty, event_bus):
        event_bus.subscribe("order.placed", self.add_points)
        event_bus.subscribe("order.cancelled", self.remove_points)
```

### HIGH - No Error Isolation Between Side Effects
If `self.analytics.track()` throws an exception, subsequent operations (loyalty points, shipping, notifications) are skipped even though the order was already placed and paid for. Side effects should not prevent core operations.

**Fix:** The EventBus wraps each handler in try/except (shown above), ensuring one handler's failure does not affect others.

### MEDIUM - Adding Integration Requires Code Changes Everywhere
Adding a webhook notification requires modifying `place_order`, `cancel_order`, and `ship_order`. With the Observer pattern, just subscribe a new handler -- no existing code changes needed.

### MEDIUM - Core Logic Mixed with Side Effects
Payment and inventory are core operations (the order fails without them). Email, analytics, loyalty, and notifications are side effects (the order succeeds without them). These should be separated -- core operations in the service, side effects via events.

### LOW - Notification Message Templates Duplicated
Each method constructs notification messages inline. Extract message templates for consistency.'''),

    ("thinking/code-review", r'''Review this code and suggest Decorator pattern refactoring:

```python
import time
import logging
import json
import redis
from functools import wraps

logger = logging.getLogger(__name__)
redis_client = redis.Redis()

class APIService:
    def get_user(self, user_id):
        logger.info(f"Getting user {user_id}")
        start = time.time()

        cache_key = f"user:{user_id}"
        cached = redis_client.get(cache_key)
        if cached:
            logger.info(f"Cache hit for user {user_id}")
            duration = time.time() - start
            logger.info(f"get_user took {duration:.3f}s")
            return json.loads(cached)

        try:
            result = self.db.get_user(user_id)
            if result:
                redis_client.setex(cache_key, 300, json.dumps(result.to_dict()))
            duration = time.time() - start
            logger.info(f"get_user took {duration:.3f}s")
            return result.to_dict() if result else None
        except Exception as e:
            duration = time.time() - start
            logger.error(f"get_user failed after {duration:.3f}s: {e}")
            raise

    def get_products(self, category=None):
        logger.info(f"Getting products, category={category}")
        start = time.time()

        cache_key = f"products:{category or 'all'}"
        cached = redis_client.get(cache_key)
        if cached:
            logger.info(f"Cache hit for products")
            duration = time.time() - start
            logger.info(f"get_products took {duration:.3f}s")
            return json.loads(cached)

        try:
            if category:
                results = self.db.get_products_by_category(category)
            else:
                results = self.db.get_all_products()

            data = [p.to_dict() for p in results]
            redis_client.setex(cache_key, 600, json.dumps(data))
            duration = time.time() - start
            logger.info(f"get_products took {duration:.3f}s")
            return data
        except Exception as e:
            duration = time.time() - start
            logger.error(f"get_products failed after {duration:.3f}s: {e}")
            raise

    def search(self, query, page=1):
        logger.info(f"Searching: {query}, page={page}")
        start = time.time()

        cache_key = f"search:{query}:{page}"
        cached = redis_client.get(cache_key)
        if cached:
            duration = time.time() - start
            logger.info(f"search took {duration:.3f}s (cached)")
            return json.loads(cached)

        try:
            results = self.db.search(query, page=page)
            data = [r.to_dict() for r in results]
            redis_client.setex(cache_key, 120, json.dumps(data))
            duration = time.time() - start
            logger.info(f"search took {duration:.3f}s")
            return data
        except Exception as e:
            duration = time.time() - start
            logger.error(f"search failed after {duration:.3f}s: {e}")
            raise
```''', r'''<think>
This code has three methods that all follow the exact same pattern:
1. Log the method call
2. Start a timer
3. Check cache, return if hit
4. Execute the actual logic
5. Store in cache
6. Log the duration
7. Handle errors and log them

The logging and caching are cross-cutting concerns that are duplicated across every method. The actual business logic is just a few lines in each method, buried under boilerplate.

This is a perfect case for the Decorator pattern (Python decorators). We can extract:
1. A timing/logging decorator
2. A caching decorator
3. An error-logging decorator

Then the methods contain only their core logic.

Additional issues:
- Cache TTL varies per method (300, 600, 120) but is hardcoded
- Duration logging is repeated 3 times in each method (cache hit, success, error)
- Error handling is identical across all methods
- The cache key generation logic is slightly different per method but follows a pattern
</think>

## Code Review: Decorator Pattern Refactoring

### HIGH - Cross-Cutting Concerns Duplicated in Every Method
Logging, timing, caching, and error handling are duplicated in all three methods. Each method is ~20 lines, of which only 3-5 lines are actual business logic. The rest is boilerplate.

**Extract decorators for cross-cutting concerns:**

```python
def timed(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        start = time.time()
        try:
            result = func(*args, **kwargs)
            duration = time.time() - start
            logger.info(f"{func.__name__} completed in {duration:.3f}s")
            return result
        except Exception as e:
            duration = time.time() - start
            logger.error(f"{func.__name__} failed after {duration:.3f}s: {e}")
            raise
    return wrapper

def cached(ttl=300, key_func=None):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            cache_key = key_func(*args, **kwargs) if key_func else \
                f"{func.__name__}:{json.dumps(args[1:], default=str)}:{json.dumps(kwargs, default=str)}"
            cached_value = redis_client.get(cache_key)
            if cached_value:
                logger.info(f"Cache hit: {cache_key}")
                return json.loads(cached_value)

            result = func(*args, **kwargs)
            if result is not None:
                redis_client.setex(cache_key, ttl, json.dumps(result))
            return result
        return wrapper
    return decorator

def logged(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        logger.info(f"Calling {func.__name__} with args={args[1:]}, kwargs={kwargs}")
        return func(*args, **kwargs)
    return wrapper
```

**Clean business logic:**
```python
class APIService:
    @logged
    @timed
    @cached(ttl=300, key_func=lambda self, uid: f"user:{uid}")
    def get_user(self, user_id):
        result = self.db.get_user(user_id)
        return result.to_dict() if result else None

    @logged
    @timed
    @cached(ttl=600, key_func=lambda self, cat=None: f"products:{cat or 'all'}")
    def get_products(self, category=None):
        if category:
            results = self.db.get_products_by_category(category)
        else:
            results = self.db.get_all_products()
        return [p.to_dict() for p in results]

    @logged
    @timed
    @cached(ttl=120, key_func=lambda self, q, page=1: f"search:{q}:{page}")
    def search(self, query, page=1):
        results = self.db.search(query, page=page)
        return [r.to_dict() for r in results]
```

### HIGH - Duration Logged Three Times Per Method
Each method logs duration in three places: cache hit path, success path, and error path. The `@timed` decorator handles all three cases in one place.

### MEDIUM - Cache TTL Hardcoded in Method Bodies
TTL values (300, 600, 120) are buried inside method implementations. The `@cached(ttl=300)` decorator parameter makes TTL visible at the method declaration level.

### MEDIUM - Error Handling Identical Across Methods
Every method has the same try/except pattern: catch Exception, log with duration, re-raise. The `@timed` decorator handles this uniformly.

### LOW - Business Logic Obscured by Boilerplate
The actual database call in each method is 1-3 lines. With 20 lines of boilerplate per method, the important code is hard to find. Decorators separate what the method does from how it is instrumented.'''),

    ("thinking/code-review", r'''Review this code and suggest applying the Builder pattern:

```python
class EmailBuilder:
    def send_welcome_email(self, user):
        subject = "Welcome to MyApp!"
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; }}
                .container {{ max-width: 600px; margin: auto; padding: 20px; }}
                .header {{ background-color: #007bff; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .footer {{ text-align: center; color: #666; font-size: 12px; padding: 10px; }}
                .button {{ background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Welcome, {user.name}!</h1>
                </div>
                <div class="content">
                    <p>Thank you for joining MyApp.</p>
                    <p>Get started by setting up your profile:</p>
                    <p><a href="https://myapp.com/profile" class="button">Set Up Profile</a></p>
                </div>
                <div class="footer">
                    <p>MyApp Inc. | 123 Main St | <a href="https://myapp.com/unsubscribe?uid={user.id}">Unsubscribe</a></p>
                </div>
            </div>
        </body>
        </html>
        """
        self.email_client.send(to=user.email, subject=subject, html=html)

    def send_order_confirmation(self, user, order):
        items_html = ""
        for item in order.items:
            items_html += f"""
            <tr>
                <td>{item.product_name}</td>
                <td>{item.quantity}</td>
                <td>${item.price:.2f}</td>
                <td>${item.total:.2f}</td>
            </tr>
            """

        subject = f"Order #{order.id} Confirmed"
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; color: #333; }}
                .container {{ max-width: 600px; margin: auto; padding: 20px; }}
                .header {{ background-color: #28a745; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; }}
                .footer {{ text-align: center; color: #666; font-size: 12px; padding: 10px; }}
                table {{ width: 100%; border-collapse: collapse; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1>Order Confirmed!</h1>
                </div>
                <div class="content">
                    <p>Hi {user.name},</p>
                    <p>Your order #{order.id} has been confirmed.</p>
                    <table>
                        <tr><th>Product</th><th>Qty</th><th>Price</th><th>Total</th></tr>
                        {items_html}
                    </table>
                    <p><strong>Order Total: ${order.total:.2f}</strong></p>
                </div>
                <div class="footer">
                    <p>MyApp Inc. | 123 Main St | <a href="https://myapp.com/unsubscribe?uid={user.id}">Unsubscribe</a></p>
                </div>
            </div>
        </body>
        </html>
        """
        self.email_client.send(to=user.email, subject=subject, html=html)

    # ... 5 more similar methods for password_reset, shipping, etc.
```''', r'''<think>
This code constructs HTML emails using inline f-strings. The issues:

1. Massive HTML strings embedded in Python code - impossible to maintain
2. CSS styles duplicated across every email method (font-family, container, header, footer, button)
3. HTML layout structure (container, header, content, footer) duplicated
4. No HTML escaping of user data (XSS in email clients - less critical than web but still a concern)
5. Company info and unsubscribe link duplicated in every footer
6. Colors hardcoded per email (blue for welcome, green for order)
7. No support for plain-text fallback
8. The class is called EmailBuilder but does not use the Builder pattern

While the Builder pattern itself is not the ideal solution here (template engine is better), we can use a builder-like approach to construct emails from reusable parts.

Better approaches:
1. Use Jinja2 or similar template engine with base template + blocks
2. Use a builder pattern for programmatic email construction
3. Separate content from presentation
</think>

## Code Review: Builder Pattern / Template Refactoring

### CRITICAL - HTML Templates Embedded in Python Code
Massive HTML strings with inline CSS are embedded in Python methods. This is unmaintainable: designers cannot edit emails without modifying Python code, CSS changes require updating every method, and the code is nearly impossible to read.

**Refactor using Jinja2 templates with inheritance:**

```html
<!-- templates/email/base.html -->
<html>
<head>
    <style>
        body { font-family: Arial, sans-serif; color: #333; }
        .container { max-width: 600px; margin: auto; padding: 20px; }
        .header { background-color: {{ header_color | default('#007bff') }}; color: white; padding: 20px; text-align: center; }
        .content { padding: 20px; }
        .footer { text-align: center; color: #666; font-size: 12px; }
        .button { background-color: #007bff; color: white; padding: 10px 20px; text-decoration: none; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header"><h1>{% block header %}{% endblock %}</h1></div>
        <div class="content">{% block content %}{% endblock %}</div>
        <div class="footer">
            <p>MyApp Inc. | 123 Main St |
            <a href="{{ unsubscribe_url }}">Unsubscribe</a></p>
        </div>
    </div>
</body>
</html>
```

```html
<!-- templates/email/welcome.html -->
{% extends "email/base.html" %}
{% block header %}Welcome, {{ user.name }}!{% endblock %}
{% block content %}
<p>Thank you for joining MyApp.</p>
<p><a href="{{ profile_url }}" class="button">Set Up Profile</a></p>
{% endblock %}
```

**Or use a Builder for programmatic construction:**

```python
class EmailBuilder:
    def __init__(self):
        self._to = None
        self._subject = None
        self._header = None
        self._header_color = "#007bff"
        self._sections = []
        self._template_env = Environment(loader=FileSystemLoader("templates"))

    def to(self, email):
        self._to = email
        return self

    def subject(self, subject):
        self._subject = subject
        return self

    def header(self, text, color="#007bff"):
        self._header = text
        self._header_color = color
        return self

    def section(self, html):
        self._sections.append(html)
        return self

    def build(self):
        template = self._template_env.get_template("email/base.html")
        html = template.render(
            header=self._header,
            header_color=self._header_color,
            sections=self._sections,
        )
        return {"to": self._to, "subject": self._subject, "html": html}
```

**Usage:**
```python
email = (EmailBuilder()
    .to(user.email)
    .subject("Welcome to MyApp!")
    .header(f"Welcome, {user.name}!", color="#007bff")
    .section('<p>Thank you for joining.</p>')
    .section(f'<a href="{profile_url}" class="button">Set Up Profile</a>')
    .build())
self.email_client.send(**email)
```

### HIGH - CSS Duplicated Across Every Email
The same CSS styles (font-family, container, header, footer, button) are copy-pasted into every email method. A design change requires updating N methods.

**Fix:** The base template approach (above) defines shared CSS once.

### HIGH - No HTML Escaping
`{user.name}`, `{item.product_name}`, and other user data are interpolated directly into HTML. If a user's name contains `<script>alert('xss')</script>`, it executes in email clients that render HTML.

**Fix:** Jinja2 auto-escapes by default. For the builder approach:
```python
from markupsafe import escape
self._header = escape(text)
```

### MEDIUM - Footer and Company Info Duplicated
The footer with company address and unsubscribe link is identical in every email. The base template approach eliminates this duplication.

### MEDIUM - No Plain-Text Fallback
All emails are HTML-only. Email clients that cannot render HTML (or users who prefer plain text) see nothing. Generate both HTML and plain-text versions.

### LOW - Hardcoded URLs
`"https://myapp.com/profile"` and `"https://myapp.com/unsubscribe"` are hardcoded. Use configuration variables for the base URL.'''),
]
