PAIRS = [
    ("projects/rest-api", r'''<think>
Building a REST API with FastAPI requires proper project structure.
I need to set up the app factory pattern, include routers, middleware,
and configure CORS. Using Pydantic models for request/response validation.
</think>
Build a REST API with FastAPI: set up the application factory, include routers, and configure middleware.''', r'''from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import time
import logging
import uvicorn

logger = logging.getLogger(__name__)


# Database connection simulation
class Database:
    """Simple async database connection manager."""
    def __init__(self):
        self.pool = None

    async def connect(self):
        logger.info("Connecting to database...")
        # In production: self.pool = await asyncpg.create_pool(DATABASE_URL)
        self.pool = {"connected": True}

    async def disconnect(self):
        logger.info("Disconnecting from database...")
        self.pool = None


db = Database()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator:
    """Application lifespan - startup and shutdown events."""
    await db.connect()
    logger.info("Application started")
    yield
    await db.disconnect()
    logger.info("Application stopped")


def create_app() -> FastAPI:
    """Application factory pattern for FastAPI."""
    app = FastAPI(
        title="MyAPI",
        description="A production-ready REST API",
        version="1.0.0",
        lifespan=lifespan,
    )

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Request timing middleware
    @app.middleware("http")
    async def add_timing_header(request: Request, call_next):
        start = time.perf_counter()
        response: Response = await call_next(request)
        elapsed = time.perf_counter() - start
        response.headers["X-Process-Time"] = f"{elapsed:.4f}"
        return response

    # Request ID middleware
    @app.middleware("http")
    async def add_request_id(request: Request, call_next):
        import uuid
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    # Import and include routers
    from .routers import users, items
    app.include_router(users.router, prefix="/api/v1/users", tags=["users"])
    app.include_router(items.router, prefix="/api/v1/items", tags=["items"])

    @app.get("/health")
    async def health_check():
        return {"status": "healthy", "database": db.pool is not None}

    return app


app = create_app()

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
'''),
    ("projects/rest-api", r'''Define Pydantic models for the REST API, including User and Item models with validation, and database schema mapping.''', r'''from pydantic import BaseModel, Field, EmailStr, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum
import re


class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"
    MODERATOR = "moderator"


class UserBase(BaseModel):
    """Base user model with shared fields."""
    email: EmailStr
    username: str = Field(min_length=3, max_length=50)
    full_name: Optional[str] = Field(None, max_length=100)

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        if not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("Username must contain only alphanumeric characters, hyphens, and underscores")
        return v.lower()


class UserCreate(UserBase):
    """Model for creating a new user."""
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if not any(c.isupper() for c in v):
            raise ValueError("Password must contain at least one uppercase letter")
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit")
        return v


class UserUpdate(BaseModel):
    """Model for updating user fields (all optional)."""
    email: Optional[EmailStr] = None
    full_name: Optional[str] = Field(None, max_length=100)
    role: Optional[UserRole] = None


class UserResponse(UserBase):
    """Model for user API responses."""
    id: int
    role: UserRole = UserRole.USER
    is_active: bool = True
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class ItemBase(BaseModel):
    """Base item model."""
    title: str = Field(min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    price: float = Field(gt=0, le=1000000)
    tags: List[str] = Field(default_factory=list, max_length=10)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: List[str]) -> List[str]:
        return [tag.strip().lower() for tag in v if tag.strip()]


class ItemCreate(ItemBase):
    """Model for creating a new item."""
    pass


class ItemUpdate(BaseModel):
    """Model for partial item updates."""
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    price: Optional[float] = Field(None, gt=0, le=1000000)
    tags: Optional[List[str]] = None


class ItemResponse(ItemBase):
    """Model for item API responses."""
    id: int
    owner_id: int
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = {"from_attributes": True}


class PaginatedResponse(BaseModel):
    """Generic paginated response wrapper."""
    items: List[ItemResponse]
    total: int
    page: int
    page_size: int
    pages: int

    @classmethod
    def create(cls, items: List, total: int, page: int, page_size: int):
        return cls(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            pages=(total + page_size - 1) // page_size,
        )
'''),
    ("projects/rest-api", r'''<think>
CRUD endpoints need proper error handling, dependency injection
for the database session, and consistent response patterns.
I will use FastAPI's Depends for DI and HTTPException for errors.
</think>
Implement CRUD endpoints for the items resource with proper error handling and dependency injection.''', r'''from fastapi import APIRouter, Depends, HTTPException, Query, status
from typing import List, Optional
from .models import ItemCreate, ItemUpdate, ItemResponse, PaginatedResponse
from .auth import get_current_user, UserResponse


router = APIRouter()


# Simulated in-memory store (replace with real DB in production)
_items_db: dict = {}
_next_id = 1


async def get_item_or_404(item_id: int) -> dict:
    """Dependency that fetches an item or raises 404."""
    item = _items_db.get(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with id {item_id} not found",
        )
    return item


@router.post("/", response_model=ItemResponse, status_code=status.HTTP_201_CREATED)
async def create_item(
    item_data: ItemCreate,
    current_user: UserResponse = Depends(get_current_user),
):
    """Create a new item owned by the current user."""
    global _next_id
    from datetime import datetime

    item = {
        "id": _next_id,
        "owner_id": current_user.id,
        "created_at": datetime.utcnow(),
        "updated_at": None,
        **item_data.model_dump(),
    }
    _items_db[_next_id] = item
    _next_id += 1
    return item


@router.get("/", response_model=PaginatedResponse)
async def list_items(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None, max_length=100),
    tag: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
):
    """List items with pagination and filtering."""
    items = list(_items_db.values())

    if search:
        search_lower = search.lower()
        items = [
            i for i in items
            if search_lower in i["title"].lower()
            or (i.get("description") and search_lower in i["description"].lower())
        ]

    if tag:
        items = [i for i in items if tag.lower() in i.get("tags", [])]

    if min_price is not None:
        items = [i for i in items if i["price"] >= min_price]

    if max_price is not None:
        items = [i for i in items if i["price"] <= max_price]

    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    page_items = items[start:end]

    return PaginatedResponse.create(page_items, total, page, page_size)


@router.get("/{item_id}", response_model=ItemResponse)
async def get_item(item: dict = Depends(get_item_or_404)):
    """Get a single item by ID."""
    return item


@router.patch("/{item_id}", response_model=ItemResponse)
async def update_item(
    item_id: int,
    update_data: ItemUpdate,
    item: dict = Depends(get_item_or_404),
    current_user: UserResponse = Depends(get_current_user),
):
    """Update an item. Only the owner can update."""
    if item["owner_id"] != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only update your own items",
        )

    from datetime import datetime
    updates = update_data.model_dump(exclude_unset=True)
    item.update(updates)
    item["updated_at"] = datetime.utcnow()
    _items_db[item_id] = item
    return item


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: int,
    item: dict = Depends(get_item_or_404),
    current_user: UserResponse = Depends(get_current_user),
):
    """Delete an item. Only the owner or admin can delete."""
    if item["owner_id"] != current_user.id and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only delete your own items",
        )
    del _items_db[item_id]
'''),
    ("projects/rest-api", r'''Implement authentication middleware for the REST API with JWT token verification and role-based access control.''', r'''from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from typing import List, Optional
from datetime import datetime, timedelta
from functools import wraps
import hashlib
import hmac
import json
import base64
import secrets


SECRET_KEY = secrets.token_hex(32)
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_DAYS = 7

security = HTTPBearer()


def _b64encode(data: bytes) -> str:
    """URL-safe base64 encode without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    """URL-safe base64 decode with padding restoration."""
    padding = 4 - len(data) % 4
    if padding != 4:
        data += "=" * padding
    return base64.urlsafe_b64decode(data)


def create_token(payload: dict, expires_delta: timedelta) -> str:
    """Create a JWT token with the given payload and expiration."""
    header = {"alg": ALGORITHM, "typ": "JWT"}
    now = datetime.utcnow()
    claims = {
        **payload,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    header_b64 = _b64encode(json.dumps(header).encode())
    payload_b64 = _b64encode(json.dumps(claims).encode())
    message = f"{header_b64}.{payload_b64}"
    signature = hmac.new(
        SECRET_KEY.encode(), message.encode(), hashlib.sha256
    ).digest()
    sig_b64 = _b64encode(signature)
    return f"{message}.{sig_b64}"


def verify_token(token: str) -> dict:
    """Verify and decode a JWT token."""
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid token format")

    header_b64, payload_b64, sig_b64 = parts
    message = f"{header_b64}.{payload_b64}"
    expected_sig = hmac.new(
        SECRET_KEY.encode(), message.encode(), hashlib.sha256
    ).digest()
    actual_sig = _b64decode(sig_b64)

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise ValueError("Invalid token signature")

    payload = json.loads(_b64decode(payload_b64))

    if payload.get("exp", 0) < datetime.utcnow().timestamp():
        raise ValueError("Token has expired")

    return payload


def create_access_token(user_id: int, role: str) -> str:
    """Create an access token for a user."""
    return create_token(
        {"sub": str(user_id), "role": role, "type": "access"},
        timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: int) -> str:
    """Create a refresh token for a user."""
    return create_token(
        {"sub": str(user_id), "type": "refresh"},
        timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """FastAPI dependency to get the current authenticated user."""
    try:
        payload = verify_token(credentials.credentials)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    # In production, fetch user from database
    return {"id": int(payload["sub"]), "role": payload["role"]}


def require_roles(*roles: str):
    """Dependency factory that checks the user has one of the required roles."""
    async def role_checker(user=Depends(get_current_user)):
        if user["role"] not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{user['role']}' is not authorized. Required: {', '.join(roles)}",
            )
        return user
    return role_checker
'''),
    ("projects/rest-api", r'''<think>
API testing is critical for production APIs. I should write tests using
httpx and pytest-asyncio with FastAPI's TestClient. Need to cover
happy paths, validation errors, auth failures, and pagination.
</think>
Write comprehensive tests for the REST API using pytest and httpx, covering CRUD operations, authentication, and error handling.''', r'''import pytest
from httpx import AsyncClient, ASGITransport
from datetime import timedelta


# Assuming the app is importable from main module
# from app.main import app
# from app.auth import create_access_token


@pytest.fixture
def admin_token():
    """Create an admin JWT token for testing."""
    from app.auth import create_access_token
    return create_access_token(user_id=1, role="admin")


@pytest.fixture
def user_token():
    """Create a regular user JWT token for testing."""
    from app.auth import create_access_token
    return create_access_token(user_id=2, role="user")


@pytest.fixture
def auth_headers(user_token):
    """Return authorization headers for a regular user."""
    return {"Authorization": f"Bearer {user_token}"}


@pytest.fixture
def admin_headers(admin_token):
    """Return authorization headers for an admin user."""
    return {"Authorization": f"Bearer {admin_token}"}


@pytest.fixture
async def client():
    """Create an async test client."""
    from app.main import app
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    """Test the health endpoint returns 200."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_create_item(client: AsyncClient, auth_headers: dict):
    """Test creating a new item."""
    item_data = {
        "title": "Test Item",
        "description": "A test item for unit testing",
        "price": 29.99,
        "tags": ["test", "sample"],
    }
    response = await client.post(
        "/api/v1/items/", json=item_data, headers=auth_headers
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "Test Item"
    assert data["price"] == 29.99
    assert "id" in data
    assert data["owner_id"] == 2


@pytest.mark.asyncio
async def test_create_item_validation_error(client: AsyncClient, auth_headers: dict):
    """Test that invalid data returns 422."""
    item_data = {"title": "", "price": -5}
    response = await client.post(
        "/api/v1/items/", json=item_data, headers=auth_headers
    )
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert len(errors) > 0


@pytest.mark.asyncio
async def test_create_item_unauthorized(client: AsyncClient):
    """Test that missing auth returns 401 or 403."""
    item_data = {"title": "Test", "price": 10.0}
    response = await client.post("/api/v1/items/", json=item_data)
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_list_items_pagination(client: AsyncClient, auth_headers: dict):
    """Test listing items with pagination."""
    # Create multiple items
    for i in range(25):
        await client.post(
            "/api/v1/items/",
            json={"title": f"Item {i}", "price": 10.0 + i},
            headers=auth_headers,
        )

    # Fetch first page
    response = await client.get("/api/v1/items/?page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert len(data["items"]) == 10
    assert data["total"] >= 25
    assert data["page"] == 1


@pytest.mark.asyncio
async def test_get_item_not_found(client: AsyncClient):
    """Test fetching a nonexistent item returns 404."""
    response = await client.get("/api/v1/items/99999")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_item_forbidden(client: AsyncClient, auth_headers: dict):
    """Test that a user cannot update another user's item."""
    # Create as admin (user_id=1)
    admin_token_val = create_access_token(user_id=1, role="admin")
    admin_h = {"Authorization": f"Bearer {admin_token_val}"}
    resp = await client.post(
        "/api/v1/items/",
        json={"title": "Admin Item", "price": 50.0},
        headers=admin_h,
    )
    item_id = resp.json()["id"]

    # Try to update as regular user (user_id=2)
    response = await client.patch(
        f"/api/v1/items/{item_id}",
        json={"title": "Hacked"},
        headers=auth_headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_expired_token(client: AsyncClient):
    """Test that expired tokens are rejected."""
    from app.auth import create_token
    token = create_token(
        {"sub": "1", "role": "user", "type": "access"},
        timedelta(seconds=-10),
    )
    headers = {"Authorization": f"Bearer {token}"}
    response = await client.get("/api/v1/items/", headers=headers)
    assert response.status_code == 401
'''),
]
