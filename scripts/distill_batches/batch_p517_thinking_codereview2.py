"""Phase 1E: Foundation Thinking — Code Review & Refactoring (Part 2/4)
Design pattern misuse, SOLID violations, API design smells, abstraction problems."""

PAIRS = [
    (
        "thinking/review-singleton-abuse",
        "Our codebase uses singletons everywhere. Here's a typical example:\n\n```python\nclass DatabaseManager:\n    _instance = None\n    \n    def __new__(cls):\n        if cls._instance is None:\n            cls._instance = super().__new__(cls)\n            cls._instance._connection = psycopg2.connect(DATABASE_URL)\n        return cls._instance\n    \n    def query(self, sql, params=None):\n        return self._connection.execute(sql, params)\n\nclass UserService:\n    def get_user(self, user_id):\n        db = DatabaseManager()\n        return db.query('SELECT * FROM users WHERE id = %s', (user_id,))\n\nclass OrderService:\n    def create_order(self, user_id, items):\n        db = DatabaseManager()\n        # ... order creation logic\n```\n\nIs this a good pattern? Code review please.",
        r'''<think>
Let me analyze this singleton pattern usage critically.

Problems I see:

1. **Hidden dependencies** — `UserService` and `OrderService` secretly depend on `DatabaseManager` but don't declare it. You can't tell from the constructor what they need.

2. **Untestable** — How do you unit test `UserService` without a real database? You can't easily inject a mock because the dependency is created inside the method.

3. **Single connection** — The singleton holds ONE connection. In a web server with concurrent requests, this will cause race conditions or serialization bottlenecks.

4. **Lifecycle management** — When does the connection close? What if it drops? The singleton has no reconnection logic and no cleanup.

5. **SOLID violations**:
   - Single Responsibility: DatabaseManager is both a connection manager AND a singleton lifecycle manager
   - Dependency Inversion: High-level services depend on a concrete class, not an abstraction
   - Open/Closed: Can't switch to a different database without modifying all services

The fix is dependency injection — pass the database dependency in rather than having services fetch it themselves.
</think>

This is a textbook case of **singleton abuse** — one of the most common anti-patterns in Python codebases. Here's what's wrong and how to fix it:

## Problems

### 1. Hidden Dependencies
Services secretly depend on `DatabaseManager` but don't declare it. Reading the constructor tells you nothing about what the class needs.

### 2. Impossible to Test
```python
# How do you test this without a real database?
def test_get_user():
    service = UserService()
    # DatabaseManager() will try to connect to real DB
    result = service.get_user(1)  # Fails in CI
```

### 3. Single Connection Bottleneck
One connection shared across all threads/requests — causes race conditions in any concurrent environment.

### 4. No Lifecycle Management
Connection never closes, no reconnection on failure, no cleanup.

## The Fix: Dependency Injection

```python
from abc import ABC, abstractmethod

class Database(ABC):
    @abstractmethod
    def query(self, sql, params=None):
        ...

class PostgresDatabase(Database):
    def __init__(self, connection_pool):
        self._pool = connection_pool

    def query(self, sql, params=None):
        with self._pool.getconn() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                return cur.fetchall()

class UserService:
    def __init__(self, db: Database):
        self._db = db

    def get_user(self, user_id):
        return self._db.query(
            'SELECT * FROM users WHERE id = %s', (user_id,)
        )
```

Now testing is trivial:
```python
def test_get_user():
    mock_db = Mock(spec=Database)
    mock_db.query.return_value = [{'id': 1, 'name': 'Alice'}]
    service = UserService(mock_db)
    result = service.get_user(1)
    assert result[0]['name'] == 'Alice'
```

**Rule of thumb**: If you're using a singleton, you probably need dependency injection instead. The only legitimate singleton use is for truly global, stateless configuration.'''
    ),
    (
        "thinking/review-interface-segregation",
        "We have a base class that all our data processors must implement:\n\n```python\nclass DataProcessor(ABC):\n    @abstractmethod\n    def read_from_file(self, path: str) -> pd.DataFrame: ...\n    \n    @abstractmethod\n    def read_from_api(self, url: str, api_key: str) -> pd.DataFrame: ...\n    \n    @abstractmethod\n    def read_from_database(self, query: str) -> pd.DataFrame: ...\n    \n    @abstractmethod\n    def validate(self, df: pd.DataFrame) -> bool: ...\n    \n    @abstractmethod\n    def transform(self, df: pd.DataFrame) -> pd.DataFrame: ...\n    \n    @abstractmethod\n    def write_to_file(self, df: pd.DataFrame, path: str) -> None: ...\n    \n    @abstractmethod\n    def write_to_database(self, df: pd.DataFrame, table: str) -> None: ...\n    \n    @abstractmethod\n    def send_notification(self, message: str) -> None: ...\n```\n\nSome of our processors only read from files and write to files. They have to implement `read_from_api`, `read_from_database`, etc. with `raise NotImplementedError`. Is there a better design?",
        r'''<think>
This is a classic Interface Segregation Principle (ISP) violation — the "I" in SOLID.

The problem: every implementer is forced to depend on methods it doesn't use. A file-only processor must implement API reading, database reading, database writing, and notifications — all with `raise NotImplementedError`.

Signs of the violation:
- `raise NotImplementedError` in implementations = the interface is too fat
- The class has 8 abstract methods covering 4 different concerns (reading, validation, transformation, writing, notification)
- SRP violation too — one class handles reading, transforming, writing, AND notifications

The fix: split into focused interfaces (protocols in Python) and compose them.

Let me think about the right granularity:
- Reader (source-specific)
- Validator
- Transformer
- Writer (destination-specific)
- Notifier

Each processor composes only what it needs.
</think>

This violates the **Interface Segregation Principle** — clients shouldn't depend on methods they don't use. The `raise NotImplementedError` pattern is the telltale sign.

## The Problem

Your file-only processor looks like this:
```python
class FileProcessor(DataProcessor):
    def read_from_file(self, path): return pd.read_csv(path)
    def read_from_api(self, url, api_key): raise NotImplementedError  # Forced
    def read_from_database(self, query): raise NotImplementedError    # Forced
    def validate(self, df): return len(df) > 0
    def transform(self, df): return df.dropna()
    def write_to_file(self, df, path): df.to_csv(path)
    def write_to_database(self, df, table): raise NotImplementedError # Forced
    def send_notification(self, msg): raise NotImplementedError       # Forced
```

4 out of 8 methods are dead code. This is a maintenance burden and a runtime trap.

## The Fix: Split Into Focused Protocols

```python
from typing import Protocol

class FileReader(Protocol):
    def read_from_file(self, path: str) -> pd.DataFrame: ...

class ApiReader(Protocol):
    def read_from_api(self, url: str, api_key: str) -> pd.DataFrame: ...

class DatabaseReader(Protocol):
    def read_from_database(self, query: str) -> pd.DataFrame: ...

class Validator(Protocol):
    def validate(self, df: pd.DataFrame) -> bool: ...

class Transformer(Protocol):
    def transform(self, df: pd.DataFrame) -> pd.DataFrame: ...

class FileWriter(Protocol):
    def write_to_file(self, df: pd.DataFrame, path: str) -> None: ...

class DatabaseWriter(Protocol):
    def write_to_database(self, df: pd.DataFrame, table: str) -> None: ...

class Notifier(Protocol):
    def send_notification(self, message: str) -> None: ...
```

Now each processor implements only what it needs:
```python
class CsvProcessor:
    """Implements FileReader, Validator, Transformer, FileWriter"""
    def read_from_file(self, path): return pd.read_csv(path)
    def validate(self, df): return len(df) > 0
    def transform(self, df): return df.dropna()
    def write_to_file(self, df, path): df.to_csv(path, index=False)

class ApiToDbProcessor:
    """Implements ApiReader, Transformer, DatabaseWriter"""
    def read_from_api(self, url, api_key): ...
    def transform(self, df): ...
    def write_to_database(self, df, table): ...
```

Functions accept only the capabilities they need:
```python
def etl_pipeline(
    reader: FileReader,
    transformer: Transformer,
    writer: FileWriter,
):
    df = reader.read_from_file("input.csv")
    df = transformer.transform(df)
    writer.write_to_file(df, "output.csv")
```

**Key insight**: Protocols provide structural typing — no inheritance required. Classes just implement the methods and Python's duck typing handles the rest.'''
    ),
    (
        "thinking/review-liskov-substitution",
        "We're getting weird bugs after a junior dev added `ReadOnlyUser` to our user hierarchy:\n\n```python\nclass User:\n    def __init__(self, name, email):\n        self.name = name\n        self.email = email\n        self._permissions = set()\n    \n    def add_permission(self, perm):\n        self._permissions.add(perm)\n    \n    def remove_permission(self, perm):\n        self._permissions.discard(perm)\n    \n    def has_permission(self, perm):\n        return perm in self._permissions\n\nclass ReadOnlyUser(User):\n    def add_permission(self, perm):\n        raise PermissionError(\"Read-only users cannot have permissions modified\")\n    \n    def remove_permission(self, perm):\n        raise PermissionError(\"Read-only users cannot have permissions modified\")\n\ndef grant_access(user: User, resource: str):\n    user.add_permission(f'access:{resource}')\n    log_audit(f'Granted {resource} access to {user.name}')\n```\n\nNow `grant_access` crashes when passed a `ReadOnlyUser`. The junior says \"just add a try/except\". Is that the right fix?",
        r'''<think>
This is a Liskov Substitution Principle (LSP) violation — the "L" in SOLID.

LSP says: if S is a subtype of T, then objects of type T can be replaced with objects of type S without altering the correctness of the program.

Here, `ReadOnlyUser` is a subtype of `User`, but you can't substitute it anywhere a `User` is expected because it throws exceptions where `User` doesn't. The `grant_access` function accepts `User` but breaks with `ReadOnlyUser`.

The junior's suggestion of "just add try/except" is wrong because:
1. It spreads defensive checks everywhere `User` is used
2. Every function that calls `add_permission` or `remove_permission` needs the same guard
3. It means the type hierarchy is lying — `ReadOnlyUser` promises to be a `User` but doesn't behave like one

Solutions:
1. Composition over inheritance — don't make ReadOnlyUser extend User
2. Split the interface — separate "readable user" from "modifiable user"
3. Use the type system to prevent the mistake at compile/lint time

The best fix is to restructure the hierarchy so read-only users aren't pretending to be fully mutable users.
</think>

The junior's fix is wrong. Adding try/except everywhere is a band-aid that spreads through the entire codebase. This is a **Liskov Substitution Principle** violation.

## Why It's Broken

`ReadOnlyUser` inherits from `User` but **breaks the contract** — it promises to be a `User` yet throws exceptions where `User` doesn't. Every function accepting `User` is now a potential crash site:

```python
grant_access(regular_user, "dashboard")  # Works
grant_access(readonly_user, "dashboard") # BOOM - PermissionError
```

## Why Try/Except Is Wrong

```python
# This "fix" would need to be added EVERYWHERE
def grant_access(user: User, resource: str):
    try:
        user.add_permission(f'access:{resource}')
    except PermissionError:
        pass  # Silently fails — is access granted or not??
```

Now you have silent failures, unclear behavior, and every function using `User` needs the same guard.

## The Real Fix: Restructure the Hierarchy

```python
class User:
    """Base user with read-only capabilities."""
    def __init__(self, name, email):
        self.name = name
        self.email = email
        self._permissions = frozenset()

    def has_permission(self, perm):
        return perm in self._permissions

class MutableUser(User):
    """User whose permissions can be modified."""
    def __init__(self, name, email):
        super().__init__(name, email)
        self._permissions = set()

    def add_permission(self, perm):
        self._permissions.add(perm)

    def remove_permission(self, perm):
        self._permissions.discard(perm)

def grant_access(user: MutableUser, resource: str):
    """Type signature prevents passing read-only users."""
    user.add_permission(f'access:{resource}')
    log_audit(f'Granted {resource} access to {user.name}')

def check_access(user: User, resource: str) -> bool:
    """Works with ANY user type."""
    return user.has_permission(f'access:{resource}')
```

Now the type system prevents the bug:
- `grant_access(readonly_user, "x")` → type checker catches it
- `check_access(readonly_user, "x")` → works fine, read-only is naturally supported

**LSP rule**: Subtypes must honor the parent's contract. If a subclass needs to restrict behavior, the hierarchy is upside down.'''
    ),
    (
        "thinking/review-open-closed-violation",
        "Every time we add a new payment method, we have to modify this function. It's getting out of hand:\n\n```python\ndef process_payment(order, payment_method, payment_details):\n    if payment_method == 'credit_card':\n        card = payment_details['card_number']\n        expiry = payment_details['expiry']\n        cvv = payment_details['cvv']\n        result = stripe.charges.create(\n            amount=order.total,\n            currency='usd',\n            source=create_token(card, expiry, cvv)\n        )\n        if result.status == 'succeeded':\n            order.mark_paid()\n            send_receipt(order, 'card')\n    elif payment_method == 'paypal':\n        redirect_url = paypal.create_payment(\n            amount=order.total,\n            return_url='/paypal/confirm',\n            cancel_url='/paypal/cancel'\n        )\n        return {'redirect': redirect_url}\n    elif payment_method == 'crypto':\n        address = crypto_gateway.create_invoice(\n            amount_usd=order.total,\n            callback_url='/crypto/webhook'\n        )\n        return {'crypto_address': address}\n    elif payment_method == 'apple_pay':\n        # Added last month\n        token = payment_details['apple_token']\n        result = stripe.charges.create(\n            amount=order.total,\n            currency='usd',\n            source=token\n        )\n        if result.status == 'succeeded':\n            order.mark_paid()\n            send_receipt(order, 'apple_pay')\n    elif payment_method == 'bank_transfer':\n        # Added last week\n        # ... 30 more lines\n        pass\n    else:\n        raise ValueError(f'Unknown payment method: {payment_method}')\n```\n\nHow should I refactor this?",
        r'''<think>
Classic Open/Closed Principle violation — the "O" in SOLID. The function must be modified every time a new payment method is added. It's a growing if/elif chain that will only get worse.

The fix is the Strategy pattern — define a common interface for payment processors and register them. New payment methods are added by creating a new class, not by modifying existing code.

I also notice:
- Each branch has different return types (some return dicts, some return None, some mark orders as paid) — this inconsistency makes the caller's job harder
- The function is doing too much: validating, processing, marking orders, sending receipts
- Error handling is inconsistent

The refactored version should:
1. Define a PaymentProcessor protocol/ABC
2. Each payment method is a class implementing that protocol
3. A registry maps method names to processor instances
4. The main function just looks up and delegates
</think>

This violates the **Open/Closed Principle** — the function must be modified every time you add a payment method. The Strategy pattern fixes this cleanly:

## Refactored Design

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class PaymentResult:
    success: bool
    redirect_url: str | None = None
    payment_address: str | None = None
    error: str | None = None

class PaymentProcessor(ABC):
    @abstractmethod
    def process(self, order, payment_details: dict) -> PaymentResult:
        ...

class CreditCardProcessor(PaymentProcessor):
    def process(self, order, payment_details):
        result = stripe.charges.create(
            amount=order.total,
            currency='usd',
            source=create_token(
                payment_details['card_number'],
                payment_details['expiry'],
                payment_details['cvv'],
            ),
        )
        if result.status == 'succeeded':
            order.mark_paid()
            send_receipt(order, 'card')
            return PaymentResult(success=True)
        return PaymentResult(success=False, error=result.failure_message)

class PayPalProcessor(PaymentProcessor):
    def process(self, order, payment_details):
        url = paypal.create_payment(
            amount=order.total,
            return_url='/paypal/confirm',
            cancel_url='/paypal/cancel',
        )
        return PaymentResult(success=True, redirect_url=url)

class CryptoProcessor(PaymentProcessor):
    def process(self, order, payment_details):
        address = crypto_gateway.create_invoice(
            amount_usd=order.total,
            callback_url='/crypto/webhook',
        )
        return PaymentResult(success=True, payment_address=address)

# Registry — add new methods here, never modify process_payment
PROCESSORS: dict[str, PaymentProcessor] = {
    'credit_card': CreditCardProcessor(),
    'paypal': PayPalProcessor(),
    'crypto': CryptoProcessor(),
    'apple_pay': ApplePayProcessor(),
}

def process_payment(order, payment_method: str, payment_details: dict) -> PaymentResult:
    processor = PROCESSORS.get(payment_method)
    if not processor:
        raise ValueError(f'Unknown payment method: {payment_method}')
    return processor.process(order, payment_details)
```

## Benefits
1. **Adding a new method** = create one new class + one registry entry. Zero changes to existing code
2. **Each processor is independently testable** — mock the external gateway, test the logic
3. **Consistent return type** — `PaymentResult` instead of mixed dicts/None/implicit returns
4. **Single Responsibility** — each processor handles exactly one payment flow'''
    ),
    (
        "thinking/review-anemic-domain-model",
        "Review this code. Something feels off about the design but I can't pinpoint it:\n\n```python\n# models.py\nclass Order:\n    def __init__(self):\n        self.id = None\n        self.items = []\n        self.status = 'pending'\n        self.total = 0\n        self.discount = 0\n        self.shipping_cost = 0\n        self.customer_id = None\n        self.created_at = None\n\n# services.py\nclass OrderService:\n    def calculate_total(self, order):\n        order.total = sum(item.price * item.quantity for item in order.items)\n    \n    def apply_discount(self, order, coupon_code):\n        coupon = self.coupon_repo.find(coupon_code)\n        if coupon and coupon.is_valid():\n            order.discount = order.total * coupon.percent / 100\n            order.total -= order.discount\n    \n    def calculate_shipping(self, order):\n        if order.total > 100:\n            order.shipping_cost = 0\n        else:\n            order.shipping_cost = sum(item.weight * 0.5 for item in order.items)\n    \n    def can_cancel(self, order):\n        return order.status in ('pending', 'confirmed')\n    \n    def cancel(self, order):\n        if self.can_cancel(order):\n            order.status = 'cancelled'\n            self.refund_service.refund(order)\n    \n    def ship(self, order):\n        if order.status == 'confirmed':\n            order.status = 'shipped'\n            self.notification_service.notify_shipped(order)\n```",
        r'''<think>
This is the **Anemic Domain Model** anti-pattern. The `Order` class is just a data bag with no behavior — all logic lives in `OrderService`.

The problems:
1. `Order` is basically a dict/struct — it has no invariants, no business logic, no encapsulation
2. Anyone can set `order.status = 'whatever'` directly, bypassing business rules
3. `OrderService` is a procedural grab-bag that operates ON the order rather than the order knowing its own rules
4. Status transitions have rules (`can_cancel` checks) but they're not enforced — nothing stops `order.status = 'shipped'` from a pending order
5. The order's total can be out of sync with its items because calculation is external

The fix: move behavior into the domain model. The Order should know how to calculate its total, validate transitions, and enforce its own invariants.

External services (refunds, notifications, coupon lookup) still belong in a service layer, but the domain logic should live on the entity.
</think>

You've spotted the **Anemic Domain Model** anti-pattern. `Order` is a dumb data bag; all logic lives in a procedural service class.

## What's Wrong

| Problem | Consequence |
|---------|-------------|
| `Order` has no behavior | Anyone can set `order.status = 'shipped'` directly, bypassing rules |
| `total` is externally calculated | Items can change without total updating — silent inconsistency |
| Status transitions aren't enforced | No guarantee the state machine is respected |
| Service is a procedural grab-bag | Logic for one concept scattered across a separate class |

## The Fix: Rich Domain Model

```python
class Order:
    CANCELLABLE = frozenset({'pending', 'confirmed'})

    def __init__(self, customer_id: str):
        self.id = None
        self._items = []
        self._status = 'pending'
        self.customer_id = customer_id
        self.discount = Decimal(0)
        self.created_at = datetime.utcnow()

    @property
    def status(self):
        return self._status

    @property
    def items(self):
        return tuple(self._items)  # Immutable view

    @property
    def subtotal(self) -> Decimal:
        return sum(item.price * item.quantity for item in self._items)

    @property
    def shipping_cost(self) -> Decimal:
        if self.subtotal > 100:
            return Decimal(0)
        return sum(item.weight * Decimal('0.5') for item in self._items)

    @property
    def total(self) -> Decimal:
        return self.subtotal - self.discount + self.shipping_cost

    def add_item(self, item):
        if self._status != 'pending':
            raise InvalidOperation("Cannot modify a non-pending order")
        self._items.append(item)

    def apply_discount(self, coupon):
        if not coupon.is_valid():
            raise InvalidCoupon(coupon.code)
        self.discount = self.subtotal * coupon.percent / 100

    def confirm(self):
        if self._status != 'pending':
            raise InvalidTransition(self._status, 'confirmed')
        if not self._items:
            raise InvalidOperation("Cannot confirm empty order")
        self._status = 'confirmed'

    def ship(self):
        if self._status != 'confirmed':
            raise InvalidTransition(self._status, 'shipped')
        self._status = 'shipped'

    def cancel(self):
        if self._status not in self.CANCELLABLE:
            raise InvalidTransition(self._status, 'cancelled')
        self._status = 'cancelled'

# Thin service layer for orchestration only
class OrderService:
    def cancel_order(self, order_id):
        order = self.repo.get(order_id)
        order.cancel()  # Domain enforces the rules
        self.repo.save(order)
        self.refund_service.refund(order)
```

## Key Principles
- **Tell, Don't Ask** — `order.cancel()` instead of `if service.can_cancel(order): order.status = 'cancelled'`
- **Encapsulation** — `_status` is private, transitions go through methods that enforce rules
- **Always-consistent** — `total` is computed, never stale
- **Service layer** handles orchestration (DB, external services) not business logic'''
    ),
    (
        "thinking/review-shotgun-surgery",
        "Every time we change how user display names work, we have to modify 6+ files. Here's the pattern:\n\n```python\n# views/profile.py\ndef render_profile(user):\n    if user.nickname:\n        display = user.nickname\n    elif user.first_name:\n        display = f'{user.first_name} {user.last_name}'.strip()\n    else:\n        display = user.email.split('@')[0]\n    return template.render(display_name=display)\n\n# views/comments.py\ndef render_comment(comment):\n    user = comment.author\n    if user.nickname:\n        name = user.nickname\n    elif user.first_name:\n        name = f'{user.first_name} {user.last_name}'.strip()\n    else:\n        name = user.email.split('@')[0]\n    return f'<span class=\"author\">{name}</span>: {comment.text}'\n\n# api/serializers.py\nclass UserSerializer:\n    def to_dict(self, user):\n        if user.nickname:\n            display_name = user.nickname\n        elif user.first_name:\n            display_name = f'{user.first_name} {user.last_name}'.strip()\n        else:\n            display_name = user.email.split('@')[0]\n        return {'id': user.id, 'display_name': display_name}\n\n# notifications/email.py\ndef send_welcome(user):\n    if user.nickname:\n        greeting = user.nickname\n    elif user.first_name:\n        greeting = user.first_name\n    else:\n        greeting = user.email.split('@')[0]\n    send_email(user.email, f'Welcome, {greeting}!')\n```\n\nOur PM just asked us to add \"preferred name\" as a new option. That means changing all 6+ files again.",
        r'''<think>
This is the **Shotgun Surgery** code smell — one logical change requires modifications scattered across many files.

The root cause: display name logic is duplicated everywhere instead of living in one place. The User model should own this behavior.

There's also a subtle inconsistency — the email notification version uses just `first_name` for the greeting, while the others use `first_name + last_name`. This kind of divergence is inevitable with copy-paste logic.

Fix: put the display_name logic on the User model as a property. One place to change, one place to test.
</think>

This is **Shotgun Surgery** — one conceptual change (display name logic) forces edits across 6+ files. The fix is trivial but powerful:

## Put It Where It Belongs

```python
class User:
    @property
    def display_name(self) -> str:
        if self.preferred_name:  # New field — add it once
            return self.preferred_name
        if self.nickname:
            return self.nickname
        if self.first_name:
            return f'{self.first_name} {self.last_name}'.strip()
        return self.email.split('@')[0]
```

Now every call site simplifies:

```python
# views/profile.py
def render_profile(user):
    return template.render(display_name=user.display_name)

# views/comments.py
def render_comment(comment):
    return f'<span class="author">{comment.author.display_name}</span>: {comment.text}'

# api/serializers.py
def to_dict(self, user):
    return {'id': user.id, 'display_name': user.display_name}

# notifications/email.py
def send_welcome(user):
    send_email(user.email, f'Welcome, {user.display_name}!')
```

Adding "preferred name" now means changing **one property** instead of six files. You also eliminated a subtle bug — the email version was using just `first_name` while others used `first_name + last_name`.

**Whenever the same if/elif chain appears in 3+ places, it belongs on the object itself.**'''
    ),
    (
        "thinking/review-inappropriate-intimacy",
        "Code review request:\n\n```python\nclass ShoppingCart:\n    def __init__(self):\n        self.items = []\n        self._discount_percent = 0\n    \n    def add_item(self, product, quantity):\n        self.items.append({'product': product, 'quantity': quantity})\n\nclass CheckoutService:\n    def checkout(self, cart: ShoppingCart, user):\n        # Directly reaching into cart internals\n        total = 0\n        for item in cart.items:\n            price = item['product'].price\n            qty = item['quantity']\n            total += price * qty\n        \n        # Accessing private attribute!\n        if cart._discount_percent > 0:\n            total *= (1 - cart._discount_percent / 100)\n        \n        # Rearranging cart internals\n        cart.items.sort(key=lambda x: x['product'].name)\n        \n        # Adding to cart's internal list directly\n        if total > 100:\n            free_item = {'product': Product('Free Gift', 0), 'quantity': 1}\n            cart.items.append(free_item)\n        \n        return self.payment_gateway.charge(user, total)\n```",
        r'''<think>
This is the **Inappropriate Intimacy** smell (also related to Law of Demeter violations). `CheckoutService` knows way too much about `ShoppingCart`'s internal structure:

1. Knows items are stored as a list of dicts with 'product' and 'quantity' keys
2. Accesses `_discount_percent` private attribute directly
3. Sorts the internal list
4. Appends to the internal list directly

If `ShoppingCart` changes its internal representation (e.g., uses a dict keyed by product ID, or switches to dataclass items), `CheckoutService` breaks.

Fix: Cart should expose behavior, not data. Cart calculates its own total, manages its own items.
</think>

**Inappropriate Intimacy** — `CheckoutService` knows everything about `ShoppingCart`'s internal data structures. This creates tight coupling that breaks whenever the cart's internals change.

## Violations

1. **Knows internal data format** — iterates `cart.items` knowing they're dicts with `'product'` and `'quantity'` keys
2. **Accesses private state** — reads `cart._discount_percent` directly
3. **Mutates internals** — sorts `cart.items` and appends to it
4. **Duplicates logic** — total calculation should be the cart's job

## Refactored

```python
class ShoppingCart:
    def __init__(self):
        self._items: list[CartItem] = []
        self._discount_percent = Decimal(0)

    def add_item(self, product, quantity):
        self._items.append(CartItem(product, quantity))

    @property
    def total(self) -> Decimal:
        subtotal = sum(item.line_total for item in self._items)
        if self._discount_percent > 0:
            subtotal *= (1 - self._discount_percent / 100)
        return subtotal

    @property
    def item_count(self) -> int:
        return sum(item.quantity for item in self._items)

    def add_gift(self, product):
        self._items.append(CartItem(product, quantity=1))

class CheckoutService:
    def checkout(self, cart: ShoppingCart, user):
        total = cart.total  # Ask, don't dig

        if total > 100:
            cart.add_gift(Product('Free Gift', 0))  # Use cart's interface

        return self.payment_gateway.charge(user, cart.total)
```

**Principle**: Objects expose behavior, not data. If you're reaching into another object's fields to compute something, that computation belongs on the other object.'''
    ),
    (
        "thinking/review-god-method",
        "This method in our user registration flow is 200 lines long. Here's the abbreviated version:\n\n```python\ndef register_user(request):\n    # Validate input (30 lines)\n    email = request.json.get('email', '').strip().lower()\n    if not email or not re.match(r'^[^@]+@[^@]+\\.[^@]+$', email):\n        return error_response('Invalid email')\n    password = request.json.get('password', '')\n    if len(password) < 8 or not re.search(r'[A-Z]', password):\n        return error_response('Weak password')\n    username = request.json.get('username', '').strip()\n    if not username or len(username) < 3 or not username.isalnum():\n        return error_response('Invalid username')\n    \n    # Check for existing users (15 lines)\n    if db.query('SELECT id FROM users WHERE email = %s', email):\n        return error_response('Email taken')\n    if db.query('SELECT id FROM users WHERE username = %s', username):\n        return error_response('Username taken')\n    \n    # Hash password and create user (20 lines)\n    salt = os.urandom(32)\n    hashed = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 100000)\n    user_id = db.execute('INSERT INTO users ...', ...)\n    \n    # Set up user profile (25 lines)\n    db.execute('INSERT INTO profiles ...', ...)\n    db.execute('INSERT INTO user_settings ...', ...)\n    \n    # Create default workspace (20 lines)\n    workspace_id = db.execute('INSERT INTO workspaces ...', ...)\n    db.execute('INSERT INTO workspace_members ...', ...)\n    \n    # Send verification email (20 lines)\n    token = secrets.token_urlsafe(32)\n    db.execute('INSERT INTO email_verifications ...', ...)\n    email_service.send(email, 'verify', {'token': token, 'name': username})\n    \n    # Set up initial onboarding (15 lines)\n    db.execute('INSERT INTO onboarding_state ...', ...)\n    \n    # Analytics tracking (15 lines)\n    analytics.track('user_registered', {'user_id': user_id, 'source': request.referrer})\n    \n    # Generate session (15 lines)\n    session_token = create_session(user_id)\n    \n    return success_response({'token': session_token, 'user_id': user_id})\n```\n\nHow should I break this up?",
        r'''<think>
This is a God Method — one function doing everything. The comments actually mark the natural seams for extraction. Each comment block is a separate responsibility.

The key insight: the comments telling you what each section does ARE the function names waiting to be extracted.

Let me identify the responsibilities:
1. Input validation
2. Uniqueness checks
3. User creation (hashing + DB)
4. Profile/settings setup
5. Workspace creation
6. Email verification
7. Onboarding setup
8. Analytics
9. Session creation

I should also note: this should probably be wrapped in a transaction since multiple DB writes need to be atomic.
</think>

The comments are your refactoring guide — each one is a function waiting to be extracted.

## Refactored

```python
# Thin controller — orchestrates, doesn't implement
def register_user(request):
    data = validate_registration(request.json)  # Returns validated DTO or raises
    ensure_unique(data.email, data.username)

    with db.transaction():
        user = create_user(data)
        create_default_workspace(user)
        verification_token = create_email_verification(user)

    # Side effects after successful commit
    send_verification_email(user, verification_token)
    track_registration(user, request.referrer)
    session_token = create_session(user.id)

    return success_response({'token': session_token, 'user_id': user.id})

@dataclass
class RegistrationData:
    email: str
    username: str
    password: str

def validate_registration(data: dict) -> RegistrationData:
    email = data.get('email', '').strip().lower()
    if not email or not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        raise ValidationError('Invalid email')

    password = data.get('password', '')
    if len(password) < 8 or not re.search(r'[A-Z]', password):
        raise ValidationError('Weak password')

    username = data.get('username', '').strip()
    if not username or len(username) < 3 or not username.isalnum():
        raise ValidationError('Invalid username')

    return RegistrationData(email=email, username=username, password=password)

def ensure_unique(email: str, username: str):
    if db.query('SELECT id FROM users WHERE email = %s', email):
        raise ConflictError('Email taken')
    if db.query('SELECT id FROM users WHERE username = %s', username):
        raise ConflictError('Username taken')

def create_user(data: RegistrationData) -> User:
    hashed_pw = hash_password(data.password)  # Use bcrypt, not raw pbkdf2
    user_id = db.execute('INSERT INTO users ...', ...)
    db.execute('INSERT INTO profiles ...', ...)
    db.execute('INSERT INTO user_settings ...', ...)
    db.execute('INSERT INTO onboarding_state ...', ...)
    return User(id=user_id, email=data.email, username=data.username)

def create_default_workspace(user: User):
    workspace_id = db.execute('INSERT INTO workspaces ...', ...)
    db.execute('INSERT INTO workspace_members ...', ...)
```

## Key Improvements

1. **Each function does one thing** and is independently testable
2. **Transaction boundary** is explicit — DB writes are atomic, side effects happen after commit
3. **Error handling** uses exceptions instead of early returns, so the controller stays clean
4. **Password hashing**: use `bcrypt` not raw `pbkdf2_hmac` — bcrypt handles salting automatically
5. **Main function reads like a spec** — you can understand the registration flow in 10 seconds'''
    ),
    (
        "thinking/review-boolean-parameters",
        "Code review — I see this pattern throughout our codebase:\n\n```python\ndef send_notification(user, message, is_urgent=False, is_email=False, \n                      is_sms=False, is_push=True, include_unsubscribe=True,\n                      retry_on_failure=True, log_to_analytics=True):\n    if is_urgent:\n        message = f'URGENT: {message}'\n    \n    channels = []\n    if is_email:\n        channels.append('email')\n    if is_sms:\n        channels.append('sms')\n    if is_push:\n        channels.append('push')\n    \n    for channel in channels:\n        try:\n            if channel == 'email':\n                body = message\n                if include_unsubscribe:\n                    body += '\\n\\nUnsubscribe: ...'\n                mailer.send(user.email, body)\n            elif channel == 'sms':\n                sms_gateway.send(user.phone, message[:160])\n            elif channel == 'push':\n                push_service.send(user.device_id, message)\n        except SendError:\n            if retry_on_failure:\n                queue_retry(channel, user, message)\n    \n    if log_to_analytics:\n        analytics.track('notification_sent', ...)\n```\n\nCall sites look like:\n```python\nsend_notification(user, msg, True, True, False, True, True, True, False)\n```",
        r'''<think>
Multiple problems here:

1. **Boolean parameter explosion** — 7 boolean params. Call sites are unreadable: `True, True, False, True, True, True, False` — what does each one mean?
2. **Flag arguments** — the function does completely different things based on flags. It's really multiple functions pretending to be one.
3. **Combinatorial complexity** — 2^7 = 128 possible combinations of behavior

Solutions:
- Replace boolean flags with enums/value objects
- Use a notification config dataclass
- Or better: use a builder/fluent pattern or just separate the concerns
</think>

The call site says it all: `True, True, False, True, True, True, False` — completely unreadable. This has two problems: **boolean blindness** and **flag-driven dispatch**.

## The Fix: Replace Booleans with Value Objects

```python
from enum import Flag, auto
from dataclasses import dataclass

class Channel(Flag):
    EMAIL = auto()
    SMS = auto()
    PUSH = auto()

class Priority(Enum):
    NORMAL = "normal"
    URGENT = "urgent"

@dataclass
class NotificationOptions:
    channels: Channel = Channel.PUSH
    priority: Priority = Priority.NORMAL
    include_unsubscribe: bool = True
    retry_on_failure: bool = True
    track_analytics: bool = True

def send_notification(user, message: str, options: NotificationOptions = None):
    options = options or NotificationOptions()

    if options.priority == Priority.URGENT:
        message = f'URGENT: {message}'

    for channel in Channel:
        if channel in options.channels:
            _send_to_channel(user, message, channel, options)

def _send_to_channel(user, message, channel, options):
    try:
        match channel:
            case Channel.EMAIL:
                body = message
                if options.include_unsubscribe:
                    body += '\n\nUnsubscribe: ...'
                mailer.send(user.email, body)
            case Channel.SMS:
                sms_gateway.send(user.phone, message[:160])
            case Channel.PUSH:
                push_service.send(user.device_id, message)
    except SendError:
        if options.retry_on_failure:
            queue_retry(channel, user, message)
```

Call sites become self-documenting:
```python
# Before: what does True, True, False, True, True, True, False mean??
send_notification(user, msg, True, True, False, True, True, True, False)

# After: crystal clear
send_notification(user, msg, NotificationOptions(
    channels=Channel.EMAIL | Channel.PUSH,
    priority=Priority.URGENT,
    track_analytics=False,
))
```

**Rules for booleans in APIs**:
- 0-1 booleans: probably fine
- 2-3 booleans: use a config object
- 4+ booleans: you have a design problem — the function is doing too many things'''
    ),
    (
        "thinking/review-speculative-generality",
        "I'm reviewing a PR from a senior dev. The feature request was 'add CSV export for the users table'. Here's what they wrote:\n\n```python\nclass ExportEngine:\n    def __init__(self, strategy: ExportStrategy, filters: FilterChain = None,\n                 transformers: list[DataTransformer] = None,\n                 post_processors: list[PostProcessor] = None):\n        self.strategy = strategy\n        self.filters = filters or FilterChain()\n        self.transformers = transformers or []\n        self.post_processors = post_processors or []\n    \n    def export(self, queryset, options: ExportOptions = None):\n        options = options or ExportOptions()\n        data = self.filters.apply(queryset)\n        for transformer in self.transformers:\n            data = transformer.transform(data)\n        output = self.strategy.write(data, options)\n        for pp in self.post_processors:\n            output = pp.process(output)\n        return output\n\nclass ExportStrategy(ABC):\n    @abstractmethod\n    def write(self, data, options: ExportOptions) -> bytes: ...\n\nclass CsvStrategy(ExportStrategy):\n    def write(self, data, options): ...\n\nclass JsonStrategy(ExportStrategy):\n    def write(self, data, options): ...\n\nclass XmlStrategy(ExportStrategy):\n    def write(self, data, options): ...\n\nclass ExcelStrategy(ExportStrategy):\n    def write(self, data, options): ...\n\nclass FilterChain: ...\nclass DataTransformer(ABC): ...\nclass PostProcessor(ABC): ...\nclass ExportOptions: ...  # 20 configurable fields\n\n# The actual usage in the codebase:\ndef export_users_csv(request):\n    engine = ExportEngine(CsvStrategy())\n    return engine.export(User.objects.all())\n```\n\nIs this over-engineered?",
        r'''<think>
Classic **Speculative Generality** / YAGNI violation. The request was "add CSV export for users table." The developer built a full export framework with:

- Abstract strategy pattern (4 strategies, only 1 used)
- Filter chains (unused)
- Data transformers (unused)
- Post-processors (unused)
- ExportOptions with 20 configurable fields (unused)

The actual usage is `ExportEngine(CsvStrategy()).export(User.objects.all())` — all the abstractions are unnecessary overhead.
</think>

Yes, this is textbook **Speculative Generality** (YAGNI violation). The request was "CSV export for users." The delivery was an enterprise export framework.

## What Was Needed

```python
def export_users_csv(request):
    users = User.objects.all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['id', 'name', 'email', 'created_at'])
    for user in users:
        writer.writerow([user.id, user.name, user.email, user.created_at])
    return HttpResponse(output.getvalue(), content_type='text/csv')
```

**15 lines. Done.**

## What Was Delivered

- `ExportEngine` with filter chains, transformers, post-processors
- 4 export strategies (only CSV is used)
- `ExportOptions` with 20 fields (none configured)
- `FilterChain`, `DataTransformer`, `PostProcessor` ABCs (no implementations)
- ~200 lines of framework code wrapping 15 lines of actual logic

## The Costs of Over-Engineering

1. **Harder to understand** — new devs must learn the framework to add a column
2. **Harder to debug** — data flows through 4 abstraction layers
3. **Harder to change** — ironically, all this "flexibility" makes real changes harder because you have to work within the framework's assumptions
4. **Maintenance burden** — unused code still needs to compile, pass tests, and be understood

## The Right Approach

Write the simple version now. If the PM later asks for JSON export, refactor then — you'll know the actual requirements instead of guessing. The cost of refactoring 15 lines into a strategy pattern later is far less than maintaining a premature framework.

**YAGNI**: You Aren't Gonna Need It. Build for today's requirements. Tomorrow's abstractions should be driven by tomorrow's actual needs.'''
    ),
    (
        "thinking/review-missing-encapsulation-collections",
        "We keep having bugs where order items get into weird states. Here's our code:\n\n```python\nclass Order:\n    def __init__(self):\n        self.items: list[OrderItem] = []\n        self.status = 'draft'\n\n# Throughout the codebase:\norder.items.append(OrderItem(product, qty))       # View layer\norder.items.remove(item)                            # API handler\norder.items[0].quantity = 0                          # Background job\norder.items.clear()                                  # Test cleanup\norder.items = other_order.items                      # Copy operation\ndel order.items[2]                                   # Admin panel\norder.items.sort(key=lambda x: x.product.name)       # Display logic\n```\n\nRecent bugs:\n- An order had items with quantity 0\n- An order was shipped with 0 items (items were cleared after confirmation)\n- Two orders shared the same items list (mutation affected both)",
        r'''<think>
Exposed collection — the internal list is fully exposed and mutated from everywhere. No invariants are enforced.

Fix: encapsulate the collection behind methods that enforce business rules.
</think>

The `items` list is fully exposed — anyone can mutate it however they want, bypassing all business rules. This is **missing collection encapsulation**.

## The Fix: Hide the Collection, Expose Operations

```python
class Order:
    def __init__(self):
        self._items: list[OrderItem] = []
        self._status = 'draft'

    @property
    def items(self) -> tuple[OrderItem, ...]:
        return tuple(self._items)  # Read-only view

    def add_item(self, product, quantity: int):
        if self._status != 'draft':
            raise InvalidOperation("Cannot modify a non-draft order")
        if quantity < 1:
            raise ValueError("Quantity must be at least 1")

        # Merge if product already exists
        for item in self._items:
            if item.product.id == product.id:
                item._quantity += quantity
                return
        self._items.append(OrderItem(product, quantity))

    def remove_item(self, product_id: str):
        if self._status != 'draft':
            raise InvalidOperation("Cannot modify a non-draft order")
        self._items = [i for i in self._items if i.product.id != product_id]

    def update_quantity(self, product_id: str, quantity: int):
        if self._status != 'draft':
            raise InvalidOperation("Cannot modify a non-draft order")
        if quantity < 1:
            raise ValueError("Quantity must be at least 1")
        for item in self._items:
            if item.product.id == product_id:
                item._quantity = quantity
                return
        raise ItemNotFound(product_id)

    def confirm(self):
        if not self._items:
            raise InvalidOperation("Cannot confirm empty order")
        self._status = 'confirmed'
```

Every bug is now prevented:
| Bug | Prevention |
|-----|-----------|
| Quantity 0 | `add_item` and `update_quantity` reject quantity < 1 |
| Shipped with 0 items | `confirm()` requires items; modification blocked after draft |
| Shared items list | `items` returns a tuple copy, `_items` is private |

**Rule**: Never expose a mutable collection as a public attribute. Expose operations that enforce invariants.'''
    ),
    (
        "thinking/review-primitive-obsession-advanced",
        "We keep having bugs with our money handling:\n\n```python\ndef transfer(from_account, to_account, amount: float, currency: str):\n    if amount <= 0:\n        raise ValueError('Invalid amount')\n    \n    if from_account.currency != currency:\n        rate = get_exchange_rate(from_account.currency, currency)\n        debit_amount = amount * rate\n    else:\n        debit_amount = amount\n    \n    if to_account.currency != currency:\n        rate = get_exchange_rate(currency, to_account.currency)\n        credit_amount = amount * rate\n    else:\n        credit_amount = amount\n    \n    from_account.balance -= debit_amount\n    to_account.balance += credit_amount\n\n# Bugs we've had:\n# 1. transfer(acc_a, acc_b, 10.50, 'USD')  -- 10.50 became 10.4999999999\n# 2. transfer(acc_a, acc_b, 100, 'usd')    -- currency comparison failed (case)\n# 3. transfer(acc_a, acc_b, 100, 'USDD')   -- typo not caught\n# 4. Mixed up which rate to apply -- debited wrong amount\n```",
        r'''<think>
Primitive obsession with money — using float for amounts and str for currencies. This causes:
1. Floating point precision errors
2. Case sensitivity bugs
3. No validation of currency codes
4. Easy to mix up amount/currency pairs

Fix: create Money and Currency value objects.
</think>

Using `float` for money and `str` for currency is **primitive obsession** — the root cause of all four bugs.

## The Fix: Money Value Object

```python
from decimal import Decimal, ROUND_HALF_UP
from enum import Enum

class Currency(Enum):
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    # ... all supported currencies

    @classmethod
    def parse(cls, value: str) -> 'Currency':
        try:
            return cls[value.upper()]
        except KeyError:
            raise ValueError(f"Unknown currency: {value}")

class Money:
    __slots__ = ('amount', 'currency')

    def __init__(self, amount: Decimal | str | int, currency: Currency):
        if isinstance(amount, float):
            raise TypeError("Use Decimal or str, not float")
        self.amount = Decimal(str(amount)).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP
        )
        self.currency = currency
        if self.amount < 0:
            raise ValueError("Money cannot be negative")

    def __add__(self, other: 'Money') -> 'Money':
        self._assert_same_currency(other)
        return Money(self.amount + other.amount, self.currency)

    def __sub__(self, other: 'Money') -> 'Money':
        self._assert_same_currency(other)
        return Money(self.amount - other.amount, self.currency)

    def convert_to(self, target: Currency, rate: Decimal) -> 'Money':
        return Money(self.amount * rate, target)

    def _assert_same_currency(self, other):
        if self.currency != other.currency:
            raise CurrencyMismatch(self.currency, other.currency)

    def __repr__(self):
        return f"{self.currency.value} {self.amount}"

# Now transfer is safe:
def transfer(from_account, to_account, amount: Money):
    debit = amount.convert_to(from_account.currency, get_rate(...))
    credit = amount.convert_to(to_account.currency, get_rate(...))
    from_account.debit(debit)   # Type-safe: only accepts Money
    to_account.credit(credit)
```

Every bug eliminated:
| Bug | Fix |
|-----|-----|
| `10.4999999` | `Decimal` with explicit rounding — no floats allowed |
| `'usd'` case mismatch | `Currency` enum — case handled in `parse()` |
| `'USDD'` typo | Enum rejects unknown values immediately |
| Wrong rate applied | `Money.convert_to()` encapsulates conversion correctly |

**Whenever two primitives always travel together (amount + currency, lat + lng, start + end), they're a value object waiting to be born.**'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
