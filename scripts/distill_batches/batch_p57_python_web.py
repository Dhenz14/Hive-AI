"""Python web — FastAPI advanced, Pydantic v2, and ASGI patterns."""

PAIRS = [
    (
        "python/pydantic-v2",
        "Show Pydantic v2 patterns: models, validators, serialization, generic models, and discriminated unions.",
        '''Pydantic v2 patterns:

```python
from pydantic import (
    BaseModel, Field, field_validator, model_validator,
    ConfigDict, computed_field, field_serializer,
    TypeAdapter, ValidationError,
)
from typing import Annotated, Literal, Union, Optional
from datetime import datetime, timezone
from enum import Enum
import re


# --- Basic model with validation ---

class UserCreate(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        str_min_length=1,
    )

    email: str = Field(pattern=r'^[\w.+-]+@[\w-]+\.[\w.]+$')
    name: str = Field(min_length=2, max_length=100)
    age: int = Field(ge=13, le=150)
    tags: list[str] = Field(default_factory=list, max_length=10)
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator('email')
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return v.lower()

    @field_validator('tags')
    @classmethod
    def unique_tags(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(v))  # Deduplicate preserving order

    @model_validator(mode='after')
    def check_consistency(self) -> 'UserCreate':
        if self.age < 18 and 'adult' in self.tags:
            raise ValueError('Cannot tag as adult if under 18')
        return self


# --- Computed fields ---

class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    name: str
    created_at: datetime

    @computed_field
    @property
    def display_name(self) -> str:
        return self.name.title()

    @computed_field
    @property
    def is_recent(self) -> bool:
        delta = datetime.now(timezone.utc) - self.created_at
        return delta.days < 30

    @field_serializer('created_at')
    def serialize_dt(self, dt: datetime) -> str:
        return dt.isoformat()


# --- Discriminated unions ---

class EmailNotification(BaseModel):
    type: Literal['email'] = 'email'
    to: str
    subject: str
    body: str

class PushNotification(BaseModel):
    type: Literal['push'] = 'push'
    device_token: str
    title: str
    body: str
    data: dict = Field(default_factory=dict)

class SMSNotification(BaseModel):
    type: Literal['sms'] = 'sms'
    phone: str = Field(pattern=r'^\+\d{10,15}$')
    message: str = Field(max_length=160)

# Discriminated union: type field determines which model to use
Notification = Annotated[
    Union[EmailNotification, PushNotification, SMSNotification],
    Field(discriminator='type'),
]

class NotificationRequest(BaseModel):
    notifications: list[Notification]

# Validates correctly:
# NotificationRequest(notifications=[
#     {"type": "email", "to": "a@b.com", "subject": "Hi", "body": "Hello"},
#     {"type": "push", "device_token": "abc", "title": "Hi", "body": "Hello"},
# ])


# --- Generic models ---

from typing import Generic, TypeVar
T = TypeVar('T')

class PaginatedResponse(BaseModel, Generic[T]):
    data: list[T]
    total: int
    page: int
    per_page: int
    has_next: bool

    @computed_field
    @property
    def total_pages(self) -> int:
        return (self.total + self.per_page - 1) // self.per_page

# Type-safe:
# PaginatedResponse[UserResponse](data=[...], total=100, page=1, per_page=20, has_next=True)


# --- TypeAdapter for non-model validation ---

IntList = TypeAdapter(list[int])
validated = IntList.validate_python(["1", "2", "3"])  # [1, 2, 3]
json_bytes = IntList.dump_json(validated)               # b'[1,2,3]'

DateAdapter = TypeAdapter(datetime)
dt = DateAdapter.validate_python("2024-01-15T10:30:00Z")


# --- Nested model updates (partial) ---

class Address(BaseModel):
    street: str
    city: str
    state: str
    zip_code: str

class UserUpdate(BaseModel):
    """All fields optional for PATCH updates."""
    name: Optional[str] = None
    email: Optional[str] = None
    address: Optional[Address] = None

def apply_update(user: dict, update: UserUpdate) -> dict:
    """Apply partial update, only changing provided fields."""
    update_data = update.model_dump(exclude_unset=True)
    return {**user, **update_data}
```

Pydantic v2 patterns:
1. **`model_config`** — class-level settings (strip whitespace, from_attributes)
2. **`field_validator`** — validate/transform individual fields
3. **`computed_field`** — derived fields included in serialization
4. **Discriminated unions** — `type` field selects correct model for validation
5. **`exclude_unset=True`** — distinguish between None and not-provided for PATCH'''
    ),
    (
        "python/fastapi-production",
        "Show production FastAPI patterns: dependency injection, background tasks, streaming, and structured responses.",
        '''Production FastAPI patterns:

```python
from fastapi import FastAPI, Depends, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from typing import Annotated, AsyncGenerator
import asyncpg
import logging

logger = logging.getLogger(__name__)


# --- Lifespan (startup/shutdown) ---

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.db_pool = await asyncpg.create_pool(
        dsn="postgresql://user:pass@localhost/db",
        min_size=5, max_size=20,
    )
    app.state.redis = await create_redis_pool()
    logger.info("Application started")

    yield  # Application runs

    # Shutdown
    await app.state.db_pool.close()
    await app.state.redis.close()
    logger.info("Application stopped")

app = FastAPI(lifespan=lifespan)


# --- Dependency injection ---

async def get_db(request: Request) -> AsyncGenerator[asyncpg.Connection, None]:
    async with request.app.state.db_pool.acquire() as conn:
        yield conn

async def get_current_user(request: Request) -> User:
    token = request.headers.get("Authorization", "").replace("Bearer ", "")
    if not token:
        raise HTTPException(401, "Missing token")
    user = await verify_token(token)
    if not user:
        raise HTTPException(401, "Invalid token")
    return user

async def require_admin(user: Annotated[User, Depends(get_current_user)]) -> User:
    if user.role != "admin":
        raise HTTPException(403, "Admin required")
    return user

DB = Annotated[asyncpg.Connection, Depends(get_db)]
CurrentUser = Annotated[User, Depends(get_current_user)]
AdminUser = Annotated[User, Depends(require_admin)]


# --- Endpoints with proper typing ---

@app.get("/api/users/{user_id}", response_model=UserResponse)
async def get_user(user_id: str, db: DB, user: CurrentUser):
    row = await db.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    if not row:
        raise HTTPException(404, "User not found")
    return UserResponse.model_validate(dict(row))


@app.post("/api/users", response_model=UserResponse, status_code=201)
async def create_user(
    data: UserCreate,
    db: DB,
    background_tasks: BackgroundTasks,
    admin: AdminUser,
):
    user_id = await db.fetchval(
        "INSERT INTO users (email, name) VALUES ($1, $2) RETURNING id",
        data.email, data.name,
    )

    # Non-blocking background work
    background_tasks.add_task(send_welcome_email, data.email, data.name)
    background_tasks.add_task(track_event, "user_created", {"user_id": user_id})

    row = await db.fetchrow("SELECT * FROM users WHERE id = $1", user_id)
    return UserResponse.model_validate(dict(row))


# --- Streaming response ---

@app.get("/api/export/users")
async def export_users(db: DB, admin: AdminUser):
    async def generate():
        yield "id,email,name,created_at\n"
        async with db.transaction():
            async for record in db.cursor("SELECT * FROM users ORDER BY id"):
                yield f"{record['id']},{record['email']},{record['name']},{record['created_at']}\n"

    return StreamingResponse(
        generate(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=users.csv"},
    )


# --- Request validation middleware ---

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    import uuid
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id

    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


# --- Exception handlers ---

@app.exception_handler(ValueError)
async def value_error_handler(request: Request, exc: ValueError):
    return JSONResponse(
        status_code=422,
        content={
            "error": "validation_error",
            "message": str(exc),
            "request_id": getattr(request.state, 'request_id', ''),
        },
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error", extra={
        "request_id": getattr(request.state, 'request_id', ''),
        "path": request.url.path,
    })
    return JSONResponse(
        status_code=500,
        content={"error": "internal_error", "message": "Internal server error"},
    )
```

FastAPI production patterns:
1. **Lifespan** — manage DB pools, Redis connections on startup/shutdown
2. **`Annotated` dependencies** — type-safe DI with `DB = Annotated[..., Depends(...)]`
3. **BackgroundTasks** — non-blocking email, analytics without Celery
4. **StreamingResponse** — export large datasets without memory issues
5. **Request ID** — trace requests through logs and error responses'''
    ),
    (
        "python/webscraping",
        "Show web scraping patterns: httpx async, BeautifulSoup parsing, rate limiting, and retry logic.",
        '''Web scraping patterns:

```python
import httpx
from bs4 import BeautifulSoup
from dataclasses import dataclass, field
from typing import AsyncGenerator
import asyncio
import logging
import json
import time
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


@dataclass
class ScrapedPage:
    url: str
    title: str
    content: str
    links: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


class AsyncScraper:
    """Rate-limited async web scraper."""

    def __init__(self, max_concurrent: int = 5,
                 delay: float = 1.0, timeout: float = 30.0):
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.delay = delay
        self.timeout = timeout
        self._last_request: dict[str, float] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=self.timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; MyScraper/1.0)",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )

    async def _rate_limit(self, domain: str):
        """Per-domain rate limiting."""
        last = self._last_request.get(domain, 0)
        elapsed = time.time() - last
        if elapsed < self.delay:
            await asyncio.sleep(self.delay - elapsed)
        self._last_request[domain] = time.time()

    async def fetch(self, url: str, retries: int = 3) -> str | None:
        """Fetch URL with retry and rate limiting."""
        domain = urlparse(url).netloc

        async with self.semaphore:
            await self._rate_limit(domain)

            for attempt in range(retries):
                try:
                    async with await self._get_client() as client:
                        response = await client.get(url)
                        response.raise_for_status()
                        return response.text
                except httpx.HTTPStatusError as e:
                    if e.response.status_code == 429:
                        retry_after = int(e.response.headers.get("Retry-After", 60))
                        logger.warning("Rate limited, waiting %ds", retry_after)
                        await asyncio.sleep(retry_after)
                    elif e.response.status_code >= 500:
                        await asyncio.sleep(2 ** attempt)
                    else:
                        logger.error("HTTP %d for %s", e.response.status_code, url)
                        return None
                except (httpx.ConnectError, httpx.ReadTimeout) as e:
                    logger.warning("Attempt %d failed for %s: %s",
                                 attempt + 1, url, e)
                    await asyncio.sleep(2 ** attempt)

        return None

    def parse_page(self, url: str, html: str) -> ScrapedPage:
        """Parse HTML into structured data."""
        soup = BeautifulSoup(html, "html.parser")

        # Remove scripts and styles
        for tag in soup(["script", "style", "nav", "footer"]):
            tag.decompose()

        title = soup.title.string.strip() if soup.title else ""
        content = soup.get_text(separator="\n", strip=True)

        # Extract links
        links = []
        for a in soup.find_all("a", href=True):
            href = urljoin(url, a["href"])
            if urlparse(href).scheme in ("http", "https"):
                links.append(href)

        # Extract metadata
        metadata = {}
        for meta in soup.find_all("meta"):
            name = meta.get("name") or meta.get("property", "")
            content_attr = meta.get("content", "")
            if name and content_attr:
                metadata[name] = content_attr

        return ScrapedPage(
            url=url, title=title, content=content[:5000],
            links=list(set(links)), metadata=metadata,
        )

    async def scrape_pages(self, urls: list[str]) -> list[ScrapedPage]:
        """Scrape multiple pages concurrently."""
        async def scrape_one(url: str) -> ScrapedPage | None:
            html = await self.fetch(url)
            if html:
                return self.parse_page(url, html)
            return None

        tasks = [scrape_one(url) for url in urls]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]


# --- CSS selector extraction ---

def extract_products(html: str) -> list[dict]:
    """Extract product data from HTML."""
    soup = BeautifulSoup(html, "html.parser")
    products = []

    for card in soup.select(".product-card"):
        product = {
            "name": card.select_one(".product-name").get_text(strip=True),
            "price": card.select_one(".price").get_text(strip=True),
            "rating": card.select_one("[data-rating]")["data-rating"],
            "image": card.select_one("img")["src"],
            "link": card.select_one("a")["href"],
        }
        products.append(product)

    return products


# Usage:
# scraper = AsyncScraper(max_concurrent=3, delay=2.0)
# pages = await scraper.scrape_pages(urls)
```

Scraping patterns:
1. **Semaphore** — limit concurrent requests to avoid overwhelming servers
2. **Per-domain rate limiting** — respect each site independently
3. **Retry with backoff** — handle transient failures and 429s
4. **`urljoin`** — resolve relative URLs correctly
5. **Decompose noise** — remove script, style, nav before text extraction'''
    ),
]
"""
