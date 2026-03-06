"""Phase 2B: Advanced Reasoning — Adversarial Self-Testing (Part 6/8)"""

PAIRS = [
    (
        "thinking/adversarial-password-reset-flow",
        "Review this password reset implementation for security issues:\n\n```python\nimport hashlib\nimport time\nfrom flask import Flask, request, jsonify\n\napp = Flask(__name__)\nreset_tokens = {}\n\n@app.route('/forgot-password', methods=['POST'])\ndef forgot_password():\n    email = request.json['email']\n    user = db.get_user_by_email(email)\n    if not user:\n        return jsonify({'error': 'No account with that email'}), 404\n    \n    token = hashlib.md5(f\"{email}{time.time()}\".encode()).hexdigest()\n    reset_tokens[token] = {'user_id': user.id, 'created': time.time()}\n    \n    send_email(email, f\"Reset your password: https://app.com/reset?token={token}\")\n    return jsonify({'message': 'Reset email sent'})\n\n@app.route('/reset-password', methods=['POST'])\ndef reset_password():\n    token = request.json['token']\n    new_password = request.json['new_password']\n    \n    if token not in reset_tokens:\n        return jsonify({'error': 'Invalid token'}), 400\n    \n    token_data = reset_tokens[token]\n    user = db.get_user(token_data['user_id'])\n    user.password = hashlib.sha256(new_password.encode()).hexdigest()\n    db.save(user)\n    \n    return jsonify({'message': 'Password updated'})\n```",
        r'''<think>
Let me systematically attack this password reset implementation. I'll think like an attacker targeting each component.

**Attack vector 1: User enumeration**
The `/forgot-password` endpoint returns a 404 with "No account with that email" for non-existent users. An attacker can enumerate valid email addresses by checking the response code. This leaks which emails are registered.

**Attack vector 2: Weak token generation (CRITICAL)**
`hashlib.md5(f"{email}{time.time()}")` — This is catastrophically weak.
- MD5 is fast and has known collisions
- `time.time()` has limited precision — if I know WHEN the request was made (±1 second), I can brute-force the token in ~1000 attempts
- Email is known to the attacker (they submitted it)
- An attacker can: submit a reset request, note the time, and compute all possible tokens for that second

**Attack vector 3: Token never expires**
There's no expiry check. A token from 6 months ago still works. Reset tokens should expire in 15-30 minutes.

**Attack vector 4: Token not invalidated after use**
After password reset, the token stays in `reset_tokens`. An attacker who intercepts the email later can reuse the token. One-time use is required.

**Attack vector 5: No rate limiting on forgot-password**
An attacker can submit thousands of reset requests, flooding a victim's inbox (email bombing) or brute-forcing tokens.

**Attack vector 6: Insecure password storage (CRITICAL)**
`hashlib.sha256(new_password.encode()).hexdigest()` — unsalted SHA-256. This is trivially crackable with rainbow tables. Passwords must use bcrypt, argon2, or scrypt with salting.

**Attack vector 7: No password complexity validation**
`new_password` could be "a" or "123". No minimum length or complexity check.

**Attack vector 8: In-memory token storage**
`reset_tokens = {}` is a dictionary in memory. Server restart loses all tokens. Multiple server instances don't share tokens. Not production-ready.

**Attack vector 9: Token in URL query parameter**
`?token={token}` in the URL means the token appears in:
- Browser history
- Server access logs
- Referrer headers if the page has external links
- Potentially in proxy logs

**Attack vector 10: No CSRF protection on reset**
The reset endpoint doesn't validate the request origin. An attacker could craft a page that submits a reset request with a known token.

**Attack vector 11: Multiple valid tokens per user**
Each reset request creates a NEW token without invalidating previous ones. An attacker could request 1000 tokens and try them all.

Let me count: 11 distinct attack vectors. This implementation is critically insecure.
</think>

This password reset flow has **11 security vulnerabilities**, several of which are critical. Here's the full attack analysis:

## Critical Vulnerabilities

### 1. Predictable Token Generation (CRITICAL)
```python
# ❌ CURRENT: attacker can compute the token
token = hashlib.md5(f"{email}{time.time()}").hexdigest()
# If attacker knows the email and approximate time (±1 second),
# they only need ~1000 guesses to find the token

# ✅ FIX: cryptographically random token
import secrets
token = secrets.token_urlsafe(32)  # 256 bits of randomness
```

### 2. Unsalted SHA-256 Password Storage (CRITICAL)
```python
# ❌ CURRENT: crackable with rainbow tables in minutes
user.password = hashlib.sha256(new_password.encode()).hexdigest()

# ✅ FIX: use bcrypt with automatic salting
from bcrypt import hashpw, gensalt
user.password = hashpw(new_password.encode(), gensalt(rounds=12))
```

### 3. User Enumeration
```python
# ❌ CURRENT: different response reveals if email exists
if not user:
    return jsonify({'error': 'No account with that email'}), 404

# ✅ FIX: same response regardless
@app.route('/forgot-password', methods=['POST'])
def forgot_password():
    email = request.json.get('email', '')
    user = db.get_user_by_email(email)
    if user:
        token = secrets.token_urlsafe(32)
        # ... create and send token
    # Always return the same response
    return jsonify({'message': 'If an account exists, a reset email has been sent'})
```

## High Severity

### 4. Tokens Never Expire
```python
# ❌ CURRENT: no expiry check at all

# ✅ FIX: 30-minute expiry
@app.route('/reset-password', methods=['POST'])
def reset_password():
    token_data = reset_tokens.get(token)
    if not token_data:
        return jsonify({'error': 'Invalid token'}), 400

    if time.time() - token_data['created'] > 1800:  # 30 minutes
        del reset_tokens[token]
        return jsonify({'error': 'Token expired'}), 400
```

### 5. Token Not Invalidated After Use
```python
# ❌ CURRENT: token remains valid after password reset

# ✅ FIX: delete token after use
    db.save(user)
    del reset_tokens[token]  # One-time use
```

### 6. Multiple Valid Tokens Per User
```python
# ❌ CURRENT: each request creates a new token, old ones remain

# ✅ FIX: invalidate previous tokens for this user
def forgot_password():
    # Remove any existing tokens for this user
    reset_tokens = {
        k: v for k, v in reset_tokens.items()
        if v['user_id'] != user.id
    }
    # Then create new token
```

## Medium Severity

### 7. No Rate Limiting
```python
# ✅ FIX: limit reset requests
from flask_limiter import Limiter
limiter = Limiter(app, key_func=lambda: request.json.get('email', ''))

@app.route('/forgot-password', methods=['POST'])
@limiter.limit("3 per hour")
def forgot_password():
    ...
```

### 8. No Password Validation
```python
# ✅ FIX: enforce minimum requirements
def validate_password(password: str) -> str | None:
    if len(password) < 12:
        return "Password must be at least 12 characters"
    if password.lower() in COMMON_PASSWORDS:
        return "Password is too common"
    return None
```

### 9. Token in URL (Logged Everywhere)
```python
# ❌ CURRENT: token in query string — appears in logs, referrer headers
f"https://app.com/reset?token={token}"

# ✅ FIX: use POST-based flow or fragment
# Option A: token in URL fragment (not sent to server in referrer)
f"https://app.com/reset#{token}"
# Option B: short-lived code that exchanges for a session
```

### 10. In-Memory Token Storage
```python
# ❌ CURRENT: lost on restart, not shared across instances

# ✅ FIX: use Redis with automatic expiry
redis_client.setex(
    f"reset:{token}",
    1800,  # 30 minutes TTL
    json.dumps({"user_id": user.id})
)
```

## Secure Implementation

```python
import secrets
import time
from bcrypt import hashpw, gensalt, checkpw

@app.route('/forgot-password', methods=['POST'])
@limiter.limit("3 per hour")
def forgot_password():
    email = request.json.get('email', '')
    user = db.get_user_by_email(email)

    if user:
        # Invalidate previous tokens
        redis_client.delete(f"reset_user:{user.id}")

        # Cryptographically random token
        token = secrets.token_urlsafe(32)

        # Store with expiry
        redis_client.setex(f"reset:{token}", 1800, str(user.id))
        redis_client.setex(f"reset_user:{user.id}", 1800, token)

        send_email(email, f"Reset link: https://app.com/reset#{token}")

    # Same response regardless
    return jsonify({'message': 'If an account exists, a reset email has been sent'})

@app.route('/reset-password', methods=['POST'])
@limiter.limit("5 per hour")
def reset_password():
    token = request.json.get('token', '')
    new_password = request.json.get('new_password', '')

    error = validate_password(new_password)
    if error:
        return jsonify({'error': error}), 400

    user_id = redis_client.get(f"reset:{token}")
    if not user_id:
        return jsonify({'error': 'Invalid or expired token'}), 400

    user = db.get_user(int(user_id))
    user.password = hashpw(new_password.encode(), gensalt(rounds=12))
    db.save(user)

    # Invalidate token (one-time use)
    redis_client.delete(f"reset:{token}")
    redis_client.delete(f"reset_user:{user.id}")

    # Invalidate all existing sessions
    invalidate_user_sessions(user.id)

    return jsonify({'message': 'Password updated'})
```'''
    ),
    (
        "thinking/adversarial-file-download-endpoint",
        "Is this file download endpoint safe?\n\n```python\nfrom flask import Flask, send_file, request\nimport os\n\napp = Flask(__name__)\nUPLOAD_DIR = '/app/uploads'\n\n@app.route('/download')\ndef download():\n    filename = request.args.get('file')\n    filepath = os.path.join(UPLOAD_DIR, filename)\n    if os.path.exists(filepath):\n        return send_file(filepath)\n    return 'File not found', 404\n```",
        r'''<think>
Let me attack this file download endpoint systematically.

**Attack vector 1: Path traversal (CRITICAL)**
`filename = request.args.get('file')` — no sanitization.
An attacker can send: `?file=../../../etc/passwd`
`os.path.join('/app/uploads', '../../../etc/passwd')` = `/etc/passwd`

Even simpler: `?file=../../app/config.py` → reads source code
Or: `?file=../../etc/shadow` → reads password hashes (if running as root)

`os.path.join` does NOT prevent traversal. It just concatenates.

**Attack vector 2: Null byte injection**
Some older Python versions: `?file=../../../etc/passwd%00.png`
The `%00` null byte could truncate the path after `.png` check (if there was one). Modern Python handles this, but it's worth noting.

**Attack vector 3: Symlink following**
If an attacker can create a symlink in `/app/uploads/` (via another vulnerability), they could create `uploads/evil -> /etc/passwd` and then request `?file=evil`.

**Attack vector 4: No authentication**
Anyone can download any file. No auth check.

**Attack vector 5: No filename parameter = crash**
`request.args.get('file')` returns `None` if not provided.
`os.path.join('/app/uploads', None)` raises `TypeError`.
Unhandled exception → 500 error with potential stack trace leak.

**Attack vector 6: Information disclosure via error messages**
If Flask is in debug mode, the stack trace reveals file paths, Python version, etc.

**Attack vector 7: Content-Type guessing**
`send_file` guesses the content type. An attacker could upload an HTML file, then download it. If served with `text/html`, the browser renders it → stored XSS.

Let me provide a secure version.
</think>

This endpoint has a **critical path traversal vulnerability** and several other issues. An attacker can read ANY file on the server.

## Attack Demonstration

```bash
# Read system files
curl "https://app.com/download?file=../../../etc/passwd"
# → root:x:0:0:root:/root:/bin/bash ...

# Read application source code
curl "https://app.com/download?file=../app.py"
# → entire application source code

# Read environment variables (often contain secrets)
curl "https://app.com/download?file=../../../proc/self/environ"
# → DATABASE_URL=postgres://... SECRET_KEY=... AWS_KEY=...

# Read Docker secrets
curl "https://app.com/download?file=../../../run/secrets/db_password"
```

## All Vulnerabilities

| # | Issue | Severity |
|---|-------|----------|
| 1 | Path traversal — read any file on the server | **Critical** |
| 2 | No authentication — anyone can download | High |
| 3 | Missing `filename` param → unhandled TypeError | Medium |
| 4 | Content-Type guessing → potential XSS | Medium |
| 5 | Symlink following | Medium |
| 6 | No access logging / audit trail | Low |

## Secure Implementation

```python
from flask import Flask, send_file, request, abort
from flask_login import login_required, current_user
import os
import re

app = Flask(__name__)
UPLOAD_DIR = os.path.realpath('/app/uploads')  # Resolve any symlinks


@app.route('/download')
@login_required
def download():
    filename = request.args.get('file')
    if not filename:
        abort(400, 'Missing filename')

    # Defense 1: Strip any path components — only allow bare filenames
    filename = os.path.basename(filename)

    # Defense 2: Validate filename characters (whitelist approach)
    if not re.match(r'^[a-zA-Z0-9_\-][a-zA-Z0-9_\-. ]*$', filename):
        abort(400, 'Invalid filename')

    # Defense 3: Resolve the full path and verify it's under UPLOAD_DIR
    filepath = os.path.realpath(os.path.join(UPLOAD_DIR, filename))
    if not filepath.startswith(UPLOAD_DIR + os.sep):
        abort(403, 'Access denied')

    # Defense 4: Verify file exists and is a regular file (not symlink to outside)
    if not os.path.isfile(filepath):
        abort(404, 'File not found')

    # Defense 5: Verify user has access to this file
    if not user_can_access_file(current_user.id, filename):
        abort(403, 'Access denied')

    # Defense 6: Force safe content type (prevents XSS via HTML files)
    return send_file(
        filepath,
        mimetype='application/octet-stream',  # Force download
        as_attachment=True,
        download_name=filename,  # Sanitized filename
    )
```

## Why Each Defense Matters

```python
# Defense 1: os.path.basename
os.path.basename("../../../etc/passwd")  # → "passwd"
# Strips ALL directory components. Attacker can't traverse.

# Defense 2: Character whitelist
# Blocks: null bytes, unicode tricks, URL encoding remnants

# Defense 3: realpath + startswith
# Catches ANY traversal that basename might miss:
os.path.realpath("/app/uploads/../../etc/passwd")  # → "/etc/passwd"
"/etc/passwd".startswith("/app/uploads/")  # → False → blocked

# Defense 4: isfile check
# Prevents serving directories, devices, or broken symlinks

# Defense 5: Authorization check
# Just because a file exists doesn't mean THIS user should access it

# Defense 6: Content-Type override
# Forces browser to download rather than render (prevents XSS)
```

Defense in depth — even if one layer is bypassed, the next layer catches it. The most critical fix is `os.path.basename()` + `realpath` + `startswith` to prevent path traversal.'''
    ),
    (
        "thinking/adversarial-graphql-endpoint",
        "We just launched a GraphQL API. What security issues should we be worried about that are specific to GraphQL (beyond normal web security)?",
        r'''<think>
GraphQL-specific security issues — let me think about what's unique to GraphQL vs REST.

**Attack vector 1: Introspection in production**
GraphQL has built-in introspection — anyone can query the full schema. In production, this reveals every type, field, relationship, and mutation. It's like publishing your database schema publicly.

**Attack vector 2: Deeply nested queries (DoS)**
GraphQL allows recursive relationships:
```graphql
{ user { friends { friends { friends { friends { ... } } } } } }
```
Each level multiplies the database queries. 10 levels deep with 100 friends each = 100^10 queries. This is a trivial DoS attack.

**Attack vector 3: Query complexity / resource exhaustion**
Even without nesting, a single query can request thousands of fields:
```graphql
{ users(first: 10000) { name email posts { comments { author { ... } } } } }
```

**Attack vector 4: Batched queries**
GraphQL often supports query batching — send 1000 queries in one request. This bypasses per-request rate limiting.

**Attack vector 5: Field-level authorization bypass**
REST: `/admin/users` is clearly an admin endpoint — easy to add auth middleware.
GraphQL: everything goes through `/graphql`. A regular user query might include admin-only fields:
```graphql
{ user(id: "other-user") { email ssn salary } }
```
Authorization must be checked at the FIELD level, not the route level.

**Attack vector 6: SQL injection through arguments**
If resolvers build SQL from GraphQL arguments without parameterization.

**Attack vector 7: Alias-based rate limit bypass**
```graphql
{
  a1: login(user:"admin", pass:"password1")
  a2: login(user:"admin", pass:"password2")
  # ... 1000 login attempts in ONE request
}
```
Each alias executes the resolver separately. Rate limiting by request count is useless.

**Attack vector 8: Persisted queries bypass**
If you implement an allowlist of persisted queries, make sure the server ONLY accepts persisted query IDs in production and rejects arbitrary query strings.

Let me provide practical mitigations for each.
</think>

GraphQL has several unique attack surfaces beyond normal web security. Here are the 8 GraphQL-specific threats and their mitigations:

## 1. Introspection Leaks Your Entire Schema

```python
# ❌ Default: anyone can query your full schema
# POST /graphql
# { __schema { types { name fields { name type { name } } } } }
# → Returns EVERY type, field, mutation, enum in your API

# ✅ Disable introspection in production
from ariadne import make_executable_schema
from ariadne.constants import PLAYGROUND_HTML

schema = make_executable_schema(type_defs, resolvers)

# Strawberry example:
import strawberry
from strawberry.extensions import DisableIntrospection

schema = strawberry.Schema(
    query=Query,
    extensions=[DisableIntrospection] if not settings.DEBUG else [],
)
```

## 2. Deeply Nested Queries (DoS)

```graphql
# ATTACK: exponential database queries
{
  users {
    friends {
      friends {
        friends {
          posts {
            comments {
              author {
                friends { ... }
              }
            }
          }
        }
      }
    }
  }
}
```

```python
# ✅ Limit query depth
from graphql import validation
from graphql.validation import ASTValidationRule

class DepthLimitRule(ASTValidationRule):
    """Reject queries deeper than max_depth."""
    max_depth = 5

    def enter_field(self, node, *args):
        depth = self._get_depth(node)
        if depth > self.max_depth:
            self.report_error(
                GraphQLError(f"Query depth {depth} exceeds maximum {self.max_depth}")
            )

# Apply to schema execution
result = schema.execute(query, validation_rules=[DepthLimitRule])
```

## 3. Query Complexity / Cost Analysis

```python
# ✅ Assign costs to fields, reject expensive queries
field_costs = {
    "users": 10,         # List query
    "posts": 5,          # Nested list
    "comments": 3,       # Deep nesting
    "friends": 8,        # Recursive relationship
}

def calculate_query_cost(query_ast) -> int:
    """Walk the AST and sum field costs."""
    total = 0
    for field in walk_fields(query_ast):
        cost = field_costs.get(field.name.value, 1)
        # Multiply by pagination limit if present
        first_arg = get_argument(field, "first")
        if first_arg:
            cost *= min(int(first_arg.value), 100)
        total += cost
    return total

MAX_QUERY_COST = 500

@app.before_request
def check_query_cost():
    cost = calculate_query_cost(parse(request.json["query"]))
    if cost > MAX_QUERY_COST:
        abort(400, f"Query cost {cost} exceeds limit {MAX_QUERY_COST}")
```

## 4. Alias-Based Brute Force

```graphql
# ATTACK: 1000 login attempts in one request
{
  a1: login(email: "admin@co.com", password: "pass1") { token }
  a2: login(email: "admin@co.com", password: "pass2") { token }
  a3: login(email: "admin@co.com", password: "pass3") { token }
  # ... 997 more
}
```

```python
# ✅ Limit aliases per query
def count_root_fields(query_string: str) -> int:
    doc = parse(query_string)
    for definition in doc.definitions:
        if isinstance(definition, OperationDefinition):
            return len(definition.selection_set.selections)
    return 0

MAX_ALIASES = 10

@app.before_request
def check_aliases():
    count = count_root_fields(request.json["query"])
    if count > MAX_ALIASES:
        abort(400, f"Too many root fields ({count}). Maximum is {MAX_ALIASES}")
```

## 5. Field-Level Authorization

```python
# ❌ WRONG: route-level auth (doesn't work for GraphQL)
@app.route('/graphql')
@login_required
def graphql():  # ALL or nothing — can't protect individual fields

# ✅ RIGHT: field-level authorization in resolvers
@strawberry.type
class User:
    name: str
    email: str

    @strawberry.field
    def salary(self, info: strawberry.types.Info) -> float | None:
        # Only the user themselves or HR can see salary
        current_user = info.context["user"]
        if current_user.id != self.id and "hr" not in current_user.roles:
            raise PermissionError("Not authorized to view salary")
        return self._salary

    @strawberry.field
    def ssn(self, info: strawberry.types.Info) -> str | None:
        # Only the user themselves can see SSN
        if info.context["user"].id != self.id:
            return None  # Or raise error
        return self._ssn
```

## 6. Batched Query Abuse

```python
# ✅ Limit batch size
@app.before_request
def limit_batch():
    if isinstance(request.json, list):
        if len(request.json) > 5:
            abort(400, "Maximum 5 queries per batch")
```

## Security Checklist for GraphQL APIs

```markdown
- [ ] Introspection disabled in production
- [ ] Query depth limited (max 5-7 levels)
- [ ] Query cost analysis with rejection threshold
- [ ] Root field/alias count limited (max 10)
- [ ] Batch query size limited
- [ ] Field-level authorization on sensitive fields
- [ ] Rate limiting by query complexity, not just request count
- [ ] Persisted queries in production (optional but strongest defense)
- [ ] Request timeout (30s max per query)
- [ ] Error messages don't leak schema details
```'''
    ),
    (
        "thinking/adversarial-webhook-receiver",
        "We receive webhooks from Stripe and process payments. Here's our handler:\n\n```python\n@app.route('/webhooks/stripe', methods=['POST'])\ndef stripe_webhook():\n    event = request.get_json()\n    \n    if event['type'] == 'payment_intent.succeeded':\n        payment = event['data']['object']\n        order = db.get_order(payment['metadata']['order_id'])\n        order.status = 'paid'\n        order.amount_paid = payment['amount'] / 100\n        db.save(order)\n    \n    return '', 200\n```\n\nIs this secure?",
        r'''<think>
Let me attack this webhook handler systematically.

**Attack vector 1: No signature verification (CRITICAL)**
The handler doesn't verify the `Stripe-Signature` header. ANYONE can send a POST to `/webhooks/stripe` with a fake event. An attacker can:
- Mark any order as "paid" without paying
- Set any amount they want
- Process fake refunds

This is the #1 webhook security issue and it's a complete authentication bypass.

**Attack vector 2: Direct trust of payload data**
Even with signature verification, the handler trusts `payment['amount']` from the webhook. But Stripe recommends verifying amounts against your records, not just trusting the webhook payload.

**Attack vector 3: No idempotency**
If Stripe retries the webhook (which it does), the handler processes it again. If `order.amount_paid` is additive, the order could be double-charged or double-credited.

**Attack vector 4: No event type validation**
The handler only checks for `payment_intent.succeeded` but returns 200 for all events. This is actually fine (Stripe recommends returning 200 for unhandled events), but the handler doesn't validate the event structure.

**Attack vector 5: Race condition**
Two webhook deliveries for the same event could race. Both read order.status = 'pending', both set it to 'paid'. If there are side effects (like sending confirmation email), they fire twice.

**Attack vector 6: Order ID injection**
`payment['metadata']['order_id']` — if this isn't validated, an attacker (with signature bypass) could reference any order ID. Even with signatures, if the metadata is set client-side, a malicious user could set someone else's order_id.

**Attack vector 7: No error handling**
If `db.get_order()` returns None (order doesn't exist), `order.status = 'paid'` raises AttributeError. The 500 response causes Stripe to retry, creating an infinite retry loop.

**Attack vector 8: Missing replay protection**
Without tracking processed event IDs, an attacker who captures a legitimate webhook could replay it.
</think>

This webhook handler has a **critical authentication bypass** — anyone can forge payment confirmations. Here's the full analysis:

## Critical: No Signature Verification

```bash
# ATTACK: Mark any order as paid for free
curl -X POST https://app.com/webhooks/stripe \
  -H "Content-Type: application/json" \
  -d '{
    "type": "payment_intent.succeeded",
    "data": {
      "object": {
        "amount": 1,
        "metadata": {"order_id": "ORD-12345"}
      }
    }
  }'
# → Order ORD-12345 is now marked as "paid" for $0.01
```

## All Vulnerabilities

| # | Issue | Impact |
|---|-------|--------|
| 1 | No Stripe signature verification | Anyone can forge payments |
| 2 | No idempotency check | Double-processing on retries |
| 3 | No amount verification | Attacker controls paid amount |
| 4 | No error handling | Bad data causes retry loops |
| 5 | Race condition | Duplicate side effects |
| 6 | No replay protection | Captured webhooks can be replayed |

## Secure Implementation

```python
import stripe
import json
import logging
from flask import Flask, request, abort

logger = logging.getLogger(__name__)
stripe.api_key = os.environ["STRIPE_SECRET_KEY"]
WEBHOOK_SECRET = os.environ["STRIPE_WEBHOOK_SECRET"]

@app.route('/webhooks/stripe', methods=['POST'])
def stripe_webhook():
    # DEFENSE 1: Verify Stripe signature
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, WEBHOOK_SECRET
        )
    except ValueError:
        logger.warning("Invalid webhook payload")
        abort(400)
    except stripe.error.SignatureVerificationError:
        logger.warning("Invalid webhook signature")
        abort(400)

    # DEFENSE 2: Idempotency — track processed events
    event_id = event['id']
    if db.webhook_event_exists(event_id):
        logger.info("Duplicate webhook event %s, skipping", event_id)
        return '', 200

    # Record event BEFORE processing (prevents race condition)
    db.record_webhook_event(event_id, event['type'])

    try:
        if event['type'] == 'payment_intent.succeeded':
            handle_payment_succeeded(event['data']['object'])
        # Handle other event types...
    except Exception:
        logger.exception("Error processing webhook event %s", event_id)
        # Return 200 anyway to prevent Stripe retries on app errors
        # The event is recorded; investigate and reprocess manually

    return '', 200


def handle_payment_succeeded(payment_intent):
    order_id = payment_intent.get('metadata', {}).get('order_id')
    if not order_id:
        logger.error("Payment %s has no order_id in metadata", payment_intent['id'])
        return

    order = db.get_order(order_id)
    if not order:
        logger.error("Order %s not found for payment %s", order_id, payment_intent['id'])
        return

    # DEFENSE 3: Verify amount matches what we expected
    paid_amount = payment_intent['amount'] / 100
    if abs(paid_amount - order.expected_amount) > 0.01:
        logger.error(
            "Amount mismatch for order %s: expected %.2f, got %.2f",
            order_id, order.expected_amount, paid_amount
        )
        # Flag for manual review instead of auto-completing
        order.status = 'amount_mismatch'
        order.amount_paid = paid_amount
        db.save(order)
        return

    # DEFENSE 4: Only transition from expected states
    if order.status not in ('pending', 'payment_processing'):
        logger.warning(
            "Order %s in unexpected state '%s' for payment success",
            order_id, order.status
        )
        return

    order.status = 'paid'
    order.amount_paid = paid_amount
    order.stripe_payment_id = payment_intent['id']
    db.save(order)
```

The golden rule for webhooks: **never trust the caller's identity without cryptographic verification**. Stripe signatures use HMAC-SHA256 — without checking them, your payment processing is completely unauthenticated.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
