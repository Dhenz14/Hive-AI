"""Thinking-trace pairs: testing strategy decisions and test design reasoning."""

PAIRS = [
    (
        "thinking/testing-what-to-test",
        "I have a new payment processing module. What should I test and at what level? Here's the module:\n\n```python\nclass PaymentProcessor:\n    def __init__(self, gateway: PaymentGateway, db: Database, notifier: Notifier):\n        self.gateway = gateway\n        self.db = db\n        self.notifier = notifier\n\n    def process_payment(self, order_id: str, amount: Decimal, card_token: str) -> PaymentResult:\n        # Validate\n        if amount <= 0:\n            raise ValueError('Amount must be positive')\n        order = self.db.get_order(order_id)\n        if not order:\n            raise OrderNotFoundError(order_id)\n        if order.status != 'pending':\n            raise InvalidOrderStateError(order_id, order.status)\n\n        # Charge\n        try:\n            charge = self.gateway.charge(card_token, amount, currency=order.currency)\n        except GatewayDeclinedError as e:\n            self.db.update_order(order_id, status='payment_failed', error=str(e))\n            return PaymentResult(success=False, error=str(e))\n        except GatewayTimeoutError:\n            # Don't update order — might have charged, need manual review\n            self.notifier.alert_ops('Payment gateway timeout', order_id=order_id)\n            raise\n\n        # Record\n        self.db.update_order(order_id, status='paid', charge_id=charge.id)\n        self.db.insert_payment(order_id=order_id, charge_id=charge.id, amount=amount)\n\n        # Notify\n        try:\n            self.notifier.send_receipt(order.user_email, charge)\n        except NotificationError:\n            pass  # Receipt failure shouldn't fail the payment\n\n        return PaymentResult(success=True, charge_id=charge.id)\n```",
        r'''<think>
Let me analyze this module to determine the right testing strategy. I need to think about:
1. What are the critical paths that MUST work correctly?
2. What are the edge cases and error scenarios?
3. What level of testing (unit, integration, e2e) for each scenario?

**Critical path analysis:**

The happy path: validate → charge → record → notify → return success.
This involves 4 external dependencies: gateway, db (read), db (write), notifier.

**Scenarios to test:**

1. **Happy path**: Valid order, successful charge, receipt sent → PaymentResult(success=True)
2. **Validation: negative amount** → ValueError
3. **Validation: order not found** → OrderNotFoundError
4. **Validation: wrong order status** → InvalidOrderStateError
5. **Gateway declined** → order updated to 'payment_failed', return PaymentResult(success=False)
6. **Gateway timeout** → NO order update, ops alerted, exception re-raised
7. **Receipt fails** → Payment still succeeds (silent catch)
8. **Amount is exactly zero** → ValueError (boundary)
9. **Amount is Decimal edge case** → e.g., very large amount, many decimal places

**What's NOT tested by unit tests:**
- Database constraints (unique charge_id, etc.)
- Actual gateway behavior (retries, idempotency)
- Concurrent payments for the same order (race condition?)

**Testing levels:**

**Unit tests (mock all dependencies):**
- All 9 scenarios above
- Fast, isolated, test the LOGIC of PaymentProcessor
- Mock gateway, db, notifier
- These are the most important tests — they verify the business logic

**Integration tests (real DB, mock gateway):**
- Verify DB state transitions: pending → paid, pending → payment_failed
- Verify the payment record is actually inserted with correct data
- Test concurrent payments (two threads try to process same order)

**E2E tests (real everything, test gateway sandbox):**
- One or two happy path tests against the payment gateway's sandbox
- Verify the full round-trip: charge → record → receipt
- Run these in CI but not on every commit (slow, external dependency)

**What I'd skip testing:**
- The notifier.send_receipt implementation (that's the Notifier's unit tests' job)
- The exact format of the ops alert message (implementation detail)
- Database schema migrations (separate concern)

**Test design decisions:**

For the gateway timeout case — this is the most interesting one. The code intentionally does NOT update the order status because the charge might have succeeded. This is a critical business rule. The test should verify:
1. Order status is NOT changed
2. Ops is alerted
3. The GatewayTimeoutError is re-raised (caller handles it)

For the receipt failure case — the code swallows the exception. Test should verify:
1. Payment still returns success=True
2. No exception propagates
3. charge_id is correct in the result

For concurrent payments — what happens if two requests try to process the same order? The code checks `order.status != 'pending'`, but there's a TOCTOU race between the check and the gateway charge. This needs an integration test with a real DB and a SELECT FOR UPDATE or optimistic locking check.

Actually, looking at the code again, there's no locking. Two concurrent calls could both read `status = 'pending'`, both charge the card, and both update the order. That's a double-charge bug! This is a critical finding that should be noted in the test plan AND flagged as a bug.

Let me structure the tests.
</think>

Here's the complete test strategy, organized by level and priority.

### Unit Tests (mock all deps, run on every commit)

```python
import pytest
from decimal import Decimal
from unittest.mock import Mock, patch

@pytest.fixture
def processor():
    gateway = Mock(spec=PaymentGateway)
    db = Mock(spec=Database)
    notifier = Mock(spec=Notifier)
    return PaymentProcessor(gateway, db, notifier), gateway, db, notifier

@pytest.fixture
def pending_order():
    order = Mock()
    order.status = 'pending'
    order.currency = 'USD'
    order.user_email = 'user@example.com'
    return order


# --- Happy path ---

def test_successful_payment(processor, pending_order):
    proc, gateway, db, notifier = processor
    db.get_order.return_value = pending_order
    gateway.charge.return_value = Mock(id='ch_123')

    result = proc.process_payment('order_1', Decimal('99.99'), 'tok_visa')

    assert result.success is True
    assert result.charge_id == 'ch_123'
    gateway.charge.assert_called_once_with('tok_visa', Decimal('99.99'), currency='USD')
    db.update_order.assert_called_once_with('order_1', status='paid', charge_id='ch_123')
    db.insert_payment.assert_called_once_with(
        order_id='order_1', charge_id='ch_123', amount=Decimal('99.99')
    )
    notifier.send_receipt.assert_called_once()


# --- Validation ---

def test_rejects_zero_amount(processor):
    proc, *_ = processor
    with pytest.raises(ValueError, match='positive'):
        proc.process_payment('order_1', Decimal('0'), 'tok_visa')

def test_rejects_negative_amount(processor):
    proc, *_ = processor
    with pytest.raises(ValueError, match='positive'):
        proc.process_payment('order_1', Decimal('-10'), 'tok_visa')

def test_rejects_nonexistent_order(processor):
    proc, _, db, _ = processor
    db.get_order.return_value = None
    with pytest.raises(OrderNotFoundError):
        proc.process_payment('bad_id', Decimal('10'), 'tok_visa')

def test_rejects_non_pending_order(processor, pending_order):
    proc, _, db, _ = processor
    pending_order.status = 'shipped'
    db.get_order.return_value = pending_order
    with pytest.raises(InvalidOrderStateError):
        proc.process_payment('order_1', Decimal('10'), 'tok_visa')


# --- Gateway failure modes ---

def test_declined_card_updates_order_and_returns_failure(processor, pending_order):
    proc, gateway, db, _ = processor
    db.get_order.return_value = pending_order
    gateway.charge.side_effect = GatewayDeclinedError('insufficient funds')

    result = proc.process_payment('order_1', Decimal('10'), 'tok_declined')

    assert result.success is False
    assert 'insufficient funds' in result.error
    db.update_order.assert_called_once_with(
        'order_1', status='payment_failed', error='insufficient funds'
    )
    # Verify NO payment record was created
    db.insert_payment.assert_not_called()

def test_gateway_timeout_does_not_update_order(processor, pending_order):
    """Critical: timeout means charge may have succeeded. Don't mark as failed."""
    proc, gateway, db, notifier = processor
    db.get_order.return_value = pending_order
    gateway.charge.side_effect = GatewayTimeoutError()

    with pytest.raises(GatewayTimeoutError):
        proc.process_payment('order_1', Decimal('10'), 'tok_visa')

    # Order status must NOT be changed
    db.update_order.assert_not_called()
    # Ops must be alerted for manual review
    notifier.alert_ops.assert_called_once()


# --- Notification failure ---

def test_receipt_failure_does_not_fail_payment(processor, pending_order):
    proc, gateway, db, notifier = processor
    db.get_order.return_value = pending_order
    gateway.charge.return_value = Mock(id='ch_123')
    notifier.send_receipt.side_effect = NotificationError('email down')

    result = proc.process_payment('order_1', Decimal('10'), 'tok_visa')

    assert result.success is True  # Payment succeeded despite notification failure
    assert result.charge_id == 'ch_123'
```

### Integration Tests (real DB, mock gateway)

```python
@pytest.mark.integration
async def test_payment_persists_correctly(real_db):
    """Verify actual DB state after payment."""
    # Setup: create a real pending order in the DB
    order_id = await real_db.create_order(user_id=1, amount=Decimal('50'), status='pending')

    gateway = Mock(spec=PaymentGateway)
    gateway.charge.return_value = Mock(id='ch_real_123')
    proc = PaymentProcessor(gateway, real_db, Mock())

    proc.process_payment(order_id, Decimal('50'), 'tok_visa')

    # Verify DB state
    order = await real_db.get_order(order_id)
    assert order.status == 'paid'
    assert order.charge_id == 'ch_real_123'

    payment = await real_db.get_payment_by_order(order_id)
    assert payment.amount == Decimal('50')


@pytest.mark.integration
async def test_concurrent_payments_prevented(real_db):
    """BUG ALERT: Two concurrent payments could double-charge.
    This test documents the race condition and verifies the fix."""
    order_id = await real_db.create_order(user_id=1, amount=Decimal('50'), status='pending')

    gateway = Mock(spec=PaymentGateway)
    gateway.charge.return_value = Mock(id='ch_123')

    proc = PaymentProcessor(gateway, real_db, Mock())

    # Simulate concurrent calls
    import asyncio
    results = await asyncio.gather(
        asyncio.to_thread(proc.process_payment, order_id, Decimal('50'), 'tok_1'),
        asyncio.to_thread(proc.process_payment, order_id, Decimal('50'), 'tok_2'),
        return_exceptions=True,
    )

    # Exactly one should succeed, one should raise InvalidOrderStateError
    successes = [r for r in results if isinstance(r, PaymentResult) and r.success]
    errors = [r for r in results if isinstance(r, InvalidOrderStateError)]
    assert len(successes) == 1, f"Double charge! Both payments succeeded: {results}"
    assert gateway.charge.call_count == 1, "Gateway was charged twice"
```

### Critical bug found

The code has a **TOCTOU race condition**. Two concurrent requests can both read `status = 'pending'`, both charge the card, both succeed. This is a **double-charge bug**.

Fix: use `SELECT ... FOR UPDATE` or optimistic locking:

```python
# In process_payment, replace:
order = self.db.get_order(order_id)

# With:
order = self.db.get_order_for_update(order_id)  # SELECT ... FOR UPDATE
```

### Test priority matrix

| Test | Level | Priority | Why |
|------|-------|----------|-----|
| Happy path | Unit | P0 | Core business logic |
| Gateway timeout (no status change) | Unit | P0 | Prevents false payment_failed on ambiguous state |
| Declined card | Unit | P0 | Customer-facing error handling |
| Concurrent payment race | Integration | P0 | Prevents double-charging real money |
| Receipt failure isolation | Unit | P1 | Verifies payment isn't coupled to email |
| Validation (amount, order state) | Unit | P1 | Input boundary checks |
| DB persistence correctness | Integration | P1 | Verifies data integrity |
| E2E with gateway sandbox | E2E | P2 | Full round-trip, run weekly |'''
    ),
    (
        "thinking/testing-mock-vs-real",
        "When should I mock dependencies vs use the real thing in tests? My team keeps arguing about it.",
        r'''<think>
This is one of the most debated topics in software testing. Let me organize my thinking around concrete principles rather than ideology.

**The fundamental tradeoff:**
- Mocks: fast, isolated, test YOUR code's logic. But they can't catch integration bugs (wrong query, wrong API call format, behavior mismatch between mock and real).
- Real dependencies: slower, more complex setup, but catch real bugs. However, they make tests flaky (network issues, DB state, external service downtime).

**When to mock (test the logic, not the integration):**

1. External services you don't control: payment gateways, email APIs, third-party APIs
   - You can't control their state, and you can't make them fail on demand
   - Mock to test YOUR error handling logic
   - Test the actual integration separately (integration/e2e tests)

2. Slow dependencies: anything adding >10ms per test
   - Network calls, file I/O, complex computations
   - If your test suite takes 30 minutes, devs stop running it

3. Non-deterministic behavior: time, randomness, UUIDs
   - `datetime.now()`, `random.choice()`, `uuid4()`
   - Mock to make tests deterministic and reproducible

4. Error conditions that are hard to reproduce: disk full, network timeout, OOM
   - Mock the dependency to return specific errors
   - Can't reliably trigger "disk full" in a test

**When to use real dependencies (test the integration):**

1. Database: use a real DB (SQLite for unit, PostgreSQL in Docker for integration)
   - ORM queries are complex — a mock that returns the right data doesn't verify the SQL is correct
   - Migrations, constraints, indexes — all invisible to mocks
   - SQLite for fast tests, real PostgreSQL in CI

2. File system: use a tmpdir
   - `pytest.tmp_path` gives you a real directory per test
   - Faster to use a real FS than mock open/read/write chains

3. Your own code: never mock the code under test
   - If class A depends on class B and both are your code, test A with real B
   - Mock only the outermost boundary (DB, HTTP, etc.)

4. Serialization: JSON, protobuf, msgpack
   - A mock that returns pre-parsed data won't catch serialization bugs

**The key principle: mock at the boundary, not at the seam.**

Bad: mock every class/method call between your components
Good: mock at the infrastructure boundary (HTTP, DB, filesystem, message queue)

Example:
```
Controller → Service → Repository → Database
                                     ↑ mock here
         don't mock these ↑
```

If you mock the Service in the Controller test, you're not testing that the Controller calls the Service correctly. If the Service's API changes, your Controller test still passes (green) but the real system is broken.

**The Detroit vs London school debate:**

Detroit (classicist): only mock external boundaries, test clusters of objects together
London (mockist): mock all collaborators, test one class at a time

I lean Detroit. London-style tests break constantly during refactoring (you rename a method → 50 tests break even though behavior is unchanged) because they're coupled to implementation details.

Detroit-style tests are coupled to behavior (input → output). Refactoring internal structure doesn't break them as long as behavior is preserved.

**Practical decision framework:**

For each dependency, ask:
1. Does it cross a network? → Mock it
2. Does it touch a database? → Real for integration tests, mock for unit tests
3. Is it your own code? → Use the real thing
4. Is it slow (>10ms)? → Mock it
5. Is it non-deterministic? → Mock it
6. Is it hard to set up? → Consider a fake (in-memory implementation) over a mock
</think>

Here's a concrete decision framework your team can reference:

### The rule: mock at the infrastructure boundary

```
Your Code         │  Infrastructure
                  │
Controller ──→ Service ──→ Repository ──→  DB        ← mock here
                  │                        │
                  ├──→ PaymentClient ───→  Stripe API  ← mock here
                  │                        │
                  └──→ EmailSender ────→  SMTP server  ← mock here
                  │
     never mock these
```

**Mock what crosses the process boundary. Use real instances of your own code.**

### Decision table

| Dependency | Unit tests | Integration tests | Why |
|-----------|-----------|-------------------|-----|
| Your own classes | **Real** | **Real** | Mocking your own code hides interface mismatches |
| Database | **Mock or fake** | **Real (Docker)** | ORM bugs are invisible to mocks |
| External APIs | **Mock** | **Sandbox/VCR** | Can't control external state |
| File system | **Real (tmpdir)** | **Real** | Faster than mocking open/read/write chains |
| Time/randomness | **Mock** | **Mock** | Must be deterministic |
| Message queues | **Mock** | **Real (Docker)** | Protocol bugs invisible to mocks |

### Bad mock vs good mock

```python
# BAD: Mocking your own code (hides bugs)
def test_controller():
    service = Mock(spec=OrderService)
    service.create_order.return_value = Order(id=1)
    controller = OrderController(service)
    # If OrderService.create_order changes signature, this test still passes!

# GOOD: Mock only the DB, use real service
def test_controller():
    db = Mock(spec=Database)
    db.insert_order.return_value = 1
    service = OrderService(db)  # Real service
    controller = OrderController(service)  # Real integration
    # If signatures change, test fails immediately
```

```python
# BAD: Over-mocking (tests implementation, not behavior)
def test_send_welcome_email():
    template = Mock()
    template.render.return_value = '<h1>Welcome</h1>'
    sender = Mock()
    service = EmailService(template, sender)
    service.send_welcome('user@test.com')
    template.render.assert_called_with('welcome.html', name='user')  # Fragile!
    sender.send.assert_called_with('user@test.com', '<h1>Welcome</h1>')

# GOOD: Test the outcome, not the steps
def test_send_welcome_email():
    sender = FakeEmailSender()  # In-memory fake, not a mock
    service = EmailService(RealTemplateEngine(), sender)
    service.send_welcome('user@test.com')
    assert len(sender.sent_emails) == 1
    assert 'Welcome' in sender.sent_emails[0].body
```

### Fakes > Mocks for complex dependencies

A **fake** is a simplified working implementation. A **mock** records calls and returns canned responses.

```python
# Fake: actually works, just simpler
class FakeDatabase:
    def __init__(self):
        self._orders = {}
        self._next_id = 1

    def insert_order(self, order):
        order.id = self._next_id
        self._orders[self._next_id] = order
        self._next_id += 1
        return order.id

    def get_order(self, order_id):
        return self._orders.get(order_id)

# Use in tests: catches real bugs (duplicate IDs, missing records)
# Mock would just return whatever you told it to — catches nothing
```

### The test that settles the argument

If you mock everything, this bug is invisible:

```python
class OrderService:
    def create_order(self, user_id, items):
        total = sum(item.price * item.qty for item in items)  # Bug: should use item.quantity
        return self.db.insert_order(user_id=user_id, total=total)
```

- Mock-heavy test: `db.insert_order.return_value = Order(total=100)` — passes, bug hidden
- Real service + fake DB: `FakeDatabase` stores the actual computed total — test checks `order.total == 29.97` — **fails, bug caught**

**Use mocks for things you can't control. Use real code (or fakes) for things you can.**'''
    ),
    (
        "thinking/testing-flaky-tests",
        "We have about 20 flaky tests in our CI pipeline that randomly fail. The team has been adding `@retry(3)` decorators. Is that the right approach? How should we actually fix flaky tests?",
        r'''<think>
Retries are a bandaid that hides the underlying problem. The tests are telling you something is wrong — either with the test design or with the system under test. Let me categorize the common causes and actual fixes.

**Why retries are harmful:**
1. They hide real bugs. If a test fails 1/10 times, there IS a real bug — a race condition, a timing dependency, or shared state. Retrying just means you need 3 concurrent failures to notice.
2. They slow down CI. 3 retries × 20 flaky tests × 30 seconds each = 30 minutes wasted per build.
3. They erode trust. Devs start ignoring test failures ("it's probably flaky, just re-run"). Real regressions slip through.

**Root cause categories for flaky tests:**

**1. Shared state between tests (most common)**
Tests pass individually, fail together. Order-dependent.
- Test A creates a user with email "test@example.com"
- Test B also creates a user with "test@example.com"
- If B runs after A, it fails (unique constraint)

Fix: Each test sets up its own isolated state. Use factories with unique values.

**2. Timing/race conditions**
Tests depend on things happening in order or within a time window.
- `time.sleep(1)` hoping an async operation completes — brittle
- Checking a queue for a message that hasn't arrived yet
- Waiting for a file to be written by a background process

Fix: Poll with timeout instead of sleep. Use explicit synchronization (events, semaphores, condition variables).

**3. External service dependencies**
Tests call real external services that are sometimes slow/down.
- Test calls a staging API that occasionally times out
- Test depends on DNS resolution that sometimes fails
- Test reads from a shared database that another CI run is also using

Fix: Mock external services. Use Docker containers for databases. Isolate test environments.

**4. Resource leaks**
Tests don't clean up after themselves.
- Open file handles, database connections, threads, server sockets
- After 50 tests, the system runs out of file descriptors
- Tests later in the suite fail but earlier ones pass

Fix: Use fixtures with proper teardown. Check for leaks with `pytest-leak-finder` or resource monitoring.

**5. Time-dependent tests**
Tests that break at midnight, on DST transitions, on month boundaries, on year boundaries.
- `assert order.created_at.date() == date.today()` — fails at 11:59:59 PM
- Tests that assume "next month" has 30 days

Fix: Mock `datetime.now()`. Use `freezegun` or `time-machine`.

**6. Floating point / ordering assumptions**
- `assert result == [1, 2, 3]` when the order isn't guaranteed (dict iteration, SQL without ORDER BY, set operations)
- `assert 0.1 + 0.2 == 0.3` (floating point)

Fix: Use `assert sorted(result) == [1, 2, 3]` or `assert set(result) == {1, 2, 3}`. Use `pytest.approx()` for floats.

**Strategy for fixing 20 flaky tests:**

1. Quarantine them: move to a separate CI job that runs but doesn't block deploys
2. Categorize: for each, determine the root cause category
3. Fix by category: usually 5-6 tests share the same root cause, so fixing the pattern fixes multiple tests
4. Track: dashboard showing flaky test count over time (should trend to zero)
</think>

Retries are the wrong approach — they hide real bugs and slow down CI. Every flaky test has a root cause that should be fixed.

### Why retries are harmful

```
Before retries: Test fails → You investigate → Find race condition → Fix it
After retries:  Test fails → Retry passes → Nobody notices → Race condition ships to prod
```

### The 6 root causes (and actual fixes)

**1. Shared state between tests (~40% of flaky tests)**

```python
# FLAKY: tests share database state
def test_create_user():
    db.insert(User(email='test@example.com'))  # Works first time
    assert db.get_user('test@example.com')

def test_duplicate_check():
    db.insert(User(email='test@example.com'))  # FAILS if test above ran first

# FIXED: unique state per test
def test_create_user(db_session):  # Fresh DB transaction, rolled back after test
    email = f'user_{uuid4().hex[:8]}@example.com'
    db_session.insert(User(email=email))
    assert db_session.get_user(email)
```

**2. Timing dependencies (~25%)**

```python
# FLAKY: sleep and pray
def test_async_processing():
    queue.publish({'order_id': 1})
    time.sleep(2)  # Sometimes 2s isn't enough
    assert db.get_order(1).status == 'processed'

# FIXED: poll with timeout
def test_async_processing():
    queue.publish({'order_id': 1})
    assert poll_until(
        lambda: db.get_order(1).status == 'processed',
        timeout=10,
        interval=0.1,
    )

def poll_until(predicate, timeout=10, interval=0.1):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(interval)
    return False
```

**3. Unordered results (~15%)**

```python
# FLAKY: assumes query order
def test_get_users():
    result = api.get('/users')
    assert result == [{'name': 'Alice'}, {'name': 'Bob'}]  # Order not guaranteed!

# FIXED: sort or use sets
def test_get_users():
    result = api.get('/users')
    names = sorted(u['name'] for u in result)
    assert names == ['Alice', 'Bob']
```

**4. Time-dependent logic (~10%)**

```python
# FLAKY: fails at midnight
def test_order_created_today():
    order = create_order()
    assert order.created_at.date() == date.today()  # Fails at 23:59:59.999

# FIXED: freeze time
from freezegun import freeze_time

@freeze_time('2026-03-05 12:00:00')
def test_order_created_today():
    order = create_order()
    assert order.created_at == datetime(2026, 3, 5, 12, 0, 0)
```

**5. Port/resource conflicts (~5%)**

```python
# FLAKY: port already in use from previous test
def test_server_starts():
    server = start_server(port=8080)  # Fails if port still bound

# FIXED: random port
def test_server_starts():
    server = start_server(port=0)  # OS assigns free port
    assert server.port > 0
```

**6. External dependencies (~5%)**

```python
# FLAKY: staging API is sometimes slow
def test_payment():
    result = stripe_client.charge(amount=100)  # Real API call in CI!

# FIXED: mock external services
def test_payment(mock_stripe):
    mock_stripe.charge.return_value = Charge(id='ch_123')
    result = payment_service.process(amount=100)
    assert result.success
```

### Action plan for your 20 flaky tests

```
Week 1: Quarantine
  ├─ Move flaky tests to separate CI job (runs, doesn't block deploy)
  ├─ Remove all @retry decorators
  └─ Log each failure with full context (timestamp, test order, env)

Week 2: Categorize
  ├─ Run flaky tests 100x: `pytest --count=100 -x tests/flaky/`
  ├─ For each failure, tag root cause: shared_state | timing | ordering | time | port | external
  └─ Usually 3-4 root causes explain all 20 failures

Week 3: Fix by pattern
  ├─ Shared state → add proper fixtures with teardown
  ├─ Timing → replace sleep() with poll_until()
  ├─ Ordering → sort results or use set comparisons
  └─ Move fixed tests back to main CI

Week 4: Prevent recurrence
  ├─ Add `pytest-randomly` to randomize test order (catches shared state early)
  ├─ Add `pytest-timeout` to fail slow tests explicitly
  └─ Track flaky test count as a team metric (should be 0)
```

### pytest plugins that help

```ini
# pytest.ini
[pytest]
addopts =
    -p randomly          # Randomize test order every run
    --timeout=30         # Kill tests that hang >30s
    --strict-markers     # Catch unmarked tests
    -x                   # Stop on first failure (faster feedback)
```'''
    ),
]
