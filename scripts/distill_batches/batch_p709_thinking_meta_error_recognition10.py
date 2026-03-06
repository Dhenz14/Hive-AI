"""Phase 3A: Metacognition — Error Recognition in Own Output (Part 10)
Scenarios: Wrong database design, wrong error patterns, logic edge cases
"""

PAIRS = [
    (
        "thinking/meta-error-wrong-boolean-flag-status",
        r'''I designed my orders table with boolean flags for status:

```sql
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    total DECIMAL(10,2) NOT NULL,
    is_paid BOOLEAN DEFAULT FALSE,
    is_shipped BOOLEAN DEFAULT FALSE,
    is_delivered BOOLEAN DEFAULT FALSE,
    is_cancelled BOOLEAN DEFAULT FALSE,
    is_refunded BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

This lets me track each stage of the order. Good design?''',
        r'''<think>
Let me think about the implications of boolean flags for order status...

Problems:

1. **Impossible states**: Can an order be both `is_cancelled = TRUE` and `is_shipped = TRUE`? What about `is_refunded = TRUE` and `is_delivered = FALSE`? With 5 booleans, there are 2^5 = 32 possible states, but only a few make sense:
   - paid=F, shipped=F, delivered=F, cancelled=F, refunded=F (new order)
   - paid=T, shipped=F, delivered=F, cancelled=F, refunded=F (paid)
   - paid=T, shipped=T, delivered=F, cancelled=F, refunded=F (shipped)
   - paid=T, shipped=T, delivered=T, cancelled=F, refunded=F (delivered)
   - paid=F, shipped=F, delivered=F, cancelled=T, refunded=F (cancelled)

   Maybe ~8 valid combinations out of 32. The other 24 are nonsensical but nothing prevents them.

2. **No transition history**: When was it shipped? When was it delivered? The booleans only capture current state, not when transitions happened.

3. **Complex queries**: "Find orders ready to ship" requires `WHERE is_paid = TRUE AND is_shipped = FALSE AND is_cancelled = FALSE`. Each new flag makes queries more complex.

4. **Race conditions**: Two processes could set different flags simultaneously, creating an invalid state.

5. **No business rule enforcement**: Nothing prevents setting `is_delivered = TRUE` without `is_shipped = TRUE`.

The correct design: a single `status` enum column plus a status history table.

My error: I modeled a STATE MACHINE (order lifecycle) as independent boolean flags. These flags are actually NOT independent — they represent sequential stages with specific valid transitions.
</think>

**Boolean flags create 32 possible states when only ~8 are valid, with no enforcement of valid transitions.**

### Impossible states this allows
```sql
-- These can all exist with boolean flags:
is_paid=F, is_shipped=T     -- shipped without payment?
is_delivered=T, is_shipped=F -- delivered without shipping?
is_cancelled=T, is_shipped=T -- cancelled but shipped?
is_refunded=T, is_paid=F    -- refunded without payment?
```

### Fix: enum status + history table
```sql
CREATE TYPE order_status AS ENUM (
    'pending', 'paid', 'processing', 'shipped',
    'delivered', 'cancelled', 'refunded'
);

CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    total DECIMAL(10,2) NOT NULL,
    status order_status NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Track all transitions with timestamps
CREATE TABLE order_status_history (
    id SERIAL PRIMARY KEY,
    order_id INTEGER REFERENCES orders(id),
    from_status order_status,
    to_status order_status NOT NULL,
    changed_at TIMESTAMP DEFAULT NOW(),
    changed_by INTEGER REFERENCES users(id),
    reason TEXT
);
```

### Benefits
```sql
-- Simple queries:
SELECT * FROM orders WHERE status = 'paid';  -- ready to process

-- vs boolean version:
SELECT * FROM orders
WHERE is_paid = TRUE AND is_shipped = FALSE
AND is_cancelled = FALSE AND is_refunded = FALSE;

-- When was it shipped?
SELECT changed_at FROM order_status_history
WHERE order_id = 123 AND to_status = 'shipped';
```

### Enforce valid transitions in code
```python
VALID_TRANSITIONS = {
    'pending': ['paid', 'cancelled'],
    'paid': ['processing', 'refunded', 'cancelled'],
    'processing': ['shipped', 'cancelled'],
    'shipped': ['delivered'],
    'delivered': ['refunded'],
    'cancelled': [],
    'refunded': [],
}

def update_status(order, new_status):
    if new_status not in VALID_TRANSITIONS[order.status]:
        raise ValueError(f"Cannot transition from {order.status} to {new_status}")
    order.status = new_status
```

### The meta-lesson
When boolean flags represent stages of a lifecycle, they're modeling a state machine with independent flags — but the states aren't independent. Use an enum column for current state and a history table for transitions. This makes impossible states unrepresentable, queries simple, and audit trails automatic.'''
    ),
    (
        "thinking/meta-error-logic-timezone-comparison",
        r'''I wrote this function to check if a subscription has expired:

```python
from datetime import datetime

def is_expired(expiry_date):
    return datetime.now() > expiry_date
```

Simple comparison. Any issues?''',
        r'''<think>
Let me think about datetime comparisons...

`datetime.now()` returns a NAIVE datetime — no timezone information. `expiry_date` could be:
1. A naive datetime (no timezone) — comparison works, but both times are ambiguous
2. A timezone-aware datetime — `TypeError: can't compare offset-naive and offset-aware datetimes`

So if the expiry date comes from a database that stores UTC timestamps (common), and it includes timezone info, this code CRASHES.

But even if both are naive, there's a bigger problem: WHICH timezone is `datetime.now()` in? It returns the server's LOCAL time. If the server is in UTC but the expiry date was stored in US Eastern time (or vice versa), the comparison is wrong by hours.

Scenario:
- User in New York (EST, UTC-5) has subscription expiring at "2024-03-15 23:59:59 EST"
- Server in UTC: `datetime.now()` returns "2024-03-16 04:59:59" (UTC)
- If expiry_date is stored naively as "2024-03-15 23:59:59" (no timezone), and the server's now() is "2024-03-16 04:59:59"...
- The comparison says expired (now > expiry) but the user still has ~hours left in their timezone

The fix: ALWAYS use timezone-aware datetimes, and ALWAYS compare in UTC.

```python
from datetime import datetime, timezone

def is_expired(expiry_date):
    now = datetime.now(timezone.utc)
    # Ensure expiry_date is also UTC-aware
    return now > expiry_date
```

And store all dates in UTC in the database.
</think>

**`datetime.now()` is timezone-naive and returns server-local time, making this comparison unreliable across timezones.**

### The bugs

**1. Crashes with timezone-aware dates:**
```python
from datetime import datetime, timezone

expiry = datetime(2024, 3, 15, tzinfo=timezone.utc)
datetime.now() > expiry
# TypeError: can't compare offset-naive and offset-aware datetimes
```

**2. Wrong results across timezones:**
```python
# Server in UTC, expiry stored in EST (no timezone info):
# Server datetime.now() = 2024-03-16 01:00 (UTC)
# Expiry = 2024-03-15 23:00 (meant to be EST = 2024-03-16 04:00 UTC)
# now() > expiry → True, but subscription has 3 hours left!
```

**3. DST transitions:**
```python
# During "spring forward": 2:00 AM jumps to 3:00 AM
# datetime.now() could skip an hour, expiring subscriptions early
```

### Fix: always use UTC
```python
from datetime import datetime, timezone

def is_expired(expiry_date: datetime) -> bool:
    now = datetime.now(timezone.utc)
    if expiry_date.tzinfo is None:
        raise ValueError("expiry_date must be timezone-aware")
    return now > expiry_date
```

### The golden rule
```python
# Store: always UTC
created_at = datetime.now(timezone.utc)

# Display: convert to user's timezone for presentation only
from zoneinfo import ZoneInfo
user_tz = ZoneInfo("America/New_York")
display_time = created_at.astimezone(user_tz)
```

### The meta-lesson
`datetime.now()` without a timezone is a bug waiting to happen. It silently uses server-local time, which varies by deployment. Always use `datetime.now(timezone.utc)` and store/compare in UTC. Convert to local time only for display.'''
    ),
    (
        "thinking/meta-error-wrong-default-mutable-arg",
        r'''A junior developer showed me this bug they can't figure out:

```python
def add_item(item, items=[]):
    items.append(item)
    return items

# First call
result1 = add_item("apple")
print(result1)  # ['apple'] ✓

# Second call
result2 = add_item("banana")
print(result2)  # Expected: ['banana'], Got: ['apple', 'banana'] ???

# Third call
result3 = add_item("cherry")
print(result3)  # Expected: ['cherry'], Got: ['apple', 'banana', 'cherry'] ???
```

I looked at it quickly and said "Python must have a bug." Let me reconsider...''',
        r'''<think>
Wait, I said "Python must have a bug"? That's almost never the right conclusion. Let me think about this more carefully.

This is the classic mutable default argument trap in Python.

When Python defines the function `def add_item(item, items=[])`, it evaluates the default argument `[]` ONCE at function definition time, not at each call. So there's ONE list object that serves as the default for ALL calls.

- Call 1: `items` defaults to that ONE list, which is empty → appends "apple" → `["apple"]`
- Call 2: `items` defaults to THE SAME list, now `["apple"]` → appends "banana" → `["apple", "banana"]`
- Call 3: same list, now has both → appends "cherry" → all three

The default argument `[]` is created once and shared across all invocations. This is a well-known Python gotcha, not a language bug.

My error was classic: I blamed the language instead of examining my own misunderstanding. The correct mental model is: default arguments are evaluated ONCE at def-time, not at call-time.

The fix:
```python
def add_item(item, items=None):
    if items is None:
        items = []
    items.append(item)
    return items
```

Use `None` as the sentinel and create a new list inside the function body.
</think>

**This is not a Python bug — it's the mutable default argument trap. Default arguments are evaluated ONCE at function definition time, not per call.**

### What happens internally
```python
# At definition time, Python creates ONE list object:
def add_item(item, items=[]):  # items defaults to SAME list every call
    items.append(item)
    return items

# All calls without explicit items share that ONE list:
add_item("apple")   # appends to the shared list → ["apple"]
add_item("banana")  # SAME list → ["apple", "banana"]
add_item("cherry")  # SAME list → ["apple", "banana", "cherry"]
```

You can see the shared object:
```python
add_item.__defaults__  # (['apple', 'banana', 'cherry'],)
```

### The fix: use None sentinel
```python
def add_item(item, items=None):
    if items is None:
        items = []  # new list created each call
    items.append(item)
    return items
```

### Other mutable defaults to avoid
```python
# BAD                          # GOOD
def f(data={}):                def f(data=None):
    ...                            data = data if data is not None else {}

def f(seen=set()):             def f(seen=None):
    ...                            seen = seen if seen is not None else set()

def f(config={"debug": True}): def f(config=None):
    ...                            config = config or {"debug": True}
```

### My meta-error
I blamed the language ("Python must have a bug") instead of questioning my own assumptions. Languages with millions of users don't have bugs in basic function calls — when something seems broken, the problem is almost always in our mental model, not the language. The correct response is: "I must be misunderstanding something. Let me read the docs."'''
    ),
    (
        "thinking/meta-error-wrong-recursion-no-base",
        r'''I wrote this recursive function to flatten nested lists:

```python
def flatten(nested):
    result = []
    for item in nested:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result

# Test
print(flatten([1, [2, [3, 4]], [5, 6]]))
# Output: [1, 2, 3, 4, 5, 6] ✓
```

This works perfectly. Any issues?''',
        r'''<think>
Let me think about edge cases and potential problems...

The function works for the test case. Let me think about what could go wrong:

1. **Circular references**: What if the list contains itself?
```python
lst = [1, 2]
lst.append(lst)
flatten(lst)  # RecursionError: maximum recursion depth exceeded
```
The function has no protection against circular references. It would recurse infinitely.

2. **Deep nesting**: Even without circular references, deeply nested lists hit Python's recursion limit:
```python
deeply_nested = [1]
for _ in range(1000):
    deeply_nested = [deeply_nested]
flatten(deeply_nested)  # RecursionError at ~1000 depth
```

3. **isinstance(item, list) is too narrow**: What about tuples, generators, sets, or other iterables? `flatten([1, (2, 3), {4, 5}])` would return `[1, (2, 3), {4, 5}]` — tuples and sets aren't flattened.

Should it handle all iterables? Maybe. But strings are iterable too — `flatten(["hello"])` should return `["hello"]`, not `["h", "e", "l", "l", "o"]`.

4. **Not a generator**: The function builds the entire result in memory. For very large nested structures, this could use lots of memory. A generator version would be more memory-efficient.

5. **Empty list**: `flatten([])` → `[]`. This works fine.

So the main issues are:
- Crashes on circular references (infinite recursion)
- Crashes on deeply nested structures (recursion limit)
- Only handles `list` type, not other iterables
- No memory efficiency for large structures

The test case was too simple to reveal these issues.
</think>

**The function works for simple cases but crashes on circular references and deep nesting, and only handles `list` type.**

### Bug 1: Infinite recursion on circular references
```python
lst = [1, 2]
lst.append(lst)  # lst = [1, 2, [1, 2, [1, 2, ...]]]
flatten(lst)     # RecursionError! Infinite loop.
```

### Bug 2: RecursionError on deep nesting
```python
nested = [1]
for _ in range(1000):
    nested = [nested]
flatten(nested)  # RecursionError: maximum recursion depth exceeded
```

### Bug 3: Only handles `list`, not other iterables
```python
flatten([1, (2, 3), {4, 5}])  # [1, (2, 3), {4, 5}] — tuples/sets not flattened
```

### Robust version
```python
def flatten(nested, _seen=None):
    if _seen is None:
        _seen = set()

    obj_id = id(nested)
    if obj_id in _seen:
        return []  # circular reference detected
    _seen.add(obj_id)

    result = []
    for item in nested:
        if isinstance(item, (list, tuple)):
            result.extend(flatten(item, _seen))
        else:
            result.append(item)

    _seen.discard(obj_id)
    return result
```

### Iterative version (no recursion limit)
```python
def flatten_iterative(nested):
    stack = list(reversed(nested))
    result = []
    seen = set()
    while stack:
        item = stack.pop()
        if isinstance(item, (list, tuple)):
            if id(item) not in seen:
                seen.add(id(item))
                stack.extend(reversed(item))
        else:
            result.append(item)
    return result
```

### The meta-lesson
Recursive functions need to handle: (1) circular references that cause infinite loops, (2) deep nesting that exceeds recursion limits, and (3) the full range of input types. A single happy-path test doesn't prove correctness — always test with adversarial inputs: self-referencing structures, empty inputs, deeply nested inputs, and unexpected types.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
