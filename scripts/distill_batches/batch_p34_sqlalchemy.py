"""SQLAlchemy — ORM patterns, relationships, queries, and migrations."""

PAIRS = [
    (
        "python/sqlalchemy-models",
        "Show SQLAlchemy 2.0 model patterns: declarative models, relationships, mixins, and hybrid properties.",
        '''SQLAlchemy 2.0 modern model patterns:

```python
from sqlalchemy import (
    String, Integer, Float, Boolean, DateTime, ForeignKey,
    Text, Index, UniqueConstraint, CheckConstraint,
    func, select, and_, or_,
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship,
    declared_attr, validates, Session,
)
from sqlalchemy.ext.hybrid import hybrid_property
from datetime import datetime, timezone
from typing import Optional
import re

# --- Base with common mixins ---

class Base(DeclarativeBase):
    pass

class TimestampMixin:
    """Add created_at and updated_at to any model."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

class SoftDeleteMixin:
    """Soft delete support."""
    deleted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), default=None
    )

    @hybrid_property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self):
        self.deleted_at = datetime.now(timezone.utc)


# --- User model ---

class User(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(default=True)

    # Relationships
    orders: Mapped[list["Order"]] = relationship(
        back_populates="user", lazy="selectin",
        order_by="Order.created_at.desc()",
    )
    profile: Mapped[Optional["UserProfile"]] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan",
    )
    roles: Mapped[list["Role"]] = relationship(
        secondary="user_roles", back_populates="users",
    )

    # Validation
    @validates("email")
    def validate_email(self, key, value):
        if not re.match(r"^[^@]+@[^@]+\\.[^@]+$", value):
            raise ValueError(f"Invalid email: {value}")
        return value.lower()

    # Hybrid property (works in Python AND SQL)
    @hybrid_property
    def order_count(self) -> int:
        return len(self.orders)

    @order_count.expression
    def order_count(cls):
        return (
            select(func.count(Order.id))
            .where(Order.user_id == cls.id)
            .correlate(cls)
            .scalar_subquery()
        )

    # Table-level constraints
    __table_args__ = (
        Index("ix_users_email_active", "email", "is_active"),
        CheckConstraint("length(name) >= 2", name="ck_users_name_length"),
    )


# --- Order with items ---

class Order(TimestampMixin, Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    status: Mapped[str] = mapped_column(
        String(20), default="pending",
    )
    notes: Mapped[Optional[str]] = mapped_column(Text)

    user: Mapped["User"] = relationship(back_populates="orders")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan",
    )

    @hybrid_property
    def total(self) -> float:
        return sum(item.subtotal for item in self.items)

    @total.expression
    def total(cls):
        return (
            select(func.coalesce(func.sum(
                OrderItem.price * OrderItem.quantity
            ), 0))
            .where(OrderItem.order_id == cls.id)
            .correlate(cls)
            .scalar_subquery()
        )

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'confirmed', 'shipped', 'delivered', 'cancelled')",
            name="ck_orders_status",
        ),
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"))
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"))
    quantity: Mapped[int] = mapped_column(default=1)
    price: Mapped[float] = mapped_column(Float)

    order: Mapped["Order"] = relationship(back_populates="items")
    product: Mapped["Product"] = relationship()

    @hybrid_property
    def subtotal(self) -> float:
        return self.price * self.quantity

    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_order_items_qty"),
        CheckConstraint("price >= 0", name="ck_order_items_price"),
    )


# --- Many-to-many with association table ---

from sqlalchemy import Table, Column

user_roles = Table(
    "user_roles", Base.metadata,
    Column("user_id", ForeignKey("users.id"), primary_key=True),
    Column("role_id", ForeignKey("roles.id"), primary_key=True),
)

class Role(Base):
    __tablename__ = "roles"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(50), unique=True)
    users: Mapped[list["User"]] = relationship(
        secondary=user_roles, back_populates="roles",
    )
```

Key patterns:
1. **Mapped columns** — `Mapped[type]` with `mapped_column()` (SQLAlchemy 2.0 style)
2. **Mixins** — reusable timestamp, soft-delete across models
3. **Hybrid properties** — same logic works in Python and SQL queries
4. **Relationship loading** — `lazy="selectin"` for N+1 prevention
5. **Validation** — `@validates` for domain rules on assignment'''
    ),
    (
        "python/sqlalchemy-queries",
        "Show SQLAlchemy 2.0 query patterns: select, join, subquery, window functions, CTEs, and bulk operations.",
        '''SQLAlchemy 2.0 query patterns:

```python
from sqlalchemy import select, func, and_, or_, case, text, update, delete
from sqlalchemy.orm import selectinload, joinedload, subqueryload
from sqlalchemy.ext.asyncio import AsyncSession

class UserRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    # --- Basic queries ---

    async def get_by_id(self, user_id: int) -> User | None:
        return await self.session.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # --- Eager loading (prevent N+1) ---

    async def get_with_orders(self, user_id: int) -> User | None:
        stmt = (
            select(User)
            .options(
                selectinload(User.orders).selectinload(Order.items),
                selectinload(User.roles),
            )
            .where(User.id == user_id)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    # --- Filtering and pagination ---

    async def search(
        self, query: str = None, is_active: bool = None,
        role: str = None, page: int = 1, size: int = 20,
    ) -> tuple[list[User], int]:
        stmt = select(User).where(User.deleted_at.is_(None))
        count_stmt = select(func.count()).select_from(User).where(
            User.deleted_at.is_(None)
        )

        if query:
            pattern = f"%{query}%"
            filter_clause = or_(
                User.name.ilike(pattern),
                User.email.ilike(pattern),
            )
            stmt = stmt.where(filter_clause)
            count_stmt = count_stmt.where(filter_clause)

        if is_active is not None:
            stmt = stmt.where(User.is_active == is_active)
            count_stmt = count_stmt.where(User.is_active == is_active)

        if role:
            stmt = stmt.join(User.roles).where(Role.name == role)
            count_stmt = count_stmt.join(User.roles).where(Role.name == role)

        # Get total count
        total = (await self.session.execute(count_stmt)).scalar()

        # Get page
        stmt = stmt.order_by(User.created_at.desc())
        stmt = stmt.offset((page - 1) * size).limit(size)
        result = await self.session.execute(stmt)
        users = list(result.scalars().all())

        return users, total

    # --- Aggregation ---

    async def get_user_stats(self) -> dict:
        stmt = select(
            func.count(User.id).label("total_users"),
            func.count(User.id).filter(User.is_active).label("active_users"),
            func.avg(User.order_count).label("avg_orders"),
        )
        result = (await self.session.execute(stmt)).one()
        return {
            "total": result.total_users,
            "active": result.active_users,
            "avg_orders": float(result.avg_orders or 0),
        }

    # --- Window functions ---

    async def get_users_ranked_by_spending(self) -> list[dict]:
        spending = (
            select(
                User.id,
                User.name,
                func.coalesce(func.sum(Order.total), 0).label("total_spent"),
                func.rank().over(
                    order_by=func.sum(Order.total).desc()
                ).label("rank"),
            )
            .outerjoin(Order, User.id == Order.user_id)
            .group_by(User.id, User.name)
        )
        result = await self.session.execute(spending)
        return [dict(row._mapping) for row in result.all()]

    # --- CTE (Common Table Expression) ---

    async def get_top_customers(self, min_orders: int = 5) -> list:
        customer_stats = (
            select(
                User.id.label("user_id"),
                func.count(Order.id).label("order_count"),
                func.sum(Order.total).label("total_spent"),
            )
            .join(Order, User.id == Order.user_id)
            .where(Order.status != "cancelled")
            .group_by(User.id)
            .having(func.count(Order.id) >= min_orders)
            .cte("customer_stats")
        )

        stmt = (
            select(User, customer_stats.c.order_count,
                   customer_stats.c.total_spent)
            .join(customer_stats, User.id == customer_stats.c.user_id)
            .order_by(customer_stats.c.total_spent.desc())
            .limit(10)
        )
        return (await self.session.execute(stmt)).all()

    # --- Bulk operations ---

    async def bulk_deactivate(self, user_ids: list[int]):
        stmt = (
            update(User)
            .where(User.id.in_(user_ids))
            .values(is_active=False, updated_at=func.now())
        )
        await self.session.execute(stmt)

    async def bulk_create(self, users_data: list[dict]):
        users = [User(**data) for data in users_data]
        self.session.add_all(users)
        await self.session.flush()  # Get IDs without committing
        return users

    # --- Conditional update ---

    async def update_status_conditional(self, order_id: int,
                                         new_status: str) -> bool:
        valid_transitions = {
            "pending": ["confirmed", "cancelled"],
            "confirmed": ["processing", "cancelled"],
            "processing": ["shipped"],
            "shipped": ["delivered"],
        }

        stmt = (
            update(Order)
            .where(
                Order.id == order_id,
                Order.status.in_(
                    [k for k, v in valid_transitions.items()
                     if new_status in v]
                ),
            )
            .values(status=new_status)
        )
        result = await self.session.execute(stmt)
        return result.rowcount > 0
```

Key patterns:
1. **2.0 style** — `select()` instead of `session.query()`
2. **Eager loading** — `selectinload` for collections, `joinedload` for single
3. **Window functions** — ranking, running totals without subqueries
4. **CTEs** — readable complex queries with `.cte()`
5. **Bulk operations** — `update()` and `delete()` bypass ORM for performance'''
    ),
    (
        "python/alembic-migrations",
        "Show Alembic migration patterns: auto-generation, data migrations, reversible operations, and branching strategies.",
        '''Alembic migration patterns for production:

```python
# --- alembic/env.py configuration ---

from alembic import context
from sqlalchemy import engine_from_config, pool
from app.models import Base  # Import all models

target_metadata = Base.metadata

def run_migrations_online():
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,           # Detect column type changes
            compare_server_default=True, # Detect default changes
            render_as_batch=True,        # SQLite batch mode
        )
        with context.begin_transaction():
            context.run_migrations()


# --- Schema migration (auto-generated) ---
# alembic revision --autogenerate -m "add user preferences"

"""add user preferences

Revision ID: abc123
"""
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"),
                  nullable=False, unique=True),
        sa.Column("theme", sa.String(20), server_default="light"),
        sa.Column("language", sa.String(10), server_default="en"),
        sa.Column("notifications", sa.Boolean(), server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now()),
    )
    op.create_index("ix_user_prefs_user", "user_preferences", ["user_id"])

def downgrade():
    op.drop_index("ix_user_prefs_user")
    op.drop_table("user_preferences")


# --- Data migration ---
# alembic revision -m "backfill user display names"

"""backfill user display names"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import Session

def upgrade():
    # Add column (nullable first)
    op.add_column("users",
        sa.Column("display_name", sa.String(100), nullable=True))

    # Backfill data
    bind = op.get_bind()
    session = Session(bind=bind)
    session.execute(
        sa.text("UPDATE users SET display_name = name WHERE display_name IS NULL")
    )
    session.commit()

    # Now make non-nullable
    op.alter_column("users", "display_name", nullable=False)

def downgrade():
    op.drop_column("users", "display_name")


# --- Expand-contract migration (zero-downtime) ---

# Step 1: Expand (add new, keep old)
"""add email_verified column"""

def upgrade():
    # Add as nullable with default
    op.add_column("users",
        sa.Column("email_verified", sa.Boolean(), server_default=sa.false()))
    # Backfill
    op.execute("UPDATE users SET email_verified = true WHERE confirmed_at IS NOT NULL")

def downgrade():
    op.drop_column("users", "email_verified")


# Step 2: Contract (after all code uses new column)
"""remove legacy confirmed_at column"""

def upgrade():
    op.drop_column("users", "confirmed_at")

def downgrade():
    op.add_column("users",
        sa.Column("confirmed_at", sa.DateTime(timezone=True)))
```

```bash
# Common Alembic commands
alembic revision --autogenerate -m "description"  # Generate from models
alembic upgrade head                               # Apply all migrations
alembic downgrade -1                               # Rollback one step
alembic history                                    # Show migration history
alembic current                                    # Show current revision
alembic stamp head                                 # Mark DB as current
alembic branches                                   # Show migration branches
alembic merge -m "merge" rev1 rev2                 # Merge branches
```

Best practices:
1. **Always reversible** — every `upgrade()` has a working `downgrade()`
2. **Expand-contract** — add new → migrate data → remove old (zero downtime)
3. **Data + schema separate** — don't mix data backfills with schema changes
4. **Test migrations** — run upgrade then downgrade in CI
5. **Review autogenerated** — autogenerate is a starting point, always review'''
    ),
]
