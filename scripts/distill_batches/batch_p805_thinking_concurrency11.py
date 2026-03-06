"""Phase 1G: Foundation Thinking — Concurrency & Distributed Systems (Part 11)

Connection pooling, thread pool sizing, resource management, and partition tolerance
in distributed systems.
"""

PAIRS = [
    (
        "thinking/concurrency-connection-pooling",
        r'''Our web app creates a new database connection for every request and we're hitting
the PostgreSQL max_connections limit (100):

```python
from fastapi import FastAPI
import asyncpg

app = FastAPI()

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    conn = await asyncpg.connect(
        "postgresql://localhost/mydb"
    )
    try:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE id = $1", user_id
        )
        return dict(row)
    finally:
        await conn.close()
```

With 200 concurrent requests, we get "too many connections" errors. Each connection
takes ~50ms to establish. How do we properly pool connections?''',
        r'''<think>
Problems with connection-per-request:
1. Connection establishment is expensive (~50ms TCP + TLS + auth)
2. PostgreSQL max_connections is typically 100-200
3. Each connection uses ~10MB of server memory
4. With 200 concurrent requests, we need 200 connections (exceeds limit)

Connection pooling:
- Maintain a pool of pre-established connections
- Requests borrow a connection, use it, return it
- Pool has min/max size limits
- Connections are reused across requests

Sizing the pool:
- Too small: requests queue waiting for a connection
- Too large: wastes DB memory, may hit max_connections
- Rule of thumb: pool_size = 2 * cpu_cores (on the DB server)
- For most apps: 10-25 connections per app instance

Also consider:
- Connection validation (test before use)
- Idle timeout (close connections unused for too long)
- Max lifetime (close connections after N minutes to handle DNS changes)
- Connection health checks
- PgBouncer for connection pooling at the PostgreSQL level
</think>

## Proper Connection Pool Setup

```python
from fastapi import FastAPI
import asyncpg
from contextlib import asynccontextmanager

app = FastAPI()
pool: asyncpg.Pool = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle: create pool on startup, close on shutdown."""
    global pool
    pool = await asyncpg.create_pool(
        "postgresql://localhost/mydb",
        min_size=5,           # keep 5 connections warm
        max_size=20,          # never exceed 20 connections
        max_inactive_connection_lifetime=300,  # close idle after 5min
        command_timeout=30,   # query timeout
        max_queries=50000,    # recycle connection after N queries
    )
    yield
    await pool.close()

app = FastAPI(lifespan=lifespan)

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    # Borrow a connection from the pool (returns automatically)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT * FROM users WHERE id = $1", user_id
        )
        return dict(row) if row else {"error": "not found"}

# Or use pool directly for simple queries
@app.get("/users")
async def list_users():
    rows = await pool.fetch("SELECT id, name FROM users LIMIT 100")
    return [dict(r) for r in rows]
```

### Connection Pool Monitoring

```python
@app.get("/health/db")
async def db_health():
    return {
        "pool_size": pool.get_size(),
        "pool_free": pool.get_idle_size(),
        "pool_used": pool.get_size() - pool.get_idle_size(),
        "pool_min": pool.get_min_size(),
        "pool_max": pool.get_max_size(),
    }
```

### With PgBouncer (production best practice)

```ini
; pgbouncer.ini
[databases]
mydb = host=localhost port=5432 dbname=mydb

[pgbouncer]
listen_port = 6432
pool_mode = transaction     ; return conn to pool after each transaction
max_client_conn = 1000      ; accept many app connections
default_pool_size = 25      ; but only use 25 actual PG connections
reserve_pool_size = 5       ; extra connections for burst
server_idle_timeout = 60
```

**Pool sizing guidelines:**

| App Instances | Pool per Instance | Total Connections | PG max_connections |
|---------------|------------------|-------------------|-------------------|
| 1 | 20 | 20 | 30 (headroom) |
| 5 | 10 | 50 | 70 |
| 20 | 5 | 100 | 120 |
| 20 + PgBouncer | 50 (to pgbouncer) | 25 (to PG) | 35 |

**Key insight:** With PgBouncer, each app instance can accept many connections, but
PgBouncer multiplexes them onto a small number of real PostgreSQL connections.'''
    ),
    (
        "thinking/concurrency-thread-pool-sizing",
        r'''Our Java service uses a thread pool for handling requests, but we're not sure how
to size it. With the default pool of 200 threads, we see high CPU but also high
latency. Our workload is mixed: some requests are CPU-heavy (image processing),
others are IO-heavy (database queries). How do we size thread pools correctly?

```java
// Current: one pool for everything
ExecutorService executor = Executors.newFixedThreadPool(200);

public Response handleRequest(Request req) {
    return executor.submit(() -> {
        if (req.type == "image") {
            return processImage(req);    // CPU: 500ms
        } else {
            return queryDatabase(req);   // IO: 50ms (mostly waiting)
        }
    }).get();
}
```''',
        r'''<think>
Thread pool sizing depends on the type of work:

**CPU-bound work:**
- Optimal threads = number of CPU cores
- More threads than cores = context switching overhead, no throughput gain
- Formula: threads = N_cpu (or N_cpu + 1 for scheduling slack)

**IO-bound work:**
- Threads spend most time waiting (DB, network, disk)
- Can have many more threads than cores
- Formula: threads = N_cpu * (1 + wait_time / compute_time)
- If wait is 90% of time: threads = 8 * (1 + 9) = 80

**Mixed workload:**
- DON'T use one pool for both CPU and IO work
- CPU tasks in a small pool starve IO tasks (and vice versa: too many CPU tasks cause context switching)
- Solution: separate pools for CPU-bound and IO-bound work

The current code uses 200 threads for everything. With 8 cores:
- Image processing (CPU): 200 threads fighting for 8 cores = massive context switching
- DB queries (IO): might be fine with 200, but they're queued behind CPU tasks

Fix: two pools, properly sized.
</think>

## Separate Thread Pools by Work Type

```java
public class ThreadPoolConfig {
    private static final int CPU_CORES = Runtime.getRuntime().availableProcessors();

    // CPU-bound pool: ~cores (never more)
    private static final ExecutorService cpuPool =
        new ThreadPoolExecutor(
            CPU_CORES,                      // core size
            CPU_CORES,                      // max size (same — no point going higher)
            60L, TimeUnit.SECONDS,
            new LinkedBlockingQueue<>(100),  // bounded queue for backpressure
            new ThreadPoolExecutor.CallerRunsPolicy()  // slow down caller if full
        );

    // IO-bound pool: cores * (1 + wait/compute)
    // DB queries: ~50ms total, ~5ms compute, ~45ms wait
    // Ratio: 1 + 45/5 = 10, so 8 cores * 10 = 80 threads
    private static final ExecutorService ioPool =
        new ThreadPoolExecutor(
            CPU_CORES * 2,                  // core size
            CPU_CORES * 10,                 // max size
            120L, TimeUnit.SECONDS,
            new SynchronousQueue<>(),       // direct handoff
            new ThreadPoolExecutor.AbortPolicy()
        );

    public Response handleRequest(Request req) {
        if (req.type.equals("image")) {
            return cpuPool.submit(() -> processImage(req)).get();
        } else {
            return ioPool.submit(() -> queryDatabase(req)).get();
        }
    }
}
```

### Python Equivalent

```python
import concurrent.futures
import os

CPU_CORES = os.cpu_count()

# CPU-bound: use ProcessPoolExecutor (bypasses GIL)
cpu_pool = concurrent.futures.ProcessPoolExecutor(
    max_workers=CPU_CORES
)

# IO-bound: use ThreadPoolExecutor (GIL is fine, threads release during IO)
io_pool = concurrent.futures.ThreadPoolExecutor(
    max_workers=CPU_CORES * 10,
    thread_name_prefix="io-worker",
)

async def handle_request(req):
    loop = asyncio.get_event_loop()
    if req.type == "image":
        # CPU work in process pool (true parallelism)
        return await loop.run_in_executor(cpu_pool, process_image, req)
    else:
        # IO work in thread pool
        return await loop.run_in_executor(io_pool, query_database, req)
```

### Thread Pool Sizing Formulas

```python
def optimal_pool_size(
    num_cores: int,
    target_utilization: float,  # 0.0-1.0, typically 0.8
    wait_time_ms: float,
    compute_time_ms: float,
) -> int:
    """Brian Goetz formula from 'Java Concurrency in Practice'."""
    if compute_time_ms == 0:
        return num_cores * 10  # pure IO
    ratio = wait_time_ms / compute_time_ms
    return int(num_cores * target_utilization * (1 + ratio))

# Examples:
print(optimal_pool_size(8, 0.8, wait_time_ms=0, compute_time_ms=500))
# CPU-bound: 8 * 0.8 * (1 + 0) = 6 threads

print(optimal_pool_size(8, 0.8, wait_time_ms=200, compute_time_ms=10))
# IO-bound: 8 * 0.8 * (1 + 20) = 134 threads

print(optimal_pool_size(8, 0.8, wait_time_ms=50, compute_time_ms=50))
# Mixed: 8 * 0.8 * (1 + 1) = 13 threads
```

**Summary:**

| Work Type | Formula | 8-core Example | Queue Strategy |
|-----------|---------|---------------|----------------|
| CPU-bound | N_cpu | 8 threads | Bounded queue + CallerRuns |
| IO-bound | N_cpu * (1 + W/C) | 80-160 threads | SynchronousQueue |
| Mixed | Separate pools | 8 CPU + 80 IO | Per-pool config |'''
    ),
    (
        "thinking/concurrency-partition-tolerance",
        r'''Our distributed cache cluster has 3 nodes. When a network partition splits node C
from nodes A and B, clients connected to node C get stale data while clients on A/B
see updates. After the partition heals, we have conflicting data. How do we handle this?

```
Before partition:
  [Client] -> [Node A] <-> [Node B] <-> [Node C]

During partition:
  [Client1] -> [Node A] <-> [Node B]    |    [Node C] <- [Client2]
                                         ^
                                    network split

Client1 writes key "balance" = 100 to Node A
Client2 writes key "balance" = 200 to Node C
After partition heals: which value wins?
```''',
        r'''<think>
This is the CAP theorem in action. During a network partition, we must choose:
- **CP (Consistency over Availability)**: Reject writes on the minority side (node C refuses
  writes since it can't reach quorum). Data stays consistent but node C is unavailable.
- **AP (Availability over Partition tolerance)**: Both sides accept writes. Data diverges.
  Need conflict resolution after partition heals.

Neither is universally "right" — depends on the use case:
- Bank balances: CP (consistency matters, reject writes on minority)
- Shopping cart: AP (availability matters, merge later)
- Session cache: AP with last-write-wins (good enough)

For AP systems, conflict resolution strategies:
1. Last-Write-Wins (LWW) — timestamp-based, simple but lossy
2. Vector clocks — detect conflicts, let application resolve
3. CRDTs — data structures that merge automatically without conflicts
4. Application-specific merge — domain logic decides

For the "balance" example: LWW is dangerous (loses one write). Need a CRDT counter
or conflict detection + manual resolution.
</think>

## Handling Network Partitions

### Strategy 1: CP — Quorum Writes (Reject Minority)

```python
class ConsistentCache:
    """CP system: requires quorum for reads and writes."""

    def __init__(self, nodes: list, replication_factor: int = 3):
        self.nodes = nodes
        self.rf = replication_factor
        self.quorum = replication_factor // 2 + 1  # majority

    async def write(self, key: str, value: any) -> bool:
        """Write only succeeds if quorum of nodes acknowledge."""
        target_nodes = self._get_nodes_for_key(key)
        results = await asyncio.gather(
            *[node.write(key, value) for node in target_nodes],
            return_exceptions=True,
        )

        acks = sum(1 for r in results if not isinstance(r, Exception))
        if acks >= self.quorum:
            return True
        else:
            # Rollback successful writes
            for node, result in zip(target_nodes, results):
                if not isinstance(result, Exception):
                    await node.delete(key)
            raise QuorumNotReached(
                f"Only {acks}/{self.quorum} nodes acknowledged"
            )

    async def read(self, key: str) -> any:
        """Read from quorum and return the most recent value."""
        target_nodes = self._get_nodes_for_key(key)
        results = await asyncio.gather(
            *[node.read(key) for node in target_nodes],
            return_exceptions=True,
        )

        valid = [
            r for r in results
            if not isinstance(r, Exception) and r is not None
        ]
        if len(valid) < self.quorum:
            raise QuorumNotReached("Cannot read from quorum")

        # Return value with highest version/timestamp
        return max(valid, key=lambda r: r.version)
```

### Strategy 2: AP — Accept All Writes, Merge Later (CRDT)

```python
class GCounter:
    """Grow-only counter CRDT. Merges automatically without conflicts.

    Each node maintains its own counter. The total is the sum of all.
    Merge = take max of each node's counter.
    """

    def __init__(self, node_id: str):
        self.node_id = node_id
        self.counts = {}  # {node_id: count}

    def increment(self, amount: int = 1):
        self.counts[self.node_id] = self.counts.get(self.node_id, 0) + amount

    @property
    def value(self) -> int:
        return sum(self.counts.values())

    def merge(self, other: 'GCounter'):
        """Merge two counters — commutative, associative, idempotent."""
        all_nodes = set(self.counts) | set(other.counts)
        for node in all_nodes:
            self.counts[node] = max(
                self.counts.get(node, 0),
                other.counts.get(node, 0),
            )

class LWWRegister:
    """Last-Write-Wins register. Simple but may lose writes."""

    def __init__(self):
        self.value = None
        self.timestamp = 0

    def set(self, value, timestamp: float = None):
        ts = timestamp or time.time()
        if ts > self.timestamp:
            self.value = value
            self.timestamp = ts

    def merge(self, other: 'LWWRegister'):
        if other.timestamp > self.timestamp:
            self.value = other.value
            self.timestamp = other.timestamp

class LWWMap:
    """Last-Write-Wins map — useful for caches and session stores."""

    def __init__(self):
        self.entries = {}  # key -> LWWRegister

    def set(self, key: str, value: any):
        if key not in self.entries:
            self.entries[key] = LWWRegister()
        self.entries[key].set(value)

    def get(self, key: str):
        reg = self.entries.get(key)
        return reg.value if reg else None

    def merge(self, other: 'LWWMap'):
        for key, reg in other.entries.items():
            if key not in self.entries:
                self.entries[key] = LWWRegister()
            self.entries[key].merge(reg)
```

### Anti-Entropy: Healing After Partition

```python
class AntiEntropy:
    """Periodically sync data between nodes to detect and resolve conflicts."""

    async def sync(self, node_a, node_b):
        """Merkle tree comparison for efficient diff detection."""
        hash_a = await node_a.get_merkle_root()
        hash_b = await node_b.get_merkle_root()

        if hash_a == hash_b:
            return  # in sync

        # Find differing keys
        diff_keys = await self._find_diffs(node_a, node_b)
        for key in diff_keys:
            val_a = await node_a.read(key)
            val_b = await node_b.read(key)
            merged = val_a.merge(val_b)  # CRDT merge
            await node_a.write(key, merged)
            await node_b.write(key, merged)
```

**Decision guide:**

| Use Case | Strategy | Trade-off |
|----------|----------|-----------|
| Bank balance | CP (quorum) | Unavailable during partition |
| Shopping cart | AP (CRDT set) | Always available, auto-merge |
| Config store | CP (consensus) | Unavailable during partition |
| Session cache | AP (LWW) | May lose a recent write |
| Leaderboard | AP (CRDT counter) | Always available, eventually consistent |'''
    ),
    (
        "thinking/concurrency-resource-pool-generic",
        r'''We need a generic resource pool that works for database connections, HTTP clients,
gRPC channels, or any expensive-to-create resource. Requirements:
- Bounded pool size
- Health checking (discard broken resources)
- Idle timeout (close resources not used for a while)
- Metrics (utilization, wait time)

How do we design this?''',
        r'''<think>
A generic resource pool needs:
1. A factory to create new resources
2. A health check to validate resources before lending
3. Bounded size (min and max)
4. Borrowing with timeout (don't wait forever)
5. Return with optional discard (if resource is broken)
6. Background maintenance: close idle resources, validate pool

Design:
- Use asyncio.Queue for available resources
- Semaphore to limit total count
- Background task for maintenance (idle cleanup, health checks)
- Context manager for borrow/return pattern

The pool tracks:
- Available resources (ready to use)
- In-use resources (borrowed)
- Total count (available + in-use)
</think>

## Generic Async Resource Pool

```python
import asyncio
import time
import logging
from typing import TypeVar, Generic, Optional, Protocol
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

T = TypeVar("T")

class ResourceFactory(Protocol[T]):
    async def create(self) -> T: ...
    async def destroy(self, resource: T) -> None: ...
    async def validate(self, resource: T) -> bool: ...

@dataclass
class PooledResource(Generic[T]):
    resource: T
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    use_count: int = 0

@dataclass
class PoolMetrics:
    total: int = 0
    available: int = 0
    in_use: int = 0
    wait_count: int = 0
    total_borrows: int = 0
    total_creates: int = 0
    total_destroys: int = 0
    avg_wait_ms: float = 0

class ResourcePool(Generic[T]):
    def __init__(
        self,
        factory: ResourceFactory[T],
        min_size: int = 2,
        max_size: int = 10,
        max_idle_seconds: float = 300,
        max_lifetime_seconds: float = 3600,
        acquire_timeout: float = 10.0,
        validate_on_borrow: bool = True,
    ):
        self.factory = factory
        self.min_size = min_size
        self.max_size = max_size
        self.max_idle = max_idle_seconds
        self.max_lifetime = max_lifetime_seconds
        self.acquire_timeout = acquire_timeout
        self.validate_on_borrow = validate_on_borrow

        self._available: asyncio.Queue[PooledResource[T]] = asyncio.Queue()
        self._semaphore = asyncio.Semaphore(max_size)
        self._total_count = 0
        self._in_use_count = 0
        self._lock = asyncio.Lock()
        self._closed = False

        # Metrics
        self._total_borrows = 0
        self._total_creates = 0
        self._total_destroys = 0
        self._total_wait_ms = 0.0
        self._maintenance_task: Optional[asyncio.Task] = None

    async def start(self):
        """Initialize pool with min_size resources."""
        for _ in range(self.min_size):
            pooled = await self._create_resource()
            await self._available.put(pooled)
        self._maintenance_task = asyncio.create_task(self._maintenance_loop())

    async def close(self):
        """Drain and close all resources."""
        self._closed = True
        if self._maintenance_task:
            self._maintenance_task.cancel()
        while not self._available.empty():
            pooled = self._available.get_nowait()
            await self._destroy_resource(pooled)

    async def acquire(self) -> T:
        """Borrow a resource from the pool."""
        if self._closed:
            raise RuntimeError("Pool is closed")

        start = time.time()

        # Try to get an existing resource
        while True:
            try:
                pooled = self._available.get_nowait()
                # Check lifetime
                if time.time() - pooled.created_at > self.max_lifetime:
                    await self._destroy_resource(pooled)
                    continue
                # Validate
                if self.validate_on_borrow:
                    if not await self.factory.validate(pooled.resource):
                        await self._destroy_resource(pooled)
                        continue
                # Good resource
                pooled.last_used_at = time.time()
                pooled.use_count += 1
                async with self._lock:
                    self._in_use_count += 1
                self._total_borrows += 1
                self._total_wait_ms += (time.time() - start) * 1000
                return pooled.resource
            except asyncio.QueueEmpty:
                break

        # No available resource — try to create one (within max_size)
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self.acquire_timeout,
            )
        except asyncio.TimeoutError:
            raise TimeoutError(
                f"Timed out waiting for resource "
                f"(pool: {self._total_count}/{self.max_size})"
            )

        pooled = await self._create_resource()
        pooled.use_count = 1
        async with self._lock:
            self._in_use_count += 1
        self._total_borrows += 1
        self._total_wait_ms += (time.time() - start) * 1000
        return pooled.resource

    async def release(self, resource: T, discard: bool = False):
        """Return a resource to the pool."""
        async with self._lock:
            self._in_use_count -= 1

        if discard or self._closed:
            pooled = PooledResource(resource=resource)
            await self._destroy_resource(pooled)
            self._semaphore.release()
        else:
            pooled = PooledResource(
                resource=resource, last_used_at=time.time()
            )
            await self._available.put(pooled)

    def borrow(self):
        """Context manager for acquire/release."""
        return _PoolContext(self)

    async def _create_resource(self) -> PooledResource[T]:
        resource = await self.factory.create()
        async with self._lock:
            self._total_count += 1
        self._total_creates += 1
        return PooledResource(resource=resource)

    async def _destroy_resource(self, pooled: PooledResource[T]):
        try:
            await self.factory.destroy(pooled.resource)
        except Exception as e:
            logger.warning(f"Error destroying resource: {e}")
        async with self._lock:
            self._total_count -= 1
        self._total_destroys += 1

    async def _maintenance_loop(self):
        """Background: close idle resources, maintain min_size."""
        while not self._closed:
            await asyncio.sleep(30)
            try:
                await self._evict_idle()
                await self._ensure_min_size()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Pool maintenance error: {e}")

    async def _evict_idle(self):
        """Remove resources idle longer than max_idle."""
        to_check = self._available.qsize()
        for _ in range(to_check):
            try:
                pooled = self._available.get_nowait()
            except asyncio.QueueEmpty:
                break
            if time.time() - pooled.last_used_at > self.max_idle:
                await self._destroy_resource(pooled)
                self._semaphore.release()
            else:
                await self._available.put(pooled)

    async def _ensure_min_size(self):
        async with self._lock:
            deficit = self.min_size - self._total_count
        for _ in range(max(0, deficit)):
            pooled = await self._create_resource()
            await self._available.put(pooled)

    @property
    def metrics(self) -> PoolMetrics:
        return PoolMetrics(
            total=self._total_count,
            available=self._available.qsize(),
            in_use=self._in_use_count,
            total_borrows=self._total_borrows,
            total_creates=self._total_creates,
            total_destroys=self._total_destroys,
            avg_wait_ms=(
                self._total_wait_ms / self._total_borrows
                if self._total_borrows > 0 else 0
            ),
        )

class _PoolContext:
    def __init__(self, pool):
        self.pool = pool
        self.resource = None

    async def __aenter__(self):
        self.resource = await self.pool.acquire()
        return self.resource

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        discard = exc_type is not None  # discard if error occurred
        await self.pool.release(self.resource, discard=discard)

# Usage with a database connection factory
class PgConnectionFactory:
    def __init__(self, dsn: str):
        self.dsn = dsn

    async def create(self):
        import asyncpg
        return await asyncpg.connect(self.dsn)

    async def destroy(self, conn):
        await conn.close()

    async def validate(self, conn) -> bool:
        try:
            await conn.fetchval("SELECT 1")
            return True
        except Exception:
            return False

# Create pool
db_pool = ResourcePool(
    factory=PgConnectionFactory("postgresql://localhost/mydb"),
    min_size=5,
    max_size=20,
)

@app.get("/users/{user_id}")
async def get_user(user_id: int):
    async with db_pool.borrow() as conn:
        return await conn.fetchrow("SELECT * FROM users WHERE id=$1", user_id)
```

**Pool behavior under load:**
- Low traffic: min_size connections kept warm
- Normal: borrow/return cycles, pool stays at min-max range
- Spike: creates up to max_size, excess requests wait (with timeout)
- After spike: idle resources evicted back to min_size
- Bad resource: discarded on error, replaced on next acquire'''
    ),
    (
        "thinking/concurrency-graceful-shutdown",
        r'''Our service processes background jobs and HTTP requests. When we deploy (SIGTERM),
in-flight requests get dropped and background jobs get interrupted mid-processing:

```python
import uvicorn
from fastapi import FastAPI

app = FastAPI()

# Background job processor
async def job_processor():
    while True:
        job = await job_queue.get()
        await process_job(job)  # takes 30-60 seconds

@app.post("/api/submit")
async def submit_work(data: dict):
    result = await expensive_computation(data)  # 5-10 seconds
    return {"result": result}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

How do we shut down gracefully, completing in-flight work?''',
        r'''<think>
Graceful shutdown needs to:
1. Stop accepting new requests
2. Wait for in-flight requests to complete (with timeout)
3. Signal background jobs to stop
4. Wait for current job to finish (with timeout)
5. Clean up resources (close DB connections, flush logs)

The SIGTERM handler should:
1. Set a shutdown flag
2. Stop the HTTP server from accepting new connections
3. Wait for in-flight work with a deadline
4. Force-kill anything still running after deadline

Kubernetes sends SIGTERM, waits terminationGracePeriodSeconds (default 30s), then SIGKILL.
So we have ~30s to finish in-flight work.

Implementation:
- Use asyncio signal handlers
- Track in-flight work with a counter or event
- Background jobs check a shutdown flag between units of work
- HTTP middleware rejects new requests once shutting down
</think>

## Graceful Shutdown Pattern

```python
import asyncio
import signal
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException

logger = logging.getLogger(__name__)

class GracefulShutdown:
    """Coordinates graceful shutdown of all components."""

    def __init__(self, grace_period: float = 25.0):
        self.grace_period = grace_period
        self._shutting_down = False
        self._in_flight = 0
        self._in_flight_event = asyncio.Event()
        self._in_flight_event.set()  # no work in flight initially
        self._lock = asyncio.Lock()
        self._background_tasks: list[asyncio.Task] = []

    @property
    def is_shutting_down(self) -> bool:
        return self._shutting_down

    async def track_request(self):
        """Increment in-flight counter. Raise if shutting down."""
        async with self._lock:
            if self._shutting_down:
                raise HTTPException(503, "Server is shutting down")
            self._in_flight += 1
            self._in_flight_event.clear()

    async def complete_request(self):
        """Decrement in-flight counter."""
        async with self._lock:
            self._in_flight -= 1
            if self._in_flight == 0:
                self._in_flight_event.set()

    def register_background_task(self, task: asyncio.Task):
        self._background_tasks.append(task)

    async def shutdown(self):
        """Graceful shutdown sequence."""
        logger.info("Initiating graceful shutdown...")
        self._shutting_down = True

        # 1. Wait for in-flight requests to complete
        logger.info(f"Waiting for {self._in_flight} in-flight requests...")
        try:
            await asyncio.wait_for(
                self._in_flight_event.wait(),
                timeout=self.grace_period * 0.8,  # 80% of grace period
            )
            logger.info("All in-flight requests completed.")
        except asyncio.TimeoutError:
            logger.warning(
                f"{self._in_flight} requests still in-flight after timeout"
            )

        # 2. Cancel background tasks
        logger.info(f"Cancelling {len(self._background_tasks)} background tasks...")
        for task in self._background_tasks:
            task.cancel()

        # 3. Wait for background tasks to finish cleanup
        if self._background_tasks:
            await asyncio.gather(
                *self._background_tasks, return_exceptions=True
            )

        logger.info("Graceful shutdown complete.")

shutdown_handler = GracefulShutdown(grace_period=25.0)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    loop = asyncio.get_event_loop()

    # Register signal handlers
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(
            sig,
            lambda s=sig: asyncio.create_task(_handle_signal(s)),
        )

    # Start background job processor
    job_task = asyncio.create_task(job_processor())
    shutdown_handler.register_background_task(job_task)

    yield

    # Shutdown
    await shutdown_handler.shutdown()

async def _handle_signal(sig):
    logger.info(f"Received signal {sig.name}")
    await shutdown_handler.shutdown()

app = FastAPI(lifespan=lifespan)

# Middleware to track in-flight requests
@app.middleware("http")
async def track_requests(request, call_next):
    await shutdown_handler.track_request()
    try:
        return await call_next(request)
    finally:
        await shutdown_handler.complete_request()

# Background job processor with shutdown awareness
async def job_processor():
    try:
        while not shutdown_handler.is_shutting_down:
            try:
                job = await asyncio.wait_for(
                    job_queue.get(), timeout=1.0
                )
            except asyncio.TimeoutError:
                continue  # check shutdown flag

            try:
                await process_job(job)
                job_queue.task_done()
            except asyncio.CancelledError:
                # Put job back in queue for another worker/restart
                await job_queue.put(job)
                logger.info("Re-queued interrupted job")
                raise

    except asyncio.CancelledError:
        logger.info("Job processor shutting down")

@app.post("/api/submit")
async def submit_work(data: dict):
    result = await expensive_computation(data)
    return {"result": result}

@app.get("/health")
async def health():
    if shutdown_handler.is_shutting_down:
        raise HTTPException(503, "Shutting down")
    return {"status": "healthy"}
```

**Shutdown timeline with Kubernetes:**
```
T+0s:  Pod receives SIGTERM
T+0s:  Stop accepting new requests (503 on /health)
T+0s:  Load balancer removes pod from rotation (readiness probe fails)
T+1s:  Wait for in-flight HTTP requests to finish
T+20s: Cancel background jobs, re-queue incomplete work
T+25s: Close DB connections, flush logs
T+30s: Kubernetes sends SIGKILL (terminationGracePeriodSeconds)
```

**Key principles:**
1. Health endpoint returns 503 immediately on shutdown (LB stops sending traffic)
2. In-flight requests get time to complete (80% of grace period)
3. Background jobs check shutdown flag between work units
4. Interrupted jobs are re-queued, not lost
5. Always finish within Kubernetes grace period'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
