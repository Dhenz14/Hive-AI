"""Phase 4A: Self-Improvement -- Training Data Generation (Part 10)

Generate and evaluate training pairs for API design topics.
Each answer creates 3 graded training pairs with quality analysis.
"""

PAIRS = [
    (
        "thinking/auto-datagen-rest-api-design",
        r'''Generate 3 high-quality training pairs that teach RESTful API design principles. For each pair, explain why it's effective training data.''',
        r'''<think>
For API design training data, I need to cover:
1. Common mistakes: inconsistent naming, wrong HTTP methods, poor error responses
2. Real scenarios: designing CRUD endpoints, pagination, versioning
3. Difficulty progression: basic REST conventions -> advanced patterns -> API evolution

API design is about communication and consistency -- developers interact with your API like a language.
</think>

Here are 3 training pairs for RESTful API design:

**Pair 1 (Beginner):**
```
Q: I'm designing my first REST API. I have these endpoints:
  GET /getUsers
  POST /createUser
  GET /getUserById?id=123
  POST /deleteUser
  POST /updateUser

Is this good design?

A: This is a common beginner pattern, but it violates REST conventions. The problem is putting verbs in URLs -- HTTP methods already provide the verb.

**Your design vs REST conventions:**

| Your endpoint | RESTful version | Why |
|--------------|----------------|-----|
| GET /getUsers | GET /users | HTTP GET is already "get" |
| POST /createUser | POST /users | POST to a collection = create |
| GET /getUserById?id=123 | GET /users/123 | Resource ID goes in the path |
| POST /deleteUser | DELETE /users/123 | Use HTTP DELETE method |
| POST /updateUser | PUT /users/123 | PUT = full update, PATCH = partial |

**The RESTful API:**
```
GET    /users          -> List all users
POST   /users          -> Create a new user
GET    /users/123      -> Get user 123
PUT    /users/123      -> Replace user 123
PATCH  /users/123      -> Partially update user 123
DELETE /users/123      -> Delete user 123
```

**Key principles:**
1. URLs are NOUNS (resources), not VERBS (actions)
2. HTTP methods provide the verb (GET, POST, PUT, DELETE)
3. Use plural nouns: `/users` not `/user`
4. Nest related resources: `/users/123/orders`
```
*Why this is effective:* Addresses the most common beginner mistake (verb-in-URL) with a clear before/after comparison, making the principle immediately actionable.

**Pair 2 (Intermediate):**
```
Q: How should I design error responses for my API? Right now I just return {"error": "something went wrong"} with status 500 for everything.

A: Good error responses are crucial -- they're how developers debug integrations with your API.

**Bad (what you have now):**
```json
HTTP 500
{"error": "something went wrong"}
```
Problems: No status code variety, no error codes, no details, no help.

**Good error response structure:**
```json
HTTP 422
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [
      {
        "field": "email",
        "message": "Must be a valid email address",
        "value": "not-an-email"
      },
      {
        "field": "age",
        "message": "Must be between 0 and 150",
        "value": -5
      }
    ]
  },
  "request_id": "req_abc123"
}
```

**Status codes to use:**
| Code | When to use | Example |
|------|------------|---------|
| 400 | Malformed request | Invalid JSON body |
| 401 | Not authenticated | Missing or invalid token |
| 403 | Not authorized | Valid token but no permission |
| 404 | Resource not found | GET /users/999 (doesn't exist) |
| 409 | Conflict | Creating duplicate username |
| 422 | Validation failed | Invalid email format |
| 429 | Rate limited | Too many requests |
| 500 | Server error | Unexpected crash (your bug) |

**Implementation:**
```python
@app.errorhandler(422)
def validation_error(e):
    return jsonify({
        "error": {
            "code": "VALIDATION_ERROR",
            "message": str(e),
            "details": e.details if hasattr(e, 'details') else []
        },
        "request_id": request.id
    }), 422
```

**Rules:**
- Never return 500 for client mistakes (use 4xx)
- Always include a machine-readable error code
- Include request_id so users can reference it in support tickets
- Never expose stack traces or internal details in production
```
*Why this is effective:* Error handling is where most APIs fail. Teaching structured errors with specific status codes gives developers a complete reference they can implement immediately.

**Pair 3 (Advanced):**
```
Q: My API has been running in production for 2 years. I need to make breaking changes (rename fields, change response structure). How do I evolve the API without breaking existing clients?

A: API evolution is one of the hardest design challenges. You need a versioning strategy and a migration plan.

**Option 1: URL versioning (simplest, most common):**
```
GET /v1/users/123  -> Old response format
GET /v2/users/123  -> New response format
```
Run both versions simultaneously. Deprecate v1 after migration period.

**Option 2: Header versioning (cleaner URLs):**
```
GET /users/123
Accept: application/vnd.myapi.v2+json
```

**Option 3: Additive changes only (best if possible):**
```json
// v1 response:
{"name": "Alice", "email": "alice@example.com"}

// v2 response (additive -- no breaking change):
{"name": "Alice", "email": "alice@example.com", "full_name": "Alice Smith", "verified": true}

// v3 -- deprecate but don't remove:
{"name": "Alice", "email": "alice@example.com", "full_name": "Alice Smith", "verified": true}
// Mark 'name' as deprecated in docs, but keep it working
```

**Migration strategy:**
```
Phase 1: Deploy new version alongside old
  - /v2/users works with new format
  - /v1/users still works exactly as before

Phase 2: Notify consumers (3-6 months)
  - Add deprecation headers: Sunset: Sat, 01 Jun 2025 00:00:00 GMT
  - Log which clients still use v1
  - Provide migration guide

Phase 3: Remove old version
  - Return 410 Gone for /v1 with message pointing to /v2
  - Only after confirming zero v1 traffic
```

**Breaking vs non-breaking changes:**
| Change | Breaking? | Safe approach |
|--------|-----------|--------------|
| Add new field | No | Just add it |
| Remove field | YES | Deprecate, then remove in new version |
| Rename field | YES | Add new name, keep old, deprecate old |
| Change field type | YES | New version required |
| Add optional parameter | No | Just add it |
| Make optional param required | YES | New version required |
| Add new endpoint | No | Just add it |
| Remove endpoint | YES | Deprecate, then 410 Gone |
```
*Why this is effective:* API versioning is rarely taught but critically important for production systems. The phase-based migration plan gives a concrete timeline developers can follow.'''
    ),
    (
        "thinking/auto-datagen-api-authentication",
        r'''Generate 3 high-quality training pairs that teach API authentication and authorization patterns. For each pair, explain why it's effective training data.''',
        r'''<think>
Authentication/authorization is critical but often confused:
1. Authentication = who are you (identity)
2. Authorization = what can you do (permissions)
3. Common patterns: API keys, JWT, OAuth2

Progression: API keys for simple cases -> JWT for stateless auth -> OAuth2 for third-party access
</think>

Here are 3 training pairs for API authentication:

**Pair 1 (Beginner):**
```
Q: What's the difference between API keys, JWT tokens, and OAuth? When should I use each?

A: These solve different problems at different scales:

**API Keys -- simplest, for server-to-server:**
```
curl -H "X-API-Key: sk_test_abc123" https://api.example.com/data
```
- What it is: A secret string that identifies the caller
- Good for: Server-to-server calls, simple integrations, rate limiting
- Bad for: User authentication (API keys don't represent users)
- Example: Stripe API, SendGrid, weather APIs

**JWT (JSON Web Tokens) -- for user authentication:**
```
curl -H "Authorization: Bearer eyJhbGciOiJI..." https://api.example.com/me
```
- What it is: A signed token containing user info (user_id, role, expiry)
- Good for: User login sessions, stateless authentication, microservices
- Bad for: Third-party access (you can't give a JWT to another app safely)
- Example: Your own app's login system

**OAuth 2.0 -- for third-party access:**
```
"Sign in with Google" -> User grants permission -> Your app gets a token
```
- What it is: A protocol for users to grant limited access to their data
- Good for: "Sign in with X", letting third-party apps access your API
- Bad for: Simple server-to-server calls (too complex)
- Example: Google login, GitHub OAuth, "Connect your Slack"

**Decision matrix:**
| Scenario | Use |
|----------|-----|
| My server calls a third-party API | API Key |
| Users log into my app | JWT |
| Users log in via Google/GitHub | OAuth 2.0 |
| Third-party apps access my users' data | OAuth 2.0 |
| Microservice-to-microservice | JWT or mTLS |
```
*Why this is effective:* Clarifies three commonly confused concepts with concrete use cases, preventing beginners from using the wrong pattern for their needs.

**Pair 2 (Intermediate):**
```
Q: How do I implement JWT authentication properly? I've seen warnings about JWTs being insecure.

A: JWTs aren't insecure -- but they're commonly implemented insecurely. Here are the critical rules:

**Correct JWT implementation:**
```python
import jwt
from datetime import datetime, timedelta

SECRET_KEY = os.environ['JWT_SECRET']  # Never hardcode!
ALGORITHM = "HS256"

def create_token(user_id: int, role: str) -> str:
    payload = {
        "sub": user_id,
        "role": role,
        "iat": datetime.utcnow(),
        "exp": datetime.utcnow() + timedelta(minutes=15),  # Short-lived!
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthError("Token expired")
    except jwt.InvalidTokenError:
        raise AuthError("Invalid token")
```

**Critical security rules:**

1. **Short expiration (15-60 minutes):**
```python
"exp": datetime.utcnow() + timedelta(minutes=15)
# NOT hours=24 or days=30
```
If a JWT is stolen, the damage is limited to 15 minutes.

2. **Use refresh tokens for long sessions:**
```python
# Access token: 15 min, stored in memory
# Refresh token: 7 days, stored in httpOnly cookie
def refresh(refresh_token):
    user = verify_refresh_token(refresh_token)
    return create_token(user.id, user.role)  # New 15-min access token
```

3. **Never store JWTs in localStorage:**
```javascript
// BAD -- XSS can steal it:
localStorage.setItem('token', jwt);

// GOOD -- httpOnly cookie (JavaScript can't access):
// Set from server:
res.cookie('token', jwt, { httpOnly: true, secure: true, sameSite: 'strict' });
```

4. **Always specify the algorithm:**
```python
# BAD -- allows algorithm switching attack:
jwt.decode(token, SECRET_KEY)

# GOOD -- explicitly require your algorithm:
jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
```

5. **Include only necessary claims:**
```python
# BAD -- sensitive data in JWT:
{"sub": 1, "email": "alice@x.com", "ssn": "123-45-6789"}

# GOOD -- minimal claims:
{"sub": 1, "role": "admin", "exp": 1700000000}
```
```
*Why this is effective:* Addresses the specific security pitfalls that make JWTs dangerous when misimplemented, with concrete code showing the right and wrong way for each rule.

**Pair 3 (Advanced):**
```
Q: How do I implement role-based access control (RBAC) in my API so different users can access different endpoints?

A: RBAC has three components: roles, permissions, and enforcement. Here's a production-ready approach:

**1. Define roles and permissions:**
```python
PERMISSIONS = {
    "admin": ["users:read", "users:write", "users:delete", "orders:read", "orders:write", "reports:read"],
    "manager": ["users:read", "orders:read", "orders:write", "reports:read"],
    "user": ["orders:read", "orders:write"],  # Only their own
    "viewer": ["orders:read"],  # Only their own
}
```

**2. Encode role in JWT:**
```python
def create_token(user):
    return jwt.encode({
        "sub": user.id,
        "role": user.role,  # "admin", "manager", "user", "viewer"
        "exp": datetime.utcnow() + timedelta(minutes=15)
    }, SECRET_KEY, algorithm="HS256")
```

**3. Create a permission decorator:**
```python
from functools import wraps
from flask import request, jsonify

def require_permission(permission):
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            token = request.headers.get('Authorization', '').replace('Bearer ', '')
            try:
                payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
            except jwt.InvalidTokenError:
                return jsonify({"error": "Invalid token"}), 401

            role = payload.get('role')
            if permission not in PERMISSIONS.get(role, []):
                return jsonify({
                    "error": "Forbidden",
                    "required_permission": permission,
                    "your_role": role
                }), 403

            request.current_user = payload
            return f(*args, **kwargs)
        return wrapper
    return decorator
```

**4. Apply to routes:**
```python
@app.route('/users', methods=['GET'])
@require_permission('users:read')
def list_users():
    return jsonify(get_all_users())

@app.route('/users/<int:user_id>', methods=['DELETE'])
@require_permission('users:delete')
def delete_user(user_id):
    # Only admins reach here
    remove_user(user_id)
    return '', 204

@app.route('/orders', methods=['GET'])
@require_permission('orders:read')
def list_orders():
    user = request.current_user
    if user['role'] in ('user', 'viewer'):
        # Non-admin users only see their own orders
        return jsonify(get_orders(user_id=user['sub']))
    return jsonify(get_all_orders())
```

**5. Resource-level authorization (beyond RBAC):**
```python
@app.route('/orders/<int:order_id>', methods=['PUT'])
@require_permission('orders:write')
def update_order(order_id):
    order = get_order(order_id)
    user = request.current_user

    # RBAC says they CAN edit orders, but is this THEIR order?
    if user['role'] == 'user' and order.user_id != user['sub']:
        return jsonify({"error": "You can only edit your own orders"}), 403

    update_order_data(order_id, request.json)
    return jsonify(order)
```

**Key insight:** RBAC (role-based) controls WHICH actions. Resource-level auth controls WHICH resources. You usually need both.
```
*Why this is effective:* Provides a complete, copy-paste-ready RBAC implementation that covers both role-level and resource-level authorization, which is what production APIs actually need.'''
    ),
    (
        "thinking/auto-datagen-api-pagination",
        r'''Generate 3 high-quality training pairs that teach API pagination and filtering patterns. For each pair, explain why it's effective training data.''',
        r'''<think>
Pagination seems simple but has important tradeoffs:
1. Offset vs cursor pagination
2. Filtering and sorting conventions
3. Handling real-time data with pagination

Progression: basic offset pagination -> cursor pagination -> filtering/sorting best practices
</think>

Here are 3 training pairs for API pagination:

**Pair 1 (Beginner):**
```
Q: My API endpoint GET /users returns all 50,000 users at once. It's slow and crashes on mobile. How do I add pagination?

A: Return a page at a time with metadata about total results. Here's offset-based pagination:

**Request:**
```
GET /users?page=1&per_page=20
GET /users?page=2&per_page=20
```

**Response:**
```json
{
  "data": [
    {"id": 1, "name": "Alice"},
    {"id": 2, "name": "Bob"}
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 50000,
    "total_pages": 2500,
    "has_next": true,
    "has_prev": false
  }
}
```

**Implementation:**
```python
@app.route('/users')
def list_users():
    page = request.args.get('page', 1, type=int)
    per_page = min(request.args.get('per_page', 20, type=int), 100)  # Cap at 100

    offset = (page - 1) * per_page
    users = db.query(User).offset(offset).limit(per_page).all()
    total = db.query(User).count()

    return jsonify({
        "data": [u.to_dict() for u in users],
        "pagination": {
            "page": page,
            "per_page": per_page,
            "total": total,
            "total_pages": (total + per_page - 1) // per_page,
            "has_next": page * per_page < total,
            "has_prev": page > 1
        }
    })
```

**Important rules:**
1. Always set a maximum per_page (e.g., 100) to prevent abuse
2. Default to a reasonable per_page (20-50)
3. Include total count and navigation metadata
4. Return empty array (not error) for pages beyond the last
```
*Why this is effective:* Teaches pagination from scratch with a complete implementation and defensive coding practices (max per_page), which beginners often miss.

**Pair 2 (Intermediate):**
```
Q: I'm using offset pagination but users complain about seeing duplicate items when scrolling through a feed. What's going wrong?

A: Offset pagination breaks when data changes between page requests. This is the "shifting window" problem:

**The problem:**
```
Time 0: User fetches page 1 (items 1-20)
Time 1: New item is inserted at position 1
Time 2: User fetches page 2 (items 21-40)
         But item 20 shifted to position 21 -- they see it TWICE!
```

**The solution: Cursor-based pagination**

Instead of "give me page N," you say "give me items AFTER this cursor":

**Request:**
```
GET /feed                        -> First page
GET /feed?after=cursor_abc123    -> Next page (after last item)
```

**Response:**
```json
{
  "data": [
    {"id": 42, "text": "Hello", "created_at": "2024-01-15T10:00:00Z"},
    {"id": 41, "text": "World", "created_at": "2024-01-15T09:55:00Z"}
  ],
  "cursors": {
    "after": "eyJpZCI6NDEsInQiOiIyMDI0LTAxLTE1VDA5OjU1OjAwWiJ9",
    "has_more": true
  }
}
```

**Implementation:**
```python
import base64, json

def encode_cursor(item):
    data = {"id": item.id, "t": item.created_at.isoformat()}
    return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()

def decode_cursor(cursor):
    data = json.loads(base64.urlsafe_b64decode(cursor))
    return data

@app.route('/feed')
def get_feed():
    limit = min(request.args.get('limit', 20, type=int), 100)
    after = request.args.get('after')

    query = db.query(Post).order_by(Post.created_at.desc())

    if after:
        cursor_data = decode_cursor(after)
        query = query.filter(
            (Post.created_at < cursor_data['t']) |
            ((Post.created_at == cursor_data['t']) & (Post.id < cursor_data['id']))
        )

    posts = query.limit(limit + 1).all()  # Fetch one extra to check has_more
    has_more = len(posts) > limit
    posts = posts[:limit]

    return jsonify({
        "data": [p.to_dict() for p in posts],
        "cursors": {
            "after": encode_cursor(posts[-1]) if posts else None,
            "has_more": has_more
        }
    })
```

**Offset vs Cursor comparison:**
| Feature | Offset | Cursor |
|---------|--------|--------|
| Jump to page N | Yes | No |
| Stable with inserts/deletes | No | Yes |
| Performance on large offsets | Slow (OFFSET 50000) | Fast (indexed WHERE) |
| Use for | Admin tables | Feeds, timelines, infinite scroll |
```
*Why this is effective:* Explains WHY offset pagination fails with real-time data, which motivates cursor pagination. Most tutorials just say "use cursors" without explaining the underlying problem.

**Pair 3 (Advanced):**
```
Q: How should I design filtering, sorting, and search for my API? I have an e-commerce product catalog with many attributes.

A: Filtering and sorting need consistent conventions across your entire API. Here's a production-tested approach:

**Filtering convention:**
```
GET /products?category=electronics&price_min=100&price_max=500&in_stock=true
GET /products?brand=apple,samsung    (multiple values = OR)
GET /products?created_after=2024-01-01
```

**Sorting convention:**
```
GET /products?sort=price             (ascending by default)
GET /products?sort=-price            (descending with - prefix)
GET /products?sort=-created_at,name  (multi-field sort)
```

**Search convention:**
```
GET /products?q=wireless+headphones  (full-text search)
GET /products?q=wireless+headphones&category=electronics  (search + filter)
```

**Complete implementation:**
```python
@app.route('/products')
def list_products():
    query = db.query(Product)

    # Filtering
    if category := request.args.get('category'):
        query = query.filter(Product.category == category)
    if brand := request.args.get('brand'):
        brands = brand.split(',')
        query = query.filter(Product.brand.in_(brands))
    if price_min := request.args.get('price_min', type=float):
        query = query.filter(Product.price >= price_min)
    if price_max := request.args.get('price_max', type=float):
        query = query.filter(Product.price <= price_max)
    if request.args.get('in_stock') == 'true':
        query = query.filter(Product.stock > 0)

    # Search
    if q := request.args.get('q'):
        query = query.filter(
            Product.name.ilike(f'%{q}%') | Product.description.ilike(f'%{q}%')
        )

    # Sorting
    sort = request.args.get('sort', '-created_at')
    for field in sort.split(','):
        if field.startswith('-'):
            column = getattr(Product, field[1:], None)
            if column:
                query = query.order_by(column.desc())
        else:
            column = getattr(Product, field, None)
            if column:
                query = query.order_by(column.asc())

    # Pagination (cursor-based for large catalogs)
    limit = min(request.args.get('limit', 20, type=int), 100)
    after = request.args.get('after')
    if after:
        cursor = decode_cursor(after)
        query = apply_cursor_filter(query, cursor, sort)

    products = query.limit(limit + 1).all()
    has_more = len(products) > limit
    products = products[:limit]

    return jsonify({
        "data": [p.to_dict() for p in products],
        "filters_applied": {
            "category": request.args.get('category'),
            "brand": request.args.get('brand'),
            "price_range": [price_min, price_max],
            "in_stock": request.args.get('in_stock'),
            "search": request.args.get('q')
        },
        "cursors": {
            "after": encode_cursor(products[-1]) if products else None,
            "has_more": has_more
        }
    })
```

**Security considerations:**
```python
# NEVER allow arbitrary column names in sort/filter:
ALLOWED_SORT_FIELDS = {'price', 'name', 'created_at', 'rating'}

sort_field = request.args.get('sort', 'created_at').lstrip('-')
if sort_field not in ALLOWED_SORT_FIELDS:
    return jsonify({"error": f"Cannot sort by '{sort_field}'"}), 400
```

**Performance tips:**
- Add database indexes on all filterable columns
- For full-text search at scale, use Elasticsearch instead of ILIKE
- Cache common filter combinations
- Use EXPLAIN ANALYZE to verify query performance
```
*Why this is effective:* Provides a complete, production-ready filtering/sorting implementation with security (whitelist fields) and performance considerations that most tutorials skip.'''
    ),
    (
        "thinking/auto-datagen-api-rate-limiting",
        r'''Generate 3 high-quality training pairs that teach API rate limiting design and implementation. For each pair, explain why it's effective training data.''',
        r'''<think>
Rate limiting is essential for API reliability:
1. Why rate limiting matters and common algorithms
2. Implementing rate limiting middleware
3. Advanced patterns: tiered limits, rate limit headers, graceful degradation

Progression: understanding rate limits as a consumer -> implementing basic rate limiting -> advanced patterns
</think>

Here are 3 training pairs for API rate limiting:

**Pair 1 (Beginner):**
```
Q: I keep getting "429 Too Many Requests" from the GitHub API. What does this mean and how do I handle it?

A: HTTP 429 means you've hit the API's rate limit -- you're making too many requests in a time window.

**Understanding rate limits:**
```bash
# Check your rate limit status:
curl -I https://api.github.com/users/octocat

# Response headers tell you:
# X-RateLimit-Limit: 60        <- Max requests per hour
# X-RateLimit-Remaining: 45    <- Requests left this window
# X-RateLimit-Reset: 1700000000 <- When the window resets (Unix timestamp)
```

**How to handle 429 in your code:**
```python
import time
import requests

def call_api_with_retry(url, max_retries=3):
    for attempt in range(max_retries):
        response = requests.get(url)

        if response.status_code == 200:
            return response.json()

        if response.status_code == 429:
            # Check Retry-After header first
            retry_after = response.headers.get('Retry-After')
            if retry_after:
                wait = int(retry_after)
            else:
                # Exponential backoff: 1s, 2s, 4s
                wait = 2 ** attempt

            print(f"Rate limited. Waiting {wait}s...")
            time.sleep(wait)
            continue

        response.raise_for_status()

    raise Exception("Max retries exceeded")
```

**Proactive approach -- check before you hit the limit:**
```python
def call_api_safe(url):
    response = requests.get(url)
    remaining = int(response.headers.get('X-RateLimit-Remaining', 1))
    reset_time = int(response.headers.get('X-RateLimit-Reset', 0))

    if remaining < 5:
        wait = max(reset_time - time.time(), 0)
        print(f"Only {remaining} requests left. Waiting {wait:.0f}s...")
        time.sleep(wait)

    return response.json()
```
```
*Why this is effective:* Teaches rate limiting from the consumer perspective first, which is how most developers first encounter it, with practical retry logic.

**Pair 2 (Intermediate):**
```
Q: How do I add rate limiting to my own API? I want to limit users to 100 requests per minute.

A: Here are two approaches -- in-memory for single servers, Redis for distributed:

**Simple in-memory rate limiter (single server):**
```python
from collections import defaultdict
import time
from functools import wraps
from flask import request, jsonify

class RateLimiter:
    def __init__(self, max_requests, window_seconds):
        self.max_requests = max_requests
        self.window = window_seconds
        self.requests = defaultdict(list)

    def is_allowed(self, key):
        now = time.time()
        # Remove old requests outside the window
        self.requests[key] = [
            t for t in self.requests[key]
            if t > now - self.window
        ]
        if len(self.requests[key]) >= self.max_requests:
            return False
        self.requests[key].append(now)
        return True

    def remaining(self, key):
        now = time.time()
        recent = [t for t in self.requests[key] if t > now - self.window]
        return max(0, self.max_requests - len(recent))

limiter = RateLimiter(max_requests=100, window_seconds=60)

def rate_limit(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        key = request.headers.get('X-API-Key', request.remote_addr)
        if not limiter.is_allowed(key):
            return jsonify({
                "error": "Rate limit exceeded",
                "retry_after": 60
            }), 429, {
                'Retry-After': '60',
                'X-RateLimit-Limit': '100',
                'X-RateLimit-Remaining': '0'
            }
        response = f(*args, **kwargs)
        # Add rate limit headers to successful responses too
        return response
    return wrapper

@app.route('/api/data')
@rate_limit
def get_data():
    return jsonify({"result": "data"})
```

**Redis-based rate limiter (distributed, production):**
```python
import redis

r = redis.Redis()

def is_rate_limited(key, max_requests=100, window=60):
    pipe = r.pipeline()
    now = time.time()
    window_key = f"ratelimit:{key}"

    pipe.zremrangebyscore(window_key, 0, now - window)  # Remove old
    pipe.zadd(window_key, {str(now): now})               # Add current
    pipe.zcard(window_key)                                # Count
    pipe.expire(window_key, window)                       # Auto-cleanup
    results = pipe.execute()

    request_count = results[2]
    return request_count > max_requests
```

**Always include rate limit headers:**
```
X-RateLimit-Limit: 100
X-RateLimit-Remaining: 73
X-RateLimit-Reset: 1700000060
Retry-After: 45  (only on 429 responses)
```
```
*Why this is effective:* Provides both a simple implementation for learning and a production-ready Redis version, showing the progression from prototype to production.

**Pair 3 (Advanced):**
```
Q: How do I implement tiered rate limits -- different limits for free vs paid users, and different limits for different endpoints?

A: Tiered rate limiting needs per-user configuration and per-endpoint rules:

**Define rate limit tiers:**
```python
RATE_LIMITS = {
    "free": {
        "default": (60, 60),       # 60 requests per 60 seconds
        "/api/search": (10, 60),   # Search is expensive: 10/min
        "/api/export": (2, 3600),  # Export: 2 per hour
    },
    "pro": {
        "default": (600, 60),      # 600/min
        "/api/search": (100, 60),  # 100/min
        "/api/export": (20, 3600), # 20/hour
    },
    "enterprise": {
        "default": (6000, 60),     # 6000/min
        "/api/search": (1000, 60), # 1000/min
        "/api/export": (200, 3600),# 200/hour
    }
}
```

**Implementation with Redis:**
```python
def get_rate_limit(user, endpoint):
    tier = user.plan  # "free", "pro", "enterprise"
    limits = RATE_LIMITS.get(tier, RATE_LIMITS["free"])
    max_requests, window = limits.get(endpoint, limits["default"])
    return max_requests, window

def check_rate_limit(user, endpoint):
    max_requests, window = get_rate_limit(user, endpoint)
    key = f"ratelimit:{user.id}:{endpoint}"

    pipe = redis_client.pipeline()
    now = time.time()
    pipe.zremrangebyscore(key, 0, now - window)
    pipe.zadd(key, {f"{now}:{uuid4()}": now})
    pipe.zcard(key)
    pipe.expire(key, window)
    _, _, count, _ = pipe.execute()

    remaining = max(0, max_requests - count)
    reset_at = int(now + window)

    return {
        "allowed": count <= max_requests,
        "limit": max_requests,
        "remaining": remaining,
        "reset": reset_at
    }

@app.before_request
def apply_rate_limit():
    user = get_current_user()
    result = check_rate_limit(user, request.path)

    # Always set headers
    g.rate_limit_headers = {
        'X-RateLimit-Limit': str(result['limit']),
        'X-RateLimit-Remaining': str(result['remaining']),
        'X-RateLimit-Reset': str(result['reset'])
    }

    if not result['allowed']:
        response = jsonify({
            "error": "Rate limit exceeded",
            "plan": user.plan,
            "upgrade_url": "https://example.com/pricing"
        })
        response.status_code = 429
        response.headers['Retry-After'] = str(result['reset'] - int(time.time()))
        for k, v in g.rate_limit_headers.items():
            response.headers[k] = v
        return response

@app.after_request
def add_rate_limit_headers(response):
    if hasattr(g, 'rate_limit_headers'):
        for k, v in g.rate_limit_headers.items():
            response.headers[k] = v
    return response
```

**Graceful degradation for rate-limited users:**
```python
# Instead of hard 429, offer degraded service:
def search_products(query, user):
    limit_result = check_rate_limit(user, '/api/search')

    if not limit_result['allowed']:
        if user.plan == 'free':
            # Return cached results instead of 429
            cached = get_cached_search(query)
            if cached:
                return jsonify({
                    "data": cached,
                    "note": "Showing cached results. Upgrade for real-time search.",
                    "upgrade_url": "/pricing"
                })
        return rate_limit_response(limit_result)

    return jsonify({"data": execute_search(query)})
```
```
*Why this is effective:* Goes beyond basic rate limiting to show the business logic integration (tiered plans, upgrade prompts, graceful degradation) that production APIs need.'''
    ),
    (
        "thinking/auto-datagen-api-documentation",
        r'''Generate 3 high-quality training pairs that teach API documentation best practices. For each pair, explain why it's effective training data.''',
        r'''<think>
API documentation is often overlooked but critical:
1. What makes good API docs vs bad API docs
2. Using OpenAPI/Swagger for auto-generated docs
3. Writing effective examples and error documentation

Progression: writing good endpoint docs -> OpenAPI specs -> documentation-driven development
</think>

Here are 3 training pairs for API documentation:

**Pair 1 (Beginner):**
```
Q: I need to document my API but I don't know where to start. What should I include?

A: Good API documentation answers 5 questions for every endpoint:

1. **What does it do?** (description)
2. **How do I call it?** (method, URL, parameters)
3. **What does it return?** (response format)
4. **What can go wrong?** (error responses)
5. **Show me a real example** (curl command + response)

**Example of BAD documentation:**
```
POST /api/users - Creates a user
```
That's it? What parameters? What response? What errors?

**Example of GOOD documentation:**
```markdown
## Create User

Creates a new user account.

**Endpoint:** `POST /api/users`

**Headers:**
| Header | Required | Value |
|--------|----------|-------|
| Authorization | Yes | Bearer {token} |
| Content-Type | Yes | application/json |

**Request body:**
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| email | string | Yes | Valid email address |
| name | string | Yes | 1-100 characters |
| role | string | No | "user" (default), "admin" |

**Success response (201 Created):**
```json
{
  "id": 42,
  "email": "alice@example.com",
  "name": "Alice Smith",
  "role": "user",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Error responses:**
| Status | Code | Description |
|--------|------|-------------|
| 400 | INVALID_JSON | Request body is not valid JSON |
| 409 | EMAIL_EXISTS | A user with this email already exists |
| 422 | VALIDATION_ERROR | Required field missing or invalid |

**Example:**
```bash
curl -X POST https://api.example.com/api/users \
  -H "Authorization: Bearer eyJhbG..." \
  -H "Content-Type: application/json" \
  -d '{"email": "alice@example.com", "name": "Alice Smith"}'
```
```

**The curl example is the most important part** -- developers will copy-paste it to test your API immediately.
```
*Why this is effective:* Shows the concrete difference between bad and good documentation with a template developers can copy for every endpoint they document.

**Pair 2 (Intermediate):**
```
Q: How do I use OpenAPI (Swagger) to auto-generate API documentation? I'm tired of docs getting out of sync with my code.

A: OpenAPI lets you define your API in a spec file, then auto-generate docs, client SDKs, and validation. Here's how to integrate it with your code:

**Approach 1: Code-first (generate spec from code):**
```python
# Flask with flask-smorest (recommended)
from flask_smorest import Blueprint, Api
from marshmallow import Schema, fields

class UserSchema(Schema):
    id = fields.Int(dump_only=True)
    email = fields.Email(required=True)
    name = fields.Str(required=True)
    role = fields.Str(load_default="user")
    created_at = fields.DateTime(dump_only=True)

class ErrorSchema(Schema):
    error = fields.Str()
    code = fields.Str()

blp = Blueprint("users", __name__, url_prefix="/api/users")

@blp.route("/")
class UserList(MethodView):
    @blp.arguments(UserSchema)
    @blp.response(201, UserSchema)
    @blp.alt_response(409, schema=ErrorSchema)
    def post(self, user_data):
        """Create a new user.

        Creates a user account with the provided email and name.
        Returns the created user with a server-generated ID.
        """
        user = create_user(user_data)
        return user
```
Visit `/swagger-ui` to see auto-generated interactive docs.

**Approach 2: Spec-first (write spec, generate code):**
```yaml
# openapi.yaml
openapi: 3.0.3
info:
  title: My API
  version: 1.0.0
paths:
  /api/users:
    post:
      summary: Create a new user
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/UserCreate'
            example:
              email: alice@example.com
              name: Alice Smith
      responses:
        '201':
          description: User created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/User'
        '409':
          description: Email already exists
components:
  schemas:
    UserCreate:
      type: object
      required: [email, name]
      properties:
        email:
          type: string
          format: email
        name:
          type: string
          minLength: 1
          maxLength: 100
    User:
      allOf:
        - $ref: '#/components/schemas/UserCreate'
        - type: object
          properties:
            id:
              type: integer
            created_at:
              type: string
              format: date-time
```

**Code-first vs spec-first:**
| Approach | Pros | Cons |
|----------|------|------|
| Code-first | Docs always match code | Less control over spec format |
| Spec-first | Design API before coding | Spec can drift from code |

**Recommendation:** Start code-first. It ensures docs never go stale.
```
*Why this is effective:* Shows both approaches with enough detail to implement either one, and gives a clear recommendation so developers don't get stuck choosing.

**Pair 3 (Advanced):**
```
Q: Our API has 200+ endpoints. Documentation is a mess -- some endpoints are undocumented, some docs are wrong, and developers complain they can't find what they need. How do we fix this?

A: Large API documentation needs structure, automation, and governance. Here's a systematic approach:

**1. Audit and organize by domain:**
```
/api/v1/
  /users/          -> User Management (12 endpoints)
  /orders/         -> Order Processing (18 endpoints)
  /products/       -> Product Catalog (15 endpoints)
  /payments/       -> Billing & Payments (8 endpoints)
  /admin/          -> Administration (10 endpoints)
```

**2. Enforce documentation in CI/CD:**
```yaml
# .github/workflows/api-docs.yml
- name: Validate OpenAPI spec
  run: npx @openapitools/openapi-generator-cli validate -i openapi.yaml

- name: Check for undocumented endpoints
  run: |
    python scripts/check_docs_coverage.py
    # Compares registered routes vs documented endpoints
    # Fails CI if any endpoint is missing documentation
```

```python
# scripts/check_docs_coverage.py
def check_coverage():
    registered = get_all_flask_routes()  # From app.url_map
    documented = get_documented_endpoints()  # From openapi.yaml

    undocumented = registered - documented
    if undocumented:
        print(f"UNDOCUMENTED ENDPOINTS:")
        for ep in undocumented:
            print(f"  - {ep}")
        sys.exit(1)
    print(f"All {len(registered)} endpoints documented.")
```

**3. Add runnable examples (not just static docs):**
```markdown
## Try it yourself

```bash
# 1. Get an API key:
curl -X POST https://api.example.com/api-keys \
  -u your@email.com:password

# 2. List your orders:
curl https://api.example.com/api/orders \
  -H "Authorization: Bearer YOUR_KEY"

# 3. Create an order:
curl -X POST https://api.example.com/api/orders \
  -H "Authorization: Bearer YOUR_KEY" \
  -H "Content-Type: application/json" \
  -d '{"product_id": 1, "quantity": 2}'
```
```

**4. Structure docs for different audiences:**
```
Getting Started (5 min)
  -> Quick start with curl examples
  -> Authentication setup
  -> First API call

Guides (by use case)
  -> "How to process a payment"
  -> "How to manage user accounts"
  -> "How to set up webhooks"

API Reference (auto-generated)
  -> Every endpoint with parameters, responses, errors
  -> Generated from OpenAPI spec

Changelog
  -> What changed in each version
  -> Migration guides for breaking changes
```

**5. Test your examples automatically:**
```python
# Run documentation examples as integration tests:
@pytest.mark.parametrize("example", load_doc_examples())
def test_documentation_example(example):
    response = requests.request(
        method=example.method,
        url=example.url,
        headers=example.headers,
        json=example.body
    )
    assert response.status_code == example.expected_status
```

This ensures your documentation examples never break.
```
*Why this is effective:* Addresses the organizational challenge of large API documentation with concrete automation strategies, which is the real problem teams face at scale.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
