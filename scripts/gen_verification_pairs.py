#!/usr/bin/env python3
"""
scripts/gen_verification_pairs.py — Generate semi-formal code verification training pairs.

Creates training pairs where the model must verify code correctness using a structured
certificate format (Section 23 of improvement_notes.md). Each pair includes:
- A code snippet to verify (with or without bugs)
- A structured certificate: Claim → Premises → Code Trace → Conclusion

Output: appends to loras/training_data/v9_research_pairs.jsonl
"""

import json
from pathlib import Path

OUTPUT = Path(__file__).resolve().parent.parent / "loras" / "training_data" / "v9_research_pairs.jsonl"

PAIRS = [
    # -------------------------------------------------------------------------
    # 1. Python: Off-by-one in binary search (BUGGY)
    # -------------------------------------------------------------------------
    {
        "instruction": "Verify whether this binary search implementation is correct. Use structured reasoning with premises, code trace, and a formal conclusion.",
        "input": """```python
def binary_search(arr, target):
    lo, hi = 0, len(arr)
    while lo < hi:
        mid = (lo + hi) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1
```""",
        "output": """<think>
I need to verify this binary search. The standard contract is: given a sorted array, return the index of target or -1. Let me trace through the boundary conditions carefully.

The search space is [lo, hi) since hi starts at len(arr), but the else branch sets hi = mid - 1. This is a mixing of half-open and closed interval conventions — a classic source of bugs.
</think>

**Verification Certificate**

**Claim**: This binary search correctly finds `target` in a sorted array and returns its index, or -1 if absent.

**Premises**:
- P1: `lo` starts at 0, `hi` starts at `len(arr)` — this is a half-open interval `[0, n)`
- P2: The `while lo < hi` loop condition is compatible with half-open intervals
- P3: `mid = (lo + hi) // 2` is correct for half-open (no overflow for Python ints)
- P4: When `arr[mid] < target`, `lo = mid + 1` correctly narrows from the left
- P5: When `arr[mid] > target`, `hi = mid - 1` sets hi to `mid - 1`

**Code Trace** (arr = [1, 3, 5, 7, 9], target = 9):
- Iteration 1: lo=0, hi=5, mid=2, arr[2]=5 < 9 → lo=3
- Iteration 2: lo=3, hi=5, mid=4, arr[4]=9 == 9 → return 4 ✓

**Code Trace** (arr = [1, 3, 5, 7, 9], target = 7):
- Iteration 1: lo=0, hi=5, mid=2, arr[2]=5 < 7 → lo=3
- Iteration 2: lo=3, hi=5, mid=4, arr[4]=9 > 7 → hi=3 (mid-1=3)
- Iteration 3: lo=3, hi=3, loop exits → return -1 ✗ (7 IS in the array at index 3!)

**Conclusion**: **INVALID** — The code mixes half-open interval `[lo, hi)` (from `hi = len(arr)` and `while lo < hi`) with closed-interval narrowing (`hi = mid - 1`). When the target is at `mid - 1`, the search space skips it.

**Fix**: Either use `hi = mid` (half-open convention) or change initialization to `hi = len(arr) - 1` and loop condition to `while lo <= hi` (closed convention):

```python
# Option A: half-open [lo, hi)
def binary_search(arr, target):
    lo, hi = 0, len(arr)
    while lo < hi:
        mid = (lo + hi) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid  # NOT mid - 1
    return -1
```"""
    },

    # -------------------------------------------------------------------------
    # 2. Rust: Correct ownership transfer (CORRECT)
    # -------------------------------------------------------------------------
    {
        "instruction": "Verify whether this Rust function correctly handles ownership and returns the expected result. Provide a structured verification certificate.",
        "input": """```rust
fn longest(s1: &str, s2: &str) -> String {
    if s1.len() >= s2.len() {
        s1.to_string()
    } else {
        s2.to_string()
    }
}

fn main() {
    let a = String::from("hello");
    let b = String::from("hi");
    let result = longest(&a, &b);
    println!("{} and {} -> {}", a, b, result);
}
```""",
        "output": """<think>
Let me verify ownership semantics and lifetime correctness for this Rust code. The function takes two string slices and returns an owned String. I need to check that borrows don't conflict with the return value and that all values are valid when used.
</think>

**Verification Certificate**

**Claim**: This code correctly returns the longer of two strings without ownership violations.

**Premises**:
- P1: `longest` borrows `s1` and `s2` as `&str` (immutable references) — no ownership transfer
- P2: `s1.to_string()` and `s2.to_string()` create NEW owned `String` values — independent of the borrows
- P3: The return type is `String` (owned), so the caller receives a fresh allocation
- P4: In `main`, `a` and `b` are borrowed immutably for `longest()`, then used again in `println!`

**Code Trace**:
- Line 1: `a = String::from("hello")` — a owns "hello" (5 bytes)
- Line 2: `b = String::from("hi")` — b owns "hi" (2 bytes)
- Line 3: `longest(&a, &b)` — borrows a and b immutably
  - Inside longest: s1.len()=5 >= s2.len()=2 → returns `s1.to_string()` = new String("hello")
  - Borrows of a and b END when longest returns
- Line 3: `result` now owns the new String("hello")
- Line 4: `println!` borrows a, b, result immutably — all three are still valid

**Conclusion**: **VALID** — The function correctly borrows inputs, creates a new owned String for the return value, and the original strings remain usable after the call. No lifetime issues because the return value is owned (not a reference into the inputs)."""
    },

    # -------------------------------------------------------------------------
    # 3. Go: Goroutine leak (BUGGY)
    # -------------------------------------------------------------------------
    {
        "instruction": "Analyze this Go code for correctness. Does it properly clean up goroutines? Use a structured verification certificate with premises and code trace.",
        "input": """```go
func fetchAll(urls []string) []string {
    results := make([]string, len(urls))
    ch := make(chan struct{ idx int; body string })

    for i, url := range urls {
        go func(i int, url string) {
            resp, err := http.Get(url)
            if err != nil {
                return
            }
            defer resp.Body.Close()
            body, _ := io.ReadAll(resp.Body)
            ch <- struct{ idx int; body string }{i, string(body)}
        }(i, url)
    }

    for i := 0; i < len(urls); i++ {
        r := <-ch
        results[r.idx] = r.body
    }
    return results
}
```""",
        "output": """<think>
I need to check for goroutine leaks and channel deadlocks. The function spawns one goroutine per URL and expects len(urls) results from the channel. But what if some goroutines hit errors and return early without sending to ch?
</think>

**Verification Certificate**

**Claim**: This function correctly fetches all URLs concurrently and returns results without goroutine leaks.

**Premises**:
- P1: `len(urls)` goroutines are spawned, one per URL
- P2: The channel `ch` is unbuffered — each send blocks until a receiver reads
- P3: On error (`err != nil`), the goroutine returns WITHOUT sending to `ch`
- P4: The collection loop reads exactly `len(urls)` values from `ch`
- P5: If K goroutines error out, only `len(urls) - K` values will ever be sent

**Code Trace** (urls = ["http://ok.com", "http://fail.com", "http://ok2.com"]):
- Goroutine 0: http.Get succeeds → sends {0, body0} to ch
- Goroutine 1: http.Get fails → returns immediately, sends NOTHING
- Goroutine 2: http.Get succeeds → sends {2, body2} to ch
- Collection loop: reads r0 (i=0), reads r2 (i=1)... blocks forever waiting for 3rd value

**Conclusion**: **INVALID** — Goroutine leak + deadlock. When any `http.Get` fails, the goroutine returns without sending to `ch`, but the collection loop still expects `len(urls)` messages. The main goroutine blocks forever on the channel read.

**Fix**: Either send errors through the channel too, or use a WaitGroup + buffered channel:

```go
func fetchAll(urls []string) []string {
    results := make([]string, len(urls))
    ch := make(chan struct{ idx int; body string }, len(urls)) // buffered

    var wg sync.WaitGroup
    for i, url := range urls {
        wg.Add(1)
        go func(i int, url string) {
            defer wg.Done()
            resp, err := http.Get(url)
            if err != nil {
                ch <- struct{ idx int; body string }{i, ""} // send empty on error
                return
            }
            defer resp.Body.Close()
            body, _ := io.ReadAll(resp.Body)
            ch <- struct{ idx int; body string }{i, string(body)}
        }(i, url)
    }

    go func() { wg.Wait(); close(ch) }()
    for r := range ch {
        results[r.idx] = r.body
    }
    return results
}
```"""
    },

    # -------------------------------------------------------------------------
    # 4. Python: Thread-safe singleton (CORRECT)
    # -------------------------------------------------------------------------
    {
        "instruction": "Verify this Python thread-safe singleton implementation. Is it correct under concurrent access? Provide a structured certificate.",
        "input": """```python
import threading

class DatabasePool:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self, dsn="default"):
        if self._initialized:
            return
        self.dsn = dsn
        self.connections = []
        self._initialized = True
```""",
        "output": """<think>
This is the double-checked locking pattern. I need to verify: (1) thread safety of instance creation, (2) the __init__ guard, and (3) whether Python's GIL makes the outer check safe.
</think>

**Verification Certificate**

**Claim**: This singleton correctly ensures exactly one instance under concurrent access from multiple threads.

**Premises**:
- P1: `_instance` starts as `None`, `_lock` is a class-level `threading.Lock()`
- P2: `__new__` uses double-checked locking: fast path (no lock) + slow path (with lock)
- P3: Python's GIL ensures the outer `if cls._instance is None` read is atomic for reference checks
- P4: Inside the lock, a second check prevents race where two threads both pass the outer check
- P5: `_initialized` flag prevents `__init__` from re-running on subsequent `DatabasePool()` calls
- P6: `super().__new__(cls)` creates the instance; assignment to `_instance` happens only inside the lock

**Code Trace** (Thread A and Thread B call `DatabasePool("prod")` simultaneously):
- Thread A: outer check → `_instance is None` → True → acquires lock
- Thread B: outer check → `_instance is None` → True → blocks on lock
- Thread A: inner check → `_instance is None` → True → creates instance, sets `_initialized=False`, releases lock
- Thread B: acquires lock → inner check → `_instance is NOT None` → skips creation, releases lock
- Thread A: `__init__` runs → `_initialized` is False → sets dsn, connections, `_initialized=True`
- Thread B: `__init__` runs → `_initialized` is True → returns immediately

**Conclusion**: **VALID** — The double-checked locking pattern is correctly implemented. The outer check avoids lock contention on the fast path. The inner check prevents duplicate creation. The `_initialized` flag prevents `__init__` from resetting state. One subtle note: in CPython, the GIL makes the outer reference check safe, but in theory this pattern could be fragile on non-CPython implementations (PyPy, GraalPy) — using the lock on every call would be safer but slower."""
    },

    # -------------------------------------------------------------------------
    # 5. C++: Use-after-move (BUGGY)
    # -------------------------------------------------------------------------
    {
        "instruction": "Verify this C++ code for correctness. Does it properly handle move semantics? Provide a verification certificate with premises and trace.",
        "input": """```cpp
#include <vector>
#include <string>
#include <iostream>

std::vector<std::string> process(std::vector<std::string> items) {
    std::vector<std::string> result;
    for (auto& item : items) {
        if (item.length() > 3) {
            result.push_back(std::move(item));
        }
    }
    // Log what we didn't keep
    for (const auto& item : items) {
        if (item.length() <= 3) {
            std::cout << "Skipped: " << item << std::endl;
        }
    }
    return result;
}
```""",
        "output": """<think>
The code moves elements out of `items` in the first loop, then reads from `items` in the second loop. After `std::move`, the moved-from string is in a valid but unspecified state — its length could be 0. This means the second loop's length check will see moved strings as short strings and "skip" them erroneously.
</think>

**Verification Certificate**

**Claim**: This function correctly partitions strings by length, moving long ones to result and logging short ones.

**Premises**:
- P1: First loop iterates `items` by reference, moves strings with length > 3 into `result`
- P2: `std::move(item)` transfers ownership — after move, `item` is in a "valid but unspecified" state
- P3: For `std::string`, moved-from state is typically empty (`""`, length 0) but NOT guaranteed by the standard
- P4: Second loop reads `items` again, checking `item.length() <= 3`
- P5: Moved-from strings now have length 0 (typically), which is `<= 3`

**Code Trace** (items = {"hi", "hello", "go", "world"}):
- First loop:
  - "hi" (len=2): skip
  - "hello" (len=5): move to result → items[1] is now "" (moved-from)
  - "go" (len=2): skip
  - "world" (len=5): move to result → items[3] is now "" (moved-from)
- After first loop: items = {"hi", "", "go", ""}, result = {"hello", "world"}
- Second loop:
  - "hi" (len=2 <= 3): prints "Skipped: hi" ✓
  - "" (len=0 <= 3): prints "Skipped: " ✗ (this was "hello", not a short string!)
  - "go" (len=2 <= 3): prints "Skipped: go" ✓
  - "" (len=0 <= 3): prints "Skipped: " ✗ (this was "world")

**Conclusion**: **INVALID** — Use-after-move bug. The second loop reads moved-from strings, which appear as empty strings, causing them to be incorrectly logged as "skipped." The moved-from state satisfies `length() <= 3`, so they pass the filter.

**Fix**: Track indices of kept items, or partition differently:

```cpp
std::vector<std::string> process(std::vector<std::string> items) {
    std::vector<std::string> result;
    std::vector<std::string> skipped;

    for (auto& item : items) {
        if (item.length() > 3) {
            result.push_back(std::move(item));
        } else {
            skipped.push_back(item);  // copy short ones before any moves
        }
    }
    for (const auto& item : skipped) {
        std::cout << "Skipped: " << item << std::endl;
    }
    return result;
}
```"""
    },

    # -------------------------------------------------------------------------
    # 6. JavaScript: Promise.all short-circuit (BUGGY behavior, but correct impl)
    # -------------------------------------------------------------------------
    {
        "instruction": "A developer says this code has a bug because not all API calls complete. Verify the claim using a structured certificate.",
        "input": """```javascript
async function fetchUserData(userIds) {
    const promises = userIds.map(id =>
        fetch(`/api/users/${id}`).then(r => {
            if (!r.ok) throw new Error(`User ${id}: ${r.status}`);
            return r.json();
        })
    );
    const users = await Promise.all(promises);
    return users;
}
// Usage: fetchUserData([1, 2, 999, 4])
// Developer reports: "Only gets error for user 999, users 1, 2, 4 data is lost"
```""",
        "output": """<think>
The developer is experiencing `Promise.all`'s short-circuit behavior — if ANY promise rejects, the entire batch rejects immediately. The successful results for users 1, 2, and 4 are discarded. The code is technically correct JavaScript, but the behavior doesn't match the developer's intent.
</think>

**Verification Certificate**

**Claim**: The developer's bug report is correct — this code loses successful results when any single fetch fails.

**Premises**:
- P1: `Promise.all(promises)` resolves only when ALL promises resolve
- P2: If ANY promise rejects, `Promise.all` rejects immediately with that error
- P3: Successful results from other promises are discarded (not returned)
- P4: `fetch` for user 999 returns 404, causing `throw new Error` → promise rejection
- P5: All fetch requests are already in-flight (they don't cancel), but their results are unreachable

**Code Trace** (userIds = [1, 2, 999, 4]):
- fetch(/api/users/1) → 200 → resolves with user1 data
- fetch(/api/users/2) → 200 → resolves with user2 data
- fetch(/api/users/999) → 404 → r.ok is false → throws Error("User 999: 404") → rejects
- fetch(/api/users/4) → 200 → resolves with user4 data
- Promise.all sees rejection → immediately rejects with Error("User 999: 404")
- `await Promise.all(promises)` throws → users 1, 2, 4 data is lost

**Conclusion**: **VALID** (the bug report is correct) — `Promise.all` short-circuits on first rejection. The code works for the happy path (all users exist) but fails ungracefully when any user is missing.

**Fix**: Use `Promise.allSettled` to get all results regardless of individual failures:

```javascript
async function fetchUserData(userIds) {
    const promises = userIds.map(id =>
        fetch(`/api/users/${id}`)
            .then(r => {
                if (!r.ok) throw new Error(`User ${id}: ${r.status}`);
                return r.json();
            })
            .then(data => ({ status: 'ok', id, data }))
            .catch(err => ({ status: 'error', id, error: err.message }))
    );
    const results = await Promise.all(promises);
    const users = results.filter(r => r.status === 'ok').map(r => r.data);
    const errors = results.filter(r => r.status === 'error');
    if (errors.length) console.warn('Failed:', errors);
    return users;
}
```"""
    },

    # -------------------------------------------------------------------------
    # 7. Python: Race condition in dict update (BUGGY)
    # -------------------------------------------------------------------------
    {
        "instruction": "This Python web server handler keeps losing count updates under load. Verify the code and identify the race condition. Use structured reasoning.",
        "input": """```python
import threading
from flask import Flask, jsonify

app = Flask(__name__)
counters = {}

@app.route('/increment/<key>')
def increment(key):
    if key not in counters:
        counters[key] = 0
    counters[key] += 1
    return jsonify({key: counters[key]})
```""",
        "output": """<think>
Flask uses threads by default. The `counters[key] += 1` is a read-modify-write that isn't atomic. Two threads could read the same value, both increment to the same result, and one update is lost. The `key not in counters` check also races.
</think>

**Verification Certificate**

**Claim**: This handler correctly counts increments per key under concurrent requests.

**Premises**:
- P1: Flask's default server (Werkzeug) uses threading for concurrent requests
- P2: `counters[key] += 1` is syntactic sugar for `counters[key] = counters[key] + 1` — three operations: read, add, write
- P3: Python's GIL prevents simultaneous execution but allows thread switching BETWEEN bytecode instructions
- P4: The read of `counters[key]`, the addition, and the write back are separate bytecodes
- P5: `key not in counters` + `counters[key] = 0` is a check-then-act race

**Code Trace** (Thread A and B both request `/increment/hits` when counters["hits"] = 5):
- Thread A: reads counters["hits"] → 5
- Thread A: computes 5 + 1 = 6
- *GIL switches to Thread B*
- Thread B: reads counters["hits"] → 5 (still 5, A hasn't written yet)
- Thread B: computes 5 + 1 = 6
- Thread B: writes counters["hits"] = 6
- *GIL switches back to Thread A*
- Thread A: writes counters["hits"] = 6 (overwrites B's write — same value!)
- Result: counters["hits"] = 6 instead of expected 7. **One increment is lost.**

**Conclusion**: **INVALID** — Classic TOCTOU (time-of-check-to-time-of-use) race condition. The `+=` operator is not atomic under threading, and the existence check + initialization also races.

**Fix**: Use a lock or `collections.defaultdict` with atomic operations:

```python
import threading
from collections import defaultdict
from flask import Flask, jsonify

app = Flask(__name__)
_lock = threading.Lock()
counters = defaultdict(int)

@app.route('/increment/<key>')
def increment(key):
    with _lock:
        counters[key] += 1
        value = counters[key]
    return jsonify({key: value})
```"""
    },

    # -------------------------------------------------------------------------
    # 8. Rust: Correct async error handling chain (CORRECT)
    # -------------------------------------------------------------------------
    {
        "instruction": "Verify this Rust error handling chain. Does the `?` operator correctly propagate errors through the async call stack? Provide a structured certificate.",
        "input": """```rust
use thiserror::Error;

#[derive(Error, Debug)]
enum AppError {
    #[error("http: {0}")]
    Http(#[from] reqwest::Error),
    #[error("json: {0}")]
    Json(#[from] serde_json::Error),
    #[error("not found: {0}")]
    NotFound(String),
}

async fn fetch_user(id: u64) -> Result<User, AppError> {
    let url = format!("https://api.example.com/users/{}", id);
    let resp = reqwest::get(&url).await?;

    if resp.status() == 404 {
        return Err(AppError::NotFound(format!("user {}", id)));
    }

    let user: User = resp.json().await?;
    Ok(user)
}
```""",
        "output": """<think>
I need to verify that the `?` operator correctly converts each error type into `AppError` via the `From` trait implementations generated by `#[from]`. Let me trace each fallible operation.
</think>

**Verification Certificate**

**Claim**: The `?` operator correctly propagates all errors as `AppError` variants through the async chain.

**Premises**:
- P1: `#[from] reqwest::Error` generates `impl From<reqwest::Error> for AppError` → `?` on reqwest calls produces `AppError::Http`
- P2: `#[from] serde_json::Error` generates `impl From<serde_json::Error> for AppError` → `?` on JSON parsing produces `AppError::Json`
- P3: `AppError::NotFound` is manually constructed — no `From` impl needed
- P4: `reqwest::get().await` returns `Result<Response, reqwest::Error>`
- P5: `resp.json::<User>().await` returns `Result<User, reqwest::Error>` (reqwest does JSON parsing internally, wrapping serde errors)

**Code Trace** (happy path: id=1, server returns 200 + valid JSON):
- `reqwest::get(&url).await` → Ok(Response) → `?` passes through
- `resp.status() == 404` → false → skip NotFound
- `resp.json().await` → Ok(User{...}) → `?` passes through
- Returns `Ok(user)` ✓

**Code Trace** (network error):
- `reqwest::get(&url).await` → Err(reqwest::Error) → `?` converts via `From` → `Err(AppError::Http(e))` ✓

**Code Trace** (404):
- `reqwest::get(&url).await` → Ok(Response{status: 404})
- `resp.status() == 404` → true → returns `Err(AppError::NotFound("user 1"))` ✓

**Code Trace** (200 but malformed JSON):
- `resp.json().await` → Err(reqwest::Error) → `?` converts via `From` → `Err(AppError::Http(e))`
- Note: This becomes `AppError::Http`, not `AppError::Json`, because `reqwest` wraps serde errors in its own error type

**Conclusion**: **VALID** — The error chain correctly propagates all failure modes. One subtlety: JSON parse failures surface as `AppError::Http` (not `AppError::Json`) because reqwest wraps serde internally. The `Json` variant would only be used if you manually called `serde_json::from_str` on the body text. This is correct behavior but may surprise callers expecting `AppError::Json` for bad JSON."""
    },

    # -------------------------------------------------------------------------
    # 9. Go: Correct mutex usage with defer (CORRECT)
    # -------------------------------------------------------------------------
    {
        "instruction": "Verify this Go concurrent cache implementation. Is the mutex usage correct? Analyze with a structured verification certificate.",
        "input": """```go
type Cache struct {
    mu    sync.RWMutex
    items map[string]item
}

type item struct {
    value     interface{}
    expiresAt time.Time
}

func (c *Cache) Get(key string) (interface{}, bool) {
    c.mu.RLock()
    defer c.mu.RUnlock()
    it, ok := c.items[key]
    if !ok || time.Now().After(it.expiresAt) {
        return nil, false
    }
    return it.value, true
}

func (c *Cache) Set(key string, value interface{}, ttl time.Duration) {
    c.mu.Lock()
    defer c.mu.Unlock()
    c.items[key] = item{value: value, expiresAt: time.Now().Add(ttl)}
}

func (c *Cache) Delete(key string) {
    c.mu.Lock()
    defer c.mu.Unlock()
    delete(c.items, key)
}
```""",
        "output": """<think>
I need to verify: (1) RLock for reads, Lock for writes — correct reader-writer pattern; (2) defer ensures unlock even on panic; (3) no lock upgrade attempts (RLock→Lock causes deadlock in Go); (4) expired items are lazily ignored on read but not cleaned up.
</think>

**Verification Certificate**

**Claim**: This concurrent cache correctly handles concurrent reads and writes without data races.

**Premises**:
- P1: `Get` uses `RLock/RUnlock` — allows multiple concurrent readers
- P2: `Set` and `Delete` use `Lock/Unlock` — exclusive access for writers
- P3: `defer` ensures unlock runs even if map access panics (e.g., nil map)
- P4: No lock upgrades — `Get` never tries to acquire `Lock` while holding `RLock`
- P5: `sync.RWMutex` zero value is unlocked — safe to use without initialization
- P6: Expired items are lazily filtered on read but not proactively deleted

**Code Trace** (3 goroutines: G1=Get("k"), G2=Get("k"), G3=Set("k", v, 5s)):
- G1: RLock acquired → reads items["k"] → returns value → RUnlock
- G2: RLock acquired (concurrent with G1) → reads items["k"] → returns value → RUnlock
- G3: Lock blocks until G1 and G2 release RLock → writes items["k"] → Unlock

**Code Trace** (expired key):
- Set("temp", v, 1s) at T=0 → expiresAt = T+1s
- Get("temp") at T=2s → RLock → items["temp"] exists → time.Now().After(T+1s) → true → returns nil, false → RUnlock

**Conclusion**: **VALID** — The RWMutex usage is correct. Reads are concurrent, writes are exclusive, defer ensures cleanup. One design note: expired items are never actually removed from the map (lazy expiration). Over time, the map grows. A production cache would add periodic cleanup (e.g., a background goroutine calling Delete on expired keys). This is a design choice, not a bug — the code is correct for what it implements."""
    },

    # -------------------------------------------------------------------------
    # 10. Python: Subtle generator exhaustion (BUGGY)
    # -------------------------------------------------------------------------
    {
        "instruction": "A developer reports that this function works on the first call but returns empty results on second call with the same data. Verify the code.",
        "input": """```python
def pipeline(data):
    # Step 1: Filter
    filtered = (x for x in data if x > 0)

    # Step 2: Transform
    transformed = (x * 2 for x in filtered)

    # Step 3: Aggregate
    total = sum(transformed)
    count = sum(1 for _ in transformed)  # count items

    return {"total": total, "count": count, "avg": total / count if count else 0}

# Works: pipeline([1, -2, 3, -4, 5])
# Bug: returns {"total": 18, "count": 0, ...} → ZeroDivisionError
```""",
        "output": """<think>
The issue is generator exhaustion. `transformed` is a generator expression — it can only be iterated ONCE. After `sum(transformed)` consumes it, the second `sum(1 for _ in transformed)` gets an empty iterator.
</think>

**Verification Certificate**

**Claim**: This pipeline correctly computes total, count, and average of filtered+transformed data.

**Premises**:
- P1: `filtered` is a generator expression — single-use iterator
- P2: `transformed` is a generator expression chained from `filtered` — also single-use
- P3: `sum(transformed)` iterates the entire generator, consuming all values
- P4: After consumption, the generator is exhausted — further iteration yields nothing
- P5: `sum(1 for _ in transformed)` iterates an already-exhausted generator

**Code Trace** (data = [1, -2, 3, -4, 5]):
- `filtered` generator: will yield 1, 3, 5 (when iterated)
- `transformed` generator: will yield 2, 6, 10 (when iterated)
- `sum(transformed)`: iterates transformed → 2 + 6 + 10 = 18. Generator is now EXHAUSTED.
- `sum(1 for _ in transformed)`: iterates transformed again → yields NOTHING → sum = 0
- `count = 0`, `total / count` → ZeroDivisionError!

**Conclusion**: **INVALID** — Generator exhaustion bug. The generator `transformed` is consumed by the first `sum()` call and yields nothing for the second.

**Fix**: Materialize the generator into a list before aggregating:

```python
def pipeline(data):
    filtered = (x for x in data if x > 0)
    transformed = [x * 2 for x in filtered]  # list, not generator

    total = sum(transformed)
    count = len(transformed)

    return {"total": total, "count": count, "avg": total / count if count else 0}
```"""
    },

    # -------------------------------------------------------------------------
    # 11. C++: Template SFINAE correctness (CORRECT)
    # -------------------------------------------------------------------------
    {
        "instruction": "Verify this C++ template SFINAE pattern. Does it correctly select the right overload based on whether the type has a `.size()` method?",
        "input": """```cpp
#include <type_traits>
#include <string>
#include <vector>
#include <iostream>

template<typename T, typename = void>
struct has_size : std::false_type {};

template<typename T>
struct has_size<T, std::void_t<decltype(std::declval<T>().size())>> : std::true_type {};

template<typename T>
auto describe(const T& val) -> std::enable_if_t<has_size<T>::value, std::string> {
    return "Container with " + std::to_string(val.size()) + " elements";
}

template<typename T>
auto describe(const T& val) -> std::enable_if_t<!has_size<T>::value, std::string> {
    return "Non-container value";
}
```""",
        "output": """<think>
This is a classic SFINAE detection pattern using `std::void_t` and `std::enable_if_t`. I need to verify: (1) the `has_size` trait correctly detects `.size()`, (2) `enable_if_t` properly selects the right overload, (3) no ambiguity when both overloads exist.
</think>

**Verification Certificate**

**Claim**: The `describe` function correctly selects the container overload for types with `.size()` and the non-container overload for other types.

**Premises**:
- P1: `has_size<T>` primary template inherits `false_type` — default is "no .size()"
- P2: Partial specialization uses `std::void_t<decltype(std::declval<T>().size())>` — if `T.size()` is valid, this specialization is selected (inherits `true_type`)
- P3: If `T.size()` is invalid, SFINAE removes the specialization — primary template remains (`false_type`)
- P4: First `describe` overload: enabled when `has_size<T>::value == true`
- P5: Second `describe` overload: enabled when `has_size<T>::value == false`
- P6: Exactly one overload is enabled for any given T — no ambiguity

**Code Trace** (T = std::vector<int>):
- `std::declval<std::vector<int>>().size()` → valid (returns `size_t`) → `void_t` succeeds
- `has_size<std::vector<int>>` matches specialization → `true_type`
- First overload: `enable_if_t<true>` → enabled → `std::string`
- Second overload: `enable_if_t<false>` → SFINAE'd away
- Result: `describe(vec)` → "Container with N elements" ✓

**Code Trace** (T = int):
- `std::declval<int>().size()` → invalid (int has no .size()) → `void_t` fails → SFINAE
- `has_size<int>` uses primary template → `false_type`
- First overload: `enable_if_t<false>` → SFINAE'd away
- Second overload: `enable_if_t<true>` → enabled → `std::string`
- Result: `describe(42)` → "Non-container value" ✓

**Conclusion**: **VALID** — The SFINAE pattern correctly detects `.size()` and selects the right overload. The `void_t` trick ensures substitution failure is soft (not a hard error). Note: In C++20, this entire pattern can be replaced with a simple concept: `template<typename T> concept Sized = requires(T t) { t.size(); };`"""
    },

    # -------------------------------------------------------------------------
    # 12. Python: Mutable default argument (BUGGY)
    # -------------------------------------------------------------------------
    {
        "instruction": "A developer says this function 'remembers' items between calls. Verify the claim and identify the root cause.",
        "input": """```python
def add_item(item, items=[]):
    items.append(item)
    return items

# Expected: each call returns a fresh list with one item
result1 = add_item("apple")   # Expected: ["apple"]
result2 = add_item("banana")  # Expected: ["banana"]
print(result1)  # ["apple", "banana"] ??
print(result2)  # ["apple", "banana"] ??
```""",
        "output": """<think>
This is the classic mutable default argument gotcha. The default list `[]` is created once at function definition time, not per call. Every call that uses the default shares the same list object.
</think>

**Verification Certificate**

**Claim**: Each call to `add_item` with only one argument returns a list containing only that item.

**Premises**:
- P1: Default argument `items=[]` is evaluated ONCE at function definition time (Python semantics)
- P2: The same list object is reused across all calls that don't provide `items`
- P3: `items.append(item)` mutates the default list in-place
- P4: `result1` and `result2` are references to the SAME list object

**Code Trace**:
- Function defined: `items` default = list object at address 0xABC (empty)
- `add_item("apple")`: items=0xABC (default) → append "apple" → 0xABC = ["apple"] → return 0xABC
- `result1` points to 0xABC = ["apple"]
- `add_item("banana")`: items=0xABC (SAME default) → append "banana" → 0xABC = ["apple", "banana"] → return 0xABC
- `result2` points to 0xABC = ["apple", "banana"]
- `result1` ALSO points to 0xABC = ["apple", "banana"] (same object!)

**Conclusion**: **INVALID** — Mutable default argument bug. The default `[]` is shared across calls. Both `result1` and `result2` reference the same list, which accumulates all items.

**Fix**: Use `None` as sentinel and create a new list per call:

```python
def add_item(item, items=None):
    if items is None:
        items = []
    items.append(item)
    return items
```"""
    },

    # -------------------------------------------------------------------------
    # 13. Go: Correct error wrapping chain (CORRECT)
    # -------------------------------------------------------------------------
    {
        "instruction": "Verify this Go error handling. Does `errors.Is` correctly traverse the wrapped error chain? Provide a structured certificate.",
        "input": """```go
var ErrNotFound = errors.New("not found")
var ErrDatabase = errors.New("database error")

func getUser(id int) (*User, error) {
    row := db.QueryRow("SELECT * FROM users WHERE id = ?", id)
    var u User
    if err := row.Scan(&u.Name, &u.Email); err != nil {
        if errors.Is(err, sql.ErrNoRows) {
            return nil, fmt.Errorf("user %d: %w", id, ErrNotFound)
        }
        return nil, fmt.Errorf("user %d query failed: %w", id, ErrDatabase)
    }
    return &u, nil
}

func handler(w http.ResponseWriter, r *http.Request) {
    user, err := getUser(42)
    if err != nil {
        if errors.Is(err, ErrNotFound) {
            http.Error(w, "User not found", 404)
            return
        }
        http.Error(w, "Internal error", 500)
        return
    }
    json.NewEncoder(w).Encode(user)
}
```""",
        "output": """<think>
I need to verify that `fmt.Errorf` with `%w` correctly wraps errors so that `errors.Is` can unwrap and find them. The key is whether the wrapping preserves the error chain.
</think>

**Verification Certificate**

**Claim**: The handler correctly matches wrapped errors using `errors.Is` to return appropriate HTTP status codes.

**Premises**:
- P1: `fmt.Errorf("...: %w", err)` wraps `err` — creates a new error that contains the original
- P2: `errors.Is(err, target)` recursively unwraps the error chain looking for `target`
- P3: `ErrNotFound` and `ErrDatabase` are package-level sentinel errors (pointer equality)
- P4: `sql.ErrNoRows` is the standard library sentinel for "no matching rows"

**Code Trace** (user 42 doesn't exist):
- `row.Scan()` returns `sql.ErrNoRows`
- `errors.Is(err, sql.ErrNoRows)` → true → enters if block
- Returns `fmt.Errorf("user 42: %w", ErrNotFound)` — wraps ErrNotFound with context
- In handler: `err` = wrapped error containing ErrNotFound
- `errors.Is(err, ErrNotFound)` → unwraps → finds ErrNotFound → true
- Returns HTTP 404 ✓

**Code Trace** (database connection fails):
- `row.Scan()` returns some other error (e.g., connection reset)
- `errors.Is(err, sql.ErrNoRows)` → false → enters else
- Returns `fmt.Errorf("user 42 query failed: %w", ErrDatabase)` — wraps ErrDatabase
- In handler: `errors.Is(err, ErrNotFound)` → unwraps → doesn't find ErrNotFound → false
- Falls through to HTTP 500 ✓

**Code Trace** (user exists):
- `row.Scan()` succeeds → err is nil → returns &u, nil
- In handler: err is nil → encodes user as JSON ✓

**Conclusion**: **VALID** — The error wrapping chain is correct. `%w` preserves the sentinel error, and `errors.Is` correctly traverses the chain. The context messages ("user 42:") add debugging information without breaking error matching. This is idiomatic Go error handling."""
    },

    # -------------------------------------------------------------------------
    # 14. Python: Async context manager correctness (CORRECT)
    # -------------------------------------------------------------------------
    {
        "instruction": "Verify this async context manager for database connection pooling. Does it correctly handle acquisition, release, and error cleanup?",
        "input": """```python
import asyncio
from contextlib import asynccontextmanager

class AsyncPool:
    def __init__(self, max_size=5):
        self._sem = asyncio.Semaphore(max_size)
        self._pool = asyncio.Queue(maxsize=max_size)
        for _ in range(max_size):
            self._pool.put_nowait(self._create_conn())

    def _create_conn(self):
        return {"id": id(object()), "healthy": True}

    @asynccontextmanager
    async def acquire(self):
        await self._sem.acquire()
        conn = await self._pool.get()
        try:
            yield conn
        except Exception:
            conn["healthy"] = False
            raise
        finally:
            if conn["healthy"]:
                await self._pool.put(conn)
            else:
                await self._pool.put(self._create_conn())
            self._sem.release()
```""",
        "output": """<think>
I need to verify: (1) semaphore correctly bounds concurrency, (2) connection is always returned to pool (even on error), (3) unhealthy connections are replaced, (4) no semaphore/queue state desync.
</think>

**Verification Certificate**

**Claim**: This async pool correctly manages connection lifecycle with bounded concurrency and error recovery.

**Premises**:
- P1: Semaphore starts at `max_size` — limits concurrent acquisitions
- P2: Queue pre-filled with `max_size` connections — matches semaphore count
- P3: `acquire()` takes semaphore permit THEN gets connection from queue
- P4: `finally` block ALWAYS returns a connection to the queue and releases the semaphore
- P5: On exception, connection is marked unhealthy → replaced with fresh one in finally
- P6: `@asynccontextmanager` + `try/yield/finally` ensures cleanup runs on both normal exit and exception

**Code Trace** (normal usage):
- `await sem.acquire()` → permit granted (4 remaining)
- `await pool.get()` → gets conn1
- `yield conn1` → caller uses connection
- No exception → finally: conn1 is healthy → `pool.put(conn1)` → `sem.release()` (5 remaining)
- Pool state: restored to original ✓

**Code Trace** (exception during usage):
- `await sem.acquire()` → permit granted
- `await pool.get()` → gets conn2
- `yield conn2` → caller raises ValueError
- `except Exception` → `conn2["healthy"] = False` → re-raises ValueError
- `finally` → conn2 NOT healthy → `pool.put(self._create_conn())` → fresh connection replaces broken one
- `sem.release()` → semaphore balanced
- ValueError propagates to caller ✓

**Code Trace** (pool exhaustion — 6th concurrent request with max_size=5):
- 5 tasks hold permits → `await sem.acquire()` blocks 6th task
- When any task finishes → releases permit → 6th task unblocks

**Conclusion**: **VALID** — The pool correctly handles all lifecycle states. Semaphore and queue stay synchronized because: (1) every `sem.acquire` is paired with `sem.release` in finally, (2) every `pool.get` is paired with `pool.put` in finally, (3) unhealthy connections are replaced (not lost). The `@asynccontextmanager` pattern guarantees the finally block runs."""
    },

    # -------------------------------------------------------------------------
    # 15. JavaScript: Closure variable capture (BUGGY)
    # -------------------------------------------------------------------------
    {
        "instruction": "Verify this JavaScript code. The developer expects buttons 0-4 to log their index when clicked, but all buttons log '5'. Identify and fix the issue.",
        "input": """```javascript
function createButtons() {
    const buttons = [];
    for (var i = 0; i < 5; i++) {
        const btn = document.createElement('button');
        btn.textContent = `Button ${i}`;
        btn.addEventListener('click', function() {
            console.log(`Clicked button ${i}`);
        });
        buttons.push(btn);
    }
    return buttons;
}
```""",
        "output": """<think>
Classic closure-over-var bug. `var i` has function scope, not block scope. By the time any button is clicked, the loop has finished and `i` is 5. All click handlers close over the same `i` variable.
</think>

**Verification Certificate**

**Claim**: Each button correctly logs its own index (0-4) when clicked.

**Premises**:
- P1: `var i` declares `i` with FUNCTION scope — one `i` variable shared across all loop iterations
- P2: The click handler is a closure that captures `i` by reference, not by value
- P3: Click handlers execute LATER (when user clicks), not during the loop
- P4: By the time any handler runs, the loop has completed: `i` = 5

**Code Trace**:
- Loop iteration 0: creates button, handler captures reference to `i` (currently 0)
- Loop iteration 1: creates button, handler captures reference to SAME `i` (currently 1)
- ...iterations 2, 3, 4...
- Loop ends: `i` = 5 (the value that failed `i < 5`)
- User clicks Button 0: handler reads `i` → 5 → logs "Clicked button 5" ✗
- User clicks Button 3: handler reads `i` → 5 → logs "Clicked button 5" ✗

**Conclusion**: **INVALID** — All handlers share the same `var i`, which is 5 after the loop. This is the classic "closure over loop variable" bug.

**Fix**: Use `let` instead of `var` — `let` has block scope, creating a fresh `i` per iteration:

```javascript
function createButtons() {
    const buttons = [];
    for (let i = 0; i < 5; i++) {  // let instead of var
        const btn = document.createElement('button');
        btn.textContent = `Button ${i}`;
        btn.addEventListener('click', function() {
            console.log(`Clicked button ${i}`);
        });
        buttons.push(btn);
    }
    return buttons;
}
```"""
    },

    # -------------------------------------------------------------------------
    # 16. Rust: Correct lifetime elision (CORRECT)
    # -------------------------------------------------------------------------
    {
        "instruction": "Verify this Rust code's lifetime handling. Does the compiler correctly infer lifetimes, or will it fail to compile?",
        "input": """```rust
struct Config {
    name: String,
    values: Vec<i32>,
}

impl Config {
    fn name(&self) -> &str {
        &self.name
    }

    fn first_value(&self) -> Option<&i32> {
        self.values.first()
    }

    fn summary(&self) -> String {
        format!("{}: {:?}", self.name(), self.values)
    }
}

fn print_config(config: &Config) {
    let name = config.name();
    let first = config.first_value();
    println!("Config '{}', first={:?}", name, first);
}
```""",
        "output": """<think>
Let me check lifetime elision rules. For methods with `&self`, the output lifetime is tied to `self` by the first elision rule. All references returned from these methods borrow from `self`, which is fine as long as the Config outlives the references.
</think>

**Verification Certificate**

**Claim**: This code compiles successfully with correct lifetime inference.

**Premises**:
- P1: Lifetime elision rule 1: each `&self` parameter gets its own lifetime `'a`
- P2: Lifetime elision rule 3: if one of the parameters is `&self`, the output lifetime is `'a` (tied to self)
- P3: `name(&self) -> &str` elides to `name<'a>(&'a self) -> &'a str` — borrows from self
- P4: `first_value(&self) -> Option<&i32>` elides to `first_value<'a>(&'a self) -> Option<&'a i32>` — borrows from self.values
- P5: `summary(&self) -> String` returns OWNED String — no lifetime constraints
- P6: In `print_config`, both `name` and `first` borrow from `config` which is alive for the entire function

**Code Trace** (compile-time):
- `config.name()` → returns `&str` with lifetime of `config` → valid
- `config.first_value()` → returns `Option<&i32>` with lifetime of `config` → valid
- `println!` borrows `name` and `first` immutably → both still valid (config alive) → valid
- No mutable borrows conflict with immutable borrows

**Conclusion**: **VALID** — The code compiles correctly. Lifetime elision rules correctly tie output lifetimes to `&self`. The `summary()` method returns an owned `String`, so it has no lifetime constraints. In `print_config`, all borrows are from the same `config` reference, which outlives all local variables."""
    },

    # -------------------------------------------------------------------------
    # 17. Python: Correct decorator with arguments (CORRECT)
    # -------------------------------------------------------------------------
    {
        "instruction": "Verify this rate-limiting decorator. Does it correctly enforce the rate limit across calls?",
        "input": """```python
import time
import functools
from collections import deque

def rate_limit(max_calls, period):
    def decorator(func):
        calls = deque()

        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            now = time.monotonic()
            # Remove expired timestamps
            while calls and calls[0] <= now - period:
                calls.popleft()
            if len(calls) >= max_calls:
                wait = period - (now - calls[0])
                time.sleep(wait)
                # Clean up again after sleeping
                now = time.monotonic()
                while calls and calls[0] <= now - period:
                    calls.popleft()
            calls.append(time.monotonic())
            return func(*args, **kwargs)
        return wrapper
    return decorator
```""",
        "output": """<think>
This is a sliding window rate limiter using a deque of timestamps. I need to verify: (1) the sliding window logic is correct, (2) sleep duration is right, (3) `functools.wraps` preserves metadata, (4) the closure correctly shares state across calls.
</think>

**Verification Certificate**

**Claim**: This decorator correctly limits a function to `max_calls` invocations within any `period`-second sliding window.

**Premises**:
- P1: `calls` deque is in the closure — shared across all invocations of the wrapped function
- P2: Expired timestamps (older than `period` seconds) are pruned on each call
- P3: If at capacity, sleeps until the oldest call expires (sliding window)
- P4: After sleeping, re-prunes and records the new call timestamp
- P5: `time.monotonic()` is monotonically increasing — immune to wall clock adjustments
- P6: `functools.wraps(func)` preserves `__name__`, `__doc__`, etc.

**Code Trace** (@rate_limit(max_calls=3, period=1.0)):
- T=0.0: call 1 → calls empty → no wait → append 0.0 → calls=[0.0]
- T=0.2: call 2 → prune(none expired) → len=1 < 3 → append 0.2 → calls=[0.0, 0.2]
- T=0.4: call 3 → prune(none) → len=2 < 3 → append 0.4 → calls=[0.0, 0.2, 0.4]
- T=0.5: call 4 → prune(none) → len=3 >= 3 → wait = 1.0 - (0.5 - 0.0) = 0.5s → sleep(0.5)
- T=1.0: wake up → prune(0.0 expired at T=1.0) → calls=[0.2, 0.4] → len=2 < 3 → append 1.0 → calls=[0.2, 0.4, 1.0]
- Rate enforced: 4 calls spread across 1.0s ✓

**Conclusion**: **VALID** — The sliding window rate limiter is correct for single-threaded use. The deque efficiently maintains the window with O(1) append/popleft. **Caveat**: NOT thread-safe. Concurrent calls could race on `len(calls)` check and `calls.append()`. For thread safety, add a `threading.Lock`. For async, use `asyncio.Lock` and `asyncio.sleep`."""
    },

    # -------------------------------------------------------------------------
    # 18. Go: Nil interface check gotcha (BUGGY)
    # -------------------------------------------------------------------------
    {
        "instruction": "This Go function is supposed to return nil when no error occurs, but the caller's nil check always fails. Verify the code.",
        "input": """```go
type AppError struct {
    Code    int
    Message string
}

func (e *AppError) Error() string {
    return fmt.Sprintf("[%d] %s", e.Code, e.Message)
}

func validate(input string) error {
    var err *AppError
    if input == "" {
        err = &AppError{400, "input required"}
    }
    return err  // Returns (*AppError)(nil), NOT nil interface
}

func main() {
    err := validate("hello")
    if err != nil {
        fmt.Println("Error:", err)  // Always prints, even with valid input!
    }
}
```""",
        "output": """<think>
This is the classic Go nil interface gotcha. An interface value is nil only when BOTH its type and value are nil. Returning a typed nil pointer (`(*AppError)(nil)`) gives an interface with type=*AppError, value=nil — which is NOT equal to nil.
</think>

**Verification Certificate**

**Claim**: `validate("hello")` returns nil, and the nil check in main correctly detects no error.

**Premises**:
- P1: `var err *AppError` declares a nil pointer of type `*AppError`
- P2: `input == ""` is false for "hello" → `err` stays nil (*AppError pointer is nil)
- P3: `return err` returns a nil `*AppError` pointer as an `error` interface
- P4: Go interface = (type, value) pair. `error` interface wrapping `(*AppError)(nil)` = (type=*AppError, value=nil)
- P5: `err != nil` checks if the INTERFACE is nil, i.e., both type AND value are nil
- P6: (type=*AppError, value=nil) ≠ nil interface (type=nil, value=nil)

**Code Trace**:
- `validate("hello")`: `var err *AppError` → nil pointer
- `input == ""` → false → no assignment
- `return err` → returns `error` interface with type=*AppError, value=nil
- In main: `err != nil` → interface has non-nil type → evaluates to TRUE
- Prints "Error:" → calls `err.Error()` → PANICS (nil pointer dereference on `e.Code`)

**Conclusion**: **INVALID** — Go nil interface gotcha. A typed nil pointer wrapped in an interface is NOT nil. The function should return `nil` explicitly (untyped nil) instead of a typed nil pointer.

**Fix**: Return `nil` directly instead of the typed variable:

```go
func validate(input string) error {
    if input == "" {
        return &AppError{400, "input required"}
    }
    return nil  // Untyped nil → interface is (type=nil, value=nil) → correctly == nil
}
```"""
    },

    # -------------------------------------------------------------------------
    # 19. Python: Correct async gather with exception handling (CORRECT)
    # -------------------------------------------------------------------------
    {
        "instruction": "Verify this async task manager. Does it correctly handle partial failures without losing successful results?",
        "input": """```python
import asyncio

async def safe_gather(*coros, return_exceptions=False):
    tasks = [asyncio.ensure_future(c) for c in coros]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    successes = []
    failures = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            failures.append((i, result))
        else:
            successes.append((i, result))

    if not return_exceptions and failures:
        # Cancel any pending tasks (already done since gather completed)
        raise failures[0][1]  # Re-raise first failure

    return successes, failures
```""",
        "output": """<think>
Let me verify the gather semantics. `return_exceptions=True` in the inner gather means ALL tasks complete (no short-circuit). Results are partitioned into successes and failures. If the caller doesn't want exceptions, the first failure is re-raised.
</think>

**Verification Certificate**

**Claim**: This function correctly gathers all results, partitions successes/failures, and optionally re-raises the first failure.

**Premises**:
- P1: `asyncio.ensure_future(c)` wraps each coroutine as a Task (starts execution)
- P2: Inner `gather(*tasks, return_exceptions=True)` waits for ALL tasks to complete — exceptions don't short-circuit
- P3: Results order matches input order — `results[i]` corresponds to `coros[i]`
- P4: `isinstance(result, Exception)` correctly identifies failed tasks
- P5: When `return_exceptions=False` and failures exist, re-raises the first failure
- P6: All tasks have already completed by the time we check results (gather awaited them all)

**Code Trace** (3 tasks: success, failure, success):
- Task 0: returns "ok" → results[0] = "ok"
- Task 1: raises ValueError("bad") → results[1] = ValueError("bad")
- Task 2: returns "also ok" → results[2] = "also ok"
- Partition: successes = [(0, "ok"), (2, "also ok")], failures = [(1, ValueError)]
- If return_exceptions=True: returns (successes, failures) ✓
- If return_exceptions=False: raises ValueError("bad") ✓

**Conclusion**: **VALID** — The function correctly handles partial failures. Using `return_exceptions=True` in the inner gather is the key — it prevents the standard `gather` behavior of cancelling remaining tasks on first exception. All results are preserved regardless of individual task outcomes. The index tracking in tuples allows the caller to match results to their original position."""
    },

    # -------------------------------------------------------------------------
    # 20. C++: Dangling reference from temporary (BUGGY)
    # -------------------------------------------------------------------------
    {
        "instruction": "Verify this C++ code. Is the string_view safe to use after the function returns?",
        "input": """```cpp
#include <string>
#include <string_view>
#include <iostream>

std::string_view get_greeting(const std::string& name) {
    std::string greeting = "Hello, " + name + "!";
    return greeting;  // Returns string_view to local string
}

int main() {
    auto sv = get_greeting("World");
    std::cout << sv << std::endl;  // Undefined behavior?
}
```""",
        "output": """<think>
`std::string_view` is a non-owning reference. Returning a `string_view` to a local `std::string` creates a dangling reference — the string is destroyed when the function returns, but the string_view still points to the freed memory.
</think>

**Verification Certificate**

**Claim**: The code safely prints "Hello, World!" using a string_view returned from get_greeting.

**Premises**:
- P1: `std::string greeting` is a local variable — destroyed at function scope exit
- P2: `return greeting` implicitly converts `std::string` to `std::string_view` — creates a view pointing to greeting's internal buffer
- P3: `std::string_view` does NOT own the data — it's a pointer + length
- P4: When `get_greeting` returns, `greeting` is destroyed → its buffer is freed
- P5: `sv` in main holds a string_view pointing to FREED memory

**Code Trace**:
- `get_greeting("World")`:
  - `greeting` allocated on stack, internal buffer = "Hello, World!" (heap)
  - `return greeting` → implicit conversion to `string_view{greeting.data(), greeting.size()}`
  - Function returns → `greeting` destructor runs → heap buffer freed
- In main: `sv` = string_view{dangling_ptr, 13}
- `std::cout << sv` → reads from freed memory → **UNDEFINED BEHAVIOR**

**Conclusion**: **INVALID** — Dangling reference. The `string_view` outlives the `string` it references. This may appear to work (memory might not be overwritten yet) but is UB and will crash under sanitizers.

**Fix**: Return `std::string` (owned) instead of `string_view`:

```cpp
std::string get_greeting(const std::string& name) {
    return "Hello, " + name + "!";  // Return owned string, move semantics apply
}
```"""
    },
]


def main():
    # Append to existing file
    existing = 0
    if OUTPUT.exists():
        with open(OUTPUT, encoding="utf-8") as f:
            existing = sum(1 for _ in f)

    with open(OUTPUT, "a", encoding="utf-8") as f:
        for pair in PAIRS:
            f.write(json.dumps(pair, ensure_ascii=False) + "\n")

    total = existing + len(PAIRS)
    print(f"Appended {len(PAIRS)} semi-formal verification pairs to {OUTPUT}")
    print(f"Total v9 research pairs: {total}")


if __name__ == "__main__":
    main()
