PAIRS = [
    (
        "python-web/fastapi-dependency-injection-middleware",
        "Explain FastAPI dependency injection system internals including sub-dependencies, yield dependencies for resource cleanup, middleware stack ordering, and background tasks with practical async patterns",
        r"""# FastAPI Dependency Injection and Middleware Deep Dive

## Understanding the Dependency System

FastAPI's dependency injection system is one of the most powerful features in any Python web framework, **because** it provides automatic resolution of nested dependencies, lifecycle management through `yield`, and seamless integration with Python's type system. Understanding how it works internally — not just how to use it — is critical for building production-grade APIs.

### How Dependency Resolution Works

When a request arrives, FastAPI builds a **dependency graph** by inspecting function signatures via `inspect.signature()`. Dependencies are resolved bottom-up: if `endpoint A` depends on `service B`, which depends on `db_session C`, FastAPI resolves C first, then B, then A. **Therefore**, circular dependencies cause immediate errors at startup, not at runtime.

```python
from fastapi import FastAPI, Depends, Request, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional, Annotated
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import asyncio
import time
import logging

logger = logging.getLogger(__name__)

# --- Database session management with yield dependencies ---

@dataclass
class DBSession:
    # Simulates an async database session
    _closed: bool = False
    _transaction_active: bool = False
    queries: list = field(default_factory=list)

    async def execute(self, query: str, params: dict = None) -> list:
        if self._closed:
            raise RuntimeError("Session is closed")
        self.queries.append((query, params))
        return [{"id": 1, "result": "mock"}]

    async def begin(self) -> None:
        self._transaction_active = True

    async def commit(self) -> None:
        self._transaction_active = False

    async def rollback(self) -> None:
        self._transaction_active = False

    async def close(self) -> None:
        if self._transaction_active:
            await self.rollback()
        self._closed = True

class DBPool:
    # Connection pool with health checking
    def __init__(self, dsn: str, min_size: int = 5, max_size: int = 20):
        self.dsn = dsn
        self.min_size = min_size
        self.max_size = max_size
        self._semaphore = asyncio.Semaphore(max_size)
        self._active_count = 0

    async def acquire(self) -> DBSession:
        await self._semaphore.acquire()
        self._active_count += 1
        return DBSession()

    async def release(self, session: DBSession) -> None:
        await session.close()
        self._active_count -= 1
        self._semaphore.release()

    @property
    def active_connections(self) -> int:
        return self._active_count

# Global pool — initialized at startup
_pool: Optional[DBPool] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create connection pool
    global _pool
    _pool = DBPool("postgresql://user:pass@localhost/db", min_size=5, max_size=20)
    logger.info("Database pool initialized")
    yield
    # Shutdown: cleanup pool
    logger.info("Shutting down database pool")
    _pool = None

# Yield dependency — ensures cleanup even on exceptions
async def get_db() -> AsyncGenerator[DBSession, None]:
    # A common mistake is forgetting that yield dependencies
    # ALWAYS run their cleanup code, even if the endpoint raises
    session = await _pool.acquire()
    try:
        await session.begin()
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await _pool.release(session)
```

### Sub-Dependencies and Dependency Caching

**However**, a critical detail many developers miss is that FastAPI caches dependency results within a single request by default. If two parameters both depend on `get_db()`, they receive the **same** session instance. This is controlled by the `use_cache` parameter.

```python
# --- Sub-dependency patterns ---

@dataclass
class CurrentUser:
    id: int
    email: str
    roles: list[str]
    is_active: bool = True

class AuthService:
    def __init__(self, db: DBSession):
        self.db = db

    async def get_user_by_token(self, token: str) -> Optional[CurrentUser]:
        results = await self.db.execute(
            "SELECT id, email, roles, is_active FROM users WHERE token = :token",
            {"token": token}
        )
        if not results:
            return None
        row = results[0]
        return CurrentUser(
            id=row["id"],
            email=row.get("email", ""),
            roles=row.get("roles", []),
            is_active=row.get("is_active", True),
        )

# Sub-dependency: auth service depends on db
async def get_auth_service(db: Annotated[DBSession, Depends(get_db)]) -> AuthService:
    return AuthService(db)

# Sub-dependency: current user depends on auth service and request
async def get_current_user(
    request: Request,
    auth: Annotated[AuthService, Depends(get_auth_service)],
) -> CurrentUser:
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(status_code=401, detail="Missing auth token")
    user = await auth.get_user_by_token(token)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="Invalid or inactive user")
    return user

# Role-based access — dependency factory pattern
# Best practice: use closures to create parameterized dependencies
def require_roles(*roles: str):
    async def role_checker(
        user: Annotated[CurrentUser, Depends(get_current_user)]
    ) -> CurrentUser:
        if not any(r in user.roles for r in roles):
            raise HTTPException(
                status_code=403,
                detail=f"Requires one of: {', '.join(roles)}"
            )
        return user
    return role_checker

# Rate limiter as a dependency
class RateLimiter:
    def __init__(self, requests_per_minute: int = 60):
        self.rpm = requests_per_minute
        self._buckets: dict[str, list[float]] = {}

    async def __call__(self, request: Request) -> None:
        key = request.client.host if request.client else "unknown"
        now = time.time()
        window_start = now - 60.0
        # Clean old entries
        self._buckets[key] = [
            t for t in self._buckets.get(key, []) if t > window_start
        ]
        if len(self._buckets[key]) >= self.rpm:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded",
                headers={"Retry-After": "60"},
            )
        self._buckets[key].append(now)

rate_limit = RateLimiter(requests_per_minute=100)

# --- Middleware stack ---

app = FastAPI(lifespan=lifespan)

# Middleware ordering pitfall: middleware is applied in REVERSE order
# The LAST added middleware runs FIRST on request (outermost)
# Therefore, add CORS last so it runs first

class TimingMiddleware:
    # Custom ASGI middleware for request timing
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        start = time.perf_counter()
        async def send_with_timing(message):
            if message["type"] == "http.response.start":
                duration = time.perf_counter() - start
                headers = list(message.get("headers", []))
                headers.append(
                    (b"x-process-time", f"{duration:.4f}".encode())
                )
                message["headers"] = headers
            await send(message)
        await self.app(scope, receive, send_with_timing)

class RequestIdMiddleware:
    # Adds unique request ID for tracing
    def __init__(self, app):
        self.app = app
        self._counter = 0

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            self._counter += 1
            scope["state"] = scope.get("state", {})
            scope["state"]["request_id"] = f"req-{self._counter:08d}"
        await self.app(scope, receive, send)

# Order matters — outermost to innermost on request:
# CORS -> RequestId -> Timing -> Route handler
app.add_middleware(TimingMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://myapp.com"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### Background Tasks and Advanced Patterns

The **trade-off** with FastAPI's `BackgroundTasks` is simplicity vs reliability. Background tasks run in the same process after the response is sent — **therefore**, if the server crashes, the task is lost. For critical work, use a proper task queue like Celery or arq.

```python
# --- Background tasks and advanced endpoint patterns ---

class AuditLogger:
    # Logs user actions after response is sent
    async def log_action(
        self, user_id: int, action: str, resource: str, details: dict
    ) -> None:
        # In production, write to audit table or external service
        logger.info(
            "AUDIT: user=%d action=%s resource=%s details=%s",
            user_id, action, resource, details,
        )

audit_logger = AuditLogger()

@app.get("/api/admin/users")
async def list_users(
    background_tasks: BackgroundTasks,
    user: Annotated[CurrentUser, Depends(require_roles("admin"))],
    db: Annotated[DBSession, Depends(get_db)],
    _rate: Annotated[None, Depends(rate_limit)],
    page: int = 1,
    per_page: int = 20,
):
    # Dependency resolution order:
    # 1. get_db() -> DBSession
    # 2. get_auth_service(db) -> AuthService (reuses cached db)
    # 3. get_current_user(request, auth) -> CurrentUser
    # 4. require_roles("admin")(user) -> CurrentUser (verified)
    # 5. rate_limit(request) -> None (side effect only)
    offset = (page - 1) * per_page
    results = await db.execute(
        "SELECT * FROM users LIMIT :limit OFFSET :offset",
        {"limit": per_page, "offset": offset},
    )
    # Background task runs AFTER response is sent
    background_tasks.add_task(
        audit_logger.log_action,
        user_id=user.id,
        action="list_users",
        resource="users",
        details={"page": page, "per_page": per_page},
    )
    return {"users": results, "page": page, "per_page": per_page}

# --- Testing dependencies with overrides ---

from fastapi.testclient import TestClient

def test_admin_endpoint():
    # Best practice: override dependencies for isolated testing
    mock_user = CurrentUser(id=99, email="admin@test.com", roles=["admin"])

    async def override_user():
        return mock_user

    async def override_db():
        session = DBSession()
        yield session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_db] = override_db

    client = TestClient(app)
    response = client.get("/api/admin/users?page=1")
    assert response.status_code == 200
    assert "users" in response.json()

    # Always clean up overrides
    app.dependency_overrides.clear()
```

## Summary and Key Takeaways

- **Yield dependencies** provide deterministic cleanup — the `finally` block runs even on exceptions, making them ideal for database sessions, file handles, and locks
- **Dependency caching** within a request means the same `Depends(get_db)` returns the same instance — use `Depends(get_db, use_cache=False)` to get separate instances
- **Middleware ordering** is reverse of addition order — add CORS last so it runs first on every request
- A **common mistake** is putting heavy computation in dependencies instead of using background tasks or worker queues
- The **pitfall** of `BackgroundTasks` is that they're fire-and-forget within the same process — for reliability, use distributed task queues
- **Dependency factories** (closures returning dependency functions) enable parameterized dependencies like role checking
- **Testing** with `dependency_overrides` is the cleanest way to mock dependencies without patching"""
    ),
    (
        "python-web/django-orm-optimization-patterns",
        "Describe Django ORM query optimization including select_related and prefetch_related strategies, custom managers, QuerySet chaining, N+1 detection, database indexing, and raw SQL escape hatches for complex reporting queries",
        r"""# Django ORM Query Optimization Patterns

## The N+1 Problem and How Django Solves It

The most common performance **pitfall** in Django applications is the N+1 query problem: fetching a list of N objects and then making one additional query per object to access related data. **Because** Django's ORM uses lazy evaluation by default, related objects are only fetched when accessed — which is elegant for simple cases but devastating for list views.

### Understanding Lazy vs Eager Loading

```python
from django.db import models, connection
from django.db.models import (
    Q, F, Value, Count, Sum, Avg, Prefetch,
    OuterRef, Subquery, Exists, Window
)
from django.db.models.functions import Rank, DenseRank, RowNumber
from typing import Optional
import logging

logger = logging.getLogger("django.db")

# --- Models with various relationship types ---

class Author(models.Model):
    name = models.CharField(max_length=200)
    email = models.EmailField(unique=True)
    bio = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "library"
        indexes = [
            models.Index(fields=["name"], name="idx_author_name"),
            models.Index(fields=["email"], name="idx_author_email"),
        ]

class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(unique=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True,
        on_delete=models.CASCADE,
        related_name="children"
    )

    class Meta:
        app_label = "library"

class Book(models.Model):
    title = models.CharField(max_length=300)
    author = models.ForeignKey(
        Author, on_delete=models.CASCADE, related_name="books"
    )
    categories = models.ManyToManyField(Category, related_name="books")
    published_date = models.DateField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        app_label = "library"
        indexes = [
            models.Index(
                fields=["author", "-published_date"],
                name="idx_book_author_date"
            ),
            models.Index(
                fields=["is_active", "price"],
                name="idx_book_active_price",
                condition=Q(is_active=True),  # Partial index
            ),
        ]
        ordering = ["-published_date"]

class Review(models.Model):
    book = models.ForeignKey(
        Book, on_delete=models.CASCADE, related_name="reviews"
    )
    reviewer_name = models.CharField(max_length=200)
    rating = models.IntegerField()
    text = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "library"
        indexes = [
            models.Index(
                fields=["book", "-rating"],
                name="idx_review_book_rating"
            ),
        ]
```

### select_related vs prefetch_related

The fundamental **trade-off** is between `select_related` (SQL JOIN, one query, good for ForeignKey/OneToOne) and `prefetch_related` (separate query + Python-side join, good for ManyToMany and reverse FK). **Therefore**, choosing the wrong one can either cause cartesian explosion (too many JOINs) or unnecessary round-trips.

```python
# --- Custom Manager with optimization built in ---

class BookQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True)

    def with_author(self):
        # select_related for ForeignKey — single JOIN
        return self.select_related("author")

    def with_categories(self):
        # prefetch_related for M2M — separate query
        return self.prefetch_related("categories")

    def with_top_reviews(self, limit: int = 3):
        # Custom Prefetch with filtered queryset
        # Best practice: limit prefetch results to avoid memory bloat
        top_reviews = Review.objects.order_by("-rating")[:limit]
        return self.prefetch_related(
            Prefetch("reviews", queryset=top_reviews, to_attr="top_reviews")
        )

    def with_review_stats(self):
        # Annotation avoids N+1 for aggregate data
        return self.annotate(
            review_count=Count("reviews"),
            avg_rating=Avg("reviews__rating"),
        )

    def expensive_books(self, threshold=50):
        return self.filter(price__gte=threshold)

    def by_category(self, category_slug: str):
        return self.filter(categories__slug=category_slug).distinct()

    def search(self, query: str):
        # Full-text search with ranking
        return self.filter(
            Q(title__icontains=query) | Q(author__name__icontains=query)
        )

class BookManager(models.Manager):
    def get_queryset(self) -> BookQuerySet:
        return BookQuerySet(self.model, using=self._db)

    def active(self):
        return self.get_queryset().active()

# Attach to model: objects = BookManager()

# --- Optimized view patterns ---

def get_book_list_optimized():
    # Common mistake: not chaining optimizations
    # BAD: Book.objects.all() then accessing .author in template -> N+1
    # GOOD: chain all needed relations upfront
    return (
        Book.objects
        .active()
        .with_author()
        .with_categories()
        .with_review_stats()
        .only("id", "title", "price", "published_date",
              "author__id", "author__name")  # Defer large fields
        .order_by("-published_date")
    )

def get_author_dashboard(author_id: int) -> dict:
    # Subquery for latest book date per author
    latest_book = (
        Book.objects
        .filter(author=OuterRef("pk"))
        .order_by("-published_date")
        .values("published_date")[:1]
    )
    # Exists subquery for "has reviewed books"
    has_reviews = Review.objects.filter(
        book__author=OuterRef("pk")
    )
    author = (
        Author.objects
        .annotate(
            book_count=Count("books", filter=Q(books__is_active=True)),
            total_revenue=Sum("books__price", filter=Q(books__is_active=True)),
            avg_book_rating=Avg("books__reviews__rating"),
            latest_publication=Subquery(latest_book),
            has_any_reviews=Exists(has_reviews),
        )
        .prefetch_related(
            Prefetch(
                "books",
                queryset=Book.objects.active().with_review_stats().order_by("-published_date")[:10],
                to_attr="recent_books",
            )
        )
        .get(pk=author_id)
    )
    return {
        "author": author,
        "book_count": author.book_count,
        "total_revenue": author.total_revenue,
        "recent_books": author.recent_books,
    }

# --- Window functions for ranking ---

def get_books_ranked_by_category():
    # Window functions avoid self-joins for ranking
    return (
        Book.objects
        .active()
        .with_author()
        .annotate(
            category_rank=Window(
                expression=DenseRank(),
                partition_by=F("categories"),
                order_by=F("price").desc(),
            ),
            row_num=Window(
                expression=RowNumber(),
                order_by=F("published_date").desc(),
            ),
        )
    )
```

### N+1 Detection and Raw SQL Escape Hatch

**However**, even with best practices, complex reporting queries sometimes need raw SQL. Django provides `raw()` and `connection.cursor()` as escape hatches. The **pitfall** is that raw SQL bypasses the ORM's type coercion and model validation.

```python
# --- N+1 detection middleware ---

class QueryCountMiddleware:
    # Detects N+1 patterns in development
    def __init__(self, get_response):
        self.get_response = get_response
        self.threshold = 10  # Alert if more than 10 queries

    def __call__(self, request):
        from django.db import reset_queries
        from django.conf import settings

        if not settings.DEBUG:
            return self.get_response(request)

        reset_queries()
        initial_count = len(connection.queries)
        response = self.get_response(request)
        query_count = len(connection.queries) - initial_count

        if query_count > self.threshold:
            logger.warning(
                "N+1 ALERT: %s %s executed %d queries",
                request.method, request.path, query_count,
            )
            # Log duplicate query patterns
            seen = {}
            for q in connection.queries[initial_count:]:
                sql = q["sql"]
                prefix = sql[:100]
                seen[prefix] = seen.get(prefix, 0) + 1
            for prefix, count in seen.items():
                if count > 2:
                    logger.warning(
                        "  Repeated %dx: %s...", count, prefix
                    )

        response["X-Query-Count"] = str(query_count)
        return response

# --- Raw SQL for complex reporting ---

def get_revenue_report(year: int) -> list[dict]:
    # Best practice: use params for SQL injection prevention
    # However, use raw SQL only when ORM cannot express the query
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT a.name AS author_name, "
            "  COUNT(DISTINCT b.id) AS book_count, "
            "  COALESCE(SUM(b.price), 0) AS total_revenue, "
            "  COALESCE(AVG(r.rating), 0) AS avg_rating, "
            "  COUNT(DISTINCT r.id) AS review_count "
            "FROM library_author a "
            "LEFT JOIN library_book b ON b.author_id = a.id "
            "  AND b.is_active = TRUE "
            "  AND EXTRACT(YEAR FROM b.published_date) = %s "
            "LEFT JOIN library_review r ON r.book_id = b.id "
            "GROUP BY a.id, a.name "
            "HAVING COUNT(DISTINCT b.id) > 0 "
            "ORDER BY total_revenue DESC",
            [year],
        )
        columns = [col[0] for col in cursor.description]
        return [dict(zip(columns, row)) for row in cursor.fetchall()]

# --- Bulk operations for write performance ---

def bulk_update_prices(category_slug: str, increase_pct: float) -> int:
    # F() expressions update at database level — no Python round-trip
    # Therefore, no race conditions with concurrent updates
    updated = (
        Book.objects
        .filter(categories__slug=category_slug, is_active=True)
        .update(price=F("price") * (1 + increase_pct / 100))
    )
    return updated

def bulk_create_reviews(reviews_data: list[dict]) -> list[Review]:
    # batch_size prevents memory issues with large inserts
    reviews = [Review(**data) for data in reviews_data]
    return Review.objects.bulk_create(reviews, batch_size=500)
```

## Summary and Key Takeaways

- Use **`select_related`** for ForeignKey/OneToOne (SQL JOIN) and **`prefetch_related`** for ManyToMany/reverse FK (separate query)
- **Custom `Prefetch` objects** with filtered querysets and `to_attr` give precise control over what gets loaded
- **Annotations** (`Count`, `Avg`, `Sum`) push aggregation to the database, eliminating N+1 for computed values
- **`.only()` and `.defer()`** reduce memory by skipping large text/binary columns
- A **common mistake** is using `select_related` on ManyToMany fields — Django silently ignores it, giving you N+1 anyway
- **Window functions** (`DenseRank`, `RowNumber`) handle ranking without self-joins
- Use raw SQL only as a last resort, always with parameterized queries to prevent injection
- **QueryCountMiddleware** in development catches N+1 patterns before they reach production"""
    ),
    (
        "python-web/async-python-patterns-concurrency",
        "Explain advanced async Python patterns including structured concurrency with TaskGroups, cancellation and timeout handling, async iterators and generators, semaphore-based rate limiting, and event-driven architectures with asyncio",
        r"""# Advanced Async Python Patterns and Structured Concurrency

## Why Structured Concurrency Matters

Traditional `asyncio.create_task()` creates "fire-and-forget" tasks that can silently fail or outlive their parent scope. **Structured concurrency** — enforced through `TaskGroup` (Python 3.11+) — ensures that all spawned tasks complete (or are cancelled) before the enclosing scope exits. This is critical **because** leaked tasks are one of the most common sources of resource leaks and debugging nightmares in async applications.

### TaskGroups and Exception Handling

```python
import asyncio
from asyncio import TaskGroup
from contextlib import asynccontextmanager
from typing import AsyncIterator, AsyncGenerator, TypeVar, Callable, Any
from dataclasses import dataclass, field
from collections.abc import Awaitable
import time
import logging

logger = logging.getLogger(__name__)
T = TypeVar("T")

# --- Structured concurrency with TaskGroup ---

@dataclass
class FetchResult:
    url: str
    status: int
    body: str
    elapsed_ms: float

async def fetch_url(url: str, timeout: float = 10.0) -> FetchResult:
    # Simulated HTTP fetch
    start = time.monotonic()
    await asyncio.sleep(0.1)  # Simulate network latency
    elapsed = (time.monotonic() - start) * 1000
    return FetchResult(url=url, status=200, body=f"Content of {url}", elapsed_ms=elapsed)

async def fetch_all_structured(urls: list[str]) -> list[FetchResult]:
    # Best practice: use TaskGroup for parallel fetches
    # All tasks are guaranteed to complete or be cancelled
    results: list[FetchResult] = []

    async with TaskGroup() as tg:
        async def fetch_and_collect(url: str):
            result = await fetch_url(url)
            results.append(result)

        for url in urls:
            tg.create_task(fetch_and_collect(url))

    # This line only runs if ALL tasks succeeded
    # If any task raises, ALL others are cancelled and
    # an ExceptionGroup is raised
    return results

async def fetch_with_partial_failure(urls: list[str]) -> tuple[list[FetchResult], list[Exception]]:
    # However, sometimes you want to tolerate partial failures
    # Trade-off: more complex error handling vs resilience
    results: list[FetchResult] = []
    errors: list[Exception] = []

    async with TaskGroup() as tg:
        async def safe_fetch(url: str):
            try:
                result = await fetch_url(url)
                results.append(result)
            except Exception as e:
                # Catch per-task errors instead of failing the group
                errors.append(e)
                logger.warning("Failed to fetch %s: %s", url, e)

        for url in urls:
            tg.create_task(safe_fetch(url))

    return results, errors
```

### Cancellation, Timeouts, and Shielding

The **trade-off** with cancellation is between responsiveness and cleanup guarantees. When a task is cancelled, Python raises `CancelledError` at the next `await` point. **Therefore**, any cleanup code must itself be cancellation-safe, or you need `asyncio.shield()`.

```python
# --- Timeout patterns ---

async def fetch_with_timeout(url: str, timeout: float) -> FetchResult:
    # asyncio.timeout is preferred over wait_for in Python 3.11+
    # because it uses structured cancellation
    try:
        async with asyncio.timeout(timeout):
            return await fetch_url(url)
    except TimeoutError:
        logger.warning("Timeout fetching %s after %.1fs", url, timeout)
        raise

# --- Cascading timeouts ---

async def fetch_with_cascading_timeout(
    urls: list[str],
    per_url_timeout: float = 5.0,
    total_timeout: float = 30.0,
) -> list[FetchResult]:
    # Outer timeout caps total time, inner caps per-URL
    # Common mistake: only setting outer timeout, allowing
    # one slow URL to consume the entire budget
    results: list[FetchResult] = []
    try:
        async with asyncio.timeout(total_timeout):
            async with TaskGroup() as tg:
                async def bounded_fetch(url: str):
                    try:
                        async with asyncio.timeout(per_url_timeout):
                            result = await fetch_url(url)
                            results.append(result)
                    except TimeoutError:
                        logger.warning("Individual timeout: %s", url)
                for url in urls:
                    tg.create_task(bounded_fetch(url))
    except TimeoutError:
        logger.error("Total timeout exceeded with %d/%d complete", len(results), len(urls))
    except* TimeoutError:
        logger.error("Multiple timeouts in task group")
    return results

# --- Shield pattern for critical cleanup ---

async def process_payment(payment_id: str) -> dict:
    await asyncio.sleep(0.5)  # Simulate payment API
    return {"payment_id": payment_id, "status": "completed"}

async def save_payment_record(record: dict) -> None:
    await asyncio.sleep(0.1)  # Simulate DB write
    logger.info("Payment record saved: %s", record["payment_id"])

async def handle_payment(payment_id: str) -> dict:
    # Shield the DB write from cancellation
    # Pitfall: shield only prevents CancelledError propagation,
    # the shielded coroutine still runs but its result may be lost
    result = await process_payment(payment_id)
    try:
        await asyncio.shield(save_payment_record(result))
    except asyncio.CancelledError:
        # The save is still running, but we got cancelled
        logger.warning("Cancelled during save, record may still persist")
        raise
    return result
```

### Async Iterators and Generators

Async iterators enable **streaming data processing** without loading everything into memory. This is the **best practice** for handling large datasets, real-time event streams, or paginated API responses.

```python
# --- Async iterator for paginated API ---

@dataclass
class Page:
    items: list[dict]
    next_cursor: str | None

class PaginatedFetcher:
    # Async iterator protocol for paginated APIs
    def __init__(self, base_url: str, page_size: int = 100):
        self.base_url = base_url
        self.page_size = page_size
        self._cursor: str | None = "start"

    def __aiter__(self):
        return self

    async def __anext__(self) -> list[dict]:
        if self._cursor is None:
            raise StopAsyncIteration
        # Simulate paginated API call
        await asyncio.sleep(0.05)
        items = [{"id": i, "data": f"item-{i}"} for i in range(self.page_size)]
        self._cursor = None  # Simulate last page
        return items

# --- Async generator for streaming transforms ---

async def stream_transform(
    source: AsyncIterator[list[dict]],
    transform: Callable[[dict], Awaitable[dict]],
    concurrency: int = 10,
) -> AsyncGenerator[dict, None]:
    # Semaphore-based concurrency control
    # Therefore, we process items in parallel but limit resource usage
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded_transform(item: dict) -> dict:
        async with semaphore:
            return await transform(item)

    async for batch in source:
        tasks = [bounded_transform(item) for item in batch]
        for coro in asyncio.as_completed(tasks):
            yield await coro

# --- Event-driven architecture with asyncio ---

@dataclass
class Event:
    type: str
    payload: dict
    timestamp: float = field(default_factory=time.time)

class AsyncEventBus:
    # Pub/sub with typed event handlers and backpressure
    def __init__(self, max_queue_size: int = 1000):
        self._handlers: dict[str, list[Callable]] = {}
        self._queue: asyncio.Queue[Event | None] = asyncio.Queue(
            maxsize=max_queue_size
        )
        self._running = False
        self._worker_task: asyncio.Task | None = None

    def subscribe(self, event_type: str, handler: Callable) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    async def publish(self, event: Event) -> None:
        # Backpressure: blocks if queue is full
        # This is a trade-off: prevents memory exhaustion but
        # can slow down publishers
        await self._queue.put(event)

    async def start(self) -> None:
        self._running = True
        self._worker_task = asyncio.create_task(self._process_events())

    async def stop(self) -> None:
        self._running = False
        await self._queue.put(None)  # Sentinel to unblock
        if self._worker_task:
            await self._worker_task

    async def _process_events(self) -> None:
        while self._running:
            event = await self._queue.get()
            if event is None:
                break
            handlers = self._handlers.get(event.type, [])
            if handlers:
                # Run handlers concurrently with error isolation
                async with TaskGroup() as tg:
                    for handler in handlers:
                        async def safe_handle(h=handler, e=event):
                            try:
                                await h(e)
                            except Exception as exc:
                                logger.error(
                                    "Handler %s failed for %s: %s",
                                    h.__name__, e.type, exc,
                                )
                        tg.create_task(safe_handle())

# --- Rate-limited async worker pool ---

class RateLimitedPool:
    # Process items with concurrency AND rate limits
    def __init__(self, concurrency: int = 10, rate_per_second: float = 50.0):
        self._semaphore = asyncio.Semaphore(concurrency)
        self._interval = 1.0 / rate_per_second
        self._last_call = 0.0
        self._lock = asyncio.Lock()

    async def _wait_for_rate(self) -> None:
        async with self._lock:
            now = time.monotonic()
            wait = self._last_call + self._interval - now
            if wait > 0:
                await asyncio.sleep(wait)
            self._last_call = time.monotonic()

    async def submit(self, coro: Awaitable[T]) -> T:
        async with self._semaphore:
            await self._wait_for_rate()
            return await coro

    async def map(
        self, func: Callable[..., Awaitable[T]], items: list
    ) -> list[T]:
        async with TaskGroup() as tg:
            tasks = []
            for item in items:
                task = tg.create_task(self.submit(func(item)))
                tasks.append(task)
        return [t.result() for t in tasks]
```

## Summary and Key Takeaways

- **`TaskGroup`** (Python 3.11+) enforces structured concurrency — all child tasks complete before the scope exits, preventing leaked coroutines
- **`except*`** (ExceptionGroup handling) lets you catch specific exceptions from multiple concurrent failures
- A **common mistake** is using `asyncio.create_task()` without storing the reference — the task can be garbage collected
- **Cascading timeouts** (total + per-item) prevent one slow operation from consuming the entire budget
- **`asyncio.shield()`** protects critical operations from cancellation but the **pitfall** is that the shielded result may be silently lost
- **Async generators** with semaphore-based concurrency enable streaming processing with backpressure
- For **event-driven patterns**, use `asyncio.Queue` with bounded size to provide natural backpressure"""
    ),
    (
        "python-web/fastapi-testing-strategies",
        "Describe comprehensive FastAPI testing strategies including async test fixtures, database transaction rollback isolation, mocking external services, testing WebSocket endpoints, load testing with locust, and contract testing patterns",
        r"""# Comprehensive FastAPI Testing Strategies

## Test Architecture Overview

Testing FastAPI applications requires a layered strategy **because** different test types catch different classes of bugs. Unit tests validate business logic in isolation, integration tests verify database interactions and dependency wiring, and contract tests ensure API compatibility. **Therefore**, a well-structured test suite uses all three levels with appropriate isolation mechanisms.

### Async Test Fixtures and Database Isolation

```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect
from fastapi.testclient import TestClient
from typing import AsyncGenerator, Any
from dataclasses import dataclass, field
from unittest.mock import AsyncMock, patch, MagicMock
from contextlib import asynccontextmanager
import asyncio
import json

# --- Application under test ---

app = FastAPI()

@dataclass
class DBSession:
    committed: bool = False
    rolled_back: bool = False
    queries: list = field(default_factory=list)

    async def execute(self, query: str, params: dict = None) -> list:
        self.queries.append((query, params))
        return [{"id": 1, "name": "test"}]

    async def commit(self):
        self.committed = True

    async def rollback(self):
        self.rolled_back = True

@dataclass
class User:
    id: int
    name: str
    email: str

# --- Fixtures with transaction rollback ---

@pytest_asyncio.fixture
async def db_session() -> AsyncGenerator[DBSession, None]:
    # Best practice: wrap each test in a transaction and roll back
    # This ensures test isolation without slow DB recreations
    session = DBSession()
    yield session
    # Rollback ensures no test data persists
    if not session.committed:
        await session.rollback()

@pytest_asyncio.fixture
async def async_client(db_session: DBSession) -> AsyncGenerator[AsyncClient, None]:
    # Override dependencies for testing
    async def override_db():
        yield db_session

    app.dependency_overrides[lambda: None] = override_db

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()

# --- Unit tests for business logic ---

class UserService:
    def __init__(self, db: DBSession):
        self.db = db

    async def create_user(self, name: str, email: str) -> User:
        if not email or "@" not in email:
            raise ValueError("Invalid email format")
        results = await self.db.execute(
            "INSERT INTO users (name, email) VALUES (:name, :email) RETURNING id",
            {"name": name, "email": email},
        )
        return User(id=results[0]["id"], name=name, email=email)

    async def get_user(self, user_id: int) -> User | None:
        results = await self.db.execute(
            "SELECT id, name, email FROM users WHERE id = :id",
            {"id": user_id},
        )
        if not results:
            return None
        row = results[0]
        return User(id=row["id"], name=row.get("name", ""), email=row.get("email", ""))

@pytest.mark.asyncio
async def test_create_user_validates_email(db_session: DBSession):
    service = UserService(db_session)
    with pytest.raises(ValueError, match="Invalid email"):
        await service.create_user("Alice", "not-an-email")

@pytest.mark.asyncio
async def test_create_user_success(db_session: DBSession):
    service = UserService(db_session)
    user = await service.create_user("Alice", "alice@example.com")
    assert user.name == "Alice"
    assert user.email == "alice@example.com"
    assert len(db_session.queries) == 1
```

### Mocking External Services

The **trade-off** with mocking is fidelity vs speed. Mocks run instantly but can mask integration issues. **However**, for external APIs (payment gateways, email services), mocking is essential because you cannot call production APIs in tests.

```python
# --- External service mocking ---

class PaymentGateway:
    # External service client
    def __init__(self, api_key: str, base_url: str = "https://api.stripe.com"):
        self.api_key = api_key
        self.base_url = base_url

    async def charge(self, amount: int, currency: str, token: str) -> dict:
        # In production, this calls Stripe API
        raise NotImplementedError("Must be mocked in tests")

    async def refund(self, charge_id: str, amount: int | None = None) -> dict:
        raise NotImplementedError("Must be mocked in tests")

class OrderService:
    def __init__(self, db: DBSession, payment: PaymentGateway):
        self.db = db
        self.payment = payment

    async def place_order(
        self, user_id: int, items: list[dict], payment_token: str
    ) -> dict:
        total = sum(item["price"] * item["quantity"] for item in items)
        # Charge payment
        charge = await self.payment.charge(
            amount=total, currency="usd", token=payment_token
        )
        if charge.get("status") != "succeeded":
            raise ValueError(f"Payment failed: {charge.get('error', 'unknown')}")
        # Save order
        await self.db.execute(
            "INSERT INTO orders (user_id, total, charge_id) VALUES (:uid, :total, :cid)",
            {"uid": user_id, "total": total, "cid": charge["id"]},
        )
        return {"order_id": 1, "total": total, "charge_id": charge["id"]}

@pytest.mark.asyncio
async def test_place_order_success(db_session: DBSession):
    # Common mistake: mocking too broadly (e.g., entire service)
    # Best practice: mock only the external boundary
    mock_payment = AsyncMock(spec=PaymentGateway)
    mock_payment.charge.return_value = {
        "id": "ch_test123",
        "status": "succeeded",
        "amount": 5000,
    }

    service = OrderService(db_session, mock_payment)
    result = await service.place_order(
        user_id=1,
        items=[{"price": 2500, "quantity": 2}],
        payment_token="tok_visa",
    )

    assert result["charge_id"] == "ch_test123"
    assert result["total"] == 5000
    mock_payment.charge.assert_called_once_with(
        amount=5000, currency="usd", token="tok_visa"
    )

@pytest.mark.asyncio
async def test_place_order_payment_failure(db_session: DBSession):
    mock_payment = AsyncMock(spec=PaymentGateway)
    mock_payment.charge.return_value = {
        "status": "failed",
        "error": "card_declined",
    }

    service = OrderService(db_session, mock_payment)
    with pytest.raises(ValueError, match="Payment failed"):
        await service.place_order(
            user_id=1,
            items=[{"price": 1000, "quantity": 1}],
            payment_token="tok_declined",
        )

# --- WebSocket testing ---

@app.websocket("/ws/chat/{room_id}")
async def websocket_chat(websocket: WebSocket, room_id: str):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            # Echo with metadata
            await websocket.send_json({
                "room": room_id,
                "message": data.get("message", ""),
                "echo": True,
            })
    except WebSocketDisconnect:
        pass

def test_websocket_chat():
    # Pitfall: WebSocket tests need TestClient, not AsyncClient
    client = TestClient(app)
    with client.websocket_connect("/ws/chat/room-1") as ws:
        ws.send_json({"message": "hello"})
        response = ws.receive_json()
        assert response["room"] == "room-1"
        assert response["message"] == "hello"
        assert response["echo"] is True
```

### Contract Testing and Schema Validation

Contract tests ensure your API doesn't accidentally break clients. **Therefore**, they validate response shapes against a fixed schema, catching unintentional breaking changes that integration tests might miss.

```python
# --- Contract testing with schema snapshots ---

from pydantic import BaseModel
from typing import Optional

class UserResponse(BaseModel):
    id: int
    name: str
    email: str
    is_active: bool = True

class PaginatedResponse(BaseModel):
    items: list[UserResponse]
    total: int
    page: int
    per_page: int
    has_next: bool

@app.get("/api/users", response_model=PaginatedResponse)
async def list_users(page: int = 1, per_page: int = 20):
    return PaginatedResponse(
        items=[UserResponse(id=1, name="Alice", email="alice@test.com")],
        total=1, page=page, per_page=per_page, has_next=False,
    )

def test_user_list_contract():
    # Contract test: validate response schema matches expectation
    client = TestClient(app)
    response = client.get("/api/users?page=1&per_page=10")
    assert response.status_code == 200

    data = response.json()
    # Validate required fields exist with correct types
    assert isinstance(data["items"], list)
    assert isinstance(data["total"], int)
    assert isinstance(data["page"], int)
    assert isinstance(data["has_next"], bool)

    if data["items"]:
        user = data["items"][0]
        assert "id" in user
        assert "name" in user
        assert "email" in user
        # Ensure no extra fields leaked (PII, internal IDs)
        allowed_fields = {"id", "name", "email", "is_active"}
        assert set(user.keys()).issubset(allowed_fields)

def test_openapi_schema_stability():
    # Best practice: snapshot the OpenAPI schema to detect breaking changes
    client = TestClient(app)
    response = client.get("/openapi.json")
    schema = response.json()

    # Verify key paths exist
    assert "/api/users" in schema["paths"]
    user_get = schema["paths"]["/api/users"]["get"]
    assert user_get["responses"]["200"] is not None

    # Check response schema reference exists
    # This catches model renames or deletions
    components = schema.get("components", {}).get("schemas", {})
    assert "PaginatedResponse" in components
    assert "UserResponse" in components

# --- Performance testing setup with locust ---

# locustfile.py (separate file)
LOCUST_CONFIG = '''
from locust import HttpUser, task, between

class APIUser(HttpUser):
    wait_time = between(0.5, 2.0)

    @task(3)
    def list_users(self):
        self.client.get("/api/users?page=1")

    @task(1)
    def get_user(self):
        self.client.get("/api/users/1")

    def on_start(self):
        # Login and store token
        response = self.client.post("/auth/login", json={
            "email": "load-test@example.com",
            "password": "test-password",
        })
        if response.status_code == 200:
            token = response.json()["access_token"]
            self.client.headers.update({
                "Authorization": f"Bearer {token}"
            })
'''
```

## Summary and Key Takeaways

- **Transaction rollback** in fixtures provides fast, reliable test isolation without recreating the database
- Use **`AsyncClient` with `ASGITransport`** for async endpoint tests, **`TestClient`** for sync and WebSocket tests
- **Mock external services** at the client boundary, not at the HTTP level — use `AsyncMock(spec=...)` for type safety
- A **common mistake** is sharing state between tests via module-level variables — always use fixtures
- **Contract tests** validate response schemas against snapshots to catch breaking API changes
- The **pitfall** of over-mocking is that tests pass but production breaks — keep an integration test suite that hits real dependencies
- **Load testing** with locust should mirror real traffic patterns with weighted task distributions"""
    ),
    (
        "python-web/celery-task-queue-patterns",
        "Explain production Celery task queue patterns including task design principles, retry strategies with exponential backoff, task chaining and chord workflows, result backend optimization, monitoring with Flower, and dead letter queue handling",
        r"""# Production Celery Task Queue Patterns

## Task Design Principles

Celery tasks are the backbone of async processing in Python web applications, but poorly designed tasks cause cascading failures. The first principle is **idempotency**: every task must produce the same result if executed multiple times with the same arguments. This is critical **because** Celery guarantees at-least-once delivery — network issues, worker crashes, or visibility timeouts can all cause re-execution.

### Core Task Patterns

```python
from celery import Celery, Task, chain, chord, group, signature
from celery.exceptions import MaxRetriesExceededError, Reject
from celery.utils.log import get_task_logger
from celery.signals import task_failure, task_success, worker_ready
from typing import Any, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps
import json
import time
import hashlib

logger = get_task_logger(__name__)

app = Celery("tasks")
app.config_from_object({
    "broker_url": "redis://localhost:6379/0",
    "result_backend": "redis://localhost:6379/1",
    "task_serializer": "json",
    "result_serializer": "json",
    "accept_content": ["json"],
    "task_track_started": True,
    "task_time_limit": 300,        # Hard kill after 5 min
    "task_soft_time_limit": 240,   # SoftTimeLimitExceeded after 4 min
    "worker_prefetch_multiplier": 1,  # Fair scheduling
    "task_acks_late": True,        # Ack after completion, not receipt
    "task_reject_on_worker_lost": True,
    "result_expires": 3600,        # Clean results after 1 hour
    "broker_transport_options": {
        "visibility_timeout": 600,  # Must be > task_time_limit
    },
})

# --- Idempotency key pattern ---

class IdempotentTask(Task):
    # Base class ensuring at-most-once execution semantics
    # Best practice: use a deduplication key based on task args
    abstract = True
    _redis = None

    @property
    def redis(self):
        if self._redis is None:
            import redis
            self._redis = redis.Redis.from_url("redis://localhost:6379/2")
        return self._redis

    def get_idempotency_key(self, *args: Any, **kwargs: Any) -> str:
        # Hash the task name + arguments for dedup key
        key_data = json.dumps({"task": self.name, "args": args, "kwargs": kwargs}, sort_keys=True)
        return f"idemp:{hashlib.sha256(key_data.encode()).hexdigest()}"

    def before_start(self, task_id: str, args: tuple, kwargs: dict) -> None:
        key = self.get_idempotency_key(*args, **kwargs)
        # SET NX with TTL — only first execution proceeds
        if not self.redis.set(key, task_id, nx=True, ex=3600):
            existing = self.redis.get(key)
            logger.info(
                "Task %s already processed by %s, skipping",
                task_id, existing,
            )
            raise Reject("Duplicate task", requeue=False)

# --- Retry strategies ---

@app.task(
    bind=True,
    base=IdempotentTask,
    max_retries=5,
    default_retry_delay=10,
    retry_backoff=True,        # Exponential backoff
    retry_backoff_max=600,     # Cap at 10 minutes
    retry_jitter=True,         # Add randomness to prevent thundering herd
)
def send_notification(self, user_id: int, message: str, channel: str = "email") -> dict:
    # Trade-off: retry_jitter adds randomness (0-100% of delay)
    # which prevents all retries hitting the service simultaneously
    try:
        # Simulate external API call
        result = _call_notification_api(user_id, message, channel)
        return {"status": "sent", "user_id": user_id, "channel": channel}
    except ConnectionError as exc:
        # Transient error — retry with backoff
        logger.warning("Notification API connection error, retrying: %s", exc)
        raise self.retry(exc=exc)
    except ValueError as exc:
        # Permanent error — don't retry, send to dead letter
        logger.error("Invalid notification data: %s", exc)
        _send_to_dead_letter(self, exc, user_id=user_id, message=message)
        raise Reject(str(exc), requeue=False)
    except Exception as exc:
        # Unknown error — retry but with shorter limit
        try:
            raise self.retry(exc=exc, max_retries=2)
        except MaxRetriesExceededError:
            _send_to_dead_letter(self, exc, user_id=user_id, message=message)
            raise

def _call_notification_api(user_id: int, message: str, channel: str) -> dict:
    # Placeholder for actual API call
    return {"delivered": True}

def _send_to_dead_letter(task: Task, exc: Exception, **context: Any) -> None:
    # Common mistake: silently dropping failed tasks
    # Best practice: persist failures for later analysis/replay
    dead_letter = {
        "task_name": task.name,
        "task_id": task.request.id,
        "exception": str(exc),
        "exception_type": type(exc).__name__,
        "context": context,
        "timestamp": datetime.utcnow().isoformat(),
        "retries": task.request.retries,
    }
    # Store in Redis list for dead letter processing
    import redis
    r = redis.Redis.from_url("redis://localhost:6379/2")
    r.lpush("dead_letters", json.dumps(dead_letter))
    logger.error("Task sent to dead letter queue: %s", dead_letter)
```

### Task Chaining and Chord Workflows

Celery's **canvas primitives** — `chain`, `group`, `chord` — enable complex workflows. **However**, the **pitfall** is that error handling in canvas workflows is non-obvious: a failing task in a chain stops the entire chain, while a failing task in a chord prevents the callback from executing.

```python
# --- Workflow patterns ---

@app.task(bind=True, max_retries=3, retry_backoff=True)
def extract_data(self, source_url: str) -> dict:
    # Step 1: Download and parse data
    logger.info("Extracting data from %s", source_url)
    return {"source": source_url, "records": 1000, "raw_path": "/tmp/raw.json"}

@app.task(bind=True, max_retries=3, retry_backoff=True)
def transform_data(self, extracted: dict) -> dict:
    # Step 2: Clean and transform
    logger.info("Transforming %d records", extracted["records"])
    return {
        "source": extracted["source"],
        "records": extracted["records"],
        "clean_path": "/tmp/clean.json",
        "errors": 5,
    }

@app.task(bind=True, max_retries=3, retry_backoff=True)
def load_data(self, transformed: dict) -> dict:
    # Step 3: Load into destination
    logger.info("Loading %d records", transformed["records"])
    return {
        "loaded": transformed["records"] - transformed["errors"],
        "errors": transformed["errors"],
    }

@app.task
def aggregate_results(results: list[dict]) -> dict:
    # Chord callback — runs after all parallel tasks complete
    total_loaded = sum(r.get("loaded", 0) for r in results)
    total_errors = sum(r.get("errors", 0) for r in results)
    logger.info("Pipeline complete: %d loaded, %d errors", total_loaded, total_errors)
    return {"total_loaded": total_loaded, "total_errors": total_errors}

@app.task
def send_pipeline_report(result: dict) -> None:
    logger.info("Sending pipeline report: %s", result)

def run_etl_pipeline(sources: list[str]) -> None:
    # Chain: sequential steps for each source
    # Group: parallel execution across sources
    # Chord: group + callback when all complete
    # Therefore, we get parallel ETL with aggregation

    if len(sources) == 1:
        # Simple chain for single source
        workflow = chain(
            extract_data.s(sources[0]),
            transform_data.s(),
            load_data.s(),
            send_pipeline_report.s(),
        )
    else:
        # Chord for parallel sources with aggregation
        parallel_pipelines = group(
            chain(
                extract_data.s(source),
                transform_data.s(),
                load_data.s(),
            )
            for source in sources
        )
        workflow = chord(parallel_pipelines)(
            aggregate_results.s() | send_pipeline_report.s()
        )

    workflow.apply_async()

# --- Task routing and priority queues ---

app.conf.task_routes = {
    "tasks.send_notification": {"queue": "notifications"},
    "tasks.extract_data": {"queue": "etl"},
    "tasks.transform_data": {"queue": "etl"},
    "tasks.load_data": {"queue": "etl"},
    "tasks.aggregate_results": {"queue": "default"},
}

# Priority queues (Redis broker supports 0-9, lower = higher priority)
app.conf.broker_transport_options = {
    "priority_steps": list(range(10)),
    "queue_order_strategy": "priority",
}

@app.task(bind=True, priority=0)  # Highest priority
def critical_payment_task(self, payment_id: str) -> dict:
    return {"payment_id": payment_id, "status": "processed"}

@app.task(bind=True, priority=5)  # Normal priority
def send_marketing_email(self, campaign_id: str, user_ids: list[int]) -> dict:
    return {"campaign_id": campaign_id, "sent": len(user_ids)}

# --- Monitoring and signals ---

@task_failure.connect
def handle_task_failure(sender: Task, task_id: str, exception: Exception, **kwargs: Any) -> None:
    # Pitfall: this signal fires for EVERY failure, including retries
    # Check if retries are exhausted before alerting
    if sender.request.retries >= sender.max_retries:
        logger.critical(
            "ALERT: Task %s permanently failed after %d retries: %s",
            sender.name, sender.request.retries, exception,
        )

@task_success.connect
def handle_task_success(sender: Task, result: Any, **kwargs: Any) -> None:
    # Track task duration for monitoring
    runtime = sender.request.delivery_info.get("routing_key", "unknown")
    logger.info("Task %s completed on queue %s", sender.name, runtime)

# --- Dead letter queue processor ---

@app.task
def process_dead_letters(batch_size: int = 100) -> dict:
    # Periodically process failed tasks for retry or alerting
    import redis
    r = redis.Redis.from_url("redis://localhost:6379/2")
    processed = 0
    retried = 0
    discarded = 0

    for _ in range(batch_size):
        raw = r.rpop("dead_letters")
        if raw is None:
            break
        letter = json.loads(raw)
        processed += 1

        # Decide: retry, discard, or escalate
        age = datetime.utcnow() - datetime.fromisoformat(letter["timestamp"])
        if age > timedelta(hours=24):
            discarded += 1
            logger.info("Discarding old dead letter: %s", letter["task_id"])
        elif letter["retries"] < 10:
            # Re-queue with delay
            task = app.signature(letter["task_name"])
            task.apply_async(
                kwargs=letter["context"],
                countdown=300,
            )
            retried += 1

    return {"processed": processed, "retried": retried, "discarded": discarded}

# Schedule dead letter processing every 15 minutes
app.conf.beat_schedule = {
    "process-dead-letters": {
        "task": "tasks.process_dead_letters",
        "schedule": 900.0,
        "kwargs": {"batch_size": 200},
    },
}
```

## Summary and Key Takeaways

- **Idempotency** is non-negotiable — use deduplication keys with Redis SET NX to ensure at-most-once execution
- Enable **`task_acks_late=True`** with **`task_reject_on_worker_lost=True`** so tasks survive worker crashes
- A **common mistake** is setting `visibility_timeout` shorter than `task_time_limit` — this causes tasks to be re-delivered while still running
- **Exponential backoff with jitter** (`retry_backoff=True, retry_jitter=True`) prevents thundering herd on transient failures
- Use **chord** for fan-out/fan-in patterns, but beware that any task failure in the group blocks the callback
- **Dead letter queues** catch permanently failed tasks — never silently drop failures
- **Task routing** with dedicated queues prevents slow ETL jobs from blocking critical notification delivery
- The **trade-off** of `worker_prefetch_multiplier=1` is lower throughput but fairer scheduling across workers"""
    ),
]
