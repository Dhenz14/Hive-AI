"""
Real-world project help training pairs - Migration tasks
"""

pairs = [
    {
        "instruction": r'''We have a Flask app that still uses Python 2.7. Yes, in 2024. Management finally approved the Python 3 migration. The app is about 30k lines with 200+ files. What's the safest migration strategy?''',
        "output": r'''<think>
Python 2 to 3 migration of a large Flask app. The key is making it work on both 2 and 3 first (bridge phase), then dropping 2 support. Trying to do a big-bang migration of 30k lines is too risky.
</think>

Don't do a big-bang migration. Use the bridge approach: make the code work on both Python 2 AND 3, verify it on 3, then drop 2 support.

Phase 1: Automated analysis (1 day)

```bash
# Install the migration tools
pip install modernize futurize pylint

# Get a report of what needs to change
python-modernize -w --no-diffs -l . 2>&1 | tee migration_report.txt

# Count the issues
python-modernize -l . 2>&1 | grep -c "RefactoringTool"
```

Phase 2: Add compatibility layer (1 week)

```python
# compat.py -- put this in your project root
import sys
PY2 = sys.version_info[0] == 2

if PY2:
    string_types = (str, unicode)
    text_type = unicode
    binary_type = str
    input = raw_input
else:
    string_types = (str,)
    text_type = str
    binary_type = bytes
    input = input
```

Phase 3: Fix files in priority order (2-4 weeks)

The most common changes:

```python
# 1. Print statements -> function calls
# BEFORE:
print "hello"
# AFTER:
from __future__ import print_function
print("hello")

# 2. Division
# BEFORE:
result = 5 / 2  # returns 2 in Py2, 2.5 in Py3
# AFTER:
from __future__ import division
result = 5 // 2  # integer division explicit

# 3. Dict methods
# BEFORE:
for k, v in d.iteritems():
# AFTER:
for k, v in d.items():

# 4. Unicode
# BEFORE:
name = u"hello"
# AFTER:
from __future__ import unicode_literals
name = "hello"

# 5. Imports that moved
# BEFORE:
from urllib import urlencode
from urlparse import urlparse
# AFTER:
try:
    from urllib.parse import urlencode, urlparse
except ImportError:
    from urllib import urlencode
    from urlparse import urlparse
```

Use `python-modernize` to auto-fix the mechanical stuff:

```bash
# Auto-fix one directory at a time, review the diffs
python-modernize -w --no-six app/models/
git diff  # review
git add -p  # stage selectively
```

Phase 4: Set up dual CI (ongoing)

```yaml
# Run tests on both versions
jobs:
  test-py2:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v4
        with:
          python-version: '2.7'
      - run: pip install -r requirements.txt && pytest

  test-py3:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt && pytest
```

Phase 5: Once all tests pass on both versions, deploy on Python 3 and drop the Python 2 support.

Tackle files in this order: models first (data layer), then utilities, then views, then templates. The `__future__` imports are safe to add everywhere immediately.'''
    },
    {
        "instruction": r'''We need to migrate our database from MySQL 5.7 to PostgreSQL 14. The app is Django. We have about 50 tables and 20GB of data. What's the migration plan?''',
        "output": r'''Django makes this easier than most frameworks because the ORM abstracts the database. But there are MySQL-specific things that will bite you.

Phase 1: Audit MySQL-specific code (1-2 days)

```bash
# Find raw SQL that might use MySQL syntax
grep -rn "connection.cursor\|raw(\|extra(" --include="*.py" | grep -v migration

# Find MySQL-specific field types or functions
grep -rn "UNSIGNED\|TINYINT\|MEDIUMTEXT\|GROUP_CONCAT\|IF(" --include="*.py"

# Check for MySQL-specific Django settings
grep -rn "mysql\|MySQLdb\|mysqlclient" --include="*.py" --include="*.txt" --include="*.cfg"
```

Common MySQL-to-Postgres differences:
- `AUTO_INCREMENT` -> `SERIAL` / `GENERATED ALWAYS AS IDENTITY` (Django handles this)
- `GROUP_CONCAT` -> `STRING_AGG`
- Backtick quoting -> double-quote quoting (Django handles this)
- `TINYINT(1)` for booleans -> actual `BOOLEAN` type
- Case-insensitive `LIKE` by default in MySQL -> case-sensitive in Postgres

Phase 2: Set up Postgres locally and run migrations (1 day)

```python
# settings.py
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": "myapp",
        "USER": "myapp",
        "PASSWORD": "localdev",
        "HOST": "localhost",
        "PORT": "5432",
    }
}
```

```bash
createdb myapp
python manage.py migrate
```

Fix any migration errors. Common issues:
- Unsigned integers (Postgres doesn't have them -- use PositiveIntegerField constraints)
- Default values using MySQL functions

Phase 3: Migrate data using pgloader (fastest approach):

```bash
# Install pgloader
apt-get install pgloader

# Create config
cat > migrate.load << 'CONF'
LOAD DATABASE
    FROM mysql://user:pass@localhost/myapp_mysql
    INTO postgresql://user:pass@localhost/myapp_pg

WITH include no drop,
     create no tables,  -- Django already created them
     data only,
     reset sequences

SET maintenance_work_mem to '512MB',
    work_mem to '48MB'

CAST type tinyint to boolean using tinyint-to-boolean
CONF

pgloader migrate.load
```

Phase 4: Verify data integrity:

```python
# verify_migration.py
import MySQLdb
import psycopg2

tables = ["users", "orders", "products"]  # your tables

mysql_conn = MySQLdb.connect(db="myapp_mysql")
pg_conn = psycopg2.connect(dbname="myapp_pg")

for table in tables:
    mysql_count = mysql_conn.cursor()
    mysql_count.execute(f"SELECT COUNT(*) FROM {table}")
    pg_count = pg_conn.cursor()
    pg_count.execute(f"SELECT COUNT(*) FROM {table}")

    m = mysql_count.fetchone()[0]
    p = pg_count.fetchone()[0]
    status = "OK" if m == p else "MISMATCH"
    print(f"{table}: MySQL={m} Postgres={p} [{status}]")
```

Phase 5: Deploy. Use a maintenance window:
1. Put app in maintenance mode
2. Run final pgloader sync
3. Switch DATABASE settings to Postgres
4. Run `python manage.py migrate` (for any pending)
5. Smoke test critical flows
6. Remove maintenance mode

Keep MySQL running read-only for 1 week as a rollback option.'''
    },
    {
        "instruction": r'''We're upgrading our Django project from 2.2 to 4.2 (yes, we're way behind). We skipped several major versions. The project has about 100 models and 50 views. What's the upgrade path?''',
        "output": r'''<think>
Django 2.2 to 4.2 is a big jump. You can't skip versions -- each major version has breaking changes and deprecation removals. The safe path is stepping through each LTS version: 2.2 -> 3.2 -> 4.2.
</think>

You must step through each LTS release. Jumping directly will break things in ways that are hard to debug.

Path: 2.2 -> 3.0 -> 3.1 -> 3.2 (LTS) -> 4.0 -> 4.1 -> 4.2 (LTS)

But practically, you only need to stop and stabilize at LTS versions: 2.2 -> 3.2 -> 4.2.

Step 1: Fix all deprecation warnings on 2.2 FIRST:

```bash
python -Wd manage.py test 2>&1 | grep DeprecationWarning | sort -u
```

Common 2.2 deprecations to fix now:

```python
# url() -> path() or re_path()
# BEFORE:
from django.conf.urls import url
url(r'^users/(?P<pk>\d+)/$', user_detail)
# AFTER:
from django.urls import path
path('users/<int:pk>/', user_detail)

# django.utils.encoding.force_text -> force_str
# django.utils.translation.ugettext -> gettext

# on_delete is now required on ForeignKey (should already be there in 2.2)
```

Step 2: Upgrade to Django 3.2:

```bash
pip install Django==3.2.*
python manage.py test
```

Major breaking changes in 3.x:
- `DEFAULT_AUTO_FIELD` must be set:

```python
# settings.py
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
```

- `HttpRequest.is_ajax()` removed. Replace with:

```python
# BEFORE:
if request.is_ajax():
# AFTER:
if request.headers.get("X-Requested-With") == "XMLHttpRequest":
```

- `django.conf.urls.url()` fully removed -- use `path()` or `re_path()`
- Middleware must be new-style (not `MiddlewareMixin` -- but check if yours already is)

Step 3: Stabilize on 3.2. Run full test suite, deploy, run in production for a few days.

Step 4: Upgrade to Django 4.2:

```bash
pip install Django==4.2.*
python manage.py test
```

Major breaking changes in 4.x:
- `USE_L10N` defaults to True now
- `CSRF_TRUSTED_ORIGINS` requires scheme (https://):

```python
CSRF_TRUSTED_ORIGINS = ["https://mysite.com"]  # was just "mysite.com"
```

- Form fields `use_l10n` parameter removed
- `django.contrib.postgres.fields.JSONField` -> `django.db.models.JSONField`

Step 5: Update your dependencies too. Check each one supports the target Django version:

```bash
pip list --outdated
# Check each package's Django compatibility on PyPI
```

Common packages that need version bumps:
- django-rest-framework
- django-filter
- django-allauth
- celery/django-celery-beat

Do each upgrade in its own branch and PR. Don't combine the 3.2 and 4.2 upgrades -- if something breaks, you want to know which upgrade caused it.'''
    },
    {
        "instruction": r'''We need to add Alembic migrations to an existing SQLAlchemy project that never had them. The database has 40 tables with data in production. How do I set up Alembic without it trying to recreate all the tables?''',
        "output": r'''This is the "brownfield Alembic setup" problem. You need to create an initial migration that represents the current state, then mark it as already applied.

Step 1: Install and initialize Alembic:

```bash
pip install alembic
alembic init alembic
```

Step 2: Configure alembic.ini and env.py:

```python
# alembic/env.py
from myapp.models import Base  # your SQLAlchemy Base
from myapp.config import DATABASE_URL

config = context.config
config.set_main_option("sqlalchemy.url", DATABASE_URL)
target_metadata = Base.metadata
```

Step 3: Auto-generate the initial migration:

```bash
alembic revision --autogenerate -m "initial schema"
```

This creates a migration with all your CREATE TABLE statements. But you do NOT want to run this against production -- the tables already exist.

Step 4: Open the generated migration and verify it looks correct. It should have all 40 tables in the `upgrade()` function.

Step 5: Mark this migration as already applied WITHOUT running it:

```bash
# On your production database (and staging, dev, etc.)
alembic stamp head
```

This writes the migration version to the `alembic_version` table without executing any SQL. Alembic now thinks the database is up to date.

Step 6: Verify:

```bash
alembic current
# Should show the initial migration as current

alembic check
# Should show no pending migrations
```

Step 7: Test that future migrations work by making a small model change:

```python
# Add a column to an existing model
class User(Base):
    __tablename__ = "users"
    # ... existing columns ...
    bio = Column(Text, nullable=True)  # new column
```

```bash
alembic revision --autogenerate -m "add user bio column"
# Review the generated migration
alembic upgrade head
```

Important gotchas:
- Run `alembic stamp head` on EVERY environment (prod, staging, dev) before anyone runs `alembic upgrade`
- If your models don't perfectly match the actual database, autogenerate will produce diffs. Fix your models to match reality first
- Add `alembic/versions/` to git. Every developer needs the same migration chain

```bash
# Verify models match database
alembic revision --autogenerate -m "test"
# If this generates an empty migration, you're in sync
# Delete the test migration file
```'''
    },
    {
        "instruction": r'''We're migrating from REST to GraphQL for our Node.js API. We have 30 REST endpoints that mobile and web clients use. We can't break existing clients. How do we do this incrementally?''',
        "output": r'''Run both REST and GraphQL side by side. Migrate one endpoint at a time while keeping the REST versions alive.

Step 1: Add GraphQL alongside existing REST (1 day):

```javascript
// server.js -- keep Express routes, add Apollo
const express = require("express");
const { ApolloServer } = require("@apollo/server");
const { expressMiddleware } = require("@apollo/server/express4");

const app = express();

// Existing REST routes stay exactly as they are
app.use("/api/users", usersRouter);
app.use("/api/orders", ordersRouter);

// Add GraphQL on a separate path
const server = new ApolloServer({ typeDefs, resolvers });
await server.start();
app.use("/graphql", expressMiddleware(server, {
    context: async ({ req }) => ({
        user: await authenticateRequest(req),  // reuse existing auth
    }),
}));
```

Step 2: Build GraphQL resolvers that call your existing service layer:

```javascript
// Don't rewrite business logic -- wrap it

// Existing service (keep this)
// services/users.js
async function getUser(id) { ... }
async function listUsers(filters) { ... }

// New GraphQL resolver (calls existing service)
const resolvers = {
    Query: {
        user: (_, { id }, ctx) => userService.getUser(id),
        users: (_, { filter }, ctx) => userService.listUsers(filter),
    },
    Mutation: {
        createUser: (_, { input }, ctx) => userService.createUser(input),
    },
};
```

Step 3: Migrate endpoints in priority order. Start with read-heavy endpoints that benefit most from GraphQL (clients can request exactly the fields they need):

```
Week 1: GET /api/users, GET /api/users/:id  -> Query.users, Query.user
Week 2: GET /api/orders (with nested items)  -> Query.orders (big win -- avoids N+1 REST calls)
Week 3: POST /api/orders                    -> Mutation.createOrder
Week 4-6: Remaining endpoints
```

Step 4: Update clients incrementally. Don't switch all clients at once:

```
Phase 1: Web app switches to GraphQL (you control deploys)
Phase 2: New mobile app version uses GraphQL
Phase 3: After old mobile versions die off, deprecate REST endpoints
```

Step 5: Deprecate REST endpoints with headers:

```javascript
// Mark old endpoints as deprecated but keep them working
app.use("/api/users", (req, res, next) => {
    res.set("Deprecation", "true");
    res.set("Sunset", "2025-06-01");
    res.set("Link", '</graphql>; rel="successor-version"');
    next();
}, usersRouter);
```

Key rule: never remove a REST endpoint until analytics confirm zero traffic. The GraphQL endpoint runs alongside REST for as long as needed -- there is no cutover date.'''
    },
]
