"""Phase 3A: Metacognition — Error Recognition in Own Output (Part 15)
Final 10 pairs to reach 80 total for Phase 3A.
"""

PAIRS = [
    (
        "thinking/meta-error-cors-wildcard-with-credentials",
        r'''I configured CORS for my API:

```python
from flask_cors import CORS

app = Flask(__name__)
CORS(app, resources={r"/api/*": {
    "origins": "*",
    "supports_credentials": True
}})
```

I need credentials support for cookie-based auth. Is this configuration correct?''',
        r'''<think>
Let me think about this CORS configuration...

`origins: "*"` allows ANY origin to make requests.
`supports_credentials: True` sends `Access-Control-Allow-Credentials: true` header, allowing cookies to be included.

But wait — the browser REJECTS this combination! The CORS spec says:
> If the response includes `Access-Control-Allow-Credentials: true`, the `Access-Control-Allow-Origin` header MUST NOT be `*`. It must be a specific origin.

This is a security protection built into browsers. If you could use wildcard + credentials, any website could make authenticated requests to your API using the user's cookies.

So this configuration either:
1. The browser ignores the credentials (cookies not sent) — breaking auth
2. Or flask-cors handles it by reflecting the request Origin header — which is equivalent to allowing ALL origins with credentials, a security disaster

Let me check what flask-cors does... Some CORS libraries automatically reflect the Origin header when credentials are needed. That means `evil.com` sends a request, and the API responds with `Access-Control-Allow-Origin: evil.com` — allowing the attack.

The fix: explicitly list allowed origins.
</think>

**The CORS spec forbids `Access-Control-Allow-Origin: *` with credentials. Some libraries work around this by reflecting the Origin header — which is even worse (allows all origins with credentials).**

### What happens

**Scenario 1** (strict browser enforcement):
```
Browser: "Can evil.com access this with cookies?"
Server: "Allow-Origin: *, Allow-Credentials: true"
Browser: "Spec violation — I'll block the cookies."
→ Auth breaks for legitimate requests too!
```

**Scenario 2** (library reflects Origin):
```
Browser: "Can evil.com access this with cookies?"
Server: "Allow-Origin: evil.com, Allow-Credentials: true"
Browser: "OK, sending cookies!"
→ evil.com can now make authenticated API calls as the user!
```

### Fix: whitelist specific origins
```python
CORS(app, resources={r"/api/*": {
    "origins": [
        "https://yourapp.com",
        "https://admin.yourapp.com",
        "http://localhost:3000"  # dev only
    ],
    "supports_credentials": True
}})
```

### The meta-lesson
CORS with credentials requires explicit origin whitelisting — wildcards are forbidden by the spec. If your CORS library silently "works" with `*` + credentials, it's probably reflecting the Origin header, which is equivalent to no CORS protection at all.'''
    ),
    (
        "thinking/meta-error-string-immutability-concat",
        r'''I wrote this function to build a large string efficiently:

```python
def build_report(records):
    report = ""
    report += "=== Report ===\n"
    for record in records:
        report += f"Name: {record['name']}\n"
        report += f"Email: {record['email']}\n"
        report += f"Score: {record['score']}\n"
        report += "---\n"
    report += "=== End ===\n"
    return report
```

With 100,000 records, this takes 30+ seconds. Why?''',
        r'''<think>
Python strings are immutable. Each `report += ...` creates a NEW string object:

1. `report = "" + "=== Report ===\n"` — creates new 16-char string
2. `report += f"Name: Alice\n"` — creates new 28-char string (copies old + new)
3. `report += f"Email: ...\n"` — creates new 50-char string (copies old + new)

Each concatenation copies the entire existing string. As the report grows, each concatenation copies more data:
- Iteration 1: copy ~50 bytes
- Iteration 1000: copy ~50,000 bytes
- Iteration 100,000: copy ~5,000,000 bytes

Total bytes copied: roughly proportional to n²/2 where n is the final string length.

With 100,000 records, each ~50 chars = 5,000,000 chars total. The sum of copies is about 5,000,000 * 100,000 / 2 = 250 billion character copies. That's O(n²).

Actually, CPython has an optimization for `s += t` when s has only one reference (refcount == 1) — it tries to extend the string in place. So in practice, CPython's optimization makes this faster than the theoretical O(n²). But it's still slow for very large strings and the optimization isn't guaranteed.

The fix: use `str.join()` or `io.StringIO`, which are O(n):

```python
parts = []
parts.append("=== Report ===")
for record in records:
    parts.append(f"Name: {record['name']}")
    ...
report = "\n".join(parts)
```

`join` allocates one string of the total size and copies each part once.
</think>

**String concatenation in a loop is O(n²) because Python strings are immutable — each `+=` copies the entire existing string.**

### Why it's slow
```python
# Each += creates a NEW string (copy old + append new):
report = ""                 # ""
report += "A" * 1000        # copies 1000 bytes
report += "B" * 1000        # copies 2000 bytes (old 1000 + new 1000)
report += "C" * 1000        # copies 3000 bytes
# ...
# Total copies: 1000 + 2000 + 3000 + ... + n*1000 = O(n²)
```

### Fix: list + join (O(n))
```python
def build_report(records):
    parts = ["=== Report ==="]
    for record in records:
        parts.append(f"Name: {record['name']}")
        parts.append(f"Email: {record['email']}")
        parts.append(f"Score: {record['score']}")
        parts.append("---")
    parts.append("=== End ===")
    return "\n".join(parts)
```

`join` calculates total length, allocates one string, and copies each part exactly once — O(n).

### Fix: io.StringIO (also O(n))
```python
from io import StringIO

def build_report(records):
    buf = StringIO()
    buf.write("=== Report ===\n")
    for record in records:
        buf.write(f"Name: {record['name']}\n")
        buf.write(f"Email: {record['email']}\n")
        buf.write(f"Score: {record['score']}\n")
        buf.write("---\n")
    buf.write("=== End ===\n")
    return buf.getvalue()
```

### Performance comparison (100K records)
| Method | Time |
|--------|------|
| `+=` in loop | ~30 seconds |
| `list + join` | ~0.1 seconds |
| `StringIO` | ~0.1 seconds |

### The meta-lesson
In any language with immutable strings (Python, Java, C#, Go), string concatenation in a loop is O(n²). Use a list/StringBuilder/buffer to collect parts, then join once at the end.'''
    ),
    (
        "thinking/meta-error-path-traversal-filename",
        r'''I wrote this file download endpoint:

```python
@app.get("/api/documents/{filename}")
def download_document(filename: str):
    filepath = os.path.join("/var/app/documents", filename)
    if os.path.exists(filepath):
        return FileResponse(filepath)
    return {"error": "Not found"}, 404
```

Simple file serving. Any security issues?''',
        r'''<think>
Classic path traversal vulnerability!

If `filename` is `../../etc/passwd`, then:
```
os.path.join("/var/app/documents", "../../etc/passwd")
= "/var/app/documents/../../etc/passwd"
= "/etc/passwd"  (after path resolution)
```

The attacker can read ANY file on the server by using `../` to escape the documents directory.

Even more dangerous paths:
- `../../etc/shadow` — password hashes
- `../../root/.ssh/id_rsa` — SSH private key
- `../../var/app/.env` — environment variables/secrets
- `../../../proc/self/environ` — process environment variables

The `os.path.join` doesn't prevent traversal — it just concatenates paths. And `os.path.exists` doesn't check if the path is within the allowed directory.

The fix: resolve the path and verify it starts with the allowed directory.
</think>

**Path traversal: `../../etc/passwd` as filename lets attackers read ANY file on the server.**

### The attack
```
GET /api/documents/../../etc/passwd
→ filepath = "/var/app/documents/../../etc/passwd"
→ resolves to "/etc/passwd"
→ FileResponse("/etc/passwd") — server's password file!

GET /api/documents/../.env
→ resolves to "/var/app/.env" — your secrets!
```

### Fix: resolve and validate the path
```python
@app.get("/api/documents/{filename}")
def download_document(filename: str):
    base_dir = os.path.realpath("/var/app/documents")
    filepath = os.path.realpath(os.path.join(base_dir, filename))

    # Verify the resolved path is within the allowed directory
    if not filepath.startswith(base_dir + os.sep):
        return {"error": "Invalid path"}, 400

    if os.path.exists(filepath):
        return FileResponse(filepath)
    return {"error": "Not found"}, 404
```

Key: `os.path.realpath()` resolves all `..`, symlinks, and relative paths to an absolute path. Then we verify it still starts with the base directory.

### Also sanitize the filename
```python
from werkzeug.utils import secure_filename

@app.get("/api/documents/{filename}")
def download_document(filename: str):
    safe_name = secure_filename(filename)  # strips ../, /, etc.
    if not safe_name:
        return {"error": "Invalid filename"}, 400
    filepath = os.path.join("/var/app/documents", safe_name)
    ...
```

### The meta-lesson
Never trust user-provided filenames or paths. `os.path.join()` does NOT prevent directory traversal — it just joins strings. Always: (1) resolve to absolute path with `realpath()`, (2) verify the result is within the allowed directory, (3) sanitize the filename to strip traversal sequences.'''
    ),
    (
        "thinking/meta-error-weak-password-hashing",
        r'''I store user passwords securely using hashing:

```python
import hashlib

def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(password, stored_hash):
    return hash_password(password) == stored_hash
```

SHA-256 is a strong hash. This is secure, right?''',
        r'''<think>
SHA-256 IS a strong cryptographic hash, but it's the WRONG tool for password hashing. Here's why:

1. **SHA-256 is designed to be FAST**: It can compute billions of hashes per second on modern GPUs. This is great for file integrity checking, but terrible for passwords. An attacker with a GPU can try billions of password guesses per second.

2. **No salt**: Without a salt, identical passwords produce identical hashes. If two users both use "password123", their hashes are identical. An attacker who cracks one gets both. Also enables rainbow table attacks — precomputed tables of hash→password mappings.

3. **No key stretching**: bcrypt/argon2 intentionally slow down hashing by running thousands of rounds. SHA-256 runs once — microseconds per hash.

Comparison:
- SHA-256: ~10 billion hashes/second on GPU
- bcrypt (cost=12): ~10,000 hashes/second on GPU
- argon2id: ~1,000 hashes/second (also memory-hard)

The difference: an attacker trying all 8-character alphanumeric passwords:
- SHA-256: cracked in hours
- bcrypt: cracked in centuries
- argon2id: cracked in millennia

The fix: use bcrypt or argon2id, which are purpose-built for password hashing with salting and key stretching built in.
</think>

**SHA-256 is a fast hash — exactly what you DON'T want for passwords. Attackers can try billions of guesses per second.**

### Why fast hashing is bad for passwords
```
SHA-256:   ~10,000,000,000 hashes/second (GPU)
bcrypt:    ~10,000 hashes/second (GPU)
argon2id:  ~1,000 hashes/second (GPU + memory-hard)
```

An attacker brute-forcing 8-character passwords:
- SHA-256: **hours**
- bcrypt: **centuries**

### Missing salt = rainbow tables
```python
hash_password("password123")
# Always returns the same hash! Pre-computed tables exist for common passwords.
# Also: two users with "password123" have identical hashes — crack one, get both.
```

### Fix: use bcrypt or argon2id
```python
import bcrypt

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)  # salt is auto-generated
    return bcrypt.hashpw(password.encode(), salt).decode()

def verify_password(password: str, stored_hash: str) -> bool:
    return bcrypt.checkpw(password.encode(), stored_hash.encode())
```

bcrypt automatically:
- Generates a unique salt per password
- Applies key stretching (thousands of rounds)
- Stores the salt in the hash output (self-contained)

### Password hashing hierarchy
| Algorithm | Status |
|-----------|--------|
| MD5/SHA-1/SHA-256 | WRONG — fast hashes, not for passwords |
| bcrypt | Good — battle-tested, widely supported |
| scrypt | Good — memory-hard |
| argon2id | Best — winner of Password Hashing Competition |

### The meta-lesson
"Strong hash" ≠ "good for passwords." SHA-256 is strong for integrity checking (making it hard to find collisions). Passwords need the opposite property: making it SLOW to verify guesses. Always use purpose-built password hashing (bcrypt, argon2id) that includes salting and intentional slowness.'''
    ),
    (
        "thinking/meta-error-select-star-production",
        r'''I wrote this database query:

```python
def get_users():
    return db.execute("SELECT * FROM users").fetchall()
```

Simple and works. Any issues with using SELECT * in production code?''',
        r'''<think>
`SELECT *` has several production issues:

1. **Fetches unnecessary data**: The users table might have columns like `password_hash`, `ssn`, `address`, `profile_photo_blob`. SELECT * fetches ALL of them, even if the caller only needs `id` and `name`. This wastes network bandwidth, memory, and DB I/O.

2. **Breaks when schema changes**: If someone adds a column to the users table, SELECT * returns a different number of columns. Code that unpacks results by position (`id, name, email = row`) breaks. Code that uses column names (`row['name']`) is safer but still fetches unnecessary data.

3. **Security — leaks sensitive data**: SELECT * includes `password_hash`, `api_key`, and other sensitive columns. If this data is serialized to JSON and returned to the client, you've got a data breach. Even if you filter in Python, the sensitive data traveled over the network from DB to app.

4. **Performance — prevents covering indexes**: If you only need `id` and `name`, a query `SELECT id, name FROM users` can be served entirely from an index (covering index), never touching the main table. `SELECT *` forces a full table read.

5. **Column ordering dependency**: The column order of SELECT * depends on the table definition. If columns are reordered, code that depends on position breaks.

The fix: always specify the columns you need.
</think>

**`SELECT *` in production code wastes bandwidth, leaks sensitive columns, breaks on schema changes, and prevents index-only scans.**

### The problems

**1. Leaks sensitive data:**
```python
users = db.execute("SELECT * FROM users").fetchall()
# Each row now contains: password_hash, ssn, api_key, etc.
# If serialized to JSON response → data breach!
```

**2. Wastes resources:**
```sql
-- You need id and name. SELECT * also fetches:
-- profile_photo (BYTEA, 5MB each), bio (TEXT, 10KB each),
-- address, phone, ssn, password_hash, api_key, ...
```

**3. Breaks on schema changes:**
```python
# Code written assuming 5 columns:
id, name, email, role, created = row  # works today

# Someone adds a column:
# ValueError: too many values to unpack
```

**4. Prevents covering indexes:**
```sql
-- Can use index-only scan (fast):
SELECT id, name FROM users WHERE name LIKE 'A%';

-- Must read full table (slow):
SELECT * FROM users WHERE name LIKE 'A%';
```

### Fix: explicit column selection
```python
def get_users():
    return db.execute(
        "SELECT id, name, email, role, created_at FROM users"
    ).fetchall()

# Even better with ORM:
def get_users():
    return db.query(User.id, User.name, User.email).all()
```

### The meta-lesson
`SELECT *` is fine for ad-hoc queries and debugging. In production code, always specify the columns you need. This documents what data the code uses, prevents accidental sensitive data exposure, enables query optimization, and makes the code resilient to schema changes.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
