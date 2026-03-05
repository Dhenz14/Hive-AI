"""Architecture — microservices patterns, API gateway, and service communication."""

PAIRS = [
    (
        "architecture/api-gateway",
        "Show API gateway patterns: routing, authentication, rate limiting, request aggregation, and circuit breaking.",
        '''API gateway patterns:

```python
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx
import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# --- Service registry ---

@dataclass
class ServiceConfig:
    name: str
    base_url: str
    timeout: float = 10.0
    retries: int = 2
    circuit_breaker_threshold: int = 5


SERVICES = {
    "users": ServiceConfig("users", "http://user-service:8001"),
    "orders": ServiceConfig("orders", "http://order-service:8002"),
    "products": ServiceConfig("products", "http://product-service:8003"),
    "payments": ServiceConfig("payments", "http://payment-service:8004",
                              timeout=30.0),
}


# --- Gateway application ---

app = FastAPI(title="API Gateway")


# --- Request routing ---

@app.api_route("/api/{service}/{path:path}", methods=["GET", "POST", "PUT", "DELETE"])
async def proxy(service: str, path: str, request: Request):
    """Route requests to backend services."""
    config = SERVICES.get(service)
    if not config:
        raise HTTPException(404, f"Service '{service}' not found")

    # Build backend URL
    url = f"{config.base_url}/{path}"
    if request.query_params:
        url += f"?{request.query_params}"

    # Forward headers (filter hop-by-hop headers)
    headers = {
        k: v for k, v in request.headers.items()
        if k.lower() not in ("host", "connection", "transfer-encoding")
    }
    headers["X-Request-ID"] = request.state.request_id
    headers["X-Forwarded-For"] = request.client.host

    # Forward request body
    body = await request.body()

    async with httpx.AsyncClient(timeout=config.timeout) as client:
        for attempt in range(config.retries + 1):
            try:
                response = await client.request(
                    method=request.method,
                    url=url,
                    headers=headers,
                    content=body,
                )

                return JSONResponse(
                    content=response.json() if response.headers.get(
                        "content-type", ""
                    ).startswith("application/json") else response.text,
                    status_code=response.status_code,
                    headers={
                        "X-Service": service,
                        "X-Response-Time": str(time.perf_counter()),
                    },
                )
            except (httpx.ConnectError, httpx.ReadTimeout) as e:
                if attempt == config.retries:
                    logger.error("Service %s unreachable: %s", service, e)
                    raise HTTPException(503, f"Service '{service}' unavailable")
                await asyncio.sleep(0.5 * (2 ** attempt))


# --- Request aggregation (BFF pattern) ---

@app.get("/api/dashboard/{user_id}")
async def get_dashboard(user_id: str, request: Request):
    """Aggregate data from multiple services for dashboard."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        # Parallel requests to multiple services
        user_task = client.get(
            f"{SERVICES['users'].base_url}/users/{user_id}",
            headers={"X-Request-ID": request.state.request_id},
        )
        orders_task = client.get(
            f"{SERVICES['orders'].base_url}/orders",
            params={"user_id": user_id, "limit": 5},
            headers={"X-Request-ID": request.state.request_id},
        )
        products_task = client.get(
            f"{SERVICES['products'].base_url}/products/recommended",
            params={"user_id": user_id},
            headers={"X-Request-ID": request.state.request_id},
        )

        # Gather with error tolerance
        results = await asyncio.gather(
            user_task, orders_task, products_task,
            return_exceptions=True,
        )

        response = {}

        # User data (required)
        if isinstance(results[0], Exception):
            raise HTTPException(503, "User service unavailable")
        response["user"] = results[0].json()

        # Orders (optional — degrade gracefully)
        if isinstance(results[1], Exception):
            response["recent_orders"] = []
            response["_warnings"] = ["Orders temporarily unavailable"]
        else:
            response["recent_orders"] = results[1].json()

        # Recommendations (optional)
        if isinstance(results[2], Exception):
            response["recommended"] = []
        else:
            response["recommended"] = results[2].json()

        return response


# --- Middleware: auth + rate limiting + request ID ---

@app.middleware("http")
async def gateway_middleware(request: Request, call_next):
    import uuid
    start = time.perf_counter()

    # Request ID
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.request_id = request_id

    # Skip auth for health check
    if request.url.path == "/health":
        return await call_next(request)

    # Authentication
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(
            {"error": "Missing authentication"},
            status_code=401,
        )

    # Validate token (in production, use JWT verification)
    token = auth_header[7:]
    user = await verify_token(token)
    if not user:
        return JSONResponse(
            {"error": "Invalid token"},
            status_code=401,
        )
    request.state.user = user

    # Rate limiting
    rate_key = f"rate:{user['id']}"
    if await is_rate_limited(rate_key):
        return JSONResponse(
            {"error": "Rate limit exceeded"},
            status_code=429,
            headers={"Retry-After": "60"},
        )

    # Forward request
    response = await call_next(request)

    # Add response headers
    elapsed = time.perf_counter() - start
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{elapsed:.3f}s"

    return response
```

API gateway patterns:
1. **Service routing** — proxy requests to backend services by path prefix
2. **Request aggregation** — BFF pattern combines multiple service calls
3. **Graceful degradation** — optional services fail silently, required ones error
4. **Middleware chain** — auth, rate limiting, request ID in single pipeline
5. **Retry with backoff** — retry failed backend requests before returning 503'''
    ),
    (
        "architecture/service-communication",
        "Show microservice communication patterns: sync REST, async messaging, outbox pattern, and idempotency.",
        '''Microservice communication patterns:

```python
import json
import asyncio
import logging
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable
from uuid import uuid4

logger = logging.getLogger(__name__)


# --- Outbox pattern (reliable event publishing) ---

class OutboxPublisher:
    """Transactional outbox for reliable event publishing.

    Events are written to DB in the same transaction as business data,
    then a background worker publishes them to the message broker.
    This prevents lost events on crashes between DB write and publish.
    """

    def __init__(self, pool, publisher):
        self.pool = pool
        self.publisher = publisher  # Kafka/RabbitMQ producer

    async def save_with_event(self, conn, business_sql: str,
                               business_params: tuple,
                               event_type: str, event_data: dict):
        """Save business data and outbox event in one transaction."""
        async with conn.transaction():
            # Business operation
            await conn.execute(business_sql, *business_params)

            # Write event to outbox table (same transaction)
            await conn.execute("""
                INSERT INTO outbox (id, event_type, payload, status)
                VALUES ($1, $2, $3, 'pending')
            """, str(uuid4()), event_type, json.dumps(event_data))

    async def publish_pending(self, batch_size: int = 100):
        """Background worker: publish pending outbox events."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, event_type, payload
                FROM outbox
                WHERE status = 'pending'
                ORDER BY created_at
                LIMIT $1
                FOR UPDATE SKIP LOCKED
            """, batch_size)

            for row in rows:
                try:
                    await self.publisher.publish(
                        topic=row["event_type"],
                        data=json.loads(row["payload"]),
                        headers={"outbox_id": row["id"]},
                    )

                    await conn.execute("""
                        UPDATE outbox SET status = 'published',
                        published_at = NOW()
                        WHERE id = $1
                    """, row["id"])

                except Exception as e:
                    logger.error("Failed to publish %s: %s", row["id"], e)
                    await conn.execute("""
                        UPDATE outbox SET status = 'failed',
                        error = $2, retry_count = retry_count + 1
                        WHERE id = $1
                    """, row["id"], str(e))


# --- Idempotent message processing ---

class IdempotentConsumer:
    """Process each message exactly once using idempotency keys."""

    def __init__(self, pool, redis):
        self.pool = pool
        self.redis = redis

    async def process(self, message_id: str, handler: Callable,
                      data: dict, ttl: int = 86400):
        """Process message idempotently."""
        dedup_key = f"processed:{message_id}"

        # Check if already processed (fast path)
        if await self.redis.exists(dedup_key):
            logger.info("Duplicate message %s, skipping", message_id)
            return

        # Process with DB-level idempotency check
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Atomic insert-or-ignore
                inserted = await conn.fetchval("""
                    INSERT INTO processed_messages (message_id, processed_at)
                    VALUES ($1, NOW())
                    ON CONFLICT (message_id) DO NOTHING
                    RETURNING message_id
                """, message_id)

                if not inserted:
                    logger.info("Duplicate message %s (DB check)", message_id)
                    return

                # Process the message
                await handler(conn, data)

        # Set Redis cache for fast dedup
        await self.redis.set(dedup_key, "1", ex=ttl)


# --- Request-reply pattern ---

class RequestReplyClient:
    """Synchronous request-reply over async messaging."""

    def __init__(self, publisher, subscriber):
        self.publisher = publisher
        self.subscriber = subscriber
        self._pending: dict[str, asyncio.Future] = {}

    async def request(self, service: str, action: str,
                      data: dict, timeout: float = 10.0) -> dict:
        """Send request and wait for reply."""
        correlation_id = str(uuid4())
        reply_to = f"reply.{correlation_id}"

        # Create future for response
        future = asyncio.get_event_loop().create_future()
        self._pending[correlation_id] = future

        # Publish request
        await self.publisher.publish(
            topic=f"service.{service}.{action}",
            data=data,
            headers={
                "correlation_id": correlation_id,
                "reply_to": reply_to,
            },
        )

        try:
            # Wait for reply with timeout
            result = await asyncio.wait_for(future, timeout=timeout)
            return result
        except asyncio.TimeoutError:
            raise ServiceTimeoutError(
                f"No reply from {service}.{action} within {timeout}s"
            )
        finally:
            self._pending.pop(correlation_id, None)

    async def handle_reply(self, message):
        """Callback for reply messages."""
        correlation_id = message.headers.get("correlation_id")
        future = self._pending.get(correlation_id)
        if future and not future.done():
            future.set_result(message.data)


# --- Correlation context propagation ---

@dataclass
class CorrelationContext:
    """Propagate tracing context across services."""
    request_id: str = field(default_factory=lambda: str(uuid4()))
    correlation_id: str = ""
    causation_id: str = ""
    user_id: str = ""
    tenant_id: str = ""
    span_id: str = ""

    def to_headers(self) -> dict:
        return {
            "X-Request-ID": self.request_id,
            "X-Correlation-ID": self.correlation_id or self.request_id,
            "X-Causation-ID": self.causation_id,
            "X-User-ID": self.user_id,
            "X-Tenant-ID": self.tenant_id,
        }

    @classmethod
    def from_headers(cls, headers: dict) -> 'CorrelationContext':
        return cls(
            request_id=headers.get("X-Request-ID", str(uuid4())),
            correlation_id=headers.get("X-Correlation-ID", ""),
            causation_id=headers.get("X-Causation-ID", ""),
            user_id=headers.get("X-User-ID", ""),
            tenant_id=headers.get("X-Tenant-ID", ""),
        )
```

Microservice communication patterns:
1. **Outbox pattern** — write events to DB + outbox in one transaction, publish async
2. **Idempotent processing** — Redis + DB dedup ensures exactly-once semantics
3. **Request-reply** — synchronous semantics over async messaging with correlation IDs
4. **Correlation context** — propagate request/user/tenant IDs across services
5. **FOR UPDATE SKIP LOCKED** — concurrent outbox workers without contention'''
    ),
    (
        "architecture/circuit-breaker",
        "Show circuit breaker pattern with states, half-open testing, metrics, and fallbacks.",
        '''Circuit breaker pattern:

```python
import asyncio
import time
import logging
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Any, Optional
from collections import deque

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = auto()     # Normal operation
    OPEN = auto()       # Failing, reject requests
    HALF_OPEN = auto()  # Testing recovery


@dataclass
class CircuitStats:
    total_requests: int = 0
    failures: int = 0
    successes: int = 0
    consecutive_failures: int = 0
    last_failure_time: float = 0
    last_success_time: float = 0


class CircuitBreaker:
    """Circuit breaker with sliding window failure detection."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        success_threshold: int = 3,
        timeout: float = 60.0,
        window_size: int = 10,
        fallback: Optional[Callable] = None,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.success_threshold = success_threshold
        self.timeout = timeout
        self.window_size = window_size
        self.fallback = fallback

        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._window: deque[bool] = deque(maxlen=window_size)
        self._half_open_successes = 0
        self._lock = asyncio.Lock()

    @property
    def state(self) -> CircuitState:
        if self._state == CircuitState.OPEN:
            # Check if timeout elapsed -> move to half-open
            if time.time() - self._stats.last_failure_time > self.timeout:
                self._state = CircuitState.HALF_OPEN
                self._half_open_successes = 0
                logger.info("Circuit %s: OPEN -> HALF_OPEN", self.name)
        return self._state

    async def call(self, fn: Callable, *args, **kwargs) -> Any:
        """Execute function through circuit breaker."""
        state = self.state
        self._stats.total_requests += 1

        if state == CircuitState.OPEN:
            logger.warning("Circuit %s is OPEN, rejecting request", self.name)
            if self.fallback:
                return await self.fallback(*args, **kwargs)
            raise CircuitOpenError(
                f"Circuit breaker '{self.name}' is open. "
                f"Retry after {self.timeout}s"
            )

        try:
            result = await fn(*args, **kwargs)
            await self._on_success()
            return result

        except Exception as e:
            await self._on_failure()
            if self.state == CircuitState.OPEN and self.fallback:
                return await self.fallback(*args, **kwargs)
            raise

    async def _on_success(self):
        async with self._lock:
            self._stats.successes += 1
            self._stats.consecutive_failures = 0
            self._stats.last_success_time = time.time()
            self._window.append(True)

            if self._state == CircuitState.HALF_OPEN:
                self._half_open_successes += 1
                if self._half_open_successes >= self.success_threshold:
                    self._state = CircuitState.CLOSED
                    logger.info("Circuit %s: HALF_OPEN -> CLOSED", self.name)

    async def _on_failure(self):
        async with self._lock:
            self._stats.failures += 1
            self._stats.consecutive_failures += 1
            self._stats.last_failure_time = time.time()
            self._window.append(False)

            if self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open -> back to open
                self._state = CircuitState.OPEN
                logger.warning("Circuit %s: HALF_OPEN -> OPEN", self.name)

            elif self._state == CircuitState.CLOSED:
                # Check failure rate in window
                if len(self._window) >= self.window_size:
                    failure_rate = self._window.count(False) / len(self._window)
                    if failure_rate >= self.failure_threshold / self.window_size:
                        self._state = CircuitState.OPEN
                        logger.warning(
                            "Circuit %s: CLOSED -> OPEN (%.0f%% failures)",
                            self.name, failure_rate * 100
                        )

    def get_metrics(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.name,
            "total_requests": self._stats.total_requests,
            "failures": self._stats.failures,
            "successes": self._stats.successes,
            "failure_rate": (
                self._window.count(False) / len(self._window)
                if self._window else 0
            ),
        }


# --- Usage with decorator ---

def circuit_breaker(name: str, **kwargs):
    """Decorator version of circuit breaker."""
    cb = CircuitBreaker(name, **kwargs)

    def decorator(fn):
        import functools
        @functools.wraps(fn)
        async def wrapper(*args, **kw):
            return await cb.call(fn, *args, **kw)
        wrapper.circuit_breaker = cb  # Expose for metrics
        return wrapper
    return decorator

@circuit_breaker(
    "payment-service",
    failure_threshold=3,
    timeout=30.0,
    fallback=lambda *a, **kw: {"status": "pending", "message": "Payment queued"},
)
async def process_payment(order_id: str, amount: float) -> dict:
    """Call payment service with circuit breaker."""
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(
            "http://payment-service/charge",
            json={"order_id": order_id, "amount": amount},
        )
        response.raise_for_status()
        return response.json()
```

Circuit breaker patterns:
1. **Three states** — CLOSED (normal), OPEN (reject), HALF_OPEN (test recovery)
2. **Sliding window** — track failure rate over last N requests
3. **Half-open testing** — allow N successes before closing circuit
4. **Fallback** — return degraded response when circuit is open
5. **Async lock** — thread-safe state transitions'''
    ),
]
