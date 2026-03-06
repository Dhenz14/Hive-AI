"""Phase 1G: Foundation Thinking — Concurrency & Distributed Systems (Part 4/5)
Distributed consensus, leader election, consistency patterns, CRDTs."""

PAIRS = [
    (
        "thinking/distributed-leader-election",
        "We have 3 instances of our scheduler service behind a load balancer. All 3 are running the same cron jobs, causing every job to execute 3 times. How do we ensure only one instance runs each job?",
        r'''<think>
This is the leader election problem. Options:
1. Database-based locking (simple, uses existing infra)
2. Redis-based lock (fast, but Redis can lose data)
3. ZooKeeper/etcd (strongest guarantees, most complex)
4. Consul sessions
5. Kubernetes leader election (if on K8s)

For most teams, database-based or Redis-based is sufficient. Let me show both.
</think>

## Option 1: Database Leader Election (Simplest)

```python
import socket
import time
from contextlib import contextmanager

class DatabaseLeaderElection:
    HEARTBEAT_INTERVAL = 10  # seconds
    LEASE_DURATION = 30      # seconds

    def __init__(self, db, service_name):
        self.db = db
        self.service_name = service_name
        self.instance_id = f"{socket.gethostname()}-{os.getpid()}"

    def try_become_leader(self) -> bool:
        """Try to acquire or renew leadership."""
        now = time.time()

        # Try to claim leadership if no current leader or lease expired
        result = self.db.execute("""
            INSERT INTO leader_election (service, leader_id, lease_until)
            VALUES (%s, %s, %s)
            ON CONFLICT (service) DO UPDATE
            SET leader_id = %s, lease_until = %s
            WHERE leader_election.lease_until < %s
               OR leader_election.leader_id = %s
            RETURNING leader_id
        """, (
            self.service_name, self.instance_id, now + self.LEASE_DURATION,
            self.instance_id, now + self.LEASE_DURATION,
            now, self.instance_id,
        ))

        return result and result[0]['leader_id'] == self.instance_id

    def run_as_leader(self, work_fn):
        """Run work_fn only if this instance is the leader."""
        while True:
            if self.try_become_leader():
                try:
                    work_fn()
                except Exception:
                    logger.exception("Leader work failed")
            time.sleep(self.HEARTBEAT_INTERVAL)

# Usage
election = DatabaseLeaderElection(db, 'scheduler')

def run_scheduled_jobs():
    for job in get_due_jobs():
        job.execute()

election.run_as_leader(run_scheduled_jobs)
```

```sql
CREATE TABLE leader_election (
    service VARCHAR(100) PRIMARY KEY,
    leader_id VARCHAR(200) NOT NULL,
    lease_until DOUBLE PRECISION NOT NULL
);
```

## Option 2: Redis Leader Election

```python
import redis
import time
import uuid

class RedisLeaderElection:
    def __init__(self, redis_client, service_name, lease_seconds=30):
        self.redis = redis_client
        self.key = f"leader:{service_name}"
        self.instance_id = str(uuid.uuid4())
        self.lease_seconds = lease_seconds

    def is_leader(self) -> bool:
        """Try to become/stay leader. Returns True if this instance is leader."""
        # SET NX = only set if key doesn't exist (atomic)
        acquired = self.redis.set(
            self.key,
            self.instance_id,
            nx=True,               # Only if key doesn't exist
            ex=self.lease_seconds,  # Auto-expire
        )

        if acquired:
            return True

        # Check if we're already the leader and refresh lease
        current = self.redis.get(self.key)
        if current and current.decode() == self.instance_id:
            self.redis.expire(self.key, self.lease_seconds)
            return True

        return False

# Usage
election = RedisLeaderElection(redis_client, 'scheduler')

while True:
    if election.is_leader():
        run_scheduled_jobs()
    time.sleep(10)
```

## Option 3: Kubernetes Native (If on K8s)

```python
# Use the official kubernetes client leader election
from kubernetes import client, config
from kubernetes.leaderelection import leaderelection

config.load_incluster_config()

def on_started_leading():
    print("I'm the leader, starting scheduler")
    run_scheduler()

def on_stopped_leading():
    print("Lost leadership, stopping scheduler")
    stop_scheduler()

leaderelection.LeaderElection(
    lock=leaderelection.LeaseLock(
        name="scheduler-leader",
        namespace="default",
        identity=socket.gethostname(),
    ),
    lease_duration=15,
    renew_deadline=10,
    retry_period=2,
    callbacks=leaderelection.LeaderCallbacks(
        on_started_leading=on_started_leading,
        on_stopped_leading=on_stopped_leading,
    ),
).run()
```

## Which to Choose

| Method | Pros | Cons |
|--------|------|------|
| Database | Uses existing infra, strong consistency | Slower heartbeats |
| Redis | Fast, simple | Redis can lose data on restart |
| Kubernetes | Native K8s support | K8s only |
| ZooKeeper/etcd | Strongest guarantees | Extra infrastructure |

**Default**: Database if you have one. Redis if you need faster failover.'''
    ),
    (
        "thinking/distributed-crdt-intro",
        "Two of our servers can go offline for periods of time (we're building a mobile-first app that works offline). When they come back online, we need to merge their changes without conflicts. Regular 'last write wins' loses data. Is there a better approach?",
        r'''<think>
This is a perfect use case for CRDTs — Conflict-free Replicated Data Types. They're data structures designed to be merged automatically without conflicts.

Types of CRDTs:
1. G-Counter (grow-only counter)
2. PN-Counter (increment/decrement counter)
3. G-Set (grow-only set — add only)
4. OR-Set (observed-remove set — add and remove)
5. LWW-Register (last-writer-wins register)
6. LWW-Map (last-writer-wins map)

For a collaborative/offline-first app, OR-Set and LWW-Map cover most use cases.
</think>

**CRDTs** (Conflict-free Replicated Data Types) — data structures that merge automatically without conflicts:

## The Problem with Last-Write-Wins

```
Server A (offline): Adds "buy milk" to shopping list
Server B (offline): Adds "buy eggs" to shopping list

Last-Write-Wins merge: Only one item survives!
CRDT merge: Both items appear in the list ✓
```

## G-Counter (Grow-Only Counter)

```python
class GCounter:
    """Each node tracks its own count. Total = sum of all nodes."""

    def __init__(self, node_id):
        self.node_id = node_id
        self.counts = {}  # {node_id: count}

    def increment(self, amount=1):
        self.counts[self.node_id] = self.counts.get(self.node_id, 0) + amount

    @property
    def value(self):
        return sum(self.counts.values())

    def merge(self, other: 'GCounter'):
        """Merge by taking max of each node's count."""
        for node_id, count in other.counts.items():
            self.counts[node_id] = max(
                self.counts.get(node_id, 0),
                count,
            )

# Usage
a = GCounter('server-a')
b = GCounter('server-b')

a.increment(5)   # a knows: {a: 5}
b.increment(3)   # b knows: {b: 3}
a.increment(2)   # a knows: {a: 7}

# After reconnection:
a.merge(b)
print(a.value)  # 10 (7 + 3) — nothing lost!
```

## OR-Set (Add and Remove Items)

```python
import uuid

class ORSet:
    """Observed-Remove Set — handles add and remove without conflicts."""

    def __init__(self):
        self.additions = {}   # {item: set of unique_tags}
        self.removals = set()  # set of unique_tags

    def add(self, item):
        tag = str(uuid.uuid4())
        self.additions.setdefault(item, set()).add(tag)

    def remove(self, item):
        if item in self.additions:
            # Remove all OBSERVED tags for this item
            self.removals.update(self.additions[item])

    @property
    def items(self):
        result = set()
        for item, tags in self.additions.items():
            # Item exists if it has tags NOT in removals
            if tags - self.removals:
                result.add(item)
        return result

    def merge(self, other: 'ORSet'):
        # Union of all additions and removals
        for item, tags in other.additions.items():
            self.additions.setdefault(item, set()).update(tags)
        self.removals.update(other.removals)

# Usage
a = ORSet()
b = ORSet()

a.add("milk")
b.add("eggs")
a.remove("milk")

a.merge(b)
print(a.items)  # {"eggs"} — milk was removed, eggs were added
```

## LWW-Map (Last-Writer-Wins per Field)

```python
class LWWMap:
    """Each field tracks its own timestamp. Latest timestamp wins per field."""

    def __init__(self):
        self.data = {}       # {key: value}
        self.timestamps = {} # {key: timestamp}

    def set(self, key, value, timestamp=None):
        timestamp = timestamp or time.time()
        if key not in self.timestamps or timestamp > self.timestamps[key]:
            self.data[key] = value
            self.timestamps[key] = timestamp

    def get(self, key):
        return self.data.get(key)

    def merge(self, other: 'LWWMap'):
        for key in other.data:
            if key not in self.timestamps or other.timestamps[key] > self.timestamps[key]:
                self.data[key] = other.data[key]
                self.timestamps[key] = other.timestamps[key]

# Usage: User profile edited on two offline devices
phone = LWWMap()
tablet = LWWMap()

phone.set('name', 'Alice', timestamp=100)
tablet.set('name', 'Alicia', timestamp=105)  # Later = wins
phone.set('bio', 'Developer', timestamp=110)

phone.merge(tablet)
print(phone.get('name'))  # "Alicia" (tablet's later timestamp wins)
print(phone.get('bio'))   # "Developer" (only on phone)
```

## When to Use CRDTs

| Use CRDTs | Use Regular DB |
|-----------|---------------|
| Offline-first mobile apps | Always-online services |
| Multi-region with sync | Single-region |
| Collaborative editing | Single-user data |
| IoT device data merging | Server-side processing |'''
    ),
    (
        "thinking/distributed-consistent-hashing",
        "We use Redis to cache data across 4 servers. When we add a 5th server, almost all cache keys get remapped and we get a cache stampede. How do we add/remove servers without invalidating the entire cache?",
        r'''<think>
Consistent hashing — instead of `hash(key) % num_servers`, map both keys and servers onto a ring. Each key is assigned to the next server clockwise on the ring. Adding/removing a server only affects 1/N of the keys, not all of them.

With virtual nodes (each server gets multiple positions on the ring), the distribution is more even.
</think>

## The Problem with Modular Hashing

```python
# With 4 servers: hash(key) % 4
# "user:1" → server 2
# "user:2" → server 0
# "user:3" → server 1

# Add 5th server: hash(key) % 5
# "user:1" → server 3  ← MOVED!
# "user:2" → server 2  ← MOVED!
# "user:3" → server 3  ← MOVED!
# Almost EVERYTHING moves → cache stampede
```

## Consistent Hashing

```python
import hashlib
from bisect import bisect_right

class ConsistentHash:
    def __init__(self, nodes=None, virtual_nodes=150):
        self._ring = []         # Sorted hash positions
        self._node_map = {}     # hash_position → node
        self._virtual_nodes = virtual_nodes

        for node in (nodes or []):
            self.add_node(node)

    def _hash(self, key: str) -> int:
        return int(hashlib.md5(key.encode()).hexdigest(), 16)

    def add_node(self, node: str):
        """Add a node with virtual replicas for even distribution."""
        for i in range(self._virtual_nodes):
            virtual_key = f"{node}:vnode:{i}"
            h = self._hash(virtual_key)
            self._ring.append(h)
            self._node_map[h] = node
        self._ring.sort()

    def remove_node(self, node: str):
        """Remove a node — only its keys get redistributed."""
        for i in range(self._virtual_nodes):
            virtual_key = f"{node}:vnode:{i}"
            h = self._hash(virtual_key)
            self._ring.remove(h)
            del self._node_map[h]

    def get_node(self, key: str) -> str:
        """Find which node should handle this key."""
        if not self._ring:
            raise ValueError("No nodes in ring")

        h = self._hash(key)
        idx = bisect_right(self._ring, h)
        if idx == len(self._ring):
            idx = 0  # Wrap around
        return self._node_map[self._ring[idx]]

# Usage
ring = ConsistentHash(['redis-1', 'redis-2', 'redis-3', 'redis-4'])

# Get cache server for a key
server = ring.get_node('user:12345')  # → "redis-2"

# Add a 5th server — only ~1/5 of keys move (not ALL of them)
ring.add_node('redis-5')
```

## Impact Comparison

```
Adding 5th server:
  Modular hash:     ~80% of keys remapped → massive cache stampede
  Consistent hash:  ~20% of keys remapped → minimal impact

Removing a server:
  Modular hash:     ~75% of keys remapped
  Consistent hash:  ~25% of keys remapped (only that server's keys)
```

## With Redis Cluster (Built-in)

```python
# Redis Cluster uses hash slots (16384 slots) with consistent hashing
from redis.cluster import RedisCluster

rc = RedisCluster(
    startup_nodes=[
        {"host": "redis-1", "port": 6379},
        {"host": "redis-2", "port": 6379},
        {"host": "redis-3", "port": 6379},
    ]
)

# Redis Cluster handles key distribution automatically
rc.set("user:12345", "data")  # Automatically routed to correct node
```

**Use Redis Cluster** if you can. Only implement custom consistent hashing for non-Redis distributed caches.'''
    ),
    (
        "thinking/distributed-saga-pattern",
        "Our order process spans 4 services: Order, Payment, Inventory, Shipping. If payment succeeds but inventory fails, we need to refund the payment. How do I implement this rollback across services?",
        r'''<think>
This is the Saga pattern — a sequence of local transactions where each step has a compensating action (rollback). If any step fails, all previous steps are compensated in reverse order.

Two flavors:
1. Choreography — each service listens for events and reacts
2. Orchestration — a central coordinator manages the sequence

For 4 services, orchestration is usually clearer and easier to debug.
</think>

Use the **Saga Pattern** with orchestration — a central coordinator manages the sequence and compensations:

## The Saga Definition

```python
from dataclasses import dataclass
from enum import Enum

class SagaStep:
    def __init__(self, name, action, compensation):
        self.name = name
        self.action = action          # Forward action
        self.compensation = compensation  # Rollback action

class OrderSaga:
    def __init__(self, order_service, payment_service,
                 inventory_service, shipping_service):
        self.steps = [
            SagaStep(
                name="create_order",
                action=order_service.create,
                compensation=order_service.cancel,
            ),
            SagaStep(
                name="process_payment",
                action=payment_service.charge,
                compensation=payment_service.refund,
            ),
            SagaStep(
                name="reserve_inventory",
                action=inventory_service.reserve,
                compensation=inventory_service.release,
            ),
            SagaStep(
                name="schedule_shipping",
                action=shipping_service.schedule,
                compensation=shipping_service.cancel,
            ),
        ]

    def execute(self, order_data: dict) -> dict:
        completed_steps = []
        context = {'order_data': order_data}

        for step in self.steps:
            try:
                result = step.action(context)
                context[step.name] = result
                completed_steps.append(step)
            except Exception as e:
                # Compensate all completed steps in reverse order
                self._compensate(completed_steps, context)
                raise SagaFailed(
                    f"Step '{step.name}' failed: {e}",
                    failed_step=step.name,
                    compensated=True,
                )

        return context

    def _compensate(self, completed_steps, context):
        for step in reversed(completed_steps):
            try:
                step.compensation(context)
            except Exception as e:
                # Compensation failed — needs manual intervention
                logger.critical(
                    f"COMPENSATION FAILED for '{step.name}': {e}. "
                    f"Manual intervention required. Context: {context}"
                )
                alert_ops(step.name, context)
```

## Usage

```python
saga = OrderSaga(order_service, payment_service,
                 inventory_service, shipping_service)

try:
    result = saga.execute({
        'user_id': 123,
        'items': [{'product_id': 1, 'qty': 2}],
        'payment_method': 'card_token_xxx',
    })
    return {'order_id': result['create_order']['id'], 'status': 'confirmed'}
except SagaFailed as e:
    return {'error': str(e), 'status': 'failed'}
```

## Execution Timeline

```
Success:
  create_order ✓ → process_payment ✓ → reserve_inventory ✓ → schedule_shipping ✓
  Done!

Failure at step 3:
  create_order ✓ → process_payment ✓ → reserve_inventory ✗
  Compensate: refund_payment ✓ → cancel_order ✓
  Rolled back cleanly.
```

## Persistent Saga (Production)

```python
class PersistentSaga:
    """Saves state to DB so sagas survive crashes."""

    def execute(self, order_data):
        saga_id = str(uuid.uuid4())
        self._save_state(saga_id, 'started', order_data)

        for i, step in enumerate(self.steps):
            self._save_state(saga_id, f'executing:{step.name}')
            try:
                result = step.action(context)
                self._save_state(saga_id, f'completed:{step.name}', result)
            except Exception:
                self._save_state(saga_id, f'compensating:{step.name}')
                self._compensate(completed_steps, context)
                self._save_state(saga_id, 'failed')
                raise

        self._save_state(saga_id, 'completed')
```

If the process crashes mid-saga, a recovery worker reads the saved state and resumes compensation.'''
    ),
    (
        "thinking/distributed-split-brain",
        "During a network partition, both halves of our cluster elected a leader. When the partition healed, we had conflicting data written by two leaders. How do we prevent split-brain?",
        r'''<think>
Split-brain prevention strategies:
1. Quorum-based leader election (majority required)
2. Fencing tokens (monotonically increasing tokens invalidate old leaders)
3. Odd number of nodes (prevents 50/50 splits)
4. External arbiter (a third-party tiebreaker)
5. STONITH (Shoot The Other Node In The Head — fence old leader)

The most practical approach for software: quorum + fencing tokens.
</think>

## What Happened

```
Normal:    [A] [B] [C]  ← C is leader
               |
           network split
               |
Partition: [A] | [B] [C]
           A elects itself leader!
           Both A and C accept writes → conflicting data
```

## Prevention 1: Quorum (Majority Required)

```python
class QuorumLeaderElection:
    def __init__(self, nodes, node_id):
        self.nodes = nodes
        self.node_id = node_id
        self.quorum_size = len(nodes) // 2 + 1  # Majority

    def try_become_leader(self) -> bool:
        votes = 0
        for node in self.nodes:
            try:
                if node.vote_for(self.node_id):
                    votes += 1
            except ConnectionError:
                pass  # Node unreachable

        # Need MAJORITY to become leader
        if votes >= self.quorum_size:
            return True
        return False

# With 3 nodes, need 2 votes (majority)
# Partition [A] vs [B,C]:
#   A tries to get votes: only gets 1 (itself) → NOT leader
#   C tries to get votes: gets 2 (B and C) → IS leader
# Split-brain prevented!
```

## Prevention 2: Fencing Tokens

```python
class FencedLeader:
    """Each leader gets a monotonically increasing token.
    Storage rejects writes with old tokens."""

    def __init__(self, db):
        self.db = db

    def acquire_leadership(self) -> int:
        """Returns a fencing token (epoch number)."""
        token = self.db.execute(
            "UPDATE leader_state SET epoch = epoch + 1 RETURNING epoch"
        ).scalar()
        return token

    def write_with_fence(self, key, value, fence_token):
        """Only succeeds if fence_token is the latest."""
        result = self.db.execute(
            """UPDATE data SET value = %s
               WHERE key = %s AND fence_token <= %s""",
            (value, key, fence_token)
        )
        if result.rowcount == 0:
            raise StaleLeaderError("A newer leader has taken over")

# Old leader with token=5 tries to write
# New leader already has token=6
# Old leader's writes are rejected → data consistency preserved
```

## Prevention 3: Odd Number of Nodes

```
3 nodes: partition can be [1] vs [2] → 2 has majority ✓
5 nodes: partition can be [2] vs [3] → 3 has majority ✓
4 nodes: partition can be [2] vs [2] → NO majority, BOTH sides freeze!

Always use ODD number of nodes: 3, 5, 7
```

## Prevention 4: Automatic Fencing (STONITH)

```python
# When a new leader is elected, ensure old leader can't write
class LeaderWithFencing:
    def on_leadership_acquired(self):
        # Revoke old leader's database credentials
        self.db.execute(
            "ALTER USER old_leader NOLOGIN"
        )
        # Or: change the shared lock in a way old leader can't write
        self.redis.set('write_lock_owner', self.node_id)

    def before_write(self, data):
        # Verify we're still the legitimate leader
        if self.redis.get('write_lock_owner') != self.node_id:
            raise NotLeaderError("Lost leadership, aborting write")
        self.db.write(data)
```

**Rules**:
1. Always use odd number of nodes (3, 5, 7)
2. Require quorum (majority) for leader election
3. Use fencing tokens to reject writes from stale leaders
4. Verify leadership before every write'''
    ),
]

if __name__ == "__main__":
    for tag, q, a in PAIRS:
        print(f"  [{tag}] {q[:60]}...")
    print(f"\nTotal pairs in this file: {len(PAIRS)}")
