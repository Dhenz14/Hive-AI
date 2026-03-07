"""
Real-world project help training pairs - Working with legacy code
"""

pairs = [
    {
        "instruction": r'''I inherited a Django 1.11 codebase with no tests. The main app has a 2000-line views.py file with all the business logic jammed into view functions. My boss wants me to add a new feature (subscription billing) but I'm scared to touch anything. How do I approach this without breaking everything?''',
        "output": r'''<think>
Classic legacy situation. They need to add a feature to a fragile codebase with no tests. The answer is NOT "rewrite everything" or "add tests for everything first" -- that takes months and the boss wants the feature now.

The strategy is: create a safe zone for new code, add targeted tests around what you'll touch, then build the feature in the safe zone.
</think>

Don't try to fix the whole codebase. Your goal is to add the feature safely while making things slightly better, not to do a rewrite.

Step 1: Create a separate app for the new feature.

```bash
python manage.py startapp subscriptions
```

This keeps your new code clean and isolated. The 2000-line views.py stays untouched for now.

Step 2: Identify the integration points. Your subscription feature probably needs to interact with the existing User model and maybe an Order or Account model. Read those models carefully. Map out which views touch them:

```bash
# Find every view that references the User model
grep -n "User\|request.user\|get_user" app/views.py
```

Step 3: Add characterization tests for ONLY the parts you'll interact with. Don't test everything -- just the login flow, account page, and whatever endpoint your subscriptions will hook into:

```python
# tests/test_existing_account.py
from django.test import TestCase, Client

class AccountViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("testuser", password="testpass")
        self.client = Client()
        self.client.login(username="testuser", password="testpass")

    def test_account_page_loads(self):
        resp = self.client.get("/account/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, self.user.username)

    def test_account_page_shows_plan_info(self):
        # This will fail now -- that's fine, it documents current behavior
        resp = self.client.get("/account/")
        # Just assert it doesn't crash
        self.assertEqual(resp.status_code, 200)
```

Step 4: Build subscriptions in the new app with proper structure:

```
subscriptions/
    models.py      # Subscription, Plan models
    services.py    # Business logic (NOT in views)
    views.py       # Thin views that call services
    tests/
    urls.py
```

Step 5: Connect to the old code with minimal changes. Add a ForeignKey from your new Subscription model to the existing User. Add one line to the old account template to include subscription info:

```html
<!-- In the existing account template, add ONE line: -->
{% include "subscriptions/status_widget.html" %}
```

This approach means you touch maybe 3 lines in the old codebase while building everything new in a clean, tested app. Over time you can extract more logic out of that views.py into separate apps using the same pattern.'''
    },
    {
        "instruction": r'''I'm looking at a Flask app where all the database queries are raw SQL strings scattered throughout the route handlers. There are about 60 routes and maybe 200 raw queries. I want to gradually move to SQLAlchemy but I can't do it all at once. What's a practical migration strategy?''',
        "output": r'''You need a strangler fig approach -- run both raw SQL and SQLAlchemy side by side, migrate route by route.

Phase 1: Set up SQLAlchemy alongside raw SQL (1 day)

```python
# db.py -- keep your existing connection AND add SQLAlchemy
import sqlite3  # or psycopg2, whatever you use now
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Existing raw connection (keep this working)
def get_raw_conn():
    return sqlite3.connect("app.db")

# New SQLAlchemy session
engine = create_engine("sqlite:///app.db")
SessionLocal = sessionmaker(bind=engine)

class Base(DeclarativeBase):
    pass

def get_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
```

Phase 2: Create models that match your existing tables exactly (2-3 days)

Use `sqlacodegen` to auto-generate models from your existing DB:

```bash
pip install sqlacodegen
sqlacodegen sqlite:///app.db > models_generated.py
```

Review and clean up the output. The tables already exist, so tell SQLAlchemy not to create them:

```python
class User(Base):
    __tablename__ = "users"
    # Match existing columns exactly
    id = Column(Integer, primary_key=True)
    email = Column(String(255))
    # ...
```

Phase 3: Migrate one route at a time. Pick the simplest read-only route first:

```python
# BEFORE
@app.route("/users")
def list_users():
    conn = get_raw_conn()
    rows = conn.execute("SELECT id, email, name FROM users WHERE active = 1").fetchall()
    return render_template("users.html", users=rows)

# AFTER
@app.route("/users")
def list_users():
    session = SessionLocal()
    users = session.query(User).filter(User.active == True).all()
    session.close()
    return render_template("users.html", users=users)
```

Prioritization order:
1. Simple SELECT routes (lowest risk)
2. Routes with complex JOINs (highest value -- raw SQL JOINs are where bugs hide)
3. Write routes (INSERT/UPDATE) last since they carry the most risk

Track progress with a simple checklist:

```python
# MIGRATION_STATUS.py -- not code, just tracking
# [x] GET /users -- migrated 2024-03-01
# [x] GET /users/<id> -- migrated 2024-03-01
# [ ] POST /users -- needs review
# [ ] GET /orders -- complex joins, do after users
```

Aim for 3-5 routes per week. At that pace you'll finish in 3-4 months without any big-bang risk.'''
    },
    {
        "instruction": r'''I'm working on a Node.js Express app where error handling is completely inconsistent. Some routes use try/catch, some use .catch(), some don't handle errors at all and just crash. There's no global error handler. How do I fix this incrementally?''',
        "output": r'''<think>
They need a consistent error handling strategy they can roll out gradually. The key pieces are: a global error handler middleware, a custom error class, and an async wrapper so they don't need try/catch in every route.
</think>

Start by adding the safety net (global error handler), then fix routes one by one.

Step 1: Add a global error handler middleware RIGHT NOW (5 minutes):

```javascript
// middleware/errorHandler.js
function errorHandler(err, req, res, next) {
    console.error(`[${new Date().toISOString()}] ${req.method} ${req.path}:`, err.message);

    const status = err.statusCode || 500;
    const message = status === 500 ? "Internal server error" : err.message;

    res.status(status).json({ error: message });
}

module.exports = errorHandler;
```

```javascript
// app.js -- add this AFTER all your route definitions
const errorHandler = require("./middleware/errorHandler");
// ... all your app.use("/api/...", router) calls ...
app.use(errorHandler);  // must be last
```

This immediately catches any unhandled errors instead of crashing.

Step 2: Create an async wrapper to eliminate try/catch boilerplate:

```javascript
// middleware/asyncHandler.js
const asyncHandler = (fn) => (req, res, next) => {
    Promise.resolve(fn(req, res, next)).catch(next);
};

module.exports = asyncHandler;
```

Step 3: Create a custom error class:

```javascript
// utils/AppError.js
class AppError extends Error {
    constructor(message, statusCode) {
        super(message);
        this.statusCode = statusCode;
    }
}

module.exports = AppError;
```

Step 4: Migrate routes gradually. Before:

```javascript
router.get("/users/:id", async (req, res) => {
    const user = await User.findById(req.params.id);
    // crashes if user is null, no error handling
    res.json(user);
});
```

After:

```javascript
const asyncHandler = require("../middleware/asyncHandler");
const AppError = require("../utils/AppError");

router.get("/users/:id", asyncHandler(async (req, res) => {
    const user = await User.findById(req.params.id);
    if (!user) throw new AppError("User not found", 404);
    res.json(user);
}));
```

The migration is mechanical: wrap with asyncHandler, add null checks, throw AppError instead of sending error responses manually. You can do 5-10 routes per sitting.

The global error handler catches everything immediately, so even unmigrated routes stop crashing the process.'''
    },
    {
        "instruction": r'''I have a Python codebase with a god class -- a single Manager class that's 3500 lines and handles user management, email sending, report generation, and payment processing. I know it needs to be broken up but where do I even start?''',
        "output": r'''Start by mapping the territories. Open that file and look for natural clusters.

```bash
# Find all method definitions to see the scope
grep -n "def " manager.py | head -60
```

You'll likely see methods clustering around topics:

```
# Lines 1-400:    __init__, config, utility methods
# Lines 401-900:  create_user, update_user, delete_user, authenticate, ...
# Lines 901-1400: send_email, send_welcome_email, send_invoice_email, ...
# Lines 1401-2200: generate_report, monthly_report, export_csv, ...
# Lines 2201-3500: charge_card, refund, create_subscription, ...
```

Now extract one cluster at a time. Start with the one that has the FEWEST dependencies on the rest -- usually email or reports.

```python
# services/email_service.py
class EmailService:
    def __init__(self, smtp_config):
        self.config = smtp_config

    def send(self, to, subject, body):
        # Move the raw send logic here
        ...

    def send_welcome(self, user):
        # Move from Manager.send_welcome_email
        ...

    def send_invoice(self, user, invoice):
        # Move from Manager.send_invoice_email
        ...
```

Then in the Manager class, replace the extracted methods with delegation:

```python
class Manager:
    def __init__(self, config):
        # ... existing init ...
        self.email = EmailService(config.smtp)

    # DELETE the old send_welcome_email method body, replace with:
    def send_welcome_email(self, user):
        return self.email.send_welcome(user)
```

This is critical: keep the old method signatures as thin wrappers initially. Every caller still works. You can update callers to use `manager.email.send_welcome()` directly later.

Extraction order (least to most entangled):
1. EmailService -- usually standalone, just needs SMTP config
2. ReportService -- reads data but rarely writes
3. PaymentService -- has external API deps but clear boundaries
4. UserService -- most entangled, do last

After each extraction, run your app and verify nothing broke. If you have no tests, at minimum do a manual smoke test of the affected features.

Target: one extraction per week. In a month, Manager is down to a thin orchestration layer that delegates to focused services.'''
    },
    {
        "instruction": r'''There's a Python script at work that everyone's afraid to modify. It's a 500-line data pipeline that reads from 3 APIs, transforms the data, and loads it into our database. No functions -- just one long procedural script with lots of global variables. I need to add a 4th API source. How should I approach this?''',
        "output": r'''Don't refactor the whole thing. Your goal is to add the 4th source with minimal risk to the existing 3.

First, understand the current flow. Read through it and drop comments marking the sections:

```python
# === SECTION 1: Config and globals (lines 1-40) ===
API_KEY_1 = os.environ["API_KEY_1"]
all_records = []
# ...

# === SECTION 2: Fetch from API 1 (lines 41-120) ===
resp = requests.get(...)
for item in resp.json()["data"]:
    # ... transform ...
    all_records.append(transformed)

# === SECTION 3: Fetch from API 2 (lines 121-200) ===
# ... similar pattern ...

# === SECTION 4: Fetch from API 3 (lines 201-300) ===
# ... similar pattern ...

# === SECTION 5: Load into database (lines 301-500) ===
conn = psycopg2.connect(...)
for record in all_records:
    # ... insert ...
```

Now add your 4th source following the EXACT same pattern as the existing ones. Put it right before the database load section:

```python
# === SECTION 4.5: Fetch from API 4 (NEW) ===
API_KEY_4 = os.environ.get("API_KEY_4", "")
if API_KEY_4:
    try:
        resp4 = requests.get(
            "https://api.fourthtool.com/v1/data",
            headers={"Authorization": f"Bearer {API_KEY_4}"},
            timeout=30,
        )
        resp4.raise_for_status()
        for item in resp4.json()["results"]:
            transformed = {
                "source": "api4",
                "id": item["id"],
                "name": item["name"],
                "value": float(item.get("amount", 0)),
                "timestamp": item["created_at"],
            }
            all_records.append(transformed)
        print(f"API 4: fetched {len(resp4.json()['results'])} records")
    except Exception as e:
        print(f"API 4 failed: {e}")
        # Don't crash the whole pipeline for the new source
```

Key decisions:
- Wrap it in `if API_KEY_4` so the pipeline still works without it configured
- Add a try/except so a failure in your new source doesn't kill the existing pipeline
- Match the exact record format the other sections produce
- Add a timeout (the existing code probably doesn't have one -- that's okay, don't fix it now)

After this is working and deployed, THEN if you want to do a small cleanup, extract each section into a function:

```python
def fetch_api1():
    # move section 2 here
    return records

def fetch_api4():
    # your new section
    return records

all_records = fetch_api1() + fetch_api2() + fetch_api3() + fetch_api4()
```

But that's optional. The main thing is: ship the feature first, refactor second.'''
    },
]
