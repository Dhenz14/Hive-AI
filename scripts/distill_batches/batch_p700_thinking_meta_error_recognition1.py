"""Phase 3A: Metacognition — Error Recognition in Own Output (Part 1)"""

PAIRS = [
    (
        "thinking/meta-error-off-by-one-loop",
        "I previously wrote this function to get the last N elements of a list. Looking at it again, is it correct?\n\n```python\ndef last_n(lst, n):\n    return lst[len(lst) - n - 1:]\n```",
        r'''<think>
Let me re-examine this code critically.

The function should return the last N elements of a list.

Example: last_n([1, 2, 3, 4, 5], 3) should return [3, 4, 5]

Let me trace through:
- lst = [1, 2, 3, 4, 5], n = 3
- len(lst) = 5
- 5 - 3 - 1 = 1
- lst[1:] = [2, 3, 4, 5]

That returns 4 elements, not 3! Off-by-one error.

The correct slice should be lst[len(lst) - n:] or simply lst[-n:].

Let me verify: lst[-3:] = [3, 4, 5] ✓

Also, what about edge cases?
- n = 0: lst[-0:] = lst[0:] = entire list! That's wrong.
- n > len(lst): lst[-10:] when len is 5 → returns [1,2,3,4,5] — actually that works in Python, returns the full list.
- n = 0 needs special handling.

**My error:** the `-1` in `len(lst) - n - 1` is wrong. I was probably thinking of index-based access (where the last element is at index len-1), but for slicing, we want position len-n as the start.

**Category of error:** Off-by-one, caused by confusing index access with slice boundaries.

**Why I made this mistake:** When computing indices manually, it's easy to mix up whether you need -1 (for 0-based indexing) or not (for slicing). Python slicing is already designed so that lst[-n:] does exactly what we want.
</think>

**No, there's an off-by-one error.** The `-1` is incorrect.

## The Bug

```python
def last_n(lst, n):
    return lst[len(lst) - n - 1:]  # ← the -1 is wrong

# Trace: last_n([1, 2, 3, 4, 5], 3)
# len(lst) - n - 1 = 5 - 3 - 1 = 1
# lst[1:] = [2, 3, 4, 5]  ← returns 4 elements, not 3!
```

## The Fix

```python
# Simplest correct version:
def last_n(lst, n):
    if n == 0:
        return []
    return lst[-n:]

# Trace: last_n([1, 2, 3, 4, 5], 3)
# lst[-3:] = [3, 4, 5] ✓

# Edge cases:
# last_n([1, 2, 3], 0) → []  ✓ (special case: -0 would give full list)
# last_n([1, 2, 3], 5) → [1, 2, 3]  ✓ (Python handles gracefully)
# last_n([], 3) → []  ✓
```

## Why This Error Happens

The `-1` comes from confusing **index access** with **slice boundaries**:
- Index: `lst[len(lst) - 1]` gets the last element (0-based, need -1)
- Slice: `lst[len(lst) - n:]` gets last N elements (no -1 needed)

**Lesson:** when working with indices and slices in Python, prefer negative indexing (`lst[-n:]`) over manual arithmetic. It's clearer and less error-prone.'''
    ),
    (
        "thinking/meta-error-sql-injection-in-validation",
        "I wrote this input validation function for a search endpoint. Looking at it again, is it safe?\n\n```python\ndef search_products(query, sort_by='name'):\n    # Validate sort_by to prevent injection\n    allowed_sorts = ['name', 'price', 'rating']\n    if sort_by not in allowed_sorts:\n        sort_by = 'name'\n    \n    # Build and execute query\n    sql = f\"SELECT * FROM products WHERE name LIKE '%{query}%' ORDER BY {sort_by}\"\n    return db.execute(sql)\n```",
        r'''<think>
Let me re-examine this code critically from a security perspective.

Two parts to analyze:
1. `sort_by` validation: the whitelist approach is correct — only allowed values pass.
2. `query` parameter: this is DIRECTLY interpolated into the SQL string with f-string formatting!

```python
sql = f"SELECT * FROM products WHERE name LIKE '%{query}%' ORDER BY {sort_by}"
```

If query = `'; DROP TABLE products; --`:
```sql
SELECT * FROM products WHERE name LIKE '%'; DROP TABLE products; --%' ORDER BY name
```
→ SQL injection! The products table is dropped.

**The irony:** I correctly validated `sort_by` against injection but then used string interpolation for `query` — the very same vulnerability I was supposedly protecting against!

**My error:** I focused on the obvious injection vector (sort_by, which comes from a parameter name) but missed the more dangerous one (query, which is user-provided text). This is a classic case of security theater — protecting one door while leaving another wide open.

**Category of error:** Security vulnerability caused by inconsistent defense. Applied the right pattern (whitelist) to the less dangerous input but forgot to parameterize the more dangerous one.

**Meta-analysis:** This mistake happens when you're thinking about security as a specific fix ("validate sort_by") rather than as a principle ("never interpolate user input into SQL").
</think>

**The `sort_by` validation is correct, but `query` has a SQL injection vulnerability.** You protected one input but left the other wide open.

## The Bug

```python
# sort_by: properly validated with whitelist ✓
# query: directly interpolated into SQL with f-string ✗

sql = f"SELECT * FROM products WHERE name LIKE '%{query}%' ORDER BY {sort_by}"
#                                              ^^^^^^^^
#                                              SQL INJECTION!

# Attack: query = "'; DROP TABLE products; --"
# Result: SELECT * FROM products WHERE name LIKE '%'; DROP TABLE products; --%'
```

## The Fix

```python
def search_products(query, sort_by='name'):
    # Validate sort_by (whitelist — correct approach, keep it)
    allowed_sorts = ['name', 'price', 'rating']
    if sort_by not in allowed_sorts:
        sort_by = 'name'

    # Parameterize the query (NEVER use f-strings for SQL)
    sql = f"SELECT * FROM products WHERE name LIKE %s ORDER BY {sort_by}"
    #      sort_by is safe (whitelisted)     ^^^^ query is parameterized
    return db.execute(sql, [f"%{query}%"])
```

## Why This Error Is Dangerous

The code gives a **false sense of security**. Someone reviewing this code might think: "They validated against injection, looks safe." But the validation only covers `sort_by` — the `query` parameter, which is the actual user input, is completely unprotected.

**The principle:** security must be applied **consistently** to ALL user inputs, not just the ones you happen to think of. Use parameterized queries as the default, not as a special case.

**Lesson:** when writing SQL, the rule is simple — **never use string formatting (f-strings, .format(), %, +) for ANY user input**. Always parameterize with `%s` or `?` placeholders.'''
    ),
    (
        "thinking/meta-error-race-condition-counter",
        "I wrote this hit counter for my web app. It seems to lose counts under heavy traffic. Can you spot the issue?\n\n```python\nimport threading\n\nclass HitCounter:\n    def __init__(self):\n        self.count = 0\n    \n    def increment(self):\n        current = self.count\n        self.count = current + 1\n    \n    def get_count(self):\n        return self.count\n```",
        r'''<think>
Let me re-examine this critically for concurrency issues.

The `increment` method:
```python
def increment(self):
    current = self.count     # Read
    self.count = current + 1  # Write
```

This is a classic read-modify-write race condition. Between the read and the write, another thread can also read the same value.

Trace with two threads:
```
Thread A: current = self.count  → reads 42
Thread B: current = self.count  → reads 42 (same value!)
Thread A: self.count = 42 + 1   → writes 43
Thread B: self.count = 42 + 1   → writes 43 (overwrites!)
```

Both threads read 42, both write 43. Two increments, but count only went up by 1. One count is lost.

**In Python specifically:** Even though Python has the GIL, `self.count = current + 1` is NOT atomic. The GIL can release between the read (`current = self.count`) and the write (`self.count = current + 1`) because they're separate bytecode operations.

Actually, even `self.count += 1` is NOT atomic in Python. It compiles to LOAD_ATTR, then BINARY_ADD, then STORE_ATTR — three separate bytecode operations, and the GIL can switch between any of them.

**My error:** Assuming that a simple two-line operation is safe because "it's so fast." Race conditions don't care about speed — they care about atomicity.

**Category of error:** Race condition due to non-atomic read-modify-write operation.
</think>

**Yes, there's a race condition.** The read-modify-write in `increment()` is not atomic — two threads can read the same value and one increment gets lost.

## The Race Condition

```python
def increment(self):
    current = self.count      # STEP 1: Read
    self.count = current + 1  # STEP 2: Write

# Thread A: reads count = 42
# Thread B: reads count = 42  ← same value, before A writes!
# Thread A: writes count = 43
# Thread B: writes count = 43  ← overwrites A's increment!

# Two increments happened, but count only went up by 1.
# Under heavy traffic, this loses hundreds of counts.
```

## The Fixes

```python
import threading

# Fix 1: Use a lock
class HitCounter:
    def __init__(self):
        self.count = 0
        self._lock = threading.Lock()

    def increment(self):
        with self._lock:  # Only one thread can execute this at a time
            self.count += 1

    def get_count(self):
        return self.count

# Fix 2: Use threading.Event / atomic operation (simpler for counters)
from itertools import count as atomic_count
# Actually, Python doesn't have a built-in atomic integer.

# Fix 3: For web apps, use Redis INCR (truly atomic, works across processes)
import redis
r = redis.Redis()

def increment():
    r.incr("hit_counter")  # Atomic, thread-safe, process-safe

def get_count():
    return int(r.get("hit_counter") or 0)
```

## Why This Error Happens

**The intuition trap:** "It's just one line (`self.count += 1`), surely it's atomic." But `+=` in Python compiles to three separate operations (load, add, store), and the thread can be interrupted between any of them.

**Lesson:** any read-modify-write sequence on shared mutable state needs synchronization. This applies to `+=`, `-=`, `append()`, `dict[key] = ...`, and any operation that reads then writes. Either use a lock, an atomic operation, or move the state to a system designed for concurrency (Redis, database).'''
    ),
    (
        "thinking/meta-error-wrong-complexity",
        "I wrote this function and told my team it's O(n). Looking at it again, is my complexity analysis correct?\n\n```python\ndef has_duplicates(lst):\n    for i in range(len(lst)):\n        for j in range(i + 1, len(lst)):\n            if lst[i] == lst[j]:\n                return True\n    return False\n```",
        r'''<think>
Let me re-examine my complexity analysis.

I said this is O(n). Let me recount.

The outer loop runs n times (i from 0 to n-1).
The inner loop runs n-i-1 times for each i.

Total comparisons:
- i=0: n-1 comparisons
- i=1: n-2 comparisons
- i=2: n-3 comparisons
- ...
- i=n-2: 1 comparison
- i=n-1: 0 comparisons

Total = (n-1) + (n-2) + ... + 1 + 0 = n(n-1)/2 = O(n²)

This is clearly O(n²), not O(n). I was wrong.

**Why I might have said O(n):**
- I may have only looked at the outer loop (n iterations) without properly analyzing the inner loop.
- Or I may have thought "it returns early on the first duplicate" — but worst case (no duplicates), it checks ALL pairs.

**The correct O(n) approach:** use a set.

```python
def has_duplicates(lst):
    seen = set()
    for item in lst:
        if item in seen:
            return True
        seen.add(item)
    return False
```

This is genuinely O(n) — single loop, O(1) set lookups.

**Category of error:** Wrong complexity analysis — counted only the outer loop, ignored the inner loop's contribution. Classic mistake of analyzing nested loops as if they were sequential.
</think>

**No, this is O(n²), not O(n).** I miscounted by only looking at the outer loop.

## The Error in My Analysis

```python
for i in range(len(lst)):           # Outer: n iterations
    for j in range(i + 1, len(lst)):  # Inner: n-i-1 iterations
        if lst[i] == lst[j]:
            return True

# Total comparisons:
# i=0: n-1 comparisons
# i=1: n-2 comparisons
# i=2: n-3 comparisons
# ...
# Total = (n-1) + (n-2) + ... + 1 = n(n-1)/2 = O(n²)

# I said O(n) — I was wrong by an entire order of magnitude.
```

## Why I Got It Wrong

I likely only counted the outer loop (n iterations) and didn't properly account for the inner loop running n-i-1 times for each iteration. Nested loops are O(outer × inner), not O(outer + inner).

**The early return doesn't help worst-case analysis:** if the list has no duplicates, we check ALL n(n-1)/2 pairs.

## The Correct O(n) Solution

```python
def has_duplicates(lst):
    seen = set()
    for item in lst:          # O(n) — single loop
        if item in seen:      # O(1) — set lookup
            return True
        seen.add(item)        # O(1) — set insertion
    return False

# Total: O(n) time, O(n) space
# The tradeoff: uses extra memory (the set) for faster time
```

## Practical Impact

```
For a list of 10,000 elements:
  O(n²) version: ~50,000,000 comparisons
  O(n) version:  ~10,000 lookups

For 1,000,000 elements:
  O(n²): ~500,000,000,000 comparisons (minutes to hours)
  O(n):  ~1,000,000 lookups (milliseconds)
```

**Lesson:** when analyzing complexity, count the **total work across all iterations**, not just the number of loop headers. Two nested loops over the same data is almost always O(n²).'''
    ),
    (
        "thinking/meta-error-swallowed-exception",
        "I wrote this error handling for a payment function. Looking at it again, is the error handling correct?\n\n```python\ndef process_payment(order):\n    try:\n        result = payment_api.charge(order.total, order.card_token)\n        order.status = 'paid'\n        order.save()\n        return {'success': True}\n    except Exception:\n        return {'success': False}\n```",
        r'''<think>
Let me re-examine this error handling critically.

**Problems I can see:**

1. **Swallowed exception** — `except Exception` catches everything but logs NOTHING. When payments fail, we'll have no idea WHY.
   - Was it a network timeout?
   - Was the card declined?
   - Was it an API key error?
   - Was it a bug in our code (TypeError, AttributeError)?
   We catch all of these identically and return `{'success': False}`.

2. **Catches too broadly** — `except Exception` catches programming errors (TypeError, AttributeError, NameError) alongside business errors (CardDeclined, InsufficientFunds). If there's a bug in our code (e.g., `order.totl` typo → AttributeError), we silently treat it as a payment failure instead of seeing the crash.

3. **No error message to the user** — the response is just `{'success': False}` with no information about what went wrong. Did the card get declined? Should they try a different card? Should they try again later?

4. **No logging** — when things go wrong in production, there's no trail. "Payment failed" → "Why?" → "We have no idea, the error was swallowed."

5. **Database state might be wrong** — if `payment_api.charge()` succeeds but `order.save()` fails, the customer is charged but the order isn't marked as paid. This should be in a transaction with proper error handling for each step.

**Category of error:** Silent failure / swallowed exception — the worst kind of error handling because it hides problems instead of surfacing them.

**Why I made this mistake:** "Handle errors gracefully" was interpreted as "don't show errors to the user," which became "don't acknowledge errors exist."
</think>

**The error handling is harmful — it's worse than having no try/except at all.** It swallows every error silently, making debugging impossible.

## The Problems

```python
except Exception:            # Problem 1: catches EVERYTHING (bugs too)
    return {'success': False} # Problem 2: no error info logged or returned

# Card declined? {'success': False}
# Network timeout? {'success': False}
# Typo in code (AttributeError)? {'success': False}
# API key expired? {'success': False}
# All look identical. When 100 payments fail at 3 AM,
# you have NO IDEA why. Zero debugging information.
```

## The Fix

```python
import logging

logger = logging.getLogger(__name__)

def process_payment(order):
    try:
        result = payment_api.charge(order.total, order.card_token)
    except payment_api.CardDeclinedError as e:
        # Expected business error — tell the user
        logger.info("Payment declined", extra={"order_id": order.id, "reason": str(e)})
        return {'success': False, 'error': 'card_declined', 'message': str(e)}
    except payment_api.NetworkError as e:
        # Transient error — user can retry
        logger.warning("Payment network error", extra={"order_id": order.id, "error": str(e)})
        return {'success': False, 'error': 'network_error', 'message': 'Please try again'}
    except Exception as e:
        # Unexpected error — this is a BUG, not a payment failure
        logger.error("Unexpected payment error", extra={"order_id": order.id}, exc_info=True)
        return {'success': False, 'error': 'internal_error', 'message': 'Something went wrong'}

    # Only reached if charge succeeded
    try:
        order.status = 'paid'
        order.payment_id = result.id
        order.save()
    except Exception as e:
        # CRITICAL: customer was charged but we can't save the order
        logger.critical("Payment succeeded but order save failed!",
                       extra={"order_id": order.id, "payment_id": result.id}, exc_info=True)
        # Alert on-call engineer immediately
        return {'success': True, 'warning': 'Payment processed, confirmation may be delayed'}

    return {'success': True, 'payment_id': result.id}
```

## The Principle

```
ERROR HANDLING RULES:

1. NEVER catch Exception without logging
   → Silent failures are worse than crashes
   → At least log what went wrong with full context

2. Catch SPECIFIC exceptions, not broad ones
   → CardDeclined (business error) ≠ AttributeError (bug)
   → Handle each differently

3. Include error context in the response
   → "Payment failed" is useless
   → "Card declined: insufficient funds" is actionable

4. Distinguish expected errors from bugs
   → Expected: card declined, timeout → handle gracefully
   → Unexpected: TypeError, KeyError → log, alert, investigate
```

**Lesson:** error handling should make problems **visible**, not invisible. A bare `except Exception: pass` is the software equivalent of unplugging a fire alarm.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
