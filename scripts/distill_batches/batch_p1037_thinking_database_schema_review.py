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
Let me analyze this database schema systematically.

Starting with the users table -- password is VARCHAR(64). That length suggests a raw SHA-256 hash. Could this be a bcrypt hash? No, bcrypt produces 60 characters and is usually stored in VARCHAR(255). A 64-character limit strongly implies unsalted SHA-256, which is a security concern. But wait, even if the application handles hashing correctly, there is no salt column, so the hashing is likely naive.

No UNIQUE constraint on username or email -- this means duplicate accounts are possible at the database level. I considered whether the application layer might enforce uniqueness... but that is a race condition waiting to happen. Two concurrent registrations with the same email could both pass the application check and both insert. UNIQUE constraints must be at the database level. Also no NOT NULL on critical fields like username and email, so rows with NULL usernames are valid.

The orders table uses FLOAT for total, discount, and tax. Could FLOAT be acceptable here? Actually no -- this is the classic floating-point precision antipattern. 0.1 + 0.2 != 0.3 in IEEE 754. For monetary values, DECIMAL(10, 2) is mandatory. The same issue appears in order_items.product_price and order_items.subtotal, and products.price.

Hmm, none of the foreign key relationships are actually defined. orders.user_id, order_items.order_id, reviews.user_id, reviews.product_id -- all are just bare INT columns with no FOREIGN KEY constraint. Orphaned records can accumulate freely since there is nothing preventing deletion of a user who has orders.

The order_items table has product_name and product_price columns that duplicate data from products. I initially thought this might be intentional denormalization to capture the price at time of purchase... and actually that is a valid reason for product_price. But there should still be a foreign key to products.id for traceability, and subtotal is purely derived (price * quantity) with no justification for storage.

The reviews table has no CHECK constraint on rating -- values like -5 or 999 are valid. No unique constraint on (user_id, product_id) either, so a user can submit unlimited reviews for the same product. And products.stock has no CHECK (stock >= 0), meaning inventory can go negative.
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
Let me review this migration for safety and correctness issues.

The first thing I see is five separate ALTER TABLE statements on the users table. Each ALTER can lock the table depending on the MySQL version and storage engine. Could these run without locking on recent InnoDB? Actually, adding nullable columns without defaults is often an online operation in MySQL 5.6+... but wait, the timezone column has a DEFAULT value, and five separate ALTERs still means five schema operations. On a production table with millions of rows, this is risky. They should be combined into a single ALTER TABLE statement.

The notifications table uses BIGINT for id, which is good foresight for a high-volume table. But hmm, the foreign key on user_id has no ON DELETE CASCADE. What happens when a user is deleted? Depending on the default (RESTRICT), the delete will fail entirely. The most common query will be "get unread notifications for this user" -- but there is no composite index on (user_id, read_at). The existing idx_notifications_user only covers user_id, so filtering by read_at IS NULL still requires scanning all of that user's notifications.

The user_devices table has device_token as VARCHAR(500) with an index but no UNIQUE constraint. I initially thought multiple registrations of the same device might be intentional for different platforms... but no, a device token uniquely identifies a physical device. Without UNIQUE, the same token can be registered multiple times, causing duplicate push notifications.

The backfill INSERT INTO notification_preferences SELECT id FROM users runs unbatched across the entire users table. For a table with millions of rows, this creates a massive transaction that locks both tables, spikes replication lag, and could timeout. It should be batched in chunks of a few thousand rows.

There is no transaction wrapping around the entire migration, so a failure midway leaves the database partially migrated. Also no DOWN migration for rollback, and the ALTER TABLE statements are not idempotent -- running the migration twice will error on "duplicate column." The notification_preferences table is well-designed (user_id as PRIMARY KEY for 1:1), but digest_frequency has no CHECK constraint to validate allowed values.
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
This code has severe issues. Let me start with the most dangerous one.

Every single query uses f-strings to interpolate parameters directly into SQL. Could any of these be safe because the inputs are trusted? Let me check... get_sales_report takes start_date and end_date which could come from user input. search_products takes search_term which almost certainly comes from a form. get_user_activity takes user_id which could come from a URL parameter. Actually, even get_low_stock_products with threshold is injectable if the value comes from an API request. None of these use parameterized queries. search_products is especially dangerous since `search_term = "'; DROP TABLE products; --"` would execute arbitrary SQL.

For connection management, a single connection is created in __init__ and reused. I considered whether this might be acceptable for a simple script... but wait, this is a ReportGenerator class that could be used in a web application. No connection pooling, no reconnection logic, and cursors are created with `self.conn.cursor().execute(...)` but never closed. The connection is closed in __del__ which Python does not guarantee will ever be called -- if the process crashes or the object has circular references, the connection leaks.

