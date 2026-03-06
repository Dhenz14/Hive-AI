"""Phase 3F: Metacognition — Code Quality Judgment (Part 4)

Scenario 5: Rate code testability with dependency analysis.
Scenario 6: Rate code maintainability (what changes are hard?).
"""

PAIRS = [
    (
        "thinking/meta-quality-testability-tightly-coupled",
        r'''Rate the testability of this code (1-10):

```python
class OrderProcessor:
    def process(self, order_data):
        # Validate
        if not order_data.get('email'):
            raise ValueError("Email required")

        # Check inventory
        conn = psycopg2.connect("postgresql://prod:pass@db.internal/shop")
        cursor = conn.cursor()
        cursor.execute("SELECT stock FROM products WHERE id = %s", (order_data['product_id'],))
        stock = cursor.fetchone()[0]
        if stock < order_data['quantity']:
            raise ValueError("Out of stock")

        # Charge payment
        stripe.api_key = "sk_live_actual_key"
        charge = stripe.Charge.create(
            amount=order_data['total'],
            currency='usd',
            source=order_data['payment_token']
        )

        # Send confirmation
        smtp = smtplib.SMTP('smtp.gmail.com', 587)
        smtp.starttls()
        smtp.login('shop@gmail.com', 'actual_password')
        smtp.send_message(create_email(order_data['email'], charge.id))

        conn.close()
        return charge.id
```''',
        r'''<think>
Let me analyze testability:

**Hard dependencies (can't test without real services):**
1. `psycopg2.connect()` — hardcoded production database connection string
2. `stripe.Charge.create()` — hardcoded live API key, would charge real money
3. `smtplib.SMTP` — hardcoded Gmail SMTP, would send real emails

**Coupling assessment:**
- Database: Direct connection, hardcoded credentials. Can't test without PostgreSQL.
- Payment: Global `stripe.api_key` mutation. Would charge real cards.
- Email: Direct SMTP connection. Would send real emails.

**Side effects in the function:**
- Reads from production database
- Charges real money
- Sends real emails
- Mutates global state (`stripe.api_key`)

**To test this function, you would need:**
- A running PostgreSQL database with the right schema
- A Stripe test key (but the code hardcodes a live key)
- An SMTP server (or mock the entire smtplib)
- To monkey-patch 3+ modules

**No interfaces/abstractions:** There's no way to inject a fake database, payment processor, or email service. Everything is hardcoded.

Score: 1/10. This is essentially untestable without mocking everything, and the hardcoded credentials make it dangerous to even try.
</think>

**Testability: 1/10 — Essentially untestable without dangerous side effects.**

**Problems:**
| Dependency | Issue | Test impact |
|-----------|-------|-------------|
| Database | Hardcoded prod connection string | Would hit production DB |
| Stripe | Hardcoded live API key | Would charge real money |
| Email | Hardcoded SMTP credentials | Would send real emails |

**Running this test would literally charge customers and email them.**

**Fixed — dependency injection:**
```python
class OrderProcessor:
    def __init__(self, db, payment_gateway, email_service):
        self.db = db
        self.payment = payment_gateway
        self.email = email_service

    def process(self, order_data):
        if not order_data.get('email'):
            raise ValueError("Email required")

        stock = self.db.get_stock(order_data['product_id'])
        if stock < order_data['quantity']:
            raise ValueError("Out of stock")

        charge_id = self.payment.charge(
            amount=order_data['total'],
            token=order_data['payment_token']
        )

        self.email.send_confirmation(order_data['email'], charge_id)
        return charge_id
```

**Now testable:**
```python
def test_process_out_of_stock():
    db = FakeDB(stock=0)
    processor = OrderProcessor(db, FakePayment(), FakeEmail())
    with pytest.raises(ValueError, match="Out of stock"):
        processor.process({"email": "a@b.com", "product_id": 1, "quantity": 5, "total": 100})

    assert db.charge_count == 0  # No payment charged
```

No real database, no real charges, no real emails. Fast, isolated, safe.'''
    ),
    (
        "thinking/meta-quality-testability-pure-functions",
        r'''Rate the testability of this code (1-10):

```python
def calculate_discount(subtotal: Decimal, coupon_code: str | None, is_member: bool) -> Decimal:
    discount = Decimal("0")

    # Member discount
    if is_member:
        discount += subtotal * Decimal("0.10")

    # Coupon discount
    if coupon_code == "SAVE20":
        discount += subtotal * Decimal("0.20")
    elif coupon_code == "FLAT10":
        discount += Decimal("10.00")

    # Cap discount at 50% of subtotal
    max_discount = subtotal * Decimal("0.50")
    return min(discount, max_discount)
```''',
        r'''<think>
Let me analyze testability:

**Dependencies:** None. Pure function — takes inputs, returns output. No database, no API calls, no file system, no global state.

**Side effects:** None. Doesn't modify any external state.

**Deterministic:** Yes. Same inputs always produce the same output. No randomness, no time-dependence.

**Testable properties:**
- Member discount: 10%
- SAVE20 coupon: 20%
- FLAT10 coupon: $10 flat
- Combined discounts (member + coupon)
- Discount cap at 50%
- No coupon, no membership
- Edge cases: zero subtotal, negative subtotal

**Writing tests is trivial:**
```python
assert calculate_discount(Decimal("100"), None, False) == Decimal("0")
assert calculate_discount(Decimal("100"), None, True) == Decimal("10")
```

Score: 10/10. This is the ideal function for testing — pure, no side effects, no dependencies, deterministic.
</think>

**Testability: 10/10 — Pure function, trivially testable.**

**Why it's perfect for testing:**
- ✅ No dependencies (no DB, no API, no file system)
- ✅ No side effects (doesn't modify anything)
- ✅ Deterministic (same inputs → same output)
- ✅ Clear inputs and output (all behavior is parameter-driven)

**Tests write themselves:**
```python
def test_no_discount():
    assert calculate_discount(Decimal("100"), None, False) == Decimal("0")

def test_member_discount():
    assert calculate_discount(Decimal("100"), None, True) == Decimal("10")

def test_coupon_percent():
    assert calculate_discount(Decimal("100"), "SAVE20", False) == Decimal("20")

def test_coupon_flat():
    assert calculate_discount(Decimal("100"), "FLAT10", False) == Decimal("10")

def test_combined_discount():
    # Member (10%) + SAVE20 (20%) = 30%
    assert calculate_discount(Decimal("100"), "SAVE20", True) == Decimal("30")

def test_discount_cap():
    # Member (10%) + SAVE20 (20%) = 30%, but on $20 that's $6 — under 50% cap
    # On $10: member $1 + SAVE20 $2 = $3 — under $5 cap
    # Need to test when cap kicks in:
    # $100 with member + SAVE20 = $30 (30%, under 50% cap)
    # To exceed cap: need > 50% total discount
    assert calculate_discount(Decimal("10"), "FLAT10", True) == Decimal("5")  # Capped at 50%

def test_zero_subtotal():
    assert calculate_discount(Decimal("0"), "SAVE20", True) == Decimal("0")
```

**No mocks, no setup, no teardown.** Each test is one line. This is what testable code looks like — push logic into pure functions whenever possible.'''
    ),
    (
        "thinking/meta-quality-testability-global-state",
        r'''Rate the testability of this code (1-10):

```python
# config.py
settings = {"rate_limit": 100, "cache_ttl": 300}

# rate_limiter.py
import time
from config import settings

_request_counts = {}

def check_rate_limit(user_id):
    now = time.time()
    if user_id not in _request_counts:
        _request_counts[user_id] = []

    # Clean old entries
    _request_counts[user_id] = [t for t in _request_counts[user_id] if now - t < 60]

    if len(_request_counts[user_id]) >= settings["rate_limit"]:
        return False

    _request_counts[user_id].append(now)
    return True
```''',
        r'''<think>
Let me analyze testability:

**Dependencies:**
1. `time.time()` — non-deterministic, changes every call
2. `settings` — imported global, hard to change per test
3. `_request_counts` — module-level mutable state that persists between tests

**Issues:**
1. **Time-dependent:** Tests using real time are slow (need to wait 60 seconds for window to reset) or flaky (timing-sensitive assertions).
2. **Global mutable state:** `_request_counts` persists between tests. Test A's requests affect Test B's rate limit. Tests must clean up or they interfere with each other.
3. **Module-level config import:** Can't easily test with different rate limits without monkey-patching `settings`.
4. **No reset mechanism:** No way to clear `_request_counts` for test isolation.

**To test properly, you'd need to:**
- Mock `time.time()` for deterministic behavior
- Clear `_request_counts` between tests
- Possibly patch `settings` for different rate limits

Score: 3/10. The core logic is simple but the global state and time dependency make tests fragile and order-dependent.
</think>

**Testability: 3/10**

**Three testability problems:**

| Issue | Impact on tests |
|-------|----------------|
| `time.time()` | Non-deterministic, tests are slow or flaky |
| `_request_counts` (global) | State leaks between tests |
| `settings` (imported global) | Can't easily vary rate limits per test |

**Test isolation nightmare:**
```python
def test_allows_first_request():
    assert check_rate_limit("user1") == True

def test_blocks_over_limit():
    # PROBLEM: _request_counts still has user1 from previous test!
    # This test depends on the previous test's state
```

**Fixed — injectable dependencies:**
```python
class RateLimiter:
    def __init__(self, max_requests: int = 100, window_seconds: int = 60,
                 clock=time.time):
        self.max_requests = max_requests
        self.window = window_seconds
        self.clock = clock  # Injectable clock
        self.counts: dict[str, list[float]] = {}

    def check(self, user_id: str) -> bool:
        now = self.clock()
        history = self.counts.get(user_id, [])
        history = [t for t in history if now - t < self.window]

        if len(history) >= self.max_requests:
            return False

        history.append(now)
        self.counts[user_id] = history
        return True
```

**Now tests are isolated and fast:**
```python
def test_blocks_over_limit():
    fake_time = 1000.0
    limiter = RateLimiter(max_requests=2, clock=lambda: fake_time)

    assert limiter.check("user1") == True
    assert limiter.check("user1") == True
    assert limiter.check("user1") == False  # Over limit

def test_resets_after_window():
    times = iter([1000.0, 1000.1, 1061.0])  # Third call after window
    limiter = RateLimiter(max_requests=2, clock=lambda: next(times))

    assert limiter.check("user1") == True
    assert limiter.check("user1") == True
    assert limiter.check("user1") == True  # Window reset
```

No mocks, no global state, no waiting.'''
    ),
    (
        "thinking/meta-quality-maintainability-rigid-switch",
        r'''Rate the maintainability of this code — what changes would be hard? (1-10):

```python
def calculate_price(product_type, base_price, quantity):
    if product_type == "physical":
        shipping = 5.99 if quantity == 1 else 5.99 + (quantity - 1) * 2.99
        tax = base_price * quantity * 0.08
        return base_price * quantity + shipping + tax
    elif product_type == "digital":
        tax = base_price * quantity * 0.05
        return base_price * quantity + tax
    elif product_type == "subscription":
        discount = 0.15 if quantity >= 12 else 0.0
        price = base_price * quantity * (1 - discount)
        return price
    elif product_type == "bundle":
        bundle_discount = 0.20
        price = base_price * quantity * (1 - bundle_discount)
        shipping = 5.99
        tax = price * 0.08
        return price + shipping + tax
    else:
        raise ValueError(f"Unknown product type: {product_type}")
```''',
        r'''<think>
Let me evaluate what changes would be hard:

1. **Adding a new product type:** Moderate — need to add another elif branch. This function grows linearly with product types. At 10 types, it's 100+ lines.

2. **Changing tax calculation:** Hard — tax logic is duplicated across branches (0.08 for physical, 0.05 for digital, 0.08 for bundle). Changing tax rules means updating multiple branches and hoping you don't miss one.

3. **Adding a new pricing dimension (e.g., member discount):** Hard — need to modify every branch. If members get 10% off, you'd add the same logic to all 4 branches.

4. **Testing:** Moderate — the function is pure, but every branch needs tests, and branches share implicit patterns that might diverge.

5. **Regional pricing (different tax rates):** Very hard — currently hardcoded. Would need to modify every branch.

**Code smells:**
- String-typed dispatch (`product_type == "physical"`) instead of polymorphism
- Duplicated tax/shipping logic across branches
- Magic numbers (0.08, 0.05, 5.99, 2.99, 0.15, 0.20)
- No separation of pricing components (shipping, tax, discount are mixed together)

Score: 3/10 for maintainability. Adding one product type is fine, but cross-cutting changes (tax rules, new pricing dimension) require touching every branch.
</think>

**Maintainability: 3/10**

**Easy changes:**
- Adding one new product type (add elif branch)

**Hard changes:**
| Change | Difficulty | Why |
|--------|-----------|-----|
| New tax rules | Hard | Tax logic duplicated in 3 branches |
| Regional pricing | Very hard | Tax rates hardcoded in each branch |
| Member discounts | Hard | Must modify all 4 branches |
| New pricing dimension | Hard | Every branch needs updating |
| Audit pricing logic | Hard | Rules spread across branches |

**The problem: horizontal changes require vertical edits.** Any change that applies to ALL product types requires modifying EVERY branch.

**Improved — separate pricing components:**
```python
TAX_RATES = {
    "physical": Decimal("0.08"),
    "digital": Decimal("0.05"),
    "subscription": Decimal("0"),
    "bundle": Decimal("0.08"),
}

SHIPPING_TYPES = {"physical", "bundle"}

def calculate_price(product_type, base_price, quantity):
    if product_type not in TAX_RATES:
        raise ValueError(f"Unknown product type: {product_type}")

    subtotal = base_price * quantity
    discount = calculate_discount(product_type, quantity)
    subtotal *= (1 - discount)
    tax = subtotal * TAX_RATES[product_type]
    shipping = calculate_shipping(product_type, quantity)
    return subtotal + tax + shipping

def calculate_discount(product_type, quantity):
    if product_type == "subscription" and quantity >= 12:
        return Decimal("0.15")
    if product_type == "bundle":
        return Decimal("0.20")
    return Decimal("0")

def calculate_shipping(product_type, quantity):
    if product_type not in SHIPPING_TYPES:
        return Decimal("0")
    return Decimal("5.99") + max(0, quantity - 1) * Decimal("2.99")
```

**Now cross-cutting changes are easy:**
- Change tax? Edit `TAX_RATES` dict
- Add regional pricing? Make `TAX_RATES` a function of region
- Add member discount? One place in `calculate_discount`
- New product type? Add to dicts, optionally add discount/shipping rule'''
    ),
    (
        "thinking/meta-quality-maintainability-well-layered",
        r'''Rate the maintainability of this code — what changes would be hard? (1-10):

```python
# repository.py
class OrderRepository:
    def __init__(self, session):
        self.session = session

    def find_by_id(self, order_id: int) -> Order | None:
        return self.session.query(Order).get(order_id)

    def find_by_user(self, user_id: int) -> list[Order]:
        return self.session.query(Order).filter_by(user_id=user_id).all()

    def save(self, order: Order) -> None:
        self.session.add(order)
        self.session.flush()

# service.py
class OrderService:
    def __init__(self, order_repo: OrderRepository, payment: PaymentGateway, email: EmailService):
        self.orders = order_repo
        self.payment = payment
        self.email = email

    def place_order(self, user_id: int, items: list[dict]) -> Order:
        order = Order(user_id=user_id, items=items, status="pending")
        self.orders.save(order)
        charge = self.payment.charge(order.total, order.payment_token)
        order.status = "paid"
        order.charge_id = charge.id
        self.orders.save(order)
        self.email.send_confirmation(order)
        return order

# routes.py
@app.post("/orders")
def create_order():
    service = get_order_service()  # Factory/DI
    order = service.place_order(current_user.id, request.json["items"])
    return jsonify(order.to_dict()), 201
```''',
        r'''<think>
Let me evaluate what changes would be hard:

1. **Switch database:** Easy — only OrderRepository touches the ORM. Swap the implementation.
2. **Switch payment provider:** Easy — PaymentGateway is injected, just provide a different implementation.
3. **Add new order operations:** Easy — add methods to OrderService.
4. **Change email provider:** Easy — EmailService is injected.
5. **Add validation:** Moderate — add a validation step in place_order or a separate validator.
6. **Add new endpoints:** Easy — routes are thin, just call service methods.
7. **Test business logic:** Easy — inject fakes for repo, payment, email.

**What would be somewhat hard:**
- Adding a cross-cutting concern like audit logging (need to decide: service layer? decorator? middleware?)
- Changing the order workflow significantly (e.g., async payment) — would need restructuring place_order
- Adding real-time notifications (WebSocket) — need to decide where to integrate

**Code quality signals:**
- Clear separation: routes → service → repository
- Dependency injection throughout
- Each class has one responsibility
- Dependencies are explicit in constructors

Score: 8/10. Well-layered, testable, most changes are isolated to one layer.
</think>

**Maintainability: 8/10**

**Change difficulty assessment:**
| Change | Difficulty | Affected layer |
|--------|-----------|---------------|
| Switch database | Easy | Repository only |
| Switch payment provider | Easy | Inject different PaymentGateway |
| Switch email provider | Easy | Inject different EmailService |
| Add new endpoints | Easy | Routes + new service method |
| Add validation | Easy | Service layer |
| Test business logic | Easy | Inject fakes |
| Add audit logging | Moderate | Service layer decorator |
| Async payment flow | Moderate | Restructure service method |

**What makes this maintainable:**
1. **Clear layers**: Routes (HTTP) → Service (business logic) → Repository (data)
2. **Dependency injection**: All dependencies are constructor parameters
3. **Single responsibility**: Each class does one thing
4. **Thin routes**: HTTP handler just calls service, no business logic

**Why 8 and not 10:**
- `place_order` does 4 things sequentially (save, charge, update, email). If the workflow becomes complex (retries, rollback on payment failure, async), this method gets unwieldy.
- No explicit error handling for payment failures (what happens if charge fails after order is saved?)

**Minor improvement:**
```python
def place_order(self, user_id, items):
    order = self._create_order(user_id, items)
    try:
        charge = self._process_payment(order)
        self._confirm_order(order, charge)
    except PaymentError:
        order.status = "payment_failed"
        self.orders.save(order)
        raise
    self.email.send_confirmation(order)
    return order
```

Explicit error handling and named steps within the service method.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
