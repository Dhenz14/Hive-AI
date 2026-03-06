r"""Thinking-trace pairs: SQLAlchemy code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this SQLAlchemy code and identify issues:

```python
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, DateTime
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from datetime import datetime

engine = create_engine('postgresql://user:pass@localhost/mydb')
Session = sessionmaker(bind=engine)
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String(50))
    email = Column(String(100))
    orders = relationship('Order', backref='user')

class Product(Base):
    __tablename__ = 'products'
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    price = Column(Float)
    stock = Column(Integer)

class Order(Base):
    __tablename__ = 'orders'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    created_at = Column(DateTime, default=datetime.now)
    total = Column(Float)
    items = relationship('OrderItem', backref='order')

class OrderItem(Base):
    __tablename__ = 'order_items'
    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('orders.id'))
    product_id = Column(Integer, ForeignKey('products.id'))
    quantity = Column(Integer)
    price = Column(Float)

def create_order(user_id, items):
    session = Session()
    user = session.query(User).get(user_id)
    order = Order(user_id=user_id, total=0)
    session.add(order)

    total = 0
    for item in items:
        product = session.query(Product).get(item['product_id'])
        if product.stock < item['quantity']:
            raise ValueError(f"Not enough stock for {product.name}")
        product.stock -= item['quantity']
        order_item = OrderItem(
            order=order,
            product_id=product.id,
            quantity=item['quantity'],
            price=product.price,
        )
        session.add(order_item)
        total += product.price * item['quantity']

    order.total = total
    session.commit()
    return order

def get_user_orders(user_id):
    session = Session()
    user = session.query(User).get(user_id)
    orders = []
    for order in user.orders:
        order_data = {
            'id': order.id,
            'total': order.total,
            'items': []
        }
        for item in order.items:
            product = session.query(Product).get(item.product_id)
            order_data['items'].append({
                'product': product.name,
                'quantity': item.quantity,
                'price': item.price,
            })
        orders.append(order_data)
    return orders

def search_products(name=None, min_price=None, max_price=None):
    session = Session()
    query = session.query(Product)
    if name:
        query = query.filter(Product.name.like(f'%{name}%'))
    if min_price:
        query = query.filter(Product.price >= min_price)
    if max_price:
        query = query.filter(Product.price <= max_price)
    return query.all()
```''', r'''<think>
Let me review this SQLAlchemy code for session management, query optimization, relationship design, and correctness issues.

1. Session management:
- Every function creates a new Session() but never closes it. This leaks database connections.
- create_order creates a session but if the ValueError is raised (not enough stock), the session is never rolled back or closed. The session is left in a dirty state.
- No context manager pattern for sessions. Should use try/finally or a context manager.
- Sessions are created in function scope, meaning detached objects are returned (order returned from create_order is detached after function returns if session is garbage collected).

2. N+1 queries in get_user_orders:
- user.orders triggers a lazy load (1 query)
- For each order, order.items triggers another lazy load (N queries)
- For each item, session.query(Product).get(item.product_id) is yet another query (M queries per order)
- Total: 1 + N + sum(items per order) queries. Should use eager loading.

3. Race conditions in create_order:
- product.stock check and decrement is not atomic. Two concurrent orders can both check stock > quantity and both succeed, resulting in negative stock.
- No SELECT FOR UPDATE or similar locking mechanism.

4. Model issues:
- datetime.now is called once at class definition time, not per-row. The default value is a fixed timestamp. Should be datetime.now (without calling) or use server_default.
  Wait, actually in SQLAlchemy, `default=datetime.now` (without parentheses) passes the function itself, which gets called each time. But the code has `default=datetime.now` -- actually looking again, it says `datetime.now` which IS the function reference. But wait -- it does NOT have parentheses, so this is correct. Let me re-read... `default=datetime.now` -- yes this is the function reference, so it's actually fine. No, wait -- I see `default=datetime.now` -- if there are no parentheses, it passes the function and SQLAlchemy calls it on each insert. That's correct. Let me look more carefully... The code says `default=datetime.now`. This is correct as a Python-side default.
  Actually, on re-reading, it could be `datetime.now()` with parens. Let me check again: `default=datetime.now`. No parens. This is correct.

5. Float for money:
- Using Float for price and total is a classic mistake. Floating point cannot represent decimal values exactly. $19.99 might become $19.990000000000002. Use Numeric/Decimal.

6. Missing constraints:
- username and email have no unique constraints
- No NOT NULL constraints on critical fields
- No indexes on foreign keys or frequently queried columns

7. search_products:
- `if min_price:` evaluates to False when min_price is 0, skipping a valid filter. Should be `if min_price is not None:`.
- Returns SQLAlchemy model instances that are bound to a session that might be garbage collected.

Let me structure the review.
</think>

## Code Review: SQLAlchemy Order Management

### CRITICAL - Session Management

**SM1: Sessions never closed (Severity: CRITICAL)**
Every function creates `Session()` but never calls `session.close()`. This leaks database connections. Under load, the connection pool is exhausted and the application hangs.

**SM2: No rollback on error in create_order (Severity: CRITICAL)**
If `ValueError` is raised for insufficient stock, the session has uncommitted changes (added order, modified products). The session is never rolled back. Depending on garbage collection timing, this dirty session may cause issues.

Fix: Use a context manager:
```python
def create_order(user_id, items):
    session = Session()
    try:
        # ... business logic ...
        session.commit()
        return order
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

### CRITICAL - Race Condition

**RC1: Non-atomic stock check and decrement (Severity: CRITICAL)**
```python
if product.stock < item['quantity']:
    raise ValueError(...)
product.stock -= item['quantity']
```
Two concurrent orders both read stock=5, both see 5 >= 3, both set stock=2. Actual stock should be -1. Use SELECT FOR UPDATE:
```python
product = session.query(Product).with_for_update().get(item['product_id'])
```
Or use an atomic update with a CHECK constraint:
```python
result = session.execute(
    update(Product)
    .where(Product.id == item['product_id'])
    .where(Product.stock >= item['quantity'])
    .values(stock=Product.stock - item['quantity'])
)
if result.rowcount == 0:
    raise ValueError("Not enough stock")
```

### HIGH - N+1 Queries

**Q1: get_user_orders has cascading lazy loads (Severity: HIGH)**
For a user with 10 orders, each with 5 items:
- 1 query for user
- 1 lazy load for user.orders (10 results)
- 10 lazy loads for order.items (5 items each)
- 50 queries for Product.get() per item
Total: 62 queries. Fix with eager loading:
```python
user = session.query(User).options(
    joinedload(User.orders)
    .joinedload(Order.items)
    .joinedload(OrderItem.product)
).get(user_id)
```

### HIGH - Data Types

**DT1: Float used for monetary values (Severity: HIGH)**
`Float` for price and total causes floating-point precision errors. $19.99 may become $19.990000000000002. Use `Numeric(10, 2)`:
```python
from sqlalchemy import Numeric
price = Column(Numeric(10, 2), nullable=False)
```

### MEDIUM - Model Constraints

**MC1: Missing unique constraints (Severity: MEDIUM)**
`username` and `email` have no unique constraint. Duplicate usernames and emails can be inserted.

**MC2: Missing NOT NULL constraints (Severity: MEDIUM)**
Critical fields like `username`, `email`, `price`, `stock`, `quantity` allow NULL by default. Add `nullable=False` to required columns.

**MC3: Missing indexes on foreign keys (Severity: MEDIUM)**
`order_id`, `product_id`, `user_id` foreign key columns have no explicit indexes. While PostgreSQL automatically indexes primary keys, it does NOT auto-index foreign keys. Add `index=True`:
```python
user_id = Column(Integer, ForeignKey('users.id'), nullable=False, index=True)
```

### LOW - Filter Bug

**FB1: Falsy value check on min_price (Severity: LOW)**
```python
if min_price:
```
This evaluates to False when `min_price=0`, skipping a valid filter for free products. Use `if min_price is not None:`.'''),

    ("thinking/code-review", r'''Review this SQLAlchemy code and identify issues:

```python
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from contextlib import contextmanager
import os

DATABASE_URL = os.environ.get('DATABASE_URL', 'sqlite:///local.db')

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

@contextmanager
def get_session():
    session = SessionLocal()
    yield session
    session.commit()
    session.close()

def bulk_insert_users(users_data):
    with get_session() as session:
        for user_data in users_data:
            session.execute(
                text("INSERT INTO users (username, email) VALUES (:username, :email)"),
                user_data
            )

def transfer_funds(from_id, to_id, amount):
    with get_session() as session:
        from_account = session.execute(
            text("SELECT balance FROM accounts WHERE id = :id"),
            {"id": from_id}
        ).fetchone()

        if from_account[0] < amount:
            raise ValueError("Insufficient funds")

        session.execute(
            text("UPDATE accounts SET balance = balance - :amount WHERE id = :id"),
            {"amount": amount, "id": from_id}
        )
        session.execute(
            text("UPDATE accounts SET balance = balance + :amount WHERE id = :id"),
            {"amount": amount, "id": to_id}
        )

def get_report():
    with get_session() as session:
        result = session.execute(text("""
            SELECT u.username, COUNT(o.id) as order_count, SUM(o.total) as total_spent
            FROM users u
            LEFT JOIN orders o ON u.id = o.user_id
            GROUP BY u.username
            ORDER BY total_spent DESC
        """))
        return [dict(row._mapping) for row in result]

def delete_old_orders(days=90):
    with get_session() as session:
        session.execute(
            text("DELETE FROM order_items WHERE order_id IN "
                 "(SELECT id FROM orders WHERE created_at < NOW() - INTERVAL :days DAY)"),
            {"days": days}
        )
        session.execute(
            text("DELETE FROM orders WHERE created_at < NOW() - INTERVAL :days DAY"),
            {"days": days}
        )

def update_product_prices(category, multiplier):
    with get_session() as session:
        session.execute(
            text("UPDATE products SET price = price * :mult WHERE category = :cat"),
            {"mult": multiplier, "cat": category}
        )
```''', r'''<think>
Let me review this SQLAlchemy session management and raw SQL code.

1. Context manager is broken for errors:
- get_session yields, then commits, then closes. But if an exception occurs inside the `with` block, the code after `yield` in the generator is NOT executed (the exception propagates). This means:
  - On success: commit + close (correct)
  - On exception: no rollback, no close (WRONG). The session leaks and has dirty state.
- This is the most critical issue. Need try/except/finally:

```python
@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

2. transfer_funds race condition:
- Reads balance, checks in Python, then updates. Classic TOCTOU (time-of-check-time-of-use). Two concurrent transfers can both see sufficient balance and both succeed. Need SELECT FOR UPDATE or use a CHECK constraint.
- Also, from_account could be None if from_id doesn't exist. `from_account[0]` would then be a TypeError.

3. bulk_insert_users performance:
- Inserts one row at a time in a loop. For large datasets, this is extremely slow. Use executemany or bulk insert:
```python
session.execute(
    text("INSERT INTO users (username, email) VALUES (:username, :email)"),
    users_data  # pass the list directly
)
```

4. delete_old_orders:
- Uses `INTERVAL :days DAY` which is MySQL-specific syntax. SQLite and PostgreSQL use different syntax. This query is not portable.
- The two DELETE statements are not in a transaction... well, they ARE because get_session commits at the end. But if the first DELETE succeeds and the second fails, get_session does not rollback (as noted above), leaving orphaned order_items deleted but orders intact. Wait, it's the opposite -- it deletes order_items first, then orders. If the second fails, the items are deleted but orders remain, which is actually the correct order for foreign key constraints. But still, partial execution is bad.

5. Raw SQL everywhere:
- The entire codebase uses raw SQL via text() instead of the ORM. This loses type safety, relationship management, and makes the code harder to maintain. While raw SQL is sometimes necessary for complex queries, simple CRUD should use the ORM.

6. Connection pooling:
- create_engine with default settings uses a pool of 5 connections. No configuration for pool_size, max_overflow, pool_timeout, or pool_recycle. For production, these need tuning.
- No pool_pre_ping=True, so stale connections after database restart cause errors.

7. get_report:
- Returns data after the session context exits. Since get_session commits and closes, the result objects might be unusable. Actually, raw SQL results are just tuples, so they should be fine. The dict comprehension materializes the data before session close... wait, `return` happens inside the with block, so the session is still open when the list comprehension runs. But then the context manager runs commit/close after the generator resumes from yield. This is actually fine for raw results.

Let me write the review.
</think>

## Code Review: SQLAlchemy Session Management and Raw SQL

### CRITICAL - Broken Context Manager

**CM1: No rollback or close on exception (Severity: CRITICAL)**
```python
@contextmanager
def get_session():
    session = SessionLocal()
    yield session
    session.commit()
    session.close()
```
If any exception occurs inside the `with` block, the code after `yield` never executes. The session is never rolled back and never closed, leaking a database connection with dirty state. This affects every function in the file.

Fix:
```python
@contextmanager
def get_session():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

### CRITICAL - Race Condition

**RC1: TOCTOU in transfer_funds (Severity: CRITICAL)**
The balance check and update are not atomic:
```python
from_account = session.execute(text("SELECT balance ...")).fetchone()
if from_account[0] < amount:  # check
    raise ValueError(...)
session.execute(text("UPDATE accounts SET balance = balance - :amount ..."))  # update
```
Two concurrent transfers can both read a balance of $100 and both transfer $75, resulting in -$50. Use `SELECT ... FOR UPDATE` or an atomic update with a WHERE clause:
```python
result = session.execute(
    text("UPDATE accounts SET balance = balance - :amount "
         "WHERE id = :id AND balance >= :amount"),
    {"amount": amount, "id": from_id}
)
if result.rowcount == 0:
    raise ValueError("Insufficient funds or account not found")
```

**RC2: Null check missing (Severity: HIGH)**
`from_account` can be None if the account ID does not exist. `from_account[0]` raises TypeError. Check for None first.

### HIGH - Performance

**P1: Row-by-row bulk insert (Severity: HIGH)**
```python
for user_data in users_data:
    session.execute(text("INSERT ..."), user_data)
```
Inserting one row at a time generates N round trips to the database. For 10,000 users, this takes seconds instead of milliseconds. Use executemany:
```python
session.execute(
    text("INSERT INTO users (username, email) VALUES (:username, :email)"),
    users_data  # pass entire list
)
```

### HIGH - Portability

**PORT1: MySQL-specific date syntax (Severity: HIGH)**
```python
"WHERE created_at < NOW() - INTERVAL :days DAY"
```
`INTERVAL :days DAY` is MySQL syntax. PostgreSQL uses `INTERVAL ':days days'` differently, and SQLite has no INTERVAL at all. The DATABASE_URL defaults to SQLite, so this query will always fail locally. Use Python to compute the cutoff date:
```python
from datetime import datetime, timedelta
cutoff = datetime.utcnow() - timedelta(days=days)
session.execute(
    text("DELETE FROM orders WHERE created_at < :cutoff"),
    {"cutoff": cutoff}
)
```

### MEDIUM - Connection Pool

**CP1: No pool configuration (Severity: MEDIUM)**
Default pool_size=5 with no max_overflow, pool_timeout, or pool_recycle. For production workloads:
```python
engine = create_engine(
    DATABASE_URL,
    pool_size=20,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,
    pool_pre_ping=True,
)
```
`pool_pre_ping=True` is important to detect stale connections after database restarts.

### MEDIUM - Design

**D1: Raw SQL for simple CRUD (Severity: MEDIUM)**
Every operation uses `text()` raw SQL. Simple operations like insert, update, and delete should use the ORM for type safety, relationship management, and maintainability. Reserve raw SQL for complex reporting queries like `get_report`.

### LOW - Safety

**S1: update_product_prices lacks safeguards (Severity: LOW)**
No validation on `multiplier`. A value of 0 sets all prices to zero, and negative values produce negative prices. Add bounds checking. Also consider logging the change for audit.'''),

    ("thinking/code-review", r'''Review this SQLAlchemy code and identify issues:

```python
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, Table
from sqlalchemy.orm import relationship, declarative_base, Session
from sqlalchemy import event

Base = declarative_base()

# Many-to-many association table
post_tags = Table('post_tags', Base.metadata,
    Column('post_id', Integer, ForeignKey('posts.id')),
    Column('tag_id', Integer, ForeignKey('tags.id'))
)

class Tag(Base):
    __tablename__ = 'tags'
    id = Column(Integer, primary_key=True)
    name = Column(String(50))
    posts = relationship('Post', secondary=post_tags, back_populates='tags')

class Post(Base):
    __tablename__ = 'posts'
    id = Column(Integer, primary_key=True)
    title = Column(String(200))
    body = Column(String)
    author_id = Column(Integer, ForeignKey('authors.id'))
    author = relationship('Author', back_populates='posts')
    tags = relationship('Tag', secondary=post_tags, back_populates='posts')
    comments = relationship('Comment', back_populates='post', cascade='all, delete')

class Author(Base):
    __tablename__ = 'authors'
    id = Column(Integer, primary_key=True)
    name = Column(String(100))
    email = Column(String(100))
    posts = relationship('Post', back_populates='author')

    @property
    def post_count(self):
        return len(self.posts)

    @property
    def recent_posts(self):
        return sorted(self.posts, key=lambda p: p.id, reverse=True)[:5]

class Comment(Base):
    __tablename__ = 'comments'
    id = Column(Integer, primary_key=True)
    body = Column(String)
    post_id = Column(Integer, ForeignKey('posts.id'))
    author_id = Column(Integer, ForeignKey('authors.id'))
    post = relationship('Post', back_populates='comments')
    author = relationship('Author')
    replies = relationship('Comment', backref='parent',
                          foreign_keys='Comment.parent_id')
    parent_id = Column(Integer, ForeignKey('comments.id'))

@event.listens_for(Post, 'after_insert')
def after_post_insert(mapper, connection, target):
    session = Session.object_session(target)
    author = session.query(Author).get(target.author_id)
    # Send notification
    send_notification(author.email, f'Your post "{target.title}" was published')

@event.listens_for(Comment, 'after_insert')
def after_comment_insert(mapper, connection, target):
    session = Session.object_session(target)
    post = session.query(Post).get(target.post_id)
    author = session.query(Author).get(post.author_id)
    send_notification(author.email, f'New comment on "{post.title}"')

def get_posts_with_tag(session, tag_name):
    tag = session.query(Tag).filter(Tag.name == tag_name).first()
    if tag:
        return tag.posts
    return []

def get_author_stats(session):
    authors = session.query(Author).all()
    stats = []
    for author in authors:
        stats.append({
            'name': author.name,
            'post_count': author.post_count,
            'recent_posts': [p.title for p in author.recent_posts],
            'total_comments': sum(len(p.comments) for p in author.posts),
        })
    return stats
```''', r'''<think>
Let me review this SQLAlchemy relationship and event code.

1. Relationship design issues:
- post_tags association table has no primary key constraint and no unique constraint on (post_id, tag_id). The same tag can be associated with the same post multiple times.
- Comment.replies uses backref='parent' but parent_id is defined after the relationship. While SQLAlchemy can handle this, it is confusing. Also, the relationship uses `foreign_keys='Comment.parent_id'` as a string but the standard form is a list.

2. Performance disasters in properties:
- Author.post_count uses `len(self.posts)` which loads ALL posts into memory just to count them. Should use a database COUNT query.
- Author.recent_posts loads ALL posts, sorts in Python, then takes 5. Should use a database query with ORDER BY and LIMIT.
- get_author_stats calls both properties for every author, plus iterates all posts for comments. This is an N+1 catastrophe.

3. Event handler issues:
- after_post_insert and after_comment_insert run queries inside SQLAlchemy events. The 'after_insert' event fires within the flush cycle. Running new queries during a flush can cause re-entrancy issues and unexpected behavior.
- send_notification is presumably doing I/O (sending an email) inside an event handler, which blocks the database transaction. If the notification service is slow, the transaction stays open.
- Session.object_session(target) may return None if the object is not associated with a session.

4. get_posts_with_tag:
- Returns tag.posts which is a lazy-loaded collection. This triggers a query, but the returned posts have no eager-loaded relationships. Callers accessing post.author or post.comments trigger more lazy loads.

5. get_author_stats N+1:
- session.query(Author).all() -- loads all authors (1 query)
- For each author: author.post_count loads all posts (N queries)
- For each author: author.recent_posts loads all posts again (N queries, same data)
- For each author: sum(len(p.comments) for p in author.posts) loads all comments for all posts (N*M queries)
- This is potentially thousands of queries.

6. Cascade issue:
- Post has cascade='all, delete' on comments. This means deleting a post deletes its comments, but 'all' includes 'save-update, merge, refresh-expire, expunge, delete'. The 'delete-orphan' is NOT included. If you remove a comment from post.comments, it becomes an orphan but is not deleted. Usually you want 'all, delete-orphan'.

7. Missing constraints:
- No unique constraint on Tag.name
- No unique constraint on Author.email
- No NOT NULL on required fields

Let me structure this.
</think>

## Code Review: SQLAlchemy Relationships and Events

### CRITICAL - Performance

**P1: Author.post_count loads all posts (Severity: CRITICAL)**
```python
@property
def post_count(self):
    return len(self.posts)
```
This loads every post into memory, creates Python objects for each, then counts them. For an author with 10,000 posts, this fetches 10,000 rows just to return a number. Use a query:
```python
@property
def post_count(self):
    session = Session.object_session(self)
    return session.query(Post).filter(Post.author_id == self.id).count()
```
Or better, use a hybrid_property with a subquery for use in annotations.

**P2: Author.recent_posts sorts in Python (Severity: HIGH)**
Loads ALL posts, sorts in Python, takes 5. For large datasets this is extremely wasteful. Use a database query:
```python
@property
def recent_posts(self):
    session = Session.object_session(self)
    return session.query(Post).filter(
        Post.author_id == self.id
    ).order_by(Post.id.desc()).limit(5).all()
```

**P3: get_author_stats is an N+1 catastrophe (Severity: CRITICAL)**
For A authors, each with P posts and C comments per post:
- 1 query for authors
- A queries for post_count (loads all posts per author)
- A queries for recent_posts (loads all posts again)
- A * P queries for comments
Total: 1 + 2A + A*P queries. With 100 authors averaging 50 posts: 5,201 queries.

Fix with eager loading and annotations:
```python
from sqlalchemy import func

def get_author_stats(session):
    authors = session.query(
        Author,
        func.count(Post.id).label('post_count')
    ).outerjoin(Post).group_by(Author.id).all()
```

### HIGH - Event Handler Issues

**EV1: Queries during flush cycle (Severity: HIGH)**
`after_insert` events fire during `session.flush()`. Running `session.query(Author).get(...)` inside this event can cause re-entrancy issues, as the flush is still in progress. Use `after_commit` events or defer the work:
```python
@event.listens_for(Session, 'after_commit')
def after_commit(session):
    # process pending notifications
```

**EV2: I/O inside event handler (Severity: HIGH)**
`send_notification()` presumably does network I/O inside the event handler. This blocks the database transaction, increasing lock hold time. Queue notifications for async processing instead.

**EV3: Session may be None (Severity: MEDIUM)**
`Session.object_session(target)` returns None if the object is detached. The subsequent `.query()` call would then raise AttributeError.

### HIGH - Relationship Design

**RD1: No uniqueness on association table (Severity: HIGH)**
`post_tags` has no unique constraint on `(post_id, tag_id)`. The same tag can be linked to the same post multiple times. Add a primary key or unique constraint:
```python
post_tags = Table('post_tags', Base.metadata,
    Column('post_id', Integer, ForeignKey('posts.id'), primary_key=True),
    Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True)
)
```

**RD2: Missing delete-orphan cascade (Severity: MEDIUM)**
`cascade='all, delete'` does not include `delete-orphan`. Removing a comment from `post.comments` leaves an orphaned row. Use `cascade='all, delete-orphan'`.

### MEDIUM - Constraints

**C1: No unique constraint on Tag.name (Severity: MEDIUM)**
Multiple tags with the same name can be created. Add `unique=True`:
```python
name = Column(String(50), unique=True, nullable=False)
```

**C2: No unique constraint on Author.email (Severity: MEDIUM)**
Duplicate email addresses allowed.

**C3: Missing nullable=False (Severity: LOW)**
Required fields like `Post.title`, `Author.name`, `Comment.body` default to allowing NULL.'''),

    ("thinking/code-review", r'''Review this SQLAlchemy migration code and identify issues:

```python
"""Add user preferences and notification settings"""

from alembic import op
import sqlalchemy as sa

revision = 'abc123'
down_revision = 'def456'

def upgrade():
    # Add preferences column to users table
    op.add_column('users', sa.Column('preferences', sa.JSON()))

    # Create notifications table
    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id')),
        sa.Column('message', sa.String(500)),
        sa.Column('read', sa.Boolean(), default=False),
        sa.Column('created_at', sa.DateTime()),
    )

    # Backfill default preferences
    op.execute("UPDATE users SET preferences = '{}'")

    # Add index
    op.create_index('idx_notifications_user', 'notifications', ['user_id'])

    # Rename column
    op.alter_column('users', 'name', new_column_name='full_name')

    # Change column type
    op.alter_column('users', 'age', type_=sa.String(10),
                    existing_type=sa.Integer())

    # Drop old table
    op.drop_table('legacy_preferences')

    # Add NOT NULL constraint
    op.alter_column('users', 'email', nullable=False)

def downgrade():
    op.alter_column('users', 'email', nullable=True)
    op.create_table('legacy_preferences',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('user_id', sa.Integer()),
        sa.Column('data', sa.Text()),
    )
    op.alter_column('users', 'age', type_=sa.Integer(),
                    existing_type=sa.String(10))
    op.alter_column('users', 'full_name', new_column_name='name')
    op.drop_index('idx_notifications_user', 'notifications')
    op.execute("UPDATE users SET preferences = NULL")
    op.drop_table('notifications')
    op.drop_column('users', 'preferences')
```''', r'''<think>
Let me review this Alembic migration for safety, correctness, and best practices.

1. Migration is too large / does too many things:
- This single migration adds a column, creates a table, backfills data, creates an index, renames a column, changes a column type, drops a table, and adds a NOT NULL constraint. If any step fails partway through, the migration is partially applied and hard to recover from (especially on MySQL/MariaDB which don't support transactional DDL).
- Should be split into multiple smaller migrations.

2. Dangerous operations:
- Dropping legacy_preferences table is irreversible in practice. The downgrade recreates the table structure but the DATA is lost forever. This should be a separate migration with a data backup step.
- Changing `age` from Integer to String is a lossy type change. The downgrade from String back to Integer will fail if any non-numeric strings were inserted after the upgrade.
- Adding NOT NULL to `email` will fail if any existing rows have NULL emails. Should backfill first.

3. Backfill issue:
- `op.execute("UPDATE users SET preferences = '{}'")` -- the string '{}' may not be valid JSON for all databases. PostgreSQL JSON columns need proper JSON syntax. Also, this runs as a single UPDATE which locks the entire users table. For large tables, this causes downtime.

4. Missing constraints:
- notifications.user_id has no NOT NULL constraint. Also, no ON DELETE behavior specified for the foreign key.
- notifications.read uses `default=False` which is a Python default, not a server default. Use `server_default=sa.text('false')` for database-level defaults.
- No index on notifications.created_at, which is commonly used for ordering.

5. Downgrade issues:
- The downgrade recreates legacy_preferences without its data. This means the downgrade is lossy -- you cannot roll back without data loss.
- The downgrade converts age back from String to Integer. If any values like "unknown" were inserted while it was a String, the type conversion fails.
- The JSON backfill in downgrade sets preferences to NULL then drops the column, which is redundant.

6. Locking concerns:
- On PostgreSQL, ALTER TABLE operations take an ACCESS EXCLUSIVE lock. Multiple ALTER operations on the users table (add_column, alter_column x3) each take a lock. This can cause extended downtime on large tables.
- Column rename on large tables can be slow on some databases.

7. No concurrency safety:
- The migration does not use `op.execute` with batched updates for the backfill.
- No mention of running in a maintenance window.

Let me structure this.
</think>

## Code Review: Alembic Database Migration

### CRITICAL - Migration Safety

**MS1: Migration is too large and non-atomic (Severity: CRITICAL)**
This single migration performs 8 different operations: add column, create table, backfill data, create index, rename column, change type, drop table, and add constraint. If any step fails mid-migration (especially on MySQL which lacks transactional DDL), the database is left in a partially migrated state that is very difficult to recover from.

Split into separate migrations:
1. Add preferences column + backfill
2. Create notifications table + index
3. Rename column
4. Change column type
5. Drop legacy table (with data backup)
6. Add NOT NULL constraint

### CRITICAL - Data Loss

**DL1: Drop table destroys data irreversibly (Severity: CRITICAL)**
`op.drop_table('legacy_preferences')` permanently deletes the table and all its data. The downgrade recreates the schema but the data is gone. Either:
- Migrate data before dropping
- Keep the old table for a release cycle with a deprecation warning
- At minimum, create a data backup step before dropping

**DL2: Integer to String type change is risky (Severity: HIGH)**
Converting `age` from Integer to String allows non-numeric values. The downgrade back to Integer will fail with a cast error if any such values exist. This should include a CHECK constraint or validation.

### HIGH - NOT NULL Without Backfill

**NF1: Adding NOT NULL to email may fail (Severity: HIGH)**
```python
op.alter_column('users', 'email', nullable=False)
```
This fails if any existing rows have NULL email values. Backfill first:
```python
op.execute("UPDATE users SET email = 'unknown@example.com' WHERE email IS NULL")
op.alter_column('users', 'email', nullable=False)
```

### HIGH - Locking and Downtime

**LK1: Multiple ALTER TABLE operations on users (Severity: HIGH)**
Each `alter_column` call on the `users` table takes an ACCESS EXCLUSIVE lock in PostgreSQL, blocking all reads and writes. Four ALTER operations means the table is locked four separate times. On a table with millions of rows, this causes significant downtime.

Mitigations:
- Combine alterations into fewer operations
- Use `CONCURRENTLY` where possible
- Schedule during maintenance windows

**LK2: Full table UPDATE for backfill (Severity: HIGH)**
```python
op.execute("UPDATE users SET preferences = '{}'")
```
This updates every row in a single transaction, locking the entire table. For large tables, batch the update:
```python
# Batch in chunks of 10000
op.execute("""
    UPDATE users SET preferences = '{}' WHERE id IN (
        SELECT id FROM users WHERE preferences IS NULL LIMIT 10000
    )
