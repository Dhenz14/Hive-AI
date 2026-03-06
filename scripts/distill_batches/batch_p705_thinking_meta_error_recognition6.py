"""Phase 3A: Metacognition — Error Recognition in Own Output (Part 6)
Scenarios: Wrong complexity analysis, incorrect tests, wrong tradeoffs
"""

PAIRS = [
    (
        "thinking/meta-error-wrong-complexity-hashmap",
        r'''I analyzed the complexity of this function and concluded it's O(n):

```python
def find_duplicates(items):
    seen = {}
    duplicates = []
    for item in items:
        if item in seen:
            duplicates.append(item)
        else:
            seen[item] = True
    return duplicates
```

My reasoning: we iterate through the list once, and hash table lookups are O(1), so total is O(n). Is my analysis correct?''',
        r'''<think>
Let me re-examine this complexity analysis...

The claim is O(n) with the reasoning: one loop through n items, each with O(1) hash lookup.

For typical inputs, this IS O(n). Hash table operations (dict in Python) are O(1) AVERAGE case.

But wait — what's the WORST case? If all items hash to the same bucket (hash collision), each lookup becomes O(n) because the hash table degrades to a linked list. With n items all in one bucket, each lookup is O(k) where k is the current number of items in that bucket. Total: O(1 + 2 + ... + n) = O(n²).

However, Python uses open addressing (not chaining) and has a sophisticated hash function that makes pathological collisions extremely unlikely for built-in types. For strings and ints, the hash function distributes well.

But there's a more subtle issue: what if `items` contains unhashable types? If `item` is a list or dict, `item in seen` raises `TypeError`. The function silently assumes all items are hashable.

And there's another complexity consideration: what if the items are long strings? Then computing the hash of each string is O(m) where m is the string length. The total would be O(n × m), not O(n).

Actually, let me reconsider the original claim more carefully. For PRACTICAL purposes with hashable built-in types of bounded size, the O(n) analysis is correct. The average case IS O(n). But saying "hash table lookups are O(1)" without noting it's average case (not worst case) is technically imprecise.

My analysis was essentially correct for practical purposes but imprecise about:
1. Worst case vs average case distinction
2. The assumption that items are hashable
3. The assumption that hash computation is O(1) (not true for variable-length items)

This isn't a major error, but the nuance matters in interviews and formal analysis.
</think>

**Your O(n) analysis is correct for the average case but overlooks important nuances.**

### What's right
For typical inputs with built-in hashable types (int, str of bounded length), the function is indeed O(n) average case. Python's dict uses a well-distributed hash function, so collisions are rare.

### What's imprecise

**1. Average vs worst case:**
```python
# Average case: O(1) per lookup → O(n) total ✓
# Worst case: all items collide → O(n) per lookup → O(n²) total

# Python mitigates this with:
# - Randomized hash seeds (since 3.3, prevents HashDoS)
# - Open addressing with perturbation
# But worst case is still theoretically O(n²)
```

**2. Hash computation isn't always O(1):**
```python
# For strings of length m: hash("a" * m) is O(m)
# Total for n strings of length m: O(n × m), not O(n)
items = ["a" * 1000000 for _ in range(1000)]  # O(n × m) to hash all
```

**3. Items must be hashable:**
```python
find_duplicates([[1, 2], [3, 4]])  # TypeError: unhashable type: 'list'
```

### The precise statement
> "O(n) average case for n hashable items of bounded size, O(n²) worst case with pathological hash collisions."

### When this nuance matters
- **Job interviews**: saying "O(1) average, O(n) worst case" for hash lookups shows depth
- **Security**: before Python 3.3, attackers could craft inputs causing O(n²) via hash flooding (HashDoS)
- **Large keys**: hashing a 1GB file to check for duplicates — hash computation dominates

### The meta-lesson
When analyzing complexity, always clarify average vs worst case for hash-based data structures, and note assumptions about key types and sizes. "Hash lookups are O(1)" is a useful simplification but not the whole truth.'''
    ),
    (
        "thinking/meta-error-wrong-complexity-nested-set",
        r'''I analyzed this function as O(n²) because of the nested loops:

```python
def unique_pairs(items):
    result = set()
    for i in items:
        for j in items:
            if i != j:
                pair = tuple(sorted([i, j]))
                result.add(pair)
    return result
```

O(n²) because of the double loop, right?''',
        r'''<think>
Let me re-examine this complexity...

Two nested loops over `items` of length n: that gives n × n = n² iterations. Each iteration does:
- `i != j`: O(1) comparison (assuming items are comparable in O(1))
- `sorted([i, j])`: O(1) since it's always 2 elements
- `tuple(...)`: O(1)
- `result.add(pair)`: O(1) average case

So the loop body is O(1), and we have n² iterations. Total: O(n²).

Wait, but the claim is just "O(n²) because of the double loop." Let me check if that reasoning is actually correct or if it's right for the wrong reason.

Actually, the O(n²) analysis IS correct here. Two nested loops each iterating over n elements = O(n²). The key question is whether the loop body is O(1), which it is.

But is O(n²) the TIGHT bound? Let's see — we always do n² iterations regardless of input. So it's Θ(n²), not just O(n²). The analysis is correct.

However, I should note that the OUTPUT size is also O(n²) — there are at most n(n-1)/2 unique pairs. So O(n²) is optimal for this problem if you need all pairs. You can't do better than O(n²) because you need to produce O(n²) results.

Actually wait — there's an optimization opportunity. The current code generates each pair TWICE (once as (i,j) and once as (j,i)), then relies on sorted + set to deduplicate. A smarter loop would only generate each pair once:

```python
for i in range(len(items)):
    for j in range(i+1, len(items)):
```

This does n(n-1)/2 iterations instead of n². Still O(n²), but half the constant factor.

So the complexity analysis is correct. The concern isn't wrong complexity analysis — it's that the code does redundant work. Each pair is computed twice.

Actually, I think the user is asking me to validate their analysis, and it IS correct. Let me think about whether I should flag it as an error...

No, the O(n²) is correct. But the reasoning "because of nested loops" is incomplete — nested loops don't ALWAYS mean O(n²). The inner loop might do fewer iterations (like binary search O(log n) inner), or the loop body might not be O(1). The correct reasoning is: "O(n²) because both loops iterate over all n items and the body is O(1)."
</think>

**Your O(n²) analysis is correct, but the reasoning "because of nested loops" is incomplete.**

### Why "nested loops = O(n²)" is oversimplified
Nested loops don't always mean O(n²):

```python
# O(n log n) — inner loop is logarithmic
for i in range(n):
    j = 1
    while j < n:
        j *= 2  # only log(n) iterations

# O(n) — inner loop total iterations bounded
for i in range(n):
    for j in range(i, min(i+5, n)):  # constant inner iterations
        process(i, j)

# O(n³) — inner loop body is O(n)
for i in range(n):
    for j in range(n):
        data[i:j]  # slice is O(j-i), averages to O(n)
```

### The correct reasoning for YOUR code
"O(n²) because both loops iterate over all n elements (n × n iterations) AND the loop body is O(1) (comparison, 2-element sort, set add are all constant time)."

### An actual issue with the code (not complexity)
The code does redundant work — each pair is generated twice:
```python
# Iteration (i=A, j=B): sorted([A,B]) = (A,B) → added to set
# Iteration (i=B, j=A): sorted([B,A]) = (A,B) → already in set (redundant!)
```

More efficient:
```python
def unique_pairs(items):
    items = list(items)
    result = set()
    for i in range(len(items)):
        for j in range(i + 1, len(items)):
            if items[i] != items[j]:
                result.add((min(items[i], items[j]), max(items[i], items[j])))
    return result
```

Still O(n²) but half the iterations: n(n-1)/2 instead of n².

### The meta-lesson
When analyzing complexity, don't just count loop nesting depth. Verify: (1) how many iterations does each loop actually perform, (2) what's the complexity of the loop body, and (3) is the bound tight? "Nested loops = O(n²)" is a heuristic, not a rule.'''
    ),
    (
        "thinking/meta-error-test-doesnt-test-anything",
        r'''I wrote this test for my user registration function:

```python
def test_user_registration():
    """Test that user registration works correctly."""
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "SecurePass123!"
    }

    result = register_user(user_data)

    assert result is not None
    assert isinstance(result, dict)
    assert "id" in result
```

Is this test thorough enough?''',
        r'''<think>
Let me analyze what this test actually verifies...

The test creates a user and checks:
1. `result is not None` — the function returned something
2. `isinstance(result, dict)` — it returned a dict
3. `"id" in result` — the dict has an "id" key

What does this NOT verify?
- Is the username stored correctly? Never checks `result["username"] == "testuser"`
- Is the email stored correctly? Never checks
- Is the password HASHED (not stored in plaintext)? Never checks
- Does a duplicate username raise an error? Not tested
- Does a duplicate email raise an error? Not tested
- Is the email format validated? Not tested
- Is the password strength validated? Not tested
- Can you log in with the registered credentials? Not tested

The test would pass even if `register_user` returned `{"id": 1}` with no data stored at all. It would pass if the password was stored in plaintext. It would pass if the username was silently truncated.

This is a "does it not crash?" test, not a "does it work correctly?" test. The assertions are too weak — they check the shape of the response but not its content or side effects.

The mutation testing perspective: if I changed `register_user` to always return `{"id": 999}` regardless of input, this test would still pass. That means the test doesn't actually test the function's behavior.

My error: I wrote assertions that check structural properties (not None, is dict, has key) instead of behavioral properties (correct values, correct side effects, correct error handling).
</think>

**This test barely tests anything. It verifies the response shape but not the actual behavior.**

### What the test actually checks
```python
assert result is not None      # "Something was returned"
assert isinstance(result, dict) # "It's a dict"
assert "id" in result           # "Dict has an 'id' key"
```

This test passes even if `register_user` is:
```python
def register_user(data):
    return {"id": 1}  # ignores input entirely!
```

### Mutation test: would these mutations be caught?
| Mutation | Caught? |
|----------|---------|
| Return `{"id": 1}` ignoring all input | No |
| Store password in plaintext | No |
| Ignore the email field | No |
| Allow duplicate usernames | No |
| Truncate username to 3 chars | No |

### A meaningful test
```python
def test_user_registration():
    user_data = {
        "username": "testuser",
        "email": "test@example.com",
        "password": "SecurePass123!"
    }

    result = register_user(user_data)

    # Verify returned data matches input
    assert result["username"] == "testuser"
    assert result["email"] == "test@example.com"
    assert "password" not in result  # password should NOT be in response

    # Verify user was actually created in database
    stored_user = get_user_by_id(result["id"])
    assert stored_user is not None
    assert stored_user.username == "testuser"

    # Verify password was hashed, not stored plaintext
    assert stored_user.password_hash != "SecurePass123!"
    assert verify_password("SecurePass123!", stored_user.password_hash)


def test_duplicate_username_rejected():
    register_user({"username": "taken", "email": "a@b.com", "password": "Pass123!"})
    with pytest.raises(ValueError, match="username already exists"):
        register_user({"username": "taken", "email": "c@d.com", "password": "Pass456!"})


def test_invalid_email_rejected():
    with pytest.raises(ValueError, match="invalid email"):
        register_user({"username": "user2", "email": "not-an-email", "password": "Pass123!"})
```

### The meta-lesson
A good test should fail when the code is wrong. If you can break the implementation without breaking the test, the test is too weak. Use the "mutation test" mental model: imagine changing the implementation — would the test catch it? Assert on VALUES and BEHAVIOR, not just types and shapes.'''
    ),
    (
        "thinking/meta-error-test-tests-framework-not-code",
        r'''I wrote this test for my caching decorator:

```python
def test_cache_decorator():
    @cache(ttl=60)
    def expensive_function(x):
        return x * 2

    result1 = expensive_function(5)
    result2 = expensive_function(5)

    assert result1 == 10
    assert result2 == 10
    assert result1 == result2
```

Does this test prove the cache is working?''',
        r'''<think>
Let me analyze what this test actually proves...

The test calls `expensive_function(5)` twice and checks that both return 10.

But `expensive_function(5)` ALWAYS returns 10 whether caching works or not! Even without the `@cache` decorator, calling `5 * 2` returns 10 every time.

This test would pass even if:
- The cache decorator is a no-op
- The cache decorator is removed entirely
- The function is called 1000 times (all returning 10)

The test checks the FUNCTION's correctness, not the CACHE's correctness. To test caching, you need to verify:
1. The underlying function is called only ONCE for the same input (not twice)
2. The cached result is returned on the second call WITHOUT calling the function
3. Different inputs get different cache entries
4. Cache expires after TTL

You need to track HOW MANY TIMES the underlying function was called, not just what it returned. This requires a mock or a counter.

```python
call_count = 0
@cache(ttl=60)
def tracked_function(x):
    nonlocal call_count
    call_count += 1
    return x * 2

tracked_function(5)  # call_count = 1
tracked_function(5)  # call_count should still be 1 if cache works!
```

My error: I tested the function's output instead of the cache's behavior. The test proves `5 * 2 == 10`, not that caching works.
</think>

**This test proves that `5 * 2 == 10`, not that caching works. The test passes identically with or without the cache decorator.**

### Why it doesn't test caching
```python
result1 = expensive_function(5)  # Returns 10 (with or without cache)
result2 = expensive_function(5)  # Returns 10 (with or without cache)
assert result1 == 10             # Proves 5*2==10, not caching
assert result2 == 10             # Same thing again
```

Remove `@cache(ttl=60)` entirely — the test still passes.

### What a real cache test looks like
```python
def test_cache_prevents_recomputation():
    call_count = 0

    @cache(ttl=60)
    def expensive_function(x):
        nonlocal call_count
        call_count += 1
        return x * 2

    result1 = expensive_function(5)
    result2 = expensive_function(5)

    assert result1 == 10
    assert result2 == 10
    assert call_count == 1  # THIS is the cache test!


def test_cache_different_args_separate():
    call_count = 0

    @cache(ttl=60)
    def func(x):
        nonlocal call_count
        call_count += 1
        return x * 2

    func(5)
    func(10)
    assert call_count == 2  # different args = different cache entries


def test_cache_expires_after_ttl():
    call_count = 0

    @cache(ttl=1)  # 1 second TTL
    def func(x):
        nonlocal call_count
        call_count += 1
        return x

    func(5)
    assert call_count == 1
    time.sleep(1.5)
    func(5)
    assert call_count == 2  # cache expired, function called again
```

### The meta-lesson
To test a behavior (caching, retrying, rate limiting), you must observe a SIDE EFFECT that differs between "behavior active" and "behavior inactive." For caching, that side effect is "how many times was the underlying function called?" If your test passes identically without the feature, it's not testing the feature.'''
    ),
    (
        "thinking/meta-error-wrong-tradeoff-consistency-availability",
        r'''For our e-commerce checkout system, I chose eventual consistency to maximize availability:

```python
async def process_checkout(order):
    # Deduct inventory asynchronously (eventual consistency)
    await message_queue.publish("inventory.deduct", {
        "product_id": order.product_id,
        "quantity": order.quantity
    })

    # Charge payment asynchronously
    await message_queue.publish("payment.charge", {
        "user_id": order.user_id,
        "amount": order.total
    })

    # Mark order as "processing"
    order.status = "processing"
    await order.save()

    return {"status": "processing", "order_id": order.id}
```

I prioritized availability over consistency since that's what modern systems do. Good design?''',
        r'''<think>
Let me think about this design for a checkout system...

The code publishes two async messages: one to deduct inventory, one to charge payment. Then marks the order as "processing." All three operations are independent — they can succeed or fail independently.

What can go wrong?

1. **Payment succeeds but inventory deduction fails:** Customer is charged but product is out of stock. Now you need a refund process — terrible UX and potential legal issues.

2. **Inventory deducted but payment fails:** Product reserved but customer can't pay. Inventory is held hostage until some timeout or manual intervention.

3. **Message queue loses a message:** The inventory deduction message is lost. Customer gets charged, order shows "processing" forever, product is never shipped.

4. **Double processing:** If the publish succeeds but the response times out, the caller might retry. Now you deduct inventory twice and charge twice.

5. **No atomicity between the two publishes:** If the second `publish` fails after the first succeeds, you have inventory deducted but no payment.

The fundamental error: checkout requires STRONG consistency, not eventual consistency. When money and physical goods are involved, you MUST guarantee that inventory deduction, payment, and order creation either ALL succeed or ALL fail. This is exactly the use case for transactions.

"Modern systems use eventual consistency" is true for things like social media feeds, search indexes, and analytics. But financial transactions are the TEXTBOOK example of where you need strong consistency. Banks don't do "eventual consistency" with your money.

The right approach: use a saga pattern with compensating transactions, or better yet, use synchronous operations with proper error handling and rollback.
</think>

**Checkout is one of the worst places to use eventual consistency. Financial transactions require strong consistency — either everything succeeds or everything rolls back.**

### What goes wrong with this design
```
Timeline 1: Payment succeeds, inventory fails
  → Customer charged, product out of stock, need manual refund

Timeline 2: Inventory deducted, payment fails
  → Product reserved, customer can't pay, inventory locked

Timeline 3: First message published, second fails
  → Partial state: inventory deducted but no payment initiated

Timeline 4: Message lost in queue
  → Customer charged, order stuck in "processing" forever
```

### The right approach: Saga with compensating transactions
```python
async def process_checkout(order):
    try:
        # Step 1: Reserve inventory (synchronous, reversible)
        reservation = await inventory_service.reserve(
            order.product_id, order.quantity
        )

        try:
            # Step 2: Charge payment (synchronous)
            payment = await payment_service.charge(
                order.user_id, order.total,
                idempotency_key=f"order-{order.id}"
            )
        except PaymentError:
            # Compensate: release inventory
            await inventory_service.release(reservation.id)
            raise

        # Step 3: Confirm order (all prerequisites succeeded)
        order.status = "confirmed"
        order.payment_id = payment.id
        order.reservation_id = reservation.id
        await order.save()

        # Step 4: THEN do async stuff (notifications, analytics)
        await message_queue.publish("order.confirmed", {"order_id": order.id})

        return {"status": "confirmed", "order_id": order.id}

    except Exception:
        order.status = "failed"
        await order.save()
        raise
```

### When eventual consistency IS appropriate
| Use case | Consistency needed |
|----------|-------------------|
| Social media likes count | Eventual |
| Search index updates | Eventual |
| Analytics/reporting | Eventual |
| Email notifications | Eventual |
| **Financial transactions** | **Strong** |
| **Inventory management** | **Strong** |
| **Order processing** | **Strong** |

### The meta-lesson
"Use eventual consistency" is not universal advice — it's a tradeoff. Eventual consistency trades correctness for availability and performance. For operations where incorrectness means financial loss, legal liability, or broken customer trust, strong consistency is non-negotiable. Always ask: "What's the cost of a temporarily inconsistent state?" If the answer involves money or legal obligations, use transactions.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
