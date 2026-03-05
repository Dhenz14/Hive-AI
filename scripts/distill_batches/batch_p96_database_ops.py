"""Database operations — migrations, connection pooling, and query builders."""

PAIRS = [
    (
        "database/migrations",
        "Show database migration patterns: versioned migrations, rollbacks, and schema management with Alembic.",
        '''Database migration patterns with Alembic:

```python
# --- Alembic setup ---
# alembic init migrations
# Edit alembic.ini: sqlalchemy.url = postgresql://user:pass@localhost/mydb

# migrations/env.py
from alembic import context
from sqlalchemy import engine_from_config, pool
from myapp.models import Base  # Import your models

target_metadata = Base.metadata


# --- Migration script (auto-generated) ---
# alembic revision --autogenerate -m "add users table"

# migrations/versions/001_add_users_table.py

"""Add users table."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "001"
down_revision = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(254), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("password_hash", sa.String(128), nullable=False),
        sa.Column("metadata", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("is_active", sa.Boolean, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_users_email", "users", ["email"])
    op.create_index("idx_users_created", "users", ["created_at"])


def downgrade():
    op.drop_index("idx_users_created")
    op.drop_index("idx_users_email")
    op.drop_table("users")


# --- Data migration ---
# alembic revision -m "backfill user display names"

# migrations/versions/005_backfill_display_names.py

"""Backfill user display names."""
from alembic import op
import sqlalchemy as sa

revision = "005"
down_revision = "004"


def upgrade():
    # Add column
    op.add_column("users", sa.Column("display_name", sa.String(100)))

    # Backfill data in batches (avoid locking entire table)
    conn = op.get_bind()
    users = sa.table("users",
        sa.column("id", sa.String),
        sa.column("name", sa.String),
        sa.column("display_name", sa.String),
    )

    # Process in batches of 1000
    while True:
        batch = conn.execute(
            sa.select(users.c.id, users.c.name)
            .where(users.c.display_name.is_(None))
            .limit(1000)
        ).fetchall()

        if not batch:
            break

        for row in batch:
            conn.execute(
                users.update()
                .where(users.c.id == row.id)
                .values(display_name=row.name.split()[0])
            )

    # Make non-nullable after backfill
    op.alter_column("users", "display_name", nullable=False)


def downgrade():
    op.drop_column("users", "display_name")


# --- Zero-downtime migration pattern ---

# Step 1: Add column (nullable, no default) — no lock
# Step 2: Deploy code that writes to both old and new column
# Step 3: Backfill existing rows (batched)
# Step 4: Add NOT NULL constraint
# Step 5: Deploy code that reads from new column only
# Step 6: Drop old column

# --- Commands ---
# alembic upgrade head          # Apply all migrations
# alembic downgrade -1          # Rollback one migration
# alembic history               # Show migration history
# alembic current               # Show current revision
# alembic stamp head            # Mark DB as up-to-date without running
```

Migration patterns:
1. **`--autogenerate`** — detect model changes and generate migration scripts
2. **Batched backfill** — process data in chunks to avoid table locks
3. **Separate DDL and data** — schema changes and data backfills in separate migrations
4. **Zero-downtime** — expand-migrate-contract pattern for production
5. **`downgrade()`** — every migration must be reversible for rollback safety'''
    ),
    (
        "database/connection-pooling",
        "Show database connection pooling patterns: pool sizing, health checks, and async connection management.",
        '''Connection pooling patterns:

```python
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

import asyncpg
from sqlalchemy.ext.asyncio import (
    create_async_engine, AsyncSession, async_sessionmaker,
)
from sqlalchemy import text

logger = logging.getLogger(__name__)


# --- asyncpg pool (raw, fastest) ---

class DatabasePool:
    """Managed asyncpg connection pool."""

    def __init__(self, dsn: str, min_size: int = 5, max_size: int = 20):
        self.dsn = dsn
        self.min_size = min_size
        self.max_size = max_size
        self._pool: asyncpg.Pool | None = None

    async def start(self):
        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=self.min_size,
            max_size=self.max_size,
            max_inactive_connection_lifetime=300,  # Close idle after 5 min
            command_timeout=30,
            setup=self._setup_connection,
        )
        logger.info("Pool created: %d-%d connections", self.min_size, self.max_size)

    async def _setup_connection(self, conn: asyncpg.Connection):
        """Called for each new connection."""
        await conn.execute("SET timezone = 'UTC'")
        await conn.execute("SET statement_timeout = '30s'")

    async def stop(self):
        if self._pool:
            await self._pool.close()
            logger.info("Pool closed")

    @asynccontextmanager
    async def acquire(self) -> AsyncGenerator[asyncpg.Connection, None]:
        async with self._pool.acquire() as conn:
            yield conn

    @asynccontextmanager
    async def transaction(self) -> AsyncGenerator[asyncpg.Connection, None]:
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                yield conn

    async def health_check(self) -> bool:
        try:
            async with self.acquire() as conn:
                await conn.fetchval("SELECT 1")
            return True
        except Exception as e:
            logger.error("Health check failed: %s", e)
            return False

    @property
    def stats(self) -> dict:
        if not self._pool:
            return {}
        return {
            "size": self._pool.get_size(),
            "free": self._pool.get_idle_size(),
            "used": self._pool.get_size() - self._pool.get_idle_size(),
            "min": self._pool.get_min_size(),
            "max": self._pool.get_max_size(),
        }


# --- SQLAlchemy async pool ---

class SQLAlchemyPool:
    """SQLAlchemy async session factory with pool."""

    def __init__(self, database_url: str):
        self.engine = create_async_engine(
            database_url,
            pool_size=10,            # Steady-state connections
            max_overflow=20,         # Extra connections under load
            pool_timeout=30,         # Wait for connection
            pool_recycle=3600,       # Recycle connections after 1 hour
            pool_pre_ping=True,      # Health check before use
            echo=False,
        )
        self.session_factory = async_sessionmaker(
            self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def health_check(self) -> bool:
        try:
            async with self.engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
            return True
        except Exception:
            return False

    async def close(self):
        await self.engine.dispose()


# --- Pool sizing guidelines ---

# Formula: connections = (2 * num_cores) + num_spindles
# For SSD: connections ≈ (2 * CPU cores) + 1
# Example: 4-core server → pool_size = 9

# Too few connections: requests queue up, high latency
# Too many connections: DB overwhelmed, context switching overhead
# Sweet spot: monitor query wait times and connection utilization

# PostgreSQL max_connections default is 100
# Each connection uses ~5-10 MB RAM on the server
# Rule: total app pools < max_connections - 10 (leave room for admin)

POOL_SIZING = {
    "small":  {"pool_size": 5,  "max_overflow": 5},   # Dev / small app
    "medium": {"pool_size": 10, "max_overflow": 20},  # Standard web app
    "large":  {"pool_size": 20, "max_overflow": 40},  # High-traffic
}
```

Connection pooling patterns:
1. **`min_size` / `max_size`** — maintain warm connections, cap under load
2. **`pool_pre_ping`** — detect stale connections before queries
3. **`pool_recycle`** — recycle connections periodically (prevents stale auth)
4. **Session context manager** — auto-commit on success, rollback on error
5. **Pool sizing** — `(2 * cores) + 1` as starting point, monitor and adjust'''
    ),
    (
        "database/query-builder",
        "Show type-safe query builder patterns: composable queries, pagination, and dynamic filtering.",
        '''Query builder patterns:

```python
from dataclasses import dataclass, field
from typing import Any
from enum import Enum


class SortOrder(Enum):
    ASC = "ASC"
    DESC = "DESC"


@dataclass
class QueryBuilder:
    """Composable SQL query builder with parameterized queries."""

    _table: str = ""
    _select: list[str] = field(default_factory=lambda: ["*"])
    _where: list[str] = field(default_factory=list)
    _params: list[Any] = field(default_factory=list)
    _order_by: list[str] = field(default_factory=list)
    _limit: int | None = None
    _offset: int | None = None
    _joins: list[str] = field(default_factory=list)
    _group_by: list[str] = field(default_factory=list)
    _having: list[str] = field(default_factory=list)

    def table(self, name: str) -> "QueryBuilder":
        self._table = name
        return self

    def select(self, *columns: str) -> "QueryBuilder":
        self._select = list(columns)
        return self

    def where(self, condition: str, *params: Any) -> "QueryBuilder":
        self._where.append(condition)
        self._params.extend(params)
        return self

    def where_in(self, column: str, values: list) -> "QueryBuilder":
        placeholders = ", ".join(["%s"] * len(values))
        self._where.append(f"{column} IN ({placeholders})")
        self._params.extend(values)
        return self

    def where_between(self, column: str, low: Any, high: Any) -> "QueryBuilder":
        self._where.append(f"{column} BETWEEN %s AND %s")
        self._params.extend([low, high])
        return self

    def join(self, table: str, on: str, join_type: str = "INNER") -> "QueryBuilder":
        self._joins.append(f"{join_type} JOIN {table} ON {on}")
        return self

    def order_by(self, column: str, order: SortOrder = SortOrder.ASC) -> "QueryBuilder":
        self._order_by.append(f"{column} {order.value}")
        return self

    def limit(self, n: int) -> "QueryBuilder":
        self._limit = n
        return self

    def offset(self, n: int) -> "QueryBuilder":
        self._offset = n
        return self

    def group_by(self, *columns: str) -> "QueryBuilder":
        self._group_by = list(columns)
        return self

    def build(self) -> tuple[str, list[Any]]:
        """Build SQL string and parameters."""
        parts = [f"SELECT {', '.join(self._select)}", f"FROM {self._table}"]

        for join in self._joins:
            parts.append(join)

        if self._where:
            parts.append("WHERE " + " AND ".join(self._where))

        if self._group_by:
            parts.append("GROUP BY " + ", ".join(self._group_by))

        if self._having:
            parts.append("HAVING " + " AND ".join(self._having))

        if self._order_by:
            parts.append("ORDER BY " + ", ".join(self._order_by))

        if self._limit is not None:
            parts.append(f"LIMIT {self._limit}")

        if self._offset is not None:
            parts.append(f"OFFSET {self._offset}")

        return " ".join(parts), self._params


# --- Dynamic filtering ---

@dataclass
class OrderFilter:
    status: str | None = None
    customer_id: str | None = None
    min_total: float | None = None
    max_total: float | None = None
    date_from: str | None = None
    date_to: str | None = None
    sort_by: str = "created_at"
    sort_order: str = "desc"
    page: int = 1
    per_page: int = 20


def build_order_query(filters: OrderFilter) -> tuple[str, list]:
    """Build query from filter object."""
    qb = QueryBuilder().table("orders").select(
        "orders.*", "customers.name as customer_name",
    ).join("customers", "customers.id = orders.customer_id", "LEFT")

    if filters.status:
        qb.where("orders.status = %s", filters.status)
    if filters.customer_id:
        qb.where("orders.customer_id = %s", filters.customer_id)
    if filters.min_total is not None:
        qb.where("orders.total >= %s", filters.min_total)
    if filters.max_total is not None:
        qb.where("orders.total <= %s", filters.max_total)
    if filters.date_from:
        qb.where("orders.created_at >= %s", filters.date_from)
    if filters.date_to:
        qb.where("orders.created_at <= %s", filters.date_to)

    # Whitelist sortable columns to prevent SQL injection
    allowed_sorts = {"created_at", "total", "status", "customer_name"}
    sort_col = filters.sort_by if filters.sort_by in allowed_sorts else "created_at"
    sort_dir = SortOrder.DESC if filters.sort_order == "desc" else SortOrder.ASC
    qb.order_by(sort_col, sort_dir)

    qb.limit(filters.per_page)
    qb.offset((filters.page - 1) * filters.per_page)

    return qb.build()

# sql, params = build_order_query(OrderFilter(status="active", min_total=100))
# cursor.execute(sql, params)
```

Query builder patterns:
1. **Parameterized queries** — `%s` placeholders prevent SQL injection
2. **Composable methods** — chain `.where().join().order_by()` fluently
3. **Dynamic filtering** — filter object → query with optional conditions
4. **Sort whitelist** — only allow known columns to prevent injection
5. **Cursor pagination** — use `LIMIT`/`OFFSET` with page calculation'''
    ),
]
"""
