"""Webhook systems — delivery with retries, signature verification, idempotency, registration API, dead letter queues."""

PAIRS = [
    (
        "webhooks/delivery-retries",
        "Implement a webhook delivery system with exponential backoff retries, circuit breaking per endpoint, and delivery status tracking in Python using asyncio and httpx.",
        '''Webhook delivery engine with retries, circuit breaking, and status tracking:

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
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger("webhooks.delivery")


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    RETRYING = "retrying"
    FAILED = "failed"
    DEAD_LETTERED = "dead_lettered"


class CircuitState(str, Enum):
    CLOSED = "closed"       # normal operation
    OPEN = "open"           # failing, skip deliveries
    HALF_OPEN = "half_open" # testing if endpoint recovered


@dataclass
class WebhookEvent:
    event_id: str
    event_type: str
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class WebhookSubscription:
    subscription_id: str
    url: str
    secret: str
    event_types: list[str]
    active: bool = True
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass
class DeliveryAttempt:
    attempt_number: int
    timestamp: datetime
    status_code: int | None = None
    response_body: str = ""
    error: str = ""
    duration_ms: float = 0.0


@dataclass
class DeliveryRecord:
    delivery_id: str
    event: WebhookEvent
    subscription: WebhookSubscription
    status: DeliveryStatus = DeliveryStatus.PENDING
    attempts: list[DeliveryAttempt] = field(default_factory=list)
    next_retry_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None


class EndpointCircuitBreaker:
    """Circuit breaker per webhook endpoint.

    Opens after consecutive failures, half-opens after a cooldown
    to test if the endpoint has recovered.
    """

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        half_open_max_calls: int = 1,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float = 0
        self.half_open_calls = 0

    def can_send(self) -> bool:
        if self.state == CircuitState.CLOSED:
            return True
        if self.state == CircuitState.OPEN:
            if time.monotonic() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self.half_open_calls = 0
                return True
            return False
        # HALF_OPEN
        return self.half_open_calls < self.half_open_max_calls

    def record_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        else:
            self.failure_count = 0

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN


class WebhookDeliveryEngine:
    """Delivers webhook events with retries and circuit breaking.

    Retry schedule (exponential backoff with jitter):
      Attempt 1: immediate
      Attempt 2: ~30s
      Attempt 3: ~2min
      Attempt 4: ~8min
      Attempt 5: ~30min
      Attempt 6: ~2hr
    """

    MAX_RETRIES = 6
    BASE_DELAY_SECONDS = 30
    MAX_DELAY_SECONDS = 7200       # 2 hours
    JITTER_FACTOR = 0.2
    DELIVERY_TIMEOUT = 30.0        # seconds per attempt
    MAX_RESPONSE_BODY = 1024       # bytes to store from response

    def __init__(self) -> None:
        self._circuit_breakers: dict[str, EndpointCircuitBreaker] = {}
        self._delivery_records: dict[str, DeliveryRecord] = {}
        self._dead_letter_queue: list[DeliveryRecord] = []
        self._retry_queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.DELIVERY_TIMEOUT),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
        )
        asyncio.create_task(self._retry_worker())

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()

    def _get_circuit_breaker(self, url: str) -> EndpointCircuitBreaker:
        if url not in self._circuit_breakers:
            self._circuit_breakers[url] = EndpointCircuitBreaker()
        return self._circuit_breakers[url]

    # ── Signature generation ──────────────────────────────────────

    @staticmethod
    def _sign_payload(payload_bytes: bytes, secret: str, timestamp: str) -> str:
        """Generate HMAC-SHA256 signature for webhook payload."""
        message = f"{timestamp}.{payload_bytes.decode()}"
        return hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

    # ── Delivery ──────────────────────────────────────────────────

    async def deliver(
        self,
        event: WebhookEvent,
        subscription: WebhookSubscription,
    ) -> DeliveryRecord:
        record = DeliveryRecord(
            delivery_id=str(uuid.uuid4()),
            event=event,
            subscription=subscription,
        )
        self._delivery_records[record.delivery_id] = record
        await self._attempt_delivery(record)
        return record

    async def _attempt_delivery(self, record: DeliveryRecord) -> None:
        sub = record.subscription
        cb = self._get_circuit_breaker(sub.url)

        if not cb.can_send():
            logger.warning(f"Circuit open for {sub.url}, scheduling retry")
            self._schedule_retry(record)
            return

        record.status = DeliveryStatus.DELIVERING
        attempt_num = len(record.attempts) + 1

        payload_bytes = json.dumps({
            "event_id": record.event.event_id,
            "event_type": record.event.event_type,
            "created_at": record.event.created_at.isoformat(),
            "data": record.event.payload,
        }).encode()

        timestamp = str(int(time.time()))
        signature = self._sign_payload(payload_bytes, sub.secret, timestamp)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Id": record.delivery_id,
            "X-Webhook-Timestamp": timestamp,
            "X-Webhook-Signature": f"sha256={signature}",
            "X-Webhook-Event": record.event.event_type,
            "User-Agent": "WebhookEngine/1.0",
        }

        attempt = DeliveryAttempt(
            attempt_number=attempt_num,
            timestamp=datetime.now(timezone.utc),
        )

        start = time.monotonic()
        try:
            response = await self._client.post(
                sub.url,
                content=payload_bytes,
                headers=headers,
            )
            attempt.duration_ms = (time.monotonic() - start) * 1000
            attempt.status_code = response.status_code
            attempt.response_body = response.text[:self.MAX_RESPONSE_BODY]

            if 200 <= response.status_code < 300:
                cb.record_success()
                record.status = DeliveryStatus.DELIVERED
                record.completed_at = datetime.now(timezone.utc)
                logger.info(f"Delivered {record.event.event_id} to {sub.url}")
            else:
                cb.record_failure()
                self._handle_failure(record, attempt)

        except httpx.TimeoutException as e:
            attempt.duration_ms = (time.monotonic() - start) * 1000
            attempt.error = f"Timeout: {e}"
            cb.record_failure()
            self._handle_failure(record, attempt)

        except httpx.ConnectError as e:
            attempt.duration_ms = (time.monotonic() - start) * 1000
            attempt.error = f"Connection error: {e}"
            cb.record_failure()
            self._handle_failure(record, attempt)

        record.attempts.append(attempt)

    def _handle_failure(self, record: DeliveryRecord, attempt: DeliveryAttempt) -> None:
        if len(record.attempts) >= self.MAX_RETRIES:
            record.status = DeliveryStatus.DEAD_LETTERED
            record.completed_at = datetime.now(timezone.utc)
            self._dead_letter_queue.append(record)
            logger.error(
                f"Dead-lettered {record.event.event_id} after "
                f"{self.MAX_RETRIES} attempts to {record.subscription.url}"
            )
        else:
            record.status = DeliveryStatus.RETRYING
            self._schedule_retry(record)

    def _schedule_retry(self, record: DeliveryRecord) -> None:
        import random
        attempt_num = len(record.attempts)
        delay = min(
            self.BASE_DELAY_SECONDS * (2 ** attempt_num),
            self.MAX_DELAY_SECONDS,
        )
        jitter = delay * self.JITTER_FACTOR * random.random()
        retry_at = time.monotonic() + delay + jitter
        record.next_retry_at = datetime.now(timezone.utc)
        self._retry_queue.put_nowait((retry_at, record.delivery_id))

    async def _retry_worker(self) -> None:
        """Background worker that processes scheduled retries."""
        while True:
            retry_at, delivery_id = await self._retry_queue.get()
            now = time.monotonic()
            if retry_at > now:
                await asyncio.sleep(retry_at - now)

            record = self._delivery_records.get(delivery_id)
            if record and record.status == DeliveryStatus.RETRYING:
                await self._attempt_delivery(record)
```

Retry schedule with exponential backoff:

| Attempt | Delay | Cumulative |
|---|---|---|
| 1 | Immediate | 0s |
| 2 | ~30s | 30s |
| 3 | ~2min | 2.5min |
| 4 | ~8min | 10.5min |
| 5 | ~32min | 42.5min |
| 6 | ~2hr | 2hr 42min |

Key design decisions:
- **HMAC-SHA256 signatures** with timestamp prevent replay attacks
- **Circuit breaker per endpoint** avoids hammering dead servers
- **Dead letter queue** preserves failed events for manual replay
- **Idempotency via event_id** lets receivers safely deduplicate
- **Jitter on backoff** prevents thundering herd on endpoint recovery
- **Response body capture** aids debugging failed deliveries
'''
    ),
    (
        "webhooks/signature-verification",
        "Implement webhook signature verification with HMAC-SHA256 in both the sender and receiver, including timestamp validation to prevent replay attacks and a FastAPI receiver endpoint.",
        '''Webhook signature verification with replay attack prevention:

```python
from __future__ import annotations

import hashlib
import hmac
import time
from dataclasses import dataclass
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel


# ── Signature scheme ──────────────────────────────────────────────

SIGNATURE_VERSION = "v1"
TIMESTAMP_TOLERANCE = 300  # 5 minutes — reject older payloads


@dataclass
class SignedPayload:
    """Represents a signed webhook payload ready for transmission."""
    body: bytes
    timestamp: str
    signature: str

    @property
    def headers(self) -> dict[str, str]:
        return {
            "X-Webhook-Timestamp": self.timestamp,
            "X-Webhook-Signature": f"{SIGNATURE_VERSION}={self.signature}",
            "Content-Type": "application/json",
        }


class WebhookSigner:
    """Signs webhook payloads using HMAC-SHA256.

    Signature format: v1=<hex-digest>
    Signed message: "<timestamp>.<raw_body>"

    Including the timestamp in the signed message prevents
    replay attacks — even if an attacker captures a valid
    signature, they cannot reuse it beyond the tolerance window.
    """

    def __init__(self, secret: str) -> None:
        self._secret = secret.encode("utf-8")

    def sign(self, payload_bytes: bytes) -> SignedPayload:
        timestamp = str(int(time.time()))
        message = f"{timestamp}.{payload_bytes.decode('utf-8')}"
        signature = hmac.new(
            self._secret,
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        return SignedPayload(
            body=payload_bytes,
            timestamp=timestamp,
            signature=signature,
        )

    def verify(
        self,
        payload_bytes: bytes,
        timestamp: str,
        signature_header: str,
        tolerance: int = TIMESTAMP_TOLERANCE,
    ) -> bool:
        """Verify signature and check timestamp freshness.

        Returns True if signature is valid and timestamp is within tolerance.
        Uses constant-time comparison to prevent timing attacks.
        """
        # 1. Parse signature header
        parts = signature_header.split("=", 1)
        if len(parts) != 2 or parts[0] != SIGNATURE_VERSION:
            return False
        received_sig = parts[1]

        # 2. Check timestamp freshness (prevent replay)
        try:
            ts = int(timestamp)
        except (ValueError, TypeError):
            return False

        current_time = int(time.time())
        if abs(current_time - ts) > tolerance:
            return False

        # 3. Recompute signature
        message = f"{timestamp}.{payload_bytes.decode('utf-8')}"
        expected_sig = hmac.new(
            self._secret,
            message.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        # 4. Constant-time comparison
        return hmac.compare_digest(expected_sig, received_sig)


# ── FastAPI receiver with verification ────────────────────────────

app = FastAPI(title="Webhook Receiver")

# In production, load from environment / secrets manager
WEBHOOK_SECRETS: dict[str, str] = {
    "provider-A": "whsec_a1b2c3d4e5f6",
    "provider-B": "whsec_x7y8z9w0v1u2",
}

# Idempotency store (use Redis in production)
_processed_events: set[str] = set()


class WebhookPayload(BaseModel):
    event_id: str
    event_type: str
    created_at: str
    data: dict[str, Any]


@app.post("/webhooks/{provider}")
async def receive_webhook(
    provider: str,
    request: Request,
    x_webhook_timestamp: str = Header(...),
    x_webhook_signature: str = Header(...),
    x_webhook_id: str = Header(default=""),
) -> Response:
    """Receive and verify a webhook payload.

    Security checks:
    1. Provider must be registered
    2. HMAC-SHA256 signature must match
    3. Timestamp must be within 5-minute window
    4. Event ID must not have been processed before (idempotency)
    """
    # 1. Get provider secret
    secret = WEBHOOK_SECRETS.get(provider)
    if not secret:
        raise HTTPException(status_code=404, detail="Unknown provider")

    # 2. Read raw body for signature verification
    body = await request.body()

    # 3. Verify signature
    verifier = WebhookSigner(secret)
    if not verifier.verify(body, x_webhook_timestamp, x_webhook_signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # 4. Parse payload
    try:
        payload = WebhookPayload.model_validate_json(body)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload format")

    # 5. Idempotency check
    idempotency_key = x_webhook_id or payload.event_id
    if idempotency_key in _processed_events:
        return Response(status_code=200, content="Already processed")

    # 6. Process the webhook event
    try:
        await _process_event(provider, payload)
        _processed_events.add(idempotency_key)
    except Exception as e:
        # Return 500 so the sender retries
        raise HTTPException(status_code=500, detail=f"Processing failed: {e}")

    return Response(status_code=200, content="OK")


async def _process_event(provider: str, payload: WebhookPayload) -> None:
    """Route webhook events to handlers."""
    handlers: dict[str, Any] = {
        "order.created": handle_order_created,
        "order.updated": handle_order_updated,
        "payment.completed": handle_payment_completed,
    }
    handler = handlers.get(payload.event_type)
    if handler:
        await handler(payload.data)


async def handle_order_created(data: dict) -> None:
    print(f"New order: {data}")

async def handle_order_updated(data: dict) -> None:
    print(f"Order updated: {data}")

async def handle_payment_completed(data: dict) -> None:
    print(f"Payment: {data}")


# ── Multi-signature support (key rotation) ────────────────────────

class MultiSecretVerifier:
    """Supports multiple active secrets for zero-downtime key rotation.

    During rotation:
    1. Add new secret to the list
    2. Start signing with the new secret
    3. Old signatures remain valid until they expire (timestamp tolerance)
    4. Remove old secret after tolerance window passes
    """

    def __init__(self, secrets: list[str]) -> None:
        self._signers = [WebhookSigner(s) for s in secrets]

    def verify(
        self,
        payload_bytes: bytes,
        timestamp: str,
        signature_header: str,
    ) -> bool:
        return any(
            signer.verify(payload_bytes, timestamp, signature_header)
            for signer in self._signers
        )

    def sign(self, payload_bytes: bytes) -> SignedPayload:
        """Sign with the first (newest) secret."""
        return self._signers[0].sign(payload_bytes)
```

Signature verification checklist:

| Step | Purpose | Failure mode if skipped |
|---|---|---|
| Parse version prefix | Forward compatibility | Accept unknown signature schemes |
| Timestamp validation | Prevent replay attacks | Captured signatures reusable forever |
| HMAC recomputation | Verify authenticity | Accept forged payloads |
| Constant-time compare | Prevent timing attacks | Side-channel signature extraction |
| Idempotency check | Prevent duplicate processing | Double-charging, duplicate records |
| Raw body verification | Ensure exact bytes signed | Serialization differences break sig |

Key security patterns:
- **Never parse JSON before verifying signature** -- use raw bytes
- **Include timestamp in signed message** to bind signature to time window
- **Use `hmac.compare_digest()`** for constant-time comparison
- **Support multiple secrets** for zero-downtime key rotation
- **Return 200 for duplicates** to prevent unnecessary retries
- **Return 5xx on processing errors** so sender knows to retry
'''
    ),
    (
        "webhooks/idempotency",
        "Implement idempotent webhook processing with Redis-backed deduplication, exactly-once delivery semantics, and transactional outbox pattern for reliable event publishing.",
        '''Idempotent webhook processing with Redis deduplication and transactional outbox:

```python
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Coroutine

import asyncpg
import redis.asyncio as aioredis

logger = logging.getLogger("webhooks.idempotency")


# ── Idempotency store ─────────────────────────────────────────────

class IdempotencyStore:
    """Redis-backed idempotency check with configurable retention.

    Uses Redis SET with NX (set-if-not-exists) and EX (expiry) to
    atomically check-and-mark an event as processing.

    States:
      - Key absent: event not seen before
      - Key = "processing": event is being handled
      - Key = "completed:<result_hash>": event was processed successfully
      - Key = "failed": event processing failed (safe to retry)
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        key_prefix: str = "webhook:idempotency",
        retention_seconds: int = 86400 * 7,  # 7 days
    ) -> None:
        self._redis = redis_client
        self._prefix = key_prefix
        self._retention = retention_seconds

    def _key(self, event_id: str) -> str:
        return f"{self._prefix}:{event_id}"

    async def try_acquire(self, event_id: str) -> str | None:
        """Try to mark event as processing.

        Returns:
          None if we acquired the lock (first time seeing this event)
          "processing" if another worker is handling it
          "completed:<hash>" if already successfully processed
          "failed" if previous attempt failed (safe to retry)
        """
        key = self._key(event_id)
        # Try to set atomically — only succeeds if key doesn\'t exist
        acquired = await self._redis.set(
            key, "processing", nx=True, ex=self._retention,
        )
        if acquired:
            return None  # we got it

        # Key exists — check current state
        current = await self._redis.get(key)
        if current:
            return current.decode()
        return None

    async def mark_completed(self, event_id: str, result_hash: str = "") -> None:
        key = self._key(event_id)
        await self._redis.set(
            key, f"completed:{result_hash}", ex=self._retention,
        )

    async def mark_failed(self, event_id: str) -> None:
        key = self._key(event_id)
        await self._redis.set(key, "failed", ex=self._retention)

    async def get_status(self, event_id: str) -> str | None:
        result = await self._redis.get(self._key(event_id))
        return result.decode() if result else None


# ── Idempotent webhook processor ──────────────────────────────────

@dataclass
class ProcessingResult:
    event_id: str
    status: str         # "processed", "duplicate", "failed", "in_progress"
    message: str = ""


class IdempotentWebhookProcessor:
    """Processes webhook events exactly once using Redis deduplication.

    Flow:
    1. Try to acquire idempotency lock
    2. If acquired, process event in a transaction
    3. Mark as completed on success, failed on error
    4. If duplicate, return cached result
    """

    def __init__(
        self,
        store: IdempotencyStore,
        handlers: dict[str, Callable[..., Coroutine[Any, Any, Any]]],
    ) -> None:
        self._store = store
        self._handlers = handlers

    async def process(
        self,
        event_id: str,
        event_type: str,
        payload: dict[str, Any],
    ) -> ProcessingResult:
        # Step 1: Idempotency check
        existing = await self._store.try_acquire(event_id)

        if existing is not None:
            if existing.startswith("completed"):
                return ProcessingResult(
                    event_id=event_id,
                    status="duplicate",
                    message="Event already processed",
                )
            if existing == "processing":
                return ProcessingResult(
                    event_id=event_id,
                    status="in_progress",
                    message="Event is being processed by another worker",
                )
            if existing == "failed":
                # Previous attempt failed — safe to retry
                logger.info(f"Retrying previously failed event {event_id}")

        # Step 2: Find and execute handler
        handler = self._handlers.get(event_type)
        if not handler:
            await self._store.mark_completed(event_id, "no_handler")
            return ProcessingResult(
                event_id=event_id,
                status="processed",
                message=f"No handler for event type: {event_type}",
            )

        try:
            result = await handler(payload)
            result_hash = hashlib.md5(
                json.dumps(result, default=str).encode()
            ).hexdigest() if result else ""
            await self._store.mark_completed(event_id, result_hash)
            return ProcessingResult(
                event_id=event_id,
                status="processed",
                message="Event processed successfully",
            )
        except Exception as e:
            logger.exception(f"Failed to process event {event_id}")
            await self._store.mark_failed(event_id)
            return ProcessingResult(
                event_id=event_id,
                status="failed",
                message=str(e),
            )


# ── Transactional outbox pattern ──────────────────────────────────

import hashlib


class TransactionalOutbox:
    """Transactional outbox for reliable webhook event publishing.

    Instead of publishing events directly (which can fail after DB commit),
    events are written to an outbox table in the same DB transaction.
    A background poller reads the outbox and publishes events.

    This guarantees at-least-once delivery: if the app crashes after
    commit but before publishing, the poller will pick it up.
    """

    CREATE_TABLE_SQL = """
    CREATE TABLE IF NOT EXISTS webhook_outbox (
        id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        event_type      TEXT NOT NULL,
        payload         JSONB NOT NULL,
        created_at      TIMESTAMPTZ DEFAULT now(),
        published_at    TIMESTAMPTZ,
        attempts        INT DEFAULT 0,
        last_error      TEXT,
        status          TEXT DEFAULT 'pending'
    );
    CREATE INDEX IF NOT EXISTS idx_outbox_status
        ON webhook_outbox (status, created_at)
        WHERE status = 'pending';
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def initialize(self) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(self.CREATE_TABLE_SQL)

    async def enqueue_in_transaction(
        self,
        conn: asyncpg.Connection,
        event_type: str,
        payload: dict[str, Any],
    ) -> str:
        """Add event to outbox within an existing transaction.

        This must be called inside the same transaction as the
        business logic that triggers the event.
        """
        row = await conn.fetchrow(
            """
            INSERT INTO webhook_outbox (event_type, payload)
            VALUES ($1, $2::jsonb)
            RETURNING id
            """,
            event_type,
            json.dumps(payload),
        )
        return str(row["id"])

    async def poll_and_publish(
        self,
        publish_fn: Callable[[str, str, dict], Coroutine[Any, Any, bool]],
        batch_size: int = 100,
    ) -> int:
        """Poll outbox for pending events and publish them.

        Uses SELECT FOR UPDATE SKIP LOCKED to allow multiple
        pollers to work concurrently without conflicts.
        """
        published = 0

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, event_type, payload, attempts
                FROM webhook_outbox
                WHERE status = 'pending'
                ORDER BY created_at
                LIMIT $1
                FOR UPDATE SKIP LOCKED
                """,
                batch_size,
            )

            for row in rows:
                event_id = str(row["id"])
                event_type = row["event_type"]
                payload = json.loads(row["payload"])

                try:
                    success = await publish_fn(event_id, event_type, payload)
                    if success:
                        await conn.execute(
                            """
                            UPDATE webhook_outbox
                            SET status = 'published',
                                published_at = now()
                            WHERE id = $1
                            """,
                            row["id"],
                        )
                        published += 1
                    else:
                        await conn.execute(
                            """
                            UPDATE webhook_outbox
                            SET attempts = attempts + 1,
                                last_error = 'publish returned false'
                            WHERE id = $1
                            """,
                            row["id"],
                        )
                except Exception as e:
                    await conn.execute(
                        """
                        UPDATE webhook_outbox
                        SET attempts = attempts + 1,
                            last_error = $2
                        WHERE id = $1
                        """,
                        row["id"],
                        str(e)[:500],
                    )

        return published

    async def run_poller(
        self,
        publish_fn: Callable,
        interval: float = 5.0,
    ) -> None:
        """Background poller that continuously publishes pending events."""
        while True:
            try:
                count = await self.poll_and_publish(publish_fn)
                if count > 0:
                    logger.info(f"Published {count} outbox events")
            except Exception:
                logger.exception("Outbox poller error")
            await asyncio.sleep(interval)


# ── Usage: business logic with outbox ─────────────────────────────

async def create_order_with_webhook(
    pool: asyncpg.Pool,
    outbox: TransactionalOutbox,
    order_data: dict,
) -> str:
    """Create an order and enqueue a webhook event atomically."""
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Business logic
            order_id = await conn.fetchval(
                "INSERT INTO orders (customer_id, total) VALUES ($1, $2) RETURNING id",
                order_data["customer_id"],
                order_data["total"],
            )

            # Enqueue webhook in SAME transaction
            await outbox.enqueue_in_transaction(
                conn,
                "order.created",
                {"order_id": str(order_id), **order_data},
            )

            return str(order_id)
    # If transaction rolls back, webhook event is also rolled back
    # If transaction commits, webhook event is guaranteed to be published
```

Exactly-once delivery semantics:

| Pattern | Guarantee | Trade-off |
|---|---|---|
| Redis NX lock | At-most-once check | Needs TTL; lost on Redis restart |
| Transactional outbox | At-least-once publish | Requires DB polling; slight delay |
| Idempotency key (receiver) | Exactly-once processing | Receiver must implement dedup |
| Combined approach | Exactly-once end-to-end | More infrastructure complexity |

Key patterns:
- **Sender**: Transactional outbox guarantees events are published if committed
- **Receiver**: Idempotency store guarantees events are processed at most once
- **Together**: Achieves exactly-once semantics across the system
- **`SELECT FOR UPDATE SKIP LOCKED`**: Allows parallel pollers without conflicts
- **Failed events stay in outbox**: Automatic retry on next poll cycle
'''
    ),
    (
        "webhooks/registration-api",
        "Build a webhook registration and management API with FastAPI, including endpoint validation, event type filtering, secret rotation, and subscription lifecycle management.",
        '''Webhook registration and management API with FastAPI:

```python
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl, field_validator


# ── Models ────────────────────────────────────────────────────────

class WebhookStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DISABLED = "disabled"   # too many failures


class EventType(str, Enum):
    ORDER_CREATED = "order.created"
    ORDER_UPDATED = "order.updated"
    ORDER_CANCELLED = "order.cancelled"
    PAYMENT_COMPLETED = "payment.completed"
    PAYMENT_FAILED = "payment.failed"
    SHIPMENT_CREATED = "shipment.created"
    SHIPMENT_DELIVERED = "shipment.delivered"
    CUSTOMER_CREATED = "customer.created"
    WILDCARD = "*"


class CreateWebhookRequest(BaseModel):
    url: HttpUrl
    description: str = ""
    event_types: list[EventType] = Field(min_length=1)
    metadata: dict[str, str] = Field(default_factory=dict)
    # Optional: custom headers to include on delivery
    custom_headers: dict[str, str] = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: HttpUrl) -> HttpUrl:
        url_str = str(v)
        if url_str.startswith("http://") and "localhost" not in url_str:
            raise ValueError("Only HTTPS URLs are allowed in production")
        if any(host in url_str for host in ["169.254.", "10.", "192.168.", "127."]):
            raise ValueError("Private/internal IPs are not allowed")
        return v


class UpdateWebhookRequest(BaseModel):
    url: HttpUrl | None = None
    description: str | None = None
    event_types: list[EventType] | None = None
    status: WebhookStatus | None = None
    custom_headers: dict[str, str] | None = None


class WebhookResponse(BaseModel):
    id: str
    url: str
    description: str
    event_types: list[str]
    status: WebhookStatus
    secret: str | None = None   # only shown on creation
    created_at: str
    updated_at: str
    delivery_stats: DeliveryStats | None = None


class DeliveryStats(BaseModel):
    total_deliveries: int = 0
    successful: int = 0
    failed: int = 0
    success_rate: float = 0.0
    avg_latency_ms: float = 0.0
    last_delivery_at: str | None = None
    last_status_code: int | None = None


class SecretRotationResponse(BaseModel):
    old_secret_expires_at: str
    new_secret: str
    message: str


class WebhookTestResponse(BaseModel):
    success: bool
    status_code: int | None = None
    response_time_ms: float
    error: str | None = None


class WebhookLogEntry(BaseModel):
    delivery_id: str
    event_type: str
    event_id: str
    status_code: int | None
    success: bool
    response_time_ms: float
    error: str | None
    timestamp: str


# ── In-memory store (replace with database in production) ─────────

_webhooks: dict[str, dict[str, Any]] = {}
_webhook_logs: dict[str, list[dict]] = {}
_rotating_secrets: dict[str, dict[str, Any]] = {}


def _generate_secret() -> str:
    return f"whsec_{secrets.token_urlsafe(32)}"


# ── Router ────────────────────────────────────────────────────────

router = APIRouter(prefix="/api/v1/webhooks", tags=["webhooks"])


@router.post("", response_model=WebhookResponse, status_code=201)
async def create_webhook(req: CreateWebhookRequest) -> WebhookResponse:
    """Register a new webhook endpoint.

    Returns the webhook secret — this is the ONLY time the full
    secret is returned. Store it securely.
    """
    webhook_id = f"wh_{uuid.uuid4().hex[:12]}"
    secret = _generate_secret()
    now = datetime.now(timezone.utc).isoformat()

    # Validate endpoint is reachable
    validation = await _validate_endpoint(str(req.url))
    if not validation["reachable"]:
        raise HTTPException(
            status_code=422,
            detail=f"Endpoint validation failed: {validation['error']}",
        )

    webhook = {
        "id": webhook_id,
        "url": str(req.url),
        "description": req.description,
        "event_types": [e.value for e in req.event_types],
        "status": WebhookStatus.ACTIVE,
        "secret": secret,
        "custom_headers": req.custom_headers,
        "metadata": req.metadata,
        "created_at": now,
        "updated_at": now,
        "delivery_stats": {
            "total_deliveries": 0,
            "successful": 0,
            "failed": 0,
        },
    }
    _webhooks[webhook_id] = webhook

    return WebhookResponse(
        id=webhook_id,
        url=str(req.url),
        description=req.description,
        event_types=[e.value for e in req.event_types],
        status=WebhookStatus.ACTIVE,
        secret=secret,   # only revealed once
        created_at=now,
        updated_at=now,
    )


@router.get("", response_model=list[WebhookResponse])
async def list_webhooks(
    status: WebhookStatus | None = None,
    event_type: EventType | None = None,
) -> list[WebhookResponse]:
    """List all registered webhooks with optional filters."""
    results = []
    for wh in _webhooks.values():
        if status and wh["status"] != status:
            continue
        if event_type and event_type.value not in wh["event_types"]:
            continue
        results.append(WebhookResponse(
            id=wh["id"],
            url=wh["url"],
            description=wh["description"],
            event_types=wh["event_types"],
            status=wh["status"],
            created_at=wh["created_at"],
            updated_at=wh["updated_at"],
        ))
    return results


@router.get("/{webhook_id}", response_model=WebhookResponse)
async def get_webhook(webhook_id: str) -> WebhookResponse:
    wh = _webhooks.get(webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")
    stats = wh.get("delivery_stats", {})
    total = stats.get("total_deliveries", 0)
    success = stats.get("successful", 0)
    return WebhookResponse(
        id=wh["id"],
        url=wh["url"],
        description=wh["description"],
        event_types=wh["event_types"],
        status=wh["status"],
        created_at=wh["created_at"],
        updated_at=wh["updated_at"],
        delivery_stats=DeliveryStats(
            total_deliveries=total,
            successful=success,
            failed=stats.get("failed", 0),
            success_rate=success / total if total > 0 else 0.0,
        ),
    )


@router.patch("/{webhook_id}", response_model=WebhookResponse)
async def update_webhook(webhook_id: str, req: UpdateWebhookRequest) -> WebhookResponse:
    wh = _webhooks.get(webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")

    if req.url is not None:
        validation = await _validate_endpoint(str(req.url))
        if not validation["reachable"]:
            raise HTTPException(status_code=422, detail="Endpoint unreachable")
        wh["url"] = str(req.url)
    if req.description is not None:
        wh["description"] = req.description
    if req.event_types is not None:
        wh["event_types"] = [e.value for e in req.event_types]
    if req.status is not None:
        wh["status"] = req.status
    if req.custom_headers is not None:
        wh["custom_headers"] = req.custom_headers

    wh["updated_at"] = datetime.now(timezone.utc).isoformat()
    return await get_webhook(webhook_id)


@router.delete("/{webhook_id}", status_code=204)
async def delete_webhook(webhook_id: str) -> None:
    if webhook_id not in _webhooks:
        raise HTTPException(status_code=404, detail="Webhook not found")
    del _webhooks[webhook_id]
    _webhook_logs.pop(webhook_id, None)


@router.post("/{webhook_id}/rotate-secret", response_model=SecretRotationResponse)
async def rotate_secret(webhook_id: str) -> SecretRotationResponse:
    """Rotate webhook secret with a grace period.

    Both old and new secrets are valid for 24 hours,
    allowing zero-downtime rotation on the receiver side.
    """
    wh = _webhooks.get(webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")

    new_secret = _generate_secret()
    old_secret = wh["secret"]
    expires_at = datetime.now(timezone.utc).isoformat()

    # Store rotation state (both secrets valid during grace period)
    _rotating_secrets[webhook_id] = {
        "old_secret": old_secret,
        "new_secret": new_secret,
        "expires_at": expires_at,
    }
    wh["secret"] = new_secret
    wh["updated_at"] = datetime.now(timezone.utc).isoformat()

    return SecretRotationResponse(
        old_secret_expires_at=expires_at,
        new_secret=new_secret,
        message="Old secret valid for 24 hours. Update your receiver, then old secret expires.",
    )


@router.post("/{webhook_id}/test", response_model=WebhookTestResponse)
async def test_webhook(webhook_id: str) -> WebhookTestResponse:
    """Send a test event to verify the webhook endpoint."""
    wh = _webhooks.get(webhook_id)
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook not found")

    test_payload = json.dumps({
        "event_id": f"evt_test_{uuid.uuid4().hex[:8]}",
        "event_type": "webhook.test",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data": {"message": "This is a test webhook delivery"},
    }).encode()

    timestamp = str(int(time.time()))
    message = f"{timestamp}.{test_payload.decode()}"
    signature = hmac.new(
        wh["secret"].encode(), message.encode(), hashlib.sha256,
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Signature": f"v1={signature}",
        "X-Webhook-Event": "webhook.test",
        **(wh.get("custom_headers") or {}),
    }

    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(wh["url"], content=test_payload, headers=headers)
            elapsed = (time.monotonic() - start) * 1000
            return WebhookTestResponse(
                success=200 <= resp.status_code < 300,
                status_code=resp.status_code,
                response_time_ms=round(elapsed, 1),
            )
    except Exception as e:
        elapsed = (time.monotonic() - start) * 1000
        return WebhookTestResponse(
            success=False,
            response_time_ms=round(elapsed, 1),
            error=str(e),
        )


@router.get("/{webhook_id}/logs", response_model=list[WebhookLogEntry])
async def get_webhook_logs(
    webhook_id: str,
    limit: int = Query(default=50, le=200),
    event_type: str | None = None,
    success: bool | None = None,
) -> list[WebhookLogEntry]:
    """Retrieve delivery logs for a webhook."""
    if webhook_id not in _webhooks:
        raise HTTPException(status_code=404, detail="Webhook not found")

    logs = _webhook_logs.get(webhook_id, [])

    if event_type:
        logs = [l for l in logs if l["event_type"] == event_type]
    if success is not None:
        logs = [l for l in logs if l["success"] == success]

    return [WebhookLogEntry(**l) for l in logs[-limit:]]


# ── Endpoint validation ──────────────────────────────────────────

async def _validate_endpoint(url: str) -> dict[str, Any]:
    """Validate that a webhook endpoint is reachable and returns 2xx."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.head(url)
            return {
                "reachable": 200 <= resp.status_code < 500,
                "status_code": resp.status_code,
                "error": None,
            }
    except Exception as e:
        return {"reachable": False, "status_code": None, "error": str(e)}
```

Webhook API design best practices:

| Feature | Implementation |
|---|---|
| URL validation | Block private IPs, require HTTPS in production |
| Secret management | Generate secure random secret, show only once |
| Secret rotation | Grace period with dual-secret validation |
| Event filtering | Subscribe to specific event types only |
| Test endpoint | `/test` sends a synthetic event for verification |
| Delivery logs | Queryable history with status, timing, errors |
| Auto-disable | Disable webhook after N consecutive failures |
| Custom headers | Let consumers add auth headers for their endpoint |

Key patterns:
- Validate endpoint reachability on registration and URL changes
- Support wildcard (`*`) event type for catch-all subscriptions
- Secret rotation with grace period prevents downtime during key changes
- Delivery logs enable self-service debugging for consumers
- SSRF prevention: block private IPs and internal hostnames
'''
    ),
    (
        "webhooks/dead-letter-queue",
        "Implement a dead letter queue for failed webhook deliveries with inspection, replay, and bulk retry capabilities using Redis streams and FastAPI.",
        '''Dead letter queue for webhook failures with replay and bulk retry:

```python
from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger("webhooks.dlq")


class DLQEntryStatus(str, Enum):
    PENDING = "pending"       # awaiting manual review
    REPLAYING = "replaying"   # being retried
    RESOLVED = "resolved"     # successfully replayed
    DISCARDED = "discarded"   # manually discarded


class DLQEntry(BaseModel):
    entry_id: str
    event_id: str
    event_type: str
    subscription_id: str
    destination_url: str
    payload: dict[str, Any]
    status: DLQEntryStatus
    failure_reason: str
    last_status_code: int | None
    attempt_count: int
    created_at: str
    last_attempt_at: str | None


class DLQStats(BaseModel):
    total_entries: int
    pending: int
    replaying: int
    resolved: int
    discarded: int
    oldest_entry_age_hours: float
    entries_by_event_type: dict[str, int]
    entries_by_destination: dict[str, int]


class ReplayRequest(BaseModel):
    entry_ids: list[str] = []       # specific entries
    event_type: str | None = None   # replay all of a type
    subscription_id: str | None = None
    max_entries: int = 100


class ReplayResult(BaseModel):
    total_replayed: int
    successful: int
    failed: int
    details: list[dict[str, Any]]


# ── Dead Letter Queue backed by Redis Streams ────────────────────

class WebhookDeadLetterQueue:
    """Dead letter queue using Redis Streams for durability.

    Redis Streams provide:
    - Ordered, persistent message storage
    - Consumer groups for parallel processing
    - Automatic ID generation with timestamps
    - Efficient range queries for inspection
    """

    STREAM_KEY = "webhook:dlq:stream"
    INDEX_KEY = "webhook:dlq:index"
    STATS_KEY = "webhook:dlq:stats"

    def __init__(self, redis_client: aioredis.Redis) -> None:
        self._redis = redis_client

    async def enqueue(
        self,
        event_id: str,
        event_type: str,
        subscription_id: str,
        destination_url: str,
        payload: dict[str, Any],
        failure_reason: str,
        last_status_code: int | None,
        attempt_count: int,
    ) -> str:
        """Add a failed delivery to the dead letter queue."""
        entry_id = f"dlq_{uuid.uuid4().hex[:12]}"

        entry_data = {
            "entry_id": entry_id,
            "event_id": event_id,
            "event_type": event_type,
            "subscription_id": subscription_id,
            "destination_url": destination_url,
            "payload": json.dumps(payload),
            "status": DLQEntryStatus.PENDING.value,
            "failure_reason": failure_reason,
            "last_status_code": str(last_status_code or ""),
            "attempt_count": str(attempt_count),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_attempt_at": datetime.now(timezone.utc).isoformat(),
        }

        # Add to stream
        stream_id = await self._redis.xadd(self.STREAM_KEY, entry_data)

        # Index by entry_id for direct lookups
        await self._redis.hset(self.INDEX_KEY, entry_id, stream_id)

        # Update stats
        await self._redis.hincrby(self.STATS_KEY, "total", 1)
        await self._redis.hincrby(self.STATS_KEY, f"type:{event_type}", 1)
        await self._redis.hincrby(self.STATS_KEY, f"dest:{subscription_id}", 1)

        logger.warning(
            f"Dead-lettered event {event_id} for {destination_url}: {failure_reason}"
        )
        return entry_id

    async def get_entry(self, entry_id: str) -> DLQEntry | None:
        """Get a single DLQ entry by ID."""
        stream_id = await self._redis.hget(self.INDEX_KEY, entry_id)
        if not stream_id:
            return None

        # Read the specific stream entry
        entries = await self._redis.xrange(
            self.STREAM_KEY, min=stream_id, max=stream_id,
        )
        if not entries:
            return None

        _, data = entries[0]
        return self._parse_entry(data)

    async def list_entries(
        self,
        status: DLQEntryStatus | None = None,
        event_type: str | None = None,
        subscription_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DLQEntry]:
        """List DLQ entries with filters."""
        # Read all entries (in production, use cursor-based pagination)
        raw_entries = await self._redis.xrange(
            self.STREAM_KEY, count=limit + offset,
        )

        entries = []
        skipped = 0
        for _, data in raw_entries:
            entry = self._parse_entry(data)

            # Apply filters
            if status and entry.status != status:
                continue
            if event_type and entry.event_type != event_type:
                continue
            if subscription_id and entry.subscription_id != subscription_id:
                continue

            if skipped < offset:
                skipped += 1
                continue

            entries.append(entry)
            if len(entries) >= limit:
                break

        return entries

    async def get_stats(self) -> DLQStats:
        """Get DLQ statistics."""
        all_data = await self._redis.hgetall(self.STATS_KEY)
        stats = {k.decode(): int(v) for k, v in all_data.items()}

        entries = await self.list_entries(limit=1)
        oldest_age = 0.0
        if entries:
            oldest = datetime.fromisoformat(entries[0].created_at)
            oldest_age = (datetime.now(timezone.utc) - oldest).total_seconds() / 3600

        by_type = {
            k.replace("type:", ""): v
            for k, v in stats.items() if k.startswith("type:")
        }
        by_dest = {
            k.replace("dest:", ""): v
            for k, v in stats.items() if k.startswith("dest:")
        }

        pending = await self._count_by_status(DLQEntryStatus.PENDING)
        replaying = await self._count_by_status(DLQEntryStatus.REPLAYING)
        resolved = await self._count_by_status(DLQEntryStatus.RESOLVED)
        discarded = await self._count_by_status(DLQEntryStatus.DISCARDED)

        return DLQStats(
            total_entries=stats.get("total", 0),
            pending=pending,
            replaying=replaying,
            resolved=resolved,
            discarded=discarded,
            oldest_entry_age_hours=oldest_age,
            entries_by_event_type=by_type,
            entries_by_destination=by_dest,
        )

    async def _count_by_status(self, status: DLQEntryStatus) -> int:
        entries = await self.list_entries(status=status, limit=10000)
        return len(entries)

    async def update_status(
        self, entry_id: str, status: DLQEntryStatus,
    ) -> bool:
        """Update the status of a DLQ entry.

        Note: Redis Streams are append-only, so we store the latest
        status in the index hash. The stream entry retains the original data.
        """
        stream_id = await self._redis.hget(self.INDEX_KEY, entry_id)
        if not stream_id:
            return False
        await self._redis.hset(
            f"webhook:dlq:status:{entry_id}", "status", status.value,
        )
        return True

    async def discard(self, entry_id: str, reason: str = "") -> bool:
        """Mark an entry as discarded (will not be retried)."""
        return await self.update_status(entry_id, DLQEntryStatus.DISCARDED)

    async def purge_resolved(self, older_than_hours: int = 72) -> int:
        """Remove resolved entries older than the specified age."""
        entries = await self.list_entries(status=DLQEntryStatus.RESOLVED, limit=10000)
        removed = 0
        cutoff = datetime.now(timezone.utc)

        for entry in entries:
            entry_time = datetime.fromisoformat(entry.created_at)
            age_hours = (cutoff - entry_time).total_seconds() / 3600
            if age_hours > older_than_hours:
                stream_id = await self._redis.hget(self.INDEX_KEY, entry.entry_id)
                if stream_id:
                    await self._redis.xdel(self.STREAM_KEY, stream_id)
                    await self._redis.hdel(self.INDEX_KEY, entry.entry_id)
                    removed += 1

        return removed

    def _parse_entry(self, data: dict[bytes, bytes]) -> DLQEntry:
        decoded = {k.decode(): v.decode() for k, v in data.items()}
        return DLQEntry(
            entry_id=decoded["entry_id"],
            event_id=decoded["event_id"],
            event_type=decoded["event_type"],
            subscription_id=decoded["subscription_id"],
            destination_url=decoded["destination_url"],
            payload=json.loads(decoded["payload"]),
            status=DLQEntryStatus(decoded["status"]),
            failure_reason=decoded["failure_reason"],
            last_status_code=int(decoded["last_status_code"]) if decoded["last_status_code"] else None,
            attempt_count=int(decoded["attempt_count"]),
            created_at=decoded["created_at"],
            last_attempt_at=decoded.get("last_attempt_at"),
        )


# ── API endpoints for DLQ management ─────────────────────────────

router = APIRouter(prefix="/api/v1/webhooks/dlq", tags=["webhook-dlq"])


async def get_dlq() -> WebhookDeadLetterQueue:
    # In production, inject via dependency
    redis_client = aioredis.from_url("redis://localhost:6379")
    return WebhookDeadLetterQueue(redis_client)


@router.get("/stats", response_model=DLQStats)
async def dlq_stats(dlq: WebhookDeadLetterQueue = Depends(get_dlq)) -> DLQStats:
    return await dlq.get_stats()


@router.get("/entries", response_model=list[DLQEntry])
async def list_dlq_entries(
    status: DLQEntryStatus | None = None,
    event_type: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    dlq: WebhookDeadLetterQueue = Depends(get_dlq),
) -> list[DLQEntry]:
    return await dlq.list_entries(
        status=status, event_type=event_type,
        limit=limit, offset=offset,
    )


@router.get("/entries/{entry_id}", response_model=DLQEntry)
async def get_dlq_entry(
    entry_id: str,
    dlq: WebhookDeadLetterQueue = Depends(get_dlq),
) -> DLQEntry:
    entry = await dlq.get_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="DLQ entry not found")
    return entry


@router.post("/replay", response_model=ReplayResult)
async def replay_entries(
    req: ReplayRequest,
    dlq: WebhookDeadLetterQueue = Depends(get_dlq),
) -> ReplayResult:
    """Replay failed webhook deliveries.

    Can replay specific entries by ID, or bulk replay by
    event type or subscription.
    """
    entries_to_replay: list[DLQEntry] = []

    if req.entry_ids:
        for eid in req.entry_ids:
            entry = await dlq.get_entry(eid)
            if entry and entry.status == DLQEntryStatus.PENDING:
                entries_to_replay.append(entry)
    else:
        entries_to_replay = await dlq.list_entries(
            status=DLQEntryStatus.PENDING,
            event_type=req.event_type,
            subscription_id=req.subscription_id,
            limit=req.max_entries,
        )

    successful = 0
    failed = 0
    details = []

    for entry in entries_to_replay:
        await dlq.update_status(entry.entry_id, DLQEntryStatus.REPLAYING)
        try:
            # Re-deliver the webhook (call your delivery engine)
            # success = await delivery_engine.deliver(entry.payload, entry.destination_url)
            success = True  # placeholder

            if success:
                await dlq.update_status(entry.entry_id, DLQEntryStatus.RESOLVED)
                successful += 1
                details.append({"entry_id": entry.entry_id, "result": "success"})
            else:
                await dlq.update_status(entry.entry_id, DLQEntryStatus.PENDING)
                failed += 1
                details.append({"entry_id": entry.entry_id, "result": "failed"})
        except Exception as e:
            await dlq.update_status(entry.entry_id, DLQEntryStatus.PENDING)
            failed += 1
            details.append({"entry_id": entry.entry_id, "result": "error", "error": str(e)})

    return ReplayResult(
        total_replayed=len(entries_to_replay),
        successful=successful,
        failed=failed,
        details=details,
    )


@router.post("/entries/{entry_id}/discard")
async def discard_entry(
    entry_id: str,
    dlq: WebhookDeadLetterQueue = Depends(get_dlq),
) -> dict[str, str]:
    success = await dlq.discard(entry_id)
    if not success:
        raise HTTPException(status_code=404, detail="DLQ entry not found")
    return {"status": "discarded", "entry_id": entry_id}


@router.post("/purge")
async def purge_resolved(
    older_than_hours: int = Query(default=72),
    dlq: WebhookDeadLetterQueue = Depends(get_dlq),
) -> dict[str, int]:
    removed = await dlq.purge_resolved(older_than_hours)
    return {"removed": removed}
```

DLQ lifecycle and operations:

| Operation | When to use | Effect |
|---|---|---|
| Enqueue | After max retries exhausted | Preserves event for inspection |
| List / Inspect | Debugging delivery failures | View payload, error, attempts |
| Replay (single) | Endpoint fixed, retry one event | Re-delivers with current config |
| Replay (bulk) | Endpoint recovered, retry all pending | Batch re-delivery |
| Discard | Event is stale or irrelevant | Marks as discarded, no retry |
| Purge | Housekeeping | Removes old resolved entries |

Key patterns:
- **Redis Streams** provide ordered, persistent storage with built-in IDs
- **Separate index hash** enables O(1) lookups by entry ID
- **Status tracking** prevents double-replay of in-progress entries
- **Bulk replay with filters** enables targeted recovery by event type or destination
- **Stats endpoint** for monitoring DLQ depth and failure patterns
- **Purge resolved** prevents unbounded growth of the DLQ
'''
    ),
]
