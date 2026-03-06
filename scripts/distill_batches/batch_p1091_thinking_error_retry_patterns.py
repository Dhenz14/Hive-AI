"""Thinking-trace pairs: retry and resilience patterns."""

PAIRS = [
    (
        "thinking/error-handling",
        r'''How do I implement exponential backoff with jitter for retrying failed API calls? I want to avoid the "thundering herd" problem where all clients retry at the same time.''',
        r'''<think>
Exponential backoff increases the wait time between retries exponentially (1s, 2s, 4s, 8s...). But if all clients started at the same time, they will all retry at the same time (thundering herd). Adding jitter (randomness) to the backoff time spreads the retries out.

There are several jitter strategies:
1. Full jitter: random(0, base * 2^attempt)
2. Equal jitter: base * 2^attempt / 2 + random(0, base * 2^attempt / 2)
3. Decorrelated jitter: min(cap, random(base, previous_sleep * 3))

AWS recommends full jitter as the best general strategy.
</think>

Exponential backoff with jitter prevents the thundering herd problem by spreading retries across time. Here are multiple implementations:

```python
import random
import time
import asyncio
import logging
from functools import wraps
from typing import Callable, Type, Tuple, Optional

logger = logging.getLogger(__name__)

# ============================================================
# BASIC: Exponential backoff with full jitter
# ============================================================

def retry_with_backoff(
    func: Callable,
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
):
    """Retry a function with exponential backoff and full jitter."""
    for attempt in range(max_retries + 1):
        try:
            return func()
        except retryable_exceptions as e:
            if attempt == max_retries:
                logger.error(
                    "All %d retries exhausted. Last error: %s",
                    max_retries, e,
                )
                raise

            # Exponential backoff: base * 2^attempt
            exponential = base_delay * (2 ** attempt)
            # Cap at max_delay
            capped = min(exponential, max_delay)
            # Full jitter: random between 0 and the capped value
            delay = random.uniform(0, capped)

            logger.warning(
                "Attempt %d/%d failed: %s. Retrying in %.2fs",
                attempt + 1, max_retries, e, delay,
            )
            time.sleep(delay)


# Usage:
# result = retry_with_backoff(
#     lambda: requests.get("https://api.example.com/data").json(),
#     max_retries=5,
#     retryable_exceptions=(requests.ConnectionError, requests.Timeout),
# )


# ============================================================
# DECORATOR: Retry decorator with configuration
# ============================================================

def retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    jitter: str = "full",  # "full", "equal", "decorrelated", "none"
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable] = None,
):
    """Decorator for retrying functions with configurable backoff."""

    def calculate_delay(attempt: int, prev_delay: float) -> float:
        exponential = base_delay * (exponential_base ** attempt)
        capped = min(exponential, max_delay)

        if jitter == "full":
            return random.uniform(0, capped)
        elif jitter == "equal":
            half = capped / 2
            return half + random.uniform(0, half)
        elif jitter == "decorrelated":
            return min(max_delay, random.uniform(base_delay, prev_delay * 3))
        else:  # "none"
            return capped

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            prev_delay = base_delay
            last_exception = None

            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt == max_retries:
                        raise

                    delay = calculate_delay(attempt, prev_delay)
                    prev_delay = delay

                    if on_retry:
                        on_retry(attempt + 1, max_retries, e, delay)
                    else:
                        logger.warning(
                            "Retry %d/%d for %s: %s (delay: %.2fs)",
                            attempt + 1, max_retries,
                            func.__name__, e, delay,
                        )
                    time.sleep(delay)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            prev_delay = base_delay
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    if attempt == max_retries:
                        raise
                    delay = calculate_delay(attempt, prev_delay)
                    prev_delay = delay
                    logger.warning(
                        "Retry %d/%d for %s: %s (delay: %.2fs)",
                        attempt + 1, max_retries,
                        func.__name__, e, delay,
                    )
                    await asyncio.sleep(delay)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


# Usage:
import requests

@retry(
    max_retries=5,
    base_delay=1.0,
    jitter="full",
    retryable_exceptions=(
        requests.ConnectionError,
        requests.Timeout,
        requests.HTTPError,
    ),
)
def fetch_data(url):
    response = requests.get(url, timeout=10)
    response.raise_for_status()
    return response.json()

# result = fetch_data("https://api.example.com/data")


# ============================================================
# JITTER COMPARISON (for visualization)
# ============================================================

def compare_jitter_strategies():
    """Show delay values for each jitter strategy."""
    base = 1.0
    max_d = 60.0
    prev = base

    print(f"{'Attempt':<8} {'None':<10} {'Full':<10} {'Equal':<10} {'Decorr':<10}")
    for attempt in range(8):
        exp = min(base * (2 ** attempt), max_d)
        full = random.uniform(0, exp)
        half = exp / 2
        equal = half + random.uniform(0, half)
        decorr = min(max_d, random.uniform(base, prev * 3))
        prev = decorr

        print(f"{attempt:<8} {exp:<10.2f} {full:<10.2f} {equal:<10.2f} {decorr:<10.2f}")

# compare_jitter_strategies()
# Output shows how each strategy distributes delays differently


# ============================================================
# ADVANCED: Conditional retry based on response
# ============================================================

@retry(
    max_retries=3,
    retryable_exceptions=(requests.HTTPError,),
)
def fetch_with_status_check(url):
    response = requests.get(url, timeout=10)

    if response.status_code == 429:  # Rate limited
        retry_after = int(response.headers.get("Retry-After", 60))
        raise requests.HTTPError(
            f"Rate limited. Retry after {retry_after}s"
        )
    elif response.status_code >= 500:  # Server error -- retryable
        raise requests.HTTPError(f"Server error: {response.status_code}")
    elif response.status_code >= 400:  # Client error -- NOT retryable
        # Do NOT raise a retryable exception
        response.raise_for_status()  # Raises HTTPError but won't retry

    return response.json()
```

**Jitter strategy recommendations:**
- **Full jitter** (recommended): `random(0, min(cap, base * 2^attempt))` -- best spread
- **Equal jitter**: guaranteed minimum wait + randomness -- good for SLAs
- **Decorrelated jitter**: each delay based on previous -- smooth progression
- **No jitter**: all clients retry simultaneously -- avoid this''',
    ),
    (
        "thinking/error-handling",
        r'''How do I implement the Circuit Breaker pattern in Python? I want to prevent cascading failures when a downstream service is unhealthy, instead of retrying indefinitely.''',
        r'''<think>
The circuit breaker pattern has three states:
1. CLOSED (normal): requests pass through. Track failures.
2. OPEN (broken): requests fail immediately without calling the service. Wait for a timeout.
3. HALF-OPEN (testing): allow a single request through to test if the service recovered.

Transitions:
- CLOSED -> OPEN: when failure count exceeds threshold
- OPEN -> HALF-OPEN: after the timeout period
- HALF-OPEN -> CLOSED: if the test request succeeds
- HALF-OPEN -> OPEN: if the test request fails

This prevents wasting resources on a known-broken service and allows it time to recover.
</think>

The Circuit Breaker pattern prevents cascading failures by failing fast when a service is unhealthy. Here is a complete implementation:

```python
import time
import threading
import logging
from enum import Enum
from typing import Callable, Optional, Type, Tuple
from functools import wraps
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"       # Normal operation
    OPEN = "open"           # Failing fast
    HALF_OPEN = "half_open" # Testing recovery


@dataclass
class CircuitStats:
    """Track circuit breaker statistics."""
    total_calls: int = 0
    total_failures: int = 0
    total_successes: int = 0
    consecutive_failures: int = 0
    last_failure_time: Optional[float] = None
    last_state_change: float = field(default_factory=time.time)


class CircuitBreaker:
    """Circuit breaker implementation with configurable thresholds."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        half_open_max_calls: int = 1,
        expected_exceptions: Tuple[Type[Exception], ...] = (Exception,),
        name: str = "default",
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.half_open_max_calls = half_open_max_calls
        self.expected_exceptions = expected_exceptions
        self.name = name

        self._state = CircuitState.CLOSED
        self._stats = CircuitStats()
        self._lock = threading.Lock()
        self._half_open_calls = 0

    @property
    def state(self) -> CircuitState:
        # Check if OPEN circuit should transition to HALF_OPEN
        if self._state == CircuitState.OPEN:
            elapsed = time.time() - self._stats.last_failure_time
            if elapsed >= self.recovery_timeout:
                self._transition_to(CircuitState.HALF_OPEN)
        return self._state

    def _transition_to(self, new_state: CircuitState):
        old_state = self._state
        self._state = new_state
        self._stats.last_state_change = time.time()

        if new_state == CircuitState.HALF_OPEN:
            self._half_open_calls = 0

        logger.info(
            "Circuit '%s': %s -> %s (failures: %d)",
            self.name, old_state.value, new_state.value,
            self._stats.consecutive_failures,
        )

    def call(self, func: Callable, *args, **kwargs):
        """Execute a function through the circuit breaker."""
        with self._lock:
            current_state = self.state

            if current_state == CircuitState.OPEN:
                raise CircuitBreakerOpenError(
                    f"Circuit '{self.name}' is OPEN. "
                    f"Recovery in {self._time_until_recovery():.1f}s"
                )

            if current_state == CircuitState.HALF_OPEN:
                if self._half_open_calls >= self.half_open_max_calls:
                    raise CircuitBreakerOpenError(
                        f"Circuit '{self.name}' is HALF_OPEN, "
                        f"max test calls reached"
                    )
                self._half_open_calls += 1

        # Execute the call (outside the lock)
        self._stats.total_calls += 1
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except self.expected_exceptions as e:
            self._on_failure(e)
            raise

    def _on_success(self):
        with self._lock:
            self._stats.total_successes += 1
            self._stats.consecutive_failures = 0
            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.CLOSED)

    def _on_failure(self, error: Exception):
        with self._lock:
            self._stats.total_failures += 1
            self._stats.consecutive_failures += 1
            self._stats.last_failure_time = time.time()

            if self._state == CircuitState.HALF_OPEN:
                self._transition_to(CircuitState.OPEN)
            elif (self._state == CircuitState.CLOSED and
                  self._stats.consecutive_failures >= self.failure_threshold):
                self._transition_to(CircuitState.OPEN)

    def _time_until_recovery(self) -> float:
        if self._stats.last_failure_time is None:
            return 0
        elapsed = time.time() - self._stats.last_failure_time
        return max(0, self.recovery_timeout - elapsed)

    def get_stats(self) -> dict:
        return {
            "name": self.name,
            "state": self.state.value,
            "total_calls": self._stats.total_calls,
            "total_failures": self._stats.total_failures,
            "consecutive_failures": self._stats.consecutive_failures,
            "time_until_recovery": self._time_until_recovery(),
        }


class CircuitBreakerOpenError(Exception):
    """Raised when the circuit breaker is open."""
    pass


# ============================================================
# DECORATOR VERSION
# ============================================================

def circuit_breaker(
    failure_threshold: int = 5,
    recovery_timeout: float = 30.0,
    expected_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    fallback: Optional[Callable] = None,
):
    """Decorator that wraps a function with a circuit breaker."""
    breaker = CircuitBreaker(
        failure_threshold=failure_threshold,
        recovery_timeout=recovery_timeout,
        expected_exceptions=expected_exceptions,
    )

    def decorator(func):
        breaker.name = func.__name__

        @wraps(func)
        def wrapper(*args, **kwargs):
            try:
                return breaker.call(func, *args, **kwargs)
            except CircuitBreakerOpenError:
                if fallback:
                    logger.info(
                        "Circuit open for %s, using fallback",
                        func.__name__,
                    )
                    return fallback(*args, **kwargs)
                raise

        wrapper.circuit_breaker = breaker
        return wrapper

    return decorator


# ============================================================
# USAGE
# ============================================================

import requests

def payment_fallback(order_id, amount):
    """Fallback when payment service is down."""
    logger.warning("Payment service unavailable, queuing order %s", order_id)
    queue_for_later(order_id, amount)
    return {"status": "queued", "order_id": order_id}

@circuit_breaker(
    failure_threshold=3,
    recovery_timeout=60.0,
    expected_exceptions=(requests.ConnectionError, requests.Timeout),
    fallback=payment_fallback,
)
def process_payment(order_id, amount):
    response = requests.post(
        "https://payment.example.com/charge",
        json={"order_id": order_id, "amount": amount},
        timeout=5,
    )
    response.raise_for_status()
    return response.json()

# First 3 failures: calls go through, counting failures
# After 3rd failure: circuit OPENS, calls fail fast with fallback
# After 60s: circuit goes HALF_OPEN, allows one test call
# If test succeeds: circuit CLOSES, normal operation resumes
# If test fails: circuit re-OPENS for another 60s

# Monitor circuit state:
# print(process_payment.circuit_breaker.get_stats())
```

**Circuit breaker best practices:**
1. Set `failure_threshold` based on acceptable error rate
2. Set `recovery_timeout` long enough for the service to recover
3. Always provide a fallback (cached data, queue, degraded response)
4. Monitor circuit state and alert when circuits open
5. Only count relevant exceptions (network errors, not validation errors)''',
    ),
    (
        "thinking/error-handling",
        r'''How do I implement the Bulkhead pattern to isolate failures between different parts of my application? I want to prevent one slow dependency from consuming all my resources.''',
        r'''<think>
The Bulkhead pattern isolates resource pools so that one failing component cannot consume all resources. Named after ship bulkheads that prevent one flooded compartment from sinking the whole ship.

In software, this means:
1. Separate thread pools for different services
2. Separate connection pools for different databases
3. Semaphores to limit concurrent access to a resource
4. Separate timeouts for different operations

The key insight: if Service A is slow and you have a single shared thread pool, all threads get stuck waiting for Service A, and Service B requests cannot be processed either.
</think>

The Bulkhead pattern isolates resources so that one failing dependency cannot starve others. Here is how to implement it:

```python
import asyncio
import threading
import time
import logging
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Optional, Callable

logger = logging.getLogger(__name__)


# ============================================================
# PATTERN 1: Semaphore-based bulkhead (limit concurrency)
# ============================================================

class BulkheadSemaphore:
    """Limit concurrent access to a resource."""

    def __init__(self, name: str, max_concurrent: int, max_wait: float = 5.0):
        self.name = name
        self.max_concurrent = max_concurrent
        self.max_wait = max_wait
        self._semaphore = threading.Semaphore(max_concurrent)
        self._active = 0
        self._rejected = 0

    @contextmanager
    def acquire(self):
        """Acquire a slot in the bulkhead."""
        acquired = self._semaphore.acquire(timeout=self.max_wait)
        if not acquired:
            self._rejected += 1
            raise BulkheadFullError(
                f"Bulkhead '{self.name}' is full "
                f"({self.max_concurrent} concurrent, "
                f"{self._rejected} rejected)"
            )
        self._active += 1
        try:
            yield
        finally:
            self._active -= 1
            self._semaphore.release()

    @property
    def stats(self) -> dict:
        return {
            "name": self.name,
            "active": self._active,
            "max_concurrent": self.max_concurrent,
            "rejected": self._rejected,
        }


class BulkheadFullError(Exception):
    """Raised when a bulkhead has no available capacity."""
    pass


# ============================================================
# PATTERN 2: Thread pool bulkhead (isolated execution)
# ============================================================

class ThreadPoolBulkhead:
    """Isolated thread pool for a specific dependency."""

    def __init__(
        self,
        name: str,
        max_workers: int = 5,
        queue_size: int = 10,
        timeout: float = 30.0,
    ):
        self.name = name
        self.timeout = timeout
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=f"bulkhead-{name}",
        )
        self._semaphore = threading.Semaphore(max_workers + queue_size)
        self._stats = {"submitted": 0, "completed": 0, "failed": 0, "rejected": 0}

    def submit(self, func: Callable, *args, **kwargs):
        """Submit work to the isolated thread pool."""
        acquired = self._semaphore.acquire(blocking=False)
        if not acquired:
            self._stats["rejected"] += 1
            raise BulkheadFullError(
                f"Bulkhead '{self.name}' queue is full"
            )

        self._stats["submitted"] += 1
        try:
            future = self._executor.submit(func, *args, **kwargs)
            try:
                result = future.result(timeout=self.timeout)
                self._stats["completed"] += 1
                return result
            except TimeoutError:
                self._stats["failed"] += 1
                future.cancel()
                raise BulkheadTimeoutError(
                    f"Operation in bulkhead '{self.name}' "
                    f"timed out after {self.timeout}s"
                )
            except Exception:
                self._stats["failed"] += 1
                raise
        finally:
            self._semaphore.release()

    def shutdown(self):
        self._executor.shutdown(wait=False)


class BulkheadTimeoutError(Exception):
    pass


# ============================================================
# USAGE: Isolate multiple dependencies
# ============================================================

class ServiceClient:
    """Client with bulkhead-isolated dependencies."""

    def __init__(self):
        # Each dependency gets its own resource pool
        self.payment_bulkhead = ThreadPoolBulkhead(
            name="payment-service",
            max_workers=5,    # Max 5 concurrent payment calls
            queue_size=10,    # Queue up to 10 more
            timeout=10.0,     # 10s timeout per call
        )
        self.inventory_bulkhead = ThreadPoolBulkhead(
            name="inventory-service",
            max_workers=3,
            queue_size=5,
            timeout=5.0,
        )
        self.notification_bulkhead = ThreadPoolBulkhead(
            name="notification-service",
            max_workers=2,
            queue_size=20,
            timeout=15.0,
        )

    def process_order(self, order):
        """Process order with isolated service calls."""
        # Even if payment service is slow/down, inventory
        # and notification services still have their own threads
        try:
            payment = self.payment_bulkhead.submit(
                self._charge_payment, order
            )
        except (BulkheadFullError, BulkheadTimeoutError) as e:
            logger.error("Payment bulkhead error: %s", e)
            return {"status": "payment_unavailable"}

        try:
            inventory = self.inventory_bulkhead.submit(
                self._update_inventory, order
            )
        except (BulkheadFullError, BulkheadTimeoutError) as e:
            logger.error("Inventory bulkhead error: %s", e)
            # Compensate: refund payment
            self.payment_bulkhead.submit(self._refund_payment, order)
            return {"status": "inventory_unavailable"}

        # Notification is non-critical -- fire and forget
        try:
            self.notification_bulkhead.submit(
                self._send_notification, order
            )
        except (BulkheadFullError, BulkheadTimeoutError):
            logger.warning("Notification skipped (bulkhead full)")

        return {"status": "success", "payment": payment}

    def _charge_payment(self, order):
        import requests
        return requests.post("https://payment.example.com/charge",
                           json=order, timeout=8).json()

    def _update_inventory(self, order):
        import requests
        return requests.post("https://inventory.example.com/reserve",
                           json=order, timeout=4).json()

    def _send_notification(self, order):
        import requests
        return requests.post("https://notify.example.com/send",
                           json=order, timeout=10).json()


# ============================================================
# ASYNC BULKHEAD (for async applications)
# ============================================================

class AsyncBulkhead:
    """Async semaphore-based bulkhead."""

    def __init__(self, name: str, max_concurrent: int = 10):
        self.name = name
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._active = 0

    async def execute(self, coro, timeout: float = 30.0):
        """Execute a coroutine within the bulkhead."""
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(), timeout=5.0
            )
        except asyncio.TimeoutError:
            raise BulkheadFullError(f"Bulkhead '{self.name}' is full")

        self._active += 1
        try:
            return await asyncio.wait_for(coro, timeout=timeout)
        finally:
            self._active -= 1
            self._semaphore.release()

# Usage:
# payment_bh = AsyncBulkhead("payment", max_concurrent=5)
# result = await payment_bh.execute(
#     aiohttp_session.post(url, json=data),
#     timeout=10.0,
# )
```

**Bulkhead design decisions:**
1. **Max workers**: based on downstream service capacity
2. **Queue size**: how many requests to buffer before rejecting
3. **Timeout**: fail fast if the service is too slow
4. Combine with Circuit Breaker: bulkhead limits concurrency, circuit breaker stops retrying
5. Monitor each bulkhead's stats to detect when services degrade''',
    ),
    (
        "thinking/error-handling",
        r'''How do I implement proper timeout patterns in Python? I need to handle both synchronous and asynchronous timeouts, and I want to ensure cleanup happens even when a timeout fires.''',
        r'''<think>
Timeout patterns in Python:
1. socket/request timeouts (most common)
2. threading.Timer for general timeouts
3. signal.alarm for Unix process-level timeouts
4. asyncio.wait_for for async timeouts
5. concurrent.futures timeout
6. Context manager timeout

Important: Python threads cannot be forcefully killed (no Thread.kill()). So timeout for synchronous code is tricky -- you can only timeout at the I/O boundary level (sockets, files) or use signals (Unix only, main thread only).
</think>

Timeout patterns in Python vary by execution model. Here are the correct approaches for each:

```python
import asyncio
import signal
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeout
from contextlib import contextmanager
from typing import Callable, Optional
import logging

logger = logging.getLogger(__name__)

# ============================================================
# PATTERN 1: Socket/HTTP request timeout (most common)
# ============================================================

import requests

def fetch_with_timeout(url, timeout=10):
    """HTTP request with connect and read timeouts."""
    try:
        response = requests.get(
            url,
            timeout=(3, 10),  # (connect_timeout, read_timeout)
        )
        response.raise_for_status()
        return response.json()
    except requests.Timeout as e:
        logger.warning("Request to %s timed out: %s", url, e)
        raise
    except requests.ConnectionError as e:
        logger.warning("Connection to %s failed: %s", url, e)
        raise


# ============================================================
# PATTERN 2: asyncio.wait_for (async timeout)
# ============================================================

async def fetch_with_async_timeout(session, url, timeout=10):
    """Async HTTP request with timeout and cleanup."""
    try:
        async with asyncio.timeout(timeout):
            async with session.get(url) as response:
                return await response.json()
    except asyncio.TimeoutError:
        logger.warning("Async request to %s timed out after %ds", url, timeout)
        raise
    except asyncio.CancelledError:
        logger.info("Request to %s was cancelled", url)
        raise


async def multiple_with_timeout(tasks, timeout=30):
    """Run multiple async tasks with an overall timeout."""
    try:
        results = await asyncio.wait_for(
            asyncio.gather(*tasks, return_exceptions=True),
            timeout=timeout,
        )
        # Check for exceptions in results
        errors = [r for r in results if isinstance(r, Exception)]
        successes = [r for r in results if not isinstance(r, Exception)]
        return successes, errors
    except asyncio.TimeoutError:
        logger.error("Overall timeout of %ds exceeded", timeout)
        # Cancel remaining tasks
        for task in tasks:
            if not task.done():
                task.cancel()
        raise


# ============================================================
# PATTERN 3: Thread pool timeout (sync code)
# ============================================================

def run_with_timeout(func: Callable, timeout: float, *args, **kwargs):
    """Run a synchronous function with a timeout.

    WARNING: This does not actually stop the function -- it just
    stops waiting for it. The function continues running in the
    background thread. Use this only for I/O-bound work that
    respects socket timeouts internally.
    """
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(func, *args, **kwargs)
        try:
            return future.result(timeout=timeout)
        except FuturesTimeout:
            # NOTE: The function is still running in the background!
            # We cannot kill the thread in Python.
            logger.warning(
                "%s did not complete within %ds",
                func.__name__, timeout,
            )
            raise TimeoutError(
                f"{func.__name__} timed out after {timeout}s"
            )


# ============================================================
# PATTERN 4: Signal-based timeout (Unix only, main thread only)
# ============================================================

@contextmanager
def signal_timeout(seconds: float):
    """Timeout using SIGALRM. Unix main thread only.

    This ACTUALLY interrupts the running code (unlike thread timeout).
    """
    def handler(signum, frame):
        raise TimeoutError(f"Operation timed out after {seconds}s")

    # Save old handler and set new one
    old_handler = signal.signal(signal.SIGALRM, handler)
    signal.alarm(int(seconds))
    try:
        yield
    finally:
        signal.alarm(0)  # Cancel the alarm
        signal.signal(signal.SIGALRM, old_handler)

# Usage (Unix only):
# with signal_timeout(5):
#     result = slow_computation()  # Interrupted after 5s


# ============================================================
# PATTERN 5: Timeout with cleanup
# ============================================================

class TimeoutWithCleanup:
    """Execute an operation with timeout and guaranteed cleanup."""

    def __init__(self, timeout: float):
        self.timeout = timeout
        self._cleanup_funcs = []
        self._timed_out = False

    def add_cleanup(self, func: Callable, *args, **kwargs):
        """Register a cleanup function to run on timeout."""
        self._cleanup_funcs.append((func, args, kwargs))

    async def execute(self, coro):
        """Run coroutine with timeout and cleanup."""
        try:
            return await asyncio.wait_for(coro, timeout=self.timeout)
        except asyncio.TimeoutError:
            self._timed_out = True
            logger.warning("Operation timed out after %ds, running cleanup", self.timeout)
            await self._run_cleanup()
            raise

    async def _run_cleanup(self):
        """Run all registered cleanup functions."""
        for func, args, kwargs in self._cleanup_funcs:
            try:
                if asyncio.iscoroutinefunction(func):
                    await func(*args, **kwargs)
                else:
                    func(*args, **kwargs)
            except Exception as e:
                logger.error("Cleanup error: %s", e)


# Usage:
async def process_with_cleanup():
    timeout_handler = TimeoutWithCleanup(timeout=30)

    # Register cleanup actions
    temp_file = create_temp_file()
    timeout_handler.add_cleanup(os.unlink, temp_file)
    timeout_handler.add_cleanup(release_lock, lock_id)

    result = await timeout_handler.execute(
        long_running_operation(temp_file)
    )
    return result


# ============================================================
# PATTERN 6: Cascading timeouts (budget-based)
# ============================================================

class TimeoutBudget:
    """Track remaining time across multiple operations."""

    def __init__(self, total_timeout: float):
        self.total_timeout = total_timeout
        self.start_time = time.time()

    @property
    def remaining(self) -> float:
        elapsed = time.time() - self.start_time
        return max(0, self.total_timeout - elapsed)

    @property
    def expired(self) -> bool:
        return self.remaining <= 0

    def check(self):
        if self.expired:
            raise TimeoutError("Timeout budget exhausted")

# Usage:
def process_order(order):
    budget = TimeoutBudget(total_timeout=30)

    # Each step gets the remaining budget
    payment = fetch_with_timeout(
        "https://payment.example.com/charge",
        timeout=min(10, budget.remaining),
    )
    budget.check()

    inventory = fetch_with_timeout(
        "https://inventory.example.com/reserve",
        timeout=min(5, budget.remaining),
    )
    budget.check()

    notification = fetch_with_timeout(
        "https://notify.example.com/send",
        timeout=min(5, budget.remaining),
    )
    return {"payment": payment, "inventory": inventory}
```

**Key principles:**
1. Always set both connect and read timeouts on HTTP requests
2. Use `asyncio.wait_for()` or `asyncio.timeout()` for async code
3. Thread-based timeouts cannot kill the thread -- the work continues
4. Signal-based timeouts (SIGALRM) actually interrupt code, but Unix main thread only
5. Use a timeout budget when chaining multiple operations to enforce an overall deadline''',
    ),
    (
        "thinking/error-handling",
        r'''How do I combine Circuit Breaker, Retry, Bulkhead, and Timeout patterns into a single resilient service call? What order should they be applied in?''',
        r'''<think>
The order matters! From outermost to innermost:
1. Timeout (overall deadline)
2. Bulkhead (limit concurrency)
3. Circuit Breaker (fail fast if service is known-broken)
4. Retry (retry on transient failures)
5. Actual call (with its own per-request timeout)

This order ensures:
- The overall timeout caps everything
- The bulkhead limits resource consumption
- The circuit breaker prevents retries when the service is down
- Retries happen within the circuit breaker (failures count correctly)
- Each individual call has its own timeout

Let me build a composable resilience layer.
</think>

The resilience patterns should be layered in a specific order. Here is a composable implementation:

```python
import asyncio
import time
import random
import logging
from typing import Callable, Optional, Tuple, Type
from functools import wraps

logger = logging.getLogger(__name__)

# Assume CircuitBreaker, BulkheadSemaphore from previous examples

# ============================================================
# COMPOSABLE RESILIENCE PIPELINE
# ============================================================

class ResilientCall:
    """Compose resilience patterns in the correct order.

    Execution order (outermost to innermost):
    1. Overall timeout
    2. Bulkhead (concurrency limit)
    3. Circuit breaker (fail fast)
    4. Retry with backoff
    5. Per-call timeout
    6. Actual function call
    """

    def __init__(
        self,
        name: str,
        # Timeout settings
        overall_timeout: float = 30.0,
        per_call_timeout: float = 10.0,
        # Retry settings
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 15.0,
        retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
        # Circuit breaker settings
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0,
        # Bulkhead settings
        max_concurrent: int = 10,
        # Fallback
        fallback: Optional[Callable] = None,
    ):
        self.name = name
        self.overall_timeout = overall_timeout
        self.per_call_timeout = per_call_timeout
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay
        self.retryable_exceptions = retryable_exceptions
        self.fallback = fallback

        # Initialize patterns
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._circuit_state = "closed"
        self._failure_count = 0
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._last_failure = 0.0
        self._stats = {
            "total_calls": 0,
            "successes": 0,
            "failures": 0,
            "retries": 0,
            "circuit_opens": 0,
            "bulkhead_rejects": 0,
            "timeouts": 0,
            "fallbacks": 0,
        }

    async def execute(self, func, *args, **kwargs):
        """Execute with full resilience pipeline."""
        self._stats["total_calls"] += 1
        start_time = time.time()

        try:
            # Layer 1: Overall timeout
            return await asyncio.wait_for(
                self._with_bulkhead(func, *args, **kwargs),
                timeout=self.overall_timeout,
            )
        except asyncio.TimeoutError:
            self._stats["timeouts"] += 1
            logger.error(
                "[%s] Overall timeout (%ds) exceeded",
                self.name, self.overall_timeout,
            )
            return self._try_fallback(*args, **kwargs)

    async def _with_bulkhead(self, func, *args, **kwargs):
        """Layer 2: Bulkhead (concurrency limit)."""
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=5.0)
        except asyncio.TimeoutError:
            self._stats["bulkhead_rejects"] += 1
            logger.warning("[%s] Bulkhead full, rejecting", self.name)
            return self._try_fallback(*args, **kwargs)

        try:
            return await self._with_circuit_breaker(func, *args, **kwargs)
        finally:
            self._semaphore.release()

    async def _with_circuit_breaker(self, func, *args, **kwargs):
        """Layer 3: Circuit breaker."""
        if self._circuit_state == "open":
            elapsed = time.time() - self._last_failure
            if elapsed < self._recovery_timeout:
                logger.warning(
                    "[%s] Circuit OPEN, failing fast (%.0fs until recovery)",
                    self.name, self._recovery_timeout - elapsed,
                )
                return self._try_fallback(*args, **kwargs)
            self._circuit_state = "half_open"
            logger.info("[%s] Circuit HALF_OPEN, testing...", self.name)

        try:
            result = await self._with_retry(func, *args, **kwargs)
            # Success: close the circuit
            if self._circuit_state == "half_open":
                self._circuit_state = "closed"
                self._failure_count = 0
                logger.info("[%s] Circuit CLOSED (recovered)", self.name)
            return result
        except Exception:
            self._failure_count += 1
            self._last_failure = time.time()
            if self._failure_count >= self._failure_threshold:
                self._circuit_state = "open"
                self._stats["circuit_opens"] += 1
                logger.error(
                    "[%s] Circuit OPEN after %d failures",
                    self.name, self._failure_count,
                )
            raise

    async def _with_retry(self, func, *args, **kwargs):
        """Layer 4: Retry with exponential backoff and jitter."""
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                # Layer 5: Per-call timeout
                return await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=self.per_call_timeout,
                )
            except self.retryable_exceptions as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = min(
                        self.retry_base_delay * (2 ** attempt),
                        self.retry_max_delay,
                    )
                    delay = random.uniform(0, delay)  # Full jitter
                    self._stats["retries"] += 1
                    logger.warning(
                        "[%s] Attempt %d/%d failed: %s. Retry in %.1fs",
                        self.name, attempt + 1, self.max_retries,
                        e, delay,
                    )
                    await asyncio.sleep(delay)
                else:
                    self._stats["failures"] += 1
                    raise

    def _try_fallback(self, *args, **kwargs):
        """Execute fallback if available."""
        if self.fallback:
            self._stats["fallbacks"] += 1
            logger.info("[%s] Using fallback", self.name)
            return self.fallback(*args, **kwargs)
        raise RuntimeError(f"[{self.name}] No fallback available")

    @property
    def stats(self):
        return {**self._stats, "circuit_state": self._circuit_state}


# ============================================================
# USAGE: Define resilient service calls
# ============================================================

import aiohttp

# Create resilient callers for each dependency
payment_call = ResilientCall(
    name="payment-service",
    overall_timeout=15.0,
    per_call_timeout=5.0,
    max_retries=2,
    max_concurrent=5,
    failure_threshold=3,
    recovery_timeout=30.0,
    retryable_exceptions=(aiohttp.ClientError, asyncio.TimeoutError),
    fallback=lambda order: {"status": "queued", "message": "Payment delayed"},
)

inventory_call = ResilientCall(
    name="inventory-service",
    overall_timeout=10.0,
    per_call_timeout=3.0,
    max_retries=1,
    max_concurrent=10,
    failure_threshold=5,
)

async def process_order(order):
    """Process order with full resilience."""
    async def charge_payment(order):
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://payment.example.com/charge",
                json=order,
            ) as resp:
                return await resp.json()

    result = await payment_call.execute(charge_payment, order)
    return result

# Monitor:
# print(payment_call.stats)
# print(inventory_call.stats)
```

**Pattern ordering (outermost to innermost):**
1. **Timeout** -- caps total time, prevents infinite waits
2. **Bulkhead** -- limits concurrency, prevents resource exhaustion
3. **Circuit Breaker** -- fails fast when service is known-broken
4. **Retry** -- retries transient failures with backoff
5. **Per-call timeout** -- prevents individual calls from hanging
6. **Fallback** -- provides degraded response when all else fails''',
    ),
]
