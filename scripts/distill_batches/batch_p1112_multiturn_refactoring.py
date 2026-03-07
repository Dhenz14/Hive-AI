"""
Multi-turn conversation training pairs - Progressive Code Refactoring
Start with working but messy code, improve step by step
"""

pairs = [
    {
        "instruction": r'''[Previous conversation]
User: I have a Flask app with database queries scattered across route handlers. Here is an example:

```python
@app.route('/users/<int:user_id>')
def get_user(user_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, email FROM users WHERE id = %s", (user_id,))
    row = cursor.fetchone()
    cursor.close()
    conn.close()
    if not row:
        return jsonify({"error": "Not found"}), 404
    return jsonify({"id": row[0], "name": row[1], "email": row[2]})

@app.route('/users', methods=['POST'])
def create_user():
    data = request.json
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO users (name, email) VALUES (%s, %s) RETURNING id",
                   (data['name'], data['email']))
    new_id = cursor.fetchone()[0]
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"id": new_id}), 201
```

Every route has the same connection/cursor/close boilerplate. How do I clean this up?
Assistant: Extract the database logic into a repository class. This separates data access from request handling and eliminates the repeated connection boilerplate.

[Current message]
User: I like that idea. Can you show me what the repository class would look like, and how the routes would change to use it?''',
        "output": r'''Here is a UserRepository class that encapsulates all the database logic, plus a context manager for connection handling:

```python
# db.py -- connection management
from contextlib import contextmanager
import psycopg2

@contextmanager
def get_connection():
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

# repositories/user_repository.py
class UserRepository:
    def get_by_id(self, user_id):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, email FROM users WHERE id = %s",
                (user_id,)
            )
            row = cursor.fetchone()
            if row is None:
                return None
            return {"id": row[0], "name": row[1], "email": row[2]}

    def create(self, name, email):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (name, email) VALUES (%s, %s) RETURNING id",
                (name, email)
            )
            new_id = cursor.fetchone()[0]
            return {"id": new_id, "name": name, "email": email}

    def list_all(self, limit=50, offset=0):
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, name, email FROM users ORDER BY id LIMIT %s OFFSET %s",
                (limit, offset)
            )
            return [{"id": r[0], "name": r[1], "email": r[2]} for r in cursor.fetchall()]

# routes/users.py -- clean route handlers
user_repo = UserRepository()

@app.route('/users/<int:user_id>')
def get_user(user_id):
    user = user_repo.get_by_id(user_id)
    if not user:
        return jsonify({"error": "Not found"}), 404
    return jsonify(user)

@app.route('/users', methods=['POST'])
def create_user():
    data = request.json
    user = user_repo.create(data['name'], data['email'])
    return jsonify(user), 201
```

The routes are now just thin handlers that validate input and call the repository. The connection boilerplate is in one place (the context manager), and all SQL is in the repository. If you later switch to SQLAlchemy or a different database, you only change the repository -- the routes stay the same.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I extracted my database queries into a UserRepository class with a get_connection() context manager. Routes are now clean and just call repo methods.
Assistant: Good separation. The repository handles all SQL and connection management, routes just handle HTTP concerns.

User: But there is no error handling. If the database is down or someone passes invalid data, the app crashes with a 500 error and an ugly traceback.

[Current message]
User: How should I add error handling? Should it go in the repository or in the routes?''',
        "output": r'''Error handling should be layered -- the repository catches database-specific errors and raises domain exceptions, and the routes (or a global handler) convert those to HTTP responses:

```python
# exceptions.py -- domain exceptions (not tied to HTTP or database)
class NotFoundError(Exception):
    def __init__(self, resource, identifier):
        self.resource = resource
        self.identifier = identifier
        super().__init__(f"{resource} not found: {identifier}")

class DuplicateError(Exception):
    def __init__(self, resource, field, value):
        self.resource = resource
        self.field = field
        super().__init__(f"{resource} with {field}={value} already exists")

class DatabaseError(Exception):
    pass

# repositories/user_repository.py
import psycopg2
from exceptions import NotFoundError, DuplicateError, DatabaseError

class UserRepository:
    def get_by_id(self, user_id):
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, name, email FROM users WHERE id = %s", (user_id,))
                row = cursor.fetchone()
        except psycopg2.OperationalError as e:
            raise DatabaseError(f"Failed to query users: {e}")

        if row is None:
            raise NotFoundError("User", user_id)
        return {"id": row[0], "name": row[1], "email": row[2]}

    def create(self, name, email):
        try:
            with get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO users (name, email) VALUES (%s, %s) RETURNING id",
                    (name, email)
                )
                new_id = cursor.fetchone()[0]
                return {"id": new_id, "name": name, "email": email}
        except psycopg2.IntegrityError:
            raise DuplicateError("User", "email", email)
        except psycopg2.OperationalError as e:
            raise DatabaseError(f"Failed to create user: {e}")

# app.py -- global error handlers
@app.errorhandler(NotFoundError)
def handle_not_found(e):
    return jsonify({"error": str(e)}), 404

@app.errorhandler(DuplicateError)
def handle_duplicate(e):
    return jsonify({"error": str(e)}), 409

@app.errorhandler(DatabaseError)
def handle_db_error(e):
    app.logger.error(f"Database error: {e}")
    return jsonify({"error": "Service temporarily unavailable"}), 503

# Routes stay clean -- no try/except needed
@app.route('/users/<int:user_id>')
def get_user(user_id):
    user = user_repo.get_by_id(user_id)
    return jsonify(user)
```

The repository translates psycopg2 exceptions into domain exceptions. The global error handlers translate domain exceptions into HTTP responses. The routes themselves have zero error handling code.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I have a UserRepository with error handling that raises domain exceptions. Global Flask error handlers convert those to HTTP responses. Routes are clean.
Assistant: Good layered architecture. Repository handles DB + domain errors, Flask handles HTTP translation.

User: Now I want to write unit tests for the routes, but they always hit the real database because UserRepository calls get_connection() internally.

[Current message]
User: How do I make this testable without needing a real database for route tests?''',
        "output": r'''The issue is that the repository is created as a module-level global, so routes are tightly coupled to it. Use dependency injection to make the repository swappable:

```python
# repositories/user_repository.py -- add a base class
from abc import ABC, abstractmethod

class UserRepositoryBase(ABC):
    @abstractmethod
    def get_by_id(self, user_id):
        pass

    @abstractmethod
    def create(self, name, email):
        pass

    @abstractmethod
    def list_all(self, limit=50, offset=0):
        pass

class UserRepository(UserRepositoryBase):
    # ... your existing implementation with get_connection() ...
    pass

# app.py -- inject the repository
def create_app(user_repo=None):
    app = Flask(__name__)
    if user_repo is None:
        user_repo = UserRepository()  # default to real DB

    @app.route('/users/<int:user_id>')
    def get_user(user_id):
        user = user_repo.get_by_id(user_id)
        return jsonify(user)

    @app.route('/users', methods=['POST'])
    def create_user():
        data = request.json
        user = user_repo.create(data['name'], data['email'])
        return jsonify(user), 201

    # ... register error handlers ...
    return app

# tests/test_user_routes.py
from unittest.mock import MagicMock
from exceptions import NotFoundError

def test_get_user_returns_user():
    mock_repo = MagicMock(spec=UserRepositoryBase)
    mock_repo.get_by_id.return_value = {"id": 1, "name": "Alice", "email": "alice@test.com"}

    app = create_app(user_repo=mock_repo)
    client = app.test_client()

    response = client.get('/users/1')
    assert response.status_code == 200
    assert response.json['name'] == 'Alice'
    mock_repo.get_by_id.assert_called_once_with(1)

def test_get_user_not_found():
    mock_repo = MagicMock(spec=UserRepositoryBase)
    mock_repo.get_by_id.side_effect = NotFoundError("User", 999)

    app = create_app(user_repo=mock_repo)
    client = app.test_client()

    response = client.get('/users/999')
    assert response.status_code == 404
```

The factory function create_app() accepts an optional repository. In production, it uses the real one. In tests, you pass a mock. The tests verify route behavior without touching a database.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I have this Node.js code with deeply nested callbacks. It works but it is really hard to read and modify:

```javascript
function processOrder(orderId, callback) {
    db.getOrder(orderId, (err, order) => {
        if (err) return callback(err);
        db.getUser(order.userId, (err, user) => {
            if (err) return callback(err);
            db.getInventory(order.productId, (err, inventory) => {
                if (err) return callback(err);
                if (inventory.count < order.quantity) {
                    return callback(new Error('Out of stock'));
                }
                db.updateInventory(order.productId, inventory.count - order.quantity, (err) => {
                    if (err) return callback(err);
                    emailService.sendConfirmation(user.email, order, (err) => {
                        if (err) return callback(err);
                        callback(null, { order, user, status: 'confirmed' });
                    });
                });
            });
        });
    });
}
```

[Current message]
User: How would I refactor this to use async/await? And should I also break it into smaller functions?''',
        "output": r'''Yes, both -- convert to async/await and extract logical steps. First wrap callback APIs if needed:

```javascript
const { promisify } = require('util');

// Wrap callback-based functions
const dbGetOrder = promisify(db.getOrder.bind(db));
const dbGetUser = promisify(db.getUser.bind(db));
const dbGetInventory = promisify(db.getInventory.bind(db));
const dbUpdateInventory = promisify(db.updateInventory.bind(db));
const sendConfirmation = promisify(emailService.sendConfirmation.bind(emailService));

// Main function -- flat and readable
async function processOrder(orderId) {
    const order = await dbGetOrder(orderId);
    const user = await dbGetUser(order.userId);

    await validateInventory(order);
    await reserveInventory(order);
    await notifyUser(user, order);

    return { order, user, status: 'confirmed' };
}

// Extracted helpers with single responsibilities
async function validateInventory(order) {
    const inventory = await dbGetInventory(order.productId);
    if (inventory.count < order.quantity) {
        throw new Error(
            'Out of stock: product ' + order.productId +
            ' has ' + inventory.count + ' but need ' + order.quantity
        );
    }
    return inventory;
}

async function reserveInventory(order) {
    const inventory = await dbGetInventory(order.productId);
    await dbUpdateInventory(order.productId, inventory.count - order.quantity);
}

async function notifyUser(user, order) {
    try {
        await sendConfirmation(user.email, order);
    } catch (err) {
        // Email failure should not fail the whole order
        console.error('Failed to send confirmation email:', err.message);
    }
}
```

Key improvements: (1) No nesting -- each step is at the same indentation level. (2) Error handling is natural with try/catch instead of checking err on every callback. (3) Helper functions have clear names. (4) Email notification has its own error handling -- a failed email should not roll back the inventory update.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I am reviewing our Python codebase and there are hardcoded values everywhere:

```python
class NotificationService:
    def __init__(self):
        self.smtp_host = "smtp.gmail.com"
        self.smtp_port = 587
        self.max_retries = 3
        self.timeout = 30
        self.from_email = "noreply@myapp.com"
        self.batch_size = 100
        self.rate_limit = 50  # per minute
```

The same values (3 retries, 30 second timeout) are repeated as literals in the send method too.
Assistant: Those should be extracted to configuration. Use environment variables with sensible defaults, or a config file.

[Current message]
User: Can you show me how to refactor this properly? I want it to be configurable but also have good defaults, and I do not want to have to pass 10 environment variables in development.''',
        "output": r'''Use a configuration class with defaults that can be overridden by environment variables:

```python
import os
from dataclasses import dataclass

@dataclass
class NotificationConfig:
    # SMTP settings
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    from_email: str = "noreply@myapp.com"

    # Retry/timeout settings
    max_retries: int = 3
    timeout_seconds: int = 30

    # Rate limiting
    batch_size: int = 100
    rate_limit_per_minute: int = 50

    @classmethod
    def from_env(cls):
        """Load config from environment variables with fallback to defaults."""
        kwargs = {}
        env_map = {
            'SMTP_HOST': ('smtp_host', str),
            'SMTP_PORT': ('smtp_port', int),
            'FROM_EMAIL': ('from_email', str),
            'NOTIFY_MAX_RETRIES': ('max_retries', int),
            'NOTIFY_TIMEOUT': ('timeout_seconds', int),
            'NOTIFY_BATCH_SIZE': ('batch_size', int),
            'NOTIFY_RATE_LIMIT': ('rate_limit_per_minute', int),
        }
        for env_var, (field_name, type_fn) in env_map.items():
            value = os.environ.get(env_var)
            if value is not None:
                kwargs[field_name] = type_fn(value)
        return cls(**kwargs)


class NotificationService:
    def __init__(self, config=None):
        self.config = config or NotificationConfig.from_env()

    def send(self, to, subject, body):
        for attempt in range(self.config.max_retries):
            try:
                connection = self._connect(
                    self.config.smtp_host,
                    self.config.smtp_port,
                    timeout=self.config.timeout_seconds,
                )
                connection.send_message(
                    from_addr=self.config.from_email,
                    to_addr=to,
                    subject=subject,
                    body=body,
                )
                return
            except TimeoutError:
                if attempt == self.config.max_retries - 1:
                    raise

# Development -- just use defaults
service = NotificationService()

# Production -- set env vars: SMTP_HOST=smtp.sendgrid.net

# Testing -- pass explicit config
test_config = NotificationConfig(smtp_host="localhost", smtp_port=1025, max_retries=1)
test_service = NotificationService(config=test_config)
```

The dataclass gives you: (1) all settings in one place with documented defaults, (2) environment variable overrides for production, (3) explicit config injection for tests, (4) no magic numbers in business logic.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I have a payment processing function that handles different payment methods. Every time we add a new payment method I have to modify this function and it is 150 lines long with if/elif chains:

```python
def process_payment(method, amount, details):
    if method == "credit_card":
        if not validate_card(details["card_number"]):
            raise ValueError("Invalid card")
        result = stripe_charge(details["card_number"], amount)
        log_payment("credit_card", amount, result)
        return result
    elif method == "paypal":
        token = paypal_get_token(details["email"])
        result = paypal_charge(token, amount)
        log_payment("paypal", amount, result)
        return result
    elif method == "bank_transfer":
        # ... more code ...
        pass
    else:
        raise ValueError("Unknown payment method: " + method)
```
Assistant: This is a classic case for the Strategy pattern. Extract each payment method into its own class with a common interface.

[Current message]
User: Show me how to refactor this. I want to be able to add new payment methods without touching the core processing logic.''',
        "output": r'''Here is the Strategy pattern applied to your payment processing:

```python
from abc import ABC, abstractmethod
from typing import Dict, Any

class PaymentProcessor(ABC):
    @abstractmethod
    def validate(self, details: Dict[str, Any]) -> None:
        pass

    @abstractmethod
    def charge(self, amount: float, details: Dict[str, Any]) -> Dict[str, Any]:
        pass

class CreditCardProcessor(PaymentProcessor):
    def validate(self, details):
        if not validate_card(details.get("card_number", "")):
            raise ValueError("Invalid card number")

    def charge(self, amount, details):
        return stripe_charge(details["card_number"], amount)

class PayPalProcessor(PaymentProcessor):
    def validate(self, details):
        if "email" not in details:
            raise ValueError("PayPal email required")

    def charge(self, amount, details):
        token = paypal_get_token(details["email"])
        return paypal_charge(token, amount)

class BankTransferProcessor(PaymentProcessor):
    def validate(self, details):
        validate_routing(details.get("routing_number", ""))
        if "account_number" not in details:
            raise ValueError("Account number required")

    def charge(self, amount, details):
        return initiate_transfer(details["account_number"], amount)

# Registry -- maps method names to processor classes
PAYMENT_PROCESSORS = {
    "credit_card": CreditCardProcessor,
    "paypal": PayPalProcessor,
    "bank_transfer": BankTransferProcessor,
}

def register_processor(method_name, processor_class):
    PAYMENT_PROCESSORS[method_name] = processor_class

def process_payment(method, amount, details):
    """Core logic -- never needs to change for new methods."""
    processor_class = PAYMENT_PROCESSORS.get(method)
    if processor_class is None:
        raise ValueError("Unknown payment method: " + method)

    processor = processor_class()
    processor.validate(details)
    result = processor.charge(amount, details)
    log_payment(method, amount, result)
    return result
```

To add crypto payments, just create a class and register it:

```python
class CryptoProcessor(PaymentProcessor):
    def validate(self, details):
        if "wallet_address" not in details:
            raise ValueError("Wallet address required")

    def charge(self, amount, details):
        return crypto_transfer(details["wallet_address"], amount)

register_processor("crypto", CryptoProcessor)
```

The process_payment function is now 8 lines and will never need to grow. Each processor is independently testable. Open for extension, closed for modification.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I have a React component that is 400 lines long. It handles a user profile page with editing, avatar upload, password change, and notification preferences all in one component.

[Current message]
User: Here is a simplified version. Can you show me how to extract it into smaller pieces?

```javascript
function UserProfile() {
    const [user, setUser] = useState(null);
    const [isEditing, setIsEditing] = useState(false);
    const [name, setName] = useState('');
    const [email, setEmail] = useState('');
    const [avatar, setAvatar] = useState(null);
    const [currentPassword, setCurrentPassword] = useState('');
    const [newPassword, setNewPassword] = useState('');
    const [emailNotifs, setEmailNotifs] = useState(true);
    const [pushNotifs, setPushNotifs] = useState(false);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => { fetchUser(); }, []);

    const fetchUser = async () => { /* fetch and set all state */ };
    const handleSaveProfile = async () => { /* save name/email */ };
    const handleAvatarUpload = async (file) => { /* upload avatar */ };
    const handlePasswordChange = async () => { /* change password */ };
    const handleNotifUpdate = async (type, value) => { /* update prefs */ };

    return (
        <div>
            {/* profile section - 50 lines */}
            {/* avatar section - 30 lines */}
            {/* password section - 40 lines */}
            {/* notification prefs - 35 lines */}
        </div>
    );
}
```''',
        "output": r'''Break it into a container component plus focused sub-components. Extract shared logic into a custom hook:

```javascript
// hooks/useUser.js -- custom hook for user data
function useUser() {
    const [user, setUser] = useState(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        async function load() {
            try {
                const res = await fetch('/api/user/me');
                const data = await res.json();
                setUser(data);
            } catch (err) {
                setError(err.message);
            } finally {
                setLoading(false);
            }
        }
        load();
    }, []);

    const updateUser = (updates) => {
        setUser(prev => ({ ...prev, ...updates }));
    };

    return { user, loading, error, updateUser };
}

// components/ProfileForm.js
function ProfileForm({ user, onSave }) {
    const [name, setName] = useState(user.name);
    const [email, setEmail] = useState(user.email);
    const [saving, setSaving] = useState(false);

    const handleSubmit = async (e) => {
        e.preventDefault();
        setSaving(true);
        await fetch('/api/user/me', {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, email }),
        });
        onSave({ name, email });
        setSaving(false);
    };

    return (
        <form onSubmit={handleSubmit}>
            <input value={name} onChange={e => setName(e.target.value)} />
            <input value={email} onChange={e => setEmail(e.target.value)} />
            <button disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
        </form>
    );
}

// components/AvatarUpload.js
function AvatarUpload({ currentAvatar, onUpload }) {
    const handleFile = async (e) => {
        const file = e.target.files[0];
        if (!file) return;
        const form = new FormData();
        form.append('avatar', file);
        const res = await fetch('/api/user/avatar', { method: 'POST', body: form });
        const data = await res.json();
        onUpload(data.avatarUrl);
    };

    return (
        <div>
            <img src={currentAvatar} alt="Avatar" />
            <input type="file" accept="image/*" onChange={handleFile} />
        </div>
    );
}

// components/UserProfile.js -- container, now ~30 lines
function UserProfile() {
    const { user, loading, error, updateUser } = useUser();

    if (loading) return <div>Loading...</div>;
    if (error) return <div>Error: {error}</div>;

    return (
        <div>
            <ProfileForm user={user} onSave={updateUser} />
            <AvatarUpload currentAvatar={user.avatar} onUpload={url => updateUser({ avatar: url })} />
            <PasswordChange />
            <NotificationPrefs userId={user.id} />
        </div>
    );
}
```

Each sub-component manages its own local state. The container coordinates data flow through props and callbacks. The useUser hook is reusable anywhere you need user data.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My Python codebase has string comparisons everywhere for status values like order.status == "pending". Someone typo'd "pening" and it caused a bug.
Assistant: Use an Enum to define the valid statuses. You get autocomplete, typo detection, and a single source of truth.

[Current message]
User: Show me how to convert the string statuses to an Enum and how to update the code that uses them. Also, we store these in a PostgreSQL database so the Enum needs to work with SQLAlchemy.''',
        "output": r'''Here is how to define the Enum and integrate it with SQLAlchemy:

```python
import enum
from sqlalchemy import Column, Integer, Enum as SAEnum
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class OrderStatus(enum.Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

    @classmethod
    def from_string(cls, value):
        try:
            return cls(value)
        except ValueError:
            valid = [s.value for s in cls]
            raise ValueError(f"Invalid status: '{value}'. Must be one of: {valid}")

class Order(Base):
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True)
    status = Column(SAEnum(OrderStatus), default=OrderStatus.PENDING, nullable=False)

    def can_cancel(self):
        return self.status in (OrderStatus.PENDING, OrderStatus.PROCESSING)

    def transition_to(self, new_status):
        """Enforce valid state transitions."""
        valid_transitions = {
            OrderStatus.PENDING: [OrderStatus.PROCESSING, OrderStatus.CANCELLED],
            OrderStatus.PROCESSING: [OrderStatus.SHIPPED, OrderStatus.CANCELLED],
            OrderStatus.SHIPPED: [OrderStatus.DELIVERED],
            OrderStatus.DELIVERED: [],
            OrderStatus.CANCELLED: [],
        }
        allowed = valid_transitions.get(self.status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition from {self.status.value} to {new_status.value}. "
                f"Allowed: {[s.value for s in allowed]}"
            )
        self.status = new_status

# Usage -- before (fragile): if order.status == "pending":
# Usage -- after (safe):
if order.status == OrderStatus.PENDING:
    order.transition_to(OrderStatus.PROCESSING)

# API layer -- convert strings from request body
@app.route('/orders/<int:order_id>/status', methods=['PATCH'])
def update_order_status(order_id):
    data = request.json
    new_status = OrderStatus.from_string(data['status'])
    order = Order.query.get_or_404(order_id)
    order.transition_to(new_status)
    db.session.commit()
    return jsonify({"status": order.status.value})
```

Benefits: (1) typos like OrderStatus.PENING cause AttributeError immediately, (2) transition_to enforces valid state transitions, (3) SQLAlchemy stores the string value so existing data works, (4) from_string gives clear errors for invalid API input.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My FastAPI endpoint calls three external APIs sequentially and it takes 3 seconds total because each one takes about 1 second:

```python
@app.get("/dashboard/{user_id}")
async def get_dashboard(user_id: int):
    profile = requests.get(f"http://user-service/users/{user_id}").json()
    orders = requests.get(f"http://order-service/users/{user_id}/orders").json()
    recommendations = requests.get(f"http://rec-service/users/{user_id}/recs").json()

    return {
        "profile": profile,
        "recent_orders": orders[:5],
        "recommendations": recommendations[:10],
    }
```
Assistant: You are using the synchronous requests library in an async endpoint. That blocks the event loop. Switch to httpx with async support and use asyncio.gather to make the calls concurrently.

[Current message]
User: Show me the refactored version. Also, what happens if one of the services is down? I do not want the whole dashboard to fail just because recommendations are unavailable.''',
        "output": r'''Here is the async version with concurrent calls and graceful degradation:

```python
import httpx
import asyncio
import logging

# Reuse a single async client (connection pooling)
http_client = httpx.AsyncClient(timeout=5.0)

async def fetch_service(url, fallback=None, critical=True):
    """Fetch from a service with optional fallback on failure."""
    try:
        response = await http_client.get(url)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, httpx.TimeoutException) as e:
        if critical:
            raise HTTPException(503, f"Required service unavailable: {e}")
        logging.warning(f"Non-critical service failed: {url} -- {e}")
        return fallback

@app.get("/dashboard/{user_id}")
async def get_dashboard(user_id: int):
    # Fire all three requests concurrently
    profile, orders, recommendations = await asyncio.gather(
        fetch_service(
            f"http://user-service/users/{user_id}",
            critical=True,  # Dashboard cannot load without profile
        ),
        fetch_service(
            f"http://order-service/users/{user_id}/orders",
            critical=True,
        ),
        fetch_service(
            f"http://rec-service/users/{user_id}/recs",
            critical=False,  # Nice-to-have
            fallback=[],
        ),
    )

    return {
        "profile": profile,
        "recent_orders": orders[:5],
        "recommendations": recommendations[:10],
    }

@app.on_event("shutdown")
async def shutdown():
    await http_client.aclose()
```

Key changes: (1) httpx.AsyncClient instead of requests -- does not block the event loop, (2) asyncio.gather runs all three concurrently, so total time is ~1 second instead of 3, (3) fetch_service handles errors with critical/non-critical distinction -- recommendations failing returns empty list, but profile failing returns 503, (4) 5-second timeout prevents one slow service from hanging everything. The AsyncClient is created once for connection pooling.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I have a function that determines if a user can access a resource. The logic has gotten really complicated with nested if/elif:

```python
def can_access(user, resource):
    if user.role == "admin":
        return True
    if resource.is_public:
        return True
    if user.role == "moderator" and resource.type in ("post", "comment"):
        return True
    if resource.owner_id == user.id:
        return True
    if resource.type == "admin_settings":
        return False
    if user.organization_id and user.organization_id == resource.organization_id:
        if resource.org_visibility in ("members", "all"):
            return True
    return False
```

Some conditions contradict each other and it is hard to reason about.

[Current message]
User: How do I refactor this so the access logic is clear and maintainable?''',
        "output": r'''Refactor into a chain of clearly named rule functions. Each rule returns True (allow), False (deny), or None (no opinion):

```python
# Each rule is a simple function that returns True, False, or None
def admin_access(user, resource):
    """Admins can access everything."""
    if user.role == "admin":
        return True
    return None

def public_access(user, resource):
    """Anyone can access public resources."""
    if resource.is_public:
        return True
    return None

def admin_settings_restriction(user, resource):
    """Only admins can access admin settings."""
    if resource.type == "admin_settings":
        return False
    return None

def owner_access(user, resource):
    """Owners can always access their own resources."""
    if resource.owner_id == user.id:
        return True
    return None

def moderator_access(user, resource):
    """Moderators can access posts and comments."""
    if user.role == "moderator" and resource.type in ("post", "comment"):
        return True
    return None

def organization_access(user, resource):
    """Org members can access org resources with appropriate visibility."""
    if not user.organization_id:
        return None
    if user.organization_id != resource.organization_id:
        return None
    if resource.org_visibility in ("members", "all"):
        return True
    return None

# Rule chain -- order matters, first definitive answer wins
ACCESS_RULES = [
    admin_access,
    public_access,
    admin_settings_restriction,
    owner_access,
    moderator_access,
    organization_access,
]

def can_access(user, resource):
    for rule in ACCESS_RULES:
        result = rule(user, resource)
        if result is not None:
            return result
    return False  # Default deny
```

Each rule is independently testable and has a docstring explaining its purpose. The three-valued return lets rules either make a decision or defer to the next rule. Adding a new access rule means writing one function and inserting it at the right position -- no need to understand the other rules. You can also log which rule made the decision for debugging access issues.'''
    },
]
