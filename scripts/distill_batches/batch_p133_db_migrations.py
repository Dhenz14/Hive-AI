"""Database migrations — Alembic, schema evolution, and zero-downtime migrations."""

PAIRS = [
    (
        "backend/alembic-migrations",
        "Show Alembic migration patterns: setup, auto-generation, data migrations, and branching.",
        '''Alembic database migration patterns:

```python
# --- alembic.ini (key settings) ---
# [alembic]
# script_location = alembic
# sqlalchemy.url = postgresql://user:pass@localhost/mydb
# file_template = %%(year)d_%%(month).2d_%%(day).2d_%%(rev)s_%%(slug)s


# --- alembic/env.py ---

from alembic import context
from sqlalchemy import engine_from_config, pool
from myapp.models import Base  # Import all models

target_metadata = Base.metadata

def run_migrations_online():
    connectable = engine_from_config(
        context.config.get_section(context.config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,        # Detect column type changes
            compare_server_default=True,
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()


# --- Schema migration (auto-generated) ---
# alembic revision --autogenerate -m "add users table"

"""add users table

Revision ID: a1b2c3d4e5f6
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_users_email", "users", ["email"])

def downgrade():
    op.drop_index("ix_users_email", "users")
    op.drop_table("users")


# --- Add column with default (safe for large tables) ---

"""add status to orders

Revision ID: b2c3d4e5f6g7
"""

def upgrade():
    # Step 1: Add column as nullable (no table lock)
    op.add_column("orders",
        sa.Column("status", sa.String(20), nullable=True)
    )

    # Step 2: Backfill in batches (data migration)
    conn = op.get_bind()
    while True:
        result = conn.execute(sa.text("""
            UPDATE orders SET status = 'active'
            WHERE id IN (
                SELECT id FROM orders
                WHERE status IS NULL
                LIMIT 1000
            )
            RETURNING id
        """))
        if result.rowcount == 0:
            break

    # Step 3: Set NOT NULL after backfill
    op.alter_column("orders", "status",
        existing_type=sa.String(20),
        nullable=False,
        server_default="active",
    )

def downgrade():
    op.drop_column("orders", "status")


# --- Rename column (zero-downtime) ---

"""rename username to display_name

Revision ID: c3d4e5f6g7h8
"""

def upgrade():
    # Phase 1: Add new column
    op.add_column("users",
        sa.Column("display_name", sa.String(100))
    )

    # Phase 2: Copy data
    op.execute("UPDATE users SET display_name = username")

    # Phase 3: Make non-null
    op.alter_column("users", "display_name", nullable=False)

    # Phase 4: Drop old column (after app code updated)
    # op.drop_column("users", "username")

def downgrade():
    op.drop_column("users", "display_name")


# --- Enum type migration ---

"""add premium to plan_type enum

Revision ID: d4e5f6g7h8i9
"""

def upgrade():
    # PostgreSQL: alter enum type
    op.execute("ALTER TYPE plan_type ADD VALUE IF NOT EXISTS 'premium'")

def downgrade():
    # PostgreSQL enums can't easily remove values
    # Requires recreating the type
    pass


# --- Data-only migration ---

"""backfill user slugs

Revision ID: e5f6g7h8i9j0
"""

def upgrade():
    conn = op.get_bind()
    users = conn.execute(sa.text(
        "SELECT id, name FROM users WHERE slug IS NULL"
    ))
    for user in users:
        slug = user.name.lower().replace(" ", "-")
        conn.execute(
            sa.text("UPDATE users SET slug = :slug WHERE id = :id"),
            {"slug": slug, "id": user.id},
        )

def downgrade():
    op.execute("UPDATE users SET slug = NULL")
```

```bash
# --- Common commands ---

# Create migration
alembic revision --autogenerate -m "add users table"

# Run migrations
alembic upgrade head          # Apply all pending
alembic upgrade +1            # Apply next one
alembic downgrade -1          # Rollback one

# Check status
alembic current               # Current revision
alembic history --verbose     # Full history
alembic check                 # Verify head matches models

# Stamp (mark as applied without running)
alembic stamp head            # Mark all as applied
```

Alembic patterns:
1. **`--autogenerate`** — detect model changes and generate migration skeleton
2. **Batch backfill** — update rows in chunks to avoid long table locks
3. **Three-phase column add** — add nullable, backfill, then set NOT NULL
4. **`compare_type=True`** — detect column type changes in autogenerate
5. **Zero-downtime rename** — add new column, copy data, drop old (in separate deploys)'''
    ),
    (
        "backend/schema-evolution",
        "Show database schema evolution patterns: backward-compatible changes, expand-contract, and migration testing.",
        '''Database schema evolution patterns:

```python
"""
Schema Evolution Strategy: Expand-Contract Pattern

Phase 1 (EXPAND): Add new structure alongside old
Phase 2 (MIGRATE): Update code to use new structure
Phase 3 (CONTRACT): Remove old structure

This ensures zero-downtime deployments with rolling updates.
"""


# --- Phase 1: Expand (backward-compatible) ---

# SAFE changes (no coordination needed):
#   - Add nullable column
#   - Add table
#   - Add index (CONCURRENTLY)
#   - Add column with default (Postgres 11+: instant)
#   - Widen column (varchar(50) -> varchar(100))

# UNSAFE changes (need expand-contract):
#   - Drop column/table
#   - Rename column/table
#   - Change column type
#   - Add NOT NULL constraint
#   - Shrink column


# --- Example: Split name into first_name + last_name ---

# Migration 1: EXPAND (add new columns)
"""
def upgrade():
    op.add_column("users", sa.Column("first_name", sa.String(50)))
    op.add_column("users", sa.Column("last_name", sa.String(50)))

    # Backfill from existing data
    op.execute(\"\"\"
        UPDATE users SET
            first_name = split_part(name, ' ', 1),
            last_name = CASE
                WHEN position(' ' in name) > 0
                THEN substring(name from position(' ' in name) + 1)
                ELSE ''
            END
    \"\"\")
"""

# Application code v2: Write to BOTH old and new columns
class UserModel:
    def save(self):
        self.name = f"{self.first_name} {self.last_name}"  # Keep old column updated
        self.first_name = self.first_name
        self.last_name = self.last_name
        db.session.commit()


# Migration 2: CONTRACT (after all app servers on v2)
"""
def upgrade():
    op.alter_column("users", "first_name", nullable=False)
    op.alter_column("users", "last_name", nullable=False, server_default="")
    op.drop_column("users", "name")  # Safe now
"""


# --- Concurrent index creation (PostgreSQL) ---

from alembic import op

def upgrade():
    # Regular CREATE INDEX locks the table — bad for production
    # Use CONCURRENTLY (requires autocommit)
    op.execute(
        "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
        "ix_orders_customer_date ON orders (customer_id, created_at DESC)"
    )

# In env.py, for CONCURRENTLY to work:
# context.configure(
#     connection=connection,
#     target_metadata=target_metadata,
#     transaction_per_migration=True,  # Separate transaction per migration
# )


# --- Migration testing ---

import pytest
from alembic.config import Config
from alembic import command
from sqlalchemy import create_engine, inspect


@pytest.fixture
def alembic_config():
    config = Config("alembic.ini")
    config.set_main_option(
        "sqlalchemy.url", "postgresql://test:test@localhost/test_migrations"
    )
    return config


def test_upgrade_downgrade_cycle(alembic_config):
    """Test full upgrade then downgrade."""
    # Upgrade to head
    command.upgrade(alembic_config, "head")

    # Verify expected tables exist
    engine = create_engine(alembic_config.get_main_option("sqlalchemy.url"))
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "users" in tables
    assert "orders" in tables

    # Downgrade to base
    command.downgrade(alembic_config, "base")

    # Verify tables removed
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert "users" not in tables


def test_migration_is_reversible(alembic_config):
    """Test each migration can be applied and reverted."""
    from alembic.script import ScriptDirectory
    script = ScriptDirectory.from_config(alembic_config)

    for revision in script.walk_revisions():
        if revision.down_revision:
            command.upgrade(alembic_config, revision.revision)
            command.downgrade(alembic_config, revision.down_revision)


def test_no_pending_migrations(alembic_config):
    """CI check: models match latest migration."""
    command.upgrade(alembic_config, "head")
    # This raises if models differ from migrations
    command.check(alembic_config)
```

Schema evolution patterns:
1. **Expand-contract** — add new alongside old, migrate code, then remove old
2. **Dual-write** — write to both old and new columns during transition
3. **`CREATE INDEX CONCURRENTLY`** — non-blocking index creation in PostgreSQL
4. **Migration testing** — automated upgrade/downgrade cycle in CI
5. **`alembic check`** — verify models match migrations to catch missing migrations'''
    ),
]
"""
