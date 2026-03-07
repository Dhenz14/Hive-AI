"""
Proactive alternatives training pairs - Database patterns and anti-patterns
"""

pairs = [
    {
        "instruction": r'''I have a query that fetches user data for a profile page:

```sql
SELECT * FROM users WHERE id = 42;
```

The users table has about 30 columns. This works fine. Should I be doing anything differently?''',
        "output": r'''<think>
SELECT * works but has several downsides: fetches columns you do not need (wastes bandwidth and memory), breaks if columns are added/renamed, prevents covering indexes from being used, and leaks sensitive columns accidentally. For a 30-column table this matters. I should show the better approach while acknowledging SELECT * is fine for quick exploration.
</think>

It works, but with 30 columns there are good reasons to list only what you need:

```sql
-- Instead of SELECT *
SELECT id, username, display_name, avatar_url, bio, created_at
FROM users
WHERE id = 42;
```

Here is why this matters for a 30-column table:

**Performance**: If some of those 30 columns include large text fields, JSON blobs, or binary data, you are transferring all of it over the wire even if the profile page only shows 6 fields. On a busy app this adds up.

**Security**: SELECT * might return `password_hash`, `email`, `phone`, `ssn`, or `internal_notes` to your application layer. Even if you filter them before sending to the client, they are still in memory.

**Stability**: If someone adds a column to the users table, SELECT * silently returns it. Your code might break if it does not expect the new column, or it might leak sensitive data.

**Index efficiency**: PostgreSQL can use a covering index to answer a query without touching the main table:

```sql
-- This index can fully satisfy the specific-column query
CREATE INDEX idx_users_profile ON users (id)
    INCLUDE (username, display_name, avatar_url, bio, created_at);

-- But SELECT * always needs the full row from the heap
```

SELECT * is perfectly fine for ad-hoc exploration in a SQL console or when you genuinely need all columns. For application queries that run repeatedly, listing specific columns is the safer habit.

A nice pattern if you want reusability:

```sql
-- Create a view for the profile shape
CREATE VIEW user_profiles AS
SELECT id, username, display_name, avatar_url, bio, created_at
FROM users;

-- Now this is clean and maintained in one place
SELECT * FROM user_profiles WHERE id = 42;
```'''
    },
    {
        "instruction": r'''My app queries are getting slow as the database grows. I have a users table with about 2 million rows. Here's a typical query:

```sql
SELECT * FROM users WHERE email = 'alice@example.com';
SELECT * FROM orders WHERE user_id = 42 AND status = 'pending';
SELECT * FROM products WHERE category = 'electronics' AND price < 100;
```

I haven't added any indexes besides the primary keys. Should I just index everything?''',
        "output": r'''<think>
Indexing everything is wasteful -- each index slows down writes and uses disk space. The right approach is to index based on actual query patterns. I should show them how to identify what needs indexing using EXPLAIN, then create targeted indexes for their specific queries. Composite indexes for multi-column WHERE clauses are important to mention.
</think>

Do not index everything -- each index slows down INSERT/UPDATE operations and uses disk space. Instead, create indexes that match your actual query patterns.

For your three queries, here are the targeted indexes:

```sql
-- For: WHERE email = '...'
-- Unique index since emails should be unique anyway
CREATE UNIQUE INDEX idx_users_email ON users (email);

-- For: WHERE user_id = X AND status = '...'
-- Composite index with the more selective column first
CREATE INDEX idx_orders_user_status ON orders (user_id, status);

-- For: WHERE category = '...' AND price < X
-- Category first (equality), then price (range)
CREATE INDEX idx_products_cat_price ON products (category, price);
```

The order of columns in composite indexes matters. Put equality conditions first, range conditions last:

```sql
-- GOOD: category = X (equality) then price < Y (range)
CREATE INDEX idx_products_cat_price ON products (category, price);

-- This index handles all of these queries:
WHERE category = 'electronics' AND price < 100   -- uses both columns
WHERE category = 'electronics'                    -- uses first column
-- But NOT:
WHERE price < 100                                 -- cannot skip first column
```

Use EXPLAIN to verify your indexes are actually being used:

```sql
EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'alice@example.com';

-- Before index: Seq Scan on users  (cost=... rows=2000000)
-- After index:  Index Scan using idx_users_email  (cost=... rows=1)
```

A few rules of thumb:

```sql
-- Index columns that appear in WHERE, JOIN, and ORDER BY
-- Do NOT index columns with low cardinality unless combined with others
CREATE INDEX idx_orders_status ON orders (status);  -- only 4 values, rarely useful alone

-- DO index foreign keys (they speed up JOINs and cascading deletes)
CREATE INDEX idx_orders_user_id ON orders (user_id);

-- Consider partial indexes for common filters
CREATE INDEX idx_orders_pending ON orders (user_id)
    WHERE status = 'pending';  -- smaller index, only for pending orders
```

Start with EXPLAIN ANALYZE on your slowest queries, add indexes for those, and recheck. You will likely find that 5-10 well-chosen indexes cover 95% of your query patterns.'''
    },
    {
        "instruction": r'''I'm building a search feature where users can filter by name. Here's my Python code:

```python
def search_users(name):
    query = "SELECT * FROM users WHERE name LIKE '%" + name + "%'"
    cursor.execute(query)
    return cursor.fetchall()
```

It works but I've heard this might have issues. What should I change?''',
        "output": r'''<think>
This is SQL injection -- the most critical web security vulnerability. If name is "'; DROP TABLE users; --" the query becomes destructive. Parameterized queries fix this completely. I need to be direct about the severity without being preachy, and show the fix clearly. This is not a "nice to have" alternative -- it is a security fix.
</think>

This is a SQL injection vulnerability -- one of the most critical security issues in web applications. An attacker could pass a name like `'; DROP TABLE users; --` and it would execute as SQL.

Here is the fix using parameterized queries:

```python
def search_users(name):
    query = "SELECT id, username, email FROM users WHERE name LIKE %s"
    cursor.execute(query, (f"%{name}%",))
    return cursor.fetchall()
```

The database driver handles escaping and quoting automatically. The `%s` is a parameter placeholder -- it is NOT string formatting. The driver treats the parameter as a value, never as SQL code.

Here is what happens with malicious input:

```python
# String concatenation (VULNERABLE)
name = "'; DROP TABLE users; --"
query = "SELECT * FROM users WHERE name LIKE '%'; DROP TABLE users; --%'"
# Executes TWO statements -- searches and then drops the table

# Parameterized (SAFE)
name = "'; DROP TABLE users; --"
cursor.execute("SELECT * FROM users WHERE name LIKE %s", (f"%{name}%",))
# Searches for the literal string "'; DROP TABLE users; --"
# The database sees it as data, not code
```

Different libraries use different placeholder styles:

```python
# psycopg2 (PostgreSQL)
cursor.execute("SELECT * FROM users WHERE name LIKE %s", (f"%{name}%",))

# sqlite3
cursor.execute("SELECT * FROM users WHERE name LIKE ?", (f"%{name}%",))

# SQLAlchemy (any database)
from sqlalchemy import text
result = db.execute(
    text("SELECT * FROM users WHERE name LIKE :pattern"),
    {"pattern": f"%{name}%"}
)

# Or better yet, use the ORM
users = db.query(User).filter(User.name.ilike(f"%{name}%")).all()
```

This is not an optional improvement -- parameterized queries should be used for every query that includes user input. No exceptions. Most linting tools and security scanners will flag string concatenation in SQL as a critical issue.'''
    },
    {
        "instruction": r'''I'm designing a database for a project management app. I'm putting everything in one table:

```sql
CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    project_name VARCHAR(255),
    project_description TEXT,
    owner_name VARCHAR(255),
    owner_email VARCHAR(255),
    task1_name VARCHAR(255),
    task1_status VARCHAR(50),
    task1_assignee VARCHAR(255),
    task2_name VARCHAR(255),
    task2_status VARCHAR(50),
    task2_assignee VARCHAR(255),
    task3_name VARCHAR(255),
    task3_status VARCHAR(50),
    task3_assignee VARCHAR(255)
);
```

I figure 3 tasks per project is enough. Does this look right?''',
        "output": r'''<think>
This is a classic denormalized design with repeating groups. The problems: 3-task limit is arbitrary, adding a 4th task means altering the table, queries for "all tasks assigned to Alice" require checking 3 columns, and owner data is duplicated across projects. Normalization into separate tables (users, projects, tasks) solves all of these. I should show the normalized design and explain why it is more flexible.
</think>

This will hit some walls quickly. What happens when a project needs 4 tasks? Or 20? You would have to alter the table and update all your queries each time. Also, finding all tasks assigned to a specific person means checking three separate columns.

Here is a normalized design that removes those limitations:

```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL
);

CREATE TABLE projects (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    owner_id INTEGER NOT NULL REFERENCES users(id),
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE tasks (
    id SERIAL PRIMARY KEY,
    project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    assignee_id INTEGER REFERENCES users(id),
    name VARCHAR(255) NOT NULL,
    status VARCHAR(50) DEFAULT 'todo',
    created_at TIMESTAMP DEFAULT NOW()
);
```

Now your queries become simple and flexible:

```sql
-- All tasks for a project (no limit on count)
SELECT t.name, t.status, u.name AS assignee
FROM tasks t
LEFT JOIN users u ON t.assignee_id = u.id
WHERE t.project_id = 1;

-- All tasks assigned to Alice (one clean query)
SELECT t.name, t.status, p.name AS project
FROM tasks t
JOIN projects p ON t.project_id = p.id
JOIN users u ON t.assignee_id = u.id
WHERE u.email = 'alice@example.com';

-- Count tasks by status per project
SELECT p.name, t.status, COUNT(*) AS task_count
FROM projects p
JOIN tasks t ON t.project_id = p.id
GROUP BY p.name, t.status;

-- Projects with no incomplete tasks
SELECT p.name FROM projects p
WHERE NOT EXISTS (
    SELECT 1 FROM tasks t
    WHERE t.project_id = p.id AND t.status != 'done'
);
```

Benefits of separate tables:
- **Unlimited tasks** per project -- no schema changes needed
- **No duplicated data** -- Alice's email is stored once, not repeated in every project
- **Easy queries** -- "find all of Alice's tasks" is a simple JOIN, not a UNION across three column sets
- **Data integrity** -- foreign keys prevent orphaned records and invalid references

If you update Alice's email, you change one row in the users table instead of hunting through every project row.'''
    },
    {
        "instruction": r'''I have a notification system where the app needs to check for new messages. Right now I'm polling the database every 2 seconds:

```python
import time

def check_notifications(user_id):
    while True:
        new = db.execute(
            "SELECT * FROM notifications WHERE user_id = %s AND seen = FALSE",
            (user_id,)
        )
        if new:
            send_to_client(new)
            mark_as_seen(new)
        time.sleep(2)
```

This works for a few users but I'm worried about scaling it. Is there a better pattern?''',
        "output": r'''<think>
Polling every 2 seconds per user means N users = N queries every 2 seconds, which scales poorly. PostgreSQL has LISTEN/NOTIFY built in -- the database pushes events to connected clients when data changes. This is zero-cost when nothing happens and instant when something does. For other databases, Change Data Capture (CDC) or message queues serve the same purpose.
</think>

With 100 users, that is 50 queries per second hitting your database even when there are no new notifications. PostgreSQL has a built-in solution for this: LISTEN/NOTIFY. The database pushes events to your app -- no polling needed.

Set up a trigger that fires when a notification is inserted:

```sql
-- Create a function that sends a notification event
CREATE OR REPLACE FUNCTION notify_new_notification()
RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify(
        'new_notification',
        json_build_object(
            'user_id', NEW.user_id,
            'id', NEW.id,
            'message', NEW.message
        )::text
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Attach it to the notifications table
CREATE TRIGGER trg_new_notification
    AFTER INSERT ON notifications
    FOR EACH ROW
    EXECUTE FUNCTION notify_new_notification();
```

Python listener using psycopg2:

```python
import psycopg2
import psycopg2.extensions
import select
import json

def listen_for_notifications():
    conn = psycopg2.connect(dsn)
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cursor = conn.cursor()
    cursor.execute("LISTEN new_notification;")

    while True:
        # select() blocks until there is data -- no polling, no CPU waste
        if select.select([conn], [], [], 5) == ([], [], []):
            # Timeout -- just a keepalive check, no query executed
            continue
        conn.poll()
        while conn.notifies:
            event = conn.notifies.pop(0)
            payload = json.loads(event.payload)
            user_id = payload['user_id']
            send_to_client(user_id, payload)
```

The key difference: your polling approach runs a query every 2 seconds regardless of activity. LISTEN/NOTIFY uses zero resources when nothing happens and delivers instantly when something does.

For non-PostgreSQL databases, similar patterns exist: Redis Pub/Sub, MongoDB Change Streams, or Debezium for Change Data Capture. But if you are on PostgreSQL, LISTEN/NOTIFY is the simplest upgrade since it requires no additional infrastructure.'''
    },
]
