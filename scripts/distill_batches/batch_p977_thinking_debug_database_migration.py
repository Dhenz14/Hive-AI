PAIRS = [
    ("thinking/debugging", r'''We renamed a column in our database migration but lost all the data in that column:

```python
# Alembic migration
def upgrade():
    op.drop_column('users', 'email_address')
    op.add_column('users', sa.Column('email', sa.String(255)))

def downgrade():
    op.drop_column('users', 'email')
    op.add_column('users', sa.Column('email_address', sa.String(255)))
```

After running the migration:
```
$ alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade abc123 -> def456
INFO  [alembic.runtime.migration] OK

$ python -c "from app import db; print(db.session.execute('SELECT email FROM users LIMIT 5').fetchall())"
[(None,), (None,), (None,), (None,), (None,)]
```

All 50,000 users lost their email addresses. The column was dropped and a new empty column was created instead of being renamed.''', r'''<think>
This is a classic and devastating migration mistake. The developer wanted to rename a column from `email_address` to `email`, but instead of using a rename operation, they dropped the old column (deleting all data) and added a new empty column.

At first I wondered if Alembic might have a rename_column operation that was just missed... but wait, Alembic's autogenerate fundamentally cannot detect renames. Because it compares the current model schema against the database schema, it only sees "column X disappeared, column Y appeared" -- there is no way for it to infer that X was renamed to Y. So it generates drop + add, which destroys data.

I considered whether a downgrade could recover the data, but that won't work because the downgrade also uses drop + add. The data was destroyed the moment `drop_column` executed, and creating a new column in the downgrade just gives another empty column. Hmm, actually the only recovery path is from a backup or point-in-time recovery.

The correct approach is to use `op.alter_column()` with the `new_column_name` parameter, or raw SQL `ALTER TABLE ... RENAME COLUMN`. Because RENAME preserves the column's data, constraints, and indexes, it is a safe metadata-only operation that completes instantly regardless of table size.

Wait, I should also consider: what if the database does not support ALTER TABLE RENAME COLUMN? Older MySQL versions require creating a new column, copying data, then dropping the old one. But PostgreSQL, MySQL 8.0+, and SQLite 3.25+ all support it natively.
</think>

This is one of the most common and destructive migration mistakes. Dropping a column and adding a new one is NOT a rename -- it destroys all existing data. Alembic's autogenerate cannot detect renames and generates drop+add by default.

**The correct migration for renaming a column:**

```python
# CORRECT: Use alter_column to rename (preserves data)
def upgrade():
    op.alter_column('users', 'email_address', new_column_name='email')

def downgrade():
    op.alter_column('users', 'email', new_column_name='email_address')
```

**Or use raw SQL for databases where alter_column rename is not supported:**

```python
def upgrade():
    # PostgreSQL
    op.execute('ALTER TABLE users RENAME COLUMN email_address TO email')

def downgrade():
    op.execute('ALTER TABLE users RENAME COLUMN email TO email_address')
```

**Recovering the lost data:**

```bash
# Option 1: Point-in-time recovery (AWS RDS, Cloud SQL, etc.)
# Restore to a time just before the migration ran
aws rds restore-db-instance-to-point-in-time \
    --source-db-instance-identifier mydb \
    --target-db-instance-identifier mydb-recovery \
    --restore-time "2026-03-06T10:00:00Z"

# Then copy the data from the recovered instance:
pg_dump -h mydb-recovery -t users --column-inserts mydb > users_backup.sql
```

```python
# Option 2: Restore from backup and copy the column
# Connect to both the backup and live databases
import psycopg2

backup_conn = psycopg2.connect("host=backup-db dbname=myapp")
live_conn = psycopg2.connect("host=live-db dbname=myapp")

backup_cur = backup_conn.cursor()
live_cur = live_conn.cursor()

# Read emails from backup
backup_cur.execute("SELECT id, email_address FROM users")
rows = backup_cur.fetchall()

# Update live database
for user_id, email in rows:
    live_cur.execute("UPDATE users SET email = %s WHERE id = %s", (email, user_id))

live_conn.commit()
print(f"Restored {len(rows)} email addresses")
```

```python
# Option 3: If you have a recent logical backup (pg_dump)
# Create a temporary table, restore into it, then copy
def emergency_restore():
    op.execute("""
        CREATE TEMP TABLE users_backup AS
        SELECT id, email_address FROM users WHERE 1=0
    """)
    # Load from backup file into temp table, then:
    op.execute("""
        UPDATE users u SET email = b.email_address
        FROM users_backup b WHERE u.id = b.id
    """)
```

**Preventing this in the future:**

```python
# 1. Add a pre-migration check in your CI pipeline
import re

def check_migration_for_data_loss(migration_file):
    content = open(migration_file).read()
    # Flag drop_column followed by add_column on the same table
    drops = re.findall(r"op\.drop_column\('(\w+)', '(\w+)'\)", content)
    adds = re.findall(r"op\.add_column\('(\w+)',", content)

    for table, col in drops:
        if table in [t for t, in adds]:
            print(f"WARNING: {migration_file} drops column '{col}' from "
                  f"'{table}' and adds a new column. Did you mean to rename?")

# 2. Always review autogenerated migrations manually
# 3. Test migrations against a copy of production data first
# 4. Take a backup immediately before running migrations
```

**Prevention tips:**
- NEVER trust Alembic autogenerate for column renames -- it always generates drop+add
- Always manually review autogenerated migrations before running them
- Take a database snapshot/backup before every migration
- Test migrations on a staging database with production-like data first
- Add a CI check that flags `drop_column` operations for manual review
- Use `--sql` mode to preview the SQL before executing: `alembic upgrade head --sql`'''),

    ("thinking/debugging", r'''We need to add a NOT NULL constraint to an existing column that has NULL values in production. Our migration fails:

```python
# Alembic migration
def upgrade():
    op.alter_column('orders', 'customer_id',
                     existing_type=sa.Integer(),
                     nullable=False)

def downgrade():
    op.alter_column('orders', 'customer_id',
                     existing_type=sa.Integer(),
                     nullable=True)
```

Running the migration:
```
$ alembic upgrade head
sqlalchemy.exc.IntegrityError: (psycopg2.errors.NotNullViolation)
column "customer_id" of relation "orders" contains null values
```

We have 2 million orders, and about 15,000 of them have NULL customer_id (from legacy guest checkout orders).''', r'''<think>
The migration fails because you cannot add a NOT NULL constraint to a column that already contains NULL values. The database rejects it because the existing data violates the constraint.

My first instinct is to just add a DEFAULT value to the ALTER TABLE... but wait, that only helps for FUTURE inserts. The 15,000 existing NULL rows would still violate the constraint. Because the database validates ALL existing rows when adding NOT NULL, we need to handle the NULLs first.

I considered just deleting the 15,000 rows with NULL customer_id, but that won't work because those are real orders from guest checkouts -- deleting them would lose financial records. Hmm, actually the right approach depends on the business requirements: do we assign these to a placeholder "guest" customer, or do we set them to NULL and keep the column nullable?

Wait, I need to reconsider the performance implications too. With 2 million orders, a simple `UPDATE orders SET customer_id = 0 WHERE customer_id IS NULL` takes an exclusive lock on affected rows. Option A (single UPDATE) is simpler but locks the table during the update. Option B (batch updates in a loop) avoids long locks but takes longer. Option C (PostgreSQL NOT VALID constraint) is the most production-safe because it does not require a full table scan during ALTER TABLE.

The fix is a multi-step migration:
1. First, handle the existing NULL values (either set a default value or assign to a placeholder)
2. Then add the NOT NULL constraint
3. Use batched updates for large tables to avoid long-running locks
</think>

You cannot add a NOT NULL constraint to a column that already contains NULL values. The database validates ALL existing rows against the new constraint. You need a multi-step migration that handles existing NULLs first.

**The problem:** 15,000 orders have `customer_id = NULL` from legacy guest checkouts. The database rightfully refuses to add NOT NULL.

**Fix 1: Backfill NULLs with a default value, then add constraint:**

```python
def upgrade():
    # Step 1: Create a "guest" customer record for legacy orders
    op.execute("""
        INSERT INTO customers (id, name, email, is_guest)
        VALUES (0, 'Legacy Guest', 'guest@legacy.internal', true)
        ON CONFLICT (id) DO NOTHING
    """)

    # Step 2: Backfill NULL customer_ids with the guest customer
    op.execute("""
        UPDATE orders SET customer_id = 0
        WHERE customer_id IS NULL
    """)

    # Step 3: NOW it is safe to add NOT NULL
    op.alter_column('orders', 'customer_id',
                     existing_type=sa.Integer(),
                     nullable=False)

def downgrade():
    op.alter_column('orders', 'customer_id',
                     existing_type=sa.Integer(),
                     nullable=True)
    # Optionally restore NULLs for guest orders
    op.execute("""
        UPDATE orders SET customer_id = NULL
        WHERE customer_id = 0
    """)
```

**Fix 2: Backfill in batches (for large tables to avoid long locks):**

```python
def upgrade():
    # Backfill in batches to avoid locking the entire table
    op.execute("""
        INSERT INTO customers (id, name, email, is_guest)
        VALUES (0, 'Legacy Guest', 'guest@legacy.internal', true)
        ON CONFLICT (id) DO NOTHING
    """)

    # Batch update to avoid long-running transaction
    batch_size = 5000
    while True:
        result = op.get_bind().execute(sa.text("""
            UPDATE orders SET customer_id = 0
            WHERE id IN (
                SELECT id FROM orders
                WHERE customer_id IS NULL
                LIMIT :batch_size
            )
        """), {"batch_size": batch_size})

        if result.rowcount == 0:
            break
        print(f"Updated {result.rowcount} rows...")

    # Verify no NULLs remain
    count = op.get_bind().execute(sa.text(
        "SELECT COUNT(*) FROM orders WHERE customer_id IS NULL"
    )).scalar()
    assert count == 0, f"Still {count} NULL customer_ids!"

    # NOW add the constraint
    op.alter_column('orders', 'customer_id',
                     existing_type=sa.Integer(),
                     nullable=False)
```

**Fix 3: Add a server default instead (PostgreSQL):**

```python
def upgrade():
    # Add a server default for the column first
    op.alter_column('orders', 'customer_id',
                     existing_type=sa.Integer(),
                     server_default='0')

    # Backfill existing NULLs
    op.execute("UPDATE orders SET customer_id = 0 WHERE customer_id IS NULL")

    # Add NOT NULL constraint
    op.alter_column('orders', 'customer_id',
                     existing_type=sa.Integer(),
                     nullable=False)

    # Optionally remove server default if you want app-level control
    # op.alter_column('orders', 'customer_id',
    #                  existing_type=sa.Integer(),
    #                  server_default=None)
```

**Fix 4: Use a CHECK constraint instead of NOT NULL (PostgreSQL 12+):**

```python
def upgrade():
    # PostgreSQL 12+ can add NOT NULL using a NOT VALID check constraint
    # This avoids scanning the entire table during ALTER TABLE

    # Step 1: Add check constraint as NOT VALID (no table scan)
    op.execute("""
        ALTER TABLE orders
        ADD CONSTRAINT orders_customer_id_not_null
        CHECK (customer_id IS NOT NULL) NOT VALID
    """)

    # Step 2: Backfill NULLs in batches (can happen concurrently)
    op.execute("UPDATE orders SET customer_id = 0 WHERE customer_id IS NULL")

    # Step 3: Validate the constraint (scans table but does not lock writes)
    op.execute("""
        ALTER TABLE orders
        VALIDATE CONSTRAINT orders_customer_id_not_null
    """)

    # Step 4: Now safe to add actual NOT NULL (instant, no scan needed)
    op.alter_column('orders', 'customer_id',
                     existing_type=sa.Integer(),
                     nullable=False)

    # Step 5: Drop the now-redundant check constraint
    op.execute("ALTER TABLE orders DROP CONSTRAINT orders_customer_id_not_null")
```

**Prevention tips:**
- Always check for NULL values before adding NOT NULL constraints: `SELECT COUNT(*) WHERE col IS NULL`
- Write migrations as multi-step: backfill data first, then add constraints
- Test migrations against a copy of production data, not empty dev databases
- For large tables, use batch updates to avoid long locks
- PostgreSQL 12+: use NOT VALID constraints for zero-downtime NOT NULL additions
- Always include both upgrade and downgrade logic for data backfills'''),

    ("thinking/debugging", r'''Our Alembic migration to add an index on a large production table caused a 15-minute outage because it locked the entire table:

```python
# Migration that caused the outage
def upgrade():
    op.create_index('ix_events_created_at', 'events', ['created_at'])
```

The events table has 500 million rows. During the migration:
```
# Application logs during migration:
14:00:00 Starting migration: add index on events.created_at
14:00:01 WARNING: Query timeout after 5s: SELECT * FROM events WHERE ...
14:00:02 ERROR: Lock wait timeout: INSERT INTO events ...
14:00:03 ERROR: Lock wait timeout: SELECT * FROM events WHERE ...
... (15 minutes of errors)
14:15:23 Migration completed
14:15:24 Application recovering...
```

The CREATE INDEX statement took an ACCESS EXCLUSIVE lock on the table, blocking all reads and writes for 15 minutes.''', r'''<think>
Standard CREATE INDEX in PostgreSQL acquires a SHARE lock on the table, which blocks writes (INSERT, UPDATE, DELETE) but allows reads. With 500 million rows, building this index took 15 minutes of blocked writes -- a serious production outage.

My first thought is to just run the migration during off-peak hours... but wait, that only reduces the impact, it does not eliminate it. 15 minutes of write-blocking is unacceptable even at 3 AM if there are background jobs or async workers.

PostgreSQL supports CREATE INDEX CONCURRENTLY, which does not hold a write-blocking lock. I considered just swapping `op.create_index()` with a CONCURRENTLY variant, but that won't work directly because Alembic wraps migrations in a transaction by default, and CREATE INDEX CONCURRENTLY cannot run inside a transaction. Because PostgreSQL needs to do multiple table scans for concurrent index building (one to build the index, another to validate entries added during the build), it requires autocommit mode.

Hmm, actually this creates a second problem: if CREATE INDEX CONCURRENTLY fails partway through (disk space, killed process, etc.), it leaves an INVALID index behind that still occupies space and slows down writes. We need retry logic to handle that case.

Option A is using Alembic's `execution_options(isolation_level="AUTOCOMMIT")` to break out of the transaction. Option B is using raw SQL in a non-transactional migration context. Both achieve the same result but Option A is cleaner for Alembic 1.11+.
</think>

Standard `CREATE INDEX` locks the table, blocking writes (and in some configurations, reads) for the entire duration of the index build. On a 500-million-row table, that means a 15-minute outage.

**The fix: Use CREATE INDEX CONCURRENTLY:**

PostgreSQL supports `CONCURRENTLY` which builds the index without holding a lock that blocks writes. It takes longer but allows normal operations to continue.

**Critical caveat:** `CREATE INDEX CONCURRENTLY` cannot run inside a transaction, but Alembic migrations run inside a transaction by default. You must disable the transaction for this migration.

```python
# Fixed migration -- non-transactional for CONCURRENTLY support

# IMPORTANT: This flag tells Alembic to NOT wrap this migration in a transaction
# Add this at the module level, outside any function:
from alembic import op
import sqlalchemy as sa

# This is the key line:
# It must be a module-level variable, not inside a function
revision = 'def456'
down_revision = 'abc123'

def upgrade():
    # Use raw SQL with CONCURRENTLY
    # op.create_index does not support CONCURRENTLY directly
    op.execute("CREATE INDEX CONCURRENTLY ix_events_created_at ON events (created_at)")

def downgrade():
    op.execute("DROP INDEX CONCURRENTLY ix_events_created_at")
```

**But wait -- you also need to disable the transaction wrapper:**

```python
# Method 1: Use Alembic's "autocommit" context for this specific migration
from alembic import context

def upgrade():
    # Get the raw connection and set autocommit
    connection = op.get_bind()
    # For Alembic 1.11+:
    with connection.execution_options(isolation_level="AUTOCOMMIT"):
        connection.execute(sa.text(
            "CREATE INDEX CONCURRENTLY ix_events_created_at ON events (created_at)"
        ))

def downgrade():
    connection = op.get_bind()
    with connection.execution_options(isolation_level="AUTOCOMMIT"):
        connection.execute(sa.text(
            "DROP INDEX CONCURRENTLY ix_events_created_at"
        ))
```

```python
# Method 2: Use Alembic's run_migrations context with transaction_per_migration=False
# In env.py:
def run_migrations_online():
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            transaction_per_migration=True,  # Default
        )
        with context.begin_transaction():
            context.run_migrations()

# Then in the migration file, override for this specific migration:
# Set the migration to run outside a transaction
```

**Handling CONCURRENTLY failures:**

If `CREATE INDEX CONCURRENTLY` fails partway through, it leaves an INVALID index:

```sql
-- Check for invalid indexes
SELECT indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
  AND indexname = 'ix_events_created_at';

-- Check if the index is valid
SELECT pg_index.indisvalid
FROM pg_index
JOIN pg_class ON pg_class.oid = pg_index.indexrelid
WHERE pg_class.relname = 'ix_events_created_at';
-- false = INVALID index!

-- Fix: drop the invalid index and retry
DROP INDEX CONCURRENTLY ix_events_created_at;
-- Then re-run the migration
```

**Complete safe migration with retry logic:**

```python
def upgrade():
    conn = op.get_bind()

    # Drop any leftover invalid index from a previous failed attempt
    result = conn.execute(sa.text("""
        SELECT pg_index.indisvalid
        FROM pg_index
        JOIN pg_class ON pg_class.oid = pg_index.indexrelid
        WHERE pg_class.relname = 'ix_events_created_at'
    """))
    row = result.fetchone()
    if row and not row[0]:
        with conn.execution_options(isolation_level="AUTOCOMMIT"):
            conn.execute(sa.text(
                "DROP INDEX CONCURRENTLY IF EXISTS ix_events_created_at"
            ))

    # Create the index concurrently
    with conn.execution_options(isolation_level="AUTOCOMMIT"):
        conn.execute(sa.text(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "ix_events_created_at ON events (created_at)"
        ))
```

**Prevention tips:**
- ALWAYS use `CREATE INDEX CONCURRENTLY` on tables with more than a few thousand rows
- Never run schema-locking operations during peak traffic hours
- Test migrations on a staging database with production-scale data
- Set a `statement_timeout` for migrations to prevent runaway locks: `SET statement_timeout = '30min'`
- Monitor `pg_stat_activity` for blocked queries during migrations
- Use `pg_locks` to check for lock conflicts before running migrations'''),

    ("thinking/debugging", r'''We are trying to add a foreign key constraint in a migration, but it fails because orphaned rows exist in the child table:

```python
def upgrade():
    # Add foreign key from orders.customer_id -> customers.id
    op.create_foreign_key(
        'fk_orders_customer_id',
        'orders', 'customers',
        ['customer_id'], ['id']
    )
```

Error:
```
sqlalchemy.exc.IntegrityError: (psycopg2.errors.ForeignKeyViolation)
insert or update on table "orders" violates foreign key constraint "fk_orders_customer_id"
DETAIL: Key (customer_id)=(45892) is not present in table "customers".
```

We have 3 million orders and apparently some reference customers that were deleted without cleaning up the orders. We need the foreign key for data integrity going forward but cannot lose the orphaned order data.''', r'''<think>
Cannot add a foreign key because orphaned rows exist -- customer_ids in orders that do not exist in customers table. Need to handle the orphans before adding the constraint.

Options:
1. Delete orphaned orders (might lose important data)
2. Set orphaned customer_ids to NULL
3. Create placeholder customer records for orphaned IDs
4. Use NOT VALID to add the constraint without checking existing data

PostgreSQL supports adding FK constraints as NOT VALID, which skips the validation of existing rows but enforces the constraint on new inserts/updates.
</think>

The foreign key constraint fails because orphaned rows in `orders` reference customer IDs that no longer exist in `customers`. You need to handle existing orphans before (or while) adding the constraint.

**Step 1: Assess the scope of orphaned data:**

```sql
-- Count orphaned orders
SELECT COUNT(*) FROM orders o
LEFT JOIN customers c ON o.customer_id = c.id
WHERE o.customer_id IS NOT NULL AND c.id IS NULL;

-- See which customer_ids are orphaned
SELECT DISTINCT o.customer_id, COUNT(*) as order_count
FROM orders o
LEFT JOIN customers c ON o.customer_id = c.id
WHERE o.customer_id IS NOT NULL AND c.id IS NULL
GROUP BY o.customer_id
ORDER BY order_count DESC
LIMIT 20;
```

**Fix 1: Create placeholder customers for orphaned IDs (preserves all data):**

```python
def upgrade():
    # Step 1: Find all orphaned customer_ids
    conn = op.get_bind()

    # Create placeholder customer records for orphaned references
    conn.execute(sa.text("""
        INSERT INTO customers (id, name, email, is_deleted, deleted_note)
        SELECT DISTINCT o.customer_id,
               'Deleted Customer ' || o.customer_id,
               'deleted_' || o.customer_id || '@placeholder.internal',
               true,
               'Auto-created placeholder during FK migration'
        FROM orders o
        LEFT JOIN customers c ON o.customer_id = c.id
        WHERE o.customer_id IS NOT NULL
          AND c.id IS NULL
    """))

    orphan_count = conn.execute(sa.text("""
        SELECT COUNT(*) FROM customers WHERE is_deleted = true
        AND deleted_note = 'Auto-created placeholder during FK migration'
    """)).scalar()
    print(f"Created {orphan_count} placeholder customer records")

    # Step 2: Now safe to add the foreign key
    op.create_foreign_key(
        'fk_orders_customer_id',
        'orders', 'customers',
        ['customer_id'], ['id']
    )
```

**Fix 2: Set orphaned references to NULL (if customer_id is nullable):**

```python
def upgrade():
    conn = op.get_bind()

    # Nullify orphaned references in batches
    total = 0
    while True:
        result = conn.execute(sa.text("""
            UPDATE orders SET customer_id = NULL
            WHERE id IN (
                SELECT o.id FROM orders o
                LEFT JOIN customers c ON o.customer_id = c.id
                WHERE o.customer_id IS NOT NULL AND c.id IS NULL
                LIMIT 10000
            )
        """))
        total += result.rowcount
        if result.rowcount == 0:
            break
        print(f"Nullified {total} orphaned references so far...")

    print(f"Total orphaned references nullified: {total}")

    op.create_foreign_key(
        'fk_orders_customer_id',
        'orders', 'customers',
        ['customer_id'], ['id']
    )
```

**Fix 3: Use NOT VALID to skip existing row validation (PostgreSQL):**

```python
def upgrade():
    # Add FK constraint WITHOUT validating existing rows
    # New inserts/updates will be checked, but existing orphans are ignored
    op.execute("""
        ALTER TABLE orders
        ADD CONSTRAINT fk_orders_customer_id
        FOREIGN KEY (customer_id) REFERENCES customers(id)
        NOT VALID
    """)

    # Later (in a separate migration or background job), clean up orphans
    # then validate the constraint:
    # ALTER TABLE orders VALIDATE CONSTRAINT fk_orders_customer_id

def downgrade():
    op.drop_constraint('fk_orders_customer_id', 'orders', type_='foreignkey')
```

**Fix 4: Move orphaned orders to an archive table:**

```python
def upgrade():
    conn = op.get_bind()

    # Create archive table for orphaned orders
    op.execute("""
        CREATE TABLE IF NOT EXISTS orders_orphaned (
            LIKE orders INCLUDING ALL
        )
    """)

    # Move orphaned orders to archive
    op.execute("""
        WITH moved AS (
            DELETE FROM orders o
            USING (
                SELECT o2.id FROM orders o2
                LEFT JOIN customers c ON o2.customer_id = c.id
                WHERE o2.customer_id IS NOT NULL AND c.id IS NULL
            ) orphans
            WHERE o.id = orphans.id
            RETURNING o.*
        )
        INSERT INTO orders_orphaned SELECT * FROM moved
    """)

    # Now add the constraint
    op.create_foreign_key(
        'fk_orders_customer_id',
        'orders', 'customers',
        ['customer_id'], ['id']
    )
```

**Prevention tips:**
- Always check for orphaned records before adding foreign key constraints
- Use `NOT VALID` for large tables to avoid long-running validation locks
- Add ON DELETE SET NULL or ON DELETE CASCADE to foreign keys to prevent future orphans
- Run regular integrity checks: `SELECT COUNT(*) FROM child LEFT JOIN parent WHERE parent.id IS NULL`
- Add the foreign key constraint when the table is first created, not retroactively
- Use database-level cascading deletes instead of relying on application logic'''),

    ("thinking/debugging", r'''Two developers ran `alembic revision --autogenerate` on different branches, and now we have a migration conflict when merging:

```
$ alembic upgrade head
alembic.util.exc.CommandError: Multiple head revisions are present for given argument 'head';
please specify a specific target revision, '--resolve-dependencies' flag, or use the 'heads' command

$ alembic heads
abc123 (head)  -- Branch A: add users.phone_number
def456 (head)  -- Branch B: add orders.shipping_method

$ alembic history --verbose
abc123 -> None (head), add_phone_number, Parent: base123
def456 -> None (head), add_shipping_method, Parent: base123
base123 -> abc123, def456, initial_schema
```

Both migrations have the same parent (`base123`) but are independent changes on different tables. How do we resolve this without losing either migration?''', r'''<think>
This is a standard Alembic "multiple heads" situation. Two developers branched from the same migration and created independent migrations. Alembic needs a linear history (or explicitly merged branches) to know the order of operations.

The solution is to create a merge migration that joins the two heads into a single head. Alembic has a built-in command for this: `alembic merge`.
</think>

Multiple heads occur when two developers create migrations from the same parent on different branches. Alembic requires a single head (or explicit merge) to determine migration order. The fix is to create a **merge migration**.

**Fix: Create a merge migration that joins both heads:**

```bash
# Alembic has a built-in merge command
$ alembic merge -m "merge phone_number and shipping_method" abc123 def456

# This creates a new migration file:
# migrations/versions/ghi789_merge_phone_number_and_shipping_method.py
```

**The generated merge migration looks like:**

```python
"""merge phone_number and shipping_method

Revision ID: ghi789
Revises: abc123, def456
Create Date: 2026-03-06 14:30:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'ghi789'
down_revision = ('abc123', 'def456')  # Tuple -- both parents!
branch_labels = None
depends_on = None

def upgrade():
    pass  # No schema changes -- just merges the history

def downgrade():
    pass
```

**Now verify the merge:**

```bash
$ alembic heads
ghi789 (head)  -- Single head!

$ alembic history
ghi789 (head) <- abc123, def456  (merge)
abc123 <- base123  (add_phone_number)
def456 <- base123  (add_shipping_method)
base123  (initial_schema)

# Run the migration
$ alembic upgrade head
INFO  [alembic.runtime.migration] Running upgrade base123 -> abc123, add_phone_number
INFO  [alembic.runtime.migration] Running upgrade base123 -> def456, add_shipping_method
INFO  [alembic.runtime.migration] Running upgrade abc123, def456 -> ghi789, merge
```

**Handling conflicts when migrations touch the same table:**

If both migrations modify the same table, the merge migration might need manual intervention:

```python
# Branch A adds phone_number with NOT NULL and a default
# Branch B adds a unique constraint on email
# Both touch the users table -- might have ordering issues

def upgrade():
    # If needed, add reconciliation logic here
    # For example, if both branches added columns with conflicting positions
    pass
```

**Preventing merge conflicts in the future:**

```python
# Add a pre-commit hook that checks for multiple heads
# .pre-commit-config.yaml or CI script:

#!/bin/bash
# check_alembic_heads.sh
heads=$(alembic heads 2>/dev/null | wc -l)
if [ "$heads" -gt 1 ]; then
    echo "ERROR: Multiple Alembic heads detected!"
    echo "Run: alembic merge heads -m 'merge description'"
    alembic heads
    exit 1
fi
```

```python
# Add to your CI pipeline (GitHub Actions example):
# .github/workflows/check-migrations.yml
# - name: Check for multiple Alembic heads
#   run: |
#     heads=$(alembic heads | wc -l)
#     if [ "$heads" -gt 1 ]; then
#       echo "Multiple migration heads detected. Create a merge migration."
#       exit 1
#     fi
```

**Team workflow to minimize conflicts:**

```
1. Before creating a migration, pull latest main and run:
   $ alembic heads
   # Ensure single head

2. Create your migration from the current single head:
   $ alembic revision --autogenerate -m "description"

3. Before merging your PR, rebase on main:
   $ git rebase main
   # If a new migration landed on main, you now have two heads

4. If multiple heads exist after rebase:
   $ alembic merge heads -m "merge my_change and other_change"
   # Commit the merge migration with your PR
```

**Prevention tips:**
- Add a CI check that fails if multiple Alembic heads exist
- Always run `alembic heads` before creating a new migration
- Keep migrations small and merge PRs with migrations quickly to reduce conflict window
- Use `alembic merge heads` immediately when conflicts are detected
- Consider using sequential numeric prefixes in migration filenames for easier ordering
- Communicate with your team when creating migrations on shared tables'''),
]
