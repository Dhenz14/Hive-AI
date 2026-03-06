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

Starting with the login endpoint. The SQL query uses f-string interpolation: f"SELECT * FROM users WHERE username='{username}' AND password='{password}'". Could this be safe if Flask sanitizes inputs somehow? No -- Flask does no input sanitization. This is classic SQL injection. An attacker can pass username = "' OR 1=1 --" and bypass authentication entirely, gaining access to the first user (often admin).

Wait, get_user() has the same problem with user_id. I initially assumed user_id would be an integer since it looks like a database ID, but Flask does not enforce types on route parameters by default. So user_id could contain arbitrary SQL like "1 OR 1=1".

Password handling is alarming. Passwords are compared directly in SQL, meaning they are stored in plain text. But actually it gets worse -- get_user returns the password field in the JSON response, and it requires no authentication! Anyone can read any user's password by hitting /users/<id>. The admin_users endpoint also returns passwords for all users. Even with the login_required decorator, the password exposure is inexcusable.

Security: app.secret_key = 'my-secret-key-123' is hardcoded in source. I considered whether this might be overridden by environment config elsewhere, but there is no indication of that. Anyone who reads the source can forge session cookies and escalate to admin. Actually, since Flask sessions are client-side (signed but not encrypted), the role value is already visible in the cookie even without the secret key. With the secret key, an attacker can change their role to admin.

The upload endpoint -- at first I thought path traversal might be mitigated by os.path.join, but no. A filename like "../../../etc/cron.d/malicious" would resolve to /etc/cron.d/malicious because os.path.join does not prevent directory traversal. Need werkzeug.utils.secure_filename(). There is also no file type validation or size limit.

Design issues: data['username'] and data['password'] will raise KeyError (producing 500 errors) if the JSON body is missing those fields. Same for request.files['file']. No CSRF protection, no input validation, and SQLite without WAL mode will have locking issues under concurrent writes.

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

The caching decorator immediately catches my eye. cache.cached(timeout=300) on list_items -- could this properly cache different filtered results? Hmm, let me think about how Flask-Caching generates cache keys. By default, it uses the URL path only. Since query parameters (category, min_price, etc.) change the result but the cache key is just '/api/items', the first request's response is served for ALL subsequent requests regardless of filters. That is a critical bug -- a user searching for "electronics" gets the same cached result as someone searching for "books" for 5 minutes.

Mass assignment is the next major issue. create_item does Item(**data) with unvalidated request data. I considered whether Marshmallow might validate this, but the schema is only used for serialization (dump), not deserialization (load). Therefore a client can set any model field including id, created_at, or any other column. update_item has the same vulnerability via setattr in a loop.

Error handling -- update_item and delete_item use Item.query.get(item_id) which returns None if not found. I initially thought SQLAlchemy might raise an exception on None, but actually db.session.delete(None) raises UnmappedInstanceError, and setattr on None raises AttributeError. Both return 500 instead of a proper 404. Wait, create_item has another issue: request.get_json() returns None if the body is not valid JSON or the Content-Type is wrong, and then Item(**None) raises a TypeError.

query.order_by(sort) takes user input directly. While SQLAlchemy is safer than raw SQL here because it does not directly interpolate into SQL strings, passing arbitrary strings to order_by can still cause application errors or expose information about the schema. Should validate against an allowlist of allowed column names.

Configuration: database credentials are hardcoded ('postgresql://user:pass@localhost/mydb'). CACHE_TYPE = 'simple' is in-memory and will not work across multiple Gunicorn workers since each process has its own cache. Celery is initialized at module level but never configured with the Flask app context via init_app, so Celery tasks will not have access to Flask extensions.

The Item model is referenced in routes but never imported -- this would cause a NameError at runtime.

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

Starting with test isolation. test_list_items creates items directly via db.session, and test_search creates 100 items. Could these interfere with each other? The fixture yields and calls db.drop_all(), but wait -- all tests in the class share the same app/db context within a single test run. If test_search runs before test_list_items, the database already has 100 items, and len(data) == 2 would fail. Actually, I need to reconsider -- the fixture is function-scoped by default in pytest, so each test gets a fresh database. Hmm, but the fixture yields the app (not recreates), so it depends on whether create_all/drop_all properly resets auto-increment IDs. The isolation is fragile at best.

Fixture issues: auth_headers returns a hardcoded token 'test-token-123'. I initially thought this might be wired into a test configuration, but there is no setup that makes this token valid. If the app validates tokens, these tests would fail. If the app skips validation in testing mode, then authentication is never actually tested. Either way, the tests are misleading.

The app fixture uses sqlite:///:memory: but production uses PostgreSQL. I considered whether this might be acceptable for basic CRUD tests, but actually SQLite lacks strict typing, has different date handling, and no array types. Tests that pass on SQLite can fail on PostgreSQL due to these behavioral differences. This is a common trap.

