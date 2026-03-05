"""Multi-region architecture — database replication, CRDTs, global load balancing, data residency compliance."""

PAIRS = [
    (
        "infrastructure/multiregion-database-replication",
        "Show multi-region database replication patterns: primary-replica topology, conflict resolution, read routing, and failover with PostgreSQL and CockroachDB.",
        '''Multi-region database replication patterns:

```python
from __future__ import annotations

import asyncio
import logging
import random
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, AsyncGenerator

from sqlalchemy import text, event
from sqlalchemy.ext.asyncio import (
    AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine,
)

logger = logging.getLogger(__name__)


# ── Region configuration ─────────────────────────────────────────

class Region(str, Enum):
    US_EAST = "us-east-1"
    US_WEST = "us-west-2"
    EU_WEST = "eu-west-1"
    AP_SOUTHEAST = "ap-southeast-1"


@dataclass
class RegionConfig:
    region: Region
    primary_dsn: str          # read-write (primary)
    replica_dsns: list[str]   # read-only (replicas in this region)
    is_primary_region: bool = False
    max_replication_lag_ms: int = 1000


# ── Multi-region connection manager ──────────────────────────────

class MultiRegionDB:
    """Manages database connections across multiple regions.

    Supports:
      - Write routing to primary
      - Read routing to nearest replica
      - Replica lag awareness
      - Automatic failover
    """

    def __init__(
        self,
        local_region: Region,
        configs: dict[Region, RegionConfig],
    ) -> None:
        self._local_region = local_region
        self._configs = configs
        self._primary_engine: AsyncEngine | None = None
        self._replica_engines: dict[Region, list[AsyncEngine]] = {}
        self._session_factories: dict[str, async_sessionmaker] = {}

    async def initialize(self) -> None:
        """Create engines for all configured regions."""
        for region, config in self._configs.items():
            # Primary engine (for writes or if this is the primary region)
            if config.is_primary_region:
                self._primary_engine = create_async_engine(
                    config.primary_dsn,
                    pool_size=20,
                    max_overflow=30,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                )

            # Replica engines
            engines = []
            for dsn in config.replica_dsns:
                engine = create_async_engine(
                    dsn,
                    pool_size=10,
                    max_overflow=20,
                    pool_pre_ping=True,
                    pool_recycle=3600,
                )
                engines.append(engine)
            self._replica_engines[region] = engines

    def _get_nearest_replica(self) -> AsyncEngine:
        """Get a replica engine, preferring the local region."""
        # Try local region first
        local_replicas = self._replica_engines.get(self._local_region, [])
        if local_replicas:
            return random.choice(local_replicas)

        # Fall back to any available replica
        for region, engines in self._replica_engines.items():
            if engines:
                return random.choice(engines)

        # Last resort: use primary
        if self._primary_engine:
            return self._primary_engine

        raise RuntimeError("No database engines available")

    @asynccontextmanager
    async def write_session(self) -> AsyncGenerator[AsyncSession, None]:
        """Session for write operations — always uses primary."""
        if not self._primary_engine:
            raise RuntimeError("No primary database configured")

        factory = async_sessionmaker(
            self._primary_engine,
            expire_on_commit=False,
        )
        session = factory()
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()

    @asynccontextmanager
    async def read_session(
        self,
        region: Region | None = None,
        max_lag_ms: int | None = None,
    ) -> AsyncGenerator[AsyncSession, None]:
        """Session for read operations — uses nearest replica."""
        engine = self._get_nearest_replica()
        factory = async_sessionmaker(engine, expire_on_commit=False)
        session = factory()
        try:
            # Check replication lag if required
            if max_lag_ms is not None:
                lag = await self._check_replication_lag(session)
                if lag > max_lag_ms:
                    logger.warning(
                        f"Replica lag {lag}ms > {max_lag_ms}ms, "
                        f"falling back to primary"
                    )
                    await session.close()
                    async with self.write_session() as primary_session:
                        yield primary_session
                        return

            await session.execute(text("SET TRANSACTION READ ONLY"))
            yield session
        finally:
            await session.rollback()
            await session.close()

    async def _check_replication_lag(self, session: AsyncSession) -> int:
        """Check replication lag in milliseconds (PostgreSQL)."""
        try:
            result = await session.execute(text("""
                SELECT CASE
                    WHEN pg_last_wal_receive_lsn() = pg_last_wal_replay_lsn()
                    THEN 0
                    ELSE EXTRACT(EPOCH FROM now() - pg_last_xact_replay_timestamp()) * 1000
                END AS lag_ms
            """))
            row = result.scalar_one_or_none()
            return int(row) if row else 0
        except Exception:
            return 0  # assume no lag on error

    async def close(self) -> None:
        if self._primary_engine:
            await self._primary_engine.dispose()
        for engines in self._replica_engines.values():
            for engine in engines:
                await engine.dispose()
```

```python
# ── Read-after-write consistency ──────────────────────────────────

import redis.asyncio as aioredis


class ConsistencyManager:
    """Ensures read-after-write consistency across regions.

    After a write, store the write timestamp in Redis.
    On reads, check if the replica is caught up to that timestamp.
    If not, route to primary.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        db: MultiRegionDB,
    ) -> None:
        self._redis = redis_client
        self._db = db

    async def record_write(self, user_id: str) -> None:
        """Record that a user just performed a write."""
        key = f"write:ts:{user_id}"
        await self._redis.set(key, str(time.time()), ex=30)

    async def get_read_session(
        self, user_id: str
    ) -> AsyncGenerator[AsyncSession, None]:
        """Get appropriate session based on consistency needs."""
        key = f"write:ts:{user_id}"
        write_ts = await self._redis.get(key)

        if write_ts:
            # Recent write — read from primary for consistency
            async with self._db.write_session() as session:
                yield session
        else:
            # No recent write — read from replica
            async with self._db.read_session() as session:
                yield session


# ── CockroachDB multi-region configuration ────────────────────────

COCKROACH_MULTI_REGION_SQL = """
-- Enable multi-region on database
ALTER DATABASE myapp PRIMARY REGION "us-east-1";
ALTER DATABASE myapp ADD REGION "eu-west-1";
ALTER DATABASE myapp ADD REGION "ap-southeast-1";

-- Regional by row: each row lives in its owner's region
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email STRING NOT NULL,
    name STRING NOT NULL,
    region crdb_internal_region NOT NULL DEFAULT 'us-east-1',
    created_at TIMESTAMPTZ DEFAULT now()
) LOCALITY REGIONAL BY ROW AS region;

-- Global table: replicated to all regions (read from local)
CREATE TABLE product_catalog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name STRING NOT NULL,
    price DECIMAL(10,2),
    description STRING
) LOCALITY GLOBAL;

-- Regional table: entire table in one region
CREATE TABLE us_tax_records (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    taxpayer_id STRING NOT NULL,
    year INT,
    amount DECIMAL(12,2)
) LOCALITY REGIONAL BY TABLE IN "us-east-1";

-- Survive region failure (requires 5+ regions)
ALTER DATABASE myapp SURVIVE REGION FAILURE;
"""


# ── Failover manager ─────────────────────────────────────────────

class FailoverManager:
    """Handles database failover between regions."""

    def __init__(
        self,
        db: MultiRegionDB,
        health_check_interval: float = 5.0,
    ) -> None:
        self._db = db
        self._interval = health_check_interval
        self._primary_healthy = True

    async def run_health_checks(self) -> None:
        """Continuously check primary database health."""
        while True:
            try:
                async with self._db.write_session() as session:
                    await session.execute(text("SELECT 1"))
                if not self._primary_healthy:
                    logger.info("Primary database recovered")
                self._primary_healthy = True
            except Exception as e:
                if self._primary_healthy:
                    logger.error(f"Primary database failed: {e}")
                    await self._trigger_failover()
                self._primary_healthy = False

            await asyncio.sleep(self._interval)

    async def _trigger_failover(self) -> None:
        """Promote a replica to primary.
        In practice, this is handled by the DB cluster manager."""
        logger.critical("FAILOVER: Promoting replica to primary")
        # PostgreSQL: pg_promote() on the standby
        # CockroachDB: automatic (Raft consensus)
        # Aurora: automatic failover to read replica
```

```python
# ── FastAPI integration ───────────────────────────────────────────

from fastapi import FastAPI, Depends, Request

app = FastAPI()

# Initialize multi-region DB
db = MultiRegionDB(
    local_region=Region.US_EAST,
    configs={
        Region.US_EAST: RegionConfig(
            region=Region.US_EAST,
            primary_dsn="postgresql+asyncpg://user:pass@primary.us-east:5432/myapp",
            replica_dsns=[
                "postgresql+asyncpg://user:pass@replica1.us-east:5432/myapp",
                "postgresql+asyncpg://user:pass@replica2.us-east:5432/myapp",
            ],
            is_primary_region=True,
        ),
        Region.EU_WEST: RegionConfig(
            region=Region.EU_WEST,
            primary_dsn="postgresql+asyncpg://user:pass@primary.eu-west:5432/myapp",
            replica_dsns=[
                "postgresql+asyncpg://user:pass@replica1.eu-west:5432/myapp",
            ],
        ),
    },
)

redis_client = aioredis.from_url("redis://redis:6379")
consistency = ConsistencyManager(redis_client, db)


@app.on_event("startup")
async def startup():
    await db.initialize()


@app.on_event("shutdown")
async def shutdown():
    await db.close()


@app.get("/users/{user_id}")
async def get_user(user_id: str):
    """Read from replica (with consistency check)."""
    async for session in consistency.get_read_session(user_id):
        result = await session.execute(
            text("SELECT id, name, email FROM users WHERE id = :id"),
            {"id": user_id},
        )
        row = result.one_or_none()
        if not row:
            from fastapi import HTTPException
            raise HTTPException(404)
        return {"id": row[0], "name": row[1], "email": row[2]}


@app.put("/users/{user_id}")
async def update_user(user_id: str, name: str):
    """Write to primary, record for consistency."""
    async with db.write_session() as session:
        await session.execute(
            text("UPDATE users SET name = :name WHERE id = :id"),
            {"id": user_id, "name": name},
        )
    await consistency.record_write(user_id)
    return {"status": "updated"}
```

| Topology | Write Latency | Read Latency | Consistency | Use Case |
|---|---|---|---|---|
| Single primary + read replicas | Low (local primary) | Low (local replica) | Eventual | Most web apps |
| Multi-primary (CockroachDB) | Medium (consensus) | Low | Strong | Global consistency needed |
| Regional-by-row | Low (write to local) | Low (read local) | Strong per-row | User data partitioned by region |
| Global tables | Medium (replicate everywhere) | Very low | Strongly consistent reads | Product catalogs, config |
| Active-active PostgreSQL (BDR) | Low | Low | Eventual (conflict resolution) | Specific PostgreSQL need |

Key patterns:
1. **Write to primary, read from replicas** -- simplest multi-region pattern.
2. **Read-after-write consistency** via Redis: track recent writes, route to primary.
3. CockroachDB `REGIONAL BY ROW` keeps each row in its owner's region automatically.
4. **Global tables** replicate everywhere for low-latency reads of reference data.
5. Check **replication lag** before serving reads; fall back to primary if too high.
6. Failover should be automatic (managed DB) -- manual promotion is error-prone.'''
    ),
    (
        "infrastructure/multiregion-crdts",
        "Show CRDTs for multi-region state: distributed counters, shopping carts, and feature flags that converge across regions without coordination.",
        '''CRDTs for multi-region convergence without coordination:

```python
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)


# ── Redis-backed distributed counter (CRDT) ──────────────────────

class RedisGCounter:
    """Grow-only counter backed by Redis hash.

    Each region increments its own field. Total = sum of all fields.
    Merge = element-wise MAX of hash fields across regions.
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        key: str,
        region: str,
    ) -> None:
        self._redis = redis_client
        self._key = f"gcounter:{key}"
        self._region = region

    async def increment(self, amount: int = 1) -> int:
        """Increment this region's counter."""
        new_val = await self._redis.hincrby(
            self._key, self._region, amount
        )
        return new_val

    async def value(self) -> int:
        """Get the total count across all regions."""
        values = await self._redis.hgetall(self._key)
        return sum(int(v) for v in values.values())

    async def merge(self, remote_state: dict[str, int]) -> None:
        """Merge remote state (element-wise MAX)."""
        for region, count in remote_state.items():
            current = await self._redis.hget(self._key, region)
            current_val = int(current) if current else 0
            if count > current_val:
                await self._redis.hset(self._key, region, count)

    async def get_state(self) -> dict[str, int]:
        """Export state for replication to other regions."""
        values = await self._redis.hgetall(self._key)
        return {
            k.decode() if isinstance(k, bytes) else k:
            int(v) for k, v in values.items()
        }


class RedisPNCounter:
    """Positive-Negative counter backed by two Redis hashes."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        key: str,
        region: str,
    ) -> None:
        self._pos = RedisGCounter(redis_client, f"{key}:pos", region)
        self._neg = RedisGCounter(redis_client, f"{key}:neg", region)

    async def increment(self, amount: int = 1) -> None:
        await self._pos.increment(amount)

    async def decrement(self, amount: int = 1) -> None:
        await self._neg.increment(amount)

    async def value(self) -> int:
        pos = await self._pos.value()
        neg = await self._neg.value()
        return pos - neg

    async def merge(
        self, remote_pos: dict[str, int], remote_neg: dict[str, int]
    ) -> None:
        await self._pos.merge(remote_pos)
        await self._neg.merge(remote_neg)

    async def get_state(self) -> dict[str, dict[str, int]]:
        return {
            "pos": await self._pos.get_state(),
            "neg": await self._neg.get_state(),
        }


# ── Multi-region shopping cart (OR-Set CRDT) ─────────────────────

class DistributedCart:
    """Shopping cart using an Observed-Remove Set CRDT.

    Each add creates a unique tag. Remove only removes observed tags.
    Concurrent add + remove = add wins (item stays).
    """

    def __init__(
        self,
        redis_client: aioredis.Redis,
        cart_id: str,
        region: str,
    ) -> None:
        self._redis = redis_client
        self._cart_id = cart_id
        self._region = region
        self._elements_key = f"cart:{cart_id}:elements"
        self._tombstones_key = f"cart:{cart_id}:tombstones"

    async def add_item(
        self,
        product_id: str,
        quantity: int = 1,
        price: float = 0.0,
    ) -> str:
        """Add item to cart with a unique tag."""
        import uuid
        tag = f"{self._region}:{uuid.uuid4().hex[:8]}"
        entry = json.dumps({
            "product_id": product_id,
            "quantity": quantity,
            "price": price,
            "tag": tag,
            "added_at": time.time(),
            "region": self._region,
        })
        await self._redis.hset(self._elements_key, tag, entry)
        return tag

    async def remove_item(self, product_id: str) -> int:
        """Remove all observed instances of a product."""
        elements = await self._redis.hgetall(self._elements_key)
        removed = 0
        for tag, entry_bytes in elements.items():
            entry = json.loads(entry_bytes)
            if entry.get("product_id") == product_id:
                tag_str = tag.decode() if isinstance(tag, bytes) else tag
                await self._redis.sadd(self._tombstones_key, tag_str)
                await self._redis.hdel(self._elements_key, tag_str)
                removed += 1
        return removed

    async def update_quantity(
        self, product_id: str, quantity: int
    ) -> None:
        """Update quantity by removing all + re-adding."""
        elements = await self.get_items()
        matching = [e for e in elements if e["product_id"] == product_id]
        if matching:
            price = matching[0]["price"]
            await self.remove_item(product_id)
            await self.add_item(product_id, quantity, price)

    async def get_items(self) -> list[dict[str, Any]]:
        """Get all items in the cart (excluding tombstoned)."""
        elements = await self._redis.hgetall(self._elements_key)
        tombstones = await self._redis.smembers(self._tombstones_key)
        tombstone_set = {
            t.decode() if isinstance(t, bytes) else t for t in tombstones
        }

        items: dict[str, dict[str, Any]] = {}
        for tag, entry_bytes in elements.items():
            tag_str = tag.decode() if isinstance(tag, bytes) else tag
            if tag_str in tombstone_set:
                continue
            entry = json.loads(entry_bytes)
            pid = entry["product_id"]
            if pid in items:
                items[pid]["quantity"] += entry["quantity"]
            else:
                items[pid] = entry
        return list(items.values())

    async def get_state(self) -> dict[str, Any]:
        """Export state for cross-region replication."""
        elements = await self._redis.hgetall(self._elements_key)
        tombstones = await self._redis.smembers(self._tombstones_key)
        return {
            "elements": {
                (k.decode() if isinstance(k, bytes) else k):
                json.loads(v)
                for k, v in elements.items()
            },
            "tombstones": [
                t.decode() if isinstance(t, bytes) else t
                for t in tombstones
            ],
        }

    async def merge(self, remote_state: dict[str, Any]) -> None:
        """Merge state from another region."""
        remote_elements = remote_state.get("elements", {})
        remote_tombstones = set(remote_state.get("tombstones", []))

        # Add remote elements (if not already present)
        for tag, entry in remote_elements.items():
            exists = await self._redis.hexists(self._elements_key, tag)
            if not exists:
                await self._redis.hset(
                    self._elements_key, tag, json.dumps(entry)
                )

        # Merge tombstones
        if remote_tombstones:
            await self._redis.sadd(self._tombstones_key, *remote_tombstones)

        # Clean up tombstoned elements
        for tag in remote_tombstones:
            await self._redis.hdel(self._elements_key, tag)
```

```python
# ── Cross-region replication service ──────────────────────────────

import asyncio
import httpx


class CRDTReplicator:
    """Replicates CRDT state between regions."""

    def __init__(
        self,
        local_region: str,
        peer_endpoints: dict[str, str],
        replication_interval: float = 5.0,
    ) -> None:
        self._local_region = local_region
        self._peers = peer_endpoints  # region -> URL
        self._interval = replication_interval
        self._client = httpx.AsyncClient(timeout=10.0)
        self._counters: list[RedisGCounter] = []
        self._carts: list[DistributedCart] = []

    def register_counter(self, counter: RedisGCounter) -> None:
        self._counters.append(counter)

    def register_cart(self, cart: DistributedCart) -> None:
        self._carts.append(cart)

    async def run(self) -> None:
        """Periodically push local state to all peers."""
        while True:
            for peer_region, endpoint in self._peers.items():
                try:
                    await self._replicate_to(peer_region, endpoint)
                except Exception as e:
                    logger.error(
                        f"Replication to {peer_region} failed: {e}"
                    )
            await asyncio.sleep(self._interval)

    async def _replicate_to(
        self, peer_region: str, endpoint: str
    ) -> None:
        """Push local CRDT state to a peer region."""
        # Collect local state
        state: dict[str, Any] = {"region": self._local_region}

        for counter in self._counters:
            state[f"counter:{counter._key}"] = await counter.get_state()

        for cart in self._carts:
            state[f"cart:{cart._cart_id}"] = await cart.get_state()

        # Push to peer
        response = await self._client.post(
            f"{endpoint}/crdt/merge",
            json=state,
        )
        response.raise_for_status()

    async def handle_merge(self, remote_state: dict[str, Any]) -> None:
        """Handle incoming CRDT state from a peer."""
        source = remote_state.get("region", "unknown")
        logger.info(f"Merging CRDT state from {source}")

        for counter in self._counters:
            key = f"counter:{counter._key}"
            if key in remote_state:
                await counter.merge(remote_state[key])

        for cart in self._carts:
            key = f"cart:{cart._cart_id}"
            if key in remote_state:
                await cart.merge(remote_state[key])


# ── Usage example ─────────────────────────────────────────────────

async def demo_multiregion_crdt() -> None:
    us_redis = aioredis.from_url("redis://redis-us:6379")
    eu_redis = aioredis.from_url("redis://redis-eu:6379")

    # Page view counter
    us_counter = RedisGCounter(us_redis, "page_views:homepage", "us-east")
    eu_counter = RedisGCounter(eu_redis, "page_views:homepage", "eu-west")

    # Increment in each region independently
    await us_counter.increment(100)
    await eu_counter.increment(50)

    # After replication merge:
    us_state = await us_counter.get_state()
    await eu_counter.merge(us_state)

    eu_state = await eu_counter.get_state()
    await us_counter.merge(eu_state)

    # Both regions see the same total
    assert await us_counter.value() == await eu_counter.value() == 150

    # Shopping cart
    us_cart = DistributedCart(us_redis, "cart-123", "us-east")
    eu_cart = DistributedCart(eu_redis, "cart-123", "eu-west")

    await us_cart.add_item("widget-A", 2, 9.99)
    await eu_cart.add_item("gadget-B", 1, 29.99)

    # Merge both directions
    us_state = await us_cart.get_state()
    await eu_cart.merge(us_state)

    eu_state = await eu_cart.get_state()
    await us_cart.merge(eu_state)

    # Both see both items
    items = await us_cart.get_items()
    assert len(items) == 2

    await us_redis.close()
    await eu_redis.close()
```

| CRDT Type | Redis Backing | Merge Rule | Use Case |
|---|---|---|---|
| G-Counter | Hash (region -> count) | Element-wise MAX | Page views, likes |
| PN-Counter | Two hashes (pos, neg) | MAX on both hashes | Inventory, votes |
| OR-Set (cart) | Hash + Set (tombstones) | Union elements, union tombstones | Shopping carts, tags |
| LWW-Register | Sorted set by timestamp | Latest timestamp wins | User profile fields |
| G-Set (grow-only) | Set | Union | Feature flag enrollments |

Key patterns:
1. **G-Counter** uses Redis HASH with per-region keys; merge = element-wise MAX.
2. **OR-Set** shopping cart uses unique tags per add; tombstones prevent ghost re-adds.
3. **Replication interval** (5s) balances freshness vs. cross-region bandwidth.
4. CRDTs need no coordination -- regions operate independently and merge asynchronously.
5. Always **merge bidirectionally** -- push local state to peers AND accept incoming merges.
6. Use Redis for local CRDT state; HTTP for cross-region state exchange.'''
    ),
    (
        "infrastructure/global-load-balancing-failover",
        "Show global load balancing and failover: DNS-based routing, GeoDNS, health-checked failover, and traffic shifting strategies.",
        '''Global load balancing and failover:

```python
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import httpx

logger = logging.getLogger(__name__)


# ── Region and endpoint definitions ──────────────────────────────

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass
class RegionEndpoint:
    region: str
    endpoint: str
    weight: int = 100
    priority: int = 1        # lower = higher priority
    health: HealthStatus = HealthStatus.HEALTHY
    latency_ms: float = 0.0
    last_check: float = 0.0
    consecutive_failures: int = 0
    metadata: dict[str, str] = field(default_factory=dict)


# ── Health checker ────────────────────────────────────────────────

class HealthChecker:
    """Checks health of regional endpoints."""

    def __init__(
        self,
        check_interval: float = 10.0,
        timeout: float = 5.0,
        failure_threshold: int = 3,
        recovery_threshold: int = 2,
    ) -> None:
        self._interval = check_interval
        self._timeout = timeout
        self._failure_threshold = failure_threshold
        self._recovery_threshold = recovery_threshold
        self._client = httpx.AsyncClient(timeout=timeout)
        self._recovery_count: dict[str, int] = {}

    async def check(self, endpoint: RegionEndpoint) -> HealthStatus:
        """Check a single endpoint's health."""
        try:
            start = time.monotonic()
            response = await self._client.get(
                f"{endpoint.endpoint}/health"
            )
            latency = (time.monotonic() - start) * 1000

            endpoint.latency_ms = latency
            endpoint.last_check = time.time()

            if response.status_code == 200:
                endpoint.consecutive_failures = 0
                self._recovery_count[endpoint.region] = (
                    self._recovery_count.get(endpoint.region, 0) + 1
                )

                # Require N consecutive successes to recover
                if endpoint.health == HealthStatus.UNHEALTHY:
                    if self._recovery_count[endpoint.region] >= self._recovery_threshold:
                        endpoint.health = HealthStatus.HEALTHY
                        self._recovery_count[endpoint.region] = 0
                        logger.info(f"Region {endpoint.region} recovered")
                    else:
                        return HealthStatus.DEGRADED
                else:
                    endpoint.health = HealthStatus.HEALTHY
                return endpoint.health

            elif response.status_code == 503:
                endpoint.health = HealthStatus.DEGRADED
                return HealthStatus.DEGRADED

            else:
                return self._record_failure(endpoint)

        except (httpx.TimeoutException, httpx.ConnectError) as e:
            logger.warning(f"Health check failed for {endpoint.region}: {e}")
            return self._record_failure(endpoint)

    def _record_failure(self, endpoint: RegionEndpoint) -> HealthStatus:
        endpoint.consecutive_failures += 1
        self._recovery_count[endpoint.region] = 0
        if endpoint.consecutive_failures >= self._failure_threshold:
            endpoint.health = HealthStatus.UNHEALTHY
            logger.error(
                f"Region {endpoint.region} marked UNHEALTHY after "
                f"{endpoint.consecutive_failures} failures"
            )
        else:
            endpoint.health = HealthStatus.DEGRADED
        return endpoint.health

    async def run(self, endpoints: list[RegionEndpoint]) -> None:
        """Continuously check all endpoints."""
        while True:
            tasks = [self.check(ep) for ep in endpoints]
            await asyncio.gather(*tasks, return_exceptions=True)
            await asyncio.sleep(self._interval)

    async def close(self) -> None:
        await self._client.aclose()
```

```python
# ── Global load balancer ──────────────────────────────────────────

from enum import Enum
import math


class RoutingPolicy(str, Enum):
    LATENCY = "latency"           # route to lowest latency
    GEOPROXIMITY = "geoproximity" # route to nearest region
    WEIGHTED = "weighted"         # weighted distribution
    FAILOVER = "failover"         # active-passive by priority


class GlobalLoadBalancer:
    """Application-level global load balancer."""

    # Approximate region coordinates for geo-routing
    REGION_COORDS: dict[str, tuple[float, float]] = {
        "us-east-1": (39.0, -77.0),
        "us-west-2": (46.0, -120.0),
        "eu-west-1": (53.0, -6.0),
        "eu-central-1": (50.0, 8.0),
        "ap-southeast-1": (1.3, 103.8),
        "ap-northeast-1": (35.7, 139.7),
    }

    def __init__(
        self,
        endpoints: list[RegionEndpoint],
        policy: RoutingPolicy = RoutingPolicy.LATENCY,
    ) -> None:
        self._endpoints = endpoints
        self._policy = policy
        self._rr_index = 0

    def route(
        self,
        client_region: str | None = None,
        client_coords: tuple[float, float] | None = None,
    ) -> RegionEndpoint | None:
        """Select the best endpoint based on routing policy."""
        healthy = [
            ep for ep in self._endpoints
            if ep.health != HealthStatus.UNHEALTHY
        ]

        if not healthy:
            logger.critical("No healthy endpoints available!")
            # Last resort: try all endpoints
            return self._endpoints[0] if self._endpoints else None

        if self._policy == RoutingPolicy.LATENCY:
            return self._route_by_latency(healthy)
        elif self._policy == RoutingPolicy.GEOPROXIMITY:
            return self._route_by_geo(healthy, client_coords)
        elif self._policy == RoutingPolicy.WEIGHTED:
            return self._route_by_weight(healthy)
        elif self._policy == RoutingPolicy.FAILOVER:
            return self._route_by_priority(healthy)

        return healthy[0]

    def _route_by_latency(
        self, endpoints: list[RegionEndpoint]
    ) -> RegionEndpoint:
        """Route to the endpoint with lowest measured latency."""
        return min(endpoints, key=lambda ep: ep.latency_ms)

    def _route_by_geo(
        self,
        endpoints: list[RegionEndpoint],
        client_coords: tuple[float, float] | None,
    ) -> RegionEndpoint:
        """Route to the geographically nearest region."""
        if not client_coords:
            return self._route_by_latency(endpoints)

        def distance(ep: RegionEndpoint) -> float:
            coords = self.REGION_COORDS.get(ep.region, (0, 0))
            lat1, lon1 = client_coords
            lat2, lon2 = coords
            return math.sqrt((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2)

        return min(endpoints, key=distance)

    def _route_by_weight(
        self, endpoints: list[RegionEndpoint]
    ) -> RegionEndpoint:
        """Weighted random selection."""
        import random
        total_weight = sum(ep.weight for ep in endpoints)
        r = random.uniform(0, total_weight)
        cumulative = 0
        for ep in endpoints:
            cumulative += ep.weight
            if r <= cumulative:
                return ep
        return endpoints[-1]

    def _route_by_priority(
        self, endpoints: list[RegionEndpoint]
    ) -> RegionEndpoint:
        """Active-passive: return highest priority (lowest number)."""
        return min(endpoints, key=lambda ep: ep.priority)

    def get_status(self) -> list[dict[str, Any]]:
        """Get current status of all endpoints."""
        return [
            {
                "region": ep.region,
                "health": ep.health.value,
                "latency_ms": round(ep.latency_ms, 1),
                "weight": ep.weight,
                "priority": ep.priority,
                "last_check": ep.last_check,
            }
            for ep in self._endpoints
        ]
```

```python
# ── Traffic shifting for deployments ──────────────────────────────

class TrafficShifter:
    """Gradually shift traffic between regions for deployments."""

    def __init__(self, balancer: GlobalLoadBalancer) -> None:
        self._balancer = balancer

    async def canary_shift(
        self,
        source_region: str,
        target_region: str,
        steps: list[int],
        step_duration: float = 300.0,
        health_checker: HealthChecker | None = None,
    ) -> bool:
        """Gradually shift traffic from source to target.

        steps: [5, 25, 50, 75, 100] — percentage to target
        """
        source_ep = self._find_endpoint(source_region)
        target_ep = self._find_endpoint(target_region)

        if not source_ep or not target_ep:
            return False

        original_source_weight = source_ep.weight
        original_target_weight = target_ep.weight
        total = original_source_weight + original_target_weight

        for pct in steps:
            target_weight = int(total * pct / 100)
            source_weight = total - target_weight

            target_ep.weight = target_weight
            source_ep.weight = source_weight

            logger.info(
                f"Traffic shift: {source_region}={source_weight}%, "
                f"{target_region}={target_weight}%"
            )

            # Wait and check health
            await asyncio.sleep(step_duration)

            if health_checker:
                status = await health_checker.check(target_ep)
                if status == HealthStatus.UNHEALTHY:
                    logger.error(
                        f"Rollback: {target_region} unhealthy at {pct}%"
                    )
                    source_ep.weight = original_source_weight
                    target_ep.weight = original_target_weight
                    return False

        return True

    def _find_endpoint(self, region: str) -> RegionEndpoint | None:
        for ep in self._balancer._endpoints:
            if ep.region == region:
                return ep
        return None


# ── DNS configuration examples ────────────────────────────────────

DNS_CONFIG = """
# AWS Route 53 — Latency-based routing
resource "aws_route53_record" "api_latency" {
  for_each = {
    "us-east-1" = "us-east-alb.example.com"
    "eu-west-1" = "eu-west-alb.example.com"
    "ap-southeast-1" = "ap-se-alb.example.com"
  }

  zone_id = aws_route53_zone.main.zone_id
  name    = "api.example.com"
  type    = "CNAME"
  ttl     = 60

  set_identifier = each.key
  latency_routing_policy {
    region = each.key
  }

  records = [each.value]

  health_check_id = aws_route53_health_check.api[each.key].id
}

# Health check per region
resource "aws_route53_health_check" "api" {
  for_each = toset(["us-east-1", "eu-west-1", "ap-southeast-1"])

  fqdn              = "${each.value}-alb.example.com"
  port               = 443
  type               = "HTTPS"
  resource_path      = "/health"
  failure_threshold  = 3
  request_interval   = 10

  tags = {
    Name = "api-health-${each.value}"
  }
}

# Failover configuration
resource "aws_route53_record" "api_failover_primary" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "api.example.com"
  type    = "CNAME"
  ttl     = 60

  set_identifier = "primary"
  failover_routing_policy {
    type = "PRIMARY"
  }
  records         = ["us-east-alb.example.com"]
  health_check_id = aws_route53_health_check.api["us-east-1"].id
}

resource "aws_route53_record" "api_failover_secondary" {
  zone_id = aws_route53_zone.main.zone_id
  name    = "api.example.com"
  type    = "CNAME"
  ttl     = 60

  set_identifier = "secondary"
  failover_routing_policy {
    type = "SECONDARY"
  }
  records = ["eu-west-alb.example.com"]
}
"""
```

| Routing Policy | How It Works | Best For |
|---|---|---|
| Latency-based | DNS resolves to lowest-latency region | Most global apps |
| Geo-proximity | Route to nearest region by coordinates | Data residency, compliance |
| Weighted | Distribute by weight percentage | Canary deployments |
| Failover | Active-passive with health checks | DR, simple HA |
| Multivalue | Return multiple IPs, client picks | Client-side resilience |

Key patterns:
1. **GeoDNS** (Route 53 latency routing) routes users to nearest healthy region.
2. **Health checks** with `failure_threshold=3` prevent flapping on transient errors.
3. **Recovery threshold** requires N consecutive successes before marking healthy.
4. **Canary traffic shifting** gradually moves traffic: 5% -> 25% -> 50% -> 100%.
5. Automatic **rollback** on health degradation during traffic shifts.
6. DNS TTL of 60s balances failover speed vs. DNS query volume.'''
    ),
    (
        "infrastructure/data-residency-compliance",
        "Show data residency and compliance routing: GDPR/CCPA-aware data storage, geographic request routing, and PII handling across regions.",
        '''Data residency and compliance routing:

```python
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from fastapi import FastAPI, Request, HTTPException, Depends
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ── Compliance regions and rules ──────────────────────────────────

class ComplianceRegion(str, Enum):
    EU = "eu"           # GDPR
    US = "us"           # CCPA, state laws
    UK = "uk"           # UK GDPR
    BR = "br"           # LGPD
    IN = "in"           # DPDP
    AU = "au"           # Privacy Act
    GLOBAL = "global"   # no specific regulation


@dataclass
class DataResidencyRule:
    """Rules for where data can be stored and processed."""
    compliance_region: ComplianceRegion
    allowed_storage_regions: list[str]
    allowed_processing_regions: list[str]
    requires_encryption_at_rest: bool = True
    requires_encryption_in_transit: bool = True
    max_retention_days: int | None = None
    requires_consent: bool = False
    right_to_erasure: bool = False
    cross_border_transfer_allowed: bool = False
    transfer_mechanism: str | None = None  # SCCs, adequacy decision, etc.


# Compliance rules per regulation
COMPLIANCE_RULES: dict[ComplianceRegion, DataResidencyRule] = {
    ComplianceRegion.EU: DataResidencyRule(
        compliance_region=ComplianceRegion.EU,
        allowed_storage_regions=["eu-west-1", "eu-central-1", "eu-north-1"],
        allowed_processing_regions=["eu-west-1", "eu-central-1", "eu-north-1"],
        requires_encryption_at_rest=True,
        requires_encryption_in_transit=True,
        requires_consent=True,
        right_to_erasure=True,
        cross_border_transfer_allowed=True,
        transfer_mechanism="Standard Contractual Clauses",
    ),
    ComplianceRegion.US: DataResidencyRule(
        compliance_region=ComplianceRegion.US,
        allowed_storage_regions=["us-east-1", "us-west-2"],
        allowed_processing_regions=["us-east-1", "us-west-2", "eu-west-1"],
        requires_encryption_at_rest=True,
        max_retention_days=365 * 7,
        right_to_erasure=True,  # CCPA
        cross_border_transfer_allowed=True,
    ),
    ComplianceRegion.BR: DataResidencyRule(
        compliance_region=ComplianceRegion.BR,
        allowed_storage_regions=["sa-east-1"],
        allowed_processing_regions=["sa-east-1"],
        requires_encryption_at_rest=True,
        requires_consent=True,
        right_to_erasure=True,
        cross_border_transfer_allowed=False,
    ),
}


# ── Data classification ──────────────────────────────────────────

class DataCategory(str, Enum):
    PII = "pii"                     # Personally identifiable info
    SENSITIVE_PII = "sensitive_pii" # Health, biometrics, etc.
    FINANCIAL = "financial"         # Payment, banking data
    USAGE = "usage"                 # Analytics, logs
    PUBLIC = "public"               # Non-sensitive data


@dataclass
class DataClassification:
    """Classification of a data field."""
    field_name: str
    category: DataCategory
    requires_masking: bool = False
    requires_tokenization: bool = False
    retention_override_days: int | None = None


# Standard PII field classifications
FIELD_CLASSIFICATIONS: dict[str, DataClassification] = {
    "email": DataClassification("email", DataCategory.PII, requires_masking=True),
    "phone": DataClassification("phone", DataCategory.PII, requires_masking=True),
    "ssn": DataClassification("ssn", DataCategory.SENSITIVE_PII, requires_tokenization=True),
    "name": DataClassification("name", DataCategory.PII),
    "address": DataClassification("address", DataCategory.PII),
    "ip_address": DataClassification("ip_address", DataCategory.PII),
    "dob": DataClassification("dob", DataCategory.SENSITIVE_PII),
    "credit_card": DataClassification("credit_card", DataCategory.FINANCIAL, requires_tokenization=True),
}
```

```python
# ── Compliance-aware data router ──────────────────────────────────

class ComplianceRouter:
    """Routes data storage/processing based on compliance rules."""

    def __init__(
        self,
        rules: dict[ComplianceRegion, DataResidencyRule],
        local_region: str,
    ) -> None:
        self._rules = rules
        self._local_region = local_region

    def get_storage_region(
        self,
        user_country: str,
        data_category: DataCategory = DataCategory.PII,
    ) -> str:
        """Determine where to store user data."""
        compliance = self._country_to_compliance(user_country)
        rule = self._rules.get(compliance)

        if not rule:
            return self._local_region

        # For sensitive data, must be in allowed regions
        if data_category in (DataCategory.PII, DataCategory.SENSITIVE_PII, DataCategory.FINANCIAL):
            allowed = rule.allowed_storage_regions
            if self._local_region in allowed:
                return self._local_region
            return allowed[0]  # primary allowed region

        # Non-sensitive data can go anywhere
        return self._local_region

    def can_process_in_region(
        self,
        user_country: str,
        processing_region: str,
    ) -> bool:
        """Check if data can be processed in the given region."""
        compliance = self._country_to_compliance(user_country)
        rule = self._rules.get(compliance)
        if not rule:
            return True
        return processing_region in rule.allowed_processing_regions

    def get_retention_days(
        self,
        user_country: str,
        data_category: DataCategory,
    ) -> int | None:
        """Get maximum retention period for data."""
        compliance = self._country_to_compliance(user_country)
        rule = self._rules.get(compliance)
        if not rule:
            return None

        # Check field-specific overrides
        return rule.max_retention_days

    def requires_consent(self, user_country: str) -> bool:
        compliance = self._country_to_compliance(user_country)
        rule = self._rules.get(compliance)
        return rule.requires_consent if rule else False

    def supports_erasure(self, user_country: str) -> bool:
        compliance = self._country_to_compliance(user_country)
        rule = self._rules.get(compliance)
        return rule.right_to_erasure if rule else False

    def _country_to_compliance(self, country: str) -> ComplianceRegion:
        EU_COUNTRIES = {
            "DE", "FR", "IT", "ES", "NL", "BE", "AT", "IE", "PT",
            "FI", "SE", "DK", "PL", "CZ", "GR", "HU", "RO", "BG",
            "HR", "SK", "SI", "LT", "LV", "EE", "CY", "LU", "MT",
        }
        if country in EU_COUNTRIES:
            return ComplianceRegion.EU
        if country == "GB":
            return ComplianceRegion.UK
        if country == "US":
            return ComplianceRegion.US
        if country == "BR":
            return ComplianceRegion.BR
        if country == "IN":
            return ComplianceRegion.IN
        if country == "AU":
            return ComplianceRegion.AU
        return ComplianceRegion.GLOBAL


# ── PII masking and tokenization ──────────────────────────────────

class PIIHandler:
    """Mask and tokenize PII fields."""

    @staticmethod
    def mask_email(email: str) -> str:
        parts = email.split("@")
        if len(parts) != 2:
            return "***"
        name = parts[0]
        domain = parts[1]
        masked_name = name[0] + "*" * (len(name) - 2) + name[-1] if len(name) > 2 else "**"
        return f"{masked_name}@{domain}"

    @staticmethod
    def mask_phone(phone: str) -> str:
        digits = "".join(c for c in phone if c.isdigit())
        if len(digits) < 4:
            return "***"
        return "*" * (len(digits) - 4) + digits[-4:]

    @staticmethod
    def tokenize(value: str, salt: str = "default") -> str:
        """One-way tokenization for sensitive fields."""
        return hashlib.sha256(f"{salt}:{value}".encode()).hexdigest()[:32]

    @staticmethod
    def mask_record(
        record: dict[str, Any],
        classifications: dict[str, DataClassification],
    ) -> dict[str, Any]:
        """Apply masking/tokenization to a record based on classifications."""
        masked = dict(record)
        for field_name, classification in classifications.items():
            if field_name not in masked or masked[field_name] is None:
                continue
            if classification.requires_tokenization:
                masked[field_name] = PIIHandler.tokenize(str(masked[field_name]))
            elif classification.requires_masking:
                if field_name == "email":
                    masked[field_name] = PIIHandler.mask_email(masked[field_name])
                elif field_name == "phone":
                    masked[field_name] = PIIHandler.mask_phone(masked[field_name])
                else:
                    val = str(masked[field_name])
                    masked[field_name] = val[:2] + "*" * (len(val) - 2)
        return masked
```

```python
# ── FastAPI middleware for compliance routing ─────────────────────

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class ComplianceMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces data residency rules."""

    def __init__(
        self,
        app: FastAPI,
        router: ComplianceRouter,
        local_region: str,
    ) -> None:
        super().__init__(app)
        self._router = router
        self._local_region = local_region

    async def dispatch(self, request: Request, call_next):
        # Determine user's country from headers, IP, or JWT
        user_country = (
            request.headers.get("x-user-country", "")
            or self._geolocate_ip(request.client.host if request.client else "")
        )

        # Check if this region can process the request
        if user_country and not self._router.can_process_in_region(
            user_country, self._local_region
        ):
            target = self._router.get_storage_region(user_country)
            return JSONResponse(
                status_code=307,
                content={
                    "error": "data_residency_redirect",
                    "message": f"Request must be processed in {target}",
                    "redirect_region": target,
                },
                headers={
                    "X-Data-Region": target,
                    "X-Compliance-Region": self._router._country_to_compliance(
                        user_country
                    ).value,
                },
            )

        # Add compliance context to request state
        request.state.user_country = user_country
        request.state.compliance_region = (
            self._router._country_to_compliance(user_country)
            if user_country else ComplianceRegion.GLOBAL
        )

        response = await call_next(request)
        return response

    def _geolocate_ip(self, ip: str) -> str:
        """Stub for IP geolocation. Use MaxMind GeoIP2 in production."""
        return ""


# ── GDPR data subject access request (DSAR) ──────────────────────

class DSARHandler:
    """Handle Data Subject Access Requests (GDPR Article 15)."""

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def export_user_data(
        self, user_id: str
    ) -> dict[str, Any]:
        """Export all personal data for a user (Article 15)."""
        from sqlalchemy import text
        async with self._session_factory() as session:
            tables = ["users", "orders", "addresses", "preferences", "activity_log"]
            exported: dict[str, Any] = {}

            for table in tables:
                try:
                    result = await session.execute(
                        text(f"SELECT * FROM {table} WHERE user_id = :uid"),
                        {"uid": user_id},
                    )
                    rows = result.mappings().all()
                    exported[table] = [dict(r) for r in rows]
                except Exception:
                    exported[table] = []

            return exported

    async def erase_user_data(
        self, user_id: str
    ) -> dict[str, int]:
        """Right to erasure (Article 17). Delete or anonymize all PII."""
        from sqlalchemy import text
        async with self._session_factory() as session:
            results: dict[str, int] = {}

            # Anonymize instead of delete where referential integrity matters
            result = await session.execute(
                text("""
                    UPDATE users SET
                        email = 'deleted_' || id || '@deleted.invalid',
                        name = 'Deleted User',
                        phone = NULL,
                        address = NULL,
                        deleted_at = NOW()
                    WHERE id = :uid
                """),
                {"uid": user_id},
            )
            results["users_anonymized"] = result.rowcount or 0

            # Hard delete activity logs
            result = await session.execute(
                text("DELETE FROM activity_log WHERE user_id = :uid"),
                {"uid": user_id},
            )
            results["activity_logs_deleted"] = result.rowcount or 0

            await session.commit()
            return results
```

| Regulation | Region | Key Requirements |
|---|---|---|
| GDPR | EU/EEA | Consent, right to erasure, DPO, 72h breach notification |
| UK GDPR | UK | Similar to GDPR, independent adequacy decisions |
| CCPA/CPRA | California/US | Right to know, delete, opt-out of sale |
| LGPD | Brazil | Consent, data localization, DPO |
| DPDP | India | Consent, fiduciary obligations, localization |
| PIPL | China | Strict localization, cross-border review |

| Data Category | Storage Rules | Masking | Retention |
|---|---|---|---|
| PII (name, email) | In compliance region | Mask in logs/exports | Per regulation |
| Sensitive PII (SSN, health) | Strictly in region | Tokenize always | Minimum necessary |
| Financial (credit card) | PCI DSS zones | Tokenize | Per PCI DSS |
| Usage/analytics | Flexible (aggregated) | Anonymize | Business decision |
| Public | Any region | None | Unlimited |

Key patterns:
1. **Country-to-compliance** mapping determines which rules apply per user.
2. **Compliance middleware** redirects requests to the correct processing region.
3. **PII masking** in logs and exports prevents accidental data exposure.
4. **DSAR handler** implements Article 15 (export) and Article 17 (erasure) for GDPR.
5. Anonymize rather than delete when referential integrity requires it.
6. Use `x-user-country` header or IP geolocation to determine data residency.'''
    ),
]
"""
