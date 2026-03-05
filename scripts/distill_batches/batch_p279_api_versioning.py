"""API versioning and evolution — backward compatibility, migration."""

PAIRS = [
    (
        "architecture/api-versioning",
        "Show API versioning strategies: URL path, header-based, content negotiation, and backward-compatible evolution.",
        '''API versioning strategies:

```python
from fastapi import FastAPI, Header, Request, APIRouter
from typing import Optional, Any
from pydantic import BaseModel


# Strategy 1: URL Path Versioning
v1_router = APIRouter(prefix="/api/v1")
v2_router = APIRouter(prefix="/api/v2")

class UserV1(BaseModel):
    id: str
    name: str       # V1: single name field
    email: str

class UserV2(BaseModel):
    id: str
    first_name: str  # V2: split into first/last
    last_name: str
    email: str
    phone: Optional[str] = None  # V2: new field

@v1_router.get("/users/{user_id}")
async def get_user_v1(user_id: str) -> UserV1:
    user = await db.get_user(user_id)
    return UserV1(
        id=user.id,
        name=f"{user.first_name} {user.last_name}",  # Combine for V1
        email=user.email,
    )

@v2_router.get("/users/{user_id}")
async def get_user_v2(user_id: str) -> UserV2:
    user = await db.get_user(user_id)
    return UserV2(**user.dict())


# Strategy 2: Header-Based Versioning
class VersionedAPI:
    def __init__(self):
        self.handlers: dict[str, dict] = {}

    def route(self, path: str, version: str):
        def decorator(fn):
            self.handlers.setdefault(path, {})[version] = fn
            return fn
        return decorator

    async def dispatch(self, request: Request):
        path = request.url.path
        version = request.headers.get("API-Version", "2024-01-01")
        handlers = self.handlers.get(path, {})

        # Find best matching version (latest <= requested)
        available = sorted(handlers.keys())
        selected = available[0]
        for v in available:
            if v <= version:
                selected = v
        return await handlers[selected](request)


# Strategy 3: Backward-Compatible Evolution
class EvolvableAPI:
    """Add fields (never remove), deprecate gracefully."""

    @staticmethod
    def response_with_compat(data: dict, version: str) -> dict:
        """Transform response based on client version."""
        response = data.copy()

        if version < "2025-01-01":
            # Legacy clients expect 'name' not 'first_name'/'last_name'
            if "first_name" in response:
                response["name"] = f"{response['first_name']} {response['last_name']}"
                # Keep new fields too — additive is safe

        if version < "2026-01-01":
            # Older clients don't understand 'preferences' nested object
            response.pop("preferences", None)

        return response


# Strategy 4: Sunset Headers
class SunsetMiddleware:
    """Add deprecation/sunset headers to old API versions."""

    SUNSET_DATES = {
        "v1": "2025-06-01",
        "v2": None,  # Current, no sunset
    }

    async def __call__(self, request: Request, call_next):
        response = await call_next(request)

        path = request.url.path
        for version, sunset in self.SUNSET_DATES.items():
            if f"/{version}/" in path and sunset:
                response.headers["Sunset"] = sunset
                response.headers["Deprecation"] = "true"
                response.headers["Link"] = (
                    f'</api/v2{path.split(version)[1]}>; rel="successor-version"'
                )

        return response
```

Key patterns:
1. **URL versioning** — clear, cacheable, but requires maintaining multiple route sets
2. **Header versioning** — clean URLs, version in Accept or custom header
3. **Additive evolution** — add fields freely; never remove or rename; safest approach
4. **Sunset headers** — RFC 8594; tell clients when old version will be removed
5. **Version-aware transforms** — single data source, transform response per client version'''
    ),
    (
        "architecture/api-pagination",
        "Show API pagination patterns: cursor-based, offset, keyset pagination with proper link headers.",
        '''API pagination patterns:

```python
import base64
import json
from dataclasses import dataclass
from typing import Optional, Any


@dataclass
class Page:
    items: list[Any]
    total_count: Optional[int]
    has_next: bool
    has_prev: bool
    cursor_next: Optional[str]
    cursor_prev: Optional[str]


class CursorPagination:
    """Cursor-based pagination — stable, efficient for large datasets.

    Cursor encodes position (e.g., last item's ID + sort value).
    No page skipping, but consistent results even with inserts/deletes.
    """

    @staticmethod
    def encode_cursor(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).decode()

    @staticmethod
    def decode_cursor(cursor: str) -> dict:
        return json.loads(base64.urlsafe_b64decode(cursor).decode())

    async def paginate(self, db, table: str, limit: int = 20,
                        after: str = None, before: str = None,
                        order_by: str = "created_at") -> Page:
        query = f"SELECT * FROM {table}"
        params = []

        if after:
            cursor_data = self.decode_cursor(after)
            query += f" WHERE ({order_by}, id) > ($1, $2)"
            params.extend([cursor_data["value"], cursor_data["id"]])
        elif before:
            cursor_data = self.decode_cursor(before)
            query += f" WHERE ({order_by}, id) < ($1, $2)"
            params.extend([cursor_data["value"], cursor_data["id"]])

        query += f" ORDER BY {order_by}, id LIMIT $%d" % (len(params) + 1)
        params.append(limit + 1)  # Fetch one extra to detect has_next

        rows = await db.fetch(query, *params)
        has_next = len(rows) > limit
        items = rows[:limit]

        return Page(
            items=items,
            total_count=None,  # Cursor pagination skips expensive COUNT
            has_next=has_next,
            has_prev=after is not None,
            cursor_next=self.encode_cursor({
                "id": str(items[-1]["id"]),
                "value": str(items[-1][order_by]),
            }) if items and has_next else None,
            cursor_prev=self.encode_cursor({
                "id": str(items[0]["id"]),
                "value": str(items[0][order_by]),
            }) if items else None,
        )


class KeysetPagination:
    """Keyset (seek) pagination — most efficient for DB.

    Uses WHERE clause instead of OFFSET; always O(log n) index seek.
    """

    async def paginate(self, db, table: str, limit: int = 20,
                        last_id: Optional[str] = None) -> Page:
        if last_id:
            rows = await db.fetch(
                f"SELECT * FROM {table} WHERE id > $1 ORDER BY id LIMIT $2",
                last_id, limit + 1,
            )
        else:
            rows = await db.fetch(
                f"SELECT * FROM {table} ORDER BY id LIMIT $1",
                limit + 1,
            )

        has_next = len(rows) > limit
        items = rows[:limit]

        return Page(
            items=items, total_count=None,
            has_next=has_next, has_prev=last_id is not None,
            cursor_next=str(items[-1]["id"]) if items and has_next else None,
            cursor_prev=None,
        )


def build_link_header(base_url: str, page: Page) -> str:
    """RFC 8288 Link header for pagination."""
    links = []
    if page.cursor_next:
        links.append(f'<{base_url}?after={page.cursor_next}>; rel="next"')
    if page.cursor_prev:
        links.append(f'<{base_url}?before={page.cursor_prev}>; rel="prev"')
    return ", ".join(links)
```

Key patterns:
1. **Cursor pagination** — encode position in opaque cursor; stable across data changes
2. **Keyset/seek** — WHERE id > last_id; O(log n) index seek vs O(n) OFFSET scan
3. **Fetch N+1** — request one extra row to determine has_next without separate COUNT
4. **Link headers** — RFC 8288; machine-readable next/prev links in response headers
5. **Avoid OFFSET** — OFFSET is O(n) and results shift with inserts; use cursors instead'''
    ),
]
"""