get_user_activity is a classic N+1 pattern: fetch all orders, then for each order, query order_items individually. With 100 orders, that is 102 queries instead of a single JOIN. Also, `order = order + (order_items,)` reassigns the local loop variable but does not modify the original `orders` list. The returned orders will NOT contain their items -- this is a bug, not just a style issue.

update_product_stats is even worse -- it fetches all product IDs, then runs an individual UPDATE for each product. With 10,000 products, that is 10,001 queries when a single UPDATE with correlated subqueries would do. Hmm, also autocommit is not explicitly set, so whether partial updates persist on failure depends on the connection settings.

Other issues: SELECT * everywhere fetches unnecessary columns, no error handling, no pagination (get_sales_report could return millions of rows), and search_products uses LIKE with a leading wildcard which forces full table scans since B-tree indexes cannot optimize leading wildcards.
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
Let me analyze this indexing strategy. The first thing that jumps out is the sheer number of indexes.

Counting: users has 8 indexes, orders has 9, order_items has 5, products has 7 (including fulltext), reviews has 6. That is 35 indexes across 5 tables. Could this be justified for a read-heavy system? Hmm, maybe for a reporting database... but this is an e-commerce application with high write volume on orders and order_items. Every INSERT into orders must update 9 indexes. That is severe write amplification.

Let me check for redundancy. idx_orders_user is a leftmost prefix of idx_orders_user_status, idx_orders_user_created, AND idx_orders_user_status_created. Any query filtering only on user_id can use any of those composite indexes. So idx_orders_user is completely redundant. Wait, idx_orders_user_status is ALSO a prefix of idx_orders_user_status_created, making it redundant too. Similarly, idx_orders_status is a prefix of idx_orders_status_created, idx_items_order is a prefix of idx_items_order_product, and idx_reviews_product is a prefix of idx_reviews_product_rating. That is at least 5 purely redundant indexes.

Now for low-selectivity indexes. idx_users_role has maybe 3-5 distinct values. idx_users_active is boolean -- 2 values. The optimizer will almost always prefer a table scan over using an index with such low cardinality. I initially thought idx_orders_status might be useful since status queries are common... but actually with only 5-10 distinct values, the optimizer will ignore it for large tables. idx_items_quantity and idx_items_subtotal are puzzling -- why would you ever query "find all order items with quantity = 3"?

For column ordering, idx_products_name_category has name first. But most queries filter by category and optionally by name, not the other way around. The index should be (category, name) to support category-only queries. The existing idx_products_category_price handles category+price but not category+name.

Also idx_users_email and idx_users_username should be UNIQUE indexes, not regular indexes. The uniqueness constraint is more valuable than the performance benefit. Missing from this strategy: covering indexes for common queries, and no mention of the fulltext index for products being the only sensible way to handle product search.
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
Let me analyze this migration runner for safety and correctness.

Every method uses f-strings to build SQL from table/column names. I initially thought this might be unavoidable since parameterized queries only work for values, not identifiers... but actually there is zero validation or sanitization of the identifiers. If table or column names come from a config file or user input (which they often do in migration tools), SQL injection is possible. At minimum, identifiers should be validated against a regex pattern and backtick-quoted.

The connection is created with autocommit=True. Could this be intentional for DDL statements which auto-commit anyway in MySQL? Hmm, that is true for DDL (ALTER TABLE, CREATE INDEX), but the backfill_column method does DML (UPDATE), and run_migration could contain any mix of DDL and DML. With autocommit=True, there is no atomicity for multi-step migrations. If step 3 of 5 fails, steps 1-2 are already committed with no way to roll back. The rollback_migration method is misleading -- it does not actually roll back anything; it just runs forward-only compensating SQL.

The backfill_column method has several problems. It loops continuously with no sleep or throttle between batches, which will saturate database I/O and spike replication lag. Wait, the value parameter is also interpolated via f-string -- that is SQL injection on a value, not just an identifier. Also, the WHERE clause uses `column IS NULL` which requires scanning all rows to find nulls. Without an index on that column (which was just added, so no index exists), every batch iteration does a full table scan.

Cursors are created with `self.conn.cursor().execute(...)` and never closed -- the cursor reference is immediately discarded. Over many operations this leaks server-side resources. No context managers, no error handling, no cleanup.

run_migration splits SQL on semicolons, which breaks on any SQL containing semicolons in string literals or stored procedures. check_table_size uses SELECT COUNT(*) which requires a full table scan on InnoDB -- information_schema.tables would give an approximate count instantly. The tool also has no migration versioning, no idempotency checks, no dry-run mode, and no lock timeout handling.
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
