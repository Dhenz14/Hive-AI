"""Phase 2H: Advanced Reasoning — First Principles Reasoning (Part 1/4)
Design systems from fundamental constraints, not pattern matching.
'Design a cache from scratch', 'Design auth from scratch'."""

PAIRS = [
    (
        "thinking/firstprinciples-design-cache",
        "If you had to design a caching system from scratch — no Redis, no Memcached, no existing solution — how would you approach it? What are the fundamental requirements?",
        r'''<think>
Instead of reaching for Redis, let me reason from first principles about what caching IS and what properties it must have.

What is a cache? At its most fundamental:
- A cache is a FASTER copy of data that exists in a SLOWER store
- It trades space (memory) for time (avoiding slow lookups)
- It's a lossy optimization — the cache can be wrong (stale) or missing data (miss)

What are the fundamental constraints?
1. Memory is limited — can't cache everything
2. Data changes — cached data can become stale
3. Access patterns are unequal — some data is accessed much more than others
4. Consistency matters — how wrong can the cache be?

What must be true for ANY valid cache?
- It must be faster than the source (otherwise pointless)
- It must handle misses (data not in cache → fetch from source)
- It must have a maximum size (memory is finite)
- It must have an eviction policy (what to remove when full)
- It must have a staleness strategy (how to know data is outdated)

Let me derive each component from these constraints:

1. STORAGE: Need O(1) read/write → hash table (dict)
2. EVICTION: When full, remove something. What?
   - Random: simple but might evict frequently-used items
   - FIFO: oldest out. Simple but ignores access patterns
   - LRU: least recently used. Good default — assumes recent access predicts future access
   - LFU: least frequently used. Better for some patterns but more memory overhead
3. STALENESS: How to know data is outdated?
   - TTL: item expires after N seconds. Simple, predictable.
   - Invalidation: source tells cache "this changed." Fresher but requires notification channel.
   - Validation: check with source "is this still current?" before using. Always fresh but adds latency.
4. CONCURRENCY: Multiple threads accessing simultaneously
   - Need thread-safe data structure or locking strategy

Let me build the minimum viable cache from these principles.
</think>

Let me derive a cache from first principles — no existing solutions, just constraints.

**The fundamental constraints**:
```
1. Memory is finite → can't store everything → need EVICTION
2. Data changes → cache can be wrong → need STALENESS STRATEGY
3. Must be faster than source → need O(1) operations → need HASH TABLE
4. Multiple users → need THREAD SAFETY → need LOCKING
5. Not all data equally important → need ACCESS TRACKING
```

**Deriving each component from constraints**:

```python
import time
import threading
from collections import OrderedDict
from typing import TypeVar, Callable, Any

V = TypeVar('V')

class Cache:
    """Cache derived from first principles."""

    def __init__(self, max_size: int, default_ttl: float = 300):
        # Constraint: memory is finite → bounded size
        self._max_size = max_size
        self._default_ttl = default_ttl

        # Derived: need O(1) lookup → hash table
        # Derived: need eviction order → ordered dict (LRU)
        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()

        # Derived: concurrent access → lock
        self._lock = threading.Lock()

    def get(self, key: str) -> Any | None:
        """O(1) lookup. Returns None on miss or expiry."""
        with self._lock:
            if key not in self._store:
                return None  # Cache miss

            value, expires_at = self._store[key]

            # Constraint: data changes → check staleness
            if time.time() > expires_at:
                del self._store[key]
                return None  # Expired → treat as miss

            # Derived from LRU: move to end (most recently used)
            self._store.move_to_end(key)
            return value

    def set(self, key: str, value: Any, ttl: float | None = None) -> None:
        """O(1) insert with eviction if full."""
        ttl = ttl or self._default_ttl
        expires_at = time.time() + ttl

        with self._lock:
            # If key exists, update it
            if key in self._store:
                self._store[key] = (value, expires_at)
                self._store.move_to_end(key)
                return

            # Constraint: memory is finite → evict if full
            while len(self._store) >= self._max_size:
                self._store.popitem(last=False)  # Remove LRU item (front of ordered dict)

            self._store[key] = (value, expires_at)

    def delete(self, key: str) -> bool:
        """Explicit invalidation — source says 'this changed'."""
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def get_or_set(self, key: str, fetch_func: Callable[[], V], ttl: float | None = None) -> V:
        """Cache-aside pattern: get from cache, or fetch and cache."""
        result = self.get(key)
        if result is not None:
            return result

        # Cache miss → fetch from slower source
        value = fetch_func()
        self.set(key, value, ttl)
        return value

    @property
    def stats(self) -> dict:
        """Derived: need observability to know if cache is effective."""
        with self._lock:
            now = time.time()
            live = sum(1 for _, (_, exp) in self._store.items() if exp > now)
            return {
                "size": len(self._store),
                "max_size": self._max_size,
                "live_entries": live,
                "expired_entries": len(self._store) - live,
                "utilization": len(self._store) / self._max_size,
            }
```

**Why each design choice follows from constraints**:
```
Constraint                  → Design Choice           → Why
────────────────────        ──────────────────         ───────
Must be faster than DB      → In-memory hash table     → O(1) vs O(log n) or O(n)
Memory is finite            → max_size + eviction      → Can't grow forever
Data changes                → TTL on each entry        → Bounded staleness
Some data accessed more     → LRU eviction             → Keep hot data, evict cold
Multiple threads            → Lock around operations   → No corrupted state
Need to know if it works    → Stats tracking           → Hit rate, utilization
```

**What Redis adds beyond this** (and why you'd eventually switch):
```
This cache:                        Redis adds:
- In-process, single-machine      - Network-accessible, shared across processes
- Lost on restart                  - Persistence (RDB/AOF snapshots)
- Single eviction policy           - Multiple policies (LRU, LFU, random, volatile)
- No data types                    - Strings, lists, sets, sorted sets, streams
- No pub/sub                       - Pub/sub for cache invalidation
- No clustering                    - Redis Cluster for horizontal scaling

Start with the simple cache for single-process apps.
Switch to Redis when you need cross-process sharing.
```'''
    ),
    (
        "thinking/firstprinciples-design-auth",
        "If you had to design an authentication system from first principles — not 'use JWT' or 'use OAuth' — what would you build and why?",
        r'''<think>
Let me reason from the fundamental problem authentication solves, not from existing solutions.

What is authentication? At its core:
- PROVE you are who you claim to be
- Then REMEMBER that proof so you don't have to prove it again on every request

Fundamental constraints:
1. Users can't send their password with every request (interception risk)
2. The server can't keep everyone's session in memory forever
3. The proof must be UNFORGEABLE (attacker can't create fake proof)
4. The proof must be REVOCABLE (can be invalidated if compromised)
5. The proof must EXPIRE (limits damage window if stolen)

From these constraints, let me derive what's needed:

Step 1: Initial proof (login)
- User provides a SECRET (password, biometric, hardware key)
- Server VERIFIES the secret
- Server issues a TOKEN that proves "this user was verified"

Step 2: The token must be unforgeable
- Option A: Random token → server stores mapping (token → user). Server-side sessions.
- Option B: Signed token → server signs the token with a secret key. Anyone can READ it but can't FORGE it. This is JWT.

Step 3: Remembering the proof
- Option A (server-side): Store in memory/database. Every request = database lookup.
- Option B (client-side): Token contains all info. No database lookup. But can't revoke easily.

These naturally converge to the same solutions the industry uses — because they're derived from the same constraints!

Let me also think about what password storage needs:
- Can't store plaintext (database leak = all passwords exposed)
- Can't use fast hash (brute-force attack is too fast)
- Need slow hash (bcrypt, argon2) — intentionally expensive to compute
- Need salt (prevent rainbow tables)

These aren't arbitrary choices — they're derived from the threat model.
</think>

Let me derive authentication from the fundamental problem, not from existing solutions.

**The fundamental question**: How does a server KNOW a request comes from Alice and not an attacker?

**Constraint derivation**:
```
Problem: Alice needs to prove her identity
Constraint 1: Can't send password every request → too risky (interception)
    → Need a TEMPORARY PROOF (token) issued after one-time verification

Constraint 2: Token must be unforgeable → attacker can't create fake tokens
    → Need CRYPTOGRAPHIC GUARANTEE (signature or server-side record)

Constraint 3: Token must expire → limits damage if stolen
    → Need EXPIRATION built into the token

Constraint 4: Token must be revocable → if compromised, invalidate it
    → Need a REVOCATION MECHANISM (delete from DB or blacklist)

Constraint 5: Can't store passwords in cleartext → database leaks happen
    → Need ONE-WAY TRANSFORMATION (hash)

Constraint 6: Hash must be slow → fast hash = fast brute force
    → Need INTENTIONALLY SLOW hash (bcrypt, argon2)
```

**Deriving the system from constraints**:

```python
import secrets
import hashlib
import time
from dataclasses import dataclass

# ═══════════════════════════════════════
# DERIVED: Password storage (from constraints 5, 6)
# ═══════════════════════════════════════

# Why not SHA-256?
# SHA-256 hashes 1 billion passwords/second on a GPU
# At that rate, any 8-char password is cracked in hours

# Why bcrypt/argon2?
# Designed to be SLOW — 100ms per hash (intentional!)
# 100ms × 1 billion = 3,170 YEARS to brute-force

from argon2 import PasswordHasher
ph = PasswordHasher(
    time_cost=3,       # Number of iterations (more = slower = safer)
    memory_cost=65536,  # KB of memory required (makes GPU attacks expensive)
    parallelism=4,      # Threads (more = more resources needed)
)

def store_password(password: str) -> str:
    # Salt is included automatically (prevents rainbow tables)
    return ph.hash(password)

def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return ph.verify(stored_hash, password)
    except Exception:
        return False


# ═══════════════════════════════════════
# DERIVED: Token issuance (from constraints 1, 2, 3)
# ═══════════════════════════════════════

# Two possible designs emerge from the constraints:

# DESIGN A: Server-side token (random string → database lookup)
# Pros: Revocable (delete from DB). Simple.
# Cons: Every request hits the DB for token lookup.

@dataclass
class ServerToken:
    token: str          # Random, unguessable string
    user_id: str
    created_at: float
    expires_at: float

def create_server_token(user_id: str, ttl: float = 3600) -> ServerToken:
    token = secrets.token_urlsafe(32)  # 256 bits of randomness
    now = time.time()
    record = ServerToken(token=token, user_id=user_id, created_at=now, expires_at=now + ttl)
    db.store_token(record)  # Server remembers the token
    return record

def verify_server_token(token: str) -> str | None:
    record = db.get_token(token)  # DB lookup on every request
    if record and record.expires_at > time.time():
        return record.user_id
    return None

def revoke_server_token(token: str):
    db.delete_token(token)  # Instant revocation — just delete it


# DESIGN B: Self-contained signed token (like JWT — derived from first principles)
# Pros: No DB lookup. Server just verifies signature.
# Cons: Hard to revoke (token is valid until it expires).

import hmac
import json
import base64

SECRET_KEY = secrets.token_bytes(32)

def create_signed_token(user_id: str, ttl: float = 900) -> str:
    """The token CONTAINS the user info, signed so it can't be forged."""
    payload = {
        "sub": user_id,
        "exp": time.time() + ttl,
        "iat": time.time(),
    }
    payload_bytes = base64.urlsafe_b64encode(json.dumps(payload).encode())
    # HMAC signature: proves the server created this token
    signature = hmac.new(SECRET_KEY, payload_bytes, hashlib.sha256).hexdigest()
    return f"{payload_bytes.decode()}.{signature}"

def verify_signed_token(token: str) -> str | None:
    try:
        payload_b64, signature = token.rsplit(".", 1)
        # Verify signature (unforgeable — only server knows SECRET_KEY)
        expected_sig = hmac.new(SECRET_KEY, payload_b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected_sig):
            return None  # Forged token!
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if payload["exp"] < time.time():
            return None  # Expired
        return payload["sub"]
    except Exception:
        return None
```

**The trade-off that every auth system must make**:
```
                    Server-side tokens         Signed tokens (JWT-like)
                    ─────────────────          ──────────────────────
Speed per request:  Slow (DB lookup)           Fast (verify signature)
Revocation:         Instant (delete record)    Hard (must wait for expiry)
Scalability:        Limited by DB              Unlimited (stateless)
Storage:            Server stores all tokens   Client stores the token

Resolution (what the industry does):
  → SHORT-lived signed tokens (15 min) for speed
  → LONG-lived server-side refresh tokens for revocation
  → Best of both: fast + revocable
```

Every modern auth system (JWT, OAuth, session cookies) is a different point on this trade-off curve. They weren't invented — they were **derived** from the same fundamental constraints.'''
    ),
    (
        "thinking/firstprinciples-design-rate-limiter",
        "Design a rate limiter from first principles. Not 'use Redis with a sorted set' — why does rate limiting work the way it does?",
        r'''<think>
Let me reason from the fundamental problem.

What is rate limiting? At its core:
- Limit HOW MANY actions an entity can perform in a TIME WINDOW
- "No more than 100 requests per minute per user"

Fundamental constraints:
1. We need to COUNT actions per entity per time window
2. The count must reset after the window passes
3. Must be efficient (can't slow down the requests we're trying to limit)
4. Must be fair (each entity gets its own limit)
5. Time is continuous but our counting must work with discrete checks

From these constraints, let me derive different algorithms:

Approach 1: Fixed Window
- Divide time into fixed windows (minute 0, minute 1, ...)
- Count requests in each window
- Simple but has edge case: 100 requests at second 59 + 100 at second 61 = 200 in 2 seconds

Approach 2: Sliding Window Log
- Store timestamp of each request
- Count requests in last N seconds
- Accurate but O(n) storage per entity

Approach 3: Sliding Window Counter
- Two fixed windows + interpolation
- Approximation: current_count = previous_window_count * overlap_fraction + current_window_count
- Good accuracy with O(1) storage

Approach 4: Token Bucket
- Each entity has a "bucket" of tokens
- Tokens are added at a fixed rate
- Each request consumes one token
- Allows bursts (up to bucket capacity) with sustained rate limiting
- Most flexible, used by most production systems

Let me derive the token bucket mathematically:
- rate = 10 requests/second
- capacity = 50 tokens (burst allowance)
- tokens refill at 10/second
- Burst: 50 requests instantly, then 10/second steady state

This is the most intuitive because it models a physical constraint: a faucet filling a bucket.
</think>

Let me derive rate limiting from the fundamental problem, not from implementations.

**The fundamental constraint**: A system has finite capacity. Uncontrolled access exceeds capacity → system degrades for everyone.

**Deriving the simplest solution** (and its problems):

```python
# ATTEMPT 1: Fixed Window Counter
# Derivation: Count requests per time window. Reset at window boundary.

class FixedWindowCounter:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.counts: dict[str, tuple[int, int]] = {}  # entity → (count, window_id)

    def allow(self, entity_id: str) -> bool:
        current_window = int(time.time()) // self.window_seconds
        count, window = self.counts.get(entity_id, (0, current_window))

        if window != current_window:
            count = 0  # New window → reset

        if count >= self.max_requests:
            return False

        self.counts[entity_id] = (count + 1, current_window)
        return True

# PROBLEM: "boundary burst"
# Window 1: [0s ─── 59s] — 0 requests in first 58s, 100 at second 59
# Window 2: [60s ── 119s] — 100 requests at second 60, 0 after
# Result: 200 requests in 2 seconds, despite 100/minute limit!
#
#   second 59: ████████████████ 100 requests
#   second 60: ████████████████ 100 requests
#   ← this 2-second window sees 200 requests but each minute is within limit


# ATTEMPT 2: Sliding Window (fixes boundary burst)
# Derivation: Instead of fixed boundaries, look at "last N seconds"

class SlidingWindowLog:
    def __init__(self, max_requests: int, window_seconds: int):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.logs: dict[str, list[float]] = {}

    def allow(self, entity_id: str) -> bool:
        now = time.time()
        cutoff = now - self.window_seconds

        # Keep only timestamps within the window
        timestamps = self.logs.get(entity_id, [])
        timestamps = [t for t in timestamps if t > cutoff]

        if len(timestamps) >= self.max_requests:
            self.logs[entity_id] = timestamps
            return False

        timestamps.append(now)
        self.logs[entity_id] = timestamps
        return True

# PROBLEM: Stores one timestamp per request
# 100K entities × 1000 requests each = 100M timestamps in memory


# ATTEMPT 3: Token Bucket (derived from physical analogy)
# A bucket fills with tokens at a constant rate.
# Each request removes one token. If bucket is empty, request denied.
# Bucket has max capacity (burst allowance).

class TokenBucket:
    """Derived from physical constraint: faucet fills bucket at constant rate."""

    def __init__(self, rate: float, capacity: int):
        """
        rate: tokens added per second (sustained throughput)
        capacity: max tokens (burst allowance)

        Example: rate=10, capacity=50
        → Sustained: 10 requests/second
        → Burst: up to 50 requests instantly, then back to 10/sec
        """
        self.rate = rate
        self.capacity = capacity
        self.buckets: dict[str, tuple[float, float]] = {}  # entity → (tokens, last_refill)

    def allow(self, entity_id: str) -> bool:
        now = time.time()
        tokens, last_refill = self.buckets.get(entity_id, (self.capacity, now))

        # Refill: add tokens based on elapsed time
        elapsed = now - last_refill
        tokens = min(self.capacity, tokens + elapsed * self.rate)

        if tokens < 1:
            self.buckets[entity_id] = (tokens, now)
            return False

        # Consume one token
        self.buckets[entity_id] = (tokens - 1, now)
        return True
```

**Why the industry converged on Token Bucket**:
```
Algorithm          | Storage    | Burst handling | Accuracy | Complexity
Fixed Window       | O(1)/entity | Bad (boundary) | Low      | Simple
Sliding Window Log | O(n)/entity | Perfect        | Perfect  | Memory-heavy
Sliding Window Cnt | O(1)/entity | Good (approx)  | Good     | Moderate
Token Bucket       | O(1)/entity | Configurable   | Good     | Simple

Token Bucket wins because:
- O(1) storage (just 2 numbers per entity)
- Burst is a FEATURE, not a bug (configurable via capacity)
- Simple to implement and reason about
- Maps to physical intuition (faucet + bucket)
```

**The derivation from first principles**:
```
"Limit requests per time" (problem)
        ↓
"Need to count and bound" (constraint)
        ↓
"Fixed windows have boundary bursts" (derived limitation)
        ↓
"Need continuous tracking with O(1) space" (refined constraint)
        ↓
"Refill at constant rate, drain on use" (token bucket — emergent solution)
```

Every real rate limiter — nginx, AWS API Gateway, Cloudflare, Stripe — uses a variant of token bucket or sliding window. Not because someone "invented" it, but because the constraints FORCE this design.'''
    ),
    (
        "thinking/firstprinciples-design-queue",
        "Design a message queue from scratch. What properties must it have? What trade-offs are unavoidable?",
        r'''<think>
Let me reason from what a message queue fundamentally IS.

What is a message queue? At its core:
- A BUFFER between a PRODUCER (sends messages) and a CONSUMER (processes messages)
- Decouples the two: producer doesn't wait for consumer, consumer doesn't need producer online

Fundamental constraints:
1. Messages must not be lost (durability)
2. Messages should be processed exactly once (but this is impossible in distributed systems — at-least-once or at-most-once)
3. Order might matter (FIFO) or might not
4. Multiple consumers might need different messages (routing)
5. Consumers might be slower than producers (backpressure)
6. System must handle consumer failure (redelivery)

Unavoidable trade-offs:
1. Durability vs Speed: writing to disk = safe but slow. Memory-only = fast but data loss on crash.
2. Ordering vs Parallelism: strict FIFO = single consumer. Parallel = ordering lost.
3. At-least-once vs At-most-once: can't have exactly-once without coordination.
4. Throughput vs Latency: batching increases throughput but adds latency.

Let me derive the minimum viable queue from these constraints.
</think>

Deriving a message queue from the fundamental problem it solves:

**The fundamental problem**: Producer creates work faster than consumer can process it. Without a buffer, either the producer blocks (slow) or work is lost (unsafe).

**Constraint derivation**:
```
Problem: decouple producer and consumer
    → Need a BUFFER (queue)

Constraint: messages must not be lost
    → Need PERSISTENCE (disk, not just memory)

Constraint: consumer might crash mid-processing
    → Need ACKNOWLEDGMENT (consumer says "done")
    → Need REDELIVERY (if no ack, give to another consumer)

Constraint: producer might be faster than consumer
    → Need BOUNDED BUFFER + BACKPRESSURE

Constraint: multiple consumers might want different messages
    → Need ROUTING or TOPICS
```

**Minimum viable queue from first principles**:
```python
import json
import time
import threading
import os
from collections import deque
from dataclasses import dataclass, field

@dataclass
class Message:
    id: str
    body: dict
    created_at: float = field(default_factory=time.time)
    delivery_count: int = 0

class SimpleQueue:
    """Message queue derived from fundamental constraints."""

    def __init__(self, name: str, persist_dir: str = "/tmp/queue"):
        self.name = name
        self.persist_dir = persist_dir

        # DERIVED FROM: messages must not be lost → persist to disk
        os.makedirs(persist_dir, exist_ok=True)
        self._queue_file = os.path.join(persist_dir, f"{name}.jsonl")

        # DERIVED FROM: need fast access → in-memory + disk backup
        self._pending: deque[Message] = deque()       # Ready to deliver
        self._in_flight: dict[str, Message] = {}      # Delivered, awaiting ack
        self._lock = threading.Lock()

        # DERIVED FROM: consumer might be slow → bounded size
        self._max_size = 10000

        # DERIVED FROM: consumer might crash → redelivery timeout
        self._visibility_timeout = 30.0  # Seconds before redelivery

        # Load persisted messages on startup
        self._load_from_disk()

    def publish(self, body: dict) -> str:
        """Producer sends a message. Returns message ID."""
        with self._lock:
            if len(self._pending) >= self._max_size:
                raise QueueFullError("Backpressure: queue is full")

            msg = Message(
                id=f"{self.name}-{int(time.time()*1000)}-{os.urandom(4).hex()}",
                body=body,
            )
            self._pending.append(msg)
            self._persist(msg)
            return msg.id

    def receive(self, timeout: float = 0) -> Message | None:
        """Consumer gets next message. Message becomes invisible to others."""
        self._check_redelivery()

        with self._lock:
            if not self._pending:
                return None

            msg = self._pending.popleft()
            msg.delivery_count += 1

            # Move to in-flight: invisible to other consumers
            # DERIVED FROM: exactly-once is impossible, so at-least-once:
            # message stays in-flight until acked or timeout
            self._in_flight[msg.id] = msg
            return msg

    def acknowledge(self, message_id: str) -> None:
        """Consumer confirms processing is complete. Message is removed permanently."""
        with self._lock:
            if message_id in self._in_flight:
                del self._in_flight[message_id]
                # DERIVED FROM: durability → remove from disk too
                self._remove_from_disk(message_id)

    def _check_redelivery(self):
        """DERIVED FROM: consumer might crash → redeliver after timeout."""
        with self._lock:
            now = time.time()
            redeliver = []
            for msg_id, msg in list(self._in_flight.items()):
                if now - msg.created_at > self._visibility_timeout * msg.delivery_count:
                    redeliver.append(msg)
                    del self._in_flight[msg_id]

            for msg in redeliver:
                if msg.delivery_count < 5:  # Max retries
                    self._pending.appendleft(msg)  # Back to front of queue
                else:
                    self._dead_letter(msg)  # Give up → dead letter queue

    def _persist(self, msg: Message):
        with open(self._queue_file, 'a') as f:
            f.write(json.dumps({"id": msg.id, "body": msg.body, "ts": msg.created_at}) + "\n")

    def _dead_letter(self, msg: Message):
        """DERIVED FROM: some messages are unprocessable → don't retry forever."""
        dlq_file = os.path.join(self.persist_dir, f"{self.name}_dlq.jsonl")
        with open(dlq_file, 'a') as f:
            f.write(json.dumps({"id": msg.id, "body": msg.body, "retries": msg.delivery_count}) + "\n")
```

**The unavoidable trade-offs** (no queue can avoid these):
```
Trade-off 1: DURABILITY vs SPEED
  Write to disk on every publish → safe, 1000 msg/sec
  Write to memory only → fast, 1M msg/sec, data lost on crash
  Compromise: batch writes (every 100ms) → 100K msg/sec, ≤100ms data loss window

Trade-off 2: ORDERING vs PARALLELISM
  Strict FIFO → one consumer at a time → limited throughput
  Parallel consumers → messages processed out of order
  Compromise: partition by key → ordered within partition, parallel across partitions
  (This is exactly what Kafka does, and it's derived from this trade-off)

Trade-off 3: AT-LEAST-ONCE vs AT-MOST-ONCE
  At-least-once: consumer might process same message twice (safe but duplicated)
  At-most-once: consumer might miss messages (fast but lossy)
  "Exactly-once": requires idempotent consumers (push complexity to application)

Trade-off 4: THROUGHPUT vs LATENCY
  Deliver immediately → low latency, high overhead per message
  Batch delivery → high throughput, added latency
  Every queue makes this trade-off (Kafka batches, RabbitMQ delivers immediately)
```

**This is why Kafka, RabbitMQ, and SQS exist** — they each chose different points on these trade-off curves. They weren't invented independently; they were derived from the same constraints with different priorities.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
