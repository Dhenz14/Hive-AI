"""Phase 1X: Foundation Thinking — Testing Strategies (Part 5)

Five training pairs on testing: property-based testing design, mutation testing
interpretation, contract testing for APIs, load/stress test design, and chaos
engineering.
"""

PAIRS = [
    (
        "thinking/test-property-based",
        r'''We have a function that merges two sorted lists into one sorted list. Unit tests pass but we suspect edge cases are missed. Current tests:

def merge_sorted(a: list[int], b: list[int]) -> list[int]:
    result = []
    i = j = 0
    while i < len(a) and j < len(b):
        if a[i] <= b[j]:
            result.append(a[i])
            i += 1
        else:
            result.append(b[j])
            j += 1
    result.extend(a[i:])
    result.extend(b[j:])
    return result

# Current unit tests
def test_basic_merge():
    assert merge_sorted([1, 3, 5], [2, 4, 6]) == [1, 2, 3, 4, 5, 6]

def test_empty_lists():
    assert merge_sorted([], []) == []
    assert merge_sorted([1], []) == [1]
    assert merge_sorted([], [1]) == [1]

def test_duplicates():
    assert merge_sorted([1, 1], [1, 1]) == [1, 1, 1, 1]

How would you design property-based tests using Hypothesis to find edge cases that these unit tests miss?''',
        r'''<think>
Property-based testing generates random inputs and checks that certain properties (invariants) always hold. For merge_sorted, the properties are:

1. **Output is sorted:** For any two sorted inputs, the output must be sorted.
2. **Output is a permutation of inputs:** Every element in a and b appears in the output, with correct multiplicity.
3. **Output length = len(a) + len(b):** No elements lost or duplicated.
4. **Idempotency with reference:** merge_sorted(a, b) == sorted(a + b). This is the strongest property -- it says our function equals the specification.
5. **Stability-like:** Elements from a appear before elements from b when equal (since we use `<=`).

For Hypothesis strategies, we need to generate SORTED lists. We can either:
- Generate any list and sort it
- Use `st.lists(st.integers(), min_size=0).map(sorted)`

Edge cases Hypothesis might find that the unit tests miss:
- Very large lists (performance issues)
- Negative numbers
- Single-element lists
- Lists with all identical elements
- Lists where one is entirely before/after the other
- Lists with min/max integer values

Let me write the property-based tests.
</think>

Property-based tests check invariants across thousands of random inputs. For `merge_sorted`, here are the key properties:

```python
from hypothesis import given, settings, assume
from hypothesis import strategies as st

# Strategy: generate sorted lists of integers
sorted_lists = st.lists(
    st.integers(min_value=-10**9, max_value=10**9),
    max_size=1000,
).map(sorted)

# Property 1: Output is always sorted
@given(a=sorted_lists, b=sorted_lists)
def test_output_is_sorted(a, b):
    result = merge_sorted(a, b)
    for i in range(len(result) - 1):
        assert result[i] <= result[i + 1], (
            f"Not sorted at index {i}: {result[i]} > {result[i+1]}"
        )

# Property 2: Output contains exactly the input elements (no loss, no duplication)
@given(a=sorted_lists, b=sorted_lists)
def test_output_is_permutation_of_inputs(a, b):
    result = merge_sorted(a, b)
    assert sorted(result) == sorted(a + b)

# Property 3: Output length equals sum of input lengths
@given(a=sorted_lists, b=sorted_lists)
def test_output_length(a, b):
    result = merge_sorted(a, b)
    assert len(result) == len(a) + len(b)

# Property 4: Equivalence with reference implementation (strongest test)
@given(a=sorted_lists, b=sorted_lists)
def test_matches_reference(a, b):
    result = merge_sorted(a, b)
    expected = sorted(a + b)
    assert result == expected

# Property 5: Merging with empty list is identity
@given(a=sorted_lists)
def test_identity_with_empty(a):
    assert merge_sorted(a, []) == a
    assert merge_sorted([], a) == a

# Property 6: Commutativity of content (same elements regardless of order)
@given(a=sorted_lists, b=sorted_lists)
def test_commutative_content(a, b):
    r1 = merge_sorted(a, b)
    r2 = merge_sorted(b, a)
    assert sorted(r1) == sorted(r2)

# Property 7: Associativity -- merge(merge(a,b), c) == merge(a, merge(b,c))
@given(
    a=sorted_lists,
    b=sorted_lists,
    c=sorted_lists,
)
def test_associative(a, b, c):
    left = merge_sorted(merge_sorted(a, b), c)
    right = merge_sorted(a, merge_sorted(b, c))
    assert left == right

# Property 8: Stability -- equal elements from 'a' come before those from 'b'
@given(a=sorted_lists, b=sorted_lists)
def test_stability(a, b):
    """Track origin of each element to verify stable merge."""
    # Tag elements with source
    tagged_a = [(v, 'a', i) for i, v in enumerate(a)]
    tagged_b = [(v, 'b', i) for i, v in enumerate(b)]

    result = merge_sorted(a, b)

    # For equal values, verify 'a' elements appear first
    # Rebuild the merge tracking origins
    ri, ai, bi = 0, 0, 0
    while ai < len(a) and bi < len(b):
        if a[ai] <= b[bi]:
            assert result[ri] == a[ai]
            ai += 1
        else:
            assert result[ri] == b[bi]
            bi += 1
        ri += 1
```

**What property-based tests catch that unit tests miss:**
- **Integer overflow ranges:** Hypothesis tests with `min_value/max_value` near bounds
- **Large inputs:** Catches O(n^2) performance bugs
- **All-duplicates:** `[5,5,5,5]` merged with `[5,5,5,5]`
- **One list entirely before/after the other:** `[1,2,3]` + `[10,20,30]`
- **Single-element edge cases** that Hypothesis's shrinking reveals as minimal failing examples

**Design principle:** Properties 1-3 are necessary but not sufficient. Property 4 (reference equivalence) is the strongest single test. Use weaker properties to get better error messages when they fail.'''
    ),
    (
        "thinking/test-mutation-testing",
        r'''We ran mutation testing on our discount calculator and got 72% mutation score. Here are the surviving mutants. Interpret each one and write the missing tests:

# Original code
def calculate_discount(price: float, quantity: int,
                       customer_type: str, coupon: str = None) -> float:
    """Calculate final price after all applicable discounts."""
    if price <= 0 or quantity <= 0:
        raise ValueError("Price and quantity must be positive")

    subtotal = price * quantity

    # Volume discount
    if quantity >= 100:
        subtotal *= 0.85   # 15% off
    elif quantity >= 50:
        subtotal *= 0.90   # 10% off
    elif quantity >= 10:
        subtotal *= 0.95   # 5% off

    # Customer type discount
    if customer_type == "wholesale":
        subtotal *= 0.90   # extra 10% off
    elif customer_type == "preferred":
        subtotal *= 0.95   # extra 5% off

    # Coupon discount
    if coupon == "SAVE20":
        subtotal *= 0.80
    elif coupon == "SAVE10":
        subtotal *= 0.90

    # Minimum charge
    return max(subtotal, 1.00)

# Surviving mutants:
# 1. Changed `quantity >= 100` to `quantity > 100`
# 2. Changed `subtotal *= 0.85` to `subtotal *= 0.90`
# 3. Changed `return max(subtotal, 1.00)` to `return max(subtotal, 0.00)`
# 4. Changed `price <= 0` to `price < 0`
# 5. Removed the `elif quantity >= 50` branch entirely''',
        r'''<think>
Each surviving mutant means there's no test that distinguishes the mutated code from the original. Let me analyze each:

**Mutant 1: `quantity >= 100` -> `quantity > 100`**
This means no test uses exactly `quantity=100`. At quantity=100, original gives 15% off, mutant gives 10% off (falls to the elif). Missing test: boundary value at exactly 100.

**Mutant 2: `subtotal *= 0.85` -> `subtotal *= 0.90`**
This means the test for quantity >= 100 doesn't check the exact discount amount. It probably just checks "some discount was applied" or the test uses a price where 0.85 and 0.90 give the same rounded result. Missing test: assert exact value for volume discount.

Wait, 0.85 and 0.90 would give different values for any non-zero price. So maybe there's no test at all for quantity >= 100? Or the test checks something else. The test needs to assert the exact final price.

**Mutant 3: `max(subtotal, 1.00)` -> `max(subtotal, 0.00)`**
No test exercises the minimum charge. We need a test where all discounts stack to bring the price below $1.00. For example: price=$0.10, quantity=100, customer="wholesale", coupon="SAVE20" gives 0.10 * 100 * 0.85 * 0.90 * 0.80 = $6.12 -- still above $1. Need smaller values.

Actually, the minimum charge only matters if subtotal < $1.00. With all discounts: 0.85 * 0.90 * 0.80 = 0.612. So price * quantity * 0.612 < 1.00 means price * quantity < 1.634. So price=$0.01, quantity=10 gives 0.01 * 10 * 0.95 * 0.80 (with SAVE20, no customer discount) = $0.076. That's below $1.00 and should return $1.00.

**Mutant 4: `price <= 0` -> `price < 0`**
No test uses `price=0`. At price=0, original raises ValueError, mutant allows it (subtotal=0). Missing: boundary test for price=0.

**Mutant 5: Removed `elif quantity >= 50` branch entirely**
No test uses quantity in [50, 99]. Without this branch, quantities 50-99 get no volume discount (fall through). Missing: test with quantity=50 or similar.

Let me write the missing tests.
</think>

Each surviving mutant reveals a gap in the test suite. Here's the interpretation and fix:

**Mutant 1: `>= 100` to `> 100` -- Missing boundary test**
No test uses exactly `quantity=100`. The boundary between 10% and 15% discount is untested.

**Mutant 2: `0.85` to `0.90` -- No exact value assertion for 15% discount**
Tests either don't cover quantity >= 100, or check "a discount was applied" without verifying the exact amount.

**Mutant 3: `max(subtotal, 1.00)` to `max(subtotal, 0.00)` -- Minimum charge never triggered**
No test produces a subtotal below $1.00, so the `max` floor is never exercised.

**Mutant 4: `<= 0` to `< 0` -- Zero price not tested**
Tests check negative prices but not `price=0`, which should also raise ValueError.

**Mutant 5: `elif quantity >= 50` removed -- 50-99 range untested**
No test uses quantities in the 50-99 range.

```python
import pytest
from math import isclose

class TestDiscountCalculator:
    """Tests that kill each surviving mutant."""

    # Kills Mutant 1: boundary at exactly 100
    def test_volume_discount_boundary_at_100(self):
        # quantity=100 should get 15% off, not 10%
        result = calculate_discount(10.00, 100, "retail")
        expected = 10.00 * 100 * 0.85  # $850.00
        assert isclose(result, expected), (
            f"quantity=100 should get 15% discount: expected {expected}, got {result}"
        )

    def test_volume_discount_boundary_at_99(self):
        # quantity=99 should get 10% off (not 15%)
        result = calculate_discount(10.00, 99, "retail")
        expected = 10.00 * 99 * 0.90  # $891.00
        assert isclose(result, expected)

    # Kills Mutant 2: exact discount percentage verified
    def test_volume_discount_15_percent_exact(self):
        result = calculate_discount(100.00, 100, "retail")
        assert isclose(result, 8500.00), (
            "15% volume discount on $10,000 should be $8,500"
        )

    def test_volume_discount_not_confused_with_10_percent(self):
        # If mutant changes 0.85 to 0.90, this fails
        result = calculate_discount(20.00, 100, "retail")
        assert isclose(result, 20.00 * 100 * 0.85)  # $1700, not $1800
        assert not isclose(result, 20.00 * 100 * 0.90)

    # Kills Mutant 3: minimum charge exercised
    def test_minimum_charge_applied(self):
        # price=$0.01, qty=10, coupon=SAVE20 -> 0.01*10*0.95*0.80 = $0.076
        result = calculate_discount(0.01, 10, "retail", "SAVE20")
        assert result == 1.00, (
            "Subtotals below $1.00 should be capped at minimum charge $1.00"
        )

    def test_minimum_charge_edge_just_above(self):
        # Ensure prices just above $1.00 are NOT capped
        # Find inputs where subtotal is just above $1.00
        result = calculate_discount(1.00, 1, "retail")
        assert result == 1.00  # exactly at minimum

    # Kills Mutant 4: zero price raises ValueError
    def test_zero_price_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            calculate_discount(0, 5, "retail")

    def test_zero_quantity_raises(self):
        with pytest.raises(ValueError, match="must be positive"):
            calculate_discount(10.00, 0, "retail")

    # Kills Mutant 5: quantity 50-99 range tested
    def test_volume_discount_at_50(self):
        result = calculate_discount(10.00, 50, "retail")
        expected = 10.00 * 50 * 0.90  # $450.00 (10% off)
        assert isclose(result, expected), (
            f"quantity=50 should get 10% discount: expected {expected}, got {result}"
        )

    def test_volume_discount_at_75(self):
        result = calculate_discount(10.00, 75, "retail")
        expected = 10.00 * 75 * 0.90  # $675.00
        assert isclose(result, expected)

    def test_no_volume_discount_at_9(self):
        # quantity=9 gets no volume discount
        result = calculate_discount(10.00, 9, "retail")
        assert isclose(result, 90.00)  # no discount

    # Stacked discounts (bonus: ensures all discount paths interact correctly)
    def test_all_discounts_stacked(self):
        result = calculate_discount(10.00, 100, "wholesale", "SAVE20")
        expected = 10.00 * 100 * 0.85 * 0.90 * 0.80  # $612.00
        assert isclose(result, expected)
```

**Mutation testing lesson:** A 72% mutation score means 28% of code paths have no test that detects changes. The most common gaps are:
1. **Boundary values** (=100 vs >100)
2. **Exact value assertions** (checking "discount applied" vs "correct amount")
3. **Edge cases at limits** (minimum charge, zero inputs)
4. **Middle-of-range values** (50-99 never tested, only <10 and >=100)'''
    ),
    (
        "thinking/test-contract-testing",
        r'''We have a frontend that calls a user API, and both teams deploy independently. The API contract keeps breaking silently -- the backend team changes field names or types without telling us. Last week they renamed "user_name" to "username" and our frontend crashed in production.

Current API:
GET /api/users/{id}
Response: {
    "id": 123,
    "username": "jdoe",
    "email": "jdoe@example.com",
    "role": "admin",
    "created_at": "2025-01-15T10:30:00Z",
    "preferences": {
        "theme": "dark",
        "notifications": true
    }
}

POST /api/users
Request: {
    "username": "newuser",
    "email": "new@example.com",
    "password": "secret123"
}
Response: {
    "id": 456,
    "username": "newuser",
    "email": "new@example.com",
    "role": "user",
    "created_at": "2025-01-20T14:00:00Z",
    "preferences": null
}

How should we set up contract testing to prevent this?''',
        r'''<think>
Contract testing ensures that the API provider and consumer agree on the contract (request/response format) and both are tested against it.

The main approaches:
1. **Pact** (consumer-driven contract testing) -- the consumer (frontend) defines what it expects, and the provider (backend) verifies it can satisfy those expectations.
2. **OpenAPI/Swagger spec testing** -- both sides validate against a shared spec.
3. **Schema validation testing** -- validate responses against JSON schemas.

Pact is the gold standard for this scenario because:
- Consumer defines expectations (not the provider deciding unilaterally)
- Contract is a versioned artifact
- Provider verification catches breaking changes before deployment
- Can be integrated into CI/CD pipelines

The workflow:
1. Frontend team writes Pact tests that define expected request/response pairs
2. Pact generates a "contract file" (JSON)
3. Contract is published to a Pact Broker
4. Backend team runs provider verification against the contract
5. If verification fails, backend deployment is blocked

Let me design this for the user API.
</think>

Use **consumer-driven contract testing with Pact**. The frontend (consumer) defines what it needs, and the backend (provider) verifies it can deliver. Breaking changes are caught in CI before deployment.

**Step 1: Consumer (Frontend) defines contracts**

```python
# frontend/tests/contract/test_user_api_contract.py
import pytest
from pact import Consumer, Provider, Like, EachLike, Term

pact = Consumer('UserFrontend').has_pact_with(
    Provider('UserService'),
    pact_dir='./pacts',
)

@pytest.fixture
def setup_pact():
    pact.start_service()
    yield pact
    pact.stop_service()

class TestUserAPIContract:

    def test_get_user_by_id(self, setup_pact):
        """Frontend expects these fields with these types."""
        expected = {
            "id": Like(123),                    # any integer
            "username": Like("jdoe"),           # any string
            "email": Like("jdoe@example.com"),  # any string
            "role": Term(r"admin|user|viewer",  # enum of roles
                         "admin"),
            "created_at": Term(                 # ISO 8601 datetime
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                "2025-01-15T10:30:00Z",
            ),
            "preferences": Like({              # nullable object
                "theme": Like("dark"),
                "notifications": Like(True),
            }),
        }

        (setup_pact
         .given("user 123 exists")
         .upon_receiving("a request for user 123")
         .with_request("GET", "/api/users/123")
         .will_respond_with(200, body=expected))

        with pact:
            # Call the MOCK server (not real backend)
            result = my_api_client.get_user(123,
                                            base_url=pact.uri)
            assert result["username"]  # frontend uses this field
            assert result["email"]
            assert result["role"] in ("admin", "user", "viewer")

    def test_create_user(self, setup_pact):
        """Frontend sends this shape, expects this response."""
        request_body = {
            "username": "newuser",
            "email": "new@example.com",
            "password": "secret123",
        }
        expected_response = {
            "id": Like(456),
            "username": Like("newuser"),
            "email": Like("new@example.com"),
            "role": Like("user"),
            "created_at": Term(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z",
                "2025-01-20T14:00:00Z",
            ),
        }

        (setup_pact
         .given("no user named newuser exists")
         .upon_receiving("a request to create a user")
         .with_request("POST", "/api/users",
                       body=request_body,
                       headers={"Content-Type": "application/json"})
         .will_respond_with(201, body=expected_response))

        with pact:
            result = my_api_client.create_user(
                "newuser", "new@example.com", "secret123",
                base_url=pact.uri,
            )
            assert result["id"]

    def test_get_nonexistent_user(self, setup_pact):
        """Frontend handles 404 gracefully."""
        (setup_pact
         .given("user 999 does not exist")
         .upon_receiving("a request for nonexistent user")
         .with_request("GET", "/api/users/999")
         .will_respond_with(404, body={
             "error": Like("not_found"),
             "message": Like("User not found"),
         }))

        with pact:
            with pytest.raises(UserNotFoundError):
                my_api_client.get_user(999, base_url=pact.uri)
```

**Step 2: Publish contract to Pact Broker**
```bash
# In frontend CI pipeline
pact-broker publish ./pacts \
  --consumer-app-version=$(git rev-parse HEAD) \
  --broker-base-url=https://pact-broker.internal \
  --tag=$(git branch --show-current)
```

**Step 3: Provider (Backend) verifies the contract**
```python
# backend/tests/contract/test_provider_verification.py
from pact import Verifier

def test_user_service_satisfies_contracts():
    verifier = Verifier(
        provider="UserService",
        provider_base_url="http://localhost:8080",
    )

    # Provider states: set up test data
    verifier.provider_states_setup_url = (
        "http://localhost:8080/_pact/provider-states"
    )

    output, logs = verifier.verify_with_broker(
        broker_url="https://pact-broker.internal",
        publish_version=os.environ["GIT_SHA"],
        consumer_version_selectors=[
            {"tag": "main", "latest": True},     # main branch contracts
            {"deployed": True},                   # deployed consumer contracts
        ],
        enable_pending=True,  # new contracts don't break existing builds
    )
    assert output == 0, f"Contract verification failed:\n{logs}"


# backend/app/pact_states.py -- set up test data for each provider state
@app.post("/_pact/provider-states")
def setup_provider_state(request):
    state = request.json["state"]

    if state == "user 123 exists":
        db.insert_test_user(id=123, username="jdoe",
                            email="jdoe@example.com", role="admin")
    elif state == "user 999 does not exist":
        db.delete_user(999)  # ensure doesn't exist
    elif state == "no user named newuser exists":
        db.delete_user_by_name("newuser")
```

**Step 4: CI/CD gate (the critical part)**
```yaml
# backend CI pipeline
- name: Verify Pact contracts
  run: |
    pytest tests/contract/test_provider_verification.py
    # This step BLOCKS deployment if contract is broken

# can-i-deploy check before release
- name: Check deployment safety
  run: |
    pact-broker can-i-deploy \
      --pacticipant UserService \
      --version $GIT_SHA \
      --to-environment production
```

**How this prevents the "username" rename incident:**
1. Frontend contract specifies `"username": Like("jdoe")`
2. Backend team renames field to `user_name`
3. Provider verification fails: `"expected key 'username' but got 'user_name'"`
4. Backend CI blocks the deployment
5. Backend team either: keeps `username` (backward compatible) or coordinates the change with frontend'''
    ),
    (
        "thinking/test-load-testing",
        r'''We're launching a flash sale event expecting 50x normal traffic (normally 200 req/s, expecting 10,000 req/s peak). Our stack is:
- 4x FastAPI instances behind nginx
- PostgreSQL (primary + 2 read replicas)
- Redis for caching and sessions
- RabbitMQ for async order processing

We've never load-tested before. Design a comprehensive load test plan.''',
        r'''<think>
A load test plan for a flash sale needs to cover:

1. **Baseline measurement** -- what's current performance at 200 req/s?
2. **Gradual ramp-up** -- find the breaking point before 10k req/s
3. **Sustained load** -- can we handle 10k req/s for the duration of the sale?
4. **Spike test** -- what happens at the exact moment the sale opens (0 to 10k instantly)?
5. **Soak test** -- does performance degrade over time (memory leaks, connection pool exhaustion)?

Key metrics to track:
- Response time (p50, p95, p99)
- Error rate
- Throughput (actual req/s vs target)
- System resources (CPU, memory, disk I/O, network)
- Database metrics (connections, query time, replication lag)
- Redis hit rate, memory
- RabbitMQ queue depth, consumer lag

Realistic test scenarios:
- Browse products (read-heavy, cacheable)
- Add to cart (write, session state)
- Checkout (write, transactional, payment API call)
- Search (read, potentially expensive queries)

The traffic mix matters -- flash sales are typically:
- 70% browse/product pages
- 20% add-to-cart
- 8% checkout attempts
- 2% search

I'll use k6 (modern, scriptable, good reporting) for the load test tool.

Important: test against a staging environment that mirrors production. Never load test production directly.
</think>

Here's a comprehensive load test plan using k6:

**Phase 1: Test scenarios matching real user behavior**

```javascript
// load_test.js -- k6 load test script
import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const BASE_URL = __ENV.TARGET_URL || 'https://staging.example.com';

// Custom metrics
const errorRate = new Rate('errors');
const checkoutDuration = new Trend('checkout_duration');

// Realistic user session
export default function () {
    const userId = `user_${__VU}_${__ITER}`;

    group('Browse Products', () => {
        // 70% of traffic -- should be fast (cached)
        const res = http.get(`${BASE_URL}/api/products?page=1&limit=20`, {
            headers: { 'Accept': 'application/json' },
            tags: { name: 'list_products' },
        });
        check(res, {
            'products 200': (r) => r.status === 200,
            'products < 200ms': (r) => r.timings.duration < 200,
            'has products': (r) => JSON.parse(r.body).length > 0,
        }) || errorRate.add(1);

        sleep(1 + Math.random() * 2);  // think time

        // View product detail
        const productId = Math.floor(Math.random() * 100) + 1;
        const detail = http.get(`${BASE_URL}/api/products/${productId}`, {
            tags: { name: 'product_detail' },
        });
        check(detail, {
            'detail 200': (r) => r.status === 200,
            'detail < 150ms': (r) => r.timings.duration < 150,
        }) || errorRate.add(1);
    });

    sleep(0.5 + Math.random());

    // 20% add to cart
    if (Math.random() < 0.2) {
        group('Add to Cart', () => {
            const res = http.post(
                `${BASE_URL}/api/cart/items`,
                JSON.stringify({
                    product_id: Math.floor(Math.random() * 100) + 1,
                    quantity: 1,
                }),
                {
                    headers: { 'Content-Type': 'application/json' },
                    tags: { name: 'add_to_cart' },
                },
            );
            check(res, {
                'cart 200/201': (r) => [200, 201].includes(r.status),
                'cart < 300ms': (r) => r.timings.duration < 300,
            }) || errorRate.add(1);
        });
    }

    // 8% attempt checkout
    if (Math.random() < 0.08) {
        group('Checkout', () => {
            const start = Date.now();
            const res = http.post(
                `${BASE_URL}/api/orders`,
                JSON.stringify({
                    payment_method: 'card',
                    card_token: 'tok_test_visa',
                }),
                {
                    headers: { 'Content-Type': 'application/json' },
                    tags: { name: 'checkout' },
                    timeout: '10s',
                },
            );
            checkoutDuration.add(Date.now() - start);
            check(res, {
                'checkout success': (r) => [200, 201, 202].includes(r.status),
                'checkout < 2s': (r) => r.timings.duration < 2000,
            }) || errorRate.add(1);
        });
    }

    sleep(1 + Math.random() * 3);  // between-action think time
}
```

**Phase 2: Staged test execution plan**

```javascript
// k6 options for each test phase
// Phase 2a: Baseline -- confirm current capacity
export const baseline = {
    scenarios: {
        baseline: {
            executor: 'constant-arrival-rate',
            rate: 200,
            timeUnit: '1s',
            duration: '10m',
            preAllocatedVUs: 100,
            maxVUs: 300,
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<500', 'p(99)<1000'],
        errors: ['rate<0.01'],  // < 1% errors
    },
};

// Phase 2b: Ramp -- find breaking point
export const ramp = {
    scenarios: {
        ramp_up: {
            executor: 'ramping-arrival-rate',
            startRate: 200,
            timeUnit: '1s',
            stages: [
                { duration: '2m', target: 1000 },
                { duration: '2m', target: 2500 },
                { duration: '2m', target: 5000 },
                { duration: '2m', target: 7500 },
                { duration: '2m', target: 10000 },
                { duration: '5m', target: 10000 },  // sustain peak
                { duration: '2m', target: 200 },     // cool down
            ],
            preAllocatedVUs: 500,
            maxVUs: 5000,
        },
    },
    thresholds: {
        http_req_duration: ['p(95)<1000'],
        errors: ['rate<0.05'],  // < 5% at peak acceptable
    },
};

// Phase 2c: Spike -- simulate sale opening (0 to 10k instantly)
export const spike = {
    scenarios: {
        spike: {
            executor: 'ramping-arrival-rate',
            startRate: 200,
            timeUnit: '1s',
            stages: [
                { duration: '5m', target: 200 },     // normal traffic
                { duration: '10s', target: 10000 },   // SPIKE: sale opens
                { duration: '10m', target: 10000 },   // sustain
                { duration: '2m', target: 3000 },     // gradual decline
            ],
            preAllocatedVUs: 2000,
            maxVUs: 8000,
        },
    },
};

// Phase 2d: Soak -- 2-hour sustained load (detect memory leaks)
export const soak = {
    scenarios: {
        soak: {
            executor: 'constant-arrival-rate',
            rate: 5000,
            timeUnit: '1s',
            duration: '2h',
            preAllocatedVUs: 1000,
            maxVUs: 3000,
        },
    },
};
```

**Phase 3: Monitoring dashboard checklist**

```
Application metrics (Prometheus/Grafana):
  [ ] Request rate (actual vs target)
  [ ] Response time percentiles (p50, p95, p99)
  [ ] Error rate by endpoint
  [ ] Active connections per instance

PostgreSQL:
  [ ] Active connections vs max_connections
  [ ] Query duration (p95)
  [ ] Replication lag (read replicas)
  [ ] Lock wait time
  [ ] Cache hit ratio (should stay > 99%)

Redis:
  [ ] Hit rate (expect > 95% for product pages)
  [ ] Memory usage
  [ ] Connected clients
  [ ] Eviction rate

RabbitMQ:
  [ ] Queue depth (orders backing up?)
  [ ] Consumer processing rate
  [ ] Unacknowledged messages

Infrastructure:
  [ ] CPU per instance (alert at 80%)
  [ ] Memory per instance (alert at 85%)
  [ ] Network I/O
  [ ] Disk I/O (especially PostgreSQL)
```

**Phase 4: Pass/fail criteria**

| Metric | Baseline | Acceptable at 10k | Fail |
|---|---|---|---|
| p95 latency | < 200ms | < 1000ms | > 2000ms |
| p99 latency | < 500ms | < 2000ms | > 5000ms |
| Error rate | < 0.1% | < 2% | > 5% |
| Checkout success | > 99.9% | > 98% | < 95% |
| DB replication lag | < 10ms | < 500ms | > 2s |

**Run order:** baseline -> ramp -> fix bottlenecks -> spike -> soak -> sign off.'''
    ),
    (
        "thinking/test-chaos-engineering",
        r'''We run a Kubernetes-based e-commerce platform with 15 microservices. We've had three outages in the past quarter:
1. A Redis cluster node died and the session service went down for 20 minutes
2. DNS resolution failed intermittently, causing cascading timeouts
3. A deployment caused one service to consume all CPU, starving co-located services

Management wants us to start chaos engineering. How do we design a safe chaos engineering program?''',
        r'''<think>
Chaos engineering principles:
1. Define steady state (what does "healthy" look like?)
2. Hypothesize that steady state will hold during turbulence
3. Introduce realistic failures
4. Observe and learn

For a program that management will approve, I need:
- Safe blast radius (start small, expand gradually)
- Clear abort criteria
- Runbooks for each experiment
- GameDay format for team learning

Based on their three incidents, the experiments should target:
1. Cache/Redis failure resilience
2. Network failure resilience (DNS, latency, packet loss)
3. Resource exhaustion (CPU, memory)

Let me design a phased program.
</think>

Here's a phased chaos engineering program, designed for safety and organizational buy-in:

**Phase 0: Prerequisites (before any chaos)**

```yaml
# prerequisites_checklist.yaml
observability:
  - Centralized logging (all 15 services)
  - Distributed tracing (Jaeger/Zipkin)
  - Metrics dashboards per service
  - Alerting on error rate, latency, availability

steady_state_definition:
  # "Normal" looks like this:
  availability: ">= 99.9% of requests return 2xx/3xx"
  latency_p95: "<= 500ms for user-facing endpoints"
  order_processing: "orders complete within 30 seconds"
  error_rate: "<= 0.1% of requests return 5xx"

abort_criteria:
  # STOP the experiment immediately if:
  - "Error rate exceeds 5% for 60 seconds"
  - "Any service is completely unavailable"
  - "Order processing stops entirely"
  - "Manual abort by any team member (no questions asked)"

blast_radius_controls:
  - "Start in staging, graduate to production"
  - "Production experiments only during business hours (M-F 10am-3pm)"
  - "Never during peak traffic or promotional events"
  - "Affect max 1 service at a time initially"
  - "Feature flag to instantly disable experiments"
```

**Phase 1: Staging experiments (weeks 1-4)**

```python
# Experiment 1: Redis node failure (addresses Incident #1)
# Tool: Litmus Chaos or custom ChaosToolkit

# chaos_redis_failure.yaml (ChaosToolkit experiment)
experiment = {
    "title": "Redis node failure - session service resilience",
    "description": (
        "Kill one Redis cluster node. Hypothesis: session service "
        "degrades gracefully with higher latency but zero data loss."
    ),
    "steady-state-hypothesis": {
        "title": "Session service is healthy",
        "probes": [
            {
                "type": "probe",
                "name": "session-service-healthy",
                "provider": {
                    "type": "http",
                    "url": "http://session-svc/health",
                    "timeout": 3,
                },
                "tolerance": {"status": 200},
            },
            {
                "type": "probe",
                "name": "login-works",
                "provider": {
                    "type": "http",
                    "url": "http://gateway/api/auth/test-login",
                    "method": "POST",
                    "timeout": 5,
                },
                "tolerance": {"status": [200, 201]},
            },
        ],
    },
    "method": [
        {
            "type": "action",
            "name": "kill-redis-node",
            "provider": {
                "type": "process",
                "path": "kubectl",
                "arguments": (
                    "delete pod redis-cluster-2 "
                    "--namespace=cache --grace-period=0"
                ),
            },
        },
        # Wait for turbulence
        {"type": "probe", "name": "wait", "provider": {
            "type": "python", "module": "time", "func": "sleep",
            "arguments": {"secs": 30},
        }},
    ],
    "rollbacks": [
        {
            "type": "action",
            "name": "verify-redis-recovery",
            "provider": {
                "type": "process",
                "path": "kubectl",
                "arguments": (
                    "wait --for=condition=ready "
                    "pod -l app=redis-cluster --timeout=120s"
                ),
            },
        },
    ],
}
```

```python
# Experiment 2: DNS failure (addresses Incident #2)
experiment_dns = {
    "title": "Intermittent DNS failure",
    "hypothesis": (
        "Services handle DNS failures with retries and circuit breakers. "
        "User-facing error rate stays below 1%."
    ),
    "method": "Inject 50% DNS resolution failures for service-to-service calls",
    "tool": "Litmus ChaosEngine with dns-chaos",
    "duration": "5 minutes",
    "blast_radius": "Only traffic between order-service and inventory-service",
}

# Kubernetes NetworkChaos manifest (Chaos Mesh)
network_chaos_dns = """
apiVersion: chaos-mesh.org/v1alpha1
kind: DNSChaos
metadata:
  name: dns-failure-test
  namespace: staging
spec:
  action: error
  mode: all
  selector:
    namespaces: ["staging"]
    labelSelectors:
      app: order-service
  duration: "5m"
  patterns:
    - "inventory-svc.staging.svc.cluster.local"
"""
```

```python
# Experiment 3: CPU exhaustion (addresses Incident #3)
experiment_cpu = {
    "title": "Noisy neighbor CPU exhaustion",
    "hypothesis": (
        "Kubernetes resource limits prevent one service from starving others. "
        "Co-located services maintain normal latency."
    ),
    "method": "Stress-test CPU in one pod, verify neighbors are unaffected",
    "verification": [
        "Stressed pod gets throttled (not killed)",
        "Neighbor pods maintain p95 < 500ms",
        "No cascading failures",
    ],
}

# Verify resource limits are set (prerequisite!)
resource_check = """
# BEFORE the experiment, verify all services have limits
kubectl get pods -n staging -o json | jq '
  .items[] |
  {name: .metadata.name,
   limits: .spec.containers[].resources.limits,
   requests: .spec.containers[].resources.requests} |
  select(.limits == null or .requests == null)
'
# If any pods lack limits, FIX FIRST before experimenting
"""
```

**Phase 2: Production experiments (weeks 5-8)**

```python
# GameDay format -- structured team exercise
gameday_plan = {
    "name": "Flash Sale Resilience GameDay",
    "date": "2025-04-15 10:00-14:00",
    "participants": [
        "SRE team (facilitators)",
        "Backend engineers (observers + responders)",
        "On-call engineer (practice incident response)",
    ],
    "experiments": [
        {
            "time": "10:30",
            "name": "Kill 1 of 4 API gateway pods",
            "expected": "Load balancer routes around failed pod in < 10s",
            "abort_if": "Error rate > 2% for 30s",
        },
        {
            "time": "11:00",
            "name": "Inject 200ms latency on database calls",
            "expected": "Responses degrade but stay under 2s p99",
            "abort_if": "Timeouts cascade to more than 2 services",
        },
        {
            "time": "11:30",
            "name": "Redis failover (promote replica to primary)",
            "expected": "< 5s disruption, no session data loss",
            "abort_if": "Sessions are lost or login fails",
        },
        {
            "time": "13:00",
            "name": "Simulate AZ failure (drain one node group)",
            "expected": "Pods reschedule to remaining AZ in < 60s",
            "abort_if": "Any service has zero running pods",
        },
    ],
    "post_mortem": "14:00 -- review findings, create action items",
}
```

**Experiment results tracking:**
```
| Experiment | Hypothesis | Result | Action Items |
|------------|-----------|--------|--------------|
| Redis node kill | Graceful degradation | FAILED: session-svc crashed, no fallback | Add local cache fallback, circuit breaker |
| DNS 50% failure | Retries handle it | PARTIAL: order-svc retried but inventory-svc didn't | Add retry middleware to all services |
| CPU exhaustion | Limits prevent starvation | PASSED: Kubernetes throttled correctly | Verify all prod pods have limits set |
```

**Key principle:** Chaos engineering is NOT "break things and see what happens." It's the scientific method applied to distributed systems: hypothesis, controlled experiment, observation, learning.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
