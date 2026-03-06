"""Phase 1E: Foundation Thinking — Code Review & Refactoring (Part 1/4)
Code smells, refactoring patterns, complexity reduction."""

PAIRS = [
    (
        "thinking/review-god-class-refactor",
        "Review this 500-line class that handles everything for user management:\n\n```python\nclass UserManager:\n    def __init__(self, db, email_service, cache, logger):\n        self.db = db\n        self.email = email_service\n        self.cache = cache\n        self.logger = logger\n    \n    def create_user(self, data): ...        # 50 lines\n    def update_user(self, user_id, data): ... # 40 lines\n    def delete_user(self, user_id): ...       # 30 lines\n    def authenticate(self, username, pwd): ... # 60 lines\n    def reset_password(self, email): ...      # 45 lines\n    def verify_email(self, token): ...        # 35 lines\n    def send_welcome_email(self, user): ...   # 25 lines\n    def send_password_reset(self, user): ...  # 25 lines\n    def get_user_permissions(self, user_id): ... # 40 lines\n    def check_permission(self, user, action): ... # 30 lines\n    def generate_report(self, filters): ...   # 60 lines\n    def export_users_csv(self, filters): ...  # 40 lines\n    def import_users_csv(self, file): ...     # 50 lines\n```\n\nIdentify the problems and propose a refactoring plan.",
        r'''<think>
This is a God Class — it has too many responsibilities. Let me identify the distinct responsibility groups:

1. CRUD operations: create, update, delete
2. Authentication: authenticate, reset_password, verify_email
3. Email notifications: send_welcome, send_password_reset
4. Authorization: get_permissions, check_permission
5. Reporting: generate_report, export_csv, import_csv

That's 5 separate responsibilities in one class. This violates Single Responsibility Principle.

Problems:
- Hard to test (need to set up email, cache, permissions to test a simple user creation)
- Hard to modify (changing email logic risks breaking CRUD)
- Hard to understand (500 lines, must read all to understand any part)
- Dependencies are bloated (every user of UserManager gets everything)
</think>

## Problems Identified

1. **God Class** — 5 distinct responsibilities in one class
2. **SRP Violation** — CRUD, auth, email, permissions, reporting all coupled
3. **Testing burden** — need all dependencies to test anything
4. **Shotgun surgery** — email changes require touching the class that also handles CRUD

## Refactoring Plan: Extract Classes by Responsibility

```python
# 1. CRUD operations
class UserRepository:
    def __init__(self, db):
        self.db = db

    def create(self, data): ...
    def get_by_id(self, user_id): ...
    def update(self, user_id, data): ...
    def delete(self, user_id): ...

# 2. Authentication
class AuthService:
    def __init__(self, user_repo, password_hasher):
        self.user_repo = user_repo
        self.hasher = password_hasher

    def authenticate(self, username, password): ...
    def reset_password(self, email): ...
    def verify_email(self, token): ...

# 3. Email notifications
class UserEmailService:
    def __init__(self, email_client, template_engine):
        self.email = email_client
        self.templates = template_engine

    def send_welcome(self, user): ...
    def send_password_reset(self, user, token): ...

# 4. Authorization
class PermissionService:
    def __init__(self, user_repo, role_repo):
        self.user_repo = user_repo
        self.role_repo = role_repo

    def get_permissions(self, user_id): ...
    def check_permission(self, user, action): ...

# 5. Import/Export
class UserDataService:
    def __init__(self, user_repo):
        self.user_repo = user_repo

    def generate_report(self, filters): ...
    def export_csv(self, filters): ...
    def import_csv(self, file): ...
```

**Each class:** single responsibility, minimal dependencies, independently testable. The registration flow composes them:

```python
def register_user(data):
    user = user_repo.create(data)
    email_service.send_welcome(user)
    return user
```'''
    ),
    (
        "thinking/review-primitive-obsession",
        "Review this code that passes user data as individual parameters through many function calls:\n\n```python\ndef process_order(user_id, user_name, user_email, user_address,\n                   user_phone, user_tier, item_id, item_name,\n                   item_price, quantity, discount_code, shipping_method):\n    validate_user(user_id, user_name, user_email, user_tier)\n    validate_item(item_id, item_name, item_price, quantity)\n    total = calculate_total(item_price, quantity, discount_code, user_tier)\n    create_shipment(user_name, user_address, user_phone, \n                    item_name, quantity, shipping_method)\n    send_receipt(user_email, user_name, item_name, total)\n```",
        r'''<think>
Primitive obsession — using raw primitives (strings, ints) instead of domain objects. Problems:
- 12 parameters — impossible to remember the order
- Easy to swap parameters of the same type (user_name and item_name are both strings)
- No validation encapsulated — every function validates separately
- Adding a field requires changing every function signature
</think>

**Primitive obsession — 12 loose parameters instead of domain objects.** Easy to swap `user_name` and `item_name` (both strings), impossible to remember parameter order.

## Fix: Extract Domain Objects

```python
from dataclasses import dataclass
from decimal import Decimal

@dataclass
class Customer:
    id: int
    name: str
    email: str
    address: str
    phone: str
    tier: str

    def validate(self):
        if not self.email or '@' not in self.email:
            raise ValueError('Invalid email')

@dataclass
class OrderItem:
    id: int
    name: str
    price: Decimal
    quantity: int

    def validate(self):
        if self.quantity <= 0:
            raise ValueError('Quantity must be positive')
        if self.price < 0:
            raise ValueError('Price cannot be negative')

    @property
    def subtotal(self):
        return self.price * self.quantity

@dataclass
class OrderRequest:
    customer: Customer
    item: OrderItem
    discount_code: str | None = None
    shipping_method: str = 'standard'

def process_order(order: OrderRequest):
    order.customer.validate()
    order.item.validate()
    total = calculate_total(order)
    create_shipment(order)
    send_receipt(order, total)
```

**Benefits:**
- 1 parameter instead of 12
- Can't accidentally swap customer name and item name
- Validation is encapsulated in the objects
- Adding a field only changes the dataclass, not every function signature'''
    ),
    (
        "thinking/review-deep-nesting-refactor",
        "This function has 6 levels of nesting, making it hard to read and modify:\n\n```python\ndef process_transactions(transactions):\n    results = []\n    for tx in transactions:\n        if tx.is_valid:\n            if tx.amount > 0:\n                if tx.currency in SUPPORTED_CURRENCIES:\n                    if tx.user.is_active:\n                        if not tx.is_duplicate:\n                            if tx.amount < tx.user.daily_limit:\n                                result = execute_transaction(tx)\n                                results.append(result)\n                            else:\n                                log.warning(f'Over limit: {tx.id}')\n                        else:\n                            log.warning(f'Duplicate: {tx.id}')\n                    else:\n                        log.warning(f'Inactive user: {tx.user.id}')\n                else:\n                    log.warning(f'Unsupported currency: {tx.currency}')\n            else:\n                log.warning(f'Non-positive amount: {tx.id}')\n        else:\n            log.warning(f'Invalid: {tx.id}')\n    return results\n```",
        r'''<think>
Arrow anti-pattern (deeply nested code that forms an arrow shape). Fix with guard clauses — invert conditions and return/continue early.
</think>

**Arrow anti-pattern — 6 levels of nesting.** Fix with guard clauses (early `continue`).

## Refactored: Guard Clauses

```python
def process_transactions(transactions):
    results = []
    for tx in transactions:
        error = _validate_transaction(tx)
        if error:
            log.warning(f'{error}: {tx.id}')
            continue

        result = execute_transaction(tx)
        results.append(result)
    return results

def _validate_transaction(tx):
    if not tx.is_valid:
        return 'Invalid transaction'
    if tx.amount <= 0:
        return 'Non-positive amount'
    if tx.currency not in SUPPORTED_CURRENCIES:
        return f'Unsupported currency: {tx.currency}'
    if not tx.user.is_active:
        return f'Inactive user: {tx.user.id}'
    if tx.is_duplicate:
        return 'Duplicate transaction'
    if tx.amount >= tx.user.daily_limit:
        return 'Over daily limit'
    return None  # All checks passed
```

**From 6 levels of nesting to 1.** Each validation is a flat guard clause. The happy path is at the bottom. Adding a new check is one `if` statement — no restructuring needed.'''
    ),
    (
        "thinking/review-feature-envy-code-smell",
        "This code reaches into another object's internals extensively:\n\n```python\ndef calculate_shipping(order):\n    # Reaches deep into order's customer and address\n    if order.customer.address.country == 'US':\n        if order.customer.address.state in ('AK', 'HI'):\n            base_rate = 15.0\n        else:\n            base_rate = 5.0\n    else:\n        base_rate = 25.0\n    \n    # Reaches into order items\n    total_weight = sum(item.product.weight * item.quantity \n                       for item in order.items)\n    \n    # More reaching into customer\n    if order.customer.membership.tier == 'premium':\n        discount = 0.5\n    elif order.customer.membership.tier == 'gold':\n        discount = 0.25\n    else:\n        discount = 0.0\n    \n    return base_rate + (total_weight * 0.5) * (1 - discount)\n```",
        r'''<think>
Feature envy — this function uses more data from other objects (Order, Customer, Address, Membership) than from its own context. It violates the Law of Demeter (don't talk to strangers).

Fix: move logic to the objects that own the data.
</think>

**Feature envy — the function knows too much about other objects' internals.** It reaches through `order.customer.address.state` and `order.customer.membership.tier` (Law of Demeter violations).

## Fix: Move Logic to the Objects That Own the Data

```python
# Address knows how to calculate its base shipping rate
class Address:
    def get_shipping_rate(self):
        if self.country == 'US':
            return 15.0 if self.state in ('AK', 'HI') else 5.0
        return 25.0

# Membership knows its shipping discount
class Membership:
    DISCOUNTS = {'premium': 0.5, 'gold': 0.25}

    @property
    def shipping_discount(self):
        return self.DISCOUNTS.get(self.tier, 0.0)

# Order knows its total weight
class Order:
    @property
    def total_weight(self):
        return sum(item.product.weight * item.quantity for item in self.items)

# Now the shipping calculation is simple and doesn't reach into internals
def calculate_shipping(order):
    base_rate = order.customer.address.get_shipping_rate()
    weight_charge = order.total_weight * 0.5
    discount = order.customer.membership.shipping_discount
    return base_rate + weight_charge * (1 - discount)
```

**The function now asks objects for answers instead of reaching into their internals.** Each object encapsulates its own logic.'''
    ),
    (
        "thinking/review-long-parameter-list",
        "This function has 15 parameters with several boolean flags:\n\n```python\ndef send_notification(user_id, title, body, channel, priority,\n                      send_email, send_sms, send_push, send_slack,\n                      schedule_time, retry_count, include_unsubscribe,\n                      track_opens, track_clicks, template_id):\n    ...\n\n# Callers:\nsend_notification(123, 'Welcome', 'Hello!', 'marketing', 'low',\n                  True, False, True, False, None, 3, True, True, False, 'tpl_welcome')\n```\n\nRefactor this API.",
        r'''<think>
15 parameters, many booleans — impossible to read at the call site. `True, False, True, False` — which is which?

Fixes:
1. Builder pattern or config object
2. Keyword-only arguments at minimum
3. Group related parameters into objects
</think>

**15 parameters with opaque boolean flags.** `True, False, True, False` is unreadable at the call site.

## Fix: Configuration Object + Builder

```python
from dataclasses import dataclass, field

@dataclass
class NotificationChannels:
    email: bool = False
    sms: bool = False
    push: bool = False
    slack: bool = False

@dataclass
class TrackingOptions:
    track_opens: bool = True
    track_clicks: bool = False
    include_unsubscribe: bool = True

@dataclass
class NotificationRequest:
    user_id: int
    title: str
    body: str
    channel: str = 'transactional'
    priority: str = 'normal'
    channels: NotificationChannels = field(default_factory=NotificationChannels)
    tracking: TrackingOptions = field(default_factory=TrackingOptions)
    schedule_time: datetime | None = None
    retry_count: int = 3
    template_id: str | None = None

def send_notification(request: NotificationRequest):
    ...

# Clear, readable call site
send_notification(NotificationRequest(
    user_id=123,
    title='Welcome',
    body='Hello!',
    channel='marketing',
    priority='low',
    channels=NotificationChannels(email=True, push=True),
    tracking=TrackingOptions(track_opens=True),
    template_id='tpl_welcome',
))
```

**Every parameter is named.** No more guessing which `True` means what.'''
    ),
    (
        "thinking/review-magic-numbers",
        "This code is full of unexplained numbers:\n\n```python\ndef calculate_price(base_price, quantity, user_type):\n    if quantity > 100:\n        price = base_price * 0.85\n    elif quantity > 50:\n        price = base_price * 0.9\n    elif quantity > 10:\n        price = base_price * 0.95\n    else:\n        price = base_price\n    \n    if user_type == 1:\n        price *= 0.8\n    elif user_type == 2:\n        price *= 0.9\n    \n    if price < 5.0:\n        price = 5.0\n    \n    price += 3.99\n    \n    if price > 9999.99:\n        return None\n    \n    return round(price, 2)\n```",
        r'''<think>
Magic numbers: 0.85, 0.9, 0.95, 1, 2, 5.0, 3.99, 9999.99, 100, 50, 10 — none have explanations. What's user_type 1 vs 2? What's 3.99?
</think>

**Magic numbers everywhere.** What's user_type 1? What's 3.99? What's 9999.99?

## Fix: Named Constants + Enums

```python
from enum import Enum
from decimal import Decimal

class UserTier(Enum):
    PREMIUM = 'premium'
    GOLD = 'gold'
    STANDARD = 'standard'

# Named constants explain the business rules
VOLUME_DISCOUNTS = [
    (100, Decimal('0.15')),  # 15% off for 100+
    (50,  Decimal('0.10')),  # 10% off for 50+
    (10,  Decimal('0.05')),  # 5% off for 10+
]

TIER_DISCOUNTS = {
    UserTier.PREMIUM: Decimal('0.20'),   # 20% off
    UserTier.GOLD:    Decimal('0.10'),   # 10% off
    UserTier.STANDARD: Decimal('0'),
}

MINIMUM_PRICE = Decimal('5.00')
HANDLING_FEE = Decimal('3.99')
MAXIMUM_PRICE = Decimal('9999.99')

def calculate_price(base_price: Decimal, quantity: int, tier: UserTier) -> Decimal | None:
    price = base_price

    # Apply volume discount
    for min_qty, discount in VOLUME_DISCOUNTS:
        if quantity > min_qty:
            price *= (1 - discount)
            break

    # Apply tier discount
    tier_discount = TIER_DISCOUNTS.get(tier, Decimal('0'))
    price *= (1 - tier_discount)

    # Enforce minimum price
    price = max(price, MINIMUM_PRICE)

    # Add handling fee
    price += HANDLING_FEE

    if price > MAXIMUM_PRICE:
        return None

    return price.quantize(Decimal('0.01'))
```

**Now a business person can read the code and verify the rules.** Every number has a name that explains its purpose.'''
    ),
    (
        "thinking/review-dead-code-detection",
        "During code review, you notice these patterns. Which are dead code and safe to remove?\n\n```python\n# 1. Commented-out code\n# def old_calculate_tax(amount):\n#     return amount * 0.08\n\n# 2. Unreachable code\ndef process(data):\n    return transform(data)\n    validate(data)  # After return!\n\n# 3. Unused import\nimport os\nimport sys  # Never used in this file\nimport json\n\n# 4. Feature flag that's always True\nENABLE_NEW_CHECKOUT = True  # Set to True 2 years ago\n\ndef checkout():\n    if ENABLE_NEW_CHECKOUT:\n        return new_checkout()\n    else:\n        return old_checkout()  # Never runs\n\n# 5. Defensive code for impossible conditions\ndef get_user(user_id: int) -> User:\n    user = db.get(user_id)\n    if user is None:\n        return None\n    if user is None:  # Double check??\n        raise ValueError('User is None')\n    return user\n\n# 6. Unused function\ndef legacy_export_v1(data):\n    \"\"\"Replaced by export_v2 in PR #1234 (2024-06)\"\"\"\n    ...\n```",
        r'''<think>
Let me evaluate each:

1. Commented-out code — DEAD. Remove it. It's in git history if needed.
2. Unreachable code after return — DEAD. `validate(data)` never executes.
3. Unused import `sys` — DEAD. Remove it. `import os` and `import json` — need to check if they're used.
4. Feature flag always True for 2 years — the else branch is DEAD. Remove the flag and the `old_checkout()` function.
5. Second `if user is None` — DEAD. Can never be reached because the first check already returns.
6. Unused function with replacement — DEAD. The comment tells us it's replaced. Verify no callers, then remove.
</think>

## Analysis

| # | Pattern | Verdict | Action |
|---|---------|---------|--------|
| 1 | Commented-out code | Dead | Remove — it's in git history |
| 2 | Code after `return` | Dead | Remove — unreachable |
| 3 | `import sys` unused | Dead | Remove — verify with grep first |
| 4 | Feature flag always True | Dead branch | Remove flag, remove `old_checkout()` |
| 5 | Duplicate None check | Dead | Remove second check |
| 6 | Legacy function replaced | Likely dead | Grep for callers, then remove |

## Cleaned Code

```python
import os
import json

def process(data):
    return transform(data)

def checkout():
    return new_checkout()

def get_user(user_id: int) -> User:
    user = db.get(user_id)
    if user is None:
        return None
    return user
```

**Detection tools:**
- `vulture` — finds unused Python code
- `pylint` — flags unused imports and variables
- IDE "find usages" — verify no callers before deleting functions
- `git log --all -- path/to/function` — check if it's referenced elsewhere

**Rule:** Don't comment out code — delete it. Don't keep feature flags longer than one release cycle. Don't keep "just in case" code — git has your back.'''
    ),
    (
        "thinking/review-extract-method-refactor",
        "This 80-line function does too many things. Identify extraction points:\n\n```python\ndef process_csv_upload(file):\n    # Validate file type (10 lines)\n    if not file.filename.endswith('.csv'):\n        raise ValueError('Not a CSV')\n    content = file.read().decode('utf-8')\n    if len(content) > 10_000_000:\n        raise ValueError('File too large')\n    \n    # Parse CSV (15 lines)\n    reader = csv.DictReader(io.StringIO(content))\n    required = {'name', 'email', 'department'}\n    if not required.issubset(set(reader.fieldnames)):\n        raise ValueError(f'Missing columns: {required - set(reader.fieldnames)}')\n    rows = list(reader)\n    \n    # Validate each row (20 lines)\n    errors = []\n    valid_rows = []\n    for i, row in enumerate(rows, 1):\n        if not row['email'] or '@' not in row['email']:\n            errors.append(f'Row {i}: invalid email')\n        elif row['department'] not in VALID_DEPARTMENTS:\n            errors.append(f'Row {i}: invalid department')\n        else:\n            valid_rows.append(row)\n    \n    # Import valid rows (15 lines)\n    imported = 0\n    for row in valid_rows:\n        user = User(name=row['name'], email=row['email'], \n                    department=row['department'])\n        db.session.add(user)\n        imported += 1\n    db.session.commit()\n    \n    # Build report (10 lines)\n    return {\n        'total_rows': len(rows),\n        'imported': imported,\n        'errors': errors,\n        'error_count': len(errors),\n    }\n```",
        r'''<think>
Clear responsibility boundaries in the code: validate file → parse CSV → validate rows → import → report. Each section is a natural extraction point.
</think>

## Refactored: One Function Per Responsibility

```python
def process_csv_upload(file):
    content = _validate_file(file)
    rows = _parse_csv(content)
    valid_rows, errors = _validate_rows(rows)
    imported = _import_users(valid_rows)
    return _build_report(rows, imported, errors)

def _validate_file(file) -> str:
    if not file.filename.endswith('.csv'):
        raise ValueError('Not a CSV')
    content = file.read().decode('utf-8')
    if len(content) > 10_000_000:
        raise ValueError('File too large')
    return content

def _parse_csv(content: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(content))
    required = {'name', 'email', 'department'}
    if not required.issubset(set(reader.fieldnames or [])):
        missing = required - set(reader.fieldnames or [])
        raise ValueError(f'Missing columns: {missing}')
    return list(reader)

def _validate_rows(rows: list[dict]) -> tuple[list[dict], list[str]]:
    errors = []
    valid = []
    for i, row in enumerate(rows, 1):
        if not row['email'] or '@' not in row['email']:
            errors.append(f'Row {i}: invalid email')
        elif row['department'] not in VALID_DEPARTMENTS:
            errors.append(f'Row {i}: invalid department')
        else:
            valid.append(row)
    return valid, errors

def _import_users(rows: list[dict]) -> int:
    for row in rows:
        db.session.add(User(
            name=row['name'], email=row['email'],
            department=row['department'],
        ))
    db.session.commit()
    return len(rows)

def _build_report(all_rows, imported, errors):
    return {
        'total_rows': len(all_rows),
        'imported': imported,
        'errors': errors,
        'error_count': len(errors),
    }
```

**The main function reads like a summary.** Each helper has one job, is independently testable, and can be modified without affecting the others.'''
    ),
    (
        "thinking/review-temporal-coupling",
        "This code breaks if methods aren't called in a specific order, but nothing enforces that order:\n\n```python\nclass ReportBuilder:\n    def set_title(self, title):\n        self.title = title\n    \n    def set_data(self, data):\n        self.data = data\n    \n    def set_format(self, fmt):\n        self.format = fmt\n    \n    def generate(self):\n        # Crashes if set_title, set_data, or set_format weren't called first!\n        if self.format == 'pdf':\n            return PDFReport(self.title, self.data)\n        return HTMLReport(self.title, self.data)\n\n# Easy to misuse:\nbuilder = ReportBuilder()\nbuilder.set_data(data)\nbuilder.generate()  # AttributeError: 'ReportBuilder' has no attribute 'title'\n```",
        r'''<think>
Temporal coupling — methods must be called in a specific order but nothing enforces it. The generate() method assumes set_title, set_data, and set_format were called.

Fix: require all necessary data upfront, either in constructor or as generate() parameters.
</think>

**Temporal coupling — `generate()` crashes if setters weren't called in the right order.** Nothing enforces the required sequence.

## Fix: Require Data Upfront

```python
# Option 1: Constructor (simplest)
class ReportBuilder:
    def __init__(self, title: str, data: list, fmt: str = 'html'):
        self.title = title
        self.data = data
        self.format = fmt

    def generate(self):
        if self.format == 'pdf':
            return PDFReport(self.title, self.data)
        return HTMLReport(self.title, self.data)

# Can't misuse — all required data provided at construction
report = ReportBuilder('Sales Q1', data, 'pdf').generate()

# Option 2: generate() takes parameters
class ReportGenerator:
    def generate(self, title: str, data: list, fmt: str = 'html'):
        if fmt == 'pdf':
            return PDFReport(title, data)
        return HTMLReport(title, data)

# Option 3: Builder pattern (if construction is complex)
class ReportBuilder:
    def __init__(self, title: str, data: list):
        self._title = title
        self._data = data
        self._format = 'html'

    def as_pdf(self):
        self._format = 'pdf'
        return self  # Chainable

    def generate(self):
        if self._format == 'pdf':
            return PDFReport(self._title, self._data)
        return HTMLReport(self._title, self._data)

# Fluent API — required args in constructor, optional via chaining
report = ReportBuilder('Sales Q1', data).as_pdf().generate()
```

**Rule:** If a method requires prior setup, take that data as a constructor argument or method parameter. Don't rely on callers to know the right sequence.'''
    ),
    (
        "thinking/review-exception-handling-smells",
        "Review the exception handling in this code:\n\n```python\n# Smell 1: Catch-all\ntry:\n    result = process(data)\nexcept:\n    pass\n\n# Smell 2: Exception as flow control\ntry:\n    user = users[username]\nexcept KeyError:\n    user = create_user(username)\n\n# Smell 3: Catching too broad\ntry:\n    data = json.loads(response.text)\n    user_id = data['user']['id']\n    permissions = fetch_permissions(user_id)\n    result = check_access(permissions, resource)\nexcept Exception as e:\n    logger.error(f'Error: {e}')\n    return default_result\n\n# Smell 4: Swallowing and re-raising\ntry:\n    do_work()\nexcept ValueError as e:\n    logger.error(e)\n    raise ValueError(str(e))  # Loses original traceback!\n\n# Smell 5: Try around everything\ntry:\n    config = load_config()\n    db = connect_db(config)\n    cache = connect_cache(config)\n    app = create_app(db, cache)\n    app.run()\nexcept Exception as e:\n    print(f'Something went wrong: {e}')\n```",
        r'''<think>
Five distinct exception handling smells:

1. Bare `except: pass` — swallows ALL exceptions including SystemExit, KeyboardInterrupt. Never know if something failed.
2. Exception as flow control — using try/except for expected cases. `dict.get()` is cleaner.
3. Catching too broad — 4 different operations with one except. Can't distinguish JSON parse error from network error from permission error.
4. Losing traceback — `raise ValueError(str(e))` creates a new exception, losing the original stack trace.
5. Giant try block — everything in one try, impossible to know what failed.
</think>

## Five Exception Handling Smells and Fixes

### 1. Bare `except: pass` — Silent Failure
```python
# BAD
try:
    result = process(data)
except:
    pass

# GOOD — catch specific exceptions, at least log
try:
    result = process(data)
except ProcessingError as e:
    logger.warning(f'Processing failed: {e}')
    result = default_value
```

### 2. Exception as Flow Control
```python
# SMELL — exception for expected case
try:
    user = users[username]
except KeyError:
    user = create_user(username)

# BETTER — explicit check
user = users.get(username) or create_user(username)
```

### 3. Catching Too Broadly
```python
# BAD — one catch for 4 operations
try:
    data = json.loads(response.text)
    user_id = data['user']['id']
    permissions = fetch_permissions(user_id)
    result = check_access(permissions, resource)
except Exception:
    return default_result

# GOOD — specific catches
try:
    data = json.loads(response.text)
except json.JSONDecodeError:
    return error_response('Invalid JSON from upstream')

try:
    user_id = data['user']['id']
except KeyError:
    return error_response('Missing user ID in response')

permissions = fetch_permissions(user_id)  # Let network errors propagate
result = check_access(permissions, resource)
```

### 4. Losing Traceback
```python
# BAD — creates new exception, loses stack trace
except ValueError as e:
    raise ValueError(str(e))

# GOOD — re-raise original or chain
except ValueError:
    raise  # Preserves original traceback

# Or chain with context
except ValueError as e:
    raise ProcessingError('Failed to process data') from e
```

### 5. Giant Try Block
```python
# BAD — can't tell what failed
try:
    config = load_config()
    db = connect_db(config)
    cache = connect_cache(config)
    app = create_app(db, cache)
except Exception:
    print('Something went wrong')

# GOOD — each operation has clear failure handling
config = load_config()  # Let ConfigError propagate with clear message
db = connect_db(config)  # Let DBConnectionError propagate
cache = connect_cache(config)  # Let CacheConnectionError propagate
app = create_app(db, cache)
```'''
    ),
    (
        "thinking/review-duplicated-logic-dry",
        "Three API endpoints have nearly identical validation and processing logic:\n\n```python\n@app.route('/api/users', methods=['POST'])\ndef create_user():\n    data = request.json\n    if not data.get('name') or len(data['name']) > 100:\n        return jsonify(error='Invalid name'), 400\n    if not data.get('email') or '@' not in data['email']:\n        return jsonify(error='Invalid email'), 400\n    user = User(name=data['name'], email=data['email'])\n    db.session.add(user)\n    db.session.commit()\n    return jsonify(user.to_dict()), 201\n\n@app.route('/api/admins', methods=['POST'])\ndef create_admin():\n    data = request.json\n    if not data.get('name') or len(data['name']) > 100:\n        return jsonify(error='Invalid name'), 400\n    if not data.get('email') or '@' not in data['email']:\n        return jsonify(error='Invalid email'), 400\n    admin = Admin(name=data['name'], email=data['email'], role='admin')\n    db.session.add(admin)\n    db.session.commit()\n    return jsonify(admin.to_dict()), 201\n\n@app.route('/api/guests', methods=['POST'])\ndef create_guest():\n    data = request.json\n    if not data.get('name') or len(data['name']) > 100:\n        return jsonify(error='Invalid name'), 400\n    if not data.get('email') or '@' not in data['email']:\n        return jsonify(error='Invalid email'), 400\n    guest = Guest(name=data['name'], email=data['email'], expires=tomorrow())\n    db.session.add(guest)\n    db.session.commit()\n    return jsonify(guest.to_dict()), 201\n```",
        r'''<think>
Identical validation logic copied 3 times. If the email validation rule changes, you must update 3 places. Extract the common validation and use a factory or generic create function.
</think>

**Same validation copied 3 times.** A rule change requires updating all three endpoints.

## Fix: Extract Shared Logic

```python
def validate_person_data(data):
    """Shared validation for all person types."""
    errors = []
    if not data.get('name') or len(data['name']) > 100:
        errors.append('Invalid name')
    if not data.get('email') or '@' not in data['email']:
        errors.append('Invalid email')
    if errors:
        raise ValidationError(errors)

def create_entity(model_class, data, **extra_fields):
    """Generic create for any person-type model."""
    validate_person_data(data)
    entity = model_class(name=data['name'], email=data['email'], **extra_fields)
    db.session.add(entity)
    db.session.commit()
    return jsonify(entity.to_dict()), 201

@app.route('/api/users', methods=['POST'])
def create_user():
    return create_entity(User, request.json)

@app.route('/api/admins', methods=['POST'])
def create_admin():
    return create_entity(Admin, request.json, role='admin')

@app.route('/api/guests', methods=['POST'])
def create_guest():
    return create_entity(Guest, request.json, expires=tomorrow())
```

**Validation logic exists in ONE place.** Adding a new validation rule or a new person type requires minimal changes.'''
    ),
    (
        "thinking/review-naming-conventions",
        "Review the naming in this code:\n\n```python\ndef proc(d, f=True, x=None):\n    r = []\n    for i in d:\n        if f:\n            t = i['val'] * 1.08\n        else:\n            t = i['val']\n        if x and t > x:\n            continue\n        r.append({'n': i['n'], 'v': t})\n    return r\n\nclass Mgr:\n    def __init__(self):\n        self.lst = []\n        self.cnt = 0\n    \n    def do(self, itm):\n        self.lst.append(itm)\n        self.cnt += 1\n    \n    def clr(self):\n        self.lst = []\n        self.cnt = 0\n```",
        r'''<think>
Terrible naming: proc, d, f, x, r, i, t, n, v, Mgr, lst, cnt, do, clr, itm. No one can understand this code without reading every line.
</think>

**Cryptic abbreviations everywhere.** No one can understand this code without tracing every variable.

## Fix: Self-Documenting Names

```python
def calculate_prices(items, include_tax=True, max_price=None):
    results = []
    for item in items:
        if include_tax:
            price = item['value'] * 1.08
        else:
            price = item['value']
        if max_price and price > max_price:
            continue
        results.append({'name': item['name'], 'price': price})
    return results

class ItemCollection:
    def __init__(self):
        self.items = []
        self.count = 0

    def add(self, item):
        self.items.append(item)
        self.count += 1

    def clear(self):
        self.items = []
        self.count = 0
```

**Naming rules:**
- Functions: verb + noun (`calculate_prices`, not `proc`)
- Booleans: `include_tax` (reads as English), not `f`
- Variables: describe the content (`items`, not `d`)
- Classes: noun describing the concept (`ItemCollection`, not `Mgr`)
- Avoid abbreviations unless universally understood (`url`, `id`, `db` are OK; `mgr`, `lst`, `cnt` are not)'''
    ),
    (
        "thinking/review-law-of-demeter",
        "This code reaches through multiple levels of objects:\n\n```python\ndef get_manager_email(employee):\n    return employee.department.manager.contact_info.email\n\ndef approve_expense(expense):\n    budget = expense.project.department.budget_allocation.remaining\n    if expense.amount > budget:\n        raise OverBudgetError()\n    expense.project.department.budget_allocation.remaining -= expense.amount\n    expense.approver = expense.project.department.manager\n    expense.status = 'approved'\n```",
        r'''<think>
Law of Demeter violations — reaching through chains of objects. If any intermediate object's structure changes, this code breaks. Also tightly couples this code to the internal structure of 4 different classes.

Fix: each object provides what you need. "Don't ask for things to ask things from — ask for things directly."
</think>

**Law of Demeter violation — long chains of attribute access.** If `Department` changes how it stores `manager`, all callers break.

## Fix: Tell, Don't Ask

```python
# Each object provides what callers need
class Employee:
    def get_manager_email(self):
        return self.department.get_manager_email()

class Department:
    def get_manager_email(self):
        return self.manager.email

    def has_budget_for(self, amount):
        return self.budget_allocation.remaining >= amount

    def deduct_budget(self, amount):
        self.budget_allocation.remaining -= amount

    @property
    def manager(self):
        return self._manager

class Project:
    def approve_expense(self, expense):
        if not self.department.has_budget_for(expense.amount):
            raise OverBudgetError()
        self.department.deduct_budget(expense.amount)
        expense.approver = self.department.manager
        expense.status = 'approved'

# Clean call site — one dot, not four
manager_email = employee.get_manager_email()
project.approve_expense(expense)
```

**Rule:** Only talk to your immediate friends. Each object wraps its internals and provides the specific answers callers need.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
