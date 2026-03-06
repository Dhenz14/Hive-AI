"""Phase 1G: Foundation Thinking — Concurrency & Distributed Systems (Part 10)

Retry strategies: exponential backoff with jitter, circuit breaker pattern,
retry budgets, and deadline propagation in distributed systems.
"""

PAIRS = [
    (
        "thinking/concurrency-exponential-backoff",
        r'''Our service retries failed HTTP calls, but during outages it hammers the
downstream service and makes things worse:

```python
import httpx

MAX_RETRIES = 5

async def call_service(url: str, data: dict):
    for attempt in range(MAX_RETRIES):
        try:
            resp = await httpx.AsyncClient().post(url, json=data, timeout=5.0)
            resp.raise_for_status()
            return resp.json()
        except (httpx.HTTPStatusError, httpx.TimeoutException):
            if attempt == MAX_RETRIES - 1:
                raise
            await asyncio.sleep(1)  # fixed 1-second delay
```

With 100 instances retrying every second, the downstream service gets 500 req/s of
retry traffic on top of normal load. How do we fix this?''',
        r'''<think>
Problems with the current retry:
1. **Fixed delay** — all instances retry at exactly the same intervals, creating
   "thundering herd" / retry storm
2. **No jitter** — synchronized retries amplify load spikes
3. **New client per request** — connection overhead, no pooling
4. **Retries non-idempotent requests** — POST might not be safe to retry
5. **No backoff** — delay stays at 1s regardless of how many failures

Exponential backoff with jitter:
- Base delay doubles each attempt: 1s, 2s, 4s, 8s, 16s
- Jitter randomizes the actual delay within a range
- This spreads retries over time instead of synchronized bursts

Jitter strategies:
1. **Full jitter**: delay = random(0, base * 2^attempt) — most spread
2. **Equal jitter**: delay = base * 2^attempt / 2 + random(0, base * 2^attempt / 2)
3. **Decorrelated jitter**: delay = random(base, prev_delay * 3) — AWS recommended

Also need:
- Max delay cap (don't wait 5 minutes)
- Only retry on retriable errors (5xx, timeout, not 400)
- Retry budget per time window
</think>

## Exponential Backoff with Jitter

```python
import asyncio
import random
import httpx
from typing import Optional, Set

# Retriable status codes
RETRIABLE_STATUS = {429, 500, 502, 503, 504}

class RetryConfig:
    def __init__(
        self,
        max_retries: int = 5,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        jitter: str = "full",            # "full", "equal", "decorrelated"
        retriable_exceptions: tuple = (
            httpx.TimeoutException,
            httpx.ConnectError,
            httpx.PoolTimeout,
        ),
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter
        self.retriable_exceptions = retriable_exceptions

    def get_delay(self, attempt: int, prev_delay: float = 0) -> float:
        """Calculate delay with jitter for this attempt."""
        exp_delay = self.base_delay * (2 ** attempt)

        if self.jitter == "full":
            # Full jitter: uniform random [0, exp_delay]
            delay = random.uniform(0, exp_delay)
        elif self.jitter == "equal":
            # Equal jitter: half fixed + half random
            half = exp_delay / 2
            delay = half + random.uniform(0, half)
        elif self.jitter == "decorrelated":
            # Decorrelated: random [base, prev * 3]
            delay = random.uniform(self.base_delay, max(self.base_delay, prev_delay * 3))
        else:
            delay = exp_delay

        return min(delay, self.max_delay)

async def call_with_retry(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    config: RetryConfig = RetryConfig(),
    **kwargs,
) -> httpx.Response:
    prev_delay = 0
    last_exception = None

    for attempt in range(config.max_retries + 1):
        try:
            resp = await client.request(method, url, **kwargs)

            # Don't retry client errors (except 429)
            if resp.status_code < 500 and resp.status_code != 429:
                return resp

            if resp.status_code in RETRIABLE_STATUS:
                # Use server's Retry-After if provided
                retry_after = resp.headers.get("Retry-After")
                if retry_after and attempt < config.max_retries:
                    delay = float(retry_after)
                else:
                    delay = config.get_delay(attempt, prev_delay)
                    prev_delay = delay

                if attempt < config.max_retries:
                    await asyncio.sleep(delay)
                    continue

            return resp  # non-retriable or exhausted retries

        except config.retriable_exceptions as e:
            last_exception = e
            if attempt < config.max_retries:
                delay = config.get_delay(attempt, prev_delay)
                prev_delay = delay
                await asyncio.sleep(delay)
            else:
                raise

    raise last_exception
```

**Jitter comparison (attempt 3, base=1s):**

| Strategy | No Jitter | Full Jitter | Equal Jitter | Decorrelated |
|----------|-----------|-------------|--------------|--------------|
| Delay range | 8s exactly | [0, 8s] | [4s, 8s] | [1s, 3*prev] |
| Spread | None | Maximum | Moderate | Adaptive |

Full jitter has the best spread and prevents thundering herd most effectively.'''
    ),
    (
        "thinking/concurrency-circuit-breaker",
        r'''Our microservice calls an unreliable payment gateway. When the gateway is down,
requests pile up waiting for timeouts, and our service becomes unresponsive too.
Even with retries and backoff, we waste resources on calls that will definitely fail.
How do we implement a circuit breaker?''',
        r'''<think>
Circuit breaker pattern — inspired by electrical circuit breakers:

States:
1. **CLOSED** (normal): requests flow through. Track failures.
   - If failure rate exceeds threshold -> OPEN
2. **OPEN** (tripped): all requests fail immediately without calling the service.
   - After a timeout period -> HALF_OPEN
3. **HALF_OPEN** (testing): allow ONE request through.
   - If it succeeds -> CLOSED
   - If it fails -> OPEN

Benefits:
- Fail fast when service is known to be down
- Give the failing service time to recover (no retry storm)
- Prevent cascading failures (our service stays responsive)

Implementation needs:
- Sliding window for failure rate calculation
- Configurable thresholds (failure rate, minimum calls)
- Timeout for OPEN -> HALF_OPEN transition
- Thread-safe state transitions
- Optional: half-open can allow N requests (not just 1)
</think>

## Circuit Breaker Implementation

```python
import asyncio
import enum
import time
import threading
from collections import deque
from dataclasses import dataclass
from typing import Callable, Optional

class CircuitState(enum.Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

@dataclass
class CircuitBreakerConfig:
    failure_threshold: float = 0.5    # 50% failure rate trips the breaker
    min_calls: int = 10               # minimum calls before evaluating
    window_size: int = 60             # sliding window in seconds
    open_timeout: float = 30.0        # seconds before trying again
    half_open_max: int = 3            # test calls in half-open state

class CircuitBreaker:
    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        self.name = name
        self.config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._lock = threading.Lock()
        self._opened_at: float = 0
        self._half_open_calls = 0

        # Sliding window of (timestamp, success: bool) tuples
        self._window: deque = deque()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if self._state == CircuitState.OPEN:
                # Check if timeout has elapsed
                if time.time() - self._opened_at >= self.config.open_timeout:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
            return self._state

    def record_success(self):
        with self._lock:
            self._window.append((time.time(), True))
            self._trim_window()
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1
                if self._half_open_calls >= self.config.half_open_max:
                    self._state = CircuitState.CLOSED

    def record_failure(self):
        with self._lock:
            self._window.append((time.time(), False))
            self._trim_window()
            if self._state == CircuitState.HALF_OPEN:
                self._trip()
            elif self._state == CircuitState.CLOSED:
                self._evaluate()

    def _trim_window(self):
        cutoff = time.time() - self.config.window_size
        while self._window and self._window[0][0] < cutoff:
            self._window.popleft()

    def _evaluate(self):
        if len(self._window) < self.config.min_calls:
            return
        failures = sum(1 for _, success in self._window if not success)
        failure_rate = failures / len(self._window)
        if failure_rate >= self.config.failure_threshold:
            self._trip()

    def _trip(self):
        self._state = CircuitState.OPEN
        self._opened_at = time.time()

    async def call(self, func, *args, **kwargs):
        """Execute func through the circuit breaker."""
        state = self.state
        if state == CircuitState.OPEN:
            raise CircuitOpenError(
                f"Circuit '{self.name}' is OPEN. "
                f"Retry after {self.config.open_timeout}s."
            )

        try:
            result = await func(*args, **kwargs)
            self.record_success()
            return result
        except Exception as e:
            self.record_failure()
            raise

class CircuitOpenError(Exception):
    pass

# Usage
payment_breaker = CircuitBreaker(
    "payment-gateway",
    CircuitBreakerConfig(
        failure_threshold=0.5,
        min_calls=5,
        open_timeout=30.0,
    ),
)

async def charge_customer(amount: float):
    try:
        return await payment_breaker.call(
            payment_gateway.charge, amount
        )
    except CircuitOpenError:
        # Fail fast — don't even try
        return {"status": "queued", "message": "Payment queued for retry"}
```

**State diagram:**
```
CLOSED --[failure rate >= 50%]--> OPEN
OPEN --[after 30s timeout]--> HALF_OPEN
HALF_OPEN --[3 successes]--> CLOSED
HALF_OPEN --[any failure]--> OPEN
```'''
    ),
    (
        "thinking/concurrency-retry-budget",
        r'''We have 20 microservices in a chain. Each service retries 3 times on failure.
When the last service in the chain fails, the total retry amplification is enormous:

Service A (3 retries) -> Service B (3 retries) -> Service C (3 retries)
Total calls to C: 3 * 3 * 3 = 27 attempts for one user request!

With 1000 users, that's 27,000 calls to Service C. How do we prevent retry amplification?''',
        r'''<think>
Retry amplification is a classic distributed systems problem. With N services each
retrying M times, the worst case is M^N calls to the deepest service.

Solutions:
1. **Retry budget** — limit total retries per request across the entire chain
2. **Deadline propagation** — pass a deadline; don't retry if deadline has passed
3. **Retry only at the edge** — only the outermost service retries, inner services
   return errors immediately
4. **Adaptive retry budget** — limit retries as a percentage of successful calls
   (e.g., only 10% of calls can be retries)

Google SRE approach: set a retry budget as a ratio. If 10% of calls are retries,
stop retrying until the ratio drops. This prevents retry storms.

Deadline propagation is complementary: propagate the original request's deadline
through all services. If only 2s remain of a 10s deadline, don't start a 5s retry loop.
</think>

## Solution 1: Retry Budget (Limit Retry Ratio)

```python
import time
import threading
from collections import deque

class RetryBudget:
    """Limits retries to a percentage of total calls.

    Google SRE approach: allow retries only if they are < N% of recent traffic.
    Prevents retry storms during outages.
    """

    def __init__(self, ratio: float = 0.1, window: float = 60.0):
        self.ratio = ratio        # max 10% of calls can be retries
        self.window = window
        self._lock = threading.Lock()
        self._calls: deque = deque()    # timestamps of all calls
        self._retries: deque = deque()  # timestamps of retry calls

    def _trim(self, q: deque):
        cutoff = time.time() - self.window
        while q and q[0] < cutoff:
            q.popleft()

    def record_call(self):
        with self._lock:
            self._calls.append(time.time())
            self._trim(self._calls)

    def can_retry(self) -> bool:
        """Check if we're within budget for retries."""
        with self._lock:
            self._trim(self._calls)
            self._trim(self._retries)
            total = len(self._calls)
            retries = len(self._retries)
            if total == 0:
                return True
            return retries / total < self.ratio

    def record_retry(self):
        with self._lock:
            self._retries.append(time.time())
            self._calls.append(time.time())

budget = RetryBudget(ratio=0.1)  # max 10% retries

async def call_downstream(url, data, max_retries=3):
    budget.record_call()
    for attempt in range(max_retries + 1):
        try:
            resp = await client.post(url, json=data)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            if attempt < max_retries and budget.can_retry():
                budget.record_retry()
                await asyncio.sleep(exponential_backoff(attempt))
            else:
                raise  # budget exhausted or out of retries
```

## Solution 2: Deadline Propagation

```python
import time
from contextvars import ContextVar

# Propagate deadline across async call chain
request_deadline: ContextVar[float] = ContextVar("request_deadline")

class DeadlineMiddleware:
    """Extract or set deadline from incoming request."""

    async def __call__(self, request, call_next):
        # Incoming deadline from upstream service
        deadline_header = request.headers.get("X-Deadline")
        if deadline_header:
            deadline = float(deadline_header)
        else:
            deadline = time.time() + 10.0  # default 10s budget

        token = request_deadline.set(deadline)
        try:
            remaining = deadline - time.time()
            if remaining <= 0:
                return JSONResponse(
                    {"error": "Deadline exceeded"}, status_code=504
                )
            return await call_next(request)
        finally:
            request_deadline.reset(token)

async def call_downstream_with_deadline(url, data, max_retries=3):
    """Only retry if there's time remaining in the deadline."""
    deadline = request_deadline.get()

    for attempt in range(max_retries + 1):
        remaining = deadline - time.time()
        if remaining <= 0:
            raise TimeoutError("Request deadline exceeded")

        try:
            resp = await client.post(
                url,
                json=data,
                headers={"X-Deadline": str(deadline)},  # propagate!
                timeout=min(remaining, 5.0),  # don't exceed deadline
            )
            resp.raise_for_status()
            return resp.json()
        except Exception:
            remaining = deadline - time.time()
            delay = exponential_backoff(attempt)
            if attempt < max_retries and remaining > delay + 1.0:
                await asyncio.sleep(delay)
            else:
                raise  # no time for more retries
```

## Solution 3: Retry Only at the Edge

```python
# Edge service (API gateway): retries allowed
@app.post("/api/order")
async def create_order(data: OrderRequest):
    for attempt in range(3):
        try:
            return await order_service.create(data)
        except RetriableError:
            await asyncio.sleep(exponential_backoff(attempt))
    raise HTTPException(503, "Service unavailable")

# Internal service: NO retries, fail fast
class OrderService:
    async def create(self, data):
        # No retries — let the edge service handle retry logic
        inventory = await inventory_client.check(data.items)  # no retry
        payment = await payment_client.charge(data.total)      # no retry
        return await db.create_order(data, inventory, payment)
```

**Retry amplification comparison (3 services, 3 retries each):**

| Strategy | Calls to deepest service | During outage |
|----------|-------------------------|---------------|
| Naive retries | 3^3 = 27 per request | Collapse |
| Retry budget (10%) | ~3-4 per request | Capped at 10% overhead |
| Deadline propagation | Varies, time-bounded | Graceful timeout |
| Edge-only retry | 3 per request | Controlled |'''
    ),
    (
        "thinking/concurrency-retry-idempotent",
        r'''We need to retry a bank transfer operation, but it involves both a debit and a
credit. Retrying naively could debit twice:

```python
async def transfer(from_account: str, to_account: str, amount: float):
    await debit(from_account, amount)   # step 1
    await credit(to_account, amount)    # step 2 — might fail
```

If step 2 fails and we retry the whole transfer, step 1 runs again, debiting twice.
How do we make multi-step operations safely retriable?''',
        r'''<think>
This is the classic problem of making non-idempotent operations retriable.

The transfer has two steps:
1. Debit from_account (decreases balance)
2. Credit to_account (increases balance)

If we retry after step 2 fails, step 1 runs again -> double debit.

Solutions:
1. **Idempotency key per operation** — each debit/credit checks if already done
2. **Transaction log** — record progress, resume from where we left off
3. **Database transaction** — if same DB, wrap both in one transaction
4. **Saga with compensation** — if different DBs, use saga pattern

The transaction log / state machine approach is most general:
- Record the transfer with a unique ID and state PENDING
- Execute each step, updating state as we go
- On retry, check state and skip completed steps
- This is essentially a mini saga orchestrator
</think>

## Idempotent Multi-Step Operations with Transaction Log

```python
import uuid
import enum
from datetime import datetime

class TransferState(enum.Enum):
    PENDING = "pending"
    DEBITED = "debited"
    CREDITED = "credited"
    COMPLETED = "completed"
    FAILED = "failed"
    REVERSED = "reversed"

class IdempotentTransfer:
    def __init__(self, db):
        self.db = db

    async def transfer(
        self,
        from_account: str,
        to_account: str,
        amount: float,
        transfer_id: str = None,
    ) -> dict:
        """Safely retriable transfer. Same transfer_id = same result."""
        transfer_id = transfer_id or str(uuid.uuid4())

        # Check if this transfer was already attempted
        existing = await self.db.fetchrow(
            "SELECT state, result FROM transfers WHERE transfer_id = $1",
            transfer_id,
        )
        if existing:
            return await self._resume(transfer_id, existing["state"],
                                       from_account, to_account, amount)

        # Record new transfer
        await self.db.execute(
            "INSERT INTO transfers (transfer_id, from_account, to_account, "
            "amount, state, created_at) VALUES ($1,$2,$3,$4,$5,NOW())",
            transfer_id, from_account, to_account, amount,
            TransferState.PENDING.value,
        )

        return await self._resume(transfer_id, TransferState.PENDING.value,
                                   from_account, to_account, amount)

    async def _resume(self, transfer_id, state, from_acct, to_acct, amount):
        """Resume from wherever we left off."""

        if state == TransferState.COMPLETED.value:
            return {"status": "completed", "transfer_id": transfer_id}

        if state == TransferState.FAILED.value:
            return {"status": "failed", "transfer_id": transfer_id}

        # Step 1: Debit (skip if already done)
        if state == TransferState.PENDING.value:
            try:
                await self._idempotent_debit(
                    from_acct, amount,
                    idempotency_key=f"{transfer_id}-debit",
                )
                await self._update_state(transfer_id, TransferState.DEBITED)
                state = TransferState.DEBITED.value
            except InsufficientFunds:
                await self._update_state(transfer_id, TransferState.FAILED)
                return {"status": "failed", "error": "Insufficient funds"}

        # Step 2: Credit (skip if already done)
        if state == TransferState.DEBITED.value:
            try:
                await self._idempotent_credit(
                    to_acct, amount,
                    idempotency_key=f"{transfer_id}-credit",
                )
                await self._update_state(transfer_id, TransferState.COMPLETED)
                return {"status": "completed", "transfer_id": transfer_id}
            except Exception:
                # Credit failed — reverse the debit
                await self._idempotent_credit(
                    from_acct, amount,
                    idempotency_key=f"{transfer_id}-reversal",
                )
                await self._update_state(transfer_id, TransferState.REVERSED)
                raise

    async def _idempotent_debit(self, account, amount, idempotency_key):
        """Debit that only executes once per idempotency key."""
        async with self.db.transaction() as tx:
            done = await tx.fetchval(
                "SELECT 1 FROM ledger_entries WHERE idempotency_key = $1",
                idempotency_key,
            )
            if done:
                return  # already executed

            result = await tx.execute(
                "UPDATE accounts SET balance = balance - $1 "
                "WHERE account_id = $2 AND balance >= $1",
                amount, account,
            )
            if result == "UPDATE 0":
                raise InsufficientFunds()

            await tx.execute(
                "INSERT INTO ledger_entries "
                "(idempotency_key, account_id, amount, type, created_at) "
                "VALUES ($1, $2, $3, 'debit', NOW())",
                idempotency_key, account, amount,
            )

    async def _idempotent_credit(self, account, amount, idempotency_key):
        """Credit that only executes once per idempotency key."""
        async with self.db.transaction() as tx:
            done = await tx.fetchval(
                "SELECT 1 FROM ledger_entries WHERE idempotency_key = $1",
                idempotency_key,
            )
            if done:
                return

            await tx.execute(
                "UPDATE accounts SET balance = balance + $1 "
                "WHERE account_id = $2",
                amount, account,
            )
            await tx.execute(
                "INSERT INTO ledger_entries "
                "(idempotency_key, account_id, amount, type, created_at) "
                "VALUES ($1, $2, $3, 'credit', NOW())",
                idempotency_key, account, amount,
            )

    async def _update_state(self, transfer_id, state):
        await self.db.execute(
            "UPDATE transfers SET state = $1, updated_at = NOW() "
            "WHERE transfer_id = $2",
            state.value, transfer_id,
        )
```

**The pattern:** Each sub-operation has its own idempotency key derived from the
parent operation ID. The transaction log tracks progress. On retry, completed steps
are skipped. This makes the entire multi-step operation safely retriable.'''
    ),
    (
        "thinking/concurrency-hedged-requests",
        r'''Our service needs p99 latency under 200ms, but our database occasionally has
long tail latencies (p99 = 500ms) due to GC pauses or slow queries. Most requests
complete in <50ms, but the occasional slow one kills our SLA. What can we do?''',
        r'''<think>
The problem is tail latency — most requests are fast, but a few are very slow. This is
common with databases, caches, or any system with GC pauses, lock contention, or
slow disks.

Hedged requests (also called speculative execution):
1. Send the request to the primary
2. If no response after p50 latency (e.g., 50ms), send the SAME request to a replica
3. Use whichever response arrives first
4. Cancel the other request

This trades extra load (a small percentage of extra requests) for dramatically better
tail latency.

Google's "The Tail at Scale" paper shows hedging can cut p99 from 500ms to ~60ms with
only 2-5% extra load.

Key considerations:
- Only works for idempotent read operations
- Need multiple backends/replicas to hedge against
- The trigger delay matters: too short = too much extra load, too long = no benefit
- Should be disabled when the system is already overloaded
</think>

## Hedged Requests for Tail Latency Reduction

```python
import asyncio
import time
import random
from typing import Any, List

class HedgedRequester:
    """Send speculative requests to reduce tail latency.

    Based on Google's "The Tail at Scale" paper.
    """

    def __init__(
        self,
        backends: List[str],
        hedge_delay_ms: float = 50.0,   # p50 latency
        max_hedges: int = 2,             # max extra requests
    ):
        self.backends = backends
        self.hedge_delay = hedge_delay_ms / 1000.0
        self.max_hedges = max_hedges
        self._hedge_count = 0
        self._total_count = 0

    async def fetch(self, key: str) -> Any:
        """Fetch with hedging — returns first successful response."""
        self._total_count += 1

        # Pick primary + backup backends
        targets = random.sample(self.backends, min(
            1 + self.max_hedges, len(self.backends)
        ))
        primary, *backups = targets

        # Start primary request
        primary_task = asyncio.create_task(
            self._do_fetch(primary, key)
        )

        # Wait for hedge_delay before launching backups
        done, pending = await asyncio.wait(
            {primary_task},
            timeout=self.hedge_delay,
        )

        if done:
            # Primary responded within hedge delay — great!
            return primary_task.result()

        # Primary is slow — hedge!
        self._hedge_count += 1
        hedge_tasks = [
            asyncio.create_task(self._do_fetch(b, key))
            for b in backups
        ]
        all_tasks = {primary_task} | set(hedge_tasks)

        try:
            # Return first completed result
            while all_tasks:
                done, pending = await asyncio.wait(
                    all_tasks,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in done:
                    try:
                        result = task.result()
                        # Got a result — cancel the rest
                        for t in pending:
                            t.cancel()
                        return result
                    except Exception:
                        all_tasks.discard(task)

            raise RuntimeError("All hedged requests failed")
        finally:
            # Ensure all tasks are cleaned up
            for t in all_tasks:
                t.cancel()

    async def _do_fetch(self, backend: str, key: str) -> Any:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{backend}/get/{key}", timeout=1.0)
            resp.raise_for_status()
            return resp.json()

    @property
    def hedge_rate(self) -> float:
        """Percentage of requests that triggered hedging."""
        if self._total_count == 0:
            return 0
        return self._hedge_count / self._total_count

# Usage
hedger = HedgedRequester(
    backends=[
        "http://db-replica-1:8080",
        "http://db-replica-2:8080",
        "http://db-replica-3:8080",
    ],
    hedge_delay_ms=50,  # hedge if primary doesn't respond in 50ms
    max_hedges=1,        # only one extra request
)

@app.get("/api/product/{product_id}")
async def get_product(product_id: str):
    return await hedger.fetch(product_id)
```

**Impact on tail latency:**

| Metric | Without Hedging | With Hedging (p50 delay) |
|--------|----------------|-------------------------|
| p50 | 30ms | 30ms (unchanged) |
| p90 | 100ms | 55ms |
| p99 | 500ms | 65ms |
| p99.9 | 2000ms | 80ms |
| Extra load | 0% | ~5% |

**Rules for hedged requests:**
1. Only for idempotent reads (never hedge writes!)
2. Set hedge delay at p50-p75 latency (not lower)
3. Limit max hedges (1-2 is usually enough)
4. Monitor hedge rate — if >10%, the system has a bigger problem
5. Disable hedging during overload (don't add load to a struggling system)'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
