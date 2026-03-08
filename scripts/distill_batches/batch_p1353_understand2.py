"""Understanding-focused training pairs: debugging, performance analysis, architecture, and concepts."""
PAIRS = [
    # ===================== DEBUG THIS ERROR (8 pairs) =====================

    (
        "understand2_01",
        r'''I'm getting a circular import error in Python. Here's the traceback:

```
ImportError: cannot import name 'UserService' from partially initialized module 'services.user' (most likely due to a circular import)
```

My files:
```python
# services/user.py
from services.auth import AuthService

class UserService:
    def __init__(self):
        self.auth = AuthService()
    def get_user(self, user_id):
        return {"id": user_id, "name": "Alice"}

# services/auth.py
from services.user import UserService

class AuthService:
    def __init__(self):
        self.users = UserService()
    def authenticate(self, user_id):
        user = self.users.get_user(user_id)
        return user is not None
```

What's going wrong and how do I fix it?''',
        r'''<think>
Classic circular import. Python starts loading `user.py`, hits the import of `auth.py`, starts loading `auth.py`, which tries to import `UserService` from `user.py` — but `user.py` hasn't finished initializing yet, so `UserService` doesn't exist. I need to explain the resolution order and give practical fixes: lazy import, dependency inversion, or restructuring.
</think>

## Circular Import Diagnosis

The error happens because of Python's **module loading order**:

1. Python starts loading `services/user.py`
2. First line: `from services.auth import AuthService` — Python pauses loading `user.py` and starts loading `auth.py`
3. First line of `auth.py`: `from services.user import UserService` — but `user.py` is only **partially initialized** (it paused at step 2), so `UserService` doesn't exist yet
4. **ImportError** — Python can't find `UserService` in the half-loaded module

The root cause is that `UserService` depends on `AuthService` **and** `AuthService` depends on `UserService`. This creates a dependency cycle.

### Fix 1: Lazy Import (Quickest)

Move the import inside the method that needs it:

```python
# services/auth.py
class AuthService:
    def authenticate(self, user_id):
        from services.user import UserService  # imported at call time, not load time
        users = UserService()
        user = users.get_user(user_id)
        return user is not None
```

This works because by the time `authenticate()` is called, both modules are fully loaded.

### Fix 2: Dependency Injection (Best)

Remove the circular dependency entirely by passing the dependency in:

```python
# services/auth.py — no import of UserService at all
class AuthService:
    def authenticate(self, user_service, user_id):
        user = user_service.get_user(user_id)
        return user is not None
```

```python
# services/user.py
from services.auth import AuthService

class UserService:
    def __init__(self):
        self.auth = AuthService()
    def get_user(self, user_id):
        return {"id": user_id, "name": "Alice"}
    def check_auth(self, user_id):
        return self.auth.authenticate(self, user_id)
```

### Fix 3: Extract Shared Interface

If both services genuinely need each other, the real problem is that they belong together or need an intermediary module:

```python
# services/base.py
class UserLookup:
    """Interface that AuthService depends on."""
    def get_user(self, user_id): ...
```

Then `AuthService` depends on `UserLookup` (in `base.py`), and `UserService` implements it. No cycle.

**General rule**: Circular imports almost always signal a design problem. Lazy imports are a band-aid; dependency injection or restructuring is the real fix.'''
    ),

    (
        "understand2_02",
        r'''I have this Python code that crashes with `TypeError: '<' not supported between instances of 'NoneType' and 'int'`:

```python
def find_minimum(items):
    result = None
    for item in items:
        if item < result:  # line 4 — crashes here
            result = item
    return result

print(find_minimum([3, 1, 4, 1, 5]))
```

Why does this happen on the first iteration?''',
        r'''## Why the TypeError Occurs

On the **first iteration**, `item` is `3` (an `int`) and `result` is `None`. Python tries to evaluate `3 < None`, and since Python 3 **removed implicit ordering between incompatible types**, this raises:

```
TypeError: '<' not supported between instances of 'NoneType' and 'int'
```

In Python 2, `None` was arbitrarily "less than" everything, which silently hid bugs. Python 3 correctly refuses to compare unrelated types.

### The Core Problem

You initialized `result = None` as a sentinel but then compared against it numerically. The comparison `item < result` assumes `result` is always a number, which is false on the first pass.

### Fix 1: Initialize from the sequence

```python
def find_minimum(items):
    result = items[0]  # start with first element
    for item in items[1:]:
        if item < result:
            result = item
    return result
```

This avoids the `None` comparison entirely. Add a guard for empty lists if needed:

```python
def find_minimum(items):
    if not items:
        return None  # or raise ValueError("empty sequence")
    result = items[0]
    for item in items[1:]:
        if item < result:
            result = item
    return result
```

### Fix 2: Use `math.inf` as sentinel

```python
import math

def find_minimum(items):
    result = math.inf  # larger than any real number
    for item in items:
        if item < result:
            result = item
    return result if result != math.inf else None
```

### Fix 3: Guard the None case

```python
def find_minimum(items):
    result = None
    for item in items:
        if result is None or item < result:
            result = item
    return result
```

This works but is slightly wasteful — you're checking `result is None` on every iteration when it's only `None` once.

**Best practice**: Use Fix 1. Initializing from the first element is the standard pattern (it's exactly what the built-in `min()` does internally). The sentinel approach is only needed when the initial value can't come from the sequence itself.'''
    ),

    (
        "understand2_03",
        r'''I'm getting this Rust compiler error and I don't understand the suggestion:

```rust
fn main() {
    let mut data = vec![1, 2, 3, 4, 5];
    let first = &data[0];
    data.push(6);
    println!("first: {}", first);
}
```

```
error[E0502]: cannot borrow `data` as mutable because it is also borrowed as immutable
 --> src/main.rs:4:5
  |
3 |     let first = &data[0];
  |                  ---- immutable borrow occurs here
4 |     data.push(6);
  |     ^^^^^^^^^^^^ mutable borrow occurs here
5 |     println!("first: {}", first);
  |                           ----- immutable borrow later used here
```

Why won't Rust let me push to a Vec while I have a reference to an element?''',
        r'''<think>
This is the classic Vec reallocation invalidation problem. The key insight is that `push()` might reallocate the Vec's backing buffer, which would leave `first` pointing to freed memory. Rust's borrow checker prevents this at compile time — this is the exact same bug that causes use-after-free in C++, but Rust catches it statically.
</think>

## Why the Borrow Checker Rejects This

This is one of Rust's most important safety guarantees. The issue is **memory invalidation through reallocation**.

### What Happens Inside `Vec::push`

A `Vec<T>` stores its elements in a heap-allocated buffer with a fixed capacity. When you call `push()` and the buffer is full, the Vec:

1. Allocates a **new, larger buffer** (typically 2x capacity)
2. Copies all existing elements to the new buffer
3. **Frees the old buffer**

After step 3, `first` (which points into the **old** buffer) becomes a **dangling pointer** — it points to freed memory. Reading from it is undefined behavior.

### Rust Prevents This at Compile Time

The borrow checker sees:
- Line 3: `first = &data[0]` — immutable borrow of `data` begins
- Line 4: `data.push(6)` — requires **mutable** borrow of `data`
- Line 5: `first` is used — immutable borrow is still **alive**

Rust's rule: **you cannot have a mutable borrow while any immutable borrows exist.** This prevents the push from silently invalidating `first`.

### How to Fix It

**Option 1**: Clone the value so you don't hold a reference:
```rust
let first = data[0];  // Copy the i32 value, no borrow
data.push(6);
println!("first: {}", first);  // works — first owns its value
```

**Option 2**: Finish using the reference before mutating:
```rust
let first = &data[0];
println!("first: {}", first);  // use it here
// immutable borrow ends — first is never used again
data.push(6);  // mutable borrow is fine now
```

**Option 3**: Use an index instead of a reference:
```rust
let first_idx = 0;
data.push(6);
println!("first: {}", data[first_idx]);
```

### The C++ Equivalent Bug

In C++, this compiles and runs with **undefined behavior**:
```cpp
std::vector<int> data = {1, 2, 3, 4, 5};
int& first = data[0];
data.push_back(6);  // may reallocate
std::cout << first;  // use-after-free — UB!
```

This is the exact class of bugs Rust's ownership system was designed to prevent. The compiler error is protecting you from a real memory safety vulnerability.'''
    ),

    (
        "understand2_04",
        r'''Getting this Rust error and I'm confused by trait bounds:

```rust
use std::collections::HashMap;

fn count_items<T>(items: &[T]) -> HashMap<T, usize> {
    let mut counts = HashMap::new();
    for item in items {
        *counts.entry(item).or_insert(0) += 1;
    }
    counts
}
```

```
error[E0599]: the method `entry` exists for struct `HashMap<T, usize>`, but its trait bounds were not satisfied
  --> src/main.rs:5:17
   |
5  |         *counts.entry(item).or_insert(0) += 1;
   |                 ^^^^^ method cannot be called on `HashMap<T, usize>` due to unsatisfied trait bounds
   |
   = note: the following trait bounds were not satisfied:
           `T: Eq`
           `T: Hash`
```

What does "trait bounds not satisfied" mean and how do I fix it?''',
        r'''## Understanding Trait Bounds

The error means your generic function says `T` can be **any type**, but `HashMap` needs its keys to be **hashable and comparable**. Not every type in Rust supports these operations, so the compiler won't let you use just any `T` as a key.

### Why HashMap Needs These Traits

A `HashMap<K, V>` works by:
1. **Hashing** the key to find which bucket to store it in → requires `Hash` trait
2. **Comparing** keys for equality when there are hash collisions → requires `Eq` trait

If `T` doesn't implement `Hash` and `Eq`, the HashMap literally cannot function. The compiler enforces this at the type level.

### The Fix: Add Trait Bounds

Tell the compiler that `T` must implement the required traits:

```rust
use std::collections::HashMap;
use std::hash::Hash;

fn count_items<T: Hash + Eq>(items: &[T]) -> HashMap<&T, usize> {
    let mut counts = HashMap::new();
    for item in items {
        *counts.entry(item).or_insert(0) += 1;
    }
    counts
}
```

Two changes:
1. **`T: Hash + Eq`** — constrains `T` to types that are hashable and equality-comparable
2. **`HashMap<&T, usize>`** — the return type uses `&T` because `item` from iterating over `&[T]` is a reference

### If You Want Owned Keys

If you want the HashMap to own its keys (not borrow them), add `Clone`:

```rust
fn count_items<T: Hash + Eq + Clone>(items: &[T]) -> HashMap<T, usize> {
    let mut counts = HashMap::new();
    for item in items {
        *counts.entry(item.clone()).or_insert(0) += 1;
    }
    counts
}
```

### What Types Satisfy These Bounds?

Most standard types implement `Hash + Eq`: `String`, `i32`, `u64`, `bool`, `&str`, tuples of hashable types. Types that **don't**: `f32`, `f64` (because `NaN != NaN` breaks `Eq`), and custom structs unless you derive the traits:

```rust
#[derive(Hash, Eq, PartialEq)]
struct UserId(u64);
```

### Reading Trait Bound Errors

When you see "trait bounds not satisfied," the fix is almost always: add the missing traits to your generic parameter with `+`. The compiler tells you exactly which traits are missing — just add them to the `where` clause or inline bounds.'''
    ),

    (
        "understand2_05",
        r'''My Go program panics with this error:

```
fatal error: all goroutines are asleep - deadlock!

goroutine 1 [chan receive]:
main.main()
    /tmp/main.go:18 +0x120

goroutine 6 [chan send]:
main.process(0x0, 0xc0000b6000)
    /tmp/main.go:10 +0x40
```

```go
package main

import "fmt"

func process(id int, results chan<- string) {
    results <- fmt.Sprintf("result from %d", id)
}

func main() {
    results := make(chan string)

    for i := 0; i < 5; i++ {
        go process(i, results)
    }

    for i := 0; i < 5; i++ {
        fmt.Println(<-results)
    }
    close(results)
}
```

Wait, actually the code above works fine when I test it. But my real code looks more like this:

```go
func main() {
    results := make(chan string)

    for i := 0; i < 5; i++ {
        go process(i, results)
    }

    var all []string
    for result := range results {  // blocks forever!
        all = append(all, result)
    }
    fmt.Println(all)
}
```

Why does using `range` over the channel cause a deadlock?''',
        r'''<think>
The issue is that `range` over a channel keeps reading until the channel is **closed**. The 5 goroutines send their results and exit, but nobody ever closes the channel. So after receiving all 5 values, `range` blocks waiting for more — and since all goroutines are done, the runtime detects deadlock. The first version works because the `for i := 0; i < 5` loop reads exactly 5 values and stops.
</think>

## Why `range` Over an Unbuffered Channel Deadlocks

The key difference between your two versions:

- **`for i := 0; i < 5; i++`** — reads exactly 5 values, then stops
- **`for result := range results`** — reads until the channel is **closed**

The `range` loop is equivalent to:
```go
for {
    result, ok := <-results
    if !ok {
        break  // only breaks when channel is closed
    }
    all = append(all, result)
}
```

After all 5 goroutines send their values and exit, nobody calls `close(results)`. The `range` loop blocks on a 6th receive that will never come. The Go runtime sees that every goroutine is either finished or blocked, so it panics with "all goroutines are asleep — deadlock!"

### Fix 1: Use a WaitGroup to Close the Channel

```go
func main() {
    results := make(chan string)
    var wg sync.WaitGroup

    for i := 0; i < 5; i++ {
        wg.Add(1)
        go func(id int) {
            defer wg.Done()
            results <- fmt.Sprintf("result from %d", id)
        }(i)
    }

    // Close channel after all goroutines finish
    go func() {
        wg.Wait()
        close(results)
    }()

    var all []string
    for result := range results {
        all = append(all, result)
    }
    fmt.Println(all)
}
```

The closing goroutine waits for all senders to finish, then closes the channel, which terminates the `range` loop.

### Fix 2: Know the Count (Simpler)

If you know how many results to expect, just count them:

```go
var all []string
for i := 0; i < 5; i++ {
    all = append(all, <-results)
}
```

### When to Use Which

- **Known count**: Use a counted loop — simpler, no WaitGroup needed
- **Unknown count** (e.g., producer decides when to stop): Use WaitGroup + close pattern
- **Multiple producers, complex lifetime**: Consider a `done` channel or `context.Context` for cancellation

### Common Mistake

Never close a channel from the receiver side. The **sender** (or a coordinator that knows when all senders are done) should close the channel. Closing from the receiver causes a panic if a sender tries to write to the closed channel.'''
    ),

    (
        "understand2_06",
        r'''My Go code panics with a nil pointer dereference but I don't see where the nil comes from:

```go
type Logger interface {
    Log(msg string)
}

type App struct {
    logger Logger
}

func NewApp() *App {
    return &App{}
}

func (a *App) Start() {
    a.logger.Log("starting up")  // panic: nil pointer dereference
}
```

I didn't get a compile error, so why does it crash?''',
        r'''## Why Go Interfaces Allow Nil Without a Compile Error

In Go, interfaces have a **zero value of `nil`**. When you create `&App{}`, the `logger` field is initialized to its zero value — which for the `Logger` interface is `nil`. The compiler doesn't flag this because:

1. `App.logger` has type `Logger` (an interface) — perfectly valid type
2. Go doesn't have a concept of "non-nullable" interface types
3. The struct literal `&App{}` is valid — zero-value initialization is a core Go pattern

The crash happens at runtime when you call `a.logger.Log("starting up")`. Go tries to dispatch the method call on the interface value, finds it's `nil`, and panics.

### The Subtle Part: Interface Nil vs Typed Nil

Go has a confusing distinction. An interface is nil only when **both** its type and value are nil:

```go
var l Logger          // nil interface (type=nil, value=nil)
fmt.Println(l == nil) // true — calling l.Log() panics

var s *StdoutLogger   // typed nil pointer
l = s                 // interface now has (type=*StdoutLogger, value=nil)
fmt.Println(l == nil) // false! — but calling l.Log() may still panic
```

### Fix 1: Require the Dependency in the Constructor

```go
func NewApp(logger Logger) *App {
    if logger == nil {
        panic("logger is required")
    }
    return &App{logger: logger}
}
```

This is the Go convention — make required dependencies constructor parameters.

### Fix 2: Provide a Default

```go
type noopLogger struct{}
func (noopLogger) Log(string) {}

func NewApp() *App {
    return &App{logger: noopLogger{}}
}

func (a *App) WithLogger(l Logger) *App {
    a.logger = l
    return a
}
```

### Fix 3: Nil Check Before Use

```go
func (a *App) Start() {
    if a.logger != nil {
        a.logger.Log("starting up")
    }
}
```

This works but scatters nil checks everywhere. Prefer Fix 1 or Fix 2.

**Best practice**: In Go, required dependencies should be constructor parameters. Optional ones should have a sensible default (like a no-op implementation). The type system won't protect you from nil interfaces, so defend at the boundary where the value is set.'''
    ),

    (
        "understand2_07",
        r'''I have this JavaScript code that throws "Cannot read properties of undefined (reading 'name')" but only sometimes:

```javascript
async function getUser(id) {
    const response = await fetch(`/api/users/${id}`);
    const data = await response.json();
    return data;
}

async function getUserProjects(userId) {
    const user = await getUser(userId);
    const response = await fetch(`/api/projects?owner=${user.name}`);
    return response.json();
}

async function main() {
    const projects = await getUserProjects(42);
    console.log(projects);
}
```

The error points to `user.name` in `getUserProjects`. Why does it only fail sometimes?''',
        r'''<think>
The intermittent failure is the key clue. The code doesn't check if the API response was successful. When `/api/users/42` returns a 404 or 500, `response.json()` might parse to `undefined`, `null`, or an error object without a `name` field. The `fetch` API doesn't throw on HTTP errors — it only throws on network failures. So `response.ok` could be false, but the code proceeds to use `data` as if it's always a valid user object.
</think>

## Why This Fails Intermittently

The bug is that **`fetch` doesn't throw on HTTP errors**. It only throws on network failures (DNS failure, server unreachable). A 404 or 500 response is a "successful" fetch from the network perspective.

### What Happens on a Failed Request

```javascript
const response = await fetch(`/api/users/42`);
// response.status might be 404
// response.ok is false
// But NO error is thrown!

const data = await response.json();
// Parses the error body: maybe { "error": "not found" }
// Or maybe the body is empty/invalid → data is undefined
```

Now `data` is either `undefined`, `null`, or an object like `{"error": "not found"}` — none of which have a `.name` property.

It works "sometimes" because:
- When the API returns 200 → `data` is `{"name": "alice", ...}` → works
- When the API returns 404/500 or is slow and times out → `data` has no `.name` → crash

### The Fix: Check Response Status

```javascript
async function getUser(id) {
    const response = await fetch(`/api/users/${id}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch user ${id}: ${response.status}`);
    }
    const data = await response.json();
    return data;
}

async function getUserProjects(userId) {
    const user = await getUser(userId);
    if (!user?.name) {
        throw new Error(`User ${userId} has no name field`);
    }
    const response = await fetch(`/api/projects?owner=${user.name}`);
    if (!response.ok) {
        throw new Error(`Failed to fetch projects: ${response.status}`);
    }
    return response.json();
}
```

### Key Lessons

1. **Always check `response.ok`** (or `response.status`) after `fetch`. This is the #1 `fetch` footgun.
2. **Validate the shape of API responses** before accessing nested properties. Use optional chaining (`user?.name`) for defensive access.
3. **Intermittent errors usually mean an unchecked external dependency** — network, API, database. The "sometimes" is the clue that the code path depends on something outside your control.'''
    ),

    (
        "understand2_08",
        r'''My C++ program segfaults and I've narrowed it down to this section:

```cpp
#include <vector>
#include <iostream>

int main() {
    std::vector<int> nums = {1, 2, 3, 4, 5};

    for (auto it = nums.begin(); it != nums.end(); ++it) {
        if (*it % 2 == 0) {
            nums.erase(it);  // remove even numbers
        }
    }

    for (int n : nums) {
        std::cout << n << " ";
    }
}
```

Sometimes it crashes, sometimes it prints garbage. What's wrong?''',
        r'''## Iterator Invalidation: The Classic C++ Trap

The bug is that `nums.erase(it)` **invalidates** the iterator `it` and every iterator after it. When the loop then does `++it`, it increments an invalidated iterator — undefined behavior. This can segfault, skip elements, read garbage memory, or appear to work (the worst outcome, because it hides the bug).

### Why Erase Invalidates Iterators

When you erase an element from a `std::vector`, all elements after it shift left to fill the gap. The internal memory layout changes:

```
Before erase(it) where *it == 2:
[1, 2, 3, 4, 5]
     ^it

After erase:
[1, 3, 4, 5]
     ^it is now invalidated — it pointed to the old layout
```

The iterator `it` now points to shifted memory. Incrementing it skips the element that shifted into position (3), and at the end of the vector, `it` may fly past `end()`.

### The Fix: Use Erase's Return Value

`erase()` returns an iterator to the **next valid element** after the erased one:

```cpp
for (auto it = nums.begin(); it != nums.end(); /* no ++it here */) {
    if (*it % 2 == 0) {
        it = nums.erase(it);  // returns iterator to next element
    } else {
        ++it;  // only advance if we didn't erase
    }
}
```

### The Modern Fix: Erase-Remove Idiom

C++20 added `std::erase_if` which is cleaner:

```cpp
std::erase_if(nums, [](int n) { return n % 2 == 0; });
```

Pre-C++20, use the erase-remove idiom:

```cpp
nums.erase(
    std::remove_if(nums.begin(), nums.end(),
                   [](int n) { return n % 2 == 0; }),
    nums.end()
);
```

`std::remove_if` shifts wanted elements to the front and returns an iterator to the new logical end. `erase` then chops off the tail. This is O(n) instead of O(n²) from repeated single erases.

### Iterator Invalidation Rules by Container

- **`vector`**: erase/insert invalidates iterators at and after the point of modification
- **`deque`**: erase/insert anywhere invalidates all iterators
- **`list`/`map`/`set`**: erase only invalidates the erased iterator — others remain valid

When in doubt, consult the container's invalidation rules or use the erase-remove idiom.'''
    ),

    # ===================== ANALYZE PERFORMANCE (7 pairs) =====================

    (
        "understand2_09",
        r'''This Django view is slow when a user has many orders. Why?

```python
def user_orders_view(request, user_id):
    user = User.objects.get(id=user_id)
    orders = Order.objects.filter(user=user)

    result = []
    for order in orders:
        items = OrderItem.objects.filter(order=order)
        result.append({
            "order_id": order.id,
            "total": order.total,
            "items": [
                {
                    "product": item.product.name,  # another query!
                    "qty": item.quantity,
                }
                for item in items
            ],
        })
    return JsonResponse({"orders": result})
```''',
        r'''<think>
Classic N+1 query problem. For a user with 100 orders and 5 items each: 1 query for user + 1 for orders + 100 for items + 500 for products = 602 queries. Should be 1-3 queries with select_related/prefetch_related. Let me break down the exact query count and show the fix.
</think>

## N+1 Query Problem

This code executes **1 + 1 + N + (N × M)** database queries, where N is the number of orders and M is the average items per order. For a user with 100 orders averaging 5 items each:

| Step | Queries | Count |
|------|---------|-------|
| `User.objects.get(id=user_id)` | 1 query | 1 |
| `Order.objects.filter(user=user)` | 1 query | 1 |
| `OrderItem.objects.filter(order=order)` inside loop | 1 per order | 100 |
| `item.product.name` (lazy load) | 1 per item | 500 |
| **Total** | | **602 queries** |

Each query has network round-trip overhead (typically 1-5ms), so 602 queries take 0.6-3 seconds even if each query is trivial.

### The Fix: Eager Loading

```python
def user_orders_view(request, user_id):
    orders = (
        Order.objects
        .filter(user_id=user_id)
        .prefetch_related(
            Prefetch(
                'orderitem_set',
                queryset=OrderItem.objects.select_related('product')
            )
        )
    )

    result = []
    for order in orders:
        result.append({
            "order_id": order.id,
            "total": order.total,
            "items": [
                {
                    "product": item.product.name,  # no extra query!
                    "qty": item.quantity,
                }
                for item in order.orderitem_set.all()  # no extra query!
            ],
        })
    return JsonResponse({"orders": result})
```

This executes **3 queries total** regardless of how many orders or items:
1. `SELECT * FROM orders WHERE user_id = ?`
2. `SELECT * FROM order_items WHERE order_id IN (?, ?, ...)`
3. `SELECT * FROM products WHERE id IN (?, ?, ...)`

### How to Detect N+1 Queries

- **Django Debug Toolbar**: Shows query count per request in development
- **`django.db.connection.queries`**: Log all queries in a test
- **`nplusone` package**: Automatically warns about N+1 patterns
- **Rule of thumb**: If you see a query inside a `for` loop over a queryset, it's almost certainly an N+1 problem

### Key ORM Concepts

- **`select_related`**: Uses SQL JOIN — works for ForeignKey/OneToOne (single parent)
- **`prefetch_related`**: Uses separate query + Python-side join — works for reverse ForeignKey/ManyToMany (multiple children)

Going from 602 queries to 3 queries typically gives a **10-100x speedup** on this pattern.'''
    ),

    (
        "understand2_10",
        r'''Why is this Python string building code slow when processing millions of log lines?

```python
def build_report(log_lines):
    report = ""
    for line in log_lines:
        if "ERROR" in line:
            report = report + "[ERR] " + line + "\n"
    return report
```''',
        r'''<think>
The user is concatenating strings in a loop. Python strings are immutable, so each concatenation creates a new string and copies the entire existing content. That's O(n²) total copying. The fix is str.join() which pre-calculates total length and does one allocation, or io.StringIO for streaming builds.
</think>

## String Concatenation in a Loop: O(n²) Hidden Cost

The problem is that **Python strings are immutable**. Every time you do `report = report + "[ERR] " + line + "\n"`, Python:

1. Allocates a **new** string large enough for the concatenated result
2. Copies the **entire** existing `report` into the new string
3. Appends the new content
4. The old `report` string becomes garbage

If you have 100,000 error lines averaging 100 characters, the copy sizes grow like: 100, 200, 300, ..., 10,000,000 bytes. The total bytes copied is roughly `n² × avg_len / 2` — that's about **500 GB** of memory copies for 100K lines.

### Fix: Use `str.join()`

```python
def build_report(log_lines):
    error_lines = []
    for line in log_lines:
        if "ERROR" in line:
            error_lines.append(f"[ERR] {line}")
    return "\n".join(error_lines)
```

Or more concisely with a generator:

```python
def build_report(log_lines):
    return "\n".join(
        f"[ERR] {line}"
        for line in log_lines
        if "ERROR" in line
    )
```

### Why `join()` Is O(n)

`str.join()` first calculates the total length needed, allocates **one** string of that size, then copies each piece into the pre-allocated buffer exactly once. Total bytes copied: `n × avg_len` — linear, not quadratic.

### Benchmark Comparison

For 100,000 error lines:
- **Concatenation**: ~12 seconds (quadratic growth in copy cost)
- **`join()`**: ~0.02 seconds (single allocation + linear copy)

That's roughly a **600x speedup**.

### Alternative: `io.StringIO`

If you need to build a string incrementally (not all at once), use `StringIO`:

```python
from io import StringIO

def build_report(log_lines):
    buf = StringIO()
    for line in log_lines:
        if "ERROR" in line:
            buf.write(f"[ERR] {line}\n")
    return buf.getvalue()
```

`StringIO` uses an internal buffer that grows with amortized O(1) appends (like a list), then produces the final string in one pass.

**Rule of thumb**: Never concatenate strings in a loop. Use `join()` for building from a collection, `StringIO` for streaming/conditional builds.'''
    ),

    (
        "understand2_11",
        r'''I have a hot loop in Rust that processes millions of strings and it's slower than expected. Profiling shows most time in allocation:

```rust
fn process_records(records: &[Record]) -> Vec<String> {
    let mut results = Vec::new();
    for record in records {
        let key = String::from(&record.category) + ":" + &record.id.to_string();
        let normalized = key.to_lowercase();
        let trimmed = normalized.trim().to_string();
        results.push(trimmed);
    }
    results
}
```

How can I reduce allocations?''',
        r'''<think>
Let me count the allocations per iteration: (1) String::from for category, (2) record.id.to_string(), (3) the concatenation creates another String, (4) to_lowercase() creates a new String, (5) trim().to_string() creates another. That's 5 allocations per record. For millions of records, that's devastating. I should show how to reuse a buffer with write!/format! and pre-allocate the results vec.
</think>

## Allocation Analysis

Each loop iteration performs **5 heap allocations**:

```rust
let key = String::from(&record.category)   // alloc 1: clone category
    + ":"                                    // alloc 2: grow or realloc for concat
    + &record.id.to_string();               // alloc 3: id to string
let normalized = key.to_lowercase();         // alloc 4: new lowercase string
let trimmed = normalized.trim().to_string(); // alloc 5: clone trimmed slice
```

For 1 million records, that's **5 million allocations**. Each allocation involves a system call to the allocator, possible cache misses, and eventual deallocation overhead.

### Optimized Version: Reuse a Buffer

```rust
use std::fmt::Write;

fn process_records(records: &[Record]) -> Vec<String> {
    let mut results = Vec::with_capacity(records.len()); // pre-allocate
    let mut buf = String::with_capacity(128); // reusable buffer

    for record in records {
        buf.clear(); // resets length to 0, keeps allocation
        write!(buf, "{}:{}", record.category, record.id).unwrap();
        buf.make_ascii_lowercase(); // in-place, no allocation

        let trimmed = buf.trim();
        results.push(trimmed.to_owned()); // 1 allocation (unavoidable)
    }
    results
}
```

### What Changed

| Original | Optimized | Why |
|----------|-----------|-----|
| `String::from() + ":" + &to_string()` | `write!(buf, ...)` | Formats directly into reused buffer, 0 allocations |
| `to_lowercase()` | `make_ascii_lowercase()` | Mutates in-place, 0 allocations |
| `trim().to_string()` | `trim().to_owned()` | Same 1 allocation (must clone to own) |
| `Vec::new()` | `Vec::with_capacity(n)` | Single allocation instead of repeated doubling |

**Result**: 5 allocations per iteration → 1 allocation per iteration, plus the buffer stabilizes after the first iteration and stops reallocating.

### Further Optimization: Interning or Indices

If many records share the same category, consider interning strings or using indices into a lookup table:

```rust
use std::collections::HashMap;

fn process_records(records: &[Record]) -> Vec<usize> {
    let mut intern: HashMap<String, usize> = HashMap::new();
    let mut table: Vec<String> = Vec::new();

    records.iter().map(|record| {
        // build key, check if seen before
        let key = format!("{}:{}", record.category, record.id).to_lowercase();
        let len = intern.len();
        *intern.entry(key.clone()).or_insert_with(|| {
            table.push(key);
            len
        })
    }).collect()
}
```

**General rule for hot loops**: Allocate outside the loop, reuse buffers inside, use `with_capacity` when the size is known, and prefer in-place mutation (`make_ascii_lowercase`) over allocating transformations (`to_lowercase`).'''
    ),

    (
        "understand2_12",
        r'''My Go service handles 50k requests/second but latency spikes occur randomly. Profiling shows contention on this shared counter:

```go
var (
    mu       sync.Mutex
    counters map[string]int64
)

func IncrementCounter(key string) {
    mu.Lock()
    counters[key]++
    mu.Unlock()
}

func GetCounter(key string) int64 {
    mu.Lock()
    defer mu.Unlock()
    return counters[key]
}
```

All 50k requests funnel through one mutex. How do I fix the contention?''',
        r'''## Global Mutex Contention

A single `sync.Mutex` protecting all counters serializes **every** request. At 50k req/s with, say, 100 different counter keys, goroutines waiting for the lock stack up. The lock itself is fast (~20ns uncontended), but under contention, goroutines spin and then park, causing latency spikes when many hit the lock simultaneously.

### Fix 1: Sharded Locks (Best General Solution)

Split the map into N shards, each with its own mutex. Requests to different shards proceed in parallel:

```go
const numShards = 64

type CounterShard struct {
    mu       sync.Mutex
    counters map[string]int64
}

type ShardedCounters struct {
    shards [numShards]CounterShard
}

func NewShardedCounters() *ShardedCounters {
    sc := &ShardedCounters{}
    for i := range sc.shards {
        sc.shards[i].counters = make(map[string]int64)
    }
    return sc
}

func (sc *ShardedCounters) shard(key string) *CounterShard {
    h := fnv32(key)
    return &sc.shards[h%numShards]
}

func (sc *ShardedCounters) Increment(key string) {
    s := sc.shard(key)
    s.mu.Lock()
    s.counters[key]++
    s.mu.Unlock()
}
```

Contention drops by roughly `numShards`x because only 1/64th of requests compete for the same lock.

### Fix 2: `sync.Map` (Read-Heavy Workloads)

If reads vastly outnumber writes:

```go
var counters sync.Map

func IncrementCounter(key string) {
    for {
        val, _ := counters.LoadOrStore(key, new(atomic.Int64))
        counter := val.(*atomic.Int64)
        counter.Add(1)
        return
    }
}
```

`sync.Map` is optimized for cases where keys are stable and reads dominate. It uses a read-only fast path that avoids locking entirely.

### Fix 3: Per-Goroutine Buffering

Buffer increments locally and flush periodically:

```go
type LocalCounters struct {
    buf map[string]int64
    sc  *ShardedCounters
}

func (lc *LocalCounters) Increment(key string) {
    lc.buf[key]++
    if len(lc.buf) > 1000 {
        lc.Flush()
    }
}

func (lc *LocalCounters) Flush() {
    for k, v := range lc.buf {
        lc.sc.IncrementBy(k, v)
    }
    lc.buf = make(map[string]int64)
}
```

This batches lock acquisitions — instead of locking per request, you lock once per 1000 increments.

### Which to Choose

| Pattern | Best For | Tradeoff |
|---------|----------|----------|
| Sharded locks | General purpose, write-heavy | Slight code complexity |
| `sync.Map` | Read-heavy, stable key set | Slower for write-heavy |
| Local buffering | Extreme throughput | Counters are eventually consistent |
| `atomic.Int64` | Single counter | Doesn't work for dynamic keys |

For your case (50k writes/s, 100 keys), **sharded locks with 64 shards** is the straightforward win.'''
    ),

    (
        "understand2_13",
        r'''My React app is laggy and React DevTools Profiler shows frequent re-renders of `<ExpensiveList>` even when the list data hasn't changed. Here's my component:

```jsx
function Dashboard({ userId }) {
    const [filters, setFilters] = useState({ status: 'all' });
    const [items, setItems] = useState([]);

    useEffect(() => {
        fetchItems(userId).then(setItems);
    }, [userId]);

    const filteredItems = items.filter(item =>
        filters.status === 'all' || item.status === filters.status
    );

    return (
        <div>
            <FilterBar filters={filters} onChange={setFilters} />
            <ExpensiveList items={filteredItems} />
            <StatusBar count={filteredItems.length} />
        </div>
    );
}
```

Why does ExpensiveList re-render when I type in a totally unrelated input field that's also on this page?''',
        r'''<think>
The issue is object identity. Every render of `Dashboard` creates a **new** `filteredItems` array via `.filter()`. Even if the filter hasn't changed and produces identical results, it's a new array reference. `ExpensiveList` gets a new `items` prop reference every render, so React re-renders it. Additionally, any state change in a parent (or sibling in the same parent) causes Dashboard to re-render, which recreates filteredItems. The fix is `useMemo` for the filtered array.
</think>

## Re-render Cascade from Object Identity

The problem is on this line:

```jsx
const filteredItems = items.filter(item =>
    filters.status === 'all' || item.status === filters.status
);
```

Every time `Dashboard` re-renders (for **any** reason — a sibling state change, parent re-render, unrelated context update), `items.filter()` creates a **new array**. Even if the contents are identical, it's a new object reference:

```jsx
[1, 2, 3] === [1, 2, 3]  // false — different references
```

React's default behavior is to re-render a child whenever its parent re-renders, and since `filteredItems` is always a new reference, even `React.memo(ExpensiveList)` won't help — the `items` prop looks "changed" to the shallow comparison.

### Fix: `useMemo` to Stabilize the Reference

```jsx
const filteredItems = useMemo(
    () => items.filter(item =>
        filters.status === 'all' || item.status === filters.status
    ),
    [items, filters.status]  // only recompute when these change
);
```

Now `filteredItems` keeps the **same reference** between renders unless `items` or `filters.status` actually changes.

### Also Memoize the Child

Wrap `ExpensiveList` with `React.memo` so it skips re-rendering when props haven't changed:

```jsx
const ExpensiveList = React.memo(function ExpensiveList({ items }) {
    // expensive rendering logic
    return items.map(item => <ItemCard key={item.id} item={item} />);
});
```

With both `useMemo` on the data and `React.memo` on the component, `ExpensiveList` only re-renders when the filtered data genuinely changes.

### Common Object Identity Traps

```jsx
// BAD: new object every render
<Child style={{ color: 'red' }} />
<Child onClick={() => handleClick(id)} />
<Child config={{ ...baseConfig, extra: true }} />

// GOOD: stable references
const style = useMemo(() => ({ color: 'red' }), []);
const onClick = useCallback(() => handleClick(id), [id]);
```

### Debugging Tip

In React DevTools Profiler, enable "Record why each component rendered." It will tell you exactly which prop changed, making it easy to spot reference-identity issues.'''
    ),

    (
        "understand2_14",
        r'''My Node.js server becomes unresponsive for seconds at a time. I found this endpoint:

```javascript
app.get('/api/report', async (req, res) => {
    const data = fs.readFileSync('/data/large-report.csv'); // 200MB file
    const lines = data.toString().split('\n');
    const parsed = lines.map(line => {
        const cols = line.split(',');
        return { name: cols[0], value: parseFloat(cols[1]) };
    });
    const total = parsed.reduce((sum, row) => sum + row.value, 0);
    res.json({ total, rowCount: parsed.length });
});
```

Why does this freeze the entire server, not just this request?''',
        r'''## Blocking the Event Loop

Node.js runs JavaScript on a **single thread** (the event loop). When you call `fs.readFileSync` on a 200MB file, that thread is blocked doing I/O — it literally cannot process any other requests, timers, or callbacks until the read completes.

But the I/O is only the start. After reading, you're doing **CPU-intensive synchronous work** on the main thread:

1. `data.toString()` — converts 200MB Buffer to a string (allocates ~400MB for UTF-16)
2. `.split('\n')` — creates millions of string objects
3. `.map(...)` — parses every line synchronously, creating millions of objects
4. `.reduce(...)` — iterates the entire array

The event loop is frozen for the entire duration — typically **several seconds** for 200MB. Every other request queued during this time gets no response.

### Fix 1: Stream Processing (Best)

```javascript
const { createReadStream } = require('fs');
const readline = require('readline');

app.get('/api/report', async (req, res) => {
    const rl = readline.createInterface({
        input: createReadStream('/data/large-report.csv'),
        crlfDelay: Infinity,
    });

    let total = 0;
    let rowCount = 0;

    for await (const line of rl) {
        const cols = line.split(',');
        total += parseFloat(cols[1]) || 0;
        rowCount++;
    }

    res.json({ total, rowCount });
});
```

This processes one line at a time using streams. Memory stays low (kilobytes instead of gigabytes), and the `for await` loop yields back to the event loop between chunks, so other requests get processed.

### Fix 2: Worker Thread for CPU-Heavy Work

```javascript
const { Worker } = require('worker_threads');

app.get('/api/report', async (req, res) => {
    const result = await new Promise((resolve, reject) => {
        const worker = new Worker('./report-worker.js');
        worker.on('message', resolve);
        worker.on('error', reject);
    });
    res.json(result);
});
```

This offloads the entire computation to a separate thread, keeping the event loop free.

### Memory Impact

The original code's peak memory for 200MB CSV:
- 200MB raw Buffer
- ~400MB string (UTF-16 encoding)
- Millions of split strings + parsed objects

Total: easily **1-2GB** peak. The streaming version uses ~64KB at any point.

**Rule**: In Node.js, never use `*Sync` functions in request handlers, and never process large data synchronously. Stream or offload to a worker.'''
    ),

    (
        "understand2_15",
        r'''Our PostgreSQL query is slow and the DBA told me to look at the EXPLAIN output:

```sql
EXPLAIN ANALYZE SELECT * FROM orders
WHERE customer_id = 12345
AND status = 'pending'
AND created_at > '2025-01-01'
ORDER BY created_at DESC
LIMIT 20;
```

```
Limit  (cost=15234.56..15234.61 rows=20 width=128) (actual time=892.451..892.458 rows=20 loops=1)
  ->  Sort  (cost=15234.56..15289.12 rows=21824 width=128) (actual time=892.449..892.453 rows=20 loops=1)
        Sort Key: created_at DESC
        Sort Method: top-N heapsort  Memory: 28kB
        ->  Seq Scan on orders  (cost=0.00..14523.00 rows=21824 width=512) (actual time=0.021..867.234 rows=21513 loops=1)
              Filter: ((customer_id = 12345) AND (status = 'pending'::text) AND (created_at > '2025-01-01'))
              Rows Removed by Filter: 978487
```

What does this tell me and how do I fix it?''',
        r'''## Reading the EXPLAIN ANALYZE Output

Let me walk through what each line tells you:

**The critical line is `Seq Scan on orders`** — PostgreSQL is reading the **entire table** (1,000,000 rows) sequentially, then filtering down to 21,513 matches, then sorting, then taking the top 20. The 867ms is almost entirely spent scanning rows that get thrown away.

### Breaking Down the Numbers

| Metric | Meaning |
|--------|---------|
| `Seq Scan` | Full table scan — no index used |
| `rows=21824` (estimated) vs `rows=21513` (actual) | Estimates are close, so statistics are fine |
| `Rows Removed by Filter: 978487` | Scanned ~1M rows, kept ~21K — 97.8% wasted I/O |
| `actual time=867.234` | 867ms just to scan and filter |
| `Sort Method: top-N heapsort` | Efficient for LIMIT + ORDER BY (only tracks top 20) |

### The Fix: Composite Index

Create an index that covers all three filter columns plus the sort column:

```sql
CREATE INDEX idx_orders_customer_status_created
ON orders (customer_id, status, created_at DESC);
```

Column order matters — put **equality** conditions first (`customer_id`, `status`), then the **range/sort** column (`created_at`). This lets PostgreSQL:

1. Jump directly to `customer_id = 12345` entries (B-tree seek)
2. Within those, jump to `status = 'pending'` (B-tree seek)
3. Walk the `created_at DESC` entries in order
4. Stop after 20 rows (no sort needed — the index is already ordered)

### Expected EXPLAIN After Index

```
Limit  (cost=0.56..12.34 rows=20 width=128) (actual time=0.045..0.089 rows=20 loops=1)
  ->  Index Scan using idx_orders_customer_status_created on orders
        Index Cond: ((customer_id = 12345) AND (status = 'pending') AND (created_at > '2025-01-01'))
```

**Index Scan** instead of Seq Scan. The query goes from 867ms to under 1ms because it reads exactly the 20 rows it needs directly from the index, already in the correct order.

### Key EXPLAIN Red Flags

- **`Seq Scan`** on large tables with selective filters → needs an index
- **`Rows Removed by Filter`** much larger than rows returned → index not covering the filter
- **`Sort`** appearing when you have ORDER BY + LIMIT → index could eliminate the sort
- **Estimated rows wildly different from actual** → run `ANALYZE tablename` to update statistics'''
    ),

    # ===================== EXPLAIN THE ARCHITECTURE (8 pairs) =====================

    (
        "understand2_16",
        r'''Why does Rust use ownership instead of garbage collection? What problem does it actually solve?''',
        r'''## Ownership vs Garbage Collection: Different Tradeoffs

Both ownership and garbage collection solve the same core problem: **when is it safe to free memory?** They just solve it at different times with different costs.

### The Problem

When multiple parts of a program reference the same data, you need to know when **no one** references it anymore so you can free it. Get this wrong and you get:
- **Use-after-free**: Memory freed too early, dangling pointer reads garbage
- **Memory leak**: Memory never freed, usage grows forever
- **Double free**: Memory freed twice, corrupts the allocator

### How GC Solves It (Java, Go, Python, JS)

A garbage collector periodically scans all live references, finds objects no one points to, and frees them. The programmer never explicitly frees memory.

**Cost**: GC must pause or slow the program to scan references. This creates unpredictable latency spikes (GC pauses). GC also uses extra memory — typically 2-3x the live data set — because it needs headroom before triggering a collection. And the runtime overhead of reference tracking is constant.

### How Ownership Solves It (Rust)

Rust uses three compile-time rules instead of a runtime scanner:
1. **Every value has exactly one owner**
2. **When the owner goes out of scope, the value is dropped (freed)**
3. **You can have either one mutable reference OR multiple immutable references, not both**

```rust
fn process() {
    let data = vec![1, 2, 3];  // data owns the Vec
    do_something(&data);        // borrow — data still owns it
}  // data goes out of scope → Vec is freed immediately, deterministically
```

The compiler tracks ownership at compile time. There is **zero runtime cost** — no GC pauses, no reference counting, no scanning. Memory is freed the instant its owner's scope ends.

### What Ownership Actually Gives You

1. **Deterministic destruction**: Resources (files, sockets, locks) are released immediately when scope ends, not "eventually" when the GC runs
2. **No GC pauses**: Critical for real-time systems, game engines, embedded systems
3. **Lower memory usage**: No 2-3x GC headroom needed
4. **Thread safety guarantee**: The borrow rules prevent data races at compile time — this is the often-overlooked killer feature

### The Tradeoff

Ownership is **harder to program with**. Some patterns that are trivial with GC (graphs, doubly-linked lists, circular references) require explicit design decisions in Rust (`Rc<T>`, `Arc<T>`, or redesigning the data structure). The compiler rejects programs that violate ownership rules, which means a steeper learning curve.

### When Each Makes Sense

- **GC**: Application code where developer productivity matters more than latency (web services, scripts, business logic)
- **Ownership**: Systems where predictability matters (OS kernels, game engines, embedded, databases, network infrastructure)'''
    ),

    (
        "understand2_17",
        r'''Explain the actor model and when I should use it versus shared-state concurrency.''',
        r'''<think>
Actor model: each actor is an independent unit with its own state, communicating only through message passing. No shared memory. Erlang/Elixir are the canonical examples, Akka in JVM land. Compare with shared-state using mutexes/atomics. The key tradeoff is reasoning simplicity vs performance.
</think>

## The Actor Model

In the actor model, the fundamental unit of computation is an **actor** — a lightweight, isolated entity that:

1. Has **private state** that no other actor can access directly
2. Communicates **only by sending and receiving messages**
3. Can create new actors, send messages, and decide how to handle the next message
4. Processes **one message at a time** (no internal concurrency)

```
Actor A                    Actor B
┌──────────┐   message    ┌──────────┐
│ state: 5  │────────────→│ state: 10│
│ mailbox   │             │ mailbox  │
└──────────┘   message    └──────────┘
              ←────────────
```

Because each actor processes messages sequentially and never shares state, there are **no locks, no data races, and no deadlocks** by construction.

### Shared-State Concurrency

The alternative is threads/goroutines sharing memory, protected by synchronization primitives:

```go
var mu sync.Mutex
var balance int

func Deposit(amount int) {
    mu.Lock()
    balance += amount
    mu.Unlock()
}
```

Multiple threads access the same data. Correctness depends on getting every lock/unlock right.

### When to Use Actors

**Actors shine when:**
- Each entity has its own lifecycle and state (user sessions, game entities, IoT devices)
- You need fault isolation — one actor crashing shouldn't affect others
- The system is distributed across multiple machines (messages serialize naturally to network)
- You want to avoid reasoning about lock ordering and deadlocks

**Real examples**: Erlang/OTP telecom systems (99.9999% uptime), Akka for JVM microservices, Orleans for game backends (Halo used it).

### When to Use Shared State

**Shared state wins when:**
- You need **low-latency** access to shared data (actors add message-passing overhead)
- The shared state is simple (a counter, a cache) and a single mutex/atomic suffices
- You need to read shared data frequently from many threads without copying
- You're doing fine-grained parallelism (matrix multiplication, image processing)

### Key Tradeoffs

| Aspect | Actor Model | Shared State |
|--------|-------------|--------------|
| Reasoning | Simple — no shared state to corrupt | Complex — must reason about interleavings |
| Performance | Message-passing overhead, copying data | Lower overhead, direct memory access |
| Failure handling | Supervisor hierarchies, restart policies | One thread crash can corrupt shared state |
| Distributed | Natural — messages go over network | Hard — need distributed locking |
| Debugging | Trace message flows | Reproduce race conditions |

### Practical Guidance

Most applications benefit from a **hybrid**: use actors (or channels in Go) for coarse-grained component isolation, and shared state with mutexes/atomics for performance-critical shared data within a component.'''
    ),

    (
        "understand2_18",
        r'''What is event sourcing and how does it differ from CRUD?''',
        r'''## Event Sourcing vs CRUD

### Traditional CRUD

In CRUD (Create, Read, Update, Delete), you store the **current state** of an entity:

```
orders table:
| id  | status    | total  | updated_at |
|-----|-----------|--------|------------|
| 123 | shipped   | 99.50  | 2025-03-01 |
```

When the order ships, you UPDATE the row: `SET status = 'shipped'`. The previous state (`pending`) is **lost** unless you've built separate audit logging.

### Event Sourcing

In event sourcing, you store the **sequence of events** that happened, never modifying or deleting them:

```
events table:
| event_id | aggregate_id | event_type      | data                          | timestamp  |
|----------|-------------|-----------------|-------------------------------|------------|
| 1        | order-123   | OrderCreated    | {"items": [...], "total": 99.50} | 2025-02-28 |
| 2        | order-123   | PaymentReceived | {"amount": 99.50}             | 2025-02-28 |
| 3        | order-123   | OrderShipped    | {"tracking": "1Z999..."}      | 2025-03-01 |
```

To get the current state, you **replay** all events for that aggregate:

```python
def rebuild_order(events):
    order = {}
    for event in events:
        if event.type == "OrderCreated":
            order = {"status": "pending", **event.data}
        elif event.type == "PaymentReceived":
            order["status"] = "paid"
        elif event.type == "OrderShipped":
            order["status"] = "shipped"
            order["tracking"] = event.data["tracking"]
    return order
```

### What Event Sourcing Gives You

1. **Complete audit trail**: Every state change is recorded permanently. Critical for finance, healthcare, legal compliance.
2. **Temporal queries**: "What was the order status at 3pm yesterday?" Just replay events up to that timestamp.
3. **Event replay**: Rebuild projections, fix bugs by replaying with corrected logic, migrate to new schemas.
4. **Decoupled consumers**: Other services subscribe to events (order shipped → send email, update inventory, notify warehouse).

### What It Costs

1. **Complexity**: Querying current state requires replaying events or maintaining separate read models (CQRS pattern).
2. **Storage**: Events accumulate forever. A busy system generates millions of events per day.
3. **Schema evolution**: Old events may have different shapes. You need versioning and upcasting.
4. **Eventual consistency**: Read models update asynchronously from the event stream, so queries may lag behind writes.

### When to Use Each

**Use CRUD when**: Simple domains, mostly reading current state, no audit requirements, small team.

**Use event sourcing when**: Audit trails are mandatory, you need temporal queries, multiple systems react to state changes, or the domain naturally models events (banking transactions, user activity, logistics).

**Hybrid approach**: Most teams use CRUD for 90% of their system and event source only the domains where history and auditability matter.'''
    ),

    (
        "understand2_19",
        r'''How does the Language Server Protocol (LSP) work? I use VS Code and see "language server" mentioned everywhere.''',
        r'''<think>
LSP separates editor features (code completion, diagnostics, go-to-definition) from the editor itself. Before LSP, every editor-language pair needed a custom plugin. Now you write one language server and it works in any LSP-supporting editor. I should explain the architecture, the communication protocol, and give concrete examples of requests/responses.
</think>

## How LSP Works

The Language Server Protocol is a standardized communication protocol between a **code editor** (the client) and a **language-specific analysis engine** (the server). Before LSP, if you wanted Python support in 5 editors, you needed 5 separate plugins. With LSP, you write **one** Python language server that works in VS Code, Neovim, Emacs, Sublime, etc.

### Architecture

```
┌─────────────┐    JSON-RPC     ┌──────────────────┐
│   VS Code   │ ◄─────────────► │ rust-analyzer     │
│  (client)   │   over stdio    │ (language server) │
└─────────────┘                 └──────────────────┘
```

The editor and the language server are **separate processes**. They communicate over stdin/stdout (or TCP sockets) using JSON-RPC, a lightweight RPC protocol.

### Lifecycle

1. **Initialize**: Editor starts the language server process and sends an `initialize` request listing its capabilities (supports code actions? folding? semantic tokens?)
2. **Sync**: As you type, the editor sends `textDocument/didOpen`, `textDocument/didChange` notifications so the server has an up-to-date view of your files
3. **Features**: The editor sends requests when you trigger features; the server responds

### Example: Code Completion

When you type `user.` and the completion popup appears:

```json
// Editor → Server (request)
{
    "method": "textDocument/completion",
    "params": {
        "textDocument": {"uri": "file:///src/main.py"},
        "position": {"line": 10, "character": 5}
    }
}

// Server → Editor (response)
{
    "result": {
        "items": [
            {"label": "name", "kind": 5, "detail": "str"},
            {"label": "email", "kind": 5, "detail": "str"},
            {"label": "save", "kind": 2, "detail": "() -> None"}
        ]
    }
}
```

### Key LSP Features

| Feature | LSP Method | What It Does |
|---------|-----------|--------------|
| Diagnostics (red squiggles) | `textDocument/publishDiagnostics` | Server pushes errors/warnings |
| Go to definition | `textDocument/definition` | Returns the location of a symbol's definition |
| Hover info | `textDocument/hover` | Returns type info and docs |
| Find references | `textDocument/references` | Returns all locations where a symbol is used |
| Rename | `textDocument/rename` | Returns edits to rename a symbol everywhere |
| Code actions | `textDocument/codeAction` | "Quick fix" suggestions (auto-import, extract function) |

### Why This Matters

Without LSP: M editors × N languages = M×N plugins to maintain.
With LSP: M editors + N language servers = M+N implementations.

The rust-analyzer team builds one server, and it works everywhere. The VS Code team builds one LSP client, and it supports every language.

### How the Server Stays Fast

Language servers typically maintain an **incremental index** of your codebase. When you edit a file, they re-analyze only the changed file and its dependents. Rust-analyzer, for example, uses a salsa-based incremental computation framework that caches intermediate analysis results.'''
    ),

    (
        "understand2_20",
        r'''What are the tradeoffs of microservices vs monolith? When should a startup choose one over the other?''',
        r'''## Microservices vs Monolith: Practical Tradeoffs

### Monolith

A monolith is a single deployable unit containing all your application's code:

```
my-app/
├── users/
├── orders/
├── payments/
├── notifications/
└── main.py          # one process, one database
```

**Advantages:**
- **Simple to develop**: One repo, one deployment, one debugging session. `grep` finds anything.
- **Simple to deploy**: Build one artifact, deploy to one server.
- **No network overhead**: Function calls between modules are nanoseconds, not milliseconds.
- **Transactions are easy**: One database, real ACID transactions across all your data.
- **Refactoring is easy**: Rename a function and your IDE updates all callers.

**Disadvantages:**
- **Scaling is all-or-nothing**: If payments is CPU-heavy, you scale the entire app.
- **Deployment coupling**: A bug in notifications blocks deploying an orders fix.
- **Technology lock-in**: Everything uses the same language, framework, and database.
- **Team coupling**: As the team grows past ~10 developers, merge conflicts and coordination overhead increase.

### Microservices

Each domain is a separate service with its own process, database, and deployment:

```
users-service/     → PostgreSQL
orders-service/    → PostgreSQL
payments-service/  → Stripe API + Redis
notifications/     → RabbitMQ consumer
```

**Advantages:**
- **Independent deployment**: Ship payments changes without touching orders.
- **Independent scaling**: Run 10 instances of payments, 2 of notifications.
- **Technology freedom**: Payments in Go, ML service in Python, frontend in Node.
- **Team autonomy**: Each team owns a service end-to-end.

**Disadvantages:**
- **Distributed systems complexity**: Network failures, message ordering, eventual consistency, distributed tracing.
- **Operational overhead**: You now need service discovery, load balancing, circuit breakers, centralized logging, container orchestration.
- **Cross-service transactions**: No more `BEGIN/COMMIT`. You need sagas or eventual consistency patterns.
- **Debugging is harder**: A bug might span 3 services. You need distributed tracing (Jaeger, Zipkin) to follow a request.
- **Data consistency**: Each service has its own database. Keeping them in sync requires event-driven architecture.

### When to Choose What

**Start with a monolith** if:
- You're a startup with < 10 engineers
- You're exploring product-market fit (requirements change weekly)
- You don't know your domain boundaries yet
- You can't afford the operational overhead of Kubernetes, service mesh, etc.

**Consider microservices** when:
- Your team grows past 15-20 and stepping on each other's toes
- Parts of the system have genuinely different scaling needs
- You need to deploy different components on different schedules
- Your domain boundaries are well-understood and stable

### The Middle Path: Modular Monolith

Structure your monolith as well-separated modules with clean interfaces, but deploy as one unit. When a module genuinely needs independence, extract it. This gives you most of the simplicity of a monolith with a clear path to selective extraction later.

Almost every successful microservices system (Netflix, Amazon, Uber) **started as a monolith** and extracted services as they grew.'''
    ),

    (
        "understand2_21",
        r'''How does a B-tree index work and why do databases use them instead of hash indexes for most things?''',
        r'''## B-Tree Indexes: How They Work

A B-tree is a self-balancing tree structure where each node contains multiple keys and pointers. In a database, the leaf nodes point to actual rows (or row IDs) on disk.

### Structure

For a B-tree of order 4 (each node holds up to 3 keys):

```
                    [30 | 60]                    ← root node
                   /    |    \
          [10 | 20]  [40 | 50]  [70 | 80 | 90]  ← internal nodes
          /  |  \    /  |  \    /  |  \    \
        [rows] [rows] [rows] [rows] ...          ← leaf nodes → disk pages
```

**Key property**: Leaf nodes are linked as a **doubly-linked list**, so sequential traversal is efficient.

### How a Lookup Works

To find `customer_id = 50`:

1. Start at root: 50 > 30, 50 < 60 → follow middle pointer
2. At `[40 | 50]`: 50 matches → follow pointer to leaf
3. Leaf contains a pointer to the disk page with that row

**Depth**: A B-tree with 10 million rows and order 200 has a depth of roughly 3-4. That means any lookup touches **3-4 disk pages** — compared to scanning all 10 million rows.

### Why B-Trees Beat Hash Indexes

Hash indexes give O(1) exact lookups — seemingly faster. But databases need much more than exact-match:

| Operation | B-Tree | Hash Index |
|-----------|--------|------------|
| Exact match: `WHERE id = 5` | O(log n) — 3-4 disk reads | O(1) — 1-2 disk reads |
| Range: `WHERE price > 10 AND price < 50` | Efficient — walk the leaf list | **Impossible** — must full scan |
| Sorting: `ORDER BY created_at` | Free — already ordered | **Impossible** — hash has no order |
| Prefix: `WHERE name LIKE 'Jo%'` | Efficient — B-tree range scan | **Impossible** |
| Min/Max: `SELECT MIN(price)` | O(log n) — leftmost/rightmost leaf | Full scan |

Since most real queries involve ranges, sorting, or ordering, B-trees handle **95% of query patterns** while hash indexes only handle exact-match.

### Why Not Binary Trees?

Binary trees have depth O(log₂ n) — for 10M rows, that's ~23 levels, meaning 23 disk I/O operations. B-trees have high fan-out (100-500 children per node), so depth is O(log₂₀₀ n) ≈ 3-4 levels. Fewer levels = fewer disk reads, which dominates performance for on-disk data.

### B-Tree Node Size = Disk Page

Database B-tree nodes are sized to match the disk page (typically 4-16KB). This means each node read is exactly one disk I/O, and the OS can cache frequently-accessed upper nodes in memory. In practice, the root and first level are always cached, so a lookup requires only 1-2 actual disk reads.

### When Hash Indexes Make Sense

Use hash indexes when you **only** need exact-match lookups on a high-cardinality column (like a UUID primary key) and never range scan or sort by it. PostgreSQL supports hash indexes, but most DBAs still default to B-tree because the flexibility is worth the marginal lookup overhead.'''
    ),

    (
        "understand2_22",
        r'''Explain the CAP theorem with practical examples. I've heard "you can only pick 2 out of 3" but that seems too simplistic.''',
        r'''<think>
The user already suspects the "pick 2 of 3" framing is oversimplified — and they're right. The real insight is that during a network partition (which will happen), you must choose between consistency and availability. No partition = you get both. I should give concrete system examples.
</think>

## The CAP Theorem: What It Actually Says

The "pick 2 of 3" framing is misleading. Here's what CAP actually states:

**During a network partition, a distributed system must choose between consistency and availability.**

The three properties:
- **Consistency (C)**: Every read receives the most recent write (all nodes see the same data at the same time)
- **Availability (A)**: Every request receives a response (no timeouts or errors)
- **Partition tolerance (P)**: The system continues operating despite network splits between nodes

### Why "Pick 2" Is Wrong

You don't get to "drop" partition tolerance. In any real distributed system, network partitions **will happen** (switch failures, datacenter splits, cloud provider issues). So P is mandatory. The real choice is:

**During a partition, do you sacrifice consistency or availability?**

### CP System Example: Bank Account

Imagine a bank balance stored on two nodes:

```
Node A: balance = $1000    |  PARTITION  |    Node B: balance = $1000
                           |  (can't     |
User tries to withdraw $800|  communicate)|   User tries to withdraw $800
```

**CP choice**: Node A processes the withdrawal but blocks Node B's withdrawal until the partition heals and they can synchronize. Node B returns an error: "Service temporarily unavailable."

**Result**: Consistent (no overdraft), but unavailable on Node B.

**Real systems**: Google Spanner, etcd, ZooKeeper, any system where correctness > uptime.

### AP System Example: Social Media

Imagine a "like count" stored on two nodes:

```
Node A: likes = 500       |  PARTITION  |    Node B: likes = 500
                          |             |
User likes post (+1)      |             |   User likes post (+1)
Node A: likes = 501       |             |   Node B: likes = 501
                          |  HEALS     |
          Both nodes: likes = 502 (merge)
```

**AP choice**: Both nodes accept writes independently. During the partition, Node A says 501 and Node B says 501 (inconsistent). After healing, they merge to 502.

**Result**: Always available, but temporarily inconsistent.

**Real systems**: DynamoDB, Cassandra, DNS, CDN caches.

### The Normal Case (No Partition)

When the network is healthy, you get **both** consistency and availability. CAP only forces a tradeoff during partitions. Most systems spend 99.99% of their time not partitioned.

### Practical Decision Framework

Ask yourself: **What happens if two nodes disagree?**

- "Show an error" → CP (banks, inventory, distributed locks)
- "Show stale data and reconcile later" → AP (social media, shopping carts, analytics)
- "It depends on the operation" → Use different strategies per feature

### Beyond CAP: PACELC

The PACELC extension adds: even without a partition, there's a latency-consistency tradeoff. Strong consistency requires coordination (round trips between nodes), which adds latency. Eventual consistency can respond from the nearest replica immediately.

```
If Partition → choose Availability or Consistency
Else         → choose Latency or Consistency
```

DynamoDB is PA/EL (available during partition, low latency normally). Spanner is PC/EC (consistent always, pays the latency cost).'''
    ),

    (
        "understand2_23",
        r'''What is backpressure in streaming systems and how do you handle it?''',
        r'''## Backpressure in Streaming Systems

Backpressure is a flow control mechanism where a **slow consumer signals a fast producer to slow down**. Without it, the producer overwhelms the consumer, causing memory exhaustion, dropped messages, or cascading failures.

### The Problem

Imagine a data pipeline:

```
[Kafka] → 100K msg/s → [Processor] → 10K msg/s → [Database]
                              ↑
                     Processes at 50K msg/s
```

The processor can handle 50K msg/s, but the database can only absorb 10K msg/s. Without backpressure, the processor's output buffer grows unbounded:

```
Time 0:   buffer = 0 messages
Time 1s:  buffer = 40,000 messages (50K produced - 10K consumed)
Time 10s: buffer = 400,000 messages
Time 60s: OutOfMemoryError
```

### Backpressure Strategies

**1. Block the producer (synchronous backpressure)**

```python
# Bounded queue — producer blocks when full
import queue

buffer = queue.Queue(maxsize=1000)

def producer():
    for msg in kafka_stream:
        buffer.put(msg)  # blocks when queue is full

def consumer():
    while True:
        msg = buffer.get()
        db.insert(msg)
```

The producer can't outrun the consumer because `put()` blocks. Simple, but the producer is idle while waiting.

**2. Drop messages (load shedding)**

```python
def producer():
    for msg in kafka_stream:
        try:
            buffer.put_nowait(msg)
        except queue.Full:
            metrics.increment("dropped_messages")
            # newest or oldest message dropped
```

Acceptable when data is replaceable (metrics, telemetry, live video frames). Not acceptable for financial transactions.

**3. Reactive Streams / Pull-based**

Instead of the producer pushing data, the consumer **requests** data when ready:

```
Consumer → "I can handle 100 more items" → Producer
Producer → sends exactly 100 items → Consumer
Consumer → processes them
Consumer → "I can handle 100 more" → Producer
```

This is how Reactive Streams (Java), RxJS, and Akka Streams work. The consumer controls the flow rate explicitly.

**4. Rate limiting**

```python
import time

def producer():
    rate_limit = 10_000  # match DB throughput
    interval = 1.0 / rate_limit
    for msg in kafka_stream:
        buffer.put(msg)
        time.sleep(interval)
```

Crude but effective. Use token bucket or leaky bucket algorithms for production.

**5. Dynamic scaling**

Spin up more consumer instances when the buffer grows:
```
if buffer_size > threshold:
    scale_up_consumers()
if buffer_size < low_watermark:
    scale_down_consumers()
```

Kubernetes HPA (Horizontal Pod Autoscaler) can do this based on custom metrics.

### Real-World Examples

| System | Backpressure Mechanism |
|--------|----------------------|
| TCP | Receive window — receiver advertises how much data it can accept |
| Kafka | Consumer pulls at its own pace; producer doesn't know consumer speed |
| Node.js Streams | `pipe()` automatically pauses readable when writable's buffer is full |
| gRPC | Flow control frames limit how much data can be in flight |

### Key Principle

Every unbounded buffer is a crash waiting to happen. Whenever a fast component feeds a slow one, you need explicit backpressure — either block, drop, pull, or scale.'''
    ),

    # ===================== TEACH ME THIS CONCEPT (7 pairs) =====================

    (
        "understand2_24",
        r'''What are algebraic data types and why do Rust and Haskell use them?''',
        r'''<think>
Algebraic data types (ADTs) are sum types (enums/tagged unions) and product types (structs/tuples). The "algebraic" comes from the fact that you can reason about the number of possible values: products multiply, sums add. Rust's enum is the prime example of a sum type. The key benefit is exhaustive pattern matching — the compiler ensures you handle all cases.
</think>

## Algebraic Data Types (ADTs)

Algebraic data types are types built from two operations: **products** (AND) and **sums** (OR). The name "algebraic" comes from the fact that you can count possible values using arithmetic.

### Product Types (AND)

A product type combines multiple values — you need **all** of them. The number of possible values is the **product** of the individual types.

```rust
struct Point {
    x: f64,  // ~2^64 values
    y: f64,  // ~2^64 values
}
// Total possible Points: 2^64 × 2^64 = 2^128
```

Structs, tuples, and records are product types. Most languages have these.

### Sum Types (OR)

A sum type is one of several variants — you have **exactly one** at a time. The number of possible values is the **sum** of the variants.

```rust
enum Shape {
    Circle(f64),           // radius — 2^64 values
    Rectangle(f64, f64),   // width, height — 2^128 values
    Triangle(f64, f64, f64), // three sides — 2^192 values
}
// Total possible Shapes: 2^64 + 2^128 + 2^192
```

This is the powerful part. A `Shape` is a `Circle` **or** a `Rectangle` **or** a `Triangle` — never two at once, never something else.

### Why This Matters: Exhaustive Matching

The compiler **forces** you to handle every variant:

```rust
fn area(shape: &Shape) -> f64 {
    match shape {
        Shape::Circle(r) => std::f64::consts::PI * r * r,
        Shape::Rectangle(w, h) => w * h,
        // compile error: non-exhaustive pattern
        // missing: Shape::Triangle(_, _, _)
    }
}
```

If you add a new variant later, the compiler finds **every** match statement that needs updating. This makes refactoring safe — you can't forget a case.

### Modeling Impossible States as Unrepresentable

Without sum types (e.g., in Java or Python), you use nullable fields or status flags:

```python
class ApiResponse:
    def __init__(self):
        self.data = None    # set if success
        self.error = None   # set if failure
        self.status = ""    # "ok" or "error"
```

Nothing prevents `data` and `error` from both being set, or both being `None`. Invalid states are **representable**.

With sum types:

```rust
enum ApiResponse<T> {
    Ok(T),        // has data, no error — guaranteed
    Err(String),  // has error, no data — guaranteed
}
```

It's **impossible** to have both data and error, or neither. The type system eliminates an entire class of bugs.

### Languages With Sum Types

- **Rust**: `enum` (most practical, widely used)
- **Haskell**: Algebraic data types (the OG)
- **OCaml/F#**: Discriminated unions
- **Swift**: `enum` with associated values
- **TypeScript**: Tagged unions (less enforced, but the pattern works)
- **Java/C#**: Sealed interfaces/classes (recent, verbose)

### The Missing Piece in Most Languages

Python, Java (pre-17), Go, and C don't have proper sum types. The workaround is class hierarchies, sentinel values, or convention — all of which lack compiler-enforced exhaustiveness.'''
    ),

    (
        "understand2_25",
        r'''Explain dependency injection without a framework. Every tutorial I find uses Spring or Dagger and I still don't understand the core idea.''',
        r'''## Dependency Injection in Plain Code

Dependency injection (DI) is absurdly simple at its core: **pass dependencies in instead of creating them inside the class.**

### Without DI (Hard-Coded Dependencies)

```python
class OrderService:
    def __init__(self):
        self.db = PostgresDatabase("localhost", 5432)  # hard-coded
        self.mailer = SmtpMailer("smtp.gmail.com")      # hard-coded

    def place_order(self, order):
        self.db.save(order)
        self.mailer.send(order.customer_email, "Order confirmed")
```

Problems:
- **Can't test**: Tests hit a real database and send real emails
- **Can't swap**: Changing from Postgres to MySQL means editing `OrderService`
- **Hidden dependencies**: You can't see what `OrderService` needs without reading its code

### With DI (Dependencies Passed In)

```python
class OrderService:
    def __init__(self, db, mailer):  # dependencies are parameters
        self.db = db
        self.mailer = mailer

    def place_order(self, order):
        self.db.save(order)
        self.mailer.send(order.customer_email, "Order confirmed")
```

That's it. That's dependency injection. You "inject" the dependencies from the outside instead of creating them inside.

### Why This Is Powerful

**Testing with fakes:**
```python
class FakeDatabase:
    def __init__(self):
        self.saved = []
    def save(self, item):
        self.saved.append(item)

class FakeMailer:
    def __init__(self):
        self.sent = []
    def send(self, to, body):
        self.sent.append((to, body))

def test_place_order():
    db = FakeDatabase()
    mailer = FakeMailer()
    service = OrderService(db, mailer)

    service.place_order(Order(customer_email="a@b.com"))

    assert len(db.saved) == 1
    assert mailer.sent[0][0] == "a@b.com"
```

No real database. No real emails. The test runs in milliseconds.

**Swapping implementations:**
```python
# Production
service = OrderService(PostgresDatabase(...), SmtpMailer(...))

# Staging
service = OrderService(PostgresDatabase(...), LoggingMailer(...))

# Testing
service = OrderService(FakeDatabase(), FakeMailer())
```

Same `OrderService` code, different behavior based on what you inject.

### The Wiring Code

Someone has to create the dependencies and pass them in. In a small app, this is just your `main()`:

```python
def main():
    db = PostgresDatabase("localhost", 5432)
    mailer = SmtpMailer("smtp.gmail.com")
    service = OrderService(db, mailer)
    app = WebApp(service)
    app.run()
```

This is called the **composition root** — the one place where you wire everything together. Frameworks like Spring automate this wiring with annotations, but the concept is identical: construct objects at the top, pass them down.

### When It's Overkill

DI is unnecessary for simple utilities, pure functions, or value objects. If a dependency is a core part of the class (e.g., `Vec` using a heap allocator), injecting it adds complexity without benefit. Use DI for **external services** (databases, APIs, file systems) and **things you'd want to fake in tests**.'''
    ),

    (
        "understand2_26",
        r'''What is the difference between concurrency and parallelism? I keep seeing contradictory explanations.''',
        r'''<think>
Rob Pike's formulation is the clearest: "Concurrency is about dealing with lots of things at once. Parallelism is about doing lots of things at once." Concurrency is about structure (composing independently executing processes), parallelism is about execution (running simultaneously on multiple cores). A concurrent program may or may not be parallel.
</think>

## Concurrency vs Parallelism

The clearest distinction (from Rob Pike):

- **Concurrency**: Dealing with multiple things at once (structure)
- **Parallelism**: Doing multiple things at once (execution)

### Concrete Analogy

**One cook, two burners** (concurrent, not parallel):
The cook starts pasta boiling on burner 1, then chops vegetables. While the pasta cooks, they sauté vegetables on burner 2. One person, switching between tasks. Both dishes make progress, but only one hand is chopping at any moment.

**Two cooks, two burners** (concurrent AND parallel):
Each cook works on their own dish simultaneously. Two tasks actually executing at the same instant.

### In Code

**Concurrent, single core** (Python with asyncio):
```python
async def main():
    task1 = asyncio.create_task(fetch_url("https://api.a.com"))
    task2 = asyncio.create_task(fetch_url("https://api.b.com"))
    a, b = await asyncio.gather(task1, task2)
```

Both HTTP requests are "in flight" simultaneously — while waiting for A's response, Python sends B's request. But there's **one thread** doing the work. When A's response arrives, it processes it; then B's. The I/O overlaps, but the CPU work is sequential.

**Parallel, multi-core** (Rust with rayon):
```rust
use rayon::prelude::*;

let results: Vec<_> = data
    .par_iter()
    .map(|item| expensive_computation(item))
    .collect();
```

This splits the data across CPU cores. If you have 8 cores, 8 computations happen **at the same physical instant**. This is true parallelism.

### The Key Distinction

| | Concurrency | Parallelism |
|--|-------------|-------------|
| About | Structure — managing multiple tasks | Execution — running simultaneously |
| Requires | Task switching mechanism | Multiple cores/processors |
| Example | Single-threaded web server handling 10K connections | Matrix multiplication across 8 cores |
| Speedup from | Overlapping I/O waits | Dividing CPU work |

### Why It Matters Practically

**I/O-bound work** benefits from concurrency even on a single core. A web server waiting for database responses can handle other requests during the wait. Adding cores doesn't help much — the bottleneck is I/O latency, not CPU.

**CPU-bound work** benefits from parallelism. Compressing 100 files on one core is 100x slower than on 100 cores. Concurrency alone doesn't help — there's no waiting to overlap.

### Language Approaches

- **Go**: Goroutines are concurrent. The runtime schedules them across cores (parallel when beneficial).
- **Python**: `asyncio` is concurrent but not parallel (GIL). `multiprocessing` is parallel.
- **Rust**: `async` is concurrent. `rayon`/threads are parallel. You choose explicitly.
- **JavaScript**: `async/await` is concurrent. `Worker` threads are parallel.

**A concurrent program CAN be parallel** (if run on multiple cores), but a parallel program is always concurrent (by definition, it manages multiple simultaneous tasks).'''
    ),

    (
        "understand2_27",
        r'''How do bloom filters work and when should I use one?''',
        r'''## Bloom Filters

A bloom filter is a space-efficient probabilistic data structure that answers the question: **"Is this element in the set?"** with two possible answers:

- **"Definitely not in the set"** — always correct
- **"Probably in the set"** — might be wrong (false positive)

It **never** produces false negatives. If it says "no," the element is guaranteed absent.

### How It Works

A bloom filter is a **bit array** of size `m`, initially all zeros, with `k` independent hash functions.

**Adding an element:**
```
Hash functions: h1, h2, h3
Bit array (m=10): [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

Add "hello":
  h1("hello") % 10 = 2
  h2("hello") % 10 = 5
  h3("hello") % 10 = 9

Bit array:           [0, 0, 1, 0, 0, 1, 0, 0, 0, 1]
                            ^           ^              ^
```

**Checking membership:**
```
Check "world":
  h1("world") % 10 = 1
  h2("world") % 10 = 5  ← bit is 1 (set by "hello")
  h3("world") % 10 = 7

Bits at positions 1, 5, 7: [0, 1, 0]
Not all bits are 1 → "Definitely NOT in the set" ✓

Check "maybe":
  h1("maybe") % 10 = 2  ← bit is 1
  h2("maybe") % 10 = 5  ← bit is 1
  h3("maybe") % 10 = 9  ← bit is 1

All bits are 1 → "Probably in the set" (could be false positive!)
```

"maybe" was never added, but its hash positions happen to overlap with bits set by other elements. This is a **false positive**.

### Space Efficiency

To store 1 million elements with a 1% false positive rate:
- **Bloom filter**: ~1.2 MB (about 10 bits per element)
- **HashSet**: ~40-80 MB (storing actual elements + hash table overhead)

That's a **30-60x** space reduction.

### When to Use Bloom Filters

**Web crawler**: Before crawling a URL, check the bloom filter. If "definitely not seen," crawl it. If "probably seen," skip it (an occasional false positive means you skip a URL you haven't actually visited — acceptable).

**Database queries**: Check a bloom filter before hitting disk. If the key is "definitely not" in the database file, skip the expensive disk read. LevelDB, RocksDB, and Cassandra all use this.

**Network security**: Check if a URL is in a malware blocklist. A 10-million-entry blocklist fits in ~12MB with 1% false positive rate.

**Cache checking**: Before querying a remote cache, check a local bloom filter. If the key is "definitely not" cached, go straight to the database (avoids a cache miss round-trip).

### When NOT to Use Them

- When you need **exact** answers (no false positives allowed)
- When you need to **delete** elements (standard bloom filters don't support deletion — use a counting bloom filter instead)
- When the set is small enough that a HashSet fits in memory
- When false positives are expensive (e.g., skipping a critical security check)

### Implementation

```python
import mmh3  # MurmurHash3
from bitarray import bitarray

class BloomFilter:
    def __init__(self, size: int, num_hashes: int):
        self.size = size
        self.num_hashes = num_hashes
        self.bits = bitarray(size)
        self.bits.setall(0)

    def add(self, item: str):
        for i in range(self.num_hashes):
            idx = mmh3.hash(item, i) % self.size
            self.bits[idx] = 1

    def might_contain(self, item: str) -> bool:
        return all(
            self.bits[mmh3.hash(item, i) % self.size]
            for i in range(self.num_hashes)
        )
```'''
    ),

    (
        "understand2_28",
        r'''Explain eventual consistency vs strong consistency. When is eventual consistency actually okay?''',
        r'''<think>
Strong consistency: after a write completes, all subsequent reads see the new value. Eventual consistency: after a write, reads may return stale data for a while, but will eventually converge. The key is understanding that "eventually" usually means milliseconds, and many use cases genuinely don't need immediate consistency.
</think>

## Strong vs Eventual Consistency

### Strong Consistency

After a write completes, **every** subsequent read from **any** node returns the updated value. The system behaves as if there's one copy of the data.

```
Client writes: balance = $500
                ↓
Write acknowledged
                ↓
Client reads from ANY node: balance = $500  ✓ guaranteed
```

**How it works**: The write doesn't return success until a majority of nodes (or all nodes) confirm they have the new value. This requires coordination (consensus protocols like Raft, Paxos).

**Cost**: Higher latency (must wait for confirmation from multiple nodes) and lower availability during partitions.

### Eventual Consistency

After a write, replicas may temporarily have different values. Given enough time without new writes, all replicas **converge** to the same value.

```
Client writes to Node A: balance = $500
Write acknowledged immediately
                ↓
Node A: $500    Node B: $1000 (stale)    Node C: $1000 (stale)
  ... replication propagates (usually milliseconds) ...
Node A: $500    Node B: $500             Node C: $500  ✓ converged
```

**Cost**: Reads may return stale data. Concurrent writes may conflict and require resolution.

### When Eventual Consistency Is Actually Fine

**Social media feeds**: If a new post takes 2 seconds to appear for all followers, nobody notices or cares. Strong consistency would add latency for zero user benefit.

**Shopping cart**: Amazon's cart is eventually consistent (the famous Dynamo paper). If you add an item and briefly see it missing on another device, you just add it again — and the system merges both additions. Worse case: duplicate item in cart (easily fixed at checkout).

**Analytics and counters**: A dashboard showing "~1.2M page views" that's 30 seconds behind is perfectly useful. Real-time precision is unnecessary.

**CDN/Caches**: When you update a webpage, CDN caches expire over minutes. Users see slightly stale content temporarily. This is eventual consistency by design.

**DNS**: Updating a DNS record takes hours to propagate globally. The entire internet runs on eventual consistency for name resolution.

### When You Need Strong Consistency

**Bank transfers**: Withdrawing $500 must be immediately visible everywhere. If two ATMs both see $1000 balance simultaneously, they might both allow a $800 withdrawal → overdraft.

**Inventory for limited items**: If 1 item remains and two users buy simultaneously, one must get an error immediately. Eventually consistent inventory → overselling.

**Distributed locks**: If Node A acquires a lock and Node B doesn't know about it yet, they both proceed — defeating the lock's purpose.

**Unique constraints**: Username registration, ticket booking, anything where duplicates are unacceptable.

### The Practical Spectrum

Consistency isn't binary. Real systems offer tunable levels:

| Level | Guarantee | Example |
|-------|-----------|---------|
| Strong | Read always returns latest write | Google Spanner |
| Bounded staleness | Read is at most N seconds behind | Cosmos DB |
| Session | Your own reads see your own writes | Most web apps with sticky sessions |
| Eventual | Reads converge eventually | DynamoDB (default), Cassandra |

**Session consistency** is the sweet spot for many applications. The user who made a change sees it immediately. Other users may see it with a slight delay. This matches user expectations: "I changed my profile name, I should see it right away, but it's fine if my friend sees the old name for a few seconds."'''
    ),

    (
        "understand2_29",
        r'''What is tail call optimization and which languages support it?''',
        r'''## Tail Call Optimization (TCO)

A **tail call** is a function call that is the **last operation** in a function — there's nothing left to do after the call returns.

```python
# Tail call — the recursive call IS the return value
def factorial(n, acc=1):
    if n <= 1:
        return acc
    return factorial(n - 1, n * acc)  # nothing happens after this call

# NOT a tail call — multiplication happens AFTER the recursive call
def factorial(n):
    if n <= 1:
        return 1
    return n * factorial(n - 1)  # must multiply n by the result
```

**Tail call optimization** is when the compiler/runtime recognizes a tail call and **reuses the current stack frame** instead of creating a new one. The recursive call becomes a jump (like a `goto`), converting recursion into a loop internally.

### Why It Matters

Without TCO, each recursive call adds a stack frame:

```
factorial(10000) → factorial(9999) → factorial(9998) → ...
                    10,000 stack frames
                    → Stack Overflow!
```

With TCO, the compiler transforms it to:

```
factorial(10000, 1):
  loop:
    if n <= 1: return acc
    acc = n * acc
    n = n - 1
    goto loop               // one stack frame, always
```

Same result, O(1) stack space instead of O(n).

### Language Support

| Language | TCO Support | Notes |
|----------|-------------|-------|
| **Scheme/Racket** | Required by spec | Must optimize all tail calls |
| **Haskell** | Yes (lazy evaluation) | Tail recursion is the natural idiom |
| **Erlang/Elixir** | Yes | Critical for actor loop: `receive → handle → recurse` |
| **Scala** | Opt-in (`@tailrec`) | Compiler verifies and optimizes, error if not tail-recursive |
| **Rust** | No (no guaranteed TCO) | LLVM may optimize it, but it's not guaranteed |
| **Go** | No | By design — clear stack traces are prioritized |
| **Python** | No | Guido explicitly rejected it — prefers explicit loops |
| **JavaScript** | Spec says yes (ES2015), only Safari implements it | V8/SpiderMonkey chose not to implement |
| **C/C++** | Compiler-dependent | GCC/Clang with `-O2` often optimize tail calls, but no guarantee |
| **Java** | No (JVM limitation) | Project Loom doesn't change this |

### The Accumulator Pattern

To make a function tail-recursive, move the "work after the call" into an **accumulator parameter**:

```elixir
# Not tail-recursive
def sum([]), do: 0
def sum([h | t]), do: h + sum(t)  # + happens after recursive call

# Tail-recursive with accumulator
def sum(list), do: sum(list, 0)
def sum([], acc), do: acc
def sum([h | t], acc), do: sum(t, acc + h)  # recursive call IS the return
```

### When to Care

- **Functional languages** (Haskell, Scheme, Elixir): TCO is essential — recursion is the primary looping mechanism
- **Python/JS/Java**: Just use a loop — the language doesn't optimize recursion, so a `while` loop is both clearer and stack-safe
- **Systems languages** (Rust, C): Don't rely on TCO unless you've verified the compiler output'''
    ),

    (
        "understand2_30",
        r'''How does a garbage collector decide what to collect? I know it "frees unused memory" but how does it know what's unused?''',
        r'''<think>
The core question: how does a GC determine liveness? Two main approaches: reference counting and tracing. Most modern GCs are tracing collectors using mark-and-sweep or generational approaches. I should explain reachability (the root set concept), mark-and-sweep, generational hypothesis, and briefly mention reference counting with its cycle problem.
</think>

## How Garbage Collectors Determine Liveness

The fundamental question a GC answers: **"Can any part of the running program ever access this object again?"** If not, the memory is safe to reclaim.

### Approach 1: Tracing (Most Common)

Used by Java, Go, C#, Python (as a cycle collector), JavaScript.

The core idea is **reachability from roots**:

**Root set** — things that are definitely alive:
- Local variables on all thread stacks
- Global/static variables
- CPU registers

Starting from the roots, the GC **traces** every reference, marking objects as reachable:

```
Roots:         [main.users] → [User A] → [Address X]
                                       → [Address Y]
               [main.cache] → [User B] → [Address Z]

Unreachable:   [User C] → [Address W]   ← no root reaches these
                                          ← eligible for collection
```

**Mark-and-Sweep** (simplest tracing algorithm):
1. **Mark phase**: Starting from roots, follow all references, marking each reached object
2. **Sweep phase**: Walk all allocated memory, free anything not marked

```
Before:  [A✓] [B✓] [C✗] [D✓] [E✗] [F✓]
                     ↑           ↑
Sweep:          freed here   freed here
After:   [A] [B] [free] [D] [free] [F]
```

### Approach 2: Reference Counting

Used by Python (primary), Swift, Rust's `Rc<T>`, Objective-C (ARC).

Each object has a counter tracking how many references point to it. When the count drops to zero, free immediately.

```python
a = SomeObject()  # refcount = 1
b = a              # refcount = 2
del a              # refcount = 1
del b              # refcount = 0 → freed immediately
```

**Problem: cycles.** If A references B and B references A, both have refcount 1 even when no external reference exists — they leak forever.

```python
a = []
b = []
a.append(b)  # a→b, b refcount = 1
b.append(a)  # b→a, a refcount = 1
del a, b     # a refcount = 1 (from b), b refcount = 1 (from a)
             # neither reaches 0 — leaked!
```

Python fixes this with a **supplemental tracing collector** that detects cycles periodically.

### The Generational Hypothesis

Most objects die young. A temporary string in a function is allocated, used, and abandoned within microseconds. An application's config object lives forever.

Modern GCs exploit this with **generational collection**:

- **Young generation** (nursery): Small, collected frequently. Most objects die here. Collection is fast because the space is small.
- **Old generation**: Larger, collected rarely. Objects that survive several young collections get promoted here.

```
Allocation → [Young Gen] → survives 3 collections → [Old Gen]
                  ↓                                      ↓
             Collected often (ms)              Collected rarely (100ms+)
```

Java's G1, Go's concurrent GC, and .NET's GC all use generational strategies.

### Summary

| Strategy | Determines Liveness By | Strength | Weakness |
|----------|----------------------|----------|----------|
| Tracing (mark-sweep) | Reachability from roots | Handles cycles | Stop-the-world pauses |
| Reference counting | Count of incoming references | Immediate, predictable | Can't detect cycles alone |
| Generational | Tracing, optimized by age | Fast for common case | Promotion can be expensive |
| Concurrent | Tracing while app runs | Low pause times | Higher CPU overhead |'''
    ),
]
