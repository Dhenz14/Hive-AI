"""
Batch P11 — System Design Patterns
Covers: rate limiting, URL shortener, distributed task queues,
real-time notifications, search engine architecture.
Target quality: >0.80 per v5 scorer.
"""

PAIRS = [
    # --- 1. Rate Limiting and Throttling ---
    (
        "system-design/rate-limiting-throttling",
        r"""Explain rate limiting and throttling strategies for distributed systems including token bucket and sliding window algorithms, distributed rate limiting with Redis, API gateway integration patterns, and client-side exponential backoff with jitter implementation.""",
        r"""# Rate Limiting and Throttling: Protecting Distributed Systems at Scale

## Why Rate Limiting Is Non-Negotiable

Every production API must enforce **rate limiting** — without it, a single misbehaving client can overwhelm your backend, degrade service for everyone, and rack up infrastructure costs. Rate limiting is also critical for **DDoS mitigation**, **fair usage enforcement**, **cost control** on downstream APIs, and **compliance** with SLAs. A **common mistake** is treating rate limiting as an afterthought; however, it should be designed into the system from day one because retrofitting it onto an existing architecture is significantly harder.

The **trade-off** is between strictness and usability: too aggressive and you frustrate legitimate users; too lenient and you leave the system vulnerable. Therefore, the best approach is a layered strategy combining multiple algorithms at different tiers.

## Core Algorithms

### Token Bucket Algorithm

The **token bucket** is the most widely used algorithm because it naturally allows short bursts while enforcing a long-term average rate. A bucket holds up to `max_tokens` tokens. Tokens are added at a fixed `refill_rate`. Each request consumes one token. If the bucket is empty, the request is rejected.

```python
import time
from dataclasses import dataclass, field
from threading import Lock
from typing import Optional


@dataclass
class TokenBucket:
    # Token bucket rate limiter with thread safety
    max_tokens: float
    refill_rate: float  # tokens per second
    _tokens: float = field(init=False)
    _last_refill: float = field(init=False)
    _lock: Lock = field(default_factory=Lock, init=False)

    def __post_init__(self) -> None:
        self._tokens = self.max_tokens
        self._last_refill = time.monotonic()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(
            self.max_tokens,
            self._tokens + elapsed * self.refill_rate,
        )
        self._last_refill = now

    def consume(self, tokens: int = 1) -> bool:
        # Attempt to consume tokens; returns True if allowed
        with self._lock:
            self._refill()
            if self._tokens >= tokens:
                self._tokens -= tokens
                return True
            return False

    def wait_time(self) -> Optional[float]:
        # Returns seconds to wait until a token is available
        with self._lock:
            self._refill()
            if self._tokens >= 1:
                return 0.0
            deficit = 1.0 - self._tokens
            return deficit / self.refill_rate


# Usage: 100 requests/minute with burst of 20
limiter = TokenBucket(max_tokens=20, refill_rate=100 / 60)
```

The token bucket is **best practice** for API rate limiting because it maps intuitively to "N requests per time window" while gracefully handling bursty traffic. The key insight is that `max_tokens` controls the burst size and `refill_rate` controls the sustained throughput.

### Sliding Window Log Algorithm

The **sliding window log** provides exact counting but uses more memory. It stores the timestamp of every request and counts how many fall within the current window.

```python
import time
from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from typing import Deque


@dataclass
class SlidingWindowLog:
    # Exact sliding window using a deque of timestamps
    max_requests: int
    window_seconds: float
    _timestamps: Deque[float] = field(default_factory=deque, init=False)
    _lock: Lock = field(default_factory=Lock, init=False)

    def allow(self) -> bool:
        with self._lock:
            now = time.monotonic()
            cutoff = now - self.window_seconds
            # Evict expired entries
            while self._timestamps and self._timestamps[0] <= cutoff:
                self._timestamps.popleft()
            if len(self._timestamps) < self.max_requests:
                self._timestamps.append(now)
                return True
            return False

    @property
    def current_count(self) -> int:
        with self._lock:
            now = time.monotonic()
            cutoff = now - self.window_seconds
            while self._timestamps and self._timestamps[0] <= cutoff:
                self._timestamps.popleft()
            return len(self._timestamps)
```

A **pitfall** with the sliding window log is memory usage: if you allow 10,000 requests per minute, you store 10,000 timestamps. For high-throughput services, prefer the **sliding window counter** hybrid that interpolates between the previous and current fixed window.

## Distributed Rate Limiting with Redis

In-process rate limiters fail when you have multiple server instances behind a load balancer, because each instance tracks its own counter independently. Therefore, you need a **centralized store** — Redis is the standard choice because of its atomic operations and sub-millisecond latency.

```python
import redis
import time
from typing import Tuple


class RedisRateLimiter:
    # Distributed rate limiter using Redis sorted sets
    # Implements sliding window log pattern

    def __init__(
        self,
        redis_client: redis.Redis,
        key_prefix: str = "ratelimit",
        max_requests: int = 100,
        window_seconds: int = 60,
    ) -> None:
        self.redis = redis_client
        self.key_prefix = key_prefix
        self.max_requests = max_requests
        self.window_seconds = window_seconds

    def _key(self, identifier: str) -> str:
        return f"{self.key_prefix}:{identifier}"

    def is_allowed(self, identifier: str) -> Tuple[bool, dict]:
        # Check if request is allowed; returns (allowed, metadata)
        key = self._key(identifier)
        now = time.time()
        cutoff = now - self.window_seconds
        pipe = self.redis.pipeline(transaction=True)
        # Remove expired entries
        pipe.zremrangebyscore(key, 0, cutoff)
        # Count remaining entries
        pipe.zcard(key)
        # Add current request timestamp with unique member
        member = f"{now}:{id(object())}"
        pipe.zadd(key, {member: now})
        # Set expiry to auto-cleanup
        pipe.expire(key, self.window_seconds + 1)
        results = pipe.execute()
        current_count = results[1]
        allowed = current_count < self.max_requests
        if not allowed:
            # Remove the entry we just added since it is denied
            self.redis.zrem(key, member)
        remaining = max(0, self.max_requests - current_count - (1 if allowed else 0))
        return allowed, {
            "limit": self.max_requests,
            "remaining": remaining,
            "reset": int(now + self.window_seconds),
            "retry_after": self.window_seconds if not allowed else None,
        }


class RedisTokenBucket:
    # Distributed token bucket using a Lua script for atomicity

    # Lua script for atomic token bucket operations in Redis
    LUA_SCRIPT = (
        "local key = KEYS[1]\n"
        "local max_tokens = tonumber(ARGV[1])\n"
        "local refill_rate = tonumber(ARGV[2])\n"
        "local now = tonumber(ARGV[3])\n"
        "local requested = tonumber(ARGV[4])\n"
        "local data = redis.call('HMGET', key, 'tokens', 'last_refill')\n"
        "local tokens = tonumber(data[1]) or max_tokens\n"
        "local last_refill = tonumber(data[2]) or now\n"
        "local elapsed = now - last_refill\n"
        "tokens = math.min(max_tokens, tokens + elapsed * refill_rate)\n"
        "local allowed = 0\n"
        "if tokens >= requested then\n"
        "    tokens = tokens - requested\n"
        "    allowed = 1\n"
        "end\n"
        "redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)\n"
        "redis.call('EXPIRE', key, math.ceil(max_tokens / refill_rate) + 1)\n"
        "return {allowed, tostring(tokens)}"
    )

    def __init__(
        self,
        redis_client: redis.Redis,
        max_tokens: float = 20,
        refill_rate: float = 1.67,
    ) -> None:
        self.redis = redis_client
        self.max_tokens = max_tokens
        self.refill_rate = refill_rate
        self._script = self.redis.register_script(self.LUA_SCRIPT)

    def consume(self, identifier: str, tokens: int = 1) -> Tuple[bool, float]:
        # Returns (allowed, remaining_tokens)
        result = self._script(
            keys=[f"tbucket:{identifier}"],
            args=[self.max_tokens, self.refill_rate, time.time(), tokens],
        )
        return bool(result[0]), float(result[1])
```

The Lua script approach is **best practice** because the entire check-and-decrement happens atomically inside Redis — no race conditions between read and write. This is critical because without atomicity, two concurrent requests could both read "1 token remaining" and both proceed.

## API Gateway Integration

Rate limiting is most effective at the **API gateway** layer (e.g., Kong, NGINX, AWS API Gateway) because it rejects traffic before it reaches your application servers. However, the **trade-off** is that gateway-level limiting is coarser — it cannot easily incorporate business logic like "premium users get higher limits."

**Best practice** is to use a two-tier approach: the gateway enforces a global safety limit (e.g., 1000 req/min per IP), and the application layer enforces per-user limits based on their subscription tier.

## Client-Side Exponential Backoff with Jitter

When a client receives a `429 Too Many Requests` response, it must not retry immediately — that would amplify the overload. **Exponential backoff with jitter** is the standard solution.

```python
import random
import time
import httpx
from typing import Optional, Any


def request_with_backoff(
    client: httpx.Client,
    method: str,
    url: str,
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    **kwargs: Any,
) -> Optional[httpx.Response]:
    # Retry with exponential backoff and full jitter on 429/5xx
    for attempt in range(max_retries + 1):
        response = client.request(method, url, **kwargs)
        if response.status_code == 429:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                delay = float(retry_after)
            else:
                # Exponential backoff: 2^attempt * base, capped
                delay = min(max_delay, base_delay * (2 ** attempt))
                # Full jitter: uniform random between 0 and delay
                delay = random.uniform(0, delay)
            time.sleep(delay)
            continue
        if response.status_code >= 500 and attempt < max_retries:
            delay = min(max_delay, base_delay * (2 ** attempt))
            delay = random.uniform(0, delay)
            time.sleep(delay)
            continue
        return response
    return None
```

The **jitter** is essential — without it, all throttled clients retry at the same instant, creating a **thundering herd** that overwhelms the server again. Full jitter (uniform random from 0 to the computed delay) provides the best load distribution. A **common mistake** is using "equal jitter" (half fixed + half random), which still concentrates retries.

## Key Takeaways

- **Token bucket** is the default choice for API rate limiting — it handles bursts naturally and is simple to implement both in-process and distributed
- **Redis with Lua scripts** provides atomic, distributed rate limiting across multiple server instances — always use atomic operations to prevent race conditions
- **Two-tier limiting** (gateway + application) provides both safety and flexibility — the gateway stops abuse, the application enforces business rules
- **Exponential backoff with full jitter** is mandatory for well-behaved clients — always respect `Retry-After` headers and randomize retry timing
- **Sliding window counters** offer a good balance between accuracy and memory — they avoid the boundary problems of fixed windows without the per-request storage of sliding window logs
- **Best practice**: return `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset` headers so clients can self-throttle before hitting the limit
"""
    ),
    # --- 2. URL Shortener System Design ---
    (
        "system-design/url-shortener",
        r"""Design a URL shortener service from scratch covering base62 encoding for short code generation, consistent hashing for horizontal scaling, read-heavy optimization with caching layers, analytics pipeline for click tracking, and cache invalidation strategies for high availability.""",
        r"""# URL Shortener System Design: From Encoding to Analytics at Scale

## Problem Analysis and Scale Estimation

A URL shortener maps long URLs to short codes (e.g., `https://sho.rt/a3Xb92`) and redirects users to the original URL. While the concept is simple, building one at scale (think Bitly or TinyURL) involves interesting **trade-offs** across encoding, storage, caching, and analytics.

**Scale assumptions** for a mid-to-large service: 100M new URLs per month (write), 10B redirects per month (read), giving a **100:1 read-to-write ratio**. This is an extremely **read-heavy** workload, which fundamentally drives the architecture. Each shortened URL record is roughly 500 bytes (short code + long URL + metadata), so storage grows at ~50GB/month.

## Short Code Generation with Base62 Encoding

The core question is: how do we generate a short, unique, URL-safe string for each URL? **Base62 encoding** (a-z, A-Z, 0-9) is the standard approach because all 62 characters are URL-safe without percent-encoding.

```python
import hashlib
from typing import Optional

# Base62 character set — URL safe without encoding
BASE62_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE = len(BASE62_CHARS)  # 62


def int_to_base62(num: int) -> str:
    # Convert a non-negative integer to a base62 string
    if num == 0:
        return BASE62_CHARS[0]
    result: list[str] = []
    while num > 0:
        result.append(BASE62_CHARS[num % BASE])
        num //= BASE
    return "".join(reversed(result))


def base62_to_int(encoded: str) -> int:
    # Decode a base62 string back to an integer
    result = 0
    for char in encoded:
        result = result * BASE + BASE62_CHARS.index(char)
    return result


class ShortCodeGenerator:
    # Generates unique short codes using a distributed counter
    # approach with range-based ID allocation

    def __init__(
        self,
        counter_service: "CounterService",
        code_length: int = 7,
    ) -> None:
        self.counter = counter_service
        self.code_length = code_length
        # 7 chars in base62 = 62^7 = 3.5 trillion combinations
        self.max_id = BASE ** code_length

    def generate(self, long_url: str) -> str:
        # Generate a unique short code for the given URL
        unique_id = self.counter.next_id()
        if unique_id >= self.max_id:
            raise OverflowError("Short code space exhausted")
        code = int_to_base62(unique_id)
        # Pad to fixed length for consistency
        return code.zfill(self.code_length)

    def generate_from_hash(
        self, long_url: str, attempt: int = 0
    ) -> str:
        # Alternative: hash-based generation with collision handling
        data = f"{long_url}:{attempt}".encode()
        digest = hashlib.md5(data).hexdigest()
        num = int(digest[:12], 16) % self.max_id
        return int_to_base62(num).zfill(self.code_length)
```

A 7-character base62 code gives 62^7 = **3.5 trillion** unique URLs — more than sufficient for any realistic scale. The **trade-off** between counter-based and hash-based generation is important: counters guarantee uniqueness but require coordination; hashes are stateless but risk collisions. **Best practice** is to use a **range-based counter** (each server pre-allocates a block of IDs, e.g., 1000 at a time) to avoid per-request coordination while guaranteeing uniqueness.

A **common mistake** is using sequential IDs directly, which leaks information (competitors can estimate your traffic volume). Therefore, you can apply a simple bijective mapping or XOR with a secret to obscure the sequence.

## Consistent Hashing for Horizontal Scaling

As the service grows, you need to partition data across multiple database nodes. **Consistent hashing** minimizes data movement when nodes are added or removed.

```python
import bisect
import hashlib
from dataclasses import dataclass, field
from typing import Generic, TypeVar, Optional

T = TypeVar("T")


@dataclass
class ConsistentHashRing(Generic[T]):
    # Consistent hash ring with virtual nodes for uniform distribution
    num_virtual_nodes: int = 150
    _ring: dict[int, T] = field(default_factory=dict, init=False)
    _sorted_keys: list[int] = field(default_factory=list, init=False)

    def _hash(self, key: str) -> int:
        digest = hashlib.md5(key.encode()).hexdigest()
        return int(digest, 16)

    def add_node(self, node: T) -> None:
        # Add a node with virtual nodes for better distribution
        for i in range(self.num_virtual_nodes):
            virtual_key = f"{node}:vn{i}"
            hash_val = self._hash(virtual_key)
            self._ring[hash_val] = node
            bisect.insort(self._sorted_keys, hash_val)

    def remove_node(self, node: T) -> None:
        # Remove a node and all its virtual nodes
        for i in range(self.num_virtual_nodes):
            virtual_key = f"{node}:vn{i}"
            hash_val = self._hash(virtual_key)
            if hash_val in self._ring:
                del self._ring[hash_val]
                self._sorted_keys.remove(hash_val)

    def get_node(self, key: str) -> Optional[T]:
        # Find the node responsible for a given key
        if not self._ring:
            return None
        hash_val = self._hash(key)
        idx = bisect.bisect_right(self._sorted_keys, hash_val)
        if idx == len(self._sorted_keys):
            idx = 0  # Wrap around the ring
        return self._ring[self._sorted_keys[idx]]


# Partition URL data across database shards
ring: ConsistentHashRing[str] = ConsistentHashRing(num_virtual_nodes=150)
for shard in ["db-shard-1", "db-shard-2", "db-shard-3", "db-shard-4"]:
    ring.add_node(shard)

target_shard = ring.get_node("a3Xb92")  # Deterministic shard lookup
```

Using **150 virtual nodes per physical node** is **best practice** — it ensures a roughly even distribution of keys (standard deviation drops below 5%). Without virtual nodes, consistent hashing can produce severely unbalanced loads.

## Read-Heavy Optimization with Caching

With a 100:1 read-to-write ratio, caching is the single most impactful optimization. The **hot URL problem** is real — a small fraction of URLs (trending content, viral links) generates the vast majority of redirects.

```python
import redis
import json
import time
from dataclasses import dataclass
from typing import Optional


@dataclass
class CachedURLService:
    # Multi-layer caching for URL resolution
    redis_client: redis.Redis
    db: "DatabaseClient"
    cache_ttl: int = 3600  # 1 hour default
    hot_url_ttl: int = 86400  # 24 hours for popular URLs
    hot_threshold: int = 100  # hits before promoting to hot

    def resolve(self, short_code: str) -> Optional[str]:
        # Resolve short code to long URL with caching layers
        cache_key = f"url:{short_code}"
        # Layer 1: Redis cache lookup
        cached = self.redis_client.get(cache_key)
        if cached:
            self._increment_hits(short_code)
            return cached.decode()
        # Layer 2: Database lookup
        record = self.db.get_url(short_code)
        if record is None:
            # Cache negative results to prevent DB hammering
            self.redis_client.setex(
                f"url:neg:{short_code}", 300, "1"
            )
            return None
        # Populate cache
        self.redis_client.setex(
            cache_key, self.cache_ttl, record.long_url
        )
        self._increment_hits(short_code)
        return record.long_url

    def _increment_hits(self, short_code: str) -> None:
        # Track hit count and promote hot URLs to longer TTL
        hits_key = f"hits:{short_code}"
        hits = self.redis_client.incr(hits_key)
        self.redis_client.expire(hits_key, self.hot_url_ttl)
        if hits == self.hot_threshold:
            # Promote to hot tier with extended TTL
            cache_key = f"url:{short_code}"
            self.redis_client.expire(cache_key, self.hot_url_ttl)

    def create(self, short_code: str, long_url: str) -> None:
        # Write-through: DB first, then cache
        self.db.insert_url(short_code, long_url)
        cache_key = f"url:{short_code}"
        self.redis_client.setex(cache_key, self.cache_ttl, long_url)
        # Invalidate any negative cache
        self.redis_client.delete(f"url:neg:{short_code}")
```

**Negative caching** (caching "not found" results) is critical — without it, invalid or expired short codes trigger a database query on every hit, which could be a DDoS vector. However, keep negative cache TTLs short (5 minutes) to avoid stale negatives after a URL is created.

## Analytics Pipeline for Click Tracking

Every redirect is a data point: timestamp, referrer, country, device, browser. Processing this synchronously would add latency to redirects, therefore the analytics path must be **fully asynchronous**.

The architecture follows the pattern: redirect handler emits an event to Kafka, a stream processor aggregates the events, and results are stored in a time-series or OLAP database for dashboards.

```python
import json
import time
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class ClickEvent:
    # Analytics event emitted on every redirect
    short_code: str
    timestamp: float
    ip_address: str
    user_agent: str
    referrer: Optional[str]
    country: Optional[str] = None
    device_type: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self))


class AnalyticsProducer:
    # Async analytics event publisher using Kafka
    def __init__(self, kafka_producer: "KafkaProducer", topic: str = "click-events") -> None:
        self.producer = kafka_producer
        self.topic = topic

    def record_click(self, event: ClickEvent) -> None:
        # Fire-and-forget to Kafka — does not block the redirect
        self.producer.send(
            self.topic,
            key=event.short_code.encode(),
            value=event.to_json().encode(),
        )

    def flush(self) -> None:
        self.producer.flush()
```

Using the short code as the **Kafka partition key** ensures all clicks for the same URL land in the same partition, enabling efficient per-URL aggregation downstream. This is a deliberate **trade-off**: it may cause hot partitions for viral URLs, but it simplifies the consumer logic significantly.

## Key Takeaways

- **Base62 with range-based counters** gives guaranteed uniqueness without per-request coordination — 7 characters provide 3.5 trillion codes
- **Consistent hashing with virtual nodes** enables horizontal scaling with minimal data movement — use 100-200 virtual nodes per physical node for even distribution
- **Multi-layer caching** (local + Redis + negative caching) is the primary optimization for read-heavy workloads — promote hot URLs to longer TTLs automatically
- **Write-through caching** on URL creation avoids cache inconsistency without complex invalidation — the redirect path always checks cache first
- **Asynchronous analytics** via Kafka decouples click tracking from the redirect hot path — partition by short code for efficient per-URL aggregation
- A **pitfall** is neglecting to cache negative results — invalid short codes can become an accidental or intentional DDoS amplifier hitting your database
"""
    ),
    # --- 3. Distributed Task Queue ---
    (
        "system-design/distributed-task-queue",
        r"""Design a distributed task queue system covering priority-based scheduling with multiple priority levels, dead letter queue handling for failed tasks, exactly-once processing semantics, worker autoscaling based on queue depth, and monitoring with observability best practices.""",
        r"""# Distributed Task Queue: Reliable Async Processing at Scale

## Why Distributed Task Queues Matter

Nearly every production system has work that should not happen in the request-response cycle: sending emails, processing images, running ML inference, generating reports, syncing data. A **distributed task queue** decouples producers (who submit work) from workers (who execute it), providing **resilience**, **scalability**, and **load leveling**.

The **common mistake** is building a naive queue on top of a relational database with a `status` column and `SELECT ... FOR UPDATE` polling. This approach works for small scale but creates lock contention, polling overhead, and lacks proper failure handling. Therefore, purpose-built queue systems (Celery, Temporal, AWS SQS, or custom solutions on Redis/Kafka) are **best practice** for any non-trivial workload.

## Priority-Based Scheduling

Not all tasks are equal. A password reset email is more urgent than a weekly analytics rollup. **Priority queues** ensure high-priority work is processed first, however implementing them correctly in a distributed setting requires careful design.

```python
import enum
import heapq
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional
from threading import Lock


class Priority(enum.IntEnum):
    # Lower numeric value = higher priority
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    BULK = 4


@dataclass(order=True)
class Task:
    # Sortable task with priority and timestamp for FIFO within priority
    priority: int
    submitted_at: float = field(compare=True)
    task_id: str = field(default_factory=lambda: str(uuid.uuid4()), compare=False)
    func_name: str = field(default="", compare=False)
    args: tuple = field(default_factory=tuple, compare=False)
    kwargs: dict = field(default_factory=dict, compare=False)
    max_retries: int = field(default=3, compare=False)
    retry_count: int = field(default=0, compare=False)
    timeout_seconds: float = field(default=300.0, compare=False)


class PriorityTaskQueue:
    # In-memory priority queue; in production use Redis sorted sets
    # or separate queues per priority level

    def __init__(self) -> None:
        self._heap: list[Task] = []
        self._lock = Lock()
        self._task_count = 0

    def enqueue(self, task: Task) -> None:
        with self._lock:
            heapq.heappush(self._heap, task)
            self._task_count += 1

    def dequeue(self) -> Optional[Task]:
        with self._lock:
            if self._heap:
                self._task_count -= 1
                return heapq.heappop(self._heap)
            return None

    @property
    def depth(self) -> int:
        return self._task_count

    def depth_by_priority(self) -> dict[str, int]:
        with self._lock:
            counts: dict[str, int] = {}
            for task in self._heap:
                name = Priority(task.priority).name
                counts[name] = counts.get(name, 0) + 1
            return counts
```

In production, the **best practice** is to use **separate Redis lists per priority level** rather than a single sorted set. Workers check queues in priority order using `BRPOP` across multiple lists — Redis handles this atomically with `BRPOP queue:critical queue:high queue:normal queue:low 5`. This avoids the O(log n) insertion cost of sorted sets while providing strict priority ordering.

A **pitfall** is **starvation**: if CRITICAL tasks arrive continuously, LOW tasks never execute. The solution is a **weighted fair scheduling** approach where workers occasionally pull from lower-priority queues even when higher-priority work exists.

## Dead Letter Queue (DLQ) Handling

Tasks fail — dependencies go down, input data is malformed, bugs exist. A robust queue system must handle failures gracefully rather than silently dropping work.

```python
import json
import time
import traceback
from dataclasses import dataclass, asdict
from typing import Optional
import redis


@dataclass
class FailureRecord:
    # Complete context about a task failure
    task_id: str
    func_name: str
    original_args: str
    error_type: str
    error_message: str
    traceback: str
    retry_count: int
    max_retries: int
    failed_at: float
    worker_id: str


class DeadLetterQueue:
    # Manages permanently failed tasks for inspection and replay

    def __init__(self, redis_client: redis.Redis, namespace: str = "dlq") -> None:
        self.redis = redis_client
        self.namespace = namespace

    def send_to_dlq(self, record: FailureRecord) -> None:
        # Store failed task with full context for debugging
        key = f"{self.namespace}:{record.task_id}"
        self.redis.hset(key, mapping={
            "task_id": record.task_id,
            "func_name": record.func_name,
            "original_args": record.original_args,
            "error_type": record.error_type,
            "error_message": record.error_message,
            "traceback": record.traceback,
            "retry_count": str(record.retry_count),
            "max_retries": str(record.max_retries),
            "failed_at": str(record.failed_at),
            "worker_id": record.worker_id,
        })
        # Add to the DLQ index sorted by failure time
        self.redis.zadd(
            f"{self.namespace}:index",
            {record.task_id: record.failed_at},
        )
        # Increment error counters for monitoring
        self.redis.incr(f"{self.namespace}:count:{record.func_name}")

    def list_failed(
        self, offset: int = 0, limit: int = 50
    ) -> list[dict]:
        # List failed tasks, newest first
        task_ids = self.redis.zrevrange(
            f"{self.namespace}:index", offset, offset + limit - 1
        )
        results = []
        for tid in task_ids:
            key = f"{self.namespace}:{tid.decode()}"
            data = self.redis.hgetall(key)
            results.append({
                k.decode(): v.decode() for k, v in data.items()
            })
        return results

    def replay(self, task_id: str, queue: "TaskQueue") -> bool:
        # Re-enqueue a failed task for another attempt
        key = f"{self.namespace}:{task_id}"
        data = self.redis.hgetall(key)
        if not data:
            return False
        # Re-enqueue with reset retry count
        task = Task(
            priority=Priority.HIGH.value,
            submitted_at=time.time(),
            task_id=task_id,
            func_name=data[b"func_name"].decode(),
            args=json.loads(data[b"original_args"].decode()),
            max_retries=3,
            retry_count=0,
        )
        queue.enqueue(task)
        # Remove from DLQ
        self.redis.delete(key)
        self.redis.zrem(f"{self.namespace}:index", task_id)
        return True
```

The retry strategy before DLQ admission should use **exponential backoff**: delays of 1s, 4s, 16s, 64s for retries 1-4. This prevents a failing downstream service from being hammered by immediate retries. After `max_retries` is exhausted, the task moves to the DLQ where an operator can inspect it, fix the underlying issue, and replay it.

## Exactly-Once Processing Semantics

True exactly-once processing in a distributed system is notoriously difficult. The practical approach is **at-least-once delivery** combined with **idempotent task execution**.

```python
import hashlib
import redis
from typing import Any, Callable


class IdempotencyGuard:
    # Ensures a task produces its side effects exactly once
    # using a deduplication key stored in Redis

    def __init__(self, redis_client: redis.Redis, ttl: int = 86400) -> None:
        self.redis = redis_client
        self.ttl = ttl

    def compute_key(self, task_id: str, func_name: str) -> str:
        return f"idempotent:{func_name}:{task_id}"

    def execute_once(
        self,
        task_id: str,
        func_name: str,
        func: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        # Execute function only if not already completed
        key = self.compute_key(task_id, func_name)
        # SET NX returns True only if key did not exist
        acquired = self.redis.set(key, "processing", nx=True, ex=self.ttl)
        if not acquired:
            status = self.redis.get(key)
            if status and status.decode() == "completed":
                return None  # Already done — skip
            # Status is 'processing' — another worker may be executing
            # In production, add a lock timeout check here
            return None
        try:
            result = func(*args, **kwargs)
            self.redis.set(key, "completed", ex=self.ttl)
            return result
        except Exception:
            # Allow retry by deleting the key
            self.redis.delete(key)
            raise
```

The **trade-off** here is between correctness and performance: the idempotency check adds a Redis round-trip per task. However, this is almost always worth it because duplicate task execution can cause double charges, duplicate notifications, or corrupted data. A **common mistake** is setting the idempotency TTL too short — if a task is retried after the key expires, it will execute again.

## Worker Autoscaling

Static worker pools waste resources during low-traffic periods and bottleneck during spikes. **Autoscaling** based on queue depth provides elastic capacity.

```python
import time
from dataclasses import dataclass
from typing import Protocol


class ScalingBackend(Protocol):
    def current_worker_count(self) -> int: ...
    def scale_to(self, count: int) -> None: ...


@dataclass
class AutoScaler:
    # Queue-depth-based autoscaler with cooldown and dampening
    queue: "TaskQueue"
    backend: ScalingBackend
    min_workers: int = 2
    max_workers: int = 50
    tasks_per_worker: int = 10  # Target tasks per worker
    scale_up_cooldown: float = 60.0  # seconds
    scale_down_cooldown: float = 300.0  # slower scale-down
    _last_scale_up: float = 0.0
    _last_scale_down: float = 0.0

    def evaluate(self) -> None:
        # Evaluate and adjust worker count based on queue depth
        depth = self.queue.depth
        current = self.backend.current_worker_count()
        desired = max(
            self.min_workers,
            min(self.max_workers, depth // self.tasks_per_worker + 1),
        )
        now = time.time()
        if desired > current:
            if now - self._last_scale_up < self.scale_up_cooldown:
                return  # Cooldown not elapsed
            # Scale up aggressively but cap at 2x current
            target = min(desired, current * 2)
            self.backend.scale_to(target)
            self._last_scale_up = now
        elif desired < current:
            if now - self._last_scale_down < self.scale_down_cooldown:
                return  # Wait longer before scaling down
            # Scale down conservatively — remove 1 worker at a time
            self.backend.scale_to(current - 1)
            self._last_scale_down = now
```

**Best practice** is asymmetric scaling: scale up aggressively (react to load spikes quickly) but scale down conservatively (avoid flapping). The longer `scale_down_cooldown` prevents the system from thrashing between adding and removing workers during variable load.

## Monitoring and Observability

### Key Metrics to Track

A task queue without monitoring is a black hole. You must track queue depth (overall and per priority), task latency (time from enqueue to completion), failure rate by task type, DLQ size trends, and worker utilization.

```python
import time
from dataclasses import dataclass
from typing import Dict
from prometheus_client import Counter, Histogram, Gauge


# Prometheus metrics for task queue observability
TASKS_ENQUEUED = Counter(
    "task_queue_enqueued_total",
    "Total tasks enqueued",
    ["priority", "func_name"],
)
TASKS_COMPLETED = Counter(
    "task_queue_completed_total",
    "Total tasks completed",
    ["func_name", "status"],  # status: success, failure, timeout
)
TASK_DURATION = Histogram(
    "task_queue_duration_seconds",
    "Task execution duration",
    ["func_name"],
    buckets=[0.1, 0.5, 1, 5, 10, 30, 60, 120, 300],
)
QUEUE_DEPTH = Gauge(
    "task_queue_depth",
    "Current queue depth",
    ["priority"],
)
DLQ_SIZE = Gauge(
    "task_queue_dlq_size",
    "Dead letter queue size",
)
WORKER_COUNT = Gauge(
    "task_queue_workers",
    "Current active worker count",
)
```

**Best practice** is to set alerts on: DLQ size increasing (indicates a systematic failure), queue depth growing faster than it drains (workers cannot keep up), and p99 task latency exceeding SLA thresholds. These three signals catch most operational issues before they cascade.

## Key Takeaways

- **Separate queues per priority** with `BRPOP` across multiple Redis lists provide strict priority ordering without sorted set overhead — add weighted scheduling to prevent starvation
- **Dead letter queues** with full failure context (traceback, args, worker ID) enable post-mortem debugging and task replay — never silently drop failed tasks
- **Exactly-once semantics** are achieved practically through at-least-once delivery plus idempotent execution with Redis-backed deduplication keys
- **Asymmetric autoscaling** (fast scale-up, slow scale-down) prevents both capacity shortfalls and resource waste — always enforce min/max bounds
- **Prometheus metrics** on queue depth, task latency, failure rates, and DLQ size provide the observability foundation — alert on trends, not just thresholds
- A **pitfall** is using a relational database as a queue — `SELECT ... FOR UPDATE` creates lock contention that degrades performance at exactly the moment you need more throughput
"""
    ),
    # --- 4. Real-Time Notification System ---
    (
        "system-design/realtime-notification-system",
        r"""Design a real-time notification system covering WebSocket connection management with heartbeats and reconnection, pub/sub fanout patterns for multi-device delivery, push notification integration with APNs and FCM, user presence detection, and delivery guarantee mechanisms including at-least-once semantics.""",
        r"""# Real-Time Notification System: WebSockets, Pub/Sub, and Delivery Guarantees

## Architecture Overview

A real-time notification system must deliver messages to users within seconds across **multiple channels**: in-app (WebSocket), mobile push (APNs/FCM), email, and SMS. The fundamental challenge is maintaining persistent connections to millions of concurrent users while guaranteeing that no notification is lost, even when users are offline or switching between devices.

The **trade-off** at the heart of this design is between **latency** and **reliability**. Fire-and-forget WebSocket pushes are fast but unreliable; store-then-deliver approaches guarantee delivery but add latency. Therefore, the **best practice** is a hybrid: push immediately via WebSocket if the user is online, and simultaneously persist the notification for retrieval when they reconnect.

## WebSocket Connection Management

Managing millions of persistent WebSocket connections requires careful engineering around **heartbeats**, **reconnection**, and **connection state tracking**.

```python
import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional, Dict, Set
from enum import Enum

import websockets
from websockets.server import WebSocketServerProtocol


class ConnectionState(Enum):
    CONNECTED = "connected"
    IDLE = "idle"
    DISCONNECTING = "disconnecting"


@dataclass
class ClientConnection:
    # Represents a single WebSocket connection from a user device
    user_id: str
    device_id: str
    ws: WebSocketServerProtocol
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    state: ConnectionState = ConnectionState.CONNECTED
    missed_heartbeats: int = 0
    connection_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class ConnectionManager:
    # Manages WebSocket connections with heartbeat monitoring
    # In production, each server instance manages its local connections
    # and registers them in Redis for cross-server routing

    def __init__(
        self,
        heartbeat_interval: float = 30.0,
        max_missed_heartbeats: int = 3,
    ) -> None:
        self.heartbeat_interval = heartbeat_interval
        self.max_missed = max_missed_heartbeats
        # user_id -> {device_id -> ClientConnection}
        self._connections: Dict[str, Dict[str, ClientConnection]] = {}
        self._total_connections = 0

    async def register(
        self, user_id: str, device_id: str, ws: WebSocketServerProtocol
    ) -> ClientConnection:
        # Register a new WebSocket connection
        conn = ClientConnection(user_id=user_id, device_id=device_id, ws=ws)
        if user_id not in self._connections:
            self._connections[user_id] = {}
        # Close existing connection from same device (replace)
        if device_id in self._connections[user_id]:
            old = self._connections[user_id][device_id]
            await old.ws.close(1000, "Replaced by new connection")
        self._connections[user_id][device_id] = conn
        self._total_connections += 1
        return conn

    async def unregister(self, user_id: str, device_id: str) -> None:
        if user_id in self._connections:
            if device_id in self._connections[user_id]:
                del self._connections[user_id][device_id]
                self._total_connections -= 1
            if not self._connections[user_id]:
                del self._connections[user_id]

    def get_connections(self, user_id: str) -> list[ClientConnection]:
        # Get all active connections for a user (multi-device)
        if user_id not in self._connections:
            return []
        return list(self._connections[user_id].values())

    def is_online(self, user_id: str) -> bool:
        return user_id in self._connections and len(self._connections[user_id]) > 0

    async def send_to_user(
        self, user_id: str, message: dict
    ) -> int:
        # Send message to all connected devices; returns delivery count
        connections = self.get_connections(user_id)
        delivered = 0
        payload = json.dumps(message)
        for conn in connections:
            try:
                await conn.ws.send(payload)
                delivered += 1
            except websockets.ConnectionClosed:
                await self.unregister(user_id, conn.device_id)
        return delivered

    async def heartbeat_loop(self) -> None:
        # Runs continuously to detect stale connections
        while True:
            await asyncio.sleep(self.heartbeat_interval)
            now = time.time()
            stale: list[tuple[str, str]] = []
            for user_id, devices in self._connections.items():
                for device_id, conn in devices.items():
                    elapsed = now - conn.last_heartbeat
                    if elapsed > self.heartbeat_interval * self.max_missed:
                        stale.append((user_id, device_id))
            for user_id, device_id in stale:
                conn = self._connections.get(user_id, {}).get(device_id)
                if conn:
                    await conn.ws.close(1001, "Heartbeat timeout")
                    await self.unregister(user_id, device_id)
```

A **common mistake** is relying solely on TCP keepalive for connection health detection. TCP keepalive intervals are typically 2 hours by default, which is far too slow. Application-level heartbeats (ping/pong every 30 seconds) detect dead connections within 90 seconds, which is critical for accurate **presence detection**.

## Pub/Sub Fanout for Multi-Server Delivery

In production, you run multiple WebSocket server instances behind a load balancer. A user's connection lands on one specific server, but the notification producer does not know which server. Therefore, you need a **pub/sub layer** that fans out notifications to all servers, and each server delivers only to its locally connected users.

```python
import redis.asyncio as aioredis
import json
from typing import Callable, Awaitable


class RedisPubSubFanout:
    # Cross-server notification fanout using Redis pub/sub
    # Each WebSocket server subscribes and filters locally

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        channel_prefix: str = "notifications",
    ) -> None:
        self.redis_url = redis_url
        self.channel_prefix = channel_prefix
        self._redis: aioredis.Redis | None = None
        self._pubsub: aioredis.client.PubSub | None = None

    async def connect(self) -> None:
        self._redis = aioredis.from_url(self.redis_url)
        self._pubsub = self._redis.pubsub()

    async def publish(self, user_id: str, notification: dict) -> int:
        # Publish notification to user-specific channel
        channel = f"{self.channel_prefix}:{user_id}"
        payload = json.dumps(notification)
        if self._redis is None:
            raise RuntimeError("Not connected")
        return await self._redis.publish(channel, payload)

    async def subscribe_user(
        self,
        user_id: str,
        handler: Callable[[dict], Awaitable[None]],
    ) -> None:
        # Subscribe to notifications for a specific user
        channel = f"{self.channel_prefix}:{user_id}"
        if self._pubsub is None:
            raise RuntimeError("Not connected")
        await self._pubsub.subscribe(channel)

    async def listen(
        self,
        handler: Callable[[str, dict], Awaitable[None]],
    ) -> None:
        # Listen for messages and dispatch to handler
        if self._pubsub is None:
            raise RuntimeError("Not connected")
        async for message in self._pubsub.listen():
            if message["type"] == "message":
                channel = message["channel"].decode()
                user_id = channel.split(":")[-1]
                data = json.loads(message["data"].decode())
                await handler(user_id, data)
```

The **trade-off** with Redis pub/sub is that messages are fire-and-forget — if no subscriber is listening when a message is published, it is lost. This is acceptable because we combine pub/sub with persistent storage (see delivery guarantees below). For higher throughput scenarios, consider **Redis Streams** or **Kafka** which provide message persistence and consumer groups.

## Push Notification Integration

When a user is offline (no active WebSocket connection), notifications must be delivered via platform push services — **APNs** for iOS and **FCM** for Android.

```python
import httpx
import jwt
import time
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class PushPlatform(Enum):
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"


@dataclass
class PushToken:
    user_id: str
    device_id: str
    platform: PushPlatform
    token: str
    created_at: float


class PushNotificationService:
    # Unified push notification sender for iOS, Android, and Web

    def __init__(
        self,
        fcm_server_key: str,
        apns_key_path: str,
        apns_key_id: str,
        apns_team_id: str,
        apns_bundle_id: str,
    ) -> None:
        self.fcm_key = fcm_server_key
        self.apns_key_path = apns_key_path
        self.apns_key_id = apns_key_id
        self.apns_team_id = apns_team_id
        self.apns_bundle_id = apns_bundle_id
        self._http = httpx.AsyncClient(timeout=10.0)

    async def send(
        self, token: PushToken, title: str, body: str,
        data: Optional[dict] = None,
    ) -> bool:
        if token.platform == PushPlatform.ANDROID:
            return await self._send_fcm(token.token, title, body, data)
        elif token.platform == PushPlatform.IOS:
            return await self._send_apns(token.token, title, body, data)
        return False

    async def _send_fcm(
        self, device_token: str, title: str, body: str,
        data: Optional[dict] = None,
    ) -> bool:
        # Firebase Cloud Messaging HTTP v1 API
        payload = {
            "message": {
                "token": device_token,
                "notification": {"title": title, "body": body},
                "data": data or {},
                "android": {
                    "priority": "high",
                    "notification": {"channel_id": "default"},
                },
            }
        }
        resp = await self._http.post(
            "https://fcm.googleapis.com/v1/projects/myproject/messages:send",
            json=payload,
            headers={"Authorization": f"Bearer {self.fcm_key}"},
        )
        return resp.status_code == 200

    async def _send_apns(
        self, device_token: str, title: str, body: str,
        data: Optional[dict] = None,
    ) -> bool:
        # Apple Push Notification service with JWT auth
        token = self._generate_apns_jwt()
        payload = {
            "aps": {
                "alert": {"title": title, "body": body},
                "sound": "default",
                "badge": 1,
            },
        }
        if data:
            payload.update(data)
        resp = await self._http.post(
            f"https://api.push.apple.com/3/device/{device_token}",
            json=payload,
            headers={
                "Authorization": f"bearer {token}",
                "apns-topic": self.apns_bundle_id,
                "apns-push-type": "alert",
                "apns-priority": "10",
            },
        )
        return resp.status_code == 200

    def _generate_apns_jwt(self) -> str:
        with open(self.apns_key_path, "r") as f:
            private_key = f.read()
        payload = {
            "iss": self.apns_team_id,
            "iat": int(time.time()),
        }
        return jwt.encode(
            payload, private_key,
            algorithm="ES256",
            headers={"kid": self.apns_key_id},
        )
```

A **pitfall** with push notifications is **token invalidation** — when a user uninstalls the app or revokes notification permissions, the push token becomes invalid. Both APNs and FCM return specific error codes for invalid tokens. **Best practice** is to handle these errors and remove stale tokens from your database immediately to avoid wasting API quota and triggering rate limits from the push providers.

## Presence Detection

**Presence detection** (knowing who is currently online) serves two purposes: routing decisions (WebSocket vs push) and user-facing features ("Dan is typing...").

```python
import time
import redis


class PresenceService:
    # Tracks user online/offline status using Redis with TTL-based expiry

    def __init__(
        self,
        redis_client: redis.Redis,
        presence_ttl: int = 60,
    ) -> None:
        self.redis = redis_client
        self.ttl = presence_ttl

    def heartbeat(self, user_id: str, device_id: str) -> None:
        # Called on every WebSocket heartbeat to maintain presence
        key = f"presence:{user_id}"
        self.redis.hset(key, device_id, str(time.time()))
        self.redis.expire(key, self.ttl)

    def is_online(self, user_id: str) -> bool:
        return self.redis.exists(f"presence:{user_id}") > 0

    def get_online_devices(self, user_id: str) -> list[str]:
        key = f"presence:{user_id}"
        devices = self.redis.hgetall(key)
        return [d.decode() for d in devices.keys()]

    def remove(self, user_id: str, device_id: str) -> None:
        key = f"presence:{user_id}"
        self.redis.hdel(key, device_id)
        # Clean up empty hash
        if self.redis.hlen(key) == 0:
            self.redis.delete(key)

    def bulk_check(self, user_ids: list[str]) -> dict[str, bool]:
        # Efficiently check presence for a batch of users
        pipe = self.redis.pipeline(transaction=False)
        for uid in user_ids:
            pipe.exists(f"presence:{uid}")
        results = pipe.execute()
        return {uid: bool(r) for uid, r in zip(user_ids, results)}
```

The **TTL-based approach** is elegant: if a user's WebSocket connection drops without a clean disconnect (network failure, app crash), their presence key automatically expires after `presence_ttl` seconds. No explicit cleanup is needed. However, the **trade-off** is that presence information can be stale by up to `presence_ttl` seconds — set it to match your heartbeat interval for the best accuracy.

## Delivery Guarantees

The notification delivery pipeline must guarantee **at-least-once delivery**: every notification must eventually reach the user, even if they are offline for hours.

```python
import json
import time
import uuid
import redis
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class DeliveryStatus(Enum):
    PENDING = "pending"
    DELIVERED_WS = "delivered_ws"
    DELIVERED_PUSH = "delivered_push"
    READ = "read"


@dataclass
class Notification:
    notification_id: str
    user_id: str
    title: str
    body: str
    data: dict = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    status: DeliveryStatus = DeliveryStatus.PENDING


class NotificationStore:
    # Persistent notification storage with delivery tracking

    def __init__(self, redis_client: redis.Redis) -> None:
        self.redis = redis_client

    def store(self, notification: Notification) -> None:
        # Store notification and add to user unread set
        key = f"notif:{notification.notification_id}"
        self.redis.hset(key, mapping={
            "id": notification.notification_id,
            "user_id": notification.user_id,
            "title": notification.title,
            "body": notification.body,
            "data": json.dumps(notification.data),
            "created_at": str(notification.created_at),
            "status": notification.status.value,
        })
        self.redis.expire(key, 30 * 86400)  # 30 days retention
        # Add to user unread sorted set (sorted by time)
        self.redis.zadd(
            f"unread:{notification.user_id}",
            {notification.notification_id: notification.created_at},
        )

    def mark_delivered(
        self, notification_id: str, channel: str
    ) -> None:
        key = f"notif:{notification_id}"
        self.redis.hset(key, "status", f"delivered_{channel}")

    def get_unread(
        self, user_id: str, limit: int = 50
    ) -> list[dict]:
        # Fetch unread notifications for a user
        ids = self.redis.zrevrange(f"unread:{user_id}", 0, limit - 1)
        results = []
        for nid in ids:
            data = self.redis.hgetall(f"notif:{nid.decode()}")
            if data:
                results.append({
                    k.decode(): v.decode() for k, v in data.items()
                })
        return results

    def mark_read(self, user_id: str, notification_id: str) -> None:
        self.redis.hset(f"notif:{notification_id}", "status", "read")
        self.redis.zrem(f"unread:{user_id}", notification_id)
```

The delivery flow is: (1) persist notification to store, (2) check presence, (3) if online push via WebSocket, (4) if offline send push notification, (5) on WebSocket reconnection deliver all unread notifications. This ensures that even if the WebSocket push fails silently, the notification is retrievable on reconnect.

## Key Takeaways

- **WebSocket heartbeats** at 30-second intervals detect dead connections within 90 seconds — never rely on TCP keepalive alone for presence accuracy
- **Redis pub/sub** provides efficient cross-server fanout, but must be combined with persistent storage because pub/sub messages are ephemeral
- **Persist-then-push** is the **best practice** delivery pattern: store the notification first, attempt real-time delivery second, and serve unread notifications on reconnect
- **Push token hygiene** is critical — immediately remove invalid APNs/FCM tokens to avoid quota waste and provider rate limiting
- **TTL-based presence** with Redis hashes provides automatic cleanup of stale sessions without explicit disconnect handling
- A **common mistake** is treating WebSocket delivery as reliable — network issues, app backgrounding, and server restarts all cause silent connection drops, therefore always have a pull-based fallback
"""
    ),
    # --- 5. Search Engine Architecture ---
    (
        "system-design/search-engine-architecture",
        r"""Explain search engine architecture covering inverted index construction and storage formats, BM25 relevance scoring with term frequency and inverse document frequency, faceted search implementation with aggregation, query parsing with boolean operators and phrase matching, relevance tuning strategies, and distributed indexing with sharding.""",
        r"""# Search Engine Architecture: From Inverted Indexes to Distributed Relevance

## The Core Problem

A search engine must answer the question "which documents match this query, ranked by relevance?" across millions or billions of documents in milliseconds. The naive approach — scanning every document for every query — is O(N * D) where N is query terms and D is documents. With 100M documents, this is impossibly slow. Therefore, the entire architecture revolves around **pre-computed data structures** (inverted indexes) that make query-time lookup O(N * P) where P is the number of matching postings, which is typically orders of magnitude smaller than D.

**Best practice** is to separate the system into three phases: **indexing** (offline, batch or streaming), **query processing** (online, latency-critical), and **ranking** (online, quality-critical). Each phase has different optimization targets and constraints.

## Inverted Index Construction

The **inverted index** is the fundamental data structure of information retrieval. It maps each term to a sorted list of document IDs (the **postings list**) along with term frequency and positional information.

```python
import re
import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Posting:
    # A single occurrence record in the inverted index
    doc_id: int
    term_frequency: int  # how many times term appears in this doc
    positions: list[int] = field(default_factory=list)  # for phrase queries

    def __repr__(self) -> str:
        return f"Posting(doc={self.doc_id}, tf={self.term_frequency})"


@dataclass
class DocumentStats:
    # Per-document statistics needed for scoring
    doc_id: int
    length: int  # total number of terms
    title: str = ""


class InvertedIndex:
    # In-memory inverted index with positional information
    # Production systems use memory-mapped files or SSTable-like formats

    def __init__(self) -> None:
        # term -> sorted list of Postings
        self._index: dict[str, list[Posting]] = defaultdict(list)
        self._doc_stats: dict[int, DocumentStats] = {}
        self._doc_count: int = 0
        self._total_doc_length: int = 0
        # term -> document frequency (number of docs containing term)
        self._df: dict[str, int] = defaultdict(int)

    def _tokenize(self, text: str) -> list[str]:
        # Simple whitespace + punctuation tokenizer with lowercasing
        # Production systems use language-specific analyzers
        tokens = re.findall(r'\b[a-z0-9]+\b', text.lower())
        return tokens

    def _analyze(self, text: str) -> list[str]:
        # Full analysis pipeline: tokenize, normalize, filter
        tokens = self._tokenize(text)
        # Remove common stop words (abbreviated list)
        stop_words = {"the", "a", "an", "is", "are", "was", "in", "of", "to", "and"}
        return [t for t in tokens if t not in stop_words and len(t) > 1]

    def add_document(self, doc_id: int, text: str, title: str = "") -> None:
        # Index a single document
        tokens = self._analyze(text)
        self._doc_count += 1
        self._total_doc_length += len(tokens)
        self._doc_stats[doc_id] = DocumentStats(
            doc_id=doc_id, length=len(tokens), title=title
        )
        # Build term frequency and position maps
        tf_map: dict[str, list[int]] = defaultdict(list)
        for pos, token in enumerate(tokens):
            tf_map[token].append(pos)
        # Create postings
        for term, positions in tf_map.items():
            posting = Posting(
                doc_id=doc_id,
                term_frequency=len(positions),
                positions=positions,
            )
            self._index[term].append(posting)
            self._df[term] += 1

    @property
    def avg_doc_length(self) -> float:
        if self._doc_count == 0:
            return 0.0
        return self._total_doc_length / self._doc_count

    def get_postings(self, term: str) -> list[Posting]:
        analyzed = self._analyze(term)
        if not analyzed:
            return []
        return self._index.get(analyzed[0], [])

    def document_frequency(self, term: str) -> int:
        analyzed = self._analyze(term)
        if not analyzed:
            return 0
        return self._df.get(analyzed[0], 0)
```

The **trade-off** in index design is between index size and query capability. A basic index (doc IDs only) is compact but cannot support phrase queries. Adding **positional information** (the position of each term occurrence) enables phrase matching and proximity queries but increases index size by 3-5x. However, positional indexes are **best practice** for any general-purpose search engine because phrase queries are extremely common.

### Storage Formats

Production search engines (Lucene, Tantivy) store inverted indexes as **immutable segments** on disk. Each segment contains: a **term dictionary** (sorted terms with pointers), **postings lists** (compressed doc ID and frequency arrays), and **stored fields** (original document data for result display). Segments are periodically **merged** to reduce the number of files and reclaim space from deleted documents.

## BM25 Relevance Scoring

**BM25** (Best Matching 25) is the standard relevance scoring function used by Elasticsearch, Solr, and most modern search engines. It improves upon raw TF-IDF by applying **term frequency saturation** and **document length normalization**.

```python
class BM25Scorer:
    # BM25 relevance scoring implementation
    # Parameters k1 and b control term frequency saturation
    # and document length normalization respectively

    def __init__(
        self,
        index: InvertedIndex,
        k1: float = 1.2,  # Term frequency saturation
        b: float = 0.75,  # Length normalization (0=none, 1=full)
    ) -> None:
        self.index = index
        self.k1 = k1
        self.b = b

    def _idf(self, term: str) -> float:
        # Inverse document frequency with smoothing
        # IDF = log((N - df + 0.5) / (df + 0.5) + 1)
        n = self.index._doc_count
        df = self.index.document_frequency(term)
        return math.log((n - df + 0.5) / (df + 0.5) + 1.0)

    def score_document(
        self, query_terms: list[str], doc_id: int
    ) -> float:
        # Compute BM25 score for a document against query terms
        doc_stats = self.index._doc_stats.get(doc_id)
        if doc_stats is None:
            return 0.0
        avg_dl = self.index.avg_doc_length
        doc_len = doc_stats.length
        total_score = 0.0
        for term in query_terms:
            idf = self._idf(term)
            # Find term frequency in this document
            tf = 0
            for posting in self.index.get_postings(term):
                if posting.doc_id == doc_id:
                    tf = posting.term_frequency
                    break
            if tf == 0:
                continue
            # BM25 term frequency component with saturation
            # As tf grows, the score increases but saturates
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (
                1 - self.b + self.b * (doc_len / avg_dl)
            )
            total_score += idf * (numerator / denominator)
        return total_score

    def search(
        self, query: str, top_k: int = 10
    ) -> list[tuple[int, float]]:
        # Search the index and return top-k results by BM25 score
        terms = self.index._analyze(query)
        if not terms:
            return []
        # Collect candidate documents (union of all postings)
        candidates: set[int] = set()
        for term in terms:
            for posting in self.index.get_postings(term):
                candidates.add(posting.doc_id)
        # Score each candidate
        scored = [
            (doc_id, self.score_document(terms, doc_id))
            for doc_id in candidates
        ]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]
```

The parameter `k1` controls **term frequency saturation**: with k1=1.2, the 10th occurrence of a term contributes much less than the first. Setting k1=0 would make BM25 purely binary (term present or absent). The parameter `b` controls **document length normalization**: b=0.75 means longer documents are penalized (they naturally have higher term frequencies). A **common mistake** is setting b=1.0, which over-penalizes long documents and biases results toward short snippets.

## Faceted Search Implementation

**Faceted search** (also called aggregated navigation) lets users filter results by categories, price ranges, ratings, etc. It requires maintaining auxiliary data structures alongside the inverted index.

```python
from dataclasses import dataclass
from typing import Any
from collections import Counter


@dataclass
class FacetValue:
    value: str
    count: int


@dataclass
class FacetResult:
    field_name: str
    values: list[FacetValue]


class FacetIndex:
    # Facet index for categorical and numeric fields
    # Maps field_name -> value -> set of doc_ids

    def __init__(self) -> None:
        self._facets: dict[str, dict[str, set[int]]] = defaultdict(
            lambda: defaultdict(set)
        )
        self._doc_facets: dict[int, dict[str, str]] = defaultdict(dict)

    def index_facet(
        self, doc_id: int, field_name: str, value: str
    ) -> None:
        self._facets[field_name][value].add(doc_id)
        self._doc_facets[doc_id][field_name] = value

    def get_facet_counts(
        self,
        field_name: str,
        candidate_docs: set[int],
        top_n: int = 20,
    ) -> FacetResult:
        # Count facet values within search results
        if field_name not in self._facets:
            return FacetResult(field_name=field_name, values=[])
        counts: Counter[str] = Counter()
        for value, doc_ids in self._facets[field_name].items():
            overlap = len(doc_ids & candidate_docs)
            if overlap > 0:
                counts[value] = overlap
        top_values = [
            FacetValue(value=v, count=c)
            for v, c in counts.most_common(top_n)
        ]
        return FacetResult(field_name=field_name, values=top_values)

    def filter_by_facet(
        self, field_name: str, value: str
    ) -> set[int]:
        # Return doc IDs matching a facet filter
        return self._facets.get(field_name, {}).get(value, set())
```

The **trade-off** with facets is computation cost: computing facet counts requires intersecting the search result set with every facet value's document set. For large catalogs with many facet values, this becomes expensive. **Best practice** is to limit facet computation to the top N values and use approximate counting for low-cardinality facets.

## Query Parsing with Boolean Operators

A production search engine must parse queries like `python AND (web OR api) NOT framework` into a structured query tree.

```python
from dataclasses import dataclass
from typing import Union
from enum import Enum


class QueryOp(Enum):
    AND = "AND"
    OR = "OR"
    NOT = "NOT"
    PHRASE = "PHRASE"
    TERM = "TERM"


@dataclass
class QueryNode:
    op: QueryOp
    value: str = ""  # for TERM nodes
    children: list["QueryNode"] = field(default_factory=list)

    def __repr__(self) -> str:
        if self.op == QueryOp.TERM:
            return f'Term("{self.value}")'
        if self.op == QueryOp.PHRASE:
            return f'Phrase("{self.value}")'
        kids = ", ".join(str(c) for c in self.children)
        return f"{self.op.value}({kids})"


class QueryParser:
    # Recursive descent parser for boolean search queries
    # Supports: AND, OR, NOT, "phrase queries", parentheses

    def __init__(self, query: str) -> None:
        self.tokens = self._tokenize(query)
        self.pos = 0

    def _tokenize(self, query: str) -> list[str]:
        tokens: list[str] = []
        i = 0
        while i < len(query):
            if query[i] == '"':
                # Phrase query
                j = query.index('"', i + 1)
                tokens.append(f'"{query[i+1:j]}"')
                i = j + 1
            elif query[i] in '()':
                tokens.append(query[i])
                i += 1
            elif query[i].isspace():
                i += 1
            else:
                j = i
                while j < len(query) and not query[j].isspace() and query[j] not in '()"':
                    j += 1
                tokens.append(query[i:j])
                i = j
        return tokens

    def parse(self) -> QueryNode:
        result = self._parse_or()
        return result

    def _parse_or(self) -> QueryNode:
        left = self._parse_and()
        while self.pos < len(self.tokens) and self.tokens[self.pos] == "OR":
            self.pos += 1
            right = self._parse_and()
            left = QueryNode(op=QueryOp.OR, children=[left, right])
        return left

    def _parse_and(self) -> QueryNode:
        left = self._parse_not()
        while self.pos < len(self.tokens) and self.tokens[self.pos] == "AND":
            self.pos += 1
            right = self._parse_not()
            left = QueryNode(op=QueryOp.AND, children=[left, right])
        return left

    def _parse_not(self) -> QueryNode:
        if self.pos < len(self.tokens) and self.tokens[self.pos] == "NOT":
            self.pos += 1
            child = self._parse_primary()
            return QueryNode(op=QueryOp.NOT, children=[child])
        return self._parse_primary()

    def _parse_primary(self) -> QueryNode:
        if self.pos >= len(self.tokens):
            return QueryNode(op=QueryOp.TERM, value="")
        token = self.tokens[self.pos]
        if token == "(":
            self.pos += 1
            node = self._parse_or()
            if self.pos < len(self.tokens) and self.tokens[self.pos] == ")":
                self.pos += 1
            return node
        if token.startswith('"') and token.endswith('"'):
            self.pos += 1
            return QueryNode(op=QueryOp.PHRASE, value=token[1:-1])
        self.pos += 1
        return QueryNode(op=QueryOp.TERM, value=token.lower())
```

## Relevance Tuning Strategies

Raw BM25 scores are a starting point, but production search engines apply **boosting** and **signals** to improve result quality. **Field boosting** weights matches in the title higher than the body. **Recency boosting** favors newer documents. **Popularity signals** (click-through rate, page rank) provide query-independent quality indicators.

The key insight is that relevance is not a single number — it is a **learned function** combining multiple signals. Modern search engines use **Learning to Rank (LTR)** models trained on click data to combine BM25, field boosts, freshness, popularity, and dozens of other features into a final relevance score.

## Distributed Indexing with Sharding

At scale, a single machine cannot hold the entire index. **Document-based sharding** partitions documents across N shards, each holding a complete inverted index for its subset of documents.

```python
import hashlib
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class ShardedSearcher:
    # Coordinates search across multiple index shards
    # Each shard holds a subset of documents
    shards: list["SearchShard"]
    num_shards: int = 4

    def assign_shard(self, doc_id: int) -> int:
        # Deterministic shard assignment via hash
        h = hashlib.md5(str(doc_id).encode()).hexdigest()
        return int(h, 16) % self.num_shards

    def distributed_search(
        self, query: str, top_k: int = 10
    ) -> list[tuple[int, float]]:
        # Scatter-gather search across all shards
        # In production, these run in parallel via async/RPC
        all_results: list[tuple[int, float]] = []
        for shard in self.shards:
            # Each shard returns its local top-k
            local_results = shard.search(query, top_k=top_k)
            all_results.extend(local_results)
        # Global merge: re-rank all shard results
        all_results.sort(key=lambda x: x[1], reverse=True)
        return all_results[:top_k]
```

The **trade-off** between document-based and term-based sharding is fundamental. **Document-based** (each shard has all terms for its documents) means every query must hit every shard, but each shard can score independently. **Term-based** (each shard has all documents for its terms) means queries only hit relevant shards, but multi-term queries require cross-shard coordination. **Best practice** is document-based sharding because it is simpler, scales linearly, and avoids the complex coordination of term-based approaches. This is the approach used by Elasticsearch and Solr.

A **pitfall** with distributed search is **score comparability**: BM25 uses corpus-level statistics (document frequency, average document length) which differ across shards. If shard 1 has 1M documents and shard 2 has 500K, the same term gets different IDF values. The solution is to use **global statistics** computed periodically and distributed to all shards, or to use **shard-local statistics** and accept minor ranking differences (which is what Elasticsearch does by default for performance).

## Key Takeaways

- **Inverted indexes** with positional information are the foundation of all text search — positions enable phrase queries and proximity scoring at the cost of 3-5x index size
- **BM25** with k1=1.2 and b=0.75 provides robust relevance scoring out of the box — avoid setting b=1.0 which over-penalizes long documents
- **Faceted search** requires intersecting result sets with facet value sets — limit computation to top-N values and pre-compute for common query patterns
- **Boolean query parsing** with recursive descent supports AND, OR, NOT, and phrase queries — phrase matching uses positional index data to verify term adjacency
- **Document-based sharding** with scatter-gather is the standard distributed search architecture — use global IDF statistics to ensure score comparability across shards
- **Relevance tuning** combines BM25 with field boosting, recency, popularity, and Learning to Rank models — raw text similarity is necessary but not sufficient for good search quality
"""
    ),
]
