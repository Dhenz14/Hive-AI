"""Deep reasoning training pairs: debugging with extended think blocks."""

PAIRS = [
    # -------------------------------------------------------------------------
    # 1. Race condition in a thread-safe LRU cache (lock ordering bug)
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-race-condition-lru-cache",
        r'''I wrote a thread-safe LRU cache but it sometimes returns stale values or crashes under heavy concurrent use. Can you find the bugs?

```python
import threading
from collections import OrderedDict

class ThreadSafeLRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = OrderedDict()
        self.lock = threading.Lock()
        self.stats_lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key):
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                value = self.cache[key]
                with self.stats_lock:
                    self.hits += 1
                return value
            else:
                with self.stats_lock:
                    self.misses += 1
                return None

    def put(self, key, value):
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                self.cache[key] = value
            else:
                if len(self.cache) >= self.capacity:
                    self.cache.popitem(last=False)
                self.cache[key] = value

    def get_or_compute(self, key, compute_fn):
        value = self.get(key)
        if value is None:
            value = compute_fn(key)
            self.put(key, value)
        return value

    def get_stats(self):
        with self.stats_lock:
            return {"hits": self.hits, "misses": self.misses}
```''',
        r'''<think>
Let me trace through this code carefully under concurrent access.

First bug — lock ordering. In `get()`, the code acquires `self.lock` and then tries to acquire `self.stats_lock` while still holding `self.lock`. Meanwhile, if any other code path acquired `stats_lock` first and then tried to acquire `lock`, we'd have a classic ABBA deadlock. Looking at this code, `get_stats()` only acquires `stats_lock`, so there's no immediate ABBA deadlock from the existing methods. But the nested lock acquisition is still a bad pattern — any future method that takes `stats_lock` then `lock` will deadlock.

However, the REAL critical bug is in `get_or_compute()`. Let me trace through it with two threads calling `get_or_compute("key1", expensive_fn)` simultaneously:

Thread A: calls get("key1") -> returns None (cache miss)
Thread B: calls get("key1") -> returns None (cache miss)
Thread A: computes value, calls put("key1", value_A)
Thread B: computes value, calls put("key1", value_B) — overwrites A's result

This is a TOCTOU race — the check (get) and the act (compute + put) are not atomic. Both threads compute the value, wasting work, and the second write wins. Worse, the miss count is incremented twice even though conceptually it's one logical miss.

Second bug: `get_or_compute` cannot cache `None` values. If `compute_fn` legitimately returns `None`, the cache will never store it — every call will recompute because `get()` returns `None` for both "not found" and "value is None". This is a sentinel value collision.

Third bug: the nested lock acquisition inside `get()` — acquiring `stats_lock` while holding `lock` — means every cache hit/miss pays the cost of two lock acquisitions. More importantly, if someone extends the class and calls `get()` while holding `stats_lock`, instant deadlock. The stats should be updated outside the main lock, or use a single lock.

Let me verify my fix handles the edge cases: concurrent compute, None values, and lock ordering.
</think>

There are three bugs in this code:

**Bug 1 (Critical): TOCTOU race in `get_or_compute()`**

The `get()` and `put()` calls are individually atomic, but `get_or_compute()` releases the lock between them. Two threads can both see a cache miss, both compute the value (wasting work), and the last write wins. Under heavy load this means redundant expensive computations and potentially inconsistent state.

**Bug 2: Cannot cache `None` values**

`get()` returns `None` for both "key not found" and "key maps to None". If `compute_fn` returns `None`, the value is never effectively cached.

**Bug 3: Nested lock acquisition (deadlock risk)**

`get()` acquires `self.lock` then `self.stats_lock` inside it. This nested locking creates a deadlock hazard if any code path ever acquires the locks in the opposite order.

**Fixed code:**

```python
import threading
from collections import OrderedDict

_MISSING = object()  # Sentinel distinct from any real value

class ThreadSafeLRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = OrderedDict()
        self.lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key, default=_MISSING):
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                self.hits += 1
                return self.cache[key]
            else:
                self.misses += 1
                if default is not _MISSING:
                    return default
                return _MISSING

    def put(self, key, value):
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                self.cache[key] = value
            else:
                if len(self.cache) >= self.capacity:
                    self.cache.popitem(last=False)
                self.cache[key] = value

    def get_or_compute(self, key, compute_fn):
        with self.lock:
            if key in self.cache:
                self.cache.move_to_end(key)
                self.hits += 1
                return self.cache[key]
            self.misses += 1

        # Compute outside the lock (allows concurrency for different keys).
        # Accept that two threads may both compute for the same NEW key;
        # first-write-wins is acceptable, but we can refine with per-key locks
        # if compute_fn is very expensive.
        value = compute_fn(key)

        with self.lock:
            # Only insert if not already computed by another thread
            if key not in self.cache:
                if len(self.cache) >= self.capacity:
                    self.cache.popitem(last=False)
                self.cache[key] = value
            else:
                # Another thread beat us — use their result for consistency
                value = self.cache[key]
        return value

    def get_stats(self):
        with self.lock:
            return {"hits": self.hits, "misses": self.misses}


# ---------- Test ----------
import concurrent.futures, time

def test_thread_safe_lru():
    cache = ThreadSafeLRUCache(capacity=3)
    call_count = {"k": 0}
    count_lock = threading.Lock()

    def expensive(key):
        with count_lock:
            call_count["k"] += 1
        time.sleep(0.01)
        return f"value-{key}"

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(cache.get_or_compute, "same_key", expensive) for _ in range(20)]
        results = [f.result() for f in futures]

    # All results must be identical
    assert all(r == "value-same_key" for r in results), f"Inconsistent results: {set(results)}"
    stats = cache.get_stats()
    assert stats["hits"] + stats["misses"] == 20
    print(f"PASS  call_count={call_count['k']} hits={stats['hits']} misses={stats['misses']}")

test_thread_safe_lru()
```

Key changes: single lock (eliminates deadlock risk), sentinel object (allows caching `None`), and `get_or_compute` does a second check-under-lock after computing to avoid overwriting a value another thread already inserted.'''
    ),

    # -------------------------------------------------------------------------
    # 2. Off-by-one in binary search returning wrong index
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-binary-search-off-by-one",
        r'''My binary search function should return the index of the leftmost occurrence of `target` in a sorted list. It works for some inputs but returns the wrong index for others. What's wrong?

```python
def binary_search_leftmost(arr, target):
    """Return index of leftmost occurrence of target, or -1 if not found."""
    lo, hi = 0, len(arr)
    result = -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if arr[mid] == target:
            result = mid
            hi = mid - 1  # keep searching left
        elif arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return result

# Tests
print(binary_search_leftmost([1, 2, 3, 3, 3, 4, 5], 3))  # expect 2
print(binary_search_leftmost([1, 2, 3], 4))                # expect -1
print(binary_search_leftmost([1], 1))                      # expect 0
print(binary_search_leftmost([], 1))                       # expect -1
```''',
        r'''<think>
Let me trace through this binary search carefully.

The bounds are initialized as `lo = 0, hi = len(arr)`. This is a half-open style (hi is exclusive). But the while condition is `lo <= hi`, and the code accesses `arr[mid]` where `mid = (lo + hi) // 2`.

Let me trace with an empty array `[]`:
- lo=0, hi=0 (len([]) = 0)
- lo <= hi is True (0 <= 0)
- mid = 0
- arr[0] -> IndexError! The array is empty.

So that's one bug: when the array is empty, it crashes.

Now let me trace with `[1]` and target=1:
- lo=0, hi=1
- lo <= hi: True
- mid = 0, arr[0]=1 == target -> result=0, hi = -1
- lo <= hi: 0 <= -1 is False, stop
- Returns 0. Correct.

Now trace with `[1]` and target=2:
- lo=0, hi=1
- lo <= hi: True
- mid = 0, arr[0]=1 < 2 -> lo = 1
- lo <= hi: 1 <= 1 is True
- mid = 1, arr[1] -> IndexError! The array only has index 0.

So there it is. The root cause: `hi` is initialized to `len(arr)` (exclusive upper bound) but the while loop uses `lo <= hi` (which is the convention for inclusive upper bounds). This means `mid` can equal `len(arr)`, causing an index-out-of-bounds access.

The fix: either use `hi = len(arr) - 1` (inclusive), or use `lo < hi` with different update logic.

Let me also check: is there an integer overflow risk with `(lo + hi) // 2`? In Python, integers are arbitrary precision, so no — but in other languages this would be a concern. Not a bug here.

Let me verify my fix with the duplicate case [1,2,3,3,3,4,5] target=3:
Using hi = len(arr) - 1 = 6:
- lo=0, hi=6, mid=3, arr[3]=3==target -> result=3, hi=2
- lo=0, hi=2, mid=1, arr[1]=2 < 3 -> lo=2
- lo=2, hi=2, mid=2, arr[2]=3==target -> result=2, hi=1
- lo=2, hi=1, stop. Returns 2. Correct!

And the empty array: hi = len([]) - 1 = -1, lo=0. 0 <= -1 is False, loop never runs, returns -1. Correct.
</think>

The bug is in the initialization of `hi`. You set `hi = len(arr)` (exclusive upper bound) but use `while lo <= hi` (inclusive upper bound convention). This mismatch means `mid` can equal `len(arr)`, causing an **IndexError** on `arr[mid]`.

It manifests in two ways:
1. **Empty array** crashes immediately: `lo=0, hi=0`, enters loop, accesses `arr[0]` which doesn't exist.
2. **Target greater than all elements** eventually sets `lo` high enough that `mid = len(arr)`, again an out-of-bounds access.

**Fixed code:**

```python
def binary_search_leftmost(arr, target):
    """Return index of leftmost occurrence of target, or -1 if not found."""
    lo, hi = 0, len(arr) - 1  # FIX: inclusive upper bound
    result = -1
    while lo <= hi:
        mid = (lo + hi) // 2
        if arr[mid] == target:
            result = mid
            hi = mid - 1  # keep searching left
        elif arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return result


# ---------- Tests ----------
assert binary_search_leftmost([1, 2, 3, 3, 3, 4, 5], 3) == 2
assert binary_search_leftmost([1, 2, 3], 4) == -1
assert binary_search_leftmost([1], 1) == 0
assert binary_search_leftmost([], 1) == -1
assert binary_search_leftmost([3, 3, 3], 3) == 0
assert binary_search_leftmost([1, 2, 3], 1) == 0
assert binary_search_leftmost([1, 2, 3], 3) == 2
print("All tests passed.")
```

The single-character fix (`len(arr) - 1` instead of `len(arr)`) ensures `mid` always stays within valid array bounds.'''
    ),

    # -------------------------------------------------------------------------
    # 3. Closure variable capture in loop
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-closure-variable-capture-loop",
        r'''I'm building a list of callback functions in a loop, but they all return the same value when called. What's wrong?

```python
def make_multipliers():
    multipliers = []
    for i in range(5):
        def multiply(x):
            return x * i
        multipliers.append(multiply)
    return multipliers

mults = make_multipliers()
print([m(10) for m in mults])
# Expected: [0, 10, 20, 30, 40]
# Actual:   [40, 40, 40, 40, 40]
```''',
        r'''<think>
This is a classic Python closure bug. Let me trace through what happens.

When the loop runs, it creates 5 functions. Each function's body references the variable `i`. Crucially, the functions do NOT capture the VALUE of `i` at creation time — they capture a reference to the variable `i` in the enclosing scope.

After the loop finishes, `i` has its final value of 4. When any of the 5 functions are called, they all look up `i` in the enclosing scope, find 4, and compute `x * 4`. So `m(10)` = 40 for all of them.

This is because Python closures use late binding — the variable is looked up when the function is called, not when it is defined. This surprises people coming from languages with block-level scoping.

There are several fixes:
1. Use a default argument to capture the value at definition time: `def multiply(x, i=i):`
2. Use `functools.partial`
3. Use a factory function that creates a new scope for each value

The default argument approach is the most common Python idiom, though the factory function is arguably cleaner since it doesn't pollute the function signature.

Let me also consider: is there a second bug? No, the logic is otherwise correct — it's purely the closure capture issue.

Let me verify: with `def multiply(x, i=i):`, at each loop iteration the current value of `i` is bound to the default parameter. Default arguments are evaluated once at function definition time, so each function gets its own snapshot. When called with just one argument `m(10)`, the default `i` is used. This correctly produces [0, 10, 20, 30, 40].
</think>

This is the classic **late-binding closure** bug in Python. All 5 `multiply` functions close over the **same variable** `i`, not its value at each iteration. By the time the functions are called, the loop has finished and `i == 4`, so every function computes `x * 4`.

Python closures use **late binding**: the variable is looked up at call time, not at definition time.

**Fixed code (three approaches):**

```python
# Fix 1: Default argument captures value at definition time
def make_multipliers_v1():
    multipliers = []
    for i in range(5):
        def multiply(x, i=i):  # i=i binds current value as default
            return x * i
        multipliers.append(multiply)
    return multipliers

# Fix 2: Factory function creates a new scope per iteration
def make_multipliers_v2():
    def make_mult(i):
        def multiply(x):
            return x * i
        return multiply
    return [make_mult(i) for i in range(5)]

# Fix 3: functools.partial
from functools import partial

def make_multipliers_v3():
    def multiply(i, x):
        return x * i
    return [partial(multiply, i) for i in range(5)]


# ---------- Tests ----------
for name, fn in [("v1", make_multipliers_v1),
                 ("v2", make_multipliers_v2),
                 ("v3", make_multipliers_v3)]:
    result = [m(10) for m in fn()]
    assert result == [0, 10, 20, 30, 40], f"{name} failed: {result}"
    print(f"{name} PASS: {result}")
```

The default-argument trick (`i=i`) is the most common Python idiom — it evaluates `i` at function definition time and binds it to the parameter's default value, giving each closure its own snapshot.'''
    ),

    # -------------------------------------------------------------------------
    # 4. Generator exhaustion
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-generator-exhaustion",
        r'''My data pipeline processes records twice — once to validate, once to transform — but the second pass always produces an empty result. What's wrong?

```python
def read_records(filename):
    """Read records from a CSV-like file."""
    with open(filename) as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) == 3:
                yield {"name": parts[0], "age": int(parts[1]), "score": float(parts[2])}

def validate(records):
    """Check all records are valid. Returns True if all pass."""
    for r in records:
        if r["age"] < 0 or r["score"] < 0:
            return False
    return True

def transform(records):
    """Normalize scores to 0-1 range."""
    all_records = list(records)
    if not all_records:
        return []
    max_score = max(r["score"] for r in all_records)
    return [
        {**r, "score": r["score"] / max_score} for r in all_records
    ]

def process(filename):
    records = read_records(filename)

    if not validate(records):
        raise ValueError("Invalid records found")

    result = transform(records)
    print(f"Processed {len(result)} records")
    return result
```''',
        r'''<think>
Let me trace through the `process` function step by step.

`records = read_records(filename)` — this returns a generator object. It does NOT read the file yet.

`validate(records)` — this iterates through the generator, consuming every record. The generator yields each record, validate checks it, and when the generator is exhausted, validate returns True.

Now `transform(records)` is called with the SAME generator object. But the generator has already been fully consumed by `validate()`. A generator in Python can only be iterated once — once exhausted, it yields nothing. So `list(records)` returns `[]`, and `transform` returns `[]`.

The root cause: generators are single-use iterators. The code treats `records` as if it were a reusable collection (like a list), but it's actually a one-shot generator.

There's also a subtle secondary issue: if the file is very large, materializing all records into a list might use too much memory. But the immediate bug is the exhaustion problem.

Possible fixes:
1. Convert the generator to a list once, then pass the list to both functions
2. Use `itertools.tee` to fork the generator (but this buffers everything in memory anyway)
3. Call `read_records()` twice (re-opens the file, which works but is wasteful)
4. Restructure to do validation and transformation in a single pass

The cleanest fix is option 1 — materialize once, use twice.

Wait, there's another edge case: if `max_score` is 0, we'd get a ZeroDivisionError in transform. Not the reported bug, but worth noting.

Let me verify: with the fix of materializing to a list, validate gets a list (re-iterable), transform gets the same list (still iterable). Both work correctly.
</think>

The bug is **generator exhaustion**. `read_records()` returns a generator, which is a **single-use iterator**. When `validate(records)` iterates through all the records, the generator is fully consumed. When `transform(records)` then tries to iterate the same generator, it immediately gets nothing — the generator is already done.

There's also a lurking **ZeroDivisionError** in `transform` if all scores are 0.

**Fixed code:**

```python
def read_records(filename):
    """Read records from a CSV-like file."""
    with open(filename) as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) == 3:
                yield {"name": parts[0], "age": int(parts[1]), "score": float(parts[2])}

def validate(records):
    for r in records:
        if r["age"] < 0 or r["score"] < 0:
            return False
    return True

def transform(records):
    all_records = list(records)
    if not all_records:
        return []
    max_score = max(r["score"] for r in all_records)
    if max_score == 0:
        return all_records  # FIX: avoid division by zero
    return [
        {**r, "score": r["score"] / max_score} for r in all_records
    ]

def process(filename):
    # FIX: materialize the generator into a list ONCE
    records = list(read_records(filename))

    if not validate(records):
        raise ValueError("Invalid records found")

    result = transform(records)
    print(f"Processed {len(result)} records")
    return result


# ---------- Test ----------
import tempfile, os

with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
    f.write("Alice,30,85.0\nBob,25,92.5\nCarol,28,78.0\n")
    tmpfile = f.name

try:
    result = process(tmpfile)
    assert len(result) == 3, f"Expected 3, got {len(result)}"
    assert result[1]["score"] == 1.0  # Bob has max score
    print(f"PASS: {result}")
finally:
    os.unlink(tmpfile)
```

The key fix: `records = list(read_records(filename))` materializes the generator into a reusable list. Both `validate()` and `transform()` can now iterate over it independently.'''
    ),

    # -------------------------------------------------------------------------
    # 5. Mutable default argument
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-mutable-default-argument",
        r'''Instances of my class are supposed to have independent tag lists, but adding a tag to one instance affects others. What's the bug?

```python
class Task:
    def __init__(self, title, tags=[]):
        self.title = title
        self.tags = tags

    def add_tag(self, tag):
        self.tags.append(tag)

    def __repr__(self):
        return f"Task({self.title!r}, tags={self.tags})"

# Test
t1 = Task("Write docs")
t2 = Task("Fix bug")
t3 = Task("Deploy", tags=["urgent"])

t1.add_tag("documentation")
t2.add_tag("bugfix")

print(t1)  # Expected: Task('Write docs', tags=['documentation'])
print(t2)  # Expected: Task('Fix bug', tags=['bugfix'])
print(t3)  # Expected: Task('Deploy', tags=['urgent'])
```''',
        r'''<think>
This is the classic mutable default argument bug in Python. Let me trace through exactly what happens.

When Python parses `def __init__(self, title, tags=[])`, it evaluates the default value `[]` ONCE, at function definition time, and stores that single list object as the default. Every call to `__init__` that doesn't provide `tags` gets a reference to this SAME list object.

Let me trace:
1. `t1 = Task("Write docs")` — tags not provided, so `self.tags` = the shared default list `[]`
2. `t2 = Task("Fix bug")` — tags not provided, so `self.tags` = the SAME shared default list
3. `t3 = Task("Deploy", tags=["urgent"])` — tags explicitly provided, so `self.tags` = a new independent list `["urgent"]`

Now:
4. `t1.add_tag("documentation")` — appends to the shared default list, which is now `["documentation"]`
5. `t2.add_tag("bugfix")` — appends to the SAME shared list, which is now `["documentation", "bugfix"]`

So `t1.tags` and `t2.tags` both point to `["documentation", "bugfix"]`. Only `t3` has its own list.

The actual output would be:
```
Task('Write docs', tags=['documentation', 'bugfix'])
Task('Fix bug', tags=['documentation', 'bugfix'])
Task('Deploy', tags=['urgent'])
```

The fix is to use `None` as the default and create a new list inside the function body.

Let me verify: with `tags=None` and `self.tags = tags if tags is not None else []`, each call without tags creates a fresh `[]`. The `else []` creates a new list each time `__init__` runs. This gives each instance its own independent list. For t3, the explicit list is used directly.
</think>

This is the **mutable default argument** bug, one of Python's most notorious gotchas.

The default value `tags=[]` is evaluated **once** at class definition time. Every instance created without an explicit `tags` argument shares the **same list object**. Appending to one instance's tags mutates the shared list, affecting all other instances.

Actual output of the buggy code:
```
Task('Write docs', tags=['documentation', 'bugfix'])
Task('Fix bug', tags=['documentation', 'bugfix'])
```

**Fixed code:**

```python
class Task:
    def __init__(self, title, tags=None):  # FIX: None instead of []
        self.title = title
        self.tags = tags if tags is not None else []  # FIX: fresh list per instance

    def add_tag(self, tag):
        self.tags.append(tag)

    def __repr__(self):
        return f"Task({self.title!r}, tags={self.tags})"


# ---------- Test ----------
t1 = Task("Write docs")
t2 = Task("Fix bug")
t3 = Task("Deploy", tags=["urgent"])

t1.add_tag("documentation")
t2.add_tag("bugfix")

assert t1.tags == ["documentation"], f"t1 wrong: {t1.tags}"
assert t2.tags == ["bugfix"], f"t2 wrong: {t2.tags}"
assert t3.tags == ["urgent"], f"t3 wrong: {t3.tags}"

# Verify they are truly independent objects
assert t1.tags is not t2.tags
print(f"PASS: {t1}, {t2}, {t3}")
```

The rule: **never use a mutable object as a default argument**. Use `None` and create a fresh instance inside the function body.'''
    ),

    # -------------------------------------------------------------------------
    # 6. Async deadlock from unreleased semaphore on exception
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-async-semaphore-deadlock",
        r'''My async rate limiter hangs after a few errors. It works fine when all requests succeed, but once an exception occurs it eventually freezes. What's wrong?

```python
import asyncio

class RateLimiter:
    def __init__(self, max_concurrent: int):
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def execute(self, coro):
        await self.semaphore.acquire()
        result = await coro
        self.semaphore.release()
        return result

async def fetch(url: str):
    await asyncio.sleep(0.01)
    if "error" in url:
        raise ValueError(f"Bad URL: {url}")
    return f"OK: {url}"

async def main():
    limiter = RateLimiter(max_concurrent=3)
    urls = [
        "https://example.com/1",
        "https://example.com/error",
        "https://example.com/2",
        "https://example.com/3",
        "https://example.com/4",
        "https://example.com/5",
    ]
    tasks = [limiter.execute(fetch(url)) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        print(r)

asyncio.run(main())
```''',
        r'''<think>
Let me trace through what happens when a request fails.

The `execute` method does:
1. `await self.semaphore.acquire()` — decrements the semaphore count
2. `result = await coro` — runs the coroutine
3. `self.semaphore.release()` — increments the semaphore count
4. `return result`

If step 2 raises an exception, step 3 (release) is NEVER called. The semaphore counter is permanently decremented by 1. With max_concurrent=3, after 3 exceptions, the semaphore count reaches 0 and no new tasks can acquire it. All remaining tasks hang forever waiting on `acquire()`.

In this specific example, only one URL has "error", so the semaphore drops from 3 to 2 effective slots. That's enough to finish, but if there were 3+ errors, it would deadlock. However, even with one unreleased slot, we're leaking capacity.

Wait, let me look more carefully at `asyncio.gather(*tasks, return_exceptions=True)`. This means exceptions don't propagate — they're returned as results. But the semaphore still doesn't get released when the exception occurs in `execute`.

Actually, with only one error and max_concurrent=3, this specific example might complete. But with 3+ errors it absolutely deadlocks. Let me re-read the user's description: "hangs after a few errors" — so in their real usage they have more errors.

The fix is straightforward: use try/finally to ensure the semaphore is always released, or better yet, use `async with self.semaphore:` which handles this automatically.

Let me also check: is there a second bug? The `coro` in `execute` — when we write `limiter.execute(fetch(url))`, `fetch(url)` creates the coroutine immediately. The coroutine object is created before `acquire()` is called. This isn't a bug per se, but the coroutine starts executing only when awaited, so the semaphore correctly gates the actual work.

Let me verify the fix: `async with self.semaphore:` uses `__aenter__` (acquire) and `__aexit__` (release), with the release guaranteed even on exception. This is the correct pattern.
</think>

The bug: when `await coro` raises an exception, `self.semaphore.release()` is **never called**. Each failed request permanently consumes one semaphore slot. After `max_concurrent` failures, the semaphore count hits 0 and all subsequent `acquire()` calls hang forever.

This is the async equivalent of a resource leak — failing to release a lock/semaphore in the error path.

**Fixed code:**

```python
import asyncio

class RateLimiter:
    def __init__(self, max_concurrent: int):
        self.semaphore = asyncio.Semaphore(max_concurrent)

    async def execute(self, coro):
        # FIX: use async context manager — guarantees release even on exception
        async with self.semaphore:
            return await coro

async def fetch(url: str):
    await asyncio.sleep(0.01)
    if "error" in url:
        raise ValueError(f"Bad URL: {url}")
    return f"OK: {url}"

async def main():
    limiter = RateLimiter(max_concurrent=3)
    # Stress test: many errors mixed in
    urls = [
        "https://example.com/1",
        "https://example.com/error1",
        "https://example.com/error2",
        "https://example.com/error3",
        "https://example.com/error4",  # Would deadlock with old code
        "https://example.com/2",
        "https://example.com/3",
    ]
    tasks = [limiter.execute(fetch(url)) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = [r for r in results if isinstance(r, str)]
    failures = [r for r in results if isinstance(r, Exception)]
    print(f"Successes: {len(successes)}, Failures: {len(failures)}")
    assert len(successes) == 3
    assert len(failures) == 4
    print("PASS")

asyncio.run(main())
```

`async with self.semaphore:` is equivalent to acquire/try/finally/release, but cleaner and impossible to get wrong. Always use context managers for resource acquisition in async code.'''
    ),

    # -------------------------------------------------------------------------
    # 7. Shallow copy bug in undo/redo system
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-shallow-copy-undo-redo",
        r'''My undo/redo system doesn't restore the previous state correctly — after undo, the state still shows the latest changes. What's wrong?

```python
class UndoRedoManager:
    def __init__(self, initial_state):
        self.undo_stack = [initial_state]
        self.redo_stack = []

    def save_state(self, state):
        self.undo_stack.append(state)
        self.redo_stack.clear()

    def undo(self):
        if len(self.undo_stack) > 1:
            current = self.undo_stack.pop()
            self.redo_stack.append(current)
            return self.undo_stack[-1]
        return self.undo_stack[-1]

    def redo(self):
        if self.redo_stack:
            state = self.redo_stack.pop()
            self.undo_stack.append(state)
            return state
        return self.undo_stack[-1]

# Test
doc = {"text": "Hello", "style": {"bold": False, "font_size": 12}}
mgr = UndoRedoManager(doc)

doc["text"] = "Hello World"
mgr.save_state(doc)

doc["style"]["bold"] = True
mgr.save_state(doc)

# Now undo the bold change
restored = mgr.undo()
print(restored)  # Expected: {"text": "Hello World", "style": {"bold": False, ...}}
# Actual: {"text": "Hello World", "style": {"bold": True, ...}}
```''',
        r'''<think>
Let me trace through the object references carefully.

`doc = {"text": "Hello", "style": {"bold": False, "font_size": 12}}`
This creates one dict with a nested dict.

`mgr = UndoRedoManager(doc)` — undo_stack = [doc]. This stores a REFERENCE to `doc`, not a copy.

`doc["text"] = "Hello World"` — mutates the original dict. Since undo_stack[0] IS the same object, undo_stack[0]["text"] is now "Hello World" too.

`mgr.save_state(doc)` — undo_stack = [doc, doc]. Both entries are references to the SAME dict object!

`doc["style"]["bold"] = True` — mutates the original dict (and its nested dict). All references see this change.

`mgr.save_state(doc)` — undo_stack = [doc, doc, doc]. Three references to the SAME object.

`mgr.undo()` — pops undo_stack[-1] (a reference to doc), pushes it to redo_stack, returns undo_stack[-1] which is still a reference to doc. Since there's only ONE actual dict object, it still shows the latest mutations.

The root cause: the manager stores references to the same mutable dict, never making copies. All "snapshots" point to the same object.

The fix: make a DEEP copy of the state when saving. `copy.deepcopy()` is needed because the state has nested dicts — a shallow copy with `dict.copy()` or `copy.copy()` would still share the nested `style` dict.

Let me verify: with `copy.deepcopy(state)` in both `__init__` and `save_state`, each snapshot is an independent copy. Mutations to the original `doc` won't affect previously saved snapshots.

Wait, should `undo()` and `redo()` also return deep copies? If the caller mutates the returned state, it would corrupt the stored snapshot. Yes — for safety, the return values should also be deep-copied. Let me include that.
</think>

The bug is a **shallow reference** problem. The manager stores references to the same dict object, never making copies. When you mutate `doc`, all "snapshots" in the undo stack see the same changes because they all point to the same object.

After the three `save_state` calls, `undo_stack` contains `[doc, doc, doc]` — three references to the **same dict**. Undo just shuffles references around but they all reflect the latest mutations.

**Fixed code:**

```python
import copy

class UndoRedoManager:
    def __init__(self, initial_state):
        self.undo_stack = [copy.deepcopy(initial_state)]  # FIX: deep copy
        self.redo_stack = []

    def save_state(self, state):
        self.undo_stack.append(copy.deepcopy(state))  # FIX: deep copy
        self.redo_stack.clear()

    def undo(self):
        if len(self.undo_stack) > 1:
            current = self.undo_stack.pop()
            self.redo_stack.append(current)
            return copy.deepcopy(self.undo_stack[-1])  # FIX: return copy
        return copy.deepcopy(self.undo_stack[-1])

    def redo(self):
        if self.redo_stack:
            state = self.redo_stack.pop()
            self.undo_stack.append(state)
            return copy.deepcopy(state)  # FIX: return copy
        return copy.deepcopy(self.undo_stack[-1])


# ---------- Test ----------
doc = {"text": "Hello", "style": {"bold": False, "font_size": 12}}
mgr = UndoRedoManager(doc)

doc["text"] = "Hello World"
mgr.save_state(doc)

doc["style"]["bold"] = True
mgr.save_state(doc)

# Undo bold change
restored = mgr.undo()
assert restored["style"]["bold"] is False, f"bold should be False: {restored}"
assert restored["text"] == "Hello World"

# Undo text change
restored2 = mgr.undo()
assert restored2["text"] == "Hello"
assert restored2["style"]["bold"] is False

# Redo
redone = mgr.redo()
assert redone["text"] == "Hello World"

# Full redo
redone2 = mgr.redo()
assert redone2["style"]["bold"] is True

print("PASS: all undo/redo tests passed")
```

Key insight: `copy.deepcopy()` is required, not `dict.copy()`, because the state has nested dicts. A shallow copy would still share the inner `style` dict, causing the same bug for nested mutations.'''
    ),

    # -------------------------------------------------------------------------
    # 8. Python descriptor storing value on class instead of instance
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-descriptor-class-vs-instance",
        r'''I wrote a custom descriptor for type-validated attributes, but setting a value on one instance changes it for ALL instances. What's wrong?

```python
class TypedField:
    """Descriptor that enforces a type on assignment."""
    def __init__(self, name, expected_type):
        self.name = name
        self.expected_type = expected_type
        self.value = None  # storage

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return self.value

    def __set__(self, obj, value):
        if not isinstance(value, self.expected_type):
            raise TypeError(f"{self.name} must be {self.expected_type.__name__}")
        self.value = value

class User:
    name = TypedField("name", str)
    age = TypedField("age", int)

    def __init__(self, name, age):
        self.name = name
        self.age = age

# Test
u1 = User("Alice", 30)
u2 = User("Bob", 25)
print(u1.name, u1.age)  # Expected: Alice 30
print(u2.name, u2.age)  # Expected: Bob 25
# Actual: Bob 25 for BOTH
```''',
        r'''<think>
Let me trace through the descriptor protocol carefully.

`TypedField` is a descriptor — it's defined as a CLASS attribute of `User`. There is ONE `TypedField("name", str)` instance shared across ALL `User` instances. Same for `TypedField("age", int)`.

When we do `self.name = "Alice"` in `__init__`, Python calls `TypedField.__set__(self=the_descriptor, obj=u1, value="Alice")`. The `__set__` method stores the value in `self.value` — but `self` here is the DESCRIPTOR instance (the class-level `TypedField` object), NOT the `User` instance.

So `self.value` is stored on the descriptor itself, which is shared. When u2 sets name="Bob", it overwrites the same `self.value`. Reading `u1.name` then returns "Bob".

The root cause: the descriptor stores data on itself (the class-level object) instead of on the per-instance `obj`.

The fix: store the value in `obj.__dict__` (the instance's dictionary), keyed by the field name. The `__get__` method should read from `obj.__dict__` too.

Let me verify: with `obj.__dict__[self.name] = value` in `__set__` and `obj.__dict__.get(self.name)` in `__get__`, each instance stores its own value. The descriptor object itself is stateless (it just knows the name and type).

Wait — there's a subtlety. If we use `obj.__dict__[self.name]`, and the descriptor's `self.name` matches the class attribute name, then `obj.__dict__["name"]` would normally shadow the descriptor. But since we define `__set__`, it's a data descriptor, which takes priority over instance `__dict__`. So `__get__` will be called even if there's a value in `obj.__dict__`. This means our approach of storing in `obj.__dict__` and reading from it in `__get__` will work correctly.
</think>

The bug: the descriptor stores values on **itself** (`self.value = value`) instead of on the **instance** (`obj`). Since there's only one `TypedField("name", str)` object shared by all `User` instances, all instances read and write the same `self.value`. The last assignment wins.

**Fixed code:**

```python
class TypedField:
    """Descriptor that enforces a type on assignment."""
    def __init__(self, name, expected_type):
        self.name = name
        self.expected_type = expected_type
        # FIX: no self.value — data lives on each instance, not the descriptor

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        # FIX: read from the instance's __dict__
        return obj.__dict__.get(self.name)

    def __set__(self, obj, value):
        if not isinstance(value, self.expected_type):
            raise TypeError(f"{self.name} must be {self.expected_type.__name__}")
        # FIX: store on the instance, not the descriptor
        obj.__dict__[self.name] = value

class User:
    name = TypedField("name", str)
    age = TypedField("age", int)

    def __init__(self, name, age):
        self.name = name
        self.age = age


# ---------- Test ----------
u1 = User("Alice", 30)
u2 = User("Bob", 25)

assert u1.name == "Alice" and u1.age == 30, f"u1 wrong: {u1.name}, {u1.age}"
assert u2.name == "Bob" and u2.age == 25, f"u2 wrong: {u2.name}, {u2.age}"

# Type validation still works
try:
    u1.age = "not a number"
    assert False, "Should have raised TypeError"
except TypeError:
    pass

# Mutation independence
u1.name = "Alicia"
assert u2.name == "Bob", "u2 should be unaffected"

print(f"PASS: u1=({u1.name}, {u1.age}), u2=({u2.name}, {u2.age})")
```

The golden rule for descriptors: **store data on the instance (`obj.__dict__`), not on the descriptor (`self`)**. The descriptor is a class-level singleton — it should only hold metadata (name, type), not per-instance values.'''
    ),

    # -------------------------------------------------------------------------
    # 9. Memory leak from circular references with __del__
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-circular-reference-del-leak",
        r'''My node-based graph keeps consuming more memory even after I delete all references to it. I added `__del__` to log cleanup, but it never gets called. What's wrong?

```python
import gc

class Node:
    _alive_count = 0

    def __init__(self, name):
        self.name = name
        self.neighbors = []
        Node._alive_count += 1

    def connect(self, other):
        self.neighbors.append(other)
        other.neighbors.append(self)

    def __del__(self):
        Node._alive_count -= 1
        print(f"Node {self.name} deleted")

    def __repr__(self):
        return f"Node({self.name})"

def build_graph():
    a = Node("A")
    b = Node("B")
    c = Node("C")
    a.connect(b)
    b.connect(c)
    c.connect(a)  # circular
    return [a, b, c]

# Test
nodes = build_graph()
print(f"Before delete: {Node._alive_count} nodes alive")
del nodes
gc.collect()
print(f"After delete + gc: {Node._alive_count} nodes alive")
```''',
        r'''<think>
Let me trace through the reference counting and garbage collection.

After `build_graph()`, we have:
- A -> [B], B -> [A, C], C -> [B, A] — a circular reference cycle.

When `del nodes` is called, the list is deleted, removing the external references to A, B, C. But each node is still referenced by other nodes' `neighbors` lists. The reference counts don't drop to zero.

Python's garbage collector CAN handle circular references — that's what `gc.collect()` is for. It detects cycles and collects them. However, there's a critical caveat: in older Python versions (< 3.4), objects with `__del__` methods in a reference cycle were NOT collected because the GC couldn't determine a safe order to finalize them. They were placed in `gc.garbage` instead.

In Python 3.4+, PEP 442 changed this — the GC CAN now collect objects with `__del__` in cycles. So in modern Python, this should actually work...

Wait, let me re-read the problem. The user says `__del__` never gets called. Let me think about what Python version could cause this.

Actually, even in Python 3.4+, there can be issues. Let me look more carefully. The problem might be more subtle — the `__del__` method itself captures a reference to the class (`Node._alive_count`), which isn't an issue.

Hmm, but in practice, even with PEP 442, the timing of `__del__` for cyclic objects is unpredictable. The real problem is that relying on `__del__` for resource cleanup in the presence of circular references is fundamentally fragile.

But the core learning here is: circular references + `__del__` = memory leak (or at least, unreliable cleanup). The fix is to either break the cycles explicitly or use `weakref` to avoid creating strong cycles.

Let me think about the proper fix:
1. Use `weakref.ref` for back-references so cycles don't form strong reference loops
2. Or implement an explicit `dispose()` / `clear()` method
3. Or use `weakref.WeakSet` for the neighbors list

The weakref approach is best — it lets the GC do its job without `__del__` complications.

Actually, for the neighbors case, we want bidirectional edges. One approach: store neighbors as weak references. But `weakref.ref` to each neighbor means we need to handle dead references. A `WeakSet` is cleaner.

Let me verify: with `weakref.WeakSet`, when a node is deleted, its entries automatically disappear from other nodes' neighbor sets. No cycle to break.
</think>

The bug is a **circular reference cycle combined with `__del__`**. Nodes A, B, and C reference each other through their `neighbors` lists, forming a cycle. In Python < 3.4, the garbage collector **refuses to collect** objects in a reference cycle if any of them define `__del__`, because it can't determine a safe finalization order. They get shunted to `gc.garbage` and leak forever.

Even in Python 3.4+ (PEP 442), relying on `__del__` with circular references is fragile — the timing is unpredictable and the design is fundamentally brittle.

**Fixed code:**

```python
import gc
import weakref

class Node:
    _alive_count = 0

    def __init__(self, name):
        self.name = name
        self.neighbors = weakref.WeakSet()  # FIX: weak references break cycles
        Node._alive_count += 1

    def connect(self, other):
        self.neighbors.add(other)
        other.neighbors.add(self)

    def __del__(self):
        Node._alive_count -= 1

    def __repr__(self):
        neighbor_names = [n.name for n in self.neighbors]
        return f"Node({self.name}, neighbors={neighbor_names})"

    # Required for WeakSet
    def __hash__(self):
        return hash(self.name)

def build_graph():
    a = Node("A")
    b = Node("B")
    c = Node("C")
    a.connect(b)
    b.connect(c)
    c.connect(a)
    return [a, b, c]


# ---------- Test ----------
nodes = build_graph()
print(f"Before delete: {Node._alive_count} nodes alive")

# Verify connectivity still works
assert len(list(nodes[0].neighbors)) == 2  # A connected to B and C

del nodes
gc.collect()
print(f"After delete + gc: {Node._alive_count} nodes alive")
assert Node._alive_count == 0, f"LEAK: {Node._alive_count} nodes still alive"
print("PASS: all nodes collected, no memory leak")
```

`weakref.WeakSet` stores weak references to neighbors, so the cycle doesn't prevent garbage collection. When a node's last strong reference disappears, the GC reclaims it immediately, and the weak references in other nodes' `WeakSet`s automatically become invalid and are cleaned up.'''
    ),

    # -------------------------------------------------------------------------
    # 10. Silent data corruption from float precision in financial calc
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-float-precision-financial",
        r'''My shopping cart total is occasionally wrong by a penny. I can't reproduce it consistently. What's the bug?

```python
def calculate_total(items):
    """Calculate total with tax and discount.
    items: list of (name, price, quantity, tax_rate)
    """
    subtotal = 0.0
    for name, price, qty, tax_rate in items:
        line_total = price * qty
        tax = line_total * tax_rate
        subtotal += line_total + tax

    # 10% discount if over $100
    if subtotal > 100:
        discount = subtotal * 0.10
        subtotal -= discount

    return round(subtotal, 2)

# Test
items = [
    ("Widget A", 19.99, 3, 0.08),
    ("Widget B", 9.99, 2, 0.08),
    ("Widget C", 0.10, 1, 0.08),
]
total = calculate_total(items)
print(f"Total: ${total}")
# Manual calculation:
# A: 19.99*3 = 59.97, tax = 4.7976 -> 64.7676
# B: 9.99*2 = 19.98, tax = 1.5984 -> 21.5784
# C: 0.10*1 = 0.10, tax = 0.008 -> 0.108
# Subtotal = 86.4540
# < $100, no discount
# Expected: $86.45
```''',
        r'''<think>
Let me trace through this calculation with actual float arithmetic, paying attention to precision.

The user says the total is sometimes wrong by a penny. This is the classic floating-point representation problem. Let me compute what Python actually gets:

19.99 * 3 = ? In IEEE 754: 19.99 cannot be represented exactly. It's actually 19.989999999999998... So 19.99 * 3 might not be exactly 59.97.

Let me think about where the rounding error accumulates:
- Each multiplication introduces a small error
- Adding the tax (another multiplication) adds more error
- Summing everything accumulates errors
- The final `round(subtotal, 2)` might round the wrong way if the accumulated error pushes the value just above or below the .5 cent boundary

For example, 0.1 + 0.2 = 0.30000000000000004 in Python. Similarly, 19.99 * 3 = 59.970000000000006 (not exactly 59.97).

The root cause: IEEE 754 floats cannot exactly represent most decimal values (like 0.10, 19.99, etc.). Each operation introduces tiny errors that accumulate, and `round()` at the very end sometimes rounds the wrong way.

The fix: use `decimal.Decimal` for financial calculations, which represents decimal numbers exactly. Or at minimum, round each line item to cents before accumulating.

Actually, there's also a subtlety: the single `round()` at the end is not the same as rounding each intermediate step. In real financial systems, you round each line item's tax to the penny, THEN sum. This matches how tax is actually calculated (you don't pay fractional cents on a line item).

Let me verify with Decimal:
- Decimal("19.99") * 3 = Decimal("59.97") — exact
- Decimal("59.97") * Decimal("0.08") = Decimal("4.7976")
- Round to cents: Decimal("4.80")
- Line total: Decimal("64.77")

This gives the correct, predictable result every time.
</think>

The bug is **floating-point precision errors** accumulating across multiple operations. IEEE 754 cannot exactly represent values like `19.99`, `0.10`, or `0.08`. Each multiplication introduces a tiny error, and by the time you `round()` at the end, the accumulated error can push a value like `$86.445` to `$86.4449999...` (rounds to `$86.44`) or `$86.4450000...01` (rounds to `$86.45`). The result is non-deterministic-looking penny errors.

A second issue: in real financial systems, tax is rounded to the penny **per line item**, not summed as fractional cents and rounded once at the end.

**Fixed code:**

```python
from decimal import Decimal, ROUND_HALF_UP

def to_cents(d):
    """Round a Decimal to 2 decimal places (nearest cent)."""
    return d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def calculate_total(items):
    """Calculate total with tax and discount using exact decimal arithmetic.
    items: list of (name, price_str, quantity, tax_rate_str)
    """
    subtotal = Decimal("0.00")
    for name, price, qty, tax_rate in items:
        price = Decimal(str(price))
        tax_rate = Decimal(str(tax_rate))
        line_total = to_cents(price * qty)          # FIX: round per line
        tax = to_cents(line_total * tax_rate)        # FIX: round tax per line
        subtotal += line_total + tax

    # 10% discount if over $100
    if subtotal > Decimal("100.00"):
        discount = to_cents(subtotal * Decimal("0.10"))
        subtotal -= discount

    return to_cents(subtotal)


# ---------- Test ----------
items = [
    ("Widget A", 19.99, 3, 0.08),
    ("Widget B", 9.99, 2, 0.08),
    ("Widget C", 0.10, 1, 0.08),
]
total = calculate_total(items)
# Manual: A=59.97+4.80=64.77, B=19.98+1.60=21.58, C=0.10+0.01=0.11
# Subtotal = 86.46 (no discount)
print(f"Total: ${total}")
assert total == Decimal("86.46"), f"Wrong total: {total}"

# Stress test: the classic 0.1 + 0.2 problem
assert Decimal("0.1") + Decimal("0.2") == Decimal("0.3")
print("PASS: all totals exact")
```

The rule for financial code: **never use `float`**. Use `decimal.Decimal` with string inputs (e.g., `Decimal("19.99")`, not `Decimal(19.99)` which captures the float error). Round each intermediate step to cents, matching real-world tax calculation rules.'''
    ),

    # -------------------------------------------------------------------------
    # 11. Deadlock from nested lock acquisition in wrong order
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-nested-lock-deadlock",
        r'''My bank transfer function deadlocks intermittently when two transfers happen simultaneously. It works fine if transfers are sequential. What's the bug?

```python
import threading
import time

class BankAccount:
    def __init__(self, name, balance):
        self.name = name
        self.balance = balance
        self.lock = threading.Lock()

    def __repr__(self):
        return f"BankAccount({self.name}, ${self.balance})"

def transfer(from_account, to_account, amount):
    """Transfer amount from one account to another."""
    with from_account.lock:
        time.sleep(0.001)  # simulate processing
        with to_account.lock:
            if from_account.balance >= amount:
                from_account.balance -= amount
                to_account.balance += amount
                return True
            return False

# Test
alice = BankAccount("Alice", 1000)
bob = BankAccount("Bob", 1000)

# Simultaneous transfers in both directions
t1 = threading.Thread(target=transfer, args=(alice, bob, 100))
t2 = threading.Thread(target=transfer, args=(bob, alice, 50))
t1.start()
t2.start()
t1.join(timeout=5)
t2.join(timeout=5)

if t1.is_alive() or t2.is_alive():
    print("DEADLOCK detected!")
else:
    print(f"Alice: ${alice.balance}, Bob: ${bob.balance}")
```''',
        r'''<think>
This is a classic ABBA deadlock. Let me trace through the concurrent execution:

Thread 1: transfer(alice, bob, 100)
- Acquires alice.lock
- Sleeps 0.001s
- Tries to acquire bob.lock... BLOCKED (T2 holds it)

Thread 2: transfer(bob, alice, 50)
- Acquires bob.lock
- Sleeps 0.001s
- Tries to acquire alice.lock... BLOCKED (T1 holds it)

Deadlock! T1 holds alice.lock, wants bob.lock. T2 holds bob.lock, wants alice.lock. Neither can proceed.

The sleep makes it very likely but not guaranteed — without the sleep, one thread might finish before the other starts. The fundamental issue is that the two threads acquire the same two locks in DIFFERENT orders.

The fix: always acquire locks in a CONSISTENT global order, regardless of transfer direction. A common approach is to order by object id (or account number, or any stable unique identifier).

If we always lock the account with the lower id() first, then:
- transfer(alice, bob): locks lower-id first, then higher-id
- transfer(bob, alice): locks lower-id first, then higher-id
Same order, no deadlock possible.

Let me also consider: what if from_account is the same as to_account? Self-transfer. With the id-based ordering, we'd try to acquire the same lock twice — and since it's a regular Lock (not RLock), that would deadlock. We should check for this edge case.

Let me verify my fix handles all cases: normal transfer, reverse transfer, and self-transfer.
</think>

This is a classic **ABBA deadlock**. The two threads acquire the same two locks in opposite order:

- Thread 1: locks Alice, then tries to lock Bob
- Thread 2: locks Bob, then tries to lock Alice

Each thread holds one lock and waits for the other. Neither can proceed.

The fix: **always acquire locks in a consistent global order** regardless of transfer direction. Using `id()` to establish ordering guarantees both threads lock in the same sequence.

**Fixed code:**

```python
import threading
import time

class BankAccount:
    def __init__(self, name, balance):
        self.name = name
        self.balance = balance
        self.lock = threading.Lock()

    def __repr__(self):
        return f"BankAccount({self.name}, ${self.balance})"

def transfer(from_account, to_account, amount):
    """Transfer amount from one account to another, deadlock-free."""
    if from_account is to_account:
        return False  # FIX: prevent self-transfer deadlock

    # FIX: always lock in consistent order (by object id)
    first, second = sorted([from_account, to_account], key=id)

    with first.lock:
        time.sleep(0.001)  # simulate processing
        with second.lock:
            if from_account.balance >= amount:
                from_account.balance -= amount
                to_account.balance += amount
                return True
            return False


# ---------- Test ----------
alice = BankAccount("Alice", 1000)
bob = BankAccount("Bob", 1000)

# Simultaneous transfers in both directions — would deadlock with old code
threads = []
for _ in range(50):
    t1 = threading.Thread(target=transfer, args=(alice, bob, 10))
    t2 = threading.Thread(target=transfer, args=(bob, alice, 10))
    threads.extend([t1, t2])

for t in threads:
    t.start()
for t in threads:
    t.join(timeout=5)
    assert not t.is_alive(), "DEADLOCK!"

# Conservation of money
total = alice.balance + bob.balance
assert total == 2000, f"Money not conserved: {total}"
print(f"PASS: Alice=${alice.balance}, Bob=${bob.balance}, Total=${total}")
```

The key insight: lock ordering by `id()` means both `transfer(alice, bob)` and `transfer(bob, alice)` acquire locks in the same order. No ABBA cycle is possible.'''
    ),

    # -------------------------------------------------------------------------
    # 12. Iterator invalidation — modifying dict during iteration
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-dict-modification-during-iteration",
        r'''My cache cleanup function randomly crashes with "dictionary changed size during iteration". Sometimes it works, sometimes it doesn't. What's wrong?

```python
import time

class ExpiringCache:
    def __init__(self, ttl_seconds=60):
        self.ttl = ttl_seconds
        self.store = {}  # key -> (value, timestamp)

    def put(self, key, value):
        self.store[key] = (value, time.time())

    def get(self, key):
        if key in self.store:
            value, ts = self.store[key]
            if time.time() - ts < self.ttl:
                return value
            else:
                del self.store[key]
        return None

    def cleanup(self):
        """Remove all expired entries."""
        now = time.time()
        for key in self.store:
            value, ts = self.store[key]
            if now - ts >= self.ttl:
                del self.store[key]

    def size(self):
        return len(self.store)
```''',
        r'''<think>
Let me trace through the `cleanup` method.

`for key in self.store:` — this iterates over the dictionary's keys using an iterator. Inside the loop, `del self.store[key]` deletes an entry from the dictionary. In Python 3, modifying a dictionary's size while iterating over it raises `RuntimeError: dictionary changed size during iteration`.

The "sometimes works" aspect: if NO entries are expired, no deletions happen, and it works fine. If ALL entries are expired, it might crash on the first or second deletion. The behavior is deterministic for a given set of entries, but appears random because it depends on which entries have expired.

There's also a subtlety in `get()` — it deletes expired entries individually, which is fine because it's not inside a dict iteration loop. But if `get()` were called during `cleanup()`'s iteration from another thread, that would also cause the error. However, since there's no threading shown, the primary bug is the iteration+deletion in `cleanup()`.

Fix: iterate over a snapshot of the keys. `list(self.store.keys())` creates a list copy. Then deletions don't affect the iteration because we're iterating over the list, not the dict.

Alternative: build a list of keys to delete, then delete them after the loop. Same effect.

Or use a dict comprehension to build a new dict with only non-expired entries.

Let me verify: `for key in list(self.store):` creates a copy of the keys. Deleting from `self.store` during this loop is safe because the `list(...)` is a separate object.
</think>

The bug is in `cleanup()`: you're deleting entries from `self.store` **while iterating over it**. Python 3 raises `RuntimeError: dictionary changed size during iteration` when you modify a dict's size during iteration. It "sometimes works" because if no entries are expired, no deletion happens and the iterator isn't invalidated.

**Fixed code:**

```python
import time

class ExpiringCache:
    def __init__(self, ttl_seconds=60):
        self.ttl = ttl_seconds
        self.store = {}

    def put(self, key, value):
        self.store[key] = (value, time.time())

    def get(self, key):
        if key in self.store:
            value, ts = self.store[key]
            if time.time() - ts < self.ttl:
                return value
            else:
                del self.store[key]
        return None

    def cleanup(self):
        """Remove all expired entries."""
        now = time.time()
        # FIX: iterate over a snapshot of the keys, not the live dict
        expired_keys = [
            key for key, (value, ts) in self.store.items()
            if now - ts >= self.ttl
        ]
        for key in expired_keys:
            del self.store[key]

    def size(self):
        return len(self.store)


# ---------- Test ----------
cache = ExpiringCache(ttl_seconds=0.05)

# Add entries
for i in range(20):
    cache.put(f"key_{i}", f"value_{i}")

assert cache.size() == 20

# Wait for expiry
time.sleep(0.1)

# Add some fresh entries
cache.put("fresh_1", "alive")
cache.put("fresh_2", "alive")

# This would crash with the old code
cache.cleanup()

assert cache.size() == 2, f"Expected 2 fresh entries, got {cache.size()}"
assert cache.get("fresh_1") == "alive"
assert cache.get("key_0") is None
print(f"PASS: cleanup removed expired entries, {cache.size()} remain")
```

The fix collects expired keys into a separate list first, then deletes them. Since we iterate over the list (not the dict), modifications to the dict are safe.'''
    ),

    # -------------------------------------------------------------------------
    # 13. TOCTOU race in file operations
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-toctou-race-file-operations",
        r'''My file processing script occasionally overwrites files or crashes with FileNotFoundError even though I check if the file exists first. What's the bug?

```python
import os
import shutil

def safe_process_file(src_path, dest_dir):
    """Process a file: move to dest_dir, but don't overwrite existing files."""
    if not os.path.exists(src_path):
        print(f"Source not found: {src_path}")
        return False

    dest_path = os.path.join(dest_dir, os.path.basename(src_path))

    if os.path.exists(dest_path):
        print(f"Destination already exists: {dest_path}")
        return False

    # File exists at src and doesn't exist at dest, safe to move
    os.makedirs(dest_dir, exist_ok=True)
    shutil.move(src_path, dest_path)
    return True

def safe_write_file(path, content):
    """Write content to a file, but only if it doesn't already exist."""
    if not os.path.exists(path):
        with open(path, "w") as f:
            f.write(content)
        return True
    return False
```''',
        r'''<think>
Both functions have TOCTOU (Time-of-Check to Time-of-Use) races.

In `safe_process_file`:
1. Check `os.path.exists(src_path)` -> True
2. Between check and `shutil.move()`, another process could delete `src_path` -> FileNotFoundError
3. Check `os.path.exists(dest_path)` -> False
4. Between check and `shutil.move()`, another process could create `dest_path` -> overwrites it (or fails depending on OS)

In `safe_write_file`:
1. Check `os.path.exists(path)` -> False
2. Between check and `open(path, "w")`, another process could create the file -> silently overwritten

The root cause: the check and the action are separate operations with a window between them where the filesystem state can change. This is the classic TOCTOU pattern.

Fixes:
- For `safe_write_file`: use `open(path, "x")` (exclusive create mode) — it atomically creates the file and raises FileExistsError if it already exists. No race window.
- For `safe_process_file`: this is harder. `shutil.move` doesn't have an atomic "move only if destination doesn't exist" mode. Options:
  1. Use `os.rename()` which is atomic on the same filesystem, but raises FileExistsError on Windows if dest exists (on Linux it silently overwrites)
  2. Use `os.link()` to create a hard link at dest (atomic, fails if dest exists), then `os.unlink()` the source
  3. Use a lock file for coordination
  4. Use try/except around the move

The most portable approach for the move: try the operation and handle the exceptions, rather than checking first. EAFP (Easier to Ask Forgiveness than Permission) over LBYL (Look Before You Leap).

For the source-not-found case, just catch FileNotFoundError from the move itself.
</think>

Both functions have **TOCTOU (Time-of-Check to Time-of-Use) race conditions**. Between the `os.path.exists()` check and the actual operation, another process can change the filesystem state. This causes:
- `FileNotFoundError` when the source is deleted between check and move
- Silent overwrites when the destination is created between check and write/move

The fix: **don't check-then-act**. Use atomic operations or catch exceptions (EAFP pattern).

**Fixed code:**

```python
import os
import shutil
import tempfile

def safe_process_file(src_path, dest_dir):
    """Process a file: move to dest_dir, but don't overwrite existing files."""
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, os.path.basename(src_path))

    try:
        # FIX: Use a two-step atomic approach
        # Step 1: create a unique temp file in dest_dir to "claim" the name
        # Step 2: atomically rename source to dest

        # On POSIX: os.link + os.unlink is atomic
        # Portable fallback: open with exclusive create to claim dest, then move
        fd = os.open(dest_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(fd)
    except FileExistsError:
        print(f"Destination already exists: {dest_path}")
        return False

    try:
        # We now "own" dest_path (created exclusively). Replace it with the move.
        shutil.move(src_path, dest_path)
        return True
    except FileNotFoundError:
        # Source was deleted between our claim and the move
        os.unlink(dest_path)  # clean up our placeholder
        print(f"Source vanished: {src_path}")
        return False

def safe_write_file(path, content):
    """Write content to a file, but only if it doesn't already exist."""
    try:
        # FIX: 'x' mode = exclusive create — atomic, fails if file exists
        with open(path, "x") as f:
            f.write(content)
        return True
    except FileExistsError:
        return False


# ---------- Test ----------
import tempfile

with tempfile.TemporaryDirectory() as tmpdir:
    # Test safe_write_file
    test_file = os.path.join(tmpdir, "test.txt")
    assert safe_write_file(test_file, "hello") is True
    assert safe_write_file(test_file, "overwrite") is False  # already exists
    with open(test_file) as f:
        assert f.read() == "hello"  # original content preserved

    # Test safe_process_file
    src = os.path.join(tmpdir, "source.txt")
    dest_dir = os.path.join(tmpdir, "dest")
    with open(src, "w") as f:
        f.write("data")

    assert safe_process_file(src, dest_dir) is True
    assert not os.path.exists(src)  # moved
    assert os.path.exists(os.path.join(dest_dir, "source.txt"))

    # Trying again with same dest — should fail (dest exists)
    with open(src, "w") as f:
        f.write("data2")
    assert safe_process_file(src, dest_dir) is False

    print("PASS: no TOCTOU races")
```

Key lessons: Use `open(path, "x")` for exclusive file creation. Use `os.open()` with `O_CREAT | O_EXCL` flags for atomic file claiming. Never use `os.path.exists()` as a guard before a filesystem mutation.'''
    ),

    # -------------------------------------------------------------------------
    # 14. Signal handler re-entrancy bug
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-signal-handler-reentrancy",
        r'''My graceful shutdown handler sometimes corrupts data or deadlocks. It works fine when I ctrl+C once, but rapidly pressing ctrl+C causes issues. What's wrong?

```python
import signal
import time
import json

class Server:
    def __init__(self):
        self.running = True
        self.data = []
        self.save_in_progress = False

    def save_data(self):
        """Save accumulated data to disk."""
        self.save_in_progress = True
        print(f"Saving {len(self.data)} items...")
        # Simulate slow write
        temp = list(self.data)
        time.sleep(0.1)
        with open("server_data.json", "w") as f:
            json.dump(temp, f)
        self.data.clear()
        self.save_in_progress = False
        print("Save complete")

    def handle_shutdown(self, signum, frame):
        """Handle SIGINT for graceful shutdown."""
        print("\nShutting down gracefully...")
        self.save_data()
        self.running = False

    def run(self):
        signal.signal(signal.SIGINT, self.handle_shutdown)
        while self.running:
            self.data.append({"timestamp": time.time()})
            if len(self.data) >= 100:
                self.save_data()
            time.sleep(0.01)

server = Server()
server.run()
```''',
        r'''<think>
Let me think about what happens when a signal handler is re-entered.

Signal handlers in Python can be interrupted by another signal. If the user presses Ctrl+C twice rapidly:

1. First SIGINT: `handle_shutdown` starts running, calls `save_data()`
2. During `save_data()` (which sleeps 0.1s), second SIGINT arrives
3. Python interrupts `save_data()` mid-execution and calls `handle_shutdown` AGAIN
4. The second `handle_shutdown` calls `save_data()` AGAIN

This means:
- `temp = list(self.data)` in the first call captured some data
- The second call also does `temp = list(self.data)` with the same data (data hasn't been cleared yet)
- Both calls write to the same file — the second write may overwrite the first, or they might interleave writes causing JSON corruption
- `self.data.clear()` could be called by the first handler after the second handler has already captured a reference to `self.data`
- The `save_in_progress` flag is not checked and is not atomic

There's also a subtle issue: `time.sleep()` in a signal handler is dangerous — the signal handler should do minimal work.

The fix:
1. Set a flag in the signal handler, do the actual shutdown in the main loop
2. Use `signal.signal(signal.SIGINT, signal.SIG_IGN)` inside the handler to prevent re-entrancy
3. Or set self.running = False in the handler and let the main loop do the save

The cleanest approach: the signal handler should ONLY set a flag. The main loop checks the flag and performs the save. This avoids all re-entrancy issues.
</think>

There are multiple bugs caused by **signal handler re-entrancy**:

1. **Re-entrant save**: A second SIGINT during `save_data()` (which takes 0.1s) re-enters `handle_shutdown`, calling `save_data()` again while the first is mid-write. This can corrupt the JSON file or lose data.

2. **Non-atomic flag**: `save_in_progress` is set but never checked — a second signal ignores it.

3. **Too much work in signal handler**: Signal handlers should do minimal work (set a flag). Doing I/O, sleeping, and mutating shared state in a handler is inherently unsafe.

**Fixed code:**

```python
import signal
import time
import json
import os

class Server:
    def __init__(self):
        self.running = True
        self.shutdown_requested = False
        self.data = []

    def save_data(self):
        """Save accumulated data to disk (called from main loop only)."""
        if not self.data:
            return
        print(f"Saving {len(self.data)} items...")
        temp = list(self.data)
        # Atomic write: write to temp file, then rename
        tmp_path = "server_data.json.tmp"
        with open(tmp_path, "w") as f:
            json.dump(temp, f)
        os.replace(tmp_path, "server_data.json")  # atomic on most OSes
        self.data.clear()
        print("Save complete")

    def handle_shutdown(self, signum, frame):
        """Signal handler: ONLY set a flag, do no real work."""
        if self.shutdown_requested:
            # Second Ctrl+C = force quit
            print("\nForced shutdown!")
            raise SystemExit(1)
        print("\nShutdown requested (Ctrl+C again to force)...")
        self.shutdown_requested = True  # FIX: just set the flag

    def run(self):
        signal.signal(signal.SIGINT, self.handle_shutdown)
        while self.running:
            # FIX: check shutdown flag in main loop
            if self.shutdown_requested:
                print("Performing graceful shutdown...")
                self.save_data()
                self.running = False
                break

            self.data.append({"timestamp": time.time()})
            if len(self.data) >= 100:
                self.save_data()
            time.sleep(0.01)
        print("Server stopped.")


# ---------- Demonstration ----------
# Can't easily unit-test signal handling, but we can test the save logic:
server = Server()
for i in range(50):
    server.data.append({"timestamp": time.time(), "i": i})

server.save_data()
with open("server_data.json") as f:
    loaded = json.load(f)
assert len(loaded) == 50
assert server.data == []

# Simulate shutdown request
server.shutdown_requested = True
server.data.append({"final": True})
# Main loop would catch the flag and save
server.save_data()
os.unlink("server_data.json")

print("PASS: signal-safe shutdown logic verified")
```

The golden rule: **signal handlers should only set flags**. All real work (I/O, cleanup, saves) belongs in the main loop where it cannot be re-entered by another signal.'''
    ),

    # -------------------------------------------------------------------------
    # 15. Exception swallowing hiding the real error
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-exception-swallowing",
        r'''My data pipeline silently produces empty results instead of reporting errors. I've added logging but can never see what goes wrong. What's the bug?

```python
import json
import logging

logger = logging.getLogger(__name__)

def fetch_data(url):
    """Simulate fetching data from an API."""
    if "invalid" in url:
        raise ConnectionError(f"Cannot connect to {url}")
    return '{"items": [1, 2, 3]}'

def parse_response(raw):
    """Parse JSON response."""
    try:
        data = json.loads(raw)
        return data["items"]
    except Exception:
        return []

def transform(items):
    """Double each item."""
    try:
        return [item * 2 for item in items]
    except Exception:
        return []

def pipeline(url):
    """Full data pipeline."""
    try:
        raw = fetch_data(url)
        items = parse_response(raw)
        result = transform(items)
        return result
    except Exception as e:
        logger.error(f"Pipeline failed: {e}")
        return []

# Test
print(pipeline("https://api.example.com/data"))    # [2, 4, 6] -- works
print(pipeline("https://api.example.com/invalid"))  # [] -- but WHY?

# Worse: silently wrong
def parse_response_v2(raw):
    try:
        data = json.loads(raw)
        return data["results"]  # BUG: wrong key, should be "items"
    except Exception:
        return []

# This silently returns [] instead of telling us "results" key doesn't exist
```''',
        r'''<think>
The bug is bare `except Exception` blocks that catch ALL exceptions and return empty defaults. This is the "exception swallowing" anti-pattern. Let me trace through:

1. `pipeline("https://api.example.com/invalid")`:
   - `fetch_data()` raises `ConnectionError`
   - The outer try/except in `pipeline` catches it, logs it, returns `[]`
   - This one actually logs! So it's partially visible.

2. But `parse_response` with the wrong key `data["results"]`:
   - `json.loads(raw)` succeeds
   - `data["results"]` raises `KeyError`
   - The bare `except Exception: return []` swallows the KeyError silently
   - No logging, no indication of what went wrong
   - Pipeline gets `[]` and happily transforms it to `[]`

The problem is pervasive:
- `parse_response` catches ALL exceptions including programming errors (KeyError, TypeError, AttributeError)
- `transform` catches ALL exceptions — even things like `NameError` from typos
- The error is invisible because the empty list is a "valid" result

This is one of the most damaging anti-patterns in Python. It turns every bug into mysterious "empty results" with no stack trace.

Fix:
1. Catch SPECIFIC exceptions you can handle
2. Log or re-raise everything else
3. Use custom exception types for expected failures
4. Never return a default value from a bare except
</think>

The bug is the **exception swallowing anti-pattern**: bare `except Exception: return []` blocks catch ALL exceptions — including programming errors like `KeyError`, `TypeError`, `AttributeError` — and silently replace them with empty results. The real error is hidden forever.

In `parse_response_v2`, `data["results"]` raises `KeyError` (wrong key name), but the except block catches it and returns `[]`. You'll never know the key name is wrong. You'll just stare at empty results wondering why.

**Fixed code:**

```python
import json
import logging

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class PipelineError(Exception):
    """Base exception for pipeline failures."""
    pass

class FetchError(PipelineError):
    pass

class ParseError(PipelineError):
    pass

def fetch_data(url):
    """Simulate fetching data from an API."""
    try:
        if "invalid" in url:
            raise ConnectionError(f"Cannot connect to {url}")
        return '{"items": [1, 2, 3]}'
    except ConnectionError as e:
        # FIX: wrap in domain exception, preserve original
        raise FetchError(f"Failed to fetch {url}") from e

def parse_response(raw):
    """Parse JSON response."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        # FIX: catch ONLY the specific exception we expect
        raise ParseError(f"Invalid JSON: {e}") from e

    # FIX: don't catch KeyError — a missing key is a BUG, not a handled case
    if "items" not in data:
        raise ParseError(f"Response missing 'items' key. Keys found: {list(data.keys())}")
    return data["items"]

def transform(items):
    """Double each item."""
    # FIX: no try/except at all — if this fails, it's a bug that should propagate
    return [item * 2 for item in items]

def pipeline(url):
    """Full data pipeline."""
    try:
        raw = fetch_data(url)
        items = parse_response(raw)
        result = transform(items)
        return result
    except PipelineError as e:
        # FIX: catch only EXPECTED domain errors, log with full chain
        logger.error(f"Pipeline failed: {e}", exc_info=True)
        return []
    # Let unexpected errors (TypeError, AttributeError, etc.) propagate!


# ---------- Test ----------
# Normal case
result = pipeline("https://api.example.com/data")
assert result == [2, 4, 6], f"Expected [2,4,6], got {result}"

# Connection error — properly logged
result = pipeline("https://api.example.com/invalid")
assert result == []

# Wrong key — now this FAILS LOUDLY instead of silently returning []
bad_json = '{"results": [1, 2, 3]}'
try:
    parse_response(bad_json)
    assert False, "Should have raised ParseError"
except ParseError as e:
    assert "missing 'items' key" in str(e)
    print(f"Correctly caught: {e}")

print("PASS: errors are visible, not swallowed")
```

Rules for exception handling:
1. **Catch specific exceptions** — never bare `except Exception`
2. **Preserve the chain** — use `raise X from e` so the original traceback is visible
3. **Let bugs propagate** — `KeyError`, `TypeError`, `AttributeError` are usually bugs, not expected conditions
4. **Log with `exc_info=True`** to get the full stack trace'''
    ),

    # -------------------------------------------------------------------------
    # 16. Incorrect __eq__ without __hash__ causing dict/set bugs
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-eq-without-hash",
        r'''My deduplication logic using a set doesn't work — duplicates still appear. And my dict lookups sometimes fail even though the key exists. What's wrong?

```python
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __eq__(self, other):
        if not isinstance(other, Point):
            return NotImplemented
        return self.x == other.x and self.y == other.y

    def __repr__(self):
        return f"Point({self.x}, {self.y})"

# Deduplication
points = [Point(1, 2), Point(3, 4), Point(1, 2), Point(5, 6), Point(3, 4)]
unique = set(points)
print(f"Unique points: {unique}")
# Expected: 3 unique points
# Actual: 5 (no deduplication!)

# Dict lookup
cache = {}
p1 = Point(1, 2)
cache[p1] = "cached_value"
p2 = Point(1, 2)  # same logical point
print(cache.get(p2))  # Expected: "cached_value", Actual: None
```''',
        r'''<think>
This is the classic `__eq__` without `__hash__` bug.

In Python, when you define `__eq__`, Python automatically sets `__hash__` to `None`, making the class unhashable... wait, actually in Python 3, if you define `__eq__` without `__hash__`, the class becomes unhashable. Let me reconsider.

Actually, in Python 3, if you define `__eq__` but NOT `__hash__`, Python sets `__hash__ = None`. This makes instances unhashable. But wait — if that were the case, `set(points)` would raise `TypeError: unhashable type: 'Point'`, not silently fail at deduplication.

Hmm, let me reconsider. Actually, in Python 3:
- If a class defines neither `__eq__` nor `__hash__`, it inherits both from `object`. `object.__hash__` uses `id()`.
- If a class defines `__eq__` but not `__hash__`, Python sets `__hash__ = None`, making instances unhashable.

So `set(points)` should raise `TypeError`. But the user says duplicates appear... unless they're running Python 2 where behavior differs.

Wait, actually, I need to test this. In Python 3, defining `__eq__` does indeed set `__hash__` to None. So `set(points)` would raise TypeError, not silently keep duplicates.

Let me reconsider the scenario. Perhaps the user's actual experience is the TypeError, or perhaps they have a different Python version. For training purposes, let me address both:

1. In Python 3: `set(points)` raises `TypeError: unhashable type: 'Point'`
2. The fix is to implement `__hash__` consistent with `__eq__`

Actually wait — let me re-examine. Some Python 3 versions might handle this differently. In CPython 3.x, if `__eq__` is defined and `__hash__` is not, `__hash__` is set to None. `set()` will raise TypeError.

For the training pair, the core lesson is: you MUST define `__hash__` when you define `__eq__` if you want to use the class in sets or as dict keys. The hash must be consistent with equality.

Let me adjust my analysis: the code raises TypeError, not silently fails. The user's description of "duplicates still appear" might be their interpretation of the error, or they might have a workaround that uses `id()`-based hash.
</think>

In Python 3, when you define `__eq__` without `__hash__`, Python sets `__hash__ = None`, making instances **unhashable**. Attempting `set(points)` or using a Point as a dict key raises `TypeError: unhashable type: 'Point'`.

If you remove `__eq__` (or explicitly set `__hash__ = object.__hash__`), the default `id()`-based hash is used — each instance has a unique hash regardless of its values, so `Point(1, 2) != Point(1, 2)` from a hash perspective, and deduplication/lookup fails.

Either way, you need `__hash__` to be **consistent with `__eq__`**: equal objects must have the same hash.

**Fixed code:**

```python
class Point:
    def __init__(self, x, y):
        self.x = x
        self.y = y

    def __eq__(self, other):
        if not isinstance(other, Point):
            return NotImplemented
        return self.x == other.x and self.y == other.y

    def __hash__(self):
        # FIX: implement __hash__ consistent with __eq__
        return hash((self.x, self.y))

    def __repr__(self):
        return f"Point({self.x}, {self.y})"


# ---------- Test ----------
# Deduplication
points = [Point(1, 2), Point(3, 4), Point(1, 2), Point(5, 6), Point(3, 4)]
unique = set(points)
assert len(unique) == 3, f"Expected 3 unique, got {len(unique)}: {unique}"

# Dict lookup
cache = {}
p1 = Point(1, 2)
cache[p1] = "cached_value"
p2 = Point(1, 2)  # different object, same value
assert cache.get(p2) == "cached_value", f"Lookup failed: {cache.get(p2)}"

# Verify consistency: equal objects must have the same hash
assert p1 == p2
assert hash(p1) == hash(p2)

# Verify non-equal objects can (but don't have to) have different hashes
p3 = Point(9, 9)
assert p1 != p3

print(f"PASS: unique={unique}, cache lookup={cache[p2]}")
```

The contract: **if `a == b`, then `hash(a) == hash(b)`**. The reverse doesn't need to hold (hash collisions are fine). Use a tuple of the fields that participate in `__eq__` as the hash input.

Important caveat: **mutable objects used as dict keys are dangerous**. If you mutate `p1.x` after inserting it into a dict, the hash changes and the key becomes unfindable. If the object is mutable, consider making it immutable (or use `@dataclass(frozen=True)` which auto-generates both `__eq__` and `__hash__`).'''
    ),

    # -------------------------------------------------------------------------
    # 17. Threading bug: checking-then-acting without atomicity
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-check-then-act-threading",
        r'''My thread-safe counter with a maximum value sometimes exceeds the maximum under concurrent access. What's wrong?

```python
import threading

class BoundedCounter:
    def __init__(self, max_value):
        self.value = 0
        self.max_value = max_value
        self.lock = threading.Lock()

    def increment(self):
        """Increment if below max. Returns True if successful."""
        with self.lock:
            current = self.value
        # Check outside the lock
        if current < self.max_value:
            with self.lock:
                self.value = current + 1
            return True
        return False

    def get(self):
        with self.lock:
            return self.value

def stress_test():
    counter = BoundedCounter(max_value=100)
    results = {"success": 0, "rejected": 0}
    results_lock = threading.Lock()

    def worker():
        for _ in range(50):
            if counter.increment():
                with results_lock:
                    results["success"] += 1
            else:
                with results_lock:
                    results["rejected"] += 1

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    print(f"Counter: {counter.get()}, Success: {results['success']}, Rejected: {results['rejected']}")
    # Expected: Counter <= 100
    # Actual: Counter can be >> 100!

stress_test()
```''',
        r'''<think>
Let me trace through the `increment` method carefully.

```python
def increment(self):
    with self.lock:
        current = self.value    # Step 1: read (under lock)
    # Lock released here!
    if current < self.max_value: # Step 2: check (NO lock)
        with self.lock:
            self.value = current + 1  # Step 3: write (under lock)
        return True
    return False
```

The read and write are individually atomic (each is under the lock), but the CHECK between them is NOT atomic with either operation. The lock is released between reading and writing.

Scenario with max_value=100 and value=99:
- Thread A: reads current=99, releases lock
- Thread B: reads current=99, releases lock
- Thread C: reads current=99, releases lock
- Thread A: 99 < 100 is True, sets value=100
- Thread B: 99 < 100 is True, sets value=100 (should be 101, but it's using stale `current=99`)

Wait, actually it's even worse. Thread B sets `self.value = current + 1 = 99 + 1 = 100`. Thread A already set it to 100 too. So the value is 100 but two increments were counted as successful. But we lose a count.

Actually, let me re-trace. With 10 threads * 50 = 500 attempts and max=100:
- Many threads can read the same value simultaneously
- Multiple threads can pass the `< max_value` check with the same value
- They all write `current + 1` where `current` is the SAME stale value
- This means some increments are lost (two threads both set value from 50 to 51)
- AND the max check can be bypassed (multiple threads read 99, all proceed to write 100)

Wait, will the value actually EXCEED 100? Let me think again...

If all threads read current=99, they all check 99 < 100 = True, and they all set self.value = 100. The value stays at 100 (not exceeded) but we counted multiple "successes" at the boundary.

But what about earlier values? Thread A reads 50, Thread B reads 50. Both set value=51. We counted 2 successes but only incremented by 1. So later, there are "extra" successes that shouldn't have happened, and the counter might actually never reach 100 because increments are lost, allowing more successes before hitting the cap.

Actually the bug manifests in two ways:
1. Lost increments: two threads read 50, both write 51, counter only went up by 1 but 2 successes counted
2. This means the counter reaches 100 slower, allowing MORE than 100 successful increments total

So `results["success"]` can be > 100 even if `counter.value` is <= 100. The counter value might not exceed max, but the number of "successful" increments does exceed max because of lost updates.

The fix: the entire read-check-write must be atomic — all under a single lock acquisition.
</think>

The bug is a **check-then-act race** — the read, check, and write are under separate lock acquisitions with gaps between them.

```python
with self.lock:
    current = self.value     # READ (locked)
# <-- lock released, other threads can read the same value
if current < self.max_value: # CHECK (unlocked!)
    with self.lock:
        self.value = current + 1  # WRITE (locked, but uses stale value)
```

**What happens:** Multiple threads read the same value (e.g., 50), all pass the check, all write 51. Result: multiple "successful" increments but the counter only increases by 1. Total successful increments exceeds `max_value` because lost updates allow more threads through the gate.

**Fixed code:**

```python
import threading

class BoundedCounter:
    def __init__(self, max_value):
        self.value = 0
        self.max_value = max_value
        self.lock = threading.Lock()

    def increment(self):
        """Increment if below max. Returns True if successful."""
        # FIX: read, check, and write must ALL be under the SAME lock
        with self.lock:
            if self.value < self.max_value:
                self.value += 1
                return True
            return False

    def get(self):
        with self.lock:
            return self.value


# ---------- Test ----------
def stress_test():
    counter = BoundedCounter(max_value=100)
    success_count = 0
    count_lock = threading.Lock()

    def worker():
        nonlocal success_count
        local_success = 0
        for _ in range(50):
            if counter.increment():
                local_success += 1
        with count_lock:
            success_count += local_success

    threads = [threading.Thread(target=worker) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    final = counter.get()
    print(f"Counter: {final}, Successes: {success_count}")
    # 10 threads * 50 attempts = 500 attempts, but max is 100
    assert final == 100, f"Counter should be exactly 100, got {final}"
    assert success_count == 100, f"Successes should be exactly 100, got {success_count}"
    print("PASS: bounded counter is correctly thread-safe")

stress_test()
```

The rule: **the entire read-check-write sequence must be atomic**. If you release the lock between any of these steps, another thread can interleave and invalidate your check.'''
    ),

    # -------------------------------------------------------------------------
    # 18. asyncio.gather exception handling
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-asyncio-gather-exceptions",
        r'''My parallel API fetcher loses successful results when one request fails. I want all results that succeeded, not just an all-or-nothing. What's wrong?

```python
import asyncio

async def fetch_api(url: str) -> dict:
    """Simulate API fetch."""
    await asyncio.sleep(0.01)
    if "fail" in url:
        raise ConnectionError(f"Failed to connect: {url}")
    return {"url": url, "data": "OK"}

async def fetch_all(urls: list[str]) -> list[dict]:
    """Fetch all URLs in parallel, return results."""
    tasks = [fetch_api(url) for url in urls]
    try:
        results = await asyncio.gather(*tasks)
        return results
    except Exception as e:
        print(f"Error: {e}")
        return []

async def main():
    urls = [
        "https://api.example.com/users",
        "https://api.example.com/fail_orders",
        "https://api.example.com/products",
        "https://api.example.com/fail_inventory",
        "https://api.example.com/reviews",
    ]
    results = await fetch_all(urls)
    print(f"Got {len(results)} results")
    for r in results:
        print(r)

asyncio.run(main())
```''',
        r'''<think>
Let me trace through the behavior of `asyncio.gather()` when exceptions occur.

Without `return_exceptions=True`, `asyncio.gather()` raises the FIRST exception it encounters. When one task fails:

1. `asyncio.gather(*tasks)` starts all 5 tasks concurrently
2. "fail_orders" raises ConnectionError
3. `gather` propagates this exception immediately
4. The try/except catches it, prints "Error:", and returns `[]`
5. ALL successful results are LOST — even though users, products, and reviews completed fine

The other tasks might still be running in the background (they're not automatically cancelled by gather in Python < 3.12 without a TaskGroup). So we also have potential resource leaks.

The user wants partial results — all successes plus information about failures.

Fix options:
1. Use `return_exceptions=True` — exceptions are returned as values in the result list, not raised
2. Use `asyncio.TaskGroup` (Python 3.11+) for better semantics
3. Wrap each coroutine to catch its own exceptions

Option 1 is simplest and most compatible. With `return_exceptions=True`, we get a list where each element is either the result or the exception. We then filter.

Let me also note: the cancelled tasks issue. Without `return_exceptions=True`, gather cancels remaining tasks when one fails (in Python 3.9+). With `return_exceptions=True`, all tasks run to completion.
</think>

The bug: `asyncio.gather()` without `return_exceptions=True` raises the **first exception** and discards all successful results. You get either all results or nothing — one failure means zero results.

Additionally, the other tasks may still be running in the background, wasting resources.

**Fixed code:**

```python
import asyncio
from dataclasses import dataclass
from typing import Any

@dataclass
class Success:
    url: str
    data: Any

@dataclass
class Failure:
    url: str
    error: Exception

async def fetch_api(url: str) -> dict:
    """Simulate API fetch."""
    await asyncio.sleep(0.01)
    if "fail" in url:
        raise ConnectionError(f"Failed to connect: {url}")
    return {"url": url, "data": "OK"}

async def safe_fetch(url: str):
    """Wrap a fetch to never raise — return Success or Failure."""
    try:
        result = await fetch_api(url)
        return Success(url=url, data=result)
    except Exception as e:
        return Failure(url=url, error=e)

async def fetch_all(urls: list[str]) -> tuple[list[Success], list[Failure]]:
    """Fetch all URLs in parallel. Returns (successes, failures)."""
    tasks = [safe_fetch(url) for url in urls]
    # FIX: return_exceptions=True so one failure doesn't kill everything
    results = await asyncio.gather(*tasks)

    successes = [r for r in results if isinstance(r, Success)]
    failures = [r for r in results if isinstance(r, Failure)]
    return successes, failures

async def main():
    urls = [
        "https://api.example.com/users",
        "https://api.example.com/fail_orders",
        "https://api.example.com/products",
        "https://api.example.com/fail_inventory",
        "https://api.example.com/reviews",
    ]
    successes, failures = await fetch_all(urls)

    print(f"Successes: {len(successes)}, Failures: {len(failures)}")
    for s in successes:
        print(f"  OK: {s.url}")
    for f in failures:
        print(f"  FAIL: {f.url} -> {f.error}")

    # Verify: 3 successes, 2 failures
    assert len(successes) == 3, f"Expected 3 successes, got {len(successes)}"
    assert len(failures) == 2, f"Expected 2 failures, got {len(failures)}"
    print("PASS")

asyncio.run(main())
```

The pattern: wrap each coroutine in a `safe_fetch` that catches exceptions and returns a typed result object. This guarantees `gather` never sees an exception, so all tasks complete. You get clean separation of successes and failures without losing any data.'''
    ),

    # -------------------------------------------------------------------------
    # 19. Regex catastrophic backtracking
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-regex-catastrophic-backtracking",
        r'''My email validator hangs for several seconds on certain invalid inputs. Valid emails are fast. What's wrong?

```python
import re
import time

def validate_email(email):
    """Validate email address format."""
    pattern = r'^([a-zA-Z0-9]+[._+&-]*)*[a-zA-Z0-9]+@([a-zA-Z0-9]+[-]*)*[a-zA-Z0-9]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

# Fast cases
start = time.time()
print(validate_email("user@example.com"))        # True - instant
print(validate_email("a.b.c@test.org"))          # True - instant
print(f"Fast case: {time.time() - start:.3f}s")

# Slow cases
start = time.time()
print(validate_email("aaaaaaaaaaaaaaaaaaaaaaaa@"))  # False - but takes FOREVER
print(f"Slow case: {time.time() - start:.3f}s")
```''',
        r'''<think>
Let me analyze the regex pattern: `^([a-zA-Z0-9]+[._+&-]*)*[a-zA-Z0-9]+@...`

The problem is in the local part (before @): `([a-zA-Z0-9]+[._+&-]*)*[a-zA-Z0-9]+`

Let me break this down:
- `([a-zA-Z0-9]+[._+&-]*)*` — a group that matches one or more alnum chars followed by zero or more special chars, repeated zero or more times
- `[a-zA-Z0-9]+` — then one or more alnum chars

For the input "aaaaaaaaaaaaaaaaaaaaaaaa@":
The regex engine tries to match the local part before @. The `a`s can be matched by `[a-zA-Z0-9]+` inside the group OR by the final `[a-zA-Z0-9]+` outside the group. The `[._+&-]*` matches zero characters since there are no special chars.

So `([a-zA-Z0-9]+)*[a-zA-Z0-9]+` on a string of 24 `a`s has exponentially many ways to partition the string. The regex engine tries:
- Group eats 23, final eats 1
- Group eats 22, final eats 2
- Group eats 1 then 22, final eats 1
- Group eats 1 then 21, final eats 2
- ... and so on

This is exponential backtracking — O(2^n) because each `a` can be assigned to either the group or the final `+`. When the match ultimately fails (because there's no valid domain after @), the engine exhaustively tries all combinations.

The root cause: nested quantifiers `(X+)*` where X can match the same characters as the following pattern, creating ambiguity.

Fix: rewrite the regex to eliminate ambiguity. A simple, non-backtracking email regex:
`^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`

This uses `[a-zA-Z0-9._%+-]+` which matches the entire local part in ONE pass with no nesting.

Or for production code, just use a library or a simple string check (split on @, check parts).
</think>

The bug is **catastrophic backtracking** (also called "regex denial of service" or ReDoS). The pattern `([a-zA-Z0-9]+[._+&-]*)*[a-zA-Z0-9]+` has **nested quantifiers** where the inner `[a-zA-Z0-9]+` and the outer `[a-zA-Z0-9]+` can both match the same characters.

For input "aaaaaaaaaaaaaaaaaaaaaaaa@", the engine must decide how to partition the `a`s between the group repetitions and the trailing `+`. With n characters, there are O(2^n) ways to partition — and when the match ultimately fails (no valid domain), the engine backtracks through ALL of them.

24 `a`s = ~16 million combinations. 30 `a`s = ~1 billion.

**Fixed code:**

```python
import re
import time

def validate_email(email):
    """Validate email address format — no catastrophic backtracking."""
    # FIX: flat character class, no nested quantifiers
    pattern = r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))

def validate_email_strict(email):
    """Stricter validation without regex — immune to backtracking."""
    if len(email) > 254:
        return False
    parts = email.split("@")
    if len(parts) != 2:
        return False
    local, domain = parts
    if not local or not domain:
        return False
    if ".." in local or ".." in domain:
        return False
    domain_parts = domain.split(".")
    if len(domain_parts) < 2 or any(not p for p in domain_parts):
        return False
    if len(domain_parts[-1]) < 2:
        return False
    return True


# ---------- Test ----------
# Valid emails
assert validate_email("user@example.com") is True
assert validate_email("a.b.c+tag@test.org") is True
assert validate_email("name_123@sub.domain.co.uk") is True

# Invalid emails
assert validate_email("@example.com") is False
assert validate_email("user@") is False
assert validate_email("user@.com") is False

# THE KEY TEST: this was hanging before, now it's instant
start = time.time()
result = validate_email("a" * 100 + "@")
elapsed = time.time() - start
assert result is False
assert elapsed < 0.01, f"Took {elapsed:.3f}s — still backtracking!"
print(f"Adversarial input: {elapsed*1000:.1f}ms (should be <10ms)")

# Stress test with long input
start = time.time()
validate_email("a" * 10000 + "@")
elapsed = time.time() - start
assert elapsed < 0.1, f"Took {elapsed:.3f}s"

print("PASS: no catastrophic backtracking")
```

Rules for safe regex:
1. **Never nest quantifiers** on overlapping character classes: `(a+)*`, `(a+)+`, `(a*)*` are all dangerous
2. Use **flat character classes** instead: `[a-z.]+` instead of `([a-z]+\.)*[a-z]+`
3. For production email validation, use a library or simple string parsing — RFC 5322 is too complex for a single regex'''
    ),

    # -------------------------------------------------------------------------
    # 20. Incorrect use of `is` vs `==` for value comparison
    # -------------------------------------------------------------------------
    (
        "deep_reasoning/debugging-is-vs-equality",
        r'''My comparison logic works for small numbers but fails for larger values. It also breaks for strings sometimes. What's wrong?

```python
def check_status_code(code):
    """Check if HTTP status code indicates success."""
    if code is 200:
        return "OK"
    elif code is 404:
        return "Not Found"
    elif code is 500:
        return "Server Error"
    else:
        return "Unknown"

def find_user(users, target_name):
    """Find user by name."""
    for user in users:
        if user["name"] is target_name:
            return user
    return None

# Test status codes
print(check_status_code(200))    # Works: "OK"
print(check_status_code(404))    # Works: "Not Found"

# But this breaks:
code = int("200")  # parsed from HTTP response
print(check_status_code(code))   # "Unknown"?!

x = 256
y = 256
print(x is y)  # True (coincidence!)

x = 257
y = 257
print(x is y)  # False (surprise!)

# String comparison
name = "alice"
print(find_user([{"name": "alice"}], name))       # Works (maybe)
name = "".join(["a", "l", "i", "c", "e"])
print(find_user([{"name": "alice"}], name))       # None?!
```''',
        r'''<think>
This is the `is` vs `==` confusion. Let me trace through carefully.

`is` checks **identity** (same object in memory). `==` checks **equality** (same value).

Python interns small integers (-5 to 256) and some short strings. So `256 is 256` is True because Python reuses the same object. But `257 is 257` is False because Python creates separate objects for integers outside the interning range.

For `check_status_code(200)`:
- When the literal `200` appears in both the function call and the `if` comparison, Python may (or may not) intern the integer, making `is` accidentally work for small values.
- `int("200")` creates a NEW integer object. Even though its value is 200, it's a different object than the literal 200 in the function. So `code is 200` is False.

For strings:
- `"alice"` literal is interned — all occurrences share the same object
- `"".join(["a","l","i","c","e"])` creates a NEW string object. Same value, different identity. So `user["name"] is target_name` is False.

The fix is straightforward: use `==` for value comparison. `is` should ONLY be used for:
- `is None` (None is a singleton)
- `is True` / `is False` (singletons)
- Explicit identity checks (rare)

Let me verify: replacing all `is` with `==` in comparisons fixes every case. `int("200") == 200` is True. `"".join([...]) == "alice"` is True.
</think>

The bug is using `is` (identity comparison) instead of `==` (value comparison). `is` checks whether two references point to the **same object in memory**, not whether they have the same value.

It appears to work for small integers because CPython **interns** integers from -5 to 256 — reusing the same object for each value. But this is an implementation detail, not a language guarantee:
- `256 is 256` → True (interned, same object)
- `257 is 257` → False (separate objects)
- `int("200") is 200` → False (different object, even though value matches)

Similarly, string literals are interned, but dynamically constructed strings are not.

**Fixed code:**

```python
def check_status_code(code):
    """Check if HTTP status code indicates success."""
    if code == 200:       # FIX: == instead of is
        return "OK"
    elif code == 404:     # FIX
        return "Not Found"
    elif code == 500:     # FIX
        return "Server Error"
    else:
        return "Unknown"

def find_user(users, target_name):
    """Find user by name."""
    for user in users:
        if user["name"] == target_name:  # FIX: == instead of is
            return user
    return None


# ---------- Test ----------
# Status codes — all methods of creating 200 should match
assert check_status_code(200) == "OK"
assert check_status_code(int("200")) == "OK"
assert check_status_code(100 + 100) == "OK"
assert check_status_code(404) == "Not Found"
assert check_status_code(500) == "Server Error"

# Strings — dynamically constructed strings should match
users = [{"name": "alice"}, {"name": "bob"}]
dynamic_name = "".join(["a", "l", "i", "c", "e"])
result = find_user(users, dynamic_name)
assert result is not None and result["name"] == "alice"

# Demonstrate the is vs == difference
a = 257
b = 257
assert a == b       # Same VALUE: True
# a is b may be False (implementation detail)

c = "hello world"
d = "".join(["hello", " ", "world"])
assert c == d       # Same VALUE: True
assert c is not d   # Different OBJECTS

# The ONLY correct uses of 'is':
assert None is None
assert True is True
assert False is not None

print("PASS: all comparisons use == for values")
```

The rule: **use `==` for comparing values, `is` only for singletons (`None`, `True`, `False`) or explicit identity checks.** Never rely on integer or string interning — it's a CPython optimization that varies by version and context.'''
    ),
]
