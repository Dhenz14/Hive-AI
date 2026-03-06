PAIRS = [
    ("thinking/debugging", r'''I have a Python function that appends to a list, but the list keeps growing across calls even though I give it a default empty list:

```python
def add_item(item, items=[]):
    items.append(item)
    return items

# Expected: each call starts fresh
result1 = add_item("apple")
print(result1)  # ['apple'] -- correct

result2 = add_item("banana")
print(result2)  # Expected ['banana'], got ['apple', 'banana'] -- WRONG!

result3 = add_item("cherry")
print(result3)  # Expected ['cherry'], got ['apple', 'banana', 'cherry'] -- WRONG!

# Even worse, result1 changed too:
print(result1)  # ['apple', 'banana', 'cherry'] -- all the same list!
```

Why does the default list persist across function calls?''', r'''<think>
This is the classic Python mutable default argument gotcha. But let me think through WHY this happens rather than just stating the rule.

When Python executes `def add_item(item, items=[]):`, it evaluates the default value `[]` right then and there, at function DEFINITION time. The resulting list object is stored in `add_item.__defaults__`. My first thought was "surely Python creates a new list each time the function is called" -- but no, that is exactly the trap. The default is evaluated ONCE, not per call.

Wait, but why would Python design it this way? Could it not create a fresh default on each call? Actually, there is a reason: default values can be expensive to compute (e.g., a complex object or a database query), so evaluating them once at definition time is an intentional optimization. The language designers chose "evaluate once" for consistency and performance, even though it creates this gotcha for mutable types.

So each call to `add_item` without an explicit `items` argument gets the SAME list object. When we `append` to it, we modify the shared default. And since result1, result2, and result3 all reference that same object, they all reflect the accumulated changes. That also explains why `result1` changes when we call `add_item("banana")` -- they are literally the same list in memory.

Hmm, I initially thought this only affects lists, but actually it affects ALL mutable types: dicts, sets, and even custom objects. The fix is always the same: use `None` as the default and create the mutable object inside the function body. That way each call gets a fresh instance.

One interesting edge case: this behavior is sometimes INTENTIONAL, as a simple memoization technique (e.g., `def fib(n, cache={0:0, 1:1})`). But using `functools.lru_cache` is the proper way to do that.
</think>

This is Python's most famous gotcha: **mutable default arguments**. Default parameter values are evaluated **once** at function definition time, not at each call. The empty list `[]` is created when Python first parses the `def` statement, and that single list object is shared across all calls.

**What happens internally:**

```python
def add_item(item, items=[]):
    items.append(item)
    return items

# Python creates the function object with defaults stored:
print(add_item.__defaults__)  # ([],)  -- one list, created at def time

add_item("apple")
print(add_item.__defaults__)  # (['apple'],)  -- same list, now mutated!

add_item("banana")
print(add_item.__defaults__)  # (['apple', 'banana'],)  -- keeps growing!
```

All three results point to the exact same list object:

```python
result1 = add_item("apple")
result2 = add_item("banana")
print(result1 is result2)  # True -- same object!
print(id(result1) == id(result2))  # True
```

**The fix -- use None as the default and create the list inside the function:**

```python
def add_item(item, items=None):
    if items is None:
        items = []  # New list created on each call
    items.append(item)
    return items

result1 = add_item("apple")
print(result1)  # ['apple']

result2 = add_item("banana")
print(result2)  # ['banana'] -- correct!

result3 = add_item("cherry")
print(result3)  # ['cherry'] -- correct!
```

**This affects ALL mutable default types:**

```python
# BAD -- mutable defaults
def add_to_dict(key, value, d={}):       # Shared dict!
    d[key] = value
    return d

def add_to_set(item, s=set()):           # Shared set!
    s.add(item)
    return s

def append_row(row, matrix=[[]]):         # Shared nested list!
    matrix[0].append(row)
    return matrix

# GOOD -- None defaults
def add_to_dict(key, value, d=None):
    if d is None:
        d = {}
    d[key] = value
    return d

def add_to_set(item, s=None):
    if s is None:
        s = set()
    s.add(item)
    return s
```

**Real-world example where this causes subtle bugs:**

```python
class EventProcessor:
    def __init__(self, handlers=[]):  # BUG: shared across all instances!
        self.handlers = handlers

    def add_handler(self, handler):
        self.handlers.append(handler)

# All instances share the same handlers list:
proc1 = EventProcessor()
proc1.add_handler(lambda e: print(e))

proc2 = EventProcessor()
print(len(proc2.handlers))  # 1 -- has proc1's handler!

# Fix:
class EventProcessor:
    def __init__(self, handlers=None):
        self.handlers = handlers if handlers is not None else []
```

**When mutable defaults ARE intentional (caching):**

```python
# Memoization using mutable default (intentional, but use functools instead)
def fibonacci(n, cache={0: 0, 1: 1}):
    if n not in cache:
        cache[n] = fibonacci(n - 1) + fibonacci(n - 2)
    return cache[n]

# Better: use functools.lru_cache
from functools import lru_cache

@lru_cache(maxsize=None)
def fibonacci(n):
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)
```

**Prevention tips:**
- ALWAYS use `None` as the default for mutable parameters (lists, dicts, sets, custom objects)
- Enable pylint or flake8 with the `W0102` / `B006` rule to catch mutable defaults
- Use `dataclasses.field(default_factory=list)` for dataclass mutable fields
- Check `func.__defaults__` if you suspect a mutable default bug
- When reviewing code, flag any `def func(x=[])` or `def func(x={})` patterns'''),

    ("thinking/debugging", r'''My list comprehension closure is capturing the wrong variable values. All my lambda functions return the same result:

```python
# Create a list of multiplier functions
multipliers = [lambda x: x * i for i in range(5)]

# Expected: each function multiplies by a different number (0, 1, 2, 3, 4)
print(multipliers[0](10))  # Expected: 0, Got: 40
print(multipliers[1](10))  # Expected: 10, Got: 40
print(multipliers[2](10))  # Expected: 20, Got: 40
print(multipliers[3](10))  # Expected: 30, Got: 40
print(multipliers[4](10))  # Expected: 40, Got: 40

# All functions return 40 (10 * 4)!
```

Why do all the lambda functions use i=4 instead of their respective values?''', r'''<think>
All lambdas return 40 (which is 10 * 4). So all of them are using i=4. But I created them inside a loop where i goes from 0 to 4. Why are they not capturing different values?

My first instinct was that each lambda gets its own copy of i at creation time. But actually, Python closures capture VARIABLES, not VALUES. The lambda `lambda x: x * i` does not snapshot i=0 when created during i=0's iteration. Instead, it keeps a reference to the variable i in the enclosing scope. When the lambda is eventually called, it looks up the CURRENT value of i.

Wait, is this late binding or something else? Let me think... In Python, closures use late binding -- variable lookup happens at call time, not at definition time. All five lambdas close over the same variable `i` in the list comprehension's scope. By the time any of them is called, the comprehension has finished and `i` is 4 (the last value from range(5)). So every lambda computes x * 4.

Hmm, this seems like a design flaw. Could Python have chosen early binding instead? Actually, late binding is intentional -- it allows closures to see updated values of variables, which is useful for things like callbacks that need to reference mutable state. The tradeoff is that loop closures behave unexpectedly.

The fix uses a beautiful irony: default arguments ARE evaluated at definition time (this is the same behavior that causes the mutable default gotcha from the previous example). So `lambda x, i=i: x * i` captures the CURRENT VALUE of i as a default parameter, freezing it at creation time. The gotcha that bites us with mutable defaults actually saves us here.

An alternative is a factory function `def make_multiplier(i): return lambda x: x * i` -- each call to make_multiplier creates a new scope with its own `i`, so the closure captures a different variable each time.
</think>

This is Python's **late binding closure** gotcha. Lambda functions (and all closures) capture **variables**, not **values**. When the lambda is called, it looks up the current value of `i`, which is 4 after the loop completes.

**What happens step by step:**

```python
multipliers = [lambda x: x * i for i in range(5)]
# After the comprehension, i = 4

# When we call any of the lambdas:
multipliers[0](10)
# Python evaluates: x * i
# x = 10, i = ??? -> looks up i in enclosing scope -> i = 4
# Result: 10 * 4 = 40

# ALL lambdas look up the SAME variable i, which is 4
```

**Fix 1: Use a default argument to capture the value at definition time:**

```python
# Default arguments are evaluated at DEFINITION time (not call time)
multipliers = [lambda x, i=i: x * i for i in range(5)]

print(multipliers[0](10))  # 0
print(multipliers[1](10))  # 10
print(multipliers[2](10))  # 20
print(multipliers[3](10))  # 30
print(multipliers[4](10))  # 40
```

The `i=i` in `lambda x, i=i:` captures the CURRENT value of `i` as a default parameter value. Each lambda gets its own copy of `i` frozen at creation time.

**Fix 2: Use functools.partial:**

```python
from functools import partial

def multiply(i, x):
    return x * i

multipliers = [partial(multiply, i) for i in range(5)]

print(multipliers[0](10))  # 0
print(multipliers[1](10))  # 10
print(multipliers[2](10))  # 20
```

**Fix 3: Use a factory function to create a new scope:**

```python
def make_multiplier(i):
    # Each call creates a new scope with its own 'i'
    return lambda x: x * i

multipliers = [make_multiplier(i) for i in range(5)]

print(multipliers[0](10))  # 0
print(multipliers[1](10))  # 10
print(multipliers[2](10))  # 20
```

**This gotcha appears in many disguises:**

```python
# GUI callbacks -- all buttons do the same thing
buttons = []
for i in range(5):
    btn = Button(text=f"Button {i}",
                 command=lambda: print(f"Clicked {i}"))  # BUG!
    buttons.append(btn)
# All buttons print "Clicked 4"

# Fix:
for i in range(5):
    btn = Button(text=f"Button {i}",
                 command=lambda i=i: print(f"Clicked {i}"))  # i=i captures value


# Thread targets -- all threads process the same item
for item in items:
    threading.Thread(target=lambda: process(item)).start()  # BUG!
# All threads process the last item

# Fix:
for item in items:
    threading.Thread(target=lambda item=item: process(item)).start()


# Async tasks -- same problem
for url in urls:
    asyncio.create_task(fetch(url))  # This is fine -- url is passed as argument
    # But this is NOT:
    asyncio.create_task(lambda: aiohttp.get(url))  # BUG -- late binding
```

**Understanding the difference -- early vs late binding:**

```python
# Late binding (closure -- looks up variable at CALL time)
funcs = []
for i in range(3):
    funcs.append(lambda: i)  # Captures variable 'i'
print([f() for f in funcs])  # [2, 2, 2]

# Early binding (default arg -- evaluates at DEFINITION time)
funcs = []
for i in range(3):
    funcs.append(lambda i=i: i)  # Captures value of 'i'
print([f() for f in funcs])  # [0, 1, 2]
```

**Prevention tips:**
- Whenever creating closures/lambdas inside a loop, use `i=i` default argument pattern
- Use `functools.partial` for clearer intent when binding arguments
- Use a factory function for complex closures (easier to reason about scope)
- Linters like pylint have `cell-var-from-loop` (W0640) to catch this pattern
- This applies to ALL closures, not just lambdas -- `def` inside a loop has the same issue'''),

    ("thinking/debugging", r'''I am confused by Python's integer caching behavior. Sometimes `is` works for comparing numbers and sometimes it does not:

```python
# These work as expected:
a = 256
b = 256
print(a is b)  # True

# But these do not:
c = 257
d = 257
print(c is d)  # False!

# Even stranger:
e = 257; f = 257
print(e is f)  # True!

# And in a function:
def test():
    x = 1000
    y = 1000
    return x is y

print(test())  # True!

# But at the REPL:
>>> x = 1000
>>> y = 1000
>>> x is y
False
```

Why does `is` behave differently for the same integer values depending on context?''', r'''<think>
This is confusing at first glance. Let me work through each case:

Case 1: `a = 256; b = 256; a is b` returns True. Could this be because Python caches small integers? Yes -- CPython pre-creates integer objects for -5 through 256 at startup. Every reference to 256 points to the same cached object. But wait, why 256 specifically? I think it is because small integers are used so frequently (loop counters, array indices, etc.) that caching them saves significant memory and allocation time.

Case 2: `c = 257; d = 257; c is d` returns False. So 257 is outside the cache range, and Python creates two separate objects. That makes sense given the cache boundary.

Case 3: `e = 257; f = 257; e is f` returns True. Wait, but 257 is outside the cache! How is this True? Hmm... the difference is that these are on the SAME LINE. The CPython compiler sees both constants 257 in the same statement and deduplicates them into a single constant object. That is a compilation optimization, not a runtime cache.

Case 4: Inside a function, `x = 1000; y = 1000; x is y` returns True. Same principle -- the compiler compiles the entire function body into a single code object and deduplicates all constants within it. So `1000` appears once in `test.__code__.co_consts` and both x and y reference it.

Case 5: At the REPL, `x = 1000` then `y = 1000` gives `x is y` as False. Because each REPL line is a separate compilation unit, so 1000 is compiled independently each time, creating separate objects.

So there are actually TWO separate mechanisms: the startup integer cache ([-5, 256]) and the compiler constant folding (within a compilation unit). I initially conflated them, but they are distinct. The key takeaway is that `is` behavior depends on implementation details that vary by context, Python version, and even alternative implementations like PyPy. Therefore, NEVER use `is` for value comparison -- always use `==`.
</think>

This is Python's **integer interning** combined with CPython's **constant folding** optimization. The behavior depends on two separate mechanisms.

**Mechanism 1: Small integer cache ([-5, 256])**

CPython pre-creates and caches integer objects for -5 through 256 at startup. Every reference to these values points to the same object:

```python
# These are the SAME object (cached at startup)
a = 256
b = 256
print(a is b)       # True -- same cached object
print(id(a) == id(b))  # True

# These are DIFFERENT objects (not in cache range)
c = 257
d = 257
print(c is d)       # False -- different objects
print(c == d)       # True  -- same VALUE though!
```

**Mechanism 2: Compiler constant folding**

The CPython compiler deduplicates constants within the same **compilation unit** (function, module, or statement):

```python
# Same line = same compilation unit -> deduplicated
e = 257; f = 257
print(e is f)  # True -- compiler reuses the constant

# Same function = same compilation unit -> deduplicated
def test():
    x = 1000
    y = 1000
    return x is y  # True -- compiler sees both constants

# REPL: each line is a separate compilation unit
>>> x = 1000   # compilation unit 1
>>> y = 1000   # compilation unit 2
>>> x is y     # False -- different objects from different compilations
```

**Inspecting the compiled constants:**

```python
def test():
    x = 1000
    y = 1000
    return x is y

# The function has only ONE 1000 constant:
print(test.__code__.co_consts)  # (None, 1000)
# Both x and y reference the same constant from the code object
```

**The CRITICAL lesson -- NEVER use `is` for value comparison:**

```python
# WRONG -- unreliable, depends on implementation details
if x is 256:     # Happens to work (cached)
    pass
if x is 257:     # Fails (not cached)
    pass
if x is 1000:    # Unpredictable (depends on compilation context)
    pass

# CORRECT -- always use == for value comparison
if x == 256:     # Always works correctly
    pass
if x == 257:     # Always works correctly
    pass
if x == 1000:    # Always works correctly
    pass
```

**When IS `is` appropriate?**

```python
# Use 'is' ONLY for singleton comparisons:
if value is None:      # Correct -- None is a singleton
    pass
if value is True:      # Acceptable -- True is a singleton
    pass
if value is False:     # Acceptable -- False is a singleton
    pass
if value is NotImplemented:  # Correct -- singleton
    pass

# NEVER use 'is' for:
if value is 0:         # BAD -- use ==
if value is "":        # BAD -- use ==
if value is 42:        # BAD -- use ==
if value is "hello":   # BAD -- use == (string interning is also unreliable)
```

**String interning has similar gotchas:**

```python
# Strings that look like identifiers are interned:
a = "hello"
b = "hello"
print(a is b)  # True (interned)

# Strings with spaces or special chars are NOT interned:
a = "hello world"
b = "hello world"
print(a is b)  # False (not interned) -- or True in some contexts!

# Again: use == for strings, always
print(a == b)  # True -- reliable
```

**Prevention tips:**
- ALWAYS use `==` for value comparison, `is` only for identity/singleton checks
- Enable the pylint `comparison-with-callable` and SyntaxWarning for `is` with literals (Python 3.8+)
- Python 3.8+ emits `SyntaxWarning: "is" with a literal` to catch this mistake
- Never rely on integer caching or string interning -- these are CPython implementation details
- The cache range [-5, 256] is not guaranteed by the Python spec and could change
- PyPy, Jython, and other implementations may have different caching behavior'''),

    ("thinking/debugging", r'''Python's string interning is causing confusing behavior in our application. We are using `is` for string comparison in a hot path for performance, and it mostly works but fails for some strings:

```python
# Our "optimized" string comparison
def check_status(status):
    if status is "active":    # Using 'is' for "performance"
        return True
    return False

# Works for literal strings:
check_status("active")  # True

# Fails for dynamically created strings:
s = "act" + "ive"
check_status(s)  # True (compiler optimized the concatenation)

user_input = input("Enter status: ")  # User types "active"
check_status(user_input)  # False! Different object

data = json.loads('{"status": "active"}')
check_status(data["status"])  # False! Different object

db_result = cursor.fetchone()[0]  # Returns "active" from database
check_status(db_result)  # False! Different object
```

We thought using `is` would be faster than `==` for string comparison. Is that even true?''', r'''<think>
The developer thinks using `is` instead of `==` for string comparison is a performance optimization. But is it actually faster? And more importantly, is it correct?

My first thought: `is` compares memory addresses (a single pointer comparison), while `==` does a value comparison. So `is` should be O(1) always, while `==` is O(n) in the worst case for strings of length n. That sounds like a clear win... but wait, does CPython's `==` actually do character-by-character comparison every time?

Actually, no. CPython's string `__eq__` first checks identity (`is`), then checks length, then checks hash equality, and ONLY THEN falls back to byte-by-byte comparison. For short strings (like "active"), the identity check and length check are so fast that `==` is nearly as fast as `is`. The difference is maybe 30 nanoseconds per comparison. At a million comparisons per second, that saves 30 milliseconds. Not worth introducing correctness bugs for.

Now, why does `is` sometimes work and sometimes fail? String interning. CPython interns certain strings:
- String literals in source code are interned at compile time
- Strings that look like identifiers (alphanumeric + underscore) may be interned
- Compile-time constant folding (e.g., "act" + "ive" at compile time) produces interned strings

But strings from external sources -- user input, JSON parsing, database results, network data -- are NOT interned. They are fresh string objects every time. So `is` gives True for string literals (by accident) but False for dynamically created strings (correctly reflecting they are different objects).

Hmm, I initially considered recommending `sys.intern()` to make `is` work reliably. But that is a hack -- you would need to intern EVERY incoming string before comparison, which costs more than just using `==`. The correct answer is simply: use `==` for value comparison, always. It is already fast enough, and it is always correct.
</think>

Using `is` for string comparison is a bug, not an optimization. It introduces intermittent failures that are extremely difficult to debug because they depend on whether Python happens to intern the string.

**Why it "mostly works" but fails unpredictably:**

```python
# INTERNED (is works by accident):
"active"                    # Source code literals are interned
"act" + "ive"               # Compile-time concatenation -> interned
sys.intern("active")        # Explicitly interned

# NOT INTERNED (is fails):
input("...")                # User input creates new string objects
json.loads(...)["status"]   # JSON parser creates new strings
cursor.fetchone()[0]        # Database driver creates new strings
f"{'active'}"              # f-string results may not be interned
"active".encode().decode()  # Round-trip creates new object
```

**The fix -- use `==` always:**

```python
def check_status(status):
    if status == "active":    # Always correct, always fast
        return True
    return False

# Or more Pythonically:
def check_status(status):
    return status == "active"
```

**Is `is` actually faster than `==`? Let us measure:**

```python
import timeit

s1 = "active"
s2 = "active"
s3 = sys.intern("act" + "ive")
s4 = "act" + "ive"  # May or may not be interned at runtime

# Identity comparison
timeit.timeit('s1 is s2', globals=globals(), number=10_000_000)
# ~0.25 seconds

# Equality comparison
timeit.timeit('s1 == s2', globals=globals(), number=10_000_000)
# ~0.28 seconds

# The difference is ~30 nanoseconds per comparison
# For short strings, == is almost as fast as 'is' because:
# 1. Python first checks identity (is) as optimization inside ==
# 2. Then checks hash equality (O(1))
# 3. Then checks length equality (O(1))
# 4. Only then does character-by-character comparison (rarely reached)
```

**How Python's `==` for strings is already optimized:**

```python
# CPython's string __eq__ implementation (simplified):
def string_eq(a, b):
    if a is b:           # Identity check first (free!)
        return True
    if len(a) != len(b): # Length check (O(1))
        return False
    if hash(a) != hash(b):  # Hash check (O(1), cached)
        return False
    return memcmp(a, b)  # Only if everything else matches
```

**When interning IS appropriate (rare):**

```python
import sys

# If you are doing millions of comparisons against a fixed set of strings
# AND the strings come from an external source, you can intern them:
VALID_STATUSES = {sys.intern(s) for s in ("active", "inactive", "pending")}

def check_status_hot_path(status):
    # Intern the incoming string so 'is' works
    status = sys.intern(status)
    return status in VALID_STATUSES

# But honestly, a regular set lookup with == is already O(1):
VALID_STATUSES = {"active", "inactive", "pending"}
def check_status_simple(status):
    return status in VALID_STATUSES
# This is just as fast and always correct
```

**Prevention tips:**
- NEVER use `is` for string or number comparison -- it is not an optimization, it is a bug
- Python 3.8+ warns: `SyntaxWarning: "is" with a literal. Did you mean "=="?`
- Use `==` for value comparison; it already includes an identity check internally
- If you genuinely need to optimize string lookups, use sets or dicts (hash-based O(1))
- `sys.intern()` is useful for memory optimization (deduplication), not speed
- Profile before optimizing -- string comparison is almost never a bottleneck'''),

    ("thinking/debugging", r'''I am confused by Python's descriptor protocol. My property-like class works on instances but not on the class itself:

```python
class Validator:
    def __init__(self, min_val, max_val):
        self.min_val = min_val
        self.max_val = max_val
        self.name = None

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self  # Accessed from class, return descriptor itself
        return getattr(obj, f'_{self.name}', None)

    def __set__(self, obj, value):
        if not isinstance(value, (int, float)):
            raise TypeError(f"{self.name} must be a number")
        if not (self.min_val <= value <= self.max_val):
            raise ValueError(f"{self.name} must be between {self.min_val} and {self.max_val}")
        setattr(obj, f'_{self.name}', value)


class Product:
    price = Validator(0, 10000)
    quantity = Validator(0, 1000)

    def __init__(self, name, price, quantity):
        self.name = name
        self.price = price
        self.quantity = quantity


# Works fine:
p = Product("Widget", 9.99, 100)
print(p.price)    # 9.99
print(p.quantity)  # 100

# Validation works:
try:
    p.price = -5  # Raises ValueError
except ValueError as e:
    print(e)  # price must be between 0 and 10000

# But this is confusing:
p.price = 50
print(Product.price)  # <__main__.Validator object at 0x...>  -- not a price!

# And this breaks:
print(vars(p))  # {'name': 'Widget', '_price': 50, '_quantity': 100}
# The actual attribute is _price, not price!

# Serialization breaks:
import json
print(json.dumps(p.__dict__))  # {"name": "Widget", "_price": 50, "_quantity": 100}
# Keys have underscores that should not be in the JSON!
```

How do descriptors actually work, and how do I fix the serialization issue?''', r'''<think>
The user has a working descriptor but is confused about two things. Let me think through each one.

**Issue 1: `Product.price` returns the descriptor object**
When you access `Product.price` (class-level access, not instance), Python calls `Validator.__get__(self, obj=None, objtype=Product)`. The code checks `if obj is None: return self`. So it returns the Validator instance itself. Is this wrong? Actually no -- this is the standard pattern. When you do `Product.price`, there is no instance to look up a value for, so returning the descriptor object is the convention. That is how `property` works too: `MyClass.my_property` returns the property object, not a value.

**Issue 2: Serialization shows `_price` instead of `price`**
Hmm, this is trickier. The descriptor stores values using `setattr(obj, f'_{self.name}', value)`, so the actual instance attribute is `_price`, not `price`. When you serialize via `p.__dict__`, you see the internal storage names. I initially thought this was just a naming convention issue, but it is actually a fundamental design tension: the descriptor name (`price`) and the storage name (`_price`) are different, and `__dict__` only shows storage.

Wait, could we store as `price` instead of `_price`? No -- if we do `setattr(obj, 'price', value)`, that would trigger the descriptor's `__set__` again because `price` IS the descriptor. That would cause infinite recursion. The underscore prefix is necessary to avoid colliding with the descriptor name. That is a clever workaround but creates the serialization problem.

What alternatives are there? I considered three approaches:
1. A custom `to_dict()` method that maps `_price` back to `price` -- works but requires boilerplate
2. Using a `WeakKeyDictionary` inside the descriptor to store values -- keeps `__dict__` clean entirely since values are stored in the descriptor, not on the instance
3. Using `__slots__` -- similar to approach 1 but with memory benefits

Actually, the WeakKeyDictionary approach is elegant. Values are stored in `descriptor._values[instance]` instead of `instance._price`. The instance's `__dict__` stays clean (only has non-descriptor attributes like `name`). But there is a tradeoff: the values are harder to inspect during debugging since they are hidden inside the descriptor object rather than being visible on the instance.
</think>

Python descriptors are a powerful protocol that powers `property`, `classmethod`, `staticmethod`, and ORMs. Let me explain the lookup chain and fix your serialization issue.

**How descriptor lookup works:**

```python
# When you access p.price (instance access):
# 1. Python checks type(p).__mro__ for a DATA descriptor named 'price'
#    (data descriptor = has __get__ AND __set__ or __delete__)
# 2. Found Validator with __get__ and __set__ -> it is a data descriptor
# 3. Calls Validator.__get__(descriptor_instance, p, Product)
# 4. Returns getattr(p, '_price', None) -> 50

# When you access Product.price (class access):
# 1. Python finds Validator in Product.__dict__['price']
# 2. Calls Validator.__get__(descriptor_instance, None, Product)
# 3. obj is None -> returns self (the Validator instance)
```

**The lookup priority chain:**
```
1. Data descriptors (has __set__ or __delete__) in the class
2. Instance __dict__
3. Non-data descriptors (only __get__) and class __dict__
```

**Fix the serialization issue -- Option 1: Custom to_dict method:**

```python
class Product:
    price = Validator(0, 10000)
    quantity = Validator(0, 1000)

    def __init__(self, name, price, quantity):
        self.name = name
        self.price = price
        self.quantity = quantity

    def to_dict(self):
        """Serialize using descriptor names, not internal storage names."""
        result = {}
        for key in vars(self):
            if key.startswith('_'):
                # Check if there is a descriptor for this attribute
                clean_key = key.lstrip('_')
                if hasattr(type(self), clean_key):
                    descriptor = getattr(type(self), clean_key)
                    if hasattr(descriptor, '__get__'):
                        result[clean_key] = getattr(self, clean_key)
                        continue
            result[key] = getattr(self, key)
        return result

p = Product("Widget", 9.99, 100)
print(p.to_dict())  # {'name': 'Widget', 'price': 9.99, 'quantity': 100}
```

**Fix -- Option 2: Store values in the descriptor itself using WeakKeyDictionary:**

```python
import weakref

class Validator:
    def __init__(self, min_val, max_val):
        self.min_val = min_val
        self.max_val = max_val
        self.name = None
        self._values = weakref.WeakKeyDictionary()

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        return self._values.get(obj)

    def __set__(self, obj, value):
        if not isinstance(value, (int, float)):
            raise TypeError(f"{self.name} must be a number")
        if not (self.min_val <= value <= self.max_val):
            raise ValueError(
                f"{self.name} must be between {self.min_val} and {self.max_val}"
            )
        self._values[obj] = value

# Now the instance __dict__ is clean:
p = Product("Widget", 9.99, 100)
print(vars(p))  # {'name': 'Widget'}  -- no _price or _quantity!
print(p.price)  # 9.99 (stored in descriptor's WeakKeyDictionary)
```

**Fix -- Option 3: Use __slots__ with the original approach:**

```python
class Product:
    price = Validator(0, 10000)
    quantity = Validator(0, 1000)
    __slots__ = ('name', '_price', '_quantity')

    def __init__(self, name, price, quantity):
        self.name = name
        self.price = price      # Goes through Validator.__set__
        self.quantity = quantity

    def __json__(self):
        return {
            'name': self.name,
            'price': self.price,       # Goes through Validator.__get__
            'quantity': self.quantity,
        }
```

**Auto-discovering descriptors for serialization:**

```python
def descriptor_dict(obj):
    """Get a dict using descriptor names instead of internal storage."""
    result = {}
    cls = type(obj)
    for name in dir(cls):
        attr = getattr(cls, name)
        if isinstance(attr, Validator):
            result[name] = getattr(obj, name)  # Triggers __get__
    # Add non-descriptor instance attributes
    for key, val in vars(obj).items():
        if not key.startswith('_'):
            result[key] = val
    return result

p = Product("Widget", 9.99, 100)
print(descriptor_dict(p))  # {'price': 9.99, 'quantity': 100, 'name': 'Widget'}
print(json.dumps(descriptor_dict(p)))  # Correct JSON!
```

**Prevention tips:**
- Choose a consistent storage strategy for descriptors (instance dict with prefix OR WeakKeyDictionary)
- Always implement `to_dict()` or `__json__()` when using descriptors, since `__dict__` will not reflect descriptor names
- Use `__set_name__` (Python 3.6+) to automatically name descriptors
- Remember that data descriptors (with `__set__`) take priority over instance `__dict__`
- Test serialization (JSON, pickle) early when using descriptors
- Consider using `dataclasses` with `__post_init__` validation as a simpler alternative to descriptors for basic validation'''),
]
