"""API documentation — OpenAPI, auto-generated docs, and SDK generation."""

PAIRS = [
    (
        "backend/openapi-fastapi",
        "Show FastAPI OpenAPI documentation patterns: custom schemas, examples, response models, and tags.",
        '''FastAPI OpenAPI documentation patterns:

```python
from fastapi import FastAPI, Query, Path, Body, HTTPException, status
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime
from enum import Enum
from typing import Annotated


# --- Custom OpenAPI schema ---

app = FastAPI(
    title="My API",
    version="1.0.0",
    description="Production API with full OpenAPI documentation",
    servers=[
        {"url": "https://api.example.com", "description": "Production"},
        {"url": "https://staging-api.example.com", "description": "Staging"},
    ],
)


# --- Enum for query parameters ---

class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"


class UserStatus(str, Enum):
    active = "active"
    inactive = "inactive"
    suspended = "suspended"


# --- Request/Response models with examples ---

class UserCreate(BaseModel):
    email: str = Field(
        ...,
        description="User's email address",
        json_schema_extra={"example": "alice@example.com"},
    )
    name: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Display name",
        json_schema_extra={"example": "Alice Johnson"},
    )
    role: str = Field(
        default="user",
        description="User role",
        json_schema_extra={"example": "admin"},
    )

    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "summary": "Regular user",
                    "value": {
                        "email": "bob@example.com",
                        "name": "Bob Smith",
                    },
                },
                {
                    "summary": "Admin user",
                    "value": {
                        "email": "admin@example.com",
                        "name": "Admin",
                        "role": "admin",
                    },
                },
            ]
        }
    )


class UserResponse(BaseModel):
    id: str = Field(..., description="Unique user ID")
    email: str
    name: str
    status: UserStatus
    created_at: datetime

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "usr_abc123",
                "email": "alice@example.com",
                "name": "Alice Johnson",
                "status": "active",
                "created_at": "2024-01-15T10:30:00Z",
            }
        }
    )


class PaginatedResponse(BaseModel):
    items: list[UserResponse]
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number")
    per_page: int = Field(..., description="Items per page")
    has_next: bool


class ErrorResponse(BaseModel):
    detail: str = Field(..., description="Error message")
    code: str = Field(..., description="Machine-readable error code")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "detail": "User not found",
                "code": "USER_NOT_FOUND",
            }
        }
    )


# --- Endpoints with full documentation ---

@app.get(
    "/api/users",
    response_model=PaginatedResponse,
    tags=["Users"],
    summary="List users",
    description="Retrieve paginated list of users with optional filtering.",
    responses={
        200: {"description": "Successful response with user list"},
        422: {"description": "Validation error", "model": ErrorResponse},
    },
)
async def list_users(
    page: Annotated[int, Query(ge=1, description="Page number")] = 1,
    per_page: Annotated[int, Query(ge=1, le=100, description="Items per page")] = 20,
    status: Annotated[UserStatus | None, Query(description="Filter by status")] = None,
    search: Annotated[str | None, Query(
        min_length=2,
        description="Search by name or email",
    )] = None,
    sort: Annotated[SortOrder, Query(description="Sort order")] = SortOrder.desc,
):
    """List users with pagination, filtering, and search."""
    ...


@app.post(
    "/api/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Users"],
    summary="Create user",
    responses={
        201: {"description": "User created successfully"},
        409: {
            "description": "User already exists",
            "model": ErrorResponse,
            "content": {
                "application/json": {
                    "example": {
                        "detail": "Email already registered",
                        "code": "DUPLICATE_EMAIL",
                    }
                }
            },
        },
    },
)
async def create_user(user: UserCreate):
    """Create a new user account."""
    ...


@app.get(
    "/api/users/{user_id}",
    response_model=UserResponse,
    tags=["Users"],
    summary="Get user by ID",
    responses={
        404: {"description": "User not found", "model": ErrorResponse},
    },
)
async def get_user(
    user_id: Annotated[str, Path(
        description="User ID",
        pattern=r"^usr_[a-zA-Z0-9]+$",
        examples=["usr_abc123"],
    )],
):
    """Retrieve a single user by their ID."""
    ...


# --- Custom OpenAPI schema modifications ---

def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )

    # Add security scheme
    schema["components"]["securitySchemes"] = {
        "BearerAuth": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        },
        "ApiKey": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
        },
    }
    schema["security"] = [{"BearerAuth": []}, {"ApiKey": []}]

    app.openapi_schema = schema
    return schema

app.openapi = custom_openapi
```

OpenAPI documentation patterns:
1. **`Field(description=, example=)`** — document each field with type + example
2. **`json_schema_extra.examples`** — multiple named examples per schema
3. **`responses={}`** — document error codes with specific models and examples
4. **`Annotated[type, Query/Path]`** — typed parameters with validation + docs
5. **`custom_openapi()`** — modify generated schema to add security schemes'''
    ),
    (
        "backend/api-versioning",
        "Show API versioning patterns: URL path, header-based, content negotiation, and migration strategies.",
        '''API versioning patterns:

```python
from fastapi import FastAPI, APIRouter, Header, Request, Depends
from fastapi.routing import APIRoute
from typing import Annotated, Callable
from enum import Enum
import re


# === Strategy 1: URL path versioning (most common) ===

app = FastAPI()

v1_router = APIRouter(prefix="/api/v1", tags=["v1"])
v2_router = APIRouter(prefix="/api/v2", tags=["v2"])


# V1: original response format
@v1_router.get("/users/{user_id}")
async def get_user_v1(user_id: str):
    user = await fetch_user(user_id)
    return {
        "id": user.id,
        "name": user.name,          # V1: single name field
        "email": user.email,
    }


# V2: updated response format
@v2_router.get("/users/{user_id}")
async def get_user_v2(user_id: str):
    user = await fetch_user(user_id)
    return {
        "id": user.id,
        "first_name": user.first_name,  # V2: split name
        "last_name": user.last_name,
        "email": user.email,
        "avatar_url": user.avatar_url,  # V2: new field
    }


app.include_router(v1_router)
app.include_router(v2_router)


# === Strategy 2: Header-based versioning ===

class APIVersion(str, Enum):
    v1 = "1"
    v2 = "2"


def get_api_version(
    accept_version: Annotated[
        str | None, Header(alias="X-API-Version")
    ] = None,
) -> APIVersion:
    """Extract API version from header, default to latest."""
    if accept_version == "1":
        return APIVersion.v1
    return APIVersion.v2


@app.get("/api/users/{user_id}")
async def get_user_header_versioned(
    user_id: str,
    version: APIVersion = Depends(get_api_version),
):
    user = await fetch_user(user_id)

    if version == APIVersion.v1:
        return {"id": user.id, "name": user.name}

    return {"id": user.id, "first_name": user.first_name, "last_name": user.last_name}


# === Strategy 3: Version-aware response transformer ===

class VersionedResponse:
    """Transform response based on API version."""

    transforms: dict[str, dict[str, Callable]] = {
        "/users": {
            "1": lambda data: {
                "id": data["id"],
                "name": f"{data['first_name']} {data['last_name']}",
                "email": data["email"],
            },
            "2": lambda data: data,  # V2 is canonical
        },
    }

    @classmethod
    def transform(cls, path: str, version: str, data: dict) -> dict:
        # Find matching path pattern
        for pattern, versions in cls.transforms.items():
            if pattern in path:
                transformer = versions.get(version, versions[max(versions)])
                return transformer(data)
        return data


# === Deprecation headers middleware ===

from starlette.middleware.base import BaseHTTPMiddleware

class DeprecationMiddleware(BaseHTTPMiddleware):
    """Add deprecation headers for old API versions."""

    DEPRECATED_PREFIXES = {
        "/api/v1": {
            "sunset": "2025-06-01",
            "link": "https://docs.example.com/migration-guide",
        },
    }

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)

        for prefix, info in self.DEPRECATED_PREFIXES.items():
            if request.url.path.startswith(prefix):
                response.headers["Deprecation"] = "true"
                response.headers["Sunset"] = info["sunset"]
                response.headers["Link"] = (
                    f'<{info["link"]}>; rel="deprecation"'
                )
                break

        return response

app.add_middleware(DeprecationMiddleware)


# === Version migration checklist ===

"""
API Version Migration Strategy:

1. ANNOUNCE (3+ months before):
   - Document breaking changes
   - Add Deprecation headers to old version
   - Publish migration guide

2. DUAL-RUN (migration period):
   - Both versions active
   - Monitor v1 vs v2 traffic ratio
   - Help major consumers migrate

3. SUNSET (after migration):
   - V1 returns 410 Gone with migration link
   - Keep V1 docs accessible
   - Log remaining V1 consumers

Breaking vs Non-Breaking:
  NON-BREAKING (safe to add):
    - New optional fields in response
    - New optional query parameters
    - New endpoints
    - New enum values (if client ignores unknown)

  BREAKING (requires new version):
    - Removing/renaming fields
    - Changing field types
    - Removing endpoints
    - Changing authentication
    - Changing error format
"""
```

API versioning patterns:
1. **URL path versioning** (`/api/v1/`) — most explicit, easiest for clients and docs
2. **Header versioning** (`X-API-Version: 2`) — clean URLs, requires client awareness
3. **Response transformers** — single handler with version-aware output mapping
4. **Deprecation headers** — `Sunset` + `Link` headers warn clients of upcoming removal
5. **Non-breaking additions** — new optional fields don't require a version bump'''
    ),
]
"""
