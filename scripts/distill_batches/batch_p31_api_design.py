"""API design — REST best practices, versioning, pagination, error handling, OpenAPI."""

PAIRS = [
    (
        "api/rest-best-practices",
        "Show REST API design best practices: resource naming, HTTP methods, status codes, pagination, filtering, and HATEOAS.",
        '''REST API design patterns for production:

```python
from fastapi import FastAPI, Query, Path, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional, Generic, TypeVar
from datetime import datetime
import math

app = FastAPI()
T = TypeVar("T")

# --- Resource naming ---
# Plural nouns, not verbs
# GET    /users          → List users
# POST   /users          → Create user
# GET    /users/{id}     → Get user
# PUT    /users/{id}     → Replace user
# PATCH  /users/{id}     → Partial update
# DELETE /users/{id}     → Delete user
# GET    /users/{id}/orders → User's orders (sub-resource)

# --- Pagination response ---

class PaginationMeta(BaseModel):
    page: int
    per_page: int
    total: int
    total_pages: int
    has_next: bool
    has_prev: bool

class PaginatedResponse(BaseModel, Generic[T]):
    data: list
    meta: PaginationMeta
    links: dict  # HATEOAS links

def paginate(items: list, page: int, per_page: int,
             base_url: str) -> PaginatedResponse:
    total = len(items)
    total_pages = math.ceil(total / per_page)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = items[start:end]

    links = {"self": f"{base_url}?page={page}&per_page={per_page}"}
    if page < total_pages:
        links["next"] = f"{base_url}?page={page+1}&per_page={per_page}"
    if page > 1:
        links["prev"] = f"{base_url}?page={page-1}&per_page={per_page}"
    links["first"] = f"{base_url}?page=1&per_page={per_page}"
    links["last"] = f"{base_url}?page={total_pages}&per_page={per_page}"

    return PaginatedResponse(
        data=page_items,
        meta=PaginationMeta(
            page=page, per_page=per_page, total=total,
            total_pages=total_pages,
            has_next=page < total_pages, has_prev=page > 1,
        ),
        links=links,
    )

# --- Error response format ---

class ErrorDetail(BaseModel):
    code: str
    message: str
    field: Optional[str] = None

class ErrorResponse(BaseModel):
    error: str
    message: str
    details: list[ErrorDetail] = []
    request_id: str = ""

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(
            error=HTTP_STATUS_MAP.get(exc.status_code, "error"),
            message=str(exc.detail),
            request_id=request.state.request_id,
        ).dict(),
    )

HTTP_STATUS_MAP = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
}

# --- Filtering and sorting ---

@app.get("/api/v1/orders")
async def list_orders(
    status: Optional[str] = Query(None, description="Filter by status"),
    user_id: Optional[str] = Query(None, description="Filter by user"),
    min_total: Optional[float] = Query(None, ge=0),
    max_total: Optional[float] = Query(None, ge=0),
    created_after: Optional[datetime] = Query(None),
    created_before: Optional[datetime] = Query(None),
    sort: str = Query("created_at", regex="^-?(created_at|total|status)$"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
):
    """List orders with filtering, sorting, and pagination."""
    query = build_query(
        status=status, user_id=user_id,
        min_total=min_total, max_total=max_total,
        created_after=created_after, created_before=created_before,
    )

    # Sort direction from prefix
    sort_desc = sort.startswith("-")
    sort_field = sort.lstrip("-")

    orders = await db.fetch_orders(query, sort_field, sort_desc, page, per_page)
    total = await db.count_orders(query)

    return paginate(orders, page, per_page, "/api/v1/orders")

# --- Partial updates (PATCH) ---

class UserUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[str] = None
    bio: Optional[str] = None

@app.patch("/api/v1/users/{user_id}")
async def update_user(
    user_id: str = Path(...),
    update: UserUpdate = ...,
):
    # Only update provided fields (exclude unset)
    update_data = update.dict(exclude_unset=True)
    if not update_data:
        raise HTTPException(400, "No fields to update")

    user = await db.update_user(user_id, update_data)
    if not user:
        raise HTTPException(404, f"User {user_id} not found")

    return {"data": user}

# --- Status codes ---
STATUS_CODE_GUIDE = """
200 OK           — Successful GET, PUT, PATCH
201 Created      — Successful POST (include Location header)
204 No Content   — Successful DELETE
400 Bad Request  — Invalid input, malformed JSON
401 Unauthorized — Missing or invalid authentication
403 Forbidden    — Authenticated but not authorized
404 Not Found    — Resource doesn't exist
409 Conflict     — Duplicate resource, version conflict
422 Unprocessable — Valid JSON but failed validation
429 Too Many Req — Rate limited (include Retry-After header)
500 Internal     — Server error (never expose details)
503 Service Unavail — Temporarily unavailable (maintenance)
"""
```

REST API checklist:
1. **Plural resource names** — `/users`, not `/user`
2. **HTTP methods for actions** — POST creates, PUT replaces, PATCH updates
3. **Consistent error format** — `{error, message, details}`
4. **Pagination on all list endpoints** — page/per_page or cursor
5. **Filtering via query params** — `?status=active&sort=-created_at`
6. **Versioning** — URL prefix `/api/v1/` or header
7. **HATEOAS links** — self, next, prev for discoverability'''
    ),
    (
        "api/versioning-strategies",
        "Explain API versioning strategies: URL path, header, and query parameter versioning with deprecation and migration patterns.",
        '''API versioning for backwards compatibility:

```python
from fastapi import FastAPI, Header, Request, Depends
from typing import Optional
from datetime import date

# --- Strategy 1: URL Path Versioning (most common) ---

app_v1 = FastAPI(prefix="/api/v1")
app_v2 = FastAPI(prefix="/api/v2")

# V1: original format
@app_v1.get("/users/{user_id}")
async def get_user_v1(user_id: str):
    user = await db.get_user(user_id)
    return {
        "id": user.id,
        "name": user.name,  # V1: single name field
        "email": user.email,
    }

# V2: split name into first/last
@app_v2.get("/users/{user_id}")
async def get_user_v2(user_id: str):
    user = await db.get_user(user_id)
    return {
        "id": user.id,
        "first_name": user.first_name,  # V2: split names
        "last_name": user.last_name,
        "email": user.email,
        "created_at": user.created_at.isoformat(),  # V2: added field
    }

# --- Strategy 2: Header Versioning ---

async def get_api_version(
    accept: str = Header("application/json"),
    api_version: Optional[str] = Header(None, alias="API-Version"),
) -> int:
    """Extract version from Accept header or API-Version header."""
    # Option A: Custom header
    if api_version:
        return int(api_version)

    # Option B: Accept header media type
    # Accept: application/vnd.myapi.v2+json
    if "vnd.myapi." in accept:
        version_str = accept.split("vnd.myapi.v")[1].split("+")[0]
        return int(version_str)

    return 1  # Default to v1

@app.get("/users/{user_id}")
async def get_user(user_id: str, version: int = Depends(get_api_version)):
    user = await db.get_user(user_id)
    if version == 1:
        return format_user_v1(user)
    elif version == 2:
        return format_user_v2(user)

# --- Deprecation management ---

from fastapi import Response
from datetime import datetime, timezone

class VersionConfig:
    versions = {
        1: {"status": "deprecated", "sunset": date(2024, 6, 1), "successor": 2},
        2: {"status": "current"},
        3: {"status": "beta"},
    }

def add_deprecation_headers(response: Response, version: int):
    config = VersionConfig.versions.get(version, {})

    if config.get("status") == "deprecated":
        response.headers["Deprecation"] = "true"
        sunset = config.get("sunset")
        if sunset:
            response.headers["Sunset"] = sunset.isoformat()
        successor = config.get("successor")
        if successor:
            response.headers["Link"] = f'</api/v{successor}/>; rel="successor-version"'

@app.middleware("http")
async def version_middleware(request: Request, call_next):
    response = await call_next(request)

    # Extract version from path
    path = request.url.path
    if "/api/v" in path:
        version = int(path.split("/api/v")[1].split("/")[0])
        add_deprecation_headers(response, version)

    return response

# --- Migration helper ---

class APIVersionAdapter:
    """Adapt between API versions for gradual migration."""

    @staticmethod
    def v1_to_v2_user(v1_data: dict) -> dict:
        """Transform V1 user response to V2 format."""
        name_parts = v1_data.get("name", "").split(" ", 1)
        return {
            "id": v1_data["id"],
            "first_name": name_parts[0],
            "last_name": name_parts[1] if len(name_parts) > 1 else "",
            "email": v1_data["email"],
            "created_at": None,  # Not available in V1
        }

    @staticmethod
    def v2_to_v1_user(v2_data: dict) -> dict:
        """Transform V2 user response to V1 format (backwards compat)."""
        return {
            "id": v2_data["id"],
            "name": f"{v2_data['first_name']} {v2_data['last_name']}".strip(),
            "email": v2_data["email"],
        }
```

Versioning decision:
| Strategy | Pros | Cons |
|----------|------|------|
| URL path `/v1/` | Simple, explicit, cacheable | URL pollution |
| Header `API-Version: 2` | Clean URLs | Hidden, harder to test |
| Query param `?v=2` | Easy to test | Pollutes caching |
| Content negotiation | RESTful | Complex, rarely used |

Best practices:
1. **Default to latest stable** when no version specified
2. **Sunset policy** — announce deprecation 6+ months ahead
3. **Maximum 2 versions active** — old + current
4. **Additive changes are non-breaking** — add fields, don't remove
5. **New version only for breaking changes** — not every release'''
    ),
    (
        "api/webhook-design",
        "Show how to design and implement webhooks: delivery guarantees, signature verification, retry logic, and event payload design.",
        '''Webhook system design for reliable event delivery:

```python
import hashlib
import hmac
import json
import time
import asyncio
from dataclasses import dataclass, field
from typing import Optional
from uuid import uuid4
from datetime import datetime, timezone
import httpx

@dataclass
class WebhookSubscription:
    id: str
    url: str
    secret: str
    events: list[str]  # ["order.created", "order.fulfilled"]
    active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

@dataclass
class WebhookEvent:
    id: str
    type: str
    data: dict
    created_at: str
    api_version: str = "2024-03-01"

@dataclass
class WebhookDelivery:
    id: str
    event_id: str
    subscription_id: str
    url: str
    status: str = "pending"  # pending, success, failed, exhausted
    attempts: int = 0
    last_attempt_at: Optional[float] = None
    response_status: Optional[int] = None
    response_body: Optional[str] = None
    next_retry_at: Optional[float] = None

class WebhookSender:
    """Reliable webhook delivery with retries and signatures."""

    RETRY_SCHEDULE = [60, 300, 1800, 7200, 28800, 86400]  # 1m, 5m, 30m, 2h, 8h, 24h

    def __init__(self, db, queue):
        self.db = db
        self.queue = queue

    def sign_payload(self, payload: bytes, secret: str) -> str:
        """Generate HMAC signature for payload verification."""
        timestamp = str(int(time.time()))
        signed_content = f"{timestamp}.{payload.decode()}"
        signature = hmac.new(
            secret.encode(),
            signed_content.encode(),
            hashlib.sha256,
        ).hexdigest()
        return f"t={timestamp},v1={signature}"

    async def dispatch_event(self, event_type: str, data: dict):
        """Find all subscribers and queue deliveries."""
        event = WebhookEvent(
            id=str(uuid4()),
            type=event_type,
            data=data,
            created_at=datetime.now(timezone.utc).isoformat(),
        )

        subscriptions = await self.db.get_active_subscriptions(event_type)
        for sub in subscriptions:
            delivery = WebhookDelivery(
                id=str(uuid4()),
                event_id=event.id,
                subscription_id=sub.id,
                url=sub.url,
            )
            await self.db.save_delivery(delivery)
            await self.queue.enqueue("webhook_deliver", {
                "delivery_id": delivery.id,
                "event": event.__dict__,
                "subscription": sub.__dict__,
            })

    async def deliver(self, delivery_id: str, event: dict, subscription: dict):
        """Attempt to deliver a webhook."""
        delivery = await self.db.get_delivery(delivery_id)
        if not delivery or delivery.status in ("success", "exhausted"):
            return

        payload = json.dumps({
            "id": event["id"],
            "type": event["type"],
            "api_version": event["api_version"],
            "created_at": event["created_at"],
            "data": event["data"],
        }).encode()

        signature = self.sign_payload(payload, subscription["secret"])
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "MyApp-Webhooks/1.0",
            "X-Webhook-ID": event["id"],
            "X-Webhook-Signature": signature,
            "X-Webhook-Timestamp": signature.split("t=")[1].split(",")[0],
        }

        delivery.attempts += 1
        delivery.last_attempt_at = time.time()

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    subscription["url"],
                    content=payload,
                    headers=headers,
                    timeout=30.0,
                )
                delivery.response_status = response.status_code
                delivery.response_body = response.text[:1000]

                if 200 <= response.status_code < 300:
                    delivery.status = "success"
                else:
                    await self._schedule_retry(delivery)

        except Exception as e:
            delivery.response_body = str(e)[:500]
            await self._schedule_retry(delivery)

        await self.db.save_delivery(delivery)

    async def _schedule_retry(self, delivery: WebhookDelivery):
        attempt_idx = delivery.attempts - 1
        if attempt_idx < len(self.RETRY_SCHEDULE):
            delay = self.RETRY_SCHEDULE[attempt_idx]
            delivery.next_retry_at = time.time() + delay
            delivery.status = "pending"
        else:
            delivery.status = "exhausted"
            # Disable subscription after too many failures
            failures = await self.db.count_recent_failures(delivery.subscription_id)
            if failures > 50:
                await self.db.disable_subscription(delivery.subscription_id)

# --- Receiver side: verify webhook ---

def verify_webhook(payload: bytes, signature_header: str, secret: str,
                   tolerance: int = 300) -> bool:
    """Verify webhook signature on receiving end."""
    try:
        parts = dict(p.split("=", 1) for p in signature_header.split(","))
        timestamp = int(parts["t"])
        expected_sig = parts["v1"]
    except (KeyError, ValueError):
        return False

    # Check timestamp to prevent replay attacks
    if abs(time.time() - timestamp) > tolerance:
        return False

    # Verify signature
    signed_content = f"{timestamp}.{payload.decode()}"
    computed = hmac.new(
        secret.encode(), signed_content.encode(), hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(computed, expected_sig)
```

Webhook best practices:
1. **HMAC signatures** — verify sender authenticity
2. **Timestamp in signature** — prevent replay attacks
3. **Exponential backoff** — 1m, 5m, 30m, 2h, 8h, 24h retries
4. **Idempotency** — receivers should handle duplicate deliveries
5. **Event ID** — unique per event for deduplication
6. **Timeout** — 30s max, return 2xx quickly
7. **Disable after failures** — auto-disable dead endpoints'''
    ),
]