""")
```

### MEDIUM - Schema Issues

**SI1: Server default missing on notifications.read (Severity: MEDIUM)**
```python
sa.Column('read', sa.Boolean(), default=False)
```
`default=False` is a Python-side default that only works through SQLAlchemy ORM. Direct SQL inserts will get NULL. Use:
```python
sa.Column('read', sa.Boolean(), server_default=sa.text('false'), nullable=False)
```

**SI2: Missing NOT NULL on notifications.user_id (Severity: MEDIUM)**
A notification without a user makes no sense. Add `nullable=False`.

**SI3: No ON DELETE for foreign key (Severity: MEDIUM)**
`sa.ForeignKey('users.id')` with no `ondelete` parameter. If a user is deleted, their notifications become orphans. Add `ondelete='CASCADE'`.

### LOW - Downgrade Quality

**DG1: Lossy downgrade (Severity: LOW)**
The downgrade cannot restore legacy_preferences data or safely convert String age back to Integer. Document that this migration is not safely reversible, and ensure a database backup exists before running.'''),

    ("thinking/code-review", r'''Review this SQLAlchemy code and identify issues:

```python
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Enum
from sqlalchemy.orm import declarative_base, Session, sessionmaker
from sqlalchemy.pool import QueuePool
import enum
from datetime import datetime, timedelta
import threading

Base = declarative_base()

engine = create_engine(
    'postgresql://user:pass@db-host/mydb',
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
)

SessionFactory = sessionmaker(bind=engine)

class TaskStatus(enum.Enum):
    PENDING = 'pending'
    RUNNING = 'running'
    COMPLETED = 'completed'
    FAILED = 'failed'

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    name = Column(String(200))
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING)
    worker_id = Column(String(50))
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime)
    completed_at = Column(DateTime)
    result = Column(String)

_session_local = threading.local()

def get_session():
    if not hasattr(_session_local, 'session'):
        _session_local.session = SessionFactory()
    return _session_local.session

def claim_task(worker_id):
    session = get_session()
    task = session.query(Task).filter(
        Task.status == TaskStatus.PENDING
    ).first()
    if task:
        task.status = TaskStatus.RUNNING
        task.worker_id = worker_id
        task.started_at = datetime.utcnow()
        session.commit()
    return task

def complete_task(task_id, result):
    session = get_session()
    task = session.query(Task).get(task_id)
    task.status = TaskStatus.COMPLETED
    task.completed_at = datetime.utcnow()
    task.result = str(result)
    session.commit()

def fail_task(task_id, error):
    session = get_session()
    task = session.query(Task).get(task_id)
    task.status = TaskStatus.FAILED
    task.result = str(error)
    session.commit()

def get_stale_tasks(timeout_minutes=30):
    session = get_session()
    cutoff = datetime.utcnow() - timedelta(minutes=timeout_minutes)
    return session.query(Task).filter(
        Task.status == TaskStatus.RUNNING,
        Task.started_at < cutoff
    ).all()

def retry_stale_tasks():
    session = get_session()
    stale = get_stale_tasks()
    for task in stale:
        task.status = TaskStatus.PENDING
        task.worker_id = None
        task.started_at = None
    session.commit()

def get_stats():
    session = get_session()
    stats = {}
    for status in TaskStatus:
        stats[status.value] = session.query(Task).filter(
            Task.status == status
        ).count()
    return stats
```''', r'''<think>
Let me review this SQLAlchemy task queue implementation.

1. Race condition in claim_task:
- This is the most critical issue. Two workers can both call claim_task simultaneously, both execute the same query, both get the same PENDING task, and both set it to RUNNING. This is a classic race condition.
- No SELECT FOR UPDATE, no optimistic locking, no atomic update.
- Fix: Use SELECT FOR UPDATE SKIP LOCKED:
```python
task = session.query(Task).filter(
    Task.status == TaskStatus.PENDING
).with_for_update(skip_locked=True).first()
```

2. Thread-local session management:
- Using threading.local() to store sessions means sessions are never closed. They persist for the lifetime of the thread. In a thread pool (common in web servers), sessions accumulate stale state.
- If a session encounters an error and is not properly rolled back, all subsequent operations on that thread use the broken session.
- No error handling or rollback mechanism.

3. Error handling:
- complete_task and fail_task do not check if task is None (could be deleted by another process).
- No try/except/rollback pattern. If session.commit() fails, the session is in a broken state and all subsequent operations on that thread fail.
- No isolation between operations -- one failed commit poisons the thread-local session.

4. get_stats performance:
- Runs a separate COUNT query for each TaskStatus value (4 queries). Could be done in one query with GROUP BY:
```python
session.query(Task.status, func.count(Task.id)).group_by(Task.status).all()
```

5. datetime.utcnow in default:
- `default=datetime.utcnow` (without parentheses) correctly passes the function. However, datetime.utcnow() is deprecated in Python 3.12+. Should use `datetime.now(timezone.utc)`.

6. Missing indexes:
- No index on Task.status. The claim_task query filters by status, and get_stale_tasks filters by status AND started_at. Without indexes, these are full table scans.

7. Connection pooling:
- pool_size=5 with max_overflow=10 means up to 15 connections. But if there are more than 15 worker threads, they block for pool_timeout=30 seconds then get a timeout error.
- No pool_pre_ping for detecting stale connections.
- Hardcoded credentials in connection string.

8. retry_stale_tasks:
- Calls get_stale_tasks() which returns objects from get_session(). Since both functions use the same thread-local session, this works. But the stale tasks are fetched without FOR UPDATE, so another process could claim them between the SELECT and the UPDATE.

Let me structure this.
</think>

## Code Review: SQLAlchemy Task Queue

### CRITICAL - Race Condition in Task Claiming

**RC1: Non-atomic task claim (Severity: CRITICAL)**
```python
def claim_task(worker_id):
    task = session.query(Task).filter(Task.status == TaskStatus.PENDING).first()
    if task:
        task.status = TaskStatus.RUNNING
```
Two workers calling `claim_task` simultaneously can SELECT the same PENDING task, and both set it to RUNNING. One worker's work is silently lost. Use `SELECT ... FOR UPDATE SKIP LOCKED`:
```python
def claim_task(worker_id):
    session = get_session()
    task = session.query(Task).filter(
        Task.status == TaskStatus.PENDING
    ).with_for_update(skip_locked=True).first()
    if task:
        task.status = TaskStatus.RUNNING
        task.worker_id = worker_id
        task.started_at = datetime.utcnow()
        session.commit()
    return task
```
`SKIP LOCKED` makes concurrent workers skip already-locked rows instead of blocking, enabling parallel task claiming.

### CRITICAL - Session Management

**SM1: Thread-local sessions never closed or recycled (Severity: CRITICAL)**
```python
def get_session():
    if not hasattr(_session_local, 'session'):
        _session_local.session = SessionFactory()
    return _session_local.session
```
Once created, a session lives for the lifetime of the thread. Issues:
- If any operation fails without rollback, the session is permanently corrupted. All subsequent operations on that thread fail or produce unexpected results.
- Long-lived sessions hold stale data from their identity map, returning outdated objects.
- Connections may go stale (server-side timeout) without `pool_pre_ping`.

Fix: Use scoped_session with proper cleanup, or create sessions per-operation:
```python
from sqlalchemy.orm import scoped_session
Session = scoped_session(SessionFactory)

# After each unit of work:
Session.remove()
```

### HIGH - No Error Handling

**EH1: No rollback on failures (Severity: HIGH)**
No function has try/except around session operations. If `session.commit()` fails (constraint violation, connection lost), the session enters a broken state. All subsequent calls on that thread fail silently or raise confusing errors.

Fix: Add rollback handling:
```python
def complete_task(task_id, result):
    session = get_session()
    try:
        task = session.query(Task).get(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")
        task.status = TaskStatus.COMPLETED
        task.completed_at = datetime.utcnow()
        task.result = str(result)
        session.commit()
    except Exception:
        session.rollback()
        raise
```

**EH2: No None check on task lookups (Severity: MEDIUM)**
`complete_task` and `fail_task` call `.get(task_id)` without checking for None. If the task was deleted, `task.status = ...` raises AttributeError.

### MEDIUM - Performance

**P1: get_stats runs 4 separate queries (Severity: MEDIUM)**
One COUNT query per status value. Consolidate into one:
```python
from sqlalchemy import func

def get_stats():
    session = get_session()
    rows = session.query(Task.status, func.count(Task.id)).group_by(Task.status).all()
    return {status.value: count for status, count in rows}
```

**P2: Missing indexes (Severity: MEDIUM)**
`claim_task` filters by status; `get_stale_tasks` filters by status AND started_at. Without indexes, both do full table scans. Add:
```python
from sqlalchemy import Index
__table_args__ = (
    Index('idx_task_status', 'status'),
    Index('idx_task_status_started', 'status', 'started_at'),
)
```

### MEDIUM - Connection Pool

**CP1: No pool_pre_ping (Severity: MEDIUM)**
Without `pool_pre_ping=True`, stale connections after database restarts cause "server closed the connection unexpectedly" errors.

**CP2: Hardcoded credentials (Severity: MEDIUM)**
Database URL with credentials is hardcoded. Use environment variables.

### LOW - Deprecation

**DEP1: datetime.utcnow() deprecated (Severity: LOW)**
`datetime.utcnow()` is deprecated in Python 3.12. Use `datetime.now(timezone.utc)`.'''),
]
