"""Resilience patterns — circuit breaker, bulkhead, retry, fallback."""

PAIRS = [
    (
        "architecture/circuit-breaker",
        "Show circuit breaker pattern implementation: closed/open/half-open states, failure tracking, and automatic recovery.",
        '''Circuit breaker for resilient service calls:

```python
import time
import asyncio
from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, Any


class CircuitState(Enum):
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing — reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class CircuitBreaker:
    """Prevent cascading failures by stopping calls to failing services.

    CLOSED → (failures > threshold) → OPEN
    OPEN → (timeout elapsed) → HALF_OPEN
    HALF_OPEN → (success) → CLOSED
    HALF_OPEN → (failure) → OPEN
    """
    name: str
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3

    state: CircuitState = CircuitState.CLOSED
    failure_count: int = 0
    success_count: int = 0
    last_failure_time: float = 0
    _half_open_calls: int = 0

    async def call(self, fn: Callable, *args, **kwargs) -> Any:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                self._half_open_calls = 0
            else:
                raise CircuitOpenError(f"Circuit {self.name} is OPEN")

        if self.state == CircuitState.HALF_OPEN:
            if self._half_open_calls >= self.half_open_max_calls:
                raise CircuitOpenError(f"Circuit {self.name} HALF_OPEN limit reached")
            self._half_open_calls += 1

        try:
            result = await fn(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise

    def _on_success(self):
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.half_open_max_calls:
                self.state = CircuitState.CLOSED
                self.failure_count = 0
                self.success_count = 0
        else:
            self.failure_count = max(0, self.failure_count - 1)

    def _on_failure(self):
        self.failure_count += 1
        self.last_failure_time = time.time()
        if self.state == CircuitState.HALF_OPEN:
            self.state = CircuitState.OPEN
        elif self.failure_count >= self.failure_threshold:
            self.state = CircuitState.OPEN
            self.success_count = 0


class CircuitOpenError(Exception):
    pass


class RetryWithBackoff:
    """Retry with exponential backoff and jitter."""

    def __init__(self, max_retries: int = 3, base_delay: float = 1.0,
                 max_delay: float = 30.0, jitter: bool = True):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

    async def execute(self, fn: Callable, *args, **kwargs) -> Any:
        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                return await fn(*args, **kwargs)
            except Exception as e:
                last_error = e
                if attempt < self.max_retries:
                    delay = min(self.base_delay * (2 ** attempt), self.max_delay)
                    if self.jitter:
                        import random
                        delay *= random.uniform(0.5, 1.5)
                    await asyncio.sleep(delay)
        raise last_error


class Bulkhead:
    """Bulkhead pattern: limit concurrent calls to isolate failures."""

    def __init__(self, name: str, max_concurrent: int = 10,
                 max_queue: int = 20):
        self.name = name
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.max_queue = max_queue
        self._queued = 0

    async def execute(self, fn: Callable, *args, **kwargs) -> Any:
        if self._queued >= self.max_queue:
            raise BulkheadFullError(f"Bulkhead {self.name} queue full")
        self._queued += 1
        try:
            async with self.semaphore:
                return await fn(*args, **kwargs)
        finally:
            self._queued -= 1


class BulkheadFullError(Exception):
    pass


class ResilientClient:
    """Compose resilience patterns: retry → circuit breaker → bulkhead."""

    def __init__(self, name: str):
        self.circuit = CircuitBreaker(name)
        self.retry = RetryWithBackoff(max_retries=2)
        self.bulkhead = Bulkhead(name, max_concurrent=20)

    async def call(self, fn: Callable, *args,
                    fallback: Callable = None, **kwargs) -> Any:
        try:
            return await self.bulkhead.execute(
                self.circuit.call,
                lambda: self.retry.execute(fn, *args, **kwargs)
            )
        except (CircuitOpenError, BulkheadFullError) as e:
            if fallback:
                return await fallback(*args, **kwargs)
            raise
```

Key patterns:
1. **Circuit breaker states** — CLOSED (normal) → OPEN (blocking) → HALF_OPEN (probing)
2. **Failure threshold** — open circuit after N consecutive failures; prevent cascading
3. **Exponential backoff** — delay doubles each retry; jitter prevents thundering herd
4. **Bulkhead isolation** — limit concurrency per service; one failing service can't exhaust all resources
5. **Composition** — layer patterns: bulkhead → circuit breaker → retry → fallback'''
    ),
    (
        "architecture/timeout-deadline",
        "Show timeout and deadline propagation: request deadlines, context-based cancellation, and timeout budgeting across microservices.",
        '''Timeout and deadline propagation:

```python
import time
import asyncio
from dataclasses import dataclass
from typing import Optional, Any, Callable
from contextlib import asynccontextmanager


@dataclass
class Deadline:
    """Propagating deadline across service calls."""
    absolute_time: float  # Unix timestamp when request expires
    budget_remaining: float = 0  # Seconds remaining

    @classmethod
    def from_timeout(cls, timeout_seconds: float) -> "Deadline":
        now = time.time()
        return cls(absolute_time=now + timeout_seconds,
                   budget_remaining=timeout_seconds)

    @property
    def remaining(self) -> float:
        return max(0, self.absolute_time - time.time())

    @property
    def is_expired(self) -> bool:
        return time.time() >= self.absolute_time

    def child_timeout(self, overhead_ms: float = 50) -> float:
        """Calculate timeout for downstream call, reserving overhead."""
        remaining = self.remaining - (overhead_ms / 1000)
        return max(0.1, remaining)

    def to_header(self) -> str:
        return str(self.absolute_time)

    @classmethod
    def from_header(cls, header: str) -> "Deadline":
        abs_time = float(header)
        return cls(absolute_time=abs_time,
                   budget_remaining=abs_time - time.time())


class TimeoutBudget:
    """Track timeout budget across a chain of service calls."""

    def __init__(self, total_budget: float):
        self.total = total_budget
        self.deadline = Deadline.from_timeout(total_budget)
        self.segments: list[dict] = []

    @asynccontextmanager
    async def segment(self, name: str):
        """Track time spent in each segment."""
        start = time.time()
        remaining = self.deadline.remaining
        if remaining <= 0:
            raise TimeoutError(f"Budget exhausted before {name}")
        try:
            yield remaining
        finally:
            elapsed = time.time() - start
            self.segments.append({"name": name, "elapsed": elapsed,
                                   "budget_at_start": remaining})

    async def call_with_budget(self, name: str, fn: Callable,
                                *args, **kwargs) -> Any:
        async with self.segment(name) as remaining:
            try:
                return await asyncio.wait_for(
                    fn(*args, **kwargs),
                    timeout=remaining
                )
            except asyncio.TimeoutError:
                raise TimeoutError(
                    f"{name} timed out (budget: {remaining:.2f}s). "
                    f"Segments: {self.segments}"
                )

    def summary(self) -> dict:
        return {
            "total_budget": self.total,
            "remaining": self.deadline.remaining,
            "segments": self.segments,
        }
```

Key patterns:
1. **Deadline propagation** — pass absolute deadline to downstream services; everyone sees same clock
2. **Budget tracking** — subtract time spent at each hop; prevent late responses nobody wants
3. **Overhead reservation** — reserve time for response processing when computing child timeouts
4. **Segment tracking** — record time per service call for latency debugging
5. **Early termination** — check budget before starting work; don't waste resources on expired requests'''
    ),
]
