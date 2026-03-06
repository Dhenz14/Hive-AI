"""Phase 3C: Metacognition — Socratic Self-Questioning (Part 6)

Scenarios: "What would the next maintainer think?", "Am I testing what
matters?", additional "Am I solving the right problem?"
"""

PAIRS = [
    (
        "thinking/meta-socratic-maintainer-global-state",
        r'''I use global variables to share configuration across my Flask app:

```python
# config.py
db_connection = None
cache_client = None
api_keys = {}
current_user = None
request_count = 0

def init_app():
    global db_connection, cache_client, api_keys
    db_connection = create_connection(DATABASE_URL)
    cache_client = Redis(REDIS_URL)
    api_keys = load_api_keys()
```

Then I import these wherever needed: `from config import db_connection, current_user`. Is this fine?''',
        r'''<think>
My initial approach: Global config is common in Python...

Q: What would the next maintainer think of this?
A: They would:
  1. Wonder what sets `current_user` — it could be set from anywhere
  2. Be confused about initialization order — must call init_app() before imports use the globals
  3. Not know which modules depend on which globals
  4. Be afraid to modify any global because side effects are invisible

Q: Is `current_user` as a global safe?
A: NO. In a multi-threaded Flask app, `current_user` is shared across ALL requests. User A's request sets current_user = "Alice", then User B's request reads current_user and sees "Alice" — complete security breach. This is why Flask has `g` and thread-local storage.

Q: What about `request_count`?
A: Same problem. `request_count += 1` is not thread-safe. Race condition → inaccurate counts. And with multiple gunicorn workers, each worker has its own count.

Q: What happens in tests?
A: Tests need to call init_app() or set globals manually. Tests can't run in parallel because they share globals. One test modifies db_connection and breaks another test.

Q: What's the Flask-idiomatic way?
A: Flask has patterns for all of these:
  - db_connection → Flask-SQLAlchemy (app.extensions)
  - cache_client → Flask-Caching (app.extensions)
  - api_keys → app.config
  - current_user → flask.g or flask-login.current_user (thread-safe)
  - request_count → middleware or Redis

The globals pattern breaks in every production scenario.
</think>

**This is dangerous.** The `current_user` global is a **security vulnerability** in multi-threaded Flask, and the other globals break in production.

**Security issue — `current_user` shared across requests:**
```python
# Thread 1 (User Alice): current_user = "Alice"
# Thread 2 (User Bob):   reads current_user → sees "Alice"!
# Bob now has Alice's permissions
```

**Flask-idiomatic approach:**

```python
# config.py — use app.config for static config
class Config:
    DATABASE_URL = os.environ['DATABASE_URL']
    REDIS_URL = os.environ['REDIS_URL']

# extensions.py — use Flask extensions
from flask_sqlalchemy import SQLAlchemy
from flask_caching import Cache

db = SQLAlchemy()
cache = Cache()

def init_app(app):
    db.init_app(app)
    cache.init_app(app)

# Use flask.g for per-request data (thread-safe)
from flask import g

@app.before_request
def set_current_user():
    g.current_user = get_user_from_token(request.headers.get('Authorization'))

# Access in views:
@app.route('/profile')
def profile():
    return {'name': g.current_user.name}  # Thread-safe
```

**What each global should become:**

| Global | Problem | Correct pattern |
|--------|---------|----------------|
| `current_user` | Shared across threads = security hole | `flask.g` or `flask_login.current_user` |
| `request_count` | Race condition + per-worker only | Redis INCR or middleware |
| `db_connection` | One connection for all requests | Connection pool (SQLAlchemy) |
| `cache_client` | Initialization order dependency | Flask extension pattern |
| `api_keys` | Mutable global dict | `app.config` (immutable) |

**Rule**: If the data is per-request, use `flask.g`. If it's app-wide config, use `app.config`. If it's a service connection, use Flask extensions with `init_app()`.'''
    ),
    (
        "thinking/meta-socratic-right-problem-auth",
        r'''Users are complaining they keep getting logged out of our web app. My team lead thinks we need to increase the session timeout from 30 minutes to 24 hours. Should we?''',
        r'''<think>
Q: Am I solving the right problem? WHY are users getting logged out?

Q: Is the session actually timing out after 30 minutes?
A: "Users keep getting logged out" doesn't necessarily mean the timeout is too short. Possible causes:
  1. Session timeout is 30 min of INACTIVITY — if users are active and still getting logged out, the timeout isn't the issue
  2. Session storage is failing (Redis connection drops, session table full)
  3. Cookies being cleared by browser settings or extensions
  4. Load balancer routing to different servers with different session stores
  5. Session fixation protection is regenerating session IDs too aggressively
  6. CSRF token validation failing and being confused with "logged out"
  7. Authentication cookies not set with correct domain/path
  8. HTTPS/HTTP mismatch — secure cookies dropped on HTTP requests

Q: Would increasing timeout to 24 hours even fix it?
A: If users are being logged out after 5 minutes of activity, a 24-hour timeout won't help — the root cause is something else.

Q: What are the RISKS of a 24-hour session?
A:
  - Shared computers: user walks away, next person has access for 24 hours
  - Stolen session cookies are valid 48x longer
  - Compliance issues (PCI, HIPAA may require shorter timeouts)
  - More sessions to store (memory/storage cost)

Q: What should we do first?
A: INVESTIGATE the actual cause before changing timeouts:
  1. Check session logs — are sessions being destroyed or expired?
  2. Check if the issue correlates with deployments (new deploy = new session store)
  3. Check browser console for cookie issues
  4. Check if it happens on specific browsers/devices
  5. Check load balancer session affinity

Don't increase attack surface area to mask a bug.
</think>

**Don't increase the timeout yet.** First find out WHY users are being logged out — the timeout may not be the problem.

**Investigate before changing anything:**

1. **Check session logs**: Are sessions expiring or being destroyed?
   ```python
   @app.before_request
   def log_session():
       if not session.get('user_id') and request.cookies.get('session'):
           logger.warning("Session cookie exists but session is empty",
               extra={'path': request.path, 'user_agent': request.user_agent})
   ```

2. **Common non-timeout causes:**

| Symptom | Likely cause |
|---------|-------------|
| Logged out on every deploy | Session store (Redis) restarted with deploy |
| Logged out randomly while active | Load balancer routing to server without session |
| Logged out on specific pages | CSRF validation failing |
| Logged out switching HTTP/HTTPS | Secure cookie flag + mixed content |
| Logged out on mobile only | Cookie settings incompatible with mobile browser |

3. **Quick diagnostics:**
   ```bash
   # Check if sessions exist in Redis
   redis-cli KEYS "session:*" | wc -l

   # Check if sessions expire early
   redis-cli TTL "session:<user_session_id>"

   # Check recent session destruction events
   grep "session destroyed\|session expired" app.log | tail -20
   ```

**Risks of 24-hour sessions:**
- Shared/public computers: 24-hour window for unauthorized access
- Session hijacking: stolen cookies valid 48x longer
- Compliance: PCI DSS requires 15-minute idle timeout for payment systems

**Better alternatives if timeout IS the issue:**
- **Sliding expiration**: Reset 30-min timer on each request (most users stay logged in naturally)
- **Remember me**: Optional "keep me logged in" checkbox with a separate long-lived token
- **Refresh tokens**: Short session (30 min) + refresh token (7 days) — balances security and convenience'''
    ),
    (
        "thinking/meta-socratic-testing-auth-bypass",
        r'''I wrote tests for our authentication middleware. Here they are:

```python
def test_login_success(client):
    response = client.post('/login', json={
        'username': 'admin', 'password': 'admin123'
    })
    assert response.status_code == 200
    assert 'token' in response.json

def test_login_wrong_password(client):
    response = client.post('/login', json={
        'username': 'admin', 'password': 'wrong'
    })
    assert response.status_code == 401

def test_protected_with_token(client):
    token = get_test_token('admin')
    response = client.get('/protected', headers={
        'Authorization': f'Bearer {token}'
    })
    assert response.status_code == 200

def test_protected_without_token(client):
    response = client.get('/protected')
    assert response.status_code == 401
```

Are these sufficient tests for auth?''',
        r'''<think>
My initial approach: Login success, wrong password, with/without token — covers the basics.

Q: Am I testing what matters or what's easy to test?
A: These tests verify the HAPPY PATHS and ONE failure case. Auth is a security boundary — the tests should be adversarial.

Q: What auth bypass techniques are NOT tested?
A:
  1. Expired token — does it actually reject expired tokens?
  2. Tampered token — modified JWT still accepted?
  3. Token for deleted user — user deleted but token still valid?
  4. Token for deactivated user — user banned but token works?
  5. Wrong algorithm — JWT signed with 'none' algorithm?
  6. SQL injection in username — `admin' OR '1'='1`
  7. Case sensitivity — is 'Admin' the same as 'admin'?
  8. Empty token — `Authorization: Bearer ` (empty)
  9. Brute force — is there rate limiting on login?
  10. Token in URL — does it accept tokens in query params? (logged in access logs)

Q: What about the token generation?
A: `get_test_token('admin')` creates a valid token in tests. But does it use the same signing key and algorithm as production? If the test helper generates tokens differently, the test doesn't prove production works.

Q: What about authorization (not just authentication)?
A: The tests verify "can access /protected" but not "can regular user access /admin". Authentication ≠ authorization.

Q: What would a penetration tester try?
A: All of the above, plus:
  - Token reuse across environments (staging token on production)
  - Race conditions during password change
  - Password reset token enumeration

These 4 tests provide false security confidence.
</think>

**These tests only cover the easy cases.** Authentication is a security boundary — you need adversarial tests.

**Critical missing tests:**

```python
def test_expired_token_rejected(client):
    """Expired tokens must not grant access."""
    token = create_token('admin', expires_in=-60)  # Already expired
    response = client.get('/protected',
        headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 401

def test_tampered_token_rejected(client):
    """Modified tokens must not be accepted."""
    token = get_test_token('admin')
    tampered = token[:-5] + 'XXXXX'  # Corrupt signature
    response = client.get('/protected',
        headers={'Authorization': f'Bearer {tampered}'})
    assert response.status_code == 401

def test_deleted_user_token_rejected(client, db):
    """Tokens for deleted users must not work."""
    token = get_test_token('admin')
    db.execute("DELETE FROM users WHERE username = 'admin'")
    response = client.get('/protected',
        headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 401

def test_deactivated_user_rejected(client, db):
    """Banned/deactivated users must not have access."""
    token = get_test_token('admin')
    db.execute("UPDATE users SET active = false WHERE username = 'admin'")
    response = client.get('/protected',
        headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 403

def test_empty_token_rejected(client):
    response = client.get('/protected',
        headers={'Authorization': 'Bearer '})
    assert response.status_code == 401

def test_sql_injection_in_login(client):
    response = client.post('/login', json={
        'username': "admin' OR '1'='1", 'password': 'anything'
    })
    assert response.status_code == 401  # NOT 200

def test_regular_user_cannot_access_admin(client):
    """Authorization, not just authentication."""
    token = get_test_token('regular_user')
    response = client.get('/admin',
        headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 403

def test_none_algorithm_rejected(client):
    """JWT 'none' algorithm bypass must not work."""
    # Create token with alg=none (no signature)
    import jwt
    token = jwt.encode({'sub': 'admin'}, '', algorithm='none')
    response = client.get('/protected',
        headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 401
```

**Auth testing priority:**
1. Token expiry (most common real-world issue)
2. Deleted/deactivated users
3. Authorization (role-based access)
4. Token tampering
5. Input injection
6. Algorithm confusion attacks'''
    ),
    (
        "thinking/meta-socratic-blind-spots-error-handling",
        r'''I'm building a REST API and I handle errors like this in every endpoint:

```python
@app.route('/users/<int:user_id>')
def get_user(user_id):
    try:
        user = User.query.get(user_id)
        if not user:
            return jsonify({'error': 'User not found'}), 404
        return jsonify(user.to_dict())
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/orders', methods=['POST'])
def create_order():
    try:
        data = request.get_json()
        order = Order.create(data)
        return jsonify(order.to_dict()), 201
    except Exception as e:
        return jsonify({'error': str(e)}), 500
```

Clean and consistent error handling, right?''',
        r'''<think>
My initial approach: Try/except in every endpoint, return JSON errors. Looks consistent.

Q: What am I not considering? Let me check for blind spots.

Q: Is `str(e)` safe to expose?
A: NO. Exception messages can contain:
  - Database connection strings: `OperationalError: could not connect to postgres://admin:password123@db:5432`
  - SQL queries: `ProgrammingError: relation "users" does not exist`
  - File paths: `FileNotFoundError: /app/config/secrets.json`
  - Stack traces in some exceptions
  This is information disclosure — tells attackers about your database, file structure, and internal workings.

Q: Is catching all exceptions with `except Exception` correct?
A: It catches everything — including bugs that should crash loudly. If there's a TypeError because of a code bug, the user gets a generic 500 instead of a proper error, and the developer never sees the actual error.

Q: Is this DRY?
A: The same try/except pattern is copied in EVERY endpoint. Flask has error handlers for this.

Q: What about validation errors vs server errors?
A: Everything returns 500. But:
  - Missing required field → should be 422
  - Invalid data type → should be 400
  - Duplicate entry → should be 409
  - Permission denied → should be 403
  The bare `except Exception` can't distinguish these.

Q: What about logging?
A: Errors are returned to the user but NOT LOGGED. If the database goes down, you'd see it in client responses but have no server-side record.

Q: What about errors outside endpoints?
A: 404 for unknown routes, 405 for wrong methods — these bypass the try/except and return HTML error pages, not JSON. Inconsistent API.
</think>

**Several blind spots.** The pattern looks clean but has security, debugging, and consistency issues.

**Issue 1: Information disclosure**
```python
# str(e) can leak sensitive info:
except Exception as e:
    return jsonify({'error': str(e)}), 500
    # Could return: "OperationalError: could not connect to
    #   postgres://admin:p4ssw0rd@db.internal:5432/myapp"
```

**Issue 2: No logging — errors vanish**
```python
# Errors returned to client but never logged on server
# You'll never know your DB went down until users complain
```

**Issue 3: All errors are 500**
```python
# Validation error? 500. Permission error? 500. Duplicate? 500.
# Client can't distinguish between "fix your input" and "server is broken"
```

**Fix: use Flask error handlers (DRY and secure):**

```python
import logging

logger = logging.getLogger(__name__)

class APIError(Exception):
    def __init__(self, message, status_code=400):
        self.message = message
        self.status_code = status_code

@app.errorhandler(APIError)
def handle_api_error(e):
    return jsonify({'error': e.message}), e.status_code

@app.errorhandler(404)
def handle_404(e):
    return jsonify({'error': 'Resource not found'}), 404

@app.errorhandler(500)
def handle_500(e):
    logger.exception("Internal server error")  # Log the real error
    return jsonify({'error': 'Internal server error'}), 500  # Generic message to client

# Clean endpoints — no try/except needed:
@app.route('/users/<int:user_id>')
def get_user(user_id):
    user = User.query.get(user_id)
    if not user:
        raise APIError('User not found', 404)
    return jsonify(user.to_dict())

@app.route('/orders', methods=['POST'])
def create_order():
    data = request.get_json()
    if not data or 'product_id' not in data:
        raise APIError('product_id is required', 422)
    order = Order.create(data)
    return jsonify(order.to_dict()), 201
```

**What this fixes:**
- **Security**: Generic message to client, real error in logs
- **Logging**: `logger.exception()` captures full traceback
- **Status codes**: `APIError` with specific status codes
- **DRY**: Error handling defined once, not in every endpoint
- **Consistency**: All errors return JSON, including 404/405'''
    ),
    (
        "thinking/meta-socratic-not-considering-deployment",
        r'''I built a Python web app that works perfectly on my laptop. Here's my setup:

```python
# app.py
from flask import Flask
app = Flask(__name__)

if __name__ == '__main__':
    app.run(debug=True)
```

I have a `requirements.txt` and the code in a git repo. I'm ready to deploy to a VPS. What do I need?''',
        r'''<think>
My initial approach: The app works locally, just need to deploy it.

Q: What am I not considering about the gap between laptop and production?
A: Many things:
  1. Flask's development server is NOT for production — single-threaded, auto-reloads, debug mode exposes interactive debugger
  2. No process manager — if the app crashes, it stays dead
  3. No reverse proxy — can't handle TLS, static files efficiently, or concurrent connections
  4. debug=True in production = remote code execution vulnerability (Werkzeug debugger)

Q: What's the minimum viable production setup?
A:
  - WSGI server: gunicorn (replaces Flask dev server)
  - Reverse proxy: Nginx or Caddy (TLS, static files, buffering)
  - Process manager: systemd (restarts on crash)
  - Environment config: don't hardcode secrets

Q: What about the database?
A: If using SQLite on laptop, it won't work with multiple gunicorn workers (concurrent writes). Need PostgreSQL for production.

Q: What about security?
A:
  - debug=True must be FALSE
  - SECRET_KEY must be random, not default
  - HTTPS required
  - Firewall — only expose ports 80/443
  - No root user for running the app

Q: What about reliability?
A:
  - What if the VPS reboots? → systemd auto-start
  - What if the app crashes? → systemd restart
  - What if disk fills up? → log rotation
  - What if traffic spikes? → gunicorn workers

Q: What about deployment process?
A: Currently: SSH in, git pull, restart. Need a repeatable process.

The gap between "works on my laptop" and "runs in production" is significant.
</think>

**The gap between laptop and production is bigger than you think.** Here's the minimum viable production setup:

**Critical: `debug=True` is a security vulnerability**
```python
# debug=True exposes Werkzeug interactive debugger
# Anyone can execute arbitrary Python code on your server
# NEVER use debug=True in production
```

**Minimum production setup:**

```bash
# 1. Install gunicorn (production WSGI server)
pip install gunicorn

# 2. Run with gunicorn instead of flask dev server
gunicorn -w 4 -b 0.0.0.0:8000 app:app
```

```nginx
# 3. Nginx reverse proxy (/etc/nginx/sites-available/myapp)
server {
    listen 80;
    server_name myapp.com;
    return 301 https://$server_name$request_uri;
}
server {
    listen 443 ssl;
    server_name myapp.com;
    ssl_certificate /etc/letsencrypt/live/myapp.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/myapp.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
    location /static/ {
        alias /var/www/myapp/static/;
    }
}
```

```ini
# 4. Systemd service (/etc/systemd/system/myapp.service)
[Unit]
Description=My Flask App
After=network.target

[Service]
User=www-data
WorkingDirectory=/var/www/myapp
ExecStart=/var/www/myapp/venv/bin/gunicorn -w 4 -b 127.0.0.1:8000 app:app
Restart=always
Environment=FLASK_ENV=production
EnvironmentFile=/var/www/myapp/.env

[Install]
WantedBy=multi-user.target
```

```python
# 5. Production config (app.py)
import os
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ['SECRET_KEY']  # Not hardcoded
app.config['DEBUG'] = False  # NEVER True in production
```

**Deployment checklist:**

| Concern | Dev | Production |
|---------|-----|-----------|
| Server | Flask dev server | gunicorn |
| Proxy | None | Nginx/Caddy |
| TLS | None | Let's Encrypt |
| Process manager | Manual | systemd |
| Debug mode | True | **False** |
| Database | SQLite | PostgreSQL |
| Secret key | Hardcoded | Environment variable |
| Logging | Console | File + rotation |
| Restart on crash | Manual | Automatic |'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
