"""Phase 3C: Metacognition — Socratic Self-Questioning (Part 12)

Final pairs to complete Phase 3C at 60 total.
"""

PAIRS = [
    (
        "thinking/meta-socratic-coupling-database-schema",
        r'''My API directly returns database columns as JSON fields:

```python
@app.route('/users/<int:id>')
def get_user(id):
    user = db.execute("SELECT * FROM users WHERE id = %s", (id,)).fetchone()
    return jsonify(dict(user))

# Returns:
# {
#   "id": 1,
#   "first_name": "Alice",
#   "last_name": "Smith",
#   "password_hash": "$2b$12$...",
#   "internal_notes": "VIP customer, special pricing",
#   "created_at": "2024-01-15T10:30:00",
#   "updated_at": "2024-01-20T14:22:00",
#   "stripe_customer_id": "cus_123abc",
#   "failed_login_attempts": 3
# }
```

This is the simplest possible API. Any problems?''',
        r'''<think>
Q: Am I introducing tight coupling? Let me think about what this exposes.

Q: Is the API response coupled to the database schema?
A: Completely. `SELECT *` returns ALL columns. `dict(user)` serializes ALL of them. The API response IS the database row.

Q: What sensitive data is being leaked?
A:
  - `password_hash` — exposing hashed passwords allows offline brute-force attacks
  - `internal_notes` — "VIP customer, special pricing" is internal business info
  - `stripe_customer_id` — Stripe customer IDs should be kept server-side
  - `failed_login_attempts` — tells an attacker how close they are to account lockout

Q: What happens when the database schema changes?
A: - Adding a column → automatically exposed in API (could leak new sensitive data)
  - Renaming a column → API field names change, breaking all clients
  - Removing a column → API field disappears, breaking all clients

Q: Can clients rely on the API shape?
A: No. Any database migration changes the API. Schema and API evolve together when they should be independent.

Q: What's the fix?
A: Explicit field mapping. Choose exactly which fields to expose and what to name them. Database and API are independent layers.

This is the most common mistake in API design.
</think>

**Critical security and design issues.** You're leaking sensitive data and coupling your API to your database schema.

**Sensitive data being leaked:**
```json
{
    "password_hash": "$2b$12$...",         // Enables offline brute-force
    "internal_notes": "VIP, special pricing", // Business secrets
    "stripe_customer_id": "cus_123abc",     // Payment system internals
    "failed_login_attempts": 3              // Attack intelligence
}
```

**Fix: Explicit field mapping**
```python
@app.route('/users/<int:id>')
def get_user(id):
    user = User.query.get_or_404(id)
    return jsonify({
        'id': user.id,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'created_at': user.created_at.isoformat(),
    })
    # password_hash, internal_notes, stripe_customer_id: NOT exposed
```

**Or use a serializer:**
```python
from marshmallow import Schema, fields

class UserSchema(Schema):
    id = fields.Int()
    first_name = fields.Str()
    last_name = fields.Str()
    full_name = fields.Method('get_full_name')
    created_at = fields.DateTime()

    def get_full_name(self, user):
        return f"{user.first_name} {user.last_name}"

user_schema = UserSchema()

@app.route('/users/<int:id>')
def get_user(id):
    user = User.query.get_or_404(id)
    return jsonify(user_schema.dump(user))
```

**Why explicit mapping matters:**
- **Security**: Control exactly what's exposed
- **Stability**: Database changes don't break the API
- **Flexibility**: API fields can differ from DB columns (full_name from first + last)
- **Documentation**: Schema IS the API contract

**Never use `SELECT *` in API endpoints.** Always select specific columns and map them explicitly to API fields.'''
    ),
    (
        "thinking/meta-socratic-not-considering-permissions",
        r'''I built an API endpoint to let users update their profile:

```python
@app.route('/users/<int:user_id>', methods=['PUT'])
@login_required
def update_user(user_id):
    data = request.get_json()
    user = User.query.get_or_404(user_id)

    for key, value in data.items():
        setattr(user, key, value)

    db.session.commit()
    return jsonify(user.to_dict())
```

Clean and flexible — accepts any fields. Any issues?''',
        r'''<think>
Q: What am I not considering?

Q: Can user A update user B's profile?
A: YES. The endpoint takes user_id from the URL. Any logged-in user can update ANY user's profile by changing the user_id. No ownership check.

Q: What fields can be updated?
A: ANY field. `setattr(user, key, value)` accepts anything. An attacker could send:
  - `{"role": "admin"}` → privilege escalation
  - `{"password_hash": "known_hash"}` → account takeover
  - `{"email": "attacker@evil.com"}` → steal the account
  - `{"is_active": false}` → disable any user
  - `{"balance": 999999}` → give themselves money

This is a mass assignment vulnerability (one of OWASP top 10).

Q: Is there any validation?
A: None. Whatever JSON is sent is directly applied to the model.

Q: What's the blast radius?
A: Total. Any authenticated user can:
  1. Make themselves admin
  2. Take over any account
  3. Modify any user's data
  4. Disable any user

This is a critical security vulnerability.
</think>

**Two critical security vulnerabilities:**

**1. No authorization — any user can update anyone:**
```bash
# User with id=1 can update user with id=2
curl -X PUT /users/2 -d '{"name": "hacked"}' -H "Authorization: Bearer user1_token"
```

**2. Mass assignment — any field can be modified:**
```bash
# Regular user makes themselves admin:
curl -X PUT /users/1 -d '{"role": "admin"}'

# Attacker takes over account:
curl -X PUT /users/42 -d '{"email": "attacker@evil.com"}'

# Attacker resets password hash:
curl -X PUT /users/42 -d '{"password_hash": "$2b$12$known"}'
```

**Fixed version:**
```python
@app.route('/users/me', methods=['PUT'])  # No user_id in URL
@login_required
def update_profile():
    data = request.get_json()
    user = current_user  # Can only update YOUR OWN profile

    # Whitelist — only allowed fields
    ALLOWED_FIELDS = {'name', 'bio', 'avatar_url'}
    for key, value in data.items():
        if key in ALLOWED_FIELDS:
            setattr(user, key, value)

    db.session.commit()
    return jsonify(user.to_dict())
```

**Key fixes:**
1. **`/users/me`** instead of `/users/<id>` — users can only update themselves
2. **Whitelist allowed fields** — only `name`, `bio`, `avatar_url` can be modified
3. **`current_user`** from auth — can't impersonate another user

**For admin-only operations:**
```python
@app.route('/admin/users/<int:user_id>', methods=['PUT'])
@login_required
@admin_required  # Separate endpoint for admins
def admin_update_user(user_id):
    ...
```

**Rule**: Never use `setattr` with user input without a field whitelist. This is called "mass assignment" and it's a top-10 vulnerability.'''
    ),
    (
        "thinking/meta-socratic-blind-spots-logging",
        r'''I log everything in my API for debugging:

```python
@app.before_request
def log_request():
    logger.info(f"Request: {request.method} {request.url}")
    logger.info(f"Headers: {dict(request.headers)}")
    logger.info(f"Body: {request.get_data(as_text=True)}")

@app.after_request
def log_response(response):
    logger.info(f"Response: {response.status_code}")
    logger.info(f"Response body: {response.get_data(as_text=True)}")
    return response
```

Comprehensive logging for debugging. Good practice?''',
        r'''<think>
Q: What am I not considering?

Q: What's in those request bodies?
A: Login requests contain PASSWORDS in plain text:
  `Body: {"email": "alice@example.com", "password": "MySecretPass123!"}`
  Now the password is in the log file, the log aggregator, any log backup, and potentially shown to any developer with log access.

Q: What's in those headers?
A: Authorization headers contain tokens/credentials:
  `Headers: {'Authorization': 'Bearer eyJ...'}`
  Anyone with log access can impersonate users.

Q: What's in those response bodies?
A: Could include:
  - User personal data (GDPR violation)
  - API keys or tokens in responses
  - Financial data
  - Medical data (HIPAA violation)

Q: What about log volume?
A: Logging EVERY request body and response body for a busy API:
  - 1000 requests/hour × average 1KB body × 2 (req + resp) = 2MB/hour of logs
  - That's 48MB/day, 1.4GB/month of verbose logs
  - And most of it is never looked at

Q: What about PII in URLs?
A: `GET /users/alice@example.com/orders` — email addresses in URLs get logged.

Q: What should be logged?
A: Method, path, status code, duration, request ID. NOT bodies, NOT auth headers.

This logging creates security vulnerabilities and compliance issues.
</think>

**This is a security vulnerability and potential compliance violation.** You're logging passwords, tokens, and personal data.

**What your logs contain:**
```
INFO Request: POST /login
INFO Body: {"email": "alice@example.com", "password": "MySecretPass123!"}
INFO Headers: {'Authorization': 'Bearer eyJhbGciOiJIUzI1NiJ9...'}
INFO Response body: {"user": {"ssn": "123-45-6789", "credit_card": "4111..."}}
```

**Passwords, tokens, PII, and financial data in plain text logs.** Anyone with log access (developers, ops, log aggregation service) sees everything.

**Fixed logging:**
```python
import time
import uuid

SENSITIVE_HEADERS = {'authorization', 'cookie', 'x-api-key'}
SENSITIVE_PATHS = {'/login', '/register', '/password-reset'}

@app.before_request
def log_request():
    g.request_id = str(uuid.uuid4())[:8]
    g.start_time = time.time()

    # Log request metadata, NOT body
    logger.info(f"[{g.request_id}] {request.method} {request.path}",
        extra={
            'request_id': g.request_id,
            'remote_addr': request.remote_addr,
            'user_agent': request.user_agent.string[:100],
        })

@app.after_request
def log_response(response):
    duration = time.time() - g.start_time
    logger.info(
        f"[{g.request_id}] {response.status_code} {duration:.3f}s",
        extra={'request_id': g.request_id, 'duration': duration}
    )
    return response
```

**What to log vs what NOT to log:**

| Log this | Never log this |
|----------|---------------|
| HTTP method + path | Request/response bodies |
| Status code | Authorization headers |
| Response time | Passwords |
| Request ID | Tokens/API keys |
| Client IP | Personal data (SSN, email) |
| Error messages | Credit card numbers |

**For debugging specific issues**, add targeted logging in the relevant endpoint — don't log everything globally.'''
    ),
    (
        "thinking/meta-socratic-premature-optimization-cache-all",
        r'''I'm adding caching to every database query in my Django app:

```python
from django.core.cache import cache

def get_user(user_id):
    key = f'user:{user_id}'
    user = cache.get(key)
    if user is None:
        user = User.objects.get(id=user_id)
        cache.set(key, user, timeout=3600)
    return user

def get_user_orders(user_id):
    key = f'orders:{user_id}'
    orders = cache.get(key)
    if orders is None:
        orders = list(Order.objects.filter(user_id=user_id))
        cache.set(key, orders, timeout=3600)
    return orders

# ... same pattern for every query in the app
```

Maximum performance, right?''',
        r'''<think>
Q: Is this premature optimization?

Q: Is every database query actually slow?
A: A simple `User.objects.get(id=user_id)` with a primary key lookup takes <1ms on PostgreSQL. Caching it saves <1ms and adds the complexity of cache management.

Q: What problems does caching EVERY query create?
A:
  1. Cache invalidation everywhere: when a user updates their profile, must invalidate user:{id}. When an order is created, must invalidate orders:{user_id}. For every write, you need to know ALL cache keys affected.
  2. Stale data: user changes their name → name stays old for up to 1 hour
  3. Memory pressure: every user object, every order list in Redis
  4. Debugging difficulty: "is the bug in the data or the cache?"

Q: What percentage of queries actually benefit from caching?
A: In most apps, 90% of queries are fast enough without caching. The 10% that benefit are:
  - Expensive aggregations (counts, sums across large tables)
  - Queries with complex JOINs across multiple tables
  - Queries called hundreds of times per second (hot paths)

Q: Am I measuring before optimizing?
A: No. Caching every query is cargo cult optimization — "caching is fast, so cache everything."

Q: What's the right approach?
A: 1. Build without caching
   2. Measure with django-debug-toolbar or EXPLAIN ANALYZE
   3. Identify the 2-3 queries that are actually slow
   4. Cache THOSE specific queries
   5. Handle invalidation for only those caches
</think>

**This is premature optimization that creates more problems than it solves.** Caching every query makes your app harder to debug, introduces stale data bugs, and solves problems that don't exist.

**The cache invalidation nightmare you're creating:**
```python
# User updates their profile:
def update_user(user_id, data):
    user = User.objects.get(id=user_id)
    user.name = data['name']
    user.save()

    # Now you must invalidate:
    cache.delete(f'user:{user_id}')
    cache.delete(f'orders:{user_id}')  # Orders include user data?
    cache.delete(f'dashboard:{user_id}')
    cache.delete(f'leaderboard')  # User name appears here too?
    # ... how many more keys? You don't know. You'll miss some.
```

**What you should do instead:**

```python
# Step 1: No caching. Measure with django-debug-toolbar.
# Most queries are <5ms. That's fast enough.

# Step 2: Find the ACTUALLY slow queries
# Example: "Top 10 products with average rating"
# This aggregation across millions of reviews IS worth caching

# Step 3: Cache ONLY that query
def get_top_products():
    key = 'top_products'
    result = cache.get(key)
    if result is None:
        result = list(Product.objects.annotate(
            avg_rating=Avg('reviews__rating')
        ).order_by('-avg_rating')[:10])
        cache.set(key, result, timeout=300)
    return result
```

**Database queries that DON'T need caching:**
- Primary key lookups (`User.objects.get(id=1)`) — <1ms
- Foreign key lookups with indexes — <1ms
- Simple filtered queries on indexed columns — <5ms

**Database queries that DO need caching:**
- Complex aggregations across large tables
- Queries with multiple JOINs
- Queries called 100+ times/second on the same data
- Expensive full-text searches

**Rule**: If you can't name the specific query that's slow, you don't need caching yet.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
