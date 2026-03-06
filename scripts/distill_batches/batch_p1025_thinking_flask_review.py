r"""Thinking-trace pairs: Flask code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this Flask code and identify issues:

```python
from flask import Flask, request, jsonify, session, g
from functools import wraps
import sqlite3
import os
import json

app = Flask(__name__)
app.secret_key = 'my-secret-key-123'

DATABASE = 'app.db'

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DATABASE)
    return g.db

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()
    username = data['username']
    password = data['password']
    db = get_db()
    user = db.execute(
        f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
    ).fetchone()
    if user:
        session['user_id'] = user[0]
        session['role'] = user[3]
        return jsonify({'message': 'logged in'})
    return jsonify({'error': 'invalid credentials'}), 401

@app.route('/users/<user_id>')
def get_user(user_id):
    db = get_db()
    user = db.execute(
        f"SELECT * FROM users WHERE id={user_id}"
    ).fetchone()
    if user:
        return jsonify({
            'id': user[0],
            'username': user[1],
            'password': user[2],
            'role': user[3],
        })
    return jsonify({'error': 'not found'}), 404

@app.route('/admin/users')
@login_required
def admin_users():
    if session.get('role') != 'admin':
        return jsonify({'error': 'forbidden'}), 403
    db = get_db()
    users = db.execute("SELECT * FROM users").fetchall()
    return jsonify({'users': [dict(zip(['id','username','password','role'], u)) for u in users]})

@app.route('/upload', methods=['POST'])
@login_required
def upload():
    file = request.files['file']
    filename = file.filename
    file.save(os.path.join('/uploads', filename))
    return jsonify({'filename': filename})

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()
```''', r'''<think>
Let me review this Flask application for security, design, and correctness issues.

1. SQL Injection:
- login() uses f-string interpolation for username and password in SQL query. Classic SQL injection: username = "' OR 1=1 --" bypasses authentication entirely.
- get_user() interpolates user_id directly into SQL. Since user_id comes from the URL and is not typed, it can contain arbitrary SQL.

2. Password handling:
- Passwords are stored in plain text (compared directly in SQL).
- get_user returns the password field in the JSON response to anyone (no auth required).
- admin_users also returns passwords for all users.

3. Security:
- app.secret_key is hardcoded. Anyone who reads the source code can forge session cookies.
- get_user has no authentication -- anyone can view any user profile including passwords.
- The upload endpoint has path traversal vulnerability: filename could be "../../../etc/cron.d/malicious". Need secure_filename().
- No file type validation on upload.
- No file size limit.

4. Session management:
- Role is stored in session cookie. Since Flask sessions are client-side (signed but not encrypted), the role value is visible to the user. If the secret key is compromised, the user can change their role to admin.

5. Design:
- SQLite with no connection pooling or WAL mode -- will have locking issues under concurrent access.
- No CSRF protection for state-changing operations.
- No input validation on any endpoint.
- data['username'] and data['password'] can raise KeyError if fields are missing.
- request.files['file'] can raise KeyError if no file is sent.

Let me write the structured review.
</think>

## Code Review: Flask Application

### CRITICAL - SQL Injection (Multiple)

**SQL1: Login endpoint SQL injection (Severity: CRITICAL)**
```python
f"SELECT * FROM users WHERE username='{username}' AND password='{password}'"
```
An attacker can bypass authentication entirely with `username = "' OR 1=1 --"`. This grants access to the first user in the database (often admin). Use parameterized queries:
```python
db.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
```

**SQL2: get_user SQL injection (Severity: CRITICAL)**
`user_id` from the URL path is interpolated directly into SQL. Despite appearing numeric, Flask does not enforce types on route parameters by default.

### CRITICAL - Password Exposure

**PW1: Plain text password storage (Severity: CRITICAL)**
Passwords are compared as plain text in the database. If the database is compromised, all credentials are immediately exposed. Use bcrypt or argon2 for hashing.

**PW2: Passwords returned in API responses (Severity: CRITICAL)**
Both `get_user` and `admin_users` include the password field in JSON responses. The get_user endpoint requires no authentication at all -- anyone can read any user's password.

### CRITICAL - File Upload Vulnerabilities

**FU1: Path traversal in upload (Severity: CRITICAL)**
`file.filename` is used directly. A crafted filename like `../../../etc/cron.d/backdoor` writes to arbitrary filesystem locations. Use `werkzeug.utils.secure_filename`:
```python
from werkzeug.utils import secure_filename
filename = secure_filename(file.filename)
```

**FU2: No file type or size validation (Severity: HIGH)**
No restrictions on file type or size. An attacker can upload executable files or exhaust disk space. Add `MAX_CONTENT_LENGTH` and validate extensions.

### HIGH - Secret Management

**SEC1: Hardcoded secret key (Severity: HIGH)**
`app.secret_key = 'my-secret-key-123'` is committed to source control. Anyone with code access can forge session cookies, escalating to admin. Load from environment:
```python
app.secret_key = os.environ['FLASK_SECRET_KEY']
```

**SEC2: Client-side role storage (Severity: HIGH)**
Flask sessions are signed but not encrypted -- the role is visible in the cookie. If the secret key leaks, users can set `role: admin`. Store roles server-side only.

### MEDIUM - Error Handling

**EH1: Unhandled KeyError on missing fields (Severity: MEDIUM)**
`data['username']`, `data['password']`, `request.files['file']` all raise KeyError (500 error) when fields are missing. Use `.get()` with validation or try/except.

### MEDIUM - Design

**D1: No CSRF protection (Severity: MEDIUM)**
State-changing POST endpoints have no CSRF protection. Use Flask-WTF's CSRFProtect.

**D2: Unauthenticated user endpoint (Severity: MEDIUM)**
`get_user` requires no login. Even without the password leak, exposing user data to anonymous users may violate privacy requirements.

**D3: SQLite concurrency limitations (Severity: LOW)**
SQLite with default settings has write locking issues under concurrent access. Enable WAL mode or use a proper database for production.'''),

    ("thinking/code-review", r'''Review this Flask code and identify issues:

```python
from flask import Flask, Blueprint, request, jsonify, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_marshmallow import Marshmallow
from flask_caching import Cache
from celery import Celery

db = SQLAlchemy()
ma = Marshmallow()
cache = Cache()
celery = Celery()

def create_app():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://user:pass@localhost/mydb'
    app.config['CACHE_TYPE'] = 'simple'
    app.config['CELERY_BROKER_URL'] = 'redis://localhost:6379/0'

    db.init_app(app)
    ma.init_app(app)
    cache.init_app(app)

    from .routes import api_bp
    app.register_blueprint(api_bp, url_prefix='/api')

    return app

# routes.py
api_bp = Blueprint('api', __name__)

class ItemSchema(ma.Schema):
    class Meta:
        fields = ('id', 'name', 'price', 'category', 'created_at')

item_schema = ItemSchema()
items_schema = ItemSchema(many=True)

@api_bp.route('/items', methods=['GET'])
@cache.cached(timeout=300)
def list_items():
    category = request.args.get('category')
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    sort = request.args.get('sort', 'created_at')

    query = db.session.query(Item)
    if category:
        query = query.filter(Item.category == category)
    if min_price:
        query = query.filter(Item.price >= min_price)
    if max_price:
        query = query.filter(Item.price <= max_price)
    query = query.order_by(sort)
    items = query.all()

    return jsonify(items_schema.dump(items))

@api_bp.route('/items', methods=['POST'])
def create_item():
    data = request.get_json()
    item = Item(**data)
    db.session.add(item)
    db.session.commit()
    return jsonify(item_schema.dump(item)), 201

@api_bp.route('/items/<int:item_id>', methods=['PUT'])
def update_item(item_id):
    item = Item.query.get(item_id)
    data = request.get_json()
    for key, value in data.items():
        setattr(item, key, value)
    db.session.commit()
    return jsonify(item_schema.dump(item))

@api_bp.route('/items/<int:item_id>', methods=['DELETE'])
def delete_item(item_id):
    item = Item.query.get(item_id)
    db.session.delete(item)
    db.session.commit()
    return '', 204

@api_bp.route('/items/bulk', methods=['POST'])
def bulk_create():
    items_data = request.get_json()
    for item_data in items_data:
        item = Item(**item_data)
        db.session.add(item)
    db.session.commit()
    return jsonify({'created': len(items_data)}), 201
```''', r'''<think>
Let me review this Flask application with blueprints and extensions.

1. Caching issues:
- cache.cached(timeout=300) on list_items caches by URL path only. Since query parameters (category, min_price, etc.) change the result, but the cache key is just '/api/items', every query returns the same cached result regardless of filters. The first request's response is served for all subsequent requests for 5 minutes.

2. Security / Mass assignment:
- create_item does Item(**data) with unvalidated request data. This is mass assignment -- a client can set any model field including id, created_at, or any other column.
- update_item iterates over data.items() and calls setattr for each key. Same mass assignment vulnerability -- a client can modify protected fields.

3. Error handling:
- update_item and delete_item use Item.query.get(item_id) which returns None if not found. Then db.session.delete(None) or setattr on None raises an exception, returning 500 instead of 404.
- create_item: request.get_json() returns None if body is not JSON. Item(**None) raises TypeError.
- bulk_create: no validation on individual items, no limit on batch size.

4. Query injection:
- query.order_by(sort) takes user input directly. While SQLAlchemy is safer than raw SQL, passing arbitrary strings to order_by can cause errors or unexpected behavior. Should validate against allowed columns.

5. Configuration:
- Database credentials hardcoded in the app factory: 'postgresql://user:pass@localhost/mydb'. Should use environment variables.
- CACHE_TYPE = 'simple' is in-memory and not suitable for production. Does not work across multiple workers.
- Celery is initialized but never properly configured with the Flask app context.

6. Schema issues:
- ItemSchema is defined as ma.Schema but instantiated at module level. Since Marshmallow is initialized with init_app, the schema may not have the app context available when first imported, depending on import order.

7. Blueprint organization:
- The Item model is used but never imported in the routes file.

Let me structure this review.
</think>

## Code Review: Flask Blueprint Application

### CRITICAL - Caching Bug

**CACHE1: Cache ignores query parameters (Severity: CRITICAL)**
`@cache.cached(timeout=300)` on `list_items` generates the cache key from the URL path only (`/api/items`). Query parameters like `category`, `min_price`, `max_price`, and `sort` are ignored. The first request's response is cached and returned for all subsequent requests regardless of filters.

Fix: Include query string in cache key:
```python
@cache.cached(timeout=300, query_string=True)
```
Or use `make_cache_key` to build a custom key.

### CRITICAL - Mass Assignment

**MA1: Unvalidated kwargs in create_item (Severity: CRITICAL)**
```python
item = Item(**data)
```
A client can set any model column: `id`, `created_at`, or any other field. Validate against an allowlist of fields or use the Marshmallow schema for deserialization with `load()`.

**MA2: Unvalidated setattr in update_item (Severity: CRITICAL)**
```python
for key, value in data.items():
    setattr(item, key, value)
```
Same mass assignment vulnerability. An attacker can modify protected columns. Use schema validation:
```python
data = item_schema.load(request.get_json(), partial=True)
```

### HIGH - Missing Error Handling

**EH1: No 404 handling on get/update/delete (Severity: HIGH)**
`Item.query.get(item_id)` returns None when the item does not exist. `update_item` then calls `setattr(None, ...)` and `delete_item` calls `db.session.delete(None)`, both producing 500 errors.

Fix:
```python
item = Item.query.get(item_id)
if item is None:
    return jsonify({'error': 'Item not found'}), 404
```

**EH2: No JSON body validation (Severity: MEDIUM)**
`request.get_json()` returns None when the Content-Type is wrong or the body is not valid JSON. `Item(**None)` raises TypeError.

### HIGH - Query Issues

**Q1: Unvalidated sort parameter (Severity: HIGH)**
`query.order_by(sort)` passes user input directly as the ordering column. While SQLAlchemy protects against SQL injection here, arbitrary strings cause application errors. Validate against allowed columns:
```python
ALLOWED_SORT = {'name', 'price', 'created_at'}
if sort not in ALLOWED_SORT:
    return jsonify({'error': 'Invalid sort field'}), 400
```

**Q2: No pagination on list_items (Severity: MEDIUM)**
`query.all()` loads every matching item into memory. Add limit/offset or cursor-based pagination.

### HIGH - Configuration

**CFG1: Hardcoded database credentials (Severity: HIGH)**
`'postgresql://user:pass@localhost/mydb'` is in source code. Use environment variables:
```python
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ['DATABASE_URL']
```

**CFG2: In-memory cache not production-ready (Severity: MEDIUM)**
`CACHE_TYPE = 'simple'` stores cache in-process memory. With multiple workers, each has its own cache, causing inconsistencies. Use Redis for production.

**CFG3: Celery not integrated with Flask app (Severity: MEDIUM)**
The Celery instance is created at module level but never configured with the Flask app context. Celery tasks will not have access to Flask extensions or configuration.

### MEDIUM - Bulk Operations

**B1: No batch size limit (Severity: MEDIUM)**
`bulk_create` accepts an unbounded list. A client can send millions of items in one request, exhausting memory and locking the database. Add a maximum batch size.

**B2: No individual validation (Severity: MEDIUM)**
If one item in the batch is invalid, the entire commit fails, but no helpful error is returned. Validate each item and report which ones failed.'''),

    ("thinking/code-review", r'''Review this Flask testing code and identify issues:

```python
import pytest
import json
from unittest.mock import patch, MagicMock
from app import create_app, db
from app.models import User, Item

@pytest.fixture
def app():
    app = create_app()
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth_headers():
    return {'Authorization': 'Bearer test-token-123'}

class TestItems:
    def test_create_item(self, client, auth_headers):
        response = client.post('/api/items',
            data=json.dumps({'name': 'Test', 'price': 9.99}),
            content_type='application/json',
            headers=auth_headers)
        assert response.status_code == 201

    def test_list_items(self, client):
        item1 = Item(name='A', price=10.0, category='electronics')
        item2 = Item(name='B', price=20.0, category='books')
        db.session.add_all([item1, item2])
        db.session.commit()
        response = client.get('/api/items')
        data = json.loads(response.data)
        assert len(data) == 2

    def test_update_item(self, client, auth_headers):
        item = Item(name='Old', price=5.0, category='misc')
        db.session.add(item)
        db.session.commit()
        response = client.put(f'/api/items/{item.id}',
            data=json.dumps({'name': 'New'}),
            content_type='application/json',
            headers=auth_headers)
        assert response.status_code == 200
        assert json.loads(response.data)['name'] == 'New'

    def test_delete_item(self, client, auth_headers):
        item = Item(name='Delete Me', price=1.0, category='trash')
        db.session.add(item)
        db.session.commit()
        response = client.delete(f'/api/items/{item.id}',
            headers=auth_headers)
        assert response.status_code == 204

    @patch('app.routes.external_service')
    def test_with_mock(self, mock_service, client):
        mock_service.get_price.return_value = 42.0
        response = client.get('/api/items/price-check/123')
        assert response.status_code == 200
        mock_service.get_price.assert_called_once_with('123')

    def test_search(self, client):
        for i in range(100):
            db.session.add(Item(name=f'Item {i}', price=float(i), category='test'))
        db.session.commit()
        response = client.get('/api/items?category=test&min_price=50')
        data = json.loads(response.data)
        assert all(item['price'] >= 50 for item in data)

    def test_error_handling(self, client):
        response = client.get('/api/items/99999')
        assert response.status_code == 404

    def test_bulk_create(self, client, auth_headers):
        items = [{'name': f'Bulk {i}', 'price': float(i)} for i in range(10)]
        response = client.post('/api/items/bulk',
            data=json.dumps(items),
            content_type='application/json',
            headers=auth_headers)
        assert response.status_code == 201
```''', r'''<think>
Let me review this Flask test suite for test isolation, fixture design, mock usage, assertion quality, and coverage gaps.

1. Test isolation:
- test_list_items creates items directly via db.session but shares the same database with other tests. If test ordering changes, stale data from previous tests could affect results. Each test should clean up or use transactions.
- Actually, the fixture yields then calls db.drop_all(), but the issue is that all tests in the class share the same app/db context within a single test run. If tests run in different orders, the auto-increment IDs change.

2. Fixture issues:
- auth_headers returns a hardcoded token 'test-token-123'. There is no setup that actually makes this token valid. If the app validates tokens, all authenticated tests pass with a fake token that would never work. If the app does NOT validate tokens in testing mode, then the tests are not testing authentication at all.
- The app fixture configures sqlite in memory but the production app uses PostgreSQL. SQLite has different behavior (no strict typing, different date handling, no array types, etc.). Tests may pass on SQLite but fail on PostgreSQL.

3. Assertion quality:
- test_create_item only checks status_code == 201. Does not verify the response body, database state, or that the item was actually created correctly.
- test_delete_item checks status 204 but does not verify the item was actually removed from the database.
- test_list_items checks len(data) == 2 but does not verify the content of the items.
- test_search does not verify the total count of returned items (could return 0 and still pass `all()`).

4. Mock issues:
- test_with_mock patches 'app.routes.external_service' but the patch decorator and method argument ordering may conflict with pytest fixtures in a class. In unittest-style, @patch passes the mock as the first positional arg after self. This means mock_service is the mock and client is not injected. Actually, with pytest, the fixture injection happens by name, so `client` should still work. But the ordering of mock_service before client suggests confusion.

5. Missing test coverage:
- No tests for validation errors (missing required fields, wrong types).
- No tests for concurrent operations.
- No tests for edge cases (empty name, negative price, very long strings).
- No test for unauthorized access (missing auth headers).
- No test for pagination behavior.
- No test for the actual auth mechanism.

6. Database session usage:
- Tests directly use db.session to create test data, but the app might use a different session scope. This can cause issues where test data is not visible to the application during requests.

Let me write the review.
</think>

## Code Review: Flask Test Suite

### HIGH - Test Authenticity

**TA1: Fake auth token with no validation (Severity: HIGH)**
```python
@pytest.fixture
def auth_headers():
    return {'Authorization': 'Bearer test-token-123'}
```
This token is hardcoded and never validated. Either the application skips token validation in test mode (meaning auth is never tested) or the tests would fail. Neither outcome is good. Create a real test user and generate a valid token:
```python
@pytest.fixture
def auth_headers(app):
    user = User(username='testuser', email='test@example.com')
    db.session.add(user)
    db.session.commit()
    token = generate_token(user)
    return {'Authorization': f'Bearer {token}'}
```

**TA2: SQLite vs PostgreSQL mismatch (Severity: HIGH)**
Tests use `sqlite:///:memory:` but production uses PostgreSQL. SQLite lacks strict typing, has different locking behavior, and missing features (array types, JSON operators). Tests may pass on SQLite but fail in production. Use a test PostgreSQL database or testcontainers.

### HIGH - Weak Assertions

**WA1: test_create_item checks only status code (Severity: HIGH)**
```python
assert response.status_code == 201
```
This verifies the endpoint did not crash, but not that the item was correctly created. Add assertions:
```python
data = json.loads(response.data)
assert data['name'] == 'Test'
assert data['price'] == 9.99
assert Item.query.count() == 1
```

**WA2: test_delete_item does not verify deletion (Severity: HIGH)**
Only checks status 204. The item might still exist in the database. Add:
```python
assert Item.query.get(item.id) is None
```

**WA3: test_search passes vacuously on empty results (Severity: MEDIUM)**
```python
assert all(item['price'] >= 50 for item in data)
```
`all()` on an empty iterable returns True. If the query returns zero items, this assertion passes. Add a count check:
```python
assert len(data) == 50  # items 50-99
assert all(item['price'] >= 50 for item in data)
```

### MEDIUM - Test Isolation

**TI1: Shared database state between tests (Severity: MEDIUM)**
Tests in the class share the same database context. `test_list_items` inserts 2 items, `test_search` inserts 100. If they run in the same session without per-test cleanup, item counts can be wrong. Use a per-test transaction rollback:
```python
@pytest.fixture(autouse=True)
def session(app):
    connection = db.engine.connect()
    transaction = connection.begin()
    # bind session to this connection
    yield
    transaction.rollback()
    connection.close()
```

### MEDIUM - Missing Coverage

**MC1: No negative test cases**
Missing tests for:
- Missing required fields in POST (should return 400)
- Invalid data types (string for price)
- Unauthorized access (no auth headers, should return 401)
- Creating items with negative prices

**MC2: No edge case tests**
Missing tests for:
- Empty string name
- Extremely long strings
- Price of 0.0
- Unicode characters in names
- SQL-special characters in search queries

**MC3: No pagination test**
If `list_items` has no pagination (as noted in the code review), a test with many items would demonstrate the problem.

### LOW - Style

**S1: json.dumps + content_type repetition**
Every POST test manually serializes JSON and sets content_type. Use a helper or `client.post(..., json={...})` which Flask test client supports:
```python
response = client.post('/api/items', json={'name': 'Test', 'price': 9.99})
```'''),

    ("thinking/code-review", r'''Review this Flask code and identify issues:

```python
from flask import Flask, request, jsonify, make_response
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import jwt
import datetime
import os
import logging
from logging.handlers import RotatingFileHandler

app = Flask(__name__)

limiter = Limiter(app, key_func=get_remote_address)

JWT_SECRET = os.environ.get('JWT_SECRET', 'fallback-secret')
JWT_ALGORITHM = 'HS256'

handler = RotatingFileHandler('app.log', maxBytes=10000, backupCount=1)
handler.setLevel(logging.INFO)
app.logger.addHandler(handler)

def token_required(f):
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization')
        if not token:
            return jsonify({'error': 'token missing'}), 401
        try:
            data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            request.user = data
        except:
            return jsonify({'error': 'invalid token'}), 401
        return f(*args, **kwargs)
    return decorated

@app.route('/auth/login', methods=['POST'])
@limiter.limit("5 per minute")
def login():
    data = request.get_json()
    user = authenticate(data.get('username'), data.get('password'))
    if user:
        token = jwt.encode({
            'user_id': user['id'],
            'role': user['role'],
            'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
        }, JWT_SECRET, algorithm=JWT_ALGORITHM)
        return jsonify({'token': token})
    return jsonify({'error': 'bad credentials'}), 401

@app.route('/auth/refresh', methods=['POST'])
@token_required
def refresh():
    token = jwt.encode({
        'user_id': request.user['user_id'],
        'role': request.user['role'],
        'exp': datetime.datetime.utcnow() + datetime.timedelta(days=30)
    }, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return jsonify({'token': token})

@app.route('/auth/change-password', methods=['POST'])
@token_required
def change_password():
    data = request.get_json()
    old_password = data['old_password']
    new_password = data['new_password']
    user = get_user(request.user['user_id'])
    if user['password'] == old_password:
        update_password(request.user['user_id'], new_password)
        return jsonify({'message': 'password changed'})
    return jsonify({'error': 'wrong password'}), 400

@app.errorhandler(429)
def ratelimit_handler(e):
    return jsonify({'error': 'rate limit exceeded'}), 429

@app.errorhandler(Exception)
def handle_exception(e):
    app.logger.error(f'Unhandled exception: {e}')
    return jsonify({'error': str(e)}), 500
```''', r'''<think>
Let me review this Flask authentication/authorization code.

1. JWT and Token issues:
- JWT_SECRET has a fallback 'fallback-secret'. If the environment variable is not set, all tokens are signed with a known secret. This must fail loudly, not fall back silently.
- Token expiry is 30 days, which is extremely long for an access token. If a token is compromised, the attacker has 30 days of access.
- The refresh endpoint issues a new 30-day token using the old token. There is no refresh token concept -- the access token IS the refresh token. And there is no token revocation mechanism, so compromised tokens cannot be invalidated.
- The role is embedded in the JWT. If a user's role is changed (demoted from admin), their existing token still has the old role for up to 30 days.
- No token type distinction. The same token works for both access and refresh.

2. Security:
- token_required uses a bare `except:` which catches everything including SystemExit and KeyboardInterrupt. Should catch jwt.PyJWTError specifically.
- token_required does not use @wraps(f), so the decorated function loses its name and docstring. This breaks Flask's URL routing if multiple endpoints use the decorator.
- change_password compares passwords in plain text: `user['password'] == old_password`. Passwords should be hashed.
- change_password does not invalidate existing sessions/tokens after password change. The old token (with 30-day expiry) still works.
- The Authorization header token is used directly without stripping the "Bearer " prefix. If the client sends "Bearer <token>", the decode will fail.

3. Logging:
- RotatingFileHandler with maxBytes=10000 (10KB) is tiny. This will rotate extremely frequently. And backupCount=1 means only one backup -- you lose logs quickly.
- handle_exception logs with f-string interpolation, not lazy formatting.
- handle_exception returns str(e) to the client, potentially leaking internal details (stack traces, file paths, database errors).

4. Rate limiting:
- Only the login endpoint is rate limited. The change-password endpoint is not, allowing brute-force attacks on old_password.
- The refresh endpoint is not rate limited.

5. Missing features:
- No token blacklist/revocation
- No password strength validation
- No account lockout after failed attempts
- authenticate() function is referenced but not defined

Let me structure this.
</think>

## Code Review: Flask Authentication System

### CRITICAL - Token Security

**T1: Fallback JWT secret (Severity: CRITICAL)**
```python
JWT_SECRET = os.environ.get('JWT_SECRET', 'fallback-secret')
```
If the environment variable is missing, all tokens are signed with a known, hardcoded secret. Anyone can forge valid tokens. Remove the fallback and fail loudly:
```python
JWT_SECRET = os.environ['JWT_SECRET']
```

**T2: 30-day token expiry with no revocation (Severity: CRITICAL)**
Access tokens last 30 days with no mechanism to revoke them. If a token is stolen, the attacker has a month of access. If a user's role changes, the old role persists in the JWT. Implement short-lived access tokens (15 minutes) with separate refresh tokens, and a token blacklist.

**T3: Missing Bearer prefix handling (Severity: HIGH)**
```python
token = request.headers.get('Authorization')
jwt.decode(token, ...)
```
The Authorization header typically contains `Bearer <token>`. The code passes the entire header value including "Bearer " to jwt.decode, which will fail. Parse the prefix:
```python
auth = request.headers.get('Authorization', '')
if not auth.startswith('Bearer '):
    return jsonify({'error': 'invalid header'}), 401
token = auth[7:]
```

### CRITICAL - Password Handling

**PW1: Plain text password comparison (Severity: CRITICAL)**
```python
if user['password'] == old_password:
```
This implies passwords are stored unhashed. Use bcrypt:
```python
if bcrypt.check_password_hash(user['password_hash'], old_password):
```

**PW2: No token invalidation after password change (Severity: HIGH)**
After changing password, all existing tokens remain valid for up to 30 days. An attacker who stole the old password AND a token retains access. Invalidate all tokens on password change (e.g., change the user's token version).

### HIGH - Decorator Bug

**DEC1: Missing @wraps in token_required (Severity: HIGH)**
```python
def token_required(f):
    def decorated(*args, **kwargs):
```
Without `@wraps(f)`, all decorated functions have the name "decorated". Flask uses function names for URL routing, so the second endpoint using `@token_required` will collide with the first, causing a routing error. Add `from functools import wraps` and `@wraps(f)`.

### HIGH - Exception Handling

**EX1: Bare except in token_required (Severity: HIGH)**
```python
except:
    return jsonify({'error': 'invalid token'}), 401
```
This catches SystemExit, KeyboardInterrupt, and MemoryError, masking serious failures as auth errors. Catch specific exceptions:
```python
except jwt.ExpiredSignatureError:
    return jsonify({'error': 'token expired'}), 401
except jwt.InvalidTokenError:
    return jsonify({'error': 'invalid token'}), 401
```

**EX2: Error details leaked to client (Severity: MEDIUM)**
`handle_exception` returns `str(e)`, which may contain stack traces, file paths, or database connection strings. Return a generic message in production.

### MEDIUM - Rate Limiting Gaps

**RL1: change-password not rate limited (Severity: MEDIUM)**
The password change endpoint has no rate limit, allowing brute-force attacks on `old_password`. Add rate limiting.

**RL2: refresh not rate limited (Severity: LOW)**
Token refresh should be rate limited to prevent token farming.

### LOW - Logging

**LOG1: Tiny log file size (Severity: LOW)**
`maxBytes=10000` (10 KB) with `backupCount=1` means you keep at most ~20 KB of logs. Set maxBytes to at least 10 MB and backupCount to 5-10 for meaningful log retention.'''),

    ("thinking/code-review", r'''Review this Flask code and identify issues:

```python
from flask import Flask, request, jsonify, g
import os
import redis
import json
from datetime import datetime, timedelta

app = Flask(__name__)

class Config:
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379')
    DEBUG = True
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024

class ProductionConfig(Config):
    DEBUG = False

class DevelopmentConfig(Config):
    DEBUG = True

app.config.from_object(Config)

redis_client = redis.from_url(app.config['REDIS_URL'])

@app.before_request
def before_request():
    g.start_time = datetime.now()
    g.request_id = os.urandom(16).hex()

@app.after_request
def after_request(response):
    duration = (datetime.now() - g.start_time).total_seconds()
    redis_client.lpush('request_log', json.dumps({
        'request_id': g.request_id,
        'method': request.method,
        'path': request.path,
        'status': response.status_code,
        'duration': duration,
        'ip': request.remote_addr,
        'user_agent': request.headers.get('User-Agent'),
        'timestamp': str(datetime.now()),
    }))
    return response

@app.route('/api/config')
def get_config():
    return jsonify({
        'debug': app.config['DEBUG'],
        'max_upload': app.config['MAX_CONTENT_LENGTH'],
        'redis_url': app.config['REDIS_URL'],
        'secret_key': app.config['SECRET_KEY'],
        'environment': os.environ.get('FLASK_ENV', 'development'),
    })

@app.route('/api/health')
def health():
    try:
        redis_client.ping()
        return jsonify({'status': 'healthy', 'redis': 'connected'})
    except:
        return jsonify({'status': 'unhealthy', 'redis': 'disconnected'})

@app.route('/api/feature-flags')
def feature_flags():
    flags = {}
    for key in redis_client.scan_iter('flag:*'):
        flags[key.decode()] = redis_client.get(key).decode()
    return jsonify(flags)

@app.route('/api/feature-flags/<flag_name>', methods=['PUT'])
def set_flag(flag_name):
    data = request.get_json()
    redis_client.set(f'flag:{flag_name}', json.dumps(data['value']))
    return jsonify({'flag': flag_name, 'value': data['value']})

@app.route('/api/cache/<key>')
def get_cache(key):
    value = redis_client.get(f'cache:{key}')
    if value:
        return jsonify({'key': key, 'value': json.loads(value)})
    return jsonify({'error': 'not found'}), 404

@app.route('/api/cache/<key>', methods=['PUT'])
def set_cache(key):
    data = request.get_json()
    ttl = data.get('ttl', 3600)
    redis_client.setex(f'cache:{key}', ttl, json.dumps(data['value']))
    return jsonify({'key': key, 'ttl': ttl})
```''', r'''<think>
Let me review this Flask application with Redis integration and configuration management.

1. Configuration issues:
- The app always uses Config (base class), never ProductionConfig. The config classes exist but there is no mechanism to select between them based on environment. `app.config.from_object(Config)` always loads the base.
- DEBUG = True in the base Config means production uses debug mode by default.
- SECRET_KEY has a fallback 'dev' -- same issue as before, insecure in production.

2. Critical security -- get_config endpoint:
- /api/config exposes SECRET_KEY and REDIS_URL to anyone! This endpoint literally dumps sensitive configuration including secrets and connection strings. An attacker gets everything needed to forge sessions and connect to Redis.
- No authentication required.

3. Redis issues:
- after_request logs every request to Redis via lpush with no TTL. The 'request_log' list grows indefinitely, consuming Redis memory until the server runs out and crashes.
- redis_client is created at module level. If Redis is unavailable at startup, the import fails.
- feature_flags uses scan_iter which can be slow on large keyspaces. Also, no authentication on flag management -- anyone can change feature flags.

4. Error handling:
- health endpoint catches all exceptions with bare except. Even if Redis is down, it returns 200 with status "unhealthy". Load balancers typically check status codes, not response bodies, so the health check always appears healthy.
- No error handling on Redis operations in other endpoints. If Redis is down, endpoints crash with 500.
- set_flag and set_cache: data['value'] raises KeyError if missing. request.get_json() can return None.

5. Cache endpoint security:
- /api/cache/<key> allows reading and writing arbitrary cache entries. An attacker can read sensitive cached data or overwrite cache entries with malicious values. There is no authentication.
- The TTL comes from user input with no bounds. A user could set TTL to billions, effectively making entries permanent.

6. Request logging:
- Logging User-Agent and IP to Redis on every request is fine for analytics but has privacy implications (PII storage in Redis with no TTL and no encryption).
- The request_log has no trimming -- it is a list that only grows.

Let me structure this.
</think>

## Code Review: Flask Configuration and Redis Application

### CRITICAL - Secret Exposure

**SEC1: Configuration endpoint leaks secrets (Severity: CRITICAL)**
```python
@app.route('/api/config')
def get_config():
    return jsonify({
        'secret_key': app.config['SECRET_KEY'],
        'redis_url': app.config['REDIS_URL'],
    })
```
This unauthenticated endpoint exposes the secret key (enabling session forgery) and Redis connection URL (enabling unauthorized data access). Remove this endpoint entirely or restrict it to development mode behind authentication.

**SEC2: Unauthenticated feature flag management (Severity: CRITICAL)**
Anyone can read and modify feature flags via PUT. An attacker can enable or disable features, potentially exposing beta functionality or disabling security features. Add authentication.

**SEC3: Arbitrary cache read/write (Severity: CRITICAL)**
`/api/cache/<key>` endpoints allow anyone to read or overwrite any cache entry. An attacker can read cached session data, API responses, or inject malicious values. Remove public access or add strict authentication and key namespace restrictions.

### HIGH - Configuration Management

**CFG1: Config class selection is broken (Severity: HIGH)**
```python
app.config.from_object(Config)
```
This always loads the base Config class. `ProductionConfig` and `DevelopmentConfig` are defined but never used. The base class has `DEBUG = True`, so production runs in debug mode (which enables the interactive debugger and stack traces).

Fix:
```python
config_map = {
    'production': ProductionConfig,
    'development': DevelopmentConfig,
}
env = os.environ.get('FLASK_ENV', 'development')
app.config.from_object(config_map.get(env, Config))
```

**CFG2: Secret key fallback (Severity: HIGH)**
`SECRET_KEY = os.environ.get('SECRET_KEY', 'dev')` falls back to a known value. In production, all sessions can be forged. Fail if the variable is not set in production.

### HIGH - Memory Leak

**MEM1: Unbounded request log in Redis (Severity: HIGH)**
`redis_client.lpush('request_log', ...)` is called on every request with no TTL or trimming. The list grows indefinitely, consuming Redis memory. At scale, this will cause Redis OOM kills.

Fix: Use `ltrim` to cap the list size:
```python
redis_client.lpush('request_log', json.dumps(log_entry))
redis_client.ltrim('request_log', 0, 99999)  # keep last 100k entries
```
Or use a time-series database for request logging.

### MEDIUM - Health Check

**HC1: Health check returns 200 when unhealthy (Severity: MEDIUM)**
```python
except:
    return jsonify({'status': 'unhealthy', 'redis': 'disconnected'})
```
Returns HTTP 200 even when Redis is down. Load balancers check status codes, not response bodies. Return 503:
```python
except Exception:
    return jsonify({'status': 'unhealthy'}), 503
```

### MEDIUM - Error Handling

**EH1: No Redis error handling in endpoints (Severity: MEDIUM)**
If Redis becomes unavailable after startup, every endpoint crashes with an unhandled ConnectionError. Wrap Redis operations in try/except or use a circuit breaker.

**EH2: No input validation (Severity: MEDIUM)**
`data['value']` raises KeyError, `request.get_json()` returns None on bad Content-Type. Validate inputs before accessing.

### LOW - Privacy

**P1: PII in unbounded Redis log (Severity: LOW)**
IP addresses and User-Agent strings are PII under GDPR. Storing them indefinitely in Redis without encryption or retention policies creates compliance risk.'''),
]
