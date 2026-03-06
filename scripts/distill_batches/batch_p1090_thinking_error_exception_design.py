"""Thinking-trace pairs: exception design patterns."""

PAIRS = [
    (
        "thinking/error-handling",
        r'''How should I design a custom exception hierarchy for a payment processing library? I want to distinguish between different types of payment failures so callers can handle them differently.''',
        r'''<think>
For a payment processing library, the exception hierarchy needs to reflect the different failure modes. My first thought was to just create one PaymentError with an error code enum, but wait -- that forces callers to use if/elif on error codes instead of except clauses. Since Python has a rich exception hierarchy specifically for this purpose, I should use subclasses so callers can catch exactly what they need.

The failure modes break down into:
1. Transient errors (network timeout, rate limit) - caller should retry
2. Validation errors (invalid card, insufficient funds) - caller should not retry
3. Configuration errors (bad API key, misconfigured merchant) - developer error
4. Security errors (fraud detection, stolen card) - needs special handling

Hmm, could "insufficient funds" be transient rather than validation? The customer might add funds and retry. But actually no -- from the payment library's perspective, the current request failed due to the current card state. The caller decides whether to let the user try again; the exception type should reflect what happened, not what might happen next. Therefore it belongs under validation.

The hierarchy should:
- Have a base exception for catching all payment errors
- Use exception attributes to carry structured error data (because bare string messages are not machine-parseable)
- Support exception chaining for root cause tracking
- Be serializable for logging and monitoring
</think>

A well-designed exception hierarchy for payment processing should categorize errors by **what the caller should do about them** (retry, fix input, fix config, escalate):

```python
from typing import Optional, Any
from datetime import datetime


class PaymentError(Exception):
    """Base exception for all payment-related errors.

    Catching this catches every payment failure.
    """

    def __init__(
        self,
        message: str,
        code: str = "PAYMENT_ERROR",
        details: Optional[dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.code = code
        self.details = details or {}
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> dict:
        """Serialize for logging/monitoring."""
        return {
            "error_type": self.__class__.__name__,
            "code": self.code,
            "message": str(self),
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


# ============================================================
# TIER 1: Transient errors (RETRY-ABLE)
# ============================================================

class TransientPaymentError(PaymentError):
    """Temporary failure -- caller should retry with backoff."""

    def __init__(
        self,
        message: str,
        retry_after: Optional[float] = None,
        **kwargs,
    ):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after  # Seconds to wait before retry


class GatewayTimeoutError(TransientPaymentError):
    """Payment gateway did not respond in time."""

    def __init__(self, gateway: str, timeout: float):
        super().__init__(
            f"Gateway {gateway} timed out after {timeout}s",
            code="GATEWAY_TIMEOUT",
            retry_after=5.0,
            details={"gateway": gateway, "timeout": timeout},
        )


class RateLimitError(TransientPaymentError):
    """Too many requests to the payment gateway."""

    def __init__(self, gateway: str, retry_after: float = 60.0):
        super().__init__(
            f"Rate limited by {gateway}",
            code="RATE_LIMITED",
            retry_after=retry_after,
            details={"gateway": gateway},
        )


class GatewayUnavailableError(TransientPaymentError):
    """Payment gateway is temporarily down."""

    def __init__(self, gateway: str):
        super().__init__(
            f"Gateway {gateway} is temporarily unavailable",
            code="GATEWAY_UNAVAILABLE",
            retry_after=30.0,
            details={"gateway": gateway},
        )


# ============================================================
# TIER 2: Validation errors (DO NOT RETRY)
# ============================================================

class PaymentValidationError(PaymentError):
    """Invalid payment data -- fix the input and try again."""

    def __init__(self, message: str, field: Optional[str] = None, **kwargs):
        super().__init__(message, code="VALIDATION_ERROR", **kwargs)
        self.field = field


class InvalidCardError(PaymentValidationError):
    """Card number, expiry, or CVV is invalid."""

    def __init__(self, reason: str):
        super().__init__(
            f"Invalid card: {reason}",
            field="card_number",
            details={"reason": reason},
        )


class InsufficientFundsError(PaymentValidationError):
    """Card has insufficient funds for the transaction."""

    def __init__(self, amount: float, currency: str):
        super().__init__(
            f"Insufficient funds for {currency} {amount:.2f}",
            details={"amount": amount, "currency": currency},
        )
        self.code = "INSUFFICIENT_FUNDS"


class CardExpiredError(PaymentValidationError):
    """Card has expired."""

    def __init__(self):
        super().__init__("Card has expired", field="expiry_date")
        self.code = "CARD_EXPIRED"


# ============================================================
# TIER 3: Configuration errors (DEVELOPER must fix)
# ============================================================

class PaymentConfigError(PaymentError):
    """Configuration problem -- developer needs to fix setup."""

    def __init__(self, message: str, **kwargs):
        super().__init__(message, code="CONFIG_ERROR", **kwargs)


class InvalidAPIKeyError(PaymentConfigError):
    def __init__(self, gateway: str):
        super().__init__(
            f"Invalid API key for {gateway}. Check your credentials.",
            details={"gateway": gateway},
        )


# ============================================================
# TIER 4: Security errors (ESCALATE)
# ============================================================

class PaymentSecurityError(PaymentError):
    """Security concern -- may need human review."""

    def __init__(self, message: str, **kwargs):
        super().__init__(message, code="SECURITY_ERROR", **kwargs)


class FraudDetectedError(PaymentSecurityError):
    def __init__(self, reason: str, transaction_id: str):
        super().__init__(
            f"Fraud detected: {reason}",
            details={"reason": reason, "transaction_id": transaction_id},
        )


# ============================================================
# USAGE EXAMPLE
# ============================================================

def process_payment(card, amount, currency):
    """Example showing how callers handle different error tiers."""
    try:
        result = payment_gateway.charge(card, amount, currency)
        return result
    except TransientPaymentError as e:
        # Retry with backoff
        if e.retry_after:
            import time
            time.sleep(e.retry_after)
        raise  # Re-raise for the retry mechanism
    except PaymentValidationError as e:
        # Show user-friendly message, do NOT retry
        return {"error": str(e), "field": e.field}
    except PaymentSecurityError as e:
        # Log for security team, block the transaction
        security_logger.critical("Security alert: %s", e.to_dict())
        raise
    except PaymentConfigError as e:
        # Alert the development team
        ops_logger.error("Configuration error: %s", e.to_dict())
        raise
    except PaymentError as e:
        # Catch-all for any payment error
        logger.error("Unexpected payment error: %s", e.to_dict())
        raise
```

**Design principles:**
1. Base class catches everything; subclasses let callers be specific
2. Each tier implies a different response strategy (retry, fix input, fix config, escalate)
3. Structured `to_dict()` for consistent logging across all error types
4. Attributes like `retry_after` and `field` guide the caller's response''',
    ),
    (
        "thinking/error-handling",
        r'''How does exception chaining work in Python? When should I use "raise X from Y" versus just "raise X"? I am confused about __cause__ and __context__.''',
        r'''<think>
Python 3 has two forms of exception chaining -- actually wait, there are three if you count suppression:

1. Explicit chaining: `raise NewError() from original_error`
   - Sets __cause__ = original_error
   - Sets __suppress_context__ = True
   - Traceback shows "The above exception was the direct cause..."

2. Implicit chaining: `raise NewError()` inside an except block
   - Sets __context__ = the caught exception (automatically)
   - __suppress_context__ = False
   - Traceback shows "During handling of the above exception..."

3. Suppressing context: `raise NewError() from None`
   - Sets __cause__ = None
   - Sets __suppress_context__ = True
   - Hides the original exception from the traceback

I initially thought __cause__ and __context__ were redundant, but actually they serve different purposes. __cause__ is intentional ("I am deliberately wrapping this error"), while __context__ is incidental ("this happened while I was handling another error"). The traceback messages differ precisely because the relationship is different.

Hmm, one subtlety I almost missed: explicit chaining sets __suppress_context__ = True. This means even if there is also an implicit __context__, the traceback only shows the __cause__ chain. That could be confusing -- you might wonder why the "During handling of..." message disappeared. It is because `from e` takes priority over implicit context.
</think>

Exception chaining in Python 3 has three forms, each with different semantics:

```python
import traceback

# ============================================================
# 1. EXPLICIT CHAINING: raise X from Y
# ============================================================
# Use when you are INTENTIONALLY wrapping an exception.
# The original exception is the CAUSE of the new one.

def fetch_user_profile(user_id):
    """Wrap low-level errors in domain-specific exceptions."""
    try:
        response = http_client.get(f"/users/{user_id}")
        return response.json()
    except ConnectionError as e:
        # "raise from" sets __cause__ and shows:
        # "The above exception was the direct cause of..."
        raise ServiceUnavailableError(
            f"Cannot reach user service for user {user_id}"
        ) from e
    except ValueError as e:
        raise DataCorruptionError(
            f"Invalid JSON response for user {user_id}"
        ) from e


# ============================================================
# 2. IMPLICIT CHAINING: raise X (inside except block)
# ============================================================
# Happens automatically when you raise a NEW exception
# while handling an existing one. Python saves the original
# in __context__. Shows: "During handling of the above exception..."

def process_order(order):
    try:
        validate(order)
    except ValidationError:
        # This implicitly chains -- __context__ is set automatically
        # Traceback shows: "During handling of the above exception,
        #                   another exception occurred:"
        notify_admin("Validation failed")  # This might also raise!
        raise OrderProcessingError("Order validation failed")


# ============================================================
# 3. SUPPRESS CONTEXT: raise X from None
# ============================================================
# Use when you want to HIDE the original exception.
# The caller should not know about internal implementation details.

def get_config(key):
    """Get config value, hiding internal storage details."""
    try:
        return redis_client.get(key)
    except Exception:
        # "from None" suppresses the Redis error in the traceback.
        # Callers see only ConfigError, not the Redis details.
        raise ConfigError(f"Config key '{key}' not available") from None


# ============================================================
# DEMONSTRATION: All three forms
# ============================================================

class AppError(Exception):
    pass

class DatabaseError(AppError):
    pass

# EXPLICIT: preserves cause chain
def example_explicit():
    try:
        raise ConnectionRefusedError("DB connection refused")
    except ConnectionRefusedError as e:
        raise DatabaseError("Cannot connect to database") from e
        # Traceback:
        # ConnectionRefusedError: DB connection refused
        # The above exception was the direct cause of the following:
        # DatabaseError: Cannot connect to database

# IMPLICIT: shows context
def example_implicit():
    try:
        raise ConnectionRefusedError("DB connection refused")
    except ConnectionRefusedError:
        raise DatabaseError("Cannot connect to database")
        # Traceback:
        # ConnectionRefusedError: DB connection refused
        # During handling of the above exception, another occurred:
        # DatabaseError: Cannot connect to database

# SUPPRESSED: hides original
def example_suppressed():
    try:
        raise ConnectionRefusedError("DB connection refused")
    except ConnectionRefusedError:
        raise DatabaseError("Cannot connect to database") from None
        # Traceback:
        # DatabaseError: Cannot connect to database
        # (no mention of ConnectionRefusedError)

# ============================================================
# INSPECTING THE CHAIN
# ============================================================

def print_exception_chain(exc):
    """Walk the exception chain."""
    current = exc
    depth = 0
    while current is not None:
        indent = "  " * depth
        print(f"{indent}{type(current).__name__}: {current}")
        if current.__cause__:
            print(f"{indent}  (explicit cause)")
            current = current.__cause__
        elif current.__context__ and not current.__suppress_context__:
            print(f"{indent}  (implicit context)")
            current = current.__context__
        else:
            current = None
        depth += 1

# ============================================================
# BEST PRACTICES
# ============================================================

# DO: Use "from e" when wrapping lower-level exceptions
def read_data(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError as e:
        raise DataNotFoundError(f"Data file missing: {path}") from e
    except json.JSONDecodeError as e:
        raise DataCorruptError(f"Invalid JSON in {path}") from e

# DO: Use "from None" when the original exception leaks internals
def authenticate(token):
    try:
        payload = jwt.decode(token, SECRET)
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthError("Token expired") from None
    except jwt.InvalidTokenError:
        raise AuthError("Invalid token") from None

# DON'T: Bare "raise X" in except block (confusing traceback)
# The implicit context message "During handling of..." implies
# something went wrong during error handling, which may mislead.
```

**Rules of thumb:**
- `raise X from e` -- "e caused X" (intentional wrapping, preserves traceback)
- `raise X` in except -- "X happened while handling another error" (incidental)
- `raise X from None` -- "forget the original" (hide implementation details)
- Use `from e` most of the time; use `from None` for security/abstraction boundaries''',
    ),
    (
        "thinking/error-handling",
        r'''How do I properly use context managers for resource cleanup in error handling? I want to make sure database connections, file handles, and locks are always released even when exceptions occur.''',
        r'''<think>
Context managers (with statements) are the primary mechanism for guaranteed cleanup in Python. They use __enter__ and __exit__ methods (or @contextmanager decorator). The __exit__ method is always called, even if an exception occurs.

Could you just use try/finally instead? You could, but context managers are better because they encapsulate the acquire/release pattern into a reusable object. With try/finally, every call site must remember the cleanup steps. A context manager centralizes that logic, so a bug fix in cleanup applies everywhere.

I considered whether to focus on @contextmanager (simpler) or the class-based approach (__enter__/__exit__). Actually, I should cover both -- @contextmanager is great for simple cases, but the class-based approach is necessary when you need to inspect exception info in __exit__ (since @contextmanager just sees the exception as a raised error in the yield). Wait, that is not quite right -- @contextmanager can catch exceptions around the yield too. But __exit__ gets exc_type, exc_val, exc_tb as arguments, making it easier to conditionally handle errors without re-raising.

Key points to cover:
1. Basic context manager pattern
2. @contextmanager decorator
3. Nested context managers
4. ExitStack for dynamic resource management (because you cannot hardcode nested with-blocks when the number of resources is unknown)
5. Async context managers
6. Context managers that handle specific exceptions
</think>

Context managers guarantee cleanup even when exceptions occur. Here are the patterns from basic to advanced:

```python
from contextlib import contextmanager, ExitStack, asynccontextmanager
import asyncio
import logging

logger = logging.getLogger(__name__)

# ============================================================
# PATTERN 1: Class-based context manager
# ============================================================

class DatabaseConnection:
    """Context manager for database connections."""

    def __init__(self, connection_string):
        self.connection_string = connection_string
        self.conn = None

    def __enter__(self):
        """Acquire the resource."""
        self.conn = create_connection(self.connection_string)
        return self.conn

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Release the resource, regardless of exceptions.

        Args:
            exc_type: Exception class (or None if no exception)
            exc_val: Exception instance (or None)
            exc_tb: Traceback (or None)

        Returns:
            True to suppress the exception, False to propagate it.
        """
        if self.conn:
            if exc_type is not None:
                # Exception occurred -- rollback
                logger.warning("Rolling back due to %s: %s", exc_type.__name__, exc_val)
                self.conn.rollback()
            else:
                # No exception -- commit
                self.conn.commit()
            self.conn.close()
            self.conn = None

        # Return False to propagate exceptions (almost always correct)
        return False

# Usage:
# with DatabaseConnection("postgresql://...") as conn:
#     conn.execute("INSERT INTO users ...")
#     # If this raises, __exit__ rolls back and closes
#     # If no error, __exit__ commits and closes


# ============================================================
# PATTERN 2: @contextmanager decorator (simpler)
# ============================================================

@contextmanager
def managed_transaction(conn):
    """Context manager for a database transaction."""
    cursor = conn.cursor()
    try:
        yield cursor
        # If we reach here, no exception -- commit
        conn.commit()
    except Exception:
        # Exception occurred -- rollback
        conn.rollback()
        raise  # Always re-raise!
    finally:
        # ALWAYS close the cursor
        cursor.close()

# Usage:
# with managed_transaction(conn) as cursor:
#     cursor.execute("UPDATE accounts SET balance = balance - 100 WHERE id = 1")
#     cursor.execute("UPDATE accounts SET balance = balance + 100 WHERE id = 2")


# ============================================================
# PATTERN 3: ExitStack for dynamic resource management
# ============================================================

def process_multiple_files(file_paths):
    """Open a variable number of files safely."""
    with ExitStack() as stack:
        # Each file is registered for cleanup
        files = [
            stack.enter_context(open(path, "r"))
            for path in file_paths
        ]
        # All files are guaranteed to close, even if one fails
        contents = [f.read() for f in files]
        return contents


def conditional_resources(need_db=True, need_cache=True):
    """Acquire resources conditionally."""
    with ExitStack() as stack:
        db = None
        cache = None

        if need_db:
            db = stack.enter_context(DatabaseConnection("postgresql://..."))
        if need_cache:
            cache = stack.enter_context(CacheConnection("redis://..."))

        # Use whatever resources were acquired
        process(db=db, cache=cache)
        # All acquired resources are cleaned up automatically


# ============================================================
# PATTERN 4: Async context managers
# ============================================================

@asynccontextmanager
async def async_db_session(pool):
    """Async context manager for database sessions."""
    conn = await pool.acquire()
    try:
        yield conn
        # No exception: commit is implicit with asyncpg
    except Exception:
        # Exception: rollback
        await conn.execute("ROLLBACK")
        raise
    finally:
        await pool.release(conn)


# Usage:
# async with async_db_session(pool) as conn:
#     await conn.execute("INSERT INTO ...")


# ============================================================
# PATTERN 5: Context manager with cleanup callbacks
# ============================================================

@contextmanager
def temporary_directory():
    """Create a temp dir and clean up on exit."""
    import tempfile
    import shutil
    tmpdir = tempfile.mkdtemp()
    try:
        yield tmpdir
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


@contextmanager
def locked_resource(lock, timeout=30):
    """Acquire a lock with timeout, guarantee release."""
    acquired = lock.acquire(timeout=timeout)
    if not acquired:
        raise TimeoutError(f"Could not acquire lock within {timeout}s")
    try:
        yield
    finally:
        lock.release()


# ============================================================
# PATTERN 6: Composing context managers
# ============================================================

@contextmanager
def full_operation_context():
    """Compose multiple resource acquisitions."""
    with DatabaseConnection("postgresql://...") as db:
        with CacheConnection("redis://...") as cache:
            with locked_resource(distributed_lock):
                yield {"db": db, "cache": cache}

# Or using ExitStack (more flexible):
@contextmanager
def full_operation_context_v2():
    with ExitStack() as stack:
        db = stack.enter_context(DatabaseConnection("postgresql://..."))
        cache = stack.enter_context(CacheConnection("redis://..."))
        stack.enter_context(locked_resource(distributed_lock))

        # Register additional cleanup callbacks
        stack.callback(logger.info, "Operation context closed")

        yield {"db": db, "cache": cache}
```

**Key rules:**
1. `__exit__` should almost never return `True` (suppressing exceptions hides bugs)
2. Always `raise` in the except block of `@contextmanager` -- do not swallow
3. Use `ExitStack` when the number of resources is dynamic
4. Use `finally` for unconditional cleanup, `except` for error-specific cleanup
5. For async resources, use `@asynccontextmanager` and `async with`''',
    ),
    (
        "thinking/error-handling",
        r'''Python 3.11 introduced ExceptionGroup and the "except*" syntax. How do these work and when should I use them? Can you show practical examples?''',
        r'''<think>
ExceptionGroup (PEP 654) allows raising multiple exceptions simultaneously. At first I thought this was just syntactic sugar for collecting errors in a list, but actually it is fundamentally different -- it integrates with the traceback system and allows structured matching via except*.

This is useful for:
1. Concurrent operations where multiple tasks can fail independently
2. Validation that collects all errors before reporting
3. Cleanup operations where multiple cleanup steps can fail

Could you just raise the first error and ignore the rest? You could, but that loses information. In concurrent scenarios, three out of five tasks might fail for different reasons, and the caller needs to know about all of them to respond correctly.

Key concepts:
- ExceptionGroup wraps multiple exceptions
- except* matches specific exception types within the group
- Multiple except* clauses can each match different exceptions from the same group -- wait, this is a big difference from regular except, where only the first matching clause runs. With except*, all matching clauses execute because each handles a disjoint subset of the group.
- except* catches subgroups, not the entire group. Therefore unmatched exceptions propagate automatically.
</think>

ExceptionGroup (Python 3.11+) lets you raise and handle multiple exceptions simultaneously. Here are practical use cases:

```python
import asyncio
from typing import Any

# ============================================================
# BASIC USAGE: ExceptionGroup
# ============================================================

# An ExceptionGroup wraps multiple exceptions
eg = ExceptionGroup("multiple failures", [
    ValueError("invalid email"),
    TypeError("age must be int"),
    PermissionError("not authorized"),
])

# except* matches SPECIFIC types within the group
try:
    raise eg
except* ValueError as e:
    # e is an ExceptionGroup containing only the ValueError(s)
    print(f"Value errors: {e.exceptions}")
except* TypeError as e:
    print(f"Type errors: {e.exceptions}")
except* PermissionError as e:
    print(f"Permission errors: {e.exceptions}")

# IMPORTANT: Multiple except* clauses CAN match from the same group.
# Each gets a subgroup containing its matching exceptions.
# Unmatched exceptions propagate up.

# ============================================================
# USE CASE 1: Input validation (collect ALL errors)
# ============================================================

class ValidationError(Exception):
    def __init__(self, field: str, message: str):
        super().__init__(f"{field}: {message}")
        self.field = field

def validate_user(data: dict) -> dict:
    """Validate user data, reporting ALL errors at once."""
    errors = []

    if not data.get("email"):
        errors.append(ValidationError("email", "required"))
    elif "@" not in data.get("email", ""):
        errors.append(ValidationError("email", "invalid format"))

    if not data.get("name"):
        errors.append(ValidationError("name", "required"))
    elif len(data["name"]) < 2:
        errors.append(ValidationError("name", "too short"))

    age = data.get("age")
    if age is not None:
        if not isinstance(age, int):
            errors.append(ValidationError("age", "must be integer"))
        elif age < 0 or age > 150:
            errors.append(ValidationError("age", "out of range"))

    if errors:
        raise ExceptionGroup("Validation failed", errors)

    return data

# Handle validation errors:
try:
    validate_user({"email": "bad", "name": "", "age": -5})
except* ValidationError as eg:
    # eg.exceptions contains all ValidationError instances
    for err in eg.exceptions:
        print(f"  Field '{err.field}': {err}")


# ============================================================
# USE CASE 2: Concurrent task failures
# ============================================================

class FetchError(Exception):
    def __init__(self, url: str, reason: str):
        super().__init__(f"Failed to fetch {url}: {reason}")
        self.url = url

class ParseError(Exception):
    def __init__(self, url: str, reason: str):
        super().__init__(f"Failed to parse {url}: {reason}")
        self.url = url

async def fetch_all(urls: list[str]) -> list[Any]:
    """Fetch multiple URLs, collecting all failures."""
    async def fetch_one(url):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as resp:
                    if resp.status != 200:
                        raise FetchError(url, f"HTTP {resp.status}")
                    return await resp.json()
        except aiohttp.ClientError as e:
            raise FetchError(url, str(e))

    # asyncio.TaskGroup raises ExceptionGroup on failures
    results = {}
    try:
        async with asyncio.TaskGroup() as tg:
            tasks = {
                url: tg.create_task(fetch_one(url))
                for url in urls
            }
    except* FetchError as eg:
        # Some URLs failed -- handle gracefully
        failed_urls = [e.url for e in eg.exceptions]
        print(f"Failed to fetch: {failed_urls}")
        # Return partial results
        for url, task in tasks.items():
            if not task.cancelled() and task.exception() is None:
                results[url] = task.result()
    else:
        # All succeeded
        results = {url: task.result() for url, task in tasks.items()}

    return results


# ============================================================
# USE CASE 3: Cleanup with multiple failures
# ============================================================

class CleanupError(Exception):
    def __init__(self, resource: str, reason: str):
        super().__init__(f"Failed to clean up {resource}: {reason}")
        self.resource = resource

def cleanup_resources(resources: list):
    """Clean up multiple resources, collecting all failures."""
    errors = []
    for resource in resources:
        try:
            resource.close()
        except Exception as e:
            errors.append(
                CleanupError(resource.name, str(e))
            )

    if errors:
        raise ExceptionGroup("Cleanup failures", errors)


# ============================================================
# IMPORTANT DIFFERENCES from regular except
# ============================================================

# 1. except* can match MULTIPLE clauses from one raise
try:
    raise ExceptionGroup("mixed", [
        ValueError("a"),
        TypeError("b"),
    ])
except* ValueError:
    print("Caught ValueError(s)")  # This runs
except* TypeError:
    print("Caught TypeError(s)")   # This ALSO runs!
# Regular except would only match the first clause.

# 2. except* always receives an ExceptionGroup, even for one error
try:
    raise ExceptionGroup("single", [ValueError("only one")])
except* ValueError as eg:
    print(type(eg))        # <class 'ExceptionGroup'>
    print(len(eg.exceptions))  # 1
    print(eg.exceptions[0])    # only one

# 3. You CANNOT mix except and except* in the same try block
# This is a SyntaxError:
# try:
#     ...
# except ValueError:     # regular
#     ...
# except* TypeError:     # starred
#     ...

# 4. Unmatched exceptions propagate
try:
    raise ExceptionGroup("partial", [
        ValueError("matched"),
        RuntimeError("not matched"),
    ])
except* ValueError:
    print("Got ValueError")
# RuntimeError propagates up as an ExceptionGroup!
```

**When to use ExceptionGroup:**
1. Validation that should report ALL errors, not just the first one
2. Concurrent operations (asyncio.TaskGroup uses it automatically)
3. Cleanup code where multiple cleanup steps can fail independently
4. Any situation where multiple independent errors can occur together''',
    ),
    (
        "thinking/error-handling",
        r'''What are the dangers of using bare "except:" or "except Exception:" in Python? When is it acceptable and what should I do instead?''',
        r'''<think>
Bare except and except Exception are dangerous because:
1. They catch KeyboardInterrupt (Ctrl+C) - user cannot stop the program
2. They catch SystemExit - prevents clean shutdown
3. They hide bugs by silently swallowing unexpected errors
4. They make debugging very difficult
5. They catch GeneratorExit which breaks generators

Wait, I should be precise here. `except:` (bare) catches everything including KeyboardInterrupt, SystemExit, and GeneratorExit. `except Exception:` is slightly better because KeyboardInterrupt and SystemExit inherit from BaseException, not Exception -- so they propagate through. But GeneratorExit also inherits from BaseException since Python 3.x, so actually `except Exception:` does not catch that either. Hmm, I need to double-check... yes, GeneratorExit inherits from BaseException. So the real danger of `except Exception:` is not catching system signals, but rather silently swallowing programming errors like TypeError and AttributeError.

However, there are legitimate use cases:
- Top-level error handlers in web frameworks
- Background task runners that must not crash
- Logging and re-raising

I considered whether "except Exception with logging" is always safe, but actually it is not -- even with logging, if you swallow the exception, the caller assumes success. Therefore the key principle is: catch specific exceptions, or if you must catch broadly, always log and usually re-raise.
</think>

Bare `except:` and `except Exception:` are the most common source of hidden bugs in Python. Here is why and what to do instead:

```python
import logging
import sys
import traceback

logger = logging.getLogger(__name__)

# ============================================================
# THE DANGER: Bare except catches EVERYTHING
# ============================================================

# BAD: Catches KeyboardInterrupt (Ctrl+C cannot stop this!)
while True:
    try:
        do_work()
    except:  # Catches KeyboardInterrupt, SystemExit, GeneratorExit!
        pass   # Silent! No logging, no re-raise, just swallowed

# BAD: Catches Exception (slightly better, but still dangerous)
try:
    result = process(data)
except Exception:
    pass  # Hides ALL errors -- impossible to debug

# BAD: Logs but does not fix the problem
try:
    result = process(data)
except Exception as e:
    print(f"Error: {e}")  # Swallowed -- caller thinks it succeeded
    result = None  # Silent wrong result


# ============================================================
# WHY IT IS DANGEROUS: Real-world examples
# ============================================================

# Bug 1: Hiding a TypeError that indicates a real bug
def calculate_total(items):
    total = 0
    for item in items:
        try:
            total += item["price"] * item["quantity"]
        except Exception:
            pass  # Silently skips items with wrong structure!
    return total

# items = [{"price": 10, "qty": 2}]  # "qty" not "quantity"!
# calculate_total returns 0 instead of crashing with KeyError
# The bug is hidden for weeks until someone notices wrong totals

# Bug 2: Catching exceptions meant for the caller
def get_user(user_id):
    try:
        return db.query(f"SELECT * FROM users WHERE id = {user_id}")
    except Exception:
        return None  # Hides SQL injection, connection errors, etc.

# Bug 3: Preventing shutdown
def background_worker():
    while True:
        try:
            task = queue.get()
            process(task)
        except:  # Cannot stop this worker with Ctrl+C!
            continue


# ============================================================
# CORRECT PATTERNS
# ============================================================

# PATTERN 1: Catch specific exceptions
def read_config(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Config file not found: %s", path)
        return {}
    except json.JSONDecodeError as e:
        logger.error("Invalid JSON in %s: %s", path, e)
        return {}
    # Other exceptions (PermissionError, etc.) propagate up

# PATTERN 2: Catch broadly but ALWAYS log and re-raise
def handle_request(request):
    try:
        return process_request(request)
    except Exception as e:
        logger.exception("Unhandled error in request handler")
        raise  # RE-RAISE! Do not swallow

# PATTERN 3: Top-level handler (ONLY at the outermost boundary)
def main():
    try:
        app.run()
    except KeyboardInterrupt:
        logger.info("Shutting down (Ctrl+C)")
        sys.exit(0)
    except SystemExit:
        raise  # Always let SystemExit propagate
    except Exception:
        logger.critical("Fatal error", exc_info=True)
        sys.exit(1)

# PATTERN 4: Cleanup that must not fail
def safe_cleanup(resource):
    """Cleanup where you genuinely cannot do anything about failures."""
    try:
        resource.close()
    except Exception:
        # Logging is the MINIMUM you should do
        logger.warning(
            "Failed to close resource %s: %s",
            resource, traceback.format_exc()
        )
        # Do NOT re-raise -- we are in cleanup, and the original
        # error (if any) is more important

# PATTERN 5: Default value with logging
def safe_parse_int(value, default=0):
    """Convert to int with explicit fallback."""
    try:
        return int(value)
    except (ValueError, TypeError) as e:
        logger.debug("Cannot parse %r as int: %s", value, e)
        return default
    # Note: catches only ValueError and TypeError, not everything!


# ============================================================
# WHEN broad except IS acceptable
# ============================================================

# 1. Framework-level error handlers (Django, Flask, FastAPI)
#    These MUST catch all exceptions to return HTTP 500 responses.
#    They always log the full traceback.

# 2. Background task runners (Celery, scheduler)
#    They catch exceptions to prevent one failed task from
#    killing the worker. They always log and report.

# 3. Plugin/extension systems
#    The host catches plugin exceptions to prevent one bad
#    plugin from crashing the application.

# 4. Test frameworks
#    They catch exceptions to report test failures without
#    crashing the test runner.

# IN ALL THESE CASES: The exception is ALWAYS logged,
# and the catch is at the OUTERMOST boundary.

# ============================================================
# CHECKLIST: Before writing "except Exception"
# ============================================================

# Ask yourself:
# 1. Can I catch a more specific exception? (Almost always yes)
# 2. Am I logging the full traceback? (Must be yes)
# 3. Am I re-raising or returning an error indicator? (Should be yes)
# 4. Am I at an application boundary? (Should be yes)
# 5. Would a bug in the try block be visible? (Must be yes)
```

**The golden rule:** Catch the most specific exception you can. If you must catch broadly, ALWAYS log the full traceback (use `logger.exception()`) and consider re-raising. Only swallow exceptions at the outermost application boundary, and even then, always log them.''',
    ),
]
