"""Phase 2B: Advanced Reasoning — Adversarial Self-Testing (Part 7/8)"""

PAIRS = [
    (
        "thinking/adversarial-user-registration",
        "Review this user registration endpoint for security issues:\n\n```python\nfrom flask import Flask, request, jsonify\nimport sqlite3\nimport hashlib\n\napp = Flask(__name__)\n\n@app.route('/register', methods=['POST'])\ndef register():\n    data = request.get_json()\n    username = data['username']\n    email = data['email']\n    password = data['password']\n    \n    conn = sqlite3.connect('users.db')\n    cursor = conn.cursor()\n    cursor.execute(f\"INSERT INTO users (username, email, password) VALUES ('{username}', '{email}', '{hashlib.md5(password.encode()).hexdigest()}')\")\n    conn.commit()\n    conn.close()\n    \n    return jsonify({'message': f'Welcome {username}!'}), 201\n```",
        r'''<think>
Let me systematically attack every part of this registration endpoint.

**Attack vector 1: SQL injection (CRITICAL)**
```python
cursor.execute(f"INSERT INTO users ... VALUES ('{username}', '{email}', ...")
```
Direct f-string interpolation into SQL. An attacker can:
- `username = "admin', 'hacker@evil.com', 'hash'); DROP TABLE users; --"`
- This drops the entire users table
- Or: insert themselves as admin, read all data, etc.

**Attack vector 2: MD5 password hashing (CRITICAL)**
MD5 is:
- Cryptographically broken (collisions exist)
- Extremely fast (GPU can compute billions of MD5 hashes/second)
- Unsalted — identical passwords produce identical hashes
- Rainbow table attacks trivially crack MD5 hashes

**Attack vector 3: No input validation**
- Username: can be empty, contain SQL, be 10,000 characters
- Email: no format validation, can be anything
- Password: no minimum length/complexity requirement
- No duplicate check (same email/username registered twice)

**Attack vector 4: No rate limiting**
Attackers can create millions of accounts (credential stuffing, spam).

**Attack vector 5: Reflected user input in response (XSS)**
```python
return jsonify({'message': f'Welcome {username}!'})
```
If username contains HTML/JavaScript and this JSON is rendered in a browser unsafely, it could lead to XSS. JSON APIs are generally safe, but if the frontend inserts this message into the DOM without escaping...

**Attack vector 6: Database connection handling**
- Connection opened but never closed in error cases (no try/finally)
- Using SQLite for a web app (concurrency issues)
- No connection pooling

**Attack vector 7: No HTTPS enforcement**
Password sent in plaintext if the server doesn't enforce HTTPS.

**Attack vector 8: Unhandled exceptions**
If the INSERT fails (duplicate key, DB locked), the 500 error might leak database schema information.

**Attack vector 9: No CSRF protection**
No CSRF token validation. If this endpoint is accessed by browsers, CSRF attacks can create accounts on behalf of victims.

**Attack vector 10: Password in memory**
The raw password is kept in `data['password']` — in a crash dump or memory analysis, the plaintext password would be visible.

That's 10 attack vectors. This endpoint is critically insecure.
</think>

This registration endpoint has **10 security vulnerabilities**, two of which are critical. Here's the complete analysis:

## Critical Vulnerabilities

### 1. SQL Injection (Instant Database Compromise)

```bash
# ATTACK: Drop the entire users table
curl -X POST http://app.com/register -H "Content-Type: application/json" \
  -d '{"username": "x\", \"e\", \"p\"); DROP TABLE users; --",
       "email": "x", "password": "x"}'

# ATTACK: Extract all existing users
# username = "x', (SELECT group_concat(password) FROM users), 'x'); --"

# ATTACK: Create an admin account
# username = "admin', 'admin@evil.com', 'known_hash'); --"
```

### 2. MD5 Password Hashing (Crackable in Seconds)

```python
# MD5 is FAST — that's the problem. GPUs can do 50 BILLION MD5 hashes/second
hashlib.md5(password.encode()).hexdigest()
# "password123" → "482c811da5d5b4bc6d497ffa98491e38"
# Cracked in < 1 second with rainbow tables or brute force

# Also UNSALTED — all users with "password123" have the same hash
# Leak the DB → crack one → crack all identical passwords
```

## All 10 Vulnerabilities

| # | Issue | Severity |
|---|-------|----------|
| 1 | SQL injection via f-string | **Critical** |
| 2 | MD5 unsalted password hashing | **Critical** |
| 3 | No input validation | High |
| 4 | No duplicate user/email check | High |
| 5 | No rate limiting | High |
| 6 | Reflected input in response | Medium |
| 7 | No error handling / connection leak | Medium |
| 8 | No password complexity requirement | Medium |
| 9 | Error messages may leak DB schema | Low |
| 10 | No CSRF protection | Low (API) |

## Secure Implementation

```python
from flask import Flask, request, jsonify, abort
from flask_limiter import Limiter
import bcrypt
import re
import sqlite3

app = Flask(__name__)
limiter = Limiter(app, key_func=lambda: request.remote_addr)


def get_db():
    conn = sqlite3.connect('users.db')
    conn.row_factory = sqlite3.Row
    return conn


def validate_registration(data: dict) -> list[str]:
    """Validate all inputs. Returns list of errors."""
    errors = []

    username = data.get('username', '')
    if not username or len(username) < 3 or len(username) > 30:
        errors.append("Username must be 3-30 characters")
    if not re.match(r'^[a-zA-Z0-9_-]+$', username):
        errors.append("Username can only contain letters, numbers, _ and -")

    email = data.get('email', '')
    if not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
        errors.append("Invalid email format")

    password = data.get('password', '')
    if len(password) < 12:
        errors.append("Password must be at least 12 characters")

    return errors


@app.route('/register', methods=['POST'])
@limiter.limit("5 per minute")  # Rate limiting
def register():
    data = request.get_json()
    if not data:
        abort(400, "Missing request body")

    # Input validation
    errors = validate_registration(data)
    if errors:
        return jsonify({'errors': errors}), 400

    username = data['username']
    email = data['email'].lower()

    # Secure password hashing (bcrypt with automatic salt)
    password_hash = bcrypt.hashpw(
        data['password'].encode(), bcrypt.gensalt(rounds=12)
    ).decode()

    conn = get_db()
    try:
        # Check for duplicates
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ? OR email = ?",
            (username, email)
        ).fetchone()
        if existing:
            return jsonify({'error': 'Username or email already registered'}), 409

        # Parameterized query — immune to SQL injection
        conn.execute(
            "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
            (username, email, password_hash)
        )
        conn.commit()

        # Don't reflect user input in response
        return jsonify({'message': 'Account created successfully'}), 201

    except sqlite3.IntegrityError:
        return jsonify({'error': 'Registration failed'}), 409
    finally:
        conn.close()  # Always close, even on error
```

## Key Fixes Explained

```python
# FIX 1: Parameterized queries (? placeholders)
cursor.execute("INSERT INTO users VALUES (?, ?, ?)", (username, email, hash))
# SQLite treats ? values as DATA, not SQL — injection impossible

# FIX 2: bcrypt with salt (instead of MD5)
bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=12))
# bcrypt is intentionally SLOW (0.3s per hash vs nanoseconds for MD5)
# Each password gets a unique random salt — rainbow tables don't work
# rounds=12 means 2^12 = 4,096 iterations — resistant to GPU attacks

# FIX 3: Input validation before processing
# Reject bad input early — don't even try to insert it

# FIX 4: Generic error messages
# "Registration failed" not "UNIQUE constraint failed: users.email"
# Don't leak database internals
```'''
    ),
    (
        "thinking/adversarial-api-key-storage",
        "We store API keys for third-party services in our Django settings.py file. We've been told this is insecure but the alternatives seem overly complex. Is this really a problem?",
        r'''<think>
API keys in settings.py — let me think about the attack surface.

**How API keys in settings.py get exposed:**

1. **Source control** — settings.py is committed to git. Everyone with repo access sees the keys. Former employees, contractors, anyone who finds the repo. If the repo is public (or becomes public by accident), keys are exposed to the world.

2. **Git history** — even if you remove the keys now, they're in the git history FOREVER. `git log -p settings.py` shows every version.

3. **CI/CD logs** — build systems may print settings for debugging.

4. **Error reporting** — Sentry, Datadog, etc. may capture settings in stack traces.

5. **Developer machines** — every developer has a local copy of ALL production keys. Laptop stolen? All keys compromised.

6. **Backups** — database backups, server snapshots, source code backups all contain the keys.

7. **Container images** — if settings.py is baked into a Docker image, anyone with access to the image registry can extract the keys.

The severity depends on WHAT the keys are for:
- Stripe secret key → attacker can charge customers, refund to themselves
- AWS root key → attacker owns your entire cloud infrastructure
- SendGrid key → attacker sends emails as you (phishing)
- Database password → attacker reads/modifies all data

**Is this really a problem?** Yes. Unequivocally. Every major breach in the last decade has involved credential exposure. Keys in source code are the #1 source of credential leaks.

**The alternatives aren't overly complex.** Environment variables take 5 minutes to set up. Let me show the progression from simple to robust.
</think>

Yes, this is a **real and serious problem**. API keys in settings.py get exposed through at least 7 channels. Here's why and the fix:

## How Keys in settings.py Get Leaked

```
1. Git history → Every developer, past employee, contractor can see them
                 Even after "removing" them, they're in git log forever

2. Source code leak → If repo goes public accidentally (happens regularly)
                     GitHub auto-scanners find keys within MINUTES

3. Error reports → Sentry captures local variables in stack traces
                   settings.STRIPE_SECRET_KEY appears in error reports

4. Docker images → Keys baked into container images
                   Anyone with registry access can: docker inspect

5. CI/CD logs → Build systems often dump environment for debugging
                Your Stripe key is in the Jenkins build log

6. Developer laptops → Every dev has production keys on their laptop
                      Laptop stolen? All keys compromised.

7. Backups → Every backup of the codebase includes production secrets
```

## Real-World Impact

```
If your Stripe key leaks:    → Attacker charges customers, refunds to themselves
If your AWS key leaks:       → Attacker spins up crypto miners ($$$), steals data
If your DB password leaks:   → Attacker reads ALL customer data (GDPR breach)
If your SendGrid key leaks:  → Attacker sends phishing emails from your domain
```

## The Fix: Progressive Levels of Security

### Level 1: Environment Variables (5 minutes — do this TODAY)

```python
# ❌ settings.py with hardcoded keys
STRIPE_SECRET_KEY = "sk_live_abc123..."
DATABASE_PASSWORD = "supersecret"
AWS_ACCESS_KEY = "AKIAIOSFODNN7EXAMPLE"

# ✅ settings.py reading from environment
import os

STRIPE_SECRET_KEY = os.environ["STRIPE_SECRET_KEY"]
DATABASE_PASSWORD = os.environ["DATABASE_PASSWORD"]
AWS_ACCESS_KEY = os.environ["AWS_ACCESS_KEY"]
```

```bash
# Set in your deployment environment:
export STRIPE_SECRET_KEY="sk_live_abc123..."

# For local development, use a .env file (NOT committed to git):
# .env
STRIPE_SECRET_KEY=sk_test_local_key
DATABASE_PASSWORD=localdevpassword

# .gitignore — CRITICAL
.env
*.env
.env.*
```

```python
# Load .env file for local development
# pip install python-dotenv
from dotenv import load_dotenv
load_dotenv()  # Loads .env file into os.environ
```

### Level 2: Validate on Startup (10 minutes)

```python
# settings.py — fail FAST if keys are missing
import os
import sys

def require_env(name: str) -> str:
    """Get environment variable or crash with clear message."""
    value = os.environ.get(name)
    if not value:
        print(f"FATAL: Missing required environment variable: {name}", file=sys.stderr)
        sys.exit(1)
    return value

STRIPE_SECRET_KEY = require_env("STRIPE_SECRET_KEY")
DATABASE_URL = require_env("DATABASE_URL")
SECRET_KEY = require_env("DJANGO_SECRET_KEY")

# Optional variables with safe defaults
DEBUG = os.environ.get("DEBUG", "false").lower() == "true"
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
```

### Level 3: Separate Dev/Prod Keys (30 minutes)

```python
# Each environment has its own keys — devs NEVER see production keys

# Development: .env.dev (committed, contains test/sandbox keys only)
STRIPE_SECRET_KEY=sk_test_devkey123
DATABASE_URL=postgres://localhost/myapp_dev

# Production: set via deployment platform (Heroku, AWS, etc.)
# heroku config:set STRIPE_SECRET_KEY=sk_live_realkey
# aws ssm put-parameter --name /myapp/stripe_key --value sk_live_realkey
```

### Level 4: Secrets Manager (2 hours — for production)

```python
# For production, use a secrets manager instead of env vars
# AWS Secrets Manager, HashiCorp Vault, or similar

import boto3
import json
from functools import lru_cache

@lru_cache()
def get_secrets():
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId="myapp/production")
    return json.loads(response["SecretString"])

# Usage in settings.py
secrets = get_secrets()
STRIPE_SECRET_KEY = secrets["stripe_secret_key"]
DATABASE_PASSWORD = secrets["database_password"]
```

## Cleaning Up Git History

If keys were EVER in settings.py, they're in git history. After moving to env vars:

```bash
# 1. Rotate ALL exposed keys immediately
# - Generate new Stripe key, deactivate old one
# - Generate new AWS key, deactivate old one
# - Change all database passwords
# This is the ONLY reliable fix. Scrubbing git history is unreliable.

# 2. Optionally clean git history (belt and suspenders)
# pip install git-filter-repo
# git filter-repo --path settings.py --invert-paths
# WARNING: rewrites all commit hashes, breaks existing clones
```

The bottom line: environment variables take 5 minutes and eliminate the most dangerous exposure channel. There's no excuse for keys in source code.'''
    ),
    (
        "thinking/adversarial-celery-task-security",
        "We use Celery for background jobs and recently exposed a 'run any task' API endpoint for internal tools:\n\n```python\n@app.route('/api/run-task', methods=['POST'])\n@require_auth\ndef run_task():\n    task_name = request.json['task']\n    args = request.json.get('args', [])\n    kwargs = request.json.get('kwargs', {})\n    result = celery_app.send_task(task_name, args=args, kwargs=kwargs)\n    return jsonify({'task_id': result.id})\n```\n\nThis is behind authentication. Is it safe?",
        r'''<think>
"Run any task" API endpoint. Even behind auth, this is dangerous. Let me think about the attack surface.

**Attack vector 1: Arbitrary task execution**
`celery_app.send_task(task_name)` can dispatch ANY registered task — not just the ones you intended. If task_name is "myapp.tasks.delete_all_users", an authenticated user can invoke it. The attacker doesn't need to know the exact name — they can enumerate by trying common patterns.

**Attack vector 2: Celery built-in tasks**
Celery has built-in tasks that could be exploited:
- `celery.backend_cleanup` — clears results
- `celery.chord_unlock` — can mess with chord execution
- Custom tasks from third-party libraries

**Attack vector 3: Argument injection**
Even if you restrict task names, `args` and `kwargs` are fully controlled:
```python
# If a task does: subprocess.run(args[0])
# Attacker sends: {"task": "deploy", "args": ["rm -rf /"]}
```

**Attack vector 4: Resource exhaustion**
An authenticated user could:
- Send millions of tasks → overwhelm workers
- Send tasks with massive payloads → Redis/RabbitMQ memory exhaustion
- Send long-running tasks → worker pool exhaustion

**Attack vector 5: Privilege escalation**
The API is "for internal tools" but:
- Who has auth? All employees? All developers?
- Celery workers often run with elevated privileges (DB access, API keys)
- Running any task = running code with worker privileges

**Attack vector 6: Deserialization attacks**
If Celery uses pickle serializer (default in some configs), crafted args/kwargs could execute arbitrary code during deserialization.

**Even with authentication, this is critically dangerous.** Authentication proves IDENTITY. Authorization (what you're ALLOWED to do) is missing entirely. Any authenticated user can run any task with any arguments.
</think>

This is **critically dangerous** even behind authentication. Authentication proves who you are — it doesn't restrict what you can do. Any authenticated user can run ANY Celery task with ANY arguments.

## The Attack Surface

```python
# What an attacker (any authenticated user) can do:

# 1. Run destructive tasks
requests.post("/api/run-task", json={
    "task": "myapp.tasks.delete_user",
    "kwargs": {"user_id": 1}  # Delete any user
})

# 2. Run admin-only tasks
requests.post("/api/run-task", json={
    "task": "myapp.tasks.export_all_customer_data",
    "args": ["attacker@evil.com"]  # Send data dump to attacker
})

# 3. Enumerate tasks by trying common names
for name in ["delete_all", "reset_db", "send_email", "deploy", "backup"]:
    requests.post("/api/run-task", json={
        "task": f"myapp.tasks.{name}"
    })

# 4. Resource exhaustion
for i in range(1_000_000):
    requests.post("/api/run-task", json={
        "task": "myapp.tasks.heavy_computation",
        "args": [{"data": "x" * 10_000_000}]  # 10MB per task
    })

# 5. Privilege escalation — worker has DB access, API keys, etc.
# Running any task = running code with worker privileges
```

## The Secure Version

```python
from flask import Flask, request, jsonify, abort
from functools import wraps

# DEFENSE 1: Explicit allowlist of runnable tasks
ALLOWED_TASKS = {
    "generate_report": {
        "task": "myapp.tasks.generate_report",
        "allowed_args": ["report_type", "date_from", "date_to"],
        "required_role": "analyst",
    },
    "send_reminder": {
        "task": "myapp.tasks.send_reminder_email",
        "allowed_args": ["user_id", "template"],
        "required_role": "support",
    },
    "recalculate_metrics": {
        "task": "myapp.tasks.recalculate_metrics",
        "allowed_args": ["metric_name", "date"],
        "required_role": "admin",
    },
}

def require_role(role):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if role not in request.user.roles:
                abort(403, f"Requires role: {role}")
            return f(*args, **kwargs)
        return wrapper
    return decorator


@app.route('/api/run-task', methods=['POST'])
@require_auth
def run_task():
    data = request.get_json()
    task_key = data.get('task')

    # DEFENSE 1: Only allow explicitly listed tasks
    if task_key not in ALLOWED_TASKS:
        abort(400, f"Unknown task: {task_key}. Allowed: {list(ALLOWED_TASKS.keys())}")

    task_config = ALLOWED_TASKS[task_key]

    # DEFENSE 2: Check role-based authorization
    required_role = task_config["required_role"]
    if required_role not in request.user.roles:
        abort(403, f"Task '{task_key}' requires role: {required_role}")

    # DEFENSE 3: Validate and filter arguments
    kwargs = {}
    for key, value in data.get('kwargs', {}).items():
        if key not in task_config["allowed_args"]:
            abort(400, f"Argument '{key}' not allowed for task '{task_key}'")
        kwargs[key] = value

    # DEFENSE 4: Rate limiting per user
    rate_key = f"task_rate:{request.user.id}"
    current = cache.incr(rate_key)
    cache.expire(rate_key, 3600)
    if current > 50:  # Max 50 tasks per hour per user
        abort(429, "Rate limit exceeded")

    # DEFENSE 5: Audit logging
    logger.info(
        "Task dispatched: %s by user %s with args %s",
        task_key, request.user.id, kwargs
    )

    # Dispatch the REAL task name (user never sees internal task names)
    result = celery_app.send_task(task_config["task"], kwargs=kwargs)

    return jsonify({
        'task_id': result.id,
        'task': task_key,
        'status': 'queued',
    })
```

## Security Layers

| Defense | What it prevents |
|---------|-----------------|
| Task allowlist | Running arbitrary/destructive tasks |
| Role-based auth | Unauthorized task execution |
| Argument validation | Argument injection attacks |
| Rate limiting | Resource exhaustion |
| Audit logging | Forensics and accountability |
| Internal task names hidden | Information disclosure |

The fundamental rule: **never let user input choose which code to execute.** An allowlist with explicit mappings is the only safe approach for task dispatch APIs.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
