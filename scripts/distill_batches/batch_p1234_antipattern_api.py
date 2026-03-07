"""
Anti-pattern training pairs - API design anti-patterns
Topics: verbs in URLs, no pagination, no versioning, leaking internals, no rate limiting
"""

pairs = [
    {
        "instruction": r'''I designed my REST API routes. Do these look correct?

```
POST /api/createUser
GET  /api/getUser/123
POST /api/updateUser/123
POST /api/deleteUser/123
GET  /api/getAllUsers
POST /api/sendEmail
GET  /api/searchProducts?name=widget
POST /api/addToCart/456
```''',
        "output": r'''<think>
Verbs in URLs anti-pattern. REST uses HTTP methods (GET, POST, PUT, DELETE) as the verbs, so URLs should be nouns representing resources. "createUser" puts the verb in the URL and the method becomes redundant. Also using POST for everything instead of the appropriate HTTP method. Need to show the RESTful way with proper resource naming and HTTP methods.
</think>

These URLs have verbs baked in (`create`, `get`, `update`, `delete`, `send`, `search`, `add`). In REST, the HTTP method IS the verb, so the URL should be a noun representing the resource.

**Why this matters:**
- HTTP caches understand GET but not "POST /getUser" -- you lose free caching
- Clients must memorize arbitrary verb names instead of a consistent pattern
- Your API becomes unpredictable -- is it `deleteUser` or `removeUser`? `getAll` or `listAll`?

**The fix -- resources as nouns, HTTP methods as verbs:**

```
POST   /api/users          --> create a user
GET    /api/users/123      --> get a user
PUT    /api/users/123      --> update a user (full replace)
PATCH  /api/users/123      --> update a user (partial)
DELETE /api/users/123      --> delete a user
GET    /api/users          --> list all users

POST   /api/emails         --> send an email
GET    /api/products?name=widget  --> search products
POST   /api/carts/456/items       --> add item to cart
```

**The pattern is consistent:**
- `GET /resources` -- list
- `POST /resources` -- create
- `GET /resources/:id` -- read one
- `PUT /resources/:id` -- replace
- `PATCH /resources/:id` -- partial update
- `DELETE /resources/:id` -- delete

**For actions that don't fit CRUD**, model them as sub-resources or state changes:

```
POST /api/orders/789/cancel     --> cancel an order
POST /api/users/123/verify      --> verify a user
```

Once you follow this pattern, a developer can guess your entire API from knowing the resource names.'''
    },
    {
        "instruction": r'''My endpoint returns all users. It works fine in development with 50 test users:

```python
@app.route('/api/users')
def list_users():
    users = User.query.all()
    return jsonify([u.to_dict() for u in users])
```''',
        "output": r'''<think>
No pagination anti-pattern. Returning all records works with 50 rows but will crash or time out with 100,000 rows. It loads everything into memory, serializes it all to JSON, and sends a massive response. The user tested with small data and assumed it would scale. Need to show cursor-based or offset pagination.
</think>

This works with 50 users but will fail in production. When you have 100,000 users:

- The database loads all 100,000 rows into memory
- Python serializes them all to JSON (potentially hundreds of MB)
- The HTTP response takes minutes to transfer
- The client must parse the entire payload before showing anything
- Your server runs out of memory under concurrent requests

**The fix -- add pagination:**

```python
@app.route('/api/users')
def list_users():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)

    # Cap per_page to prevent abuse
    per_page = min(per_page, 100)

    query = User.query.order_by(User.id)
    pagination = query.paginate(page=page, per_page=per_page)

    return jsonify({
        'data': [u.to_dict() for u in pagination.items],
        'pagination': {
            'page': page,
            'per_page': per_page,
            'total': pagination.total,
            'pages': pagination.pages,
            'has_next': pagination.has_next,
        }
    })
```

**Usage:** `GET /api/users?page=2&per_page=20`

**For large datasets, use cursor-based pagination** (better performance than OFFSET):

```python
@app.route('/api/users')
def list_users():
    after = request.args.get('after', type=int)  # last seen ID
    limit = min(request.args.get('limit', 20, type=int), 100)

    query = User.query.order_by(User.id)
    if after:
        query = query.filter(User.id > after)

    users = query.limit(limit + 1).all()
    has_more = len(users) > limit
    users = users[:limit]

    return jsonify({
        'data': [u.to_dict() for u in users],
        'has_more': has_more,
        'next_cursor': users[-1].id if has_more else None,
    })
```

Cursor pagination does not slow down on deep pages like OFFSET does, because it uses an indexed column to seek directly.'''
    },
    {
        "instruction": r'''We just shipped v1 of our API and clients are using it. Now I need to change the user response format. I'll just update the endpoint:

```python
# Before: { "name": "Alice Smith" }
# After:  { "first_name": "Alice", "last_name": "Smith" }

@app.route('/api/users/<int:user_id>')
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify({
        'first_name': user.first_name,
        'last_name': user.last_name,
        # removed 'name' field
    })
```''',
        "output": r'''<think>
No API versioning. The user is making a breaking change to a live API -- removing the "name" field and replacing it with "first_name"/"last_name". Every existing client that reads "name" will break immediately. This is a breaking change deployed without versioning. Need to show how to version APIs and handle backward compatibility.
</think>

This is a breaking change. Every existing client that reads the `name` field will break the moment you deploy. Mobile apps in particular cannot be force-updated -- users on old app versions will see crashes.

**What makes a change "breaking":**
- Removing a field (you removed `name`)
- Renaming a field (`name` -> `first_name`)
- Changing a field's type (string -> object)
- Changing required fields

**The fix -- version your API:**

```python
# v1 -- keep working for existing clients
@app.route('/api/v1/users/<int:user_id>')
def get_user_v1(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify({
        'name': f"{user.first_name} {user.last_name}",
    })

# v2 -- new format for new clients
@app.route('/api/v2/users/<int:user_id>')
def get_user_v2(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify({
        'first_name': user.first_name,
        'last_name': user.last_name,
    })
```

**Even better -- make additive changes that don't need a new version:**

```python
@app.route('/api/v1/users/<int:user_id>')
def get_user(user_id):
    user = User.query.get_or_404(user_id)
    return jsonify({
        'name': f"{user.first_name} {user.last_name}",  # keep old field
        'first_name': user.first_name,  # add new fields
        'last_name': user.last_name,
    })
```

Adding fields is backward-compatible -- old clients ignore the new fields, new clients use them. Only remove the old field when you have confirmed zero clients depend on it.

**Versioning strategies:** URL path (`/v1/`), header (`Accept: application/vnd.api.v2+json`), or query parameter (`?version=2`). URL path is the simplest and most widely used.'''
    },
    {
        "instruction": r'''Here's my API response for getting a user. I return everything the frontend might need:

```json
{
    "id": 42,
    "username": "alice",
    "email": "alice@example.com",
    "password_hash": "$2b$12$LJ3m4ys...",
    "internal_flags": 0x0F,
    "db_created_at": "2024-01-15T10:30:00",
    "stripe_customer_id": "cus_abc123",
    "last_login_ip": "192.168.1.50",
    "admin_notes": "VIP customer, give priority support",
    "role_bitmask": 7,
    "preferences": {"theme": "dark"}
}
```''',
        "output": r'''<think>
Leaking internal implementation details through the API. The response includes password_hash (security breach), internal_flags (meaningless to clients), stripe_customer_id (sensitive), last_login_ip (privacy issue), admin_notes (confidential), and raw bitmask (implementation detail). The user thinks "return everything" is helpful but it creates security and privacy problems. Need to show how to create a proper API response schema.
</think>

This response leaks sensitive internal data that creates security, privacy, and maintainability problems.

**Security issues:**
- `password_hash` -- even hashed, exposing this lets attackers run offline brute-force attacks
- `stripe_customer_id` -- a third-party identifier that could be used for social engineering with Stripe support
- `admin_notes` -- confidential internal communication visible to the user

**Privacy issues:**
- `last_login_ip` -- personally identifiable information that may violate GDPR/privacy laws
- `email` might need to be masked depending on who is requesting

**Maintainability issues:**
- `internal_flags` and `role_bitmask` -- meaningless to clients, but once exposed, clients start depending on them and you can never change the format
- `db_created_at` -- the "db_" prefix exposes your storage layer naming

**The fix -- define explicit response schemas:**

```python
def user_to_public_response(user):
    """What any authenticated user can see."""
    return {
        'id': user.id,
        'username': user.username,
        'created_at': user.created_at.isoformat(),
        'preferences': user.preferences,
    }

def user_to_private_response(user):
    """What the user can see about themselves."""
    return {
        **user_to_public_response(user),
        'email': user.email,
        'role': role_bitmask_to_string(user.role_bitmask),
    }

def user_to_admin_response(user):
    """What admins can see."""
    return {
        **user_to_private_response(user),
        'last_login_ip': user.last_login_ip,
        'admin_notes': user.admin_notes,
    }
```

**Rule:** Never serialize your database model directly to JSON. Always have an explicit serialization layer that controls exactly which fields are exposed to which audience. What goes out through your API is a contract -- once clients depend on a field, you cannot remove it.'''
    },
    {
        "instruction": r'''My public API is live. Here's the endpoint that generates PDF reports:

```python
@app.route('/api/reports/generate', methods=['POST'])
def generate_report():
    data = request.json
    report = build_report(data['start_date'], data['end_date'])
    pdf = render_pdf(report)  # takes 5-10 seconds, CPU intensive
    return send_file(pdf, mimetype='application/pdf')
```

A few users are complaining that the API is unresponsive sometimes.''',
        "output": r'''<think>
No rate limiting on a CPU-intensive endpoint. Any user (or bot) can hammer this endpoint, and each request ties up a worker for 5-10 seconds generating a PDF. A few concurrent requests can exhaust all workers, making the API unresponsive for everyone. This is trivially exploitable as a denial-of-service attack. Need rate limiting and possibly async processing.
</think>

Without rate limiting, any single user (or attacker) can send 100 concurrent requests to this endpoint. Each one consumes a server worker for 5-10 seconds. With a typical deployment of 4-8 workers, just a handful of concurrent report requests locks out your entire API.

This is also a trivial denial-of-service vector -- no authentication or special tools needed.

**The fix -- add rate limiting and async processing:**

**Step 1: Rate limiting**

```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per minute"]
)

@app.route('/api/reports/generate', methods=['POST'])
@limiter.limit("5 per minute")  # stricter for expensive operations
def generate_report():
    data = request.json
    report = build_report(data['start_date'], data['end_date'])
    pdf = render_pdf(report)
    return send_file(pdf, mimetype='application/pdf')
```

When the limit is exceeded, the client gets a `429 Too Many Requests` response with a `Retry-After` header.

**Step 2: For CPU-heavy work, use async processing:**

```python
from celery import Celery

@app.route('/api/reports/generate', methods=['POST'])
@limiter.limit("5 per minute")
def generate_report():
    data = request.json
    task = generate_report_task.delay(
        data['start_date'], data['end_date']
    )
    return jsonify({
        'task_id': task.id,
        'status_url': f'/api/reports/status/{task.id}'
    }), 202  # 202 Accepted

@app.route('/api/reports/status/<task_id>')
def report_status(task_id):
    task = generate_report_task.AsyncResult(task_id)
    if task.ready():
        return jsonify({'status': 'done', 'download_url': task.result})
    return jsonify({'status': 'processing'})
```

This pattern returns immediately (202 Accepted), does the heavy work in a background queue, and lets the client poll for completion. Your API workers stay free to handle other requests.'''
    },
]
