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
This is the classic Python mutable default argument gotcha. Default argument values are evaluated ONCE when the function is defined, not each time the function is called. So the empty list `[]` is created once and the same list object is reused for every call that does not provide an explicit `items` argument.

Each call to `add_item` without an explicit `items` argument uses the SAME list object. When we append to it, we are modifying the shared default list. And since result1, result2, and result3 all point to that same list object, they all reflect the accumulated changes.

This is one of the most common Python surprises for newcomers, and it bites experienced developers too when they use mutable defaults with dicts, sets, or other mutable types.
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
This is the late binding closure gotcha in Python. The lambda functions capture the VARIABLE `i`, not the VALUE of `i` at the time the lambda is created. When the lambda is eventually called, it looks up the current value of `i`, which is 4 (the last value from the range(5) loop).

This is because Python closures use late binding -- the variable is looked up at call time, not at definition time. All five lambdas close over the same variable `i`, and by the time any of them is called, the loop has finished and `i` is 4.

The classic fix is to use a default argument to capture the value at definition time, since default arguments ARE evaluated at definition time (the same behavior that causes the mutable default gotcha actually helps here).
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
This is about Python's integer interning/caching and the difference between `is` (identity) and `==` (equality).

Python caches small integers in the range [-5, 256] at startup. These are singleton objects -- every reference to `256` points to the same object. But `257` and above are not cached, so each time you write `257`, Python MAY create a new object.

However, the behavior also depends on compilation context:
1. The CPython compiler optimizes constants within the same compilation unit (module, function, or single-line statement)
2. When `e = 257; f = 257` are on the same line, the compiler sees both constants and deduplicates them
3. Inside a function, the compiler compiles all constants in the function's code object and deduplicates
4. At the REPL, each line is a separate compilation unit, so `x = 1000` and `y = 1000` on separate lines create separate objects

The key takeaway: `is` checks identity (same object in memory), `==` checks equality (same value). You should NEVER use `is` for value comparison except with singletons like None, True, False.
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
This is a dangerous optimization attempt based on a misunderstanding of string interning. The developer is using `is` for string comparison thinking it is faster, but it is unreliable because string interning only applies to certain strings in certain contexts.

Key points:
1. `is` compares object identity (memory address), not value
2. CPython interns strings that look like identifiers (alphanumeric + underscore)
3. String literals in source code are interned
4. Strings from external sources (user input, databases, JSON, network) are NOT interned
5. Even `==` for strings is very fast due to hash comparison and short-circuit on length

The "performance optimization" of using `is` instead of `==` is a premature optimization that introduces bugs and provides negligible (if any) speedup.
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
The user has a working descriptor but is confused about two things:
1. Why `Product.price` returns the descriptor object instead of a value
2. Why serialization shows `_price` instead of `price`

For #1: When you access a descriptor from the class (not an instance), `__get__` is called with `obj=None`. The standard pattern is to return `self` (the descriptor) in that case, which is what the user does. This is the correct behavior -- the descriptor is a class-level construct.

For #2: The descriptor stores values on the instance using `setattr(obj, f'_{self.name}', value)`, so the actual instance attribute is `_price`. When serializing `p.__dict__`, you see the underscore-prefixed names.

The fix for serialization is to either:
1. Override `__dict__` or provide a custom serialization method
2. Use a different storage mechanism (like a WeakKeyDictionary in the descriptor)
3. Add a custom `to_dict()` method
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
