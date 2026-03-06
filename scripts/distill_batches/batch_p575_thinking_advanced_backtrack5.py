"""Phase 2A: Advanced Reasoning — Backtracking & Dead-End Recovery (Part 5/5)
Try wrong approach first, hit the wall, recover with better solution:
global state to dependency injection, polling to webhooks, manual deploy to CI/CD,
string parsing to AST, flat config to hierarchical."""

PAIRS = [
    (
        "thinking/backtrack-global-state-to-di",
        "I have a Flask app where database connections and config are accessed via global variables. It works but tests are failing randomly when run in parallel. What's wrong?",
        r'''<think>
Let me start with the obvious approach and see where it fails.

First attempt: just add locks around the global state.

```python
# Current code (global state):
db = None
config = None

def init_app():
    global db, config
    config = load_config()
    db = connect_database(config.DB_URL)

def get_users():
    return db.execute("SELECT * FROM users")
```

The problem with parallel tests:
- Test A calls init_app() with test config (test DB)
- Test B calls init_app() with different test config
- Test A's db variable gets overwritten by Test B's init_app()
- Test A now queries Test B's database → wrong results or crashes

My first instinct: add a threading lock.

```python
import threading
lock = threading.Lock()

def get_users():
    with lock:
        return db.execute("SELECT * FROM users")
```

Wait... this doesn't actually solve the problem. The issue isn't concurrent ACCESS to db — it's concurrent ASSIGNMENT. Test B overwrites the global db while Test A is using it. A lock on get_users() doesn't prevent Test B from calling init_app() and changing db.

Could I lock init_app() too? Even if I do, the tests would serialize (run one at a time) — defeating the purpose of parallel testing.

Let me backtrack. The real problem isn't thread safety — it's SHARED MUTABLE STATE. The global variables are shared by all tests, and any test can change them.

The fix isn't locks — it's eliminating global state entirely.

Second attempt: Flask's application context / g object.

```python
from flask import g

def get_db():
    if 'db' not in g:
        g.db = connect_database(current_app.config['DB_URL'])
    return g.db
```

This is better — g is request-scoped, not global. But it still relies on Flask's app context, which is essentially a thread-local global. Tests need to create an app context for every test.

Third attempt: Dependency injection.

Instead of functions reaching out to get their dependencies (global or app context), dependencies are PASSED IN.

```python
def get_users(db):  # db is passed in, not looked up
    return db.execute("SELECT * FROM users")
```

Now each test can pass its own db:
- Test A: get_users(test_db_a) — uses its own database
- Test B: get_users(test_db_b) — uses its own database
- No shared state, no race condition, tests run in parallel safely

This is the correct solution. Global state was a dead end for testability.
</think>

Your global state approach hit a fundamental wall: **shared mutable state can't work with parallel tests**. Let me show why my first fix attempt also failed, then the real solution.

**First attempt (wrong): Add locks**

```python
# This does NOT solve the problem
import threading
lock = threading.Lock()

db = None  # Still global!

def get_users():
    with lock:
        return db.execute("SELECT * FROM users")

# Why it fails:
# Test A: init_app(test_config_a) → sets global db = db_a
# Test B: init_app(test_config_b) → sets global db = db_b  ← overwrites!
# Test A: get_users() → uses db_b (WRONG DATABASE)
# Locks serialize access but don't prevent the overwrite
```

**Why I had to backtrack:** The problem isn't concurrent access — it's shared state itself. No amount of locking fixes "two tests need different configurations simultaneously."

**The real fix — dependency injection:**

```python
# BEFORE: Functions reach out for dependencies (global state)
db = connect_database(DB_URL)  # Global!

def get_users():
    return db.execute("SELECT * FROM users")  # Uses global db

def get_orders(user_id):
    return db.execute("SELECT * FROM orders WHERE user_id = %s", (user_id,))

# AFTER: Dependencies are passed in
class UserRepository:
    def __init__(self, db):
        self.db = db  # Injected, not global

    def get_users(self):
        return self.db.execute("SELECT * FROM users")

class OrderRepository:
    def __init__(self, db):
        self.db = db

    def get_orders(self, user_id):
        return self.db.execute(
            "SELECT * FROM orders WHERE user_id = %s", (user_id,)
        )
```

**Flask app with DI:**

```python
# app.py
from flask import Flask

def create_app(config=None):
    """Application factory — creates a fresh app with its own dependencies."""
    app = Flask(__name__)

    if config:
        app.config.update(config)
    else:
        app.config.from_object("config.ProductionConfig")

    # Initialize dependencies for THIS app instance
    db = connect_database(app.config["DB_URL"])
    user_repo = UserRepository(db)
    order_repo = OrderRepository(db)

    @app.route("/users")
    def list_users():
        return jsonify(user_repo.get_users())

    @app.route("/users/<int:user_id>/orders")
    def list_orders(user_id):
        return jsonify(order_repo.get_orders(user_id))

    @app.teardown_appcontext
    def close_db(exception):
        db.close()

    return app
```

**Tests now work in parallel — each gets its own everything:**

```python
import pytest

@pytest.fixture
def app():
    """Each test gets its own app with its own database."""
    app = create_app({
        "DB_URL": "sqlite:///:memory:",
        "TESTING": True,
    })
    with app.app_context():
        init_test_db()
        yield app

@pytest.fixture
def client(app):
    return app.test_client()

def test_get_users(client):
    # Uses its own in-memory DB — no interference from other tests
    response = client.get("/users")
    assert response.status_code == 200

def test_get_orders(client):
    # Also its own DB — runs in parallel safely
    response = client.get("/users/1/orders")
    assert response.status_code == 200

# Both tests can run simultaneously: different app instances, different DBs
```

**The pattern: dependency injection eliminates shared mutable state.**

```
Global state:           All code shares ONE db → untestable in parallel
Thread-local state:     Each thread gets own db → better, but complex
Dependency injection:   Each caller provides own db → fully independent
```

If you're using Flask, the `create_app()` application factory pattern is the standard way to do this. It's in Flask's official documentation for exactly this reason.'''
    ),
    (
        "thinking/backtrack-polling-to-webhooks",
        "I'm checking if a payment has completed by polling the Stripe API every 5 seconds. It works but my API is slow because the user waits up to 5 seconds for confirmation. How do I make it faster?",
        r'''<think>
Let me trace through their current approach and see why it's problematic.

Current approach: polling
```
User → [Your API] → "Is payment done?" → Stripe → "No"
                     (wait 5 seconds)
                   → "Is payment done?" → Stripe → "No"
                     (wait 5 seconds)
                   → "Is payment done?" → Stripe → "Yes!"
                   → return to user
```

Worst case: user waits 5 seconds for nothing (payment completed 1ms after last poll).
Average wait: 2.5 seconds even after payment completes.

My first instinct: poll more frequently! Every 500ms instead of 5 seconds.

```python
# More frequent polling
for _ in range(60):  # 30 seconds max
    payment = stripe.PaymentIntent.retrieve(payment_id)
    if payment.status == "succeeded":
        return {"status": "paid"}
    time.sleep(0.5)
```

Wait, this creates new problems:
1. 60 API calls to Stripe per checkout → rate limited
2. If 100 concurrent checkouts → 6000 Stripe API calls in 30 seconds → definitely rate limited
3. Still has 250ms average delay (half of 500ms poll interval)
4. Server thread is blocked for up to 30 seconds per request

Even with async, I'm still hammering Stripe's API unnecessarily.

Let me backtrack further. The fundamental problem: polling is the WRONG pattern when the source can notify you.

Stripe supports webhooks — Stripe calls YOUR API when the payment completes. This inverts the control:

Instead of: "Hey Stripe, is it done yet? Is it done yet? Is it done yet?"
It becomes: Stripe → "It's done!" → You handle it

But wait, there's a UX problem: the user is sitting on a checkout page waiting for confirmation. If the webhook goes to your backend asynchronously, how does the frontend know?

Options:
A. Frontend polls YOUR server (not Stripe): cheaper, faster
B. WebSocket: backend pushes to frontend when webhook arrives
C. Server-Sent Events: simpler than WebSocket for one-way push

The optimal architecture:
1. Create PaymentIntent, return to frontend
2. Frontend uses Stripe.js (which handles its own confirmation flow)
3. Backend receives webhook from Stripe (async, reliable)
4. Frontend polls YOUR backend (fast local endpoint, not Stripe's API)
   OR uses WebSocket for instant notification

Actually, the simplest fix: Stripe.js handles the payment confirmation on the CLIENT side. The frontend gets the result directly from Stripe, then tells your backend. The webhook is the backup to ensure you always get the result.

This eliminates all server-side polling.
</think>

Polling Stripe was a dead end — even faster polling just hammers their API. The solution inverts the architecture.

**Why faster polling doesn't work:**

```python
# First attempt: poll every 500ms instead of 5s
for _ in range(60):
    payment = stripe.PaymentIntent.retrieve(payment_id)  # API call!
    if payment.status == "succeeded":
        return {"status": "paid"}
    time.sleep(0.5)

# Problems:
# 100 concurrent checkouts × 60 polls each = 6000 API calls in 30s
# Stripe rate limit: 100 req/s → you're rate limited
# Each request thread is blocked for up to 30 seconds
# You're using server resources to wait
```

**The real solution: let Stripe tell you (webhooks + client-side confirmation)**

```python
# Step 1: Create PaymentIntent, return immediately
@app.post("/checkout")
async def create_checkout(order: OrderRequest):
    intent = stripe.PaymentIntent.create(
        amount=int(order.total * 100),
        currency="usd",
    )

    order = await create_order(order, payment_intent_id=intent.id)

    return {
        "order_id": order.id,
        "client_secret": intent.client_secret,  # Frontend uses this
    }
    # Response time: ~200ms. No waiting for payment.
```

```javascript
// Step 2: Frontend confirms payment with Stripe.js (NO server polling)
const { error, paymentIntent } = await stripe.confirmCardPayment(
    clientSecret,
    { payment_method: { card: cardElement } }
);

if (paymentIntent.status === 'succeeded') {
    // Payment confirmed! Tell our backend.
    await fetch(`/orders/${orderId}/confirm`, { method: 'POST' });
    showSuccess("Payment complete!");
} else if (error) {
    showError(error.message);
}
// User gets INSTANT feedback — no polling, no waiting
```

```python
# Step 3: Webhook as the reliable backend confirmation
@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    event = stripe.Webhook.construct_event(
        payload, sig_header, STRIPE_WEBHOOK_SECRET
    )

    if event.type == "payment_intent.succeeded":
        intent = event.data.object
        order = await get_order_by_payment_intent(intent.id)
        order.status = "paid"
        order.paid_at = datetime.utcnow()
        await db.commit()

        # Send confirmation email (background task)
        await send_confirmation_email(order.id)

    return {"received": True}
```

**Why this is better:**

```
BEFORE (polling):
User → Server → Stripe → "not yet" (×10) → "yes!" → User
Total time: 0-5 seconds of waiting, 10 API calls

AFTER (webhooks + client-side):
User → Stripe.js → Stripe (direct) → User "success!"    (instant)
       Stripe → Your webhook → DB updated                (async, reliable)
Total time: ~1 second, 0 polling API calls
```

**For cases where you DO need server-side status (no frontend):**

```python
# If you must know payment status server-side (e.g., API-only checkout):
# Use webhooks + short client polling of YOUR server

@app.get("/orders/{order_id}/status")
async def check_order_status(order_id: int):
    """Frontend polls THIS (fast, local) instead of Stripe (slow, rate-limited)."""
    order = await get_order(order_id)
    return {"status": order.status}
    # Response: < 5ms (local DB query)

# Frontend:
# Poll /orders/123/status every 1 second (your own fast endpoint)
# Stop when status == "paid"
# Webhook updates the order status in your DB asynchronously
```

The key insight: **never poll an external API when it supports webhooks**. Let the source notify you, and use your own fast local endpoints for any client-side polling.'''
    ),
    (
        "thinking/backtrack-string-parsing-to-ast",
        "I'm trying to evaluate user-provided mathematical expressions like '2 + 3 * (4 - 1)'. I started with regex and string splitting but it's getting really complex. What should I do?",
        r'''<think>
Let me trace through the regex/string approach and see where it breaks down.

First attempt: split by operators and evaluate left-to-right.

```python
def evaluate(expr):
    # Split "2 + 3 * 4" → ["2", "+", "3", "*", "4"]
    tokens = expr.split()
    result = int(tokens[0])
    i = 1
    while i < len(tokens):
        op = tokens[i]
        num = int(tokens[i+1])
        if op == '+': result += num
        elif op == '-': result -= num
        elif op == '*': result *= num
        elif op == '/': result /= num
        i += 2
    return result
```

Problem 1: Operator precedence.
- "2 + 3 * 4" should be 2 + (3*4) = 14
- But left-to-right gives (2+3) * 4 = 20
- WRONG!

Second attempt: handle precedence by doing multiplication/division first.

```python
def evaluate(expr):
    # First pass: handle * and /
    # Second pass: handle + and -
    # This is getting complex...
```

Problem 2: Parentheses.
- "2 * (3 + 4)" — need to evaluate inner expression first
- Can't just do two passes — need to handle nested parens
- "(2 + (3 * (4 - 1)))" — arbitrarily deep nesting

Third attempt: use regex to find innermost parentheses and evaluate outward.

```python
import re

def evaluate(expr):
    # Find innermost parens, evaluate, replace, repeat
    while '(' in expr:
        # Match innermost: (stuff-without-parens)
        match = re.search(r'\(([^()]+)\)', expr)
        inner_result = evaluate_simple(match.group(1))
        expr = expr[:match.start()] + str(inner_result) + expr[match.end():]
    return evaluate_simple(expr)
```

This is getting messy and fragile. Edge cases:
- Negative numbers: "-3 + 4" — the minus is part of the number, not an operator
- Decimal numbers: "3.14 * 2"
- Multiple operators: "2 + 3 + 4" (need to chain correctly)
- Spaces: "2+3" vs "2 + 3"
- Invalid input: "2 ++ 3", "2 + ", "abc"

Each edge case adds another regex or special case. This is a dead end — I'm reimplementing a parser poorly with regex.

Let me backtrack completely. This is a PARSING problem. There are well-known algorithms for this:

1. Recursive descent parser — clean, readable, handles precedence naturally
2. Shunting-yard algorithm — converts infix to postfix, then evaluates
3. Python's ast module — built-in, safe expression parsing

For a math expression evaluator, the recursive descent parser is the cleanest approach. Or even simpler: Python's ast.literal_eval won't work (it's for literals, not expressions), but ast.parse + a safe evaluator will.

Actually, the SIMPLEST correct approach: use Python's ast module to parse and safely evaluate.
</think>

Regex for math expressions is a dead end — every fix creates two new edge cases. Let me show you why, then the clean solution.

**Why regex breaks down (my failed attempts):**

```python
# Attempt 1: Split and evaluate left-to-right
"2 + 3 * 4".split() → ["2", "+", "3", "*", "4"]
# Left-to-right: (2+3)*4 = 20
# Correct:       2+(3*4) = 14
# WRONG — doesn't handle precedence

# Attempt 2: Regex for innermost parentheses
import re
re.search(r'\(([^()]+)\)', "(2 + (3 * 4))")
# Finds "3 * 4", evaluates, replaces: "(2 + 12)", evaluate: "14" ✓
# But: What about "-3 + 4"? Is "-" an operator or negative sign?
#      What about "2.5 * 1e3"? Scientific notation?
#      What about "2 + + 3"? Need error handling...
# Each edge case = another regex. This is reimplementing a parser badly.
```

**The clean solution: recursive descent parser**

```python
class MathParser:
    """
    Grammar:
      expression = term (('+' | '-') term)*
      term       = factor (('*' | '/') factor)*
      factor     = NUMBER | '(' expression ')' | '-' factor
    """

    def __init__(self, text: str):
        self.text = text
        self.pos = 0

    def parse(self) -> float:
        result = self.expression()
        if self.pos < len(self.text):
            raise ValueError(f"Unexpected character at position {self.pos}")
        return result

    def expression(self) -> float:
        """Handle + and - (lowest precedence)."""
        result = self.term()
        while self.pos < len(self.text) and self.peek() in ('+', '-'):
            op = self.advance()
            if op == '+':
                result += self.term()
            else:
                result -= self.term()
        return result

    def term(self) -> float:
        """Handle * and / (higher precedence)."""
        result = self.factor()
        while self.pos < len(self.text) and self.peek() in ('*', '/'):
            op = self.advance()
            if op == '*':
                result *= self.factor()
            else:
                divisor = self.factor()
                if divisor == 0:
                    raise ValueError("Division by zero")
                result /= divisor
        return result

    def factor(self) -> float:
        """Handle numbers, parentheses, and unary minus."""
        self.skip_whitespace()

        if self.peek() == '(':
            self.advance()  # consume '('
            result = self.expression()
            if self.peek() != ')':
                raise ValueError("Missing closing parenthesis")
            self.advance()  # consume ')'
            return result

        if self.peek() == '-':
            self.advance()
            return -self.factor()

        return self.number()

    def number(self) -> float:
        self.skip_whitespace()
        start = self.pos
        while self.pos < len(self.text) and (
            self.text[self.pos].isdigit() or self.text[self.pos] == '.'
        ):
            self.pos += 1
        if start == self.pos:
            raise ValueError(f"Expected number at position {self.pos}")
        return float(self.text[start:self.pos])

    def peek(self) -> str:
        self.skip_whitespace()
        if self.pos >= len(self.text):
            return ''
        return self.text[self.pos]

    def advance(self) -> str:
        self.skip_whitespace()
        ch = self.text[self.pos]
        self.pos += 1
        return ch

    def skip_whitespace(self):
        while self.pos < len(self.text) and self.text[self.pos] == ' ':
            self.pos += 1


def evaluate(expression: str) -> float:
    return MathParser(expression).parse()

# All of these work correctly:
evaluate("2 + 3 * 4")           # 14.0 (precedence ✓)
evaluate("(2 + 3) * 4")         # 20.0 (parentheses ✓)
evaluate("2 * (3 + (4 - 1))")   # 12.0 (nested parens ✓)
evaluate("-3 + 4")              # 1.0  (unary minus ✓)
evaluate("3.14 * 2")            # 6.28 (decimals ✓)
```

**Even simpler — use Python's ast module safely:**

```python
import ast
import operator

# Safe math evaluator using Python's own parser
ALLOWED_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.USub: operator.neg,
}

def safe_eval(expression: str) -> float:
    """Evaluate math expression safely — no arbitrary code execution."""
    tree = ast.parse(expression, mode='eval')

    def _eval(node):
        if isinstance(node, ast.Expression):
            return _eval(node.body)
        elif isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        elif isinstance(node, ast.BinOp) and type(node.op) in ALLOWED_OPS:
            left = _eval(node.left)
            right = _eval(node.right)
            return ALLOWED_OPS[type(node.op)](left, right)
        elif isinstance(node, ast.UnaryOp) and type(node.op) in ALLOWED_OPS:
            return ALLOWED_OPS[type(node.op)](_eval(node.operand))
        else:
            raise ValueError(f"Unsupported operation: {ast.dump(node)}")

    return _eval(tree)

# Works perfectly AND is safe (can't execute arbitrary code):
safe_eval("2 + 3 * (4 - 1)")  # 11.0
safe_eval("__import__('os').system('rm -rf /')")  # ValueError!
```

The lesson: when you find yourself writing regex to parse a language (even a simple one), stop and use a parser. Regex is for matching patterns, not for understanding structure.'''
    ),
    (
        "thinking/backtrack-flat-config-to-hierarchical",
        "My application config is getting unwieldy. I have 150+ environment variables like DB_HOST, DB_PORT, DB_USER, DB_PASS, REDIS_HOST, REDIS_PORT, STRIPE_KEY, STRIPE_SECRET, SMTP_HOST, SMTP_PORT, SMTP_USER, etc. How do I manage this?",
        r'''<think>
Let me trace through the approaches and see where each one hits a wall.

First approach: Just keep adding env vars.
```bash
DB_HOST=localhost
DB_PORT=5432
DB_USER=myapp
DB_PASS=secret
DB_NAME=myapp
DB_POOL_SIZE=10
DB_POOL_TIMEOUT=30
DB_SSL_MODE=require
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
REDIS_POOL_SIZE=20
# ... 140 more
```

Problems:
1. No structure — flat list, hard to find related settings
2. Naming conventions drift — is it SMTP_USER or EMAIL_USERNAME?
3. No validation — DB_PORT="hello" is accepted silently
4. No documentation — what does CACHE_TTL_FACTOR do?
5. No way to see which configs a specific service needs
6. Hard to diff between environments (which 50 of 150 vars differ between dev/prod?)

Second approach: Use a .env file per environment.
```
.env.development
.env.staging
.env.production
```

This is slightly better for per-environment management, but doesn't solve:
- No structure or grouping
- No validation
- 150 variables in each file to maintain
- Copy-paste between files → drift

Third approach: Use a config file (YAML/TOML) instead of env vars.

```yaml
# config.yaml
database:
  host: localhost
  port: 5432
  user: myapp
  ...
```

Better structure! But:
- Secrets in a file → can be accidentally committed to git
- 12-Factor App says: config in env vars, not files
- How do you override per-environment? Multiple YAML files?

Let me backtrack and think about what we actually need:

1. Grouping/structure → typed config objects
2. Validation → Pydantic or similar
3. Secrets separate from config → env vars for secrets, file for non-secrets
4. Per-environment overrides → layered config
5. Documentation → types + descriptions in code

The answer: structured config CLASSES that READ FROM env vars (and optionally files). Best of both worlds.

Pydantic Settings gives us exactly this:
- Structure: nested classes
- Validation: type annotations
- Env var support: auto-reads from env
- Documentation: Field descriptions
- Defaults: sensible defaults in code
- Per-environment: .env files + env var overrides
</think>

150 flat env vars is a dead end for maintainability. Let me show you why each incremental fix also fails, then the real solution.

**Why "just organize the .env file" doesn't scale:**

```bash
# Attempt: group with comments
# === Database ===
DB_HOST=localhost
DB_PORT=5432

# === Redis ===
REDIS_HOST=localhost

# Still 150 variables. Still no validation. Still no types.
# DB_PORT=hello → accepted. Bug discovered in production.
```

**Why "switch to YAML" is only half the answer:**

```yaml
# config.yaml — nice structure, but...
database:
  host: localhost
  password: super_secret  # ← COMMITTED TO GIT!
```

**The real solution: structured config classes that read from env vars**

```python
# config.py — ONE file that documents ALL 150 configs
from pydantic_settings import BaseSettings
from pydantic import Field

class DatabaseConfig(BaseSettings):
    host: str = "localhost"
    port: int = Field(default=5432, ge=1, le=65535)
    user: str = "myapp"
    password: str = Field(description="Database password")
    name: str = "myapp"
    pool_size: int = Field(default=10, ge=1, le=100)
    pool_timeout: int = Field(default=30, ge=1)
    ssl_mode: str = Field(default="prefer", pattern=r"^(disable|prefer|require)$")

    model_config = {"env_prefix": "DB_"}
    # Reads: DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, etc.

class RedisConfig(BaseSettings):
    host: str = "localhost"
    port: int = Field(default=6379, ge=1, le=65535)
    password: str = ""
    db: int = Field(default=0, ge=0, le=15)
    pool_size: int = Field(default=20, ge=1)

    model_config = {"env_prefix": "REDIS_"}

class StripeConfig(BaseSettings):
    api_key: str = Field(description="Stripe secret key (sk_...)")
    webhook_secret: str = Field(default="", description="Stripe webhook signing secret")
    publishable_key: str = Field(default="", description="Stripe publishable key (pk_...)")

    model_config = {"env_prefix": "STRIPE_"}

class EmailConfig(BaseSettings):
    smtp_host: str = "localhost"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    from_address: str = "noreply@myapp.com"
    from_name: str = "MyApp"

    model_config = {"env_prefix": "EMAIL_"}

class AppConfig(BaseSettings):
    debug: bool = False
    log_level: str = Field(default="INFO", pattern=r"^(DEBUG|INFO|WARNING|ERROR)$")
    secret_key: str = Field(description="Application secret for session signing")
    allowed_hosts: list[str] = ["localhost"]
    environment: str = Field(default="development", pattern=r"^(development|staging|production)$")

    # Nested configs
    database: DatabaseConfig = DatabaseConfig()
    redis: RedisConfig = RedisConfig()
    stripe: StripeConfig = StripeConfig()
    email: EmailConfig = EmailConfig()

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}

# Singleton — validated at startup
settings = AppConfig()
```

**Usage — clean, typed, discoverable:**

```python
# BEFORE: scattered env var lookups
import os
db_host = os.environ.get("DB_HOST", "localhost")
db_port = int(os.environ.get("DB_PORT", "5432"))  # Crashes on "hello"!
redis_host = os.environ.get("REDIS_HOST", "localhost")

# AFTER: structured access
from config import settings

db_host = settings.database.host       # str, validated
db_port = settings.database.port       # int, guaranteed 1-65535
redis_host = settings.redis.host       # str
stripe_key = settings.stripe.api_key   # str, required (no default)

# IDE autocomplete works! settings.database.<TAB> shows all DB options
```

**Startup validation catches errors immediately:**

```bash
# If DB_PORT=hello in .env:
$ python app.py
pydantic_core._pydantic_core.ValidationError: 1 validation error for AppConfig
database -> port
  Input should be a valid integer [type=int_parsing, input_value='hello']

# If STRIPE_API_KEY is missing:
$ python app.py
pydantic_core._pydantic_core.ValidationError: 1 validation error for AppConfig
stripe -> api_key
  Field required [type=missing]

# App crashes IMMEDIATELY with a clear error — not 3 hours later in production
```

**Environment management:**

```bash
# .env.example (committed to git — documents everything)
# Database
DB_HOST=localhost
DB_PORT=5432
DB_USER=myapp
DB_PASSWORD=change_me
DB_NAME=myapp_dev

# Redis
REDIS_HOST=localhost

# Stripe (get from Stripe dashboard)
STRIPE_API_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...

# .env (NOT committed — developer's local overrides)
DB_PASSWORD=my_local_password
STRIPE_API_KEY=sk_test_my_key

# Production: set env vars in deployment platform
# Only the 10 vars that differ from defaults need to be set
```

**The result: 150 env vars → ~10 env vars per environment**

```
Development: .env with just passwords and API keys (~10 vars)
             Everything else uses sensible defaults from config.py

Staging:     Override DB_HOST, REDIS_HOST, environment-specific URLs (~15 vars)

Production:  Override secrets + hosts + performance tuning (~20 vars)
             130+ vars use validated, documented defaults
```

The key insight: flat env vars are for deployment. Structured config classes are for code. Pydantic bridges both — reads from env vars, provides structure, validation, and documentation.'''
    ),
    (
        "thinking/backtrack-manual-deploy-to-cicd",
        "I set up a deployment script that runs on my laptop and SSHes into production. It works great for me, but now I'm going on vacation and my colleague needs to deploy. We realized only I have the SSH keys and server access. How do we fix this?",
        r'''<think>
Let me trace through the quick fixes and see why they don't work long-term.

First approach: Share my SSH key with my colleague.
- Copy my private key to their laptop
- They can run the same deploy script

Problems:
1. My SSH key is now on two machines — if either is compromised, server is compromised
2. No audit trail — all actions look like "me" in logs
3. When I rotate my key, colleague's access breaks
4. What about the NEXT person who needs to deploy? Share with them too?
5. My key might have sudo access for things colleague shouldn't touch
This is a dead end for any team larger than 1.

Second approach: Create an SSH key per person.
- Generate key for colleague, add their public key to the server
- Each person has their own key

Better! But:
1. Still requires laptop access to deploy — can't deploy from a phone or if laptop breaks
2. Deploy script is on my laptop — colleague needs a copy (and it might have hardcoded paths)
3. No standardization — colleague might modify the script
4. No gates — anyone with the key can deploy anything anytime
5. Still no audit trail beyond SSH logs
6. Onboarding: every new hire needs key setup, server access, script copy

Third approach: Put the deploy script in the repo, give team members keys.
- Script is version-controlled
- Each person has their own SSH key

Still:
1. Deploys happen from random laptops with random environments
2. "It works on my machine" for the deploy script itself
3. No automated testing before deploy
4. Someone could deploy untested code
5. No rollback mechanism beyond "run the script again with the old version"

Let me backtrack completely. The problem isn't "who has the SSH key." The problem is:
- Deployment shouldn't depend on a specific person's machine
- Deployment should be automated, audited, and gated

This is what CI/CD solves: deployment runs in a consistent environment (CI server), triggered by a specific action (merge to main, tag push), with the keys stored securely in the CI system.
</think>

Each "quick fix" for sharing access creates new problems. Let me show you the progression from dead ends to the real solution.

**Dead end 1: Share your SSH key**

```
You: "Here's my private key, copy it to your laptop"

Problems:
- Your key on 2+ machines = 2x attack surface
- All deploys look like "you" in logs (no audit trail)
- Key rotation breaks everyone's access
- Next new hire? Share again?
- THIS IS A SECURITY ANTI-PATTERN
```

**Dead end 2: Per-person SSH keys + script copy**

```
Better, but:
- Deploy still runs from random laptops
- "Works on my machine" applies to deploy scripts too
- No gates: anyone can deploy untested code at 3am
- Onboarding each new hire: generate key, add to server, copy script
```

**The real solution: CI/CD — deployments run in the cloud, not on laptops**

```yaml
# .github/workflows/deploy.yml
# Deploy runs on GitHub's servers, not your laptop
# SSH key is stored as a GitHub Secret — no one copies it

name: Deploy
on:
  push:
    tags: ['v*']  # Deploy when you push a version tag

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pip install -r requirements.txt
      - run: pytest tests/  # Tests MUST pass before deploy

  deploy:
    needs: test  # Only deploy if tests pass
    runs-on: ubuntu-latest
    environment: production  # Requires approval (optional)
    steps:
      - uses: actions/checkout@v4

      - name: Deploy to production
        uses: appleboy/ssh-action@v1
        with:
          host: ${{ secrets.PROD_HOST }}
          username: deploy
          key: ${{ secrets.DEPLOY_SSH_KEY }}
          script: |
            cd /opt/myapp
            git fetch origin
            git checkout ${{ github.ref_name }}
            pip install -r requirements.txt
            python manage.py migrate --noinput
            systemctl restart myapp
            sleep 3
            curl -sf http://localhost:8000/health || exit 1
```

**How to deploy now:**

```bash
# Anyone on the team can deploy — no SSH key needed
git tag v1.2.3
git push origin v1.2.3
# CI: runs tests → deploys → health checks → done

# Or just push to main (if you prefer):
# on: push: branches: [main]
```

**Set up the secrets (one time):**

```bash
# Generate a deploy-specific key (not anyone's personal key)
ssh-keygen -t ed25519 -f deploy_key -C "github-actions-deploy"

# Add public key to server
ssh prod-server "echo '$(cat deploy_key.pub)' >> ~/.ssh/authorized_keys"

# Add private key to GitHub Secrets
# Settings → Secrets → Actions → New secret
# Name: DEPLOY_SSH_KEY
# Value: (contents of deploy_key)
```

**What this gives you:**

| Before (laptop deploy) | After (CI/CD) |
|---|---|
| Only you can deploy | Anyone can trigger a deploy |
| No tests before deploy | Tests MUST pass |
| No audit trail | Full log of who deployed what, when |
| Deploy from random laptops | Consistent CI environment |
| Manual rollback | `git tag v1.2.2 && git push origin v1.2.2` |
| SSH key on laptops | SSH key in GitHub Secrets only |
| You can't go on vacation | Deploys work without you |

**Optional: require approval for production deploys**

```yaml
# In GitHub: Settings → Environments → "production" → Required reviewers
# Now pushing a tag doesn't auto-deploy — a team lead must click "Approve"

deploy:
  environment: production  # This triggers the approval gate
```

Your vacation shouldn't be blocked by deployment access. Move the keys to CI, the scripts to the repo, and the triggers to git tags. Nobody needs SSH access to production for routine deploys.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
