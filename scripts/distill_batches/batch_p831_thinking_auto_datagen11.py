"""Phase 4A: Self-Improvement — Training Data Generation (Part 11)

Generate and evaluate training pairs for testing strategy topics.
Each answer creates 3 graded training pairs with quality analysis.
"""

PAIRS = [
    (
        "thinking/auto-datagen-unit-testing-fundamentals",
        r'''Generate 3 high-quality training pairs that teach unit testing fundamentals and best practices. For each pair, explain why it's effective training data.''',
        r'''<think>
Unit testing is a skill most developers know they should have but struggle with:
1. What to test and what not to test
2. Writing testable code vs untestable code
3. Common testing anti-patterns

Progression: writing first tests -> structuring tests well -> testing edge cases and error paths
</think>

Here are 3 training pairs for unit testing fundamentals:

**Pair 1 (Beginner):**
```
Q: I've never written unit tests. My manager says I need to add tests to my Python project. Where do I start?

A: Start with your simplest pure function — one that takes input and returns output with no side effects.

**Step 1: Identify a testable function:**
```python
# calculator.py
def calculate_discount(price, discount_percent):
    if discount_percent < 0 or discount_percent > 100:
        raise ValueError("Discount must be between 0 and 100")
    return price * (1 - discount_percent / 100)
```

**Step 2: Write your first test:**
```python
# test_calculator.py
from calculator import calculate_discount

def test_basic_discount():
    assert calculate_discount(100, 10) == 90.0

def test_no_discount():
    assert calculate_discount(100, 0) == 100.0

def test_full_discount():
    assert calculate_discount(100, 100) == 0.0

def test_invalid_discount_raises():
    import pytest
    with pytest.raises(ValueError):
        calculate_discount(100, -5)
    with pytest.raises(ValueError):
        calculate_discount(100, 101)
```

**Step 3: Run the tests:**
```bash
pip install pytest
pytest test_calculator.py -v
```

**What to test first (priority order):**
1. Pure functions (input -> output, no side effects)
2. Core business logic (pricing, validation, calculations)
3. Edge cases (zero, empty, None, boundary values)
4. Error handling (does it raise the right exceptions?)

**What NOT to test (yet):**
- Framework code (Flask routing, Django ORM)
- Third-party libraries
- Trivial getters/setters
```
*Why this is effective:* Removes the intimidation of testing by starting with the simplest possible case and giving a clear priority order for what to test next.

**Pair 2 (Intermediate):**
```
Q: My tests are brittle — they break whenever I refactor my code, even when the behavior hasn't changed. What am I doing wrong?

A: Brittle tests usually test IMPLEMENTATION instead of BEHAVIOR. Here's the difference:

**Brittle test (tests implementation):**
```python
def test_get_user():
    service = UserService()
    service.get_user(1)

    # Testing HOW it works internally:
    service.db.execute.assert_called_once_with(
        "SELECT * FROM users WHERE id = ?", (1,)
    )
```
This breaks if you change the SQL query, add caching, or switch ORMs — even if the behavior is identical.

**Robust test (tests behavior):**
```python
def test_get_user_returns_user_data():
    service = UserService(db=fake_db_with_users)
    user = service.get_user(1)

    # Testing WHAT it returns:
    assert user.name == "Alice"
    assert user.email == "alice@example.com"

def test_get_user_returns_none_for_missing():
    service = UserService(db=empty_fake_db)
    user = service.get_user(999)
    assert user is None
```
This test doesn't care about SQL queries, caching, or ORMs. It only cares: "Given user 1 exists, does get_user(1) return the right data?"

**Rules for non-brittle tests:**
1. Test WHAT the function returns, not HOW it gets there
2. Don't assert on internal method calls (assert_called_with)
3. Use real objects when possible, fakes when necessary, mocks as last resort
4. If refactoring breaks a test but not behavior, the test is wrong

**The testing pyramid of stability:**
```
Most stable:  Assert on RETURN VALUES
              Assert on SIDE EFFECTS (database state, files written)
              Assert on EXCEPTIONS raised
Least stable: Assert on INTERNAL METHOD CALLS (mocks)
```
```
*Why this is effective:* Directly addresses the most common reason developers abandon testing (brittle tests) with a clear principle: test behavior, not implementation.

**Pair 3 (Advanced):**
```
Q: How do I test code that depends on external services (databases, APIs, file systems) without making tests slow or flaky?

A: Use the dependency injection pattern to make external dependencies replaceable in tests:

**Step 1: Make dependencies injectable:**
```python
# BAD — hard-coded dependency, untestable:
class OrderService:
    def __init__(self):
        self.db = PostgresDatabase()  # Can't replace in tests
        self.payment = StripeClient()  # Can't replace in tests

# GOOD — injectable dependencies:
class OrderService:
    def __init__(self, db, payment_client):
        self.db = db
        self.payment = payment_client
```

**Step 2: Create test doubles:**
```python
# Fake database (in-memory, fast, deterministic):
class FakeDatabase:
    def __init__(self):
        self.orders = {}

    def save_order(self, order):
        self.orders[order.id] = order

    def get_order(self, order_id):
        return self.orders.get(order_id)

# Fake payment client:
class FakePaymentClient:
    def __init__(self, should_succeed=True):
        self.should_succeed = should_succeed
        self.charges = []

    def charge(self, amount, card_token):
        self.charges.append({"amount": amount, "token": card_token})
        if self.should_succeed:
            return {"status": "success", "charge_id": "ch_fake123"}
        raise PaymentError("Card declined")
```

**Step 3: Write clean tests:**
```python
def test_place_order_success():
    db = FakeDatabase()
    payment = FakePaymentClient(should_succeed=True)
    service = OrderService(db=db, payment_client=payment)

    order = service.place_order(user_id=1, product_id=42, card_token="tok_123")

    assert order.status == "confirmed"
    assert order.id in db.orders  # Verify side effect
    assert len(payment.charges) == 1
    assert payment.charges[0]["amount"] == order.total

def test_place_order_payment_failure():
    db = FakeDatabase()
    payment = FakePaymentClient(should_succeed=False)
    service = OrderService(db=db, payment_client=payment)

    with pytest.raises(PaymentError):
        service.place_order(user_id=1, product_id=42, card_token="tok_bad")

    # Verify no order was saved on payment failure:
    assert len(db.orders) == 0
```

**When to use each test double:**
| Type | What it does | When to use |
|------|-------------|-------------|
| Fake | Working implementation (in-memory) | Databases, caches |
| Stub | Returns canned responses | External APIs |
| Mock | Records calls for verification | When you must verify interactions |
| Spy | Real object that also records calls | When you need real behavior + verification |

**Prefer fakes over mocks.** Fakes test behavior; mocks test implementation.
```
*Why this is effective:* Teaches the dependency injection pattern as the solution to testability, with a complete example showing fake objects that are more maintainable than mocks.'''
    ),
    (
        "thinking/auto-datagen-integration-testing",
        r'''Generate 3 high-quality training pairs that teach integration testing strategies. For each pair, explain why it's effective training data.''',
        r'''<think>
Integration testing bridges unit tests and end-to-end tests:
1. What integration tests cover that unit tests don't
2. Testing database interactions
3. Testing API endpoints end-to-end

Progression: understanding the testing pyramid -> database integration tests -> API integration tests
</think>

Here are 3 training pairs for integration testing:

**Pair 1 (Beginner):**
```
Q: What's the difference between unit tests and integration tests? My team argues about this constantly.

A: The difference is about BOUNDARIES — what's real and what's fake:

**Unit test:** Tests ONE function/class with ALL dependencies replaced by fakes.
```python
def test_calculate_shipping():
    # No database, no API, no filesystem — just the function:
    cost = calculate_shipping(weight=5, distance=100)
    assert cost == 15.50
```

**Integration test:** Tests how multiple real components work TOGETHER.
```python
def test_order_flow_with_database():
    # Real database, real service, real interactions:
    db = create_test_database()
    service = OrderService(db=db)

    order = service.create_order(user_id=1, items=[{"product": 1, "qty": 2}])
    retrieved = service.get_order(order.id)

    assert retrieved.items[0].quantity == 2
    assert retrieved.total > 0
```

**The testing pyramid:**
```
        /  E2E  \        Few, slow, expensive
       / tests    \      (browser, full stack)
      /____________\
     / Integration  \    Some, medium speed
    /   tests        \   (real DB, real APIs)
   /__________________\
  /    Unit tests      \  Many, fast, cheap
 /      (isolated)      \ (no external deps)
/________________________\
```

**What each level catches:**
| Level | Catches | Example |
|-------|---------|---------|
| Unit | Logic bugs | Wrong discount calculation |
| Integration | Wiring bugs | SQL query returns wrong columns |
| E2E | User flow bugs | Checkout button doesn't work |

**Rule of thumb:** 70% unit, 20% integration, 10% E2E.
```
*Why this is effective:* Settles the common team debate with a clear definition based on boundaries, not gut feeling.

**Pair 2 (Intermediate):**
```
Q: How do I write integration tests that use a real database without making them slow or leaving test data behind?

A: Use transaction rollback and test fixtures for fast, clean database tests:

**Strategy 1: Transaction rollback (fastest)**
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

@pytest.fixture
def db_session():
    engine = create_engine("postgresql://localhost/myapp_test")
    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)

    yield session  # Test runs here

    session.close()
    transaction.rollback()   # Undo ALL changes — database is clean
    connection.close()
```

Every test gets a clean database because all changes are rolled back:
```python
def test_create_user(db_session):
    user = User(name="Alice", email="alice@test.com")
    db_session.add(user)
    db_session.flush()  # Writes to DB (within transaction)

    found = db_session.query(User).filter_by(email="alice@test.com").first()
    assert found.name == "Alice"
    # After test: transaction.rollback() undoes everything

def test_user_table_is_empty(db_session):
    # This passes because the previous test was rolled back!
    count = db_session.query(User).count()
    assert count == 0
```

**Strategy 2: Test fixtures with factories**
```python
import factory
from factory.alchemy import SQLAlchemyModelFactory

class UserFactory(SQLAlchemyModelFactory):
    class Meta:
        model = User
        sqlalchemy_session_persistence = "commit"

    name = factory.Faker('name')
    email = factory.Faker('email')

class OrderFactory(SQLAlchemyModelFactory):
    class Meta:
        model = Order

    user = factory.SubFactory(UserFactory)
    total = factory.Faker('pydecimal', left_digits=3, right_digits=2, positive=True)

# In tests — create complex scenarios easily:
def test_user_with_orders(db_session):
    user = UserFactory()
    orders = OrderFactory.create_batch(5, user=user)

    result = get_user_order_summary(user.id)
    assert result.order_count == 5
```

**Strategy 3: Docker test database**
```python
# conftest.py — spin up a fresh database per test session
import docker

@pytest.fixture(scope="session")
def postgres_container():
    client = docker.from_env()
    container = client.containers.run(
        "postgres:15",
        environment={"POSTGRES_PASSWORD": "test"},
        ports={"5432/tcp": None},
        detach=True
    )
    # Wait for postgres to be ready
    port = container.ports["5432/tcp"][0]["HostPort"]
    yield f"postgresql://postgres:test@localhost:{port}/postgres"
    container.stop()
    container.remove()
```

**Performance tips:**
- Use `scope="session"` for database setup (create once, not per test)
- Use transaction rollback for per-test isolation (fast)
- Run tests in parallel with `pytest-xdist` using separate databases
```
*Why this is effective:* Solves the two biggest integration test problems (speed and cleanup) with three progressively sophisticated strategies.

**Pair 3 (Advanced):**
```
Q: How do I write integration tests for my REST API endpoints that test the full request/response cycle?

A: Use a test client to make real HTTP requests to your app without running a server:

**Flask API testing:**
```python
import pytest
from app import create_app

@pytest.fixture
def client():
    app = create_app(config="testing")
    app.config["TESTING"] = True
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
            yield client
            db.drop_all()

@pytest.fixture
def auth_headers(client):
    # Create a user and get a token:
    client.post('/api/register', json={
        "email": "test@example.com",
        "password": "securepass123"
    })
    response = client.post('/api/login', json={
        "email": "test@example.com",
        "password": "securepass123"
    })
    token = response.json["token"]
    return {"Authorization": f"Bearer {token}"}

# Test the full CRUD cycle:
def test_create_and_get_product(client, auth_headers):
    # Create
    response = client.post('/api/products', json={
        "name": "Widget",
        "price": 29.99,
        "category": "gadgets"
    }, headers=auth_headers)

    assert response.status_code == 201
    product_id = response.json["id"]
    assert response.json["name"] == "Widget"

    # Read
    response = client.get(f'/api/products/{product_id}', headers=auth_headers)
    assert response.status_code == 200
    assert response.json["price"] == 29.99

def test_create_product_validation(client, auth_headers):
    # Missing required field
    response = client.post('/api/products', json={
        "name": "Widget"
        # missing price
    }, headers=auth_headers)

    assert response.status_code == 422
    assert "price" in response.json["error"]["details"][0]["field"]

def test_unauthorized_access(client):
    response = client.get('/api/products')
    assert response.status_code == 401

def test_list_products_pagination(client, auth_headers):
    # Create 25 products
    for i in range(25):
        client.post('/api/products', json={
            "name": f"Widget {i}",
            "price": 10.0 + i
        }, headers=auth_headers)

    # First page
    response = client.get('/api/products?page=1&per_page=10', headers=auth_headers)
    assert response.status_code == 200
    assert len(response.json["data"]) == 10
    assert response.json["pagination"]["total"] == 25
    assert response.json["pagination"]["has_next"] is True

    # Last page
    response = client.get('/api/products?page=3&per_page=10', headers=auth_headers)
    assert len(response.json["data"]) == 5
    assert response.json["pagination"]["has_next"] is False
```

**What to test in API integration tests:**
| Category | What to verify |
|----------|---------------|
| Happy path | Correct status code, response body, headers |
| Validation | 422 for invalid input with helpful error messages |
| Auth | 401 for missing token, 403 for wrong permissions |
| Not found | 404 for missing resources |
| Pagination | Correct page sizes, has_next, total count |
| Idempotency | PUT/DELETE return same result on repeat calls |
| Concurrency | Two simultaneous creates don't conflict |
```
*Why this is effective:* Provides a complete, real-world API test suite pattern that developers can adapt for any REST API, covering all the response scenarios they should verify.'''
    ),
    (
        "thinking/auto-datagen-test-driven-development",
        r'''Generate 3 high-quality training pairs that teach test-driven development (TDD) methodology. For each pair, explain why it's effective training data.''',
        r'''<think>
TDD is widely discussed but rarely practiced correctly:
1. The red-green-refactor cycle
2. When TDD helps and when it doesn't
3. TDD for complex business logic

Progression: basic TDD cycle -> TDD for a real feature -> knowing when NOT to use TDD
</think>

Here are 3 training pairs for TDD:

**Pair 1 (Beginner):**
```
Q: I've heard about TDD but it seems backwards — how can I write tests before the code exists? Can you walk me through a real example?

A: TDD works in tiny cycles: Write a failing test -> Make it pass -> Clean up. Let's build a password validator:

**Cycle 1: First requirement — minimum length**
```python
# RED: Write a test that fails
def test_password_too_short():
    assert validate_password("abc") == {"valid": False, "errors": ["Must be at least 8 characters"]}

# Run: pytest → NameError: validate_password is not defined (RED ✗)

# GREEN: Write minimal code to pass
def validate_password(password):
    errors = []
    if len(password) < 8:
        errors.append("Must be at least 8 characters")
    return {"valid": len(errors) == 0, "errors": errors}

# Run: pytest → PASSED (GREEN ✓)
```

**Cycle 2: Add uppercase requirement**
```python
# RED: New failing test
def test_password_needs_uppercase():
    assert validate_password("abcdefgh") == {"valid": False, "errors": ["Must contain an uppercase letter"]}

# Run: pytest → FAILED (RED ✗) — our function doesn't check uppercase yet

# GREEN: Add uppercase check
def validate_password(password):
    errors = []
    if len(password) < 8:
        errors.append("Must be at least 8 characters")
    if not any(c.isupper() for c in password):
        errors.append("Must contain an uppercase letter")
    return {"valid": len(errors) == 0, "errors": errors}

# Run: pytest → PASSED (GREEN ✓)
```

**Cycle 3: Add number requirement**
```python
# RED:
def test_password_needs_number():
    assert validate_password("Abcdefgh") == {"valid": False, "errors": ["Must contain a number"]}

# GREEN: Add number check
# ... (add the check)

# REFACTOR: Clean up the pattern
def validate_password(password):
    rules = [
        (lambda p: len(p) >= 8, "Must be at least 8 characters"),
        (lambda p: any(c.isupper() for c in p), "Must contain an uppercase letter"),
        (lambda p: any(c.isdigit() for c in p), "Must contain a number"),
    ]
    errors = [msg for check, msg in rules if not check(password)]
    return {"valid": len(errors) == 0, "errors": errors}

# Run: pytest → ALL PASSED (GREEN ✓) — refactor didn't break anything
```

**The rhythm:** RED (fail) → GREEN (pass) → REFACTOR (clean) → repeat.

Each cycle takes 1-5 minutes. You never write more than a few lines before running tests.
```
*Why this is effective:* Shows TDD as a series of tiny concrete steps, making the "backwards" approach feel natural and manageable.

**Pair 2 (Intermediate):**
```
Q: TDD seems to work for simple functions, but how do I use it for a real feature like "user registration with email verification"?

A: Break the feature into small testable behaviors, then TDD each one:

**Step 1: List the behaviors (not the implementation):**
```
1. Registration creates a user with "unverified" status
2. Registration sends a verification email
3. Registration rejects duplicate emails
4. Verification with valid token marks user as verified
5. Verification with invalid token returns error
6. Verification with expired token returns error
```

**Step 2: TDD each behavior:**

```python
# Behavior 1: Registration creates unverified user
def test_register_creates_unverified_user():
    db = FakeDatabase()
    email_service = FakeEmailService()
    service = RegistrationService(db=db, email=email_service)

    result = service.register("alice@example.com", "SecurePass1!")

    assert result.success is True
    user = db.get_user_by_email("alice@example.com")
    assert user is not None
    assert user.verified is False

# Write just enough code to pass, then next test:

# Behavior 2: Registration sends verification email
def test_register_sends_verification_email():
    db = FakeDatabase()
    email_service = FakeEmailService()
    service = RegistrationService(db=db, email=email_service)

    service.register("alice@example.com", "SecurePass1!")

    assert len(email_service.sent) == 1
    assert email_service.sent[0]["to"] == "alice@example.com"
    assert "verify" in email_service.sent[0]["subject"].lower()

# Behavior 3: Reject duplicate emails
def test_register_rejects_duplicate_email():
    db = FakeDatabase()
    email_service = FakeEmailService()
    service = RegistrationService(db=db, email=email_service)

    service.register("alice@example.com", "SecurePass1!")
    result = service.register("alice@example.com", "AnotherPass1!")

    assert result.success is False
    assert "already exists" in result.error

# Behavior 4: Valid token verifies user
def test_verify_with_valid_token():
    db = FakeDatabase()
    email_service = FakeEmailService()
    service = RegistrationService(db=db, email=email_service)

    service.register("alice@example.com", "SecurePass1!")
    token = email_service.sent[0]["token"]

    result = service.verify_email(token)

    assert result.success is True
    user = db.get_user_by_email("alice@example.com")
    assert user.verified is True
```

**The key insight:** Each test describes ONE behavior. The implementation emerges from making all tests pass. You never need to design the whole system upfront.
```
*Why this is effective:* Shows how to decompose a real feature into testable behaviors, which is the hardest part of TDD for most developers.

**Pair 3 (Advanced):**
```
Q: When should I NOT use TDD? Are there cases where writing tests first is counterproductive?

A: Yes. TDD is a powerful tool but not always the right one. Here's when to skip it:

**Don't use TDD for:**

**1. Exploratory/prototype code:**
```
When you don't know WHAT to build yet, TDD locks you into premature decisions.

Spike first (no tests) → Understand the problem → Throw away the spike → TDD the real implementation.

Example: "Can we integrate with this new payment API?" Write throwaway code first to learn the API, then TDD the production integration.
```

**2. UI layout and visual design:**
```
Testing "the button is blue and 200px wide" is brittle and low-value.
Use visual regression tests (screenshot comparison) instead of unit tests for UI appearance.

TDD DOES work for UI behavior: "clicking submit disables the button and shows a spinner."
```

**3. One-off scripts and data migrations:**
```
A script you'll run once and delete doesn't need TDD.
But DO test the critical part:

# Don't TDD the whole migration script, but DO test the transform:
def test_transform_old_format_to_new():
    old = {"user_name": "alice", "user_email": "a@b.com"}
    new = transform(old)
    assert new == {"name": "alice", "email": "a@b.com"}
```

**4. When the API/interface is unclear:**
```
If you're designing an API and don't know what the interface looks like yet, TDD forces premature decisions. Sketch the API first, then TDD.
```

**DO use TDD for:**
| Scenario | Why TDD helps |
|----------|--------------|
| Business logic | Catches calculation errors immediately |
| Data transformations | Input/output is clearly defined |
| State machines | Complex transitions need verification |
| Bug fixes | Write a test that reproduces the bug first |
| Algorithms | Verify correctness at each step |
| Refactoring | Tests ensure behavior is preserved |

**The pragmatic approach:**
1. TDD for core business logic (always)
2. Test-after for infrastructure/integration code (usually)
3. No tests for throwaway code (sometimes)
4. Never zero tests for production code (non-negotiable)
```
*Why this is effective:* Teaches when NOT to use a technique, which is more valuable than dogmatic "always TDD" advice. Developers trust advice more when it acknowledges tradeoffs.'''
    ),
    (
        "thinking/auto-datagen-testing-edge-cases",
        r'''Generate 3 high-quality training pairs that teach how to identify and test edge cases. For each pair, explain why it's effective training data.''',
        r'''<think>
Edge case testing is where bugs hide:
1. Systematic approaches to finding edge cases
2. Boundary value analysis
3. Property-based testing for automatic edge case discovery

Progression: common edge case categories -> boundary value analysis -> property-based testing
</think>

Here are 3 training pairs for edge case testing:

**Pair 1 (Beginner):**
```
Q: I wrote tests for the "happy path" of my function but my manager says I need edge case tests. What are edge cases and how do I find them?

A: Edge cases are inputs at the BOUNDARIES of what your function handles. They're where most bugs hide.

**For any function, check these categories:**

```python
def process_items(items, max_count=10):
    """Process a list of items, up to max_count."""
    ...
```

**Empty/zero inputs:**
```python
test: process_items([])           # Empty list
test: process_items([], max_count=0)  # Zero max
```

**Single element:**
```python
test: process_items(["one"])      # Just one item
```

**Boundary values:**
```python
test: process_items(items, max_count=10)  # Exactly at limit
test: process_items(items, max_count=11)  # One over
test: process_items(items, max_count=9)   # One under
```

**None/null:**
```python
test: process_items(None)         # None instead of list
test: process_items([None, None]) # None elements
```

**Negative values:**
```python
test: process_items(items, max_count=-1)  # Negative max
```

**Very large inputs:**
```python
test: process_items(["x"] * 1_000_000)  # Huge list
```

**Special characters (for strings):**
```python
test: process_items(["", " ", "\n", "a" * 10000])
```

**The edge case checklist (memorize this):**
| Category | Test values |
|----------|------------|
| Empty | [], "", {}, 0, None |
| One | Single element, length 1 |
| Boundary | At the limit, limit-1, limit+1 |
| Negative | -1, -0.1, negative counts |
| Large | 10^6 elements, very long strings |
| Special | Unicode, newlines, spaces, special chars |
| Duplicate | All same values, repeated elements |
| Type | Wrong type (string instead of int) |
```
*Why this is effective:* Gives a concrete, memorizable checklist that developers can apply to ANY function, making edge case thinking systematic rather than ad hoc.

**Pair 2 (Intermediate):**
```
Q: I have a function that calculates shipping costs based on weight ranges. How do I test the boundaries between ranges?

A: This is boundary value analysis — testing at the exact points where behavior changes:

**The function:**
```python
def shipping_cost(weight_kg):
    """Calculate shipping cost by weight bracket."""
    if weight_kg <= 0:
        raise ValueError("Weight must be positive")
    if weight_kg <= 1:
        return 5.00
    if weight_kg <= 5:
        return 10.00
    if weight_kg <= 20:
        return 25.00
    return 50.00  # Over 20kg
```

**Boundary value tests:**
```python
# At each boundary, test the value ON the boundary, just below, and just above:

# Boundary: 0 (invalid/valid)
def test_zero_weight_raises():
    with pytest.raises(ValueError):
        shipping_cost(0)

def test_negative_weight_raises():
    with pytest.raises(ValueError):
        shipping_cost(-0.01)

def test_smallest_valid_weight():
    assert shipping_cost(0.01) == 5.00

# Boundary: 1kg (5.00 -> 10.00)
def test_exactly_1kg():
    assert shipping_cost(1.0) == 5.00   # <= 1, so 5.00

def test_just_over_1kg():
    assert shipping_cost(1.01) == 10.00  # > 1, so 10.00

# Boundary: 5kg (10.00 -> 25.00)
def test_exactly_5kg():
    assert shipping_cost(5.0) == 10.00

def test_just_over_5kg():
    assert shipping_cost(5.01) == 25.00

# Boundary: 20kg (25.00 -> 50.00)
def test_exactly_20kg():
    assert shipping_cost(20.0) == 25.00

def test_just_over_20kg():
    assert shipping_cost(20.01) == 50.00

# Floating point edge case:
def test_floating_point_boundary():
    # Does 0.1 + 0.1 + 0.1 ... == 1.0? (Floating point can surprise you)
    weight = sum([0.1] * 10)  # Should be 1.0
    assert shipping_cost(weight) == 5.00  # Might fail due to float imprecision!
```

**The boundary testing formula:**
For every boundary B: test B-epsilon, B, and B+epsilon.

This catches the most common bug: using `<` instead of `<=` (off-by-one at boundaries).
```
*Why this is effective:* Shows exactly how to apply boundary analysis to a realistic function, including the floating-point trap that most developers wouldn't think to test.

**Pair 3 (Advanced):**
```
Q: Writing individual edge case tests is tedious. Is there a way to automatically find edge cases I haven't thought of?

A: Yes — property-based testing generates hundreds of random inputs to find edge cases you'd never think of:

**Traditional tests:** You pick specific inputs.
**Property-based tests:** You describe PROPERTIES that should always hold, and the framework generates inputs.

**Using Hypothesis (Python):**
```python
from hypothesis import given, assume
from hypothesis import strategies as st

# Property: shipping cost is always positive for positive weights
@given(weight=st.floats(min_value=0.01, max_value=1000))
def test_shipping_always_positive(weight):
    cost = shipping_cost(weight)
    assert cost > 0

# Property: heavier packages never cost LESS than lighter ones
@given(
    w1=st.floats(min_value=0.01, max_value=1000),
    w2=st.floats(min_value=0.01, max_value=1000)
)
def test_heavier_costs_more_or_equal(w1, w2):
    if w1 <= w2:
        assert shipping_cost(w1) <= shipping_cost(w2)

# Property: a sort function returns the same elements
@given(lst=st.lists(st.integers()))
def test_sort_preserves_elements(lst):
    result = my_sort(lst)
    assert sorted(result) == sorted(lst)  # Same elements
    assert len(result) == len(lst)         # Same count

# Property: encode then decode returns original
@given(data=st.text())
def test_codec_roundtrip(data):
    encoded = my_encode(data)
    decoded = my_decode(encoded)
    assert decoded == data

# Property: a function never crashes (basic sanity)
@given(
    email=st.text(),
    name=st.text(),
    age=st.integers()
)
def test_create_user_never_crashes(email, name, age):
    try:
        result = create_user(email, name, age)
    except ValidationError:
        pass  # Expected for bad input
    except Exception as e:
        pytest.fail(f"Unexpected error: {e}")
```

**What Hypothesis finds that humans miss:**
- Empty strings, very long strings, unicode characters
- Boundary integers (0, -1, MAX_INT)
- NaN, Infinity, -0.0 for floats
- Lists with duplicates, sorted lists, reverse-sorted lists
- Combinations of edge cases you'd never think to combine

**When Hypothesis finds a bug, it SHRINKS the input to the smallest failing case:**
```
# Hypothesis found: test fails with weight=float('nan')
# Shrunk to: shipping_cost(float('nan')) — NaN comparison is always False!
```

**Properties to look for:**
| Property | Example |
|----------|---------|
| Roundtrip | encode(decode(x)) == x |
| Idempotent | f(f(x)) == f(x) |
| Monotonic | x > y implies f(x) >= f(y) |
| Invariant | len(sort(x)) == len(x) |
| Never crashes | f(any_input) doesn't raise unexpected errors |
```
*Why this is effective:* Introduces property-based testing as a practical upgrade from manual edge case testing, with concrete examples of properties to test for and real bugs it catches.'''
    ),
    (
        "thinking/auto-datagen-mocking-strategies",
        r'''Generate 3 high-quality training pairs that teach effective mocking and test double strategies. For each pair, explain why it's effective training data.''',
        r'''<think>
Mocking is often overused and misunderstood:
1. When to mock vs when to use real objects
2. Common mocking anti-patterns
3. Testing with external service contracts

Progression: basic mocking -> knowing when NOT to mock -> contract testing
</think>

Here are 3 training pairs for mocking strategies:

**Pair 1 (Beginner):**
```
Q: My function calls an external API. I can't call the real API in tests because it costs money and is slow. How do I mock it?

A: Replace the external call with a fake that returns predetermined data:

**The function to test:**
```python
import requests

def get_weather(city):
    response = requests.get(f"https://api.weather.com/v1/{city}")
    data = response.json()
    return {
        "city": city,
        "temp": data["temperature"],
        "condition": data["condition"]
    }
```

**Test with unittest.mock:**
```python
from unittest.mock import patch, Mock

def test_get_weather():
    # Create a fake response
    mock_response = Mock()
    mock_response.json.return_value = {
        "temperature": 72,
        "condition": "sunny"
    }

    with patch('mymodule.requests.get', return_value=mock_response) as mock_get:
        result = get_weather("seattle")

        assert result == {"city": "seattle", "temp": 72, "condition": "sunny"}
        mock_get.assert_called_once_with("https://api.weather.com/v1/seattle")

def test_get_weather_api_error():
    mock_response = Mock()
    mock_response.json.side_effect = ValueError("Invalid JSON")

    with patch('mymodule.requests.get', return_value=mock_response):
        with pytest.raises(ValueError):
            get_weather("seattle")
```

**Better approach — dependency injection (avoids patching):**
```python
def get_weather(city, http_client=None):
    client = http_client or requests
    response = client.get(f"https://api.weather.com/v1/{city}")
    data = response.json()
    return {"city": city, "temp": data["temperature"], "condition": data["condition"]}

# Test:
def test_get_weather():
    fake_client = Mock()
    fake_client.get.return_value.json.return_value = {"temperature": 72, "condition": "sunny"}

    result = get_weather("seattle", http_client=fake_client)
    assert result["temp"] == 72
```

**Rules for mocking external services:**
1. Mock at the boundary (the HTTP call), not internal functions
2. Test both success and failure responses
3. Test timeout handling
4. Keep mock data realistic (use actual API response format)
```
*Why this is effective:* Shows both the quick (patch) and proper (dependency injection) approaches, letting developers start fast and improve later.

**Pair 2 (Intermediate):**
```
Q: My team mocks everything in tests — even the database and internal classes. Our tests pass but bugs still make it to production. What are we doing wrong?

A: You're over-mocking. When you mock everything, you're testing that your mocks work, not that your code works.

**The over-mocking anti-pattern:**
```python
# This test mocks SO much that it tests nothing:
def test_create_order():
    mock_db = Mock()
    mock_validator = Mock()
    mock_pricer = Mock()
    mock_emailer = Mock()

    mock_validator.validate.return_value = True
    mock_pricer.calculate.return_value = 99.99

    service = OrderService(mock_db, mock_validator, mock_pricer, mock_emailer)
    service.create_order(user_id=1, items=[{"id": 1}])

    mock_db.save.assert_called_once()  # Tests that save was called... but was it the RIGHT data?
    mock_emailer.send.assert_called_once()  # Tests that email was sent... but with what content?
```

**Problems:**
1. Mock returns whatever you tell it — it can't catch wrong inputs
2. If you change the Pricer interface, mock tests still pass (no contract)
3. You're testing the SERVICE orchestrates calls, not that it WORKS

**Better: Use real objects where possible, mock only external boundaries:**
```python
def test_create_order():
    # REAL validator, REAL pricer, FAKE database, FAKE emailer
    db = FakeDatabase()  # In-memory, functional implementation
    emailer = FakeEmailer()  # Records sent emails
    validator = OrderValidator()  # Real validation logic
    pricer = Pricer(tax_rate=0.1)  # Real pricing logic

    service = OrderService(db, validator, pricer, emailer)
    order = service.create_order(user_id=1, items=[{"id": 1, "qty": 2, "price": 50}])

    # Test REAL behavior:
    assert order.total == 110.00  # 50*2 + 10% tax — real calculation
    assert db.get_order(order.id).status == "confirmed"  # Really saved
    assert emailer.sent[0]["subject"] == f"Order #{order.id} confirmed"  # Real email content
```

**The mocking spectrum (least to most fake):**
```
Real object → Spy → Fake → Stub → Mock
(best)                              (worst for confidence)

Real: Actual database (integration test)
Spy:  Real object that records calls
Fake: Simplified working implementation (in-memory DB)
Stub: Returns canned responses
Mock: Records calls, returns nothing useful
```

**Rule: Mock at the boundaries, use real objects inside.**
- Mock: External APIs, email services, payment gateways
- Real: Business logic, validation, calculations, data transformations
- Fake: Databases (in-memory), file systems, caches
```
*Why this is effective:* Diagnoses the exact problem (over-mocking leads to false confidence) and provides the mocking spectrum as a decision framework.

**Pair 3 (Advanced):**
```
Q: We mock external APIs in our tests, but when those APIs change their response format, our tests still pass while production breaks. How do we catch this?

A: You need contract tests — tests that verify your mocks match reality:

**The problem: Mock drift**
```python
# Your mock from 6 months ago:
mock_response = {"user": {"name": "Alice", "email": "alice@x.com"}}

# The real API now returns:
{"data": {"user": {"full_name": "Alice", "email_address": "alice@x.com"}}}

# Your tests pass. Production breaks.
```

**Solution 1: Record and replay with VCR.py:**
```python
import vcr

@vcr.use_cassette('tests/cassettes/weather_seattle.yaml')
def test_get_weather():
    # First run: makes real API call, records response to YAML file
    # Subsequent runs: replays recorded response (no network call)
    result = get_weather("seattle")
    assert result["temp"] > -50  # Sanity check

# Periodically re-record cassettes to catch API changes:
# pytest --vcr-record=all  (re-records all cassettes)
```

**Solution 2: Contract tests with schema validation:**
```python
import jsonschema

# Define the contract (expected response schema):
WEATHER_API_SCHEMA = {
    "type": "object",
    "required": ["temperature", "condition"],
    "properties": {
        "temperature": {"type": "number"},
        "condition": {"type": "string", "enum": ["sunny", "cloudy", "rainy", "snowy"]}
    }
}

# Contract test (runs against real API in CI, weekly):
@pytest.mark.contract
def test_weather_api_contract():
    response = requests.get("https://api.weather.com/v1/seattle")
    data = response.json()
    jsonschema.validate(data, WEATHER_API_SCHEMA)

# Unit test (uses same schema to validate mock data):
def test_mock_matches_contract():
    mock_data = {"temperature": 72, "condition": "sunny"}
    jsonschema.validate(mock_data, WEATHER_API_SCHEMA)  # Mock is valid
```

**Solution 3: Pact (consumer-driven contract testing):**
```python
# For internal microservices — Service A defines what it expects from Service B:

# Service A (consumer) test:
def test_get_user_contract(pact):
    pact.given("user 1 exists")\
        .upon_receiving("a request for user 1")\
        .with_request("GET", "/users/1")\
        .will_respond_with(200, body={
            "id": 1,
            "name": Like("Alice"),  # Any string
            "email": Like("alice@x.com")  # Any string matching pattern
        })

    with pact:
        result = user_client.get_user(1)
        assert result.name is not None

# The Pact file is shared with Service B, which verifies it can fulfill the contract.
```

**Testing strategy summary:**
| Test type | What it catches | When to run |
|-----------|----------------|-------------|
| Unit (with mocks) | Logic bugs | Every commit |
| Contract (against real API) | API changes | Weekly / in CI |
| Integration (real services) | Wiring bugs | Before deploy |

Never rely solely on mocked tests for external dependencies. Periodically verify your mocks match reality.
```
*Why this is effective:* Addresses a real production failure mode (mock drift) with three increasingly sophisticated solutions, giving developers options based on their needs.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
