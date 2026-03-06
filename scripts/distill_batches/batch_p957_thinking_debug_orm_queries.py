PAIRS = [
    ("thinking/debugging", r'''Our API endpoint is extremely slow. Profiling shows 500+ database queries for a single request:

```
GET /api/orders?status=active
Duration: 4.2s
SQL Queries: 523

Query log (sample):
SELECT * FROM orders WHERE status = 'active';
SELECT * FROM customers WHERE id = 1;
SELECT * FROM customers WHERE id = 2;
SELECT * FROM customers WHERE id = 3;
... (repeated 520 more times)
```

SQLAlchemy code:
```python
@app.route('/api/orders')
def get_orders():
    status = request.args.get('status', 'active')
    orders = Order.query.filter_by(status=status).all()
    result = []
    for order in orders:
        result.append({
            'id': order.id,
            'total': order.total,
            'customer_name': order.customer.name,  # triggers lazy load!
            'customer_email': order.customer.email,
        })
    return jsonify(result)
```

Models:
```python
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    total = db.Column(db.Float)
    status = db.Column(db.String(20))
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    customer = db.relationship('Customer', backref='orders')
```

How do I fix this N+1 query problem?''', r'''<think>
This is a classic N+1 query problem. Let me trace the query pattern:

1. Executes 1 query to fetch all active orders (the "1")
2. For each order, accessing `order.customer.name` triggers a lazy load query to fetch that customer (the "N")

With 522 active orders, that is 1 + 522 = 523 queries. That matches the log showing 523 queries.

My first thought was "just add a JOIN" -- but wait, which kind of JOIN? SQLAlchemy has multiple eager loading strategies and the right choice depends on the relationship cardinality:
- `joinedload()` uses a SQL JOIN. Could this cause data duplication? For many-to-one (order->customer), no -- each order row just gets customer columns appended. But for one-to-many (customer->orders), YES -- the customer row would be duplicated for each order, inflating the result set.
- `subqueryload()` uses a separate correlated subquery. Hmm, this avoids duplication but adds query complexity.
- `selectinload()` uses SELECT ... WHERE id IN (...). This is often the best all-around choice because it avoids both data duplication and correlated subqueries.

Wait, for this specific case (many orders, each with ONE customer), joinedload is actually ideal. The relationship is many-to-one, so there is no duplication risk. But if the user later adds `order.items` (a one-to-many), using joinedload on BOTH relationships would create a Cartesian product disaster. I should mention selectinload as the safer default.

I also considered whether setting `lazy='joined'` as the default on the relationship model would be better than using `.options()` per query. The tradeoff: default eager loading ensures you never accidentally trigger N+1, but it loads the relationship even when you do not need it. For an API endpoint that only returns order IDs and totals, joining the customer table is wasted work. Hmm, actually for web apps, the per-query `.options()` approach is more flexible -- you eagerly load only what each endpoint needs.

There is also a fourth approach I should mention: writing a raw query that selects only the columns needed. This bypasses the ORM entirely and is the most efficient, but loses the convenience of ORM objects. For a pure read-only API endpoint like this, it might be the best option.
</think>

This is the classic N+1 query problem. For each of the 522 active orders, accessing `order.customer` triggers a separate SQL query because SQLAlchemy's default relationship loading is "lazy" -- it only fetches related objects when they are accessed.

**The query pattern:**
```
1 query:   SELECT * FROM orders WHERE status = 'active'  (fetches 522 orders)
522 queries: SELECT * FROM customers WHERE id = ?  (one per order)
Total: 523 queries
```

**Fix 1: Use eager loading with joinedload (best for this case)**

```python
from sqlalchemy.orm import joinedload

@app.route('/api/orders')
def get_orders():
    status = request.args.get('status', 'active')
    orders = Order.query.options(
        joinedload(Order.customer)
    ).filter_by(status=status).all()

    result = []
    for order in orders:
        result.append({
            'id': order.id,
            'total': order.total,
            'customer_name': order.customer.name,   # no extra query!
            'customer_email': order.customer.email,
        })
    return jsonify(result)
```

This generates a single query with a JOIN:
```sql
SELECT orders.*, customers.*
FROM orders
LEFT JOIN customers ON orders.customer_id = customers.id
WHERE orders.status = 'active';
```

**Fix 2: Use selectinload (better for large result sets)**

```python
from sqlalchemy.orm import selectinload

orders = Order.query.options(
    selectinload(Order.customer)
).filter_by(status=status).all()
```

This generates exactly 2 queries:
```sql
SELECT * FROM orders WHERE status = 'active';
SELECT * FROM customers WHERE id IN (1, 2, 3, ...);
```

`selectinload` is preferred over `joinedload` when:
- The related table has many columns (JOIN would duplicate order data)
- You are loading collections (one-to-many relationships)
- The result set is very large

**Fix 3: Set eager loading as the default on the relationship**

```python
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    total = db.Column(db.Float)
    status = db.Column(db.String(20))
    customer_id = db.Column(db.Integer, db.ForeignKey('customer.id'))
    customer = db.relationship('Customer', backref='orders', lazy='joined')
```

Setting `lazy='joined'` makes every query for Orders automatically JOIN with Customers. Use this when the relationship is almost always needed.

**Fix 4: Use a dedicated query for the exact data you need**

```python
@app.route('/api/orders')
def get_orders():
    status = request.args.get('status', 'active')
    results = db.session.query(
        Order.id,
        Order.total,
        Customer.name.label('customer_name'),
        Customer.email.label('customer_email'),
    ).join(Customer).filter(
        Order.status == status
    ).all()

    return jsonify([{
        'id': r.id,
        'total': r.total,
        'customer_name': r.customer_name,
        'customer_email': r.customer_email,
    } for r in results])
```

This selects only the columns you need -- most efficient, but loses ORM object features.

**Prevention tips:**
- Enable SQLAlchemy query logging in development: `app.config['SQLALCHEMY_ECHO'] = True`
- Use `sqlalchemy-utils` or custom middleware to count queries per request
- Set `SQLALCHEMY_WARN_20=1` environment variable to catch legacy patterns
- Consider `raise_load` to make lazy loading raise an exception instead of silently executing
- Add a query count assertion in your test suite: fail if any endpoint exceeds N queries'''),

    ("thinking/debugging", r'''My Flask app crashes with a "detached instance" error when accessing a lazy-loaded relationship:

```
sqlalchemy.orm.exc.DetachedInstanceError: Parent instance <Order at 0x7f3b2c> is not bound to a Session; lazy load operation of attribute 'items' cannot proceed (Background on this error at: https://sqlalche.me/e/14/bhk3)
```

Code:
```python
def get_order(order_id):
    with Session() as session:
        order = session.query(Order).get(order_id)
    # session is closed here
    return order

# Later in the code:
order = get_order(42)
for item in order.items:  # CRASH! Session is closed
    print(item.name)
```

The order object exists but its items relationship cannot be loaded because the session is gone.''', r'''<think>
This is a common SQLAlchemy issue. When a session is closed, all objects loaded through it become "detached." Detached objects retain their eagerly loaded scalar data (like order.id, order.total) but cannot perform lazy loads because there is no active session to execute queries.

My first instinct was "just keep the session open longer." But wait -- that means holding a database connection for the entire request lifecycle. If the request does CPU-bound work (template rendering, computation) while holding the connection, other requests cannot use it. Under load, this exhausts the connection pool. So keeping sessions open longer trades one problem for another.

I then considered eager loading -- loading the relationships before closing the session. That would work here: `joinedload(Order.items)` fetches everything in one query, so accessing `order.items` after the session closes works because the data is already in memory. But hmm, this requires knowing in advance which relationships will be accessed. What if sometimes the caller needs `order.items` and sometimes `order.payments`? The `get_order` function would need to accept loading options as parameters, coupling the data access layer to whatever the caller wants.

Could I use `expire_on_commit=False`? That prevents objects from being expired after commit, so their attributes remain accessible. But wait, that only helps with scalar attributes -- lazy-loaded relationships still require an active session. And it introduces a staleness risk: the object might show data that another transaction has already changed.

Actually, the cleanest approach is to convert ORM objects to DTOs (Data Transfer Objects) or plain dicts inside the session scope. This way, no SQLAlchemy object ever leaves the session boundary. The tradeoff is more boilerplate for the conversion step, but it eliminates an entire class of detached-instance bugs. I initially resisted this because it feels like extra work, but for web apps returning JSON anyway, you need serialization logic regardless -- might as well do it inside the session.

For Flask/FastAPI apps specifically, a request-scoped session is also viable. It keeps the session open for the entire request but closes automatically when the response is sent. This is a good middle ground between "session per function" and manual lifetime management.
</think>

When the `Session()` context manager exits, the session is closed and all objects loaded through it become "detached." Detached objects retain their scalar column data (id, name, etc.) but cannot perform lazy loading because there is no active database connection to execute the query.

Accessing `order.items` (a lazy-loaded relationship) on a detached object triggers this error.

**Fix 1: Eager load before closing the session**

```python
from sqlalchemy.orm import joinedload

def get_order(order_id):
    with Session() as session:
        order = session.query(Order).options(
            joinedload(Order.items)
        ).get(order_id)
    return order  # items are already loaded, no lazy load needed

order = get_order(42)
for item in order.items:  # Works! Data was loaded eagerly
    print(item.name)
```

**Fix 2: Convert to a data transfer object inside the session**

```python
from dataclasses import dataclass
from typing import List

@dataclass
class OrderDTO:
    id: int
    total: float
    items: List[dict]

def get_order(order_id):
    with Session() as session:
        order = session.query(Order).options(
            joinedload(Order.items)
        ).get(order_id)

        if order is None:
            return None

        return OrderDTO(
            id=order.id,
            total=order.total,
            items=[{'name': item.name, 'qty': item.qty} for item in order.items]
        )
```

This is the cleanest approach: convert to plain data objects before leaving the session scope. No SQLAlchemy objects leak outside the session boundary.

**Fix 3: Use a request-scoped session (for web apps)**

```python
from flask import g
from sqlalchemy.orm import scoped_session, sessionmaker

SessionFactory = sessionmaker(bind=engine)
ScopedSession = scoped_session(SessionFactory)

@app.before_request
def open_session():
    g.db = ScopedSession()

@app.teardown_request
def close_session(exception=None):
    ScopedSession.remove()

def get_order(order_id):
    # Uses the request-scoped session -- stays open for the entire request
    return g.db.query(Order).get(order_id)

@app.route('/orders/<int:order_id>')
def show_order(order_id):
    order = get_order(order_id)
    items = order.items  # Works! Session is still open
    return jsonify(...)
```

**Fix 4: Use expire_on_commit=False**

```python
Session = sessionmaker(bind=engine, expire_on_commit=False)

def get_order(order_id):
    with Session() as session:
        order = session.query(Order).options(
            joinedload(Order.items)
        ).get(order_id)
        session.commit()  # normally expires all objects
    return order  # attributes still accessible

# Caution: data may be stale if another transaction modifies it
```

This prevents objects from being expired after commit, but it means you might work with stale data.

**Prevention tips:**
- Establish a clear session lifecycle boundary (per request, per task, per unit of work)
- Use the repository pattern: all database access happens inside the session scope
- Convert ORM objects to DTOs or dicts before returning from repository methods
- Use `session.expire_on_commit = False` only when you understand the staleness implications
- Enable `lazy='raise'` on relationships during testing to catch lazy loads early:
  ```python
  customer = db.relationship('Customer', lazy='raise')
  ```'''),

    ("thinking/debugging", r'''Our Alembic migration fails when two developers create migrations on different branches:

```
alembic.util.exc.CommandError: Can't locate revision identified by 'a1b2c3d4e5f6'

FAILED: Multiple head revisions are present for given argument 'head';
please specify a specific target revision, '--resolve-dependencies',
or 'heads' for all heads.

Current heads: a1b2c3d4e5f6, f6e5d4c3b2a1
```

Developer A created migration a1b2c3d4 (add user_email column) and Developer B created migration f6e5d4c3 (add user_phone column). Both branched from the same parent revision. After merging branches, Alembic has two heads.

How do we resolve this?''', r'''<think>
This is a common issue with Alembic migrations in team environments. When two developers branch from the same parent migration and both create new migrations, Alembic ends up with a forked history -- two "heads" instead of one.

My first thought was "just rebase one migration onto the other" by editing its `down_revision`. But wait -- manually editing `down_revision` is dangerous because it changes the migration's identity and could cause Alembic to re-run or skip migrations on environments where one branch was already applied. If Developer A's migration is already applied on staging, changing its down_revision would confuse Alembic's version tracking.

Could I just delete one migration and recreate it? That would work if it has not been applied anywhere, but once migrations are applied to any shared environment, they should be treated as immutable. Deleting applied migrations breaks the history chain.

Actually, the correct solution is `alembic merge heads`. This creates a new migration file that has BOTH heads as its parent revisions (`down_revision` is a tuple). Alembic understands branching and merging natively -- the merge migration simply records that both branches are prerequisites. The merge migration's upgrade/downgrade functions are empty since no schema changes are needed, it just reconciles the history.

Hmm, but what if the two migrations conflict -- both adding a column with the same name, or both altering the same table in incompatible ways? The merge migration itself would still be empty, but applying both migrations would fail at the database level. In that case, we need manual conflict resolution in the merge migration's upgrade function. This is similar to a git merge conflict but at the schema level.

For prevention, I should recommend a CI check that fails if multiple heads exist, and a team practice of always pulling before creating new migrations.
</think>

This is a common team workflow issue with Alembic. When two developers branch from the same migration and both create new migrations, the history forks. Alembic requires a linear history (or an explicit merge) to determine the correct current state.

**Step 1: Verify the situation**

```bash
alembic heads
# Output:
# a1b2c3d4e5f6 (head)
# f6e5d4c3b2a1 (head)

alembic history --verbose
# Shows the branching point
```

**Step 2: Create a merge migration**

```bash
alembic merge heads -m "merge_add_email_and_phone"
```

This creates a new migration file that has both heads as its parents:

```python
"""merge_add_email_and_phone

Revision ID: 99887766aabb
Revises: a1b2c3d4e5f6, f6e5d4c3b2a1
"""

revision = '99887766aabb'
down_revision = ('a1b2c3d4e5f6', 'f6e5d4c3b2a1')

def upgrade():
    pass  # no schema changes needed, just merging history

def downgrade():
    pass
```

**Step 3: Run the migrations**

```bash
# If both migrations have already been applied on different environments,
# run only the merge:
alembic upgrade head

# If starting fresh:
alembic upgrade head  # applies all three: both branches + merge
```

**Step 4: Verify single head**

```bash
alembic heads
# Output:
# 99887766aabb (head)
```

**What if the migrations conflict (both modify the same table)?**

If both migrations modify the same column or have conflicting changes, you need to manually resolve the conflict in the merge migration:

```python
def upgrade():
    # If migration A added email as VARCHAR(100) and migration B
    # also altered the users table, handle conflicts here
    pass

def downgrade():
    pass
```

**Preventing this in the future:**

```python
# alembic.ini or alembic/env.py
# Add a pre-commit hook that checks for multiple heads:

# .pre-commit-config.yaml
# - repo: local
#   hooks:
#     - id: alembic-heads-check
#       name: Check for multiple Alembic heads
#       entry: bash -c 'heads=$(alembic heads | wc -l); if [ "$heads" -gt 1 ]; then echo "Multiple Alembic heads detected! Run: alembic merge heads"; exit 1; fi'
#       language: system
```

**CI check for migration conflicts:**

```bash
#!/bin/bash
# ci/check_migrations.sh
HEAD_COUNT=$(alembic heads 2>/dev/null | wc -l)
if [ "$HEAD_COUNT" -gt 1 ]; then
    echo "ERROR: Multiple Alembic heads detected."
    echo "Run 'alembic merge heads -m \"merge_description\"' to fix."
    alembic heads
    exit 1
fi
echo "OK: Single migration head"
```

**Team workflow best practices:**
- Always pull and check `alembic heads` before creating a new migration
- Create migrations as late as possible (right before merging to main)
- Add a CI check that fails if multiple heads exist
- Use descriptive migration messages so team members understand conflicts
- Consider squashing migrations on feature branches before merging to main
- Never manually edit the `down_revision` field -- use `alembic merge` instead'''),

    ("thinking/debugging", r'''Our SQLAlchemy connection pool keeps timing out during peak traffic:

```
sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.0
```

Configuration:
```python
engine = create_engine(
    'postgresql://user:pass@db-host:5432/mydb',
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
)
```

During peak: 200 concurrent requests, each holding a connection for database operations.''', r'''<think>
The connection pool has a maximum of 5 + 10 = 15 connections. With 200 concurrent requests, that leaves 185 requests queued waiting for a connection. They wait up to 30 seconds, then timeout. The math is simple: 200 concurrent - 15 available = 185 starved.

My first instinct is "just increase pool_size to 200." But wait -- PostgreSQL has a default `max_connections` of 100. If we have multiple application instances (say 4 workers), each with pool_size=50, that is 200 connections total, exceeding PostgreSQL's limit. The database is the bottleneck, not just the application pool. Blindly increasing pool_size shifts the problem to the database layer.

Could we just increase PostgreSQL's max_connections to 500? Hmm, each PostgreSQL connection consumes memory (roughly 10MB per connection for work_mem and shared buffers). 500 connections would use ~5GB just for connection overhead, which is significant. PostgreSQL also has performance degradation with too many connections due to lock contention and context switching.

Actually, the real fix is multi-pronged:
1. Increase pool size moderately (to maybe 20+30=50)
2. Reduce connection hold time -- the biggest win is often releasing connections between database operations instead of holding them during CPU-bound processing
3. Use PgBouncer as a connection pooler between the app and PostgreSQL (it multiplexes many app connections over fewer DB connections)
4. For read-heavy workloads, add read replicas and route queries appropriately

I initially overlooked `pool_pre_ping` and `pool_recycle`, which are also important. `pool_pre_ping=True` tests connections before use (handles DB restarts gracefully), and `pool_recycle=1800` prevents connections from going stale. These do not solve the capacity issue but prevent secondary failures.
</think>

The pool allows a maximum of 15 connections (pool_size=5 + max_overflow=10), but you have 200 concurrent requests. The remaining 185 requests wait in a queue for up to 30 seconds for a connection to become available, then timeout.

**Immediate fix: Tune the pool parameters**

```python
engine = create_engine(
    'postgresql://user:pass@db-host:5432/mydb',
    pool_size=20,        # base pool size
    max_overflow=30,     # additional connections under load
    pool_timeout=10,     # fail fast instead of waiting 30s
    pool_recycle=1800,   # recycle connections every 30 min (avoids stale connections)
    pool_pre_ping=True,  # test connections before using (handles DB restarts)
)
```

This gives you 50 maximum connections. But PostgreSQL's default max_connections is 100, so do not exceed that across all application instances.

**Check PostgreSQL's limit:**

```sql
SHOW max_connections;  -- default: 100
-- Increase in postgresql.conf if needed:
-- max_connections = 200
```

**Fix 2: Reduce connection hold time**

The biggest improvement often comes from holding connections for shorter periods:

```python
# BAD: holds connection for the entire request
@app.route('/api/report')
def generate_report():
    with Session() as session:
        data = session.query(Order).all()  # gets connection
        # ... 2 seconds of CPU-bound processing ...
        summary = compute_summary(data)    # still holding connection!
        more_data = session.query(Item).all()
        return jsonify(summary)

# GOOD: release connection between queries
@app.route('/api/report')
def generate_report():
    with Session() as session:
        data = session.query(Order).all()

    summary = compute_summary(data)  # no connection held

    with Session() as session:
        more_data = session.query(Item).all()

    return jsonify(summary)
```

**Fix 3: Use connection pooling middleware (PgBouncer)**

```
App (200 connections) -> PgBouncer (20 connections) -> PostgreSQL
```

PgBouncer sits between your application and PostgreSQL, multiplexing many application connections over fewer database connections. Configure it in transaction mode:

```ini
; pgbouncer.ini
[databases]
mydb = host=localhost port=5432 dbname=mydb

[pgbouncer]
pool_mode = transaction
default_pool_size = 20
max_client_conn = 200
```

**Fix 4: Add monitoring for pool usage**

```python
from sqlalchemy import event

@event.listens_for(engine, 'checkout')
def on_checkout(dbapi_conn, connection_rec, connection_proxy):
    pool = engine.pool
    print(f"Pool: size={pool.size()}, "
          f"checked_out={pool.checkedout()}, "
          f"overflow={pool.overflow()}")
```

**Fix 5: Use read replicas for read-heavy workloads**

```python
write_engine = create_engine('postgresql://user:pass@primary:5432/mydb')
read_engine = create_engine('postgresql://user:pass@replica:5432/mydb')

# Route reads to replica, writes to primary
class RoutingSession(Session):
    def get_bind(self, mapper=None, clause=None):
        if self._flushing or self.is_modified():
            return write_engine
        return read_engine
```

**Prevention tips:**
- Set pool_timeout to a low value (5-10 seconds) so requests fail fast instead of queueing
- Monitor pool metrics (checked_out, overflow) in your observability stack
- Use `pool_pre_ping=True` to avoid serving dead connections
- Calculate required pool size: peak_concurrent_requests / num_app_instances
- Set `pool_recycle` to less than PostgreSQL's `idle_session_timeout`'''),

    ("thinking/debugging", r'''Bulk inserting 1 million records takes 45 minutes with SQLAlchemy:

```python
def import_records(records):
    session = Session()
    for record in records:
        obj = MyModel(
            name=record['name'],
            value=record['value'],
            category=record['category'],
        )
        session.add(obj)
    session.commit()
    session.close()
```

This is unacceptably slow. I need it under 2 minutes.''', r'''<think>
Why is this taking 45 minutes for 1 million records? Let me think through all the overhead sources.

My first thought was "the database is slow" -- but inserting 1M rows should take seconds with bulk operations, not 45 minutes. The bottleneck must be on the Python/ORM side.

Let me count the costs per record:
1. Creating an ORM object: Python allocates a new object with __dict__, SQLAlchemy adds it to the identity map, sets up state tracking. That is ~microseconds per object but adds up to seconds for 1M.
2. `session.add(obj)`: registers the object with the unit of work. SQLAlchemy might trigger an autoflush if autoflush is enabled, which would try to flush pending objects.
3. Change tracking: SQLAlchemy compares each object's current state against its original state on flush. For 1M new objects, that is 1M comparisons.
4. SQL generation: without batching, SQLAlchemy generates 1M individual INSERT statements. Each one has to be parsed, planned, and executed by PostgreSQL. That is catastrophically slow compared to a single bulk INSERT.

Wait, actually -- does SQLAlchemy batch INSERTs by default? In older versions (< 2.0), no. Each `session.add()` followed by `session.flush()` executes individual INSERTs. Even without explicit flush, the final `session.commit()` flushes all 1M objects, generating 1M individual INSERT statements. The network round-trip overhead alone (assuming 1ms per query) would be 1000 seconds = ~17 minutes. With server-side parsing, planning, and indexing, 45 minutes is not surprising.

Hmm, I initially thought `executemany_mode` would solve this, but it only helps with the SQL generation -- it batches INSERTs into multi-row VALUES clauses. The ORM overhead of creating 1M objects and tracking them is still there.

The fastest approaches bypass the ORM entirely:
1. PostgreSQL COPY command -- binary protocol, no SQL parsing, fastest possible
2. Core INSERT with `executemany_mode='values_plus_batch'` -- bypasses ORM objects entirely
3. `bulk_insert_mappings` -- still uses ORM table metadata but skips identity map and change tracking
4. Batched `session.add()` with periodic flush/expunge -- slowest but keeps ORM features

I should present these in order from fastest to slowest with benchmarks.
</think>

The slow performance comes from SQLAlchemy's ORM overhead: creating 1 million Python objects, tracking each one in the identity map, and generating individual INSERT statements. Here are the fixes, from fastest to slowest:

**Fix 1: Use Core INSERT with executemany (fastest ORM approach)**

```python
from sqlalchemy import insert

def import_records(records):
    BATCH_SIZE = 10000

    with engine.begin() as conn:
        for i in range(0, len(records), BATCH_SIZE):
            batch = records[i:i + BATCH_SIZE]
            conn.execute(
                insert(MyModel.__table__),
                batch  # list of dicts
            )
```

This bypasses ORM object creation entirely. With `executemany_mode='values_plus_batch'` on the engine, SQLAlchemy batches inserts into multi-row VALUES clauses.

Configure the engine for fast bulk inserts:
```python
engine = create_engine(
    'postgresql://...',
    executemany_mode='values_plus_batch',
    insertmanyvalues_page_size=10000,
)
```

**Fix 2: Use bulk_insert_mappings (still uses ORM but skips tracking)**

```python
def import_records(records):
    BATCH_SIZE = 10000
    session = Session()

    for i in range(0, len(records), BATCH_SIZE):
        batch = records[i:i + BATCH_SIZE]
        session.bulk_insert_mappings(MyModel, batch)
        session.flush()

    session.commit()
    session.close()
```

`bulk_insert_mappings` skips the identity map, change tracking, and relationship cascades. It is 10-50x faster than individual `session.add()`.

**Fix 3: Use PostgreSQL COPY for maximum speed**

```python
import csv
import io

def import_records_copy(records):
    """Fastest possible: uses PostgreSQL COPY protocol."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter='\t')
    for record in records:
        writer.writerow([record['name'], record['value'], record['category']])

    buffer.seek(0)
    raw_conn = engine.raw_connection()
    try:
        cursor = raw_conn.cursor()
        cursor.copy_from(
            buffer,
            'my_model',
            columns=('name', 'value', 'category'),
            sep='\t',
        )
        raw_conn.commit()
    finally:
        raw_conn.close()
```

COPY is the fastest way to load data into PostgreSQL -- it uses a binary protocol optimized for bulk data transfer. 1 million records typically loads in 10-30 seconds.

**Fix 4: Fix the original approach with batching**

If you must use ORM objects (for validation, events, etc.):

```python
def import_records(records):
    BATCH_SIZE = 1000
    session = Session()

    for i, record in enumerate(records):
        obj = MyModel(
            name=record['name'],
            value=record['value'],
            category=record['category'],
        )
        session.add(obj)

        if (i + 1) % BATCH_SIZE == 0:
            session.flush()
            session.expunge_all()  # clear identity map, free memory

    session.commit()
    session.close()
```

**Performance comparison for 1 million records:**
```
Individual session.add():           45 minutes
Batched session.add() + flush:       5 minutes
bulk_insert_mappings():              1 minute
Core INSERT + values_plus_batch:    30 seconds
PostgreSQL COPY:                    10 seconds
```

**Prevention tips:**
- Never use `session.add()` in a loop for bulk operations
- Use Core `insert()` for bulk loads -- skip the ORM overhead
- Batch inserts in groups of 1,000-10,000 rows
- Disable autoflush during bulk operations: `session.autoflush = False`
- Drop indexes before bulk insert, recreate after (if applicable)
- Use `UNLOGGED` tables for temporary staging data in PostgreSQL'''),
]
