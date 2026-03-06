r"""Thinking-trace pairs: security code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this authentication code and identify security issues:

```python
import hashlib
import jwt
import time
from flask import Flask, request, jsonify
from functools import wraps

app = Flask(__name__)
SECRET_KEY = "my-secret-key-do-not-share"

def hash_password(password):
    return hashlib.md5(password.encode()).hexdigest()

def verify_password(password, hashed):
    return hash_password(password) == hashed

def create_token(user_id, role):
    payload = {
        "user_id": user_id,
        "role": role,
        "exp": time.time() + 86400 * 30
    }
    return jwt.encode(payload, SECRET_KEY, algorithm="HS256")

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get("Authorization", "").replace("Bearer ", "")
        if not token:
            return jsonify({"error": "No token"}), 401
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            request.user_id = payload["user_id"]
            request.user_role = payload["role"]
        except:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated

def require_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if request.user_role != "admin":
            return jsonify({"error": "Admin required"}), 403
        return f(*args, **kwargs)
    return decorated

@app.route("/api/register", methods=["POST"])
def register():
    data = request.get_json()
    username = data["username"]
    email = data["email"]
    password = data["password"]

    hashed = hash_password(password)
    user = db.create_user(username, email, hashed)
    token = create_token(user.id, user.role)

    return jsonify({"token": token, "user": {"id": user.id, "email": email}})

@app.route("/api/login", methods=["POST"])
def login():
    data = request.get_json()
    email = data["email"]
    password = data["password"]

    user = db.get_user_by_email(email)
    if not user:
        return jsonify({"error": "Invalid credentials"}), 401

    if not verify_password(password, user.password_hash):
        return jsonify({"error": "Invalid credentials"}), 401

    token = create_token(user.id, user.role)
    return jsonify({"token": token})

@app.route("/api/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json()
    email = data["email"]
    user = db.get_user_by_email(email)
    if user:
        new_password = "temp" + str(int(time.time()))[-4:]
        user.password_hash = hash_password(new_password)
        db.save(user)
        send_email(email, f"Your new password is: {new_password}")
    return jsonify({"message": "If the email exists, a reset link was sent"})
```''', r'''<think>
This authentication code has numerous severe security vulnerabilities. Let me go through each one.

Password hashing:
- Using MD5 for password hashing. MD5 is cryptographically broken and can be brute-forced at billions of hashes per second with modern hardware. Rainbow tables exist for common MD5 hashes.
- No salt. Identical passwords produce identical hashes, enabling rainbow table attacks and revealing when two users share the same password.
- Should use bcrypt, argon2, or scrypt with automatic salting.

JWT issues:
- SECRET_KEY is hardcoded in source code ("my-secret-key-do-not-share"). This will be in version control.
- Token expiry is 30 days (86400 * 30). This is extremely long. If a token is compromised, it remains valid for a month.
- exp uses time.time() (Unix timestamp as float) but JWT standard expects integer. Some JWT libraries may handle this, but it could cause issues.
- No token refresh mechanism. Users must re-login every 30 days.
- No token revocation mechanism. If a user changes their password or is banned, existing tokens remain valid.
- Role is stored in the token. If a user's role changes, existing tokens still carry the old role.

Authentication:
- require_auth uses bare except, catching all exceptions including non-JWT errors like MemoryError.
- The token is extracted with a simple string replace, which would fail if "Bearer" is lowercase or missing the space.
- No rate limiting on login endpoint - vulnerable to brute force attacks.
- No account lockout after failed attempts.

Password reset:
- Generates a predictable temporary password: "temp" + last 4 digits of current timestamp. An attacker who knows when the reset was requested can guess the password (only 10000 possibilities for the last 4 digits of a timestamp).
- Sends the new password in plaintext via email instead of a time-limited reset link.
- The response message tries to prevent user enumeration ("If the email exists...") but the behavior differs: it only sends an email if the user exists. Timing differences could reveal whether the email exists.

Input validation:
- No validation of username, email, or password format/strength.
- data["username"] will raise KeyError if not provided, returning a 500 error instead of 400.
- No CSRF protection.
- No password complexity requirements.

Other:
- verify_password uses == for string comparison, which is vulnerable to timing attacks. Should use hmac.compare_digest.
</think>

## Code Review: Authentication System

### CRITICAL - MD5 Password Hashing Without Salt
`hashlib.md5(password.encode()).hexdigest()` is catastrophically insecure. MD5 can be brute-forced at billions of hashes per second. No salt means identical passwords produce identical hashes, and precomputed rainbow tables can crack most passwords instantly.

**Fix:** Use bcrypt or argon2:
```python
import bcrypt

def hash_password(password):
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def verify_password(password, hashed):
    return bcrypt.checkpw(password.encode(), hashed.encode())
```

### CRITICAL - Predictable Password Reset
The temporary password `"temp" + str(int(time.time()))[-4:]` has only 10,000 possible values for any given second. An attacker who triggers a reset and knows the approximate time can brute-force the new password within seconds.

**Fix:** Use a cryptographically secure time-limited reset token instead of generating a new password:
```python
import secrets

def reset_password():
    token = secrets.token_urlsafe(32)
    # Store token with expiry in database
    # Send reset link, not password
    send_email(email, f"Reset: https://app.com/reset?token={token}")
```

### CRITICAL - Hardcoded Secret Key
`SECRET_KEY = "my-secret-key-do-not-share"` is in source code and will be committed to version control. Anyone with repo access can forge JWT tokens for any user, including admin.

**Fix:** `SECRET_KEY = os.environ["JWT_SECRET_KEY"]`

### HIGH - 30-Day Token Expiry With No Revocation
Tokens are valid for 30 days and cannot be revoked. If a token is stolen, an attacker has a month-long window. If a user changes their password or is banned, existing tokens remain valid.

**Fix:** Reduce expiry to 15-60 minutes and implement refresh tokens:
```python
def create_token(user_id, role):
    return jwt.encode({
        "user_id": user_id,
        "role": role,
        "exp": int(time.time()) + 900  # 15 minutes
    }, SECRET_KEY, algorithm="HS256")
```

### HIGH - Role Embedded in Token
Storing `role` in the JWT means role changes do not take effect until the token expires. An admin who is demoted retains admin access for up to 30 days.

**Fix:** Look up the role from the database on each request, or use short-lived tokens.

### HIGH - Timing Attack on Password Verification
`hash_password(password) == hashed` uses Python's string equality, which short-circuits on the first different character. This enables timing attacks to gradually determine the hash.

**Fix:**
```python
import hmac
def verify_password(password, hashed):
    return hmac.compare_digest(hash_password(password), hashed)
```

### HIGH - No Rate Limiting on Login
The login endpoint has no rate limiting or account lockout. An attacker can attempt unlimited password guesses against any account.

### MEDIUM - No Input Validation
No checks on email format, password strength, or username length. `data["email"]` raises an unhandled KeyError (500 response) if missing.

**Fix:** Validate all inputs and use `data.get()` with proper error responses.

### MEDIUM - Bare Except in require_auth
`except:` catches everything including SystemExit and KeyboardInterrupt. Use `except jwt.InvalidTokenError:` for specific JWT errors.

### LOW - Password Sent in Plaintext Email
The reset endpoint sends the new password in the email body. Email is not encrypted end-to-end, so the password is visible in transit and in email server logs.'''),

    ("thinking/code-review", r'''Review this input validation and sanitization code:

```python
import re
import html
import sqlite3
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)
DB_PATH = "app.db"

def get_db():
    return sqlite3.connect(DB_PATH)

def sanitize_input(text):
    return text.replace("'", "''").replace(";", "")

@app.route("/api/search")
def search():
    query = request.args.get("q", "")
    sanitized = sanitize_input(query)

    db = get_db()
    results = db.execute(
        f"SELECT * FROM products WHERE name LIKE '%{sanitized}%'"
    ).fetchall()

    return jsonify({"results": results})

@app.route("/api/users/<username>")
def get_user_profile(username):
    db = get_db()
    user = db.execute(
        f"SELECT * FROM users WHERE username = '{sanitize_input(username)}'"
    ).fetchone()

    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify({"user": dict(zip(["id", "username", "email", "bio"], user))})

@app.route("/api/comment", methods=["POST"])
def add_comment():
    data = request.get_json()
    comment_text = data.get("text", "")
    user_id = data.get("user_id")

    db = get_db()
    db.execute(
        f"INSERT INTO comments (user_id, text) VALUES ({user_id}, '{comment_text}')"
    )
    db.commit()

    return jsonify({"status": "created"}), 201

@app.route("/profile/<username>")
def render_profile(username):
    db = get_db()
    user = db.execute(
        f"SELECT * FROM users WHERE username = '{sanitize_input(username)}'"
    ).fetchone()

    if user:
        template = f"""
        <h1>Profile: {user[1]}</h1>
        <p>Bio: {user[3]}</p>
        <div class="comments">
            {{% for comment in comments %}}
            <p>{{{{ comment }}}}</p>
            {{% endfor %}}
        </div>
        """
        comments = db.execute(
            f"SELECT text FROM comments WHERE user_id = {user[0]}"
        ).fetchall()
        return render_template_string(
            template, comments=[c[0] for c in comments]
        )

    return "Not found", 404

@app.route("/api/file")
def serve_file():
    filename = request.args.get("name", "")
    filepath = f"/var/www/uploads/{filename}"
    return app.send_static_file(filepath)

@app.route("/api/redirect")
def redirect_user():
    url = request.args.get("url", "/")
    return redirect(url)
```''', r'''<think>
This code is a textbook example of nearly every major web security vulnerability. Let me catalog them.

SQL Injection:
- sanitize_input is completely inadequate. It only replaces single quotes with doubled quotes and removes semicolons. This does not prevent SQL injection. The attacker can use double quotes, UNION-based injection, boolean blind injection, or many other techniques that do not require single quotes or semicolons.
- Even with the sanitization, the queries still use f-string formatting. The search endpoint, user profile, comments, and profile render all construct SQL dynamically.
- add_comment does not even call sanitize_input on comment_text or user_id. user_id is directly interpolated into SQL without any type checking or sanitization.

XSS (Cross-Site Scripting):
- render_profile uses render_template_string with user data (user[1], user[3]) directly interpolated into the template string BEFORE Jinja2 processes it. This means the data bypasses Jinja2's auto-escaping. If user[3] (bio) contains JavaScript, it will execute.
- The template uses {{ comment }} inside Jinja2, which IS auto-escaped. But the bio field is not.
- Even worse, since user data is interpolated into the template string itself, an attacker could inject Jinja2 template syntax (SSTI - Server-Side Template Injection), potentially achieving remote code execution.

Path Traversal:
- serve_file takes a filename from user input and constructs a path: f"/var/www/uploads/{filename}". An attacker can use "../../etc/passwd" to read arbitrary files on the server.

Open Redirect:
- redirect_user takes a URL from user input and redirects to it. An attacker can craft a URL like /api/redirect?url=https://evil.com to redirect users to a phishing site while the link appears to come from the legitimate domain.

Other issues:
- No CSRF protection on POST endpoints
- No authentication required for add_comment - anyone can post as any user_id
- No Content-Type validation on incoming requests
- Database connections are not properly closed
- SELECT * returns all columns including potentially sensitive ones
</think>

## Code Review: Input Validation and Sanitization

### CRITICAL - SQL Injection in Every Endpoint
The `sanitize_input` function is entirely ineffective. Replacing single quotes and removing semicolons does not prevent SQL injection. Attackers can use UNION-based injection, boolean blind injection, or techniques that do not require these characters. The `add_comment` endpoint does not even use `sanitize_input` at all -- `user_id` and `comment_text` are directly interpolated.

**Exploit example for add_comment:**
```
user_id: "1; DROP TABLE users; --"
```

**Fix:** Use parameterized queries for ALL database operations:
```python
@app.route("/api/search")
def search():
    query = request.args.get("q", "")
    db = get_db()
    results = db.execute(
        "SELECT id, name, price FROM products WHERE name LIKE ?",
        (f"%{query}%",)
    ).fetchall()
    return jsonify({"results": results})
```

### CRITICAL - Server-Side Template Injection (SSTI)
`render_profile` interpolates user data directly into a Jinja2 template string before passing it to `render_template_string`. This is not just XSS -- it is SSTI. An attacker who controls the bio field can inject Jinja2 syntax to execute arbitrary Python code on the server.

**Exploit:** Set bio to `{{ config.items() }}` to dump app config, or `{{ ''.__class__.__mro__[1].__subclasses__() }}` for remote code execution.

**Fix:** Never interpolate user data into template strings. Pass all user data as template context variables:
```python
template = """
<h1>Profile: {{ username }}</h1>
<p>Bio: {{ bio }}</p>
"""
return render_template_string(template, username=user[1], bio=user[3], comments=...)
```

### CRITICAL - Path Traversal in File Serving
`serve_file` constructs a file path from user input: `f"/var/www/uploads/{filename}"`. An attacker can request `?name=../../etc/passwd` to read any file on the server.

**Fix:** Validate the filename and use `secure_filename`:
```python
from werkzeug.utils import secure_filename
import os

@app.route("/api/file")
def serve_file():
    filename = secure_filename(request.args.get("name", ""))
    filepath = os.path.join("/var/www/uploads", filename)
    if not os.path.abspath(filepath).startswith("/var/www/uploads"):
        return "Forbidden", 403
    return send_from_directory("/var/www/uploads", filename)
```

### HIGH - Open Redirect
`redirect_user` redirects to any URL provided by the user, enabling phishing attacks where the malicious link appears to originate from the legitimate domain.

**Fix:** Validate that the redirect URL is relative or on an allowed domain:
```python
from urllib.parse import urlparse

@app.route("/api/redirect")
def redirect_user():
    url = request.args.get("url", "/")
    parsed = urlparse(url)
    if parsed.netloc and parsed.netloc != "myapp.com":
        return "Invalid redirect", 400
    return redirect(url)
```

### HIGH - No Authentication on Comment Endpoint
`add_comment` accepts `user_id` from the request body with no authentication. Anyone can post comments as any user.

### MEDIUM - Database Connections Never Closed
`get_db()` creates a new SQLite connection on every request but never closes it. This leaks file descriptors.

**Fix:** Use Flask's `g` object and `teardown_appcontext`:
```python
from flask import g

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()
```

### MEDIUM - No CSRF Protection
POST endpoints have no CSRF token validation. An attacker can create a form on their site that submits comments to this application on behalf of logged-in users.'''),

    ("thinking/code-review", r'''Review this API key and secrets management code:

```python
import os
import hashlib
import hmac
import base64
import json
import time
from cryptography.fernet import Fernet

API_KEYS = {
    "client_a": "sk_live_abc123def456",
    "client_b": "sk_live_xyz789ghi012",
    "internal": "sk_live_internal_key_999"
}

ENCRYPTION_KEY = b"my-32-byte-encryption-key-here!!"
SIGNING_SECRET = "webhook-signing-secret-42"

class SecretsManager:
    def __init__(self):
        self.cipher = Fernet(base64.urlsafe_b64encode(ENCRYPTION_KEY))

    def encrypt(self, plaintext):
        return self.cipher.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext):
        return self.cipher.decrypt(ciphertext.encode()).decode()

    def store_secret(self, name, value):
        encrypted = self.encrypt(value)
        with open("secrets.json", "r+") as f:
            secrets = json.load(f)
            secrets[name] = encrypted
            f.seek(0)
            json.dump(secrets, f)
            f.truncate()

    def get_secret(self, name):
        with open("secrets.json") as f:
            secrets = json.load(f)
            return self.decrypt(secrets[name])

def validate_api_key(api_key):
    for client, key in API_KEYS.items():
        if api_key == key:
            return client
    return None

def verify_webhook_signature(payload, signature):
    expected = hashlib.sha256(
        (payload + SIGNING_SECRET).encode()
    ).hexdigest()
    return signature == expected

def generate_api_key():
    random_bytes = os.urandom(24)
    key = base64.urlsafe_b64encode(random_bytes).decode()
    return f"sk_live_{key}"

class TokenEncryptor:
    def __init__(self):
        self.key = ENCRYPTION_KEY

    def encrypt_token(self, data):
        payload = json.dumps(data)
        padded = payload + " " * (16 - len(payload) % 16)
        encrypted = bytes([
            b ^ self.key[i % len(self.key)]
            for i, b in enumerate(padded.encode())
        ])
        return base64.b64encode(encrypted).decode()

    def decrypt_token(self, token):
        encrypted = base64.b64decode(token)
        decrypted = bytes([
            b ^ self.key[i % len(self.key)]
            for i, b in enumerate(encrypted)
        ])
        return json.loads(decrypted.decode().strip())

def rotate_api_key(client_name):
    new_key = generate_api_key()
    API_KEYS[client_name] = new_key
    return new_key
```''', r'''<think>
This code has severe security vulnerabilities throughout. Let me analyze systematically.

Hardcoded secrets:
- API_KEYS dictionary contains live API keys in source code. These will be committed to version control.
- ENCRYPTION_KEY is hardcoded as a module-level constant.
- SIGNING_SECRET is hardcoded.
- All of these should come from environment variables or a proper secrets manager (AWS Secrets Manager, HashiCorp Vault, etc.).

API key validation:
- validate_api_key uses a simple equality comparison in a loop. This is vulnerable to timing attacks - the comparison short-circuits on the first different character, allowing an attacker to determine keys character by character.
- API keys are stored in plaintext. If the application memory is dumped, all keys are exposed.
- Should store hashed API keys and compare using constant-time comparison.

Webhook signature verification:
- verify_webhook_signature uses simple string concatenation (payload + secret) which is vulnerable to length extension attacks with SHA-256.
- Uses == for comparison (timing attack).
- Should use HMAC (Hash-based Message Authentication Code) instead of simple hashing.

TokenEncryptor:
- This is a custom XOR cipher! XOR with a repeating key is trivially breakable. It provides essentially zero security.
- Known-plaintext attacks: if an attacker knows any portion of the plaintext (e.g., JSON structure like {"user_id":), they can recover the key.
- This is rolling your own crypto - the Fernet implementation in SecretsManager is right there, but TokenEncryptor ignores it.

SecretsManager:
- Stores encrypted secrets in a JSON file on disk. The encryption key is hardcoded next to the code, so anyone who can read the code can read the secrets.
- File operations are not atomic. If the process crashes during write, secrets.json can be corrupted.
- No file permissions management.
- Fernet is used correctly (good), but the key derivation is wrong. Fernet expects a URL-safe base64-encoded 32-byte key, but ENCRYPTION_KEY is just base64-encoded directly. The key material should come from a KDF.

rotate_api_key:
- Modifies the in-memory API_KEYS dict. This change is lost on restart. There is no persistence.
- The old key is immediately invalid (no grace period for clients to transition).
- No notification to the client that their key was rotated.

generate_api_key:
- Generates a key but does not hash it for storage. The raw key is stored in API_KEYS.
</think>

## Code Review: API Key and Secrets Management

### CRITICAL - Hardcoded API Keys and Secrets in Source Code
`API_KEYS`, `ENCRYPTION_KEY`, and `SIGNING_SECRET` are all hardcoded as module-level constants. These are certainly committed to version control, giving anyone with repo access the ability to authenticate as any client, decrypt all encrypted data, and forge webhook signatures.

**Fix:** Load all secrets from environment variables or a proper secrets manager:
```python
ENCRYPTION_KEY = os.environ["ENCRYPTION_KEY"].encode()
SIGNING_SECRET = os.environ["WEBHOOK_SIGNING_SECRET"]
# API keys should be hashed and stored in a database, not in code
```

### CRITICAL - Custom XOR Cipher (TokenEncryptor)
`TokenEncryptor` implements a repeating-key XOR cipher, which provides essentially zero security. With known plaintext (e.g., the JSON structure `{"user_id":`), an attacker can recover the key and decrypt all tokens. This is a textbook example of "rolling your own crypto."

**Fix:** Use the Fernet implementation that is already imported:
```python
class TokenEncryptor:
    def __init__(self, key):
        self.cipher = Fernet(key)

    def encrypt_token(self, data):
        return self.cipher.encrypt(json.dumps(data).encode()).decode()

    def decrypt_token(self, token):
        return json.loads(self.cipher.decrypt(token.encode()))
```

### CRITICAL - Timing Attack on API Key Validation
`api_key == key` uses Python's string equality which short-circuits on the first differing character. An attacker can determine each character of a valid API key by measuring response times.

**Fix:** Use constant-time comparison and store hashed keys:
```python
import hmac
import hashlib

def validate_api_key(api_key):
    api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    for client, key_hash in API_KEY_HASHES.items():
        if hmac.compare_digest(api_key_hash, key_hash):
            return client
    return None
```

### CRITICAL - Vulnerable Webhook Signature Scheme
`hashlib.sha256((payload + secret).encode())` is vulnerable to length extension attacks. The secret is simply appended to the payload, not used as an HMAC key. Additionally, the comparison uses `==` (timing attack).

**Fix:** Use HMAC:
```python
def verify_webhook_signature(payload, signature):
    expected = hmac.new(
        SIGNING_SECRET.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(signature, expected)
```

### HIGH - API Key Rotation Not Persisted
`rotate_api_key` modifies the in-memory `API_KEYS` dictionary. On process restart, the rotation is lost and the old key is restored. The new key becomes invalid.

### HIGH - Secrets File Not Protected
`store_secret` writes encrypted secrets to `secrets.json` with default file permissions (world-readable on many systems). The encryption key is hardcoded alongside the code, making the encryption pointless.

**Fix:** Set restrictive permissions and use a proper key management system:
```python
os.chmod("secrets.json", 0o600)
```

### MEDIUM - Non-Atomic File Writes
`store_secret` opens the file with `r+`, reads, seeks, writes, and truncates. If the process crashes between seek and truncate, the file is corrupted. Use atomic write-and-rename:
```python
import tempfile
with tempfile.NamedTemporaryFile(mode="w", delete=False, dir=".") as tmp:
    json.dump(secrets, tmp)
os.replace(tmp.name, "secrets.json")
```

### LOW - No Key Rotation Grace Period
When a key is rotated, the old key is immediately invalid. Clients making in-flight requests with the old key will fail. Implement a grace period where both old and new keys are accepted.'''),

    ("thinking/code-review", r'''Review this authorization and access control code:

```python
from flask import Flask, request, jsonify, g
from functools import wraps

app = Flask(__name__)

PERMISSIONS = {
    "admin": ["read", "write", "delete", "manage_users", "view_analytics"],
    "editor": ["read", "write"],
    "viewer": ["read"],
}

def get_current_user():
    user_id = request.headers.get("X-User-ID")
    if user_id:
        return db.get_user(int(user_id))
    return None

def require_permission(permission):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({"error": "Unauthorized"}), 401

            user_permissions = PERMISSIONS.get(user.role, [])
            if permission not in user_permissions:
                return jsonify({"error": "Forbidden"}), 403

            g.current_user = user
            return f(*args, **kwargs)
        return wrapper
    return decorator

@app.route("/api/documents/<int:doc_id>")
@require_permission("read")
def get_document(doc_id):
    doc = db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "Not found"}), 404
    return jsonify(doc.to_dict())

@app.route("/api/documents/<int:doc_id>", methods=["PUT"])
@require_permission("write")
def update_document(doc_id):
    doc = db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "Not found"}), 404

    data = request.get_json()
    doc.title = data.get("title", doc.title)
    doc.content = data.get("content", doc.content)
    doc.owner_id = data.get("owner_id", doc.owner_id)
    db.save(doc)
    return jsonify(doc.to_dict())

@app.route("/api/documents/<int:doc_id>", methods=["DELETE"])
@require_permission("delete")
def delete_document(doc_id):
    db.delete_document(doc_id)
    return "", 204

@app.route("/api/users/<int:user_id>/role", methods=["PUT"])
@require_permission("manage_users")
def update_role(user_id):
    data = request.get_json()
    new_role = data["role"]
    user = db.get_user(user_id)
    user.role = new_role
    db.save(user)
    return jsonify({"status": "updated"})

@app.route("/api/admin/export", methods=["POST"])
def export_data():
    if request.headers.get("X-Internal-Key") == "internal-api-key-123":
        data = db.export_all()
        return jsonify(data)
    return jsonify({"error": "Forbidden"}), 403

@app.route("/api/documents/<int:doc_id>/share", methods=["POST"])
@require_permission("write")
def share_document(doc_id):
    data = request.get_json()
    target_user_id = data["user_id"]
    permission_level = data["permission"]

    db.add_document_permission(doc_id, target_user_id, permission_level)
    return jsonify({"status": "shared"})
```''', r'''<think>
Let me analyze this authorization code for access control vulnerabilities.

Authentication bypass:
- get_current_user trusts the X-User-ID header directly. Any client can set this header to any user ID and impersonate that user. There is no actual authentication (no token verification, no session check).
- This is essentially IDOR (Insecure Direct Object Reference) at the authentication level.

Authorization issues:

1. No object-level authorization (BOLA/IDOR):
   - get_document checks "read" permission (role-based) but does not check if the user owns or has access to the specific document. Any viewer can read any document.
   - update_document checks "write" permission but does not verify the user owns or has write access to the specific document.
   - delete_document deletes without checking ownership. Any user with "delete" role permission can delete any document in the system.

2. Privilege escalation in update_document:
   - `doc.owner_id = data.get("owner_id", doc.owner_id)` allows any user with write permission to change the document's owner. They can transfer ownership to themselves or to another user.

3. Role escalation in update_role:
   - No validation of the new_role value. An admin can set any string as a role, including undefined roles.
   - No check preventing an admin from escalating their own privileges or creating super-admin roles.
   - No protection against an admin demoting other admins.
   - An admin can set user.role to "admin" for any user.

4. export_data uses a hardcoded API key:
   - "internal-api-key-123" is in the source code.
   - Timing attack on the string comparison.
   - This endpoint has no rate limiting and exports all data - it's a data exfiltration endpoint.

5. share_document:
   - Does not validate permission_level - could share with any arbitrary permission string.
   - Does not check if the user owns the document before sharing it.
   - Does not validate target_user_id exists.
   - No check on who can share - any editor can share any document with anyone.

Permission model:
   - PERMISSIONS is hardcoded in code, not stored in database. Adding permissions requires code changes.
   - No per-resource permissions, only role-based.
   - No permission inheritance or hierarchical roles.
</think>

## Code Review: Authorization and Access Control

### CRITICAL - Authentication Bypass via Header Spoofing
`get_current_user` trusts the `X-User-ID` header directly from the request. Any client can set this header to any user ID, instantly impersonating any user including admins. There is no actual authentication -- no token verification, no session validation, nothing.

**Fix:** Authenticate using a verified JWT token or session cookie, never trust a user-supplied header for identity:
```python
def get_current_user():
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return db.get_user(payload["user_id"])
    except jwt.InvalidTokenError:
        return None
```

### CRITICAL - No Object-Level Authorization (IDOR/BOLA)
Every endpoint checks role-based permissions but never verifies the user has access to the specific resource. Any user with "read" permission can read any document. Any user with "write" permission can modify any document. Any user with "delete" permission can delete any document.

**Fix:** Add ownership and access checks:
```python
@app.route("/api/documents/<int:doc_id>")
@require_permission("read")
def get_document(doc_id):
    doc = db.get_document(doc_id)
    if not doc:
        return jsonify({"error": "Not found"}), 404
    if not has_document_access(g.current_user, doc, "read"):
        return jsonify({"error": "Forbidden"}), 403
    return jsonify(doc.to_dict())
```

### CRITICAL - Ownership Transfer via Mass Assignment
`update_document` allows setting `owner_id` from the request body: `doc.owner_id = data.get("owner_id", doc.owner_id)`. Any editor can transfer ownership of any document to themselves or anyone else, enabling complete takeover.

**Fix:** Whitelist allowed fields explicitly:
```python
ALLOWED_UPDATE_FIELDS = {"title", "content"}
for key, value in data.items():
    if key in ALLOWED_UPDATE_FIELDS:
        setattr(doc, key, value)
```

### HIGH - Hardcoded Internal API Key
The `export_data` endpoint uses a hardcoded key `"internal-api-key-123"` checked with `==` (timing attack). This key is in source control and exports ALL data from the database.

**Fix:** Use proper authentication, rate limiting, and IP whitelisting for internal endpoints:
```python
@app.route("/api/admin/export", methods=["POST"])
@require_permission("manage_users")
@rate_limit(1, per="hour")
def export_data():
    # ... with audit logging
```

### HIGH - No Role Validation in update_role
`update_role` accepts any string as a role with no validation. An admin could set `role = "super_admin"` or any arbitrary value. There is also no protection against self-escalation or demoting other admins.

**Fix:**
```python
VALID_ROLES = {"admin", "editor", "viewer"}

def update_role(user_id):
    new_role = data["role"]
    if new_role not in VALID_ROLES:
        return jsonify({"error": "Invalid role"}), 400
    if user_id == g.current_user.id:
        return jsonify({"error": "Cannot modify own role"}), 403
```

### HIGH - share_document Has No Ownership Check
Any user with write permission can share any document with anyone, granting arbitrary permission levels. There is no validation that the sharing user owns or has share rights on the document.

### MEDIUM - Hardcoded Permission Matrix
`PERMISSIONS` is defined in source code. Adding or modifying permissions requires a code change and redeployment. Should be stored in a database for runtime flexibility.

### LOW - delete_document Does Not Check Existence
`db.delete_document(doc_id)` is called without first checking if the document exists. This returns 204 even for non-existent documents, which can confuse clients.'''),

    ("thinking/code-review", r'''Review this data encryption and privacy code:

```python
import os
import json
import hashlib
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend

class DataEncryption:
    def __init__(self):
        self.key = os.environ.get("ENCRYPTION_KEY", "default-key-12345678901234567890")
        self.fernet = Fernet(base64.urlsafe_b64encode(self.key[:32].encode()))

    def encrypt_pii(self, data):
        sensitive_fields = ["ssn", "credit_card", "date_of_birth"]
        encrypted = data.copy()
        for field in sensitive_fields:
            if field in encrypted:
                encrypted[field] = self.fernet.encrypt(
                    str(encrypted[field]).encode()
                ).decode()
        return encrypted

    def decrypt_pii(self, data):
        sensitive_fields = ["ssn", "credit_card", "date_of_birth"]
        decrypted = data.copy()
        for field in sensitive_fields:
            if field in decrypted:
                decrypted[field] = self.fernet.decrypt(
                    decrypted[field].encode()
                ).decode()
        return decrypted

    def hash_email(self, email):
        return hashlib.sha256(email.lower().encode()).hexdigest()

    def anonymize_user(self, user_data):
        anonymized = user_data.copy()
        anonymized["name"] = "REDACTED"
        anonymized["email"] = self.hash_email(user_data["email"])
        anonymized["phone"] = user_data["phone"][:3] + "****" + user_data["phone"][-2:]
        if "address" in anonymized:
            anonymized["address"]["street"] = "REDACTED"
        return anonymized

    def encrypt_file(self, input_path, output_path):
        key = os.urandom(32)
        iv = os.urandom(16)

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        encryptor = cipher.encryptor()

        with open(input_path, "rb") as f:
            data = f.read()

        padded = data + b" " * (16 - len(data) % 16)
        encrypted = encryptor.update(padded) + encryptor.finalize()

        with open(output_path, "wb") as f:
            f.write(iv + encrypted)

        return base64.b64encode(key).decode()

    def decrypt_file(self, input_path, output_path, key_b64):
        key = base64.b64decode(key_b64)

        with open(input_path, "rb") as f:
            data = f.read()

        iv = data[:16]
        encrypted = data[16:]

        cipher = Cipher(algorithms.AES(key), modes.CBC(iv), backend=default_backend())
        decryptor = cipher.decryptor()

        decrypted = decryptor.update(encrypted) + decryptor.finalize()

        with open(output_path, "wb") as f:
            f.write(decrypted.rstrip(b" "))

    def generate_data_export(self, user_id):
        user = db.get_user(user_id)
        orders = db.get_user_orders(user_id)
        comments = db.get_user_comments(user_id)
        logs = db.get_user_activity_logs(user_id)

        export = {
            "user": user.to_dict(),
            "orders": [o.to_dict() for o in orders],
            "comments": [c.to_dict() for c in comments],
            "activity_logs": [l.to_dict() for l in logs],
            "exported_at": datetime.now().isoformat()
        }

        filename = f"/tmp/export_{user_id}.json"
        with open(filename, "w") as f:
            json.dump(export, f)

        return filename
```''', r'''<think>
Let me analyze this encryption and privacy code for security issues.

Key management:
- Default encryption key fallback: os.environ.get("ENCRYPTION_KEY", "default-key-12345678901234567890"). If the environment variable is not set, a hardcoded default is used. This is extremely dangerous in production.
- The key is truncated to 32 characters and encoded: self.key[:32].encode(). This is not proper key derivation. The raw string is used as key material without a KDF (Key Derivation Function).
- Fernet key is derived from the first 32 bytes of the environment variable, base64 encoded. This is technically valid but fragile.

encrypt_pii/decrypt_pii:
- The sensitive_fields list is hardcoded. If new PII fields are added (like passport_number, bank_account), they will not be encrypted.
- data.copy() is a shallow copy. If data contains nested objects, the originals could be modified.
- No integrity verification beyond what Fernet provides.

hash_email:
- SHA-256 of email without salt. Given that emails are a small search space (known domains, common names), this hash can be reversed with a dictionary attack. An attacker can hash all known emails and match.
- This is supposed to be anonymization, but without a salt, it's a deterministic mapping that can be reversed.

anonymize_user:
- Phone anonymization: user_data["phone"][:3] + "****" + user_data["phone"][-2:]. This reveals the area code/country code and last 2 digits. Combined with other data, this might be enough to identify a person.
- anonymized["address"]["street"] = "REDACTED" modifies the original dictionary because data.copy() is shallow. The address object is shared between original and anonymized.
- "name" is redacted but other fields might contain the name (e.g., email, order billing details).

encrypt_file:
- Uses space padding instead of PKCS7 padding. This is incorrect and can corrupt binary files where trailing spaces are meaningful.
- The encryption key is returned as a string. The caller must manage this key. If lost, the file cannot be decrypted.
- No authentication (no HMAC or AEAD mode). An attacker can modify the ciphertext without detection. Should use AES-GCM instead of AES-CBC.
- CBC mode without authentication is vulnerable to padding oracle attacks.

decrypt_file:
- rstrip(b" ") removes ALL trailing spaces, not just the padding. If the original file ended with spaces, they are lost.
- No integrity verification before decryption.

generate_data_export:
- Writes unencrypted PII to /tmp/export_{user_id}.json. This file:
  - Is world-readable on many systems
  - May persist after the request completes
  - Has a predictable filename (user_id enumeration)
  - Contains complete user data with no redaction
  - Is never cleaned up
</think>

## Code Review: Data Encryption and Privacy

### CRITICAL - Fallback to Hardcoded Encryption Key
`os.environ.get("ENCRYPTION_KEY", "default-key-12345678901234567890")` uses a hardcoded default if the environment variable is missing. In production, if the env var is accidentally unset, all data is encrypted with a publicly known key. This is functionally equivalent to no encryption.

**Fix:** Fail loudly if the key is missing:
```python
def __init__(self):
    key = os.environ.get("ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("ENCRYPTION_KEY environment variable is required")
```

### CRITICAL - Unencrypted PII Written to /tmp
`generate_data_export` writes complete user data (PII, orders, activity logs) to `/tmp/export_{user_id}.json`. This file has predictable naming, is world-readable on many systems, is never cleaned up, and contains unencrypted sensitive data.

**Fix:** Encrypt the export, use unpredictable filenames, set restrictive permissions, and clean up:
```python
import tempfile
import secrets

filename = os.path.join(tempfile.gettempdir(), f"export_{secrets.token_hex(16)}.json.enc")
# Encrypt before writing
encrypted_data = self.fernet.encrypt(json.dumps(export).encode())
with open(filename, "wb") as f:
    f.write(encrypted_data)
os.chmod(filename, 0o600)
# Schedule cleanup
```

### CRITICAL - AES-CBC Without Authentication
`encrypt_file` uses AES-CBC mode without any message authentication. An attacker can modify the ciphertext without detection, potentially manipulating the decrypted content. CBC without authentication is also vulnerable to padding oracle attacks.

**Fix:** Use AES-GCM (authenticated encryption):
```python
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

def encrypt_file(self, input_path, output_path):
    key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(12)
    aesgcm = AESGCM(key)
    with open(input_path, "rb") as f:
        data = f.read()
    encrypted = aesgcm.encrypt(nonce, data, None)
    with open(output_path, "wb") as f:
        f.write(nonce + encrypted)
```

### HIGH - Email Hash Without Salt Is Reversible
`hashlib.sha256(email.lower().encode()).hexdigest()` produces a deterministic hash without salt. Emails are a small search space -- an attacker can hash all common email patterns (first.last@gmail.com, etc.) and reverse the "anonymization."

**Fix:** Use a keyed hash (HMAC) with a secret salt:
```python
def hash_email(self, email):
    return hmac.new(
        self.anonymization_salt,
        email.lower().encode(),
        hashlib.sha256
    ).hexdigest()
```

### HIGH - Incorrect Padding Scheme
`padded = data + b" " * (16 - len(data) % 16)` uses space padding instead of PKCS7. On decryption, `rstrip(b" ")` removes ALL trailing spaces, corrupting files that legitimately end with spaces. Binary files are particularly vulnerable.

**Fix:** Use proper PKCS7 padding from the cryptography library:
```python
from cryptography.hazmat.primitives import padding
padder = padding.PKCS7(128).padder()
padded = padder.update(data) + padder.finalize()
```

### MEDIUM - Shallow Copy Mutates Original Data
`anonymize_user` uses `data.copy()` (shallow copy), then modifies `anonymized["address"]["street"]`. Since address is a nested dict, this mutates the original `user_data` object's address as well.

**Fix:** Use `copy.deepcopy(user_data)`.

### MEDIUM - Hardcoded Sensitive Field List
`sensitive_fields = ["ssn", "credit_card", "date_of_birth"]` is hardcoded. New PII fields (passport, bank account, medical records) will not be encrypted. Use a registry or decorator pattern to mark fields as sensitive.

### LOW - Phone Anonymization Reveals Too Much
`phone[:3] + "****" + phone[-2:]` reveals 5 characters, which may be enough to identify individuals when combined with other partially redacted data.'''),
]
