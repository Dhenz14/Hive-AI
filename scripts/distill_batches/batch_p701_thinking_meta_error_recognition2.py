"""Phase 3A: Metacognition — Error Recognition in Own Output (Part 2)"""

PAIRS = [
    (
        "thinking/meta-error-n-plus-1-in-serializer",
        "I wrote this Django REST serializer. The endpoint is slow with lots of data. Can you spot the problem?\n\n```python\nclass OrderSerializer(serializers.ModelSerializer):\n    customer_name = serializers.SerializerMethodField()\n    items = serializers.SerializerMethodField()\n    \n    class Meta:\n        model = Order\n        fields = ['id', 'total', 'customer_name', 'items']\n    \n    def get_customer_name(self, obj):\n        return obj.customer.name\n    \n    def get_items(self, obj):\n        return [{'name': item.product.name, 'qty': item.quantity}\n                for item in obj.items.all()]\n```",
        r'''<think>
Let me re-examine this serializer for performance issues.

`get_customer_name` accesses `obj.customer.name` — this triggers a database query for each order (customer is a FK, lazy-loaded by default).

`get_items` accesses `obj.items.all()` — another query per order. AND inside the list comprehension, `item.product.name` triggers ANOTHER query per item.

So for 100 orders with 5 items each:
- 1 query: get all orders
- 100 queries: get customer for each order (N+1)
- 100 queries: get items for each order (N+1)
- 500 queries: get product for each item (N+1 within N+1!)
- Total: 1 + 100 + 100 + 500 = 701 queries

This is the classic N+1 problem, hidden inside a serializer where it's especially hard to spot because the serializer LOOKS innocent — it's just accessing attributes.

**My error:** I wrote a correct serializer that WORKS but generates hundreds of database queries. The code is logically correct but has O(n²) database access hidden behind ORM lazy loading.

**Why this is hard to catch:** Django's ORM makes it very easy to write N+1 queries because attribute access (`obj.customer.name`) looks like a simple property access but actually triggers a SQL query.
</think>

**The serializer is correct but has a severe N+1 query problem.** For 100 orders with 5 items each, it generates **701 database queries** instead of 3-4.

## The Hidden Queries

```python
# For each of 100 orders:
def get_customer_name(self, obj):
    return obj.customer.name      # 1 query per order (100 total)

def get_items(self, obj):
    for item in obj.items.all():  # 1 query per order (100 total)
        item.product.name         # 1 query per item (500 total)

# Total: 1 + 100 + 100 + 500 = 701 queries
# Each query is ~5ms → 701 × 5ms = 3.5 seconds!
```

## The Fix: Eager Loading in the View

```python
# The serializer stays the same — the fix is in the VIEW
class OrderViewSet(viewsets.ModelViewSet):
    serializer_class = OrderSerializer

    def get_queryset(self):
        return Order.objects.select_related(
            'customer'           # JOIN customer in single query
        ).prefetch_related(
            'items',             # Fetch all items in 1 query
            'items__product',    # Fetch all products in 1 query
        )

# Now: 3-4 queries total regardless of order count
# 1: SELECT * FROM orders
# 2: SELECT * FROM customers WHERE id IN (...)
# 3: SELECT * FROM order_items WHERE order_id IN (...)
# 4: SELECT * FROM products WHERE id IN (...)
```

## Why This Error Is Hard to Catch

Django's ORM makes lazy loading look like simple attribute access. `obj.customer.name` looks like reading a property, but it actually executes `SELECT * FROM customers WHERE id = ?`. The serializer code looks clean and correct — the N+1 problem is completely invisible until you profile.

**Lesson:** whenever you serialize related objects in a loop (SerializerMethodField, list comprehensions over querysets), check that the view uses `select_related` / `prefetch_related`. The serializer should never trigger database queries that the view could have batched.'''
    ),
    (
        "thinking/meta-error-wrong-test-assertion",
        "I wrote this test for a discount calculator. The test passes. But is it actually testing what it claims?\n\n```python\ndef test_bulk_discount():\n    \"\"\"Test that orders over $100 get a 10% discount.\"\"\"\n    order = Order(items=[Item(price=50), Item(price=60)])\n    discounted = apply_discount(order)\n    assert discounted.total > 0\n```",
        r'''<think>
Let me critically examine what this test actually verifies.

The test claims to verify: "orders over $100 get a 10% discount"
The total before discount: $50 + $60 = $110 (over $100, so should get 10% off)
Expected after discount: $110 × 0.90 = $99

But the assertion is: `assert discounted.total > 0`

This assertion will pass for:
- $99 (correct 10% discount) ✓
- $110 (no discount applied) ✓
- $1 (99% discount) ✓
- $1,000,000 (added a million dollars) ✓

The test passes for virtually ANY non-negative result. It doesn't verify the discount was applied, it doesn't verify the discount amount, and it doesn't verify the calculation is correct.

**The test is worse than useless — it gives false confidence.** Someone could completely break the discount function and this test would still pass.

**My error:** I wrote a test that asserts something trivially true instead of asserting the actual business requirement. The test "passes" but tests nothing meaningful.

**Category of error:** Tautological assertion — the test's assertion is so weak it can never fail.

**Why this happens:** "Write a test" was interpreted as "write code that looks like a test" rather than "verify the specific behavior claimed in the test name."
</think>

**The test passes but tests nothing.** `assert discounted.total > 0` is true for virtually any result — it doesn't verify the discount was actually applied.

## What the Test Claims vs What It Checks

```python
def test_bulk_discount():
    """Test that orders over $100 get a 10% discount."""
    order = Order(items=[Item(price=50), Item(price=60)])  # Total: $110
    discounted = apply_discount(order)
    assert discounted.total > 0  # ← THIS IS THE PROBLEM

# This assertion passes for:
#   $99.00 — correct (10% off $110) ✓
#   $110.00 — no discount applied ✓ (still > 0)
#   $55.00 — 50% discount ✓ (still > 0)
#   $0.01 — 99.99% discount ✓ (still > 0)
#   $999.00 — added money ✓ (still > 0)

# The ONLY way this test fails: total is 0 or negative
# That's not testing the discount — it's testing that prices exist
```

## The Fix: Assert the Specific Expected Value

```python
def test_bulk_discount_applied_over_100():
    """Orders over $100 should receive a 10% discount."""
    order = Order(items=[Item(price=50), Item(price=60)])  # Total: $110
    discounted = apply_discount(order)
    assert discounted.total == 99.00  # Exactly $110 × 0.90

def test_no_discount_under_100():
    """Orders under $100 should NOT receive a discount."""
    order = Order(items=[Item(price=30), Item(price=40)])  # Total: $70
    discounted = apply_discount(order)
    assert discounted.total == 70.00  # No discount applied

def test_discount_at_boundary():
    """Order at exactly $100 should receive the discount."""
    order = Order(items=[Item(price=50), Item(price=50)])  # Total: $100
    discounted = apply_discount(order)
    assert discounted.total == 90.00  # 10% off $100
```

## The Mutation Test

A good way to check if your test is meaningful: **mutate the code and see if the test catches it.**

```python
# If I change apply_discount to:
def apply_discount(order):
    return order  # Bug: no discount applied at all!

# Original test: assert discounted.total > 0  → PASSES (test is useless)
# Fixed test: assert discounted.total == 99.00 → FAILS (test catches the bug)
```

**Lesson:** a test's value comes from its assertion, not its setup. Ask yourself: "What could go wrong that this test would NOT catch?" If the answer is "everything," the test is useless.'''
    ),
    (
        "thinking/meta-error-overengineered-solution",
        "A user asked me how to check if a string contains only digits in Python. I gave them this answer. Was it appropriate?\n\n```python\nimport re\nfrom typing import Optional\n\nclass StringValidator:\n    _digit_pattern = re.compile(r'^\\d+$')\n    \n    @classmethod\n    def is_numeric(cls, value: Optional[str]) -> bool:\n        if value is None:\n            return False\n        if not isinstance(value, str):\n            raise TypeError(f'Expected str, got {type(value).__name__}')\n        return bool(cls._digit_pattern.match(value))\n\n# Usage:\nif StringValidator.is_numeric(user_input):\n    ...\n```",
        r'''<think>
Let me re-examine whether this answer was appropriate for the question asked.

**The question:** "How to check if a string contains only digits in Python?"

**My answer:** A class with a compiled regex, type checking, None handling, and a classmethod.

**The simplest correct answer:**

```python
my_string.isdigit()  # Built-in string method
```

One line. Built into Python. Does exactly what they asked.

Or if they need to handle None/empty:
```python
my_string and my_string.isdigit()
```

**What I over-engineered:**
1. Created a class for a one-line check
2. Used compiled regex when `str.isdigit()` exists
3. Added type checking that's unnecessary in normal Python code
4. Added Optional handling that wasn't asked for
5. Made it a classmethod for no reason

**My error:** I solved a 1-line problem with a 15-line solution. I added complexity that doesn't serve the user's actual need.

**Category of error:** Over-engineering / YAGNI violation. I built an abstraction for something that doesn't need one.

**Why this happens:** It feels "professional" to write classes, add type checks, and handle edge cases. But for a simple question, the best answer is the simplest one that's correct.
</think>

**No, this is massively over-engineered.** The correct answer is one line:

```python
my_string.isdigit()  # Built-in Python method. Done.
```

## What I Got Wrong

```python
# THE QUESTION: "How to check if a string contains only digits?"
# SIMPLEST CORRECT ANSWER: my_string.isdigit()

# MY ANSWER: 15 lines, a class, compiled regex, type checking, None handling
# This is like building a car when someone asked for directions to the store.

# Unnecessary components:
# ✗ Class (StringValidator) — no state, no reason for a class
# ✗ Compiled regex — str.isdigit() already exists
# ✗ @classmethod — adds ceremony, no benefit
# ✗ Optional[str] type hint — over-engineering for this context
# ✗ isinstance check — Python is duck-typed, this is unusual
# ✗ None handling — wasn't asked for
```

## The Right Answer

```python
# Simple question → simple answer:
"12345".isdigit()   # True
"123a5".isdigit()   # False
"".isdigit()        # False
"-123".isdigit()    # False (only digits, no sign)

# If they also need to handle negative numbers:
def is_integer(s):
    return s.lstrip('-').isdigit() and s != '-'

# If they need to handle floats:
def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False
```

## The Lesson

```
MATCH THE SOLUTION TO THE PROBLEM:

  Simple question → simple answer
  "How do I check for digits?" → str.isdigit()

  Complex question → measured answer
  "How do I validate all user inputs across our API?" →
  Then a validation class might be appropriate.

SIGNS YOU'RE OVER-ENGINEERING:
  □ You created a class for something a function does
  □ You used a library for something built-in
  □ You added error handling the user didn't ask about
  □ Your answer is 10x longer than the simplest correct answer
  □ You'd need comments to explain why the complexity exists
```

**Lesson:** the best answer to a simple question is a simple answer. Over-engineering a response doesn't make it more helpful — it makes it harder to understand and use.'''
    ),
    (
        "thinking/meta-error-memory-model-confusion",
        "I wrote this function to remove duplicates from a list while preserving order. But when the caller checks their original list afterward, it's been modified too! What went wrong?\n\n```python\ndef remove_duplicates(lst):\n    seen = set()\n    i = 0\n    while i < len(lst):\n        if lst[i] in seen:\n            lst.pop(i)\n        else:\n            seen.add(lst[i])\n            i += 1\n    return lst\n```",
        r'''<think>
Let me re-examine this code critically.

The function modifies the input list IN PLACE by calling `lst.pop(i)`. Then it returns `lst` — the same object.

```python
original = [1, 2, 3, 2, 1]
result = remove_duplicates(original)
# result is [1, 2, 3] ✓
# BUT: original is ALSO [1, 2, 3] ← surprise!
# result IS original (same object in memory)
```

In Python, lists are passed by reference (more precisely, the reference is passed by value). The function receives a reference to the SAME list object, not a copy. Calling `.pop()` on the parameter modifies the original list.

**The caller's expectation:**
```python
data = [1, 2, 3, 2, 1]
unique = remove_duplicates(data)
print(data)  # Expected: [1, 2, 3, 2, 1] — still has original data
              # Actual: [1, 2, 3] — original was mutated!
```

**My error:** I mutated the input list instead of creating a new one. This violates the principle of least surprise — a function called `remove_duplicates` that takes a list and returns a list LOOKS like it returns a new list, but it actually destroys the input.

**Category of error:** Unexpected mutation / pass-by-reference confusion. The function has a hidden side effect.

**Why this is dangerous:** The caller might still need the original data. This mutation can cause bugs far from where `remove_duplicates` was called, making debugging very difficult.
</think>

**The function mutates the original list.** Python passes lists by reference, so `lst.pop(i)` modifies the caller's data.

## The Bug

```python
data = [1, 2, 3, 2, 1]
unique = remove_duplicates(data)

print(unique)  # [1, 2, 3] — looks correct
print(data)    # [1, 2, 3] — SURPRISE! original is destroyed

# Even worse: `unique IS data` (same object in memory)
# The caller's original data is gone forever
```

## The Fix: Return a New List

```python
# ✅ CORRECT: create a new list, don't modify the input
def remove_duplicates(lst):
    seen = set()
    result = []
    for item in lst:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result

# Now:
data = [1, 2, 3, 2, 1]
unique = remove_duplicates(data)
print(unique)  # [1, 2, 3]
print(data)    # [1, 2, 3, 2, 1] — original preserved ✓

# Even simpler (Python 3.7+, dicts preserve insertion order):
def remove_duplicates(lst):
    return list(dict.fromkeys(lst))
```

## Why This Error Is Insidious

```python
# The bug might not appear at the call site:
def process_report(transactions):
    unique = remove_duplicates(transactions)  # Silently destroys transactions
    summary = generate_summary(unique)

    # LATER in the code:
    all_count = len(transactions)  # Expected: original count
                                   # Actual: deduplicated count!
    unique_count = len(unique)
    dup_rate = 1 - (unique_count / all_count)  # Always 0! Bug!
```

**Lesson:** functions should either mutate the input (in-place operation, like `list.sort()`) OR return a new value (like `sorted()`), but be clear about which they do. A function that both mutates AND returns the same object is confusing. Name in-place mutations clearly (e.g., `remove_duplicates_inplace`) or, better, return new objects by default.'''
    ),
    (
        "thinking/meta-error-api-design-inconsistency",
        "I designed these API endpoints. Looking at them again, do they follow good REST conventions?\n\n```\nGET /api/getUsers\nPOST /api/createUser\nGET /api/user/123/orders\nPUT /api/updateOrder/456\nDELETE /api/orders/delete/789\nGET /api/search-products?q=laptop\nPOST /api/user/123/add-to-cart\n```",
        r'''<think>
Let me critically examine these API endpoints against REST conventions.

**Issues I can spot:**

1. **Verbs in URLs:** REST uses HTTP methods for actions, not URL paths.
   - `GET /api/getUsers` → should be `GET /api/users`
   - `POST /api/createUser` → should be `POST /api/users`
   - `PUT /api/updateOrder/456` → should be `PUT /api/orders/456`
   - `DELETE /api/orders/delete/789` → should be `DELETE /api/orders/789`
   - `POST /api/user/123/add-to-cart` → should be `POST /api/users/123/cart`

2. **Inconsistent pluralization:**
   - `/api/getUsers` (plural)
   - `/api/user/123/orders` (singular user, plural orders)
   - `/api/orders/delete/789` (plural)
   Pick one: always plural or always singular. Convention: always plural.

3. **Inconsistent naming style:**
   - `getUsers` (camelCase)
   - `search-products` (kebab-case)
   - `add-to-cart` (kebab-case)
   - `createUser` (camelCase)
   Pick one: URLs should use kebab-case (convention).

4. **Redundant action in URL:**
   - `DELETE /api/orders/delete/789` → DELETE already means delete
   - `GET /api/getUsers` → GET already means get
   The HTTP method IS the verb.

**Category of error:** Inconsistent API design — mixing conventions, redundant information, non-RESTful patterns.

**Why this happens:** Each endpoint was added at a different time by different people without a style guide.
</think>

**No, these have several REST convention violations.** Let me enumerate them.

## The Problems

```
ORIGINAL:                          ISSUE:
GET /api/getUsers                  Verb in URL (GET already means "get")
POST /api/createUser               Verb in URL (POST already means "create")
GET /api/user/123/orders           Inconsistent: "user" singular, elsewhere plural
PUT /api/updateOrder/456           Verb in URL + camelCase
DELETE /api/orders/delete/789      Redundant "delete" (DELETE method IS delete)
GET /api/search-products?q=laptop  Verb in URL + kebab-case (inconsistent)
POST /api/user/123/add-to-cart     Verb in URL + singular "user"
```

## The Corrected Version

```
GET    /api/users                   ← List users
POST   /api/users                   ← Create user
GET    /api/users/123               ← Get specific user
PUT    /api/users/123               ← Update user
DELETE /api/users/123               ← Delete user
GET    /api/users/123/orders        ← Get user's orders
GET    /api/orders/456              ← Get specific order
PUT    /api/orders/456              ← Update order
DELETE /api/orders/789              ← Delete order
GET    /api/products?q=laptop       ← Search products (search is a filter, not an action)
POST   /api/users/123/cart/items    ← Add item to cart
```

## The REST Principles Applied

```
1. NOUNS, NOT VERBS in URLs
   HTTP method IS the verb:
   GET = read, POST = create, PUT = update, DELETE = delete
   The URL identifies the RESOURCE, not the action.
   ✗ /api/getUsers     → ✓ GET /api/users
   ✗ /api/deleteOrder  → ✓ DELETE /api/orders/123

2. CONSISTENT PLURALIZATION
   Pick plural (convention) and stick with it:
   /api/users, /api/orders, /api/products
   NOT: /api/user (singular) mixed with /api/orders (plural)

3. CONSISTENT CASING
   URLs use kebab-case or lowercase (convention):
   /api/order-items  NOT /api/orderItems

4. HIERARCHICAL RESOURCES
   /api/users/123/orders  ← orders belonging to user 123
   /api/orders/456/items  ← items belonging to order 456

5. USE QUERY PARAMETERS FOR FILTERING
   /api/products?q=laptop&category=electronics&sort=price
   NOT: /api/search-products
```

**Lesson:** REST API design should be consistent and predictable. A developer using your API should be able to guess the endpoint for a new resource without reading documentation. Establish conventions early and enforce them with linting or code review.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
