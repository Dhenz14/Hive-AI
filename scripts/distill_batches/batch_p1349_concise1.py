"""Intentionally concise training pairs: short, direct answers (2-5 lines) to teach brevity."""
PAIRS = [
    # -- 01-08: Python (concise) ---------------------------------------------------
    ("concise1_01", r'''How do I reverse a string in Python?''', r'''Use slicing with a step of -1:

```python
reversed_str = s[::-1]
```'''),

    ("concise1_02", r'''How do I check if a key exists in a Python dictionary?''', r'''Use the `in` operator:

```python
if "key" in my_dict:
    print(my_dict["key"])
```'''),

    ("concise1_03", r'''How do I merge two dictionaries in Python 3.9+?''', r'''Use the merge operator:

```python
merged = dict_a | dict_b
```

Values from `dict_b` override duplicates from `dict_a`.'''),

    ("concise1_04", r'''What's the difference between `is` and `==` in Python?''', r'''`==` checks if two objects have the **same value**. `is` checks if they are the **same object in memory** (identity). Use `==` for value comparison, `is` for `None` checks (`if x is None`).'''),

    ("concise1_05", r'''How do I flatten a list of lists in Python?''', r'''Use a list comprehension:

```python
flat = [item for sublist in nested for item in sublist]
```

For deeply nested structures, use `itertools.chain.from_iterable()` or recursion.'''),

    ("concise1_06", r'''How do I get the current timestamp in Python?''', r'''```python
import time
timestamp = time.time()          # float, seconds since epoch

from datetime import datetime
now = datetime.now()              # local datetime object
now_utc = datetime.utcnow()      # UTC datetime object
```'''),

    ("concise1_07", r'''How do I remove duplicates from a list while preserving order in Python?''', r'''```python
seen = set()
unique = [x for x in items if x not in seen and not seen.add(x)]
```

Or on Python 3.7+ where dicts preserve insertion order: `list(dict.fromkeys(items))`.'''),

    ("concise1_08", r'''How do I swap two variables in Python?''', r'''```python
a, b = b, a
```

No temporary variable needed — Python evaluates the right side as a tuple first, then unpacks.'''),

    # -- 09-14: JS/TS (concise) ----------------------------------------------------
    ("concise1_09", r'''What's the difference between `let` and `const` in JavaScript?''', r'''`let` allows reassignment, `const` does not. Both are block-scoped. Note that `const` only prevents reassignment of the binding — object properties and array elements can still be mutated.'''),

    ("concise1_10", r'''How do I check if a value is an array in JavaScript?''', r'''```javascript
Array.isArray(value)
```

Don't use `typeof` — it returns `"object"` for arrays.'''),

    ("concise1_11", r'''How do I remove an element from an array by index in JavaScript?''', r'''Use `splice`:

```javascript
arr.splice(index, 1);  // modifies in place, returns removed elements
```

For a new array without mutation: `arr.filter((_, i) => i !== index)`.'''),

    ("concise1_12", r'''What's the difference between `null` and `undefined` in JavaScript?''', r'''`undefined` means a variable was declared but not assigned a value. `null` is an intentional assignment meaning "no value." Use `null` when you want to explicitly clear something; `undefined` is what JS gives you by default.'''),

    ("concise1_13", r'''How do I convert a string to a number in TypeScript?''', r'''Several options:

```typescript
const n1 = Number("42");      // 42
const n2 = parseInt("42", 10); // 42 (always pass radix)
const n3 = +"42";              // 42 (unary plus)
```

`Number()` is usually preferred — it handles floats and rejects trailing non-numeric characters.'''),

    ("concise1_14", r'''How do I deep clone an object in JavaScript?''', r'''In modern runtimes:

```javascript
const clone = structuredClone(obj);
```

This handles nested objects, arrays, Maps, Sets, and circular references. Avoid `JSON.parse(JSON.stringify(obj))` — it drops `undefined`, functions, and `Date` objects.'''),

    # -- 15-18: Rust (concise) -----------------------------------------------------
    ("concise1_15", r'''How do I read a file to a string in Rust?''', r'''```rust
let contents = std::fs::read_to_string("path.txt")?;
```

This reads the entire file into a `String` and returns `io::Result<String>`.'''),

    ("concise1_16", r'''What's the difference between `String` and `&str` in Rust?''', r'''`String` is an owned, heap-allocated, growable string. `&str` is a borrowed reference to a string slice (could point into a `String`, a static literal, or any UTF-8 byte buffer). Use `&str` for function parameters, `String` when you need ownership.'''),

    ("concise1_17", r'''How do I convert between `String` and `&str` in Rust?''', r'''```rust
// &str → String
let owned: String = "hello".to_string();  // or String::from("hello")

// String → &str
let borrowed: &str = &owned;  // auto-deref coercion
```'''),

    ("concise1_18", r'''How do I handle Option unwrapping in Rust without panicking?''', r'''Use combinators or pattern matching instead of `.unwrap()`:

```rust
let val = some_option.unwrap_or(default);       // fallback value
let val = some_option.unwrap_or_else(|| compute()); // lazy fallback
let val = some_option?;                          // propagate None as early return
if let Some(v) = some_option { /* use v */ }
```'''),

    # -- 19-22: Go (concise) -------------------------------------------------------
    ("concise1_19", r'''How do I check if a map contains a key in Go?''', r'''Use the comma-ok idiom:

```go
val, ok := myMap[key]
if ok {
    // key exists, val is the value
}
```'''),

    ("concise1_20", r'''How do I concatenate strings efficiently in Go?''', r'''Use `strings.Builder` for multiple concatenations:

```go
var b strings.Builder
b.WriteString("hello")
b.WriteString(" world")
result := b.String()
```

Avoid repeated `+` in loops — it allocates a new string each time.'''),

    ("concise1_21", r'''What's the difference between a slice and an array in Go?''', r'''Arrays have a fixed size known at compile time (`[5]int`). Slices are dynamically-sized views backed by an array (`[]int`). Slices have a length and capacity, and grow automatically via `append`. Almost all Go code uses slices.'''),

    ("concise1_22", r'''How do I convert a string to an integer in Go?''', r'''```go
import "strconv"

n, err := strconv.Atoi("42")  // string → int
s := strconv.Itoa(42)          // int → string
```

For explicit bit-size control, use `strconv.ParseInt("42", 10, 64)`.'''),

    # -- 23-25: General (concise) --------------------------------------------------
    ("concise1_23", r'''What's the difference between a stack and a queue?''', r'''A **stack** is LIFO (last in, first out) — think of a stack of plates. A **queue** is FIFO (first in, first out) — think of a line at a store. Stacks use push/pop; queues use enqueue/dequeue.'''),

    ("concise1_24", r'''What does `O(log n)` mean in Big-O notation?''', r'''It means the algorithm's runtime grows proportional to the logarithm of the input size. Each step roughly halves the remaining work. Binary search is the classic example — doubling the input only adds one extra step.'''),

    ("concise1_25", r'''What's the difference between HTTP GET and POST?''', r'''**GET** requests data and should be idempotent — parameters go in the URL query string. **POST** submits data to be processed — parameters go in the request body. GET requests can be cached and bookmarked; POST requests cannot.'''),
]
