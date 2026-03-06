"""Phase 1X: Foundation Thinking — Code Review & Refactoring (Part 2)

Five training pairs on code review/refactoring: god class decomposition,
callback hell to async/await, tight coupling to DI, inheritance to composition,
and feature flag cleanup.
"""

PAIRS = [
    (
        "thinking/refactor-god-class",
        r'''This OrderService class has grown to 800+ lines and handles everything. It's becoming impossible to test and modify. Show how to decompose it:

class OrderService:
    def __init__(self, db, email_client, payment_gateway, inventory_api,
                 shipping_api, tax_service, analytics, logger):
        self.db = db
        self.email_client = email_client
        self.payment_gateway = payment_gateway
        self.inventory_api = inventory_api
        self.shipping_api = shipping_api
        self.tax_service = tax_service
        self.analytics = analytics
        self.logger = logger

    def create_order(self, user_id, items, shipping_address, payment_info):
        # Validate items (50 lines of validation logic)
        for item in items:
            product = self.db.get_product(item["product_id"])
            if not product or not product.active:
                raise ValueError(f"Invalid product: {item['product_id']}")
            stock = self.inventory_api.check_stock(item["product_id"])
            if stock < item["quantity"]:
                raise ValueError(f"Insufficient stock for {product.name}")
        # ... more validation

        # Calculate pricing (80 lines of pricing logic)
        subtotal = sum(
            self.db.get_product(i["product_id"]).price * i["quantity"]
            for i in items
        )
        tax = self.tax_service.calculate(subtotal, shipping_address)
        shipping_cost = self.shipping_api.get_rate(items, shipping_address)
        discount = self._calculate_loyalty_discount(user_id, subtotal)
        total = subtotal + tax + shipping_cost - discount
        # ... more pricing

        # Process payment (40 lines)
        charge = self.payment_gateway.charge(payment_info, total)
        if not charge.success:
            raise PaymentError(charge.error)

        # Create order record (30 lines)
        order = self.db.create_order(
            user_id=user_id, items=items, total=total,
            tax=tax, shipping=shipping_cost, discount=discount,
        )

        # Reserve inventory (20 lines)
        for item in items:
            self.inventory_api.reserve(item["product_id"], item["quantity"])

        # Send notifications (30 lines)
        user = self.db.get_user(user_id)
        self.email_client.send_order_confirmation(user.email, order)
        self.analytics.track("order_created", {"order_id": order.id, "total": total})

        return order

    def cancel_order(self, order_id, reason):
        # 60 lines: validation, refund, inventory release, notifications
        pass

    def update_shipping(self, order_id, tracking_info):
        # 40 lines: update status, notify customer, update analytics
        pass

    def process_return(self, order_id, items, reason):
        # 80 lines: validate return, process refund, update inventory, notify
        pass

    def generate_invoice(self, order_id):
        # 50 lines: fetch order, calculate totals, generate PDF
        pass

    def _calculate_loyalty_discount(self, user_id, subtotal):
        # 40 lines: fetch user history, calculate tier, apply discount
        pass

    # ... 15 more methods''',
        r'''<think>
This is a classic god class. Let me identify the distinct responsibilities:

1. **Order validation** -- checking products exist, stock available
2. **Pricing/calculation** -- subtotal, tax, shipping, discounts
3. **Payment processing** -- charging cards, refunds
4. **Inventory management** -- reserving, releasing stock
5. **Notifications** -- emails, analytics tracking
6. **Order persistence** -- CRUD on order records
7. **Invoice generation** -- PDF creation
8. **Loyalty/discount calculation** -- user tier, discounts

The 8 constructor dependencies are a code smell -- each one represents a different concern.

Decomposition strategy using Single Responsibility Principle:

1. `OrderValidator` -- validates items, stock, addresses
2. `PricingCalculator` -- subtotal, tax, shipping, discounts
3. `PaymentProcessor` -- charges, refunds
4. `InventoryManager` -- reserve, release stock
5. `OrderNotifier` -- emails and analytics
6. `InvoiceGenerator` -- PDF generation
7. `OrderService` -- thin orchestrator that coordinates the above

The orchestrator should be ~50 lines, not 800. Each extracted class is independently testable.

For the orchestration pattern, I'll use a "pipeline" approach where create_order is a sequence of steps, and each step can be tested independently.

I should also consider: should these be separate classes, or could some be functions? For things like validation that don't need state, a function module is simpler. For things with dependencies (payment gateway), a class with DI makes sense.
</think>

The 8 constructor dependencies are the red flag -- each represents a separate concern. Decompose into focused classes with a thin orchestrator.

**Step 1: Extract domain logic into focused classes**

```python
# validation.py
class OrderValidator:
    def __init__(self, db, inventory_api):
        self.db = db
        self.inventory_api = inventory_api

    def validate_items(self, items: list[dict]) -> list[dict]:
        """Validate and enrich items with product data. Raises on invalid."""
        validated = []
        for item in items:
            product = self.db.get_product(item["product_id"])
            if not product or not product.active:
                raise ValueError(f"Invalid product: {item['product_id']}")
            stock = self.inventory_api.check_stock(item["product_id"])
            if stock < item["quantity"]:
                raise ValueError(f"Insufficient stock for {product.name}")
            validated.append({**item, "product": product, "unit_price": product.price})
        return validated


# pricing.py
class PricingCalculator:
    def __init__(self, tax_service, shipping_api, loyalty_service):
        self.tax_service = tax_service
        self.shipping_api = shipping_api
        self.loyalty_service = loyalty_service

    def calculate(self, user_id: int, items: list[dict],
                  shipping_address: dict) -> "PricingResult":
        subtotal = sum(i["unit_price"] * i["quantity"] for i in items)
        tax = self.tax_service.calculate(subtotal, shipping_address)
        shipping = self.shipping_api.get_rate(items, shipping_address)
        discount = self.loyalty_service.get_discount(user_id, subtotal)
        return PricingResult(
            subtotal=subtotal, tax=tax,
            shipping=shipping, discount=discount,
            total=subtotal + tax + shipping - discount,
        )

@dataclass(frozen=True)
class PricingResult:
    subtotal: float
    tax: float
    shipping: float
    discount: float
    total: float


# payment.py
class PaymentProcessor:
    def __init__(self, payment_gateway):
        self.gateway = payment_gateway

    def charge(self, payment_info: dict, amount: float) -> "ChargeResult":
        result = self.gateway.charge(payment_info, amount)
        if not result.success:
            raise PaymentError(result.error)
        return result

    def refund(self, charge_id: str, amount: float) -> "RefundResult":
        return self.gateway.refund(charge_id, amount)


# inventory.py
class InventoryManager:
    def __init__(self, inventory_api):
        self.api = inventory_api

    def reserve(self, items: list[dict]):
        reserved = []
        try:
            for item in items:
                self.api.reserve(item["product_id"], item["quantity"])
                reserved.append(item)
        except Exception:
            # Rollback partial reservations
            self.release(reserved)
            raise

    def release(self, items: list[dict]):
        for item in items:
            self.api.release(item["product_id"], item["quantity"])


# notifications.py
class OrderNotifier:
    def __init__(self, email_client, analytics):
        self.email = email_client
        self.analytics = analytics

    def order_created(self, user, order):
        self.email.send_order_confirmation(user.email, order)
        self.analytics.track("order_created", {
            "order_id": order.id, "total": order.total,
        })

    def order_cancelled(self, user, order, reason):
        self.email.send_cancellation(user.email, order, reason)
        self.analytics.track("order_cancelled", {
            "order_id": order.id, "reason": reason,
        })
```

**Step 2: Thin orchestrator (~50 lines, not 800)**

```python
# order_service.py
class OrderService:
    """Orchestrates order workflows. Contains NO business logic."""

    def __init__(
        self,
        db,
        validator: OrderValidator,
        pricing: PricingCalculator,
        payment: PaymentProcessor,
        inventory: InventoryManager,
        notifier: OrderNotifier,
    ):
        self.db = db
        self.validator = validator
        self.pricing = pricing
        self.payment = payment
        self.inventory = inventory
        self.notifier = notifier

    def create_order(self, user_id, items, shipping_address, payment_info):
        # 1. Validate
        validated_items = self.validator.validate_items(items)

        # 2. Price
        pricing = self.pricing.calculate(
            user_id, validated_items, shipping_address
        )

        # 3. Charge
        charge = self.payment.charge(payment_info, pricing.total)

        # 4. Persist
        try:
            order = self.db.create_order(
                user_id=user_id,
                items=validated_items,
                pricing=pricing,
                charge_id=charge.id,
            )
        except Exception:
            self.payment.refund(charge.id, pricing.total)
            raise

        # 5. Reserve inventory
        try:
            self.inventory.reserve(validated_items)
        except Exception:
            self.payment.refund(charge.id, pricing.total)
            self.db.cancel_order(order.id, "inventory_failure")
            raise

        # 6. Notify (fire-and-forget, don't fail the order)
        try:
            user = self.db.get_user(user_id)
            self.notifier.order_created(user, order)
        except Exception:
            pass  # log but don't fail

        return order
```

**Before vs After:**

| Metric | God Class | Decomposed |
|--------|-----------|------------|
| OrderService lines | 800+ | ~50 |
| Constructor params | 8 | 5 (focused) |
| Test setup per test | Mock 8 dependencies | Mock 1-2 dependencies |
| Change blast radius | Any change risks entire class | Changes isolated to one class |
| Reusability | None (monolith) | PricingCalculator reusable in quotes, invoices |

**Key principle:** The orchestrator should read like a recipe -- "validate, price, charge, persist, reserve, notify." Each step is a single method call. All logic lives in the extracted classes.'''
    ),
    (
        "thinking/refactor-callback-hell",
        r'''Our Node.js data processing pipeline is deeply nested callback hell. It's impossible to add error handling or new steps. Refactor to async/await:

function processUserData(userId, callback) {
    db.getUser(userId, function(err, user) {
        if (err) return callback(err);
        if (!user) return callback(new Error('User not found'));

        api.fetchOrders(user.accountId, function(err, orders) {
            if (err) return callback(err);

            var enrichedOrders = [];
            var processed = 0;

            if (orders.length === 0) {
                return callback(null, { user: user, orders: [] });
            }

            orders.forEach(function(order) {
                api.getOrderDetails(order.id, function(err, details) {
                    if (err) return callback(err);

                    api.calculateShipping(details, user.address, function(err, shipping) {
                        if (err) return callback(err);

                        api.applyDiscount(details, user.loyaltyTier, function(err, discounted) {
                            if (err) return callback(err);

                            enrichedOrders.push({
                                ...order,
                                details: discounted,
                                shipping: shipping,
                            });
                            processed++;

                            if (processed === orders.length) {
                                analytics.track('user_data_processed', {
                                    userId: userId,
                                    orderCount: orders.length,
                                }, function(err) {
                                    if (err) console.error('Analytics failed:', err);
                                    // Don't fail on analytics error
                                    cache.set('user:' + userId, JSON.stringify({
                                        user: user,
                                        orders: enrichedOrders,
                                    }), function(err) {
                                        if (err) console.error('Cache failed:', err);
                                        callback(null, {
                                            user: user,
                                            orders: enrichedOrders,
                                        });
                                    });
                                });
                            }
                        });
                    });
                });
            });
        });
    });
}''',
        r'''<think>
Let me analyze this callback hell:

1. Get user from DB
2. Fetch orders for user
3. For each order (in parallel implicitly, but with a manual counter):
   a. Get order details
   b. Calculate shipping
   c. Apply discount
4. Track analytics (fire-and-forget)
5. Cache the result (fire-and-forget)
6. Return result

Bugs in the original:
1. **The callback can be called multiple times!** If `getOrderDetails` fails for two orders, `callback(err)` is called twice. The `processed` counter check doesn't prevent early error callbacks.
2. **Order of enrichedOrders is non-deterministic** -- forEach with async callbacks completes in arbitrary order.
3. **No cleanup on partial failure** -- if order 3 of 5 fails, orders 1-2 are already pushed to enrichedOrders but we error out.

Refactoring approach:
1. Promisify all callback-based APIs (or use util.promisify)
2. Use async/await for sequential operations
3. Use Promise.all for parallel order enrichment
4. Use try/catch for error handling
5. Separate concerns into helper functions

Let me write the refactored version.
</think>

The callback version has bugs beyond just readability: the callback can fire multiple times on parallel failures, and order results are non-deterministic. Here's the refactored version:

```javascript
import { promisify } from 'util';

// Promisify all callback-based APIs once
const dbGetUser = promisify(db.getUser.bind(db));
const apiFetchOrders = promisify(api.fetchOrders.bind(api));
const apiGetOrderDetails = promisify(api.getOrderDetails.bind(api));
const apiCalculateShipping = promisify(api.calculateShipping.bind(api));
const apiApplyDiscount = promisify(api.applyDiscount.bind(api));
const analyticsTrack = promisify(analytics.track.bind(analytics));
const cacheSet = promisify(cache.set.bind(cache));

/**
 * Enrich a single order with details, shipping, and discount.
 * Extracted for testability and clarity.
 */
async function enrichOrder(order, userAddress, loyaltyTier) {
    const details = await apiGetOrderDetails(order.id);

    // Shipping and discount are independent -- run in parallel
    const [shipping, discounted] = await Promise.all([
        apiCalculateShipping(details, userAddress),
        apiApplyDiscount(details, loyaltyTier),
    ]);

    return {
        ...order,
        details: discounted,
        shipping,
    };
}

/**
 * Fire-and-forget side effects. Failures are logged, not thrown.
 */
async function recordSideEffects(userId, result) {
    const tasks = [
        analyticsTrack('user_data_processed', {
            userId,
            orderCount: result.orders.length,
        }).catch(err => console.error('Analytics failed:', err)),

        cacheSet(
            `user:${userId}`,
            JSON.stringify(result),
        ).catch(err => console.error('Cache failed:', err)),
    ];
    await Promise.allSettled(tasks);
}

/**
 * Main pipeline: clean, linear, easy to add/remove steps.
 */
async function processUserData(userId) {
    // Step 1: Get user
    const user = await dbGetUser(userId);
    if (!user) {
        throw new Error('User not found');
    }

    // Step 2: Fetch orders
    const orders = await apiFetchOrders(user.accountId);

    // Step 3: Enrich all orders in parallel (deterministic order via map)
    const enrichedOrders = await Promise.all(
        orders.map(order => enrichOrder(order, user.address, user.loyaltyTier))
    );

    const result = { user, orders: enrichedOrders };

    // Step 4: Side effects (don't block or fail the response)
    recordSideEffects(userId, result).catch(() => {});

    return result;
}
```

**Bugs fixed beyond readability:**

| Bug | Callback Version | Async/Await Version |
|-----|-----------------|---------------------|
| Double callback on parallel error | `callback(err)` called once per failed order | `Promise.all` rejects once, cleanly |
| Non-deterministic order | `enrichedOrders.push()` in completion order | `Promise.all` preserves input order |
| Shipping blocks discount | Sequential (unnecessarily) | Parallel via `Promise.all` |
| Analytics blocks response | User waits for analytics + cache | Fire-and-forget with `Promise.allSettled` |

**Performance improvement:** The original runs shipping and discount sequentially per order. The refactored version runs them in parallel, and enriches all orders in parallel. For 10 orders with 100ms per API call:
```
Original:  10 * (details + shipping + discount) = 10 * 300ms = 3000ms
Refactored: max(details + max(shipping, discount)) = 200ms  (all parallel)
```

**Usage migration:**
```javascript
// Before (callback):
processUserData(123, (err, result) => {
    if (err) handleError(err);
    else render(result);
});

// After (async/await):
try {
    const result = await processUserData(123);
    render(result);
} catch (err) {
    handleError(err);
}
```'''
    ),
    (
        "thinking/refactor-tight-coupling-to-di",
        r'''Our notification service is tightly coupled to specific implementations. We can't test it without sending real emails and SMS, and adding new channels (Slack, push notifications) requires modifying the core class:

import smtplib
from twilio.rest import Client as TwilioClient
from email.mime.text import MIMEText
import os

class NotificationService:
    def __init__(self):
        # Hardcoded dependencies -- can't mock for testing
        self.smtp = smtplib.SMTP(os.environ["SMTP_HOST"], 587)
        self.smtp.starttls()
        self.smtp.login(os.environ["SMTP_USER"], os.environ["SMTP_PASS"])

        self.twilio = TwilioClient(
            os.environ["TWILIO_SID"],
            os.environ["TWILIO_TOKEN"],
        )
        self.twilio_from = os.environ["TWILIO_FROM"]

    def notify_user(self, user, event_type, data):
        if event_type == "order_confirmed":
            self._send_email(
                user.email,
                "Order Confirmed",
                f"Your order #{data['order_id']} is confirmed!",
            )
            if user.phone:
                self._send_sms(
                    user.phone,
                    f"Order #{data['order_id']} confirmed!",
                )

        elif event_type == "password_reset":
            self._send_email(
                user.email,
                "Password Reset",
                f"Reset link: {data['reset_url']}",
            )

        elif event_type == "shipping_update":
            self._send_email(
                user.email,
                "Shipping Update",
                f"Tracking: {data['tracking_number']}",
            )
            if user.phone:
                self._send_sms(
                    user.phone,
                    f"Your package is on the way! Track: {data['tracking_number']}",
                )

    def _send_email(self, to, subject, body):
        msg = MIMEText(body)
        msg["Subject"] = subject
        msg["From"] = os.environ["FROM_EMAIL"]
        msg["To"] = to
        self.smtp.send_message(msg)

    def _send_sms(self, to, body):
        self.twilio.messages.create(
            body=body, from_=self.twilio_from, to=to,
        )

Refactor this to use dependency injection and make it extensible.''',
        r'''<think>
Problems with the current design:

1. **Tight coupling:** SMTP and Twilio clients are created in `__init__`, not injected. Can't test without real credentials.
2. **Not extensible:** Adding Slack requires modifying `notify_user` and adding new `_send_slack` method.
3. **Mixed responsibilities:** Routing logic (which channel for which event) is mixed with delivery logic (how to send email/SMS).
4. **No abstraction:** Email and SMS are concrete implementations, not interfaces.
5. **Hardcoded message templates:** Templates are inline strings, not configurable.

Refactoring plan:
1. Define a `NotificationChannel` interface (protocol in Python)
2. Implement `EmailChannel`, `SMSChannel`, `SlackChannel` etc.
3. Define a routing configuration: event_type -> list of channels
4. `NotificationService` takes channels as dependencies (DI)
5. Message formatting is separated from delivery

This follows:
- Open/Closed Principle: add channels without modifying existing code
- Dependency Inversion: depend on abstractions, not concretions
- Single Responsibility: each class does one thing
</think>

Three design problems: tight coupling (can't test), violation of Open/Closed (can't extend), and mixed responsibilities (routing + delivery + formatting in one class).

**Step 1: Define the abstraction**

```python
# channels/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Protocol

@dataclass
class Message:
    recipient: str      # email, phone, slack channel, etc.
    subject: str
    body: str
    html_body: str = ""

class NotificationChannel(Protocol):
    """Any channel must implement this interface."""

    @property
    def channel_name(self) -> str: ...

    def send(self, message: Message) -> bool: ...

    def is_available(self) -> bool: ...
```

**Step 2: Implement channels (each independently testable)**

```python
# channels/email.py
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

class EmailChannel:
    channel_name = "email"

    def __init__(self, smtp_host: str, smtp_port: int,
                 username: str, password: str, from_email: str):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_email = from_email

    def send(self, message: Message) -> bool:
        msg = MIMEText(message.body)
        msg["Subject"] = message.subject
        msg["From"] = self.from_email
        msg["To"] = message.recipient
        with smtplib.SMTP(self.smtp_host, self.smtp_port) as smtp:
            smtp.starttls()
            smtp.login(self.username, self.password)
            smtp.send_message(msg)
        return True

    def is_available(self) -> bool:
        try:
            with smtplib.SMTP(self.smtp_host, self.smtp_port, timeout=5):
                return True
        except Exception:
            return False


# channels/sms.py
class SMSChannel:
    channel_name = "sms"

    def __init__(self, twilio_client, from_number: str):
        self.client = twilio_client  # injected, not created
        self.from_number = from_number

    def send(self, message: Message) -> bool:
        self.client.messages.create(
            body=message.body,
            from_=self.from_number,
            to=message.recipient,
        )
        return True

    def is_available(self) -> bool:
        return True  # Twilio is always "available"


# channels/slack.py -- added without modifying existing code!
class SlackChannel:
    channel_name = "slack"

    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send(self, message: Message) -> bool:
        import requests
        resp = requests.post(self.webhook_url, json={
            "text": f"*{message.subject}*\n{message.body}",
        })
        return resp.status_code == 200

    def is_available(self) -> bool:
        return bool(self.webhook_url)
```

**Step 3: Routing configuration (separate from delivery)**

```python
# routing.py
from dataclasses import dataclass, field

@dataclass
class NotificationRoute:
    channels: list[str]                  # ["email", "sms"]
    template_subject: str
    template_body: str
    condition: callable = field(default=lambda user, data: True)

# Configuration: which events go to which channels
ROUTES: dict[str, NotificationRoute] = {
    "order_confirmed": NotificationRoute(
        channels=["email", "sms"],
        template_subject="Order Confirmed",
        template_body="Your order #{order_id} is confirmed!",
    ),
    "password_reset": NotificationRoute(
        channels=["email"],  # never SMS a reset link
        template_subject="Password Reset",
        template_body="Reset link: {reset_url}",
    ),
    "shipping_update": NotificationRoute(
        channels=["email", "sms", "slack"],
        template_subject="Shipping Update",
        template_body="Tracking: {tracking_number}",
    ),
}
```

**Step 4: Thin orchestrator with dependency injection**

```python
# notification_service.py
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class NotificationService:
    def __init__(
        self,
        channels: dict[str, NotificationChannel],
        routes: dict[str, NotificationRoute],
    ):
        self.channels = channels  # injected, not created
        self.routes = routes

    def notify_user(self, user, event_type: str, data: dict):
        route = self.routes.get(event_type)
        if not route:
            logger.warning(f"No route for event: {event_type}")
            return

        subject = route.template_subject.format(**data)
        body = route.template_body.format(**data)

        for channel_name in route.channels:
            channel = self.channels.get(channel_name)
            if not channel:
                continue

            recipient = self._get_recipient(user, channel_name)
            if not recipient:
                continue

            try:
                channel.send(Message(
                    recipient=recipient,
                    subject=subject,
                    body=body,
                ))
            except Exception as e:
                logger.error(
                    f"Failed to send {channel_name} for {event_type}: {e}"
                )

    def _get_recipient(self, user, channel_name: str) -> Optional[str]:
        mapping = {
            "email": getattr(user, "email", None),
            "sms": getattr(user, "phone", None),
            "slack": getattr(user, "slack_id", None),
        }
        return mapping.get(channel_name)
```

**Step 5: Testable without real services**

```python
# tests/test_notifications.py
class FakeChannel:
    """Test double -- no real email/SMS/Slack."""
    def __init__(self, name):
        self.channel_name = name
        self.sent = []

    def send(self, message):
        self.sent.append(message)
        return True

    def is_available(self):
        return True

def test_order_confirmed_sends_email_and_sms():
    email = FakeChannel("email")
    sms = FakeChannel("sms")
    service = NotificationService(
        channels={"email": email, "sms": sms},
        routes=ROUTES,
    )

    user = FakeUser(email="a@b.com", phone="+1234567890")
    service.notify_user(user, "order_confirmed", {"order_id": "ORD-1"})

    assert len(email.sent) == 1
    assert "ORD-1" in email.sent[0].body
    assert len(sms.sent) == 1

def test_password_reset_email_only():
    email = FakeChannel("email")
    sms = FakeChannel("sms")
    service = NotificationService(
        channels={"email": email, "sms": sms},
        routes=ROUTES,
    )

    user = FakeUser(email="a@b.com", phone="+1234567890")
    service.notify_user(user, "password_reset", {"reset_url": "https://..."})

    assert len(email.sent) == 1
    assert len(sms.sent) == 0  # SMS not in route for password_reset
```

**Adding a new channel (e.g., push notifications) requires:**
1. Implement `PushChannel` class (follows Protocol)
2. Add `"push"` to relevant routes in config
3. Register channel in DI container

**Zero modifications to `NotificationService`, `EmailChannel`, or `SMSChannel`.**'''
    ),
    (
        "thinking/refactor-inheritance-to-composition",
        r'''Our reporting system uses deep inheritance and it's become a nightmare to modify. Changing the base class breaks child classes in unexpected ways:

class BaseReport:
    def __init__(self, data_source, date_range):
        self.data_source = data_source
        self.date_range = date_range
        self.data = None
        self.formatted_data = None

    def generate(self):
        self.data = self.fetch_data()
        self.data = self.filter_data(self.data)
        self.data = self.transform_data(self.data)
        self.formatted_data = self.format_output(self.data)
        return self.formatted_data

    def fetch_data(self):
        return self.data_source.query(self.date_range)

    def filter_data(self, data):
        return data  # override in subclass

    def transform_data(self, data):
        return data  # override in subclass

    def format_output(self, data):
        raise NotImplementedError

class SalesReport(BaseReport):
    def filter_data(self, data):
        return [r for r in data if r["type"] == "sale"]

    def transform_data(self, data):
        # Group by product
        grouped = {}
        for r in data:
            grouped.setdefault(r["product"], []).append(r)
        return grouped

    def format_output(self, data):
        return {"type": "table", "columns": ["Product", "Total"], "rows": data}

class PDFSalesReport(SalesReport):
    def format_output(self, data):
        # Must call super but also convert to PDF
        table = super().format_output(data)
        return self.render_pdf(table)

    def render_pdf(self, table):
        # ... 50 lines of PDF generation

class EmailablePDFSalesReport(PDFSalesReport):
    def generate(self):
        result = super().generate()
        self.send_email(result)
        return result

    def send_email(self, pdf):
        # ... email logic

class ScheduledEmailablePDFSalesReport(EmailablePDFSalesReport):
    # 4 levels deep... and we need ScheduledCSVInventoryReport too?
    pass

Show how to refactor from inheritance to composition.''',
        r'''<think>
The inheritance hierarchy is:
```
BaseReport
  -> SalesReport
    -> PDFSalesReport
      -> EmailablePDFSalesReport
        -> ScheduledEmailablePDFSalesReport
```

This is the classic "inheritance explosion" problem. To get a ScheduledCSVInventoryReport, you'd need another deep hierarchy. The number of classes grows multiplicatively:

- Report types: Sales, Inventory, Customer, etc.
- Formats: Table, PDF, CSV, Excel
- Delivery: Email, Upload, Print
- Scheduling: Immediate, Scheduled, Recurring

With inheritance: types * formats * delivery * scheduling = explosion
With composition: types + formats + delivery + scheduling = manageable

The Template Method pattern (BaseReport.generate calling overrideable methods) is actually OK for the high-level flow. The problem is that formatting, delivery, and scheduling are orthogonal concerns being forced into the inheritance chain.

Composition approach:
1. **DataFetcher** -- gets data from source (strategy pattern)
2. **DataTransformer** -- filters and transforms (pipeline of functions)
3. **Formatter** -- converts to output format (PDF, CSV, table)
4. **Deliverer** -- sends the output (email, upload, etc.)
5. **ReportBuilder** -- composes these together

This is essentially the Strategy pattern for each concern.
</think>

The inheritance tree grows exponentially because it conflates four orthogonal concerns: data logic, formatting, delivery, and scheduling. With composition, you combine them freely.

**The explosion problem:**
```
                     inheritance (multiplicative)
Sales    x PDF  x Email    x Scheduled = need a class for every combo
Sales    x CSV  x Upload   x Immediate = another class
Inventory x PDF x Email    x Scheduled = yet another class
... (types * formats * delivery * scheduling) = dozens of classes

                     composition (additive)
Sales, Inventory, Customer     = 3 data strategies
PDF, CSV, Table, Excel         = 4 formatters
Email, Upload, Print, Slack    = 4 deliverers
Immediate, Scheduled, Recurring = 3 schedulers
                               = 14 total components, any combination
```

**Refactored with composition:**

```python
# protocols.py -- define the interfaces
from typing import Protocol, Any

class DataFetcher(Protocol):
    def fetch(self, data_source, date_range) -> list[dict]: ...

class DataFilter(Protocol):
    def filter(self, data: list[dict]) -> list[dict]: ...

class DataTransformer(Protocol):
    def transform(self, data: list[dict]) -> Any: ...

class Formatter(Protocol):
    def format(self, data: Any) -> bytes | str | dict: ...

class Deliverer(Protocol):
    def deliver(self, output: Any, metadata: dict) -> None: ...


# fetchers.py -- data retrieval strategies
class DefaultFetcher:
    def fetch(self, data_source, date_range):
        return data_source.query(date_range)

# filters.py -- composable filters
class TypeFilter:
    def __init__(self, record_type: str):
        self.record_type = record_type

    def filter(self, data):
        return [r for r in data if r["type"] == self.record_type]

class MinAmountFilter:
    def __init__(self, min_amount: float):
        self.min_amount = min_amount

    def filter(self, data):
        return [r for r in data if r.get("amount", 0) >= self.min_amount]

class CompositeFilter:
    """Chain multiple filters together."""
    def __init__(self, *filters):
        self.filters = filters

    def filter(self, data):
        for f in self.filters:
            data = f.filter(data)
        return data


# transformers.py -- data transformation strategies
class GroupByTransformer:
    def __init__(self, key: str):
        self.key = key

    def transform(self, data):
        grouped = {}
        for r in data:
            grouped.setdefault(r[self.key], []).append(r)
        return grouped

class AggregateTransformer:
    def __init__(self, group_key: str, sum_key: str):
        self.group_key = group_key
        self.sum_key = sum_key

    def transform(self, data):
        totals = {}
        for r in data:
            key = r[self.group_key]
            totals[key] = totals.get(key, 0) + r[self.sum_key]
        return totals


# formatters.py -- output format strategies
class TableFormatter:
    def __init__(self, columns: list[str]):
        self.columns = columns

    def format(self, data):
        return {"type": "table", "columns": self.columns, "rows": data}

class PDFFormatter:
    def format(self, data):
        # PDF generation logic
        return render_pdf(data)

class CSVFormatter:
    def format(self, data):
        import csv, io
        output = io.StringIO()
        writer = csv.writer(output)
        # ... write data
        return output.getvalue()


# deliverers.py -- output delivery strategies
class EmailDeliverer:
    def __init__(self, email_client, recipients: list[str]):
        self.client = email_client
        self.recipients = recipients

    def deliver(self, output, metadata):
        self.client.send(
            to=self.recipients,
            subject=f"Report: {metadata.get('name', 'Report')}",
            attachment=output,
        )

class FileDeliverer:
    def __init__(self, output_dir: str):
        self.output_dir = output_dir

    def deliver(self, output, metadata):
        path = f"{self.output_dir}/{metadata['name']}_{metadata['date']}"
        with open(path, 'wb') as f:
            f.write(output if isinstance(output, bytes) else output.encode())

class NoOpDeliverer:
    def deliver(self, output, metadata):
        pass  # just return the output


# report.py -- the composed report runner
class Report:
    """Composes strategies. No inheritance needed."""

    def __init__(
        self,
        name: str,
        fetcher: DataFetcher,
        filter: DataFilter,
        transformer: DataTransformer,
        formatter: Formatter,
        deliverer: Deliverer = NoOpDeliverer(),
    ):
        self.name = name
        self.fetcher = fetcher
        self.filter = filter
        self.transformer = transformer
        self.formatter = formatter
        self.deliverer = deliverer

    def generate(self, data_source, date_range):
        data = self.fetcher.fetch(data_source, date_range)
        data = self.filter.filter(data)
        transformed = self.transformer.transform(data)
        output = self.formatter.format(transformed)

        metadata = {"name": self.name, "date": str(date_range)}
        self.deliverer.deliver(output, metadata)
        return output


# Usage: compose any combination without new classes
sales_pdf_email = Report(
    name="Monthly Sales",
    fetcher=DefaultFetcher(),
    filter=TypeFilter("sale"),
    transformer=GroupByTransformer("product"),
    formatter=PDFFormatter(),
    deliverer=EmailDeliverer(email_client, ["boss@co.com"]),
)

inventory_csv_file = Report(
    name="Inventory",
    fetcher=DefaultFetcher(),
    filter=CompositeFilter(
        TypeFilter("inventory"),
        MinAmountFilter(100),
    ),
    transformer=AggregateTransformer("warehouse", "quantity"),
    formatter=CSVFormatter(),
    deliverer=FileDeliverer("/reports/"),
)
```

**Key insight:** When you see class names like `ScheduledEmailablePDFSalesReport`, each adjective is a separate axis of variation. Inheritance can only extend along ONE axis. Composition handles all of them independently.'''
    ),
    (
        "thinking/refactor-feature-flags",
        r'''Our codebase is littered with stale feature flags. Some flags are 2+ years old and nobody knows if they can be removed. The code has become unreadable:

def process_payment(order):
    if feature_flags.is_enabled("new_payment_flow"):
        if feature_flags.is_enabled("stripe_v2"):
            if feature_flags.is_enabled("3ds_required"):
                result = stripe_v2_3ds_charge(order)
            else:
                result = stripe_v2_charge(order)
        elif feature_flags.is_enabled("paypal_enabled"):
            result = paypal_charge(order)
        else:
            result = stripe_v1_charge(order)
    else:
        result = legacy_charge(order)

    if feature_flags.is_enabled("fraud_check_v2"):
        fraud_result = fraud_check_v2(result)
    elif feature_flags.is_enabled("fraud_check_v1"):
        fraud_result = fraud_check_v1(result)
    else:
        fraud_result = None

    if feature_flags.is_enabled("new_receipt_format"):
        send_receipt_v2(order, result)
    else:
        send_receipt(order, result)

    if feature_flags.is_enabled("analytics_v2"):
        if feature_flags.is_enabled("detailed_analytics"):
            track_detailed(order, result, fraud_result)
        else:
            track_v2(order, result)
    else:
        track_v1(order, result)

    return result

We have 47 feature flags in the system. How do we clean this up systematically?''',
        r'''<think>
This is a common problem. The feature flags have accumulated without a lifecycle management process. Let me design both the cleanup process and the prevention strategy.

Problems with the current code:
1. Nested conditionals make the code hard to follow (8 possible paths through process_payment)
2. Stale flags that are always on/off but never removed
3. No documentation of what each flag does or when it was introduced
4. No owner assigned to flags
5. Combinatorial explosion of flag interactions (2^n possible states)

Cleanup approach:
1. **Audit** -- catalog all 47 flags with status, owner, and age
2. **Classify** -- categorize by type and lifecycle stage
3. **Remove stale flags** -- the easy wins (flags that are 100% on or 100% off)
4. **Simplify remaining flags** -- strategy pattern instead of nested ifs
5. **Prevent future accumulation** -- add expiration dates and ownership

Let me design this systematically.
</think>

This is a feature flag lifecycle management problem. Here's a systematic cleanup in four phases:

**Phase 1: Audit all 47 flags (1 day)**

```python
# scripts/audit_feature_flags.py
"""Scan codebase and flag service to classify all flags."""
import re
import json
from pathlib import Path
from datetime import datetime, timedelta

def audit_flags(codebase_path: str, flag_service) -> list[dict]:
    # Find all flag references in code
    flag_pattern = re.compile(
        r'feature_flags\.is_enabled\(["\'](\w+)["\']\)'
    )
    code_refs = {}
    for py_file in Path(codebase_path).rglob("*.py"):
        content = py_file.read_text()
        for match in flag_pattern.finditer(content):
            flag_name = match.group(1)
            code_refs.setdefault(flag_name, []).append(str(py_file))

    # Get runtime data from flag service
    results = []
    for flag_name, files in code_refs.items():
        flag_data = flag_service.get_flag(flag_name)
        results.append({
            "name": flag_name,
            "files": files,
            "file_count": len(files),
            "created_at": flag_data.get("created_at", "unknown"),
            "age_days": (
                (datetime.now() - datetime.fromisoformat(flag_data["created_at"])).days
                if flag_data.get("created_at") else None
            ),
            "enabled_pct": flag_data.get("enabled_percentage", "unknown"),
            "last_toggled": flag_data.get("last_toggled", "never"),
            "owner": flag_data.get("owner", "UNOWNED"),
            "classification": classify_flag(flag_data),
        })

    return sorted(results, key=lambda f: f.get("age_days") or 9999, reverse=True)

def classify_flag(flag_data) -> str:
    enabled_pct = flag_data.get("enabled_percentage", 50)
    age_days = flag_data.get("age_days", 0)

    if enabled_pct == 100 and age_days > 30:
        return "STALE_ON"      # always on, safe to remove (keep code, delete flag)
    elif enabled_pct == 0 and age_days > 30:
        return "STALE_OFF"     # always off, safe to remove (delete code AND flag)
    elif age_days > 365:
        return "ANCIENT"       # needs investigation
    elif enabled_pct in (0, 100):
        return "RECENTLY_DECIDED"  # decided but not yet cleaned up
    else:
        return "ACTIVE"        # actually in use for gradual rollout

# Expected output:
# STALE_ON:     18 flags  -> Remove flag checks, keep the "enabled" code path
# STALE_OFF:     7 flags  -> Remove flag checks AND the dead code
# ANCIENT:       8 flags  -> Investigate with team, then remove
# ACTIVE:       14 flags  -> Keep, but refactor how they're used
```

**Phase 2: Remove stale flags (1-2 weeks)**

```python
# BEFORE: nested flag spaghetti
def process_payment(order):
    if feature_flags.is_enabled("new_payment_flow"):
        if feature_flags.is_enabled("stripe_v2"): ...
    else:
        result = legacy_charge(order)  # STALE_ON: remove this dead path

# AFTER removing STALE_ON "new_payment_flow" (always True for 18 months):
def process_payment(order):
    if feature_flags.is_enabled("stripe_v2"): ...
    # legacy_charge() deleted entirely

# AFTER removing STALE_OFF "paypal_enabled" (always False for 6 months):
def process_payment(order):
    if feature_flags.is_enabled("stripe_v2"): ...
    # paypal_charge() deleted entirely

# Script to generate removal PRs:
# For each STALE_ON flag:
#   1. Replace `if flag: A else: B` with just `A`
#   2. Delete B code path
#   3. Remove flag from service
# For each STALE_OFF flag:
#   1. Replace `if flag: A else: B` with just `B`
#   2. Delete A code path
#   3. Remove flag from service
```

**Phase 3: Refactor remaining active flags with strategy pattern**

```python
# BEFORE: nested ifs for payment selection
def process_payment(order):
    if feature_flags.is_enabled("stripe_v2"):
        if feature_flags.is_enabled("3ds_required"):
            result = stripe_v2_3ds_charge(order)
        else:
            result = stripe_v2_charge(order)
    else:
        result = stripe_v1_charge(order)

# AFTER: strategy pattern -- flag selects strategy, no nesting
from typing import Protocol

class PaymentStrategy(Protocol):
    def charge(self, order) -> ChargeResult: ...

PAYMENT_STRATEGIES = {
    "stripe_v2_3ds": StripeV2With3DS(),
    "stripe_v2":     StripeV2(),
    "stripe_v1":     StripeV1(),
}

def get_payment_strategy() -> PaymentStrategy:
    """Single flag lookup, returns the right strategy."""
    name = feature_flags.get_variant("payment_strategy",
                                     default="stripe_v1")
    return PAYMENT_STRATEGIES[name]

def process_payment(order):
    strategy = get_payment_strategy()
    result = strategy.charge(order)
    # ... rest of pipeline
```

**Phase 4: Prevent future accumulation**

```python
# feature_flags/managed_flag.py
from dataclasses import dataclass
from datetime import datetime, timedelta

@dataclass
class ManagedFlag:
    name: str
    owner: str               # who is responsible for cleanup
    created_at: datetime
    expires_at: datetime      # REQUIRED: when must this flag be removed
    description: str
    jira_ticket: str          # cleanup ticket created at flag creation time

    def is_expired(self) -> bool:
        return datetime.now() > self.expires_at

# CI check that runs on every build
def check_expired_flags():
    """Fails the build if any flag is past its expiration date."""
    expired = [
        f for f in get_all_managed_flags()
        if f.is_expired()
    ]
    if expired:
        names = [f"{f.name} (owner: {f.owner}, expired: {f.expires_at})"
                 for f in expired]
        raise RuntimeError(
            f"Expired feature flags must be cleaned up:\n"
            + "\n".join(names)
        )

# Linter rule: flag creation requires expiration
# BAD:
#   feature_flags.create("my_flag")
# GOOD:
#   feature_flags.create("my_flag",
#       owner="alice",
#       expires_at=datetime.now() + timedelta(days=90),
#       cleanup_ticket="JIRA-1234")
```

**Cleanup summary for the 47 flags:**

| Classification | Count | Action | Effort |
|---------------|-------|--------|--------|
| STALE_ON | ~18 | Remove flag check, keep enabled code | 1 PR each |
| STALE_OFF | ~7 | Remove flag check AND dead code | 1 PR each |
| ANCIENT | ~8 | Investigate, then remove | 1 day |
| ACTIVE | ~14 | Refactor to strategy pattern | 1 week |

**Rule going forward:** Every feature flag gets a 90-day expiration date and a cleanup Jira ticket at creation time. CI fails if expired flags exist.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
