"""
Ambiguous request handling pairs - vague code improvement requests
"""

pairs = [
    {
        "instruction": r'''Make this better:

def process(data):
    result = []
    for i in range(len(data)):
        if data[i]["type"] == "A":
            if data[i]["value"] > 10:
                if data[i]["active"] == True:
                    result.append({"name": data[i]["name"], "value": data[i]["value"] * 2, "type": "A"})
        elif data[i]["type"] == "B":
            if data[i]["value"] > 20:
                if data[i]["active"] == True:
                    result.append({"name": data[i]["name"], "value": data[i]["value"] * 3, "type": "B"})
    return result''',
        "output": r'''<think>
"Make this better" -- better how? More readable? Faster? More extensible? Type-safe? The code has several clear issues: nested ifs, indexing with range(len()), magic numbers, no type hints, repetition. I'll assume they want readability and maintainability since those are the most obvious problems, but I should ask about extensibility since the type/multiplier pattern might grow.
</think>

A couple things I'd clarify:

1. **Are there more types coming?** If you'll add types C, D, etc., this needs a data-driven approach rather than if/elif chains.
2. **Does performance matter?** How large is `data` -- hundreds or millions of items?

Here's an improved version assuming readability and maintainability are the priority:

```python
from typing import TypedDict

class Item(TypedDict):
    name: str
    type: str
    value: int
    active: bool

# Configuration-driven -- adding new types is just adding a row
TYPE_CONFIG = {
    "A": {"min_value": 10, "multiplier": 2},
    "B": {"min_value": 20, "multiplier": 3},
}

def process(data: list[Item]) -> list[dict]:
    results = []
    for item in data:
        config = TYPE_CONFIG.get(item["type"])
        if config is None:
            continue
        if not item["active"]:
            continue
        if item["value"] <= config["min_value"]:
            continue

        results.append({
            "name": item["name"],
            "value": item["value"] * config["multiplier"],
            "type": item["type"],
        })
    return results
```

What changed and why:
- **Iterate directly** over items instead of `range(len(data))` -- more Pythonic and avoids repeated indexing
- **Early continues** instead of nested ifs -- reduces indentation and makes each filter condition obvious
- **Config dict** instead of if/elif -- adding type "C" is one line, not another elif block
- **Type hints** -- makes it clear what goes in and comes out
- **`== True` removed** -- `if item["active"]` is sufficient and idiomatic

If you want a more functional style, this also works as a list comprehension, though it trades some readability:

```python
def process(data: list[Item]) -> list[dict]:
    return [
        {"name": item["name"], "value": item["value"] * cfg["multiplier"], "type": item["type"]}
        for item in data
        if (cfg := TYPE_CONFIG.get(item["type"]))
        and item["active"]
        and item["value"] > cfg["min_value"]
    ]
```

Let me know if extensibility or performance is the bigger concern and I'll adjust.'''
    },
    {
        "instruction": r'''Clean up this code please.

import os, sys, json, re, time, logging
from datetime import datetime, timedelta

def handle_request(req):
    logging.info("got request")
    try:
        data = json.loads(req.body)
        user = get_user(data["user_id"])
        if user == None:
            return {"status": "error", "message": "no user"}
        if user["role"] == "admin":
            items = get_all_items()
        else:
            items = get_items_for_user(user["id"])
        filtered = []
        for item in items:
            if item["deleted"] == False:
                if item["expires"] == None or item["expires"] > datetime.now():
                    filtered.append(item)
        result = {"status": "ok", "items": filtered, "count": len(filtered)}
        logging.info("returning " + str(len(filtered)) + " items")
        return result
    except Exception as e:
        logging.error("error: " + str(e))
        return {"status": "error", "message": "something went wrong"}''',
        "output": r'''<think>
"Clean up this code" -- they probably want readability improvements, but I should also flag the structural issues: bare except swallowing all errors, unused imports, comparing with == None, no type hints, inconsistent error handling. I'll focus on practical cleanup but should ask if they want to restructure the error handling pattern more broadly.
</think>

Quick question: Is this part of a larger codebase with many similar `handle_request` functions? If so, the error handling and response format should probably be standardized with middleware rather than repeated in each handler.

Here's the cleaned-up version:

```python
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def handle_request(req):
    """Fetch active, non-expired items visible to the requesting user."""
    try:
        data = json.loads(req.body)
    except (json.JSONDecodeError, AttributeError) as exc:
        logger.warning("Invalid request body: %s", exc)
        return {"status": "error", "message": "Invalid request body"}

    user = get_user(data.get("user_id"))
    if user is None:
        return {"status": "error", "message": "User not found"}

    items = get_all_items() if user["role"] == "admin" else get_items_for_user(user["id"])

    filtered = [
        item for item in items
        if not item["deleted"]
        and (item["expires"] is None or item["expires"] > datetime.now())
    ]

    logger.info("Returning %d items for user %s", len(filtered), user["id"])
    return {"status": "ok", "items": filtered, "count": len(filtered)}
```

Changes made:
- **Removed unused imports** (`os`, `sys`, `re`, `time`, `timedelta`) -- dead imports add confusion
- **`== None` -> `is None`** and **`== False` -> `not`** -- Python identity/boolean idioms
- **Specific exception handling** -- catch `JSONDecodeError` instead of bare `except Exception` which hides real bugs
- **List comprehension** for filtering -- replaces the nested-if loop
- **`logger.info("format %s", val)`** instead of string concatenation -- avoids building the string if the log level is disabled
- **Named logger** via `__name__` instead of root logger -- better log management
- **Removed the catch-all try/except** -- let unexpected errors propagate so they surface in your error tracker rather than returning a generic message that hides bugs

If you have many endpoints following this pattern, consider a decorator or middleware for the common error handling and response wrapping.'''
    },
    {
        "instruction": r'''This code is a mess, fix it. It's our user management module.''',
        "output": r'''<think>
"This is a mess" -- but they haven't shared any code. They mentioned it's a user management module, but I have no idea what language, framework, what it does, or what makes it messy. Is it spaghetti logic? Poor naming? Mixed concerns? Too many responsibilities? I need to see the code and understand the scope before I can help.
</think>

I'd be happy to help clean it up, but I'll need a few things first:

1. **Can you share the code?** (or at least the file -- I can't see it from here)
2. **What makes it messy?** Some common issues:
   - Hard to add new features without breaking things?
   - Functions that are hundreds of lines long?
   - Business logic mixed with database calls and HTTP handling?
   - No clear separation between user CRUD, auth, and permissions?
3. **What's the tech stack?** (Language, framework, ORM)

While I wait for the code, here's what a well-structured user management module typically looks like, so you can compare against yours:

```python
# Good structure for a user management module:
#
# users/
#   __init__.py
#   models.py      -- User data model / ORM definition
#   schemas.py     -- Input/output validation (Pydantic, etc.)
#   repository.py  -- Database queries only (create, read, update, delete)
#   service.py     -- Business logic (registration rules, role changes)
#   routes.py      -- HTTP endpoints (thin -- just parse request, call service, return response)
#   exceptions.py  -- Domain-specific errors (UserNotFound, EmailTaken, etc.)

# Example: service.py (business logic, no HTTP or DB details)
class UserService:
    def __init__(self, user_repo: UserRepository):
        self.repo = user_repo

    async def register(self, email: str, password: str) -> User:
        existing = await self.repo.find_by_email(email)
        if existing:
            raise EmailAlreadyTaken(email)
        hashed = hash_password(password)
        return await self.repo.create(email=email, hashed_password=hashed)

    async def change_role(self, user_id: int, new_role: str, changed_by: User) -> User:
        if changed_by.role != "admin":
            raise InsufficientPermissions("Only admins can change roles")
        user = await self.repo.get_by_id(user_id)
        if user is None:
            raise UserNotFound(user_id)
        user.role = new_role
        return await self.repo.update(user)
```

Common "mess" patterns I see in user modules:
- **God function**: one 500-line function handling registration, login, profile updates, and password resets
- **Mixed layers**: SQL queries inside route handlers
- **No validation**: trusting user input directly

Share the code and I'll give you a specific refactoring plan.'''
    },
    {
        "instruction": r'''Refactor this.

class OrderProcessor:
    def process(self, order):
        # validate
        if not order.get("items"):
            raise ValueError("no items")
        if not order.get("customer_id"):
            raise ValueError("no customer")
        total = 0
        for item in order["items"]:
            if item["quantity"] < 1:
                raise ValueError("bad quantity")
            price = self.get_price(item["product_id"])
            total += price * item["quantity"]
        # apply discount
        if order.get("coupon"):
            coupon = self.get_coupon(order["coupon"])
            if coupon and coupon["active"]:
                if coupon["type"] == "percent":
                    total = total * (1 - coupon["value"] / 100)
                elif coupon["type"] == "fixed":
                    total = total - coupon["value"]
                if total < 0:
                    total = 0
        # apply tax
        tax_rate = self.get_tax_rate(order.get("state", "CA"))
        total_with_tax = total * (1 + tax_rate)
        # save
        order_id = self.save_order(order["customer_id"], order["items"], total_with_tax)
        # send email
        self.send_confirmation(order["customer_id"], order_id, total_with_tax)
        return {"order_id": order_id, "total": total_with_tax}''',
        "output": r'''<think>
"Refactor this" -- but refactor toward what goal? Better testability? Separation of concerns? Extensibility for new discount types? The code works but has multiple responsibilities crammed into one method. I should ask about their goals but can already see the SRP violations and suggest a clean split.
</think>

Before refactoring, it helps to know the goal:

1. **Is testability the pain point?** (Hard to unit test because validation, pricing, discounts, tax, persistence, and email are all tangled together?)
2. **Are new discount types coming?** If so, the coupon handling needs to be extensible.
3. **Should the email be synchronous?** Sending email in the same call path means a slow email service blocks the order response.

Here's a refactored version that separates concerns, making each piece independently testable:

```python
from dataclasses import dataclass
from typing import Optional

@dataclass
class OrderResult:
    order_id: str
    subtotal: float
    total_with_tax: float

class OrderValidator:
    def validate(self, order: dict) -> None:
        if not order.get("items"):
            raise ValueError("Order must contain at least one item")
        if not order.get("customer_id"):
            raise ValueError("Order must have a customer_id")
        for item in order["items"]:
            if item.get("quantity", 0) < 1:
                raise ValueError(f"Invalid quantity for product {item.get('product_id')}")

class PriceCalculator:
    def __init__(self, price_service):
        self.price_service = price_service

    def calculate_subtotal(self, items: list[dict]) -> float:
        total = 0.0
        for item in items:
            price = self.price_service.get_price(item["product_id"])
            total += price * item["quantity"]
        return total

class DiscountApplier:
    def __init__(self, coupon_service):
        self.coupon_service = coupon_service

    def apply(self, subtotal: float, coupon_code: Optional[str]) -> float:
        if not coupon_code:
            return subtotal
        coupon = self.coupon_service.get_coupon(coupon_code)
        if not coupon or not coupon["active"]:
            return subtotal
        if coupon["type"] == "percent":
            subtotal *= (1 - coupon["value"] / 100)
        elif coupon["type"] == "fixed":
            subtotal -= coupon["value"]
        return max(subtotal, 0.0)

class OrderProcessor:
    def __init__(self, validator, calculator, discounter, tax_service, order_repo, notifier):
        self.validator = validator
        self.calculator = calculator
        self.discounter = discounter
        self.tax_service = tax_service
        self.order_repo = order_repo
        self.notifier = notifier

    def process(self, order: dict) -> OrderResult:
        self.validator.validate(order)

        subtotal = self.calculator.calculate_subtotal(order["items"])
        subtotal = self.discounter.apply(subtotal, order.get("coupon"))

        tax_rate = self.tax_service.get_tax_rate(order.get("state", "CA"))
        total = subtotal * (1 + tax_rate)

        order_id = self.order_repo.save(order["customer_id"], order["items"], total)
        self.notifier.send_confirmation(order["customer_id"], order_id, total)

        return OrderResult(order_id=order_id, subtotal=subtotal, total_with_tax=total)
```

Each piece is now testable in isolation -- you can test discount logic without touching the database, test validation without sending emails, etc. Let me know if you'd prefer a simpler refactor that keeps it as one class.'''
    },
    {
        "instruction": r'''Improve the architecture of our backend. It's a Python Flask app.''',
        "output": r'''<think>
"Improve the architecture" of a Flask app -- this is extremely broad. Are they dealing with a monolithic app.py with all routes? Poor separation of concerns? Need to add async? Scale to microservices? I don't know the size of the codebase, number of developers, traffic patterns, or what problems they're actually hitting. I need to understand the pain points before recommending structural changes.
</think>

Architecture changes are high-cost, so I want to make sure I'm solving the right problems:

1. **What's the current structure?** One big `app.py` with all routes, or already split into blueprints/modules?
2. **What's painful right now?** Hard to find code? Tests are difficult? Deployments are scary? Features conflict with each other?
3. **How big is the team?** Solo dev vs. 10 people stepping on each other?

Here's a proven Flask architecture progression. Tell me where you are now, and I'll help you get to the next level:

```text
Level 1: Single file (fine for prototypes)
  app.py  <-- everything here

Level 2: Blueprints (good for small teams, 5-20 routes)
  app/
    __init__.py      <-- create_app factory
    config.py        <-- environment-based config
    models.py        <-- SQLAlchemy models
    routes/
      auth.py        <-- auth blueprint
      users.py       <-- users blueprint
      orders.py      <-- orders blueprint

Level 3: Layered (good for medium apps, 20-100 routes)
  app/
    __init__.py
    config.py
    models/          <-- one file per model
    schemas/         <-- request/response validation
    services/        <-- business logic (no Flask imports here)
    repositories/    <-- database queries only
    routes/          <-- thin HTTP handlers
    middleware/      <-- auth, logging, error handling
    tasks/           <-- background jobs (Celery)
```

```python
# Example: Level 3 create_app factory
# app/__init__.py
from flask import Flask
from app.config import Config
from app.extensions import db, migrate, cors

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)
    cors.init_app(app)

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.users import users_bp
    from app.routes.orders import orders_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(users_bp, url_prefix="/api/users")
    app.register_blueprint(orders_bp, url_prefix="/api/orders")

    # Register error handlers
    from app.middleware.errors import register_error_handlers
    register_error_handlers(app)

    return app
```

The key principle: **routes should be thin**. A route handler parses the request, calls a service, and returns a response. Business logic lives in services, database access lives in repositories. This makes everything testable and keeps concerns separated.

Share your current structure and pain points and I'll give you a specific migration plan.'''
    },
]
