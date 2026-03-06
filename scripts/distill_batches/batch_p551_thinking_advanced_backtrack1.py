"""Phase 2A: Advanced Reasoning — Backtracking & Dead-End Recovery (Part 1/5)
Algorithm failures: greedy fails → needs DP, sync fails → needs async, SQL join fails → needs CTE."""

PAIRS = [
    (
        "thinking/backtrack-greedy-fails-dp-coins",
        "I need to make change for any amount using coins [1, 3, 4]. My greedy approach always picks the largest coin first, but sometimes gives wrong results. Can you help?",
        r'''<think>
Let me work through the greedy approach first to see where it fails.

Greedy for amount = 6 with coins [1, 3, 4]:
- Pick 4 → remaining 2
- Pick 1 → remaining 1
- Pick 1 → remaining 0
- Total: 3 coins (4 + 1 + 1)

But wait — is that optimal? Let me check: 3 + 3 = 6, which is only 2 coins!

So greedy gives 3 coins, but optimal is 2. The greedy approach fails here because picking the locally optimal choice (largest coin) doesn't lead to the globally optimal solution.

This is a classic case where we need dynamic programming instead. The key insight is that the greedy choice at each step can block us from finding a better combination.

Let me design the DP solution:
- dp[i] = minimum coins needed for amount i
- For each amount, try every coin and take the minimum
- Base case: dp[0] = 0

Let me trace through:
dp[0] = 0
dp[1] = dp[1-1] + 1 = 1 (use coin 1)
dp[2] = dp[2-1] + 1 = 2 (use coin 1)
dp[3] = min(dp[3-1]+1, dp[3-3]+1) = min(3, 1) = 1 (use coin 3)
dp[4] = min(dp[4-1]+1, dp[4-3]+1, dp[4-4]+1) = min(2, 2, 1) = 1 (use coin 4)
dp[5] = min(dp[5-1]+1, dp[5-3]+1, dp[5-4]+1) = min(2, 2, 2) = 2
dp[6] = min(dp[6-1]+1, dp[6-3]+1, dp[6-4]+1) = min(3, 2, 2) = 2

dp[6] = 2, confirming that 3+3 is optimal.
</think>

Your greedy approach fails because picking the largest coin first doesn't always minimize the total count. For amount 6 with coins [1, 3, 4], greedy picks 4+1+1 = 3 coins, but 3+3 = 2 coins is better.

This requires **dynamic programming**:

```python
def min_coins(coins: list[int], amount: int) -> int:
    dp = [float('inf')] * (amount + 1)
    dp[0] = 0

    for i in range(1, amount + 1):
        for coin in coins:
            if coin <= i and dp[i - coin] + 1 < dp[i]:
                dp[i] = dp[i - coin] + 1

    return dp[amount] if dp[amount] != float('inf') else -1


def min_coins_with_trace(coins: list[int], amount: int) -> list[int]:
    """Also returns which coins were used."""
    dp = [float('inf')] * (amount + 1)
    parent = [-1] * (amount + 1)
    dp[0] = 0

    for i in range(1, amount + 1):
        for coin in coins:
            if coin <= i and dp[i - coin] + 1 < dp[i]:
                dp[i] = dp[i - coin] + 1
                parent[i] = coin

    if dp[amount] == float('inf'):
        return []

    result = []
    while amount > 0:
        result.append(parent[amount])
        amount -= parent[amount]
    return result
```

**Why greedy fails**: Greedy algorithms work when the "greedy choice property" holds — every locally optimal choice leads to a globally optimal solution. For coin change, this only works with specific coin sets (like US coins: 25, 10, 5, 1). With arbitrary denominations, you need DP to explore all combinations.

**When to suspect greedy won't work**: If you can construct a small example where the "obvious" first choice leads to a worse result, greedy will fail on larger inputs too.'''
    ),
    (
        "thinking/backtrack-greedy-fails-dp-scheduling",
        "I'm scheduling jobs to maximize profit. Each job has a deadline and profit. I'm sorting by profit and greedily assigning each to its latest available slot, but I'm getting suboptimal results with some inputs. What's wrong?",
        r'''<think>
Let me think about when greedy job scheduling fails.

Actually, wait — for the weighted job scheduling problem where jobs have different durations, greedy by profit doesn't work. But for the classic "each job takes 1 unit of time" problem, greedy by profit IS optimal.

Let me clarify which problem this is. The user says "each job has a deadline and profit" and they're assigning to "latest available slot" — this sounds like the unit-time job scheduling, which should work with greedy.

But what if the jobs have different durations? Then greedy by profit fails:
- Job A: profit 100, duration 3, deadline 3
- Job B: profit 60, duration 1, deadline 1
- Job C: profit 60, duration 1, deadline 2

Greedy picks A (profit 100), uses slots 1-3. Can't fit B or C. Total: 100.
Optimal: B at slot 1, C at slot 2 → profit 120.

So if jobs have varying durations, we need DP (weighted interval scheduling).

Actually, even with unit-time jobs but with weights, the greedy approach of "sort by profit, assign to latest slot" IS correct. The failure mode is when jobs have different durations/processing times.

Let me also consider: what if the user is doing the interval scheduling variant where jobs have start times, end times, and weights? Then greedy by profit definitely fails and we need DP.

I'll cover both the fix and the deeper issue.
</think>

The greedy approach works for unit-time jobs (each takes 1 slot), but fails when **jobs have different durations** or are **weighted interval scheduling** problems.

**Where greedy fails** — jobs with varying durations:
```
Job A: profit=100, duration=3, deadline=3  →  occupies slots [1,2,3]
Job B: profit=60,  duration=1, deadline=1  →  needs slot [1]
Job C: profit=60,  duration=1, deadline=2  →  needs slot [2]

Greedy (by profit): picks A → total = 100
Optimal: picks B + C → total = 120
```

**The DP solution for weighted interval scheduling**:

```python
from dataclasses import dataclass
from bisect import bisect_right

@dataclass
class Job:
    start: int
    end: int
    profit: int

def max_profit_schedule(jobs: list[Job]) -> tuple[int, list[Job]]:
    # Sort by end time
    jobs.sort(key=lambda j: j.end)
    n = len(jobs)

    # For each job, find latest non-conflicting job
    ends = [j.end for j in jobs]

    def latest_non_conflict(i: int) -> int:
        # Latest job that ends <= jobs[i].start
        idx = bisect_right(ends, jobs[i].start) - 1
        return idx

    # dp[i] = max profit using jobs[0..i]
    dp = [0] * (n + 1)

    for i in range(1, n + 1):
        # Option 1: skip this job
        skip = dp[i - 1]
        # Option 2: take this job + best from non-conflicting
        prev = latest_non_conflict(i - 1)
        take = jobs[i - 1].profit + dp[prev + 1]
        dp[i] = max(skip, take)

    # Backtrack to find which jobs were selected
    selected = []
    i = n
    while i > 0:
        prev = latest_non_conflict(i - 1)
        take = jobs[i - 1].profit + dp[prev + 1]
        if take >= dp[i - 1]:
            selected.append(jobs[i - 1])
            i = prev + 1
        else:
            i -= 1

    return dp[n], list(reversed(selected))
```

**Key insight**: Greedy works when choices are independent (unit-time jobs). When choosing one job *excludes* others (overlapping intervals), you need DP to explore the "take it or leave it" decision tree.

**Rule of thumb**: If selecting one item can block multiple other items, greedy likely fails.'''
    ),
    (
        "thinking/backtrack-sync-fails-async-api",
        "Our API endpoint fetches data from 3 external services sequentially, and response times are terrible (2-3 seconds). I tried adding caching but it only helps on repeat requests. How do I fix the cold-cache case?",
        r'''<think>
Let me analyze the problem. Three sequential external service calls:

Service A: ~500ms
Service B: ~800ms
Service C: ~700ms
Total sequential: ~2000ms

Caching helps repeat requests, but the first request (cold cache) is still slow. The user asked how to fix the cold-cache case specifically.

My first instinct might be to optimize each individual call — connection pooling, HTTP keep-alive, etc. But that's polishing the wrong thing.

Wait — the real question is: do these three calls depend on each other? If Service B needs the result of Service A, they MUST be sequential. But if they're independent, we can parallelize them.

Let me think about the likely architecture:
- Get user profile from Service A
- Get user orders from Service B
- Get recommendations from Service C
- Combine into response

If independent: parallel reduces time from sum to max: ~800ms instead of ~2000ms.

But what if there are partial dependencies? Say B needs A's result but C is independent?
- Run A first (~500ms), then B and C in parallel (max(800, 700) = 800ms)
- Total: ~1300ms vs ~2000ms

Let me also think about what happens when one service is slow or fails:
- Need timeouts per service
- Need fallback/default values
- The sync approach actually masks this problem because you just get a slow response
- The async approach forces you to handle partial failures explicitly

This is a case where the sync design is fundamentally wrong, not just slow.
</think>

Caching doesn't fix the cold-cache case because the fundamental problem is **sequential I/O** — you're waiting for each service to respond before calling the next.

**The sync bottleneck**:
```python
# Sequential: total = A + B + C = 500 + 800 + 700 = 2000ms
def get_dashboard(user_id: str):
    profile = service_a.get_profile(user_id)      # 500ms
    orders = service_b.get_orders(user_id)         # 800ms
    recommendations = service_c.get_recs(user_id)  # 700ms
    return combine(profile, orders, recommendations)
```

**Async parallel — if calls are independent**:
```python
import asyncio
import aiohttp

async def get_dashboard(user_id: str):
    async with aiohttp.ClientSession() as session:
        # All three run concurrently: total = max(500, 800, 700) = 800ms
        profile_task = fetch_profile(session, user_id)
        orders_task = fetch_orders(session, user_id)
        recs_task = fetch_recs(session, user_id)

        profile, orders, recs = await asyncio.gather(
            profile_task, orders_task, recs_task,
            return_exceptions=True  # Don't let one failure kill all
        )

    return combine(
        profile if not isinstance(profile, Exception) else default_profile(),
        orders if not isinstance(orders, Exception) else [],
        recs if not isinstance(recs, Exception) else [],
    )

async def fetch_profile(session, user_id: str, timeout: float = 1.0):
    async with session.get(
        f"{PROFILE_URL}/users/{user_id}",
        timeout=aiohttp.ClientTimeout(total=timeout)
    ) as resp:
        return await resp.json()
```

**If there are dependencies** (B needs A's result):
```python
async def get_dashboard(user_id: str):
    async with aiohttp.ClientSession() as session:
        # A must come first
        profile = await fetch_profile(session, user_id)

        # B depends on A, C is independent — run B and C in parallel
        orders, recs = await asyncio.gather(
            fetch_orders(session, user_id, profile["tier"]),
            fetch_recs(session, user_id),
            return_exceptions=True
        )
        # Total: A + max(B, C) = 500 + 800 = 1300ms
```

**Why just "optimizing the sync code" doesn't work**: Connection pooling, HTTP/2, and keep-alive shave off maybe 50-100ms per call. The fundamental constraint is that sequential I/O waits for each response before starting the next request. Going from 2000ms to 1800ms doesn't solve the user experience problem — going from 2000ms to 800ms does.'''
    ),
    (
        "thinking/backtrack-single-query-fails-cte",
        "I'm trying to write a SQL query to find customers who spent more than the average of their category. My JOIN approach is giving wrong results — some customers appear multiple times.",
        r'''<think>
Let me think about why a simple JOIN would give wrong results here.

The query probably looks something like:
```sql
SELECT c.name, SUM(o.amount) as total
FROM customers c
JOIN orders o ON c.id = o.customer_id
JOIN categories cat ON c.category_id = cat.id
WHERE SUM(o.amount) > (SELECT AVG(total) FROM ... per category)
GROUP BY c.name
```

The problem: if customers have multiple orders AND belong to categories, the JOIN can create a cartesian product, inflating the SUM. Also, you can't use WHERE with aggregate functions — need HAVING. And the subquery for "average per category" is correlated and tricky to write inline.

Let me try the naive approach first to show why it fails:

```sql
SELECT c.name, c.category_id, SUM(o.amount) as total_spent
FROM customers c
JOIN orders o ON c.id = o.customer_id
GROUP BY c.name, c.category_id
HAVING SUM(o.amount) > (
    SELECT AVG(sub.total)
    FROM (
        SELECT customer_id, SUM(amount) as total
        FROM orders
        GROUP BY customer_id
    ) sub
    JOIN customers c2 ON sub.customer_id = c2.id
    WHERE c2.category_id = c.category_id
)
```

This works but it's a mess — the correlated subquery in HAVING recalculates for each group. And if there are additional JOINs (like to a customer_addresses table), the cartesian product problem gets worse.

The CTE approach is much cleaner:
1. First CTE: calculate each customer's total spend
2. Second CTE: calculate average per category
3. Final query: join and filter

This separates concerns and avoids the duplicate row problem.
</think>

The duplicate rows come from the JOIN creating a cartesian product — if a customer has 5 orders and belongs to 1 category, that's fine. But add another JOIN (e.g., to addresses) and suddenly each order row multiplies by each address row, inflating your SUM.

**The failing JOIN approach**:
```sql
-- BUG: if customer has 3 orders and 2 addresses, each order counted twice
SELECT c.name, SUM(o.amount) as total
FROM customers c
JOIN orders o ON c.id = o.customer_id
JOIN addresses a ON c.id = a.customer_id  -- causes multiplication
GROUP BY c.name
```

**Fix with CTEs — separate the aggregations**:
```sql
WITH customer_totals AS (
    -- Step 1: each customer's total spend (no duplication possible)
    SELECT
        customer_id,
        SUM(amount) as total_spent
    FROM orders
    GROUP BY customer_id
),
category_averages AS (
    -- Step 2: average spend per category
    SELECT
        c.category_id,
        AVG(ct.total_spent) as avg_spent
    FROM customers c
    JOIN customer_totals ct ON c.id = ct.customer_id
    GROUP BY c.category_id
)
-- Step 3: find above-average customers
SELECT
    c.name,
    c.category_id,
    ct.total_spent,
    ca.avg_spent
FROM customers c
JOIN customer_totals ct ON c.id = ct.customer_id
JOIN category_averages ca ON c.category_id = ca.category_id
WHERE ct.total_spent > ca.avg_spent
ORDER BY ct.total_spent DESC;
```

**Why CTEs fix the problem**:
1. Each CTE does ONE aggregation with ONE base table — no cartesian products
2. The results are pre-aggregated before joining, so row multiplication doesn't inflate totals
3. The logic reads top-to-bottom like a story: "first compute totals, then averages, then filter"

**Rule of thumb**: When your JOIN+GROUP BY gives inflated counts or sums, break it into CTEs that aggregate *before* joining.'''
    ),
    (
        "thinking/backtrack-security-fix-bypassable",
        "I added input validation to prevent SQL injection by blocking quotes and semicolons in user input. But a penetration tester still got through. What am I doing wrong?",
        r'''<think>
Oh no — this is a classic mistake. Blocklist-based input sanitization for SQL injection is fundamentally broken. Let me think through why.

The user is blocking quotes (', ") and semicolons (;). A pen tester could bypass this with:

1. URL encoding: %27 for quote, %3B for semicolon (if decoded after validation)
2. Unicode tricks: ＇ (fullwidth apostrophe) might be normalized to ' by the database
3. No-quote techniques: `1 OR 1=1` doesn't need quotes for numeric fields
4. Comment-based: `1 UNION SELECT password FROM users--`
5. Char() function: `CHAR(39)` produces a quote in many databases
6. Backslash escaping: `\'` might escape the escape in some databases
7. Double encoding: %2527 → %27 → ' if double-decoded
8. Hex encoding: 0x27 for quote in MySQL

The first fix attempt (blocklist) fails. Let me think about the second attempt...

Someone might say "okay, I'll use an allowlist instead — only allow alphanumeric characters." That's better but too restrictive — users named O'Brien can't register, addresses with # fail, etc.

The real fix: parameterized queries (prepared statements). These separate SQL structure from data at the protocol level, making injection structurally impossible.

But I should also mention defense-in-depth:
- Parameterized queries (primary defense)
- Least-privilege database user
- WAF rules (secondary)
- Input validation for business rules (not security)

The key lesson: you can't fix an injection vulnerability by filtering the injectable content. You fix it by removing the injection point entirely.
</think>

Your blocklist approach is fundamentally broken — you're playing whack-a-mole against an infinite number of bypass techniques. Here's why each "fix" fails:

**Your blocklist blocked**: `'`, `"`, `;`

**Bypass techniques the pen tester likely used**:
```
# No quotes needed for numeric fields
GET /users?id=1 OR 1=1

# Comment-based injection (no semicolon needed)
GET /users?id=1 UNION SELECT password FROM users--

# CHAR() function builds quotes without typing them
GET /users?name=admin' becomes:
GET /users?name=CONCAT(CHAR(97),CHAR(100),CHAR(109),CHAR(105),CHAR(110))

# URL encoding (if decoded AFTER your check)
GET /users?name=%27%20OR%201%3D1--

# Double encoding
GET /users?name=%2527%20OR%201%3D1--
```

**The WRONG next step** — expanding the blocklist:
```python
# Still broken — there's always another bypass
BLOCKED = ["'", '"', ';', '--', 'UNION', 'SELECT', 'DROP', 'CHAR(', '0x']
def sanitize(input_str):
    for blocked in BLOCKED:
        if blocked.lower() in input_str.lower():
            raise ValueError("Invalid input")
    return input_str
```

**The CORRECT fix — parameterized queries**:
```python
# BEFORE (injectable — string concatenation)
cursor.execute(f"SELECT * FROM users WHERE name = '{user_input}'")

# AFTER (structurally impossible to inject)
cursor.execute("SELECT * FROM users WHERE name = %s", (user_input,))
```

**Why parameterized queries can't be bypassed**: The SQL structure (`SELECT * FROM users WHERE name = ?`) is sent to the database engine *separately* from the data. The engine compiles the query first, then binds the parameter. The data is NEVER parsed as SQL — it's literally impossible for it to change the query structure.

**Defense-in-depth** (layers on top of parameterized queries):
```python
# 1. Parameterized queries (primary — prevents injection)
cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))

# 2. Least-privilege DB user (limits damage IF somehow bypassed)
# CREATE USER app_readonly WITH PASSWORD '...'
# GRANT SELECT ON users TO app_readonly

# 3. Input validation for BUSINESS rules (not security)
def validate_username(name: str) -> str:
    if len(name) > 100:
        raise ValueError("Username too long")
    return name.strip()

# 4. ORM (abstracts away raw SQL entirely)
user = session.query(User).filter(User.name == user_input).first()
```

**The lesson**: You cannot secure an injection vulnerability by filtering the injected content. You must eliminate the injection point by separating code from data.'''
    ),
    (
        "thinking/backtrack-extract-method-needs-class",
        "I have a 200-line function that processes orders. I tried breaking it into smaller methods, but I ended up with 8 methods all passing the same 6 parameters around. It feels worse, not better. What went wrong?",
        r'''<think>
This is a common refactoring dead-end. The user extracted methods, which is the right instinct, but the symptom of "passing 6 parameters everywhere" tells me the real problem isn't method length — it's that these methods all operate on shared state that should be encapsulated in a class.

Let me think through the progression:

Step 1 (original): One 200-line function with lots of local variables
Step 2 (extract methods): 8 functions, but they all need the same context (order, customer, discount_rules, tax_rates, inventory, shipping_options)
Step 3 (what they should do): Extract a class that holds this shared context as instance state

The "6 parameters passed around" is a code smell called "data clump" — when the same group of variables always travels together, they want to be an object.

But I should also consider: maybe not ALL 8 methods need ALL 6 parameters. Let me think about whether this could be split into multiple smaller classes:
- OrderValidator(order, rules)
- PriceCalculator(order, discount_rules, tax_rates)
- ShipmentPlanner(order, inventory, shipping_options)

That might be even better — separate concerns rather than one big ProcessOrder class.

Let me also consider the builder or pipeline pattern — if these methods run in sequence, maybe it's a pipeline where each step adds to a context object.
</think>

You hit the classic "**extract method** is necessary but insufficient" wall. When 8 methods all share 6 parameters, the real problem isn't method length — it's that the shared state wants to be an **object**.

**What you have now** (worse than before):
```python
def process_order(order, customer, rules, tax_rates, inventory, shipping):
    validated = validate_order(order, customer, rules)
    priced = calculate_price(order, customer, rules, tax_rates)
    stock = check_inventory(order, inventory)
    ship = plan_shipping(order, customer, inventory, shipping)
    discount = apply_discounts(order, customer, rules, priced)
    tax = calculate_tax(order, customer, tax_rates, priced, discount)
    receipt = build_receipt(order, customer, priced, discount, tax, ship)
    notify = send_notifications(order, customer, receipt)
    # Every function takes order, customer, plus other stuff — parameter soup
```

**Step 1: Group into a class** (eliminates parameter passing):
```python
class OrderProcessor:
    def __init__(self, order, customer, rules, tax_rates, inventory, shipping):
        self.order = order
        self.customer = customer
        self.rules = rules
        self.tax_rates = tax_rates
        self.inventory = inventory
        self.shipping = shipping

    def process(self) -> Receipt:
        self._validate()
        self._calculate_price()
        self._check_inventory()
        self._apply_discounts()
        self._calculate_tax()
        self._plan_shipping()
        return self._build_receipt()
```

**Step 2: Notice not all methods need all state — split into focused classes**:
```python
@dataclass
class OrderContext:
    """Accumulates results as order flows through processing."""
    order: Order
    customer: Customer
    subtotal: Decimal = Decimal(0)
    discount: Decimal = Decimal(0)
    tax: Decimal = Decimal(0)
    shipping_plan: ShippingPlan | None = None

class OrderValidator:
    def __init__(self, rules: DiscountRules):
        self.rules = rules

    def validate(self, ctx: OrderContext) -> None:
        # Only needs order + rules
        ...

class PriceCalculator:
    def __init__(self, tax_rates: TaxRates, rules: DiscountRules):
        self.tax_rates = tax_rates
        self.rules = rules

    def calculate(self, ctx: OrderContext) -> None:
        # Writes subtotal, discount, tax to ctx
        ...

class ShipmentPlanner:
    def __init__(self, inventory: Inventory, shipping: ShippingOptions):
        self.inventory = inventory
        self.shipping = shipping

    def plan(self, ctx: OrderContext) -> None:
        # Only needs order + inventory + shipping
        ...

# Pipeline composition
def process_order(order, customer, rules, tax_rates, inventory, shipping):
    ctx = OrderContext(order=order, customer=customer)
    OrderValidator(rules).validate(ctx)
    PriceCalculator(tax_rates, rules).calculate(ctx)
    ShipmentPlanner(inventory, shipping).plan(ctx)
    return build_receipt(ctx)
```

**The progression**: Extract Method → Extract Class → Extract Multiple Classes. If you stop at "extract method," you get parameter soup. The methods are telling you they share context — listen to them.'''
    ),
    (
        "thinking/backtrack-unit-test-needs-integration",
        "All my unit tests pass with mocks, but the feature is broken in production. My mock for the payment gateway returns success, but the real gateway rejects our requests. What should I do differently?",
        r'''<think>
This is a textbook case where unit tests with mocks give false confidence. Let me think about what's happening.

The unit test mocks the payment gateway and returns success. The test verifies that:
- The code handles success correctly
- The code handles (mocked) errors correctly
- Business logic around payments works

What the test DOESN'T verify:
- The actual request format matches what the gateway expects
- The HTTP headers are correct (auth token, content-type)
- The response parsing handles the REAL response format
- Timeout handling with actual network latency
- TLS/certificate configuration
- API version compatibility

The mock is a lie — it tells your test "everything is fine" when the actual integration is broken.

First thought: "just don't mock" — but that's too extreme. You don't want unit tests hitting real payment gateways.

Better approach: layers of testing:
1. Unit tests with mocks → test business logic
2. Contract tests → verify your mock matches reality
3. Integration tests → hit a sandbox/test gateway
4. Smoke tests → verify production connectivity

The key insight is that mocks have a maintenance burden — when the real API changes, your mocks don't update automatically. You need contract tests to detect this drift.

Let me also think about the specific common failures:
- Serialization differences (snake_case vs camelCase)
- Missing required fields the mock didn't enforce
- Different error response formats
- Pagination the mock didn't simulate
- Rate limiting the mock didn't implement
</think>

Your mocks are **lying to you**. They tell your tests "the integration works" without actually testing the integration. This is the #1 failure mode of over-mocked test suites.

**What your unit test actually verifies**:
```python
# This test passes, but proves nothing about the real gateway
def test_process_payment(self):
    mock_gateway = Mock()
    mock_gateway.charge.return_value = {"status": "success", "id": "txn_123"}

    result = process_payment(mock_gateway, amount=99.99, card="tok_visa")

    assert result.success  # Yes, your mock returned success. Congratulations.
```

**What's probably failing in production**:
```python
# Your code sends:
{"amount": 99.99, "card_token": "tok_visa"}

# But the real gateway expects:
{"amount_cents": 9999, "source": "tok_visa", "currency": "usd"}
# Field names are wrong, amount format is wrong, missing required field
```

**The fix — layered testing strategy**:

```python
# Layer 1: Unit test with mock (tests YOUR logic, not the integration)
def test_payment_retries_on_network_error(self):
    gateway = Mock()
    gateway.charge.side_effect = [ConnectionError, {"status": "success"}]
    result = process_payment(gateway, amount=99.99)
    assert result.success
    assert gateway.charge.call_count == 2

# Layer 2: Contract test (verifies your mock matches reality)
def test_mock_matches_real_gateway_schema(self):
    """Run occasionally against sandbox to verify mock accuracy."""
    real_response = requests.post(
        SANDBOX_URL + "/charges",
        json={"amount_cents": 100, "source": "tok_test", "currency": "usd"},
        headers={"Authorization": f"Bearer {SANDBOX_KEY}"}
    ).json()

    # Verify our mock returns the same SHAPE as reality
    mock_response = mock_gateway.charge(100, "tok_test")
    assert set(real_response.keys()) == set(mock_response.keys())
    assert type(real_response["amount"]) == type(mock_response["amount"])

# Layer 3: Integration test (hits sandbox, runs in CI nightly)
@pytest.mark.integration
def test_real_gateway_charge(sandbox_gateway):
    result = sandbox_gateway.charge(
        amount_cents=100,
        source="tok_visa_test",
        currency="usd"
    )
    assert result["status"] in ("succeeded", "pending")
    assert "id" in result

# Layer 4: Smoke test (runs post-deploy, verifies connectivity)
@pytest.mark.smoke
def test_gateway_connectivity():
    response = requests.get(
        GATEWAY_URL + "/health",
        timeout=5,
        headers={"Authorization": f"Bearer {API_KEY}"}
    )
    assert response.status_code == 200
```

**The lesson**: Mocks test *your code's behavior*. Contract tests verify *your mocks are accurate*. Integration tests verify *the real integration works*. You need all three — a mock that doesn't match reality is worse than no test at all, because it gives false confidence.'''
    ),
    (
        "thinking/backtrack-cache-needs-algorithm",
        "Our recommendation API is slow (5 seconds). I added Redis caching, which helps on repeat requests, but first-request latency is still 5 seconds. Cache warm-up helps some, but we can't pre-compute for all 2M users. How do I fix this?",
        r'''<think>
The user added caching, which is the typical first response to "it's slow." But caching doesn't help when:
1. The cache is cold (first request)
2. The key space is too large to pre-warm (2M users)
3. The data changes frequently (invalidation storms)

So caching was the wrong approach — or at least, insufficient. Let me think about what's actually slow.

5 seconds for a recommendation API. What's it doing?

Typical recommendation pipeline:
1. Fetch user profile and history (100ms)
2. Fetch candidate items (200ms)
3. Score all candidates against user (4000ms) ← likely bottleneck
4. Sort and return top N (100ms)

The scoring step is probably O(users × items) or running a model inference. Let me think about algorithmic improvements:

Option 1: Approximate Nearest Neighbors (ANN) instead of brute-force scoring
- Pre-compute embeddings for all items
- Use FAISS, Annoy, or ScaNN for ANN search
- O(log n) instead of O(n) lookup
- Cold query drops from 5s to ~50ms

Option 2: Two-stage retrieval
- Stage 1: Fast candidate retrieval (ANN, simple heuristics) → top 1000
- Stage 2: Expensive re-ranking model on just 1000 candidates
- Much faster than scoring all items

Option 3: Pre-computed candidate pools
- Cluster similar users
- Pre-compute recommendations per cluster, not per user
- Reduces key space from 2M to ~1000 clusters

The key insight: caching is a BAND-AID that avoids the slow computation. The real fix is making the computation fast. If the algorithm is O(n²) and n is large, no amount of caching fixes the cold-cache case.

Let me recommend the ANN approach since it's the most impactful.
</think>

Caching doesn't fix slow algorithms — it just amortizes them. With 2M users and changing data, you'll always have cold cache misses. **The fix is algorithmic, not infrastructural.**

**Why your 5-second recommendation is slow** (likely):
```python
# O(n) brute-force scoring — 2M users × 100K items = too slow
def get_recommendations(user_id: str) -> list[Item]:
    user = get_user_profile(user_id)          # 100ms
    all_items = get_all_items()                # 200ms
    scored = [(item, score(user, item))        # 4500ms — THE BOTTLENECK
              for item in all_items]
    return sorted(scored, key=lambda x: -x[1])[:20]  # 200ms
```

**Fix: Approximate Nearest Neighbors (ANN) — O(log n) instead of O(n)**:
```python
import numpy as np
import faiss

class RecommendationEngine:
    def __init__(self, item_embeddings: np.ndarray):
        # Pre-build the search index (done once, on startup or in a job)
        dim = item_embeddings.shape[1]
        self.index = faiss.IndexIVFFlat(
            faiss.IndexFlatL2(dim), dim,
            n_clusters=1024  # sqrt(n_items) is a good default
        )
        self.index.train(item_embeddings)
        self.index.add(item_embeddings)
        self.index.nprobe = 10  # search 10 clusters (trade accuracy/speed)

    def recommend(self, user_id: str, top_k: int = 20) -> list[Item]:
        user_embedding = self.get_user_embedding(user_id)  # 10ms

        # ANN search: finds approximate top-K in ~5ms instead of 4500ms
        distances, indices = self.index.search(
            user_embedding.reshape(1, -1), top_k * 5  # oversample for re-ranking
        )

        # Re-rank the top 100 candidates with expensive model (optional)
        candidates = [self.items[i] for i in indices[0]]
        reranked = self.rerank(user_id, candidates)  # 50ms on 100 items

        return reranked[:top_k]
        # Total: ~65ms vs 5000ms
```

**The performance comparison**:
```
Approach          | Cold request | Warm request | Memory
------------------|-------------|-------------|--------
Brute force       | 5000ms      | 5000ms      | Low
+ Redis cache     | 5000ms      | 5ms         | High (2M keys)
ANN (FAISS)       | 65ms        | 65ms        | ~1GB index
ANN + cache       | 65ms        | 5ms         | Moderate
```

**The lesson**: When caching doesn't solve your problem, the computation itself is too expensive. Look for algorithmic improvements that reduce the complexity class (O(n) → O(log n)), not infrastructure that avoids the computation.'''
    ),
    (
        "thinking/backtrack-inheritance-needs-composition",
        "I have a class hierarchy for notifications: EmailNotification, SMSNotification, PushNotification. Now I need to add logging, retry logic, and rate limiting. My first instinct is to create LoggingEmailNotification, RetryEmailNotification, etc., but that's a combinatorial explosion. What's the right pattern?",
        r'''<think>
Classic diamond/combinatorial problem with inheritance. Let me count the explosion:

3 notification types × 3 features × combinations =
- EmailNotification
- LoggingEmailNotification
- RetryEmailNotification
- RateLimitedEmailNotification
- LoggingRetryEmailNotification
- LoggingRateLimitedEmailNotification
- RetryRateLimitedEmailNotification
- LoggingRetryRateLimitedEmailNotification
- ... × 3 for SMS and Push = 24 classes!

That's clearly wrong. The user already recognizes this, so I need to show the right approach.

My first thought: Decorator pattern. Each concern (logging, retry, rate limiting) wraps a notification sender and adds behavior before/after the send() call.

Let me also consider:
- Strategy pattern: pass the retry/logging behavior as strategies? Less natural here.
- Middleware/pipeline: like HTTP middleware, each step processes and passes to next? Yes, this is essentially the decorator pattern.
- Composition with mixins: Python supports multiple inheritance, could use mixins. But order matters and it's fragile.

Decorator pattern is the best fit here because:
1. Each wrapper has a single responsibility
2. They compose arbitrarily: Logging(Retry(RateLimit(Email())))
3. Easy to add new wrappers without touching existing code
4. Order of wrapping is explicit and meaningful

Let me think about the order:
- Logging should be outermost (log everything including retries)
- Retry should wrap rate limiting (retry after rate limit backoff)
- Rate limiting should be innermost (prevent actual sends)
- So: Logging(Retry(RateLimit(EmailSender())))

Actually, I need to think more carefully. Rate limiting should probably be outside retry — you want to rate limit the total attempts, not just the initial ones. It depends on the use case. This is a great teaching point about composition order mattering.
</think>

You're right to avoid the combinatorial explosion. The answer is the **Decorator pattern** — each concern (logging, retry, rate limiting) wraps any notification sender, composing arbitrarily.

**The inheritance explosion you want to avoid**: 3 types × 8 feature combos = 24 classes

**Decorator pattern solution**:
```python
from abc import ABC, abstractmethod
import time
import logging

logger = logging.getLogger(__name__)

# Core interface
class NotificationSender(ABC):
    @abstractmethod
    def send(self, recipient: str, message: str) -> bool:
        ...

# Concrete implementations
class EmailSender(NotificationSender):
    def send(self, recipient: str, message: str) -> bool:
        # actual email sending logic
        return send_email(recipient, message)

class SMSSender(NotificationSender):
    def send(self, recipient: str, message: str) -> bool:
        return send_sms(recipient, message)

class PushSender(NotificationSender):
    def send(self, recipient: str, message: str) -> bool:
        return send_push(recipient, message)

# Decorators — each wraps ANY NotificationSender
class LoggingNotification(NotificationSender):
    def __init__(self, inner: NotificationSender):
        self.inner = inner

    def send(self, recipient: str, message: str) -> bool:
        logger.info(f"Sending to {recipient} via {self.inner.__class__.__name__}")
        result = self.inner.send(recipient, message)
        logger.info(f"Result: {'success' if result else 'failure'}")
        return result

class RetryNotification(NotificationSender):
    def __init__(self, inner: NotificationSender, max_retries: int = 3):
        self.inner = inner
        self.max_retries = max_retries

    def send(self, recipient: str, message: str) -> bool:
        for attempt in range(self.max_retries):
            try:
                if self.inner.send(recipient, message):
                    return True
            except Exception:
                if attempt == self.max_retries - 1:
                    raise
            time.sleep(2 ** attempt)  # exponential backoff
        return False

class RateLimitedNotification(NotificationSender):
    def __init__(self, inner: NotificationSender, max_per_minute: int = 10):
        self.inner = inner
        self.max_per_minute = max_per_minute
        self.timestamps: list[float] = []

    def send(self, recipient: str, message: str) -> bool:
        now = time.time()
        self.timestamps = [t for t in self.timestamps if now - t < 60]
        if len(self.timestamps) >= self.max_per_minute:
            raise RateLimitExceeded("Too many notifications")
        self.timestamps.append(now)
        return self.inner.send(recipient, message)

# Compose freely — any combination, any order
email = LoggingNotification(RetryNotification(RateLimitedNotification(EmailSender())))
sms = LoggingNotification(RetryNotification(SMSSender()))  # no rate limit
push = RetryNotification(PushSender(), max_retries=1)      # no logging, 1 retry

# All share the same interface
for sender in [email, sms, push]:
    sender.send("user@example.com", "Hello!")
```

**Why composition beats inheritance here**:
- 3 concrete classes + 3 decorators = **6 classes** total (vs 24 with inheritance)
- Adding a new feature (e.g., deduplication) = 1 new decorator, not 8 new subclasses
- Wrapping order is explicit: `Logging(Retry(RateLimit(Email())))` — you can see exactly what happens and in what order
- Each class has a single responsibility and is independently testable'''
    ),
    (
        "thinking/backtrack-rest-needs-different-paradigm",
        "I'm building a real-time collaborative document editor. I started with REST endpoints (GET /doc, PUT /doc, PATCH /doc), but multiple users editing simultaneously causes constant conflicts and lost updates. How do I fix this?",
        r'''<think>
This is a fundamental paradigm mismatch. REST is request-response and stateless — but collaborative editing needs:
1. Real-time updates pushed to all clients
2. Conflict resolution for concurrent edits
3. Persistent connection for low-latency sync

Let me trace why REST fails here:

User A loads doc (version 1)
User B loads doc (version 1)
User A saves changes (PUT) → version 2
User B saves changes (PUT based on version 1) → overwrites User A's changes!

Even with optimistic locking (ETags), the UX is terrible:
User B gets a 409 Conflict, has to manually merge. With 5 users editing simultaneously, everyone gets constant conflicts.

The polling approach is also bad:
- Poll every second: 5 users × 1 req/sec = lots of traffic, still 1 second latency
- Poll every 100ms: too much traffic
- And you still have the conflict problem

What paradigm should we use instead?

Option 1: WebSockets + Operational Transform (OT)
- Google Docs uses this
- Each edit is an "operation" (insert char at position 5, delete chars 10-15)
- Server transforms operations to handle concurrent edits
- Complex to implement correctly

Option 2: WebSockets + CRDTs (Conflict-free Replicated Data Types)
- Newer approach (Yjs, Automerge)
- Data structure guarantees convergence without a central server
- Simpler conceptually but can be memory-intensive

Option 3: WebSockets + Last-Write-Wins with real-time cursors
- Simplest, but loses edits
- Only acceptable for non-critical content

For a document editor, Option 2 (CRDTs via Yjs) is probably the best modern choice. It's simpler than OT and works offline.

Let me show the architecture shift from REST to WebSocket+CRDT.
</think>

REST is fundamentally wrong for this use case. It's request-response and stateless, but collaborative editing needs **real-time, bidirectional, conflict-free synchronization**.

**Why REST fails — the lost update problem**:
```
User A: GET /doc → version 1 → edits → PUT /doc (version 1 → 2)
User B: GET /doc → version 1 → edits → PUT /doc (version 1 → 2) ← OVERWRITES A!
```

Even optimistic locking (ETags/409 Conflict) just means users get constant merge conflicts with 3+ editors.

**The right paradigm: WebSocket + CRDT**:
```python
# Server (Python + FastAPI + Yjs)
from fastapi import FastAPI, WebSocket
import y_py as Y

app = FastAPI()
docs: dict[str, Y.YDoc] = {}

@app.websocket("/ws/doc/{doc_id}")
async def doc_websocket(websocket: WebSocket, doc_id: str):
    await websocket.accept()

    # Get or create collaborative document
    if doc_id not in docs:
        docs[doc_id] = Y.YDoc()
    doc = docs[doc_id]

    # Send current state to new client
    state = Y.encode_state_as_update(doc)
    await websocket.send_bytes(state)

    # Bidirectional sync loop
    try:
        while True:
            # Receive edit from this client
            update = await websocket.receive_bytes()
            Y.apply_update(doc, update)

            # Broadcast to all other clients (simplified)
            await broadcast(doc_id, update, exclude=websocket)
    except WebSocketDisconnect:
        pass
```

```javascript
// Client (JavaScript + Yjs)
import * as Y from 'yjs'
import { WebsocketProvider } from 'y-websocket'
import { QuillBinding } from 'y-quill'

const ydoc = new Y.Doc()
const provider = new WebsocketProvider('ws://localhost/ws/doc', 'my-doc', ydoc)

// Bind to editor — all edits automatically sync
const ytext = ydoc.getText('content')
const binding = new QuillBinding(ytext, quillEditor, provider.awareness)

// Awareness: see other users' cursors in real-time
provider.awareness.setLocalStateField('user', {
    name: 'User A',
    color: '#ff0000'
})
```

**Why CRDTs solve the conflict problem**: Every edit is a CRDT operation that is guaranteed to converge regardless of the order received. Two users typing at the same position? The CRDT assigns a deterministic order based on client IDs. No conflicts, no merges, no lost updates — by mathematical guarantee.

**Architecture comparison**:
```
REST (wrong tool)          WebSocket + CRDT (right tool)
─────────────────          ────────────────────────────
Request-response           Bidirectional streaming
Stateless                  Persistent connection + state
Poll for updates           Push updates instantly
Manual conflict resolution Automatic conflict resolution
Works for CRUD apps        Works for real-time collaboration
```

**When REST is still right**: CRUD operations, form submissions, API integrations, anything that's "submit and wait." Don't throw out REST — just recognize that real-time collaboration is a fundamentally different problem.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
