"""Phase 4B: Self-Improvement — Self-Evaluation (Part 8)

Evaluating own security recommendations for completeness and accuracy.
"""

PAIRS = [
    (
        "thinking/auto-selfeval-security-password-storage",
        r'''A user asked how to store passwords in their database. I'm about to suggest this approach. Let me verify it's secure:

My draft: "Hash the password with SHA-256 before storing it: hashlib.sha256(password.encode()).hexdigest(). Never store plaintext passwords."''',
        r'''<think>
Let me evaluate my password storage recommendation:

**What's correct:**
- Never store plaintext passwords ✓
- Using a hash function ✓

**What's WRONG:**
1. **SHA-256 is NOT suitable for password hashing.**
   - SHA-256 is a general-purpose hash designed to be FAST
   - Fast hashes are bad for passwords — attackers can try billions per second
   - GPU-based attacks can check ~10 billion SHA-256 hashes per second
   - A 6-character password can be brute-forced in under 1 second

2. **No salt.**
   - Without a salt, identical passwords produce identical hashes
   - An attacker with a rainbow table can crack all common passwords instantly
   - Two users with password "password123" would have the same hash

3. **No key stretching / iterations.**
   - Password hashing should be deliberately slow (100ms+ per hash)
   - This makes brute-force attacks infeasible

**What I should recommend:**
- bcrypt (most common, widely supported)
- Argon2 (winner of the Password Hashing Competition, best for new projects)
- scrypt (alternative to bcrypt)

**NEVER for passwords:** MD5, SHA-1, SHA-256, SHA-512 (all too fast)

**Verdict:** My recommendation is actively dangerous. SHA-256 passwords can be cracked in minutes.
</think>

**Self-evaluation: DANGEROUS recommendation. SHA-256 is NOT suitable for password hashing. Rating: 1/10.**

**Why SHA-256 is wrong for passwords:**
| Factor | SHA-256 | bcrypt | Argon2 |
|--------|---------|--------|--------|
| Speed | 10 billion/sec on GPU | ~100/sec | ~10/sec |
| Built-in salt | No | Yes | Yes |
| Adjustable cost | No | Yes | Yes |
| Time to crack 8-char password | Minutes | Centuries | Centuries |

**What I should recommend:**

```python
# CORRECT: Use bcrypt (most widely supported)
import bcrypt

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt(rounds=12)  # Cost factor 12 = ~250ms per hash
    return bcrypt.hashpw(password.encode(), salt).decode()

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())

# Usage:
stored_hash = hash_password("user_password")
# stored_hash = "$2b$12$LJ3m4ys3Lg..." (includes salt + cost + hash)

is_valid = verify_password("user_password", stored_hash)  # True
```

```python
# EVEN BETTER: Use Argon2 (recommended for new projects)
from argon2 import PasswordHasher

ph = PasswordHasher(
    time_cost=3,      # Number of iterations
    memory_cost=65536, # 64MB memory per hash (resists GPU attacks)
    parallelism=4
)

hashed = ph.hash("user_password")
is_valid = ph.verify(hashed, "user_password")  # True
```

**Password storage rules:**
1. Use bcrypt or Argon2 (NEVER SHA-256, MD5, or SHA-1)
2. Use a unique salt per password (bcrypt/Argon2 do this automatically)
3. Set cost factor high enough for ~250ms per hash
4. Never implement your own password hashing
5. Use constant-time comparison to prevent timing attacks

**Self-evaluation lesson:** Security recommendations require extra care because a wrong answer creates vulnerabilities. Always verify against current best practices (OWASP) before suggesting security-related code.'''
    ),
    (
        "thinking/auto-selfeval-security-sql-injection",
        r'''I wrote this code to handle user login. Let me check it for SQL injection vulnerabilities before suggesting it:

My draft:
```python
@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
    user = db.execute(query).fetchone()
    if user:
        session['user_id'] = user['id']
        return redirect('/dashboard')
    return "Invalid credentials", 401
```''',
        r'''<think>
Let me audit this code for security issues:

**CRITICAL: SQL Injection vulnerability**
The query uses f-string formatting to insert user input directly into SQL:
```python
query = f"SELECT * FROM users WHERE username = '{username}' AND password = '{password}'"
```

An attacker can input:
- username: `' OR '1'='1' --`
- The query becomes: `SELECT * FROM users WHERE username = '' OR '1'='1' --' AND password = ''`
- The `--` comments out the rest, and `'1'='1'` is always true
- This returns ALL users, logging the attacker in as the first user (usually admin)

**CRITICAL: Plaintext password comparison**
The code compares the password directly: `AND password = '{password}'`
This means passwords are stored in plaintext in the database.

**CRITICAL: No rate limiting**
No protection against brute-force login attempts.

**ISSUE: No CSRF protection**
POST form without CSRF token.

**ISSUE: Generic error message is actually good here**
"Invalid credentials" doesn't reveal whether the username exists — this is correct.

**Security issues found: 3 critical, 1 moderate**
This code would allow an attacker to bypass authentication entirely.
</think>

**Self-evaluation: THREE critical security vulnerabilities. This code must NOT be deployed. Rating: 0/10.**

**Vulnerability 1: SQL Injection (CRITICAL)**
```python
# Attacker inputs username: ' OR '1'='1' --
# Your query becomes:
SELECT * FROM users WHERE username = '' OR '1'='1' --' AND password = ''
# Returns ALL users — attacker logs in as admin!
```

**Vulnerability 2: Plaintext passwords (CRITICAL)**
```python
# Passwords stored and compared as plaintext
AND password = '{password}'
# If database is breached, ALL passwords are exposed
```

**Vulnerability 3: No brute-force protection (HIGH)**
An attacker can try millions of password combinations with no throttling.

**Secure version:**
```python
import bcrypt
from flask_limiter import Limiter

limiter = Limiter(app, default_limits=["5 per minute"])

@app.route('/login', methods=['POST'])
@limiter.limit("5 per minute")  # Rate limit login attempts
def login():
    username = request.form.get('username', '')
    password = request.form.get('password', '')

    if not username or not password:
        return "Invalid credentials", 401

    # Parameterized query — SQL injection is IMPOSSIBLE:
    user = db.execute(
        "SELECT * FROM users WHERE username = ?",  # ? placeholder
        (username,)                                  # Parameters passed separately
    ).fetchone()

    if user and bcrypt.checkpw(password.encode(), user['password_hash'].encode()):
        session['user_id'] = user['id']
        session.regenerate()  # Prevent session fixation
        return redirect('/dashboard')

    # Same message whether username or password is wrong:
    return "Invalid credentials", 401
```

**Security comparison:**
| Issue | My draft | Fixed version |
|-------|----------|--------------|
| SQL injection | f-string formatting | Parameterized query |
| Password storage | Plaintext | bcrypt hash |
| Brute force | No protection | Rate limited (5/min) |
| Session fixation | Not addressed | Session regenerated |

**Self-evaluation lesson:** NEVER use f-strings or string formatting to build SQL queries. This is the number one web security vulnerability (OWASP #1). Always use parameterized queries.'''
    ),
    (
        "thinking/auto-selfeval-security-jwt-implementation",
        r'''I implemented JWT authentication for an API. Let me audit my own code before deploying:

My code:
```python
import jwt

SECRET = "mysecretkey123"

def create_token(user_id):
    return jwt.encode({"user_id": user_id}, SECRET)

def get_current_user(request):
    token = request.headers.get("Authorization")
    data = jwt.decode(token, SECRET, algorithms=["HS256"])
    return data["user_id"]
```''',
        r'''<think>
Let me audit this JWT implementation:

**Issue 1: Hardcoded secret key**
`SECRET = "mysecretkey123"` — This is in source code, will be committed to git, and is a weak secret.
- Anyone with access to the repo can forge tokens
- "mysecretkey123" is trivially guessable
- Should be loaded from environment variables
- Should be at least 256 bits of randomness

**Issue 2: No token expiration**
`jwt.encode({"user_id": user_id}, SECRET)` — No `exp` claim
- Tokens are valid FOREVER
- If a token is stolen, it can never be invalidated
- This is equivalent to a permanent password

**Issue 3: No error handling**
`jwt.decode(token, SECRET, algorithms=["HS256"])` — No try/except
- Invalid tokens will crash the application (500 error)
- Expired tokens will crash instead of returning 401
- Missing Authorization header will crash

**Issue 4: Authorization header not parsed correctly**
`request.headers.get("Authorization")` — Doesn't strip "Bearer " prefix
- Standard format is "Bearer <token>"
- The code would try to decode "Bearer eyJhbG..." which would fail

**Issue 5: No token type validation**
No check that the token is the right type (access vs refresh)

**Issue 6: Algorithm not specified in encode**
`jwt.encode({"user_id": user_id}, SECRET)` — relies on library default
- Explicit is better than implicit for security

**Security issues found: 6 (2 critical, 2 high, 2 medium)**
</think>

**Self-evaluation: 6 security issues found. This JWT implementation is insecure. Rating: 2/10.**

**Issues found:**

| # | Issue | Severity | Risk |
|---|-------|----------|------|
| 1 | Hardcoded weak secret | Critical | Anyone can forge tokens |
| 2 | No token expiration | Critical | Stolen tokens valid forever |
| 3 | No error handling | High | App crashes on invalid tokens |
| 4 | Authorization header not parsed | High | All requests fail |
| 5 | No algorithm in encode | Medium | Relies on library defaults |
| 6 | No token type claim | Medium | Token confusion attacks |

**Secure version:**
```python
import jwt
import os
from datetime import datetime, timedelta
from functools import wraps
from flask import request, jsonify

# Load secret from environment (never hardcode!)
SECRET = os.environ['JWT_SECRET']  # Must be set in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE = timedelta(minutes=15)

def create_token(user_id, role="user"):
    payload = {
        "sub": user_id,
        "role": role,
        "type": "access",
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + ACCESS_TOKEN_EXPIRE,
    }
    return jwt.encode(payload, SECRET, algorithm=ALGORITHM)

def get_current_user(request):
    auth_header = request.headers.get("Authorization", "")

    if not auth_header.startswith("Bearer "):
        raise AuthError("Missing or malformed Authorization header", 401)

    token = auth_header[7:]  # Strip "Bearer " prefix

    try:
        payload = jwt.decode(token, SECRET, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise AuthError("Token has expired", 401)
    except jwt.InvalidTokenError:
        raise AuthError("Invalid token", 401)

    if payload.get("type") != "access":
        raise AuthError("Invalid token type", 401)

    return payload["sub"]

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        try:
            user_id = get_current_user(request)
            request.user_id = user_id
        except AuthError as e:
            return jsonify({"error": str(e)}), e.status_code
        return f(*args, **kwargs)
    return decorated
```

**Generate a proper secret:**
```bash
# Generate a 256-bit random secret:
python -c "import secrets; print(secrets.token_hex(32))"
# Set it as an environment variable, NEVER in code
export JWT_SECRET="a1b2c3d4e5f6..."
```

**Self-evaluation lesson:** JWT implementations have many subtle security requirements. Always check: secret from env, short expiration, error handling, proper header parsing, and explicit algorithm specification.'''
    ),
    (
        "thinking/auto-selfeval-security-file-upload",
        r'''I built a file upload endpoint. Let me check it for security issues:

My code:
```python
@app.route('/upload', methods=['POST'])
def upload_file():
    file = request.files['file']
    filename = file.filename
    file.save(os.path.join('/var/www/uploads', filename))
    return jsonify({"url": f"/uploads/{filename}"})
```''',
        r'''<think>
Let me audit this file upload code:

**Issue 1: Path traversal attack**
`filename = file.filename` — The filename comes from the user and is not sanitized.
An attacker can send: `filename = "../../etc/cron.d/backdoor"`
This would save the file to `/etc/cron.d/backdoor` instead of the uploads directory, potentially executing arbitrary code.

**Issue 2: No file type validation**
Any file type is accepted — including:
- `.php`, `.py`, `.sh` — executable scripts
- `.html` with XSS — stored XSS attacks
- `.svg` with JavaScript — another XSS vector
- Malware and viruses

**Issue 3: No file size limit**
An attacker could upload a 100GB file, filling the disk and crashing the server.

**Issue 4: Predictable filenames**
Using the original filename means:
- Attackers can overwrite existing files
- Filenames may contain special characters that break the filesystem
- Users can discover other users' uploaded files by guessing filenames

**Issue 5: Files served from web root**
Saving to `/var/www/uploads` means files might be directly executable by the web server. If someone uploads `shell.php`, visiting `/uploads/shell.php` could execute it.

**Issue 6: No authentication**
Anyone can upload files without being logged in.

**Security issues found: 6 (3 critical, 2 high, 1 medium)**
</think>

**Self-evaluation: 6 security vulnerabilities, 3 critical. This upload endpoint is extremely dangerous. Rating: 0/10.**

**Attack scenarios:**

```bash
# Attack 1: Path traversal — write to any location
curl -F 'file=@evil.sh;filename=../../etc/cron.d/backdoor' /upload
# Writes a cron job that runs attacker's code!

# Attack 2: Web shell — execute arbitrary code
curl -F 'file=@shell.php' /upload
# Then visit /uploads/shell.php — attacker has server access

# Attack 3: Disk exhaustion
dd if=/dev/zero bs=1M count=100000 | curl -F 'file=@-' /upload
# 100GB upload fills the disk
```

**Secure version:**
```python
import os
import uuid
from werkzeug.utils import secure_filename

UPLOAD_DIR = '/var/data/uploads'  # Outside web root!
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'docx'}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB

app.config['MAX_CONTENT_LENGTH'] = MAX_FILE_SIZE  # Flask enforces this

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/upload', methods=['POST'])
@require_auth  # Must be logged in
def upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files['file']

    if not file.filename:
        return jsonify({"error": "No file selected"}), 400

    if not allowed_file(file.filename):
        return jsonify({"error": "File type not allowed"}), 400

    # Generate random filename (prevents overwrite and path traversal):
    ext = secure_filename(file.filename).rsplit('.', 1)[1].lower()
    safe_filename = f"{uuid.uuid4().hex}.{ext}"

    # Verify the file content matches the extension:
    file_header = file.read(8)
    file.seek(0)
    if not verify_file_magic(file_header, ext):
        return jsonify({"error": "File content doesn't match extension"}), 400

    filepath = os.path.join(UPLOAD_DIR, safe_filename)
    file.save(filepath)

    return jsonify({"url": f"/api/files/{safe_filename}"}), 201

# Serve files through the app (not directly from filesystem):
@app.route('/api/files/<filename>')
def serve_file(filename):
    safe = secure_filename(filename)
    return send_from_directory(UPLOAD_DIR, safe)
```

**Security fixes applied:**
| Issue | Before | After |
|-------|--------|-------|
| Path traversal | User-controlled filename | UUID random filename |
| File type | Any file accepted | Whitelist + magic byte check |
| File size | No limit | 10MB max |
| Overwrite | Same filename overwrites | UUID prevents collisions |
| Web shell | Files in web root | Files outside web root, served via app |
| Authentication | None | Login required |

**Self-evaluation lesson:** File uploads are one of the most dangerous features in web applications. Every piece of user input (filename, content, size) is an attack vector.'''
    ),
    (
        "thinking/auto-selfeval-security-env-vars",
        r'''I wrote a deployment guide that includes this step. Let me check if it has security issues:

My draft: "Create a .env file in your project root with these values:
DATABASE_URL=postgresql://admin:P@ssw0rd123@db.example.com:5432/myapp
SECRET_KEY=django-insecure-key-change-me-later
AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
STRIPE_SECRET_KEY=sk_live_EXAMPLE_REPLACE_ME"''',
        r'''<think>
Let me evaluate this deployment guide for security:

**Issue 1: Real-looking credentials in documentation**
These look like real credentials (especially the AWS keys which follow the exact AWS format). Even if they're examples:
- Someone might copy-paste them into their own .env
- The AWS key format (AKIA...) might trigger credential scanners to flag the repo
- The Stripe key starts with sk_live_ (LIVE key, not test key)

**Issue 2: No mention of .gitignore**
The guide says "create a .env file" but doesn't say to add it to .gitignore. If the user commits this file, all credentials are leaked to the repository (and potentially GitHub, where bots scrape for exposed keys within seconds).

**Issue 3: "change-me-later" in SECRET_KEY**
`django-insecure-key-change-me-later` — users will forget to change it. "Later" never comes.

**Issue 4: Database password in plaintext**
`P@ssw0rd123` — weak password, and stored in plaintext in a file

**Issue 5: No mention of credential rotation**
No guidance on how often to rotate these keys or what to do if they're leaked.

**Issue 6: No distinction between dev and production**
Using `sk_live_` (Stripe live key) in development could result in real charges. Should use `sk_test_` for development.

**Verdict: This guide will lead to credential leaks. Rating: 2/10.**
</think>

**Self-evaluation: This guide will lead to credential leaks and security breaches. Rating: 2/10.**

**Critical issues:**

| Issue | Risk |
|-------|------|
| No .gitignore mention | Credentials committed to git |
| Real-looking AWS keys | Might be flagged or accidentally used |
| sk_live_ Stripe key | Real charges in development |
| "change-me-later" | Users won't change it |
| No rotation guidance | Stale credentials |

**What I should write instead:**

"**Step 1: Create .gitignore first (CRITICAL)**
```bash
# Add .env to .gitignore BEFORE creating it:
echo '.env' >> .gitignore
git add .gitignore
git commit -m 'Ensure .env is never committed'
```

**Step 2: Create .env from template**
```bash
# Copy the template:
cp .env.example .env
```

**.env.example (commit this — no real values):**
```bash
# Database
DATABASE_URL=postgresql://user:password@localhost:5432/myapp_dev

# Django secret key — generate with:
# python -c \"import secrets; print(secrets.token_urlsafe(50))\"
SECRET_KEY=GENERATE_A_REAL_KEY_SEE_ABOVE

# AWS (use IAM roles in production instead of keys)
AWS_ACCESS_KEY_ID=your-access-key-here
AWS_SECRET_ACCESS_KEY=your-secret-key-here

# Stripe (use TEST keys for development!)
STRIPE_SECRET_KEY=sk_test_your_test_key_here
```

**.env (never commit this):**
```bash
DATABASE_URL=postgresql://myuser:$(generate_strong_password)@db.example.com:5432/myapp
SECRET_KEY=$(python -c 'import secrets; print(secrets.token_urlsafe(50))')
AWS_ACCESS_KEY_ID=<your real key>
AWS_SECRET_ACCESS_KEY=<your real key>
STRIPE_SECRET_KEY=sk_test_<your test key>  # Use sk_live_ ONLY in production
```

**Step 3: Verify .env is not tracked**
```bash
git status  # .env should NOT appear
git log --all --full-history -- .env  # Should return nothing
```

**Production: Use a secrets manager instead of .env files:**
- AWS: Secrets Manager or SSM Parameter Store
- GCP: Secret Manager
- Azure: Key Vault
- Kubernetes: Secrets (or external-secrets operator)
"

**Self-evaluation lesson:** Deployment guides with credentials are one of the most common sources of security breaches. Always: provide a template with fake values, enforce .gitignore, and recommend secrets managers for production.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
