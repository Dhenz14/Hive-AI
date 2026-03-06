"""Thinking-trace pairs: database problems from real users."""

PAIRS = [
    (
        "thinking/practical",
        r'''this query used to be fast but now it takes 30 seconds

SELECT o.id, o.created_at, o.total, u.email, u.name
FROM orders o
JOIN users u ON u.id = o.user_id
WHERE o.status = 'pending'
AND o.created_at > '2024-01-01'
ORDER BY o.created_at DESC
LIMIT 50;

EXPLAIN ANALYZE output:
Limit (cost=45892.31..45892.44 rows=50 width=120) (actual time=29874.231..29874.298 rows=50 loops=1)
  -> Sort (cost=45892.31..46142.31 rows=100000 width=120) (actual time=29874.229..29874.261 rows=50 loops=1)
        Sort Key: o.created_at DESC
        Sort Method: top-N heapsort Memory: 35kB
        -> Hash Join (cost=1234.56..42567.89 rows=100000 width=120) (actual time=234.567..29654.123 rows=487923 loops=1)
              Hash Cond: (o.user_id = u.id)
              -> Seq Scan on orders o (cost=0.00..38765.43 rows=100000 width=80) (actual time=0.023..28876.543 rows=487923 loops=1)
                    Filter: ((status = 'pending') AND (created_at > '2024-01-01'))
                    Rows Removed by Filter: 2312077
              -> Hash (cost=987.65..987.65 rows=50000 width=44) (actual time=123.456..123.456 rows=50000 loops=1)
                    Buckets: 65536 Memory Usage: 3456kB
                    -> Seq Scan on users u (cost=0.00..987.65 rows=50000 width=44) (actual time=0.012..78.234 rows=50000 loops=1)
Planning Time: 0.234 ms
Execution Time: 29875.456 ms''',
        r'''<think>
Let me read this EXPLAIN ANALYZE output carefully. The total execution time is ~30 seconds. Where is the time going?

Looking at the plan from bottom to top:
1. Seq Scan on users: 78ms for 50k rows -- fine, small table
2. Seq Scan on orders: 28,876ms for filtering 2.8M rows down to 487,923 -- THIS IS THE PROBLEM
3. Hash Join: fast once data is available
4. Sort: fast (top-N heapsort, only needs to find top 50)

So 28.8 seconds out of 30 is spent on the sequential scan of orders. My first thought was "just add an index on status" -- but wait, let me think more carefully.

The orders table has ~2.8 million rows. The sequential scan is reading ALL of them and filtering by status='pending' AND created_at > '2024-01-01'. This returns 487,923 rows -- that is a LOT of pending orders. It used to be fast probably because the table was smaller, or there were fewer pending orders. Actually, hmm, could it also be table bloat from dead tuples? Possibly, but the EXPLAIN ANALYZE shows the filter returning 487k rows, so the index issue is clearly the primary bottleneck.

Key observations:
- There is no index on (status, created_at) for the orders table
- Even if there were an index on status alone, 'pending' matches 487k rows which is ~17% of the table -- PostgreSQL might skip the index anyway because at that selectivity a seq scan can be cheaper than random I/O from an index scan
- The query sorts by created_at DESC and limits to 50, but without an appropriate index, it has to find ALL matching rows first, then sort them just to keep 50

I initially considered just adding an index on (status, created_at), but actually there is a better approach: a composite index on (status, created_at DESC) would let PostgreSQL do an index scan that finds the 50 most recent pending orders directly, without scanning the whole table. The DESC matters because the query sorts by created_at DESC -- the index ordering must match the query ordering.

Even better: a partial index WHERE status = 'pending' since that is the specific filter. This makes the index smaller and faster because it excludes the millions of completed/cancelled orders.

I should also mention: 487k pending orders seems like a lot. Wait -- is there a business logic issue here? Orders should transition from pending to completed or cancelled. If they are accumulating indefinitely, there might be a bug in the order processing pipeline.
</think>

The problem is clear from your EXPLAIN output: the `Seq Scan on orders` is reading **2.8 million rows** to find 487,923 matching ones. There is no index to support your WHERE clause. Here is the fix.

**The root cause:**

```
Seq Scan on orders o ... (actual time=0.023..28876.543 rows=487923 loops=1)
    Filter: ((status = 'pending') AND (created_at > '2024-01-01'))
    Rows Removed by Filter: 2312077
```

PostgreSQL is doing a full table scan of ~2.8M rows, checking every single row against your filter. As the table grew, this got slower linearly.

**Fix 1 (immediate): Add a composite index**

```sql
-- This index covers your exact query pattern: filter by status + date range + sort
CREATE INDEX CONCURRENTLY idx_orders_status_created
ON orders (status, created_at DESC);

-- CONCURRENTLY means it won't lock the table (safe for production)
-- Takes a few minutes to build on 2.8M rows but does not block reads or writes
```

This lets PostgreSQL do an **index scan** that walks the B-tree from `status='pending'` with the most recent `created_at` first, stopping after 50 rows. It never needs to read the other 487,873 matching rows.

**Fix 2 (even better): Partial index for the specific status**

```sql
-- If you mostly query for 'pending' orders, a partial index is smaller and faster
CREATE INDEX CONCURRENTLY idx_orders_pending_created
ON orders (created_at DESC)
WHERE status = 'pending';
```

This index only contains the ~487k pending rows instead of all 2.8M. It is smaller, fits in memory better, and is faster to scan. PostgreSQL will use it for any query that has `WHERE status = 'pending'` in the filter.

**Fix 3 (include columns to avoid table lookups):**

```sql
-- INCLUDE the columns referenced in SELECT to make this an index-only scan
CREATE INDEX CONCURRENTLY idx_orders_pending_created_covering
ON orders (created_at DESC)
INCLUDE (id, total, user_id)
WHERE status = 'pending';
```

With this covering index, PostgreSQL can satisfy the query entirely from the index without fetching rows from the table heap. This is the fastest possible approach.

**Expected result after indexing:**

```sql
-- Run EXPLAIN ANALYZE again after creating the index:
EXPLAIN ANALYZE
SELECT o.id, o.created_at, o.total, u.email, u.name
FROM orders o
JOIN users u ON u.id = o.user_id
WHERE o.status = 'pending'
AND o.created_at > '2024-01-01'
ORDER BY o.created_at DESC
LIMIT 50;

-- Expected plan (approximate):
-- Limit (rows=50)
--   -> Nested Loop (rows=50)
--         -> Index Scan using idx_orders_pending_created_covering on orders o (rows=50)
--               Index Cond: (created_at > '2024-01-01')
--         -> Index Scan using users_pkey on users u (rows=1)
--               Index Cond: (id = o.user_id)
-- Execution Time: ~2ms
```

The query goes from scanning 2.8M rows to reading exactly 50 index entries. From 30 seconds to under 5 milliseconds.

**Side note on your data:** 487,923 pending orders is a lot. If orders are supposed to transition out of 'pending' status (to 'shipped', 'cancelled', etc.), you might have a business logic issue where orders are getting stuck. Worth investigating -- fixing that would also make this query faster by reducing the number of matching rows.

**Monitoring to prevent this from happening again:**

```sql
-- Find slow queries (PostgreSQL pg_stat_statements extension)
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Check for missing indexes -- look for sequential scans on large tables
SELECT schemaname, relname, seq_scan, seq_tup_read,
       idx_scan, idx_tup_fetch,
       seq_tup_read / GREATEST(seq_scan, 1) AS avg_rows_per_scan
FROM pg_stat_user_tables
WHERE seq_scan > 100
AND seq_tup_read > 100000
ORDER BY seq_tup_read DESC
LIMIT 20;

-- Check for unused indexes (clean up waste)
SELECT indexrelname, idx_scan, pg_size_pretty(pg_relation_size(indexrelid))
FROM pg_stat_user_indexes
WHERE idx_scan = 0
AND indexrelname NOT LIKE 'pg_%'
ORDER BY pg_relation_size(indexrelid) DESC;
```'''
    ),
    (
        "thinking/practical",
        r'''I need to add full-text search to our product catalog''',
        r'''<think>
The user wants full-text search for a product catalog. They have not told me:
- Database they use (probably PostgreSQL since it is the most common)
- How many products (hundreds? millions?)
- What search features they need (fuzzy matching? faceted search? autocomplete?)
- Current tech stack

My first instinct is Elasticsearch -- it is the gold standard for full-text search. But wait, do they actually need a separate search cluster? For a product catalog, that might be massive overkill. Let me reason about the options more carefully:

1. PostgreSQL tsvector (built-in full-text search):
   - Pro: No additional infrastructure, already in your database, good enough for most use cases
   - Pro: Supports ranking, stemming, multiple languages, prefix matching
   - Con: No typo tolerance out of the box, faceted search is manual
   - Good for: < 1M products, simple search needs

2. Elasticsearch:
   - Pro: Very powerful, fuzzy matching, faceted search, autocomplete, highlighting
   - Con: Separate cluster to manage, Java-based, resource hungry, complex to operate. Hmm, I have seen teams spend more time managing their Elasticsearch cluster than building features.
   - Good for: Large catalogs, complex search requirements, dedicated search team

3. Typesense / Meilisearch:
   - Pro: Simple to set up, typo-tolerant by default, fast, good developer experience
   - Con: Less mature ecosystem, fewer advanced features than Elasticsearch
   - Good for: Small-to-medium catalogs where you want good search quickly

I initially leaned toward Typesense as a compromise, but actually for a product catalog, the right call depends on scale. For most companies, PostgreSQL full-text search is the pragmatic starting point. You already have the database, no new infrastructure needed, and it handles 90% of search needs. You only need to add something like Typesense later if users complain about typo tolerance or faceted search -- and they might not.

I will implement PostgreSQL FTS since it is the zero-infrastructure-cost option that works immediately. This way the user can ship today and upgrade later if needed.
</think>

Start with **PostgreSQL full-text search** -- it is already in your database, requires no additional infrastructure, and handles product catalogs well up to hundreds of thousands of products. Here is a complete implementation.

**Step 1: Add search columns and index to your products table**

```sql
-- Add a tsvector column that combines searchable fields with different weights
ALTER TABLE products ADD COLUMN search_vector tsvector;

-- Populate it: name gets weight A (highest), description gets B, tags get C
UPDATE products SET search_vector =
    setweight(to_tsvector('english', coalesce(name, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(description, '')), 'B') ||
    setweight(to_tsvector('english', coalesce(brand, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(category, '')), 'C') ||
    setweight(to_tsvector('english', coalesce(array_to_string(tags, ' '), '')), 'C');

-- GIN index for fast full-text lookups
CREATE INDEX idx_products_search ON products USING GIN (search_vector);

-- Trigram index for fuzzy/partial matching (handles typos)
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX idx_products_name_trgm ON products USING GIN (name gin_trgm_ops);

-- Keep search_vector updated automatically
CREATE OR REPLACE FUNCTION products_search_trigger() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('english', coalesce(NEW.name, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.description, '')), 'B') ||
        setweight(to_tsvector('english', coalesce(NEW.brand, '')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.category, '')), 'C') ||
        setweight(to_tsvector('english', coalesce(array_to_string(NEW.tags, ' '), '')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_products_search
    BEFORE INSERT OR UPDATE OF name, description, brand, category, tags
    ON products
    FOR EACH ROW
    EXECUTE FUNCTION products_search_trigger();
```

**Step 2: Python search service with ranking and highlighting**

```python
# search/service.py
from dataclasses import dataclass
from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class SearchResult:
    id: int
    name: str
    description: str
    brand: str
    category: str
    price: float
    rank: float
    headline: str  # highlighted snippet


@dataclass
class SearchResponse:
    results: list[SearchResult]
    total_count: int
    query: str
    page: int
    page_size: int


class ProductSearchService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def search(
        self,
        query: str,
        category: Optional[str] = None,
        min_price: Optional[float] = None,
        max_price: Optional[float] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> SearchResponse:
        """Full-text search with ranking, filtering, and highlighted snippets."""

        # Sanitize and convert user query to tsquery
        # plainto_tsquery handles natural language input safely
        # websearch_to_tsquery (PG 11+) handles quoted phrases and OR/AND
        search_clause = """
            search_vector @@ websearch_to_tsquery('english', :query)
        """

        # Build dynamic filter conditions
        filters = [search_clause]
        params = {"query": query, "page_size": page_size, "offset": (page - 1) * page_size}

        if category:
            filters.append("category = :category")
            params["category"] = category

        if min_price is not None:
            filters.append("price >= :min_price")
            params["min_price"] = min_price

        if max_price is not None:
            filters.append("price <= :max_price")
            params["max_price"] = max_price

        where_clause = " AND ".join(filters)

        # Main search query with ranking and highlighting
        sql = text(f"""
            SELECT
                id, name, description, brand, category, price,
                ts_rank_cd(search_vector, websearch_to_tsquery('english', :query), 32) AS rank,
                ts_headline(
                    'english',
                    coalesce(name, '') || ' - ' || coalesce(description, ''),
                    websearch_to_tsquery('english', :query),
                    'StartSel=<mark>, StopSel=</mark>, MaxWords=35, MinWords=15, MaxFragments=2'
                ) AS headline
            FROM products
            WHERE {where_clause}
            ORDER BY rank DESC, name ASC
            LIMIT :page_size OFFSET :offset
        """)

        # Count query for pagination
        count_sql = text(f"""
            SELECT COUNT(*) FROM products WHERE {where_clause}
        """)

        result = await self.db.execute(sql, params)
        rows = result.fetchall()

        count_result = await self.db.execute(count_sql, params)
        total = count_result.scalar()

        return SearchResponse(
            results=[
                SearchResult(
                    id=row.id,
                    name=row.name,
                    description=row.description or "",
                    brand=row.brand or "",
                    category=row.category or "",
                    price=float(row.price),
                    rank=float(row.rank),
                    headline=row.headline,
                )
                for row in rows
            ],
            total_count=total,
            query=query,
            page=page,
            page_size=page_size,
        )

    async def autocomplete(self, prefix: str, limit: int = 10) -> list[str]:
        """Fast prefix-based autocomplete using trigram similarity."""
        sql = text("""
            SELECT DISTINCT name,
                   similarity(name, :prefix) AS sim
            FROM products
            WHERE name % :prefix
               OR name ILIKE :prefix_pattern
            ORDER BY sim DESC, name
            LIMIT :limit
        """)
        result = await self.db.execute(sql, {
            "prefix": prefix,
            "prefix_pattern": f"{prefix}%",
            "limit": limit,
        })
        return [row.name for row in result.fetchall()]

    async def suggest_corrections(self, query: str) -> Optional[str]:
        """Did-you-mean suggestions using trigram similarity against known product names."""
        sql = text("""
            SELECT name, similarity(name, :query) AS sim
            FROM products
            WHERE similarity(name, :query) > 0.3
            ORDER BY sim DESC
            LIMIT 1
        """)
        result = await self.db.execute(sql, {"query": query})
        row = result.fetchone()
        if row and row.sim < 0.9:  # Only suggest if not already a close match
            return row.name
        return None
```

**Step 3: API endpoint**

```python
# search/routes.py
from fastapi import APIRouter, Depends, Query
from typing import Optional
from search.service import ProductSearchService, SearchResponse

router = APIRouter(prefix="/search", tags=["search"])


@router.get("/products", response_model=SearchResponse)
async def search_products(
    q: str = Query(..., min_length=1, description="Search query"),
    category: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    service: ProductSearchService = Depends(),
):
    return await service.search(
        query=q,
        category=category,
        min_price=min_price,
        max_price=max_price,
        page=page,
        page_size=page_size,
    )


@router.get("/autocomplete")
async def autocomplete(
    q: str = Query(..., min_length=1),
    service: ProductSearchService = Depends(),
):
    suggestions = await service.autocomplete(q)
    return {"suggestions": suggestions}
```

**When to upgrade beyond PostgreSQL FTS:**
- You need typo tolerance beyond trigrams (look at Typesense -- single binary, easy to deploy)
- You need faceted search with counts (e.g., "Brand: Nike (42), Adidas (38)")
- You have millions of products and search latency matters at the p99 level
- You need per-user personalized ranking

PostgreSQL FTS will take you surprisingly far. Most product catalogs under 500k items work great with this approach.'''
    ),
    (
        "thinking/practical",
        r'''how do I handle soft deletes properly? I keep getting bugs with deleted records showing up''',
        r'''<think>
This is a very common pain point. The user has a soft delete pattern (probably an `is_deleted` boolean or `deleted_at` timestamp) but keeps forgetting to filter deleted records in queries.

The root cause is interesting -- it is not really a code quality problem, it is a design problem. Soft deletes are opt-out (every query must remember to exclude deleted records) instead of opt-in (you have to explicitly ask for deleted records). That means every new query, every JOIN, every report is a potential bug. The system is designed to fail by default.

I considered suggesting they switch to hard deletes with an audit log, but wait -- there are legitimate reasons for soft deletes (legal compliance, undo functionality, data recovery). So the real question is: how do we make soft deletes safe?

Let me think about the solutions at different layers:

1. Application-level: SQLAlchemy query hooks that auto-filter deleted records -- this handles the ORM path
2. Database-level: PostgreSQL views that exclude deleted records -- hmm, this is actually the most robust approach because it catches direct SQL queries too, not just ORM queries
3. Architecture-level: Use a "status" column instead of soft delete, or move to event sourcing

Actually, the pragmatic fix is multi-layered. No single approach is sufficient because queries can bypass any one layer:
- Use `deleted_at` timestamp instead of boolean (more useful for auditing -- you know WHEN something was deleted, not just that it was)
- Default query scope that excludes deleted records
- Database view for cases where ORM hooks are bypassed (direct SQL, other services, reporting tools)
- Filtered indexes so deleted records do not slow down normal queries
- Make it hard to forget and easy to include deleted records when needed

I should show the complete pattern including the SQLAlchemy mixin, the query filtering, and the database-level safety net. The goal is defense in depth.
</think>

The core problem is that soft deletes are "opt-out" -- every query must remember to exclude deleted records. The fix is to make it "opt-in" -- you have to explicitly ask for deleted records. Here is the complete pattern.

**Step 1: Use `deleted_at` timestamp, not a boolean**

```python
# models/mixins.py
from datetime import datetime
from typing import Optional
from sqlalchemy import Column, DateTime, event
from sqlalchemy.orm import Session, Query, DeclarativeBase


class Base(DeclarativeBase):
    pass


class SoftDeleteMixin:
    """Add to any model that needs soft deletion.

    Usage:
        class User(SoftDeleteMixin, Base):
            __tablename__ = "users"
            ...

        # Delete (soft):
        user.soft_delete()
        session.commit()

        # Restore:
        user.restore()
        session.commit()

        # Query (deleted records automatically excluded):
        users = session.query(User).all()  # only active users

        # Include deleted records explicitly:
        users = session.query(User).execution_options(include_deleted=True).all()
    """
    deleted_at = Column(
        DateTime,
        nullable=True,
        default=None,
        index=True,
        comment="NULL means active, timestamp means soft-deleted",
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        self.deleted_at = datetime.utcnow()

    def restore(self) -> None:
        self.deleted_at = None


# --- Automatic query filtering ---
# This is the key: every query automatically excludes deleted records
# unless you explicitly opt in with .execution_options(include_deleted=True)

@event.listens_for(Session, "do_orm_execute")
def _filter_soft_deleted(execute_state):
    """Intercept all ORM queries and exclude soft-deleted records."""
    if not execute_state.is_select:
        return

    # Check if the caller explicitly wants deleted records
    if execute_state.execution_options.get("include_deleted", False):
        return

    # Add deleted_at IS NULL filter for all soft-delete models in the query
    for column_desc in execute_state.statement.column_descriptions:
        entity = column_desc.get("entity")
        if entity and hasattr(entity, "deleted_at"):
            execute_state.statement = execute_state.statement.filter(
                entity.deleted_at.is_(None)
            )
```

**Step 2: Use the mixin in your models**

```python
# models/user.py
from sqlalchemy import Column, Integer, String, ForeignKey
from sqlalchemy.orm import relationship
from models.mixins import SoftDeleteMixin, Base


class User(SoftDeleteMixin, Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), nullable=False, unique=True)
    name = Column(String(255))

    # Relationships also need to respect soft deletes
    orders = relationship(
        "Order",
        primaryjoin="and_(User.id == Order.user_id, Order.deleted_at == None)",
        back_populates="user",
    )


class Order(SoftDeleteMixin, Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    total = Column(Integer, nullable=False)

    user = relationship("User", back_populates="orders")
```

**Step 3: Database-level safety net**

```sql
-- Create views that only show active records
-- Use these for reporting, direct SQL queries, and as a safety net
CREATE OR REPLACE VIEW active_users AS
SELECT * FROM users WHERE deleted_at IS NULL;

CREATE OR REPLACE VIEW active_orders AS
SELECT * FROM orders WHERE deleted_at IS NULL;

-- Partial indexes: only index active records
-- This keeps your indexes small and fast (deleted records are dead weight)
CREATE INDEX idx_users_email_active ON users (email) WHERE deleted_at IS NULL;
CREATE INDEX idx_orders_user_active ON orders (user_id) WHERE deleted_at IS NULL;

-- If you need uniqueness only among active records:
-- (e.g., email must be unique but a deleted user's email can be reused)
CREATE UNIQUE INDEX idx_users_email_unique_active
ON users (email)
WHERE deleted_at IS NULL;
```

**Step 4: Service layer with explicit soft delete operations**

```python
# services/user_service.py
from datetime import datetime
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from models.user import User


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_user(self, user_id: int) -> Optional[User]:
        """Returns active user only (deleted records auto-filtered)."""
        result = await self.db.execute(
            select(User).where(User.id == user_id)
        )
        return result.scalar_one_or_none()

    async def get_user_including_deleted(self, user_id: int) -> Optional[User]:
        """Explicitly fetch even if soft-deleted (for admin/audit purposes)."""
        result = await self.db.execute(
            select(User)
            .where(User.id == user_id)
            .execution_options(include_deleted=True)
        )
        return result.scalar_one_or_none()

    async def delete_user(self, user_id: int) -> bool:
        """Soft delete a user."""
        user = await self.get_user(user_id)
        if not user:
            return False

        user.soft_delete()

        # Also soft-delete related records if needed
        for order in user.orders:
            order.soft_delete()

        await self.db.commit()
        return True

    async def restore_user(self, user_id: int) -> bool:
        """Restore a soft-deleted user."""
        user = await self.get_user_including_deleted(user_id)
        if not user or not user.is_deleted:
            return False

        user.restore()
        await self.db.commit()
        return True

    async def hard_delete_old_records(self, days_old: int = 90) -> int:
        """Permanently delete records that were soft-deleted over N days ago.
        Run this as a scheduled job."""
        cutoff = datetime.utcnow() - timedelta(days=days_old)
        result = await self.db.execute(
            delete(User)
            .where(User.deleted_at.isnot(None))
            .where(User.deleted_at < cutoff)
            .execution_options(include_deleted=True)
        )
        await self.db.commit()
        return result.rowcount
```

**Step 5: Tests that verify soft delete behavior**

```python
# tests/test_soft_delete.py
import pytest
from datetime import datetime


class TestSoftDelete:
    async def test_deleted_records_excluded_by_default(self, db, user_factory):
        user = await user_factory(email="test@example.com")
        user.soft_delete()
        await db.commit()

        # Default query should NOT find the deleted user
        result = await db.execute(select(User).where(User.email == "test@example.com"))
        assert result.scalar_one_or_none() is None

    async def test_include_deleted_option(self, db, user_factory):
        user = await user_factory(email="test@example.com")
        user.soft_delete()
        await db.commit()

        # Explicit opt-in SHOULD find the deleted user
        result = await db.execute(
            select(User)
            .where(User.email == "test@example.com")
            .execution_options(include_deleted=True)
        )
        found = result.scalar_one_or_none()
        assert found is not None
        assert found.deleted_at is not None

    async def test_restore_makes_record_visible_again(self, db, user_factory):
        user = await user_factory(email="test@example.com")
        user.soft_delete()
        await db.commit()

        user.restore()
        await db.commit()

        result = await db.execute(select(User).where(User.email == "test@example.com"))
        assert result.scalar_one_or_none() is not None

    async def test_unique_constraint_allows_reuse_of_deleted_email(self, db, user_factory):
        # Delete a user
        user1 = await user_factory(email="reuse@example.com")
        user1.soft_delete()
        await db.commit()

        # Should be able to create a new user with the same email
        user2 = await user_factory(email="reuse@example.com")
        await db.commit()
        assert user2.id != user1.id

    async def test_relationships_respect_soft_delete(self, db, user_factory, order_factory):
        user = await user_factory(email="test@example.com")
        order1 = await order_factory(user_id=user.id)
        order2 = await order_factory(user_id=user.id)
        order2.soft_delete()
        await db.commit()

        await db.refresh(user)
        # Only active orders should appear in the relationship
        assert len(user.orders) == 1
```

**Common pitfalls this pattern prevents:**
1. Forgetting to add `WHERE deleted_at IS NULL` -- handled by the ORM event hook
2. Unique constraint violations when re-creating records -- partial unique index
3. Deleted records slowing down queries -- partial indexes only cover active rows
4. Relationships loading deleted records -- filtered in relationship definition
5. No way to hard-delete old data -- scheduled cleanup job removes ancient soft-deleted rows'''
    ),
    (
        "thinking/practical",
        r'''our database is at 95% disk usage and growing''',
        r'''<think>
This is urgent -- 95% disk usage means they could run out of space soon, which would crash the database. At 100%, PostgreSQL refuses new writes and can even corrupt data. I need to give them both immediate relief and a long-term plan.

But wait -- what is actually consuming the space? My first assumption was "big tables with lots of data," but actually the culprit could be something else entirely. Dead tuples from UPDATE-heavy tables without proper vacuuming can double or triple the table size. WAL files from a broken replication setup can consume hundreds of GB. Unused indexes can be surprisingly large. I need to help them diagnose before prescribing a fix.

Let me think about the layers of response:

Immediate (buy time):
1. Identify what is using the space (tables, indexes, dead tuples, WAL) -- this diagnostic step is critical
2. VACUUM FULL on bloated tables (reclaims space but locks the table) -- hmm, actually this is risky. VACUUM FULL takes an exclusive lock, so on a production database it will block all queries. pg_repack is safer because it works online.
3. Drop unused indexes -- zero-cost win if there are any
4. Truncate or archive old log/audit tables

Short-term (days):
1. Set up table partitioning for large tables (especially time-series data)
2. Archive old data to cheaper storage
3. Enable compression (TOAST already handles this for large values)
4. Clean up dead tuples -- if autovacuum is falling behind, that is a configuration problem. The default settings are often too conservative for busy databases.

Long-term (weeks):
1. Partition large tables by date
2. Implement data retention policies (because without them, you will be back here in 6 months)
3. Set up monitoring and alerts at 80% -- not 90%, because 80% gives you time to act before it becomes a crisis
4. Consider read replicas to offload analytical queries

I should give them diagnostic queries first so they can understand what is eating their disk, then concrete actions in priority order. No point recommending partitioning if the real problem is WAL bloat.
</think>

This is urgent. Here is a triage plan: diagnose what is eating space, get immediate relief, then implement long-term fixes.

**Step 1: Diagnose -- figure out where the space is going**

```sql
-- Top 20 largest tables (data + toast)
SELECT
    schemaname || '.' || tablename AS table_name,
    pg_size_pretty(pg_total_relation_size(schemaname || '.' || tablename)) AS total_size,
    pg_size_pretty(pg_relation_size(schemaname || '.' || tablename)) AS table_size,
    pg_size_pretty(
        pg_total_relation_size(schemaname || '.' || tablename) -
        pg_relation_size(schemaname || '.' || tablename)
    ) AS indexes_and_toast,
    n_live_tup AS live_rows,
    n_dead_tup AS dead_rows,
    CASE WHEN n_live_tup > 0
        THEN round(100.0 * n_dead_tup / (n_live_tup + n_dead_tup), 1)
        ELSE 0
    END AS dead_pct
FROM pg_stat_user_tables
JOIN pg_tables USING (schemaname, tablename)
ORDER BY pg_total_relation_size(schemaname || '.' || tablename) DESC
LIMIT 20;

-- Index bloat -- find oversized indexes
SELECT
    schemaname || '.' || indexrelname AS index_name,
    pg_size_pretty(pg_relation_size(indexrelid)) AS index_size,
    idx_scan AS times_used,
    CASE WHEN idx_scan = 0 THEN 'UNUSED - safe to drop' ELSE 'in use' END AS status
FROM pg_stat_user_indexes
ORDER BY pg_relation_size(indexrelid) DESC
LIMIT 20;

-- Table bloat estimate (dead tuples that VACUUM has not reclaimed)
SELECT
    schemaname || '.' || relname AS table_name,
    n_dead_tup,
    n_live_tup,
    pg_size_pretty(pg_relation_size(relid)) AS size,
    last_autovacuum,
    last_vacuum
FROM pg_stat_user_tables
WHERE n_dead_tup > 10000
ORDER BY n_dead_tup DESC;

-- WAL files (can consume significant space)
SELECT pg_size_pretty(sum(size)) AS total_wal_size
FROM pg_ls_waldir();

-- Check overall database size
SELECT
    datname,
    pg_size_pretty(pg_database_size(datname)) AS size
FROM pg_database
ORDER BY pg_database_size(datname) DESC;
```

**Step 2: Immediate relief (do these NOW)**

```sql
-- 2a: Drop unused indexes (they take space but provide no benefit)
-- First, verify they are truly unused:
SELECT indexrelname, idx_scan, pg_size_pretty(pg_relation_size(indexrelid))
FROM pg_stat_user_indexes
WHERE idx_scan = 0
AND indexrelname NOT LIKE '%_pkey'  -- never drop primary keys
AND indexrelname NOT LIKE '%_unique%'  -- be careful with unique constraints
ORDER BY pg_relation_size(indexrelid) DESC;

-- Drop each unused index:
-- DROP INDEX CONCURRENTLY idx_that_nobody_uses;

-- 2b: Reclaim dead tuple space (aggressive vacuum)
-- For each bloated table found in step 1:
VACUUM (VERBOSE, ANALYZE) your_bloated_table;

-- If VACUUM alone does not reclaim enough space (it returns space to the OS
-- only from the end of the file), use VACUUM FULL during a maintenance window:
-- WARNING: VACUUM FULL locks the table for the entire duration
-- VACUUM FULL your_bloated_table;

-- 2c: Truncate or archive large log/audit/event tables
-- If you have event_log, audit_trail, etc. with millions of old rows:
BEGIN;
-- Move old data to archive table (or just delete if you do not need it)
CREATE TABLE event_log_archive_2023 AS
SELECT * FROM event_log WHERE created_at < '2024-01-01';

DELETE FROM event_log WHERE created_at < '2024-01-01';
COMMIT;
VACUUM FULL event_log;  -- reclaim the space
```

**Step 3: Table partitioning for the biggest tables**

```sql
-- Convert your largest time-series table to partitioned table
-- Example: converting an 'events' table to monthly partitions

-- 3a: Create the new partitioned table
CREATE TABLE events_partitioned (
    id bigserial,
    event_type text NOT NULL,
    payload jsonb,
    user_id integer,
    created_at timestamptz NOT NULL DEFAULT now()
) PARTITION BY RANGE (created_at);

-- 3b: Create partitions for each month
CREATE TABLE events_y2024m01 PARTITION OF events_partitioned
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');
CREATE TABLE events_y2024m02 PARTITION OF events_partitioned
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');
-- ... create one per month through current date + 3 months ahead

-- 3c: Create a default partition for anything that does not match
CREATE TABLE events_default PARTITION OF events_partitioned DEFAULT;

-- 3d: Migrate data (during maintenance window)
INSERT INTO events_partitioned SELECT * FROM events;

-- 3e: Swap tables
ALTER TABLE events RENAME TO events_old;
ALTER TABLE events_partitioned RENAME TO events;

-- 3f: After verification, drop the old table
-- DROP TABLE events_old;
```

**Step 4: Automated data retention policy**

```python
# scripts/data_retention.py
"""Run this as a daily cron job to enforce data retention policies."""

import asyncio
from datetime import datetime, timedelta
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession

RETENTION_POLICIES = {
    # table_name: days to keep
    "event_log": 90,
    "api_request_log": 30,
    "session_tokens": 7,
    "email_delivery_log": 180,
    "audit_trail": 365,  # keep audit logs longer
}


async def enforce_retention():
    engine = create_async_engine("postgresql+asyncpg://localhost/myapp")

    async with AsyncSession(engine) as session:
        for table, retention_days in RETENTION_POLICIES.items():
            cutoff = datetime.utcnow() - timedelta(days=retention_days)

            # Delete in batches to avoid long-running transactions
            total_deleted = 0
            while True:
                result = await session.execute(
                    text(f"""
                        DELETE FROM {table}
                        WHERE ctid IN (
                            SELECT ctid FROM {table}
                            WHERE created_at < :cutoff
                            LIMIT 10000
                        )
                    """),
                    {"cutoff": cutoff},
                )
                await session.commit()
                batch_deleted = result.rowcount
                total_deleted += batch_deleted

                if batch_deleted < 10000:
                    break

            if total_deleted > 0:
                print(f"[{table}] Deleted {total_deleted} rows older than {retention_days} days")
                # VACUUM after bulk deletes to reclaim space
                await session.execute(text(f"VACUUM ANALYZE {table}"))

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(enforce_retention())
```

**Step 5: Monitoring to prevent this from happening again**

```python
# monitoring/disk_check.py
"""Add this to your health check endpoint or monitoring system."""

from sqlalchemy import text

async def check_disk_usage(session) -> dict:
    result = await session.execute(text("""
        SELECT
            pg_size_pretty(pg_database_size(current_database())) AS db_size,
            pg_database_size(current_database()) AS db_size_bytes
    """))
    row = result.fetchone()

    # Alert thresholds (adjust based on your disk size)
    disk_total_bytes = 100 * 1024 * 1024 * 1024  # 100 GB -- set to your actual disk
    usage_pct = (row.db_size_bytes / disk_total_bytes) * 100

    status = "ok"
    if usage_pct > 90:
        status = "critical"
    elif usage_pct > 80:
        status = "warning"

    return {
        "database_size": row.db_size,
        "disk_usage_percent": round(usage_pct, 1),
        "status": status,
    }
```

**Priority order:**
1. Run diagnostic queries (5 minutes)
2. Drop unused indexes (immediate space savings, no risk)
3. VACUUM bloated tables (minutes to hours depending on size)
4. Delete or archive old data from log tables (biggest wins usually here)
5. Set up partitioning for time-series tables (prevents future growth)
6. Deploy retention policy cron job (automated ongoing cleanup)
7. Add disk usage monitoring with alerts at 80%'''
    ),
    (
        "thinking/practical",
        r'''I keep getting deadlocks between these two queries

-- Query A (runs in the order processing worker):
BEGIN;
UPDATE inventory SET quantity = quantity - 1 WHERE product_id = 101;
UPDATE orders SET status = 'confirmed' WHERE id = 5001;
COMMIT;

-- Query B (runs in the refund processor):
BEGIN;
UPDATE orders SET status = 'refunded' WHERE id = 5001;
UPDATE inventory SET quantity = quantity + 1 WHERE product_id = 101;
COMMIT;''',
        r'''<think>
This is a textbook deadlock scenario. Let me trace through exactly what happens step by step:

1. Query A starts: acquires row lock on inventory (product_id=101)
2. Query B starts: acquires row lock on orders (id=5001)
3. Query A tries to update orders (id=5001) -- BLOCKED, waiting for Query B's lock
4. Query B tries to update inventory (product_id=101) -- BLOCKED, waiting for Query A's lock
5. DEADLOCK: both transactions are waiting for each other, and neither can make progress

My first thought was "just add a timeout so one transaction fails and the other can proceed." But wait, that is treating the symptom, not the cause. The deadlock would just keep happening on every retry.

The fundamental problem is that these two transactions lock the SAME TWO RESOURCES in DIFFERENT ORDER:
- Query A: inventory first, then orders
- Query B: orders first, then inventory

Hmm, could this also happen with more than two resources? Yes -- deadlocks can form cycles of any length, but in practice two-resource deadlocks are the most common because they are the easiest to accidentally create.

The fix is straightforward: always acquire locks in the same order. Both transactions should lock in the same sequence (e.g., always inventory before orders, or always orders before inventory). The specific order does not matter, as long as it is consistent. I would recommend alphabetical by table name as a simple convention.

There are also defensive strategies:
1. Lock ordering (primary fix -- prevents deadlocks entirely)
2. SELECT FOR UPDATE to acquire locks upfront -- actually, this is important because it makes the locking explicit and visible, rather than implicit in UPDATE statements where you might not realize you are acquiring locks
3. Advisory locks for complex multi-resource transactions
4. Timeout and retry with backoff (defense in depth, since lock ordering only works if everyone follows the convention)

I should show all of these since the user will encounter variations of this problem.
</think>

Classic deadlock: your two transactions lock the same resources in opposite order.

**What is happening:**

```
Timeline:
T1: Query A locks inventory(101)     Query B locks orders(5001)
T2: Query A wants orders(5001) ----> BLOCKED (B holds it)
    Query B wants inventory(101) --> BLOCKED (A holds it)
T3: DEADLOCK -- PostgreSQL kills one transaction
```

**Fix 1: Consistent lock ordering (the primary fix)**

Always access tables in the same order across all transactions. Pick an order (e.g., alphabetical: inventory before orders) and stick to it everywhere:

```python
# services/order_service.py
from sqlalchemy import text, select, update
from sqlalchemy.ext.asyncio import AsyncSession


class OrderService:
    # RULE: All transactions that touch multiple tables must lock in this order:
    # 1. inventory
    # 2. orders
    # 3. payments
    # This prevents deadlocks by ensuring no circular wait condition.

    def __init__(self, db: AsyncSession):
        self.db = db

    async def confirm_order(self, order_id: int, product_id: int) -> None:
        """Order processing: decrement inventory, confirm order."""
        async with self.db.begin():
            # Step 1: Lock inventory FIRST (consistent ordering)
            await self.db.execute(
                update(Inventory)
                .where(Inventory.product_id == product_id)
                .values(quantity=Inventory.quantity - 1)
            )
            # Step 2: Lock orders SECOND
            await self.db.execute(
                update(Order)
                .where(Order.id == order_id)
                .values(status="confirmed")
            )

    async def refund_order(self, order_id: int, product_id: int) -> None:
        """Refund processing: restore inventory, mark refunded.
        NOTE: We lock inventory FIRST even though the business logic
        is 'refund the order then restore inventory'. Lock ordering
        is about preventing deadlocks, not business semantics."""
        async with self.db.begin():
            # Step 1: Lock inventory FIRST (same order as confirm_order!)
            await self.db.execute(
                update(Inventory)
                .where(Inventory.product_id == product_id)
                .values(quantity=Inventory.quantity + 1)
            )
            # Step 2: Lock orders SECOND
            await self.db.execute(
                update(Order)
                .where(Order.id == order_id)
                .values(status="refunded")
            )
```

**Fix 2: Explicit upfront locking with SELECT FOR UPDATE**

If you need to read data before deciding what to update, grab all locks at the start of the transaction:

```python
async def process_order_with_validation(
    self, order_id: int, product_id: int
) -> str:
    """Acquire all locks upfront, then do business logic."""
    async with self.db.begin():
        # Grab locks in consistent order BEFORE doing any logic
        inventory = await self.db.execute(
            select(Inventory)
            .where(Inventory.product_id == product_id)
            .with_for_update()  # row-level exclusive lock
        )
        inv_row = inventory.scalar_one()

        order = await self.db.execute(
            select(Order)
            .where(Order.id == order_id)
            .with_for_update()
        )
        order_row = order.scalar_one()

        # Now we hold both locks -- safe to do business logic
        if inv_row.quantity <= 0:
            return "out_of_stock"

        if order_row.status != "pending":
            return "already_processed"

        inv_row.quantity -= 1
        order_row.status = "confirmed"
        return "confirmed"
```

**Fix 3: Advisory locks for complex multi-resource operations**

When you need to coordinate across many resources and lock ordering is not practical:

```python
async def process_complex_operation(
    self, order_id: int, product_ids: list[int]
) -> None:
    """Use advisory locks when the set of resources is dynamic."""
    async with self.db.begin():
        # Sort resource IDs to ensure consistent lock ordering
        # even when the set of resources varies per call
        sorted_product_ids = sorted(product_ids)

        # Acquire advisory locks in sorted order
        for pid in sorted_product_ids:
            # pg_advisory_xact_lock auto-releases at end of transaction
            await self.db.execute(
                text("SELECT pg_advisory_xact_lock(:lock_id)"),
                {"lock_id": pid},
            )

        # Now safe to update all products without deadlock risk
        for pid in sorted_product_ids:
            await self.db.execute(
                update(Inventory)
                .where(Inventory.product_id == pid)
                .values(quantity=Inventory.quantity - 1)
            )

        await self.db.execute(
            update(Order)
            .where(Order.id == order_id)
            .values(status="confirmed")
        )
```

**Fix 4: Retry with backoff (defensive layer)**

Even with lock ordering, add retry logic as a safety net:

```python
import asyncio
import random
from sqlalchemy.exc import OperationalError


async def with_deadlock_retry(
    operation,
    max_retries: int = 3,
    base_delay: float = 0.1,
):
    """Retry an operation if it hits a deadlock.

    This is a SAFETY NET, not a fix. The primary fix is lock ordering.
    If you are hitting this retry often, fix your lock ordering.
    """
    for attempt in range(max_retries + 1):
        try:
            return await operation()
        except OperationalError as e:
            if "deadlock detected" not in str(e).lower():
                raise  # not a deadlock, re-raise immediately

            if attempt == max_retries:
                raise  # exhausted retries

            # Exponential backoff with jitter
            delay = base_delay * (2 ** attempt) + random.uniform(0, 0.1)
            print(
                f"Deadlock detected (attempt {attempt + 1}/{max_retries}), "
                f"retrying in {delay:.2f}s"
            )
            await asyncio.sleep(delay)


# Usage:
await with_deadlock_retry(
    lambda: order_service.confirm_order(order_id=5001, product_id=101)
)
```

**Summary of the deadlock prevention rules:**

1. **Always lock resources in the same order** across all transactions (alphabetical by table name is a simple convention)
2. **Sort dynamic resource sets** before locking (e.g., sort product IDs)
3. **Lock everything upfront** with SELECT FOR UPDATE before doing business logic
4. **Keep transactions short** -- do validation and computation outside the transaction, only lock/update inside
5. **Add retry as a safety net** -- but fix the root cause if retries fire frequently
6. **Monitor deadlocks** -- `SELECT * FROM pg_stat_activity WHERE wait_event_type = 'Lock'` shows current lock waits'''
    ),
]
