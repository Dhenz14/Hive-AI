"""SQLAlchemy 2.0+ async patterns — engine management, relationship loading, hybrid properties, events, multi-tenancy."""

PAIRS = [
    (
        "python/sqlalchemy-async-engine-session",
        "Show SQLAlchemy 2.0+ async engine and session management with proper lifecycle, connection pooling, and dependency injection for FastAPI.",
        '''SQLAlchemy 2.0+ async engine and session management:

```python
from __future__ import annotations

import contextlib
from typing import AsyncGenerator, Any

from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.pool import AsyncAdaptedQueuePool


# ── Engine configuration ─────────────────────────────────────────

def create_engine(database_url: str, *, echo: bool = False) -> AsyncEngine:
    """Create async engine with production-ready pool settings."""
    return create_async_engine(
        database_url,
        echo=echo,
        # Pool configuration
        poolclass=AsyncAdaptedQueuePool,
        pool_size=10,           # steady-state connections
        max_overflow=20,        # burst capacity above pool_size
        pool_timeout=30,        # seconds to wait for connection
        pool_recycle=3600,      # recycle connections after 1 hour
        pool_pre_ping=True,     # verify connection before checkout
        # Performance
        connect_args={
            "server_settings": {
                "jit": "off",                  # avoid JIT for short queries
                "statement_timeout": "30000",  # 30s query timeout
            }
        },
    )


# ── Session factory ──────────────────────────────────────────────

class DatabaseManager:
    """Manages async engine lifecycle and session creation."""

    def __init__(self, database_url: str, echo: bool = False) -> None:
        self._engine = create_engine(database_url, echo=echo)
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,  # prevent lazy loads after commit
            autoflush=False,         # explicit flush control
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @contextlib.asynccontextmanager
    async def session(self) -> AsyncGenerator[AsyncSession, None]:
        """Provide a transactional session scope."""
        session = self._session_factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @contextlib.asynccontextmanager
    async def readonly_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Read-only session — sets transaction to read only."""
        session = self._session_factory()
        try:
            await session.execute(
                text("SET TRANSACTION READ ONLY")
            )
            yield session
        finally:
            await session.rollback()  # always rollback read-only
            await session.close()

    async def create_tables(self, base: type[DeclarativeBase]) -> None:
        async with self._engine.begin() as conn:
            await conn.run_sync(base.metadata.create_all)

    async def close(self) -> None:
        await self._engine.dispose()


# ── Base model ───────────────────────────────────────────────────

from datetime import datetime, timezone
from sqlalchemy import DateTime, func


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
```

```python
# ── FastAPI dependency injection ──────────────────────────────────

from fastapi import Depends, FastAPI, Request


db_manager = DatabaseManager(
    "postgresql+asyncpg://user:pass@localhost:5432/myapp"
)

app = FastAPI()


@app.on_event("startup")
async def startup() -> None:
    await db_manager.create_tables(Base)


@app.on_event("shutdown")
async def shutdown() -> None:
    await db_manager.close()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with db_manager.session() as session:
        yield session


async def get_readonly_session() -> AsyncGenerator[AsyncSession, None]:
    async with db_manager.readonly_session() as session:
        yield session


# Usage in routes
@app.get("/users/{user_id}")
async def get_user(
    user_id: int,
    session: AsyncSession = Depends(get_readonly_session),
) -> dict[str, Any]:
    result = await session.execute(
        text("SELECT id, name FROM users WHERE id = :id"),
        {"id": user_id},
    )
    row = result.one_or_none()
    if not row:
        from fastapi import HTTPException
        raise HTTPException(404, "User not found")
    return {"id": row.id, "name": row.name}


@app.post("/users")
async def create_user(
    name: str,
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    result = await session.execute(
        text("INSERT INTO users (name) VALUES (:name) RETURNING id"),
        {"name": name},
    )
    user_id = result.scalar_one()
    return {"id": user_id, "name": name}
```

```python
# ── Health checks and pool monitoring ─────────────────────────────

from sqlalchemy.pool import Pool


async def check_database_health(engine: AsyncEngine) -> dict[str, Any]:
    """Database health check with pool statistics."""
    pool: Pool = engine.pool  # type: ignore[assignment]
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            result.scalar()
        return {
            "status": "healthy",
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e),
        }


# ── Testing with async fixtures ──────────────────────────────────

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[DatabaseManager, None]:
    """In-memory SQLite for fast tests."""
    manager = DatabaseManager(
        "sqlite+aiosqlite:///:memory:",
        echo=True,
    )
    await manager.create_tables(Base)
    yield manager
    await manager.close()


@pytest_asyncio.fixture
async def test_session(
    test_db: DatabaseManager,
) -> AsyncGenerator[AsyncSession, None]:
    async with test_db.session() as session:
        yield session
        # Transaction is rolled back if test fails


@pytest.mark.asyncio
async def test_user_creation(test_session: AsyncSession) -> None:
    result = await test_session.execute(
        text("SELECT 1 AS val")
    )
    assert result.scalar() == 1
```

| Setting | Default | Production Value | Purpose |
|---|---|---|---|
| `pool_size` | 5 | 10-20 | Steady-state connections |
| `max_overflow` | 10 | 20-40 | Burst capacity |
| `pool_timeout` | 30 | 30 | Wait time for connection (secs) |
| `pool_recycle` | -1 | 3600 | Reconnect stale connections |
| `pool_pre_ping` | False | True | Verify connection on checkout |
| `expire_on_commit` | True | False | Prevent lazy loads after commit |
| `autoflush` | True | False | Explicit flush control |

Key patterns:
1. Use `async_sessionmaker` with `expire_on_commit=False` to prevent lazy-load traps.
2. Wrap sessions in context managers that auto-commit/rollback.
3. Separate read-only sessions with `SET TRANSACTION READ ONLY` for replicas.
4. Use `pool_pre_ping=True` in production to detect stale connections.
5. `pool_recycle=3600` prevents connections from being killed by database timeouts.
6. Always `await engine.dispose()` on shutdown to clean up the pool.'''
    ),
    (
        "python/sqlalchemy-async-relationship-loading",
        "Show SQLAlchemy 2.0+ relationship loading strategies: selectin, subquery, joined, lazy raise, and how to avoid N+1 queries in async code.",
        '''SQLAlchemy 2.0+ relationship loading strategies for async:

```python
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import ForeignKey, String, DateTime, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    selectinload,
    subqueryload,
    joinedload,
    raiseload,
    contains_eager,
    lazyload,
)


class Base(DeclarativeBase):
    pass


# ── Models with different relationship strategies ─────────────────

class Author(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    bio: Mapped[Optional[str]] = mapped_column(String(500), default=None)

    # Default eager loading: selectin (best for async)
    books: Mapped[list[Book]] = relationship(
        back_populates="author",
        lazy="selectin",        # eager load by default
        order_by="Book.published_at.desc()",
    )

    # Lazy with raiseload — forces explicit loading
    reviews: Mapped[list[Review]] = relationship(
        back_populates="author",
        lazy="raise",           # error if accessed without eager load
    )


class Book(Base):
    __tablename__ = "books"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id"))
    published_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    author: Mapped[Author] = relationship(back_populates="books")

    # Many-to-many through association table
    tags: Mapped[list[Tag]] = relationship(
        secondary="book_tags",
        lazy="selectin",
    )

    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="book",
        lazy="raise",  # must explicitly load
        order_by="Chapter.number",
    )


class Chapter(Base):
    __tablename__ = "chapters"

    id: Mapped[int] = mapped_column(primary_key=True)
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"))
    number: Mapped[int]
    title: Mapped[str] = mapped_column(String(200))

    book: Mapped[Book] = relationship(back_populates="chapters")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id"))
    book_id: Mapped[int] = mapped_column(ForeignKey("books.id"))
    rating: Mapped[int]
    content: Mapped[str] = mapped_column(String(2000))

    author: Mapped[Author] = relationship(back_populates="reviews")


# Association table for many-to-many
from sqlalchemy import Table, Column, Integer
book_tags = Table(
    "book_tags", Base.metadata,
    Column("book_id", Integer, ForeignKey("books.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
)
```

```python
# ── Loading strategy examples ─────────────────────────────────────

async def get_authors_with_books(session: AsyncSession) -> list[Author]:
    """selectinload — 2 queries: one for authors, one for books.
    Best for async because it avoids JOIN explosion."""
    stmt = (
        select(Author)
        .options(selectinload(Author.books))
        .order_by(Author.name)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_author_full(
    session: AsyncSession, author_id: int
) -> Author | None:
    """Deep eager loading — load author + books + chapters + tags."""
    stmt = (
        select(Author)
        .options(
            # Load books with selectin
            selectinload(Author.books)
            # Chain: also load each book's chapters
            .selectinload(Book.chapters),
            # And each book's tags
            selectinload(Author.books)
            .selectinload(Book.tags),
            # Also load reviews (overrides lazy="raise")
            selectinload(Author.reviews),
        )
        .where(Author.id == author_id)
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_books_with_author_joined(
    session: AsyncSession,
) -> list[Book]:
    """joinedload — single query with LEFT JOIN.
    Good for many-to-one (book -> author)."""
    stmt = (
        select(Book)
        .options(joinedload(Book.author))
        .order_by(Book.published_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.unique().scalars().all())  # unique() required with joinedload


async def search_books_with_contains_eager(
    session: AsyncSession, author_name: str
) -> list[Author]:
    """contains_eager — use when you already have the JOIN in your query."""
    stmt = (
        select(Author)
        .join(Author.books)
        .options(contains_eager(Author.books))
        .where(Author.name.ilike(f"%{author_name}%"))
        .order_by(Author.name, Book.published_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.unique().scalars().all())


async def get_books_no_lazy(session: AsyncSession) -> list[Book]:
    """raiseload('*') — prevent ALL implicit lazy loads.
    Forces you to explicitly load what you need."""
    stmt = (
        select(Book)
        .options(
            joinedload(Book.author),     # explicitly load author
            selectinload(Book.tags),     # explicitly load tags
            raiseload("*"),              # error on anything else
        )
    )
    result = await session.execute(stmt)
    return list(result.unique().scalars().all())
```

```python
# ── Pagination with eager loading ─────────────────────────────────

from sqlalchemy import func as sa_func


async def paginated_authors(
    session: AsyncSession,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Paginate authors with book counts — avoids N+1."""
    # Count query (separate for accuracy with LIMIT)
    count_stmt = select(sa_func.count(Author.id))
    total = (await session.execute(count_stmt)).scalar_one()

    # Data query with eager loading
    stmt = (
        select(Author)
        .options(selectinload(Author.books))
        .order_by(Author.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await session.execute(stmt)
    authors = list(result.scalars().all())

    return {
        "items": [
            {
                "id": a.id,
                "name": a.name,
                "book_count": len(a.books),  # no N+1: already loaded
            }
            for a in authors
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


# ── Hybrid approach: subquery for counts ──────────────────────────

from sqlalchemy import literal_column

async def authors_with_book_count(session: AsyncSession) -> list[dict]:
    """Use subquery for counts instead of loading all books."""
    book_count_subq = (
        select(
            Book.author_id,
            sa_func.count(Book.id).label("book_count"),
        )
        .group_by(Book.author_id)
        .subquery()
    )

    stmt = (
        select(
            Author.id,
            Author.name,
            sa_func.coalesce(book_count_subq.c.book_count, 0).label("book_count"),
        )
        .outerjoin(book_count_subq, Author.id == book_count_subq.c.author_id)
        .order_by(Author.name)
    )

    result = await session.execute(stmt)
    return [
        {"id": row.id, "name": row.name, "book_count": row.book_count}
        for row in result.all()
    ]
```

| Strategy | Queries | Best For | Caveats |
|---|---|---|---|
| `selectinload` | N+1 → 2 | Collections (one-to-many) | Extra query per level |
| `subqueryload` | N+1 → 2 | Collections (complex filters) | Full subquery per level |
| `joinedload` | 1 (JOIN) | Many-to-one / small collections | Cartesian explosion risk |
| `contains_eager` | 1 (your JOIN) | When JOIN already in query | Must match your join |
| `lazyload` | N+1 | **Never in async** | `MissingGreenlet` error |
| `raiseload` | 0 (raises) | Preventing accidents | Forces explicit loading |

Key patterns:
1. **Default to `selectinload`** for async -- it avoids cartesian explosion and works with pagination.
2. Use `joinedload` only for many-to-one (e.g., `Book.author`) -- never for large collections.
3. Set `lazy="raise"` on relationships you rarely need to force explicit loading.
4. Always call `.unique()` on results when using `joinedload` with collections.
5. Chain `.selectinload(Parent.children).selectinload(Child.grandchildren)` for deep loading.
6. Use subqueries for aggregates (counts, sums) instead of loading full collections.'''
    ),
    (
        "python/sqlalchemy-hybrid-properties",
        "Show SQLAlchemy 2.0+ hybrid properties and custom query constructs for computed columns that work both in Python and SQL.",
        '''SQLAlchemy 2.0+ hybrid properties and custom query constructs:

```python
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    String, Numeric, DateTime, Integer, ForeignKey,
    case, func, select, type_coerce,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.hybrid import hybrid_property, hybrid_method
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ── Hybrid properties on a User model ────────────────────────────

class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    last_login: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )

    orders: Mapped[list[Order]] = relationship(back_populates="user")

    # ── Simple hybrid: works in Python AND SQL ────────────────

    @hybrid_property
    def full_name(self) -> str:
        """Python: concatenate strings."""
        return f"{self.first_name} {self.last_name}"

    @full_name.inplace.expression
    @classmethod
    def _full_name_expression(cls) -> Any:
        """SQL: use || operator for concatenation."""
        return cls.first_name + " " + cls.last_name

    # ── Hybrid with different logic for Python vs SQL ─────────

    @hybrid_property
    def is_stale(self) -> bool:
        """Python: check if user hasn't logged in for 90 days."""
        if self.last_login is None:
            return True
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        return self.last_login < cutoff

    @is_stale.inplace.expression
    @classmethod
    def _is_stale_expression(cls) -> Any:
        """SQL: use CASE expression for the same logic."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=90)
        return case(
            (cls.last_login.is_(None), True),
            (cls.last_login < cutoff, True),
            else_=False,
        )

    # ── Hybrid method (accepts parameters) ────────────────────

    @hybrid_method
    def has_ordered_in_last(self, days: int) -> bool:
        """Python: check orders list."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return any(o.placed_at >= cutoff for o in self.orders)

    @has_ordered_in_last.expression
    def _has_ordered_in_last_expression(cls, days: int) -> Any:
        """SQL: EXISTS subquery."""
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        return (
            select(Order.id)
            .where(Order.user_id == cls.id)
            .where(Order.placed_at >= cutoff)
            .exists()
        )


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    status: Mapped[str] = mapped_column(String(20), default="pending")

    user: Mapped[User] = relationship(back_populates="orders")
    items: Mapped[list[OrderItem]] = relationship(back_populates="order")

    # ── Hybrid property with aggregation ──────────────────────

    @hybrid_property
    def total(self) -> Decimal:
        """Python: sum line items."""
        return sum(
            (item.quantity * item.unit_price for item in self.items),
            Decimal("0.00"),
        )

    @total.inplace.expression
    @classmethod
    def _total_expression(cls) -> Any:
        """SQL: correlated subquery for sum."""
        return (
            select(
                func.coalesce(
                    func.sum(OrderItem.quantity * OrderItem.unit_price),
                    Decimal("0.00"),
                )
            )
            .where(OrderItem.order_id == cls.id)
            .correlate(cls)
            .scalar_subquery()
        )

    @hybrid_property
    def is_completed(self) -> bool:
        return self.status == "completed"

    @is_completed.inplace.expression
    @classmethod
    def _is_completed_expression(cls) -> Any:
        return cls.status == "completed"


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_name: Mapped[str] = mapped_column(String(200))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))

    order: Mapped[Order] = relationship(back_populates="items")
```

```python
# ── Using hybrid properties in queries ────────────────────────────

async def find_users_by_full_name(
    session: AsyncSession, name: str
) -> list[User]:
    """hybrid_property works in WHERE clauses."""
    stmt = (
        select(User)
        .where(User.full_name.ilike(f"%{name}%"))
        .order_by(User.full_name)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def find_stale_users(session: AsyncSession) -> list[User]:
    """Filter by hybrid property boolean."""
    stmt = select(User).where(User.is_stale == True)  # noqa: E712
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def find_high_value_orders(
    session: AsyncSession, min_total: Decimal
) -> list[Order]:
    """Filter and sort by hybrid with subquery."""
    stmt = (
        select(Order)
        .where(Order.total >= min_total)
        .where(Order.is_completed == True)  # noqa: E712
        .order_by(Order.total.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def find_recent_buyers(
    session: AsyncSession, days: int = 30
) -> list[User]:
    """Use hybrid_method in WHERE clause."""
    stmt = (
        select(User)
        .where(User.has_ordered_in_last(days))
        .where(User.is_active == True)  # noqa: E712
        .order_by(User.full_name)
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
```

```python
# ── Custom SQL constructs and column properties ──────────────────

from sqlalchemy.orm import column_property


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    base_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    tax_rate: Mapped[Decimal] = mapped_column(
        Numeric(5, 4), default=Decimal("0.0800")
    )
    discount_pct: Mapped[Decimal] = mapped_column(
        Numeric(5, 2), default=Decimal("0.00")
    )
    stock_quantity: Mapped[int] = mapped_column(default=0)

    # column_property: computed at query time, part of SELECT
    price_with_tax = column_property(
        base_price * (1 + tax_rate)
    )

    discounted_price = column_property(
        base_price * (1 - discount_pct / 100)
    )

    @hybrid_property
    def in_stock(self) -> bool:
        return self.stock_quantity > 0

    @in_stock.inplace.expression
    @classmethod
    def _in_stock_expression(cls) -> Any:
        return cls.stock_quantity > 0

    @hybrid_property
    def stock_status(self) -> str:
        if self.stock_quantity == 0:
            return "out_of_stock"
        if self.stock_quantity < 10:
            return "low_stock"
        return "in_stock"

    @stock_status.inplace.expression
    @classmethod
    def _stock_status_expression(cls) -> Any:
        return case(
            (cls.stock_quantity == 0, "out_of_stock"),
            (cls.stock_quantity < 10, "low_stock"),
            else_="in_stock",
        )


# Query using column_property and hybrid
async def find_deals(session: AsyncSession) -> list[Product]:
    stmt = (
        select(Product)
        .where(Product.in_stock == True)  # noqa: E712
        .where(Product.discount_pct > 0)
        .order_by(Product.discounted_price.asc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
```

| Feature | Python Side | SQL Side | Use Case |
|---|---|---|---|
| `hybrid_property` | `@property` | `.expression` classmethod | Computed attributes |
| `hybrid_method` | Instance method | `.expression` classmethod | Parameterized queries |
| `column_property` | Auto-loaded column | Inline SQL expression | Simple arithmetic |
| `case()` | N/A | SQL CASE WHEN | Conditional SQL logic |
| Correlated subquery | N/A | `scalar_subquery()` | Aggregates across tables |

Key patterns:
1. `@hybrid_property` gives you one name that works in Python and in SQL `WHERE`/`ORDER BY`.
2. The `.expression` classmethod receives `cls` (the mapped class), not `self`.
3. Use `case()` for multi-branch conditionals in SQL expressions.
4. Correlated subqueries with `.scalar_subquery()` compute aggregates per row.
5. `column_property` is simpler than hybrids but only works for inline SQL math.
6. Always test both Python-side and SQL-side behavior -- they can diverge silently.'''
    ),
    (
        "python/sqlalchemy-event-hooks-audit",
        "Show SQLAlchemy 2.0+ event hooks for audit logging: tracking who changed what, automatic timestamps, and change history tables.",
        '''SQLAlchemy 2.0+ event hooks and audit logging:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from contextvars import ContextVar

from sqlalchemy import (
    String, DateTime, Text, Integer, ForeignKey,
    event, inspect, func, select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship,
    Session, UOWTransaction, InstanceState,
    attributes,
)


# Context var to track current user across async tasks
current_user_var: ContextVar[str] = ContextVar("current_user", default="system")


class Base(DeclarativeBase):
    pass


# ── Audit trail table ────────────────────────────────────────────

class AuditLog(Base):
    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    table_name: Mapped[str] = mapped_column(String(100))
    record_id: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(10))  # INSERT, UPDATE, DELETE
    changes: Mapped[str] = mapped_column(Text)       # JSON of changes
    actor: Mapped[str] = mapped_column(String(100))
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), default=None)


# ── Auditable mixin ──────────────────────────────────────────────

class AuditableMixin:
    """Mixin that marks a model for audit tracking."""
    __audit_fields__: set[str] = set()  # empty = audit all fields
    __audit_exclude__: set[str] = {"updated_at", "created_at"}

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    created_by: Mapped[str] = mapped_column(
        String(100), default=lambda: current_user_var.get()
    )
    updated_by: Mapped[str] = mapped_column(
        String(100), default=lambda: current_user_var.get()
    )


# ── Domain models ────────────────────────────────────────────────

class Customer(AuditableMixin, Base):
    __tablename__ = "customers"
    __audit_exclude__ = {"updated_at", "created_at", "updated_by", "created_by"}

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    tier: Mapped[str] = mapped_column(String(20), default="free")
    credit_limit: Mapped[int] = mapped_column(Integer, default=0)

    orders: Mapped[list[Order]] = relationship(back_populates="customer")


class Order(AuditableMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    status: Mapped[str] = mapped_column(String(20), default="draft")
    total: Mapped[int] = mapped_column(Integer, default=0)

    customer: Mapped[Customer] = relationship(back_populates="orders")
```

```python
# ── Event listeners for audit logging ─────────────────────────────

def get_changes(instance: Any) -> dict[str, Any]:
    """Extract changed fields from a SQLAlchemy instance."""
    insp: InstanceState = inspect(instance)
    changes: dict[str, Any] = {}

    exclude = getattr(instance, "__audit_exclude__", set())
    audit_fields = getattr(instance, "__audit_fields__", set())

    for attr in insp.mapper.column_attrs:
        key = attr.key
        if key in exclude:
            continue
        if audit_fields and key not in audit_fields:
            continue

        history = attributes.get_history(instance, key)
        if history.has_changes():
            old_value = history.deleted[0] if history.deleted else None
            new_value = history.added[0] if history.added else None
            # Convert non-serializable types
            changes[key] = {
                "old": _serialize(old_value),
                "new": _serialize(new_value),
            }

    return changes


def _serialize(value: Any) -> Any:
    """Make value JSON-serializable."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def _get_primary_key(instance: Any) -> str:
    """Get primary key value as string."""
    insp = inspect(instance)
    pk_values = [str(v) for v in insp.mapper.primary_key_from_instance(instance)]
    return ",".join(pk_values)


# ── Register the event hooks ─────────────────────────────────────

@event.listens_for(Session, "before_flush")
def audit_before_flush(
    session: Session,
    flush_context: UOWTransaction,
    instances: Any,
) -> None:
    """Capture changes before flush — works for sync and async."""
    audit_entries: list[AuditLog] = []
    actor = current_user_var.get()

    # New objects
    for instance in session.new:
        if not isinstance(instance, AuditableMixin):
            continue
        if isinstance(instance, AuditLog):
            continue

        audit_entries.append(AuditLog(
            table_name=instance.__tablename__,
            record_id=_get_primary_key(instance) or "new",
            action="INSERT",
            changes=json.dumps(
                {c.key: _serialize(getattr(instance, c.key))
                 for c in inspect(instance).mapper.column_attrs
                 if c.key not in getattr(instance, "__audit_exclude__", set())}
            ),
            actor=actor,
        ))

    # Modified objects
    for instance in session.dirty:
        if not isinstance(instance, AuditableMixin):
            continue
        if not session.is_modified(instance, include_collections=False):
            continue

        changes = get_changes(instance)
        if changes:
            audit_entries.append(AuditLog(
                table_name=instance.__tablename__,
                record_id=_get_primary_key(instance),
                action="UPDATE",
                changes=json.dumps(changes),
                actor=actor,
            ))

    # Deleted objects
    for instance in session.deleted:
        if not isinstance(instance, AuditableMixin):
            continue

        audit_entries.append(AuditLog(
            table_name=instance.__tablename__,
            record_id=_get_primary_key(instance),
            action="DELETE",
            changes=json.dumps({"deleted": True}),
            actor=actor,
        ))

    session.add_all(audit_entries)


# Auto-update updated_by on dirty objects
@event.listens_for(Session, "before_flush")
def update_actor_field(
    session: Session,
    flush_context: UOWTransaction,
    instances: Any,
) -> None:
    actor = current_user_var.get()
    for instance in session.dirty:
        if isinstance(instance, AuditableMixin):
            instance.updated_by = actor
```

```python
# ── FastAPI middleware to set current user ────────────────────────

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware


class AuditMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Extract user from JWT or session
        user = "anonymous"
        auth_header = request.headers.get("authorization", "")
        if auth_header.startswith("Bearer "):
            # In real code: decode JWT here
            user = request.headers.get("x-user-id", "anonymous")

        token = current_user_var.set(user)
        try:
            response = await call_next(request)
            return response
        finally:
            current_user_var.reset(token)


app = FastAPI()
app.add_middleware(AuditMiddleware)


# ── Query audit log ──────────────────────────────────────────────

async def get_audit_trail(
    session: AsyncSession,
    table_name: str,
    record_id: str,
) -> list[dict[str, Any]]:
    """Get full audit history for a record."""
    stmt = (
        select(AuditLog)
        .where(AuditLog.table_name == table_name)
        .where(AuditLog.record_id == record_id)
        .order_by(AuditLog.timestamp.desc())
    )
    result = await session.execute(stmt)
    return [
        {
            "action": log.action,
            "changes": json.loads(log.changes),
            "actor": log.actor,
            "timestamp": log.timestamp.isoformat(),
        }
        for log in result.scalars().all()
    ]


# ── Connection-level events ──────────────────────────────────────

from sqlalchemy import Engine


@event.listens_for(Engine, "before_cursor_execute")
def log_slow_queries(
    conn: Any,
    cursor: Any,
    statement: str,
    parameters: Any,
    context: Any,
    executemany: bool,
) -> None:
    import time
    conn.info.setdefault("query_start_time", []).append(time.monotonic())


@event.listens_for(Engine, "after_cursor_execute")
def check_slow_queries(
    conn: Any,
    cursor: Any,
    statement: str,
    parameters: Any,
    context: Any,
    executemany: bool,
) -> None:
    import time
    import logging
    total = time.monotonic() - conn.info["query_start_time"].pop()
    if total > 0.5:  # 500ms threshold
        logging.warning(
            "Slow query (%.2fs): %s", total, statement[:200]
        )
```

| Event | When | Use Case |
|---|---|---|
| `before_flush` | Before SQL emitted | Audit logging, auto-fill fields |
| `after_flush` | After SQL committed to DB | Post-commit hooks |
| `before_cursor_execute` | Before each SQL query | Query timing, logging |
| `after_cursor_execute` | After each SQL query | Slow query detection |
| `before_insert` | Before INSERT (mapper) | Auto-generate values |
| `before_update` | Before UPDATE (mapper) | Validate state transitions |
| `load` | After object loaded from DB | Post-load processing |

Key patterns:
1. Use `ContextVar` to propagate the current user through async request handlers.
2. `before_flush` event catches INSERT, UPDATE, and DELETE in one listener.
3. `attributes.get_history()` reveals old and new values for change tracking.
4. Exclude audit fields themselves (`created_at`, `updated_at`) from the audit log.
5. Add `AuditLog` entries to the same session so they commit atomically.
6. Connection-level events for slow query logging work across all models.'''
    ),
    (
        "python/sqlalchemy-multi-tenancy",
        "Show SQLAlchemy 2.0+ multi-tenancy with schema-per-tenant: dynamic schema switching, tenant-aware sessions, and migration strategies.",
        '''SQLAlchemy 2.0+ multi-tenancy with schema-per-tenant:

```python
from __future__ import annotations

from contextvars import ContextVar
from typing import Any, AsyncGenerator

from sqlalchemy import MetaData, String, Integer, event, text, DDL
from sqlalchemy.ext.asyncio import (
    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


# ── Tenant context ───────────────────────────────────────────────

current_tenant: ContextVar[str] = ContextVar("current_tenant", default="public")


# ── Base with dynamic schema ─────────────────────────────────────

class TenantBase(DeclarativeBase):
    """Base class that uses tenant schema for all tables."""
    metadata = MetaData()


class TenantUser(TenantBase):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(200), unique=True)
    role: Mapped[str] = mapped_column(String(20), default="member")


class TenantProject(TenantBase):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(String(2000), default="")


# ── Shared / public schema models ────────────────────────────────

class SharedBase(DeclarativeBase):
    metadata = MetaData(schema="public")


class Tenant(SharedBase):
    __tablename__ = "tenants"

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(50), unique=True)
    name: Mapped[str] = mapped_column(String(200))
    schema_name: Mapped[str] = mapped_column(String(63), unique=True)
    is_active: Mapped[bool] = mapped_column(default=True)


class TenantPlan(SharedBase):
    __tablename__ = "tenant_plans"

    id: Mapped[int] = mapped_column(primary_key=True)
    tenant_id: Mapped[int] = mapped_column(Integer)
    plan_name: Mapped[str] = mapped_column(String(50))
    max_users: Mapped[int] = mapped_column(Integer, default=10)


# ── Tenant-aware engine and session management ───────────────────

class MultiTenantDB:
    """Manages schema-per-tenant database access."""

    def __init__(self, database_url: str) -> None:
        self._engine = create_async_engine(
            database_url,
            pool_size=20,
            max_overflow=30,
            pool_pre_ping=True,
        )
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    async def tenant_session(
        self, tenant_schema: str
    ) -> AsyncGenerator[AsyncSession, None]:
        """Create session scoped to a tenant schema."""
        session = self._session_factory()
        try:
            # Set search_path to tenant schema
            await session.execute(
                text(f"SET search_path TO {tenant_schema}, public")
            )
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            # Reset search_path
            await session.execute(text("SET search_path TO public"))
            await session.close()

    async def create_tenant_schema(self, schema_name: str) -> None:
        """Create a new tenant schema with all tables."""
        async with self._engine.begin() as conn:
            # Create schema
            await conn.execute(text(f"CREATE SCHEMA IF NOT EXISTS {schema_name}"))
            # Set search_path for table creation
            await conn.execute(
                text(f"SET search_path TO {schema_name}")
            )
            # Create all tenant tables in the new schema
            await conn.run_sync(TenantBase.metadata.create_all)
            # Reset
            await conn.execute(text("SET search_path TO public"))

    async def drop_tenant_schema(self, schema_name: str) -> None:
        """Drop a tenant schema (careful!)."""
        async with self._engine.begin() as conn:
            await conn.execute(
                text(f"DROP SCHEMA IF EXISTS {schema_name} CASCADE")
            )

    async def close(self) -> None:
        await self._engine.dispose()
```

```python
# ── FastAPI integration ───────────────────────────────────────────

from fastapi import Depends, FastAPI, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware
from sqlalchemy import select


db = MultiTenantDB("postgresql+asyncpg://user:pass@localhost:5432/saas")

app = FastAPI()


class TenantMiddleware(BaseHTTPMiddleware):
    """Extract tenant from subdomain or header."""

    async def dispatch(self, request: Request, call_next):
        # Strategy 1: subdomain (acme.myapp.com)
        host = request.headers.get("host", "")
        parts = host.split(".")
        if len(parts) >= 3:
            tenant_slug = parts[0]
        else:
            # Strategy 2: header
            tenant_slug = request.headers.get("x-tenant-id", "")

        if not tenant_slug:
            return await call_next(request)

        # Look up tenant schema
        async with db.engine.connect() as conn:
            await conn.execute(text("SET search_path TO public"))
            result = await conn.execute(
                select(Tenant).where(
                    Tenant.slug == tenant_slug,
                    Tenant.is_active == True,  # noqa: E712
                )
            )
            tenant = result.first()

        if not tenant:
            from starlette.responses import JSONResponse
            return JSONResponse(
                status_code=404,
                content={"error": f"Tenant '{tenant_slug}' not found"},
            )

        # Store in request state and context var
        request.state.tenant_schema = tenant.schema_name
        token = current_tenant.set(tenant.schema_name)

        try:
            response = await call_next(request)
            return response
        finally:
            current_tenant.reset(token)


app.add_middleware(TenantMiddleware)


async def get_tenant_session(
    request: Request,
) -> AsyncGenerator[AsyncSession, None]:
    """Dependency: get session scoped to the current tenant."""
    schema = getattr(request.state, "tenant_schema", None)
    if not schema:
        raise HTTPException(400, "No tenant context")
    async for session in db.tenant_session(schema):
        yield session


@app.get("/users")
async def list_users(
    session: AsyncSession = Depends(get_tenant_session),
):
    result = await session.execute(select(TenantUser))
    users = result.scalars().all()
    return [{"id": u.id, "name": u.name, "email": u.email} for u in users]
```

```python
# ── Tenant provisioning and migration ─────────────────────────────

from sqlalchemy import select


async def provision_tenant(
    db: MultiTenantDB,
    slug: str,
    name: str,
    admin_email: str,
) -> Tenant:
    """Full tenant provisioning workflow."""
    schema_name = f"tenant_{slug}"

    # 1. Create schema with tables
    await db.create_tenant_schema(schema_name)

    # 2. Register in shared tenants table
    async with db.engine.begin() as conn:
        await conn.execute(text("SET search_path TO public"))
        result = await conn.execute(
            text("""
                INSERT INTO tenants (slug, name, schema_name, is_active)
                VALUES (:slug, :name, :schema_name, true)
                RETURNING id
            """),
            {"slug": slug, "name": name, "schema_name": schema_name},
        )
        tenant_id = result.scalar_one()

    # 3. Create admin user in tenant schema
    async for session in db.tenant_session(schema_name):
        admin = TenantUser(
            name="Admin",
            email=admin_email,
            role="admin",
        )
        session.add(admin)

    return Tenant(
        id=tenant_id, slug=slug, name=name,
        schema_name=schema_name, is_active=True,
    )


# ── Alembic multi-tenant migration ───────────────────────────────

# alembic/env.py additions:
MIGRATION_CODE = '''
import asyncio
from alembic import context
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

# Run migration for each tenant schema
async def run_tenant_migrations():
    engine = create_async_engine(config.get_main_option("sqlalchemy.url"))

    async with engine.connect() as conn:
        # Get all tenant schemas
        result = await conn.execute(
            text("SELECT schema_name FROM public.tenants WHERE is_active = true")
        )
        schemas = [row[0] for row in result.fetchall()]

    for schema in schemas:
        print(f"Migrating schema: {schema}")
        async with engine.begin() as conn:
            await conn.execute(text(f"SET search_path TO {schema}"))
            await conn.run_sync(do_run_migrations)
            await conn.execute(text("SET search_path TO public"))

    await engine.dispose()
'''


# ── Testing multi-tenancy ────────────────────────────────────────

import pytest
import pytest_asyncio


@pytest_asyncio.fixture
async def tenant_db() -> AsyncGenerator[MultiTenantDB, None]:
    db = MultiTenantDB("postgresql+asyncpg://user:pass@localhost:5432/test_saas")
    async with db.engine.begin() as conn:
        await conn.run_sync(SharedBase.metadata.create_all)
    yield db
    # Cleanup all test schemas
    async with db.engine.begin() as conn:
        result = await conn.execute(
            text("SELECT schema_name FROM public.tenants")
        )
        for row in result.fetchall():
            await conn.execute(text(f"DROP SCHEMA IF EXISTS {row[0]} CASCADE"))
        await conn.run_sync(SharedBase.metadata.drop_all)
    await db.close()


@pytest.mark.asyncio
async def test_tenant_isolation(tenant_db: MultiTenantDB) -> None:
    # Create two tenants
    t1 = await provision_tenant(tenant_db, "acme", "Acme Corp", "admin@acme.com")
    t2 = await provision_tenant(tenant_db, "globex", "Globex Inc", "admin@globex.com")

    # Add user to tenant 1
    async for session in tenant_db.tenant_session(t1.schema_name):
        session.add(TenantUser(name="Alice", email="alice@acme.com"))

    # Verify tenant 2 cannot see tenant 1 users
    async for session in tenant_db.tenant_session(t2.schema_name):
        result = await session.execute(
            select(TenantUser).where(TenantUser.email == "alice@acme.com")
        )
        assert result.scalar_one_or_none() is None  # isolated!
```

| Strategy | Isolation | Complexity | Scaling | Use Case |
|---|---|---|---|---|
| Schema-per-tenant | Strong | Medium | Moderate (thousands) | SaaS with compliance needs |
| Row-level (tenant_id) | Weak | Low | High (millions) | Simple multi-tenant apps |
| Database-per-tenant | Strongest | High | Limited (hundreds) | Regulated industries |
| Hybrid (shared + schema) | Medium | Medium | Good | Common pragmatic choice |

Key patterns:
1. Use PostgreSQL `SET search_path TO tenant_schema, public` for schema isolation.
2. Shared tables (tenants, plans) live in `public` schema.
3. `ContextVar` propagates tenant context through async middleware.
4. Provision flow: create schema, register tenant, seed initial data -- all in one transaction.
5. Run Alembic migrations per-schema by iterating active tenants.
6. Always reset `search_path` to `public` in `finally` blocks to prevent cross-tenant leaks.'''
    ),
]
"""
