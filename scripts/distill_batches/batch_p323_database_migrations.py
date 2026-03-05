"""Database migrations — Alembic patterns, zero-downtime migrations, data migrations, rollback strategies."""

PAIRS = [
    (
        "database-migrations/alembic-production-setup",
        "Show a production Alembic setup with environment-based configuration, async engine support, multi-database migrations, and custom migration templates.",
        '''Production Alembic setup with async support and multi-database configuration:

```python
# --- alembic/env.py --- Production migration environment ---

from __future__ import annotations

import asyncio
import logging
from logging.config import fileConfig
from typing import Any

from alembic import context
from alembic.config import Config
from sqlalchemy import pool, text, engine_from_config
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config, AsyncConnection

from app.config import get_settings
from app.models.base import Base  # Your declarative base with all models imported

# Alembic Config object
config: Config = context.config
settings = get_settings()

# Logging setup
if config.config_file_name is not None:
    fileConfig(config.config_file_name)
logger = logging.getLogger("alembic.env")

# Target metadata for autogenerate
target_metadata = Base.metadata

# Override sqlalchemy.url from environment
config.set_main_option("sqlalchemy.url", settings.database_url)


def include_name(name: str | None, type_: str, parent_names: dict[str, Any]) -> bool:
    """Filter which tables/schemas to include in autogenerate."""
    if type_ == "schema":
        return name in (None, "public", settings.db_schema)
    return True


def process_revision_directives(context, revision, directives):
    """Prevent empty migration files from being generated."""
    if config.cmd_opts and getattr(config.cmd_opts, "autogenerate", False):
        script = directives[0]
        if script.upgrade_ops.is_empty():
            directives[:] = []
            logger.info("No changes detected — skipping migration generation.")


# ---- Synchronous migration (offline mode) ----

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode — generates SQL without connecting."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_name=include_name,
        compare_type=True,
        compare_server_default=True,
        process_revision_directives=process_revision_directives,
        render_as_batch=True,  # Required for SQLite compatibility
    )

    with context.begin_transaction():
        context.run_migrations()


# ---- Async migration (online mode) ----

def do_run_migrations(connection: Connection) -> None:
    """Configure and run migrations within a connection."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        include_name=include_name,
        compare_type=True,
        compare_server_default=True,
        process_revision_directives=process_revision_directives,
        render_as_batch=True,
        # Migration locking for concurrent deploys
        transaction_per_migration=True,
    )

    with context.begin_transaction():
        # Acquire advisory lock to prevent concurrent migrations
        connection.execute(text("SELECT pg_advisory_lock(12345)"))
        try:
            context.run_migrations()
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(12345)"))


async def run_async_migrations() -> None:
    """Run migrations using async engine."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,  # No pooling for migrations
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode with async support."""
    connectable_url = config.get_main_option("sqlalchemy.url", "")
    if connectable_url.startswith("postgresql+asyncpg"):
        asyncio.run(run_async_migrations())
    else:
        connectable = engine_from_config(
            config.get_section(config.config_ini_section, {}),
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as connection:
            do_run_migrations(connection)
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

```ini
# --- alembic.ini --- Production configuration ---

[alembic]
script_location = alembic
file_template = %%(year)d_%%(month).2d_%%(day).2d_%%(rev)s_%%(slug)s
prepend_sys_path = .
timezone = utc
truncate_slug_length = 40

[post_write_hooks]
hooks = ruff
ruff.type = exec
ruff.executable = ruff
ruff.options = format REVISION_SCRIPT_FILENAME

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

Key Alembic production patterns:

| Pattern | Implementation | Purpose |
|---------|---------------|---------|
| Advisory lock | `pg_advisory_lock(12345)` | Prevent concurrent migrations |
| Async support | `async_engine_from_config` | Works with asyncpg driver |
| Empty migration prevention | `process_revision_directives` | Skip if no changes detected |
| Type comparison | `compare_type=True` | Detect column type changes |
| Batch mode | `render_as_batch=True` | SQLite ALTER TABLE compatibility |
| UTC timestamps | `timezone = utc` | Consistent revision timestamps |

- **Advisory lock** prevents two deploying pods from running migrations simultaneously
- **NullPool** avoids connection pool overhead during one-off migration runs
- **Async engine** support lets you use the same connection string for both app and migrations
'''
    ),
    (
        "database-migrations/zero-downtime-migration",
        "Show how to perform a zero-downtime column rename in PostgreSQL using Alembic with a multi-step migration strategy.",
        '''Zero-downtime column rename using a 4-phase migration strategy:

```python
# --- Phase 1: Add new column (backward compatible) ---
# alembic/versions/2026_03_01_a1b2c3_add_full_name_column.py

"""Add full_name column alongside existing name column."""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "previous_rev_id"


def upgrade() -> None:
    # Step 1: Add new column (nullable, no default yet)
    op.add_column("users", sa.Column("full_name", sa.String(255), nullable=True))

    # Step 2: Backfill data in batches to avoid locking
    # Using raw SQL for performance on large tables
    conn = op.get_bind()
    total = conn.execute(sa.text("SELECT COUNT(*) FROM users WHERE full_name IS NULL")).scalar()

    batch_size = 5000
    updated = 0
    while updated < total:
        result = conn.execute(sa.text("""
            UPDATE users
            SET full_name = name
            WHERE id IN (
                SELECT id FROM users
                WHERE full_name IS NULL
                ORDER BY id
                LIMIT :batch_size
            )
        """), {"batch_size": batch_size})
        updated += result.rowcount
        conn.commit()  # Commit each batch to release locks

    # Step 3: Add trigger to keep columns in sync during transition
    conn.execute(sa.text("""
        CREATE OR REPLACE FUNCTION sync_user_name()
        RETURNS TRIGGER AS $$
        BEGIN
            IF TG_OP = 'INSERT' OR NEW.name IS DISTINCT FROM OLD.name THEN
                NEW.full_name := COALESCE(NEW.full_name, NEW.name);
            END IF;
            IF TG_OP = 'INSERT' OR NEW.full_name IS DISTINCT FROM OLD.full_name THEN
                NEW.name := COALESCE(NEW.name, NEW.full_name);
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;

        CREATE TRIGGER trg_sync_user_name
        BEFORE INSERT OR UPDATE ON users
        FOR EACH ROW EXECUTE FUNCTION sync_user_name();
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TRIGGER IF EXISTS trg_sync_user_name ON users"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS sync_user_name()"))
    op.drop_column("users", "full_name")


# --- Phase 2: Application code reads from both columns ---
# (Deploy application that reads full_name with fallback to name)
# This is a code change, not a migration:
#
#   @property
#   def display_name(self) -> str:
#       return self.full_name or self.name


# --- Phase 3: Make new column NOT NULL, drop old column ---
# alembic/versions/2026_03_04_g7h8i9_finalize_full_name.py

"""Make full_name NOT NULL and drop old name column."""

revision = "g7h8i9j0k1l2"
down_revision = "a1b2c3d4e5f6"


def upgrade() -> None:
    conn = op.get_bind()

    # Verify no NULLs remain
    null_count = conn.execute(
        sa.text("SELECT COUNT(*) FROM users WHERE full_name IS NULL")
    ).scalar()
    if null_count > 0:
        raise RuntimeError(
            f"Cannot proceed: {null_count} rows still have NULL full_name. "
            "Run backfill first."
        )

    # Add NOT NULL constraint using ALTER TABLE ... SET NOT NULL
    # In PostgreSQL 12+, this is instant if a CHECK constraint exists
    conn.execute(sa.text("""
        ALTER TABLE users
        ADD CONSTRAINT users_full_name_not_null
        CHECK (full_name IS NOT NULL) NOT VALID
    """))
    conn.execute(sa.text("""
        ALTER TABLE users VALIDATE CONSTRAINT users_full_name_not_null
    """))
    conn.execute(sa.text("""
        ALTER TABLE users ALTER COLUMN full_name SET NOT NULL
    """))
    conn.execute(sa.text("""
        ALTER TABLE users DROP CONSTRAINT users_full_name_not_null
    """))

    # Create index concurrently (non-blocking)
    op.execute("CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_full_name ON users (full_name)")


def downgrade() -> None:
    op.drop_index("ix_users_full_name", table_name="users")
    op.alter_column("users", "full_name", nullable=True)


# --- Phase 4: Remove old column and trigger (after all code deployed) ---
# alembic/versions/2026_03_07_m3n4o5_drop_old_name_column.py

"""Drop old name column and sync trigger."""

revision = "m3n4o5p6q7r8"
down_revision = "g7h8i9j0k1l2"


def upgrade() -> None:
    conn = op.get_bind()
    # Remove trigger first
    conn.execute(sa.text("DROP TRIGGER IF EXISTS trg_sync_user_name ON users"))
    conn.execute(sa.text("DROP FUNCTION IF EXISTS sync_user_name()"))
    # Drop old column
    op.drop_column("users", "name")


def downgrade() -> None:
    # Re-add the old column and backfill from full_name
    op.add_column("users", sa.Column("name", sa.String(255), nullable=True))
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE users SET name = full_name"))
    op.alter_column("users", "name", nullable=False)
```

Zero-downtime migration phases:

| Phase | Migration | Code Deploy | Risk |
|-------|-----------|-------------|------|
| 1. Expand | Add new column + trigger | None needed | Zero — additive only |
| 2. Migrate code | None | Read both columns | Zero — backward compatible |
| 3. Contract prep | Add NOT NULL, indexes | Write to new column | Low — validated incrementally |
| 4. Cleanup | Drop old column + trigger | Remove fallback code | Low — old column unused |

Critical rules for zero-downtime migrations:

- **Never rename a column directly** — old code still references the old name
- **Never drop a column still in use** — first remove all code references
- **Batch backfills** with commits to avoid long-held locks
- **Triggers** keep old and new columns in sync during the transition window
- **CREATE INDEX CONCURRENTLY** avoids table-level locks during index creation
- **NOT VALID + VALIDATE** constraint pattern avoids full table scan lock
'''
    ),
    (
        "database-migrations/data-migration-patterns",
        "Show patterns for large-scale data migrations in Alembic including batched updates, progress tracking, validation, and reversibility.",
        '''Large-scale data migration patterns with batching, validation, and safe rollback:

```python
# --- alembic/versions/2026_03_02_x1y2z3_migrate_user_addresses.py ---

"""Migrate user addresses from JSON column to normalized address table."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB
import json
import logging
import time

revision = "x1y2z3a4b5c6"
down_revision = "prev_rev_id"

logger = logging.getLogger(__name__)


def upgrade() -> None:
    conn = op.get_bind()

    # Step 1: Create the new normalized table
    op.create_table(
        "addresses",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type", sa.String(20), nullable=False, server_default="home"),
        sa.Column("street", sa.String(255), nullable=False),
        sa.Column("street2", sa.String(255), nullable=True),
        sa.Column("city", sa.String(100), nullable=False),
        sa.Column("state", sa.String(50), nullable=False),
        sa.Column("zip_code", sa.String(20), nullable=False),
        sa.Column("country", sa.String(2), nullable=False, server_default="US"),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("migrated_from_json", sa.Boolean, server_default="true"),
    )
    op.create_index("ix_addresses_user_id", "addresses", ["user_id"])
    op.create_index("ix_addresses_zip_code", "addresses", ["zip_code"])

    # Step 2: Batched data migration with progress tracking
    _migrate_addresses_batched(conn, batch_size=2000)

    # Step 3: Validate migration
    _validate_migration(conn)


def _migrate_addresses_batched(conn, batch_size: int = 2000) -> None:
    """Migrate address data in batches with progress tracking."""

    # Count total users with address data
    total = conn.execute(sa.text("""
        SELECT COUNT(*) FROM users
        WHERE address_json IS NOT NULL
        AND address_json != 'null'::jsonb
        AND address_json != '{}'::jsonb
    """)).scalar() or 0

    logger.info("Migrating addresses for %d users", total)
    if total == 0:
        return

    migrated = 0
    errors = 0
    last_id = 0
    start_time = time.time()

    while True:
        # Fetch batch using keyset pagination (more efficient than OFFSET)
        rows = conn.execute(sa.text("""
            SELECT id, address_json
            FROM users
            WHERE id > :last_id
            AND address_json IS NOT NULL
            AND address_json != 'null'::jsonb
            AND address_json != '{}'::jsonb
            ORDER BY id
            LIMIT :batch_size
        """), {"last_id": last_id, "batch_size": batch_size}).fetchall()

        if not rows:
            break

        # Build bulk insert values
        insert_values = []
        for user_id, address_json in rows:
            last_id = user_id
            try:
                addr = address_json if isinstance(address_json, dict) else json.loads(address_json)

                # Handle both single address and array of addresses
                addresses = addr if isinstance(addr, list) else [addr]
                for i, a in enumerate(addresses):
                    insert_values.append({
                        "user_id": user_id,
                        "type": a.get("type", "home"),
                        "street": a.get("street", a.get("address1", "")),
                        "street2": a.get("street2", a.get("address2")),
                        "city": a.get("city", ""),
                        "state": a.get("state", a.get("province", "")),
                        "zip_code": a.get("zip", a.get("zip_code", a.get("postal_code", ""))),
                        "country": a.get("country", "US")[:2].upper(),
                        "is_primary": i == 0,
                    })
            except (json.JSONDecodeError, TypeError, KeyError) as e:
                errors += 1
                logger.warning("Failed to parse address for user %d: %s", user_id, e)
                continue

        # Bulk insert batch
        if insert_values:
            conn.execute(
                sa.text("""
                    INSERT INTO addresses (user_id, type, street, street2, city, state, zip_code, country, is_primary)
                    VALUES (:user_id, :type, :street, :street2, :city, :state, :zip_code, :country, :is_primary)
                """),
                insert_values,
            )
            conn.commit()

        migrated += len(rows)
        elapsed = time.time() - start_time
        rate = migrated / elapsed if elapsed > 0 else 0
        eta = (total - migrated) / rate if rate > 0 else 0
        logger.info(
            "Progress: %d/%d (%.1f%%) — %.0f rows/sec — ETA: %.0fs — Errors: %d",
            migrated, total, migrated / total * 100, rate, eta, errors,
        )

    logger.info(
        "Migration complete: %d users migrated, %d errors, %.1fs elapsed",
        migrated, errors, time.time() - start_time,
    )


def _validate_migration(conn) -> None:
    """Validate that migrated data matches source data."""

    # Check row counts
    source_count = conn.execute(sa.text("""
        SELECT COUNT(*) FROM users
        WHERE address_json IS NOT NULL
        AND address_json != 'null'::jsonb
        AND address_json != '{}'::jsonb
    """)).scalar()

    migrated_users = conn.execute(sa.text("""
        SELECT COUNT(DISTINCT user_id) FROM addresses WHERE migrated_from_json = true
    """)).scalar()

    logger.info("Validation: %d source users, %d migrated users", source_count, migrated_users)

    if migrated_users < source_count * 0.95:  # Allow 5% error tolerance
        raise RuntimeError(
            f"Migration validation failed: only {migrated_users}/{source_count} users migrated. "
            "Check error logs and re-run."
        )

    # Spot-check random records
    sample = conn.execute(sa.text("""
        SELECT u.id, u.address_json, a.street, a.city, a.state
        FROM users u
        JOIN addresses a ON a.user_id = u.id AND a.is_primary = true
        WHERE u.address_json IS NOT NULL
        ORDER BY RANDOM()
        LIMIT 100
    """)).fetchall()

    mismatches = 0
    for user_id, addr_json, street, city, state in sample:
        addr = addr_json if isinstance(addr_json, dict) else json.loads(addr_json)
        if isinstance(addr, list):
            addr = addr[0]
        src_street = addr.get("street", addr.get("address1", ""))
        if src_street != street:
            mismatches += 1
            logger.warning("Mismatch user %d: '%s' != '%s'", user_id, src_street, street)

    if mismatches > 5:
        raise RuntimeError(f"Too many validation mismatches: {mismatches}/100")

    logger.info("Validation passed: %d/100 spot checks OK", 100 - mismatches)


def downgrade() -> None:
    # Safe downgrade: old JSON column still exists, just drop the new table
    op.drop_index("ix_addresses_zip_code", table_name="addresses")
    op.drop_index("ix_addresses_user_id", table_name="addresses")
    op.drop_table("addresses")
```

Data migration best practices:

| Practice | Implementation | Why |
|----------|---------------|-----|
| Keyset pagination | `WHERE id > :last_id ORDER BY id LIMIT N` | O(1) vs O(n) for OFFSET |
| Batch commits | `conn.commit()` per batch | Release locks between batches |
| Progress logging | Rate, ETA, error count | Visibility during long migrations |
| Validation | Count check + spot check | Catch data corruption early |
| Error tolerance | Skip bad rows, log, continue | Don't fail entire migration for edge cases |
| Reversibility | Keep source data until verified | Safe rollback without data loss |
| Bulk inserts | Multi-row INSERT | 10-50x faster than individual INSERTs |
'''
    ),
    (
        "database-migrations/rollback-strategies",
        "Implement robust rollback strategies for database migrations including forward-fix patterns, migration checkpoints, and automated rollback testing.",
        '''Migration rollback strategies with forward-fix, checkpoints, and automated testing:

```python
# --- migration_manager.py --- Production migration manager with rollback support ---

from __future__ import annotations

import logging
import time
import subprocess
import json
from dataclasses import dataclass, field
from typing import Any
from pathlib import Path
from datetime import datetime, timezone

import sqlalchemy as sa
from sqlalchemy import create_engine, text

logger = logging.getLogger(__name__)


@dataclass
class MigrationCheckpoint:
    """Snapshot of database state before a migration."""
    revision: str
    timestamp: str
    table_checksums: dict[str, int]
    row_counts: dict[str, int]
    schema_hash: str


@dataclass
class RollbackPlan:
    """Plan for rolling back a failed migration."""
    target_revision: str
    steps: list[str]
    estimated_duration_seconds: float
    data_loss_risk: str  # "none", "low", "medium", "high"
    requires_downtime: bool


class MigrationManager:
    """
    Production migration manager with:
    - Pre-migration checkpoints
    - Automatic rollback on failure
    - Forward-fix pattern support
    - Migration dry-run / preview
    - Health checks before and after
    """

    def __init__(self, database_url: str, alembic_dir: str = "alembic") -> None:
        self._engine = create_engine(database_url, pool_pre_ping=True)
        self._alembic_dir = alembic_dir

    def create_checkpoint(self) -> MigrationCheckpoint:
        """Create a checkpoint of current database state."""
        with self._engine.connect() as conn:
            # Get current revision
            result = conn.execute(text(
                "SELECT version_num FROM alembic_version"
            ))
            current_rev = result.scalar() or "base"

            # Get row counts for all tables
            tables = conn.execute(text("""
                SELECT tablename FROM pg_tables
                WHERE schemaname = 'public'
                AND tablename != 'alembic_version'
                ORDER BY tablename
            """)).fetchall()

            row_counts = {}
            table_checksums = {}
            for (table_name,) in tables:
                count = conn.execute(
                    text(f"SELECT COUNT(*) FROM {table_name}")  # noqa: S608
                ).scalar()
                row_counts[table_name] = count

                # Lightweight checksum via pg_stat
                stats = conn.execute(text(f"""
                    SELECT n_live_tup, n_dead_tup, last_autovacuum
                    FROM pg_stat_user_tables
                    WHERE relname = :table
                """), {"table": table_name}).fetchone()
                table_checksums[table_name] = hash(stats) if stats else 0

            # Schema hash
            schema = conn.execute(text("""
                SELECT md5(string_agg(
                    table_name || column_name || data_type || COALESCE(column_default, ''),
                    '|' ORDER BY table_name, ordinal_position
                ))
                FROM information_schema.columns
                WHERE table_schema = 'public'
            """)).scalar()

            checkpoint = MigrationCheckpoint(
                revision=current_rev,
                timestamp=datetime.now(timezone.utc).isoformat(),
                table_checksums=table_checksums,
                row_counts=row_counts,
                schema_hash=schema or "",
            )

            logger.info("Checkpoint created at revision %s", current_rev)
            return checkpoint

    def preview_migration(self, target: str = "head") -> dict[str, Any]:
        """Preview what a migration will do without executing it."""
        result = subprocess.run(
            ["alembic", "upgrade", target, "--sql"],
            capture_output=True,
            text=True,
            cwd=self._alembic_dir,
        )
        sql_statements = result.stdout.strip().split(";\n")
        ddl_ops = [s for s in sql_statements if any(
            kw in s.upper() for kw in ["CREATE", "DROP", "ALTER", "RENAME"]
        )]
        dml_ops = [s for s in sql_statements if any(
            kw in s.upper() for kw in ["INSERT", "UPDATE", "DELETE"]
        )]

        return {
            "target_revision": target,
            "total_statements": len(sql_statements),
            "ddl_operations": len(ddl_ops),
            "dml_operations": len(dml_ops),
            "has_drop_statements": any("DROP" in s.upper() for s in sql_statements),
            "has_data_changes": len(dml_ops) > 0,
            "sql_preview": result.stdout[:5000],
        }

    def pre_migration_health_check(self) -> bool:
        """Verify database health before migrating."""
        with self._engine.connect() as conn:
            checks = {}

            # Check replication lag
            try:
                lag = conn.execute(text("""
                    SELECT COALESCE(
                        EXTRACT(EPOCH FROM (now() - pg_last_xact_replay_timestamp())),
                        0
                    )
                """)).scalar()
                checks["replication_lag_seconds"] = lag
                if lag and lag > 30:
                    logger.error("Replication lag too high: %.1fs", lag)
                    return False
            except Exception:
                checks["replication_lag_seconds"] = "N/A (primary)"

            # Check active long-running queries
            long_queries = conn.execute(text("""
                SELECT count(*) FROM pg_stat_activity
                WHERE state = 'active'
                AND query_start < NOW() - INTERVAL '5 minutes'
                AND pid != pg_backend_pid()
            """)).scalar()
            checks["long_running_queries"] = long_queries
            if long_queries > 0:
                logger.warning("%d long-running queries detected", long_queries)

            # Check available connections
            max_conn = conn.execute(text("SHOW max_connections")).scalar()
            active_conn = conn.execute(text(
                "SELECT count(*) FROM pg_stat_activity"
            )).scalar()
            checks["connection_usage"] = f"{active_conn}/{max_conn}"

            # Check disk space (rough estimate via pg_database_size)
            db_size = conn.execute(text(
                "SELECT pg_size_pretty(pg_database_size(current_database()))"
            )).scalar()
            checks["database_size"] = db_size

            logger.info("Health check results: %s", json.dumps(checks, default=str))
            return True

    def run_migration(
        self,
        target: str = "head",
        *,
        auto_rollback: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """
        Execute migration with safety checks and optional auto-rollback.
        """
        result = {"success": False, "checkpoint": None, "rollback": None}

        # Step 1: Health check
        if not self.pre_migration_health_check():
            result["error"] = "Pre-migration health check failed"
            return result

        # Step 2: Create checkpoint
        checkpoint = self.create_checkpoint()
        result["checkpoint"] = checkpoint

        if dry_run:
            result["preview"] = self.preview_migration(target)
            result["success"] = True
            return result

        # Step 3: Execute migration
        start_time = time.time()
        try:
            logger.info("Starting migration to %s from %s", target, checkpoint.revision)
            proc = subprocess.run(
                ["alembic", "upgrade", target],
                capture_output=True,
                text=True,
                timeout=600,  # 10-minute timeout
            )

            if proc.returncode != 0:
                raise RuntimeError(f"Alembic upgrade failed: {proc.stderr}")

            elapsed = time.time() - start_time
            logger.info("Migration completed in %.1fs", elapsed)

            # Step 4: Post-migration validation
            post_checkpoint = self.create_checkpoint()
            result["post_checkpoint"] = post_checkpoint
            result["duration_seconds"] = elapsed
            result["success"] = True

        except Exception as e:
            elapsed = time.time() - start_time
            logger.error("Migration failed after %.1fs: %s", elapsed, e)
            result["error"] = str(e)

            if auto_rollback:
                logger.info("Auto-rolling back to %s", checkpoint.revision)
                try:
                    subprocess.run(
                        ["alembic", "downgrade", checkpoint.revision],
                        capture_output=True,
                        text=True,
                        timeout=600,
                        check=True,
                    )
                    result["rollback"] = "success"
                    logger.info("Rollback to %s succeeded", checkpoint.revision)
                except Exception as rb_err:
                    result["rollback"] = f"failed: {rb_err}"
                    logger.critical("ROLLBACK FAILED: %s — manual intervention required", rb_err)

        return result


# ---- Migration test framework ----

class MigrationTester:
    """Automated testing of migration up/down cycle."""

    @staticmethod
    def test_migration_reversibility(database_url: str, revision: str) -> bool:
        """Test that a migration can be applied and rolled back cleanly."""
        engine = create_engine(database_url)

        with engine.connect() as conn:
            # Get schema before
            schema_before = conn.execute(text("""
                SELECT md5(string_agg(
                    table_name || column_name || data_type, '|'
                    ORDER BY table_name, ordinal_position
                ))
                FROM information_schema.columns
                WHERE table_schema = 'public'
            """)).scalar()

        # Upgrade
        subprocess.run(["alembic", "upgrade", revision], check=True)

        # Downgrade
        subprocess.run(["alembic", "downgrade", "-1"], check=True)

        with engine.connect() as conn:
            schema_after = conn.execute(text("""
                SELECT md5(string_agg(
                    table_name || column_name || data_type, '|'
                    ORDER BY table_name, ordinal_position
                ))
                FROM information_schema.columns
                WHERE table_schema = 'public'
            """)).scalar()

        if schema_before != schema_after:
            logger.error("Schema mismatch after up/down cycle!")
            return False

        logger.info("Migration %s is fully reversible", revision)
        return True
```

Rollback strategy comparison:

| Strategy | Speed | Risk | When to Use |
|----------|-------|------|-------------|
| Alembic downgrade | Fast (DDL only) | Low | Schema-only migrations |
| Point-in-time recovery | Slow (full restore) | Medium | Data corruption |
| Forward-fix | Variable | Low | When downgrade is impractical |
| Blue-green switch | Instant | Low | When using blue-green databases |
| Checkpoint + restore | Medium | Low | Large data migrations |

Key rollback principles:

- **Always write downgrades** — even if you never plan to use them, they prove reversibility
- **Test up/down cycles** in CI against a real database (not SQLite)
- **Forward-fix** is often safer than rollback for data migrations (add new migration to fix issues)
- **Advisory locks** prevent concurrent migrations from creating inconsistent state
- **Checkpoints** capture row counts and schema hashes for post-migration validation
'''
    ),
    (
        "database-migrations/concurrent-index-creation",
        "Show how to safely create indexes on large tables without downtime using Alembic, including concurrent index creation and partial indexes.",
        '''Safe index creation on large PostgreSQL tables with concurrent and partial indexes:

```python
# --- alembic/versions/2026_03_03_idx01_create_performance_indexes.py ---

"""Create performance indexes on large tables without downtime."""

from alembic import op
import sqlalchemy as sa

revision = "idx01_perf_v1"
down_revision = "prev_rev"

# IMPORTANT: Concurrent index creation cannot run inside a transaction.
# Alembic wraps migrations in transactions by default, so we must disable it.


def upgrade() -> None:
    # ---- Strategy 1: CONCURRENTLY for large tables ----
    # CREATE INDEX CONCURRENTLY takes a weaker lock (ShareUpdateExclusiveLock)
    # instead of AccessExclusiveLock, allowing reads AND writes during creation.

    # Must run outside a transaction block
    op.execute("COMMIT")  # End the implicit transaction

    # B-tree index for exact lookups and range queries
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_customer_created
        ON orders (customer_id, created_at DESC)
    """)

    # Covering index (INCLUDE) — index-only scans without heap access
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_covering
        ON orders (customer_id, status)
        INCLUDE (total, currency)
    """)

    # ---- Strategy 2: Partial indexes for hot queries ----
    # Only index rows matching a WHERE clause — much smaller, faster to build

    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_orders_active
        ON orders (customer_id, created_at DESC)
        WHERE status IN ('pending', 'processing', 'shipped')
    """)

    # Partial index for soft-deleted rows
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_active
        ON users (email)
        WHERE deleted_at IS NULL
    """)

    # ---- Strategy 3: Expression indexes ----
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_users_email_lower
        ON users (LOWER(email))
    """)

    # GIN index for JSONB containment queries
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_events_metadata
        ON events USING gin (metadata jsonb_path_ops)
    """)

    # ---- Strategy 4: Hash index for equality-only lookups ----
    op.execute("""
        CREATE INDEX CONCURRENTLY IF NOT EXISTS ix_sessions_token_hash
        ON sessions USING hash (session_token)
    """)

    # Verify all indexes are valid (CONCURRENTLY can leave invalid indexes on failure)
    _verify_indexes(op.get_bind())


def _verify_indexes(conn) -> None:
    """Check that all newly created indexes are valid."""
    invalid = conn.execute(sa.text("""
        SELECT indexrelid::regclass AS index_name,
               indrelid::regclass AS table_name
        FROM pg_index
        WHERE NOT indisvalid
    """)).fetchall()

    if invalid:
        for idx_name, table_name in invalid:
            # Drop and recreate invalid indexes
            conn.execute(sa.text(f"DROP INDEX CONCURRENTLY IF EXISTS {idx_name}"))
            raise RuntimeError(
                f"Index {idx_name} on {table_name} is invalid. "
                "Dropped it — re-run migration to recreate."
            )


def downgrade() -> None:
    op.execute("COMMIT")  # Exit transaction for CONCURRENTLY

    indexes_to_drop = [
        "ix_orders_customer_created",
        "ix_orders_covering",
        "ix_orders_active",
        "ix_users_active",
        "ix_users_email_lower",
        "ix_events_metadata",
        "ix_sessions_token_hash",
    ]

    for idx in indexes_to_drop:
        op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {idx}")
```

```python
# --- index_advisor.py --- Analyze queries and suggest indexes ---

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import sqlalchemy as sa
from sqlalchemy import text

logger = logging.getLogger(__name__)


@dataclass
class IndexRecommendation:
    table: str
    columns: list[str]
    type: str  # btree, gin, hash, brin
    is_partial: bool
    where_clause: str | None
    estimated_size_mb: float
    reason: str


class IndexAdvisor:
    """Analyze slow queries and recommend indexes."""

    def __init__(self, engine: sa.engine.Engine) -> None:
        self._engine = engine

    def find_missing_indexes(self) -> list[IndexRecommendation]:
        """Analyze pg_stat_user_tables for sequential scan heavy tables."""
        with self._engine.connect() as conn:
            results = conn.execute(text("""
                SELECT
                    schemaname, relname,
                    seq_scan, seq_tup_read,
                    idx_scan, idx_tup_fetch,
                    n_live_tup,
                    pg_size_pretty(pg_relation_size(relid)) as table_size
                FROM pg_stat_user_tables
                WHERE seq_scan > 1000
                AND n_live_tup > 10000
                AND (idx_scan IS NULL OR seq_scan > idx_scan * 10)
                ORDER BY seq_tup_read DESC
                LIMIT 20
            """)).fetchall()

            recommendations = []
            for row in results:
                recommendations.append(IndexRecommendation(
                    table=row.relname,
                    columns=["<analyze slow queries to determine>"],
                    type="btree",
                    is_partial=False,
                    where_clause=None,
                    estimated_size_mb=0,
                    reason=(
                        f"Table '{row.relname}' has {row.seq_scan} sequential scans "
                        f"vs {row.idx_scan or 0} index scans on {row.n_live_tup} rows"
                    ),
                ))

            return recommendations

    def get_unused_indexes(self) -> list[dict[str, Any]]:
        """Find indexes that are never used (candidates for removal)."""
        with self._engine.connect() as conn:
            return conn.execute(text("""
                SELECT
                    indexrelid::regclass AS index_name,
                    relid::regclass AS table_name,
                    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
                    idx_scan AS times_used
                FROM pg_stat_user_indexes
                WHERE idx_scan = 0
                AND indexrelid NOT IN (
                    SELECT conindid FROM pg_constraint
                    WHERE contype IN ('p', 'u')  -- Exclude PK and UNIQUE constraints
                )
                ORDER BY pg_relation_size(indexrelid) DESC
                LIMIT 20
            """)).mappings().fetchall()
```

Index creation strategies for zero-downtime:

| Strategy | Lock Level | Blocks Writes? | Blocks Reads? | Build Time |
|----------|-----------|---------------|--------------|-----------|
| CREATE INDEX | AccessExclusive | Yes | Yes | Fast |
| CREATE INDEX CONCURRENTLY | ShareUpdateExclusive | No | No | 2-3x slower |
| REINDEX CONCURRENTLY | ShareUpdateExclusive | No | No | Same as create |

Index type selection guide:

| Index Type | Best For | Size | Notes |
|-----------|---------|------|-------|
| B-tree | Equality, range, sorting | Medium | Default, most versatile |
| Hash | Equality only | Small | Faster for point lookups |
| GIN | Full-text, JSONB, arrays | Large | Handles multi-valued columns |
| GiST | Geometric, range types | Medium | Supports overlap/contains |
| BRIN | Time-series, naturally ordered | Tiny | Only for physically sorted data |
| Covering (INCLUDE) | Index-only scans | Larger | Avoids heap lookups |
| Partial (WHERE) | Hot subset queries | Small | Only indexes matching rows |
'''
    ),
]
