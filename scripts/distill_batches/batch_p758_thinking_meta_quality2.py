"""Phase 3F: Metacognition — Code Quality Judgment (Part 2)

Scenario 2: Rate code correctness with edge case analysis.
Trace with adversarial inputs.
"""

PAIRS = [
    (
        "thinking/meta-quality-correctness-email-validation",
        r'''Rate the correctness of this email validation (1-10):

```python
def is_valid_email(email: str) -> bool:
    if not email or '@' not in email:
        return False
    local, domain = email.split('@')
    if not local or not domain:
        return False
    if '.' not in domain:
        return False
    if domain.startswith('.') or domain.endswith('.'):
        return False
    return True
```''',
        r'''<think>
Let me trace this with adversarial inputs:

1. `""` → caught by `not email` → False ✓
2. `"noatsign"` → caught by `'@' not in email` → False ✓
3. `"@domain.com"` → `local = ""` → caught by `not local` → False ✓
4. `"user@"` → `domain = ""` → caught by `not domain` → False ✓
5. `"user@domain"` → caught by `'.' not in domain` → False ✓
6. `"user@.com"` → caught by `domain.startswith('.')` → False ✓
7. `"user@domain."` → caught by `domain.endswith('.')` → False ✓
8. `"user@domain.com"` → passes all checks → True ✓

Now adversarial inputs:
9. `"user@@domain.com"` → `email.split('@')` raises ValueError (too many values to unpack) → CRASH ✗
10. `"user@dom@ain.com"` → same crash ✗
11. `"a b@domain.com"` → spaces in local part → accepted but invalid ✗
12. `"user@-domain.com"` → domain starts with hyphen → accepted but violates DNS ✗
13. `"user@domain..com"` → double dots in domain → accepted but invalid ✗
14. `"<script>@domain.com"` → XSS attempt in local part → accepted ✗

Bug #9-10 is a crash (correctness failure). The rest are false positives (accepting invalid emails).

Correctness score: catches basic cases but crashes on double @ and misses many invalid patterns. Maybe 4/10.
</think>

**Correctness: 4/10**

**Critical bug — crashes on multiple @ signs:**
```python
>>> is_valid_email("user@@domain.com")
ValueError: too many values to unpack
```

`email.split('@')` returns 3+ parts but the unpacking expects exactly 2.

**Fix for the crash:**
```python
parts = email.split('@')
if len(parts) != 2:
    return False
local, domain = parts
```

**Additional false positives (accepts invalid emails):**
| Input | Result | Should be |
|-------|--------|-----------|
| `"a b@domain.com"` | True | False (spaces) |
| `"user@-domain.com"` | True | False (leading hyphen) |
| `"user@domain..com"` | True | False (consecutive dots) |
| `"user@123.456.789.0"` | True | Depends on context |

**The honest recommendation:** Don't write email validation yourself. Use a library:
```python
from email_validator import validate_email, EmailNotValidError

def is_valid_email(email: str) -> bool:
    try:
        validate_email(email, check_deliverability=False)
        return True
    except EmailNotValidError:
        return False
```

Email validation is an RFC 5322 minefield. Even the regex-based approach has edge cases. A well-maintained library handles them all.'''
    ),
    (
        "thinking/meta-quality-correctness-binary-search",
        r'''Rate the correctness of this binary search (1-10):

```python
def binary_search(arr, target):
    lo, hi = 0, len(arr) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if arr[mid] == target:
            return mid
        elif arr[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1
```''',
        r'''<think>
Let me trace this with various inputs:

1. Normal case: `[1,3,5,7,9], 5`
   - lo=0, hi=4, mid=2, arr[2]=5 → found at index 2 ✓

2. Target at start: `[1,3,5,7,9], 1`
   - lo=0, hi=4, mid=2, arr[2]=5 > 1 → hi=1
   - lo=0, hi=1, mid=0, arr[0]=1 → found at index 0 ✓

3. Target at end: `[1,3,5,7,9], 9`
   - lo=0, hi=4, mid=2 → lo=3
   - lo=3, hi=4, mid=3, arr[3]=7 → lo=4
   - lo=4, hi=4, mid=4, arr[4]=9 → found at index 4 ✓

4. Target not found: `[1,3,5,7,9], 4`
   - lo=0, hi=4, mid=2, arr[2]=5 > 4 → hi=1
   - lo=0, hi=1, mid=0, arr[0]=1 < 4 → lo=1
   - lo=1, hi=1, mid=1, arr[1]=3 < 4 → lo=2
   - lo=2, hi=1, exit loop → return -1 ✓

5. Empty array: `[], 5`
   - lo=0, hi=-1, loop doesn't execute → return -1 ✓

6. Single element found: `[5], 5`
   - lo=0, hi=0, mid=0, arr[0]=5 → found at index 0 ✓

7. Single element not found: `[3], 5`
   - lo=0, hi=0, mid=0, arr[0]=3 < 5 → lo=1
   - lo=1, hi=0, exit → return -1 ✓

8. Two elements: `[1,3], 3`
   - lo=0, hi=1, mid=0, arr[0]=1 < 3 → lo=1
   - lo=1, hi=1, mid=1, arr[1]=3 → found at index 1 ✓

9. Duplicate elements: `[1,3,3,3,5], 3`
   - lo=0, hi=4, mid=2, arr[2]=3 → found at index 2 ✓
   (But which 3? Returns the first one found, not necessarily the first occurrence.)

10. Integer overflow: `(lo + hi) // 2` — in Python, integers are arbitrary precision, so no overflow. In C/Java this would be a bug.

The algorithm is correct for all standard cases. The only "issue" is that with duplicates, it doesn't guarantee finding the first/last occurrence — but that's not a bug, it's just not bisect_left/bisect_right.

Correctness: 9/10. Solid implementation of standard binary search.
</think>

**Correctness: 9/10**

Traced with 8+ adversarial inputs — all correct:

| Test case | Result | Correct? |
|-----------|--------|----------|
| Normal `[1,3,5,7,9], 5` | 2 | ✓ |
| First element | 0 | ✓ |
| Last element | 4 | ✓ |
| Not found | -1 | ✓ |
| Empty array `[]` | -1 | ✓ |
| Single element (found) | 0 | ✓ |
| Single element (not found) | -1 | ✓ |
| Two elements | Correct | ✓ |

**Why 9 and not 10:**
- With duplicates `[1,3,3,3,5]`, returns index 2 (middle 3), not the first or last occurrence. This isn't a bug — standard binary search finds "any" match — but callers might expect first/last.
- No type hints or docstring (style, not correctness)

**No integer overflow in Python:** `(lo + hi) // 2` is safe because Python integers have arbitrary precision. In Java/C++, this would overflow — use `lo + (hi - lo) // 2` instead.

**The implementation is textbook correct.** Loop invariant: target is in `arr[lo..hi]` if it exists. Each iteration shrinks the range by at least 1. Terminates when `lo > hi` (not found) or `arr[mid] == target` (found).'''
    ),
    (
        "thinking/meta-quality-correctness-flatten-recursive",
        r'''Rate the correctness of this recursive list flattener (1-10):

```python
def flatten(nested):
    result = []
    for item in nested:
        if isinstance(item, list):
            result.extend(flatten(item))
        else:
            result.append(item)
    return result
```''',
        r'''<think>
Let me trace with adversarial inputs:

1. Normal: `[1, [2, 3], [4, [5, 6]]]` → `[1, 2, 3, 4, 5, 6]` ✓
2. Empty: `[]` → `[]` ✓
3. Already flat: `[1, 2, 3]` → `[1, 2, 3]` ✓
4. Deeply nested: `[[[[1]]]]` → `[1]` ✓
5. Mixed types: `[1, "hello", [2, "world"]]` → `[1, "hello", 2, "world"]` ✓
6. Nested empty lists: `[[], [[]], [1, []]]` → `[1]` ✓
7. Tuples: `[1, (2, 3), [4]]` → `[1, (2, 3), 4]` — tuples are NOT flattened. Is this correct? Depends on expectations.
8. None values: `[1, None, [2, None]]` → `[1, None, 2, None]` ✓
9. Strings: `["abc", ["def"]]` → `["abc", "def"]` ✓ (strings are NOT iterable-flattened, because isinstance checks for list, not iterable)
10. Very deep nesting: `[[[...[1]...]]]` with 1000 levels → RecursionError ✗

Bug #10 is the main issue — Python's default recursion limit is 1000. Very deeply nested structures cause a crash. But this is extreme — in practice, nesting > 10 levels is unusual.

Bug #7 is a design choice — only `list` is flattened, not tuples or other iterables. This is actually reasonable and prevents accidental flattening of strings.

Correctness: 8/10. Works correctly for all reasonable inputs. The recursion limit is a theoretical concern but matters for untrusted input.
</think>

**Correctness: 8/10**

Traced with 10 adversarial inputs:

| Test case | Result | Correct? |
|-----------|--------|----------|
| `[1, [2, 3], [4, [5, 6]]]` | `[1,2,3,4,5,6]` | ✓ |
| `[]` | `[]` | ✓ |
| Already flat `[1,2,3]` | `[1,2,3]` | ✓ |
| Deep `[[[[1]]]]` | `[1]` | ✓ |
| Mixed types `[1, "hi", [2]]` | `[1, "hi", 2]` | ✓ |
| Nested empties `[[], [[]]]` | `[]` | ✓ |
| Tuples `[1, (2,3)]` | `[1, (2,3)]` | ⚠️ Design choice |
| 1000+ depth nesting | RecursionError | ✗ |

**Two concerns:**

**1. RecursionError on deep nesting (-1 point):**
If processing untrusted input, malicious data like `[[[...[1]...]]]` (1000+ deep) crashes.
```python
# Fix: iterative version
def flatten(nested):
    stack = list(reversed(nested))
    result = []
    while stack:
        item = stack.pop()
        if isinstance(item, list):
            stack.extend(reversed(item))
        else:
            result.append(item)
    return result
```

**2. Only flattens `list`, not tuples/sets (-1 point):**
This is actually a *good* design choice — it prevents accidentally iterating over strings (which are iterable). But it should be documented.

**Overall:** Correct for all practical inputs. The recursive approach is clean and readable. For production use with untrusted input, switch to iterative.'''
    ),
    (
        "thinking/meta-quality-correctness-url-parser",
        r'''Rate the correctness of this URL parser (1-10):

```python
def parse_url(url):
    protocol = url.split("://")[0]
    rest = url.split("://")[1]
    if "/" in rest:
        domain = rest.split("/")[0]
        path = "/" + "/".join(rest.split("/")[1:])
    else:
        domain = rest
        path = "/"
    if "?" in path:
        path, query = path.split("?")
        params = dict(p.split("=") for p in query.split("&"))
    else:
        params = {}
    return {"protocol": protocol, "domain": domain, "path": path, "params": params}
```''',
        r'''<think>
Let me trace with adversarial inputs:

1. Normal: `"https://example.com/path?key=value"` → protocol=https, domain=example.com, path=/path, params={key: value} ✓
2. No path: `"https://example.com"` → protocol=https, domain=example.com, path=/, params={} ✓
3. Multiple path segments: `"https://example.com/a/b/c"` → domain=example.com, path=/a/b/c ✓
4. Multiple query params: `"https://example.com/p?a=1&b=2"` → params={a: 1, b: 2} ✓

Now adversarial:
5. No protocol: `"example.com/path"` → url.split("://")[0] = "example.com/path", [1] = IndexError ✗ CRASH
6. Port: `"https://example.com:8080/path"` → domain="example.com:8080" — port mixed into domain ✗
7. Fragment: `"https://example.com/path#section"` → fragment mixed into path ✗
8. Query with no value: `"https://example.com?key"` → `"key".split("=")` = ["key"] → dict() fails ✗ CRASH
9. Encoded chars: `"https://example.com/path?q=hello%20world"` → not decoded, stored raw ⚠️
10. Query with = in value: `"https://example.com?q=a=b"` → `"q=a=b".split("=")` = ["q", "a", "b"] → dict() fails ✗ CRASH
11. Empty string: `""` → split("://") = [""] → [1] = IndexError ✗ CRASH
12. Auth in URL: `"https://user:pass@example.com"` → domain="user:pass@example.com" ✗
13. Multiple ? in URL: `"https://example.com/path?a=1?b=2"` → split("?") gives wrong result ✗

This crashes on at least 4 inputs and gives wrong results on at least 4 more. Maybe 2/10.
</think>

**Correctness: 2/10**

**Crashes on these inputs:**
| Input | Error |
|-------|-------|
| `"example.com/path"` (no protocol) | IndexError |
| `""` (empty) | IndexError |
| `"https://example.com?key"` (no value) | ValueError in dict() |
| `"https://example.com?q=a=b"` (= in value) | ValueError in dict() |

**Wrong results on these inputs:**
| Input | Bug |
|-------|-----|
| `"https://example.com:8080/path"` | Port mixed into domain |
| `"https://example.com/path#section"` | Fragment ignored |
| `"https://user:pass@example.com"` | Auth mixed into domain |
| `"https://example.com/path?q=hello%20world"` | Not URL-decoded |

**The fix: don't parse URLs yourself.**
```python
from urllib.parse import urlparse, parse_qs

def parse_url(url):
    parsed = urlparse(url)
    return {
        "protocol": parsed.scheme,
        "domain": parsed.hostname,
        "port": parsed.port,
        "path": parsed.path or "/",
        "params": parse_qs(parsed.query),
    }
```

`urllib.parse` handles all edge cases: ports, auth, fragments, encoding, missing components, etc.

**The lesson: never hand-parse URLs, emails, dates, or HTML with string splitting.** Use the standard library parser — it handles hundreds of edge cases you won't think of.'''
    ),
    (
        "thinking/meta-quality-correctness-debounce",
        r'''Rate the correctness of this JavaScript debounce implementation (1-10):

```javascript
function debounce(fn, delay) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), delay);
    };
}
```''',
        r'''<think>
Let me trace through the behavior:

1. Call debounced function → clears any existing timer, sets new timer for `delay` ms
2. Call again before delay → clears previous timer, sets new one. Previous call never fires. ✓
3. Wait for delay → function fires with most recent args. ✓
4. Multiple rapid calls → only the last one fires. ✓ (that's what debounce means)

Edge cases:
5. `this` context: The returned function is a regular function (not arrow), so `this` depends on how it's called. If used as a method: `obj.debouncedMethod()` → `this` inside the returned function is `obj`. But the arrow function `() => fn(...args)` captures `this` from the outer scope (the returned function). So `this` is correctly propagated to `fn`. ✓

Wait, actually: `fn(...args)` inside the arrow function — `fn` is called without explicit `this` binding. If the caller expects `this` to be the object: `const handler = debounce(obj.method, 100); handler()` — `fn` is just the function reference, `this` inside `fn` will be undefined (strict mode) or window.

Actually, the arrow function captures `this` from the lexical scope of the regular function. So `fn(...args)` doesn't pass `this`. To fix: `fn.apply(this, args)` inside the arrow... but that won't work because arrow functions don't have their own `this`.

Let me think more carefully:
```javascript
return function(...args) {  // this = whatever context it's called with
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);  // arrow captures this from above
    // But fn(...args) doesn't use this at all. fn is called without context.
};
```

To preserve `this`:
```javascript
return function(...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
};
```

So the `this` binding is broken. This matters for event handlers and object methods.

6. Return value: `fn`'s return value is lost because `setTimeout` doesn't return the callback's result. This is expected for debounce (async, can't return synchronously).

7. Cancel: No way to cancel a pending debounce. Minor feature gap.

8. Leading vs trailing: This only does trailing debounce. No option for leading edge.

Core debounce logic is correct. The `this` binding bug is a real issue. I'd say 7/10.
</think>

**Correctness: 7/10**

**Core debounce logic: correct.** Rapid calls → only the last one fires after the delay. Timer properly cleared on each call.

**Bug: `this` context is lost (-2 points):**
```javascript
const obj = {
    name: "Alice",
    greet: debounce(function() {
        console.log(this.name);  // undefined! `this` not forwarded
    }, 100)
};
obj.greet();  // Logs undefined instead of "Alice"
```

**Fix:**
```javascript
function debounce(fn, delay) {
    let timer;
    return function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);  // Preserve this
    };
}
```

The arrow function inside `setTimeout` captures `this` from the outer regular function, and `fn.apply(this, args)` forwards it.

**Missing feature: no cancel (-1 point):**
```javascript
function debounce(fn, delay) {
    let timer;
    const debounced = function(...args) {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
    debounced.cancel = () => clearTimeout(timer);
    return debounced;
}
```

**Summary:**
- ✅ Core debounce logic (trailing edge)
- ✅ Argument forwarding
- ✅ Timer management
- ❌ `this` binding (broken for methods/event handlers)
- ⚠️ No cancel method
- ⚠️ No leading edge option'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
