"""SQLAlchemy 2.0+ async patterns -- engine management, relationship loading, hybrid properties, events, multi-tenancy."""

PAIRS = [
    (
        "python/sqlalchemy-async-engine-session",
        "Show SQLAlchemy 2.0+ async engine and session management with proper lifecycle, connection pooling, and dependency injection for FastAPI.",
        '''from __future__ import annotations

import contextlib
from typing import AsyncGenerator, Any

from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,'''
    ),
    (
        "statement_timeout",
        "} } )",
        '''class DatabaseManager:
    """Manages async engine lifecycle and session creation."""

    def __init__(self, database_url: str, echo: bool = False) -> None:
        self._engine = create_engine(database_url, echo=echo)
        self._session_factory = async_sessionmaker(
            self._engine,
            class_=AsyncSession,
            expire_on_commit=False,  # prevent lazy loads after commit
            autoflush=False,         # explicit flush control'''
    ),
    (
        "error",
        "}",
        '''import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine


@pytest_asyncio.fixture
async def test_db() -> AsyncGenerator[DatabaseManager, None]:
    """In-memory SQLite for fast tests."""
    manager = DatabaseManager(
        "sqlite+aiosqlite:///:memory:",
        echo=True,'''
    ),
    (
        "python/sqlalchemy-async-relationship-loading",
        "Show SQLAlchemy 2.0+ relationship loading strategies: selectin, subquery, joined, lazy raise, and how to avoid N+1 queries in async code.",
        '''from __future__ import annotations

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
    lazyload,'''
    ),
    (
        "book_tags",
        "Column('book_id', Integer, ForeignKey('books.id'), primary_key=True) Column('tag_id', Integer, ForeignKey('tags.id'), primary_key=True) )",
        '''```python
# ── Loading strategy examples ─────────────────────────────────────

async def get_authors_with_books(session: AsyncSession) -> list[Author]:
    """selectinload -- 2 queries: one for authors, one for books.
    Best for async because it avoids JOIN explosion."""
    stmt = (
        select(Author)
        .options(selectinload(Author.books))
        .order_by(Author.name)'''
    ),
    (
        "page_size",
        "}",
        '''from sqlalchemy import literal_column

async def authors_with_book_count(session: AsyncSession) -> list[dict]:
    """Use subquery for counts instead of loading all books."""
    book_count_subq = (
        select(
            Book.author_id,
            sa_func.count(Book.id).label("book_count"),'''
    ),
    (
        "python/sqlalchemy-hybrid-properties",
        "Show SQLAlchemy 2.0+ hybrid properties and custom query constructs for computed columns that work both in Python and SQL.",
        '''from __future__ import annotations

from datetime import datetime, timezone, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    String, Numeric, DateTime, Integer, ForeignKey,
    case, func, select, type_coerce,'''
    ),
    (
        "python/sqlalchemy-event-hooks-audit",
        "Show SQLAlchemy 2.0+ event hooks for audit logging: tracking who changed what, automatic timestamps, and change history tables.",
        '''from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional
from contextvars import ContextVar

from sqlalchemy import (
    String, DateTime, Text, Integer, ForeignKey,
    event, inspect, func, select,'''
    ),
    (
        "new",
        "} return changes def _serialize(value: Any) -> Any:",
        '''return None
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
    """Capture changes before flush -- works for sync and async."""
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
                 if c.key not in getattr(instance, "__audit_exclude__", set())}'''
    ),
    (
        "timestamp",
        "} for log in result.scalars().all() ]",
        '''from sqlalchemy import Engine


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
            "Slow query (%.2fs): %s", total, statement[:200]'''
    ),
    (
        "python/sqlalchemy-multi-tenancy",
        "Show SQLAlchemy 2.0+ multi-tenancy with schema-per-tenant: dynamic schema switching, tenant-aware sessions, and migration strategies.",
        '''from __future__ import annotations

from contextvars import ContextVar
from typing import Any, AsyncGenerator

from sqlalchemy import MetaData, String, Integer, event, text, DDL
from sqlalchemy.ext.asyncio import (
    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine,'''
    ),
]
