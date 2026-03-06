"""Phase 2H: Advanced Reasoning — First Principles Derivation (Part 3/5)
Derive solutions from constraints: event sourcing, load balancer, database index,
distributed lock, feature flag system."""

PAIRS = [
    (
        "thinking/firstprinciples-event-sourcing",
        "My app stores only the current state of entities (e.g., order.status = 'shipped'). But now the business wants a full audit trail of every state change. Retrofitting audit logging feels hacky. Is there a better approach?",
        r'''<think>
Let me think about this from first principles rather than jumping to a pattern name.

What does the business fundamentally need?
1. Know the CURRENT state of an entity (for operations)
2. Know the COMPLETE HISTORY of state changes (for audit)
3. Know WHO changed WHAT and WHEN (for compliance)

Current approach: store only current state
```
orders table: {id: 1, status: "shipped", updated_at: "2024-01-15"}
```
History is lost. We know it's "shipped" but not when it was "created", "paid", "fulfilled".

Naive fix: add an audit_log table
```
audit_log: {entity: "order", id: 1, field: "status", old: "paid", new: "shipped", timestamp: ..., user: ...}
```

This works but has problems:
- Two sources of truth (orders table AND audit_log) — they can diverge
- Audit log is an afterthought — easy to forget to log a change
- Complex to reconstruct past states ("what did order 1 look like on Jan 10?")
- The audit log is derivative — it's generated FROM state changes but isn't THE state changes

What if we flip it? Instead of storing state and deriving history...
Store history and derive state.

The fundamental insight:
- An order isn't a row with a status field
- An order is a SEQUENCE OF EVENTS that happened to it:
  1. OrderCreated {customer: "Alice", items: [...]}
  2. PaymentReceived {amount: 99.99, method: "card"}
  3. ItemsPacked {warehouse: "WH-1"}
  4. OrderShipped {tracking: "1Z999..."}

Current state = replay all events from the beginning
Audit trail = the events themselves (they ARE the history)

This is event sourcing. Let me derive what it needs:

Requirement 1: Event store
- Append-only log of events (immutable — never update, never delete)
- Each event has: entity_id, event_type, data, timestamp, user
- Events are ordered (sequence number per entity)

Requirement 2: Projections (current state)
- Read the event stream, build current state in memory or a read table
- "Projection" = a materialized view of the event stream
- Can have MULTIPLE projections (one for API, one for analytics, one for search)

Requirement 3: Rebuild capability
- If a projection is wrong, rebuild it from the event stream
- Events are the source of truth, projections are derived

Trade-offs:
- Storage: events grow forever (but storage is cheap)
- Complexity: more complex than CRUD (significant learning curve)
- Query performance: need projections for fast reads
- Eventual consistency: projections may lag behind events

When it's worth it:
- Audit trail is a hard requirement (finance, healthcare, compliance)
- Business needs to answer "what happened?" not just "what is?"
- Domain has complex state transitions
- Need to replay or reprocess historical data

When it's overkill:
- Simple CRUD with no audit needs
- Small team unfamiliar with the pattern
- Low-volume, simple entities
</think>

You're feeling the pain of storing state without history. The audit-log-as-afterthought approach has a fundamental flaw: two sources of truth that can diverge. Let me derive a better approach from first principles.

**The core insight: flip the data model**

```
Traditional (state-based):
  Store: current state     → Derive: history (audit log)
  Problem: history is an afterthought, can be forgotten or wrong

Event sourcing (event-based):
  Store: events (history)  → Derive: current state (projection)
  History IS the data. State is computed from it.
```

**Implementation:**

```python
# Event store — the source of truth
from datetime import datetime
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)  # Events are immutable
class Event:
    entity_id: str
    event_type: str
    data: dict
    timestamp: datetime
    user_id: str
    sequence: int

# Storage: append-only table
"""
CREATE TABLE events (
    id BIGSERIAL PRIMARY KEY,
    entity_id UUID NOT NULL,
    entity_type VARCHAR(50) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    data JSONB NOT NULL,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
    user_id UUID NOT NULL,
    sequence INT NOT NULL,
    UNIQUE(entity_id, sequence)  -- Order guarantee per entity
);

-- Append-only: NO UPDATE, NO DELETE allowed
-- (enforce via DB permissions or application-level policy)
CREATE INDEX idx_events_entity ON events(entity_id, sequence);
"""
```

**Recording events instead of updating state:**

```python
class OrderService:
    def __init__(self, event_store):
        self.event_store = event_store

    def create_order(self, customer_id: str, items: list, user_id: str):
        order_id = str(uuid.uuid4())
        self.event_store.append(Event(
            entity_id=order_id,
            event_type="OrderCreated",
            data={"customer_id": customer_id, "items": items},
            timestamp=datetime.utcnow(),
            user_id=user_id,
            sequence=1,
        ))
        return order_id

    def receive_payment(self, order_id: str, amount: float, method: str, user_id: str):
        # Load current state to validate
        order = self._rebuild(order_id)
        if order.status != "pending":
            raise ValueError(f"Cannot pay order in status {order.status}")

        self.event_store.append(Event(
            entity_id=order_id,
            event_type="PaymentReceived",
            data={"amount": amount, "method": method},
            timestamp=datetime.utcnow(),
            user_id=user_id,
            sequence=order.version + 1,
        ))

    def ship_order(self, order_id: str, tracking: str, user_id: str):
        order = self._rebuild(order_id)
        if order.status != "paid":
            raise ValueError(f"Cannot ship order in status {order.status}")

        self.event_store.append(Event(
            entity_id=order_id,
            event_type="OrderShipped",
            data={"tracking_number": tracking},
            timestamp=datetime.utcnow(),
            user_id=user_id,
            sequence=order.version + 1,
        ))

    def _rebuild(self, order_id: str) -> "OrderState":
        """Replay events to get current state."""
        events = self.event_store.get_events(order_id)
        state = OrderState()
        for event in events:
            state.apply(event)
        return state
```

**Projection — deriving current state from events:**

```python
class OrderState:
    """Mutable state built by replaying events."""
    def __init__(self):
        self.status = "new"
        self.customer_id = None
        self.items = []
        self.amount_paid = 0
        self.tracking = None
        self.version = 0

    def apply(self, event: Event):
        self.version = event.sequence
        if event.event_type == "OrderCreated":
            self.status = "pending"
            self.customer_id = event.data["customer_id"]
            self.items = event.data["items"]
        elif event.event_type == "PaymentReceived":
            self.status = "paid"
            self.amount_paid = event.data["amount"]
        elif event.event_type == "OrderShipped":
            self.status = "shipped"
            self.tracking = event.data["tracking_number"]
        elif event.event_type == "OrderDelivered":
            self.status = "delivered"
```

**The audit trail you wanted — it's free:**

```python
# Full history of order 42:
events = event_store.get_events("order-42")
for e in events:
    print(f"[{e.timestamp}] {e.user_id}: {e.event_type} — {e.data}")

# Output:
# [2024-01-10 10:00] alice: OrderCreated — {customer: "Bob", items: [...]}
# [2024-01-10 10:05] system: PaymentReceived — {amount: 99.99, method: "card"}
# [2024-01-11 14:30] warehouse: OrderShipped — {tracking: "1Z999..."}

# "What was the order state on Jan 10 at noon?"
events_until = [e for e in events if e.timestamp <= datetime(2024, 1, 10, 12)]
state = OrderState()
for e in events_until:
    state.apply(e)
# state.status == "paid" (payment received at 10:05, not yet shipped)
```

**When to use this vs. simple audit logging:**

| | Audit Log Table | Event Sourcing |
|---|---|---|
| Complexity | Low | Medium-High |
| Audit trail | Yes (but derivative) | Yes (it IS the data) |
| State reconstruction | Complex joins | Replay events |
| Two sources of truth? | Yes (risk of divergence) | No (events are the truth) |
| Use when | Simple compliance need | Complex workflows, full history required |

Start with event sourcing if audit trail is a core requirement. Use a simple audit log table if you just need "who changed what" and can tolerate occasional gaps.'''
    ),
    (
        "thinking/firstprinciples-load-balancer",
        "I have 3 instances of my web app running. How do I distribute traffic between them? I just have nginx in front right now pointing to one instance.",
        r'''<think>
Let me derive load balancing from first principles.

What's the fundamental problem?
- 3 server instances can each handle N requests/second
- 1 nginx pointing to 1 instance: only using 1/3 of capacity
- Goal: spread requests across all 3

What does a load balancer need to do?
1. Know which backends exist and are healthy
2. Choose which backend gets each request
3. Forward the request and return the response

The choosing algorithm is the interesting part. Options:

Round-robin: 1→2→3→1→2→3...
- Simple, fair distribution
- Problem: if request 1 takes 100ms and request 2 takes 10s, instance 2 gets overloaded
- Assumes all requests are equal (they're not)

Least connections: send to the instance with fewest active requests
- Better than round-robin when request durations vary
- Instance processing a slow query gets fewer new requests
- More adaptive to actual load

Weighted: some instances get more traffic
- Useful if instances have different specs (one has 16GB, another has 8GB)
- Assign weights proportional to capacity

IP hash: hash(client_ip) % num_instances
- Same client always goes to same instance
- Useful for session affinity (sticky sessions)
- Problem: if one instance goes down, all its clients get reshuffled

Random: pick a random instance
- Surprisingly effective! With 3+ instances, random distribution is fairly even
- No state to maintain

Health checking:
- Must detect when an instance is down
- Passive: if a request fails, mark instance as down
- Active: periodically send health check requests (GET /health)
- Both together is best

For nginx, this is actually very simple to configure.
</think>

You're already 90% there with nginx — you just need to add the other two instances and configure load balancing.

**The simplest fix (round-robin — works for most cases):**

```nginx
# /etc/nginx/conf.d/myapp.conf
upstream myapp {
    server 10.0.0.1:8000;  # Instance 1
    server 10.0.0.2:8000;  # Instance 2
    server 10.0.0.3:8000;  # Instance 3
}

server {
    listen 80;
    server_name myapp.com;

    location / {
        proxy_pass http://myapp;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

```bash
# Test and reload
nginx -t && systemctl reload nginx
# Traffic now spreads across all 3 instances
```

**Choosing the right algorithm (derived from constraints):**

```nginx
# Round-robin (default) — requests are equal length
upstream myapp {
    server 10.0.0.1:8000;
    server 10.0.0.2:8000;
    server 10.0.0.3:8000;
}

# Least connections — requests vary in duration
# (e.g., some API calls are fast, some trigger heavy queries)
upstream myapp {
    least_conn;
    server 10.0.0.1:8000;
    server 10.0.0.2:8000;
    server 10.0.0.3:8000;
}

# Weighted — instances have different capacity
upstream myapp {
    server 10.0.0.1:8000 weight=3;  # 16GB RAM, gets 3x traffic
    server 10.0.0.2:8000 weight=2;  # 8GB RAM
    server 10.0.0.3:8000 weight=1;  # 4GB RAM
}

# IP hash — need session stickiness (user always hits same server)
upstream myapp {
    ip_hash;
    server 10.0.0.1:8000;
    server 10.0.0.2:8000;
    server 10.0.0.3:8000;
}
```

**Health checking (critical — detect dead instances):**

```nginx
upstream myapp {
    server 10.0.0.1:8000 max_fails=3 fail_timeout=30s;
    server 10.0.0.2:8000 max_fails=3 fail_timeout=30s;
    server 10.0.0.3:8000 max_fails=3 fail_timeout=30s;
    # After 3 failed requests, mark instance as down for 30 seconds
    # Traffic automatically shifts to healthy instances
}
```

```python
# Your app's health endpoint
@app.get("/health")
def health_check():
    # Check critical dependencies
    try:
        db.execute(text("SELECT 1"))
        return {"status": "healthy"}
    except Exception:
        raise HTTPException(503, "Database unreachable")
```

**Decision guide:**

```
Q: Are all requests roughly equal in duration?
  Yes → round-robin (simplest, default)
  No  → least_conn (adapts to slow requests)

Q: Do instances have different specs?
  Yes → weighted round-robin
  No  → equal weights (default)

Q: Do you use server-side sessions?
  Yes → ip_hash (sticky sessions)
  No  → round-robin or least_conn
  Better: move sessions to Redis so any instance can serve any request
```

For most web apps, `least_conn` with health checks is the best default. It handles variable request durations and automatically routes around failures.'''
    ),
    (
        "thinking/firstprinciples-distributed-lock",
        "I have 3 instances of my worker service processing jobs from a queue. Sometimes two workers pick up the same job and process it twice. How do I prevent this?",
        r'''<think>
Let me derive the solution from first principles.

The fundamental problem: mutual exclusion across multiple processes/machines.
A regular mutex (threading.Lock) only works within one process.
I need a lock that works across 3 separate machines.

What does a distributed lock need?

1. Mutual exclusion: only ONE worker can hold the lock at a time
2. Deadlock freedom: if a worker crashes while holding the lock, it eventually releases
3. Fault tolerance: if the lock service has issues, the system recovers

Where should the lock state live?
- Not in any worker (they're the ones competing)
- Needs to be in a shared, accessible store
- Options: Redis, PostgreSQL, ZooKeeper, etcd

For most apps, Redis is the simplest. Let me derive the Redis lock:

Naive approach:
```
Worker A: SET lock_job_42 "worker-a"   → OK (got lock)
Worker B: SET lock_job_42 "worker-b"   → OK (overwrote A's lock!)
```
WRONG — no mutual exclusion.

Fix: use SET with NX (only set if not exists):
```
Worker A: SET lock_job_42 "worker-a" NX   → OK (got lock)
Worker B: SET lock_job_42 "worker-b" NX   → nil (lock taken)
```
Better — but what if Worker A crashes? Lock held forever.

Fix: add expiry:
```
Worker A: SET lock_job_42 "worker-a" NX EX 30   → OK (lock expires in 30s)
```
If A crashes, lock auto-releases after 30 seconds.

But new problem: what if A is still processing after 30 seconds?
Lock expires, B picks up the same job, now both are processing it.

Fix: extend the lock while still working (heartbeat):
```
While processing:
  Every 10 seconds: if I still hold the lock, extend it by 30s
  Only extend if the lock value is still mine (CAS operation)
```

This is essentially the Redlock pattern (simplified).

For the job queue specifically, there's an even simpler approach:
Use the queue's built-in acknowledgment mechanism.
- Worker takes a job → job becomes "invisible" to other workers
- Worker finishes → acknowledges → job removed from queue
- Worker crashes → visibility timeout expires → job reappears for another worker
- This is how SQS, RabbitMQ, and Redis Streams work

The queue's visibility timeout IS a distributed lock, purpose-built for this use case.
</think>

Two workers processing the same job is a distributed mutual exclusion problem. Let me give you the proper solution.

**The quick fix — use your queue's built-in mechanism:**

```python
# If using Redis Streams (recommended for this pattern):
import redis

r = redis.Redis()
STREAM = "jobs"
GROUP = "workers"
CONSUMER = f"worker-{os.getpid()}"

# Create consumer group (once)
try:
    r.xgroup_create(STREAM, GROUP, id="0", mkstream=True)
except redis.exceptions.ResponseError:
    pass  # Group already exists

while True:
    # Read job — ONLY THIS CONSUMER sees it
    messages = r.xreadgroup(GROUP, CONSUMER, {STREAM: ">"}, count=1, block=5000)

    if not messages:
        continue

    for stream, entries in messages:
        for msg_id, data in entries:
            try:
                process_job(data)
                # Acknowledge: job is done, remove from pending
                r.xack(STREAM, GROUP, msg_id)
            except Exception:
                # Don't acknowledge — job will be re-delivered
                # after the pending timeout
                pass

# If this worker crashes:
# - Unacknowledged messages are claimed by other workers after timeout
# - No duplicate processing because only one consumer gets each message
```

**If you need a general-purpose distributed lock (Redis):**

```python
import redis
import uuid
import time

class DistributedLock:
    def __init__(self, redis_client, name: str, timeout: int = 30):
        self.redis = redis_client
        self.name = f"lock:{name}"
        self.timeout = timeout
        self.token = str(uuid.uuid4())  # Unique to this lock holder

    def acquire(self, retry_interval: float = 0.1, max_wait: float = 10) -> bool:
        """Try to acquire the lock with retry."""
        deadline = time.time() + max_wait
        while time.time() < deadline:
            # SET NX EX = atomic "set if not exists with expiry"
            if self.redis.set(self.name, self.token, nx=True, ex=self.timeout):
                return True
            time.sleep(retry_interval)
        return False

    def release(self):
        """Release only if WE hold the lock (compare-and-delete)."""
        # Lua script ensures atomic check-and-delete
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        self.redis.eval(script, 1, self.name, self.token)

    def extend(self, additional_time: int = None):
        """Extend lock if we still hold it (heartbeat)."""
        ext = additional_time or self.timeout
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        return self.redis.eval(script, 1, self.name, self.token, ext)

    def __enter__(self):
        if not self.acquire():
            raise TimeoutError(f"Could not acquire lock {self.name}")
        return self

    def __exit__(self, *args):
        self.release()


# Usage:
r = redis.Redis()

def process_job(job_id, job_data):
    lock = DistributedLock(r, f"job:{job_id}", timeout=60)

    with lock:
        # Only ONE worker can be here for this job_id
        result = do_expensive_work(job_data)
        save_result(job_id, result)
    # Lock released automatically
```

**Why the Lua scripts matter:**

```python
# WITHOUT Lua (race condition):
if r.get("lock:job:42") == my_token:   # Check
    r.delete("lock:job:42")             # Delete
# Between check and delete, another worker could have acquired the lock!

# WITH Lua (atomic):
# Check and delete happen in ONE Redis operation
# No race condition possible
```

**For your specific case — job queue with exactly-once processing:**

```python
# The idempotent approach (belt AND suspenders):
def process_job(job_id, job_data):
    # 1. Lock prevents concurrent processing
    lock = DistributedLock(r, f"job:{job_id}", timeout=120)
    if not lock.acquire(max_wait=5):
        return  # Another worker has it — skip

    try:
        # 2. Idempotency check prevents reprocessing
        if r.sismember("processed_jobs", job_id):
            return  # Already processed — skip

        result = do_work(job_data)
        save_result(job_id, result)

        # 3. Mark as processed (with TTL for cleanup)
        r.sadd("processed_jobs", job_id)
        r.expire("processed_jobs", 86400 * 7)  # Keep for 7 days
    finally:
        lock.release()
```

The simplest fix is using your queue's built-in consumer groups (Redis Streams, SQS visibility timeout, RabbitMQ ack). Only use a distributed lock if you need mutual exclusion outside of queue processing.'''
    ),
    (
        "thinking/firstprinciples-feature-flags",
        "We want to roll out a new feature to 10% of users first, then gradually increase. We're thinking of hardcoding a random check. Is there a better way?",
        r'''<think>
Let me derive a feature flag system from constraints.

What does a gradual rollout fundamentally need?

1. Decision: is the feature ON for this user? (boolean)
2. Consistency: same user should get the same answer every time (can't flip between requests)
3. Gradability: 10% → 25% → 50% → 100% (change the percentage without deploys)
4. Targetability: maybe 100% for internal users, 10% for external
5. Kill switch: turn it OFF immediately if something breaks

Naive approach: random check
```python
import random
if random.random() < 0.10:  # 10% chance
    show_new_feature()
```

Problems:
1. Not consistent — same user gets different results on each request
2. Can't target specific users (internal team should see it)
3. Changing 10% to 20% requires a deploy
4. No kill switch without another deploy

Better approach: hash the user ID
```python
# hash(user_id) % 100 < 10 → feature on for this user
# Same user always gets same result (deterministic)
# Change 10 to 20 to expand → but still needs deploy
```

This is better for consistency but still needs code deploys to change percentages.

The right approach: separate the flag VALUE from the code.

Code says: "if flag X is on for this user, show the feature"
Config says: "flag X is on for 10% of users" ← changed without deploy

Where should the flag config live?
- Database → can query, but adds latency to every request
- Redis → fast, but need to update carefully
- Config file → needs deploy (defeats the purpose)
- Feature flag service → purpose-built (LaunchDarkly, PostHog, Unleash)

For a simple system: store flags in Redis with a hash-based rollout.

The hash trick for consistent percentage rollout:
- hash(feature_name + user_id) → number 0-99
- If number < rollout_percentage → feature is ON
- Increasing percentage from 10 to 20: all original 10% stay in, new 10% added
- Users don't flip-flop between on and off as you increase the percentage

This is how every major feature flag system works internally.
</think>

Hardcoded random checks are a dead end — users flip-flop between states and you need deploys to change percentages. Let me derive a proper feature flag system.

**The core mechanism (hash-based consistent rollout):**

```python
import hashlib

def is_feature_enabled(feature_name: str, user_id: str, rollout_percent: int) -> bool:
    """
    Deterministic feature flag check.
    Same user always gets the same result for the same percentage.
    Increasing the percentage only ADDS users, never removes.
    """
    # Hash the feature+user to get a stable number 0-99
    key = f"{feature_name}:{user_id}"
    hash_value = int(hashlib.sha256(key.encode()).hexdigest(), 16) % 100

    return hash_value < rollout_percent

# User "alice" + feature "new-checkout":
# hash → 42. If rollout is 10% (42 >= 10) → OFF
#              If rollout is 50% (42 < 50)  → ON
#              If rollout is 100% (42 < 100) → ON
# Alice never flip-flops as you increase from 10→50→100
```

**Full feature flag system (store config in Redis, not code):**

```python
import redis
import json

r = redis.Redis()

class FeatureFlags:
    def __init__(self, redis_client):
        self.redis = redis_client
        self._cache = {}
        self._cache_ttl = 30  # Refresh every 30s

    def is_enabled(self, feature: str, user_id: str = None,
                   attributes: dict = None) -> bool:
        """Check if a feature is enabled for a user."""
        config = self._get_config(feature)
        if not config:
            return False

        # Kill switch — instantly disable
        if not config.get("enabled", True):
            return False

        # User allowlist — always on for specific users
        if user_id and user_id in config.get("allowlist", []):
            return True

        # User blocklist — always off for specific users
        if user_id and user_id in config.get("blocklist", []):
            return False

        # Attribute targeting — e.g., internal users only
        if attributes and config.get("rules"):
            for rule in config["rules"]:
                if self._matches_rule(attributes, rule):
                    return True

        # Percentage rollout
        rollout = config.get("rollout_percent", 0)
        if user_id and rollout > 0:
            key = f"{feature}:{user_id}"
            bucket = int(hashlib.sha256(key.encode()).hexdigest(), 16) % 100
            return bucket < rollout

        return False

    def _get_config(self, feature: str) -> dict:
        """Get flag config from Redis (with local cache)."""
        raw = self.redis.get(f"feature:{feature}")
        if raw:
            return json.loads(raw)
        return None

    def _matches_rule(self, attributes: dict, rule: dict) -> bool:
        attr_value = attributes.get(rule["attribute"])
        if rule["operator"] == "in":
            return attr_value in rule["values"]
        elif rule["operator"] == "eq":
            return attr_value == rule["value"]
        return False


# Usage:
flags = FeatureFlags(r)

@app.get("/checkout")
def checkout(user: User = Depends(get_user)):
    if flags.is_enabled("new-checkout", user_id=str(user.id),
                         attributes={"plan": user.plan, "country": user.country}):
        return new_checkout_flow(user)
    else:
        return old_checkout_flow(user)
```

**Admin API to control flags (no deploys needed):**

```python
@app.post("/admin/features/{feature}")
def update_feature(feature: str, config: FeatureFlagConfig, admin: Admin = Depends()):
    r.set(f"feature:{feature}", json.dumps({
        "enabled": config.enabled,
        "rollout_percent": config.rollout_percent,
        "allowlist": config.allowlist,
        "blocklist": config.blocklist,
        "rules": config.rules,
    }))
    return {"status": "updated"}

# Gradual rollout:
# Day 1: POST /admin/features/new-checkout {"rollout_percent": 10}
# Day 3: POST /admin/features/new-checkout {"rollout_percent": 25}
# Day 7: POST /admin/features/new-checkout {"rollout_percent": 100}
# Emergency: POST /admin/features/new-checkout {"enabled": false}  ← instant kill
```

**Rollout strategy:**

```
1. Internal team first:
   {"enabled": true, "rollout_percent": 0,
    "rules": [{"attribute": "plan", "operator": "eq", "value": "internal"}]}

2. 10% of free users:
   {"rollout_percent": 10}

3. 50% of all users:
   {"rollout_percent": 50}

4. 100% (general availability):
   {"rollout_percent": 100}

5. Remove the flag from code:
   # After flag is at 100% for 2+ weeks with no issues,
   # delete the if/else and keep only the new code path
   # This prevents "flag debt" (hundreds of dead flags)
```

For a small team, this Redis-based system is all you need. If you want pre-built UI, analytics, and A/B testing, PostHog (free, self-hosted) or LaunchDarkly (paid) add those on top.'''
    ),
    (
        "thinking/firstprinciples-database-index",
        "My query is slow. Someone told me to 'add an index' but I don't really understand what that means or how to choose which columns to index. Can you explain from scratch?",
        r'''<think>
Let me derive database indexes from first principles.

What happens when you query without an index?

```sql
SELECT * FROM users WHERE email = 'alice@example.com';
```

The database has to check EVERY row in the users table.
1 million users → 1 million comparisons.
This is called a "full table scan" — O(N).

It's like finding a word in a book by reading every page from start to finish.

What's an index?
It's like the index at the back of a book.
Instead of reading every page, look up "polymorphism" → page 142.

Specifically, a database index is usually a B-tree (balanced tree):
- Keys are sorted
- Finding a key takes O(log N) — binary search in a tree
- 1 million rows → ~20 comparisons (log2 of 1M ≈ 20)

So an index on email means:
- B-tree with all email values, sorted
- Each entry points to the corresponding row
- Lookup: O(log N) instead of O(N)

When should you add an index?
- Columns in WHERE clauses (filtering)
- Columns in JOIN conditions
- Columns in ORDER BY (if you sort by it)
- Columns in GROUP BY (for aggregation)

When should you NOT add an index?
- Columns with very few unique values (boolean, status with 3 values)
  → Index doesn't help much if 50% of rows match
- Tables with very few rows (< 1000)
  → Full scan is fast enough
- Columns that are written much more than read
  → Every INSERT/UPDATE must also update the index

Trade-offs:
- Indexes speed up reads but slow down writes (maintaining the tree)
- Indexes consume disk space (copy of the indexed columns in sorted order)
- Too many indexes = slow inserts

Compound indexes: multiple columns in one index
- INDEX(last_name, first_name) — sorted by last_name, then first_name within same last_name
- Works for: WHERE last_name = 'Smith' AND first_name = 'John'
- Works for: WHERE last_name = 'Smith' (uses first part)
- Does NOT work for: WHERE first_name = 'John' (can't skip first part)
- This is the "leftmost prefix" rule

How to know which indexes to add:
1. Find slow queries (pg_stat_statements, slow query log)
2. Run EXPLAIN on them
3. If you see "Seq Scan" on a large table → probably needs an index
4. If you see "Index Scan" → already using an index

Let me explain this concretely.
</think>

An index is like the index at the back of a book. Without it, finding something means reading every page. Let me explain from scratch.

**Without an index — full table scan:**

```sql
-- "Find Alice's email" in a table of 1 million users
SELECT * FROM users WHERE email = 'alice@example.com';

-- Without index: database reads ALL 1,000,000 rows
-- Checks each one: "Is this alice@example.com? No. Next. No. Next..."
-- Time: ~500ms (depends on table size and disk speed)
```

**With an index — direct lookup:**

```sql
-- Create an index on the email column
CREATE INDEX idx_users_email ON users(email);

-- Now the same query:
SELECT * FROM users WHERE email = 'alice@example.com';
-- Database looks up 'alice@example.com' in the sorted index
-- Like looking up a word in a dictionary — jump to 'A', then 'Al', then 'Ali'...
-- ~20 comparisons instead of 1,000,000
-- Time: ~1ms
```

**How to see if you need an index — use EXPLAIN:**

```sql
-- EXPLAIN shows HOW the database executes your query
EXPLAIN ANALYZE SELECT * FROM users WHERE email = 'alice@example.com';

-- WITHOUT index (bad):
-- Seq Scan on users  (cost=0.00..18345.00 rows=1 width=128)
--   Filter: (email = 'alice@example.com')
--   Rows Removed by Filter: 999999
--   Execution Time: 423.456 ms
-- ^^^^^^^^^^^^^^^ "Seq Scan" = reading every row. SLOW.

-- WITH index (good):
-- Index Scan using idx_users_email on users  (cost=0.42..8.44 rows=1 width=128)
--   Index Cond: (email = 'alice@example.com')
--   Execution Time: 0.052 ms
-- ^^^^^^^^^^^^^^ "Index Scan" = using the index. FAST.
```

**Which columns to index (rules of thumb):**

```sql
-- 1. Columns you filter by (WHERE clause)
SELECT * FROM orders WHERE user_id = 42;
-- → CREATE INDEX idx_orders_user_id ON orders(user_id);

-- 2. Columns you join on
SELECT * FROM orders JOIN users ON orders.user_id = users.id;
-- → user_id should be indexed (and users.id is already indexed as primary key)

-- 3. Columns you sort by (ORDER BY) on large result sets
SELECT * FROM products ORDER BY price;
-- → CREATE INDEX idx_products_price ON products(price);

-- 4. Columns you group by
SELECT category, COUNT(*) FROM products GROUP BY category;
-- → CREATE INDEX idx_products_category ON products(category);
```

**Compound indexes (multiple columns):**

```sql
-- You often filter by BOTH user_id AND status
SELECT * FROM orders WHERE user_id = 42 AND status = 'pending';

-- Single indexes: database can use ONE, then filter the rest
-- Compound index: database uses BOTH at once
CREATE INDEX idx_orders_user_status ON orders(user_id, status);

-- IMPORTANT: column order matters!
-- This index works for:
--   WHERE user_id = 42 AND status = 'pending'  ✓ (uses both)
--   WHERE user_id = 42                          ✓ (uses first column)
--   WHERE status = 'pending'                    ✗ (can't skip first column!)

-- Rule: put the most selective column first
-- (user_id has 100K values, status has 5 → user_id first)
```

**When NOT to index:**

```sql
-- DON'T index boolean/low-cardinality columns alone
CREATE INDEX idx_users_active ON users(is_active);  -- BAD
-- Only 2 values (true/false). If 90% are active, index doesn't help.
-- But: compound index (is_active, created_at) CAN help if you filter both.

-- DON'T index tiny tables
-- A table with 100 rows is fully cached in memory — scan is instant.

-- DON'T over-index write-heavy tables
-- Each INSERT/UPDATE must update ALL indexes
-- 10 indexes on a table = 10x write overhead
```

**Finding your slow queries:**

```sql
-- PostgreSQL: enable pg_stat_statements
-- Shows the slowest queries automatically
SELECT query, calls, mean_exec_time, rows
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Then EXPLAIN each slow query to see if it needs an index
```

**Quick checklist for your app:**

```
1. Run EXPLAIN on your 5 slowest queries
2. If you see "Seq Scan" on a table with > 10K rows → needs index
3. Index the columns in the WHERE clause
4. If filtering by multiple columns → compound index
5. Verify with EXPLAIN that "Index Scan" is now used
6. Monitor: don't add more than 5-6 indexes per table
```

Indexes are the single highest-impact performance optimization in most web apps. One CREATE INDEX statement can turn a 500ms query into a 1ms query.'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
