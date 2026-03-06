r"""Thinking-trace pairs: database schema code review and refactoring."""

PAIRS = [
    ("thinking/code-review", r'''Review this SQL schema and identify issues:

```sql
CREATE TABLE users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    username VARCHAR(50),
    email VARCHAR(100),
    password VARCHAR(64),
    role VARCHAR(20) DEFAULT 'user',
    created_at TIMESTAMP,
    last_login TIMESTAMP,
    profile_data TEXT,
    is_active TINYINT DEFAULT 1
);

CREATE TABLE orders (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    total FLOAT,
    status VARCHAR(20),
    shipping_address TEXT,
    billing_address TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    notes TEXT,
    discount FLOAT,
    tax FLOAT
);

CREATE TABLE order_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    order_id INT,
    product_name VARCHAR(200),
    product_price FLOAT,
    quantity INT,
    subtotal FLOAT
);

CREATE TABLE products (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(200),
    description TEXT,
    price FLOAT,
    category VARCHAR(100),
    stock INT,
    image_url VARCHAR(500)
);

CREATE TABLE reviews (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT,
    product_id INT,
    rating INT,
    comment TEXT,
    created_at TIMESTAMP
);
```''', r'''<think>
Let me analyze this database schema for normalization issues, missing constraints, data type problems, indexing gaps, and general design antipatterns.

Starting with the users table:
- password stored as VARCHAR(64) suggests raw hash storage but no salt column - potential security concern
- No UNIQUE constraint on username or email - allows duplicates
- No NOT NULL constraints on critical fields
- profile_data as TEXT is a schema smell - unstructured blob
- created_at has no DEFAULT

Orders table:
- user_id has no FOREIGN KEY constraint - referential integrity not enforced
- FLOAT for monetary values - classic precision error antipattern
- shipping_address and billing_address as TEXT - not normalized, should be a separate addresses table
- No index on user_id for lookups
- status as VARCHAR with no CHECK constraint

Order_items table:
- No foreign key to orders or products
- product_name and product_price duplicated from products table - partial denormalization without clear justification
- subtotal is a derived column (price * quantity) stored redundantly
- No composite unique constraint to prevent duplicate items

Products table:
- FLOAT for price again
- No index on category for filtering
- stock as INT with no CHECK constraint (could go negative)

Reviews table:
- No foreign keys defined
- rating has no CHECK constraint (could be 0, -5, or 999)
- No unique constraint preventing multiple reviews per user per product
</think>

## Code Review: E-Commerce Database Schema

### CRITICAL - Missing Foreign Key Constraints
None of the relationships between tables are enforced at the database level. `orders.user_id`, `order_items.order_id`, `reviews.user_id`, and `reviews.product_id` all lack FOREIGN KEY constraints. This means orphaned records can accumulate freely, destroying data integrity.

**Fix:**
```sql
ALTER TABLE orders ADD CONSTRAINT fk_orders_user
    FOREIGN KEY (user_id) REFERENCES users(id);
ALTER TABLE order_items ADD CONSTRAINT fk_items_order
    FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE CASCADE;
ALTER TABLE reviews ADD CONSTRAINT fk_reviews_user
    FOREIGN KEY (user_id) REFERENCES users(id);
ALTER TABLE reviews ADD CONSTRAINT fk_reviews_product
    FOREIGN KEY (product_id) REFERENCES products(id);
```

### CRITICAL - FLOAT for Monetary Values
Using FLOAT for `total`, `discount`, `tax`, `product_price`, and `subtotal` will cause rounding errors in financial calculations. `0.1 + 0.2 != 0.3` in floating point.

**Fix:** Use `DECIMAL(10, 2)` for all monetary columns.

### HIGH - Missing UNIQUE Constraints
`users.username` and `users.email` have no UNIQUE constraints, allowing duplicate accounts. `reviews` has no composite unique on `(user_id, product_id)` to prevent duplicate reviews.

### HIGH - Missing NOT NULL Constraints
Critical columns like `username`, `email`, `password`, `order.user_id`, `order_items.order_id` allow NULL values. This leads to incomplete, unusable records.

### HIGH - No Indexes on Foreign Keys or Filter Columns
`orders.user_id`, `order_items.order_id`, `reviews.product_id`, `products.category`, and `orders.status` all lack indexes. Queries joining or filtering on these columns will perform full table scans.

### MEDIUM - Password Storage Concerns
`password VARCHAR(64)` suggests a raw SHA-256 hash with no salt. Modern password hashing (bcrypt, argon2) produces longer outputs. Consider `VARCHAR(255)` and ensure the application uses a proper hashing algorithm with per-user salts.

### MEDIUM - Redundant Stored Calculations
`order_items.subtotal` is derivable from `product_price * quantity`. Storing it creates a risk of inconsistency. Either compute it in queries or use a generated column.

### LOW - Address Denormalization
Storing addresses as TEXT blobs in orders prevents reuse and makes address management difficult. Consider a separate `addresses` table with structured fields.'''),

    ("thinking/code-review", r'''Review this SQL migration and identify issues:

```sql
-- Migration: Add user preferences and notification system

ALTER TABLE users ADD COLUMN preferences JSON;
ALTER TABLE users ADD COLUMN phone VARCHAR(20);
ALTER TABLE users ADD COLUMN avatar_url VARCHAR(500);
ALTER TABLE users ADD COLUMN bio TEXT;
ALTER TABLE users ADD COLUMN timezone VARCHAR(50) DEFAULT 'UTC';

CREATE TABLE notifications (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    type VARCHAR(50) NOT NULL,
    title VARCHAR(200),
    body TEXT,
    data JSON,
    read_at TIMESTAMP NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE user_devices (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    device_token VARCHAR(500) NOT NULL,
    platform VARCHAR(20) NOT NULL,
    last_active TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE notification_preferences (
    user_id INT PRIMARY KEY,
    email_enabled BOOLEAN DEFAULT TRUE,
    push_enabled BOOLEAN DEFAULT TRUE,
    sms_enabled BOOLEAN DEFAULT FALSE,
    marketing_enabled BOOLEAN DEFAULT FALSE,
    digest_frequency VARCHAR(20) DEFAULT 'daily',
    quiet_hours_start TIME,
    quiet_hours_end TIME,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

-- Backfill existing users
INSERT INTO notification_preferences (user_id)
SELECT id FROM users;

-- Add indexes
CREATE INDEX idx_notifications_user ON notifications(user_id);
CREATE INDEX idx_notifications_created ON notifications(created_at);
CREATE INDEX idx_devices_user ON user_devices(user_id);
CREATE INDEX idx_devices_token ON user_devices(device_token);
```''', r'''<think>
Let me review this migration for safety, correctness, and design issues.

First, the ALTER TABLE statements:
- Adding 5 columns in separate ALTER statements to a potentially large users table. Each ALTER can lock the table (depending on engine/version). Should be combined or use online DDL.
- preferences as JSON is flexible but unvalidated
- No DEFAULT values specified for phone, avatar_url, bio - they will be NULL which is fine for optional fields

Notifications table:
- Uses BIGINT for id which is good for high-volume table
- Has foreign key and NOT NULL on user_id - good
- No ON DELETE CASCADE - what happens when user is deleted?
- No index on (user_id, read_at) for "unread notifications" query which will be extremely common
- No index on type for filtering by notification type

User devices table:
- device_token as VARCHAR(500) - should have UNIQUE constraint to prevent duplicate registrations
- No ON DELETE CASCADE for user deletion
- last_active has no default

Notification preferences:
- Using user_id as PRIMARY KEY is good (1:1 relationship)
- digest_frequency as VARCHAR with no CHECK constraint
- quiet_hours logic will need application-level handling

The backfill:
- INSERT INTO ... SELECT with no WHERE clause on a large users table could be slow and lock both tables
- No batching strategy
- If migration fails partway through, no rollback plan visible

Missing:
- No transaction wrapping
- No DOWN migration / rollback script
- The ALTER TABLE statements are not idempotent - running twice will error
- No partition strategy for notifications table which will grow very large
</think>

## Code Review: Notification System Migration

### CRITICAL - No Transaction Wrapping
This migration has no BEGIN/COMMIT transaction boundary. If it fails midway (e.g., during the backfill INSERT), the database will be in a partially migrated state that is difficult to recover from.

**Fix:**
```sql
START TRANSACTION;
-- all DDL and DML here
COMMIT;
```
Note: In MySQL, DDL statements cause implicit commits, so consider separating DDL and DML into distinct migration steps.

### CRITICAL - Table-Locking ALTER Statements
Five separate ALTER TABLE statements on `users` will each potentially lock the table. On a production database with millions of rows, this causes extended downtime.

**Fix:** Combine into a single ALTER or use pt-online-schema-change / gh-ost for zero-downtime migrations:
```sql
ALTER TABLE users
    ADD COLUMN preferences JSON,
    ADD COLUMN phone VARCHAR(20),
    ADD COLUMN avatar_url VARCHAR(500),
    ADD COLUMN bio TEXT,
    ADD COLUMN timezone VARCHAR(50) DEFAULT 'UTC';
```

### HIGH - Missing Cascade Deletes
Foreign keys on `notifications` and `user_devices` lack ON DELETE CASCADE. Deleting a user will either fail (if RESTRICT) or leave orphaned records depending on the default behavior.

### HIGH - Missing Index for Common Query Pattern
The most frequent query will be "get unread notifications for user." There is no composite index on `(user_id, read_at)` to support this efficiently.

**Fix:**
```sql
CREATE INDEX idx_notifications_unread ON notifications(user_id, read_at);
```

### HIGH - Unbatched Backfill on Large Table
`INSERT INTO notification_preferences SELECT id FROM users` will attempt to insert all rows in a single transaction. On a large users table, this can cause lock contention, replication lag, and memory pressure.

**Fix:** Batch the backfill in chunks of 1000-5000 rows.

### MEDIUM - No Unique Constraint on Device Token
`user_devices.device_token` has an index but no UNIQUE constraint. The same device token could be registered multiple times, causing duplicate push notifications.

### MEDIUM - No Rollback Script
There is no corresponding DOWN migration. If this migration needs to be reverted, there is no documented procedure.

### LOW - Non-Idempotent Migration
Running this migration twice will fail on the ADD COLUMN statements. Consider using IF NOT EXISTS guards for safety.'''),

    ("thinking/code-review", r'''Review this database query code and identify issues:

```python
import mysql.connector
from datetime import datetime, timedelta

class ReportGenerator:
    def __init__(self, db_config):
        self.conn = mysql.connector.connect(**db_config)

    def get_sales_report(self, start_date, end_date):
        cursor = self.conn.cursor()
        query = f"""
            SELECT
                p.name,
                p.category,
                SUM(oi.quantity) as total_sold,
                SUM(oi.subtotal) as total_revenue,
                COUNT(DISTINCT o.user_id) as unique_buyers
            FROM order_items oi
            JOIN orders o ON oi.order_id = o.id
            JOIN products p ON oi.product_id = p.id
            WHERE o.created_at BETWEEN '{start_date}' AND '{end_date}'
            AND o.status != 'cancelled'
            GROUP BY p.name, p.category
            ORDER BY total_revenue DESC
        """
        cursor.execute(query)
        results = cursor.fetchall()
        return results

    def get_user_activity(self, user_id):
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT * FROM orders WHERE user_id = {user_id}")
        orders = cursor.fetchall()

        for order in orders:
            cursor.execute(
                f"SELECT * FROM order_items WHERE order_id = {order[0]}"
            )
            order_items = cursor.fetchall()
            order = order + (order_items,)

        cursor.execute(
            f"SELECT * FROM reviews WHERE user_id = {user_id}"
        )
        reviews = cursor.fetchall()

        return {"orders": orders, "reviews": reviews}

    def get_low_stock_products(self, threshold=10):
        cursor = self.conn.cursor()
        query = f"SELECT * FROM products WHERE stock < {threshold}"
        cursor.execute(query)
        return cursor.fetchall()

    def update_product_stats(self):
        cursor = self.conn.cursor()
        products = cursor.execute("SELECT id FROM products")
        for product in cursor.fetchall():
            cursor.execute(f"""
                UPDATE products SET
                    total_sold = (
                        SELECT COALESCE(SUM(quantity), 0)
                        FROM order_items WHERE product_id = {product[0]}
                    ),
                    avg_rating = (
                        SELECT COALESCE(AVG(rating), 0)
                        FROM reviews WHERE product_id = {product[0]}
                    )
                WHERE id = {product[0]}
            """)
        self.conn.commit()

    def search_products(self, search_term):
        cursor = self.conn.cursor()
        query = f"""
            SELECT * FROM products
            WHERE name LIKE '%{search_term}%'
            OR description LIKE '%{search_term}%'
        """
        cursor.execute(query)
        return cursor.fetchall()

    def __del__(self):
        self.conn.close()
```''', r'''<think>
This code has severe issues. Let me analyze systematically.

SQL Injection:
Every single query uses f-strings to interpolate user input directly into SQL. This is the most critical vulnerability possible in database code. The search_products method is especially dangerous since search_term likely comes from user input. get_user_activity with user_id, get_low_stock_products with threshold - all injectable.

Connection management:
- Single connection created in __init__ and reused - no connection pooling
- Connection closed in __del__ which is unreliable (may never be called)
- No context manager support
- No connection health checking or reconnection logic
- Cursors are never closed

N+1 query problem:
- get_user_activity fetches all orders, then loops and queries order_items for each order individually. This is a classic N+1 pattern. Should use a JOIN or IN clause.

update_product_stats:
- Fetches all product IDs, then runs individual UPDATE for each one. On a table with 10,000 products, that is 10,001 queries. Should be a single UPDATE with subquery or JOIN.
- Each update is a separate query but only one commit at the end - if it fails midway, partial updates are committed or lost depending on autocommit setting.

Other issues:
- SELECT * used everywhere - fetches unnecessary columns
- No error handling at all
- Results returned as raw tuples, not dictionaries or objects
- get_user_activity modifies the loop variable `order` but this does not affect the original list
- No pagination on any query
- search_products uses LIKE with leading wildcard - cannot use indexes, full table scan every time
</think>

## Code Review: Database Report Generator

### CRITICAL - SQL Injection Vulnerabilities (Every Method)
Every single query in this class uses f-string interpolation to embed user input directly into SQL strings. This is exploitable in every method. The `search_products` method is especially dangerous as search terms likely come from end users.

**Example exploit:** `search_products("'; DROP TABLE products; --")`

**Fix:** Use parameterized queries everywhere:
```python
def search_products(self, search_term):
    cursor = self.conn.cursor()
    query = "SELECT id, name, price FROM products WHERE name LIKE %s OR description LIKE %s"
    pattern = f"%{search_term}%"
    cursor.execute(query, (pattern, pattern))
    return cursor.fetchall()
```

### CRITICAL - N+1 Query Pattern in get_user_activity
Fetches all orders, then executes a separate query for each order to get its items. For a user with 100 orders, this is 102 queries instead of 2.

**Fix:**
```python
cursor.execute(
    "SELECT oi.* FROM order_items oi "
    "JOIN orders o ON oi.order_id = o.id "
    "WHERE o.user_id = %s", (user_id,)
)
```

### CRITICAL - update_product_stats Runs N+1 Updates
Iterates every product and runs individual UPDATE statements. Replace with a single query:
```sql
UPDATE products p SET
    total_sold = (SELECT COALESCE(SUM(quantity), 0) FROM order_items WHERE product_id = p.id),
    avg_rating = (SELECT COALESCE(AVG(rating), 0) FROM reviews WHERE product_id = p.id);
```

### HIGH - Unsafe Connection and Cursor Management
Connection is created once in `__init__` and closed in `__del__`, which is unreliable in Python. Cursors are never closed, leaking resources. No connection pooling, no reconnection logic.

**Fix:** Use a connection pool and context managers:
```python
from mysql.connector.pooling import MySQLConnectionPool

class ReportGenerator:
    def __init__(self, db_config):
        self.pool = MySQLConnectionPool(pool_size=5, **db_config)
```

### HIGH - No Error Handling
No try/except blocks anywhere. A failed query will leave connections and cursors in an undefined state. No transaction rollback on failure.

### MEDIUM - SELECT * Everywhere
Fetching all columns wastes bandwidth and memory, and breaks if schema changes. Always specify needed columns explicitly.

### MEDIUM - Broken Loop Variable Assignment
In `get_user_activity`, `order = order + (order_items,)` reassigns the local loop variable but does not modify the `orders` list. The returned orders will not contain their items.

### LOW - No Pagination
All queries fetch unbounded result sets. `get_sales_report` and `search_products` could return millions of rows.'''),

    ("thinking/code-review", r'''Review this database index strategy and identify issues:

```sql
-- Indexes for e-commerce application
-- Users table
CREATE INDEX idx_users_email ON users(email);
CREATE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_created ON users(created_at);
CREATE INDEX idx_users_role ON users(role);
CREATE INDEX idx_users_active ON users(is_active);
CREATE INDEX idx_users_email_active ON users(email, is_active);
CREATE INDEX idx_users_role_active ON users(role, is_active);
CREATE INDEX idx_users_last_login ON users(last_login);

-- Orders table
CREATE INDEX idx_orders_user ON orders(user_id);
CREATE INDEX idx_orders_status ON orders(status);
CREATE INDEX idx_orders_created ON orders(created_at);
CREATE INDEX idx_orders_user_status ON orders(user_id, status);
CREATE INDEX idx_orders_user_created ON orders(user_id, created_at);
CREATE INDEX idx_orders_status_created ON orders(status, created_at);
CREATE INDEX idx_orders_user_status_created ON orders(user_id, status, created_at);
CREATE INDEX idx_orders_total ON orders(total);
CREATE INDEX idx_orders_updated ON orders(updated_at);

-- Order items table
CREATE INDEX idx_items_order ON order_items(order_id);
CREATE INDEX idx_items_product ON order_items(product_id);
CREATE INDEX idx_items_order_product ON order_items(order_id, product_id);
CREATE INDEX idx_items_quantity ON order_items(quantity);
CREATE INDEX idx_items_subtotal ON order_items(subtotal);

-- Products table
CREATE INDEX idx_products_name ON products(name);
CREATE INDEX idx_products_category ON products(category);
CREATE INDEX idx_products_price ON products(price);
CREATE INDEX idx_products_stock ON products(stock);
CREATE INDEX idx_products_category_price ON products(category, price);
CREATE INDEX idx_products_name_category ON products(name, category);
CREATE FULLTEXT INDEX idx_products_search ON products(name, description);

-- Reviews table
CREATE INDEX idx_reviews_user ON reviews(user_id);
CREATE INDEX idx_reviews_product ON reviews(product_id);
CREATE INDEX idx_reviews_rating ON reviews(rating);
CREATE INDEX idx_reviews_created ON reviews(created_at);
CREATE INDEX idx_reviews_product_rating ON reviews(product_id, rating);
CREATE INDEX idx_reviews_user_product ON reviews(user_id, product_id);
```''', r'''<think>
Let me analyze this indexing strategy for over-indexing, redundancy, missing indexes, and column ordering issues.

Over-indexing is a major concern here. Every table has a large number of indexes. Let me count:
- users: 8 indexes
- orders: 9 indexes
- order_items: 5 indexes
- products: 7 indexes (including fulltext)
- reviews: 6 indexes

Total: 35 indexes across 5 tables. This is excessive.

Redundant indexes:
- idx_users_email is redundant if email should have a UNIQUE constraint (which would create its own index)
- idx_users_username same issue
- idx_orders_user is a prefix of idx_orders_user_status and idx_orders_user_created and idx_orders_user_status_created. The composite indexes can serve queries that only filter on user_id.
- idx_orders_status is a prefix of idx_orders_status_created
- idx_orders_user_status is a prefix of idx_orders_user_status_created
- idx_items_order is a prefix of idx_items_order_product
- idx_reviews_product is a prefix of idx_reviews_product_rating

Low-selectivity indexes:
- idx_users_role: roles typically have very few distinct values (admin, user, moderator). Low cardinality index.
- idx_users_active: boolean column, only 2 values. Useless as standalone index.
- idx_orders_status: likely few distinct values
- idx_items_quantity: why index quantity? Rarely queried alone.
- idx_items_subtotal: same issue
- idx_reviews_rating: only 5 distinct values typically

Write amplification:
Every INSERT into orders must update 9 indexes. Every INSERT into order_items must update 5. For a high-write e-commerce system, this is a significant performance penalty.

Missing considerations:
- No covering indexes for common query patterns
- No partial/filtered indexes (though MySQL doesn't support them, PostgreSQL does)
- idx_products_name as B-tree index on a VARCHAR(200) is large and inefficient for prefix searches
</think>

## Code Review: Database Index Strategy

### CRITICAL - Severe Over-Indexing (35 Indexes on 5 Tables)
This schema has far too many indexes. Each index adds write overhead (INSERT, UPDATE, DELETE all must update every index), consumes disk space, and increases memory pressure on the buffer pool. An e-commerce system with high write volume on orders and order_items will suffer significant performance degradation.

**Recommendation:** Aim for 3-5 well-chosen indexes per table based on actual query patterns, not speculative coverage.

### HIGH - Redundant Prefix Indexes
Several indexes are strict prefixes of composite indexes and serve no purpose:

- `idx_orders_user` is redundant with `idx_orders_user_status_created` (leftmost prefix)
- `idx_orders_status` is redundant with `idx_orders_status_created`
- `idx_orders_user_status` is redundant with `idx_orders_user_status_created`
- `idx_items_order` is redundant with `idx_items_order_product`
- `idx_reviews_product` is redundant with `idx_reviews_product_rating`

**Fix:** Drop the prefix indexes. The composite index can serve both specific and prefix queries.

### HIGH - Low-Cardinality Indexes Are Wasteful
These indexes have very few distinct values and the optimizer will often ignore them in favor of table scans:
- `idx_users_role` (3-5 distinct values)
- `idx_users_active` (2 values: 0 or 1)
- `idx_orders_status` (5-10 distinct values)
- `idx_reviews_rating` (5 values: 1-5)
- `idx_items_quantity` and `idx_items_subtotal` (rarely queried alone)

**Fix:** Remove standalone low-cardinality indexes. They are only useful as secondary columns in composite indexes.

### MEDIUM - Missing UNIQUE Indexes Where Needed
`idx_users_email` and `idx_users_username` are regular indexes, not UNIQUE. If these should enforce uniqueness (they almost certainly should), use UNIQUE INDEX instead. The uniqueness constraint is more valuable than the index itself.

### MEDIUM - Composite Index Column Ordering
`idx_products_name_category` has name first, but most queries filter by category and then optionally by name. The index should be `(category, name)` to support category-only queries. The existing `idx_products_category_price` handles category+price but not category+name filtering.

### LOW - No Covering Indexes
For frequently executed queries (e.g., order list page showing status and date), a covering index that includes all selected columns would avoid table lookups entirely:
```sql
CREATE INDEX idx_orders_user_covering ON orders(user_id, status, created_at, total);
```

**Recommended minimal index set:**
```sql
-- Users: 3 indexes
CREATE UNIQUE INDEX idx_users_email ON users(email);
CREATE UNIQUE INDEX idx_users_username ON users(username);
CREATE INDEX idx_users_role_active ON users(role, is_active);

-- Orders: 2-3 indexes
CREATE INDEX idx_orders_user_status_created ON orders(user_id, status, created_at);
CREATE INDEX idx_orders_status_created ON orders(status, created_at);

-- Order items: 2 indexes
CREATE INDEX idx_items_order_product ON order_items(order_id, product_id);
CREATE INDEX idx_items_product ON order_items(product_id);

-- Products: 3 indexes
CREATE INDEX idx_products_category_price ON products(category, price);
CREATE FULLTEXT INDEX idx_products_search ON products(name, description);
CREATE INDEX idx_products_stock ON products(stock);

-- Reviews: 2 indexes
CREATE UNIQUE INDEX idx_reviews_user_product ON reviews(user_id, product_id);
CREATE INDEX idx_reviews_product_rating ON reviews(product_id, rating);
```'''),

    ("thinking/code-review", r'''Review this database migration safety script and identify issues:

```python
import pymysql
import time
import logging

logger = logging.getLogger(__name__)

class MigrationRunner:
    def __init__(self, host, user, password, database):
        self.conn = pymysql.connect(
            host=host, user=user, password=password,
            database=database, autocommit=True
        )

    def add_column(self, table, column, col_type, default=None):
        sql = f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
        if default is not None:
            sql += f" DEFAULT {default}"
        self.conn.cursor().execute(sql)
        logger.info(f"Added column {column} to {table}")

    def drop_column(self, table, column):
        self.conn.cursor().execute(
            f"ALTER TABLE {table} DROP COLUMN {column}"
        )
        logger.info(f"Dropped column {column} from {table}")

    def rename_table(self, old_name, new_name):
        self.conn.cursor().execute(
            f"RENAME TABLE {old_name} TO {new_name}"
        )
        logger.info(f"Renamed {old_name} to {new_name}")

    def add_index(self, table, columns, index_name=None):
        cols = ", ".join(columns)
        name = index_name or f"idx_{table}_{'_'.join(columns)}"
        self.conn.cursor().execute(
            f"CREATE INDEX {name} ON {table}({cols})"
        )
        logger.info(f"Created index {name}")

    def backfill_column(self, table, column, value, batch_size=10000):
        while True:
            cursor = self.conn.cursor()
            cursor.execute(
                f"UPDATE {table} SET {column} = {value} "
                f"WHERE {column} IS NULL LIMIT {batch_size}"
            )
            affected = cursor.rowcount
            logger.info(f"Updated {affected} rows in {table}")
            if affected < batch_size:
                break

    def run_migration(self, migration_sql):
        statements = migration_sql.split(';')
        for stmt in statements:
            stmt = stmt.strip()
            if stmt:
                self.conn.cursor().execute(stmt)
                logger.info(f"Executed: {stmt[:100]}")

    def check_table_size(self, table):
        cursor = self.conn.cursor()
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        return count

    def validate_migration(self, table, expected_columns):
        cursor = self.conn.cursor()
        cursor.execute(f"DESCRIBE {table}")
        actual_columns = {row[0] for row in cursor.fetchall()}
        missing = set(expected_columns) - actual_columns
        if missing:
            raise Exception(f"Missing columns: {missing}")
        logger.info(f"Migration validated for {table}")

    def rollback_migration(self, rollback_sql):
        self.run_migration(rollback_sql)
        logger.info("Rollback completed")
```''', r'''<think>
Let me analyze this migration runner for safety, correctness, and operational issues.

SQL Injection:
Every method uses f-strings to build SQL. While table/column names cannot use parameterized queries directly, there is zero validation or sanitization. If any of these values come from user input or configuration files, SQL injection is possible. Table and column names should be validated against a whitelist or escaped using backtick quoting.

autocommit=True:
The connection is created with autocommit=True. This means every statement is immediately committed. For multi-step migrations, there is no atomicity. If step 3 of 5 fails, steps 1-2 are already committed and cannot be rolled back.

backfill_column issues:
- No sleep/throttle between batches - will hammer the database continuously
- Uses f-string for the value parameter - SQL injection
- No progress tracking or estimated completion time
- If the connection drops mid-backfill, there is no recovery mechanism
- The WHERE clause with IS NULL will do a full table scan each iteration if there is no index on the column

Cursor management:
- Cursors created but never closed (self.conn.cursor().execute(...))
- No context manager usage
- No error handling or cleanup

run_migration:
- Splits on semicolon which will break if SQL contains semicolons in string literals
- No transaction wrapping
- No dry-run mode
- Executes arbitrary SQL with no validation

check_table_size:
- SELECT COUNT(*) on large tables is very slow in InnoDB (requires full table scan)
- Should use information_schema.tables for an estimate

Missing features:
- No migration versioning or tracking
- No lock timeout handling
- No deadlock retry logic
- No pre-migration backup
- No dry-run mode
- No idempotency checks
- rollback_migration just calls run_migration with different SQL - no actual rollback semantics
</think>

## Code Review: Database Migration Runner

### CRITICAL - SQL Injection in All Methods
Every method constructs SQL via f-strings with no input validation. While table/column names cannot use standard parameterized queries, there is no sanitization or allowlist checking. The `backfill_column` method is especially dangerous as the `value` parameter could be arbitrary user input.

**Fix:** Validate identifiers against a regex pattern and quote them:
```python
import re

def _validate_identifier(self, name):
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        raise ValueError(f"Invalid SQL identifier: {name}")
    return f"`{name}`"
```

### CRITICAL - autocommit=True Breaks Migration Atomicity
With autocommit enabled, each statement is immediately committed. A multi-step migration that fails partway through leaves the database in a partially migrated state with no rollback possible. The `rollback_migration` method is misleading -- it does not actually roll back; it runs forward-only compensating SQL.

**Fix:** Use `autocommit=False` and explicit transaction management:
```python
def run_migration(self, migration_sql):
    try:
        self.conn.begin()
        # execute statements
        self.conn.commit()
    except Exception:
        self.conn.rollback()
        raise
```

### HIGH - Unbatched Backfill Has No Throttling
`backfill_column` runs UPDATE loops with no pause between iterations. On a large table, this will saturate I/O, spike replication lag, and potentially lock out other queries. There is also no progress reporting beyond row counts.

**Fix:** Add a configurable sleep between batches and progress logging:
```python
def backfill_column(self, table, column, value, batch_size=10000, sleep_seconds=0.5):
    total_updated = 0
    while True:
        # ... execute batch
        total_updated += affected
        logger.info(f"Progress: {total_updated} rows updated")
        if affected < batch_size:
            break
        time.sleep(sleep_seconds)
```

### HIGH - Cursors Never Closed
Every method creates a cursor with `self.conn.cursor().execute(...)` but never closes it. Over many operations, this leaks server-side resources. Use context managers or explicit close() calls.

### HIGH - SQL Splitting on Semicolon Is Fragile
`run_migration` splits SQL on `;` which breaks when SQL contains semicolons inside string literals, stored procedures, or trigger definitions. Use a proper SQL parser or require migrations to be provided as lists of individual statements.

### MEDIUM - check_table_size Uses COUNT(*)
`SELECT COUNT(*) FROM table` on InnoDB requires a full table scan. For large tables, this can take minutes. Use `information_schema.tables` for an approximate count:
```sql
SELECT TABLE_ROWS FROM information_schema.tables
WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
```

### MEDIUM - No Migration Tracking or Versioning
There is no record of which migrations have been applied. Running the same migration twice will fail or corrupt data. Add a `schema_migrations` table to track applied versions.

### LOW - No Dry-Run Mode
There is no way to preview what a migration will do without executing it. Add a `dry_run` parameter that logs statements without executing them.'''),
]
