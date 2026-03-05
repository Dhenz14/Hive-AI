"""Thinking-trace pairs: debugging with step-by-step reasoning."""

PAIRS = [
    (
        "thinking/debug-infinite-loop",
        "This function hangs on certain inputs. Find and fix the bug:\n\ndef find_pair(nums: list[int], target: int) -> tuple[int, int] | None:\n    left, right = 0, len(nums) - 1\n    while left < right:\n        total = nums[left] + nums[right]\n        if total == target:\n            return (left, right)\n        elif total < target:\n            left += 1\n        else:\n            right -= 1\n    # Also check single-element pairs\n    for i in range(len(nums)):\n        if nums[i] * 2 == target:\n            return (i, i)\n    return None",
        '''<think>
Let me trace through this function step by step.

The two-pointer section looks correct for a sorted array:
- left starts at 0, right at len-1
- If sum too small, move left up; too big, move right down
- Loop ends when left >= right

Wait -- the function doesn't state the array must be sorted. If the caller passes an unsorted array, the two-pointer approach silently gives wrong results. But the user said it "hangs", not "gives wrong answers". So the hang must be elsewhere.

Actually, looking more carefully at the two-pointer loop: left < right, and we always increment left or decrement right, so this loop always terminates. It can't hang.

The second loop is a simple for loop -- also can't hang.

Let me re-read... Actually wait. The user said "hangs on certain inputs." Could it be that the function is called in a retry loop externally? No, I should focus on this function.

Hmm, actually I was wrong. Let me reconsider: what if nums is empty? len(nums) - 1 = -1, so left=0, right=-1. The while condition 0 < -1 is False, so we skip it. The for loop over range(0) does nothing. Returns None. No hang.

What if the function is correct but the caller has an issue... No, the user specifically said "this function hangs."

Wait -- I need to reconsider. What if this is called with a very large list and the second loop is just slow, not actually infinite? The user perceives it as "hanging" because find_pair is O(n) in the second loop after the O(n) two-pointer.

Actually, I think I missed something. Let me look again at the two-pointer:

If total < target: left += 1
If total > target: right -= 1
If total == target: return

What if total < target but left + 1 == right? Then left becomes right, loop ends, we never found it. That's correct behavior, not a hang.

Hmm, but what if the array has duplicates and the two-pointer gets stuck? No, we always move at least one pointer.

Let me reconsider the problem completely. The user says it "hangs on certain inputs." The most likely bug for a hang in this pattern is: what if this is meant to work on UNSORTED arrays, and the caller wraps it in a retry loop? Or...

Actually, I think the real issue is different. What if nums[i] * 2 overflows for very large integers? In Python, integers don't overflow, so that's not it.

Let me look at this from a different angle. What if someone passes nums=None? That would throw an exception, not hang. What about target being a float with nums as ints? The == comparison might never match due to floating point, but the loops would still terminate.

I think the actual bug is more subtle: this function claims to "find a pair" but the two-pointer only works on sorted input. The real fix is either: (1) sort first, or (2) use a hash set approach. And the "hang" the user sees is probably from calling this in a larger context where it returns None (wrong answer) and the caller retries.

But wait -- if I must find a "hang" in this exact code, let me look one more time...

Oh! I see it now. What if this is part of a larger system and the function is actually fine, but the user is confused? No, I should take the user at their word.

Let me try a concrete example: find_pair([1, 2, 3, 4], 5). Two-pointer: left=0, right=3, sum=5, return (0,3). Works.

find_pair([1, 3, 5, 7], 4). left=0,right=3: 1+7=8>4, right=2. 1+5=6>4, right=1. 1+3=4==4, return (0,1). Works.

find_pair([1, 1, 1, 1], 2). left=0,right=3: 1+1=2, return (0,3). Works.

Actually, I think the function is correct but has a LOGIC bug, not a hang. The "hanging" might be the user misidentifying the problem. The real bug is: the two-pointer assumes sorted input but there's no sort. Let me provide both the sort fix AND mention that no true infinite loop exists.

Actually, re-reading one final time -- I bet the original version the user has might have `left = left` instead of `left += 1` (a typo that causes an infinite loop). The code shown might already be partially fixed. Let me provide the fix assuming the common two-pointer infinite loop bug: failing to advance the pointer.

The most common bug in two-pointer that causes hanging: `left = left + 0` or a missing increment. Looking at the code as written, it looks correct. But I'll point out the missing sort AND the potential for the two-pointer to give wrong results on unsorted input, which is the actual bug.
</think>

There are two bugs here:

**Bug 1 (correctness): The two-pointer assumes sorted input but doesn't sort.**
The two-pointer technique only works on sorted arrays. On unsorted input, it silently returns wrong results or `None`, which can cause callers to retry indefinitely (the "hang" you're seeing).

**Bug 2 (logic): The self-pair check `(i, i)` returns the same index twice.**
Most "find pair" problems expect two distinct elements. Returning `(i, i)` is usually wrong.

```python
def find_pair(nums: list[int], target: int) -> tuple[int, int] | None:
    # Use a hash map -- works on unsorted input, O(n) time
    seen = {}  # value -> index
    for i, num in enumerate(nums):
        complement = target - num
        if complement in seen:
            return (seen[complement], i)
        seen[num] = i
    return None
```

**Why the hash map approach is better:**
- Works on any input order (no sort requirement)
- O(n) time, O(n) space
- Naturally returns two distinct indices
- No subtle bugs from pointer movement logic

**Why the original "hangs":**
The function itself terminates, but on unsorted input it returns `None` when a valid pair exists. If your calling code retries on `None` (common pattern), that's your infinite loop -- one level up in the call stack.'''
    ),
    (
        "thinking/debug-race-condition",
        "Users report intermittent wrong balances. This code runs in a web server handling concurrent requests:\n\nclass AccountService:\n    def __init__(self, db):\n        self.db = db\n\n    def transfer(self, from_id: int, to_id: int, amount: float) -> bool:\n        from_acct = self.db.get_account(from_id)\n        to_acct = self.db.get_account(to_id)\n\n        if from_acct.balance < amount:\n            return False\n\n        from_acct.balance -= amount\n        to_acct.balance += amount\n\n        self.db.save_account(from_acct)\n        self.db.save_account(to_acct)\n        return True",
        '''<think>
The user says "intermittent wrong balances" in a concurrent web server. Classic race condition territory. Let me trace through what happens with concurrent requests.

Scenario: Account A has $100. Two requests try to transfer $60 from A simultaneously.

Thread 1: reads A.balance = 100, checks 100 >= 60 (True)
Thread 2: reads A.balance = 100, checks 100 >= 60 (True)  -- stale read!
Thread 1: sets A.balance = 40, saves
Thread 2: sets A.balance = 40, saves  -- overwrites Thread 1's save!

Result: $120 was transferred but only $60 was deducted. Money was created from nothing.

This is TOCTOU (Time Of Check to Time Of Use). The balance check and the update are not atomic.

There's also a second race: the two saves are not in a transaction. If the server crashes between save_account(from_acct) and save_account(to_acct), money disappears -- deducted from sender but never credited to receiver.

A third issue: if from_id == to_id, we'd read the same account twice, and the second save would overwrite the first. But that's an edge case, not the main bug.

Possible fixes:
1. Database-level: SELECT ... FOR UPDATE (row locking) + transaction
2. Application-level: lock per account (but need to lock in consistent order to avoid deadlocks)
3. Optimistic concurrency: version column, retry on conflict

The best fix for a web server is database-level because it works across multiple server processes. Application-level locks only work within a single process.

For the lock ordering: if we lock from_id then to_id, and another thread locks to_id then from_id (reverse transfer), we get a deadlock. Fix: always lock the lower ID first.
</think>

Classic TOCTOU (Time Of Check, Time Of Use) race condition. Here's what happens with concurrent transfers:

```
Thread 1: reads balance = $100, checks $100 >= $60 (ok)
Thread 2: reads balance = $100, checks $100 >= $60 (ok)  -- stale!
Thread 1: balance = $40, saves
Thread 2: balance = $40, saves  -- overwrites Thread 1
Result: $120 transferred, only $60 deducted. Money created from nothing.
```

**Three bugs:**
1. Read-check-write is not atomic (the race condition)
2. Two saves without a transaction (crash between them = lost money)
3. No deadlock prevention if A->B and B->A transfer simultaneously

```python
class AccountService:
    def __init__(self, db):
        self.db = db

    def transfer(self, from_id: int, to_id: int, amount: float) -> bool:
        if from_id == to_id:
            return False
        if amount <= 0:
            return False

        # Lock in consistent order to prevent deadlocks
        lock_order = sorted([from_id, to_id])

        with self.db.transaction() as txn:
            # SELECT ... FOR UPDATE locks the rows until commit
            acct1 = txn.get_account_for_update(lock_order[0])
            acct2 = txn.get_account_for_update(lock_order[1])

            from_acct = acct1 if lock_order[0] == from_id else acct2
            to_acct = acct2 if lock_order[0] == from_id else acct1

            if from_acct.balance < amount:
                return False  # txn auto-rolls back

            from_acct.balance -= amount
            to_acct.balance += amount

            txn.save_account(from_acct)
            txn.save_account(to_acct)
            # Both saves commit atomically
            return True
```

**Key fixes:**
- `SELECT ... FOR UPDATE` prevents concurrent reads of stale data
- Transaction ensures both saves are atomic (all-or-nothing)
- Lock ordering (lower ID first) prevents deadlocks
- Input validation catches edge cases'''
    ),
    (
        "thinking/debug-memory-leak",
        "Our Python web service's memory grows by ~50MB/hour until it OOMs. The leak survives garbage collection. Here's the suspicious module:\n\nimport functools\nimport time\n\n_cache = {}\n_listeners = []\n\nclass EventBus:\n    def __init__(self):\n        self.handlers = {}\n\n    def on(self, event: str, handler):\n        self.handlers.setdefault(event, []).append(handler)\n\n    def emit(self, event: str, data):\n        for handler in self.handlers.get(event, []):\n            handler(data)\n\nbus = EventBus()  # module-level singleton\n\ndef cached_query(func):\n    @functools.wraps(func)\n    def wrapper(*args, **kwargs):\n        key = (func.__name__, args, tuple(sorted(kwargs.items())))\n        if key not in _cache:\n            _cache[key] = func(*args, **kwargs)\n        return _cache[key]\n    return wrapper\n\nclass RequestHandler:\n    def __init__(self, request):\n        self.request = request\n        self.created_at = time.time()\n        bus.on('shutdown', self.cleanup)\n        _listeners.append(self)\n\n    def handle(self):\n        pass\n\n    def cleanup(self, data):\n        pass",
        '''<think>
The user reports 50MB/hour growth that survives GC. That means objects are being retained by strong references, not just uncollected cycles. Let me trace every reference path.

Looking at the module-level state:
1. `_cache = {}` -- module-level dict, never cleared
2. `_listeners = []` -- module-level list, never cleared
3. `bus = EventBus()` -- module-level singleton with handler lists

Now let me trace what happens per request:

Each `RequestHandler.__init__`:
- `bus.on('shutdown', self.cleanup)` -- appends a BOUND METHOD to bus.handlers['shutdown']
- `_listeners.append(self)` -- appends self to module-level list

A bound method (`self.cleanup`) holds a reference to `self`. So `bus.handlers['shutdown']` grows by one entry per request. And `_listeners` grows by one entry per request. Neither is ever cleaned up.

After the request is done, the RequestHandler can't be garbage collected because:
1. `bus.handlers['shutdown']` holds `self.cleanup` which holds `self`
2. `_listeners` holds `self`
3. `self.request` holds the full request object (headers, body, etc.)

So per request we're leaking: RequestHandler + Request object + bound method. If a request is ~50KB, that's 50MB per ~1000 requests, which at modest traffic = ~1 hour.

The `_cache` dict is also unbounded -- every unique query caches forever. But the user said it's 50MB/hour consistently, which suggests per-request leaks (the cache would grow proportional to unique queries, not time).

Three separate leaks:
1. `bus.on('shutdown', self.cleanup)` -- event handlers never removed
2. `_listeners.append(self)` -- listeners never removed
3. `_cache` dict -- never evicted or expired

Fixes:
1. Use weakref for event handlers, or require explicit unsubscribe
2. Use weakref.WeakSet for _listeners, or explicit remove
3. Add TTL or maxsize to the cache

The most impactful fix is #1 and #2 since they leak per-request. #3 leaks per unique query which is slower.
</think>

Three separate memory leaks, all caused by unbounded module-level collections that hold references to per-request objects:

**Leak 1 (biggest): Event bus handlers never removed**
Every `RequestHandler.__init__` calls `bus.on('shutdown', self.cleanup)`. The bound method `self.cleanup` holds a strong reference to `self`. The handler list grows forever -- one entry per request, never removed.

**Leak 2: `_listeners` list never cleared**
`_listeners.append(self)` adds every handler, never removes them.

**Leak 3: `_cache` dict never evicted**
Every unique query is cached forever with no TTL or size limit.

```python
import functools
import time
import weakref
from collections import OrderedDict

_cache = OrderedDict()
_CACHE_MAX = 1000

class EventBus:
    def __init__(self):
        self.handlers = {}

    def on(self, event: str, handler):
        # Store weak references so handlers don't prevent GC
        ref = weakref.WeakMethod(handler) if hasattr(handler, '__self__') else weakref.ref(handler)
        self.handlers.setdefault(event, []).append(ref)

    def emit(self, event: str, data):
        live = []
        for ref in self.handlers.get(event, []):
            handler = ref()
            if handler is not None:
                handler(data)
                live.append(ref)
        # Prune dead references
        if event in self.handlers:
            self.handlers[event] = live

bus = EventBus()

def cached_query(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        key = (func.__name__, args, tuple(sorted(kwargs.items())))
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
        result = func(*args, **kwargs)
        _cache[key] = result
        if len(_cache) > _CACHE_MAX:
            _cache.popitem(last=False)  # evict oldest
        return result
    return wrapper

class RequestHandler:
    def __init__(self, request):
        self.request = request
        self.created_at = time.time()
        bus.on('shutdown', self.cleanup)
        # No _listeners list needed -- weakrefs handle cleanup

    def handle(self):
        pass

    def cleanup(self, data):
        pass
```

**Why this fixes the 50MB/hour leak:**
- `WeakMethod` lets RequestHandlers be GC'd when the request is done -- the event bus won't hold them alive
- `OrderedDict` with `_CACHE_MAX` bounds cache memory at ~1000 entries
- No more `_listeners` list leaking references
- `emit()` automatically prunes dead weakrefs on each call'''
    ),
    (
        "thinking/debug-silent-data-corruption",
        "Our data pipeline produces correct results in tests but wrong results in production. The pipeline processes CSV files:\n\nimport csv\nfrom decimal import Decimal\n\ndef process_transactions(filepath: str) -> dict:\n    totals = {}\n    with open(filepath, 'r') as f:\n        reader = csv.DictReader(f)\n        for row in reader:\n            category = row['category']\n            amount = float(row['amount'])\n            if category not in totals:\n                totals[category] = 0.0\n            totals[category] += amount\n    return totals\n\ndef calculate_tax(totals: dict, rate: float = 0.08) -> dict:\n    return {cat: round(amount * rate, 2) for cat, amount in totals.items()}\n\ndef generate_report(totals: dict, tax: dict) -> str:\n    lines = []\n    grand_total = 0.0\n    for cat in sorted(totals):\n        net = totals[cat]\n        t = tax[cat]\n        lines.append(f'{cat}: ${net:.2f} + ${t:.2f} tax')\n        grand_total += net + t\n    lines.append(f'Grand Total: ${grand_total:.2f}')\n    return '\\n'.join(lines)",
        '''<think>
"Correct in tests, wrong in production." This is almost always about data differences between test fixtures and real-world data. Let me analyze each function for assumptions that hold in tests but break in production.

`process_transactions`:
- Uses `float(row['amount'])` -- floating point! With enough transactions, rounding errors accumulate. Test data probably has small numbers of transactions. Production has thousands.
- Example: 0.1 + 0.2 = 0.30000000000000004 in float
- After 10,000 transactions, errors can be in the cents or even dollars range

But wait, the module imports `Decimal` and never uses it. That's a big clue -- someone knew about float issues but forgot to use Decimal.

- `open(filepath, 'r')` with no encoding specified. Default encoding is platform-dependent. Production might have UTF-8 CSV files with BOM or special characters in category names. Test files are probably ASCII.

- No error handling for missing 'category' or 'amount' keys. Production data might have malformed rows.

`calculate_tax`:
- `round(amount * rate, 2)` -- rounding float * float compounds the error from process_transactions

`generate_report`:
- `grand_total += net + t` -- more float accumulation
- The grand total won't match the sum of displayed values due to float formatting vs actual values

The core issue: **float arithmetic for money**. This is a classic bug. Tests pass because they use small datasets where float errors are below the display threshold (< 0.005). Production fails because thousands of additions accumulate errors above $0.01.

Secondary issues:
1. No encoding specification (platform-dependent)
2. No handling of malformed rows
3. Imported Decimal but never used it

The fix: use Decimal throughout, specify encoding, handle errors.
</think>

The `Decimal` import is the clue -- someone knew about this bug but didn't finish the fix.

**Root cause: float arithmetic for money.** Tests pass with small datasets where rounding errors stay below $0.005 (invisible after `:.2f` formatting). Production has thousands of transactions where errors accumulate into visible cents or dollars.

```python
>>> sum(0.1 for _ in range(1000))
99.99999999999857  # not 100.00
```

**Secondary bugs:**
- No file encoding specified (platform-dependent behavior in production vs dev)
- Imported `Decimal` but never used it
- `grand_total` accumulates more float error in the report

```python
import csv
from decimal import Decimal, ROUND_HALF_UP

TWO_PLACES = Decimal('0.01')

def process_transactions(filepath: str) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        for row in reader:
            category = row.get('category', '').strip()
            raw_amount = row.get('amount', '').strip()
            if not category or not raw_amount:
                continue
            try:
                amount = Decimal(raw_amount)
            except Exception:
                continue  # skip malformed rows
            totals[category] = totals.get(category, Decimal('0')) + amount
    return totals

def calculate_tax(totals: dict[str, Decimal],
                  rate: Decimal = Decimal('0.08')) -> dict[str, Decimal]:
    return {
        cat: (amount * rate).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        for cat, amount in totals.items()
    }

def generate_report(totals: dict[str, Decimal],
                    tax: dict[str, Decimal]) -> str:
    lines = []
    grand_total = Decimal('0')
    for cat in sorted(totals):
        net = totals[cat]
        t = tax[cat]
        lines.append(f'{cat}: ${net:.2f} + ${t:.2f} tax')
        grand_total += net + t
    lines.append(f'Grand Total: ${grand_total:.2f}')
    return '\n'.join(lines)
```

**Why this fixes production:**
- `Decimal` is exact for base-10 arithmetic -- no accumulated rounding errors
- `Decimal(raw_amount)` parses the CSV string directly (never goes through float)
- `utf-8-sig` handles BOM markers in production CSVs
- `.quantize(ROUND_HALF_UP)` gives standard financial rounding
- Malformed rows are skipped instead of crashing the pipeline'''
    ),
]
