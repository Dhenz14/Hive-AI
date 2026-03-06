r"""Thinking-trace pairs: extract refactoring code review."""

PAIRS = [
    ("thinking/code-review", r'''Review this code and suggest extract method refactoring:

```python
class OrderProcessor:
    def process_order(self, order_data):
        # Validate order
        if not order_data.get("items"):
            raise ValueError("Order must have items")
        if not order_data.get("customer_id"):
            raise ValueError("Customer ID required")

        total = 0
        for item in order_data["items"]:
            if item["quantity"] <= 0:
                raise ValueError(f"Invalid quantity for {item['product_id']}")
            product = self.db.get_product(item["product_id"])
            if not product:
                raise ValueError(f"Product {item['product_id']} not found")
            if product.stock < item["quantity"]:
                raise ValueError(f"Insufficient stock for {product.name}")
            item_price = product.price * item["quantity"]
            if item.get("discount_code"):
                discount = self.db.get_discount(item["discount_code"])
                if discount and discount.is_valid():
                    if discount.type == "percent":
                        item_price *= (1 - discount.value / 100)
                    elif discount.type == "fixed":
                        item_price -= discount.value
                    if item_price < 0:
                        item_price = 0
            total += item_price

        # Apply order-level discount
        if order_data.get("promo_code"):
            promo = self.db.get_promo(order_data["promo_code"])
            if promo and promo.is_valid():
                if promo.min_order and total < promo.min_order:
                    pass
                else:
                    if promo.type == "percent":
                        total *= (1 - promo.value / 100)
                    elif promo.type == "fixed":
                        total -= promo.value
                    if total < 0:
                        total = 0

        # Calculate tax
        customer = self.db.get_customer(order_data["customer_id"])
        if customer.state in ["CA", "NY", "TX"]:
            tax_rates = {"CA": 0.0725, "NY": 0.08, "TX": 0.0625}
            tax = total * tax_rates[customer.state]
        elif customer.country != "US":
            tax = total * 0.20  # VAT
        else:
            tax = 0

        # Calculate shipping
        total_weight = sum(
            self.db.get_product(i["product_id"]).weight * i["quantity"]
            for i in order_data["items"]
        )
        if total_weight < 1:
            shipping = 5.99
        elif total_weight < 5:
            shipping = 9.99
        elif total_weight < 20:
            shipping = 14.99
        else:
            shipping = 24.99

        if order_data.get("shipping_method") == "express":
            shipping *= 2
        if total > 100:
            shipping = 0  # Free shipping

        grand_total = total + tax + shipping

        # Create order
        order = self.db.create_order(
            customer_id=order_data["customer_id"],
            items=order_data["items"],
            subtotal=total,
            tax=tax,
            shipping=shipping,
            total=grand_total,
            status="pending"
        )

        # Send notifications
        self.email_service.send_confirmation(customer.email, order)
        if customer.phone:
            self.sms_service.send_confirmation(customer.phone, order)
        if total > 500:
            self.slack_service.notify_high_value_order(order)

        return order
```''', r'''<think>
This is a classic "god method" that does far too many things. Let me identify the distinct responsibilities and suggest extract method refactoring.

The method currently handles:
1. Order validation
2. Item-level price calculation with discounts
3. Order-level promo code application
4. Tax calculation
5. Shipping calculation
6. Order creation/persistence
7. Notification sending

Each of these should be its own method. Let me also identify design issues:

Validation:
- Validation is mixed with price calculation (stock check during price calc)
- No input type validation (quantity could be a string)

Price calculation:
- Discount logic is duplicated between item-level and order-level (both check type == "percent" vs "fixed")
- The product is fetched again for shipping weight calculation - N+1 query pattern
- Floating point arithmetic for money

Tax calculation:
- Hardcoded tax rates in the code
- Only handles 3 US states
- Non-US customers always get 20% VAT regardless of country

Shipping:
- Magic numbers for weight thresholds and prices
- Hardcoded "free shipping over $100" business rule

Notifications:
- Sent synchronously - if email fails, the order still exists but the customer never knows
- Slack notification is only for >$500 orders - business logic in notification code

The method is about 80 lines long and handles 7 different concerns. It should be refactored into focused methods following the Single Responsibility Principle.
</think>

## Code Review: Extract Method Refactoring

### CRITICAL - God Method (80+ Lines, 7 Responsibilities)
`process_order` handles validation, pricing, discounts, tax, shipping, persistence, and notifications in a single method. This violates the Single Responsibility Principle, making the code difficult to test, modify, and debug. A change to tax logic risks breaking notification logic.

**Suggested refactoring -- extract into focused methods:**

```python
class OrderProcessor:
    def process_order(self, order_data):
        self._validate_order(order_data)
        items_with_prices = self._calculate_item_prices(order_data["items"])
        subtotal = sum(item["total"] for item in items_with_prices)
        subtotal = self._apply_promo_code(subtotal, order_data.get("promo_code"))
        customer = self.db.get_customer(order_data["customer_id"])
        tax = self._calculate_tax(subtotal, customer)
        shipping = self._calculate_shipping(items_with_prices, order_data, subtotal)
        grand_total = subtotal + tax + shipping
        order = self._persist_order(order_data, items_with_prices, subtotal, tax, shipping, grand_total)
        self._send_notifications(customer, order, subtotal)
        return order
```

### HIGH - Duplicated Discount Logic
The discount calculation pattern (check type, apply percent or fixed, clamp to zero) appears twice -- once for item-level discounts and once for promo codes. This violates DRY.

**Extract method:**
```python
def _apply_discount(self, amount, discount):
    if not discount or not discount.is_valid():
        return amount
    if discount.type == "percent":
        amount *= (1 - discount.value / 100)
    elif discount.type == "fixed":
        amount -= discount.value
    return max(amount, 0)
```

### HIGH - Hardcoded Tax Rates
Tax rates are hardcoded in the method body. These change periodically and vary by jurisdiction. They should be in a configuration source or database.

**Extract to configuration:**
```python
class TaxCalculator:
    def __init__(self, tax_config):
        self.rates = tax_config

    def calculate(self, subtotal, customer):
        rate = self.rates.get(customer.state, self.rates.get(customer.country, 0))
        return subtotal * rate
```

### HIGH - N+1 Product Query for Shipping
Products are fetched individually during price calculation, then fetched AGAIN during shipping weight calculation. Each item triggers a separate database query.

**Fix:** Fetch all products once and pass them through:
```python
def _fetch_products(self, items):
    product_ids = [item["product_id"] for item in items]
    return {p.id: p for p in self.db.get_products_by_ids(product_ids)}
```

### MEDIUM - Synchronous Notifications
Email, SMS, and Slack notifications are sent synchronously. If the email service is slow or down, the order creation appears to hang or fail, even though the order was successfully created in the database.

**Extract and make async:**
```python
def _send_notifications(self, customer, order, subtotal):
    # Queue for async processing
    self.task_queue.enqueue(
        "send_order_notifications",
        customer_id=customer.id,
        order_id=order.id
    )
```

### MEDIUM - Magic Numbers for Shipping
Weight thresholds (1, 5, 20) and prices (5.99, 9.99, 14.99, 24.99) are hardcoded. The "free shipping over $100" rule and "express = 2x" multiplier are buried in the code.

**Extract to a shipping calculator:**
```python
class ShippingCalculator:
    WEIGHT_TIERS = [
        (1, 5.99), (5, 9.99), (20, 14.99), (float("inf"), 24.99)
    ]
    FREE_SHIPPING_THRESHOLD = 100
    EXPRESS_MULTIPLIER = 2

    def calculate(self, total_weight, subtotal, method="standard"):
        # ... clean, testable logic
```

### MEDIUM - Validation Mixed with Business Logic
Stock checking happens inside the price calculation loop rather than in a separate validation phase. This means partial price calculations occur before a stock validation error is raised.

### LOW - Float Arithmetic for Money
All monetary calculations use float, which causes rounding errors. Use `decimal.Decimal` for financial precision.'''),

    ("thinking/code-review", r'''Review this code and suggest extract class refactoring:

```python
class UserManager:
    def __init__(self, db, email_client, sms_client, cache, logger):
        self.db = db
        self.email_client = email_client
        self.sms_client = sms_client
        self.cache = cache
        self.logger = logger

    def create_user(self, data):
        if len(data.get("password", "")) < 8:
            raise ValueError("Password too short")
        if not re.match(r"[^@]+@[^@]+\.[^@]+", data.get("email", "")):
            raise ValueError("Invalid email")
        if self.db.get_user_by_email(data["email"]):
            raise ValueError("Email already registered")

        import bcrypt
        hashed = bcrypt.hashpw(data["password"].encode(), bcrypt.gensalt())
        user = self.db.create_user(
            username=data["username"],
            email=data["email"],
            password_hash=hashed.decode()
        )

        self.cache.delete(f"user_list")
        self.cache.delete(f"user_count")

        verification_token = secrets.token_urlsafe(32)
        self.db.store_verification_token(user.id, verification_token)

        html = f"""
        <h1>Welcome {user.username}!</h1>
        <p>Please verify your email by clicking
        <a href="https://myapp.com/verify?token={verification_token}">here</a>
        </p>
        """
        self.email_client.send(
            to=user.email,
            subject="Welcome to MyApp",
            html=html
        )

        if data.get("phone"):
            self.sms_client.send(
                to=data["phone"],
                message=f"Welcome to MyApp! Your account has been created."
            )

        self.logger.info(f"User created: {user.id} ({user.email})")

        return user

    def update_profile(self, user_id, data):
        user = self.db.get_user(user_id)
        if not user:
            raise ValueError("User not found")

        if "email" in data and data["email"] != user.email:
            if not re.match(r"[^@]+@[^@]+\.[^@]+", data["email"]):
                raise ValueError("Invalid email")
            if self.db.get_user_by_email(data["email"]):
                raise ValueError("Email already in use")

            old_email = user.email
            user.email = data["email"]
            user.email_verified = False

            verification_token = secrets.token_urlsafe(32)
            self.db.store_verification_token(user.id, verification_token)

            html = f"""
            <h1>Email Change Notification</h1>
            <p>Your email has been changed to {data['email']}.</p>
            <p>Please verify by clicking
            <a href="https://myapp.com/verify?token={verification_token}">here</a>
            </p>
            """
            self.email_client.send(to=data["email"], subject="Verify New Email", html=html)
            self.email_client.send(
                to=old_email,
                subject="Email Changed",
                html=f"<p>Your email was changed to {data['email']}.</p>"
            )

        if "username" in data:
            user.username = data["username"]
        if "bio" in data:
            user.bio = data["bio"]

        self.db.save(user)
        self.cache.delete(f"user:{user_id}")
        self.cache.delete(f"user_profile:{user_id}")
        self.logger.info(f"Profile updated: {user_id}")

        return user

    def change_password(self, user_id, old_password, new_password):
        user = self.db.get_user(user_id)
        if not user:
            raise ValueError("User not found")

        import bcrypt
        if not bcrypt.checkpw(old_password.encode(), user.password_hash.encode()):
            self.logger.warning(f"Failed password change attempt: {user_id}")
            raise ValueError("Current password is incorrect")

        if len(new_password) < 8:
            raise ValueError("New password too short")

        hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt())
        user.password_hash = hashed.decode()
        self.db.save(user)

        self.email_client.send(
            to=user.email,
            subject="Password Changed",
            html="<p>Your password was recently changed. If this was not you, contact support.</p>"
        )

        self.logger.info(f"Password changed: {user_id}")

    def delete_user(self, user_id, admin_id=None):
        user = self.db.get_user(user_id)
        if not user:
            raise ValueError("User not found")

        self.db.delete_user_orders(user_id)
        self.db.delete_user_comments(user_id)
        self.db.delete_user_sessions(user_id)
        self.db.delete_user(user_id)

        self.cache.delete(f"user:{user_id}")
        self.cache.delete(f"user_profile:{user_id}")
        self.cache.delete(f"user_orders:{user_id}")
        self.cache.delete(f"user_list")

        self.email_client.send(
            to=user.email,
            subject="Account Deleted",
            html="<p>Your account has been deleted.</p>"
        )

        self.logger.info(
            f"User deleted: {user_id} by {'admin ' + str(admin_id) if admin_id else 'self'}"
        )
```''', r'''<think>
This UserManager class has too many responsibilities. Let me identify the distinct concerns:

1. Input validation (password length, email format, uniqueness checks)
2. Password hashing (bcrypt)
3. Database operations (CRUD)
4. Cache invalidation
5. Email template construction and sending
6. SMS notifications
7. Verification token management
8. Audit logging

The class has 5 dependencies injected in __init__ (db, email_client, sms_client, cache, logger). This is a strong smell of a class doing too much.

Each method follows the same pattern:
1. Validate input
2. Perform database operation
3. Invalidate cache
4. Send notification(s)
5. Log the action

These cross-cutting concerns should be extracted into separate classes:

- InputValidator: Validates email format, password strength, uniqueness
- PasswordService: Handles hashing and verification
- NotificationService: Sends emails and SMS (with templates)
- CacheInvalidator: Handles cache invalidation patterns
- UserRepository: Database operations

Additional issues:
- Email templates are inline HTML strings. Should use a template engine.
- bcrypt is imported inside methods instead of at module level.
- Hardcoded URL "https://myapp.com/verify" should be configurable.
- Email validation regex is basic and does not handle edge cases.
- delete_user deletes related records manually instead of using CASCADE or a proper cascade mechanism.
- Cache keys are duplicated between methods (e.g., "user:{user_id}" appears in multiple methods).
- Verification token generation is duplicated between create_user and update_profile.
</think>

## Code Review: Extract Class Refactoring

### CRITICAL - Class Has 8 Responsibilities
`UserManager` handles validation, password hashing, database CRUD, cache invalidation, email templating, SMS messaging, token generation, and audit logging. This violates the Single Responsibility Principle and makes the class nearly impossible to unit test in isolation.

**Suggested class extraction:**

```python
class UserValidator:
    def validate_email(self, email):
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            raise ValidationError("Invalid email")

    def validate_password(self, password):
        if len(password) < 8:
            raise ValidationError("Password too short")

class PasswordService:
    def hash(self, password):
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def verify(self, password, hashed):
        return bcrypt.checkpw(password.encode(), hashed.encode())

class UserNotificationService:
    def __init__(self, email_client, sms_client, template_engine):
        self.email = email_client
        self.sms = sms_client
        self.templates = template_engine

    def send_welcome(self, user, verification_token):
        html = self.templates.render("welcome.html", user=user, token=verification_token)
        self.email.send(to=user.email, subject="Welcome", html=html)

    def send_password_changed(self, user):
        html = self.templates.render("password_changed.html")
        self.email.send(to=user.email, subject="Password Changed", html=html)

class UserCacheManager:
    def __init__(self, cache):
        self.cache = cache

    def invalidate_user(self, user_id):
        keys = [f"user:{user_id}", f"user_profile:{user_id}", f"user_orders:{user_id}"]
        for key in keys:
            self.cache.delete(key)

    def invalidate_lists(self):
        self.cache.delete("user_list")
        self.cache.delete("user_count")
```

### HIGH - Inline HTML Email Templates
Email templates are constructed as f-string HTML inline in business logic methods. This mixes presentation with logic, makes templates difficult to maintain, and is error-prone (no HTML escaping of user data).

**Fix:** Use a template engine:
```python
# templates/welcome.html
# <h1>Welcome {{ username }}!</h1>
# <p><a href="{{ verify_url }}">Verify your email</a></p>
```

### HIGH - Hardcoded Application URL
`"https://myapp.com/verify?token={verification_token}"` is hardcoded in two places. In staging/development environments, this URL is wrong.

**Fix:** Use configuration:
```python
base_url = self.config.get("APP_BASE_URL")
verify_url = f"{base_url}/verify?token={verification_token}"
```

### HIGH - Duplicated Verification Token Logic
Token generation and storage is duplicated between `create_user` and `update_profile`. Both generate a token with `secrets.token_urlsafe(32)` and call `db.store_verification_token`.

**Extract method:**
```python
class VerificationService:
    def create_and_store_token(self, user_id):
        token = secrets.token_urlsafe(32)
        self.db.store_verification_token(user_id, token)
        return token
```

### MEDIUM - Manual Cascade Delete
`delete_user` manually deletes orders, comments, and sessions before the user. This is fragile -- adding a new related table requires updating this method. If any delete fails midway, data is partially deleted with no rollback.

**Fix:** Use database CASCADE constraints or a transaction:
```python
def delete_user(self, user_id):
    with self.db.transaction():
        self.db.delete_user(user_id)  # CASCADE handles related records
```

### MEDIUM - Duplicated Cache Key Patterns
Cache keys like `f"user:{user_id}"` and `f"user_profile:{user_id}"` are hardcoded in multiple methods. A typo in one location creates a stale cache bug.

**Fix:** Centralize cache key generation in `UserCacheManager`.

### MEDIUM - Import Inside Methods
`import bcrypt` appears inside `create_user` and `change_password` instead of at the module level. This hides the dependency and adds import overhead on each call.

### LOW - Duplicated Email Validation
The email regex validation is repeated in `create_user` and `update_profile`. Extract to `UserValidator.validate_email()`.'''),

    ("thinking/code-review", r'''Review this code and suggest extract interface/protocol refactoring:

```python
class ReportGenerator:
    def __init__(self, db_connection):
        self.db = db_connection

    def generate_sales_report(self, start_date, end_date, format="pdf"):
        data = self.db.query(
            "SELECT * FROM orders WHERE created_at BETWEEN %s AND %s",
            (start_date, end_date)
        )

        summary = {
            "total_revenue": sum(row["total"] for row in data),
            "order_count": len(data),
            "avg_order_value": sum(row["total"] for row in data) / len(data) if data else 0,
            "top_products": self._get_top_products(data),
        }

        if format == "pdf":
            from reportlab.pdfgen import canvas
            filename = f"sales_report_{start_date}_{end_date}.pdf"
            c = canvas.Canvas(filename)
            c.drawString(100, 750, f"Sales Report: {start_date} to {end_date}")
            c.drawString(100, 700, f"Total Revenue: ${summary['total_revenue']:.2f}")
            c.drawString(100, 650, f"Orders: {summary['order_count']}")
            c.drawString(100, 600, f"Average: ${summary['avg_order_value']:.2f}")
            y = 550
            for product in summary["top_products"]:
                c.drawString(100, y, f"{product['name']}: {product['count']} sold")
                y -= 30
            c.save()
            return filename

        elif format == "csv":
            import csv
            filename = f"sales_report_{start_date}_{end_date}.csv"
            with open(filename, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["Metric", "Value"])
                writer.writerow(["Total Revenue", summary["total_revenue"]])
                writer.writerow(["Order Count", summary["order_count"]])
                writer.writerow(["Average Order Value", summary["avg_order_value"]])
                writer.writerow([])
                writer.writerow(["Product", "Units Sold"])
                for product in summary["top_products"]:
                    writer.writerow([product["name"], product["count"]])
            return filename

        elif format == "html":
            html = f"""
            <html>
            <body>
            <h1>Sales Report: {start_date} to {end_date}</h1>
            <table>
            <tr><td>Total Revenue</td><td>${summary['total_revenue']:.2f}</td></tr>
            <tr><td>Orders</td><td>{summary['order_count']}</td></tr>
            <tr><td>Average</td><td>${summary['avg_order_value']:.2f}</td></tr>
            </table>
            <h2>Top Products</h2>
            <ul>
            """
            for product in summary["top_products"]:
                html += f"<li>{product['name']}: {product['count']} sold</li>"
            html += "</ul></body></html>"

            filename = f"sales_report_{start_date}_{end_date}.html"
            with open(filename, "w") as f:
                f.write(html)
            return filename

        elif format == "json":
            import json
            filename = f"sales_report_{start_date}_{end_date}.json"
            with open(filename, "w") as f:
                json.dump(summary, f, indent=2)
            return filename

        else:
            raise ValueError(f"Unsupported format: {format}")

    def _get_top_products(self, order_data):
        product_counts = {}
        for order in order_data:
            for item in order.get("items", []):
                pid = item["product_id"]
                product_counts[pid] = product_counts.get(pid, 0) + item["quantity"]

        sorted_products = sorted(product_counts.items(), key=lambda x: x[1], reverse=True)[:10]
        return [
            {"name": self.db.get_product(pid).name, "count": count}
            for pid, count in sorted_products
        ]
```''', r'''<think>
This code has a classic Open/Closed Principle violation. The generate_sales_report method is a large if/elif chain that handles multiple output formats. Adding a new format (e.g., Excel, Markdown) requires modifying this method.

The key insight is that data collection and formatting are separate concerns:
1. Data collection (SQL query, aggregation) is the same regardless of format
2. Formatting/rendering is different for each output type

This should be refactored using the Strategy pattern or Protocol/Interface extraction.

Current issues:
1. Single method handles 4 formats with completely different rendering logic (~60 lines of format-specific code)
2. Each format has inline imports (reportlab, csv, json)
3. Adding a new format requires modifying the existing method
4. Format-specific logic cannot be tested independently
5. File I/O is mixed with formatting
6. No abstraction for a "report formatter" concept

Additional issues:
- _get_top_products does N+1 queries (db.get_product for each top product)
- Files are written to the current directory with no path configuration
- No cleanup of generated files
- HTML is constructed via string concatenation (XSS risk if product names contain HTML)
- summary["avg_order_value"] can divide by zero (though guarded by ternary)
- SQL query uses SELECT * which is wasteful
</think>

## Code Review: Extract Interface/Protocol Refactoring

### CRITICAL - Open/Closed Principle Violation
The `generate_sales_report` method is a 70+ line if/elif chain that handles four output formats. Adding a new format (Excel, Markdown, XML) requires modifying this method, risking bugs in existing formats. Each format's rendering logic is untestable in isolation.

**Extract a ReportFormatter protocol:**
```python
from typing import Protocol, Dict

class ReportFormatter(Protocol):
    def format(self, summary: Dict, start_date: str, end_date: str) -> str:
        ...

class PdfFormatter:
    def format(self, summary, start_date, end_date):
        from reportlab.pdfgen import canvas
        filename = f"sales_report_{start_date}_{end_date}.pdf"
        c = canvas.Canvas(filename)
        # ... PDF-specific rendering
        c.save()
        return filename

class CsvFormatter:
    def format(self, summary, start_date, end_date):
        import csv
        filename = f"sales_report_{start_date}_{end_date}.csv"
        # ... CSV-specific rendering
        return filename

class HtmlFormatter:
    def format(self, summary, start_date, end_date):
        # ... use a template engine
        return filename

class JsonFormatter:
    def format(self, summary, start_date, end_date):
        # ... JSON rendering
        return filename
```

**Refactored ReportGenerator:**
```python
class ReportGenerator:
    FORMATTERS = {
        "pdf": PdfFormatter,
        "csv": CsvFormatter,
        "html": HtmlFormatter,
        "json": JsonFormatter,
    }

    def generate_sales_report(self, start_date, end_date, format="pdf"):
        data = self._fetch_data(start_date, end_date)
        summary = self._compute_summary(data)

        formatter_class = self.FORMATTERS.get(format)
        if not formatter_class:
            raise ValueError(f"Unsupported format: {format}")

        return formatter_class().format(summary, start_date, end_date)
```

### HIGH - Data Collection Mixed with Presentation
The SQL query, aggregation logic, and rendering code are interleaved in one method. The data collection should be completely separate from formatting.

**Extract data methods:**
```python
def _fetch_data(self, start_date, end_date):
    return self.db.query(
        "SELECT id, total, items, created_at FROM orders "
        "WHERE created_at BETWEEN %s AND %s",
        (start_date, end_date)
    )

def _compute_summary(self, data):
    totals = [row["total"] for row in data]
    return {
        "total_revenue": sum(totals),
        "order_count": len(data),
        "avg_order_value": sum(totals) / len(totals) if totals else 0,
        "top_products": self._get_top_products(data),
    }
```

### HIGH - N+1 Query in _get_top_products
`_get_top_products` calls `self.db.get_product(pid)` individually for each of the top 10 products. This is 10 separate database queries that should be a single batch query.

**Fix:**
```python
product_ids = [pid for pid, _ in sorted_products]
products = self.db.get_products_by_ids(product_ids)
product_map = {p.id: p for p in products}
```

### MEDIUM - HTML Built via String Concatenation
The HTML format constructs markup using f-strings and concatenation. Product names are not HTML-escaped, creating an XSS vulnerability if product names contain `<script>` tags or other HTML.

**Fix:** Use a template engine like Jinja2:
```python
from jinja2 import Template
template = Template(open("templates/sales_report.html").read())
html = template.render(summary=summary, start_date=start_date, end_date=end_date)
```

### MEDIUM - Files Written to Current Directory
Generated reports are written to the current working directory with no configurable output path. In production, the CWD may not be writable or appropriate.

**Fix:** Accept an output directory parameter:
```python
def format(self, summary, start_date, end_date, output_dir="/tmp/reports"):
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.join(output_dir, f"sales_report_{start_date}_{end_date}.csv")
```

### LOW - SELECT * in SQL Query
`SELECT *` fetches all columns including potentially large text fields. Only the fields needed for the report should be selected.'''),

    ("thinking/code-review", r'''Review this code and suggest extract module refactoring:

```python
# app.py - 500+ line file

from flask import Flask, request, jsonify, g
import redis
import psycopg2
import jwt
import hashlib
import hmac
import time
import json
import os
import logging
import re
import csv
import io
from functools import wraps
from datetime import datetime, timedelta

app = Flask(__name__)
logger = logging.getLogger(__name__)
redis_client = redis.Redis(host="localhost", port=6379, db=0)

# --- Database ---
def get_db():
    if "db" not in g:
        g.db = psycopg2.connect(os.environ["DATABASE_URL"])
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db:
        db.close()

# --- Auth ---
SECRET_KEY = os.environ.get("SECRET_KEY", "default")

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_token(user_id):
    return jwt.encode({"user_id": user_id, "exp": time.time() + 3600}, SECRET_KEY)

def require_auth(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            g.user_id = payload["user_id"]
        except Exception:
            return jsonify({"error": "Unauthorized"}), 401
        return f(*args, **kwargs)
    return wrapper

# --- Validators ---
def validate_email(email):
    return re.match(r"[^@]+@[^@]+\.[^@]+", email)

def validate_password(password):
    return len(password) >= 8

# --- Cache helpers ---
def cache_get(key):
    data = redis_client.get(key)
    return json.loads(data) if data else None

def cache_set(key, value, ttl=300):
    redis_client.setex(key, ttl, json.dumps(value))

def cache_delete(key):
    redis_client.delete(key)

# --- User routes ---
@app.route("/api/users", methods=["POST"])
def create_user():
    data = request.get_json()
    # ... 30 lines of user creation logic

@app.route("/api/users/<int:user_id>")
@require_auth
def get_user(user_id):
    cached = cache_get(f"user:{user_id}")
    if cached:
        return jsonify(cached)
    # ... 20 lines of user retrieval

@app.route("/api/users/<int:user_id>", methods=["PUT"])
@require_auth
def update_user(user_id):
    # ... 25 lines of user update logic

# --- Product routes ---
@app.route("/api/products")
def list_products():
    # ... 20 lines

@app.route("/api/products/<int:product_id>")
def get_product(product_id):
    # ... 15 lines

@app.route("/api/products", methods=["POST"])
@require_auth
def create_product():
    # ... 25 lines

# --- Order routes ---
@app.route("/api/orders", methods=["POST"])
@require_auth
def create_order():
    # ... 40 lines of order creation

@app.route("/api/orders/<int:order_id>")
@require_auth
def get_order(order_id):
    # ... 20 lines

# --- Report routes ---
@app.route("/api/reports/sales")
@require_auth
def sales_report():
    # ... 30 lines

@app.route("/api/reports/export")
@require_auth
def export_report():
    # ... 25 lines with CSV generation

# ... 200 more lines of routes, helpers, and utilities
```''', r'''<think>
This is a classic "monolith module" antipattern. Everything is in a single file with 500+ lines. Let me identify the natural module boundaries.

Current structure in app.py:
1. Database connection management
2. Authentication (password hashing, JWT, decorator)
3. Input validators
4. Cache helpers
5. User routes (CRUD)
6. Product routes (CRUD)
7. Order routes
8. Report routes
9. Various utilities

Each of these should be its own module. The Flask application should follow a standard project structure.

Issues beyond just organization:
- All imports at the top of one massive file
- Global redis_client and database connection
- SECRET_KEY with a default fallback
- SHA-256 for password hashing (should be bcrypt)
- No blueprints for route organization
- Cache, auth, and database logic tightly coupled with route handlers
- No clear service layer between routes and database
- Testing this file requires importing everything

Recommended structure:
```
app/
    __init__.py          (app factory)
    config.py            (configuration)
    extensions.py        (db, redis, etc.)
    auth/
        __init__.py
        decorators.py
        service.py
    users/
        __init__.py
        routes.py
        service.py
        models.py
    products/
        __init__.py
        routes.py
        service.py
    orders/
        __init__.py
        routes.py
        service.py
    reports/
        __init__.py
        routes.py
    cache/
        __init__.py
        helpers.py
    validators/
        __init__.py
```
</think>

## Code Review: Extract Module Refactoring

### CRITICAL - 500+ Line Monolith File
The entire application -- database, auth, caching, validation, and all route handlers -- lives in a single file. This makes the code impossible to navigate, test in isolation, or work on concurrently with other developers. Changes to authentication logic require re-reading hundreds of lines of unrelated route handlers.

**Recommended module structure:**
```
app/
    __init__.py           # App factory
    config.py             # Configuration classes
    extensions.py         # Redis, DB initialization
    auth/
        __init__.py
        decorators.py     # require_auth
        service.py        # hash_password, create_token
    users/
        __init__.py
        routes.py         # Blueprint with user endpoints
        service.py        # Business logic
    products/
        routes.py
        service.py
    orders/
        routes.py
        service.py
    reports/
        routes.py
    cache/
        helpers.py        # cache_get, cache_set, cache_delete
    validators.py         # validate_email, validate_password
```

### HIGH - No Flask Blueprints
All routes are registered directly on the app object. This prevents modular loading, makes route namespacing manual, and couples all routes to a single file.

**Fix:** Use blueprints per domain:
```python
# app/users/routes.py
from flask import Blueprint

users_bp = Blueprint("users", __name__, url_prefix="/api/users")

@users_bp.route("/", methods=["POST"])
def create_user():
    ...

# app/__init__.py
def create_app():
    app = Flask(__name__)
    from app.users.routes import users_bp
    from app.products.routes import products_bp
    app.register_blueprint(users_bp)
    app.register_blueprint(products_bp)
    return app
```

### HIGH - No Application Factory
The Flask app is created at module level (`app = Flask(__name__)`). This prevents creating different app configurations for testing, development, and production. It also causes import side effects.

**Fix:**
```python
# app/__init__.py
def create_app(config_name="production"):
    app = Flask(__name__)
    app.config.from_object(configs[config_name])
    # Register extensions, blueprints
    return app
```

### HIGH - No Service Layer
Route handlers contain business logic, database queries, caching, and validation all inline. This makes logic untestable without HTTP requests and duplicates logic across endpoints.

**Fix:** Extract service classes:
```python
# app/users/service.py
class UserService:
    def __init__(self, db, cache):
        self.db = db
        self.cache = cache

    def get_user(self, user_id):
        cached = self.cache.get(f"user:{user_id}")
        if cached:
            return cached
        user = self.db.get_user(user_id)
        self.cache.set(f"user:{user_id}", user.to_dict())
        return user.to_dict()

# app/users/routes.py
@users_bp.route("/<int:user_id>")
@require_auth
def get_user(user_id):
    return jsonify(user_service.get_user(user_id))
```

### MEDIUM - Global State (Redis Client, DB)
`redis_client` is a module-level global. This prevents configuration changes at runtime and makes testing require a running Redis instance.

**Fix:** Use Flask extensions pattern:
```python
# app/extensions.py
from flask_redis import FlaskRedis
redis_client = FlaskRedis()

# app/__init__.py
def create_app():
    redis_client.init_app(app)
```

### MEDIUM - Authentication Concerns Mixed with Routes
Password hashing, token creation, and auth decorators are defined alongside route handlers. Extract to `app/auth/`.

### LOW - Default Secret Key Fallback
`SECRET_KEY = os.environ.get("SECRET_KEY", "default")` silently falls back to "default" if the environment variable is not set. This should raise an error in production.'''),

    ("thinking/code-review", r'''Review this code and suggest extract configuration refactoring:

```python
import os
import json
import smtplib
import stripe
import boto3

class PaymentService:
    def __init__(self):
        self.stripe_key = "sk_test_EXAMPLE_KEY_REPLACE_ME"
        self.stripe_webhook_secret = "whsec_EXAMPLE_SECRET_REPLACE_ME"
        stripe.api_key = self.stripe_key

        self.tax_rates = {
            "US-CA": 0.0725,
            "US-NY": 0.08,
            "US-TX": 0.0625,
            "US-WA": 0.065,
            "GB": 0.20,
            "DE": 0.19,
            "FR": 0.20,
            "JP": 0.10,
        }

        self.shipping_rates = {
            "standard": {"domestic": 5.99, "international": 14.99},
            "express": {"domestic": 12.99, "international": 29.99},
            "overnight": {"domestic": 24.99, "international": 49.99}
        }

        self.free_shipping_threshold = 100.00
        self.max_order_amount = 10000.00
        self.min_order_amount = 1.00
        self.currency = "usd"

        self.email_host = "smtp.gmail.com"
        self.email_port = 587
        self.email_user = "orders@mycompany.com"
        self.email_password = "gmail-app-password-123"
        self.email_from = "MyCompany Orders <orders@mycompany.com>"

        self.aws_access_key = "AKIAIOSFODNN7EXAMPLE"
        self.aws_secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
        self.aws_region = "us-east-1"
        self.s3_bucket = "mycompany-receipts"

        self.receipt_template = """
        Dear {customer_name},

        Thank you for your order #{order_id}.

        Items: {items}
        Subtotal: ${subtotal:.2f}
        Tax: ${tax:.2f}
        Shipping: ${shipping:.2f}
        Total: ${total:.2f}

        Your order will be shipped to:
        {shipping_address}

        Thank you for shopping with MyCompany!
        """

    def process_payment(self, order):
        if order.total < self.min_order_amount:
            raise ValueError("Order below minimum")
        if order.total > self.max_order_amount:
            raise ValueError("Order exceeds maximum")

        tax = order.subtotal * self.tax_rates.get(order.tax_region, 0)
        shipping = self._calculate_shipping(order)

        charge = stripe.Charge.create(
            amount=int((order.subtotal + tax + shipping) * 100),
            currency=self.currency,
            source=order.payment_token,
        )

        self._send_receipt(order, tax, shipping, charge)
        self._upload_receipt(order, charge)

        return charge

    def _calculate_shipping(self, order):
        rates = self.shipping_rates.get(order.shipping_method, self.shipping_rates["standard"])
        rate_key = "domestic" if order.country == "US" else "international"
        cost = rates[rate_key]
        if order.subtotal >= self.free_shipping_threshold:
            cost = 0
        return cost

    def _send_receipt(self, order, tax, shipping, charge):
        body = self.receipt_template.format(
            customer_name=order.customer_name,
            order_id=order.id,
            items=order.items_summary,
            subtotal=order.subtotal,
            tax=tax,
            shipping=shipping,
            total=charge.amount / 100,
            shipping_address=order.shipping_address
        )

        server = smtplib.SMTP(self.email_host, self.email_port)
        server.starttls()
        server.login(self.email_user, self.email_password)
        server.sendmail(self.email_from, order.customer_email, body)
        server.quit()

    def _upload_receipt(self, order, charge):
        s3 = boto3.client(
            "s3",
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key,
            region_name=self.aws_region
        )
        s3.put_object(
            Bucket=self.s3_bucket,
            Key=f"receipts/{order.id}.json",
            Body=json.dumps({"order_id": order.id, "charge_id": charge.id})
        )
```''', r'''<think>
This class has severe configuration management issues. Almost everything is hardcoded.

Security issues (CRITICAL):
1. Stripe live API key hardcoded in source code
2. Stripe webhook secret hardcoded
3. Gmail password hardcoded
4. AWS access key and secret key hardcoded
5. All of these will be committed to version control

Configuration issues:
1. Tax rates hardcoded - these change and vary by jurisdiction
2. Shipping rates hardcoded - these change frequently
3. Business rules (free shipping threshold, min/max order) hardcoded
4. Email server configuration hardcoded
5. AWS region and S3 bucket hardcoded
6. Receipt template hardcoded as a class attribute
7. Currency hardcoded to "usd"

Architecture issues:
1. PaymentService does too many things: payment processing, tax calculation, shipping calculation, email sending, and file upload to S3
2. All configuration in __init__ makes the class impossible to configure differently for testing
3. No dependency injection - creates its own SMTP and S3 connections

The configuration should be extracted into:
1. Environment variables for secrets
2. Configuration classes for environment-specific settings
3. Database or config files for business rules (tax rates, shipping rates)
4. Template files for email templates
</think>

## Code Review: Extract Configuration Refactoring

### CRITICAL - Secrets Hardcoded in Source Code
The Stripe API key, webhook secret, Gmail password, and AWS credentials are all hardcoded strings. These will be committed to version control, exposing them to anyone with repository access.

**Fix:** Load all secrets from environment variables:
```python
class PaymentConfig:
    STRIPE_KEY = os.environ["STRIPE_API_KEY"]
    STRIPE_WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]
    EMAIL_PASSWORD = os.environ["EMAIL_PASSWORD"]
    AWS_ACCESS_KEY = os.environ["AWS_ACCESS_KEY_ID"]
    AWS_SECRET_KEY = os.environ["AWS_SECRET_ACCESS_KEY"]
```

### HIGH - Business Rules Hardcoded
Tax rates, shipping rates, free shipping threshold, min/max order amounts, and currency are all hardcoded constants. These change frequently (tax rates change annually, shipping rates change with carrier contracts, thresholds change with promotions).

**Fix:** Extract to external configuration:
```python
# config/business_rules.yaml
tax_rates:
    US-CA: 0.0725
    US-NY: 0.08
    ...

shipping:
    free_threshold: 100.00
    rates:
        standard:
            domestic: 5.99
            international: 14.99
```

```python
class BusinessConfig:
    def __init__(self, config_path="config/business_rules.yaml"):
        with open(config_path) as f:
            self.config = yaml.safe_load(f)

    @property
    def tax_rates(self):
        return self.config["tax_rates"]
```

### HIGH - Email Template Hardcoded as String
The receipt template is an inline string in the constructor. Changes require code changes and redeployment. No support for HTML formatting, internationalization, or different template variations.

**Fix:** Use external template files:
```python
# templates/receipt.txt
from jinja2 import Environment, FileSystemLoader

env = Environment(loader=FileSystemLoader("templates"))
template = env.get_template("receipt.txt")
body = template.render(order=order, tax=tax, shipping=shipping)
```

### HIGH - Class Has 5 Responsibilities
`PaymentService` handles payment processing, tax calculation, shipping calculation, email sending, and S3 file upload. Each of these should be a separate service.

**Fix:** Extract into focused services:
```python
class PaymentService:
    def __init__(self, config, tax_calc, shipping_calc, notifier, receipt_store):
        self.config = config
        self.tax = tax_calc
        self.shipping = shipping_calc
        self.notifier = notifier
        self.receipts = receipt_store
```

### MEDIUM - No Environment-Specific Configuration
There is no way to use different settings for development, staging, and production. The live Stripe key is used everywhere, meaning development testing charges real credit cards.

**Fix:** Use environment-based configuration:
```python
class Config:
    pass

class DevelopmentConfig(Config):
    STRIPE_KEY = os.environ.get("STRIPE_KEY", "sk_test_...")
    S3_BUCKET = "mycompany-receipts-dev"

class ProductionConfig(Config):
    STRIPE_KEY = os.environ["STRIPE_KEY"]
    S3_BUCKET = "mycompany-receipts"

configs = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
}
```

### MEDIUM - No Dependency Injection
The class creates its own SMTP connection and S3 client internally. This makes testing impossible without actually sending emails and uploading to S3.

**Fix:** Accept dependencies as constructor parameters:
```python
class PaymentService:
    def __init__(self, stripe_client, email_sender, receipt_store):
        self.stripe = stripe_client
        self.email = email_sender
        self.receipts = receipt_store
```

### LOW - Tax Rates Should Be in a Database
Tax rates change periodically and vary by sub-jurisdiction. Hardcoding them means a tax rate change requires a code change, review, and deployment. Store in a database with effective dates for automatic updates.'''),
]
