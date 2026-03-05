"""System design — distributed systems, consistency, scaling, caching strategies."""

PAIRS = [
    (
        "system-design/distributed-consensus",
        "Explain distributed consensus: CAP theorem, Raft algorithm, leader election, and how databases like etcd and CockroachDB use consensus.",
        '''Distributed consensus for reliable systems:

```python
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional
import random
import time

# --- CAP Theorem ---
# In a network partition, you must choose:
# CP: Consistent + Partition-tolerant (reject writes during partition)
#     Examples: etcd, ZooKeeper, CockroachDB
# AP: Available + Partition-tolerant (accept writes, resolve conflicts later)
#     Examples: Cassandra, DynamoDB, CouchDB
# CA: Not possible in distributed systems (single node = not distributed)

# --- Simplified Raft Implementation ---

class NodeState(Enum):
    FOLLOWER = auto()
    CANDIDATE = auto()
    LEADER = auto()

@dataclass
class LogEntry:
    term: int
    index: int
    command: str
    committed: bool = False

@dataclass
class RaftNode:
    """Simplified Raft consensus node."""
    node_id: str
    state: NodeState = NodeState.FOLLOWER
    current_term: int = 0
    voted_for: Optional[str] = None
    log: list[LogEntry] = field(default_factory=list)
    commit_index: int = -1
    leader_id: Optional[str] = None

    # Volatile leader state
    next_index: dict[str, int] = field(default_factory=dict)
    match_index: dict[str, int] = field(default_factory=dict)

    def request_vote(self, candidate_term: int, candidate_id: str,
                     last_log_index: int, last_log_term: int) -> tuple[int, bool]:
        """Handle RequestVote RPC."""
        # Rule 1: Reject if candidate's term is old
        if candidate_term < self.current_term:
            return self.current_term, False

        # Rule 2: Update term if candidate is newer
        if candidate_term > self.current_term:
            self.current_term = candidate_term
            self.state = NodeState.FOLLOWER
            self.voted_for = None

        # Rule 3: Vote if haven't voted or already voted for this candidate
        # AND candidate's log is at least as up-to-date
        if self.voted_for in (None, candidate_id):
            my_last_term = self.log[-1].term if self.log else 0
            my_last_index = len(self.log) - 1

            log_ok = (last_log_term > my_last_term or
                      (last_log_term == my_last_term and
                       last_log_index >= my_last_index))

            if log_ok:
                self.voted_for = candidate_id
                return self.current_term, True

        return self.current_term, False

    def append_entries(self, leader_term: int, leader_id: str,
                       prev_log_index: int, prev_log_term: int,
                       entries: list[LogEntry],
                       leader_commit: int) -> tuple[int, bool]:
        """Handle AppendEntries RPC (heartbeat + replication)."""
        # Rule 1: Reject if leader's term is old
        if leader_term < self.current_term:
            return self.current_term, False

        # Accept leader
        self.current_term = leader_term
        self.state = NodeState.FOLLOWER
        self.leader_id = leader_id

        # Rule 2: Check log consistency
        if prev_log_index >= 0:
            if prev_log_index >= len(self.log):
                return self.current_term, False
            if self.log[prev_log_index].term != prev_log_term:
                # Delete conflicting entries
                self.log = self.log[:prev_log_index]
                return self.current_term, False

        # Rule 3: Append new entries
        for entry in entries:
            if entry.index < len(self.log):
                if self.log[entry.index].term != entry.term:
                    self.log = self.log[:entry.index]
                    self.log.append(entry)
            else:
                self.log.append(entry)

        # Rule 4: Update commit index
        if leader_commit > self.commit_index:
            self.commit_index = min(leader_commit, len(self.log) - 1)

        return self.current_term, True

    def start_election(self, peers: list[str]) -> bool:
        """Transition to candidate and request votes."""
        self.state = NodeState.CANDIDATE
        self.current_term += 1
        self.voted_for = self.node_id
        votes = 1  # Vote for self

        last_log_index = len(self.log) - 1
        last_log_term = self.log[-1].term if self.log else 0

        for peer in peers:
            term, granted = send_request_vote(
                peer, self.current_term, self.node_id,
                last_log_index, last_log_term,
            )
            if granted:
                votes += 1
            if term > self.current_term:
                self.current_term = term
                self.state = NodeState.FOLLOWER
                return False

        # Majority wins
        majority = (len(peers) + 1) // 2 + 1
        if votes >= majority:
            self.state = NodeState.LEADER
            self.leader_id = self.node_id
            # Initialize leader state
            for peer in peers:
                self.next_index[peer] = len(self.log)
                self.match_index[peer] = -1
            return True

        self.state = NodeState.FOLLOWER
        return False

# --- Consistency Levels (practical) ---

CONSISTENCY_LEVELS = """
| Level | Read from | Write to | Use case |
|-------|-----------|----------|----------|
| Strong | Leader | Majority | Financial transactions |
| Bounded staleness | Any, max lag | Majority | Analytics dashboards |
| Session | Same node | Any | User's own data |
| Eventual | Any | Any | Social media feeds |

Real-world mapping:
- PostgreSQL single-node: Strong consistency (ACID)
- CockroachDB: Strong (serializable) across distributed nodes
- Cassandra: Tunable (ONE, QUORUM, ALL per query)
- DynamoDB: Eventual by default, strong optional per read
- Redis: Eventual (async replication to replicas)
"""
```

Raft guarantees:
1. **Election safety** — at most one leader per term
2. **Leader append-only** — leader never overwrites/deletes its log
3. **Log matching** — if two logs contain same index+term, all prior entries match
4. **Leader completeness** — committed entries appear in all future leaders
5. **State machine safety** — all nodes apply same commands in same order'''
    ),
    (
        "system-design/caching-strategies",
        "Explain caching strategies in depth: cache-aside, write-through, write-behind, cache invalidation, and distributed caching patterns.",
        '''Caching strategies for scalable systems:

```python
import hashlib
import json
import time
from dataclasses import dataclass
from typing import Any, Optional, Callable
from functools import wraps

# --- Cache-Aside (Lazy Loading) ---

class CacheAside:
    """Application manages cache explicitly."""

    def __init__(self, cache_client, db_client, default_ttl: int = 300):
        self.cache = cache_client
        self.db = db_client
        self.ttl = default_ttl

    async def get_user(self, user_id: str) -> dict:
        # 1. Check cache
        key = f"user:{user_id}"
        cached = await self.cache.get(key)
        if cached:
            return json.loads(cached)

        # 2. Cache miss → query database
        user = await self.db.get_user(user_id)
        if user:
            # 3. Populate cache
            await self.cache.setex(key, self.ttl, json.dumps(user))
        return user

    async def update_user(self, user_id: str, data: dict):
        # 1. Update database (source of truth)
        await self.db.update_user(user_id, data)
        # 2. Invalidate cache (don't update — avoids race conditions)
        await self.cache.delete(f"user:{user_id}")

# --- Write-Through Cache ---

class WriteThrough:
    """Writes go to cache and DB synchronously."""

    async def update_user(self, user_id: str, data: dict):
        key = f"user:{user_id}"
        # Write to both atomically (or with careful ordering)
        await self.db.update_user(user_id, data)
        user = await self.db.get_user(user_id)
        await self.cache.setex(key, self.ttl, json.dumps(user))
        # Pro: cache always fresh
        # Con: write latency = db + cache

# --- Write-Behind (Write-Back) Cache ---

class WriteBehind:
    """Writes go to cache immediately, DB updated asynchronously."""

    def __init__(self, cache, db, flush_interval: int = 5):
        self.cache = cache
        self.db = db
        self.dirty_keys: set[str] = set()

    async def update_user(self, user_id: str, data: dict):
        key = f"user:{user_id}"
        # Write to cache immediately (fast!)
        await self.cache.setex(key, 3600, json.dumps(data))
        self.dirty_keys.add(key)
        # Pro: very low write latency
        # Con: data loss risk if cache crashes before flush

    async def flush_to_db(self):
        """Background task — flush dirty entries to DB."""
        for key in list(self.dirty_keys):
            data = await self.cache.get(key)
            if data:
                user_id = key.split(":")[1]
                await self.db.update_user(user_id, json.loads(data))
                self.dirty_keys.discard(key)

# --- Cache Stampede Prevention ---

class StampedeProtectedCache:
    """Prevent thundering herd on cache miss."""

    def __init__(self, cache, db):
        self.cache = cache
        self.db = db
        self.locks: dict[str, bool] = {}

    async def get(self, key: str, fetch_fn: Callable, ttl: int = 300) -> Any:
        # Try cache
        cached = await self.cache.get(key)
        if cached:
            data = json.loads(cached)
            # Probabilistic early refresh (stale-while-revalidate)
            remaining_ttl = await self.cache.ttl(key)
            if remaining_ttl < ttl * 0.1:  # Less than 10% TTL left
                if not self.locks.get(key):
                    self.locks[key] = True
                    # Refresh in background
                    import asyncio
                    asyncio.create_task(self._refresh(key, fetch_fn, ttl))
            return data

        # Cache miss — use distributed lock to prevent stampede
        lock_key = f"lock:{key}"
        acquired = await self.cache.set(lock_key, "1", nx=True, ex=30)

        if acquired:
            try:
                data = await fetch_fn()
                await self.cache.setex(key, ttl, json.dumps(data))
                return data
            finally:
                await self.cache.delete(lock_key)
                self.locks.pop(key, None)
        else:
            # Another process is fetching — wait and retry
            import asyncio
            for _ in range(10):
                await asyncio.sleep(0.1)
                cached = await self.cache.get(key)
                if cached:
                    return json.loads(cached)
            # Fallback to DB
            return await fetch_fn()

# --- Cache Invalidation Patterns ---

class CacheInvalidator:
    """Structured cache invalidation."""

    def __init__(self, cache):
        self.cache = cache

    async def invalidate_entity(self, entity_type: str, entity_id: str):
        """Invalidate all cache keys related to an entity."""
        # Direct key
        await self.cache.delete(f"{entity_type}:{entity_id}")

        # Invalidate lists/queries containing this entity
        # Option 1: Tag-based invalidation
        tag_key = f"tag:{entity_type}:{entity_id}"
        related_keys = await self.cache.smembers(tag_key)
        if related_keys:
            await self.cache.delete(*related_keys)
            await self.cache.delete(tag_key)

    async def cache_with_tags(self, key: str, value: Any, ttl: int,
                               tags: list[str]):
        """Store value with tags for grouped invalidation."""
        await self.cache.setex(key, ttl, json.dumps(value))
        for tag in tags:
            await self.cache.sadd(f"tag:{tag}", key)
            await self.cache.expire(f"tag:{tag}", ttl)

# --- Consistent Hashing for distributed cache ---

class ConsistentHashRing:
    """Distribute cache keys across nodes with minimal redistribution."""

    def __init__(self, nodes: list[str], replicas: int = 150):
        self.ring: dict[int, str] = {}
        self.sorted_keys: list[int] = []

        for node in nodes:
            for i in range(replicas):
                key = self._hash(f"{node}:{i}")
                self.ring[key] = node
        self.sorted_keys = sorted(self.ring.keys())

    def get_node(self, key: str) -> str:
        if not self.ring:
            raise RuntimeError("No nodes in ring")
        h = self._hash(key)
        for ring_key in self.sorted_keys:
            if h <= ring_key:
                return self.ring[ring_key]
        return self.ring[self.sorted_keys[0]]

    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)
```

Strategy selection:
| Pattern | Read latency | Write latency | Consistency | Use case |
|---------|-------------|--------------|-------------|----------|
| Cache-aside | Low (hit) | Normal | Eventual | General purpose |
| Write-through | Low | Higher | Strong | Read-heavy, consistency |
| Write-behind | Low | Very low | Eventual | Write-heavy |
| Read-through | Low | Normal | Eventual | ORM integration |'''
    ),
    (
        "system-design/rate-limiting",
        "Show rate limiting algorithms in depth: token bucket, sliding window, distributed rate limiting with Redis, and API gateway patterns.",
        '''Rate limiting algorithms for API protection:

```python
import time
import math
from dataclasses import dataclass
from typing import Optional

# --- Token Bucket Algorithm ---

class TokenBucket:
    """Smooth rate limiting with burst allowance."""

    def __init__(self, rate: float, capacity: int):
        self.rate = rate          # Tokens per second
        self.capacity = capacity  # Max burst size
        self.tokens = capacity    # Current tokens
        self.last_refill = time.monotonic()

    def allow(self, tokens: int = 1) -> bool:
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now

# --- Sliding Window Counter (Redis) ---

class SlidingWindowRedis:
    """Distributed sliding window rate limiter using Redis."""

    def __init__(self, redis_client, limit: int, window_seconds: int):
        self.redis = redis_client
        self.limit = limit
        self.window = window_seconds

    async def allow(self, key: str) -> dict:
        """Check and increment counter atomically."""
        now = time.time()
        window_start = now - self.window
        redis_key = f"ratelimit:{key}"

        # Lua script for atomic operation
        lua_script = """
        local key = KEYS[1]
        local window_start = tonumber(ARGV[1])
        local now = tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        local window = tonumber(ARGV[4])

        -- Remove expired entries
        redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

        -- Count current requests
        local count = redis.call('ZCARD', key)

        if count < limit then
            -- Add current request
            redis.call('ZADD', key, now, now .. ':' .. math.random(1000000))
            redis.call('EXPIRE', key, window)
            return {1, limit - count - 1, 0}  -- allowed, remaining, retry_after
        else
            -- Get oldest entry to calculate retry time
            local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
            local retry_after = 0
            if #oldest > 0 then
                retry_after = tonumber(oldest[2]) + window - now
            end
            return {0, 0, math.ceil(retry_after)}  -- denied, remaining, retry_after
        end
        """

        result = await self.redis.eval(
            lua_script, 1, redis_key,
            str(window_start), str(now), str(self.limit), str(self.window),
        )

        allowed, remaining, retry_after = result
        return {
            "allowed": bool(allowed),
            "remaining": int(remaining),
            "retry_after": int(retry_after),
            "limit": self.limit,
            "reset": int(now + self.window),
        }

# --- Fixed Window Counter (simple, lightweight) ---

class FixedWindowRedis:
    """Fixed time window counter — simple but has boundary burst issue."""

    async def allow(self, redis, key: str, limit: int, window: int) -> bool:
        window_key = f"ratelimit:{key}:{int(time.time()) // window}"
        count = await redis.incr(window_key)
        if count == 1:
            await redis.expire(window_key, window)
        return count <= limit

# --- Multi-tier rate limiting ---

@dataclass
class RateLimitTier:
    name: str
    requests_per_second: int
    requests_per_minute: int
    requests_per_hour: int
    burst_size: int

TIERS = {
    "free": RateLimitTier("free", rps=1, rpm=30, rph=500, burst_size=5),
    "basic": RateLimitTier("basic", rps=10, rpm=300, rph=10000, burst_size=20),
    "pro": RateLimitTier("pro", rps=100, rpm=3000, rph=100000, burst_size=200),
}

class MultiTierLimiter:
    """Apply multiple rate limit windows."""

    def __init__(self, redis_client):
        self.redis = redis_client

    async def check(self, user_id: str, tier_name: str) -> dict:
        tier = TIERS[tier_name]
        checks = [
            ("second", tier.requests_per_second, 1),
            ("minute", tier.requests_per_minute, 60),
            ("hour", tier.requests_per_hour, 3600),
        ]

        for window_name, limit, window_size in checks:
            limiter = SlidingWindowRedis(self.redis, limit, window_size)
            result = await limiter.allow(f"{user_id}:{window_name}")
            if not result["allowed"]:
                return {
                    "allowed": False,
                    "limited_by": window_name,
                    "retry_after": result["retry_after"],
                    "headers": self._build_headers(result, window_name),
                }

        return {"allowed": True}

    def _build_headers(self, result: dict, window: str) -> dict:
        return {
            "X-RateLimit-Limit": str(result["limit"]),
            "X-RateLimit-Remaining": str(result["remaining"]),
            "X-RateLimit-Reset": str(result["reset"]),
            "Retry-After": str(result["retry_after"]),
        }

# --- FastAPI middleware ---

from fastapi import Request, HTTPException

async def rate_limit_middleware(request: Request, call_next):
    user_id = get_user_id(request) or get_client_ip(request)
    tier = get_user_tier(request)

    limiter = MultiTierLimiter(request.app.state.redis)
    result = await limiter.check(user_id, tier)

    if not result["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=f"Rate limited ({result['limited_by']})",
            headers=result.get("headers", {}),
        )

    response = await call_next(request)
    return response
```

Algorithm comparison:
| Algorithm | Precision | Memory | Burst handling | Distributed |
|-----------|-----------|--------|---------------|-------------|
| Token bucket | Good | O(1) | Configurable burst | Needs sync |
| Fixed window | Low | O(1) | Boundary burst issue | Easy |
| Sliding window log | High | O(n) | Precise | Redis sorted set |
| Sliding window counter | Good | O(1) | Approximate | Redis + Lua |'''
    ),
    (
        "system-design/event-sourcing",
        "Explain event sourcing: event store design, projections, snapshots, and when to use event sourcing vs traditional CRUD.",
        '''Event sourcing — store state as sequence of events:

```python
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4
import json

# --- Events (immutable facts) ---

@dataclass(frozen=True)
class Event:
    event_id: str
    aggregate_id: str
    event_type: str
    data: dict
    metadata: dict
    version: int
    timestamp: datetime

    @staticmethod
    def create(aggregate_id: str, event_type: str, data: dict,
               version: int, metadata: dict = None) -> "Event":
        return Event(
            event_id=str(uuid4()),
            aggregate_id=aggregate_id,
            event_type=event_type,
            data=data,
            metadata=metadata or {},
            version=version,
            timestamp=datetime.now(timezone.utc),
        )

# --- Aggregate (domain object rebuilt from events) ---

class BankAccount:
    """Event-sourced bank account aggregate."""

    def __init__(self, account_id: str):
        self.account_id = account_id
        self.balance = 0
        self.status = "active"
        self.version = 0
        self._pending_events: list[Event] = []

    # --- Commands (validate + produce events) ---

    def deposit(self, amount: int, reference: str):
        if amount <= 0:
            raise ValueError("Deposit must be positive")
        if self.status != "active":
            raise ValueError("Account is not active")
        self._apply(Event.create(
            self.account_id, "MoneyDeposited",
            {"amount": amount, "reference": reference},
            self.version + 1,
        ))

    def withdraw(self, amount: int, reference: str):
        if amount <= 0:
            raise ValueError("Withdrawal must be positive")
        if amount > self.balance:
            raise ValueError(f"Insufficient funds: {self.balance} < {amount}")
        if self.status != "active":
            raise ValueError("Account is not active")
        self._apply(Event.create(
            self.account_id, "MoneyWithdrawn",
            {"amount": amount, "reference": reference},
            self.version + 1,
        ))

    def close(self, reason: str):
        if self.balance != 0:
            raise ValueError("Cannot close account with non-zero balance")
        self._apply(Event.create(
            self.account_id, "AccountClosed",
            {"reason": reason},
            self.version + 1,
        ))

    # --- Event handlers (apply state changes) ---

    def _apply(self, event: Event):
        self._handle(event)
        self._pending_events.append(event)

    def _handle(self, event: Event):
        handler = getattr(self, f"_on_{event.event_type}", None)
        if handler:
            handler(event.data)
        self.version = event.version

    def _on_MoneyDeposited(self, data: dict):
        self.balance += data["amount"]

    def _on_MoneyWithdrawn(self, data: dict):
        self.balance -= data["amount"]

    def _on_AccountClosed(self, data: dict):
        self.status = "closed"

    # --- Rebuild from event history ---

    @classmethod
    def from_events(cls, account_id: str, events: list[Event]) -> "BankAccount":
        account = cls(account_id)
        for event in events:
            account._handle(event)
        return account

    def get_pending_events(self) -> list[Event]:
        events = self._pending_events.copy()
        self._pending_events.clear()
        return events

# --- Event Store ---

class EventStore:
    """Append-only event store with optimistic concurrency."""

    def __init__(self, db):
        self.db = db

    async def append(self, aggregate_id: str, events: list[Event],
                     expected_version: int):
        """Append events with optimistic concurrency check."""
        async with self.db.transaction():
            current = await self.db.fetchval(
                "SELECT MAX(version) FROM events WHERE aggregate_id = $1",
                aggregate_id,
            )
            current = current or 0

            if current != expected_version:
                raise ConcurrencyError(
                    f"Expected version {expected_version}, "
                    f"but current is {current}"
                )

            for event in events:
                await self.db.execute("""
                    INSERT INTO events (event_id, aggregate_id, event_type,
                                       data, metadata, version, timestamp)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """, event.event_id, event.aggregate_id, event.event_type,
                    json.dumps(event.data), json.dumps(event.metadata),
                    event.version, event.timestamp)

    async def get_events(self, aggregate_id: str,
                          after_version: int = 0) -> list[Event]:
        rows = await self.db.fetch("""
            SELECT * FROM events
            WHERE aggregate_id = $1 AND version > $2
            ORDER BY version ASC
        """, aggregate_id, after_version)
        return [self._row_to_event(r) for r in rows]

# --- Projection (read model) ---

class AccountBalanceProjection:
    """Maintains denormalized read model from events."""

    def __init__(self, db):
        self.db = db

    async def handle(self, event: Event):
        if event.event_type == "MoneyDeposited":
            await self.db.execute("""
                INSERT INTO account_balances (account_id, balance, last_updated)
                VALUES ($1, $2, $3)
                ON CONFLICT (account_id)
                DO UPDATE SET balance = account_balances.balance + $2,
                             last_updated = $3
            """, event.aggregate_id, event.data["amount"], event.timestamp)

        elif event.event_type == "MoneyWithdrawn":
            await self.db.execute("""
                UPDATE account_balances
                SET balance = balance - $2, last_updated = $3
                WHERE account_id = $1
            """, event.aggregate_id, event.data["amount"], event.timestamp)

# --- Usage ---

async def transfer_money(from_id: str, to_id: str, amount: int):
    store = EventStore(db)

    # Load aggregates from events
    from_events = await store.get_events(from_id)
    from_account = BankAccount.from_events(from_id, from_events)

    to_events = await store.get_events(to_id)
    to_account = BankAccount.from_events(to_id, to_events)

    # Execute commands
    ref = str(uuid4())
    from_account.withdraw(amount, ref)
    to_account.deposit(amount, ref)

    # Persist events (optimistic concurrency)
    await store.append(from_id, from_account.get_pending_events(), from_account.version - 1)
    await store.append(to_id, to_account.get_pending_events(), to_account.version - 1)
```

When to use event sourcing:
- **Audit trail required** — financial, healthcare, compliance
- **Complex domain logic** — state transitions matter
- **Event-driven architecture** — events already central
- **Temporal queries** — "what was the balance on March 15?"

When NOT to use:
- Simple CRUD with no audit needs
- High-frequency updates to same aggregate
- Team unfamiliar with eventual consistency'''
    ),
]
