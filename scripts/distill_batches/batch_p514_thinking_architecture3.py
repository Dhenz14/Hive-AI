"""Phase 1D: Foundation Thinking — Architecture & Design (Part 3/4)
Design patterns, dependency injection, clean architecture, error handling."""

PAIRS = [
    (
        "thinking/arch-dependency-injection-testing",
        "Our code directly instantiates dependencies, making testing impossible without hitting real services:\n\n```python\nclass OrderService:\n    def create_order(self, user_id, items):\n        # Directly creates concrete dependencies\n        payment = StripePaymentGateway()\n        inventory = WarehouseInventoryService()\n        email = SendGridEmailService()\n        \n        payment.charge(user_id, self._calculate_total(items))\n        inventory.reserve(items)\n        email.send_confirmation(user_id, items)\n```\n\nEvery test hits Stripe, the warehouse API, and SendGrid. How to fix this?",
        r'''<think>
The class creates its own dependencies (StripePaymentGateway, etc.) inside the method. This means:
1. Can't test without hitting real services
2. Can't swap implementations (e.g., different payment provider)
3. Can't mock for testing

Fix: inject dependencies through the constructor.
</think>

**Hard-coded dependencies make testing impossible.** Every test charges real credit cards and sends real emails.

## Fix: Constructor Injection

```python
from abc import ABC, abstractmethod

# Define interfaces (protocols/ABCs)
class PaymentGateway(ABC):
    @abstractmethod
    def charge(self, user_id: int, amount: float) -> str: ...

class InventoryService(ABC):
    @abstractmethod
    def reserve(self, items: list) -> bool: ...

class EmailService(ABC):
    @abstractmethod
    def send_confirmation(self, user_id: int, items: list) -> None: ...

# Service accepts dependencies through constructor
class OrderService:
    def __init__(self, payment: PaymentGateway, inventory: InventoryService,
                 email: EmailService):
        self.payment = payment
        self.inventory = inventory
        self.email = email

    def create_order(self, user_id, items):
        total = self._calculate_total(items)
        payment_id = self.payment.charge(user_id, total)
        self.inventory.reserve(items)
        self.email.send_confirmation(user_id, items)
        return payment_id

# Production
order_service = OrderService(
    payment=StripePaymentGateway(api_key=os.environ['STRIPE_KEY']),
    inventory=WarehouseInventoryService(url=os.environ['WAREHOUSE_URL']),
    email=SendGridEmailService(api_key=os.environ['SENDGRID_KEY']),
)

# Testing — no real services
class FakePayment(PaymentGateway):
    def __init__(self):
        self.charges = []
    def charge(self, user_id, amount):
        self.charges.append((user_id, amount))
        return 'fake_payment_123'

def test_create_order():
    payment = FakePayment()
    inventory = FakeInventory()
    email = FakeEmail()

    service = OrderService(payment, inventory, email)
    service.create_order(user_id=1, items=[{'id': 1, 'qty': 2}])

    assert len(payment.charges) == 1
    assert payment.charges[0] == (1, expected_total)
```

**Benefits:** testable without real services, swappable implementations, explicit dependencies.'''
    ),
    (
        "thinking/arch-repository-pattern",
        "Our Flask views directly execute SQL queries, mixing business logic with data access. When we want to switch from PostgreSQL to MongoDB, we'd have to rewrite everything:\n\n```python\n@app.route('/api/orders', methods=['POST'])\ndef create_order():\n    data = request.json\n    \n    # Business logic mixed with SQL\n    user = db.execute('SELECT * FROM users WHERE id = ?', (data['user_id'],)).fetchone()\n    if user['balance'] < data['total']:\n        return jsonify(error='Insufficient balance'), 400\n    \n    db.execute('UPDATE users SET balance = balance - ? WHERE id = ?', \n               (data['total'], data['user_id']))\n    db.execute(\n        'INSERT INTO orders (user_id, total, status) VALUES (?, ?, ?)',\n        (data['user_id'], data['total'], 'pending')\n    )\n    db.commit()\n    return jsonify(message='Order created'), 201\n```",
        r'''<think>
Business logic (balance check, order creation) is tangled with data access (SQL queries). The repository pattern separates these concerns.
</think>

**Business logic tangled with SQL.** Can't test, can't switch databases, can't reuse logic.

## Fix: Repository Pattern

```python
# repositories.py — data access only
class UserRepository:
    def __init__(self, db):
        self.db = db

    def get_by_id(self, user_id):
        row = self.db.execute(
            'SELECT * FROM users WHERE id = ?', (user_id,)
        ).fetchone()
        return User(**dict(row)) if row else None

    def update_balance(self, user_id, new_balance):
        self.db.execute(
            'UPDATE users SET balance = ? WHERE id = ?',
            (new_balance, user_id)
        )

class OrderRepository:
    def __init__(self, db):
        self.db = db

    def create(self, order):
        self.db.execute(
            'INSERT INTO orders (user_id, total, status) VALUES (?, ?, ?)',
            (order.user_id, order.total, order.status)
        )

# services.py — business logic only (no SQL)
class OrderService:
    def __init__(self, user_repo, order_repo):
        self.user_repo = user_repo
        self.order_repo = order_repo

    def create_order(self, user_id, total):
        user = self.user_repo.get_by_id(user_id)
        if not user:
            raise ValueError('User not found')
        if user.balance < total:
            raise InsufficientBalanceError(user.balance, total)

        user.balance -= total
        self.user_repo.update_balance(user.id, user.balance)

        order = Order(user_id=user_id, total=total, status='pending')
        self.order_repo.create(order)
        return order

# views.py — HTTP handling only
@app.route('/api/orders', methods=['POST'])
def create_order():
    data = request.json
    try:
        order = order_service.create_order(data['user_id'], data['total'])
        return jsonify(order.to_dict()), 201
    except InsufficientBalanceError:
        return jsonify(error='Insufficient balance'), 400
```

**Separation:** views handle HTTP, services handle business logic, repositories handle data access. Each layer is independently testable and swappable.'''
    ),
    (
        "thinking/arch-error-handling-strategy",
        "Our API returns inconsistent error responses. Some endpoints return `{\"error\": \"msg\"}`, others return `{\"message\": \"msg\"}`, some return plain text, and status codes are used inconsistently. Design a standardized error handling strategy.",
        r'''<think>
Need:
1. Consistent error response format
2. Proper HTTP status codes
3. Machine-readable error codes
4. Human-readable messages
5. Centralized error handling
</think>

## Standardized Error Response Format

```python
from flask import Flask, jsonify
from werkzeug.exceptions import HTTPException

app = Flask(__name__)

# Standard error response format
def error_response(status_code, error_code, message, details=None):
    body = {
        'error': {
            'code': error_code,
            'message': message,
        }
    }
    if details:
        body['error']['details'] = details
    return jsonify(body), status_code

# Custom exception hierarchy
class AppError(Exception):
    status_code = 500
    error_code = 'INTERNAL_ERROR'
    message = 'An unexpected error occurred'

    def __init__(self, message=None, details=None):
        self.message = message or self.__class__.message
        self.details = details

class NotFoundError(AppError):
    status_code = 404
    error_code = 'NOT_FOUND'

class ValidationError(AppError):
    status_code = 400
    error_code = 'VALIDATION_ERROR'

class AuthenticationError(AppError):
    status_code = 401
    error_code = 'AUTHENTICATION_REQUIRED'

class ForbiddenError(AppError):
    status_code = 403
    error_code = 'FORBIDDEN'

class ConflictError(AppError):
    status_code = 409
    error_code = 'CONFLICT'

class RateLimitError(AppError):
    status_code = 429
    error_code = 'RATE_LIMIT_EXCEEDED'

# Global error handler — catches ALL exceptions
@app.errorhandler(AppError)
def handle_app_error(error):
    return error_response(error.status_code, error.error_code,
                         error.message, error.details)

@app.errorhandler(HTTPException)
def handle_http_error(error):
    return error_response(error.code, error.name.upper().replace(' ', '_'),
                         error.description)

@app.errorhandler(Exception)
def handle_unexpected(error):
    app.logger.exception('Unexpected error')
    return error_response(500, 'INTERNAL_ERROR',
                         'An unexpected error occurred')

# Usage in endpoints
@app.route('/api/users/<int:user_id>')
def get_user(user_id):
    user = User.query.get(user_id)
    if not user:
        raise NotFoundError(f'User {user_id} not found')
    return jsonify(user.to_dict())

@app.route('/api/orders', methods=['POST'])
def create_order():
    data = request.json
    errors = validate_order(data)
    if errors:
        raise ValidationError('Invalid order data', details=errors)
    # ...
```

**Consistent response format:**
```json
{
    "error": {
        "code": "VALIDATION_ERROR",
        "message": "Invalid order data",
        "details": [
            {"field": "total", "message": "Must be positive"},
            {"field": "items", "message": "At least one item required"}
        ]
    }
}
```

**Error codes are machine-readable** (clients switch on `error.code`), messages are human-readable.'''
    ),
    (
        "thinking/arch-strategy-pattern-payment",
        "Our checkout code has a growing if/else chain for different payment methods, and adding new ones requires modifying the existing code:\n\n```python\ndef process_payment(method, amount, details):\n    if method == 'credit_card':\n        # 50 lines of credit card processing\n        stripe.charge(amount, details['card_token'])\n    elif method == 'paypal':\n        # 40 lines of PayPal processing\n        paypal.create_payment(amount, details['paypal_email'])\n    elif method == 'bank_transfer':\n        # 30 lines of bank transfer processing\n        bank.initiate_transfer(amount, details['routing'], details['account'])\n    elif method == 'crypto':\n        # New requirement — adding here makes this function even bigger\n        ...\n    else:\n        raise ValueError(f'Unknown payment method: {method}')\n```",
        r'''<think>
Open/Closed Principle violation. Every new payment method requires modifying this function. Strategy pattern: each payment method is a separate class implementing a common interface.
</think>

**Open/Closed Principle violation.** Every new payment method requires modifying existing code, risking bugs in working methods.

## Fix: Strategy Pattern

```python
from abc import ABC, abstractmethod

class PaymentStrategy(ABC):
    @abstractmethod
    def charge(self, amount: float, details: dict) -> str:
        """Process payment, return transaction ID."""
        ...

class CreditCardPayment(PaymentStrategy):
    def charge(self, amount, details):
        return stripe.charge(amount, details['card_token'])

class PayPalPayment(PaymentStrategy):
    def charge(self, amount, details):
        return paypal.create_payment(amount, details['paypal_email'])

class BankTransferPayment(PaymentStrategy):
    def charge(self, amount, details):
        return bank.initiate_transfer(amount, details['routing'], details['account'])

class CryptoPayment(PaymentStrategy):
    def charge(self, amount, details):
        return crypto.create_invoice(amount, details['wallet_address'])

# Registry — maps method names to strategies
PAYMENT_STRATEGIES: dict[str, PaymentStrategy] = {
    'credit_card': CreditCardPayment(),
    'paypal': PayPalPayment(),
    'bank_transfer': BankTransferPayment(),
    'crypto': CryptoPayment(),
}

def process_payment(method: str, amount: float, details: dict) -> str:
    strategy = PAYMENT_STRATEGIES.get(method)
    if not strategy:
        raise ValueError(f'Unknown payment method: {method}')
    return strategy.charge(amount, details)
```

**Adding a new payment method:** create one new class, add one line to the registry. Zero changes to existing code.'''
    ),
    (
        "thinking/arch-event-sourcing-intro",
        "Our banking system needs a complete audit trail of every balance change. The current system stores only the current balance — when discrepancies are found, there's no way to trace what happened:\n\n```python\ndef transfer(from_id, to_id, amount):\n    from_acc = Account.query.get(from_id)\n    to_acc = Account.query.get(to_id)\n    from_acc.balance -= amount\n    to_acc.balance += amount\n    db.session.commit()\n    # What happened to create this balance? No history!\n```",
        r'''<think>
Event sourcing: instead of storing current state, store the sequence of events that led to the current state. The current balance is derived by replaying all events.

Benefits:
- Complete audit trail
- Can reconstruct state at any point in time
- Can add new projections (views) retroactively
- Natural fit for banking/financial systems
</think>

## Event Sourcing: Store Events, Derive State

```python
from datetime import datetime
from decimal import Decimal

# Events are the source of truth — immutable, append-only
class AccountEvent:
    def __init__(self, account_id, event_type, amount, metadata=None):
        self.account_id = account_id
        self.event_type = event_type  # 'credited', 'debited', 'opened'
        self.amount = amount
        self.metadata = metadata or {}
        self.timestamp = datetime.utcnow()
        self.version = None  # Set by the event store

class EventStore:
    def append(self, event):
        # Append-only — events are NEVER modified or deleted
        db.execute(
            'INSERT INTO account_events '
            '(account_id, event_type, amount, metadata, timestamp, version) '
            'VALUES (?, ?, ?, ?, ?, '
            '  (SELECT COALESCE(MAX(version), 0) + 1 FROM account_events WHERE account_id = ?))',
            (event.account_id, event.event_type, str(event.amount),
             json.dumps(event.metadata), event.timestamp, event.account_id)
        )
        db.commit()

    def get_events(self, account_id, since_version=0):
        return db.execute(
            'SELECT * FROM account_events WHERE account_id = ? AND version > ? '
            'ORDER BY version',
            (account_id, since_version)
        ).fetchall()

# Derive current balance by replaying events
def get_balance(account_id):
    events = event_store.get_events(account_id)
    balance = Decimal('0')
    for event in events:
        if event['event_type'] == 'credited':
            balance += Decimal(event['amount'])
        elif event['event_type'] == 'debited':
            balance -= Decimal(event['amount'])
    return balance

# Transfer creates two events
def transfer(from_id, to_id, amount, description=''):
    amount = Decimal(str(amount))

    # Check balance
    from_balance = get_balance(from_id)
    if from_balance < amount:
        raise InsufficientFundsError()

    transfer_id = str(uuid.uuid4())

    event_store.append(AccountEvent(
        from_id, 'debited', amount,
        {'transfer_id': transfer_id, 'to': to_id, 'description': description}
    ))
    event_store.append(AccountEvent(
        to_id, 'credited', amount,
        {'transfer_id': transfer_id, 'from': from_id, 'description': description}
    ))
```

**Now you can answer:** "Why is this account at $500?"
```python
events = event_store.get_events(account_id)
for e in events:
    print(f'{e["timestamp"]} {e["event_type"]} ${e["amount"]} — {e["metadata"]}')
# 2026-01-01 opened       $0     {}
# 2026-01-05 credited   $1000    {from: payroll}
# 2026-01-10 debited     $200    {to: rent, transfer_id: abc}
# 2026-01-15 debited     $300    {to: groceries, transfer_id: def}
# Balance: $500 ✓ — complete audit trail
```'''
    ),
    (
        "thinking/arch-retry-with-backoff-design",
        "Design a generic retry mechanism with exponential backoff, jitter, and configurable retry conditions. It should work as a decorator.",
        r'''<think>
Requirements:
- Exponential backoff (1s, 2s, 4s, 8s...)
- Jitter (randomize to avoid thundering herd)
- Configurable max retries
- Configurable which exceptions to retry
- Configurable max delay
- Works as a decorator
</think>

```python
import time
import random
import functools
import logging
from typing import Type

logger = logging.getLogger(__name__)

def retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,),
):
    """Decorator for retrying functions with exponential backoff."""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        logger.error(
                            f'{func.__name__} failed after {max_retries + 1} attempts: {e}'
                        )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(base_delay * (exponential_base ** attempt), max_delay)

                    # Add jitter to prevent thundering herd
                    if jitter:
                        delay = random.uniform(0, delay)

                    logger.warning(
                        f'{func.__name__} attempt {attempt + 1} failed: {e}. '
                        f'Retrying in {delay:.1f}s'
                    )
                    time.sleep(delay)

            raise last_exception
        return wrapper
    return decorator

# Usage
@retry(max_retries=3, retryable_exceptions=(ConnectionError, TimeoutError))
def call_external_api(url):
    response = requests.get(url, timeout=5)
    response.raise_for_status()
    return response.json()

# Async version
def async_retry(max_retries=3, base_delay=1.0, max_delay=60.0,
                retryable_exceptions=(Exception,)):
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        raise
                    delay = min(base_delay * (2 ** attempt), max_delay)
                    delay = random.uniform(0, delay)
                    await asyncio.sleep(delay)
            raise last_exception
        return wrapper
    return decorator
```

**Key design decisions:**
1. **Full jitter** (`uniform(0, delay)`) — spreads retries uniformly, best for preventing thundering herd
2. **Configurable exception types** — don't retry `ValueError` (won't fix itself)
3. **Max delay cap** — exponential growth doesn't exceed 60 seconds
4. **Attempt 0 is the initial try** — `max_retries=3` means 4 total attempts'''
    ),
    (
        "thinking/arch-observer-pattern-events",
        "A user registration triggers 5 actions: send welcome email, create default settings, add to mailing list, log analytics event, and trigger onboarding workflow. The registration function is 200 lines long and growing:\n\n```python\ndef register_user(username, email, password):\n    user = User(username=username, email=email)\n    user.set_password(password)\n    db.session.add(user)\n    db.session.commit()\n    \n    # Every new requirement adds more code here\n    send_welcome_email(user)\n    create_default_settings(user)\n    add_to_mailing_list(user)\n    log_analytics('user_registered', user)\n    trigger_onboarding(user)\n    # ... more coming\n```",
        r'''<think>
The function violates Single Responsibility — registration logic mixed with email, analytics, settings, etc. Observer/event pattern: register the user, emit an event, let observers handle the rest.
</think>

**Single Responsibility violation.** Registration is coupled to 5+ side effects. Adding a 6th requires modifying the registration function.

## Fix: Event System (Observer Pattern)

```python
from collections import defaultdict
from typing import Callable

class EventBus:
    def __init__(self):
        self._handlers: dict[str, list[Callable]] = defaultdict(list)

    def on(self, event_name: str, handler: Callable):
        self._handlers[event_name].append(handler)

    def emit(self, event_name: str, **data):
        for handler in self._handlers[event_name]:
            try:
                handler(**data)
            except Exception as e:
                logger.error(f'Handler {handler.__name__} failed for {event_name}: {e}')

events = EventBus()

# Registration — clean, single responsibility
def register_user(username, email, password):
    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()

    events.emit('user_registered', user=user)
    return user

# Handlers — each in its own module, independently maintainable
@events.on('user_registered')
def handle_welcome_email(user):
    send_welcome_email(user)

@events.on('user_registered')
def handle_default_settings(user):
    create_default_settings(user)

@events.on('user_registered')
def handle_mailing_list(user):
    add_to_mailing_list(user)

@events.on('user_registered')
def handle_analytics(user):
    log_analytics('user_registered', user)

@events.on('user_registered')
def handle_onboarding(user):
    trigger_onboarding(user)
```

**Adding a new requirement:** write one new handler function. Zero changes to `register_user`.

**For production, consider making handlers async** so slow handlers (email, external APIs) don't block registration.'''
    ),
    (
        "thinking/arch-clean-architecture-layers",
        "Explain clean architecture layers with a practical example. Our team argues about where business rules, database queries, and HTTP handling should live.",
        r'''<think>
Clean architecture: dependencies point inward. Inner layers don't know about outer layers.

Layers (inside out):
1. Entities — core business objects and rules
2. Use Cases — application-specific business logic
3. Interface Adapters — controllers, presenters, gateways
4. Frameworks — web framework, database, external services
</think>

## Clean Architecture: Practical Example

```
[Frameworks & Drivers]  ← Flask, SQLAlchemy, Redis, Stripe
      ↓ depends on
[Interface Adapters]    ← Controllers, Repositories, Presenters
      ↓ depends on
[Use Cases]             ← Application business logic
      ↓ depends on
[Entities]              ← Core business rules, domain objects
```

```python
# Layer 1: Entities (innermost — no dependencies)
class Order:
    def __init__(self, user_id, items):
        self.user_id = user_id
        self.items = items
        self.total = sum(i.price * i.quantity for i in items)
        self.status = 'pending'

    def can_be_cancelled(self):
        return self.status in ('pending', 'confirmed')

    def apply_discount(self, percentage):
        if percentage > 50:
            raise ValueError('Discount cannot exceed 50%')
        self.total *= (1 - percentage / 100)

# Layer 2: Use Cases (depends on entities, NOT on frameworks)
class CreateOrderUseCase:
    def __init__(self, order_repo, payment_gateway, inventory_checker):
        # Dependencies are INTERFACES, not concrete implementations
        self.order_repo = order_repo
        self.payment_gateway = payment_gateway
        self.inventory_checker = inventory_checker

    def execute(self, user_id, items):
        order = Order(user_id, items)

        if not self.inventory_checker.all_available(items):
            raise OutOfStockError()

        payment = self.payment_gateway.charge(user_id, order.total)
        order.payment_id = payment.id
        order.status = 'confirmed'

        self.order_repo.save(order)
        return order

# Layer 3: Interface Adapters
# Repository implementation (knows about SQLAlchemy)
class SQLAlchemyOrderRepo:
    def save(self, order):
        db.session.add(OrderModel.from_entity(order))
        db.session.commit()

# Controller (knows about Flask)
class OrderController:
    def __init__(self, create_order_use_case):
        self.create_order = create_order_use_case

    def handle_create(self, request_data):
        items = [Item(**i) for i in request_data['items']]
        order = self.create_order.execute(request_data['user_id'], items)
        return {'order_id': order.id, 'total': str(order.total)}

# Layer 4: Framework wiring (outermost)
@app.route('/api/orders', methods=['POST'])
def create_order_endpoint():
    controller = OrderController(
        CreateOrderUseCase(
            order_repo=SQLAlchemyOrderRepo(),
            payment_gateway=StripeGateway(),
            inventory_checker=WarehouseChecker(),
        )
    )
    return jsonify(controller.handle_create(request.json)), 201
```

**The key rule:** dependencies point inward. Business logic (`Order`, `CreateOrderUseCase`) never imports Flask, SQLAlchemy, or Stripe. They define interfaces that outer layers implement.'''
    ),
    (
        "thinking/arch-message-queue-selection",
        "We need a message queue for our event-driven architecture. We're choosing between RabbitMQ, Kafka, and Redis Streams. Our requirements: event ordering, at-least-once delivery, 500K events/day, 5 consumer services.",
        r'''<think>
Let me compare the three for the given requirements:

500K events/day = ~6 events/sec average. Low throughput — all three can handle this easily.

**RabbitMQ:**
- Traditional message broker — push model
- Great for task queues and work distribution
- Messages are removed after consumption
- Complex routing with exchanges
- At-least-once delivery with acknowledgments
- Ordering per queue (not global)

**Kafka:**
- Distributed log — pull model
- Messages persist (configurable retention)
- Multiple consumers can read same messages (consumer groups)
- Strict ordering per partition
- At-least-once (configurable to exactly-once)
- Overkill for 500K events/day

**Redis Streams:**
- Lightweight, built into Redis
- Consumer groups, acknowledgment
- Persistence with AOF/RDB
- Good for moderate throughput
- Simplest to operate (if you already have Redis)

For 500K events/day with 5 consumers needing ordering:
- Redis Streams if you already have Redis (simplest)
- RabbitMQ if you need complex routing patterns
- Kafka is overkill for this volume
</think>

## Comparison for Your Requirements

| Feature | RabbitMQ | Kafka | Redis Streams |
|---------|----------|-------|---------------|
| 500K events/day | Easy | Massive overkill | Easy |
| Event ordering | Per-queue | Per-partition | Per-stream |
| At-least-once | Yes (ACK) | Yes (offsets) | Yes (ACK) |
| 5 consumers | Work queues or fanout | Consumer groups | Consumer groups |
| Operational complexity | Medium | High | Low (if you have Redis) |
| Message replay | No (consumed = gone) | Yes (log retention) | Yes (stream retention) |

## Recommendation: Redis Streams

For 500K events/day, you already have Redis, and the simplest operational model wins:

```python
import redis

r = redis.Redis()

# Producer
def publish_event(stream, event_type, data):
    r.xadd(stream, {
        'type': event_type,
        'data': json.dumps(data),
        'timestamp': str(time.time()),
    })

# Consumer
async def consume_events(stream, group, consumer_name):
    # Create consumer group (idempotent)
    try:
        r.xgroup_create(stream, group, id='0', mkstream=True)
    except redis.ResponseError:
        pass  # Group already exists

    while True:
        # Read new messages for this consumer
        messages = r.xreadgroup(
            group, consumer_name,
            {stream: '>'},  # '>' = only new messages
            count=10,
            block=5000,  # Wait 5s for new messages
        )

        for stream_name, entries in messages:
            for msg_id, fields in entries:
                try:
                    event = json.loads(fields[b'data'])
                    await process_event(fields[b'type'].decode(), event)
                    r.xack(stream, group, msg_id)  # Acknowledge
                except Exception as e:
                    logger.error(f'Failed to process {msg_id}: {e}')
                    # Message stays pending — will be redelivered
```

**When to use Kafka instead:** millions of events/sec, multi-datacenter replication, long retention (days/weeks), stream processing (Kafka Streams/Flink).'''
    ),
    (
        "thinking/arch-backend-for-frontend-graphql",
        "Our REST API serves 3 different clients: web app, mobile app, and partner API. Each needs different data shapes. The mobile app over-fetches (gets 20 fields, needs 5), the web app under-fetches (needs 3 calls to build one page). Should we use GraphQL?",
        r'''<think>
The symptoms match GraphQL's strengths:
- Over-fetching (mobile gets unnecessary fields) → GraphQL: clients specify fields
- Under-fetching (web needs multiple calls) → GraphQL: one query, nested data
- Different client needs → GraphQL: each client sends different queries

But GraphQL also has downsides:
- Complexity (schema design, resolvers, N+1 problems)
- Caching is harder (every query is unique)
- File uploads are awkward
- Learning curve for the team

For 3 clients, the BFF (Backend for Frontend) pattern with REST might be simpler. Or GraphQL if the team is willing to invest in it.
</think>

GraphQL solves your exact pain points, but consider the trade-offs:

## GraphQL Approach

```python
import strawberry
from strawberry.flask.views import GraphQLView

@strawberry.type
class Product:
    id: int
    name: str
    description: str
    price: float
    images: list[str]
    reviews: list['Review']
    inventory_count: int

# Mobile: gets exactly what it needs
# query { product(id: 1) { id name price images } }

# Web: gets everything in one call
# query { product(id: 1) { id name description price images reviews { text rating } inventory_count } }

# Partner: gets specific fields
# query { product(id: 1) { id name price inventory_count } }
```

## Or BFF Pattern (Simpler, REST-Based)

```python
# Mobile BFF — optimized responses
@app.route('/mobile/api/products/<int:id>')
def mobile_product(id):
    p = Product.query.get(id)
    return jsonify({
        'id': p.id, 'name': p.name, 'price': p.price,
        'image': p.images[0] if p.images else None,
    })

# Web BFF — aggregated responses
@app.route('/web/api/products/<int:id>')
def web_product(id):
    p = Product.query.options(joinedload('reviews')).get(id)
    return jsonify({
        'id': p.id, 'name': p.name, 'description': p.description,
        'price': p.price, 'images': p.images,
        'reviews': [r.to_dict() for r in p.reviews],
        'inventory': inventory_service.check(p.id),
    })
```

## Decision Matrix

| Factor | GraphQL | BFF (REST) |
|--------|---------|------------|
| Client flexibility | High (client picks fields) | Medium (server defines) |
| Caching | Hard (unique queries) | Easy (URL-based) |
| Team learning curve | High | Low |
| N+1 query risk | High (need DataLoader) | Low (server controls) |
| API evolution | Easy (add fields) | Easy (versioned endpoints) |

**Recommendation:** If your team knows GraphQL → use it. If not → BFF pattern gives 80% of the benefit with 20% of the complexity.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
