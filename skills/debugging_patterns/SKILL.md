# Systematic Debugging Patterns

## Step 1: Reproduce and Isolate
- Get the smallest input that triggers the bug
- Confirm: is it deterministic or intermittent (race condition, timing)?
- Check: does it fail in tests, REPL, or only production? Environment-specific = config/dependency issue

## Step 2: Classify the Bug

| Category | Symptoms | First Check |
|----------|----------|-------------|
| **Off-by-one** | Wrong count, missing first/last element, index out of range | Loop bounds, `<` vs `<=`, 0-based vs 1-based |
| **Null/None** | AttributeError, NullPointerException, segfault | Uninitialized vars, missing dict keys, optional returns |
| **Type mismatch** | Wrong output type, silent coercion | String "1" vs int 1, float division, JSON parse types |
| **Race condition** | Intermittent failures, works in debugger | Shared mutable state, missing locks, check-then-act |
| **Resource leak** | Slow degradation, OOM, fd exhaustion | Unclosed files/connections, missing `finally`/`defer`/RAII |
| **Logic error** | Wrong result, correct types | Operator precedence, boolean logic (De Morgan), edge cases |
| **State mutation** | Works first call, fails on second | Mutable default args (Python), global state, aliased refs |
| **Encoding** | Garbled text, mojibake, length mismatch | UTF-8 vs Latin-1, bytes vs str, BOM markers |

## Step 3: Diagnosis Techniques

### Binary search the problem
```
# Git bisect — find which commit introduced the bug
git bisect start
git bisect bad          # Current commit is broken
git bisect good abc123  # This old commit was fine
# Git tests each midpoint. O(log n) commits to check.
```

### Print debugging (fast, universal)
```python
# Python: use repr() to see types and escaping
print(f"DEBUG: x={x!r}, type={type(x)}, len={len(x)}")

# Add assertions at boundaries
assert isinstance(result, list), f"Expected list, got {type(result)}"
assert len(result) > 0, "Empty result — upstream returned nothing"
```

```go
// Go: use %#v for full struct representation
log.Printf("DEBUG: obj=%#v\n", obj)
```

```rust
// Rust: use {:?} or {:#?} for Debug trait
eprintln!("DEBUG: val={:?}", val);
// dbg! macro prints expression + value + file:line
dbg!(&my_struct);
```

### Rubber duck checklist
1. What EXACTLY is the input? (print it)
2. What EXACTLY is the output? (print it)
3. What did I EXPECT the output to be?
4. At which step does actual diverge from expected?

## Step 4: Common Anti-patterns

### Python
```python
# BUG: Mutable default argument (shared between calls!)
def append_to(item, lst=[]):  # lst is created ONCE
    lst.append(item)
    return lst
# FIX: Use None sentinel
def append_to(item, lst=None):
    if lst is None:
        lst = []
    lst.append(item)
    return lst

# BUG: Late binding closures
funcs = [lambda: i for i in range(3)]
# All return 2! Lambda captures variable `i`, not its value
# FIX: Default argument capture
funcs = [lambda i=i: i for i in range(3)]
```

### JavaScript/TypeScript
```javascript
// BUG: == type coercion
0 == ""   // true!  Use === always
null == undefined  // true!

// BUG: Floating point
0.1 + 0.2 === 0.3  // false!
// FIX: Math.abs(a - b) < Number.EPSILON

// BUG: async forEach doesn't await
items.forEach(async (item) => { await process(item); });  // Fire-and-forget!
// FIX: for...of or Promise.all with map
for (const item of items) { await process(item); }
```

### Concurrency
```
# BUG: Check-then-act race
if not file.exists():     # Thread A checks
    file.create()         # Thread B creates between check and create → conflict
# FIX: Atomic operation or lock

# BUG: Deadlock from lock ordering
# Thread 1: lock(A) → lock(B)
# Thread 2: lock(B) → lock(A)
# FIX: Always acquire locks in consistent global order
```

## Step 5: Verify the Fix
- Does the original failing input now produce correct output?
- Do existing tests still pass? (no regression)
- Add a test for this specific bug (prevent recurrence)
- Check edge cases: empty input, single element, max size, negative values
