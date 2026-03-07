"""
Multi-turn conversation training pairs - Database design evolution
Covers: schema design -> migrations -> query optimization -> scaling -> replication
Focus on PostgreSQL and SQLite
"""

pairs = [
    {
        "instruction": r'''[Previous conversation]
User: I'm building a blog platform and need help designing the database schema. It'll have users, posts, and comments. I'm using PostgreSQL.
Assistant: Here's a solid starting schema for your blog platform:

CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE posts (
    id SERIAL PRIMARY KEY,
    author_id INTEGER NOT NULL REFERENCES users(id),
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255) UNIQUE NOT NULL,
    body TEXT NOT NULL,
    published BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE comments (
    id SERIAL PRIMARY KEY,
    post_id INTEGER NOT NULL REFERENCES posts(id),
    author_id INTEGER NOT NULL REFERENCES users(id),
    body TEXT NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

[Current message]
User: That looks great. Now I want to add tags to posts -- each post can have multiple tags and each tag can be on multiple posts. How do I handle that?''',
        "output": r'''Since we already have the posts table from the schema above, we need a classic many-to-many relationship. This requires a tags table and a junction table connecting posts to tags.

Here's what to add:

```sql
CREATE TABLE tags (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL
);

CREATE TABLE post_tags (
    post_id INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
    tag_id INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (post_id, tag_id)
);

-- Index for looking up posts by tag (the reverse direction)
CREATE INDEX idx_post_tags_tag_id ON post_tags(tag_id);
```

Key design decisions here:

1. **Composite primary key** on post_tags -- the combination (post_id, tag_id) is naturally unique and serves as both the PK and a uniqueness constraint. No need for a surrogate id column.

2. **ON DELETE CASCADE** -- if a post is deleted, its tag associations are cleaned up automatically. Same for tags. This prevents orphaned rows in the junction table.

3. **The extra index on tag_id** -- PostgreSQL automatically indexes the first column of a composite PK, so lookups by post_id are fast. But queries like "find all posts with tag X" need the reverse lookup, hence the explicit index.

To query posts with their tags:

```sql
SELECT p.id, p.title, array_agg(t.name) AS tags
FROM posts p
LEFT JOIN post_tags pt ON p.id = pt.post_id
LEFT JOIN tags t ON pt.tag_id = t.id
GROUP BY p.id, p.title;
```

And to find posts with a specific tag:

```sql
SELECT p.*
FROM posts p
JOIN post_tags pt ON p.id = pt.post_id
JOIN tags t ON pt.tag_id = t.id
WHERE t.slug = 'python';
```

Use LEFT JOIN in the first query so posts with no tags still appear in results.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I have a PostgreSQL blog schema with users, posts, comments, tags, and a post_tags junction table. Now I need to add a "categories" feature. Each post belongs to exactly one category, and categories can be nested (like "Programming" -> "Python" -> "Web Frameworks").
Assistant: For hierarchical categories with single-parent assignment, I'd use an adjacency list with a self-referencing foreign key:

CREATE TABLE categories (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    slug VARCHAR(100) UNIQUE NOT NULL,
    parent_id INTEGER REFERENCES categories(id),
    sort_order INTEGER DEFAULT 0
);

ALTER TABLE posts ADD COLUMN category_id INTEGER REFERENCES categories(id);
CREATE INDEX idx_posts_category ON posts(category_id);

Then use recursive CTEs to query the hierarchy.

[Current message]
User: The recursive CTE stuff is confusing me. Can you show me how to get all posts in a category AND its subcategories? Like if I pick "Programming", I want posts in "Programming", "Python", "Web Frameworks", etc.''',
        "output": r'''Building on the categories table we set up, here's how recursive CTEs work for your use case. The idea is to start at the target category and walk down the tree to find all descendants.

```sql
-- Get all posts in "Programming" and all its subcategories
WITH RECURSIVE category_tree AS (
    -- Base case: start with the target category
    SELECT id, name, parent_id
    FROM categories
    WHERE slug = 'programming'

    UNION ALL

    -- Recursive case: find children of current level
    SELECT c.id, c.name, c.parent_id
    FROM categories c
    INNER JOIN category_tree ct ON c.parent_id = ct.id
)
SELECT p.id, p.title, p.slug, cat.name AS category_name
FROM posts p
JOIN category_tree cat ON p.category_id = cat.id
WHERE p.published = TRUE
ORDER BY p.created_at DESC;
```

How it works step by step:

1. The base case selects the "programming" category (id=1, say).
2. First recursion finds categories where parent_id=1 (e.g., "Python" id=5, "JavaScript" id=6).
3. Second recursion finds categories where parent_id IN (5, 6) (e.g., "Web Frameworks" id=12).
4. Recursion stops when no more children are found.
5. The final SELECT joins posts against all discovered category IDs.

If your hierarchy gets deep (5+ levels) or you query it very frequently, consider adding a materialized path column for faster lookups:

```sql
ALTER TABLE categories ADD COLUMN path TEXT;
-- Store paths like '/1/5/12/' for quick LIKE queries

-- Then querying becomes simple:
UPDATE categories SET path = '/1/' WHERE id = 1;
UPDATE categories SET path = '/1/5/' WHERE id = 5;
UPDATE categories SET path = '/1/5/12/' WHERE id = 12;

-- Find all subcategories of "programming" (id=1):
SELECT p.*
FROM posts p
JOIN categories c ON p.category_id = c.id
WHERE c.path LIKE '/1/%';
```

The materialized path trades write complexity for read speed. For a blog with infrequent category changes but frequent reads, it is a solid optimization.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My blog app is growing and I need to add database migrations. I've been running CREATE TABLE statements manually. What migration tool should I use with Python and PostgreSQL?
Assistant: I recommend Alembic -- it's the standard migration tool for SQLAlchemy. Install with pip install alembic, then run alembic init migrations to set up. Configure your database URL in alembic.ini and you're ready to create migrations.

User: I set up Alembic. How do I create my first migration?
Assistant: Run `alembic revision --autogenerate -m "initial schema"` and it will compare your SQLAlchemy models to the database and generate a migration script. Then `alembic upgrade head` to apply it.

[Current message]
User: OK so now I need to add a "likes" feature. Users can like posts. I need to create a migration for this. Can you walk me through the whole process?''',
        "output": r'''Since you already have Alembic configured from our earlier setup, here's the complete workflow for adding a likes feature.

Step 1 -- Define the model in your SQLAlchemy models file:

```python
# models.py
from sqlalchemy import Column, Integer, ForeignKey, UniqueConstraint, DateTime
from sqlalchemy.sql import func

class PostLike(Base):
    __tablename__ = 'post_likes'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    post_id = Column(Integer, ForeignKey('posts.id', ondelete='CASCADE'), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint('user_id', 'post_id', name='uq_user_post_like'),
    )
```

Step 2 -- Generate the migration:

```bash
alembic revision --autogenerate -m "add post_likes table"
```

Step 3 -- Review the generated migration file (this is critical):

```python
# migrations/versions/xxxx_add_post_likes_table.py

def upgrade():
    op.create_table(
        'post_likes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('post_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'post_id', name='uq_user_post_like')
    )
    # Add index for counting likes per post efficiently
    op.create_index('idx_post_likes_post_id', 'post_likes', ['post_id'])


def downgrade():
    op.drop_index('idx_post_likes_post_id')
    op.drop_table('post_likes')
```

Step 4 -- Apply it:

```bash
# Check current state
alembic current

# Apply the migration
alembic upgrade head

# Verify
alembic current
```

The UniqueConstraint on (user_id, post_id) prevents a user from liking the same post twice. The index on post_id makes "count likes for this post" queries fast. Always review autogenerated migrations before applying -- Alembic sometimes misses indexes or gets the order wrong on complex changes.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My blog's post listing page is getting slow. It takes about 2 seconds to load. The query fetches posts with author info, comment count, and like count.
Assistant: That sounds like an N+1 query problem or missing indexes. Can you share the query you're running?

User: Here it is:
SELECT p.*, u.username,
    (SELECT COUNT(*) FROM comments WHERE post_id = p.id) as comment_count,
    (SELECT COUNT(*) FROM post_likes WHERE post_id = p.id) as like_count
FROM posts p
JOIN users u ON p.author_id = u.id
WHERE p.published = TRUE
ORDER BY p.created_at DESC
LIMIT 20 OFFSET 0;
Assistant: The correlated subqueries for comment_count and like_count run once per row. Let me rewrite this with JOINs and check your indexes.

[Current message]
User: Yes please rewrite it. Also, EXPLAIN ANALYZE shows a sequential scan on posts even though I have an index on created_at. What's going on?''',
        "output": r'''Building on the query we looked at, here are both fixes:

First, the rewritten query using lateral joins instead of correlated subqueries:

```sql
SELECT p.id, p.title, p.slug, p.created_at,
       u.username AS author_name,
       COALESCE(c.cnt, 0) AS comment_count,
       COALESCE(l.cnt, 0) AS like_count
FROM posts p
JOIN users u ON p.author_id = u.id
LEFT JOIN (
    SELECT post_id, COUNT(*) AS cnt
    FROM comments
    GROUP BY post_id
) c ON c.post_id = p.id
LEFT JOIN (
    SELECT post_id, COUNT(*) AS cnt
    FROM post_likes
    GROUP BY post_id
) l ON l.post_id = p.id
WHERE p.published = TRUE
ORDER BY p.created_at DESC
LIMIT 20 OFFSET 0;
```

This aggregates counts once per table instead of once per row. For 20 posts with ~100 comments each, that goes from 40 subqueries to 2 grouped scans.

Now, about the sequential scan despite having an index on created_at -- the problem is your WHERE clause. PostgreSQL needs a **composite index** that covers both the filter and the sort:

```sql
-- This index covers WHERE published = TRUE ORDER BY created_at DESC
CREATE INDEX idx_posts_published_created
ON posts(published, created_at DESC);
```

Why your existing index on created_at alone was ignored: PostgreSQL's query planner estimated it would be cheaper to do a sequential scan + filter + sort than to use the created_at index (which would still need to check `published` for every row). With the composite index, it can skip non-published rows and read in sorted order simultaneously.

Verify the fix:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT p.id, p.title, p.slug, p.created_at
FROM posts p
WHERE p.published = TRUE
ORDER BY p.created_at DESC
LIMIT 20;
```

You should see "Index Scan Backward" instead of "Seq Scan". If you still see a seq scan on a small table, that is fine -- PostgreSQL correctly prefers seq scan when the table fits in a few pages. It will switch to the index as data grows.

Also ensure you have indexes on the foreign keys used in the joins:

```sql
CREATE INDEX IF NOT EXISTS idx_comments_post_id ON comments(post_id);
CREATE INDEX IF NOT EXISTS idx_post_likes_post_id ON post_likes(post_id);
```'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I'm prototyping a new feature locally using SQLite before deploying to PostgreSQL in production. What are the main gotchas I should watch out for?
Assistant: The biggest differences are: SQLite uses dynamic typing (no strict type enforcement), lacks ALTER TABLE support for dropping columns (before 3.35), has no native TIMESTAMP type, and handles concurrency with file-level locking instead of row-level. I'd suggest writing your queries in a common SQL subset and testing on both.

User: Good to know. I wrote this SQLite query locally and it works, but it uses GROUP_CONCAT. Will that work in PostgreSQL?
Assistant: No -- PostgreSQL uses string_agg() or array_agg() instead of GROUP_CONCAT. You'll need to adjust those queries.

[Current message]
User: Can you give me a compatibility layer? I want my Python code to work with both SQLite and PostgreSQL without rewriting queries everywhere.''',
        "output": r'''Since we identified GROUP_CONCAT vs string_agg as one of the pain points, let's build a proper abstraction layer that handles the key differences between SQLite and PostgreSQL.

```python
import os
from contextlib import contextmanager

class DatabaseAdapter:
    # Adapts queries and connections for SQLite or PostgreSQL

    def __init__(self, db_url=None):
        self.db_url = db_url or os.environ.get('DATABASE_URL', 'sqlite:///local.db')
        self.is_postgres = self.db_url.startswith('postgres')
        self._conn = None

    def connect(self):
        if self.is_postgres:
            import psycopg2
            self._conn = psycopg2.connect(self.db_url)
        else:
            import sqlite3
            db_path = self.db_url.replace('sqlite:///', '')
            self._conn = sqlite3.connect(db_path)
            self._conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrent reads
            self._conn.execute('PRAGMA journal_mode=WAL')
        return self._conn

    @contextmanager
    def transaction(self):
        conn = self._conn or self.connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def group_concat(self, column, separator=', '):
        # Returns the right aggregation syntax per database
        if self.is_postgres:
            return "string_agg(%s::text, '%s')" % (column, separator)
        return "GROUP_CONCAT(%s, '%s')" % (column, separator)

    def placeholder(self):
        # PostgreSQL uses %s, SQLite uses ?
        return '%s' if self.is_postgres else '?'

    def upsert(self, table, columns, conflict_col):
        # Builds an upsert statement for either database
        ph = self.placeholder()
        cols = ', '.join(columns)
        vals = ', '.join([ph] * len(columns))
        updates = ', '.join(
            '%s = EXCLUDED.%s' % (c, c) for c in columns if c != conflict_col
        )

        if self.is_postgres:
            return (
                "INSERT INTO %s (%s) VALUES (%s) "
                "ON CONFLICT (%s) DO UPDATE SET %s"
                % (table, cols, vals, conflict_col, updates)
            )
        else:
            return (
                "INSERT INTO %s (%s) VALUES (%s) "
                "ON CONFLICT (%s) DO UPDATE SET %s"
                % (table, cols, vals, conflict_col, updates)
            )
            # SQLite 3.24+ supports the same ON CONFLICT syntax

    def now_expr(self):
        if self.is_postgres:
            return "NOW()"
        return "datetime('now')"

    def boolean_val(self, val):
        if self.is_postgres:
            return 'TRUE' if val else 'FALSE'
        return '1' if val else '0'
```

Usage in your application code:

```python
db = DatabaseAdapter()  # reads DATABASE_URL
db.connect()

# Build a portable query
tags_agg = db.group_concat('t.name')
pub_val = db.boolean_val(True)
query = (
    "SELECT p.title, %s AS tags "
    "FROM posts p "
    "LEFT JOIN post_tags pt ON p.id = pt.post_id "
    "LEFT JOIN tags t ON pt.tag_id = t.id "
    "WHERE p.published = %s "
    "GROUP BY p.id, p.title "
    "ORDER BY p.created_at DESC"
) % (tags_agg, pub_val)

with db.transaction() as conn:
    results = conn.execute(query).fetchall()
```

Set `DATABASE_URL=sqlite:///local.db` for local dev and `DATABASE_URL=postgresql://user:pass@host/dbname` in production. The adapter handles the syntax differences transparently.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: My blog has grown to 5 million posts and queries are getting slow even with indexes. I'm on a single PostgreSQL instance. What are my options for scaling?
Assistant: At 5M posts you have several options: table partitioning (split posts by date range), read replicas for distributing read load, connection pooling with PgBouncer, and denormalization of hot data. Let's figure out which bottleneck you're hitting first. What does your query load look like -- mostly reads or writes?

User: 95% reads, 5% writes. The main bottleneck is the posts listing page and search. We get about 1000 requests per second.
Assistant: For a read-heavy workload like that, I'd start with read replicas and connection pooling. That alone could handle 4-5x your current load. Let me walk you through the setup.

[Current message]
User: Let's start with connection pooling. I'm currently using psycopg2 directly in my Flask app. How do I add PgBouncer?''',
        "output": r'''Since your workload is 95% reads at 1000 rps, connection pooling will give you the biggest immediate win. Right now each Flask request probably opens its own PostgreSQL connection, which is expensive (each connection uses ~5-10MB of RAM on the server).

Step 1 -- Install and configure PgBouncer:

```ini
; /etc/pgbouncer/pgbouncer.ini

[databases]
blogdb = host=127.0.0.1 port=5432 dbname=blogdb

[pgbouncer]
listen_addr = 127.0.0.1
listen_port = 6432
auth_type = md5
auth_file = /etc/pgbouncer/userlist.txt

; Transaction pooling -- connections are returned to the pool
; after each transaction, not after disconnect
pool_mode = transaction

; Max connections PgBouncer opens to PostgreSQL
default_pool_size = 20
max_client_conn = 200
min_pool_size = 5

; Timeout settings
server_idle_timeout = 300
client_idle_timeout = 0
```

```ini
; /etc/pgbouncer/userlist.txt
"bloguser" "md5hashofpassword"
```

Step 2 -- Update your Flask app to connect through PgBouncer:

```python
# config.py
import os

# Point at PgBouncer (port 6432) instead of PostgreSQL directly (5432)
DATABASE_URL = os.environ.get(
    'DATABASE_URL',
    'postgresql://bloguser:password@127.0.0.1:6432/blogdb'
)
```

Step 3 -- Add application-level connection pooling with SQLAlchemy:

```python
# database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

engine = create_engine(
    DATABASE_URL,
    pool_size=10,          # SQLAlchemy's own pool
    max_overflow=5,        # Extra connections when pool is full
    pool_pre_ping=True,    # Verify connections are alive
    pool_recycle=300,      # Recycle connections every 5 min
)

Session = scoped_session(sessionmaker(bind=engine))

# Flask integration
def init_app(app):
    @app.teardown_appcontext
    def close_session(exception=None):
        Session.remove()
```

The two layers work together: SQLAlchemy pools connections to PgBouncer, and PgBouncer pools connections to PostgreSQL. With `pool_mode = transaction`, PgBouncer can multiplex 200 client connections onto just 20 real PostgreSQL connections. This is the right mode for your read-heavy workload since most transactions are short SELECT queries.

Monitor with: `psql -h 127.0.0.1 -p 6432 pgbouncer -c "SHOW POOLS;"` to verify utilization.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I set up PgBouncer and it helped a lot. Now I want to add read replicas. How does PostgreSQL streaming replication work?
Assistant: PostgreSQL streaming replication continuously ships WAL (Write-Ahead Log) records from the primary to replicas. The replica replays these records to stay in sync. Setup involves configuring the primary to allow replication connections and the replica to connect and follow the primary.

User: Makes sense. I have a second server ready. Walk me through setting up the replica.
Assistant: On the primary, edit postgresql.conf to set wal_level=replica, max_wal_senders=3, and create a replication user. On the replica, use pg_basebackup to copy the data directory, then configure it as a standby. I showed you the primary config changes.

[Current message]
User: OK the primary is configured. Now show me the replica side -- how do I run pg_basebackup and configure the standby?''',
        "output": r'''Since you already configured the primary with wal_level=replica and the replication user, here's the replica side setup.

Step 1 -- Take a base backup from the primary:

```bash
# On the replica server, stop PostgreSQL first
sudo systemctl stop postgresql

# Remove the existing data directory (or move it as backup)
sudo rm -rf /var/lib/postgresql/16/main/*

# Run pg_basebackup as the postgres user
sudo -u postgres pg_basebackup \
    -h primary-server-ip \
    -U replication_user \
    -D /var/lib/postgresql/16/main \
    -Fp -Xs -P -R

# -Fp: plain format (direct copy)
# -Xs: stream WAL during backup for consistency
# -P: show progress
# -R: auto-create standby.signal and connection config
```

The `-R` flag is key -- it creates two things automatically:
- `standby.signal` file (tells PostgreSQL this is a replica)
- Adds `primary_conninfo` to `postgresql.auto.conf`

Step 2 -- Verify and tune the replica config:

```bash
# Check what -R generated
cat /var/lib/postgresql/16/main/postgresql.auto.conf
```

You should see something like:

```
primary_conninfo = 'host=primary-server-ip port=5432 user=replication_user password=xxx'
```

Add these to `postgresql.conf` on the replica:

```ini
# /etc/postgresql/16/main/postgresql.conf

# Allow read queries on the replica
hot_standby = on

# How much WAL to keep if replica falls behind
max_standby_streaming_delay = 30s

# Feedback to primary about replay progress
hot_standby_feedback = on
```

Step 3 -- Start the replica:

```bash
sudo systemctl start postgresql

# Verify replication is working
sudo -u postgres psql -c "SELECT pg_is_in_recovery();"
# Should return: t (true = this is a replica)

# On the PRIMARY, check replication status:
sudo -u postgres psql -c "SELECT client_addr, state, sent_lsn, replay_lsn FROM pg_stat_replication;"
```

Step 4 -- Route reads to the replica in your app:

```python
# Update your database.py to use separate engines
from sqlalchemy import create_engine

primary_engine = create_engine('postgresql://user:pass@primary:6432/blogdb')
replica_engine = create_engine('postgresql://user:pass@replica:6432/blogdb')

# In your Flask route handlers:
# Use primary_engine for writes, replica_engine for reads
```

The replica will typically be 0-100ms behind the primary. For a blog, that lag is invisible to users.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I need to add full-text search to my blog. Right now I'm using LIKE '%keyword%' and it's very slow on 5 million posts.
Assistant: LIKE with leading wildcards can't use B-tree indexes -- it always does a sequential scan. PostgreSQL has built-in full-text search using tsvector and tsquery. It's powerful enough that you may not need Elasticsearch.

[Current message]
User: Show me how to set up PostgreSQL full-text search on my posts table. I want to search title and body together, with title matches ranked higher.''',
        "output": r'''Building on the posts table from our schema, here's how to set up weighted full-text search.

Step 1 -- Add a tsvector column and keep it updated:

```sql
-- Add the search vector column
ALTER TABLE posts ADD COLUMN search_vector tsvector;

-- Create a GIN index for fast lookups
CREATE INDEX idx_posts_search ON posts USING GIN(search_vector);

-- Populate it with weighted vectors
-- 'A' weight for title (highest), 'B' weight for body
UPDATE posts SET search_vector =
    setweight(to_tsvector('english', COALESCE(title, '')), 'A') ||
    setweight(to_tsvector('english', COALESCE(body, '')), 'B');

-- Keep it updated automatically with a trigger
CREATE OR REPLACE FUNCTION posts_search_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', COALESCE(NEW.title, '')), 'A') ||
        setweight(to_tsvector('english', COALESCE(NEW.body, '')), 'B');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_posts_search_update
    BEFORE INSERT OR UPDATE OF title, body ON posts
    FOR EACH ROW EXECUTE FUNCTION posts_search_update();
```

Step 2 -- Query with ranking:

```sql
-- Basic search
SELECT id, title,
       ts_rank_cd(search_vector, query) AS rank
FROM posts, plainto_tsquery('english', 'python web framework') AS query
WHERE search_vector @@ query
  AND published = TRUE
ORDER BY rank DESC
LIMIT 20;
```

Step 3 -- Add highlighted snippets:

```sql
SELECT id, title,
       ts_headline('english', body, query,
           'StartSel=<mark>, StopSel=</mark>, MaxWords=50, MinWords=20'
       ) AS snippet,
       ts_rank_cd(search_vector, query) AS rank
FROM posts, plainto_tsquery('english', 'python web framework') AS query
WHERE search_vector @@ query
  AND published = TRUE
ORDER BY rank DESC
LIMIT 20;
```

Step 4 -- Python integration:

```python
def search_posts(query_text, page=1, per_page=20):
    offset = (page - 1) * per_page
    sql = """
        SELECT p.id, p.title, p.slug, u.username,
               ts_headline('english', p.body, query,
                   'StartSel=<mark>, StopSel=</mark>, MaxWords=50'
               ) AS snippet,
               ts_rank_cd(p.search_vector, query) AS rank
        FROM posts p
        JOIN users u ON p.author_id = u.id,
             plainto_tsquery('english', %s) AS query
        WHERE p.search_vector @@ query
          AND p.published = TRUE
        ORDER BY rank DESC
        LIMIT %s OFFSET %s
    """
    return db.execute(sql, [query_text, per_page, offset]).fetchall()
```

The weights mean a title match for "python" scores higher than a body match. The GIN index makes this orders of magnitude faster than your LIKE queries -- expect sub-10ms response times even on 5 million rows.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I'm using PostgreSQL partitioning for my posts table since it has 50 million rows now. I partitioned by created_at using range partitioning with monthly partitions.
Assistant: Good choice for time-series data. Monthly partitions let PostgreSQL skip entire partitions when queries filter by date. Make sure you have a partition creation strategy -- either create them ahead of time or use pg_partman to automate it.

User: I set up pg_partman and it's creating monthly partitions automatically. But I have a problem -- queries that don't filter by created_at are now slower because they scan ALL partitions.
Assistant: That's the main tradeoff with range partitioning. Queries without the partition key in the WHERE clause hit every partition. You have a few options: add a default date filter, create additional indexes, or consider a different partitioning strategy for those queries.

[Current message]
User: Most of my slow queries are "find posts by author_id" and "find posts by category_id". These don't use created_at at all. What can I do?''',
        "output": r'''Since your partitioning is by created_at but the slow queries filter by author_id and category_id, you need to address partition pruning for those access patterns. Here are three approaches, from simplest to most involved:

Approach 1 -- Add partition-level indexes (simplest fix):

```sql
-- Create indexes on each partition for the common query patterns
-- pg_partman can auto-create these on new partitions

-- For existing partitions, create indexes:
DO $$
DECLARE
    part_name TEXT;
BEGIN
    FOR part_name IN
        SELECT inhrelid::regclass::text
        FROM pg_inherits
        WHERE inhparent = 'posts'::regclass
    LOOP
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON %I (author_id, created_at DESC)',
            part_name || '_author_idx', part_name
        );
        EXECUTE format(
            'CREATE INDEX IF NOT EXISTS %I ON %I (category_id, created_at DESC)',
            part_name || '_category_idx', part_name
        );
    END LOOP;
END $$;
```

This still scans all partitions, but each partition scan uses an index instead of a sequential scan. Often good enough.

Approach 2 -- Force partition pruning by adding a date bound:

```sql
-- Instead of: SELECT * FROM posts WHERE author_id = 42
-- Add a reasonable date bound:
SELECT * FROM posts
WHERE author_id = 42
  AND created_at >= NOW() - INTERVAL '2 years'
ORDER BY created_at DESC
LIMIT 50;
```

This prunes old partitions. If users rarely look at posts older than 2 years, this is a practical fix.

Approach 3 -- Maintain a lightweight lookup table:

```sql
CREATE TABLE author_post_index (
    author_id INTEGER NOT NULL,
    post_id INTEGER NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (author_id, created_at, post_id)
);

CREATE INDEX idx_category_posts ON author_post_index(author_id);

-- Keep it updated with a trigger on the partitioned posts table
CREATE OR REPLACE FUNCTION sync_author_post_index() RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO author_post_index (author_id, post_id, created_at)
        VALUES (NEW.author_id, NEW.id, NEW.created_at);
    ELSIF TG_OP = 'DELETE' THEN
        DELETE FROM author_post_index
        WHERE post_id = OLD.id AND author_id = OLD.author_id;
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
```

Query pattern becomes a two-step lookup:

```sql
SELECT p.* FROM posts p
WHERE p.id IN (
    SELECT post_id FROM author_post_index
    WHERE author_id = 42
    ORDER BY created_at DESC LIMIT 50
) AND p.created_at >= '2024-01-01';  -- helps with pruning
```

For your situation with 50M rows, I would start with Approach 1 + 2 combined. Add indexes to each partition and modify your application queries to include a date bound. That avoids the complexity of maintaining a separate index table.'''
    },
    {
        "instruction": r'''[Previous conversation]
User: I want to add a "drafts" feature to my blog where users can save drafts that auto-save every 30 seconds. I'm worried about the write load on PostgreSQL since we have 10,000 active users.
Assistant: Auto-save every 30 seconds for 10K users means up to ~333 writes/second for drafts alone. For PostgreSQL that's manageable but you should optimize the approach. Options include: using UPSERT to avoid separate insert/update logic, batching saves, or using Redis for the hot draft data and syncing to PostgreSQL periodically.

User: I like the Redis idea for hot data. But I'm worried about losing drafts if Redis crashes.
Assistant: Valid concern. The standard pattern is write-behind caching: save to Redis immediately (fast) and flush to PostgreSQL every few minutes or on explicit save. You can also use Redis persistence (RDB snapshots or AOF) as a safety net.

[Current message]
User: Show me how to implement this write-behind pattern for auto-saving drafts with Redis and PostgreSQL.''',
        "output": r'''Building on the Redis + PostgreSQL approach we discussed, here's a complete implementation of the write-behind draft system.

```python
import json
import time
import threading
import redis
import psycopg2
from psycopg2.extras import execute_values

r = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)

DB_DSN = 'postgresql://user:pass@localhost:5432/blogdb'

class DraftManager:
    DRAFT_KEY = 'draft:{user_id}'
    DIRTY_SET = 'drafts:dirty'
    FLUSH_INTERVAL = 60  # seconds

    def __init__(self):
        self._flush_thread = None
        self._running = False

    def save_draft(self, user_id, title, body, category_id=None):
        # Save to Redis immediately -- sub-millisecond response
        draft_data = {
            'user_id': str(user_id),
            'title': title,
            'body': body,
            'category_id': str(category_id) if category_id else '',
            'updated_at': str(time.time())
        }
        pipe = r.pipeline()
        pipe.hset(self.DRAFT_KEY.format(user_id=user_id), mapping=draft_data)
        # Mark this draft as needing a database flush
        pipe.sadd(self.DIRTY_SET, str(user_id))
        # Expire after 7 days if never flushed
        pipe.expire(self.DRAFT_KEY.format(user_id=user_id), 604800)
        pipe.execute()
        return True

    def get_draft(self, user_id):
        data = r.hgetall(self.DRAFT_KEY.format(user_id=user_id))
        if not data:
            # Fall back to PostgreSQL
            return self._load_from_db(user_id)
        return data

    def _load_from_db(self, user_id):
        conn = psycopg2.connect(DB_DSN)
        try:
            cur = conn.cursor()
            cur.execute(
                'SELECT title, body, category_id FROM drafts '
                'WHERE user_id = %s ORDER BY updated_at DESC LIMIT 1',
                (user_id,)
            )
            row = cur.fetchone()
            return {'title': row[0], 'body': row[1]} if row else None
        finally:
            conn.close()

    def flush_dirty_drafts(self):
        # Atomically grab all dirty user IDs and clear the set
        pipe = r.pipeline()
        pipe.smembers(self.DIRTY_SET)
        pipe.delete(self.DIRTY_SET)
        results = pipe.execute()
        dirty_user_ids = results[0]

        if not dirty_user_ids:
            return 0

        # Batch-read all dirty drafts from Redis
        draft_pipe = r.pipeline()
        for uid in dirty_user_ids:
            draft_pipe.hgetall(self.DRAFT_KEY.format(user_id=uid))
        drafts = draft_pipe.execute()

        # Batch-upsert to PostgreSQL
        conn = psycopg2.connect(DB_DSN)
        try:
            cur = conn.cursor()
            values = []
            for uid, draft in zip(dirty_user_ids, drafts):
                if draft:
                    values.append((
                        int(uid),
                        draft.get('title', ''),
                        draft.get('body', ''),
                        int(draft['category_id']) if draft.get('category_id') else None,
                    ))
            if values:
                execute_values(cur, """
                    INSERT INTO drafts (user_id, title, body, category_id, updated_at)
                    VALUES %s
                    ON CONFLICT (user_id)
                    DO UPDATE SET title = EXCLUDED.title,
                                  body = EXCLUDED.body,
                                  category_id = EXCLUDED.category_id,
                                  updated_at = NOW()
                """, values)
            conn.commit()
            return len(values)
        finally:
            conn.close()

    def start_flush_loop(self):
        self._running = True
        def loop():
            while self._running:
                time.sleep(self.FLUSH_INTERVAL)
                try:
                    count = self.flush_dirty_drafts()
                    if count:
                        print('Flushed %d drafts to PostgreSQL' % count)
                except Exception as e:
                    print('Flush error: %s' % e)
        self._flush_thread = threading.Thread(target=loop, daemon=True)
        self._flush_thread.start()
```

The dirty set pattern is key -- instead of scanning all Redis keys, we track exactly which drafts changed since the last flush. The batch upsert writes them all in one transaction, keeping PostgreSQL write load low regardless of how many users are auto-saving.'''
    },
]
