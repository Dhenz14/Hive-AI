"""Webhook delivery and event systems — reliable delivery, CloudEvents, signature verification, fan-out subscriptions."""

PAIRS = [
    (
        "backend/webhook-reliable-delivery",
        "Show reliable webhook delivery patterns: idempotency keys, exponential backoff retry, dead letter queues, and delivery guarantees.",
        '''Reliable webhook delivery with idempotency, retry, and DLQ:

```python
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Any

import httpx
from sqlalchemy import (
    String, Integer, DateTime, Text, Boolean,
    select, update, func,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

logger = logging.getLogger(__name__)


# ── Data models ──────────────────────────────────────────────────

class Base(DeclarativeBase):
    pass


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    FAILED = "failed"
    DLQ = "dead_letter"


class WebhookEvent(Base):
    """Outbound webhook event with delivery tracking."""
    __tablename__ = "webhook_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[str] = mapped_column(Text)  # JSON
    idempotency_key: Mapped[str] = mapped_column(
        String(64), unique=True, index=True
    )

    # Delivery state
    subscription_id: Mapped[str] = mapped_column(String(36), index=True)
    target_url: Mapped[str] = mapped_column(String(2000))
    status: Mapped[str] = mapped_column(
        String(20), default=DeliveryStatus.PENDING.value, index=True
    )
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    # Response tracking
    last_status_code: Mapped[int | None] = mapped_column(Integer, default=None)
    last_response_body: Mapped[str | None] = mapped_column(Text, default=None)
    last_error: Mapped[str | None] = mapped_column(Text, default=None)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None
    )


class WebhookSubscription(Base):
    """Webhook subscription (endpoint registration)."""
    __tablename__ = "webhook_subscriptions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    url: Mapped[str] = mapped_column(String(2000))
    secret: Mapped[str] = mapped_column(String(64))
    event_types: Mapped[str] = mapped_column(Text)  # JSON array
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


# ── Webhook delivery engine ──────────────────────────────────────

class WebhookDeliveryEngine:
    """Delivers webhooks with retry, idempotency, and DLQ."""

    BACKOFF_SCHEDULE = [
        timedelta(seconds=10),    # attempt 1
        timedelta(minutes=1),     # attempt 2
        timedelta(minutes=5),     # attempt 3
        timedelta(minutes=30),    # attempt 4
        timedelta(hours=2),       # attempt 5
    ]

    def __init__(
        self,
        session_factory: Any,
        timeout: float = 30.0,
        max_concurrent: int = 50,
    ) -> None:
        self._session_factory = session_factory
        self._timeout = timeout
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout),
            follow_redirects=False,
            limits=httpx.Limits(
                max_connections=100,
                max_keepalive_connections=20,
            ),
        )

    async def enqueue_event(
        self,
        session: AsyncSession,
        event_type: str,
        payload: dict[str, Any],
        source_id: str | None = None,
    ) -> list[str]:
        """Create webhook events for all matching subscriptions."""
        # Find active subscriptions for this event type
        stmt = select(WebhookSubscription).where(
            WebhookSubscription.is_active == True,  # noqa: E712
        )
        result = await session.execute(stmt)
        subscriptions = result.scalars().all()

        event_ids: list[str] = []
        for sub in subscriptions:
            sub_events = json.loads(sub.event_types)
            if event_type not in sub_events and "*" not in sub_events:
                continue

            # Generate idempotency key
            idem_key = hashlib.sha256(
                f"{sub.id}:{event_type}:{source_id or uuid.uuid4()}".encode()
            ).hexdigest()

            event = WebhookEvent(
                event_type=event_type,
                payload=json.dumps(payload),
                idempotency_key=idem_key,
                subscription_id=sub.id,
                target_url=sub.url,
            )
            session.add(event)
            event_ids.append(event.id)

        return event_ids
```

```python
    # ── Delivery with retry logic ─────────────────────────────

    async def deliver(self, event_id: str) -> bool:
        """Attempt to deliver a single webhook event."""
        async with self._semaphore:
            async with self._session_factory() as session:
                event = await session.get(WebhookEvent, event_id)
                if not event or event.status in (
                    DeliveryStatus.DELIVERED.value,
                    DeliveryStatus.DLQ.value,
                ):
                    return False

                # Get subscription for signing
                sub = await session.get(
                    WebhookSubscription, event.subscription_id
                )
                if not sub or not sub.is_active:
                    event.status = DeliveryStatus.FAILED.value
                    event.last_error = "Subscription inactive"
                    await session.commit()
                    return False

                event.status = DeliveryStatus.DELIVERING.value
                event.attempt_count += 1
                await session.commit()

            # Deliver outside the DB transaction
            success = await self._attempt_delivery(event, sub.secret)

            async with self._session_factory() as session:
                event = await session.get(WebhookEvent, event_id)
                if not event:
                    return False

                if success:
                    event.status = DeliveryStatus.DELIVERED.value
                    event.delivered_at = datetime.now(timezone.utc)
                elif event.attempt_count >= event.max_attempts:
                    event.status = DeliveryStatus.DLQ.value
                    logger.warning(
                        f"Webhook {event_id} moved to DLQ after "
                        f"{event.attempt_count} attempts"
                    )
                else:
                    event.status = DeliveryStatus.PENDING.value
                    backoff_idx = min(
                        event.attempt_count - 1,
                        len(self.BACKOFF_SCHEDULE) - 1,
                    )
                    event.next_attempt_at = (
                        datetime.now(timezone.utc)
                        + self.BACKOFF_SCHEDULE[backoff_idx]
                    )

                await session.commit()
                return success

    async def _attempt_delivery(
        self, event: WebhookEvent, secret: str
    ) -> bool:
        """Make the actual HTTP request."""
        payload = event.payload
        timestamp = str(int(time.time()))

        # Sign the payload
        signature = hmac.new(
            secret.encode(),
            f"{timestamp}.{payload}".encode(),
            hashlib.sha256,
        ).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-ID": event.id,
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Signature": f"sha256={signature}",
            "X-Webhook-Event": event.event_type,
            "X-Idempotency-Key": event.idempotency_key,
            "User-Agent": "MyApp-Webhooks/1.0",
        }

        try:
            response = await self._client.post(
                event.target_url,
                content=payload,
                headers=headers,
            )
            event.last_status_code = response.status_code
            event.last_response_body = response.text[:1000]

            # 2xx = success, anything else = retry
            return 200 <= response.status_code < 300

        except httpx.TimeoutException:
            event.last_error = "Request timed out"
            return False
        except httpx.ConnectError as e:
            event.last_error = f"Connection error: {e}"
            return False
        except Exception as e:
            event.last_error = f"Unexpected error: {e}"
            return False

    # ── Polling worker ────────────────────────────────────────

    async def run_delivery_worker(
        self, poll_interval: float = 5.0, batch_size: int = 100
    ) -> None:
        """Poll for pending webhooks and deliver them."""
        while True:
            try:
                async with self._session_factory() as session:
                    now = datetime.now(timezone.utc)
                    stmt = (
                        select(WebhookEvent.id)
                        .where(WebhookEvent.status == DeliveryStatus.PENDING.value)
                        .where(WebhookEvent.next_attempt_at <= now)
                        .order_by(WebhookEvent.next_attempt_at)
                        .limit(batch_size)
                    )
                    result = await session.execute(stmt)
                    event_ids = [row[0] for row in result.all()]

                if event_ids:
                    tasks = [self.deliver(eid) for eid in event_ids]
                    await asyncio.gather(*tasks, return_exceptions=True)
                    logger.info(f"Processed {len(event_ids)} webhooks")

            except Exception as e:
                logger.error(f"Delivery worker error: {e}")

            await asyncio.sleep(poll_interval)
```

```python
# ── DLQ management ────────────────────────────────────────────────

class DLQManager:
    """Manage dead-letter queue for failed webhooks."""

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def get_dlq_events(
        self,
        subscription_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        async with self._session_factory() as session:
            stmt = select(WebhookEvent).where(
                WebhookEvent.status == DeliveryStatus.DLQ.value,
            )
            if subscription_id:
                stmt = stmt.where(
                    WebhookEvent.subscription_id == subscription_id
                )
            stmt = stmt.order_by(WebhookEvent.created_at.desc()).limit(limit)

            result = await session.execute(stmt)
            return [
                {
                    "id": e.id,
                    "event_type": e.event_type,
                    "target_url": e.target_url,
                    "attempt_count": e.attempt_count,
                    "last_status_code": e.last_status_code,
                    "last_error": e.last_error,
                    "created_at": e.created_at.isoformat(),
                }
                for e in result.scalars().all()
            ]

    async def retry_dlq_event(self, event_id: str) -> bool:
        """Move a DLQ event back to pending for retry."""
        async with self._session_factory() as session:
            event = await session.get(WebhookEvent, event_id)
            if not event or event.status != DeliveryStatus.DLQ.value:
                return False
            event.status = DeliveryStatus.PENDING.value
            event.attempt_count = 0
            event.next_attempt_at = datetime.now(timezone.utc)
            await session.commit()
            return True

    async def retry_all_dlq(self, subscription_id: str) -> int:
        """Retry all DLQ events for a subscription."""
        async with self._session_factory() as session:
            stmt = (
                update(WebhookEvent)
                .where(WebhookEvent.status == DeliveryStatus.DLQ.value)
                .where(WebhookEvent.subscription_id == subscription_id)
                .values(
                    status=DeliveryStatus.PENDING.value,
                    attempt_count=0,
                    next_attempt_at=datetime.now(timezone.utc),
                )
            )
            result = await session.execute(stmt)
            await session.commit()
            return result.rowcount  # type: ignore

    async def purge_old_events(self, days: int = 30) -> int:
        """Delete delivered events older than N days."""
        async with self._session_factory() as session:
            cutoff = datetime.now(timezone.utc) - timedelta(days=days)
            stmt = (
                select(WebhookEvent)
                .where(WebhookEvent.status == DeliveryStatus.DELIVERED.value)
                .where(WebhookEvent.delivered_at < cutoff)
            )
            result = await session.execute(stmt)
            events = result.scalars().all()
            for event in events:
                await session.delete(event)
            await session.commit()
            return len(events)
```

| Component | Purpose | Implementation |
|---|---|---|
| Idempotency key | Prevent duplicate delivery | SHA256 of sub_id + event + source |
| Exponential backoff | Avoid hammering failed endpoints | 10s, 1m, 5m, 30m, 2h |
| Dead Letter Queue | Capture permanently failed deliveries | Status = "dead_letter" after max retries |
| Signature header | Prove authenticity to receiver | HMAC-SHA256 of timestamp.payload |
| Delivery semaphore | Limit concurrent outbound requests | `asyncio.Semaphore(50)` |
| Polling worker | Process pending events in batches | `SELECT ... WHERE next_attempt_at <= now` |

Key patterns:
1. Generate **idempotency keys** from subscription + event + source to prevent dupes.
2. Use **exponential backoff** with increasing delays: 10s, 1m, 5m, 30m, 2h.
3. Move to **DLQ** after max attempts -- provide an API to retry or inspect failures.
4. Sign payloads with **HMAC-SHA256** using a per-subscription secret.
5. Deliver **outside** the database transaction to avoid holding locks during HTTP calls.
6. Include **X-Webhook-ID** and **X-Idempotency-Key** headers for receiver deduplication.'''
    ),
    (
        "backend/webhook-cloudevents",
        "Show event-driven architecture with CloudEvents format: structured events, routing, event bus, and schema registry integration.",
        '''Event-driven architecture with CloudEvents format:

```python
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, TypeVar

from pydantic import BaseModel, Field


# ── CloudEvents specification (v1.0) ─────────────────────────────

class CloudEvent(BaseModel):
    """CloudEvents v1.0 specification.

    Standard envelope for events across services.
    See: https://cloudevents.io/
    """

    # Required attributes
    specversion: str = "1.0"
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    source: str                    # URI of event origin
    type: str                      # Event type (reverse DNS)
    time: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # Optional attributes
    datacontenttype: str = "application/json"
    dataschema: str | None = None  # URI to schema
    subject: str | None = None     # Subject (e.g., resource ID)

    # Extensions
    data: dict[str, Any] | None = None
    extensions: dict[str, Any] = Field(default_factory=dict)

    def to_http_headers(self) -> dict[str, str]:
        """Binary content mode: attributes in HTTP headers."""
        headers = {
            "ce-specversion": self.specversion,
            "ce-id": self.id,
            "ce-source": self.source,
            "ce-type": self.type,
            "ce-time": self.time.isoformat(),
            "Content-Type": self.datacontenttype,
        }
        if self.subject:
            headers["ce-subject"] = self.subject
        if self.dataschema:
            headers["ce-dataschema"] = self.dataschema
        for key, value in self.extensions.items():
            headers[f"ce-{key}"] = str(value)
        return headers

    @classmethod
    def from_http(
        cls, headers: dict[str, str], body: bytes
    ) -> CloudEvent:
        """Parse CloudEvent from HTTP request (binary mode)."""
        extensions = {}
        for key, value in headers.items():
            key_lower = key.lower()
            if key_lower.startswith("ce-") and key_lower not in {
                "ce-specversion", "ce-id", "ce-source",
                "ce-type", "ce-time", "ce-subject", "ce-dataschema",
            }:
                ext_name = key_lower[3:]
                extensions[ext_name] = value

        return cls(
            specversion=headers.get("ce-specversion", "1.0"),
            id=headers.get("ce-id", str(uuid.uuid4())),
            source=headers.get("ce-source", ""),
            type=headers.get("ce-type", ""),
            time=datetime.fromisoformat(
                headers.get("ce-time", datetime.now(timezone.utc).isoformat())
            ),
            subject=headers.get("ce-subject"),
            dataschema=headers.get("ce-dataschema"),
            datacontenttype=headers.get("Content-Type", "application/json"),
            data=json.loads(body) if body else None,
            extensions=extensions,
        )

    def to_structured(self) -> dict[str, Any]:
        """Structured content mode: everything in JSON body."""
        result: dict[str, Any] = {
            "specversion": self.specversion,
            "id": self.id,
            "source": self.source,
            "type": self.type,
            "time": self.time.isoformat(),
            "datacontenttype": self.datacontenttype,
        }
        if self.subject:
            result["subject"] = self.subject
        if self.dataschema:
            result["dataschema"] = self.dataschema
        if self.data:
            result["data"] = self.data
        result.update(self.extensions)
        return result


# ── Event factory ─────────────────────────────────────────────────

class EventFactory:
    """Create domain events in CloudEvents format."""

    def __init__(self, service_name: str, base_uri: str) -> None:
        self._source = f"{base_uri}/{service_name}"

    def create(
        self,
        event_type: str,
        data: dict[str, Any],
        subject: str | None = None,
        **extensions: Any,
    ) -> CloudEvent:
        return CloudEvent(
            source=self._source,
            type=f"com.myapp.{event_type}",
            data=data,
            subject=subject,
            dataschema=f"https://schemas.myapp.com/{event_type}/v1.json",
            extensions=extensions,
        )


# Usage
factory = EventFactory("user-service", "https://api.myapp.com")
event = factory.create(
    event_type="user.created",
    data={"user_id": "u-123", "email": "alice@example.com", "plan": "pro"},
    subject="u-123",
    correlationid="req-abc-123",
)
```

```python
# ── In-memory event bus with routing ──────────────────────────────

import asyncio
import re
from collections import defaultdict


EventHandler = Callable[[CloudEvent], Coroutine[Any, Any, None]]


class EventBus:
    """In-process event bus with pattern-based routing."""

    def __init__(self) -> None:
        self._handlers: dict[str, list[EventHandler]] = defaultdict(list)
        self._wildcard_handlers: list[tuple[re.Pattern, EventHandler]] = []
        self._middleware: list[Callable] = []

    def subscribe(
        self, event_type: str, handler: EventHandler
    ) -> None:
        """Subscribe to exact event type."""
        self._handlers[event_type].append(handler)

    def subscribe_pattern(
        self, pattern: str, handler: EventHandler
    ) -> None:
        """Subscribe to event types matching a glob pattern.
        e.g., 'com.myapp.user.*' matches all user events.
        """
        regex = pattern.replace(".", r"\.").replace("*", r"[^.]*")
        self._wildcard_handlers.append((re.compile(f"^{regex}$"), handler))

    def add_middleware(
        self,
        middleware: Callable[[CloudEvent, Callable], Coroutine],
    ) -> None:
        """Add middleware that wraps all handlers."""
        self._middleware.append(middleware)

    async def publish(self, event: CloudEvent) -> None:
        """Publish event to all matching handlers."""
        handlers: list[EventHandler] = []

        # Exact match
        handlers.extend(self._handlers.get(event.type, []))

        # Pattern match
        for pattern, handler in self._wildcard_handlers:
            if pattern.match(event.type):
                handlers.append(handler)

        # Execute all handlers concurrently
        tasks = [self._invoke(handler, event) for handler in handlers]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _invoke(
        self, handler: EventHandler, event: CloudEvent
    ) -> None:
        """Invoke handler with middleware chain."""
        async def final_handler(evt: CloudEvent) -> None:
            await handler(evt)

        chain = final_handler
        for mw in reversed(self._middleware):
            prev = chain
            async def wrapped(evt: CloudEvent, _prev=prev, _mw=mw) -> None:
                await _mw(evt, _prev)
            chain = wrapped

        await chain(event)


# ── Middleware examples ───────────────────────────────────────────

import logging
import time

logger = logging.getLogger(__name__)


async def logging_middleware(
    event: CloudEvent, next_handler: Callable
) -> None:
    start = time.monotonic()
    logger.info(f"Event received: {event.type} ({event.id})")
    try:
        await next_handler(event)
        elapsed = (time.monotonic() - start) * 1000
        logger.info(f"Event processed: {event.type} ({elapsed:.1f}ms)")
    except Exception as e:
        logger.error(f"Event handler failed: {event.type} - {e}")
        raise


async def deduplication_middleware(
    event: CloudEvent, next_handler: Callable
) -> None:
    """Skip already-processed events."""
    import redis.asyncio as aioredis
    r = aioredis.from_url("redis://localhost:6379")
    key = f"event:seen:{event.id}"
    if await r.set(key, "1", nx=True, ex=86400):
        await next_handler(event)
    else:
        logger.info(f"Duplicate event skipped: {event.id}")
    await r.close()
```

```python
# ── Example: domain event handlers ───────────────────────────────

bus = EventBus()
bus.add_middleware(logging_middleware)


# Handler for specific event
@bus.subscribe("com.myapp.user.created", handler=None)  # decorator pattern below
async def on_user_created(event: CloudEvent) -> None:
    data = event.data or {}
    user_id = data.get("user_id")
    email = data.get("email")
    # Send welcome email, create default settings, etc.
    logger.info(f"New user: {user_id} ({email})")


# Subscribe via method call
async def handle_order_events(event: CloudEvent) -> None:
    data = event.data or {}
    if event.type == "com.myapp.order.placed":
        logger.info(f"Order placed: {data.get('order_id')}")
    elif event.type == "com.myapp.order.shipped":
        logger.info(f"Order shipped: {data.get('tracking')}")

bus.subscribe_pattern("com.myapp.order.*", handle_order_events)


# ── FastAPI integration ──────────────────────────────────────────

from fastapi import FastAPI, Request, Response

app = FastAPI()


@app.post("/events")
async def receive_cloudevent(request: Request) -> Response:
    """Receive CloudEvents in both binary and structured mode."""
    headers = dict(request.headers)
    body = await request.body()

    # Detect content mode
    content_type = headers.get("content-type", "")
    if "ce-type" in headers:
        # Binary content mode
        event = CloudEvent.from_http(headers, body)
    elif "application/cloudevents+json" in content_type:
        # Structured content mode
        raw = json.loads(body)
        event = CloudEvent(**raw)
    else:
        return Response(status_code=400, content="Unknown event format")

    # Publish to internal bus
    await bus.publish(event)

    return Response(status_code=202)


@app.post("/events/batch")
async def receive_batch(request: Request) -> Response:
    """Receive batch of CloudEvents."""
    body = await request.body()
    raw_events = json.loads(body)

    events = [CloudEvent(**raw) for raw in raw_events]
    tasks = [bus.publish(event) for event in events]
    await asyncio.gather(*tasks, return_exceptions=True)

    return Response(status_code=202)
```

| Content Mode | Headers | Body | Use Case |
|---|---|---|---|
| Binary | `ce-*` headers | Raw data only | HTTP, efficient, binary data |
| Structured | None | Full JSON envelope | Message queues, logging |
| Batch | None | JSON array of events | High-throughput ingestion |

| CloudEvents Attribute | Required | Example |
|---|---|---|
| `specversion` | Yes | `"1.0"` |
| `id` | Yes | `"550e8400-e29b..."` |
| `source` | Yes | `"https://api.myapp.com/user-service"` |
| `type` | Yes | `"com.myapp.user.created"` |
| `time` | No (recommended) | `"2025-01-15T10:30:00Z"` |
| `subject` | No | `"u-123"` (resource ID) |
| `dataschema` | No | `"https://schemas.myapp.com/..."` |

Key patterns:
1. Use **CloudEvents** format for interoperability across services and clouds.
2. **Binary mode** puts attributes in HTTP headers; **structured mode** puts everything in JSON body.
3. Event types should use **reverse DNS** notation: `com.company.domain.action`.
4. **Deduplication middleware** with Redis prevents duplicate processing.
5. Pattern subscriptions (`com.myapp.order.*`) enable flexible event routing.
6. Always return **202 Accepted** -- process events asynchronously.'''
    ),
    (
        "backend/webhook-signature-verification",
        "Show webhook signature verification and security: HMAC signing, timestamp validation, replay attack prevention, and IP allowlisting.",
        '''Webhook signature verification and security:

```python
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import logging
import time
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


# ── Signature verification ────────────────────────────────────────

class WebhookVerifier:
    """Verifies webhook signatures for multiple providers."""

    def __init__(
        self,
        tolerance_seconds: int = 300,  # 5 minutes
    ) -> None:
        self._tolerance = tolerance_seconds

    def verify_hmac_sha256(
        self,
        payload: bytes,
        signature: str,
        secret: str,
        timestamp: str | None = None,
    ) -> bool:
        """Verify HMAC-SHA256 signature (Stripe-style).

        Signed message: {timestamp}.{payload}
        Header: sha256={hex_digest}
        """
        if timestamp:
            self._check_timestamp(int(timestamp))
            signed_payload = f"{timestamp}.".encode() + payload
        else:
            signed_payload = payload

        expected = hmac.new(
            secret.encode(),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()

        # Strip prefix if present
        sig = signature.removeprefix("sha256=")

        # Constant-time comparison prevents timing attacks
        return hmac.compare_digest(expected, sig)

    def verify_github(
        self,
        payload: bytes,
        signature: str,
        secret: str,
    ) -> bool:
        """Verify GitHub webhook signature.
        Header: X-Hub-Signature-256: sha256={hex}
        """
        expected = hmac.new(
            secret.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()

        sig = signature.removeprefix("sha256=")
        return hmac.compare_digest(expected, sig)

    def verify_stripe(
        self,
        payload: bytes,
        sig_header: str,
        secret: str,
    ) -> bool:
        """Verify Stripe webhook signature.
        Header: Stripe-Signature: t={timestamp},v1={sig}
        """
        parts: dict[str, str] = {}
        for item in sig_header.split(","):
            key, _, value = item.partition("=")
            parts[key.strip()] = value.strip()

        timestamp = parts.get("t", "")
        sig = parts.get("v1", "")

        if not timestamp or not sig:
            return False

        self._check_timestamp(int(timestamp))

        signed_payload = f"{timestamp}.".encode() + payload
        expected = hmac.new(
            secret.encode(),
            signed_payload,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, sig)

    def verify_slack(
        self,
        payload: bytes,
        signature: str,
        timestamp: str,
        secret: str,
    ) -> bool:
        """Verify Slack webhook signature.
        Headers: X-Slack-Signature, X-Slack-Request-Timestamp
        Signed: v0:{timestamp}:{body}
        """
        self._check_timestamp(int(timestamp))

        base_string = f"v0:{timestamp}:".encode() + payload
        expected = "v0=" + hmac.new(
            secret.encode(),
            base_string,
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def _check_timestamp(self, timestamp: int) -> None:
        """Prevent replay attacks by checking timestamp freshness."""
        now = int(time.time())
        if abs(now - timestamp) > self._tolerance:
            raise WebhookSecurityError(
                f"Timestamp too old/future: {abs(now - timestamp)}s "
                f"(tolerance: {self._tolerance}s)"
            )


class WebhookSecurityError(Exception):
    pass
```

```python
# ── FastAPI middleware for webhook verification ───────────────────

class WebhookSecurityMiddleware(BaseHTTPMiddleware):
    """Middleware that verifies webhook signatures and checks IPs."""

    def __init__(
        self,
        app: FastAPI,
        webhook_paths: dict[str, dict[str, Any]],
    ) -> None:
        """
        webhook_paths: {
            "/webhooks/stripe": {
                "provider": "stripe",
                "secret": "whsec_...",
                "allowed_ips": ["3.18.12.63", ...],
            },
            "/webhooks/github": {
                "provider": "github",
                "secret": "gh_webhook_secret",
            },
        }
        """
        super().__init__(app)
        self._paths = webhook_paths
        self._verifier = WebhookVerifier()

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        config = self._paths.get(path)

        if config is None or request.method != "POST":
            return await call_next(request)

        # IP allowlist check
        allowed_ips = config.get("allowed_ips", [])
        if allowed_ips:
            client_ip = request.client.host if request.client else ""
            if not self._check_ip(client_ip, allowed_ips):
                logger.warning(f"Rejected webhook from {client_ip}")
                raise HTTPException(403, "IP not allowed")

        # Read body for verification
        body = await request.body()
        provider = config["provider"]
        secret = config["secret"]

        try:
            if provider == "stripe":
                sig = request.headers.get("stripe-signature", "")
                if not self._verifier.verify_stripe(body, sig, secret):
                    raise WebhookSecurityError("Invalid Stripe signature")

            elif provider == "github":
                sig = request.headers.get("x-hub-signature-256", "")
                if not self._verifier.verify_github(body, sig, secret):
                    raise WebhookSecurityError("Invalid GitHub signature")

            elif provider == "slack":
                sig = request.headers.get("x-slack-signature", "")
                ts = request.headers.get("x-slack-request-timestamp", "")
                if not self._verifier.verify_slack(body, sig, ts, secret):
                    raise WebhookSecurityError("Invalid Slack signature")

            elif provider == "generic":
                sig = request.headers.get("x-webhook-signature", "")
                ts = request.headers.get("x-webhook-timestamp", "")
                if not self._verifier.verify_hmac_sha256(body, sig, secret, ts):
                    raise WebhookSecurityError("Invalid signature")

        except WebhookSecurityError as e:
            logger.warning(f"Webhook verification failed: {e}")
            raise HTTPException(401, "Signature verification failed")

        return await call_next(request)

    def _check_ip(
        self, client_ip: str, allowed: list[str]
    ) -> bool:
        """Check if client IP is in the allowlist (supports CIDR)."""
        try:
            addr = ipaddress.ip_address(client_ip)
            for allowed_ip in allowed:
                if "/" in allowed_ip:
                    network = ipaddress.ip_network(allowed_ip, strict=False)
                    if addr in network:
                        return True
                else:
                    if addr == ipaddress.ip_address(allowed_ip):
                        return True
            return False
        except ValueError:
            return False
```

```python
# ── Receiver-side webhook handler with full security ──────────────

from fastapi import FastAPI, Request
from pydantic import BaseModel

app = FastAPI()

# Configure webhook security
app.add_middleware(
    WebhookSecurityMiddleware,
    webhook_paths={
        "/webhooks/stripe": {
            "provider": "stripe",
            "secret": "whsec_test_secret",
            "allowed_ips": [
                "3.18.12.63",
                "3.130.192.0/24",
                "13.235.14.0/24",
            ],
        },
        "/webhooks/github": {
            "provider": "github",
            "secret": "github_webhook_secret",
            "allowed_ips": [
                "192.30.252.0/22",
                "185.199.108.0/22",
                "140.82.112.0/20",
            ],
        },
    },
)


# Idempotent webhook receiver
import redis.asyncio as aioredis

redis_client = aioredis.from_url("redis://localhost:6379")


async def is_duplicate(event_id: str) -> bool:
    """Check if we've already processed this event."""
    result = await redis_client.set(
        f"webhook:processed:{event_id}",
        "1",
        nx=True,  # only set if not exists
        ex=86400 * 7,  # keep for 7 days
    )
    return not result  # True if already existed


@app.post("/webhooks/stripe")
async def stripe_webhook(request: Request):
    body = await request.body()
    event = json.loads(body)

    event_id = event.get("id", "")
    if await is_duplicate(event_id):
        return {"status": "already_processed"}

    event_type = event.get("type", "")

    if event_type == "payment_intent.succeeded":
        await handle_payment_success(event["data"]["object"])
    elif event_type == "customer.subscription.deleted":
        await handle_subscription_cancelled(event["data"]["object"])

    return {"status": "processed"}


@app.post("/webhooks/github")
async def github_webhook(request: Request):
    body = await request.body()
    event = json.loads(body)

    event_type = request.headers.get("x-github-event", "")
    delivery_id = request.headers.get("x-github-delivery", "")

    if await is_duplicate(delivery_id):
        return {"status": "already_processed"}

    if event_type == "push":
        await handle_push(event)
    elif event_type == "pull_request":
        await handle_pr(event)

    return {"status": "processed"}


# Placeholder handlers
async def handle_payment_success(data: dict) -> None:
    pass

async def handle_subscription_cancelled(data: dict) -> None:
    pass

async def handle_push(data: dict) -> None:
    pass

async def handle_pr(data: dict) -> None:
    pass
```

| Security Layer | Attack Prevented | Implementation |
|---|---|---|
| HMAC signature | Tampering, spoofing | `hmac.compare_digest()` (constant-time) |
| Timestamp validation | Replay attacks | Reject if abs(now - ts) > 5 min |
| IP allowlisting | Unauthorized sources | CIDR range matching |
| Idempotency check | Duplicate processing | Redis SET NX with TTL |
| HTTPS only | Eavesdropping | TLS termination at LB |
| Rate limiting | DoS attacks | Sliding window limiter |

Key patterns:
1. Always use `hmac.compare_digest()` -- not `==` -- to prevent **timing attacks**.
2. Validate **timestamps** within 5 minutes to prevent replay attacks.
3. Different providers use different signing schemes -- abstract behind a `WebhookVerifier`.
4. **IP allowlisting** with CIDR support blocks unauthorized webhook sources.
5. Use **Redis SET NX** for idempotent processing -- deduplicate by event/delivery ID.
6. Return **200/202** quickly, then process asynchronously to avoid timeout retries.'''
    ),
    (
        "backend/webhook-fanout-subscriptions",
        "Show webhook fan-out and subscription management: subscriber registration, event filtering, delivery routing, and subscription lifecycle.",
        '''Webhook fan-out and subscription management:

```python
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, String, Boolean, DateTime, Text, Integer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# ── Subscription model ───────────────────────────────────────────

class Subscription(Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    url: Mapped[str] = mapped_column(String(2000))
    description: Mapped[str] = mapped_column(String(500), default="")
    secret: Mapped[str] = mapped_column(String(64))
    event_types: Mapped[str] = mapped_column(Text)  # JSON: ["user.*", "order.created"]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    verification_token: Mapped[str | None] = mapped_column(String(64), default=None)

    # Stats
    total_deliveries: Mapped[int] = mapped_column(Integer, default=0)
    total_failures: Mapped[int] = mapped_column(Integer, default=0)
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    last_delivery_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), default=None,
    )


# ── API schemas ───────────────────────────────────────────────────

class CreateSubscriptionRequest(BaseModel):
    url: str = Field(max_length=2000)
    description: str = Field(default="", max_length=500)
    event_types: list[str] = Field(min_length=1)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not v.startswith("https://"):
            raise ValueError("Webhook URL must use HTTPS")
        return v

    @field_validator("event_types")
    @classmethod
    def validate_event_types(cls, v: list[str]) -> list[str]:
        valid_patterns = {
            "user.created", "user.updated", "user.deleted",
            "order.created", "order.updated", "order.shipped",
            "payment.succeeded", "payment.failed",
            "user.*", "order.*", "payment.*", "*",
        }
        for et in v:
            if et not in valid_patterns:
                raise ValueError(f"Invalid event type: {et}")
        return v


class SubscriptionResponse(BaseModel):
    id: str
    url: str
    description: str
    event_types: list[str]
    is_active: bool
    is_verified: bool
    secret: str  # only shown on creation
    created_at: datetime
    stats: dict[str, int]


class SubscriptionListResponse(BaseModel):
    subscriptions: list[SubscriptionResponse]
    total: int
```

```python
# ── Subscription manager ─────────────────────────────────────────

import re
import httpx
import asyncio


class SubscriptionManager:
    """Manages webhook subscriptions with verification and health."""

    MAX_CONSECUTIVE_FAILURES = 10

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def create(
        self,
        tenant_id: str,
        request: CreateSubscriptionRequest,
    ) -> SubscriptionResponse:
        """Create a new subscription with URL verification."""
        secret = secrets.token_hex(32)
        verification_token = secrets.token_urlsafe(32)

        async with self._session_factory() as session:
            sub = Subscription(
                tenant_id=tenant_id,
                url=request.url,
                description=request.description,
                secret=secret,
                event_types=json.dumps(request.event_types),
                verification_token=verification_token,
                is_verified=False,
            )
            session.add(sub)
            await session.commit()
            await session.refresh(sub)

        # Send verification challenge
        asyncio.create_task(
            self._send_verification(sub.id, request.url, verification_token)
        )

        return self._to_response(sub, show_secret=True)

    async def _send_verification(
        self, sub_id: str, url: str, token: str
    ) -> None:
        """Send verification challenge to the endpoint.
        Endpoint must echo back the challenge token."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    url,
                    json={
                        "type": "webhook.verification",
                        "challenge": token,
                    },
                    headers={
                        "Content-Type": "application/json",
                        "X-Webhook-Verification": "true",
                    },
                )
                body = response.json()
                if (
                    response.status_code == 200
                    and body.get("challenge") == token
                ):
                    async with self._session_factory() as session:
                        sub = await session.get(Subscription, sub_id)
                        if sub:
                            sub.is_verified = True
                            sub.verification_token = None
                            await session.commit()
        except Exception as e:
            logger.warning(f"Verification failed for {sub_id}: {e}")

    async def list_subscriptions(
        self,
        tenant_id: str,
        active_only: bool = False,
    ) -> SubscriptionListResponse:
        async with self._session_factory() as session:
            stmt = select(Subscription).where(
                Subscription.tenant_id == tenant_id,
            )
            if active_only:
                stmt = stmt.where(Subscription.is_active == True)  # noqa: E712
            result = await session.execute(stmt)
            subs = result.scalars().all()
            return SubscriptionListResponse(
                subscriptions=[self._to_response(s) for s in subs],
                total=len(subs),
            )

    async def rotate_secret(self, sub_id: str, tenant_id: str) -> str:
        """Rotate the signing secret for a subscription."""
        new_secret = secrets.token_hex(32)
        async with self._session_factory() as session:
            sub = await session.get(Subscription, sub_id)
            if not sub or sub.tenant_id != tenant_id:
                raise ValueError("Subscription not found")
            sub.secret = new_secret
            await session.commit()
        return new_secret

    async def deactivate(self, sub_id: str, tenant_id: str) -> None:
        async with self._session_factory() as session:
            sub = await session.get(Subscription, sub_id)
            if not sub or sub.tenant_id != tenant_id:
                raise ValueError("Subscription not found")
            sub.is_active = False
            await session.commit()

    async def record_delivery(
        self, sub_id: str, success: bool
    ) -> None:
        """Update delivery stats and auto-disable on repeated failures."""
        async with self._session_factory() as session:
            sub = await session.get(Subscription, sub_id)
            if not sub:
                return
            sub.total_deliveries += 1
            sub.last_delivery_at = datetime.now(timezone.utc)

            if success:
                sub.consecutive_failures = 0
            else:
                sub.total_failures += 1
                sub.consecutive_failures += 1

                if sub.consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                    sub.is_active = False
                    logger.warning(
                        f"Auto-disabled subscription {sub_id} after "
                        f"{sub.consecutive_failures} consecutive failures"
                    )

            await session.commit()

    def _to_response(
        self, sub: Subscription, show_secret: bool = False
    ) -> SubscriptionResponse:
        return SubscriptionResponse(
            id=sub.id,
            url=sub.url,
            description=sub.description,
            event_types=json.loads(sub.event_types),
            is_active=sub.is_active,
            is_verified=sub.is_verified,
            secret=sub.secret if show_secret else "***",
            created_at=sub.created_at,
            stats={
                "total_deliveries": sub.total_deliveries,
                "total_failures": sub.total_failures,
                "consecutive_failures": sub.consecutive_failures,
            },
        )
```

```python
# ── Fan-out engine ────────────────────────────────────────────────

import fnmatch


class FanOutEngine:
    """Routes events to matching subscriptions."""

    def __init__(
        self,
        session_factory: Any,
        delivery_engine: Any,  # WebhookDeliveryEngine from pair 1
    ) -> None:
        self._session_factory = session_factory
        self._delivery = delivery_engine

    async def fan_out(
        self,
        tenant_id: str,
        event_type: str,
        payload: dict[str, Any],
        source_id: str | None = None,
    ) -> int:
        """Route an event to all matching subscriptions.
        Returns count of webhooks enqueued."""

        async with self._session_factory() as session:
            # Get all active, verified subscriptions for this tenant
            stmt = select(Subscription).where(
                Subscription.tenant_id == tenant_id,
                Subscription.is_active == True,  # noqa: E712
                Subscription.is_verified == True,  # noqa: E712
            )
            result = await session.execute(stmt)
            subscriptions = result.scalars().all()

        # Match event type against subscription patterns
        matched = []
        for sub in subscriptions:
            patterns = json.loads(sub.event_types)
            if self._matches(event_type, patterns):
                matched.append(sub)

        # Enqueue delivery for each matched subscription
        enqueued = 0
        async with self._session_factory() as session:
            for sub in matched:
                event_ids = await self._delivery.enqueue_event(
                    session=session,
                    event_type=event_type,
                    payload=payload,
                    source_id=source_id,
                )
                enqueued += len(event_ids)
            await session.commit()

        logger.info(
            f"Fan-out: {event_type} -> {len(matched)} subscriptions, "
            f"{enqueued} events enqueued"
        )
        return enqueued

    def _matches(self, event_type: str, patterns: list[str]) -> bool:
        """Check if event_type matches any subscription pattern."""
        for pattern in patterns:
            if pattern == "*":
                return True
            if pattern == event_type:
                return True
            # Wildcard match: "user.*" matches "user.created"
            if fnmatch.fnmatch(event_type, pattern):
                return True
        return False


# ── FastAPI webhook management API ────────────────────────────────

app = FastAPI(title="Webhook Management API")


@app.post("/api/webhooks/subscriptions", status_code=201)
async def create_subscription(
    request: CreateSubscriptionRequest,
    tenant_id: str = "demo-tenant",  # from auth middleware
) -> SubscriptionResponse:
    manager = SubscriptionManager(session_factory)
    return await manager.create(tenant_id, request)


@app.get("/api/webhooks/subscriptions")
async def list_subscriptions(
    active_only: bool = False,
    tenant_id: str = "demo-tenant",
) -> SubscriptionListResponse:
    manager = SubscriptionManager(session_factory)
    return await manager.list_subscriptions(tenant_id, active_only)


@app.post("/api/webhooks/subscriptions/{sub_id}/rotate-secret")
async def rotate_secret(
    sub_id: str,
    tenant_id: str = "demo-tenant",
) -> dict[str, str]:
    manager = SubscriptionManager(session_factory)
    new_secret = await manager.rotate_secret(sub_id, tenant_id)
    return {"secret": new_secret}


@app.delete("/api/webhooks/subscriptions/{sub_id}")
async def delete_subscription(
    sub_id: str,
    tenant_id: str = "demo-tenant",
) -> dict[str, str]:
    manager = SubscriptionManager(session_factory)
    await manager.deactivate(sub_id, tenant_id)
    return {"status": "deactivated"}


# Placeholder
session_factory = None
import logging
logger = logging.getLogger(__name__)
```

| Feature | Implementation | Why |
|---|---|---|
| URL verification | Challenge-response on create | Confirm endpoint ownership |
| HTTPS only | Validator rejects HTTP | Prevent eavesdropping |
| Secret rotation | `rotate_secret` endpoint | Regular credential hygiene |
| Auto-disable | 10 consecutive failures | Prevent wasting resources |
| Pattern matching | `fnmatch` glob patterns | Flexible event filtering |
| Delivery stats | Per-subscription counters | Monitoring and debugging |

Key patterns:
1. **Verify endpoints** on creation with a challenge-response handshake.
2. **Require HTTPS** -- reject HTTP URLs at the validation layer.
3. **Auto-disable** subscriptions after N consecutive failures to save resources.
4. Use **glob patterns** (`user.*`, `order.created`) for flexible event filtering.
5. Show the **secret only once** at creation time -- mask it on subsequent reads.
6. **Secret rotation** should be seamless -- accept both old and new secrets during transition.'''
    ),
]
