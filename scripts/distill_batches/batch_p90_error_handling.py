"""Error handling — patterns across languages, retry strategies, and graceful degradation."""

PAIRS = [
    (
        "patterns/error-handling",
        "Show error handling patterns: Result types, error hierarchies, and recovery strategies across languages.",
        '''Error handling patterns:

```python
from dataclasses import dataclass
from typing import TypeVar, Generic, Callable
from enum import Enum
import logging

logger = logging.getLogger(__name__)

T = TypeVar("T")
E = TypeVar("E")


# --- Result type (Rust-inspired) ---

@dataclass(frozen=True)
class Ok(Generic[T]):
    value: T

    def is_ok(self) -> bool:
        return True

    def map(self, fn: Callable) -> "Result":
        return Ok(fn(self.value))

    def flat_map(self, fn: Callable) -> "Result":
        return fn(self.value)

    def unwrap(self) -> T:
        return self.value

    def unwrap_or(self, default: T) -> T:
        return self.value


@dataclass(frozen=True)
class Err(Generic[E]):
    error: E

    def is_ok(self) -> bool:
        return False

    def map(self, fn: Callable) -> "Result":
        return self  # Pass through errors

    def flat_map(self, fn: Callable) -> "Result":
        return self

    def unwrap(self):
        raise ValueError(f"Called unwrap on Err: {self.error}")

    def unwrap_or(self, default):
        return default


Result = Ok | Err


# Usage:
def parse_int(s: str) -> Result:
    try:
        return Ok(int(s))
    except ValueError as e:
        return Err(str(e))

# result = parse_int("42").map(lambda x: x * 2)  # Ok(84)
# result = parse_int("abc").map(lambda x: x * 2)  # Err("invalid literal...")


# --- Error hierarchy ---

class AppError(Exception):
    """Base error with structured context."""

    def __init__(self, message: str, code: str = "INTERNAL",
                 details: dict | None = None, cause: Exception | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}
        self.cause = cause

    def to_dict(self) -> dict:
        return {
            "error": self.code,
            "message": str(self),
            "details": self.details,
        }


class NotFoundError(AppError):
    def __init__(self, resource: str, id: str):
        super().__init__(
            f"{resource} '{id}' not found",
            code="NOT_FOUND",
            details={"resource": resource, "id": id},
        )


class ValidationError(AppError):
    def __init__(self, field: str, message: str):
        super().__init__(
            f"Validation failed on '{field}': {message}",
            code="VALIDATION_ERROR",
            details={"field": field},
        )


class RateLimitError(AppError):
    def __init__(self, retry_after: int = 60):
        super().__init__(
            f"Rate limit exceeded. Retry after {retry_after}s",
            code="RATE_LIMITED",
            details={"retry_after": retry_after},
        )


# --- Exception handler middleware ---

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

app = FastAPI()

@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    status_map = {
        "NOT_FOUND": 404,
        "VALIDATION_ERROR": 422,
        "RATE_LIMITED": 429,
        "UNAUTHORIZED": 401,
        "FORBIDDEN": 403,
        "CONFLICT": 409,
        "INTERNAL": 500,
    }
    return JSONResponse(
        status_code=status_map.get(exc.code, 500),
        content=exc.to_dict(),
    )

@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL", "message": "An unexpected error occurred"},
    )


# --- Graceful degradation ---

class GracefulService:
    """Service that degrades gracefully on failures."""

    async def get_user_profile(self, user_id: str) -> dict:
        """Fetch profile with fallbacks."""
        # Primary: full profile from API
        try:
            return await self._fetch_full_profile(user_id)
        except Exception as e:
            logger.warning("Full profile fetch failed: %s", e)

        # Fallback 1: cached profile
        try:
            cached = await self._get_cached_profile(user_id)
            if cached:
                cached["_stale"] = True
                return cached
        except Exception as e:
            logger.warning("Cache fetch failed: %s", e)

        # Fallback 2: minimal profile
        return {
            "id": user_id,
            "name": "Unknown",
            "_degraded": True,
        }
```

Error handling patterns:
1. **Result type** — explicit success/failure without exceptions for expected errors
2. **Error hierarchy** — structured errors with code, message, and details
3. **Status code mapping** — map error codes to HTTP status in one place
4. **Graceful degradation** — fallback chain: primary → cache → minimal response
5. **Unhandled catch-all** — log unexpected errors, return generic 500'''
    ),
    (
        "patterns/retry-strategies",
        "Show retry patterns: exponential backoff, jitter, circuit breaker integration, and idempotency.",
        '''Retry strategies:

```python
import asyncio
import random
import time
import logging
from typing import TypeVar, Callable, Awaitable
from dataclasses import dataclass, field
from functools import wraps

logger = logging.getLogger(__name__)
T = TypeVar("T")


# --- Retry with exponential backoff + jitter ---

@dataclass
class RetryConfig:
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,)
    non_retryable_exceptions: tuple[type[Exception], ...] = ()

    def delay_for_attempt(self, attempt: int) -> float:
        """Calculate delay with exponential backoff + jitter."""
        delay = min(
            self.base_delay * (self.exponential_base ** attempt),
            self.max_delay,
        )
        if self.jitter:
            delay = random.uniform(0, delay)  # Full jitter
        return delay


async def retry_async(
    fn: Callable[..., Awaitable[T]],
    config: RetryConfig = RetryConfig(),
    *args, **kwargs,
) -> T:
    """Retry async function with exponential backoff."""
    last_exception = None

    for attempt in range(config.max_retries + 1):
        try:
            return await fn(*args, **kwargs)

        except config.non_retryable_exceptions:
            raise  # Don't retry these

        except config.retryable_exceptions as e:
            last_exception = e

            if attempt == config.max_retries:
                break

            delay = config.delay_for_attempt(attempt)
            logger.warning(
                "Attempt %d/%d failed: %s. Retrying in %.1fs",
                attempt + 1, config.max_retries + 1, e, delay,
            )
            await asyncio.sleep(delay)

    raise last_exception


# --- Retry decorator ---

def with_retry(
    max_retries: int = 3,
    retryable: tuple[type[Exception], ...] = (Exception,),
    base_delay: float = 1.0,
):
    config = RetryConfig(
        max_retries=max_retries,
        retryable_exceptions=retryable,
        base_delay=base_delay,
    )

    def decorator(fn):
        @wraps(fn)
        async def wrapper(*args, **kwargs):
            return await retry_async(fn, config, *args, **kwargs)
        return wrapper
    return decorator


# Usage:
# @with_retry(max_retries=3, retryable=(httpx.TimeoutException, httpx.NetworkError))
# async def fetch_user(user_id: str) -> dict:
#     async with httpx.AsyncClient() as client:
#         resp = await client.get(f"/api/users/{user_id}")
#         resp.raise_for_status()
#         return resp.json()


# --- Retry with idempotency key ---

class IdempotentRetry:
    """Retry with idempotency key to prevent duplicate side effects."""

    def __init__(self, store):
        self.store = store  # Redis or DB

    async def execute(
        self,
        idempotency_key: str,
        fn: Callable[..., Awaitable[T]],
        *args, **kwargs,
    ) -> T:
        """Execute with idempotency — safe to retry."""
        # Check if already completed
        cached = await self.store.get(f"idem:{idempotency_key}")
        if cached:
            logger.info("Returning cached result for %s", idempotency_key)
            return cached

        # Execute
        result = await fn(*args, **kwargs)

        # Cache result (TTL: 24h)
        await self.store.set(f"idem:{idempotency_key}", result, ttl=86400)

        return result


# --- Backoff strategies comparison ---

def constant_backoff(attempt: int, delay: float = 1.0) -> float:
    """Same delay every time: 1s, 1s, 1s, ..."""
    return delay

def linear_backoff(attempt: int, delay: float = 1.0) -> float:
    """Linearly increasing: 1s, 2s, 3s, ..."""
    return delay * (attempt + 1)

def exponential_backoff(attempt: int, base: float = 1.0) -> float:
    """Exponentially increasing: 1s, 2s, 4s, 8s, ..."""
    return base * (2 ** attempt)

def exponential_with_jitter(attempt: int, base: float = 1.0) -> float:
    """Exponential + random jitter (recommended for distributed systems)."""
    return random.uniform(0, base * (2 ** attempt))

def decorrelated_jitter(attempt: int, base: float = 1.0,
                        prev_delay: float = 1.0) -> float:
    """AWS-recommended: sleep = min(cap, random(base, prev * 3))."""
    cap = 60.0
    return min(cap, random.uniform(base, prev_delay * 3))
```

Retry patterns:
1. **Exponential backoff** — double delay each attempt (1s, 2s, 4s, 8s)
2. **Full jitter** — `random(0, backoff)` prevents thundering herd
3. **Non-retryable exceptions** — don't retry 4xx client errors, only 5xx/timeouts
4. **Idempotency keys** — cache results to make retries safe for side effects
5. **Decorrelated jitter** — AWS-recommended for distributed systems'''
    ),
]
