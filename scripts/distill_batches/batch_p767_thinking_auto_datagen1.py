"""Phase 4A: Self-Improvement -- Training Data Generation (Part 1)

Teaching the model to generate high-quality training pairs for Python fundamentals.
Each pair asks the model to CREATE training data and explains why each generated pair
is effective, building the meta-skill of self-improvement through data generation.
"""

PAIRS = [
    (
        "thinking/auto-datagen-python-list-comprehensions",
        r'''Generate 3 high-quality training pairs that teach Python list comprehensions. For each pair, explain why it's effective training data.''',
        r'''<think>
To generate good training data for list comprehensions, I need to:
1. Cover different difficulty levels (beginner, intermediate, advanced)
2. Include realistic scenarios, not toy examples
3. Each pair should teach ONE clear concept
4. Answers should show the reasoning process, not just the solution

For the beginner pair, I'll cover the basic syntax transformation from a for-loop to a comprehension -- this is the foundational mental model. For intermediate, I'll show filtering with conditionals since that's where most people start making mistakes. For advanced, I'll tackle nested comprehensions with a realistic data transformation scenario, since that's where readability tradeoffs matter most.

Let me design 3 pairs with increasing complexity...
</think>

Here are 3 training pairs for teaching Python list comprehensions:

**Pair 1 (Beginner):**
```
Q: I have this loop that builds a list of squared numbers. How can I rewrite it using a list comprehension?

squares = []
for n in range(10):
    squares.append(n ** 2)

A: You can rewrite this as a single line using a list comprehension:

squares = [n ** 2 for n in range(10)]

The pattern is: [expression for variable in iterable]. Think of it as reading the for-loop "inside out" -- the expression (n ** 2) goes first, then the loop header (for n in range(10)). The result is identical: [0, 1, 4, 9, 16, 25, 36, 49, 64, 81].

A list comprehension is preferred here because the intent -- "build a list by transforming each element" -- is immediately clear. The append-in-a-loop version buries that intent across three lines.
```
**Why this is effective:** It starts from code the learner already understands (a for-loop) and shows the mechanical transformation. The "inside out" mental model gives them a repeatable strategy, not just an answer to memorize.

**Pair 2 (Intermediate):**
```
Q: I have a list of filenames and I want to extract just the .csv files, converted to lowercase. I tried this but it feels wrong:

csv_files = [f.lower() for f in filenames for f in filenames if f.endswith('.csv')]

What's the correct way?

A: The problem is you wrote `for f in filenames` twice. A comprehension with a filter uses this structure:

csv_files = [f.lower() for f in filenames if f.endswith('.csv')]

The order is: [transform for variable in iterable if condition]. The if-clause acts as a filter -- only elements passing the condition get transformed and included.

One subtlety: the condition `f.endswith('.csv')` is checked BEFORE the transform `f.lower()`. So if your filenames contain 'Data.CSV' (uppercase extension), this won't match. To handle case-insensitive matching:

csv_files = [f.lower() for f in filenames if f.lower().endswith('.csv')]

This calls .lower() twice per matching element, which is fine for filenames. If performance mattered on large data, you'd use a walrus operator (Python 3.8+):

csv_files = [low for f in filenames if (low := f.lower()).endswith('.csv')]
```
**Why this is effective:** It uses a realistic scenario (file filtering), starts from a common mistake (duplicated for-clause), and layers in a real-world subtlety (case sensitivity) that demonstrates deeper understanding. The walrus operator variant rewards curiosity without overwhelming beginners.

**Pair 3 (Advanced):**
```
Q: I have a list of dictionaries representing orders, and I need to build a flat list of (customer, product) tuples for all orders over $50. Is a list comprehension appropriate here, or should I use a loop?

orders = [
    {"customer": "Alice", "items": [{"product": "Widget", "price": 25}, {"product": "Gadget", "price": 75}]},
    {"customer": "Bob", "items": [{"product": "Doohickey", "price": 120}]},
]

A: A nested comprehension works but pushes readability limits:

result = [
    (order["customer"], item["product"])
    for order in orders
    for item in order["items"]
    if item["price"] > 50
]
# Result: [("Alice", "Gadget"), ("Bob", "Doohickey")]

The nested for-clauses read top-to-bottom like nested loops: the outer loop (for order in orders) comes first, then the inner loop (for item in order["items"]), then the filter.

This is acceptable because the structure is still scannable when formatted across multiple lines. But if you needed additional logic -- like grouping by customer or accumulating totals -- switch to an explicit loop or use itertools.groupby. The rule of thumb: if a comprehension requires more than about 3 clauses or you need intermediate variables, a loop is clearer.

For maximum clarity in a team codebase, you could also extract the filtering into a helper:

def expensive_items(order, threshold=50):
    return [(order["customer"], item["product"]) for item in order["items"] if item["price"] > threshold]

result = [pair for order in orders for pair in expensive_items(order)]
```
**Why this is effective:** It forces a judgment call (comprehension vs. loop) rather than just showing syntax. The refactoring into a helper function teaches code design, not just Python mechanics. Real engineers face this exact readability tradeoff daily.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
    (
        "thinking/auto-datagen-python-error-handling",
        r'''Generate 3 high-quality training pairs that teach Python error handling patterns. For each pair, explain why it's effective training data.''',
        r'''<think>
For error handling training data, I need to cover:
1. Beginner: basic try/except structure and why bare except is bad
2. Intermediate: designing custom exceptions and using exception chaining
3. Advanced: the nuanced patterns like retry logic, contextual error wrapping, and when NOT to catch exceptions

The biggest mistake beginners make is catching too broadly (except Exception or bare except). The intermediate gap is not knowing how to design exception hierarchies for libraries. The advanced skill is knowing when to let exceptions propagate vs. catch them.

Let me make sure each pair has a realistic scenario...
</think>

Here are 3 training pairs for teaching Python error handling patterns:

**Pair 1 (Beginner):**
```
Q: My script crashes when a user enters non-numeric input. I added error handling but my colleague said it's bad practice. What's wrong?

try:
    age = int(input("Enter age: "))
    process_age(age)
except:
    print("Something went wrong")

A: Two problems here:

1. **Bare `except:` catches EVERYTHING** -- including KeyboardInterrupt (Ctrl+C) and SystemExit. Your user literally cannot stop the program if process_age() enters an infinite loop. Always catch specific exceptions:

try:
    age = int(input("Enter age: "))
except ValueError:
    print("Please enter a valid number")

2. **The error message is useless.** "Something went wrong" gives the user no way to fix the problem. Tell them what went wrong and what to do about it.

If you also want to catch errors from process_age(), separate the concerns:

try:
    age = int(input("Enter age: "))
except ValueError:
    print("Please enter a valid number")
else:
    # Only runs if no exception was raised
    try:
        process_age(age)
    except AgeOutOfRangeError:
        print("Age must be between 0 and 150")

The else clause keeps the "happy path" distinct from error recovery. Never put code in the try block that you don't intend to catch exceptions from.
```
**Why this is effective:** It addresses the single most common anti-pattern (bare except) with a concrete harmful consequence (can't Ctrl+C). The else clause introduction is a natural extension that most tutorials skip but working developers need.

**Pair 2 (Intermediate):**
```
Q: I'm building a library that talks to a payment API. Right now my code raises generic exceptions like ValueError and RuntimeError. My users are complaining they can't distinguish between "invalid card number" and "API timeout." How should I design my exceptions?

A: Create an exception hierarchy rooted in a single base class for your library:

class PaymentError(Exception):
    """Base exception for all payment library errors."""
    pass

class ValidationError(PaymentError):
    """Input validation failed before reaching the API."""
    pass

class InvalidCardNumber(ValidationError):
    pass

class APIError(PaymentError):
    """The API returned an error or was unreachable."""
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code

class APITimeout(APIError):
    pass

class PaymentDeclined(APIError):
    pass

Now your users can catch at the granularity they need:

# Catch everything from your library
except PaymentError:

# Catch only API-related issues (for retry logic)
except APIError:

# Catch one specific case
except InvalidCardNumber:

Key design rules:
- One base exception per library (users can catch-all with one type)
- Group by failure category (validation vs. API vs. auth)
- Add context attributes (status_code) where callers need them
- Use exception chaining when wrapping lower-level errors:

try:
    response = requests.post(url, json=payload, timeout=5)
except requests.Timeout as e:
    raise APITimeout("Payment API timed out after 5s") from e
```
**Why this is effective:** It teaches exception design as an API design problem, which is the right mental model. The hierarchy example is directly usable, and the `from e` chaining detail is something most intermediate developers miss, leading to lost debugging context.

**Pair 3 (Advanced):**
```
Q: I see this pattern in our codebase. Every function wraps its entire body in try/except and logs the error. Is this a good pattern?

def get_user(user_id):
    try:
        user = db.query(User, user_id)
        return user
    except Exception as e:
        logger.error(f"Failed to get user: {e}")
        return None

A: This is the "exception swallowing" anti-pattern, and it's one of the most damaging patterns in production code. Problems:

1. **Every caller must check for None**, and they won't. You've turned a loud, debuggable crash into a silent, cascading failure. Somewhere downstream, code does `user.name` on None and you get an AttributeError with no connection to the actual database error.

2. **You lose the stack trace.** `logger.error(f"...")` only logs the message string, not the traceback. Use `logger.exception()` or `logger.error("...", exc_info=True)` if you must log.

3. **You catch too broadly.** A TypeError from a bug in your code gets silently swallowed the same as a database connectivity error.

The fix depends on the layer:

**In library/business logic -- let exceptions propagate:**
def get_user(user_id):
    return db.query(User, user_id)  # Let DatabaseError propagate

**At the boundary (API handler, CLI entry point) -- catch and translate:**
@app.get("/users/{user_id}")
def get_user_endpoint(user_id: int):
    try:
        user = get_user(user_id)
    except DatabaseError:
        logger.exception("Database error fetching user %s", user_id)
        raise HTTPException(status_code=503, detail="Service unavailable")

The rule: catch exceptions at the level where you can DO something meaningful about them. If all you can do is log and return None, you can't do anything meaningful -- let it propagate to a layer that can.
```
**Why this is effective:** It challenges a pattern that many teams adopt thinking it's "safe." The explanation connects the anti-pattern to real production consequences (silent cascading failures), which is more persuasive than abstract rules. The boundary pattern gives a concrete alternative.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
    (
        "thinking/auto-datagen-python-decorators",
        r'''Generate 3 high-quality training pairs that teach Python decorators. For each pair, explain why it's effective training data.''',
        r'''<think>
For decorators, the key progression is:
1. Beginner: Understanding that decorators are just functions that wrap functions -- demystify the @ syntax
2. Intermediate: Writing a decorator that takes arguments (the extra nesting layer confuses people)
3. Advanced: Class-based decorators and using functools.wraps, plus when decorators are the wrong tool

I want to avoid the overused "timer decorator" example for beginner level -- let me use something that shows the practical value more clearly, like input validation. For intermediate, parameterized decorators are the biggest stumbling block. For advanced, preserving function metadata and decorator stacking order.
</think>

Here are 3 training pairs for teaching Python decorators:

**Pair 1 (Beginner):**
```
Q: I keep seeing the @ symbol above function definitions in Python code. What does this do and how do I write my own?

@login_required
def dashboard(request):
    return render("dashboard.html")

A: The @ syntax is a decorator -- it's shorthand for wrapping a function inside another function. The code above is identical to:

def dashboard(request):
    return render("dashboard.html")
dashboard = login_required(dashboard)

A decorator is just a function that takes a function as input and returns a new function. Here's a simple one that prints when a function is called:

def log_calls(func):
    def wrapper(*args, **kwargs):
        print(f"Calling {func.__name__}")
        result = func(*args, **kwargs)
        print(f"{func.__name__} returned {result}")
        return result
    return wrapper

@log_calls
def add(a, b):
    return a + b

add(3, 4)
# Output:
# Calling add
# returned 7

The key insight: `wrapper` replaces `add`. When you call add(3, 4), you're actually calling wrapper(3, 4), which calls the original add inside it. The *args/**kwargs ensure the wrapper accepts whatever arguments the original function takes.

Always add @functools.wraps(func) above your wrapper to preserve the original function's name and docstring:

import functools

def log_calls(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        ...
    return wrapper
```
**Why this is effective:** It de-sugars the @ syntax immediately, showing it's not magic. The "wrapper replaces the original function" explanation gives the correct mental model. Including functools.wraps from the start prevents a common gotcha from becoming a habit.

**Pair 2 (Intermediate):**
```
Q: I want to write a decorator that retries a function N times if it raises an exception. I can write a basic decorator, but I don't know how to pass the number of retries as a parameter. How does @retry(max_attempts=3) work?

A: A parameterized decorator has three layers of nesting. Think of it this way:

- @log_calls -- decorator takes a function, returns a wrapper
- @retry(max_attempts=3) -- a function that RETURNS a decorator

import functools
import time

def retry(max_attempts=3, delay=1.0):
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts:
                        print(f"Attempt {attempt} failed, retrying in {delay}s...")
                        time.sleep(delay)
            raise last_exception
        return wrapper
    return decorator

@retry(max_attempts=5, delay=2.0)
def fetch_data(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.json()

The execution flow: retry(max_attempts=5, delay=2.0) is called first and returns `decorator`. Then `decorator(fetch_data)` is called and returns `wrapper`. So @retry(...) is a decorator factory -- it manufactures a decorator configured with your parameters.

If the nesting feels confusing, read it outside-in:
- retry() captures configuration (max_attempts, delay)
- decorator() captures the original function
- wrapper() runs on every call and has access to both
```
**Why this is effective:** The retry decorator is genuinely useful (not a toy example), and the three-layer nesting is the exact point where most people get confused. The "decorator factory" mental model and the outside-in reading strategy give learners a way to reason about it, not just copy the pattern.

**Pair 3 (Advanced):**
```
Q: I have multiple decorators on a function. I'm confused about the order they run in, and I'm seeing unexpected behavior:

@authenticate
@rate_limit(100)
@cache(ttl=300)
def get_user_profile(user_id):
    return db.fetch_user(user_id)

Which decorator runs first? Does the order matter?

A: Decorators are applied bottom-up but execute top-down. This is the single most confusing aspect of decorator stacking.

**Application order (at import/definition time):**
The code is equivalent to:
get_user_profile = authenticate(rate_limit(100)(cache(ttl=300)(get_user_profile)))

So cache wraps the original function first, then rate_limit wraps that, then authenticate wraps everything.

**Execution order (at call time):**
When you call get_user_profile(42), execution flows top-down:
1. authenticate checks credentials -- if invalid, returns 401 (never hits rate_limit)
2. rate_limit checks the counter -- if over limit, returns 429 (never hits cache)
3. cache checks for cached result -- if found, returns it (never hits db)
4. Original function runs only if all three decorators pass through

**This means order absolutely matters.** If you put @cache above @authenticate:

@cache(ttl=300)
@authenticate
def get_user_profile(user_id):
    ...

Now unauthenticated requests would get cached results -- a security vulnerability. The rule: put access control outermost (top), caching innermost (bottom), and validation/rate-limiting in between.

Think of it as layers of an onion: the outermost layer is the first checkpoint a request hits. Each decorator decides whether to pass through to the next layer or short-circuit.
```
**Why this is effective:** Decorator stacking order is a real source of bugs (especially security bugs). The "apply bottom-up, execute top-down" rule with the security vulnerability example makes the consequences visceral. The onion metaphor gives a lasting mental model.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
    (
        "thinking/auto-datagen-python-context-managers",
        r'''Generate 3 high-quality training pairs that teach Python context managers. For each pair, explain why it's effective training data.''',
        r'''<think>
For context managers, the progression should be:
1. Beginner: Why `with` exists (resource cleanup guarantee) -- move beyond just files
2. Intermediate: Writing your own context manager with __enter__/__exit__ vs contextlib.contextmanager
3. Advanced: Using context managers for non-obvious patterns like transaction rollback, temporary state changes, and exception handling in __exit__

The biggest misconception is that context managers are "just for files." I need to show the broader principle: guaranteed setup/teardown regardless of exceptions.
</think>

Here are 3 training pairs for teaching Python context managers:

**Pair 1 (Beginner):**
```
Q: I know I should use `with open(...)` for files, but I don't really understand why. What does `with` actually do, and does it work with things other than files?

A: The `with` statement guarantees cleanup happens, even if an exception occurs. Compare:

# Without `with` -- cleanup can be skipped
f = open("data.csv")
data = f.read()       # If this raises an exception...
f.close()             # ...this line never runs. File handle leaked.

# With `with` -- cleanup is guaranteed
with open("data.csv") as f:
    data = f.read()   # Even if this raises, f.close() still runs

The `with` block calls two special methods on the object:
- __enter__() at the start (opens the file, returns it)
- __exit__() at the end (closes the file, no matter what)

This works with many things beyond files:

# Database connections
with sqlite3.connect("app.db") as conn:
    conn.execute("INSERT INTO users ...")
    # Auto-commits on success, rolls back on exception

# Thread locks
with threading.Lock():
    shared_counter += 1
    # Lock is released even if the increment logic fails

# Temporary directories
with tempfile.TemporaryDirectory() as tmpdir:
    # Directory and all contents deleted when block exits

The pattern is always the same: acquire a resource, use it, guarantee it gets released. Any time you have setup/teardown that MUST happen as a pair, a context manager is the right tool.
```
**Why this is effective:** It starts from the familiar (files) and generalizes to the principle (guaranteed cleanup). Showing three non-file examples immediately breaks the "context managers = files" misconception. The explicit comparison of with vs. without makes the value proposition concrete.

**Pair 2 (Intermediate):**
```
Q: I want to write a context manager that temporarily changes the working directory and restores it when done. Should I write a class with __enter__/__exit__ or use the @contextmanager decorator?

A: Both work. Here's each approach so you can choose:

**Class-based (explicit, good for complex state):**

import os

class change_directory:
    def __init__(self, target_dir):
        self.target = target_dir
        self.original = None

    def __enter__(self):
        self.original = os.getcwd()
        os.chdir(self.target)
        return self.target

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.chdir(self.original)
        return False  # Don't suppress exceptions

**Generator-based (concise, good for simple cases):**

from contextlib import contextmanager
import os

@contextmanager
def change_directory(target_dir):
    original = os.getcwd()
    os.chdir(target_dir)
    try:
        yield target_dir
    finally:
        os.chdir(original)

Both are used identically:

with change_directory("/tmp/build"):
    print(os.getcwd())  # /tmp/build
print(os.getcwd())      # back to original

**When to use which:**
- @contextmanager: fewer than ~15 lines, no need to store complex state, one yield point
- Class-based: reusable across the codebase, needs methods beyond enter/exit, or you want to support async (__aenter__/__aexit__)

Critical detail: in the generator version, the try/finally around yield is essential. Without it, if the code inside the `with` block raises an exception, os.chdir(original) won't run -- defeating the entire purpose.
```
**Why this is effective:** It presents both approaches side-by-side with identical behavior, letting the learner compare directly. The "when to use which" guidance prevents analysis paralysis. The warning about try/finally around yield catches a real bug that even experienced developers make.

**Pair 3 (Advanced):**
```
Q: I'm writing a database library. I want a transaction context manager that auto-commits on success and rolls back on any exception. But I also want the option to nest transactions using savepoints. How do I handle this?

A: This requires your __exit__ to inspect the exception and your __enter__ to track nesting depth:

class Transaction:
    def __init__(self, connection):
        self.conn = connection
        self.savepoint_id = None

    def __enter__(self):
        if self.conn.in_transaction:
            # Nested: use a savepoint instead of a real transaction
            self.savepoint_id = f"sp_{id(self)}"
            self.conn.execute(f"SAVEPOINT {self.savepoint_id}")
        else:
            self.conn.execute("BEGIN")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Exception occurred -- roll back
            if self.savepoint_id:
                self.conn.execute(f"ROLLBACK TO {self.savepoint_id}")
            else:
                self.conn.execute("ROLLBACK")
            return False  # Re-raise the exception
        else:
            # Success -- commit or release savepoint
            if self.savepoint_id:
                self.conn.execute(f"RELEASE {self.savepoint_id}")
            else:
                self.conn.execute("COMMIT")
            return False

# Usage:
with Transaction(conn):           # BEGIN
    conn.execute("INSERT INTO orders ...")
    with Transaction(conn):       # SAVEPOINT
        conn.execute("INSERT INTO order_items ...")
        # If this raises, only the savepoint rolls back
    conn.execute("UPDATE inventory ...")
    # If this raises, entire transaction rolls back

Key design decisions:
- __exit__ returns False always, so exceptions propagate to the caller. Returning True would suppress them silently, which is almost never what you want.
- The savepoint ID uses id(self) for uniqueness, avoiding collisions with concurrent nested transactions.
- The nesting is transparent to the caller -- they use the same Transaction class regardless of depth.
```
**Why this is effective:** It teaches __exit__'s exception parameters (exc_type, exc_val, exc_tb) in a context where they actually matter for control flow. The nested transaction/savepoint pattern is a real-world design that forces understanding of both the protocol and database semantics. The return value of __exit__ (False vs. True) is explained with consequences.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
    (
        "thinking/auto-datagen-python-generators-iterators",
        r'''Generate 3 high-quality training pairs that teach Python generators and iterators. For each pair, explain why it's effective training data.''',
        r'''<think>
For generators/iterators, the key concepts are:
1. Beginner: What yield does and why generators are memory-efficient (lazy evaluation)
2. Intermediate: Generator expressions vs list comprehensions, and using generators in pipelines
3. Advanced: send(), throw(), close() -- bidirectional communication with generators, and implementing complex protocols like pagination

The critical insight is laziness/memory efficiency. Most beginners think generators are "just a weird way to return lists." I need to show WHY you'd use them -- processing data larger than memory.
</think>

Here are 3 training pairs for teaching Python generators and iterators:

**Pair 1 (Beginner):**
```
Q: I need to process a 10GB log file line by line. My script runs out of memory when I do:

lines = open("huge.log").readlines()
for line in lines:
    if "ERROR" in line:
        print(line)

How can I handle this without loading everything into memory?

A: The problem is readlines() loads ALL 10GB into memory at once. Use a generator instead -- it processes one line at a time:

def error_lines(filepath):
    with open(filepath) as f:
        for line in f:
            if "ERROR" in line:
                yield line

for line in error_lines("huge.log"):
    print(line)

The `yield` keyword makes this a generator function. Instead of building a list and returning it, the function pauses at each yield, hands out one value, and resumes only when the next value is requested.

Memory comparison:
- readlines(): loads 10GB into RAM
- Generator: holds ~1 line in RAM at any time (maybe 200 bytes)

You can think of yield as "return one item and pause." The function's local variables are frozen in place until the next iteration resumes it.

Even simpler -- files are already iterators in Python:

with open("huge.log") as f:
    for line in f:
        if "ERROR" in line:
            print(line)

This works because open() returns an iterator that yields one line at a time. The generator version is useful when you want to encapsulate the filtering logic for reuse.
```
**Why this is effective:** It starts from a real pain point (out-of-memory crash) rather than abstract syntax. The memory comparison makes the benefit quantifiable. Showing that files are already iterators prevents over-engineering.

**Pair 2 (Intermediate):**
```
Q: I have a data processing pipeline: read CSV rows, filter by date, convert currencies, and compute averages. Each step currently builds a full list. How do I chain these as generators for better memory efficiency?

A: Chain generators by having each one consume the previous one. Each stage processes one item at a time:

import csv
from datetime import datetime

def read_rows(filepath):
    with open(filepath) as f:
        reader = csv.DictReader(f)
        for row in reader:
            yield row

def filter_recent(rows, days=30):
    cutoff = datetime.now().timestamp() - (days * 86400)
    for row in rows:
        if float(row["timestamp"]) > cutoff:
            yield row

def convert_currency(rows, rate):
    for row in rows:
        row["amount_usd"] = float(row["amount_eur"]) * rate
        yield row

# Chain the pipeline
rows = read_rows("transactions.csv")
recent = filter_recent(rows, days=30)
converted = convert_currency(recent, rate=1.08)

# Nothing has executed yet! Generators are lazy.
# Processing starts only when you consume the final generator:
total = sum(row["amount_usd"] for row in converted)

The entire pipeline processes ONE row at a time through all stages. For a 5-million-row CSV, you still use memory proportional to one row.

You can also write this with generator expressions for simple transforms:

rows = read_rows("transactions.csv")
recent = (r for r in rows if float(r["timestamp"]) > cutoff)
converted = (dict(r, amount_usd=float(r["amount_eur"]) * 1.08) for r in recent)

Generator expressions use () instead of []. They follow the same lazy evaluation -- nothing runs until consumed.
```
**Why this is effective:** Pipeline composition is the most practical use of generators beyond simple iteration. Showing that "nothing has executed yet" drives home lazy evaluation. The generator expression alternative shows the syntactic shorthand without replacing the explicit version.

**Pair 3 (Advanced):**
```
Q: I'm building a client for a paginated API. Each page requires a network request, and I want to provide a clean iterator interface so callers can just write `for item in api.list_users()` without worrying about pagination. How do I implement this?

A: Use a generator that handles pagination internally, yielding individual items while fetching pages on demand:

import requests

class APIClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {api_key}"

    def list_users(self, per_page=100):
        """Yields User dicts, transparently handling pagination."""
        url = f"{self.base_url}/users"
        params = {"per_page": per_page, "cursor": None}

        while True:
            response = self.session.get(url, params=params)
            response.raise_for_status()
            data = response.json()

            for user in data["users"]:
                yield user

            # Check for next page
            next_cursor = data.get("next_cursor")
            if not next_cursor:
                return  # No more pages -- generator ends
            params["cursor"] = next_cursor

# Caller's code is beautifully simple:
client = APIClient("https://api.example.com", key)

# Get first 10 users (only fetches 1 page if per_page >= 10)
first_ten = list(itertools.islice(client.list_users(), 10))

# Process all users without loading them all into memory
for user in client.list_users():
    sync_to_local_db(user)

This pattern is powerful because:
- Callers don't know or care about pagination
- Pages are fetched lazily -- if the caller breaks early, remaining pages are never fetched
- islice() lets callers take exactly N items efficiently
- Memory usage is O(page_size), not O(total_users)

To make it even more robust, add retry logic inside the while loop and handle rate limiting by inspecting response headers. The generator's internal state (the cursor) survives across yield points, so retrying a failed page request is straightforward.
```
**Why this is effective:** Pagination is the canonical real-world use case for generators. The caller-side code (simple for-loop) demonstrates why the abstraction matters. The islice() tip shows composability with the standard library. This is production-grade code, not a tutorial toy.

**Quality checklist for these pairs:**
- [x] Each teaches exactly one concept
- [x] Questions are realistic (someone would actually ask this)
- [x] Answers show reasoning, not just solutions
- [x] Difficulty progression is clear
- [x] No factual errors'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
