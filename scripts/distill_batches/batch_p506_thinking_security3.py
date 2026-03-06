"""Phase 1B: Foundation Thinking — Security Analysis (Part 3/4)
Cryptography, secrets management, supply chain, and infrastructure security."""

PAIRS = [
    (
        "thinking/security-weak-random-token",
        "Our password reset tokens can be predicted. The generation code:\n\n```python\nimport random\nimport time\n\ndef generate_reset_token(user_id):\n    random.seed(int(time.time()))\n    token = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=32))\n    db.execute(\n        'INSERT INTO reset_tokens (user_id, token, expires) VALUES (?, ?, ?)',\n        (user_id, token, time.time() + 3600)\n    )\n    return token\n```\n\nWhy is this predictable, and how would an attacker exploit it?",
        r'''<think>
Multiple issues making tokens predictable:

1. **`random.seed(int(time.time()))`** — the seed is the current Unix timestamp (seconds). There are only ~86,400 possible seeds per day. An attacker who knows approximately when a reset was requested can try all timestamps within that window.

2. **`random` module is Mersenne Twister** — it's a PRNG designed for statistical quality, NOT cryptographic security. Given 624 consecutive 32-bit outputs, the entire internal state can be reconstructed, allowing prediction of all future outputs.

3. **Re-seeding every call** — each call seeds with the current second. Multiple requests in the same second produce the SAME token.

Attack:
1. Request password reset for victim
2. Note the approximate time
3. For each second in a ±60 second window:
   - `random.seed(timestamp)`
   - Generate the token using the same code
4. Try each predicted token
5. ~120 attempts to guess the token

Fix: use `secrets` module (CSPRNG).
</think>

**The token is seeded with `int(time.time())`** — the current Unix timestamp in seconds. An attacker who knows when the reset was requested (±60 seconds) only needs ~120 guesses:

```python
# Attacker's script
import random
import time

# Try timestamps around when the reset was requested
for ts in range(int(time.time()) - 60, int(time.time()) + 60):
    random.seed(ts)
    predicted_token = ''.join(random.choices('abcdefghijklmnopqrstuvwxyz0123456789', k=32))
    if try_reset_with_token(predicted_token):
        print(f"Token found! Generated at timestamp {ts}")
        break
```

## Additional Problems
- **Same-second collision:** Two requests in the same second produce identical tokens
- **Mersenne Twister is not cryptographic:** 624 outputs → full state recovery → predict all future tokens

## Fix: Use `secrets` Module

```python
import secrets

def generate_reset_token(user_id):
    token = secrets.token_urlsafe(32)  # 256 bits of cryptographic randomness
    db.execute(
        'INSERT INTO reset_tokens (user_id, token, expires) VALUES (?, ?, ?)',
        (user_id, token, time.time() + 3600)
    )
    return token
```

**`secrets.token_urlsafe()`** uses the OS CSPRNG (`/dev/urandom` on Linux, `CryptGenRandom` on Windows). It's unpredictable even if the attacker knows the exact time, source code, and all previously generated tokens.'''
    ),
    (
        "thinking/security-hardcoded-secrets-detection",
        "A code review found these patterns across the codebase. Identify each secret and explain the risk:\n\n```python\n# config.py\nDATABASE_URL = 'postgresql://admin:Sup3rS3cret@db.prod.internal:5432/myapp'\nAWS_SECRET_KEY = 'wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY'\nSENDGRID_API_KEY = 'SG.xxxxx.yyyyy'\n\n# utils/auth.py\nJWT_SECRET = 'my-jwt-secret-key-2024'\nENCRYPTION_KEY = b'\\x01\\x02\\x03\\x04\\x05\\x06\\x07\\x08' * 4\n\n# docker-compose.yml\n# environment:\n#   - STRIPE_SECRET_KEY=sk_live_xxxxxxxxxxxx\n#   - GITHUB_TOKEN=ghp_xxxxxxxxxxxx\n```",
        r'''<think>
Each hardcoded secret and its risk:

1. DATABASE_URL with password — direct database access, data exfiltration
2. AWS_SECRET_KEY — full AWS account access (S3, EC2, IAM...)
3. SENDGRID_API_KEY — send email as the company (phishing, spam)
4. JWT_SECRET — forge any JWT token, impersonate any user
5. ENCRYPTION_KEY — predictable/weak key (sequential bytes), decrypt all encrypted data
6. STRIPE_SECRET_KEY — charge customers, refund to attacker accounts
7. GITHUB_TOKEN — access private repos, push malicious code

The docker-compose.yml is particularly bad because docker-compose files are often committed to version control.
</think>

## Secrets Found and Risk Assessment

| Secret | Risk | Severity |
|--------|------|----------|
| `DATABASE_URL` with password | Direct database access, full data breach | Critical |
| `AWS_SECRET_KEY` | Full AWS account control (S3, EC2, IAM) | Critical |
| `SENDGRID_API_KEY` | Send phishing emails as your domain | High |
| `JWT_SECRET` | Forge tokens, impersonate any user including admins | Critical |
| `ENCRYPTION_KEY` | Predictable sequential bytes — trivially decrypt all data | Critical |
| `STRIPE_SECRET_KEY` (`sk_live_`) | Charge/refund real money | Critical |
| `GITHUB_TOKEN` (`ghp_`) | Access private repos, inject malicious code | Critical |

## Fix: Environment Variables + Secrets Manager

```python
# config.py — NO secrets in code
import os

DATABASE_URL = os.environ['DATABASE_URL']
AWS_SECRET_KEY = os.environ['AWS_SECRET_ACCESS_KEY']
JWT_SECRET = os.environ['JWT_SECRET']

# For encryption keys, generate properly:
import secrets
ENCRYPTION_KEY = os.environ.get('ENCRYPTION_KEY') or secrets.token_bytes(32)
```

```bash
# .env (NEVER committed — add to .gitignore)
DATABASE_URL=postgresql://admin:xxx@db.prod.internal:5432/myapp
AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMI/...

# .gitignore
.env
*.pem
*secret*
```

**Immediate actions after finding committed secrets:**
1. **Rotate ALL exposed secrets** — they're in git history forever
2. Add `.env` and secret patterns to `.gitignore`
3. Use `git-secrets` or `trufflehog` in CI to prevent future leaks
4. For production: use a secrets manager (AWS Secrets Manager, Vault, Doppler)'''
    ),
    (
        "thinking/security-weak-encryption-ecb-mode",
        "Medical records are encrypted before storage, but a researcher noticed that identical records produce identical ciphertext. The encryption code:\n\n```python\nfrom Crypto.Cipher import AES\nimport base64\n\nKEY = b'0123456789abcdef'  # 16 bytes = AES-128\n\ndef encrypt_record(plaintext: str) -> str:\n    # Pad to 16-byte blocks\n    padded = plaintext.encode().ljust(((len(plaintext) + 15) // 16) * 16, b'\\x00')\n    cipher = AES.new(KEY, AES.MODE_ECB)\n    ciphertext = cipher.encrypt(padded)\n    return base64.b64encode(ciphertext).decode()\n\ndef decrypt_record(b64_ciphertext: str) -> str:\n    cipher = AES.new(KEY, AES.MODE_ECB)\n    ciphertext = base64.b64decode(b64_ciphertext)\n    plaintext = cipher.decrypt(ciphertext)\n    return plaintext.rstrip(b'\\x00').decode()\n```",
        r'''<think>
Multiple crypto issues:

1. **ECB mode** — each 16-byte block is encrypted independently. Identical plaintext blocks produce identical ciphertext blocks. This leaks patterns (the famous ECB penguin). For structured data like medical records, an attacker can:
   - Identify records with the same diagnosis
   - Track patients across records
   - Build a codebook of known plaintext→ciphertext mappings

2. **No IV/nonce** — same plaintext always produces same ciphertext (deterministic encryption)

3. **Null-byte padding** — ambiguous (can't distinguish padding from real null bytes), not a standard padding scheme

4. **Hardcoded key** — already covered in previous pair but worth noting

5. **No authentication (MAC)** — ciphertext can be modified without detection (bit-flipping attacks)

Fix: use AES-GCM (authenticated encryption with random nonce).
</think>

**ECB mode encrypts each block independently** — identical plaintext blocks produce identical ciphertext. This leaks patterns in structured data.

## Problems

1. **ECB mode** — no diffusion between blocks. Two patients with the same diagnosis produce identical ciphertext for that block. Attackers can identify, compare, and build codebooks.
2. **Deterministic** — same record always encrypts to the same ciphertext. Attacker can tell when a record hasn't changed.
3. **No authentication** — ciphertext can be silently modified (swap blocks between records)
4. **Null-byte padding** — non-standard, ambiguous with real data

## Fix: AES-GCM (Authenticated Encryption)

```python
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
import base64

KEY = get_random_bytes(32)  # AES-256, stored in secrets manager

def encrypt_record(plaintext: str) -> str:
    nonce = get_random_bytes(12)  # Random nonce — NEVER reuse with same key
    cipher = AES.new(KEY, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode())
    # Store nonce + tag + ciphertext together
    return base64.b64encode(nonce + tag + ciphertext).decode()

def decrypt_record(b64_data: str) -> str:
    raw = base64.b64decode(b64_data)
    nonce = raw[:12]
    tag = raw[12:28]
    ciphertext = raw[28:]
    cipher = AES.new(KEY, AES.MODE_GCM, nonce=nonce)
    plaintext = cipher.decrypt_and_verify(ciphertext, tag)
    return plaintext.decode()
```

**AES-GCM provides:**
- **Confidentiality** — random nonce means identical plaintexts produce different ciphertexts
- **Integrity** — authentication tag detects any tampering
- **Standard** — no custom padding, widely supported'''
    ),
    (
        "thinking/security-dependency-confusion",
        "Our CI pipeline installs packages from both a private registry and PyPI. An attacker published a package with the same name as our internal package on PyPI:\n\n```ini\n# pip.conf\n[global]\nextra-index-url = https://private.registry.company.com/simple/\n\n# requirements.txt\ncompany-auth-lib==2.3.1\ncompany-utils==1.0.0\nrequests==2.31.0\nflask==3.0.0\n```\n\nThe attacker published `company-auth-lib==99.0.0` on PyPI with a malicious `setup.py`. What happens?",
        r'''<think>
Dependency confusion / namespace attack.

With `extra-index-url`, pip checks BOTH registries. When pip finds `company-auth-lib` on both the private registry (v2.3.1) and PyPI (v99.0.0), it installs the HIGHEST version by default. The attacker's v99.0.0 wins.

The malicious `setup.py` runs during installation, giving the attacker code execution on the CI server.

The fix: use `--index-url` (replaces default, doesn't add) or pin hashes, or use PEP 708 package source verification.
</think>

**Dependency confusion.** With `extra-index-url`, pip searches BOTH your private registry AND PyPI. The attacker's `company-auth-lib==99.0.0` on PyPI has a higher version than your internal `2.3.1` — pip installs the attacker's version.

The malicious `setup.py` runs during `pip install`, giving the attacker code execution on your CI/CD server.

## Fix Options

**Option 1: Use `--index-url` (not `--extra-index-url`)**
```ini
# pip.conf — private registry ONLY
[global]
index-url = https://private.registry.company.com/simple/
# Public packages are proxied through private registry
```
Configure your private registry to proxy PyPI for public packages. All resolution goes through one controlled source.

**Option 2: Pin package hashes**
```txt
# requirements.txt
company-auth-lib==2.3.1 --hash=sha256:abc123...
company-utils==1.0.0 --hash=sha256:def456...
```
Hash pinning ensures only the exact known-good package is installed, regardless of what's on PyPI.

**Option 3: Namespace reservation**
Register your internal package names on PyPI as empty placeholder packages. The attacker can't publish a package with a name that already exists.

**Option 4: PEP 708 / pip `--only-binary` + build isolation**
```bash
pip install --require-hashes --no-deps -r requirements.txt
```

**Critical rule:** Never use `extra-index-url` in CI/CD — it creates a race between registries that attackers can win.'''
    ),
    (
        "thinking/security-docker-escape-privileged",
        "A developer runs containers in privileged mode for convenience. Review the security implications:\n\n```dockerfile\n# Dockerfile\nFROM python:3.11-slim\nCOPY app/ /app/\nCMD [\"python\", \"/app/main.py\"]\n```\n\n```yaml\n# docker-compose.yml\nservices:\n  app:\n    build: .\n    privileged: true\n    volumes:\n      - /var/run/docker.sock:/var/run/docker.sock\n    environment:\n      - AWS_SECRET_ACCESS_KEY=xxxxx\n```",
        r'''<think>
Multiple severe security issues:

1. **`privileged: true`** — gives the container ALL Linux capabilities, access to all host devices, and disables most security features (AppArmor, seccomp, cgroups). A container escape is trivial.

2. **Docker socket mount** — `/var/run/docker.sock` inside the container means the container can create NEW containers on the host. An attacker can:
   - Create a container with the host root filesystem mounted
   - Read/write any file on the host
   - This is effectively root access on the host

3. **AWS credentials in environment** — visible in `docker inspect`, process listings, and logs

4. **Running as root** (default) — no `USER` directive, so the app runs as root inside the container
</think>

**This configuration is equivalent to running the app directly as root on the host.** Four critical issues:

## 1. `privileged: true` = Container Escape
The container has ALL Linux capabilities, access to host devices, no seccomp/AppArmor. Escape is trivial:
```bash
# Inside privileged container — mount host filesystem
mount /dev/sda1 /mnt && chroot /mnt
# Now you're root on the host
```

## 2. Docker Socket = Full Host Control
With `/var/run/docker.sock` mounted, the container can spawn new containers with the host root filesystem:
```bash
docker run -v /:/host alpine cat /host/etc/shadow
```

## 3. Credentials in Environment Variables
`docker inspect` exposes them. They're in `/proc/1/environ`, visible to any process.

## 4. Running as Root (Default)

## Fix

```yaml
services:
  app:
    build: .
    # privileged: true  # REMOVED
    # volumes: docker.sock  # REMOVED
    read_only: true  # Read-only root filesystem
    security_opt:
      - no-new-privileges:true  # Prevent privilege escalation
    cap_drop:
      - ALL  # Drop ALL capabilities
    cap_add:
      - NET_BIND_SERVICE  # Only add what's needed
    tmpfs:
      - /tmp  # Writable temp directory
    user: "1000:1000"  # Non-root user
    secrets:
      - aws_credentials  # Docker secrets (encrypted, in-memory only)

secrets:
  aws_credentials:
    file: ./secrets/aws.json  # Not in environment
```

```dockerfile
FROM python:3.11-slim
RUN adduser --disabled-password --no-create-home appuser
COPY app/ /app/
USER appuser
CMD ["python", "/app/main.py"]
```

**Principle of least privilege:** drop all capabilities, add only what's needed, run as non-root, never mount the Docker socket.'''
    ),
    (
        "thinking/security-log-injection",
        "An attacker manipulated our log files to hide their tracks and inject fake log entries:\n\n```python\nimport logging\n\nlogger = logging.getLogger('auth')\n\n@app.route('/api/login', methods=['POST'])\ndef login():\n    username = request.json['username']\n    user = authenticate(username, request.json['password'])\n    \n    if user:\n        logger.info(f'Login successful for user: {username}')\n        return jsonify(token=create_token(user))\n    \n    logger.warning(f'Failed login attempt for user: {username}')\n    return jsonify(error='Invalid credentials'), 401\n```\n\nAttacker submits username: `admin\\nINFO:auth:Login successful for user: admin`",
        r'''<think>
Log injection / log forging. The newline in the username creates a fake log entry:

```
WARNING:auth:Failed login attempt for user: admin
INFO:auth:Login successful for user: admin
```

The second line is injected by the attacker, making it look like admin logged in successfully. This can:
1. Hide attack evidence
2. Inject fake entries to frame others
3. Confuse SIEM systems
4. In some logging systems, inject control sequences for terminal escape (ANSI codes)
</think>

**Log injection.** The newline in the username creates a fake log entry that looks legitimate:

```
WARNING:auth:Failed login attempt for user: admin
INFO:auth:Login successful for user: admin    ← FAKE (injected by attacker)
```

## Risks
- **Hide attacks** — inject "successful" entries to mask brute force
- **Frame users** — inject entries implicating other accounts
- **SIEM evasion** — confuse automated log analysis
- **Terminal attacks** — ANSI escape codes can manipulate log viewers

## Fix: Sanitize Log Data

```python
import logging
import re

logger = logging.getLogger('auth')

def sanitize_log_value(value: str) -> str:
    """Remove characters that can break log formatting."""
    # Remove newlines, carriage returns, and ANSI escape codes
    value = re.sub(r'[\r\n]', ' ', value)
    value = re.sub(r'\x1b\[[0-9;]*m', '', value)  # ANSI codes
    # Truncate to prevent log flooding
    return value[:200]

@app.route('/api/login', methods=['POST'])
def login():
    username = sanitize_log_value(request.json.get('username', ''))
    user = authenticate(username, request.json['password'])

    if user:
        logger.info('Login successful for user: %s from IP: %s',
                     username, request.remote_addr)
        return jsonify(token=create_token(user))

    logger.warning('Failed login attempt for user: %s from IP: %s',
                    username, request.remote_addr)
    return jsonify(error='Invalid credentials'), 401
```

**Key fixes:**
1. Strip newlines and control characters from all logged user data
2. Use `%s` formatting (not f-strings) — some log frameworks handle escaping
3. Truncate to prevent log flooding attacks
4. Include IP address for forensics'''
    ),
    (
        "thinking/security-xml-xxe-attack",
        "An API endpoint accepts XML data for import. An attacker used it to read files from the server:\n\n```python\nfrom lxml import etree\n\n@app.route('/api/import', methods=['POST'])\ndef import_data():\n    xml_data = request.data\n    tree = etree.fromstring(xml_data)\n    \n    records = []\n    for item in tree.findall('.//item'):\n        records.append({\n            'name': item.find('name').text,\n            'value': item.find('value').text,\n        })\n    return jsonify(imported=len(records))\n```\n\nAttacker's payload:\n```xml\n<?xml version=\"1.0\"?>\n<!DOCTYPE foo [\n  <!ENTITY xxe SYSTEM \"file:///etc/passwd\">\n]>\n<data><item><name>&xxe;</name><value>test</value></item></data>\n```",
        r'''<think>
XML External Entity (XXE) injection. The XML DTD defines an external entity `xxe` that references `file:///etc/passwd`. When the parser resolves `&xxe;`, it reads the file and inserts its contents as the `<name>` value. The server then returns the file contents in the response (or stores them, depending on the logic).

lxml by default resolves external entities if DTD processing is enabled.

Fix: disable DTD processing and external entity resolution.
</think>

**XML External Entity (XXE) injection.** The DTD defines an entity that reads local files. When parsed, `&xxe;` is replaced with the contents of `/etc/passwd`:

```xml
<name>root:x:0:0:root:/root:/bin/bash
daemon:x:1:1:...</name>
```

## Attack Escalation

```xml
<!-- Read any file -->
<!ENTITY xxe SYSTEM "file:///app/config.py">

<!-- SSRF — access internal services -->
<!ENTITY xxe SYSTEM "http://169.254.169.254/latest/meta-data/iam/security-credentials/">

<!-- Denial of Service (Billion Laughs) -->
<!ENTITY lol "lol">
<!ENTITY lol2 "&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;&lol;">
<!-- ... nested 10 levels deep = 10^10 expansions → OOM -->
```

## Fix: Disable External Entities

```python
from lxml import etree

@app.route('/api/import', methods=['POST'])
def import_data():
    xml_data = request.data

    # Secure parser — disable DTD, external entities, and network access
    parser = etree.XMLParser(
        resolve_entities=False,
        no_network=True,
        dtd_validation=False,
        load_dtd=False,
    )

    tree = etree.fromstring(xml_data, parser=parser)

    records = []
    for item in tree.findall('.//item'):
        name_el = item.find('name')
        value_el = item.find('value')
        if name_el is not None and value_el is not None:
            records.append({
                'name': name_el.text or '',
                'value': value_el.text or '',
            })
    return jsonify(imported=len(records))
```

**Or better — use JSON.** Unless you specifically need XML, JSON doesn't have entity expansion and is immune to XXE.'''
    ),
    (
        "thinking/security-regex-dos-input-validation",
        "An input validation regex causes the API to hang on certain inputs. The regex validates email addresses:\n\n```python\nimport re\n\nEMAIL_PATTERN = re.compile(\n    r'^([a-zA-Z0-9]+\\.?)+[a-zA-Z0-9]+@([a-zA-Z0-9]+\\.)+[a-zA-Z]{2,}$'\n)\n\ndef is_valid_email(email: str) -> bool:\n    return bool(EMAIL_PATTERN.match(email))\n\n# This hangs:\nis_valid_email('aaaaaaaaaaaaaaaaaaaaaaaa@')\n```\n\nIdentify the vulnerable pattern and fix it.",
        r'''<think>
ReDoS. `([a-zA-Z0-9]+\\.?)+` has nested quantifiers. For the input `aaaaaaaaaaaaaaaaaaaaaaaa@`:
- `[a-zA-Z0-9]+` matches some characters
- `\\.?` optionally matches a dot (no dot here)
- `()+` repeats the group

The a's can be divided between the inner `+` and outer `+` in exponentially many ways. When the `@` doesn't lead to a valid domain match, the engine backtracks through all divisions. 24 a's = ~2^24 backtracking steps.
</think>

**ReDoS from nested quantifiers.** `([a-zA-Z0-9]+\\.?)+` — the inner `+` and outer `+` can split the input in exponentially many ways when the match fails. 24 characters = ~2^24 backtracking steps.

## Fix: Non-Overlapping Pattern

```python
import re

# Simple, efficient email validation (no nested quantifiers)
EMAIL_PATTERN = re.compile(
    r'^[a-zA-Z0-9][a-zA-Z0-9._+-]*@[a-zA-Z0-9-]+(\.[a-zA-Z0-9-]+)*\.[a-zA-Z]{2,}$'
)

def is_valid_email(email: str) -> bool:
    if len(email) > 254:  # RFC max
        return False
    return bool(EMAIL_PATTERN.match(email))
```

**Why this is safe:** `[a-zA-Z0-9._+-]*` is a single character class with `*` — no group repetition, linear backtracking. Each character is consumed by exactly one part of the pattern.

**General ReDoS prevention rules:**
1. Never nest quantifiers: `(a+)+`, `(a*)*`, `(a+)*`
2. Avoid overlapping alternatives: `(a|ab)+`
3. Always set input length limits before regex matching
4. Use `re2` or `regex` module with timeout for untrusted patterns'''
    ),
    (
        "thinking/security-insecure-file-permissions",
        "A deployment script creates config files with secrets. After deployment, any user on the server can read the database password:\n\n```python\nimport json\n\ndef write_config(config, path='/etc/myapp/config.json'):\n    with open(path, 'w') as f:\n        json.dump(config, f, indent=2)\n    print(f'Config written to {path}')\n\n# Config contains:\n# {'database': {'host': 'db.internal', 'password': 's3cret'}, ...}\n```\n\n```bash\n$ ls -la /etc/myapp/config.json\n-rw-r--r-- 1 root root 256 Jan 15 10:30 config.json\n# ^^^ readable by everyone!\n```",
        r'''<think>
`open()` in Python creates files with the default umask permissions, typically 0644 (`-rw-r--r--`). This means any user on the system can read the file, including the database password.

Fix: set restrictive permissions explicitly.
</think>

`open()` creates files with default umask (typically `0644` = world-readable). Any user on the server can read your database password.

## Fix: Restrictive File Permissions

```python
import json
import os
import stat

def write_config(config, path='/etc/myapp/config.json'):
    # Create parent directory with restricted permissions
    os.makedirs(os.path.dirname(path), mode=0o750, exist_ok=True)

    # Write file with owner-only permissions (0600 = -rw-------)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, 'w') as f:
            json.dump(config, f, indent=2)
    except Exception:
        os.close(fd)
        raise

    # Verify permissions (belt and suspenders)
    actual = stat.S_IMODE(os.stat(path).st_mode)
    if actual != 0o600:
        os.chmod(path, 0o600)

    print(f'Config written to {path} (mode 0600)')
```

```bash
$ ls -la /etc/myapp/config.json
-rw------- 1 root root 256 Jan 15 10:30 config.json
# Only root can read this now
```

**Key:** `os.open()` with explicit mode `0o600` (owner read/write only). The standard `open()` function doesn't accept a mode for new files and respects the process umask.'''
    ),
    (
        "thinking/security-timing-side-channel-api-key",
        "An attacker is brute-forcing API keys character by character. They noticed that invalid keys return faster when the first character is wrong vs when the first 10 characters are correct:\n\n```python\ndef verify_api_key(provided_key: str) -> bool:\n    stored_key = get_stored_api_key()\n    if len(provided_key) != len(stored_key):\n        return False\n    for i in range(len(stored_key)):\n        if provided_key[i] != stored_key[i]:\n            return False\n    return True\n```\n\nHow does the timing attack work, and what's the fix?",
        r'''<think>
Character-by-character comparison short-circuits on first mismatch. If the first character is wrong, the function returns after checking 1 character. If the first 10 characters are correct, it checks 10 before returning on the 11th.

The attacker can measure response times:
1. Try key starting with 'a' → 1ms
2. Try key starting with 'b' → 1ms
3. Try key starting with 'c' → 1.1ms → slightly slower → first char is 'c'
4. Now try 'ca', 'cb', 'cc', ... find second character
5. Continue character by character

Instead of 36^32 guesses for a 32-char alphanumeric key (impossible), only 36*32 = 1152 guesses (trivial).
</think>

**Timing side channel.** The comparison returns earlier when the first mismatch is early. By measuring response times, the attacker brute-forces one character at a time:

- Instead of `36^32` guesses (impossible)
- Only `36 × 32 = 1,152` guesses (trivial)

## Fix: Constant-Time Comparison

```python
import hmac

def verify_api_key(provided_key: str) -> bool:
    stored_key = get_stored_api_key()
    # hmac.compare_digest runs in constant time regardless of where the mismatch is
    return hmac.compare_digest(provided_key.encode(), stored_key.encode())
```

**`hmac.compare_digest()`** compares ALL bytes and XORs the results, taking the same time regardless of where (or if) characters differ. The attacker learns nothing from timing.

**When to use constant-time comparison:** API keys, tokens, password hashes, HMAC verification — any secret comparison where timing leakage would help an attacker.'''
    ),
    (
        "thinking/security-unsafe-reflection",
        "A plugin system lets users specify a class to instantiate. An attacker used it to execute arbitrary code:\n\n```python\nimport importlib\n\ndef load_plugin(plugin_path: str):\n    \"\"\"Load a plugin by dotted path. E.g., 'plugins.auth.OAuthPlugin'\"\"\"\n    module_path, class_name = plugin_path.rsplit('.', 1)\n    module = importlib.import_module(module_path)\n    cls = getattr(module, class_name)\n    return cls()\n\n# API endpoint\n@app.route('/api/plugins', methods=['POST'])\ndef activate_plugin():\n    plugin_path = request.json['plugin']\n    plugin = load_plugin(plugin_path)\n    plugin.activate()\n    return jsonify(success=True)\n```\n\nAttacker sends: `{\"plugin\": \"os.system\"}` or `{\"plugin\": \"subprocess.Popen\"}`",
        r'''<think>
Unsafe reflection / arbitrary class instantiation. The code imports any module and gets any attribute — the attacker can instantiate any Python class or call any function:

- `os.system` → call os.system() (though it needs arguments)
- `subprocess.Popen` → create a Popen object
- `builtins.eval` → access eval
- `importlib.import_module` → import anything

Actually, `os.system` returns a function, not a class. `cls()` would call `os.system()` with no arguments, which is a no-op. But `subprocess.Popen` with empty args would try to execute something.

More dangerous: any class with side effects in `__init__`, or using it to import malicious modules.

Fix: allowlist of permitted plugins.
</think>

**Unsafe reflection.** The code imports ANY module and accesses ANY attribute. The attacker can instantiate arbitrary Python classes or call functions:

```json
{"plugin": "subprocess.Popen"}
{"plugin": "importlib.import_module"}
{"plugin": "code.InteractiveConsole"}
```

## Fix: Allowlist of Permitted Plugins

```python
from importlib import import_module

ALLOWED_PLUGINS = {
    'oauth': 'plugins.auth.OAuthPlugin',
    'ldap': 'plugins.auth.LDAPPlugin',
    'webhook': 'plugins.notifications.WebhookPlugin',
    'email': 'plugins.notifications.EmailPlugin',
}

def load_plugin(plugin_name: str):
    """Load a plugin by its registered name (not arbitrary path)."""
    plugin_path = ALLOWED_PLUGINS.get(plugin_name)
    if not plugin_path:
        raise ValueError(f"Unknown plugin: {plugin_name}")

    module_path, class_name = plugin_path.rsplit('.', 1)
    module = import_module(module_path)
    cls = getattr(module, class_name)

    # Verify it's actually a plugin (not some other class)
    if not issubclass(cls, BasePlugin):
        raise TypeError(f"{cls} is not a valid plugin")

    return cls()

@app.route('/api/plugins', methods=['POST'])
def activate_plugin():
    plugin_name = request.json['plugin']  # 'oauth', not 'os.system'
    plugin = load_plugin(plugin_name)
    plugin.activate()
    return jsonify(success=True)
```

**Never let user input control what code is loaded.** Use a lookup table (allowlist) mapping safe names to actual implementations.'''
    ),
    (
        "thinking/security-graphql-introspection-dos",
        "Our GraphQL API is vulnerable to two attacks — information disclosure via introspection and denial of service via deeply nested queries:\n\n```python\nimport graphene\n\nclass User(graphene.ObjectType):\n    id = graphene.ID()\n    name = graphene.String()\n    friends = graphene.List(lambda: User)\n    posts = graphene.List(lambda: Post)\n\nclass Post(graphene.ObjectType):\n    id = graphene.ID()\n    title = graphene.String()\n    author = graphene.Field(User)\n    comments = graphene.List(lambda: Comment)\n\nclass Comment(graphene.ObjectType):\n    id = graphene.ID()\n    text = graphene.String()\n    author = graphene.Field(User)\n```\n\nAttacker's query:\n```graphql\n{\n  users {\n    friends {\n      friends {\n        friends {\n          friends {\n            posts {\n              comments {\n                author {\n                  friends {\n                    posts { comments { author { friends { name } } } }\n                  }\n                }\n              }\n            }\n          }\n        }\n      }\n    }\n  }\n}\n```",
        r'''<think>
Two issues:

1. **Introspection** — GraphQL introspection query reveals the entire API schema (all types, fields, arguments, enums). This is useful for development but shouldn't be enabled in production. Attackers use it to discover hidden fields, admin mutations, and relationships.

2. **Deeply nested queries** — The circular relationships (User → friends → User → posts → comments → author → User) allow infinite nesting. Each level multiplies the number of database queries. A depth-15 query could trigger millions of DB lookups.

Fix: disable introspection in production, limit query depth, limit query complexity.
</think>

Two attacks:

## 1. Introspection — Schema Disclosure
Default GraphQL introspection reveals your entire API: all types, fields, mutations, internal structures. Attackers discover hidden admin endpoints.

## 2. Nested Query DoS
Circular relationships (User→friends→User→posts→comments→author) allow unbounded nesting. Depth 15 = millions of database queries → server exhaustion.

## Fix: Depth Limiting + Complexity Analysis + Disable Introspection

```python
from graphql import validate
from graphene import Schema

# Depth limiting middleware
class DepthLimitMiddleware:
    MAX_DEPTH = 7

    def resolve(self, next, root, info, **args):
        # Check query depth before execution
        depth = self._get_depth(info.field_nodes[0])
        if depth > self.MAX_DEPTH:
            raise Exception(f"Query depth {depth} exceeds maximum {self.MAX_DEPTH}")
        return next(root, info, **args)

    def _get_depth(self, node, current=0):
        if not hasattr(node, 'selection_set') or not node.selection_set:
            return current
        return max(
            self._get_depth(child, current + 1)
            for child in node.selection_set.selections
        )

# Disable introspection in production
class NoIntrospectionMiddleware:
    def resolve(self, next, root, info, **args):
        if info.field_name in ('__schema', '__type'):
            raise Exception("Introspection is disabled")
        return next(root, info, **args)

schema = Schema(query=Query)

# Apply middleware
schema.execute(
    query,
    middleware=[DepthLimitMiddleware(), NoIntrospectionMiddleware()]
)
```

**Additional defenses:**
- **Query cost analysis** — assign cost to each field, reject queries above threshold
- **Rate limiting** per user/IP
- **Pagination required** — don't allow unbounded list queries
- **Persisted queries** — only accept pre-registered query hashes in production'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
