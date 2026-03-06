"""Thinking-trace pairs: real-world database debugging scenarios."""

PAIRS = [
    (
        "thinking/debug-postgresql-deadlock",
        r'''We're getting intermittent deadlocks in production. This happens maybe 10 times a day under load. PostgreSQL log:

```
2024-01-15 14:32:01.234 UTC [4521] ERROR:  deadlock detected
DETAIL:  Process 4521 waits for ShareLock on transaction 918234; blocked by process 4518.
Process 4518 waits for ShareLock on transaction 918237; blocked by process 4521.
HINT:  See server log for query details.
CONTEXT:  while updating tuple (42,7) in relation "inventory"
2024-01-15 14:32:01.234 UTC [4521] STATEMENT:  UPDATE inventory SET quantity = quantity - $1 WHERE product_id = $2 AND warehouse_id = $3
```

Our endpoint processes order items:

```python
from sqlalchemy.orm import Session

def fulfill_order(session: Session, order_items: list[dict]):
    """Deduct inventory for each item in the order."""
    for item in order_items:
        row = session.query(Inventory).filter_by(
            product_id=item['product_id'],
            warehouse_id=item['warehouse_id']
        ).with_for_update().one()

        if row.quantity < item['quantity']:
            raise InsufficientStock(item['product_id'])

        row.quantity -= item['quantity']

    session.commit()
```

Two concurrent requests:
- Order A: [product_1 from warehouse_1, product_2 from warehouse_1]
- Order B: [product_2 from warehouse_1, product_1 from warehouse_1]

Why is this deadlocking?''',
        r'''<think>
Classic deadlock pattern. Let me trace the concurrent execution:

Transaction A (Order A):
1. Locks inventory row (product_1, warehouse_1) via FOR UPDATE
2. Tries to lock inventory row (product_2, warehouse_1)

Transaction B (Order B):
1. Locks inventory row (product_2, warehouse_1) via FOR UPDATE
2. Tries to lock inventory row (product_1, warehouse_1)

If the timing is:
1. Txn A locks (product_1, warehouse_1)
2. Txn B locks (product_2, warehouse_1)
3. Txn A tries to lock (product_2, warehouse_1) -- BLOCKED by Txn B
4. Txn B tries to lock (product_1, warehouse_1) -- BLOCKED by Txn A

Deadlock! Neither can proceed.

The root cause is that the two transactions lock the SAME rows but in DIFFERENT ORDERS. If both transactions locked in the same order (e.g., sorted by product_id), they would never deadlock -- one would wait for the other, but never circularly.

The fix is simple: sort the items by a consistent key before processing.

There are also alternative approaches:
- Use a single UPDATE with WHERE ... IN (...) to lock all rows atomically
- Use advisory locks
- Use SKIP LOCKED for queue-style processing
</think>

## Root Cause: Lock Ordering Violation

This is a textbook deadlock caused by two transactions acquiring row-level locks in opposite orders.

**Timeline:**

| Step | Transaction A (Order A) | Transaction B (Order B) |
|------|------------------------|------------------------|
| 1 | `LOCK (product_1, wh_1)` -- acquired | `LOCK (product_2, wh_1)` -- acquired |
| 2 | `LOCK (product_2, wh_1)` -- BLOCKED by B | `LOCK (product_1, wh_1)` -- BLOCKED by A |
| 3 | **DEADLOCK** | **DEADLOCK** |

PostgreSQL detects the circular wait after `deadlock_timeout` (default 1 second) and kills one transaction.

## The Fix: Consistent Lock Ordering

Sort items by a deterministic key before locking. If all transactions lock rows in the same order, circular waits are impossible.

```python
def fulfill_order(session: Session, order_items: list[dict]):
    """Deduct inventory for each item in the order.
    Sort by (product_id, warehouse_id) to prevent deadlocks.
    """
    # CRITICAL: Sort to ensure consistent lock ordering across all transactions
    sorted_items = sorted(order_items, key=lambda x: (x['product_id'], x['warehouse_id']))

    for item in sorted_items:
        row = session.query(Inventory).filter_by(
            product_id=item['product_id'],
            warehouse_id=item['warehouse_id']
        ).with_for_update().one()

        if row.quantity < item['quantity']:
            raise InsufficientStock(item['product_id'])

        row.quantity -= item['quantity']

    session.commit()
```

Now both Transaction A and B will lock `(product_1, wh_1)` first, then `(product_2, wh_1)`. One will wait for the other, but no circular dependency.

## Alternative: Single Bulk UPDATE

For better performance under high contention, lock all rows at once:

```python
def fulfill_order(session: Session, order_items: list[dict]):
    """Lock all rows in a single query to minimize lock duration."""
    product_warehouse_pairs = [
        (item['product_id'], item['warehouse_id']) for item in order_items
    ]

    # Lock all needed rows in one shot (PostgreSQL sorts internally)
    rows = (
        session.query(Inventory)
        .filter(
            tuple_(Inventory.product_id, Inventory.warehouse_id)
            .in_(product_warehouse_pairs)
        )
        .with_for_update()
        .order_by(Inventory.product_id, Inventory.warehouse_id)
        .all()
    )

    # Build lookup for fast access
    inventory_map = {(r.product_id, r.warehouse_id): r for r in rows}

    for item in order_items:
        key = (item['product_id'], item['warehouse_id'])
        row = inventory_map.get(key)
        if row is None or row.quantity < item['quantity']:
            raise InsufficientStock(item['product_id'])
        row.quantity -= item['quantity']

    session.commit()
```

This is faster because:
1. One round-trip to the database instead of N
2. All locks acquired atomically -- no window for interleaving
3. The `ORDER BY` ensures PostgreSQL acquires locks in a consistent order

## Prevention Checklist

1. **Always sort before locking.** Any code that locks multiple rows in a loop must sort by primary key first.
2. **Keep transactions short.** Don't do HTTP calls or heavy computation while holding locks.
3. **Set `lock_timeout`** to fail fast instead of waiting forever: `SET lock_timeout = '5s'`
4. **Monitor with `pg_stat_activity`**: `SELECT * FROM pg_stat_activity WHERE wait_event_type = 'Lock'`
5. **Consider `SERIALIZABLE` isolation level** for critical sections -- PostgreSQL will automatically detect conflicts and retry, but you must handle serialization failures in your application.''',
    ),
    (
        "thinking/debug-n-plus-1-query",
        r'''Our API endpoint that returns a list of 50 blog posts with author info takes 3.2 seconds. Profiling shows 51 database queries for a single request. Here's the SQLAlchemy debug log:

```
INFO sqlalchemy.engine.Engine SELECT posts.id, posts.title, posts.body, posts.author_id, posts.created_at FROM posts ORDER BY posts.created_at DESC LIMIT 50
INFO sqlalchemy.engine.Engine SELECT users.id, users.name, users.avatar_url FROM users WHERE users.id = %(pk)s
INFO sqlalchemy.engine.Engine {'pk': 7}
INFO sqlalchemy.engine.Engine SELECT users.id, users.name, users.avatar_url FROM users WHERE users.id = %(pk)s
INFO sqlalchemy.engine.Engine {'pk': 3}
INFO sqlalchemy.engine.Engine SELECT users.id, users.name, users.avatar_url FROM users WHERE users.id = %(pk)s
INFO sqlalchemy.engine.Engine {'pk': 7}
... (48 more identical SELECT users queries)
```

Models and endpoint:

```python
class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    name = Column(String)
    avatar_url = Column(String)

class Post(Base):
    __tablename__ = 'posts'
    id = Column(Integer, primary_key=True)
    title = Column(String)
    body = Column(Text)
    author_id = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime)
    author = relationship('User')

@app.get('/api/posts')
def list_posts():
    posts = db.session.query(Post).order_by(Post.created_at.desc()).limit(50).all()
    return jsonify([{
        'id': p.id,
        'title': p.title,
        'author': {'name': p.author.name, 'avatar': p.author.avatar_url},
        'created_at': p.created_at.isoformat()
    } for p in posts])
```

Why 51 queries for 50 posts?''',
        r'''<think>
This is the classic N+1 query problem.

Query 1: `SELECT * FROM posts LIMIT 50` -- fetches 50 posts
Queries 2-51: For each post, when `p.author.name` is accessed, SQLAlchemy lazy-loads the author with a separate query: `SELECT * FROM users WHERE id = ?`

That's 1 + 50 = 51 queries. Even though some authors are the same (user 7 appears multiple times), SQLAlchemy's default lazy loading doesn't cache across different relationship accesses within the same query -- actually, it does use the identity map, so if user 7 is already loaded, accessing it again won't fire a query. But looking at the log, user 7 IS queried twice. That's because the identity map lookup happens, but the log shows it was queried before the map was populated.

Wait, actually SQLAlchemy DOES use the identity map. If user 7 was loaded in the first `SELECT users WHERE id=7`, then the second access to a post with author_id=7 should hit the identity map and NOT fire a query. The log shows user 7 queried twice, which suggests either: (a) the session was configured with `expire_on_commit=True` and there was a commit between accesses, or (b) I'm reading the log wrong.

Regardless, the fix is the same: use eager loading to fetch all authors in one query.
</think>

## Root Cause: N+1 Query Problem

This is the most common ORM performance anti-pattern. Here's what happens:

1. **Query 1**: `SELECT * FROM posts ORDER BY created_at DESC LIMIT 50` -- loads 50 posts
2. **Queries 2-51**: For each post, accessing `p.author.name` triggers a **lazy load** -- SQLAlchemy fires `SELECT * FROM users WHERE id = ?` for each post individually

SQLAlchemy's `relationship('User')` defaults to `lazy='select'`, meaning the related object is loaded on first access with a separate query.

Result: 1 + N queries where N = number of posts = 51 queries, each with its own round-trip to the database. At ~60ms per round-trip on a cloud database, that's 3+ seconds.

## The Fix: Eager Loading

**Option 1: `joinedload` (single query with JOIN)**

```python
from sqlalchemy.orm import joinedload

@app.get('/api/posts')
def list_posts():
    posts = (
        db.session.query(Post)
        .options(joinedload(Post.author))  # JOIN users in the same query
        .order_by(Post.created_at.desc())
        .limit(50)
        .all()
    )
    return jsonify([{
        'id': p.id,
        'title': p.title,
        'author': {'name': p.author.name, 'avatar': p.author.avatar_url},
        'created_at': p.created_at.isoformat()
    } for p in posts])
```

This generates ONE query:
```sql
SELECT posts.*, users.* FROM posts
LEFT JOIN users ON posts.author_id = users.id
ORDER BY posts.created_at DESC LIMIT 50
```

**Option 2: `subqueryload` (two queries total)**

```python
from sqlalchemy.orm import subqueryload

posts = (
    db.session.query(Post)
    .options(subqueryload(Post.author))
    .order_by(Post.created_at.desc())
    .limit(50)
    .all()
)
```

This generates TWO queries:
```sql
SELECT * FROM posts ORDER BY created_at DESC LIMIT 50;
SELECT * FROM users WHERE id IN (7, 3, 12, 5, ...);  -- all unique author_ids
```

**Option 3: `selectinload` (preferred for collections)**

```python
from sqlalchemy.orm import selectinload

posts = (
    db.session.query(Post)
    .options(selectinload(Post.author))
    .order_by(Post.created_at.desc())
    .limit(50)
    .all()
)
```

Similar to `subqueryload` but uses `WHERE id IN (...)` instead of a subquery. Generally the best default for modern PostgreSQL.

## Which to Use?

| Strategy | Queries | Best For |
|----------|---------|----------|
| `joinedload` | 1 | Many-to-one (like post -> author). Small related tables. |
| `selectinload` | 2 | One-to-many (like author -> posts). Large result sets. |
| `subqueryload` | 2 | Same as selectinload, but works better with complex filters. |

For your case (many posts, each with one author), `joinedload` is ideal -- single query, no duplication of post data.

## Make It the Default

You can set eager loading at the model level so you never forget:

```python
class Post(Base):
    __tablename__ = 'posts'
    # ...
    author = relationship('User', lazy='joined')  # Always eager load
```

Or use SQLAlchemy 2.0's `Mapped` style with `lazy` default:

```python
class Post(Base):
    __tablename__ = 'posts'
    author: Mapped[User] = relationship(lazy='selectin')
```

## Detection & Prevention

1. **Enable query counting in tests:**
```python
from sqlalchemy import event

@contextmanager
def assert_query_count(session, expected):
    count = [0]
    def counter(conn, cursor, statement, *args):
        count[0] += 1
    event.listen(session.bind, 'before_cursor_execute', counter)
    yield
    event.remove(session.bind, 'before_cursor_execute', counter)
    assert count[0] <= expected, f"Expected <= {expected} queries, got {count[0]}"

# In your test:
with assert_query_count(db.session, 2):
    client.get('/api/posts')
```

2. **Use `nplusone` library** to auto-detect N+1 queries in development:
```python
pip install nplusone
# In Flask config:
NPLUSONE_RAISE = True  # Raises exception on N+1 in development
```

3. **Performance budget:** An endpoint returning a list should NEVER fire more queries than `O(number_of_relationships)`, not `O(number_of_rows)`.''',
    ),
    (
        "thinking/debug-connection-pool-exhaustion",
        r'''Our Python web service becomes unresponsive under moderate load (50 concurrent users). The health check starts timing out, and we see this in the logs:

```
2024-03-10 09:15:42 WARNING sqlalchemy.pool.impl.QueuePool Connection pool exhausted, connection request timed out after 30.00 seconds
2024-03-10 09:15:42 ERROR app.api TimeoutError in /api/reports/generate
Traceback (most recent call last):
  File "app/api/reports.py", line 45, in generate_report
    data = db.session.execute(text(query))
  File "sqlalchemy/engine/base.py", line 1412, in execute
    conn = self._connection_for_bind(engine)
sqlalchemy.exc.TimeoutError: QueuePool limit of size 5 overflow 10 reached, connection timed out, timeout 30.0
```

```
2024-03-10 09:15:43 INFO sqlalchemy.pool Checked out connections: 15, pool size: 5, overflow: 10
```

Config:
```python
app.config['SQLALCHEMY_DATABASE_URI'] = 'postgresql://...'
app.config['SQLALCHEMY_POOL_SIZE'] = 5
app.config['SQLALCHEMY_MAX_OVERFLOW'] = 10
# Using gunicorn with 4 workers, 8 threads each
```

The report generation endpoint:
```python
@app.route('/api/reports/generate', methods=['POST'])
def generate_report():
    report_type = request.json['type']
    params = request.json['params']

    # Fetch data
    data = db.session.execute(text(QUERIES[report_type]), params).fetchall()

    # Generate PDF (CPU-intensive, takes 5-30 seconds)
    pdf_bytes = render_pdf(data, report_type)

    # Save to S3
    s3_url = upload_to_s3(pdf_bytes, f"reports/{uuid4()}.pdf")

    # Save report record
    report = Report(type=report_type, url=s3_url, user_id=g.user.id)
    db.session.add(report)
    db.session.commit()

    return jsonify({'url': s3_url})
```

We bumped pool_size to 20 but the problem just comes back at slightly higher load. What's the real issue?''',
        r'''<think>
Let me trace the connection lifecycle in this endpoint:

1. `db.session.execute(...)` -- checks out a connection from the pool
2. `render_pdf(data, report_type)` -- CPU-intensive, takes 5-30 seconds. THE CONNECTION IS STILL CHECKED OUT during this entire time because the session is still active.
3. `upload_to_s3(...)` -- network I/O, could take seconds. Connection still held.
4. `db.session.add(report)` / `db.session.commit()` -- uses the connection again.

So the connection is held for the entire duration of the request, which is dominated by PDF rendering (5-30 seconds) and S3 upload. The database operations themselves might take <100ms but the connection is occupied for 5-30 seconds.

With pool_size=5 and max_overflow=10, that's 15 connections max. With 4 gunicorn workers, each worker has its own pool, so 15 * 4 = 60 connections total. But each worker has 8 threads, so 32 concurrent requests per worker. If each holds a connection for 15 seconds average, a worker can only process 15/15 = 1 request per second... actually let me think about this differently.

Per worker: 15 connections available, each held for ~15 seconds. That means the pool can handle 15 concurrent report generations. With 8 threads, if all 8 are generating reports simultaneously, 8 < 15, so it should work... unless there are more than 15 concurrent requests queued up.

Actually, with 4 workers * 8 threads = 32 possible concurrent requests. Each worker has 15 connections. If all 8 threads in a worker are generating reports, that's 8 connections held for 15+ seconds. That's fine for one burst, but with steady load, new requests queue up and wait for connections.

The real issue: connections are held far longer than needed. The DB work is <100ms but the connection is held for the entire request lifecycle (5-30 seconds). The fix is to NOT hold the connection while doing PDF rendering and S3 upload.
</think>

## Root Cause: Connection Held During Non-Database Work

The database connection is checked out at step 1 (`db.session.execute`) and not released until `db.session.commit()` at step 4. But between those two database operations, the connection sits idle for 5-30 seconds while:

- `render_pdf()` burns CPU for 5-30 seconds
- `upload_to_s3()` does network I/O for 1-5 seconds

**Your connections are held for 6-35 seconds but only actively used for ~100ms.** That's 99.5% idle connection time.

With `pool_size=5 + max_overflow=10 = 15` connections per worker and 8 threads per worker, only 15 concurrent report requests can be processed before the pool is exhausted. At 15 seconds average per request, your throughput is roughly 1 report/second per worker.

Bumping pool size just delays the inevitable -- you'd need `pool_size` equal to your max concurrency, which means hundreds of database connections. PostgreSQL defaults to `max_connections=100` and each connection costs ~10MB of RAM.

## The Fix: Release the Connection Between Database Operations

```python
@app.route('/api/reports/generate', methods=['POST'])
def generate_report():
    report_type = request.json['type']
    params = request.json['params']

    # Step 1: Fetch data and IMMEDIATELY release the connection
    data = db.session.execute(text(QUERIES[report_type]), params).fetchall()
    db.session.close()  # Returns connection to pool

    # Step 2: CPU-heavy work -- NO connection held
    pdf_bytes = render_pdf(data, report_type)

    # Step 3: Network I/O -- NO connection held
    s3_url = upload_to_s3(pdf_bytes, f"reports/{uuid4()}.pdf")

    # Step 4: Quick DB write -- checks out connection, uses it, releases it
    report = Report(type=report_type, url=s3_url, user_id=g.user.id)
    db.session.add(report)
    db.session.commit()
    # Flask-SQLAlchemy auto-closes session at end of request

    return jsonify({'url': s3_url})
```

**The key change:** `db.session.close()` after fetching data returns the connection to the pool immediately. The session will transparently check out a new connection when `db.session.add()` is called later. Each checkout now lasts milliseconds, not minutes.

## Even Better: Move Heavy Work to a Task Queue

Report generation shouldn't block the request at all:

```python
# api/reports.py
from celery_app import generate_report_task

@app.route('/api/reports/generate', methods=['POST'])
def generate_report():
    report_type = request.json['type']
    params = request.json['params']

    # Queue the work -- returns immediately
    task = generate_report_task.delay(report_type, params, g.user.id)
    return jsonify({'task_id': task.id, 'status': 'pending'}), 202

# tasks.py
@celery.task(bind=True)
def generate_report_task(self, report_type, params, user_id):
    # This runs in a Celery worker, not in the web process
    with db_session() as session:
        data = session.execute(text(QUERIES[report_type]), params).fetchall()

    pdf_bytes = render_pdf(data, report_type)
    s3_url = upload_to_s3(pdf_bytes, f"reports/{uuid4()}.pdf")

    with db_session() as session:
        report = Report(type=report_type, url=s3_url, user_id=user_id)
        session.add(report)
        session.commit()

    return {'url': s3_url}
```

## Right-Sizing the Pool

After fixing connection hold times, calculate the actual pool size needed:

```
pool_size = max_concurrent_requests_per_worker * avg_db_time / avg_request_time
```

If each worker handles 8 concurrent requests, each request does ~100ms of DB work over a 1-second total request time, you need: `8 * 0.1 / 1.0 = ~1 connection`. A `pool_size=5` is already generous.

## Configuration Recommendations

```python
app.config.update(
    SQLALCHEMY_POOL_SIZE=5,          # Base connections per worker
    SQLALCHEMY_MAX_OVERFLOW=5,       # Allow 5 more under burst
    SQLALCHEMY_POOL_TIMEOUT=10,      # Fail fast, don't wait 30s
    SQLALCHEMY_POOL_RECYCLE=1800,    # Recycle connections every 30min
    SQLALCHEMY_POOL_PRE_PING=True,   # Verify connections aren't stale
)
```

And in PostgreSQL, make sure `max_connections` accommodates all workers: `4 workers * 10 connections = 40`. Add margin for migrations, monitoring, and admin connections -- set to ~60.''',
    ),
    (
        "thinking/debug-detached-instance-sqlalchemy",
        r'''I'm getting this error when I try to access a relationship after returning from a service function:

```
Traceback (most recent call last):
  File "app/api/users.py", line 23, in get_user_profile
    return jsonify({
  File "app/api/users.py", line 26, in <dictcomp>
    'team_name': user.team.name,
  File "sqlalchemy/orm/attributes.py", line 481, in __get__
    return self.impl.get(instance_state(instance), dict_)
  File "sqlalchemy/orm/attributes.py", line 944, in get
    value = self._fire_loader_callables(state, key, passive)
sqlalchemy.orm.exc.DetachedInstanceError: Parent instance <User at 0x7f...> is not bound to a Session; lazy load operation of attribute 'team' cannot proceed

(Background on this error at: https://sqlalche.me/e/14/bhk3)
```

Code:

```python
# app/services/user_service.py
from app.models import User
from app.database import SessionLocal

def get_user_by_id(user_id: int) -> User:
    with SessionLocal() as session:
        user = session.query(User).filter_by(id=user_id).first()
        return user  # session closes here when 'with' block exits

# app/api/users.py
from app.services.user_service import get_user_by_id

@app.get('/api/users/<int:user_id>')
def get_user_profile(user_id):
    user = get_user_by_id(user_id)
    if not user:
        abort(404)
    return jsonify({
        'id': user.id,
        'name': user.name,
        'team_name': user.team.name,  # CRASHES HERE
    })
```

Why can't I access `user.team` if the user object was successfully loaded?''',
        r'''<think>
The issue is clear: the `with SessionLocal() as session:` block closes the session when the function returns. The `User` object is now "detached" -- it exists in memory but is no longer associated with a session.

When the API layer accesses `user.team`, SQLAlchemy needs to lazy-load the `team` relationship, which requires a database query, which requires a session. Since the user is detached, there's no session to query through.

Scalar attributes like `user.id` and `user.name` work because they were loaded when the user was fetched. But `user.team` was never loaded (lazy loading), so it's a proxy that needs to fire a query.

Several fixes:
1. Eager load the team in the service function
2. Keep the session alive longer (scoped session per request)
3. Use `expire_on_commit=False` and eager load
4. Return a DTO/dict instead of the ORM object
</think>

## Root Cause: Session Closed Before Lazy Load

SQLAlchemy ORM objects are bound to the session that loaded them. When you access a lazy-loaded relationship like `user.team`, SQLAlchemy needs to fire a SQL query, which requires an active session.

In your code:

```python
def get_user_by_id(user_id: int) -> User:
    with SessionLocal() as session:
        user = session.query(User).filter_by(id=user_id).first()
        return user  # <-- session closes here, user becomes "detached"
```

The `user` object is returned AFTER the `with` block exits and the session is closed. The user's scalar attributes (`id`, `name`) are already in memory, but `team` is a relationship proxy that hasn't been loaded yet. When the API layer accesses `user.team.name`, SQLAlchemy tries to lazy-load it and fails because there's no session.

## Fix 1: Eager Load in the Service Layer (Recommended)

Load everything you need BEFORE the session closes:

```python
from sqlalchemy.orm import joinedload

def get_user_by_id(user_id: int) -> User:
    with SessionLocal() as session:
        user = (
            session.query(User)
            .options(joinedload(User.team))  # Load team in the same query
            .filter_by(id=user_id)
            .first()
        )
        # Expunge so the object can live outside the session
        if user:
            session.expunge(user)
        return user
```

Now `user.team` is already loaded in memory. `session.expunge(user)` formally detaches the user from the session, making it clear this is intentional. Accessing `user.team.name` works because the data is already populated.

## Fix 2: Request-Scoped Session (Flask Pattern)

Instead of creating a session per service call, use one session per HTTP request:

```python
# app/database.py
from flask import g

def get_db():
    if 'db' not in g:
        g.db = SessionLocal()
    return g.db

@app.teardown_appcontext
def close_db(exception):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# app/services/user_service.py
def get_user_by_id(user_id: int) -> User:
    session = get_db()  # Same session for the entire request
    return session.query(User).filter_by(id=user_id).first()

# app/api/users.py
@app.get('/api/users/<int:user_id>')
def get_user_profile(user_id):
    user = get_user_by_id(user_id)
    # Session is still open, lazy loading works
    return jsonify({
        'id': user.id,
        'name': user.name,
        'team_name': user.team.name,  # Works! Session still active
    })
    # Session closed in teardown_appcontext
```

This is how Flask-SQLAlchemy works internally -- one session per request, closed in teardown.

## Fix 3: Return DTOs Instead of ORM Objects

Don't leak ORM objects outside the service layer:

```python
from dataclasses import dataclass

@dataclass
class UserProfile:
    id: int
    name: str
    team_name: str | None

def get_user_by_id(user_id: int) -> UserProfile | None:
    with SessionLocal() as session:
        user = (
            session.query(User)
            .options(joinedload(User.team))
            .filter_by(id=user_id)
            .first()
        )
        if user is None:
            return None
        return UserProfile(
            id=user.id,
            name=user.name,
            team_name=user.team.name if user.team else None,
        )
```

This is the cleanest approach for APIs -- the service layer controls exactly what data is loaded and exposed.

## Anti-Pattern: Don't Do This

```python
# DON'T: expire_on_commit=False doesn't fix this
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)
```

`expire_on_commit=False` only prevents re-loading attributes after `commit()`. It does NOT help with lazy-loading relationships after session closure. You'll still get `DetachedInstanceError`.

## When Each Fix Is Appropriate

| Scenario | Best Fix |
|----------|----------|
| Flask/Django web app | Request-scoped session (Fix 2) |
| FastAPI with Pydantic | DTOs / response models (Fix 3) |
| Background jobs / scripts | Eager load + expunge (Fix 1) |
| Complex service layer | DTOs (Fix 3) -- cleanest separation |''',
    ),
    (
        "thinking/debug-migration-failure-mid-deploy",
        r'''We deployed a database migration and it failed halfway. Now the app is broken and we can't roll back cleanly. Here's what happened:

```
$ alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade abc123 -> def456, Add user preferences
INFO  [alembic.runtime.migration] Running upgrade def456 -> ghi789, Restructure orders table

  Applying ghi789...
  ALTER TABLE orders ADD COLUMN shipping_address_id INTEGER;
  OK
  ALTER TABLE orders DROP COLUMN shipping_street;
  OK
  ALTER TABLE orders DROP COLUMN shipping_city;
  OK
  UPDATE orders SET shipping_address_id = (SELECT id FROM addresses WHERE ...);
  ERROR: column "shipping_state" does not exist

sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn) column "shipping_state" does not exist
```

Current state:
- Migration `def456` (user preferences) applied successfully
- Migration `ghi789` (restructure orders) PARTIALLY applied:
  - `shipping_address_id` column was added
  - `shipping_street` was DROPPED
  - `shipping_city` was DROPPED
  - Data migration UPDATE failed (referenced `shipping_state` which had a typo -- should be `shipping_state_province`)
- Old code expects `shipping_street` and `shipping_city` columns (they're gone)
- New code expects `shipping_address_id` to be populated (it's empty)

The app is down. How do I recover?''',
        r'''<think>
This is a production incident. The migration partially applied destructive DDL (dropping columns) before the data migration step failed. The state is:

Current DB state:
- `shipping_address_id` exists (added) but is NULL
- `shipping_street` is GONE (dropped)
- `shipping_city` is GONE (dropped)
- `shipping_state_province` still exists (the UPDATE that referenced "shipping_state" failed before touching it)

The alembic_version table shows either `def456` (if the failed migration rolled back its version bump) or is in an inconsistent state.

PostgreSQL wraps DDL in transactions, so in theory the entire migration should have rolled back. BUT -- the user says columns are actually dropped, which means either:
1. The migration used `autocommit=True` or individual transactions per statement
2. The migration had multiple transaction blocks
3. They're using a setup where each DDL statement auto-commits

Actually, by default Alembic runs in a transaction. PostgreSQL DOES support transactional DDL (unlike MySQL), so the entire migration SHOULD have rolled back atomically. If it didn't, the migration probably used `connection.execution_options(isolation_level="AUTOCOMMIT")` or had explicit `op.execute("COMMIT")` calls.

Let me address both the immediate recovery and the prevention.

Recovery plan:
1. Assess actual DB state
2. Manually restore dropped columns from backup or pg_dump
3. Fix the alembic version stamp
4. Fix the migration script
5. Re-run
</think>

## Immediate Recovery Plan

**Step 1: Assess the actual database state**

```sql
-- Check what columns currently exist on orders
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'orders'
ORDER BY ordinal_position;

-- Check alembic's recorded version
SELECT * FROM alembic_version;
```

**Step 2: Restore the dropped columns**

If you have a recent backup (you should -- always backup before migrations):

```sql
-- Restore from backup using pg_restore targeted at just the data
-- First, add the columns back with their original types
ALTER TABLE orders ADD COLUMN shipping_street VARCHAR(255);
ALTER TABLE orders ADD COLUMN shipping_city VARCHAR(100);

-- Restore data from backup
-- Option A: If you have a logical backup
pg_restore --data-only --table=orders -d yourdb backup.dump

-- Option B: Copy from a backup database
INSERT INTO orders (id, shipping_street, shipping_city)
SELECT id, shipping_street, shipping_city FROM backup_db.orders
ON CONFLICT (id) DO UPDATE SET
    shipping_street = EXCLUDED.shipping_street,
    shipping_city = EXCLUDED.shipping_city;
```

If you don't have a backup (this is bad), you may need to reconstruct from application logs, audit tables, or S3 backups.

**Step 3: Remove the partially-applied changes**

```sql
-- Remove the column that was added by the failed migration
ALTER TABLE orders DROP COLUMN IF EXISTS shipping_address_id;
```

**Step 4: Stamp alembic back to the last good state**

```bash
# Tell alembic the DB is at the pre-failure version
alembic stamp def456
```

**Step 5: Verify the app works with the restored state**

Deploy the OLD code (before the migration) and confirm the app is functional.

## Root Cause: Destructive DDL Before Data Validation

The migration dropped columns (`shipping_street`, `shipping_city`) BEFORE successfully migrating the data. When the data migration failed, the old data was already destroyed.

Additionally, PostgreSQL supports transactional DDL, so the entire migration SHOULD have rolled back automatically. The fact that it didn't means your migration likely broke the transaction boundary. Common causes:

```python
# These break transactional DDL in Alembic:
op.execute("COMMIT")  # Explicit commit mid-migration
connection.execution_options(isolation_level="AUTOCOMMIT")
# Or: running with transaction_per_migration=False
```

## Fix the Migration (Safe Pattern)

```python
"""Restructure orders table - safe version."""

def upgrade():
    # Phase 1: ADD new columns (non-destructive)
    op.add_column('orders', sa.Column('shipping_address_id', sa.Integer()))

    # Phase 2: MIGRATE data (before dropping anything!)
    op.execute("""
        UPDATE orders
        SET shipping_address_id = (
            SELECT a.id FROM addresses a
            WHERE a.street = orders.shipping_street
            AND a.city = orders.shipping_city
            AND a.state_province = orders.shipping_state_province
        )
    """)

    # Phase 3: VALIDATE data migration succeeded
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM orders
                WHERE shipping_street IS NOT NULL
                AND shipping_address_id IS NULL
            ) THEN
                RAISE EXCEPTION 'Data migration incomplete: orders exist with street but no address_id';
            END IF;
        END $$;
    """)

    # Phase 4: Only NOW drop old columns (data is safely migrated)
    op.drop_column('orders', 'shipping_street')
    op.drop_column('orders', 'shipping_city')
    op.drop_column('orders', 'shipping_state_province')

def downgrade():
    # Restore columns
    op.add_column('orders', sa.Column('shipping_state_province', sa.String(100)))
    op.add_column('orders', sa.Column('shipping_city', sa.String(100)))
    op.add_column('orders', sa.Column('shipping_street', sa.String(255)))

    # Restore data from addresses
    op.execute("""
        UPDATE orders SET
            shipping_street = a.street,
            shipping_city = a.city,
            shipping_state_province = a.state_province
        FROM addresses a WHERE a.id = orders.shipping_address_id
    """)

    op.drop_column('orders', 'shipping_address_id')
```

## Prevention: Multi-Phase Migration Strategy

For destructive schema changes, split into separate deploy phases:

**Deploy 1: Add new structure (backward-compatible)**
```python
def upgrade():
    op.add_column('orders', sa.Column('shipping_address_id', sa.Integer()))
    # Old code still works -- old columns still exist
```

**Deploy 2: Backfill data + update code**
```python
# Migration: backfill shipping_address_id from old columns
# Code: read from shipping_address_id, fall back to old columns
```

**Deploy 3: Drop old columns (after validating new code works)**
```python
def upgrade():
    op.drop_column('orders', 'shipping_street')
    op.drop_column('orders', 'shipping_city')
    op.drop_column('orders', 'shipping_state_province')
```

## Deployment Checklist

1. **Always backup before migrations**: `pg_dump -Fc yourdb > pre_migration_$(date +%s).dump`
2. **Test migrations against a copy of production data**, not just an empty test database
3. **Never drop columns in the same migration that adds their replacements**
4. **Ensure transactional DDL is enabled** (default in Alembic + PostgreSQL)
5. **Add validation queries** that abort the migration if data migration was incomplete
6. **Write downgrades** for every migration, and test them''',
    ),
]
