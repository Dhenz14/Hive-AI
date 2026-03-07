"""Async/concurrency training pairs: async database access."""

pairs = [
    {
        "instruction": r'''How do I use asyncpg for async PostgreSQL access in Python? Show connection pooling and basic CRUD operations.''',
        "output": r'''<think>
asyncpg is the fastest async PostgreSQL driver for Python. It is written in Cython and uses the binary PostgreSQL protocol. Key things to cover:

1. Connection pools (critical for production) -- create_pool with min/max size
2. Basic operations: fetch, fetchrow, fetchval, execute
3. Parameterized queries (asyncpg uses $1, $2 syntax, not %s or ?)
4. Transaction management
5. Type handling (asyncpg has excellent automatic type conversion)

I should show a clean pattern with a database class that manages the pool lifecycle.

One gotcha: asyncpg does NOT support the DBAPI interface. It has its own API which is different from psycopg2. The placeholder syntax is $1, $2 (PostgreSQL native) instead of %s.
</think>

```python
import asyncio
import asyncpg
from typing import Any, Optional
from contextlib import asynccontextmanager

# ============================================================
# Connection pool setup
# ============================================================

class Database:
    """Async PostgreSQL client with connection pooling."""

    def __init__(self, dsn: str, min_pool: int = 2, max_pool: int = 10):
        self.dsn = dsn
        self.min_pool = min_pool
        self.max_pool = max_pool
        self._pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        self._pool = await asyncpg.create_pool(
            self.dsn,
            min_size=self.min_pool,
            max_size=self.max_pool,
            command_timeout=30,
        )

    async def disconnect(self):
        if self._pool:
            await self._pool.close()

    @asynccontextmanager
    async def acquire(self):
        async with self._pool.acquire() as conn:
            yield conn

    # ============================================================
    # CRUD operations
    # ============================================================

    async def get_user(self, user_id: int) -> Optional[dict]:
        async with self.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, name, email, created_at "
                "FROM users WHERE id = $1",
                user_id,
            )
            return dict(row) if row else None

    async def list_users(
        self, limit: int = 50, offset: int = 0
    ) -> list[dict]:
        async with self.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, name, email, created_at "
                "FROM users ORDER BY id LIMIT $1 OFFSET $2",
                limit, offset,
            )
            return [dict(row) for row in rows]

    async def create_user(self, name: str, email: str) -> int:
        async with self.acquire() as conn:
            user_id = await conn.fetchval(
                "INSERT INTO users (name, email) "
                "VALUES ($1, $2) RETURNING id",
                name, email,
            )
            return user_id

    async def update_user(
        self, user_id: int, name: str, email: str
    ) -> bool:
        async with self.acquire() as conn:
            result = await conn.execute(
                "UPDATE users SET name = $1, email = $2 "
                "WHERE id = $3",
                name, email, user_id,
            )
            # result is like "UPDATE 1" or "UPDATE 0"
            return result == "UPDATE 1"

    async def delete_user(self, user_id: int) -> bool:
        async with self.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM users WHERE id = $1", user_id
            )
            return result == "DELETE 1"

    # ============================================================
    # Transactions
    # ============================================================

    async def transfer_balance(
        self, from_id: int, to_id: int, amount: float
    ):
        async with self.acquire() as conn:
            async with conn.transaction():
                # Both operations are atomic
                await conn.execute(
                    "UPDATE accounts SET balance = balance - $1 "
                    "WHERE user_id = $2",
                    amount, from_id,
                )
                await conn.execute(
                    "UPDATE accounts SET balance = balance + $1 "
                    "WHERE user_id = $2",
                    amount, to_id,
                )

    # ============================================================
    # Bulk operations
    # ============================================================

    async def bulk_insert_users(
        self, users: list[tuple[str, str]]
    ) -> int:
        """Insert many users efficiently using copy."""
        async with self.acquire() as conn:
            result = await conn.copy_records_to_table(
                "users",
                records=[(name, email) for name, email in users],
                columns=["name", "email"],
            )
            return len(users)

# ============================================================
# Usage
# ============================================================

async def main():
    db = Database("postgresql://user:pass@localhost:5432/mydb")
    await db.connect()

    try:
        # Create
        user_id = await db.create_user("Alice", "alice@example.com")
        print(f"Created user {user_id}")

        # Read
        user = await db.get_user(user_id)
        print(f"User: {user}")

        # Update
        updated = await db.update_user(user_id, "Alice B.", "alice@new.com")
        print(f"Updated: {updated}")

        # List
        users = await db.list_users(limit=10)
        print(f"Total users: {len(users)}")

        # Delete
        deleted = await db.delete_user(user_id)
        print(f"Deleted: {deleted}")
    finally:
        await db.disconnect()

# asyncio.run(main())
```

Key points:
- Always use connection pooling in production (`create_pool`)
- asyncpg uses `$1, $2` parameter placeholders (not `%s`)
- `fetchrow` returns one row, `fetch` returns many, `fetchval` returns one value
- Use `conn.transaction()` for atomic multi-statement operations
- `copy_records_to_table` is the fastest way to bulk insert'''
    },
    {
        "instruction": r'''How do I use SQLAlchemy 2.0 with async support? Show the async engine, session, and ORM patterns.''',
        "output": r'''```python
import asyncio
from typing import Optional
from datetime import datetime

from sqlalchemy import String, ForeignKey, select, func
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    selectinload,
)

# ============================================================
# Model definitions
# ============================================================

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    posts: Mapped[list["Post"]] = relationship(
        back_populates="author", lazy="selectin"
    )

class Post(Base):
    __tablename__ = "posts"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str]
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"))

    author: Mapped["User"] = relationship(back_populates="posts")

# ============================================================
# Async engine and session setup
# ============================================================

# Use async driver: asyncpg for PostgreSQL, aiosqlite for SQLite
engine = create_async_engine(
    "postgresql+asyncpg://user:pass@localhost:5432/mydb",
    echo=False,
    pool_size=5,
    max_overflow=10,
)

# Session factory
async_session = async_sessionmaker(engine, expire_on_commit=False)

# ============================================================
# CRUD operations
# ============================================================

class UserRepository:
    """Async repository for User operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, name: str, email: str) -> User:
        user = User(name=name, email=email)
        self.session.add(user)
        await self.session.flush()  # get the ID without committing
        return user

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self.session.execute(
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.posts))
        )
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.session.execute(
            select(User).where(User.email == email)
        )
        return result.scalar_one_or_none()

    async def list_users(
        self, limit: int = 50, offset: int = 0
    ) -> list[User]:
        result = await self.session.execute(
            select(User)
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def update(self, user_id: int, **kwargs) -> Optional[User]:
        user = await self.get_by_id(user_id)
        if user is None:
            return None
        for key, value in kwargs.items():
            setattr(user, key, value)
        return user

    async def delete(self, user_id: int) -> bool:
        user = await self.get_by_id(user_id)
        if user is None:
            return False
        await self.session.delete(user)
        return True

    async def count(self) -> int:
        result = await self.session.execute(
            select(func.count()).select_from(User)
        )
        return result.scalar_one()

# ============================================================
# Service layer with transaction management
# ============================================================

class UserService:
    async def create_user_with_post(
        self, name: str, email: str, post_title: str, post_content: str
    ) -> User:
        async with async_session() as session:
            async with session.begin():
                # Everything inside begin() is one transaction
                repo = UserRepository(session)
                user = await repo.create(name, email)

                post = Post(
                    title=post_title,
                    content=post_content,
                    author_id=user.id,
                )
                session.add(post)
                # Commit happens automatically at end of begin()

            return user

    async def get_user(self, user_id: int) -> Optional[User]:
        async with async_session() as session:
            repo = UserRepository(session)
            return await repo.get_by_id(user_id)

# ============================================================
# Startup/shutdown
# ============================================================

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def shutdown_db():
    await engine.dispose()

async def main():
    await init_db()

    service = UserService()
    user = await service.create_user_with_post(
        name="Alice",
        email="alice@example.com",
        post_title="First Post",
        post_content="Hello, world!",
    )
    print(f"Created user: {user.name} (id={user.id})")

    fetched = await service.get_user(user.id)
    if fetched:
        print(f"Posts: {len(fetched.posts)}")

    await shutdown_db()

# asyncio.run(main())
```

Key patterns:
- Use `create_async_engine` with an async driver (`asyncpg`, `aiosqlite`)
- Use `async_sessionmaker` to create session factories
- `session.begin()` provides automatic commit/rollback
- Use `selectinload()` for eager loading relations (lazy loading does not work in async)
- Call `engine.dispose()` on shutdown to clean up the connection pool'''
    },
    {
        "instruction": r'''How do I manage async database connection pools properly? What are the best practices for pool sizing, health checks, and error recovery?''',
        "output": r'''<think>
Connection pool management is critical for production async applications. The key concerns:

1. Pool sizing: too small = connection starvation under load; too large = wastes database connections and can hit server limits
2. Health checks: connections can go stale (network timeout, server restart). Need to validate before use.
3. Error recovery: what happens when the database goes down? Need to handle reconnection gracefully.
4. Connection lifetime: long-lived connections can accumulate resources on the server side.

For pool sizing, a common formula is: pool_size = (2 * num_cpu_cores) + number_of_spindles. But for async, it depends more on the concurrency of your application and the database's max_connections setting.

Let me show a production-quality pool management pattern with asyncpg.
</think>

```python
import asyncio
import asyncpg
import logging
import time
from typing import Any, Optional, AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class PoolConfig:
    dsn: str
    min_size: int = 2
    max_size: int = 10
    max_idle_seconds: float = 300.0
    command_timeout: float = 30.0
    statement_cache_size: int = 100
    # Health check
    health_check_interval: float = 30.0
    # Retry
    max_connect_retries: int = 5
    retry_delay: float = 1.0

class ManagedPool:
    """Production-ready async database connection pool."""

    def __init__(self, config: PoolConfig):
        self.config = config
        self._pool: Optional[asyncpg.Pool] = None
        self._health_task: Optional[asyncio.Task] = None
        self._stats = {
            "queries": 0,
            "errors": 0,
            "reconnects": 0,
        }

    async def start(self):
        """Initialize the pool with retry logic."""
        for attempt in range(1, self.config.max_connect_retries + 1):
            try:
                self._pool = await asyncpg.create_pool(
                    self.config.dsn,
                    min_size=self.config.min_size,
                    max_size=self.config.max_size,
                    max_inactive_connection_lifetime=(
                        self.config.max_idle_seconds
                    ),
                    command_timeout=self.config.command_timeout,
                    statement_cache_size=(
                        self.config.statement_cache_size
                    ),
                    setup=self._setup_connection,
                )
                logger.info("Database pool connected (size %d-%d)",
                    self.config.min_size, self.config.max_size)
                break
            except (OSError, asyncpg.PostgresError) as e:
                logger.warning(
                    "Connection attempt %d/%d failed: %s",
                    attempt, self.config.max_connect_retries, e,
                )
                if attempt == self.config.max_connect_retries:
                    raise
                await asyncio.sleep(
                    self.config.retry_delay * attempt
                )

        # Start health check background task
        self._health_task = asyncio.create_task(
            self._health_check_loop()
        )

    async def stop(self):
        """Gracefully shut down the pool."""
        if self._health_task:
            self._health_task.cancel()
            try:
                await self._health_task
            except asyncio.CancelledError:
                pass
        if self._pool:
            await self._pool.close()
            logger.info("Database pool closed")

    @staticmethod
    async def _setup_connection(conn: asyncpg.Connection):
        """Called for each new connection in the pool."""
        await conn.execute("SET timezone = 'UTC'")
        await conn.execute(
            "SET statement_timeout = '30s'"
        )

    @asynccontextmanager
    async def acquire(self):
        """Get a connection from the pool with error handling."""
        if not self._pool:
            raise RuntimeError("Pool not started")
        try:
            async with self._pool.acquire() as conn:
                self._stats["queries"] += 1
                yield conn
        except asyncpg.InterfaceError as e:
            self._stats["errors"] += 1
            logger.error("Connection error: %s", e)
            raise
        except asyncpg.PostgresError as e:
            self._stats["errors"] += 1
            raise

    @asynccontextmanager
    async def transaction(self):
        """Get a connection with an active transaction."""
        async with self.acquire() as conn:
            async with conn.transaction():
                yield conn

    async def execute(self, query: str, *args) -> str:
        async with self.acquire() as conn:
            return await conn.execute(query, *args)

    async def fetch(self, query: str, *args) -> list:
        async with self.acquire() as conn:
            return await conn.fetch(query, *args)

    async def fetchrow(self, query: str, *args):
        async with self.acquire() as conn:
            return await conn.fetchrow(query, *args)

    async def fetchval(self, query: str, *args):
        async with self.acquire() as conn:
            return await conn.fetchval(query, *args)

    # ============================================================
    # Health monitoring
    # ============================================================

    async def _health_check_loop(self):
        while True:
            await asyncio.sleep(self.config.health_check_interval)
            try:
                await self._check_health()
            except Exception as e:
                logger.error("Health check failed: %s", e)

    async def _check_health(self):
        try:
            async with self.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                assert result == 1
        except Exception as e:
            logger.warning("Database health check failed: %s", e)
            self._stats["errors"] += 1
            raise

    def get_stats(self) -> dict[str, Any]:
        pool_stats = {}
        if self._pool:
            pool_stats = {
                "pool_size": self._pool.get_size(),
                "pool_free": self._pool.get_idle_size(),
                "pool_min": self._pool.get_min_size(),
                "pool_max": self._pool.get_max_size(),
            }
        return {**self._stats, **pool_stats}

# ============================================================
# Usage with FastAPI-style lifecycle
# ============================================================

pool = ManagedPool(PoolConfig(
    dsn="postgresql://user:pass@localhost:5432/mydb",
    min_size=2,
    max_size=20,
))

async def startup():
    await pool.start()

async def shutdown():
    await pool.stop()

async def get_user(user_id: int) -> Optional[dict]:
    row = await pool.fetchrow(
        "SELECT id, name, email FROM users WHERE id = $1",
        user_id,
    )
    return dict(row) if row else None

async def create_user_with_profile(
    name: str, email: str, bio: str,
) -> int:
    async with pool.transaction() as conn:
        user_id = await conn.fetchval(
            "INSERT INTO users (name, email) "
            "VALUES ($1, $2) RETURNING id",
            name, email,
        )
        await conn.execute(
            "INSERT INTO profiles (user_id, bio) "
            "VALUES ($1, $2)",
            user_id, bio,
        )
        return user_id
```

Pool sizing guidelines:
- `min_size`: 2-5 (keeps connections warm for low-traffic periods)
- `max_size`: depends on DB max_connections divided by app instances
- Formula: `max_size = db_max_connections / num_app_instances - buffer`
- Monitor `pool_free` vs `pool_size` to detect connection starvation'''
    },
    {
        "instruction": r'''Show me how to implement async bulk database operations -- bulk inserts, upserts, and batch updates -- efficiently in Python.''',
        "output": r'''```python
import asyncio
import asyncpg
from typing import Any, Optional
from itertools import islice

# ============================================================
# Bulk insert with COPY (fastest method)
# ============================================================

async def bulk_insert_copy(
    pool: asyncpg.Pool,
    table: str,
    columns: list[str],
    records: list[tuple],
) -> int:
    """Fastest bulk insert using PostgreSQL COPY protocol."""
    async with pool.acquire() as conn:
        result = await conn.copy_records_to_table(
            table,
            records=records,
            columns=columns,
        )
        # result is like "COPY 1000"
        return int(result.split()[1])

# Usage:
# users = [(f"user_{i}", f"user{i}@example.com") for i in range(10000)]
# count = await bulk_insert_copy(pool, "users", ["name", "email"], users)

# ============================================================
# Bulk insert with multi-row VALUES (good for moderate sizes)
# ============================================================

async def bulk_insert_values(
    pool: asyncpg.Pool,
    table: str,
    columns: list[str],
    records: list[tuple],
    batch_size: int = 1000,
) -> int:
    """Insert records in batches using multi-row VALUES."""
    total = 0
    col_str = ", ".join(columns)

    async with pool.acquire() as conn:
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]

            # Build VALUES clause: ($1,$2), ($3,$4), ...
            num_cols = len(columns)
            value_rows = []
            params = []
            for row_idx, row in enumerate(batch):
                placeholders = ", ".join(
                    f"${row_idx * num_cols + col_idx + 1}"
                    for col_idx in range(num_cols)
                )
                value_rows.append(f"({placeholders})")
                params.extend(row)

            values_str = ", ".join(value_rows)
            query = f"INSERT INTO {table} ({col_str}) VALUES {values_str}"

            await conn.execute(query, *params)
            total += len(batch)

    return total

# ============================================================
# Bulk upsert (INSERT ... ON CONFLICT)
# ============================================================

async def bulk_upsert(
    pool: asyncpg.Pool,
    table: str,
    columns: list[str],
    records: list[tuple],
    conflict_columns: list[str],
    update_columns: list[str],
    batch_size: int = 500,
) -> int:
    """Upsert records in batches."""
    total = 0
    col_str = ", ".join(columns)
    conflict_str = ", ".join(conflict_columns)
    update_str = ", ".join(
        f"{col} = EXCLUDED.{col}" for col in update_columns
    )
    num_cols = len(columns)

    async with pool.acquire() as conn:
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]

            value_rows = []
            params = []
            for row_idx, row in enumerate(batch):
                placeholders = ", ".join(
                    f"${row_idx * num_cols + col_idx + 1}"
                    for col_idx in range(num_cols)
                )
                value_rows.append(f"({placeholders})")
                params.extend(row)

            values_str = ", ".join(value_rows)
            query = (
                f"INSERT INTO {table} ({col_str}) VALUES {values_str} "
                f"ON CONFLICT ({conflict_str}) DO UPDATE SET {update_str}"
            )
            await conn.execute(query, *params)
            total += len(batch)

    return total

# Usage:
# await bulk_upsert(
#     pool, "users",
#     columns=["email", "name", "updated_at"],
#     records=[("alice@x.com", "Alice", datetime.utcnow()), ...],
#     conflict_columns=["email"],
#     update_columns=["name", "updated_at"],
# )

# ============================================================
# Batch update with executemany
# ============================================================

async def batch_update(
    pool: asyncpg.Pool,
    query: str,
    params_list: list[tuple],
    batch_size: int = 500,
) -> int:
    """Execute an UPDATE for each set of params, in batches."""
    total = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Use prepared statement for efficiency
            stmt = await conn.prepare(query)
            for i in range(0, len(params_list), batch_size):
                batch = params_list[i:i + batch_size]
                await stmt.executemany(batch)
                total += len(batch)
    return total

# Usage:
# await batch_update(
#     pool,
#     "UPDATE users SET name = $1 WHERE id = $2",
#     [("New Name 1", 1), ("New Name 2", 2), ...],
# )

# ============================================================
# Streaming bulk read with cursor
# ============================================================

async def stream_large_table(
    pool: asyncpg.Pool,
    query: str,
    params: tuple = (),
    batch_size: int = 1000,
):
    """Stream rows from a large query without loading all into memory."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            async for row in conn.cursor(query, *params):
                yield dict(row)

async def process_large_table(pool: asyncpg.Pool):
    """Process a large table in chunks."""
    count = 0
    async for row in stream_large_table(
        pool,
        "SELECT * FROM large_table WHERE status = $1",
        ("pending",),
    ):
        count += 1
        # Process each row
        if count % 10000 == 0:
            print(f"Processed {count} rows")
    return count

# ============================================================
# Complete example
# ============================================================

async def demo(dsn: str):
    pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)

    try:
        # Bulk insert 10k records
        records = [
            (f"user_{i}", f"user{i}@example.com")
            for i in range(10000)
        ]
        count = await bulk_insert_copy(
            pool, "users", ["name", "email"], records
        )
        print(f"Inserted {count} records via COPY")

        # Bulk upsert
        upsert_records = [
            (f"user{i}@example.com", f"User {i} Updated")
            for i in range(5000)
        ]
        count = await bulk_upsert(
            pool, "users",
            columns=["email", "name"],
            records=upsert_records,
            conflict_columns=["email"],
            update_columns=["name"],
        )
        print(f"Upserted {count} records")
    finally:
        await pool.close()
```

Performance ranking (fastest to slowest for inserts):
1. `copy_records_to_table` -- binary COPY protocol, fastest
2. Multi-row VALUES -- good for moderate batches (100-5000 rows)
3. `executemany` with prepared statement -- good for updates
4. Individual INSERT in a loop -- slowest, avoid for bulk operations'''
    },
    {
        "instruction": r'''How do I handle database transaction isolation levels in async Python? Show practical examples of when different isolation levels matter.''',
        "output": r'''```python
import asyncio
import asyncpg
from typing import Optional
from enum import Enum

class IsolationLevel(str, Enum):
    READ_COMMITTED = "read_committed"
    REPEATABLE_READ = "repeatable_read"
    SERIALIZABLE = "serializable"

# ============================================================
# Helper: transaction with specific isolation level
# ============================================================

async def run_in_transaction(
    pool: asyncpg.Pool,
    callback,
    isolation: IsolationLevel = IsolationLevel.READ_COMMITTED,
    max_retries: int = 3,
):
    """Run a callback in a transaction with retry on serialization failure."""
    for attempt in range(1, max_retries + 1):
        try:
            async with pool.acquire() as conn:
                async with conn.transaction(
                    isolation=isolation.value,
                ):
                    return await callback(conn)
        except asyncpg.SerializationError:
            if attempt == max_retries:
                raise
            # Retry with backoff on serialization failure
            await asyncio.sleep(0.1 * attempt)

# ============================================================
# Scenario 1: READ COMMITTED (default) -- simple operations
# ============================================================

async def read_committed_example(pool: asyncpg.Pool):
    """READ COMMITTED is fine for independent operations."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Each query sees the latest committed data
            user = await conn.fetchrow(
                "SELECT * FROM users WHERE id = $1", 1
            )
            # Another transaction could commit between these queries
            orders = await conn.fetch(
                "SELECT * FROM orders WHERE user_id = $1", 1
            )
            # user and orders might be inconsistent if another
            # transaction modified data between the two queries
            return user, orders

# ============================================================
# Scenario 2: REPEATABLE READ -- consistent snapshots
# ============================================================

async def generate_report(pool: asyncpg.Pool) -> dict:
    """Report needs a consistent snapshot of the data."""

    async def _report(conn: asyncpg.Connection) -> dict:
        # All queries see data as of transaction start
        total_users = await conn.fetchval(
            "SELECT COUNT(*) FROM users"
        )
        total_revenue = await conn.fetchval(
            "SELECT COALESCE(SUM(amount), 0) FROM payments"
        )
        active_users = await conn.fetchval(
            "SELECT COUNT(*) FROM users WHERE last_active > NOW() - INTERVAL '30 days'"
        )
        # These numbers are guaranteed consistent -- no other
        # transaction can change what this transaction sees
        return {
            "total_users": total_users,
            "total_revenue": float(total_revenue),
            "active_users": active_users,
        }

    return await run_in_transaction(
        pool, _report, IsolationLevel.REPEATABLE_READ
    )

# ============================================================
# Scenario 3: SERIALIZABLE -- preventing double-spending
# ============================================================

async def transfer_funds(
    pool: asyncpg.Pool,
    from_account: int,
    to_account: int,
    amount: float,
):
    """Financial transfer must be serializable to prevent double-spend."""

    async def _transfer(conn: asyncpg.Connection):
        # Check balance
        balance = await conn.fetchval(
            "SELECT balance FROM accounts WHERE id = $1",
            from_account,
        )
        if balance < amount:
            raise ValueError(
                f"Insufficient funds: {balance} < {amount}"
            )

        # Debit and credit
        await conn.execute(
            "UPDATE accounts SET balance = balance - $1 WHERE id = $2",
            amount, from_account,
        )
        await conn.execute(
            "UPDATE accounts SET balance = balance + $1 WHERE id = $2",
            amount, to_account,
        )
        return {"from": from_account, "to": to_account, "amount": amount}

    # SERIALIZABLE ensures no two concurrent transfers can
    # both read the same balance and both succeed
    return await run_in_transaction(
        pool, _transfer, IsolationLevel.SERIALIZABLE, max_retries=5
    )

# ============================================================
# Scenario 4: SELECT FOR UPDATE -- row-level locking
# ============================================================

async def increment_counter(
    pool: asyncpg.Pool,
    counter_name: str,
) -> int:
    """Atomic counter increment using SELECT FOR UPDATE."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Lock the row -- other transactions wait
            row = await conn.fetchrow(
                "SELECT value FROM counters "
                "WHERE name = $1 FOR UPDATE",
                counter_name,
            )
            new_value = row["value"] + 1
            await conn.execute(
                "UPDATE counters SET value = $1 WHERE name = $2",
                new_value, counter_name,
            )
            return new_value

# Alternative: atomic UPDATE without explicit locking
async def increment_counter_simple(
    pool: asyncpg.Pool,
    counter_name: str,
) -> int:
    """Simpler atomic increment using RETURNING."""
    async with pool.acquire() as conn:
        return await conn.fetchval(
            "UPDATE counters SET value = value + 1 "
            "WHERE name = $1 RETURNING value",
            counter_name,
        )

# ============================================================
# Summary
# ============================================================

# READ COMMITTED (default):
#   Use for: most CRUD operations, independent queries
#   Risk: non-repeatable reads between queries in same transaction
#
# REPEATABLE READ:
#   Use for: reports, analytics, consistent multi-query reads
#   Risk: serialization errors (must retry)
#
# SERIALIZABLE:
#   Use for: financial transactions, inventory management
#   Risk: higher serialization error rate (must retry)
#
# SELECT FOR UPDATE:
#   Use for: counter increments, resource reservation
#   Simpler than SERIALIZABLE but locks specific rows
```

Key rules:
- Default to READ COMMITTED for most operations
- Use REPEATABLE READ for multi-query consistency (reports)
- Use SERIALIZABLE for operations where concurrent execution could violate invariants
- Always implement retry logic for REPEATABLE READ and SERIALIZABLE
- Prefer atomic SQL (UPDATE ... RETURNING) over SELECT-then-UPDATE when possible'''
    },
]
