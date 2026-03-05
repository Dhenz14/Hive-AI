"""Payment system design — processing architecture, idempotent APIs, retry and reconciliation, PCI compliance and tokenization."""

PAIRS = [
    (
        "system-design/payment-processing-architecture",
        "Design a payment processing system covering authorization, capture, settlement, and the overall payment lifecycle.",
        '''Payment processing architecture with authorization, capture, and settlement:

```python
# --- payment_service.py --- Core payment processing engine ---

from __future__ import annotations

import uuid
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class PaymentStatus(Enum):
    CREATED = "created"
    AUTHORIZED = "authorized"     # funds held on card
    CAPTURED = "captured"         # funds transferred
    SETTLED = "settled"           # funds in merchant account
    VOIDED = "voided"            # authorization released
    REFUNDED = "refunded"
    PARTIALLY_REFUNDED = "partially_refunded"
    FAILED = "failed"
    DECLINED = "declined"


class PaymentMethod(Enum):
    CREDIT_CARD = "credit_card"
    DEBIT_CARD = "debit_card"
    ACH = "ach"
    WIRE = "wire"
    WALLET = "wallet"


@dataclass
class Payment:
    """Core payment entity — tracks the full lifecycle."""
    id: str
    order_id: str
    merchant_id: str
    amount: Decimal
    currency: str
    status: PaymentStatus
    payment_method: PaymentMethod
    token: str                          # tokenized card/account
    authorization_code: Optional[str] = None
    capture_id: Optional[str] = None
    settlement_id: Optional[str] = None
    gateway_reference: Optional[str] = None
    idempotency_key: str = ""
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    authorized_at: Optional[datetime] = None
    captured_at: Optional[datetime] = None
    settled_at: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    refunded_amount: Decimal = Decimal("0")


class PaymentProcessor:
    """Orchestrates the payment lifecycle.

    Flow: Create -> Authorize -> Capture -> Settle
    """

    def __init__(
        self,
        gateway: PaymentGateway,
        repository: PaymentRepository,
        fraud_checker: FraudChecker,
        event_bus: EventBus,
    ):
        self.gateway = gateway
        self.repo = repository
        self.fraud = fraud_checker
        self.events = event_bus

    async def create_payment(
        self,
        order_id: str,
        merchant_id: str,
        amount: Decimal,
        currency: str,
        payment_method: PaymentMethod,
        token: str,
        idempotency_key: str,
        metadata: dict | None = None,
    ) -> Payment:
        """Create a new payment intent."""
        # Check idempotency
        existing = await self.repo.find_by_idempotency_key(idempotency_key)
        if existing:
            logger.info(f"Idempotent hit: {idempotency_key}")
            return existing

        payment = Payment(
            id=f"pay_{uuid.uuid4().hex[:16]}",
            order_id=order_id,
            merchant_id=merchant_id,
            amount=amount,
            currency=currency,
            status=PaymentStatus.CREATED,
            payment_method=payment_method,
            token=token,
            idempotency_key=idempotency_key,
            metadata=metadata or {},
        )

        await self.repo.save(payment)
        await self.events.publish("payment.created", payment)
        return payment

    async def authorize(self, payment_id: str) -> Payment:
        """Authorize payment — hold funds on the card.

        Authorization does NOT transfer money. It verifies:
        1. Card is valid
        2. Sufficient funds/credit
        3. Passes fraud checks
        The hold typically expires in 5-7 days.
        """
        payment = await self.repo.find_by_id(payment_id)
        if not payment:
            raise PaymentNotFoundError(payment_id)

        if payment.status != PaymentStatus.CREATED:
            raise InvalidStateError(
                f"Cannot authorize payment in {payment.status.value} state"
            )

        # Step 1: Fraud check
        fraud_result = await self.fraud.check(payment)
        if fraud_result.is_fraudulent:
            payment.status = PaymentStatus.DECLINED
            payment.error_code = "fraud_detected"
            payment.error_message = fraud_result.reason
            await self.repo.save(payment)
            await self.events.publish("payment.declined", payment)
            return payment

        # Step 2: Call payment gateway
        try:
            auth_result = await self.gateway.authorize(
                token=payment.token,
                amount=payment.amount,
                currency=payment.currency,
                merchant_id=payment.merchant_id,
            )

            if auth_result.approved:
                payment.status = PaymentStatus.AUTHORIZED
                payment.authorization_code = auth_result.auth_code
                payment.gateway_reference = auth_result.reference
                payment.authorized_at = datetime.utcnow()
                await self.events.publish("payment.authorized", payment)
            else:
                payment.status = PaymentStatus.DECLINED
                payment.error_code = auth_result.decline_code
                payment.error_message = auth_result.decline_reason
                await self.events.publish("payment.declined", payment)

        except GatewayTimeoutError:
            payment.status = PaymentStatus.FAILED
            payment.error_code = "gateway_timeout"
            await self.events.publish("payment.failed", payment)

        payment.updated_at = datetime.utcnow()
        await self.repo.save(payment)
        return payment

    async def capture(
        self, payment_id: str, amount: Optional[Decimal] = None
    ) -> Payment:
        """Capture authorized payment — transfer funds.

        Can capture full or partial amount. Must capture before
        authorization expires (typically 5-7 days).
        """
        payment = await self.repo.find_by_id(payment_id)
        if not payment:
            raise PaymentNotFoundError(payment_id)

        if payment.status != PaymentStatus.AUTHORIZED:
            raise InvalidStateError(
                f"Cannot capture payment in {payment.status.value} state"
            )

        capture_amount = amount or payment.amount
        if capture_amount > payment.amount:
            raise ValueError("Capture amount exceeds authorized amount")

        try:
            capture_result = await self.gateway.capture(
                authorization_code=payment.authorization_code,
                amount=capture_amount,
                currency=payment.currency,
            )

            payment.status = PaymentStatus.CAPTURED
            payment.capture_id = capture_result.capture_id
            payment.captured_at = datetime.utcnow()
            if capture_amount < payment.amount:
                payment.amount = capture_amount  # partial capture

            await self.events.publish("payment.captured", payment)

        except GatewayError as e:
            payment.error_code = "capture_failed"
            payment.error_message = str(e)
            await self.events.publish("payment.capture_failed", payment)

        payment.updated_at = datetime.utcnow()
        await self.repo.save(payment)
        return payment

    async def void(self, payment_id: str) -> Payment:
        """Void an authorized payment — release the hold."""
        payment = await self.repo.find_by_id(payment_id)
        if not payment:
            raise PaymentNotFoundError(payment_id)

        if payment.status != PaymentStatus.AUTHORIZED:
            raise InvalidStateError("Can only void authorized payments")

        await self.gateway.void(payment.authorization_code)
        payment.status = PaymentStatus.VOIDED
        payment.updated_at = datetime.utcnow()
        await self.repo.save(payment)
        await self.events.publish("payment.voided", payment)
        return payment

    async def refund(
        self, payment_id: str, amount: Optional[Decimal] = None
    ) -> Payment:
        """Refund a captured/settled payment."""
        payment = await self.repo.find_by_id(payment_id)
        if not payment:
            raise PaymentNotFoundError(payment_id)

        if payment.status not in (
            PaymentStatus.CAPTURED, PaymentStatus.SETTLED,
            PaymentStatus.PARTIALLY_REFUNDED,
        ):
            raise InvalidStateError(
                f"Cannot refund payment in {payment.status.value} state"
            )

        refund_amount = amount or payment.amount
        remaining = payment.amount - payment.refunded_amount
        if refund_amount > remaining:
            raise ValueError(f"Refund {refund_amount} exceeds remaining {remaining}")

        await self.gateway.refund(
            capture_id=payment.capture_id,
            amount=refund_amount,
            currency=payment.currency,
        )

        payment.refunded_amount += refund_amount
        if payment.refunded_amount >= payment.amount:
            payment.status = PaymentStatus.REFUNDED
        else:
            payment.status = PaymentStatus.PARTIALLY_REFUNDED

        payment.updated_at = datetime.utcnow()
        await self.repo.save(payment)
        await self.events.publish("payment.refunded", payment)
        return payment
```

```python
# --- settlement.py --- Settlement batch processing ---

from __future__ import annotations

import logging
from datetime import datetime, date, timedelta
from decimal import Decimal
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SettlementBatch:
    """A batch of captured payments to be settled with the acquirer."""
    id: str
    merchant_id: str
    batch_date: date
    total_amount: Decimal
    transaction_count: int
    status: str  # "pending", "submitted", "settled", "failed"
    payment_ids: list[str]
    settlement_reference: Optional[str] = None
    settled_at: Optional[datetime] = None


class SettlementService:
    """Batch settlement of captured payments.

    Settlement is the actual transfer of funds from the acquiring bank
    to the merchant's bank account. Typically runs daily.
    """

    def __init__(self, repo, gateway, event_bus):
        self.repo = repo
        self.gateway = gateway
        self.events = event_bus

    async def create_settlement_batch(
        self, merchant_id: str, batch_date: date
    ) -> SettlementBatch:
        """Create a settlement batch for all captured payments for a merchant."""
        # Find all captured, unsettled payments
        payments = await self.repo.find_captured_unsettled(
            merchant_id=merchant_id,
            captured_before=datetime.combine(batch_date, datetime.max.time()),
        )

        if not payments:
            logger.info(f"No payments to settle for {merchant_id} on {batch_date}")
            return None

        total = sum(p.amount - p.refunded_amount for p in payments)

        batch = SettlementBatch(
            id=f"stl_{batch_date.isoformat()}_{merchant_id[:8]}",
            merchant_id=merchant_id,
            batch_date=batch_date,
            total_amount=total,
            transaction_count=len(payments),
            status="pending",
            payment_ids=[p.id for p in payments],
        )

        await self.repo.save_batch(batch)
        return batch

    async def submit_batch(self, batch_id: str) -> SettlementBatch:
        """Submit the batch to the acquiring bank for settlement."""
        batch = await self.repo.find_batch(batch_id)

        result = await self.gateway.submit_settlement(
            merchant_id=batch.merchant_id,
            amount=batch.total_amount,
            transaction_count=batch.transaction_count,
            reference=batch.id,
        )

        batch.status = "submitted"
        batch.settlement_reference = result.reference
        await self.repo.save_batch(batch)

        logger.info(
            f"Settlement batch {batch.id} submitted: "
            f"{batch.transaction_count} txns, {batch.total_amount} {batch.merchant_id}"
        )
        return batch

    async def confirm_settlement(self, batch_id: str) -> SettlementBatch:
        """Called when acquiring bank confirms settlement."""
        batch = await self.repo.find_batch(batch_id)
        batch.status = "settled"
        batch.settled_at = datetime.utcnow()
        await self.repo.save_batch(batch)

        # Update individual payment statuses
        for payment_id in batch.payment_ids:
            payment = await self.repo.find_payment(payment_id)
            payment.status = PaymentStatus.SETTLED
            payment.settlement_id = batch.id
            payment.settled_at = datetime.utcnow()
            await self.repo.save_payment(payment)

        await self.events.publish("settlement.completed", batch)
        return batch

    async def run_daily_settlement(self) -> list[SettlementBatch]:
        """Cron job: settle all merchants for yesterday's captures."""
        yesterday = date.today() - timedelta(days=1)
        merchants = await self.repo.list_active_merchants()
        batches = []

        for merchant_id in merchants:
            batch = await self.create_settlement_batch(merchant_id, yesterday)
            if batch:
                await self.submit_batch(batch.id)
                batches.append(batch)

        logger.info(f"Daily settlement: {len(batches)} batches submitted")
        return batches
```

```
Payment Lifecycle State Machine:

    CREATED
       |
       v
   AUTHORIZED -----> VOIDED (release hold)
       |
       v
    CAPTURED
       |
       v
    SETTLED -------> REFUNDED
       |                |
       +------> PARTIALLY_REFUNDED

    (Any state) ---> FAILED / DECLINED

Timeline:
  T+0:        Customer clicks "Pay"        -> CREATED
  T+1s:       Gateway approves hold         -> AUTHORIZED
  T+0 to T+7d: Merchant ships item         -> (still AUTHORIZED)
  T+shipping:  Merchant captures payment    -> CAPTURED
  T+1-2 days:  Acquirer settles batch       -> SETTLED
  T+any:       Customer requests refund     -> REFUNDED

Key entities:
  Issuing Bank  -> Customer's bank (holds funds)
  Acquiring Bank -> Merchant's bank (receives funds)
  Card Network   -> Visa/Mastercard (routes transactions)
  Payment Gateway -> Stripe/Adyen (API layer)
```

| Stage | What happens | Who | Duration |
|-------|-------------|-----|----------|
| Authorization | Verify card, hold funds | Issuing bank | ~1 second |
| Capture | Transfer from hold to merchant | Acquiring bank | ~1 second |
| Settlement | Batch transfer to merchant account | Acquiring bank | 1-2 days |
| Void | Release authorization hold | Issuing bank | ~1 second |
| Refund | Return funds to customer | Issuing bank | 5-10 days |

Key patterns:
1. Separate authorization from capture — allows order fulfillment before charging
2. Authorization holds expire (5-7 days) — capture before expiry or re-authorize
3. Settlement is batched daily — individual transactions are not settled in real-time
4. Use state machine transitions to enforce valid payment lifecycle flows
5. Publish events at every state change for audit trail and downstream processing'''
    ),
    (
        "system-design/idempotent-payment-api",
        "Design an idempotent payment API that safely handles retries, network failures, and duplicate requests.",
        '''Idempotent payment API design for safe retries and duplicate prevention:

```python
# --- idempotency.py --- Idempotency key middleware ---

from __future__ import annotations

import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Any
from dataclasses import dataclass
from enum import Enum

import redis.asyncio as redis
from fastapi import FastAPI, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)


class IdempotencyStatus(Enum):
    PROCESSING = "processing"  # request in flight
    COMPLETED = "completed"    # response cached
    EXPIRED = "expired"


@dataclass
class IdempotencyRecord:
    key: str
    status: IdempotencyStatus
    status_code: int
    response_body: Optional[str]
    response_headers: dict[str, str]
    request_hash: str           # hash of request body for mismatch detection
    created_at: datetime
    expires_at: datetime


class IdempotencyStore:
    """Redis-backed idempotency key store.

    Keys are kept for 24 hours to handle late retries.
    Uses Redis SETNX for atomic lock acquisition.
    """

    def __init__(self, redis_client: redis.Redis, ttl_hours: int = 24):
        self.redis = redis_client
        self.ttl = timedelta(hours=ttl_hours)
        self.prefix = "idempotency:"
        self.lock_ttl = 30  # seconds — max time for request processing

    async def acquire(
        self, key: str, request_hash: str
    ) -> tuple[bool, Optional[IdempotencyRecord]]:
        """Try to acquire the idempotency key.

        Returns:
            (True, None) — key acquired, proceed with processing
            (False, record) — key exists, return cached response
        """
        redis_key = f"{self.prefix}{key}"

        # Atomic set-if-not-exists with lock TTL
        lock_value = json.dumps({
            "status": IdempotencyStatus.PROCESSING.value,
            "request_hash": request_hash,
            "created_at": datetime.utcnow().isoformat(),
        })

        acquired = await self.redis.set(
            redis_key, lock_value,
            nx=True,                          # only if not exists
            ex=self.lock_ttl,                 # auto-expire lock
        )

        if acquired:
            return True, None

        # Key exists — check if it's completed or still processing
        existing = await self.redis.get(redis_key)
        if not existing:
            # Key expired between check and get — retry
            return await self.acquire(key, request_hash)

        data = json.loads(existing)

        # Verify request body matches (detect misuse)
        if data.get("request_hash") != request_hash:
            raise IdempotencyMismatchError(
                "Idempotency key reused with different request body"
            )

        if data["status"] == IdempotencyStatus.PROCESSING.value:
            # Another request is still processing — client should retry
            raise IdempotencyConflictError(
                "Request with this idempotency key is still being processed"
            )

        # Completed — return cached response
        record = IdempotencyRecord(
            key=key,
            status=IdempotencyStatus.COMPLETED,
            status_code=data["status_code"],
            response_body=data.get("response_body"),
            response_headers=data.get("response_headers", {}),
            request_hash=data["request_hash"],
            created_at=datetime.fromisoformat(data["created_at"]),
            expires_at=datetime.fromisoformat(data["expires_at"]),
        )
        return False, record

    async def complete(
        self,
        key: str,
        status_code: int,
        response_body: str,
        response_headers: dict[str, str],
        request_hash: str,
    ) -> None:
        """Mark key as completed with cached response."""
        redis_key = f"{self.prefix}{key}"
        now = datetime.utcnow()

        data = json.dumps({
            "status": IdempotencyStatus.COMPLETED.value,
            "status_code": status_code,
            "response_body": response_body,
            "response_headers": response_headers,
            "request_hash": request_hash,
            "created_at": now.isoformat(),
            "expires_at": (now + self.ttl).isoformat(),
        })

        await self.redis.set(redis_key, data, ex=int(self.ttl.total_seconds()))

    async def release(self, key: str) -> None:
        """Release a processing lock (on error)."""
        await self.redis.delete(f"{self.prefix}{key}")


class IdempotencyMismatchError(Exception):
    pass


class IdempotencyConflictError(Exception):
    pass
```

```python
# --- middleware.py --- FastAPI idempotency middleware ---

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import hashlib
import json


class IdempotencyMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces idempotency for mutating endpoints.

    Clients include an `Idempotency-Key` header with a unique value (UUID).
    """

    IDEMPOTENT_METHODS = {"POST", "PUT", "PATCH"}

    def __init__(self, app: FastAPI, store: IdempotencyStore):
        super().__init__(app)
        self.store = store

    async def dispatch(self, request: Request, call_next) -> Response:
        # Only enforce for mutating methods
        if request.method not in self.IDEMPOTENT_METHODS:
            return await call_next(request)

        # Check for idempotency key header
        idempotency_key = request.headers.get("Idempotency-Key")
        if not idempotency_key:
            # Optional: require for payment endpoints
            if "/payments" in request.url.path:
                return JSONResponse(
                    status_code=400,
                    content={"error": "Idempotency-Key header required for payment endpoints"},
                )
            return await call_next(request)

        # Hash the request body for mismatch detection
        body = await request.body()
        request_hash = hashlib.sha256(body).hexdigest()

        try:
            acquired, existing = await self.store.acquire(idempotency_key, request_hash)
        except IdempotencyMismatchError:
            return JSONResponse(
                status_code=422,
                content={"error": "Idempotency key reused with different request body"},
            )
        except IdempotencyConflictError:
            return JSONResponse(
                status_code=409,
                content={"error": "Request still processing, retry later"},
                headers={"Retry-After": "5"},
            )

        if not acquired:
            # Return cached response
            return Response(
                content=existing.response_body,
                status_code=existing.status_code,
                headers={
                    **existing.response_headers,
                    "Idempotency-Replayed": "true",
                },
                media_type="application/json",
            )

        # Process the request
        try:
            response = await call_next(request)

            # Cache the response
            response_body = b""
            async for chunk in response.body_iterator:
                response_body += chunk

            await self.store.complete(
                key=idempotency_key,
                status_code=response.status_code,
                response_body=response_body.decode(),
                response_headers=dict(response.headers),
                request_hash=request_hash,
            )

            return Response(
                content=response_body,
                status_code=response.status_code,
                headers=dict(response.headers),
                media_type=response.media_type,
            )

        except Exception as e:
            # Release the lock so client can retry
            await self.store.release(idempotency_key)
            raise


# --- Setup ---
app = FastAPI()
redis_client = redis.Redis(host="localhost", port=6379, decode_responses=True)
idempotency_store = IdempotencyStore(redis_client)
app.add_middleware(IdempotencyMiddleware, store=idempotency_store)
```

```python
# --- client_usage.py --- Client-side idempotency patterns ---

import uuid
import time
import requests
from typing import Optional


class PaymentClient:
    """Client with built-in idempotency and retry logic."""

    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {api_key}"
        self.session.headers["Content-Type"] = "application/json"

    def create_payment(
        self,
        amount: int,       # amount in cents
        currency: str,
        token: str,
        idempotency_key: Optional[str] = None,
        max_retries: int = 3,
    ) -> dict:
        """Create a payment with automatic idempotency and retry.

        The same idempotency_key always returns the same result,
        even if called multiple times.
        """
        # Generate key if not provided — tie to business operation
        if not idempotency_key:
            idempotency_key = str(uuid.uuid4())

        payload = {
            "amount": amount,
            "currency": currency,
            "payment_token": token,
        }

        for attempt in range(max_retries + 1):
            try:
                response = self.session.post(
                    f"{self.base_url}/api/payments",
                    json=payload,
                    headers={"Idempotency-Key": idempotency_key},
                    timeout=30,
                )

                if response.status_code == 409:
                    # Still processing — wait and retry
                    retry_after = int(response.headers.get("Retry-After", "5"))
                    time.sleep(retry_after)
                    continue

                if response.status_code == 201:
                    replayed = response.headers.get("Idempotency-Replayed") == "true"
                    if replayed:
                        print(f"Idempotent replay for key {idempotency_key}")
                    return response.json()

                response.raise_for_status()

            except requests.exceptions.Timeout:
                # Network timeout — SAFE to retry with same idempotency key
                if attempt < max_retries:
                    backoff = 2 ** attempt
                    time.sleep(backoff)
                    continue
                raise

            except requests.exceptions.ConnectionError:
                # Connection failed — SAFE to retry
                if attempt < max_retries:
                    time.sleep(2 ** attempt)
                    continue
                raise

        raise Exception(f"Payment creation failed after {max_retries} retries")


# Usage:
# client = PaymentClient("https://api.example.com", "sk_live_xxx")
#
# # Safe: same key = same result, no double charge
# result = client.create_payment(
#     amount=2999,
#     currency="usd",
#     token="tok_visa_4242",
#     idempotency_key="order_ORD-123_payment",  # tie to order
# )
```

| Scenario | Without idempotency | With idempotency |
|----------|-------------------|-----------------|
| Network timeout during payment | Customer charged, client gets error, retries = double charge | Retry returns original result, no double charge |
| Client crashes mid-request | Partial state, inconsistent records | Retry picks up from lock or cached response |
| Load balancer retry | Different server processes duplicate | Both servers check same Redis key |
| User double-clicks "Pay" | Two payments created | Second request returns first payment |
| Server crashes after DB write | Response lost, client retries | Retry returns cached response |

Key patterns:
1. Require `Idempotency-Key` header on all mutating payment endpoints
2. Use Redis SETNX for atomic lock acquisition to prevent race conditions
3. Hash the request body to detect misuse (same key, different payload)
4. Cache the full response (status code + body) for replays
5. Release the lock on error so clients can retry with the same key'''
    ),
    (
        "system-design/payment-retry-reconciliation",
        "Show payment retry strategies and reconciliation processes to ensure consistency between payment system and external gateways.",
        '''Payment retry strategies and reconciliation for consistency:

```python
# --- retry_engine.py --- Payment retry with exponential backoff ---

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Optional, Callable, Awaitable
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class RetryPolicy(Enum):
    IMMEDIATE = "immediate"          # retry now
    EXPONENTIAL = "exponential"      # 2^n seconds
    FIXED_DELAY = "fixed_delay"      # fixed interval
    SCHEDULED = "scheduled"          # cron-based


@dataclass
class RetryConfig:
    max_attempts: int = 3
    initial_delay_seconds: float = 1.0
    max_delay_seconds: float = 300.0   # 5 minutes max
    backoff_multiplier: float = 2.0
    retryable_errors: set[str] = field(default_factory=lambda: {
        "gateway_timeout",
        "rate_limited",
        "temporary_failure",
        "network_error",
        "internal_error",
    })
    non_retryable_errors: set[str] = field(default_factory=lambda: {
        "card_declined",
        "insufficient_funds",
        "invalid_card",
        "expired_card",
        "fraud_detected",
    })


@dataclass
class RetryAttempt:
    attempt_number: int
    executed_at: datetime
    status: str          # "success", "failed", "skipped"
    error_code: Optional[str] = None
    error_message: Optional[str] = None
    next_retry_at: Optional[datetime] = None


class PaymentRetryEngine:
    """Handles payment retries with backoff and dead-letter queue."""

    def __init__(
        self,
        config: RetryConfig,
        payment_processor: PaymentProcessor,
        queue: RetryQueue,
        dead_letter_queue: DeadLetterQueue,
    ):
        self.config = config
        self.processor = payment_processor
        self.queue = queue
        self.dlq = dead_letter_queue

    async def execute_with_retry(
        self,
        payment_id: str,
        operation: str,  # "authorize", "capture", "refund"
    ) -> tuple[bool, list[RetryAttempt]]:
        """Execute a payment operation with retry logic."""
        attempts: list[RetryAttempt] = []

        for attempt_num in range(1, self.config.max_attempts + 1):
            logger.info(
                f"Payment {payment_id}: {operation} attempt {attempt_num}"
                f"/{self.config.max_attempts}"
            )

            try:
                result = await self._execute_operation(payment_id, operation)

                attempts.append(RetryAttempt(
                    attempt_number=attempt_num,
                    executed_at=datetime.utcnow(),
                    status="success",
                ))
                return True, attempts

            except PaymentError as e:
                delay = self._calculate_delay(attempt_num)

                attempt = RetryAttempt(
                    attempt_number=attempt_num,
                    executed_at=datetime.utcnow(),
                    status="failed",
                    error_code=e.error_code,
                    error_message=str(e),
                )

                # Check if error is retryable
                if e.error_code in self.config.non_retryable_errors:
                    attempt.status = "non_retryable"
                    attempts.append(attempt)
                    logger.warning(
                        f"Payment {payment_id}: non-retryable error {e.error_code}"
                    )
                    return False, attempts

                if attempt_num < self.config.max_attempts:
                    attempt.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
                    attempts.append(attempt)
                    logger.info(f"Retrying in {delay:.1f}s...")
                    await asyncio.sleep(delay)
                else:
                    attempts.append(attempt)
                    # Max retries exhausted — send to dead letter queue
                    await self.dlq.enqueue(payment_id, operation, attempts)
                    logger.error(
                        f"Payment {payment_id}: max retries exhausted, sent to DLQ"
                    )

        return False, attempts

    async def _execute_operation(self, payment_id: str, operation: str):
        ops = {
            "authorize": self.processor.authorize,
            "capture": self.processor.capture,
            "refund": self.processor.refund,
        }
        op_func = ops.get(operation)
        if not op_func:
            raise ValueError(f"Unknown operation: {operation}")
        return await op_func(payment_id)

    def _calculate_delay(self, attempt: int) -> float:
        """Exponential backoff with jitter."""
        import random
        delay = self.config.initial_delay_seconds * (
            self.config.backoff_multiplier ** (attempt - 1)
        )
        delay = min(delay, self.config.max_delay_seconds)
        # Add jitter: +/- 25%
        jitter = delay * 0.25 * (2 * random.random() - 1)
        return max(0.1, delay + jitter)


class PaymentError(Exception):
    def __init__(self, message: str, error_code: str):
        super().__init__(message)
        self.error_code = error_code
```

```python
# --- reconciliation.py --- Payment reconciliation engine ---

from __future__ import annotations

import csv
import logging
from datetime import date, datetime
from decimal import Decimal
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)


class DiscrepancyType(Enum):
    MISSING_IN_GATEWAY = "missing_in_gateway"      # we have it, gateway doesn't
    MISSING_IN_SYSTEM = "missing_in_system"        # gateway has it, we don't
    AMOUNT_MISMATCH = "amount_mismatch"
    STATUS_MISMATCH = "status_mismatch"
    CURRENCY_MISMATCH = "currency_mismatch"


@dataclass
class ReconciliationItem:
    payment_id: str
    our_amount: Optional[Decimal]
    our_status: Optional[str]
    gateway_amount: Optional[Decimal]
    gateway_status: Optional[str]
    gateway_reference: Optional[str]
    discrepancy: Optional[DiscrepancyType] = None
    resolved: bool = False
    resolution_notes: str = ""


@dataclass
class ReconciliationReport:
    report_date: date
    merchant_id: str
    total_our_records: int
    total_gateway_records: int
    matched: int
    discrepancies: list[ReconciliationItem]
    total_our_amount: Decimal
    total_gateway_amount: Decimal
    amount_difference: Decimal
    generated_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def discrepancy_count(self) -> int:
        return len(self.discrepancies)

    @property
    def match_rate(self) -> float:
        total = self.matched + self.discrepancy_count
        return self.matched / total if total > 0 else 0

    def summary(self) -> str:
        return (
            f"Reconciliation Report: {self.report_date}\n"
            f"  Merchant: {self.merchant_id}\n"
            f"  Our records: {self.total_our_records}\n"
            f"  Gateway records: {self.total_gateway_records}\n"
            f"  Matched: {self.matched} ({self.match_rate:.1%})\n"
            f"  Discrepancies: {self.discrepancy_count}\n"
            f"  Our total: {self.total_our_amount}\n"
            f"  Gateway total: {self.total_gateway_amount}\n"
            f"  Difference: {self.amount_difference}\n"
        )


class ReconciliationEngine:
    """Reconcile internal payment records against gateway settlement reports.

    Runs daily to ensure our records match the payment gateway's records.
    """

    def __init__(self, payment_repo, gateway_client, alert_service):
        self.repo = payment_repo
        self.gateway = gateway_client
        self.alerts = alert_service

    async def reconcile(
        self, merchant_id: str, report_date: date
    ) -> ReconciliationReport:
        """Full reconciliation for a merchant on a given date."""
        logger.info(f"Reconciling {merchant_id} for {report_date}")

        # Step 1: Fetch our records
        our_payments = await self.repo.find_payments_for_date(
            merchant_id=merchant_id,
            date=report_date,
            statuses=["captured", "settled", "refunded"],
        )
        our_index = {p.gateway_reference: p for p in our_payments if p.gateway_reference}

        # Step 2: Fetch gateway settlement report
        gateway_records = await self.gateway.get_settlement_report(
            merchant_id=merchant_id,
            date=report_date,
        )
        gateway_index = {r["reference"]: r for r in gateway_records}

        # Step 3: Compare
        matched = 0
        discrepancies: list[ReconciliationItem] = []

        # Check all our records against gateway
        for ref, payment in our_index.items():
            gateway_record = gateway_index.pop(ref, None)

            if gateway_record is None:
                discrepancies.append(ReconciliationItem(
                    payment_id=payment.id,
                    our_amount=payment.amount,
                    our_status=payment.status.value,
                    gateway_amount=None,
                    gateway_status=None,
                    gateway_reference=ref,
                    discrepancy=DiscrepancyType.MISSING_IN_GATEWAY,
                ))
                continue

            # Compare amounts
            gw_amount = Decimal(str(gateway_record["amount"]))
            if payment.amount != gw_amount:
                discrepancies.append(ReconciliationItem(
                    payment_id=payment.id,
                    our_amount=payment.amount,
                    our_status=payment.status.value,
                    gateway_amount=gw_amount,
                    gateway_status=gateway_record["status"],
                    gateway_reference=ref,
                    discrepancy=DiscrepancyType.AMOUNT_MISMATCH,
                ))
                continue

            # Compare statuses
            if not self._status_compatible(payment.status.value, gateway_record["status"]):
                discrepancies.append(ReconciliationItem(
                    payment_id=payment.id,
                    our_amount=payment.amount,
                    our_status=payment.status.value,
                    gateway_amount=gw_amount,
                    gateway_status=gateway_record["status"],
                    gateway_reference=ref,
                    discrepancy=DiscrepancyType.STATUS_MISMATCH,
                ))
                continue

            matched += 1

        # Check remaining gateway records not in our system
        for ref, gw_record in gateway_index.items():
            discrepancies.append(ReconciliationItem(
                payment_id="",
                our_amount=None,
                our_status=None,
                gateway_amount=Decimal(str(gw_record["amount"])),
                gateway_status=gw_record["status"],
                gateway_reference=ref,
                discrepancy=DiscrepancyType.MISSING_IN_SYSTEM,
            ))

        # Build report
        our_total = sum(p.amount for p in our_payments)
        gw_total = sum(Decimal(str(r["amount"])) for r in gateway_records)

        report = ReconciliationReport(
            report_date=report_date,
            merchant_id=merchant_id,
            total_our_records=len(our_payments),
            total_gateway_records=len(gateway_records),
            matched=matched,
            discrepancies=discrepancies,
            total_our_amount=our_total,
            total_gateway_amount=gw_total,
            amount_difference=our_total - gw_total,
        )

        # Alert on significant discrepancies
        if report.discrepancy_count > 0:
            await self.alerts.send(
                severity="high" if report.match_rate < 0.99 else "medium",
                message=report.summary(),
            )

        logger.info(report.summary())
        return report

    def _status_compatible(self, our_status: str, gw_status: str) -> bool:
        """Check if our status is compatible with the gateway's status."""
        compatibility = {
            "captured": {"captured", "settled", "success"},
            "settled": {"settled", "success", "paid"},
            "refunded": {"refunded", "reversed"},
        }
        return gw_status.lower() in compatibility.get(our_status, set())
```

```sql
-- Schema for payment retry and reconciliation tracking

CREATE TABLE payment_retry_log (
    id              BIGSERIAL PRIMARY KEY,
    payment_id      VARCHAR(32) NOT NULL REFERENCES payments(id),
    operation       VARCHAR(20) NOT NULL,  -- authorize, capture, refund
    attempt_number  INT NOT NULL,
    status          VARCHAR(20) NOT NULL,  -- success, failed, non_retryable
    error_code      VARCHAR(50),
    error_message   TEXT,
    next_retry_at   TIMESTAMPTZ,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_retry_payment ON payment_retry_log(payment_id);
CREATE INDEX idx_retry_next ON payment_retry_log(next_retry_at) WHERE status = 'failed';

CREATE TABLE reconciliation_reports (
    id                  BIGSERIAL PRIMARY KEY,
    merchant_id         VARCHAR(32) NOT NULL,
    report_date         DATE NOT NULL,
    total_our_records   INT NOT NULL,
    total_gw_records    INT NOT NULL,
    matched_count       INT NOT NULL,
    discrepancy_count   INT NOT NULL,
    our_total_amount    DECIMAL(15,2) NOT NULL,
    gw_total_amount     DECIMAL(15,2) NOT NULL,
    amount_difference   DECIMAL(15,2) NOT NULL,
    generated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (merchant_id, report_date)
);

CREATE TABLE reconciliation_discrepancies (
    id                  BIGSERIAL PRIMARY KEY,
    report_id           BIGINT REFERENCES reconciliation_reports(id),
    payment_id          VARCHAR(32),
    gateway_reference   VARCHAR(64),
    discrepancy_type    VARCHAR(30) NOT NULL,
    our_amount          DECIMAL(15,2),
    our_status          VARCHAR(20),
    gateway_amount      DECIMAL(15,2),
    gateway_status      VARCHAR(20),
    resolved            BOOLEAN NOT NULL DEFAULT FALSE,
    resolved_by         VARCHAR(100),
    resolution_notes    TEXT,
    resolved_at         TIMESTAMPTZ
);

CREATE INDEX idx_disc_unresolved ON reconciliation_discrepancies(resolved)
    WHERE resolved = FALSE;
```

| Retry Strategy | Delay pattern | Best for |
|---------------|---------------|----------|
| Exponential backoff | 1s, 2s, 4s, 8s, ... | Gateway timeouts, rate limits |
| Fixed delay | 5s, 5s, 5s, ... | Scheduled batch retries |
| Immediate | 0s | Transient network errors |
| Jittered backoff | Randomized exponential | High-throughput systems (prevent thundering herd) |
| Dead letter queue | After max retries | Manual investigation, auto-resolution |

Key patterns:
1. Classify errors as retryable (timeout, rate limit) vs non-retryable (card declined, fraud)
2. Use exponential backoff with jitter to prevent thundering herd on retries
3. Send to dead letter queue after max retries for manual or automated investigation
4. Run daily reconciliation against the gateway settlement report to catch drift
5. Alert on any discrepancies and track resolution status for audit compliance'''
    ),
    (
        "system-design/pci-compliance-tokenization",
        "Show PCI DSS compliance patterns including card tokenization, vault architecture, and secure payment data handling.",
        '''PCI DSS compliance patterns with tokenization and vault architecture:

```python
# --- tokenization.py --- Card tokenization service ---

from __future__ import annotations

import os
import hmac
import hashlib
import secrets
import logging
from datetime import datetime, timedelta
from typing import Optional
from dataclasses import dataclass
from enum import Enum

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

logger = logging.getLogger(__name__)


class TokenType(Enum):
    SINGLE_USE = "single_use"     # one-time payment
    MULTI_USE = "multi_use"       # stored card (subscription)
    NETWORK = "network"           # network-level token (Visa Token Service)


@dataclass
class CardToken:
    """Opaque token representing a stored payment method."""
    token: str                      # tok_xxxxxxxxxxxx
    token_type: TokenType
    last_four: str                  # "4242"
    card_brand: str                 # "visa", "mastercard"
    exp_month: int
    exp_year: int
    fingerprint: str                # deterministic hash for dedup
    created_at: datetime
    expires_at: Optional[datetime]  # None for multi-use tokens
    customer_id: Optional[str] = None


class TokenizationService:
    """Tokenize payment cards — replaces raw card data with opaque tokens.

    PCI DSS Requirement: never store raw card numbers (PAN) in your systems.
    Tokenization replaces the PAN with a non-reversible token.
    """

    def __init__(self, vault: CardVault, key_manager: KeyManager):
        self.vault = vault
        self.keys = key_manager

    async def tokenize(
        self,
        card_number: str,
        exp_month: int,
        exp_year: int,
        cvv: str,
        customer_id: Optional[str] = None,
        token_type: TokenType = TokenType.MULTI_USE,
    ) -> CardToken:
        """Tokenize a raw card number.

        1. Validate card
        2. Generate fingerprint (for dedup)
        3. Encrypt and store in vault
        4. Return opaque token
        """
        # Validate card (Luhn check)
        if not self._luhn_check(card_number):
            raise InvalidCardError("Card number failed Luhn check")

        # Generate deterministic fingerprint for dedup
        fingerprint = self._generate_fingerprint(card_number)

        # Check for existing token with same card
        existing = await self.vault.find_by_fingerprint(fingerprint, customer_id)
        if existing and token_type == TokenType.MULTI_USE:
            logger.info(f"Reusing existing token for fingerprint {fingerprint[:8]}...")
            return existing

        # Generate opaque token
        token_value = f"tok_{secrets.token_urlsafe(24)}"

        # Encrypt card data for vault storage
        encrypted_pan = self.keys.encrypt(card_number)
        encrypted_cvv = self.keys.encrypt(cvv)  # stored briefly for auth

        # Store in vault
        card_token = CardToken(
            token=token_value,
            token_type=token_type,
            last_four=card_number[-4:],
            card_brand=self._detect_brand(card_number),
            exp_month=exp_month,
            exp_year=exp_year,
            fingerprint=fingerprint,
            created_at=datetime.utcnow(),
            expires_at=(
                datetime.utcnow() + timedelta(minutes=15)
                if token_type == TokenType.SINGLE_USE else None
            ),
            customer_id=customer_id,
        )

        await self.vault.store(
            token=card_token,
            encrypted_pan=encrypted_pan,
            encrypted_cvv=encrypted_cvv,
        )

        # CVV is deleted after first authorization (PCI DSS requirement)
        logger.info(f"Tokenized card: {card_token.card_brand} ****{card_token.last_four}")
        return card_token

    async def detokenize(self, token: str) -> str:
        """Retrieve the raw PAN for gateway communication.

        Only callable from the payment gateway integration layer.
        Requires audit logging and key management access.
        """
        encrypted_pan = await self.vault.get_pan(token)
        if not encrypted_pan:
            raise TokenNotFoundError(f"Token not found: {token}")

        pan = self.keys.decrypt(encrypted_pan)

        # Audit log every detokenization
        logger.info(
            f"Detokenized: {token[:8]}... "
            f"(caller: payment_gateway_integration)"
        )

        return pan

    def _luhn_check(self, card_number: str) -> bool:
        """Validate card number using Luhn algorithm."""
        digits = [int(d) for d in card_number.replace(" ", "")]
        checksum = 0
        reverse = digits[::-1]
        for i, d in enumerate(reverse):
            if i % 2 == 1:
                d *= 2
                if d > 9:
                    d -= 9
            checksum += d
        return checksum % 10 == 0

    def _generate_fingerprint(self, card_number: str) -> str:
        """Deterministic fingerprint for deduplication."""
        key = os.environ["FINGERPRINT_KEY"].encode()
        return hmac.new(key, card_number.encode(), hashlib.sha256).hexdigest()

    def _detect_brand(self, card_number: str) -> str:
        """Detect card brand from BIN (first 6 digits)."""
        n = card_number.replace(" ", "")
        if n[0] == "4":
            return "visa"
        if n[:2] in ("51", "52", "53", "54", "55"):
            return "mastercard"
        if n[:2] in ("34", "37"):
            return "amex"
        if n[:4] == "6011" or n[:2] == "65":
            return "discover"
        return "unknown"


class InvalidCardError(Exception):
    pass


class TokenNotFoundError(Exception):
    pass
```

```python
# --- key_manager.py --- Encryption key management (PCI DSS Req 3) ---

from __future__ import annotations

import os
import logging
from typing import Optional
from datetime import datetime, timedelta

from cryptography.fernet import Fernet, MultiFernet

logger = logging.getLogger(__name__)


class KeyManager:
    """Encryption key management for PCI-compliant card data storage.

    PCI DSS Requirements:
    - Req 3.5: Protect encryption keys against disclosure and misuse
    - Req 3.6: Key management procedures
    - Req 3.7: Key rotation at least annually
    """

    def __init__(self):
        # Load keys from secure key store (HSM, KMS, Vault)
        # NEVER hardcode keys or store in config files
        self._current_key = self._load_key("CARD_ENCRYPTION_KEY_CURRENT")
        self._previous_key = self._load_key("CARD_ENCRYPTION_KEY_PREVIOUS")

        # MultiFernet supports key rotation — decrypts with any known key
        keys = [Fernet(self._current_key)]
        if self._previous_key:
            keys.append(Fernet(self._previous_key))
        self._fernet = MultiFernet(keys)

    def encrypt(self, plaintext: str) -> bytes:
        """Encrypt sensitive data (PAN, CVV) using current key."""
        return self._fernet.encrypt(plaintext.encode())

    def decrypt(self, ciphertext: bytes) -> str:
        """Decrypt data — tries current key first, then previous."""
        return self._fernet.decrypt(ciphertext).decode()

    def rotate_key(self) -> str:
        """Generate a new encryption key and rotate.

        After rotation:
        1. New data encrypted with new key
        2. Old data can still be decrypted
        3. Schedule re-encryption of old records with new key
        """
        new_key = Fernet.generate_key()
        logger.info("Encryption key rotated. Schedule re-encryption of existing records.")
        return new_key.decode()

    def _load_key(self, env_var: str) -> Optional[bytes]:
        """Load key from environment (in production, use HSM/KMS)."""
        key = os.environ.get(env_var)
        if key:
            return key.encode()
        return None


# --- PCI DSS data handling rules ---

PCI_DATA_CLASSIFICATION = {
    "PAN": {
        "storage": "encrypted_in_vault",
        "display": "masked_last_4",    # ****4242
        "logging": "never",
        "retention": "as_needed",
    },
    "CVV/CVC": {
        "storage": "never_after_auth",  # delete immediately after authorization
        "display": "never",
        "logging": "never",
        "retention": "none",
    },
    "Cardholder Name": {
        "storage": "encrypted",
        "display": "allowed",
        "logging": "masked",
        "retention": "as_needed",
    },
    "Expiry Date": {
        "storage": "encrypted",
        "display": "allowed",
        "logging": "masked",
        "retention": "as_needed",
    },
    "Track Data": {
        "storage": "never",
        "display": "never",
        "logging": "never",
        "retention": "none",
    },
}
```

```python
# --- pci_architecture.py --- PCI-compliant architecture patterns ---

from dataclasses import dataclass


@dataclass
class PCIArchitecture:
    """PCI DSS scope reduction through architecture."""

    description: str = """
    PCI Scope Reduction Strategy:
    =============================

    Goal: Minimize the number of systems that handle raw card data.

    Architecture:

    [Browser] --HTTPS--> [Payment Page (iframe)]
         |                        |
         |                   Hosted by PSP (Stripe, Adyen)
         |                        |
         v                        v
    [Your App Server]     [PSP Tokenization API]
         |                        |
         | (token only)           | (raw PAN)
         v                        v
    [Your Backend]         [PSP Card Vault]
         |                        |
         | token-based API        | encrypted storage
         v                        v
    [Your Database]        [PSP Gateway]
         |                        |
         | (no PAN ever)          | (processes payment)
         v                        v
    [Your Analytics]       [Card Networks]

    Key: Your systems NEVER see the raw PAN.
    PCI scope is limited to the PSP iframe/SDK.

    SAQ Types by Integration:
    ========================
    SAQ A    - Fully hosted payment page (redirect/iframe)
               Your scope: almost nothing
    SAQ A-EP - Embedded form that posts directly to PSP
               Your scope: web server security
    SAQ D    - You handle raw card data
               Your scope: everything (400+ controls)

    Recommendation: Use SAQ A (iframe) to minimize PCI scope.
    """


# Secure payment form integration (SAQ A pattern)
PAYMENT_FORM_HTML = """
<!-- Payment page using Stripe Elements (SAQ A) -->
<!-- Raw card data NEVER touches your server -->

<form id="payment-form">
  <div id="card-element">
    <!-- Stripe.js injects the card input iframe here -->
    <!-- The iframe is hosted on Stripe's PCI-compliant servers -->
  </div>
  <button type="submit">Pay $29.99</button>
</form>

<script src="https://js.stripe.com/v3/"></script>
<script>
  const stripe = Stripe('pk_live_xxx');
  const elements = stripe.elements();
  const cardElement = elements.create('card');
  cardElement.mount('#card-element');

  document.getElementById('payment-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    // Card data goes directly to Stripe — never to your server
    const { token, error } = await stripe.createToken(cardElement);

    if (error) {
      showError(error.message);
      return;
    }

    // Send only the token to your backend
    const response = await fetch('/api/payments', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Idempotency-Key': generateUUID(),
      },
      body: JSON.stringify({
        token: token.id,        // "tok_1abc..." — NOT the card number
        amount: 2999,
        currency: 'usd',
      }),
    });
  });
</script>
"""
```

| PCI DSS Requirement | What it covers | Implementation |
|--------------------|----------------|---------------|
| Req 1: Firewall | Network segmentation | VPC, security groups, WAF |
| Req 2: Defaults | Remove vendor defaults | Harden OS, disable unused services |
| Req 3: Stored data | Protect stored card data | Encryption, tokenization, key mgmt |
| Req 4: Transmission | Encrypt data in transit | TLS 1.2+, certificate pinning |
| Req 5: Malware | Anti-virus/malware | Endpoint protection, container scanning |
| Req 6: Secure dev | Secure SDLC | Code review, SAST/DAST, patching |
| Req 7: Access control | Restrict access | RBAC, least privilege |
| Req 8: Authentication | Unique IDs, MFA | SSO, MFA for admin access |
| Req 9: Physical | Physical security | N/A for cloud (CSP responsibility) |
| Req 10: Logging | Audit trails | Centralized logging, SIEM |
| Req 11: Testing | Regular testing | Pen tests, vulnerability scans |
| Req 12: Policy | Security policy | Documented policies, training |

Key patterns:
1. Use PSP-hosted payment forms (Stripe Elements, Adyen Drop-in) to achieve SAQ A and minimize PCI scope
2. Never store raw PAN in your database — only store opaque tokens
3. Delete CVV/CVC immediately after authorization — PCI DSS prohibits storage
4. Use Fernet/AES-256 encryption with key rotation via MultiFernet for vault storage
5. Fingerprint cards deterministically (HMAC) for dedup without exposing the PAN'''
    ),
]