Assertion quality is weak across the board. test_create_item only checks status_code == 201 -- it does not verify the response body or that the item actually exists in the database. test_delete_item checks status 204 but never confirms the item was removed. And here is a subtle one: test_search asserts `all(item['price'] >= 50 for item in data)`, but all() on an empty iterable returns True. If the query returns zero items, the assertion passes vacuously. Should add a count check first.

Mock usage: test_with_mock patches 'app.routes.external_service' with @patch. I was worried about argument ordering -- with unittest-style @patch, the mock is injected as a positional arg after self, which could conflict with pytest fixtures. But actually pytest injects fixtures by name, so `client` should be matched by name correctly. The ordering of mock_service before client is confusing but technically works.

Missing coverage is significant: no negative test cases (missing fields, wrong types), no edge cases (empty strings, negative prices), no auth testing, no pagination tests.

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

JWT_SECRET = os.environ.get('JWT_SECRET', 'fallback-secret'). Could this fallback be intentional for development? Maybe, but it is extremely dangerous. If the environment variable is not set in production, all tokens are signed with a publicly known secret. Anyone can forge valid tokens. This must fail loudly instead of falling back silently.

Token expiry is 30 days. I initially thought this might be acceptable for a "remember me" feature, but wait -- there is no distinction between access tokens and refresh tokens. The same token serves both purposes. And there is no revocation mechanism, so if a token is compromised, the attacker has 30 days of access with no way to stop them. The role is embedded in the JWT too, so if a user is demoted from admin, their existing token still has the old role.

The refresh endpoint is concerning -- it issues a new 30-day token using the old token. This means a stolen token can be refreshed indefinitely because each refresh produces a new 30-day token. Effectively, a single token theft grants permanent access.

Security issues in token_required: it uses a bare `except:` which catches everything including SystemExit and KeyboardInterrupt. I considered whether this might be acceptable as a catch-all auth check, but no -- it masks serious system errors as auth failures. Should catch jwt.PyJWTError specifically. Also, token_required does not use @wraps(f). Hmm, this is actually a show-stopper: without @wraps, all decorated functions are named "decorated". Flask uses function names for URL routing, so the second endpoint using @token_required collides with the first, causing a routing error.

Wait, there is another issue I almost missed: the Authorization header token is used directly without stripping the "Bearer " prefix. If the client sends "Bearer <token>" (the standard format), jwt.decode receives "Bearer eyJ..." which is not valid JWT and fails.

change_password compares passwords in plain text: user['password'] == old_password. This implies passwords are stored unhashed. And after changing the password, existing tokens are not invalidated -- the old token still works for up to 30 days.

Logging: RotatingFileHandler with maxBytes=10000 (10KB) is absurdly tiny. This rotates after roughly 100 log lines. With backupCount=1, you lose logs almost immediately. handle_exception returns str(e) to the client, potentially leaking file paths, database errors, or connection strings.

Rate limiting only covers login. The change-password endpoint is unprotected, allowing brute-force attacks on old_password.

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

Configuration first. The app uses app.config.from_object(Config) which always loads the base Config class. ProductionConfig and DevelopmentConfig exist but are never used. Could there be a mechanism elsewhere to switch configs? There is no indication of one. Since the base Config has DEBUG = True, production runs in debug mode by default, exposing the interactive debugger and stack traces. SECRET_KEY falls back to 'dev' if the environment variable is missing, which means session cookies can be forged.

Now, the /api/config endpoint -- wait, this literally dumps SECRET_KEY and REDIS_URL to any anonymous request! I initially thought it might be a debug-only endpoint, but there is no conditional check. An attacker gets everything needed to forge sessions and connect to Redis directly. This is catastrophic.

Redis issues: after_request logs every request via lpush to a 'request_log' list. Could Redis handle this volume? The problem is not throughput but memory -- there is no TTL and no ltrim. The list grows indefinitely, consuming Redis memory until the server runs OOM and crashes. I considered whether Redis eviction policies might help, but the default noeviction policy just rejects new writes, which would crash the application.

The health endpoint has a subtle bug. It catches all exceptions with bare except and returns 200 with {"status": "unhealthy"}. I initially thought this was fine since the body says "unhealthy", but actually load balancers check HTTP status codes, not response bodies. So the load balancer thinks the instance is healthy even when Redis is completely down. Should return 503.

Cache endpoint security: /api/cache/<key> allows reading and writing arbitrary cache entries with no authentication. An attacker could read cached session data or overwrite cache entries with malicious values. The TTL comes from user input with no upper bound -- a user could set TTL to billions of seconds, effectively making entries permanent.

Feature flags: scan_iter can be slow on large keyspaces, but the bigger issue is that anyone can modify feature flags via PUT with no authentication. An attacker could disable security features or enable beta functionality.

Request logging stores IP addresses and User-Agent strings in Redis with no TTL -- this is PII under GDPR stored indefinitely without encryption or retention policies.

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
